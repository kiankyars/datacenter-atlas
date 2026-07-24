from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
from typing import Any, Iterator
import unittest
from unittest.mock import patch
import urllib.request

import rasterio

try:
    from datacenter_atlas.datacenter_atlas import (
        satellite_change_preparation_v2 as v2,
    )
except ModuleNotFoundError:
    from datacenter_atlas import satellite_change_preparation_v2 as v2


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / v2.DEFINITION_PATH
RELEASE = ROOT / v2.OUTPUT_PATH
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
CATALOG = ROOT / "satellite_review_runs/2026-07-21-open-seed-v83-active-002"

# Filled from the frozen publication; these are deliberately not inferred from
# the manifest under test.
DEFINITION_SHA256 = "3074d54f9082c539d70db7313e6534a13794dc2d52ead99a131f1215eed21f53"
MANIFEST_SHA256 = "9d7df8ad8393556b172b5fda49174750e0d9ce17d6c560c692003af5c0e33430"
TREE_SHA256 = "929bd1b79beb2226961ebf652610159a56058c4aa135ee2203cb9eef4e15a227"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        128,
        "b781266a8d13d79f2530fe7085d9f651b9f4e55afae1deb43c64ae998e6e459e",
    ),
    "README.md": (
        1_029,
        "f5b8cfb24882ab44ddaa5734d9217efa6c5e8f60bbfb358c02594462d5af8481",
    ),
    "aoi-relationships.jsonl": (
        33_924,
        "8af36d043cdeee02c9665c32af6a4f0eb9bbc107c5bec0732c453df4c553a7c1",
    ),
    "manifest.json": (
        8_214,
        "9d7df8ad8393556b172b5fda49174750e0d9ce17d6c560c692003af5c0e33430",
    ),
    "manifest.sha256": (
        80,
        "ff9ab0d02ff37d747862bf4564e2a1cf535dd442168887df3a003648ce82aad6",
    ),
    "multi-tile-blocked.jsonl": (
        91_788,
        "73d8be3f06a1f4cb5ea45aa36d509eaae5945b9f43a26f4e3e0494d6cc0535b2",
    ),
    "multi-tile-ready.jsonl": (
        117_897,
        "167bf7a314e6d93f9674d4d7dbc8ae3941d4b09f52a773ed2cdf51446158f4f2",
    ),
    "single-tile-ready.jsonl": (
        1_189_889,
        "ca805c55b9030416c0660da06fa370e397afd9a0dc709d5dd56b3f220eceec56",
    ),
    "source-inventory.json": (
        99_202,
        "bd0eabb776161a739d4fb8388cb22ef621daf4420d3f1a77e5e9ee6706ef0cec",
    ),
    "summary.json": (
        1_757,
        "4f089b35b2aac1a99e007dde0ecfb7a703d82e7d32d076381603befc30d28c75",
    ),
    "terminal-no-scene.jsonl": (
        7_639,
        "cbe996745dc07b97510fb49810c458fd6dc342cf70086932dee58f562488e36f",
    ),
}

EXPECTED_SUMMARY = {
    "active_jobs": 104,
    "distinct_aois": 100,
    "jobs_in_shared_aois": 8,
    "multi_tile_blocked": 7,
    "multi_tile_blocked_net_new_v83": 6,
    "multi_tile_blocked_retained": 1,
    "multi_tile_ready": 6,
    "partition_inventory_sha256": (
        "54f219388b7f80abb17cf0c53c4a5ca06b604333fde4234aa19a5cab33a5d74f"
    ),
    "review_coverage": {
        "active_jobs": 104,
        "context_only_not_preparation_input": True,
        "reviewed_jobs": 27,
        "reviewed_queue_ids_sha256": (
            "c55aa3aa3b40b5e882b414b26a0a47dec3f297866d48248a08a6b8dc72e61c88"
        ),
        "unreviewed_jobs": 77,
        "unreviewed_no_scene_jobs": 3,
    },
    "shared_aoi_groups": 4,
    "single_tile_ready": 88,
    "terminal_no_scene": 3,
}

BLOCKED = {
    8: ("satq-415d80a31d8798a2e2c06d17", "multi_tile_missing", "multi_tile_missing", True),
    17: ("satq-e6e1ceab9c56fe15b25e03f4", "multi_tile_complete", "multi_tile_missing", True),
    21: ("satq-d0a872a7aee9f9f54a8631ef", "multi_tile_missing", "multi_tile_missing", False),
    31: ("satq-3288e71f7387eee72714a756", "multi_tile_missing", "multi_tile_missing", True),
    62: ("satq-1478784c38a09b1d3c588c3b", "multi_tile_missing", "multi_tile_missing", True),
    65: ("satq-66d1dc2e7f8654ac10d7980c", "multi_tile_complete", "multi_tile_missing", True),
    78: ("satq-6936ad65587f752edbc1ba41", "multi_tile_missing", "multi_tile_complete", True),
}

