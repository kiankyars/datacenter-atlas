from __future__ import annotations

import base64
import builtins
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map import FIELDS as V1_FIELDS
from datacenter_atlas.construction_map_v2 import (
    BUNDLE_FILES,
    FIELDS,
    ConstructionMapV2Error,
    _project_row,
    validate_construction_map_v2,
    validate_map_definition_v2,
    write_construction_map_v2,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v16.json"
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v16.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v16"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v16"
BASE_MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-19-public-open-v14.json"
)
BASE_MASTER = ROOT / "construction_master/2026-07-19-public-open-v14"
BASE_MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-19-public-open-v14.json"
BASE_MAP = ROOT / "construction_maps/2026-07-19-public-open-v14"
V42_DATA = ROOT / "releases/2026-07-20-open-seed-v42/construction_pipeline.csv"
TEMPLATE = ROOT / "web/construction-map-template-v2.html"
MODULE = ROOT / "datacenter_atlas/construction_map_v2.py"

DEFINITION_SHA256 = "cdbcf7f9f71e451ef6a298102866ea6715cec022ab4f1315d61bea682939a0d4"
MODULE_SHA256 = "6f5e15e4bf86db7df31a55e1177057ac27d407ce7012cf8d7b2d1631018afe0b"
MASTER_DEFINITION_SHA256 = (
    "541fddec96e1ef309219ee648d6d9c8fa0e99dbf6db09619d89cb5d05b423be6"
)
MASTER_MANIFEST_SHA256 = (
    "a43846e71f07b4eb9ac10643caf71c907a837537ba1ec994caa70a366e45908f"
)
MASTER_JSONL_SHA256 = (
    "e573deea4314a9edd2148e695489bd0f2cc47fac71530fe09b81b685c678e19c"
)
TEMPLATE_SHA256 = "c05b5831cd0fb85c6b2dda08c5bea2c828c948663c612b1e79ed499a34bcad89"
MANIFEST_SHA256 = "ee8dbdd2c0a050695b739af59ee167fb40edefb4cc8c68261fb36eabc1a29fe2"
BUNDLE_INVENTORY_SHA256 = (
    "5edbc7f2d98e9bcf3ee9f5ceb1ada6ccf6299914203aa2de6c8afb48e06b7f06"
)
OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "a41d92e9c1385672deffc5e3130e4405b34a7bbf560ea8c5fa6ea9c52db95582",
    ),
    "construction-map-index.json.gz": (
        6_675_540,
        "ff83068bbd4070c90617098ee19bbfd6e6c1d435643dd9865b973456785044f4",
    ),
    "construction-map.html": (
        8_918_328,
        "163861725dfea13e13cf57d7b206cd430f2e314b9b554a93bef35f2486e37ebc",
    ),
    "coverage.json": (
        7_342,
        "f293fea7fb94768932da8b3260901c8b7faed01485235e5ad6570cda497a32e1",
    ),
    "manifest.json": (2_192, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "11a5c153317e5dc46f2aab3048a9c0b3eabb1c5daecae900581ca5b92cee2138",
    ),
}
BASE_MAP_DEFINITION_SHA256 = (
    "7ad7320bbbb8d1ae4bef56363177fe904891be9527e35e31eedc9103b1122db9"
)
BASE_MAP_MANIFEST_SHA256 = (
    "85f102967b8a6329c6d4466e61d1773132ee71b92cad05fc014b475eb0ef75f1"
)
BASE_MAP_INVENTORY_SHA256 = (
    "b69c784bd3b9f12c4a0c46cbd56784cc2aa15b332febe98764ebb3f77bfa7681"
)
BASE_MASTER_DEFINITION_SHA256 = (
    "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4"
)
BASE_MASTER_MANIFEST_SHA256 = (
    "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b"
)
BASE_MASTER_INVENTORY_SHA256 = (
    "4b2ce6298788a6af9b5df90c4148b640fafdcb39ad8c0044d35832b8cd3bee60"
)

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 63,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "0fd9aa71b3b3292235f7eba7d694d1609ce5a0a28be5d260d10210f7418446a2"
    ),
    "default_visible_rows": 6_479,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 199, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 80,
    "mapped_rows": 108_973,
    "mapped_rows_with_any_role": 66,
    "master_rows": 109_174,
    "unmapped_rows": 201,
    "unmapped_source_record_ids_sha256": (
        "21d7faba73f192a82cee72f5f6e2f7e64383d7e966f97bcb7ba7b1a0917c5c3e"
    ),
}
BASE_SOURCE_RECORD_IDS_SHA256 = (
    "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
)
V42_SOURCE_RECORD_IDS_SHA256 = (
    "19a28da1b0269404cc81997912a51c8a58e72a44783dba56980b0daa4eba2e16"
)
REJECTED_PATH_FRAGMENTS = (
    "sources/construction-map-2026-07-20-public-open-v15.json",
    "construction_maps/2026-07-20-public-open-v15",
    "sources/construction-master-2026-07-20-public-open-v15.json",
    "construction_master/2026-07-20-public-open-v15",
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
)
REJECTED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        "2026-07-20-public-open-v15",
        "epoch-official-open-seed-v41",
        "2026-07-20-open-seed-v41",
        "967127f07f0e30be989bfbeba2ab7884a20b4ff570357648af8c48652e67c1b5",
        "e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
        "cf8007a718c7b971daffa8608345abb9bed82f1806a1387556c1dca0c1ce7609",
        "1f2c14858b601c60e511afbe0d359cf78fadafe8f8fcdcd0734fdcc7a639fdca",
        "d41e49f2c35dcd986373c7bf396e2f7776664ad6f1cca874251cd9056cf63aa1",
        "6eea9e37b31e5a48440e7f6c4adc2b15e954b76eb3fb53297fea01fb71279b04",
    )
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> tuple[str, dict[str, tuple[int, str]]]:
    digest = hashlib.sha256()
    entries: dict[str, tuple[int, str]] = {}
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        checkpoint = (entry.stat().st_size, _sha256(entry))
        entries[entry.name] = checkpoint
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(checkpoint[1]))
    return digest.hexdigest(), entries


