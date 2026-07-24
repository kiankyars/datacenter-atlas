from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]

EDGED_SOURCE = (
    "curated-official-2026-07-20-edged-council-bluffs-first-data-center.json"
)
AWS_SOURCE = (
    "curated-official-2026-07-20-aws-bharat-future-city-groundbreaking.json"
)
MU4_CURRENT_SOURCE = (
    "curated-official-2026-07-20-equinix-mu4-munich-phase-3-topout.json"
)
QTS_SOURCE = "curated-official-2026-07-20-qts-hall-county-proposed-campus.json"
NEW_SOURCES = (EDGED_SOURCE, AWS_SOURCE, MU4_CURRENT_SOURCE, QTS_SOURCE)

MU4_IDENTITY_SOURCE = (
    "curated-official-2026-07-20-equinix-mu4-munich-phase-3.json"
)
CHILDRESS_SOURCE = "curated-official-2026-07-17-childress.json"
COMBINED_SOURCES = (MU4_IDENTITY_SOURCE,) + NEW_SOURCES

RETRIEVED_AT_BY_SOURCE = {
    EDGED_SOURCE: "2026-07-20T06:09:20Z",
    AWS_SOURCE: "2026-07-20T06:08:15Z",
    MU4_CURRENT_SOURCE: "2026-07-20T06:08:14Z",
    QTS_SOURCE: "2026-07-20T06:11:59Z",
    MU4_IDENTITY_SOURCE: "2026-07-20T02:20:07Z",
}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    EDGED_SOURCE: {
        "sha256": "d65f65e715c84fd6f93d6d248811c6a83258714a65244b6130e90c2ee77f5117",
        "bytes": 18_529,
        "evidence_count": 3,
        "campus_key": "curated:edged-council-bluffs-data-center-campus",
        "project_key": (
            "curated:edged-council-bluffs-data-center-campus:first-data-center"
        ),
    },
    AWS_SOURCE: {
        "sha256": "6080fbf53e1921321f5c03c25975c2d5adfb3d827d7891b08bff4585d9231a68",
        "bytes": 8_714,
        "evidence_count": 1,
        "campus_key": "curated:aws-bharat-future-city-data-center-campus",
        "project_key": (
            "curated:aws-bharat-future-city-data-center-campus:"
            "initial-data-center-project"
        ),
    },
    MU4_CURRENT_SOURCE: {
        "sha256": "87caf33997afbd8663486511815a141e6c7cb18d59ee5951648a21d3591a27d2",
        "bytes": 7_748,
        "evidence_count": 1,
        "campus_key": "curated:equinix-mu4-munich-data-center",
        "project_key": "curated:equinix-mu4-munich-data-center:phase-3",
    },
    QTS_SOURCE: {
        "sha256": "cbbd00b617cc0150cf6ad5b5ce70f12c7e108f7aed78067a18b11a6a1cb92ea5",
        "bytes": 20_008,
        "evidence_count": 3,
        "campus_key": "curated:qts-hall-county-data-center-campus",
        "project_key": (
            "curated:qts-hall-county-data-center-campus:proposed-building-program"
        ),
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "edged-council-bluffs-first-data-center-topout-2026-07-17-captured-2026-07-20": {
        "body_bytes": 111_902,
        "body_sha256": "007da7d0a085b98374f64c7c6bc7d5a916613e8585fa7a3d5ede12a390602aed",
        "headers_bytes": 5_347,
        "headers_sha256": "9accb33fa746e9a8e79d8fbde9d5d71ee0a457362035657ac113e1caeaff0d10",
        "writeout_bytes": 17_686,
        "writeout_sha256": "4fd089597f4c530f08e31bd3d72794163dfd5f9ded8c0aec980bb6bf4fc69b88",
        "response_http_date": "2026-07-20T06:08:14Z",
        "source_url": (
            "https://www.linkedin.com/posts/edgedenergy_edgedus-councilbluffs-"
            "omaha-activity-7483966398021390336-wI13"
        ),
    },
    "edged-council-bluffs-groundbreaking-capacity-release-captured-2026-07-20": {
        "body_bytes": 80_140,
        "body_sha256": "d5644b680decb7be50aa40a7272070a580c6630256cc236e8cd05c9efbf4a7d8",
        "headers_bytes": 756,
        "headers_sha256": "45f6e883c3bf51791a504c7970e29f1203edfd275c3b8ed7e499c9a36eb71bc1",
        "writeout_bytes": 9_554,
        "writeout_sha256": "36f722a53679842dc25e7edc4f3942c6e01ea8539272ef07b7abe525e2629725",
        "response_http_date": "2026-07-20T06:08:14Z",
        "source_url": (
            "https://edged.us/news/edged-breaks-ground-on-200-mw-council-"
            "bluffs-data-center-to-power-ai"
        ),
    },
    "edged-council-bluffs-admin-building-topout-guardrail-captured-2026-07-20": {
        "body_bytes": 109_344,
        "body_sha256": "f8cfbc2baa50b76f0bd7afb2b81ddfcaccc73f7ab7535f9883c772803b4b2c15",
        "headers_bytes": 5_348,
        "headers_sha256": "91e37467ea47ac45e98c1ad9b145c3280d002855d1de785263fd3a0c7f3b6f3a",
        "writeout_bytes": 17_692,
        "writeout_sha256": "0e5bde2540b7821c6e30a6dccc7479557833b422ac7af08d7763dd2174a7d5b5",
        "response_http_date": "2026-07-20T06:09:20Z",
        "source_url": (
            "https://www.linkedin.com/posts/edgedenergy_edgedus-councilbluffs-"
            "omaha-activity-7475939502033780736-jM2n"
        ),
    },
    "telangana-aws-bharat-future-city-groundbreaking-2026-07-15-captured-2026-07-20": {
        "body_bytes": 176_472,
        "body_sha256": "66a63cf560f4aa37f236450a101bb3893f196f82e030846ffb3a526437ee50ce",
        "headers_bytes": 720,
        "headers_sha256": "8a85fc46451dac02982375c1c6458e1b1c09e43cf8e77bc0bb312d9151cc8f11",
        "writeout_bytes": 14_875,
        "writeout_sha256": "931c9885ef126c2a418bb588a6397ed1103a7e8be9ea98b05fe36fb69fedb912",
        "response_http_date": "2026-07-20T06:08:15Z",
        "source_url": (
            "https://www.telangana.gov.in/news/press-releases/2026/07/"
            "honble-cm-sri-a-revanth-reddy-participated-in-groundbreaking-"
            "ceremony-of-amazon-data-centre-at-bharat-future-city-ranga-"
            "reddy-district-aws/"
        ),
    },
    "mercury-equinix-mu4-phase-3-topout-2026-07-16-captured-2026-07-20": {
        "body_bytes": 58_388,
        "body_sha256": "f34a6e2809d6b8e62fff00f22adfa92a5de72bafbab9b78e3bae2c1da0185a7c",
        "headers_bytes": 1_028,
        "headers_sha256": "12c94a81cf13917b463d7504eaf7d632a575ed3fcf789168eee5c0b31654815f",
        "writeout_bytes": 15_596,
        "writeout_sha256": "7299bd6c71f130a08727034027ed0f8363ba2292cbe7b2fbd59b26d12c97cd94",
        "response_http_date": "2026-07-20T06:08:14Z",
        "source_url": (
            "https://www.mercuryeng.com/2026/07/16/mercury-marks-significant-"
            "milestone-at-equinixs-mu4-3-data-centre-delivery-in-munich-germany/"
        ),
    },
    "qts-hall-county-proposed-campus-page-captured-2026-07-20": {
        "body_bytes": 417_052,
        "body_sha256": "bb29cfd601e61fca4b592e95ccbd5d783affcb61e1c29b32276262788f13b3de",
        "headers_bytes": 949,
        "headers_sha256": "f3e0b9f2cbdc0d0bf3453b92276a00ac11c76cfbee18e875928e40102a8118e6",
        "writeout_bytes": 9_340,
        "writeout_sha256": "935238a063f4d0b3f6c3155efe65310c6bf8c38401844171d5c35ed4b682ab78",
        "response_http_date": "2026-07-20T06:11:59Z",
        "source_url": "https://q.com/data-centers/hall-county/",
    },
    "qts-lancium-hall-county-joint-announcement-2026-07-13-captured-2026-07-20": {
        "body_bytes": 274_843,
        "body_sha256": "be25581b1a3dce19d5edea08167d0284ff15a86cb0440e3b1a830d54ca180a7d",
        "headers_bytes": 942,
        "headers_sha256": "da1cd7c9178cc253ca0817e235791dc6cc00b13d893dbdde146b7ab409d88975",
        "writeout_bytes": 9_521,
        "writeout_sha256": "84674e05a20b30e66084729b6fd22720e491256b8cec93b4c645e1cd88a97061",
        "response_http_date": "2026-07-20T06:11:57Z",
        "source_url": (
            "https://q.com/news/qts-and-lancium-announce-data-center-campus-"
            "in-hall-county-texas/"
        ),
    },
    "lancium-hall-county-clean-campus-page-captured-2026-07-20": {
        "body_bytes": 91_863,
        "body_sha256": "1105a5351ac02c797f067de5fdad6544f8deadf5fd697d66f414c806b849b359",
        "headers_bytes": 1_480,
        "headers_sha256": "2ce6a98c7658945944eb06902d45c82b49fbb0ed45ef0860611e809df4de709f",
        "writeout_bytes": 12_702,
        "writeout_sha256": "3656b3291dc92fa51558df67b146d0710870c0feb64a6ef92285dfd568b732ed",
        "response_http_date": "2026-07-20T06:11:58Z",
        "source_url": "https://lancium.com/locations-hall-county/",
    },
}


class JulyPrimaryBuildCuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

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

    def _state(
        self,
        order: tuple[str, ...],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=RETRIEVED_AT_BY_SOURCE[name],
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at, created_from_evidence_id "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, recorded_at",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, recorded_at",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "as_of_date, recorded_at, target_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT projects.entity_id, projects.target_entity_id "
                    "FROM projects ORDER BY projects.entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_exact_sources_are_hash_pinned_canonical_json(self) -> None:
        self.assertEqual(len(NEW_SOURCES), 4)
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(path.stat().st_size, expected["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(
                    len(document["evidence"]), expected["evidence_count"]
                )
                self.assertEqual(
                    document["campus"]["stable_key"], expected["campus_key"]
                )
                self.assertEqual(
                    document["project"]["stable_key"], expected["project_key"]
                )

        self.assertEqual(
            hashlib.sha256(self._path(MU4_IDENTITY_SOURCE).read_bytes()).hexdigest(),
            "bdd5a3b404a5a628694db043735cdafb4bf72604b20887bd49ce0de751623c6f",
        )
        self.assertEqual(
            hashlib.sha256(self._path(CHILDRESS_SOURCE).read_bytes()).hexdigest(),
            "d81e9f86ce56d0521debfa32e9cfb8ad6d30412183e66bbb347602f005ad4c7c",
        )

    def test_exact_capture_contract_is_closed_and_byte_bound(self) -> None:
        observed: dict[str, dict[str, Any]] = {}
        for name in NEW_SOURCES:
            retrieved_at = RETRIEVED_AT_BY_SOURCE[name]
            for evidence in self._load(name)["evidence"]:
                self.assertEqual(evidence["retrieved_at"], retrieved_at)
                self.assertNotIn(evidence["key"], observed)
                observed[evidence["key"]] = evidence

        self.assertEqual(set(observed), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                evidence = observed[key]
                metadata = evidence["metadata"]
                self.assertEqual(evidence["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['headers_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["response_http_date"]
                )
                self.assertEqual(evidence["source_url"], expected["source_url"])
                self.assertEqual(metadata["canonical_url"], expected["source_url"])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("retries disabled", metadata["retrieval_method"])
                self.assertIn(
                    "supplied no Authorization",
                    metadata["request_credentials_guardrail"],
                )
                self.assertIn("not redistributed", metadata["rights_scope"])
                self.assertIn(
                    "satellite imagery", metadata["imagery_guardrail"].lower()
                )

    def test_edged_first_data_center_shell_and_campus_capacity_are_scoped(self) -> None:
        document = self._load(EDGED_SOURCE)
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": (
                        "edged-council-bluffs-first-data-center-topout-2026-07-17-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-17",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
                capacity["as_of_date"],
            ),
            ("campus", "critical_it_mw", "planned", 200, 200, 200, "2025-10-29"),
        )
        self.assertIn("not allocated", capacity["notes"])
        self.assertIn("not installed", capacity["notes"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["campus"]["roles"], {})
        self.assertEqual(document["project"]["roles"], {})

        evidence = {item["key"]: item for item in document["evidence"]}
        admin = evidence[
            "edged-council-bluffs-admin-building-topout-guardrail-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(admin["activity_id"], "7475939502033780736")
        self.assertTrue(admin["edited_marker_present"])
        self.assertIn("administrative building", admin["administrative_building_exclusion"])
        self.assertIn("creates no data-center entity", admin["administrative_building_exclusion"])
        first = evidence[
            "edged-council-bluffs-first-data-center-topout-2026-07-17-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(first["activity_id"], "7483966398021390336")
        self.assertIn("not assigned", first["capacity_scope"])

    def test_aws_groundbreaking_is_generic_construction_not_foundations(self) -> None:
        document = self._load(AWS_SOURCE)
        for entity in (document["campus"], document["project"]):
            self.assertIsNone(entity["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "telangana-aws-bharat-future-city-groundbreaking-2026-07-15-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-15",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertNotIn("foundations", {row["value"] for row in document["lifecycle"]})
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("ceremonial", metadata["foundation_stage_guardrail"])
        self.assertIn("must not create", metadata["foundation_stage_guardrail"])
        self.assertIn("$7 billion", metadata["investment_wording_as_reported"])
        self.assertIn("metadata only", metadata["investment_scope"])
        self.assertIn("no MW", metadata["capacity_guardrail"])
        self.assertIn("addresses remain null", metadata["location_guardrail"])

    def test_mu4_reuses_exact_identity_and_advances_only_phase_to_shell(self) -> None:
        historical = self._load(MU4_IDENTITY_SOURCE)
        current = self._load(MU4_CURRENT_SOURCE)
        self.assertEqual(current["campus"]["stable_key"], historical["campus"]["stable_key"])
        self.assertEqual(
            current["project"]["stable_key"], historical["project"]["stable_key"]
        )
        self.assertEqual(current["campus"]["name"], historical["campus"]["name"])
        self.assertEqual(current["project"]["name"], historical["project"]["name"])
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in historical["lifecycle"]],
            [("under_construction", "2025-12-31")],
        )
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in current["lifecycle"]],
            [("shell", "2026-07-16")],
        )
        self.assertEqual(current["capacities"], [])
        self.assertEqual(current["operating_models"], [])
        self.assertEqual(current["workloads"], [])
        metadata = current["evidence"][0]["metadata"]
        self.assertIn("imported alongside", metadata["identity_reuse_scope"])
        self.assertIn("future/incomplete", metadata["fitout_guardrail"])
        self.assertIn("must not be converted", metadata["phase_operation_guardrail"])

    def test_qts_hall_county_is_one_proposed_program_with_no_power_row(self) -> None:
        document = self._load(QTS_SOURCE)
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "proposed",
                    "evidence_key": "qts-hall-county-proposed-campus-page-captured-2026-07-20",
                    "as_of_date": "2026-07-13",
                    "method": "authoritative_announcement",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["campus"]["roles"], {"owner": ["Lancium"]})
        self.assertEqual(
            document["project"]["roles"],
            {
                "developer": ["QTS Data Centers"],
                "operator": ["QTS Data Centers"],
            },
        )
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        evidence = {item["key"]: item for item in document["evidence"]}
        qts_page = evidence[
            "qts-hall-county-proposed-campus-page-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(qts_page["maximum_building_count_as_reported"], 11)
        self.assertIn("creates no eleven", qts_page["building_count_guardrail"])
        self.assertIn("early planning", qts_page["planning_wording_as_reported"])
        lancium = evidence[
            "lancium-hall-county-clean-campus-page-captured-2026-07-20"
        ]["metadata"]
        self.assertIn("1 GW", lancium["interconnect_scope"])
        self.assertIn("not allocated", lancium["interconnect_scope"])
        self.assertIn("QTS critical IT", lancium["one_gw_exclusion"])
        self.assertIn("secured power", lancium["one_gw_exclusion"])
        self.assertIn("does not advance", lancium["status_scope_guardrail"])
        self.assertIn("Childress", lancium["identity_nonmerge_guardrail"])
        stable_keys = {document["campus"]["stable_key"], document["project"]["stable_key"]}
        self.assertFalse(
            any(":building-" in key or "childress" in key for key in stable_keys)
        )

    def test_new_keys_are_globally_collision_safe_except_explicit_mu4_reuse(self) -> None:
        entity_occurrences: dict[str, set[str]] = defaultdict(set)
        evidence_occurrences: dict[str, set[str]] = defaultdict(set)
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None:
                    entity_occurrences[entity["stable_key"]].add(path.name)
            for evidence in document["evidence"]:
                evidence_occurrences[evidence["key"]].add(path.name)

        for name, expected in SOURCE_SPECS.items():
            for key_name in ("campus_key", "project_key"):
                key = expected[key_name]
                expected_files = {name}
                if name == MU4_CURRENT_SOURCE:
                    expected_files.add(MU4_IDENTITY_SOURCE)
                self.assertEqual(entity_occurrences[key], expected_files, key)

        for name in NEW_SOURCES:
            for evidence in self._load(name)["evidence"]:
                self.assertEqual(evidence_occurrences[evidence["key"]], {name})

    def test_each_new_source_imports_offline_in_isolation(self) -> None:
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT_BY_SOURCE[name],
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                    expected_capacity_count = int(name == EDGED_SOURCE)
                    expected_counts = {
                        "evidence": expected["evidence_count"],
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": expected_capacity_count,
                    }
                    for table, count in expected_counts.items():
                        self.assertEqual(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0],
                            count,
                            table,
                        )
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_combined_import_is_offline_order_independent_and_idempotent(self) -> None:
        forward = self._state(COMBINED_SOURCES)
        reverse = self._state(tuple(reversed(COMBINED_SOURCES)))
        repeated = self._state(COMBINED_SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            operating_models,
            workloads,
            projects,
        ) = forward
        self.assertEqual(len(entities), 8)
        self.assertEqual(len(evidence), 9)
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(len(lifecycle), 5)
        self.assertEqual(len(capacities), 1)
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 4)
        self.assertEqual(
            capacities[0][:7],
            (
                "curated:edged-council-bluffs-data-center-campus",
                "critical_it_mw",
                "planned",
                200.0,
                200.0,
                200.0,
                "2025-10-29",
            ),
        )
        self.assertEqual(
            {
                (row[0], row[1], row[2])
                for row in lifecycle
                if row[0].endswith(":phase-3")
            },
            {
                (
                    "curated:equinix-mu4-munich-data-center:phase-3",
                    "under_construction",
                    "2025-12-31",
                ),
                (
                    "curated:equinix-mu4-munich-data-center:phase-3",
                    "shell",
                    "2026-07-16",
                ),
            },
        )
        self.assertFalse(
            any(
                row[1] in {"operational", "foundations", "commissioning"}
                for row in lifecycle
            )
        )
        for row in snapshots:
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
