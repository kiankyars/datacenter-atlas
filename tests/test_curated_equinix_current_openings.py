from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T03:44:34Z"

HK6_SOURCE = "curated-official-2026-07-20-equinix-hk6-current-opening.json"
MD5_SOURCE = "curated-official-2026-07-20-equinix-md5-current-opening.json"
MB3_SOURCE = "curated-official-2026-07-20-equinix-mb3-current-opening.json"
CURRENT_SOURCES = (HK6_SOURCE, MD5_SOURCE, MB3_SOURCE)

HISTORICAL_SOURCES = (
    "curated-official-2026-07-20-equinix-hk6-hong-kong-phase-1.json",
    "curated-official-2026-07-20-equinix-md5-madrid-phase-1.json",
    "curated-official-2026-07-20-equinix-mb3-mumbai-phase-2.json",
)

HK6_CAMPUS = "curated:equinix-hk6-hong-kong-data-center"
HK6_PROJECT = f"{HK6_CAMPUS}:phase-1"
MD5_CAMPUS = "curated:equinix-md5-madrid-data-center"
MD5_PROJECT = f"{MD5_CAMPUS}:phase-1"
MB3_CAMPUS = "curated:equinix-mb3-mumbai-data-center"
MB3_PROJECT = f"{MB3_CAMPUS}:phase-2"

SPECS: dict[str, dict[str, Any]] = {
    HK6_SOURCE: {
        "source_sha256": "8b84a0d95e5000372a72ddbd398334579a16e24cb47030470a383fd3a3d5cf7e",
        "evidence_key": "equinix-hk6-opening-2026-06-16-captured-2026-07-20",
        "body_sha256": "b4665c2a53b92445914f445c58fae6564cd2d305d085d09b7565aa378038c0f2",
        "body_bytes": 126739,
        "header_sha256": "b3d9934f16941d550143320566ad37d4785f65b8eb092347b5563fadd55e8473",
        "header_bytes": 711,
        "transfer_bytes": 24579,
        "last_modified": "2026-07-20T03:44:34Z",
        "published_at": "2026-06-16",
        "campus_key": HK6_CAMPUS,
        "project_key": HK6_PROJECT,
        "country": "Hong Kong",
        "address": "Tsuen Wan, Hong Kong",
        "lifecycle_entities": ("campus", "project"),
    },
    MD5_SOURCE: {
        "source_sha256": "8a8e6fac2a32c76e58eb82abd156e324d85a90134a6c421e834ed15b4f6ad5e7",
        "evidence_key": "equinix-md5-opening-2026-05-22-captured-2026-07-20",
        "body_sha256": "616da96e30cc58b50cea89fdf668aa1ce017202a27889db6bf93d2e4d542de0b",
        "body_bytes": 96197,
        "header_sha256": "4fca29ae6857238c0c6bf7f1fd20298f0e60d345a11572df5be2432c7fef666b",
        "header_bytes": 721,
        "transfer_bytes": 17756,
        "last_modified": "2026-07-20T03:28:44Z",
        "published_at": "2026-05-22",
        "campus_key": MD5_CAMPUS,
        "project_key": None,
        "country": "Spain",
        "address": "Alcobendas, Madrid, Spain",
        "lifecycle_entities": ("campus",),
    },
    MB3_SOURCE: {
        "source_sha256": "1205465f933d70b4d6af453000782c2d7b2ce2bf1384137aa82dfeee8ccc41ed",
        "evidence_key": "equinix-mb3-opening-2026-04-08-captured-2026-07-20",
        "body_sha256": "4110fc79198bc6b79acb955c22e06d77e08a785c316453423ffa7f7822e3c269",
        "body_bytes": 127406,
        "header_sha256": "7cba90529a7b5bdec0ab9a494df82305286a1f4ee33345a158174c0dc1b7dd62",
        "header_bytes": 711,
        "transfer_bytes": 24746,
        "last_modified": "2026-07-20T03:44:34Z",
        "published_at": "2026-04-08",
        "campus_key": MB3_CAMPUS,
        "project_key": None,
        "country": "India",
        "address": "Chandivali, Powai, Mumbai, India",
        "lifecycle_entities": ("campus",),
    },
}


class EquinixCurrentOpeningsTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _database_state(
        self,
        current_order: tuple[str, ...],
        *,
        current_repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for name in HISTORICAL_SOURCES:
                        document = self._load(name)
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )
                    for _ in range(current_repetitions):
                        for name in current_order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                ROOT / "sources" / name,
                                retrieved_at=RETRIEVED_AT,
                            )

                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "source_family, source_url, content_hash FROM evidence "
                    "ORDER BY source_url",
                    "SELECT entities.stable_key, status, lifecycle_observations.as_of_date, "
                    "lifecycle_observations.method FROM lifecycle_observations "
                    "JOIN entities ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, lifecycle_observations.as_of_date",
                    "SELECT entities.stable_key, entity_snapshots.as_of_date, "
                    "entity_snapshots.latitude, entity_snapshots.longitude, "
                    "entity_snapshots.geometry_json, entity_snapshots.tags_json "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, entity_snapshots.as_of_date",
                    "SELECT entity_id, metric, stage FROM capacity_estimates",
                    "SELECT entity_id, operating_model FROM operating_model_observations",
                    "SELECT entity_id, workload FROM workload_observations",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_exact_sources_and_fresh_official_capture_provenance(self) -> None:
        for name, expected in SPECS.items():
            with self.subTest(source=name):
                path = ROOT / "sources" / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["source_sha256"],
                )
                document = self._load(name)
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
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(len(document["evidence"]), 1)
                evidence = document["evidence"][0]
                self.assertEqual(evidence["key"], expected["evidence_key"])
                self.assertEqual(evidence["kind"], "company_disclosure")
                self.assertEqual(evidence["publisher"], "Equinix")
                self.assertEqual(evidence["source_family"], "equinix_newsroom")
                self.assertEqual(evidence["published_at"], expected["published_at"])
                self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(evidence["content_hash"], expected["body_sha256"])
                self.assertTrue(
                    evidence["source_url"].startswith("https://newsroom.equinix.com/")
                )

                metadata = evidence["metadata"]
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f'{expected["body_bytes"]}-byte', metadata["content_hash_scope"]
                )
                self.assertIn(
                    f'{expected["header_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_content_length_bytes_as_received"])
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["transfer_bytes"],
                )
                self.assertEqual(metadata["request_started_at"], RETRIEVED_AT)
                self.assertEqual(metadata["request_finished_at"], RETRIEVED_AT)
                self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["response_set_cookie_header_count"], 1)
                self.assertEqual(metadata["requested_url"], evidence["source_url"])
                self.assertEqual(metadata["effective_url"], evidence["source_url"])
                self.assertEqual(metadata["canonical_url"], evidence["source_url"])
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["http_version"], "2")
                self.assertIn("not redistributed", metadata["rights_scope"])
                self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

                campus = document["campus"]
                self.assertEqual(campus["stable_key"], expected["campus_key"])
                self.assertEqual(campus["country"], expected["country"])
                self.assertEqual(campus["address"], expected["address"])
                self.assertEqual(campus["roles"], {})
                self.assertIsNone(campus["coordinates"])
                self.assertIsNone(campus["geometry"])
                self.assertEqual(campus["method"], "authoritative_locality")
                self.assertEqual(campus["as_of_date"], expected["published_at"])

                if expected["project_key"] is None:
                    self.assertIsNone(document["project"])
                else:
                    project = document["project"]
                    self.assertEqual(project["stable_key"], expected["project_key"])
                    self.assertEqual(project["country"], expected["country"])
                    self.assertEqual(project["address"], expected["address"])
                    self.assertEqual(project["roles"], {})
                    self.assertIsNone(project["coordinates"])
                    self.assertIsNone(project["geometry"])
                    self.assertEqual(project["method"], "authoritative_locality")

                self.assertEqual(
                    tuple(row["entity"] for row in document["lifecycle"]),
                    expected["lifecycle_entities"],
                )
                for lifecycle in document["lifecycle"]:
                    self.assertEqual(lifecycle["value"], "operational")
                    self.assertEqual(lifecycle["as_of_date"], expected["published_at"])
                    self.assertEqual(lifecycle["method"], "authoritative_status_update")
                    self.assertEqual(lifecycle["confidence"], 0.99)
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                self.assertEqual(document["capacities"], [])

    def test_scope_guardrails_keep_phase_and_energy_claims_separate(self) -> None:
        hk6 = self._load(HK6_SOURCE)
        hk6_metadata = hk6["evidence"][0]["metadata"]
        self.assertEqual(hk6_metadata["first_phase_cabinets_as_reported"], 1000)
        self.assertEqual(hk6_metadata["full_buildout_cabinets_as_reported"], 3550)
        self.assertEqual(
            hk6_metadata["initial_investment_usd_millions_as_reported"], 124
        )
        self.assertIn("campus operational", hk6_metadata["status_scope"])
        self.assertIn("phase-1 project operational", hk6_metadata["status_scope"])
        self.assertIn("unnamed future phases", hk6_metadata["future_buildout_guardrail"])

        md5 = self._load(MD5_SOURCE)
        md5_metadata = md5["evidence"][0]["metadata"]
        self.assertIsNone(md5["project"])
        self.assertNotIn(MD5_PROJECT, (ROOT / "sources" / MD5_SOURCE).read_text())
        self.assertIn("creates no current lifecycle observation", md5_metadata["phase_identity_guardrail"])
        self.assertEqual(
            md5_metadata["alcobendas_campus_investment_eur_millions_as_reported"],
            460,
        )
        self.assertEqual(
            md5_metadata["md5_colocation_floor_area_square_metres_as_reported_minimum"],
            4400,
        )
        self.assertIn("neither MW nor energy", md5_metadata["floor_area_guardrail"])

        mb3 = self._load(MB3_SOURCE)
        mb3_metadata = mb3["evidence"][0]["metadata"]
        self.assertIsNone(mb3["project"])
        self.assertNotIn(MB3_PROJECT, (ROOT / "sources" / MB3_SOURCE).read_text())
        self.assertIn("creates no current lifecycle observation", mb3_metadata["phase_identity_guardrail"])
        self.assertEqual(mb3_metadata["initial_cabinets_as_reported_minimum"], 1370)
        self.assertEqual(mb3_metadata["full_buildout_cabinets_as_reported_minimum"], 5475)
        self.assertEqual(
            mb3_metadata["group_captive_solar_nameplate_mwp_as_reported"], 26.4
        )
        self.assertEqual(
            mb3_metadata["group_captive_solar_expected_annual_generation_kwh_as_reported"],
            41_400_000,
        )
        self.assertIn("not MB3 critical IT load", mb3_metadata["energy_guardrail"])
        self.assertIn("annual facility consumption", mb3_metadata["energy_guardrail"])
        self.assertIn("evidence metadata only", mb3_metadata["energy_guardrail"])

    def test_historical_then_current_import_is_idempotent_and_order_independent(self) -> None:
        forward = self._database_state(CURRENT_SOURCES)
        reverse = self._database_state(tuple(reversed(CURRENT_SOURCES)))
        repeated = self._database_state(CURRENT_SOURCES, current_repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        self.assertEqual(
            forward[0],
            (
                ("campus", HK6_CAMPUS),
                ("campus", MB3_CAMPUS),
                ("campus", MD5_CAMPUS),
                ("project", HK6_PROJECT),
                ("project", MB3_PROJECT),
                ("project", MD5_PROJECT),
            ),
        )
        self.assertEqual(len(forward[1]), 4)
        self.assertEqual(
            {row[3] for row in forward[1]},
            {
                "2fdbe45af04ff1513a1dba3851cf3ed4d181edbf2561e193176e728a3437760c",
                *(spec["body_sha256"] for spec in SPECS.values()),
            },
        )
        self.assertEqual(len(forward[2]), 7)
        self.assertEqual(len(forward[3]), 10)
        self.assertEqual(forward[4], ())
        self.assertEqual(forward[5], ())
        self.assertEqual(forward[6], ())
        for snapshot in forward[3]:
            self.assertIsNone(snapshot[2])
            self.assertIsNone(snapshot[3])
            self.assertIsNone(snapshot[4])
            self.assertFalse(
                any(key.startswith("role:") for key in json.loads(snapshot[5]))
            )

    def test_latest_status_and_snapshot_preserve_zero_md5_mb3_project_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for name in HISTORICAL_SOURCES:
                        document = self._load(name)
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )
                    for name in CURRENT_SOURCES:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=RETRIEVED_AT,
                        )

                latest_lifecycle = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        WITH ranked AS (
                            SELECT entity_id, status, as_of_date, method,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY entity_id
                                       ORDER BY as_of_date DESC, recorded_at DESC, id DESC
                                   ) AS temporal_rank
                            FROM lifecycle_observations
                            WHERE as_of_date <= '2026-07-20'
                              AND recorded_at <= '2026-07-20T23:59:59Z'
                              AND (superseded_at IS NULL
                                   OR '2026-07-20T23:59:59Z' < superseded_at)
                        )
                        SELECT entities.stable_key, ranked.status,
                               ranked.as_of_date, ranked.method
                        FROM ranked
                        JOIN entities ON entities.id = ranked.entity_id
                        WHERE ranked.temporal_rank = 1
                        ORDER BY entities.stable_key
                        """
                    )
                ]
                self.assertEqual(
                    latest_lifecycle,
                    [
                        (
                            HK6_CAMPUS,
                            "operational",
                            "2026-06-16",
                            "authoritative_status_update",
                        ),
                        (
                            HK6_PROJECT,
                            "operational",
                            "2026-06-16",
                            "authoritative_status_update",
                        ),
                        (
                            MB3_CAMPUS,
                            "operational",
                            "2026-04-08",
                            "authoritative_status_update",
                        ),
                        (
                            MB3_PROJECT,
                            "under_construction",
                            "2025-12-31",
                            "authoritative_physical_status_update",
                        ),
                        (
                            MD5_CAMPUS,
                            "operational",
                            "2026-05-22",
                            "authoritative_status_update",
                        ),
                        (
                            MD5_PROJECT,
                            "under_construction",
                            "2025-12-31",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )

                latest_snapshots = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        WITH ranked AS (
                            SELECT entity_id, as_of_date, tags_json,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY entity_id
                                       ORDER BY as_of_date DESC, recorded_at DESC, id DESC
                                   ) AS temporal_rank
                            FROM entity_snapshots
                            WHERE as_of_date <= '2026-07-20'
                              AND recorded_at <= '2026-07-20T23:59:59Z'
                              AND (superseded_at IS NULL
                                   OR '2026-07-20T23:59:59Z' < superseded_at)
                        )
                        SELECT entities.stable_key, ranked.as_of_date,
                               json_extract(ranked.tags_json, '$.address')
                        FROM ranked
                        JOIN entities ON entities.id = ranked.entity_id
                        WHERE ranked.temporal_rank = 1
                        ORDER BY entities.stable_key
                        """
                    )
                ]
                self.assertEqual(
                    latest_snapshots,
                    [
                        (HK6_CAMPUS, "2026-06-16", "Tsuen Wan, Hong Kong"),
                        (HK6_PROJECT, "2026-06-16", "Tsuen Wan, Hong Kong"),
                        (MB3_CAMPUS, "2026-04-08", "Chandivali, Powai, Mumbai, India"),
                        (MB3_PROJECT, "2025-12-31", "Mumbai, India"),
                        (MD5_CAMPUS, "2026-05-22", "Alcobendas, Madrid, Spain"),
                        (MD5_PROJECT, "2025-12-31", "Madrid, Spain"),
                    ],
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
