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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v20.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v20"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v19.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v19"

DEFINITION_SHA256 = "099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd"
MANIFEST_SHA256 = "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456"
PREVIOUS_DEFINITION_SHA256 = (
    "8c6e88b9228b23657475bca28ba8de944e0653d2946b02762f51ebbe726efac6"
)
PREVIOUS_MANIFEST_SHA256 = (
    "f16569524f4bd2059329a2a9b68018cf1595c3d56f4a2b4dbfd24a56891d8bd3"
)
RECORDED_AT = "2026-07-19T20:16:24Z"

TRANCHE_TEST_HASHES = {
    "test_curated_yondr_khazna_next_tranche.py": (
        "bcb13088d1458c1f57cbe1b04b49e68481a430197a1fc6ab457813d8cd3c28e7"
    ),
    "test_curated_khazna_qaj1_design_capacity.py": (
        "e9767d0f829fbede802ed3f8f1b27000a20220298c42f0f80bf97571e3ad48b7"
    ),
}

SOURCE_HASHES = {
    "curated-official-2026-07-19-yondr-slough-third-building.json": (
        "74e07cff7e1058c9d956e329f11d4ad72f0fe9fb66b3dc5c64858867a5123e32"
    ),
    "curated-official-2026-07-19-khazna-auh4-mafraq.json": (
        "529c6f247336e6d4b7953b6980c0f2c10810191bcfe754f695571444d5d6a1b4"
    ),
    "curated-official-2026-07-19-khazna-auh8-masdar-city.json": (
        "74b2cdeb870e1aadb374943aff5798bf8360af164a665c1d867d4da305642b22"
    ),
    "curated-official-2026-07-19-khazna-qaj1-ajman.json": (
        "34524821d70715fae1070ddf632cbb78c746c0c83282572f8aac406d880e42e5"
    ),
    "curated-official-2026-07-19-khazna-qaj1-tier-iii-design.json": (
        "7366625bdc8a737943bfdc8eee6f5ffbf753efb6602393f5b1fdedfb672482af"
    ),
}

