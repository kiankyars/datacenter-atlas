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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v29.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v29"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v28.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v28"

DEFINITION_SHA256 = "e79eaacfa814594cf59ab691ece931f4b7463891aa1dbec04db6a45019f5dc99"
MANIFEST_SHA256 = "4e075e0f87d5e9b09857ada1509a673077117dd5c21e472b519e120b59fdf8b2"
PREVIOUS_DEFINITION_SHA256 = (
    "77777bbe26c8e5de198ab60f39eb83175dae5eb4bb5dfd0bdf84d7ef79e97733"
)
PREVIOUS_MANIFEST_SHA256 = (
    "651916a393f50c7bb8e4179c139373585a41caa3099cdb03b1bd6378533326ec"
)
RECORDED_AT = "2026-07-19T21:20:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-atlasedge-lev002-leverkusen.json": (
        "33bf4a8515215806d145db703941fbab9c853873801a7bdfc977b18acf3b2a46"
    ),
    "curated-official-2026-07-19-maincubes-ber02-mainhub-nauen.json": (
        "0dd1cf621fd7ffc8d7924fc757fa89c70bcd01101824830c422bc1ec8c216738"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_maincubes_atlasedge_next_tranche.py": (
        "b25478ef59c47c67d42c4872a68115e51963c66ccf24216391a4dbe261f5fe0d"
    ),
}
EVIDENCE_CONTENT_HASHES = {
    "1550ac81d2635484119ef766fcb16726e7e5062994fb61afd71cc327b3f18282",
    "32e7ca51d69ebf49621a17a97f7fb7db4a5d948ec4a88886b6a020e3da4cf43a",
    "cbf094f1a609a272739054b5c5f2f33f5663c9b2d9eee7a0dfa1a5d295f80efb",
}
CAMPUS_KEYS = {
    "curated:atlasedge-leverkusen-data-center-campus",
    "curated:maincubes-mainhub-nauen-campus",
}
PROJECT_KEYS = {
    "curated:atlasedge-leverkusen-data-center-campus:lev002",
    "curated:maincubes-mainhub-nauen-campus:ber02",
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


class OpenSeedV29Tests(unittest.TestCase):
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
        self.assertEqual(first["entities"], 344)
        self.assertEqual(first["entities_by_kind"], {"campus": 203, "project": 141})
        self.assertEqual(first["evidence_records"], 212)
        self.assertEqual(first["capacity_estimates"], 398)
        self.assertEqual(first["construction_pipeline_records"], 182)
        self.assertEqual(first["construction_source_signals"], 151)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 344)
        self.assertEqual(summary["projects_total"], 141)
        self.assertEqual(summary["evidence_total"], 236)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 114)
        self.assertEqual(summary["entities_by_status"]["site_preparation"], 9)
        self.assertEqual(summary["entities_by_status"]["permitted"], 3)
        self.assertEqual(summary["entities_by_status"]["proposed"], 1)
        self.assertEqual(summary["entities_by_status"]["shell"], 6)
        self.assertEqual(summary["entities_by_country"]["Germany"], 16)
        self.assertEqual(summary["entities_with_coordinates"], 139)
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

    def test_v28_closure_is_sealed_and_v29_is_exactly_two_inputs_additive(self) -> None:
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
            "evidence.csv": 3,
            "capacity_estimates.csv": 0,
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
        self.assertEqual(len(added_sources), 3)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EVIDENCE_CONTENT_HASHES,
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 3)

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
        self.assertEqual(len(previous_inputs), 142)
        self.assertEqual(len(current_inputs), 144)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v29")
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
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertIn(
                    entity["method"],
                    {"authoritative_locality", "authoritative_site_plan"},
                )
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            self.assertEqual(document["lifecycle"][0]["value"], "under_construction")

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
        atlasedge = documents_by_campus[
            "curated:atlasedge-leverkusen-data-center-campus"
        ]
        maincubes = documents_by_campus["curated:maincubes-mainhub-nauen-campus"]
        for entity_name in ("campus", "project"):
            self.assertIsNone(atlasedge[entity_name]["coordinates"])
            self.assertEqual(
                maincubes[entity_name]["coordinates"],
                {"latitude": 52.5935, "longitude": 12.8929999},
            )

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["country"], "Germany")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertFalse(any(name.startswith("role:") for name in json.loads(row["tags_json"])))
        maincubes_keys = {
            "curated:maincubes-mainhub-nauen-campus",
            "curated:maincubes-mainhub-nauen-campus:ber02",
        }
        for key in maincubes_keys:
            self.assertEqual(entity_rows[key]["latitude"], "52.5935")
            self.assertEqual(entity_rows[key]["longitude"], "12.8929999")
            self.assertEqual(
                json.loads(entity_rows[key]["geometry_json"]),
                {"coordinates": [12.8929999, 52.5935], "type": "Point"},
            )
        for key in NEW_ENTITY_KEYS - maincubes_keys:
            self.assertEqual(entity_rows[key]["latitude"], "")
            self.assertEqual(entity_rows[key]["longitude"], "")
            self.assertEqual(entity_rows[key]["geometry_json"], "null")
        for key in CAMPUS_KEYS:
            self.assertEqual(entity_rows[key]["status"], "")
        for key in PROJECT_KEYS:
            self.assertEqual(entity_rows[key]["status"], "under_construction")

        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 2)
        self.assertEqual(
            {signal["source_content_hash"] for signal in added_signals},
            {
                "1550ac81d2635484119ef766fcb16726e7e5062994fb61afd71cc327b3f18282",
                "cbf094f1a609a272739054b5c5f2f33f5663c9b2d9eee7a0dfa1a5d295f80efb",
            },
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
        self.assertEqual(len(added_evidence), 3)
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_CONTENT_HASHES)


if __name__ == "__main__":
    unittest.main()
