from __future__ import annotations

import copy
import csv
import gzip
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_map_v7 as map_v7
from datacenter_atlas import construction_master_v7 as master_v7
from datacenter_atlas.construction_map_v7 import (
    ConstructionMapV7Error,
    validate_construction_map_v7,
    validate_map_definition_v7,
    write_construction_map_v7,
)
from datacenter_atlas.construction_master_v7 import (
    ConstructionMasterV7Error,
    validate_construction_master_v7,
    validate_definition,
    write_construction_master_v7,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v23.json"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v23.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v23"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v23"
V22_MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v22.json"
V22_MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v22.json"
V22_MASTER = ROOT / "construction_master/2026-07-20-public-open-v22"
V22_MAP = ROOT / "construction_maps/2026-07-20-public-open-v22"
V55_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"

SOURCE_PINS = {
    MASTER_DEFINITION: "6a72a8c44808ad6d276fed6141b15ee91e5708b5ff95f91aaf0c011e0c69d438",
    MAP_DEFINITION: "6022402312649301dc921981bc89bb63801b456f9bbcb7915bb9dc475cbdcf79",
    ROOT / "datacenter_atlas/construction_master_v7.py": (
        "80fb676a3f30b92a105a656b206b837360705a3ad2534a663bc53a5488e42f02"
    ),
    ROOT / "datacenter_atlas/construction_map_v7.py": (
        "053995421f2e581ba49ea5bf89fd539afce527b718c643ea8e1074204a7586be"
    ),
    ROOT / "construction_master_v7.py": (
        "cf0657e1970a262a653418404c56abd6d3b2c3b6b79101ce97b9f796aeabe007"
    ),
    ROOT / "construction_map_v7.py": (
        "b657eba7fe56c4dd19f35f6a3388b4b1eba91f3ee810c4532c6aabef439d0bb7"
    ),
    ROOT / "scripts/build_construction_master_v7.py": (
        "a184073ce4c3d4ef591b74812c58a8250bcf0835424707e4130e2b426c19fc14"
    ),
    ROOT / "scripts/build_construction_map_v7.py": (
        "300803a84d3419cebcc6e5de1d3bf667346eac68322e1c03cce80158dbfb4ef8"
    ),
    ROOT / "datacenter_atlas/construction_master_v3.py": (
        "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b"
    ),
    ROOT / "datacenter_atlas/construction_map_v3.py": (
        "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6"
    ),
}

V22_PINS = {
    V22_MASTER_DEFINITION: "6a66eb3698d15c428d6196e46f1f1ceca468bb5180b372c33632d6506684fca7",
    V22_MAP_DEFINITION: "e9da20d5e60351f9dded7becd79927c297af40490b3b0583ba11256c350299e8",
    ROOT / "datacenter_atlas/construction_master_v6.py": (
        "260389903e4bd0b4877251076f6913eb3e5ae197efc1def4e1d0ce1d836558bd"
    ),
    ROOT / "datacenter_atlas/construction_map_v6.py": (
        "941bf89f4913f2cfc40859abb16a735f286c3323fc8e8d3811e14d728b96f6df"
    ),
}
V22_MASTER_INVENTORY_SHA256 = "896b1dd79c2eb36cbab25c13890c11b2c2e6e1a9954c4bd9d384170ede65365d"
V22_MAP_INVENTORY_SHA256 = "9e6c4e0d38963e75c4abf9a02433f98069d684d83bf12bb8e755556a87921bc7"

V55_PINS = {
    ROOT / "sources/open-seed-2026-07-20-v55.json": (
        67_472,
        "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba",
    ),
    V55_RELEASE / "manifest.json": (
        9_210,
        "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
    ),
    V55_RELEASE / "construction_pipeline.csv": (
        455_437,
        "a2843ed87812c299ec9654763604115f77fc1e5c33519bf5e41b3f04e44f73c7",
    ),
    V55_RELEASE / "evidence.csv": (
        147_576,
        "a8fd8bd16cf423a2f0582a564378cd2b1fd14ee0d2d7d8aea3a2537aa69bb548",
    ),
}

MASTER_OUTPUTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "f30741c5515bf842b051d89acf1a4b049e43df7c4fb248c53a638dd40f3fbcc6",
    ),
    "README.md": (
        1_349,
        "7dd5791056ecaf2b54b9914dafc301a05206e0d9d996dd2feeb4c34962c24500",
    ),
    "construction-master.csv": (
        189_744_742,
        "54570130c7c1149e344c2e5e8281e5a247853d6afe4d63ab05c3271563d54b96",
    ),
    "construction-master.jsonl": (
        325_534_952,
        "9ad9cc90a7844363c3900872d6591212538a435060f65b2316098ee4e3978112",
    ),
    "coverage.json": (
        8_523,
        "a8b1313c5bd017dde45f8f7ed81355a0a0bc9dad065a6ec3543587f22fa0cd7c",
    ),
    "manifest.json": (
        9_694,
        "987580aec591763c01a48ba146dfa935db59097ae189479e6a43386b4a1e8384",
    ),
    "manifest.sha256": (
        80,
        "28a7a14ecfbabffbc6269247c7893349f227c873d901197014747b0d02c880f8",
    ),
}

