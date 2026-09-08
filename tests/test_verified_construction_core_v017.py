from __future__ import annotations

import csv
from datetime import date
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree

from datacenter_atlas import verified_construction_core as verified_core_v16
from datacenter_atlas import verified_construction_core_v017 as verified_core
from datacenter_atlas.verified_construction_core_v017 import (
    CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE,
    CURRENT_V17_LIFECYCLE_REFERENCE_DATE,
    CURRENT_V17_PREVIEW_DIR,
    CURRENT_V17_PREVIEW_ID,
    LEGACY_PREVIEW_V16_COMMIT,
    LEGACY_PREVIEW_V16_DIR,
    LEGACY_PREVIEW_V16_MANIFEST_SHA256,
    V17_BATCH_CONTRACT,
    V17_BATCH_CONTRACT_SHA256,
    V17_EXPECTED_COUNTRY_COUNT,
    V17_EXPECTED_DELTA_COUNT,
    V17_EXPECTED_PROJECT_COUNT,
    V17_EXPECTED_SITE_COUNT,
    V17_GEOMETRY_CAPTURE,
    V17_GEOMETRY_CAPTURE_SHA256,
    VerifiedConstructionCoreError,
    build_preview,
    validate_frozen_v16,
    validate_preview,
)


curated_v11 = importlib.import_module(f"{verified_core_v16.__package__}.curated_v11")


