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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v22.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v22"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v21.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v21"

DEFINITION_SHA256 = "00e22edf84e73913c3e98f72b47a1f5c4a7bd792c0fd558b2cc2a48d95fd8b84"
MANIFEST_SHA256 = "21f0d4b98f01573fe7f9f4a5bc4dc0e2b2595d57863bfc349bd101e5b0bf2316"
PREVIOUS_DEFINITION_SHA256 = (
    "4192fb1b2366f5fa86bbcc3ed57037a8c174755454da3b834ea08dadf6ed22f6"
)
PREVIOUS_MANIFEST_SHA256 = (
    "08c12b7f26aa7a95a7620ac6e6733f1a83e73189cd77132a3046fe2dcd4795c0"
)
RECORDED_AT = "2026-07-19T20:41:39Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-ada-gru10-franco-da-rocha.json": (
        "28f9794c82b0eb9d0eb4a36b75a71402e9d0835bca080693512978fe0503eda2"
    ),
    "curated-official-2026-07-19-airtel-nxtra-eko-atlantic-lagos.json": (
        "a02fe6b1a64c2db1bd9e42a137c696fb9019dce2da8f5c5b7a15723665895850"
    ),
    "curated-official-2026-07-19-airtel-nxtra-tatu-city-kenya.json": (
        "2f5b90543ae83a53181f19b491981140dc5f8dd3b85141058f47a004a658bc45"
    ),
    "curated-official-2026-07-19-meeza-mvault6-um-garn.json": (
        "7c1b94944516e860b704e0a48891a9cdc62cfdae6cd6dc258bb82bed7bcf1c00"
    ),
    "curated-official-2026-07-19-sdaia-hexagon-riyadh.json": (
        "73d7ca1c5d5ecdfd187c03457b421b2ef4e13a2b9ef305899e1b2ffb383c9ed8"
    ),
}

TRANCHE_TEST_HASHES = {
    "test_curated_ada_gru10.py": (
        "2424a9872833a4f074d79eb535bc39a5847515f929b8cb59ba18a2d27782457c"
    ),
    "test_curated_airtel_africa_current.py": (
        "363573b3e2730188d1b400d9e28fade341dff190e801fd4d4d1a8a37f53f3664"
    ),
    "test_curated_meeza_mvault6.py": (
        "a55a232fb003cf5dc272ed3a0f360f76a07403898f60c3c16b171b8382b5d5de"
    ),
    "test_curated_sdaia_hexagon.py": (
        "c1467e8bad9806e6fb4b65e5926e3846e9efcafbf75ac2d1dc1dce3a065b6bc4"
    ),
}

EVIDENCE_CONTENT_HASHES = {
    "8abe8623782f6f6a096ca7d8ecf9508a51fa545cfd8443b30cc3e65a80985ee7",
    "b5199caaab2bed3dbe94466d99c815b4f25ff5ef35d97babd41df2b6f41020cf",
    "db9408e1ad1730ebff2308429b348b12cc2b93bca01a02f6735376571d8fae5a",
    "ede627f1dcba0e0e832d83e78bdbcff36e2e1d52cbd9851a5f267d816a7af064",
}