MULTI_READY = {
    "satq-54c6402eb93d14f1ea754e66",
    "satq-cef871428da247c3ecfadec6",
    "satq-96fca962064e09f0dbafa93b",
    "satq-78500568b1f6227789ae36f4",
    "satq-fb6b6f815dad079c059cf412",
    "satq-0ffe3647dc32ee25ef77eab7",
}

NO_SCENE = {
    "satq-ed5c45c9ee1bfba25a2f10c3",
    "satq-3149584b9d40a3049b84371e",
    "satq-3c6f789981688519124eeb22",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(filename: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (RELEASE / filename).read_text(encoding="utf-8").splitlines()
    ]


def _tree_inventory(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"tree contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported tree entry: {relative}")
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


@contextmanager
def _future_definition(seconds: float = 2.0) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=".v2-test-", dir=ROOT) as raw:
        temporary = Path(raw)
        generated_at = (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).isoformat().replace("+00:00", "Z")
        value = v2.build_satellite_change_preparation_definition_v2(generated_at)
        path = temporary / "definition.json"
        path.write_bytes(_canonical_json(value))
        yield path


@contextmanager
def _deny_external_io() -> Iterator[None]:
    failure = AssertionError("metadata preparation attempted external I/O")
    with ExitStack() as stack:
        stack.enter_context(patch.object(rasterio, "open", side_effect=failure))
        stack.enter_context(patch.object(urllib.request, "urlopen", side_effect=failure))
        stack.enter_context(patch.object(subprocess, "Popen", side_effect=failure))
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        yield


