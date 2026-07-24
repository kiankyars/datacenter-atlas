from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import copy
import csv
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

from datacenter_atlas.exact_identity_decisions import (
    ACCOUNTING_FILENAME,
    BUNDLE_FILES,
    COMPONENTS_FILENAME,
    MANIFEST_FILENAME,
    POLICY,
    RELATIONSHIPS_FILENAME,
    UNRESOLVED_FILENAME,
    ExactIdentityDecisionError,
    validate_exact_identity_decision_bundle,
    write_exact_identity_decision_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v3.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v3"
BASE_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v2.json"
)
BASE_BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v2"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v25.json"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v25"
V56_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
V56_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"

RECORDED_AT = "2026-07-20T22:55:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v55"
NEW_RELEASE_ID = "epoch-official-open-seed-v56"
PINS = {
    DEFINITION: "f78c91794e3d7e5b6873c702cca07216e25881a49d9cbab9468b8ce406d672eb",
    BASE_DEFINITION: (
        "65ffef9681c982b2149591706542c6b8277eedc22de63b2ffd2253ec94332a03"
    ),
    BASE_BUNDLE / MANIFEST_FILENAME: (
        "43724ed405b77ae64505a05a708e514bbdcf9c13044c3255908563eddb5e7d5c"
    ),
    FEDERATION_DEFINITION: (
        "2b60e26e211e584d60f6743beef1a3ed7f06714297cd36896cd2f60a0067e829"
    ),
    FEDERATION / "federated-index.json": (
        "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db"
    ),
    FEDERATION / MANIFEST_FILENAME: (
        "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f"
    ),
    V56_DEFINITION: (
        "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
    ),
    V56_RELEASE / MANIFEST_FILENAME: (
        "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd"
    ),
}
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        4_159,
        "62330d9f687d692b3acaffa8bba77612e37bdab8696409a68e73f58562daa562",
    ),
    "README.md": (
        628,
        "85f3c7bb1802e81bca4ecf5f156999c9ac896db454fff0d89fb673ea4218bd17",
    ),
    "accounting.json": (
        980,
        "51bc2f380da7a7f8251ac0e23d0c659c895666bdc3f00b87c2c6ef032b1ea280",
    ),
    "component-members.csv": (
        3_609_942,
        "0b6ab36fea045272cef97620dc8b61836f60f6234e498260dc1aaf339e685a45",
    ),
    "manifest.json": (
        11_274,
        "0eb02f73e24831df42235d5b732d09349fff77f725192a2b5221f45d43f1fcdd",
    ),
    "manifest.sha256": (
        80,
        "e3311ed905984df0115e5da6dc458e8406b63a1dce175fa4866551967fbc012a",
    ),
    "relationships.csv": (
        905_559,
        "c5abb444945c73d0be8960fd45e1f13920d73dbcfd5afaf245aaba5bae4c33a1",
    ),
    "source-lineage.csv": (
        24_551,
        "597d9341aed741c428ae18aac4d3a3252b9901866aafb72b72abab6b8f361b8a",
    ),
    "unresolved-candidate-references.csv": (
        38_419_568,
        "116fa4012989c258e79332104426b8a74a860b60cf1508151a96a4db154c4aaa",
    ),
}
BUNDLE_TREE_SHA256 = "5ce6d5a2dcd24d612b434124e7d67347e6dabb1a59e198285b1fd2ec51d63ff7"
BASE_TREE_SHA256 = "11b6b59a9e98c73289d1a5e9311be8b2470dc08c16dd806bfd777d6919ff426e"
FEDERATION_TREE_SHA256 = (
    "962a7d0733b363935f6640bc36d0930573e1c04ba91679dc7cdbef8cada83e57"
)
V56_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_317,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_230,
    "non_review_source_scoped_entity_records": 9_962,
    "raw_topology_links": 2_722,
    "release_candidate_references": 100_409,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_092,
    "unresolved_candidate_references": 100_536,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 2,
    "exact_component_reductions": 0,
    "exact_source_record_components": 4,
    "non_review_source_scoped_entity_records": 4,
    "raw_topology_links": 2,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 4,
    "unresolved_candidate_references": 0,
}
NEW_OCCURRENCES = {
    f"{NEW_RELEASE_ID}:60641b12-0fa3-5c37-af57-19625b5308b5": (
        "campus",
        "curated:paix-dkr1-dakar-data-center-campus",
    ),
    f"{NEW_RELEASE_ID}:8fa71704-253f-553f-a62a-68702411c61f": (
        "campus",
        "curated:pentapoint-emd-bkk01-sathorn-campus",
    ),
    f"{NEW_RELEASE_ID}:a75eaf2b-790f-5266-be60-3f2bafee2eeb": (
        "project",
        "curated:pentapoint-emd-bkk01-sathorn-campus:current-development",
    ),
    f"{NEW_RELEASE_ID}:be826096-5b00-5454-a880-cb133fd9bdd5": (
        "project",
        "curated:paix-dkr1-dakar-data-center-campus:current-development",
    ),
}
EXPECTED_TOPOLOGY = {
    (
        f"{NEW_RELEASE_ID}:be826096-5b00-5454-a880-cb133fd9bdd5",
        f"{NEW_RELEASE_ID}:60641b12-0fa3-5c37-af57-19625b5308b5",
    ),
    (
        f"{NEW_RELEASE_ID}:a75eaf2b-790f-5266-be60-3f2bafee2eeb",
        f"{NEW_RELEASE_ID}:8fa71704-253f-553f-a62a-68702411c61f",
    ),
}
FORBIDDEN = (
    "epoch-official-open-seed-v55",
    "federated_indexes/2026-07-20-public-open-v24",
    "releases/2026-07-20-open-seed-v55",
    "google-bermuda-hundred-chesterfield",
    "curated:google-bermuda-hundred-chesterfield-campus",
    "aligned-iad06-frederick-topout",
    "curated:aligned-quantum-frederick-campus",
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


class ExactIdentityDecisionV3Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v3 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_tree_double_offline_reproduction_and_modes(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(BASE_BUNDLE), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)
        self.assertEqual(tree_digest(V56_RELEASE), V56_TREE_SHA256)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(BUNDLE.is_symlink())
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        frozen = {}
        for path in BUNDLE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
            frozen[path.name] = path.read_bytes()

        with ExitStack() as stack:
            self._offline(stack)
            first = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
            second = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
            idempotent = write_exact_identity_decision_bundle(DEFINITION, BUNDLE)
        self.assertEqual(first, second)
        self.assertEqual(first, idempotent)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )
        self.assertEqual(first["scope"], POLICY)
        self.assertIsNone(first["counts"]["unique_physical_sites"])
        self.assertIsNone(first["counts"]["physical_site_lower_bound"])
        self.assertIsNone(first["counts"]["physical_site_upper_bound"])
        for key, expected in EXPECTED_COUNTS.items():
            self.assertEqual(first["counts"][key], expected, key)

        payload = b"".join([DEFINITION.read_bytes(), *frozen.values()])
        for marker in FORBIDDEN:
            self.assertNotIn(marker.encode(), payload)

    def test_definition_replaces_only_v55_v24_lineage_and_expected_counts(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = copy.deepcopy(base)
        expected["bundle_id"] = "2026-07-20-public-open-v3"
        expected["recorded_at"] = RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": PINS[FEDERATION / "federated-index.json"],
            "expected_manifest_sha256": PINS[FEDERATION / MANIFEST_FILENAME],
            "index_path": "../federated_indexes/2026-07-20-public-open-v25",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[V56_RELEASE / MANIFEST_FILENAME],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v56",
            }
        )
        expected["expected"] = EXPECTED_COUNTS
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)

        base_accounting = json.loads((BASE_BUNDLE / ACCOUNTING_FILENAME).read_text())
        accounting = json.loads((BUNDLE / ACCOUNTING_FILENAME).read_text())
        self.assertEqual(
            {key: accounting[key] - base_accounting[key] for key in EXPECTED_DELTA},
            EXPECTED_DELTA,
        )
        self.assertEqual(accounting["exact_component_reductions"], 1_732)
        self.assertIsNone(accounting["unique_physical_sites"])
        self.assertIsNone(accounting["physical_site_lower_bound"])
        self.assertIsNone(accounting["physical_site_upper_bound"])

        manifest = json.loads((BUNDLE / MANIFEST_FILENAME).read_text())
        self.assertEqual(manifest["bundle_id"], "2026-07-20-public-open-v3")
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["scope"], POLICY)
        self.assertEqual(
            manifest["definition"],
            {
                "bytes": DEFINITION.stat().st_size,
                "file": DEFINITION.name,
                "sha256": PINS[DEFINITION],
            },
        )
        self.assertEqual(
            manifest["federation_input"]["federated_index"]["sha256"],
            PINS[FEDERATION / "federated-index.json"],
        )
        self.assertEqual(
            manifest["federation_input"]["manifest"]["sha256"],
            PINS[FEDERATION / MANIFEST_FILENAME],
        )
        children = {row["release_id"]: row for row in manifest["input_children"]}
        self.assertEqual(
            set(children), {NEW_RELEASE_ID, "global-open-v3", "osm-fuzzy-review-v2"}
        )
        self.assertEqual(
            children[NEW_RELEASE_ID]["manifest"]["sha256"],
            PINS[V56_RELEASE / MANIFEST_FILENAME],
        )
        self.assertEqual(
            children["osm-fuzzy-review-v2"]["disposition"],
            "excluded_review_only",
        )

    def test_four_new_occurrences_are_singletons_with_two_explicit_links(self) -> None:
        with (BUNDLE / COMPONENTS_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            all_components = list(csv.DictReader(source))
        rows = {
            row["occurrence_id"]: row
            for row in all_components
            if row["occurrence_id"] in NEW_OCCURRENCES
        }
        self.assertEqual(set(rows), set(NEW_OCCURRENCES))
        component_counts = Counter(row["component_id"] for row in all_components)
        for occurrence_id, (kind, stable_key) in NEW_OCCURRENCES.items():
            row = rows[occurrence_id]
            self.assertEqual(row["release_id"], NEW_RELEASE_ID)
            self.assertEqual(row["entity_kind"], kind)
            self.assertEqual(row["stable_key"], stable_key)
            self.assertEqual(row["component_member_count"], "1")
            self.assertEqual(component_counts[row["component_id"]], 1)
            self.assertEqual(row["identity_proof_parent_occurrence_id"], "")
            self.assertEqual(row["identity_proof_token"], "")
            self.assertEqual(row["typed_identity_tokens_json"], "[]")
            self.assertEqual(row["ambiguous_identity_tokens_json"], "[]")

        component_for = {
            occurrence_id: row["component_id"] for occurrence_id, row in rows.items()
        }
        occurrence_for_component = {
            component_id: occurrence_id
            for occurrence_id, component_id in component_for.items()
        }
        new_component_ids = set(occurrence_for_component)
        with (BUNDLE / RELATIONSHIPS_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            relationships = [
                row
                for row in csv.DictReader(source)
                if row["subject_component_id"] in new_component_ids
                or row["object_component_id"] in new_component_ids
            ]
        self.assertEqual(len(relationships), 2)
        observed_topology = set()
        for row in relationships:
            self.assertEqual(row["relationship_type"], "project_targets")
            self.assertEqual(row["decision_basis"], "explicit_parent")
            self.assertEqual(row["typed_identity_tokens_json"], "[]")
            self.assertEqual(row["source_release_ids_json"], f'["{NEW_RELEASE_ID}"]')
            self.assertEqual(row["raw_relationship_count"], "1")
            observed_topology.add(
                (
                    occurrence_for_component[row["subject_component_id"]],
                    occurrence_for_component[row["object_component_id"]],
                )
            )
        self.assertEqual(observed_topology, EXPECTED_TOPOLOGY)

        with (BUNDLE / UNRESOLVED_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            reader = csv.DictReader(source)
            self.assertFalse(
                {"name", "latitude", "longitude", "distance", "score"}
                & set(reader.fieldnames or [])
            )
            unresolved = list(reader)
        self.assertFalse(
            any(
                occurrence_id in {row["left_occurrence_id"], row["right_occurrence_id"]}
                for occurrence_id in NEW_OCCURRENCES
                for row in unresolved
            )
        )

    def test_both_import_layouts_validate_same_frozen_bundle_offline(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.exact_identity_decisions"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.exact_identity_decisions"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
from pathlib import Path
import socket
from unittest.mock import patch
from {package} import validate_exact_identity_decision_bundle

with ExitStack() as stack:
    error = AssertionError("network access")
    for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        stack.enter_context(patch.object(socket, name, side_effect=error))
    result = validate_exact_identity_decision_bundle(
        Path({str(BUNDLE)!r}),
        definition_path=Path({str(DEFINITION)!r}),
        verify_inputs=False,
    )
assert result["counts"]["exact_source_record_components"] == 8230
assert result["counts"]["canonical_topology_links"] == 2317
assert result["counts"]["unique_physical_sites"] is None
assert result["scope"] == {POLICY!r}
"""
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_version_collision_with_changed_definition_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=DEFINITION.parent) as temporary:
            path = Path(temporary) / DEFINITION.name
            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            definition_parent = DEFINITION.parent
            federation = (
                definition_parent / document["federation"]["index_path"]
            ).resolve()
            document["federation"]["index_path"] = os.path.relpath(
                federation, path.parent
            )
            for child in document["children"]:
                release = (definition_parent / child["release_path"]).resolve()
                child["release_path"] = os.path.relpath(release, path.parent)
            document["recorded_at"] = "2026-07-20T22:56:00Z"
            path.write_bytes(canonical_json(document))
            with ExitStack() as stack:
                self._offline(stack)
                with self.assertRaisesRegex(
                    ExactIdentityDecisionError,
                    "definition checkpoint|byte-identical",
                ):
                    write_exact_identity_decision_bundle(path, BUNDLE)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
