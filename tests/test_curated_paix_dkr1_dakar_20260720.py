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
SOURCE_NAME = "curated-official-2026-07-20-paix-dkr1-dakar.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 18_386
SOURCE_SHA256 = "4abc83e219a463e3a4aa0029063b6708a668a90b80411dbb5795649d08e69ad4"
RETRIEVED_AT = "2026-07-20T22:11:09Z"

CAMPUS_KEY = "curated:paix-dkr1-dakar-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:current-development"
ANNOUNCEMENT_KEY = (
    "paix-dkr1-dakar-announcement-2025-01-27-captured-2026-07-20"
)
LOCATION_KEY = "paix-dkr1-dakar-location-page-captured-2026-07-20"
ADDRESS = (
    "Lots 48 & 49, Mamelles Fougerolles, Route du phare des mamelles, "
    "Ouakam, Dakar, Senegal"
)
LATITUDE = 14.7213975
LONGITUDE = -17.4997482
MAP_LINK = "https://goo.gl/maps/mFQmqMmdgytgyYbq6"
MAP_DESTINATION = (
    "https://www.google.com/maps/place/14%C2%B043'17.0%22N+17%C2%B029'59.1%22W/"
    "@14.7213975,-17.5019369,17z/data=!3m1!4b1!4m5!3m4!1s0x0:"
    "0x283c9da187767096!8m2!3d14.7213975!4d-17.4997482?hl=en-US&coh=164777"
    "&entry=tt&shorturl=1"
)

CAPTURES: dict[str, dict[str, Any]] = {
    ANNOUNCEMENT_KEY: {
        "url": "https://www.paix.io/en/media-centre/250127-paix-dakar-annonce",
        "published_at": "2025-01-27",
        "body_bytes": 13_734,
        "body_sha256": (
            "f7afccfd937496d72fdafa0eba262d779cf8b34558aa673ff5c806a2df6128aa"
        ),
        "header_bytes": 623,
        "header_sha256": (
            "b83efd606f28435cd6d10bc359270464b52df93924b21f03e6bcfc7e14fbec3c"
        ),
        "response_http_date": "2026-07-20T22:11:08Z",
        "document_id": "Z469HREAAB8AGiTS",
        "document_uid": "250127-paix-dakar-annonce",
        "document_type": "media_centre_detail",
        "query_predicate": (
            '[[at(my.media_centre_detail.uid,"250127-paix-dakar-annonce")]]'
        ),
        "first_publication_at": "2025-01-20T21:22:16+00:00",
        "last_publication_at": "2025-06-08T16:38:26+00:00",
    },
    LOCATION_KEY: {
        "url": "https://www.paix.io/en/locations/dakar",
        "published_at": "2023-03-10T12:39:54+00:00",
        "body_bytes": 8_963,
        "body_sha256": (
            "c2250531ebe0d2fcee50a3dbf9cd3bc28c1c6a881d6790d7ed2fa13a3981f0e0"
        ),
        "header_bytes": 622,
        "header_sha256": (
            "d4485f7b3c21f4152cfdec4d76c9070ff922faaec0c2cab30aaf6b13dbebf94c"
        ),
        "response_http_date": RETRIEVED_AT,
        "document_id": "ZArsQhAAACkAXDXj",
        "document_uid": "dakar",
        "document_type": "detail_page",
        "query_predicate": '[[at(my.detail_page.uid,"dakar")]]',
        "first_publication_at": "2023-03-10T12:39:54+00:00",
        "last_publication_at": "2025-03-31T15:29:35+00:00",
    },
}


