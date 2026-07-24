from __future__ import annotations

import csv
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-core-scientific-dalton-4.json"
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 19_614
SOURCE_SHA256 = "ed121928047032b1740d7f6e30faa0fad7304cb6b5144c1b708812300ebe9a09"
RECORDED_AT = "2026-07-21T04:40:54Z"

APRIL_KEY = "core-scientific-dalton-4-supplement-2026-04-21-captured-2026-07-20"
MAY_KEY = "core-scientific-q1-fy26-dalton-progress-2026-05-06-captured-2026-07-20"
CAMPUS_KEY = "curated:core-scientific-dalton-4-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:greenfield-build"
DALTON_1_LEGACY_KEY = "epoch-ai:data-center:f150f595-b366-5639-a43a-6bb98b3b91c1"
DALTON_1_ADDRESS = "2205 Industrial South Rd, Dalton, GA, 30721"
DALTON_4_ADDRESS = "3024 Old Tilton Road, Dalton, Georgia, United States"

RELEASES = (
    ROOT / "releases/2026-07-20-open-seed-v61",
    ROOT / "releases/2026-07-20-open-seed-v62",
)
CAPTURES: dict[str, dict[str, Any]] = {
    APRIL_KEY: {
        "url": (
            "https://investors.corescientific.com/sec-filings/all-sec-filings/"
            "content/0001193125-26-165121/d149019dex992.htm"
        ),
        "published_at": "2026-04-21",
        "body_bytes": 121_439,
        "body_sha256": (
            "997f23b91379cfbd3ce740bfe4c730e7b7c5b989d59f558f07dba50018704368"
        ),
        "header_bytes": 841,
        "header_sha256": (
            "3b76ade7cc63d6d9fffb684a4baca6787a078235a89cfbe7fba179778266239c"
        ),
        "writeout_bytes": 16_510,
        "writeout_sha256": (
            "6d48d514cf0bc64ee2c41ef26dbc2b3d4ccd335317d18d5036f639d1c6fb9d63"
        ),
        "compressed_bytes": 18_407,
    },
    MAY_KEY: {
        "url": (
            "https://investors.corescientific.com/sec-filings/all-sec-filings/"
            "content/0001628280-26-031246/q1fy26earningsdeck.htm"
        ),
        "published_at": "2026-05-06",
        "body_bytes": 30_814,
        "body_sha256": (
            "59d88adc09a5bac6e2bc5f8a9cd86f4e29ceb71718bbd3e1b8bcf1e68bc69dc9"
        ),
        "header_bytes": 840,
        "header_sha256": (
            "2472c0c70d89b4c1193ea9894fde4fe7e7e2f2130889857cfcb3519a9f3a4eca"
        ),
        "writeout_bytes": 16_529,
        "writeout_sha256": (
            "4a0b2e71b6719a50f48c60572364f4c3906c5a9397d111028c681b68f2af95ac"
        ),
        "compressed_bytes": 9_052,
    },
}


