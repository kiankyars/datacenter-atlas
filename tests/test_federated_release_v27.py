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
    from datacenter_atlas.datacenter_atlas import federated_release_v3 as federation_v3
except ModuleNotFoundError:
    from datacenter_atlas import federated_release as legacy
    from datacenter_atlas import federated_release_v2 as federation_v2
    from datacenter_atlas import federated_release_v3 as federation_v3


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v27.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v27"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v26.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v26"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"

GENERATED_AT = "2026-07-21T04:45:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v59"
NEW_RELEASE_ID = "epoch-official-open-seed-v62"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "4f0bbb0fcef771966f9d18cdcc28691b4adeb1b9b60d6f2af95fd4c6e592499e"
INDEX_SHA256 = "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8"
MANIFEST_SHA256 = "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87"
SIDECAR_SHA256 = "93af947986aa0fc77fb871521dacf09c9bf8111f17212d19caa9942a03694207"
TREE_SHA256 = "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671"

BASE_DEFINITION_SHA256 = "34a26ee6f747d3dae9a96257b6dd5e7051aacf446ce392f2c6f5087146a66b32"
BASE_INDEX_SHA256 = "df5f32a7b843e96ca6cf26aacbcf4b501614bcb57fd0f84ac8dea6889640ce53"
BASE_MANIFEST_SHA256 = "7c46daa54ea1de6da325f495f4a54fda2e1c16bae3a0ca7fdb6901ba7d391361"
BASE_SIDECAR_SHA256 = "7b36b9487f33693886d7658c6edc033d9fb5b4eda0c03f091c67f76f0237ac3a"
BASE_TREE_SHA256 = "f512cca96449fc844f6e18f72ba9705862b06563af743cb775e9ed3d6ef9ab5e"

V62_DEFINITION_SHA256 = "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
V62_MANIFEST_SHA256 = "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
V62_TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"

ARTIFACTS = {
    federation_v3.INDEX_FILENAME: (27_784, INDEX_SHA256),
    federation_v3.MANIFEST_FILENAME: (986, MANIFEST_SHA256),
    federation_v3.MANIFEST_HASH_FILENAME: (80, SIDECAR_SHA256),
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
    ROOT / "datacenter_atlas/federated_release_v3.py": (
        26_524,
        "e8504ca3bba1f201085579df20ec0cde4ebd700284e402f5104b656dd7c24528",
    ),
    ROOT / "federated_release_v3.py": (
        136,
        "eb95516c9d05b368f389b4100f08139c0d939639d833d6943a56199f1856d221",
    ),
    ROOT / "scripts/build_federated_release_index_v3.py": (
        1_720,
        "d730168e7c9f589d067d4533259ef0092d9723fbe049b4ec61862de64d8bb845",
    ),
}

EXPECTED_COUNTS = {
    "capacity_estimates": 1_288,
    "construction_pipeline_records": 6_623,
    "evidence_records": 13_457,
    "non_review_construction_pipeline_records": 493,
    "non_review_source_scoped_entity_records": 10_025,
    "release_bundles": 3,
    "resolution_candidates": 100_410,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 250,
    "source_scoped_entity_records": 16_155,
    "unique_physical_sites": None,
}

EXPECTED_DELTA = {
    "capacity_estimates": 11,
    "construction_pipeline_records": 11,
    "evidence_records": 26,
    "non_review_construction_pipeline_records": 11,
    "non_review_source_scoped_entity_records": 31,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 16,
    "source_scoped_entity_records": 31,
}

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 502,
    "construction_pipeline_records": 373,
    "entities_by_kind": {"campus": 390, "project": 340},
    "evidence_records": 444,
    "resolution_candidates": 5,
    "source_family_entries": 243,
    "source_scoped_entity_records": 730,
}

