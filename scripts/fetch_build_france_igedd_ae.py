#!/usr/bin/env python3
"""Fetch and freeze the bounded France IGEDD Ae data-centre assessment."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
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

from datacenter_atlas.france_igedd_ae import (
    ANNUAL_INDEX_URLS,
    CAPTURE_FORMAT,
    CURRENT_2026_URL,
    DOCUMENTS,
    EXPECTED_NETWORK_REQUESTS,
    EXPECTED_SUCCESSFUL_REQUESTS,
    FranceIGEDDAEError,
    MAX_ATTEMPTS_PER_REQUEST,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    OFFICIAL_HOST,
    RELEASE_ID,
    RIGHTS_URL,
    SCHEMA_VERSION,
    build_release_documents,
    canonical_json,
    parse_annual_index,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    verify_rights_page,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-france-igedd/1.0 (bounded official-source audit)"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--quarantine-dir", type=Path, required=True)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
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


def _paths_are_disjoint(*paths: Path) -> bool:
    resolved = [path.resolve(strict=False) for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                return False
    return True


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
            raise FranceIGEDDAEError("timeout must be positive")
        if minimum_interval < MIN_REQUEST_INTERVAL_SECONDS:
            raise FranceIGEDDAEError("request interval must be at least one second")
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise FranceIGEDDAEError("network request cap is outside the contract")
        if not 1 <= maximum_attempts <= MAX_ATTEMPTS_PER_REQUEST:
            raise FranceIGEDDAEError("attempt limit is outside the contract")
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

    def fetch(
        self,
        *,
        request_id: str,
        endpoint_kind: str,
        url: str,
        accepted_statuses: set[int] | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        statuses = accepted_statuses or {200}
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST:
            raise FranceIGEDDAEError("request URL is outside the official IGEDD host")
        last_error: Exception | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            if self.network_attempts >= self.request_cap:
                raise FranceIGEDDAEError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 4))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_attempts += 1
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                    "Accept-Language": "fr-FR,fr;q=0.9",
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
                body = error.read()
                status = error.code
                final_url = error.geturl()
                headers = error.headers
                if status not in statuses:
                    last_error = error
                    if status not in {429, 500, 502, 503, 504}:
                        break
                    continue
            except (URLError, TimeoutError) as error:
                last_error = error
                continue
            final = urlsplit(final_url)
            if final.scheme != "https" or final.hostname != OFFICIAL_HOST:
                raise FranceIGEDDAEError("official request redirected outside IGEDD")
            if status not in statuses or not body:
                last_error = FranceIGEDDAEError(
                    f"unexpected status or empty body for {request_id}"
                )
                if status not in {429, 500, 502, 503, 504}:
                    break
                continue
            content_type = headers.get_content_type()
            return (
                {
                    "attempt": attempt,
                    "bytes": len(body),
                    "content_type": content_type,
                    "endpoint_kind": endpoint_kind,
                    "http_status": status,
                    "method": "GET",
                    "request_id": request_id,
                    "retrieved_at": _now(),
                    "sha256": sha256_bytes(body),
                    "url": final_url,
                },
                body,
            )
        raise FranceIGEDDAEError(f"failed to retrieve {request_id}") from last_error


def _write_raw(
    quarantine: Path,
    metadata: dict[str, Any],
    filename: str,
    body: bytes,
) -> None:
    raw = quarantine / "raw"
    raw.mkdir(mode=0o700, exist_ok=True)
    destination = raw / filename
    if destination.exists() or destination.is_symlink():
        raise FranceIGEDDAEError(f"quarantine artifact already exists: {filename}")
    destination.write_bytes(body)
    destination.chmod(0o600)
    metadata["quarantine_filename"] = f"raw/{filename}"


def _write_definition(path: Path) -> None:
    body = canonical_json(source_definition())
    if path.exists() or path.is_symlink():
        if not path.is_file() or path.read_bytes() != body:
            raise FranceIGEDDAEError("existing source definition differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if not _paths_are_disjoint(
        arguments.quarantine_dir, arguments.output, arguments.definition
    ):
        raise FranceIGEDDAEError(
            "quarantine, release, and definition paths must be disjoint"
        )
    if arguments.quarantine_dir.exists() or arguments.quarantine_dir.is_symlink():
        raise FranceIGEDDAEError("quarantine directory already exists")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise FranceIGEDDAEError("release output already exists")
    arguments.quarantine_dir.mkdir(parents=True, mode=0o700)
    fetcher = BoundedFetcher(
        timeout=arguments.timeout,
        minimum_interval=arguments.minimum_request_interval,
        request_cap=arguments.maximum_network_requests,
        maximum_attempts=arguments.maximum_attempts_per_request,
    )
    retrievals: list[dict[str, Any]] = []
    annual_indexes: list[dict[str, Any]] = []

    for year, url in ANNUAL_INDEX_URLS.items():
        accepted = {404} if year == 2026 else {200}
        metadata, body = fetcher.fetch(
            request_id=f"annual_index_{year}",
            endpoint_kind="annual_opinion_index",
            url=url,
            accepted_statuses=accepted,
        )
        _write_raw(
            arguments.quarantine_dir,
            metadata,
            f"annual-index-{year}.html",
            body,
        )
        retrievals.append(metadata)
        if year <= 2025:
            matches = parse_annual_index(body, year=year, source_url=url)
        else:
            if metadata["http_status"] != 404 or url != CURRENT_2026_URL:
                raise FranceIGEDDAEError("2026 transport anomaly changed")
            matches = []
        annual_indexes.append(
            {
                "bytes": metadata["bytes"],
                "http_status": metadata["http_status"],
                "matches": matches,
                "retrieved_at": metadata["retrieved_at"],
                "sha256": metadata["sha256"],
                "url": url,
                "year": year,
            }
        )

    rights_metadata, rights_body = fetcher.fetch(
        request_id="rights",
        endpoint_kind="legal_notice",
        url=RIGHTS_URL,
    )
    _write_raw(
        arguments.quarantine_dir,
        rights_metadata,
        "rights.html",
        rights_body,
    )
    retrievals.append(rights_metadata)
    rights_checks = verify_rights_page(rights_body)

    captured_documents: list[dict[str, Any]] = []
    for document_id, expected in DOCUMENTS.items():
        metadata, body = fetcher.fetch(
            request_id=document_id,
            endpoint_kind="environmental_authority_opinion_pdf",
            url=expected["url"],
        )
        _write_raw(
            arguments.quarantine_dir,
            metadata,
            f"{document_id}.pdf",
            body,
        )
        retrievals.append(metadata)
        for field in ("bytes", "sha256", "url"):
            if metadata[field] != expected[field]:
                raise FranceIGEDDAEError(
                    f"official opinion document changed: {document_id}"
                )
        captured_documents.append(
            {
                "bytes": metadata["bytes"],
                "document_id": document_id,
                "sha256": metadata["sha256"],
                "url": metadata["url"],
            }
        )

    if fetcher.network_attempts != EXPECTED_NETWORK_REQUESTS:
        raise FranceIGEDDAEError(
            "frozen capture requires exactly "
            f"{EXPECTED_NETWORK_REQUESTS} first-attempt requests"
        )
    successful = sum(row["http_status"] == 200 for row in retrievals)
    if successful != EXPECTED_SUCCESSFUL_REQUESTS:
        raise FranceIGEDDAEError("successful-request arithmetic changed")
    capture_without_hash = {
        "annual_indexes": annual_indexes,
        "captured_at": _now(),
        "documents": captured_documents,
        "format": CAPTURE_FORMAT,
        "network_attempt_count": fetcher.network_attempts,
        "release_id": RELEASE_ID,
        "retrievals": retrievals,
        "rights_checks": rights_checks,
        "schema_version": SCHEMA_VERSION,
        "successful_request_count": successful,
    }
    capture = capture_without_hash | {
        "capture_state_sha256": sha256_bytes(canonical_json(capture_without_hash))
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
                "archive_matches": bundle["annual_index"][
                    "archive_closed_match_count"
                ],
                "current_2026_origin_capture_complete": False,
                "network_attempts": fetcher.network_attempts,
                "output": str(arguments.output),
                "quarantine": str(arguments.quarantine_dir),
                "release_id": RELEASE_ID,
                "supplemental_follow_ups": 1,
                "unique_project_sites": 3,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FranceIGEDDAEError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
