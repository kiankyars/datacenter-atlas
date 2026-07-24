from __future__ import annotations

from contextlib import ExitStack
import copy
import gzip
import hashlib
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

from datacenter_atlas import construction_map_v7 as map_v7
from datacenter_atlas import construction_map_v8 as map_v8
from datacenter_atlas.construction_map_v8 import (
    ConstructionMapV8Error,
    validate_construction_map_v8,
    validate_map_definition_v8,
    write_construction_map_v8,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v24.json"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v24"
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v24.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v24"
V23_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v23.json"
V23_MAP = ROOT / "construction_maps/2026-07-20-public-open-v23"
V23_MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-20-public-open-v23.json"
)
V23_MASTER = ROOT / "construction_master/2026-07-20-public-open-v23"

GENERATED_AT = "2026-07-20T23:05:01Z"
PAIX_ID = "be826096-5b00-5454-a880-cb133fd9bdd5"
PENTAPOINT_ID = "a75eaf2b-790f-5266-be60-3f2bafee2eeb"
ADDED_MAPPED_IDS = {PAIX_ID, PENTAPOINT_ID}
FORBIDDEN = (
    "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json",
    "curated:google-bermuda-hundred-chesterfield-campus",
    "curated-official-2026-07-20-aligned-iad06-frederick-topout.json",
    "curated:aligned-quantum-frederick-campus:iad06",
)

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 144,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "7625e430e7f12e6a35b99eb74231b98f21a33405358276182916d27f876625bb"
    ),
    "default_visible_rows": 6_486,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 206, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 87,
    "mapped_rows": 108_980,
    "mapped_rows_with_any_role": 68,
    "master_rows": 109_260,
    "unmapped_rows": 280,
    "unmapped_source_record_ids_sha256": (
        "0f21abbeab1f614b8a170def2077be4eea5953611838d3f469c4fda9eb6a493e"
    ),
}

FILE_PINS = {
    DEFINITION: (
        2_441,
        "59bf6d020cb308b7d2ad1148f39c6794fc7df5697a0f19a0149448e56e1b99cd",
    ),
    V23_DEFINITION: (
        2_441,
        "6022402312649301dc921981bc89bb63801b456f9bbcb7915bb9dc475cbdcf79",
    ),
    MASTER_DEFINITION: (
        5_657,
        "5472a417b58547027e039df6b72bd8d4ee84bcfb186424781422f04e1c9736c0",
    ),
    MASTER / "construction-master.jsonl": (
        325_543_337,
        "1ce3219e30b9c1ddbdd54167d879244f46a04f025f283214ba85976ccfbfe94c",
    ),
    MASTER / "manifest.json": (
        9_719,
        "61f8c11ce3c782d63d02539b58ebfc2dd4f3e1c9f0957fe5ccda2bc5a5216705",
    ),
    V23_MASTER_DEFINITION: (
        5_657,
        "6a72a8c44808ad6d276fed6141b15ee91e5708b5ff95f91aaf0c011e0c69d438",
    ),
    ROOT / "datacenter_atlas/construction_map_v7.py": (
        2_749,
        "053995421f2e581ba49ea5bf89fd539afce527b718c643ea8e1074204a7586be",
    ),
    ROOT / "datacenter_atlas/construction_map_v8.py": (
        3_039,
        "7b91d74faf58eac1e1ab5c9717ab4fea79a099283389fe0650aae15aebe4642a",
    ),
    ROOT / "construction_map_v8.py": (
        233,
        "78f9a67954cb548c201cb4903bb18b0f5309eb987c78fe8e98b7c43626451326",
    ),
    ROOT / "scripts/build_construction_map_v8.py": (
        2_012,
        "a4f21d0e0a9bb79780ea5715df0a1f1e2722c2662614cbec62d9a2eb1c404d1b",
    ),
}

