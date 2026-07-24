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
    QueueValidationError,
    validate_queue_bundle,
    write_queue_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v57.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v57"
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v57"
BASE_QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v56"

GENERATED_AT = "2026-07-21T00:00:00Z"
CONFIG = QueueConfig(
    baseline_target="2024-07-15",
    current_target="2026-07-15",
    provider="earth-search-v1",
    query_window_days=45,
    max_cloud_cover=20,
    catalog_limit=100,
    aoi_half_side_km=2,
    minimum_component_area_m2=5_000,
)
PINS = {
    DEFINITION: (
        68_443,
        "421a8992616cea1e0b9779d47ed1f7052465cbf59c22c3d00b8a79d9463c1bc8",
    ),
    RELEASE / "atlas.geojson": (
        2_375_109,
        "23921f0f8373925321d7d203402d2035a6768c82838d3fa1f8778ebb19111cd4",
    ),
    RELEASE / MANIFEST_FILENAME: (
        9_403,
        "37f33308466d3707e2bf9f5225bd3c3546dcb2539e7f537286dd8237728d6403",
    ),
    QUEUE / MANIFEST_FILENAME: (
        13_586,
        "578b4778e552b86c0c07c419a6dd72572d48aaef324ce42154e3e8621401a48c",
    ),
    QUEUE / MANIFEST_HASH_FILENAME: (
        80,
        "e2323631702ea26ade7001ec4c906abdb1c639ddea99d0ec299c92e3e0c6803d",
    ),
    QUEUE / QUEUE_FILENAME: (
        449_902,
        "a91f57f706e8c70a1b768e0506bfac7b2ac5c200f9fe0bbf8ee8a9a826bada99",
    ),
}
RELEASE_TREE_SHA256 = (
    "2651d54295954e4a791e0dbc44b9e2f6947f6b519473468bcec5277299f4c8fe"
)
QUEUE_TREE_SHA256 = (
    "ad8f9478172097aa29540fcb1e4507670280d100c745173633ea83cc74119ec8"
)

ADDED = {
    "curated:nextdc-b2-brisbane": (
        129,
        "satq-866abbb2fcbb620c89301998",
        "campus",
        "unknown",
        "unknown",
        (-27.4539022, 153.0332005),
    ),
    "curated:nextdc-b2-brisbane:incremental-in-progress-fit-out": (
        7,
        "satq-a2f4c12795598f107ed19e08",
        "project",
        "active_construction",
        "mep_electrical",
        (-27.4539022, 153.0332005),
    ),
    "curated:nextdc-kl1-kuala-lumpur": (
        95,
        "satq-9230c4eb89e03099f7c44a26",
        "campus",
        "unknown",
        "unknown",
        (3.0965132, 101.6241451),
    ),
    "curated:nextdc-kl1-kuala-lumpur:incremental-in-progress-fit-out": (
        10,
        "satq-ed5c45c9ee1bfba25a2f10c3",
        "project",
        "active_construction",
        "mep_electrical",
        (3.0965132, 101.6241451),
    ),
    "curated:nextdc-m2-melbourne": (
        112,
        "satq-78c937fde639c55bcb9b273b",
        "campus",
        "unknown",
        "unknown",
        (-37.7080294, 144.8756939),
    ),
    "curated:nextdc-m2-melbourne:incremental-in-progress-fit-out": (
        11,
        "satq-18a5f2d1941c6693dda824dc",
        "project",
        "active_construction",
        "mep_electrical",
        (-37.7080294, 144.8756939),
    ),
    "curated:nextdc-p1-perth": (
        105,
        "satq-de989da93156cf983ce61d82",
        "campus",
        "unknown",
        "unknown",
        (-31.8644016, 115.895935),
    ),
    "curated:nextdc-p1-perth:incremental-in-progress-fit-out": (
        9,
        "satq-abb68f0ebf367d427142523f",
        "project",
        "active_construction",
        "mep_electrical",
        (-31.8644016, 115.895935),
    ),
    "curated:nextdc-p2-perth": (
        134,
        "satq-cf5d9fbd633bd09e3c602936",
        "campus",
        "unknown",
        "unknown",
        (-31.9496948, 115.8685493),
    ),
    "curated:nextdc-p2-perth:incremental-in-progress-fit-out": (
        8,
        "satq-ee9947cfd17930319d399717",
        "project",
        "active_construction",
        "mep_electrical",
        (-31.9496948, 115.8685493),
    ),
}

