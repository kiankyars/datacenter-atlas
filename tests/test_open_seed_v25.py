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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v25.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v25"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v24.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v24"

DEFINITION_SHA256 = "c222270cf319d219de6863c79beca9ec368d8e4255c202745184c7d8cd4cfabd"
MANIFEST_SHA256 = "41002be5199f05816907f632fbe6f9d87570fcf3a4411f6d90ad471058f0610a"
PREVIOUS_DEFINITION_SHA256 = (
    "894c1a00e391aa1aaff68fa2e1626304d78fba88834d1bf5f020e08b6b6073c3"
)
PREVIOUS_MANIFEST_SHA256 = (
    "bcea0b6f3b4416c3f7474cf1079a35896bd80f30d1d5365b484b2a46d8578fe3"
)
RECORDED_AT = "2026-07-19T21:00:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-empyrion-th1-bang-na.json": (
        "5dd87f17ac34309b936e0135cb10b691047541f78bdd425cef7b3beb3c4eccfb"
    ),
    "curated-official-2026-07-19-empyrion-tw1-taipei.json": (
        "46214b54a0397a39c9f9d0519066d659652364677f7e0eb8a9e3d7089ed13c53"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_empyrion_tw1_th1.py": (
        "5b48a0d6c3b91984b21604706fbbc24ded73462729b59e5136dd2091565dd5b6"
    ),
}
EVIDENCE_CONTENT_HASHES = {
    "0ae2d638ff7785a09cd75cd5c045569a89a64d8ff656ee64131891a281da88a8",
    "4fe32da7fefeee4082243e77c8063c14f91a12b70cb41978376e8ae6e8593e7e",
}
CAMPUS_KEYS = {
    "curated:empyrion-th1-bang-na-data-center",
    "curated:empyrion-tw1-taipei-data-center",
}
PROJECT_KEYS = {
    "curated:empyrion-th1-bang-na-data-center:current-facility-build",
    "curated:empyrion-tw1-taipei-data-center:current-facility-build",
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


class OpenSeedV25Tests(unittest.TestCase):
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
        self.assertEqual(first["entities"], 324)
        self.assertEqual(first["entities_by_kind"], {"campus": 193, "project": 131})
        self.assertEqual(first["evidence_records"], 200)
        self.assertEqual(first["capacity_estimates"], 395)
        self.assertEqual(first["construction_pipeline_records"], 172)
        self.assertEqual(first["construction_source_signals"], 141)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 324)
        self.assertEqual(summary["projects_total"], 131)
        self.assertEqual(summary["evidence_total"], 222)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 108)
        self.assertEqual(summary["entities_by_country"]["Thailand"], 10)
        self.assertEqual(summary["entities_by_country"]["Taiwan, Province of China"], 2)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4731.6, "count": 42, "unit": "MW"},
        )

    def test_v24_closure_is_sealed_and_v25_is_exactly_two_inputs_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 4,
            "evidence.csv": 2,
            "capacity_estimates.csv": 2,
            "construction_pipeline.csv": 2,
            "construction_source_signals.csv": 2,
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
        self.assertEqual(len(added_sources), 2)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EVIDENCE_CONTENT_HASHES,
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 2)

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
        self.assertEqual(len(previous_inputs), 132)
        self.assertEqual(len(current_inputs), 134)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v25")
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
            self.assertEqual(len(document["capacities"]), 1)
            capacity = document["capacities"][0]
            self.assertEqual(capacity["entity"], "project")
            self.assertEqual(capacity["metric"], "critical_it_mw")
            self.assertEqual(capacity["stage"], "planned")
            self.assertEqual(capacity["unit"], "MW")
            self.assertEqual(capacity["method"], "reported")
            self.assertEqual(capacity["low"], capacity["base"])
            self.assertEqual(capacity["base"], capacity["high"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            self.assertEqual(document["lifecycle"][0]["value"], "under_construction")

        self.assertEqual({d["campus"]["stable_key"] for d in documents}, CAMPUS_KEYS)
        self.assertEqual({d["project"]["stable_key"] for d in documents}, PROJECT_KEYS)
        self.assertEqual(
            {d["capacities"][0]["base"] for d in documents},
            {7, 20},
        )

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            expected_country = "Taiwan, Province of China" if "tw1" in key else "Thailand"
            self.assertEqual(row["country"], expected_country)
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertFalse(any(name.startswith("role:") for name in json.loads(row["tags_json"])))
        for key in CAMPUS_KEYS:
            self.assertEqual(entity_rows[key]["workloads_json"], "[]")
            self.assertEqual(entity_rows[key]["capacity_estimates_json"], "[]")
            self.assertEqual(entity_rows[key]["status"], "")
        for key in PROJECT_KEYS:
            self.assertEqual(entity_rows[key]["status"], "under_construction")
            self.assertEqual(entity_rows[key]["workloads_json"], "[]")
            capacities = json.loads(entity_rows[key]["capacity_estimates_json"])
            self.assertEqual(len(capacities), 1)
            self.assertEqual(capacities[0]["metric"], "critical_it_mw")
            self.assertEqual(capacities[0]["stage"], "planned")

        added_capacities = added_rows("capacity_estimates.csv")
        self.assertEqual(len(added_capacities), 2)
        self.assertEqual(
            {
                (row["name"], row["metric"], row["stage"], row["unit"], row["base"])
                for row in added_capacities
            },
            {
                ("Empyrion TH1 Current Facility Build", "critical_it_mw", "planned", "MW", "20.0"),
                ("Empyrion TW1 Current Facility Build", "critical_it_mw", "planned", "MW", "7.0"),
            },
        )

        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 2)
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
        self.assertEqual(len(added_evidence), 2)
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_CONTENT_HASHES)


if __name__ == "__main__":
    unittest.main()
