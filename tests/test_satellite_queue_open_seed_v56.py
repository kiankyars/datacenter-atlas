from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    QueueConfig,
    validate_queue_bundle,
    write_queue_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v56"
BASE_QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v55"

GENERATED_AT = "2026-07-20T22:55:00Z"
PINS = {
    QUEUE / MANIFEST_FILENAME: (
        13_472,
        "d02dca01f2f86915d01355ac54fd10c43796576bd2a484d58e3f69f4046834e2",
    ),
    QUEUE / MANIFEST_HASH_FILENAME: (
        80,
        "f2065720d4d54d1c6d68dfbdc43f834149cfd94d5cbf4efe4371009d948225a2",
    ),
    QUEUE / QUEUE_FILENAME: (
        422_650,
        "e065c7024a4ba88fa74f87d846b2272a0a0ef006c64eca69acfb7f6e156101b7",
    ),
    BASE_QUEUE / MANIFEST_FILENAME: (
        12_885,
        "22b94402724aa349cb908d438b9c05d523519afc3fe8ce262b8a616b541ff0a4",
    ),
    BASE_QUEUE / MANIFEST_HASH_FILENAME: (
        80,
        "b863754352df836bc029769f4f943f21d9855852768f8b20df283b890f763af6",
    ),
    BASE_QUEUE / QUEUE_FILENAME: (
        411_746,
        "38b5125a7dc3b4c1692d254907cbd716e953492832b6df1917d391c0a6ec876a",
    ),
    RELEASE / "atlas.geojson": (
        2_362_225,
        "32e1c5247c7de6e4e7f9af9981957023116f64e33c8bd6a4f165ad98be98b0d5",
    ),
    RELEASE / "manifest.json": (
        9_274,
        "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd",
    ),
}
TREE_SHA256 = "11558db05baf9df827429f95270020956239b7c7d93d1ada46d3aad13a614d70"

