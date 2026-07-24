from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
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

try:
    from datacenter_atlas.datacenter_atlas import federated_release as legacy
    from datacenter_atlas.datacenter_atlas import federated_release_v3 as federation
except ModuleNotFoundError:
    from datacenter_atlas import federated_release as legacy
    from datacenter_atlas import federated_release_v3 as federation


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v29.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v29"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v28.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v28"
V68_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
V68_RELEASE = ROOT / "releases/2026-07-21-open-seed-v68"

GENERATED_AT = "2026-07-21T09:40:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v67"
NEW_RELEASE_ID = "epoch-official-open-seed-v68"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "3339bf84b41ef8088b9f2dd960101f1d962267b66cc9a409b39bf41c726cde3a"
INDEX_SHA256 = "582fb7b2ea5c10e323024e0235ceea4799e197fef15b9f4b27986e6a3ef412b0"
MANIFEST_SHA256 = "28032fa68fc9557d4d3daf26ce93bec27bcb27d5f874f25f0f0dbf2bf44563a6"
SIDECAR_SHA256 = "32d40221fac34456882afe5bd478223ffac8f4425e6ca6a141aed24c31d52c79"
TREE_SHA256 = "3c8a7d6dfd7a1d95a33ad0bbaeffc68fa29d1721412f9ccf2677d29b17cffb6a"
V68_DEFINITION_SHA256 = "430544a894c0e529693699fe6db36387b690f621ee899a38bedd9ea093ec394f"
V68_MANIFEST_SHA256 = "7aa9d511831509f953fdfe6bccd9380feeb2feac11ec529eb9b024243a7da3e7"
V68_TREE_SHA256 = "855258248ab3af498ef6f6259d55a2ace093c8eacdcc7b6b1aafe03ac8f3b89b"

EXPECTED_COUNTS = {
    "capacity_estimates": 1316,
    "construction_pipeline_records": 6664,
    "evidence_records": 13520,
    "non_review_construction_pipeline_records": 534,
    "non_review_source_scoped_entity_records": 10101,
    "release_bundles": 3,
    "resolution_candidates": 100411,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 291,
    "source_scoped_entity_records": 16231,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 9,
    "construction_pipeline_records": 13,
    "evidence_records": 13,
    "non_review_construction_pipeline_records": 13,
    "non_review_source_scoped_entity_records": 23,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 4,
    "source_scoped_entity_records": 23,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 530,
    "construction_pipeline_records": 414,
    "entities_by_kind": {"campus": 425, "project": 381},
    "evidence_records": 507,
    "resolution_candidates": 6,
    "source_family_entries": 284,
    "source_scoped_entity_records": 806,
}
CHILDREN = {
    NEW_RELEASE_ID: V68_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())]
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
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{hashlib.sha256(raw).hexdigest()}\n".encode()
            )
        else:
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


class FederatedReleaseV29Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v29 federation attempted network access")
        for name in (
            "socket", "create_connection", "getaddrinfo", "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_and_trees_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            V68_DEFINITION: V68_DEFINITION_SHA256,
            V68_RELEASE / federation.MANIFEST_FILENAME: V68_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(V68_RELEASE), V68_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in INDEX_DIR.iterdir()}, federation.FEDERATED_BUNDLE_FILES)
        for path in INDEX_DIR.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_definition_is_exact_v28_successor_and_counts_reconcile(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text())
        expected_definition = deepcopy(base_definition)
        expected_definition["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected_definition["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V68_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-21-open-seed-v68/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v68",
            }
        )
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current_definition))
        self.assertEqual(current_definition, expected_definition)

        base = json.loads((BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text())
        current = federation.validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertEqual(
            {key: current["counts"][key] - base["counts"][key] for key in EXPECTED_DELTA},
            EXPECTED_DELTA,
        )
        current_by_id = {row["release_id"]: row for row in current["releases"]}
        base_by_id = {row["release_id"]: row for row in base["releases"]}
        self.assertEqual(set(current_by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], base_by_id[release_id])
        open_child = current_by_id[NEW_RELEASE_ID]
        self.assertEqual(open_child["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            open_child["manifest"],
            {
                "as_of": "2026-07-21",
                "bytes": 12432,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 456,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T09:30:00Z",
                "sha256": V68_MANIFEST_SHA256,
            },
        )
        old_open = base_by_id[OLD_RELEASE_ID]
        self.assertEqual(open_child["rights"]["license_expression"], old_open["rights"]["license_expression"])
        self.assertEqual(open_child["rights"]["rights_notice"], old_open["rights"]["rights_notice"])
        self.assertEqual(open_child["rights"]["source_licenses"], old_open["rights"]["source_licenses"])
        self.assertEqual(open_child["rights"]["attribution"]["bytes"], 5657)

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(prefix="federation-v29-rebuild-", dir="/private/tmp") as temporary:
            reproduced = Path(temporary) / INDEX_DIR.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = federation.build_federated_release_index
                with patch.object(federation, "build_federated_release_index", wraps=wrapped) as rebuild:
                    built = federation.write_federated_release_index(DEFINITION, reproduced)
                self.assertEqual(rebuild.call_count, 2)
            self.assertEqual(built["counts"], EXPECTED_COUNTS)
            self.assertEqual({path.name: path.read_bytes() for path in reproduced.iterdir()}, frozen)
        self.assertEqual({path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen)

    def test_tampering_child_symlink_and_collisions_fail_closed(self) -> None:
        current = json.loads((INDEX_DIR / federation.INDEX_FILENAME).read_text())
        descriptor = next(row for row in current["releases"] if row["release_id"] == NEW_RELEASE_ID)
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "current_status_inferred must be false"
        ):
            federation._validate_descriptor(inferred, 0)
        with tempfile.TemporaryDirectory(prefix="federation-v29-fail-closed-", dir="/private/tmp") as temporary:
            root = Path(temporary)
            child_symlink = root / V68_RELEASE.name
            child_symlink.symlink_to(V68_RELEASE, target_is_directory=True)
            definition = legacy._ChildDefinition(
                release_id=NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=V68_MANIFEST_SHA256,
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(federation.FederatedReleaseError, "regular directory"):
                federation._inspect_child(definition)

            copied = root / "tampered"
            shutil.copytree(INDEX_DIR, copied)
            copied.chmod(0o755)
            index_path = copied / federation.INDEX_FILENAME
            index_path.chmod(0o644)
            index_path.write_bytes(index_path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "not canonical|checkpoint does not match"
            ):
                federation.validate_federated_release_index(copied, require_frozen=False)

            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(federation.FederatedReleaseError):
                federation.write_federated_release_index(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            symlink = root / "symlink"
            symlink.symlink_to(INDEX_DIR, target_is_directory=True)
            with self.assertRaisesRegex(federation.FederatedReleaseError, "output may not be a symlink"):
                federation.write_federated_release_index(DEFINITION, symlink)

    def test_both_import_layouts_validate_v68_guardrails(self) -> None:
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.federated_release_v3 import validate_federated_release_index as v; "
            f"r=v(Path({str(INDEX_DIR)!r})); "
            "assert r['counts']['source_scoped_entity_records']==16231; "
            "assert r['counts']['review_only_source_scoped_entity_records']==6130; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v68')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['lifecycle_freshness_records']==456"
        )
        for working_directory in (ROOT, WORKSPACE):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