OUTPUTS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "15585d4b7bfd7f6226ea1cd03b3c390395dfa08b7cf6010a3777055986787a2b",
    ),
    "construction-map-index.json.gz": (
        6_677_059,
        "c403c44c0ecb2fb784e6f89ff3b29f3d2d5c758c4ff4ee4a295d7b6d494f5b4b",
    ),
    "construction-map.html": (
        8_920_356,
        "1b60d7bcae517fc7c11ffa4c841d30a6467489bbe5d0e39b16665e7b2bbbff4e",
    ),
    "coverage.json": (
        7_435,
        "6528124968bcecbdc62ad3213f5128842d2614fa43fb1bde4c4d43d53833d7b4",
    ),
    "manifest.json": (
        2_192,
        "2b2c2298a550c07a507c7083326f6e062c884a81f6e32da553d1f35c0a7b314b",
    ),
    "manifest.sha256": (
        80,
        "c3bb854581288a6dbffbf131c9f5bbb6523723d29dcdf621ee8fe175b5cd6d26",
    ),
}

TREE_SHA256 = "a1f38b01ae1058aea9c502cb9b2d58881e8613d6e01a777af8fd5579f81dd8f4"
V23_MAP_TREE_SHA256 = "377677b9d7d5e750af8b4312086f1320ab09258baa4a92f44208193ccc3ad326"
V23_MASTER_TREE_SHA256 = (
    "37100ba7e612e81b7aecc8516224a75d67f70af41ac3b9991b18912238a0f077"
)
MASTER_TREE_SHA256 = "ee8d3994db5576363ae8bf3c58a990769702781e26d29f97f6775dda8bf95e40"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"bundle contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{path.stat().st_size}\0"
                    f"{sha256(path)}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def index(directory: Path) -> tuple[list[str], list[list[object]]]:
    document = json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )
    return document["fields"], document["rows"]


def by_source_record(directory: Path) -> dict[str, dict[str, object]]:
    fields, rows = index(directory)
    return {
        str(dict(zip(fields, row, strict=True))["source_record_id"]): dict(
            zip(fields, row, strict=True)
        )
        for row in rows
    }


