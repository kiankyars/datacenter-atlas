#!/usr/bin/env python3
"""Build a new Loudoun metadata-and-aggregates assessment from official sources."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.loudoun_data_center_assessment import (
    ARTIFACT_URLS,
    ASSESSMENT_ID,
    LoudounDataCenterAssessmentError,
    MANIFEST_FILENAME,
    build_assessment_documents,
    sha256_bytes,
    write_assessment_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / ASSESSMENT_ID


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument(
        "--retrieved-at",
        help="Pinned RFC 3339 timestamp; defaults to current UTC before retrieval",
    )
    result.add_argument("--timeout", type=float, default=30.0)
    result.add_argument(
        "--freeze",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Make the completed bundle read-only (default: true)",
    )
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_query_boundary() -> None:
    for artifact_id, url in ARTIFACT_URLS.items():
        parsed = urlsplit(url)
        if not parsed.path.endswith("/query"):
            continue
        parameters = parse_qs(parsed.query, keep_blank_values=True)
        if artifact_id.endswith("_count"):
            if parameters != {
                "f": ["json"],
                "returnCountOnly": ["true"],
                "where": ["1=1"],
            }:
                raise LoudounDataCenterAssessmentError(
                    "builder count queries must remain count-only"
                )
            continue
        if (
            set(parameters)
            != {
                "f",
                "groupByFieldsForStatistics",
                "orderByFields",
                "outStatistics",
                "returnGeometry",
                "where",
            }
            or parameters.get("where") != ["1=1"]
            or parameters.get("returnGeometry") != ["false"]
            or "outFields" in parameters
            or "outSR" in parameters
        ):
            raise LoudounDataCenterAssessmentError(
                "builder grouped queries may not request feature attributes or geometry"
            )


def _fetch(url: str, timeout: float) -> tuple[dict[str, object], bytes]:
    request = Request(
        url,
        headers={
            "Accept": "application/json,application/pdf,text/html;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "identity",
            "User-Agent": "datacenter-atlas-loudoun-metadata-assessment/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            effective_url = response.geturl()
            content_type = response.headers.get(
                "Content-Type", "application/octet-stream"
            )
    except (HTTPError, URLError, TimeoutError) as error:
        raise LoudounDataCenterAssessmentError(
            f"failed to retrieve {url}"
        ) from error
    if status != 200 or not body:
        raise LoudounDataCenterAssessmentError(
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


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.timeout <= 0:
        raise LoudounDataCenterAssessmentError("timeout must be positive")
    if arguments.output.exists() or arguments.output.is_symlink():
        raise LoudounDataCenterAssessmentError("output bundle already exists")
    _validate_query_boundary()

    retrieved_at = arguments.retrieved_at or _now()
    retrievals: dict[str, dict[str, object]] = {}
    bodies: dict[str, bytes] = {}
    for artifact_id, url in ARTIFACT_URLS.items():
        retrieval, body = _fetch(url, arguments.timeout)
        retrievals[artifact_id] = retrieval
        bodies[artifact_id] = body

    assessment, schema, calibration = build_assessment_documents(
        retrievals, bodies, retrieved_at
    )
    output = write_assessment_bundle(
        arguments.output,
        assessment,
        schema,
        calibration,
        freeze=arguments.freeze,
    )
    manifest_digest = sha256_bytes((output / MANIFEST_FILENAME).read_bytes())
    print(
        json.dumps(
            {
                "assessment_id": assessment["assessment_id"],
                "assessment_status": assessment["atlas_decision"]["status"],
                "assessor_complete_data_centers": calibration["assessor_report"][
                    "official_total"
                ]["complete_data_centers"],
                "assessor_parcels": calibration["assessor_report"][
                    "official_total"
                ]["parcels"],
                "assessor_under_construction_data_centers": calibration[
                    "assessor_report"
                ]["official_total"]["under_construction_data_centers"],
                "existing_parcel_records": assessment["count_assessment"][
                    "existing_parcel_records"
                ],
                "feature_rows_retrieved": assessment["retrieval_batch"][
                    "feature_rows_retrieved"
                ],
                "frozen": arguments.freeze,
                "manifest_sha256": manifest_digest,
                "network_retrievals": assessment["retrieval_batch"][
                    "network_retrievals"
                ],
                "output": str(output),
                "pipeline_parcel_records": assessment["count_assessment"][
                    "pipeline_parcel_records"
                ],
                "unique_site_count": assessment["count_assessment"][
                    "unique_site_count"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
