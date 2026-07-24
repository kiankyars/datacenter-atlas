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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v30.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v30"
BASE_DEFINITION_SHA256 = (
    "b89c7414fe9a96ddd2acfff766386dda514d61278dae039d1d70eb490340ef12"
)
BASE_MANIFEST_SHA256 = (
    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
)

LT_SOURCE = "curated-official-2026-07-19-lt-vyoma-mahape-data-centre.json"
KEPPEL_SOURCE = (
    "curated-official-2026-07-19-keppel-floating-data-centre-singapore.json"
)
SOURCE_ORDER = (LT_SOURCE, KEPPEL_SOURCE)

LT_EVIDENCE = (
    "lt-vyoma-mahape-groundbreaking-2026-01-21-captured-2026-07-19"
)
KEPPEL_CURRENT_EVIDENCE = (
    "keppel-floating-data-centre-construction-update-2026-04-23-"
    "captured-2026-07-19"
)
KEPPEL_LOCALITY_EVIDENCE = (
    "keppel-floating-data-centre-1h2025-update-2025-07-31-"
    "captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    LT_SOURCE: {
        "sha256": (
            "c2300cb3e2318d0274931ff22d95fb1180640857cb27a5f4a3fe42b254e1ac41"
        ),
        "evidence_count": 1,
        "publisher": "Larsen & Toubro",
        "source_family": "larsen_toubro_press_releases",
        "retrieved_at": "2026-07-19T20:54:52Z",
        "country": "India",
        "address": "Mahape, Navi Mumbai, India",
        "campus_key": "curated:lt-vyoma-mahape-data-centre-campus",
        "campus_name": "L&T Vyoma Mahape Data Centre Campus",
        "project_key": (
            "curated:lt-vyoma-mahape-data-centre-campus:current-facility-build"
        ),
        "project_name": "L&T Vyoma Mahape Current Facility Build",
        "entity_evidence": LT_EVIDENCE,
        "entity_as_of": "2026-01-21",
        "lifecycle_evidence": LT_EVIDENCE,
        "lifecycle_as_of": "2026-01-21",
    },
    KEPPEL_SOURCE: {
        "sha256": (
            "f253e99b499cc59d1644e6a2d7f05e6492ae8f59f519f8e0621ac6c1bbd41307"
        ),
        "evidence_count": 2,
        "publisher": "Keppel",
        "source_family": "keppel_media",
        "retrieved_at": "2026-07-19T20:53:59Z",
        "country": "Singapore",
        "address": "Singapore",
        "campus_key": "curated:keppel-floating-data-centre-singapore",
        "campus_name": "Keppel Floating Data Centre Singapore",
        "project_key": (
            "curated:keppel-floating-data-centre-singapore:current-project"
        ),
        "project_name": "Keppel Floating Data Centre Current Project",
        "entity_evidence": KEPPEL_LOCALITY_EVIDENCE,
        "entity_as_of": "2025-07-31",
        "lifecycle_evidence": KEPPEL_CURRENT_EVIDENCE,
        "lifecycle_as_of": "2026-04-23",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    LT_EVIDENCE: {
        "source": LT_SOURCE,
        "body_bytes": 106341,
        "content_hash": (
            "752202cb9bea8b8816c088a7befea2271b07420129eaa42ed63744e9037a75d6"
        ),
        "headers_bytes": 2318,
        "headers_hash": (
            "36a77ae1f31a1d0180a7fd311b345d1359b9ea8ccaef793fcfa13a8e70ef219c"
        ),
        "writeout_bytes": 14471,
        "writeout_hash": (
            "20e033890696ee330e98f2ae702ab0745f8e2342e3e3a518835b0ce062ab03fd"
        ),
        "download_bytes": 28292,
        "content_type": "text/html; charset=utf-8",
        "response_date": "2026-07-19T20:54:52Z",
        "last_modified": None,
        "published_at": "2026-01-21",
        "url": (
            "https://www.larsentoubro.com/pressreleases/2026/"
            "2026-01-21-larsen-toubro-vyoma-breaks-ground-on-40-mw-green-"
            "ai-ready-data-centre-in-navi-mumbai"
        ),
    },
    KEPPEL_CURRENT_EVIDENCE: {
        "source": KEPPEL_SOURCE,
        "body_bytes": 30517,
        "content_hash": (
            "c4a5db59ac474e4c3624feae85a78677ba0502a19f9f8b9cbbff923977f147f0"
        ),
        "headers_bytes": 687,
        "headers_hash": (
            "7582a7b37cafe58d364c75a39cb2623f3f9406d5a7cdaeed5466c7db8ae3bade"
        ),
        "writeout_bytes": 13850,
        "writeout_hash": (
            "8b6477320567e6a49dd92843de4139b8752e4db8d4814e3417f69454d564c74f"
        ),
        "download_bytes": 8422,
        "content_type": "text/html",
        "response_date": "2026-07-19T20:53:58Z",
        "last_modified": "2026-04-22T23:53:39Z",
        "published_at": "2026-04-23",
        "url": "https://www.keppel.com/media/keppels-business-update-for-1q-2026/",
    },
    KEPPEL_LOCALITY_EVIDENCE: {
        "source": KEPPEL_SOURCE,
        "body_bytes": 28588,
        "content_hash": (
            "cc7562b60f8fe7daeaf98e384b314143e92bea8575e289fe0a9afb9b9461b0b4"
        ),
        "headers_bytes": 694,
        "headers_hash": (
            "460021b96ecc2a06eca32a7abe9283b78fd98dcd4bb22f5cc8c49cbefbf9c364"
        ),
        "writeout_bytes": 13867,
        "writeout_hash": (
            "bce2b15c509e0809f89530830df690367a5cc54a1a9003a3d8debe2857cb1181"
        ),
        "download_bytes": 8209,
        "content_type": "text/html",
        "response_date": "2026-07-19T20:53:59Z",
        "last_modified": "2025-07-30T23:38:10Z",
        "published_at": "2025-07-31",
        "url": (
            "https://www.keppel.com/media/"
            "keppels-financial-results-for-1h-2025/"
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


class LtVyomaKeppelFdcTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _evidence_by_key(
        self, document: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return {row["key"]: row for row in document["evidence"]}

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["key"]]
        source = SOURCES[capture["source"]]
        metadata = evidence["metadata"]

        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], source["publisher"])
        self.assertEqual(evidence["source_family"], source["source_family"])
        self.assertEqual(evidence["published_at"], capture["published_at"])
        self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["url"])
        self.assertEqual(evidence["license"], "all-rights-reserved")

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
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], capture["content_type"])
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertEqual(metadata["http_last_modified_at"], capture["last_modified"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], capture["url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("not redistributed", metadata["rights_scope"])

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
        self.assertEqual(len(document["evidence"]), expected["evidence_count"])
        self.assertEqual(
            {row["key"] for row in document["evidence"]},
            {
                key
                for key, capture in CAPTURES.items()
                if capture["source"] == name
            },
        )
        for row in document["evidence"]:
            self._assert_capture(row)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["entity_evidence"])
            self.assertEqual(entity["as_of_date"], expected["entity_as_of"])
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
                    "value": "under_construction",
                    "evidence_key": expected["lifecycle_evidence"],
                    "as_of_date": expected["lifecycle_as_of"],
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        evidence = self._evidence_by_key(document)
        if name == LT_SOURCE:
            metadata = evidence[LT_EVIDENCE]["metadata"]
            self.assertEqual(
                metadata["construction_wording_as_reported"],
                "Bhoomi Pujan ceremony for its upcoming 40 MW green, AI-ready "
                "data centre at Mahape in Navi Mumbai",
            )
            self.assertEqual(
                metadata["commencement_wording_as_reported"],
                "signals the commencement of a facility",
            )
            self.assertIn("generic under_construction", metadata["status_scope"])
            self.assertEqual(
                metadata["current_facility_scale_wording_as_reported"],
                "upcoming 40 MW green, AI-ready data centre",
            )
            self.assertEqual(
                metadata["planned_campus_scale_wording_as_reported"],
                "100 MW data centre campus planned in the city",
            )
            self.assertEqual(
                metadata["india_roadmap_scale_wording_as_reported"],
                "over 200 MW of capacity across India",
            )
            self.assertIn("not type", metadata["capacity_metric_guardrail"])
            self.assertIn("different entity scopes", metadata["capacity_metric_guardrail"])
            self.assertIn("create no normalized capacity", metadata["capacity_metric_guardrail"])
            self.assertIn("future design", metadata["classification_guardrail"])
            self.assertIn("no normalized workload", metadata["classification_guardrail"])
            self.assertIn("no current load", metadata["sustainability_guardrail"])
            self.assertIn("authoritative named locality", metadata["locality_guardrail"])
            self.assertIn("does not use the BOM02", metadata["project_code_guardrail"])
            self.assertIn("not added", metadata["project_code_guardrail"])
            self.assertIn("computer vision", metadata["imagery_guardrail"])
        else:
            current = evidence[KEPPEL_CURRENT_EVIDENCE]["metadata"]
            locality = evidence[KEPPEL_LOCALITY_EVIDENCE]["metadata"]
            self.assertEqual(
                current["construction_wording_as_reported"],
                "Keppel has commenced construction of its Floating Data Centre project",
            )
            self.assertIn("generic under_construction", current["status_scope"])
            self.assertEqual(
                current["sgp9_future_wording_as_reported"],
                "will begin construction of Keppel DC SGP 9 in mid-2026",
            )
            self.assertIn("separate project", current["sgp9_exclusion_guardrail"])
            self.assertIn("no entity", current["sgp9_exclusion_guardrail"])
            self.assertEqual(
                current["melbourne_powerbank_scale_wording_as_reported_mw"], 720
            )
            self.assertIn("separate site near Melbourne", current["cross_project_guardrail"])
            self.assertIn("no Floating Data Centre capacity", current["cross_project_guardrail"])
            self.assertIn("separate SGP 9", current["classification_guardrail"])
            self.assertIn("two-response capture envelope", current["retrieved_at_semantics"])
            self.assertEqual(
                locality["project_locality_wording_as_reported"],
                "has completed its Environmental Impact Assessment in Singapore",
            )
            self.assertIn("future-looking", locality["historical_status_guardrail"])
            self.assertIn("later April 2026", locality["historical_status_guardrail"])
            self.assertEqual(locality["reported_fdc_scale_mw"], 25)
            self.assertEqual(
                locality["reported_fdc_scale_wording_as_reported"], "the 25 MW FDC"
            )
            self.assertIn("not typed", locality["capacity_metric_guardrail"])
            self.assertIn("no normalized capacity", locality["capacity_metric_guardrail"])
            self.assertIn("context only", locality["forecast_guardrail"])
            self.assertIn("broad authoritative", locality["locality_guardrail"])
            self.assertIn("no source-verifiable street", locality["locality_guardrail"])
            self.assertIn("computer vision", locality["imagery_guardrail"])

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
        self.assertEqual(len(paths), 146)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(
            len(paths),
            len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}),
        )
        return paths

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {row["retrieved_at"] for row in document["evidence"]}
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

    def _offline(self) -> tuple[Any, ...]:
        error = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

    def _build(
        self,
        source_order: Iterable[str],
        *,
        base_first: bool,
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                results: dict[str, tuple[int, int]] = {}
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
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
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return final_state, results
            finally:
                connection.close()

    def _baseline_state(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for path in self._base_paths():
                        self._import(connection, path)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection)
            finally:
                connection.close()

    def test_exact_hashes_raw_closure_canonical_urls_and_v30_collision_absence(
        self,
    ) -> None:
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
            document = self._load(name)
            self._assert_document(name, document)
            new_hashes.update(row["content_hash"] for row in document["evidence"])

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    patches = self._offline()
                    for network_patch in patches:
                        network_patch.start()
                    try:
                        result = self._import(connection, path)
                    finally:
                        for network_patch in reversed(patches):
                            network_patch.stop()
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, expected["evidence_count"])
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        self.assertTrue(new_keys.isdisjoint(baseline_keys))
        self.assertTrue(new_hashes.isdisjoint(baseline_hashes))
        self.assertEqual(new_hashes, {row["content_hash"] for row in (
            self._load(LT_SOURCE)["evidence"] + self._load(KEPPEL_SOURCE)["evidence"]
        )})

    def test_forward_reverse_base_order_idempotence_and_exact_deltas(self) -> None:
        baseline_state = self._baseline_state()
        scenarios = [
            self._build(SOURCE_ORDER, base_first=True),
            self._build(reversed(SOURCE_ORDER), base_first=True),
            self._build(SOURCE_ORDER, base_first=False),
            self._build(reversed(SOURCE_ORDER), base_first=False),
        ]
        expected_results = {
            LT_SOURCE: (2, 1),
            KEPPEL_SOURCE: (2, 2),
        }
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
            },
        )

    def test_combined_import_has_only_exact_narrow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for name in SOURCE_ORDER:
                        self._import(connection, ROOT / "sources" / name)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT entities.stable_key, status, as_of_date, method "
                        "FROM lifecycle_observations JOIN entities "
                        "ON entities.id = lifecycle_observations.entity_id "
                        "ORDER BY entities.stable_key"
                    )],
                    [
                        (
                            SOURCES[KEPPEL_SOURCE]["project_key"],
                            "under_construction",
                            "2026-04-23",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[LT_SOURCE]["project_key"],
                            "under_construction",
                            "2026-01-21",
                            "authoritative_construction_start",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
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
                for table in (
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
                    )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_closed(self) -> None:
        lt = self._load(LT_SOURCE)
        keppel = self._load(KEPPEL_SOURCE)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(lt)
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["capacities"] = [{"forbidden": "40 MW is untyped"}]
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["capacities"] = [{"forbidden": "100 MW is a distinct campus scope"}]
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["capacities"] = [{"forbidden": "200 MW is a national roadmap"}]
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["workloads"] = [{"forbidden": "AI-ready design is not a workload"}]
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["operating_models"] = [
            {"forbidden": "portfolio wording is not an operating model"}
        ]
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["project"]["roles"] = {"operator": ["L&T Vyoma"]}
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["project"]["coordinates"] = {
            "latitude": 19.1,
            "longitude": 73.0,
        }
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(lt)
        mutated["project"]["name"] = "L&T Vyoma BOM02"
        mutations.append((LT_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["lifecycle"].append(
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": KEPPEL_CURRENT_EVIDENCE,
                "as_of_date": "2026-04-23",
                "method": "forbidden_sgp9_inference",
                "confidence": 0.1,
            }
        )
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["capacities"] = [{"forbidden": "25 MW is untyped"}]
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["capacities"] = [{"forbidden": "720 MW belongs to Melbourne"}]
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["workloads"] = [{"forbidden": "SGP9 AI wording is cross-project"}]
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["operating_models"] = [
            {"forbidden": "company positioning is not a project operating model"}
        ]
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["campus"]["roles"] = {"owner": ["Keppel"]}
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["campus"]["coordinates"] = {
            "latitude": 1.3,
            "longitude": 103.8,
        }
        mutations.append((KEPPEL_SOURCE, mutated))

        mutated = copy.deepcopy(keppel)
        mutated["campus"]["evidence_key"] = KEPPEL_CURRENT_EVIDENCE
        mutations.append((KEPPEL_SOURCE, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
