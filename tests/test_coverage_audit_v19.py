from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

import datacenter_atlas.coverage_audit as coverage_audit_module
from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    build_coverage_audit,
    validate_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v19.json"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v19"
BASE_DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v18.json"
BASE_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v18"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v20.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v20"
OPEN_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
OPEN_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"

GENERATED_AT = "2026-07-20T08:02:17Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v43"
NEW_RELEASE_ID = "epoch-official-open-seed-v44"

DEFINITION_SHA256 = "c420307ec4b2e2188d023b5421194f9fe10eabeae4d24a5e0d16e19b5f0e5f76"
MANIFEST_SHA256 = "179c54831370c92cf5e58dec1e759190e896d554fb2d4929559c40c665be3db4"
MANIFEST_HASH_SHA256 = (
    "f622d4a2aaf808a08a434341f42521542842184ff7567d601e7e35f3fa157d9e"
)
BASE_DEFINITION_SHA256 = (
    "648aea0d6cc773accbb978f68ea0e6d34643aeab36f16ab4dcb81c2f03fa5886"
)
BASE_MANIFEST_SHA256 = (
    "b7d2623e2144c24793c9d74e0aa26da103cd2ea0ef7585ea109665533d7ce1be"
)
FEDERATION_DEFINITION_SHA256 = (
    "5bd47924d1c19c30b77b1f76198a6924a461ff9d1a8e622a4216996335afe53d"
)
FEDERATION_INDEX_SHA256 = (
    "8dfcbb82ac3ad8964ab6fb220da19b3fbe6720c3a65b0c34da624ca6829d53f4"
)
FEDERATION_MANIFEST_SHA256 = (
    "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78"
)
OPEN_DEFINITION_SHA256 = (
    "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
)
OPEN_MANIFEST_SHA256 = (
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
)

