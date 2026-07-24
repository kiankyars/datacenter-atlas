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
SOURCE_NAME = "curated-official-2026-07-20-ascenty-sumare-3.json"
SOURCE_PATH = ROOT / "sources" / SOURCE_NAME
SOURCE_SHA256 = "000f59a93f94dc9a3e3dc87cb357506e4df036f12eaf42ebbd009ca1e766626d"
SOURCE_BYTES = 25_560
RETRIEVED_AT = "2026-07-20T07:24:40Z"

CAMPUS_KEY = "curated:ascenty-sumare-campus"
PROJECT_KEY = "curated:ascenty-sumare-campus:sumare-3"
CURRENT_KEY = (
    "ascenty-sumare-3-current-construction-2026-05-28-"
    "captured-2026-07-20"
)
EXPANSION_KEY = (
    "ascenty-brazil-expansion-aggregate-2026-06-22-captured-2026-07-20"
)
CURRENT_FACTSHEET_KEY = (
    "ascenty-sumare-campus-factsheet-2025-captured-2026-07-20"
)
LEGACY_FACTSHEET_KEY = (
    "ascenty-sumare-campus-legacy-factsheet-2023-captured-2026-07-20"
)

CAPTURES: dict[str, dict[str, Any]] = {
    CURRENT_KEY: {
        "url": (
            "https://pt.linkedin.com/posts/chris-torto_ascenty-datacenter-"
            "ia-activity-7465819505873702912-8_Vq"
        ),
        "publisher": "Christopher Torto",
        "source_family": "ascenty_executive_linkedin_posts",
        "published_at": "2026-05-28T17:41:18.403Z",
        "body_bytes": 168_359,
        "body_sha256": (
            "acd61b9d54243625b7221cabf6a13b2fe4a0c649cd55b6829b95a6ddb3a2406c"
        ),
        "header_bytes": 5_238,
        "header_sha256": (
            "0e901fbc5a5742c2d77d8ae018e02d7930252b0cf633e09505c09f9a05dee34e"
        ),
        "writeout_bytes": 18_878,
        "writeout_sha256": (
            "19790deba11b727cb794fa8ba1768f3676a738969cdca22987b68e5a50351740"
        ),
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "response_bytes": 20_593,
        "http_date": "2026-07-20T07:23:36Z",
        "last_modified": None,
    },
    EXPANSION_KEY: {
        "url": (
            "https://www.linkedin.com/posts/ascenty_ascenty-announces-a-new-and-"
            "historic-expansion-activity-7474929343031537664-Yjgb"
        ),
        "publisher": "Ascenty",
        "source_family": "ascenty_linkedin_company_posts",
        "published_at": "2026-06-22T21:00:32.829Z",
        "body_bytes": 279_631,
        "body_sha256": (
            "5f146517ab098ce21a0f5e2f4e2d28952a4256cae888e34c208afc264e217835"
        ),
        "header_bytes": 5_348,
        "header_sha256": (
            "7b9ba490118673cb2e55ed33725742d16446787ac41d553ad747527b8df3603e"
        ),
        "writeout_bytes": 17_746,
        "writeout_sha256": (
            "4be9523d595693f50c4e6b27f8cd58f891950eb5568d7ce9b6c0595d962f94b9"
        ),
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "response_bytes": 31_810,
        "http_date": "2026-07-20T07:23:35Z",
        "last_modified": None,
    },
    CURRENT_FACTSHEET_KEY: {
        "url": (
            "https://ascenty.com/wp-content/uploads/2025/02/"
            "EN-Campus-Sumare_compressed.pdf"
        ),
        "publisher": "Ascenty",
        "source_family": "ascenty_data_center_factsheets",
        "published_at": None,
        "body_bytes": 414_550,
        "body_sha256": (
            "cfbab8f65d249d10cbf88cdb75ff38bf16605e879417fb9674da53b1ecf033c1"
        ),
        "header_bytes": 1_356,
        "header_sha256": (
            "4f5a0639432c89f27a96c158d131a91425850d7abf24e5c7ec71096fe9b132f6"
        ),
        "writeout_bytes": 15_176,
        "writeout_sha256": (
            "a6db203156edf3f66f8b80c668876d58190fe968022651d67b56b1a40945a905"
        ),
        "content_type": "application/pdf",
        "content_encoding": None,
        "response_bytes": 414_550,
        "http_date": "2026-07-20T07:23:36Z",
        "last_modified": "2025-02-06T16:32:31Z",
    },
    LEGACY_FACTSHEET_KEY: {
        "url": (
            "https://ascenty.com/wp-content/uploads/2023/01/"
            "Folder_Ascenty-Campus-Sumare-EN.pdf"
        ),
        "publisher": "Ascenty",
        "source_family": "ascenty_data_center_factsheets",
        "published_at": None,
        "body_bytes": 527_266,
        "body_sha256": (
            "f4d494dcee8eec4d311101af6d91baa0c9bd7477d6f4efe8acb8ac632b53dc56"
        ),
        "header_bytes": 1_356,
        "header_sha256": (
            "e0586c5ea47d17aa5213412c8c229e28161693ab23c8747a79361f86d4862750"
        ),
        "writeout_bytes": 15_199,
        "writeout_sha256": (
            "24cc87486bba6ba0f413c5d8de822182b8f23c8c953fb743322cf10b9b1dfbfa"
        ),
        "content_type": "application/pdf",
        "content_encoding": None,
        "response_bytes": 527_266,
        "http_date": RETRIEVED_AT,
        "last_modified": "2023-01-17T14:55:19Z",
    },
}


