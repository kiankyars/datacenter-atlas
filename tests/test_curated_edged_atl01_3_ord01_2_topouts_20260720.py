from __future__ import annotations

import copy
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
RETRIEVED_AT = "2026-07-20T09:40:57Z"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"

REJECTED_COORDINATE_SUCCESSORS = {
    "curated-official-2026-07-20-edged-atl01-3-atlanta-topout-v2.json": (
        "6011e9ed8172d940d15df2d0da46e4ec1c98014dc5dae47eb94a4c7125c16ded"
    ),
    "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json": (
        "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json": (
        "6cd9f44731f769cf03e68ec41ee018ac312a6f41ef2ddbb462bdd6f91f2fa728"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json": (
        "d053d2a638a73c8730e1c3eae22c2f7ac83842edff2f62e04ae30b231f70c15d"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json": (
        "4248a4487577cf53f56ba9d90aa5c0ad2b8e0a8330607e4fb5fc1bd25d719376"
    ),
}

ACCEPTED_COORDINATE_SUCCESSORS = {
    "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v3.json": (
        "a61e7d4f4c4374a99b62b52980903c94e7b8c2659a8470045530fbc2cb55fe4e"
    ),
}

CASES = {
    "atlanta": {
        "source_name": "curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json",
        "source_bytes": 18_128,
        "source_sha256": "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06",
        "campus_key": "curated:edged-atlanta-campus",
        "project_key": "curated:edged-atlanta-campus:atl01-03",
        "campus_name": "Edged Atlanta Data Center Campus",
        "project_name": "Edged Atlanta ATL01-03",
        "campus_address": "Thomas Street NW, Atlanta, Georgia 30318, United States",
        "project_address": "1740 Thomas Street NW, Atlanta, Georgia 30318, United States",
        "topout_key": "edged-atl01-3-topout-2026-04-24-captured-2026-07-20",
        "location_key": "edged-atlanta-location-page-captured-2026-07-20",
        "topout_url": (
            "https://edged.us/news/edged-us-tops-out-ultra---efficient-42-mw-"
            "data-center-optimized-for-ai-inference-at-scale-at-its-atlanta-campus"
        ),
        "location_url": "https://edged.us/atlanta",
        "topout_hash": "a8079ad7a12d05e6b28201e406b5bda6ada0b0811daeb75b8621155edd9569ae",
        "location_hash": "780f482af9c6895c665758ec8eba32110b1fe2592ee82278c0d9d55d6a73504c",
        "topout_body_bytes": 81_558,
        "location_body_bytes": 103_995,
        "topout_headers_bytes": 755,
        "location_headers_bytes": 735,
        "topout_curl_bytes": 9_736,
        "location_curl_bytes": 9_302,
        "topout_headers_hash": "5b5e6bcd1488db64f28868345e495a385152c6b144814cc85073f44350909e9c",
        "location_headers_hash": "afc199eaf2f7a2353d65556c5cad4c1a0a89de451c855f473a5b40e6df661afb",
        "topout_curl_hash": "1a1ec356df3ecc42c5899b699adb21eb16b0d381cc6da747ba1b920ea32df304",
        "location_curl_hash": "f9c41cde312ffa3cbafb4200776cbffdf5521558eac485fab9166474862703d5",
        "topout_download": 31_580,
        "location_download": 39_152,
        "topout_headers": 16,
        "location_headers": 16,
        "topout_published": "2026-04-24",
        "lifecycle_date": "2026-04-23",
        "project_capacity": 42,
        "campus_capacity": 169,
    },
    "chicago": {
        "source_name": "curated-official-2026-07-20-edged-ord01-2-chicago-topout.json",
        "source_bytes": 17_750,
        "source_sha256": "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
        "campus_key": "curated:edged-chicago-aurora-campus",
        "project_key": "curated:edged-chicago-aurora-campus:ord01-2",
        "campus_name": "Edged Chicago Aurora Data Center Campus",
        "project_name": "Edged Chicago ORD01-2",
        "campus_address": "2835 Bilter Road, Aurora, Illinois 60502, United States",
        "project_address": "2835 Bilter Road, Aurora, Illinois 60502, United States",
        "topout_key": "edged-ord01-2-topout-2026-06-04-captured-2026-07-20",
        "location_key": "edged-chicago-location-page-captured-2026-07-20",
        "topout_url": (
            "https://edged.us/news/edged-us-tops-out-second-sustainable-data-center-"
            "on-edged-chicago-campus"
        ),
        "location_url": "https://edged.us/chicago",
        "topout_hash": "72d0a1d58baf39debeb75176a2ec76459f83b9065c73070515fc2892bec27848",
        "location_hash": "d4110379d78f1108a4d6323c507dac307fafa23c5b4f07a1387793ad5165befe",
        "topout_body_bytes": 80_926,
        "location_body_bytes": 106_458,
        "topout_headers_bytes": 743,
        "location_headers_bytes": 735,
        "topout_curl_bytes": 9_580,
        "location_curl_bytes": 9_302,
        "topout_headers_hash": "fd74ce55443724f63e5585744a859053826ca4d26194a9e5435d6206154e6dff",
        "location_headers_hash": "2571406d21e7a417bbb40de82d25e22e8a9254b361ef5feb491dd08e8eaa06b4",
        "topout_curl_hash": "cc8ec695087c652062cace229e67b83e16ada48b2da4b4d20f467604df1991c7",
        "location_curl_hash": "64cc73b88f3c0f7100e5d7fbf94dd57e4135d2b0ff506363ed68f66dc552a861",
        "topout_download": 31_252,
        "location_download": 39_315,
        "topout_headers": 15,
        "location_headers": 16,
        "topout_published": "2026-06-04",
        "lifecycle_date": "2026-06-04",
        "project_capacity": 72,
        "campus_capacity": 96,
    },
}


class EdgedAtlantaChicagoTopoutCuratedTests(unittest.TestCase):
    def _path(self, case: dict[str, Any]) -> Path:
        return ROOT / "sources" / case["source_name"]

    def _load(self, case: dict[str, Any]) -> dict[str, Any]:
        return json.loads(self._path(case).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Edged curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import_document(self, case: dict[str, Any], document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            path = Path(temporary) / case["source_name"]
            path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    path,
                    retrieved_at=RETRIEVED_AT,
                )
            finally:
                connection.close()

    def _state(
        self, *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        for case in CASES.values():
                            result = CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(case),
                                retrieved_at=RETRIEVED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                            self.assertEqual(
                                result.entities_created,
                                2 if iteration == 0 else 0,
                            )
                            self.assertEqual(
                                result.evidence_created,
                                2 if iteration == 0 else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), content_hash, "
                    "retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
                    "as_of_date, recorded_at, method, confidence FROM entity_snapshots "
                    "JOIN entities ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, method, "
                    "confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date, target_date, "
                    "recorded_at, method, confidence FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, method, "
                    "confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload",
                    "SELECT COUNT(*) FROM operating_model_observations",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        for label, case in CASES.items():
            with self.subTest(label=label):
                path = self._path(case)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(path.stat().st_size, case["source_bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    case["source_sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
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

    def test_capture_contracts_are_exact_closed_and_zero_redirect(self) -> None:
        forbidden_telemetry_keys = {
            "authorization",
            "certs",
            "cookie",
            "local_ip",
            "local_port",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for label, case in CASES.items():
            with self.subTest(label=label):
                records = self._load(case)["evidence"]
                self.assertEqual(len(records), 2)
                by_key = {record["key"]: record for record in records}
                self.assertEqual(
                    set(by_key), {case["topout_key"], case["location_key"]}
                )
                self.assertEqual(
                    by_key[case["topout_key"]]["source_family"],
                    "edged_newsroom",
                )
                for kind in ("topout", "location"):
                    record = by_key[case[f"{kind}_key"]]
                    metadata = record["metadata"]
                    self.assertEqual(record["kind"], "company_disclosure")
                    self.assertEqual(record["publisher"], "Edged US")
                    self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
                    self.assertEqual(record["source_url"], case[f"{kind}_url"])
                    self.assertEqual(record["content_hash"], case[f"{kind}_hash"])
                    self.assertIn(
                        f"{case[f'{kind}_body_bytes']}-byte",
                        metadata["content_hash_scope"],
                    )
                    self.assertEqual(
                        metadata["capture_headers_sha256"],
                        case[f"{kind}_headers_hash"],
                    )
                    self.assertIn(
                        f"{case[f'{kind}_headers_bytes']}-byte",
                        metadata["capture_headers_scope"],
                    )
                    self.assertEqual(
                        metadata["capture_curl_writeout_sha256"],
                        case[f"{kind}_curl_hash"],
                    )
                    self.assertIn(
                        f"{case[f'{kind}_curl_bytes']}-byte",
                        metadata["capture_curl_writeout_scope"],
                    )
                    self.assertEqual(metadata["http_status"], 200)
                    self.assertEqual(metadata["curl_exit_code"], 0)
                    self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                    self.assertEqual(
                        metadata["content_type"], "text/html; charset=utf-8"
                    )
                    self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                    self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                    self.assertIsNone(metadata["http_content_length_bytes_as_received"])
                    self.assertEqual(
                        metadata["curl_size_download_bytes_as_received"],
                        case[f"{kind}_download"],
                    )
                    self.assertEqual(
                        metadata["curl_size_header_bytes"],
                        case[f"{kind}_headers_bytes"],
                    )
                    self.assertEqual(
                        metadata["curl_num_headers"], case[f"{kind}_headers"]
                    )
                    self.assertEqual(metadata["response_header_blocks"], 1)
                    self.assertEqual(metadata["redirect_count"], 0)
                    self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
                    for field in ("requested_url", "effective_url", "canonical_url"):
                        self.assertEqual(metadata[field], case[f"{kind}_url"])
                    self.assertTrue(
                        forbidden_telemetry_keys.isdisjoint(
                            {field.casefold() for field in metadata}
                        )
                    )
                    self.assertIn(
                        "not redistributed",
                        metadata["capture_artifact_guardrail"],
                    )
                self.assertEqual(
                    by_key[case["topout_key"]]["published_at"], case["topout_published"]
                )
                self.assertIsNone(by_key[case["location_key"]]["published_at"])

    def test_exact_identity_address_roles_and_no_geocode(self) -> None:
        expected_roles = {"developer": ["Edged US"], "operator": ["Edged US"]}
        for label, case in CASES.items():
            with self.subTest(label=label):
                document = self._load(case)
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], case["campus_key"])
                self.assertEqual(project["stable_key"], case["project_key"])
                self.assertEqual(campus["name"], case["campus_name"])
                self.assertEqual(project["name"], case["project_name"])
                self.assertEqual(campus["address"], case["campus_address"])
                self.assertEqual(project["address"], case["project_address"])
                self.assertEqual(campus["roles"], expected_roles)
                self.assertEqual(project["roles"], expected_roles)
                for entity in (campus, project):
                    self.assertEqual(entity["country"], "United States")
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["method"], "authoritative_locality")
                    self.assertEqual(entity["confidence"], 0.99)

    def test_topouts_are_shell_only(self) -> None:
        for label, case in CASES.items():
            with self.subTest(label=label):
                document = self._load(case)
                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": "shell",
                            "evidence_key": case["topout_key"],
                            "as_of_date": case["lifecycle_date"],
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                scope = document["evidence"][0]["metadata"]["construction_scope"]
                for unsupported in (
                    "MEP completion",
                    "energization",
                    "commissioning",
                    "completion",
                    "occupancy",
                    "operation",
                    "current load",
                ):
                    self.assertIn(unsupported, scope)

    def test_campus_and_project_capacities_are_nested_and_nonadditive(self) -> None:
        for label, case in CASES.items():
            with self.subTest(label=label):
                document = self._load(case)
                self.assertEqual(len(document["capacities"]), 2)
                by_entity = {row["entity"]: row for row in document["capacities"]}
                self.assertEqual(set(by_entity), {"campus", "project"})
                self.assertEqual(by_entity["campus"]["metric"], "critical_it_mw")
                self.assertEqual(by_entity["campus"]["stage"], "planned")
                self.assertEqual(by_entity["campus"]["base"], case["campus_capacity"])
                self.assertEqual(by_entity["project"]["metric"], "critical_it_mw")
                self.assertEqual(by_entity["project"]["stage"], "planned")
                self.assertEqual(by_entity["project"]["base"], case["project_capacity"])
                for row in by_entity.values():
                    self.assertEqual(row["low"], row["base"])
                    self.assertEqual(row["high"], row["base"])
                    self.assertEqual(row["unit"], "MW")
                    self.assertEqual(row["method"], "reported")
                    self.assertEqual(row["confidence"], 0.99)
                    self.assertIsNone(row["target_date"])
                    self.assertIn("not current load", row["notes"])
                self.assertIn("must not be summed", by_entity["campus"]["notes"])

    def test_types_are_intended_training_and_inference_only(self) -> None:
        for label, case in CASES.items():
            with self.subTest(label=label):
                document = self._load(case)
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(
                    document["workloads"],
                    [
                        {
                            "entity": "project",
                            "value": "ai_training",
                            "evidence_key": case["topout_key"],
                            "as_of_date": case["topout_published"],
                            "method": "company_disclosure",
                            "confidence": 0.99,
                        },
                        {
                            "entity": "project",
                            "value": "ai_inference",
                            "evidence_key": case["topout_key"],
                            "as_of_date": case["topout_published"],
                            "method": "company_disclosure",
                            "confidence": 0.99,
                        },
                    ],
                )
                metadata = document["evidence"][0]["metadata"]
                for unsupported in (
                    "installed accelerators",
                    "named models",
                    "current compute activity",
                    "utilization",
                ):
                    self.assertIn(unsupported, metadata["workload_scope"])
                self.assertIn(
                    "creates no tenant",
                    metadata.get("lease_guardrail", metadata.get("prelease_guardrail")),
                )

    def test_pue_water_and_energy_claims_remain_bounded(self) -> None:
        for label, case in CASES.items():
            with self.subTest(label=label):
                document = self._load(case)
                self.assertFalse(
                    any(row["metric"] == "pue" for row in document["capacities"])
                )
                self.assertFalse(
                    any(
                        row["metric"] == "annual_energy_mwh"
                        for row in document["capacities"]
                    )
                )
                topout = document["evidence"][0]["metadata"]
                location = document["evidence"][1]["metadata"]
                self.assertIn("modeled comparison", topout["water_energy_guardrail"])
                self.assertIn(
                    "no normalized energy row", topout["water_energy_guardrail"]
                )
                self.assertIn("portfolio-wide design PUE", location["pue_guardrail"])
                self.assertIn(
                    "no current water withdrawal", location["water_guardrail"]
                )
                self.assertIn(
                    "no source-supported MW or MWh sizes", location["power_guardrail"]
                )

    def test_offline_combined_import_is_valid_exact_and_idempotent(self) -> None:
        state = self._state()
        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            workloads,
            models,
            projects,
        ) = state
        self.assertEqual(len(entities), 4)
        self.assertEqual({row[2] for row in entities}, {RETRIEVED_AT})
        self.assertEqual(len(evidence), 4)
        self.assertEqual({row[2] for row in evidence}, {RETRIEVED_AT})
        self.assertEqual(len(snapshots), 4)
        self.assertEqual({row[6] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(
            lifecycle,
            (
                (
                    CASES["atlanta"]["project_key"],
                    "shell",
                    "2026-04-23",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
                (
                    CASES["chicago"]["project_key"],
                    "shell",
                    "2026-06-04",
                    RETRIEVED_AT,
                    "authoritative_physical_status_update",
                    0.99,
                ),
            ),
        )
        self.assertEqual(len(capacities), 4)
        self.assertEqual({row[2] for row in capacities}, {"planned"})
        self.assertEqual({row[3] for row in capacities}, {42.0, 72.0, 96.0, 169.0})
        self.assertEqual(len(workloads), 4)
        self.assertEqual({row[1] for row in workloads}, {"ai_training", "ai_inference"})
        self.assertEqual(models, ((0,),))
        self.assertEqual(
            projects,
            (
                (CASES["atlanta"]["project_key"], CASES["atlanta"]["campus_key"]),
                (CASES["chicago"]["project_key"], CASES["chicago"]["campus_key"]),
            ),
        )
        self.assertEqual(self._state(repetitions=2), state)

    def test_keys_are_collision_free_and_v44_is_unchanged(self) -> None:
        source_paths = {self._path(case) for case in CASES.values()}
        rejected_paths = {
            ROOT / "sources" / name for name in REJECTED_COORDINATE_SUCCESSORS
        }
        accepted_paths = {
            ROOT / "sources" / name for name in ACCEPTED_COORDINATE_SUCCESSORS
        }
        for name, expected_hash in REJECTED_COORDINATE_SUCCESSORS.items():
            rejected = ROOT / "sources" / name
            self.assertTrue(rejected.is_file())
            self.assertEqual(
                hashlib.sha256(rejected.read_bytes()).hexdigest(), expected_hash
            )
        for name, expected_hash in ACCEPTED_COORDINATE_SUCCESSORS.items():
            accepted = ROOT / "sources" / name
            self.assertTrue(accepted.is_file())
            self.assertEqual(
                hashlib.sha256(accepted.read_bytes()).hexdigest(), expected_hash
            )

        entity_keys: set[str] = set()
        evidence_keys: set[str] = set()
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path in source_paths or path in rejected_paths or path in accepted_paths:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                record = document.get(field)
                if isinstance(record, dict) and isinstance(
                    record.get("stable_key"), str
                ):
                    entity_keys.add(record["stable_key"])
            for record in document.get("evidence", []):
                if isinstance(record, dict) and isinstance(record.get("key"), str):
                    evidence_keys.add(record["key"])
        for case in CASES.values():
            self.assertNotIn(case["campus_key"], entity_keys)
            self.assertNotIn(case["project_key"], entity_keys)
            self.assertNotIn(case["topout_key"], evidence_keys)
            self.assertNotIn(case["location_key"], evidence_keys)

        v44 = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
        self.assertEqual(hashlib.sha256(v44.read_bytes()).hexdigest(), V44_SHA256)
        text = v44.read_text(encoding="utf-8")
        for case in CASES.values():
            self.assertNotIn(case["source_name"], text)

    def test_import_rejects_weak_method_for_shell(self) -> None:
        case = CASES["atlanta"]
        document = copy.deepcopy(self._load(case))
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(case, document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        case = CASES["chicago"]
        document = copy.deepcopy(self._load(case))
        document["campus"]["coordinates"] = {"latitude": 41.8, "longitude": -88.3}
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(case, document)


if __name__ == "__main__":
    unittest.main()
