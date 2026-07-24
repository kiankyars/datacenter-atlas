from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
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

from datacenter_atlas import exact_identity_decisions as legacy
from datacenter_atlas.datacenter_atlas import (
    exact_identity_decisions_v2 as identity_v2,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v4.json"
)
BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v4"
BASE_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v3.json"
)
BASE_BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v3"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v26"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
GLOBAL_RELEASE = ROOT / "releases/2026-07-18-global-open-v3"
REVIEW_RELEASE = ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"

RECORDED_AT = "2026-07-21T03:40:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v56"
NEW_RELEASE_ID = "epoch-official-open-seed-v59"
REVIEW_RELEASE_ID = "osm-fuzzy-review-v2"

PINS = {
    DEFINITION: "999a843a2b997fe5e378b52d85a14adf7650e460e63d6756813328bd8d091067",
    BASE_DEFINITION: (
        "f78c91794e3d7e5b6873c702cca07216e25881a49d9cbab9468b8ce406d672eb"
    ),
    BASE_BUNDLE / "manifest.json": (
        "0eb02f73e24831df42235d5b732d09349fff77f725192a2b5221f45d43f1fcdd"
    ),
    FEDERATION / "federated-index.json": (
        "df5f32a7b843e96ca6cf26aacbcf4b501614bcb57fd0f84ac8dea6889640ce53"
    ),
    FEDERATION / "manifest.json": (
        "7c46daa54ea1de6da325f495f4a54fda2e1c16bae3a0ca7fdb6901ba7d391361"
    ),
    V59_RELEASE / "manifest.json": (
        "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
    ),
    GLOBAL_RELEASE / "manifest.json": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    REVIEW_RELEASE / "manifest.json": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}

LEGACY_CODE_PINS = {
    ROOT / "datacenter_atlas/exact_identity_decisions.py": (
        76_330,
        "8c5d7fd14575d7f6afdb280144868534c9934753e96658498200a15833ccdfe1",
    ),
    ROOT / "scripts/build_exact_identity_decisions.py": (
        2_460,
        "42bf359a6cf19176bb739cffbb9396b42a4588f1b61796f10f090f91cbc63a45",
    ),
}

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        4_880,
        "16bac4f7d8923ffb3c1f5fec3c57a8eb774f83c023f0c2b1ccad547cb6e683e3",
    ),
    "README.md": (
        628,
        "6ea30f44877d8d1adf2aef9a02191bea93995b7270e1093f6212c6cf62f0d309",
    ),
    "accounting.json": (
        980,
        "ffba9dc6e35b3b22bf757172fa20090de0838ab6086f5e38153ef24e789a0ee4",
    ),
    "component-members.csv": (
        3_621_939,
        "eaab632b50d541ec1f025e1c08b725f8d0e66b49ea987d00d171e8a677ac652f",
    ),
    "manifest.json": (
        11_437,
        "396d65418437399874ba9d748e72ed1f7031dbcd5c9fa280dc2c2240f9b29058",
    ),
    "manifest.sha256": (
        80,
        "6383d9d9bf9b6a022ddd7a462c9665743c98a450a1c42b0eb0f3ae7d212e71b7",
    ),
    "relationships.csv": (
        910_503,
        "ed45d24d5326a71d26cb020ee2c46f8d49f7ca6d0aa1d2a8be895597ca27f5ec",
    ),
    "source-lineage.csv": (
        27_747,
        "d67a6778f6ff93e54ab2d3226f007940a6d58847ded4dad8544483eaa0001a1a",
    ),
    "unresolved-candidate-references.csv": (
        38_419_992,
        "6c1b8bcf141c09b30b49a7cd59b0c36dac4b5c8a769a01f107dfad4a32da2ce4",
    ),
}
BUNDLE_TREE_SHA256 = "f120065893ba382633931ffe802f08a718c5115b2c64837fac2a1d0bd76631af"
BASE_TREE_SHA256 = "5ce6d5a2dcd24d612b434124e7d67347e6dabb1a59e198285b1fd2ec51d63ff7"

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_333,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_262,
    "non_review_source_scoped_entity_records": 9_994,
    "raw_topology_links": 2_738,
    "release_candidate_references": 100_410,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_124,
    "unresolved_candidate_references": 100_537,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 16,
    "exact_component_reductions": 0,
    "exact_source_record_components": 32,
    "non_review_source_scoped_entity_records": 32,
    "raw_topology_links": 16,
    "release_candidate_references": 1,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 32,
    "unresolved_candidate_references": 1,
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


