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
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v28.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v28"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v27.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v27"
V67_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V67_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"

GENERATED_AT = "2026-07-21T07:55:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v62"
NEW_RELEASE_ID = "epoch-official-open-seed-v67"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "6dbc1095c7fd8b6d36e217263aac23b0c612e84b7d781fa5cc32fbaa2c4e57d9"
INDEX_SHA256 = "d21cfa01157dc7529d71bfd99d4f6d2bbc74285a8c58392ee402dc767faf3210"
MANIFEST_SHA256 = "d465a2de75b94168113b712740a1761e93887c1bc998a5164ba54489202e5f6e"
SIDECAR_SHA256 = "c4796d7cc0ccfbed8a85f8b35ec8290f3d35eaceea447b185a7f693077d6bc3a"
TREE_SHA256 = "88113b5342b48be3dbe663bdc4da2fe57a5de75c983220f42e2ccc822b3f501a"
V67_DEFINITION_SHA256 = "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5"
V67_MANIFEST_SHA256 = "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb"
V67_TREE_SHA256 = "fb4a8016c3c0c143cef2e5ac35d0787bb2b0dbd45115e27a83a70167ccb0b4fb"

EXPECTED_COUNTS = {
    "capacity_estimates": 1307,
    "construction_pipeline_records": 6651,
    "evidence_records": 13507,
    "non_review_construction_pipeline_records": 521,
    "non_review_source_scoped_entity_records": 10078,
    "release_bundles": 3,
    "resolution_candidates": 100411,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 287,
    "source_scoped_entity_records": 16208,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 19,
    "construction_pipeline_records": 28,
    "evidence_records": 50,
    "non_review_construction_pipeline_records": 28,
    "non_review_source_scoped_entity_records": 53,
    "release_bundles": 0,
    "resolution_candidates": 1,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 37,
    "source_scoped_entity_records": 53,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 521,
    "construction_pipeline_records": 401,
    "entities_by_kind": {"campus": 415, "project": 368},
    "evidence_records": 494,
    "resolution_candidates": 6,
    "source_family_entries": 280,
    "source_scoped_entity_records": 783,
}
CHILDREN = {
    NEW_RELEASE_ID: V67_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


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


class FederatedReleaseV28Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v28 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_and_trees_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            V67_DEFINITION: V67_DEFINITION_SHA256,
            V67_RELEASE / federation.MANIFEST_FILENAME: V67_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(V67_RELEASE), V67_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            federation.FEDERATED_BUNDLE_FILES,
        )
        for path in INDEX_DIR.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_definition_is_exact_v27_successor_and_counts_reconcile(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected_definition = deepcopy(base_definition)
        expected_definition["generated_at"] = GENERATED_AT
        child = next(
            item
            for item in expected_definition["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V67_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-21-open-seed-v67/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v67",
            }
        )
        current_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current_definition))
        self.assertEqual(current_definition, expected_definition)

        base = json.loads(
            (BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = federation.validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertEqual(
            {
                key: current["counts"][key] - base["counts"][key]
                for key in EXPECTED_DELTA
            },
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
                "bytes": 12274,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 443,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T07:30:00Z",
                "sha256": V67_MANIFEST_SHA256,
            },
        )
        old_open = base_by_id[OLD_RELEASE_ID]
        v67_manifest = json.loads(
            (V67_RELEASE / federation.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        attribution_raw = (V67_RELEASE / "ATTRIBUTION.txt").read_bytes()
        open_definition = next(
            row
            for row in current_definition["children"]
            if row["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(
            open_child["rights"],
            {
                "attribution": {
                    "bytes": len(attribution_raw),
                    "file": "ATTRIBUTION.txt",
                    "sha256": hashlib.sha256(attribution_raw).hexdigest(),
                    "text": attribution_raw.decode("utf-8"),
                },
                "license_expression": open_definition["license_expression"],
                "rights_notice": open_definition["rights_notice"],
                "source_licenses": [
                    "CC-BY-3.0",
                    "CC-BY-4.0",
                    "CC-BY-4.0-subject-to-third-party-material",
                    "all-rights-reserved",
                    "all-rights-reserved-facts-only",
                    "government-public-record",
                    "public-domain",
                    "public-domain-us-government",
                    "public-government-record",
                    "public-record",
                ],
            },
        )
        self.assertEqual(
            v67_manifest["files"]["ATTRIBUTION.txt"],
            {
                "bytes": open_child["rights"]["attribution"]["bytes"],
                "sha256": open_child["rights"]["attribution"]["sha256"],
            },
        )
        self.assertEqual(
            set(open_child["rights"]["source_licenses"])
            - set(old_open["rights"]["source_licenses"]),
            {
                "CC-BY-3.0",
                "CC-BY-4.0-subject-to-third-party-material",
                "all-rights-reserved-facts-only",
                "public-domain",
            },
        )
        self.assertEqual(
            set(old_open["rights"]["source_licenses"])
            - set(open_child["rights"]["source_licenses"]),
            set(),
        )
        self.assertEqual(
            open_child["rights"]["attribution"]["bytes"]
            - old_open["rights"]["attribution"]["bytes"],
            937,
        )
        self.assertEqual(
            open_child["counts"]["source_scoped_entity_records"]
            - old_open["counts"]["source_scoped_entity_records"],
            53,
        )

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v28-rebuild-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / INDEX_DIR.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = federation.build_federated_release_index
                with patch.object(
                    federation,
                    "build_federated_release_index",
                    wraps=wrapped,
                ) as rebuild:
                    built = federation.write_federated_release_index(
                        DEFINITION, reproduced
                    )
                self.assertEqual(rebuild.call_count, 2)
            self.assertEqual(built["counts"], EXPECTED_COUNTS)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()},
                frozen,
            )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

    def test_descriptor_child_and_bundle_tampering_fail_closed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            row for row in current["releases"] if row["release_id"] == NEW_RELEASE_ID
        )
        missing = deepcopy(descriptor)
        del missing["manifest"]["lifecycle_status_semantics"]
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "freshness fields must be present together"
        ):
            federation._validate_descriptor(missing, 0)
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "current_status_inferred must be false"
        ):
            federation._validate_descriptor(inferred, 0)

        with tempfile.TemporaryDirectory(
            prefix="federation-v28-tamper-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V67_RELEASE.name
            child_symlink.symlink_to(V67_RELEASE, target_is_directory=True)
            definition = legacy._ChildDefinition(
                release_id=NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=V67_MANIFEST_SHA256,
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "regular directory"
            ):
                federation._inspect_child(definition)

            copied = temporary_root / "tampered-index"
            shutil.copytree(INDEX_DIR, copied)
            copied.chmod(0o755)
            index_path = copied / federation.INDEX_FILENAME
            index_path.chmod(0o644)
            index_path.write_bytes(index_path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                federation.FederatedReleaseError,
                "not canonical|checkpoint does not match",
            ):
                federation.validate_federated_release_index(
                    copied, require_frozen=False
                )

    def test_no_replace_late_collision_symlink_and_both_layouts(self) -> None:
        before = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v28-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(federation.FederatedReleaseError):
                federation.write_federated_release_index(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            symlink = root / "symlink"
            symlink.symlink_to(INDEX_DIR, target_is_directory=True)
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "output may not be a symlink"
            ):
                federation.write_federated_release_index(DEFINITION, symlink)

            stage = root / "stage"
            destination = root / "destination"
            stage.mkdir()
            destination.mkdir()
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "late output collision"
            ):
                federation._promote_noreplace(stage, destination)
            self.assertTrue(stage.is_dir())
            self.assertTrue(destination.is_dir())
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, before
        )

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.federated_release_v3 import "
            "validate_federated_release_index; "
            f"r=validate_federated_release_index(Path({str(INDEX_DIR)!r})); "
            "assert r['counts']['source_scoped_entity_records']==16208; "
            "assert r['counts']['review_only_source_scoped_entity_records']==6130; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v67')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['lifecycle_freshness_records']==443"
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
