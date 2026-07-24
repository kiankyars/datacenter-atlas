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
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v19.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v19"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v18.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v18"
V43_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v43.json"
V43_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v43"

GENERATED_AT = "2026-07-20T06:55:11Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v42"
NEW_RELEASE_ID = "epoch-official-open-seed-v43"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "f1b5c6e55324e6db97110bc73846df536ba05b05bc9ac28c2d8ed5410940ec06"
INDEX_SHA256 = "29bada0af2140d0c0645abaf8ed192e1f832cbb39692af3a475b0a0a74780327"
MANIFEST_SHA256 = "55079d65fbb7cf8ce79dd753e7dcf3e6067f00a8c83de23e29de501b7c6063e0"
MANIFEST_HASH_SHA256 = (
    "9e0318befee36e53d250a5fe05809dca2d3204f1569241b14b1a41774c1087ce"
)
BASE_DEFINITION_SHA256 = (
    "bab7ae5e2f09e34d658663112c70b88ac3ca3b02a075380356cfe3f7af7298d0"
)
BASE_INDEX_SHA256 = "45048828bf4cc90e1c70fd0da86962c5a0bc0a00d588ad8c3f22e35e2597f6df"
BASE_MANIFEST_SHA256 = (
    "3f52b09facdaa5bbea82bbef045e459901a6f3206452271482d0ea798a7f28d6"
)
V43_DEFINITION_SHA256 = (
    "3b789babfbaaad54166bb7b94305c24258644bec239dd76dcf19186fdd56d6fa"
)
V43_MANIFEST_SHA256 = (
    "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537"
)

EXPECTED_COUNTS = {
    "capacity_estimates": 1_227,
    "construction_pipeline_records": 6_534,
    "evidence_records": 13_321,
    "non_review_construction_pipeline_records": 404,
    "non_review_source_scoped_entity_records": 9_839,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 151,
    "source_scoped_entity_records": 15_969,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 14,
    "construction_pipeline_records": 22,
    "evidence_records": 35,
    "non_review_construction_pipeline_records": 22,
    "non_review_source_scoped_entity_records": 42,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 21,
    "source_scoped_entity_records": 42,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 441,
    "construction_pipeline_records": 284,
    "entities_by_kind": {"campus": 298, "project": 246},
    "evidence_records": 308,
    "resolution_candidates": 4,
    "source_family_entries": 144,
    "source_scoped_entity_records": 544,
}
CHILDREN = {
    NEW_RELEASE_ID: V43_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FederatedReleaseV19Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v19 federation attempted network or v42 access")
        original = federated_release_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if "open-seed-v42" in path.as_posix():
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
            V43_DEFINITION: V43_DEFINITION_SHA256,
            V43_RELEASE / MANIFEST_FILENAME: V43_MANIFEST_SHA256,
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

    def test_v19_is_exact_v18_child_swap(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V43_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v43/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v43",
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
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V43_MANIFEST_SHA256
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
        self.assertEqual(index["counts"]["review_only_source_scoped_entity_records"], 6_130)
        self.assertEqual(index["counts"]["non_review_source_scoped_entity_records"], 9_839)
        self.assertEqual(
            index["counts"]["source_scoped_entity_records"],
            index["counts"]["review_only_source_scoped_entity_records"]
            + index["counts"]["non_review_source_scoped_entity_records"],
        )
        self.assertFalse(index["policy"]["licenses_or_attributions_combined"])
        self.assertEqual(
            {item["release_id"]: item["rights"]["license_expression"] for item in index["releases"]},
            {
                NEW_RELEASE_ID: "CC-BY-4.0 data plus source-linked factual claims from official company, government, utility, and exchange disclosures under source-specific terms",
                "global-open-v3": "ODbL-1.0 with CC0-1.0 and Public Domain inputs",
                "osm-fuzzy-review-v2": "ODbL-1.0 with a Public Domain boundary input",
            },
        )


if __name__ == "__main__":
    unittest.main()