def _id_digest(values: set[str] | list[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _index() -> dict:
    return json.loads(
        gzip.decompress((MAP / "construction-map-index.json.gz").read_bytes())
    )


def _make_writable(directory: Path) -> None:
    directory.chmod(0o755)
    for entry in directory.iterdir():
        if not entry.is_symlink():
            entry.chmod(0o644)


@contextmanager
def _offline_rejected_path_guard():
    originals = {
        "builtin_open": builtins.open,
        "io_open": io.open,
        "os_open": os.open,
        "stat": os.stat,
        "lstat": os.lstat,
        "listdir": os.listdir,
        "scandir": os.scandir,
        "access": os.access,
    }

    def check(kind: str, value: object) -> None:
        if isinstance(value, int):
            return
        try:
            normalized = os.path.abspath(os.fspath(value)).replace(os.sep, "/")
        except TypeError:
            return
        if any(fragment in normalized for fragment in REJECTED_PATH_FRAGMENTS):
            raise AssertionError(f"rejected path access via {kind}: {normalized}")

    def guarded_builtin_open(file: object, *args: object, **kwargs: object):
        check("builtins.open", file)
        return originals["builtin_open"](file, *args, **kwargs)

    def guarded_io_open(file: object, *args: object, **kwargs: object):
        check("io.open", file)
        return originals["io_open"](file, *args, **kwargs)

    def guarded_os_open(path: object, *args: object, **kwargs: object):
        check("os.open", path)
        return originals["os_open"](path, *args, **kwargs)

    def guarded_stat(path: object, *args: object, **kwargs: object):
        check("os.stat", path)
        return originals["stat"](path, *args, **kwargs)

    def guarded_lstat(path: object, *args: object, **kwargs: object):
        check("os.lstat", path)
        return originals["lstat"](path, *args, **kwargs)

    def guarded_listdir(path: object = "."):
        check("os.listdir", path)
        return originals["listdir"](path)

    def guarded_scandir(path: object = "."):
        check("os.scandir", path)
        return originals["scandir"](path)

    def guarded_access(path: object, *args: object, **kwargs: object):
        check("os.access", path)
        return originals["access"](path, *args, **kwargs)

    offline = AssertionError("construction map v16 attempted network access")
    with ExitStack() as stack:
        stack.enter_context(patch.object(builtins, "open", guarded_builtin_open))
        stack.enter_context(patch.object(io, "open", guarded_io_open))
        stack.enter_context(patch.object(os, "open", guarded_os_open))
        stack.enter_context(patch.object(os, "stat", guarded_stat))
        stack.enter_context(patch.object(os, "lstat", guarded_lstat))
        stack.enter_context(patch.object(os, "listdir", guarded_listdir))
        stack.enter_context(patch.object(os, "scandir", guarded_scandir))
        stack.enter_context(patch.object(os, "access", guarded_access))
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=offline))
        yield


