from __future__ import annotations

import csv
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_master_v3 as master_v3
from datacenter_atlas.construction_master_v3 import (
    BUNDLE_FILES,
    ConstructionMasterV3Error,
    validate_construction_master_v3,
    validate_definition,
    write_construction_master_v3,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v17.json"
BUNDLE = ROOT / "construction_master/2026-07-20-public-open-v17"
V16_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v16.json"
V16_BUNDLE = ROOT / "construction_master/2026-07-20-public-open-v16"
V42_DATA = ROOT / "releases/2026-07-20-open-seed-v42/construction_pipeline.csv"
V44_DATA = ROOT / "releases/2026-07-20-open-seed-v44/construction_pipeline.csv"

DEFINITION_SHA256 = "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19"
MODULE_SHA256 = "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b"
SCRIPT_SHA256 = "f5768050847c013d39b7816752ba20dc475afa7b3c80b1632ecbec46d21295b0"
MANIFEST_SHA256 = "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9"
BUNDLE_INVENTORY_SHA256 = "494bfd5051d08b0b337bd1e42508fa76752c561c9ee162976ac772c922b90b12"
OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (5814, "fe310cfed12cc29325fbb65446db43c193b60ef027118caef4f5fa2dfef39089"),
    "README.md": (1349, "8fe4fda4b726d1cffe63bea24a4ba6b90ffb2d0de005b8e38afef9ee11a45fc2"),
    "construction-master.csv": (189640137, "b4763ab160772bd2cbb61d6c21b23b57cb0296bb208dbb92fe496589ee00aaa7"),
    "construction-master.jsonl": (325370164, "b9104d96885a0a726ee0ca497bbb93034921f580fea20346a1fa05f564e48b82"),
    "coverage.json": (8497, "c1fbd7753e401bf7aa4c7a33b4ba1021c090afc076319b1263fd024c20617b49"),
    "manifest.json": (9668, MANIFEST_SHA256),
    "manifest.sha256": (80, "2519cdcc69dca395664bbaf4e37a9fa29ff263c50bdcbdcef0bc0f5c8253feb7"),
}
V16_PINS = {
    "datacenter_atlas/construction_master_v2.py": "cc728bef65911346347ec4eecd1debe82fe48910160b2ffb3cde87dda5aba311",
    "scripts/build_construction_master_v2.py": "b2f36aa554bd03caca3a3e61f02da82ec358022299f9802d94ca16503cd4b5da",
    "sources/construction-master-2026-07-20-public-open-v16.json": "541fddec96e1ef309219ee648d6d9c8fa0e99dbf6db09619d89cb5d05b423be6",
    "tests/test_construction_master_v16.py": "c52971cc94a309f3148d623cb4145fa857cfaa266a36a4aa0287a00f52824e3c",
}
V16_MANIFEST_SHA256 = "a43846e71f07b4eb9ac10643caf71c907a837537ba1ec994caa70a366e45908f"
V16_INVENTORY_SHA256 = "5fd8f4b8ace4a0a5e75e12454b34a64f46374ff41e88dbcbcf8117af625b3ab8"

EXPECTED_COUNTS = {
    "added_replacement_rows": 100,
    "base_replaced_rows": 199,
    "base_rows": 109111,
    "inherited_rows": 108912,
    "replacement_rows": 299,
    "replacement_rows_with_any_role": 102,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 35,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 63,
    "replacement_rows_with_tenants": 4,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 299,
    "satellite_recovery_control_plane_bytes": 15313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 419,
    "tier_b_rows": 6298,
    "tier_c_rows": 102494,
    "total_rows": 109211,
    "unchanged_replacement_rows": 199,
}
V42_TO_V44_ADDED_SHA256 = "b836ccf72b96dd5036fb85d3d9d7d4b5aaab7ac22c8eb23eb8d7268b5a9a3efb"
META_RECORD_ID = "1404f5cd-04ee-57ea-8f73-91992fea0552"
EQUINIX_RECORD_ID = "b284fbeb-8cd9-5448-860d-b4f69bb8bd7a"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda value: value.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(entry)))
    return digest.hexdigest()


def _csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"]: row for row in csv.DictReader(source)}


