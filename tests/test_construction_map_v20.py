from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map_v4 import (
    BUNDLE_FILES,
    ConstructionMapV4Error,
    validate_construction_map_v4,
    validate_map_definition_v4,
    write_construction_map_v4,
)


ROOT = Path(__file__).resolve().parents[1]
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v20.json"
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v20.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v20"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v20"
V17_MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v17.json"
V17_MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v17.json"
V17_MASTER = ROOT / "construction_master/2026-07-20-public-open-v17"
V17_MAP = ROOT / "construction_maps/2026-07-20-public-open-v17"
V44_DATA = ROOT / "releases/2026-07-20-open-seed-v44/construction_pipeline.csv"
V46_DATA = ROOT / "releases/2026-07-20-open-seed-v46/construction_pipeline.csv"

DEFINITION_SHA256 = "cbdd185f38aebd67b82899b20ddc5d23425eef33ffb1d24e97da4bdaa615e3ed"
MODULE_SHA256 = "32b92ec345172b538f28fca9a491605fec961e962d39f68b3afe943d6fa8b23e"
WRAPPER_SHA256 = "cbf26d380e306f97abef1a28d7fa0dd065c1756bf95322d504fe0a65e845eead"
SCRIPT_SHA256 = "2e48663d6304086e5bf44ee26a4a47da7732f460ddd5c71182d7352a34b4ec43"
MANIFEST_SHA256 = "6dcc9c02a37200f9fec5894aaa97f0ce30e330225567168b5455fb3d4310070c"
BUNDLE_INVENTORY_SHA256 = "72141c5c9f491e36d0e67e429db2c667c7e5d341fa363587d7ee6d360d819c9c"

OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (365, "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d"),
    "README.md": (518, "02bd367c3421bee74828338fa32a8fe078d3610676b2e9882ba2952148856ec6"),
    "construction-map-index.json.gz": (
        6_676_019,
        "13ae747bb28aa82f67634d68c79d578d46fe78704259eb9ba2e2c579d57bdb4e",
    ),
    "construction-map.html": (
        8_918_968,
        "67a22e4e4870fb8ae0849b747950f7494cd26df871fbf2139ce68b0e5949d4bc",
    ),
    "coverage.json": (7_390, "0fa081c63a2c9ea6b11fe6c81ea8660cabcb62604b716f3b46cb1ec016bb2bd8"),
    "manifest.json": (2_192, MANIFEST_SHA256),
    "manifest.sha256": (80, "7293bb33f0087823dd3d1840b90ce07af5aaf5733414efea1b13b2ea93a52920"),
}

MASTER_PINS = {
    MASTER_DEFINITION: "a51d03cd1f1db1aac3f25de5615eb587a6424ee440454175a4e0c8fd95e918b7",
    MASTER / "construction-master.jsonl": "cc5cd646832956e3dd73b35161694d003e5baa544fbf02040f01717b0298dc59",
    MASTER / "manifest.json": "b558cf776693602ae51141ec0ac6445decf84d671447fa3743513d3d0551efe7",
}
V17_PINS = {
    V17_MAP_DEFINITION: "1e0c00892932e5e1077acbc018a98785f0b85b1b565d9adc6fe3126c62d3c806",
    V17_MASTER_DEFINITION: "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19",
    V17_MASTER / "manifest.json": "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9",
    V17_MAP / "manifest.json": "5e57250b6765838ee9ae4e250b92a11e65b077307a2156c047c636752fe3e3c4",
    ROOT / "datacenter_atlas/construction_map_v3.py": "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6",
    ROOT / "tests/test_construction_map_v17.py": "d0bb5bc7c0d7f998a29fddb9d16ef3baabca02b9181fbf1e520577cb80230015",
}
V17_MAP_INVENTORY_SHA256 = "c39d99379548800cb83cac45d1e419cb1349e98ff4e1340dfe87795aa089800e"

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 115,
    "added_replacement_unmapped_source_record_ids_sha256": "6f3dfab4c7b80a4c1f3d630dea543df92c19a51aa53b73b260cdbd62f9de1894",
    "default_visible_rows": 6_481,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 201, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 82,
    "mapped_rows": 108_975,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109_229,
    "unmapped_rows": 254,
    "unmapped_source_record_ids_sha256": "9c77e665340a04014919c9392ddb82394942c28ca136a4399ebdd6d47385cac7",
}
ADDED_MAPPED = {
    "37e33657-b788-57e6-98f2-b78834cdecda",
    "6710faa1-0010-5269-b1f3-7d7ebcda1ced",
    "73ac3682-099b-5356-a872-c3ecdccdc6f6",
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


def index(directory: Path) -> dict:
    return json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )


def rows_by_record_id(document: dict) -> dict[str, list]:
    record_index = document["fields"].index("source_record_id")
    return {row[record_index]: row for row in document["rows"]}


