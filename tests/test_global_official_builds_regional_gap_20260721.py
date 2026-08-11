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
from datacenter_atlas import global_official_builds_regional_gap_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-regional-gap-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-regional-gap-20260721.pz8R6c")
BROWSER_PROFILE_TRASH = Path(
    "/Users/kian/.Trash/dc-regional-gap-chrome-20260721.pz8R6c"
)

RECORDED_AT = "2026-07-21T16:06:03Z"
ARTIFACT_TREE_SHA256 = (
    "94f96ea7bdc2a007916c8110ba8720f564aeaf794ed93773a97f150c51faf812"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-niger-national-dc-pk5-current-build.json": (
        6_627,
        "511353e1c2ee8492bf113c393c08f0ac94adb0509d8c92bf5a1f8fa439c3d076",
    ),
    "curated-official-2026-07-21-somalia-national-dc-site-unresolved-current-build.json": (
        6_391,
        "0c6a8d1ea211bb700ac2b1856946071fd42eb0270b758a8d42d5bafaf4820cf5",
    ),
    "curated-official-2026-07-21-congo-national-dc-bacongo-current-build.json": (
        8_751,
        "0adc47681f6950423a8908b654d5d30b2ebb73d070d18ff0e7be0c56e170baaa",
    ),
    "curated-official-2026-07-21-telia-vilnius-current-build.json": (
        3_811,
        "ddda25294036bb69357c0f087e46eef37a83103d366a504130f267dcd5016ec6",
    ),
    "curated-official-2026-07-21-atnorth-ice02-phase-2-current-build.json": (
        3_929,
        "8b180e3aacc62cb2317d2147c6795ba156154a655a558c2e1efb6f93b710c8c2",
    ),
    "curated-official-2026-07-21-borealis-blonduos-expansion-current-build.json": (
        6_224,
        "9f6a3292d2c3b7df30574bd27af1837f906a60bc2de30ca43b402619d2465680",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_557,
        "547e4b7baa89dd72f5e214d9453b43ce52b5c22e7d94be5bf8ebe241f7a59898",
    ),
    "candidate-assessment.json": (
        5_655,
        "e2fcfdf4edbf26005958a67da9cc56519a79fe31c70938c1b4a84bd8eaa8e140",
    ),
    "manifest.json": (
        1_795,
        "43d71b155b816b5b708cda78fff80b6646b83d4b5dc50b146a648400899b220f",
    ),
    "manifest.sha256": (
        80,
        "21920fdb4f4e3d766431dc5bdc49cde0367c3f7d1daac7c59d27e84952096431",
    ),
    "retrieval-inventory.json": (
        16_300,
        "2e314c3a6e7dfb0bcdc65f8e535b25ea3ec99b81e8f74c59e080bc62007308a9",
    ),
    "rights-and-disposition.json": (
        1_489,
        "de240332ed9d495d12a63e8b82d55ac61a03b445002fb568cf43896517b3861a",
    ),
    "source-snapshot.json": (
        7_044,
        "6089498df8181769db43408ae42a3bd9e685606b64863b863226eb5fa3cea60a",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsRegionalGapTests(unittest.TestCase):
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
                "entities": 12,
                "entity_snapshots": 12,
                "evidence": 11,
                "lifecycle_observations": 8,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
            }
            actual_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)
            lifecycle = [
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, l.status, l.as_of_date "
                    "FROM lifecycle_observations AS l "
                    "JOIN entities AS e ON e.id = l.entity_id "
                    "ORDER BY e.stable_key, l.as_of_date"
                )
            ]
            self.assertEqual(len(lifecycle), 8)
            self.assertEqual({row[1] for row in lifecycle}, {"under_construction"})
            self.assertIn(
                (
                    "curated:somalia-national-data-center-mogadishu-site-unresolved:"
                    "current-build-site-unresolved",
                    "under_construction",
                    "2025-05-06",
                ),
                lifecycle,
            )

    def test_candidate_boundaries_preserve_somalia_and_capacity_exclusions(self) -> None:
        documents = tranche.expected_source_documents()
        self.assertTrue(
            all(
                not document["capacities"]
                and not document["workloads"]
                and not document["operating_models"]
                for document in documents.values()
            )
        )
        somalia = documents[tranche.SOURCE_FILENAMES[1]]
        self.assertEqual(somalia["campus"]["address"], "Mogadishu, Somalia")
        self.assertEqual(len(somalia["lifecycle"]), 1)
        self.assertEqual(len(somalia["evidence"]), 2)
        self.assertNotIn("Airport", somalia["campus"]["address"])
        self.assertNotIn("Ministry", somalia["campus"]["address"])

        telia = documents[tranche.SOURCE_FILENAMES[3]]
        self.assertEqual(telia["project"]["address"], "Vilnius, Lithuania")
        self.assertNotIn("Raisteniškės", json.dumps(telia["project"], ensure_ascii=False))

        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 9)
        self.assertEqual(assessment["seed_eligible_count"], 6)
        self.assertEqual(assessment["review_only_count"], 3)
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        for candidate_id in (
            "somalia-national-dc-primary-mogadishu-airport",
            "somalia-national-dc-dr-moct",
            "orel-it-campus-data-center-nawinna",
        ):
            self.assertFalse(rows[candidate_id]["source_record_created"])
            self.assertFalse(rows[candidate_id]["seed_eligible"])
        for candidate_id in (
            "somalia-national-dc-primary-mogadishu-airport",
            "somalia-national-dc-dr-moct",
        ):
            self.assertFalse(rows[candidate_id]["lifecycle_observation_created"])
            self.assertFalse(rows[candidate_id]["site_allocation_inferred"])

        source_keys = {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
        self.assertFalse(any("airport" in key for key in source_keys))
        self.assertFalse(any("orel" in key for key in source_keys))

    def test_private_capture_disposition_v73_nonmutation_and_no_residue(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        self.assertTrue(capture.is_dir())
        self.assertEqual(len(list(capture.iterdir())), tranche.CAPTURE_FILE_COUNT)
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        tranche._validate_capture_directory(capture)
        self.assertFalse(tranche.BROWSER_PROFILE_ORIGIN.exists())
        browser_profile = tranche.resolve_external_capture(BROWSER_PROFILE_TRASH)
        self.assertTrue(browser_profile.is_dir())
        tranche._validate_browser_profile_disposition()

        tranche._validate_v73_nonmutation()
        definition = json.loads(tranche.V73_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list((ROOT / "sources").glob(".official-builds-regional-gap.*")),
            [],
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-regional-gap-*"
                )
            ),
            [],
        )

    def test_replay_fails_closed_before_staging(self) -> None:
        future = (datetime.now(UTC) + timedelta(seconds=60)).replace(microsecond=0)
        with self.assertRaises(tranche.OfficialTrancheError):
            tranche.build(recorded_at=future.isoformat().replace("+00:00", "Z"))


if __name__ == "__main__":
    unittest.main()
