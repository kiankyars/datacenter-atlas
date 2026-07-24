from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v21.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v21"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v20.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v20"

DEFINITION_SHA256 = "4192fb1b2366f5fa86bbcc3ed57037a8c174755454da3b834ea08dadf6ed22f6"
MANIFEST_SHA256 = "08c12b7f26aa7a95a7620ac6e6733f1a83e73189cd77132a3046fe2dcd4795c0"
PREVIOUS_DEFINITION_SHA256 = (
    "099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd"
)
PREVIOUS_MANIFEST_SHA256 = (
    "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456"
)
TRANCHE_TEST_SHA256 = (
    "b7016a53bbfd43bd3ea62b139014a782be7b49c12322b2688b34a38ef1433a41"
)
RECORDED_AT = "2026-07-19T20:30:09Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-dayone-chonburi-ctp1.json": (
        "42cf9d67828563e92cc0b80ae30cfdf0d3a9849f19612b3ff7eaee4ee54889d4"
    ),
    "curated-official-2026-07-19-dayone-gaw-tokyo-phase-one.json": (
        "d2b4b73e1de5c61524af90d805e11c5a6a183949fbf90415d6fec96030d20529"
    ),
    "curated-official-2026-07-19-dayone-sg1-singapore.json": (
        "0ff2f288415ffab9aca036fb8c28cc8598cde1c14a12e0c33c8672caf16bfdd6"
    ),
    "curated-official-2026-07-19-pdg-jc4-greater-jakarta.json": (
        "de4e6ea4997d572d76701564602d185870e21e9e70902929d6d57132d0ca03d0"
    ),
}

