from __future__ import annotations

import copy
import csv
import hashlib
import itertools
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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v34.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v34"
BASE_DEFINITION_SHA256 = (
    "004513441aaffbe7ce85562b993fcf4a6d15f9630aad6fab21ce46f359f47264"
)
BASE_MANIFEST_SHA256 = (
    "66344585b802b3640d5921e37cf64cbc990eaa3a2e8b2a44f1891acbe8887d4a"
)
SOFTBANK_SOURCE = "curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json"
GREEN_SOURCE = "curated-official-2026-07-20-green-zrh1-dc4-lupfig.json"
IIJ_SOURCE = "curated-official-2026-07-20-iij-shiroi-phase-3.json"
SOURCE_ORDER = (SOFTBANK_SOURCE, GREEN_SOURCE, IIJ_SOURCE)

SOURCES: dict[str, dict[str, Any]] = {
    SOFTBANK_SOURCE: {
        "sha256": "2efccf401355b50ce559e64c060d5cf6f1350d326440c0035ce63bf008e07d73",
        "retrieved_at": "2026-07-20T01:03:36Z",
        "evidence_count": 2,
        "campus_key": (
            "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-campus"
        ),
        "project_key": (
            "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-"
            "campus:planned-data-hall-building"
        ),
        "address": "Tomakomai, Hokkaido, Japan",
        "country": "Japan",
        "roles": {
            "developer": ["SoftBank Corp.", "IDC Frontier Inc."],
        },
        "lifecycle_date": "2025-05-01",
        "lifecycle_evidence": (
            "softbank-tomakomai-ai-data-center-groundbreaking-2025-05-01-"
            "captured-2026-07-20"
        ),
    },
    GREEN_SOURCE: {
        "sha256": "7161ad1721c77f39b432aa3b0ebf8de42c8140230b61c5a89ea843ea664d868e",
        "retrieved_at": "2026-07-20T01:03:34Z",
        "evidence_count": 1,
        "campus_key": "curated:green-campus-zrh1-lupfig",
        "project_key": "curated:green-campus-zrh1-lupfig:data-center-4",
        "address": "Lupfig, Aargau, Switzerland",
        "country": "Switzerland",
        "roles": {},
        "lifecycle_date": "2026-07-20",
        "lifecycle_evidence": (
            "green-campus-zrh1-dc4-current-construction-captured-2026-07-20"
        ),
    },
    IIJ_SOURCE: {
        "sha256": "ed214cfed7495ad6b1cf7a65f2cc1e90d80d12b58b615afb2931b98cb0bb6714",
        "retrieved_at": "2026-07-20T01:03:36Z",
        "evidence_count": 2,
        "campus_key": "curated:iij-shiroi-data-center-campus",
        "project_key": (
            "curated:iij-shiroi-data-center-campus:phase-3-server-building"
        ),
        "address": "Shiroi City, Chiba Prefecture, Japan",
        "country": "Japan",
        "roles": {
            "developer": ["Internet Initiative Japan Inc."],
        },
        "lifecycle_date": "2026-06-25",
        "lifecycle_evidence": (
            "iij-shiroi-third-site-current-construction-risk-page-"
            "captured-2026-07-20"
        ),
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "softbank-tomakomai-ai-data-center-groundbreaking-2025-05-01-captured-2026-07-20": {
        "source": SOFTBANK_SOURCE,
        "publisher": "SoftBank Corp.",
        "source_family": "softbank_news",
        "published_at": "2025-05-01T17:02:45+09:00",
        "body_bytes": 97843,
        "content_hash": "c189dce34805edb292c07c6204122b6e4a9d8d30cd7cd7e91080ea92905edd1e",
        "headers_bytes": 737,
        "headers_hash": "94cc64d888e68228e6a62487cabad40c2a81cea245d5284d9a18d423daf478e8",
        "writeout_bytes": 11546,
        "writeout_hash": "3721906e4153014ffb9ce9365ecec2155d97767089d6a095144374bbac65e175",
        "download_bytes": 20896,
        "content_type": "text/html; charset=utf-8",
        "content_length": 20896,
        "response_date": "2026-07-20T01:03:36Z",
        "last_modified": None,
        "url": "https://www.softbank.jp/en/sbnews/entry/20250501_01",
    },
    "softbank-tomakomai-50mw-receiving-capacity-current-page-captured-2026-07-20": {
        "source": SOFTBANK_SOURCE,
        "publisher": "SoftBank Corp.",
        "source_family": "softbank_sustainability",
        "published_at": None,
        "body_bytes": 89753,
        "content_hash": "02ab48dcfbb12802f3e2c01789f26acff3e516832b074645b7b160aa241372b0",
        "headers_bytes": 445,
        "headers_hash": "4749073ec2b6c64273c55632ec8060924e3d3ec0099bc00cc42153d01b9dd228",
        "writeout_bytes": 11629,
        "writeout_hash": "d9f26e71c1399d877cdbc7646d66b9986980c451b66af877311dc278977d189f",
        "download_bytes": 15733,
        "content_type": "text/html; charset=utf-8",
        "content_length": 15733,
        "response_date": "2026-07-20T01:03:36Z",
        "last_modified": None,
        "url": (
            "https://www.softbank.jp/en/corp/sustainability/materiality/"
            "next-gen-infra/"
        ),
    },
    "green-campus-zrh1-dc4-current-construction-captured-2026-07-20": {
        "source": GREEN_SOURCE,
        "publisher": "Green",
        "source_family": "green_data_center_facility_pages",
        "published_at": None,
        "body_bytes": 239150,
        "content_hash": "a241bca1a18774e0b82c7b2d23e59dbf86bbb30cc1160604808de34e626d3ce4",
        "headers_bytes": 138,
        "headers_hash": "a88f3a8f1cc5183538a7f5907d9e77e9de1a987945a7d609bd7553f32ab00dac",
        "writeout_bytes": 16443,
        "writeout_hash": "934d2e4da3618b6f66ee284ad97a2e4d2bc8d03da52552fd349b0afcab6613f6",
        "download_bytes": 25146,
        "content_type": "text/html; charset=utf-8",
        "content_length": None,
        "response_date": "2026-07-20T01:03:34Z",
        "last_modified": None,
        "url": (
            "https://www.green.ch/en/enterprise/data-center-locations/"
            "green-switzerland/campus-zrh1-lupfig/datacenter-4-lupfig"
        ),
    },
    "iij-shiroi-third-site-current-construction-risk-page-captured-2026-07-20": {
        "source": IIJ_SOURCE,
        "publisher": "Internet Initiative Japan Inc.",
        "source_family": "iij_investor_relations",
        "published_at": "2026-06-25",
        "body_bytes": 74884,
        "content_hash": "d665d479045420e991eba21ab02f6fe3bc01607cf2cb7382895427a8defb33e3",
        "headers_bytes": 342,
        "headers_hash": "0a2d1cf6afb77f9167780c6521ed4a271336cef526b1b1f85c76f704ecde3b46",
        "writeout_bytes": 11189,
        "writeout_hash": "c961ad3fbcd2b712ae1949e72ffe520bec459947e96e2ff40eb371751600e609",
        "download_bytes": 21380,
        "content_type": "text/html",
        "content_length": 21380,
        "response_date": "2026-07-20T01:03:36Z",
        "last_modified": "2026-06-25T04:08:02Z",
        "url": "https://www.iij.ad.jp/en/ir/policy/risk/",
    },
    "iij-shiroi-phase-3-plan-10mw-2025-05-08-captured-2026-07-20": {
        "source": IIJ_SOURCE,
        "publisher": "Internet Initiative Japan Inc.",
        "source_family": "iij_press_releases",
        "published_at": "2025-05-08",
        "body_bytes": 20153,
        "content_hash": "7c9f965f4d6c229f0aaab2ecd4584d9943c6d6fca13ed6c528316c72956d18b8",
        "headers_bytes": 341,
        "headers_hash": "8b4b0a54a054684f4ae45f2f051acbc676e0aa3e6084e14a124d74fc2682204a",
        "writeout_bytes": 11265,
        "writeout_hash": "67d58a9f3d3a7d3f952fe00e623837add1300edd1ddf685e1b22bcedca6a3302",
        "download_bytes": 5834,
        "content_type": "text/html",
        "content_length": 5834,
        "response_date": "2026-07-20T01:03:36Z",
        "last_modified": "2026-01-13T02:01:56Z",
        "url": "https://www.iij.ad.jp/en/news/pressrelease/2025/0508.html",
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


class SoftBankGreenIijOfficialSourceTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (
                        tuple(row)
                        for row in connection.execute(f"SELECT * FROM {table}")
                    ),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {record["retrieved_at"] for record in document["evidence"]}
        self.assertEqual(len(timestamps), 1)
        return next(iter(timestamps))

    def _import(self, connection: Any, path: Path) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            path,
            retrieved_at=self._retrieved_at(path),
        )

    def _network_block(self, stack: ExitStack) -> None:
        network_error = AssertionError("network used")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=network_error))

    def _base_paths(self) -> tuple[Path, ...]:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(BASE_DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BASE_RELEASE.stat().st_mode), 0o555)
        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
            )
            paths.append(path)
        self.assertEqual(len(paths), 164)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(
            {ROOT / "sources" / name for name in SOURCE_ORDER}.isdisjoint(paths)
        )
        return tuple(paths)

    def _baseline_state(
        self, base_paths: tuple[Path, ...]
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._network_block(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for path in base_paths:
                    self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._state(connection)
            finally:
                connection.close()

    def _build_against_base(
        self,
        base_paths: tuple[Path, ...],
        source_order: Iterable[str],
        *,
        base_first: bool,
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._network_block(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                results: dict[str, tuple[int, int]] = {}
                if base_first:
                    for path in base_paths:
                        self._import(connection, path)
                for name in source_order:
                    result = self._import(connection, ROOT / "sources" / name)
                    results[name] = (
                        result.entities_created,
                        result.evidence_created,
                    )
                    self.assertEqual(result.warnings, ())
                if not base_first:
                    for path in base_paths:
                        self._import(connection, path)
                frozen = self._state(connection)
                for name in SOURCE_ORDER:
                    result = self._import(connection, ROOT / "sources" / name)
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)
                self.assertEqual(self._state(connection), frozen)
                self.assertEqual(validate_database(connection), [])
                return frozen, results
            finally:
                connection.close()

    def _assert_semantic_contract(
        self, name: str, document: dict[str, Any]
    ) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), expected["evidence_count"])
        self.assertEqual(
            {item["retrieved_at"] for item in document["evidence"]},
            {expected["retrieved_at"]},
        )
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], expected["roles"])
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": expected["lifecycle_evidence"],
                    "as_of_date": expected["lifecycle_date"],
                    "method": (
                        "authoritative_construction_start"
                        if name == SOFTBANK_SOURCE
                        else "authoritative_physical_status_update"
                    ),
                    "confidence": 0.99,
                }
            ],
        )

        if name == SOFTBANK_SOURCE:
            self.assertEqual(
                document["workloads"],
                [
                    {
                        "entity": "project",
                        "value": "ai_specialized_unspecified",
                        "evidence_key": (
                            "softbank-tomakomai-ai-data-center-groundbreaking-"
                            "2025-05-01-captured-2026-07-20"
                        ),
                        "as_of_date": "2025-05-01",
                        "method": "company_disclosure",
                        "confidence": 0.99,
                    }
                ],
            )
            capacity = document["capacities"]
            self.assertEqual(len(capacity), 1)
            self.assertEqual(
                {
                    key: capacity[0][key]
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
                    "metric": "grid_connection_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 50,
                    "base": 50,
                    "high": 50,
                    "method": "reported",
                    "confidence": 0.98,
                    "evidence_key": (
                        "softbank-tomakomai-50mw-receiving-capacity-current-page-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-16",
                    "target_date": None,
                },
            )
        elif name == IIJ_SOURCE:
            self.assertEqual(document["workloads"], [])
            capacity = document["capacities"]
            self.assertEqual(len(capacity), 1)
            self.assertEqual(
                {
                    key: capacity[0][key]
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
                    "metric": "grid_connection_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 10,
                    "base": 10,
                    "high": 10,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": (
                        "iij-shiroi-phase-3-plan-10mw-2025-05-08-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2025-05-08",
                    "target_date": None,
                },
            )
        else:
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])

    def _build(self, order: Iterable[str]) -> dict[str, tuple[tuple[Any, ...], ...]]:
        network_error = AssertionError("network used")
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=network_error))
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in order:
                    expected = SOURCES[name]
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=expected["retrieved_at"],
                    )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                    self.assertEqual(result.warnings, ())

                first_state = self._state(connection)
                for name in SOURCE_ORDER:
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=SOURCES[name]["retrieved_at"],
                    )
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)

                self.assertEqual(self._state(connection), first_state)
                self.assertEqual(validate_database(connection), [])
                expected_counts = {
                    "evidence": 5,
                    "entities": 6,
                    "lifecycle_observations": 3,
                    "operating_model_observations": 0,
                    "workload_observations": 1,
                    "capacity_estimates": 2,
                }
                for table, count in expected_counts.items():
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0],
                        count,
                    )
                return first_state
            finally:
                connection.close()

    def test_sources_are_byte_pinned_and_semantically_narrow(self) -> None:
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            document = self._load(name)
            self._assert_semantic_contract(name, document)
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(len(document["evidence"]), expected["evidence_count"])
            self.assertEqual(
                {item["retrieved_at"] for item in document["evidence"]},
                {expected["retrieved_at"]},
            )
            self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
            self.assertEqual(document["project"]["stable_key"], expected["project_key"])
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], expected["country"])
                self.assertEqual(entity["address"], expected["address"])
                self.assertEqual(entity["roles"], expected["roles"])
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")

            self.assertEqual(len(document["lifecycle"]), 1)
            lifecycle = document["lifecycle"][0]
            self.assertEqual(lifecycle["entity"], "project")
            self.assertEqual(lifecycle["value"], "under_construction")
            self.assertEqual(lifecycle["as_of_date"], expected["lifecycle_date"])
            self.assertEqual(
                lifecycle["evidence_key"], expected["lifecycle_evidence"]
            )
            self.assertIn(
                lifecycle["method"],
                {
                    "authoritative_construction_start",
                    "authoritative_physical_status_update",
                },
            )
            self.assertEqual(document["operating_models"], [])

        softbank = self._load(SOFTBANK_SOURCE)
        self.assertEqual(
            softbank["workloads"],
            [
                {
                    "entity": "project",
                    "value": "ai_specialized_unspecified",
                    "evidence_key": (
                        "softbank-tomakomai-ai-data-center-groundbreaking-"
                        "2025-05-01-captured-2026-07-20"
                    ),
                    "as_of_date": "2025-05-01",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(softbank["capacities"]), 1)
        softbank_capacity = softbank["capacities"][0]
        self.assertEqual(softbank_capacity["entity"], "project")
        self.assertEqual(softbank_capacity["metric"], "grid_connection_mw")
        self.assertEqual(softbank_capacity["stage"], "planned")
        self.assertEqual(
            [softbank_capacity[key] for key in ("low", "base", "high")],
            [50, 50, 50],
        )
        self.assertIn("50 MW-scale", softbank_capacity["notes"])
        self.assertIn("greater-than-300 MW", softbank_capacity["notes"])
        self.assertNotIn("300", {item["base"] for item in softbank["capacities"]})

        green = self._load(GREEN_SOURCE)
        self.assertEqual(green["campus"]["roles"], {})
        self.assertEqual(green["operating_models"], [])
        self.assertEqual(green["workloads"], [])
        self.assertEqual(green["capacities"], [])
        green_metadata = green["evidence"][0]["metadata"]
        self.assertIn("No 12 MW value appears", green_metadata["capacity_guardrail"])
        self.assertIn("not data-center load", green_metadata["energy_guardrail"])

        iij = self._load(IIJ_SOURCE)
        self.assertEqual(iij["operating_models"], [])
        self.assertEqual(iij["workloads"], [])
        self.assertEqual(len(iij["capacities"]), 1)
        iij_capacity = iij["capacities"][0]
        self.assertEqual(iij_capacity["entity"], "project")
        self.assertEqual(iij_capacity["metric"], "grid_connection_mw")
        self.assertEqual(iij_capacity["stage"], "planned")
        self.assertEqual(
            [iij_capacity[key] for key in ("low", "base", "high")],
            [10, 10, 10],
        )
        for boundary in ("25 MW", "not a second", "or additive value", "MVA"):
            self.assertIn(boundary, iij_capacity["notes"])
        self.assertNotIn(25, {item["base"] for item in iij["capacities"]})

    def test_capture_facts_and_bounded_envelopes_are_exact(self) -> None:
        records = {
            evidence["key"]: evidence
            for name in SOURCE_ORDER
            for evidence in self._load(name)["evidence"]
        }
        self.assertEqual(set(records), set(CAPTURES))

        for key, expected in CAPTURES.items():
            evidence = records[key]
            metadata = evidence["metadata"]
            source = SOURCES[expected["source"]]
            self.assertEqual(evidence["kind"], "company_disclosure")
            self.assertEqual(evidence["publisher"], expected["publisher"])
            self.assertEqual(evidence["source_family"], expected["source_family"])
            self.assertEqual(evidence["published_at"], expected["published_at"])
            self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
            self.assertEqual(evidence["content_hash"], expected["content_hash"])
            self.assertIn(
                f"exact {expected['body_bytes']}-byte content-decoded",
                metadata["content_hash_scope"],
            )
            self.assertEqual(
                metadata["capture_headers_sha256"], expected["headers_hash"]
            )
            self.assertIn(
                f"exact {expected['headers_bytes']}-byte raw",
                metadata["capture_headers_scope"],
            )
            self.assertEqual(
                metadata["capture_curl_writeout_sha256"],
                expected["writeout_hash"],
            )
            self.assertIn(
                f"exact {expected['writeout_bytes']}-byte",
                metadata["capture_curl_writeout_scope"],
            )
            self.assertIn(
                "No authorization or Set-Cookie header occurred",
                metadata["capture_headers_sensitive_data_guardrail"],
            )
            self.assertEqual(metadata["http_status"], 200)
            self.assertEqual(metadata["content_type"], expected["content_type"])
            self.assertEqual(metadata["content_encoding_as_received"], "gzip")
            self.assertIsNone(metadata["http_transfer_encoding_as_received"])
            self.assertEqual(
                metadata["http_content_length_bytes_as_received"],
                expected["content_length"],
            )
            self.assertEqual(
                metadata["curl_size_download_bytes_as_received"],
                expected["download_bytes"],
            )
            self.assertEqual(metadata["response_http_date"], expected["response_date"])
            if expected["last_modified"] is None:
                self.assertNotIn("http_last_modified_at", metadata)
            else:
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
            self.assertEqual(metadata["requested_url"], expected["url"])
            self.assertEqual(metadata["effective_url"], expected["url"])
            self.assertEqual(metadata["canonical_url"], expected["url"])
            self.assertEqual(evidence["source_url"], expected["url"])
            self.assertEqual(metadata["redirect_count"], 0)
            self.assertEqual(metadata["response_header_blocks"], 1)

    def test_import_is_offline_idempotent_and_order_independent(self) -> None:
        expected_state = self._build(SOURCE_ORDER)
        for order in itertools.permutations(SOURCE_ORDER):
            with self.subTest(order=order):
                self.assertEqual(self._build(order), expected_state)

    def test_v34_collision_absence_and_base_order_are_exact(self) -> None:
        base_paths = self._base_paths()
        base_entity_keys: set[str] = set()
        base_evidence_keys: set[str] = set()
        base_content_hashes: set[str] = set()
        for path in base_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            base_entity_keys.add(document["campus"]["stable_key"])
            if document["project"] is not None:
                base_entity_keys.add(document["project"]["stable_key"])
            for evidence in document["evidence"]:
                base_evidence_keys.add(evidence["key"])
                base_content_hashes.add(evidence["content_hash"])

        with (BASE_RELEASE / "entities.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            release_entity_keys = {
                row["stable_key"] for row in csv.DictReader(stream)
            }
        with (BASE_RELEASE / "evidence.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            release_content_hashes = {
                row["content_hash"] for row in csv.DictReader(stream)
            }
        self.assertTrue(base_entity_keys.issubset(release_entity_keys))

        documents = {name: self._load(name) for name in SOURCE_ORDER}
        new_entity_keys = {
            key
            for document in documents.values()
            for key in (
                document["campus"]["stable_key"],
                document["project"]["stable_key"],
            )
        }
        new_evidence_keys = {
            evidence["key"]
            for document in documents.values()
            for evidence in document["evidence"]
        }
        new_content_hashes = {
            evidence["content_hash"]
            for document in documents.values()
            for evidence in document["evidence"]
        }
        self.assertEqual(len(new_entity_keys), 6)
        self.assertEqual(len(new_evidence_keys), 5)
        self.assertEqual(len(new_content_hashes), 5)
        self.assertTrue(new_entity_keys.isdisjoint(base_entity_keys))
        self.assertTrue(new_entity_keys.isdisjoint(release_entity_keys))
        self.assertTrue(new_evidence_keys.isdisjoint(base_evidence_keys))
        self.assertTrue(new_content_hashes.isdisjoint(base_content_hashes))
        self.assertTrue(new_content_hashes.isdisjoint(release_content_hashes))

        baseline = self._baseline_state(base_paths)
        scenarios = [
            self._build_against_base(base_paths, SOURCE_ORDER, base_first=True),
            self._build_against_base(
                base_paths, reversed(SOURCE_ORDER), base_first=True
            ),
            self._build_against_base(base_paths, SOURCE_ORDER, base_first=False),
            self._build_against_base(
                base_paths, reversed(SOURCE_ORDER), base_first=False
            ),
        ]
        expected_results = {
            name: (2, SOURCES[name]["evidence_count"]) for name in SOURCE_ORDER
        }
        reference = scenarios[0][0]
        for state, results in scenarios:
            self.assertEqual(state, reference)
            self.assertEqual(results, expected_results)

        baseline_counts = {table: len(rows) for table, rows in baseline.items()}
        final_counts = {table: len(rows) for table, rows in reference.items()}
        self.assertEqual(
            {
                table: final_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            {
                "evidence": 5,
                "entities": 6,
                "campuses": 3,
                "facilities": 0,
                "buildings": 0,
                "projects": 3,
                "administrative_assignments": 0,
                "entity_snapshots": 6,
                "lifecycle_observations": 3,
                "operating_model_observations": 0,
                "workload_observations": 1,
                "capacity_estimates": 2,
            },
        )

    def test_semantic_mutations_fail_closed(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        mutations: list[tuple[str, dict[str, Any], str]] = []

        mutated = copy.deepcopy(documents[SOFTBANK_SOURCE])
        mutated["capacities"][0]["target_date"] = "2026-12-31"
        mutations.append((SOFTBANK_SOURCE, mutated, "invented target date"))

        mutated = copy.deepcopy(documents[SOFTBANK_SOURCE])
        mutated["capacities"][0]["evidence_key"] = (
            "softbank-tomakomai-ai-data-center-groundbreaking-2025-05-01-"
            "captured-2026-07-20"
        )
        mutations.append((SOFTBANK_SOURCE, mutated, "wrong metric evidence"))

        mutated = copy.deepcopy(documents[SOFTBANK_SOURCE])
        mutated["capacities"][0]["method"] = "calculated"
        mutations.append((SOFTBANK_SOURCE, mutated, "wrong provenance method"))

        mutated = copy.deepcopy(documents[IIJ_SOURCE])
        mutated["capacities"][0]["as_of_date"] = "2026-07-20"
        mutations.append((IIJ_SOURCE, mutated, "retrieval date substituted"))

        mutated = copy.deepcopy(documents[GREEN_SOURCE])
        mutated["capacities"] = [
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 12,
                "base": 12,
                "high": 12,
                "method": "reported",
                "confidence": 0.5,
                "evidence_key": (
                    "green-campus-zrh1-dc4-current-construction-captured-"
                    "2026-07-20"
                ),
                "as_of_date": "2026-07-20",
                "target_date": None,
                "notes": "forbidden inferred capacity",
            }
        ]
        mutations.append((GREEN_SOURCE, mutated, "unsupported 12 MW"))

        for name, document, reason in mutations:
            with self.subTest(source=name, reason=reason):
                with self.assertRaises(AssertionError):
                    self._assert_semantic_contract(name, document)


if __name__ == "__main__":
    unittest.main()
