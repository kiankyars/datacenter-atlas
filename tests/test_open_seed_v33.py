from __future__ import annotations

from collections import Counter
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import (
    OpenSeedReleaseError,
    validate_open_seed_release,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v33.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v32.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v32"

DEFINITION_SHA256 = "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
MANIFEST_SHA256 = "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
PREVIOUS_DEFINITION_SHA256 = (
    "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
)
PREVIOUS_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)
RECORDED_AT = "2026-07-19T23:59:00Z"

MINOH_SOURCE = "curated-official-2026-07-19-esr-colt-minoh-osaka-phase-1.json"
LAHTI_SOURCE = "curated-official-2026-07-19-dayone-kiverio-lahti.json"
LUMI_SOURCE = "curated-official-2026-07-19-csc-lumi-ai-kajaani.json"
ADANI_SOURCE = "curated-official-2026-07-19-adani-info-valley-bhubaneswar.json"

SOURCE_HASHES = {
    MINOH_SOURCE: "effde4481c0a5859cfbfdde3fdce575772c0c9d2d32f3a9c5fd8610b71f3d8f7",
    LAHTI_SOURCE: "5367f4c31b48423a418861e3a8e06611c56213578d92ee6d632a5ada191206a4",
    LUMI_SOURCE: "36ec0668806dff0891a2ad8647938b48daa6c32ec95137fcd0e3899dbc596c12",
    ADANI_SOURCE: "3d64e7a63c433bf9f43c4c6efe1425766543ad05b77459d30b4aab988db156f9",
}
TRANCHE_TEST_SHA256 = (
    "a3dc66cc11bbe048098bac88e6d55017f03c699152944d5bb665cbdd86a87ec9"
)
CONTENT_HASHES = {
    MINOH_SOURCE: "85960a34edbbea3d2c96d2c89c672ec78b445744512d1fc2e939f154acfcca66",
    LAHTI_SOURCE: "6c0507925789191c036609350640bf3af98aac27425a677ed65fe83825606810",
    LUMI_SOURCE: "a3a5ec6874edde9f171d48731c8db083ef8913fb059b92d262aca0d51d6b9fbf",
    ADANI_SOURCE: "486723459bb190385b061a517c7a021aa351c5fd770310b1374db4f5b740c8d4",
}
SOURCE_FAMILIES = {
    MINOH_SOURCE: "esr_newsroom",
    LAHTI_SOURCE: "srv_cision_press_releases",
    LUMI_SOURCE: "csc_news_and_blog",
    ADANI_SOURCE: "adani_connect_magazine",
}
NEW_SOURCE_FAMILIES = set(SOURCE_FAMILIES.values())

CAMPUS_KEYS = {
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site",
    "curated:dayone-kiverio-lahti-unnamed-data-center-campus",
    "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani",
    "curated:adani-info-valley-bhubaneswar-data-centre-campus",
}
PROJECT_FACTS = {
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1": (
        "site_preparation",
        "2025-10-16",
        "authoritative_physical_status_update",
    ),
    (
        "curated:dayone-kiverio-lahti-unnamed-data-center-campus:"
        "unnamed-construction-project"
    ): (
        "under_construction",
        "2026-04-07",
        "authoritative_construction_start",
    ),
    "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani:current-build": (
        "under_construction",
        "2026-03-17",
        "authoritative_physical_status_update",
    ),
    (
        "curated:adani-info-valley-bhubaneswar-data-centre-campus:"
        "groundbreaking-project"
    ): (
        "under_construction",
        "2026-05-01",
        "authoritative_construction_start",
    ),
}
PROJECT_KEYS = set(PROJECT_FACTS)
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS

EXPECTED_ROLES = {
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site": {
        "owner": ["ESR–Colt DCS joint venture"],
        "developer": ["ESR–Colt DCS joint venture"],
    },
    "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1": {
        "developer": ["ESR–Colt DCS joint venture"],
        "operator": ["Colt Data Centre Services"],
    },
    "curated:dayone-kiverio-lahti-unnamed-data-center-campus": {},
    (
        "curated:dayone-kiverio-lahti-unnamed-data-center-campus:"
        "unnamed-construction-project"
    ): {},
    "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani": {},
    "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani:current-build": {
        "contractor": ["SRV"]
    },
    "curated:adani-info-valley-bhubaneswar-data-centre-campus": {},
    (
        "curated:adani-info-valley-bhubaneswar-data-centre-campus:"
        "groundbreaking-project"
    ): {},
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_signature(row: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(row.items()))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(row_signature(row) for row in rows(path))


