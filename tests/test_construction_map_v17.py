from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map_v3 import (
    BUNDLE_FILES,
    ConstructionMapV3Error,
    validate_construction_map_v3,
    validate_map_definition_v3,
    write_construction_map_v3,
)


ROOT = Path(__file__).resolve().parents[1]
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v17.json"
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v17.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v17"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v17"
V16_MAP = ROOT / "construction_maps/2026-07-20-public-open-v16"

DEFINITION_SHA256 = "1e0c00892932e5e1077acbc018a98785f0b85b1b565d9adc6fe3126c62d3c806"
MODULE_SHA256 = "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6"
SCRIPT_SHA256 = "7cb00575b73b97d6864e436f9942dce88f991d896dff88121957c316107f49ed"
MANIFEST_SHA256 = "5e57250b6765838ee9ae4e250b92a11e65b077307a2156c047c636752fe3e3c4"
BUNDLE_INVENTORY_SHA256 = "c39d99379548800cb83cac45d1e419cb1349e98ff4e1340dfe87795aa089800e"
OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (365, "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d"),
    "README.md": (518, "299774105cf5285c7c2c13c5139476ce98095facf6a86a084bd98f8d54f6a90d"),
    "construction-map-index.json.gz": (6676005, "cab31a1c1264160711fa73325896d54adad3ed8e02acc2a19296ea1a737cbf81"),
    "construction-map.html": (8918948, "cf487bcbea588df3fff0108e5b2d05c4562903d1093386d30ba24ccd613eac20"),
    "coverage.json": (7389, "ff6552d63d31944497c9c669938cc5e973b5d26a14b19aff691ecd142de92a1a"),
    "manifest.json": (2192, MANIFEST_SHA256),
    "manifest.sha256": (80, "fb2efc5be13a614e3b42dc50ecdbfbf8c6571d5089eceaa4127ea30754c5ee5c"),
}
V16_PINS = {
    "datacenter_atlas/construction_map_v2.py": "6f5e15e4bf86db7df31a55e1177057ac27d407ce7012cf8d7b2d1631018afe0b",
    "scripts/build_construction_map_v2.py": "25ac90b816a866b6824fbd220f6d2ea4eff3790d19c91bfac6fd7ed7042cfb46",
    "sources/construction-map-2026-07-20-public-open-v16.json": "cdbcf7f9f71e451ef6a298102866ea6715cec022ab4f1315d61bea682939a0d4",
    "tests/test_construction_map_v16.py": "50f78fd1100a0c5af50faea8a451e3ceb77182db4fd8e8d4eaf55c6245a9f055",
}
V16_MANIFEST_SHA256 = "ee8dbdd2c0a050695b739af59ee167fb40edefb4cc8c68261fb36eabc1a29fe2"
V16_INVENTORY_SHA256 = "5edbc7f2d98e9bcf3ee9f5ceb1ada6ccf6299914203aa2de6c8afb48e06b7f06"

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 97,
    "added_replacement_unmapped_source_record_ids_sha256": "30a008b5f635792da1ba2f07935ee5659ed5f572b061c41524294d70b13e670c",
    "default_visible_rows": 6481,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 201, "B": 6280, "C": 102494},
    "mapped_replacement_rows": 82,
    "mapped_rows": 108975,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109211,
    "unmapped_rows": 236,
    "unmapped_source_record_ids_sha256": "510afb63b92c0b51ee8bc5221c3eacb8defdd34b1d278d7b3401971490224b87",
}
ADDED_MAPPED = {
    "37e33657-b788-57e6-98f2-b78834cdecda": "curated:avaio-taurus-brandon-mississippi-campus:phase-one-current-campus-build",
    "6710faa1-0010-5269-b1f3-7d7ebcda1ced": "curated:menlo-digital-md-phx1-phoenix-campus:current-site-preparation",
    "73ac3682-099b-5356-a872-c3ecdccdc6f6": "curated:menlo-digital-md-va1-herndon-data-center:48mw-facility-build",
}
RETIRED_MAPPED = {
    "1404f5cd-04ee-57ea-8f73-91992fea0552": "curated:meta-richland-parish-data-center:current-development"
}


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


def _index(directory: Path) -> dict:
    return json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )


def _rows_by_record_id(index: dict) -> dict[str, list]:
    record_index = index["fields"].index("source_record_id")
    return {row[record_index]: row for row in index["rows"]}


