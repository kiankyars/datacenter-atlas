from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_batch import BatchConfig, validate_satellite_batch


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v56"
RUN = ROOT / "satellite_review_runs/2026-07-20-open-seed-v56-active-001"
MANIFEST = RUN / "batch-manifest.json"

MANIFEST_BYTES = 46_497
MANIFEST_SHA256 = "ab5cbf2f747b97f603def872d03a7dc4f8786108b28f78e98cc192bd3911b1d3"
TREE_SHA256 = "edd17eec057cf6f7d1da02bb4f28c2de44f31297ed6d3d20c5601f958dd8b93e"
QUEUE_MANIFEST_SHA256 = (
    "d02dca01f2f86915d01355ac54fd10c43796576bd2a484d58e3f69f4046834e2"
)
QUEUE_SHA256 = "e065c7024a4ba88fa74f87d846b2272a0a0ef006c64eca69acfb7f6e156101b7"
PENTAPOINT_QUEUE_ID = "satq-b6f121dc644b91ad78eb479a"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_inventory(root: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    directories = 0
    files = 0
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
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported catalog-run entry: {relative}")
    return directories, files, digest.hexdigest()


class OpenSeedV56SatelliteCatalogRunTests(unittest.TestCase):
    def test_frozen_run_validates_offline_with_exact_queue_lineage(self) -> None:
        config = BatchConfig(
            priority_tiers=["active_construction"],
            minimum_interval_seconds=1,
            timeout_seconds=60,
            catalog_retries=0,
            max_job_attempts=1,
        )
        failure = AssertionError("catalog-run validation attempted network access")
        with patch.object(socket, "socket", side_effect=failure), patch.object(
            socket, "create_connection", side_effect=failure
        ), patch.object(socket, "getaddrinfo", side_effect=failure):
            manifest = validate_satellite_batch(QUEUE, RUN, config=config)

        self.assertEqual(MANIFEST.stat().st_size, MANIFEST_BYTES)
        self.assertEqual(sha256(MANIFEST), MANIFEST_SHA256)
        self.assertEqual(manifest["state"], "incomplete")
        self.assertEqual(
            manifest["summary"],
            {
                "jobs_completed": 7,
                "jobs_failed": 0,
                "jobs_pending": 75,
                "jobs_selected": 82,
                "jobs_unavailable_no_scene": 0,
            },
        )
        self.assertEqual(
            manifest["queue_bundle"]["manifest_sha256"], QUEUE_MANIFEST_SHA256
        )
        self.assertEqual(manifest["queue_bundle"]["queue_sha256"], QUEUE_SHA256)

    def test_exact_seven_jobs_complete_and_pentapoint_is_catalogued(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        completed = {
            queue_id: job
            for queue_id, job in manifest["jobs"].items()
            if job["state"] == "completed"
        }
        self.assertEqual(
            sorted(job["queue_position"] for job in completed.values()),
            list(range(1, 8)),
        )
        self.assertEqual(len(completed), 7)
        pentapoint = completed[PENTAPOINT_QUEUE_ID]
        self.assertEqual(pentapoint["queue_position"], 4)
        self.assertEqual(
            pentapoint["entity_id"], "a75eaf2b-790f-5266-be60-3f2bafee2eeb"
        )
        self.assertEqual(
            pentapoint["selected_ids"],
            {
                "baseline": "S2A_47PPR_20240619_0_L2A",
                "current": "S2B_47PPR_20260624_0_L2A",
            },
        )
        self.assertEqual(
            pentapoint["artifacts"],
            {
                "baseline-response.json": {
                    "bytes": 22_201,
                    "sha256": "26aa1b9de1856c698f264c8e2f25ddc3e2468b7db917b0e8ec0e7c90e784910a",
                },
                "current-response.json": {
                    "bytes": 63_435,
                    "sha256": "182e154c47a59ff6d44fcfd22a77ee6c1178b9a6bc140e59e21d398787418a92",
                },
                "manifest.json": {
                    "bytes": 6_734,
                    "sha256": "bccac2c216c2cb5c391f64d18e56cb7d8e1417eda1b884bc7e437520db9e7ae7",
                },
            },
        )

    def test_catalog_only_scope_cannot_mutate_atlas_or_assert_semantics(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(
            manifest["scope"],
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
        self.assertTrue(manifest["last_run"]["budget_exhausted"])
        self.assertEqual(manifest["last_run"]["jobs_failed"], 0)
        self.assertEqual(manifest["last_run"]["jobs_unavailable_no_scene"], 0)

    def test_tree_is_hash_bound_and_uniformly_frozen(self) -> None:
        self.assertEqual(tree_inventory(RUN), (16, 22, TREE_SHA256))
        for path in [RUN, *RUN.rglob("*")]:
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555, path)
            else:
                self.assertTrue(path.is_file(), path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)


if __name__ == "__main__":
    unittest.main()
