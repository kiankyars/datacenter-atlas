from __future__ import annotations

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

import datacenter_atlas.federated_release as federated_release_module
from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    build_federated_release_index,
    validate_federated_release_index,
    write_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v22.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v22"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v20.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v20"
V47_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v47.json"
V47_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v47"

GENERATED_AT = "2026-07-20T10:16:18Z"
CORRECTION_FLOOR = "2026-07-20T10:16:18Z"
V47_RECORDED_AT = "2026-07-20T09:50:12Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v44"
NEW_RELEASE_ID = "epoch-official-open-seed-v47"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "87f8cf1b662431bcd3436ff89eaa8398b26d6cf42adfb1fdb9273d7fd06c37f6"
INDEX_SHA256 = "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c"
MANIFEST_SHA256 = "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94"
MANIFEST_HASH_SHA256 = (
    "6355c538fed68b6f1c015f1922d446b86010148cadaebec0032b8c9fe7422d46"
)
BASE_DEFINITION_SHA256 = (
    "5bd47924d1c19c30b77b1f76198a6924a461ff9d1a8e622a4216996335afe53d"
)
BASE_INDEX_SHA256 = "8dfcbb82ac3ad8964ab6fb220da19b3fbe6720c3a65b0c34da624ca6829d53f4"
BASE_MANIFEST_SHA256 = (
    "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78"
)
BASE_MANIFEST_HASH_SHA256 = (
    "5a416dedf7c24984b6389d5e12182b98797abd74891be1047d542f9cf4e7297b"
)
V47_DEFINITION_SHA256 = (
    "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"
)
V47_MANIFEST_SHA256 = (
    "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1"
)

REJECTED_MARKERS = {
    "sources/federation-2026-07-20-public-open-v21.json",
    "federated_indexes/2026-07-20-public-open-v21",
    "tests/test_federated_release_v21.py",
    "2026-07-20-public-open-v21",
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
    "epoch-official-open-seed-v44",
    "releases/2026-07-20-open-seed-v44",
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9",
}
FORBIDDEN_READ_FRAGMENTS = (
    "federation-2026-07-20-public-open-v21",
    "federated_indexes/2026-07-20-public-open-v21",
    "open-seed-2026-07-20-v44",
    "2026-07-20-open-seed-v44",
    "open-seed-2026-07-20-v45",
    "2026-07-20-open-seed-v45",
    "open-seed-2026-07-20-v46",
    "2026-07-20-open-seed-v46",
)