ARTIFACTS = {
    "REPORT.md": (4_151, "3ffd4a4e167c1278d985531f275a8920dbb10535deb25ad8aab144b2fedcfd32"),
    "coverage-audit.json": (
        1_917_005,
        "5bcf8b5e63236d34b6084b7f4ac5d305215ae110db1b4eefc2e0fa670d27a6b3",
    ),
    "coverage.csv": (
        264_080,
        "0ed5e84ee43d8ca987992aed58f96009d4941eeb8f1b89fcb6a3e8c781449db6",
    ),
    "gap-registry.json": (
        1_617_447,
        "501411c9292f86b5701f851e729c5b689a02bd6575c3d9046dd7018eca314b3d",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _normalize(value: object) -> object:
    if isinstance(value, dict):
        return {key: _normalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_normalize(child) for child in value]
    if value == NEW_RELEASE_ID:
        return OLD_RELEASE_ID
    return value


def _group_key(group: dict) -> tuple:
    normalized = _normalize(group)
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


def _gap_key(gap: dict) -> tuple:
    normalized = _normalize(gap)
    assert isinstance(normalized, dict)
    return tuple(
        normalized[field]
        for field in ("scope_type", "child_release", "source_family", "country", "field")
    )


def _normalized_gap(gap: dict) -> dict:
    normalized = _normalize(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


class FrozenPublicCoverageV19Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v19 coverage attempted network or v43 input access")
        original = coverage_audit_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if "open-seed-v43" in path.as_posix():
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(coverage_audit_module, "_regular_bytes", side_effect=guarded)
        )
        for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_definition_delta_and_offline_reproduction(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            RELEASE / "manifest.json": MANIFEST_SHA256,
            RELEASE / "manifest.sha256": MANIFEST_HASH_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_RELEASE / "manifest.json": BASE_MANIFEST_SHA256,
            FEDERATION_DEFINITION: FEDERATION_DEFINITION_SHA256,
            FEDERATION_RELEASE / "federated-index.json": FEDERATION_INDEX_SHA256,
            FEDERATION_RELEASE / "manifest.json": FEDERATION_MANIFEST_SHA256,
            OPEN_DEFINITION: OPEN_DEFINITION_SHA256,
            OPEN_RELEASE / "manifest.json": OPEN_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(_sha256(path), expected, path)

        base_definition = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base_definition)
        expected["audit_id"] = "public-open-coverage-v19"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v20",
        }
        open_child = next(
            child for child in expected["children"] if child["release_id"] == OLD_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_MANIFEST_SHA256,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v44",
            }
        )
        for reference in expected["methodology_evidence_classification"]["permits"]:
            self.assertEqual(reference["release_id"], OLD_RELEASE_ID)
            reference["release_id"] = NEW_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), _canonical(expected))
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            current_definition["public_benchmark"], base_definition["public_benchmark"]
        )
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(
                current_definition["methodology_evidence_classification"][field], []
            )

        frozen = {path.name: path.read_bytes() for path in RELEASE.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            validated = validate_coverage_audit(RELEASE, definition_path=DEFINITION)
        self.assertEqual(first, second)
        self.assertEqual(first.audit, validated)
        self.assertEqual(set(first.payloads), set(frozen))
        for name, payload in first.payloads.items():
            self.assertEqual(payload, frozen[name])
        for name, (size, digest) in ARTIFACTS.items():
            self.assertEqual((RELEASE / name).stat().st_size, size)
            self.assertEqual(_sha256(RELEASE / name), digest)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        for path in RELEASE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_exact_v18_semantic_delta_and_open_gaps(self) -> None:
        base = json.loads((BASE_RELEASE / AUDIT_FILENAME).read_text())
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text())
        base_gaps = json.loads((BASE_RELEASE / GAP_REGISTRY_FILENAME).read_text())
        current_gaps = json.loads((RELEASE / GAP_REGISTRY_FILENAME).read_text())

        totals = current["totals"]
        self.assertEqual(
            {
                key: totals[key]
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
                "non_review_source_scoped_entity_records": 9_868,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_998,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            totals["source_scoped_entity_records"]
            - base["totals"]["source_scoped_entity_records"],
            29,
        )
        self.assertEqual(
            totals["non_review_source_scoped_entity_records"]
            - base["totals"]["non_review_source_scoped_entity_records"],
            29,
        )
        self.assertEqual(
            totals["review_only_source_scoped_entity_records"],
            base["totals"]["review_only_source_scoped_entity_records"],
        )
        fields = totals["field_totals"]
        base_fields = base["totals"]["field_totals"]
        self.assertEqual(fields["capacity_observations"], 1_235)
        self.assertEqual(fields["capacity_observations"] - base_fields["capacity_observations"], 8)
        self.assertEqual(fields["pipeline_rows"], 385)
        self.assertEqual(fields["pipeline_rows"] - base_fields["pipeline_rows"], 7)
        self.assertEqual(fields["under_construction_rows"], 331)
        self.assertEqual(
            fields["under_construction_rows"] - base_fields["under_construction_rows"], 7
        )
        self.assertEqual(fields["coordinate_rows"], 15_458)
        self.assertEqual(fields["coordinate_rows"] - base_fields["coordinate_rows"], 2)

        old_groups = {_group_key(group): _normalize(group) for group in base["groups"]}
        new_groups = {_group_key(group): _normalize(group) for group in current["groups"]}
        self.assertEqual((len(old_groups), len(new_groups)), (566, 594))
        self.assertEqual(len(new_groups.keys() - old_groups.keys()), 28)
        self.assertEqual(len(old_groups.keys() - new_groups.keys()), 0)
        self.assertEqual(
            len(
                [
                    key
                    for key in old_groups.keys() & new_groups.keys()
                    if old_groups[key] != new_groups[key]
                ]
            ),
            4,
        )

        old_gap_map = {
            _gap_key(gap): _normalized_gap(gap) for gap in base_gaps["gaps"]
        }
        new_gap_map = {
            _gap_key(gap): _normalized_gap(gap) for gap in current_gaps["gaps"]
        }
        added_gap_keys = new_gap_map.keys() - old_gap_map.keys()
        self.assertEqual((len(old_gap_map), len(new_gap_map)), (3_011, 3_123))
        self.assertEqual(len(added_gap_keys), 112)
        self.assertEqual(len(old_gap_map.keys() - new_gap_map.keys()), 0)
        self.assertEqual(
            len(
                [
                    key
                    for key in old_gap_map.keys() & new_gap_map.keys()
                    if old_gap_map[key] != new_gap_map[key]
                ]
            ),
            0,
        )
        self.assertEqual(
            Counter(key[-1] for key in added_gap_keys),
            {
                "annual_energy": 13,
                "capacity": 12,
                "coordinates": 13,
                "informative_lifecycle_status": 11,
                "lifecycle_status": 11,
                "operating_model": 13,
                "source_scoped_rows": 3,
                "status_as_of": 11,
                "status_evidence": 11,
                "status_stale_366_plus_days": 1,
                "workload": 13,
            },
        )
        self.assertEqual(current_gaps["summary"]["open_gaps"], 3_123)
        self.assertEqual(
            current_gaps["summary"]["by_severity"],
            {"high": 205, "info": 31, "low": 1_709, "medium": 1_178},
        )
        gap_fields = {gap["field"] for gap in current_gaps["gaps"]}
        self.assertIn("parity", gap_fields)
        self.assertIn("unique_physical_sites", gap_fields)
        self.assertIn("semianalysis_public_evidence_methodology", gap_fields)

        scope = current["scope"]
        self.assertFalse(scope["children_merged"])
        self.assertFalse(scope["cross_source_deduplication"])
        self.assertFalse(scope["review_candidates_promoted"])
        self.assertTrue(scope["review_only_rows_separately_counted"])
        self.assertIsNone(scope["unique_physical_sites"])
        self.assertEqual(scope["unit"], "source_scoped_release_row")


if __name__ == "__main__":
    unittest.main()
