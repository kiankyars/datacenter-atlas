from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v18.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v18"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v17.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v17"
TRANCHE_TEST = ROOT / "tests" / "test_curated_asia_official_next_tranche.py"

DEFINITION_SHA256 = "afef922eb287cef0cfcaef49ae46da2df150e99875e93b56c0dc38c06f182064"
MANIFEST_SHA256 = "913971bbc966fb7f8f62d31f8ba79d236c5f6ff982170733f59d89f95a11a868"
PREVIOUS_DEFINITION_SHA256 = (
    "27b5ffa3cbe6442435e5b474d957490a761a75db841d0824cdd030684c962f01"
)
PREVIOUS_MANIFEST_SHA256 = (
    "eb6d8e06d1989afc487291572083c8c0530b72b860ca90b1e9d462620d5e6a94"
)
TRANCHE_TEST_SHA256 = (
    "1db04307edff9d82adb9c1b2f95aa177ffef0ec7ae70aa820e9d2ec9f1081b17"
)
RECORDED_AT = "2026-07-19T19:48:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-pdg-jc3-greater-jakarta.json": (
        "44bc4fe172ca53320994815f64b6080c2d339f39d7fc04ec9439d8e51c650303"
    ),
    "curated-official-2026-07-19-pdg-se1-incheon.json": (
        "3a68c5ff3c904bb30f4a03e24780b37a1598263b6cab0b34ae2c23cbb08ab419"
    ),
    "curated-official-2026-07-19-stt-bangkok-2.json": (
        "4b2cbca170c62bd8ae2e20034416af4f44fefc5948ceb465fbe542a2dcbe3aa3"
    ),
    "curated-official-2026-07-19-stt-jakarta-3.json": (
        "34f5383be85da949e2453dd1a211e546341535dff5281c87a45b130ddb6cb96f"
    ),
    "curated-official-2026-07-19-stt-jakarta-5.json": (
        "05c5198220c2f7616c715c566044c67776a135be7e99c3aa4ce543e5e951b258"
    ),
    "curated-official-2026-07-19-stt-jakarta-6.json": (
        "77e63e1cca648e4001d49ad44a35e73c0e33423f857f17c5e139eb7de29d3459"
    ),
}

CAMPUS_KEYS = {
    "curated:pdg-jc3-greater-jakarta-campus",
    "curated:pdg-se1-incheon-campus",
    "curated:stt-bangkok-data-centre-campus",
    "curated:stt-jakarta-data-centre-campus",
}

EXPECTED_PROJECTS = {
    "curated:pdg-jc3-greater-jakarta-campus:current-campus-build": (
        "under_construction",
        "2025-11-19",
        "authoritative_construction_start",
    ),
    "curated:pdg-se1-incheon-campus:se1-development": (
        "announced",
        "2025-11-17",
        "authoritative_announcement",
    ),
    "curated:stt-bangkok-data-centre-campus:stt-bangkok-2": (
        "under_construction",
        "2025-03-03",
        "authoritative_construction_start",
    ),
    "curated:stt-jakarta-data-centre-campus:stt-jakarta-3": (
        "shell",
        "2026-06-10",
        "authoritative_physical_status_update",
    ),
    "curated:stt-jakarta-data-centre-campus:stt-jakarta-5": (
        "under_construction",
        "2026-06-10",
        "authoritative_construction_start",
    ),
    "curated:stt-jakarta-data-centre-campus:stt-jakarta-6": (
        "under_construction",
        "2026-06-10",
        "authoritative_construction_start",
    ),
}

NEW_ENTITY_KEYS = CAMPUS_KEYS | set(EXPECTED_PROJECTS)

