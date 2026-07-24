from __future__ import annotations

import copy
import gzip
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_map_v5 as map_v5
from datacenter_atlas import construction_master_v5 as master_v5
from datacenter_atlas.construction_map_v5 import (
    ConstructionMapV5Error,
    validate_construction_map_v5,
    validate_map_definition_v5,
    write_construction_map_v5,
)
from datacenter_atlas.construction_master_v5 import (
    ConstructionMasterV5Error,
    validate_construction_master_v5,
    validate_definition,
    write_construction_master_v5,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v21.json"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v21.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v21"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v21"
V17_MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v17.json"
V17_MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v17.json"
V17_MASTER = ROOT / "construction_master/2026-07-20-public-open-v17"
V17_MAP = ROOT / "construction_maps/2026-07-20-public-open-v17"
V47_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v47.json"
V47_RELEASE = ROOT / "releases/2026-07-20-open-seed-v47"

MASTER_DEFINITION_SHA256 = "ca6258e96d72407d8aa24b94e3ac52c7c1f4d6b0c52e722b0f6d36bd2c16843a"
MAP_DEFINITION_SHA256 = "72e99c9a1734375e02ed8a4e31a975cfaaa1c9518267466d514b39ba83df78b5"
MASTER_MODULE_SHA256 = "1f52ccc0d1436c818f40f4b6ef170e4f225124ee20d905a3d7dda9fd5f4ad82b"
MAP_MODULE_SHA256 = "a64ddbcea72743e5f181a5c6ccc45d3812f47bdcce8d575267d54257bd99138f"
MASTER_SCRIPT_SHA256 = "f2773c03ecbe3e2b700bede79101bdf4c5ab42a4d861b555658ca7eaba347726"
MAP_SCRIPT_SHA256 = "4ab58bb2169e3dde61efec278c960d925b79391e6986ee42dc7c578b4fe68aef"
MASTER_MANIFEST_SHA256 = "9af4215174275908f69f2f04302992be940277350e03924a1dda7fb089bab4f9"
MAP_MANIFEST_SHA256 = "a2110233083bfef5271225e77a75d2132eedb9d848ee59671c20d26eabd26ba4"
MASTER_INVENTORY_SHA256 = "102c3ec48874738a735b83d5d0cb4fe8abd431e779ac3c49aefa1d52e59d55d4"
MAP_INVENTORY_SHA256 = "e1d21541aa0bdf7f56257f468be4850b87457ca1d8f2d092bf99e78f79968889"

MASTER_OUTPUTS = {
    "ATTRIBUTION.txt": (5_814, "cbf69ba98003255bfb472e11c55ac1b340f61ca07d02fe22d29e30e121f6add4"),
    "README.md": (1_349, "7206106503d85b36a690acd52521b02c132e1b9e42dbf56be67804b164ddd151"),
    "construction-master.csv": (
        189_666_639,
        "6272bed8a8bae9a78399e86bfc7e545c9d81a8964b3c641fe672953b90b5d949",
    ),
    "construction-master.jsonl": (
        325_414_664,
        "c609c38596dfee302a627804eb53803ffbb55c4aa2ee6ac8c0a8aee6c85f8bd5",
    ),
    "coverage.json": (8_523, "cc6288cd72eb2463a4f3bcf141eebbdfd7e56bad9c46334b5cefc54d0cae8013"),
    "manifest.json": (9_694, MASTER_MANIFEST_SHA256),
    "manifest.sha256": (80, "01c67c1eee662015a23c24aabf0bf357604a3170ba22a780499e9a08e213fee8"),
}
MAP_OUTPUTS = {
    "ATTRIBUTION.txt": (365, "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d"),
    "README.md": (518, "c415a679c410978a9f0b07709b4463f06c54ecbdffd1b9c5db1403dd35c07de1"),
    "construction-map-index.json.gz": (
        6_676_048,
        "66c45519195e4b37533825ecab2b1e8d1c5f93be053d49bb70a7677e4ca7697a",
    ),
    "construction-map.html": (
        8_919_008,
        "8d33fc3966cdf36db5b74be36ada97117d23fc9b90248fcd797919e168850341",
    ),
    "coverage.json": (7_390, "2543e3237acdd44b6c736ffc5142cdd8b2e345abe2e89f62d1d04db5f2f6566e"),
    "manifest.json": (2_192, MAP_MANIFEST_SHA256),
    "manifest.sha256": (80, "8240c29ac3c8ac88ab3ef603ca65db9018453f9509c4e35ec92ce888dc428d48"),
}

V17_PINS = {
    "datacenter_atlas/construction_master_v3.py": "f28516080627a597a56363b1570a318a085aa1cee085c5b30cc2b42b56bd211b",
    "datacenter_atlas/construction_map_v3.py": "772eecbf6770e7ecad22a1b5d6f265e15ffee39276d1e3ab5d40a098f9a84fb6",
    "sources/construction-master-2026-07-20-public-open-v17.json": "856da5d183e176bd7b2573c9cd8676976effb63b10be8dcff84fd993d385ce19",
    "sources/construction-map-2026-07-20-public-open-v17.json": "1e0c00892932e5e1077acbc018a98785f0b85b1b565d9adc6fe3126c62d3c806",
}
V17_MASTER_MANIFEST_SHA256 = "847b0aa6ae51bf6b12d1e9215e1b265c40bd4d84edee4fdf1d596d029b16ffe9"
V17_MAP_MANIFEST_SHA256 = "5e57250b6765838ee9ae4e250b92a11e65b077307a2156c047c636752fe3e3c4"
V17_MASTER_INVENTORY_SHA256 = "494bfd5051d08b0b337bd1e42508fa76752c561c9ee162976ac772c922b90b12"
V17_MAP_INVENTORY_SHA256 = "c39d99379548800cb83cac45d1e419cb1349e98ff4e1340dfe87795aa089800e"

V47_PINS = {
    "sources/open-seed-2026-07-20-v47.json": (
        59_727,
        "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2",
    ),
    "releases/2026-07-20-open-seed-v47/manifest.json": (
        8_024,
        "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1",
    ),
    "releases/2026-07-20-open-seed-v47/construction_pipeline.csv": (
        416_455,
        "c833d71f2fc082ef1e6de0533aa7589caf6c89e9ad3415015d9b0f57d66d89ec",
    ),
    "releases/2026-07-20-open-seed-v47/evidence.csv": (
        129_940,
        "fd4eefd7690b753b88c750dea51289068646b4112adab3d7df0e5c7a024d7a79",
    ),
}

EXPECTED_COUNTS = {
    "added_replacement_rows": 114,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 313,
    "replacement_rows_with_any_role": 108,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 40,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 69,
    "replacement_rows_with_tenants": 5,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 313,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 433,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_225,
    "unchanged_replacement_rows": 199,
}
EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": "4ea68913622eb9ed69a1334a3afbf953cee5ec3e540542aa4bcd43742c03f437",
    "base_replaced_source_record_ids_sha256": "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950",
    "inherited_rows_without_roles_sha256": "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f",
    "replacement_role_projection_sha256": "b45f8287817d4dab19c28f4461c958e6ef9e19479f683ccd57bbb88b7fcaa504",
    "replacement_rows_without_roles_sha256": "04476231461b7624fd26b1824019c3db9c94a9531d815b992d375c5d44a64b3d",
    "replacement_source_record_ids_sha256": "47cf4c0ad53a059a1799a8ebf53c0c874c216c4c0263c890a8a0ca9a8911e33c",
    "tier_a_arithmetic_projection_sha256": "2f888d1758d25e6597cb5ba22c155e9717697abeeb6a39b275c1d0f534118a93",
}
EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 111,
    "added_replacement_unmapped_source_record_ids_sha256": "b07d80ec7cb9190f52ed480ac16eb7966863eadca3bad20befef77186d0cacc1",
    "default_visible_rows": 6_481,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 201, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 82,
    "mapped_rows": 108_975,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109_225,
    "unmapped_rows": 250,
    "unmapped_source_record_ids_sha256": "bb3f67b3b8c3e1c3510a1cfd78c71f8ea8444256e270dea364186d397c164ed9",
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


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _map_index(directory: Path) -> dict:
    return json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )


class FrozenConstructionMasterV21Tests(unittest.TestCase):
    def test_exact_definitions_carriers_outputs_and_frozen_modes(self) -> None:
        source_pins = {
            MASTER_DEFINITION: MASTER_DEFINITION_SHA256,
            MAP_DEFINITION: MAP_DEFINITION_SHA256,
            ROOT / "datacenter_atlas/construction_master_v5.py": MASTER_MODULE_SHA256,
            ROOT / "datacenter_atlas/construction_map_v5.py": MAP_MODULE_SHA256,
            ROOT / "scripts/build_construction_master_v5.py": MASTER_SCRIPT_SHA256,
            ROOT / "scripts/build_construction_map_v5.py": MAP_SCRIPT_SHA256,
        }
        for path, digest in source_pins.items():
            with self.subTest(path=path):
                self.assertEqual(_sha256(path), digest)

        self.assertEqual(set(MASTER_OUTPUTS), master_v5.BUNDLE_FILES)
        self.assertEqual(set(MAP_OUTPUTS), map_v5.BUNDLE_FILES)
        self.assertEqual(_inventory_sha256(MASTER), MASTER_INVENTORY_SHA256)
        self.assertEqual(_inventory_sha256(MAP), MAP_INVENTORY_SHA256)
        for directory, checkpoints in ((MASTER, MASTER_OUTPUTS), (MAP, MAP_OUTPUTS)):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)
            for name, (size, digest) in checkpoints.items():
                path = directory / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, _sha256(path)), (size, digest))

    def test_accepted_v17_and_v47_are_pinned_and_only_input_lane_changed(self) -> None:
        for relative, digest in V17_PINS.items():
            self.assertEqual(_sha256(ROOT / relative), digest, relative)
        self.assertEqual(_sha256(V17_MASTER / "manifest.json"), V17_MASTER_MANIFEST_SHA256)
        self.assertEqual(_sha256(V17_MAP / "manifest.json"), V17_MAP_MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(V17_MASTER), V17_MASTER_INVENTORY_SHA256)
        self.assertEqual(_inventory_sha256(V17_MAP), V17_MAP_INVENTORY_SHA256)
        for relative, expected in V47_PINS.items():
            path = ROOT / relative
            self.assertEqual((path.stat().st_size, _sha256(path)), expected, relative)
        self.assertEqual(stat.S_IMODE(V47_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in V47_RELEASE.iterdir()
            )
        )

        old = json.loads(V17_MASTER_DEFINITION.read_text())
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
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v47")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v47")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"], V47_PINS[
                "releases/2026-07-20-open-seed-v47/manifest.json"
            ][1]
        )
        serialized = MASTER_DEFINITION.read_text() + MAP_DEFINITION.read_text()
        serialized += (ROOT / "datacenter_atlas/construction_master_v5.py").read_text()
        serialized += (ROOT / "datacenter_atlas/construction_map_v5.py").read_text()
        for marker in (
            "public-open-v20",
            "open-seed-v46",
            "open-seed-v45",
            "federated_indexes/",
            "coverage-audit-",
            "current-coverage-",
        ):
            self.assertNotIn(marker, serialized)

    def test_master_arithmetic_roles_recovery_and_inherited_tail_are_exact(self) -> None:
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
        self.assertEqual(context["recovery"]["control_plane_bytes"], 15_313)

        coverage = json.loads((MASTER / "coverage.json").read_text())
        self.assertEqual(coverage["replacement"], {
            "added_rows": 114,
            "base_artifact_id": "epoch-official-open-seed-v33",
            "base_rows_replaced": 199,
            "publication_contract_version": 4,
            "replacement_artifact_id": "epoch-official-open-seed-v47",
            "replacement_rows": 313,
            "unchanged_source_record_ids": 199,
        })
        self.assertEqual(coverage["role_counts"], {
            "rows_with_any_role": 108,
            "rows_with_contract_marker": 313,
            "rows_with_source_role_tags": 69,
            "with_core_role": {
                "customers": 1,
                "operator": 40,
                "owner": 47,
                "tenants": 5,
                "users": 36,
            },
        })
        self.assertEqual(
            coverage["row_counts"]["by_tier"],
            {"A": 433, "B": 6_298, "C": 102_494},
        )
        self.assertEqual(coverage["row_counts"]["total"], 109_225)
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])

        with (V17_MASTER / "construction-master.jsonl").open("rb") as old, (
            MASTER / "construction-master.jsonl"
        ).open("rb") as new:
            for _ in range(299):
                next(old)
            for _ in range(313):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

    def test_map_projection_and_v17_mapped_identity_set_are_exact(self) -> None:
        definition = validate_map_definition_v5(
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
            "master_observation_rows": 109_225,
            "unique_physical_site_count": None,
            "unmapped_observation_rows": 250,
        })
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertTrue(coverage["scope"]["map_rows_are_observations_not_unique_sites"])
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])

        old_index = _map_index(V17_MAP)
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
                row[artifact_index] == "epoch-official-open-seed-v47"
                for row in new_index["rows"]
            ),
            82,
        )

    def test_offline_rebuilds_are_byte_exact_and_refuse_collisions(self) -> None:
        original_checkpoint = master_v5._checkpoint_spec

        def guarded_checkpoint(package_root, spec, label):
            rendered = str(spec.get("path", ""))
            for marker in ("public-open-v20", "open-seed-v46", "open-seed-v45"):
                self.assertNotIn(marker, rendered)
            return original_checkpoint(package_root, spec, label)

        blocked = AssertionError("v21 construction build attempted network access")
        with tempfile.TemporaryDirectory(
            prefix="construction-v21-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            master_v5, "_checkpoint_spec", side_effect=guarded_checkpoint
        ), patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            root = Path(temporary)
            masters = (root / "master-first", root / "master-second")
            maps = (root / "map-first", root / "map-second")
            for output in masters:
                write_construction_master_v5(MASTER_DEFINITION, output, freeze=True)
            for output in maps:
                write_construction_map_v5(
                    MASTER,
                    output,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                    freeze=True,
                )
            for name in sorted(master_v5.BUNDLE_FILES):
                self.assertEqual((masters[0] / name).read_bytes(), (masters[1] / name).read_bytes())
                self.assertEqual((masters[0] / name).read_bytes(), (MASTER / name).read_bytes())
            for name in sorted(map_v5.BUNDLE_FILES):
                self.assertEqual((maps[0] / name).read_bytes(), (maps[1] / name).read_bytes())
                self.assertEqual((maps[0] / name).read_bytes(), (MAP / name).read_bytes())

        validate_construction_master_v5(
            MASTER, definition_path=MASTER_DEFINITION, reproduce=False
        )
        validate_construction_map_v5(
            MAP,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
            map_definition_path=MAP_DEFINITION,
            reproduce=False,
        )
        with self.assertRaises(ConstructionMasterV5Error):
            write_construction_master_v5(MASTER_DEFINITION, MASTER)
        with self.assertRaises(ConstructionMapV5Error):
            write_construction_map_v5(
                MASTER,
                MAP,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=MAP_DEFINITION,
            )

    def test_rejected_identity_mutations_and_both_import_layouts(self) -> None:
        master_document = json.loads(MASTER_DEFINITION.read_text())
        map_document = json.loads(MAP_DEFINITION.read_text())
        with tempfile.TemporaryDirectory(prefix="construction-v21-reject-") as temporary:
            root = Path(temporary)
            for rejected in ("epoch-official-open-seed-v45", "epoch-official-open-seed-v46"):
                changed = copy.deepcopy(master_document)
                changed["inputs"]["replacement_release"]["artifact_id"] = rejected
                changed["inputs"]["replacement_release"]["release_id"] = rejected
                path = root / f"{rejected}.json"
                path.write_bytes(_canonical_json(changed))
                with self.assertRaisesRegex(
                    ConstructionMasterV5Error, "base or replacement lane changed"
                ):
                    validate_definition(path)

            changed = copy.deepcopy(master_document)
            changed["master_id"] = "2026-07-20-public-open-v20"
            bad_master = root / "rejected-master.json"
            bad_master.write_bytes(_canonical_json(changed))
            with self.assertRaisesRegex(
                ConstructionMasterV5Error, "identity or scope changed"
            ):
                validate_definition(bad_master)

            changed_map = copy.deepcopy(map_document)
            changed_map["map_id"] = "2026-07-20-public-open-v20-construction-map-v2"
            bad_map = root / "rejected-map.json"
            bad_map.write_bytes(_canonical_json(changed_map))
            with self.assertRaisesRegex(
                ConstructionMapV5Error, "identity or scope changed"
            ):
                validate_map_definition_v5(
                    bad_map,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                )

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.construction_master_v5 import "
            "validate_construction_master_v5; "
            "from datacenter_atlas.construction_map_v5 import "
            "validate_construction_map_v5; "
            f"master=Path({str(MASTER)!r}); "
            f"master_definition=Path({str(MASTER_DEFINITION)!r}); "
            f"map_dir=Path({str(MAP)!r}); "
            f"map_definition=Path({str(MAP_DEFINITION)!r}); "
            "validate_construction_master_v5(master, "
            "definition_path=master_definition, reproduce=False); "
            "validate_construction_map_v5(map_dir, master_directory=master, "
            "master_definition_path=master_definition, "
            "map_definition_path=map_definition, reproduce=False)"
        )
        for cwd in (ROOT, WORKSPACE):
            with self.subTest(cwd=cwd):
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
