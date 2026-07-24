from __future__ import annotations

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
SOURCE_NAME = (
    "curated-official-2026-07-20-racks-central-johor-ai-campus-rcjm1.json"
)
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "66cf889e5396a5c766af433cc142eb78edaded1fa868ad0e7c5093c0994b87b6"
SOURCE_BYTES = 22_242
RETRIEVED_AT = "2026-07-20T07:06:16Z"

CAMPUS_KEY = "curated:racks-central-johor-ai-campus"
PROJECT_KEY = "curated:racks-central-johor-ai-campus:rcjm1-first-phase"

GROUNDBREAKING_KEY = (
    "racks-central-rcjm1-groundbreaking-2025-12-03-captured-2026-07-20"
)
STATUS_KEY = (
    "racks-central-johor-campus-status-2026-03-06-captured-2026-07-20"
)
ESA_KEY = (
    "racks-central-johor-electricity-supply-agreement-2026-05-14-"
    "captured-2026-07-20"
)

CAPTURES: dict[str, dict[str, Any]] = {
    GROUNDBREAKING_KEY: {
        "url": (
            "https://www.linkedin.com/posts/racks-central-pte-ltd_"
            "something-exciting-is-taking-shape-in-activity-"
            "7401900089285468160-6WjT"
        ),
        "published_at": "2025-12-03T08:28:21.921Z",
        "body_bytes": 339_258,
        "body_sha256": (
            "4ee799159eac3e78f17f9539ea221b179374c2566f4727ebada8bb5483e4116d"
        ),
        "header_bytes": 5_301,
        "header_sha256": (
            "f1902eb3e45f213ce58196e565000c18caf8688c62500b2b48eabc73d2446b4d"
        ),
        "writeout_bytes": 17_777,
        "writeout_sha256": (
            "a15f6337746a1952b71f6a286b74745b017353e2767af11a9e9673e6dda11e6d"
        ),
        "http_date": "2026-07-20T07:06:15Z",
    },
    STATUS_KEY: {
        "url": (
            "https://www.linkedin.com/posts/racks-central-pte-ltd_"
            "malaysia-investments-hit-record-high-in-2025-activity-"
            "7435643633845862400-Z81T"
        ),
        "published_at": "2026-03-06T11:13:09.865Z",
        "body_bytes": 314_158,
        "body_sha256": (
            "8666e0ef71c2e6038cc6823b1eb496b78984abafcce9034c2b903696b3fbf4ca"
        ),
        "header_bytes": 5_301,
        "header_sha256": (
            "dc37f9cd914765d8cc5fd618debad60d23f0458c92be91c7ea022f60bb94f578"
        ),
        "writeout_bytes": 17_797,
        "writeout_sha256": (
            "a494802cfcbf5ac6485dc745977efdc6c43cdd48e994bb290fbe9a6ca967a6c3"
        ),
        "http_date": "2026-07-20T07:06:15Z",
    },
    ESA_KEY: {
        "url": (
            "https://www.linkedin.com/posts/racks-central-pte-ltd_"
            "aiinfrastructure-aidc-johor-activity-"
            "7460573379054653440-XajC"
        ),
        "published_at": "2026-05-14T06:15:04.290Z",
        "body_bytes": 129_519,
        "body_sha256": (
            "784e0e1e65d84e0314e64096a28efd3b8c92b64a069dc1299651b71732d44a04"
        ),
        "header_bytes": 5_301,
        "header_sha256": (
            "0c95f0a58246ce53aaed5f70f9cd27183fd166f39b7f2e8daa6fcdd27ee20142"
        ),
        "writeout_bytes": 17_726,
        "writeout_sha256": (
            "192551fc8cae482f0b75a42b316890cd237de59762ed14d22782e73091074eb5"
        ),
        "http_date": "2026-07-20T07:06:16Z",
    },
}


class RacksCentralJohorCuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))

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
        self, repetitions: int
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            SOURCE_PATH,
                            retrieved_at=RETRIEVED_AT,
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method, confidence "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT metric, stage, base FROM capacity_estimates ORDER BY id",
                    "SELECT operating_model FROM operating_model_observations ORDER BY id",
                    "SELECT workload FROM workload_observations ORDER BY id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
        self.assertEqual(stat.S_IMODE(SOURCE_PATH.stat().st_mode), 0o644)
        self.assertEqual(SOURCE_PATH.stat().st_size, SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(), SOURCE_SHA256
        )

        text = SOURCE_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(
            text,
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 3)

    def test_capture_triples_are_exact_closed_and_zero_redirect(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))

        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["publisher"], "Racks Central")
                self.assertEqual(
                    item["source_family"],
                    "racks_central_linkedin_company_posts",
                )
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte',
                    metadata["content_hash_scope"],
                )
                self.assertEqual(
                    metadata["content_hash_verification"],
                    "fetched_bytes_sha256",
                )
                self.assertIn(
                    f'{expected["header_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"],
                    expected["header_sha256"],
                )
                self.assertIn(
                    f'{expected["writeout_bytes"]}-byte',
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(
                    metadata["content_type"], "text/html; charset=utf-8"
                )
                self.assertIsNone(metadata["content_encoding_as_received"])
                self.assertIsNone(
                    metadata["http_content_length_bytes_as_received"]
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["body_bytes"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["http_date"]
                )
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertEqual(
                    metadata["structured_date_published"],
                    expected["published_at"],
                )
                self.assertIn(
                    "Only the top-level Racks Central post text",
                    metadata["publisher_authored_text_scope"],
                )

    def test_scope_is_one_campus_one_first_phase_and_one_generic_status(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]

        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Racks Central Johor AI Campus")
        self.assertEqual(project["name"], "Racks Central RCJM 1 First Phase")
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Malaysia")
            self.assertEqual(entity["address"], "Johor, Malaysia")
            self.assertEqual(entity["roles"], {"developer": ["Racks Central"]})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["as_of_date"], "2026-05-14")
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": ESA_KEY,
                    "as_of_date": "2026-05-14",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.97,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

    def test_mw_esa_facility_count_and_forecasts_remain_metadata_only(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        groundbreaking = evidence[GROUNDBREAKING_KEY]["metadata"]
        status = evidence[STATUS_KEY]["metadata"]
        esa = evidence[ESA_KEY]["metadata"]

        self.assertEqual(groundbreaking["reported_development_pipeline_mw_low"], 500)
        self.assertEqual(groundbreaking["reported_development_pipeline_mw_high"], 700)
        self.assertEqual(groundbreaking["reported_rfs_forecast"], "Q4 2026")
        self.assertIn("metadata only", groundbreaking["pipeline_capacity_guardrail"])

        self.assertEqual(status["reported_first_phase_mw"], 90)
        self.assertEqual(status["reported_full_buildout_mw"], 510)
        self.assertEqual(status["reported_rfs_forecast"], "Q4 2026-Q1 2027")
        self.assertIn("untyped", status["capacity_guardrail"])

        self.assertEqual(esa["reported_full_buildout_mw"], 510)
        self.assertEqual(esa["reported_full_buildout_facility_count"], 4)
        self.assertEqual(
            esa["reported_earliest_facility_rfs_forecast"],
            "late Q4 2026 to Q1 2027",
        )
        self.assertIn("creates no normalized grid-capacity", esa["electricity_supply_agreement_scope"])
        self.assertIn("Only the named RCJM 1", esa["facility_count_guardrail"])
        self.assertIn("forecast evolution", esa["schedule_evolution_guardrail"])
        self.assertIn("no normalized workload", esa["classification_guardrail"])

    def test_stable_keys_do_not_collide_with_other_curated_sources(self) -> None:
        claimed = {CAMPUS_KEY, PROJECT_KEY}
        collisions: dict[str, list[str]] = {}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE_PATH:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            keys = {
                entity["stable_key"]
                for entity in (document.get("campus"), document.get("project"))
                if isinstance(entity, dict) and "stable_key" in entity
            }
            overlap = sorted(claimed & keys)
            if overlap:
                collisions[path.name] = overlap
        self.assertEqual(collisions, {})

    def test_offline_import_is_valid_exact_and_idempotent(self) -> None:
        once = self._database_state(1)
        twice = self._database_state(2)
        self.assertEqual(once, twice)

        (
            entities,
            evidence,
            lifecycle,
            snapshots,
            projects,
            capacities,
            operating_models,
            workloads,
        ) = once
        self.assertEqual(
            entities,
            (("campus", CAMPUS_KEY), ("project", PROJECT_KEY)),
        )
        self.assertEqual(
            evidence,
            tuple(
                sorted(
                    (
                        key,
                        expected["body_sha256"],
                    )
                    for key, expected in CAPTURES.items()
                )
            ),
        )
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-05-14",
                    "authoritative_physical_status_update",
                    0.97,
                ),
            ),
        )
        self.assertEqual(len(snapshots), 2)
        for stable_key, name, tags_json, latitude, longitude, geometry_json in snapshots:
            self.assertIn(stable_key, {CAMPUS_KEY, PROJECT_KEY})
            self.assertIn(name, {
                "Racks Central Johor AI Campus",
                "Racks Central RCJM 1 First Phase",
            })
            self.assertEqual(
                json.loads(tags_json),
                {
                    "address": "Johor, Malaysia",
                    "country": "Malaysia",
                    "role:developer": "Racks Central",
                    "source_dataset": "curated_official_sources",
                },
            )
            self.assertIsNone(latitude)
            self.assertIsNone(longitude)
            self.assertIsNone(geometry_json)
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())

    def test_import_rejects_any_other_retrieval_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    with self.assertRaisesRegex(
                        ValueError,
                        "evidence\\[0\\]\\.retrieved_at must equal the import retrieved_at",
                    ):
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            SOURCE_PATH,
                            retrieved_at="2026-07-20T07:06:15Z",
                        )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
