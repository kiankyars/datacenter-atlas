from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v19.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v19"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v18.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v18"
TRANCHE_TEST = ROOT / "tests" / "test_curated_nextdc_1h26_tranche.py"

DEFINITION_SHA256 = "8c6e88b9228b23657475bca28ba8de944e0653d2946b02762f51ebbe726efac6"
MANIFEST_SHA256 = "f16569524f4bd2059329a2a9b68018cf1595c3d56f4a2b4dbfd24a56891d8bd3"
PREVIOUS_DEFINITION_SHA256 = (
    "afef922eb287cef0cfcaef49ae46da2df150e99875e93b56c0dc38c06f182064"
)
PREVIOUS_MANIFEST_SHA256 = (
    "913971bbc966fb7f8f62d31f8ba79d236c5f6ff982170733f59d89f95a11a868"
)
TRANCHE_TEST_SHA256 = (
    "9a9f8e3f93992ab50a0719ec6cdce09e73a63de5f55914f98401078010740995"
)
RECORDED_AT = "2026-07-19T19:59:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout.json": (
        "ec0da982be0d87f142618100a518f947fd58bc014d5f7b621629fbe7cda5f97d"
    ),
    "curated-official-2026-07-19-nextdc-d2-darwin-1h26-fitout.json": (
        "77cf37681f3bdf093bd381b5cbd325f33e3fc8e3f8ff5e48e35de324b9caad65"
    ),
    "curated-official-2026-07-19-nextdc-ge1-geelong-1h26-fitout.json": (
        "5cffac3c97fd9faaa5644d18d7c0bbac8a6016be6930685dea32dce0a89347c4"
    ),
    "curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout.json": (
        "b428c2d24c796e5dc68ae64221c90fc0a85680061a092f97786512941b2c8da3"
    ),
    "curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout.json": (
        "1674ac8b23e48cf947e01ede96f0baa3fc94d891bc84ab35b4c61d10134e317b"
    ),
    "curated-official-2026-07-19-nextdc-m3-melbourne-1h26-fitout.json": (
        "998ddd53d217df3a1411c55e0ff1037488b6456d5f62d50e1d7429a8842b6ceb"
    ),
    "curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout.json": (
        "cf22bd4df7074daf34dc13f0ba2855e7ed8d5ec701b603f45aca3531ba0afefd"
    ),
    "curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout.json": (
        "60c0825766b68dccfcfa8b361389394bd2b5d0321ed0591fc20da84512798a46"
    ),
    "curated-official-2026-07-19-nextdc-s3-sydney-1h26-fitout.json": (
        "3269918319752e643a38b7391beea53377eff987547864dcb624dacd6cf1b969"
    ),
    "curated-official-2026-07-19-nextdc-s4-sydney-1h26-early-works.json": (
        "4f465a73da77cc106c37aff41050079c1f07e78d25e3bdd92319b78a30418082"
    ),
    "curated-official-2026-07-19-nextdc-s6-sydney-1h26-fitout.json": (
        "4a7482e8169884bd98cd8159217459064088e78a21c11c28584da766bc19ce7b"
    ),
    "curated-official-2026-07-19-nextdc-sc1-sunshine-coast-1h26-fitout.json": (
        "418ed5e49ff689d140b10040e458758793418797d6179340b0e7441e6216f1d9"
    ),
    "curated-official-2026-07-19-nextdc-sc2-sunshine-coast-1h26-fitout.json": (
        "768526b34023aac438eca3513898102b90d29f0107e52da16e6e16c6fe7e01c2"
    ),
    "curated-official-2026-07-19-nextdc-tk1-tokyo-1h26-preliminary-works.json": (
        "7daf178a818c25aff4b2e9a1af4f4a894622d7dc703c1fed0564e9c8e3533a51"
    ),
}

NEW_CAMPUS_KEYS = {
    "curated:nextdc-b2-brisbane",
    "curated:nextdc-d2-darwin",
    "curated:nextdc-ge1-geelong",
    "curated:nextdc-kl1-kuala-lumpur",
    "curated:nextdc-m2-melbourne",
    "curated:nextdc-m3-melbourne",
    "curated:nextdc-p1-perth",
    "curated:nextdc-p2-perth",
    "curated:nextdc-s3-sydney",
    "curated:nextdc-s4-sydney",
    "curated:nextdc-s6-sydney",
    "curated:nextdc-sc1-sunshine-coast",
    "curated:nextdc-tk1-tokyo",
}
EXISTING_SC2_CAMPUS_KEY = "curated:nextdc-sc2-maroochydore"

