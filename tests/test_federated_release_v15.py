from __future__ import annotations

import csv
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.federated_release import (
    FEDERATION_POLICY,
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    build_federated_release_index,
    validate_federated_release_index,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v15.json"
INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v15"
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-20-public-open-v14.json"
)
PREVIOUS_INDEX_DIR = ROOT / "federated_indexes" / "2026-07-20-public-open-v14"
REJECTED_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-20-public-open-v13.json"
)
V37_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v37"
V39_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v39.json"
V39_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v39"

GENERATED_AT = "2026-07-20T02:35:00Z"
OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v37"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v39"

DEFINITION_SHA256 = "52023873cb067e4ab4278ca7acc53a4277894634e882801914bd571fabe07da7"
INDEX_SHA256 = "d03f67aa9ff219a8de573d5d8137c28a2f8c3c0eea32f42498b9efd20c5c6166"
MANIFEST_SHA256 = "739dc3b1e33878bda97de8e99286a9cdfe0d80a9a3d758358f671da5b81daa0c"
MANIFEST_HASH_SHA256 = (
    "3511661a00e3ec8f49ba3e06445f9cdf61aed20d6e1274e7ce8ec75105bf9e89"
)
PREVIOUS_DEFINITION_SHA256 = (
    "03edc750359d2abe63f7a9cb4c83f0309767e44bf259190eda44c53a6bf6aaf4"
)
PREVIOUS_INDEX_SHA256 = (
    "3f191e568fec07693f03d7f3870e63ea67b3cf5dc12535ac03fe0632190016d9"
)
PREVIOUS_MANIFEST_SHA256 = (
    "ed4ab597becd2971de56a72acc39a754bb85b29bbdcb05e5c9a9674fb6c5e8ec"
)
PREVIOUS_MANIFEST_HASH_SHA256 = (
    "38e3925b02d31d66fcfceed8cc3d1075739776fe23d0cc44629c2e1bc3c71fab"
)
REJECTED_DEFINITION_SHA256 = (
    "0a82b9f772296da40c506c8323b8c3d1e3911d0960d9e5678adb6b7e887cf373"
)
V37_MANIFEST_SHA256 = (
    "bcc0d1207e5b4c709557f49fc6d42e1080dcaebb762b32093848461afd52d30a"
)
V39_DEFINITION_SHA256 = (
    "2b0b219e94e98782f58128ea7db9c9b954e44d0694f33cc17e7807a71e6ef381"
)
V39_MANIFEST_SHA256 = (
    "e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84"
)

UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}
CHILD_MANIFEST_SHA256 = {
    NEW_OPEN_RELEASE_ID: V39_MANIFEST_SHA256,
    "global-open-v3": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    "osm-fuzzy-review-v2": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
}
CHILDREN = {
    NEW_OPEN_RELEASE_ID: V39_RELEASE,
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases" / "2026-07-18-osm-fuzzy-review-v2",
}
PREVIOUS_CHILDREN = {
    OLD_OPEN_RELEASE_ID: V37_RELEASE,
    "global-open-v3": CHILDREN["global-open-v3"],
    "osm-fuzzy-review-v2": CHILDREN["osm-fuzzy-review-v2"],
}

