from __future__ import annotations

import csv
import hashlib
import io
import json
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
PUBLIC_FEDERATION_V5 = ROOT / "federated_indexes" / "2026-07-19-public-open-v5"
PUBLIC_FEDERATION_V5_MANIFEST_SHA256 = (
    "47dc6441265fd76f2d20fc826b5b13f80567db4b85976fc0680d4d07873cad7a"
)
PUBLIC_FEDERATION_V5_CHILDREN = {
    "epoch-official-open-seed-v5": ROOT / "releases" / "2026-07-19-open-seed-v5",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
PUBLIC_FEDERATION_V6 = ROOT / "federated_indexes" / "2026-07-19-public-open-v6"
PUBLIC_FEDERATION_V6_MANIFEST_SHA256 = (
    "55be7904c3399f40f12cebcacfef6d319390c6ae4415633d6e9c3fd5440f4644"
)
PUBLIC_FEDERATION_V6_CHILDREN = {
    "epoch-official-open-seed-v8": ROOT / "releases" / "2026-07-19-open-seed-v8",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
PUBLIC_FEDERATION_V7 = ROOT / "federated_indexes" / "2026-07-19-public-open-v7"
PUBLIC_FEDERATION_V7_MANIFEST_SHA256 = (
    "ce1d01cc0716c689e1cc3c71cab03d59519da9102072637d8cb867dcdada3f51"
)
PUBLIC_FEDERATION_V7_CHILDREN = {
    "epoch-official-open-seed-v9": ROOT / "releases" / "2026-07-19-open-seed-v9",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
OPEN_SEED_V13_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v13.json"
OPEN_SEED_V13_DEFINITION_SHA256 = (
    "5b62d3e69e8ae09de70fc7046318d36054e4a264d00f606efc67fa88a89bd3be"
)
OPEN_SEED_V13_MANIFEST_SHA256 = (
    "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7"
)
PUBLIC_FEDERATION_V8_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-19-public-open-v8.json"
)
PUBLIC_FEDERATION_V8_DEFINITION_SHA256 = (
    "91aed1938136a9bfd6432745cffcd1dfe55cfe5c1a99d72f2998d5ff63c9bbf0"
)
PUBLIC_FEDERATION_V8_CANDIDATE = (
    ROOT / "federated_indexes" / "2026-07-19-public-open-v8"
)
PUBLIC_FEDERATION_V8_MANIFEST_SHA256 = (
    "0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48"
)
PUBLIC_FEDERATION_V8_CHILDREN = {
    "epoch-official-open-seed-v13": ROOT / "releases" / "2026-07-19-open-seed-v13",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
PUBLIC_FEDERATION_V8_INDEX_SHA256 = (
    "75737e6175f4de03f84e9b0cead12e92cf5fcdfa9e59a85ba845bd0a7fa60bd4"
)
OPEN_SEED_V20_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v20.json"
OPEN_SEED_V20_DEFINITION_SHA256 = (
    "099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd"
)
OPEN_SEED_V20_MANIFEST_SHA256 = (
    "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456"
)
PUBLIC_FEDERATION_V9_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-19-public-open-v9.json"
)
PUBLIC_FEDERATION_V9_DEFINITION_SHA256 = (
    "3c7a9b13cda5ffd5cc4791b47f7f93266d441c37a10cd44883a7caff15b1d9f1"
)
PUBLIC_FEDERATION_V9 = ROOT / "federated_indexes" / "2026-07-19-public-open-v9"
PUBLIC_FEDERATION_V9_INDEX_SHA256 = (
    "600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1"
)
PUBLIC_FEDERATION_V9_MANIFEST_SHA256 = (
    "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5"
)
PUBLIC_FEDERATION_V9_CHILDREN = {
    "epoch-official-open-seed-v20": ROOT / "releases" / "2026-07-19-open-seed-v20",
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def canonical_json(value: dict) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def csv_bytes(fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def write_child_release(
    directory: Path,
    *,
    entity_kinds: list[str],
    source_family: str,
    source_license: str,
    attribution: str,
    construction_pipeline_records: int = 0,
) -> str:
    directory.mkdir()
    files = {
        "ATTRIBUTION.txt": (attribution + "\n").encode(),
        "entities.csv": csv_bytes(
            ["entity_id", "entity_kind"],
            [
                {"entity_id": f"{source_family}-{index}", "entity_kind": kind}
                for index, kind in enumerate(entity_kinds, start=1)
            ],
        ),
        "evidence.csv": csv_bytes(
            ["evidence_id", "source_family", "license"],
            [
                {
                    "evidence_id": f"{source_family}-evidence",
                    "source_family": source_family,
                    "license": source_license,
                }
            ],
        ),
        "source_inputs.json": canonical_json(
            {
                "sources": [
                    {
                        "source_family": source_family,
                        "license": source_license,
                    }
                ]
            }
        ),
    }
    for name, raw in files.items():
        (directory / name).write_bytes(raw)
    kind_counts: dict[str, int] = {}
    for kind in entity_kinds:
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    manifest = {
        "format": "datacenter-atlas-release-v1",
        "as_of": "2026-07-18",
        "recorded_at": "2026-07-18T20:00:00Z",
        "entities": len(entity_kinds),
        "entities_by_kind": dict(sorted(kind_counts.items())),
        "capacity_estimates": 0,
        "construction_pipeline_records": construction_pipeline_records,
        "construction_source_signals": 0,
        "evidence_records": 1,
        "source_families": [source_family],
        "resolution_candidates": 0,
        "files": {
            name: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for name, raw in sorted(files.items())
        },
    }
    manifest_raw = canonical_json(manifest)
    (directory / MANIFEST_FILENAME).write_bytes(manifest_raw)
    return hashlib.sha256(manifest_raw).hexdigest()


def write_definition(
    path: Path,
    open_release: Path,
    open_sha256: str,
    scrutica_release: Path,
    scrutica_sha256: str,
    *,
    generated_at: str = "2026-07-18T22:00:00Z",
) -> None:
    document = {
        "schema_version": 1,
        "generated_at": generated_at,
        "children": [
            {
                "release_id": "scrutica-2026-07-18",
                "release_path": str(scrutica_release),
                "reference": "../scrutica-2026-07-18/",
                "expected_manifest_sha256": scrutica_sha256,
                "license_expression": "CC-BY-SA-4.0",
                "rights_notice": "Scrutica attribution and share-alike terms apply only to this child.",
            },
            {
                "release_id": "global-open-v2",
                "release_path": str(open_release),
                "reference": "../2026-07-18-global-open-v2/",
                "expected_manifest_sha256": open_sha256,
                "license_expression": "ODbL-1.0",
                "rights_notice": "ODbL and child source attributions apply only to this child.",
            },
        ],
    }
    path.write_bytes(canonical_json(document))


class FederatedReleaseTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        open_release = root / "global-open"
        scrutica_release = root / "scrutica"
        open_sha256 = write_child_release(
            open_release,
            entity_kinds=["campus", "facility", "facility"],
            source_family="openstreetmap",
            source_license="ODbL-1.0",
            attribution="© OpenStreetMap contributors",
            construction_pipeline_records=1,
        )
        scrutica_sha256 = write_child_release(
            scrutica_release,
            entity_kinds=["facility", "facility"],
            source_family="scrutica",
            source_license="CC-BY-SA-4.0",
            attribution="Scrutica data, licensed under CC BY-SA 4.0",
            construction_pipeline_records=2,
        )
        definition = root / "federation-definition.json"
        write_definition(
            definition,
            open_release,
            open_sha256,
            scrutica_release,
            scrutica_sha256,
        )
        return definition, open_release, scrutica_release

    def test_child_and_embedded_manifests_reject_noncanonical_offsets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, _scrutica_release = self.fixture(root)
            child_manifest_path = open_release / MANIFEST_FILENAME
            child_manifest = json.loads(child_manifest_path.read_text())
            child_manifest["recorded_at"] = "2026-07-18T21:00:00+01:00"
            child_manifest_raw = canonical_json(child_manifest)
            child_manifest_path.write_bytes(child_manifest_raw)
            definition_document = json.loads(definition.read_text())
            for child in definition_document["children"]:
                if child["release_id"] == "global-open-v2":
                    child["expected_manifest_sha256"] = hashlib.sha256(
                        child_manifest_raw
                    ).hexdigest()
            definition.write_bytes(canonical_json(definition_document))
            with self.assertRaisesRegex(
                FederatedReleaseError,
                "canonical UTC seconds",
            ):
                write_federated_release_index(definition, root / "rejected")

            child_manifest["recorded_at"] = "2026-07-18T20:00:00Z"
            child_manifest_raw = canonical_json(child_manifest)
            child_manifest_path.write_bytes(child_manifest_raw)
            for child in definition_document["children"]:
                if child["release_id"] == "global-open-v2":
                    child["expected_manifest_sha256"] = hashlib.sha256(
                        child_manifest_raw
                    ).hexdigest()
            definition.write_bytes(canonical_json(definition_document))
            output = root / "federated"
            write_federated_release_index(definition, output)

            index_path = output / INDEX_FILENAME
            index = json.loads(index_path.read_text())
            index["releases"][0]["manifest"]["recorded_at"] = (
                "2026-07-18T21:00:00+01:00"
            )
            index_raw = canonical_json(index)
            index_path.write_bytes(index_raw)
            bundle_manifest_path = output / MANIFEST_FILENAME
            bundle_manifest = json.loads(bundle_manifest_path.read_text())
            bundle_manifest["artifacts"][INDEX_FILENAME].update(
                {
                    "bytes": len(index_raw),
                    "sha256": hashlib.sha256(index_raw).hexdigest(),
                }
            )
            bundle_manifest_raw = canonical_json(bundle_manifest)
            bundle_manifest_path.write_bytes(bundle_manifest_raw)
            (output / MANIFEST_HASH_FILENAME).write_text(
                f"{hashlib.sha256(bundle_manifest_raw).hexdigest()}  "
                f"{MANIFEST_FILENAME}\n"
            )
            with self.assertRaisesRegex(
                FederatedReleaseError,
                "canonical UTC seconds",
            ):
                validate_federated_release_index(output)

    def test_index_preserves_release_rights_and_only_sums_source_scoped_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, scrutica_release = self.fixture(root)
            children_before = {
                path: path.read_bytes()
                for release in (open_release, scrutica_release)
                for path in release.iterdir()
            }
            output = root / "federated"
            index = write_federated_release_index(definition, output)
            self.assertEqual(validate_federated_release_index(output), index)
            self.assertEqual(
                validate_federated_release_index(
                    output,
                    child_release_paths={
                        "global-open-v2": open_release,
                        "scrutica-2026-07-18": scrutica_release,
                    },
                ),
                index,
            )
            self.assertEqual(
                [release["release_id"] for release in index["releases"]],
                ["global-open-v2", "scrutica-2026-07-18"],
            )
            self.assertEqual(index["policy"], FEDERATION_POLICY)
            self.assertFalse(index["policy"]["cross_source_deduplication"])
            self.assertIsNone(index["counts"]["unique_physical_sites"])
            self.assertEqual(index["counts"]["release_bundles"], 2)
            self.assertEqual(index["counts"]["source_family_entries"], 2)
            self.assertEqual(index["counts"]["source_scoped_entity_records"], 5)
            self.assertEqual(index["counts"]["review_only_release_bundles"], 0)
            self.assertEqual(
                index["counts"]["review_only_source_scoped_entity_records"], 0
            )
            self.assertEqual(
                index["counts"]["non_review_source_scoped_entity_records"], 5
            )
            self.assertEqual(index["counts"]["construction_pipeline_records"], 3)
            self.assertEqual(
                index["counts"]["review_only_construction_pipeline_records"], 0
            )
            self.assertEqual(
                index["counts"]["non_review_construction_pipeline_records"], 3
            )
            rights = {
                release["release_id"]: release["rights"]
                for release in index["releases"]
            }
            self.assertEqual(
                rights["global-open-v2"]["source_licenses"], ["ODbL-1.0"]
            )
            self.assertEqual(
                rights["scrutica-2026-07-18"]["source_licenses"],
                ["CC-BY-SA-4.0"],
            )
            self.assertIn(
                "OpenStreetMap contributors",
                rights["global-open-v2"]["attribution"]["text"],
            )
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
            )
            self.assertEqual(
                children_before,
                {
                    path: path.read_bytes()
                    for release in (open_release, scrutica_release)
                    for path in release.iterdir()
                },
            )
            second = write_federated_release_index(definition, output)
            self.assertEqual(second, index)

    def test_review_only_child_scope_and_counts_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _open_release, scrutica_release = self.fixture(root)
            manifest_path = scrutica_release / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text())
            manifest.update(
                {
                    "fuzzy_review_excluded_candidates": 1,
                    "fuzzy_review_shortlist_records": 1,
                    "review_only": True,
                }
            )
            manifest_raw = canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            definition_doc = json.loads(definition.read_text())
            for child in definition_doc["children"]:
                if child["release_id"] == "scrutica-2026-07-18":
                    child["expected_manifest_sha256"] = hashlib.sha256(
                        manifest_raw
                    ).hexdigest()
            definition.write_bytes(canonical_json(definition_doc))

            index = write_federated_release_index(definition, root / "federated")
            review = next(
                release
                for release in index["releases"]
                if release["release_id"] == "scrutica-2026-07-18"
            )
            self.assertEqual(
                review["scope"],
                {
                    "review_only": True,
                    "fuzzy_review_excluded_candidates": 1,
                    "fuzzy_review_shortlist_records": 1,
                },
            )
            self.assertEqual(index["counts"]["review_only_release_bundles"], 1)
            self.assertEqual(
                index["counts"]["review_only_source_scoped_entity_records"], 2
            )
            self.assertEqual(
                index["counts"]["non_review_source_scoped_entity_records"], 3
            )
            self.assertEqual(
                index["counts"]["review_only_construction_pipeline_records"], 2
            )
            self.assertEqual(
                index["counts"]["non_review_construction_pipeline_records"], 1
            )

    def test_publication_contract_marker_is_optional_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, _scrutica_release = self.fixture(root)

            legacy_output = root / "legacy-federated"
            legacy_index = write_federated_release_index(definition, legacy_output)
            self.assertEqual(
                validate_federated_release_index(legacy_output), legacy_index
            )
            self.assertTrue(
                all(
                    "publication_contract_version" not in release["manifest"]
                    for release in legacy_index["releases"]
                )
            )

            manifest_path = open_release / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text())
            manifest["publication_contract_version"] = 3
            manifest_raw = canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            definition_doc = json.loads(definition.read_text())
            for child in definition_doc["children"]:
                if child["release_id"] == "global-open-v2":
                    child["expected_manifest_sha256"] = hashlib.sha256(
                        manifest_raw
                    ).hexdigest()
            definition.write_bytes(canonical_json(definition_doc))

            marked_output = root / "marked-federated"
            marked_index = write_federated_release_index(definition, marked_output)
            marked_child = next(
                release
                for release in marked_index["releases"]
                if release["release_id"] == "global-open-v2"
            )
            unmarked_child = next(
                release
                for release in marked_index["releases"]
                if release["release_id"] == "scrutica-2026-07-18"
            )
            self.assertEqual(
                marked_child["manifest"]["publication_contract_version"], 3
            )
            self.assertNotIn(
                "publication_contract_version", unmarked_child["manifest"]
            )
            self.assertEqual(
                validate_federated_release_index(marked_output), marked_index
            )

            tampered_index = json.loads(
                (marked_output / INDEX_FILENAME).read_text()
            )
            tampered_child = next(
                release
                for release in tampered_index["releases"]
                if release["release_id"] == "global-open-v2"
            )
            tampered_child["manifest"]["publication_contract_version"] = True
            tampered_index_raw = canonical_json(tampered_index)
            (marked_output / INDEX_FILENAME).write_bytes(tampered_index_raw)
            bundle_manifest = json.loads(
                (marked_output / MANIFEST_FILENAME).read_text()
            )
            bundle_manifest["artifacts"][INDEX_FILENAME].update(
                {
                    "bytes": len(tampered_index_raw),
                    "sha256": hashlib.sha256(tampered_index_raw).hexdigest(),
                }
            )
            bundle_manifest_raw = canonical_json(bundle_manifest)
            (marked_output / MANIFEST_FILENAME).write_bytes(bundle_manifest_raw)
            (marked_output / MANIFEST_HASH_FILENAME).write_text(
                f"{hashlib.sha256(bundle_manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
            )
            with self.assertRaisesRegex(FederatedReleaseError, "positive integer"):
                validate_federated_release_index(marked_output)

    def test_malformed_publication_contract_markers_fail_closed(self) -> None:
        cases = {
            "null": None,
            "boolean true": True,
            "boolean false": False,
            "string": "3",
            "zero": 0,
            "negative": -1,
        }
        for case, marker in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                definition, open_release, _scrutica_release = self.fixture(root)
                manifest_path = open_release / MANIFEST_FILENAME
                manifest = json.loads(manifest_path.read_text())
                manifest["publication_contract_version"] = marker
                manifest_raw = canonical_json(manifest)
                manifest_path.write_bytes(manifest_raw)
                definition_doc = json.loads(definition.read_text())
                for child in definition_doc["children"]:
                    if child["release_id"] == "global-open-v2":
                        child["expected_manifest_sha256"] = hashlib.sha256(
                            manifest_raw
                        ).hexdigest()
                definition.write_bytes(canonical_json(definition_doc))
                with self.assertRaisesRegex(
                    FederatedReleaseError, "positive integer"
                ):
                    build_federated_release_index(definition)

    def test_validator_accepts_legacy_index_without_construction_scope_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _open_release, _scrutica_release = self.fixture(root)
            output = root / "federated"
            write_federated_release_index(definition, output)

            index = json.loads((output / INDEX_FILENAME).read_text())
            del index["counts"]["review_only_construction_pipeline_records"]
            del index["counts"]["non_review_construction_pipeline_records"]
            index_raw = canonical_json(index)
            (output / INDEX_FILENAME).write_bytes(index_raw)

            manifest = json.loads((output / MANIFEST_FILENAME).read_text())
            manifest["artifacts"][INDEX_FILENAME].update(
                {
                    "bytes": len(index_raw),
                    "sha256": hashlib.sha256(index_raw).hexdigest(),
                }
            )
            manifest_raw = canonical_json(manifest)
            (output / MANIFEST_FILENAME).write_bytes(manifest_raw)
            (output / MANIFEST_HASH_FILENAME).write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
            )

            validated = validate_federated_release_index(output)
            self.assertNotIn(
                "review_only_construction_pipeline_records", validated["counts"]
            )
            self.assertEqual(validated["counts"]["construction_pipeline_records"], 3)

    def test_malformed_review_only_manifest_fields_fail_closed(self) -> None:
        cases = {
            "false marker": {"review_only": False},
            "partial counts": {
                "review_only": True,
                "fuzzy_review_shortlist_records": 2,
            },
            "count mismatch": {
                "review_only": True,
                "fuzzy_review_excluded_candidates": 1,
                "fuzzy_review_shortlist_records": 3,
            },
        }
        for case, updates in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                definition, open_release, _scrutica_release = self.fixture(root)
                manifest_path = open_release / MANIFEST_FILENAME
                manifest = json.loads(manifest_path.read_text())
                manifest.update(updates)
                manifest_raw = canonical_json(manifest)
                manifest_path.write_bytes(manifest_raw)
                definition_doc = json.loads(definition.read_text())
                for child in definition_doc["children"]:
                    if child["release_id"] == "global-open-v2":
                        child["expected_manifest_sha256"] = hashlib.sha256(
                            manifest_raw
                        ).hexdigest()
                definition.write_bytes(canonical_json(definition_doc))
                with self.assertRaises(FederatedReleaseError):
                    write_federated_release_index(definition, root / "federated")

    def test_child_csv_fields_larger_than_python_default_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, _scrutica_release = self.fixture(root)
            entities_raw = csv_bytes(
                ["entity_id", "entity_kind", "source_payload"],
                [
                    {
                        "entity_id": "openstreetmap-1",
                        "entity_kind": "campus",
                        "source_payload": "x" * 200_000,
                    },
                    {
                        "entity_id": "openstreetmap-2",
                        "entity_kind": "facility",
                        "source_payload": "",
                    },
                    {
                        "entity_id": "openstreetmap-3",
                        "entity_kind": "facility",
                        "source_payload": "",
                    },
                ],
            )
            entities_path = open_release / "entities.csv"
            entities_path.write_bytes(entities_raw)
            manifest_path = open_release / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["entities.csv"] = {
                "bytes": len(entities_raw),
                "sha256": hashlib.sha256(entities_raw).hexdigest(),
            }
            manifest_raw = canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            definition_doc = json.loads(definition.read_text())
            for child in definition_doc["children"]:
                if child["release_id"] == "global-open-v2":
                    child["expected_manifest_sha256"] = hashlib.sha256(
                        manifest_raw
                    ).hexdigest()
            definition.write_bytes(canonical_json(definition_doc))

            index = write_federated_release_index(definition, root / "federated")
            self.assertEqual(index["counts"]["source_scoped_entity_records"], 5)

    def test_child_hash_count_and_definition_pins_fail_before_publication(self) -> None:
        for case in ("file hash", "semantic count", "manifest pin"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                definition, open_release, _scrutica_release = self.fixture(root)
                if case == "file hash":
                    with (open_release / "entities.csv").open("ab") as stream:
                        stream.write(b"tampered")
                    pattern = "file hash mismatch"
                elif case == "semantic count":
                    manifest = json.loads((open_release / MANIFEST_FILENAME).read_text())
                    manifest["entities"] += 1
                    raw = canonical_json(manifest)
                    (open_release / MANIFEST_FILENAME).write_bytes(raw)
                    definition_doc = json.loads(definition.read_text())
                    for child in definition_doc["children"]:
                        if child["release_id"] == "global-open-v2":
                            child["expected_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
                    definition.write_bytes(canonical_json(definition_doc))
                    pattern = "entity counts do not reconcile"
                else:
                    definition_doc = json.loads(definition.read_text())
                    definition_doc["children"][1]["expected_manifest_sha256"] = "0" * 64
                    definition.write_bytes(canonical_json(definition_doc))
                    pattern = "manifest SHA-256"
                output = root / "federated"
                with self.assertRaisesRegex(FederatedReleaseError, pattern):
                    write_federated_release_index(definition, output)
                self.assertFalse(output.exists())

    def test_existing_output_is_immutable_and_invalid_output_is_not_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, scrutica_release = self.fixture(root)
            output = root / "federated"
            write_federated_release_index(definition, output)
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            changed_definition = root / "changed-definition.json"
            open_hash = hashlib.sha256(
                (open_release / MANIFEST_FILENAME).read_bytes()
            ).hexdigest()
            scrutica_hash = hashlib.sha256(
                (scrutica_release / MANIFEST_FILENAME).read_bytes()
            ).hexdigest()
            write_definition(
                changed_definition,
                open_release,
                open_hash,
                scrutica_release,
                scrutica_hash,
                generated_at="2026-07-18T23:00:00Z",
            )
            with self.assertRaisesRegex(FederatedReleaseError, "not byte-identical"):
                write_federated_release_index(changed_definition, output)
            self.assertEqual(
                before, {path.name: path.read_bytes() for path in output.iterdir()}
            )
            with (output / INDEX_FILENAME).open("ab") as stream:
                stream.write(b"tampered")
            tampered = (output / INDEX_FILENAME).read_bytes()
            with self.assertRaises(FederatedReleaseError):
                write_federated_release_index(definition, output)
            self.assertEqual((output / INDEX_FILENAME).read_bytes(), tampered)

    def test_index_validator_rejects_tampering_and_extra_files(self) -> None:
        for case in ("index", "sidecar", "extra"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                definition, _open_release, _scrutica_release = self.fixture(root)
                output = root / "federated"
                write_federated_release_index(definition, output)
                if case == "index":
                    with (output / INDEX_FILENAME).open("ab") as stream:
                        stream.write(b" ")
                elif case == "sidecar":
                    (output / MANIFEST_HASH_FILENAME).write_text("0" * 64)
                else:
                    (output / "extra.txt").write_text("unexpected")
                with self.assertRaises(FederatedReleaseError):
                    validate_federated_release_index(output)

    def test_child_revalidation_detects_drift_after_index_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, open_release, scrutica_release = self.fixture(root)
            output = root / "federated"
            write_federated_release_index(definition, output)
            with (scrutica_release / "evidence.csv").open("ab") as stream:
                stream.write(b"drift")
            self.assertEqual(validate_federated_release_index(output)["counts"]["release_bundles"], 2)
            with self.assertRaisesRegex(FederatedReleaseError, "file hash mismatch"):
                validate_federated_release_index(
                    output,
                    child_release_paths={
                        "global-open-v2": open_release,
                        "scrutica-2026-07-18": scrutica_release,
                    },
                )

    def test_atomic_stage_is_cleaned_when_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _open_release, _scrutica_release = self.fixture(root)
            output = root / "federated"
            with patch(
                "datacenter_atlas.federated_release.validate_federated_release_index",
                side_effect=FederatedReleaseError("injected failure"),
            ), self.assertRaisesRegex(FederatedReleaseError, "injected"):
                write_federated_release_index(definition, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".federated.stage-*")), [])

    def test_definition_requires_distinct_hash_pinned_child_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _open_release, _scrutica_release = self.fixture(root)
            document = json.loads(definition.read_text())
            document["children"][1]["release_path"] = document["children"][0][
                "release_path"
            ]
            definition.write_bytes(canonical_json(document))
            with self.assertRaisesRegex(FederatedReleaseError, "repeats a child"):
                build_federated_release_index(definition)

    def test_cli_builds_the_same_validated_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _open_release, _scrutica_release = self.fixture(root)
            output = root / "federated"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(
                        Path(__file__).resolve().parents[1]
                        / "scripts"
                        / "build_federated_release_index.py"
                    ),
                    "--definition",
                    str(definition),
                    "--output-dir",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(
                report["release_ids"],
                ["global-open-v2", "scrutica-2026-07-18"],
            )
            self.assertEqual(
                validate_federated_release_index(output)["counts"][
                    "source_scoped_entity_records"
                ],
                5,
            )


class FrozenPublicFederationV5Tests(unittest.TestCase):
    def test_current_public_federation_revalidates_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            index = validate_federated_release_index(
                PUBLIC_FEDERATION_V5,
                child_release_paths=PUBLIC_FEDERATION_V5_CHILDREN,
            )
        self.assertEqual(index["counts"]["source_scoped_entity_records"], 15_529)
        self.assertEqual(index["counts"]["non_review_source_scoped_entity_records"], 9_399)
        self.assertEqual(index["counts"]["construction_pipeline_records"], 6_310)
        self.assertIsNone(index["counts"]["unique_physical_sites"])
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V5 / MANIFEST_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V5_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_FEDERATION_V5.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_FEDERATION_V5.iterdir()
            )
        )


