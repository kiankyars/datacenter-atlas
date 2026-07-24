from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.exact_identity_decisions as decision_module
from datacenter_atlas.exact_identity_decisions import (
    ACCOUNTING_FILENAME,
    BUNDLE_FILES,
    COMPONENTS_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    POLICY,
    RELATIONSHIPS_FILENAME,
    UNRESOLVED_FILENAME,
    ExactIdentityDecisionError,
    validate_exact_identity_decision_bundle,
    write_exact_identity_decision_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    ROOT / "sources" / "exact-identity-decisions-2026-07-20-public-open-v1.json"
)
BUNDLE = ROOT / "exact_identity_decisions" / "2026-07-20-public-open-v1"
FEDERATION = ROOT / "federated_indexes" / "2026-07-20-public-open-v23"

DEFINITION_SHA256 = "c5a1adee3366bfa55407904074464d4d6c0c52bbbee1b523544721117582b428"
FEDERATION_INDEX_SHA256 = (
    "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2"
)
FEDERATION_MANIFEST_SHA256 = (
    "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be"
)
CHILD_MANIFEST_SHA256 = {
    "epoch-official-open-seed-v49": (
        "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
    ),
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILD_DIRECTORIES = {
    "epoch-official-open-seed-v49": ROOT / "releases" / "2026-07-20-open-seed-v49",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
ARTIFACT_SHA256 = {
    "ATTRIBUTION.txt": "f9ff197df2cd609fe972aff8c8563892db249b4ebd15abe899f6ff801c3f038d",
    "README.md": "b2dc3e0d0da1d4365a74bc6701102978457cd662971f826b0c04ab4c006f8936",
    "accounting.json": "6d43ad05673ed00fd1cdd7caae8c6f7d96f3c0f6cc6b9b22741f176ff11a2f2c",
    "component-members.csv": "e4353fd4fa1c3348ac1a5ede7d2c907a61214955cd2e2766e591364051fa6cac",
    "manifest.json": "2f892bdfd427321052676909b2109d2cdcc0fef32a80f1a805a58a621977fe96",
    "manifest.sha256": "af034b92b738d30e2afa9b4f33626d0098c5efc539e502875a82675ba77e834d",
    "relationships.csv": "fd7a85ebca719cb89f5ee0fde294b187108f5c12caa471f39358a30109dc8c1c",
    "source-lineage.csv": "43d8ebecc860bac7c7f4c9519e352cc2570ffeafcc4f9e20fab25102946fde6b",
    "unresolved-candidate-references.csv": (
        "963356b80e62f3eb8e64913574180871a02494f06f57db2785bdd58a4d58a6a2"
    ),
}
EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_298,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_192,
    "non_review_source_scoped_entity_records": 9_924,
    "raw_topology_links": 2_703,
    "release_candidate_references": 100_409,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_054,
    "unresolved_candidate_references": 100_536,
}


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rewrite_definition(path: Path, mutate) -> Path:
    document = json.loads(DEFINITION.read_text(encoding="utf-8"))
    base = path.parent.resolve()
    federation = (DEFINITION.parent / document["federation"]["index_path"]).resolve()
    document["federation"]["index_path"] = os.path.relpath(federation, base)
    for child in document["children"]:
        release = (DEFINITION.parent / child["release_path"]).resolve()
        child["release_path"] = os.path.relpath(release, base)
    mutate(document)
    path.write_bytes(canonical_json(document))
    return path


def thaw(directory: Path) -> None:
    directory.chmod(0o755)
    for path in directory.iterdir():
        if not path.is_symlink():
            path.chmod(0o644)


def freeze(directory: Path) -> None:
    for path in directory.iterdir():
        if not path.is_symlink():
            path.chmod(0o444)
    directory.chmod(0o555)


class ExactIdentityDecisionV1Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v1 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_exact_accounting_and_double_offline_validation(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(
            sha256(FEDERATION / "federated-index.json"), FEDERATION_INDEX_SHA256
        )
        self.assertEqual(
            sha256(FEDERATION / MANIFEST_FILENAME), FEDERATION_MANIFEST_SHA256
        )
        self.assertFalse(BUNDLE.is_symlink())
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
            self.assertEqual(sha256(path), ARTIFACT_SHA256[path.name], path)

        with ExitStack() as stack:
            self._offline(stack)
            first = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
            second = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
        self.assertEqual(first, second)
        self.assertEqual(first["scope"], POLICY)
        self.assertIsNone(first["counts"]["unique_physical_sites"])
        self.assertIsNone(first["counts"]["physical_site_lower_bound"])
        self.assertIsNone(first["counts"]["physical_site_upper_bound"])
        for key, value in EXPECTED_COUNTS.items():
            self.assertEqual(first["counts"][key], value, key)

        federation = first["federation_input"]
        self.assertEqual(
            federation["federated_index"]["sha256"], FEDERATION_INDEX_SHA256
        )
        self.assertEqual(federation["manifest"]["sha256"], FEDERATION_MANIFEST_SHA256)
        children = {child["release_id"]: child for child in first["input_children"]}
        self.assertEqual(set(children), set(CHILD_MANIFEST_SHA256))
        for release_id, expected_manifest in CHILD_MANIFEST_SHA256.items():
            child = children[release_id]
            release_manifest = json.loads(
                (CHILD_DIRECTORIES[release_id] / MANIFEST_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(child["manifest"]["sha256"], expected_manifest)
            self.assertEqual(child["files"], release_manifest["files"])
            self.assertNotIn(RELATIONSHIPS_FILENAME, child["files"])
        self.assertEqual(
            children["osm-fuzzy-review-v2"]["disposition"],
            "excluded_review_only",
        )

        with (BUNDLE / COMPONENTS_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            component_releases = {row["release_id"] for row in csv.DictReader(source)}
        self.assertEqual(
            component_releases,
            {"epoch-official-open-seed-v49", "global-open-v3"},
        )
        with (BUNDLE / UNRESOLVED_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            reader = csv.DictReader(source)
            self.assertFalse(
                {"name", "latitude", "longitude", "distance", "score"}
                & set(reader.fieldnames or [])
            )
            origins = Counter()
            for row in reader:
                origins[row["origin"]] += 1
                self.assertEqual(row["disposition"], "manual_only")
        self.assertEqual(origins["release_resolution_candidate"], 100_409)
        self.assertEqual(origins["ambiguous_typed_identity"], 127)

    def test_definition_child_order_is_output_invariant(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            definition = rewrite_definition(
                Path(temporary) / "reversed.json",
                lambda document: document["children"].reverse(),
            )
            with ExitStack() as stack:
                self._offline(stack)
                prepared, _ = decision_module._prepare_bundle(
                    decision_module._load_definition(definition)
                )
        for name in BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}:
            self.assertEqual(prepared[name], (BUNDLE / name).read_bytes(), name)

    def test_same_kind_unions_cross_kind_relates_and_ambiguous_stays_manual(
        self,
    ) -> None:
        exact_x = decision_module._Identity("test:record/x", "test")
        exact_y = decision_module._Identity("test:record/y", "test")
        ambiguous_y = decision_module._Identity(
            "test:record/y", "test-ambiguous", ambiguous=True
        )

        def occurrence(
            entity_id: str,
            kind: str,
            identities: tuple[decision_module._Identity, ...],
        ) -> decision_module._Occurrence:
            return decision_module._Occurrence(
                occurrence_id=f"release:{entity_id}",
                release_id="release",
                entity_id=entity_id,
                kind=kind,
                stable_key=f"test:{entity_id}",
                source_family="test",
                source_root="test",
                publisher_root="test",
                snapshot_evidence_id=f"evidence:{entity_id}",
                tags={},
                identities=identities,
            )

        occurrences = [
            occurrence("facility-a", "facility", (exact_x,)),
            occurrence("facility-b", "facility", (exact_x,)),
            occurrence("project", "project", (exact_x,)),
            occurrence("campus-ambiguous", "campus", (ambiguous_y,)),
            occurrence("facility-y", "facility", (exact_y,)),
        ]
        rows, component_for, candidates, component_tokens = (
            decision_module._build_components(occurrences)
        )
        self.assertEqual(len({row["component_id"] for row in rows}), 4)
        self.assertEqual(
            component_for["release:facility-a"],
            component_for["release:facility-b"],
        )
        self.assertNotEqual(
            component_for["release:facility-a"], component_for["release:project"]
        )
        self.assertNotEqual(
            component_for["release:campus-ambiguous"],
            component_for["release:facility-y"],
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["disposition"], "manual_only")

        relationships = decision_module._build_relationships(
            occurrences,
            component_for,
            [
                decision_module._RawRelationship(
                    "release",
                    "project_targets",
                    "release:project",
                    "release:facility-a",
                )
            ],
            component_tokens,
        )
        self.assertEqual(len(relationships), 1)
        self.assertEqual(
            relationships[0]["decision_basis"],
            "explicit_parent_and_exact_typed_identity",
        )

    def test_temporal_review_and_rights_boundaries_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            future = rewrite_definition(
                root / "future.json",
                lambda document: document.__setitem__(
                    "recorded_at", "2999-01-01T00:00:00Z"
                ),
            )
            with self.assertRaisesRegex(
                ExactIdentityDecisionError, "recorded_at must be in the past"
            ):
                decision_module._load_definition(future)

            too_early = rewrite_definition(
                root / "too-early.json",
                lambda document: document.__setitem__(
                    "recorded_at", "2026-07-20T16:45:00Z"
                ),
            )
            review_mismatch = rewrite_definition(
                root / "review-mismatch.json",
                lambda document: next(
                    child
                    for child in document["children"]
                    if child["release_id"] == "osm-fuzzy-review-v2"
                ).__setitem__("expected_review_only", False),
            )
            manifests = {
                path.resolve(): json.loads(
                    (path / MANIFEST_FILENAME).read_text(encoding="utf-8")
                )
                for path in CHILD_DIRECTORIES.values()
            }

            def validated_manifest(path: Path) -> dict[str, object]:
                return manifests[Path(path).resolve()]

            for definition, message in (
                (too_early, "must follow child release"),
                (review_mismatch, "review scope does not reconcile"),
            ):
                loaded = decision_module._load_definition(definition)
                index, _ = decision_module._federation_input(loaded)
                with patch.object(
                    decision_module,
                    "validate_release_files",
                    side_effect=validated_manifest,
                ):
                    with self.assertRaisesRegex(ExactIdentityDecisionError, message):
                        decision_module._inspect_children(loaded, index)

            for source_family in ("peeringdb", "scrutica"):
                source = root / source_family
                source.mkdir()
                atlas = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "id": "entity",
                            "geometry": None,
                            "properties": {
                                "entity_id": "entity",
                                "entity_kind": "facility",
                                "stable_key": f"{source_family}:entity",
                                "source_family": source_family,
                                "source_publisher": source_family,
                                "snapshot_evidence_id": "evidence",
                                "tags": {},
                            },
                        }
                    ],
                }
                (source / "atlas.geojson").write_bytes(canonical_json(atlas))
                child = decision_module._Child(
                    release_id=source_family,
                    directory=source,
                    manifest={"entities": 1},
                    manifest_checkpoint={"bytes": 0, "sha256": "0" * 64},
                    review_only=False,
                    disposition="processed",
                    federation_descriptor={},
                )
                with self.assertRaisesRegex(
                    ExactIdentityDecisionError, "rights-ineligible source root"
                ):
                    decision_module._load_occurrences(child)

    def test_closed_tree_hash_and_hash_consistent_semantics_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "bundle"
            shutil.copytree(BUNDLE, copy)

            copy.chmod(0o755)
            extra = copy / "unexpected.txt"
            extra.write_text("unexpected\n", encoding="utf-8")
            extra.chmod(0o444)
            copy.chmod(0o555)
            with self.assertRaisesRegex(
                ExactIdentityDecisionError, "file inventory is invalid"
            ):
                validate_exact_identity_decision_bundle(copy)

            copy.chmod(0o755)
            extra.unlink()
            target = copy / RELATIONSHIPS_FILENAME
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b"tamper\n")
            target.chmod(0o444)
            copy.chmod(0o555)
            with self.assertRaisesRegex(ExactIdentityDecisionError, "hash mismatch"):
                validate_exact_identity_decision_bundle(copy)

            thaw(copy)
            shutil.copyfile(BUNDLE / RELATIONSHIPS_FILENAME, target)
            accounting_path = copy / ACCOUNTING_FILENAME
            accounting = json.loads(accounting_path.read_text(encoding="utf-8"))
            accounting["unique_physical_sites"] = 1
            accounting_raw = canonical_json(accounting)
            accounting_path.write_bytes(accounting_raw)
            manifest_path = copy / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["counts"] = accounting
            manifest["files"][ACCOUNTING_FILENAME] = {
                "bytes": len(accounting_raw),
                "sha256": hashlib.sha256(accounting_raw).hexdigest(),
            }
            manifest_raw = canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            (copy / MANIFEST_HASH_FILENAME).write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            freeze(copy)
            with self.assertRaisesRegex(
                ExactIdentityDecisionError, "physical-site fields must remain null"
            ):
                validate_exact_identity_decision_bundle(copy)

    def test_late_output_collision_is_refused_without_overwrite(self) -> None:
        payloads = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        manifest = json.loads(payloads[MANIFEST_FILENAME])
        original_validate = decision_module.validate_exact_identity_decision_bundle
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "late-output"
            sentinel = output / "sentinel.txt"

            def validate_then_race(*args: object, **kwargs: object) -> object:
                validated = original_validate(*args, **kwargs)
                if not output.exists():
                    output.mkdir()
                    sentinel.write_text("late arrival\n", encoding="utf-8")
                return validated

            with (
                patch.object(
                    decision_module,
                    "_prepare_bundle",
                    return_value=(payloads, manifest),
                ),
                patch.object(
                    decision_module,
                    "validate_exact_identity_decision_bundle",
                    side_effect=validate_then_race,
                ),
            ):
                with self.assertRaisesRegex(
                    ExactIdentityDecisionError, "appeared during publication"
                ):
                    write_exact_identity_decision_bundle(DEFINITION, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "late arrival\n")


if __name__ == "__main__":
    unittest.main()
