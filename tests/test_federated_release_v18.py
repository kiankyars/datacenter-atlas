from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
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
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v18.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v18"
ACCEPTED_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-20-public-open-v15.json"
)
ACCEPTED_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v15"
V42_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v42.json"
V42_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v42"
V39_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v39"

GENERATED_AT = "2026-07-20T05:00:00Z"
OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v39"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v42"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "bab7ae5e2f09e34d658663112c70b88ac3ca3b02a075380356cfe3f7af7298d0"
INDEX_SHA256 = "45048828bf4cc90e1c70fd0da86962c5a0bc0a00d588ad8c3f22e35e2597f6df"
MANIFEST_SHA256 = "3f52b09facdaa5bbea82bbef045e459901a6f3206452271482d0ea798a7f28d6"
MANIFEST_HASH_SHA256 = (
    "cbabf0f9438b009fc373e6b500e14fb58496157eaa17e97eb8478a4370cfaf26"
)
ACCEPTED_DEFINITION_SHA256 = (
    "52023873cb067e4ab4278ca7acc53a4277894634e882801914bd571fabe07da7"
)
ACCEPTED_INDEX_SHA256 = (
    "d03f67aa9ff219a8de573d5d8137c28a2f8c3c0eea32f42498b9efd20c5c6166"
)
ACCEPTED_MANIFEST_SHA256 = (
    "739dc3b1e33878bda97de8e99286a9cdfe0d80a9a3d758358f671da5b81daa0c"
)
ACCEPTED_MANIFEST_HASH_SHA256 = (
    "3511661a00e3ec8f49ba3e06445f9cdf61aed20d6e1274e7ce8ec75105bf9e89"
)
V39_MANIFEST_SHA256 = (
    "e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84"
)
V42_DEFINITION_SHA256 = (
    "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
)
V42_MANIFEST_SHA256 = (
    "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680"
)

CHILD_MANIFEST_SHA256 = {
    NEW_OPEN_RELEASE_ID: V42_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    NEW_OPEN_RELEASE_ID: V42_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
ACCEPTED_CHILD_MANIFEST_SHA256 = {
    OLD_OPEN_RELEASE_ID: V39_MANIFEST_SHA256,
    "global-open-v3": CHILD_MANIFEST_SHA256["global-open-v3"],
    "osm-fuzzy-review-v2": CHILD_MANIFEST_SHA256["osm-fuzzy-review-v2"],
}
ACCEPTED_CHILDREN = {
    OLD_OPEN_RELEASE_ID: V39_RELEASE,
    "global-open-v3": CHILDREN["global-open-v3"],
    "osm-fuzzy-review-v2": CHILDREN["osm-fuzzy-review-v2"],
}

EXPECTED_COUNTS = {
    "capacity_estimates": 1_213,
    "construction_pipeline_records": 6_512,
    "evidence_records": 13_286,
    "non_review_construction_pipeline_records": 382,
    "non_review_source_scoped_entity_records": 9_797,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 130,
    "source_scoped_entity_records": 15_927,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 9,
    "construction_pipeline_records": 47,
    "evidence_records": 20,
    "non_review_construction_pipeline_records": 47,
    "non_review_source_scoped_entity_records": 91,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 6,
    "source_scoped_entity_records": 91,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 427,
    "construction_pipeline_records": 262,
    "entities_by_kind": {"campus": 278, "project": 224},
    "evidence_records": 273,
    "resolution_candidates": 4,
    "source_family_entries": 123,
    "source_scoped_entity_records": 502,
}
NEW_SOURCE_FAMILIES = {
    "cirion_company_blog",
    "cirion_pressroom",
    "iron_mountain_data_center_location_pages",
    "iron_mountain_resources",
    "iron_mountain_sec_filings",
    "stc_sustainability_reports",
}
REJECTED_PATH_FRAGMENTS = (
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
    "sources/federation-2026-07-20-public-open-v16.json",
    "federated_indexes/2026-07-20-public-open-v16",
    "sources/federation-2026-07-20-public-open-v17.json",
    "federated_indexes/2026-07-20-public-open-v17",
)
REJECTED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        "epoch-official-open-seed-v41",
        "2026-07-20-open-seed-v41",
        "967127f07f0e30be989bfbeba2ab7884a20b4ff570357648af8c48652e67c1b5",
        "e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
        "federation-2026-07-20-public-open-v16",
        "bd7b35488f95915465b4808727a790feeb4ca864d434c62b58a330fd833ab951",
        "84879cf6329ae48e2b18c0416c3e72203ed6b5972c254607894f692416f5f357",
        "federation-2026-07-20-public-open-v17",
        "19589fb2a579046fac956fe1bda68c6469678d6e81f506459d73266794644780",
        "bb0600d6997f4874a64b5f7ff8bebaa8a77dfd448fab17b51a7bdfab57874071",
        "dff68953b205cc2cc27553bddf50a8b3e7bc11ed02e7af028c98500df0d94ae9",
    )
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(recursive_keys(child))
    return keys


