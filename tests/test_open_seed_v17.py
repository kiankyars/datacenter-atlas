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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v17.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v17"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v16.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v16"
TRANCHE_TEST = ROOT / "tests" / "test_curated_global_official_next_tranche.py"

DEFINITION_SHA256 = "27b5ffa3cbe6442435e5b474d957490a761a75db841d0824cdd030684c962f01"
MANIFEST_SHA256 = "eb6d8e06d1989afc487291572083c8c0530b72b860ca90b1e9d462620d5e6a94"
PREVIOUS_DEFINITION_SHA256 = (
    "18ea978b258a66144e1d3a5c7a6eae955ec5776ad560b774df7ff29f8d146ab3"
)
PREVIOUS_MANIFEST_SHA256 = (
    "849eac3da58ea5acfcc221032e4d49d1d40639f1586255f526d836ab32c3b411"
)
TRANCHE_TEST_SHA256 = (
    "92ab147090aa6273bf0acf71d0cfd01b97dde701e61c23b13ae345c946b81b93"
)

SOURCE_HASHES = {
    "curated-official-2026-07-19-aligned-project-caprock-hale-county.json": (
        "d3b3e5747bd10b5a654f6000f0ccf52fc7cd5e6ccdac5c2a4f96654147168cb7"
    ),
    "curated-official-2026-07-19-atnorth-fin02-espoo-expansion.json": (
        "3f2429e4d29d7550440f93e927e42425ea98ab21eb56e6fa9891eb762195d144"
    ),
    "curated-official-2026-07-19-equinix-db7x-blanchardstown.json": (
        "f61109cc0142901d53e2581a8a86e9f6698e44858f7eb9058c8cea5d696bdf49"
    ),
    "curated-official-2026-07-19-prime-phx01-avondale-buildings-1-3.json": (
        "29d808e0ceec2714bc87427e623ea4151c4bb7769eba404054e1ee419e23d0a6"
    ),
    "curated-official-2026-07-19-prime-smf02-sacramento.json": (
        "f8e0ee48af75b3aed382eaee3a85e50df7ea5ddcaeb909289c2837cb0fe40549"
    ),
    "curated-official-2026-07-19-retelit-milan-corsico.json": (
        "9ef4402a9dee22d6b7b1c006961c36e0c9e45bbacc3bf51adeb2ec69a93ce96c"
    ),
    "curated-official-2026-07-19-xneelo-samrand-second-facility.json": (
        "96726ac469d19c6484a0cda436f2e331bec992cfb29948fae9b0247269509d86"
    ),
}

CAMPUS_KEYS = {
    "curated:aligned-project-caprock-hale-county-campus",
    "curated:atnorth-fin02-espoo-data-center",
    "curated:equinix-db7x-blanchardstown-dublin",
    "curated:prime-phx01-avondale-campus",
    "curated:prime-sacramento-data-center-campus",
    "curated:retelit-milan-corsico-data-centre",
    "curated:xneelo-samrand-data-centre-campus",
}

EXPECTED_PROJECTS = {
    "curated:aligned-project-caprock-hale-county-campus:current-campus-development": (
        "2026-04-09",
        "authoritative_construction_start",
    ),
    "curated:atnorth-fin02-espoo-data-center:current-expansion-building": (
        "2026-05-04",
        "authoritative_physical_status_update",
    ),
    "curated:equinix-db7x-blanchardstown-dublin:current-facility-build": (
        "2026-03-20",
        "authoritative_construction_start",
    ),
    "curated:prime-phx01-avondale-campus:buildings-1-3-current-phase": (
        "2026-05-21",
        "authoritative_construction_start",
    ),
    "curated:prime-sacramento-data-center-campus:smf02-current-facility-build": (
        "2026-05-07",
        "authoritative_construction_start",
    ),
    "curated:retelit-milan-corsico-data-centre:current-two-building-development": (
        "2026-05-05",
        "authoritative_construction_start",
    ),
    "curated:xneelo-samrand-data-centre-campus:second-facility-build": (
        "2026-02-03",
        "authoritative_construction_start",
    ),
}

NEW_ENTITY_KEYS = CAMPUS_KEYS | set(EXPECTED_PROJECTS)

