from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v15.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v15"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v14.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v14"
DEFINITION_SHA256 = "e876884407f66524c6881869100175749f29c60648acec5c3ba9f8f14f7e8b36"
MANIFEST_SHA256 = "0ece037ba1b894b8153808393980deaba0d56b3c4541e279950e8e9f2c52e0a0"
PREVIOUS_DEFINITION_SHA256 = (
    "897773e8fbba40e7fe69ce1c6ad79f8881981ef9d3cc034d33d3cc93d30296f1"
)
PREVIOUS_MANIFEST_SHA256 = (
    "64b0524897777915fcb43334a85dc5c9605f95f141257a521396be32a71be568"
)

SOURCE_HASHES = {
    "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json": (
        "ddeecf7811dd1d2c792e40813f9ebf07d35a37f79f50e236f5c3329ba06baa39"
    ),
    "curated-official-2026-07-19-edgeconnex-greater-osaka.json": (
        "ed5be494f24ace21d8d87c947ee3a5ebd04cb59020c0e79d0874296baec7122d"
    ),
    "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json": (
        "817a653cd86ca0e1dbacb84a3cdd7730597a657395623c2fe21896f781dae6cc"
    ),
    "curated-official-2026-07-19-vantage-lighthouse-port-washington.json": (
        "8be2fde23880e8f9f271de1213cc04bf20fb549d8e48ff11c889d213687ab138"
    ),
}

EXCLUDED_INPUT_NAMES = {
    "curated-official-2026-07-19-meta-sturgeon-county-alberta.json",
    "curated-official-2026-07-19-vantage-frontier-shackelford.json",
}

NEW_ENTITY_KEYS = {
    "curated:digital-realty-digital-dulles-campus",
    "curated:digital-realty-digital-dulles-campus:current-96mw-development",
    "curated:edgeconnex-greater-osaka-campus",
    "curated:edgeconnex-greater-osaka-campus:current-campus-development",
    "curated:oracle-project-jupiter-dona-ana-campus",
    "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build",
    "curated:vantage-lighthouse-port-washington-campus",
    "curated:vantage-lighthouse-port-washington-campus:current-campus-build",
}

EXPECTED_STATUSES = {
    "curated:digital-realty-digital-dulles-campus:current-96mw-development": (
        "under_construction",
        "2026-06-29",
        "authoritative_physical_status_update",
    ),
    "curated:edgeconnex-greater-osaka-campus:current-campus-development": (
        "under_construction",
        "2026-03-17",
        "authoritative_construction_start",
    ),
    "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build": (
        "under_construction",
        "2026-05-27",
        "authoritative_physical_status_update",
    ),
    "curated:vantage-lighthouse-port-washington-campus:current-campus-build": (
        "under_construction",
        "2026-06-12",
        "authoritative_physical_status_update",
    ),
}

EXPECTED_CAPACITIES = {
    (
        "curated:digital-realty-digital-dulles-campus:current-96mw-development",
        "critical_it_mw",
        "planned",
        96.0,
    ),
    (
        "curated:oracle-project-jupiter-dona-ana-campus",
        "generation_nameplate_mw",
        "planned",
        2450.0,
    ),
    (
        "curated:vantage-lighthouse-port-washington-campus",
        "critical_it_mw",
        "planned",
        902.0,
    ),
}

EXPECTED_WORKLOADS = {
    "curated:oracle-project-jupiter-dona-ana-campus": "ai_specialized_unspecified",
    "curated:vantage-lighthouse-port-washington-campus": (
        "ai_specialized_unspecified"
    ),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


class OpenSeedV15Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_exact_accounting(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
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
        self.assertEqual(first["recorded_at"], "2026-07-19T18:40:00Z")
        self.assertEqual(first["entities"], 219)
        self.assertEqual(first["entities_by_kind"], {"campus": 142, "project": 77})
        self.assertEqual(first["evidence_records"], 162)
        self.assertEqual(first["capacity_estimates"], 372)
        self.assertEqual(first["construction_pipeline_records"], 118)
        self.assertEqual(first["construction_source_signals"], 108)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 219)
        self.assertEqual(summary["projects_total"], 77)
        self.assertEqual(summary["evidence_total"], 178)
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 2,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 3,
                "operational": 31,
                "permitted": 2,
                "shell": 3,
                "site_preparation": 6,
                "under_construction": 71,
            },
        )

    def test_v14_closure_is_sealed_and_v15_is_exactly_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 8,
            "evidence.csv": 6,
            "capacity_estimates.csv": 3,
            "construction_pipeline.csv": 4,
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
        self.assertEqual(len(previous_inputs), 75)
        self.assertEqual(len(current_inputs), 79)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )
        input_names = {Path(path).name for path, _ in current_inputs}
        self.assertEqual(input_names & EXCLUDED_INPUT_NAMES, set())

    def test_new_sources_and_rows_keep_narrow_semantics(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(input_by_name[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["operating_models"], [])

        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(NEW_ENTITY_KEYS - set(entities), set())
        for stable_key in NEW_ENTITY_KEYS:
            entity = entities[stable_key]
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual(
                (entity["owner"], entity["operator"], entity["users"]),
                ("", "", ""),
            )
            self.assertEqual(entity["operating_model"], "")

        for stable_key, (status, as_of, method) in EXPECTED_STATUSES.items():
            entity = entities[stable_key]
            self.assertEqual(entity["status"], status)
            self.assertEqual(entity["status_as_of"], as_of)
            self.assertEqual(entity["status_method"], method)
            self.assertNotIn(status, {"commissioning", "operational"})

        entity_id_to_key = {
            row["entity_id"]: row["stable_key"] for row in entities.values()
        }
        observed_capacities = {
            (
                entity_id_to_key[row["entity_id"]],
                row["metric"],
                row["stage"],
                float(row["base"]),
            )
            for row in rows(RELEASE / "capacity_estimates.csv")
            if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
        }
        self.assertEqual(observed_capacities, EXPECTED_CAPACITIES)
        self.assertTrue(
            all(
                metric in {"critical_it_mw", "generation_nameplate_mw"}
                and stage == "planned"
                for _, metric, stage, _ in observed_capacities
            )
        )

        observed_workloads = {}
        for stable_key in NEW_ENTITY_KEYS:
            workloads = json.loads(entities[stable_key]["workloads_json"])
            if workloads:
                self.assertEqual(len(workloads), 1)
                observed_workloads[stable_key] = workloads[0]["workload"]
        self.assertEqual(observed_workloads, EXPECTED_WORKLOADS)


if __name__ == "__main__":
    unittest.main()
