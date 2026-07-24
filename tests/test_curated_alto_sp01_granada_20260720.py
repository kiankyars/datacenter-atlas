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
SOURCE_NAME = "curated-official-2026-07-20-alto-sp01-granada.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 32_589
SOURCE_SHA256 = "5e2f4e431b877d403d3f34d1d5de689450cfa58d1670c9e8b038f39f21d5cc80"
RETRIEVED_AT = "2026-07-20T08:33:14Z"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"

CAMPUS_KEY = "curated:alto-sp01-granada-data-center-campus"
PROJECT_KEY = (
    "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it"
)
CUERVA_KEY = "cuerva-alto-sp01-collaboration-2026-07-08-captured-2026-07-20"
ICEX_KEY = "icex-invest-in-spain-alto-sp01-2026-07-09-captured-2026-07-20"
ALTO_HOME_KEY = "alto-infrastructure-home-sp01-captured-2026-07-20"
ALTO_APP_KEY = "alto-infrastructure-production-app-sp01-captured-2026-07-20"

CAPTURES: dict[str, dict[str, Any]] = {
    CUERVA_KEY: {
        "kind": "company_disclosure",
        "publisher": "Cuerva",
        "source_family": "cuerva_press_releases",
        "published_at": "2026-07-08",
        "url": (
            "https://cuervaenergia.com/es/prensa/ultimas-noticias/"
            "cuerva-alto-infrastructure-impulsan-primer-gran-centro-datos-"
            "especializado-inteligencia-artificial-andalucia/"
        ),
        "body_bytes": 303_660,
        "body_sha256": (
            "b95aec8debc6d90b0735177001769a1e99ea4f7125d069a68e58d0230ed8f254"
        ),
        "header_bytes": 408,
        "header_sha256": (
            "be11249645dfd6c0c6e3a5f887d6a0a6aec23800dbe0344d89cef682ad219857"
        ),
        "writeout_bytes": 14_268,
        "writeout_sha256": (
            "fe6b4232d14509fa3fbf3b8b3030f1604718e02849c5bcf983e832d87282c606"
        ),
        "compressed_download_bytes": 58_391,
        "header_count": 11,
        "content_type": "text/html",
        "content_length": None,
        "http_date": "2026-07-20T08:32:21Z",
        "last_modified": "2026-07-16T09:05:48Z",
    },
    ICEX_KEY: {
        "kind": "government_record",
        "publisher": "Invest in Spain, ICEX España Exportación e Inversiones",
        "source_family": "icex_invest_in_spain_news",
        "published_at": "2026-07-09",
        "url": "https://www.investinspain.org/es/noticias-main/2026/alto",
        "body_bytes": 89_428,
        "body_sha256": (
            "9f55a303819fa94306ea8f99918bf6c807d6eeafee4862f11a7d085681d0587a"
        ),
        "header_bytes": 1_922,
        "header_sha256": (
            "fcefce526e9ffdc40af95a8fde08687b19bfec001384460b9e9d82d7d69e4afd"
        ),
        "writeout_bytes": 14_302,
        "writeout_sha256": (
            "b366aa6e79796f123d0b5e0848b77c69ae21e7c01ed27d0cca6e55f6ec24a902"
        ),
        "compressed_download_bytes": 12_393,
        "header_count": 23,
        "content_type": "text/html;charset=utf-8",
        "content_length": 12_393,
        "http_date": "2026-07-20T08:32:22Z",
        "last_modified": "2026-07-20T03:49:44Z",
    },
    ALTO_HOME_KEY: {
        "kind": "company_disclosure",
        "publisher": "Alto Infrastructure",
        "source_family": "alto_infrastructure_web",
        "published_at": None,
        "url": "https://altoinfrastructure.com/",
        "body_bytes": 5_403,
        "body_sha256": (
            "d2d0976be7bc7b809d9943c4c2b98d4fd0a7ade7741a7a5a74a76165c03268d3"
        ),
        "header_bytes": 596,
        "header_sha256": (
            "0a33d051409fe8499135abc7de72bd305b5457d664b1d258aa5e35c63947a529"
        ),
        "writeout_bytes": 14_275,
        "writeout_sha256": (
            "e6ccc4e241a4353ca44b9a75ff80be8a63b1e73a1d39943974eecc087a7b8e83"
        ),
        "compressed_download_bytes": 1_909,
        "header_count": 16,
        "content_type": "text/html",
        "content_length": None,
        "http_date": "2026-07-20T05:50:02Z",
        "last_modified": "2026-07-13T21:59:47Z",
    },
    ALTO_APP_KEY: {
        "kind": "company_disclosure",
        "publisher": "Alto Infrastructure",
        "source_family": "alto_infrastructure_web_application",
        "published_at": None,
        "url": "https://altoinfrastructure.com/assets/index-qcBJRWrY.js",
        "body_bytes": 2_128_032,
        "body_sha256": (
            "7e5ec53ff90be0a65d73059192807716629e1608d3b8336f12dae6d56b932461"
        ),
        "header_bytes": 603,
        "header_sha256": (
            "a07a3b60d40c6d494b840b66cfd72519a8c20a2a43115943bdcc5686d3c4b78d"
        ),
        "writeout_bytes": 14_379,
        "writeout_sha256": (
            "a33c6002cc7a6122362934927c275260ae3255bfcd641c505b9cbfebc3c36dda"
        ),
        "compressed_download_bytes": 611_018,
        "header_count": 16,
        "content_type": "text/javascript",
        "content_length": None,
        "http_date": "2026-07-20T04:21:57Z",
        "last_modified": "2026-07-13T21:59:47Z",
    },
}