FITOUT_CAPACITIES = {
    "curated:nextdc-b2-brisbane:incremental-in-progress-fit-out": Decimal("2"),
    "curated:nextdc-d2-darwin:incremental-in-progress-fit-out": Decimal("1.5"),
    "curated:nextdc-ge1-geelong:incremental-in-progress-fit-out": Decimal("1"),
    "curated:nextdc-kl1-kuala-lumpur:incremental-in-progress-fit-out": Decimal("15"),
    "curated:nextdc-m2-melbourne:incremental-in-progress-fit-out": Decimal("30"),
    "curated:nextdc-m3-melbourne:incremental-in-progress-fit-out": Decimal("185"),
    "curated:nextdc-p1-perth:incremental-in-progress-fit-out": Decimal("2"),
    "curated:nextdc-p2-perth:incremental-in-progress-fit-out": Decimal("4"),
    "curated:nextdc-s3-sydney:incremental-in-progress-fit-out": Decimal("20"),
    "curated:nextdc-s6-sydney:incremental-in-progress-fit-out": Decimal("10.8"),
    "curated:nextdc-sc1-sunshine-coast:incremental-in-progress-fit-out": Decimal("0.6"),
    "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out": Decimal("1"),
}
EARLY_PROJECTS = {
    "curated:nextdc-s4-sydney:early-works",
    "curated:nextdc-tk1-tokyo:preliminary-works",
}
NEW_PROJECT_KEYS = set(FITOUT_CAPACITIES) | EARLY_PROJECTS
NEW_ENTITY_KEYS = NEW_CAMPUS_KEYS | NEW_PROJECT_KEYS


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


