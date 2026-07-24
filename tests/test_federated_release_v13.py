from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    FederatedReleaseError,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    build_federated_release_index,
    validate_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v13.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v13"
PREVIOUS_DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v12.json"
PREVIOUS_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-19-public-open-v12"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v35.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v35"

DEFINITION_SHA256 = "0a82b9f772296da40c506c8323b8c3d1e3911d0960d9e5678adb6b7e887cf373"
INDEX_SHA256 = "5e30d71535c1700c15ddd49c05d73b6f68c293840745561015bd29e3b7c9a96c"
MANIFEST_SHA256 = "9e2c7f41bf01a2f79b322f91080325ae113b9db02bf8864c2253895c80cc1ee6"
MANIFEST_HASH_SHA256 = (
    "14c6559188fcb77c0dcf88919302383240801a78c38d843093cd4fcd8213a318"
)
PREVIOUS_DEFINITION_SHA256 = (
    "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
)
PREVIOUS_INDEX_SHA256 = (
    "266afde03fbb9eca16a0a9bfbd64c47fd50447b1b805da15542ff617f1629772"
)
PREVIOUS_MANIFEST_SHA256 = (
    "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "ade1722f44a8a97f848d94579a4cfc45bc96f7f706df80f38ad6c46cabc5735d"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "47994a012f4a97ca6dcdafb55c6b98a7121397a843ec1857328acd7953988123"
)
GENERATED_AT = "2026-07-20T00:45:00Z"
OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v33"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v35"