class CoreScientificDalton4CuratedTests(unittest.TestCase):
    def _load(self, source: Path = SOURCE) -> dict[str, Any]:
        return json.loads(source.read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError("Dalton 4 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _import(self, *, repetitions: int = 1):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = []
        for _ in range(repetitions):
            results.append(
                CuratedOfficialSourceAdapterV11().import_file(
                    connection,
                    SOURCE,
                    recorded_at=RECORDED_AT,
                )
            )
        return temporary, connection, results

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        source_bytes = SOURCE.read_bytes()
        self.assertEqual(len(source_bytes), SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), SOURCE_SHA256)
        source_text = source_bytes.decode("utf-8")
        document = json.loads(source_text)
        self.assertEqual(
            source_text,
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
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
        self.assertNotIn("/private/tmp", source_text)

    def test_capture_triples_are_exact_official_and_credential_free(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "filename_effective",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["publisher"], "Core Scientific, Inc.")
                self.assertEqual(item["source_family"], "core_scientific_sec_exhibits")
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RECORDED_AT)
                self.assertEqual(item["license"], "all-rights-reserved")
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte",
                    metadata["content_hash_scope"],
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['header_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/1.1")
                self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["compressed_bytes"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["compressed_bytes"],
                )
                self.assertEqual(metadata["response_http_date"], RECORDED_AT)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertIn("No retries", metadata["request_credentials_guardrail"])
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                self.assertTrue(
                    forbidden_telemetry_keys.isdisjoint(metadata),
                    forbidden_telemetry_keys & set(metadata),
                )

    def test_offline_import_is_exact_idempotent_and_valid(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, results = self._import(repetitions=2)
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            first, second = results
            self.assertEqual(
                (first.entities_created, first.evidence_created, first.warnings),
                (2, 2, ()),
            )
            self.assertEqual(
                (second.entities_created, second.evidence_created, second.warnings),
                (0, 0, ()),
            )
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 2,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "operating_model_observations": 1,
                    "workload_observations": 1,
                    "capacity_estimates": 2,
                },
            )

            entities = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT kind, stable_key, created_at "
                    "FROM entities ORDER BY kind, stable_key"
                )
            )
            self.assertEqual(
                entities,
                (
                    ("campus", CAMPUS_KEY, RECORDED_AT),
                    ("project", PROJECT_KEY, RECORDED_AT),
                ),
            )
            relation = connection.execute(
                "SELECT project_entities.stable_key, campus_entities.stable_key "
                "FROM projects "
                "JOIN entities AS project_entities "
                "ON project_entities.id = projects.entity_id "
                "JOIN entities AS campus_entities "
                "ON campus_entities.id = projects.target_entity_id"
            ).fetchone()
            self.assertEqual(tuple(relation), (PROJECT_KEY, CAMPUS_KEY))

            snapshots = tuple(
                connection.execute(
                    "SELECT entities.stable_key, name, tags_json, latitude, "
                    "longitude, geometry_json, as_of_date, recorded_at, method, "
                    "confidence FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                tuple(row["stable_key"] for row in snapshots),
                (CAMPUS_KEY, PROJECT_KEY),
            )
            self.assertEqual(
                tuple(row["name"] for row in snapshots),
                (
                    "Core Scientific Dalton 4 Data Center Campus",
                    "Core Scientific Dalton 4 Greenfield Build",
                ),
            )
            for row in snapshots:
                self.assertIsNone(row["latitude"])
                self.assertIsNone(row["longitude"])
                self.assertIsNone(row["geometry_json"])
                self.assertEqual(row["as_of_date"], "2026-04-21")
                self.assertEqual(row["recorded_at"], RECORDED_AT)
                self.assertEqual(row["method"], "authoritative_locality")
                self.assertEqual(row["confidence"], 0.99)
                tags = json.loads(row["tags_json"])
                self.assertEqual(tags["address"], DALTON_4_ADDRESS)
                self.assertEqual(tags["country"], "United States")
                self.assertEqual(tags["role:developer"], "Core Scientific")
                self.assertEqual(tags["role:operator"], "Core Scientific")
                self.assertEqual(tags["source_dataset"], "curated_official_sources")
            campus_tags = json.loads(snapshots[0]["tags_json"])
            project_tags = json.loads(snapshots[1]["tags_json"])
            self.assertEqual(
                {key for key in campus_tags if key.startswith("role:")},
                {"role:developer", "role:operator"},
            )
            self.assertEqual(
                {key for key in project_tags if key.startswith("role:")},
                {"role:developer", "role:operator", "role:tenant"},
            )
            self.assertEqual(project_tags["role:tenant"], "CoreWeave")

    def test_status_type_workload_and_capacity_rows_are_exact(self) -> None:
        temporary, connection, _ = self._import()
        try:
            lifecycle = connection.execute(
                "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                "method, confidence FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(lifecycle),
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-05-06",
                    RECORDED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            operating_model = connection.execute(
                "SELECT entities.stable_key, operating_model, as_of_date, "
                "recorded_at, method, confidence "
                "FROM operating_model_observations JOIN entities "
                "ON entities.id = operating_model_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(operating_model),
                (
                    PROJECT_KEY,
                    "hyperscale_lease",
                    "2026-04-21",
                    RECORDED_AT,
                    "company_disclosure",
                    0.99,
                ),
            )
            workload = connection.execute(
                "SELECT entities.stable_key, workload, as_of_date, recorded_at, "
                "method, confidence FROM workload_observations JOIN entities "
                "ON entities.id = workload_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(workload),
                (
                    PROJECT_KEY,
                    "ai_specialized_unspecified",
                    "2026-04-21",
                    RECORDED_AT,
                    "company_disclosure",
                    0.95,
                ),
            )
            capacities = tuple(
                tuple(row)
                for row in connection.execute(
                    "SELECT entities.stable_key, metric, stage, unit, low, base, "
                    "high, as_of_date, target_date, recorded_at, method, confidence "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY metric"
                )
            )
            self.assertEqual(
                capacities,
                (
                    (
                        PROJECT_KEY,
                        "critical_it_mw",
                        "contracted",
                        "MW",
                        145.0,
                        145.0,
                        145.0,
                        "2026-04-21",
                        None,
                        RECORDED_AT,
                        "reported",
                        0.99,
                    ),
                    (
                        PROJECT_KEY,
                        "grid_connection_mw",
                        "contracted",
                        "MW",
                        220.0,
                        220.0,
                        220.0,
                        "2026-04-21",
                        None,
                        RECORDED_AT,
                        "reported",
                        0.99,
                    ),
                ),
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_source_scope_has_no_inferred_coordinates_energy_or_extra_roles(
        self,
    ) -> None:
        document = self._load()
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        self.assertEqual(document["campus"]["address"], DALTON_4_ADDRESS)
        self.assertEqual(document["project"]["address"], DALTON_4_ADDRESS)
        for entity in (document["campus"], document["project"]):
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
        self.assertEqual(
            document["campus"]["roles"],
            {"developer": ["Core Scientific"], "operator": ["Core Scientific"]},
        )
        self.assertEqual(
            document["project"]["roles"],
            {
                "developer": ["Core Scientific"],
                "operator": ["Core Scientific"],
                "tenant": ["CoreWeave"],
            },
        )
        self.assertEqual(len(document["lifecycle"]), 1)
        self.assertEqual(len(document["operating_models"]), 1)
        self.assertEqual(len(document["workloads"]), 1)
        self.assertEqual(
            document["workloads"][0]["value"], "ai_specialized_unspecified"
        )
        self.assertEqual(
            {
                (row["metric"], row["stage"], row["base"])
                for row in document["capacities"]
            },
            {
                ("critical_it_mw", "contracted", 145),
                ("grid_connection_mw", "contracted", 220),
            },
        )
        self.assertTrue(
            all(row["target_date"] is None for row in document["capacities"])
        )
        april = document["evidence"][0]["metadata"]
        may = document["evidence"][1]["metadata"]
        self.assertEqual(april["reported_building_count"], 1)
        self.assertEqual(april["reported_data_hall_count"], 3)
        self.assertEqual(
            april["address_as_reported"], "3024 Old Tilton Road in Dalton, Georgia"
        )
        self.assertIn("do not create", april["building_scope_guardrail"])
        self.assertIn("No postal code", april["address_scope"])
        self.assertIn("no PUE row", april["pue_energy_guardrail"])
        self.assertIn("not normalized", april["may_update_capacity_guardrail"])
        self.assertEqual(
            may["reported_dalton_aggregate_leased_power_mw_approximate"], 175
        )
        self.assertIn("not assigned to Dalton 4", may["aggregate_capacity_guardrail"])
        self.assertIn("not an actual milestone", may["forecast_guardrail"])

    def test_time_gate_fails_closed_before_any_database_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError,
                    "must not be later than the import recorded_at",
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:40:53Z",
                    )
                for table in ("evidence", "entities", "entity_snapshots"):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                            0
                        ],
                        0,
                    )
            finally:
                connection.close()

    def test_dalton4_is_unseeded_and_distinct_from_dalton1_in_v61_v62(self) -> None:
        for release in RELEASES:
            with self.subTest(release=release.name):
                with (release / "entities.csv").open(
                    newline="", encoding="utf-8"
                ) as handle:
                    entities = {
                        row["stable_key"]: row for row in csv.DictReader(handle)
                    }
                self.assertNotIn(CAMPUS_KEY, entities)
                self.assertNotIn(PROJECT_KEY, entities)
                self.assertIn(DALTON_1_LEGACY_KEY, entities)
                dalton_1 = entities[DALTON_1_LEGACY_KEY]
                self.assertEqual(dalton_1["name"], "CoreWeave Dalton 1 & 2")
                self.assertEqual(dalton_1["address"], DALTON_1_ADDRESS)
                self.assertEqual(dalton_1["status"], "operational")
                self.assertNotEqual(dalton_1["address"], DALTON_4_ADDRESS)

                inputs = json.loads(
                    (release / "source_inputs.json").read_text(encoding="utf-8")
                )["sources"]
                urls = {item["source_url"] for item in inputs}
                keys = {item["provenance"].get("curated_record_key") for item in inputs}
                self.assertTrue(
                    {item["url"] for item in CAPTURES.values()}.isdisjoint(urls)
                )
                self.assertTrue({APRIL_KEY, MAY_KEY}.isdisjoint(keys))


if __name__ == "__main__":
    unittest.main()
