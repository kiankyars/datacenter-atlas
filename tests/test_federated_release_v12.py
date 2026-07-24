from __future__ import annotations

import csv
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
DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v12.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v12"
PREVIOUS_DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v11.json"
PREVIOUS_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v11"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v33.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"

DEFINITION_SHA256 = "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
INDEX_SHA256 = "266afde03fbb9eca16a0a9bfbd64c47fd50447b1b805da15542ff617f1629772"
MANIFEST_SHA256 = "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
MANIFEST_HASH_SHA256 = (
    "a827930e85454c47940e869cecdf875d809a372c624e13c586c7a1099f090bc2"
)
PREVIOUS_DEFINITION_SHA256 = (
    "e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c"
)
PREVIOUS_INDEX_SHA256 = (
    "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd"
)
PREVIOUS_MANIFEST_SHA256 = (
    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)
GENERATED_AT = "2026-07-19T23:59:30Z"

CHILD_MANIFEST_SHA256 = {
    "epoch-official-open-seed-v33": OPEN_SEED_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    "epoch-official-open-seed-v33": OPEN_SEED_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
NEW_SOURCE_FAMILIES = {
    "adani_connect_magazine",
    "csc_news_and_blog",
    "esr_newsroom",
    "srv_cision_press_releases",
}
MINOH_KEYS = {
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site": 130.0,
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1": 65.0,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class FederatedReleaseV12Tests(unittest.TestCase):
    def test_exact_successor_rebuilds_twice_offline_and_is_frozen(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(INDEX_DIR / INDEX_FILENAME), INDEX_SHA256)
        self.assertEqual(sha256(INDEX_DIR / MANIFEST_FILENAME), MANIFEST_SHA256)
        self.assertEqual(
            sha256(INDEX_DIR / MANIFEST_HASH_FILENAME), MANIFEST_HASH_SHA256
        )
        self.assertEqual(sha256(PREVIOUS_DEFINITION), PREVIOUS_DEFINITION_SHA256)
        self.assertEqual(
            sha256(PREVIOUS_INDEX_DIR / INDEX_FILENAME), PREVIOUS_INDEX_SHA256
        )
        self.assertEqual(
            sha256(PREVIOUS_INDEX_DIR / MANIFEST_FILENAME),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(sha256(OPEN_SEED_DEFINITION), OPEN_SEED_DEFINITION_SHA256)
        self.assertEqual(
            sha256(OPEN_SEED_RELEASE / MANIFEST_FILENAME),
            OPEN_SEED_MANIFEST_SHA256,
        )
        for release_id, release in CHILDREN.items():
            self.assertFalse(release.is_symlink())
            self.assertEqual(
                sha256(release / MANIFEST_FILENAME),
                CHILD_MANIFEST_SHA256[release_id],
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

    def test_v11_replaces_only_open_seed_v32_with_v33_and_exact_arithmetic(self) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_definition_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        current_definition_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(current_definition["schema_version"], previous_definition["schema_version"])
        self.assertEqual(current_definition["generated_at"], GENERATED_AT)
        self.assertEqual(
            set(current_definition_children),
            (set(previous_definition_children) - {"epoch-official-open-seed-v32"})
            | {"epoch-official-open-seed-v33"},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                current_definition_children[release_id],
                previous_definition_children[release_id],
            )
        previous_open_definition = previous_definition_children[
            "epoch-official-open-seed-v32"
        ]
        current_open_definition = current_definition_children[
            "epoch-official-open-seed-v33"
        ]
        self.assertEqual(
            current_open_definition,
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "license_expression": previous_open_definition["license_expression"],
                "reference": "../../releases/2026-07-19-open-seed-v33/",
                "release_id": "epoch-official-open-seed-v33",
                "release_path": "../releases/2026-07-19-open-seed-v33",
                "rights_notice": previous_open_definition["rights_notice"],
            },
        )

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
            (set(previous_releases) - {"epoch-official-open-seed-v32"})
            | {"epoch-official-open-seed-v33"},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_releases[release_id], previous_releases[release_id])

        previous_open = previous_releases["epoch-official-open-seed-v32"]
        open_release = current_releases["epoch-official-open-seed-v33"]
        open_manifest = json.loads(
            (OPEN_SEED_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(open_release["manifest"]["sha256"], OPEN_SEED_MANIFEST_SHA256)
        self.assertEqual(open_release["manifest"]["recorded_at"], "2026-07-19T23:59:00Z")
        self.assertEqual(open_release["files"], open_manifest["files"])
        self.assertEqual(
            open_release["counts"],
            {
                "capacity_estimates": 403,
                "construction_pipeline_records": 199,
                "entities_by_kind": {"campus": 220, "project": 158},
                "evidence_records": 230,
                "resolution_candidates": 4,
                "source_family_entries": 95,
                "source_scoped_entity_records": 378,
            },
        )
        self.assertEqual(
            set(open_release["source_families"]),
            set(previous_open["source_families"]) | NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(
            set(open_release["source_families"])
            - set(previous_open["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertFalse(
            set(previous_open["source_families"])
            - set(open_release["source_families"])
        )
        self.assertEqual(
            open_release["rights"]["license_expression"],
            previous_open["rights"]["license_expression"],
        )
        self.assertEqual(
            open_release["rights"]["rights_notice"],
            previous_open["rights"]["rights_notice"],
        )
        self.assertEqual(
            open_release["rights"]["source_licenses"],
            ["CC-BY-4.0", "all-rights-reserved", "public-government-record"],
        )

        expected_counts = {
            "capacity_estimates": 1189,
            "construction_pipeline_records": 6449,
            "evidence_records": 13243,
            "non_review_construction_pipeline_records": 319,
            "non_review_source_scoped_entity_records": 9673,
            "release_bundles": 3,
            "resolution_candidates": 100409,
            "review_only_construction_pipeline_records": 6130,
            "review_only_release_bundles": 1,
            "review_only_source_scoped_entity_records": 6130,
            "source_family_entries": 102,
            "source_scoped_entity_records": 15803,
            "unique_physical_sites": None,
        }
        self.assertEqual(current["counts"], expected_counts)
        expected_delta = {
            "capacity_estimates": 2,
            "construction_pipeline_records": 4,
            "evidence_records": 4,
            "non_review_construction_pipeline_records": 4,
            "non_review_source_scoped_entity_records": 8,
            "release_bundles": 0,
            "resolution_candidates": 0,
            "review_only_construction_pipeline_records": 0,
            "review_only_release_bundles": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_family_entries": 4,
            "source_scoped_entity_records": 8,
        }
        for field, delta in expected_delta.items():
            self.assertEqual(current["counts"][field] - previous["counts"][field], delta)

        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertTrue(current["policy"]["federation_only"])
        self.assertFalse(current["policy"]["child_payloads_copied"])
        self.assertFalse(current["policy"]["child_entities_merged"])
        self.assertFalse(current["policy"]["cross_source_deduplication"])
        self.assertFalse(current["policy"]["licenses_or_attributions_combined"])
        self.assertFalse(
            current["policy"]["source_family_labels_collapsed_across_releases"]
        )
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertIsNone(current["policy"]["unique_physical_site_count"])

    def test_minoh_capacity_observations_remain_nested_child_semantics(self) -> None:
        entity_ids = {
            row["stable_key"]: row["entity_id"]
            for row in csv_rows(OPEN_SEED_RELEASE / "entities.csv")
            if row["stable_key"] in MINOH_KEYS
        }
        self.assertEqual(set(entity_ids), set(MINOH_KEYS))
        key_by_entity_id = {value: key for key, value in entity_ids.items()}
        minoh_capacity_rows = [
            row
            for row in csv_rows(OPEN_SEED_RELEASE / "capacity_estimates.csv")
            if row["entity_id"] in key_by_entity_id
        ]
        self.assertEqual(len(minoh_capacity_rows), 2)
        self.assertEqual(
            {
                key_by_entity_id[row["entity_id"]]: float(row["base"])
                for row in minoh_capacity_rows
            },
            MINOH_KEYS,
        )
        for row in minoh_capacity_rows:
            self.assertEqual(row["metric"], "gross_facility_mw")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertEqual(row["low"], row["base"])
            self.assertEqual(row["high"], row["base"])
            self.assertEqual(row["target_date"], "")
            self.assertIn("non-additive", row["notes"])
            self.assertIn(
                "not IT, grid, generation, current load, or energy", row["notes"]
            )

        index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8"))
        open_descriptor = next(
            release
            for release in index["releases"]
            if release["release_id"] == "epoch-official-open-seed-v33"
        )
        self.assertEqual(open_descriptor["counts"]["capacity_estimates"], 403)
        self.assertNotIn("capacity_base_totals", open_descriptor)
        serialized = json.dumps(index, sort_keys=True).lower()
        for forbidden_claim in (
            "195 mw",
            "commercial census",
            "completeness",
            "global census",
            "parity",
        ):
            self.assertNotIn(forbidden_claim, serialized)
        self.assertIsNone(index["counts"]["unique_physical_sites"])
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        self.assertFalse(
            any(
                path.suffix in {".csv", ".geojson", ".sqlite"}
                for path in INDEX_DIR.iterdir()
            )
        )


if __name__ == "__main__":
    unittest.main()
