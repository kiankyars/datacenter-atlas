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
SOURCE = ROOT / "sources/curated-official-2026-07-20-flexential-parker-colorado-shell.json"
SOURCE_BYTES = 37_095
SOURCE_SHA256 = "caab2c8be10a81a8b26f2cc5acbfe3b4229dc9b8fbcbaef61028efb688fbb34a"
RETRIEVED_AT = "2026-07-20T09:51:24Z"
V47_SHA256 = "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"

CAMPUS_KEY = "curated:flexential-parker-compark-campus"
PROJECT_KEY = "curated:flexential-parker-compark-campus:first-data-center"
ADDRESS = "15255 Compark Boulevard, Parker, Colorado, United States"
PCL_KEY = "pcl-flexential-parker-topout-2026-03-17-captured-2026-07-20"
CORE_KEY = "core-flexential-parker-expansion-2024-05-20-captured-2026-07-20"
JUNE_KEY = "parker-june-2025-permits-flexential-piers-captured-2026-07-20"
SEPTEMBER_KEY = (
    "parker-september-2025-permits-flexential-foundation-captured-2026-07-20"
)
MANAGER_KEY = "parker-town-manager-winter-2026-flexential-captured-2026-07-20"
FAQ_KEY = "parker-faq-flexential-current-captured-2026-07-20"