class FrozenConstructionMapV24Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v24 construction map attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_frozen_modes_and_tree_digests(self) -> None:
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(set(OUTPUTS), map_v8.BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertEqual(set(path.name for path in MAP.iterdir()), set(OUTPUTS))
        for name, expected in OUTPUTS.items():
            path = MAP / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(checkpoint(path), expected)
        self.assertEqual(tree_digest(MAP), TREE_SHA256)
        self.assertEqual(tree_digest(V23_MAP), V23_MAP_TREE_SHA256)
        self.assertEqual(tree_digest(V23_MASTER), V23_MASTER_TREE_SHA256)
        self.assertEqual(tree_digest(MASTER), MASTER_TREE_SHA256)

    def test_definition_is_exact_v23_successor_bound_to_master_v24(self) -> None:
        old = json.loads(V23_DEFINITION.read_text())
        new = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(new))
        self.assertEqual(old["definition_role"], new["definition_role"])
        self.assertEqual(old["scope"], new["scope"])
        self.assertEqual(old["template"], new["template"])
        self.assertEqual(new["expected_projection"], EXPECTED_PROJECTION)
        self.assertEqual(new["generated_at"], GENERATED_AT)
        self.assertEqual(
            new["map_id"], "2026-07-20-public-open-v24-construction-map-v2"
        )
        self.assertEqual(
            new["master"],
            {
                "definition": {
                    "bytes": 5_657,
                    "path": "construction-master-2026-07-20-public-open-v24.json",
                    "sha256": FILE_PINS[MASTER_DEFINITION][1],
                },
                "directory": "../construction_master/2026-07-20-public-open-v24",
                "jsonl": {
                    "bytes": FILE_PINS[MASTER / "construction-master.jsonl"][0],
                    "path": "../construction_master/2026-07-20-public-open-v24/construction-master.jsonl",
                    "sha256": FILE_PINS[MASTER / "construction-master.jsonl"][1],
                },
                "manifest": {
                    "bytes": FILE_PINS[MASTER / "manifest.json"][0],
                    "path": "../construction_master/2026-07-20-public-open-v24/manifest.json",
                    "sha256": FILE_PINS[MASTER / "manifest.json"][1],
                },
                "master_id": "2026-07-20-public-open-v24",
            },
        )
        self.assertLess(
            json.loads(MASTER_DEFINITION.read_text())["generated_at"], GENERATED_AT
        )
        validated = validate_map_definition_v8(
            DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(validated, new)

    def test_v23_to_v24_adjacency_and_unmapped_sets_are_exact(self) -> None:
        old_rows = by_source_record(V23_MAP)
        new_rows = by_source_record(MAP)
        self.assertFalse(set(old_rows) - set(new_rows))
        self.assertEqual(set(new_rows) - set(old_rows), ADDED_MAPPED_IDS)
        for record_id in old_rows:
            old = dict(old_rows[record_id])
            new = dict(new_rows[record_id])
            for field in ("row_id", "source_artifact_id", "source_release_id"):
                old.pop(field)
                new.pop(field)
            self.assertEqual(old, new, record_id)

        old_added = map_v7._added_source_record_ids(V23_MASTER_DEFINITION)
        new_added = map_v8._added_source_record_ids(MASTER_DEFINITION)
        self.assertEqual(len(old_added), 147)
        self.assertEqual(len(new_added), 149)
        self.assertEqual(new_added - old_added, ADDED_MAPPED_IDS)
        old_added_unmapped = old_added - set(old_rows)
        new_added_unmapped = new_added - set(new_rows)
        self.assertEqual(old_added_unmapped, new_added_unmapped)
        self.assertEqual(len(new_added_unmapped), 144)
        self.assertEqual(
            map_v8._id_digest(new_added_unmapped),
            EXPECTED_PROJECTION["added_replacement_unmapped_source_record_ids_sha256"],
        )
        self.assertEqual(
            json.loads((V23_MAP / "coverage.json").read_text())["projection"][
                "unmapped_source_record_ids_sha256"
            ],
            EXPECTED_PROJECTION["unmapped_source_record_ids_sha256"],
        )

    def test_new_mapped_rows_coordinates_roles_and_scope_are_exact(self) -> None:
        rows = by_source_record(MAP)
        paix = rows[PAIX_ID]
        pentapoint = rows[PENTAPOINT_ID]
        self.assertEqual(
            (paix["latitude"], paix["longitude"], paix["country_iso_a3"]),
            (14.7213975, -17.4997482, "SEN"),
        )
        self.assertEqual(
            (
                pentapoint["latitude"],
                pentapoint["longitude"],
                pentapoint["country_iso_a3"],
            ),
            (13.7248155, 100.5390396, "THA"),
        )
        self.assertEqual(paix["normalized_status"], "site_control")
        self.assertEqual(pentapoint["normalized_status"], "under_construction")
        self.assertEqual(
            paix["source_role_tags"], {"role:developer": "PAIX Data Centres"}
        )
        self.assertEqual(
            pentapoint["source_role_tags"],
            {
                "role:developer": "PentaPoint Corporation",
                "role:operator": "AIMS Data Center",
            },
        )
        self.assertIsNone(paix["operator"])
        self.assertEqual(pentapoint["operator"], "AIMS Data Center")
        for row in (paix, pentapoint):
            self.assertEqual(row["tier"], "A")
            self.assertFalse(row["review_only"])
            self.assertEqual(row["source_artifact_id"], "epoch-official-open-seed-v56")
            self.assertEqual(row["source_publication_contract_version"], 4)

        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": 108_980,
                "mapped_replacement_rows": 87,
                "mapped_rows_with_any_role": 68,
                "master_observation_rows": 109_260,
                "unique_physical_site_count": None,
                "unmapped_observation_rows": 280,
            },
        )
        self.assertEqual(
            coverage["mapped_counts"]["by_tier"], {"A": 206, "B": 6280, "C": 102494}
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        for key in (
            "atlas_claims_created",
            "construction_arithmetic_recomputed",
            "entity_merges_created",
            "global_completeness_claimed",
        ):
            self.assertFalse(coverage["scope"][key])
        self.assertTrue(
            coverage["scope"]["historical_status_is_not_current_status_claim"]
        )
        self.assertTrue(
            coverage["scope"]["role_values_copied_from_master_without_inference"]
        )
        self.assertTrue(coverage["scope"]["source_role_tags_preserved_opaquely"])

        source_text = DEFINITION.read_text() + MASTER_DEFINITION.read_text()
        source_text += (ROOT / "sources/open-seed-2026-07-20-v56.json").read_text()
        for marker in FORBIDDEN:
            self.assertNotIn(marker, source_text)

    def test_double_offline_reproduction_is_byte_exact(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="construction-map-v24-reproduce-", dir="/private/tmp"
            ) as temporary,
            ExitStack() as stack,
        ):
            self._offline(stack)
            root = Path(temporary)
            for name in ("first", "second"):
                rebuilt = root / name
                write_construction_map_v8(
                    MASTER,
                    rebuilt,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    freeze=True,
                )
                self.assertEqual(tree_digest(rebuilt), TREE_SHA256)
                for filename, expected in OUTPUTS.items():
                    self.assertEqual(checkpoint(rebuilt / filename), expected)
            validate_construction_map_v8(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=DEFINITION,
                reproduce=False,
            )
        for filename, expected in OUTPUTS.items():
            self.assertEqual(checkpoint(MAP / filename), expected)

    def test_existing_lock_late_collision_and_fault_cleanup_fail_closed(self) -> None:
        with self.assertRaisesRegex(ConstructionMapV8Error, "existing output"):
            write_construction_map_v8(
                MASTER,
                MAP,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=DEFINITION,
            )
        with tempfile.TemporaryDirectory(
            prefix="construction-map-v24-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n")
            with self.assertRaisesRegex(ConstructionMapV8Error, "active output lock"):
                write_construction_map_v8(
                    MASTER,
                    locked,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                )
            self.assertEqual(lock.read_text(), "held\n")
            self.assertFalse(locked.exists())

            late = root / "late"

            def late_build(_master: Path, _stage: Path, **_kwargs: object) -> dict:
                late.mkdir()
                return {}

            with (
                patch.object(map_v8, "_build_into", side_effect=late_build),
                patch.object(map_v8, "_validate_static", return_value={}),
            ):
                with self.assertRaisesRegex(
                    ConstructionMapV8Error, "late output collision"
                ):
                    write_construction_map_v8(
                        MASTER,
                        late,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                        freeze=True,
                    )
            self.assertTrue(late.is_dir())
            self.assertFalse((root / ".late.lock").exists())
            self.assertFalse(
                any(".late.stage-" in path.name for path in root.iterdir())
            )

            fault = root / "fault"
            with patch.object(map_v8, "_build_into", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    write_construction_map_v8(
                        MASTER,
                        fault,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                    )
            self.assertFalse(fault.exists())
            self.assertFalse((root / ".fault.lock").exists())
            self.assertFalse(
                any(".fault.stage-" in path.name for path in root.iterdir())
            )

    def test_semantic_mutations_are_rejected(self) -> None:
        document = json.loads(DEFINITION.read_text())
        with tempfile.TemporaryDirectory(
            prefix="construction-map-v24-mutations-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            cases = []
            changed = copy.deepcopy(document)
            changed["map_id"] = "2026-07-20-public-open-v23-construction-map-v2"
            cases.append((changed, "identity or scope changed"))
            changed = copy.deepcopy(document)
            changed["scope"]["unique_physical_site_count"] = 108_980
            cases.append((changed, "identity or scope changed"))
            changed = copy.deepcopy(document)
            changed["expected_projection"]["mapped_rows"] = 108_979
            cases.append((changed, "fixed projection changed: mapped_rows"))
            changed = copy.deepcopy(document)
            changed["master"]["master_id"] = "2026-07-20-public-open-v23"
            cases.append((changed, "map master identity changed"))
            for index_value, (changed, message) in enumerate(cases):
                path = root / f"case-{index_value}.json"
                path.write_bytes(canonical_json(changed))
                with self.assertRaisesRegex(ConstructionMapV8Error, message):
                    validate_map_definition_v8(
                        path,
                        master_directory=MASTER,
                        master_definition_path=MASTER_DEFINITION,
                    )

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.construction_map_v8"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.construction_map_v8"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_construction_map_v8; "
                f"result=validate_construction_map_v8(Path({str(MAP)!r}), "
                f"master_directory=Path({str(MASTER)!r}), "
                f"master_definition_path=Path({str(MASTER_DEFINITION)!r}), "
                f"map_definition_path=Path({str(DEFINITION)!r}), reproduce=False); "
                "assert result['master']['rows']==109260; "
                "assert result['scope']['unique_physical_site_count'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
