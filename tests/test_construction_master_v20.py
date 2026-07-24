from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
import hashlib
import importlib
from itertools import zip_longest
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_master_v4 import (
    BUNDLE_FILES,
    ConstructionMasterV4Error,
    is_frozen_master_v4,
    validate_construction_master_v4,
    validate_definition,
    write_construction_master_v4,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v20.json"
BUNDLE = ROOT / "construction_master/2026-07-20-public-open-v20"
V17_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v17.json"
V17_BUNDLE = ROOT / "construction_master/2026-07-20-public-open-v17"
V44_DATA = ROOT / "releases/2026-07-20-open-seed-v44/construction_pipeline.csv"
V46_DATA = ROOT / "releases/2026-07-20-open-seed-v46/construction_pipeline.csv"

GENERATED_AT = "2026-07-20T10:00:03Z"
V46_RECORDED_AT = "2026-07-20T09:41:21Z"
DEFINITION_SHA256 = "a51d03cd1f1db1aac3f25de5615eb587a6424ee440454175a4e0c8fd95e918b7"
MODULE_SHA256 = "dd95e3edf3f88464fe13c8db1c4b930d775c435918025f3fd16ae9e1f203ab20"
WRAPPER_SHA256 = "30f51d19c3e73b82aca391100dcac8f4b108dd19df7943c58d6285d999acdabc"
SCRIPT_SHA256 = "f560005a3c17c2c4eaff264d5e06bbbc0bf9c4aa255b347acfaa22e522e1cd12"
MANIFEST_SHA256 = "b558cf776693602ae51141ec0ac6445decf84d671447fa3743513d3d0551efe7"
BUNDLE_INVENTORY_SHA256 = "4daa3c277cb9f9fb84e412d428600598edf32dd20f2c136ace052ad9175cc3a4"

OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (5_814, "793e22591832dce983f27bf934e92a5cd63685c85106345835bba469b21c75c0"),
    "README.md": (1_349, "3cbccc4d4ca9882e5fd1f4218b2793af494c5a73fac3f43c5761cab980735f85"),
    "construction-master.csv": (
        189_669_552,
        "7c2e07c14bdf92af20a18d43346dcc50c27fee156f430538491f076c3ac839f0",
    ),
    "construction-master.jsonl": (
        325_424_151,
        "cc5cd646832956e3dd73b35161694d003e5baa544fbf02040f01717b0298dc59",
    ),
    "coverage.json": (8_497, "1c71eca4681bf66f0880266d70cc2e86795ed5b51d620e42076a6613e1db4df5"),
    "manifest.json": (9_668, MANIFEST_SHA256),
    "manifest.sha256": (80, "3da2cee6e661d0c5d7860c1660ef1c2a1e6da1a4643021da0fba4c60fecfebe6"),
}

V17_PINS = {
    "datacenter_atlas/construction_master_v3.py": "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b",
    "construction_master_v3.py": "a1b45de22aa4d8173f38cc2751b0ecee05f5e93df1c32c6099cd34b557e6f06b",
    "scripts/build_construction_master_v3.py": "f5768050847c013d39b7816752ba20dc475afa7b3c80b1632ecbec46d21295b0",
    "sources/construction-master-2026-07-20-public-open-v17.json": "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19",
    "tests/test_construction_master_v17.py": "08e925f29bd3e10d1ad556a018c14bce89085a5cb9b450099842a92244fec546",
}
V17_MANIFEST_SHA256 = "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9"
V17_INVENTORY_SHA256 = "494bfd5051d08b0b337bd1e42508fa76752c561c9ee162976ac772c922b90b12"

EXPECTED_COUNTS = {
    "added_replacement_rows": 118,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 317,
    "replacement_rows_with_any_role": 102,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 35,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 63,
    "replacement_rows_with_tenants": 4,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 317,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 437,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_229,
    "unchanged_replacement_rows": 199,
}
V44_TO_V46_ADDED_SHA256 = "78723301d57f74dc5c35bb1ed60b2042f05e3502bb0752cb7639d493c9198832"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda value: value.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(entry)))
    return digest.hexdigest()


def csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"]: row for row in csv.DictReader(source)}


