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
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v21.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v21"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v20.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v20"
V46_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v46.json"
V46_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v46"

GENERATED_AT = "2026-07-20T09:52:45Z"
V46_RECORDED_AT = "2026-07-20T09:41:21Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v44"
NEW_RELEASE_ID = "epoch-official-open-seed-v46"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "623302bdec9d074f8ea9eec23f09516e2e51331884b8dedf3b4c49febc2d38d8"
INDEX_SHA256 = "d6694f7878ca193193d7a63affc391739bfe32b026d144e5166437db0678d905"
MANIFEST_SHA256 = "24210f9484ac7f0143a76395782e739c49ce75a95059920a8dedd62c43b9b4cc"
MANIFEST_HASH_SHA256 = (
    "8e233bad09113e0e4207db127face6c8e0444763ec150a2416134bf354b201ed"
)
BASE_DEFINITION_SHA256 = (
    "5bd47924d1c19c30b77b1f76198a6924a461ff9d1a8e622a4216996335afe53d"
)
BASE_INDEX_SHA256 = "8dfcbb82ac3ad8964ab6fb220da19b3fbe6720c3a65b0c34da624ca6829d53f4"
BASE_MANIFEST_SHA256 = (
    "361552c5c01e70ca1c8a562f4d1f20801d2b40b7367cc0a11998e72c50e61e78"
)
V46_DEFINITION_SHA256 = (
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293"
)
V46_MANIFEST_SHA256 = (
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
)

CODE_HASHES = {
    "datacenter_atlas/federated_release.py": "bc81c767c516f543bafe90cb4818d62956e5fd7bea69363dd274bad090155e29",
    "scripts/build_federated_release_index.py": "97068c3eb5b7c233388beab916c09266a1a4a9ae5d54d0f52014b2c1a949d078",
    "tests/test_federated_release_v20.py": "7fd2b051a47d48ddfbb47daa02235a97e023d963b7fc69d54a5fcb75fde96bc7",
}

EXPECTED_COUNTS = {
    "capacity_estimates": 1_237,
    "construction_pipeline_records": 6_567,
    "evidence_records": 13_342,
    "non_review_construction_pipeline_records": 437,
    "non_review_source_scoped_entity_records": 9_898,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 168,
    "source_scoped_entity_records": 16_028,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 2,
    "construction_pipeline_records": 18,
    "evidence_records": 2,
    "non_review_construction_pipeline_records": 18,
    "non_review_source_scoped_entity_records": 30,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 2,
    "source_scoped_entity_records": 30,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 451,
    "construction_pipeline_records": 317,
    "entities_by_kind": {"campus": 324, "project": 279},
    "evidence_records": 329,
    "resolution_candidates": 4,
    "source_family_entries": 161,
    "source_scoped_entity_records": 603,
}
CHILDREN = {
    NEW_RELEASE_ID: V46_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FederatedReleaseV21Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v21 federation attempted network or stale open-seed access")
        original = federated_release_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if "open-seed-v44" in rendered or "open-seed-v45" in rendered:
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
            V46_DEFINITION: V46_DEFINITION_SHA256,
            V46_RELEASE / MANIFEST_FILENAME: V46_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        for relative, expected in CODE_HASHES.items():
            path = ROOT / relative
            self.assertEqual(sha256(path), expected, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, path)

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

    def test_v21_is_exact_v20_child_swap(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V46_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v46/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v46",
            }
        )
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(current, expected)
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(V46_RECORDED_AT.replace("Z", "+00:00")),
        )

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
        self.assertEqual(by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V46_MANIFEST_SHA256)
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
        self.assertEqual(index["counts"]["non_review_source_scoped_entity_records"], 9_898)
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
