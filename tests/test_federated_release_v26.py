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
    from datacenter_atlas.datacenter_atlas import federated_release_v2 as federation_v2
except ModuleNotFoundError:
    from datacenter_atlas import federated_release as legacy
    from datacenter_atlas import federated_release_v2 as federation_v2


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v26.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v26"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v25.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v25"
V59_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"

GENERATED_AT = "2026-07-21T03:32:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v56"
NEW_RELEASE_ID = "epoch-official-open-seed-v59"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "34a26ee6f747d3dae9a96257b6dd5e7051aacf446ce392f2c6f5087146a66b32"
INDEX_SHA256 = "df5f32a7b843e96ca6cf26aacbcf4b501614bcb57fd0f84ac8dea6889640ce53"
MANIFEST_SHA256 = "7c46daa54ea1de6da325f495f4a54fda2e1c16bae3a0ca7fdb6901ba7d391361"
SIDECAR_SHA256 = "7b36b9487f33693886d7658c6edc033d9fb5b4eda0c03f091c67f76f0237ac3a"
TREE_SHA256 = "f512cca96449fc844f6e18f72ba9705862b06563af743cb775e9ed3d6ef9ab5e"

BASE_DEFINITION_SHA256 = "2b60e26e211e584d60f6743beef1a3ed7f06714297cd36896cd2f60a0067e829"
BASE_INDEX_SHA256 = "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db"
BASE_MANIFEST_SHA256 = "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f"
BASE_SIDECAR_SHA256 = "59a75fc6216e83b703ec16aaaad731fa07939d5a1c05fff488d2d3aab61a94da"
BASE_TREE_SHA256 = "962a7d0733b363935f6640bc36d0930573e1c04ba91679dc7cdbef8cada83e57"

V59_DEFINITION_SHA256 = "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
V59_MANIFEST_SHA256 = "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
V59_TREE_SHA256 = "53cb173fb0e07b8dba8f9bb974cc533b38ba006590583725baf122cb8ba8d636"

ARTIFACTS = {
    federation_v2.INDEX_FILENAME: (26_865, INDEX_SHA256),
    federation_v2.MANIFEST_FILENAME: (986, MANIFEST_SHA256),
    federation_v2.MANIFEST_HASH_FILENAME: (80, SIDECAR_SHA256),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/federated_release.py": (
        46_272,
        "bc81c767c516f543bafe90cb4818d62956e5fd7bea69363dd274bad090155e29",
    ),
    ROOT / "datacenter_atlas/federated_release_v2.py": (
        26_557,
        "ff16627d62a5bda3d760e9d211de9923c5691d13760c6abe7540d2b1aff216f3",
    ),
    ROOT / "federated_release_v2.py": (
        144,
        "f3b44cd056a181b73536bab186c921c6182a0c32d03054e4a6a34cb292d35906",
    ),
    ROOT / "scripts/build_federated_release_index_v2.py": (
        1_717,
        "20c6fe3765c8a25c8ac103794c1d7a4a248952c55f7e5dfd7b3e9845c0dc350d",
    ),
}

EXPECTED_COUNTS = {
    "capacity_estimates": 1_277,
    "construction_pipeline_records": 6_612,
    "evidence_records": 13_431,
    "non_review_construction_pipeline_records": 482,
    "non_review_source_scoped_entity_records": 9_994,
    "release_bundles": 3,
    "resolution_candidates": 100_410,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 234,
    "source_scoped_entity_records": 16_124,
    "unique_physical_sites": None,
}

EXPECTED_DELTA = {
    "capacity_estimates": 7,
    "construction_pipeline_records": 14,
    "evidence_records": 30,
    "non_review_construction_pipeline_records": 14,
    "non_review_source_scoped_entity_records": 32,
    "release_bundles": 0,
    "resolution_candidates": 1,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 24,
    "source_scoped_entity_records": 32,
}

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 491,
    "construction_pipeline_records": 362,
    "entities_by_kind": {"campus": 375, "project": 324},
    "evidence_records": 418,
    "resolution_candidates": 5,
    "source_family_entries": 227,
    "source_scoped_entity_records": 699,
}