ADDED = {
    "curated:paix-dkr1-dakar-data-center-campus": (
        98,
        "satq-c815082e9371bd66251e0913",
        "unknown",
        "unknown",
    ),
    "curated:paix-dkr1-dakar-data-center-campus:current-development": (
        83,
        "satq-c2e175940087e69a76afb545",
        "proposed_pipeline",
        "site_control",
    ),
    "curated:pentapoint-emd-bkk01-sathorn-campus": (
        105,
        "satq-6ad49fcfc7886e5bbf5dfab5",
        "unknown",
        "unknown",
    ),
    "curated:pentapoint-emd-bkk01-sathorn-campus:current-development": (
        4,
        "satq-b6f121dc644b91ad78eb479a",
        "active_construction",
        "under_construction",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(directory: Path) -> dict[str, dict]:
    rows = [
        json.loads(line)
        for line in (directory / QUEUE_FILENAME).read_text().splitlines()
    ]
    return {row["entity"]["stable_key"]: row for row in rows}


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"queue contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        else:
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
    return digest.hexdigest()


def contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(contains_key(child, key) for child in value)
    return False


class OpenSeedV56SatelliteQueueTests(unittest.TestCase):
    def test_exact_lineage_pins_counts_and_frozen_modes(self) -> None:
        manifest = validate_queue_bundle(QUEUE)
        for path, (expected_bytes, expected_sha256) in PINS.items():
            self.assertEqual(path.stat().st_size, expected_bytes, path)
            self.assertEqual(sha256(path), expected_sha256, path)

        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(
                manifest["source"]["atlas_recorded_at"].replace("Z", "+00:00")
            ),
        )
        self.assertEqual(manifest["source"]["atlas_recorded_at"], "2026-07-20T22:34:00Z")
        self.assertEqual(
            manifest["source"]["release_manifest"]["sha256"],
            PINS[RELEASE / "manifest.json"][1],
        )
        self.assertEqual(manifest["counts"]["features_examined"], 667)
        self.assertEqual(
            manifest["counts"]["eligible_features_by_kind"],
            {"campus": 359, "project": 308},
        )
        self.assertEqual(manifest["counts"]["entities_queued"], 154)
        self.assertEqual(manifest["counts"]["skipped_missing_coordinates"], 513)
        self.assertEqual(
            manifest["counts"]["queued_entities_by_priority_tier"],
            {
                "active_construction": 82,
                "operational": 29,
                "proposed_pipeline": 5,
                "unknown": 38,
            },
        )

        self.assertEqual(stat.S_IMODE(QUEUE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in QUEUE.iterdir()}, {
            MANIFEST_FILENAME,
            MANIFEST_HASH_FILENAME,
            QUEUE_FILENAME,
        })
        for path in QUEUE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(QUEUE), TREE_SHA256)

    def test_v55_delta_is_exactly_four_additive_coordinate_jobs(self) -> None:
        before = records(BASE_QUEUE)
        after = records(QUEUE)
        self.assertEqual((len(before), len(after)), (150, 154))
        self.assertEqual(set(after) - set(before), set(ADDED))
        self.assertFalse(set(before) - set(after))

        for stable_key, (position, queue_id, tier, lifecycle) in ADDED.items():
            row = after[stable_key]
            self.assertEqual(row["queue_position"], position)
            self.assertEqual(row["queue_id"], queue_id)
            self.assertEqual(row["priority"]["tier"], tier)
            self.assertEqual(row["priority"]["lifecycle_status"], lifecycle)

        for stable_key in before.keys() & after.keys():
            old = deepcopy(before[stable_key])
            new = deepcopy(after[stable_key])
            old.pop("queue_position")
            new.pop("queue_position")
            self.assertEqual(new, old, stable_key)

    def test_imagery_guardrails_and_no_power_or_workload_payloads(self) -> None:
        expected_constraints = {
            "imagery_identity_claim": False,
            "imagery_lifecycle_claim": False,
            "imagery_operating_status_claim": False,
            "imagery_power_claim": False,
            "queue_basis": "existing_atlas_entity_and_location",
            "review_required": True,
        }
        rows = list(records(QUEUE).values())
        self.assertEqual(
            sorted(row["queue_position"] for row in rows), list(range(1, 155))
        )
        self.assertEqual(len({row["queue_id"] for row in rows}), 154)
        for row in rows:
            self.assertEqual(row["review_constraints"], expected_constraints)
            self.assertFalse(contains_key(row, "capacity_estimates"))
            self.assertFalse(contains_key(row, "workload_tags"))
        manifest = json.loads((QUEUE / MANIFEST_FILENAME).read_text())
        self.assertFalse(manifest["scope"]["network_requests_performed"])
        self.assertFalse(manifest["scope"]["automatic_entity_merge"])
        self.assertFalse(manifest["scope"]["imagery_identity_inference"])
        self.assertFalse(manifest["scope"]["imagery_lifecycle_inference"])
        self.assertFalse(manifest["scope"]["imagery_power_inference"])

    def test_fresh_offline_reproduction_is_byte_exact(self) -> None:
        config = QueueConfig(
            baseline_target="2024-07-15",
            current_target="2026-07-15",
        )
        failure = AssertionError("v56 queue reproduction attempted network access")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "release"
            source.mkdir()
            for name in ("atlas.geojson", "manifest.json"):
                (source / name).write_bytes((RELEASE / name).read_bytes())
            output = root / "queue"
            with patch.object(socket, "socket", side_effect=failure), patch.object(
                socket, "create_connection", side_effect=failure
            ), patch.object(socket, "getaddrinfo", side_effect=failure):
                write_queue_bundle(
                    source / "atlas.geojson",
                    output,
                    generated_at=GENERATED_AT,
                    config=config,
                )
                validate_queue_bundle(output)
            for name in (MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, QUEUE_FILENAME):
                self.assertEqual((output / name).read_bytes(), (QUEUE / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
