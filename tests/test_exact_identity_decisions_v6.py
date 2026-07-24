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
    from datacenter_atlas.datacenter_atlas import exact_identity_decisions as legacy
    from datacenter_atlas.datacenter_atlas import (
        exact_identity_decisions_v3 as identity,
    )
except ModuleNotFoundError:
    from datacenter_atlas import exact_identity_decisions as legacy
    from datacenter_atlas import exact_identity_decisions_v3 as identity


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v6.json"
)
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v6"
BASE_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v5.json"
)
BASE_BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v5"
FEDERATION = ROOT / "federated_indexes/2026-07-21-public-open-v28"
V67_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"
GLOBAL_RELEASE = ROOT / "releases/2026-07-18-global-open-v3"
REVIEW_RELEASE = ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"

RECORDED_AT = "2026-07-21T07:57:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v62"
NEW_RELEASE_ID = "epoch-official-open-seed-v67"
REVIEW_RELEASE_ID = "osm-fuzzy-review-v2"

DEFINITION_SHA256 = "2b9b26f452ebfc3d36f4bb36d9cc7198a29b8be8806657750f440a928671d759"
BUNDLE_TREE_SHA256 = "44057ef4e03b3ce4412fb4d89b7e673cf9da8a289eb13ecbca6e11dcb9a4505d"
BASE_DEFINITION_SHA256 = "c5a33ae467c2187157d5799a17d81f08c49d623926303641ebb21cd15f7192d7"
BASE_MANIFEST_SHA256 = "9bb5c1ef49fe1bf3904c2dca080ef5ab51de014935f1792a2bc99c0888bb68b5"
BASE_TREE_SHA256 = "5fabf0ac8f28bc59c9969fb6a50240797ec0a440c2a534388aea9f0a2f9c64e6"
FEDERATION_INDEX_SHA256 = "d21cfa01157dc7529d71bfd99d4f6d2bbc74285a8c58392ee402dc767faf3210"
FEDERATION_MANIFEST_SHA256 = "d465a2de75b94168113b712740a1761e93887c1bc998a5164ba54489202e5f6e"
FEDERATION_TREE_SHA256 = "88113b5342b48be3dbe663bdc4da2fe57a5de75c983220f42e2ccc822b3f501a"
V67_MANIFEST_SHA256 = "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb"

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        6166,
        "bd757e8a0ff5197b82a289693dbe7f4e0febc4d3f79e62c43aeddbc8d76a6ec2",
    ),
    "README.md": (
        629,
        "b2d71c9f85cd487f9bde46f04f370e7d1f9e9423582235cf0c23198d5acb50a6",
    ),
    "accounting.json": (
        981,
        "8dc15c12f4b6d5d0cebc309a5ab46d2eeb10b835906a43dbdd8c80d95fb8d922",
    ),
    "component-members.csv": (
        3652588,
        "bded91e58205372082ebb23ab722b2cb60ef4cc88c28c7367fccde20beb544d7",
    ),
    "manifest.json": (
        11438,
        "0af1e65f5b772b87e7dfe5b5c195513e79f31d4b5648fdcae5fd343f86f82ee9",
    ),
    "manifest.sha256": (
        80,
        "97bf2944ac0670a424195a453e8382e6e056cfa65ec06442050f68b7ceacab06",
    ),
    "relationships.csv": (
        924099,
        "673a106bd8e406612be6ebaa71519965cb2031083c22833de448c49aa16727b7",
    ),
    "source-lineage.csv": (
        33318,
        "8aa4280838376602490b928c82a8d20c5f83729bfec4ec0a366511c5250ef8dd",
    ),
    "unresolved-candidate-references.csv": (
        38420416,
        "e1402493cb8ed8a38a1b73c7ddb0767b61406409b53ac292c3ec9c816474a67f",
    ),
}
EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2377,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8346,
    "non_review_source_scoped_entity_records": 10078,
    "raw_topology_links": 2782,
    "release_candidate_references": 100411,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16208,
    "unresolved_candidate_references": 100538,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 28,
    "exact_component_reductions": 0,
    "exact_source_record_components": 53,
    "non_review_source_scoped_entity_records": 53,
    "raw_topology_links": 28,
    "release_candidate_references": 1,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 53,
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


