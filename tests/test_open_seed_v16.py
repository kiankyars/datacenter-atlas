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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v16.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v16"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v15.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v15"
DEFINITION_SHA256 = "18ea978b258a66144e1d3a5c7a6eae955ec5776ad560b774df7ff29f8d146ab3"
MANIFEST_SHA256 = "849eac3da58ea5acfcc221032e4d49d1d40639f1586255f526d836ab32c3b411"
PREVIOUS_DEFINITION_SHA256 = (
    "e876884407f66524c6881869100175749f29c60648acec5c3ba9f8f14f7e8b36"
)
PREVIOUS_MANIFEST_SHA256 = (
    "0ece037ba1b894b8153808393980deaba0d56b3c4541e279950e8e9f2c52e0a0"
)

SOURCE_HASHES = {
    "curated-official-2026-07-19-meta-sturgeon-county-alberta.json": (
        "2b1b612b0ada0c25ed2bbc3cf2cef2fc0063ae6b58feaf467d9917b22c9265f1"
    ),
    "curated-official-2026-07-19-vantage-frontier-shackelford.json": (
        "169bd1808a8f6a6202a2ec8beda3f9c42515b44491e40ceed3e37e6144a978b2"
    ),
}

NEW_ENTITY_KEYS = {
    "curated:meta-sturgeon-county-alberta-data-center",
    "curated:meta-sturgeon-county-alberta-data-center:current-campus-build",
    "curated:vantage-frontier-shackelford-campus",
    (
        "curated:vantage-frontier-shackelford-campus:"
        "current-10-building-campus-development"
    ),
}

EXPECTED_STATUSES = {
    "curated:meta-sturgeon-county-alberta-data-center:current-campus-build": (
        "under_construction",
        "2026-07-08",
        "authoritative_construction_start",
    ),
    (
        "curated:vantage-frontier-shackelford-campus:"
        "current-10-building-campus-development"
    ): (
        "under_construction",
        "2026-06-01",
        "authoritative_physical_status_update",
    ),
}

EXPECTED_WORKLOADS = {
    "curated:meta-sturgeon-county-alberta-data-center": (
        "ai_specialized_unspecified"
    ),
    "curated:vantage-frontier-shackelford-campus": (
        "ai_specialized_unspecified"
    ),
}

EXPECTED_CAPACITIES = {
    (
        "curated:vantage-frontier-shackelford-campus",
        "critical_it_mw",
        "planned",
        1400.0,
    )
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


class OpenSeedV16Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_exact_accounting(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(RELEASE.is_symlink())
        self.assertTrue(
            all(not candidate.is_symlink() for candidate in RELEASE.iterdir())
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
        self.assertEqual(first["recorded_at"], "2026-07-19T19:22:01Z")
        self.assertEqual(first["entities"], 223)
        self.assertEqual(first["entities_by_kind"], {"campus": 144, "project": 79})
        self.assertEqual(first["evidence_records"], 166)
        self.assertEqual(first["capacity_estimates"], 373)
        self.assertEqual(first["construction_pipeline_records"], 120)
        self.assertEqual(first["construction_source_signals"], 110)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 223)
        self.assertEqual(summary["projects_total"], 79)
        self.assertEqual(summary["evidence_total"], 183)
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
                "shell": 3,
                "site_preparation": 6,
                "under_construction": 73,
            },
        )

    def test_v15_closure_is_sealed_and_v16_is_exactly_additive(self) -> None:
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
            "evidence.csv": 4,
            "capacity_estimates.csv": 1,
            "construction_pipeline.csv": 2,
            "construction_source_signals.csv": 2,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous = rows(PREVIOUS_RELEASE / filename)
            current = rows(RELEASE / filename)
            self.assertTrue(
                row_set(PREVIOUS_RELEASE / filename) <= row_set(RELEASE / filename),
                filename,
            )
            self.assertEqual(len(current) - len(previous), expected_delta, filename)

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
        self.assertEqual(len(previous_inputs), 79)
        self.assertEqual(len(current_inputs), 81)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )

    def test_new_sources_and_rows_keep_narrow_semantics(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
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

        meta = documents[
            "curated-official-2026-07-19-meta-sturgeon-county-alberta.json"
        ]
        self.assertEqual(meta["evidence"][0]["metadata"]["reported_scale_claim_gw"], 1)
        self.assertIn(
            "creates no typed capacity row",
            meta["evidence"][0]["metadata"]["scale_metric_guardrail"],
        )
        self.assertEqual(meta["capacities"], [])

        frontier = documents[
            "curated-official-2026-07-19-vantage-frontier-shackelford.json"
        ]
        oracle_aerial = next(
            evidence
            for evidence in frontier["evidence"]
            if evidence["key"]
            == "oracle-data-centers-shackelford-aerials-captured-2026-07-19"
        )
        self.assertEqual(
            oracle_aerial["metadata"]["power_capacity_as_reported_mw"],
            115,
        )
        self.assertIn(
            "creates no capacity row",
            oracle_aerial["metadata"]["power_metric_guardrail"],
        )
        self.assertEqual(len(frontier["capacities"]), 1)
        self.assertEqual(
            {
                key: frontier["capacities"][0][key]
                for key in ("metric", "stage", "unit", "low", "base", "high")
            },
            {
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 1400,
                "base": 1400,
                "high": 1400,
            },
        )

        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {
            row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entities) - previous_keys, NEW_ENTITY_KEYS)
        for stable_key in NEW_ENTITY_KEYS:
            entity = entities[stable_key]
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual(entity["geometry_json"], "null")
            self.assertEqual(
                (entity["owner"], entity["operator"], entity["users"]),
                ("", "", ""),
            )
            self.assertEqual(entity["operating_model"], "")

        for stable_key, (status, as_of, method) in EXPECTED_STATUSES.items():
            entity = entities[stable_key]
            self.assertEqual(entity["status"], status)
            self.assertEqual(entity["status_as_of"], as_of)
            self.assertEqual(entity["status_method"], method)
            self.assertNotIn(status, {"commissioning", "operational"})

        added_pipeline_keys = {
            row["stable_key"]
            for row in rows(RELEASE / "construction_pipeline.csv")
            if row["stable_key"] in NEW_ENTITY_KEYS
        }
        self.assertEqual(added_pipeline_keys, set(EXPECTED_STATUSES))

        entity_id_to_key = {
            row["entity_id"]: row["stable_key"] for row in entities.values()
        }
        observed_capacities = {
            (
                entity_id_to_key[row["entity_id"]],
                row["metric"],
                row["stage"],
                float(row["base"]),
            )
            for row in rows(RELEASE / "capacity_estimates.csv")
            if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
        }
        self.assertEqual(observed_capacities, EXPECTED_CAPACITIES)
        self.assertEqual(
            {
                metric for _, metric, _, _ in observed_capacities
            },
            {"critical_it_mw"},
        )

        observed_workloads = {}
        for stable_key in NEW_ENTITY_KEYS:
            workloads = json.loads(entities[stable_key]["workloads_json"])
            if workloads:
                self.assertEqual(len(workloads), 1)
                observed_workloads[stable_key] = workloads[0]["workload"]
        self.assertEqual(observed_workloads, EXPECTED_WORKLOADS)


if __name__ == "__main__":
    unittest.main()
