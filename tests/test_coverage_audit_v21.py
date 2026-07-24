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
import datacenter_atlas.federated_release as federated_release_module
from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    build_coverage_audit,
    validate_coverage_audit,
    write_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v21.json"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v21"
BASE_DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v19.json"
BASE_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v19"
FEDERATION_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-20-public-open-v22.json"
)
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v22"
OPEN_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v47.json"
OPEN_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v47"

GENERATED_AT = "2026-07-20T10:22:46Z"
INSTRUCTION_FLOOR = "2026-07-20T10:22:46Z"
FEDERATION_GENERATED_AT = "2026-07-20T10:16:18Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v44"
NEW_RELEASE_ID = "epoch-official-open-seed-v47"

DEFINITION_SHA256 = "f26fa3dda1ed3447941154635d252d68b6355f826a17a6a4c4efaa887257cd02"
MANIFEST_SHA256 = "b40981593dab96613f7a35dd5e4e07aeb7c4f7e4727f41802bec6b8af0f88393"
MANIFEST_HASH_SHA256 = (
    "12e1ef832c97abcde50bbc5ebdc1db443e00d895af20e29404f1118d4a96f1a6"
)
BASE_DEFINITION_SHA256 = (
    "c420307ec4b2e2188d023b5421194f9fe10eabeae4d24a5e0d16e19b5f0e5f76"
)
BASE_MANIFEST_SHA256 = (
    "179c54831370c92cf5e58dec1e759190e896d554fb2d4929559c40c665be3db4"
)
BASE_MANIFEST_HASH_SHA256 = (
    "f622d4a2aaf808a08a434341f42521542842184ff7567d601e7e35f3fa157d9e"
)
BASE_AUDIT_SHA256 = "5bcf8b5e63236d34b6084b7f4ac5d305215ae110db1b4eefc2e0fa670d27a6b3"
BASE_GAP_SHA256 = "501411c9292f86b5701f851e729c5b689a02bd6575c3d9046dd7018eca314b3d"
FEDERATION_DEFINITION_SHA256 = (
    "87f8cf1b662431bcd3436ff89eaa8398b26d6cf42adfb1fdb9273d7fd06c37f6"
)
FEDERATION_INDEX_SHA256 = (
    "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c"
)
FEDERATION_MANIFEST_SHA256 = (
    "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94"
)
FEDERATION_MANIFEST_HASH_SHA256 = (
    "6355c538fed68b6f1c015f1922d446b86010148cadaebec0032b8c9fe7422d46"
)
OPEN_DEFINITION_SHA256 = (
    "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"
)
OPEN_MANIFEST_SHA256 = (
    "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1"
)

ARTIFACTS = {
    "REPORT.md": (4_151, "3235d4197d5bedad0c85b09188a8e3dfea3d714bb0158639cb3dc1e8c0c4383e"),
    "coverage-audit.json": (1_979_393, "4aa91850be0663e263d1366b0d7069bace670b09cba2b71a15a02e7fe8543bb3"),
    "coverage.csv": (273_167, "d1efd7c6c1e010367c3ea13ba46efa2bfe0e906f75a61443fd027a13daf3e360"),
    "gap-registry.json": (1_654_516, "05cccfc9ac765dfd8ab2128c9ad18f833a93bd023013fa60ef1ce9058bbcda32"),
    "manifest.json": (2_240, MANIFEST_SHA256),
    "manifest.sha256": (80, MANIFEST_HASH_SHA256),
}

REJECTED_MARKERS = {
    "sources/coverage-audit-2026-07-20-public-open-v20.json",
    "audits/2026-07-20-public-open-coverage-v20",
    "tests/test_coverage_audit_v20.py",
    "public-open-coverage-v20",
    "b2e8e98b261c09a4fe34be926a176a5725131b38d5ef3aaeb564fcc5c9b92696",
    "c1c18389c91e3f37cbc8311206881746c15d7e10b5fee24ec7ce945784dbfc05",
    "sources/federation-2026-07-20-public-open-v21.json",
    "federated_indexes/2026-07-20-public-open-v21",
    "623302bdec9d074f8ea9eec23f09516e2e51331884b8dedf3b4c49febc2d38d8",
    "24210f9484ac7f0143a76395782e739c49ce75a95059920a8dedd62c43b9b4cc",
    "epoch-official-open-seed-v46",
    "sources/open-seed-2026-07-20-v46.json",
    "releases/2026-07-20-open-seed-v46",
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293",
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
    "epoch-official-open-seed-v45",
    "sources/open-seed-2026-07-20-v45.json",
    "releases/2026-07-20-open-seed-v45",
    "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13",
    "275f5767c5f08208be7178126855ce5d3a77b217dbd53b2483450c46673b7a27",
    OLD_RELEASE_ID,
    "releases/2026-07-20-open-seed-v44",
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9",
}
FORBIDDEN_READ_FRAGMENTS = (
    "coverage-audit-2026-07-20-public-open-v20",
    "2026-07-20-public-open-coverage-v20",
    "federation-2026-07-20-public-open-v21",
    "federated_indexes/2026-07-20-public-open-v21",
    "open-seed-2026-07-20-v44",
    "2026-07-20-open-seed-v44",
    "open-seed-2026-07-20-v45",
    "2026-07-20-open-seed-v45",
    "open-seed-2026-07-20-v46",
    "2026-07-20-open-seed-v46",
)


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


