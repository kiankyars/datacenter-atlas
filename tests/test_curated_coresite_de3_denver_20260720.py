from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/curated-official-2026-07-20-coresite-de3-denver.json"
SOURCE_BYTES = 35_669
SOURCE_SHA256 = "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868"
COORDINATE_SUCCESSOR = (
    ROOT / "sources/curated-official-2026-07-20-coresite-de3-denver-v2.json"
)
COORDINATE_SUCCESSOR_BYTES = 52_842
COORDINATE_SUCCESSOR_SHA256 = (
    "9d0727dcbb8ed42b55887012d0d267188e4561d67f4694dd49ce2e834ed64ab2"
)
RETRIEVED_AT = "2026-07-20T10:42:21Z"
V47_SHA256 = "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"

CAMPUS_KEY = "curated:coresite-de3-race-street-campus"
PROJECT_KEY = "curated:coresite-de3-race-street-campus:de3"
ADDRESS = "4900 Race Street, Denver, Colorado 80216, United States"
CONSTRUCTION_KEY = "coresite-de3-construction-current-captured-2026-07-20"
FACILITY_KEY = "coresite-de3-facility-current-captured-2026-07-20"
TOPOUT_KEY = "coresite-de3-topout-2025-10-06-captured-2026-07-20"
SPEC_KEY = "coresite-de3-specification-current-captured-2026-07-20"
COMMUNITY_KEY = "coresite-de3-community-update-2026-06-25-captured-2026-07-20"

CAPTURES = {
    CONSTRUCTION_KEY: {
        "hash": "fb4f5a3e686d22a50c921c9264e7045ca318a687fc17daa0bfe91885f304f7fb",
        "body_bytes": 239_924,
        "headers_hash": "843e53d1db968317982db8df63329a4976d1bc94725e00354d714f9bf4e29df4",
        "headers_bytes": 6_926,
        "curl_hash": "62dd9910fb8e8a438438609ae6c3b705685e156734aa18340eef63e4bcda0b3e",
        "curl_bytes": 9_620,
        "download": 32_474,
        "num_headers": 28,
        "blocks": 2,
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "content_length": None,
        "response_date": "2026-07-20T10:30:43Z",
        "last_modified": "2026-07-13T17:47:29Z",
        "url": "https://www.coresite.com/en-us/data-centers/denver/de3-construction",
    },
    FACILITY_KEY: {
        "hash": "99720e18665fabb5cb2d09308b60326c9bcb226dd1ff2648fa95ba3b21fdb894",
        "body_bytes": 191_985,
        "headers_hash": "00c6dcd97daf5659e2489884120888f5fd0ec274e18e55df3cbd7f59f5420e1f",
        "headers_bytes": 6_974,
        "curl_hash": "bb1d0e98d4cf5812d64f7cccff3f51dc494929e2e74fbcd187e5174c072e8e67",
        "curl_bytes": 9_548,
        "download": 26_941,
        "num_headers": 28,
        "blocks": 2,
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "content_length": None,
        "response_date": "2026-07-20T10:30:43Z",
        "last_modified": "2026-07-13T17:47:29Z",
        "url": "https://www.coresite.com/data-center/de3-denver-co",
    },
    TOPOUT_KEY: {
        "hash": "0ddd551cfb339fc8391bb7be56d59f14d587bab7221bf1924763415a9947f5e7",
        "body_bytes": 132_518,
        "headers_hash": "90a2fdf0e1ec8009e6e7f96d0a88add5a6a660107e3a9582cd9bc221434edd5d",
        "headers_bytes": 6_549,
        "curl_hash": "d06d8c7bfce2ffe2ebd1ce6bd25db58186ad38014bfc2728d367daeda5139acf",
        "curl_bytes": 9_778,
        "download": 21_328,
        "num_headers": 29,
        "blocks": 2,
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "content_length": None,
        "response_date": "2026-07-20T10:30:43Z",
        "last_modified": "2026-07-13T17:47:33Z",
        "url": (
            "https://www.coresite.com/news/coresite-achieves-key-construction-"
            "milestone-for-new-de3-data-center-in-denver"
        ),
    },
    SPEC_KEY: {
        "hash": "3883645e759b91f59887b225c46b5bdfb98f6168bacd0057bbf0780162cff2d1",
        "body_bytes": 4_717_982,
        "headers_hash": "eadf3107e69d542c55944d59af9d94e60e1a1628436c5fa82c4e642c4db43ad9",
        "headers_bytes": 1_724,
        "curl_hash": "cfd5028b852f73d77fdca9b9dc95c585b876754714da8e2d704f2034b56207ee",
        "curl_bytes": 9_782,
        "download": 4_717_982,
        "num_headers": 30,
        "blocks": 1,
        "content_type": "application/pdf",
        "encoding": None,
        "content_length": 4_717_982,
        "response_date": "2026-07-20T10:30:43Z",
        "last_modified": "2026-04-15T16:34:12Z",
        "url": (
            "https://www.coresite.com/hubfs/-website-documents/facility-"
            "specifications/sp-CoreSite-Denver-DE3-Spec-Sheet.pdf"
        ),
    },
    COMMUNITY_KEY: {
        "hash": "f0f7fbae344bf40756cd290f03f7416aa990e5264721988a1f80b05778e4fe7a",
        "body_bytes": 145_365,
        "headers_hash": "e3f4b087ce2c0c9287ce7f76d61d7ac183a7c255320b24a0c66755a270c97ac7",
        "headers_bytes": 1_730,
        "curl_hash": "ee528fa191b71bec5a1017d1c7549ffb9babe5e48bbf926870e2eab936967a61",
        "curl_bytes": 9_760,
        "download": 145_365,
        "num_headers": 30,
        "blocks": 1,
        "content_type": "application/pdf",
        "encoding": None,
        "content_length": 145_365,
        "response_date": RETRIEVED_AT,
        "last_modified": "2026-06-25T16:30:03Z",
        "url": (
            "https://www.coresite.com/hubfs/-website-documents/DE3-docs/"
            "DE3%20Construction%20Update%2006-25-2026.pdf"
        ),
    },
}


