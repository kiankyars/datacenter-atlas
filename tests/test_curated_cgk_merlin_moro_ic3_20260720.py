from __future__ import annotations

import copy
import csv
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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v33.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"
BASE_DEFINITION_SHA256 = (
    "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
)
BASE_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)

CGK_SOURCE = "curated-official-2026-07-20-digital-edge-cgk1-bekasi.json"
MERLIN_SOURCE = "curated-official-2026-07-20-merlin-lisbon-phase-2.json"
MORO_SOURCE = "curated-official-2026-07-20-moro-hub-warsan-phase-1.json"
IC3_SOURCE = "curated-official-2026-07-20-macquarie-ic3-super-west-phase-1.json"
SOURCE_ORDER = (CGK_SOURCE, MERLIN_SOURCE, MORO_SOURCE, IC3_SOURCE)

CGK_TOPOUT = "digital-edge-cgk1-topout-2026-06-08-captured-2026-07-20"
CGK_ANNOUNCEMENT = (
    "digital-edge-cgk-campus-announcement-2026-01-28-captured-2026-07-20"
)
MERLIN_PROGRESS = (
    "merlin-lisbon-phase-2-progress-2026-05-13-captured-2026-07-20"
)
MERLIN_LOCATION = "merlin-lisbon-campus-location-page-captured-2026-07-20"
MORO_PROGRESS = (
    "moro-hub-warsan-phase-1-progress-2026-01-23-captured-2026-07-20"
)
IC3_TOPOUT = (
    "macquarie-ic3-super-west-topout-2025-12-03-captured-2026-07-20"
)
IC3_CURRENT = "macquarie-ic3-super-west-current-page-captured-2026-07-20"
IC3_SPEC = (
    "macquarie-ic3-super-west-specification-pdf-captured-2026-07-20"
)