class CoverageAuditV21Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v21 coverage attempted network or rejected input access"
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
            BASE_RELEASE / "manifest.json": BASE_MANIFEST_SHA256,
            BASE_RELEASE / "manifest.sha256": BASE_MANIFEST_HASH_SHA256,
            BASE_RELEASE / AUDIT_FILENAME: BASE_AUDIT_SHA256,
            BASE_RELEASE / GAP_REGISTRY_FILENAME: BASE_GAP_SHA256,
            FEDERATION_DEFINITION: FEDERATION_DEFINITION_SHA256,
            FEDERATION_RELEASE / "federated-index.json": FEDERATION_INDEX_SHA256,
            FEDERATION_RELEASE / "manifest.json": FEDERATION_MANIFEST_SHA256,
            FEDERATION_RELEASE / "manifest.sha256": FEDERATION_MANIFEST_HASH_SHA256,
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
        for marker in REJECTED_MARKERS:
            encoded = marker.encode("ascii")
            self.assertFalse(any(encoded in payload for payload in payloads), marker)

    def test_definition_is_exact_v19_to_v22_projection(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["audit_id"] = "public-open-coverage-v21"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v22",
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
                "release_path": "../releases/2026-07-20-open-seed-v47",
            }
        )
        for reference in expected["methodology_evidence_classification"][
            "permits"
        ]:
            self.assertEqual(reference["release_id"], OLD_RELEASE_ID)
            reference["release_id"] = NEW_RELEASE_ID

        current_raw = DEFINITION.read_bytes()
        current = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(current["public_benchmark"], base["public_benchmark"])
        for category in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
            self.assertEqual(
                current["methodology_evidence_classification"][category], []
            )

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        federation_generated = datetime.fromisoformat(
            FEDERATION_GENERATED_AT.replace("Z", "+00:00")
        )
        instruction = datetime.fromisoformat(
            INSTRUCTION_FLOOR.replace("Z", "+00:00")
        )
        self.assertGreater(generated, federation_generated)
        self.assertGreaterEqual(generated, instruction)

    def test_exact_counts_group_and_gap_deltas_preserve_policy(self) -> None:
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
                "non_review_source_scoped_entity_records": 9_896,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 16_026,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            totals["source_scoped_entity_records"]
            - base["totals"]["source_scoped_entity_records"],
            28,
        )
        self.assertEqual(
            totals["non_review_source_scoped_entity_records"]
            - base["totals"]["non_review_source_scoped_entity_records"],
            28,
        )
        self.assertEqual(
            totals["review_only_source_scoped_entity_records"],
            base["totals"]["review_only_source_scoped_entity_records"],
        )

        fields = totals["field_totals"]
        base_fields = base["totals"]["field_totals"]
        expected_field_values = {
            "capacity_observations": (1_240, 5),
            "coordinate_rows": (15_458, 0),
            "country_rows": (15_924, 28),
            "informative_lifecycle_status_rows": (486, 14),
            "non_review_rows": (9_896, 28),
            "operating_model_rows": (294, 11),
            "pipeline_rows": (396, 11),
            "source_scoped_rows": (16_026, 28),
            "under_construction_rows": (341, 10),
            "workload_observations": (118, 9),
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
        self.assertEqual((len(old_groups), len(new_groups)), (594, 613))
        self.assertEqual(len(new_groups.keys() - old_groups.keys()), 19)
        self.assertFalse(old_groups.keys() - new_groups.keys())
        changed_groups = {
            key
            for key in old_groups.keys() & new_groups.keys()
            if old_groups[key] != new_groups[key]
        }
        self.assertEqual(
            changed_groups,
            {
                (
                    OLD_RELEASE_ID,
                    "release",
                    "__ALL__",
                    "__ALL__",
                    None,
                    None,
                )
            },
        )
        for child in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                [group for group in current["groups"] if group["child_release"] == child],
                [group for group in base["groups"] if group["child_release"] == child],
            )

        old_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in base_gaps["gaps"]
        }
        new_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in current_gaps["gaps"]
        }
        added_gap_keys = new_gap_map.keys() - old_gap_map.keys()
        self.assertEqual((len(old_gap_map), len(new_gap_map)), (3_123, 3_193))
        self.assertEqual(len(added_gap_keys), 70)
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
                "annual_energy": 9,
                "capacity": 7,
                "coordinates": 9,
                "informative_lifecycle_status": 7,
                "lifecycle_status": 7,
                "operating_model": 8,
                "source_scoped_rows": 1,
                "status_as_of": 7,
                "status_evidence": 7,
                "workload": 8,
            },
        )
        self.assertEqual(
            current_gaps["summary"]["by_severity"],
            {"high": 214, "info": 32, "low": 1_741, "medium": 1_206},
        )
        self.assertEqual(current_gaps["summary"]["open_gaps"], 3_193)
        self.assertEqual(current["scope"], base["scope"])

        inputs = current["inputs"]
        self.assertEqual(
            inputs["federated_index"],
            {
                "format": "datacenter-atlas-federated-release-index-v1",
                "generated_at": FEDERATION_GENERATED_AT,
                "index": {"bytes": 22_981, "sha256": FEDERATION_INDEX_SHA256},
                "manifest": {
                    "bytes": 986,
                    "sha256": FEDERATION_MANIFEST_SHA256,
                },
            },
        )
        child_inputs = {
            child["release_id"]: child for child in inputs["children"]
        }
        self.assertEqual(
            child_inputs[NEW_RELEASE_ID]["manifest"]["sha256"],
            OPEN_MANIFEST_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
