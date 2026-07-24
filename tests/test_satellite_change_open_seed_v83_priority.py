from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import stat
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
CATALOG = ROOT / "satellite_review_runs/2026-07-21-open-seed-v83-active-002"
INCIDENT = ROOT / "satellite_change_runs/2026-07-21-open-seed-v83-active-priority-001"
RUN = ROOT / "satellite_change_runs/2026-07-21-open-seed-v83-active-priority-002"
UNREVIEWED_BLOCKERS = (
    ROOT / "satellite_change_runs/2026-07-21-open-seed-v83-active-unreviewed-001"
)
UNREVIEWED_REMAINDER = (
    ROOT
    / "satellite_change_runs/2026-07-21-open-seed-v83-active-unreviewed-remaining-001"
)

INCIDENT_MANIFEST_PIN = (
    22_410,
    "8eee27c7f239560e87e0f3a5a40cb8b4fb7703742fd3827c9f813c0329870f73",
)
INCIDENT_TREE_PIN = "89d4ff05a7c8be7cbfc502769cbf40906c4d785e569b98d0dde64cfa3273988f"
RUN_MANIFEST_PIN = (
    32_227,
    "8357a6a3219315bb01620af13066415cf9fd76796fe56e8c1bd9a23708251993",
)
RUN_TREE_PIN = "713428e802254a07686ce700794a4dafcd0abd8c6e75c83e955e0e69e6890e31"
UNREVIEWED_BLOCKERS_MANIFEST_PIN = (
    31_258,
    "5385f96507cc999e0183e391744dc80264a1d2ea39646d182307cab2f4036525",
)
UNREVIEWED_BLOCKERS_TREE_PIN = (
    "2cba33b81cf7eeae84785f901ee1439185b47fa972f5bc27da6dbf42e0dc571b"
)
UNREVIEWED_REMAINDER_MANIFEST_PIN = (
    386_657,
    "399d66cec56ac57aabd097b8d9c16e302a94f47b3651c2aca6afa1dfcb29bb8a",
)
UNREVIEWED_REMAINDER_TREE_PIN = (
    "83096e75f913d79b9a2db63110d1dc53d3e5db58c27e8590f52009c4caa091af"
)
COMPLETED_QUEUE_IDS = {
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-1f72804d5d56bb342d5e2e2c",
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-b6f121dc644b91ad78eb479a",
}
MOSAIC_BLOCKER_QUEUE_ID = "satq-54c6402eb93d14f1ea754e66"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            raise AssertionError(f"change run contains symlink: {relative}")
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
            raise AssertionError(f"unsupported change-run entry: {relative}")
    return directories, files, file_bytes, digest.hexdigest()


