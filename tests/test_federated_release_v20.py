from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
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
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v20.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v20"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v19.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v19"
V44_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
V44_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"

GENERATED_AT = "2026-07-20T07:58:41Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v43"
NEW_RELEASE_ID = "epoch-official-open-seed-v44"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "5bd47924d1c19c30b77b1f76198a6924a461ff9d1a8e622a4216996335afe53d"
INDEX_SHA256 = "8dfcbb82ac3ad8964ab6fb220da19b3fbe6720c3a65b0c34da624ca6829d53f4"
MANIFEST_SHA256 = "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78"
MANIFEST_HASH_SHA256 = (
    "5a416dedf7c24984b6389d5e12182b98797abd74891be1047d542f9cf4e7297b"
)
BASE_DEFINITION_SHA256 = (
    "f1b5c6e55324e6db97110bc73846df536ba05b05bc9ac28c2d8ed5410940ec06"
)
BASE_INDEX_SHA256 = "29bada0af2140d0c0645abaf8ed192e1f832cbb39692af3a475b0a0a74780327"
BASE_MANIFEST_SHA256 = (
    "55079d65fbb7cf8ce79dd753e7dcf3e6067f00a8c83de23e29de501b7c6063e0"
)
V44_DEFINITION_SHA256 = (
    "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
)
V44_MANIFEST_SHA256 = (
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
)

EXPECTED_COUNTS = {
    "capacity_estimates": 1_235,
    "construction_pipeline_records": 6_549,
    "evidence_records": 13_340,
    "non_review_construction_pipeline_records": 419,
    "non_review_source_scoped_entity_records": 9_868,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 166,
    "source_scoped_entity_records": 15_998,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 8,
    "construction_pipeline_records": 15,
    "evidence_records": 19,
    "non_review_construction_pipeline_records": 15,
    "non_review_source_scoped_entity_records": 29,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 15,
    "source_scoped_entity_records": 29,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 449,
    "construction_pipeline_records": 299,
    "entities_by_kind": {"campus": 312, "project": 261},
    "evidence_records": 327,
    "resolution_candidates": 4,
    "source_family_entries": 159,
    "source_scoped_entity_records": 573,
}
CHILDREN = {
    NEW_RELEASE_ID: V44_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FederatedReleaseV20Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v20 federation attempted network or v43 access")
        original = federated_release_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if "open-seed-v43" in path.as_posix():
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(federated_release_module, "_regular_bytes", side_effect=guarded)
        )
        for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname"):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_offline_reproduction_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            V44_DEFINITION: V44_DEFINITION_SHA256,
            V44_RELEASE / MANIFEST_FILENAME: V44_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(_sha256(path), expected, path)

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_federated_release_index(DEFINITION)
            second = build_federated_release_index(DEFINITION)
            validated = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
        self.assertEqual(first, second)
        self.assertEqual(first.index, validated)
        self.assertEqual(first.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(first.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME])
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

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

    def test_v20_is_exact_v19_child_swap(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V44_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v44/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v44",
            }
        )
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(current, expected)

        base_index = json.loads((BASE_INDEX_DIR / INDEX_FILENAME).read_text())
        current_index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        self.assertEqual(current_index["generated_at"], GENERATED_AT)
        self.assertEqual(current_index["counts"], EXPECTED_COUNTS)
        self.assertEqual(current_index["policy"], FEDERATION_POLICY)
        self.assertIsNone(current_index["policy"]["unique_physical_site_count"])
        self.assertFalse(current_index["policy"]["child_entities_merged"])
        self.assertFalse(current_index["policy"]["cross_source_deduplication"])

        by_id = {item["release_id"]: item for item in current_index["releases"]}
        base_by_id = {item["release_id"]: item for item in base_index["releases"]}
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])
        self.assertEqual(by_id[NEW_RELEASE_ID]["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V44_MANIFEST_SHA256
        )
        self.assertFalse(by_id[NEW_RELEASE_ID]["scope"]["review_only"])

        delta = {
            key: current_index["counts"][key] - base_index["counts"][key]
            for key in EXPECTED_DELTA
        }
        self.assertEqual(delta, EXPECTED_DELTA)
        self.assertIsNone(current_index["counts"]["unique_physical_sites"])
        self.assertIsNone(base_index["counts"]["unique_physical_sites"])

    def test_review_only_and_rights_boundaries_remain_explicit(self) -> None:
        index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        by_id = {item["release_id"]: item for item in index["releases"]}
        self.assertTrue(by_id["osm-fuzzy-review-v2"]["scope"]["review_only"])
        self.assertFalse(by_id["global-open-v3"]["scope"]["review_only"])
        self.assertFalse(by_id[NEW_RELEASE_ID]["scope"]["review_only"])
        self.assertEqual(
            index["counts"]["review_only_source_scoped_entity_records"], 6_130
        )
        self.assertEqual(
            index["counts"]["non_review_source_scoped_entity_records"], 9_868
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