def added_rows(filename: str) -> list[dict[str, str]]:
    previous = row_counter(PREVIOUS_RELEASE / filename)
    added: list[dict[str, str]] = []
    for row in rows(RELEASE / filename):
        signature = row_signature(row)
        if previous[signature]:
            previous[signature] -= 1
        else:
            added.append(row)
    return added


class OpenSeedV33Tests(unittest.TestCase):
    def _offline_patches(self) -> tuple[object, ...]:
        error = AssertionError("offline validator attempted network access")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

    def _load_documents(self) -> dict[str, dict[str, object]]:
        return {
            filename: json.loads(
                (ROOT / "sources" / filename).read_text(encoding="utf-8")
            )
            for filename in SOURCE_HASHES
        }

    def _assert_source_contract(
        self, filename: str, document: dict[str, object]
    ) -> None:
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
        self.assertEqual(document["schema_version"], "1.0")
        evidence = document["evidence"]
        self.assertIsInstance(evidence, list)
        self.assertEqual(len(evidence), 1)
        evidence_row = evidence[0]
        self.assertEqual(evidence_row["kind"], "company_disclosure")
        self.assertEqual(evidence_row["content_hash"], CONTENT_HASHES[filename])
        self.assertEqual(evidence_row["source_family"], SOURCE_FAMILIES[filename])
        self.assertEqual(evidence_row["license"], "all-rights-reserved")

        campus = document["campus"]
        project = document["project"]
        self.assertIn(campus["stable_key"], CAMPUS_KEYS)
        self.assertIn(project["stable_key"], PROJECT_KEYS)
        for entity in (campus, project):
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["roles"], EXPECTED_ROLES[entity["stable_key"]])

        status, as_of_date, method = PROJECT_FACTS[project["stable_key"]]
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": status,
                    "evidence_key": evidence_row["key"],
                    "as_of_date": as_of_date,
                    "method": method,
                    "confidence": project["confidence"],
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])

        capacities = document["capacities"]
        if filename == MINOH_SOURCE:
            self.assertEqual(len(capacities), 2)
            self.assertEqual([row["entity"] for row in capacities], ["campus", "project"])
            self.assertEqual([row["base"] for row in capacities], [130, 65])
            for row in capacities:
                self.assertEqual(row["metric"], "gross_facility_mw")
                self.assertEqual(row["stage"], "planned")
                self.assertEqual(row["unit"], "MW")
                self.assertEqual(row["low"], row["base"])
                self.assertEqual(row["high"], row["base"])
                self.assertIsNone(row["target_date"])
                self.assertIn("non-additive", row["notes"])
                self.assertIn("not IT, grid, generation, current load, or energy", row["notes"])
        else:
            self.assertEqual(capacities, [])

        metadata = evidence_row["metadata"]
        self.assertIn("computer vision", metadata["imagery_guardrail"])
        self.assertIn("unique-site claim", metadata["locality_guardrail"])
        if filename == MINOH_SOURCE:
            self.assertEqual(metadata["site_facility_load_mw_as_reported"], 130)
            self.assertEqual(metadata["phase_1_facility_load_mw_as_reported"], 65)
            self.assertIn("not additive", metadata["capacity_scope"])
            self.assertIn("Neither figure is critical IT load", metadata["capacity_guardrail"])
            self.assertIn("scheduled to begin in 2027", metadata["building_construction_forecast_as_reported"])
            self.assertIn("late 2029", metadata["ready_for_service_forecast_as_reported"])
        elif filename == LAHTI_SOURCE:
            self.assertEqual(metadata["operation_forecast_as_reported"], "during 2027")
            self.assertIn("one unnamed campus", metadata["identity_guardrail"])
            self.assertIn("no power", metadata["energy_guardrail"])
        elif filename == LUMI_SOURCE:
            self.assertEqual(
                metadata["identity_aliases_as_reported"],
                ["LUMI-AI data center", "LUMI AI Factory data center"],
            )
            self.assertEqual(
                metadata["planned_hosts_as_reported"],
                ["EuroHPC LUMI-AI supercomputer", "LUMI-IQ quantum computer"],
            )
            self.assertIn("schema cannot stage", metadata["planned_hosting_guardrail"])
            self.assertIn("Roihu", metadata["collision_guardrail"])
            self.assertIn("not merged", metadata["collision_guardrail"])
        elif filename == ADANI_SOURCE:
            self.assertIsNone(evidence_row["published_at"])
            self.assertEqual(metadata["status_date_precision"], "month")
            self.assertIn("2026-05-01", metadata["status_as_of_normalization"])
            self.assertEqual(metadata["data_center_investment_inr_crore_as_reported"], 800)
            self.assertEqual(
                metadata["three_project_combined_investment_inr_crore_minimum_as_reported"],
                33000,
            )
            self.assertIn("three-project aggregate", metadata["investment_guardrail"])
            self.assertIn("AdaniConneX", metadata["role_guardrail"])

    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertTrue(entries)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in entries))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries))
        frozen = {path.name: path.read_bytes() for path in entries}

        patches = self._offline_patches()
        for network_patch in patches:
            network_patch.start()
        try:
            first = validate_open_seed_release(DEFINITION, RELEASE)
            self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
            second = validate_open_seed_release(DEFINITION, RELEASE)
        finally:
            for network_patch in reversed(patches):
                network_patch.stop()

        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 378)
        self.assertEqual(first["entities_by_kind"], {"campus": 220, "project": 158})
        self.assertEqual(first["evidence_records"], 230)
        self.assertEqual(first["capacity_estimates"], 403)
        self.assertEqual(first["construction_pipeline_records"], 199)
        self.assertEqual(first["construction_source_signals"], 165)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 378)
        self.assertEqual(summary["projects_total"], 158)
        self.assertEqual(summary["evidence_total"], 256)
        self.assertEqual(summary["entities_by_status"]["site_preparation"], 10)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 130)
        self.assertEqual(summary["entities_by_country"]["Finland"], 17)
        self.assertEqual(summary["entities_by_country"]["India"], 8)
        self.assertEqual(summary["entities_by_country"]["Japan"], 16)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(
            summary["capacity_base_totals"]["gross_facility_mw"]["planned"],
            {"base": 195.0, "count": 2, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4874.6, "count": 45, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["grid_connection_mw"]["contracted"],
            {"base": 2560.0, "count": 5, "unit": "MW"},
        )

    def test_v32_closure_and_exact_multiset_additivity(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PREVIOUS_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PREVIOUS_RELEASE.iterdir()
            )
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
            previous = row_counter(PREVIOUS_RELEASE / filename)
            current = row_counter(RELEASE / filename)
            self.assertEqual(previous & current, previous, filename)
            self.assertEqual(sum(current.values()) - sum(previous.values()), expected_delta)
            self.assertEqual(sum((current - previous).values()), expected_delta, filename)
            self.assertEqual(sum((previous - current).values()), 0, filename)

        previous_geojson = json.loads(
            (PREVIOUS_RELEASE / "atlas.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads((RELEASE / "atlas.geojson").read_text(encoding="utf-8"))
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
        self.assertTrue(all(current_features[key]["geometry"] is None for key in NEW_ENTITY_KEYS))

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
        previous_records = Counter(json.dumps(row, sort_keys=True) for row in previous_sources)
        current_records = Counter(json.dumps(row, sort_keys=True) for row in current_sources)
        self.assertEqual(previous_records & current_records, previous_records)
        added_sources = [json.loads(row) for row in (current_records - previous_records).elements()]
        self.assertEqual(len(previous_sources), 153)
        self.assertEqual(len(current_sources), 157)
        self.assertEqual(len(added_sources), 4)
        self.assertEqual(
            {row["provenance"]["content_hash"] for row in added_sources},
            set(CONTENT_HASHES.values()),
        )
        self.assertEqual(
            {row["source_family"] for row in added_sources}, NEW_SOURCE_FAMILIES
        )

        previous_manifest = json.loads(
            (PREVIOUS_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        current_manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(current_manifest["source_families"])
            - set(previous_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(
            set(previous_manifest["source_families"])
            - set(current_manifest["source_families"]),
            set(),
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        expected_summary = copy.deepcopy(previous_summary)
        expected_summary["recorded_at"] = RECORDED_AT
        expected_summary["campuses_total"] += 4
        expected_summary["projects_total"] += 4
        expected_summary["entities_total"] += 8
        expected_summary["entities_by_kind"]["campus"] += 4
        expected_summary["entities_by_kind"]["project"] += 4
        expected_summary["entities_by_country"]["Finland"] += 4
        expected_summary["entities_by_country"]["India"] += 2
        expected_summary["entities_by_country"]["Japan"] += 2
        expected_summary["entities_by_status"]["site_preparation"] += 1
        expected_summary["entities_by_status"]["under_construction"] += 3
        expected_summary["country_assignment_counts"]["not_evaluated"] += 8
        expected_summary["country_source_claims_by_method"]["source_explicit_country_tag"] += 8
        expected_summary["country_source_tag_fallbacks"] += 8
        expected_summary["evidence_total"] += 4
        expected_summary["evidence_by_kind"]["company_disclosure"] += 4
        expected_summary["lifecycle_observations_current"] += 4
        expected_summary["capacity_estimates_current"] += 2
        expected_summary["capacity_estimates_by_metric"]["gross_facility_mw"] += 2
        expected_summary["capacity_estimates_by_stage"]["planned"] += 2
        expected_summary["capacity_base_totals"]["gross_facility_mw"]["planned"] = {
            "base": 195.0,
            "count": 2,
            "unit": "MW",
        }
        expected_summary["construction_pipeline_records"] += 4
        expected_summary["construction_source_signals"] += 4
        self.assertEqual(current_summary, expected_summary)

    def test_definition_is_exactly_four_sorted_inputs_additive(self) -> None:
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
        self.assertEqual(len(previous_inputs), 157)
        self.assertEqual(len(current_inputs), 161)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v33")
        self.assertEqual(current["build"]["as_of"], previous["build"]["as_of"])
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in set(previous) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], previous[key], key)

        definition_inputs = {
            Path(record["path"]).name: record["sha256"]
            for record in current["curated_inputs"]
        }
        for filename, expected_hash in SOURCE_HASHES.items():
            path = ROOT / "sources" / filename
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(definition_inputs[filename], expected_hash)

    def test_source_contract_and_metadata_guardrails_are_pinned(self) -> None:
        tranche_test = ROOT / "tests" / "test_curated_esr_dayone_csc_adani.py"
        self.assertEqual(
            hashlib.sha256(tranche_test.read_bytes()).hexdigest(), TRANCHE_TEST_SHA256
        )
        documents = self._load_documents()
        self.assertEqual(len(documents), 4)
        for filename, document in documents.items():
            with self.subTest(source=filename):
                self._assert_source_contract(filename, document)

        self.assertEqual(
            {document["campus"]["stable_key"] for document in documents.values()},
            CAMPUS_KEYS,
        )
        self.assertEqual(
            {document["project"]["stable_key"] for document in documents.values()},
            PROJECT_KEYS,
        )
        self.assertEqual(
            {document["evidence"][0]["content_hash"] for document in documents.values()},
            set(CONTENT_HASHES.values()),
        )

    def test_export_adds_only_narrow_rows_without_semantic_leakage(self) -> None:
        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_rows = {
            row["stable_key"]: row for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entity_rows) - set(previous_rows), NEW_ENTITY_KEYS)
        self.assertEqual({key: entity_rows[key] for key in previous_rows}, previous_rows)
        self.assertEqual(len(entity_rows), len(rows(RELEASE / "entities.csv")))

        expected_tag_roles = {
            key: {f"role:{role}": values[0] for role, values in roles.items()}
            for key, roles in EXPECTED_ROLES.items()
        }
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            roles = {
                name: value
                for name, value in json.loads(row["tags_json"]).items()
                if name.startswith("role:")
            }
            self.assertEqual(roles, expected_tag_roles[key])
        self.assertEqual(
            entity_rows["curated:esr-colt-dcs-minoh-osaka-data-centre-site"]["owner"],
            "ESR–Colt DCS joint venture",
        )
        self.assertEqual(
            entity_rows[
                "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1"
            ]["operator"],
            "Colt Data Centre Services",
        )
        for key in CAMPUS_KEYS:
            self.assertEqual(entity_rows[key]["status"], "")
            self.assertEqual(entity_rows[key]["status_method"], "")
        for key, (status, as_of_date, method) in PROJECT_FACTS.items():
            self.assertEqual(entity_rows[key]["status"], status)
            self.assertEqual(entity_rows[key]["status_as_of"], as_of_date)
            self.assertEqual(entity_rows[key]["status_method"], method)

        entity_id_to_key = {row["entity_id"]: row["stable_key"] for row in entity_rows.values()}
        capacity_rows = added_rows("capacity_estimates.csv")
        self.assertEqual(len(capacity_rows), 2)
        capacity_by_key = {
            entity_id_to_key[row["entity_id"]]: row for row in capacity_rows
        }
        self.assertEqual(set(capacity_by_key), {
            "curated:esr-colt-dcs-minoh-osaka-data-centre-site",
            "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1",
        })
        self.assertEqual(
            {
                key: float(row["base"])
                for key, row in capacity_by_key.items()
            },
            {
                "curated:esr-colt-dcs-minoh-osaka-data-centre-site": 130.0,
                "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1": 65.0,
            },
        )
        for row in capacity_rows:
            self.assertEqual(row["metric"], "gross_facility_mw")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertEqual(row["low"], row["base"])
            self.assertEqual(row["high"], row["base"])
            self.assertEqual(row["target_date"], "")
            self.assertIn("non-additive", row["notes"])
            self.assertIn("not IT, grid, generation, current load, or energy", row["notes"])

        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        signal_rows = added_rows("construction_source_signals.csv")
        self.assertEqual(len(signal_rows), 4)
        self.assertEqual(
            {row["source_content_hash"] for row in signal_rows},
            set(CONTENT_HASHES.values()),
        )
        self.assertEqual({row["source_family"] for row in signal_rows}, NEW_SOURCE_FAMILIES)
        self.assertTrue(all(row["affected_entity_count"] == "1" for row in signal_rows))
        self.assertEqual(
            {
                json.loads(row["affected_entities_json"])[0]["stable_key"]
                for row in signal_rows
            },
            PROJECT_KEYS,
        )
        evidence_rows = added_rows("evidence.csv")
        self.assertEqual(len(evidence_rows), 4)
        self.assertEqual(
            {row["content_hash"] for row in evidence_rows}, set(CONTENT_HASHES.values())
        )
        self.assertEqual(added_rows("resolution_candidates.csv"), [])

    def test_release_and_semantic_mutations_fail_closed(self) -> None:
        documents = self._load_documents()
        mutations: list[tuple[str, dict[str, object]]] = []

        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["capacities"][0]["metric"] = "critical_it_mw"
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["capacities"][1]["base"] = 195
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["project"]["roles"] = {"operator": ["DayOne"]}
        mutations.append((LAHTI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["workloads"] = [{"forbidden": "future host is not current workload"}]
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["lifecycle"][0]["as_of_date"] = "2026-05-06"
        mutations.append((ADANI_SOURCE, mutated))

        for filename, document in mutations:
            with self.subTest(source=filename):
                with self.assertRaises(AssertionError):
                    self._assert_source_contract(filename, document)

        release_mutations = ("changed-file", "extra-file")
        for mutation in release_mutations:
            with self.subTest(release_mutation=mutation), tempfile.TemporaryDirectory() as temp:
                candidate = Path(temp) / "release"
                shutil.copytree(RELEASE, candidate)
                candidate.chmod(0o755)
                for path in candidate.iterdir():
                    path.chmod(0o644)
                if mutation == "changed-file":
                    entities = candidate / "entities.csv"
                    entities.write_bytes(entities.read_bytes() + b"\n")
                else:
                    (candidate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
                patches = self._offline_patches()
                for network_patch in patches:
                    network_patch.start()
                try:
                    with self.assertRaises(OpenSeedReleaseError):
                        validate_open_seed_release(
                            DEFINITION, candidate, require_frozen=False
                        )
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()


if __name__ == "__main__":
    unittest.main()
