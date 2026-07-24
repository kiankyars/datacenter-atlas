from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_change_batch import (
    ChangeBatchConfig,
    validate_satellite_change_batch,
)


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v56"
CATALOG = ROOT / "satellite_review_runs/2026-07-20-open-seed-v56-active-001"
INCIDENT = ROOT / "satellite_change_runs/2026-07-20-open-seed-v56-active-001"
RUN = (
    ROOT
    / "satellite_change_runs/2026-07-20-open-seed-v56-active-runtime-retry-001"
)

QUEUE_IDS = [
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-54c6402eb93d14f1ea754e66",
    "satq-b6f121dc644b91ad78eb479a",
    "satq-ef22ae26b5cba60034c8567f",
    "satq-511257788faac7f8fe916b55",
    "satq-5feb20b3df63076cce05ab3f",
]
INCIDENT_PIN = (
    29_299,
    "d2897172ad301f51e6a93e5beaf6f2a4dc4945833c520e2b704b907e705ca67c",
    (9, 1, "2ed63f1c25e590a654c944b6abac1da5f28a46a9d0bfaeb0eead4eaaadd12db7"),
)
RUN_PIN = (
    42_990,
    "f94fb3298b352dc579ae5d07020e442889424e782ee04dbbe6f306826270c5f8",
    (15, 37, "1305b37c874bc6c136da1e0d4f31b254c3bea5a831bc87d19eb5d9830b815806"),
)
PENTAPOINT_QUEUE_ID = "satq-b6f121dc644b91ad78eb479a"
MOSAIC_BLOCKER_QUEUE_ID = "satq-54c6402eb93d14f1ea754e66"


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
            raise AssertionError(f"change run contains symlink: {relative}")
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
            raise AssertionError(f"unsupported change-run entry: {relative}")
    return directories, files, digest.hexdigest()


def assert_frozen(test: unittest.TestCase, root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if path.is_dir():
            test.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555, path)
        else:
            test.assertTrue(path.is_file(), path)
            test.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)


class OpenSeedV56SatelliteChangeRunTests(unittest.TestCase):
    def test_no_raster_attempt_is_retained_as_a_technical_incident(self) -> None:
        manifest_path = INCIDENT / "batch-manifest.json"
        expected_bytes, expected_sha256, expected_tree = INCIDENT_PIN
        self.assertEqual(manifest_path.stat().st_size, expected_bytes)
        self.assertEqual(sha256(manifest_path), expected_sha256)
        self.assertEqual(tree_inventory(INCIDENT), expected_tree)
        assert_frozen(self, INCIDENT)

        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            manifest["summary"],
            {
                "catalog_completed_jobs": 7,
                "catalog_completed_jobs_excluded": 0,
                "catalog_completed_jobs_not_in_inclusion": 0,
                "exclusion_ids_without_completed_catalog": 0,
                "jobs_completed": 0,
                "jobs_exhausted": 0,
                "jobs_failed": 7,
                "jobs_pending": 0,
                "jobs_running": 0,
                "jobs_selected": 7,
            },
        )
        self.assertFalse(manifest["processor"]["runtime"]["required_packages_available"])
        for job in manifest["jobs"].values():
            self.assertEqual(job["state"], "failed")
            self.assertIsNone(job["artifacts"])
            self.assertIsNone(job["report"])
            self.assertIn("Install the optional imagery runtime", job["failures"][0]["error"])

    def test_runtime_retry_validates_offline_and_is_frozen(self) -> None:
        config = ChangeBatchConfig()
        failure = AssertionError("change-run validation attempted network access")
        with patch.object(socket, "socket", side_effect=failure), patch.object(
            socket, "create_connection", side_effect=failure
        ), patch.object(socket, "getaddrinfo", side_effect=failure):
            manifest = validate_satellite_change_batch(
                QUEUE,
                [CATALOG],
                RUN,
                config=config,
                include_queue_ids=QUEUE_IDS,
            )

        manifest_path = RUN / "batch-manifest.json"
        expected_bytes, expected_sha256, expected_tree = RUN_PIN
        self.assertEqual(manifest_path.stat().st_size, expected_bytes)
        self.assertEqual(sha256(manifest_path), expected_sha256)
        self.assertEqual(tree_inventory(RUN), expected_tree)
        assert_frozen(self, RUN)
        self.assertEqual(manifest["state"], "incomplete")
        self.assertEqual(manifest["summary"]["jobs_completed"], 6)
        self.assertEqual(manifest["summary"]["jobs_failed"], 1)
        self.assertEqual(manifest["summary"]["jobs_pending"], 0)
        self.assertTrue(manifest["processor"]["runtime"]["required_packages_available"])

    def test_only_known_multitile_blocker_failed(self) -> None:
        manifest = json.loads((RUN / "batch-manifest.json").read_text())
        failed = {
            queue_id: job
            for queue_id, job in manifest["jobs"].items()
            if job["state"] == "failed"
        }
        self.assertEqual(set(failed), {MOSAIC_BLOCKER_QUEUE_ID})
        blocker = failed[MOSAIC_BLOCKER_QUEUE_ID]
        self.assertEqual(blocker["attempts"], 1)
        self.assertIn(
            "AOI covering window crosses asset red; a future multi-tile mosaic is required",
            blocker["failures"][0]["error"],
        )
        self.assertIsNone(blocker["artifacts"])
        self.assertIsNone(blocker["report"])

    def test_pentapoint_has_review_only_visible_change_proposals(self) -> None:
        manifest = json.loads((RUN / "batch-manifest.json").read_text())
        job = manifest["jobs"][PENTAPOINT_QUEUE_ID]
        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["queue_position"], 4)
        self.assertEqual(job["entity"]["name"], "PentaPoint EMD BKK-01 Development")
        self.assertEqual(
            job["report"]["classification"]["label"],
            "large_spectral_change_candidate",
        )
        self.assertEqual(job["report"]["metrics"]["proposal_component_count"], 14)
        self.assertEqual(
            job["report"]["metrics"]["proposal_area_m2_after_component_filter"],
            115_400.0,
        )
        classification = job["report"]["classification"]
        self.assertTrue(classification["review_required"])
        for key, value in classification.items():
            if key.endswith("_claim"):
                self.assertFalse(value, key)

    def test_every_completed_report_is_advisory_and_atlas_is_untouched(self) -> None:
        manifest = json.loads((RUN / "batch-manifest.json").read_text())
        self.assertFalse(manifest["scope"]["atlas_mutation"])
        for key, value in manifest["scope"].items():
            if key.startswith("imagery_"):
                self.assertFalse(value, key)
        for job in manifest["jobs"].values():
            if job["state"] != "completed":
                continue
            classification = job["report"]["classification"]
            self.assertTrue(classification["review_required"])
            for key, value in classification.items():
                if key.endswith("_claim"):
                    self.assertFalse(value, (job["queue_id"], key))


if __name__ == "__main__":
    unittest.main()
