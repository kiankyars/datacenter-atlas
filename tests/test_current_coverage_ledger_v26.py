from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.datacenter_atlas import current_coverage_v26 as core


ROOT = Path(__file__).resolve().parents[1]
FINAL_DEFINITION = ROOT / core.V26_DEFINITION_PATH
FINAL_BUNDLE = ROOT / core.V26_BUNDLE_PATH
GENERATED_AT = "2026-07-22T02:10:00Z"
EXPECTED_DEFINITION_CHECKPOINT = (
    188_008,
    "04ff833055238a20172a4fb340116198321c0b18df7ba8c8250b68f03f62780c",
)
EXPECTED_BUNDLE_CHECKPOINTS = {
    core.LEDGER_FILENAME: (
        122_841,
        "0dbc06f8793ceb9232082dc99ce52383ae67b3c3e0a9db897396b3885fa62d2a",
    ),
    core.MANIFEST_FILENAME: (
        44_624,
        "8e691bf09491fed757a3d78fb72f6f27edebfa812c99dca5f528d094bbdcaf53",
    ),
    core.MANIFEST_HASH_FILENAME: (
        80,
        "f158a0d98a3d36f57c2270d3671b5c4aabce1d132e0e71b32de2470c418fd5a8",
    ),
}
EXPECTED_BUNDLE_TREE_SHA256 = (
    "0843207d5ce6a8f3e1676937b5e5b2af77d92b7d39cafeab39d1e7c426b68065"
)