def id_digest(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def first_rows(path: Path, count: int) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with path.open("rb") as source:
        for _ in range(count):
            row = json.loads(next(source))
            result[row["source"]["record_id"]] = row
    return result


class FrozenConstructionMasterV20Tests(unittest.TestCase):
    def test_frozen_bundle_rebuilds_twice_offline_byte_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            ROOT / "datacenter_atlas/construction_master_v4.py": MODULE_SHA256,
            ROOT / "construction_master_v4.py": WRAPPER_SHA256,
            ROOT / "scripts/build_construction_master_v4.py": SCRIPT_SHA256,
            BUNDLE / "manifest.json": MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(set(OUTPUT_CHECKPOINTS), BUNDLE_FILES)
        for name, (size, digest) in OUTPUT_CHECKPOINTS.items():
            self.assertEqual((BUNDLE / name).stat().st_size, size)
            self.assertEqual(sha256(BUNDLE / name), digest)

        implementation = importlib.import_module(write_construction_master_v4.__module__)
        original_checkpoint = implementation._checkpoint_spec

        def guarded_checkpoint(package_root, spec, label):
            rendered = str(spec.get("path", ""))
            for marker in (
                "open-seed-v44",
                "open-seed-v45",
                "open-seed-v47",
                "construction_master/2026-07-20-public-open-v17",
                "federated_indexes/",
                "audits/",
                "satellite_review_queues/",
            ):
                self.assertNotIn(marker, rendered)
            return original_checkpoint(package_root, spec, label)

        blocked = AssertionError("v20 construction master attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-master-v20-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            implementation, "_checkpoint_spec", side_effect=guarded_checkpoint
        ), patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            write_construction_master_v4(DEFINITION, first, freeze=True)
            write_construction_master_v4(DEFINITION, second, freeze=True)
            validate_construction_master_v4(
                BUNDLE, definition_path=DEFINITION, reproduce=False
            )
            for name in sorted(BUNDLE_FILES):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertEqual((first / name).read_bytes(), (BUNDLE / name).read_bytes())

        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(is_frozen_master_v4(BUNDLE))
        implementation_names = set(dir(implementation))
        self.assertIn("is_frozen_master_v4", implementation_names)
        self.assertNotIn("is_frozen_master_v3", implementation_names)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_definition_is_exact_three_lane_v46_contract(self) -> None:
        definition, _raw, _root, _resolved, context = validate_definition(DEFINITION)
        self.assertEqual(
            set(definition["inputs"]),
            {"base_master", "replacement_release", "satellite_recovery_acceptance"},
        )
        replacement = definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v46")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v46")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"],
            "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
        )
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])
        self.assertEqual(
            {key: definition["expected"][key] for key in EXPECTED_COUNTS},
            EXPECTED_COUNTS,
        )
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(V46_RECORDED_AT.replace("Z", "+00:00")),
        )
        serialized = DEFINITION.read_text(encoding="utf-8").lower()
        for marker in (
            "open-seed-v44",
            "open-seed-v45",
            "open-seed-v47",
            "public-open-v18",
            "public-open-v19",
            "federated_indexes/",
            "audits/",
            "satellite_review_queues/",
        ):
            self.assertNotIn(marker, serialized)

    def test_exact_v44_to_v46_delta_and_master_projection(self) -> None:
        old = csv_by_id(V44_DATA)
        new = csv_by_id(V46_DATA)
        self.assertEqual((len(old), len(new)), (299, 317))
        self.assertFalse(set(old) - set(new))
        added_ids = set(new) - set(old)
        self.assertEqual(len(added_ids), 18)
        self.assertEqual(id_digest(added_ids), V44_TO_V46_ADDED_SHA256)
        self.assertFalse(
            {key for key in set(old) & set(new) if old[key] != new[key]}
        )
        self.assertEqual(
            Counter(new[key]["status"] for key in added_ids),
            {"under_construction": 12, "mep_electrical": 5, "site_preparation": 1},
        )
        for key in added_ids:
            row = new[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            for role in ("owner", "operator", "users", "tenants", "customers"):
                self.assertEqual(row[role], "")

        replacement_rows = first_rows(BUNDLE / "construction-master.jsonl", 317)
        self.assertEqual(set(replacement_rows), set(new))
        for record_id in added_ids:
            row = replacement_rows[record_id]
            self.assertEqual(row["source"]["artifact_id"], "epoch-official-open-seed-v46")
            self.assertEqual((row["entity"]["latitude"], row["entity"]["longitude"]), (None, None))
            self.assertTrue(
                all(row["roles"][role] is None for role in ("owner", "operator", "users", "tenants", "customers"))
            )
            self.assertFalse(row["disposition"]["unique_site_counted"])

    def test_inherited_v17_tail_is_byte_exact_and_scope_stays_non_census(self) -> None:
        with (V17_BUNDLE / "construction-master.jsonl").open("rb") as old, (
            BUNDLE / "construction-master.jsonl"
        ).open("rb") as new:
            for _ in range(299):
                next(old)
            for _ in range(317):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["total"], 109_229)
        self.assertEqual(
            coverage["row_counts"]["by_tier"], {"A": 437, "B": 6_298, "C": 102_494}
        )
        self.assertEqual(
            coverage["row_counts"]["by_source_artifact"]["epoch-official-open-seed-v46"],
            317,
        )
        self.assertEqual(coverage["role_counts"]["rows_with_any_role"], 102)
        self.assertEqual(coverage["role_counts"]["rows_with_contract_marker"], 317)
        scope = coverage["scope"]
        self.assertFalse(scope["global_completeness_claimed"])
        self.assertFalse(scope["benchmark_parity_claimed"])
        self.assertFalse(scope["automatic_entity_merges"])
        self.assertFalse(scope["candidate_or_review_rows_promoted"])
        self.assertFalse(scope["cross_source_resolution_accepted"])
        self.assertIsNone(scope["unique_physical_site_count"])
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        self.assertIn("not a deduplicated physical-site census", readme)
        self.assertIn("not globally additive", readme)

    def test_v17_is_frozen_and_v4_refuses_collisions_and_active_lock(self) -> None:
        for relative, digest in V17_PINS.items():
            self.assertEqual(sha256(ROOT / relative), digest, relative)
        self.assertEqual(sha256(V17_BUNDLE / "manifest.json"), V17_MANIFEST_SHA256)
        self.assertEqual(inventory_sha256(V17_BUNDLE), V17_INVENTORY_SHA256)

        with tempfile.TemporaryDirectory(
            prefix="construction-master-v20-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(ConstructionMasterV4Error):
                write_construction_master_v4(DEFINITION, existing)
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent", target_is_directory=True)
            with self.assertRaises(ConstructionMasterV4Error):
                write_construction_master_v4(DEFINITION, dangling)
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMasterV4Error, "active output lock"):
                write_construction_master_v4(DEFINITION, locked)
            self.assertFalse(locked.exists())


if __name__ == "__main__":
    unittest.main()
