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
DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v11.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v11"
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-19-public-open-v10.json"
)
PREVIOUS_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v10"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v32.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v32"
PREVIOUS_OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v30"

DEFINITION_SHA256 = "e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c"
INDEX_SHA256 = "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd"
MANIFEST_SHA256 = "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
PREVIOUS_DEFINITION_SHA256 = (
    "c34fc326286a6b7bd92dde9163760e94e6cfbccd3fb7aee62b7dd7892578a3fd"
)
PREVIOUS_MANIFEST_SHA256 = (
    "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)
CHILD_MANIFEST_SHA256 = {
    "epoch-official-open-seed-v32": OPEN_SEED_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    "epoch-official-open-seed-v32": OPEN_SEED_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
NEW_SOURCE_FAMILIES = {
    "data4_csr_reports",
    "data4_location_pages",
    "keppel_media",
    "larsen_toubro_press_releases",
    "servpac_press_releases",
    "telehouse_news",
    "uruguay_presidency_news",
    "vietnam_news_agency_vietnamplus",
    "viettel_official_linkedin",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FederatedReleaseV11Tests(unittest.TestCase):
    def test_exact_successor_rebuilds_twice_offline_and_is_frozen(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(INDEX_DIR / INDEX_FILENAME), INDEX_SHA256)
        self.assertEqual(sha256(INDEX_DIR / MANIFEST_FILENAME), MANIFEST_SHA256)
        self.assertEqual(sha256(PREVIOUS_DEFINITION), PREVIOUS_DEFINITION_SHA256)
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

    def test_v10_is_replaced_only_by_v32_with_exact_arithmetic(self) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_definition_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        current_definition_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(
            set(current_definition_children),
            (set(previous_definition_children) - {"epoch-official-open-seed-v30"})
            | {"epoch-official-open-seed-v32"},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                current_definition_children[release_id],
                previous_definition_children[release_id],
            )
        self.assertEqual(
            current_definition_children["epoch-official-open-seed-v32"],
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "license_expression": (
                    "CC-BY-4.0 data plus source-linked factual claims from official "
                    "company, government, utility, and exchange disclosures under "
                    "source-specific terms"
                ),
                "reference": "../../releases/2026-07-19-open-seed-v32/",
                "release_id": "epoch-official-open-seed-v32",
                "release_path": "../releases/2026-07-19-open-seed-v32",
                "rights_notice": (
                    "Epoch data is CC BY 4.0; official-source evidence remains "
                    "source-linked and no underlying copyrighted page, filing, "
                    "announcement, permit, or other source content is relicensed."
                ),
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
            (set(previous_releases) - {"epoch-official-open-seed-v30"})
            | {"epoch-official-open-seed-v32"},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_releases[release_id], previous_releases[release_id])

        previous_open = previous_releases["epoch-official-open-seed-v30"]
        open_release = current_releases["epoch-official-open-seed-v32"]
        previous_open_manifest = json.loads(
            (PREVIOUS_OPEN_SEED_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        open_manifest = json.loads(
            (OPEN_SEED_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        manifest_count_fields = (
            "entities",
            "evidence_records",
            "capacity_estimates",
            "construction_pipeline_records",
            "construction_source_signals",
            "resolution_candidates",
        )
        self.assertEqual(
            {field: previous_open_manifest[field] for field in manifest_count_fields},
            {
                "entities": 348,
                "evidence_records": 215,
                "capacity_estimates": 401,
                "construction_pipeline_records": 184,
                "construction_source_signals": 153,
                "resolution_candidates": 4,
            },
        )
        self.assertEqual(
            {field: open_manifest[field] for field in manifest_count_fields},
            {
                "entities": 370,
                "evidence_records": 226,
                "capacity_estimates": 401,
                "construction_pipeline_records": 195,
                "construction_source_signals": 161,
                "resolution_candidates": 4,
            },
        )
        self.assertEqual(open_release["manifest"]["sha256"], OPEN_SEED_MANIFEST_SHA256)
        self.assertEqual(
            open_release["counts"],
            {
                "capacity_estimates": 401,
                "construction_pipeline_records": 195,
                "entities_by_kind": {"campus": 216, "project": 154},
                "evidence_records": 226,
                "resolution_candidates": 4,
                "source_family_entries": 91,
                "source_scoped_entity_records": 370,
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
            open_release["rights"]["source_licenses"],
            ["CC-BY-4.0", "all-rights-reserved", "public-government-record"],
        )
        self.assertIn("no underlying copyrighted", open_release["rights"]["rights_notice"])

        expected_counts = {
            "capacity_estimates": 1187,
            "construction_pipeline_records": 6445,
            "evidence_records": 13239,
            "non_review_construction_pipeline_records": 315,
            "non_review_source_scoped_entity_records": 9665,
            "release_bundles": 3,
            "resolution_candidates": 100409,
            "review_only_construction_pipeline_records": 6130,
            "review_only_release_bundles": 1,
            "review_only_source_scoped_entity_records": 6130,
            "source_family_entries": 98,
            "source_scoped_entity_records": 15795,
            "unique_physical_sites": None,
        }
        self.assertEqual(current["counts"], expected_counts)
        expected_delta = {
            "capacity_estimates": 0,
            "construction_pipeline_records": 11,
            "evidence_records": 11,
            "non_review_construction_pipeline_records": 11,
            "non_review_source_scoped_entity_records": 22,
            "release_bundles": 0,
            "resolution_candidates": 0,
            "review_only_construction_pipeline_records": 0,
            "review_only_release_bundles": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_family_entries": len(NEW_SOURCE_FAMILIES),
            "source_scoped_entity_records": 22,
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


if __name__ == "__main__":
    unittest.main()
