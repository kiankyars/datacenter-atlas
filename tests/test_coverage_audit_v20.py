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
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v20.json"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v20"
BASE_DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v19.json"
BASE_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v19"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v21.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v21"
OPEN_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v46.json"
OPEN_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v46"

GENERATED_AT = "2026-07-20T09:55:12Z"
FEDERATION_GENERATED_AT = "2026-07-20T09:52:45Z"
OPEN_RECORDED_AT = "2026-07-20T09:41:21Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v44"
NEW_RELEASE_ID = "epoch-official-open-seed-v46"

DEFINITION_SHA256 = "b2e8e98b261c09a4fe34be926a176a5725131b38d5ef3aaeb564fcc5c9b92696"
MANIFEST_SHA256 = "c1c18389c91e3f37cbc8311206881746c15d7e10b5fee24ec7ce945784dbfc05"
MANIFEST_HASH_SHA256 = (
    "890906ec0fc21420ef2464c0c3f3eaee2b929d7f61fd2667904bb138097320b2"
)
BASE_DEFINITION_SHA256 = (
    "c420307ec4b2e2188d023b5421194f9fe10eabeae4d24a5e0d16e19b5f0e5f76"
)
BASE_MANIFEST_SHA256 = (
    "179c54831370c92cf5e58dec1e759190e896d554fb2d4929559c40c665be3db4"
)
FEDERATION_DEFINITION_SHA256 = (
    "623302bdec9d074f8ea9eec23f09516e2e51331884b8dedf3b4c49febc2d38d8"
)
FEDERATION_INDEX_SHA256 = (
    "d6694f7878ca193193d7a63affc391739bfe32b026d144e5166437db0678d905"
)
FEDERATION_MANIFEST_SHA256 = (
    "24210f9484ac7f0143a76395782e739c49ce75a95059920a8dedd62c43b9b4cc"
)
OPEN_DEFINITION_SHA256 = (
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293"
)
OPEN_MANIFEST_SHA256 = (
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
)

CODE_HASHES = {
    "datacenter_atlas/coverage_audit.py": "5b383a4b06f3a767dbb45c52c49e10da5c85f383d1739bc6af9abebff6617ad3",
    "scripts/build_coverage_audit.py": "e8d6558588cd37a50a162937dccb7f5dee9088f35aac2c053714bc7c211ca79d",
    "tests/test_coverage_audit_v19.py": "ccb696aca9522e03756be708f59a05c35aeed4cebb60475036211eb3364b1ade",
    "tests/test_federated_release_v21.py": "1a49def702a7107aeed0f4ffdf59499508541a282b4265f00f6db8ba19e5e973",
}