def assert_frozen(test: unittest.TestCase, root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        expected = 0o555 if path.is_dir() else 0o444
        test.assertEqual(stat.S_IMODE(path.stat().st_mode), expected, path)


def pinned_runtime_available() -> bool:
    if sys.version_info[:2] != (3, 12):
        return False
    expected = {"numpy": "2.5.1", "Pillow": "12.3.0", "rasterio": "1.5.0"}
    try:
        return all(
            importlib.metadata.version(name) == value
            for name, value in expected.items()
        )
    except importlib.metadata.PackageNotFoundError:
        return False


class OpenSeedV83PriorityChangeRunTests(unittest.TestCase):
    def test_missing_runtime_attempt_is_a_frozen_technical_incident(self) -> None:
        manifest_path = INCIDENT / "batch-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            (manifest_path.stat().st_size, sha256(manifest_path)), INCIDENT_MANIFEST_PIN
        )
        self.assertEqual(
            manifest["summary"],
            {
                "catalog_completed_jobs": 101,
                "catalog_completed_jobs_excluded": 0,
                "catalog_completed_jobs_not_in_inclusion": 96,
                "exclusion_ids_without_completed_catalog": 0,
                "jobs_completed": 0,
                "jobs_exhausted": 5,
                "jobs_failed": 5,
                "jobs_pending": 0,
                "jobs_running": 0,
                "jobs_selected": 5,
            },
        )
        self.assertFalse(
            manifest["processor"]["runtime"]["required_packages_available"]
        )
        for job in manifest["jobs"].values():
            self.assertEqual(job["state"], "failed")
            self.assertIsNone(job["artifacts"])
            self.assertIn("optional imagery runtime", job["failures"][0]["error"])
        self.assertEqual(tree_inventory(INCIDENT), (7, 1, 22_410, INCIDENT_TREE_PIN))
        assert_frozen(self, INCIDENT)

    def test_six_net_new_jobs_are_frozen_multi_tile_technical_blockers(self) -> None:
        manifest_path = UNREVIEWED_BLOCKERS / "batch-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            (manifest_path.stat().st_size, sha256(manifest_path)),
            UNREVIEWED_BLOCKERS_MANIFEST_PIN,
        )
        self.assertEqual(manifest["summary"]["jobs_selected"], 6)
        self.assertEqual(manifest["summary"]["jobs_completed"], 0)
        self.assertEqual(manifest["summary"]["jobs_exhausted"], 6)
        self.assertEqual(manifest["summary"]["jobs_pending"], 0)
        self.assertEqual(
            {job["queue_position"] for job in manifest["jobs"].values()},
            {8, 17, 31, 62, 65, 78},
        )
        for job in manifest["jobs"].values():
            self.assertEqual(job["state"], "failed")
            self.assertIsNone(job["artifacts"])
            self.assertIn(
                "future multi-tile mosaic is required", job["failures"][0]["error"]
            )
        self.assertEqual(
            tree_inventory(UNREVIEWED_BLOCKERS),
            (8, 1, 31_258, UNREVIEWED_BLOCKERS_TREE_PIN),
        )
        assert_frozen(self, UNREVIEWED_BLOCKERS)

    def test_pinned_runtime_run_has_four_proposals_and_one_technical_blocker(
        self,
    ) -> None:
        manifest_path = RUN / "batch-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            (manifest_path.stat().st_size, sha256(manifest_path)), RUN_MANIFEST_PIN
        )
        self.assertEqual(
            manifest["summary"],
            {
                "catalog_completed_jobs": 101,
                "catalog_completed_jobs_excluded": 0,
                "catalog_completed_jobs_not_in_inclusion": 96,
                "exclusion_ids_without_completed_catalog": 0,
                "jobs_completed": 4,
                "jobs_exhausted": 1,
                "jobs_failed": 1,
                "jobs_pending": 0,
                "jobs_running": 0,
                "jobs_selected": 5,
            },
        )
        completed = {
            queue_id
            for queue_id, job in manifest["jobs"].items()
            if job["state"] == "completed"
        }
        self.assertEqual(completed, COMPLETED_QUEUE_IDS)
        blocker = manifest["jobs"][MOSAIC_BLOCKER_QUEUE_ID]
        self.assertEqual(blocker["state"], "failed")
        self.assertIsNone(blocker["artifacts"])
        self.assertIn(
            "future multi-tile mosaic is required", blocker["failures"][0]["error"]
        )

        for queue_id in COMPLETED_QUEUE_IDS:
            job = manifest["jobs"][queue_id]
            self.assertEqual(
                set(job["artifacts"]),
                {
                    "after.png",
                    "before.png",
                    "change-overlay.png",
                    "change-proposals.geojson",
                    "comparison.png",
                    "report.json",
                },
            )
            output = RUN / job["change_job"]["output_directory"]
            for filename, pin in job["artifacts"].items():
                artifact = output / filename
                self.assertEqual(
                    (artifact.stat().st_size, sha256(artifact)),
                    (pin["bytes"], pin["sha256"]),
                )
            classification = job["report"]["classification"]
            self.assertTrue(classification["review_required"])
            for key, value in classification.items():
                if key.endswith("_claim"):
                    self.assertFalse(value, (queue_id, key))

        self.assertEqual(tree_inventory(RUN), (11, 25, 6_821_644, RUN_TREE_PIN))
        assert_frozen(self, RUN)

    def test_corrected_unreviewed_remainder_has_68_frozen_proposals(self) -> None:
        manifest_path = UNREVIEWED_REMAINDER / "batch-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            (manifest_path.stat().st_size, sha256(manifest_path)),
            UNREVIEWED_REMAINDER_MANIFEST_PIN,
        )
        self.assertEqual(manifest["state"], "completed")
        self.assertEqual(manifest["summary"]["jobs_selected"], 68)
        self.assertEqual(manifest["summary"]["jobs_completed"], 68)
        self.assertEqual(manifest["summary"]["jobs_failed"], 0)
        self.assertEqual(manifest["summary"]["jobs_exhausted"], 0)
        self.assertEqual(manifest["summary"]["jobs_pending"], 0)
        self.assertEqual(len(manifest["selection"]["selected_queue_ids"]), 68)
        self.assertEqual(
            set(manifest["jobs"]), set(manifest["selection"]["selected_queue_ids"])
        )

        for queue_id, job in manifest["jobs"].items():
            self.assertEqual(job["state"], "completed")
            self.assertEqual(job["attempts"], 1)
            self.assertEqual(len(job["artifacts"]), 6)
            output = UNREVIEWED_REMAINDER / job["change_job"]["output_directory"]
            for filename, pin in job["artifacts"].items():
                artifact = output / filename
                self.assertEqual(
                    (artifact.stat().st_size, sha256(artifact)),
                    (pin["bytes"], pin["sha256"]),
                )
            classification = job["report"]["classification"]
            self.assertTrue(classification["review_required"])
            for key, value in classification.items():
                if key.endswith("_claim"):
                    self.assertFalse(value, (queue_id, key))

        self.assertEqual(
            tree_inventory(UNREVIEWED_REMAINDER),
            (138, 409, 108_590_556, UNREVIEWED_REMAINDER_TREE_PIN),
        )
        assert_frozen(self, UNREVIEWED_REMAINDER)

    def test_successor_run_validates_offline_under_its_exact_runtime(self) -> None:
        if not pinned_runtime_available():
            self.skipTest("exact Python 3.12 imagery runtime is unavailable")
        try:
            module = importlib.import_module(
                "datacenter_atlas.datacenter_atlas.satellite_change_batch"
            )
        except ModuleNotFoundError:
            module = importlib.import_module("datacenter_atlas.satellite_change_batch")
        config = module.ChangeBatchConfig(
            timeout_seconds=1800,
            minimum_interval_seconds=1.1,
            max_job_attempts=1,
        )
        manifest = module.validate_satellite_change_batch(
            QUEUE, [CATALOG], RUN, config=config
        )
        self.assertEqual(manifest["summary"]["jobs_completed"], 4)
        self.assertEqual(manifest["summary"]["jobs_exhausted"], 1)
        remainder = module.validate_satellite_change_batch(
            QUEUE, [CATALOG], UNREVIEWED_REMAINDER, config=config
        )
        self.assertEqual(remainder["summary"]["jobs_completed"], 68)
        self.assertEqual(remainder["summary"]["jobs_failed"], 0)


if __name__ == "__main__":
    unittest.main()
