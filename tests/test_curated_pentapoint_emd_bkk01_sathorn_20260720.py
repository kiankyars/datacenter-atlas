from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SOURCE_NAME = "curated-official-2026-07-20-pentapoint-emd-bkk01-sathorn.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 24_819
SOURCE_SHA256 = "98ecc046fac96abbef96a02ab76bbc661c7d7525dbf892dad4e49d6502250cb2"
RETRIEVED_AT = "2026-07-20T22:26:51Z"

CAMPUS_KEY = "curated:pentapoint-emd-bkk01-sathorn-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:current-development"
CONSTRUCTION_KEY = (
    "pentapoint-emd-bkk01-construction-2025-10-19-captured-2026-07-20"
)
LOCATION_KEY = "pentapoint-emd-bkk01-location-page-captured-2026-07-20"
BROCHURE_KEY = "pentapoint-emd-bkk01-brochure-captured-2026-07-20"
LATITUDE = 13.7248155
LONGITUDE = 100.5390396
CAMPUS_ADDRESS = (
    "Smooth Life Tower, 44 N Sathon Rd, Si Lom, Bang Rak, Bangkok 10500, "
    "Thailand"
)
PROJECT_ADDRESS = (
    "Smooth Life Tower, Floor 11, 44 N Sathon Rd, Si Lom, Bang Rak, "
    "Bangkok 10500, Thailand"
)
BROCHURE_URL = (
    "https://cdn.prod.website-files.com/654921564b746dceaed218d9/"
    "68fefda58625cb912e878f1f_EMD%20BKK-01_Brochure_2025.png"
)

CAPTURES: dict[str, dict[str, Any]] = {
    CONSTRUCTION_KEY: {
        "url": "https://pentapoint.jp/news/news-update-06",
        "publisher": "PentaPoint Data Corporation",
        "body_sha256": (
            "41edd89e9c1c60d03c5374032aafae99769c6fd1173b8185a2148262e61f7b67"
        ),
        "body_bytes": 20_492,
        "body_scope": (
            "SHA-256 of the exact 20492-byte content-decoded official HTML "
            "response body captured with curl --compressed"
        ),
        "header_sha256": (
            "7a55800ab7846da24a85868db3b521574c0fa2d5867528f5c46e7e7777b20b17"
        ),
        "header_bytes": 744,
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 6_495,
        "response_http_date": "2026-07-20T22:22:51Z",
        "last_modified": "2026-07-20T22:22:51Z",
    },
    LOCATION_KEY: {
        "url": "https://pentapoint.jp/emd/bkk01",
        "publisher": "PentaPoint Data Corporation",
        "body_sha256": (
            "bf451d0fd6a3a6e02ae0aecc8f7dba58be06cf79d6eec1ba5f7da649d44137f7"
        ),
        "body_bytes": 29_350,
        "body_scope": (
            "SHA-256 of the exact 29350-byte content-decoded official HTML "
            "response body captured with curl --compressed"
        ),
        "header_sha256": (
            "a3c489f96698052414bb7586d35d1c7f381161b011a45752f09c096caa9f2e08"
        ),
        "header_bytes": 741,
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 8_392,
        "response_http_date": "2026-07-20T22:23:42Z",
        "last_modified": "2026-07-20T22:23:42Z",
    },
    BROCHURE_KEY: {
        "url": BROCHURE_URL,
        "publisher": "PentaPoint Data Center Development Corporation",
        "body_sha256": (
            "a2a3a11a842cf92941eb74cdfda77c66731bf72ced8ac0fa58d64796e0758aa8"
        ),
        "body_bytes": 1_491_814,
        "body_scope": (
            "SHA-256 of the exact 1491814-byte publisher-linked PNG brochure "
            "response body"
        ),
        "header_sha256": (
            "18c57b1abca575c6e7e7e808e3ba7179b50569c4ef52feabf30ae662cd531fb8"
        ),
        "header_bytes": 664,
        "content_type": "image/png",
        "content_encoding": None,
        "content_length": 1_491_814,
        "download_bytes": None,
        "response_http_date": RETRIEVED_AT,
        "last_modified": "2025-10-27T05:05:43Z",
    },
}