def recheckpoint_bundle(directory: Path) -> None:
    index_raw = (directory / INDEX_FILENAME).read_bytes()
    manifest_path = directory / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][INDEX_FILENAME].update(
        {
            "bytes": len(index_raw),
            "sha256": hashlib.sha256(index_raw).hexdigest(),
        }
    )
    manifest_raw = canonical_json(manifest)
    manifest_path.write_bytes(manifest_raw)
    (directory / MANIFEST_HASH_FILENAME).write_bytes(
        (
            f"{hashlib.sha256(manifest_raw).hexdigest()}  "
            f"{MANIFEST_FILENAME}\n"
        ).encode("ascii")
    )


class FederatedReleaseV18Tests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        offline = AssertionError("v18 federation attempted network access")
        original_regular_bytes = federated_release_module._regular_bytes

        def guarded_regular_bytes(path: Path, label: str) -> bytes:
            normalized = path.resolve().as_posix()
            if any(fragment in normalized for fragment in REJECTED_PATH_FRAGMENTS):
                raise AssertionError(f"v18 attempted rejected path access: {path}")
            return original_regular_bytes(path, label)

        stack.enter_context(
            patch.object(
                federated_release_module,
                "_regular_bytes",
                side_effect=guarded_regular_bytes,
            )
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=offline))

    def _copy_writable(self, source: Path, destination: Path) -> None:
        shutil.copytree(source, destination)
        destination.chmod(0o755)
        for path in destination.iterdir():
            path.chmod(0o644)

    def test_exact_pins_deterministic_offline_rebuild_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            ACCEPTED_DEFINITION: ACCEPTED_DEFINITION_SHA256,
            ACCEPTED_INDEX_DIR / INDEX_FILENAME: ACCEPTED_INDEX_SHA256,
            ACCEPTED_INDEX_DIR / MANIFEST_FILENAME: ACCEPTED_MANIFEST_SHA256,
            ACCEPTED_INDEX_DIR / MANIFEST_HASH_FILENAME: (
                ACCEPTED_MANIFEST_HASH_SHA256
            ),
            V42_DEFINITION: V42_DEFINITION_SHA256,
            V42_RELEASE / MANIFEST_FILENAME: V42_MANIFEST_SHA256,
            V39_RELEASE / MANIFEST_FILENAME: V39_MANIFEST_SHA256,
        }
        pins.update(
            {
                CHILDREN[release_id] / MANIFEST_FILENAME: expected
                for release_id, expected in CHILD_MANIFEST_SHA256.items()
            }
        )
        pins.update(
            {
                ACCEPTED_CHILDREN[release_id] / MANIFEST_FILENAME: expected
                for release_id, expected in ACCEPTED_CHILD_MANIFEST_SHA256.items()
            }
        )
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        accepted_frozen = {
            path.name: path.read_bytes() for path in ACCEPTED_INDEX_DIR.iterdir()
        }
        with ExitStack() as stack:
            self._block_network(stack)
            first_build = build_federated_release_index(DEFINITION)
            second_build = build_federated_release_index(DEFINITION)
            validated = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            accepted_build = build_federated_release_index(ACCEPTED_DEFINITION)
            accepted_validated = validate_federated_release_index(
                ACCEPTED_INDEX_DIR,
                child_release_paths=ACCEPTED_CHILDREN,
            )

        self.assertEqual(first_build, second_build)
        self.assertEqual(first_build.index, validated)
        self.assertEqual(first_build.index_bytes, frozen[INDEX_FILENAME])
        self.assertEqual(first_build.manifest_bytes, frozen[MANIFEST_FILENAME])
        self.assertEqual(
            first_build.manifest_hash_bytes, frozen[MANIFEST_HASH_FILENAME]
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in ACCEPTED_INDEX_DIR.iterdir()
            },
            accepted_frozen,
        )
        self.assertEqual(accepted_build.index, accepted_validated)
        self.assertEqual(
            accepted_build.index_bytes,
            accepted_frozen[INDEX_FILENAME],
        )
        self.assertEqual(
            accepted_build.manifest_bytes,
            accepted_frozen[MANIFEST_FILENAME],
        )
        self.assertEqual(
            accepted_build.manifest_hash_bytes,
            accepted_frozen[MANIFEST_HASH_FILENAME],
        )

        current_payloads = [DEFINITION.read_bytes()]
        current_payloads.extend(path.read_bytes() for path in INDEX_DIR.iterdir())
        for marker in REJECTED_MARKERS:
            self.assertFalse(any(marker in payload for payload in current_payloads))

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

    def test_v18_is_exact_v15_child_swap_with_child_scoped_int_marker(self) -> None:
        accepted_definition = json.loads(
            ACCEPTED_DEFINITION.read_text(encoding="utf-8")
        )
        expected_definition = json.loads(
            ACCEPTED_DEFINITION.read_text(encoding="utf-8")
        )
        expected_definition["generated_at"] = GENERATED_AT
        old_child = next(
            child
            for child in expected_definition["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        old_child.update(
            {
                "expected_manifest_sha256": V42_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v42/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v42",
            }
        )
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(expected_definition))

        current_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        accepted_children = {
            child["release_id"]: child for child in accepted_definition["children"]
        }
        current_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(
            set(current_children),
            (set(accepted_children) - {OLD_OPEN_RELEASE_ID})
            | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_children[release_id], accepted_children[release_id])

        accepted_index = json.loads(
            (ACCEPTED_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current_index = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        accepted_releases = {
            release["release_id"]: release for release in accepted_index["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current_index["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(accepted_releases) - {OLD_OPEN_RELEASE_ID})
            | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_releases[release_id], accepted_releases[release_id])
            self.assertNotIn(
                "publication_contract_version",
                current_releases[release_id]["manifest"],
            )

        marked = [
            release
            for release in current_index["releases"]
            if "publication_contract_version" in release["manifest"]
        ]
        self.assertEqual([release["release_id"] for release in marked], [NEW_OPEN_RELEASE_ID])
        marker = marked[0]["manifest"]["publication_contract_version"]
        self.assertIs(type(marker), int)
        self.assertEqual(marker, 4)
        v42_marker = json.loads(V42_DEFINITION.read_text(encoding="utf-8"))[
            "publication_contract_version"
        ]
        self.assertIs(type(v42_marker), int)
        self.assertEqual(v42_marker, 4)

        expected_index = json.loads(
            (ACCEPTED_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        expected_index["generated_at"] = GENERATED_AT
        expected_index["counts"] = EXPECTED_COUNTS
        expected_index["releases"] = sorted(
            [
                current_releases[NEW_OPEN_RELEASE_ID]
                if release["release_id"] == OLD_OPEN_RELEASE_ID
                else release
                for release in expected_index["releases"]
            ],
            key=lambda release: release["release_id"],
        )
        self.assertEqual(current_index, expected_index)

    def test_exact_child_and_federation_deltas_without_capacity_claims(self) -> None:
        accepted = json.loads(
            (ACCEPTED_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        accepted_releases = {
            release["release_id"]: release for release in accepted["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current["releases"]
        }
        old_open = accepted_releases[OLD_OPEN_RELEASE_ID]
        new_open = current_releases[NEW_OPEN_RELEASE_ID]
        v42_manifest = json.loads(
            (V42_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )

        self.assertEqual(new_open["manifest"]["sha256"], V42_MANIFEST_SHA256)
        self.assertEqual(new_open["manifest"]["recorded_at"], "2026-07-20T04:45:00Z")
        self.assertGreater(current["generated_at"], new_open["manifest"]["recorded_at"])
        self.assertEqual(new_open["files"], v42_manifest["files"])
        self.assertEqual(new_open["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            set(new_open["source_families"]) - set(old_open["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertFalse(
            set(old_open["source_families"]) - set(new_open["source_families"])
        )
        for field in ("license_expression", "rights_notice", "source_licenses"):
            self.assertEqual(new_open["rights"][field], old_open["rights"][field])

        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        for field, delta in EXPECTED_DELTA.items():
            self.assertEqual(
                current["counts"][field] - accepted["counts"][field], delta, field
            )
        for field in (
            "capacity_estimates",
            "construction_pipeline_records",
            "evidence_records",
            "resolution_candidates",
            "source_family_entries",
            "source_scoped_entity_records",
        ):
            self.assertEqual(
                current["counts"][field],
                sum(release["counts"][field] for release in current["releases"]),
                field,
            )
        self.assertEqual(current["generated_at"], GENERATED_AT)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertIs(type(current["counts"]["capacity_estimates"]), int)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertIsNone(current["policy"]["unique_physical_site_count"])

        summary = json.loads(
            (V42_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(
            summary["capacity_aggregation"],
            {
                "base_totals_published": False,
                "cross_entity_sum_valid": False,
                "reason": (
                    "Capacity rows can be nested, component-scoped, superseding, "
                    "or metric-distinct. Arithmetic sums are not valid facility, "
                    "site, load, energy, or unique-physical-site totals."
                ),
                "scope": "typed_source_observation_rows",
            },
        )
        keys = recursive_keys(current)
        self.assertNotIn("capacity_base_totals", keys)
        self.assertNotIn("capacity_aggregation", keys)
        self.assertFalse(any(key.endswith(("_mw", "_mwh")) for key in keys))
        self.assertFalse(
            any(
                path.suffix in {".csv", ".geojson", ".sqlite"}
                for path in INDEX_DIR.iterdir()
            )
        )

    def test_boolean_publication_marker_and_descriptor_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            malformed_marker = root / "malformed-marker"
            self._copy_writable(INDEX_DIR, malformed_marker)
            malformed_path = malformed_marker / INDEX_FILENAME
            malformed_index = json.loads(malformed_path.read_text(encoding="utf-8"))
            malformed_child = next(
                release
                for release in malformed_index["releases"]
                if release["release_id"] == NEW_OPEN_RELEASE_ID
            )
            malformed_child["manifest"]["publication_contract_version"] = True
            malformed_path.write_bytes(canonical_json(malformed_index))
            recheckpoint_bundle(malformed_marker)
            with self.assertRaisesRegex(FederatedReleaseError, "positive integer"):
                validate_federated_release_index(malformed_marker)

            child_drift = root / "child-drift"
            self._copy_writable(V42_RELEASE, child_drift)
            child_manifest_path = child_drift / MANIFEST_FILENAME
            child_manifest = json.loads(
                child_manifest_path.read_text(encoding="utf-8")
            )
            child_manifest["publication_contract_version"] = 3
            child_manifest_path.write_bytes(canonical_json(child_manifest))
            drifted_children = dict(CHILDREN)
            drifted_children[NEW_OPEN_RELEASE_ID] = child_drift
            with self.assertRaisesRegex(FederatedReleaseError, "manifest SHA-256"):
                validate_federated_release_index(
                    INDEX_DIR, child_release_paths=drifted_children
                )


if __name__ == "__main__":
    unittest.main()