class ExactIdentityDecisionV6Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v6 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_trees_and_v5_preservation(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_BUNDLE / identity.MANIFEST_FILENAME), BASE_MANIFEST_SHA256
        )
        self.assertEqual(
            sha256(FEDERATION / "federated-index.json"), FEDERATION_INDEX_SHA256
        )
        self.assertEqual(
            sha256(FEDERATION / "manifest.json"), FEDERATION_MANIFEST_SHA256
        )
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(BASE_BUNDLE), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, identity.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])

    def test_definition_is_exact_v5_successor_and_deltas_are_derived(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["bundle_id"] = "2026-07-21-public-open-v6"
        expected["recorded_at"] = RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": FEDERATION_INDEX_SHA256,
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "index_path": "../federated_indexes/2026-07-21-public-open-v28",
        }
        child = next(
            row for row in expected["children"] if row["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V67_MANIFEST_SHA256,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v67",
            }
        )
        expected["expected"] = EXPECTED_COUNTS
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)

        base_accounting = json.loads(
            (BASE_BUNDLE / identity.ACCOUNTING_FILENAME).read_text(encoding="utf-8")
        )
        accounting = json.loads(
            (BUNDLE / identity.ACCOUNTING_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {key: accounting[key] - base_accounting[key] for key in EXPECTED_DELTA},
            EXPECTED_DELTA,
        )
        for key, value in EXPECTED_COUNTS.items():
            self.assertEqual(accounting[key], value, key)
        self.assertIsNone(accounting["unique_physical_sites"])
        self.assertIsNone(accounting["physical_site_lower_bound"])
        self.assertIsNone(accounting["physical_site_upper_bound"])

    def test_exact_only_policy_and_review_exclusion_are_explicit(self) -> None:
        manifest = identity.validate_exact_identity_decision_bundle(BUNDLE)
        base_manifest = json.loads(
            (BASE_BUNDLE / identity.MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["scope"], identity.POLICY)
        self.assertEqual(manifest["scope"], base_manifest["scope"])
        self.assertTrue(manifest["scope"]["exact_same_kind_source_record_components"])
        self.assertTrue(manifest["scope"]["explicit_topology_only"])
        self.assertFalse(manifest["scope"]["cross_kind_identity_union"])
        self.assertFalse(manifest["scope"]["automatic_physical_site_merges"])
        self.assertFalse(manifest["scope"]["review_only_rows_in_public_accounting"])

        children = {row["release_id"]: row for row in manifest["input_children"]}
        self.assertEqual(
            set(children), {NEW_RELEASE_ID, "global-open-v3", REVIEW_RELEASE_ID}
        )
        self.assertEqual(children[REVIEW_RELEASE_ID]["disposition"], "excluded_review_only")
        self.assertEqual(
            children[REVIEW_RELEASE_ID]["source_scoped_entity_records"], 6130
        )
        self.assertEqual(children[NEW_RELEASE_ID]["disposition"], "processed")
        self.assertEqual(children[NEW_RELEASE_ID]["source_scoped_entity_records"], 783)
        self.assertEqual(
            manifest["federation_input"]["federated_index"]["sha256"],
            FEDERATION_INDEX_SHA256,
        )
        self.assertEqual(
            manifest["federation_input"]["manifest"]["sha256"],
            FEDERATION_MANIFEST_SHA256,
        )

        review_prefix = f"{REVIEW_RELEASE_ID}:".encode()
        for name in (
            identity.COMPONENTS_FILENAME,
            identity.RELATIONSHIPS_FILENAME,
            identity.LINEAGE_FILENAME,
            identity.UNRESOLVED_FILENAME,
        ):
            self.assertNotIn(review_prefix, (BUNDLE / name).read_bytes(), name)

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="identity-v6-rebuild-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / BUNDLE.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = identity._prepare_bundle
                with patch.object(identity, "_prepare_bundle", wraps=wrapped) as rebuild:
                    built = identity.write_exact_identity_decision_bundle(
                        DEFINITION, reproduced
                    )
                self.assertGreaterEqual(rebuild.call_count, 2)
            validated = identity.validate_exact_identity_decision_bundle(
                reproduced,
                definition_path=DEFINITION,
                verify_inputs=True,
            )
            self.assertEqual(built, validated)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()},
                frozen,
            )
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )

    def test_descriptor_bundle_no_replace_and_symlink_fail_closed(self) -> None:
        definition = legacy._load_definition(DEFINITION)
        index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        inferred = deepcopy(index)
        descriptor = next(
            row
            for row in inferred["releases"]
            if row["release_id"] == NEW_RELEASE_ID
        )
        descriptor["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "current_status_inferred must be false"
        ):
            identity._inspect_children(definition, inferred)

        with tempfile.TemporaryDirectory(
            prefix="identity-v6-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            copied = root / "tampered"
            shutil.copytree(BUNDLE, copied)
            copied.chmod(0o755)
            component_path = copied / identity.COMPONENTS_FILENAME
            component_path.chmod(0o644)
            component_path.write_bytes(component_path.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "decision file hash mismatch|checkpoint does not match",
            ):
                identity.validate_exact_identity_decision_bundle(
                    copied, require_frozen=False
                )

            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(identity.ExactIdentityDecisionError):
                identity.write_exact_identity_decision_bundle(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            symlink = root / "symlink"
            symlink.symlink_to(BUNDLE, target_is_directory=True)
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "decision output may not be a symlink",
            ):
                identity.write_exact_identity_decision_bundle(DEFINITION, symlink)
            self.assertTrue(symlink.is_symlink())

    def test_cli_verify_inputs_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_exact_identity_decisions_v3.py",
                "--definition",
                str(DEFINITION),
                "--output-dir",
                str(BUNDLE),
                "--validate-only",
                "--verify-inputs",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["bundle_id"], BUNDLE.name)

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.exact_identity_decisions_v3 import "
            "validate_exact_identity_decision_bundle; "
            f"m=validate_exact_identity_decision_bundle(Path({str(BUNDLE)!r})); "
            "assert m['counts']['exact_source_record_components']==8346; "
            "assert m['counts']['review_only_source_scoped_entity_records']==6130; "
            "assert m['counts']['unique_physical_sites'] is None"
        )
        for working_directory in (ROOT, WORKSPACE):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