class PentaPointEmdBkk01SathornCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("PentaPoint EMD BKK01 import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write_document(self, path: Path, document: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _database_state(
        self, source_path: Path = SOURCE_PATH, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(
                            result.entities_created, 2 if iteration == 0 else 0
                        )
                        self.assertEqual(
                            result.evidence_created, 3 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence, notes "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload FROM workload_observations "
                    "JOIN entities ON entities.id = workload_observations.entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _assert_document_rejected(
        self, document: dict[str, Any], pattern: str
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            path = temporary_path / SOURCE_NAME
            self._write_document(path, document)
            connection, _ = initialize(temporary_path / "atlas.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(ValueError, pattern):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        path,
                        retrieved_at=RETRIEVED_AT,
                    )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE_PATH.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE_PATH.stat().st_mode), 0o644)
        self.assertEqual(SOURCE_PATH.stat().st_size, SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(), SOURCE_SHA256
        )
        text = SOURCE_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(
            text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 3)
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

    def test_three_capture_hashes_and_response_metadata_are_exact(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["kind"], "company_disclosure")
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], "pentapoint_official_webflow")
                self.assertEqual(item["published_at"], None)
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["license"], "all-rights-reserved")
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertEqual(metadata["content_hash_scope"], expected["body_scope"])
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertEqual(
                    metadata["capture_headers_scope"],
                    "SHA-256 of the exact "
                    f"{expected['header_bytes']}-byte raw HTTP response-header capture",
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["response_http_date"]
                )
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertIn("credential-free curl GET", metadata["retrieval_method"])
                self.assertIn(
                    "No authorization", metadata["request_credentials_guardrail"]
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                if expected["content_encoding"] is None:
                    self.assertNotIn("content_encoding_as_received", metadata)
                    self.assertNotIn("curl_size_download_bytes_as_received", metadata)
                else:
                    self.assertEqual(
                        metadata["content_encoding_as_received"],
                        expected["content_encoding"],
                    )
                    self.assertEqual(
                        metadata["curl_size_download_bytes_as_received"],
                        expected["download_bytes"],
                    )
                    self.assertEqual(metadata["canonical_url"], expected["url"])

        forbidden = {
            "authorization",
            "cookie",
            "local_ip",
            "local_port",
            "remote_ip",
            "remote_port",
            "set-cookie",
        }
        for item in evidence.values():
            self.assertTrue(
                forbidden.isdisjoint(
                    {field.casefold() for field in item["metadata"].keys()}
                )
            )

    def test_publisher_map_brochure_address_and_roles_are_exact(self) -> None:
        document = self._load()
        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        location = metadata[LOCATION_KEY]
        brochure = metadata[BROCHURE_KEY]
        self.assertEqual(location["reported_identity"], "EMD BKK-01")
        self.assertEqual(
            location["reported_locality"], "Sathorn, Bangkok, Thailand"
        )
        self.assertEqual(
            location["embedded_map_widget"],
            {
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "zoom": 14,
                "aria_label": "PentaPoint EMD BKK-01",
            },
        )
        self.assertEqual(
            location["coordinate_source_type"],
            "publisher_supplied_embedded_map_widget",
        )
        self.assertIn("not a parcel boundary", location["coordinate_scope"])
        for forbidden_source in (
            "search result",
            "geocoder",
            "OpenStreetMap",
            "satellite image",
            "brochure basemap",
            "computer vision",
        ):
            self.assertIn(forbidden_source, location["coordinate_guardrail"])

        self.assertEqual(brochure["image_width_px"], 2400)
        self.assertEqual(brochure["image_height_px"], 1707)
        self.assertEqual(brochure["image_mode"], "RGB")
        self.assertEqual(brochure["reported_building"], "Smooth Life Tower")
        self.assertEqual(
            brochure["reported_address"],
            "44 N Sathon Rd, Si Lom, Bang Rak, Bangkok 10500",
        )
        self.assertEqual(brochure["reported_building_floors"], 26)
        self.assertEqual(
            brochure["reported_data_center_floor"], "Floor 11, full dedicated floor"
        )
        self.assertIn("creates no second entity", brochure["address_scope"])

        expected_roles = {
            "developer": ["PentaPoint Corporation"],
            "operator": ["AIMS Data Center"],
        }
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(
                entity["stable_key"],
                CAMPUS_KEY if entity_name == "campus" else PROJECT_KEY,
            )
            self.assertEqual(entity["country"], "Thailand")
            self.assertEqual(entity["roles"], expected_roles)
            self.assertEqual(
                entity["coordinates"],
                {"latitude": LATITUDE, "longitude": LONGITUDE},
            )
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], LOCATION_KEY)
            self.assertEqual(entity["method"], "authoritative_site_plan")
            self.assertEqual(entity["as_of_date"], "2026-07-20")
        self.assertEqual(document["campus"]["address"], CAMPUS_ADDRESS)
        self.assertEqual(document["project"]["address"], PROJECT_ADDRESS)
        self.assertEqual(location["reported_operator"], "AIMS Data Center")
        self.assertIn("named operator", location["operator_scope"])
        self.assertIn("PentaPoint", metadata[CONSTRUCTION_KEY]["role_scope"])

    def test_construction_is_historical_despite_dates_forecast_and_marketing(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CONSTRUCTION_KEY,
                    "as_of_date": "2025-10-19",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        construction = document["evidence"][0]["metadata"]
        location = document["evidence"][1]["metadata"]
        brochure = document["evidence"][2]["metadata"]
        self.assertEqual(construction["reported_event_date"], "2025-10-19")
        self.assertEqual(
            construction["visible_date_conflict"],
            {
                "headline_and_body_date": "2025-10-19",
                "duplicated_template_date": "2024-09-02",
            },
        )
        self.assertIn("published_at is therefore null", construction["publication_date_guardrail"])
        self.assertIn("historical generic under_construction", construction["status_scope"])
        self.assertIn("does not isolate", construction["status_scope"])
        self.assertEqual(construction["reported_operational_forecast"], "January 2026")
        self.assertIn("forecast, not a realized event", construction["status_freshness_guardrail"])
        self.assertIn("creates no target_date", construction["forecast_guardrail"])
        self.assertIn("no dated post-forecast", construction["status_freshness_guardrail"])
        self.assertIn("present-tense", location["status_guardrail"])
        self.assertIn("no dated completion", location["status_guardrail"])
        self.assertIn("does not replace", location["status_guardrail"])
        self.assertIn("undated facility-marketing", brochure["status_guardrail"])
        self.assertIn("cannot advance the lifecycle", brochure["status_guardrail"])
        for evidence in document["evidence"]:
            self.assertIsNone(evidence["published_at"])
        self.assertNotIn(
            "operational", {row["value"] for row in document["lifecycle"]}
        )

    def test_capacity_colocation_edge_and_exclusions_are_narrow(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": BROCHURE_KEY,
                    "as_of_date": "2026-07-20",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(capacity["entity"], "project")
        self.assertEqual(capacity["metric"], "critical_it_mw")
        self.assertEqual(capacity["stage"], "planned")
        self.assertEqual(capacity["unit"], "MW")
        self.assertEqual(
            (capacity["low"], capacity["base"], capacity["high"]),
            (0.8, 0.8, 0.8),
        )
        self.assertEqual(capacity["evidence_key"], LOCATION_KEY)
        self.assertEqual(capacity["as_of_date"], "2026-07-20")
        self.assertIsNone(capacity["target_date"])
        self.assertIn("separately discussed 6 MW expansion is excluded", capacity["notes"])

        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        construction = metadata[CONSTRUCTION_KEY]
        location = metadata[LOCATION_KEY]
        brochure = metadata[BROCHURE_KEY]
        self.assertEqual(construction["reported_capacity_under_development_kw"], 800)
        self.assertEqual(location["reported_it_load_kw"], 800)
        self.assertEqual(brochure["reported_it_power_kw"], 800)
        self.assertEqual(construction["reported_discussed_expansion_mw"], 6)
        self.assertIn("only under discussion", construction["expansion_guardrail"])
        self.assertIn("never added to 800 kW", construction["expansion_guardrail"])
        self.assertEqual(location["reported_rack_density_kw"], 10.5)
        self.assertIn("not multiplied", location["rack_density_guardrail"])
        self.assertEqual(brochure["reported_classification"], "colocation Edge Data Center")
        for record in (construction, location, brochure):
            operating_scope = (
                record["classification_scope"]
                if "classification_scope" in record
                else record["operating_model_scope"]
            )
            self.assertIn("edge", operating_scope.casefold())
            self.assertIn("colocation", operating_scope.casefold())
            workload_scope = record.get("workload_guardrail", operating_scope)
            self.assertTrue(
                "no normalized" in workload_scope
                or "does not establish installed" in workload_scope
            )
            self.assertIn("annual energy", record["energy_guardrail"])
            self.assertIn("PUE", record["energy_guardrail"])
        self.assertIn("edge remains", location["operating_model_scope"])
        self.assertIn("no generator nameplate", location["energy_guardrail"])
        self.assertIn("no utility role", brochure["power_guardrail"])

    def test_parent_nonadditivity_geometry_and_collisions_are_guarded(self) -> None:
        document = self._load()
        claimed_stable = {CAMPUS_KEY, PROJECT_KEY}
        claimed_evidence = set(CAPTURES)
        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE_PATH:
                continue
            other = json.loads(path.read_text(encoding="utf-8"))
            stable_keys = {
                entity["stable_key"]
                for entity in (other.get("campus"), other.get("project"))
                if isinstance(entity, dict) and "stable_key" in entity
            }
            evidence_keys = {
                item["key"]
                for item in other.get("evidence", [])
                if isinstance(item, dict) and "key" in item
            }
            stable_overlap = sorted(claimed_stable & stable_keys)
            evidence_overlap = sorted(claimed_evidence & evidence_keys)
            if stable_overlap or evidence_overlap:
                collisions[path.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(collisions, {})

        for entity_name in ("campus", "project"):
            self.assertIsNone(document[entity_name]["geometry"])
        for evidence in document["evidence"]:
            metadata = evidence["metadata"]
            if "entity_model_guardrail" in metadata:
                self.assertIn("internal parent container", metadata["entity_model_guardrail"])
                self.assertIn("must not be added", metadata["entity_model_guardrail"])
            if "collision_guardrail" in metadata:
                self.assertIn("not merged", metadata["collision_guardrail"])
        self.assertIn(
            "physical-site count",
            document["evidence"][0]["metadata"]["imagery_guardrail"],
        )
        self.assertIn(
            "creates no second entity",
            document["evidence"][2]["metadata"]["address_scope"],
        )

    def test_offline_import_is_exact_idempotent_and_order_independent(self) -> None:
        once = self._database_state()
        twice = self._database_state(repetitions=2)
        self.assertEqual(once, twice)

        with tempfile.TemporaryDirectory() as temporary:
            reordered_path = Path(temporary) / SOURCE_NAME
            document = self._load()
            reordered = {
                key: (
                    [
                        {field: value for field, value in reversed(list(item.items()))}
                        for item in reversed(value)
                    ]
                    if key == "evidence"
                    else value
                )
                for key, value in reversed(list(document.items()))
            }
            self._write_document(reordered_path, reordered)
            reordered_state = self._database_state(reordered_path)
        self.assertEqual(once, reordered_state)

        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            projects,
            capacities,
            operating_models,
            workloads,
        ) = once
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(
            evidence,
            tuple(
                (
                    key,
                    CAPTURES[key]["body_sha256"],
                    RETRIEVED_AT,
                    CAPTURES[key]["url"],
                )
                for key in sorted(CAPTURES)
            ),
        )
        self.assertEqual(len(snapshots), 2)
        snapshots_by_key = {row[0]: row for row in snapshots}
        for stable_key, expected_address in (
            (CAMPUS_KEY, CAMPUS_ADDRESS),
            (PROJECT_KEY, PROJECT_ADDRESS),
        ):
            row = snapshots_by_key[stable_key]
            self.assertEqual(
                json.loads(row[2]),
                {
                    "address": expected_address,
                    "country": "Thailand",
                    "role:developer": "PentaPoint Corporation",
                    "role:operator": "AIMS Data Center",
                    "source_dataset": "curated_official_sources",
                },
            )
            self.assertEqual(row[3], LATITUDE)
            self.assertEqual(row[4], LONGITUDE)
            self.assertEqual(
                json.loads(row[5]),
                {"coordinates": [LONGITUDE, LATITUDE], "type": "Point"},
            )
            self.assertEqual(row[6], "2026-07-20")
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_site_plan")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2025-10-19",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(len(capacities), 1)
        self.assertEqual(
            capacities[0][0:7],
            (PROJECT_KEY, "critical_it_mw", "planned", "MW", 0.8, 0.8, 0.8),
        )
        self.assertEqual(
            capacities[0][7:12],
            ("2026-07-20", None, RETRIEVED_AT, "reported", 0.99),
        )
        self.assertIn("6 MW expansion is excluded", capacities[0][12])
        self.assertEqual(
            operating_models,
            (
                (
                    PROJECT_KEY,
                    "colocation",
                    "2026-07-20",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(workloads, ())

    def test_semantic_mutations_cannot_invent_status_energy_or_location(self) -> None:
        weak_status = copy.deepcopy(self._load())
        weak_status["lifecycle"][0]["method"] = "analyst_synthesis"
        self._assert_document_rejected(
            weak_status,
            "construction status requires authoritative_construction_start",
        )

        annual_energy = copy.deepcopy(self._load())
        annual_energy["capacities"][0].update(
            {
                "metric": "annual_energy_mwh",
                "stage": "measured",
                "unit": "MWh/year",
            }
        )
        self._assert_document_rejected(
            annual_energy,
            "measured annual energy requires utility_record or government_record",
        )

        ungrounded_location = copy.deepcopy(self._load())
        ungrounded_location["project"]["coordinates"] = None
        self._assert_document_rejected(
            ungrounded_location,
            "method must be authoritative_locality when coordinates and geometry are null",
        )

    def test_source_imports_offline_in_both_workspace_layouts(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated import CuratedOfficialSourceAdapter
from {package}.database import initialize
from {package}.service import validate_database

source = Path({str(SOURCE_PATH)!r})
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            first = CuratedOfficialSourceAdapter().import_file(
                connection, source, retrieved_at={RETRIEVED_AT!r}
            )
            second = CuratedOfficialSourceAdapter().import_file(
                connection, source, retrieved_at={RETRIEVED_AT!r}
            )
        assert first.entities_created == 2
        assert first.evidence_created == 3
        assert second.entities_created == 0
        assert second.evidence_created == 0
        assert first.warnings == second.warnings == ()
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        values = {{
            "capacity": connection.execute("SELECT metric || ':' || stage || ':' || base FROM capacity_estimates").fetchone()[0],
            "lifecycle": connection.execute("SELECT status FROM lifecycle_observations").fetchone()[0],
            "operating_model": connection.execute("SELECT operating_model FROM operating_model_observations").fetchone()[0],
        }}
        print(json.dumps({{"counts": counts, "values": values}}, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "counts": {
                            "capacity": 1,
                            "entities": 2,
                            "evidence": 3,
                            "lifecycle": 1,
                            "operating_models": 1,
                            "snapshots": 2,
                            "workloads": 0,
                        },
                        "values": {
                            "capacity": "critical_it_mw:planned:0.8",
                            "lifecycle": "under_construction",
                            "operating_model": "colocation",
                        },
                    },
                )


if __name__ == "__main__":
    unittest.main()
