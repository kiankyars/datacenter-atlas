#!/usr/bin/env python3
"""Fetch and freeze the bounded Italy MASE VIA/VAS search assessment."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.italy_mase_via_vas import (
    CAPTURE_FORMAT,
    ItalyMASEVIAVASError,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PORTAL_FOOTER,
    QUERY_SPECS,
    RELEASE_ID,
    SCHEMA_VERSION,
    SEARCH_ENDPOINT,
    SITEMAP_URL,
    canonical_json,
    export_url,
    parse_export_xlsx,
    parse_search_html,
    search_url,
    sha256_bytes,
    source_definition,
    validate_capture,
    validate_release_bundle,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-italy-mase-via-vas/1.0 (bounded metadata audit)"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
MAX_ATTEMPTS_PER_REQUEST = 3
RETRYABLE_HTTP_STATUSES = {500, 502, 503, 504}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--capture-output", type=Path)
    result.add_argument("--capture-only", action="store_true")
    result.add_argument("--from-capture", type=Path)
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument(
        "--minimum-request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
    )
    result.add_argument(
        "--maximum-network-requests", type=int, default=MAX_NETWORK_REQUESTS
    )
    result.add_argument(
        "--maximum-attempts-per-request",
        type=int,
        default=MAX_ATTEMPTS_PER_REQUEST,
    )
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _response_date(value: str | None) -> str:
    if value:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
    return _now()


class _SitemapParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchor_depth = 0
        self._anchor_parts: list[str] = []
        self._anchor_href = ""
        self.page_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "a":
            self._anchor_depth += 1
            if self._anchor_depth == 1:
                self._anchor_parts = []
                self._anchor_href = dict(attrs).get("href") or ""

    def handle_data(self, data: str) -> None:
        self.page_parts.append(data)
        if self._anchor_depth:
            self._anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_depth:
            if self._anchor_depth == 1:
                text = " ".join(" ".join(self._anchor_parts).split())
                self.links.append((text, self._anchor_href))
            self._anchor_depth -= 1

    def result(self) -> tuple[bool, bool]:
        page_text = " ".join(" ".join(self.page_parts).split())
        licence_tokens = ("note legali", "licenza", "licence", "license")
        licence_link = any(
            any(token in f"{text} {href}".casefold() for token in licence_tokens)
            for text, href in self.links
        )
        return PORTAL_FOOTER in page_text, licence_link


def _parse_sitemap(body: bytes) -> tuple[bool, bool]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ItalyMASEVIAVASError("sitemap HTML must be UTF-8") from error
    parser = _SitemapParser()
    parser.feed(text)
    parser.close()
    return parser.result()


class BoundedFetcher:
    """Official-host fetcher with pacing, retries, and a hard attempt cap."""

    def __init__(
        self,
        *,
        timeout: float,
        minimum_interval: float,
        request_cap: int,
        maximum_attempts: int,
    ) -> None:
        if timeout <= 0:
            raise ItalyMASEVIAVASError("timeout must be positive")
        if minimum_interval < MIN_REQUEST_INTERVAL_SECONDS:
            raise ItalyMASEVIAVASError(
                "request interval is below the source contract"
            )
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise ItalyMASEVIAVASError("network request cap is outside the contract")
        if not 1 <= maximum_attempts <= MAX_ATTEMPTS_PER_REQUEST:
            raise ItalyMASEVIAVASError("attempt limit is outside the contract")
        self.timeout = timeout
        self.minimum_interval = minimum_interval
        self.request_cap = request_cap
        self.maximum_attempts = maximum_attempts
        self.network_attempts = 0
        self._last_request_started: float | None = None
        self._opener = build_opener()

    def _pace(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.minimum_interval - (
            time.monotonic() - self._last_request_started
        )
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, *, request_id: str, url: str) -> tuple[dict[str, Any], bytes]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "va.mite.gov.it":
            raise ItalyMASEVIAVASError("request URL is outside the official portal")
        last_error: Exception | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            if self.network_attempts >= self.request_cap:
                raise ItalyMASEVIAVASError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 4))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_attempts += 1
            request = Request(
                url,
                headers={
                    "Accept": (
                        "text/html,application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet;q=0.9,*/*;q=0.8"
                    ),
                    "Accept-Encoding": "identity",
                    "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                    status = response.status
                    final_url = response.geturl()
                    headers = response.headers
            except HTTPError as error:
                last_error = error
                if error.code in RETRYABLE_HTTP_STATUSES:
                    continue
                break
            except (URLError, TimeoutError) as error:
                last_error = error
                continue
            final = urlsplit(final_url)
            if final.scheme != "https" or final.hostname != "va.mite.gov.it":
                raise ItalyMASEVIAVASError(
                    "official request redirected outside the portal"
                )
            if status != 200 or not body:
                last_error = ItalyMASEVIAVASError(
                    f"unexpected response for {request_id}"
                )
                if status in RETRYABLE_HTTP_STATUSES:
                    continue
                break
            metadata: dict[str, Any] = {
                "body_retained": False,
                "bytes": len(body),
                "content_type": headers.get_content_type(),
                "http_status": status,
                "method": "GET",
                "request_id": request_id,
                "response_date": _response_date(headers.get("Date")),
                "sha256": sha256_bytes(body),
                "url": final_url,
            }
            content_disposition = headers.get("Content-Disposition")
            if content_disposition:
                metadata["content_disposition"] = content_disposition
            return metadata, body
        raise ItalyMASEVIAVASError(f"failed to retrieve {request_id}") from last_error


def _projection(rows: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [
        [
            str(row["title"]),
            str(row["proponent"] or ""),
            str(row["object_kind"]),
            str(row["latest_procedure"]),
        ]
        for row in rows
    ]


def fetch_capture(fetcher: BoundedFetcher) -> dict[str, Any]:
    started_at = _now()
    sitemap_request, sitemap_body = fetcher.fetch(
        request_id="rights-sitemap", url=SITEMAP_URL
    )
    footer_present, licence_link_present = _parse_sitemap(sitemap_body)
    if not footer_present or licence_link_present:
        raise ItalyMASEVIAVASError("portal rights evidence changed")

    queries: list[dict[str, Any]] = []
    for spec in QUERY_SPECS:
        query_id = spec["query_id"]
        rows: list[dict[str, Any]] = []
        html_requests: list[dict[str, Any]] = []
        expected_count: int | None = None
        expected_pages: int | None = None
        service_disabled = True
        page = 1
        while expected_pages is None or page <= expected_pages:
            request_metadata, body = fetcher.fetch(
                request_id=f"{query_id}-html-{page:02d}",
                url=search_url(spec["phrase"], page=page),
            )
            if request_metadata["content_type"] != "text/html":
                raise ItalyMASEVIAVASError(f"{query_id} HTML content type changed")
            try:
                parsed = parse_search_html(body)
            except ItalyMASEVIAVASError as error:
                raise ItalyMASEVIAVASError(
                    f"{query_id} HTML page {page}: {error}"
                ) from error
            if (
                not parsed["footer_notice_present"]
                or parsed["legal_or_licence_link_present"]
            ):
                raise ItalyMASEVIAVASError(f"{query_id} rights evidence changed")
            if expected_count is None:
                expected_count = parsed["result_count"]
                expected_pages = parsed["page_count"]
            elif (
                parsed["result_count"] != expected_count
                or parsed["page_count"] != expected_pages
            ):
                raise ItalyMASEVIAVASError(f"{query_id} changed during capture")
            service_disabled = (
                service_disabled and parsed["service_disabled_notice_present"]
            )
            html_requests.append(request_metadata)
            for row in parsed["rows"]:
                rows.append({**row, "query_rank": len(rows) + 1})
            page += 1
        if expected_count is None or expected_pages is None:
            raise ItalyMASEVIAVASError(f"{query_id} capture did not start")
        if len(rows) != expected_count:
            raise ItalyMASEVIAVASError(f"{query_id} HTML row count changed")

        export_request, export_body = fetcher.fetch(
            request_id=f"{query_id}-export", url=export_url(spec["phrase"])
        )
        expected_content_type = source_definition()["endpoint_contract"][
            "export_content_type"
        ]
        if export_request["content_type"] != expected_content_type:
            raise ItalyMASEVIAVASError(f"{query_id} export content type changed")
        export_rows = parse_export_xlsx(export_body)
        html_projection = _projection(rows)
        if export_rows != html_projection:
            raise ItalyMASEVIAVASError(f"{query_id} HTML and export rows differ")
        projection_sha = sha256_bytes(canonical_json(html_projection))
        queries.append(
            {
                "export_projection_sha256": projection_sha,
                "export_request": export_request,
                "export_row_count": len(export_rows),
                "html_page_count": expected_pages,
                "html_projection_sha256": projection_sha,
                "html_requests": html_requests,
                "language": spec["language"],
                "phrase": spec["phrase"],
                "query_id": query_id,
                "result_count": expected_count,
                "rows": rows,
                "service_disabled_notice_present": service_disabled,
            }
        )

    capture = {
        "capture_window": {
            "closed": True,
            "completed_at": _now(),
            "started_at": started_at,
        },
        "format": CAPTURE_FORMAT,
        "network_attempt_count": fetcher.network_attempts,
        "queries": queries,
        "raw_response_bodies_retained": False,
        "release_id": RELEASE_ID,
        "rights_evidence": {
            "footer_notice": PORTAL_FOOTER,
            "portal_specific_open_licence_found": False,
            "raw_redistribution_permitted": False,
            "sitemap_request": sitemap_request,
        },
        "schema_version": SCHEMA_VERSION,
        "source_endpoint": SEARCH_ENDPOINT,
    }
    validate_capture(capture)
    return capture


def _write_new(path: Path, body: bytes, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise ItalyMASEVIAVASError(f"refusing existing {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _write_definition(path: Path) -> None:
    body = canonical_json(source_definition())
    if path.exists() or path.is_symlink():
        if not path.is_file() or path.read_bytes() != body:
            raise ItalyMASEVIAVASError("existing source definition differs")
        return
    _write_new(path, body, "source definition")


def _load_capture(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ItalyMASEVIAVASError("capture input must be a regular file")
    raw = path.read_bytes()
    try:
        capture = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ItalyMASEVIAVASError("capture input is invalid JSON") from error
    if not isinstance(capture, dict) or raw != canonical_json(capture):
        raise ItalyMASEVIAVASError("capture input must be canonical JSON")
    validate_capture(capture)
    return capture


def _summary(capture: Mapping[str, Any], output: Path | None) -> dict[str, Any]:
    memberships = sum(query["result_count"] for query in capture["queries"])
    return {
        "capture_window": capture["capture_window"],
        "network_attempt_count": capture["network_attempt_count"],
        "output": str(output) if output is not None else None,
        "query_hits": {
            query["query_id"]: query["result_count"]
            for query in capture["queries"]
        },
        "query_memberships": memberships,
        "release_id": RELEASE_ID,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only and arguments.capture_output is None:
        raise ItalyMASEVIAVASError("--capture-only requires --capture-output")
    if arguments.capture_only and arguments.from_capture is not None:
        raise ItalyMASEVIAVASError("--capture-only cannot use --from-capture")
    if arguments.from_capture is not None:
        capture = _load_capture(arguments.from_capture)
    else:
        fetcher = BoundedFetcher(
            timeout=arguments.timeout,
            minimum_interval=arguments.minimum_request_interval,
            request_cap=arguments.maximum_network_requests,
            maximum_attempts=arguments.maximum_attempts_per_request,
        )
        capture = fetch_capture(fetcher)
    if arguments.capture_output is not None:
        _write_new(
            arguments.capture_output,
            canonical_json(capture),
            "capture output",
        )
    if arguments.capture_only:
        print(json.dumps(_summary(capture, None), indent=2, sort_keys=True))
        return 0

    _write_definition(arguments.definition)
    write_release_bundle(capture, arguments.output)
    bundle = validate_release_bundle(arguments.output)
    summary = _summary(capture, arguments.output)
    summary["classification_counts"] = bundle["assessment"][
        "classification_counts"
    ]
    summary["exact_deduplicated_records"] = bundle["assessment"]["counts"][
        "exact_deduplicated_records"
    ]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ItalyMASEVIAVASError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
