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

try:
    from datacenter_atlas.datacenter_atlas import exact_identity_decisions as legacy
    from datacenter_atlas.datacenter_atlas import (
        exact_identity_decisions_v3 as identity_v3,
    )
except ModuleNotFoundError:
    from datacenter_atlas import exact_identity_decisions as legacy
    from datacenter_atlas import exact_identity_decisions_v3 as identity_v3


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v5.json"
)
BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v5"
BASE_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v4.json"
)
BASE_BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v4"
FEDERATION_DEFINITION = (
    ROOT / "sources/federation-2026-07-20-public-open-v27.json"
)
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v27"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
GLOBAL_RELEASE = ROOT / "releases/2026-07-18-global-open-v3"
REVIEW_RELEASE = ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"

RECORDED_AT = "2026-07-21T04:50:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v59"
NEW_RELEASE_ID = "epoch-official-open-seed-v62"
REVIEW_RELEASE_ID = "osm-fuzzy-review-v2"

PINS = {
    DEFINITION: "c5a33ae467c2187157d5799a17d81f08c49d623926303641ebb21cd15f7192d7",
    BASE_DEFINITION: (
        "999a843a2b997fe5e378b52d85a14adf7650e460e63d6756813328bd8d091067"
    ),
    BASE_BUNDLE / "manifest.json": (
        "396d65418437399874ba9d748e72ed1f7031dbcd5c9fa280dc2c2240f9b29058"
    ),
    FEDERATION_DEFINITION: (
        "4f0bbb0fcef771966f9d18cdcc28691b4adeb1b9b60d6f2af95fd4c6e592499e"
    ),
    FEDERATION / "federated-index.json": (
        "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8"
    ),
    FEDERATION / "manifest.json": (
        "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87"
    ),
    FEDERATION / "manifest.sha256": (
        "93af947986aa0fc77fb871521dacf09c9bf8111f17212d19caa9942a03694207"
    ),
    V62_DEFINITION: (
        "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
    ),
    V62_RELEASE / "manifest.json": (
        "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
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
    ROOT / "datacenter_atlas/exact_identity_decisions_v2.py": (
        17_022,
        "be46adacf4f1d67001be30f55db20320f8e7e823daa18309f8a5102078040f0f",
    ),
    ROOT / "exact_identity_decisions_v2.py": (
        146,
        "ea1a51e4ef7ce4c0b41f98627dde91a2e0c5753eb0e5718bda2fe7259b7db6f7",
    ),
    ROOT / "scripts/build_exact_identity_decisions_v2.py": (
        2_327,
        "5a789d69aeb5c9414639fb3f3b6942ada77f56f83155a43d76eeaaf84eb47b55",
    ),
}

V3_CODE_PINS = {
    ROOT / "datacenter_atlas/exact_identity_decisions_v3.py": (
        16_965,
        "a8ecbfb51237b9925d6a659973407e4353e83b4e25c2fee216b00806904a6ab5",
    ),
    ROOT / "exact_identity_decisions_v3.py": (
        147,
        "99c86b224e2e99677b9ff7fa97313b09af985baf2d597597c1d3ace41b0f4c84",
    ),
    ROOT / "scripts/build_exact_identity_decisions_v3.py": (
        2_328,
        "a0c83f8fb36cc1d8195d257add8bc94d5903c7ed6c55abb3705a6aa314813ae2",
    ),
}

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        5_229,
        "e69c0eb57341781958e5f119b8e3aa90776fb4293fe60862994eb9eb1a78f9fc",
    ),
    "README.md": (
        629,
        "926e1a41d20e7077847f63706a11610d197cb30fced41dfca886494a645494fc",
    ),
    "accounting.json": (
        981,
        "d26c6e1fbf3502ea68e2209e86355bc872826a60e351f884c69bb1b1516c42a5",
    ),
    "component-members.csv": (
        3_632_946,
        "cbd8169646d0c5c982d317101e2e7ebae5e9e367318ae0bdff1f184397ccf4aa",
    ),
    "manifest.json": (
        11_438,
        "9bb5c1ef49fe1bf3904c2dca080ef5ab51de014935f1792a2bc99c0888bb68b5",
    ),
    "manifest.sha256": (
        80,
        "c1460885a92386abdc39831e8982df77aab0b3e83765a3f9b27cbc552a61dbc6",
    ),
    "relationships.csv": (
        915_447,
        "a9029db7a08b0ce3c5b919228485671c46f29dc68764c9fea927e269a6b50a1c",
    ),
    "source-lineage.csv": (
        29_582,
        "907a46cf8746a6a45da9a4db790bea5fc75b06d6d86fd40ca975584e2dbe67ed",
    ),
    "unresolved-candidate-references.csv": (
        38_419_992,
        "df29fe1811f96ed82971034bb01046536d2e246a3db5172bc4b430935f3e800a",
    ),
}
BUNDLE_TREE_SHA256 = "5fabf0ac8f28bc59c9969fb6a50240797ec0a440c2a534388aea9f0a2f9c64e6"
BASE_TREE_SHA256 = "f120065893ba382633931ffe802f08a718c5115b2c64837fac2a1d0bd76631af"
FEDERATION_TREE_SHA256 = (
    "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671"
)

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_349,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_293,
    "non_review_source_scoped_entity_records": 10_025,
    "raw_topology_links": 2_754,
    "release_candidate_references": 100_410,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_155,
    "unresolved_candidate_references": 100_537,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 16,
    "exact_component_reductions": 0,
    "exact_source_record_components": 31,
    "non_review_source_scoped_entity_records": 31,
    "raw_topology_links": 16,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 31,
    "unresolved_candidate_references": 0,
}

