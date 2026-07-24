from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.coverage_audit as coverage_audit_module
import datacenter_atlas.federated_release as federated_release_module
from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    CoverageAuditError,
    build_coverage_audit,
    validate_coverage_audit,
    write_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v22.json"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v22"
BASE_DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v21.json"
BASE_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v21"
FEDERATION_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-20-public-open-v23.json"
)
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v23"
OPEN_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v49.json"
OPEN_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v49"

GENERATED_AT = "2026-07-20T16:50:00Z"
FEDERATION_GENERATED_AT = "2026-07-20T16:49:00Z"
OPEN_RECORDED_AT = "2026-07-20T16:45:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v47"
NEW_RELEASE_ID = "epoch-official-open-seed-v49"

DEFINITION_SHA256 = "0961741293f4ea682536498bb705a687a2b328037cc3de1577ae8803ed2d7d65"
BASE_DEFINITION_SHA256 = (
    "f26fa3dda1ed3447941154635d252d68b6355f826a17a6a4c4efaa887257cd02"
)
FEDERATION_DEFINITION_SHA256 = (
    "056d36d13712e613b51d28e59ea542b82fc720e093afb142af289ae30d1b0411"
)
FEDERATION_INDEX_SHA256 = (
    "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2"
)
FEDERATION_MANIFEST_SHA256 = (
    "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be"
)
FEDERATION_MANIFEST_HASH_SHA256 = (
    "832a7015714316ab682b243c895f36cd293806a764ea1fafda02c85aca40399e"
)
OPEN_DEFINITION_SHA256 = (
    "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c"
)
OPEN_MANIFEST_SHA256 = (
    "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
)

ARTIFACTS = {
    "REPORT.md": (
        4_152,
        "8e508d481398665c7e2f23aab6c21c4c0844d0fa132ca94ed86bbc5c2ef34a2c",
    ),
    "coverage-audit.json": (
        2_045_028,
        "118f07f8e125bcc30e6e5a426aca2e7edde1348c27f9bad153667302ca93d6e5",
    ),
    "coverage.csv": (
        282_842,
        "83150924980128f47d632ba5c904b7412820dedafc84f898d9f717d87028334a",
    ),
    "gap-registry.json": (
        1_707_917,
        "622904e230d45343d9fa82255cc4d41826d644d52ba19a7ff5099499bccea2ba",
    ),
    "manifest.json": (
        2_240,
        "e30e622393099b3bcca2c0965258664ff261133913d677cd06579c622df56307",
    ),
    "manifest.sha256": (
        80,
        "546d03c104e0f5141c9baf1977e2534703d09ae4064517603f21e169839ca3b1",
    ),
}

