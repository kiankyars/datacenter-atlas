#!/usr/bin/env python3
"""Validate the PeeringDB rights assessment and optional Scrutica conflict."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.peeringdb_assessment import (
    audit_scrutica_peeringdb_rights,
    validate_assessment_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "peeringdb-2026-07-18-v1"
)
DEFAULT_SCRUTICA_RELEASE = PROJECT_ROOT / "releases" / "scrutica-2026-07-18"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--assessment", type=Path, default=DEFAULT_ASSESSMENT)
    result.add_argument(
        "--scrutica-release", type=Path, default=DEFAULT_SCRUTICA_RELEASE
    )
    result.add_argument(
        "--skip-scrutica-audit",
        action="store_true",
        help="validate only the metadata bundle",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    assessment = validate_assessment_bundle(arguments.assessment)
    result: dict[str, object] = {
        "assessment_id": assessment["assessment_id"],
        "assessment_status": assessment["atlas_decision"]["status"],
        "network_requests": 0,
    }
    if not arguments.skip_scrutica_audit:
        audit = audit_scrutica_peeringdb_rights(arguments.scrutica_release)
        expected = assessment["scrutica_upstream_rights_conflict"]
        compared_fields = (
            "release_manifest_sha256",
            "attribution_file_sha256",
            "peeringdb_evidence_rows",
            "peeringdb_entity_rows",
            "cc_by_sa_labeled_peeringdb_evidence_rows",
            "permission_evidence_recorded_rows",
            "dependent_rows",
            "conflict_detected",
            "publication_eligible",
            "required_action",
            "relabel_alone_is_sufficient",
        )
        mismatches = {
            field: {"expected": expected.get(field), "actual": audit.get(field)}
            for field in compared_fields
            if expected.get(field) != audit.get(field)
        }
        if mismatches:
            raise SystemExit(
                "Scrutica rights audit differs from the pinned assessment: "
                + json.dumps(mismatches, sort_keys=True)
            )
        result["scrutica_upstream_rights_conflict"] = audit
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
