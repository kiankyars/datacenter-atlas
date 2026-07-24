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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v12.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v12"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v11"
DEFINITION_SHA256 = "42acd5aa158a75c81b1c213ffb6a155f5287dfc9affc7230738a1319acf04be1"
MANIFEST_SHA256 = "c512cb8ca7154f53b94734550a514d451019b899405f62d254f79e470d2e1b19"
SOURCE_HASHES = {
    "curated-official-2026-07-19-microsoft-local-boyd-farms-nc.json": "56e9dd61d607ba1f131633787d8f0713b6ce8d80b55bbf350c34175d9b855db2",
    "curated-official-2026-07-19-microsoft-local-heath-oh.json": "7baa853f3fbaa2c2c2a8ae9acade07066dcc68ead8dc70c30be18a7a3ca4f078",
    "curated-official-2026-07-19-microsoft-local-hebron-oh.json": "0b4cb18b64ac7858fc098994e110043ef6c745ea020a5f8d9cbc85a953e449a2",
    "curated-official-2026-07-19-microsoft-local-koge-phase-2-denmark.json": "92783c9bc0e6bceda588c3c414aca47994000dd5b64477ea9837fa38bd732aa1",
    "curated-official-2026-07-19-microsoft-local-new-albany-oh.json": "1c4037db5728baf062b739a5eee0ce423c681b51225cffcc79973c8b94813ac6",
    "curated-official-2026-07-19-microsoft-local-northwest-hortolandia-brazil.json": "46aa032296f076898c851ee00187e1f592cccde2c0f28342b471dbad0eadbb5c",
    "curated-official-2026-07-19-microsoft-local-san-bovio-italy.json": "00c9e055f0df79ea1226033b40aca969f8b2948e5f5b4d9f8a913ea735f11e9f",
    "curated-official-2026-07-19-microsoft-local-southwest-hortolandia-brazil.json": "291e22ec999df35161432d69d5e744f761167939c8d00832a48a3a7d080dddbe",
    "curated-official-2026-07-19-microsoft-local-stover-hickory-nc.json": "cce2c35cfe6db14787b0577277ebffaae83ad464be7244303afb2fb7023b76c9",
    "curated-official-2026-07-19-microsoft-local-sumare-east-brazil.json": "7b500dfd59682e2a4155adfab32547ec3afefff578b670ddfb1091b1047a4b48",
}
EXPECTED_STAGE_COUNTS = {
    "civil_works": 1,
    "foundations": 2,
    "mep_electrical": 3,
    "site_preparation": 4,
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV12Tests(unittest.TestCase):
    def test_accepted_release_rebuilds_twice_offline_with_exact_accounting(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_open_seed_release(
                DEFINITION,
                RELEASE,
            )
            second = validate_open_seed_release(
                DEFINITION,
                RELEASE,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["entities"], 166)
        self.assertEqual(first["entities_by_kind"], {"campus": 117, "project": 49})
        self.assertEqual(first["evidence_records"], 122)
        self.assertEqual(first["capacity_estimates"], 358)
        self.assertEqual(first["construction_pipeline_records"], 90)
        self.assertEqual(first["construction_source_signals"], 81)
        self.assertEqual(first["resolution_candidates"], 4)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 166)
        self.assertEqual(summary["projects_total"], 49)
        self.assertEqual(summary["evidence_total"], 125)
        for stage, count in EXPECTED_STAGE_COUNTS.items():
            self.assertEqual(summary["entities_by_status"][stage], count)

    def test_sources_are_coordinate_free_and_import_no_inferred_metrics(self) -> None:
        project_stages: dict[str, str] = {}
        campus_keys: set[str] = set()
        for filename, expected_hash in SOURCE_HASHES.items():
            path = ROOT / "sources" / filename
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
            source = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(source["evidence"]), 1)
            evidence = source["evidence"][0]
            self.assertEqual(evidence["source_family"], "microsoft_local_project_updates")
            self.assertEqual(evidence["license"], "all-rights-reserved")
            self.assertEqual(
                evidence["metadata"]["retrieved_at_semantics"],
                "Request-start UTC recorded by the capture harness; the response HTTP Date can be the same second or one second later.",
            )
            for entity in (source["campus"], source["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(entity["roles"], {})
            self.assertEqual(source["operating_models"], [])
            self.assertEqual(source["workloads"], [])
            self.assertEqual(source["capacities"], [])
            self.assertEqual(len(source["lifecycle"]), 1)
            lifecycle = source["lifecycle"][0]
            self.assertEqual(lifecycle["entity"], "project")
            self.assertEqual(lifecycle["method"], "authoritative_physical_status_update")
            project_stages[source["project"]["stable_key"]] = lifecycle["value"]
            campus_keys.add(source["campus"]["stable_key"])

        self.assertEqual(len(project_stages), 10)
        self.assertEqual(len(campus_keys), 10)
        self.assertEqual(
            {stage: list(project_stages.values()).count(stage) for stage in set(project_stages.values())},
            EXPECTED_STAGE_COUNTS,
        )

        release_entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        for stable_key, stage in project_stages.items():
            entity = release_entities[stable_key]
            self.assertEqual(entity["status"], stage)
            self.assertEqual(entity["status_method"], "authoritative_physical_status_update")
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual(entity["capacity_estimates_json"], "[]")
            self.assertEqual(entity["workloads_json"], "[]")
        for stable_key in campus_keys:
            entity = release_entities[stable_key]
            self.assertEqual(entity["status"], "")
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))

        all_stable_keys = set(release_entities)
        self.assertFalse(any("east-point" in stable_key for stable_key in all_stable_keys))

    def test_v11_rows_are_preserved_and_v12_is_additive(self) -> None:
        expected_deltas = {
            "entities.csv": 20,
            "evidence.csv": 10,
            "capacity_estimates.csv": 0,
            "construction_pipeline.csv": 10,
            "construction_source_signals.csv": 10,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous = rows(PREVIOUS_RELEASE / filename)
            current = rows(RELEASE / filename)
            previous_rows = {tuple(sorted(row.items())) for row in previous}
            current_rows = {tuple(sorted(row.items())) for row in current}
            self.assertTrue(previous_rows <= current_rows, filename)
            self.assertEqual(len(current) - len(previous), expected_delta, filename)


if __name__ == "__main__":
    unittest.main()