class CoreSiteDe3DenverCuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("CoreSite DE3 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            path = Path(temporary) / SOURCE.name
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    path,
                    retrieved_at=RETRIEVED_AT,
                )
            finally:
                connection.close()

    def _state(self, repetitions: int = 1) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            SOURCE,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(result.entities_created, 2 if iteration == 0 else 0)
                        self.assertEqual(result.evidence_created, 5 if iteration == 0 else 0)
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT content_hash, retrieved_at, source_url FROM evidence "
                    "ORDER BY content_hash",
                    "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
                    "tags_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, method, "
                    "confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date, "
                    "target_date, recorded_at, method, confidence FROM capacity_estimates "
                    "JOIN entities ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, operating_model, as_of_date, recorded_at, "
                    "method, confidence FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, method, "
                    "confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        self.assertEqual(SOURCE.stat().st_size, SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        text = SOURCE.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        self.assertEqual(
            set(document),
            {
                "schema_version",
                "evidence",
                "campus",
                "project",
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            },
        )

    def test_capture_contracts_are_exact_closed_and_telemetry_free(self) -> None:
        forbidden = {
            "authorization",
            "certs",
            "cookie",
            "local_ip",
            "local_port",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        records = {record["key"]: record for record in self._load()["evidence"]}
        self.assertEqual(set(records), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(key=key):
                record = records[key]
                metadata = record["metadata"]
                self.assertEqual(record["kind"], "company_disclosure")
                self.assertEqual(record["publisher"], "CoreSite")
                self.assertEqual(record["source_family"], "coresite_official_website")
                self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(record["content_hash"], expected["hash"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte', metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_hash"]
                )
                self.assertIn(
                    f'{expected["headers_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"], expected["curl_hash"]
                )
                self.assertIn(
                    f'{expected["curl_bytes"]}-byte',
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["content_encoding_as_received"], expected["encoding"]
                )
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download"],
                )
                self.assertEqual(
                    metadata["curl_size_header_bytes"], expected["headers_bytes"]
                )
                self.assertEqual(metadata["curl_num_headers"], expected["num_headers"])
                self.assertEqual(metadata["response_header_blocks"], expected["blocks"])
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["response_http_date"], expected["response_date"])
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertTrue(
                    forbidden.isdisjoint(field.casefold() for field in metadata)
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )

    def test_exact_identity_roles_address_and_no_geocode(self) -> None:
        document = self._load()
        expected_roles = {
            "developer": ["CoreSite"],
            "operator": ["CoreSite"],
            "utility": ["Xcel Energy"],
        }
        for entity, key, name in (
            (document["campus"], CAMPUS_KEY, "CoreSite DE3 Race Street Campus"),
            (document["project"], PROJECT_KEY, "CoreSite DE3"),
        ):
            self.assertEqual(entity["stable_key"], key)
            self.assertEqual(entity["name"], name)
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], ADDRESS)
            self.assertEqual(entity["roles"], expected_roles)
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], FACILITY_KEY)
            self.assertEqual(entity["as_of_date"], "2026-07-20")
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        facility = document["evidence"][1]["metadata"]
        self.assertEqual(facility["address_as_reported"], "4900 Race St., Denver, CO 80216")
        self.assertEqual(facility["reported_campus_building_count"], 3)
        self.assertIn("no coordinate", facility["identity_scope"])
        self.assertIn("unique-site count", facility["identity_scope"])
        self.assertNotIn("contractor", expected_roles)
        self.assertIn(
            "does not allocate", document["evidence"][2]["metadata"]["contractor_guardrail"]
        )

    def test_current_status_is_construction_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CONSTRUCTION_KEY,
                    "as_of_date": "2026-07-20",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        current_scope = document["evidence"][0]["metadata"]["current_status_scope"]
        for unsupported in (
            "completion",
            "energization",
            "commissioning",
            "occupancy",
            "operation",
            "current load",
            "measured consumption",
        ):
            self.assertIn(unsupported, current_scope)
        historical = document["evidence"][2]["metadata"]["physical_scope"]
        self.assertIn("historical structural milestone", historical)
        self.assertIn("later retained current page", historical)
        community = document["evidence"][4]["metadata"]
        self.assertIn("future tense", community["generator_activity_scope"])
        for unsupported in (
            "testing-started",
            "commissioning-started",
            "commissioning-completed",
            "energization",
            "operation",
        ):
            self.assertIn(unsupported, community["generator_activity_scope"])

    def test_capacities_are_nested_planned_critical_power_only(self) -> None:
        capacities = self._load()["capacities"]
        self.assertEqual(
            [
                (
                    row["entity"],
                    row["metric"],
                    row["stage"],
                    row["base"],
                    row["evidence_key"],
                    row["as_of_date"],
                    row["target_date"],
                )
                for row in capacities
            ],
            [
                (
                    "campus",
                    "critical_it_mw",
                    "planned",
                    60,
                    TOPOUT_KEY,
                    "2025-10-06",
                    None,
                ),
                (
                    "project",
                    "critical_it_mw",
                    "planned",
                    18,
                    SPEC_KEY,
                    "2026-07-20",
                    None,
                ),
            ],
        )
        for row in capacities:
            self.assertEqual((row["low"], row["base"], row["high"]), (row["base"],) * 3)
            self.assertIn("nested", row["notes"])
            self.assertIn("non-additive", row["notes"])
            for unsupported in (
                "grid connection",
                "generation",
                "current load",
                "annual energy",
                "measured consumption",
                "proof of operation",
            ):
                self.assertIn(unsupported, row["notes"])
        self.assertEqual(sum(row["base"] for row in capacities), 78)
        self.assertIn("never be summed", capacities[0]["notes"])
        self.assertFalse(
            any(
                row["metric"]
                in {
                    "grid_connection_mw",
                    "gross_facility_mw",
                    "generation_nameplate_mw",
                    "annual_energy_mwh",
                }
                for row in capacities
            )
        )

    def test_type_and_workload_claims_are_bounded(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": TOPOUT_KEY,
                    "as_of_date": "2025-10-06",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["workloads"], [])
        topout = document["evidence"][2]["metadata"]
        self.assertIn("multi-tenant colocation", topout["operating_model_scope"])
        self.assertIn("not current service", topout["operating_model_scope"])
        for record in document["evidence"]:
            scope = record["metadata"].get("workload_scope")
            if scope is None:
                continue
            self.assertIn("no normalized workload", scope.casefold())
            self.assertTrue("tenant" in scope.casefold())
            self.assertTrue("current" in scope.casefold())

    def test_water_substation_and_backup_power_remain_metadata(self) -> None:
        document = self._load()
        construction = document["evidence"][0]["metadata"]
        spec = document["evidence"][3]["metadata"]
        community = document["evidence"][4]["metadata"]
        self.assertEqual(
            construction["reported_expected_water_gallons_per_kw_per_day_approximate"],
            13,
        )
        self.assertIn("nonstandard", construction["water_scope"])
        self.assertIn("creates no WUE", construction["water_scope"])
        self.assertEqual(spec["reported_utility_input_voltage_kv"], 13.2)
        self.assertIn("voltage, not power", spec["utility_scope"])
        self.assertIn("no grid-connection MW", spec["substation_guardrail"])
        self.assertEqual(community["reported_current_backup_generator_count"], 6)
        self.assertEqual(community["reported_full_build_backup_generator_count"], 14)
        self.assertIn("no generator MW", community["generation_guardrail"])
        self.assertEqual(
            {row["metric"] for row in document["capacities"]}, {"critical_it_mw"}
        )

    def test_offline_import_is_valid_exact_and_idempotent(self) -> None:
        state = self._state()
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = state
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(len(evidence), 5)
        self.assertEqual({row[1] for row in evidence}, {RETRIEVED_AT})
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        for row in snapshots:
            self.assertEqual(row[2:5], (None, None, None))
            tags = json.loads(row[5])
            self.assertEqual(tags["address"], ADDRESS)
            self.assertEqual(tags["role:developer"], "CoreSite")
            self.assertEqual(tags["role:operator"], "CoreSite")
            self.assertEqual(tags["role:utility"], "Xcel Energy")
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-07-20",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            ),
        )
        self.assertEqual(
            capacities,
            (
                (
                    CAMPUS_KEY,
                    "critical_it_mw",
                    "planned",
                    60.0,
                    "2025-10-06",
                    None,
                    RETRIEVED_AT,
                    "reported",
                    0.99,
                ),
                (
                    PROJECT_KEY,
                    "critical_it_mw",
                    "planned",
                    18.0,
                    "2026-07-20",
                    None,
                    RETRIEVED_AT,
                    "reported",
                    0.99,
                ),
            ),
        )
        self.assertEqual(
            models,
            (
                (
                    PROJECT_KEY,
                    "colocation",
                    "2025-10-06",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(workloads, ())
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(self._state(repetitions=2), state)

    def test_keys_are_collision_free_and_v47_is_unchanged(self) -> None:
        document = self._load()
        entity_keys = {document["campus"]["stable_key"], document["project"]["stable_key"]}
        evidence_keys = {record["key"] for record in document["evidence"]}
        self.assertTrue(COORDINATE_SUCCESSOR.is_file())
        self.assertEqual(COORDINATE_SUCCESSOR.stat().st_size, COORDINATE_SUCCESSOR_BYTES)
        self.assertEqual(
            hashlib.sha256(COORDINATE_SUCCESSOR.read_bytes()).hexdigest(),
            COORDINATE_SUCCESSOR_SHA256,
        )
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path in {SOURCE, COORDINATE_SUCCESSOR}:
                continue
            other = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                record = other.get(field)
                if isinstance(record, dict):
                    self.assertNotIn(record.get("stable_key"), entity_keys, path)
            for record in other.get("evidence", []):
                self.assertNotIn(record.get("key"), evidence_keys, path)
        v47 = ROOT / "sources/open-seed-2026-07-20-v47.json"
        self.assertEqual(hashlib.sha256(v47.read_bytes()).hexdigest(), V47_SHA256)
        self.assertNotIn(SOURCE.name, v47.read_text(encoding="utf-8"))

    def test_import_rejects_weak_status_method_and_inferred_coordinates(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 39.78,
            "longitude": -104.95,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