class ExactIdentityDecisionV4Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v4 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_tree_scope_and_legacy_v3_preservation(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        for path, (size, digest) in LEGACY_CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), (size, digest))
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(BASE_BUNDLE), BASE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, identity_v2.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])

        manifest = identity_v2.validate_exact_identity_decision_bundle(BUNDLE)
        self.assertEqual(manifest["scope"], identity_v2.POLICY)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertIsNone(manifest["counts"]["unique_physical_sites"])
        self.assertIsNone(manifest["counts"]["physical_site_lower_bound"])
        self.assertIsNone(manifest["counts"]["physical_site_upper_bound"])
        for key, expected in EXPECTED_COUNTS.items():
            self.assertEqual(manifest["counts"][key], expected, key)

    def test_definition_is_exact_v59_v26_successor_and_count_delta(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["bundle_id"] = "2026-07-20-public-open-v4"
        expected["recorded_at"] = RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": PINS[FEDERATION / "federated-index.json"],
            "expected_manifest_sha256": PINS[FEDERATION / "manifest.json"],
            "index_path": "../federated_indexes/2026-07-20-public-open-v26",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[V59_RELEASE / "manifest.json"],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v59",
            }
        )
        expected["expected"] = EXPECTED_COUNTS
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertTrue(DEFINITION.name.startswith("exact-identity-decisions-2026-07-20"))
        self.assertTrue(BUNDLE.name.startswith("2026-07-20"))

        base_accounting = json.loads(
            (BASE_BUNDLE / "accounting.json").read_text(encoding="utf-8")
        )
        accounting = json.loads(
            (BUNDLE / "accounting.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {key: accounting[key] - base_accounting[key] for key in EXPECTED_DELTA},
            EXPECTED_DELTA,
        )

        manifest = json.loads(
            (BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["federation_input"]["federated_index"]["sha256"],
            PINS[FEDERATION / "federated-index.json"],
        )
        self.assertEqual(
            manifest["federation_input"]["manifest"]["sha256"],
            PINS[FEDERATION / "manifest.json"],
        )
        children = {row["release_id"]: row for row in manifest["input_children"]}
        self.assertEqual(
            set(children), {NEW_RELEASE_ID, "global-open-v3", REVIEW_RELEASE_ID}
        )
        expected_child_pins = {
            NEW_RELEASE_ID: PINS[V59_RELEASE / "manifest.json"],
            "global-open-v3": PINS[GLOBAL_RELEASE / "manifest.json"],
            REVIEW_RELEASE_ID: PINS[REVIEW_RELEASE / "manifest.json"],
        }
        for release_id, digest in expected_child_pins.items():
            self.assertEqual(children[release_id]["manifest"]["sha256"], digest)
        self.assertEqual(children[REVIEW_RELEASE_ID]["disposition"], "excluded_review_only")
        self.assertEqual(children[REVIEW_RELEASE_ID]["source_scoped_entity_records"], 6_130)
        self.assertIn("lifecycle_freshness.csv", children[NEW_RELEASE_ID]["files"])
        review_occurrence_prefix = f"{REVIEW_RELEASE_ID}:".encode()
        for name in (
            "component-members.csv",
            "relationships.csv",
            "source-lineage.csv",
            "unresolved-candidate-references.csv",
        ):
            self.assertNotIn(review_occurrence_prefix, (BUNDLE / name).read_bytes())

    def test_v2_lifecycle_descriptor_is_preserved_and_tamper_fails_closed(self) -> None:
        index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        descriptor = next(
            item for item in index["releases"] if item["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(
            descriptor["manifest"],
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
                "sha256": PINS[V59_RELEASE / "manifest.json"],
            },
        )
        definition = legacy._load_definition(DEFINITION)

        inferred = deepcopy(index)
        inferred_descriptor = next(
            item
            for item in inferred["releases"]
            if item["release_id"] == NEW_RELEASE_ID
        )
        inferred_descriptor["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            identity_v2.ExactIdentityDecisionError,
            "current_status_inferred must be false",
        ):
            identity_v2._inspect_children(definition, inferred)

        incomplete = deepcopy(index)
        incomplete_descriptor = next(
            item
            for item in incomplete["releases"]
            if item["release_id"] == NEW_RELEASE_ID
        )
        del incomplete_descriptor["manifest"]["lifecycle_status_semantics"]
        with self.assertRaisesRegex(
            identity_v2.ExactIdentityDecisionError,
            "freshness fields must be present together",
        ):
            identity_v2._inspect_children(definition, incomplete)

        wrong_count = deepcopy(index)
        count_descriptor = next(
            item
            for item in wrong_count["releases"]
            if item["release_id"] == NEW_RELEASE_ID
        )
        count_descriptor["manifest"]["lifecycle_freshness_records"] = 398
        with self.assertRaisesRegex(
            identity_v2.ExactIdentityDecisionError,
            "lifecycle descriptor does not reconcile",
        ):
            identity_v2._inspect_children(definition, wrong_count)

    def test_tampered_lifecycle_row_fails_before_identity_output(self) -> None:
        definition = legacy._load_definition(DEFINITION)
        index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory(
            prefix="exact-identity-v4-lifecycle-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V59_RELEASE.name
            shutil.copytree(V59_RELEASE, copied)
            copied.chmod(0o755)
            freshness_path = copied / "lifecycle_freshness.csv"
            freshness_path.chmod(0o644)
            raw = freshness_path.read_text(encoding="utf-8")
            self.assertIn(",false\n", raw)
            freshness_path.write_text(
                raw.replace(",false\n", ",true\n", 1), encoding="utf-8"
            )
            manifest_path = copied / "manifest.json"
            manifest_path.chmod(0o644)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["lifecycle_freshness.csv"] = {
                "bytes": freshness_path.stat().st_size,
                "sha256": sha256(freshness_path),
            }
            manifest_path.write_bytes(canonical_json(manifest))

            children = []
            for child in definition.children:
                value = dict(child)
                if value["release_id"] == NEW_RELEASE_ID:
                    value["release_path"] = copied
                    value["expected_manifest_sha256"] = sha256(manifest_path)
                children.append(value)
            tampered_definition = replace(definition, children=tuple(children))
            tampered_index = deepcopy(index)
            tampered_descriptor = next(
                item
                for item in tampered_index["releases"]
                if item["release_id"] == NEW_RELEASE_ID
            )
            tampered_descriptor["manifest"]["bytes"] = manifest_path.stat().st_size
            tampered_descriptor["manifest"]["sha256"] = sha256(manifest_path)
            tampered_descriptor["files"] = deepcopy(manifest["files"])
            with self.assertRaisesRegex(
                identity_v2.ExactIdentityDecisionError,
                "lifecycle rows are invalid.*implies current status",
            ):
                identity_v2._inspect_children(tampered_definition, tampered_index)

    def test_offline_reconstruction_is_exact_idempotent_and_no_replace(self) -> None:
        frozen = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="exact-identity-v4-rebuild-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / BUNDLE.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = identity_v2._prepare_bundle
                with patch.object(
                    identity_v2, "_prepare_bundle", wraps=wrapped
                ) as rebuild:
                    built = identity_v2.write_exact_identity_decision_bundle(
                        DEFINITION, reproduced
                    )
                self.assertGreaterEqual(rebuild.call_count, 2)
                validated = identity_v2.validate_exact_identity_decision_bundle(
                    reproduced,
                    definition_path=DEFINITION,
                    verify_inputs=True,
                )
            self.assertEqual(built, validated)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()},
                frozen,
            )

            collision = Path(temporary) / "collision"
            collision.write_bytes(b"do-not-replace\n")
            before_collision = collision.read_bytes()
            with self.assertRaises(identity_v2.ExactIdentityDecisionError):
                identity_v2.write_exact_identity_decision_bundle(
                    DEFINITION, collision
                )
            self.assertEqual(collision.read_bytes(), before_collision)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )

    def test_cli_validate_and_both_import_layouts(self) -> None:
        environments = []
        for cwd, module in (
            (ROOT, "datacenter_atlas.exact_identity_decisions_v2"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.exact_identity_decisions_v2"),
        ):
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPATH"] = str(cwd)
            environments.append((cwd, module, environment))
        for cwd, module, environment in environments:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        f"import {module} as m; "
                        "assert m.validate_exact_identity_decision_bundle"
                    ),
                ],
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
