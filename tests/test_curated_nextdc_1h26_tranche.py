from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
V16_DEFINITION = "open-seed-2026-07-19-v16.json"
EVIDENCE_KEY = "nextdc-1h26-results-presentation-captured-2026-07-19"
CONTENT_HASH = "0ad1f17697c1c812be0c6db55722ea7e335fb5299d7de6f67c261d1f6b8573ec"
HEADERS_HASH = "638f227cf6a1bdc525209d0ec9232072feae1b700c1ed7177029d923209e4468"
SOURCE_URL = (
    "https://www.nextdc.com/hubfs/ASX%20Announcements/"
    "1H26%20Results%20Presentation.pdf"
)
SC2_CANONICAL_CAMPUS_KEY = "curated:nextdc-sc2-maroochydore"

FITOUT_SOURCES: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-19-nextdc-s3-sydney-1h26-fitout.json": {
        "sha256": "3269918319752e643a38b7391beea53377eff987547864dcb624dacd6cf1b969",
        "code": "S3",
        "country": "Australia",
        "address": "Sydney, Australia",
        "campus_key": "curated:nextdc-s3-sydney",
        "campus_name": "NEXTDC S3 Sydney Data Center Campus",
        "capacity": Decimal("20"),
    },
    "curated-official-2026-07-19-nextdc-s6-sydney-1h26-fitout.json": {
        "sha256": "4a7482e8169884bd98cd8159217459064088e78a21c11c28584da766bc19ce7b",
        "code": "S6",
        "country": "Australia",
        "address": "Sydney, Australia",
        "campus_key": "curated:nextdc-s6-sydney",
        "campus_name": "NEXTDC S6 Sydney Data Center Campus",
        "capacity": Decimal("10.8"),
    },
    "curated-official-2026-07-19-nextdc-m2-melbourne-1h26-fitout.json": {
        "sha256": "1674ac8b23e48cf947e01ede96f0baa3fc94d891bc84ab35b4c61d10134e317b",
        "code": "M2",
        "country": "Australia",
        "address": "Melbourne, Australia",
        "campus_key": "curated:nextdc-m2-melbourne",
        "campus_name": "NEXTDC M2 Melbourne Data Center Campus",
        "capacity": Decimal("30"),
    },
    "curated-official-2026-07-19-nextdc-m3-melbourne-1h26-fitout.json": {
        "sha256": "998ddd53d217df3a1411c55e0ff1037488b6456d5f62d50e1d7429a8842b6ceb",
        "code": "M3",
        "country": "Australia",
        "address": "Melbourne, Australia",
        "campus_key": "curated:nextdc-m3-melbourne",
        "campus_name": "NEXTDC M3 Melbourne Data Center Campus",
        "capacity": Decimal("185"),
    },
    "curated-official-2026-07-19-nextdc-ge1-geelong-1h26-fitout.json": {
        "sha256": "5cffac3c97fd9faaa5644d18d7c0bbac8a6016be6930685dea32dce0a89347c4",
        "code": "GE1",
        "country": "Australia",
        "address": "Geelong, Australia",
        "campus_key": "curated:nextdc-ge1-geelong",
        "campus_name": "NEXTDC GE1 Geelong Data Center Campus",
        "capacity": Decimal("1"),
    },
    "curated-official-2026-07-19-nextdc-d2-darwin-1h26-fitout.json": {
        "sha256": "77cf37681f3bdf093bd381b5cbd325f33e3fc8e3f8ff5e48e35de324b9caad65",
        "code": "D2",
        "country": "Australia",
        "address": "Darwin, Australia",
        "campus_key": "curated:nextdc-d2-darwin",
        "campus_name": "NEXTDC D2 Darwin Data Center Campus",
        "capacity": Decimal("1.5"),
    },
    "curated-official-2026-07-19-nextdc-b2-brisbane-1h26-fitout.json": {
        "sha256": "ec0da982be0d87f142618100a518f947fd58bc014d5f7b621629fbe7cda5f97d",
        "code": "B2",
        "country": "Australia",
        "address": "Brisbane, Australia",
        "campus_key": "curated:nextdc-b2-brisbane",
        "campus_name": "NEXTDC B2 Brisbane Data Center Campus",
        "capacity": Decimal("2"),
    },
    "curated-official-2026-07-19-nextdc-p1-perth-1h26-fitout.json": {
        "sha256": "cf22bd4df7074daf34dc13f0ba2855e7ed8d5ec701b603f45aca3531ba0afefd",
        "code": "P1",
        "country": "Australia",
        "address": "Perth, Australia",
        "campus_key": "curated:nextdc-p1-perth",
        "campus_name": "NEXTDC P1 Perth Data Center Campus",
        "capacity": Decimal("2"),
    },
    "curated-official-2026-07-19-nextdc-p2-perth-1h26-fitout.json": {
        "sha256": "60c0825766b68dccfcfa8b361389394bd2b5d0321ed0591fc20da84512798a46",
        "code": "P2",
        "country": "Australia",
        "address": "Perth, Australia",
        "campus_key": "curated:nextdc-p2-perth",
        "campus_name": "NEXTDC P2 Perth Data Center Campus",
        "capacity": Decimal("4"),
    },
    "curated-official-2026-07-19-nextdc-sc1-sunshine-coast-1h26-fitout.json": {
        "sha256": "418ed5e49ff689d140b10040e458758793418797d6179340b0e7441e6216f1d9",
        "code": "SC1",
        "country": "Australia",
        "address": "Sunshine Coast, Australia",
        "campus_key": "curated:nextdc-sc1-sunshine-coast",
        "campus_name": "NEXTDC SC1 Sunshine Coast Data Center Campus",
        "capacity": Decimal("0.6"),
    },
    "curated-official-2026-07-19-nextdc-sc2-sunshine-coast-1h26-fitout.json": {
        "sha256": "768526b34023aac438eca3513898102b90d29f0107e52da16e6e16c6fe7e01c2",
        "code": "SC2",
        "country": "Australia",
        "address": "Sunshine Coast, Australia",
        "campus_key": SC2_CANONICAL_CAMPUS_KEY,
        "campus_name": "NEXTDC SC2 Data Center Campus",
        "capacity": Decimal("1"),
    },
    "curated-official-2026-07-19-nextdc-kl1-kuala-lumpur-1h26-fitout.json": {
        "sha256": "b428c2d24c796e5dc68ae64221c90fc0a85680061a092f97786512941b2c8da3",
        "code": "KL1",
        "country": "Malaysia",
        "address": "Kuala Lumpur, Malaysia",
        "campus_key": "curated:nextdc-kl1-kuala-lumpur",
        "campus_name": "NEXTDC KL1 Kuala Lumpur Data Center Campus",
        "capacity": Decimal("15"),
    },
}

