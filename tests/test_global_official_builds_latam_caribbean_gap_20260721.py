from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
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
from datacenter_atlas import (
    global_official_builds_latam_caribbean_gap_20260721 as tranche,
)
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-latam-caribbean-gap-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-official-latam-caribbean-20260721.pPqxte")

RECORDED_AT = "2026-07-21T16:38:08Z"
ARTIFACT_TREE_SHA256 = (
    "fb61d1eff9adf63c03a10f3a19678b2b7561a20b695022c010d55b90368a59aa"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-hive-yguazu-100mw-expansion-current-build.json": (
        9_180,
        "9cf82a5b1b50cd9982773be5cfe9fccc5a957634a8d001c347011eb42ce2cf69",
    ),
    "curated-official-2026-07-21-puntonet-epicentro-quito-current-build.json": (
        6_134,
        "c34fc6490b7145e249b9b6cc90d8d05af9dd6dfc17c62fbab82d45c26f6f51c4",
    ),
    "curated-official-2026-07-21-telcosub-costa-del-este-review-only.json": (
        8_543,
        "156e9c31780b0ec03acce8b92db72a9074530fda136ceed36e63a2ca9e2fd3b8",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_462,
        "7c95ec0175ad20e0977ceec21df72e2b43f2b1d1e614724c24e1c17616e4dd60",
    ),
    "candidate-assessment.json": (
        5_800,
        "f4777320591cd9ed05b675ca1683b147e3f7cca7317619852ef9c2b8a8195fa7",
    ),
    "manifest.json": (
        1_706,
        "732590c83c47ce86b7eeed1c738ab2f9fc12b79b05c0043566d646a08c0ab3bb",
    ),
    "manifest.sha256": (
        80,
        "861d396e67e88361e9719ae6cc6fbc31a623c45d1f0bb124e3bce1c8d54a56f9",
    ),
    "retrieval-inventory.json": (
        17_147,
        "963467e62fb8cf43bd60d1ed0480b797c7c3d02ffac01c857e8f82f82299a0c0",
    ),
    "rights-and-disposition.json": (
        1_216,
        "12ac9a99f0140de94df898e9029a64354ab9fb2c2ae3d4a07a822440e36724e7",
    ),
    "source-snapshot.json": (
        4_577,
        "231a64aac87a0d52c0d676c9e6e75d32b818e64a0dac3ab3073515b4f497f7f6",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsLatamCaribbeanGapTests(unittest.TestCase):
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
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

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

    def test_sources_are_exact_schema_v11_and_import_twice_offline(self) -> None:
        expected_documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(path.read_bytes(), tranche._canonical(expected_documents[name]))

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
                "entities": 6,
                "entity_snapshots": 6,
                "evidence": 8,
                "lifecycle_observations": 2,
                "operating_model_observations": 0,
                "workload_observations": 1,
                "capacity_estimates": 1,
            }
            actual_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)

            capacity = tuple(
                connection.execute(
                    "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                    "FROM capacity_estimates AS c "
                    "JOIN entities AS e ON e.id=c.entity_id"
                ).fetchone()
            )
            self.assertEqual(
                capacity,
                (
                    "curated:hive-yguazu-paraguay-campus:2026-100mw-expansion",
                    "grid_connection_mw",
                    "contracted",
                    "MW",
                    100.0,
                ),
            )

    def test_semantic_boundaries_exclude_ambiguous_and_stale_claims(self) -> None:
        documents = tranche.expected_source_documents()
        hive, puntonet, telcosub = [documents[name] for name in tranche.SOURCE_FILENAMES]

        self.assertEqual(hive["workloads"][0]["value"], "crypto_mining")
        self.assertEqual(hive["capacities"][0]["metric"], "grid_connection_mw")
        self.assertEqual(hive["capacities"][0]["stage"], "contracted")
        notes = hive["capacities"][0]["notes"]
        self.assertIn("Existing 200 MW", notes)
        self.assertIn("193.4 MW", notes)
        self.assertIn("excluded", notes)

        self.assertEqual(len(puntonet["lifecycle"]), 1)
        self.assertEqual(puntonet["capacities"], [])
        self.assertEqual(puntonet["workloads"], [])
        self.assertIn("6MWATTS", json.dumps(puntonet, ensure_ascii=False))

        self.assertEqual(telcosub["lifecycle"], [])
        self.assertEqual(telcosub["capacities"], [])
        self.assertEqual(telcosub["workloads"], [])
        self.assertIn("1.5 megas", json.dumps(telcosub, ensure_ascii=False))
        self.assertNotIn("CSN-1", telcosub["campus"]["name"])
        for document in documents.values():
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])

        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 5)
        self.assertEqual(assessment["seed_eligible_count"], 2)
        self.assertEqual(assessment["review_only_count"], 3)
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertFalse(
            rows["telcosub-telconet-costa-del-este-edge-dc"]["seed_eligible"]
        )
        self.assertFalse(
            rows["gualeguaychu-municipal-cpd-finishing-stage"]["source_record_created"]
        )
        self.assertFalse(
            rows["gortt-tier-iv-rated-4-modular-data-center"]["source_record_created"]
        )

    def test_private_capture_disposition_v77_nonmutation_and_no_residue(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        self.assertTrue(capture.is_dir())
        self.assertEqual(len(list(capture.iterdir())), tranche.CAPTURE_FILE_COUNT)
        self.assertEqual(
            sum(path.stat().st_size for path in capture.iterdir()),
            tranche.CAPTURE_TOTAL_BYTES,
        )
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        tranche._validate_capture_directory(capture)

        tranche._validate_v77_nonmutation()
        definition = json.loads(tranche.V77_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list((ROOT / "sources").glob(".official-builds-latam-caribbean-gap.*")),
            [],
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-latam-caribbean-gap-*"
                )
            ),
            [],
        )

    def test_late_collision_rolls_back_owned_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            artifacts = root / "source_artifacts"
            sources.mkdir()
            artifacts.mkdir()
            artifact = artifacts / tranche.ARTIFACT_ID
            with (
                patch.object(tranche, "SOURCES_ROOT", sources),
                patch.object(tranche, "ARTIFACT_ROOT", artifacts),
                patch.object(tranche, "ARTIFACT", artifact),
            ):
                target = (datetime.now(UTC) + timedelta(seconds=30)).replace(
                    microsecond=0
                )
                prepared = tranche._prepare_publication(
                    target.isoformat().replace("+00:00", "Z")
                )
                collision = sources / tranche.SOURCE_FILENAMES[1]

                def inject_collision(_: float) -> None:
                    collision.write_bytes(b"late unrelated occupant\n")

                try:
                    with (
                        patch.object(tranche, "_wait_until", side_effect=inject_collision),
                        self.assertRaises(tranche.OfficialLatamCaribbeanGapError),
                    ):
                        tranche._publish(prepared)
                    self.assertEqual(collision.read_bytes(), b"late unrelated occupant\n")
                    self.assertFalse((sources / tranche.SOURCE_FILENAMES[0]).exists())
                    self.assertFalse((sources / tranche.SOURCE_FILENAMES[2]).exists())
                    self.assertFalse(artifact.exists())
                    self.assertEqual(
                        {path.name for path in prepared.source_stage.iterdir()},
                        set(tranche.SOURCE_FILENAMES),
                    )
                finally:
                    collision.unlink(missing_ok=True)
                    tranche._cleanup_prepared(prepared)

    def test_future_wall_clock_and_republication_fail_closed(self) -> None:
        with self.assertRaises(tranche.OfficialLatamCaribbeanGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialLatamCaribbeanGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )


if __name__ == "__main__":
    unittest.main()