CHILDREN = {
    NEW_RELEASE_ID: V59_RELEASE,
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


class FederatedReleaseV26Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v26 federation attempted network or a stale open-seed child"
        )
        original = legacy._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            text = path.as_posix()
            if "open-seed-" in text and "open-seed-v59" not in text:
                raise failure
            return original(path, label)

        stack.enter_context(patch.object(legacy, "_regular_bytes", side_effect=guarded))
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_tree_and_legacy_code_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / federation_v2.INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / federation_v2.MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / federation_v2.MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / legacy.INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / legacy.MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            BASE_INDEX_DIR / legacy.MANIFEST_HASH_FILENAME: BASE_SIDECAR_SHA256,
            V59_DEFINITION: V59_DEFINITION_SHA256,
            V59_RELEASE / legacy.MANIFEST_FILENAME: V59_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(BASE_INDEX_DIR), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(V59_RELEASE), V59_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
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

    def test_exact_v25_to_v59_swap_and_v2_descriptor(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V59_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v59/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v59",
            }
        )
        raw = DEFINITION.read_bytes()
        current_definition = json.loads(raw)
        self.assertEqual(raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertTrue(DEFINITION.name.startswith("federation-2026-07-20-"))
        self.assertTrue(INDEX_DIR.name.startswith("2026-07-20-"))

        base_index = json.loads(
            (BASE_INDEX_DIR / legacy.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = json.loads(
            (INDEX_DIR / federation_v2.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(current["schema_version"], 2)
        self.assertEqual(current["format"], federation_v2.INDEX_FORMAT)
        self.assertEqual(current["generated_at"], GENERATED_AT)
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation_v2.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        by_id = {item["release_id"]: item for item in current["releases"]}
        base_by_id = {item["release_id"]: item for item in base_index["releases"]}
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])

        v59 = by_id[NEW_RELEASE_ID]
        self.assertEqual(v59["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            v59["manifest"],
            {
                "as_of": "2026-07-20",
                "bytes": 10_441,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 399,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T03:00:00Z",
                "sha256": V59_MANIFEST_SHA256,
            },
        )
        self.assertIn(federation_v2.FRESHNESS_FILENAME, v59["files"])
        self.assertEqual(
            {
                key: current["counts"][key] - base_index["counts"][key]
                for key in EXPECTED_DELTA
            },
            EXPECTED_DELTA,
        )

    def test_publication_v4_failures_are_closed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation_v2.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            item for item in current["releases"] if item["release_id"] == NEW_RELEASE_ID
        )
        missing = deepcopy(descriptor)
        del missing["manifest"]["lifecycle_status_semantics"]
        with self.assertRaisesRegex(
            federation_v2.FederatedReleaseError,
            "freshness fields must be present together",
        ):
            federation_v2._validate_descriptor(missing, 0)
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation_v2.FederatedReleaseError,
            "current_status_inferred must be false",
        ):
            federation_v2._validate_descriptor(inferred, 0)

        with tempfile.TemporaryDirectory(
            prefix="federation-v26-child-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V59_RELEASE.name
            shutil.copytree(V59_RELEASE, copied)
            copied.chmod(0o755)
            manifest_path = copied / "manifest.json"
            manifest_path.chmod(0o644)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["current_status_inferred"] = True
            manifest_path.write_bytes(canonical_json(manifest))
            definition = legacy._ChildDefinition(
                release_id=NEW_RELEASE_ID,
                release_path=copied,
                reference=descriptor["reference"],
                expected_manifest_sha256=sha256(manifest_path),
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError,
                "current_status_inferred must be false",
            ):
                federation_v2._inspect_child(definition)

    def test_freshness_csv_rows_are_reconciled_not_just_manifest_claimed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation_v2.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            item for item in current["releases"] if item["release_id"] == NEW_RELEASE_ID
        )
        with tempfile.TemporaryDirectory(
            prefix="federation-v26-freshness-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V59_RELEASE.name
            shutil.copytree(V59_RELEASE, copied)
            copied.chmod(0o755)
            freshness = copied / federation_v2.FRESHNESS_FILENAME
            freshness.chmod(0o644)
            raw = freshness.read_text(encoding="utf-8")
            self.assertIn(",false\n", raw)
            freshness.write_text(raw.replace(",false\n", ",true\n", 1), encoding="utf-8")
            manifest_path = copied / "manifest.json"
            manifest_path.chmod(0o644)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][federation_v2.FRESHNESS_FILENAME] = {
                "bytes": freshness.stat().st_size,
                "sha256": sha256(freshness),
            }
            manifest_path.write_bytes(canonical_json(manifest))
            definition = legacy._ChildDefinition(
                release_id=NEW_RELEASE_ID,
                release_path=copied,
                reference=descriptor["reference"],
                expected_manifest_sha256=sha256(manifest_path),
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError,
                "freshness row implies current status",
            ):
                federation_v2._inspect_child(definition)

    def test_offline_double_rebuild_reproduction_and_child_recheck(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v26-reproduction-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / INDEX_DIR.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = federation_v2.build_federated_release_index
                with patch.object(
                    federation_v2,
                    "build_federated_release_index",
                    wraps=wrapped,
                ) as rebuild:
                    built = federation_v2.write_federated_release_index(
                        DEFINITION, reproduced
                    )
                self.assertEqual(rebuild.call_count, 2)
                validated = federation_v2.validate_federated_release_index(
                    INDEX_DIR, child_release_paths=CHILDREN
                )
            reproduced_bytes = {
                path.name: path.read_bytes() for path in reproduced.iterdir()
            }
        self.assertEqual(built, validated)
        self.assertEqual(reproduced_bytes, frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

    def test_no_replace_tamper_and_import_layouts(self) -> None:
        before = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v26-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            other_definition = root / DEFINITION.name
            other = json.loads(DEFINITION.read_text(encoding="utf-8"))
            other["generated_at"] = "2026-07-21T03:33:00Z"
            for child in other["children"]:
                child["release_path"] = str(
                    (DEFINITION.parent / child["release_path"]).resolve()
                )
            other_definition.write_bytes(canonical_json(other))
            different = root / "different"
            federation_v2.write_federated_release_index(other_definition, different)
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError,
                "valid but not byte-identical",
            ):
                federation_v2.write_federated_release_index(DEFINITION, different)

            symlink = root / "symlink-output"
            symlink.symlink_to(different, target_is_directory=True)
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError,
                "output may not be a symlink",
            ):
                federation_v2.write_federated_release_index(DEFINITION, symlink)

            stage = root / "stage"
            destination = root / "destination"
            stage.mkdir()
            destination.mkdir()
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError, "late output collision"
            ):
                federation_v2._promote_noreplace(stage, destination)
            self.assertTrue(stage.is_dir())
            self.assertTrue(destination.is_dir())

            copied = root / "tampered"
            shutil.copytree(INDEX_DIR, copied)
            copied.chmod(0o755)
            index_path = copied / federation_v2.INDEX_FILENAME
            index_path.chmod(0o644)
            index_path.write_bytes(index_path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                federation_v2.FederatedReleaseError,
                "not canonical|checkpoint does not match",
            ):
                federation_v2.validate_federated_release_index(
                    copied, require_frozen=False
                )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, before
        )

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.federated_release_v2 import "
            "validate_federated_release_index; "
            f"result=validate_federated_release_index(Path({str(INDEX_DIR)!r})); "
            "assert result['schema_version']==2; "
            "assert result['counts']['source_scoped_entity_records']==16124; "
            "child=next(r for r in result['releases'] if r['release_id'].endswith('v59')); "
            "assert child['manifest']['current_status_inferred'] is False; "
            "assert child['manifest']['lifecycle_freshness_records']==399"
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

    def test_legacy_v25_still_validates_byte_for_byte(self) -> None:
        before = {
            path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()
        }
        validated = legacy.validate_federated_release_index(BASE_INDEX_DIR)
        self.assertEqual(validated["schema_version"], 1)
        self.assertEqual(validated["format"], legacy.INDEX_FORMAT)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()}, before
        )
        self.assertEqual(
            sha256(ROOT / "datacenter_atlas/federated_release.py"),
            CODE_PINS[ROOT / "datacenter_atlas/federated_release.py"][1],
        )


if __name__ == "__main__":
    unittest.main()