def _rows_from(path: Path, name: str) -> list[dict[str, str]]:
    with (path / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _field_definition(
    schema: dict[str, object], table: str, field: str
) -> dict[str, object]:
    table_definition = schema["tables"]
    assert isinstance(table_definition, dict)
    fields = table_definition[table]
    assert isinstance(fields, dict)
    definitions = fields["fields"]
    assert isinstance(definitions, list)
    matches = [row for row in definitions if row.get("name") == field]
    assert len(matches) == 1
    return matches[0]


NEW_CURATED_SOURCES = {
    "sources/curated-official-2026-09-06-cra-prague-gateway-current-campus-build-successor.json": {
        "bytes": 4_324,
        "sha256": "2c800f14b4fb82eb9a3fa1bb1ea7987f0d8cb03a169e936fab379edd3a765981",
        "project_key": "curated:cra-prague-gateway-data-center-campus:current-campus-build",
        "campus_key": "curated:cra-prague-gateway-data-center-campus",
        "status": "under_construction",
        "status_as_of": "2026-08-20",
        "status_method": "authoritative_physical_status_update",
    },
    "sources/curated-official-2026-09-06-dansk-data-center-1-esbjerg-current-build.json": {
        "bytes": 13_990,
        "sha256": "5f2cdc4915678835192f52d929ccea4209b5694ea53666d95130ece966c7ba83",
        "project_key": "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build",
        "campus_key": "curated:dansk-data-center-1-esbjerg-campus",
        "status": "under_construction",
        "status_as_of": "2026-08-13",
        "status_method": "authoritative_construction_start",
    },
    "sources/curated-official-2026-09-06-data-world-matatirtha-current-build.json": {
        "bytes": 4_721,
        "sha256": "ddc6f42bc43ce87344519998ec311798503ea4238125914622e7c643a78056bf",
        "project_key": "curated:data-world-matatirtha-campus:core-data-center-current-build",
        "campus_key": "curated:data-world-matatirtha-campus",
        "status": "under_construction",
        "status_as_of": "2026-07-01",
        "status_method": "authoritative_physical_status_update",
    },
    "sources/curated-official-2026-09-06-datagrid-makarewa-initial-horizontal-works.json": {
        "bytes": 11_987,
        "sha256": "88279a73dae431516cc33112a4a623a42865ab74c702dfec9a4cb0b33a897d6c",
        "project_key": "curated:datagrid-makarewa-ai-factory:initial-horizontal-works",
        "campus_key": "curated:datagrid-makarewa-ai-factory",
        "status": "under_construction",
        "status_as_of": "2026-08-18",
        "status_method": "authoritative_construction_start",
    },
}


EXPECTED_STATUS_AGES = {
    "curated:ascenty-vinhedo-campus:vinhedo-3": 84,
    "curated:cdc-brooklyn-melbourne-campus:remaining-facilities-current-build": 30,
    "curated:cdc-maddington-perth-campus:current-build": 56,
    "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build": 58,
    "curated:cra-prague-gateway-data-center-campus:current-campus-build": 0,
    "curated:cyrusone-yorkville-technology-campus:current-site-work": 32,
    "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build": 7,
    "curated:data-world-matatirtha-campus:core-data-center-current-build": 50,
    "curated:datagrid-makarewa-ai-factory:initial-horizontal-works": 2,
    "curated:digipowerx-columbiana-ai-data-center-campus:purpose-built-flagship-vertical-build": 44,
    "curated:edgecore-as02-sterling-virginia-campus:as02-data-center": 50,
    "curated:edged-council-bluffs-data-center-campus:first-data-center": 34,
    "curated:meta-sturgeon-county-alberta-data-center:current-campus-build": 43,
    "curated:microsoft-lyle-creek-conover-data-center:current-build": 81,
    "curated:niger-national-data-center-pk5-niamey:current-build": 63,
    "curated:nxdata3-bucharest-ring-road-campus:nxdata3-buh3": 79,
    "curated:odata-dc-sp04-osasco-campus:phase-2-expansion": 63,
    "curated:qts-eagle-mountain-slc1-data-center-campus:building-2": 50,
    "curated:related-digital-cheyenne-campus:phase-1": 31,
    "curated:vantage-lighthouse-port-washington-campus:current-campus-build": 69,
}


NXDATA_PROJECT_KEY = "curated:nxdata3-bucharest-ring-road-campus:nxdata3-buh3"
NXDATA_SOURCE_ID = "nxdata3-inflect-datacenter-marker"


class VerifiedConstructionCoreV017Tests(unittest.TestCase):
    def _contract(self) -> dict[str, object]:
        return json.loads(V17_BATCH_CONTRACT.read_text(encoding="utf-8"))

    def _capture(self) -> dict[str, object]:
        return json.loads(V17_GEOMETRY_CAPTURE.read_text(encoding="utf-8"))

    def _delta_project_keys(self) -> set[str]:
        contract = self._contract()
        return {row["project_stable_key"] for row in contract["acceptances"]}

    def test_profile_counts_frozen_base_and_portable_inventory(self) -> None:
        self.assertEqual(CURRENT_V17_PREVIEW_ID, "2026-08-20-preview-v0.17")
        self.assertEqual(CURRENT_V17_PREVIEW_DIR.name, CURRENT_V17_PREVIEW_ID)
        self.assertEqual(
            CURRENT_V17_LIFECYCLE_REFERENCE_DATE,
            date(2026, 8, 20),
        )
        self.assertEqual(
            CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE,
            date(2026, 9, 6),
        )
        self.assertEqual(
            validate_frozen_v16()["preview_id"],
            "2026-08-20-preview-v0.16",
        )
        manifest = validate_preview(CURRENT_V17_PREVIEW_DIR)
        self.assertEqual(
            manifest["base_preview_manifest_sha256"],
            LEGACY_PREVIEW_V16_MANIFEST_SHA256,
        )
        self.assertEqual(manifest["base_preview_commit"], LEGACY_PREVIEW_V16_COMMIT)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 100,
                "projects": 103,
                "evidence": 252,
                "countries": 40,
                "non_us_sites": 70,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 98,
            },
        )
        self.assertEqual(len(manifest["portable_source_inputs"]), 138)
        self.assertEqual(
            hashlib.sha256(V17_BATCH_CONTRACT.read_bytes()).hexdigest(),
            V17_BATCH_CONTRACT_SHA256,
        )
        self.assertEqual(V17_BATCH_CONTRACT.stat().st_size, 81_697)
        self.assertEqual(
            hashlib.sha256(V17_GEOMETRY_CAPTURE.read_bytes()).hexdigest(),
            V17_GEOMETRY_CAPTURE_SHA256,
        )
        self.assertEqual(V17_GEOMETRY_CAPTURE.stat().st_size, 81_540)
        portable_paths = {row["path"] for row in manifest["portable_source_inputs"]}
        self.assertIn(
            "definitions/verified-construction-core-v0.17-100-site-batch.json",
            portable_paths,
        )
        self.assertIn(
            "sources/verified-construction-core-v0.17-100-site-geometry-facts.json",
            portable_paths,
        )
        self.assertTrue(set(NEW_CURATED_SOURCES).issubset(portable_paths))
        self.assertFalse(
            any(
                Path(path).suffix.lower() in {".pdf", ".html", ".htm"}
                for path in portable_paths
            )
        )

    def test_exact_twenty_project_site_delta_and_seven_new_countries(self) -> None:
        contract = self._contract()
        capture = self._capture()
        acceptances = contract["acceptances"]
        results = capture["results"]
        self.assertEqual(len(acceptances), V17_EXPECTED_DELTA_COUNT)
        self.assertEqual(len(results), V17_EXPECTED_DELTA_COUNT)
        self.assertEqual(len(contract["source_lineage"]), V17_EXPECTED_DELTA_COUNT)
        self.assertEqual(
            len({row["parent_campus_stable_key"] for row in acceptances}),
            V17_EXPECTED_DELTA_COUNT,
        )
        self.assertEqual(
            {row["project_stable_key"] for row in acceptances},
            {row["project_stable_key"] for row in results},
        )

        base_projects = _rows_from(LEGACY_PREVIEW_V16_DIR, "projects.csv")
        current_projects = _rows_from(CURRENT_V17_PREVIEW_DIR, "projects.csv")
        base_sites = _rows_from(LEGACY_PREVIEW_V16_DIR, "sites.csv")
        current_sites = _rows_from(CURRENT_V17_PREVIEW_DIR, "sites.csv")
        base_evidence = _rows_from(LEGACY_PREVIEW_V16_DIR, "evidence.csv")
        current_evidence = _rows_from(CURRENT_V17_PREVIEW_DIR, "evidence.csv")
        self.assertEqual(len(current_projects), V17_EXPECTED_PROJECT_COUNT)
        self.assertEqual(len(current_sites), V17_EXPECTED_SITE_COUNT)
        self.assertEqual(len(current_evidence), 252)
        self.assertEqual(
            len(
                {row["project_id"] for row in current_projects}
                - {row["project_id"] for row in base_projects}
            ),
            20,
        )
        self.assertEqual(
            len(
                {row["site_id"] for row in current_sites}
                - {row["site_id"] for row in base_sites}
            ),
            20,
        )
        self.assertEqual(
            len(
                {row["evidence_id"] for row in current_evidence}
                - {row["evidence_id"] for row in base_evidence}
            ),
            52,
        )
        base_countries = {row["country_iso_a2"] for row in base_sites}
        current_countries = {row["country_iso_a2"] for row in current_sites}
        self.assertEqual(len(current_countries), V17_EXPECTED_COUNTRY_COUNT)
        self.assertEqual(
            current_countries - base_countries,
            {"CN", "CZ", "DK", "NE", "NP", "NZ", "RO"},
        )

    def test_delta_projects_keep_locator_status_and_sparse_claim_scope(self) -> None:
        contract = self._contract()
        capture = self._capture()
        acceptances = {
            row["project_stable_key"]: row for row in contract["acceptances"]
        }
        results = {row["locator_id"]: row for row in capture["results"]}
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V17_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in acceptances
        }
        self.assertEqual(set(projects), set(acceptances))
        self.assertEqual(len({row["site_id"] for row in projects.values()}), 20)
        for project_key, acceptance in acceptances.items():
            project = projects[project_key]
            result = results[acceptance["locator_id"]]
            geometry = verified_core._canonical_geometry(result)
            self.assertEqual(json.loads(project["geometry_json"]), geometry)
            self.assertEqual(project["geometry_type"], geometry["type"])
            self.assertEqual(
                project["geometry_use_scope"],
                result["semantics"]["geometry_use_scope"],
            )
            self.assertEqual(
                project["geometry_source_entity_kind"],
                result["semantics"]["geometry_source_entity_kind"],
            )
            self.assertEqual(
                project["last_observed_physical_status"],
                acceptance["status"]["value"],
            )
            self.assertEqual(project["status_as_of"], acceptance["status"]["as_of_date"])
            self.assertEqual(project["status_method"], acceptance["status"]["method"])
            self.assertEqual(
                project["status_evidence_id"],
                acceptance["status"]["evidence_id"],
            )
            self.assertEqual(
                int(project["status_age_days_at_review"]),
                EXPECTED_STATUS_AGES[project_key],
            )
            self.assertEqual(
                project["verification_posture"],
                "recent_authoritative_physical_observation_plus_reviewed_site_locator",
            )
            self.assertEqual(project["independent_imagery_verification"], "false")
            self.assertEqual(project["imagery_review_outcome"], "not_reviewed_for_core_preview")
            self.assertEqual(project["development_type"], "unknown")
            self.assertEqual(project["operating_model"], "unknown")
            for field in (
                "workloads_json",
                "role_claims_json",
                "power_observations_json",
                "annual_energy_observations_json",
                "efficiency_observations_json",
            ):
                self.assertEqual(project[field], "[]", f"{project_key}: {field}")
            for field in ("owner", "operator", "users", "tenants", "customers"):
                self.assertEqual(project[field], "", f"{project_key}: {field}")
            for field in (
                "development_type_unknown_reason",
                "operating_model_unknown_reason",
                "workload_unknown_reason",
                "power_unknown_reason",
                "annual_energy_unknown_reason",
                "efficiency_unknown_reason",
            ):
                self.assertTrue(project[field], f"{project_key}: {field}")

    def test_identity_only_and_overlap_source_roles_are_exact(self) -> None:
        capture = self._capture()
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V17_PREVIEW_DIR, "evidence.csv")
        }
        identity_only: set[str] = set()
        overlap: set[str] = set()
        for result in capture["results"]:
            geometry_ids = set(result["geometry_source_document_ids"])
            identity_ids = set(result["identity_source_document_ids"])
            identity_only.update(identity_ids - geometry_ids)
            overlap.update(identity_ids & geometry_ids)
        self.assertEqual(
            identity_only,
            {
                "meta-sturgeon-dp26-0028-permit-notice",
                "datagrid-makarewa-sdc-resource-consent-application",
                "ddc1-esbjerg-dma-facility-record",
            },
        )
        self.assertEqual(
            overlap,
            {
                "china-mobile-haidong-phase2-stage1-eia",
                "cra-prague-gateway-cuzk-permit-parcels",
                "data-world-matatirtha-first-party-kathmandu-marker",
                "niger-national-dc-pk5-bnee-eies",
                "nxdata3-inflect-datacenter-marker",
            },
        )
        for source_id in identity_only:
            evidence_id = verified_core._capture_evidence(documents[source_id])[
                "evidence_id"
            ]
            roles = json.loads(evidence[evidence_id]["roles_json"])
            self.assertEqual(roles, ["context:geometry_identity"])
            self.assertNotIn("geometry", roles)
        for source_id in overlap:
            evidence_id = verified_core._capture_evidence(documents[source_id])[
                "evidence_id"
            ]
            self.assertEqual(
                json.loads(evidence[evidence_id]["roles_json"]),
                ["context:geometry_identity", "geometry"],
            )
        for source_id in (
            "meta-sturgeon-alberta-ats-quarter-sections",
            "datagrid-makarewa-linz-four-primary-parcels",
            "ddc1-esbjerg-dar-sahara-9-address-point",
        ):
            evidence_id = verified_core._capture_evidence(documents[source_id])[
                "evidence_id"
            ]
            self.assertEqual(json.loads(evidence[evidence_id]["roles_json"]), ["geometry"])

    def test_capture_rights_nonredistribution_and_usage_are_exact(self) -> None:
        capture = self._capture()
        documents = {row["source_id"]: row for row in capture["source_documents"]}
        results = capture["results"]
        evidence = {
            row["evidence_id"]: row
            for row in _rows_from(CURRENT_V17_PREVIEW_DIR, "evidence.csv")
        }
        self.assertEqual(len(documents), 24)
        bound_ids: set[str] = set()
        for result in results:
            bound_ids.update(result["geometry_source_document_ids"])
            bound_ids.update(result["identity_source_document_ids"])
        self.assertEqual(bound_ids, set(documents))
        capture_evidence_ids = {
            verified_core._capture_evidence(document)["evidence_id"]
            for document in documents.values()
        }
        self.assertEqual(len(capture_evidence_ids), 24)
        self.assertTrue(capture_evidence_ids.issubset(evidence))
        for document in documents.values():
            self.assertIs(document["capture"]["redistributed"], False)
            self.assertEqual(document["capture"]["sha256"], document["content_hash"])
            self.assertGreater(document["capture"]["bytes"], 0)
            self.assertTrue(document["capture"]["capture_kind"])
            self.assertNotIn("content", document["capture"])
            self.assertNotIn("path", document["capture"])
        self.assertEqual(
            documents["datagrid-makarewa-linz-four-primary-parcels"]["license"],
            "CC-BY-4.0",
        )
        self.assertEqual(
            documents["ddc1-esbjerg-dar-sahara-9-address-point"]["license"],
            "CC-BY-4.0",
        )
        self.assertEqual(
            documents["nxdata3-inflect-datacenter-marker"]["license"],
            "all-rights-reserved-fact-extraction-only",
        )

    def test_map_footer_and_attribution_preserve_required_source_credits(self) -> None:
        contracts = verified_core._contracts()
        geojson = json.loads(
            (CURRENT_V17_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        sites = _rows_from(CURRENT_V17_PREVIEW_DIR, "sites.csv")
        evidence = _rows_from(CURRENT_V17_PREVIEW_DIR, "evidence.csv")
        map_html = verified_core._map_html(geojson, sites, evidence).decode("utf-8")
        self.assertEqual(map_html.count("<footer>"), 1)
        footer = ElementTree.fromstring(
            "<footer>" + map_html.split("<footer>", 1)[1].split("</footer>", 1)[0]
            + "</footer>"
        )
        visible_credit = "".join(footer.itertext())
        for credit in (
            "Crown copyright — Land Information New Zealand (LINZ)",
            "Klimadatastyrelsen / Danmarks Adresseregister (DAR)",
            "Government of Alberta",
        ):
            self.assertIn(credit, visible_credit)
        rights_links = {link.get("href") for link in footer.iter("a")}
        self.assertTrue(
            {
                "https://data.linz.govt.nz/license/attribution-4-0-international/",
                "https://creativecommons.org/licenses/by/4.0/",
                "https://open.alberta.ca/licence",
            }.issubset(rights_links)
        )

        attribution = verified_core._attribution(
            evidence, "Test legal notice", contracts
        ).decode("utf-8")
        self.assertIn(
            "Contains information licensed under the Open Government Licence – Alberta.",
            attribution,
        )
        documents = contracts["capture"]["source_documents"]
        self.assertEqual(len(documents), 24)
        for document in documents:
            with self.subTest(source=document["source_id"]):
                credit_lines = [
                    line
                    for line in attribution.splitlines()
                    if line.startswith(f"- {document['source_id']}:")
                ]
                self.assertEqual(len(credit_lines), 1)
                self.assertIn(document["attribution"], credit_lines[0])
                for rights_url in document.get("rights_urls", []):
                    self.assertIn(rights_url, credit_lines[0])

    def test_exact_geometry_hashes_and_batch_invariants_are_pinned(self) -> None:
        contract = self._contract()
        capture = self._capture()
        results = {row["locator_id"]: row for row in capture["results"]}
        expected = {
            "datagrid-makarewa-linz-four-core-parcel-union": (
                541,
                "839bcebf9f75a452c6bd24107c68f09768013a5e36b38c1fee26e0a1b0a7bae8",
            ),
            "niger-national-dc-pk5-bnee-eies-project-point": (
                63,
                "d13a66d949372650c0e5a5afbcad4363f8a090e3efbd0e987b39fea3614a61b5",
            ),
            "china-mobile-haidong-phase2-stage1-eia-project-point": (
                65,
                "541d5c04be2a6e0239fe72b5312b306e9659de9a71739610ae03f4560c0d7d58",
            ),
            "dansk-data-center-1-esbjerg-dar-sahara-9-address-point": (
                55,
                "218f5db9e4163f4082617f94489fb587136b82afd5c12fabbf02743d1a08604b",
            ),
        }
        for result in results.values():
            geometry = verified_core._canonical_geometry(result)
            canonical = verified_core_v16._json_bytes(geometry)[:-1]
            self.assertEqual(
                result["canonical_geometry"],
                {
                    "bytes_without_newline": len(canonical),
                    "sha256_without_newline": hashlib.sha256(canonical).hexdigest(),
                },
            )
            self.assertIsNone(result["semantics"]["horizontal_uncertainty_metres"])
            self.assertTrue(
                result["semantics"]["horizontal_uncertainty_unknown_reason"]
            )
            self.assertIs(result["semantics"]["official_boundary"], False)
        for locator_id, (byte_count, digest) in expected.items():
            geometry = verified_core._canonical_geometry(results[locator_id])
            canonical = verified_core_v16._json_bytes(geometry)[:-1]
            self.assertEqual(len(canonical), byte_count)
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        self.assertEqual(
            contract["batch_invariants"],
            {
                "accepted_physical_site_count": 20,
                "accepted_project_count": 20,
                "geometry_authority_classes": {
                    "community_source": 1,
                    "official_source": 19,
                },
                "geometry_types": {"Point": 17, "Polygon": 3},
                "geometry_use_scopes": {
                    "campus_locator": 12,
                    "project_locator": 8,
                },
                "independent_imagery_verification": False,
                "numeric_horizontal_uncertainty_rows": 0,
                "official_boundary": False,
                "raw_source_artifacts_redistributed": False,
            },
        )

    def test_lifecycle_window_is_exactly_anchored_to_august_twentieth(self) -> None:
        contract = self._contract()
        projects = {
            row["project_stable_key"]: row
            for row in _rows_from(CURRENT_V17_PREVIEW_DIR, "projects.csv")
            if row["project_stable_key"] in self._delta_project_keys()
        }
        earliest = date(2026, 5, 22)
        latest = date(2026, 8, 20)
        ages: dict[str, int] = {}
        for acceptance in contract["acceptances"]:
            status = acceptance["status"]
            status_date = date.fromisoformat(status["as_of_date"])
            self.assertGreaterEqual(status_date, earliest)
            self.assertLessEqual(status_date, latest)
            self.assertIn(status["value"], verified_core_v16.PHYSICAL_STATUSES)
            self.assertIn(status["method"], verified_core_v16.AUTHORITATIVE_STATUS_METHODS)
            age = (CURRENT_V17_LIFECYCLE_REFERENCE_DATE - status_date).days
            ages[acceptance["project_stable_key"]] = age
            self.assertEqual(
                int(projects[acceptance["project_stable_key"]]["status_age_days_at_review"]),
                age,
            )
        self.assertEqual(ages, EXPECTED_STATUS_AGES)
        self.assertEqual(min(ages.values()), 0)
        self.assertEqual(max(ages.values()), 84)

    def test_selection_accounting_and_promotion_inventory_are_exact(self) -> None:
        contract = self._contract()
        report = json.loads(
            (CURRENT_V17_PREVIEW_DIR / "selection-report.json").read_text(
                encoding="utf-8"
            )
        )
        accounting = contract["source_selection_accounting"]
        self.assertEqual(accounting, report["source_selection_accounting"])
        self.assertEqual(accounting["artifact_selected_projects"], 103)
        self.assertEqual(accounting["v97_pipeline_rows"], 531)
        self.assertEqual(accounting["v97_selected_projects"], 97)
        self.assertEqual(accounting["v97_nonselected_source_rows"], 434)
        self.assertEqual(accounting["post_v97_selected_projects"], 6)
        self.assertEqual(
            accounting["post_v97_selected_project_keys"],
            [
                "curated:cra-prague-gateway-data-center-campus:current-campus-build",
                "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build",
                "curated:data-world-matatirtha-campus:core-data-center-current-build",
                "curated:datagrid-makarewa-ai-factory:initial-horizontal-works",
                "curated:pure-dc-ams01-amsterdam-westpoort-campus:data-hall-development",
                "curated:start-campus-sines-data-campus:sin02-current-facility-build",
            ],
        )
        self.assertEqual(len(accounting["v17_v97_promotions"]), 16)
        self.assertEqual(
            {row["frozen_v16_first_failure"] for row in accounting["v17_v97_promotions"]},
            {"not_in_reviewed_site_geometry_allowlist"},
        )
        self.assertEqual(
            accounting["resulting_v97_first_failure_counts"],
            {
                "entity_kind_not_project": 49,
                "not_in_reviewed_site_geometry_allowlist": 48,
                "selected": 97,
                "status_not_physical": 12,
                "status_outside_90_day_window": 325,
            },
        )
        self.assertEqual(report["selected_project_count"], 103)
        self.assertEqual(report["selected_physical_site_count"], 100)
        self.assertEqual(report["source_pipeline_row_count"], 531)
        self.assertEqual(report["non_selected_source_row_count"], 434)
        self.assertEqual(
            report["non_selected_source_row_count"]
            + accounting["v97_selected_projects"],
            report["source_pipeline_row_count"],
        )

    def test_inherits_v016_rows_and_geojson_features_without_changes(self) -> None:
        for filename, key in (
            ("projects.csv", "project_id"),
            ("sites.csv", "site_id"),
            ("evidence.csv", "evidence_id"),
        ):
            inherited = {
                row[key]: row for row in _rows_from(LEGACY_PREVIEW_V16_DIR, filename)
            }
            current = {
                row[key]: row for row in _rows_from(CURRENT_V17_PREVIEW_DIR, filename)
            }
            self.assertEqual(
                {row_id: current[row_id] for row_id in inherited},
                inherited,
            )
        inherited_geojson = json.loads(
            (LEGACY_PREVIEW_V16_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (CURRENT_V17_PREVIEW_DIR / "sites.geojson").read_text(encoding="utf-8")
        )
        inherited_features = {
            row["properties"]["site_id"]: row
            for row in inherited_geojson["features"]
        }
        current_features = {
            row["properties"]["site_id"]: row for row in current_geojson["features"]
        }
        self.assertEqual(
            {site_id: current_features[site_id] for site_id in inherited_features},
            inherited_features,
        )

    def test_four_new_schema_v11_curated_sources_parse_exactly(self) -> None:
        for relative, expected in NEW_CURATED_SOURCES.items():
            with self.subTest(source=relative):
                path = verified_core.ROOT / relative
                self.assertEqual(path.stat().st_size, expected["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                parsed = curated_v11._parse_document(
                    path,
                    "2026-09-07T04:00:00Z",
                )
                self.assertEqual(parsed.project.stable_key, expected["project_key"])
                self.assertEqual(parsed.campus.stable_key, expected["campus_key"])
                self.assertEqual(len(parsed.lifecycle), 1)
                lifecycle = parsed.lifecycle[0]
                self.assertEqual(lifecycle.entity_ref, "project")
                self.assertEqual(lifecycle.value.value, expected["status"])
                self.assertEqual(lifecycle.as_of_date, expected["status_as_of"])
                self.assertEqual(lifecycle.method, expected["status_method"])

    def test_schema_allowed_values_equal_actual_output_sets(self) -> None:
        schema = json.loads(
            (CURRENT_V17_PREVIEW_DIR / "schema.json").read_text(encoding="utf-8")
        )
        projects = _rows_from(CURRENT_V17_PREVIEW_DIR, "projects.csv")
        sites = _rows_from(CURRENT_V17_PREVIEW_DIR, "sites.csv")
        expected_project_sets = {
            "geometry_type": ["MultiPolygon", "Point", "Polygon"],
            "geometry_source_entity_kind": [
                "address_area",
                "building",
                "campus",
                "facility",
                "project",
            ],
            "geometry_derivation": [
                "capture_replayed_geometry",
                "coordinates_to_point",
                "cross_source_geometry",
                "cross_source_overlay",
                "direct_geometry",
                "first_party_published_map_pin",
                "official_address_feature_to_point",
                "official_address_geocode",
                "official_address_point",
                "official_bag_address_record_to_point",
                "official_coordinate_transform",
                "official_dms_coordinate_to_point",
                "official_georeferenced_drawing_shared_area_centroid_transformed_to_crs84",
                "official_parcel_centroid_to_point",
                "official_parcel_union",
                "official_parcel_union_point_on_surface",
                "official_primary_parcel_union",
                "osm_way_nodes_to_polygon",
                "source_marker_decimal_coordinates_to_point_without_centroiding",
                "source_published_marker_to_point_without_atlas_centroiding",
                "topological_union_of_two_osm_host_development_way_polygons",
            ],
            "geometry_authority_class": [
                "community_mapped",
                "community_source",
                "official_source",
            ],
            "geometry_use_scope": [
                "campus_locator",
                "official_boundary",
                "project_locator",
                "reviewed_site_locator",
            ],
        }
        for field, expected in expected_project_sets.items():
            actual = sorted({row[field] for row in projects})
            self.assertEqual(actual, expected)
            self.assertEqual(
                _field_definition(schema, "projects.csv", field)["allowed_values"],
                actual,
            )
        actual_site_types = sorted({row["geometry_type"] for row in sites})
        self.assertEqual(actual_site_types, ["MultiPolygon", "Point", "Polygon"])
        self.assertEqual(
            _field_definition(schema, "sites.csv", "geometry_type")["allowed_values"],
            actual_site_types,
        )
        self.assertEqual(schema["geojson"]["allowed_geometry_types"], actual_site_types)
        self.assertEqual(
            schema["v0_17_temporal_scope"],
            {
                "cohort_lifecycle_reference_date": "2026-08-20",
                "geometry_identity_reviewed_at": "2026-09-06",
                "reviewed_at_semantics": (
                    "Legacy alias for cohort_lifecycle_reference_date; not the later "
                    "geometry review date."
                ),
            },
        )

    def _assert_altered_json_rejected(
        self,
        alterations: dict[Path, dict[str, object]],
        message: str,
        *,
        corpus_free: bool = False,
    ) -> None:
        original_load = verified_core_v16._load_json
        resolved = {path.resolve(): value for path, value in alterations.items()}

        def load_altered(path: Path) -> object:
            replacement = resolved.get(Path(path).resolve())
            if replacement is not None:
                return replacement
            return original_load(path)

        hydration = (
            mock.patch.object(
                verified_core_v16,
                "_v14_hydrated_crosscheck_available",
                return_value=False,
            )
            if corpus_free
            else mock.patch.object(
                verified_core_v16,
                "_v14_hydrated_crosscheck_available",
                wraps=verified_core_v16._v14_hydrated_crosscheck_available,
            )
        )
        with (
            mock.patch.object(
                verified_core_v16,
                "_load_json",
                side_effect=load_altered,
            ),
            hydration,
            self.assertRaisesRegex(VerifiedConstructionCoreError, message),
        ):
            verified_core._contracts()

    def test_contract_semantic_tamper_fails_closed(self) -> None:
        altered = self._contract()
        altered["reviewed_as_of"] = "2026-09-05"
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17 batch contract differs",
        )

    def test_contract_and_capture_byte_hash_tamper_fail_closed(self) -> None:
        for target, attribute, message in (
            (
                V17_BATCH_CONTRACT,
                "V17_BATCH_CONTRACT",
                "v0.17 batch contract hash differs",
            ),
            (
                V17_GEOMETRY_CAPTURE,
                "V17_GEOMETRY_CAPTURE",
                "v0.17 geometry capture hash differs",
            ),
        ):
            with self.subTest(target=target.name), tempfile.TemporaryDirectory() as temporary:
                clone = Path(temporary) / target.name
                clone.write_bytes(target.read_bytes() + b" ")
                with (
                    mock.patch.object(verified_core, attribute, clone),
                    self.assertRaisesRegex(VerifiedConstructionCoreError, message),
                ):
                    verified_core._contracts()

    def test_capture_hash_and_redistribution_tamper_fail_closed(self) -> None:
        for field, value in (("sha256", "0" * 64), ("redistributed", True)):
            with self.subTest(field=field):
                altered = self._capture()
                altered["source_documents"][0]["capture"][field] = value
                self._assert_altered_json_rejected(
                    {V17_GEOMETRY_CAPTURE: altered},
                    "v0.17 raw-source guardrail differs",
                )

    def test_canonical_geometry_tamper_fails_closed(self) -> None:
        altered = self._capture()
        row = next(
            row
            for row in altered["results"]
            if row["locator_id"]
            == "dansk-data-center-1-esbjerg-dar-sahara-9-address-point"
        )
        row["geometry"]["coordinates"][0] += 0.0001
        self._assert_altered_json_rejected(
            {V17_GEOMETRY_CAPTURE: altered},
            "v0.17 canonical geometry differs",
        )

    def test_nxdata_display_anchor_only_tamper_fails_closed(self) -> None:
        altered = self._capture()
        point_rows = [
            row for row in altered["results"] if row["geometry"]["type"] == "Point"
        ]
        self.assertEqual(len(point_rows), 17)
        for point in point_rows:
            self.assertEqual(
                point["display_anchor"]["coordinates"],
                point["geometry"]["coordinates"],
            )
        row = next(
            row
            for row in altered["results"]
            if row["project_stable_key"] == NXDATA_PROJECT_KEY
        )
        self.assertEqual(row["geometry"]["coordinates"], [26.129117, 44.538685])
        row["display_anchor"]["coordinates"] = [0, 0]
        self._assert_altered_json_rejected(
            {V17_GEOMETRY_CAPTURE: altered},
            "v0.17 display anchor differs",
            corpus_free=True,
        )

    def test_nxdata_rehashed_geometry_and_anchor_cannot_replace_source_fact(self) -> None:
        altered = self._capture()
        row = next(
            row
            for row in altered["results"]
            if row["project_stable_key"] == NXDATA_PROJECT_KEY
        )
        document = next(
            document
            for document in altered["source_documents"]
            if document["source_id"] == NXDATA_SOURCE_ID
        )
        row["geometry"]["coordinates"] = [1, 1]
        row["display_anchor"]["coordinates"] = [1, 1]
        canonical = verified_core_v16._json_bytes(row["geometry"])[:-1]
        row["canonical_geometry"] = {
            "bytes_without_newline": len(canonical),
            "sha256_without_newline": hashlib.sha256(canonical).hexdigest(),
        }
        self.assertEqual(document["facts"]["coordinate"], [26.129117, 44.538685])
        self._assert_altered_json_rejected(
            {V17_GEOMETRY_CAPTURE: altered},
            "v0.17",
            corpus_free=True,
        )

    def test_nxdata_capture_provenance_tamper_fails_closed(self) -> None:
        for mutation in (
            "rights_urls_missing",
            "rights_metadata_missing",
            "all_rights_metadata_missing",
            "retrieved_at_missing",
            "retrieved_at_empty",
            "capture_kind_missing",
            "capture_kind_empty",
            "nonhex_content_hash_with_recomputed_evidence_id",
        ):
            with self.subTest(mutation=mutation):
                altered = self._capture()
                document = next(
                    document
                    for document in altered["source_documents"]
                    if document["source_id"] == NXDATA_SOURCE_ID
                )
                if mutation == "rights_urls_missing":
                    del document["rights_urls"]
                elif mutation == "rights_metadata_missing":
                    del document["rights_metadata"]
                elif mutation == "all_rights_metadata_missing":
                    del document["rights_urls"]
                    del document["rights_metadata"]
                elif mutation == "retrieved_at_missing":
                    del document["retrieved_at"]
                elif mutation == "retrieved_at_empty":
                    document["retrieved_at"] = ""
                elif mutation == "capture_kind_missing":
                    del document["capture"]["capture_kind"]
                elif mutation == "capture_kind_empty":
                    document["capture"]["capture_kind"] = ""
                else:
                    document["content_hash"] = "z" * 64
                    document["capture"]["sha256"] = document["content_hash"]
                    document["evidence_id"] = verified_core_v16.atlas_stable_id(
                        "evidence",
                        "verified-construction-core-v0.17",
                        document["source_id"],
                        document["content_hash"],
                    )
                self._assert_altered_json_rejected(
                    {V17_GEOMETRY_CAPTURE: altered},
                    "v0.17",
                    corpus_free=True,
                )

    def test_official_boundary_promotion_fails_closed(self) -> None:
        altered = self._capture()
        altered["results"][0]["semantics"]["official_boundary"] = True
        self._assert_altered_json_rejected(
            {V17_GEOMETRY_CAPTURE: altered},
            "v0.17 geometry semantics differ",
        )

    def test_status_tamper_fails_closed(self) -> None:
        altered = self._contract()
        row = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"]
            == "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build"
        )
        row["status"]["value"] = "operational"
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17 lifecycle differs",
        )

    def test_lifecycle_window_tamper_fails_closed(self) -> None:
        contract = self._contract()
        project_key = "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build"
        acceptance = next(
            row
            for row in contract["acceptances"]
            if row["project_stable_key"] == project_key
        )
        acceptance["status"]["as_of_date"] = "2026-05-21"
        source_path = verified_core.ROOT / acceptance["source_input"]["path"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        lifecycle = next(
            row
            for row in source["lifecycle"]
            if row["evidence_key"] == acceptance["status"]["evidence_key"]
        )
        lifecycle["as_of_date"] = "2026-05-21"
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: contract, source_path: source},
            "v0.17 lifecycle window differs",
        )

    def test_source_local_relationship_tamper_fails_closed(self) -> None:
        altered = self._contract()
        row = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"]
            == "curated:datagrid-makarewa-ai-factory:initial-horizontal-works"
        )
        self.assertEqual(row["relationship"]["origin"], "source_local")
        row["relationship"]["relationship_id"] = "relationship:" + ("0" * 64)
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17 source-local topology differs",
            corpus_free=True,
        )

    def test_corpus_free_current_status_lineage_identifier_tamper_fails_closed(
        self,
    ) -> None:
        altered = self._contract()
        row = next(
            row
            for row in altered["source_lineage"]
            if row["project_stable_key"] == NXDATA_PROJECT_KEY
        )
        row["current_status_lineage"]["evidence_id"] = "bogus"
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17",
            corpus_free=True,
        )

    def test_corpus_free_matching_relationship_drift_fails_closed(self) -> None:
        altered = self._contract()
        acceptance = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"] == NXDATA_PROJECT_KEY
        )
        lineage = next(
            row
            for row in altered["source_lineage"]
            if row["project_stable_key"] == NXDATA_PROJECT_KEY
        )
        self.assertEqual(acceptance["relationship"]["origin"], "v14")
        relationship_id = "relationship:" + "0" * 64
        acceptance["relationship"]["relationship_id"] = relationship_id
        lineage["v14_topology"]["relationship_id"] = relationship_id
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17",
            corpus_free=True,
        )

    def test_hydration_binding_inventory_cannot_be_replaced_with_missing_paths(
        self,
    ) -> None:
        altered = self._contract()
        bindings = altered["hydrated_crosscheck_inputs"]
        self.assertEqual(len(bindings), 5)
        for index, binding in enumerate(bindings):
            binding["path"] = f"missing-v017-hydration-input-{index}.csv"
            self.assertFalse((verified_core.ROOT / binding["path"]).exists())
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17",
        )

    def test_curated_source_hash_tamper_fails_closed(self) -> None:
        altered = self._contract()
        row = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"]
            == "curated:data-world-matatirtha-campus:core-data-center-current-build"
        )
        row["source_input"]["sha256"] = "0" * 64
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17 curated source source hash differs",
        )

    def test_identity_document_binding_tamper_fails_closed(self) -> None:
        altered = self._capture()
        row = next(
            row
            for row in altered["results"]
            if row["project_stable_key"]
            == "curated:datagrid-makarewa-ai-factory:initial-horizontal-works"
        )
        self.assertEqual(
            row["identity_source_document_ids"],
            ["datagrid-makarewa-sdc-resource-consent-application"],
        )
        row["identity_source_document_ids"] = []
        self._assert_altered_json_rejected(
            {V17_GEOMETRY_CAPTURE: altered},
            "v0.17 unbound capture document differs",
        )

    def test_location_evidence_identifier_tamper_fails_closed(self) -> None:
        altered = self._contract()
        row = next(
            row
            for row in altered["acceptances"]
            if row["project_stable_key"]
            == "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build"
        )
        row["location_evidence"]["evidence_id"] = "00000000-0000-0000-0000-000000000000"
        self._assert_altered_json_rejected(
            {V17_BATCH_CONTRACT: altered},
            "v0.17 source evidence identifier differs",
        )

    def test_hydrated_lineage_validator_is_invoked(self) -> None:
        contract = self._contract()
        if not verified_core_v16._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        with mock.patch.object(
            verified_core,
            "_validate_hydrated_lineage",
            wraps=verified_core._validate_hydrated_lineage,
        ) as validator:
            verified_core._contracts()
        validator.assert_called_once()

    def test_hydrated_v97_project_row_tamper_fails_closed(self) -> None:
        contract = self._contract()
        if not verified_core_v16._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        original_load = verified_core_v16._load_csv

        def load_altered(
            path: Path, expected_fields: object = None
        ) -> list[dict[str, str]]:
            rows = original_load(path, expected_fields)
            if Path(path).resolve() == (
                verified_core_v16.SOURCE_RELEASE / "construction_pipeline.csv"
            ).resolve():
                rows = [dict(row) for row in rows]
                target = next(
                    row
                    for row in rows
                    if row["stable_key"]
                    == "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build"
                )
                target["status_as_of"] = "2026-06-24"
            return rows

        with (
            mock.patch.object(
                verified_core_v16,
                "_load_csv",
                side_effect=load_altered,
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.17 hydrated lineage v97 project differs",
            ),
        ):
            verified_core._contracts()

    def test_hydrated_v14_topology_tamper_fails_closed(self) -> None:
        contract = self._contract()
        if not verified_core_v16._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        original_load = verified_core_v16._load_csv

        def load_altered(
            path: Path, expected_fields: object = None
        ) -> list[dict[str, str]]:
            rows = original_load(path, expected_fields)
            if Path(path).resolve() == (
                verified_core.ROOT
                / "exact_identity_decisions"
                / "2026-07-22-public-open-v14"
                / "relationships.csv"
            ).resolve():
                rows = [dict(row) for row in rows]
                target = next(
                    row
                    for row in rows
                    if row["relationship_id"]
                    == "relationship:8aeb95e3866d81dd71dfb61429a18d8f5993b992ac88329fc56514ef68abd252"
                )
                target["object_component_id"] = "exact:tampered"
            return rows

        with (
            mock.patch.object(
                verified_core_v16,
                "_load_csv",
                side_effect=load_altered,
            ),
            self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.17 hydrated lineage v14 topology differs",
            ),
        ):
            verified_core._contracts()

    def _assert_rebuild_is_byte_exact(self, *, corpus_free: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = Path(temporary) / "preview"
            hydration = (
                mock.patch.object(
                    verified_core_v16,
                    "_v14_hydrated_crosscheck_available",
                    return_value=False,
                )
                if corpus_free
                else mock.patch.object(
                    verified_core_v16,
                    "_v14_hydrated_crosscheck_available",
                    wraps=verified_core_v16._v14_hydrated_crosscheck_available,
                )
            )
            with hydration, mock.patch.object(
                verified_core,
                "_validate_hydrated_lineage",
                wraps=verified_core._validate_hydrated_lineage,
            ) as validator:
                build_preview(rebuilt)
            if corpus_free:
                validator.assert_not_called()
            else:
                self.assertGreater(validator.call_count, 0)
            self.assertEqual(
                {path.name for path in rebuilt.iterdir()},
                {path.name for path in CURRENT_V17_PREVIEW_DIR.iterdir()},
            )
            for expected in CURRENT_V17_PREVIEW_DIR.iterdir():
                self.assertEqual(
                    (rebuilt / expected.name).read_bytes(),
                    expected.read_bytes(),
                    expected.name,
                )

    def test_corpus_free_rebuild_is_byte_exact(self) -> None:
        self._assert_rebuild_is_byte_exact(corpus_free=True)

    def test_hydrated_rebuild_is_byte_exact(self) -> None:
        contract = self._contract()
        if not verified_core_v16._v14_hydrated_crosscheck_available(contract):
            self.skipTest("hydration-only: five ignored v97/v14 inputs are absent")
        self._assert_rebuild_is_byte_exact(corpus_free=False)

    def test_builder_refuses_overwrite(self) -> None:
        with self.assertRaisesRegex(
            VerifiedConstructionCoreError,
            "refusing to overwrite",
        ):
            build_preview(CURRENT_V17_PREVIEW_DIR)

    def test_rehashed_artifact_tamper_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            clone = Path(temporary) / "preview"
            shutil.copytree(CURRENT_V17_PREVIEW_DIR, clone)
            projects_path = clone / "projects.csv"
            projects = _rows_from(clone, "projects.csv")
            target = next(
                row
                for row in projects
                if row["project_stable_key"]
                == "curated:datagrid-makarewa-ai-factory:initial-horizontal-works"
            )
            target["geometry_use_scope"] = "official_boundary"
            with projects_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=verified_core.PROJECT_FIELDS,
                )
                writer.writeheader()
                writer.writerows(projects)
            manifest_path = clone / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["projects.csv"] = {
                "bytes": projects_path.stat().st_size,
                "sha256": hashlib.sha256(projects_path.read_bytes()).hexdigest(),
            }
            manifest_bytes = verified_core_v16._json_bytes(manifest)
            manifest_path.write_bytes(manifest_bytes)
            (clone / "manifest.sha256").write_text(
                f"{hashlib.sha256(manifest_bytes).hexdigest()}  manifest.json\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                VerifiedConstructionCoreError,
                "v0.17 manifest semantics differ",
            ):
                validate_preview(clone)


if __name__ == "__main__":
    unittest.main()
