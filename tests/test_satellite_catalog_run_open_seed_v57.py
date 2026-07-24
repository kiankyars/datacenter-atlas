from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas import satellite_batch
from datacenter_atlas.satellite_batch import (
    BatchConfig,
    SatelliteBatchError,
    execute_satellite_queue,
    validate_satellite_batch,
)
from scripts.run_satellite_review_queue import (
    SatelliteRunnerLockError,
    _single_writer_lock,
    _validated_lock_path,
)


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v57"
RUN = ROOT / "satellite_review_runs/2026-07-20-open-seed-v57-active-001"
LOCK = RUN.with_name(f"{RUN.name}.lock")
MANIFEST = RUN / "batch-manifest.json"

USER_AGENT = (
    "DataCenterAtlas/0.1 (open research satellite review queue; "
    "+https://github.com/kiankyars/semiconductors)"
)
CONFIG = BatchConfig(
    priority_tiers=["active_construction"],
    user_agent=USER_AGENT,
    minimum_interval_seconds=1,
    timeout_seconds=60,
    catalog_retries=0,
    max_job_attempts=3,
    max_response_bytes=16_777_216,
)

MANIFEST_BYTES = 100_439
MANIFEST_SHA256 = "4a701a4e099b4cbbfd2d3ed9750edabe20c5fdac20df566e239c15e28f99fbef"
TREE_SHA256 = "355b4ced1d5722cce60abcd99b4af76f0e3816d2af86c07b8d697e0551f444a4"
QUEUE_MANIFEST_SHA256 = (
    "578b4778e552b86c0c07c419a6dd72572d48aaef324ce42154e3e8621401a48c"
)
QUEUE_SHA256 = "a91f57f706e8c70a1b768e0506bfac7b2ac5c200f9fe0bbf8ee8a9a826bada99"
ARTIFACT_INVENTORY_SHA256 = (
    "15fbc6bbc70de5df7d17e253c1142784b76eed3589647a210841a3d237f701f7"
)
SELECTION_INVENTORY_SHA256 = (
    "20c1fd64d1024d1ac83cef83d31a9c39baa61b03deb729873f569f170224c7f0"
)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