CHILDREN = {
    NEW_RELEASE_ID: V62_RELEASE,
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


class FederatedReleaseV27Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v27 federation attempted network or a stale open-seed child"
        )
        original = legacy._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            text = path.as_posix()
            if "open-seed-" in text and "open-seed-v62" not in text:
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
            INDEX_DIR / federation_v3.INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / federation_v3.MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / federation_v3.MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / legacy.INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / legacy.MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            BASE_INDEX_DIR / legacy.MANIFEST_HASH_FILENAME: BASE_SIDECAR_SHA256,
            V62_DEFINITION: V62_DEFINITION_SHA256,
            V62_RELEASE / legacy.MANIFEST_FILENAME: V62_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(BASE_INDEX_DIR), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(V62_RELEASE), V62_TREE_SHA256)
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

    def test_exact_v26_to_v62_swap_and_v2_descriptor(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item for item in expected["children"] if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V62_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v62/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v62",
            }
        )
        raw = DEFINITION.read_bytes()
        current_definition = json.loads(raw)
        self.assertEqual(raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertTrue(DEFINITION.name.startswith("federation-2026-07-20-"))
        self.assertTrue(INDEX_DIR.name.startswith("2026-07-20-"))
        v62_definition = json.loads(V62_DEFINITION.read_text(encoding="utf-8"))
        v62_inputs = {row["path"] for row in v62_definition["curated_inputs"]}
        self.assertTrue(
            {
                "sources/curated-official-2026-07-20-core-scientific-dalton-4.json",
                "sources/curated-official-2026-07-20-databank-iad6-culpeper.json",
                "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
            }.isdisjoint(v62_inputs)
        )

        base_index = json.loads(
            (BASE_INDEX_DIR / legacy.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = json.loads(
            (INDEX_DIR / federation_v3.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(current["schema_version"], 2)
        self.assertEqual(current["format"], federation_v3.INDEX_FORMAT)
        self.assertEqual(current["generated_at"], GENERATED_AT)
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation_v3.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        by_id = {item["release_id"]: item for item in current["releases"]}
        base_by_id = {item["release_id"]: item for item in base_index["releases"]}
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])

        v62 = by_id[NEW_RELEASE_ID]
        self.assertEqual(v62["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            v62["manifest"],
            {
                "as_of": "2026-07-20",
                "bytes": 10_934,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 415,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T04:35:00Z",
                "sha256": V62_MANIFEST_SHA256,
            },
        )
        self.assertIn(federation_v3.FRESHNESS_FILENAME, v62["files"])
        self.assertEqual(
            {
                key: current["counts"][key] - base_index["counts"][key]
                for key in EXPECTED_DELTA
            },
            EXPECTED_DELTA,
        )

    def test_publication_v4_failures_are_closed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation_v3.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            item for item in current["releases"] if item["release_id"] == NEW_RELEASE_ID
        )
        missing = deepcopy(descriptor)
        del missing["manifest"]["lifecycle_status_semantics"]
        with self.assertRaisesRegex(
            federation_v3.FederatedReleaseError,
            "freshness fields must be present together",
        ):
            federation_v3._validate_descriptor(missing, 0)
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation_v3.FederatedReleaseError,
            "current_status_inferred must be false",
        ):
            federation_v3._validate_descriptor(inferred, 0)

        with tempfile.TemporaryDirectory(
            prefix="federation-v27-child-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V62_RELEASE.name
            shutil.copytree(V62_RELEASE, copied)
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
                federation_v3.FederatedReleaseError,
                "current_status_inferred must be false",
            ):
                federation_v3._inspect_child(definition)

    def test_freshness_csv_rows_are_reconciled_not_just_manifest_claimed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation_v3.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            item for item in current["releases"] if item["release_id"] == NEW_RELEASE_ID
        )
        with tempfile.TemporaryDirectory(
            prefix="federation-v27-freshness-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V62_RELEASE.name
            shutil.copytree(V62_RELEASE, copied)
            copied.chmod(0o755)
            freshness = copied / federation_v3.FRESHNESS_FILENAME
            freshness.chmod(0o644)
            raw = freshness.read_text(encoding="utf-8")
            self.assertIn(",false\n", raw)
            freshness.write_text(raw.replace(",false\n", ",true\n", 1), encoding="utf-8")
            manifest_path = copied / "manifest.json"
            manifest_path.chmod(0o644)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][federation_v3.FRESHNESS_FILENAME] = {
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
                federation_v3.FederatedReleaseError,
                "freshness row implies current status",
            ):
                federation_v3._inspect_child(definition)

    def test_offline_double_rebuild_reproduction_and_child_recheck(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v27-reproduction-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / INDEX_DIR.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = federation_v3.build_federated_release_index
                with patch.object(
                    federation_v3,
                    "build_federated_release_index",
                    wraps=wrapped,
                ) as rebuild:
                    built = federation_v3.write_federated_release_index(
                        DEFINITION, reproduced
                    )
                self.assertEqual(rebuild.call_count, 2)
                validated = federation_v3.validate_federated_release_index(
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
            prefix="federation-v27-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            other_definition = root / DEFINITION.name
            other = json.loads(DEFINITION.read_text(encoding="utf-8"))
            other["generated_at"] = "2026-07-21T04:46:00Z"
            for child in other["children"]:
                child["release_path"] = str(
                    (DEFINITION.parent / child["release_path"]).resolve()
                )
            other_definition.write_bytes(canonical_json(other))
            different = root / "different"
            federation_v3.write_federated_release_index(other_definition, different)
            with self.assertRaisesRegex(
                federation_v3.FederatedReleaseError,
                "valid but not byte-identical",
            ):
                federation_v3.write_federated_release_index(DEFINITION, different)

            symlink = root / "symlink-output"
            symlink.symlink_to(different, target_is_directory=True)
            with self.assertRaisesRegex(
                federation_v3.FederatedReleaseError,
                "output may not be a symlink",
            ):
                federation_v3.write_federated_release_index(DEFINITION, symlink)

            stage = root / "stage"
            destination = root / "destination"
            stage.mkdir()
            destination.mkdir()
            with self.assertRaisesRegex(
                federation_v3.FederatedReleaseError, "late output collision"
            ):
                federation_v3._promote_noreplace(stage, destination)
            self.assertTrue(stage.is_dir())
            self.assertTrue(destination.is_dir())

            copied = root / "tampered"
            shutil.copytree(INDEX_DIR, copied)
            copied.chmod(0o755)
            index_path = copied / federation_v3.INDEX_FILENAME
            index_path.chmod(0o644)
            index_path.write_bytes(index_path.read_bytes() + b" ")
            with self.assertRaisesRegex(
                federation_v3.FederatedReleaseError,
                "not canonical|checkpoint does not match",
            ):
                federation_v3.validate_federated_release_index(
                    copied, require_frozen=False
                )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, before
        )

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.federated_release_v3 import "
            "validate_federated_release_index; "
            f"result=validate_federated_release_index(Path({str(INDEX_DIR)!r})); "
            "assert result['schema_version']==2; "
            "assert result['counts']['source_scoped_entity_records']==16155; "
            "child=next(r for r in result['releases'] if r['release_id'].endswith('v62')); "
            "assert child['manifest']['current_status_inferred'] is False; "
            "assert child['manifest']['lifecycle_freshness_records']==415"
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

    def test_frozen_v26_still_validates_byte_for_byte(self) -> None:
        before = {
            path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()
        }
        validated = federation_v2.validate_federated_release_index(BASE_INDEX_DIR)
        self.assertEqual(validated["schema_version"], 2)
        self.assertEqual(validated["format"], federation_v2.INDEX_FORMAT)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BASE_INDEX_DIR.iterdir()}, before
        )
        self.assertEqual(
            sha256(ROOT / "datacenter_atlas/federated_release.py"),
            CODE_PINS[ROOT / "datacenter_atlas/federated_release.py"][1],
        )
        self.assertEqual(
            sha256(ROOT / "datacenter_atlas/federated_release_v2.py"),
            CODE_PINS[ROOT / "datacenter_atlas/federated_release_v2.py"][1],
        )


if __name__ == "__main__":
    unittest.main()