CAMPUS_KEYS = {
    "curated:ada-gru10-franco-da-rocha-campus",
    "curated:meeza-mvault6-um-garn-campus",
    "curated:nxtra-eko-atlantic-lagos-data-center",
    "curated:nxtra-tatu-city-kenya-data-center",
    "curated:sdaia-hexagon-riyadh-government-data-center",
}
PROJECT_KEYS = {
    "curated:ada-gru10-franco-da-rocha-campus:phase-1",
    "curated:meeza-mvault6-um-garn-campus:current-campus-build",
    "curated:nxtra-eko-atlantic-lagos-data-center:current-facility-build",
    "curated:nxtra-tatu-city-kenya-data-center:current-facility-build",
    "curated:sdaia-hexagon-riyadh-government-data-center:current-facility-build",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
AIRTEL_PROJECT_KEYS = {
    "curated:nxtra-eko-atlantic-lagos-data-center:current-facility-build",
    "curated:nxtra-tatu-city-kenya-data-center:current-facility-build",
}


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


class OpenSeedV22Tests(unittest.TestCase):
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
        frozen_bytes = {path.name: path.read_bytes() for path in release_entries}

        offline = AssertionError("offline validator attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first = validate_open_seed_release(DEFINITION, RELEASE)
            self.assertEqual(
                {path.name: path.read_bytes() for path in release_entries}, frozen_bytes
            )
            second = validate_open_seed_release(DEFINITION, RELEASE)

        self.assertEqual(first, second)
        self.assertEqual(
            {path.name: path.read_bytes() for path in release_entries}, frozen_bytes
        )
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 300)
        self.assertEqual(first["entities_by_kind"], {"campus": 181, "project": 119})
        self.assertEqual(first["evidence_records"], 190)
        self.assertEqual(first["capacity_estimates"], 393)
        self.assertEqual(first["construction_pipeline_records"], 160)
        self.assertEqual(first["construction_source_signals"], 132)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 300)
        self.assertEqual(summary["projects_total"], 119)
        self.assertEqual(summary["evidence_total"], 209)
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
                "under_construction": 96,
            },
        )
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4704.6, "count": 40, "unit": "MW"},
        )

    def test_v21_closure_is_sealed_and_v22_is_exactly_five_inputs_additive(self) -> None:
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
            "evidence.csv": 4,
            "capacity_estimates.csv": 0,
            "construction_pipeline.csv": 5,
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
            EVIDENCE_CONTENT_HASHES,
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads(
            (RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            current_summary["evidence_total"] - previous_summary["evidence_total"],
            4,
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
        self.assertEqual(len(previous_inputs), 117)
        self.assertEqual(len(current_inputs), 122)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v22")

    def test_new_sources_and_rows_preserve_only_audited_semantics(self) -> None:
        for filename, expected_hash in TRANCHE_TEST_HASHES.items():
            test_path = ROOT / "tests" / filename
            self.assertEqual(
                hashlib.sha256(test_path.read_bytes()).hexdigest(), expected_hash
            )

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents: dict[str, dict[str, object]] = {}
        evidence_by_key: dict[str, str] = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(input_by_name[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            documents[filename] = document
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
            lifecycle = document["lifecycle"][0]
            self.assertEqual(lifecycle["entity"], "project")
            self.assertEqual(lifecycle["value"], "under_construction")
            self.assertEqual(len(document["evidence"]), 1)
            evidence = document["evidence"][0]
            serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
            if evidence["key"] in evidence_by_key:
                self.assertEqual(evidence_by_key[evidence["key"]], serialized)
            else:
                evidence_by_key[evidence["key"]] = serialized

        self.assertEqual(
            {document["campus"]["stable_key"] for document in documents.values()},
            CAMPUS_KEYS,
        )
        self.assertEqual(
            {document["project"]["stable_key"] for document in documents.values()},
            PROJECT_KEYS,
        )
        self.assertEqual(len(evidence_by_key), 4)
        self.assertEqual(
            {
                evidence["content_hash"]
                for document in documents.values()
                for evidence in document["evidence"]
            },
            EVIDENCE_CONTENT_HASHES,
        )
        self.assertEqual(
            documents[
                "curated-official-2026-07-19-airtel-nxtra-tatu-city-kenya.json"
            ]["evidence"],
            documents[
                "curated-official-2026-07-19-airtel-nxtra-eko-atlantic-lagos.json"
            ]["evidence"],
        )

        sdaia = documents[
            "curated-official-2026-07-19-sdaia-hexagon-riyadh.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(sdaia["reported_total_capacity_mw"], 480)
        self.assertEqual(sdaia["reported_area_lower_bound_square_feet"], 30_000_000)
        self.assertIn("untyped evidence metadata", sdaia["capacity_metric_guardrail"])

        airtel = documents[
            "curated-official-2026-07-19-airtel-nxtra-tatu-city-kenya.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(
            (airtel["kenya_reported_capacity_mw"], airtel["lagos_reported_capacity_mw"]),
            (44, 38),
        )
        self.assertIn("untyped evidence metadata", airtel["capacity_metric_guardrail"])
        self.assertEqual(airtel["kenya_commissioning_forecast_as_reported"], "first quarter of 2027")
        self.assertIn("future forecast", airtel["forecast_guardrail"])

        meeza = documents[
            "curated-official-2026-07-19-meeza-mvault6-um-garn.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(
            (meeza["reported_campus_scale_mw"], meeza["reported_first_operational_increment_mw"]),
            (24, 6),
        )
        self.assertIn("untyped evidence metadata", meeza["capacity_metric_guardrail"])
        self.assertEqual(meeza["first_increment_timing_as_reported"], "planned to be operational by the end of 2027")
        self.assertIn("future forecast", meeza["forecast_guardrail"])

        ada = documents[
            "curated-official-2026-07-19-ada-gru10-franco-da-rocha.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(ada["reported_onsite_substation_total_capacity_mw"], 300)
        self.assertIn("creates no normalized capacity row", ada["capacity_metric_guardrail"])
        self.assertIn("future construction forecast", ada["forecast_guardrail"])

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
            self.assertEqual(row["capacity_estimates_json"], "[]")
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

        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 4)
        affected_keys = []
        for signal in added_signals:
            affected = json.loads(signal["affected_entities_json"])
            self.assertEqual(int(signal["affected_entity_count"]), len(affected))
            affected_keys.extend(entity["stable_key"] for entity in affected)
        self.assertEqual(set(affected_keys), PROJECT_KEYS)
        self.assertEqual(len(affected_keys), len(PROJECT_KEYS))

        airtel_signals = [
            signal
            for signal in added_signals
            if signal["source_content_hash"]
            == "ede627f1dcba0e0e832d83e78bdbcff36e2e1d52cbd9851a5f267d816a7af064"
        ]
        self.assertEqual(len(airtel_signals), 1)
        airtel_signal = airtel_signals[0]
        self.assertEqual(airtel_signal["affected_entity_count"], "2")
        self.assertEqual(
            {
                entity["stable_key"]
                for entity in json.loads(airtel_signal["affected_entities_json"])
            },
            AIRTEL_PROJECT_KEYS,
        )

        added_evidence = added_rows("evidence.csv")
        self.assertEqual(len(added_evidence), 4)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence},
            EVIDENCE_CONTENT_HASHES,
        )


if __name__ == "__main__":
    unittest.main()
