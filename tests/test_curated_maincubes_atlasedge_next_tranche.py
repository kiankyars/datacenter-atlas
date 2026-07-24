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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v21.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v21"
BASE_DEFINITION_SHA256 = (
    "4192fb1b2366f5fa86bbcc3ed57037a8c174755454da3b834ea08dadf6ed22f6"
)

MAINCUBES_SOURCE = "curated-official-2026-07-19-maincubes-ber02-mainhub-nauen.json"
ATLASEDGE_SOURCE = "curated-official-2026-07-19-atlasedge-lev002-leverkusen.json"
SOURCE_ORDER = (MAINCUBES_SOURCE, ATLASEDGE_SOURCE)

MAINCUBES_PAGE_EVIDENCE = (
    "maincubes-ber02-current-construction-page-captured-2026-07-19"
)
MAINCUBES_PDF_EVIDENCE = (
    "maincubes-ber02-official-factsheet-captured-2026-07-19"
)
ATLASEDGE_EVIDENCE = (
    "atlasedge-lev002-leverkusen-construction-2026-04-16-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    MAINCUBES_SOURCE: {
        "sha256": "0dd1cf621fd7ffc8d7924fc757fa89c70bcd01101824830c422bc1ec8c216738",
        "retrieved_at": "2026-07-19T20:43:30Z",
        "evidence_keys": (MAINCUBES_PAGE_EVIDENCE, MAINCUBES_PDF_EVIDENCE),
        "campus_key": "curated:maincubes-mainhub-nauen-campus",
        "project_key": "curated:maincubes-mainhub-nauen-campus:ber02",
        "evidence_count": 2,
    },
    ATLASEDGE_SOURCE: {
        "sha256": "33bf4a8515215806d145db703941fbab9c853873801a7bdfc977b18acf3b2a46",
        "retrieved_at": "2026-07-19T20:42:28Z",
        "evidence_keys": (ATLASEDGE_EVIDENCE,),
        "campus_key": "curated:atlasedge-leverkusen-data-center-campus",
        "project_key": "curated:atlasedge-leverkusen-data-center-campus:lev002",
        "evidence_count": 1,
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "cbf094f1a609a272739054b5c5f2f33f5663c9b2d9eee7a0dfa1a5d295f80efb": {
        "body_bytes": 596655,
        "headers_bytes": 509,
        "headers_sha256": "9d7b176dacfa0b5a41b9c7e84784a1e23c7b60bf68f1fa42579d02b4a2a8a340",
        "writeout_bytes": 207,
        "writeout_sha256": "93a56c4bad7b913de628de49781a53fd92e6888aae0952700bd359386734963c",
        "response_date": "2026-07-19T20:42:28Z",
        "last_modified": "2026-07-06T12:24:24Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 84813,
        "url": "https://www.maincubes.com/en/data-centers/berlin-cloud-ai-provider-campus-ber02/",
    },
    "32e7ca51d69ebf49621a17a97f7fb7db4a5d948ec4a88886b6a020e3da4cf43a": {
        "body_bytes": 617422,
        "headers_bytes": 305,
        "headers_sha256": "32d2f98cea5e30460e4c2c9d28e6393b5f11528c47797cb7513c759396e8b7e3",
        "writeout_bytes": 204,
        "writeout_sha256": "56aa694c3a88640b389b52afd661c0141b65a00322e04577e5fc24fa8cfab56b",
        "response_date": "2026-07-19T20:43:30Z",
        "last_modified": "2026-05-18T12:26:30Z",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 617422,
        "download_bytes": 617422,
        "url": "https://www.maincubes.com/wp-content/uploads/2026/02/maincubes_factsheet_ber02_en.pdf",
    },
    "1550ac81d2635484119ef766fcb16726e7e5062994fb61afd71cc327b3f18282": {
        "body_bytes": 79934,
        "headers_bytes": 1885,
        "headers_sha256": "eb0b21d7d611a7100c095b0153a87c31b7a1597e004c1a623fce78b6a6017ff2",
        "writeout_bytes": 221,
        "writeout_sha256": "36b380d033b4eeca3ea7dc24607e45785407c9d9c1eb5b28110ffae689d66e4c",
        "response_date": "2026-07-19T20:42:28Z",
        "last_modified": "2026-07-19T20:42:28Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "download_bytes": 16760,
        "url": "https://atlasedge.com/atlasedge-accelerates-german-growth-with-second-leverkusen-data-centre/",
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


class MaincubesAtlasEdgeNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["content_hash"]]
        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_sha256"])
        self.assertIn(str(capture["writeout_bytes"]), metadata["capture_curl_writeout_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], capture["writeout_sha256"]
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], capture["content_type"])
        self.assertEqual(
            metadata["content_encoding_as_received"], capture["content_encoding"]
        )
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            capture["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertEqual(metadata["http_last_modified_at"], capture["last_modified"])
        self.assertEqual(evidence["source_url"], capture["url"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], capture["url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("no request-start artifact", metadata["retrieval_method"])
        self.assertNotIn("request_started_at", metadata)
        self.assertNotIn("request_start_utc", metadata)
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(
            tuple(row["key"] for row in document["evidence"]),
            expected["evidence_keys"],
        )
        self.assertEqual(
            {row["retrieved_at"] for row in document["evidence"]},
            {expected["retrieved_at"]},
        )
        self.assertTrue(
            all(row["kind"] == "company_disclosure" for row in document["evidence"])
        )
        for evidence in document["evidence"]:
            self._assert_capture(evidence)

        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["campus"]["roles"], {})
        self.assertEqual(document["project"]["roles"], {})
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(len(document["lifecycle"]), 1)
        lifecycle = document["lifecycle"][0]
        self.assertEqual(lifecycle["entity"], "project")
        self.assertEqual(lifecycle["value"], "under_construction")

        if name == MAINCUBES_SOURCE:
            page, pdf = document["evidence"]
            self.assertIsNone(page["published_at"])
            self.assertIsNone(pdf["published_at"])
            self.assertEqual(page["metadata"]["current_status_wording_as_reported"], "Construction")
            self.assertEqual(page["metadata"]["construction_start_as_reported"], "Q1/2026")
            self.assertEqual(pdf["metadata"]["construction_start_as_reported"], "Q1/2026")
            self.assertEqual(pdf["metadata"]["pdf_page_count"], 2)
            self.assertIn("internal creation", pdf["metadata"]["publication_date_scope"])
            for evidence in (page, pdf):
                metadata = evidence["metadata"]
                self.assertEqual(
                    metadata["it_capacity_range_as_reported_mw"],
                    {"low": 144, "high": 186, "qualifier": "depending on the design"},
                )
                self.assertEqual(metadata["design_pue_inequality_as_reported"], "<= 1.2")
                self.assertEqual(metadata["ready_for_service_forecast_as_reported"], "Q1/2028")
                self.assertIn("no midpoint", metadata["capacity_metric_guardrail"].lower())
                self.assertIn("no point estimate", metadata["pue_guardrail"].lower())
                self.assertIn("no normalized workload", metadata["classification_guardrail"])
                self.assertIn("no current consumption", metadata["energy_guardrail"])
                self.assertIn("not normalized", metadata["role_guardrail"])

            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertEqual(entity["country"], "Germany")
                self.assertEqual(
                    entity["address"], "Berliner Strasse, 14641 Nauen, Germany"
                )
                self.assertEqual(
                    entity["coordinates"],
                    {"latitude": 52.5935, "longitude": 12.8929999},
                )
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_site_plan")
                self.assertEqual(entity["confidence"], 0.99)
                self.assertEqual(entity["evidence_key"], MAINCUBES_PDF_EVIDENCE)
                self.assertEqual(entity["as_of_date"], "2026-07-19")
            self.assertEqual(
                lifecycle,
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": MAINCUBES_PAGE_EVIDENCE,
                    "as_of_date": "2026-07-19",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                },
            )
        else:
            evidence = document["evidence"][0]
            metadata = evidence["metadata"]
            self.assertEqual(evidence["published_at"], "2026-04-16")
            self.assertIn(
                "transient edge or session cookie",
                metadata["capture_headers_sensitive_data_guardrail"],
            )
            self.assertEqual(metadata["construction_start_month_as_reported"], "2026-02")
            self.assertEqual(metadata["capacity_as_reported_mw"], 4.4)
            self.assertEqual(metadata["technical_space_as_reported_sqm"], 3400)
            self.assertEqual(metadata["ready_for_service_forecast_as_reported"], "Q2 2027")
            self.assertIn("no normalized capacity", metadata["capacity_metric_guardrail"])
            self.assertIn("no normalized workload", metadata["classification_guardrail"])
            self.assertIn("no current consumption", metadata["energy_guardrail"])
            self.assertIn("no LEV001 entity", metadata["identity_scope"])
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertEqual(entity["country"], "Germany")
                self.assertEqual(entity["address"], "Leverkusen, Germany")
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(entity["confidence"], 0.99)
                self.assertEqual(entity["as_of_date"], "2026-04-16")
            self.assertEqual(
                lifecycle,
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": ATLASEDGE_EVIDENCE,
                    "as_of_date": "2026-04-16",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                },
            )

    def _baseline_paths(self) -> list[Path]:
        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(paths, sorted(paths))
        return paths

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(timestamps), 1)
        return next(iter(timestamps))

    def _semantic_state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(tuple(row) for row in connection.execute(f"SELECT * FROM {table}"))
            )
            for table in SEMANTIC_TABLES
        }

    def _counts(self, state: dict[str, tuple[tuple[Any, ...], ...]]) -> dict[str, int]:
        return {table: len(rows) for table, rows in state.items()}

    def _build_against_v21(
        self, source_order: Iterable[str], *, repeat: bool = False
    ) -> tuple[
        dict[str, tuple[tuple[Any, ...], ...]],
        dict[str, tuple[tuple[Any, ...], ...]],
        dict[str, tuple[int, int]],
    ]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                adapter = CuratedOfficialSourceAdapter()
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for path in self._baseline_paths():
                        adapter.import_file(
                            connection, path, retrieved_at=self._retrieved_at(path)
                        )
                    baseline_state = self._semantic_state(connection)
                    results: dict[str, tuple[int, int]] = {}
                    for name in source_order:
                        result = adapter.import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                        results[name] = (
                            result.entities_created,
                            result.evidence_created,
                        )
                    final_state = self._semantic_state(connection)
                    if repeat:
                        for name in source_order:
                            result = adapter.import_file(
                                connection,
                                ROOT / "sources" / name,
                                retrieved_at=SOURCES[name]["retrieved_at"],
                            )
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                        self.assertEqual(self._semantic_state(connection), final_state)
                self.assertEqual(validate_database(connection), [])
                return baseline_state, final_state, results
            finally:
                connection.close()

    def test_exact_hashes_lineage_semantics_and_v21_collision_absence(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        baseline_text = BASE_DEFINITION.read_text(encoding="utf-8")
        for name, expected in SOURCES.items():
            source_path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                expected["sha256"],
            )
            self.assertNotIn(name, baseline_text)
            self.assertNotIn(expected["campus_key"], baseline_text)
            self.assertNotIn(expected["project_key"], baseline_text)
            self._assert_document(name, self._load(name))

        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            released_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            released_hashes = {row["content_hash"] for row in csv.DictReader(stream)}
        self.assertTrue(
            {
                expected[key]
                for expected in SOURCES.values()
                for key in ("campus_key", "project_key")
            }.isdisjoint(released_keys)
        )
        self.assertTrue(set(CAPTURES).isdisjoint(released_hashes))

    def test_forward_reverse_and_repeat_imports_are_semantically_identical(self) -> None:
        baseline, forward, forward_results = self._build_against_v21(
            SOURCE_ORDER, repeat=True
        )
        reverse_baseline, reverse, reverse_results = self._build_against_v21(
            reversed(SOURCE_ORDER)
        )
        self.assertEqual(reverse_baseline, baseline)
        self.assertEqual(reverse, forward)
        expected_results = {
            name: (2, expected["evidence_count"])
            for name, expected in SOURCES.items()
        }
        self.assertEqual(forward_results, expected_results)
        self.assertEqual(reverse_results, expected_results)

        baseline_counts = self._counts(baseline)
        final_counts = self._counts(forward)
        expected_deltas = {
            "evidence": 3,
            "entities": 4,
            "campuses": 2,
            "facilities": 0,
            "buildings": 0,
            "projects": 2,
            "administrative_assignments": 0,
            "entity_snapshots": 4,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        self.assertEqual(
            {
                table: final_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            expected_deltas,
        )

    def test_standalone_combined_import_has_exact_narrow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name in SOURCE_ORDER:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT status, COUNT(*) FROM lifecycle_observations "
                            "GROUP BY status ORDER BY status"
                        )
                    ],
                    [("under_construction", 2)],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
                    4,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
                    ).fetchone()[0],
                    2,
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, latitude, longitude, method "
                            "FROM entity_snapshots JOIN entities "
                            "ON entities.id = entity_snapshots.entity_id "
                            "WHERE latitude IS NOT NULL ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        (
                            "curated:maincubes-mainhub-nauen-campus",
                            52.5935,
                            12.8929999,
                            "authoritative_site_plan",
                        ),
                        (
                            "curated:maincubes-mainhub-nauen-campus:ber02",
                            52.5935,
                            12.8929999,
                            "authoritative_site_plan",
                        ),
                    ],
                )
                for table in (
                    "capacity_estimates",
                    "workload_observations",
                    "operating_model_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                    )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        maincubes = self._load(MAINCUBES_SOURCE)
        atlasedge = self._load(ATLASEDGE_SOURCE)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(maincubes)
        mutated["capacities"] = [{"forbidden": "design range has no base point"}]
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["capacities"] = [{"forbidden": "design PUE inequality is not a point"}]
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["workloads"] = [{"forbidden": "future AI capability is not workload"}]
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["operating_models"] = [{"forbidden": "customer wording is not a model"}]
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["campus"]["roles"] = {"operator": ["maincubes"]}
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["project"]["method"] = "analyst_geolocation"
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(maincubes)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append((MAINCUBES_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["capacities"] = [{"forbidden": "4.4 MW metric is untyped"}]
        mutations.append((ATLASEDGE_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["workloads"] = [{"forbidden": "AI-ready is design capability"}]
        mutations.append((ATLASEDGE_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["operating_models"] = [{"forbidden": "no model is stated"}]
        mutations.append((ATLASEDGE_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["project"]["coordinates"] = {
            "latitude": 51.0,
            "longitude": 7.0,
        }
        mutations.append((ATLASEDGE_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["project"]["roles"] = {"operator": ["AtlasEdge"]}
        mutations.append((ATLASEDGE_SOURCE, mutated))

        mutated = copy.deepcopy(atlasedge)
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((ATLASEDGE_SOURCE, mutated))

        for name, mutation in mutations:
            with self.subTest(name=name, mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, mutation)


if __name__ == "__main__":
    unittest.main()
