from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
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
SOURCE_NAME = "curated-official-2026-07-20-hut8-beacon-point.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "b6209a4c9ebaefe562b541834c9d89a19482cfd79a4cf7de156df848ed7834f1"
SOURCE_BYTES = 24_978
RETRIEVED_AT = "2026-07-20T07:50:07Z"

CAMPUS_KEY = "curated:hut8-beacon-point-ai-data-center-campus"
PROJECT_KEY = (
    "curated:hut8-beacon-point-ai-data-center-campus:"
    "first-phase-352mw-critical-it-lease"
)
COMMERCIAL_KEY = "hut8-beacon-point-commercialization-2026-05-06-captured-2026-07-20"
NOTES_KEY = "hut8-beacon-point-notes-closing-2026-06-09-captured-2026-07-20"
CAMPUS_PAGE_KEY = "hut8-beacon-point-campus-page-captured-2026-07-20"

SEED_INHERITANCE_FIRST_VERSION = 47
RETAINED_REJECTED_SEED_DEFINITION_SHA256 = {
    50: "6d15ead5b9efe37710d3ed5748cb46655ccfc16b681027ac6e343e26b546194a"
}
PUBLISHED_EVIDENCE_MARKERS = {
    COMMERCIAL_KEY: "6dd83ce5b5b90021f77bcfad2e755722234336a38fb7914e7b3838fcbc4999fb",
    CAMPUS_PAGE_KEY: "15de5c0fcea27fe13063a2143ca66edce4bcf3c23b9154fa5b461bd7739d7279",
}

CAPTURES: dict[str, dict[str, Any]] = {
    COMMERCIAL_KEY: {
        "url": (
            "https://www.hut8.com/news-insights/press-releases/"
            "hut-8-commercializes-first-phase-of-1-gw-beacon-point-ai-data-"
            "center-campus-with-15-year-352-mw"
        ),
        "source_family": "hut8_press_releases",
        "published_at": "2026-05-06T10:30:00.000Z",
        "body_bytes": 155_167,
        "body_sha256": (
            "6dd83ce5b5b90021f77bcfad2e755722234336a38fb7914e7b3838fcbc4999fb"
        ),
        "header_bytes": 340,
        "header_sha256": (
            "3229c0efc42616e4e2ae5b7d394fdedb42321c17b1b666c2da351bfee77bb209"
        ),
        "writeout_bytes": 16_579,
        "writeout_sha256": (
            "25fc9665adf3b9bf04df60e4e48ec5000b26e7e3d592f39f2f2f5eeb090b3f19"
        ),
        "compressed_download_bytes": 31_501,
        "http_date": "2026-07-20T05:36:46Z",
    },
    NOTES_KEY: {
        "url": (
            "https://www.hut8.com/news-insights/press-releases/"
            "hut-8-closes-usd4-25-billion-of-investment-grade-senior-secured-"
            "notes-for-beacon-point-data"
        ),
        "source_family": "hut8_press_releases",
        "published_at": "2026-06-09T22:00:00.000Z",
        "body_bytes": 131_225,
        "body_sha256": (
            "5f78d2248f833344d567aca7005895c2d664bd459248cb763595f4a4b13e3b55"
        ),
        "header_bytes": 339,
        "header_sha256": (
            "6bd25533dc3263ba93f1b1a9b710129114b332d560c873b0bb0d3fb91a06d9d2"
        ),
        "writeout_bytes": 16_558,
        "writeout_sha256": (
            "b1243417f971cdbfc9915c8134b58bad7e88a70857d2131018b646b0d7552349"
        ),
        "compressed_download_bytes": 25_121,
        "http_date": "2026-07-20T04:25:22Z",
    },
    CAMPUS_PAGE_KEY: {
        "url": "https://www.hut8.com/data-centers/beacon-point",
        "source_family": "hut8_data_center_pages",
        "published_at": None,
        "body_bytes": 215_634,
        "body_sha256": (
            "15de5c0fcea27fe13063a2143ca66edce4bcf3c23b9154fa5b461bd7739d7279"
        ),
        "header_bytes": 339,
        "header_sha256": (
            "2bd6ce83836901e69d9cab52256c4fbbc4d08e1b676de13905666bbfbbde52ad"
        ),
        "writeout_bytes": 16_179,
        "writeout_sha256": (
            "2374f17bb06bfc7b6147f993c820013b41103c161a0a0108b18e14cab1eb65fd"
        ),
        "compressed_download_bytes": 37_120,
        "http_date": "2026-07-20T07:33:39Z",
    },
}