class OpenSeedV19Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        release_entries = list(RELEASE.iterdir())
        self.assertTrue(release_entries)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in release_entries))
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in release_entries)
        )

        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_open_seed_release(DEFINITION, RELEASE)
            second = validate_open_seed_release(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 274)
        self.assertEqual(first["entities_by_kind"], {"campus": 168, "project": 106})
        self.assertEqual(first["evidence_records"], 179)
        self.assertEqual(first["capacity_estimates"], 391)
        self.assertEqual(first["construction_pipeline_records"], 147)
        self.assertEqual(first["construction_source_signals"], 122)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 274)
        self.assertEqual(summary["projects_total"], 106)
        self.assertEqual(summary["evidence_total"], 196)
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 3,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 15,
                "operational": 31,
                "permitted": 2,
                "shell": 4,
                "site_preparation": 8,
                "under_construction": 84,
            },
        )

    def test_v18_closure_is_sealed_and_v19_is_exactly_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 27,
            "evidence.csv": 1,
            "capacity_estimates.csv": 12,
            "construction_pipeline.csv": 14,
            "construction_source_signals.csv": 1,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous_rows = rows(PREVIOUS_RELEASE / filename)
            current_rows = rows(RELEASE / filename)
            self.assertTrue(
                row_set(PREVIOUS_RELEASE / filename) <= row_set(RELEASE / filename),
                filename,
            )
            self.assertEqual(
                len(current_rows) - len(previous_rows), expected_delta, filename
            )

        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_inputs = {
            (record["path"], record["sha256"])
            for record in previous["curated_inputs"]
        }
        current_inputs = {
            (record["path"], record["sha256"])
            for record in current["curated_inputs"]
        }
        expected_additions = {
            (f"sources/{filename}", digest)
            for filename, digest in SOURCE_HASHES.items()
        }
        self.assertEqual(len(previous_inputs), 94)
        self.assertEqual(len(current_inputs), 108)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v19")

    def test_nextdc_rows_preserve_only_accepted_source_semantics(self) -> None:
        self.assertEqual(
            hashlib.sha256(TRANCHE_TEST.read_bytes()).hexdigest(),
            TRANCHE_TEST_SHA256,
        )
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(input_by_name[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            documents[filename] = document
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])

            project_key = document["project"]["stable_key"]
            lifecycle = document["lifecycle"]
            self.assertEqual(len(lifecycle), 1)
            self.assertEqual(lifecycle[0]["entity"], "project")
            self.assertEqual(
                lifecycle[0]["method"], "authoritative_physical_status_update"
            )
            if project_key in FITOUT_CAPACITIES:
                self.assertEqual(
                    (lifecycle[0]["value"], lifecycle[0]["as_of_date"]),
                    ("mep_electrical", "2025-12-31"),
                )
                self.assertEqual(len(document["capacities"]), 1)
                capacity = document["capacities"][0]
                expected_value = FITOUT_CAPACITIES[project_key]
                self.assertEqual(
                    (
                        capacity["metric"],
                        capacity["stage"],
                        capacity["unit"],
                        capacity["method"],
                        capacity["as_of_date"],
                        capacity["target_date"],
                    ),
                    (
                        "critical_it_mw",
                        "planned",
                        "MW",
                        "reported",
                        "2025-12-31",
                        None,
                    ),
                )
                self.assertEqual(
                    {
                        Decimal(str(capacity["low"])),
                        Decimal(str(capacity["base"])),
                        Decimal(str(capacity["high"])),
                    },
                    {expected_value},
                )
            else:
                self.assertIn(project_key, EARLY_PROJECTS)
                self.assertEqual(
                    (lifecycle[0]["value"], lifecycle[0]["as_of_date"]),
                    ("site_preparation", "2026-02-25"),
                )
                self.assertEqual(document["capacities"], [])

        metadata = next(iter(documents.values()))["evidence"][0]["metadata"]
        self.assertEqual(metadata["s4_total_power_plan_as_reported_mw"], 350)
        self.assertEqual(metadata["s4_total_power_plan_qualifier"], "approximately")
        self.assertEqual(metadata["tk1_total_power_plan_as_reported_mw"], 30)
        self.assertEqual(metadata["tk1_total_power_plan_qualifier"], "approximately")
        self.assertIn(
            "create no capacity rows", metadata["early_works_capacity_guardrail"]
        )

        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {
            row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entities) - previous_keys, NEW_ENTITY_KEYS)
        self.assertIn(EXISTING_SC2_CAMPUS_KEY, previous_keys)
        for stable_key in NEW_ENTITY_KEYS:
            entity = entities[stable_key]
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual(entity["geometry_json"], "null")
            self.assertEqual(
                (entity["owner"], entity["operator"], entity["users"]),
                ("", "", ""),
            )
            self.assertEqual(entity["operating_model"], "")
            self.assertEqual(json.loads(entity["workloads_json"]), [])

        for stable_key in FITOUT_CAPACITIES:
            entity = entities[stable_key]
            self.assertEqual(
                (entity["status"], entity["status_as_of"], entity["status_method"]),
                (
                    "mep_electrical",
                    "2025-12-31",
                    "authoritative_physical_status_update",
                ),
            )
        for stable_key in EARLY_PROJECTS:
            entity = entities[stable_key]
            self.assertEqual(
                (entity["status"], entity["status_as_of"], entity["status_method"]),
                (
                    "site_preparation",
                    "2026-02-25",
                    "authoritative_physical_status_update",
                ),
            )

        entity_id_to_key = {
            row["entity_id"]: row["stable_key"] for row in entities.values()
        }
        new_capacity_rows = [
            row
            for row in rows(RELEASE / "capacity_estimates.csv")
            if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
        ]
        observed_capacities = {
            entity_id_to_key[row["entity_id"]]: Decimal(row["base"])
            for row in new_capacity_rows
        }
        self.assertEqual(observed_capacities, FITOUT_CAPACITIES)
        self.assertEqual(
            sum(observed_capacities.values(), Decimal("0")), Decimal("272.9")
        )
        self.assertTrue(
            all(
                row["metric"] == "critical_it_mw"
                and row["stage"] == "planned"
                and row["unit"] == "MW"
                and row["low"] == row["base"] == row["high"]
                and "incremental in-progress fit-out" in row["notes"]
                and "not built capacity" in row["notes"]
                for row in new_capacity_rows
            )
        )

        previous_evidence = row_set(PREVIOUS_RELEASE / "evidence.csv")
        new_evidence = [
            row
            for row in rows(RELEASE / "evidence.csv")
            if tuple(sorted(row.items())) not in previous_evidence
        ]
        self.assertEqual(len(new_evidence), 1)
        self.assertEqual(new_evidence[0]["publisher"], "NEXTDC")
        self.assertEqual(new_evidence[0]["kind"], "company_disclosure")
        self.assertEqual(
            new_evidence[0]["source_family"], "nextdc_asx_results_presentations"
        )
        self.assertEqual(
            new_evidence[0]["content_hash"],
            "0ad1f17697c1c812be0c6db55722ea7e335fb5299d7de6f67c261d1f6b8573ec",
        )

        previous_pipeline = row_set(PREVIOUS_RELEASE / "construction_pipeline.csv")
        new_pipeline = [
            row
            for row in rows(RELEASE / "construction_pipeline.csv")
            if tuple(sorted(row.items())) not in previous_pipeline
        ]
        self.assertEqual(len(new_pipeline), 14)
        self.assertEqual({row["stable_key"] for row in new_pipeline}, NEW_PROJECT_KEYS)

        previous_signals = row_set(
            PREVIOUS_RELEASE / "construction_source_signals.csv"
        )
        new_signals = [
            row
            for row in rows(RELEASE / "construction_source_signals.csv")
            if tuple(sorted(row.items())) not in previous_signals
        ]
        self.assertEqual(len(new_signals), 1)
        self.assertEqual(new_signals[0]["affected_entity_count"], "14")
        affected = json.loads(new_signals[0]["affected_entities_json"])
        self.assertEqual({item["stable_key"] for item in affected}, NEW_PROJECT_KEYS)
        self.assertEqual(
            sum(item["status"] == "mep_electrical" for item in affected), 12
        )
        self.assertEqual(
            sum(item["status"] == "site_preparation" for item in affected), 2
        )


if __name__ == "__main__":
    unittest.main()