EXPECTED_CAPACITIES = {
    (
        "curated:prime-phx01-avondale-campus:buildings-1-3-current-phase",
        "critical_it_mw",
        "planned",
        144.0,
    ),
    (
        "curated:prime-sacramento-data-center-campus:smf02-current-facility-build",
        "critical_it_mw",
        "planned",
        18.0,
    ),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


class OpenSeedV17Tests(unittest.TestCase):
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
        self.assertEqual(first["recorded_at"], "2026-07-19T19:35:00Z")
        self.assertEqual(first["entities"], 237)
        self.assertEqual(first["entities_by_kind"], {"campus": 151, "project": 86})
        self.assertEqual(first["evidence_records"], 173)
        self.assertEqual(first["capacity_estimates"], 375)
        self.assertEqual(first["construction_pipeline_records"], 127)
        self.assertEqual(first["construction_source_signals"], 117)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 237)
        self.assertEqual(summary["projects_total"], 86)
        self.assertEqual(summary["evidence_total"], 190)
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
                "under_construction": 80,
            },
        )

    def test_v16_closure_is_sealed_and_v17_is_exactly_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 14,
            "evidence.csv": 7,
            "capacity_estimates.csv": 2,
            "construction_pipeline.csv": 7,
            "construction_source_signals.csv": 7,
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
        self.assertEqual(len(previous_inputs), 81)
        self.assertEqual(len(current_inputs), 88)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )

    def test_new_sources_and_rows_keep_accepted_semantics(self) -> None:
        self.assertEqual(
            hashlib.sha256(TRANCHE_TEST.read_bytes()).hexdigest(),
            TRANCHE_TEST_SHA256,
        )
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
            self.assertEqual(document["workloads"], [])

        db7x = documents[
            "curated-official-2026-07-19-equinix-db7x-blanchardstown.json"
        ]
        self.assertEqual(len(db7x["operating_models"]), 1)
        self.assertEqual(db7x["operating_models"][0]["value"], "retail_colocation")
        for filename, document in documents.items():
            if filename not in {
                "curated-official-2026-07-19-equinix-db7x-blanchardstown.json"
            }:
                self.assertEqual(document["operating_models"], [])

        untyped_claims = {
            "curated-official-2026-07-19-retelit-milan-corsico.json": (
                "capacity_as_reported_mw",
                13.6,
            ),
            "curated-official-2026-07-19-aligned-project-caprock-hale-county.json": (
                "capacity_as_reported_mw",
                540,
            ),
            "curated-official-2026-07-19-atnorth-fin02-espoo-expansion.json": (
                "post_expansion_whole_facility_gross_capacity_as_reported_mw",
                45,
            ),
        }
        for filename, (metadata_key, value) in untyped_claims.items():
            self.assertEqual(documents[filename]["capacities"], [])
            self.assertEqual(
                documents[filename]["evidence"][0]["metadata"][metadata_key],
                value,
            )

        fin02 = documents[
            "curated-official-2026-07-19-atnorth-fin02-espoo-expansion.json"
        ]
        fin02_metadata = fin02["evidence"][0]["metadata"]
        self.assertEqual(
            fin02_metadata["displayed_publication_time_as_reported"],
            "Mon, May 04, 2026 07:30 CET",
        )
        self.assertEqual(fin02_metadata["construction_month_as_reported"], "April 2026")
        self.assertEqual(fin02["lifecycle"][0]["as_of_date"], "2026-05-04")

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
            self.assertEqual(json.loads(entity["workloads_json"]), [])

        for stable_key, (as_of, method) in EXPECTED_PROJECTS.items():
            entity = entities[stable_key]
            self.assertEqual(entity["status"], "under_construction")
            self.assertEqual(entity["status_as_of"], as_of)
            self.assertEqual(entity["status_method"], method)
            self.assertNotIn(entity["status"], {"commissioning", "operational"})

        self.assertEqual(
            entities[
                "curated:equinix-db7x-blanchardstown-dublin:current-facility-build"
            ]["operating_model"],
            "retail_colocation",
        )
        for stable_key in NEW_ENTITY_KEYS - {
            "curated:equinix-db7x-blanchardstown-dublin:current-facility-build"
        }:
            self.assertEqual(entities[stable_key]["operating_model"], "")

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


if __name__ == "__main__":
    unittest.main()