NEW_SOURCE_FAMILIES = {
    "cipher_digital_sec_exhibits",
    "cipher_digital_sec_filings",
    "cipher_sec_exhibits",
    "cipher_sec_investor_presentations",
    "core_scientific_sec_exhibits",
    "green_data_center_facility_pages",
    "iij_investor_relations",
    "iij_press_releases",
    "softbank_news",
    "softbank_sustainability",
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1_204,
    "construction_pipeline_records": 6_465,
    "evidence_records": 13_266,
    "non_review_construction_pipeline_records": 335,
    "non_review_source_scoped_entity_records": 9_706,
    "release_bundles": 3,
    "resolution_candidates": 100_409,
    "review_only_construction_pipeline_records": 6_130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6_130,
    "source_family_entries": 124,
    "source_scoped_entity_records": 15_836,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 7,
    "construction_pipeline_records": 7,
    "evidence_records": 10,
    "non_review_construction_pipeline_records": 7,
    "non_review_source_scoped_entity_records": 15,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 10,
    "source_scoped_entity_records": 15,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 418,
    "construction_pipeline_records": 215,
    "entities_by_kind": {"campus": 235, "project": 176},
    "evidence_records": 253,
    "resolution_candidates": 4,
    "source_family_entries": 117,
    "source_scoped_entity_records": 411,
}
ROLE_FIELDS = (("users", "user"), ("tenants", "tenant"), ("customers", "customer"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise AssertionError(f"missing CSV header: {path}")
        return fieldnames, list(reader)


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


class FederatedReleaseV15Tests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        offline = AssertionError("v15 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=offline))

    def test_exact_pins_rebuild_twice_offline_and_frozen_bundle(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / MANIFEST_HASH_FILENAME: MANIFEST_HASH_SHA256,
            PREVIOUS_DEFINITION: PREVIOUS_DEFINITION_SHA256,
            PREVIOUS_INDEX_DIR / INDEX_FILENAME: PREVIOUS_INDEX_SHA256,
            PREVIOUS_INDEX_DIR / MANIFEST_FILENAME: PREVIOUS_MANIFEST_SHA256,
            PREVIOUS_INDEX_DIR / MANIFEST_HASH_FILENAME: (
                PREVIOUS_MANIFEST_HASH_SHA256
            ),
            REJECTED_DEFINITION: REJECTED_DEFINITION_SHA256,
            V37_RELEASE / MANIFEST_FILENAME: V37_MANIFEST_SHA256,
            V39_DEFINITION: V39_DEFINITION_SHA256,
            V39_RELEASE / MANIFEST_FILENAME: V39_MANIFEST_SHA256,
        }
        pins.update(
            {
                CHILDREN[release_id] / MANIFEST_FILENAME: expected
                for release_id, expected in CHILD_MANIFEST_SHA256.items()
            }
        )
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)

        current_frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        previous_frozen = {
            path.name: path.read_bytes() for path in PREVIOUS_INDEX_DIR.iterdir()
        }
        with ExitStack() as stack:
            self._block_network(stack)
            first_build = build_federated_release_index(DEFINITION)
            second_build = build_federated_release_index(DEFINITION)
            first = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            second = validate_federated_release_index(
                INDEX_DIR, child_release_paths=CHILDREN
            )
            previous = validate_federated_release_index(
                PREVIOUS_INDEX_DIR, child_release_paths=PREVIOUS_CHILDREN
            )

        self.assertEqual(first_build, second_build)
        self.assertEqual(first, second)
        self.assertEqual(first_build.index, first)
        self.assertEqual(first_build.index_bytes, current_frozen[INDEX_FILENAME])
        self.assertEqual(
            first_build.manifest_bytes, current_frozen[MANIFEST_FILENAME]
        )
        self.assertEqual(
            first_build.manifest_hash_bytes,
            current_frozen[MANIFEST_HASH_FILENAME],
        )
        self.assertEqual(previous["counts"], json.loads(
            previous_frozen[INDEX_FILENAME]
        )["counts"])
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()},
            current_frozen,
        )
        self.assertEqual(
            {path.name: path.read_bytes() for path in PREVIOUS_INDEX_DIR.iterdir()},
            previous_frozen,
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

    def test_v15_is_v14_with_only_v37_replaced_by_v39(self) -> None:
        previous_definition = json.loads(
            PREVIOUS_DEFINITION.read_text(encoding="utf-8")
        )
        current_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected_definition = json.loads(
            PREVIOUS_DEFINITION.read_text(encoding="utf-8")
        )
        expected_definition["generated_at"] = GENERATED_AT
        old_child = next(
            child
            for child in expected_definition["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        old_child.update(
            {
                "expected_manifest_sha256": V39_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-20-open-seed-v39/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v39",
            }
        )
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(expected_definition))
        self.assertEqual(current_definition["schema_version"], 1)
        self.assertEqual(current_definition["generated_at"], GENERATED_AT)

        previous_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        current_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(
            set(current_children),
            (set(previous_children) - {OLD_OPEN_RELEASE_ID})
            | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(
                current_children[release_id], previous_children[release_id]
            )

        replaced = current_children[NEW_OPEN_RELEASE_ID]
        previous = previous_children[OLD_OPEN_RELEASE_ID]
        self.assertEqual(
            replaced,
            {
                "expected_manifest_sha256": V39_MANIFEST_SHA256,
                "license_expression": previous["license_expression"],
                "reference": "../../releases/2026-07-20-open-seed-v39/",
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v39",
                "rights_notice": previous["rights_notice"],
            },
        )

        previous_index = json.loads(
            (PREVIOUS_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current_index = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        previous_releases = {
            release["release_id"]: release
            for release in previous_index["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current_index["releases"]
        }
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(
                current_releases[release_id], previous_releases[release_id]
            )

        serialized = DEFINITION.read_text(encoding="utf-8")
        self.assertNotIn("open-seed-v35", serialized)
        self.assertNotIn("public-open-v13", serialized)
        self.assertNotEqual(
            current_definition,
            json.loads(REJECTED_DEFINITION.read_text(encoding="utf-8")),
        )

    def test_exact_child_and_federation_count_deltas(self) -> None:
        previous = json.loads(
            (PREVIOUS_INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        previous_releases = {
            release["release_id"]: release for release in previous["releases"]
        }
        current_releases = {
            release["release_id"]: release for release in current["releases"]
        }
        self.assertEqual(
            set(current_releases),
            (set(previous_releases) - {OLD_OPEN_RELEASE_ID})
            | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(
                current_releases[release_id], previous_releases[release_id]
            )

        old_open = previous_releases[OLD_OPEN_RELEASE_ID]
        new_open = current_releases[NEW_OPEN_RELEASE_ID]
        v39_manifest = json.loads(
            (V39_RELEASE / MANIFEST_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(new_open["manifest"]["sha256"], V39_MANIFEST_SHA256)
        self.assertEqual(
            new_open["manifest"]["recorded_at"], "2026-07-20T02:17:49Z"
        )
        self.assertEqual(new_open["files"], v39_manifest["files"])
        self.assertEqual(new_open["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            set(new_open["source_families"]) - set(old_open["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertFalse(
            set(old_open["source_families"]) - set(new_open["source_families"])
        )
        self.assertEqual(
            len(new_open["source_families"]) - len(old_open["source_families"]),
            10,
        )
        self.assertEqual(
            new_open["rights"]["license_expression"],
            old_open["rights"]["license_expression"],
        )
        self.assertEqual(
            new_open["rights"]["rights_notice"],
            old_open["rights"]["rights_notice"],
        )
        self.assertEqual(
            new_open["rights"]["source_licenses"],
            old_open["rights"]["source_licenses"],
        )

        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        for field, delta in EXPECTED_DELTA.items():
            self.assertEqual(
                current["counts"][field] - previous["counts"][field],
                delta,
                field,
            )
        self.assertEqual(current["generated_at"], GENERATED_AT)
        self.assertEqual(current["policy"], FEDERATION_POLICY)
        self.assertEqual(
            current["counts"]["review_only_source_scoped_entity_records"],
            previous["counts"]["review_only_source_scoped_entity_records"],
        )
        self.assertEqual(
            current["counts"]["review_only_construction_pipeline_records"],
            previous["counts"]["review_only_construction_pipeline_records"],
        )
        self.assertEqual(
            current["counts"]["resolution_candidates"],
            previous["counts"]["resolution_candidates"],
        )

    def test_v39_v3_role_and_nonadditivity_contract_remains_child_scoped(self) -> None:
        v39_definition = json.loads(V39_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(v39_definition["publication_contract_version"], 3)

        for filename in ("entities.csv", "construction_pipeline.csv"):
            fieldnames, rows = csv_rows(V39_RELEASE / filename)
            role_start = fieldnames.index("users")
            self.assertEqual(
                fieldnames[role_start : role_start + 3],
                ["users", "tenants", "customers"],
            )
            for row in rows:
                tags = json.loads(row["tags_json"])
                for plural, singular in ROLE_FIELDS:
                    expected = tags.get(plural) or tags.get(f"role:{singular}") or ""
                    self.assertEqual(row[plural], expected, (filename, row["stable_key"]))

        _, entities = csv_rows(V39_RELEASE / "entities.csv")
        by_key = {row["stable_key"]: row for row in entities}
        tenant = by_key[
            "curated:cipher-digital-black-pearl-wink-texas-data-center-campus:"
            "aws-phase-1-retrofit"
        ]
        self.assertEqual(tenant["tenants"], "Amazon Web Services, Inc.")
        self.assertEqual(tenant["users"], "")
        self.assertEqual(tenant["customers"], "")
        user = by_key["curated:hyperco-dayone-koria-unnamed-data-center-campus"]
        self.assertEqual(user["users"], "TikTok")
        self.assertEqual(user["tenants"], "")
        self.assertEqual(user["customers"], "")
        customer = by_key[
            "curated:related-openai-oracle-stargate-michigan-saline"
        ]
        self.assertEqual(customer["customers"], "OpenAI; Oracle")
        self.assertEqual(customer["users"], "")
        self.assertEqual(customer["tenants"], "")

        summary = json.loads(
            (V39_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(
            summary["capacity_aggregation"],
            {
                "base_totals_published": False,
                "cross_entity_sum_valid": False,
                "reason": (
                    "Capacity rows can be nested, component-scoped, superseding, or "
                    "metric-distinct. Arithmetic sums are not valid facility, site, load, "
                    "energy, or unique-physical-site totals."
                ),
                "scope": "typed_source_observation_rows",
            },
        )
        readme = (V39_RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("Role columns are dimensioned", readme)
        self.assertIn("does not publish aggregate capacity totals", readme)

        index = json.loads(
            (INDEX_DIR / INDEX_FILENAME).read_text(encoding="utf-8")
        )
        keys = recursive_keys(index)
        self.assertNotIn("capacity_base_totals", keys)
        self.assertNotIn("capacity_aggregation", keys)
        self.assertFalse(any(key.endswith(("_mw", "_mwh")) for key in keys))
        self.assertEqual(index["counts"], EXPECTED_COUNTS)
        self.assertIsInstance(index["counts"]["capacity_estimates"], int)
        self.assertIsNone(index["counts"]["unique_physical_sites"])
        self.assertTrue(index["policy"]["federation_only"])
        self.assertFalse(index["policy"]["child_payloads_copied"])
        self.assertFalse(index["policy"]["child_entities_merged"])
        self.assertFalse(index["policy"]["cross_source_deduplication"])
        self.assertIsNone(index["policy"]["unique_physical_site_count"])
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            {INDEX_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        self.assertFalse(
            any(
                path.suffix in {".csv", ".geojson", ".sqlite"}
                for path in INDEX_DIR.iterdir()
            )
        )

        serialized = json.dumps(index, sort_keys=True).lower()
        for forbidden_claim in (
            "commercial census",
            "global completeness",
            "physical-site total",
            "parity achieved",
            "single comprehensive inventory",
            "deduplicated site count",
        ):
            self.assertNotIn(forbidden_claim, serialized)


if __name__ == "__main__":
    unittest.main()