POST_V62_INPUTS = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json",
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json",
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


class ExactIdentityDecisionV5Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v5 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_tree_scope_and_legacy_v4_preservation(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        for path, (size, digest) in LEGACY_CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), (size, digest))
        for path, (size, digest) in V3_CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), (size, digest))
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(BASE_BUNDLE), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, identity_v3.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])

        manifest = identity_v3.validate_exact_identity_decision_bundle(BUNDLE)
        base_manifest = json.loads(
            (BASE_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["scope"], identity_v3.POLICY)
        self.assertEqual(manifest["scope"], base_manifest["scope"])
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertIsNone(manifest["counts"]["unique_physical_sites"])
        self.assertIsNone(manifest["counts"]["physical_site_lower_bound"])
        self.assertIsNone(manifest["counts"]["physical_site_upper_bound"])
        for key, expected in EXPECTED_COUNTS.items():
            self.assertEqual(manifest["counts"][key], expected, key)
        for name in (
            "component-members.csv",
            "relationships.csv",
            "source-lineage.csv",
            "unresolved-candidate-references.csv",
        ):
            self.assertEqual(
                (BUNDLE / name).read_bytes().splitlines()[0],
                (BASE_BUNDLE / name).read_bytes().splitlines()[0],
            )

    def test_definition_is_exact_v62_v27_successor_and_count_delta(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["bundle_id"] = "2026-07-20-public-open-v5"
        expected["recorded_at"] = RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": PINS[FEDERATION / "federated-index.json"],
            "expected_manifest_sha256": PINS[FEDERATION / "manifest.json"],
            "index_path": "../federated_indexes/2026-07-20-public-open-v27",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[V62_RELEASE / "manifest.json"],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v62",
            }
        )
        expected["expected"] = EXPECTED_COUNTS
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertTrue(DEFINITION.name.startswith("exact-identity-decisions-2026-07-20"))
        self.assertTrue(BUNDLE.name.startswith("2026-07-20"))

        for path in (DEFINITION, *BUNDLE.iterdir()):
            self.assertNotIn(b"public-open-v26", path.read_bytes(), path)

        v62_definition = json.loads(V62_DEFINITION.read_text(encoding="utf-8"))
        v62_inputs = {row["path"] for row in v62_definition["curated_inputs"]}
        self.assertTrue(POST_V62_INPUTS.isdisjoint(v62_inputs))

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
            NEW_RELEASE_ID: PINS[V62_RELEASE / "manifest.json"],
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

    def test_v3_lifecycle_descriptor_is_preserved_and_tamper_fails_closed(self) -> None:
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
                "bytes": 10_934,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 415,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T04:35:00Z",
                "sha256": PINS[V62_RELEASE / "manifest.json"],
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
            identity_v3.ExactIdentityDecisionError,
            "current_status_inferred must be false",
        ):
            identity_v3._inspect_children(definition, inferred)

        incomplete = deepcopy(index)
        incomplete_descriptor = next(
            item
            for item in incomplete["releases"]
            if item["release_id"] == NEW_RELEASE_ID
        )
        del incomplete_descriptor["manifest"]["lifecycle_status_semantics"]
        with self.assertRaisesRegex(
            identity_v3.ExactIdentityDecisionError,
            "freshness fields must be present together",
        ):
            identity_v3._inspect_children(definition, incomplete)

        wrong_count = deepcopy(index)
        count_descriptor = next(
            item
            for item in wrong_count["releases"]
            if item["release_id"] == NEW_RELEASE_ID
        )
        count_descriptor["manifest"]["lifecycle_freshness_records"] = 414
        with self.assertRaisesRegex(
            identity_v3.ExactIdentityDecisionError,
            "lifecycle descriptor does not reconcile",
        ):
            identity_v3._inspect_children(definition, wrong_count)

    def test_tampered_lifecycle_row_fails_before_identity_output(self) -> None:
        definition = legacy._load_definition(DEFINITION)
        index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory(
            prefix="exact-identity-v5-lifecycle-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / V62_RELEASE.name
            shutil.copytree(V62_RELEASE, copied)
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
                identity_v3.ExactIdentityDecisionError,
                "lifecycle rows are invalid.*implies current status",
            ):
                identity_v3._inspect_children(tampered_definition, tampered_index)

    def test_offline_reconstruction_is_exact_idempotent_and_no_replace(self) -> None:
        frozen = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="exact-identity-v5-rebuild-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / BUNDLE.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = identity_v3._prepare_bundle
                with patch.object(
                    identity_v3, "_prepare_bundle", wraps=wrapped
                ) as rebuild:
                    built = identity_v3.write_exact_identity_decision_bundle(
                        DEFINITION, reproduced
                    )
                self.assertGreaterEqual(rebuild.call_count, 2)
                validated = identity_v3.validate_exact_identity_decision_bundle(
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
            with self.assertRaises(identity_v3.ExactIdentityDecisionError):
                identity_v3.write_exact_identity_decision_bundle(
                    DEFINITION, collision
                )
            self.assertEqual(collision.read_bytes(), before_collision)

            symlink = Path(temporary) / "symlink"
            symlink.symlink_to(BUNDLE, target_is_directory=True)
            with self.assertRaisesRegex(
                identity_v3.ExactIdentityDecisionError,
                "decision output may not be a symlink",
            ):
                identity_v3.write_exact_identity_decision_bundle(
                    DEFINITION, symlink
                )
            self.assertTrue(symlink.is_symlink())

            mode_tampered = Path(temporary) / "mode-tampered"
            shutil.copytree(BUNDLE, mode_tampered)
            mode_tampered.chmod(0o755)
            with self.assertRaisesRegex(
                identity_v3.ExactIdentityDecisionError,
                "decision bundle is not frozen",
            ):
                identity_v3.validate_exact_identity_decision_bundle(mode_tampered)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )

    def test_cli_validate_and_both_import_layouts(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
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

        environments = []
        for cwd, module in (
            (ROOT, "datacenter_atlas.exact_identity_decisions_v3"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.exact_identity_decisions_v3"),
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