EARLY_WORK_SOURCES: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-19-nextdc-s4-sydney-1h26-early-works.json": {
        "sha256": "4f465a73da77cc106c37aff41050079c1f07e78d25e3bdd92319b78a30418082",
        "code": "S4",
        "country": "Australia",
        "address": "Sydney, Australia",
        "campus_key": "curated:nextdc-s4-sydney",
        "campus_name": "NEXTDC S4 Sydney Data Center Campus",
        "project_key": "curated:nextdc-s4-sydney:early-works",
        "project_name": "NEXTDC S4 Early Works",
    },
    "curated-official-2026-07-19-nextdc-tk1-tokyo-1h26-preliminary-works.json": {
        "sha256": "7daf178a818c25aff4b2e9a1af4f4a894622d7dc703c1fed0564e9c8e3533a51",
        "code": "TK1",
        "country": "Japan",
        "address": "Tokyo, Japan",
        "campus_key": "curated:nextdc-tk1-tokyo",
        "campus_name": "NEXTDC TK1 Tokyo Data Center Campus",
        "project_key": "curated:nextdc-tk1-tokyo:preliminary-works",
        "project_name": "NEXTDC TK1 Preliminary Works",
    },
}
SOURCES = {**FITOUT_SOURCES, **EARLY_WORK_SOURCES}