class StopBeforePublication(RuntimeError):
    pass


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class CurrentCoverageLedgerV26Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("ledger v26 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _replay(self) -> tuple[core.CurrentCoverageV26Bundle, dict]:
        raw = core._canonical_json(core.definition_document(GENERATED_AT))
        with tempfile.TemporaryDirectory(prefix="v26-replay-", dir="/private/tmp") as tmp:
            root = Path(tmp)
            definition = root / "definition.json"
            definition.write_bytes(raw)
            definition.chmod(0o444)
            with ExitStack() as stack:
                self._offline(stack)
                first = core.build_current_coverage_ledger_v26(definition)
                second = core.build_current_coverage_ledger_v26(definition)
            self.assertEqual(first, second)
            bundle = root / "bundle"
            bundle.mkdir()
            core._write_bundle(bundle, first)
            for member in bundle.iterdir():
                member.chmod(0o444)
            bundle.chmod(0o555)
            manifest = core._validate_bundle(
                bundle,
                definition_path=definition,
                require_live=False,
                rebuild=True,
            )
        return first, manifest

    def _layout(self, root: Path) -> tuple[Path, Path, Path]:
        sources = root / "sources"
        ledgers = root / "current_coverage_ledgers"
        sources.mkdir()
        ledgers.mkdir()
        return (
            sources / core.DEFINITION.name,
            ledgers / core.BUNDLE.name,
            root / ".current-coverage-v26.lock",
        )

    def test_rejected_v25_incident_witness_is_exact_portable_and_immutable(self) -> None:
        v25_definition = ROOT / core.REJECTED_V25_DEFINITION["path"]
        v25_bundle = ROOT / core.REJECTED_V25_BUNDLE_PATH
        paths = (v25_definition, *v25_bundle.iterdir())
        before = {
            path.relative_to(ROOT).as_posix(): checkpoint(path)
            for path in paths
        }
        with ExitStack() as stack:
            self._offline(stack)
            core._require_inputs()
            witness = core._require_v25_incident_witness_v2()
        self.assertEqual(core.INCIDENT_LINEAGE["accepted_as_base"], False)
        self.assertEqual(
            core.INCIDENT_LINEAGE["status"], "rejected_publication_incident"
        )
        self.assertEqual(
            core.INCIDENT_LINEAGE["incident_kind"],
            "final_bundle_member_ctime_predates_generated_at",
        )
        self.assertEqual(witness["schema_version"], "2.0")
        self.assertEqual(witness["witness_id"], core.REJECTED_V25_WITNESS_ID)
        self.assertEqual(
            witness["incident"]["failed_bundle_members_at_original_observation"],
            list(core.REJECTED_V25_FAILED_MEMBERS),
        )
        self.assertEqual(
            witness["integrity_contract"]["observational_not_identity_signals"],
            ["ctime_ns", "nlink"],
        )
        original_observations = {
            path: core._incident_metadata(path)
            for path in (v25_definition, v25_bundle, *v25_bundle.iterdir())
        }

        def changed_inode_observation(path: Path) -> dict[str, int | float | None]:
            observation = dict(original_observations[path])
            observation["ctime_ns"] = int(observation["ctime_ns"]) + 1
            observation["nlink"] = int(observation["nlink"]) + 1
            return observation

        with patch.object(
            core, "_incident_metadata", side_effect=changed_inode_observation
        ):
            changed_witness = core._require_v25_incident_witness_v2()
        self.assertEqual(
            changed_witness["portable_identity"], witness["portable_identity"]
        )
        self.assertNotEqual(
            changed_witness["current_inode_observation"],
            witness["current_inode_observation"],
        )
        self.assertEqual(
            before,
            {
                path.relative_to(ROOT).as_posix(): checkpoint(path)
                for path in paths
            },
        )

    def test_definition_reconstructs_intended_v24_successor(self) -> None:
        document = core.definition_document(GENERATED_AT)
        intended = core._v25.definition_document(core._v25.V25_GENERATED_AT)
        self.assertEqual(document["base_ledger"], core._v25.BASE_LINEAGE)
        self.assertEqual(document["ledger_id"], core.V26_LEDGER_ID)
        self.assertEqual(document["generated_at"], GENERATED_AT)
        self.assertEqual(document["incident_lineage"], core.INCIDENT_LINEAGE)
        self.assertEqual(document["entries"], intended["entries"])
        self.assertEqual(document["parity_gaps"], intended["parity_gaps"])
        self.assertEqual(len(document["entries"]), 53)
        self.assertNotEqual(document["base_ledger"]["ledger_id"], core.REJECTED_V25_LEDGER_ID)
        raw = core._canonical_json(document)
        self.assertEqual(len(raw), 188_008)
        self.assertEqual(core._sha256(raw), core.V26_DEFINITION_SHA256)
        self.assertTrue(
            all(token not in raw for token in core._v25.FORBIDDEN_FUTURE_TOKENS)
        )

    def test_double_replay_inventory_semantics_and_incident_lineage(self) -> None:
        bundle, manifest = self._replay()
        self.assertEqual(manifest["ledger_id"], core.V26_LEDGER_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["incident_lineage"], core.INCIDENT_LINEAGE)
        self.assertEqual(
            manifest["input_trees"][core.REJECTED_V25_BUNDLE_PATH],
            core.REJECTED_V25_TREE_SHA256,
        )
        self.assertTrue(
            manifest["publication_chronology"][
                "all_final_ctime_gte_generated_at"
            ]
        )
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 53)
        self.assertEqual(inventory["public_open_review_only_artifacts"], 32)
        entries = {
            artifact["artifact_id"]: artifact for artifact in bundle.ledger["artifacts"]
        }
        self.assertTrue(core._v25.REMOVED_ARTIFACT_IDS.isdisjoint(entries))
        self.assertTrue(core._v25.NEW_ARTIFACT_IDS <= entries.keys())
        review = entries[core._v25.V83_REVIEW_ARTIFACT_ID]["reported_metrics"]
        self.assertEqual(review["analyst_decision_rows"], 68)
        self.assertEqual(review["unique_exact_visual_evidence_sets"], 65)
        self.assertFalse(review["automated_promotion_allowed"])
        self.assertIsNone(bundle.ledger["scope"]["unique_physical_site_count"])

    def test_chronology_refresh_covers_definition_root_and_every_member(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v26-chronology-", dir="/private/tmp") as tmp:
            root = Path(tmp)
            definition = root / "definition.json"
            definition.write_bytes(b"{}\n")
            bundle = root / "bundle"
            bundle.mkdir()
            for name in core.BUNDLE_FILES:
                bundle.joinpath(name).write_bytes(name.encode("ascii"))
            definition.chmod(0o444)
            for member in bundle.iterdir():
                member.chmod(0o444)
            bundle.chmod(0o555)
            target = datetime.now(UTC)
            core._refresh_stage_ctimes(definition, bundle, target)
            paths = core._publication_paths(definition, bundle)
            core._assert_chronology(paths, target, require_final_ctime=True)
            for path in paths:
                metadata = path.stat(follow_symlinks=False)
                self.assertLessEqual(metadata.st_birthtime, target.timestamp())
                self.assertLessEqual(metadata.st_mtime, target.timestamp())
                self.assertGreaterEqual(metadata.st_ctime, target.timestamp())
            self.assertEqual(stat.S_IMODE(definition.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)
            self.assertTrue(
                all(
                    stat.S_IMODE(member.stat().st_mode) == 0o444
                    for member in bundle.iterdir()
                )
            )

    def test_collision_hidden_staging_and_final_failure_rollback(self) -> None:
        target = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        fake_now = target - timedelta(seconds=90)
        with tempfile.TemporaryDirectory(prefix="v26-collision-", dir="/private/tmp") as tmp:
            definition, bundle, lock = self._layout(Path(tmp))
            definition.write_bytes(b"occupied")
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                with self.assertRaisesRegex(
                    core.CurrentCoverageV26Error, "refusing replacement"
                ):
                    core.publish_current_coverage_ledger_v26(GENERATED_AT)
            self.assertEqual(definition.read_bytes(), b"occupied")
            self.assertFalse(bundle.exists() or bundle.is_symlink())

        with tempfile.TemporaryDirectory(prefix="v26-hidden-", dir="/private/tmp") as tmp:
            definition, bundle, lock = self._layout(Path(tmp))

            def stop_at_barrier(actual: datetime) -> None:
                self.assertEqual(actual, target)
                self.assertFalse(definition.exists() or definition.is_symlink())
                self.assertFalse(bundle.exists() or bundle.is_symlink())
                raise StopBeforePublication("v26 finals remained hidden")

            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                stack.enter_context(
                    patch.object(core, "_assert_chronology", return_value=None)
                )
                stack.enter_context(
                    patch.object(core, "_wait_until", side_effect=stop_at_barrier)
                )
                with self.assertRaisesRegex(
                    StopBeforePublication, "v26 finals remained hidden"
                ):
                    core.publish_current_coverage_ledger_v26(GENERATED_AT)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())

        with tempfile.TemporaryDirectory(prefix="v26-rollback-", dir="/private/tmp") as tmp:
            definition, bundle, lock = self._layout(Path(tmp))
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                stack.enter_context(
                    patch.object(core, "_assert_chronology", return_value=None)
                )
                stack.enter_context(patch.object(core, "_wait_until", return_value=None))
                stack.enter_context(
                    patch.object(core, "_refresh_stage_ctimes", return_value=None)
                )
                stack.enter_context(
                    patch.object(
                        core,
                        "validate_current_coverage_ledger_v26",
                        side_effect=RuntimeError("simulated final validation failure"),
                    )
                )
                with self.assertRaisesRegex(
                    RuntimeError, "simulated final validation failure"
                ):
                    core.publish_current_coverage_ledger_v26(GENERATED_AT)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())

    def test_published_v26_when_present(self) -> None:
        if not FINAL_DEFINITION.exists() and not FINAL_BUNDLE.exists():
            return
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertTrue(FINAL_BUNDLE.is_dir())
        with ExitStack() as stack:
            self._offline(stack)
            manifest = core.validate_current_coverage_ledger_v26()
            first = core.build_current_coverage_ledger_v26(FINAL_DEFINITION)
            second = core.build_current_coverage_ledger_v26(FINAL_DEFINITION)
        self.assertEqual(first, second)
        self.assertEqual(manifest["incident_lineage"], core.INCIDENT_LINEAGE)
        self.assertEqual(checkpoint(FINAL_DEFINITION), EXPECTED_DEFINITION_CHECKPOINT)
        self.assertEqual(
            {
                member.name: checkpoint(member)
                for member in FINAL_BUNDLE.iterdir()
            },
            EXPECTED_BUNDLE_CHECKPOINTS,
        )
        self.assertEqual(
            core._v25.tree_digest(FINAL_BUNDLE), EXPECTED_BUNDLE_TREE_SHA256
        )
        self.assertEqual(
            {
                core.LEDGER_FILENAME: first.ledger_bytes,
                core.MANIFEST_FILENAME: first.manifest_bytes,
                core.MANIFEST_HASH_FILENAME: first.manifest_hash_bytes,
            },
            {member.name: member.read_bytes() for member in FINAL_BUNDLE.iterdir()},
        )
        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        paths = core._publication_paths(FINAL_DEFINITION, FINAL_BUNDLE)
        core._assert_chronology(paths, generated, require_final_ctime=True)
        for path in paths:
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(metadata.st_birthtime, generated.timestamp())
            self.assertLessEqual(metadata.st_mtime, generated.timestamp())
            self.assertGreaterEqual(metadata.st_ctime, generated.timestamp())
            self.assertEqual(
                stat.S_IMODE(metadata.st_mode), 0o555 if path == FINAL_BUNDLE else 0o444
            )


if __name__ == "__main__":
    unittest.main()
