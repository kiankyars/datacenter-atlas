#!/usr/bin/env python3
"""Capture and build the bounded EPBC referrals rights assessment."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
)


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.epbc_referrals import (
    ALL_REFERRALS_URL,
    DETAIL_URL_TEMPLATE,
    EPBCReferralsError,
    EXPECTED_NETWORK_REQUESTS,
    EXPECTED_UNIQUE_REFERRALS,
    GRID_ENDPOINT,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PORTAL_TERMS_URL,
    RELEASE_ID,
    SEARCH_PHRASES,
    TOKEN_URL,
    build_release_documents,
    canonical_json,
    classify_result,
    extract_scoped_power_statements,
    grid_request_document,
    merge_query_rows,
    parse_all_referrals_contract,
    parse_antiforgery_token,
    parse_detail_page,
    parse_grid_response,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    verify_portal_terms,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-epbc-referrals/1.0 (bounded official-source audit)"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
RESPONSE_HEADERS = ("Date", "ETag", "Last-Modified")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--quarantine-dir", type=Path, required=True)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument(
        "--min-request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
    )
    result.add_argument(
        "--max-network-requests", type=int, default=MAX_NETWORK_REQUESTS
    )
    result.add_argument("--max-attempts", type=int, default=3)
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(phrase: str) -> str:
    return phrase.replace(" ", "_")


class BoundedFetcher:
    """Cookie-aware official-host fetcher with a hard attempt cap."""

    def __init__(
        self,
        *,
        timeout: float,
        min_interval: float,
        request_cap: int,
        max_attempts: int,
    ) -> None:
        if timeout <= 0:
            raise EPBCReferralsError("timeout must be positive")
        if min_interval < MIN_REQUEST_INTERVAL_SECONDS:
            raise EPBCReferralsError("request interval must be at least one second")
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise EPBCReferralsError("network request cap must be between 1 and 15")
        if max_attempts < 1:
            raise EPBCReferralsError("max attempts must be positive")
        self.timeout = timeout
        self.min_interval = min_interval
        self.request_cap = request_cap
        self.max_attempts = max_attempts
        self.network_attempts = 0
        self._last_request_started: float | None = None
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def _pace(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(
        self,
        *,
        request_id: str,
        endpoint_kind: str,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retain_raw: bool,
    ) -> tuple[dict[str, Any], bytes]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            if self.network_attempts >= self.request_cap:
                raise EPBCReferralsError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 8))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_attempts += 1
            headers = {
                "Accept": (
                    "application/json, text/javascript, */*; q=0.01"
                    if method == "POST"
                    else "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
                ),
                "Accept-Encoding": "identity",
                "User-Agent": USER_AGENT,
            }
            if extra_headers:
                headers.update(extra_headers)
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    response_body = response.read()
                    content_type = response.headers.get_content_type()
                    metadata = {
                        "attempt": attempt,
                        "bytes": len(response_body),
                        "content_type": content_type,
                        "endpoint_kind": endpoint_kind,
                        "headers": {
                            name.lower(): response.headers[name]
                            for name in RESPONSE_HEADERS
                            if response.headers.get(name) is not None
                        },
                        "http_status": response.status,
                        "method": method,
                        "raw_artifact_retained": retain_raw,
                        "request_body_sha256": (
                            sha256_bytes(body) if body is not None else None
                        ),
                        "request_id": request_id,
                        "retrieved_at": _now(),
                        "sha256": sha256_bytes(response_body),
                        "url": response.geturl(),
                    }
                if metadata["http_status"] != 200 or not response_body:
                    raise EPBCReferralsError(
                        f"unexpected response status/body for {request_id}"
                    )
                return metadata, response_body
            except (HTTPError, URLError, TimeoutError, EPBCReferralsError) as error:
                last_error = error
                retryable = not isinstance(error, HTTPError) or error.code in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                if attempt == self.max_attempts or not retryable:
                    break
        raise EPBCReferralsError(f"failed to retrieve {request_id}") from last_error


def _write_raw(
    quarantine: Path, metadata: dict[str, Any], filename: str, body: bytes
) -> None:
    raw = quarantine / "raw"
    raw.mkdir(mode=0o700, exist_ok=True)
    destination = raw / filename
    if destination.exists() or destination.is_symlink():
        raise EPBCReferralsError(f"quarantine artifact already exists: {filename}")
    destination.write_bytes(body)
    destination.chmod(0o600)
    metadata["quarantine_filename"] = f"raw/{filename}"


def _capture_get(
    fetcher: BoundedFetcher,
    quarantine: Path,
    retrievals: list[dict[str, Any]],
    *,
    request_id: str,
    endpoint_kind: str,
    url: str,
    filename: str | None,
) -> bytes:
    retain = filename is not None
    metadata, body = fetcher.fetch(
        request_id=request_id,
        endpoint_kind=endpoint_kind,
        url=url,
        retain_raw=retain,
    )
    if filename is not None:
        _write_raw(quarantine, metadata, filename, body)
    retrievals.append(metadata)
    return body


def _write_definition(path: Path) -> None:
    body = canonical_json(source_definition())
    if path.exists() or path.is_symlink():
        if not path.is_file() or path.read_bytes() != body:
            raise EPBCReferralsError("existing source definition differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _paths_are_disjoint(*paths: Path) -> bool:
    resolved = [path.resolve(strict=False) for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if not _paths_are_disjoint(
        arguments.quarantine_dir, arguments.output, arguments.definition
    ):
        raise EPBCReferralsError(
            "quarantine, release, and source-definition paths must be disjoint"
        )
    if arguments.quarantine_dir.exists() or arguments.quarantine_dir.is_symlink():
        raise EPBCReferralsError("quarantine directory already exists")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise EPBCReferralsError("output release already exists")
    arguments.quarantine_dir.mkdir(parents=True, mode=0o700)
    fetcher = BoundedFetcher(
        timeout=arguments.timeout,
        min_interval=arguments.min_request_interval,
        request_cap=arguments.max_network_requests,
        max_attempts=arguments.max_attempts,
    )
    retrievals: list[dict[str, Any]] = []

    all_referrals_body = _capture_get(
        fetcher,
        arguments.quarantine_dir,
        retrievals,
        request_id="all_referrals",
        endpoint_kind="portal_search_page",
        url=ALL_REFERRALS_URL,
        filename="all-referrals.html",
    )
    contract = parse_all_referrals_contract(all_referrals_body)

    portal_terms_body = _capture_get(
        fetcher,
        arguments.quarantine_dir,
        retrievals,
        request_id="portal_terms",
        endpoint_kind="portal_terms",
        url=PORTAL_TERMS_URL,
        filename="portal-terms.html",
    )
    terms_checks = verify_portal_terms(portal_terms_body)
    token_body = _capture_get(
        fetcher,
        arguments.quarantine_dir,
        retrievals,
        request_id="token",
        endpoint_kind="anti_forgery_token",
        url=TOKEN_URL,
        filename=None,
    )
    token = parse_antiforgery_token(token_body)

    rows_by_phrase: dict[str, list[dict[str, Any]]] = {}
    query_summaries: list[dict[str, Any]] = []
    for phrase in SEARCH_PHRASES:
        page = 1
        paging_cookie = ""
        phrase_rows: list[dict[str, Any]] = []
        page_hashes: list[str] = []
        item_count: int | None = None
        page_count: int | None = None
        while True:
            request_document = grid_request_document(
                contract,
                phrase=phrase,
                page=page,
                paging_cookie=paging_cookie,
            )
            request_body = json.dumps(
                request_document, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            request_id = f"query_{_slug(phrase)}_page_{page:03d}"
            metadata, response_body = fetcher.fetch(
                request_id=request_id,
                endpoint_kind="entity_grid_query",
                url=GRID_ENDPOINT,
                method="POST",
                body=request_body,
                extra_headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "__RequestVerificationToken": token,
                },
                retain_raw=True,
            )
            _write_raw(
                arguments.quarantine_dir,
                metadata,
                f"query-{_slug(phrase).replace('_', '-')}-page-{page:03d}.json",
                response_body,
            )
            retrievals.append(metadata)
            parsed = parse_grid_response(
                response_body, phrase=phrase, expected_page=page
            )
            if item_count is None:
                item_count = parsed["item_count"]
                page_count = parsed["page_count"]
            elif parsed["item_count"] != item_count or parsed["page_count"] != page_count:
                raise EPBCReferralsError("entity-grid totals changed during pagination")
            phrase_rows.extend(parsed["records"])
            page_hashes.append(sha256_bytes(response_body))
            if not parsed["more_records"]:
                break
            paging_cookie = parsed["next_page_paging_cookie"] or ""
            if not paging_cookie:
                raise EPBCReferralsError("entity-grid omitted the next paging cookie")
            page += 1
            if page_count is not None and page > page_count:
                raise EPBCReferralsError("entity-grid pagination exceeded page count")
        if item_count is None or page_count is None or len(phrase_rows) != item_count:
            raise EPBCReferralsError("entity-grid result arithmetic is inconsistent")
        rows_by_phrase[phrase] = phrase_rows
        query_summaries.append(
            {
                "item_count": item_count,
                "page_count": page_count,
                "phrase": phrase,
                "raw_response_sha256": (
                    page_hashes[0]
                    if len(page_hashes) == 1
                    else sha256_bytes(canonical_json(page_hashes))
                ),
            }
        )

    results = merge_query_rows(rows_by_phrase)
    for index, result in enumerate(results, start=1):
        record_id = result["record_id"]
        detail_body = _capture_get(
            fetcher,
            arguments.quarantine_dir,
            retrievals,
            request_id=f"detail_{index:03d}",
            endpoint_kind="referral_detail",
            url=DETAIL_URL_TEMPLATE.format(record_id=record_id),
            filename=f"detail-{index:03d}.html",
        )
        detail = parse_detail_page(detail_body, expected_record_id=record_id)
        comparisons = {
            "epbc_number": (result["epbc_number"], detail["epbc_number"]),
            "industry_type": (result["industry_type"], detail["industry_type"]),
            "location": (result["location"], detail["location"]),
            "primary_jurisdiction": (
                result["primary_jurisdiction"],
                detail["primary_jurisdiction"],
            ),
            "process_status": (result["process_status"], detail["process_status"]),
            "proposer": (
                result["proposer_or_approval_holder"],
                detail["proposer"],
            ),
            "title": (result["title"], detail["title"]),
        }
        disagreements = {
            field: values
            for field, values in comparisons.items()
            if values[0] != values[1]
        }
        if disagreements:
            raise EPBCReferralsError(
                f"grid/detail fields disagree for quarantined result {index}: "
                f"{sorted(disagreements)}"
            )
        result["classification"] = classify_result(
            result["title"], detail["description_plain_text"]
        )
        result["detail"] = detail
        result["power_statements"] = extract_scoped_power_statements(
            detail["description_plain_text"]
        )
        result["evidence_boundary"] = {
            "annual_energy_consumption_mwh": None,
            "atlas_lifecycle_status": None,
            "construction_verified": False,
            "operation_verified": False,
            "portal_process_status": result["process_status"],
            "unique_physical_site_count": None,
        }

    if fetcher.network_attempts != EXPECTED_NETWORK_REQUESTS:
        raise EPBCReferralsError(
            "frozen capture requires exactly "
            f"{EXPECTED_NETWORK_REQUESTS} successful first-attempt requests"
        )
    capture_without_hash = {
        "captured_at": _now(),
        "contract": {
            key: value
            for key, value in contract.items()
            if key != "base64_secure_configuration"
        },
        "format": "datacenter-atlas-epbc-quarantine-capture-v1",
        "network_attempt_count": fetcher.network_attempts,
        "queries": query_summaries,
        "release_id": RELEASE_ID,
        "results": results,
        "retrievals": retrievals,
        "rights_checks": {
            "portal_terms": terms_checks,
        },
        "schema_version": 1,
    }
    capture_state_sha256 = sha256_bytes(canonical_json(capture_without_hash))
    capture = capture_without_hash | {
        "capture_state_sha256": capture_state_sha256
    }
    capture_path = arguments.quarantine_dir / "capture-state.json"
    capture_path.write_bytes(canonical_json(capture))
    capture_path.chmod(0o600)

    _write_definition(arguments.definition)
    documents = build_release_documents(capture)
    write_release_bundle(arguments.output, documents)
    bundle = validate_release_bundle(arguments.output)
    print(
        json.dumps(
            {
                "closed_set_sha256": bundle["query_summary"]["closed_set_sha256"],
                "network_attempt_count": fetcher.network_attempts,
                "output": str(arguments.output),
                "power_scope_sha256": bundle["query_summary"][
                    "power_scope_assessment"
                ]["scoped_statement_set_sha256"],
                "quarantine": str(arguments.quarantine_dir),
                "release_id": RELEASE_ID,
                "status": "rights_blocked_metadata_only",
                "unique_referrals": EXPECTED_UNIQUE_REFERRALS,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EPBCReferralsError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
