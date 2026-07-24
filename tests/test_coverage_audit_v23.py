from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

import datacenter_atlas.coverage_audit as coverage_module
import datacenter_atlas.federated_release as federation_module
from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    build_coverage_audit,
    validate_coverage_audit,
    write_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v23.json"
RELEASE = ROOT / "audits/2026-07-20-public-open-coverage-v23"
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v22.json"
BASE_RELEASE = ROOT / "audits/2026-07-20-public-open-coverage-v22"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v24.json"
FEDERATION_RELEASE = ROOT / "federated_indexes/2026-07-20-public-open-v24"
OPEN_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v55.json"
OPEN_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"

GENERATED_AT = "2026-07-20T20:07:00Z"
FEDERATION_GENERATED_AT = "2026-07-20T20:06:00Z"
OPEN_RECORDED_AT = "2026-07-20T20:05:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v49"
NEW_RELEASE_ID = "epoch-official-open-seed-v55"

PINS = {
    DEFINITION: "3c35a36e02aefbcb169dee6a0dd8b7fe5480983767f0766fd3e7f0c942699436",
    BASE_DEFINITION: "0961741293f4ea682536498bb705a687a2b328037cc3de1577ae8803ed2d7d65",
    FEDERATION_DEFINITION: "98dc26e06948ff3334a8c3e21fc7b31616cf177362217459f04cd5a9d221e6a0",
    FEDERATION_RELEASE
    / "federated-index.json": "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d",
    FEDERATION_RELEASE
    / "manifest.json": "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1",
    OPEN_DEFINITION: "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba",
    OPEN_RELEASE
    / "manifest.json": "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
}
ARTIFACTS = {
    "REPORT.md": (
        4_152,
        "6facec0fa6e550f8f4f357a15d25aa2b3882afdd17cd34e6e0153ae83bf43cb9",
    ),
    "coverage-audit.json": (
        2_180_901,
        "a3541741bfd0aefcc00617a1f700f1420058170bfe6927cbf208769358f175a8",
    ),
    "coverage.csv": (
        301_677,
        "0733c7c5b48278960ec2e689b313e643c34b58d18870321152e1535561575af6",
    ),
    "gap-registry.json": (
        1_783_098,
        "e9b5e76edf289d78f01d3daf24cdcabd112ea15481bdf39e1bf72530508508a4",
    ),
    "manifest.json": (
        2_240,
        "7d282d3d725a3882475bf69f581a6b70f1505ccc135ecc7027b01cd7269e3e23",
    ),
    "manifest.sha256": (
        80,
        "ddd917c6ba5e96e6be419e34dc6207be7f2a2ecd3aeddf140d162d013957fbb8",
    ),
}
FORBIDDEN = (
    "epoch-official-open-seed-v49",
    "epoch-official-open-seed-v54",
    "federated_indexes/2026-07-20-public-open-v23",
    "releases/2026-07-20-open-seed-v49",
    "releases/2026-07-20-open-seed-v54",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class CoverageAuditV23Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v23 coverage attempted network or stale input access")
        coverage_original = coverage_module._regular_bytes
        federation_original = federation_module._regular_bytes

        def coverage_guarded(path: Path, label: str) -> bytes:
            if any(marker in path.as_posix() for marker in FORBIDDEN):
                raise failure
            return coverage_original(path, label)

        def federation_guarded(path: Path, label: str) -> bytes:
            if any(marker in path.as_posix() for marker in FORBIDDEN):
                raise failure
            return federation_original(path, label)

        stack.enter_context(
            patch.object(
                coverage_module, "_regular_bytes", side_effect=coverage_guarded
            )
        )
        stack.enter_context(
            patch.object(
                federation_module, "_regular_bytes", side_effect=federation_guarded
            )
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_double_offline_idempotence_and_modes(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, set(ARTIFACTS))
        frozen = {}
        for path in RELEASE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
            frozen[path.name] = path.read_bytes()

        with ExitStack() as stack:
            self._offline(stack)
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            validated = validate_coverage_audit(RELEASE, definition_path=DEFINITION)
            idempotent = write_coverage_audit(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first.audit, validated)
        self.assertEqual(first.audit, idempotent)
        self.assertEqual(dict(first.payloads), frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in RELEASE.iterdir()}, frozen
        )
        payload = b"".join([DEFINITION.read_bytes(), *frozen.values()])
        for marker in FORBIDDEN:
            self.assertNotIn(marker.encode(), payload)

    def test_exact_definition_transform_counts_groups_and_gaps(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base_definition)
        expected["audit_id"] = "public-open-coverage-v23"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": PINS[FEDERATION_RELEASE / "manifest.json"],
            "path": "../federated_indexes/2026-07-20-public-open-v24",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[OPEN_RELEASE / "manifest.json"],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v55",
            }
        )
        for references in expected["methodology_evidence_classification"].values():
            for reference in references:
                if reference["release_id"] == OLD_RELEASE_ID:
                    reference["release_id"] = NEW_RELEASE_ID
        raw = DEFINITION.read_bytes()
        current_definition = json.loads(raw)
        self.assertEqual(raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(FEDERATION_GENERATED_AT.replace("Z", "+00:00")),
        )
        self.assertGreater(
            datetime.fromisoformat(FEDERATION_GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(OPEN_RECORDED_AT.replace("Z", "+00:00")),
        )

        base = json.loads((BASE_RELEASE / AUDIT_FILENAME).read_text())
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text())
        fields = current["totals"]["field_totals"]
        base_fields = base["totals"]["field_totals"]
        expected_fields = {
            "capacity_observations": (1_268, 15),
            "coordinate_rows": (15_465, 7),
            "country_rows": (15_986, 34),
            "informative_lifecycle_status_rows": (519, 19),
            "non_review_rows": (9_958, 34),
            "operating_model_rows": (300, 4),
            "pipeline_rows": (422, 19),
            "source_scoped_rows": (16_088, 34),
            "under_construction_rows": (366, 18),
            "workload_observations": (122, 0),
        }
        for field, (value, delta) in expected_fields.items():
            self.assertEqual(fields[field], value, field)
            self.assertEqual(fields[field] - base_fields[field], delta, field)
        self.assertEqual(
            {
                key: current["totals"][key]
                for key in (
                    "advisory_resolution_candidate_records",
                    "confirmed_duplicate_relationships",
                    "non_review_source_scoped_entity_records",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                    "unique_physical_sites",
                )
            },
            {
                "advisory_resolution_candidate_records": 100_409,
                "confirmed_duplicate_relationships": None,
                "non_review_source_scoped_entity_records": 9_958,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 16_088,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual((len(base["groups"]), len(current["groups"])), (633, 675))
        for child_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                [
                    group
                    for group in current["groups"]
                    if group["child_release"] == child_id
                ],
                [
                    group
                    for group in base["groups"]
                    if group["child_release"] == child_id
                ],
            )
        gaps = json.loads((RELEASE / GAP_REGISTRY_FILENAME).read_text())
        self.assertEqual(
            gaps["summary"],
            {
                "by_field": {
                    "annual_energy": 456,
                    "capacity": 423,
                    "coordinates": 230,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 423,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 253,
                    "operating_model": 458,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 39,
                    "status_as_of": 253,
                    "status_evidence": 253,
                    "status_stale_366_plus_days": 178,
                    "unique_physical_sites": 1,
                    "workload": 453,
                },
                "by_severity": {
                    "high": 240,
                    "info": 39,
                    "low": 1_853,
                    "medium": 1_303,
                },
                "open_gaps": 3_435,
            },
        )
        self.assertEqual(current["scope"], base["scope"])
        self.assertIsNone(current["scope"]["unique_physical_sites"])

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.coverage_audit"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.coverage_audit"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_coverage_audit; "
                f"result=validate_coverage_audit(Path({str(RELEASE)!r}), "
                f"definition_path=Path({str(DEFINITION)!r})); "
                "assert result['totals']['source_scoped_entity_records']==16088; "
                "assert result['totals']['unique_physical_sites'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
