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

from datacenter_atlas import construction_map_v6 as map_v6
from datacenter_atlas import construction_master_v6 as master_v6
from datacenter_atlas.construction_map_v6 import (
    ConstructionMapV6Error,
    validate_construction_map_v6,
    validate_map_definition_v6,
    write_construction_map_v6,
)
from datacenter_atlas.construction_master_v6 import (
    ConstructionMasterV6Error,
    validate_construction_master_v6,
    validate_definition,
    write_construction_master_v6,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v22.json"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v22.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v22"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v22"
V21_MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v21.json"
V21_MASTER = ROOT / "construction_master/2026-07-20-public-open-v21"
V21_MAP = ROOT / "construction_maps/2026-07-20-public-open-v21"
V49_RELEASE = ROOT / "releases/2026-07-20-open-seed-v49"

SOURCE_PINS = {
    MASTER_DEFINITION: "6a66eb3698d15c428d6196e46f1f1ceca468bb5180b372c33632d6506684fca7",
    MAP_DEFINITION: "e9da20d5e60351f9dded7becd79927c297af40490b3b0583ba11256c350299e8",
    ROOT / "datacenter_atlas/construction_master_v6.py": "260389903e4bd0b4877251076f6913eb3e5ae197efc1def4e1d0ce1d836558bd",
    ROOT / "datacenter_atlas/construction_map_v6.py": "941bf89f4913f2cfc40859abb16a735f286c3323fc8e8d3811e14d728b96f6df",
    ROOT / "scripts/build_construction_master_v6.py": "fb95052d78b173e3966c08b953fb1a3edf690f49a238961cfbe1d4ec61cd87ef",
    ROOT / "scripts/build_construction_map_v6.py": "f4db9fa4477673173a283d8d106d89fc49578fec31252aa517290a171cabb5c0",
}
V21_PINS = {
    ROOT / "datacenter_atlas/construction_master_v5.py": "1f52ccc0d1436c818f40f4b6ef170e4f225124ee20d905a3d7dda9fd5f4ad82b",
    ROOT / "datacenter_atlas/construction_map_v5.py": "a64ddbcea72743e5f181a5c6ccc45d3812f47bdcce8d575267d54257bd99138f",
    V21_MASTER_DEFINITION: "ca6258e96d72407d8aa24b94e3ac52c7c1f4d6b0c52e722b0f6d36bd2c16843a",
    V21_MASTER / "manifest.json": "9af4215174275908f69f2f04302992be940277350e03924a1dda7fb089bab4f9",
    V21_MAP / "manifest.json": "a2110233083bfef5271225e77a75d2132eedb9d848ee59671c20d26eabd26ba4",
}
V21_MASTER_INVENTORY_SHA256 = "102c3ec48874738a735b83d5d0cb4fe8abd431e779ac3c49aefa1d52e59d55d4"
V21_MAP_INVENTORY_SHA256 = "e1d21541aa0bdf7f56257f468be4850b87457ca1d8f2d092bf99e78f79968889"
V49_PINS = {
    ROOT / "sources/open-seed-2026-07-20-v49.json": (
        62_617,
        "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c",
    ),
    V49_RELEASE / "manifest.json": (
        8_364,
        "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489",
    ),
    V49_RELEASE / "construction_pipeline.csv": (
        434_385,
        "abe17bc0c2d7bfa425e9d28bbe96b2f6e48f7834477d984cab1a9f579493921c",
    ),
    V49_RELEASE / "evidence.csv": (
        135_561,
        "1e8f32a5fe6b129a11cb0fabe3a24b516e4bbc79f46fc6c2ed073d8ff1965c4d",
    ),
}

MASTER_OUTPUTS = {
    "ATTRIBUTION.txt": (5_814, "0207e0551dc1b2d024e09744f81fb374737c20fecfc137099d43813dcd061073"),
    "README.md": (1_349, "11485b868294752d4da7d49b73c6a890837766d6533a3133c55870e6fa7989f3"),
    "construction-master.csv": (
        189_700_597,
        "4f10f10e2eb523df3d130450bb778b68d6aa1d4b15c3ca16d529da20b32a777e",
    ),
    "construction-master.jsonl": (
        325_466_886,
        "b3bb4ff3201a4a2393982002cbc4f2f27f9408bf54952f2990c45d74f0284532",
    ),
    "coverage.json": (8_523, "3c7ebaf3ae82292bbd489c573e3393b552bf1855df3d586c72dfca3eed4b38b1"),
    "manifest.json": (9_694, "a7e96c666b440b53a6fdf8c1f295f2da0a587294abb56d51380bb85a8ac80731"),
    "manifest.sha256": (80, "925d89c52d824ec9b8f6efb1119c8e74ef213ef2878ec6d740c1e2665f659464"),
}
MAP_OUTPUTS = {
    "ATTRIBUTION.txt": (365, "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d"),
    "README.md": (518, "2defdcb888f553c1d4702a1ca149dc5e47e2a2a068b1ef46e5003984673dd698"),
    "construction-map-index.json.gz": (
        6_676_054,
        "cc36082b09a2169aa0b6aeb5334d82fa70a9662381b9f68ecb83aa205593a2f9",
    ),
    "construction-map.html": (
        8_919_016,
        "8c38d89243ec5bfbc88d61221393c37334ae467853f7d7fa20562385f1c66349",
    ),
    "coverage.json": (7_390, "8e9a52561aeba7593824af413c8e546fb657ba22816a31b21286e1d7921d2721"),
    "manifest.json": (2_192, "d0621f88437a7dc1934abe84138ecd8732868f8ecc2a4f02d836d0751746cf85"),
    "manifest.sha256": (80, "0d4268e0ce704e835fb1e437ada029aa2e9d6411fc9de5a8a52339d96d0eb120"),
}
MASTER_INVENTORY_SHA256 = "896b1dd79c2eb36cbab25c13890c11b2c2e6e1a9954c4bd9d384170ede65365d"
MAP_INVENTORY_SHA256 = "9e6c4e0d38963e75c4abf9a02433f98069d684d83bf12bb8e755556a87921bc7"

EXPECTED_COUNTS = {
    "added_replacement_rows": 128,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 327,
    "replacement_rows_with_any_role": 114,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 45,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 75,
    "replacement_rows_with_tenants": 5,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 327,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 447,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_239,
    "unchanged_replacement_rows": 199,
}
EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": "28dec13b48e6bbaaca777f6a541361b9e444678865ddfb304cf50e8796d326de",
    "base_replaced_source_record_ids_sha256": "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950",
    "inherited_rows_without_roles_sha256": "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f",
    "replacement_role_projection_sha256": "7f2844ec8a280a653b0534326e241cde7d70f5820d1311ace1c7e291e2ebbba5",
    "replacement_rows_without_roles_sha256": "14639cc37574f0cd8b5ff36c4144be99578aad32d94724cf6763bedd09b4c57e",
    "replacement_source_record_ids_sha256": "2eaa697b647e2add3c949294d8faaa6549d251fe29bc9ab1be1af467bd7063b5",
    "tier_a_arithmetic_projection_sha256": "13065869755ad42156a980678401fd73677970bbfdc7138e83665a25c081ffd5",
}
EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 125,
    "added_replacement_unmapped_source_record_ids_sha256": "8265332869d5c8b70c99d3954719169310ea201acdb32280163a6090efa293fb",
    "default_visible_rows": 6_481,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 201, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 82,
    "mapped_rows": 108_975,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109_239,
    "unmapped_rows": 264,
    "unmapped_source_record_ids_sha256": "86f2008910c4dc0fe092dba392eaa2f650c266965e86b574b99ee2a5d1170dad",
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


