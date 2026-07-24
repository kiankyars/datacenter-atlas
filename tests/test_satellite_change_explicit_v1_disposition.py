from __future__ import annotations

import stat
import tempfile
from pathlib import Path
import unittest

import datacenter_atlas.datacenter_atlas.satellite_change_explicit_v1_disposition as implementation
from datacenter_atlas.satellite_batch_explicit_v1 import (
    ExplicitBatchConfig,
    validate_explicit_satellite_batch_v1,
)
from datacenter_atlas.satellite_change_explicit_v1_disposition import (
    CHANGE_MANIFEST_SHA256,
    CHANGE_TREE_SHA256,
    tree_sha256,
)


QUEUE_PATH = implementation.QUEUE_PATH
SOURCE_CATALOG_PATH = implementation.SOURCE_CATALOG_PATH


class ExplicitV1DispositionTests(unittest.TestCase):
    def test_source_checkpoint_exact_bytes_validate_before_finalization(self) -> None:
        document = implementation._validate_source_catalog(SOURCE_CATALOG_PATH)
        self.assertEqual(document["state"], "selection_complete")
        self.assertEqual(document["summary"]["selected_jobs_completed"], 11)
        self.assertEqual(document["summary"]["jobs_not_selected"], 87)

    def test_frozen_copy_is_byte_identical_and_offline_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / "frozen-copy"
            published = Path(temporary) / "published-copy"
            implementation._copy_frozen_tree(SOURCE_CATALOG_PATH, stage)
            self.assertEqual(tree_sha256(stage), tree_sha256(SOURCE_CATALOG_PATH))
            self.assertEqual(stat.S_IMODE(stage.stat().st_mode), 0o755)
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode)
                    == (0o555 if path.is_dir() else 0o444)
                    for path in stage.rglob("*")
                )
            )
            document = validate_explicit_satellite_batch_v1(
                QUEUE_PATH, stage, config=ExplicitBatchConfig()
            )
            self.assertEqual(document["summary"]["selected_jobs_completed"], 11)
            implementation._promote_noreplace(stage, published)
            self.assertFalse(stage.exists())
            self.assertEqual(stat.S_IMODE(published.stat().st_mode), 0o555)
            implementation._validate_frozen_modes(published)
            self.assertEqual(tree_sha256(published), tree_sha256(SOURCE_CATALOG_PATH))

    def test_existing_frozen_change_bytes_and_selection_are_exact(self) -> None:
        raw = implementation._exact_file(
            implementation.CHANGE_RUN_PATH / "batch-manifest.json",
            CHANGE_MANIFEST_SHA256,
            "change manifest",
        )
        document = implementation._strict_json(raw, "change manifest")
        self.assertEqual(
            tuple(document["selection"]["selected_queue_ids"]),
            implementation.SELECTED_QUEUE_IDS,
        )
        self.assertEqual(
            set(document["jobs"]), set(implementation.SELECTED_QUEUE_IDS)
        )
        self.assertNotEqual(
            tuple(document["jobs"]), implementation.SELECTED_QUEUE_IDS
        )
        self.assertEqual(
            tree_sha256(implementation.CHANGE_RUN_PATH)[0], CHANGE_TREE_SHA256
        )
        implementation._validate_frozen_modes(implementation.CHANGE_RUN_PATH)

    def test_execution_sources_remain_at_recorded_hashes(self) -> None:
        implementation._exact_file(
            implementation.GENERIC_CARRIER_PATH,
            implementation.GENERIC_CARRIER_SHA256,
            "generic carrier",
        )
        implementation._exact_file(
            implementation.EXECUTION_ADAPTER_PATH,
            implementation.EXECUTION_ADAPTER_SHA256,
            "execution adapter",
        )
        implementation._exact_file(
            implementation.ROOT_SHIM_PATH,
            implementation.EXECUTION_ROOT_SHIM_SHA256,
            "execution root shim",
        )
        implementation._exact_file(
            implementation.EXECUTION_CLI_PATH,
            implementation.EXECUTION_CLI_SHA256,
            "execution CLI",
        )

    def test_published_finalization_and_disposition_are_frozen(self) -> None:
        catalog = implementation.validate_finalized_catalog(
            implementation.FINALIZED_CATALOG_PATH,
            finalized_at="2026-07-21T14:05:15Z",
        )
        change = implementation.validate_frozen_change_run()
        disposition = implementation.validate_disposition(
            implementation.DISPOSITION_PATH,
            expected_generated_at="2026-07-21T14:06:45Z",
            expected_catalog_finalized_at="2026-07-21T14:05:15Z",
        )
        self.assertEqual(catalog["summary"]["selected_jobs_completed"], 11)
        self.assertEqual(change["summary"]["jobs_completed"], 11)
        self.assertEqual(
            disposition["status"],
            "accepted_review_only_machine_change_batch",
        )
        self.assertEqual(
            implementation._sha256(
                (implementation.DISPOSITION_PATH / "manifest.json").read_bytes()
            ),
            "81117523744d802d50ad08d65d4192c1673b0508b421a44b3e969b6e268a00cc",
        )
        self.assertEqual(
            tree_sha256(implementation.DISPOSITION_PATH)[0],
            "96d24ac0a97f6165f2def1271efb94d00095349c44bbe07d2b31ceab767d495c",
        )


if __name__ == "__main__":
    unittest.main()
