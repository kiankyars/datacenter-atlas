#!/usr/bin/env python3
"""Fetch and build the bounded IAAC data-center registry assessment."""

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

from datacenter_atlas.iaac_registry import (
    DIRECT_PROJECTS,
    EXPECTED_DIRECT_RESULTS,
    EXPECTED_EXCLUDED_RESULTS,
    EXPECTED_NETWORK_REQUESTS,
    EXPECTED_SEARCH_RESULTS,
    GEOSPATIAL_DOCUMENTS,
    IAACRegistryError,
    MANIFEST_FILENAME,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    RELEASE_ID,
    SEARCH_URL,
    geospatial_document_url,
    is_frozen_release,
    parse_geospatial_download_url,
    project_url,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-iaac-registry/1.0"
RESPONSE_HEADERS = ("Content-Length", "Date", "ETag", "Last-Modified")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = PROJECT_ROOT / ".staging" / "iaac-data-center-search-2026-07-18-v1"
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
    result.add_argument("--max-network-requests", type=int, default=MAX_NETWORK_REQUESTS)
    result.add_argument("--max-attempts", type=int, default=3)
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
        if timeout <= 0 or min_interval < 1:
            raise IAACRegistryError("timeout must be positive and interval at least 1s")
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise IAACRegistryError("network request cap must be between 1 and 20")
        if max_attempts < 1:
            raise IAACRegistryError("max attempts must be positive")
        self.timeout = timeout
        self.min_interval = min_interval
        self.request_cap = request_cap
        self.max_attempts = max_attempts
        self.network_requests = 0
        self._last_request_started: float | None = None

    def _pace(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, url: str, *, expected_types: set[str]) -> tuple[dict[str, Any], bytes]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            if self.network_requests >= self.request_cap:
                raise IAACRegistryError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 8))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_requests += 1
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/zip;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                    "User-Agent": USER_AGENT,
                },
            )
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
                        "sha256": sha256_bytes(body),
                        "url": url,
                    }
                if response.status != 200 or not body or content_type not in expected_types:
                    raise IAACRegistryError(f"unexpected response for {url}")
                return metadata, body
            except (HTTPError, URLError, TimeoutError, IAACRegistryError) as error:
                last_error = error
                retryable = not isinstance(error, HTTPError) or error.code in {
                    429, 500, 502, 503, 504,
                }
                if attempt == self.max_attempts or not retryable:
                    break
        raise IAACRegistryError(f"failed to retrieve {url}") from last_error


def _write_capture(staging: Path, filename: str, body: bytes) -> str:
    destination = staging / "raw" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise IAACRegistryError(f"capture already exists: {destination}")
    destination.write_bytes(body)
    return str(destination.relative_to(staging))


def _capture(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.staging_dir.exists():
        raise IAACRegistryError("staging directory already exists")
    arguments.staging_dir.mkdir(parents=True)
    fetcher = BoundedFetcher(
        timeout=arguments.timeout,
        min_interval=arguments.min_request_interval,
        request_cap=arguments.max_network_requests,
        max_attempts=arguments.max_attempts,
    )
    retrievals: dict[str, dict[str, Any]] = {}

    metadata, body = fetcher.fetch(SEARCH_URL, expected_types={"text/html"})
    retrievals["search"] = metadata | {
        "filename": _write_capture(arguments.staging_dir, "search.html", body)
    }
    for reference in sorted(DIRECT_PROJECTS):
        metadata, body = fetcher.fetch(
            project_url(reference), expected_types={"text/html"}
        )
        retrievals[f"project_{reference}"] = metadata | {
            "filename": _write_capture(
                arguments.staging_dir, f"project-{reference}.html", body
            ),
            "project_reference": reference,
        }

    landing_bodies: dict[str, bytes] = {}
    for document_id, project_reference in sorted(GEOSPATIAL_DOCUMENTS.items()):
        metadata, body = fetcher.fetch(
            geospatial_document_url(document_id), expected_types={"text/html"}
        )
        landing_bodies[document_id] = body
        retrievals[f"geospatial_landing_{document_id}"] = metadata | {
            "document_id": document_id,
            "filename": _write_capture(
                arguments.staging_dir, f"geospatial-{document_id}.html", body
            ),
            "project_reference": project_reference,
        }

    for document_id, project_reference in sorted(GEOSPATIAL_DOCUMENTS.items()):
        url = parse_geospatial_download_url(
            landing_bodies[document_id], document_id=document_id
        )
        metadata, body = fetcher.fetch(
            url,
            expected_types={
                "application/zip",
                "application/x-zip-compressed",
                "application/octet-stream",
            },
        )
        retrievals[f"geospatial_archive_{document_id}"] = metadata | {
            "document_id": document_id,
            "filename": _write_capture(
                arguments.staging_dir, f"geospatial-{document_id}.zip", body
            ),
            "project_reference": project_reference,
        }

    if fetcher.network_requests != EXPECTED_NETWORK_REQUESTS:
        raise IAACRegistryError("successful capture request arithmetic changed")
    state = {
        "captured_at": _now(),
        "maximum_attempts_per_url": arguments.max_attempts,
        "maximum_network_requests": arguments.max_network_requests,
        "minimum_request_interval_seconds": arguments.min_request_interval,
        "network_requests": fetcher.network_requests,
        "retrievals": retrievals,
        "timeout_seconds": arguments.timeout,
    }
    (arguments.staging_dir / "capture-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return state


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.resume:
        state_path = arguments.staging_dir / "capture-state.json"
        if not state_path.is_file():
            raise IAACRegistryError("resume state does not exist")
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = _capture(arguments)
    if arguments.capture_only:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    if arguments.output.exists() or arguments.output.is_symlink():
        raise IAACRegistryError("output release already exists")
    try:
        definition = json.loads(arguments.definition.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IAACRegistryError("source definition is not valid JSON") from error
    if definition != source_definition():
        raise IAACRegistryError("source definition does not match code contract")
    retrievals = state.get("retrievals")
    if not isinstance(retrievals, dict):
        raise IAACRegistryError("capture state has no retrieval inventory")
    raw_bodies: dict[str, bytes] = {}
    for retrieval in retrievals.values():
        if not isinstance(retrieval, dict) or not isinstance(
            retrieval.get("filename"), str
        ):
            raise IAACRegistryError("capture retrieval record is invalid")
        filename = retrieval["filename"]
        artifact = arguments.staging_dir / filename
        if not artifact.is_file():
            raise IAACRegistryError(f"capture artifact is missing: {filename}")
        raw_bodies[filename] = artifact.read_bytes()
    write_release_bundle(arguments.output, state, raw_bodies)
    bundle = validate_release_bundle(arguments.output)
    assessment = bundle["assessment"]
    print(
        json.dumps(
            {
                "direct_rows": EXPECTED_DIRECT_RESULTS,
                "excluded_rows": EXPECTED_EXCLUDED_RESULTS,
                "frozen": is_frozen_release(arguments.output),
                "manifest_sha256": sha256_bytes(
                    (arguments.output / MANIFEST_FILENAME).read_bytes()
                ),
                "network_requests": state["network_requests"],
                "release_id": RELEASE_ID,
                "result_rows": EXPECTED_SEARCH_RESULTS,
                "unique_physical_site_count": assessment["coverage_assessment"][
                    "unique_physical_site_count"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
