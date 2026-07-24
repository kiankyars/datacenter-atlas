from __future__ import annotations

from collections import Counter
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

import datacenter_atlas.satellite_queue_v83 as accepted_predecessor
import datacenter_atlas.satellite_queue_v86 as subject
from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
)


FINAL_GENERATED_AT = "2026-07-21T20:32:37Z"
FINAL_MANIFEST_PIN = (
    20_579,
    "1a417f11e94dadbca2f5c1ddf0746d6ce5eca6ccb734957f8a3c825edab217c0",
)
FINAL_SIDECAR_PIN = (
    80,
    "1936b82892a9d60ebdc0e2265e96dddb477520e05ecede27c7b351de8845e7e4",
)
FINAL_TREE_PIN = (
    "e9611d94eff7a6cc62b22a1a3291651acaa01db468889c500455b9fb2908f1c5"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OpenSeedV86SatelliteQueueTests(unittest.TestCase):
    def _network_patches(self) -> tuple[patch, ...]:
        failure = AssertionError("v86 queue attempted network access")
        return (
            patch.object(socket, "socket", side_effect=failure),
            patch.object(socket, "create_connection", side_effect=failure),
            patch.object(socket, "getaddrinfo", side_effect=failure),
        )

    def test_frozen_inputs_and_v83_predecessor_validate_independently(self) -> None:
        before = subject._require_accepted_inputs()
        predecessor = accepted_predecessor.validate_satellite_queue_v83()
        after = subject._require_accepted_inputs()
        self.assertEqual(before, after)
        self.assertEqual(before["release_tree_sha256"], subject.RELEASE_TREE_SHA256)
        self.assertEqual(predecessor["counts"]["queue_jobs"], 200)
        self.assertIs(subject, __import__("datacenter_atlas.satellite_queue_v86", fromlist=["x"]))

    def test_two_offline_replays_have_exact_digest_and_counts(self) -> None:
        patches = self._network_patches()
        with patches[0], patches[1], patches[2]:
            first = subject._bundle("2026-07-21T20:30:00Z")
            second = subject._bundle("2026-07-21T20:30:00Z")
        self.assertEqual(subject._payloads(first), subject._payloads(second))
        subject._validate_semantics(first)
        self.assertEqual(
            (len(first.queue_bytes), hashlib.sha256(first.queue_bytes).hexdigest()),
            subject.QUEUE_PIN,
        )
        self.assertEqual(
            {
                key: first.manifest["counts"][key]
                for key in subject.EXPECTED_COUNTS
            },
            subject.EXPECTED_COUNTS,
        )
        with self.assertRaisesRegex(subject.SatelliteQueueV86Error, "exactly two"):
            subject.validate_satellite_queue_v86(replay_count=1)

    def test_v83_delta_is_retained_200_added_15_removed_zero(self) -> None:
        predecessor = [
            json.loads(line)
            for line in (
                subject.PREDECESSOR_QUEUE / QUEUE_FILENAME
            ).read_bytes().splitlines()
        ]
        successor = [
            json.loads(line)
            for line in subject._bundle(
                "2026-07-21T20:30:00Z"
            ).queue_bytes.splitlines()
        ]
        before = {row["queue_id"]: row for row in predecessor}
        after = {row["queue_id"]: row for row in successor}
        added = set(after) - set(before)
        retained = set(after) & set(before)
        self.assertEqual(len(retained), 200)
        self.assertEqual(added, set(subject.ADDED_QUEUE_EXPECTATIONS))
        self.assertEqual(set(before) - set(after), set())
        position_changes = 0
        semantic_changes = 0
        for queue_id in retained:
            old = dict(before[queue_id])
            new = dict(after[queue_id])
            position_changes += old.pop("queue_position") != new.pop("queue_position")
            semantic_changes += old != new
        self.assertEqual(position_changes, 182)
        self.assertEqual(len(retained) - position_changes, 18)
        self.assertEqual(semantic_changes, 0)
        added_rows = [after[queue_id] for queue_id in added]
        self.assertEqual(
            Counter(row["priority"]["tier"] for row in added_rows),
            subject.ADDED_PRIORITY_COUNTS,
        )
        self.assertEqual(
            Counter(row["priority"]["lifecycle_status"] for row in added_rows),
            subject.ADDED_STATUS_COUNTS,
        )

    def test_review_centers_and_no_imagery_claim_boundary_are_exact(self) -> None:
        bundle = subject._bundle("2026-07-21T20:30:00Z")
        rows = [json.loads(line) for line in bundle.queue_bytes.splitlines()]
        methods = Counter(
            row["location"]["center_wgs84"]["method"] for row in rows
        )
        self.assertEqual(methods, subject.COORDINATE_METHOD_COUNTS)
        geometry_only = {
            row["entity"]["id"]
            for row in rows
            if row["location"]["center_wgs84"]["method"]
            == "geometry_bounds_center"
        }
        self.assertEqual(geometry_only, subject.GEOMETRY_ONLY_ENTITY_IDS)
        for row in rows:
            self.assertEqual(row["review_constraints"], subject.carrier.REVIEW_CONSTRAINTS)
            self.assertFalse(
                {
                    "capacity_estimates",
                    "operating_model",
                    "workloads",
                    "workload_observations",
                }
                & set(row["entity"])
            )
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

    def test_future_atomic_publication_freezes_after_target(self) -> None:
        patches = self._network_patches()
        with tempfile.TemporaryDirectory(prefix="satellite-queue-v86-publish-") as temporary:
            root = Path(temporary)
            parent = root / "queues"
            parent.mkdir()
            output = parent / "v86"
            lock = root / ".v86.lock"
            now = datetime.now(UTC)
            target = (now + timedelta(seconds=4)).replace(microsecond=0)
            if target <= now:
                target += timedelta(seconds=4)
            generated_at = target.isoformat().replace("+00:00", "Z")
            observations: list[bool] = []

            def sleeper(seconds: float) -> None:
                observations.append(output.exists() or output.is_symlink())
                time.sleep(seconds)

            with patches[0], patches[1], patches[2]:
                manifest = subject._publish_to(
                    output,
                    lock,
                    generated_at=generated_at,
                    clock=time.time,
                    sleeper=sleeper,
                )
            self.assertTrue(observations)
            self.assertFalse(any(observations))
            self.assertEqual(manifest["counts"]["queue_jobs"], 215)
            self.assertGreaterEqual(
                output.stat().st_ctime + 0.000_001, target.timestamp()
            )
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, QUEUE_FILENAME},
            )
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o444
                    for path in output.iterdir()
                )
            )
            self.assertFalse(lock.exists())

    def test_collision_and_post_validation_failure_roll_back_without_residue(self) -> None:
        patches = self._network_patches()
        with tempfile.TemporaryDirectory(prefix="satellite-queue-v86-rollback-") as temporary:
            root = Path(temporary)
            parent = root / "queues"
            parent.mkdir()
            output = parent / "v86"
            lock = root / ".v86.lock"
            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=60)
            generated_at = target.isoformat().replace("+00:00", "Z")
            now = [time.time()]

            def clock() -> float:
                return now[0]

            def sleeper(seconds: float) -> None:
                now[0] += seconds

            def collide(_source: Path, destination: Path) -> None:
                destination.mkdir()
                (destination / "sentinel").write_text("owned\n")
                raise FileExistsError("injected v86 queue collision")

            with (
                patches[0],
                patches[1],
                patches[2],
                patch.object(subject, "promote_noreplace", side_effect=collide),
                self.assertRaisesRegex(FileExistsError, "injected"),
            ):
                subject._publish_to(
                    output,
                    lock,
                    generated_at=generated_at,
                    clock=clock,
                    sleeper=sleeper,
                )
            self.assertEqual((output / "sentinel").read_text(), "owned\n")
            self.assertFalse(lock.exists())
            self.assertEqual(
                [path.name for path in parent.iterdir()], ["v86"]
            )

        with tempfile.TemporaryDirectory(prefix="satellite-queue-v86-post-") as temporary:
            root = Path(temporary)
            parent = root / "queues"
            parent.mkdir()
            output = parent / "v86"
            lock = root / ".v86.lock"
            now = datetime.now(UTC)
            target = (now + timedelta(seconds=4)).replace(microsecond=0)
            if target <= now:
                target += timedelta(seconds=4)
            generated_at = target.isoformat().replace("+00:00", "Z")
            original = subject.validate_satellite_queue_v86

            def fail_final(path: str | Path = subject.QUEUE, **kwargs: object):
                if Path(path) == output:
                    raise subject.SatelliteQueueV86Error(
                        "injected post-promotion queue validation failure"
                    )
                return original(path, **kwargs)

            with (
                patch.object(
                    subject, "validate_satellite_queue_v86", side_effect=fail_final
                ),
                self.assertRaisesRegex(
                    subject.SatelliteQueueV86Error, "post-promotion"
                ),
            ):
                subject._publish_to(
                    output,
                    lock,
                    generated_at=generated_at,
                    clock=time.time,
                    sleeper=time.sleep,
                )
            self.assertFalse(output.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(parent.iterdir()), [])

    def test_frozen_final_or_clean_prepublication_state(self) -> None:
        if not subject.QUEUE.exists() and not subject.QUEUE.is_symlink():
            return
        self.assertIsNotNone(FINAL_GENERATED_AT)
        self.assertIsNotNone(FINAL_MANIFEST_PIN)
        self.assertIsNotNone(FINAL_SIDECAR_PIN)
        self.assertIsNotNone(FINAL_TREE_PIN)
        manifest = subject.validate_satellite_queue_v86()
        self.assertEqual(manifest["generated_at"], FINAL_GENERATED_AT)
        self.assertEqual(
            (
                (subject.QUEUE / MANIFEST_FILENAME).stat().st_size,
                sha256(subject.QUEUE / MANIFEST_FILENAME),
            ),
            FINAL_MANIFEST_PIN,
        )
        self.assertEqual(
            (
                (subject.QUEUE / MANIFEST_HASH_FILENAME).stat().st_size,
                sha256(subject.QUEUE / MANIFEST_HASH_FILENAME),
            ),
            FINAL_SIDECAR_PIN,
        )
        self.assertEqual(subject._tree_digest(subject.QUEUE), FINAL_TREE_PIN)


if __name__ == "__main__":
    unittest.main()
