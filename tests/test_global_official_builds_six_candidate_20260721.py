from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas import global_official_builds_six_candidate_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT / "source_artifacts/global-official-builds-six-candidate-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-official-builds-20260721.t7lZRV")
RECORDED_AT = "2026-07-21T13:06:52Z"

SOURCE_PINS = {
    "curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json": (
        8_203,
        "8653286bdfc853918125e1294483e9175a339cc44705422d68a9bd4709d27d9b",
    ),
    "curated-official-2026-07-21-akashi-astana-phase-1-current-build.json": (
        8_057,
        "7f93487075c06e359c8f41c264633393b64b731c4f5d89b4a804dc5476db2543",
    ),
    "curated-official-2026-07-21-bichuten-chovar-current-build.json": (
        5_339,
        "6c7b84b59da58cd5bcce44bff041578b22a243279db9e836bb6ce54c610ce1eb",
    ),
    "curated-official-2026-07-21-icatec-ica-current-build.json": (
        7_745,
        "8a87e5271914fc351ff01576661e9e5f315ab783489c44cf75144c03451fa4e6",
    ),
    "curated-official-2026-07-21-cmc-creative-space-hanoi-phase-2-historical.json": (
        4_908,
        "5bdf8e19ca3528b8533449f38eacb56e8778adf3fd2e5c3ff57f88e89a68985b",
    ),
}