CAPTURES = {
    PCL_KEY: {
        "publisher": "PCL Construction",
        "family": "pcl_construction_newsroom",
        "kind": "company_disclosure",
        "hash": "2a035b1965402af84cc1277b5e3a80a4d64a0d792024d2f446087a3b621884e2",
        "body_bytes": 67_737,
        "headers_hash": "8829f12421e2aa7580228335a29a5e19ea5c610d1755dee9ea0af33a2c2d57d1",
        "headers_bytes": 2_732,
        "curl_hash": "c2ebcdf13a1f6e7b3be5a273ccf62ad12b415722a4205ea69c875c3389b3a982",
        "curl_bytes": 11_638,
        "download": 14_655,
        "num_headers": 19,
        "blocks": 1,
        "redirects": 0,
        "content_type": "text/html;charset=utf-8",
        "encoding": "gzip",
        "content_length": 14_655,
        "response_date": RETRIEVED_AT,
        "requested": (
            "https://www.pcl.com/us/en/newsroom/press-releases/"
            "pcl-tops-out-192-million-ai-ready-data-center-as-denvers-digital-"
            "infrastructure-demand-accelerates"
        ),
        "effective": (
            "https://www.pcl.com/us/en/newsroom/press-releases/"
            "pcl-tops-out-192-million-ai-ready-data-center-as-denvers-digital-"
            "infrastructure-demand-accelerates"
        ),
    },
    CORE_KEY: {
        "publisher": "CORE Electric Cooperative",
        "family": "core_electric_cooperative_news",
        "kind": "utility_record",
        "hash": "7ffb84535325239dc4c52c43526f4519eb0fb78f5efc6fc3ae9cdebc1eb92637",
        "body_bytes": 202_910,
        "headers_hash": "a382b6f0163993efc90fedfc4b573359b9ccb662216e91ba2907b8eb6abe65e8",
        "headers_bytes": 837,
        "curl_hash": "1084d4fafc80c6df9c71389f1fc3e68df91df8a7a0e30373b05a586d8a24890e",
        "curl_bytes": 18_884,
        "download": 39_375,
        "num_headers": 22,
        "blocks": 1,
        "redirects": 0,
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "content_length": None,
        "response_date": RETRIEVED_AT,
        "requested": (
            "https://core.coop/community-partnerships-create-data-center-growth-"
            "in-douglas-county/"
        ),
        "effective": (
            "https://core.coop/community-partnerships-create-data-center-growth-"
            "in-douglas-county/"
        ),
    },
    JUNE_KEY: {
        "publisher": "Town of Parker, Colorado",
        "family": "town_of_parker_building_permit_reports",
        "kind": "government_record",
        "hash": "a292c31c0ad148698ec6700f60e39505b3cc791742ad15ed62d3d8888be0ceb3",
        "body_bytes": 515_020,
        "headers_hash": "225ff0caa4b69a4bb80a53899f88d418b53c23e859ab99beac6d0034f62f99c4",
        "headers_bytes": 889,
        "curl_hash": "4bafe4583e8aef9ea1a272b0f5df57f3aef8ce2974952d3499e4a6bde2a04c3a",
        "curl_bytes": 16_364,
        "download": 515_020,
        "num_headers": 11,
        "blocks": 1,
        "redirects": 0,
        "content_type": "application/pdf",
        "encoding": None,
        "content_length": 515_020,
        "response_date": "2026-07-20T09:51:23Z",
        "requested": "https://www.parkerco.gov/Archive/ViewFile/Item/7103",
        "effective": "https://www.parkerco.gov/Archive/ViewFile/Item/7103",
    },
    SEPTEMBER_KEY: {
        "publisher": "Town of Parker, Colorado",
        "family": "town_of_parker_building_permit_reports",
        "kind": "government_record",
        "hash": "3af8db882a28848bd18135fe96040bda9875b0af8509268bec0b67dafcc753a5",
        "body_bytes": 596_265,
        "headers_hash": "fbb37f6b797a39985123a61fe4638bbbec21878b08fcd69e68dfe0212adf16bb",
        "headers_bytes": 894,
        "curl_hash": "2227eae4e110830d4802c1976b52e5d82cfcf258b953ec61db075180693a2b22",
        "curl_bytes": 16_370,
        "download": 596_265,
        "num_headers": 11,
        "blocks": 1,
        "redirects": 0,
        "content_type": "application/pdf",
        "encoding": None,
        "content_length": 596_265,
        "response_date": "2026-07-20T09:51:23Z",
        "requested": "https://www.parkerco.gov/Archive/ViewFile/Item/7174",
        "effective": "https://www.parkerco.gov/Archive/ViewFile/Item/7174",
    },
    MANAGER_KEY: {
        "publisher": "Town of Parker, Colorado",
        "family": "town_of_parker_manager_reports",
        "kind": "government_record",
        "hash": "cc7c71270bc5a6528ad54902dd818769debf9152cff12d169d5895b2062d2393",
        "body_bytes": 1_469_154,
        "headers_hash": "d619b31dd18322671eee31e568defab22d28bcced019f5c98de44f0825ee9a91",
        "headers_bytes": 1_737,
        "curl_hash": "941a2ba5999012563062691253ded2c3cab38f8f618e5a1e81992d178ff483d5",
        "curl_bytes": 16_375,
        "download": 1_469_154,
        "num_headers": 11,
        "blocks": 2,
        "redirects": 1,
        "content_type": "application/pdf",
        "encoding": None,
        "content_length": 1_469_154,
        "response_date": "2026-07-20T09:51:23Z",
        "requested": "https://www.parkerco.gov/Archive.aspx?ADID=7206",
        "effective": "https://www.parkerco.gov/ArchiveCenter/ViewFile/Item/7206",
    },
    FAQ_KEY: {
        "publisher": "Town of Parker, Colorado",
        "family": "town_of_parker_faq",
        "kind": "government_record",
        "hash": "5cac13b254611c6a13f7fffb8909c11bbd2e7299b38d6068bcc076cebbf937a9",
        "body_bytes": 304_367,
        "headers_hash": "514a42588c779095b5817e4f744e2ebf0d4d8db21eb1654c1ec0e8a5e64fea90",
        "headers_bytes": 1_554,
        "curl_hash": "ecdc05aecfed9837e556b61881a8ecc12698c2922f336138da0c7b7a68d8b978",
        "curl_bytes": 16_281,
        "download": 73_209,
        "num_headers": 11,
        "blocks": 2,
        "redirects": 1,
        "content_type": "text/html; charset=utf-8",
        "encoding": "gzip",
        "content_length": None,
        "response_date": "2026-07-20T09:51:23Z",
        "requested": "https://www.parkerco.gov/FAQ.aspx",
        "effective": "https://www.parkerco.gov/m/faq",
    },
}


