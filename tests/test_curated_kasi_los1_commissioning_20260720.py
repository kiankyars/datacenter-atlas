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
SOURCE_NAME = "curated-official-2026-07-20-kasi-los1-commissioning.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 12_812
SOURCE_SHA256 = "caaddbfbc641c00c87c7b7fcfb29c5f2af5df8f7ca541dcff6d94294e42afd01"
SOURCE_URL = (
    "https://www.globenewswire.com/news-release/2026/05/19/3297917/0/en/"
    "kasi-cloud-datacenters-commissions-west-africa-s-first-hyperscale-ready-"
    "ai-capable-data-centre-campus-in-lagos.html"
)
EVIDENCE_KEY = "kasi-los1-commissioning-2026-05-19-captured-2026-07-20"
CAMPUS_KEY = "curated:kasi-lekki-data-centre-campus"
PROJECT_KEY = "curated:kasi-lekki-data-centre-campus:los1-first-building"
RETRIEVED_AT = "2026-07-20T09:25:15Z"
AS_OF_DATE = "2026-05-19"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"


class KasiLos1CommissioningCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Kasi curated import attempted network access")
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
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload",
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
        self.assertEqual(record["publisher"], "Kasi Cloud Datacenters")
        self.assertEqual(record["source_family"], "kasi_globenewswire_release")
        self.assertEqual(record["source_url"], SOURCE_URL)
        self.assertEqual(record["published_at"], "2026-05-19T19:40:42Z")
        self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(
            record["content_hash"],
            "c49c83ee0290a8191e32cf3077692b123881b919fd7036f584276b06430b144e",
        )
        self.assertIn("67143-byte", metadata["content_hash_scope"])
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "a2fcf5a43d124fca48860d8d04741c6d986e6e1b25b2428470cd25c897463602",
        )
        self.assertIn("2353-byte", metadata["capture_headers_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "fb6643358d75ba277027fda43fa45df417f4d528d4cb0ffc6bc01bcb00e5085d",
        )
        self.assertIn("13257-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_exit_code"], 0)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 14_701)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 14_701)
        self.assertEqual(metadata["curl_size_header_bytes"], 2_353)
        self.assertEqual(metadata["curl_num_headers"], 19)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["http_last_modified_at"], RETRIEVED_AT)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertEqual(
            metadata["structured_jsonld_date_published"],
            "2026-05-19T19:40:42Z",
        )

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

    def test_scope_is_one_unmapped_campus_and_one_first_building(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Kasi Lekki Data Centre Campus")
        self.assertEqual(project["name"], "Kasi LOS1 First Building")
        expected_roles = {
            "developer": ["Kasi Cloud Datacenters"],
            "operator": ["Kasi Cloud Datacenters"],
        }
        self.assertEqual(campus["roles"], expected_roles)
        self.assertEqual(project["roles"], expected_roles)
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Nigeria")
            self.assertEqual(entity["address"], "Maiyegun, Lekki, Lagos, Nigeria")
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        metadata = document["evidence"][0]["metadata"]
        self.assertIn("100 MW figure covers the Lekki campus", metadata["campus_project_scope"])
        self.assertIn("no street address", metadata["location_scope"])
        self.assertIn("unique_site_counted remains false", metadata["site_resolution_guardrail"])

    def test_los1_is_commissioning_but_not_operational(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "commissioning",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["reported_remaining_precommercial_activities"],
            ["phased commissioning", "systems integration", "customer readiness"],
        )
        for unsupported in (
            "completion",
            "occupancy",
            "full commercial operation",
            "current load",
            "measured energy consumption",
        ):
            self.assertIn(unsupported, metadata["lifecycle_scope"])
        self.assertIn("not treated as proof", metadata["ceremony_guardrail"])
        self.assertNotIn("operational", {row["value"] for row in document["lifecycle"]})

    def test_only_full_campus_planned_critical_it_is_normalized(self) -> None:
        document = self._load()
        self.assertEqual(
            document["capacities"],
            [
                {
                    "entity": "campus",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 100,
                    "base": 100,
                    "high": 100,
                    "method": "reported",
                    "confidence": 0.95,
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "target_date": None,
                    "notes": (
                        "Approximate long-term critical-IT capacity for the full "
                        "Lekki campus at complete development. It is not LOS1 capacity, "
                        "installed or energized capacity, grid draw, gross-facility "
                        "demand, generation, current load, measured consumption, or "
                        "annual energy."
                    ),
                }
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_campus_long_term_critical_it_mw_approximate"], 100)
        self.assertEqual(metadata["reported_grid_connection_voltage_kv"], 132)
        self.assertIn("not power capacity", metadata["power_guardrail"])
        self.assertIn("not assigned to LOS1", metadata["capacity_scope"])

    def test_open_bound_pue_and_unsized_power_system_stay_metadata_only(self) -> None:
        document = self._load()
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_pue_target_as_reported"], "less than or equal to 1.6")
        self.assertEqual(metadata["reported_power_system_components"], ["gas", "solar", "battery storage"])
        self.assertFalse(any(row["metric"] == "pue" for row in document["capacities"]))
        self.assertFalse(
            any(row["metric"] == "generation_nameplate_mw" for row in document["capacities"])
        )
        self.assertIn("open-bound future target", metadata["pue_guardrail"])
        self.assertIn("no source-supported nameplate sizes", metadata["power_guardrail"])
        self.assertIn("no operational electrical load", metadata["energy_guardrail"])
        self.assertIn("not converted into MWh", metadata["energy_guardrail"])

    def test_classification_is_broad_intended_ai_and_cloud_only(self) -> None:
        document = self._load()
        self.assertEqual(document["operating_models"], [])
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
                },
                {
                    "entity": "project",
                    "value": "general_cloud",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "company_disclosure",
                    "confidence": 0.95,
                },
            ],
        )
        metadata = document["evidence"][0]["metadata"]
        for unsupported in (
            "installed accelerators",
            "AI training-versus-inference split",
            "HPC as a distinct workload",
            "current customers",
            "current compute activity",
        ):
            self.assertIn(unsupported, metadata["workload_scope"])
        for unsupported_model in (
            "retail colocation",
            "wholesale colocation",
            "hyperscale lease",
        ):
            self.assertIn(unsupported_model, metadata["operating_model_guardrail"])

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
            ((EVIDENCE_KEY, "c49c83ee0290a8191e32cf3077692b123881b919fd7036f584276b06430b144e", RETRIEVED_AT, SOURCE_URL),),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(lifecycle, ((PROJECT_KEY, "commissioning", AS_OF_DATE, RETRIEVED_AT, "authoritative_physical_status_update", 0.99),))
        self.assertEqual(len(capacities), 1)
        self.assertEqual(
            capacities[0][:9],
            (CAMPUS_KEY, "critical_it_mw", "planned", 100.0, 100.0, 100.0, AS_OF_DATE, None, RETRIEVED_AT),
        )
        self.assertEqual(models, ())
        self.assertEqual(
            workloads,
            (
                (PROJECT_KEY, "ai_specialized_unspecified", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.95),
                (PROJECT_KEY, "general_cloud", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.95),
            ),
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
        document["evidence"][0]["retrieved_at"] = "2026-07-20T09:25:16Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_method_for_commissioning(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 6.4,
            "longitude": 3.5,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
