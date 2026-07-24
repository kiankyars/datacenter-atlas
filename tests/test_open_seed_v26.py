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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v26.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v26"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v25.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v25"

DEFINITION_SHA256 = "67f7fc1b196ea131ce26d745c747ee661d349d31bec48ab5f5fe2e5a1749f706"
MANIFEST_SHA256 = "be3ce28958451d51beb3ce83fdbb4dfe5e62107bf76482bc3164dfc8e4ee3695"
PREVIOUS_DEFINITION_SHA256 = (
    "c222270cf319d219de6863c79beca9ec368d8e4255c202745184c7d8cd4cfabd"
)
PREVIOUS_MANIFEST_SHA256 = (
    "41002be5199f05816907f632fbe6f9d87570fcf3a4411f6d90ad471058f0610a"
)
RECORDED_AT = "2026-07-19T21:05:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-microsoft-la-porte-indiana-first-phase.json": (
        "557eaac082951d41037343a668d796c6eb1e31e5c895d10597efdaac9a8c9c1d"
    ),
    "curated-official-2026-07-19-nebius-independence-missouri-phase-1.json": (
        "366ed041e837c8d28398e8e1868175e979af2297a7bdfe55a914cfbfe6db6ccf"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_microsoft_la_porte_nebius_independence.py": (
        "9828ef3e0f5efc0a2f5dbd5f012c86e14d80eebf8cb6fb33d3c108e9448f7866"
    ),
}
EVIDENCE_CONTENT_HASHES = {
    "27eaeb89b231fc1a6bf77567dc299c2110f128047ccb1deeebff7f0cdc23a1f1",
    "6b62b800778e0899da39eabd0347112a2f4729f3eb4db09ba53532085350c57e",
    "e48852f997daeb2f79ced15cf7c3bd31f4ef5e25e8a6880dbedbea84393739f7",
}
ALL_SOURCE_EVIDENCE_HASHES = EVIDENCE_CONTENT_HASHES | {
    "b73ae86bfb3e35f8017364034694d7c370111bc9ea4892bc327c019d571bf0c8",
    "e3a19166806b1c92bcb2fe4097cf590ea69657268c2d7e07454eb3a74560d67b",
}
CAMPUS_KEYS = {
    "curated:microsoft-la-porte-indiana-campus",
    "curated:nebius-independence-missouri-ai-factory-campus",
}
PROJECT_KEYS = {
    "curated:microsoft-la-porte-indiana-campus:first-phase-current-build",
    "curated:nebius-independence-missouri-ai-factory-campus:phase-1-current-build",
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


class OpenSeedV26Tests(unittest.TestCase):
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
        self.assertEqual(first["entities"], 328)
        self.assertEqual(first["entities_by_kind"], {"campus": 195, "project": 133})
        self.assertEqual(first["evidence_records"], 203)
        self.assertEqual(first["capacity_estimates"], 395)
        self.assertEqual(first["construction_pipeline_records"], 174)
        self.assertEqual(first["construction_source_signals"], 143)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 328)
        self.assertEqual(summary["projects_total"], 133)
        self.assertEqual(summary["evidence_total"], 227)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 109)
        self.assertEqual(summary["entities_by_status"]["site_preparation"], 9)
        self.assertEqual(summary["entities_by_country"]["United States"], 157)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4731.6, "count": 42, "unit": "MW"},
        )

    def test_v25_closure_is_sealed_and_v26_is_exactly_two_inputs_additive(self) -> None:
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
        self.assertEqual(len(previous_inputs), 134)
        self.assertEqual(len(current_inputs), 136)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v26")
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
            self.assertEqual(document["capacities"], [])
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
            ALL_SOURCE_EVIDENCE_HASHES,
        )
        documents_by_campus = {d["campus"]["stable_key"]: d for d in documents}
        microsoft = documents_by_campus["curated:microsoft-la-porte-indiana-campus"]
        nebius = documents_by_campus[
            "curated:nebius-independence-missouri-ai-factory-campus"
        ]
        self.assertEqual(microsoft["workloads"], [])
        self.assertEqual(
            [row["value"] for row in microsoft["lifecycle"]],
            ["under_construction", "site_preparation"],
        )
        self.assertEqual(
            [row["value"] for row in nebius["workloads"]],
            ["ai_specialized_unspecified"],
        )
        self.assertEqual(
            [row["value"] for row in nebius["lifecycle"]],
            ["under_construction"],
        )

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["country"], "United States")
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
            self.assertEqual(entity_rows[key]["capacity_estimates_json"], "[]")
        microsoft_key = "curated:microsoft-la-porte-indiana-campus:first-phase-current-build"
        nebius_key = (
            "curated:nebius-independence-missouri-ai-factory-campus:phase-1-current-build"
        )
        self.assertEqual(entity_rows[microsoft_key]["status"], "site_preparation")
        self.assertEqual(entity_rows[microsoft_key]["workloads_json"], "[]")
        self.assertEqual(entity_rows[nebius_key]["status"], "under_construction")
        self.assertEqual(
            [row["workload"] for row in json.loads(entity_rows[nebius_key]["workloads_json"])],
            ["ai_specialized_unspecified"],
        )

        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 2)
        self.assertEqual(
            {signal["source_content_hash"] for signal in added_signals},
            {
                "6b62b800778e0899da39eabd0347112a2f4729f3eb4db09ba53532085350c57e",
                "e48852f997daeb2f79ced15cf7c3bd31f4ef5e25e8a6880dbedbea84393739f7",
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
