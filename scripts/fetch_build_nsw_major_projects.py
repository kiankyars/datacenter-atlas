#!/usr/bin/env python3
"""Fetch and build the bounded NSW Major Projects Data Storage source lane."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.nsw_major_projects import (
    EXPECTED_ACTIVE_BASE_ROWS,
    EXPECTED_ACTIVE_MODIFICATION_ROWS,
    EXPECTED_BASE_ROWS,
    EXPECTED_MODIFICATION_ROWS,
    EXPECTED_RAW_INVENTORY_SHA256,
    LIST_PAGE_SIZE,
    MANIFEST_FILENAME,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    NSWMajorProjectsError,
    NONTERMINAL_STAGES,
    LIST_ENDPOINT,
    list_page_count,
    list_page_url,
    parse_list_result_count,
    parse_list_rows,
    RELEASE_ID,
    sha256_bytes,
    source_definition,
    is_frozen_release,
    validate_release_bundle,
    write_release_bundle,
)


USER_AGENT = "datacenter-atlas-nsw-major-projects/1.0"
RESPONSE_HEADERS = ("Content-Length", "Date", "ETag", "Last-Modified")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--staging-dir", type=Path, required=True)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--capture-list-only", action="store_true")
    result.add_argument("--capture-details-only", action="store_true")
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
        initial_requests: int = 0,
    ) -> None:
        if timeout <= 0 or min_interval < 1:
            raise NSWMajorProjectsError(
                "timeout must be positive and interval at least 1s"
            )
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise NSWMajorProjectsError("network request cap must be between 1 and 50")
        if max_attempts < 1:
            raise NSWMajorProjectsError("max attempts must be positive")
        self.timeout = timeout
        self.min_interval = min_interval
        self.request_cap = request_cap
        self.max_attempts = max_attempts
        if not 0 <= initial_requests <= request_cap:
            raise NSWMajorProjectsError("initial request count exceeds cap")
        self.network_requests = initial_requests
        self._last_request_started: float | None = None

    def _pace(self) -> None:
        if self._last_request_started is None:
            return
        remaining = self.min_interval - (time.monotonic() - self._last_request_started)
        if remaining > 0:
            time.sleep(remaining)

    def fetch(self, url: str) -> tuple[dict[str, Any], bytes]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            if self.network_requests >= self.request_cap:
                raise NSWMajorProjectsError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 8))
            self._pace()
            self._last_request_started = time.monotonic()
            self.network_requests += 1
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    metadata = {
                        "attempt": attempt,
                        "bytes": len(body),
                        "content_type": response.headers.get_content_type(),
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
                if metadata["http_status"] != 200 or not body:
                    raise NSWMajorProjectsError(
                        f"unexpected response status/body for {url}"
                    )
                if metadata["content_type"] not in {
                    "text/html",
                    "application/xhtml+xml",
                }:
                    raise NSWMajorProjectsError(f"unexpected content type for {url}")
                return metadata, body
            except (HTTPError, URLError, TimeoutError, NSWMajorProjectsError) as error:
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
        raise NSWMajorProjectsError(f"failed to retrieve {url}") from last_error


def _write_capture(staging: Path, name: str, body: bytes) -> Path:
    raw = staging / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    destination = raw / name
    if destination.exists():
        raise NSWMajorProjectsError(f"capture already exists: {destination}")
    destination.write_bytes(body)
    return destination


def _load_definition(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NSWMajorProjectsError("source definition is not valid JSON") from error
    if value != source_definition():
        raise NSWMajorProjectsError("source definition does not match code contract")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_list_only and arguments.capture_details_only:
        raise NSWMajorProjectsError("capture modes are mutually exclusive")
    if (
        not arguments.capture_list_only
        and not arguments.capture_details_only
        and (arguments.output.exists() or arguments.output.is_symlink())
    ):
        raise NSWMajorProjectsError("output release already exists")
    if arguments.resume:
        state_path = arguments.staging_dir / "capture-state.json"
        if not state_path.is_file():
            raise NSWMajorProjectsError("resume state does not exist")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NSWMajorProjectsError("resume state is invalid") from error
        retrievals = state.get("retrievals")
        if not isinstance(retrievals, dict):
            raise NSWMajorProjectsError("resume retrieval inventory is invalid")
        initial_requests = state.get("network_requests")
        if not isinstance(initial_requests, int):
            raise NSWMajorProjectsError("resume request count is invalid")
        for retrieval in retrievals.values():
            if not isinstance(retrieval, dict):
                raise NSWMajorProjectsError("resume retrieval record is invalid")
            filename = retrieval.get("filename")
            digest = retrieval.get("sha256")
            if not isinstance(filename, str) or not isinstance(digest, str):
                raise NSWMajorProjectsError("resume retrieval lineage is invalid")
            artifact = arguments.staging_dir / filename
            if (
                not artifact.is_file()
                or sha256_bytes(artifact.read_bytes()) != digest
            ):
                raise NSWMajorProjectsError(
                    f"resume artifact failed hash check: {filename}"
                )
    else:
        if arguments.staging_dir.exists():
            raise NSWMajorProjectsError("staging directory already exists")
        arguments.staging_dir.mkdir(parents=True)
        retrievals = {}
        initial_requests = 0

    fetcher = BoundedFetcher(
        timeout=arguments.timeout,
        min_interval=arguments.min_request_interval,
        request_cap=arguments.max_network_requests,
        max_attempts=arguments.max_attempts,
        initial_requests=initial_requests,
    )

    if not arguments.resume:
        first_metadata, first_body = fetcher.fetch(list_page_url(0))
        first_path = _write_capture(
            arguments.staging_dir, "list-page-00000.html", first_body
        )
        retrievals["list_page_00000"] = first_metadata | {
            "filename": str(first_path.relative_to(arguments.staging_dir))
        }
        result_count = parse_list_result_count(first_body)
        pages = list_page_count(result_count)
        for page in range(1, pages):
            metadata, body = fetcher.fetch(list_page_url(page))
            path = _write_capture(
                arguments.staging_dir, f"list-page-{page:05d}.html", body
            )
            retrievals[f"list_page_{page:05d}"] = metadata | {
                "filename": str(path.relative_to(arguments.staging_dir))
            }
    else:
        result_count = state.get("result_count")
        pages = state.get("list_pages")
        if not isinstance(result_count, int) or not isinstance(pages, int):
            raise NSWMajorProjectsError("resume list inventory is invalid")

    list_rows: list[dict[str, Any]] = []
    for page in range(pages):
        artifact = arguments.staging_dir / "raw" / f"list-page-{page:05d}.html"
        list_rows.extend(parse_list_rows(artifact.read_bytes(), page=page))
    if len(list_rows) != result_count:
        raise NSWMajorProjectsError(
            "parsed list rows do not match displayed result count"
        )

    state = {
        "captured_at": _now(),
        "list_page_size": LIST_PAGE_SIZE,
        "list_pages": pages,
        "network_requests": fetcher.network_requests,
        "result_count": result_count,
        "retrievals": retrievals,
    }
    (arguments.staging_dir / "capture-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if arguments.capture_list_only:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0

    active_rows = [
        row for row in list_rows if row["workflow_stage"] in NONTERMINAL_STAGES
    ]
    if len({row["detail_path"] for row in active_rows}) != len(active_rows):
        raise NSWMajorProjectsError("nonterminal detail paths are not unique")
    for row in active_rows:
        artifact_id = f"detail_{row['case_id'].lower().replace('-', '_')}"
        if artifact_id in retrievals:
            continue
        url = urljoin(LIST_ENDPOINT, row["detail_path"])
        metadata, body = fetcher.fetch(url)
        filename = f"detail-{row['case_id'].lower()}.html"
        path = _write_capture(arguments.staging_dir, filename, body)
        retrievals[artifact_id] = metadata | {
            "case_id": row["case_id"],
            "filename": str(path.relative_to(arguments.staging_dir)),
        }

    state.update(
        {
            "active_detail_pages": len(active_rows),
            "base_rows": sum(not row["is_modification"] for row in list_rows),
            "modification_rows": sum(row["is_modification"] for row in list_rows),
            "network_requests": fetcher.network_requests,
            "retrievals": retrievals,
        }
    )
    (arguments.staging_dir / "capture-state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if arguments.capture_details_only:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0

    _load_definition(arguments.definition)
    raw_bodies = {
        retrieval["filename"]: (
            arguments.staging_dir / retrieval["filename"]
        ).read_bytes()
        for retrieval in retrievals.values()
    }
    output = write_release_bundle(arguments.output, state, raw_bodies, freeze=True)
    bundle = validate_release_bundle(output)
    print(
        json.dumps(
            {
                "active_base_rows": EXPECTED_ACTIVE_BASE_ROWS,
                "active_detail_rows": len(bundle["active_observations"]),
                "active_modification_rows": EXPECTED_ACTIVE_MODIFICATION_ROWS,
                "base_rows": EXPECTED_BASE_ROWS,
                "frozen": is_frozen_release(output),
                "manifest_sha256": sha256_bytes(
                    (output / MANIFEST_FILENAME).read_bytes()
                ),
                "modification_rows": EXPECTED_MODIFICATION_ROWS,
                "network_requests_snapshot": state["network_requests"],
                "network_requests_this_invocation": (
                    fetcher.network_requests - initial_requests
                ),
                "output": str(output),
                "raw_inventory_sha256": EXPECTED_RAW_INVENTORY_SHA256,
                "release_id": RELEASE_ID,
                "stage_counts": bundle["assessment"]["selection_assessment"][
                    "stage_counts"
                ],
                "total_list_rows": len(bundle["list_observations"]),
                "validation_mode": "offline_after_bounded_fetch",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
