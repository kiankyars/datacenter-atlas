from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-19T18:30:16Z"
AS_OF_DATE = "2026-06-29"
OFFICIAL_URL = (
    "https://www.digitalrealty.com/about/newsroom/press-releases/30426/"
    "digital-realty-announces-purchase-of-blackstone-interest-in-three-"
    "northern-virginia-data-centers"
)
EVIDENCE_KEY = (
    "digital-realty-northern-virginia-manassas-portfolio-2026-06-29-"
    "captured-2026-07-19"
)
DULLES_SOURCE = (
    "curated-official-2026-07-19-digital-realty-digital-dulles-"
    "current-development.json"
)
DULLES_SOURCE_SHA256 = (
    "ddeecf7811dd1d2c792e40813f9ebf07d35a37f79f50e236f5c3329ba06baa39"
)
DULLES_EVIDENCE_KEY = (
    "digital-realty-northern-virginia-transaction-2026-06-29-"
    "captured-2026-07-19"
)
CAMPUS_KEY = "curated:digital-realty-manassas-source-scoped-campus"
CAMPUS_NAME = "Digital Realty Manassas Source-Scoped Campus"
LOCALITY = "Manassas, Virginia, United States"

SOURCE_SPECS = {
    "curated-official-2026-07-20-digital-realty-manassas-source-facility-1.json": {
        "sha256": (
            "8d119f6120b1c9ed539d0a9a0b7ff68e4eafd3e8191601c5c1f55e4f750ea8e9"
        ),
        "project_key": CAMPUS_KEY + ":source-facility-1",
        "project_name": "Digital Realty Manassas Source Facility 1",
        "ordinal": 1,
    },
    "curated-official-2026-07-20-digital-realty-manassas-source-facility-2.json": {
        "sha256": (
            "8fc424d037698f563747706d3fefb051093590e4c2bccb9dfdca73b818f4c70f"
        ),
        "project_key": CAMPUS_KEY + ":source-facility-2",
        "project_name": "Digital Realty Manassas Source Facility 2",
        "ordinal": 2,
    },
}
SOURCE_ORDER = tuple(SOURCE_SPECS)
PROJECT_KEYS = {spec["project_key"] for spec in SOURCE_SPECS.values()}
ENTITY_NAMES = {
    CAMPUS_KEY: CAMPUS_NAME,
    **{
        spec["project_key"]: spec["project_name"]
        for spec in SOURCE_SPECS.values()
    },
}
CAPTURE_METADATA_KEYS = (
    "content_hash_scope",
    "content_hash_verification",
    "capture_headers_scope",
    "capture_headers_sha256",
    "http_status",
    "content_type",
    "content_encoding_as_received",
    "response_http_date",
    "http_last_modified_at",
    "http_etag",
    "requested_url",
    "effective_url",
    "canonical_url",
    "response_header_blocks",
    "retrieval_method",
    "retrieved_at_semantics",
)
SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class DigitalRealtyManassasOfficialSourceTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        error = AssertionError("network used")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(
        self, source_order: Iterable[str], *, repeat: int = 1
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for _ in range(repeat):
                    for name in source_order:
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                expected_counts = {
                    "evidence": 1,
                    "entities": 3,
                    "campuses": 1,
                    "projects": 2,
                    "entity_snapshots": 3,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 2,
                }
                for table, expected in expected_counts.items():
                    observed = connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    self.assertEqual(observed, expected, table)
                return self._state(connection)
            finally:
                connection.close()

    def test_files_are_canonical_hash_pinned_and_reuse_exact_capture(self) -> None:
        dulles_path = self._path(DULLES_SOURCE)
        self.assertEqual(
            hashlib.sha256(dulles_path.read_bytes()).hexdigest(),
            DULLES_SOURCE_SHA256,
        )
        dulles_evidence = json.loads(dulles_path.read_text(encoding="utf-8"))[
            "evidence"
        ][0]
        self.assertEqual(dulles_evidence["key"], DULLES_EVIDENCE_KEY)

        documents: dict[str, dict[str, Any]] = {}
        for name, expected in SOURCE_SPECS.items():
            path = self._path(name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            text = path.read_text(encoding="utf-8")
            document = json.loads(text)
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            documents[name] = document

        evidence = [document["evidence"][0] for document in documents.values()]
        self.assertEqual(evidence[0], evidence[1])
        self.assertEqual(evidence[0]["key"], EVIDENCE_KEY)
        self.assertNotEqual(evidence[0]["key"], dulles_evidence["key"])
        self.assertEqual(evidence[0]["kind"], "company_disclosure")
        self.assertEqual(evidence[0]["source_url"], OFFICIAL_URL)
        self.assertEqual(evidence[0]["publisher"], "Digital Realty")
        self.assertEqual(evidence[0]["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence[0]["published_at"], AS_OF_DATE)
        self.assertEqual(
            evidence[0]["content_hash"],
            "5faadbd9d2fb5edd8c33f981495284f1c32e244d71c43cdbd9eae311137487a5",
        )
        for key in CAPTURE_METADATA_KEYS:
            self.assertEqual(
                evidence[0]["metadata"][key], dulles_evidence["metadata"][key], key
            )

    def test_source_semantics_are_narrow_nonadditive_and_nonidentifying(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        for name, document in documents.items():
            expected = SOURCE_SPECS[name]
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
            self.assertEqual(document["campus"]["name"], CAMPUS_NAME)
            self.assertEqual(document["project"]["stable_key"], expected["project_key"])
            self.assertEqual(document["project"]["name"], expected["project_name"])

            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], "United States")
                self.assertEqual(entity["address"], LOCALITY)
                self.assertEqual(entity["roles"], {})
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(entity["as_of_date"], AS_OF_DATE)
                self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)

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
            self.assertEqual(document["operating_models"], [])
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
                    "low": 96,
                    "base": 96,
                    "high": 96,
                    "method": "reported",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "target_date": None,
                },
            )
            self.assertIn("source-distinguishing label", capacity["notes"])
            self.assertIn("must not be summed", capacity["notes"])
            self.assertIn("not current load", capacity["notes"])

        metadata = next(iter(documents.values()))["evidence"][0]["metadata"]
        self.assertEqual(metadata["critical_it_capacity_per_facility_as_reported_mw"], 96)
        self.assertEqual(metadata["portfolio_capacity_as_reported_mw"], 288)
        self.assertNotIn(
            "manassas_two_facility_subtotal_critical_it_mw", metadata
        )
        self.assertIn("nonadditive", metadata["capacity_scope"])
        self.assertIn("creates no capacity row", metadata["capacity_scope"])
        self.assertIn("No derived Manassas subtotal", metadata["capacity_scope"])
        self.assertEqual(
            metadata["stabilization_forecasts_as_reported"],
            ["first half of 2027", "first half of 2028"],
        )
        self.assertIn("does not assign", metadata["forecast_guardrail"])
        self.assertIn("Neither forecast is imported", metadata["forecast_guardrail"])
        self.assertIn("do not identify any tenant or customer", metadata["lease_guardrail"])
        self.assertIn("do not establish current operation", metadata["lease_guardrail"])
        self.assertIn("not asserted facility names", metadata["ordinal_guardrail"])
        self.assertIn("not cross-source matches", metadata["ordinal_guardrail"])
        self.assertIn("Roles remain empty", metadata["role_guardrail"])
        self.assertIn("not a street address", metadata["coordinate_guardrail"])
        self.assertIn("No third-party source", metadata["external_source_guardrail"])
        self.assertIn("Virginia permit", metadata["external_source_guardrail"])

    def test_shared_campus_and_evidence_deduplicate_in_isolated_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                first_results = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in SOURCE_ORDER
                ]
                self.assertEqual(
                    [
                        (result.entities_created, result.evidence_created, result.warnings)
                        for result in first_results
                    ],
                    [(2, 1, ()), (1, 0, ())],
                )
                frozen = self._state(connection)
                repeated_results = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in SOURCE_ORDER
                ]
                self.assertEqual(
                    [
                        (result.entities_created, result.evidence_created, result.warnings)
                        for result in repeated_results
                    ],
                    [(0, 0, ()), (0, 0, ())],
                )
                self.assertEqual(self._state(connection), frozen)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

        forward = self._build(SOURCE_ORDER)
        reverse = self._build(reversed(SOURCE_ORDER))
        repeated_forward = self._build(SOURCE_ORDER, repeat=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated_forward)

    def test_isolated_database_contains_no_inferred_identity_roles_or_location(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in SOURCE_ORDER:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(validate_database(connection), [])

                snapshots = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.kind, e.stable_key, s.name, s.latitude, s.longitude,
                               s.geometry_json, s.tags_json, s.as_of_date, s.method
                        FROM entity_snapshots AS s
                        JOIN entities AS e ON e.id = s.entity_id
                        ORDER BY e.kind, e.stable_key
                        """
                    )
                ]
                self.assertEqual(len(snapshots), 3)
                for kind, stable_key, name, latitude, longitude, geometry, tags_json, as_of, method in snapshots:
                    self.assertIn(kind, {"campus", "project"})
                    self.assertEqual(name, ENTITY_NAMES[stable_key])
                    self.assertIsNone(latitude)
                    self.assertIsNone(longitude)
                    self.assertIsNone(geometry)
                    self.assertEqual(
                        json.loads(tags_json),
                        {
                            "address": LOCALITY,
                            "country": "United States",
                            "source_dataset": "curated_official_sources",
                        },
                    )
                    self.assertEqual(as_of, AS_OF_DATE)
                    self.assertEqual(method, "authoritative_locality")

                project_targets = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT project.stable_key, target.stable_key
                        FROM projects AS p
                        JOIN entities AS project ON project.id = p.entity_id
                        JOIN entities AS target ON target.id = p.target_entity_id
                        """
                    )
                }
                self.assertEqual(
                    project_targets,
                    {(project_key, CAMPUS_KEY) for project_key in PROJECT_KEYS},
                )
                lifecycle = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, l.status, l.as_of_date, l.method
                        FROM lifecycle_observations AS l
                        JOIN entities AS e ON e.id = l.entity_id
                        """
                    )
                }
                self.assertEqual(
                    lifecycle,
                    {
                        (
                            project_key,
                            "under_construction",
                            AS_OF_DATE,
                            "authoritative_physical_status_update",
                        )
                        for project_key in PROJECT_KEYS
                    },
                )
                capacities = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, c.metric, c.stage, c.unit, c.low, c.base,
                               c.high, c.method, c.as_of_date, c.target_date
                        FROM capacity_estimates AS c
                        JOIN entities AS e ON e.id = c.entity_id
                        """
                    )
                }
                self.assertEqual(
                    capacities,
                    {
                        (
                            project_key,
                            "critical_it_mw",
                            "planned",
                            "MW",
                            96.0,
                            96.0,
                            96.0,
                            "reported",
                            AS_OF_DATE,
                            None,
                        )
                        for project_key in PROJECT_KEYS
                    },
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    1,
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