SUMMARY = {
    "jobs_completed": 85,
    "jobs_failed": 0,
    "jobs_pending": 0,
    "jobs_selected": 87,
    "jobs_unavailable_no_scene": 2,
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
    "satq-ed5c45c9ee1bfba25a2f10c3": (
        10,
        "95b33a98-a85e-57af-b18d-6811a7fd3b20",
        "baseline",
        "no scene falls within the baseline temporal window",
    ),
    "satq-3c6f789981688519124eeb22": (
        14,
        "d8264840-e897-5554-87fb-b575a0fa7bf7",
        "current",
        "no scene falls within the current temporal window",
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


class OpenSeedV57SatelliteCatalogRunTests(unittest.TestCase):
    def test_frozen_run_validates_offline_with_exact_lineage_and_accounting(self) -> None:
        failure = AssertionError("catalog-run validation attempted network access")
        with patch.object(socket, "socket", side_effect=failure), patch.object(
            socket, "create_connection", side_effect=failure
        ), patch.object(socket, "getaddrinfo", side_effect=failure):
            manifest = validate_satellite_batch(QUEUE, RUN, config=CONFIG)

        self.assertEqual(MANIFEST.stat().st_size, MANIFEST_BYTES)
        self.assertEqual(sha256(MANIFEST), MANIFEST_SHA256)
        self.assertEqual(manifest["state"], "completed")
        self.assertEqual(manifest["summary"], SUMMARY)
        self.assertEqual(manifest["scope"], SCOPE)
        self.assertEqual(manifest["queue_bundle"]["manifest_sha256"], QUEUE_MANIFEST_SHA256)
        self.assertEqual(manifest["queue_bundle"]["queue_sha256"], QUEUE_SHA256)
        self.assertEqual(
            manifest["last_run"],
            {
                "budget_exhausted": False,
                "finished_at": "2026-07-21T00:20:29Z",
                "http_attempts_reserved": 174,
                "job_attempts": 87,
                "jobs_completed": 85,
                "jobs_failed": 0,
                "jobs_unavailable_no_scene": 2,
                "max_http_attempts": 174,
                "max_jobs": 87,
                "started_at": "2026-07-21T00:17:02Z",
            },
        )
        started = datetime.fromisoformat(
            manifest["last_run"]["started_at"].replace("Z", "+00:00")
        )
        finished = datetime.fromisoformat(
            manifest["last_run"]["finished_at"].replace("Z", "+00:00")
        )
        self.assertEqual((finished - started).total_seconds(), 207)
        self.assertEqual(
            manifest["last_run"]["http_attempts_reserved"],
            manifest["last_run"]["job_attempts"]
            * manifest["configuration"]["maximum_http_attempts_per_job"],
        )

    def test_selection_order_terminal_states_and_no_scene_rows_are_exact(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        queue_rows = [
            json.loads(line)
            for line in (QUEUE / "satellite-review-queue.jsonl").read_text().splitlines()
        ]
        active = [
            row for row in queue_rows if row["priority"]["tier"] == "active_construction"
        ]
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
        self.assertEqual([row["queue_position"] for row in active], list(range(1, 88)))
        self.assertEqual(
            [row["queue_id"] for row in active], [row[1] for row in selected]
        )
        self.assertEqual(canonical_digest([list(row) for row in selected]), SELECTION_INVENTORY_SHA256)
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
            self.assertEqual(len(job["failures"]), 1)

    def test_all_response_artifacts_and_request_facts_are_hash_bound(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        inventory: list[list[object]] = []
        response_bytes = 0
        response_files = 0
        job_manifest_bytes = 0
        for queue_id, job in manifest["jobs"].items():
            artifacts = job["artifacts"]
            if artifacts is None:
                continue
            catalog = RUN / job["output_directory"]
            for filename, checkpoint in artifacts.items():
                artifact = catalog / filename
                raw = artifact.read_bytes()
                self.assertEqual(len(raw), checkpoint["bytes"], artifact)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), checkpoint["sha256"], artifact)
                inventory.append(
                    [queue_id, filename, checkpoint["bytes"], checkpoint["sha256"]]
                )
                if filename.endswith("-response.json"):
                    response_files += 1
                    response_bytes += len(raw)
                elif filename == "manifest.json":
                    job_manifest_bytes += len(raw)

            pair = json.loads((catalog / "manifest.json").read_text())
            self.assertEqual(pair["queries"]["provider"], "earth-search-v1")
            for window in ("baseline", "current"):
                request = pair["queries"][window]["request"]
                self.assertEqual(request["method"], "POST")
                self.assertEqual(
                    request["url"], "https://earth-search.aws.element84.com/v1/search"
                )
                self.assertEqual(request["headers"], {"Content-Type": "application/json"})
                self.assertEqual(
                    pair["queries"][window]["raw_response_sha256"],
                    artifacts[f"{window}-response.json"]["sha256"],
                )

        inventory.sort()
        self.assertEqual(len(inventory), 255)
        self.assertEqual(canonical_digest(inventory), ARTIFACT_INVENTORY_SHA256)
        self.assertEqual((response_files, response_bytes), (170, 53_182_536))
        self.assertEqual(job_manifest_bytes, 3_217_994)
        self.assertEqual(sum(row[2] for row in inventory), 56_400_530)

    def test_catalog_scope_contains_no_semantic_or_atlas_claims(self) -> None:
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest["scope"], SCOPE)
        self.assertTrue(manifest["scope"]["review_required"])
        self.assertFalse(manifest["scope"]["atlas_mutation"])
        self.assertFalse(manifest["scope"]["change_analysis_executed"])
        keys = recursive_keys(manifest)
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
            }.isdisjoint(keys)
        )
        for flag in (
            "imagery_identity_inference",
            "imagery_lifecycle_inference",
            "imagery_operating_status_inference",
            "imagery_power_inference",
        ):
            self.assertFalse(manifest["scope"][flag])

    def test_tree_lock_tamper_and_terminal_resume_behavior_are_fail_closed(self) -> None:
        self.assertEqual(
            tree_inventory(RUN),
            (174, 256, 56_500_969, TREE_SHA256),
        )
        for path in [RUN, *RUN.rglob("*")]:
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555, path)
            else:
                self.assertTrue(path.is_file(), path)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)

        self.assertTrue(LOCK.is_file())
        self.assertFalse(LOCK.is_symlink())
        self.assertEqual((LOCK.stat().st_size, sha256(LOCK)), (0, EMPTY_SHA256))
        self.assertEqual(stat.S_IMODE(LOCK.stat().st_mode), 0o600)
        canonical_lock = _validated_lock_path(LOCK, RUN, QUEUE)
        self.assertEqual(canonical_lock, LOCK.resolve())
        with _single_writer_lock(canonical_lock), self.assertRaisesRegex(
            SatelliteRunnerLockError, "holds lock"
        ):
            with _single_writer_lock(canonical_lock):
                self.fail("a second runner acquired the canonical lock")

        target = (
            RUN
            / "jobs/satq-02a713b5d0ec25375cffb0c3/catalog/baseline-response.json"
        ).resolve()
        original_read_bytes = Path.read_bytes

        def tampered_read_bytes(path: Path) -> bytes:
            raw = original_read_bytes(path)
            return raw + b"tampered" if path.resolve() == target else raw

        with patch.object(Path, "read_bytes", tampered_read_bytes), self.assertRaises(
            SatelliteBatchError
        ):
            validate_satellite_batch(QUEUE, RUN, config=CONFIG)

        before = (MANIFEST.stat().st_ino, MANIFEST.stat().st_mtime_ns, sha256(MANIFEST))

        def forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("terminal resume attempted work or network access")

        with patch.object(satellite_batch, "_write_manifest") as write_manifest, patch.object(
            socket, "socket", side_effect=forbidden
        ), patch.object(socket, "create_connection", side_effect=forbidden), patch.object(
            socket, "getaddrinfo", side_effect=forbidden
        ):
            resumed = execute_satellite_queue(
                QUEUE,
                RUN,
                config=CONFIG,
                max_jobs=87,
                max_http_attempts=174,
                command_runner=forbidden,
                sleep=forbidden,
                timestamp=lambda: "2026-07-21T01:00:00Z",
            )
        self.assertEqual(write_manifest.call_count, 2)
        self.assertEqual(resumed["summary"], SUMMARY)
        self.assertEqual(resumed["last_run"]["job_attempts"], 0)
        self.assertEqual(resumed["last_run"]["http_attempts_reserved"], 0)
        self.assertEqual(
            (MANIFEST.stat().st_ino, MANIFEST.stat().st_mtime_ns, sha256(MANIFEST)),
            before,
        )


if __name__ == "__main__":
    unittest.main()