class Hut8BeaconPointCuratedTests(unittest.TestCase):
    def _load(self, path: Path = SOURCE_PATH) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

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
                            result.evidence_created, 3 if iteration == 0 else 0
                        )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, "
                    "method, confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY workload",
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
            text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(document["schema_version"], "1.0")
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

    def test_capture_triples_are_exact_closed_and_zero_redirect(self) -> None:
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
                self.assertEqual(item["publisher"], "Hut 8 Corp.")
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['header_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], "text/html;charset=utf-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertIsNone(metadata["http_content_length_bytes_as_received"])
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["compressed_download_bytes"],
                )
                self.assertEqual(
                    metadata["curl_size_header_bytes"], expected["header_bytes"]
                )
                self.assertEqual(metadata["curl_num_headers"], 10)
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertIsNone(metadata["http_last_modified_at"])
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(item["source_url"], expected["url"])
                for field in ("requested_url", "effective_url", "canonical_url"):
                    self.assertEqual(metadata[field], expected["url"])
                self.assertTrue(
                    forbidden_telemetry_keys.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                self.assertIn("whole-second UTC", metadata["retrieved_at_semantics"])

    def test_scope_roles_and_locality_are_narrow_and_authoritative(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Hut 8 Beacon Point AI Data Center Campus")
        self.assertEqual(
            project["name"],
            "Hut 8 Beacon Point First Phase 352 MW Critical IT Lease",
        )
        self.assertEqual(
            campus["roles"],
            {
                "developer": ["Hut 8"],
                "utility": ["AEP Texas"],
            },
        )
        self.assertEqual(project["roles"], {"developer": ["Hut 8"]})
        for entity in (campus, project):
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], "Nueces County, Texas, United States")
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertIn("No street address", evidence[COMMERCIAL_KEY]["location_scope"])
        self.assertIn(
            "no normalized coordinate",
            evidence[CAMPUS_PAGE_KEY]["coordinate_guardrail"],
        )
        self.assertIn("unnamed tenant", evidence[COMMERCIAL_KEY]["role_scope"])
        self.assertIn("create no owner", evidence[COMMERCIAL_KEY]["role_scope"])
        self.assertIn(
            "no additional standardized role", evidence[CAMPUS_PAGE_KEY]["role_scope"]
        )

    def test_public_physical_lifecycle_is_announced_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "announced",
                    "evidence_key": COMMERCIAL_KEY,
                    "as_of_date": "2026-05-06",
                    "method": "authoritative_announcement",
                    "confidence": 0.99,
                }
            ],
        )
        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        commercial = evidence[COMMERCIAL_KEY]
        notes = evidence[NOTES_KEY]
        campus = evidence[CAMPUS_PAGE_KEY]
        self.assertEqual(campus["reported_current_stage_number"], 2)
        self.assertEqual(campus["reported_current_stage_heading"], "Commercialization")
        self.assertEqual(campus["reported_next_stage_number"], 3)
        self.assertEqual(campus["reported_next_stage_heading"], "Construction")
        self.assertIn("to be built", notes["prospective_wording_scope"])
        self.assertIn(
            "financial or program-stage facts only", notes["status_guardrail"]
        )
        self.assertIn(
            "internal Energy Capacity Under Construction", commercial["status_scope"]
        )
        for unsupported in (
            "site preparation",
            "civil works",
            "excavation",
            "foundations",
            "shell",
            "MEP",
            "energization",
            "commissioning",
            "completion",
            "occupancy",
            "operation",
        ):
            self.assertIn(unsupported, commercial["status_scope"])
        self.assertIn(
            "no under_construction", campus["construction_language_guardrail"]
        )
        self.assertIn("site_preparation", campus["construction_language_guardrail"])

    def test_capacity_rows_preserve_metric_scope_and_do_not_double_count(self) -> None:
        document = self._load()
        capacities = document["capacities"]
        self.assertEqual(len(capacities), 2)
        observed = {
            (item["entity"], item["metric"], item["stage"]): (
                item["low"],
                item["base"],
                item["high"],
                item["unit"],
            )
            for item in capacities
        }
        self.assertEqual(
            observed,
            {
                ("project", "critical_it_mw", "contracted"): (352, 352, 352, "MW"),
                ("campus", "grid_connection_mw", "contracted"): (
                    1000,
                    1000,
                    1000,
                    "MW",
                ),
            },
        )
        self.assertTrue(
            all(item["evidence_key"] == COMMERCIAL_KEY for item in capacities)
        )
        self.assertTrue(all(item["as_of_date"] == "2026-05-06" for item in capacities))
        self.assertNotIn(500, [item["base"] for item in capacities])
        self.assertEqual(
            sum(item["metric"] == "critical_it_mw" for item in capacities), 1
        )

        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        commercial = evidence[COMMERCIAL_KEY]
        notes = evidence[NOTES_KEY]
        campus = evidence[CAMPUS_PAGE_KEY]
        self.assertEqual(commercial["reported_leased_critical_it_mw"], 352)
        self.assertEqual(commercial["reported_campus_interconnection_mw"], 1000)
        self.assertEqual(commercial["reported_first_phase_approximate_utility_mw"], 500)
        self.assertEqual(
            commercial[
                "reported_internal_energy_capacity_moved_to_under_construction_mw"
            ],
            500,
        )
        self.assertEqual(
            commercial[
                "reported_internal_energy_capacity_remaining_under_development_mw"
            ],
            500,
        )
        self.assertIn("nested", commercial["nonaggregation_guardrail"])
        self.assertIn("must not be added", commercial["nonaggregation_guardrail"])
        self.assertEqual(notes["reported_combined_critical_it_mw"], 352)
        self.assertEqual(notes["reported_data_hall_count"], 6)
        self.assertTrue(notes["reported_substation_in_scope"])
        self.assertEqual(notes["reported_property_acres_approximate"], 521)
        self.assertEqual(campus["reported_site_footprint_acres"], 525)
        self.assertIn("create no six", notes["hall_scope_guardrail"])
        self.assertIn(
            "neither creates normalized geometry",
            notes["acreage_reconciliation_guardrail"],
        )

    def test_future_operating_model_workloads_and_forecasts_are_exact(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "hyperscale_lease",
                    "evidence_key": COMMERCIAL_KEY,
                    "as_of_date": "2026-05-06",
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
                    "value": "ai_training",
                    "evidence_key": COMMERCIAL_KEY,
                    "as_of_date": "2026-05-06",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                },
                {
                    "entity": "project",
                    "value": "ai_inference",
                    "evidence_key": COMMERCIAL_KEY,
                    "as_of_date": "2026-05-06",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                },
            ],
        )
        commercial = self._load()["evidence"][0]["metadata"]
        self.assertEqual(commercial["reported_lease_term_years"], 15)
        self.assertEqual(
            commercial["reported_initial_energization_forecast"], "Q1 2027"
        )
        self.assertEqual(
            commercial["reported_initial_data_hall_delivery_forecast"], "Q3 2027"
        )
        self.assertIn("intended future project use only", commercial["workload_scope"])
        self.assertIn("future-project", commercial["operating_model_scope"])
        self.assertIn("company forecasts", commercial["timing_guardrail"])

    def test_stable_and_evidence_keys_do_not_collide_with_curated_sources(self) -> None:
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

    @staticmethod
    def _definition_has_exact_hut8_input(document: dict[str, Any]) -> bool:
        rows = document.get("curated_inputs")
        if not isinstance(rows, list):
            raise AssertionError("seed definition curated_inputs must be a list")
        expected = {
            "path": f"sources/{SOURCE_NAME}",
            "sha256": SOURCE_SHA256,
        }
        candidates = [
            row
            for row in rows
            if isinstance(row, dict)
            and (
                row.get("path") == expected["path"]
                or row.get("sha256") == SOURCE_SHA256
                or (isinstance(row.get("path"), str) and SOURCE_NAME in row["path"])
            )
        ]
        if not candidates:
            return False
        if candidates != [expected]:
            raise AssertionError("altered Hut8 curated-input path or hash")
        return True

    @staticmethod
    def _release_has_exact_hut8_markers(document: dict[str, Any]) -> bool:
        rows = document.get("sources")
        if not isinstance(rows, list):
            raise AssertionError("release source_inputs sources must be a list")
        expected_hashes = set(PUBLISHED_EVIDENCE_MARKERS.values())
        candidates: list[tuple[str | None, str | None]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            provenance = row.get("provenance")
            if not isinstance(provenance, dict):
                continue
            key = provenance.get("curated_record_key")
            digest = provenance.get("content_hash")
            if (
                key in PUBLISHED_EVIDENCE_MARKERS
                or digest in expected_hashes
                or (isinstance(key, str) and "hut8-beacon-point" in key)
            ):
                candidates.append((key, digest))
        if not candidates:
            return False
        if (
            len(candidates) != len(PUBLISHED_EVIDENCE_MARKERS)
            or dict(candidates) != PUBLISHED_EVIDENCE_MARKERS
        ):
            raise AssertionError(
                "altered or incomplete Hut8 published evidence markers"
            )
        return True

    @staticmethod
    def _assert_contiguous_inheritance(
        definition_versions: set[int], release_versions: set[int]
    ) -> None:
        if definition_versions != release_versions:
            raise AssertionError("Hut8 definition/release version sets differ")
        if not definition_versions:
            raise AssertionError("Hut8 seed inheritance inventory is empty")
        ordered = sorted(definition_versions)
        if ordered[0] != SEED_INHERITANCE_FIRST_VERSION:
            raise AssertionError("Hut8 seed inheritance must begin at v47")
        expected = list(range(SEED_INHERITANCE_FIRST_VERSION, ordered[-1] + 1))
        if ordered != expected:
            raise AssertionError("Hut8 seed inheritance versions must be contiguous")

    def test_source_inheritance_is_contiguous_from_v47_with_v50_rejected(
        self,
    ) -> None:
        definition_pattern = re.compile(
            r"open-seed-\d{4}-\d{2}-\d{2}-v(?P<version>\d+)\.json"
        )
        release_pattern = re.compile(r"\d{4}-\d{2}-\d{2}-open-seed-v(?P<version>\d+)")
        definitions: dict[int, Path] = {}
        releases: dict[int, Path] = {}

        for path in sorted((ROOT / "sources").glob("open-seed-*-v*.json")):
            match = definition_pattern.fullmatch(path.name)
            if match is None:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if not self._definition_has_exact_hut8_input(document):
                continue
            version = int(match.group("version"))
            if version in definitions:
                raise AssertionError(
                    f"duplicate Hut8 seed definition version: v{version}"
                )
            definitions[version] = path

        for path in sorted(
            (ROOT / "releases").glob("*-open-seed-v*/source_inputs.json")
        ):
            match = release_pattern.fullmatch(path.parent.name)
            if match is None:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if not self._release_has_exact_hut8_markers(document):
                continue
            version = int(match.group("version"))
            if version in releases:
                raise AssertionError(f"duplicate Hut8 seed release version: v{version}")
            releases[version] = path

        self._assert_contiguous_inheritance(set(definitions), set(releases))
        for version, expected_hash in RETAINED_REJECTED_SEED_DEFINITION_SHA256.items():
            self.assertIn(version, definitions)
            self.assertEqual(
                hashlib.sha256(definitions[version].read_bytes()).hexdigest(),
                expected_hash,
            )
        classifications = {
            version: (
                "retained_rejected_seed"
                if version in RETAINED_REJECTED_SEED_DEFINITION_SHA256
                else "inheritance_reference_only"
            )
            for version in definitions
        }
        self.assertEqual(classifications[50], "retained_rejected_seed")
        self.assertNotIn("accepted", set(classifications.values()))

        altered_definition = {
            "curated_inputs": [
                {
                    "path": f"sources/{SOURCE_NAME}",
                    "sha256": "0" * 64,
                }
            ]
        }
        with self.assertRaisesRegex(AssertionError, "altered Hut8 curated-input"):
            self._definition_has_exact_hut8_input(altered_definition)

        altered_release = {
            "sources": [
                {
                    "provenance": {
                        "curated_record_key": COMMERCIAL_KEY,
                        "content_hash": PUBLISHED_EVIDENCE_MARKERS[COMMERCIAL_KEY],
                    }
                }
            ]
        }
        with self.assertRaisesRegex(AssertionError, "published evidence markers"):
            self._release_has_exact_hut8_markers(altered_release)

        with self.assertRaisesRegex(AssertionError, "begin at v47"):
            self._assert_contiguous_inheritance({46, 47}, {46, 47})
        with self.assertRaisesRegex(AssertionError, "must be contiguous"):
            self._assert_contiguous_inheritance({47, 49}, {47, 49})
        with self.assertRaisesRegex(AssertionError, "version sets differ"):
            self._assert_contiguous_inheritance({47, 48}, {47})

    def test_offline_import_is_valid_exact_idempotent_and_order_independent(
        self,
    ) -> None:
        once = self._database_state()
        twice = self._database_state(repetitions=2)
        self.assertEqual(once, twice)

        with tempfile.TemporaryDirectory() as temporary:
            reversed_path = Path(temporary) / SOURCE_NAME
            document = self._load()
            document["evidence"] = list(reversed(document["evidence"]))
            reversed_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reversed_state = self._database_state(reversed_path)
        self.assertEqual(once, reversed_state)

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
        snapshot_by_key = {row[0]: row for row in snapshots}
        self.assertEqual(
            json.loads(snapshot_by_key[CAMPUS_KEY][2]),
            {
                "address": "Nueces County, Texas, United States",
                "country": "United States",
                "role:developer": "Hut 8",
                "role:utility": "AEP Texas",
                "source_dataset": "curated_official_sources",
            },
        )
        self.assertEqual(
            json.loads(snapshot_by_key[PROJECT_KEY][2]),
            {
                "address": "Nueces County, Texas, United States",
                "country": "United States",
                "role:developer": "Hut 8",
                "source_dataset": "curated_official_sources",
            },
        )
        for row in snapshots:
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertEqual(row[7], RETRIEVED_AT)
            self.assertEqual(row[8], "authoritative_locality")
            self.assertEqual(row[9], 0.99)
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "announced",
                    "2026-05-06",
                    RETRIEVED_AT,
                    "authoritative_announcement",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(
            capacities,
            (
                (
                    CAMPUS_KEY,
                    "grid_connection_mw",
                    "contracted",
                    "MW",
                    1000.0,
                    1000.0,
                    1000.0,
                    "2026-05-06",
                    None,
                    RETRIEVED_AT,
                    "reported",
                    0.99,
                ),
                (
                    PROJECT_KEY,
                    "critical_it_mw",
                    "contracted",
                    "MW",
                    352.0,
                    352.0,
                    352.0,
                    "2026-05-06",
                    None,
                    RETRIEVED_AT,
                    "reported",
                    0.99,
                ),
            ),
        )
        self.assertEqual(
            operating_models,
            (
                (
                    PROJECT_KEY,
                    "hyperscale_lease",
                    "2026-05-06",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )
        self.assertEqual(
            workloads,
            (
                (
                    PROJECT_KEY,
                    "ai_inference",
                    "2026-05-06",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
                (
                    PROJECT_KEY,
                    "ai_training",
                    "2026-05-06",
                    RETRIEVED_AT,
                    "company_disclosure",
                    0.99,
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