class FrozenConstructionMapV16Tests(unittest.TestCase):
    def test_exact_pins_double_offline_rebuild_and_v14_stability(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(_sha256(MODULE), MODULE_SHA256)
        self.assertEqual(_sha256(MASTER_DEFINITION), MASTER_DEFINITION_SHA256)
        self.assertEqual(_sha256(MASTER / "manifest.json"), MASTER_MANIFEST_SHA256)
        self.assertEqual(_sha256(MASTER / "construction-master.jsonl"), MASTER_JSONL_SHA256)
        self.assertEqual(_sha256(TEMPLATE), TEMPLATE_SHA256)
        self.assertEqual(_sha256(MAP / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_inventory(MAP), (BUNDLE_INVENTORY_SHA256, OUTPUT_CHECKPOINTS))

        self.assertEqual(_sha256(BASE_MAP_DEFINITION), BASE_MAP_DEFINITION_SHA256)
        self.assertEqual(_sha256(BASE_MAP / "manifest.json"), BASE_MAP_MANIFEST_SHA256)
        self.assertEqual(_inventory(BASE_MAP)[0], BASE_MAP_INVENTORY_SHA256)
        self.assertEqual(_sha256(BASE_MASTER_DEFINITION), BASE_MASTER_DEFINITION_SHA256)
        self.assertEqual(
            _sha256(BASE_MASTER / "manifest.json"), BASE_MASTER_MANIFEST_SHA256
        )
        self.assertEqual(_inventory(BASE_MASTER)[0], BASE_MASTER_INVENTORY_SHA256)
        accepted_before = {
            "map_definition": _sha256(BASE_MAP_DEFINITION),
            "map": _inventory(BASE_MAP),
            "master_definition": _sha256(BASE_MASTER_DEFINITION),
            "master": _inventory(BASE_MASTER),
        }

        with tempfile.TemporaryDirectory(
            dir="/private/tmp", prefix="construction-map-v16-test-"
        ) as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            with _offline_rejected_path_guard():
                first_manifest = write_construction_map_v2(
                    MASTER,
                    first,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    freeze=False,
                )
                second_manifest = write_construction_map_v2(
                    MASTER,
                    second,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    freeze=False,
                )
                published_manifest = validate_construction_map_v2(
                    MAP,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    reproduce=False,
                )
                self.assertEqual(first_manifest, second_manifest)
                self.assertEqual(first_manifest, published_manifest)
                for name in BUNDLE_FILES:
                    self.assertEqual(
                        (first / name).read_bytes(), (second / name).read_bytes(), name
                    )
                    self.assertEqual(
                        (first / name).read_bytes(), (MAP / name).read_bytes(), name
                    )

        accepted_after = {
            "map_definition": _sha256(BASE_MAP_DEFINITION),
            "map": _inventory(BASE_MAP),
            "master_definition": _sha256(BASE_MASTER_DEFINITION),
            "master": _inventory(BASE_MASTER),
        }
        self.assertEqual(accepted_after, accepted_before)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(entry.stat().st_mode) == 0o444 for entry in MAP.iterdir())
        )

    def test_definition_and_projection_are_exact_v14_plus_v42(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["expected_projection"], EXPECTED_PROJECTION)
        self.assertEqual(definition["schema_version"], 2)
        self.assertEqual(definition["generated_at"], "2026-07-20T06:15:00Z")
        self.assertEqual(
            definition["map_id"], "2026-07-20-public-open-v16-construction-map-v2"
        )
        self.assertEqual(
            definition["master"],
            {
                "definition": {
                    "bytes": 5_655,
                    "path": "construction-master-2026-07-20-public-open-v16.json",
                    "sha256": MASTER_DEFINITION_SHA256,
                },
                "directory": "../construction_master/2026-07-20-public-open-v16",
                "jsonl": {
                    "bytes": 325_247_990,
                    "path": "../construction_master/2026-07-20-public-open-v16/construction-master.jsonl",
                    "sha256": MASTER_JSONL_SHA256,
                },
                "manifest": {
                    "bytes": 9_667,
                    "path": "../construction_master/2026-07-20-public-open-v16/manifest.json",
                    "sha256": MASTER_MANIFEST_SHA256,
                },
                "master_id": "2026-07-20-public-open-v16",
            },
        )

        master_definition = json.loads(MASTER_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(
            master_definition["inputs"]["base_master"]["master_id"],
            "2026-07-19-public-open-v14",
        )
        replacement = master_definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v42")
        self.assertEqual(replacement["publication_contract_version"], 4)

        base_ids: set[str] = set()
        with (BASE_MASTER / "construction-master.jsonl").open(
            encoding="utf-8"
        ) as source:
            for raw in source:
                row = json.loads(raw)
                if row["source"]["artifact_id"] != "epoch-official-open-seed-v33":
                    break
                base_ids.add(row["source"]["record_id"])
        with V42_DATA.open(newline="", encoding="utf-8") as source:
            v42_ids = {row["entity_id"] for row in csv.DictReader(source)}
        additions = v42_ids - base_ids
        self.assertEqual(len(base_ids), 199)
        self.assertEqual(_id_digest(base_ids), BASE_SOURCE_RECORD_IDS_SHA256)
        self.assertEqual(len(v42_ids), 262)
        self.assertEqual(_id_digest(v42_ids), V42_SOURCE_RECORD_IDS_SHA256)
        self.assertEqual(base_ids - v42_ids, set())
        self.assertEqual(len(additions), 63)
        self.assertEqual(
            _id_digest(additions),
            EXPECTED_PROJECTION[
                "added_replacement_unmapped_source_record_ids_sha256"
            ],
        )

        index = _index()
        positions = {field: position for position, field in enumerate(index["fields"])}
        mapped_ids = {row[positions["source_record_id"]] for row in index["rows"]}
        self.assertEqual(additions & mapped_ids, set())
        self.assertEqual(len(index["rows"]), 108_973)
        self.assertEqual(
            Counter(row[positions["tier"]] for row in index["rows"]),
            {"A": 199, "B": 6_280, "C": 102_494},
        )
        mapped_v42 = [
            row
            for row in index["rows"]
            if row[positions["source_artifact_id"]]
            == "epoch-official-open-seed-v42"
        ]
        self.assertEqual(len(mapped_v42), 80)
        self.assertEqual(
            sum(
                any(
                    row[positions[key]] is not None
                    for key in ("owner", "operator", "users", "tenants", "customers")
                )
                or bool(row[positions["source_role_tags"]])
                for row in index["rows"]
            ),
            66,
        )
        self.assertEqual(
            FIELDS,
            V1_FIELDS
            + (
                "source_publication_contract_version",
                "owner",
                "operator",
                "users",
                "tenants",
                "customers",
                "source_role_tags",
            ),
        )

    def test_scope_roles_and_rejected_route_absence(self) -> None:
        coverage = json.loads((MAP / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertIsNone(coverage["counts"]["unique_physical_site_count"])
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        readme = (MAP / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "does not deduplicate physical sites or claim global completeness", readme
        )
        self.assertIn("Statuses are historical observations", readme)

        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", template)
        self.assertIn("valueNode.textContent", template)
        self.assertIn("link.textContent", template)
        self.assertIn("JSON.stringify(tags)", template)
        with (MASTER / "construction-master.jsonl").open(encoding="utf-8") as source:
            replacement = json.loads(next(source))
        for marker in (3, 4.0, True, "4"):
            changed = deepcopy(replacement)
            changed["roles"]["source_publication_contract_version"] = marker
            with self.subTest(marker=repr(marker)), self.assertRaisesRegex(
                ConstructionMapV2Error, "marker changed"
            ):
                _project_row(changed, 1)

        payloads = [DEFINITION.read_bytes(), MODULE.read_bytes()]
        payloads.extend(path.read_bytes() for path in MAP.iterdir())
        for marker in REJECTED_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_mutation_tampering_and_freeze_fail_closed(self) -> None:
        changed_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        changed_definition["expected_projection"]["mapped_rows_with_any_role"] = 65
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir="/private/tmp",
            prefix="changed-map-v16-",
            suffix=".json",
        ) as temporary:
            temporary.write(
                json.dumps(changed_definition, indent=2, sort_keys=True) + "\n"
            )
            temporary.flush()
            with self.assertRaisesRegex(
                ConstructionMapV2Error, "fixed projection"
            ):
                validate_map_definition_v2(
                    temporary.name,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                )

        with tempfile.TemporaryDirectory(
            dir="/private/tmp", prefix="map-v16-fail-closed-"
        ) as temporary:
            mutable = Path(temporary) / "mutable"
            tampered = Path(temporary) / "tampered"
            shutil.copytree(MAP, mutable)
            shutil.copytree(MAP, tampered)
            try:
                _make_writable(mutable)
                with self.assertRaisesRegex(
                    ConstructionMapV2Error, "must be frozen"
                ):
                    validate_construction_map_v2(
                        mutable,
                        master_directory=MASTER,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                        reproduce=False,
                    )

                _make_writable(tampered)
                with (tampered / "README.md").open("ab") as destination:
                    destination.write(b"tampered\n")
                for entry in tampered.iterdir():
                    entry.chmod(0o444)
                tampered.chmod(0o555)
                with self.assertRaisesRegex(
                    ConstructionMapV2Error, "output changed: README.md"
                ):
                    validate_construction_map_v2(
                        tampered,
                        master_directory=MASTER,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                        reproduce=False,
                    )
            finally:
                _make_writable(mutable)
                _make_writable(tampered)

        compressed = (MAP / "construction-map-index.json.gz").read_bytes()
        self.assertEqual(compressed[:4], b"\x1f\x8b\x08\x00")
        self.assertEqual(compressed[4:8], b"\0" * 4)
        self.assertEqual(compressed[9], 255)
        expected_html = TEMPLATE.read_text(encoding="utf-8").replace(
            "__CONSTRUCTION_MAP_GZIP_BASE64__",
            base64.b64encode(compressed).decode("ascii"),
        ).encode("utf-8")
        self.assertEqual((MAP / "construction-map.html").read_bytes(), expected_html)


if __name__ == "__main__":
    unittest.main()