class FrozenConstructionMasterV22Tests(unittest.TestCase):
    def test_exact_sources_outputs_inventory_and_frozen_modes(self) -> None:
        for path, digest in {**SOURCE_PINS, **V21_PINS}.items():
            with self.subTest(path=path):
                self.assertEqual(_sha256(path), digest)
        self.assertEqual(_inventory_sha256(V21_MASTER), V21_MASTER_INVENTORY_SHA256)
        self.assertEqual(_inventory_sha256(V21_MAP), V21_MAP_INVENTORY_SHA256)
        for path, expected in V49_PINS.items():
            self.assertEqual(_checkpoint(path), expected)
        self.assertEqual(stat.S_IMODE(V49_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in V49_RELEASE.iterdir()
            )
        )

        self.assertEqual(set(MASTER_OUTPUTS), master_v6.BUNDLE_FILES)
        self.assertEqual(set(MAP_OUTPUTS), map_v6.BUNDLE_FILES)
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

    def test_lineage_changes_only_from_v21_replacement_to_accepted_v49(self) -> None:
        old = json.loads(V21_MASTER_DEFINITION.read_text())
        new = json.loads(MASTER_DEFINITION.read_text())
        self.assertEqual(old["inputs"]["base_master"], new["inputs"]["base_master"])
        self.assertEqual(
            old["inputs"]["satellite_recovery_acceptance"],
            new["inputs"]["satellite_recovery_acceptance"],
        )
        self.assertEqual(old["scope"], new["scope"])
        self.assertEqual(
            set(new["inputs"]),
            {"base_master", "replacement_release", "satellite_recovery_acceptance"},
        )
        replacement = new["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v49")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v49")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"], V49_PINS[V49_RELEASE / "manifest.json"][1]
        )
        serialized = "".join(
            path.read_text()
            for path in (
                MASTER_DEFINITION,
                MAP_DEFINITION,
                ROOT / "datacenter_atlas/construction_master_v6.py",
                ROOT / "datacenter_atlas/construction_map_v6.py",
            )
        )
        for marker in (
            "public-open-v20",
            "open-seed-v48",
            "open-seed-v46",
            "open-seed-v45",
            "federated_indexes/",
            "coverage-audit-",
            "current-coverage-",
        ):
            self.assertNotIn(marker, serialized)

    def test_master_arithmetic_roles_capacity_and_satellite_boundaries(self) -> None:
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
        self.assertEqual(coverage["replacement"], {
            "added_rows": 128,
            "base_artifact_id": "epoch-official-open-seed-v33",
            "base_rows_replaced": 199,
            "publication_contract_version": 4,
            "replacement_artifact_id": "epoch-official-open-seed-v49",
            "replacement_rows": 327,
            "unchanged_source_record_ids": 199,
        })
        self.assertEqual(coverage["role_counts"], {
            "rows_with_any_role": 114,
            "rows_with_contract_marker": 327,
            "rows_with_source_role_tags": 75,
            "with_core_role": {
                "customers": 1,
                "operator": 45,
                "owner": 47,
                "tenants": 5,
                "users": 36,
            },
        })
        self.assertEqual(
            coverage["row_counts"]["by_tier"],
            {"A": 447, "B": 6_298, "C": 102_494},
        )
        self.assertEqual(coverage["row_counts"]["total"], 109_239)
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["candidate_or_review_rows_promoted"])
        self.assertFalse(coverage["scope"]["structural_or_cv_rows_in_construction_arithmetic"])

        with (V49_RELEASE / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            source_rows = {row["entity_id"]: row for row in csv.DictReader(source)}
        self.assertEqual(len(source_rows), 327)
        sentinel_rows = []
        with (MASTER / "construction-master.jsonl").open("rb") as source:
            for line_number, raw in enumerate(source, start=1):
                row = json.loads(raw)
                if line_number <= 327:
                    source_row = source_rows[row["source"]["record_id"]]
                    capacities = json.loads(source_row["capacity_estimates_json"])
                    expected_capacity, expected_annual, expected_pue = (
                        master_v6.legacy._capacity_split(capacities)
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

        with (V21_MASTER / "construction-master.jsonl").open("rb") as old, (
            MASTER / "construction-master.jsonl"
        ).open("rb") as new:
            for _ in range(313):
                next(old)
            for _ in range(327):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

    def test_map_projection_and_v21_mapped_identity_set_are_exact(self) -> None:
        definition = validate_map_definition_v6(
            MAP_DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(definition["expected_projection"], EXPECTED_PROJECTION)
        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(coverage["counts"], {
            "mapped_observation_rows": 108_975,
            "mapped_replacement_rows": 82,
            "mapped_rows_with_any_role": 66,
            "master_observation_rows": 109_239,
            "unique_physical_site_count": None,
            "unmapped_observation_rows": 264,
        })
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertTrue(coverage["scope"]["map_rows_are_observations_not_unique_sites"])
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])

        old_index = _map_index(V21_MAP)
        new_index = _map_index(MAP)
        old_record_index = old_index["fields"].index("source_record_id")
        new_record_index = new_index["fields"].index("source_record_id")
        self.assertEqual(
            {row[old_record_index] for row in old_index["rows"]},
            {row[new_record_index] for row in new_index["rows"]},
        )
        artifact_index = new_index["fields"].index("source_artifact_id")
        self.assertEqual(
            sum(
                row[artifact_index] == "epoch-official-open-seed-v49"
                for row in new_index["rows"]
            ),
            82,
        )

    def test_offline_rebuild_is_byte_exact_and_refuses_existing_outputs(self) -> None:
        original_checkpoint = master_v6._checkpoint_spec

        def guarded_checkpoint(package_root, spec, label):
            rendered = str(spec.get("path", ""))
            for marker in ("public-open-v20", "open-seed-v48", "open-seed-v46"):
                self.assertNotIn(marker, rendered)
            return original_checkpoint(package_root, spec, label)

        blocked = AssertionError("v22 construction build attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-v22-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            master_v6, "_checkpoint_spec", side_effect=guarded_checkpoint
        ), patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            root = Path(temporary)
            rebuilt_master = root / "master"
            rebuilt_map = root / "map"
            write_construction_master_v6(MASTER_DEFINITION, rebuilt_master, freeze=True)
            write_construction_map_v6(
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

        validate_construction_master_v6(
            MASTER, definition_path=MASTER_DEFINITION, reproduce=False
        )
        validate_construction_map_v6(
            MAP,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
            map_definition_path=MAP_DEFINITION,
            reproduce=False,
        )
        with self.assertRaises(ConstructionMasterV6Error):
            write_construction_master_v6(MASTER_DEFINITION, MASTER)
        with self.assertRaises(ConstructionMapV6Error):
            write_construction_map_v6(
                MASTER,
                MAP,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
            )

    def test_active_locks_and_late_arrival_collisions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="construction-v22-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            locked_master = root / "locked-master"
            (root / ".locked-master.lock").write_text("held\n")
            with self.assertRaisesRegex(ConstructionMasterV6Error, "active output lock"):
                write_construction_master_v6(MASTER_DEFINITION, locked_master)

            locked_map = root / "locked-map"
            (root / ".locked-map.lock").write_text("held\n")
            with self.assertRaisesRegex(ConstructionMapV6Error, "active output lock"):
                write_construction_map_v6(
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

            with patch.object(master_v6, "_build_into", side_effect=late_master_build):
                with self.assertRaisesRegex(
                    ConstructionMasterV6Error, "late output collision"
                ):
                    write_construction_master_v6(MASTER_DEFINITION, late_master)

            late_map = root / "late-map"

            def late_map_build(_master, stage, **_kwargs):
                for source in MAP.iterdir():
                    shutil.copy2(source, stage / source.name)
                late_map.mkdir()
                return json.loads((stage / "manifest.json").read_text())

            with patch.object(map_v6, "_build_into", side_effect=late_map_build):
                with self.assertRaisesRegex(ConstructionMapV6Error, "late output collision"):
                    write_construction_map_v6(
                        MASTER,
                        late_map,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=MAP_DEFINITION,
                    )

    def test_rejected_identities_and_both_import_layouts(self) -> None:
        master_document = json.loads(MASTER_DEFINITION.read_text())
        map_document = json.loads(MAP_DEFINITION.read_text())
        with tempfile.TemporaryDirectory(prefix="construction-v22-reject-") as temporary:
            root = Path(temporary)
            for rejected in (
                "epoch-official-open-seed-v48",
                "epoch-official-open-seed-v46",
                "epoch-official-open-seed-v45",
            ):
                changed = copy.deepcopy(master_document)
                changed["inputs"]["replacement_release"]["artifact_id"] = rejected
                changed["inputs"]["replacement_release"]["release_id"] = rejected
                path = root / f"{rejected}.json"
                path.write_bytes(_canonical_json(changed))
                with self.assertRaisesRegex(
                    ConstructionMasterV6Error, "base or replacement lane changed"
                ):
                    validate_definition(path)

            changed = copy.deepcopy(master_document)
            changed["master_id"] = "2026-07-20-public-open-v20"
            bad_master = root / "rejected-master.json"
            bad_master.write_bytes(_canonical_json(changed))
            with self.assertRaisesRegex(
                ConstructionMasterV6Error, "identity or scope changed"
            ):
                validate_definition(bad_master)

            changed_map = copy.deepcopy(map_document)
            changed_map["map_id"] = "2026-07-20-public-open-v20-construction-map-v2"
            bad_map = root / "rejected-map.json"
            bad_map.write_bytes(_canonical_json(changed_map))
            with self.assertRaisesRegex(ConstructionMapV6Error, "identity or scope changed"):
                validate_map_definition_v6(
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
                    f"from {package}.construction_master_v6 import "
                    "validate_construction_master_v6; "
                    f"from {package}.construction_map_v6 import "
                    "validate_construction_map_v6; "
                    f"master=Path({str(MASTER)!r}); "
                    f"master_definition=Path({str(MASTER_DEFINITION)!r}); "
                    f"map_dir=Path({str(MAP)!r}); "
                    f"map_definition=Path({str(MAP_DEFINITION)!r}); "
                    "validate_construction_master_v6(master, "
                    "definition_path=master_definition, reproduce=False); "
                    "validate_construction_map_v6(map_dir, master_directory=master, "
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
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