ARTIFACTS = {
    "REPORT.md": (4_151, "53fb76c7f567fb1ace98da7491fc220bff2e8a7df43dc06b64db9eb7ac731173"),
    "coverage-audit.json": (
        1_949_677,
        "7f6a5ac2109f08dfdd7a86b4c932c80d82e1d7eb5797f57b5cfd6884ecdd25d3",
    ),
    "coverage.csv": (
        269_078,
        "10f2dbced60bb62ce58e012857181bac204a9e8516f192dfc90572f91f51ab2f",
    ),
    "gap-registry.json": (
        1_655_977,
        "d9b9cd1d1212a27298d4f1814ef89e988128f2c9892a4e27a136dc55a8d64c9b",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def normalize(value: object) -> object:
    if isinstance(value, dict):
        return {key: normalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize(child) for child in value]
    if value == NEW_RELEASE_ID:
        return OLD_RELEASE_ID
    return value


def group_key(group: dict) -> tuple:
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


def gap_key(gap: dict) -> tuple:
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


def normalized_gap(gap: dict) -> dict:
    normalized = normalize(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


class FrozenPublicCoverageV20Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v20 coverage attempted network or stale input access")
        original = coverage_audit_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if (
                "releases/2026-07-20-open-seed-v44" in rendered
                or "releases/2026-07-20-open-seed-v45" in rendered
                or "federated_indexes/2026-07-20-public-open-v20" in rendered
            ):
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
            self.assertEqual(sha256(path), expected, path)
        for relative, expected in CODE_HASHES.items():
            path = ROOT / relative
            self.assertEqual(sha256(path), expected, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, path)

        base_definition = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base_definition)
        expected["audit_id"] = "public-open-coverage-v20"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v21",
        }
        open_child = next(
            child for child in expected["children"] if child["release_id"] == OLD_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_MANIFEST_SHA256,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v46",
            }
        )
        for reference in expected["methodology_evidence_classification"]["permits"]:
            self.assertEqual(reference["release_id"], OLD_RELEASE_ID)
            reference["release_id"] = NEW_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), canonical(expected))
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(current_definition["public_benchmark"], base_definition["public_benchmark"])
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(current_definition["methodology_evidence_classification"][field], [])
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(FEDERATION_GENERATED_AT.replace("Z", "+00:00")),
        )
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(OPEN_RECORDED_AT.replace("Z", "+00:00")),
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
            self.assertEqual(sha256(RELEASE / name), digest)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(len(list(RELEASE.iterdir())), 6)
        for path in RELEASE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_exact_v19_semantic_delta_and_open_gaps(self) -> None:
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
                "non_review_source_scoped_entity_records": 9_898,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 16_028,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            totals["source_scoped_entity_records"]
            - base["totals"]["source_scoped_entity_records"],
            30,
        )
        self.assertEqual(
            totals["non_review_source_scoped_entity_records"]
            - base["totals"]["non_review_source_scoped_entity_records"],
            30,
        )
        self.assertEqual(
            totals["review_only_source_scoped_entity_records"],
            base["totals"]["review_only_source_scoped_entity_records"],
        )
        fields = totals["field_totals"]
        base_fields = base["totals"]["field_totals"]
        expected_field_totals = {
            "capacity_observations": (1_237, 2),
            "construction_evidence_observations": (224, 2),
            "coordinate_rows": (15_458, 0),
            "informative_lifecycle_status_rows": (490, 18),
            "lifecycle_status_rows": (13_422, 18),
            "operating_model_rows": (291, 8),
            "pipeline_rows": (397, 12),
            "under_construction_rows": (343, 12),
        }
        for field, (total, delta) in expected_field_totals.items():
            self.assertEqual(fields[field], total, field)
            self.assertEqual(fields[field] - base_fields[field], delta, field)

        old_groups = {group_key(group): normalize(group) for group in base["groups"]}
        new_groups = {group_key(group): normalize(group) for group in current["groups"]}
        self.assertEqual((len(old_groups), len(new_groups)), (594, 604))
        self.assertEqual(len(new_groups.keys() - old_groups.keys()), 10)
        self.assertEqual(len(old_groups.keys() - new_groups.keys()), 0)
        self.assertEqual(
            sum(
                old_groups[key] != new_groups[key]
                for key in old_groups.keys() & new_groups.keys()
            ),
            1,
        )

        old_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in base_gaps["gaps"]
        }
        new_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in current_gaps["gaps"]
        }
        added_gap_keys = new_gap_map.keys() - old_gap_map.keys()
        self.assertEqual((len(old_gap_map), len(new_gap_map)), (3_123, 3_195))
        self.assertEqual(len(added_gap_keys), 72)
        self.assertEqual(len(old_gap_map.keys() - new_gap_map.keys()), 0)
        self.assertEqual(
            sum(
                old_gap_map[key] != new_gap_map[key]
                for key in old_gap_map.keys() & new_gap_map.keys()
            ),
            0,
        )
        self.assertEqual(
            Counter(key[-1] for key in added_gap_keys),
            {
                "annual_energy": 8,
                "capacity": 8,
                "coordinates": 8,
                "informative_lifecycle_status": 8,
                "lifecycle_status": 8,
                "operating_model": 8,
                "status_as_of": 8,
                "status_evidence": 8,
                "workload": 8,
            },
        )
        self.assertEqual(current_gaps["summary"]["open_gaps"], 3_195)
        self.assertEqual(
            current_gaps["summary"]["by_severity"],
            {"high": 213, "info": 31, "low": 1_741, "medium": 1_210},
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
