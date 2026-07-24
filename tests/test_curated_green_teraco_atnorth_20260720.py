from __future__ import annotations

import copy
import csv
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v32.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v32"
BASE_DEFINITION_SHA256 = (
    "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
)
BASE_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)

GREEN_SOURCE = "curated-official-2026-07-20-green-mountain-undheim.json"
TERACO_SOURCE = "curated-official-2026-07-20-teraco-jb7-isando.json"
SWE02_SOURCE = "curated-official-2026-07-20-atnorth-swe02-stockholm.json"
FIN04_SOURCE = "curated-official-2026-07-20-atnorth-fin04-kouvola.json"
SOURCE_ORDER = (GREEN_SOURCE, TERACO_SOURCE, SWE02_SOURCE, FIN04_SOURCE)

SOURCES: dict[str, dict[str, Any]] = {
    GREEN_SOURCE: {
        "sha256": "98ebd4adc98dae26061b64445f6e1f33c8ed92ffeed30b99c163ff42ad03f5f0",
        "retrieved_at": "2026-07-20T00:02:48Z",
        "evidence_count": 1,
        "campus_key": "curated:green-mountain-undheim-campus",
        "project_key": (
            "curated:green-mountain-undheim-campus:"
            "current-two-building-development"
        ),
        "country": "Norway",
        "address": "Undheim, Time, Rogaland, Norway",
        "roles": {"developer": ["Green Mountain"]},
        "lifecycle_date": "2026-07-20",
        "lifecycle_method": "authoritative_physical_status_update",
        "models": [],
        "capacities": [
            ("critical_it_mw", "planned", "MW", 80.0, 80.0, 80.0),
            ("gross_facility_mw", "planned", "MW", 100.0, 100.0, 100.0),
        ],
    },
    TERACO_SOURCE: {
        "sha256": "d76b0a162d7894e0738a39feb4505a5460e28b86cc2f7daa4deb9f9e00cf7092",
        "retrieved_at": "2026-07-20T00:02:53Z",
        "evidence_count": 1,
        "campus_key": "curated:teraco-isando-campus",
        "project_key": "curated:teraco-isando-campus:jb7",
        "country": "South Africa",
        "address": "Isando, Ekurhuleni, South Africa",
        "roles": {"operator": ["Teraco"]},
        "lifecycle_date": "2024-11-13",
        "lifecycle_method": "authoritative_construction_start",
        "models": ["colocation"],
        "capacities": [
            ("critical_it_mw", "planned", "MW", 40.0, 40.0, 40.0),
        ],
    },
    SWE02_SOURCE: {
        "sha256": "c69edf4c7c7b7f705ce3489f3ee1f112fab2032c0483a3a1b4ace77d84283169",
        "retrieved_at": "2026-07-20T00:02:55Z",
        "evidence_count": 2,
        "campus_key": "curated:atnorth-swe02-stockholm-campus",
        "project_key": (
            "curated:atnorth-swe02-stockholm-campus:current-development"
        ),
        "country": "Sweden",
        "address": "Kista, Stockholm, Sweden",
        "roles": {"developer": ["atNorth"]},
        "lifecycle_date": "2026-06-09",
        "lifecycle_method": "authoritative_physical_status_update",
        "models": [],
        "capacities": [],
    },
    FIN04_SOURCE: {
        "sha256": "28773caea4d839386074e6bd3003953c75c9f1bbd3441442a83cfc2d9ca22fe4",
        "retrieved_at": "2026-07-20T00:04:32Z",
        "evidence_count": 3,
        "campus_key": "curated:atnorth-fin04-kouvola-campus",
        "project_key": "curated:atnorth-fin04-kouvola-campus:phase-1",
        "country": "Finland",
        "address": "Ummeljoki-Myllykoski, Kouvola, Finland",
        "roles": {"developer": ["atNorth"]},
        "lifecycle_date": "2026-07-20",
        "lifecycle_method": "authoritative_physical_status_update",
        "models": [],
        "capacities": [],
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "green-mountain-undheim-live-project-page-captured-2026-07-20": {
        "source": GREEN_SOURCE,
        "kind": "company_disclosure",
        "publisher": "Green Mountain",
        "source_family": "green_mountain_project_pages",
        "published_at": "2020-12-11T12:48:00Z",
        "body_bytes": 131986,
        "content_hash": "43ffdfa6c4b1c83c367e27aa282e0e307026a1a0d2419da7e54453626f1ed26c",
        "headers_bytes": 1770,
        "headers_hash": "b77133c7af5c6be1d9e4bd47a59344ef5260b788356bfd766bcb61d8c7f6f616",
        "writeout_bytes": 9566,
        "writeout_hash": "d36d7c6023cf7ec9ba07c2c3b47c2fa5afb9101b61ba80d7390e59bc3ccb75ec",
        "download_bytes": 30970,
        "response_date": "2026-07-20T00:02:48Z",
        "url": "https://info.greenmountain.no/datasenter-pa-undheim/",
    },
    "teraco-jb7-construction-commencement-2024-11-13-captured-2026-07-20": {
        "source": TERACO_SOURCE,
        "kind": "company_disclosure",
        "publisher": "Teraco",
        "source_family": "teraco_newsroom",
        "published_at": "2024-11-13T07:00:58Z",
        "body_bytes": 154056,
        "content_hash": "6b130a2697cff5d136535a41be26c4f63c1192909d21ca09a5807e71bce607a4",
        "headers_bytes": 1002,
        "headers_hash": "3c104640f3904222d7172d66332d1916f9e7410d3ff2bf01e62a617aa371c750",
        "writeout_bytes": 17309,
        "writeout_hash": "f6fa5576cf9205db809f4305f45f5a31a9d182f7a1951f56812dc2047fdd5d51",
        "download_bytes": 36043,
        "response_date": "2026-07-20T00:02:53Z",
        "url": (
            "https://www.teraco.co.za/news/"
            "teraco-announces-jb7-and-a-new-r8-billion-syndicated-loan/"
        ),
    },
    "atnorth-swe02-current-construction-2026-06-09-captured-2026-07-20": {
        "source": SWE02_SOURCE,
        "kind": "company_disclosure",
        "publisher": "atNorth",
        "source_family": "atnorth_newsroom",
        "published_at": "2026-06-09T07:00:00Z",
        "body_bytes": 90439,
        "content_hash": "2b7995a34c638735c41705c077f6c6adbc00af1154ef8890f3b58f0a26df743c",
        "headers_bytes": 1767,
        "headers_hash": "db9e06dd0fbb9f3fde8eef53cbf6563a39d1d2486ef4b6f63de201160a254c83",
        "writeout_bytes": 9601,
        "writeout_hash": "0be25e4300f676d87030154b3e580d7ab9e032a5d47a32258659f08e37ad6241",
        "download_bytes": 21107,
        "response_date": "2026-07-20T00:02:54Z",
        "url": (
            "https://www.atnorth.com/news/"
            "atnorth-joins-norwegian-data-center-association/"
        ),
    },
    "atnorth-swe02-project-announcement-2026-01-29-captured-2026-07-20": {
        "source": SWE02_SOURCE,
        "kind": "company_disclosure",
        "publisher": "atNorth",
        "source_family": "atnorth_newsroom",
        "published_at": "2026-01-29T09:00:00Z",
        "body_bytes": 98706,
        "content_hash": "fe78d9e79cf8afe02db9cbd5fe225b9d3d9ebd93ca484c692a4ae8941ff75e04",
        "headers_bytes": 1777,
        "headers_hash": "f35c46a2d02f9d1b4c58e3dfd9cccd59656feb0883379b1ac76895811a40715c",
        "writeout_bytes": 9598,
        "writeout_hash": "2ae820fd3c49599efeb78d001368042b0ecbc15f819064440e44bd0a45eb803d",
        "download_bytes": 22976,
        "response_date": "2026-07-20T00:02:55Z",
        "url": (
            "https://www.atnorth.com/news/"
            "new-30mw-metro-data-center-in-stockholm-sweden/"
        ),
    },
    "atnorth-fin04-current-construction-2026-03-26-captured-2026-07-20": {
        "source": FIN04_SOURCE,
        "kind": "company_disclosure",
        "publisher": "atNorth",
        "source_family": "atnorth_newsroom",
        "published_at": "2026-03-26T09:00:00Z",
        "body_bytes": 89799,
        "content_hash": "7d503232b148c6069a4cd2a3f92be6b50b2dd43bb99fa7c370f77a3feb8eba6b",
        "headers_bytes": 1773,
        "headers_hash": "9cee521ee8027f57ea788640ca99a2403635d315fd592fb7e2b326e7163b2d04",
        "writeout_bytes": 9941,
        "writeout_hash": "a76822d5963bb6ea7bc39ab8cf5c43c09f51530e43e13c2fee83fc205c2a9dfd",
        "download_bytes": 20812,
        "response_date": "2026-07-20T00:04:32Z",
        "url": (
            "https://www.atnorth.com/news/atnorth-joins-the-european-data-"
            "center-association-to-further-support-its-commitment-to-"
            "sustainable-sovereign-digital-infrastructure/"
        ),
    },
    "kouvola-fin04-active-construction-2025-10-02-captured-2026-07-20": {
        "source": FIN04_SOURCE,
        "kind": "government_record",
        "publisher": "City of Kouvola",
        "source_family": "kouvola_city_news",
        "published_at": "2025-10-02T07:18:43Z",
        "body_bytes": 64549,
        "content_hash": "134e4704fe1e193077c73dfa938660c4e6ff422052d9e883ca9f5c4b2c877a9f",
        "headers_bytes": 991,
        "headers_hash": "b96279f73d80eb754b92c9b4496571df07347a425b9fbfbc6d00ebc62b583e67",
        "writeout_bytes": 16499,
        "writeout_hash": "a07200a487f95a66531c65f0fa23758016f1c3821508a163fe1dc14ec91749a0",
        "download_bytes": 16108,
        "response_date": "2026-07-20T00:02:56Z",
        "url": (
            "https://www.kouvola.fi/ajankohtaiset/atnorth-tuli-jaadakseen-"
            "datakeskusyhtio-kertoo-kuulumisistaan-kouvolassa-15-10/"
        ),
    },
    "atnorth-fin04-project-announcement-2023-12-07-captured-2026-07-20": {
        "source": FIN04_SOURCE,
        "kind": "company_disclosure",
        "publisher": "atNorth",
        "source_family": "atnorth_newsroom",
        "published_at": "2023-12-07T00:00:00Z",
        "body_bytes": 88444,
        "content_hash": "0149380e87955775c8cbd6df91e795c45fc45a1b60cce9632afb941bac4a2efc",
        "headers_bytes": 1712,
        "headers_hash": "f7456397701da19d61270e962a62bb33722f67dede37f474e9c1f85d5b7a62d2",
        "writeout_bytes": 9643,
        "writeout_hash": "40736d032f1124ecbea20fa3dcae0e9515a10ac4f1f20a2a4b389cb9323ffe4b",
        "download_bytes": 21106,
        "response_date": "2026-07-20T00:02:56Z",
        "url": (
            "https://www.atnorth.com/news/"
            "atnorth-announces-heat-reuse-enabled-mega-site-in-kouvola/"
        ),
    },
}

SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class GreenTeracoAtNorthOfficialTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _offline(self) -> tuple[Any, ...]:
        error = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

    def _import(self, connection: Any, name: str) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            ROOT / "sources" / name,
            retrieved_at=SOURCES[name]["retrieved_at"],
        )

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(self, order: Iterable[str]) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            patches = self._offline()
            try:
                for network_patch in patches:
                    network_patch.start()
                for name in order:
                    expected = SOURCES[name]
                    result = self._import(connection, name)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                first_state = self._state(connection)
                for name in SOURCE_ORDER:
                    result = self._import(connection, name)
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)
                self.assertEqual(self._state(connection), first_state)
                self.assertEqual(validate_database(connection), [])
                return first_state
            finally:
                for network_patch in reversed(patches):
                    network_patch.stop()
                connection.close()

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        expected = CAPTURES[evidence["key"]]
        source = SOURCES[expected["source"]]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["kind"], expected["kind"])
        self.assertEqual(evidence["publisher"], expected["publisher"])
        self.assertEqual(evidence["source_family"], expected["source_family"])
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
        self.assertEqual(evidence["content_hash"], expected["content_hash"])
        self.assertEqual(evidence["source_url"], expected["url"])
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(expected["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(
            str(expected["headers_bytes"]), metadata["capture_headers_scope"]
        )
        self.assertEqual(metadata["capture_headers_sha256"], expected["headers_hash"])
        self.assertIn(
            str(expected["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], expected["writeout_hash"]
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            expected["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], expected["response_date"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], expected["url"])
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("satellite imagery", metadata["imagery_guardrail"])
        self.assertIn("computer vision", metadata["imagery_guardrail"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
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
        self.assertEqual(len(document["evidence"]), expected["evidence_count"])
        self.assertEqual(
            {row["key"] for row in document["evidence"]},
            {
                key
                for key, capture in CAPTURES.items()
                if capture["source"] == name
            },
        )
        for evidence in document["evidence"]:
            self._assert_capture(evidence)
        for kind in ("campus", "project"):
            entity = document[kind]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], expected["roles"])
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": document["lifecycle"][0]["evidence_key"],
                    "as_of_date": expected["lifecycle_date"],
                    "method": expected["lifecycle_method"],
                    "confidence": 0.99,
                }
            ],
        )
        evidence_keys = {row["key"] for row in document["evidence"]}
        self.assertIn(document["lifecycle"][0]["evidence_key"], evidence_keys)
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            len(document["operating_models"]), len(expected["models"])
        )
        self.assertEqual(
            [row["value"] for row in document["operating_models"]],
            expected["models"],
        )
        self.assertEqual(
            len(document["capacities"]), len(expected["capacities"])
        )
        capacities = [
            (
                row["metric"],
                row["stage"],
                row["unit"],
                float(row["low"]),
                float(row["base"]),
                float(row["high"]),
            )
            for row in document["capacities"]
        ]
        self.assertEqual(capacities, expected["capacities"])
        for row in document["capacities"]:
            self.assertEqual(row["entity"], "project")
            self.assertEqual(row["method"], "reported")
            self.assertIn("not", row["notes"].lower())
            self.assertNotEqual(row["metric"], "generation_nameplate_mw")
            self.assertNotEqual(row["metric"], "annual_energy_mwh")
            self.assertNotEqual(row["metric"], "pue")

        evidence = {row["key"]: row for row in document["evidence"]}
        if name == GREEN_SOURCE:
            metadata = next(iter(evidence.values()))["metadata"]
            self.assertEqual(metadata["planned_it_capacity_mw"], 80)
            self.assertEqual(metadata["planned_total_effect_capacity_mw"], 100)
            self.assertIn("not additive", metadata["capacity_scope"])
            self.assertIn("generic project", metadata["status_scope"])
        elif name == TERACO_SOURCE:
            metadata = next(iter(evidence.values()))["metadata"]
            self.assertEqual(metadata["planned_critical_power_mw"], 40)
            self.assertEqual(metadata["planned_utility_supply_mva"], 68)
            self.assertIn("MVA is not MW", metadata["capacity_scope"])
            self.assertIn("does not establish current 2026 status", metadata["status_scope"])
            self.assertIn("not eligible for a current-construction release", metadata["release_guardrail"])
            self.assertIn("not attributed to JB7", metadata["release_guardrail"])
            self.assertIn("colocation", metadata["operating_model_scope"])
        elif name == SWE02_SOURCE:
            project = next(
                row for row in evidence.values() if "project-announcement" in row["key"]
            )["metadata"]
            self.assertEqual(project["reported_site_scale_mw_as_untyped"], 30)
            self.assertIn("remains untyped metadata", project["power_metric_guardrail"])
            self.assertIn("Kista", project["locality_guardrail"])
            self.assertNotIn("Akalla", project["locality_guardrail"])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["operating_models"], [])
        else:
            city = next(
                row for row in evidence.values() if row["kind"] == "government_record"
            )["metadata"]
            project = next(
                row for row in evidence.values() if "project-announcement" in row["key"]
            )["metadata"]
            self.assertEqual(city["first_phase_capacity_mw_as_reported"], 60)
            self.assertEqual(project["reported_first_phase_power_supply_mw"], 60)
            self.assertIn("remains untyped metadata", city["power_metric_guardrail"])
            self.assertIn("remains untyped metadata", project["power_metric_guardrail"])
            self.assertIn("future phases are not created", city["phase_scope"])
            current = next(
                row for row in evidence.values() if "current-construction" in row["key"]
            )["metadata"]
            self.assertIn("as of capture", current["status_scope"])
            self.assertIn("without inferring", current["status_scope"])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["operating_models"], [])

    def test_exact_hashes_capture_contract_and_v32_collision_absence(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            baseline_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            baseline_hashes = {row["content_hash"] for row in csv.DictReader(stream)}
        new_keys: set[str] = set()
        new_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            document = self._load(name)
            self._assert_document(name, document)
            new_keys.update((expected["campus_key"], expected["project_key"]))
            new_hashes.update(row["content_hash"] for row in document["evidence"])
        self.assertEqual(len(new_keys), 8)
        self.assertEqual(len(new_hashes), 7)
        self.assertTrue(new_keys.isdisjoint(baseline_keys))
        self.assertTrue(new_hashes.isdisjoint(baseline_hashes))

    def test_offline_order_independence_idempotence_and_integrity(self) -> None:
        forward = self._build(SOURCE_ORDER)
        reverse = self._build(reversed(SOURCE_ORDER))
        self.assertEqual(forward, reverse)
        self.assertEqual(
            {table: len(rows) for table, rows in forward.items()},
            {
                "evidence": 7,
                "entities": 8,
                "campuses": 4,
                "facilities": 0,
                "buildings": 0,
                "projects": 4,
                "administrative_assignments": 0,
                "entity_snapshots": 8,
                "lifecycle_observations": 4,
                "operating_model_observations": 1,
                "workload_observations": 0,
                "capacity_estimates": 3,
            },
        )

    def test_combined_rows_preserve_status_capacity_and_classification_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            patches = self._offline()
            try:
                for network_patch in patches:
                    network_patch.start()
                for name in SOURCE_ORDER:
                    self._import(connection, name)
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    sorted(
                        (
                            expected["project_key"],
                            "under_construction",
                            expected["lifecycle_date"],
                            expected["lifecycle_method"],
                        )
                        for expected in SOURCES.values()
                    ),
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT metric, stage, unit, low, base, high "
                            "FROM capacity_estimates ORDER BY metric, base"
                        )
                    ],
                    [
                        ("critical_it_mw", "planned", "MW", 40.0, 40.0, 40.0),
                        ("critical_it_mw", "planned", "MW", 80.0, 80.0, 80.0),
                        ("gross_facility_mw", "planned", "MW", 100.0, 100.0, 100.0),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT operating_model, COUNT(*) "
                            "FROM operating_model_observations "
                            "GROUP BY operating_model ORDER BY operating_model"
                        )
                    ],
                    [("colocation", 1)],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                for network_patch in reversed(patches):
                    network_patch.stop()
                connection.close()

    def test_prohibited_semantic_promotions_fail_closed(self) -> None:
        mutations: list[tuple[str, dict[str, Any]]] = []
        for name in SOURCE_ORDER:
            document = self._load(name)

            changed = copy.deepcopy(document)
            changed["lifecycle"][0]["value"] = "operational"
            mutations.append((name, changed))

            changed = copy.deepcopy(document)
            changed["project"]["coordinates"] = {
                "latitude": 1.0,
                "longitude": 1.0,
            }
            mutations.append((name, changed))

            changed = copy.deepcopy(document)
            changed["workloads"] = [{"forbidden": "design wording is not workload"}]
            mutations.append((name, changed))

        for name in (SWE02_SOURCE, FIN04_SOURCE):
            changed = copy.deepcopy(self._load(name))
            changed["capacities"] = [{"forbidden": "untyped MW is metadata only"}]
            mutations.append((name, changed))

        changed = copy.deepcopy(self._load(TERACO_SOURCE))
        changed["capacities"].append({"forbidden": "68 MVA is not MW"})
        mutations.append((TERACO_SOURCE, changed))

        changed = copy.deepcopy(self._load(GREEN_SOURCE))
        changed["operating_models"] = [
            {"forbidden": "customer wording is not an operating model"}
        ]
        mutations.append((GREEN_SOURCE, changed))

        changed = copy.deepcopy(self._load(FIN04_SOURCE))
        changed["project"]["stable_key"] = (
            "curated:atnorth-fin04-kouvola-campus:all-future-phases"
        )
        mutations.append((FIN04_SOURCE, changed))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
