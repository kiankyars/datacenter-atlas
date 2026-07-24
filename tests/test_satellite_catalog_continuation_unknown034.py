from __future__ import annotations

from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import stat
import unittest

import datacenter_atlas.satellite_batch as public_batch
import datacenter_atlas.satellite_batch_recovery as public_recovery


batch = importlib.import_module(public_batch.validate_satellite_batch.__module__)
recovery = importlib.import_module(
    public_recovery.validate_recovered_satellite_batch.__module__
)

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-18-global-open-v3"
SOURCE = (
    ROOT
    / "satellite_review_recoveries/"
    "2026-07-19-global-open-v3-unknown-033-recovered-25/batch"
)
OUTPUT = ROOT / "satellite_review_runs/2026-07-21-global-open-v3-unknown-034"
LOCK = ROOT / "satellite_review_runs/2026-07-21-global-open-v3-unknown-034.lock"
WRAPPER = (
    ROOT
    / "satellite_review_continuations/"
    "2026-07-21-global-open-v3-unknown-034-continued-25"
)
MANIFEST = WRAPPER / "continuation-manifest.json"
SIDECAR = WRAPPER / "manifest.sha256"
MANIFEST_SHA256 = (
    "7ec2eff11515b7ffe18ea581e6c73fdf3751902d8bcb7e4fb94ffd380707c74a"
)
NO_SCENE_QUEUE_IDS = {
    "satq-096a168063a356491b6b5136",
    "satq-abd001cb72ef68053ac0b683",
    "satq-d24e538796a2ddcd5947aaf4",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _pin(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(raw),
    }


def _terminal_bytes(tasks: list[dict[str, object]]) -> bytes:
    return b"".join(
        (
            json.dumps(
                task,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            + "\n"
        ).encode("utf-8")
        for task in tasks
    )


def _selected_tasks(
    document: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    return sorted(
        (
            (queue_id, task)
            for queue_id, task in document["jobs"].items()
            if 4770 <= task["queue_position"] <= 4794
        ),
        key=lambda item: item[1]["queue_position"],
    )


class Unknown034CatalogContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper_raw = MANIFEST.read_bytes()
        cls.wrapper = json.loads(cls.wrapper_raw)
        cls.source_raw = (SOURCE / batch.BATCH_MANIFEST_FILENAME).read_bytes()
        cls.output_raw = (OUTPUT / batch.BATCH_MANIFEST_FILENAME).read_bytes()
        cls.source_document = json.loads(cls.source_raw)
        cls.output_document = batch.validate_satellite_batch(QUEUE, OUTPUT)
        (
            cls.source_rows,
            cls.source_inventory_raw,
            cls.source_directories,
        ) = recovery._inventory(SOURCE, "accepted Unknown033 recovery batch")
        (
            cls.output_rows,
            cls.output_inventory_raw,
            cls.output_directories,
        ) = recovery._inventory(OUTPUT, "accepted Unknown034 continuation")

    def test_wrapper_is_canonical_hash_bound_and_pins_every_input(self) -> None:
        self.assertEqual(self.wrapper_raw, _canonical_json(self.wrapper))
        self.assertEqual(_sha256(self.wrapper_raw), MANIFEST_SHA256)
        self.assertEqual(
            SIDECAR.read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  continuation-manifest.json\n",
        )
        self.assertEqual(
            self.wrapper["format"],
            "datacenter-atlas-satellite-catalog-continuation-acceptance-v1",
        )
        self.assertEqual(self.wrapper["schema_version"], 1)
        self.assertEqual(
            self.wrapper["artifact_id"],
            "2026-07-21-global-open-v3-unknown-034-continued-25",
        )

        pin_groups = (
            self.wrapper["source_recovery"]["acceptance"],
            self.wrapper["source_recovery"]["definition"],
            self.wrapper["source_recovery"]["recovery_manifest"],
            self.wrapper["source_recovery"]["batch_manifest"],
            self.wrapper["queue_bundle"]["manifest"],
            self.wrapper["queue_bundle"]["queue"],
            *self.wrapper["execution"]["runner"].values(),
            self.wrapper["output"]["batch_manifest"],
        )
        for expected in pin_groups:
            path = ROOT / expected["path"]
            self.assertFalse(path.is_symlink())
            self.assertEqual(_pin(path), expected)

        acceptance = json.loads(
            (
                ROOT
                / self.wrapper["source_recovery"]["acceptance"]["path"]
            ).read_bytes()
        )
        self.assertEqual(
            acceptance["accepted"]["artifact_id"],
            self.wrapper["source_recovery"]["artifact_id"],
        )
        self.assertEqual(
            acceptance["accepted"]["batch_manifest"],
            self.wrapper["source_recovery"]["batch_manifest"],
        )

    def test_source_recovery_is_unchanged_and_output_is_frozen_valid(self) -> None:
        source_inventory = {
            **recovery._inventory_summary(
                self.source_rows, self.source_inventory_raw
            ),
            "directories": len(self.source_directories),
        }
        output_inventory = {
            **recovery._inventory_summary(
                self.output_rows, self.output_inventory_raw
            ),
            "directories": len(self.output_directories),
        }
        self.assertEqual(
            source_inventory, self.wrapper["source_recovery"]["batch_inventory"]
        )
        self.assertEqual(output_inventory, self.wrapper["output"]["inventory"])
        self.assertEqual(
            self.source_document["summary"],
            self.wrapper["clone"]["pre_execution_validation"]["summary"],
        )
        self.assertIsNone(self.source_document["last_run"])
        self.assertEqual(
            self.output_document["summary"], self.wrapper["output"]["summary"]
        )
        self.assertEqual(
            self.output_document["configuration"],
            self.wrapper["execution"]["configuration"],
        )
        self.assertEqual(
            self.output_document["last_run"], self.wrapper["execution"]["run"]
        )
        self.assertEqual(self.output_document["state"], "incomplete")
        self.assertEqual(
            self.output_document["scope"],
            {
                "atlas_mutation": False,
                "change_analysis_executed": False,
                "imagery_identity_inference": False,
                "imagery_lifecycle_inference": False,
                "imagery_operating_status_inference": False,
                "imagery_power_inference": False,
                "mode": "catalog_only",
                "review_required": True,
            },
        )

        for root in (SOURCE, OUTPUT, WRAPPER):
            files, directories = recovery._regular_tree(root, "sealed artifact")
            self.assertTrue(files)
            self.assertTrue(directories)
            self.assertTrue(
                all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in files)
            )
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o555
                    for path in directories
                )
            )

        self.assertFalse(LOCK.is_symlink())
        self.assertTrue(LOCK.is_file())
        self.assertEqual(LOCK.stat().st_size, 0)
        self.assertEqual(stat.S_IMODE(LOCK.stat().st_mode), 0o600)
        self.assertNotIn(OUTPUT, LOCK.parents)

    def test_clone_delta_is_exact_and_does_not_modify_historical_payload(self) -> None:
        source_files = {row["path"]: row for row in self.source_rows}
        output_files = {row["path"]: row for row in self.output_rows}
        self.assertTrue(set(source_files).issubset(output_files))
        for relative, source_record in source_files.items():
            if relative != batch.BATCH_MANIFEST_FILENAME:
                self.assertEqual(output_files[relative], source_record)

        tasks = _selected_tasks(self.output_document)
        completed = [
            item for item in tasks if item[1]["state"] == "completed"
        ]
        no_scene = [
            item
            for item in tasks
            if item[1]["state"] == batch.UNAVAILABLE_NO_SCENE
        ]
        expected_new_files = {
            f"jobs/{queue_id}/catalog/{name}"
            for queue_id, _task in completed
            for name in batch.CATALOG_FILES
        }
        self.assertEqual(set(output_files) - set(source_files), expected_new_files)
        self.assertEqual(len(expected_new_files), 66)

        expected_new_directories = {
            f"jobs/{queue_id}" for queue_id, _task in tasks
        } | {
            f"jobs/{queue_id}/catalog" for queue_id, _task in completed
        }
        self.assertEqual(
            self.output_directories - self.source_directories,
            expected_new_directories,
        )
        self.assertEqual(len(expected_new_directories), 47)
        for _queue_id, task in no_scene:
            self.assertFalse((OUTPUT / task["output_directory"]).exists())

        delta = self.wrapper["output"]["delta"]
        self.assertEqual(delta["files_added"], 66)
        self.assertEqual(delta["directories_added"], 47)
        self.assertEqual(
            delta["logical_bytes_added"],
            sum(row["bytes"] for row in self.output_rows)
            - sum(row["bytes"] for row in self.source_rows),
        )
        for queue_id, source_task in self.source_document["jobs"].items():
            position = source_task["queue_position"]
            if position < 4770 or position > 4794:
                self.assertEqual(self.output_document["jobs"][queue_id], source_task)

    def test_bounded_http_and_terminal_outcomes_are_exact(self) -> None:
        task_entries = _selected_tasks(self.output_document)
        tasks = [task for _queue_id, task in task_entries]
        self.assertEqual(
            [task["queue_position"] for task in tasks], list(range(4770, 4795))
        )
        self.assertEqual(
            Counter(task["state"] for task in tasks),
            Counter({"completed": 22, batch.UNAVAILABLE_NO_SCENE: 3}),
        )
        self.assertTrue(all(task["attempts"] == 1 for task in tasks))
        self.assertEqual(
            {
                queue_id
                for queue_id, task in task_entries
                if task["state"] == batch.UNAVAILABLE_NO_SCENE
            },
            NO_SCENE_QUEUE_IDS,
        )
        for task in tasks:
            if task["state"] == "completed":
                self.assertEqual(set(task["artifacts"]), set(batch.CATALOG_FILES))
                self.assertIsNotNone(task["selected_ids"])
            else:
                self.assertEqual(
                    task["unavailability"]["catalog_error_type"],
                    "datacenter_atlas.satellite_catalog.CatalogValidationError",
                )
                self.assertEqual(task["unavailability"]["window"], "baseline")
                self.assertEqual(
                    task["unavailability"]["raw_reason"],
                    "no scene falls within the baseline temporal window",
                )

        terminal_raw = _terminal_bytes(tasks)
        self.assertEqual(
            {
                "bytes": len(terminal_raw),
                "canonicalization": (
                    "queue-position order; compact sorted-key UTF-8 JSON plus "
                    "newline for each exact batch task object"
                ),
                "jobs": len(tasks),
                "sha256": _sha256(terminal_raw),
            },
            self.wrapper["execution"]["terminal_tasks"],
        )
        self.assertEqual(
            self.output_document["last_run"],
            {
                "budget_exhausted": True,
                "finished_at": "2026-07-21T07:43:24Z",
                "http_attempts_reserved": 50,
                "job_attempts": 25,
                "jobs_completed": 22,
                "jobs_failed": 0,
                "jobs_unavailable_no_scene": 3,
                "max_http_attempts": 50,
                "max_jobs": 25,
                "started_at": "2026-07-21T07:41:49Z",
            },
        )
        self.assertEqual(
            self.wrapper["execution"]["http_outcomes"],
            {
                "actual_status_codes_persisted": False,
                "http_attempts_reserved": 50,
                "provider_or_transport_failures_recorded": 0,
                "successful_provider_responses_inferred": 50,
                "successful_response_inference_basis": (
                    "The pinned catalog CLI performs one baseline and one current "
                    "request before semantic pair selection; all 25 first attempts "
                    "reached either completed selection or typed "
                    "CatalogValidationError no-scene selection with zero provider "
                    "or transport failures."
                ),
            },
        )

        catalog_source = (
            ROOT / self.wrapper["execution"]["runner"]["catalog_script"]["path"]
        ).read_text(encoding="utf-8")
        self.assertLess(
            catalog_source.index("baseline_raw = _post("),
            catalog_source.index("current_raw = _post("),
        )
        self.assertLess(
            catalog_source.index("current_raw = _post("),
            catalog_source.index("manifest = build_pair_manifest("),
        )

    def test_arithmetic_scope_and_next_position_remain_fail_closed(self) -> None:
        before = self.source_document["summary"]
        after = self.output_document["summary"]
        self.assertEqual(after["jobs_completed"] - before["jobs_completed"], 22)
        self.assertEqual(
            after["jobs_unavailable_no_scene"]
            - before["jobs_unavailable_no_scene"],
            3,
        )
        self.assertEqual(after["jobs_pending"] - before["jobs_pending"], -25)
        self.assertEqual(after["jobs_failed"] - before["jobs_failed"], 0)
        self.assertEqual(after["jobs_selected"] - before["jobs_selected"], 0)

        next_pending = self.wrapper["output"]["next_pending"]
        next_task = self.output_document["jobs"][next_pending["queue_id"]]
        self.assertEqual(next_task["queue_position"], 4795)
        self.assertEqual(next_task["state"], "pending")
        self.assertEqual(next_task["attempts"], 0)

        scope = self.wrapper["scope"]
        self.assertEqual(scope["mode"], "catalog_only")
        self.assertTrue(scope["review_required"])
        self.assertFalse(scope["automated_promotion_allowed"])
        self.assertFalse(scope["global_completeness_claimed"])
        self.assertFalse(scope["semianalysis_parity_claimed"])
        for name, value in scope.items():
            if name.startswith("imagery_") or name in {
                "atlas_mutation",
                "change_analysis_executed",
            }:
                self.assertFalse(value, name)
        self.assertFalse(
            any("/change/" in f"/{row['path']}" for row in self.output_rows)
            and not any("/change/" in f"/{row['path']}" for row in self.source_rows)
        )


if __name__ == "__main__":
    unittest.main()
