#!/usr/bin/env python3
"""Fetch official inputs and build a frozen England Planning Data release."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.england_planning_data import (
    MANIFEST_FILENAME,
    RAW_ARTIFACTS,
    RELEASE_ID,
    EnglandPlanningDataError,
    is_frozen_release,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
USER_AGENT = "datacenter-atlas-england-planning-data/1.0"
RESPONSE_HEADERS = (
    "Content-Length",
    "Date",
    "ETag",
    "Last-Modified",
    "x-amz-version-id",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument(
        "--retrieved-at",
        help="Pinned RFC 3339 timestamp; defaults to current UTC before retrieval",
    )
    result.add_argument("--timeout", type=float, default=120.0)
    result.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Make the completed release read-only (default: true)",
    )
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_definition(path: Path) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EnglandPlanningDataError("source definition is not valid JSON") from error
    if value != source_definition():
        raise EnglandPlanningDataError("source definition does not match code contract")


def _fetch(url: str, timeout: float) -> tuple[dict[str, Any], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "text/csv,application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            retrieval = {
                "content_type": response.headers.get_content_type(),
                "effective_url": response.geturl(),
                "headers": {
                    name.lower(): response.headers[name]
                    for name in RESPONSE_HEADERS
                    if response.headers.get(name) is not None
                },
                "http_status": response.status,
                "url": url,
            }
    except (HTTPError, URLError, TimeoutError) as error:
        raise EnglandPlanningDataError(f"failed to retrieve {url}") from error
    if retrieval["http_status"] != 200 or not body:
        raise EnglandPlanningDataError(
            f"unexpected response for {url}: "
            f"status={retrieval['http_status']}, bytes={len(body)}"
        )
    return retrieval, body


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.timeout <= 0:
        raise EnglandPlanningDataError("timeout must be positive")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise EnglandPlanningDataError("output release already exists")
    _load_definition(arguments.definition)

    retrieved_at = arguments.retrieved_at or _now()
    retrievals: dict[str, dict[str, Any]] = {}
    raw_bodies: dict[str, bytes] = {}
    for artifact_id, specification in RAW_ARTIFACTS.items():
        retrieval, body = _fetch(str(specification["url"]), arguments.timeout)
        retrievals[artifact_id] = retrieval
        raw_bodies[artifact_id] = body

    output = write_release_bundle(
        arguments.output,
        retrievals,
        raw_bodies,
        retrieved_at,
        freeze=arguments.freeze,
    )
    bundle = validate_release_bundle(output)
    print(
        json.dumps(
            {
                "bulk_csv_bytes": bundle["inventory"]["source_file"]["bytes"],
                "bulk_csv_sha256": bundle["inventory"]["source_file"]["sha256"],
                "explicit_planning_observations": len(bundle["observations"]),
                "explicit_context_classification_counts": bundle["assessment"][
                    "selection_assessment"
                ]["explicit_context_classification_counts"],
                "frozen": is_frozen_release(output),
                "manifest_sha256": sha256_bytes(
                    (output / MANIFEST_FILENAME).read_bytes()
                ),
                "network_requests": len(RAW_ARTIFACTS),
                "optional_incremental_counts": bundle["assessment"][
                    "selection_assessment"
                ]["optional_incremental_counts"],
                "output": str(output),
                "release_id": RELEASE_ID,
                "represented_bulk_row_providers": bundle["assessment"][
                    "coverage_assessment"
                ]["represented_bulk_row_provider_entities"],
                "source_rows": bundle["inventory"]["source_rows"],
                "validation_mode": "offline_after_fetch",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
