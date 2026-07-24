from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.datacenter_atlas import current_coverage_v25 as core


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-21-v24.json"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-21-v24"
FINAL_DEFINITION = ROOT / core.V25_DEFINITION_PATH
FINAL_BUNDLE = ROOT / core.V25_BUNDLE_PATH
GENERATED_AT = "2026-07-22T01:48:00Z"
EXPECTED_DEFINITION_CHECKPOINT = (
    186_574,
    "40f85a544b3fd62e7fadbfd54dc52640ad04d91b04cbedcfeec09f82d5970e1c",
)
EXPECTED_BUNDLE_CHECKPOINTS = {
    core.LEDGER_FILENAME: (
        121_407,
        "e040f735826d2f91c65fab0ea699aa40db6dedccf882c9e664d8389bf5584ae8",
    ),
    core.MANIFEST_FILENAME: (
        42_392,
        "2c167b54669a7166ee8dd18c4d2b3ae21d88963ac35bd455fc17bb540c69a297",
    ),
    core.MANIFEST_HASH_FILENAME: (
        80,
        "e898d2558d78cef151e759aea3440e219077cecbe75ced09ff5b5aa0f08e84ef",
    ),
}
EXPECTED_BUNDLE_TREE_SHA256 = (
    "1de018b86667d144593baf1e52d1af207125aa0bc137395d20accbd8a5a928a7"
)