def _id_digest(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _first_rows(path: Path, count: int) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with path.open("rb") as source:
        for _ in range(count):
            row = json.loads(next(source))
            rows[row["source"]["record_id"]] = row
    return rows


class FrozenConstructionMasterV17Tests(unittest.TestCase):
    def test_frozen_bundle_rebuilds_twice_offline_byte_exact(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(
            _sha256(ROOT / "datacenter_atlas/construction_master_v3.py"),
            MODULE_SHA256,
        )
        self.assertEqual(
            _sha256(ROOT / "scripts/build_construction_master_v3.py"),
            SCRIPT_SHA256,
        )
        self.assertEqual(_sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(set(OUTPUT_CHECKPOINTS), BUNDLE_FILES)
        for name, (size, digest) in OUTPUT_CHECKPOINTS.items():
            self.assertEqual((BUNDLE / name).stat().st_size, size)
            self.assertEqual(_sha256(BUNDLE / name), digest)

        original_checkpoint = master_v3._checkpoint_spec

        def guarded_checkpoint(package_root, spec, label):
            rendered = str(spec.get("path", ""))
            self.assertNotIn("open-seed-v42", rendered)
            self.assertNotIn("federated_indexes/2026-07-20-public-open-v20", rendered)
            self.assertNotIn("audits/2026-07-20-public-open-coverage-v19", rendered)
            self.assertNotIn("satellite_review_queues/2026-07-20-open-seed-v44", rendered)
            return original_checkpoint(package_root, spec, label)

        blocked = AssertionError("v17 construction master attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-master-v17-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            master_v3, "_checkpoint_spec", side_effect=guarded_checkpoint
        ), patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            write_construction_master_v3(DEFINITION, first, freeze=True)
            write_construction_master_v3(DEFINITION, second, freeze=True)
            validate_construction_master_v3(
                BUNDLE, definition_path=DEFINITION, reproduce=False
            )
            for name in sorted(BUNDLE_FILES):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertEqual((first / name).read_bytes(), (BUNDLE / name).read_bytes())

        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_definition_preserves_the_exact_v16_three_lane_contract(self) -> None:
        definition, _raw, _root, _resolved, context = validate_definition(DEFINITION)
        self.assertEqual(
            set(definition["inputs"]),
            {"base_master", "replacement_release", "satellite_recovery_acceptance"},
        )
        replacement = definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v44")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v44")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"],
            "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9",
        )
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])
        self.assertEqual(
            {key: definition["expected"][key] for key in EXPECTED_COUNTS},
            EXPECTED_COUNTS,
        )
        serialized = DEFINITION.read_text(encoding="utf-8")
        for marker in (
            "open-seed-v42",
            "public-open-v20",
            "public-open-coverage-v19",
            "satellite_review_queues/2026-07-20-open-seed-v44",
            "vnet-",
            "hut8",
            "galaxy",
            "open-seed-v45",
        ):
            self.assertNotIn(marker, serialized.lower())

    def test_exact_v42_to_v44_source_delta_and_coordinate_retirement(self) -> None:
        old = _csv_by_id(V42_DATA)
        new = _csv_by_id(V44_DATA)
        self.assertEqual((len(old), len(new)), (262, 299))
        self.assertFalse(set(old) - set(new))
        added = set(new) - set(old)
        changed = {key for key in old.keys() & new.keys() if old[key] != new[key]}
        self.assertEqual(len(added), 37)
        self.assertEqual(_id_digest(added), V42_TO_V44_ADDED_SHA256)
        self.assertEqual(changed, {META_RECORD_ID, EQUINIX_RECORD_ID})
        self.assertEqual(
            (old[META_RECORD_ID]["latitude"], old[META_RECORD_ID]["longitude"]),
            ("32.43", "-91.76"),
        )
        self.assertEqual(
            (new[META_RECORD_ID]["latitude"], new[META_RECORD_ID]["longitude"]),
            ("", ""),
        )
        self.assertEqual(new[META_RECORD_ID]["operator"], "")
        self.assertEqual(new[META_RECORD_ID]["geometry_json"], "null")
        self.assertEqual(
            (old[EQUINIX_RECORD_ID]["status"], new[EQUINIX_RECORD_ID]["status"]),
            ("under_construction", "shell"),
        )

        replacement_rows = _first_rows(
            BUNDLE / "construction-master.jsonl", EXPECTED_COUNTS["replacement_rows"]
        )
        self.assertEqual(set(replacement_rows), set(new))
        meta = replacement_rows[META_RECORD_ID]
        self.assertEqual((meta["entity"]["latitude"], meta["entity"]["longitude"]), (None, None))
        self.assertIsNone(meta["roles"]["operator"])
        self.assertFalse(meta["disposition"]["unique_site_counted"])
        self.assertEqual(
            replacement_rows[EQUINIX_RECORD_ID]["lifecycle"]["normalized_status"],
            "shell",
        )

    def test_inherited_v16_tail_is_byte_exact_and_scope_stays_non_census(self) -> None:
        with (V16_BUNDLE / "construction-master.jsonl").open("rb") as old, (
            BUNDLE / "construction-master.jsonl"
        ).open("rb") as new:
            for _ in range(262):
                next(old)
            for _ in range(299):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        scope = coverage["scope"]
        self.assertFalse(scope["global_completeness_claimed"])
        self.assertFalse(scope["benchmark_parity_claimed"])
        self.assertFalse(scope["automatic_entity_merges"])
        self.assertFalse(scope["candidate_or_review_rows_promoted"])
        self.assertFalse(scope["cross_source_resolution_accepted"])
        self.assertIsNone(scope["unique_physical_site_count"])
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertEqual(
            coverage["row_counts"]["by_tier"], {"A": 419, "B": 6298, "C": 102494}
        )
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        self.assertIn("not a deduplicated physical-site census", readme)
        self.assertIn("not globally additive", readme)

    def test_v16_is_byte_frozen_and_v3_refuses_collisions_and_active_lock(self) -> None:
        for relative, digest in V16_PINS.items():
            self.assertEqual(_sha256(ROOT / relative), digest, relative)
        self.assertEqual(_sha256(V16_BUNDLE / "manifest.json"), V16_MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(V16_BUNDLE), V16_INVENTORY_SHA256)

        with tempfile.TemporaryDirectory(
            prefix="construction-master-v17-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(ConstructionMasterV3Error):
                write_construction_master_v3(DEFINITION, existing)
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent", target_is_directory=True)
            with self.assertRaises(ConstructionMasterV3Error):
                write_construction_master_v3(DEFINITION, dangling)
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMasterV3Error, "active output lock"):
                write_construction_master_v3(DEFINITION, locked)
            self.assertFalse(locked.exists())


if __name__ == "__main__":
    unittest.main()