EXPECTED_COUNTS = {
    "capacity_estimates": 1_240,
    "construction_pipeline_records": 6_563,
    "evidence_records": 13_350,
    "non_review_construction_pipeline_records": 433,
    "non_review_source_scoped_entity_records": 9_896,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 176,
    "source_scoped_entity_records": 16_026,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 5,
    "construction_pipeline_records": 14,
    "evidence_records": 10,
    "non_review_construction_pipeline_records": 14,
    "non_review_source_scoped_entity_records": 28,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 10,
    "source_scoped_entity_records": 28,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 454,
    "construction_pipeline_records": 313,
    "entities_by_kind": {"campus": 326, "project": 275},
    "evidence_records": 337,
    "resolution_candidates": 4,
    "source_family_entries": 169,
    "source_scoped_entity_records": 601,
}
CHILDREN = {
    NEW_RELEASE_ID: V47_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV22Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v22 federation attempted network or rejected child access"
        )
        original = federated_release_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if any(marker in rendered for marker in FORBIDDEN_READ_FRAGMENTS):
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(
                federated_release_module,
                "_regular_bytes",
                side_effect=guarded,
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
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            BASE_INDEX_DIR / MANIFEST_HASH_FILENAME: BASE_MANIFEST_HASH_SHA256,
            V47_DEFINITION: V47_DEFINITION_SHA256,
            V47_RELEASE / MANIFEST_FILENAME: V47_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        for path in INDEX_DIR.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_federated_release_index(DEFINITION)
            second = build_federated_release_index(DEFINITION)
            validated = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            idempotent = write_federated_release_index(DEFINITION, INDEX_DIR)
        self.assertEqual(first, second)
        self.assertEqual(first.index, validated)
        self.assertEqual(first.index, idempotent)
        self.assertEqual(first.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(first.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME])
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in REJECTED_MARKERS:
            encoded = marker.encode("ascii")
            self.assertFalse(any(encoded in payload for payload in payloads), marker)

    def test_v22_is_exact_v20_to_v47_child_swap(self) -> None:
        base_raw = BASE_DEFINITION.read_bytes()
        base = json.loads(base_raw)
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V47_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v47/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v47",
            }
        )
        current_raw = DEFINITION.read_bytes()
        current = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current))
        self.assertEqual(current, expected)

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        correction = datetime.fromisoformat(
            CORRECTION_FLOOR.replace("Z", "+00:00")
        )
        child_recorded = datetime.fromisoformat(
            V47_RECORDED_AT.replace("Z", "+00:00")
        )
        self.assertGreater(generated, child_recorded)
        self.assertGreaterEqual(generated, correction)

        base_index = json.loads((BASE_INDEX_DIR / INDEX_FILENAME).read_text())
        current_index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        self.assertEqual(current_index["generated_at"], GENERATED_AT)
        self.assertEqual(current_index["counts"], EXPECTED_COUNTS)
        self.assertEqual(current_index["policy"], FEDERATION_POLICY)
        self.assertIsNone(current_index["policy"]["unique_physical_site_count"])
        self.assertFalse(current_index["policy"]["child_entities_merged"])
        self.assertFalse(current_index["policy"]["cross_source_deduplication"])

        by_id = {
            item["release_id"]: item for item in current_index["releases"]
        }
        base_by_id = {
            item["release_id"]: item for item in base_index["releases"]
        }
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])
        self.assertEqual(by_id[NEW_RELEASE_ID]["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V47_MANIFEST_SHA256
        )
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["recorded_at"], V47_RECORDED_AT
        )
        self.assertEqual(len(by_id[NEW_RELEASE_ID]["source_families"]), 169)
        self.assertFalse(by_id[NEW_RELEASE_ID]["scope"]["review_only"])

        delta = {
            key: current_index["counts"][key] - base_index["counts"][key]
            for key in EXPECTED_DELTA
        }
        self.assertEqual(delta, EXPECTED_DELTA)
        self.assertIsNone(current_index["counts"]["unique_physical_sites"])
        self.assertIsNone(base_index["counts"]["unique_physical_sites"])

    def test_review_rights_and_unchanged_child_boundaries_are_exact(self) -> None:
        index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        by_id = {item["release_id"]: item for item in index["releases"]}
        self.assertTrue(by_id["osm-fuzzy-review-v2"]["scope"]["review_only"])
        self.assertFalse(by_id["global-open-v3"]["scope"]["review_only"])
        self.assertFalse(by_id[NEW_RELEASE_ID]["scope"]["review_only"])
        self.assertEqual(
            index["counts"]["review_only_source_scoped_entity_records"],
            6_130,
        )
        self.assertEqual(
            index["counts"]["non_review_source_scoped_entity_records"],
            9_896,
        )
        self.assertEqual(
            index["counts"]["source_scoped_entity_records"],
            index["counts"]["review_only_source_scoped_entity_records"]
            + index["counts"]["non_review_source_scoped_entity_records"],
        )
        self.assertFalse(index["policy"]["licenses_or_attributions_combined"])
        self.assertEqual(
            {
                item["release_id"]: item["rights"]["license_expression"]
                for item in index["releases"]
            },
            {
                NEW_RELEASE_ID: "CC-BY-4.0 data plus source-linked factual claims from official company, government, utility, and exchange disclosures under source-specific terms",
                "global-open-v3": "ODbL-1.0 with CC0-1.0 and Public Domain inputs",
                "osm-fuzzy-review-v2": "ODbL-1.0 with a Public Domain boundary input",
            },
        )


if __name__ == "__main__":
    unittest.main()
