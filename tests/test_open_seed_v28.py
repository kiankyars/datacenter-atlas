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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v28.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v28"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v27.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v27"

DEFINITION_SHA256 = "77777bbe26c8e5de198ab60f39eb83175dae5eb4bb5dfd0bdf84d7ef79e97733"
MANIFEST_SHA256 = "651916a393f50c7bb8e4179c139373585a41caa3099cdb03b1bd6378533326ec"
PREVIOUS_DEFINITION_SHA256 = (
    "2066d3ce841321ab647933596e5ee485286c96d5e3eb893dfe320e52634388fc"
)
PREVIOUS_MANIFEST_SHA256 = (
    "f02bc8b60c84570aca28b435d29d8d14e89a5873e79bcc56a09c2903a445b1b0"
)
RECORDED_AT = "2026-07-19T21:15:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-bitdeer-fox-creek-alberta.json": (
        "6cbe4fb717074b711d244cc02b5b559a770f0a7911af362f5cfe789394186734"
    ),
    "curated-official-2026-07-19-firstcolo-fra7-rosbach.json": (
        "8df80cdc203f714795495b13ffd2bbf35d846da9ed4350f3ad657bb6af64d707"
    ),
    "curated-official-2026-07-19-pure-dc-brent-cross-lon01-b2.json": (
        "792dc6b6db721fd7efd4bf00493b6546264acfe8a563b6b4ad222be282834c1d"
    ),
    "curated-official-2026-07-19-tm-nxera-iskandar-puteri-first-building.json": (
        "e6b14f5c9216671dfcd0ae182d0fc2c4b43fe2e39f5db177e806d66331cb84f0"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_bitdeer_puredc_nxera_firstcolo.py": (
        "28520b49da00d0b627f809fea620d6e3b31afcee9c5c4339b6db48c1916aa15f"
    ),
}
EVIDENCE_CONTENT_HASHES = {
    "06e2eb9a4c4476501a8f8182e6baa9d1eaedcdc11f8c2eaf04a5e8f3465aebd0",
    "6c3cdc34dc3acb8521e7a983f0c585f0c6471fb3564b5f116d368539ce6e6899",
    "79d293abb6590f7321e8bee14f1adc732a171e774d2589bb94be1843df21acf0",
    "c129305ab7980df1d4e46272c57a0f9c2dd05dbf0e25bd021d9ae420fc537c34",
}
CAMPUS_KEYS = {
    "curated:bitdeer-fox-creek-alberta-campus",
    "curated:firstcolo-fra7-rosbach-campus",
    "curated:pure-dc-brent-cross-lon01-campus",
    "curated:tm-nxera-iskandar-puteri-johor-campus",
}
PROJECT_KEYS = {
    "curated:bitdeer-fox-creek-alberta-campus:integrated-facility-current-build",
    "curated:firstcolo-fra7-rosbach-campus:fra7-current-build",
    "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build",
    "curated:tm-nxera-iskandar-puteri-johor-campus:first-building",
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


class OpenSeedV28Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
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
        self.assertEqual(first["entities"], 340)
        self.assertEqual(first["entities_by_kind"], {"campus": 201, "project": 139})
        self.assertEqual(first["evidence_records"], 209)
        self.assertEqual(first["capacity_estimates"], 398)
        self.assertEqual(first["construction_pipeline_records"], 180)
        self.assertEqual(first["construction_source_signals"], 149)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 340)
        self.assertEqual(summary["projects_total"], 139)
        self.assertEqual(summary["evidence_total"], 233)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 112)
        self.assertEqual(summary["entities_by_status"]["site_preparation"], 9)
        self.assertEqual(summary["entities_by_status"]["permitted"], 3)
        self.assertEqual(summary["entities_by_status"]["proposed"], 1)
        self.assertEqual(summary["entities_by_status"]["shell"], 6)
        self.assertEqual(summary["entities_by_country"]["Canada"], 4)
        self.assertEqual(summary["entities_by_country"]["Germany"], 12)
        self.assertEqual(summary["entities_by_country"]["Malaysia"], 7)
        self.assertEqual(summary["entities_by_country"]["United Kingdom"], 13)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4779.6, "count": 43, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["generation_nameplate_mw"]["planned"],
            {"base": 3127.0, "count": 3, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["grid_connection_mw"]["contracted"],
            {"base": 2460.0, "count": 4, "unit": "MW"},
        )

    def test_v27_closure_is_sealed_and_v28_is_exactly_four_inputs_additive(self) -> None:
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
            "capacity_estimates.csv": 2,
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
        previous_records = {json.dumps(record, sort_keys=True) for record in previous_sources}
        added_sources = [
            record
            for record in current_sources
            if json.dumps(record, sort_keys=True) not in previous_records
        ]
        self.assertEqual(len(added_sources), 4)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EVIDENCE_CONTENT_HASHES,
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 4)

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
        self.assertEqual(len(previous_inputs), 138)
        self.assertEqual(len(current_inputs), 142)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v28")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in set(previous) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], previous[key], key)

    def test_new_rows_preserve_only_audited_semantics(self) -> None:
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
        documents = []
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(inputs[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            documents.append(document)
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["operating_models"], [])
            self.assertTrue(all(row["entity"] == "project" for row in document["workloads"]))
            self.assertTrue(all(row["entity"] == "project" for row in document["lifecycle"]))

        self.assertEqual({d["campus"]["stable_key"] for d in documents}, CAMPUS_KEYS)
        self.assertEqual({d["project"]["stable_key"] for d in documents}, PROJECT_KEYS)
        self.assertEqual(
            {
                evidence["content_hash"]
                for document in documents
                for evidence in document["evidence"]
            },
            EVIDENCE_CONTENT_HASHES,
        )
        documents_by_campus = {d["campus"]["stable_key"]: d for d in documents}
        bitdeer = documents_by_campus["curated:bitdeer-fox-creek-alberta-campus"]
        firstcolo = documents_by_campus["curated:firstcolo-fra7-rosbach-campus"]
        brent = documents_by_campus["curated:pure-dc-brent-cross-lon01-campus"]
        nxera = documents_by_campus["curated:tm-nxera-iskandar-puteri-johor-campus"]
        self.assertEqual(
            [row["value"] for row in bitdeer["workloads"]],
            ["crypto_mining"],
        )
        self.assertEqual(
            [
                (
                    row["entity"],
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    row["base"],
                )
                for row in bitdeer["capacities"]
            ],
            [("campus", "generation_nameplate_mw", "planned", "MW", 101)],
        )
        self.assertEqual(
            [
                (
                    row["entity"],
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    row["base"],
                )
                for row in nxera["capacities"]
            ],
            [("campus", "grid_connection_mw", "contracted", "MW", 280)],
        )
        self.assertEqual(firstcolo["capacities"], [])
        self.assertEqual(brent["capacities"], [])
        self.assertEqual(firstcolo["workloads"], [])
        self.assertEqual(brent["workloads"], [])
        self.assertEqual(nxera["workloads"], [])
        self.assertEqual(
            {
                document["campus"]["stable_key"]: document["lifecycle"][0]["value"]
                for document in documents
            },
            {
                "curated:bitdeer-fox-creek-alberta-campus": "under_construction",
                "curated:firstcolo-fra7-rosbach-campus": "under_construction",
                "curated:pure-dc-brent-cross-lon01-campus": "under_construction",
                "curated:tm-nxera-iskandar-puteri-johor-campus": "shell",
            },
        )

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        expected_countries = {
            "bitdeer": "Canada",
            "firstcolo": "Germany",
            "brent-cross": "United Kingdom",
            "tm-nxera": "Malaysia",
        }
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(
                row["country"],
                next(country for token, country in expected_countries.items() if token in key),
            )
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertFalse(any(name.startswith("role:") for name in json.loads(row["tags_json"])))
        capacity_campuses = {
            "curated:bitdeer-fox-creek-alberta-campus",
            "curated:tm-nxera-iskandar-puteri-johor-campus",
        }
        for key in CAMPUS_KEYS - capacity_campuses:
            self.assertEqual(entity_rows[key]["workloads_json"], "[]")
            self.assertEqual(entity_rows[key]["capacity_estimates_json"], "[]")
            self.assertEqual(entity_rows[key]["status"], "")
        for key in PROJECT_KEYS:
            self.assertEqual(entity_rows[key]["capacity_estimates_json"], "[]")
        bitdeer_key = (
            "curated:bitdeer-fox-creek-alberta-campus:integrated-facility-current-build"
        )
        firstcolo_key = "curated:firstcolo-fra7-rosbach-campus:fra7-current-build"
        brent_key = "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build"
        nxera_key = "curated:tm-nxera-iskandar-puteri-johor-campus:first-building"
        self.assertEqual(entity_rows[bitdeer_key]["status"], "under_construction")
        self.assertEqual(
            [row["workload"] for row in json.loads(entity_rows[bitdeer_key]["workloads_json"])],
            ["crypto_mining"],
        )
        self.assertEqual(entity_rows[firstcolo_key]["status"], "under_construction")
        self.assertEqual(entity_rows[brent_key]["status"], "under_construction")
        self.assertEqual(entity_rows[nxera_key]["status"], "shell")
        for key in {firstcolo_key, brent_key, nxera_key}:
            self.assertEqual(entity_rows[key]["workloads_json"], "[]")
        bitdeer_capacities = json.loads(
            entity_rows["curated:bitdeer-fox-creek-alberta-campus"]["capacity_estimates_json"]
        )
        nxera_capacities = json.loads(
            entity_rows["curated:tm-nxera-iskandar-puteri-johor-campus"][
                "capacity_estimates_json"
            ]
        )
        self.assertEqual(
            [(row["metric"], row["stage"], row["base"]) for row in bitdeer_capacities],
            [("generation_nameplate_mw", "planned", 101.0)],
        )
        self.assertEqual(
            [(row["metric"], row["stage"], row["base"]) for row in nxera_capacities],
            [("grid_connection_mw", "contracted", 280.0)],
        )

        added_capacities = added_rows("capacity_estimates.csv")
        self.assertEqual(len(added_capacities), 2)
        self.assertEqual(
            {
                (row["name"], row["metric"], row["stage"], row["base"])
                for row in added_capacities
            },
            {
                (
                    "Bitdeer Fox Creek Alberta Campus",
                    "generation_nameplate_mw",
                    "planned",
                    "101.0",
                ),
                (
                    "TM Nxera Iskandar Puteri Johor Campus",
                    "grid_connection_mw",
                    "contracted",
                    "280.0",
                ),
            },
        )

        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 4)
        self.assertEqual(
            {signal["source_content_hash"] for signal in added_signals},
            EVIDENCE_CONTENT_HASHES,
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
        self.assertEqual(len(added_evidence), 4)
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_CONTENT_HASHES)


if __name__ == "__main__":
    unittest.main()
