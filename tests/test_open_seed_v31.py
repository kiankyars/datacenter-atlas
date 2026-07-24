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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v31.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v31"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v30.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v30"

DEFINITION_SHA256 = "15d5d8a29b2a1cef0a8cbfa1f24276ea5619f9811aab53959bf83cfb3b5050dd"
MANIFEST_SHA256 = "f81df7005c17ee75ab09ff8e81d86589ad64bfe75164b10b5c643cc14d55f2ea"
PREVIOUS_DEFINITION_SHA256 = (
    "b89c7414fe9a96ddd2acfff766386dda514d61278dae039d1d70eb490340ef12"
)
PREVIOUS_MANIFEST_SHA256 = (
    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
)
RECORDED_AT = "2026-07-19T21:30:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-keppel-floating-data-centre-singapore.json": (
        "f253e99b499cc59d1644e6a2d7f05e6492ae8f59f519f8e0621ac6c1bbd41307"
    ),
    "curated-official-2026-07-19-lt-vyoma-mahape-data-centre.json": (
        "c2300cb3e2318d0274931ff22d95fb1180640857cb27a5f4a3fe42b254e1ac41"
    ),
    "curated-official-2026-07-19-servpac-mtp-building-2.json": (
        "62aceebde60970056a43296cb1e9fd556f88eaeaa15bd2b054b35bfe431b3eb4"
    ),
    "curated-official-2026-07-19-telehouse-west-two.json": (
        "475dd37080fb70be5e078072b21c060ee389856a298a3fb9c98b00ed7ee4ff1d"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_lt_vyoma_keppel_fdc.py": (
        "6650170c77bbba9d4efb55dd3bdf58015d3293485fbd2d59c3d460c43ac45dda"
    ),
    "test_curated_servpac_telehouse.py": (
        "b358e0e45f30086f7dd53b537ad5df2424ccaf79254d60c2e59fe65086178245"
    ),
}
EVIDENCE_CONTENT_HASHES = {
    "4b8f55e3428e065a1105956c6c8af021c3f35d3c333599bdedfc6c4f9eec7970",
    "752202cb9bea8b8816c088a7befea2271b07420129eaa42ed63744e9037a75d6",
    "834831ef3acd96c46b4e162903efe5ab2ec9daa6e9e1b28083626b2838bd3cd4",
    "c4a5db59ac474e4c3624feae85a78677ba0502a19f9f8b9cbbff923977f147f0",
    "cc7562b60f8fe7daeaf98e384b314143e92bea8575e289fe0a9afb9b9461b0b4",
}
STATUS_CONTENT_HASHES = EVIDENCE_CONTENT_HASHES - {
    "cc7562b60f8fe7daeaf98e384b314143e92bea8575e289fe0a9afb9b9461b0b4"
}
NEW_SOURCE_FAMILIES = {
    "keppel_media",
    "larsen_toubro_press_releases",
    "servpac_press_releases",
    "telehouse_news",
}
CAMPUS_KEYS = {
    "curated:keppel-floating-data-centre-singapore",
    "curated:lt-vyoma-mahape-data-centre-campus",
    "curated:servpac-mtp-data-center-campus",
    "curated:telehouse-london-docklands-campus",
}
PROJECT_KEYS = {
    "curated:keppel-floating-data-centre-singapore:current-project",
    "curated:lt-vyoma-mahape-data-centre-campus:current-facility-build",
    "curated:servpac-mtp-data-center-campus:building-2",
    "curated:telehouse-london-docklands-campus:west-two",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS


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


class OpenSeedV31Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertTrue(entries)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in entries))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries))
        frozen = {path.name: path.read_bytes() for path in entries}

        offline = AssertionError("offline validator attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first = validate_open_seed_release(DEFINITION, RELEASE)
            self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
            second = validate_open_seed_release(DEFINITION, RELEASE)

        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 356)
        self.assertEqual(first["entities_by_kind"], {"campus": 209, "project": 147})
        self.assertEqual(first["evidence_records"], 220)
        self.assertEqual(first["capacity_estimates"], 401)
        self.assertEqual(first["construction_pipeline_records"], 188)
        self.assertEqual(first["construction_source_signals"], 157)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 356)
        self.assertEqual(summary["projects_total"], 147)
        self.assertEqual(summary["evidence_total"], 244)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 120)
        self.assertEqual(summary["entities_by_country"]["India"], 6)
        self.assertEqual(summary["entities_by_country"]["Singapore"], 4)
        self.assertEqual(summary["entities_by_country"]["United Kingdom"], 15)
        self.assertEqual(summary["entities_by_country"]["United States"], 159)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4874.6, "count": 45, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["grid_connection_mw"]["contracted"],
            {"base": 2560.0, "count": 5, "unit": "MW"},
        )

    def test_v30_closure_is_sealed_and_v31_is_exactly_four_inputs_additive(self) -> None:
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
            "evidence.csv": 5,
            "capacity_estimates.csv": 0,
            "construction_pipeline.csv": 4,
            "construction_source_signals.csv": 4,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            self.assertTrue(
                row_set(PREVIOUS_RELEASE / filename) <= row_set(RELEASE / filename),
                filename,
            )
            self.assertEqual(
                len(rows(RELEASE / filename)) - len(rows(PREVIOUS_RELEASE / filename)),
                expected_delta,
                filename,
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
            {key: current_features[key] for key in previous_features}, previous_features
        )
        self.assertEqual(set(current_features) - set(previous_features), NEW_ENTITY_KEYS)

        for filename in (
            "capacity_estimates.csv",
            "resolution_candidates.csv",
            "resolution_candidates.json",
        ):
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
        previous_records = {json.dumps(record, sort_keys=True) for record in previous_sources}
        added_sources = [
            record
            for record in current_sources
            if json.dumps(record, sort_keys=True) not in previous_records
        ]
        self.assertEqual(len(added_sources), 5)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EVIDENCE_CONTENT_HASHES,
        )

        previous_manifest = json.loads(
            (PREVIOUS_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        current_manifest = json.loads(
            (RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(current_manifest["source_families"])
            - set(previous_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 5)

        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_inputs = {
            (record["path"], record["sha256"]) for record in previous["curated_inputs"]
        }
        current_inputs = {
            (record["path"], record["sha256"]) for record in current["curated_inputs"]
        }
        expected_additions = {
            (f"sources/{filename}", digest) for filename, digest in SOURCE_HASHES.items()
        }
        self.assertEqual(len(previous_inputs), 146)
        self.assertEqual(len(current_inputs), 150)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v31")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in set(previous) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], previous[key], key)

    def test_sources_preserve_metadata_only_scale_and_classification(self) -> None:
        for filename, expected_hash in TRANCHE_TEST_HASHES.items():
            self.assertEqual(
                hashlib.sha256((ROOT / "tests" / filename).read_bytes()).hexdigest(),
                expected_hash,
            )

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        inputs = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents: dict[str, dict[str, object]] = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(inputs[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            documents[document["campus"]["stable_key"]] = document
            self.assertEqual(
                set(document),
                {
                    "campus",
                    "capacities",
                    "evidence",
                    "lifecycle",
                    "operating_models",
                    "project",
                    "schema_version",
                    "workloads",
                },
            )
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            self.assertEqual(document["lifecycle"][0]["value"], "under_construction")

        self.assertEqual(set(documents), CAMPUS_KEYS)
        self.assertEqual(
            {
                document["project"]["stable_key"]
                for document in documents.values()
            },
            PROJECT_KEYS,
        )
        self.assertEqual(
            {
                evidence["content_hash"]
                for document in documents.values()
                for evidence in document["evidence"]
            },
            EVIDENCE_CONTENT_HASHES,
        )

        lt = documents["curated:lt-vyoma-mahape-data-centre-campus"]
        lt_metadata = lt["evidence"][0]["metadata"]
        self.assertEqual(
            lt_metadata["current_facility_scale_wording_as_reported"],
            "upcoming 40 MW green, AI-ready data centre",
        )
        self.assertEqual(
            lt_metadata["planned_campus_scale_wording_as_reported"],
            "100 MW data centre campus planned in the city",
        )
        self.assertEqual(
            lt_metadata["india_roadmap_scale_wording_as_reported"],
            "over 200 MW of capacity across India",
        )
        self.assertNotIn("BOM02", lt["campus"]["name"] + lt["project"]["name"])

        keppel = documents["curated:keppel-floating-data-centre-singapore"]
        keppel_evidence = {
            evidence["content_hash"]: evidence for evidence in keppel["evidence"]
        }
        historical = keppel_evidence[
            "cc7562b60f8fe7daeaf98e384b314143e92bea8575e289fe0a9afb9b9461b0b4"
        ]["metadata"]
        construction = keppel_evidence[
            "c4a5db59ac474e4c3624feae85a78677ba0502a19f9f8b9cbbff923977f147f0"
        ]["metadata"]
        self.assertEqual(historical["reported_fdc_scale_mw"], 25)
        self.assertIn("no normalized capacity", historical["capacity_metric_guardrail"])
        self.assertIn("future tense", construction["sgp9_exclusion_guardrail"])
        self.assertNotIn(
            "sgp9",
            (keppel["campus"]["stable_key"] + keppel["project"]["stable_key"]).lower(),
        )

        servpac = documents["curated:servpac-mtp-data-center-campus"]
        servpac_metadata = servpac["evidence"][0]["metadata"]
        self.assertEqual(servpac_metadata["reported_added_floor_area_sqft_minimum"], 15500)
        self.assertEqual(servpac_metadata["reported_facility_size_increase_percent"], 50)
        self.assertEqual(servpac_metadata["reported_additional_land_acres"], 5)
        self.assertEqual(servpac_metadata["reported_project_investment_usd"], 13000000)
        self.assertIn("no normalized capacity", servpac_metadata["scale_guardrail"])

        telehouse = documents["curated:telehouse-london-docklands-campus"]
        telehouse_metadata = telehouse["evidence"][0]["metadata"]
        self.assertEqual(telehouse_metadata["reported_building_storeys"], 9)
        self.assertEqual(telehouse_metadata["reported_white_space_levels"], 6)
        self.assertEqual(telehouse_metadata["reported_building_capacity_mw"], 33)
        self.assertEqual(telehouse_metadata["reported_floor_power_capacity_mw_maximum"], 4.4)
        self.assertIn("not multiplied or summed", telehouse_metadata["capacity_metric_guardrail"])

    def test_export_adds_only_generic_status_without_typed_inferences(self) -> None:
        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertFalse(
                any(name.startswith("role:") for name in json.loads(row["tags_json"]))
            )
        for key in CAMPUS_KEYS:
            self.assertEqual(entity_rows[key]["status"], "")
        for key in PROJECT_KEYS:
            self.assertEqual(entity_rows[key]["status"], "under_construction")
            self.assertEqual(
                entity_rows[key]["status_method"], "authoritative_construction_start"
            )

        self.assertEqual(added_rows("capacity_estimates.csv"), [])
        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 4)
        self.assertEqual(
            {signal["source_content_hash"] for signal in added_signals},
            STATUS_CONTENT_HASHES,
        )
        self.assertEqual(
            {
                entity["stable_key"]
                for signal in added_signals
                for entity in json.loads(signal["affected_entities_json"])
            },
            PROJECT_KEYS,
        )
        self.assertTrue(all(signal["affected_entity_count"] == "1" for signal in added_signals))
        added_evidence = added_rows("evidence.csv")
        self.assertEqual(len(added_evidence), 5)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence}, EVIDENCE_CONTENT_HASHES
        )


if __name__ == "__main__":
    unittest.main()
