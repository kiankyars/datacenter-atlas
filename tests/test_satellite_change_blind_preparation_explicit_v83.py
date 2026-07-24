from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import datacenter_atlas.datacenter_atlas.satellite_change_blind_preparation_explicit_v83 as implementation
from datacenter_atlas.satellite_change_blind_preparation_explicit_v83 import (
    ATTRIBUTION_FILENAME,
    BLIND_ID_PREFIX,
    DEFINITION_FILENAME,
    GUARDRAILS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    PREPARATION_ID,
    README_FILENAME,
    SOURCE_JOB_COUNT,
    SOURCE_SELECTION_SHA256,
    UNITS_FILENAME,
    VISUAL_FILENAMES,
    build_blind_preparation,
    validate_blind_preparation,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "satellite_change_preparation" / PREPARATION_ID
SOURCE_RUN = (
    ROOT
    / "satellite_change_runs"
    / "2026-07-21-open-seed-v83-active-unreviewed-remaining-001"
)
SOURCE_PREPARATION = (
    ROOT
    / "satellite_change_preparation"
    / "2026-07-21-open-seed-v83-active-v2"
)
GENERATED_AT = "2026-07-21T23:49:09.627849Z"
MANIFEST_SHA256 = "c32618fe31eaa753cea9e75a04feac3c575deba6aa22ea84c0184840b6e57c7f"
TREE_SHA256 = "732441572720e833823a655ad3e2658535e2be3a76f94e23332afbeeb05b3e90"
LINEAGE_COMMITMENT_SHA256 = (
    "441a2d6f2acce7a5a2348991da88878463cf53f41d1316304c1a2b8df08e9cc0"
)
EXPECTED_ROOT_MEMBERS = {
    ATTRIBUTION_FILENAME: (
        252,
        "f12ffacd3094b84d68c4a3734e275eab01514ee7c0fb5ba5d98c034905bc01c5",
    ),
    DEFINITION_FILENAME: (
        4_041,
        "1c09b9ba365f61241e7f86d5729fa7b347391ae96b1685d29952cb26752bd4ea",
    ),
    MANIFEST_FILENAME: (44_116, MANIFEST_SHA256),
    MANIFEST_HASH_FILENAME: (
        80,
        "cd8a7f606f81636a66835875cb684d8dd4f4defbc2eab2766dbeb79d8e94f71e",
    ),
    README_FILENAME: (
        721,
        "ec8233c4b6b0c6417ea42c62f16c07832e830632a4e81cd4f5148b909a00398a",
    ),
    UNITS_FILENAME: (
        45_200,
        "7436f689999605beea6f0d3c88dc1bfa70471d57b9de0a3c671c8dda4b2a5a29",
    ),
}
EXPECTED_SUMMARY = {
    "blind_review_units": 68,
    "coordinate_metadata_fields_exposed": 0,
    "copied_visual_artifacts": 272,
    "geojson_artifacts_copied": 0,
    "lineage_rows_exposed": 0,
    "queue_ids_exposed": 0,
    "report_artifacts_copied": 0,
    "site_identity_fields_exposed": 0,
    "status_metadata_fields_exposed": 0,
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


class ExplicitV83BlindPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition_raw = (BUNDLE / DEFINITION_FILENAME).read_bytes()
        cls.definition = json.loads(cls.definition_raw)
        cls.manifest_raw = (BUNDLE / MANIFEST_FILENAME).read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)
        cls.units = _rows(BUNDLE / UNITS_FILENAME)
        cls.source = json.loads((SOURCE_RUN / "batch-manifest.json").read_text())

    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("blind preparation attempted network access"),
        ):
            first = validate_blind_preparation(BUNDLE)
            second = validate_blind_preparation(BUNDLE)
            rebuilt = build_blind_preparation(GENERATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(first["preparation_id"], PREPARATION_ID)
        self.assertEqual(first["tree_inventory"]["inventory_sha256"], TREE_SHA256)
        self.assertEqual(
            rebuilt,
            {
                path.relative_to(BUNDLE).as_posix(): path.read_bytes()
                for path in BUNDLE.rglob("*")
                if path.is_file()
            },
        )

    def test_exact_tree_members_modes_and_publication_clock(self) -> None:
        self.assertEqual(_sha256(self.manifest_raw), MANIFEST_SHA256)
        self.assertEqual(
            (BUNDLE / MANIFEST_HASH_FILENAME).read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  {MANIFEST_FILENAME}\n",
        )
        for name, (size, digest) in EXPECTED_ROOT_MEMBERS.items():
            raw = (BUNDLE / name).read_bytes()
            self.assertEqual((len(raw), _sha256(raw)), (size, digest))
        self.assertEqual(
            implementation._tree_inventory(BUNDLE),
            {
                "directories": 70,
                "file_bytes": 97_829_252,
                "files": 278,
                "inventory_sha256": TREE_SHA256,
            },
        )
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        target = implementation._timestamp(GENERATED_AT, "generated_at")[1]
        for path in [BUNDLE, *BUNDLE.rglob("*")]:
            self.assertFalse(path.is_symlink())
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode),
                0o555 if path.is_dir() else 0o444,
            )
            self.assertLessEqual(path.stat().st_mtime, target.timestamp() + 1e-6)
            birth = getattr(path.stat(), "st_birthtime", 0.0)
            if birth:
                self.assertLessEqual(birth, target.timestamp() + 1e-6)
        self.assertGreaterEqual(BUNDLE.stat().st_ctime + 1e-6, target.timestamp())

    def test_source_set_is_exactly_the_68_unreviewed_single_tile_rows(self) -> None:
        selected_order = tuple(self.source["selection"]["selected_queue_ids"])
        selected = set(selected_order)
        unreviewed_single = {
            row["queue_id"]
            for row in _rows(SOURCE_PREPARATION / "single-tile-ready.jsonl")
            if row["analyst_review_coverage"]["status"] == "unreviewed"
        }
        blocked = {
            row["queue_id"]
            for row in _rows(SOURCE_PREPARATION / "multi-tile-blocked.jsonl")
        }
        no_scene = {
            row["queue_id"]
            for row in _rows(SOURCE_PREPARATION / "terminal-no-scene.jsonl")
        }
        older_mosaic_ready = {
            row["queue_id"]
            for row in _rows(SOURCE_PREPARATION / "multi-tile-ready.jsonl")
        }
        self.assertEqual(len(selected), SOURCE_JOB_COUNT)
        self.assertEqual(selected, unreviewed_single)
        self.assertTrue(selected.isdisjoint(blocked | no_scene | older_mosaic_ready))
        self.assertEqual(set(self.source["jobs"]), selected)
        self.assertTrue(
            all(
                job["state"] == "completed" and job["attempts"] == 1
                for job in self.source["jobs"].values()
            )
        )
        self.assertEqual(
            _sha256(implementation._canonical_json(sorted(selected))),
            SOURCE_SELECTION_SHA256,
        )
        self.assertEqual(
            tuple(queue_id for _blind_id, queue_id in implementation._blind_order(selected_order)),
            tuple(
                queue_id
                for _blind_id, queue_id in implementation._blind_order(selected_order)
            ),
        )
        self.assertNotEqual(
            tuple(queue_id for _blind_id, queue_id in implementation._blind_order(selected_order)),
            selected_order,
        )

    def test_neutral_units_expose_only_four_metadata_free_png_views(self) -> None:
        self.assertEqual(len(self.units), SOURCE_JOB_COUNT)
        self.assertEqual(
            [row["blind_id"] for row in self.units],
            [f"{BLIND_ID_PREFIX}{index:03d}" for index in range(1, 69)],
        )
        paths: set[str] = set()
        for index, row in enumerate(self.units, 1):
            self.assertEqual(
                set(row),
                {"blind_id", "inspection_order", "schema_version", "views"},
            )
            self.assertEqual(row["inspection_order"], index)
            self.assertEqual(tuple(row["views"]), tuple(sorted(VISUAL_FILENAMES)))
            for name, spec in row["views"].items():
                self.assertEqual(spec["path"], f"images/{row['blind_id']}/{name}")
                self.assertNotIn(spec["path"], paths)
                paths.add(spec["path"])
                raw = (BUNDLE / spec["path"]).read_bytes()
                self.assertEqual(
                    (len(raw), _sha256(raw)),
                    (spec["bytes"], spec["sha256"]),
                )
                chunks = implementation._png_chunks(raw, spec["path"])
                self.assertTrue(set(chunks) <= implementation.PNG_ALLOWED_CHUNKS)
        self.assertEqual(len(paths), 272)

    def test_bundle_has_no_queue_site_coordinate_report_or_status_metadata(self) -> None:
        serialized = b"".join(
            path.read_bytes() for path in BUNDLE.rglob("*") if path.is_file()
        )
        for forbidden in (
            b"satq-",
            b'"queue_id"',
            b'"entity"',
            b'"aoi_bbox_wgs84"',
            b'"priority"',
            b'"operator"',
            b'"current_status"',
            b'"report.json"',
            b'"change-proposals.geojson"',
        ):
            self.assertNotIn(forbidden, serialized)
        for job in self.source["jobs"].values():
            self.assertNotIn(job["entity"]["id"].encode(), serialized)
            self.assertNotIn(job["entity"]["name"].encode(), serialized)
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(self.manifest["summary"], EXPECTED_SUMMARY)

    def test_sources_runtime_builder_membership_and_commitment_are_exact(self) -> None:
        self.assertEqual(self.definition["generated_at"], GENERATED_AT)
        self.assertEqual(
            self.definition["membership_proof"],
            {
                "accepted_change_run_selected_jobs": 68,
                "accepted_preparation_unreviewed_single_tile_ready_jobs": 68,
                "exact_set_equality": True,
                "selected_queue_ids_sha256": SOURCE_SELECTION_SHA256,
            },
        )
        self.assertEqual(
            self.definition["source"],
            {
                "accepted_change_run": {
                    "bytes": 108_590_556,
                    "files": 409,
                    "manifest_sha256": implementation.SOURCE_RUN_MANIFEST_SHA256,
                    "path": (
                        "satellite_change_runs/"
                        "2026-07-21-open-seed-v83-active-unreviewed-remaining-001"
                    ),
                    "tree_sha256": implementation.SOURCE_RUN_TREE[
                        "inventory_sha256"
                    ],
                },
                "accepted_metadata_preparation": {
                    "definition_sha256": (
                        implementation.SOURCE_PREPARATION_DEFINITION_SHA256
                    ),
                    "manifest_sha256": (
                        implementation.SOURCE_PREPARATION_MANIFEST_SHA256
                    ),
                    "path": (
                        "satellite_change_preparation/"
                        "2026-07-21-open-seed-v83-active-v2"
                    ),
                    "tree_sha256": implementation.SOURCE_PREPARATION_TREE[
                        "inventory_sha256"
                    ],
                },
            },
        )
        self.assertEqual(
            self.definition["builder"]["files"],
            {
                "cli": {
                    "bytes": 1_904,
                    "path": (
                        "scripts/"
                        "build_satellite_change_blind_preparation_explicit_v83.py"
                    ),
                    "sha256": (
                        "536abda45f172c8322260daf745322426c1c55071d35d736b8ed45885ddf8641"
                    ),
                },
                "module": {
                    "bytes": 34_540,
                    "path": (
                        "datacenter_atlas/"
                        "satellite_change_blind_preparation_explicit_v83.py"
                    ),
                    "sha256": (
                        "d9753600df567092fc2c33b623436560e22e297759adea0b0e1445232ae4a041"
                    ),
                },
                "root_shim": {
                    "bytes": 170,
                    "path": "satellite_change_blind_preparation_explicit_v83.py",
                    "sha256": (
                        "033a96400c3d56bc3f4dea6398d9d6467b1334e0e200c0d02da39586cb3c895d"
                    ),
                },
            },
        )
        self.assertEqual(self.definition["runtime"], implementation._runtime_lineage())
        order = implementation._blind_order(
            tuple(self.source["selection"]["selected_queue_ids"])
        )
        self.assertEqual(
            self.definition["blinding"]["lineage_commitment_sha256"],
            LINEAGE_COMMITMENT_SHA256,
        )
        self.assertEqual(
            LINEAGE_COMMITMENT_SHA256,
            implementation._lineage_commitment(self.source, order),
        )

    def test_no_replace_primitive_and_validation_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.mkdir()
            final.mkdir()
            with self.assertRaisesRegex(
                implementation.ExplicitV83BlindPreparationError,
                "refusing existing output",
            ):
                implementation._promote_noreplace(stage, final)
            self.assertTrue(stage.is_dir())
            self.assertTrue(final.is_dir())
        completed = subprocess.run(
            [
                sys.executable,
                str(
                    ROOT
                    / "scripts"
                    / "build_satellite_change_blind_preparation_explicit_v83.py"
                ),
                "--validate-only",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)
        self.assertEqual(payload["tree_inventory"]["inventory_sha256"], TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
