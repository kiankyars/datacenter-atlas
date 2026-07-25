from __future__ import annotations

import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import publication_pair_v32 as pair
except ModuleNotFoundError:
    from datacenter_atlas import publication_pair_v32 as pair


class BoundaryError(RuntimeError):
    pass


class PublicationPairV32Tests(unittest.TestCase):
    def _stages(self, parent: Path) -> tuple[Path, Path]:
        definition = parent / ".definition.stage"
        bundle = parent / ".bundle.stage"
        definition.write_bytes(b"definition\n")
        nested = bundle / "nested"
        nested.mkdir(parents=True)
        (nested / "payload.json").write_bytes(b'{"ok":true}\n')
        definition.chmod(0o444)
        (nested / "payload.json").chmod(0o444)
        nested.chmod(0o555)
        bundle.chmod(0o555)
        return definition, bundle

    def test_recursive_temporal_contract_refreshes_every_inode(self) -> None:
        with TemporaryDirectory(prefix="publication-pair-v32-time-") as temporary:
            parent = Path(temporary)
            definition, bundle = self._stages(parent)
            target = datetime.now(UTC) + timedelta(milliseconds=50)
            with pair.bound_parents([parent], error=BoundaryError) as bindings:
                definition_identity = pair.entry_identity(
                    definition,
                    bindings,
                    directory=False,
                    error=BoundaryError,
                )
                tree = pair.tree_inventory(
                    bundle,
                    bindings,
                    error=BoundaryError,
                )
                pair.validate_publication_times(
                    definition,
                    definition_identity,
                    bundle,
                    tree,
                    bindings,
                    target=target,
                    wall_clock=target,
                    require_live=False,
                    error=BoundaryError,
                )
                time.sleep(max(0.0, target.timestamp() - time.time()) + 0.01)
                pair.refresh_publication_ctimes(
                    definition,
                    definition_identity,
                    bundle,
                    tree,
                    bindings,
                    target=target,
                    error=BoundaryError,
                )
                pair.validate_publication_times(
                    definition,
                    definition_identity,
                    bundle,
                    tree,
                    bindings,
                    target=target,
                    wall_clock=datetime.now(UTC),
                    require_live=True,
                    error=BoundaryError,
                )

    def test_no_replace_promotion_and_owned_rollback_preserve_identities(
        self,
    ) -> None:
        with TemporaryDirectory(prefix="publication-pair-v32-rollback-") as temporary:
            parent = Path(temporary)
            definition_stage, bundle_stage = self._stages(parent)
            definition_final = parent / "definition.json"
            bundle_final = parent / "bundle"
            with pair.bound_parents([parent], error=BoundaryError) as bindings:
                definition_identity = pair.entry_identity(
                    definition_stage,
                    bindings,
                    directory=False,
                    error=BoundaryError,
                )
                tree = pair.tree_inventory(
                    bundle_stage,
                    bindings,
                    error=BoundaryError,
                )
                bundle_identity = tree["."][1], tree["."][2]
                pair.make_directory_renameable(
                    bundle_stage,
                    bundle_identity,
                    bindings,
                    error=BoundaryError,
                )
                self.assertEqual(
                    pair.promote_noreplace(
                        bundle_stage,
                        bundle_final,
                        bindings,
                        directory=True,
                        error=BoundaryError,
                    ),
                    bundle_identity,
                )
                pair.freeze_directory(
                    bundle_final,
                    bundle_identity,
                    bindings,
                    error=BoundaryError,
                )
                self.assertEqual(
                    pair.promote_noreplace(
                        definition_stage,
                        definition_final,
                        bindings,
                        directory=False,
                        error=BoundaryError,
                    ),
                    definition_identity,
                )
                operation_error = BoundaryError("late validation failed")
                self.assertFalse(
                    pair.rollback_owned_final(
                        operation_error,
                        destination=definition_final,
                        stage=definition_stage,
                        identity=definition_identity,
                        bindings=bindings,
                        directory=False,
                        error=BoundaryError,
                    )
                )
                self.assertFalse(
                    pair.rollback_owned_final(
                        operation_error,
                        destination=bundle_final,
                        stage=bundle_stage,
                        identity=bundle_identity,
                        bindings=bindings,
                        directory=True,
                        error=BoundaryError,
                    )
                )
                self.assertFalse(definition_final.exists())
                self.assertFalse(bundle_final.exists())
                self.assertTrue(definition_stage.is_file())
                self.assertTrue(bundle_stage.is_dir())

    def test_collision_and_post_rename_failure_keep_foreign_bytes(self) -> None:
        with TemporaryDirectory(prefix="publication-pair-v32-collision-") as temporary:
            parent = Path(temporary)
            stage = parent / ".definition.stage"
            destination = parent / "definition.json"
            stage.write_bytes(b"owned")
            destination.write_bytes(b"foreign")
            with pair.bound_parents([parent], error=BoundaryError) as bindings:
                with self.assertRaisesRegex(BoundaryError, "collision"):
                    pair.promote_noreplace(
                        stage,
                        destination,
                        bindings,
                        directory=False,
                        error=BoundaryError,
                    )
                self.assertEqual(stage.read_bytes(), b"owned")
                self.assertEqual(destination.read_bytes(), b"foreign")

                destination.unlink()
                identity = pair.entry_identity(
                    stage,
                    bindings,
                    directory=False,
                    error=BoundaryError,
                )
                original = pair._rename_noreplace_at

                def rename_then_raise(*args: object, **kwargs: object) -> None:
                    original(*args, **kwargs)
                    raise BoundaryError("post-rename failure")

                with (
                    patch.object(
                        pair,
                        "_rename_noreplace_at",
                        side_effect=rename_then_raise,
                    ),
                    self.assertRaisesRegex(BoundaryError, "post-rename"),
                ):
                    pair.promote_noreplace(
                        stage,
                        destination,
                        bindings,
                        directory=False,
                        error=BoundaryError,
                    )
                operation_error = BoundaryError("promotion helper failed")
                self.assertFalse(
                    pair.rollback_owned_final(
                        operation_error,
                        destination=destination,
                        stage=stage,
                        identity=identity,
                        bindings=bindings,
                        directory=False,
                        error=BoundaryError,
                    )
                )
                self.assertTrue(stage.is_file())
                self.assertFalse(destination.exists())

                pair.promote_noreplace(
                    stage,
                    destination,
                    bindings,
                    directory=False,
                    error=BoundaryError,
                )
                rollback_error = BoundaryError("rollback helper failed")
                with patch.object(
                    pair,
                    "_rename_noreplace_at",
                    side_effect=rename_then_raise,
                ):
                    self.assertFalse(
                        pair.rollback_owned_final(
                            rollback_error,
                            destination=destination,
                            stage=stage,
                            identity=identity,
                            bindings=bindings,
                            directory=False,
                            error=BoundaryError,
                        )
                    )
                self.assertTrue(stage.is_file())
                self.assertFalse(destination.exists())

    def test_parent_swap_and_lock_substitution_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="publication-pair-v32-parent-") as temporary:
            root = Path(temporary)
            parent = root / "output"
            parent.mkdir()
            with pair.bound_parents([parent], error=BoundaryError) as bindings:
                moved = root / "moved"
                parent.rename(moved)
                parent.mkdir()
                with self.assertRaisesRegex(BoundaryError, "swapped"):
                    pair.assert_parent_bindings(
                        bindings,
                        error=BoundaryError,
                        label="adversarial swap",
                    )

        with TemporaryDirectory(prefix="publication-pair-v32-lock-") as temporary:
            parent = Path(temporary)
            lock = parent / ".publish.lock"
            with pair.bound_parents([parent], error=BoundaryError) as bindings:
                lock.write_bytes(b"active")
                with (
                    self.assertRaisesRegex(
                        BoundaryError,
                        "active publication lock",
                    ),
                    pair.publication_lock(
                        lock,
                        bindings,
                        error=BoundaryError,
                    ),
                ):
                    self.fail("active lock must win before the body")
                lock.unlink()

                saved_lock = parent / ".publish.lock.owned"
                with (
                    self.assertRaisesRegex(BoundaryError, "substituted"),
                    pair.publication_lock(
                        lock,
                        bindings,
                        error=BoundaryError,
                    ),
                ):
                    lock.rename(saved_lock)
                    lock.write_bytes(b"foreign")
                self.assertEqual(lock.read_bytes(), b"foreign")
                self.assertTrue(saved_lock.is_file())

        with TemporaryDirectory(
            prefix="publication-pair-v32-lock-exit-"
        ) as temporary:
            root = Path(temporary)
            output = root / "output"
            output.mkdir()
            lock = root / ".publish.lock"
            moved = root / "output.moved"
            original_unlink = pair.os.unlink

            def unlink_then_swap(*args: object, **kwargs: object) -> None:
                original_unlink(*args, **kwargs)
                output.rename(moved)
                output.mkdir()

            with (
                pair.bound_parents(
                    [root, output],
                    error=BoundaryError,
                ) as bindings,
                patch.object(
                    pair.os,
                    "unlink",
                    side_effect=unlink_then_swap,
                ),
                self.assertRaisesRegex(BoundaryError, "swapped"),
                pair.publication_lock(
                    lock,
                    bindings,
                    error=BoundaryError,
                ),
            ):
                pass


if __name__ == "__main__":
    unittest.main()
