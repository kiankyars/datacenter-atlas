from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.federated_release as federated_release_module
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
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v23.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v23"
BASE_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v22.json"
BASE_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v22"
V49_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v49.json"
V49_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v49"

GENERATED_AT = "2026-07-20T16:49:00Z"
V49_RECORDED_AT = "2026-07-20T16:45:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v47"
NEW_RELEASE_ID = "epoch-official-open-seed-v49"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "056d36d13712e613b51d28e59ea542b82fc720e093afb142af289ae30d1b0411"
INDEX_SHA256 = "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2"
MANIFEST_SHA256 = "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be"
MANIFEST_HASH_SHA256 = (
    "832a7015714316ab682b243c895f36cd293806a764ea1fafda02c85aca40399e"
)
BASE_DEFINITION_SHA256 = (
    "87f8cf1b662431bcd3436ff89eaa8398b26d6cf42adfb1fdb9273d7fd06c37f6"
)
BASE_INDEX_SHA256 = "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c"
BASE_MANIFEST_SHA256 = (
    "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94"
)
BASE_MANIFEST_HASH_SHA256 = (
    "6355c538fed68b6f1c015f1922d446b86010148cadaebec0032b8c9fe7422d46"
)
V49_DEFINITION_SHA256 = (
    "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c"
)
V49_MANIFEST_SHA256 = (
    "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
)

FORBIDDEN_CURRENT_MARKERS = {
    "sources/federation-2026-07-20-public-open-v21.json",
    "federated_indexes/2026-07-20-public-open-v21",
    "epoch-official-open-seed-v48",
    "sources/open-seed-2026-07-20-v48.json",
    "releases/2026-07-20-open-seed-v48",
    OLD_RELEASE_ID,
    "sources/open-seed-2026-07-20-v47.json",
    "releases/2026-07-20-open-seed-v47",
}
FORBIDDEN_READ_FRAGMENTS = tuple(FORBIDDEN_CURRENT_MARKERS)

EXPECTED_COUNTS = {
    "capacity_estimates": 1_253,
    "construction_pipeline_records": 6_577,
    "evidence_records": 13_365,
    "non_review_construction_pipeline_records": 447,
    "non_review_source_scoped_entity_records": 9_924,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 185,
    "source_scoped_entity_records": 16_054,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 13,
    "construction_pipeline_records": 14,
    "evidence_records": 15,
    "non_review_construction_pipeline_records": 14,
    "non_review_source_scoped_entity_records": 28,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 9,
    "source_scoped_entity_records": 28,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 467,
    "construction_pipeline_records": 327,
    "entities_by_kind": {"campus": 340, "project": 289},
    "evidence_records": 352,
    "resolution_candidates": 4,
    "source_family_entries": 178,
    "source_scoped_entity_records": 629,
}
CHILDREN = {
    NEW_RELEASE_ID: V49_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV23Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v23 federation attempted network or superseded/rejected child access"
        )
        original = federated_release_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            rendered = path.as_posix()
            if any(marker in rendered for marker in FORBIDDEN_READ_FRAGMENTS):
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(
                federated_release_module,
                "_regular_bytes",
                side_effect=guarded,
            )
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_double_offline_idempotence_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            BASE_DEFINITION: BASE_DEFINITION_SHA256,
            BASE_INDEX_DIR / INDEX_FILENAME: BASE_INDEX_SHA256,
            BASE_INDEX_DIR / MANIFEST_FILENAME: BASE_MANIFEST_SHA256,
            BASE_INDEX_DIR / MANIFEST_HASH_FILENAME: BASE_MANIFEST_HASH_SHA256,
            V49_DEFINITION: V49_DEFINITION_SHA256,
            V49_RELEASE / MANIFEST_FILENAME: V49_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        for path in INDEX_DIR.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = build_federated_release_index(DEFINITION)
            second = build_federated_release_index(DEFINITION)
            validated = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            idempotent = write_federated_release_index(DEFINITION, INDEX_DIR)
        self.assertEqual(first, second)
        self.assertEqual(first.index, validated)
        self.assertEqual(first.index, idempotent)
        self.assertEqual(first.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(first.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME])
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in FORBIDDEN_CURRENT_MARKERS:
            encoded = marker.encode("ascii")
            self.assertFalse(any(encoded in payload for payload in payloads), marker)

    def test_v23_is_exact_v22_to_v49_child_swap_with_exact_counts(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["generated_at"] = GENERATED_AT
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V49_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v49/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v49",
            }
        )
        current_raw = DEFINITION.read_bytes()
        current = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current))
        self.assertEqual(current, expected)

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        child_recorded = datetime.fromisoformat(
            V49_RECORDED_AT.replace("Z", "+00:00")
        )
        self.assertGreater(generated, child_recorded)

        base_index = json.loads((BASE_INDEX_DIR / INDEX_FILENAME).read_text())
        current_index = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        self.assertEqual(current_index["generated_at"], GENERATED_AT)
        self.assertEqual(current_index["counts"], EXPECTED_COUNTS)
        self.assertEqual(current_index["policy"], FEDERATION_POLICY)
        self.assertFalse(current_index["policy"]["child_entities_merged"])
        self.assertFalse(current_index["policy"]["cross_source_deduplication"])
        self.assertIsNone(current_index["policy"]["unique_physical_site_count"])

        by_id = {
            item["release_id"]: item for item in current_index["releases"]
        }
        base_by_id = {
            item["release_id"]: item for item in base_index["releases"]
        }
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])
        self.assertEqual(by_id[NEW_RELEASE_ID]["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"], V49_MANIFEST_SHA256
        )
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["recorded_at"], V49_RECORDED_AT
        )
        self.assertFalse(by_id[NEW_RELEASE_ID]["scope"]["review_only"])

        delta = {
            key: current_index["counts"][key] - base_index["counts"][key]
            for key in EXPECTED_DELTA
        }
        self.assertEqual(delta, EXPECTED_DELTA)
        self.assertTrue(by_id["osm-fuzzy-review-v2"]["scope"]["review_only"])
        self.assertEqual(
            current_index["counts"]["source_scoped_entity_records"],
            current_index["counts"]["review_only_source_scoped_entity_records"]
            + current_index["counts"]["non_review_source_scoped_entity_records"],
        )
        self.assertIsNone(current_index["counts"]["unique_physical_sites"])

    def test_late_output_collision_is_refused_without_overwrite(self) -> None:
        original_validate = federated_release_module.validate_federated_release_index
        with tempfile.TemporaryDirectory(dir=INDEX_DIR.parent) as temporary:
            output = Path(temporary)
            output.rmdir()
            sentinel = output / "sentinel.txt"

            def validate_then_race(*args: object, **kwargs: object) -> object:
                validated = original_validate(*args, **kwargs)
                output.mkdir()
                sentinel.write_text("late arrival\n", encoding="utf-8")
                return validated

            with patch.object(
                federated_release_module,
                "validate_federated_release_index",
                side_effect=validate_then_race,
            ):
                with self.assertRaisesRegex(
                    FederatedReleaseError, "appeared during publication"
                ):
                    write_federated_release_index(DEFINITION, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "late arrival\n")


if __name__ == "__main__":
    unittest.main()
