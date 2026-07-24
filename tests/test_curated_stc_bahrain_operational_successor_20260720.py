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
SOURCE = ROOT / "sources/curated-official-2026-07-20-stc-bahrain-dc-v2.json"
PREDECESSOR = ROOT / "sources/curated-official-2026-07-20-stc-bahrain-dc.json"
SOURCE_SHA256 = "4d8976e26d77a9b5aa9b4a247456af3b9274991e9f0751a73b64f862fc2af02e"
PREDECESSOR_SHA256 = (
    "f67bc593369e9fbdcf994f8238ab1c6291ba64408563590c10064437c6784273"
)
RECORDED_AT = "2026-07-21T03:34:00Z"
OLD_EVIDENCE_KEY = (
    "stc-sustainability-report-2024-data-centers-page-11-captured-2026-07-20"
)
NEW_EVIDENCE_KEY = (
    "stc-annual-report-2025-center3-bahrain-launch-captured-2026-07-20"
)


class StcBahrainOperationalSuccessorTests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError("network used while importing frozen successor")
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

    def test_source_and_predecessor_are_canonical_and_byte_pinned(self) -> None:
        self.assertEqual(
            hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256
        )
        self.assertEqual(
            hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest(),
            PREDECESSOR_SHA256,
        )
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(
            SOURCE.read_text(encoding="utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [OLD_EVIDENCE_KEY, NEW_EVIDENCE_KEY],
        )

    def test_new_capture_is_exact_and_raw_rights_are_not_overstated(self) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        evidence = {row["key"]: row for row in document["evidence"]}
        new = evidence[NEW_EVIDENCE_KEY]
        metadata = new["metadata"]
        self.assertEqual(
            new["content_hash"],
            "7dccc9e19eb2627fd7e455fab047b79044ad893071a327f6c23eb92663c7ad21",
        )
        self.assertEqual(new["retrieved_at"], "2026-07-21T03:33:38Z")
        self.assertIsNone(new["published_at"])
        self.assertEqual(new["license"], "all-rights-reserved")
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 11_940_283)
        self.assertEqual(metadata["target_pdf_file_page"], 65)
        self.assertEqual(metadata["target_printed_pages"], "128-129")
        self.assertEqual(metadata["reported_capacity_mw_untyped"], 9.6)
        self.assertEqual(metadata["reported_scalable_capacity_mw_untyped"], 60)
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No normalized capacity row", metadata["capacity_guardrail"])

    def test_offline_import_preserves_history_and_removes_active_build_status(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, result = self._import()
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            self.assertEqual(result.entities_created, 2)
            self.assertEqual(result.evidence_created, 2)
            self.assertEqual(result.warnings, ())
            self.assertEqual(validate_database(connection), [])
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
                        "2024-12-31",
                        "authoritative_physical_status_update",
                    ),
                    (
                        "operational",
                        "2025-12-31",
                        "authoritative_status_update",
                    ),
                ],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM capacity_estimates"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE kind = 'satellite_imagery'"
                ).fetchone()[0],
                0,
            )
            frozen = list(
                connection.execute(
                    "SELECT id, status, as_of_date FROM lifecycle_observations "
                    "ORDER BY id"
                )
            )
            repeated = CuratedOfficialSourceAdapterV11().import_file(
                connection, SOURCE, recorded_at=RECORDED_AT
            )
            self.assertEqual(repeated.entities_created, 0)
            self.assertEqual(repeated.evidence_created, 0)
            self.assertEqual(
                list(
                    connection.execute(
                        "SELECT id, status, as_of_date FROM lifecycle_observations "
                        "ORDER BY id"
                    )
                ),
                frozen,
            )

    def test_successor_reuses_exact_stable_identity(self) -> None:
        old = json.loads(PREDECESSOR.read_text(encoding="utf-8"))
        new = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(new["campus"]["stable_key"], old["campus"]["stable_key"])
        self.assertEqual(new["project"]["stable_key"], old["project"]["stable_key"])
        self.assertEqual(new["campus"]["coordinates"], None)
        self.assertEqual(new["project"]["coordinates"], None)
        self.assertEqual(new["capacities"], [])
        self.assertEqual(new["operating_models"], [])
        self.assertEqual(new["workloads"], [])

    def test_per_evidence_time_gate_rejects_a_pre_capture_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T03:33:37Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    0,
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