class StopBeforePublication(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def metrics(entry: dict) -> dict[str, object]:
    return {metric["label"]: metric["value"] for metric in entry["metrics"]}


class CurrentCoverageLedgerV25Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("ledger v25 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _layout(self, root: Path) -> tuple[Path, Path, Path]:
        sources = root / "sources"
        ledgers = root / "current_coverage_ledgers"
        sources.mkdir()
        ledgers.mkdir()
        return (
            sources / core.DEFINITION.name,
            ledgers / core.BUNDLE.name,
            root / ".current-coverage-v25.lock",
        )

    def _replay(self) -> tuple[core.CurrentCoverageV25Bundle, dict]:
        raw = core._canonical_json(core.definition_document(GENERATED_AT))
        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v25-replay-", dir="/private/tmp"
        ) as temporary:
            definition = Path(temporary) / core.DEFINITION.name
            definition.write_bytes(raw)
            definition.chmod(0o444)
            with ExitStack() as stack:
                self._offline(stack)
                first = core.build_current_coverage_ledger_v25(definition)
                second = core.build_current_coverage_ledger_v25(definition)
            self.assertEqual(first, second)
            bundle = Path(temporary) / "bundle"
            bundle.mkdir()
            core._write_bundle(bundle, first)
            for entry in bundle.iterdir():
                entry.chmod(0o444)
            bundle.chmod(0o555)
            manifest = core._validate_bundle(
                bundle,
                definition_path=definition,
                require_live=False,
                rebuild=True,
            )
        return first, manifest

    def test_exact_v24_successor_components_and_fuses(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            preview = core.preview_v25_delta()
        self.assertEqual(preview["base_entries"], 52)
        self.assertEqual(preview["final_entries"], 53)
        self.assertEqual(preview["added_ids"], sorted(core.ADDED_ARTIFACT_IDS))
        self.assertEqual(
            preview["replacement_ids"], sorted(core.REPLACEMENT_ARTIFACT_IDS)
        )
        self.assertEqual(
            preview["historicalized_ids"],
            sorted(core.HISTORICALIZED_ARTIFACT_IDS),
        )
        self.assertEqual(preview["unchanged_42_sha256"], core.UNCHANGED_42_SHA256)
        self.assertEqual(preview["removed_8_sha256"], core.REMOVED_8_SHA256)
        self.assertEqual(
            preview["historicalized_2_sha256"], core.HISTORICALIZED_2_SHA256
        )
        self.assertEqual(
            preview["replacement_8_sha256"], core.REPLACEMENT_8_SHA256
        )
        self.assertEqual(preview["added_1_sha256"], core.ADDED_1_SHA256)
        self.assertEqual(preview["all_53_sha256"], core.ALL_53_SHA256)
        self.assertEqual(preview["parity_gaps_sha256"], core.PARITY_GAPS_SHA256)

        base = json.loads(BASE_DEFINITION.read_bytes())
        document = core.definition_document(GENERATED_AT)
        self.assertEqual(document["base_ledger"], core.BASE_LINEAGE)
        self.assertEqual(document["ledger_id"], core.V25_LEDGER_ID)
        self.assertEqual(document["generated_at"], GENERATED_AT)
        base_entries = {entry["artifact_id"]: entry for entry in base["entries"]}
        current_entries = {
            entry["artifact_id"]: entry for entry in document["entries"]
        }
        unchanged_ids = (
            set(base_entries)
            - core.REMOVED_ARTIFACT_IDS
            - core.HISTORICALIZED_ARTIFACT_IDS
        )
        self.assertEqual(len(unchanged_ids), 42)
        self.assertEqual(
            [base_entries[artifact_id] for artifact_id in sorted(unchanged_ids)],
            [current_entries[artifact_id] for artifact_id in sorted(unchanged_ids)],
        )
        for artifact_id in core.HISTORICALIZED_ARTIFACT_IDS:
            expected = dict(base_entries[artifact_id])
            expected["limitations"] = sorted(
                [*expected["limitations"], core.HISTORICAL_LIMITATION]
            )
            self.assertEqual(current_entries[artifact_id], expected)
        self.assertTrue(core.REMOVED_ARTIFACT_IDS.isdisjoint(current_entries))
        self.assertTrue(core.NEW_ARTIFACT_IDS <= current_entries.keys())
        raw = core._canonical_json(document)
        self.assertEqual(len(raw), 186_574)
        self.assertEqual(core._sha256(raw), core.V25_DEFINITION_SHA256)
        self.assertTrue(
            all(token not in raw for token in core.FORBIDDEN_FUTURE_TOKENS)
        )

    def test_active_metrics_review_semantics_and_open_parity_gaps(self) -> None:
        document = core.definition_document(GENERATED_AT)
        entries = {entry["artifact_id"]: entry for entry in document["entries"]}
        seed = metrics(entries["seed-epoch-official-v86"])
        self.assertEqual(seed["source_scoped_entity_rows"], 927)
        self.assertEqual(seed["lifecycle_freshness_records"], 517)
        self.assertFalse(seed["current_status_inferred"])
        self.assertFalse(seed["geometry_only_representative_point_inferred"])
        queue = metrics(entries["satellite-queue-open-seed-v86"])
        self.assertEqual(queue["queue_jobs"], 215)
        self.assertEqual(queue["active_construction_priority_jobs"], 111)
        self.assertEqual(queue["skipped_missing_coordinates"], 712)
        self.assertFalse(queue["network_requests_performed"])
        federation = metrics(entries["federation-public-open-v35"])
        self.assertEqual(federation["source_scoped_rows"], 16_352)
        self.assertEqual(federation["construction_pipeline_records"], 6_719)
        self.assertEqual(
            federation["non_review_construction_pipeline_records"], 589
        )
        self.assertIsNone(federation["unique_physical_sites"])
        identity = metrics(entries["exact-identity-decisions-public-open-v11"])
        self.assertEqual(identity["exact_source_record_components"], 8_490)
        self.assertEqual(identity["unresolved_candidate_references"], 100_541)
        self.assertIsNone(identity["physical_site_lower_bound"])
        timeline = metrics(entries["construction-timeline-public-open-v8"])
        self.assertEqual(timeline["entities_with_lifecycle_observations"], 517)
        self.assertEqual(timeline["raw_lifecycle_observations"], 537)
        self.assertEqual(timeline["current_status_classification"], "unknown")
        self.assertFalse(timeline["current_construction_claimed"])
        master = metrics(entries["construction-master-public-open-v31"])
        self.assertEqual(master["total_master_rows"], 109_381)
        self.assertIsNone(master["unique_physical_sites"])
        construction_map = metrics(entries["construction-map-public-open-v31"])
        self.assertEqual(construction_map["mapped_total_rows"], 109_008)
        self.assertEqual(construction_map["unmapped_rows"], 373)
        self.assertIsNone(construction_map["unique_physical_sites"])
        coverage = metrics(entries["coverage-audit-public-open-v31"])
        self.assertEqual(coverage["coverage_groups"], 979)
        self.assertEqual(coverage["source_scoped_rows"], 16_352)
        self.assertEqual(coverage["open_gaps"], 4_582)
        self.assertEqual(coverage["v83_decision_rows"], 68)
        self.assertEqual(coverage["v83_promotions"], 0)
        self.assertIsNone(coverage["unique_physical_sites"])

        review = entries[core.V83_REVIEW_ARTIFACT_ID]
        review_metrics = metrics(review)
        self.assertEqual(review["artifact_kind"], "analyst_imagery_review")
        self.assertEqual(review["evidence_scope"], "review_only")
        self.assertEqual(review_metrics["analyst_decision_rows"], 68)
        self.assertEqual(review_metrics["unique_exact_visual_evidence_sets"], 65)
        self.assertEqual(
            review_metrics["decisions_retained_for_manual_followup"], 47
        )
        self.assertEqual(
            review_metrics["unique_retained_exact_visual_evidence_sets"], 44
        )
        self.assertEqual(review_metrics["decisions_rejected_for_site_promotion"], 21)
        self.assertEqual(review_metrics["exact_duplicate_groups"], 3)
        self.assertFalse(review_metrics["automated_promotion_allowed"])
        self.assertFalse(
            review_metrics["reviewer_similarity_used_for_exact_deduplication"]
        )
        self.assertFalse(review_metrics["x052_x041_exact_four_image_hash_match"])
        self.assertFalse(review_metrics["satellite_confirmation_claim_created"])
        self.assertFalse(review_metrics["lifecycle_status_claim_created"])
        rendered = json.dumps(review, sort_keys=True)
        self.assertIn("X052/X041", rendered)
        self.assertIn("zero decisions are promoted", rendered)

        gaps = {gap["gap_id"]: gap for gap in document["parity_gaps"]}
        self.assertEqual(gaps["benchmark-parity-not-computed"]["status"], "not_computed")
        self.assertIn("517 bounded", gaps["benchmark-parity-not-computed"]["summary"])
        self.assertIn("215 review jobs", gaps["satellite-review-backlog"]["summary"])
        self.assertFalse(document["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(document["scope"]["unique_physical_site_count"])

    def test_double_offline_replay_exact_pins_inventory_and_v24_regression(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            bundle, manifest = self._replay()
        self.assertEqual(manifest["ledger_id"], core.V25_LEDGER_ID)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(manifest["successor_delta"]["final_entries"], 53)
        self.assertEqual(manifest["input_trees"], dict(sorted(core.PINNED_TREES.items())))
        self.assertEqual(
            manifest["input_member_checkpoints"][core.V83_REVIEW_ARTIFACT_ID],
            {
                name: {"bytes": size, "sha256": digest}
                for name, (size, digest) in sorted(
                    core.V83_REVIEW_MEMBER_PINS.items()
                )
            },
        )
        self.assertEqual(
            manifest["input_modes"],
            {
                "bundle_directories": "0555",
                "bundle_files": "0444",
                "standalone_definitions": "0444",
            },
        )
        self.assertEqual(len(manifest["input_timestamps"]), 10)
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 53)
        self.assertEqual(inventory["public_open_review_only_artifacts"], 32)
        self.assertEqual(inventory["by_record_unit"]["review_record"], 19)
        self.assertEqual(inventory["by_record_unit"]["aggregate_report_metric"], 8)

        before = {
            path.name: checkpoint(path)
            for path in (BASE_DEFINITION, *BASE_BUNDLE.iterdir())
        }
        with ExitStack() as stack:
            self._offline(stack)
            predecessor = core._v24.validate_current_coverage_ledger_v24(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
        self.assertEqual(predecessor["ledger_id"], "current-coverage-2026-07-21-v24")
        self.assertEqual(
            before,
            {
                path.name: checkpoint(path)
                for path in (BASE_DEFINITION, *BASE_BUNDLE.iterdir())
            },
        )

    def test_collision_symlink_future_stage_and_rollback_fail_closed(self) -> None:
        target = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        fake_now = target - timedelta(seconds=90)
        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v25-collision-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, lock = self._layout(Path(temporary))
            definition.write_bytes(b"occupied")
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                with self.assertRaisesRegex(
                    core.CurrentCoverageV25Error, "refusing replacement"
                ):
                    core.publish_current_coverage_ledger_v25(GENERATED_AT)
            self.assertEqual(definition.read_bytes(), b"occupied")
            self.assertFalse(bundle.exists() or bundle.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v25-symlink-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)
            os.symlink(root / "absent", definition)
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                with self.assertRaisesRegex(
                    core.CurrentCoverageV25Error, "refusing replacement"
                ):
                    core.publish_current_coverage_ledger_v25(GENERATED_AT)
            self.assertTrue(definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v25-future-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)

            def stop_at_wait(actual: datetime) -> None:
                self.assertEqual(actual, target)
                self.assertFalse(definition.exists() or definition.is_symlink())
                self.assertFalse(bundle.exists() or bundle.is_symlink())
                raise StopBeforePublication("private stages remained hidden")

            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                stack.enter_context(
                    patch.object(
                        core,
                        "_stage_latest",
                        return_value=target.timestamp() - 1,
                    )
                )
                stack.enter_context(
                    patch.object(core, "_wait_until", side_effect=stop_at_wait)
                )
                with self.assertRaisesRegex(
                    StopBeforePublication, "private stages remained hidden"
                ):
                    core.publish_current_coverage_ledger_v25(GENERATED_AT)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="current-coverage-v25-rollback-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(core, "DEFINITION", definition))
                stack.enter_context(patch.object(core, "BUNDLE", bundle))
                stack.enter_context(patch.object(core, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(core, "_now", return_value=fake_now))
                stack.enter_context(
                    patch.object(
                        core,
                        "_stage_latest",
                        return_value=target.timestamp() - 1,
                    )
                )
                stack.enter_context(patch.object(core, "_wait_until", return_value=None))
                stack.enter_context(
                    patch.object(
                        core,
                        "validate_current_coverage_ledger_v25",
                        side_effect=RuntimeError("simulated final validation failure"),
                    )
                )
                with self.assertRaisesRegex(
                    RuntimeError, "simulated final validation failure"
                ):
                    core.publish_current_coverage_ledger_v25(GENERATED_AT)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.rollback-*")))
            self.assertFalse(
                list((root / "current_coverage_ledgers").glob(".*.rollback-*"))
            )

    def test_published_v25_is_rejected_for_member_chronology(self) -> None:
        if not FINAL_DEFINITION.exists() and not FINAL_BUNDLE.exists():
            return
        self.assertTrue(FINAL_DEFINITION.is_file())
        self.assertTrue(FINAL_BUNDLE.is_dir())
        with ExitStack() as stack:
            self._offline(stack)
            manifest = core._validate_bundle(
                FINAL_BUNDLE,
                definition_path=FINAL_DEFINITION,
                require_live=False,
                rebuild=True,
            )
            first = core.build_current_coverage_ledger_v25(FINAL_DEFINITION)
            second = core.build_current_coverage_ledger_v25(FINAL_DEFINITION)
        self.assertEqual(first, second)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(checkpoint(FINAL_DEFINITION), EXPECTED_DEFINITION_CHECKPOINT)
        self.assertEqual(
            {
                entry.name: checkpoint(entry)
                for entry in FINAL_BUNDLE.iterdir()
            },
            EXPECTED_BUNDLE_CHECKPOINTS,
        )
        self.assertEqual(
            core.tree_digest(FINAL_BUNDLE), EXPECTED_BUNDLE_TREE_SHA256
        )
        self.assertEqual(
            {
                core.LEDGER_FILENAME: first.ledger_bytes,
                core.MANIFEST_FILENAME: first.manifest_bytes,
                core.MANIFEST_HASH_FILENAME: first.manifest_hash_bytes,
            },
            {entry.name: entry.read_bytes() for entry in FINAL_BUNDLE.iterdir()},
        )
        self.assertEqual(stat.S_IMODE(FINAL_DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(FINAL_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in FINAL_BUNDLE.iterdir()
            )
        )
        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        for path in (FINAL_DEFINITION, FINAL_BUNDLE, *FINAL_BUNDLE.iterdir()):
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(metadata.st_birthtime, generated.timestamp())
            self.assertLessEqual(metadata.st_mtime, generated.timestamp())
        self.assertGreaterEqual(
            FINAL_DEFINITION.stat().st_ctime, generated.timestamp()
        )
        self.assertEqual(
            tuple(
                sorted(
                    path.name
                    for path in FINAL_BUNDLE.iterdir()
                    if path.stat().st_ctime < generated.timestamp()
                )
            ),
            tuple(sorted(core.BUNDLE_FILES)),
        )


if __name__ == "__main__":
    unittest.main()