class Nextdc1H26TrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _project_key(self, name: str, expected: dict[str, Any]) -> str:
        if name in FITOUT_SOURCES:
            return f"{expected['campus_key']}:incremental-in-progress-fit-out"
        return str(expected["project_key"])

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["title"], "NEXTDC 1H26 Results Presentation")
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(evidence["published_at"], "2026-02-25")
        self.assertEqual(evidence["retrieved_at"], "2026-07-19T19:25:06Z")
        self.assertEqual(evidence["content_hash"], CONTENT_HASH)
        metadata = evidence["metadata"]
        self.assertEqual(
            metadata["content_hash_scope"],
            "SHA-256 of the exact 5090407-byte official PDF response body",
        )
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertEqual(
            metadata["capture_headers_scope"],
            "SHA-256 of the exact 1712-byte raw response-header capture",
        )
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_HASH)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertIsNone(metadata["content_encoding_as_received"])
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 5090407)
        self.assertEqual(metadata["response_http_date"], "2026-07-19T19:25:06Z")
        self.assertEqual(
            metadata["http_last_modified_at"], "2026-02-25T12:42:08Z"
        )
        for key in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[key], SOURCE_URL)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertNotIn("request_started_at", metadata)
        self.assertNotIn("request_start_utc", metadata)
        self.assertIn(
            "no request-start artifact was supplied", metadata["retrieval_method"]
        )
        self.assertIn("not redistributed", metadata["rights_scope"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if len(document["evidence"]) != 1:
            raise AssertionError("one exact PDF evidence record must remain")
        self._assert_capture(document["evidence"][0])

        project_key = self._project_key(name, expected)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("localities must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("entity method must remain authoritative_locality")
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain the named locality only")
        if (
            document["campus"]["stable_key"] != expected["campus_key"]
            or document["campus"]["name"] != expected["campus_name"]
        ):
            raise AssertionError("canonical facility campus identity must remain exact")
        if document["project"]["stable_key"] != project_key:
            raise AssertionError("source-scoped project identity must remain exact")

        if document["operating_models"]:
            raise AssertionError("operating models must remain empty")
        if document["workloads"]:
            raise AssertionError("workloads must remain empty")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        if lifecycle[0]["method"] != "authoritative_physical_status_update":
            raise AssertionError("lifecycle method must remain authoritative")

        capacities = document["capacities"]
        if name in FITOUT_SOURCES:
            if lifecycle[0]["value"] != "mep_electrical":
                raise AssertionError("fit-out lifecycle must remain mep_electrical")
            if lifecycle[0]["as_of_date"] != "2025-12-31":
                raise AssertionError("fit-out date must remain the reporting date")
            if len(capacities) != 1:
                raise AssertionError("one incremental fit-out capacity must remain")
            capacity = capacities[0]
            value = expected["capacity"]
            if (
                capacity["entity"] != "project"
                or capacity["metric"] != "critical_it_mw"
                or capacity["stage"] != "planned"
                or capacity["unit"] != "MW"
                or capacity["method"] != "reported"
                or capacity["as_of_date"] != "2025-12-31"
                or capacity["target_date"] is not None
                or Decimal(str(capacity["low"])) != value
                or Decimal(str(capacity["base"])) != value
                or Decimal(str(capacity["high"])) != value
            ):
                raise AssertionError(
                    "planned project critical-IT fit-out amount must remain exact"
                )
            notes = capacity["notes"]
            for phrase in (
                "incremental in-progress fit-out",
                "nested within the facility's whole-facility total",
                "not built capacity",
                "current load",
                "operational capacity",
                "not an amount additive to that whole-facility total",
            ):
                if phrase not in notes:
                    raise AssertionError(
                        "capacity notes must preserve the anti-double-count scope"
                    )
        else:
            if lifecycle[0]["value"] != "site_preparation":
                raise AssertionError("early works must remain site_preparation")
            if lifecycle[0]["as_of_date"] != "2026-02-25":
                raise AssertionError("early-works date must remain publication scoped")
            if capacities:
                raise AssertionError("untyped total-power plans create no capacity rows")

    def test_capture_provenance_exact_wording_pages_and_math(self) -> None:
        documents = [self._load(name) for name in sorted(SOURCES)]
        canonical_evidence = documents[0]["evidence"][0]
        for document in documents:
            self.assertEqual(document["evidence"][0], canonical_evidence)
        self._assert_capture(canonical_evidence)

        metadata = canonical_evidence["metadata"]
        self.assertEqual(metadata["document_page_count"], 38)
        self.assertEqual(metadata["document_date_as_reported"], "25 February 2026")
        self.assertEqual(metadata["reporting_date_as_reported"], "31 December 2025")
        self.assertEqual(metadata["facility_capacity_page"], 16)
        self.assertEqual(
            metadata["in_progress_definition_as_reported"],
            "Mechanical and electrical fit-out underway to prepare data halls "
            "for customer deployments.",
        )
        reported = {
            row["facility_code"]: Decimal(str(row["incremental_in_progress_mw"]))
            for row in metadata["facility_in_progress_fit_out_as_reported"]
        }
        expected = {
            value["code"]: value["capacity"] for value in FITOUT_SOURCES.values()
        }
        self.assertEqual(reported, expected)
        self.assertEqual(sum(reported.values(), Decimal("0")), Decimal("272.9"))
        self.assertEqual(
            Decimal(str(metadata["total_in_progress_as_reported_mw"])),
            Decimal("272.9"),
        )
        regional = metadata["regional_in_progress_subtotals_as_reported_mw"]
        self.assertEqual(
            sum((Decimal(str(value)) for value in regional.values()), Decimal("0")),
            Decimal("272.9"),
        )
        self.assertEqual(metadata["s4_early_works_pdf_page"], 21)
        self.assertEqual(
            metadata["s4_early_works_wording_as_reported"],
            "S4 Sydney early works in progress",
        )
        self.assertEqual(metadata["s4_total_power_plan_pdf_page"], 31)
        self.assertEqual(metadata["s4_total_power_plan_as_reported_mw"], 350)
        self.assertEqual(metadata["s4_total_power_plan_qualifier"], "approximately")
        self.assertEqual(metadata["tk1_preliminary_works_pdf_page"], 16)
        self.assertEqual(
            metadata["tk1_preliminary_works_wording_as_reported"],
            "Preliminary works now underway",
        )
        self.assertEqual(metadata["tk1_total_power_plan_pdf_page"], 31)
        self.assertEqual(metadata["tk1_total_power_plan_as_reported_mw"], 30)
        self.assertEqual(metadata["tk1_total_power_plan_qualifier"], "approximately")
        for excluded in ("M4", "S5", "AK1", "S7"):
            self.assertIn(excluded, metadata["excluded_future_or_planning_scope"])
        self.assertIn(
            "create no capacity rows", metadata["early_works_capacity_guardrail"]
        )
        self.assertIn(
            "remain evidence metadata only",
            metadata["fit_out_double_count_guardrail"],
        )

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        v16_definition = (ROOT / "sources" / V16_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name, expected in SOURCES.items():
            self.assertNotIn(name, v16_definition)
            self.assertNotIn(self._project_key(name, expected), v16_definition)
            if expected["campus_key"] != SC2_CANONICAL_CAMPUS_KEY:
                self.assertNotIn(expected["campus_key"], v16_definition)
        existing_sc2_source = (
            "curated-official-2026-07-19-nextdc-sc2-maroochydore.json"
        )
        self.assertIn(existing_sc2_source, v16_definition)
        self.assertEqual(
            self._load(existing_sc2_source)["campus"]["stable_key"],
            SC2_CANONICAL_CAMPUS_KEY,
        )

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected in sorted(SOURCES.items()):
                        source_path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(source_path.read_bytes()).hexdigest(),
                            expected["sha256"],
                        )
                        document = self._load(name)
                        self._assert_document(name, document)
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at="2026-07-19T19:25:06Z",
                        )

                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 14), ("project", 14)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT status, COUNT(*) FROM lifecycle_observations "
                            "GROUP BY status ORDER BY status"
                        )
                    ],
                    [("mep_electrical", 12), ("site_preparation", 2)],
                )
                capacity_rows = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT entities.stable_key, capacity_estimates.metric,
                               capacity_estimates.stage, capacity_estimates.base,
                               capacity_estimates.unit, capacity_estimates.notes
                        FROM capacity_estimates
                        JOIN entities
                          ON entities.id = capacity_estimates.entity_id
                        ORDER BY entities.stable_key
                        """
                    )
                ]
                expected_capacity = {
                    f"{value['campus_key']}:incremental-in-progress-fit-out":
                    value["capacity"]
                    for value in FITOUT_SOURCES.values()
                }
                self.assertEqual(
                    {row[0]: Decimal(str(row[3])) for row in capacity_rows},
                    expected_capacity,
                )
                self.assertEqual(
                    sum(
                        (Decimal(str(row[3])) for row in capacity_rows),
                        Decimal("0"),
                    ),
                    Decimal("272.9"),
                )
                self.assertTrue(
                    all(
                        row[1:3] == ("critical_it_mw", "planned")
                        and row[4] == "MW"
                        and "incremental in-progress fit-out" in row[5]
                        for row in capacity_rows
                    )
                )
                self.assertEqual(len(capacity_rows), 12)
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT content_hash FROM evidence"
                    ).fetchone()[0],
                    CONTENT_HASH,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots"
                    ).fetchone()[0],
                    28,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric IN ('pue', 'annual_energy_mwh', "
                        "'grid_connection_mw', 'gross_facility_mw', "
                        "'generation_nameplate_mw')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "WHERE status IN ('commissioning', 'operational')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence "
                        "WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        fitout_name = next(iter(FITOUT_SOURCES))
        fitout = self._load(fitout_name)
        early_name = next(iter(EARLY_WORK_SOURCES))
        early = self._load(early_name)

        mutated = copy.deepcopy(fitout)
        mutated["lifecycle"][0]["value"] = "under_construction"
        with self.assertRaisesRegex(
            AssertionError, "fit-out lifecycle must remain mep_electrical"
        ):
            self._assert_document(fitout_name, mutated)

        mutated = copy.deepcopy(fitout)
        mutated["capacities"][0]["base"] = 80
        with self.assertRaisesRegex(
            AssertionError, "critical-IT fit-out amount must remain exact"
        ):
            self._assert_document(fitout_name, mutated)

        mutated = copy.deepcopy(fitout)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
                "evidence_key": EVIDENCE_KEY,
                "as_of_date": "2025-12-31",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        with self.assertRaisesRegex(AssertionError, "workloads must remain empty"):
            self._assert_document(fitout_name, mutated)

        mutated = copy.deepcopy(fitout)
        mutated["campus"]["roles"] = {"operator": ["NEXTDC"]}
        with self.assertRaisesRegex(AssertionError, "roles must remain empty"):
            self._assert_document(fitout_name, mutated)

        mutated = copy.deepcopy(fitout)
        mutated["project"]["coordinates"] = {
            "latitude": -33.0,
            "longitude": 151.0,
        }
        with self.assertRaisesRegex(AssertionError, "localities must remain ungeocoded"):
            self._assert_document(fitout_name, mutated)

        mutated = copy.deepcopy(early)
        mutated["capacities"] = [copy.deepcopy(fitout["capacities"][0])]
        with self.assertRaisesRegex(
            AssertionError, "untyped total-power plans create no capacity rows"
        ):
            self._assert_document(early_name, mutated)

        mutated = copy.deepcopy(early)
        mutated["lifecycle"][0]["value"] = "under_construction"
        with self.assertRaisesRegex(
            AssertionError, "early works must remain site_preparation"
        ):
            self._assert_document(early_name, mutated)


if __name__ == "__main__":
    unittest.main()
