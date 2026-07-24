from __future__ import annotations

import copy
import csv
import hashlib
import json
import socket
import stat
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

SERVPAC_SOURCE = "curated-official-2026-07-19-servpac-mtp-building-2.json"
TELEHOUSE_SOURCE = "curated-official-2026-07-19-telehouse-west-two.json"
SOURCE_ORDER = (SERVPAC_SOURCE, TELEHOUSE_SOURCE)

SERVPAC_EVIDENCE = (
    "servpac-mtp-building-2-groundbreaking-2026-01-22-captured-2026-07-19"
)
TELEHOUSE_EVIDENCE = (
    "telehouse-west-two-groundbreaking-2025-10-20-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    SERVPAC_SOURCE: {
        "sha256": (
            "62aceebde60970056a43296cb1e9fd556f88eaeaa15bd2b054b35bfe431b3eb4"
        ),
        "evidence_key": SERVPAC_EVIDENCE,
        "publisher": "Servpac",
        "source_family": "servpac_press_releases",
        "published_at": "2026-01-28",
        "retrieved_at": "2026-07-19T20:54:52Z",
        "country": "United States",
        "address": "Mililani Technology Park, Mililani, Hawaii, United States",
        "campus_key": "curated:servpac-mtp-data-center-campus",
        "campus_name": "Servpac MTP Data Center Campus",
        "project_key": "curated:servpac-mtp-data-center-campus:building-2",
        "project_name": "Servpac MTP Data Center Building 2",
        "as_of_date": "2026-01-22",
    },
    TELEHOUSE_SOURCE: {
        "sha256": (
            "475dd37080fb70be5e078072b21c060ee389856a298a3fb9c98b00ed7ee4ff1d"
        ),
        "evidence_key": TELEHOUSE_EVIDENCE,
        "publisher": "Telehouse",
        "source_family": "telehouse_news",
        "published_at": "2025-10-20",
        "retrieved_at": "2026-07-19T20:53:58Z",
        "country": "United Kingdom",
        "address": "London Docklands, London, United Kingdom",
        "campus_key": "curated:telehouse-london-docklands-campus",
        "campus_name": "Telehouse London Docklands Campus",
        "project_key": "curated:telehouse-london-docklands-campus:west-two",
        "project_name": "Telehouse West Two",
        "as_of_date": "2025-10-20",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    SERVPAC_EVIDENCE: {
        "source": SERVPAC_SOURCE,
        "body_bytes": 164533,
        "content_hash": (
            "834831ef3acd96c46b4e162903efe5ab2ec9daa6e9e1b28083626b2838bd3cd4"
        ),
        "headers_bytes": 713,
        "headers_hash": (
            "c9f56fdbba387e5f8c3c33cf326ce827e8c5cba99fe51c5b096e84766539a500"
        ),
        "writeout_bytes": 17026,
        "writeout_hash": (
            "242baa3b51fef976e0c722371a548bf238f073be79d364f19b86dabaaaa2b1ef"
        ),
        "download_bytes": 33347,
        "response_date": "2026-07-19T20:54:52Z",
        "last_modified": "2026-07-19T20:54:52Z",
        "requested_url": "https://servpac.com/mtp-groundbreaking/?atlas=20260720",
        "effective_url": "https://servpac.com/mtp-groundbreaking/?atlas=20260720",
        "canonical_url": "https://servpac.com/mtp-groundbreaking/",
    },
    TELEHOUSE_EVIDENCE: {
        "source": TELEHOUSE_SOURCE,
        "body_bytes": 165985,
        "content_hash": (
            "4b8f55e3428e065a1105956c6c8af021c3f35d3c333599bdedfc6c4f9eec7970"
        ),
        "headers_bytes": 837,
        "headers_hash": (
            "1bafcf3d12c6f859c19f119a8492a8bb7ecfa83a80bf686ac7298bc6324ba4a5"
        ),
        "writeout_bytes": 9652,
        "writeout_hash": (
            "fdfeb806b366b9e032a8df7926556a8f6ac9e081151f3b48ccc7bb30de97820a"
        ),
        "download_bytes": 35585,
        "response_date": "2026-07-19T20:53:58Z",
        "last_modified": None,
        "requested_url": (
            "https://www.telehouse.net/news/telehouse-breaks-ground-on-new-"
            "275m-data-centre-telehouse-west-two/"
        ),
        "effective_url": (
            "https://www.telehouse.net/news/telehouse-breaks-ground-on-new-"
            "275m-data-centre-telehouse-west-two/"
        ),
        "canonical_url": (
            "https://www.telehouse.net/news/telehouse-breaks-ground-on-new-"
            "275m-data-centre-telehouse-west-two/"
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


class ServpacTelehouseTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["key"]]
        source = SOURCES[capture["source"]]
        metadata = evidence["metadata"]

        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], source["publisher"])
        self.assertEqual(evidence["source_family"], source["source_family"])
        self.assertEqual(evidence["published_at"], source["published_at"])
        self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["canonical_url"])
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
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertEqual(metadata["http_last_modified_at"], capture["last_modified"])
        self.assertEqual(metadata["requested_url"], capture["requested_url"])
        self.assertEqual(metadata["effective_url"], capture["effective_url"])
        self.assertEqual(metadata["canonical_url"], capture["canonical_url"])
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
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], expected["evidence_key"])
        self._assert_capture(evidence)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["evidence_key"])
            self.assertEqual(entity["as_of_date"], expected["as_of_date"])
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
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": expected["as_of_date"],
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        metadata = evidence["metadata"]
        self.assertIn("generic under_construction", metadata["status_scope"])
        self.assertIn("No standardized", metadata["role_guardrail"])
        self.assertIn("no normalized workload", metadata["classification_guardrail"])
        self.assertIn("no source-verifiable street", metadata["locality_guardrail"])
        self.assertIn("computer vision", metadata["imagery_guardrail"])
        if name == SERVPAC_SOURCE:
            self.assertEqual(metadata["release_dateline"], "2026-01-22")
            self.assertIn("January 28", metadata["source_date_guardrail"])
            self.assertIn("January 22", metadata["source_date_guardrail"])
            self.assertEqual(metadata["reported_added_floor_area_sqft_minimum"], 15500)
            self.assertEqual(metadata["reported_facility_size_increase_percent"], 50)
            self.assertEqual(metadata["reported_additional_land_acres"], 5)
            self.assertEqual(metadata["reported_project_investment_usd"], 13000000)
            self.assertEqual(
                metadata["completion_forecast_wording_as_reported"],
                "Building 2 is expected to be complete in the second quarter of this year",
            )
            self.assertIn("Q2 2026", metadata["completion_forecast_normalized_context"])
            self.assertIn("creates no normalized capacity", metadata["scale_guardrail"])
            self.assertIn("not part of project identity", metadata["canonical_url_basis"])
            self.assertIn("existing Building 1", metadata["certification_guardrail"])
        else:
            self.assertEqual(metadata["reported_project_investment_gbp"], 275000000)
            self.assertEqual(metadata["reported_project_investment_usd"], 370000000)
            self.assertEqual(metadata["reported_building_storeys"], 9)
            self.assertEqual(metadata["reported_gross_area_sqm"], 32000)
            self.assertEqual(metadata["reported_white_space_sqm"], 11292)
            self.assertEqual(metadata["reported_white_space_levels"], 6)
            self.assertEqual(metadata["reported_building_capacity_mw"], 33)
            self.assertEqual(metadata["reported_floor_power_capacity_mw_maximum"], 4.4)
            self.assertEqual(metadata["reported_substation_count"], 2)
            self.assertEqual(metadata["reported_substation_voltage_kv"], 132)
            self.assertEqual(metadata["reported_campus_distribution_voltage_kv"], 11)
            self.assertIn("not type", metadata["capacity_metric_guardrail"])
            self.assertIn("not multiplied or summed", metadata["capacity_metric_guardrail"])
            self.assertIn("no normalized capacity", metadata["capacity_metric_guardrail"])
            self.assertIn(
                "transient edge-security cookie",
                metadata["capture_headers_sensitive_data_guardrail"],
            )

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

    def test_exact_capture_contract_and_v30_collision_absence(self) -> None:
        baseline_text = BASE_DEFINITION.read_text(encoding="utf-8")
        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            baseline_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            baseline_hashes = {row["content_hash"] for row in csv.DictReader(stream)}

        new_keys: set[str] = set()
        new_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            self.assertNotIn(name, baseline_text)
            self.assertNotIn(expected["campus_key"], baseline_text)
            self.assertNotIn(expected["project_key"], baseline_text)
            new_keys.update((expected["campus_key"], expected["project_key"]))
            document = self._load(name)
            self._assert_document(name, document)
            new_hashes.add(document["evidence"][0]["content_hash"])

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
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        self.assertTrue(new_keys.isdisjoint(baseline_keys))
        self.assertTrue(new_hashes.isdisjoint(baseline_hashes))
        self.assertEqual(new_hashes, {capture["content_hash"] for capture in CAPTURES.values()})

    def test_forward_reverse_base_order_idempotence_and_exact_deltas(self) -> None:
        baseline_state = self._baseline_state()
        scenarios = [
            self._build(SOURCE_ORDER, base_first=True),
            self._build(reversed(SOURCE_ORDER), base_first=True),
            self._build(SOURCE_ORDER, base_first=False),
            self._build(reversed(SOURCE_ORDER), base_first=False),
        ]
        expected_results = {
            SERVPAC_SOURCE: (2, 1),
            TELEHOUSE_SOURCE: (2, 1),
        }
        reference_state = scenarios[0][0]
        for state, results in scenarios:
            self.assertEqual(state, reference_state)
            self.assertEqual(results, expected_results)

        baseline_counts = {table: len(rows) for table, rows in baseline_state.items()}
        final_counts = {table: len(rows) for table, rows in reference_state.items()}
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
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        (
                            SOURCES[SERVPAC_SOURCE]["project_key"],
                            "under_construction",
                            "2026-01-22",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[TELEHOUSE_SOURCE]["project_key"],
                            "under_construction",
                            "2025-10-20",
                            "authoritative_construction_start",
                        ),
                    ],
                )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)
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
        servpac = self._load(SERVPAC_SOURCE)
        telehouse = self._load(TELEHOUSE_SOURCE)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(servpac)
        mutated["lifecycle"][0]["value"] = "foundations"
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["capacities"] = [{"forbidden": "relative capacity is untyped"}]
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["workloads"] = [{"forbidden": "cloud services are not a workload"}]
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["operating_models"] = [{"forbidden": "colocation wording is not a model"}]
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["project"]["roles"] = {"owner": ["Servpac"]}
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["project"]["coordinates"] = {"latitude": 21.45, "longitude": -158.02}
        mutations.append((SERVPAC_SOURCE, mutated))
        mutated = copy.deepcopy(servpac)
        mutated["lifecycle"][0]["as_of_date"] = "2026-01-28"
        mutations.append((SERVPAC_SOURCE, mutated))

        mutated = copy.deepcopy(telehouse)
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["capacities"] = [{"forbidden": "33 MW is untyped"}]
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["capacities"] = [{"forbidden": "4.4 MW per floor is untyped"}]
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["workloads"] = [{"forbidden": "AI-ready design is not a workload"}]
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["operating_models"] = [{"forbidden": "company service is not a model"}]
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["project"]["roles"] = {"operator": ["Telehouse"]}
        mutations.append((TELEHOUSE_SOURCE, mutated))
        mutated = copy.deepcopy(telehouse)
        mutated["campus"]["coordinates"] = {"latitude": 51.5, "longitude": 0.0}
        mutations.append((TELEHOUSE_SOURCE, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
