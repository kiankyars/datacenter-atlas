from __future__ import annotations

import copy
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

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "curated-official-2026-07-20-stt-palava-first-data-centre.json"
SOURCE_SHA256 = "0fbcc8f7bee88339e2665f56237ef6ecfc06db849cb9cbf42e936446054d2a3c"
SOURCE_BYTES = 10_923
RETRIEVED_AT = "2026-07-20T07:10:19Z"
EVIDENCE_KEY = (
    "stt-palava-first-data-centre-groundbreaking-2026-03-16-"
    "captured-2026-07-20"
)
SOURCE_URL = (
    "https://www.linkedin.com/posts/sttgdcindia_datacentre-datacenter-"
    "enablingourdigitalfuture-activity-7439642591719190528-eC_B"
)
CAMPUS_KEY = "curated:stt-palava-data-centre-campus"
PROJECT_KEY = "curated:stt-palava-data-centre-campus:first-data-centre"


class SttPalavaCuratedTests(unittest.TestCase):
    def _path(self) -> Path:
        return ROOT / "sources" / SOURCE

    def _load(self) -> dict[str, Any]:
        return json.loads(self._path().read_text(encoding="utf-8"))

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

    def _state(
        self, *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(),
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, recorded_at",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, recorded_at",
                    "SELECT entities.stable_key, metric, stage, low, base, high, unit, "
                    "as_of_date, recorded_at, target_date, method, confidence "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            source.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        source,
                        retrieved_at=RETRIEVED_AT,
                    )
            finally:
                connection.close()

    def test_exact_source_is_hash_pinned_canonical_regular_file(self) -> None:
        path = self._path()
        self.assertTrue(path.is_file())
        self.assertFalse(path.is_symlink())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(path.stat().st_size, SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), SOURCE_SHA256)
        text = path.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)

    def test_capture_contract_is_official_closed_and_byte_bound(self) -> None:
        evidence = self._load()["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "ST Telemedia Global Data Centres (India)")
        self.assertEqual(evidence["published_at"], "2026-03-17T12:03:35.722Z")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(
            evidence["content_hash"],
            "6773cafe0e6f395f6064d0d27e8764a52677888b7e257c935362d1a9b2dd35a2",
        )
        self.assertIn("194898-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("5348-byte", metadata["capture_headers_scope"])
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "6abf40ba16c1aa7d683c7ea3d7b6cd6a713d38a6401eafa720ae04ab38a0e372",
        )
        self.assertIn("403-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "fb13262f30c6973dc05860b24fb5fd7355bcf1e32e20d99add87231f0f89a9f9",
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 22_640)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 22_640)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertIn("supplied no Authorization", metadata["request_credentials_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])

    def test_identity_and_locality_do_not_invent_precision_or_extra_facilities(self) -> None:
        document = self._load()
        self.assertEqual(
            {document["campus"]["stable_key"], document["project"]["stable_key"]},
            {CAMPUS_KEY, PROJECT_KEY},
        )
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "India")
            self.assertEqual(
                entity["address"],
                "Palava, Mumbai Metropolitan Region, Maharashtra, India",
            )
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("does not invent", metadata["identity_scope"])
        self.assertIn("no source-verifiable street address", metadata["locality_guardrail"])

    def test_groundbreaking_is_generic_construction_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-03-16",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["construction_date_as_reported"], "2026-03-16")
        for unsupported in ("foundations", "shell", "MEP", "commissioning", "operation"):
            self.assertIn(unsupported, metadata["status_scope"])

    def test_typed_capacities_preserve_nested_scopes_and_approximation(self) -> None:
        document = self._load()
        rows = {
            (row["entity"], row["metric"], row["stage"]): row
            for row in document["capacities"]
        }
        self.assertEqual(
            set(rows),
            {
                ("project", "critical_it_mw", "planned"),
                ("campus", "critical_it_mw", "planned"),
            },
        )
        project = rows[("project", "critical_it_mw", "planned")]
        campus = rows[("campus", "critical_it_mw", "planned")]
        self.assertEqual((project["low"], project["base"], project["high"]), (50, 50, 50))
        self.assertEqual((campus["low"], campus["base"], campus["high"]), (400, 400, 400))
        self.assertEqual(project["confidence"], 0.99)
        self.assertEqual(campus["confidence"], 0.95)
        self.assertIn("approximate", campus["notes"])
        self.assertIn("not exact", campus["notes"])
        self.assertIn("not additive with 50 MW", campus["notes"])
        self.assertIn(
            "must not be added",
            document["evidence"][0]["metadata"]["capacity_non_additivity_guardrail"],
        )
        for row in rows.values():
            self.assertEqual(row["unit"], "MW")
            self.assertEqual(row["method"], "reported")
            self.assertEqual(row["as_of_date"], "2026-03-17")
            self.assertIsNone(row["target_date"])
            self.assertNotIn(row["stage"], {"installed", "energized", "operational", "measured"})

    def test_marketing_investment_and_area_create_no_false_observations(self) -> None:
        document = self._load()
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_site_area_acres"], 46)
        self.assertEqual(metadata["reported_investment_mou_inr_crore"], 5000)
        self.assertIn("no normalized workload", metadata["classification_guardrail"])
        self.assertIn("create no normalized", metadata["role_guardrail"])
        self.assertIn("no current electrical load", metadata["energy_guardrail"])
        self.assertIn("comments", metadata["comment_guardrail"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["campus"]["roles"], {})
        self.assertEqual(document["project"]["roles"], {})

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
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0][1], "6773cafe0e6f395f6064d0d27e8764a52677888b7e257c935362d1a9b2dd35a2")
        self.assertEqual(evidence[0][2:], (RETRIEVED_AT, SOURCE_URL))
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(
            lifecycle,
            ((PROJECT_KEY, "under_construction", "2026-03-16", RETRIEVED_AT, "authoritative_construction_start", 0.99),),
        )
        self.assertEqual(len(capacities), 2)
        self.assertEqual({row[0] for row in capacities}, {CAMPUS_KEY, PROJECT_KEY})
        self.assertEqual({row[1] for row in capacities}, {"critical_it_mw"})
        self.assertEqual({row[2] for row in capacities}, {"planned"})
        self.assertEqual({row[8] for row in capacities}, {RETRIEVED_AT})
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(self._state(repetitions=2), state)

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load())
        document["evidence"][0]["retrieved_at"] = "2026-07-20T07:10:18Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_construction_method(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 19.0,
            "longitude": 73.0,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
