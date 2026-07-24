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
SOURCE_NAME = "curated-official-2026-07-20-stack-stafford-first-topout.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 30_947
SOURCE_SHA256 = "76a344cb2138728572ec12789df5b6bc9d4bfc509e32664ebc15e294b3003602"
RETRIEVED_AT = "2026-07-20T08:50:35Z"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"

CAMPUS_KEY = "curated:stack-stafford-technology-campus"
PROJECT_KEY = (
    "curated:stack-stafford-technology-campus:first-topped-out-data-center"
)
LINKEDIN_KEY = (
    "stack-stafford-first-topout-linkedin-2026-05-21-captured-2026-07-20"
)
RELEASE_HTML_KEY = (
    "stack-stafford-campus-release-html-2025-01-16-captured-2026-07-20"
)
RELEASE_PDF_KEY = (
    "stack-stafford-campus-release-pdf-2025-01-16-captured-2026-07-20"
)
LOCATION_KEY = "stack-stafford-stc-location-page-captured-2026-07-20"

LINKEDIN_URL = (
    "https://www.linkedin.com/posts/stackinfrastructure_"
    "stack-celebrates-topping-out-ceremony-in-activity-7463196988604461056-V9oA"
)
RELEASE_HTML_URL = (
    "https://www.stackinfra.com/about/news-press/press-releases/"
    "stack-infrastructure-announces-landmark-1gw-stafford-technology-campus-"
    "in-northern-virginia/"
)
RELEASE_PDF_URL = (
    "https://www.stackinfra.com/wp-content/uploads/2025/04/"
    "PR-STACK-Infrastructure-Announces-Landmark-1GW-Stafford-Technology-"
    "Campus-in-Northern-Virginia.pdf"
)
LOCATION_URL = (
    "https://www.stackinfra.com/locations/americas/northern-virginia/stc/"
)

CAPTURES: dict[str, dict[str, Any]] = {
    LINKEDIN_KEY: {
        "kind": "company_disclosure",
        "publisher": "STACK Infrastructure",
        "source_family": "stack_infrastructure_linkedin_company_posts",
        "published_at": "2026-05-21T12:00:21.553Z",
        "url": LINKEDIN_URL,
        "body_bytes": 129_184,
        "body_sha256": (
            "07397de3ef6107b000e29672f52fc5ace0fdfc8f93c992bc700f0bb7c3b31ddc"
        ),
        "header_bytes": 5_616,
        "header_sha256": (
            "caa2106948180d80fdbfc3fb98349fbca8bf382b292b6868a5efd9e99cd6033d"
        ),
        "writeout_bytes": 17_768,
        "writeout_sha256": (
            "70ea3238072ec94b68a9c10a3f77f1daea0a185dbf13fc3ac8325298fae08a1b"
        ),
        "download_bytes": 19_250,
        "header_count": 29,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": 19_250,
        "http_date": "2026-07-20T08:46:56Z",
        "last_modified": None,
    },
    RELEASE_HTML_KEY: {
        "kind": "company_disclosure",
        "publisher": "STACK Infrastructure",
        "source_family": "stack_infrastructure_press_releases",
        "published_at": "2025-01-16",
        "url": RELEASE_HTML_URL,
        "body_bytes": 72_754,
        "body_sha256": (
            "f80eafe3beb643df2afe0371e8462aa4231e5b2be9892f7990957c06647bca89"
        ),
        "header_bytes": 1_407,
        "header_sha256": (
            "3b11c5f6b75dc38b6d0988ff68b57be2714fd5ef51982c40a5932488144702c8"
        ),
        "writeout_bytes": 13_117,
        "writeout_sha256": (
            "5f13f01614ed3dde26600abbd0290e68528a31f85c8ad7b0737553ff90d9f4ca"
        ),
        "download_bytes": 14_366,
        "header_count": 24,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "http_date": "2026-07-20T08:46:56Z",
        "last_modified": None,
    },
    RELEASE_PDF_KEY: {
        "kind": "company_disclosure",
        "publisher": "STACK Infrastructure",
        "source_family": "stack_infrastructure_press_release_pdfs",
        "published_at": "2025-01-16",
        "url": RELEASE_PDF_URL,
        "body_bytes": 54_886,
        "body_sha256": (
            "2086e5f7f897e958e509f99c6121172ef79b499cf9a7eccee211f00b645ed2b7"
        ),
        "header_bytes": 746,
        "header_sha256": (
            "fe16956e1e00d903352ffe8cd6b02a4eccdecbd6dce2d6469619f30264d58a07"
        ),
        "writeout_bytes": 13_111,
        "writeout_sha256": (
            "e2eb36378eeb872be37151b422370443545e05d9b451695ccaa00cc0ae1c0156"
        ),
        "download_bytes": 54_886,
        "header_count": 14,
        "http_version": "HTTP/2",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 54_886,
        "http_date": "2026-07-20T08:47:44Z",
        "last_modified": "2025-08-23T09:59:14Z",
    },
    LOCATION_KEY: {
        "kind": "company_disclosure",
        "publisher": "STACK Infrastructure",
        "source_family": "stack_infrastructure_location_pages",
        "published_at": None,
        "url": LOCATION_URL,
        "body_bytes": 66_559,
        "body_sha256": (
            "d9976a8dc79dc8ee0869b68d3d9ccae8e927075eba604c8a5fe78894bb7db9c0"
        ),
        "header_bytes": 1_407,
        "header_sha256": (
            "85d47a8ede132a51b610afa34f4b5f7a807ebdf79f3efcc8dfd59f5b2b047952"
        ),
        "writeout_bytes": 12_786,
        "writeout_sha256": (
            "d9904c47edb6b85be45bae7f78aafd8a65007d92d96dd6cd7a21667fc21c5270"
        ),
        "download_bytes": 12_473,
        "header_count": 24,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "http_date": "2026-07-20T08:50:35Z",
        "last_modified": None,
    },
}


class StackStaffordFirstTopoutCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("STACK Stafford curated import attempted network access")
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
                        self.assertEqual(result.entities_created, 2 if iteration == 0 else 0)
                        self.assertEqual(result.evidence_created, 4 if iteration == 0 else 0)
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
                    "SELECT entities.stable_key, metric, stage, low, base, high "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload FROM workload_observations "
                    "JOIN entities ON entities.id = workload_observations.entity_id",
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
        expected_roles = {
            "developer": ["STACK Infrastructure"],
            "operator": ["STACK Infrastructure"],
        }
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        self.assertEqual(document["campus"]["roles"], expected_roles)
        self.assertEqual(document["project"]["roles"], expected_roles)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(
                entity["address"],
                "Stafford County, Virginia, United States",
            )
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": LINKEDIN_KEY,
                    "as_of_date": "2026-05-21",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

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

    def test_capture_contract_is_exact_closed_and_safe(self) -> None:
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
                self.assertEqual(
                    metadata["http_version_as_received"],
                    expected["http_version"],
                )
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["content_encoding_as_received"],
                    expected["content_encoding"],
                )
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download_bytes"],
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
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertTrue(
                    forbidden_telemetry_keys.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )
                self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
                self.assertIn("whole-second UTC", metadata["retrieved_at_semantics"])

    def test_scope_roles_locality_and_shell_are_exact(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        self.assertEqual(document["campus"]["name"], "STACK Stafford Technology Campus")
        self.assertEqual(
            document["project"]["name"],
            "STACK Stafford Technology Campus First Topped-Out Data Center",
        )
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertEqual(
            metadata[LINKEDIN_KEY]["reported_status_wording"],
            "first topping out at our Stafford Technology Campus",
        )
        self.assertIn("one shell-stage observation", metadata[LINKEDIN_KEY]["physical_scope"])
        self.assertIn(
            "anonymous first-topped-out data center",
            metadata[LINKEDIN_KEY]["project_granularity_guardrail"],
        )
        for unsupported in (
            "building envelope",
            "MEP",
            "energization",
            "commissioning",
            "occupancy",
            "operation",
            "current load",
        ):
            self.assertIn(unsupported, metadata[LINKEDIN_KEY]["physical_scope"])
        self.assertIn("developer and operator", metadata[RELEASE_HTML_KEY]["role_scope"])
        self.assertIn("sole lifecycle evidence", metadata[RELEASE_HTML_KEY]["announcement_guardrail"])

    def test_capacity_energy_topology_and_coordinate_guardrails_are_exact(self) -> None:
        document = self._load()
        self._assert_semantic_contract(document)
        metadata = {item["key"]: item["metadata"] for item in document["evidence"]}
        release = metadata[RELEASE_HTML_KEY]
        location = metadata[LOCATION_KEY]
        self.assertEqual(release["reported_future_campus_capacity"], "1+GW")
        self.assertEqual(location["reported_current_page_capacity"], "1.1GW")
        self.assertEqual(release["reported_substations"], 6)
        self.assertEqual(release["reported_each_substation_mw_untyped"], 300)
        self.assertEqual(
            release["topology_reconciliation_context"],
            {
                "stack_release_and_topout_post_future_data_centers": 19,
                "county_planning_variant_building_count": 20,
                "usace_applicant_public_notice_building_count": 21,
            },
        )
        self.assertIn("no numbered buildings", release["topology_guardrail"])
        self.assertIn("unique-site count", release["topology_guardrail"])
        self.assertEqual(
            release["usace_regulatory_project_area_coordinate_as_reported"],
            {"latitude": 38.388405, "longitude": -77.425135},
        )
        self.assertIn("not normalized", release["coordinate_guardrail"])
        self.assertIn("unique_site_counted remains false", release["coordinate_guardrail"])
        self.assertIn("not summed to 1,800 MW", release["substation_guardrail"])
        self.assertIn("not added", release["substation_guardrail"])
        self.assertIn("not reconciled arithmetically", location["capacity_guardrail"])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        role_types = set(document["campus"]["roles"]) | set(document["project"]["roles"])
        self.assertEqual(role_types, {"developer", "operator"})
        for item in document["evidence"]:
            self.assertIn(
                "no current",
                item["metadata"].get("energy_guardrail", "no current").casefold(),
            )

    def test_pdf_lineage_and_visual_verification_are_closed(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        html = evidence[RELEASE_HTML_KEY]["metadata"]
        pdf = evidence[RELEASE_PDF_KEY]["metadata"]
        self.assertEqual(html["official_pdf_download_url"], RELEASE_PDF_URL)
        self.assertIn("April upload path", html["official_pdf_link_scope"])
        self.assertEqual(pdf["pdf_pages"], 2)
        self.assertEqual(pdf["pdf_version"], "1.7")
        self.assertFalse(pdf["pdf_tagged"])
        self.assertFalse(pdf["pdf_encrypted"])
        self.assertFalse(pdf["pdf_javascript"])
        self.assertEqual(pdf["pdf_page_size"], "612 x 792 points (US Letter)")
        self.assertEqual(
            pdf["extracted_text_sha256"],
            "6ec2dd943c0738388028017b5196428f3cf2325085fbd558ebb065059a844799",
        )
        self.assertIn("Both pages", pdf["pdf_visual_verification"])
        self.assertIn("no OCR", pdf["pdf_visual_verification"])
        self.assertIn("never summed to 1,800 MW", pdf["capacity_and_substation_guardrail"])

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
        self.assertEqual({row[6] for row in snapshots}, {"2025-01-16", "2026-05-21"})
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        for row in snapshots:
            tags = json.loads(row[2])
            self.assertEqual(tags["role:developer"], "STACK Infrastructure")
            self.assertEqual(tags["role:operator"], "STACK Infrastructure")
            self.assertEqual(tags["source_dataset"], "curated_official_sources")
        self.assertEqual(
            lifecycle,
            ((
                PROJECT_KEY,
                "shell",
                "2026-05-21",
                RETRIEVED_AT,
                "authoritative_physical_status_update",
                0.99,
            ),),
        )
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))

    def test_keys_are_collision_free_v44_is_unchanged_and_collision_is_rejected(self) -> None:
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

        collision = copy.deepcopy(self._load())
        collision["project"]["stable_key"] = CAMPUS_KEY
        with self.assertRaisesRegex(ValueError, "stable key is already assigned"):
            self._import_document(collision)

    def test_semantic_leakage_mutations_fail_the_focused_contract(self) -> None:
        original = self._load()
        mutations: list[tuple[str, dict[str, Any]]] = []

        changed = copy.deepcopy(original)
        changed["lifecycle"][0]["value"] = "operational"
        mutations.append(("topout-promoted-to-operation", changed))

        changed = copy.deepcopy(original)
        changed["capacities"] = [
            {
                "entity": "campus",
                "metric": "gross_facility_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 1100,
                "base": 1100,
                "high": 1100,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": LOCATION_KEY,
                "as_of_date": "2026-07-20",
                "target_date": None,
                "notes": "invalid promotion of untyped 1.1 GW",
            }
        ]
        mutations.append(("untyped-campus-gw-promoted", changed))

        changed = copy.deepcopy(original)
        changed["capacities"] = [
            {
                "entity": "campus",
                "metric": "grid_connection_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 1800,
                "base": 1800,
                "high": 1800,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": RELEASE_PDF_KEY,
                "as_of_date": "2025-01-16",
                "target_date": None,
                "notes": "invalid sum of six substation components",
            }
        ]
        mutations.append(("substations-summed-as-grid-load", changed))

        changed = copy.deepcopy(original)
        changed["project"]["coordinates"] = {
            "latitude": 38.388405,
            "longitude": -77.425135,
        }
        mutations.append(("regulatory-project-area-point-promoted", changed))

        changed = copy.deepcopy(original)
        changed["project"]["roles"]["tenant"] = ["Undisclosed Hyperscaler"]
        mutations.append(("tenant-invented", changed))

        changed = copy.deepcopy(original)
        changed["operating_models"] = [
            {
                "entity": "project",
                "value": "hyperscale_lease",
                "evidence_key": RELEASE_HTML_KEY,
                "as_of_date": "2025-01-16",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(("portfolio-language-promoted-to-model", changed))

        changed = copy.deepcopy(original)
        changed["workloads"] = [
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
                "evidence_key": RELEASE_HTML_KEY,
                "as_of_date": "2025-01-16",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(("workload-invented", changed))

        for label, document in mutations:
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                self._assert_semantic_contract(document)

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load())
        document["evidence"][0]["retrieved_at"] = "2026-07-20T08:50:36Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_regulatory_coordinate_as_locality(self) -> None:
        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 38.388405,
            "longitude": -77.425135,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)

    def test_import_rejects_weak_method_for_shell_status(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