class FrozenPublicFederationV6Tests(unittest.TestCase):
    def test_current_public_federation_revalidates_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            index = validate_federated_release_index(
                PUBLIC_FEDERATION_V6,
                child_release_paths=PUBLIC_FEDERATION_V6_CHILDREN,
            )
        self.assertEqual(index["counts"]["source_scoped_entity_records"], 15_537)
        self.assertEqual(
            index["counts"]["non_review_source_scoped_entity_records"], 9_407
        )
        self.assertEqual(index["counts"]["construction_pipeline_records"], 6_314)
        self.assertIsNone(index["counts"]["unique_physical_sites"])
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V6 / MANIFEST_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V6_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_FEDERATION_V6.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_FEDERATION_V6.iterdir()
            )
        )


class FrozenPublicFederationV7Tests(unittest.TestCase):
    def test_current_public_federation_revalidates_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            index = validate_federated_release_index(
                PUBLIC_FEDERATION_V7,
                child_release_paths=PUBLIC_FEDERATION_V7_CHILDREN,
            )
        self.assertEqual(index["counts"]["source_scoped_entity_records"], 15_552)
        self.assertEqual(
            index["counts"]["non_review_source_scoped_entity_records"], 9_422
        )
        self.assertEqual(index["counts"]["construction_pipeline_records"], 6_323)
        self.assertIsNone(index["counts"]["unique_physical_sites"])
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V7 / MANIFEST_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V7_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_FEDERATION_V7.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_FEDERATION_V7.iterdir()
            )
        )


