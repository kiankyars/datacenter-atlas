#!/usr/bin/env python3
"""Fetch and build the restricted Chile SEA e-Pertinencia assessment."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.chile_sea_pertinence import (
    ChileSEAPertinenceError,
    EXPECTED_SUCCESSFUL_REQUESTS,
    MANIFEST_FILENAME,
    MAX_ATTEMPTS_PER_REQUEST,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    PRIVACY_URL,
    QUERY_TERMS,
    RELEASE_ID,
    SEARCH_API_URL,
    TERMS_URL,
    canonical_json,
    is_frozen_release,
    make_sanitized_snapshot,
    sanitize_search_response,
    search_payload_bytes,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-chile-sea-pertinence/1.0"
RESPONSE_HEADERS = (
    "Content-Length",
    "Date",
    "ETag",
    "Last-Modified",
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = PROJECT_ROOT / ".staging" / RELEASE_ID
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--capture-only", action="store_true")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument(
        "--min-request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
    )
    result.add_argument(
        "--max-network-requests", type=int, default=MAX_NETWORK_REQUESTS
    )
    result.add_argument(
        "--max-attempts", type=int, default=MAX_ATTEMPTS_PER_REQUEST
    )
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class BoundedFetcher:
    def __init__(
        self,
        *,
        timeout: float,
        min_interval: float,
        request_cap: int,
        max_attempts: int,
    ) -> None:
        if timeout <= 0 or min_interval < MIN_REQUEST_INTERVAL_SECONDS:
            raise ChileSEAPertinenceError("timeout must be positive and interval at least 1s")
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise ChileSEAPertinenceError("network request cap must be between 1 and 10")
        if not 1 <= max_attempts <= MAX_ATTEMPTS_PER_REQUEST:
            raise ChileSEAPertinenceError("maximum attempts must be between 1 and 3")
        self.timeout = timeout
        self.min_interval = min_interval
        self.request_cap = request_cap
        self.max_attempts = max_attempts
        self.network_requests = 0
        self.successful_requests = 0
        self._last_request_started: float | None = None

    def _pace(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(
        self,
        url: str,
        *,
        method: str,
        payload: bytes | None,
        expected_types: set[str],
    ) -> tuple[dict[str, Any], bytes]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            if self.network_requests >= self.request_cap:
                raise ChileSEAPertinenceError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 4))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_requests += 1
            headers = {
                "Accept": "application/json" if method == "POST" else "text/html,*/*;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": USER_AGENT,
            }
            if method == "POST":
                headers["Content-Type"] = "application/json"
            request = Request(url, data=payload, headers=headers, method=method)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    content_type = response.headers.get_content_type()
                    metadata = {
                        "attempt": attempt,
                        "bytes": len(body),
                        "content_type": content_type,
                        "effective_url": response.geturl(),
                        "fetched_at": _now(),
                        "headers": {
                            name.lower(): response.headers[name]
                            for name in RESPONSE_HEADERS
                            if response.headers.get(name) is not None
                        },
                        "http_status": response.status,
                        "method": method,
                        "sha256": sha256_bytes(body),
                        "url": url,
                    }
                if response.status != 200 or not body or content_type not in expected_types:
                    raise ChileSEAPertinenceError(f"unexpected response for {url}")
                self.successful_requests += 1
                return metadata, body
            except (HTTPError, URLError, TimeoutError, ChileSEAPertinenceError) as error:
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
        raise ChileSEAPertinenceError(f"failed to retrieve {url}") from last_error


def _write_capture(staging: Path, filename: str, body: bytes) -> str:
    destination = staging / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ChileSEAPertinenceError(f"capture already exists: {destination}")
    destination.write_bytes(body)
    return str(destination.relative_to(staging))


def _capture(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.staging_dir.exists() or arguments.staging_dir.is_symlink():
        raise ChileSEAPertinenceError("staging directory already exists")
    arguments.staging_dir.mkdir(parents=True)
    batch_started_at = _now()
    fetcher = BoundedFetcher(
        timeout=arguments.timeout,
        min_interval=arguments.min_request_interval,
        request_cap=arguments.max_network_requests,
        max_attempts=arguments.max_attempts,
    )
    retrievals: dict[str, dict[str, Any]] = {}
    query_captures: list[dict[str, Any]] = []

    for index, term in enumerate(QUERY_TERMS, start=1):
        payload = search_payload_bytes(term)
        metadata, response_body = fetcher.fetch(
            SEARCH_API_URL,
            method="POST",
            payload=payload,
            expected_types={"application/json", "text/json"},
        )
        sanitized_rows = sanitize_search_response(response_body, term=term)
        query_captures.append(
            {
                "original_response_bytes": metadata["bytes"],
                "original_response_sha256": metadata["sha256"],
                "query_term": term,
                "rows": sanitized_rows,
            }
        )
        retrievals[f"search_{index}"] = metadata | {
            "query_term": term,
            "request_body_sha256": sha256_bytes(payload),
            "sanitized_snapshot_filename": "sanitized-search-snapshot.json",
        }
        # The unsanitized body is not written to disk or retained in state.
        response_body = b""

    rights_requests = (
        ("privacy", PRIVACY_URL, "raw/sea-privacy.html"),
        ("terms", TERMS_URL, "raw/sea-terms.html"),
    )
    for key, url, filename in rights_requests:
        metadata, body = fetcher.fetch(
            url,
            method="GET",
            payload=None,
            expected_types={"text/html"},
        )
        retrievals[key] = metadata | {
            "filename": _write_capture(arguments.staging_dir, filename, body)
        }

    if fetcher.successful_requests != EXPECTED_SUCCESSFUL_REQUESTS:
        raise ChileSEAPertinenceError("successful request arithmetic changed")
    captured_at = _now()
    snapshot = make_sanitized_snapshot(query_captures, captured_at=captured_at)
    _write_capture(
        arguments.staging_dir,
        "sanitized-search-snapshot.json",
        canonical_json(snapshot),
    )
    state = {
        "batch_started_at": batch_started_at,
        "captured_at": captured_at,
        "maximum_attempts_per_request": arguments.max_attempts,
        "maximum_network_requests": arguments.max_network_requests,
        "minimum_request_interval_seconds": arguments.min_request_interval,
        "network_requests": fetcher.network_requests,
        "release_id": RELEASE_ID,
        "retrievals": retrievals,
        "sanitized_snapshot_filename": "sanitized-search-snapshot.json",
        "successful_requests": fetcher.successful_requests,
        "timeout_seconds": arguments.timeout,
    }
    (arguments.staging_dir / "capture-state.json").write_bytes(canonical_json(state))
    return state


def _retained_bodies(staging: Path, state: dict[str, Any]) -> dict[str, bytes]:
    filenames = {
        state["sanitized_snapshot_filename"],
        state["retrievals"]["privacy"]["filename"],
        state["retrievals"]["terms"]["filename"],
    }
    bodies: dict[str, bytes] = {}
    for filename in filenames:
        artifact = staging / filename
        if not artifact.is_file():
            raise ChileSEAPertinenceError(f"capture artifact is missing: {filename}")
        bodies[filename] = artifact.read_bytes()
    return bodies


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.resume:
        state_path = arguments.staging_dir / "capture-state.json"
        if not state_path.is_file():
            raise ChileSEAPertinenceError("resume state does not exist")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ChileSEAPertinenceError("resume state is not valid JSON") from error
        if state_path.read_bytes() != canonical_json(state):
            raise ChileSEAPertinenceError("resume state is not canonical JSON")
    else:
        state = _capture(arguments)
    if arguments.capture_only:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    if arguments.output.exists() or arguments.output.is_symlink():
        raise ChileSEAPertinenceError("output release already exists")
    try:
        definition = json.loads(arguments.definition.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChileSEAPertinenceError("source definition is not valid JSON") from error
    if definition != source_definition():
        raise ChileSEAPertinenceError("source definition does not match code contract")
    retained = _retained_bodies(arguments.staging_dir, state)
    write_release_bundle(arguments.output, state, retained)
    bundle = validate_release_bundle(arguments.output)
    selection = bundle["assessment"]["selection_assessment"]
    print(
        json.dumps(
            {
                "frozen": is_frozen_release(arguments.output),
                "manifest_sha256": sha256_bytes(
                    (arguments.output / MANIFEST_FILENAME).read_bytes()
                ),
                "network_requests": state["network_requests"],
                "raw_query_hits": selection["raw_query_hits"],
                "release_id": RELEASE_ID,
                "review_candidate_rows": selection["review_candidate_rows"],
                "terminal_process_exclusion_rows": selection[
                    "terminal_process_exclusion_rows"
                ],
                "unique_physical_site_count": bundle["assessment"][
                    "coverage_assessment"
                ]["unique_physical_site_count"],
                "unique_qid_process_rows": selection["unique_qid_process_rows"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
