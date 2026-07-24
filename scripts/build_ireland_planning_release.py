#!/usr/bin/env python3
"""Retrieve and freeze the open Ireland planning-observation release."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.ireland_planning import (
    KPMG_REPORT_URL,
    MANIFEST_FILENAME,
    RAW_ARTIFACTS,
    RELEASE_ID,
    IrelandPlanningError,
    sha256_bytes,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
USER_AGENT = "datacenter-atlas-ireland-planning-release/1.0"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument(
        "--retrieved-at",
        help="Pinned RFC 3339 timestamp; defaults to current UTC before retrieval",
    )
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Make the completed bundle read-only (default: true)",
    )
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _fetch(url: str, timeout: float) -> tuple[dict[str, object], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json,text/html,application/pdf;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            effective_url = response.geturl()
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as error:
        raise IrelandPlanningError(f"failed to retrieve {url}") from error
    if status != 200 or not body:
        raise IrelandPlanningError(
            f"unexpected response for {url}: status={status}, bytes={len(body)}"
        )
    return (
        {
            "content_type": content_type,
            "effective_url": effective_url,
            "http_status": status,
            "url": url,
        },
        body,
    )


def _calibration_record(
    retrieval: dict[str, object], body: bytes
) -> dict[str, object]:
    effective_url = retrieval.get("effective_url")
    if (
        retrieval.get("content_type") != "application/pdf"
        or retrieval.get("http_status") != 200
        or not isinstance(effective_url, str)
        or urlsplit(effective_url).scheme != "https"
        or urlsplit(effective_url).hostname != "enterprise.gov.ie"
    ):
        raise IrelandPlanningError("restricted calibration retrieval is invalid")
    return {
        "aggregate_only": True,
        "as_of_year": 2025,
        "bytes": len(body),
        "content_type": retrieval["content_type"],
        "http_status": retrieval["http_status"],
        "installed_it_capacity_mw": 1543,
        "operational_grid_connected_buildings": 72,
        "operational_sites": 36,
        "planning_projects_excluded": True,
        "raw_artifact_retained": False,
        "rights_notice": "KPMG All Rights Reserved",
        "row_labeling_or_capacity_assignment_permitted": False,
        "sha256": sha256_bytes(body),
        "url": KPMG_REPORT_URL,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.timeout <= 0:
        raise IrelandPlanningError("timeout must be positive")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise IrelandPlanningError("output release already exists")

    retrieved_at = arguments.retrieved_at or _now()
    retrievals: dict[str, dict[str, object]] = {}
    raw_bodies: dict[str, bytes] = {}
    for artifact_id, specification in RAW_ARTIFACTS.items():
        retrieval, body = _fetch(specification["url"], arguments.timeout)
        retrievals[artifact_id] = retrieval
        raw_bodies[artifact_id] = body

    calibration_retrieval, calibration_body = _fetch(
        KPMG_REPORT_URL, arguments.timeout
    )
    calibration = _calibration_record(
        calibration_retrieval, calibration_body
    )
    del calibration_body

    output = write_release_bundle(
        arguments.output,
        retrievals,
        raw_bodies,
        calibration,
        retrieved_at,
        freeze=arguments.freeze,
    )
    assessment = json.loads(
        (output / "assessment.json").read_text(encoding="utf-8")
    )
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "baseline_exact_phrase_count": summary[
                    "baseline_exact_phrase_count"
                ],
                "extension_count": summary["extension_count"],
                "frozen": arguments.freeze,
                "manifest_sha256": sha256_bytes(
                    (output / MANIFEST_FILENAME).read_bytes()
                ),
                "matched_planning_application_observations": summary[
                    "matched_observation_count"
                ],
                "network_retrievals": assessment["retrieval_batch"][
                    "network_retrievals"
                ],
                "open_raw_artifacts_retained": assessment[
                    "retrieval_batch"
                ]["open_raw_artifacts_retained"],
                "output": str(output),
                "precision_review_rows_retrieved": assessment[
                    "retrieval_batch"
                ]["precision_review_rows_retrieved"],
                "release_id": RELEASE_ID,
                "unique_site_count": summary["unique_site_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
