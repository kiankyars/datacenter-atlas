from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    build_federated_release_index,
    validate_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v10.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v10"
PREVIOUS_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v9"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v30.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v30"

DEFINITION_SHA256 = "c34fc326286a6b7bd92dde9163760e94e6cfbccd3fb7aee62b7dd7892578a3fd"
INDEX_SHA256 = "aa6b55f29d237aa298cc6d2f3dfe5dfd57ed7bbd1ef6bd63688efd6be1e38251"
MANIFEST_SHA256 = "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2"
PREVIOUS_MANIFEST_SHA256 = (
    "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "b89c7414fe9a96ddd2acfff766386dda514d61278dae039d1d70eb490340ef12"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
)
CHILDREN = {
    "epoch-official-open-seed-v30": OPEN_SEED_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


class FederatedReleaseV10Tests(unittest.TestCase):
    def test_exact_successor_rebuilds_twice_offline_and_is_frozen(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((INDEX_DIR / INDEX_FILENAME).read_bytes()).hexdigest(),
            INDEX_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((INDEX_DIR / MANIFEST_FILENAME).read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_INDEX_DIR / MANIFEST_FILENAME).read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(OPEN_SEED_DEFINITION.read_bytes()).hexdigest(),
            OPEN_SEED_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((OPEN_SEED_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            OPEN_SEED_MANIFEST_SHA256,
        )

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        offline = AssertionError("federation rebuild attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first_build = build_federated_release_index(DEFINITION)
            second_build = build_federated_release_index(DEFINITION)
            first = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            second = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )

        self.assertEqual(first_build, second_build)
        self.assertEqual(first, second)
        self.assertEqual(first_build.index, first)
        self.assertEqual(first_build.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first_build.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(first_build.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME])
        self.assertEqual({path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        entries = list(INDEX_DIR.iterdir())
        self.assertEqual(
            {path.name for path in entries},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in entries
            )
        )

    def test_v9_is_replaced_only_by_v30_with_exact_arithmetic(self) -> None:
        previous = json.loads(
            (PREVIOUS_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        previous_releases = {
            release["release_id"]: release for release in previous["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(previous_releases) - {"epoch-official-open-seed-v20"})
            | {"epoch-official-open-seed-v30"},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_releases[release_id], previous_releases[release_id])

        open_release = current_releases["epoch-official-open-seed-v30"]
        self.assertEqual(open_release["manifest"]["sha256"], OPEN_SEED_MANIFEST_SHA256)
        self.assertEqual(
            open_release["rights"]["source_licenses"],
            ["CC-BY-4.0", "all-rights-reserved", "public-government-record"],
        )
        self.assertIn("no underlying copyrighted", open_release["rights"]["rights_notice"])

        expected_counts = {
            "capacity_estimates": 1187,
            "construction_pipeline_records": 6434,
            "evidence_records": 13228,
            "non_review_construction_pipeline_records": 304,
            "non_review_source_scoped_entity_records": 9643,
            "release_bundles": 3,
            "resolution_candidates": 100409,
            "review_only_construction_pipeline_records": 6130,
            "review_only_release_bundles": 1,
            "review_only_source_scoped_entity_records": 6130,
            "source_family_entries": 89,
            "source_scoped_entity_records": 15773,
            "unique_physical_sites": None,
        }
        self.assertEqual(current["counts"], expected_counts)
        expected_delta = {
            "capacity_estimates": 9,
            "construction_pipeline_records": 33,
            "evidence_records": 33,
            "non_review_construction_pipeline_records": 33,
            "non_review_source_scoped_entity_records": 66,
            "release_bundles": 0,
            "resolution_candidates": 0,
            "review_only_construction_pipeline_records": 0,
            "review_only_release_bundles": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_family_entries": 22,
            "source_scoped_entity_records": 66,
        }
        for field, delta in expected_delta.items():
            self.assertEqual(current["counts"][field] - previous["counts"][field], delta)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertFalse(current["policy"]["child_entities_merged"])
        self.assertFalse(current["policy"]["cross_source_deduplication"])
        self.assertIsNone(current["counts"]["unique_physical_sites"])


if __name__ == "__main__":
    unittest.main()
