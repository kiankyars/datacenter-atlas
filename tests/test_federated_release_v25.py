from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
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

import datacenter_atlas.federated_release as federation_module
from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    FederatedReleaseError,
    build_federated_release_index,
    validate_federated_release_index,
    write_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v25.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v25"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v24.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v24"
V56_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
V56_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"

GENERATED_AT = "2026-07-20T22:54:00Z"
V56_RECORDED_AT = "2026-07-20T22:34:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v55"
NEW_RELEASE_ID = "epoch-official-open-seed-v56"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "2b60e26e211e584d60f6743beef1a3ed7f06714297cd36896cd2f60a0067e829"
INDEX_SHA256 = "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db"
MANIFEST_SHA256 = "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f"
SIDECAR_SHA256 = "59a75fc6216e83b703ec16aaaad731fa07939d5a1c05fff488d2d3aab61a94da"
TREE_SHA256 = "962a7d0733b363935f6640bc36d0930573e1c04ba91679dc7cdbef8cada83e57"

BASE_DEFINITION_SHA256 = (
    "98dc26e06948ff3334a8c3e21fc7b31616cf177362217459f04cd5a9d221e6a0"
)
BASE_INDEX_SHA256 = "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d"
BASE_MANIFEST_SHA256 = (
    "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1"
)
BASE_SIDECAR_SHA256 = (
    "d81f5d72d6826b35c88c0ea90eab9a16f70baf0cebc3a257f41bc8489eaa9da1"
)
BASE_TREE_SHA256 = "7ee18187b63f6f68e39d04b808cb0de294eddb2837b79bb0ac7259685029e4f3"

V56_DEFINITION_SHA256 = (
    "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
)
V56_MANIFEST_SHA256 = (
    "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd"
)
V56_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"

ARTIFACTS = {
    INDEX_FILENAME: (24_828, INDEX_SHA256),
    MANIFEST_FILENAME: (986, MANIFEST_SHA256),
    MANIFEST_HASH_FILENAME: (80, SIDECAR_SHA256),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/federated_release.py": (
        46_272,
        "bc81c767c516f543bafe90cb4818d62956e5fd7bea69363dd274bad090155e29",
    ),
    ROOT / "scripts/build_federated_release_index.py": (
        1_809,
        "97068c3eb5b7c233388beab916c09266a1a4a9ae5d54d0f52014b2c1a949d078",
    ),
}

EXPECTED_COUNTS = {
    "capacity_estimates": 1_270,
    "construction_pipeline_records": 6_598,
    "evidence_records": 13_401,
    "non_review_construction_pipeline_records": 468,
    "non_review_source_scoped_entity_records": 9_962,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 210,
    "source_scoped_entity_records": 16_092,
    "unique_physical_sites": None,
}

EXPECTED_DELTA = {
    "capacity_estimates": 2,
    "construction_pipeline_records": 2,
    "evidence_records": 5,
    "non_review_construction_pipeline_records": 2,
    "non_review_source_scoped_entity_records": 4,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 2,
    "source_scoped_entity_records": 4,
}

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 484,
    "construction_pipeline_records": 348,
    "entities_by_kind": {"campus": 359, "project": 308},
    "evidence_records": 388,
    "resolution_candidates": 4,
    "source_family_entries": 203,
    "source_scoped_entity_records": 667,
}

CHILDREN = {
    NEW_RELEASE_ID: V56_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}

