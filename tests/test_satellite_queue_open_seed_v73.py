from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

import datacenter_atlas.satellite_queue_v73 as subject
from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    write_queue_bundle,
)


def _freeze(directory: Path) -> None:
    for path in directory.iterdir():
        path.chmod(0o444)
    directory.chmod(0o555)


class OpenSeedV73SatelliteQueueTests(unittest.TestCase):
    def test_published_final_is_exact_and_frozen(self) -> None:
        manifest = subject.validate_satellite_queue_v73()
        self.assertEqual(manifest["generated_at"], subject.PUBLISHED_GENERATED_AT)
        self.assertEqual(
            hashlib.sha256((subject.QUEUE / MANIFEST_FILENAME).read_bytes()).hexdigest(),
            subject.PUBLISHED_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (subject.QUEUE / MANIFEST_HASH_FILENAME).read_bytes()
            ).hexdigest(),
            subject.PUBLISHED_MANIFEST_HASH_SHA256,
        )
        self.assertEqual(subject._tree_digest(subject.QUEUE), subject.PUBLISHED_TREE_SHA256)

    def test_two_offline_builds_have_exact_hash_counts_and_audited_order(self) -> None:
        failure = AssertionError("v73 queue construction attempted network access")
        with patch.object(socket, "socket", side_effect=failure), patch.object(
            socket, "create_connection", side_effect=failure
        ), patch.object(socket, "getaddrinfo", side_effect=failure):
            first = subject._bundle("2026-07-21T14:00:00Z")
            second = subject._bundle("2026-07-21T14:00:00Z")

        self.assertEqual(subject._payloads(first), subject._payloads(second))
        self.assertEqual(len(first.queue_bytes), subject.QUEUE_BYTES)
        self.assertEqual(
            hashlib.sha256(first.queue_bytes).hexdigest(), subject.QUEUE_SHA256
        )
        self.assertEqual(
            first.manifest["counts"]["queued_entities_by_priority_tier"],
            {
                "active_construction": 100,
                "operational": 29,
                "proposed_pipeline": 5,
                "unknown": 58,
            },
        )
        self.assertEqual(first.manifest["counts"]["skipped_missing_coordinates"], 626)
        rows = [json.loads(line) for line in first.queue_bytes.splitlines()]
        active = [row for row in rows if row["priority"]["tier"] == "active_construction"]
        self.assertEqual(len(active), 100)
        self.assertEqual(
            len({tuple(row["location"]["aoi_bbox_wgs84"]) for row in active}),
            96,
        )
        by_id = {row["queue_id"]: row for row in rows}
        self.assertEqual(
            tuple(by_id[queue_id]["queue_position"] for queue_id in subject.AUDITED_QUEUE_IDS),
            subject.EXPECTED_AUDITED_POSITIONS,
        )

    def test_successor_adds_exactly_three_review_only_jobs(self) -> None:
        predecessor_rows = [
            json.loads(line)
            for line in (
                Path(__file__).resolve().parents[1]
                / "satellite_review_queues/2026-07-21-open-seed-v71"
                / QUEUE_FILENAME
            ).read_bytes().splitlines()
        ]
        successor_rows = [
            json.loads(line)
            for line in subject._bundle("2026-07-21T14:00:00Z").queue_bytes.splitlines()
        ]
        predecessor_by_id = {row["queue_id"]: row for row in predecessor_rows}
        successor_by_id = {row["queue_id"]: row for row in successor_rows}
        self.assertEqual(
            set(successor_by_id) - set(predecessor_by_id),
            set(subject.ADDED_QUEUE_EXPECTATIONS),
        )
        self.assertEqual(set(predecessor_by_id) - set(successor_by_id), set())
        for queue_id in set(predecessor_by_id) & set(successor_by_id):
            predecessor = dict(predecessor_by_id[queue_id])
            successor = dict(successor_by_id[queue_id])
            predecessor.pop("queue_position")
            successor.pop("queue_position")
            self.assertEqual(predecessor, successor)
        for row in successor_rows:
            self.assertEqual(
                {
                    key: row["review_constraints"][key]
                    for key in (
                        "imagery_identity_claim",
                        "imagery_lifecycle_claim",
                        "imagery_operating_status_claim",
                        "imagery_power_claim",
                    )
                },
                {
                    "imagery_identity_claim": False,
                    "imagery_lifecycle_claim": False,
                    "imagery_operating_status_claim": False,
                    "imagery_power_claim": False,
                },
            )

    def test_future_private_publication_freezes_and_renames_after_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "queues"
            parent.mkdir()
            output = parent / "v73"
            lock = root / ".v73.lock"
            now = datetime.now(UTC)
            target = (now + timedelta(seconds=2)).replace(microsecond=0)
            if target <= now:
                target += timedelta(seconds=1)
            generated_at = target.isoformat().replace("+00:00", "Z")
            sleep_observations: list[bool] = []

            def sleeper(seconds: float) -> None:
                sleep_observations.append(output.exists() or output.is_symlink())
                time.sleep(seconds)

            manifest = subject._publish_to(
                output,
                lock,
                generated_at=generated_at,
                clock=time.time,
                sleeper=sleeper,
            )
            self.assertTrue(sleep_observations)
            self.assertFalse(any(sleep_observations))
            self.assertEqual(manifest["counts"]["queue_jobs"], 192)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
            self.assertGreaterEqual(output.stat().st_ctime + 0.000_001, target.timestamp())
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, QUEUE_FILENAME},
            )
            self.assertTrue(
                all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in output.iterdir())
            )

    def test_tamper_collision_and_symlink_fail_without_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            write_queue_bundle(
                subject.ATLAS,
                queue,
                generated_at="2026-07-21T14:00:00Z",
                config=subject.CONFIG,
            )
            _freeze(queue)
            subject.validate_satellite_queue_v73(
                queue, require_final_root_ctime=False
            )
            queue.chmod(0o755)
            target = queue / QUEUE_FILENAME
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b"{}\n")
            target.chmod(0o444)
            queue.chmod(0o555)
            with self.assertRaisesRegex(
                subject.SatelliteQueueV73Error, "byte count|SHA-256"
            ):
                subject.validate_satellite_queue_v73(
                    queue, require_final_root_ctime=False
                )

            parent = root / "outputs"
            parent.mkdir()
            occupied = parent / "occupied"
            occupied.write_text("sentinel", encoding="utf-8")
            before = occupied.read_bytes()
            generated_at = (
                datetime.now(UTC) + timedelta(seconds=30)
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            with self.assertRaisesRegex(subject.SatelliteQueueV73Error, "occupied"):
                subject._publish_to(
                    occupied,
                    root / ".occupied.lock",
                    generated_at=generated_at,
                    clock=time.time,
                    sleeper=time.sleep,
                )
            self.assertEqual(occupied.read_bytes(), before)

            link = parent / "link"
            link.symlink_to(occupied)
            with self.assertRaisesRegex(subject.SatelliteQueueV73Error, "occupied"):
                subject._publish_to(
                    link,
                    root / ".link.lock",
                    generated_at=generated_at,
                    clock=time.time,
                    sleeper=time.sleep,
                )
            self.assertTrue(link.is_symlink())


if __name__ == "__main__":
    unittest.main()