def csv_ids(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"] for row in csv.DictReader(source)}


def id_digest(values: set[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def prefix_ids(path: Path, count: int) -> set[str]:
    result: set[str] = set()
    with path.open("rb") as source:
        for _ in range(count):
            result.add(json.loads(next(source))["source"]["record_id"])
    return result


class FrozenConstructionMapV20Tests(unittest.TestCase):
    def test_frozen_map_rebuilds_twice_offline_byte_exact(self) -> None:
        pins = {
            MAP_DEFINITION: DEFINITION_SHA256,
            ROOT / "datacenter_atlas/construction_map_v4.py": MODULE_SHA256,
            ROOT / "construction_map_v4.py": WRAPPER_SHA256,
            ROOT / "scripts/build_construction_map_v4.py": SCRIPT_SHA256,
            MAP / "manifest.json": MANIFEST_SHA256,
            **MASTER_PINS,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(inventory_sha256(MAP), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(set(OUTPUT_CHECKPOINTS), BUNDLE_FILES)
        for name, (size, digest) in OUTPUT_CHECKPOINTS.items():
            self.assertEqual((MAP / name).stat().st_size, size)
            self.assertEqual(sha256(MAP / name), digest)

        blocked = AssertionError("v20 construction map attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-map-v20-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            for output in (first, second):
                write_construction_map_v4(
                    MASTER,
                    output,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                    freeze=True,
                )
            validate_construction_map_v4(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
                reproduce=False,
            )
            for name in sorted(BUNDLE_FILES):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertEqual((first / name).read_bytes(), (MAP / name).read_bytes())

        self.assertEqual(stat.S_IMODE(MAP_DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in MAP.iterdir())
        )

    def test_definition_projection_and_unmapped_records_are_exact(self) -> None:
        definition = validate_map_definition_v4(
            MAP_DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(definition["expected_projection"], EXPECTED_PROJECTION)
        self.assertEqual(
            definition["master"]["manifest"]["sha256"],
            "b558cf776693602ae51141ec0ac6445decf84d671447fa3743513d3d0551efe7",
        )
        serialized = MAP_DEFINITION.read_text(encoding="utf-8").lower()
        for marker in (
            "public-open-v17",
            "public-open-v18",
            "public-open-v19",
            "open-seed-v44",
            "open-seed-v45",
            "open-seed-v47",
        ):
            self.assertNotIn(marker, serialized)

        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(coverage["counts"]["mapped_observation_rows"], 108_975)
        self.assertEqual(coverage["counts"]["unmapped_observation_rows"], 254)
        self.assertIsNone(coverage["counts"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["entity_merges_created"])
        self.assertFalse(coverage["scope"]["atlas_claims_created"])
        self.assertTrue(coverage["scope"]["review_and_discovery_rows_remain_unpromoted"])

        current_index = index(MAP)
        mapped = set(rows_by_record_id(current_index))
        all_records: set[str] = set()
        with (MASTER / "construction-master.jsonl").open("rb") as source:
            for raw in source:
                all_records.add(json.loads(raw)["source"]["record_id"])
        unmapped = all_records - mapped
        self.assertEqual(len(unmapped), 254)
        self.assertEqual(id_digest(unmapped), EXPECTED_PROJECTION["unmapped_source_record_ids_sha256"])

        base_ids = prefix_ids(
            ROOT / "construction_master/2026-07-19-public-open-v14/construction-master.jsonl",
            199,
        )
        replacement_ids = prefix_ids(MASTER / "construction-master.jsonl", 317)
        added = replacement_ids - base_ids
        self.assertEqual(len(added), 118)
        self.assertEqual(added & mapped, ADDED_MAPPED)
        self.assertEqual(len(added - mapped), 115)
        self.assertEqual(
            id_digest(added - mapped),
            EXPECTED_PROJECTION["added_replacement_unmapped_source_record_ids_sha256"],
        )

    def test_v17_to_v20_keeps_mapped_record_set_and_changes_only_lineage(self) -> None:
        old_index = index(V17_MAP)
        new_index = index(MAP)
        self.assertEqual(old_index["fields"], new_index["fields"])
        fields = new_index["fields"]
        field_index = {field: position for position, field in enumerate(fields)}
        old = rows_by_record_id(old_index)
        new = rows_by_record_id(new_index)
        self.assertEqual((len(old), len(new)), (108_975, 108_975))
        self.assertEqual(set(old), set(new))

        changed = {record_id for record_id in old if old[record_id] != new[record_id]}
        self.assertEqual(len(changed), 82)
        for record_id in changed:
            before = old[record_id]
            after = new[record_id]
            self.assertEqual(before[field_index["source_artifact_id"]], "epoch-official-open-seed-v44")
            self.assertEqual(after[field_index["source_artifact_id"]], "epoch-official-open-seed-v46")
            self.assertEqual(before[field_index["source_release_id"]], "epoch-official-open-seed-v44")
            self.assertEqual(after[field_index["source_release_id"]], "epoch-official-open-seed-v46")
            differing = {
                fields[position]
                for position, (left, right) in enumerate(zip(before, after))
                if left != right
            }
            self.assertEqual(
                differing, {"row_id", "source_artifact_id", "source_release_id"}
            )
        self.assertTrue(
            all(old[key] == new[key] for key in set(old) - changed)
        )

        v44_ids = csv_ids(V44_DATA)
        v46_ids = csv_ids(V46_DATA)
        added = v46_ids - v44_ids
        self.assertEqual(len(added), 18)
        self.assertEqual(id_digest(added), V44_TO_V46_ADDED_SHA256)
        self.assertTrue(added.isdisjoint(new))

    def test_v17_is_frozen_and_v4_refuses_collisions_and_active_lock(self) -> None:
        for path, digest in V17_PINS.items():
            self.assertEqual(sha256(path), digest, path)
        self.assertEqual(inventory_sha256(V17_MAP), V17_MAP_INVENTORY_SHA256)

        with tempfile.TemporaryDirectory(
            prefix="construction-map-v20-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(ConstructionMapV4Error):
                write_construction_map_v4(
                    MASTER,
                    existing,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent", target_is_directory=True)
            with self.assertRaises(ConstructionMapV4Error):
                write_construction_map_v4(
                    MASTER,
                    dangling,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMapV4Error, "active output lock"):
                write_construction_map_v4(
                    MASTER,
                    locked,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            self.assertFalse(locked.exists())


if __name__ == "__main__":
    unittest.main()