class AltoSp01GranadaCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Alto SP01 curated import attempted network access")
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
                            4 if iteration == 0 else 0,
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
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
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
                    "ORDER BY workload",
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

    def _assert_semantic_contract(self, document: dict[str, Any]) -> None:
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        self.assertEqual(
            document["campus"]["roles"],
            {
                "developer": ["Alto Infrastructure"],
                "operator": ["Alto Infrastructure"],
            },
        )
        self.assertEqual(document["project"]["roles"], document["campus"]["roles"])
        for entity in (document["campus"], document["project"]):
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": ICEX_KEY,
                    "as_of_date": "2026-07-09",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            {item["value"] for item in document["workloads"]},
            {"ai_specialized_unspecified", "hpc", "general_cloud"},
        )
        self.assertEqual(len(document["workloads"]), 3)
        self.assertEqual(
            document["capacities"],
            [
                {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 10,
                    "base": 10,
                    "high": 10,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": ICEX_KEY,
                    "as_of_date": "2026-07-09",
                    "target_date": None,
                    "notes": document["capacities"][0]["notes"],
                }
            ],
        )

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
        self.assertEqual(document["schema_version"], "1.0")

    def test_capture_contract_is_exact_closed_zero_redirect_and_safe(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
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
                self.assertEqual(item["kind"], expected["kind"])
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["source_url"], expected["url"])
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
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["compressed_download_bytes"],
                )
                self.assertEqual(
                    metadata["curl_size_header_bytes"],
                    expected["header_bytes"],
                )
                self.assertEqual(metadata["curl_num_headers"], expected["header_count"])
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(
                    metadata["http_last_modified_at"],
                    expected["last_modified"],
                )
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertTrue(
                    forbidden_telemetry_keys.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )
                self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
                self.assertIn("whole-second UTC", metadata["retrieved_at_semantics"])

    def test_scope_roles_locality_and_unmapped_guardrails_are_exact(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(
            campus["name"],
            "Alto Infrastructure SP01 Granada Data Center Campus",
        )
        self.assertEqual(
            project["name"],
            "Alto Infrastructure SP01 Phase 1 10 MW Critical IT",
        )
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Spain")
            self.assertEqual(
                entity["address"],
                "CITAI, Escúzar, Granada, Andalusia, Spain",
            )
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertIn("Cuerva", metadata[CUERVA_KEY]["role_scope"])
        self.assertIn("not normalized as the utility", metadata[CUERVA_KEY]["role_scope"])
        self.assertIn("intended operator", metadata[ALTO_APP_KEY]["role_scope"])
        self.assertEqual(
            metadata[ALTO_APP_KEY]["reported_display_latitude_label"],
            "37.10°N",
        )
        self.assertIn("incomplete", metadata[ALTO_APP_KEY]["coordinate_guardrail"])
        self.assertIn("unique-site", metadata[ALTO_APP_KEY]["coordinate_guardrail"])

    def test_physical_status_is_generic_construction_only(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertEqual(
            metadata[CUERVA_KEY]["reported_first_stone_ceremony_date"],
            "2026-06-25",
        )
        self.assertIn("ceremonial", metadata[CUERVA_KEY]["ceremony_guardrail"])
        self.assertIn("has begun construction", metadata[ICEX_KEY]["construction_scope"])
        self.assertEqual(
            metadata[ALTO_APP_KEY][
                "reported_investor_route_phase_one_construction_and_fitout_status"
            ],
            "Planned",
        )
        self.assertIn(
            "dated physical-start statements",
            metadata[ALTO_APP_KEY]["status_reconciliation_guardrail"],
        )
        for unsupported in (
            "site preparation",
            "clearing",
            "civil works",
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
            self.assertIn(unsupported, metadata[ICEX_KEY]["construction_scope"])

    def test_only_phase_one_ten_mw_it_is_normalized(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
                capacity["target_date"],
            ),
            ("project", "critical_it_mw", "planned", 10, 10, 10, None),
        )
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        icex = metadata[ICEX_KEY]
        app = metadata[ALTO_APP_KEY]
        home = metadata[ALTO_HOME_KEY]
        self.assertEqual(icex["reported_phase_one_initial_critical_it_mw"], 10)
        self.assertEqual(icex["reported_phase_one_initial_unspecified_electrical_power_mw"], 15)
        self.assertEqual(icex["reported_phase_one_later_2027_critical_it_mw"], 25)
        self.assertEqual(icex["reported_full_build_critical_it_mw"], 70)
        self.assertEqual(icex["reported_full_build_contracted_total_power_mw"], 100)
        self.assertEqual(app["reported_2028_critical_it_mw"], 45)
        self.assertEqual(app["reported_direct_grid_connection_kv"], 130)
        self.assertEqual(app["reported_site_area_square_metres"], 100_000)
        self.assertEqual(app["reported_high_density_rack_kw_more_than"], 120)
        self.assertEqual(app["reported_design_pue"], 1.29)
        self.assertEqual(home["reported_design_pue"], 1.29)
        self.assertIn("nested", icex["capacity_nonaggregation_guardrail"])
        self.assertIn("not power", app["grid_scope"])
        self.assertIn("not measured", app["pue_guardrail"])
        self.assertNotIn(
            15,
            [item["base"] for item in document["capacities"]],
        )
        self.assertNotIn(
            25,
            [item["base"] for item in document["capacities"]],
        )
        self.assertNotIn(
            70,
            [item["base"] for item in document["capacities"]],
        )
        self.assertNotIn(
            100,
            [item["base"] for item in document["capacities"]],
        )

    def test_types_are_explicit_broad_future_design_only(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            [item["value"] for item in document["workloads"]],
            ["ai_specialized_unspecified", "hpc", "general_cloud"],
        )
        self.assertTrue(
            all(item["evidence_key"] == ICEX_KEY for item in document["workloads"])
        )
        self.assertTrue(
            all(item["method"] == "government_record" for item in document["workloads"])
        )
        self.assertTrue(
            all(item["as_of_date"] == "2026-07-09" for item in document["workloads"])
        )
        self.assertNotIn("ai_training", {item["value"] for item in document["workloads"]})
        self.assertNotIn("ai_inference", {item["value"] for item in document["workloads"]})
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertIn("intended", metadata[ICEX_KEY]["classification_scope"])
        self.assertIn("training-versus-inference", metadata[ICEX_KEY]["classification_scope"])
        self.assertIn("design capability", metadata[ALTO_APP_KEY]["high_density_scope"])
        self.assertIn("signed lease", metadata[ICEX_KEY]["operating_model_guardrail"])

    def test_no_measured_energy_current_load_or_pue_is_created(self) -> None:
        document = self._load()
        metrics = {item["metric"] for item in document["capacities"]}
        self.assertEqual(metrics, {"critical_it_mw"})
        self.assertNotIn("annual_energy_mwh", metrics)
        self.assertNotIn("pue", metrics)
        self.assertNotIn("grid_connection_mw", metrics)
        self.assertNotIn("gross_facility_mw", metrics)
        self.assertNotIn("generation_nameplate_mw", metrics)
        text = json.dumps(document, ensure_ascii=False)
        self.assertIn("No current electrical load", text)
        self.assertIn("MW is not converted to MWh", text)
        self.assertIn("design PUE", text)

    def test_offline_import_is_valid_exact_idempotent_and_order_independent(self) -> None:
        state = self._state()
        self.assertEqual(self._state(repetitions=2), state)
        with tempfile.TemporaryDirectory() as temporary:
            reverse_path = Path(temporary) / SOURCE_NAME
            document = self._load()
            document["evidence"] = list(reversed(document["evidence"]))
            reverse_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(self._state(reverse_path), state)

        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            operating_models,
            workloads,
            projects,
        ) = state
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
                sorted(
                    (
                        key,
                        expected["body_sha256"],
                        RETRIEVED_AT,
                        expected["url"],
                    )
                    for key, expected in CAPTURES.items()
                )
            ),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertTrue(all(row[3] is None and row[4] is None for row in snapshots))
        self.assertTrue(all(row[5] is None for row in snapshots))
        self.assertEqual({row[6] for row in snapshots}, {"2026-07-20"})
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(
            lifecycle,
            ((
                PROJECT_KEY,
                "under_construction",
                "2026-07-09",
                RETRIEVED_AT,
                "authoritative_construction_start",
                0.99,
            ),),
        )
        self.assertEqual(len(capacities), 1)
        self.assertEqual(
            capacities[0][:12],
            (
                PROJECT_KEY,
                "critical_it_mw",
                "planned",
                "MW",
                10.0,
                10.0,
                10.0,
                "2026-07-09",
                None,
                RETRIEVED_AT,
                "reported",
                0.99,
            ),
        )
        self.assertEqual(operating_models, ())
        self.assertEqual(
            workloads,
            (
                (
                    PROJECT_KEY,
                    "ai_specialized_unspecified",
                    "2026-07-09",
                    RETRIEVED_AT,
                    "government_record",
                    0.99,
                ),
                (
                    PROJECT_KEY,
                    "general_cloud",
                    "2026-07-09",
                    RETRIEVED_AT,
                    "government_record",
                    0.99,
                ),
                (
                    PROJECT_KEY,
                    "hpc",
                    "2026-07-09",
                    RETRIEVED_AT,
                    "government_record",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))

    def test_keys_are_collision_free_and_v44_is_unchanged(self) -> None:
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

        v44 = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
        self.assertEqual(hashlib.sha256(v44.read_bytes()).hexdigest(), V44_SHA256)
        v44_text = v44.read_text(encoding="utf-8")
        for marker in (SOURCE_NAME, SOURCE_SHA256, CAMPUS_KEY, PROJECT_KEY, *CAPTURES):
            self.assertNotIn(marker, v44_text)

    def test_semantic_leakage_mutations_fail_the_focused_contract(self) -> None:
        original = self._load()
        mutations: list[tuple[str, dict[str, Any]]] = []

        changed = copy.deepcopy(original)
        changed["lifecycle"][0]["value"] = "foundations"
        mutations.append(("ceremony-promoted-to-foundations", changed))

        changed = copy.deepcopy(original)
        changed["capacities"][0]["base"] = 70
        mutations.append(("full-build-overwrites-phase-one", changed))

        changed = copy.deepcopy(original)
        changed["capacities"].append(
            {
                **changed["capacities"][0],
                "metric": "grid_connection_mw",
                "low": 100,
                "base": 100,
                "high": 100,
            }
        )
        mutations.append(("total-power-promoted-to-grid", changed))

        changed = copy.deepcopy(original)
        changed["capacities"].append(
            {
                **changed["capacities"][0],
                "metric": "pue",
                "unit": "ratio",
                "low": 1.29,
                "base": 1.29,
                "high": 1.29,
            }
        )
        mutations.append(("design-pue-promoted", changed))

        changed = copy.deepcopy(original)
        changed["project"]["coordinates"] = {
            "latitude": 37.10,
            "longitude": -3.59,
        }
        mutations.append(("incomplete-display-coordinate-promoted", changed))

        changed = copy.deepcopy(original)
        changed["workloads"][0]["value"] = "ai_training"
        mutations.append(("ai-split-invented", changed))

        changed = copy.deepcopy(original)
        changed["campus"]["roles"]["utility"] = ["Cuerva"]
        mutations.append(("partner-promoted-to-utility", changed))

        changed = copy.deepcopy(original)
        changed["operating_models"] = [
            {
                "entity": "project",
                "value": "colocation",
                "evidence_key": ALTO_HOME_KEY,
                "as_of_date": "2026-07-20",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(("marketing-keyword-promoted-to-model", changed))

        for label, document in mutations:
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                self._assert_semantic_contract(document)

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load())
        document["evidence"][0]["retrieved_at"] = "2026-07-20T08:33:15Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 37.10,
            "longitude": -3.59,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)

    def test_import_rejects_weak_method_for_physical_construction(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