class AscentySumare3CuratedTests(unittest.TestCase):
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
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            SOURCE_PATH,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
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
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 4)

    def test_capture_quads_are_exact_closed_and_zero_redirect(self) -> None:
        evidence = {item["key"]: item for item in self._load()["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))

        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["publisher"], expected["publisher"])
                self.assertEqual(item["source_family"], expected["source_family"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte', metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f'{expected["header_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
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
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["content_encoding_as_received"],
                    expected["content_encoding"],
                )
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["response_bytes"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["response_bytes"],
                )
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(item["source_url"], expected["url"])
                for field in ("requested_url", "effective_url", "canonical_url"):
                    self.assertEqual(metadata[field], expected["url"])

    def test_scope_is_one_sumare_campus_one_sumare_3_project(self) -> None:
        document = self._load()
        campus = document["campus"]
        project = document["project"]
        self.assertEqual(campus["stable_key"], CAMPUS_KEY)
        self.assertEqual(project["stable_key"], PROJECT_KEY)
        self.assertEqual(campus["name"], "Ascenty Sumaré Campus")
        self.assertEqual(project["name"], "Ascenty Sumaré 3")
        for entity in (campus, project):
            self.assertEqual(entity["country"], "Brazil")
            self.assertEqual(entity["address"], "Sumaré, Brazil")
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], CURRENT_KEY)
            self.assertEqual(entity["as_of_date"], "2026-05-28")
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)

        current = document["evidence"][0]["metadata"]
        self.assertIn("only individually named", current["identity_scope"])
        self.assertIn("does not create or infer", current["identity_scope"])
        self.assertIn("no street address", current["locality_guardrail"])

    def test_current_named_disclosure_supports_generic_construction_only(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CURRENT_KEY,
                    "as_of_date": "2026-05-28",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        current = {item["key"]: item for item in document["evidence"]}[
            CURRENT_KEY
        ]["metadata"]
        self.assertIn("Estamos construindo", current["construction_wording_as_reported"])
        self.assertIn("Sumaré 3", current["construction_wording_as_reported"])
        self.assertIn("no exact construction-start date", current["status_scope"])
        for unsupported in (
            "site preparation",
            "foundations",
            "shell",
            "MEP",
            "energization",
            "commissioning",
            "operation",
        ):
            self.assertIn(unsupported, current["status_scope"])

    def test_all_mw_figures_remain_dated_scope_specific_metadata(self) -> None:
        document = self._load()
        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        expansion = evidence[EXPANSION_KEY]
        current_factsheet = evidence[CURRENT_FACTSHEET_KEY]
        legacy_factsheet = evidence[LEGACY_FACTSHEET_KEY]

        self.assertEqual(expansion["reported_new_projects_aggregate_mw"], 150)
        self.assertIn("does not name", expansion["aggregate_capacity_guardrail"])
        self.assertIn("remains metadata only", expansion["aggregate_capacity_guardrail"])

        self.assertEqual(current_factsheet["reported_campus_total_energy_mw"], 91)
        self.assertEqual(current_factsheet["reported_campus_data_center_count"], 5)
        self.assertIn("untyped", current_factsheet["campus_capacity_guardrail"])
        self.assertIn("not allocated to Sumaré 3", current_factsheet["campus_capacity_guardrail"])

        self.assertEqual(legacy_factsheet["reported_sumare_3_total_energy_mw"], 20)
        self.assertEqual(
            legacy_factsheet["reported_sumare_3_historical_status"],
            "Under construction",
        )
        self.assertIn("historical context only", legacy_factsheet["historical_status_guardrail"])
        self.assertIn("remains metadata only", legacy_factsheet["legacy_capacity_guardrail"])

        for metadata in (current_factsheet, legacy_factsheet):
            reconciliation = metadata["reconciliation_guardrail"]
            self.assertIn("91 MW", reconciliation)
            self.assertIn("20 MW", reconciliation)
            self.assertIn("150 MW", reconciliation)
        self.assertEqual(document["capacities"], [])

    def test_ai_portfolio_and_authorship_language_create_no_classification_or_roles(self) -> None:
        document = self._load()
        evidence = {item["key"]: item["metadata"] for item in document["evidence"]}
        self.assertIn("no normalized workload", evidence[CURRENT_KEY]["classification_guardrail"])
        self.assertIn("no normalized owner", evidence[CURRENT_KEY]["role_guardrail"])
        self.assertEqual(
            evidence[EXPANSION_KEY]["reported_portfolio_operates_and_builds_data_centers"],
            40,
        )
        self.assertIn("creates no additional", evidence[EXPANSION_KEY]["portfolio_count_guardrail"])
        self.assertIn("No tenant", evidence[EXPANSION_KEY]["prelease_guardrail"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["campus"]["roles"], {})
        self.assertEqual(document["project"]["roles"], {})

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
        for row in snapshots:
            self.assertEqual(
                json.loads(row[2]),
                {
                    "address": "Sumaré, Brazil",
                    "country": "Brazil",
                    "source_dataset": "curated_official_sources",
                },
            )
        self.assertEqual({row[3] for row in snapshots}, {None})
        self.assertEqual({row[4] for row in snapshots}, {None})
        self.assertEqual({row[5] for row in snapshots}, {None})
        self.assertEqual({row[6] for row in snapshots}, {"2026-05-28"})
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual({row[8] for row in snapshots}, {"authoritative_locality"})
        self.assertEqual(
            lifecycle,
            (
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-05-28",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            ),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(capacities, ())
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())


if __name__ == "__main__":
    unittest.main()