SOURCES: dict[str, dict[str, Any]] = {
    CGK_SOURCE: {
        "sha256": "f2634a600ced7b901b84af36817881cdf9f060dd8aed56cfa1489c2e4f1d7432",
        "retrieved_at": "2026-07-20T00:52:02Z",
        "evidence_count": 2,
        "campus_key": "curated:digital-edge-cgk-campus-bekasi",
        "project_key": "curated:digital-edge-cgk-campus-bekasi:cgk1",
        "country": "Indonesia",
        "address": "GIIC Industrial Estate, Bekasi, Greater Jakarta, Indonesia",
        "roles": {"developer": ["Digital Edge"]},
        "lifecycles": [
            ("shell", "2026-06-08", CGK_TOPOUT),
        ],
        "capacities": [
            ("campus", "critical_it_mw", "planned", "MW", 500.0, "reported"),
            ("campus", "pue", "design", "ratio", 1.25, "reported"),
        ],
    },
    MERLIN_SOURCE: {
        "sha256": "30aa6dda670bdeecd03fe47eb0dc8e39bd5b6f08b44fba5ee2442579c0c5e587",
        "retrieved_at": "2026-07-20T00:52:01Z",
        "evidence_count": 2,
        "campus_key": "curated:merlin-lisbon-data-center-campus",
        "project_key": (
            "curated:merlin-lisbon-data-center-campus:"
            "phase-2-two-building-development"
        ),
        "country": "Portugal",
        "address": (
            "Plataforma Logistica Lisboa Norte, Castanheira do Ribatejo, "
            "Vila Franca de Xira, Portugal"
        ),
        "roles": {},
        "lifecycles": [
            ("under_construction", "2026-05-13", MERLIN_PROGRESS),
        ],
        "capacities": [
            ("project", "critical_it_mw", "planned", "MW", 80.0, "calculated"),
        ],
    },
    MORO_SOURCE: {
        "sha256": "c74dd8a78f2a9fd5fabdb95637fc26680958473a20a3f84f4296b0b87b2034c6",
        "retrieved_at": "2026-07-20T00:52:01Z",
        "evidence_count": 1,
        "campus_key": "curated:moro-hub-warsan-new-green-data-centre",
        "project_key": "curated:moro-hub-warsan-new-green-data-centre:phase-1",
        "country": "United Arab Emirates",
        "address": "Warsan, Dubai, United Arab Emirates",
        "roles": {"developer": ["Moro Hub"]},
        "lifecycles": [
            ("under_construction", "2026-01-23", MORO_PROGRESS),
        ],
        "capacities": [],
    },
    IC3_SOURCE: {
        "sha256": "9fe5625d1cbb2d59dbeb8d329ab1b79fb65a7e43346161f2c92901076cc7cb4f",
        "retrieved_at": "2026-07-20T00:53:38Z",
        "evidence_count": 3,
        "campus_key": "curated:macquarie-ic3-super-west-facility",
        "project_key": (
            "curated:macquarie-ic3-super-west-facility:phase-1-build"
        ),
        "country": "Australia",
        "address": "Macquarie Park, Sydney, New South Wales, Australia",
        "roles": {"developer": ["Macquarie Data Centres"]},
        "lifecycles": [
            ("shell", "2025-12-03", IC3_TOPOUT),
            ("under_construction", "2026-07-17", IC3_CURRENT),
        ],
        "capacities": [
            ("campus", "critical_it_mw", "planned", "MW", 47.0, "reported"),
            ("project", "critical_it_mw", "planned", "MW", 6.0, "reported"),
            ("campus", "pue", "design", "ratio", 1.28, "reported"),
        ],
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    CGK_TOPOUT: {
        "source": CGK_SOURCE,
        "published_at": "2026-06-08T01:58:41+00:00",
        "body_bytes": 348775,
        "content_hash": "0a7bbd094f67937d1453e784c12c56e15e99c3ffab8a76c51b2fad9c7ffc2d25",
        "headers_bytes": 862,
        "headers_hash": "ca983c2d6db5b9dc59a3f53bed5ccbbd93bd0db8e69edb28e9a9edd1e075d3a3",
        "writeout_bytes": 11000,
        "writeout_hash": "4de93064a3537bd73cc7686b68ccce56c6ebef56c740905b9e7f054937c656f8",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": "chunked",
        "content_length": None,
        "download_bytes": 64174,
        "response_date": "2026-07-20T00:52:01Z",
        "url": (
            "https://id.digitaledgedc.com/news/"
            "digital-edge-tops-out-cgk1-secures-largest-indonesia-power-deal"
        ),
    },
    CGK_ANNOUNCEMENT: {
        "source": CGK_SOURCE,
        "published_at": "2026-01-28T06:00:00+00:00",
        "body_bytes": 348977,
        "content_hash": "182adde10e93ad9818a8bb9bb815d9416511429252807d385d503a3ac8e72276",
        "headers_bytes": 862,
        "headers_hash": "ca895a8238a05f6aab16a621bfd1a7b9c5a67a41a3a04cd5f066692894cb9a82",
        "writeout_bytes": 11004,
        "writeout_hash": "958ca4f33d3b92b601791ae705c23c599264a21721db11ab3af157aa7e70598d",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": "chunked",
        "content_length": None,
        "download_bytes": 64335,
        "response_date": "2026-07-20T00:52:02Z",
        "url": (
            "https://id.digitaledgedc.com/news/"
            "digital-edge-4-5b-cgk-500mw-ai-ready-hyperscale-campus-indonesia"
        ),
    },
    MERLIN_PROGRESS: {
        "source": MERLIN_SOURCE,
        "published_at": "2026-05-14T07:44:37+00:00",
        "body_bytes": 100710,
        "content_hash": "9e4570b465ab66b282d46dd5008216b575b250e4ea4438fa8fc4839b90988f13",
        "headers_bytes": 437,
        "headers_hash": "76abbcedc3815fa9e2eb5b76596b99c780915b556b1183f650dc5d7e17c1a3c0",
        "writeout_bytes": 14777,
        "writeout_hash": "01d049cbeaf439fb60606ae1ebb09b18b53e99baeae65fac22a6c9429229747c",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 31124,
        "download_bytes": 31124,
        "response_date": "2026-07-20T00:52:01Z",
        "url": (
            "https://www.merlinproperties.com/pt/imprensa/"
            "merlin-properties-cierra-un-fuerte-primer-trimestre-con-un-"
            "incremento-en-rentas-brutas-del-112-hasta-e1462-millones/"
        ),
    },
    MERLIN_LOCATION: {
        "source": MERLIN_SOURCE,
        "published_at": "2022-06-09T07:05:45+00:00",
        "body_bytes": 91431,
        "content_hash": "16a1571bb186309f7acde2221984e742de9c6d8e743c8048a1b020cb14de0a06",
        "headers_bytes": 559,
        "headers_hash": "8c0550be3212332d979148104fb9c5ef98e434c40274f94537bc55124f84c582",
        "writeout_bytes": 14380,
        "writeout_hash": "6fbaba2d4fb42955315e2bb35795c4a1d93d124eb50439ac71d8df7c69ec2193",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 28775,
        "download_bytes": 28775,
        "response_date": "2026-07-20T00:52:01Z",
        "url": "https://www.merlinproperties.com/en/assets/data-center-lisboa/",
    },
    MORO_PROGRESS: {
        "source": MORO_SOURCE,
        "published_at": "2026-01-23",
        "body_bytes": 39575,
        "content_hash": "f0b9f73134963abe529a1a39373fd89b983a855e2972bfc8e4d3ac5c2e716d3f",
        "headers_bytes": 5765,
        "headers_hash": "f413bce30e08a9279f359a386d5645bde4d9ff14fe568366923e3dfd986559c9",
        "writeout_bytes": 14679,
        "writeout_hash": "b5ff07ea22ed450c12fb2bd05b76ea2fb1f17cbc30dee2802981a7f6d41b6b0f",
        "content_type": "text/html",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": None,
        "download_bytes": 10722,
        "response_date": "2026-07-20T00:52:01Z",
        "url": (
            "https://www.morohub.com/en/media-and-news/news/2026/01/"
            "he-saeed-mohammed-al-tayer-reviews-construction-progress-at-"
            "moro-hub-s-new-green-data-centre-in-warsan"
        ),
    },
    IC3_TOPOUT: {
        "source": IC3_SOURCE,
        "published_at": "2025-12-03T03:23:55+00:00",
        "body_bytes": 1058758,
        "content_hash": "f8f86d1d3f36d46c81f9fe23edce1416f11193e7a16fc32014f98acd96f053e3",
        "headers_bytes": 3381,
        "headers_hash": "e2e80ba19d9604d98eb124351afec9f9ddabbff5978faf785654776fca8016e4",
        "writeout_bytes": 12685,
        "writeout_hash": "62d48d6096597720f9fcc4123ed54e75b25b89f151fcc26c0538f1f3502c4c74",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": None,
        "download_bytes": 114482,
        "response_date": "2026-07-20T00:52:01Z",
        "url": (
            "https://www.macquariedatacentres.com/blog/treasurer-tops-out-"
            "macquarie-data-centres-newest-47mw-ai-and-cloud-data-centre/"
        ),
    },
    IC3_CURRENT: {
        "source": IC3_SOURCE,
        "published_at": "2025-06-02T21:39:31+00:00",
        "body_bytes": 1305676,
        "content_hash": "aea8b63b826c60a6e2027712d124a087c032f2073b611a0ca81b0742a4f5d9f9",
        "headers_bytes": 3381,
        "headers_hash": "e3f1d9a1bae70da458d19b2430421b69094ffc673a73b1b31bec84e5a0fdb4d6",
        "writeout_bytes": 12574,
        "writeout_hash": "899833b6e094e4140eda1a0651a820839c672e71734fc5479f853a144b943f3b",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": None,
        "download_bytes": 129051,
        "response_date": "2026-07-20T00:52:01Z",
        "url": (
            "https://www.macquariedatacentres.com/data-centres/sydney/"
            "macquarie-park-campus/ic3-super-west/"
        ),
    },
    IC3_SPEC: {
        "source": IC3_SOURCE,
        "published_at": None,
        "body_bytes": 429850,
        "content_hash": "bc455a2fa3310e76108b15e8459292aea83dea36beb0fafbc91d2e17ec04e6ce",
        "headers_bytes": 476,
        "headers_hash": "cd039c7ce3c441efbf293c97bb46182bbe3ca3c9305034e82b782500b2d7ec05",
        "writeout_bytes": 12697,
        "writeout_hash": "897133626c5d9909745cee75d21c756a415d51adf0cd068217ec5beb883c9bf3",
        "content_type": "application/pdf",
        "encoding": "gzip",
        "transfer_encoding": None,
        "content_length": None,
        "download_bytes": 392606,
        "response_date": "2026-07-20T00:53:38Z",
        "url": (
            "https://www.macquariedatacentres.com/wp-content/uploads/"
            "sites/5/2023/09/Data-Centres-Data-Sheet-IC3-Super-West-Specs-230923.pdf"
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


class CgkMerlinMoroIc3OfficialSourceTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

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

    def _network_block(self, stack: ExitStack) -> None:
        error = AssertionError("network used")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))

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
        self.assertEqual(len(paths), 161)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(
            {ROOT / "sources" / name for name in SOURCE_ORDER}.isdisjoint(paths)
        )
        return tuple(paths)

    def _build(
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

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        expected = CAPTURES[evidence["key"]]
        source = SOURCES[expected["source"]]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
        self.assertEqual(evidence["content_hash"], expected["content_hash"])
        self.assertEqual(evidence["source_url"], expected["url"])
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(
            metadata["content_hash_verification"], "fetched_bytes_sha256"
        )
        self.assertIn(
            f"exact {expected['body_bytes']}-byte content-decoded",
            metadata["content_hash_scope"],
        )
        self.assertIn(
            f"exact {expected['headers_bytes']}-byte raw",
            metadata["capture_headers_scope"],
        )
        self.assertEqual(metadata["capture_headers_sha256"], expected["headers_hash"])
        self.assertIn(
            f"exact {expected['writeout_bytes']}-byte",
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], expected["writeout_hash"]
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], expected["content_type"])
        self.assertEqual(metadata["content_encoding_as_received"], expected["encoding"])
        self.assertEqual(
            metadata["http_transfer_encoding_as_received"],
            expected["transfer_encoding"],
        )
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            expected["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            expected["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], expected["response_date"])
        self.assertEqual(metadata["requested_url"], expected["url"])
        self.assertEqual(metadata["effective_url"], expected["url"])
        self.assertEqual(metadata["canonical_url"], expected["url"])
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_header_blocks"], 1)

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), expected["evidence_count"])
        self.assertEqual(
            {record["retrieved_at"] for record in document["evidence"]},
            {expected["retrieved_at"]},
        )
        for record in document["evidence"]:
            self._assert_capture(record)
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
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            [
                (row["value"], row["as_of_date"], row["evidence_key"])
                for row in document["lifecycle"]
            ],
            expected["lifecycles"],
        )
        for row in document["lifecycle"]:
            self.assertEqual(row["entity"], "project")
            self.assertEqual(row["method"], "authoritative_physical_status_update")
        self.assertEqual(
            [
                (
                    row["entity"],
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    float(row["base"]),
                    row["method"],
                )
                for row in document["capacities"]
            ],
            expected["capacities"],
        )
        for row in document["capacities"]:
            self.assertEqual(row["low"], row["base"])
            self.assertEqual(row["base"], row["high"])
            self.assertIsNone(row["target_date"])
            self.assertNotIn(row["stage"], {"operational", "measured"})

        evidence = {record["key"]: record for record in document["evidence"]}
        if name == CGK_SOURCE:
            metadata = evidence[CGK_TOPOUT]["metadata"]
            self.assertEqual(metadata["reported_full_campus_it_capacity"]["value"], 500)
            self.assertEqual(
                metadata["reported_secured_power_raw"],
                {
                    "independent_feeds": 2,
                    "per_feed_value": 725,
                    "per_feed_unit": "MVA",
                    "reported_aggregate_value": 1.45,
                    "reported_aggregate_unit": "GW",
                    "scope": "entire CGK Campus",
                },
            )
            self.assertEqual(metadata["reported_target_annualized_pue"], 1.25)
            self.assertIn("never allocated to CGK1", metadata["capacity_scope"])
            self.assertIn("No power-factor conversion", metadata["power_guardrail"])
            self.assertIn("active under-construction umbrella", metadata["status_scope"])
            self.assertIn("EDGE1", metadata["collision_guardrail"])
        elif name == MERLIN_SOURCE:
            metadata = evidence[MERLIN_PROGRESS]["metadata"]
            self.assertEqual(metadata["release_dateline_date"], "2026-05-13")
            self.assertEqual(metadata["phase_2_scope"]["building_count"], 2)
            self.assertEqual(metadata["phase_2_scope"]["per_building_it_capacity_value"], 40)
            self.assertEqual(metadata["phase_2_scope"]["aggregate_it_capacity_value"], 80)
            self.assertIn("three additional", metadata["phase_3_lineage"])
            self.assertIn("metadata only", metadata["phase_3_guardrail"])
            self.assertIn("schema-safe", metadata["role_guardrail"])
            self.assertIn("not evidence that either full shell is complete", metadata["status_scope"])
        elif name == MORO_SOURCE:
            metadata = evidence[MORO_PROGRESS]["metadata"]
            self.assertEqual(
                metadata["reported_whole_centre_capacity_raw"],
                {
                    "comparison": "over",
                    "value": 100,
                    "unit": "MW",
                    "scope": "new Green Data Centre as a whole",
                    "quantity_type": "untyped",
                },
            )
            self.assertIn("not typed", metadata["capacity_guardrail"])
            self.assertIn("January 23, 2026 only", metadata["status_scope"])
            self.assertIn("Phase 2", metadata["project_scope"])
            self.assertIn("Solar-powered", metadata["energy_guardrail"])
            blocked = metadata["blocked_primary_source_attempt"]
            self.assertEqual(blocked["http_status"], 403)
            self.assertEqual(blocked["retained_response_body_bytes"], 0)
            self.assertEqual(blocked["claim_scope"], "none")
            self.assertIn("not an evidence record", metadata["blocked_source_guardrail"])
        elif name == IC3_SOURCE:
            current = evidence[IC3_CURRENT]["metadata"]
            topout = evidence[IC3_TOPOUT]["metadata"]
            specification = evidence[IC3_SPEC]["metadata"]
            self.assertEqual(current["reported_current_body_it_capacity"]["value"], 47)
            self.assertEqual(current["breadcrumb_capacity_text"], "IC3 Super West 45MW")
            self.assertIn("uses the repeated current", current["capacity_conflict_resolution"])
            self.assertEqual(topout["reported_end_state_it_capacity"]["value"], 47)
            self.assertEqual(topout["reported_phase_1_it_capacity"]["value"], 6)
            self.assertIn("must never be summed", topout["nested_capacity_guardrail"])
            self.assertEqual(specification["reported_design_pue"], 1.28)
            self.assertEqual(
                specification["legacy_reported_facility_it_capacity"]["value"], 45
            )
            self.assertEqual(
                specification["legacy_reported_campus_it_capacity"]["value"], 63
            )
            self.assertIn("Neither legacy figure", specification["capacity_conflict_guardrail"])

    def test_byte_pins_capture_closure_modes_and_collision_absence(self) -> None:
        base_paths = self._base_paths()
        base_text = BASE_DEFINITION.read_text(encoding="utf-8")
        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            base_entity_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            base_content_hashes = {row["content_hash"] for row in csv.DictReader(stream)}

        new_paths = {ROOT / "sources" / name for name in SOURCE_ORDER}
        other_entity_keys: set[str] = set()
        other_evidence_keys: set[str] = set()
        other_content_hashes: set[str] = set()
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path in new_paths:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            other_entity_keys.add(document["campus"]["stable_key"])
            if document["project"] is not None:
                other_entity_keys.add(document["project"]["stable_key"])
            for evidence in document["evidence"]:
                other_evidence_keys.add(evidence["key"])
                other_content_hashes.add(evidence["content_hash"])

        new_entity_keys: set[str] = set()
        new_evidence_keys: set[str] = set()
        new_content_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            document = self._load(name)
            self._assert_document(name, document)
            self.assertNotIn(name, base_text)
            self.assertNotIn(expected["campus_key"], base_text)
            self.assertNotIn(expected["project_key"], base_text)
            new_entity_keys.update((expected["campus_key"], expected["project_key"]))
            for evidence in document["evidence"]:
                self._assert_capture(evidence)
                new_evidence_keys.add(evidence["key"])
                new_content_hashes.add(evidence["content_hash"])

        self.assertEqual(len(base_paths), 161)
        self.assertEqual(len(new_entity_keys), 8)
        self.assertEqual(len(new_evidence_keys), 8)
        self.assertEqual(len(new_content_hashes), 8)
        self.assertEqual(new_evidence_keys, set(CAPTURES))
        self.assertEqual(
            new_content_hashes,
            {capture["content_hash"] for capture in CAPTURES.values()},
        )
        self.assertTrue(new_entity_keys.isdisjoint(base_entity_keys))
        self.assertTrue(new_entity_keys.isdisjoint(other_entity_keys))
        self.assertTrue(new_evidence_keys.isdisjoint(other_evidence_keys))
        self.assertTrue(new_content_hashes.isdisjoint(base_content_hashes))
        self.assertTrue(new_content_hashes.isdisjoint(other_content_hashes))
        self.assertFalse(
            any(
                "dewa.gov.ae" in evidence["source_url"]
                for name in SOURCE_ORDER
                for evidence in self._load(name)["evidence"]
            )
        )

    def test_forward_reverse_base_order_idempotence_and_exact_deltas(self) -> None:
        base_paths = self._base_paths()
        baseline = self._baseline_state(base_paths)
        scenarios = [
            self._build(base_paths, SOURCE_ORDER, base_first=True),
            self._build(base_paths, reversed(SOURCE_ORDER), base_first=True),
            self._build(base_paths, SOURCE_ORDER, base_first=False),
            self._build(base_paths, reversed(SOURCE_ORDER), base_first=False),
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
                "evidence": 8,
                "entities": 8,
                "campuses": 4,
                "facilities": 0,
                "buildings": 0,
                "projects": 4,
                "administrative_assignments": 0,
                "entity_snapshots": 8,
                "lifecycle_observations": 5,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 6,
            },
        )

    def test_combined_import_has_only_exact_narrow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._network_block(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in SOURCE_ORDER:
                    result = self._import(connection, ROOT / "sources" / name)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, SOURCES[name]["evidence_count"])
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 4), ("project", 4)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT e.stable_key, l.status, l.as_of_date, l.method "
                            "FROM lifecycle_observations l "
                            "JOIN entities e ON e.id = l.entity_id "
                            "ORDER BY e.stable_key, l.as_of_date"
                        )
                    ],
                    sorted(
                        [
                            (
                                SOURCES[CGK_SOURCE]["project_key"],
                                "shell",
                                "2026-06-08",
                                "authoritative_physical_status_update",
                            ),
                            (
                                SOURCES[MERLIN_SOURCE]["project_key"],
                                "under_construction",
                                "2026-05-13",
                                "authoritative_physical_status_update",
                            ),
                            (
                                SOURCES[MORO_SOURCE]["project_key"],
                                "under_construction",
                                "2026-01-23",
                                "authoritative_physical_status_update",
                            ),
                            (
                                SOURCES[IC3_SOURCE]["project_key"],
                                "shell",
                                "2025-12-03",
                                "authoritative_physical_status_update",
                            ),
                            (
                                SOURCES[IC3_SOURCE]["project_key"],
                                "under_construction",
                                "2026-07-17",
                                "authoritative_physical_status_update",
                            ),
                        ]
                    ),
                )
                capacities = [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT e.stable_key, c.metric, c.stage, c.unit, "
                        "c.low, c.base, c.high, c.method, c.as_of_date, c.notes "
                        "FROM capacity_estimates c "
                        "JOIN entities e ON e.id = c.entity_id "
                        "ORDER BY e.stable_key, c.metric, c.stage, c.as_of_date"
                    )
                ]
                self.assertEqual(len(capacities), 6)
                self.assertEqual(
                    {
                        row[:9]
                        for row in capacities
                    },
                    {
                        (
                            SOURCES[CGK_SOURCE]["campus_key"],
                            "critical_it_mw",
                            "planned",
                            "MW",
                            500.0,
                            500.0,
                            500.0,
                            "reported",
                            "2026-06-08",
                        ),
                        (
                            SOURCES[CGK_SOURCE]["campus_key"],
                            "pue",
                            "design",
                            "ratio",
                            1.25,
                            1.25,
                            1.25,
                            "reported",
                            "2026-06-08",
                        ),
                        (
                            SOURCES[MERLIN_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            "MW",
                            80.0,
                            80.0,
                            80.0,
                            "calculated",
                            "2026-05-13",
                        ),
                        (
                            SOURCES[IC3_SOURCE]["campus_key"],
                            "critical_it_mw",
                            "planned",
                            "MW",
                            47.0,
                            47.0,
                            47.0,
                            "reported",
                            "2026-07-17",
                        ),
                        (
                            SOURCES[IC3_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            "MW",
                            6.0,
                            6.0,
                            6.0,
                            "reported",
                            "2025-12-03",
                        ),
                        (
                            SOURCES[IC3_SOURCE]["campus_key"],
                            "pue",
                            "design",
                            "ratio",
                            1.28,
                            1.28,
                            1.28,
                            "reported",
                            "2026-07-20",
                        ),
                    },
                )
                notes = " ".join(str(row[9]) for row in capacities)
                self.assertIn("not allocated to CGK1", notes)
                self.assertIn("No building-level rows", notes)
                self.assertIn("not additive", notes)
                self.assertIn("planned facility-design value", notes)
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric IN ('grid_connection_mw', 'gross_facility_mw', "
                        "'generation_nameplate_mw', 'annual_energy_mwh') "
                        "OR stage IN ('operational', 'measured')"
                    ).fetchone()[0],
                    0,
                )
                for table in (
                    "operating_model_observations",
                    "workload_observations",
                    "facilities",
                    "buildings",
                    "administrative_assignments",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
                    )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_leakage_mutations_fail_closed(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(documents[CGK_SOURCE])
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append((CGK_SOURCE, mutated))
        mutated = copy.deepcopy(documents[CGK_SOURCE])
        mutated["capacities"][0]["entity"] = "project"
        mutations.append((CGK_SOURCE, mutated))
        mutated = copy.deepcopy(documents[CGK_SOURCE])
        mutated["capacities"].append(
            {
                **mutated["capacities"][0],
                "metric": "grid_connection_mw",
                "base": 1450,
                "low": 1450,
                "high": 1450,
            }
        )
        mutations.append((CGK_SOURCE, mutated))
        mutated = copy.deepcopy(documents[CGK_SOURCE])
        mutated["workloads"] = [{"forbidden": "AI-ready is not workload"}]
        mutations.append((CGK_SOURCE, mutated))

        mutated = copy.deepcopy(documents[MERLIN_SOURCE])
        mutated["capacities"][0]["base"] = 40
        mutations.append((MERLIN_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MERLIN_SOURCE])
        mutated["capacities"].append(
            {**mutated["capacities"][0], "base": 100, "low": 100, "high": 100}
        )
        mutations.append((MERLIN_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MERLIN_SOURCE])
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((MERLIN_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MERLIN_SOURCE])
        mutated["campus"]["roles"] = {"developer": ["Edged"]}
        mutated["project"]["roles"] = {"developer": ["Edged"]}
        mutations.append((MERLIN_SOURCE, mutated))

        mutated = copy.deepcopy(documents[MORO_SOURCE])
        mutated["capacities"] = [
            {
                "entity": "campus",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 100,
                "base": 100,
                "high": 100,
                "method": "reported",
                "confidence": 0.5,
                "evidence_key": MORO_PROGRESS,
                "as_of_date": "2026-01-23",
                "target_date": None,
                "notes": "forbidden allocation",
            }
        ]
        mutations.append((MORO_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MORO_SOURCE])
        mutated["lifecycle"][0]["as_of_date"] = "2026-07-20"
        mutations.append((MORO_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MORO_SOURCE])
        mutated["evidence"][0]["source_url"] = (
            "https://dewa.gov.ae/en/about-us/media-publications/latest-news/"
            "2026/1/he-saeed-mohammed-al-tayer-reviews-construction-progress"
        )
        mutations.append((MORO_SOURCE, mutated))

        mutated = copy.deepcopy(documents[IC3_SOURCE])
        mutated["capacities"][0]["base"] = 45
        mutations.append((IC3_SOURCE, mutated))
        mutated = copy.deepcopy(documents[IC3_SOURCE])
        mutated["capacities"][1]["base"] = 53
        mutations.append((IC3_SOURCE, mutated))
        mutated = copy.deepcopy(documents[IC3_SOURCE])
        mutated["capacities"][2]["stage"] = "measured"
        mutations.append((IC3_SOURCE, mutated))
        mutated = copy.deepcopy(documents[IC3_SOURCE])
        mutated["operating_models"] = [{"forbidden": "planned colocation"}]
        mutations.append((IC3_SOURCE, mutated))
        mutated = copy.deepcopy(documents[IC3_SOURCE])
        mutated["workloads"] = [{"forbidden": "AI capability"}]
        mutations.append((IC3_SOURCE, mutated))

        for name in SOURCE_ORDER:
            mutated = copy.deepcopy(documents[name])
            mutated["campus"]["coordinates"] = {
                "latitude": 0.0,
                "longitude": 0.0,
            }
            mutations.append((name, mutated))
            mutated = copy.deepcopy(documents[name])
            mutated["evidence"][0]["content_hash"] = "0" * 64
            mutations.append((name, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
