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

import datacenter_atlas.datacenter_atlas.satellite_change_blind_preparation_explicit_v1 as implementation
from datacenter_atlas.satellite_change_blind_preparation_explicit_v1 import (
    ATTRIBUTION_FILENAME,
    BLIND_ID_PREFIX,
    DEFINITION_FILENAME,
    GUARDRAILS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    PREPARATION_ID,
    README_FILENAME,
    SOURCE_JOB_COUNT,
    UNITS_FILENAME,
    VISUAL_FILENAMES,
    build_blind_preparation,
    validate_blind_preparation,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "satellite_change_preparation" / PREPARATION_ID
GENERATED_AT = "2026-07-21T14:14:00.000000Z"
MANIFEST_SHA256 = "353dad8aee795cafc8ab4c80fe83ee05c8188f153f8aa792584b021bec38dbea"
TREE_SHA256 = "184927d0fb85b4aae762fc768a4b73f4131f061254fe4ea9f880e578d39c2502"
EXPECTED_MEMBERS = {
    ATTRIBUTION_FILENAME: (
        250,
        "c2300372919a72fbd4185f65960d15e221da6b6725dc22fe9d4b48901a530ea8",
    ),
    DEFINITION_FILENAME: (
        3_375,
        "138e85a8240a3cbac98cf89066c6746137ca0a15916abb2118f14cec4176ea61",
    ),
    MANIFEST_FILENAME: (8_812, MANIFEST_SHA256),
    MANIFEST_HASH_FILENAME: (
        80,
        "f4cc7d79d1794ec0945e2f73f34a6b84f3decad09a9d741d49466e23991422c9",
    ),
    README_FILENAME: (
        716,
        "8115047e33a53b73f67c244b165d453ae67165f0b211a0e5de188656ececafe9",
    ),
    UNITS_FILENAME: (
        7_306,
        "7fceed341aacee5ff9456071d17a21daa21af13e536de3b3b19492190a85a732",
    ),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ExplicitV1BlindPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition_raw = (BUNDLE / DEFINITION_FILENAME).read_bytes()
        cls.definition = json.loads(cls.definition_raw)
        cls.manifest_raw = (BUNDLE / MANIFEST_FILENAME).read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)
        cls.units = [
            json.loads(line)
            for line in (BUNDLE / UNITS_FILENAME).read_bytes().splitlines()
        ]

    def test_frozen_bundle_reproduces_offline_with_exact_pins(self) -> None:
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

    def test_exact_manifest_members_tree_and_modes(self) -> None:
        self.assertEqual(_sha256(self.manifest_raw), MANIFEST_SHA256)
        self.assertEqual(
            (BUNDLE / MANIFEST_HASH_FILENAME).read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  {MANIFEST_FILENAME}\n",
        )
        for name, (size, digest) in EXPECTED_MEMBERS.items():
            raw = (BUNDLE / name).read_bytes()
            self.assertEqual((len(raw), _sha256(raw)), (size, digest))
        inventory = implementation._tree_inventory(BUNDLE)
        self.assertEqual(
            inventory,
            {
                "directories": 13,
                "file_bytes": 17_648_838,
                "files": 50,
                "inventory_sha256": TREE_SHA256,
            },
        )
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for path in BUNDLE.rglob("*"):
            self.assertFalse(path.is_symlink())
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode),
                0o555 if path.is_dir() else 0o444,
            )
        target = implementation._timestamp(GENERATED_AT, "generated_at")[1]
        self.assertGreaterEqual(BUNDLE.stat().st_ctime + 1e-6, target.timestamp())

    def test_neutral_randomized_units_expose_only_four_png_views(self) -> None:
        self.assertEqual(len(self.units), SOURCE_JOB_COUNT)
        self.assertEqual(
            [row["blind_id"] for row in self.units],
            [f"{BLIND_ID_PREFIX}{index:03d}" for index in range(1, 12)],
        )
        self.assertNotEqual(
            tuple(queue_id for _blind_id, queue_id in implementation._blind_order()),
            implementation.SOURCE_QUEUE_IDS,
        )
        paths: set[str] = set()
        for index, row in enumerate(self.units, 1):
            self.assertEqual(set(row), {"blind_id", "inspection_order", "schema_version", "views"})
            self.assertEqual(row["inspection_order"], index)
            self.assertEqual(tuple(row["views"]), tuple(sorted(VISUAL_FILENAMES)))
            for name, spec in row["views"].items():
                self.assertEqual(
                    spec["path"], f"images/{row['blind_id']}/{name}"
                )
                self.assertNotIn(spec["path"], paths)
                paths.add(spec["path"])
                raw = (BUNDLE / spec["path"]).read_bytes()
                self.assertEqual((len(raw), _sha256(raw)), (spec["bytes"], spec["sha256"]))
                chunks = implementation._png_chunks(raw, spec["path"])
                self.assertTrue(chunks)
        self.assertEqual(len(paths), 44)

    def test_bundle_contains_no_lineage_reports_or_atlas_facts(self) -> None:
        serialized = b"".join(
            path.read_bytes() for path in BUNDLE.rglob("*") if path.is_file()
        )
        for forbidden in (
            b"satq-",
            b'"queue_id"',
            b'"current_status"',
            b'"operator"',
            b'"report.json"',
            b'"capacity"',
            b'"power"',
            b'"pue"',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(
            self.manifest["summary"],
            {
                "blind_review_units": 11,
                "copied_visual_artifacts": 44,
                "lineage_rows_exposed": 0,
                "queue_ids_exposed": 0,
                "report_artifacts_copied": 0,
            },
        )

    def test_sources_runtime_builder_and_commitment_are_exact(self) -> None:
        self.assertEqual(self.definition["generated_at"], GENERATED_AT)
        self.assertEqual(
            self.definition["source"],
            {
                "accepted_disposition": {
                    "manifest_sha256": implementation.SOURCE_DISPOSITION_MANIFEST_SHA256,
                    "path": "satellite_change_run_dispositions/2026-07-21-open-seed-v71-active-explicit-001-v1",
                    "tree_sha256": implementation.SOURCE_DISPOSITION_TREE_SHA256,
                },
                "change_run": {
                    "bytes": 19_106_330,
                    "files": 67,
                    "manifest_sha256": implementation.SOURCE_CHANGE_MANIFEST_SHA256,
                    "path": "satellite_change_runs/2026-07-21-open-seed-v71-active-explicit-001",
                    "tree_sha256": implementation.SOURCE_CHANGE_TREE_SHA256,
                },
            },
        )
        self.assertEqual(
            self.definition["builder"]["files"],
            {
                "cli": {
                    "bytes": 1_903,
                    "path": "scripts/build_satellite_change_blind_preparation_explicit_v1.py",
                    "sha256": "a0d9c5e31bd808a1f02d9ab3bbd310c72e28fd7bfd69a89d802618eb90e50a4a",
                },
                "module": {
                    "bytes": 25_645,
                    "path": "datacenter_atlas/satellite_change_blind_preparation_explicit_v1.py",
                    "sha256": "57be830c97d843c654f1dd25bd6eea421e85a5f7984d2dacfb4073b982092941",
                },
                "root_shim": {
                    "bytes": 178,
                    "path": "satellite_change_blind_preparation_explicit_v1.py",
                    "sha256": "6233d0197a070698fa716537e7aa51322d2ff12b75000c620fff96e4a830c418",
                },
            },
        )
        self.assertEqual(
            self.definition["runtime"],
            implementation._runtime_lineage(),
        )
        self.assertEqual(
            self.definition["blinding"]["lineage_commitment_sha256"],
            implementation._lineage_commitment(
                json.loads(
                    (implementation.SOURCE_RUN_PATH / "batch-manifest.json").read_text()
                ),
                implementation._blind_order(),
            ),
        )

    def test_no_replace_promotion_and_validation_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.mkdir()
            final.mkdir()
            with self.assertRaisesRegex(
                implementation.ExplicitV1BlindPreparationError,
                "refusing existing output",
            ):
                implementation._promote_noreplace(stage, final)
            self.assertTrue(stage.is_dir())
            self.assertTrue(final.is_dir())
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_satellite_change_blind_preparation_explicit_v1.py"),
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
