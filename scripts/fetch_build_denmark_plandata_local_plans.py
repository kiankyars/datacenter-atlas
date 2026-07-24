#!/usr/bin/env python3
"""Fetch, audit, and freeze the bounded Denmark Plandata.dk assessment."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.denmark_plandata_local_plans import (
    CAPABILITIES_URL,
    CAPTURE_FORMAT,
    DenmarkPlandataError,
    LAYER_SPECS,
    LICENSE_JSONLD_URL,
    MAX_BODY_BYTES,
    MAX_CONTROLLED_REQUESTS,
    MAX_FEATURES,
    MAX_PAGES_PER_QUERY,
    MIN_REQUEST_INTERVAL_SECONDS,
    PAGE_SIZE,
    RELEASE_ID,
    ROBOTS_404_SHA256,
    ROBOTS_URL,
    SCHEMA_VERSION,
    canonical_json,
    describe_feature_type_url,
    feature_page_url,
    hits_url,
    parse_feature_page,
    parse_hits_xml,
    query_plan,
    sha256_bytes,
    source_definition,
    validate_capabilities_xml,
    validate_capture,
    validate_license_jsonld,
    validate_release_bundle,
    validate_schema_xml,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
USER_AGENT = "datacenter-atlas-denmark-plandata/1.0 (bounded source assessment)"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _response_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class BoundedFetcher:
    """One-attempt, official-host fetcher with strict pacing and caps."""

    def __init__(
        self,
        *,
        timeout: float,
        minimum_interval: float,
        request_cap: int,
    ) -> None:
        if timeout <= 0:
            raise DenmarkPlandataError("timeout must be positive")
        if minimum_interval < MIN_REQUEST_INTERVAL_SECONDS:
            raise DenmarkPlandataError("request interval is below the source contract")
        if not 1 <= request_cap <= MAX_CONTROLLED_REQUESTS:
            raise DenmarkPlandataError("request cap is outside the source contract")
        self.timeout = timeout
        self.minimum_interval = minimum_interval
        self.request_cap = request_cap
        self.request_count = 0
        self._last_started: float | None = None
        self._opener = build_opener(_NoRedirects())

    def _pace(self) -> None:
        if self._last_started is None:
            return
        remaining = self.minimum_interval - (time.monotonic() - self._last_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(
        self,
        *,
        request_id: str,
        url: str,
        accept: str,
        allowed_statuses: set[int] = {200},
    ) -> tuple[dict[str, Any], bytes]:
        if self.request_count >= self.request_cap:
            raise DenmarkPlandataError("controlled request cap reached")
        self._pace()
        self._last_started = time.monotonic()
        requested_at = _now()
        self.request_count += 1
        request = Request(
            url,
            headers={
                "Accept": accept,
                "Accept-Encoding": "identity",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            response = self._opener.open(request, timeout=self.timeout)
        except HTTPError as error:
            if error.code not in allowed_statuses:
                raise DenmarkPlandataError(
                    f"HTTP error for {request_id}: {error.code}"
                ) from error
            response = error
        except (URLError, TimeoutError) as error:
            raise DenmarkPlandataError(f"network error for {request_id}") from error
        with response:
            body = response.read(MAX_BODY_BYTES + 1)
            status = response.status
            final_url = response.geturl()
            headers = response.headers
        completed_at = _now()
        if status not in allowed_statuses:
            raise DenmarkPlandataError(f"unexpected status for {request_id}: {status}")
        if final_url != url:
            raise DenmarkPlandataError(f"redirect occurred for {request_id}")
        if not body or len(body) > MAX_BODY_BYTES:
            raise DenmarkPlandataError(f"body cap or empty body for {request_id}")
        if headers.get("Content-Encoding"):
            raise DenmarkPlandataError(f"encoded body for {request_id}")
        content_type = headers.get("Content-Type")
        media_type = headers.get_content_type()
        if not content_type or not media_type:
            raise DenmarkPlandataError(f"missing content type for {request_id}")
        metadata = {
            "body_retained": False,
            "bytes": len(body),
            "completed_at": completed_at,
            "content_type": content_type,
            "http_status": status,
            "media_type": media_type,
            "method": "GET",
            "redirect_count": 0,
            "request_id": request_id,
            "requested_at": requested_at,
            "response_date": _response_date(headers.get("Date")),
            "sha256": sha256_bytes(body),
            "url": url,
        }
        return metadata, body


def fetch_capture(fetcher: BoundedFetcher) -> dict[str, Any]:
    started_at = _now()
    licence_request, licence_body = fetcher.fetch(
        request_id="licence-jsonld",
        url=LICENSE_JSONLD_URL,
        accept="application/ld+json",
    )
    if licence_request["media_type"] != "application/ld+json":
        raise DenmarkPlandataError("licence endpoint returned an unexpected type")
    licence_summary = validate_license_jsonld(licence_body)

    robots_request, robots_body = fetcher.fetch(
        request_id="robots",
        url=ROBOTS_URL,
        accept="text/plain,*/*;q=0.1",
        allowed_statuses={404},
    )
    if (
        robots_request["media_type"] != "text/html"
        or sha256_bytes(robots_body) != ROBOTS_404_SHA256
    ):
        raise DenmarkPlandataError("robots response drifted from the reviewed 404")

    capabilities_request, capabilities_body = fetcher.fetch(
        request_id="wfs-capabilities",
        url=CAPABILITIES_URL,
        accept="application/xml,text/xml;q=0.9",
    )
    if capabilities_request["media_type"] != "application/xml":
        raise DenmarkPlandataError("GetCapabilities returned an unexpected type")
    capabilities_summary = validate_capabilities_xml(capabilities_body)

    schema_controls: list[dict[str, Any]] = []
    for index, layer_spec in enumerate(LAYER_SPECS, 1):
        layer = layer_spec["layer"]
        request, body = fetcher.fetch(
            request_id=f"schema-{index:02d}",
            url=describe_feature_type_url(layer),
            accept="application/gml+xml,application/xml;q=0.9,text/xml;q=0.8",
        )
        if request["media_type"] != "application/gml+xml":
            raise DenmarkPlandataError("DescribeFeatureType content type changed")
        schema_controls.append(
            {
                "request": request,
                "summary": validate_schema_xml(
                    layer, body, enforce_pinned_hash=True
                ),
            }
        )

    layers: list[dict[str, Any]] = []
    feature_rows = 0
    plan_by_layer = {
        layer_spec["layer"]: [
            row
            for row in query_plan()["rows"]
            if row["layer"] == layer_spec["layer"]
        ]
        for layer_spec in LAYER_SPECS
    }
    for layer_spec in LAYER_SPECS:
        queries: list[dict[str, Any]] = []
        for plan_row in plan_by_layer[layer_spec["layer"]]:
            query_id = plan_row["query_id"]
            literal = plan_row["literal"]
            hits_request, hits_body = fetcher.fetch(
                request_id=f"{query_id}-hits",
                url=hits_url(layer_spec["layer"], literal),
                accept="application/xml,text/xml;q=0.9",
            )
            if hits_request["media_type"] not in {"application/xml", "text/xml"}:
                raise DenmarkPlandataError("hits response content type changed")
            hits = parse_hits_xml(hits_body)
            matched = hits["number_matched"]
            page_count = min(
                (matched + PAGE_SIZE - 1) // PAGE_SIZE, MAX_PAGES_PER_QUERY
            )
            pages: list[dict[str, Any]] = []
            for page_number in range(1, page_count + 1):
                request, body = fetcher.fetch(
                    request_id=f"{query_id}-page-{page_number:02d}",
                    url=feature_page_url(
                        layer_spec["layer"], literal, page=page_number
                    ),
                    accept="application/json",
                )
                if request["media_type"] != "application/json":
                    raise DenmarkPlandataError("feature page content type changed")
                page = parse_feature_page(
                    body,
                    layer_spec=layer_spec,
                    literal=literal,
                    matched=matched,
                )
                page.update(
                    {
                        "page": page_number,
                        "request": request,
                        "start_index": (page_number - 1) * PAGE_SIZE,
                    }
                )
                if page_number < page_count and page["number_returned"] != PAGE_SIZE:
                    raise DenmarkPlandataError("non-final feature page is short")
                pages.append(page)
                feature_rows += page["number_returned"]
                if feature_rows > MAX_FEATURES:
                    raise DenmarkPlandataError("global feature cap reached")
            captured = sum(page["number_returned"] for page in pages)
            expected = min(matched, PAGE_SIZE * MAX_PAGES_PER_QUERY)
            if captured != expected:
                raise DenmarkPlandataError("feature paging did not reconcile")
            queries.append(
                {
                    "captured_feature_count": captured,
                    "complete": matched <= captured,
                    "hits": hits,
                    "hits_request": hits_request,
                    "layer": layer_spec["layer"],
                    "literal": literal,
                    "pages": pages,
                    "query_id": query_id,
                    "truncated": matched > captured,
                }
            )
        layers.append(
            {
                "layer": layer_spec["layer"],
                "planning_status": layer_spec["planning_status"],
                "queries": queries,
            }
        )
    capture = {
        "capture_window": {
            "closed": True,
            "completed_at": _now(),
            "started_at": started_at,
        },
        "control": {
            "capabilities": {
                "request": capabilities_request,
                "summary": capabilities_summary,
            },
            "licence_jsonld": {
                "request": licence_request,
                "summary": licence_summary,
            },
            "robots": {
                "request": robots_request,
                "summary": {
                    "robots_rule_published": False,
                    "robots_rule_is_reuse_permission": False,
                },
            },
            "schemas": schema_controls,
        },
        "controlled_request_count": fetcher.request_count,
        "detail_requests": 0,
        "document_requests": 0,
        "feature_rows_retrieved": feature_rows,
        "format": CAPTURE_FORMAT,
        "layers": layers,
        "login_or_captcha_requests": 0,
        "maximum_controlled_requests": MAX_CONTROLLED_REQUESTS,
        "maximum_features": MAX_FEATURES,
        "minimum_request_interval_seconds": fetcher.minimum_interval,
        "pdf_requests": 0,
        "raw_response_bodies_retained": False,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }
    return validate_capture(capture)


def _load_capture(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise DenmarkPlandataError("capture must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DenmarkPlandataError("capture is invalid JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise DenmarkPlandataError("capture must be canonical JSON")
    return validate_capture(value)


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
        "--maximum-controlled-requests",
        type=int,
        default=MAX_CONTROLLED_REQUESTS,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only and arguments.from_capture is not None:
        raise DenmarkPlandataError("capture-only and from-capture are exclusive")
    if arguments.from_capture is not None:
        capture = _load_capture(arguments.from_capture)
        mode = "offline_build_from_capture"
    else:
        fetcher = BoundedFetcher(
            timeout=arguments.timeout,
            minimum_interval=arguments.minimum_request_interval,
            request_cap=arguments.maximum_controlled_requests,
        )
        capture = fetch_capture(fetcher)
        mode = "live_capture"
    if arguments.capture_output is not None:
        if arguments.capture_output.exists() or arguments.capture_output.is_symlink():
            raise DenmarkPlandataError("capture output already exists")
        arguments.capture_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.capture_output.write_bytes(canonical_json(capture))
    if arguments.capture_only:
        print(
            json.dumps(
                {
                    "capture_output": str(arguments.capture_output)
                    if arguments.capture_output
                    else None,
                    "controlled_request_count": capture[
                        "controlled_request_count"
                    ],
                    "feature_rows_retrieved": capture["feature_rows_retrieved"],
                    "mode": mode,
                    "release_id": RELEASE_ID,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not arguments.definition.is_file() or arguments.definition.is_symlink():
        raise DenmarkPlandataError("checked-in definition is missing")
    if arguments.definition.read_bytes() != canonical_json(source_definition()):
        raise DenmarkPlandataError("checked-in definition differs")
    write_release_bundle(arguments.output, capture)
    bundle = validate_release_bundle(
        arguments.output, definition_path=arguments.definition
    )
    print(
        json.dumps(
            {
                "controlled_request_count": capture["controlled_request_count"],
                "counts": bundle["assessment"]["counts"],
                "manifest_sha256": sha256_bytes(
                    (arguments.output / "manifest.json").read_bytes()
                ),
                "mode": mode,
                "output": str(arguments.output),
                "release_id": RELEASE_ID,
                "status": bundle["assessment"]["atlas_decision"]["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
