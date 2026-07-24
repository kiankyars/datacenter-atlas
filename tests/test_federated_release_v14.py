from __future__ import annotations

import csv
import hashlib
import json
from contextlib import ExitStack
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
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v14.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v14"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v12.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v12"
REJECTED_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v13.json"
REJECTED_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v13"
V33_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"
V37_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v37.json"
V37_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v37"

GENERATED_AT = "2026-07-20T01:45:00Z"
OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v33"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v37"

DEFINITION_SHA256 = "03edc750359d2abe63f7a9cb4c83f0309767e44bf259190eda44c53a6bf6aaf4"
INDEX_SHA256 = "3f191e568fec07693f03d7f3870e63ea67b3cf5dc12535ac03fe0632190016d9"
MANIFEST_SHA256 = "ed4ab597becd2971de56a72acc39a754bb85b29bbdcb05e5c9a9674fb6c5e8ec"
MANIFEST_HASH_SHA256 = (
    "38e3925b02d31d66fcfceed8cc3d1075739776fe23d0cc44629c2e1bc3c71fab"
)
BASE_DEFINITION_SHA256 = (
    "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
)
BASE_INDEX_SHA256 = "266afde03fbb9eca16a0a9bfbd64c47fd50447b1b805da15542ff617f1629772"
BASE_MANIFEST_SHA256 = (
    "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
)
REJECTED_DEFINITION_SHA256 = (
    "0a82b9f772296da40c506c8323b8c3d1e3911d0960d9e5678adb6b7e887cf373"
)
REJECTED_INDEX_SHA256 = (
    "5e30d71535c1700c15ddd49c05d73b6f68c293840745561015bd29e3b7c9a96c"
)
REJECTED_MANIFEST_SHA256 = (
    "9e2c7f41bf01a2f79b322f91080325ae113b9db02bf8864c2253895c80cc1ee6"
)
REJECTED_MANIFEST_HASH_SHA256 = (
    "14c6559188fcb77c0dcf88919302383240801a78c38d843093cd4fcd8213a318"
)
V37_DEFINITION_SHA256 = (
    "c6786e684d76bfa72f5428e26396317bc05495da1afc656be4026c8c2acb9a66"
)
V37_MANIFEST_SHA256 = (
    "bcc0d1207e5b4c709557f49fc6d42e1080dcaebb762b32093848461afd52d30a"
)
CHILD_MANIFEST_SHA256 = {
    NEW_OPEN_RELEASE_ID: V37_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    NEW_OPEN_RELEASE_ID: V37_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
BASE_CHILDREN = {
    OLD_OPEN_RELEASE_ID: V33_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}

NEW_SOURCE_FAMILIES = {
    "atnorth_newsroom",
    "digital_edge_indonesia_newsroom",
    "green_mountain_project_pages",
    "kouvola_city_news",
    "loviisa_city_news",
    "macquarie_data_centres_facility_pages",
    "macquarie_data_centres_newsroom",
    "macquarie_data_centres_specifications",
    "merlin_properties_asset_pages",
    "merlin_properties_press_releases",
    "metsahallitus_press_releases",
    "moro_hub_news",
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1_197,
    "construction_pipeline_records": 6_458,
    "evidence_records": 13_256,
    "non_review_construction_pipeline_records": 328,
    "non_review_source_scoped_entity_records": 9_691,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 114,
    "source_scoped_entity_records": 15_821,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 8,
    "construction_pipeline_records": 9,
    "evidence_records": 13,
    "non_review_construction_pipeline_records": 9,
    "non_review_source_scoped_entity_records": 18,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 12,
    "source_scoped_entity_records": 18,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 411,
    "construction_pipeline_records": 208,
    "entities_by_kind": {"campus": 229, "project": 167},
    "evidence_records": 243,
    "resolution_candidates": 4,
    "source_family_entries": 107,
    "source_scoped_entity_records": 396,
}

MINOH_KEYS = {
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site": "130.0",
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1": "65.0",
}
EXPECTED_NEW_CAPACITIES = {
    (
        "curated:digital-edge-cgk-campus-bekasi",
        "critical_it_mw",
        "planned",
        "MW",
        "500.0",
        "reported",
    ),
    (
        "curated:digital-edge-cgk-campus-bekasi",
        "pue",
        "design",
        "ratio",
        "1.25",
        "reported",
    ),
    (
        "curated:green-mountain-undheim-campus:current-two-building-development",
        "critical_it_mw",
        "planned",
        "MW",
        "80.0",
        "reported",
    ),
    (
        "curated:green-mountain-undheim-campus:current-two-building-development",
        "gross_facility_mw",
        "planned",
        "MW",
        "100.0",
        "reported",
    ),
    (
        "curated:macquarie-ic3-super-west-facility",
        "critical_it_mw",
        "planned",
        "MW",
        "47.0",
        "reported",
    ),
    (
        "curated:macquarie-ic3-super-west-facility",
        "pue",
        "design",
        "ratio",
        "1.28",
        "reported",
    ),
    (
        "curated:macquarie-ic3-super-west-facility:phase-1-build",
        "critical_it_mw",
        "planned",
        "MW",
        "6.0",
        "reported",
    ),
    (
        "curated:merlin-lisbon-data-center-campus:phase-2-two-building-development",
        "critical_it_mw",
        "planned",
        "MW",
        "80.0",
        "calculated",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class FederatedReleaseV14Tests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        offline = AssertionError("v14 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=offline))

    def test_exact_pins_rebuild_twice_offline_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            REJECTED_DEFINITION: REJECTED_DEFINITION_SHA256,
            REJECTED_INDEX_DIR / INDEX_FILENAME: REJECTED_INDEX_SHA256,
            REJECTED_INDEX_DIR / MANIFEST_FILENAME: REJECTED_MANIFEST_SHA256,
            REJECTED_INDEX_DIR / MANIFEST_HASH_FILENAME: (
                REJECTED_MANIFEST_HASH_SHA256
            ),
            V37_DEFINITION: V37_DEFINITION_SHA256,
            V37_RELEASE / MANIFEST_FILENAME: V37_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        rejected_frozen = {
            path.name: path.read_bytes() for path in REJECTED_INDEX_DIR.iterdir()
        }
        current_frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with ExitStack() as stack:
            self._block_network(stack)
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
        self.assertEqual(first_build.index_bytes, current_frozen[INDEX_FILENAME])
        self.assertEqual(
            first_build.manifest_bytes, current_frozen[MANIFEST_FILENAME]
        )
        self.assertEqual(
            first_build.manifest_hash_bytes,
            current_frozen[MANIFEST_HASH_FILENAME],
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()},
            current_frozen,
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in REJECTED_INDEX_DIR.iterdir()},
            rejected_frozen,
        )

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

    def test_v14_is_v12_with_only_v33_replaced_by_v37(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected["generated_at"] = GENERATED_AT
        old_child = next(
            child
            for child in expected["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        old_child.update(
            {
                "expected_manifest_sha256": V37_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v37/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v37",
            }
        )
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(expected))
        self.assertEqual(current["schema_version"], 1)
        self.assertEqual(current["generated_at"], GENERATED_AT)

        base_children = {child["release_id"]: child for child in base["children"]}
        current_children = {
            child["release_id"]: child for child in current["children"]
        }
        self.assertEqual(
            set(current_children),
            (set(base_children) - {OLD_OPEN_RELEASE_ID}) | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_children[release_id], base_children[release_id])
            self.assertEqual(
                sha256(CHILDREN[release_id] / MANIFEST_FILENAME),
                CHILD_MANIFEST_SHA256[release_id],
            )

        replaced = current_children[NEW_OPEN_RELEASE_ID]
        previous = base_children[OLD_OPEN_RELEASE_ID]
        self.assertEqual(
            replaced,
            {
                "expected_manifest_sha256": V37_MANIFEST_SHA256,
                "license_expression": previous["license_expression"],
                "reference": "../../releases/2026-07-20-open-seed-v37/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v37",
                "rights_notice": previous["rights_notice"],
            },
        )
        self.assertNotIn("open-seed-v35", DEFINITION.read_text(encoding="utf-8"))

        rejected = json.loads(REJECTED_DEFINITION.read_text(encoding="utf-8"))
        rejected_release_ids = {
            child["release_id"] for child in rejected["children"]
        }
        self.assertIn("epoch-official-open-seed-v35", rejected_release_ids)
        self.assertNotEqual(current, rejected)

    def test_exact_child_source_family_and_federation_count_deltas(self) -> None:
        base_index = validate_federated_release_index(
            BASE_INDEX_DIR, child_release_paths=BASE_CHILDREN
        )
        current = validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        base_releases = {
            release["release_id"]: release for release in base_index["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(base_releases) - {OLD_OPEN_RELEASE_ID}) | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                current_releases[release_id], base_releases[release_id]
            )

        old_open = base_releases[OLD_OPEN_RELEASE_ID]
        new_open = current_releases[NEW_OPEN_RELEASE_ID]
        v37_manifest = json.loads(
            (V37_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(new_open["manifest"]["sha256"], V37_MANIFEST_SHA256)
        self.assertEqual(
            new_open["manifest"]["recorded_at"], "2026-07-20T01:29:39Z"
        )
        self.assertEqual(new_open["files"], v37_manifest["files"])
        self.assertEqual(new_open["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            set(new_open["source_families"]) - set(old_open["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertFalse(
            set(old_open["source_families"]) - set(new_open["source_families"])
        )
        self.assertEqual(
            len(new_open["source_families"]) - len(old_open["source_families"]),
            12,
        )
        self.assertEqual(
            new_open["rights"]["license_expression"],
            old_open["rights"]["license_expression"],
        )
        self.assertEqual(
            new_open["rights"]["rights_notice"],
            old_open["rights"]["rights_notice"],
        )
        self.assertEqual(
            new_open["rights"]["source_licenses"],
            ["CC-BY-4.0", "all-rights-reserved", "public-government-record"],
        )

        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        for field, delta in EXPECTED_DELTA.items():
            self.assertEqual(
                current["counts"][field] - base_index["counts"][field],
                delta,
                field,
            )
        self.assertEqual(current["generated_at"], GENERATED_AT)
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

        serialized = json.dumps(current, sort_keys=True).lower()
        for forbidden_claim in (
            "commercial census",
            "global completeness",
            "physical-site total",
            "parity achieved",
            "single comprehensive inventory",
            "deduplicated site count",
        ):
            self.assertNotIn(forbidden_claim, serialized)

    def test_capacity_types_and_nonadditivity_remain_child_semantics(self) -> None:
        v33_entities = csv_rows(V33_RELEASE / "entities.csv")
        v37_entities = csv_rows(V37_RELEASE / "entities.csv")
        v33_stable_keys = {row["stable_key"] for row in v33_entities}
        v37_by_id = {row["entity_id"]: row["stable_key"] for row in v37_entities}
        added_ids = {
            row["entity_id"]
            for row in v37_entities
            if row["stable_key"] not in v33_stable_keys
        }
        self.assertEqual(len(added_ids), 18)

        capacity_rows = csv_rows(V37_RELEASE / "capacity_estimates.csv")
        added_capacity_rows = [
            row for row in capacity_rows if row["entity_id"] in added_ids
        ]
        self.assertEqual(len(added_capacity_rows), 8)
        observed = {
            (
                v37_by_id[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["unit"],
                row["base"],
                row["method"],
            )
            for row in added_capacity_rows
        }
        self.assertEqual(observed, EXPECTED_NEW_CAPACITIES)
        for row in added_capacity_rows:
            self.assertEqual(row["low"], row["base"])
            self.assertEqual(row["high"], row["base"])
            self.assertEqual(row["target_date"], "")

        notes_by_key_metric = {
            (v37_by_id[row["entity_id"]], row["metric"]): row["notes"]
            for row in added_capacity_rows
        }
        green_prefix = (
            "curated:green-mountain-undheim-campus:"
            "current-two-building-development"
        )
        self.assertIn(
            "or additive to",
            notes_by_key_metric[(green_prefix, "critical_it_mw")],
        )
        self.assertIn(
            "or additive to",
            notes_by_key_metric[(green_prefix, "gross_facility_mw")],
        )
        self.assertIn(
            "must not be summed",
            notes_by_key_metric[
                ("curated:macquarie-ic3-super-west-facility", "critical_it_mw")
            ],
        )
        self.assertIn(
            "not additive",
            notes_by_key_metric[
                (
                    "curated:macquarie-ic3-super-west-facility:phase-1-build",
                    "critical_it_mw",
                )
            ],
        )
        self.assertIn(
            "not additive",
            notes_by_key_metric[
                (
                    "curated:merlin-lisbon-data-center-campus:"
                    "phase-2-two-building-development",
                    "critical_it_mw",
                )
            ],
        )
        self.assertIn(
            "not allocated to CGK1",
            notes_by_key_metric[
                ("curated:digital-edge-cgk-campus-bekasi", "critical_it_mw")
            ],
        )

        minoh_ids = {
            row["entity_id"]: row["stable_key"]
            for row in v37_entities
            if row["stable_key"] in MINOH_KEYS
        }
        minoh_rows = [
            row for row in capacity_rows if row["entity_id"] in minoh_ids
        ]
        self.assertEqual(len(minoh_rows), 2)
        self.assertEqual(
            {
                minoh_ids[row["entity_id"]]: row["base"] for row in minoh_rows
            },
            MINOH_KEYS,
        )
        for row in minoh_rows:
            self.assertEqual(row["metric"], "gross_facility_mw")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertIn("non-additive", row["notes"])
            self.assertIn(
                "not IT, grid, generation, current load, or energy",
                row["notes"],
            )

        index = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        open_descriptor = next(
            release
            for release in index["releases"]
            if release["release_id"] == NEW_OPEN_RELEASE_ID
        )
        self.assertEqual(open_descriptor["counts"]["capacity_estimates"], 411)
        self.assertNotIn("capacity_base_totals", open_descriptor)
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
