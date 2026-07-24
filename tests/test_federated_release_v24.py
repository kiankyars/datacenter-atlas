from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

import datacenter_atlas.federated_release as federation_module
from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    build_federated_release_index,
    validate_federated_release_index,
    write_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v24.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v24"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v23.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-20-public-open-v23"
V55_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"

GENERATED_AT = "2026-07-20T20:06:00Z"
V55_RECORDED_AT = "2026-07-20T20:05:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v49"
NEW_RELEASE_ID = "epoch-official-open-seed-v55"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

PINS = {
    DEFINITION: "98dc26e06948ff3334a8c3e21fc7b31616cf177362217459f04cd5a9d221e6a0",
    INDEX_DIR
    / INDEX_FILENAME: "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d",
    INDEX_DIR
    / MANIFEST_FILENAME: "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1",
    INDEX_DIR
    / MANIFEST_HASH_FILENAME: "d81f5d72d6826b35c88c0ea90eab9a16f70baf0cebc3a257f41bc8489eaa9da1",
    BASE_DEFINITION: "056d36d13712e613b51d28e59ea542b82fc720e093afb142af289ae30d1b0411",
    BASE_INDEX_DIR
    / INDEX_FILENAME: "65b71358378a145a03536d5d95530c0cc96bcb711e08595ca43723b18d2880e2",
    BASE_INDEX_DIR
    / MANIFEST_FILENAME: "0e4aabf0a9612091a25adf04a1cf51431fbf3ca1026201e8d4ab5a2f3fc4e1be",
    V55_RELEASE
    / MANIFEST_FILENAME: "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
}
ARTIFACTS = {
    INDEX_FILENAME: (24_660, PINS[INDEX_DIR / INDEX_FILENAME]),
    MANIFEST_FILENAME: (986, PINS[INDEX_DIR / MANIFEST_FILENAME]),
    MANIFEST_HASH_FILENAME: (80, PINS[INDEX_DIR / MANIFEST_HASH_FILENAME]),
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1_268,
    "construction_pipeline_records": 6_596,
    "evidence_records": 13_396,
    "non_review_construction_pipeline_records": 466,
    "non_review_source_scoped_entity_records": 9_958,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 208,
    "source_scoped_entity_records": 16_088,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 15,
    "construction_pipeline_records": 19,
    "evidence_records": 31,
    "non_review_construction_pipeline_records": 19,
    "non_review_source_scoped_entity_records": 34,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 23,
    "source_scoped_entity_records": 34,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 482,
    "construction_pipeline_records": 346,
    "entities_by_kind": {"campus": 357, "project": 306},
    "evidence_records": 383,
    "resolution_candidates": 4,
    "source_family_entries": 201,
    "source_scoped_entity_records": 663,
}
CHILDREN = {
    NEW_RELEASE_ID: V55_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}
FORBIDDEN = (
    "epoch-official-open-seed-v49",
    "epoch-official-open-seed-v54",
    "releases/2026-07-20-open-seed-v49",
    "releases/2026-07-20-open-seed-v54",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV24Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v24 federation attempted network or stale child access"
        )
        original = federation_module._regular_bytes

        def guarded(path: Path, label: str) -> bytes:
            if any(marker in path.as_posix() for marker in FORBIDDEN):
                raise failure
            return original(path, label)

        stack.enter_context(
            patch.object(federation_module, "_regular_bytes", side_effect=guarded)
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_double_offline_idempotence_and_modes(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in INDEX_DIR.iterdir()}, set(ARTIFACTS))
        frozen = {}
        for path in INDEX_DIR.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
            frozen[path.name] = path.read_bytes()

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
        for marker in FORBIDDEN:
            self.assertNotIn(
                marker.encode(), b"".join([DEFINITION.read_bytes(), *frozen.values()])
            )

    def test_exact_v23_to_v55_child_swap_and_counts(self) -> None:
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
                "expected_manifest_sha256": PINS[V55_RELEASE / MANIFEST_FILENAME],
                "reference": "../../releases/2026-07-20-open-seed-v55/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v55",
            }
        )
        raw = DEFINITION.read_bytes()
        current_definition = json.loads(raw)
        self.assertEqual(raw, canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(V55_RECORDED_AT.replace("Z", "+00:00")),
        )

        base_index = json.loads((BASE_INDEX_DIR / INDEX_FILENAME).read_text())
        current = json.loads((INDEX_DIR / INDEX_FILENAME).read_text())
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertFalse(current["policy"]["cross_source_deduplication"])
        self.assertIsNone(current["policy"]["unique_physical_site_count"])
        by_id = {item["release_id"]: item for item in current["releases"]}
        base_by_id = {item["release_id"]: item for item in base_index["releases"]}
        self.assertEqual(set(by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(by_id[release_id], base_by_id[release_id])
        self.assertEqual(by_id[NEW_RELEASE_ID]["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            by_id[NEW_RELEASE_ID]["manifest"]["sha256"],
            PINS[V55_RELEASE / MANIFEST_FILENAME],
        )
        self.assertEqual(
            {
                key: current["counts"][key] - base_index["counts"][key]
                for key in EXPECTED_DELTA
            },
            EXPECTED_DELTA,
        )
        self.assertIsNone(current["counts"]["unique_physical_sites"])

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.federated_release"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.federated_release"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_federated_release_index; "
                f"result=validate_federated_release_index(Path({str(INDEX_DIR)!r})); "
                "assert result['counts']['source_scoped_entity_records']==16088; "
                "assert result['counts']['unique_physical_sites'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
