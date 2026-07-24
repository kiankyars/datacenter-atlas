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
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v18.json"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v18"
BASE_DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v17.json"
BASE_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v17"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v19.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v19"
OPEN_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v43.json"
OPEN_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v43"

GENERATED_AT = "2026-07-20T06:58:03Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v42"
NEW_RELEASE_ID = "epoch-official-open-seed-v43"

DEFINITION_SHA256 = "648aea0d6cc773accbb978f68ea0e6d34643aeab36f16ab4dcb81c2f03fa5886"
MANIFEST_SHA256 = "b7d2623e2144c24793c9d74e0aa26da103cd2ea0ef7585ea109665533d7ce1be"
MANIFEST_HASH_SHA256 = (
    "cca3f4d1bd1c194cf2d736be2de7f36d6ee368e187257d972890b46d7b90180d"
)
BASE_DEFINITION_SHA256 = (
    "964926e8432b4bf83233201c07cad0c40dc2fc34d9d4b1f89cd871f51c461f3d"
)
BASE_MANIFEST_SHA256 = (
    "37807873e8dc0009d31b1a1eb8d4d6cc4dd2dceb88a1ab52076c166e37f04755"
)
FEDERATION_DEFINITION_SHA256 = (
    "f1b5c6e55324e6db97110bc73846df536ba05b05bc9ac28c2d8ed5410940ec06"
)
FEDERATION_INDEX_SHA256 = (
    "29bada0af2140d0c0645abaf8ed192e1f832cbb39692af3a475b0a0a74780327"
)
FEDERATION_MANIFEST_SHA256 = (
    "55079d65fbb7cf8ce79dd753e7dcf3e6067f00a8c83de23e29de501b7c6063e0"
)
OPEN_DEFINITION_SHA256 = (
    "3b789babfbaaad54166bb7b94305c24258644bec239dd76dcf19186fdd56d6fa"
)
OPEN_MANIFEST_SHA256 = (
    "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537"
)

ARTIFACTS = {
    "REPORT.md": (4_150, "418e0b6525568563181cfeaae188e4a0fa9c2ee10368d3430afa11d551650e03"),
    "coverage-audit.json": (
        1_826_947,
        "4f3022eeb5159975b2868ab9ba45d40308b1743c052306c817819b324000c03a",
    ),
    "coverage.csv": (
        251_830,
        "9fb2320a8d24d20f0fc7bd181f90fcc86bd9365584e7a93fc4d230f70465c763",
    ),
    "gap-registry.json": (
        1_557_419,
        "c248f728eaabf64b190684704b759f618fde10eb973abcdcf9d24952be62a0a1",
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


class FrozenPublicCoverageV18Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v18 coverage attempted network or v42 input access")
        original = coverage_audit_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if "open-seed-v42" in path.as_posix():
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
        expected["audit_id"] = "public-open-coverage-v18"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v19",
        }
        open_child = next(
            child for child in expected["children"] if child["release_id"] == OLD_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_MANIFEST_SHA256,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v43",
            }
        )
        for reference in expected["methodology_evidence_classification"]["permits"]:
            self.assertEqual(reference["release_id"], OLD_RELEASE_ID)
            reference["release_id"] = NEW_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), _canonical(expected))
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(current_definition["public_benchmark"], base_definition["public_benchmark"])
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(current_definition["methodology_evidence_classification"][field], [])

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
        self.assertEqual(_sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_sha256(RELEASE / "manifest.sha256"), MANIFEST_HASH_SHA256)
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

    def test_exact_v17_semantic_delta_and_open_gaps(self) -> None:
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
                "non_review_source_scoped_entity_records": 9_839,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_969,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            totals["source_scoped_entity_records"] - base["totals"]["source_scoped_entity_records"],
            42,
        )
        self.assertEqual(
            totals["non_review_source_scoped_entity_records"]
            - base["totals"]["non_review_source_scoped_entity_records"],
            42,
        )
        self.assertEqual(
            totals["review_only_source_scoped_entity_records"],
            base["totals"]["review_only_source_scoped_entity_records"],
        )
        fields = totals["field_totals"]
        self.assertEqual(fields["capacity_observations"], 1_227)
        self.assertEqual(fields["capacity_observations"] - base["totals"]["field_totals"]["capacity_observations"], 14)
        self.assertEqual(fields["pipeline_rows"], 378)
        self.assertEqual(fields["under_construction_rows"], 324)
        self.assertEqual(fields["coordinate_rows"], 15_456)

        old_groups = {_group_key(group): _normalize(group) for group in base["groups"]}
        new_groups = {_group_key(group): _normalize(group) for group in current["groups"]}
        self.assertEqual((len(old_groups), len(new_groups)), (526, 566))
        self.assertEqual(len(new_groups.keys() - old_groups.keys()), 40)
        self.assertEqual(len(old_groups.keys() - new_groups.keys()), 0)
        self.assertEqual(
            len([key for key in old_groups.keys() & new_groups.keys() if old_groups[key] != new_groups[key]]),
            6,
        )

        old_gap_map = {_gap_key(gap): _normalized_gap(gap) for gap in base_gaps["gaps"]}
        new_gap_map = {_gap_key(gap): _normalized_gap(gap) for gap in current_gaps["gaps"]}
        added_gap_keys = new_gap_map.keys() - old_gap_map.keys()
        self.assertEqual((len(old_gap_map), len(new_gap_map)), (2_845, 3_011))
        self.assertEqual(len(added_gap_keys), 166)
        self.assertEqual(len(old_gap_map.keys() - new_gap_map.keys()), 0)
        self.assertEqual(
            len([key for key in old_gap_map.keys() & new_gap_map.keys() if old_gap_map[key] != new_gap_map[key]]),
            14,
        )
        self.assertEqual(
            Counter(key[-1] for key in added_gap_keys),
            {
                "annual_energy": 19,
                "capacity": 17,
                "coordinates": 18,
                "informative_lifecycle_status": 17,
                "lifecycle_status": 17,
                "operating_model": 18,
                "source_scoped_rows": 6,
                "status_as_of": 17,
                "status_evidence": 17,
                "status_stale_366_plus_days": 2,
                "workload": 18,
            },
        )
        self.assertEqual(current_gaps["summary"]["open_gaps"], 3_011)
        self.assertEqual(
            current_gaps["summary"]["by_severity"],
            {"high": 192, "info": 28, "low": 1_658, "medium": 1_133},
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
