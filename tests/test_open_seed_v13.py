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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v13.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v13"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v12"
DEFINITION_SHA256 = "5b62d3e69e8ae09de70fc7046318d36054e4a264d00f606efc67fa88a89bd3be"
MANIFEST_SHA256 = "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7"
SOURCE_HASHES = {
    "curated-official-2026-07-19-colt-london4-hayes.json": "44a4569bed0c12103d726d0e73f8a05078f4528c74c7f032dfc5feaa9ea0b05b",
    "curated-official-2026-07-19-cyrusone-dfw7-fort-worth.json": "be3c809f135e8c00b8cd299e99ae6a5cce6cd22642bb719e86ffbb0ac4b105ee",
    "curated-official-2026-07-19-cyrusone-mil1-segrate.json": "393fd497f26e46ab15831f2d8b0dd9cf74356c65d54436e9e5139a9e1a3a975e",
    "curated-official-2026-07-19-cyrusone-yorkville-technology-campus.json": "358f37b1e224488f38ebdaf590ffc1ddb1fd2bc3fbd3e01edca960c91c572c9b",
    "curated-official-2026-07-19-digital-realty-330-east-cermak-chicago.json": "0fecb93df76c3a2f4ad276da3b3fc5710551f843109ea9f43971a7d57a1fa8a5",
    "curated-official-2026-07-19-digital-realty-dugny-par15.json": "e4e5982c65534f2c09787faade0a435d9cbf70e1e2ad706a32f1644f7d5e268e",
    "curated-official-2026-07-19-digital-realty-fra20-frankfurt.json": "096378e468cfd10d4ed41e25b5fe1b32fff3d2c19b8bc71df6ab51cdadb38e59",
    "curated-official-2026-07-19-digital-realty-rom1-rome.json": "f809518a71f8d0f4333daabab2e94534af03ea1a1b6b19cd35a91bdecd52e84e",
    "curated-official-2026-07-19-qts-cambois-earthworks.json": "1960b1cdfdde3da6cebfccb006ebdd6addc85bc1079c3b111b3f5b38bf5d8e89",
    "curated-official-2026-07-19-qts-cedar-rapids-current-campus-development.json": "0b8a466bc192a20b432e621081612927374d4cd0949553ef2c5c7aed8499bcd5",
    "curated-official-2026-07-19-qts-eagle-mountain-building-1.json": "a53e19f3f7042674b378cd736f703e53568ae8d71a6b1d5ba153c9282b4e3ef0",
    "curated-official-2026-07-19-qts-eagle-mountain-building-2.json": "c3a1da2ebea96d1e3427ee272fa4fc66f968da3ccc6e0014a122e52be6bdea21",
    "curated-official-2026-07-19-qts-eagle-mountain-building-3.json": "054bc66a6cdbc880211c1947a0bb4b0c3ec3786bde727c7845fd8e49742d1967",
    "curated-official-2026-07-19-qts-york-initial-phase-building-1.json": "11b588dfcd677fc3a5b5f8807e7aa4041f6f5e9b4fe8d31459034401d1692c4c",
    "curated-official-2026-07-19-stack-northwest-louisiana-multi-campus.json": "c632b30f4f966e334af288f6ab6ee6684a9279fbd670406059346b939752ebfe",
}
EXPECTED_CAPACITIES = {
    ("curated:colt-london-hayes-campus:london4-current-facility-build", 31.0),
    ("curated:cyrusone-mil1-segrate-data-center:current-facility-build", 27.0),
    ("curated:digital-realty-dugny-digital-hub", 176.0),
    ("curated:digital-realty-fra20-frankfurt:current-facility-build", 16.0),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV13Tests(unittest.TestCase):
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
            first = validate_open_seed_release(DEFINITION, RELEASE)
            second = validate_open_seed_release(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first["entities"], 194)
        self.assertEqual(first["entities_by_kind"], {"campus": 130, "project": 64})
        self.assertEqual(first["evidence_records"], 140)
        self.assertEqual(first["capacity_estimates"], 362)
        self.assertEqual(first["construction_pipeline_records"], 105)
        self.assertEqual(first["construction_source_signals"], 95)
        self.assertEqual(first["resolution_candidates"], 4)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 194)
        self.assertEqual(summary["projects_total"], 64)
        self.assertEqual(summary["evidence_total"], 146)
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
                "shell": 2,
                "site_preparation": 5,
                "under_construction": 60,
            },
        )

    def test_new_inputs_remain_coordinate_free_and_metric_narrow(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(len(definition["curated_inputs"]), 66)
        self.assertEqual(
            [record["path"] for record in definition["curated_inputs"]],
            sorted(record["path"] for record in definition["curated_inputs"]),
        )

        evidence_count = 0
        evidence_ids: set[str] = set()
        lifecycle: dict[str, str] = {}
        capacities: set[tuple[str, float]] = set()
        stable_keys: set[str] = set()
        for filename, expected_hash in SOURCE_HASHES.items():
            path = ROOT / "sources" / filename
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
            source = json.loads(path.read_text(encoding="utf-8"))
            evidence_count += len(source["evidence"])
            evidence_ids.update(record["key"] for record in source["evidence"])
            for entity_name in ("campus", "project"):
                entity = source[entity_name]
                stable_keys.add(entity["stable_key"])
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(entity["roles"], {})
            self.assertEqual(source["operating_models"], [])
            self.assertEqual(source["workloads"], [])
            self.assertEqual(len(source["lifecycle"]), 1)
            observation = source["lifecycle"][0]
            target = source[observation["entity"]]["stable_key"]
            lifecycle[target] = observation["value"]
            self.assertNotIn(observation["value"], {"operational", "commissioning"})
            for capacity in source["capacities"]:
                target = source[capacity["entity"]]["stable_key"]
                self.assertEqual(capacity["metric"], "critical_it_mw")
                self.assertEqual(capacity["stage"], "planned")
                capacities.add((target, float(capacity["base"])))

        self.assertEqual(evidence_count, 29)
        self.assertEqual(len(evidence_ids), 21)
        self.assertEqual(len(stable_keys), 28)
        self.assertEqual(len(lifecycle), 15)
        self.assertEqual(
            {stage: list(lifecycle.values()).count(stage) for stage in set(lifecycle.values())},
            {"civil_works": 1, "shell": 2, "site_preparation": 1, "under_construction": 11},
        )
        self.assertEqual(capacities, EXPECTED_CAPACITIES)

        release_entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        for stable_key in stable_keys:
            entity = release_entities[stable_key]
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual((entity["owner"], entity["operator"], entity["users"]), ("", "", ""))
            self.assertEqual(entity["operating_model"], "")
            self.assertEqual(entity["workloads_json"], "[]")
        for stable_key, status in lifecycle.items():
            self.assertEqual(release_entities[stable_key]["status"], status)

    def test_v12_rows_are_preserved_and_v13_is_additive(self) -> None:
        expected_deltas = {
            "entities.csv": 28,
            "evidence.csv": 18,
            "capacity_estimates.csv": 4,
            "construction_pipeline.csv": 15,
            "construction_source_signals.csv": 14,
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
