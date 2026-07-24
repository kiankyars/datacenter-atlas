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
SOURCE_NAME = "curated-official-2026-07-20-galaxy-helios-phase2.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 11_436
SOURCE_SHA256 = "5463da008a588bb9993310ee13ca82da039435cf5f3815c574d3ac0ee576f57f"
SOURCE_URL = (
    "https://www.galaxy.com/newsroom/"
    "galaxy-completes-phase-i-of-its-helios-data-center-campus"
)
EVIDENCE_KEY = (
    "galaxy-helios-phase2-construction-2026-07-06-captured-2026-07-20"
)
CAMPUS_KEY = "curated:galaxy-helios-data-center-campus"
PROJECT_KEY = (
    "curated:galaxy-helios-data-center-campus:"
    "phase-2-260mw-critical-it-build"
)
RETRIEVED_AT = "2026-07-20T07:55:03Z"
AS_OF_DATE = "2026-07-06"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"


class GalaxyHeliosPhase2CuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Galaxy curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _state(
        self,
        source_path: Path = SOURCE_PATH,
        *,
        repetitions: int = 1,
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
                            result.entities_created,
                            2 if iteration == 0 else 0,
                        )
                        self.assertEqual(
                            result.evidence_created,
                            1 if iteration == 0 else 0,
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
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence, notes "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, "
                    "method, confidence FROM workload_observations JOIN entities "
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

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            path = Path(temporary) / SOURCE_NAME
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

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE_PATH.is_file())
        self.assertFalse(SOURCE_PATH.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE_PATH.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE_PATH.stat().st_mode), 0o644)
        self.assertEqual(SOURCE_PATH.stat().st_size, SOURCE_BYTES)
        self.assertEqual(
            hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
            SOURCE_SHA256,
        )
        text = SOURCE_PATH.read_text(encoding="utf-8")
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

    def test_capture_contract_is_exact_closed_and_zero_redirect(self) -> None:
        evidence = self._load()["evidence"]
        self.assertEqual(len(evidence), 1)
        record = evidence[0]
        metadata = record["metadata"]
        self.assertEqual(record["key"], EVIDENCE_KEY)
        self.assertEqual(record["kind"], "company_disclosure")
        self.assertEqual(record["publisher"], "Galaxy Digital Inc.")
        self.assertEqual(record["source_family"], "galaxy_newsroom")
        self.assertEqual(record["source_url"], SOURCE_URL)
        self.assertEqual(record["published_at"], AS_OF_DATE)
        self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(
            record["content_hash"],
            "f46a95f8d5f6a9980416fe971dccfb1e6af0eaedd82b1159e7bd69d59d127805",
        )
        self.assertIn("106930-byte", metadata["content_hash_scope"])
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "d3ee5f9b752dddc2209302e81a23b365e2721130b3170510ee6521fee7c8af56",
        )
        self.assertIn("1053-byte", metadata["capture_headers_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "b4524177de94faea3b5838aa7c3e661509b364921217e0d4d5d873017c444f27",
        )
        self.assertIn("12863-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_exit_code"], 0)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 20_300)
        self.assertEqual(metadata["curl_size_header_bytes"], 1_053)
        self.assertEqual(metadata["curl_num_headers"], 21)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], "2026-07-20T02:01:26Z")
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertEqual(metadata["structured_page_date_text"], "July 06, 2026")
        self.assertIsNone(metadata["structured_jsonld_date_published"])

        forbidden_telemetry_keys = {
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
        self.assertTrue(
            forbidden_telemetry_keys.isdisjoint(
                {field.casefold() for field in metadata}
            )
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])

    def test_scope_is_one_unmapped_campus_and_one_phase_two_project(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Galaxy Helios Data Center Campus")
        self.assertEqual(
            project["name"],
            "Galaxy Helios Phase II 260 MW Critical IT Build",
        )
        self.assertEqual(campus["roles"], {
            "developer": ["Galaxy"],
            "operator": ["Galaxy"],
        })
        self.assertEqual(project["roles"], {
            "developer": ["Galaxy"],
            "operator": ["Galaxy"],
            "tenant": ["CoreWeave"],
        })
        for entity in (campus, project):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], "West Texas, United States")
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        metadata = document["evidence"][0]["metadata"]
        self.assertIn("No city", metadata["location_scope"])
        self.assertIn("unique_site_counted remains false", metadata["site_resolution_guardrail"])
        self.assertIn("Phase II only", metadata["phase_scope_guardrail"])

    def test_physical_status_is_generic_construction_not_a_narrower_stage(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["reported_phase_ii_physical_work"],
            [
                "greenfield development underway",
                "civil work advancing",
                "structural work advancing",
            ],
        )
        for unsupported in (
            "excavation",
            "foundations",
            "structural frame",
            "shell",
            "MEP",
            "energization",
            "commissioning",
            "completion",
            "occupancy",
            "operation",
        ):
            self.assertIn(unsupported, metadata["construction_scope"])
        self.assertEqual(metadata["reported_phase_ii_delivery_forecast"], "first half of 2027")
        self.assertIn("forward-looking range", metadata["delivery_guardrail"])

    def test_only_phase_two_critical_it_is_normalized(self) -> None:
        document = self._load()
        self.assertEqual(
            document["capacities"],
            [
                {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "contracted",
                    "unit": "MW",
                    "low": 260,
                    "base": 260,
                    "high": 260,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "target_date": None,
                    "notes": (
                        "Contracted critical IT capacity for the physically active "
                        "Phase II build. This is not Phase I capacity, the Phase I-to-III "
                        "aggregate, gross power, campus approved power, campus potential "
                        "power, generation, current load, or annual energy consumption."
                    ),
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_phase_ii_critical_it_mw"], 260)
        self.assertEqual(metadata["reported_phase_i_gross_power_mw"], 200)
        self.assertEqual(metadata["reported_phase_i_critical_it_mw"], 133)
        self.assertEqual(
            metadata["reported_phases_i_through_iii_committed_critical_it_mw"],
            526,
        )
        self.assertEqual(
            metadata["reported_phases_i_through_iii_approved_and_contracted_gross_power_mw"],
            800,
        )
        self.assertEqual(metadata["reported_campus_total_approved_power_gw"], 1.63)
        self.assertEqual(metadata["reported_campus_potential_power_gw"], 3.6)
        self.assertIn("remain metadata", metadata["capacity_nonaggregation_guardrail"])
        self.assertIn("No current electrical load", metadata["energy_guardrail"])
        self.assertIn("not converted into MWh", metadata["energy_guardrail"])

    def test_type_is_hyperscale_lease_and_broad_ai_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "hyperscale_lease",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "company_disclosure",
                    "confidence": 0.95,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("CoreWeave", metadata["operating_model_scope"])
        for unsupported in ("AI training", "AI inference", "HPC", "installed accelerators"):
            self.assertIn(unsupported, metadata["workload_scope"])

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
        self.assertEqual(
            evidence,
            ((
                EVIDENCE_KEY,
                "f46a95f8d5f6a9980416fe971dccfb1e6af0eaedd82b1159e7bd69d59d127805",
                RETRIEVED_AT,
                SOURCE_URL,
            ),),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual({row[3] for row in lifecycle}, {RETRIEVED_AT})
        self.assertEqual(lifecycle[0][:3], (PROJECT_KEY, "under_construction", AS_OF_DATE))
        self.assertEqual(len(capacities), 1)
        self.assertEqual(
            capacities[0][:9],
            (
                PROJECT_KEY,
                "critical_it_mw",
                "contracted",
                260.0,
                260.0,
                260.0,
                AS_OF_DATE,
                None,
                RETRIEVED_AT,
            ),
        )
        self.assertEqual(
            models,
            ((PROJECT_KEY, "hyperscale_lease", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.99),),
        )
        self.assertEqual(
            workloads,
            ((PROJECT_KEY, "ai_specialized_unspecified", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.95),),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(self._state(repetitions=2), state)

    def test_keys_are_collision_free_and_v44_is_unchanged(self) -> None:
        entity_keys: set[str] = set()
        evidence_keys: set[str] = set()
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE_PATH:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                record = document.get(field)
                if isinstance(record, dict) and isinstance(record.get("stable_key"), str):
                    entity_keys.add(record["stable_key"])
            for record in document.get("evidence", []):
                if isinstance(record, dict) and isinstance(record.get("key"), str):
                    evidence_keys.add(record["key"])
        self.assertNotIn(CAMPUS_KEY, entity_keys)
        self.assertNotIn(PROJECT_KEY, entity_keys)
        self.assertNotIn(EVIDENCE_KEY, evidence_keys)

        v44 = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
        self.assertEqual(hashlib.sha256(v44.read_bytes()).hexdigest(), V44_SHA256)
        self.assertNotIn(SOURCE_NAME, v44.read_text(encoding="utf-8"))

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load())
        document["evidence"][0]["retrieved_at"] = "2026-07-20T07:55:04Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_method_for_physical_construction(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 31.0,
            "longitude": -102.0,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