class FrozenConstructionMapV17Tests(unittest.TestCase):
    def test_frozen_map_rebuilds_twice_offline_byte_exact(self) -> None:
        self.assertEqual(_sha256(MAP_DEFINITION), DEFINITION_SHA256)
        self.assertEqual(
            _sha256(ROOT / "datacenter_atlas/construction_map_v3.py"), MODULE_SHA256
        )
        self.assertEqual(
            _sha256(ROOT / "scripts/build_construction_map_v3.py"), SCRIPT_SHA256
        )
        self.assertEqual(_sha256(MAP / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(MAP), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(set(OUTPUT_CHECKPOINTS), BUNDLE_FILES)
        for name, (size, digest) in OUTPUT_CHECKPOINTS.items():
            self.assertEqual((MAP / name).stat().st_size, size)
            self.assertEqual(_sha256(MAP / name), digest)

        blocked = AssertionError("v17 construction map attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-map-v17-test-", dir="/private/tmp"
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
                write_construction_map_v3(
                    MASTER,
                    output,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                    freeze=True,
                )
            validate_construction_map_v3(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
                reproduce=False,
            )
            for name in sorted(BUNDLE_FILES):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertEqual((first / name).read_bytes(), (MAP / name).read_bytes())

        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in MAP.iterdir())
        )

    def test_exact_v16_to_v17_projection_delta(self) -> None:
        old_index = _index(V16_MAP)
        new_index = _index(MAP)
        old = _rows_by_record_id(old_index)
        new = _rows_by_record_id(new_index)
        self.assertEqual((len(old), len(new)), (108973, 108975))
        self.assertEqual(set(new) - set(old), set(ADDED_MAPPED))
        self.assertEqual(set(old) - set(new), set(RETIRED_MAPPED))

        fields = new_index["fields"]
        tier_index = fields.index("tier")
        artifact_index = fields.index("source_artifact_id")
        latitude_index = fields.index("latitude")
        longitude_index = fields.index("longitude")
        for record_id in ADDED_MAPPED:
            row = new[record_id]
            self.assertEqual(row[tier_index], "A")
            self.assertEqual(row[artifact_index], "epoch-official-open-seed-v44")
            self.assertIsInstance(row[latitude_index], float)
            self.assertIsInstance(row[longitude_index], float)

        entities = {}
        with (ROOT / "releases/2026-07-20-open-seed-v44/entities.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            import csv

            entities = {row["entity_id"]: row["stable_key"] for row in csv.DictReader(source)}
        self.assertEqual({key: entities[key] for key in ADDED_MAPPED}, ADDED_MAPPED)
        self.assertEqual({key: entities[key] for key in RETIRED_MAPPED}, RETIRED_MAPPED)

    def test_definition_coverage_and_unmapped_records_are_exact(self) -> None:
        definition = validate_map_definition_v3(
            MAP_DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(definition["expected_projection"], EXPECTED_PROJECTION)
        self.assertEqual(
            definition["master"]["manifest"]["sha256"],
            "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9",
        )
        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(coverage["counts"]["mapped_observation_rows"], 108975)
        self.assertEqual(coverage["counts"]["unmapped_observation_rows"], 236)
        self.assertIsNone(coverage["counts"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["entity_merges_created"])
        self.assertFalse(coverage["scope"]["atlas_claims_created"])
        self.assertTrue(coverage["scope"]["review_and_discovery_rows_remain_unpromoted"])

        index = _index(MAP)
        mapped = set(_rows_by_record_id(index))
        all_records: set[str] = set()
        with (MASTER / "construction-master.jsonl").open("rb") as source:
            for raw in source:
                all_records.add(json.loads(raw)["source"]["record_id"])
        unmapped = all_records - mapped
        self.assertEqual(len(unmapped), 236)
        digest = hashlib.sha256()
        for record_id in sorted(unmapped):
            digest.update(record_id.encode("utf-8"))
            digest.update(b"\n")
        self.assertEqual(
            digest.hexdigest(),
            EXPECTED_PROJECTION["unmapped_source_record_ids_sha256"],
        )

    def test_v16_is_byte_frozen_and_v3_refuses_collisions_and_active_lock(self) -> None:
        for relative, digest in V16_PINS.items():
            self.assertEqual(_sha256(ROOT / relative), digest, relative)
        self.assertEqual(_sha256(V16_MAP / "manifest.json"), V16_MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(V16_MAP), V16_INVENTORY_SHA256)

        with tempfile.TemporaryDirectory(
            prefix="construction-map-v17-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(ConstructionMapV3Error):
                write_construction_map_v3(
                    MASTER,
                    existing,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent", target_is_directory=True)
            with self.assertRaises(ConstructionMapV3Error):
                write_construction_map_v3(
                    MASTER,
                    dangling,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMapV3Error, "active output lock"):
                write_construction_map_v3(
                    MASTER,
                    locked,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )
            self.assertFalse(locked.exists())


if __name__ == "__main__":
    unittest.main()