CHILD_MANIFEST_SHA256 = {
    NEW_OPEN_RELEASE_ID: OPEN_SEED_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    NEW_OPEN_RELEASE_ID: OPEN_SEED_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
NEW_SOURCE_FAMILIES = {
    "atnorth_newsroom",
    "green_mountain_project_pages",
    "kouvola_city_news",
    "loviisa_city_news",
    "metsahallitus_press_releases",
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1_191,
    "construction_pipeline_records": 6_454,
    "evidence_records": 13_249,
    "non_review_construction_pipeline_records": 324,
    "non_review_source_scoped_entity_records": 9_683,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 107,
    "source_scoped_entity_records": 15_813,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 2,
    "construction_pipeline_records": 5,
    "evidence_records": 6,
    "non_review_construction_pipeline_records": 5,
    "non_review_source_scoped_entity_records": 10,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 5,
    "source_scoped_entity_records": 10,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


class FederatedReleaseV13Tests(unittest.TestCase):
    def test_exact_pins_rebuild_twice_offline_and_frozen_bundle(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(INDEX_DIR / INDEX_FILENAME), INDEX_SHA256)
        self.assertEqual(sha256(INDEX_DIR / MANIFEST_FILENAME), MANIFEST_SHA256)
        self.assertEqual(
            sha256(INDEX_DIR / MANIFEST_HASH_FILENAME), MANIFEST_HASH_SHA256
        )
        self.assertEqual(sha256(PREVIOUS_DEFINITION), PREVIOUS_DEFINITION_SHA256)
        self.assertEqual(
            sha256(PREVIOUS_INDEX_DIR / INDEX_FILENAME), PREVIOUS_INDEX_SHA256
        )
        self.assertEqual(
            sha256(PREVIOUS_INDEX_DIR / MANIFEST_FILENAME),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(sha256(OPEN_SEED_DEFINITION), OPEN_SEED_DEFINITION_SHA256)
        for release_id, release in CHILDREN.items():
            self.assertFalse(release.is_symlink())
            self.assertEqual(
                sha256(release / MANIFEST_FILENAME),
                CHILD_MANIFEST_SHA256[release_id],
            )

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        offline = AssertionError("federation rebuild attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first_build = build_federated_release_index(DEFINITION)
            second_build = build_federated_release_index(DEFINITION)
            first = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            second = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )

        self.assertEqual(first_build, second_build)
        self.assertEqual(first, second)
        self.assertEqual(first_build.index, first)
        self.assertEqual(first_build.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first_build.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(
            first_build.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME]
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        entries = list(INDEX_DIR.iterdir())
        self.assertEqual(
            {path.name for path in entries},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in entries
            )
        )

    def test_exact_v12_to_v13_successor_and_arithmetic(self) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        current_definition = json.loads(DEFINITION.read_text())
        expected_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        expected_definition["generated_at"] = GENERATED_AT
        old_child = next(
            child
            for child in expected_definition["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        old_child.update(
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v35/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v35",
            }
        )
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(expected_definition))
        self.assertEqual(current_definition["schema_version"], 1)

        previous = json.loads(
            (PREVIOUS_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        previous_releases = {
            release["release_id"]: release for release in previous["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(previous_releases) - {OLD_OPEN_RELEASE_ID}) | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                current_releases[release_id], previous_releases[release_id]
            )

        previous_open = previous_releases[OLD_OPEN_RELEASE_ID]
        open_release = current_releases[NEW_OPEN_RELEASE_ID]
        open_manifest = json.loads(
            (OPEN_SEED_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(open_release["manifest"]["sha256"], OPEN_SEED_MANIFEST_SHA256)
        self.assertEqual(open_release["manifest"]["recorded_at"], "2026-07-20T00:40:00Z")
        self.assertEqual(open_release["files"], open_manifest["files"])
        self.assertEqual(
            open_release["counts"],
            {
                "capacity_estimates": 405,
                "construction_pipeline_records": 204,
                "entities_by_kind": {"campus": 225, "project": 163},
                "evidence_records": 236,
                "resolution_candidates": 4,
                "source_family_entries": 100,
                "source_scoped_entity_records": 388,
            },
        )
        self.assertEqual(
            set(open_release["source_families"])
            - set(previous_open["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertFalse(
            set(previous_open["source_families"])
            - set(open_release["source_families"])
        )
        self.assertEqual(open_release["rights"], {
            **previous_open["rights"],
            "attribution": open_release["rights"]["attribution"],
        })
        self.assertEqual(
            open_release["rights"]["license_expression"],
            previous_open["rights"]["license_expression"],
        )
        self.assertEqual(
            open_release["rights"]["rights_notice"],
            previous_open["rights"]["rights_notice"],
        )

        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        for field, delta in EXPECTED_DELTA.items():
            self.assertEqual(
                current["counts"][field] - previous["counts"][field], delta
            )
        self.assertEqual(current["generated_at"], GENERATED_AT)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertIsNone(current["policy"]["unique_physical_site_count"])

        serialized = json.dumps(current, sort_keys=True).lower()
        for forbidden_claim in (
            "commercial census",
            "global completeness",
            "physical-site total",
            "parity achieved",
        ):
            self.assertNotIn(forbidden_claim, serialized)

    def test_mutated_definition_and_child_fail_closed(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        for child in definition["children"]:
            child["release_path"] = str(CHILDREN[child["release_id"]].resolve())

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_root = Path(temporary)
            wrong_pin = json.loads(json.dumps(definition))
            open_child = next(
                child
                for child in wrong_pin["children"]
                if child["release_id"] == NEW_OPEN_RELEASE_ID
            )
            open_child["expected_manifest_sha256"] = "0" * 64
            wrong_definition = temporary_root / "wrong-pin.json"
            wrong_definition.write_bytes(canonical_json(wrong_pin))
            with self.assertRaisesRegex(
                FederatedReleaseError, "manifest SHA-256 does not match definition"
            ):
                build_federated_release_index(wrong_definition)

            child_copy = temporary_root / "mutated-open-seed"
            shutil.copytree(OPEN_SEED_RELEASE, child_copy)
            readme = child_copy / "README.md"
            readme.chmod(0o644)
            readme.write_bytes(readme.read_bytes() + b"mutated\n")
            mutated_child = json.loads(json.dumps(definition))
            copied_open_child = next(
                child
                for child in mutated_child["children"]
                if child["release_id"] == NEW_OPEN_RELEASE_ID
            )
            copied_open_child["release_path"] = str(child_copy)
            mutated_definition = temporary_root / "mutated-child.json"
            mutated_definition.write_bytes(canonical_json(mutated_child))
            with self.assertRaisesRegex(
                FederatedReleaseError, "child release file hash mismatch: README.md"
            ):
                build_federated_release_index(mutated_definition)


if __name__ == "__main__":
    unittest.main()
