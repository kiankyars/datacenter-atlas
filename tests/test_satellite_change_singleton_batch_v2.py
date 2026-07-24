from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

import datacenter_atlas.satellite_change_singleton_batch_v2 as public_batch


batch = importlib.import_module(
    public_batch.validate_satellite_change_singleton_batch_v2.__module__
)


class SatelliteChangeSingletonBatchV2ContractTests(unittest.TestCase):
    def test_exact_preparation_and_unchanged_processor_validate(self) -> None:
        preparation, rows, lineage = batch._validate_preparation(
            batch.PACKAGE_ROOT / batch.PREPARATION_DIRECTORY_PATH,
            batch.PACKAGE_ROOT / batch.PREPARATION_DEFINITION_PATH,
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            tuple(row["queue_id"] for row in rows), batch.EXPECTED_QUEUE_IDS
        )
        self.assertEqual(
            lineage["closed_tree"]["inventory_sha256"],
            batch.PREPARATION_TREE_SHA256,
        )
        self.assertEqual(preparation["summary"]["catalog_rediscoveries"], 0)
        processor = batch._processor_lineage()
        self.assertEqual(processor["algorithm_version"], batch.ALGORITHM_VERSION)
        self.assertEqual(
            processor["files"]["datacenter_atlas/satellite_change_mosaic.py"][
                "sha256"
            ],
            "68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071",
        )
        self.assertEqual(
            processor["files"]["scripts/sentinel_change_mosaic.py"]["sha256"],
            "6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183",
        )

    def test_every_execution_has_one_primary_and_no_companion_flags(self) -> None:
        _preparation, rows, _lineage = batch._validate_preparation(
            batch.PACKAGE_ROOT / batch.PREPARATION_DIRECTORY_PATH,
            batch.PACKAGE_ROOT / batch.PREPARATION_DEFINITION_PATH,
        )
        for row in rows:
            values = batch._prepared_arguments(row)
            self.assertEqual(
                set(values),
                {
                    "--baseline-stac",
                    "--baseline-stac-sha256",
                    "--baseline-primary",
                    "--current-stac",
                    "--current-stac-sha256",
                    "--current-primary",
                    "--bbox",
                    "--entity-id",
                    "--entity-name",
                    "--output-dir",
                    "--minimum-component-area-m2",
                },
            )
            self.assertFalse(any("companion" in flag for flag in values))
            baseline, current = batch._load_bound_epochs(row)
            self.assertEqual(
                baseline["id"], row["epochs"]["baseline"]["selected_primary"]["id"]
            )
            self.assertEqual(
                current["id"], row["epochs"]["current"]["selected_primary"]["id"]
            )

    def test_new_manifest_retains_incident_as_successor_not_retry(self) -> None:
        preparation, rows, lineage = batch._validate_preparation(
            batch.PACKAGE_ROOT / batch.PREPARATION_DIRECTORY_PATH,
            batch.PACKAGE_ROOT / batch.PREPARATION_DEFINITION_PATH,
        )
        processor = batch._processor_lineage()
        document = batch._new_manifest(
            rows,
            preparation,
            lineage,
            processor,
            batch.SingletonBatchConfig(),
            "2026-07-21T04:00:00Z",
        )
        self.assertEqual(document["summary"]["jobs_selected"], 6)
        self.assertEqual(document["summary"]["jobs_pending"], 6)
        self.assertEqual(
            document["technical_incident"]["retry_semantics"],
            "successor_selection_not_retry",
        )
        self.assertEqual(document["technical_incident"]["jobs_failed"], 6)
        self.assertEqual(document["technical_incident"]["jobs_completed"], 0)
        self.assertEqual(document["scope"]["catalog_rediscovery"], False)
        self.assertEqual(document["scope"]["catalog_reranking"], False)

    def test_canonical_checkpoint_reload_preserves_explicit_selection(self) -> None:
        preparation, rows, lineage = batch._validate_preparation(
            batch.PACKAGE_ROOT / batch.PREPARATION_DIRECTORY_PATH,
            batch.PACKAGE_ROOT / batch.PREPARATION_DEFINITION_PATH,
        )
        processor = batch._processor_lineage()
        document = batch._new_manifest(
            rows,
            preparation,
            lineage,
            processor,
            batch.SingletonBatchConfig(),
            "2026-07-21T04:00:00Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "jobs").mkdir()
            batch._write_manifest(output, document, "2026-07-21T04:00:01Z")
            reloaded = batch._load_manifest(output)
            batch._validate_document(
                reloaded, rows, preparation, lineage, processor, output
            )
            self.assertEqual(
                reloaded["selection"]["queue_ids"], list(batch.EXPECTED_QUEUE_IDS)
            )

    def test_local_date_paths_never_use_future_july_21(self) -> None:
        values = (
            str(batch.DEFAULT_OUTPUT_PATH),
            str(batch.PREPARATION_DIRECTORY_PATH),
            str(batch.PREPARATION_DEFINITION_PATH),
        )
        self.assertTrue(all("2026-07-20" in value for value in values))
        self.assertTrue(all("2026-07-21" not in value for value in values))


class SatelliteChangeSingletonBatchV2FrozenReleaseTests(unittest.TestCase):
    OUTPUT = batch.PACKAGE_ROOT / batch.DEFAULT_OUTPUT_PATH
    REPORT_SHA256 = {
        "satq-54c6402eb93d14f1ea754e66": (
            "8fc5d5766b960db0ff7a97dc0ba63f0d9d3b6a7498bfd58808f257c2adb115cd"
        ),
        "satq-cef871428da247c3ecfadec6": (
            "d098c61040111f13bfa31f757fa63848263fb296a0205371d4dbbbb4769c3044"
        ),
        "satq-96fca962064e09f0dbafa93b": (
            "79ae36cf8a0e22759c503d2cfa8dc20a158013aeaa23fe2b551e0e2eda8ecd0e"
        ),
        "satq-78500568b1f6227789ae36f4": (
            "c9113332c7b47cc96c9c9ce92c53b4a7ed8c540410f73bc65e8e26a0e4e809cf"
        ),
        "satq-fb6b6f815dad079c059cf412": (
            "428e83ba89e982127896834dd1073ce136ec8bc81341d6f8a86a030b9b595e12"
        ),
        "satq-0ffe3647dc32ee25ef77eab7": (
            "7a87aed1e52edcb013fa81fa506822bd951f511354441cb714954c099e2e7819"
        ),
    }

    def test_frozen_release_validates_offline_with_exact_counts(self) -> None:
        document = batch.validate_satellite_change_singleton_batch_v2()
        self.assertEqual(document["state"], "completed")
        self.assertEqual(
            document["summary"],
            {
                "jobs_completed": 6,
                "jobs_failed": 0,
                "jobs_pending": 0,
                "jobs_running": 0,
                "jobs_selected": 6,
                "output_artifacts": 36,
            },
        )
        self.assertEqual(
            document["determinism"],
            {
                "artifact_inventory_sha256": (
                    "9e68a00c8863bbca07e3d3e8429f8a758a6b2e7b9e7b3682f4b0964eea00d351"
                ),
                "artifacts_compared": 36,
                "jobs_replayed": 6,
                "status": "verified_byte_identical",
                "verified_at": "2026-07-21T03:42:13Z",
            },
        )
        self.assertEqual(
            {
                queue_id: job["report"]["report_sha256"]
                for queue_id, job in document["jobs"].items()
            },
            self.REPORT_SHA256,
        )

    def test_freeze_manifest_binds_exact_closed_tree_and_modes(self) -> None:
        freeze_path = self.OUTPUT / batch.FREEZE_MANIFEST_FILENAME
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
            "f44677ffd37fbd753ccb7ea87dc2173d893444df350ab977c0a205e011898adc",
        )
        self.assertEqual(
            freeze["inventory"],
            batch._freeze_inventory(self.OUTPUT),
        )
        self.assertEqual(freeze["inventory"]["directories"], 13)
        self.assertEqual(freeze["inventory"]["files"], 37)
        self.assertEqual(freeze["inventory"]["file_bytes"], 10_730_021)
        self.assertEqual(
            freeze["inventory"]["inventory_sha256"],
            "8de0d2ebfd8d8afb40fbf0451e32e7f0b13a0cd181fedc1cdd47052225542259",
        )
        self.assertEqual(
            freeze["manifest"]["sha256"],
            "8099230c183bdf4fc39e32c132f7667d011aef728e2727f2e89368e0447d9cfd",
        )
        self.assertEqual(stat.S_IMODE(self.OUTPUT.stat().st_mode), 0o555)
        for path in self.OUTPUT.rglob("*"):
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode), 0o555 if path.is_dir() else 0o444
            )

    def test_frozen_manifest_retains_failed_v1_incident_and_processor_hashes(self) -> None:
        document = json.loads(
            (self.OUTPUT / batch.BATCH_MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(
            document["technical_incident"]["manifest"]["sha256"],
            "8c23b3f6d548e302e958ac214af077bf94fe65ee4dc9db95407dd581a440a984",
        )
        self.assertEqual(
            document["processor"]["files"][
                "datacenter_atlas/satellite_change_mosaic.py"
            ]["sha256"],
            "68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071",
        )
        self.assertEqual(
            document["processor"]["files"]["scripts/sentinel_change_mosaic.py"][
                "sha256"
            ],
            "6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183",
        )
        for job in document["jobs"].values():
            flags = job["execution"]["arguments"][::2]
            self.assertFalse(any("companion" in flag for flag in flags))


if __name__ == "__main__":
    unittest.main()
