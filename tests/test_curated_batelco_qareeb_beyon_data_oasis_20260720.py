from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT / "sources/curated-official-2026-07-20-batelco-qareeb-beyon-data-oasis.json"
)
STC_SOURCE = ROOT / "sources/curated-official-2026-07-20-stc-bahrain-dc-v2.json"
SOURCE_SHA256 = "80799190bd0e57ce9274a4f480a0108a2c65d907a0edcdd2a4f27e4ec04b3a5a"
STC_SOURCE_SHA256 = "4d8976e26d77a9b5aa9b4a247456af3b9274991e9f0751a73b64f862fc2af02e"
RECORDED_AT = "2026-07-21T04:10:00Z"
FIRST_EVIDENCE_KEY = (
    "batelco-qareeb-beyon-data-oasis-under-construction-2025-02-05-captured-2026-07-20"
)
LATEST_EVIDENCE_KEY = (
    "batelco-qareeb-beyon-data-oasis-operational-readiness-2026-01-13-"
    "captured-2026-07-20"
)
CAMPUS_KEY = "curated:batelco-qareeb-beyon-data-oasis-edge-data-center"
PROJECT_KEY = f"{CAMPUS_KEY}:facility-build"


class BatelcoQareebBeyonDataOasisTests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError("network used while importing curated source")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _import(self):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        result = CuratedOfficialSourceAdapterV11().import_file(
            connection, SOURCE, recorded_at=RECORDED_AT
        )
        return temporary, connection, result

    def test_source_is_canonical_byte_pinned_and_capture_scoped(self) -> None:
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), 14_529)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [FIRST_EVIDENCE_KEY, LATEST_EVIDENCE_KEY],
        )
        expected_capture_facts = (
            (
                "2ce4e63b9737ec842f7ee144d56428071a7b7b53028b0980007191bcaaa9a0cd",
                196_174,
                "8d2938f084312baf5a7c8e64c36074fe61e824d1be9112f7da4acab6a312556b",
                "ee727ba05a4c167ace97e4a3b5cea063211bd4ab3a5ca3971966e446f6417ad1",
            ),
            (
                "55e7dce53fa8089a229c4c5d900bf4bd900bb71f70d760a561b4a2a287a045ad",
                202_852,
                "4da5d4c77c8adb32d40cbc3613738a91dc4e976b67847eb49cbdd4258b0b3d7a",
                "adbbdb60884996914ba47d8dc939dfc038908583509357914346f6d689095f4c",
            ),
        )
        for evidence, (body_hash, body_bytes, header_hash, facts_hash) in zip(
            document["evidence"], expected_capture_facts, strict=True
        ):
            metadata = evidence["metadata"]
            self.assertEqual(evidence["content_hash"], body_hash)
            self.assertEqual(evidence["retrieved_at"], "2026-07-21T04:07:00Z")
            self.assertEqual(evidence["license"], "all-rights-reserved")
            self.assertEqual(metadata["http_status"], 200)
            self.assertIn(str(body_bytes), metadata["content_hash_scope"])
            self.assertEqual(metadata["capture_headers_sha256"], header_hash)
            self.assertEqual(metadata["capture_curl_writeout_sha256"], facts_hash)
            self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])

    def test_offline_import_has_exact_rows_roles_and_lifecycle_semantics(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, result = self._import()
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            self.assertEqual(result.entities_created, 2)
            self.assertEqual(result.evidence_created, 2)
            self.assertEqual(result.warnings, ())
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 2,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 1,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                },
            )
            self.assertEqual(
                [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT status, as_of_date, method "
                        "FROM lifecycle_observations ORDER BY as_of_date"
                    )
                ],
                [
                    (
                        "under_construction",
                        "2025-02-05",
                        "authoritative_physical_status_update",
                    ),
                    (
                        "commissioning",
                        "2026-01-13",
                        "authoritative_physical_status_update",
                    ),
                ],
            )
            self.assertEqual(
                [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT operating_model, as_of_date, method "
                        "FROM operating_model_observations"
                    )
                ],
                [("colocation", "2026-01-13", "company_disclosure")],
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            for row in snapshots:
                self.assertIsNone(row["latitude"])
                self.assertIsNone(row["longitude"])
                self.assertIsNone(row["geometry_json"])
                self.assertEqual(
                    json.loads(row["tags_json"])["role:operator"],
                    "Qareeb Data Centers",
                )

    def test_untyped_space_and_energy_language_create_no_capacity_or_workload(
        self,
    ) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            document["operating_models"],
            [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": LATEST_EVIDENCE_KEY,
                    "as_of_date": "2026-01-13",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
        )
        metadata = document["evidence"][1]["metadata"]
        self.assertEqual(metadata["reported_scalable_space_square_metres"], 6000)
        self.assertIn("metadata only", metadata["space_guardrail"])
        for guardrail in (metadata["capacity_guardrail"], metadata["energy_guardrail"]):
            self.assertIn("annual energy", guardrail)
            self.assertIn("PUE", guardrail)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {"operator": ["Qareeb Data Centers"]})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])

    def test_batelco_qareeb_identity_is_distinct_from_stc_bahrain(self) -> None:
        self.assertEqual(
            hashlib.sha256(STC_SOURCE.read_bytes()).hexdigest(), STC_SOURCE_SHA256
        )
        batelco = json.loads(SOURCE.read_text(encoding="utf-8"))
        stc = json.loads(STC_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(
            {batelco["campus"]["stable_key"], batelco["project"]["stable_key"]},
            {CAMPUS_KEY, PROJECT_KEY},
        )
        self.assertTrue(
            {
                batelco["campus"]["stable_key"],
                batelco["project"]["stable_key"],
            }.isdisjoint({stc["campus"]["stable_key"], stc["project"]["stable_key"]})
        )
        self.assertEqual(
            batelco["project"]["address"], "Beyon Data Oasis, Southern Bahrain, Bahrain"
        )
        self.assertEqual(stc["project"]["address"], "Bahrain")
        self.assertNotEqual(
            batelco["evidence"][0]["source_url"], stc["evidence"][0]["source_url"]
        )

    def test_per_evidence_time_gate_rejects_pre_capture_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:06:59Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