class PaixDkr1DakarCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("PAIX DKR1 curated import attempted network access")
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
                            result.evidence_created, 2 if iteration == 0 else 0
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
            source_path = temporary_path / SOURCE_NAME
            self._write_document(source_path, document)
            connection, _ = initialize(temporary_path / "atlas.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(ValueError, pattern):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        source_path,
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
        self.assertEqual(len(document["evidence"]), 2)
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

    def test_prismic_response_hashes_and_metadata_are_exact(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["kind"], "company_disclosure")
                self.assertEqual(item["publisher"], "PAIX Data Centres")
                self.assertEqual(item["source_family"], "paix_official_prismic")
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["license"], "all-rights-reserved")
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertEqual(
                    metadata["content_hash_scope"],
                    "SHA-256 of the exact "
                    f"{expected['body_bytes']}-byte official query-specific PAIX "
                    "Prismic API JSON response body",
                )
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
                self.assertEqual(metadata["content_type"], "application/json")
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["body_bytes"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["response_http_date"]
                )
                self.assertEqual(
                    metadata["api_endpoint"],
                    "https://paix.cdn.prismic.io/api/v2/documents/search",
                )
                self.assertEqual(metadata["prismic_master_ref"], "aRG5iBIAACMAN28Z")
                self.assertEqual(metadata["query_predicate"], expected["query_predicate"])
                self.assertEqual(metadata["query_page_size"], 1)
                self.assertEqual(metadata["query_result_count"], 1)
                self.assertEqual(metadata["document_id"], expected["document_id"])
                self.assertEqual(metadata["document_uid"], expected["document_uid"])
                self.assertEqual(metadata["document_type"], expected["document_type"])
                self.assertEqual(metadata["document_language"], "en")
                self.assertEqual(
                    metadata["prismic_first_publication_at"],
                    expected["first_publication_at"],
                )
                self.assertEqual(
                    metadata["prismic_last_publication_at"],
                    expected["last_publication_at"],
                )
                self.assertIn("credential-free curl GET", metadata["retrieval_method"])
                self.assertIn(
                    "No authorization", metadata["request_credentials_guardrail"]
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                self.assertIn(
                    "HTTP 404", metadata["public_route_capture_guardrail"]
                )

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

    def test_coordinates_derive_only_from_the_publisher_map_link(self) -> None:
        document = self._load()
        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }[LOCATION_KEY]
        self.assertEqual(metadata["reported_identity"], "PAIX Dakar, DKR-1")
        self.assertEqual(
            metadata["reported_locality"], "Ouakam and Les Mamelles, Dakar, Senegal"
        )
        self.assertEqual(metadata["reported_address"], ADDRESS.removesuffix(", Senegal"))
        self.assertEqual(metadata["official_map_link"], MAP_LINK)
        self.assertEqual(metadata["map_link_checked_at"], "2026-07-20T22:13:13Z")
        self.assertEqual(metadata["map_link_http_status"], 200)
        self.assertEqual(metadata["map_link_redirect_count"], 1)
        self.assertEqual(metadata["map_link_effective_url"], MAP_DESTINATION)
        self.assertEqual(
            metadata["coordinate_values"],
            {"latitude": LATITUDE, "longitude": LONGITUDE},
        )
        self.assertEqual(
            metadata["coordinate_source_type"],
            "publisher_supplied_map_link_destination",
        )
        self.assertIn("not a parcel boundary", metadata["coordinate_scope"])
        for forbidden_source in (
            "search result",
            "geocoder",
            "OpenStreetMap",
            "satellite image",
            "computer vision",
        ):
            self.assertIn(forbidden_source, metadata["coordinate_guardrail"])

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(
                entity["stable_key"],
                CAMPUS_KEY if entity_name == "campus" else PROJECT_KEY,
            )
            self.assertEqual(entity["country"], "Senegal")
            self.assertEqual(entity["address"], ADDRESS)
            self.assertEqual(entity["roles"], {"developer": ["PAIX Data Centres"]})
            self.assertEqual(
                entity["coordinates"],
                {"latitude": LATITUDE, "longitude": LONGITUDE},
            )
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], LOCATION_KEY)
            self.assertEqual(entity["as_of_date"], "2026-07-20")
            self.assertEqual(entity["method"], "authoritative_site_plan")
            self.assertEqual(entity["confidence"], 0.99)

    def test_site_control_capacity_colocation_and_ambiguities_stay_narrow(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "site_control",
                    "evidence_key": ANNOUNCEMENT_KEY,
                    "as_of_date": "2025-01-27",
                    "method": "authoritative_announcement",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": ANNOUNCEMENT_KEY,
                    "as_of_date": "2025-01-27",
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
        self.assertEqual((capacity["low"], capacity["base"], capacity["high"]), (1.2, 1.2, 1.2))
        self.assertEqual(capacity["method"], "reported")
        self.assertEqual(capacity["evidence_key"], ANNOUNCEMENT_KEY)
        self.assertEqual(capacity["as_of_date"], "2025-01-27")
        self.assertIsNone(capacity["target_date"])
        self.assertIn("not gross demand", capacity["notes"])
        self.assertIn("or annual energy", capacity["notes"])

        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        announcement = metadata[ANNOUNCEMENT_KEY]
        location = metadata[LOCATION_KEY]
        self.assertEqual(announcement["reported_land_status"], (
            "PAIX Data Centres purchased the land to build the buildings that would "
            "house the data-centre equipment."
        ))
        self.assertEqual(announcement["reported_first_phase_operational_forecast"], "2026")
        self.assertIn("only a calendar-year forecast", announcement["forecast_guardrail"])
        self.assertIn("historical site_control", announcement["status_scope"])
        self.assertIn("do not establish groundbreaking", announcement["status_scope"])
        self.assertIn("not a dated current-status", announcement["status_freshness_guardrail"])
        self.assertEqual(announcement["reported_critical_it_design_mw"], 1.2)
        self.assertEqual(announcement["reported_colocation_space_m2_paragraph"], 918)
        self.assertEqual(announcement["reported_colocation_space_m2_list"], 900)
        self.assertEqual(announcement["reported_bays"], 330)
        self.assertEqual(location["reported_critical_it_design_mw"], 1.2)
        self.assertEqual(location["reported_colocation_space_m2"], 918)
        self.assertEqual(location["reported_cabinets"], 300)
        self.assertIn("918 square metres", announcement["specification_discrepancy_guardrail"])
        self.assertIn("900 square metres", announcement["specification_discrepancy_guardrail"])
        self.assertIn("300 cabinets", location["specification_discrepancy_guardrail"])
        self.assertIn("330 bays", location["specification_discrepancy_guardrail"])
        self.assertIn("present-tense", location["status_guardrail"])
        self.assertIn("no dated groundbreaking", location["status_guardrail"])
        self.assertIn("does not advance", location["status_guardrail"])

        for record in (announcement, location):
            self.assertIn("no normalized workload", record["workload_guardrail"] if "workload_guardrail" in record else record["classification_guardrail"])
            self.assertIn("no dated operating state", record["energy_guardrail"])
            self.assertIn("internal parent container", record["entity_model_guardrail"])
            self.assertIn("not", record["entity_model_guardrail"])
        self.assertIn("not a second data centre", announcement["entity_model_guardrail"])
        self.assertIn("must not be counted with its child", location["entity_model_guardrail"])

    def test_stable_and_evidence_keys_do_not_collide(self) -> None:
        claimed_stable = {CAMPUS_KEY, PROJECT_KEY}
        claimed_evidence = set(CAPTURES)
        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE_PATH:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            stable_keys = {
                entity["stable_key"]
                for entity in (document.get("campus"), document.get("project"))
                if isinstance(entity, dict) and "stable_key" in entity
            }
            evidence_keys = {
                item["key"]
                for item in document.get("evidence", [])
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
                    expected["body_sha256"],
                    RETRIEVED_AT,
                    expected["url"],
                )
                for key, expected in CAPTURES.items()
            ),
        )
        self.assertEqual(len(snapshots), 2)
        expected_tags = {
            "address": ADDRESS,
            "country": "Senegal",
            "role:developer": "PAIX Data Centres",
            "source_dataset": "curated_official_sources",
        }
        for row in snapshots:
            self.assertEqual(json.loads(row[2]), expected_tags)
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
                    "site_control",
                    "2025-01-27",
                    RETRIEVED_AT,
                    "authoritative_announcement",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(len(capacities), 1)
        self.assertEqual(capacities[0][0:7], (PROJECT_KEY, "critical_it_mw", "planned", "MW", 1.2, 1.2, 1.2))
        self.assertEqual(capacities[0][7:12], ("2025-01-27", None, RETRIEVED_AT, "reported", 0.99))
        self.assertIn("or annual energy", capacities[0][12])
        self.assertEqual(
            operating_models,
            (
                (
                    PROJECT_KEY,
                    "colocation",
                    "2025-01-27",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(workloads, ())

    def test_semantic_mutations_cannot_invent_construction_energy_or_location(self) -> None:
        construction = copy.deepcopy(self._load())
        construction["lifecycle"][0]["value"] = "under_construction"
        self._assert_document_rejected(
            construction,
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
        ungrounded_location["campus"]["coordinates"] = None
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
        assert first.evidence_created == 2
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
                            "evidence": 2,
                            "lifecycle": 1,
                            "operating_models": 1,
                            "snapshots": 2,
                            "workloads": 0,
                        },
                        "values": {
                            "capacity": "critical_it_mw:planned:1.2",
                            "lifecycle": "site_control",
                            "operating_model": "colocation",
                        },
                    },
                )


if __name__ == "__main__":
    unittest.main()