def _force_remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not child.is_symlink():
            child.chmod(0o700 if child.is_dir() else 0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


class SatelliteChangePreparationV2Tests(unittest.TestCase):
    def test_definition_release_and_source_pins_are_frozen(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(_sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_tree_inventory(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, v2.RELEASE_FILES)
        for path in RELEASE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(
            {
                path.name: (path.stat().st_size, _sha256(path))
                for path in RELEASE.iterdir()
            },
            ARTIFACTS,
        )

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["generated_at"], "2026-07-21T20:47:00Z")
        self.assertEqual(
            definition["sources"]["catalog_batch"]["batch_manifest"],
            {
                "bytes": 120_448,
                "mode": "0444",
                "path": (
                    "satellite_review_runs/2026-07-21-open-seed-v83-active-002/"
                    "batch-manifest.json"
                ),
                "sha256": (
                    "ec43aacf55bab8d8169e5cad4855b5e33614c2e65de0a5b82bf70c2c585adae8"
                ),
            },
        )
        self.assertEqual(
            definition["sources"]["catalog_batch"]["closed_tree"][
                "inventory_sha256"
            ],
            "7a26caebb28656c551837c1431bfd2a5a228889572d5df006a149badc8c91152",
        )
        self.assertEqual(
            definition["sources"]["catalog_lock"], v2.EXPECTED_CATALOG_LOCK
        )
        self.assertEqual(v2.CATALOG_CONFIG.minimum_interval_seconds, 1.1)

    def test_exact_partition_review_boundary_and_runner_rows(self) -> None:
        terminal = _rows("terminal-no-scene.jsonl")
        single = _rows("single-tile-ready.jsonl")
        multi = _rows("multi-tile-ready.jsonl")
        blocked = _rows("multi-tile-blocked.jsonl")
        rows = sorted([*terminal, *single, *multi, *blocked], key=lambda row: row["queue_position"])
        self.assertEqual(len(rows), 104)
        self.assertEqual([row["queue_position"] for row in rows], list(range(1, 105)))
        self.assertEqual(
            (len(single), len(multi), len(blocked), len(terminal)), (88, 6, 7, 3)
        )
        self.assertEqual(
            json.loads((RELEASE / "manifest.json").read_text())["summary"],
            EXPECTED_SUMMARY,
        )
        self.assertEqual(
            json.loads((RELEASE / "summary.json").read_text())["review_coverage"],
            EXPECTED_SUMMARY["review_coverage"],
        )
        reviewed = [
            row
            for row in rows
            if row["analyst_review_coverage"]["status"] == "reviewed"
        ]
        self.assertEqual(len(reviewed), 27)
        self.assertEqual(len(rows) - len(reviewed), 77)
        self.assertTrue(
            all(
                row["analyst_review_coverage"]["status"] == "unreviewed"
                for row in terminal
            )
        )
        self.assertEqual({row["queue_id"] for row in terminal}, NO_SCENE)
        self.assertEqual({row["queue_id"] for row in multi}, MULTI_READY)

        for row in rows:
            self.assertEqual(row["schema_version"], 2)
            self.assertEqual(row["claim_constraints"], v2.CLAIM_CONSTRAINTS)
            self.assertEqual(row["network_requests"], 0)
            self.assertFalse(row["raster_analysis_executed"])
        for row in [*single, *multi]:
            contract = row["future_runner_contract"]
            self.assertTrue(contract["execution_arguments_complete"])
            self.assertEqual(contract["output_directory_placeholder"], "{job_output_dir}")
            self.assertIn("{job_output_dir}", row["execution"]["arguments"])
        for row in [*blocked, *terminal]:
            self.assertIsNone(row["execution"])
            self.assertFalse(
                row["future_runner_contract"]["execution_arguments_complete"]
            )

        actual_blocked = {row["queue_position"]: row for row in blocked}
        self.assertEqual(set(actual_blocked), set(BLOCKED))
        for position, (queue_id, baseline, current, net_new) in BLOCKED.items():
            row = actual_blocked[position]
            self.assertEqual(row["queue_id"], queue_id)
            self.assertEqual(row["epochs"]["baseline"]["classification"], baseline)
            self.assertEqual(row["epochs"]["current"]["classification"], current)
            self.assertEqual(row["net_new_v83_multi_tile_blocker"], net_new)
            self.assertEqual(
                row["blocker_generation"],
                "net_new_v83" if net_new else "retained_predecessor",
            )

    def test_two_offline_replays_never_open_imagery(self) -> None:
        with _deny_external_io():
            first_payloads, first_manifest = v2._payloads(DEFINITION)
            second_payloads, second_manifest = v2._payloads(DEFINITION)
        self.assertEqual(first_payloads, second_payloads)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["summary"], EXPECTED_SUMMARY)
        self.assertEqual(
            first_manifest["scope"],
            {
                "aoi_deduplication_applied": False,
                "entity_jobs_retained": 104,
                "imagery_downloads": 0,
                "imagery_opens": 0,
                "network_requests": 0,
                "preparation_only": True,
                "raster_analyses": 0,
            },
        )

    def test_existing_and_late_collisions_preserve_foreign_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix=".v2-collision-", dir=ROOT) as raw:
            temporary = Path(raw)
            output = temporary / "release"
            output.mkdir()
            sentinel = output / "sentinel"
            sentinel.write_bytes(b"preserve")
            with self.assertRaisesRegex(
                v2.SatelliteChangePreparationV2Error, "refusing to replace"
            ):
                v2.write_satellite_change_preparation_v2(
                    output, definition_path=DEFINITION
                )
            self.assertEqual(sentinel.read_bytes(), b"preserve")

        with _future_definition() as definition:
            temporary = definition.parent
            output = temporary / "release"

            def collide(_stage: Path, destination: Path) -> None:
                destination.mkdir()
                (destination / "sentinel").write_bytes(b"preserve")
                raise v2.SatelliteChangePreparationV2Error("injected late collision")

            with _deny_external_io(), patch.object(
                v2, "_promote_noreplace", side_effect=collide
            ):
                with self.assertRaisesRegex(
                    v2.SatelliteChangePreparationV2Error,
                    "injected late collision",
                ):
                    v2.write_satellite_change_preparation_v2(
                        output, definition_path=definition
                    )
            self.assertEqual((output / "sentinel").read_bytes(), b"preserve")
            self.assertEqual(list(temporary.glob(".release.staging-*")), [])

    def test_postpromotion_failure_rolls_back_only_owned_output(self) -> None:
        with _future_definition() as definition:
            temporary = definition.parent
            output = temporary / "release"
            real_validate = v2.validate_satellite_change_preparation_v2
            calls = 0

            def fail_after_promotion(*args: Any, **kwargs: Any) -> dict[str, Any]:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise v2.SatelliteChangePreparationV2Error(
                        "injected post-promotion failure"
                    )
                return real_validate(*args, **kwargs)

            with _deny_external_io(), patch.object(
                v2,
                "validate_satellite_change_preparation_v2",
                side_effect=fail_after_promotion,
            ):
                with self.assertRaisesRegex(
                    v2.SatelliteChangePreparationV2Error,
                    "injected post-promotion failure",
                ):
                    v2.write_satellite_change_preparation_v2(
                        output, definition_path=definition
                    )
            self.assertEqual(calls, 2)
            self.assertFalse(output.exists())
            self.assertEqual(list(temporary.glob(".release.staging-*")), [])
            self.assertEqual(list(temporary.glob(".release.rollback-*")), [])

    def test_validator_and_cli_reject_mutation(self) -> None:
        manifest = v2.validate_satellite_change_preparation_v2(
            RELEASE, definition_path=DEFINITION
        )
        self.assertEqual(manifest["summary"], EXPECTED_SUMMARY)
        with tempfile.TemporaryDirectory(prefix=".v2-mutation-", dir=ROOT) as raw:
            copy = Path(raw) / "release"
            shutil.copytree(RELEASE, copy)
            for path in copy.iterdir():
                path.chmod(0o444)
            copy.chmod(0o555)
            copy.chmod(0o755)
            target = copy / "summary.json"
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b" ")
            target.chmod(0o444)
            copy.chmod(0o555)
            with self.assertRaisesRegex(
                v2.SatelliteChangePreparationV2Error,
                "artifact differs: summary.json",
            ):
                v2.validate_satellite_change_preparation_v2(
                    copy, definition_path=DEFINITION
                )
            _force_remove(copy)


if __name__ == "__main__":
    unittest.main()