FORBIDDEN_CURRENT_MARKERS = {
    "sources/coverage-audit-2026-07-20-public-open-v20.json",
    "audits/2026-07-20-public-open-coverage-v20",
    "sources/federation-2026-07-20-public-open-v21.json",
    "federated_indexes/2026-07-20-public-open-v21",
    "epoch-official-open-seed-v48",
    "sources/open-seed-2026-07-20-v48.json",
    "releases/2026-07-20-open-seed-v48",
    OLD_RELEASE_ID,
    "sources/open-seed-2026-07-20-v47.json",
    "releases/2026-07-20-open-seed-v47",
}
FORBIDDEN_READ_FRAGMENTS = tuple(FORBIDDEN_CURRENT_MARKERS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def normalize(value: object) -> object:
    if isinstance(value, dict):
        return {key: normalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize(child) for child in value]
    if value == NEW_RELEASE_ID:
        return OLD_RELEASE_ID
    return value


def group_key(group: dict[str, object]) -> tuple[object, ...]:
    normalized = normalize(group)
    assert isinstance(normalized, dict)
    return tuple(
        normalized[field]
        for field in (
            "child_release",
            "scope_type",
            "source_family",
            "country",
            "country_iso_a2",
            "country_iso_a3",
        )
    )


def gap_key(gap: dict[str, object]) -> tuple[object, ...]:
    normalized = normalize(gap)
    assert isinstance(normalized, dict)
    return tuple(
        normalized[field]
        for field in (
            "scope_type",
            "child_release",
            "source_family",
            "country",
            "field",
        )
    )


def normalized_gap(gap: dict[str, object]) -> dict[str, object]:
    normalized = normalize(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


class CoverageAuditV22Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v22 coverage attempted network or superseded/rejected input access"
        )
        coverage_original = coverage_audit_module._regular_bytes
        federation_original = federated_release_module._regular_bytes

        def coverage_guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if any(marker in rendered for marker in FORBIDDEN_READ_FRAGMENTS):
                raise failure
            return coverage_original(path, label)

        def federation_guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if any(marker in rendered for marker in FORBIDDEN_READ_FRAGMENTS):
                raise failure
            return federation_original(path, label)

        stack.enter_context(
            patch.object(
                coverage_audit_module,
                "_regular_bytes",
                side_effect=coverage_guarded,
            )
        )
        stack.enter_context(
            patch.object(
                federated_release_module,
                "_regular_bytes",
                side_effect=federation_guarded,
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

    def test_exact_pins_double_offline_idempotence_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            FEDERATION_DEFINITION: FEDERATION_DEFINITION_SHA256,
            FEDERATION_RELEASE / "federated-index.json": FEDERATION_INDEX_SHA256,
            FEDERATION_RELEASE / "manifest.json": FEDERATION_MANIFEST_SHA256,
            FEDERATION_RELEASE / "manifest.sha256": (
                FEDERATION_MANIFEST_HASH_SHA256
            ),
            OPEN_DEFINITION: OPEN_DEFINITION_SHA256,
            OPEN_RELEASE / "manifest.json": OPEN_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, set(ARTIFACTS))
        for path in RELEASE.iterdir():
            expected_size, expected_hash = ARTIFACTS[path.name]
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(path.stat().st_size, expected_size, path.name)
            self.assertEqual(sha256(path), expected_hash, path.name)

        frozen = {path.name: path.read_bytes() for path in RELEASE.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            validated = validate_coverage_audit(
                RELEASE, definition_path=DEFINITION
            )
            idempotent = write_coverage_audit(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first.audit, validated)
        self.assertEqual(first.audit, idempotent)
        self.assertEqual(dict(first.payloads), frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in RELEASE.iterdir()}, frozen
        )

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in FORBIDDEN_CURRENT_MARKERS:
            encoded = marker.encode("ascii")
            self.assertFalse(any(encoded in payload for payload in payloads), marker)

    def test_definition_lineage_counts_groups_and_gaps_are_exact(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base_definition)
        expected["audit_id"] = "public-open-coverage-v22"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v23",
        }
        open_child = next(
            child
            for child in expected["children"]
            if child["release_id"] == OLD_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_MANIFEST_SHA256,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v49",
            }
        )
        for category in expected["methodology_evidence_classification"].values():
            for reference in category:
                if reference["release_id"] == OLD_RELEASE_ID:
                    reference["release_id"] = NEW_RELEASE_ID

        current_raw = DEFINITION.read_bytes()
        current_definition = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertEqual(
            current_definition["public_benchmark"],
            base_definition["public_benchmark"],
        )
        for category in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
            self.assertEqual(
                current_definition["methodology_evidence_classification"][category],
                [],
            )

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        federation_generated = datetime.fromisoformat(
            FEDERATION_GENERATED_AT.replace("Z", "+00:00")
        )
        open_recorded = datetime.fromisoformat(
            OPEN_RECORDED_AT.replace("Z", "+00:00")
        )
        self.assertGreater(generated, federation_generated)
        self.assertGreater(federation_generated, open_recorded)

        base = json.loads((BASE_RELEASE / AUDIT_FILENAME).read_text())
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text())
        base_gaps = json.loads((BASE_RELEASE / GAP_REGISTRY_FILENAME).read_text())
        current_gaps = json.loads((RELEASE / GAP_REGISTRY_FILENAME).read_text())

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
                "non_review_source_scoped_entity_records": 9_924,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 16_054,
                "unique_physical_sites": None,
            },
        )
        fields = current["totals"]["field_totals"]
        base_fields = base["totals"]["field_totals"]
        expected_field_values = {
            "capacity_observations": (1_253, 13),
            "coordinate_rows": (15_458, 0),
            "country_rows": (15_952, 28),
            "informative_lifecycle_status_rows": (500, 14),
            "non_review_rows": (9_924, 28),
            "operating_model_rows": (296, 2),
            "pipeline_rows": (403, 7),
            "source_scoped_rows": (16_054, 28),
            "under_construction_rows": (348, 7),
            "workload_observations": (122, 4),
        }
        for field, (expected_value, expected_delta) in expected_field_values.items():
            self.assertEqual(fields[field], expected_value, field)
            self.assertEqual(fields[field] - base_fields[field], expected_delta, field)

        old_groups = {
            group_key(group): normalize(group) for group in base["groups"]
        }
        new_groups = {
            group_key(group): normalize(group) for group in current["groups"]
        }
        self.assertEqual((len(old_groups), len(new_groups)), (613, 633))
        self.assertEqual(len(new_groups.keys() - old_groups.keys()), 20)
        self.assertFalse(old_groups.keys() - new_groups.keys())
        self.assertEqual(
            sum(
                old_groups[key] != new_groups[key]
                for key in old_groups.keys() & new_groups.keys()
            ),
            1,
        )
        for child in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                [
                    group
                    for group in current["groups"]
                    if group["child_release"] == child
                ],
                [
                    group
                    for group in base["groups"]
                    if group["child_release"] == child
                ],
            )

        old_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in base_gaps["gaps"]
        }
        new_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in current_gaps["gaps"]
        }
        added_gap_keys = new_gap_map.keys() - old_gap_map.keys()
        self.assertEqual((len(old_gap_map), len(new_gap_map)), (3_193, 3_293))
        self.assertEqual(len(added_gap_keys), 100)
        self.assertFalse(old_gap_map.keys() - new_gap_map.keys())
        self.assertFalse(
            {
                key
                for key in old_gap_map.keys() & new_gap_map.keys()
                if old_gap_map[key] != new_gap_map[key]
            }
        )
        self.assertEqual(
            Counter(key[-1] for key in added_gap_keys),
            {
                "annual_energy": 11,
                "capacity": 9,
                "coordinates": 11,
                "informative_lifecycle_status": 11,
                "lifecycle_status": 11,
                "operating_model": 11,
                "source_scoped_rows": 3,
                "status_as_of": 11,
                "status_evidence": 11,
                "workload": 11,
            },
        )
        self.assertEqual(
            current_gaps["summary"]["by_severity"],
            {"high": 225, "info": 35, "low": 1_783, "medium": 1_250},
        )
        self.assertEqual(current_gaps["summary"]["open_gaps"], 3_293)
        self.assertEqual(current["scope"], base["scope"])
        self.assertEqual(
            current["inputs"]["federated_index"],
            {
                "format": "datacenter-atlas-federated-release-index-v1",
                "generated_at": FEDERATION_GENERATED_AT,
                "index": {"bytes": 23_453, "sha256": FEDERATION_INDEX_SHA256},
                "manifest": {
                    "bytes": 986,
                    "sha256": FEDERATION_MANIFEST_SHA256,
                },
            },
        )

    def test_late_output_collision_is_refused_without_overwrite(self) -> None:
        original_validate = coverage_audit_module.validate_coverage_audit
        with tempfile.TemporaryDirectory(dir=RELEASE.parent) as temporary:
            output = Path(temporary)
            output.rmdir()
            sentinel = output / "sentinel.txt"

            def validate_then_race(*args: object, **kwargs: object) -> object:
                validated = original_validate(*args, **kwargs)
                output.mkdir()
                sentinel.write_text("late arrival\n", encoding="utf-8")
                return validated

            with patch.object(
                coverage_audit_module,
                "validate_coverage_audit",
                side_effect=validate_then_race,
            ):
                with self.assertRaisesRegex(
                    CoverageAuditError, "appeared during publication"
                ):
                    write_coverage_audit(DEFINITION, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "late arrival\n")


if __name__ == "__main__":
    unittest.main()