CAMPUS_KEYS = {
    "curated:yondr-london-slough-data-center-campus",
    "curated:khazna-auh4-mafraq-data-center",
    "curated:khazna-auh8-masdar-city-data-center",
    "curated:khazna-qaj1-ajman-data-center",
}
PROJECT_STATUSES = {
    "curated:yondr-london-slough-data-center-campus:third-building": (
        "under_construction",
        "2026-02-20",
        "authoritative_physical_status_update",
    ),
    "curated:khazna-auh4-mafraq-data-center:current-facility-build": (
        "under_construction",
        "2025-04-21",
        "authoritative_construction_start",
    ),
    "curated:khazna-auh8-masdar-city-data-center:current-facility-build": (
        "under_construction",
        "2025-04-21",
        "authoritative_construction_start",
    ),
    "curated:khazna-qaj1-ajman-data-center:current-facility-build": (
        "shell",
        "2025-04-21",
        "authoritative_physical_status_update",
    ),
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | set(PROJECT_STATUSES)
QAJ1_PROJECT_KEY = (
    "curated:khazna-qaj1-ajman-data-center:current-facility-build"
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


class OpenSeedV20Tests(unittest.TestCase):
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
        self.assertEqual(first["entities"], 282)
        self.assertEqual(first["entities_by_kind"], {"campus": 172, "project": 110})
        self.assertEqual(first["evidence_records"], 182)
        self.assertEqual(first["capacity_estimates"], 392)
        self.assertEqual(first["construction_pipeline_records"], 151)
        self.assertEqual(first["construction_source_signals"], 124)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 282)
        self.assertEqual(summary["projects_total"], 110)
        self.assertEqual(summary["evidence_total"], 200)
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
                "under_construction": 87,
            },
        )
        planned_it = summary["capacity_base_totals"]["critical_it_mw"]["planned"]
        self.assertEqual(planned_it, {"base": 4686.6, "count": 39, "unit": "MW"})

    def test_v19_closure_is_sealed_and_v20_is_exactly_five_inputs_additive(self) -> None:
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
            "evidence.csv": 3,
            "capacity_estimates.csv": 1,
            "construction_pipeline.csv": 4,
            "construction_source_signals.csv": 2,
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
        self.assertEqual(len(previous_inputs), 108)
        self.assertEqual(len(current_inputs), 113)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v20")

    def test_new_sources_and_rows_preserve_only_audited_semantics(self) -> None:
        for filename, expected_hash in TRANCHE_TEST_HASHES.items():
            self.assertEqual(
                hashlib.sha256((ROOT / "tests" / filename).read_bytes()).hexdigest(),
                expected_hash,
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
            self.assertTrue(
                all(evidence["kind"] != "satellite_imagery" for evidence in document["evidence"])
            )

        campus_keys = {document["campus"]["stable_key"] for document in documents.values()}
        project_keys = {document["project"]["stable_key"] for document in documents.values()}
        self.assertEqual(campus_keys, CAMPUS_KEYS)
        self.assertEqual(project_keys, set(PROJECT_STATUSES))

        yondr = documents[
            "curated-official-2026-07-19-yondr-slough-third-building.json"
        ]
        current_metadata = yondr["evidence"][0]["metadata"]
        groundbreaking_metadata = yondr["evidence"][1]["metadata"]
        self.assertEqual(current_metadata["campus_capacity_wording_as_reported"], "100MW+ campus")
        self.assertEqual(
            current_metadata["first_two_buildings_capacity_wording_as_reported"],
            "over 60MW of capacity",
        )
        self.assertEqual(groundbreaking_metadata["third_building_capacity_as_reported_mw"], 40)
        self.assertIn("metadata", current_metadata["capacity_guardrail"])
        self.assertIn("untyped metadata", groundbreaking_metadata["capacity_metric_guardrail"])

        khazna_names = [
            "curated-official-2026-07-19-khazna-auh4-mafraq.json",
            "curated-official-2026-07-19-khazna-auh8-masdar-city.json",
            "curated-official-2026-07-19-khazna-qaj1-ajman.json",
        ]
        khazna_evidence = [documents[name]["evidence"] for name in khazna_names]
        self.assertEqual(khazna_evidence[0], khazna_evidence[1])
        self.assertEqual(khazna_evidence[0], khazna_evidence[2])
        khazna_metadata = khazna_evidence[0][0]["metadata"]
        self.assertEqual(khazna_metadata["auh4_auh8_combined_capacity_as_reported_mw"], 60)
        self.assertIn("untyped aggregate metadata", khazna_metadata["combined_capacity_guardrail"])
        self.assertIn("untyped metadata", khazna_metadata["qaj1_capacity_guardrail"])

        design = documents[
            "curated-official-2026-07-19-khazna-qaj1-tier-iii-design.json"
        ]
        self.assertEqual(design["lifecycle"], [])
        self.assertEqual(design["workloads"], [])
        self.assertEqual(len(design["capacities"]), 1)

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - set(row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")), NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertFalse(
                any(name.startswith("role:") for name in json.loads(row["tags_json"]))
            )

        new_projects = [entity_rows[key] for key in PROJECT_STATUSES]
        self.assertEqual(
            {row["status"] for row in new_projects},
            {"under_construction", "shell"},
        )
        self.assertEqual(
            sum(row["status"] == "under_construction" for row in new_projects), 3
        )
        self.assertEqual(sum(row["status"] == "shell" for row in new_projects), 1)
        for key, expected_status in PROJECT_STATUSES.items():
            row = entity_rows[key]
            self.assertEqual(
                (row["status"], row["status_as_of"], row["status_method"]),
                expected_status,
            )

        workload_rows = [
            (key, workload)
            for key in NEW_ENTITY_KEYS
            for workload in json.loads(entity_rows[key]["workloads_json"])
        ]
        self.assertEqual(
            workload_rows,
            [
                (
                    QAJ1_PROJECT_KEY,
                    {
                        "as_of_date": "2025-04-21",
                        "confidence": 0.99,
                        "evidence_id": "d51a3e4d-1708-52e0-a377-12fcdd8f5ad5",
                        "method": "company_disclosure",
                        "workload": "ai_specialized_unspecified",
                    },
                )
            ],
        )

        capacities = added_rows("capacity_estimates.csv")
        self.assertEqual(len(capacities), 1)
        qaj1_entity_id = entity_rows[QAJ1_PROJECT_KEY]["entity_id"]
        capacity = capacities[0]
        self.assertEqual(capacity["entity_id"], qaj1_entity_id)
        self.assertEqual(
            (
                capacity["metric"],
                capacity["stage"],
                capacity["unit"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
                capacity["method"],
                capacity["as_of_date"],
                capacity["target_date"],
            ),
            (
                "critical_it_mw",
                "planned",
                "MW",
                "100.0",
                "100.0",
                "100.0",
                "reported",
                "2026-02-24",
                "",
            ),
        )

        evidence = added_rows("evidence.csv")
        self.assertEqual(len(evidence), 3)
        self.assertEqual(
            {row["content_hash"] for row in evidence},
            {
                "7cb3b3fe110add00db98298fdc91d3a04f395d3275104bd70d91bf9ab4eea928",
                "8488186266dbdfe8f60530383d6a918415895d9de82ceef78fb718e7c6955c7c",
                "21445bbf241aec3b379417d7e2111477b535b829f542a87ffce4dfb641fd2698",
            },
        )


if __name__ == "__main__":
    unittest.main()
