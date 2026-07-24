from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
V13_DEFINITION = "open-seed-2026-07-19-v13.json"
SOURCES: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json": {
        "sha256": "ddeecf7811dd1d2c792e40813f9ebf07d35a37f79f50e236f5c3329ba06baa39",
        "retrieved_at": "2026-07-19T18:30:16Z",
        "country": "United States",
        "address": "Sterling, Virginia, United States",
        "campus_key": "curated:digital-realty-digital-dulles-campus",
        "campus_name": "Digital Realty Digital Dulles Campus",
        "project_key": (
            "curated:digital-realty-digital-dulles-campus:"
            "current-96mw-development"
        ),
        "project_name": "Digital Realty Digital Dulles Current 96 MW Development",
        "lifecycle_date": "2026-06-29",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacities": [("project", "critical_it_mw", 96.0)],
        "workloads": [],
    },
    "curated-official-2026-07-19-edgeconnex-greater-osaka.json": {
        "sha256": "ed5be494f24ace21d8d87c947ee3a5ebd04cb59020c0e79d0874296baec7122d",
        "retrieved_at": "2026-07-19T18:29:57Z",
        "country": "Japan",
        "address": "Greater Osaka, Japan",
        "campus_key": "curated:edgeconnex-greater-osaka-campus",
        "campus_name": "EdgeConneX Greater Osaka Data Center Campus",
        "project_key": (
            "curated:edgeconnex-greater-osaka-campus:current-campus-development"
        ),
        "project_name": "EdgeConneX Greater Osaka Current Campus Development",
        "lifecycle_date": "2026-03-17",
        "lifecycle_method": "authoritative_construction_start",
        "capacities": [],
        "workloads": [],
    },
    "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json": {
        "sha256": "817a653cd86ca0e1dbacb84a3cdd7730597a657395623c2fe21896f781dae6cc",
        "retrieved_at": "2026-07-19T18:33:46Z",
        "country": "United States",
        "address": "Doña Ana County, New Mexico, United States",
        "campus_key": "curated:oracle-project-jupiter-dona-ana-campus",
        "campus_name": "Oracle Project Jupiter Doña Ana County AI Data Center Campus",
        "project_key": (
            "curated:oracle-project-jupiter-dona-ana-campus:current-campus-build"
        ),
        "project_name": "Oracle Project Jupiter Doña Ana County Current Campus Build",
        "lifecycle_date": "2026-05-27",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacities": [("campus", "generation_nameplate_mw", 2450.0)],
        "workloads": [("campus", "ai_specialized_unspecified", "2026-04-27")],
    },
    "curated-official-2026-07-19-vantage-lighthouse-port-washington.json": {
        "sha256": "8be2fde23880e8f9f271de1213cc04bf20fb549d8e48ff11c889d213687ab138",
        "retrieved_at": "2026-07-19T18:33:46Z",
        "country": "United States",
        "address": "Port Washington, Ozaukee County, Wisconsin, United States",
        "campus_key": "curated:vantage-lighthouse-port-washington-campus",
        "campus_name": "Vantage Lighthouse Port Washington Data Center Campus",
        "project_key": (
            "curated:vantage-lighthouse-port-washington-campus:current-campus-build"
        ),
        "project_name": "Vantage Lighthouse Port Washington Current Campus Build",
        "lifecycle_date": "2026-06-12",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacities": [("campus", "critical_it_mw", 902.0)],
        "workloads": [("campus", "ai_specialized_unspecified", "2026-07-19")],
    },
}
CAPTURES: dict[str, dict[str, Any]] = {
    "4502f68999eb5a1b3e0cdb70084e588798f7d2960271642691db62faddd6a396": {
        "body_bytes": 114285,
        "headers_bytes": 780,
        "headers_sha256": "19a8ec5c986940f31ebc40b37606af71fd85a48d6019c33bd60459b452c8036e",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-17T23:02:02Z",
        "content_type": "text/html; charset=UTF-8",
        "url": "https://dnr.wisconsin.gov/topic/EIA/Portwashington.html",
        "license": "public-government-record",
    },
    "38c18180ab741a3b3afb03a0b9392e3aee7bafa539543fb452714e904698bc96": {
        "body_bytes": 31267,
        "headers_bytes": 1754,
        "headers_sha256": "6f20cfbc8db49cca7864c60de4fdbe1f53ff85a3479b69bd575168698ac898fe",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-12T16:06:59Z",
        "content_type": "text/html; charset=UTF-8",
        "url": "https://www.oracle.com/data-centers/port-washington/",
        "license": "all-rights-reserved",
    },
    "4ee5092b82b1ade67760cc3821f1039f6dcc9ba27083a1a258bad9c8b003697f": {
        "body_bytes": 33611,
        "headers_bytes": 1753,
        "headers_sha256": "c0f23a68c3aa50179477439420f3be493618b5778d1d27b53992cb6ba4eda59c",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-01T14:19:37Z",
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://www.oracle.com/news/announcement/blog/"
            "weve-overhauled-project-jupiters-power-plan-2026-07-01/"
        ),
        "license": "all-rights-reserved",
    },
    "5faadbd9d2fb5edd8c33f981495284f1c32e244d71c43cdbd9eae311137487a5": {
        "body_bytes": 256955,
        "headers_bytes": 384,
        "headers_sha256": "4c4e3f1ba6ec52573f83b4e5504ef1de07be4cf9bb33caf164e5c7782ed0f49b",
        "response_date": "2026-07-19T18:30:16Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://www.digitalrealty.com/about/newsroom/press-releases/30426/"
            "digital-realty-announces-purchase-of-blackstone-interest-in-three-"
            "northern-virginia-data-centers"
        ),
        "license": "all-rights-reserved",
    },
    "6c2024698fd46fbd6ef3cb247734f002ee7a8999490c4bba7ad0b8c9b86c6ba6": {
        "body_bytes": 32575,
        "headers_bytes": 1756,
        "headers_sha256": "163a40e4b927bd138076d6ca05f56059b4a1bfeebfbf931ebc61ea64abd98d74",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-07T21:08:44Z",
        "content_type": "text/html; charset=UTF-8",
        "url": "https://www.oracle.com/data-centers/dona-ana-county/",
        "license": "all-rights-reserved",
    },
    "750bb9daa116f65ce41a860ab755a7a63717be562258f94d5ee2d2f50f67a18f": {
        "body_bytes": 91977,
        "headers_bytes": 1100,
        "headers_sha256": "c35ee120c1a0c6c0bd282f218cd65da2f1acc3f339dffbcdd24585a2433d2b1e",
        "response_date": "2026-07-19T18:29:57Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://blog.vantage-dc.com/2026/03/30/vantage-data-centers-and-"
            "partners-host-career-expo-in-port-washington-wisconsin-to-connect-"
            "local-talent-with-lighthouse-opportunities/"
        ),
        "license": "all-rights-reserved",
    },
    "7eed1e19447c03d97e3da15684de3eb7a1ceb12e61dbec110e3ecb638ecebec3": {
        "body_bytes": 225544,
        "headers_bytes": 2012,
        "headers_sha256": "b6b9b632a6366ce54d7744f7f0c5f74c816c497a9007b76a702bbfe3351663dd",
        "response_date": "2026-07-19T18:30:06Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://vantage-dc.com/data-center-locations/north-america/"
            "port-washington-wisconsin"
        ),
        "license": "all-rights-reserved",
    },
    "b61b6a48d4399cd02f84781e27ea94b1ce1d66c2e82d95df1648842aae831371": {
        "body_bytes": 53946,
        "headers_bytes": 1756,
        "headers_sha256": "ce61c5de535c0a9c762f68be5ffabe904316c2176a21201903e30bacf9175e86",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-15T14:30:30Z",
        "content_type": "text/html; charset=UTF-8",
        "url": "https://www.oracle.com/data-centers/",
        "license": "all-rights-reserved",
    },
    "e18ae14839e2dea948fb1ea7701a1e135bd7cb477d18f24b67d5820ba71e739c": {
        "body_bytes": 40705,
        "headers_bytes": 1756,
        "headers_sha256": "f2062509460b94c06b30a05d56c32d25c34aacdaf99cb9a484390e24ad6d17d1",
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-18T07:42:18Z",
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://www.oracle.com/news/announcement/"
            "oracle-borderplex-and-bloom-energy-to-power-project-jupiter-with-"
            "fuel-cell-technology-2026-04-27/"
        ),
        "license": "all-rights-reserved",
    },
    "ec95177eaeaa5f451e0f416cd9cdd2c5ec4af3ea86f1c458f67423a16a427d06": {
        "body_bytes": 434630,
        "headers_bytes": 1347,
        "headers_sha256": "9233ae5cf803fbd81cab6c4d6dce16776d53ca122a745ddc48325f5b01feb49e",
        "response_date": "2026-07-19T18:29:57Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://www.edgeconnex.com/news/press-releases/edgeconnex-"
            "commences-construction-of-200mw-ai-ready-hyperscale-campus-in-"
            "greater-osaka/"
        ),
        "license": "all-rights-reserved",
    },
}


class OracleEdgeNextTrancheCandidateTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_candidate_guardrails(
        self, name: str, document: dict[str, Any]
    ) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("localities must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("snapshot method must remain authoritative_locality")
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain authoritative locality only")

        if (
            document["campus"]["stable_key"] != expected["campus_key"]
            or document["campus"]["name"] != expected["campus_name"]
        ):
            raise AssertionError("one canonical campus identity must remain")
        if (
            document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("one canonical current-build project must remain")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        if lifecycle[0]["value"] != "under_construction":
            raise AssertionError("lifecycle must remain generic under_construction")
        if lifecycle[0]["as_of_date"] != expected["lifecycle_date"]:
            raise AssertionError("lifecycle date must remain source scoped")
        if lifecycle[0]["method"] != expected["lifecycle_method"]:
            raise AssertionError("lifecycle method must remain authoritative")

        if document["operating_models"]:
            raise AssertionError("operating models must remain empty")

        actual_workloads = [
            (row["entity"], row["value"], row["as_of_date"])
            for row in document["workloads"]
        ]
        if actual_workloads != expected["workloads"]:
            raise AssertionError("workloads must remain narrowly source explicit")
        for row in document["workloads"]:
            if row["value"] != "ai_specialized_unspecified":
                raise AssertionError("AI workload must remain unspecified")

        capacities = document["capacities"]
        if len(capacities) != len(expected["capacities"]):
            raise AssertionError("typed capacity row count must remain exact")
        actual_capacities = []
        for row in capacities:
            if (
                row["stage"] != "planned"
                or row["unit"] != "MW"
                or row["method"] != "reported"
                or row["target_date"] is not None
            ):
                raise AssertionError("capacities must remain planned reported MW")
            if (row["low"], row["base"], row["high"]) != (row["base"],) * 3:
                raise AssertionError("capacity values must remain exact")
            actual_capacities.append(
                (row["entity"], row["metric"], float(row["base"]))
            )
        if actual_capacities != expected["capacities"]:
            raise AssertionError("capacity metric scope and value must remain exact")

        evidence = {row["key"]: row for row in document["evidence"]}
        if "edgeconnex" in name:
            row = evidence[
                "edgeconnex-greater-osaka-construction-2026-03-17-captured-2026-07-19"
            ]["metadata"]
            if (
                row["power_capacity_as_reported_mw"] != 200
                or "not typed" not in row["power_metric_guardrail"]
                or "creates no capacity row" not in row["power_metric_guardrail"]
            ):
                raise AssertionError("Edge 200 MW must remain untyped metadata")
            if (
                row["campus_area_as_reported_square_metres"] != 130000
                or row["first_phase_service_forecast_as_reported"] != "Q1 2028"
                or "forward-looking" not in row["forecast_guardrail"]
            ):
                raise AssertionError("Edge area and forecast must remain metadata")
            if "do not establish an actual workload" not in row["classification_guardrail"]:
                raise AssertionError("Edge AI-ready capability must not become workload")
        elif "vantage" in name:
            location = evidence[
                "vantage-lighthouse-location-page-captured-2026-07-19"
            ]["metadata"]
            dnr = evidence[
                "wisconsin-dnr-lighthouse-current-page-captured-2026-07-19"
            ]["metadata"]
            jobs = evidence[
                "vantage-lighthouse-career-expo-2026-03-30-captured-2026-07-19"
            ]["metadata"]
            oracle = evidence[
                "oracle-port-washington-page-captured-2026-07-19"
            ]["metadata"]
            if (
                location["critical_it_capacity_as_reported_mw"] != 902
                or location["building_count_as_reported"] != 4
                or "full-campus critical IT" not in location["capacity_scope"]
            ):
                raise AssertionError("Lighthouse 902 MW scope must remain exact")
            if (
                "direct AI-campus statement" not in location["ai_ready_distinction"]
                or "AI-ready wording alone" not in location["ai_ready_distinction"]
            ):
                raise AssertionError("Lighthouse AI workload basis must remain explicit")
            if (
                "being constructed" not in dnr["status_scope"]
                or "June 12, 2026" not in dnr["status_as_of_basis"]
                or "do not themselves establish" not in dnr["permit_guardrail"]
                or "four-capture Lighthouse evidence group"
                not in dnr["retrieved_at_semantics"]
            ):
                raise AssertionError("Lighthouse physical status must remain DNR scoped")
            if "do not independently establish" not in jobs["physical_status_guardrail"]:
                raise AssertionError("Lighthouse jobs evidence must remain corroboration")
            if (
                oracle["power_addition_as_reported_mw"] != 2000
                or "Wisconsin's grid"
                not in oracle["power_addition_description_as_reported"]
                or "stays untyped metadata" not in oracle["power_scope_guardrail"]
                or "creates no capacity row" not in oracle["power_scope_guardrail"]
            ):
                raise AssertionError("Lighthouse 2,000 MW grid promotion must remain excluded")
        elif "oracle" in name:
            aerials = evidence[
                "oracle-data-centers-dona-ana-aerials-captured-2026-07-19"
            ]["metadata"]
            location = evidence[
                "oracle-dona-ana-county-data-center-page-captured-2026-07-19"
            ]["metadata"]
            fuel = evidence[
                "oracle-project-jupiter-fuel-cell-announcement-2026-04-27-captured-2026-07-19"
            ]["metadata"]
            july = evidence[
                "oracle-project-jupiter-power-plan-2026-07-01-captured-2026-07-19"
            ]["metadata"]
            if (
                aerials["dona_ana_campus_aerial_caption_as_reported"]
                != "Campus - 05/27/2026"
                or aerials["dona_ana_data_hall_aerial_caption_as_reported"]
                != "Data Hall - 05/21/2026"
                or "Abilene, Texas" not in aerials["abilene_cross_site_guardrail"]
                or "must not become" not in aerials["abilene_cross_site_guardrail"]
            ):
                raise AssertionError("Jupiter aerial dates must remain Doña Ana scoped")
            if (
                "not independent satellite imagery" not in aerials["imagery_provenance_guardrail"]
                or "a geolocation" not in aerials["imagery_provenance_guardrail"]
            ):
                raise AssertionError("Jupiter first-party aerial provenance must remain explicit")
            if (
                location["building_count_as_reported"] != 4
                or location["warehouse_count_as_reported"] != 1
                or location["campus_and_microgrid_area_as_reported_acres"] != 818
            ):
                raise AssertionError("Jupiter building and land facts must remain metadata")
            if (
                fuel["generation_nameplate_as_reported_mw"] != 2450
                or "planned generation nameplate" not in fuel["generation_guardrail"]
                or "not critical IT load" not in fuel["generation_guardrail"]
                or "cannot be multiplied" not in fuel["annual_energy_guardrail"]
            ):
                raise AssertionError("Jupiter generation must not become load or energy")
            if (
                "No MW rating" not in july["grid_guardrail"]
                or "does not create a second generation row" not in july["metric_guardrail"]
                or "conditional and future" not in july["export_guardrail"]
            ):
                raise AssertionError("Jupiter grid and rounded-power exclusions must remain")
        else:
            row = evidence[
                "digital-realty-northern-virginia-transaction-2026-06-29-captured-2026-07-19"
            ]["metadata"]
            if (
                row["critical_it_capacity_as_reported_mw"] != 96
                or row["portfolio_capacity_as_reported_mw"] != 288
                or "Only the Sterling facility" not in row["facility_scope"]
                or "288 MW portfolio total" not in row["capacity_scope"]
            ):
                raise AssertionError("Dulles 96 MW must remain facility scoped")
            if (
                "ongoing development" not in row["status_scope"]
                or "not establish Blackstone" not in row["role_guardrail"]
                or "Neither forecast" not in row["forecast_guardrail"]
            ):
                raise AssertionError("Dulles status, roles, and forecasts must stay narrow")
            if "not normalized" not in row["classification_guardrail"]:
                raise AssertionError("Dulles hyperscale descriptor must remain metadata")

    def test_exact_candidates_import_offline_with_narrow_semantics(self) -> None:
        v13_definition = (ROOT / "sources" / V13_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name in SOURCES:
            self.assertNotIn(name, v13_definition)

        documents: dict[str, dict[str, Any]] = {}
        seen_captures: set[str] = set()
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
                        documents[name] = document
                        self._assert_candidate_guardrails(name, document)
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {expected["retrieved_at"]},
                        )

                        for evidence in document["evidence"]:
                            capture = CAPTURES[evidence["content_hash"]]
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(
                                str(capture["body_bytes"]),
                                metadata["content_hash_scope"],
                            )
                            self.assertIn(
                                str(capture["headers_bytes"]),
                                metadata["capture_headers_scope"],
                            )
                            self.assertEqual(
                                metadata["capture_headers_sha256"],
                                capture["headers_sha256"],
                            )
                            self.assertEqual(metadata["http_status"], 200)
                            self.assertEqual(
                                metadata["response_http_date"],
                                capture["response_date"],
                            )
                            self.assertEqual(
                                metadata["http_last_modified_at"],
                                capture["last_modified"],
                            )
                            self.assertEqual(
                                metadata["content_type"], capture["content_type"]
                            )
                            self.assertEqual(metadata["response_header_blocks"], 1)
                            self.assertEqual(evidence["source_url"], capture["url"])
                            self.assertEqual(metadata["requested_url"], capture["url"])
                            self.assertEqual(metadata["effective_url"], capture["url"])
                            self.assertEqual(metadata["canonical_url"], capture["url"])
                            self.assertEqual(evidence["license"], capture["license"])
                            self.assertIn(
                                "not redistributed", metadata["rights_scope"]
                            )
                            seen_captures.add(evidence["content_hash"])

                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=expected["retrieved_at"],
                        )

                self.assertEqual(seen_captures, set(CAPTURES))
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 4), ("project", 4)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT project_entity.stable_key,
                                   campus_entity.stable_key,
                                   lifecycle_observations.status,
                                   lifecycle_observations.as_of_date,
                                   lifecycle_observations.method
                            FROM lifecycle_observations
                            JOIN entities AS project_entity
                              ON project_entity.id = lifecycle_observations.entity_id
                            JOIN projects ON projects.entity_id = project_entity.id
                            JOIN entities AS campus_entity
                              ON campus_entity.id = projects.target_entity_id
                            ORDER BY project_entity.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[
                                "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-06-29",
                            "authoritative_physical_status_update",
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-edgeconnex-greater-osaka.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-edgeconnex-greater-osaka.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-03-17",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-05-27",
                            "authoritative_physical_status_update",
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-vantage-lighthouse-port-washington.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-vantage-lighthouse-port-washington.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-06-12",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key, capacity_estimates.metric,
                                   capacity_estimates.stage, capacity_estimates.low,
                                   capacity_estimates.base, capacity_estimates.high,
                                   capacity_estimates.unit,
                                   capacity_estimates.target_date
                            FROM capacity_estimates
                            JOIN entities
                              ON entities.id = capacity_estimates.entity_id
                            ORDER BY entities.stable_key, capacity_estimates.metric
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[
                                "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json"
                            ]["project_key"],
                            "critical_it_mw",
                            "planned",
                            96.0,
                            96.0,
                            96.0,
                            "MW",
                            None,
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json"
                            ]["campus_key"],
                            "generation_nameplate_mw",
                            "planned",
                            2450.0,
                            2450.0,
                            2450.0,
                            "MW",
                            None,
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-vantage-lighthouse-port-washington.json"
                            ]["campus_key"],
                            "critical_it_mw",
                            "planned",
                            902.0,
                            902.0,
                            902.0,
                            "MW",
                            None,
                        ),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   workload_observations.workload,
                                   workload_observations.as_of_date,
                                   workload_observations.method
                            FROM workload_observations
                            JOIN entities
                              ON entities.id = workload_observations.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[
                                "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json"
                            ]["campus_key"],
                            "ai_specialized_unspecified",
                            "2026-04-27",
                            "company_disclosure",
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-vantage-lighthouse-port-washington.json"
                            ]["campus_key"],
                            "ai_specialized_unspecified",
                            "2026-07-19",
                            "company_disclosure",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    10,
                )
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT content_hash FROM evidence"
                        )
                    },
                    set(CAPTURES),
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots"
                    ).fetchone()[0],
                    8,
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
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric IN ('pue', 'annual_energy_mwh', "
                        "'grid_connection_mw', 'gross_facility_mw')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE stage != 'planned'"
                    ).fetchone()[0],
                    0,
                )
                edge_project_key = SOURCES[
                    "curated-official-2026-07-19-edgeconnex-greater-osaka.json"
                ]["project_key"]
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "JOIN entities ON entities.id = capacity_estimates.entity_id "
                        "WHERE entities.stable_key = ?",
                        (edge_project_key,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_candidate_guardrails(self) -> None:
        edge_name = "curated-official-2026-07-19-edgeconnex-greater-osaka.json"
        vantage_name = (
            "curated-official-2026-07-19-vantage-lighthouse-port-washington.json"
        )
        oracle_name = (
            "curated-official-2026-07-19-oracle-project-jupiter-dona-ana.json"
        )
        dulles_name = (
            "curated-official-2026-07-19-digital-realty-digital-dulles-current-development.json"
        )
        edge = self._load(edge_name)
        vantage = self._load(vantage_name)
        oracle = self._load(oracle_name)
        dulles = self._load(dulles_name)
        mutations: list[tuple[str, dict[str, Any], str]] = []

        mutated = copy.deepcopy(edge)
        mutated["campus"]["roles"] = {"operator": ["EdgeConneX"]}
        mutations.append((edge_name, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(vantage)
        mutated["project"]["coordinates"] = {
            "latitude": 43.4,
            "longitude": -87.8,
        }
        mutations.append((vantage_name, mutated, "localities must remain ungeocoded"))

        mutated = copy.deepcopy(oracle)
        mutated["campus"]["geometry"] = {
            "type": "Point",
            "coordinates": [-106.7, 32.2],
        }
        mutations.append((oracle_name, mutated, "localities must remain ungeocoded"))

        mutated = copy.deepcopy(dulles)
        mutated["project"]["address"] = "Unverified street address, Sterling, Virginia"
        mutations.append(
            (dulles_name, mutated, "address must remain authoritative locality only")
        )

        mutated = copy.deepcopy(edge)
        mutated["project"]["stable_key"] += ":phase-one"
        mutations.append(
            (edge_name, mutated, "one canonical current-build project must remain")
        )

        mutated = copy.deepcopy(edge)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append(
            (edge_name, mutated, "lifecycle must remain generic under_construction")
        )

        mutated = copy.deepcopy(vantage)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(
            (vantage_name, mutated, "lifecycle must remain generic under_construction")
        )

        mutated = copy.deepcopy(oracle)
        mutated["lifecycle"][0]["as_of_date"] = "2026-06-04"
        mutations.append(
            (oracle_name, mutated, "lifecycle date must remain source scoped")
        )

        mutated = copy.deepcopy(dulles)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append(
            (dulles_name, mutated, "lifecycle must remain generic under_construction")
        )

        mutated = copy.deepcopy(vantage)
        mutated["operating_models"] = [
            {
                "entity": "campus",
                "value": "hyperscale_lease",
                "evidence_key": "vantage-lighthouse-location-page-captured-2026-07-19",
                "as_of_date": "2026-07-19",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append((vantage_name, mutated, "operating models must remain empty"))

        mutated = copy.deepcopy(dulles)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
                "evidence_key": (
                    "digital-realty-northern-virginia-transaction-2026-06-29-"
                    "captured-2026-07-19"
                ),
                "as_of_date": "2026-06-29",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (dulles_name, mutated, "workloads must remain narrowly source explicit")
        )

        mutated = copy.deepcopy(edge)
        mutated["workloads"] = [
            {
                "entity": "campus",
                "value": "ai_specialized_unspecified",
                "evidence_key": (
                    "edgeconnex-greater-osaka-construction-2026-03-17-"
                    "captured-2026-07-19"
                ),
                "as_of_date": "2026-03-17",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (edge_name, mutated, "workloads must remain narrowly source explicit")
        )

        for name, original in ((vantage_name, vantage), (oracle_name, oracle)):
            mutated = copy.deepcopy(original)
            mutated["workloads"][0]["value"] = "ai_training"
            mutations.append(
                (name, mutated, "workloads must remain narrowly source explicit")
            )

        edge_capacity = {
            "entity": "campus",
            "metric": "critical_it_mw",
            "stage": "planned",
            "unit": "MW",
            "low": 200,
            "base": 200,
            "high": 200,
            "method": "reported",
            "confidence": 0.5,
            "evidence_key": (
                "edgeconnex-greater-osaka-construction-2026-03-17-"
                "captured-2026-07-19"
            ),
            "as_of_date": "2026-03-17",
            "target_date": "2028-03-31",
            "notes": "Forbidden conversion of untyped power and phase forecast.",
        }
        mutated = copy.deepcopy(edge)
        mutated["capacities"] = [edge_capacity]
        mutations.append((edge_name, mutated, "typed capacity row count must remain exact"))

        mutated = copy.deepcopy(vantage)
        mutated["capacities"][0]["metric"] = "gross_facility_mw"
        mutations.append(
            (vantage_name, mutated, "capacity metric scope and value must remain exact")
        )

        mutated = copy.deepcopy(vantage)
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (vantage_name, mutated, "capacities must remain planned reported MW")
        )

        mutated = copy.deepcopy(vantage)
        forbidden = copy.deepcopy(mutated["capacities"][0])
        forbidden.update(
            {
                "metric": "grid_connection_mw",
                "low": 2000,
                "base": 2000,
                "high": 2000,
                "notes": "Forbidden conversion of Oracle power-system wording.",
            }
        )
        mutated["capacities"].append(forbidden)
        mutations.append(
            (vantage_name, mutated, "typed capacity row count must remain exact")
        )

        for metric, unit, value in (
            ("pue", "ratio", 1.2),
            ("annual_energy_mwh", "MWh/year", 7_901_520),
        ):
            mutated = copy.deepcopy(vantage)
            forbidden = copy.deepcopy(mutated["capacities"][0])
            forbidden.update(
                {
                    "metric": metric,
                    "unit": unit,
                    "low": value,
                    "base": value,
                    "high": value,
                    "notes": "Forbidden inferred metric.",
                }
            )
            mutated["capacities"].append(forbidden)
            mutations.append(
                (vantage_name, mutated, "typed capacity row count must remain exact")
            )

        mutated = copy.deepcopy(oracle)
        mutated["capacities"][0]["metric"] = "critical_it_mw"
        mutations.append(
            (oracle_name, mutated, "capacity metric scope and value must remain exact")
        )

        mutated = copy.deepcopy(oracle)
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (oracle_name, mutated, "capacities must remain planned reported MW")
        )

        mutated = copy.deepcopy(oracle)
        mutated["capacities"][0]["low"] = 2000
        mutated["capacities"][0]["base"] = 2000
        mutated["capacities"][0]["high"] = 2000
        mutations.append(
            (oracle_name, mutated, "capacity metric scope and value must remain exact")
        )

        for metric, unit, value in (
            ("grid_connection_mw", "MW", 2450),
            ("annual_energy_mwh", "MWh/year", 21_462_000),
            ("pue", "ratio", 1.1),
        ):
            mutated = copy.deepcopy(oracle)
            forbidden = copy.deepcopy(mutated["capacities"][0])
            forbidden.update(
                {
                    "metric": metric,
                    "unit": unit,
                    "low": value,
                    "base": value,
                    "high": value,
                    "notes": "Forbidden conversion from planned generation nameplate.",
                }
            )
            mutated["capacities"].append(forbidden)
            mutations.append(
                (oracle_name, mutated, "typed capacity row count must remain exact")
            )

        mutated = copy.deepcopy(dulles)
        mutated["capacities"][0]["low"] = 288
        mutated["capacities"][0]["base"] = 288
        mutated["capacities"][0]["high"] = 288
        mutations.append(
            (dulles_name, mutated, "capacity metric scope and value must remain exact")
        )

        mutated = copy.deepcopy(dulles)
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (dulles_name, mutated, "capacities must remain planned reported MW")
        )

        mutated = copy.deepcopy(dulles)
        mutated["capacities"][0]["target_date"] = "2027-06-30"
        mutations.append(
            (dulles_name, mutated, "capacities must remain planned reported MW")
        )

        mutated = copy.deepcopy(dulles)
        mutated["campus"]["roles"] = {"investor": ["Blackstone"]}
        mutations.append((dulles_name, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(oracle)
        aerials = {
            row["key"]: row for row in mutated["evidence"]
        }["oracle-data-centers-dona-ana-aerials-captured-2026-07-19"]
        aerials["metadata"]["abilene_cross_site_guardrail"] = ""
        mutations.append(
            (oracle_name, mutated, "Jupiter aerial dates must remain Doña Ana scoped")
        )

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_candidate_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