class PublicFederationV8Tests(unittest.TestCase):
    def candidate_definition_with_absolute_child_paths(self) -> dict:
        definition = json.loads(
            PUBLIC_FEDERATION_V8_DEFINITION.read_text(encoding="utf-8")
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (PUBLIC_FEDERATION_V8_DEFINITION.parent / child["release_path"])
                .resolve()
            )
        return definition

    def test_accepted_release_is_exactly_v7_with_open_seed_v13_replaced(self) -> None:
        self.assertEqual(
            hashlib.sha256(OPEN_SEED_V13_DEFINITION.read_bytes()).hexdigest(),
            OPEN_SEED_V13_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(PUBLIC_FEDERATION_V8_DEFINITION.read_bytes()).hexdigest(),
            PUBLIC_FEDERATION_V8_DEFINITION_SHA256,
        )
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_federated_release_index(
                PUBLIC_FEDERATION_V8_CANDIDATE,
                child_release_paths=PUBLIC_FEDERATION_V8_CHILDREN,
            )
            second = validate_federated_release_index(
                PUBLIC_FEDERATION_V8_CANDIDATE,
                child_release_paths=PUBLIC_FEDERATION_V8_CHILDREN,
            )
        self.assertEqual(first, second)
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V8_CANDIDATE / MANIFEST_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V8_MANIFEST_SHA256,
        )

        v7 = json.loads((PUBLIC_FEDERATION_V7 / INDEX_FILENAME).read_text())
        v7_releases = {
            release["release_id"]: release for release in v7["releases"]
        }
        v8_releases = {
            release["release_id"]: release for release in first["releases"]
        }
        self.assertEqual(
            set(v8_releases),
            (set(v7_releases) - {"epoch-official-open-seed-v9"})
            | {"epoch-official-open-seed-v13"},
        )
        self.assertNotIn("epoch-official-open-seed-v9", v8_releases)
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                canonical_json(v8_releases[release_id]),
                canonical_json(v7_releases[release_id]),
            )

        old_open = v7_releases["epoch-official-open-seed-v9"]
        new_open = v8_releases["epoch-official-open-seed-v13"]
        self.assertEqual(
            new_open["manifest"]["sha256"],
            OPEN_SEED_V13_MANIFEST_SHA256,
        )
        self.assertEqual(new_open["scope"], old_open["scope"])
        self.assertEqual(
            new_open["rights"]["license_expression"],
            old_open["rights"]["license_expression"],
        )
        self.assertEqual(
            new_open["rights"]["rights_notice"],
            old_open["rights"]["rights_notice"],
        )

        expected_counts = {
            "capacity_estimates": 1_148,
            "construction_pipeline_records": 6_355,
            "evidence_records": 13_153,
            "non_review_construction_pipeline_records": 225,
            "non_review_source_scoped_entity_records": 9_489,
            "release_bundles": 3,
            "resolution_candidates": 100_409,
            "review_only_construction_pipeline_records": 6_130,
            "review_only_release_bundles": 1,
            "review_only_source_scoped_entity_records": 6_130,
            "source_family_entries": 44,
            "source_scoped_entity_records": 15_619,
            "unique_physical_sites": None,
        }
        self.assertEqual(first["counts"], expected_counts)
        expected_delta = {
            "capacity_estimates": 14,
            "construction_pipeline_records": 32,
            "evidence_records": 39,
            "non_review_construction_pipeline_records": 32,
            "non_review_source_scoped_entity_records": 67,
            "release_bundles": 0,
            "resolution_candidates": 1,
            "review_only_construction_pipeline_records": 0,
            "review_only_release_bundles": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_family_entries": 16,
            "source_scoped_entity_records": 67,
        }
        for field, delta in expected_delta.items():
            self.assertEqual(first["counts"][field] - v7["counts"][field], delta)

        arithmetic_fields = (
            "capacity_estimates",
            "construction_pipeline_records",
            "evidence_records",
            "resolution_candidates",
            "source_family_entries",
            "source_scoped_entity_records",
        )
        for field in arithmetic_fields:
            self.assertEqual(
                first["counts"][field],
                sum(release["counts"][field] for release in first["releases"]),
            )
        self.assertEqual(first["policy"], FEDERATION_POLICY)
        self.assertFalse(first["policy"]["child_entities_merged"])
        self.assertFalse(first["policy"]["cross_source_deduplication"])
        self.assertIsNone(first["counts"]["unique_physical_sites"])

        self.assertFalse(PUBLIC_FEDERATION_V8_DEFINITION.is_symlink())
        self.assertFalse(PUBLIC_FEDERATION_V8_CANDIDATE.is_symlink())
        self.assertEqual(
            stat.S_IMODE(PUBLIC_FEDERATION_V8_DEFINITION.stat().st_mode), 0o644
        )
        self.assertEqual(
            stat.S_IMODE(PUBLIC_FEDERATION_V8_CANDIDATE.stat().st_mode), 0o555
        )
        self.assertTrue(
            all(
                not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_FEDERATION_V8_CANDIDATE.iterdir()
            )
        )

    def test_candidate_rejects_wrong_v13_pin_and_symlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_pin = self.candidate_definition_with_absolute_child_paths()
            open_child = next(
                child
                for child in bad_pin["children"]
                if child["release_id"] == "epoch-official-open-seed-v13"
            )
            open_child["expected_manifest_sha256"] = "0" * 64
            bad_pin_path = root / "bad-pin.json"
            bad_pin_path.write_bytes(canonical_json(bad_pin))
            with self.assertRaisesRegex(FederatedReleaseError, "manifest SHA-256"):
                build_federated_release_index(bad_pin_path)

            symlink_definition = self.candidate_definition_with_absolute_child_paths()
            open_child = next(
                child
                for child in symlink_definition["children"]
                if child["release_id"] == "epoch-official-open-seed-v13"
            )
            alias = root / "open-seed-v13-alias"
            alias.symlink_to(PUBLIC_FEDERATION_V8_CHILDREN[open_child["release_id"]])
            open_child["release_path"] = str(alias)
            symlink_path = root / "symlink.json"
            symlink_path.write_bytes(canonical_json(symlink_definition))
            with self.assertRaisesRegex(
                FederatedReleaseError, "child release must be a regular directory"
            ):
                build_federated_release_index(symlink_path)