UNLOCATED_V57_ADDITIONS = {
    "curated:aligned-quantum-frederick-campus",
    "curated:aligned-quantum-frederick-campus:iad06",
    "curated:google-bermuda-hundred-chesterfield-campus",
    "curated:google-bermuda-hundred-chesterfield-campus:current-development",
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
            raise AssertionError(f"tree contains symlink: {relative}")
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


def country_counts(manifest: dict) -> dict[str, dict]:
    return {
        row["country_iso_a2"]: row["by_priority_tier"]
        for row in manifest["counts"]["queued_entities_by_country_priority_tier"]
    }


def copy_release(root: Path) -> Path:
    release = root / "release"
    release.mkdir()
    for filename in ("atlas.geojson", MANIFEST_FILENAME):
        (release / filename).write_bytes((RELEASE / filename).read_bytes())
    return release


class OpenSeedV57SatelliteQueueTests(unittest.TestCase):
    def test_exact_lineage_counts_configuration_and_frozen_tree(self) -> None:
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
        self.assertEqual(manifest["configuration"], CONFIG.as_dict())
        self.assertEqual(manifest["source"]["atlas_recorded_at"], "2026-07-20T23:56:00Z")
        self.assertEqual(
            manifest["source"]["release_manifest"]["sha256"],
            PINS[RELEASE / MANIFEST_FILENAME][1],
        )
        self.assertEqual(manifest["source"]["sha256"], PINS[RELEASE / "atlas.geojson"][1])
        self.assertEqual(
            manifest["counts"],
            {
                **manifest["counts"],
                "features_examined": 671,
                "eligible_features_by_kind": {"campus": 361, "project": 310},
                "entities_queued": 164,
                "queue_jobs": 164,
                "skipped_missing_coordinates": 507,
                "queued_entities_by_priority_tier": {
                    "active_construction": 87,
                    "operational": 29,
                    "proposed_pipeline": 5,
                    "unknown": 43,
                },
            },
        )
        self.assertEqual(tree_digest(RELEASE), RELEASE_TREE_SHA256)
        self.assertEqual(tree_digest(QUEUE), QUEUE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(QUEUE.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in QUEUE.iterdir()},
            {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, QUEUE_FILENAME},
        )
        for path in QUEUE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_v56_delta_is_exactly_ten_nextdc_jobs_with_stable_shared_rows(self) -> None:
        before = records(BASE_QUEUE)
        after = records(QUEUE)
        self.assertEqual((len(before), len(after)), (154, 164))
        self.assertEqual(set(after) - set(before), set(ADDED))
        self.assertFalse(set(before) - set(after))
        self.assertTrue(UNLOCATED_V57_ADDITIONS.isdisjoint(after))

        for stable_key, expected in ADDED.items():
            position, queue_id, kind, tier, lifecycle, center = expected
            row = after[stable_key]
            self.assertEqual(row["queue_position"], position)
            self.assertEqual(row["queue_id"], queue_id)
            self.assertEqual(row["entity"]["kind"], kind)
            self.assertEqual(row["priority"]["tier"], tier)
            self.assertEqual(row["priority"]["lifecycle_status"], lifecycle)
            self.assertEqual(
                (
                    row["location"]["center_wgs84"]["latitude"],
                    row["location"]["center_wgs84"]["longitude"],
                ),
                center,
            )

        for stable_key in before.keys() & after.keys():
            old = deepcopy(before[stable_key])
            new = deepcopy(after[stable_key])
            old.pop("queue_position")
            new.pop("queue_position")
            self.assertEqual(new, old, stable_key)

        for prefix in (
            "curated:nextdc-b2-brisbane",
            "curated:nextdc-kl1-kuala-lumpur",
            "curated:nextdc-m2-melbourne",
            "curated:nextdc-p1-perth",
            "curated:nextdc-p2-perth",
        ):
            campus = after[prefix]
            project = after[f"{prefix}:incremental-in-progress-fit-out"]
            self.assertEqual(campus["location"], project["location"])
            self.assertEqual(campus["priority"]["tier"], "unknown")
            self.assertEqual(project["priority"]["tier"], "active_construction")

    def test_country_delta_is_limited_to_australia_and_malaysia(self) -> None:
        before = country_counts(validate_queue_bundle(BASE_QUEUE))
        after = country_counts(validate_queue_bundle(QUEUE))
        self.assertEqual(
            after["AU"], {"active_construction": 6, "unknown": 5}
        )
        self.assertEqual(
            after["MY"], {"active_construction": 2, "unknown": 1}
        )
        for country in set(before) | set(after):
            if country not in {"AU", "MY"}:
                self.assertEqual(after[country], before[country], country)

    def test_two_socket_blocked_offline_reconstructions_are_byte_exact(self) -> None:
        failure = AssertionError("v57 queue reconstruction attempted network access")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = copy_release(root)
            outputs = (root / "queue-one", root / "queue-two")
            with patch.object(socket, "socket", side_effect=failure), patch.object(
                socket, "create_connection", side_effect=failure
            ), patch.object(socket, "getaddrinfo", side_effect=failure):
                for output in outputs:
                    write_queue_bundle(
                        source / "atlas.geojson",
                        output,
                        generated_at=GENERATED_AT,
                        config=CONFIG,
                    )
                    validate_queue_bundle(output)

            for filename in (MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, QUEUE_FILENAME):
                expected = (QUEUE / filename).read_bytes()
                self.assertEqual((outputs[0] / filename).read_bytes(), expected)
                self.assertEqual((outputs[1] / filename).read_bytes(), expected)
            for output in outputs:
                for path in output.iterdir():
                    path.chmod(0o444)
                output.chmod(0o555)
                self.assertEqual(tree_digest(output), QUEUE_TREE_SHA256)

    def test_no_overwrite_symlinks_tamper_and_lineage_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = copy_release(root)
            output = root / "queue"
            write_queue_bundle(
                source / "atlas.geojson",
                output,
                generated_at=GENERATED_AT,
                config=CONFIG,
            )
            before = {
                path.name: (
                    path.read_bytes(),
                    path.stat().st_ino,
                    path.stat().st_mtime_ns,
                )
                for path in output.iterdir()
            }
            write_queue_bundle(
                source / "atlas.geojson",
                output,
                generated_at=GENERATED_AT,
                config=CONFIG,
            )
            after = {
                path.name: (
                    path.read_bytes(),
                    path.stat().st_ino,
                    path.stat().st_mtime_ns,
                )
                for path in output.iterdir()
            }
            self.assertEqual(after, before)
            with self.assertRaisesRegex(QueueValidationError, "not byte-identical"):
                write_queue_bundle(
                    source / "atlas.geojson",
                    output,
                    generated_at="2026-07-21T00:01:00Z",
                    config=CONFIG,
                )
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                {name: state[0] for name, state in before.items()},
            )

            with (output / QUEUE_FILENAME).open("ab") as destination:
                destination.write(b"tampered")
            tampered = (output / QUEUE_FILENAME).read_bytes()
            with self.assertRaises(QueueValidationError):
                write_queue_bundle(
                    source / "atlas.geojson",
                    output,
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )
            self.assertEqual((output / QUEUE_FILENAME).read_bytes(), tampered)

            source_link = root / "atlas-link.geojson"
            source_link.symlink_to(source / "atlas.geojson")
            with self.assertRaisesRegex(QueueValidationError, "not a regular file"):
                write_queue_bundle(
                    source_link,
                    root / "source-link-output",
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )
            output_link = root / "queue-link"
            output_link.symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(QueueValidationError, "may not be a symlink"):
                write_queue_bundle(
                    source / "atlas.geojson",
                    output_link,
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )

            release_manifest = json.loads((source / MANIFEST_FILENAME).read_text())
            release_manifest["files"]["atlas.geojson"]["bytes"] += 1
            (source / MANIFEST_FILENAME).write_text(json.dumps(release_manifest))
            with self.assertRaisesRegex(QueueValidationError, "does not match exact"):
                write_queue_bundle(
                    source / "atlas.geojson",
                    root / "lineage-drift-output",
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )
            self.assertFalse((root / "lineage-drift-output").exists())


if __name__ == "__main__":
    unittest.main()