EXPECTED_CAPACITIES = {
    (
        "curated:stt-bangkok-data-centre-campus:stt-bangkok-2",
        "critical_it_mw",
        "planned",
        24.0,
        "2025-03-03",
    ),
    (
        "curated:stt-jakarta-data-centre-campus:stt-jakarta-3",
        "critical_it_mw",
        "planned",
        24.0,
        "2026-07-16",
    ),
    (
        "curated:stt-jakarta-data-centre-campus:stt-jakarta-5",
        "critical_it_mw",
        "planned",
        40.0,
        "2026-06-10",
    ),
    (
        "curated:stt-jakarta-data-centre-campus:stt-jakarta-6",
        "critical_it_mw",
        "planned",
        40.0,
        "2026-06-10",
    ),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class OpenSeedV18Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_exact_accounting(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(RELEASE.is_symlink())
        self.assertTrue(
            all(not candidate.is_symlink() for candidate in RELEASE.iterdir())
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
        self.assertEqual(first["entities"], 247)
        self.assertEqual(first["entities_by_kind"], {"campus": 155, "project": 92})
        self.assertEqual(first["evidence_records"], 178)
        self.assertEqual(first["capacity_estimates"], 379)
        self.assertEqual(first["construction_pipeline_records"], 133)
        self.assertEqual(first["construction_source_signals"], 121)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 247)
        self.assertEqual(summary["projects_total"], 92)
        self.assertEqual(summary["evidence_total"], 195)
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 3,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 3,
                "operational": 31,
                "permitted": 2,
                "shell": 4,
                "site_preparation": 6,
                "under_construction": 84,
            },
        )

    def test_v17_closure_is_sealed_and_v18_is_exactly_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 10,
            "evidence.csv": 5,
            "capacity_estimates.csv": 4,
            "construction_pipeline.csv": 6,
            "construction_source_signals.csv": 4,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous = rows(PREVIOUS_RELEASE / filename)
            current = rows(RELEASE / filename)
            self.assertTrue(
                row_set(PREVIOUS_RELEASE / filename) <= row_set(RELEASE / filename),
                filename,
            )
            self.assertEqual(len(current) - len(previous), expected_delta, filename)

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
        self.assertEqual(len(previous_inputs), 88)
        self.assertEqual(len(current_inputs), 94)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )
        self.assertGreater(
            parse_timestamp(current["build"]["recorded_at"]),
            parse_timestamp(previous["build"]["recorded_at"]),
        )

    def test_new_sources_and_rows_keep_accepted_semantics(self) -> None:
        self.assertEqual(
            hashlib.sha256(TRANCHE_TEST.read_bytes()).hexdigest(),
            TRANCHE_TEST_SHA256,
        )
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        release_recorded_at = parse_timestamp(definition["build"]["recorded_at"])
        documents = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
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
            for evidence in document["evidence"]:
                self.assertEqual(evidence["kind"], "company_disclosure")
                self.assertLess(
                    parse_timestamp(evidence["retrieved_at"]),
                    release_recorded_at,
                )

        self.assertEqual(documents[
            "curated-official-2026-07-19-pdg-jc3-greater-jakarta.json"
        ]["capacities"], [])
        self.assertEqual(documents[
            "curated-official-2026-07-19-pdg-se1-incheon.json"
        ]["capacities"], [])
        self.assertEqual(
            documents[
                "curated-official-2026-07-19-stt-jakarta-3.json"
            ]["evidence"][1]["metadata"]["design_pue_wording_as_reported"],
            "Design PUE of <1.30",
        )

        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {
            row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entities) - previous_keys, NEW_ENTITY_KEYS)
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

        for stable_key, (status, as_of, method) in EXPECTED_PROJECTS.items():
            entity = entities[stable_key]
            self.assertEqual(entity["status"], status)
            self.assertEqual(entity["status_as_of"], as_of)
            self.assertEqual(entity["status_method"], method)
        self.assertEqual(
            entities["curated:pdg-se1-incheon-campus:se1-development"]["status"],
            "announced",
        )

        entity_id_to_key = {
            row["entity_id"]: row["stable_key"] for row in entities.values()
        }
        observed_capacities = {
            (
                entity_id_to_key[row["entity_id"]],
                row["metric"],
                row["stage"],
                float(row["base"]),
                row["as_of_date"],
            )
            for row in rows(RELEASE / "capacity_estimates.csv")
            if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
        }
        self.assertEqual(observed_capacities, EXPECTED_CAPACITIES)
        self.assertTrue(
            all(
                row["metric"] == "critical_it_mw" and row["stage"] == "planned"
                for row in rows(RELEASE / "capacity_estimates.csv")
                if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
            )
        )

        previous_evidence = row_set(PREVIOUS_RELEASE / "evidence.csv")
        new_evidence = [
            row
            for row in rows(RELEASE / "evidence.csv")
            if tuple(sorted(row.items())) not in previous_evidence
        ]
        self.assertEqual(len(new_evidence), 5)
        self.assertEqual({row["kind"] for row in new_evidence}, {"company_disclosure"})
        self.assertNotIn("satellite_imagery", {row["kind"] for row in new_evidence})

        previous_signals = row_set(
            PREVIOUS_RELEASE / "construction_source_signals.csv"
        )
        new_signals = [
            row
            for row in rows(RELEASE / "construction_source_signals.csv")
            if tuple(sorted(row.items())) not in previous_signals
        ]
        self.assertEqual(len(new_signals), 4)
        affected = [json.loads(row["affected_entities_json"]) for row in new_signals]
        self.assertEqual(
            {
                item["stable_key"]
                for signal_entities in affected
                for item in signal_entities
            },
            set(EXPECTED_PROJECTS),
        )
        jakarta_signal = next(
            signal_entities
            for signal_entities in affected
            if {
                item["stable_key"] for item in signal_entities
            }
            == {
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-3",
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-5",
                "curated:stt-jakarta-data-centre-campus:stt-jakarta-6",
            }
        )
        self.assertEqual(len(jakarta_signal), 3)


if __name__ == "__main__":
    unittest.main()