MAP_OUTPUTS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "7133d6ef6b9c0731f2683ebc09b208d371f6db6fe3b3509271471f1a43ce6cca",
    ),
    "construction-map-index.json.gz": (
        6_676_538,
        "ca9bfefe6e01a1cb1ac74362942066332773c175eba07160b67d433df65ab526",
    ),
    "construction-map.html": (
        8_919_660,
        "3171e5b0bce2fa3222effb7d62b3a27a9af946f28b452b2498279a452fcbe943",
    ),
    "coverage.json": (
        7_390,
        "f644082c91dbf7339092bf347652cb7a0335f50e8a3cb55a5d31fd3d6e2db3b9",
    ),
    "manifest.json": (
        2_192,
        "aa394a0e1d231d1ec3c7f28731933c3844d27f7262119027fa9ce87db9602648",
    ),
    "manifest.sha256": (
        80,
        "6016744a5d8ddbe87c87407f5974cc6748f32c7aed315e2d8faac5e24380d1ca",
    ),
}

MASTER_INVENTORY_SHA256 = "6f1f13c21c69a6cf976614b2be5487de5f635494301117f917524833e080ba65"
MAP_INVENTORY_SHA256 = "6dbc80fbca92218062bdae75796c6d1a43e22e46408dacbbb0f49579ff6a8f53"

EXPECTED_COUNTS = {
    "added_replacement_rows": 147,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 346,
    "replacement_rows_with_any_role": 124,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 48,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 85,
    "replacement_rows_with_tenants": 6,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 346,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 466,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_258,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": "0ada150890036f9770fd5462dd121b47b1cfe485e53d4eb3f507f0e06d0b38ca",
    "base_replaced_source_record_ids_sha256": "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950",
    "inherited_rows_without_roles_sha256": "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f",
    "replacement_role_projection_sha256": "097e08d75828de393155a4aa8fdd59d7ffcee98921166396d9ac39fa4dbe8988",
    "replacement_rows_without_roles_sha256": "ec620bb708901582c8c43c3e78003a6fb4576a25001fefa1d77a362e3ad1be23",
    "replacement_source_record_ids_sha256": "5ad2219cdbf7c3cb630f2e3dc633700d4a0d0742f1355b6fe7e27eca21ad5f4d",
    "tier_a_arithmetic_projection_sha256": "1191ef9e13cbf698ad5838159083601bcb4d7c204b153c5019c2bd725e8ae1a3",
}

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 144,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "7625e430e7f12e6a35b99eb74231b98f21a33405358276182916d27f876625bb"
    ),
    "default_visible_rows": 6_484,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 204, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 85,
    "mapped_rows": 108_978,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109_258,
    "unmapped_rows": 280,
    "unmapped_source_record_ids_sha256": (
        "0f21abbeab1f614b8a170def2077be4eea5953611838d3f469c4fda9eb6a493e"
    ),
}

NEW_MAPPED_BASE_IDS = {
    "3b7bb37e-1ec4-5425-9ed2-8b6218f2daa2",
    "8966a315-7510-5754-a5e4-71849896b96b",
    "97c55ef3-761e-52c1-ac61-24383954d5b4",
}
DIGITAL_EDGE_GOOGLE_IDS = {
    "462ba91a-e5a2-58f6-8e73-c9b8bce5564c",
    "4d4321d8-bdec-5073-b608-12ce8ed20e70",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, _sha256(path)


def _inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda value: value.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(entry)))
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _map_index(directory: Path) -> dict:
    return json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )


class FrozenConstructionMasterV23Tests(unittest.TestCase):
    def test_exact_sources_outputs_predecessor_inventory_and_frozen_modes(self) -> None:
        for path, digest in {**SOURCE_PINS, **V22_PINS}.items():
            with self.subTest(path=path):
                self.assertEqual(_sha256(path), digest)
        self.assertEqual(_inventory_sha256(V22_MASTER), V22_MASTER_INVENTORY_SHA256)
        self.assertEqual(_inventory_sha256(V22_MAP), V22_MAP_INVENTORY_SHA256)
        for path, expected in V55_PINS.items():
            self.assertEqual(_checkpoint(path), expected)
        self.assertEqual(stat.S_IMODE(V55_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in V55_RELEASE.iterdir()
            )
        )

        self.assertEqual(set(MASTER_OUTPUTS), master_v7.BUNDLE_FILES)
        self.assertEqual(set(MAP_OUTPUTS), map_v7.BUNDLE_FILES)
        self.assertEqual(_inventory_sha256(MASTER), MASTER_INVENTORY_SHA256)
        self.assertEqual(_inventory_sha256(MAP), MAP_INVENTORY_SHA256)
        for directory, checkpoints in ((MASTER, MASTER_OUTPUTS), (MAP, MAP_OUTPUTS)):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)
            for name, expected in checkpoints.items():
                path = directory / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual(_checkpoint(path), expected)

    def test_lineage_changes_only_from_v22_replacement_to_accepted_v55(self) -> None:
        old = json.loads(V22_MASTER_DEFINITION.read_text())
        new = json.loads(MASTER_DEFINITION.read_text())
        self.assertEqual(old["inputs"]["base_master"], new["inputs"]["base_master"])
        self.assertEqual(
            old["inputs"]["satellite_recovery_acceptance"],
            new["inputs"]["satellite_recovery_acceptance"],
        )
        self.assertEqual(old["scope"], new["scope"])
        replacement = new["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v55")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v55")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"],
            V55_PINS[V55_RELEASE / "manifest.json"][1],
        )
        master_carrier = (
            ROOT / "datacenter_atlas/construction_master_v7.py"
        ).read_text()
        map_carrier = (ROOT / "datacenter_atlas/construction_map_v7.py").read_text()
        self.assertIn('with_name("construction_master_v3.py")', master_carrier)
        self.assertIn('with_name("construction_map_v3.py")', map_carrier)
        serialized = "".join(
            path.read_text()
            for path in (
                MASTER_DEFINITION,
                MAP_DEFINITION,
                ROOT / "datacenter_atlas/construction_master_v7.py",
                ROOT / "datacenter_atlas/construction_map_v7.py",
            )
        )
        for marker in (
            "federated_indexes/",
            "coverage-audit-",
            "current-coverage-",
            "exact_identity_decisions/",
        ):
            self.assertNotIn(marker, serialized)

    def test_timestamps_are_strictly_ordered_after_v55_and_before_birth(self) -> None:
        v55 = json.loads((ROOT / "sources/open-seed-2026-07-20-v55.json").read_text())
        master_definition = json.loads(MASTER_DEFINITION.read_text())
        map_definition = json.loads(MAP_DEFINITION.read_text())
        times = [
            v55["build"]["recorded_at"],
            master_definition["generated_at"],
            map_definition["generated_at"],
        ]
        self.assertEqual(
            times,
            [
                "2026-07-20T20:05:00Z",
                "2026-07-20T20:20:00Z",
                "2026-07-20T20:20:01Z",
            ],
        )
        self.assertEqual(times, sorted(times))
        for artifact, rendered in ((MASTER, times[1]), (MAP, times[2])):
            birth_time = getattr(artifact.stat(), "st_birthtime", None)
            if birth_time is not None:
                timestamp = rendered.replace("Z", "+00:00")
                from datetime import datetime

                self.assertLessEqual(datetime.fromisoformat(timestamp).timestamp(), birth_time)

    def test_master_arithmetic_roles_capacity_status_and_satellite_boundaries(self) -> None:
        definition, _raw, _root, _resolved, context = validate_definition(
            MASTER_DEFINITION
        )
        self.assertEqual(
            {key: definition["expected"][key] for key in EXPECTED_COUNTS},
            EXPECTED_COUNTS,
        )
        self.assertEqual(
            {key: definition["expected"][key] for key in EXPECTED_DIGESTS},
            EXPECTED_DIGESTS,
        )
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])

        coverage = json.loads((MASTER / "coverage.json").read_text())
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 147,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v55",
                "replacement_rows": 346,
                "unchanged_source_record_ids": 199,
            },
        )
        self.assertEqual(
            coverage["role_counts"],
            {
                "rows_with_any_role": 124,
                "rows_with_contract_marker": 346,
                "rows_with_source_role_tags": 85,
                "with_core_role": {
                    "customers": 2,
                    "operator": 48,
                    "owner": 47,
                    "tenants": 6,
                    "users": 36,
                },
            },
        )
        self.assertEqual(
            coverage["row_counts"]["by_tier"],
            {"A": 466, "B": 6_298, "C": 102_494},
        )
        self.assertEqual(coverage["row_counts"]["total"], 109_258)
        self.assertEqual(coverage["row_counts"]["by_normalized_status"]["announced"], 6)
        self.assertEqual(
            coverage["row_counts"]["by_normalized_status"]["under_construction"],
            348,
        )
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["candidate_or_review_rows_promoted"])
        self.assertFalse(
            coverage["scope"]["structural_or_cv_rows_in_construction_arithmetic"]
        )

        with (V55_RELEASE / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            source_rows = {row["entity_id"]: row for row in csv.DictReader(source)}
        self.assertEqual(len(source_rows), 346)
        sentinel_rows = []
        with (MASTER / "construction-master.jsonl").open("rb") as source:
            for line_number, raw in enumerate(source, start=1):
                row = json.loads(raw)
                if line_number <= 346:
                    source_row = source_rows[row["source"]["record_id"]]
                    capacities = json.loads(source_row["capacity_estimates_json"])
                    expected_capacity, expected_annual, expected_pue = (
                        master_v7.legacy._capacity_split(capacities)
                    )
                    self.assertEqual(row["capacity_observations"], expected_capacity)
                    self.assertEqual(row["annual_energy_observations"], expected_annual)
                    self.assertEqual(row["pue_observations"], expected_pue)
                if row["observation_kind"] == "sentinel_analyst_change_review":
                    sentinel_rows.append(row)
        self.assertEqual(len(sentinel_rows), 43)
        self.assertTrue(all(row["tier"] == "C" for row in sentinel_rows))
        self.assertTrue(
            all(
                not row["disposition"]["construction_arithmetic_included"]
                for row in sentinel_rows
            )
        )

        with (V22_MASTER / "construction-master.jsonl").open("rb") as old, (
            MASTER / "construction-master.jsonl"
        ).open("rb") as new:
            for _ in range(327):
                next(old)
            for _ in range(346):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

    def test_map_projection_new_base_mappings_and_unmapped_new_sites_are_exact(self) -> None:
        definition = validate_map_definition_v7(
            MAP_DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(definition["expected_projection"], EXPECTED_PROJECTION)
        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": 108_978,
                "mapped_replacement_rows": 85,
                "mapped_rows_with_any_role": 66,
                "master_observation_rows": 109_258,
                "unique_physical_site_count": None,
                "unmapped_observation_rows": 280,
            },
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])

        old_index = _map_index(V22_MAP)
        new_index = _map_index(MAP)
        old_record_index = old_index["fields"].index("source_record_id")
        new_record_index = new_index["fields"].index("source_record_id")
        old_mapped = {row[old_record_index] for row in old_index["rows"]}
        new_mapped = {row[new_record_index] for row in new_index["rows"]}
        self.assertEqual(new_mapped - old_mapped, NEW_MAPPED_BASE_IDS)
        self.assertFalse(old_mapped - new_mapped)

        base_ids: set[str] = set()
        with (
            ROOT
            / "construction_master/2026-07-19-public-open-v14/construction-master.jsonl"
        ).open("rb") as source:
            for raw in source:
                row = json.loads(raw)
                if row["source"]["artifact_id"] != "epoch-official-open-seed-v33":
                    break
                base_ids.add(row["source"]["record_id"])
        self.assertEqual(len(base_ids), 199)
        self.assertTrue(NEW_MAPPED_BASE_IDS.issubset(base_ids))

        added_ids = map_v7._added_source_record_ids(MASTER_DEFINITION)
        self.assertEqual(len(added_ids), 147)
        self.assertTrue(NEW_MAPPED_BASE_IDS.isdisjoint(added_ids))
        self.assertTrue(DIGITAL_EDGE_GOOGLE_IDS.issubset(added_ids))
        self.assertTrue(DIGITAL_EDGE_GOOGLE_IDS.isdisjoint(new_mapped))
        self.assertEqual(len(added_ids - new_mapped), 144)

        artifact_index = new_index["fields"].index("source_artifact_id")
        self.assertEqual(
            sum(
                row[artifact_index] == "epoch-official-open-seed-v55"
                for row in new_index["rows"]
            ),
            85,
        )

    def test_double_offline_rebuild_is_byte_exact_and_refuses_existing_outputs(self) -> None:
        blocked = AssertionError("v23 construction build attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-v23-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            root = Path(temporary)
            rebuilt_master = root / "master"
            rebuilt_map = root / "map"
            write_construction_master_v7(MASTER_DEFINITION, rebuilt_master, freeze=True)
            write_construction_map_v7(
                MASTER,
                rebuilt_map,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
                freeze=True,
            )
            for name, expected in MASTER_OUTPUTS.items():
                self.assertEqual(_checkpoint(rebuilt_master / name), expected)
            for name, expected in MAP_OUTPUTS.items():
                self.assertEqual(_checkpoint(rebuilt_map / name), expected)

            validate_construction_master_v7(
                MASTER, definition_path=MASTER_DEFINITION, reproduce=True
            )
            validate_construction_map_v7(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
                reproduce=True,
            )

        with self.assertRaises(ConstructionMasterV7Error):
            write_construction_master_v7(MASTER_DEFINITION, MASTER)
        with self.assertRaises(ConstructionMapV7Error):
            write_construction_map_v7(
                MASTER,
                MAP,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
            )

    def test_active_locks_and_late_arrival_collisions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="construction-v23-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            locked_master = root / "locked-master"
            (root / ".locked-master.lock").write_text("held\n")
            with self.assertRaisesRegex(ConstructionMasterV7Error, "active output lock"):
                write_construction_master_v7(MASTER_DEFINITION, locked_master)

            locked_map = root / "locked-map"
            (root / ".locked-map.lock").write_text("held\n")
            with self.assertRaisesRegex(ConstructionMapV7Error, "active output lock"):
                write_construction_map_v7(
                    MASTER,
                    locked_map,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )

            late_master = root / "late-master"

            def late_master_build(_definition_path, stage):
                for source in MASTER.iterdir():
                    shutil.copy2(source, stage / source.name)
                late_master.mkdir()
                return json.loads((stage / "manifest.json").read_text())

            with patch.object(master_v7, "_build_into", side_effect=late_master_build):
                with self.assertRaisesRegex(
                    ConstructionMasterV7Error, "late output collision"
                ):
                    write_construction_master_v7(MASTER_DEFINITION, late_master)

            late_map = root / "late-map"

            def late_map_build(_master, stage, **_kwargs):
                for source in MAP.iterdir():
                    shutil.copy2(source, stage / source.name)
                late_map.mkdir()
                return json.loads((stage / "manifest.json").read_text())

            with patch.object(map_v7, "_build_into", side_effect=late_map_build):
                with self.assertRaisesRegex(ConstructionMapV7Error, "late output collision"):
                    write_construction_map_v7(
                        MASTER,
                        late_map,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=MAP_DEFINITION,
                    )

    def test_rejected_identity_mutations_and_both_import_layouts(self) -> None:
        master_document = json.loads(MASTER_DEFINITION.read_text())
        map_document = json.loads(MAP_DEFINITION.read_text())
        with tempfile.TemporaryDirectory(prefix="construction-v23-reject-") as temporary:
            root = Path(temporary)
            changed = copy.deepcopy(master_document)
            changed["inputs"]["replacement_release"]["artifact_id"] = (
                "epoch-official-open-seed-v54"
            )
            changed["inputs"]["replacement_release"]["release_id"] = (
                "epoch-official-open-seed-v54"
            )
            rejected = root / "rejected-release.json"
            rejected.write_bytes(_canonical_json(changed))
            with self.assertRaisesRegex(
                ConstructionMasterV7Error, "base or replacement lane changed"
            ):
                validate_definition(rejected)

            changed = copy.deepcopy(master_document)
            changed["scope"]["unique_physical_site_count"] = 346
            bad_sites = root / "invented-sites.json"
            bad_sites.write_bytes(_canonical_json(changed))
            with self.assertRaisesRegex(
                ConstructionMasterV7Error, "identity or scope changed"
            ):
                validate_definition(bad_sites)

            changed_map = copy.deepcopy(map_document)
            changed_map["scope"]["unique_physical_site_count"] = 280
            bad_map = root / "invented-map-sites.json"
            bad_map.write_bytes(_canonical_json(changed_map))
            with self.assertRaisesRegex(ConstructionMapV7Error, "identity or scope changed"):
                validate_map_definition_v7(
                    bad_map,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                )

        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = (
                    "from pathlib import Path; "
                    f"from {package}.construction_master_v7 import "
                    "validate_construction_master_v7; "
                    f"from {package}.construction_map_v7 import "
                    "validate_construction_map_v7; "
                    f"master=Path({str(MASTER)!r}); "
                    f"master_definition=Path({str(MASTER_DEFINITION)!r}); "
                    f"map_dir=Path({str(MAP)!r}); "
                    f"map_definition=Path({str(MAP_DEFINITION)!r}); "
                    "validate_construction_master_v7(master, "
                    "definition_path=master_definition, reproduce=False); "
                    "validate_construction_map_v7(map_dir, master_directory=master, "
                    "master_definition_path=master_definition, "
                    "map_definition_path=map_definition, reproduce=False)"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