ARTIFACT_PINS = {
    "README.md": (
        1_991,
        "13bc04d2e70cb5b86beba0194ceb3a734f991d362dcc8fba1d021126036ed1f5",
    ),
    "candidate-assessment.json": (
        2_756,
        "1d578e8e54087c378c6239f2491661583a6aaaa108226e8e983b3e63cc5e7e13",
    ),
    "manifest.json": (
        1_727,
        "20b0788dba18402cf1b6bb8874ec6cd66f86000ff85f620c7e0167bf7e1894cd",
    ),
    "manifest.sha256": (
        80,
        "4cda83dd7fa2f386609f6fea6328f71c4eccde757dc0cc96582529f3ed99ec01",
    ),
    "retrieval-inventory.json": (
        17_231,
        "19b65a0777aa00145e844ef0a66c50d2bc316bd22e841e6b13f160c1f7f0daf8",
    ),
    "rights-and-disposition.json": (
        1_343,
        "72f73a89d19aceaae15048494efadc3664b4aca6d46d6c9b860db13954259a23",
    ),
    "source-snapshot.json": (
        6_274,
        "1a6020ca7d8a07918af5397907abd90c14154f9e154427809177fa2f63a10ee4",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsSixCandidateTests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        stack.enter_context(
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        return stack

    def test_frozen_artifact_exact_closure_hashes_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(set(ARTIFACT_PINS), {path.name for path in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            path = ARTIFACT / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(
            tree_digest(ARTIFACT),
            "1562710dfd1ea030e39a83636acc322ba1ec37fd67a3e857ecce54944b67e0a0",
        )

        target = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime), target
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target)
        for path in ARTIFACT.iterdir():
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
        for name in SOURCE_PINS:
            metadata = (ROOT / "sources" / name).stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
            self.assertGreaterEqual(metadata.st_ctime, target)

    def test_sources_are_exact_canonical_schema_v11_and_import_offline(self) -> None:
        expected_documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            raw = path.read_bytes()
            self.assertEqual(raw, tranche._canonical(expected_documents[name]))

        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for _ in range(2):
                for name in SOURCE_PINS:
                    adapter.import_file(
                        connection,
                        ROOT / "sources" / name,
                        recorded_at=RECORDED_AT,
                    )
            validate_database(connection)
            expected_counts = {
                "entities": 10,
                "entity_snapshots": 10,
                "evidence": 8,
                "lifecycle_observations": 6,
                "operating_model_observations": 3,
                "workload_observations": 0,
                "capacity_estimates": 2,
            }
            actual_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)
            capacities = [
                tuple(row)
                for row in connection.execute(
                    "SELECT metric, stage, unit, base FROM capacity_estimates "
                    "ORDER BY metric, stage"
                )
            ]
            self.assertEqual(
                capacities,
                [
                    ("critical_it_mw", "planned", "MW", 5.28),
                    ("pue", "design", "ratio", 1.4),
                ],
            )

    def test_claim_boundaries_and_six_candidate_dispositions(self) -> None:
        documents = tranche.expected_source_documents()
        by_country = {
            document["project"]["country"]: document
            for document in documents.values()
        }
        self.assertEqual(
            [
                (row["value"], row["as_of_date"], row["method"])
                for row in by_country["Latvia"]["lifecycle"]
            ],
            [
                (
                    "under_construction",
                    "2026-06-30",
                    "authoritative_physical_status_update",
                )
            ],
        )
        self.assertEqual(
            [
                (row["value"], row["as_of_date"])
                for row in by_country["Peru"]["lifecycle"]
            ],
            [("foundations", "2026-02-12"), ("under_construction", "2026-04-07")],
        )
        self.assertEqual(
            [row["value"] for row in by_country["Kazakhstan"]["operating_models"]],
            ["colocation"],
        )
        self.assertEqual(
            [row["value"] for row in by_country["Nepal"]["operating_models"]],
            ["colocation"],
        )
        self.assertEqual(by_country["Nepal"]["capacities"], [])
        self.assertNotIn("48.34", json.dumps(by_country["Kazakhstan"]))
        self.assertNotIn(
            100,
            [row["base"] for row in by_country["Kazakhstan"]["capacities"]],
        )
        for document in documents.values():
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])
            self.assertEqual(document["workloads"], [])

        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["seed_eligible_count"],
                assessment["historical_only_count"],
                assessment["review_only_count"],
            ),
            (6, 4, 1, 1),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertEqual(
            rows["cmc-creative-space-hanoi-phase-2"]["decision"],
            "historical_only_current_status_unknown",
        )
        bolivia = rows["bolivia-fiscalia-sucre-data-center"]
        self.assertEqual(bolivia["decision"], "review_only_no_direct_capture")
        self.assertFalse(bolivia["source_record_created"])
        self.assertFalse(bolivia["seed_eligible"])
        self.assertFalse(
            bolivia["browser_context_not_evidence"]["used_for_normalized_claims"]
        )

    def test_capture_disposition_v71_nonmutation_and_no_staging_residue(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertFalse(tranche.CAPTURE_ORIGIN.is_symlink())
        tranche._validate_capture_directory(TRASH)
        self.assertEqual(len(list(TRASH.iterdir())), 28)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list(ROOT.glob("sources/.official-builds-six.*")),
            [],
        )
        self.assertEqual(
            list(
                ROOT.glob(
                    "source_artifacts/.global-official-builds-six-candidate-2026-07-21-v1.*"
                )
            ),
            [],
        )
        tranche._validate_v71_nonmutation()
        definition = json.loads(tranche.V71_DEFINITION.read_text())
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        snapshot = json.loads((ARTIFACT / "source-snapshot.json").read_text())
        self.assertFalse(snapshot["integration"]["open_seed_successor_created"])
        self.assertEqual(
            snapshot["integration"]["reason"],
            "coordinate_v72_lane_has_priority",
        )

    def test_no_replace_collision_and_identity_safe_multi_output_rollback(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.write_bytes(b"owned")
            final.write_bytes(b"late")
            with self.assertRaisesRegex(tranche.OfficialBuildsError, "collision"):
                tranche._promote_noreplace(stage, final)
            self.assertEqual(stage.read_bytes(), b"owned")
            self.assertEqual(final.read_bytes(), b"late")

            stage_directory = root / "private"
            final_directory = root / "public"
            stage_directory.mkdir()
            final_directory.mkdir()
            promoted = []
            for name in ("one", "two"):
                source = stage_directory / name
                destination = final_directory / name
                source.write_text(name, encoding="utf-8")
                identity = tranche._identity(source, directory=False)
                tranche._promote_noreplace(source, destination)
                promoted.append((source, destination, identity, False))
            tranche._rollback_promotions(promoted)
            for name in ("one", "two"):
                self.assertTrue((stage_directory / name).is_file())
                self.assertFalse((final_directory / name).exists())


if __name__ == "__main__":
    unittest.main()
