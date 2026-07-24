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
SOURCE_NAME = (
    "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json"
)
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 16_995
SOURCE_SHA256 = "cf283bdd697427ea54cc282b37078af2ca4e0ba85aee08352b38427bcc8f4724"
RETRIEVED_AT = "2026-07-20T22:34:18Z"

CAMPUS_KEY = "curated:google-bermuda-hundred-chesterfield-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:current-development"
GOOGLE_KEY = (
    "google-virginia-investment-chesterfield-2025-08-27-captured-2026-07-20"
)
COUNTY_KEY = (
    "chesterfield-county-google-bermuda-hundred-2025-08-28-captured-2026-07-20"
)
ADDRESS = "Bermuda Hundred, Chesterfield County, Virginia, United States"
GOOGLE_URL = (
    "https://blog.google/company-news/inside-google/company-announcements/"
    "google-american-innovation-virginia/"
)
COUNTY_URL = "https://www.chesterfield.gov/m/newsflash/Home/Detail/6383"

CAPTURES: dict[str, dict[str, Any]] = {
    GOOGLE_KEY: {
        "kind": "company_disclosure",
        "publisher": "Google",
        "source_family": "google_official_blog",
        "published_at": "2025-08-27T16:40:00+00:00",
        "url": GOOGLE_URL,
        "body_sha256": (
            "2773f7c9a2bb91e6c4589f77df93e1760054929f67591b706b191874f6819516"
        ),
        "body_bytes": 380_325,
        "header_sha256": (
            "d96f10eed563c127c0ccd930de92d324b31cfe8d546b65e56bb73486bf3f2138"
        ),
        "header_bytes": 2_799,
        "content_length": 76_381,
        "response_http_date": "2026-07-20T22:34:17Z",
    },
    COUNTY_KEY: {
        "kind": "government_record",
        "publisher": "Chesterfield County, Virginia",
        "source_family": "chesterfield_county_official_news",
        "published_at": "2025-08-28",
        "url": COUNTY_URL,
        "body_sha256": (
            "678f589c75b03989eeb9fd69566002b1eb6b29cef8f21b64604cfdbe674106ec"
        ),
        "body_bytes": 138_938,
        "header_sha256": (
            "3791ee053c1d65fc43691900f9fc1b0b646f619bc876eac784745a0bd11d2a40"
        ),
        "header_bytes": 875,
        "content_length": 38_966,
        "response_http_date": RETRIEVED_AT,
    },
}


class GoogleBermudaHundredChesterfieldCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Google Bermuda Hundred import attempted network access")
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
                    "SELECT metric FROM capacity_estimates ORDER BY id",
                    "SELECT operating_model FROM operating_model_observations "
                    "ORDER BY id",
                    "SELECT workload FROM workload_observations ORDER BY id",
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

    def test_google_and_county_capture_hashes_and_metadata_are_exact(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["kind"], expected["kind"])
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["license"], "all-rights-reserved")
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertEqual(
                    metadata["content_hash_scope"],
                    "SHA-256 of the exact "
                    f"{expected['body_bytes']}-byte content-decoded official HTML "
                    "response body captured with curl --compressed",
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
                self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["response_http_date"]
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

        google = evidence[GOOGLE_KEY]["metadata"]
        self.assertEqual(google["canonical_url"], GOOGLE_URL)
        self.assertEqual(
            google["page_date_published"], "2025-08-27T16:40:00+00:00"
        )
        self.assertEqual(
            google["page_date_modified"], "2026-01-07T18:57:45.560285+00:00"
        )
        self.assertEqual(google["visible_published_date"], "2025-08-27")
        county = evidence[COUNTY_KEY]["metadata"]
        self.assertEqual(
            county["canonical_url_as_published"],
            "http://www.chesterfield.gov/m/newsflash/Home/Detail/6383",
        )
        self.assertIn("successful captured request", county["canonical_scheme_guardrail"])
        self.assertEqual(county["visible_published_date"], "2025-08-28")

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

    def test_bermuda_hundred_locality_role_and_parent_are_exact(self) -> None:
        document = self._load()
        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        google = metadata[GOOGLE_KEY]
        county = metadata[COUNTY_KEY]
        self.assertEqual(google["reported_identity"], "new data center in Chesterfield County")
        self.assertIn("Google as the developer", google["identity_scope"])
        self.assertEqual(county["reported_identity"], "Google data center campus")
        self.assertEqual(
            county["reported_locality"],
            "Bermuda Hundred, Chesterfield County, Virginia",
        )
        self.assertEqual(county["reported_site_area_acres_lower_bound"], 300)
        self.assertEqual(
            county["reported_development_scope"], "multiphase data center campus"
        )
        self.assertIn("No street address", county["locality_scope"])
        self.assertIn("not a parcel boundary", county["area_guardrail"])

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(
                entity["stable_key"],
                CAMPUS_KEY if entity_name == "campus" else PROJECT_KEY,
            )
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], ADDRESS)
            self.assertEqual(entity["roles"], {"developer": ["Google"]})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], COUNTY_KEY)
            self.assertEqual(entity["as_of_date"], "2025-08-28")
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        for record in (google, county):
            self.assertIn("developer only", record["role_scope"])
            self.assertIn("internal parent container", record["entity_model_guardrail"])
            self.assertIn("physical-site count", record["entity_model_guardrail"])
        self.assertIn("must not be added", google["entity_model_guardrail"])
        self.assertIn("unspecified phases are not instantiated", county["entity_model_guardrail"])

    def test_historical_generic_construction_preserves_the_source_conflict(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": COUNTY_KEY,
                    "as_of_date": "2025-08-28",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.95,
                }
            ],
        )
        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        google = metadata[GOOGLE_KEY]
        county = metadata[COUNTY_KEY]
        self.assertIn("no physical construction statement", google["status_guardrail"])
        self.assertEqual(
            county["reported_physical_wording"],
            "Google already has broken ground on the 300-plus-acre Bermuda Hundred site",
        )
        self.assertEqual(
            county["reported_schedule_wording"],
            "Construction is expected to begin by the end of this year and typically "
            "takes 18 to 24 months to complete",
        )
        self.assertIn("historical generic under_construction", county["status_scope"])
        self.assertIn("prevents normalization of a narrower", county["status_scope"])
        self.assertIn("coexist in the same paragraph", county["status_conflict_guardrail"])
        self.assertIn("without deciding", county["status_conflict_guardrail"])
        self.assertIn("not a dated status update after", county["status_freshness_guardrail"])
        self.assertIn("does not prove", county["status_freshness_guardrail"])
        self.assertEqual(
            county["reported_typical_duration_months"], {"low": 18, "high": 24}
        )
        self.assertIn("not a project-specific completion", county["schedule_guardrail"])
        self.assertNotIn(
            "operational", {row["value"] for row in document["lifecycle"]}
        )

    def test_capacity_workload_type_energy_and_other_properties_are_excluded(self) -> None:
        document = self._load()
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["operating_models"], [])
        metadata = {
            item["key"]: item["metadata"] for item in document["evidence"]
        }
        google = metadata[GOOGLE_KEY]
        county = metadata[COUNTY_KEY]
        self.assertEqual(google["reported_virginia_investment_usd"], 9_000_000_000)
        self.assertIn("Virginia-wide", google["investment_scope"])
        self.assertIn("No workload is normalized", google["workload_guardrail"])
        self.assertIn("No facility-specific IT capacity", google["capacity_guardrail"])
        self.assertIn("no site-specific energy source", google["energy_guardrail"])
        self.assertEqual(
            county["future_properties"],
            [
                "Upper Magnolia Green, approximately 880 acres",
                "Watkins Centre South, approximately 350 acres",
            ],
        )
        self.assertIn("explicitly for future development", county["future_properties_guardrail"])
        self.assertIn("create no data-centre identity", county["future_properties_guardrail"])
        self.assertEqual(county["reported_fusion_offtake_mw"], 200)
        self.assertIn("separate future Commonwealth Fusion Systems", county["fusion_guardrail"])
        self.assertIn("not assigned to the Bermuda Hundred campus", county["fusion_guardrail"])
        self.assertIn("creates no site PUE", county["pue_guardrail"])
        self.assertIn("company-level", county["carbon_free_guardrail"])
        self.assertIn("no facility-specific AI", county["workload_guardrail"])
        self.assertIn("No facility-specific IT capacity", county["capacity_guardrail"])
        for record in (google, county):
            self.assertIn("geometry", record["imagery_guardrail"])
            self.assertIn("physical-site count", record["imagery_guardrail"])

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
        county = self._load()["evidence"][1]["metadata"]
        self.assertIn("not merged", county["collision_guardrail"])
        self.assertIn("Upper Magnolia Green", county["collision_guardrail"])
        self.assertIn("Watkins Centre South", county["collision_guardrail"])

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
        expected_tags = {
            "address": ADDRESS,
            "country": "United States",
            "role:developer": "Google",
            "source_dataset": "curated_official_sources",
        }
        for row in snapshots:
            self.assertEqual(json.loads(row[2]), expected_tags)
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[6], "2025-08-28")
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2025-08-28",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.95,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())

    def test_semantic_mutations_cannot_invent_status_energy_or_coordinates(self) -> None:
        weak_status = copy.deepcopy(self._load())
        weak_status["lifecycle"][0]["method"] = "analyst_synthesis"
        self._assert_document_rejected(
            weak_status,
            "construction status requires authoritative_construction_start",
        )

        annual_energy = copy.deepcopy(self._load())
        annual_energy["capacities"] = [
            {
                "entity": "project",
                "metric": "annual_energy_mwh",
                "stage": "measured",
                "unit": "MWh/year",
                "low": 200,
                "base": 200,
                "high": 200,
                "method": "reported",
                "confidence": 0.95,
                "evidence_key": GOOGLE_KEY,
                "as_of_date": "2025-08-27",
                "target_date": None,
                "notes": "Fabricated from the unrelated fusion offtake.",
            }
        ]
        self._assert_document_rejected(
            annual_energy,
            "measured annual energy requires utility_record or government_record",
        )

        invented_coordinates = copy.deepcopy(self._load())
        invented_coordinates["campus"]["coordinates"] = {
            "latitude": 37.3,
            "longitude": -77.4,
        }
        self._assert_document_rejected(
            invented_coordinates,
            "authoritative_locality requires null coordinates and geometry",
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
        status = connection.execute(
            "SELECT status || ':' || as_of_date || ':' || confidence FROM lifecycle_observations"
        ).fetchone()[0]
        print(json.dumps({{"counts": counts, "status": status}}, sort_keys=True))
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
                            "capacity": 0,
                            "entities": 2,
                            "evidence": 2,
                            "lifecycle": 1,
                            "operating_models": 0,
                            "snapshots": 2,
                            "workloads": 0,
                        },
                        "status": "under_construction:2025-08-28:0.95",
                    },
                )


if __name__ == "__main__":
    unittest.main()
