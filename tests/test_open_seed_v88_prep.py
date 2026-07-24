from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import open_seed_v88 as core
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import open_seed_v88 as core


class OpenSeedV88PrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = json.loads(core.BASE_DEFINITION.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access during offline build"),
            )
        )
        stack.enter_context(
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access during offline build"),
            )
        )
        return stack

    def test_accepted_v87_and_official_artifact_are_exact(self) -> None:
        guard = core._guard_state()
        core._validate_guard(guard)
        self.assertEqual(guard["base_definition"], core.BASE_DEFINITION_PIN)
        self.assertEqual(guard["base_manifest"], core.BASE_MANIFEST_PIN)
        self.assertEqual(guard["base_tree"], core.BASE_TREE_SHA256)
        self.assertEqual(guard["official_manifest"], core.OFFICIAL_MANIFEST_PIN)
        self.assertEqual(
            guard["official_tree"], core.OFFICIAL_PHYSICAL_TREE_SHA256
        )
        self.assertEqual(guard["additions"], core.ADDITION_PINS)

    def test_definition_selection_is_exact_five_input_append(self) -> None:
        wall = datetime(2026, 7, 22, 1, 30, tzinfo=UTC)
        selected, paths = core.selected_inputs(
            self.base,
            recorded_at="2026-07-22T01:30:00Z",
            validation_wall_clock=wall,
        )
        self.assertEqual(len(selected), 461)
        self.assertEqual(len(paths), 461)
        self.assertEqual(selected[:456], self.base["curated_inputs"])
        self.assertEqual(
            [row["path"] for row in selected[456:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(
            [row["sha256"] for row in selected[456:]],
            [core.ADDITION_PINS[path][1] for path in core.ADDITION_ORDER],
        )
        future = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)
        with self.assertRaisesRegex(core.OpenSeedV88Error, "publication time"):
            core.selected_inputs(
                self.base,
                recorded_at=future.isoformat().replace("+00:00", "Z"),
                validation_wall_clock=datetime.now(UTC),
            )

    def test_database_and_release_contract_recompute_exactly(self) -> None:
        recorded_at = "2026-07-22T01:30:00Z"
        selected, paths = core.selected_inputs(
            self.base,
            recorded_at=recorded_at,
            validation_wall_clock=datetime(2026, 7, 22, 1, 30, tzinfo=UTC),
        )
        self.assertEqual(len(selected), 461)
        with tempfile.TemporaryDirectory(
            prefix="open-seed-v88-prep-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = core._build_database(
                self.base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                release = root / "release"
                core._write_release(
                    connection, release, recorded_at=recorded_at
                )
            finally:
                connection.close()
            core._validate_release_facts(release, recorded_at=recorded_at)
            summary = json.loads((release / "summary.json").read_text())
            self.assertEqual(summary["entities_total"], 941)
            self.assertEqual(summary["campuses_total"], 490)
            self.assertEqual(summary["projects_total"], 451)
            self.assertEqual(summary["evidence_total"], 775)
            self.assertEqual(summary["capacity_estimates_current"], 557)
            self.assertEqual(summary["construction_pipeline_records"], 477)
            self.assertEqual(summary["entities_with_coordinates"], 213)

    def test_partial_collision_definition_collision_and_rollback_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="open-seed-v88-partial-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition = root / core.DEFINITION.name
            release = root / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            definition.write_text("collision\n", encoding="utf-8")
            with (
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                self.assertRaisesRegex(core.OpenSeedV88Error, "partial"),
            ):
                core.build_open_seed_v88()

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v88-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            releases = root / "releases"
            sources.mkdir()
            releases.mkdir()
            definition = sources / core.DEFINITION.name
            release = releases / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            original_promote = core.v69.promote_noreplace

            def collide_on_definition(source: Path, destination: Path) -> None:
                if Path(destination) == definition:
                    raise FileExistsError("injected v88 definition collision")
                original_promote(source, destination)

            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
            target_text = target.isoformat(timespec="seconds").replace("+00:00", "Z")
            with (
                self._offline(),
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                patch.object(core, "_wait_until", return_value=None),
                patch.object(
                    core.v69,
                    "promote_noreplace",
                    side_effect=collide_on_definition,
                ),
            ):
                with self.assertRaisesRegex(FileExistsError, "injected"):
                    core.build_open_seed_v88(recorded_at=target_text)
            self.assertFalse(definition.exists())
            self.assertFalse(release.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(sources.iterdir()), [])
            self.assertEqual(list(releases.iterdir()), [])

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v88-post-validation-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            releases = root / "releases"
            sources.mkdir()
            releases.mkdir()
            definition = sources / core.DEFINITION.name
            release = releases / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
            target_text = target.isoformat(timespec="seconds").replace("+00:00", "Z")
            injected = core.OpenSeedV88Error(
                "injected post-promotion validation failure"
            )
            with (
                self._offline(),
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                patch.object(core, "_wait_until", return_value=None),
                patch.object(core, "validate_open_seed_v88", side_effect=injected),
            ):
                with self.assertRaisesRegex(core.OpenSeedV88Error, "post-promotion"):
                    core.build_open_seed_v88(recorded_at=target_text)
            self.assertFalse(definition.exists())
            self.assertFalse(release.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(sources.iterdir()), [])
            self.assertEqual(list(releases.iterdir()), [])

    def test_publication_state_is_clean_or_complete(self) -> None:
        present = (core.DEFINITION.exists(), core.RELEASE.exists())
        self.assertNotIn(present, {(True, False), (False, True)})


if __name__ == "__main__":
    unittest.main()