class FlexentialParkerColoradoShellCuratedTests(unittest.TestCase):
    def _load(self) -> dict[str, Any]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Flexential Parker curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            path = Path(temporary) / SOURCE.name
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

    def _state(self, repetitions: int = 1) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            SOURCE,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(result.entities_created, 2 if iteration == 0 else 0)
                        self.assertEqual(result.evidence_created, 6 if iteration == 0 else 0)
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT content_hash, retrieved_at, source_url FROM evidence "
                    "ORDER BY content_hash",
                    "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
                    "tags_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, method, "
                    "confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date, "
                    "target_date, recorded_at, method, confidence FROM capacity_estimates "
                    "JOIN entities ON entities.id = capacity_estimates.entity_id",
                    "SELECT entities.stable_key, operating_model, as_of_date, recorded_at, "
                    "method, confidence FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, method, "
                    "confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        self.assertEqual(SOURCE.stat().st_size, SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        text = SOURCE.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")
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

    def test_capture_contracts_are_exact_closed_and_telemetry_free(self) -> None:
        forbidden = {
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
        records = {record["key"]: record for record in self._load()["evidence"]}
        self.assertEqual(set(records), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(key=key):
                record = records[key]
                metadata = record["metadata"]
                self.assertEqual(record["kind"], expected["kind"])
                self.assertEqual(record["publisher"], expected["publisher"])
                self.assertEqual(record["source_family"], expected["family"])
                self.assertEqual(record["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(record["content_hash"], expected["hash"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte', metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_hash"]
                )
                self.assertIn(
                    f'{expected["headers_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"], expected["curl_hash"]
                )
                self.assertIn(
                    f'{expected["curl_bytes"]}-byte',
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["content_encoding_as_received"], expected["encoding"]
                )
                self.assertIsNone(metadata["http_transfer_encoding_as_received"])
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download"],
                )
                self.assertEqual(
                    metadata["curl_size_header_bytes"], expected["headers_bytes"]
                )
                self.assertEqual(metadata["curl_num_headers"], expected["num_headers"])
                self.assertEqual(metadata["response_header_blocks"], expected["blocks"])
                self.assertEqual(metadata["redirect_count"], expected["redirects"])
                self.assertEqual(metadata["response_http_date"], expected["response_date"])
                self.assertEqual(metadata["requested_url"], expected["requested"])
                self.assertEqual(metadata["effective_url"], expected["effective"])
                self.assertTrue(
                    forbidden.isdisjoint(field.casefold() for field in metadata)
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )

    def test_exact_identity_roles_address_and_no_geocode(self) -> None:
        document = self._load()
        expected_roles = {
            "developer": ["Flexential", "Westside Partners"],
            "operator": ["Flexential"],
            "contractor": ["PCL Construction"],
            "utility": ["CORE Electric Cooperative"],
        }
        for entity, key, name in (
            (document["campus"], CAMPUS_KEY, "Flexential Parker Compark Campus"),
            (document["project"], PROJECT_KEY, "Flexential Parker Data Center"),
        ):
            self.assertEqual(entity["stable_key"], key)
            self.assertEqual(entity["name"], name)
            self.assertEqual(entity["country"], "United States")
            self.assertEqual(entity["address"], ADDRESS)
            self.assertEqual(entity["roles"], expected_roles)
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], SEPTEMBER_KEY)
            self.assertEqual(entity["as_of_date"], "2025-09-25")
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        permit = document["evidence"][3]["metadata"]
        self.assertEqual(permit["address_as_reported"], "15255 COMPARK BLVD")
        self.assertEqual(permit["address_point_geo_record_as_reported"], "223305207005")
        identity_scope = document["evidence"][1]["metadata"]["identity_scope"]
        self.assertIn("municipal address-point record", identity_scope)
        self.assertIn("not a parcel identifier", identity_scope)
        resolution = document["evidence"][0]["metadata"]["identity_resolution_scope"]
        for fingerprint in (
            "named permit applicant",
            "22.5 MW",
            "17 acres",
            "CORE independently ties Flexential to Parker",
            "277,000 square feet",
            "276,200",
            "15255 Compark Boulevard",
            "223305207005",
        ):
            self.assertIn(fingerprint, resolution)

    def test_physical_status_is_shell_only_and_permits_are_not_observations(self) -> None:
        document = self._load()
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": PCL_KEY,
                    "as_of_date": "2026-03-17",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        physical_scope = document["evidence"][0]["metadata"]["physical_scope"]
        for unsupported in (
            "MEP completion",
            "energization",
            "commissioning",
            "occupancy",
            "overall completion",
            "operation",
            "current load",
        ):
            self.assertIn(unsupported, physical_scope)
        for record in document["evidence"][2:5]:
            guardrail = record["metadata"].get(
                "permit_status_guardrail", record["metadata"].get("status_scope")
            )
            self.assertIn("no", guardrail)
            self.assertIn("lifecycle", guardrail)

    def test_grid_connection_is_planned_and_not_load_or_energy(self) -> None:
        document = self._load()
        self.assertEqual(
            document["capacities"],
            [
                {
                    "entity": "project",
                    "metric": "grid_connection_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": 22.5,
                    "base": 22.5,
                    "high": 22.5,
                    "method": "reported",
                    "confidence": 0.99,
                    "evidence_key": CORE_KEY,
                    "as_of_date": "2024-05-20",
                    "target_date": None,
                    "notes": document["capacities"][0]["notes"],
                }
            ],
        )
        notes = document["capacities"][0]["notes"]
        for unsupported in (
            "critical IT",
            "current draw",
            "annual energy",
            "measured consumption",
            "proof of operation",
        ):
            self.assertIn(unsupported, notes)
        self.assertFalse(
            any(
                row["metric"]
                in {"critical_it_mw", "annual_energy_mwh", "generation_nameplate_mw"}
                for row in document["capacities"]
            )
        )

    def test_type_claims_are_intended_and_bounded(self) -> None:
        document = self._load()
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": CORE_KEY,
                    "as_of_date": "2024-05-20",
                    "method": "utility_record",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["workloads"], [])
        workload_scope = document["evidence"][0]["metadata"]["workload_scope"]
        self.assertIn("AI-ready design capability only", workload_scope)
        self.assertIn("no normalized workload row", workload_scope)
        for unsupported in (
            "training-versus-inference",
            "installed-accelerator",
            "named model",
            "tenant",
            "current compute activity",
            "utilization",
            "exclusivity to AI",
        ):
            self.assertIn(unsupported, workload_scope)
        self.assertIn(
            "not current service",
            document["evidence"][1]["metadata"]["operating_model_scope"],
        )

    def test_cooling_and_backup_generation_remain_qualitative_metadata(self) -> None:
        faq = self._load()["evidence"][5]["metadata"]
        self.assertIn("intended closed-loop", faq["cooling_scope"])
        self.assertIn("no zero-water-consumption claim", faq["water_guardrail"])
        self.assertIn("no voltage", faq["electricity_scope"])
        self.assertIn("no number", faq["backup_generation_scope"])
        self.assertIn("No generation row", faq["backup_generation_scope"])

    def test_offline_import_is_valid_exact_and_idempotent(self) -> None:
        state = self._state()
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = state
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(len(evidence), 6)
        self.assertEqual({row[1] for row in evidence}, {RETRIEVED_AT})
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        for row in snapshots:
            self.assertEqual(row[2:5], (None, None, None))
            tags = json.loads(row[5])
            self.assertEqual(tags["address"], ADDRESS)
            self.assertEqual(tags["role:operator"], "Flexential")
            self.assertEqual(tags["role:utility"], "CORE Electric Cooperative")
        self.assertEqual(
            lifecycle,
            ((PROJECT_KEY, "shell", "2026-03-17", RETRIEVED_AT, "authoritative_physical_status_update", 0.99),),
        )
        self.assertEqual(
            capacities,
            ((PROJECT_KEY, "grid_connection_mw", "planned", 22.5, "2024-05-20", None, RETRIEVED_AT, "reported", 0.99),),
        )
        self.assertEqual(
            models,
            ((PROJECT_KEY, "colocation", "2024-05-20", RETRIEVED_AT, "utility_record", 0.99),),
        )
        self.assertEqual(workloads, ())
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))
        self.assertEqual(self._state(repetitions=2), state)

    def test_keys_are_collision_free_and_v47_is_unchanged(self) -> None:
        document = self._load()
        entity_keys = {document["campus"]["stable_key"], document["project"]["stable_key"]}
        evidence_keys = {record["key"] for record in document["evidence"]}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path == SOURCE:
                continue
            other = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                record = other.get(field)
                if isinstance(record, dict):
                    self.assertNotIn(record.get("stable_key"), entity_keys, path)
            for record in other.get("evidence", []):
                self.assertNotIn(record.get("key"), evidence_keys, path)
        v47 = ROOT / "sources/open-seed-2026-07-20-v47.json"
        self.assertEqual(hashlib.sha256(v47.read_bytes()).hexdigest(), V47_SHA256)
        self.assertNotIn(SOURCE.name, v47.read_text(encoding="utf-8"))

    def test_import_rejects_weak_shell_method_and_inferred_coordinates(self) -> None:
        document = copy.deepcopy(self._load())
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

        document = copy.deepcopy(self._load())
        document["campus"]["coordinates"] = {
            "latitude": 39.5,
            "longitude": -104.8,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