CAMPUS_KEYS = {
    "curated:dayone-chonburi-tech-park-campus",
    "curated:dayone-gaw-fuchu-tokyo-data-center-campus",
    "curated:dayone-sg1-singapore-data-center",
    "curated:pdg-jc4-greater-jakarta-campus",
}
PROJECT_KEYS = {
    "curated:dayone-chonburi-tech-park-campus:ctp1-current-development",
    "curated:dayone-gaw-fuchu-tokyo-data-center-campus:phase-one-building",
    "curated:dayone-sg1-singapore-data-center:current-facility-build",
    "curated:pdg-jc4-greater-jakarta-campus:current-campus-build",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
TOKYO_PROJECT_KEY = (
    "curated:dayone-gaw-fuchu-tokyo-data-center-campus:phase-one-building"
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


def added_rows(filename: str) -> list[dict[str, str]]:
    previous = row_set(PREVIOUS_RELEASE / filename)
    return [
        row
        for row in rows(RELEASE / filename)
        if tuple(sorted(row.items())) not in previous
    ]


class OpenSeedV21Tests(unittest.TestCase):
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
        self.assertTrue(
            all(path.is_file() and not path.is_symlink() for path in release_entries)
        )
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
        self.assertEqual(first["entities"], 290)
        self.assertEqual(first["entities_by_kind"], {"campus": 176, "project": 114})
        self.assertEqual(first["evidence_records"], 186)
        self.assertEqual(first["capacity_estimates"], 393)
        self.assertEqual(first["construction_pipeline_records"], 155)
        self.assertEqual(first["construction_source_signals"], 128)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 290)
        self.assertEqual(summary["projects_total"], 114)
        self.assertEqual(summary["evidence_total"], 205)
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
                "shell": 5,
                "site_preparation": 8,
                "under_construction": 91,
            },
        )
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4704.6, "count": 40, "unit": "MW"},
        )

    def test_v20_closure_is_sealed_and_v21_is_exactly_four_inputs_additive(self) -> None:
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
            "evidence.csv": 4,
            "capacity_estimates.csv": 1,
            "construction_pipeline.csv": 4,
            "construction_source_signals.csv": 4,
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

        previous_geojson = json.loads(
            (PREVIOUS_RELEASE / "atlas.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (RELEASE / "atlas.geojson").read_text(encoding="utf-8")
        )
        previous_features = {
            feature["properties"]["stable_key"]: feature
            for feature in previous_geojson["features"]
        }
        current_features = {
            feature["properties"]["stable_key"]: feature
            for feature in current_geojson["features"]
        }
        self.assertEqual(
            {key: current_features[key] for key in previous_features},
            previous_features,
        )
        self.assertEqual(set(current_features) - set(previous_features), NEW_ENTITY_KEYS)

        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (PREVIOUS_RELEASE / filename).read_bytes(),
                filename,
            )

        previous_sources = json.loads(
            (PREVIOUS_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        current_sources = json.loads(
            (RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        previous_source_records = {
            json.dumps(record, sort_keys=True) for record in previous_sources
        }
        current_source_records = {
            json.dumps(record, sort_keys=True) for record in current_sources
        }
        self.assertTrue(previous_source_records <= current_source_records)
        added_source_records = [
            record
            for record in current_sources
            if json.dumps(record, sort_keys=True) not in previous_source_records
        ]
        self.assertEqual(len(added_source_records), 4)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_source_records},
            {
                "7e26ac51d2c22892ee65a5e8a5c5f170dea21ff50649800154c64006e17b6596",
                "d6677c822b4b8d9689cba36db7dd44ab23f85048eb8ea43ea04afbd2b423aa41",
                "c6080cd681de2fce2771cb466a2f945ed7da85213d0213f4aa778ae85a5dce1b",
                "2a55761f18d8bee2419528a3caf4281b3b4e49689033d13e1ee70acd8910aa5c",
            },
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads(
            (RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            current_summary["evidence_total"] - previous_summary["evidence_total"],
            5,
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
        self.assertEqual(len(previous_inputs), 113)
        self.assertEqual(len(current_inputs), 117)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v21")

    def test_new_sources_and_rows_preserve_only_audited_semantics(self) -> None:
        tranche_test = ROOT / "tests" / "test_curated_pdg_dayone_next_tranche.py"
        self.assertEqual(
            hashlib.sha256(tranche_test.read_bytes()).hexdigest(),
            TRANCHE_TEST_SHA256,
        )

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents: dict[str, dict[str, object]] = {}
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
            self.assertEqual(len(document["lifecycle"]), 1)
            lifecycle = document["lifecycle"][0]
            self.assertEqual(lifecycle["entity"], "project")
            self.assertEqual(lifecycle["value"], "under_construction")
            self.assertTrue(
                all(evidence["kind"] == "company_disclosure" for evidence in document["evidence"])
            )

        self.assertEqual(
            {document["campus"]["stable_key"] for document in documents.values()},
            CAMPUS_KEYS,
        )
        self.assertEqual(
            {document["project"]["stable_key"] for document in documents.values()},
            PROJECT_KEYS,
        )
        self.assertEqual(sum(len(document["evidence"]) for document in documents.values()), 5)

        capacities = [
            capacity
            for document in documents.values()
            for capacity in document["capacities"]
        ]
        self.assertEqual(len(capacities), 1)
        self.assertEqual(
            capacities[0],
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "low": 18.0,
                "base": 18.0,
                "high": 18.0,
                "unit": "MW",
                "evidence_key": (
                    "dayone-gaw-tokyo-phase-one-groundbreaking-2025-08-01-"
                    "captured-2026-07-19"
                ),
                "as_of_date": "2025-08-01",
                "target_date": None,
                "method": "reported",
                "confidence": 0.99,
                "notes": (
                    "Planned critical-IT capacity for only the Phase One building. "
                    "The 18 MW is nested within the source-reported 80 MW total IT "
                    "capacity for the full campus; the values are not additive. This "
                    "is not current load, operational capacity, gross facility power, "
                    "grid draw, generation, measured energy consumption, or proof of "
                    "shell completion or operation."
                ),
            },
        )

        pdg = documents[
            "curated-official-2026-07-19-pdg-jc4-greater-jakarta.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(
            (
                pdg["planned_capacity_as_reported_mw"],
                pdg["building_count_as_reported"],
                pdg["per_building_capacity_as_reported_mw"],
            ),
            (240, 4, 60),
        )
        self.assertIn("untyped evidence metadata", pdg["capacity_metric_guardrail"])

        sg1 = documents[
            "curated-official-2026-07-19-dayone-sg1-singapore.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(sg1["facility_capacity_as_reported_mw"], 20)
        self.assertIn("untyped evidence metadata", sg1["capacity_metric_guardrail"])

        tokyo = documents[
            "curated-official-2026-07-19-dayone-gaw-tokyo-phase-one.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(tokyo["campus_total_it_capacity_as_reported_mw"], 80)
        self.assertIn("double count", tokyo["campus_capacity_guardrail"])

        chonburi = documents[
            "curated-official-2026-07-19-dayone-chonburi-ctp1.json"
        ]["evidence"]
        self.assertEqual(chonburi[0]["metadata"]["ctp1_site_power_capacity_as_reported_mw"], 300)
        self.assertEqual(chonburi[0]["metadata"]["unified_power_platform_as_reported_gw"], 1)
        self.assertIn(
            "more than 100 MW",
            chonburi[1]["metadata"]["expected_it_capacity_inequality_as_reported"],
        )
        self.assertIn("inequality", chonburi[1]["metadata"]["capacity_guardrail"])

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {
            row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["geometry_json"], "null")
            self.assertFalse(
                any(name.startswith("role:") for name in json.loads(row["tags_json"]))
            )
        self.assertTrue(
            all(entity_rows[key]["status"] == "under_construction" for key in PROJECT_KEYS)
        )
        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        self.assertEqual(
            {
                row["representative_stable_key"]
                for row in added_rows("construction_source_signals.csv")
            },
            PROJECT_KEYS,
        )

        added_capacity = added_rows("capacity_estimates.csv")
        self.assertEqual(len(added_capacity), 1)
        self.assertEqual(added_capacity[0]["entity_id"], entity_rows[TOKYO_PROJECT_KEY]["entity_id"])
        self.assertEqual(
            (
                added_capacity[0]["metric"],
                added_capacity[0]["stage"],
                added_capacity[0]["unit"],
                added_capacity[0]["low"],
                added_capacity[0]["base"],
                added_capacity[0]["high"],
                added_capacity[0]["method"],
                added_capacity[0]["as_of_date"],
                added_capacity[0]["target_date"],
            ),
            (
                "critical_it_mw",
                "planned",
                "MW",
                "18.0",
                "18.0",
                "18.0",
                "reported",
                "2025-08-01",
                "",
            ),
        )

        added_evidence = added_rows("evidence.csv")
        self.assertEqual(len(added_evidence), 4)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence},
            {
                "7e26ac51d2c22892ee65a5e8a5c5f170dea21ff50649800154c64006e17b6596",
                "d6677c822b4b8d9689cba36db7dd44ab23f85048eb8ea43ea04afbd2b423aa41",
                "c6080cd681de2fce2771cb466a2f945ed7da85213d0213f4aa778ae85a5dce1b",
                "2a55761f18d8bee2419528a3caf4281b3b4e49689033d13e1ee70acd8910aa5c",
            },
        )


if __name__ == "__main__":
    unittest.main()