class FrozenPublicFederationV9Tests(unittest.TestCase):
    @staticmethod
    def definition_with_absolute_child_paths() -> dict[str, object]:
        definition = json.loads(
            PUBLIC_FEDERATION_V9_DEFINITION.read_text(encoding="utf-8")
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (PUBLIC_FEDERATION_V9_DEFINITION.parent / child["release_path"])
                .resolve()
            )
        return definition

    @staticmethod
    def require_frozen_modes(directory: Path) -> None:
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o555:
            raise FederatedReleaseError("federation directory mode must be 0555")
        for path in directory.iterdir():
            if (
                path.is_symlink()
                or not path.is_file()
                or stat.S_IMODE(path.stat().st_mode) != 0o444
            ):
                raise FederatedReleaseError("federation file mode must be 0444")

    def test_frozen_successor_reproduces_twice_offline_with_exact_v13_delta(
        self,
    ) -> None:
        self.assertEqual(
            hashlib.sha256(OPEN_SEED_V20_DEFINITION.read_bytes()).hexdigest(),
            OPEN_SEED_V20_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(PUBLIC_FEDERATION_V9_DEFINITION.read_bytes()).hexdigest(),
            PUBLIC_FEDERATION_V9_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V8_CANDIDATE / INDEX_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V8_INDEX_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_FEDERATION_V8_CANDIDATE / MANIFEST_FILENAME).read_bytes()
            ).hexdigest(),
            PUBLIC_FEDERATION_V8_MANIFEST_SHA256,
        )

        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline build attempted network access"),
        ):
            first_build = build_federated_release_index(
                PUBLIC_FEDERATION_V9_DEFINITION
            )
            second_build = build_federated_release_index(
                PUBLIC_FEDERATION_V9_DEFINITION
            )
            first = validate_federated_release_index(
                PUBLIC_FEDERATION_V9,
                child_release_paths=PUBLIC_FEDERATION_V9_CHILDREN,
            )
            second = validate_federated_release_index(
                PUBLIC_FEDERATION_V9,
                child_release_paths=PUBLIC_FEDERATION_V9_CHILDREN,
            )
        self.assertEqual(first_build, second_build)
        self.assertEqual(first, second)
        self.assertEqual(first_build.index, first)
        self.assertEqual(
            first_build.index_bytes,
            (PUBLIC_FEDERATION_V9 / INDEX_FILENAME).read_bytes(),
        )
        self.assertEqual(
            first_build.manifest_bytes,
            (PUBLIC_FEDERATION_V9 / MANIFEST_FILENAME).read_bytes(),
        )
        self.assertEqual(
            first_build.manifest_hash_bytes,
            (PUBLIC_FEDERATION_V9 / MANIFEST_HASH_FILENAME).read_bytes(),
        )
        self.assertEqual(
            hashlib.sha256(first_build.index_bytes).hexdigest(),
            PUBLIC_FEDERATION_V9_INDEX_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(first_build.manifest_bytes).hexdigest(),
            PUBLIC_FEDERATION_V9_MANIFEST_SHA256,
        )

        previous = json.loads(
            (PUBLIC_FEDERATION_V8_CANDIDATE / INDEX_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        previous_releases = {
            release["release_id"]: release for release in previous["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in first["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(previous_releases) - {"epoch-official-open-seed-v13"})
            | {"epoch-official-open-seed-v20"},
        )
        self.assertNotIn("epoch-official-open-seed-v13", current_releases)
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                canonical_json(current_releases[release_id]),
                canonical_json(previous_releases[release_id]),
            )

        previous_open = previous_releases["epoch-official-open-seed-v13"]
        current_open = current_releases["epoch-official-open-seed-v20"]
        self.assertEqual(
            current_open["manifest"]["sha256"], OPEN_SEED_V20_MANIFEST_SHA256
        )
        self.assertEqual(current_open["scope"], previous_open["scope"])
        self.assertEqual(
            current_open["rights"]["license_expression"],
            previous_open["rights"]["license_expression"],
        )
        self.assertEqual(
            current_open["rights"]["source_licenses"],
            ["CC-BY-4.0", "all-rights-reserved", "public-government-record"],
        )
        self.assertIn("no underlying copyrighted", current_open["rights"]["rights_notice"])

        expected_counts = {
            "capacity_estimates": 1_178,
            "construction_pipeline_records": 6_401,
            "evidence_records": 13_195,
            "non_review_construction_pipeline_records": 271,
            "non_review_source_scoped_entity_records": 9_577,
            "release_bundles": 3,
            "resolution_candidates": 100_409,
            "review_only_construction_pipeline_records": 6_130,
            "review_only_release_bundles": 1,
            "review_only_source_scoped_entity_records": 6_130,
            "source_family_entries": 67,
            "source_scoped_entity_records": 15_707,
            "unique_physical_sites": None,
        }
        self.assertEqual(first["counts"], expected_counts)
        expected_delta = {
            "capacity_estimates": 30,
            "construction_pipeline_records": 46,
            "evidence_records": 42,
            "non_review_construction_pipeline_records": 46,
            "non_review_source_scoped_entity_records": 88,
            "release_bundles": 0,
            "resolution_candidates": 0,
            "review_only_construction_pipeline_records": 0,
            "review_only_release_bundles": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_family_entries": 23,
            "source_scoped_entity_records": 88,
        }
        for field, delta in expected_delta.items():
            self.assertEqual(first["counts"][field] - previous["counts"][field], delta)
        for field in (
            "capacity_estimates",
            "construction_pipeline_records",
            "evidence_records",
            "resolution_candidates",
            "source_family_entries",
            "source_scoped_entity_records",
        ):
            self.assertEqual(
                first["counts"][field],
                sum(release["counts"][field] for release in first["releases"]),
            )
        self.assertEqual(first["policy"], FEDERATION_POLICY)
        self.assertFalse(first["policy"]["child_entities_merged"])
        self.assertFalse(first["policy"]["cross_source_deduplication"])
        self.assertIsNone(first["counts"]["unique_physical_sites"])

        self.assertFalse(PUBLIC_FEDERATION_V9_DEFINITION.is_symlink())
        self.assertEqual(
            stat.S_IMODE(PUBLIC_FEDERATION_V9_DEFINITION.stat().st_mode), 0o644
        )
        self.require_frozen_modes(PUBLIC_FEDERATION_V8_CANDIDATE)
        self.require_frozen_modes(PUBLIC_FEDERATION_V9)

    def test_successor_fails_closed_on_wrong_v20_pin_symlink_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad_pin = self.definition_with_absolute_child_paths()
            open_child = next(
                child
                for child in bad_pin["children"]
                if child["release_id"] == "epoch-official-open-seed-v20"
            )
            open_child["expected_manifest_sha256"] = "0" * 64
            bad_pin_path = root / "bad-pin.json"
            bad_pin_path.write_bytes(canonical_json(bad_pin))
            with self.assertRaisesRegex(FederatedReleaseError, "manifest SHA-256"):
                build_federated_release_index(bad_pin_path)

            symlink_definition = self.definition_with_absolute_child_paths()
            open_child = next(
                child
                for child in symlink_definition["children"]
                if child["release_id"] == "epoch-official-open-seed-v20"
            )
            alias = root / "open-seed-v20-alias"
            alias.symlink_to(PUBLIC_FEDERATION_V9_CHILDREN[open_child["release_id"]])
            open_child["release_path"] = str(alias)
            symlink_path = root / "symlink.json"
            symlink_path.write_bytes(canonical_json(symlink_definition))
            with self.assertRaisesRegex(
                FederatedReleaseError, "child release must be a regular directory"
            ):
                build_federated_release_index(symlink_path)

            mode_copy = root / "mode-copy"
            mode_copy.mkdir()
            with self.assertRaisesRegex(FederatedReleaseError, "mode must be 0555"):
                self.require_frozen_modes(mode_copy)


if __name__ == "__main__":
    unittest.main()
