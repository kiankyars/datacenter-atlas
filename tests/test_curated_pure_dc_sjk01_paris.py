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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v22.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v22"
BASE_DEFINITION_SHA256 = (
    "00e22edf84e73913c3e98f72b47a1f5c4a7bd792c0fd558b2cc2a48d95fd8b84"
)
BASE_MANIFEST_SHA256 = (
    "21f0d4b98f01573fe7f9f4a5bc4dc0e2b2595d57863bfc349bd101e5b0bf2316"
)

SJK_SOURCE = "curated-official-2026-07-19-pure-dc-sjk01-seinajoki-phase-1.json"
PARIS_SOURCE = "curated-official-2026-07-19-pure-dc-segro-paris-jv.json"
SOURCE_ORDER = (SJK_SOURCE, PARIS_SOURCE)

SOURCES: dict[str, dict[str, Any]] = {
    SJK_SOURCE: {
        "sha256": "db055b08c3ab7f632662002877ee209908b6c944fb11350f0c149d77cef0d381",
        "evidence_key": (
            "pure-dc-sjk01-seinajoki-launch-2026-07-14-captured-2026-07-19"
        ),
        "published_at": "2026-07-14",
        "retrieved_at": "2026-07-19T20:45:08Z",
        "country": "Finland",
        "address": "Seinäjoki, Finland",
        "campus_key": "curated:pure-dc-sjk01-seinajoki-campus",
        "campus_name": "Pure DC SJK01 Seinäjoki Campus",
        "project_key": "curated:pure-dc-sjk01-seinajoki-campus:phase-1",
        "project_name": "Pure DC SJK01 Phase 1",
        "lifecycle": "permitted",
        "lifecycle_method": "authoritative_status_update",
    },
    PARIS_SOURCE: {
        "sha256": "a24e990ec4f0bf54d9784a22c9b6c7108f8916dfb9543070da73bc4fa511bb8d",
        "evidence_key": "pure-dc-segro-paris-jv-2026-07-08-captured-2026-07-19",
        "published_at": "2026-07-08",
        "retrieved_at": "2026-07-19T20:45:08Z",
        "country": "France",
        "address": "Paris Availability Zone, France",
        "campus_key": "curated:pure-dc-segro-paris-data-centre-campus",
        "campus_name": "Pure DC SEGRO Paris Data Centre Campus",
        "project_key": (
            "curated:pure-dc-segro-paris-data-centre-campus:current-jv-development"
        ),
        "project_name": "Pure DC SEGRO Paris Data Centre Development",
        "lifecycle": "proposed",
        "lifecycle_method": "authoritative_announcement",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    SJK_SOURCE: {
        "body_bytes": 94024,
        "content_hash": (
            "1f61e2fb8dd238bd664fe0c0c4d90e00d2130852aba54167360bbe611abb78a4"
        ),
        "headers_bytes": 850,
        "headers_hash": (
            "32334b621f9b51afea4aac21adf5d437269c60d4b205f72f7174da5d3ce5ae0a"
        ),
        "writeout_bytes": 229,
        "writeout_hash": (
            "5f66e51929df32926c4a28d8cb2c138387547421914bf81220c5bf5abc3c9c46"
        ),
        "download_bytes": 23504,
        "url": (
            "https://puredc.com/2026/07/14/"
            "pure-dc-launches-one-of-europes-largest-ever-ai-infrastructure-projects"
        ),
    },
    PARIS_SOURCE: {
        "body_bytes": 90584,
        "content_hash": (
            "e4a11055ff24151095727e946e4b47faf6c27853d3cef57151409b86ec6249ab"
        ),
        "headers_bytes": 849,
        "headers_hash": (
            "7fb1f2842aca0d2f86003c406f07c8c3e8646637d941dc052b5824012596437c"
        ),
        "writeout_bytes": 275,
        "writeout_hash": (
            "ce365c165a03e471318b35eb107a6d386c0ef7d60690e22612240d4c4cb4b40d"
        ),
        "download_bytes": 22517,
        "url": (
            "https://puredc.com/2026/07/08/segro-plc-and-pure-data-centres-"
            "group-announce-second-joint-venture-to-develop-48mw-fully-fitted-"
            "data-centre-in-paris"
        ),
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


class PureDcSjk01ParisTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, name: str, evidence: dict[str, Any]) -> None:
        expected = SOURCES[name]
        capture = CAPTURES[name]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["url"])
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], expected["retrieved_at"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_hash"])
        self.assertIn(
            str(capture["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], capture["writeout_hash"]
        )
        self.assertIn(
            "transient edge or session cookie",
            metadata["capture_headers_sensitive_data_guardrail"],
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertIn("no cookie or token value", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], "2026-07-19T20:45:08Z")
        self.assertIsNone(metadata["http_last_modified_at"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], capture["url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("no request-start artifact", metadata["retrieval_method"])
        self.assertIn("exact response HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("all-rights-reserved", evidence["license"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No publisher photograph", metadata["imagery_guardrail"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
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
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], expected["evidence_key"])
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Pure DC")
        self.assertEqual(evidence["source_family"], "pure_dc_news")
        self._assert_capture(name, evidence)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["evidence_key"])
            self.assertEqual(entity["as_of_date"], expected["published_at"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": expected["lifecycle"],
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": expected["published_at"],
                    "method": expected["lifecycle_method"],
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])

        metadata = evidence["metadata"]
        if name == SJK_SOURCE:
            self.assertEqual(document["capacities"], [])
            self.assertEqual(
                document["workloads"],
                [
                    {
                        "entity": "project",
                        "value": "ai_specialized_unspecified",
                        "evidence_key": expected["evidence_key"],
                        "as_of_date": "2026-07-14",
                        "method": "company_disclosure",
                        "confidence": 0.99,
                    }
                ],
            )
            self.assertEqual(
                metadata["phase_1_capacity_wording_as_reported"], "110MW AI campus"
            )
            self.assertEqual(
                metadata["full_campus_it_capacity_wording_as_reported"],
                "over 550MW of IT capacity",
            )
            self.assertEqual(
                metadata["renewable_power_access_wording_as_reported"],
                "more than 700MVA of renewable power",
            )
            self.assertEqual(
                metadata["module_capacity_wording_as_reported"],
                "repeatable 40MW 'AI-ready' modules",
            )
            self.assertIn("110 MW figure is not identified", metadata["capacity_metric_guardrail"])
            self.assertIn("open lower bound", metadata["capacity_metric_guardrail"])
            self.assertIn("MVA", metadata["capacity_metric_guardrail"])
            self.assertIn("supports one permitted", metadata["status_scope"])
            self.assertIn("does not explicitly say", metadata["status_scope"])
            self.assertIn("substation", metadata["substation_guardrail"])
            self.assertIn("not transferred", metadata["substation_guardrail"])
            self.assertIn("only ai_specialized_unspecified", metadata["workload_scope"])
        else:
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["capacities"]), 1)
            capacity = document["capacities"][0]
            self.assertEqual(
                {
                    key: capacity[key]
                    for key in (
                        "entity",
                        "metric",
                        "stage",
                        "unit",
                        "low",
                        "base",
                        "high",
                        "method",
                        "confidence",
                        "evidence_key",
                        "as_of_date",
                        "target_date",
                    )
                },
                {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 48,
                    "base": 48,
                    "high": 48,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": "2026-07-08",
                    "target_date": None,
                },
            )
            self.assertEqual(metadata["planned_it_load_as_reported_mw"], 48)
            self.assertEqual(metadata["presecured_power_capacity_as_reported_mva"], 75)
            self.assertIn("one proposed project", metadata["status_scope"])
            self.assertIn("expressly conditional", metadata["status_scope"])
            self.assertIn("not this Paris development", metadata["cross_project_guardrail"])
            self.assertIn("MVA is not converted to MW", metadata["power_metric_guardrail"])
            self.assertIn(
                "do not identify a committed Paris occupier",
                metadata["tenant_and_model_guardrail"],
            )
            self.assertIn("operating model", metadata["tenant_and_model_guardrail"])

    def _base_paths(self) -> list[Path]:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(len(paths), 122)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        return paths

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {item["retrieved_at"] for item in document["evidence"]}
        self.assertEqual(len(timestamps), 1)
        return next(iter(timestamps))

    def _import(self, connection: Any, path: Path) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            path,
            retrieved_at=self._retrieved_at(path),
        )

    def _semantic_state(
        self, connection: Any
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _counts(self, state: dict[str, tuple[tuple[Any, ...], ...]]) -> dict[str, int]:
        return {table: len(rows) for table, rows in state.items()}

    def _build(
        self,
        source_order: Iterable[str],
        *,
        base_first: bool,
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                adapter = CuratedOfficialSourceAdapter()
                results: dict[str, tuple[int, int]] = {}
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    if base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                    for name in source_order:
                        result = self._import(connection, ROOT / "sources" / name)
                        results[name] = (
                            result.entities_created,
                            result.evidence_created,
                        )
                    if not base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                    final_state = self._semantic_state(connection)
                    for name in SOURCE_ORDER:
                        result = self._import(connection, ROOT / "sources" / name)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._semantic_state(connection), final_state)
                self.assertEqual(validate_database(connection), [])
                return final_state, results
            finally:
                connection.close()

    def _baseline_state(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
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
                    for path in self._base_paths():
                        self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection)
            finally:
                connection.close()

    def test_exact_hashes_raw_closure_schema_and_v22_collision_absence(self) -> None:
        baseline_text = BASE_DEFINITION.read_text(encoding="utf-8")
        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            baseline_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            baseline_hashes = {row["content_hash"] for row in csv.DictReader(stream)}

        new_keys: set[str] = set()
        new_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            self.assertNotIn(name, baseline_text)
            self.assertNotIn(expected["campus_key"], baseline_text)
            self.assertNotIn(expected["project_key"], baseline_text)
            new_keys.update((expected["campus_key"], expected["project_key"]))
            new_hashes.add(CAPTURES[name]["content_hash"])
            self._assert_document(name, self._load(name))

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with patch.object(
                        socket, "socket", side_effect=AssertionError("network used")
                    ), patch.object(
                        socket,
                        "create_connection",
                        side_effect=AssertionError("network used"),
                    ):
                        result = self._import(connection, path)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        self.assertTrue(new_keys.isdisjoint(baseline_keys))
        self.assertTrue(new_hashes.isdisjoint(baseline_hashes))

    def test_forward_reverse_base_order_and_idempotence_are_complete_state_equal(
        self,
    ) -> None:
        baseline_state = self._baseline_state()
        scenarios = [
            self._build(SOURCE_ORDER, base_first=True),
            self._build(reversed(SOURCE_ORDER), base_first=True),
            self._build(SOURCE_ORDER, base_first=False),
            self._build(reversed(SOURCE_ORDER), base_first=False),
        ]
        expected_results = {name: (2, 1) for name in SOURCE_ORDER}
        reference_state = scenarios[0][0]
        for state, results in scenarios:
            self.assertEqual(state, reference_state)
            self.assertEqual(results, expected_results)

        baseline_counts = self._counts(baseline_state)
        final_counts = self._counts(reference_state)
        self.assertEqual(
            {
                table: final_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            {
                "evidence": 2,
                "entities": 4,
                "campuses": 2,
                "facilities": 0,
                "buildings": 0,
                "projects": 2,
                "administrative_assignments": 0,
                "entity_snapshots": 4,
                "lifecycle_observations": 2,
                "operating_model_observations": 0,
                "workload_observations": 1,
                "capacity_estimates": 1,
            },
        )

    def test_combined_import_has_exact_narrow_rows(self) -> None:
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
                        self._import(connection, ROOT / "sources" / name)

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT status, method FROM lifecycle_observations ORDER BY status"
                    )],
                    [
                        ("permitted", "authoritative_status_update"),
                        ("proposed", "authoritative_announcement"),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, workload FROM workload_observations "
                        "JOIN entities ON entities.id = workload_observations.entity_id"
                    )],
                    [
                        (
                            SOURCES[SJK_SOURCE]["project_key"],
                            "ai_specialized_unspecified",
                        )
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, metric, stage, unit, low, base, high "
                        "FROM capacity_estimates JOIN entities "
                        "ON entities.id = capacity_estimates.entity_id"
                    )],
                    [
                        (
                            SOURCES[PARIS_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            "MW",
                            48.0,
                            48.0,
                            48.0,
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        sjk = self._load(SJK_SOURCE)
        paris = self._load(PARIS_SOURCE)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(sjk)
        mutated["lifecycle"][0]["value"] = "under_construction"
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["capacities"] = [{"forbidden": "110 MW is untyped"}]
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["capacities"] = [{"forbidden": "over 550 MW is open-ended"}]
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["capacities"] = [{"forbidden": "MVA is not MW"}]
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["workloads"][0]["value"] = "ai_training"
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["project"]["roles"] = {"operator": ["Pure DC"]}
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(sjk)
        mutated["project"]["coordinates"] = {"latitude": 62.8, "longitude": 22.8}
        mutations.append((SJK_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["lifecycle"][0]["value"] = "under_construction"
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["capacities"][0]["entity"] = "campus"
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["capacities"][0]["metric"] = "grid_connection_mw"
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["capacities"].append({"forbidden": "75 MVA is not 75 MW"})
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["workloads"] = [{"forbidden": "target hyperscaler is not workload"}]
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["operating_models"] = [
            {"forbidden": "conditional pre-let is not operating model"}
        ]
        mutations.append((PARIS_SOURCE, mutated))

        mutated = copy.deepcopy(paris)
        mutated["campus"]["roles"] = {"owner": ["SEGRO", "Pure DC"]}
        mutations.append((PARIS_SOURCE, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
