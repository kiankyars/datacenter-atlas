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

import datacenter_atlas.open_seed_v83 as accepted_seed
import datacenter_atlas.satellite_queue_v73 as accepted_predecessor
import datacenter_atlas.satellite_queue_v83 as subject
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


class OpenSeedV83SatelliteQueueTests(unittest.TestCase):
    def test_accepted_v83_and_v73_validate_independently(self) -> None:
        seed_manifest = accepted_seed.validate_open_seed_v83()
        predecessor_manifest = accepted_predecessor.validate_satellite_queue_v73()
        self.assertEqual(seed_manifest["recorded_at"], "2026-07-21T17:38:10Z")
        self.assertEqual(predecessor_manifest["counts"]["queue_jobs"], 192)
        self.assertEqual(
            subject._require_accepted_inputs()["release_tree_sha256"],
            subject.RELEASE_TREE_SHA256,
        )

    def test_published_final_is_exact_and_frozen(self) -> None:
        manifest = subject.validate_satellite_queue_v83()
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
        failure = AssertionError("v83 queue construction attempted network access")
        with patch.object(socket, "socket", side_effect=failure), patch.object(
            socket, "create_connection", side_effect=failure
        ), patch.object(socket, "getaddrinfo", side_effect=failure):
            first = subject._bundle("2026-07-21T18:00:00Z")
            second = subject._bundle("2026-07-21T18:00:00Z")

        self.assertEqual(subject._payloads(first), subject._payloads(second))
        subject._validate_semantics(first)
        self.assertEqual(len(first.queue_bytes), subject.QUEUE_BYTES)
        self.assertEqual(
            hashlib.sha256(first.queue_bytes).hexdigest(), subject.QUEUE_SHA256
        )
        self.assertEqual(
            first.manifest["counts"]["queued_entities_by_priority_tier"],
            {
                "active_construction": 104,
                "operational": 29,
                "proposed_pipeline": 5,
                "unknown": 62,
            },
        )
        rows = [json.loads(line) for line in first.queue_bytes.splitlines()]
        active = [row for row in rows if row["priority"]["tier"] == "active_construction"]
        self.assertEqual(len(active), 104)
        self.assertEqual(
            len({tuple(row["location"]["aoi_bbox_wgs84"]) for row in active}),
            100,
        )
        by_id = {row["queue_id"]: row for row in rows}
        self.assertEqual(
            tuple(by_id[queue_id]["queue_position"] for queue_id in subject.AUDITED_QUEUE_IDS),
            subject.EXPECTED_AUDITED_POSITIONS,
        )

    def test_successor_delta_and_coordinate_sources_are_exact(self) -> None:
        predecessor_rows = [
            json.loads(line)
            for line in (subject.PREDECESSOR_QUEUE / QUEUE_FILENAME).read_bytes().splitlines()
        ]
        successor_rows = [
            json.loads(line)
            for line in subject._bundle("2026-07-21T18:00:00Z").queue_bytes.splitlines()
        ]
        predecessor_by_id = {row["queue_id"]: row for row in predecessor_rows}
        successor_by_id = {row["queue_id"]: row for row in successor_rows}
        self.assertEqual(
            set(successor_by_id) - set(predecessor_by_id),
            set(subject.ADDED_QUEUE_EXPECTATIONS),
        )
        self.assertEqual(set(predecessor_by_id) - set(successor_by_id), set())
        semantic_changes = 0
        position_changes = 0
        for queue_id in set(predecessor_by_id) & set(successor_by_id):
            predecessor = dict(predecessor_by_id[queue_id])
            successor = dict(successor_by_id[queue_id])
            if predecessor.pop("queue_position") != successor.pop("queue_position"):
                position_changes += 1
            semantic_changes += predecessor != successor
        self.assertEqual(position_changes, subject.INHERITED_POSITION_CHANGE_COUNT)
        self.assertEqual(semantic_changes, subject.INHERITED_SEMANTIC_CHANGE_COUNT)

        definition = json.loads(subject.DEFINITION.read_bytes())
        selected = {row["path"]: row["sha256"] for row in definition["curated_inputs"]}
        expected_sources = {
            "sources/curated-official-2026-07-21-bcc-jashore-dr-data-center-current-build.json": (
                "534bf10ddf8139391d7b511a2b739a88cf1e6ca46d3ce4fb5a2e0e4d0540c100"
            ),
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-akashi-astana-"
            "phase-1-current-build-coordinate-v5.json": (
                "b1f3f37927895d6e7a02adc9afd8b93aac9e0a322d846158fe362c645a07e3a6"
            ),
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-icatec-ica-"
            "current-build-coordinate-v5.json": (
                "88d05044c8a3ab7ad7c4f0a42227cb610b2b0fff43863672c5faf0a121d31e2a"
            ),
            "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
            "normalized-successors/curated-official-2026-07-21-lvrtc-pozitrons-"
            "kurzeme-current-build-coordinate-v5.json": (
                "5fce778372ee4d01b8e7990a11624ed2d588007c9a071e7f73a9e2a8a117e426"
            ),
        }
        self.assertEqual(
            {path: selected.get(path) for path in expected_sources}, expected_sources
        )

        atlas = json.loads(subject.ATLAS.read_bytes())
        atlas_by_id = {feature["id"]: feature["properties"] for feature in atlas["features"]}
        added = [successor_by_id[queue_id] for queue_id in subject.ADDED_QUEUE_EXPECTATIONS]
        pair_names = {
            "BCC Jashore DR Data Center Rebuild and Expansion": (
                "BCC Jashore Disaster Recovery Data Center"
            ),
            "ICATEC Four-Storey Technology Center Build": (
                "ICATEC Ica Digital Transformation and Data Processing Center"
            ),
            "Pozitrons Phase 1 Current Build": "LVRTC Pozitrons Kurzeme Data Center",
            "Akashi Astana Phase 1 Current Build": "Akashi Astana Data Center Campus",
        }
        projects = {row["entity"]["name"]: row for row in added if row["entity"]["kind"] == "project"}
        campuses = {row["entity"]["name"]: row for row in added if row["entity"]["kind"] == "campus"}
        self.assertEqual(set(projects), set(pair_names))
        self.assertEqual(set(campuses), set(pair_names.values()))
        for project_name, campus_name in pair_names.items():
            project = projects[project_name]
            campus = campuses[campus_name]
            self.assertEqual(project["entity"]["target_entity_id"], campus["entity"]["id"])
            self.assertEqual(
                project["location"]["center_wgs84"], campus["location"]["center_wgs84"]
            )
        for row in successor_rows:
            properties = atlas_by_id[row["entity"]["id"]]
            self.assertEqual(
                row["location"]["center_wgs84"]["method"],
                "properties.latitude_longitude",
            )
            self.assertEqual(
                row["priority"]["lifecycle_status"], properties.get("status") or "unknown"
            )
            self.assertFalse(
                {"capacity_estimates", "operating_model", "workloads"}
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

    def test_future_private_publication_freezes_and_renames_after_target(self) -> None:
        failure = AssertionError("v83 queue publication attempted network access")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "queues"
            parent.mkdir()
            output = parent / "v83"
            lock = root / ".v83.lock"
            now = datetime.now(UTC)
            target = (now + timedelta(seconds=2)).replace(microsecond=0)
            if target <= now:
                target += timedelta(seconds=1)
            generated_at = target.isoformat().replace("+00:00", "Z")
            sleep_observations: list[bool] = []

            def sleeper(seconds: float) -> None:
                sleep_observations.append(output.exists() or output.is_symlink())
                time.sleep(seconds)

            with patch.object(socket, "socket", side_effect=failure), patch.object(
                socket, "create_connection", side_effect=failure
            ), patch.object(socket, "getaddrinfo", side_effect=failure):
                manifest = subject._publish_to(
                    output,
                    lock,
                    generated_at=generated_at,
                    clock=time.time,
                    sleeper=sleeper,
                )
            self.assertTrue(sleep_observations)
            self.assertFalse(any(sleep_observations))
            self.assertEqual(manifest["counts"]["queue_jobs"], 200)
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
                generated_at="2026-07-21T18:00:00Z",
                config=subject.CONFIG,
            )
            _freeze(queue)
            subject.validate_satellite_queue_v83(queue, require_final_root_ctime=False)
            queue.chmod(0o755)
            target = queue / QUEUE_FILENAME
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b"{}\n")
            target.chmod(0o444)
            queue.chmod(0o555)
            with self.assertRaisesRegex(
                subject.SatelliteQueueV83Error, "byte count|SHA-256"
            ):
                subject.validate_satellite_queue_v83(
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
            with self.assertRaisesRegex(subject.SatelliteQueueV83Error, "occupied"):
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
            with self.assertRaisesRegex(subject.SatelliteQueueV83Error, "occupied"):
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