FORBIDDEN = (
    "epoch-official-open-seed-v49",
    "epoch-official-open-seed-v54",
    "epoch-official-open-seed-v55",
    "releases/2026-07-20-open-seed-v49",
    "releases/2026-07-20-open-seed-v54",
    "releases/2026-07-20-open-seed-v55",
    "google-bermuda-hundred-chesterfield",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


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
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


class FederatedReleaseV25Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v25 federation attempted network, stale child, or excluded input access"
        )
        original = federation_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if any(marker in path.as_posix() for marker in FORBIDDEN):
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(federation_module, "_regular_bytes", side_effect=guarded)
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_predecessors_modes_and_tree_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            BASE_INDEX_DIR / MANIFEST_HASH_FILENAME: BASE_SIDECAR_SHA256,
            V56_DEFINITION: V56_DEFINITION_SHA256,
            V56_RELEASE / MANIFEST_FILENAME: V56_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(BASE_INDEX_DIR), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(V56_RELEASE), V56_TREE_SHA256)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in INDEX_DIR.iterdir()}, set(ARTIFACTS))
        for path in INDEX_DIR.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, (size, digest) in CODE_PINS.items():
            self.assertEqual(path.stat().st_size, size, path)
            self.assertEqual(sha256(path), digest, path)

    def test_exact_v24_to_v56_child_swap_and_additive_counts(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V56_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v56/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v56",
            }
        )
        raw = DEFINITION.read_bytes()
        current_definition = json.loads(raw)
        self.assertEqual(raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(V56_RECORDED_AT.replace("Z", "+00:00")),
        )

        base_index = json.loads((BASE_INDEX_DIR / INDEX_FILENAME).read_text())
        current = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertFalse(current["policy"]["cross_source_deduplication"])
        self.assertIsNone(current["policy"]["unique_physical_site_count"])
        by_id = {item["release_id"]: item for item in current["releases"]}
        base_by_id = {item["release_id"]: item for item in base_index["releases"]}
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])
        self.assertEqual(by_id[NEW_RELEASE_ID]["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V56_MANIFEST_SHA256
        )
        self.assertEqual(
            {
                key: current["counts"][key] - base_index["counts"][key]
                for key in EXPECTED_DELTA
            },
            EXPECTED_DELTA,
        )
        self.assertIsNone(current["counts"]["unique_physical_sites"])

        old_child = base_by_id[OLD_RELEASE_ID]
        new_child = by_id[NEW_RELEASE_ID]
        self.assertEqual(
            set(new_child["source_families"]) - set(old_child["source_families"]),
            {"paix_official_prismic", "pentapoint_official_webflow"},
        )
        attribution = new_child["rights"]["attribution"]["text"]
        self.assertIn("PAIX Data Centres\n", attribution)
        self.assertIn("PentaPoint Data Center Development Corporation\n", attribution)
        self.assertIn("PentaPoint Data Corporation\n", attribution)
        for marker in FORBIDDEN:
            if "v55" not in marker:
                self.assertNotIn(marker, json.dumps(current_definition))
                self.assertNotIn(marker, json.dumps(current))

    def test_double_offline_reproduction_validation_and_idempotence(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_federated_release_index(DEFINITION)
            second = build_federated_release_index(DEFINITION)
            validated = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            idempotent = write_federated_release_index(DEFINITION, INDEX_DIR)
            with tempfile.TemporaryDirectory(
                prefix="federation-v25-reproduction-", dir="/private/tmp"
            ) as temporary:
                root = Path(temporary)
                first_dir = root / "first"
                second_dir = root / "second"
                write_federated_release_index(DEFINITION, first_dir)
                write_federated_release_index(DEFINITION, second_dir)
                first_reproduction = {
                    path.name: path.read_bytes() for path in first_dir.iterdir()
                }
                second_reproduction = {
                    path.name: path.read_bytes() for path in second_dir.iterdir()
                }
        self.assertEqual(first, second)
        self.assertEqual(first.index, validated)
        self.assertEqual(first.index, idempotent)
        self.assertEqual(first.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(first.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME])
        self.assertEqual(first_reproduction, frozen)
        self.assertEqual(second_reproduction, frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )
        for marker in FORBIDDEN:
            self.assertNotIn(
                marker.encode(), b"".join([DEFINITION.read_bytes(), *frozen.values()])
            )

    def test_existing_different_bundle_and_symlink_collisions_are_rejected(self) -> None:
        before = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        before_base = {
            path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()
        }
        with tempfile.TemporaryDirectory(
            prefix="federation-v25-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            different = root / "different"
            shutil.copytree(BASE_INDEX_DIR, different)
            with self.assertRaisesRegex(
                FederatedReleaseError,
                "existing federated index is valid but not byte-identical",
            ):
                write_federated_release_index(DEFINITION, different)
            self.assertEqual(
                {path.name: path.read_bytes() for path in different.iterdir()},
                before_base,
            )

            symlink = root / "symlink-output"
            symlink.symlink_to(different, target_is_directory=True)
            with self.assertRaisesRegex(
                FederatedReleaseError, "federated output may not be a symlink"
            ):
                write_federated_release_index(DEFINITION, symlink)
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, before
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()},
            before_base,
        )

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.federated_release"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.federated_release"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_federated_release_index; "
                f"result=validate_federated_release_index(Path({str(INDEX_DIR)!r})); "
                "assert result['counts']['source_scoped_entity_records']==16092; "
                "assert result['counts']['non_review_source_scoped_entity_records']==9962; "
                "assert result['counts']['review_only_source_scoped_entity_records']==6130; "
                "assert result['counts']['unique_physical_sites'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
