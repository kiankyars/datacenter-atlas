from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch


try:
    satellite_batch = importlib.import_module(
        "datacenter_atlas.datacenter_atlas.satellite_batch"
    )
except ModuleNotFoundError:
    satellite_batch = importlib.import_module("datacenter_atlas.satellite_batch")

BatchConfig = satellite_batch.BatchConfig
SatelliteBatchError = satellite_batch.SatelliteBatchError
validate_satellite_batch = satellite_batch.validate_satellite_batch

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
RUN = ROOT / "satellite_review_runs/2026-07-21-open-seed-v83-active-002"
LOCK = RUN.with_name(f"{RUN.name}.lock")
MANIFEST = RUN / "batch-manifest.json"

CONFIG = BatchConfig(
    priority_tiers=["active_construction"],
    user_agent=(
        "DataCenterAtlas/0.1 (open research satellite review queue; "
        "+https://github.com/kiankyars/semiconductors)"
    ),
    minimum_interval_seconds=1.1,
    timeout_seconds=60,
    catalog_retries=0,
    max_job_attempts=3,
    max_response_bytes=16_777_216,
)

MANIFEST_PIN = (
    120_448,
    "ec43aacf55bab8d8169e5cad4855b5e33614c2e65de0a5b82bf70c2c585adae8",
)
QUEUE_MANIFEST_SHA256 = (
    "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd"
)
QUEUE_SHA256 = "8792ee2d80ed9b44d3ef67d3511b29ca0f9160b8ebd641e7f54cf4f5db4e4251"
SELECTION_INVENTORY_SHA256 = (
    "43cc5bac37ba4675ccb09a3261d014947d8f36b2e27889913389867c8a368bfc"
)
ARTIFACT_INVENTORY_SHA256 = (
    "6d2204c5cb75f7e30f841dd67288bdfe605fd3bd08dc23a8289cba8c9be33211"
)
TREE_PIN = "7a26caebb28656c551837c1431bfd2a5a228889572d5df006a149badc8c91152"
SUMMARY = {
    "jobs_completed": 101,
    "jobs_failed": 0,
    "jobs_pending": 0,
    "jobs_selected": 104,
    "jobs_unavailable_no_scene": 3,
}
SCOPE = {
    "atlas_mutation": False,
    "change_analysis_executed": False,
    "imagery_identity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_power_inference": False,
    "mode": "catalog_only",
    "review_required": True,
}
UNAVAILABLE = {
    "satq-3149584b9d40a3049b84371e": (
        14,
        "5c6e55e6-1029-5edf-9975-8695c3009b9d",
        "baseline",
        "no scene falls within the baseline temporal window",
    ),
    "satq-3c6f789981688519124eeb22": (
        19,
        "d8264840-e897-5554-87fb-b575a0fa7bf7",
        "current",
        "no scene falls within the current temporal window",
    ),
    "satq-ed5c45c9ee1bfba25a2f10c3": (
        12,
        "95b33a98-a85e-57af-b18d-6811a7fd3b20",
        "baseline",
        "no scene falls within the baseline temporal window",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: object) -> str:
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def tree_inventory(root: Path) -> tuple[int, int, int, str]:
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"catalog run contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            directories += 1
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            files += 1
            raw = path.read_bytes()
            file_bytes += len(raw)
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported catalog-run entry: {relative}")
    return directories, files, file_bytes, digest.hexdigest()


def recursive_keys(value: object) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        result.update(value)
        for child in value.values():
            result.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            result.update(recursive_keys(child))
    return result


class OpenSeedV83Active002SatelliteCatalogTests(unittest.TestCase):
    def test_frozen_run_validates_offline_with_exact_lineage(self) -> None:
        failure = AssertionError("catalog validation attempted network access")
        with (
            patch.object(socket, "socket", side_effect=failure),
            patch.object(socket, "create_connection", side_effect=failure),
            patch.object(socket, "getaddrinfo", side_effect=failure),
        ):
            manifest = validate_satellite_batch(QUEUE, RUN, config=CONFIG)

        self.assertEqual((MANIFEST.stat().st_size, sha256(MANIFEST)), MANIFEST_PIN)
        self.assertEqual(manifest["state"], "completed")
        self.assertEqual(manifest["summary"], SUMMARY)
        self.assertEqual(manifest["scope"], SCOPE)
        self.assertEqual(
            manifest["queue_bundle"]["manifest_sha256"], QUEUE_MANIFEST_SHA256
        )
        self.assertEqual(manifest["queue_bundle"]["queue_sha256"], QUEUE_SHA256)

    def test_terminal_selection_artifacts_and_unavailable_rows_are_exact(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        selected = sorted(
            (
                job["queue_position"],
                queue_id,
                job["state"],
                (job.get("selected_ids") or {}).get("baseline"),
                (job.get("selected_ids") or {}).get("current"),
                job["attempts"],
            )
            for queue_id, job in manifest["jobs"].items()
        )
        self.assertEqual(
            canonical_digest([list(row) for row in selected]),
            SELECTION_INVENTORY_SHA256,
        )
        self.assertEqual({row[-1] for row in selected}, {1})

        unavailable = {
            queue_id: job
            for queue_id, job in manifest["jobs"].items()
            if job["state"] == "unavailable_no_scene"
        }
        self.assertEqual(set(unavailable), set(UNAVAILABLE))
        for queue_id, expected in UNAVAILABLE.items():
            position, entity_id, window, reason = expected
            job = unavailable[queue_id]
            self.assertEqual(job["queue_position"], position)
            self.assertEqual(job["entity_id"], entity_id)
            self.assertEqual(job["unavailability"]["window"], window)
            self.assertEqual(job["unavailability"]["raw_reason"], reason)
            self.assertIsNone(job["artifacts"])
            self.assertIsNone(job["selected_ids"])

        inventory: list[list[object]] = []
        response_files = 0
        response_bytes = 0
        job_manifest_bytes = 0
        for queue_id, job in manifest["jobs"].items():
            artifacts = job["artifacts"]
            if artifacts is None:
                continue
            catalog = RUN / job["output_directory"]
            for filename, checkpoint in artifacts.items():
                artifact = catalog / filename
                raw = artifact.read_bytes()
                self.assertEqual(
                    (len(raw), hashlib.sha256(raw).hexdigest()),
                    (checkpoint["bytes"], checkpoint["sha256"]),
                )
                inventory.append(
                    [queue_id, filename, checkpoint["bytes"], checkpoint["sha256"]]
                )
                if filename.endswith("-response.json"):
                    response_files += 1
                    response_bytes += len(raw)
                elif filename == "manifest.json":
                    job_manifest_bytes += len(raw)

        inventory.sort()
        self.assertEqual(
            (len(inventory), canonical_digest(inventory)),
            (303, ARTIFACT_INVENTORY_SHA256),
        )
        self.assertEqual((response_files, response_bytes), (202, 60_567_481))
        self.assertEqual(job_manifest_bytes, 3_672_420)
        self.assertEqual(sum(row[2] for row in inventory), 64_239_901)

    def test_scope_tree_modes_lock_and_tamper_validation_are_fail_closed(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest["scope"], SCOPE)
        self.assertTrue(
            {
                "capacity_estimates",
                "capacity_claim",
                "data_centre_type",
                "energy",
                "operator",
                "pue",
                "site_claim",
                "unique_site",
                "workload",
            }.isdisjoint(recursive_keys(manifest))
        )
        self.assertEqual(tree_inventory(RUN), (207, 304, 64_360_349, TREE_PIN))
        for path in [RUN, *RUN.rglob("*")]:
            expected = 0o555 if path.is_dir() else 0o444
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected, path)

        self.assertTrue(LOCK.is_file())
        self.assertFalse(LOCK.is_symlink())
        self.assertEqual(
            (LOCK.stat().st_size, sha256(LOCK)), (0, hashlib.sha256(b"").hexdigest())
        )
        self.assertEqual(stat.S_IMODE(LOCK.stat().st_mode), 0o600)

        target = (
            RUN / "jobs/satq-1f72804d5d56bb342d5e2e2c/catalog/baseline-response.json"
        )
        original_read_bytes = Path.read_bytes

        def tampered_read_bytes(path: Path) -> bytes:
            raw = original_read_bytes(path)
            return raw + b"tampered" if path.resolve() == target.resolve() else raw

        with (
            patch.object(Path, "read_bytes", tampered_read_bytes),
            self.assertRaises(SatelliteBatchError),
        ):
            validate_satellite_batch(QUEUE, RUN, config=CONFIG)


if __name__ == "__main__":
    unittest.main()
