from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_master_v12 as master
    from datacenter_atlas import construction_master_v12 as shim
except ModuleNotFoundError:
    from datacenter_atlas import construction_master_v12 as master
    import construction_master_v12 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v27.json"
)
PREPARATION_DEFINITION_PIN = (
    5_659,
    "02f974ce734fd9fccf3d458f2fa25abd44ce5f36efc08d9527a43edccd0c83fd",
)
PREPARATION_MANIFEST_PIN = (
    9_720,
    "53593fdbfc4232ff9aa7c2d98bbe417c7b8e4b51c86d18842da5a1eeaedb5aa2",
)
PREPARATION_TREE_PIN = (
    "839b986a00689678e131d4221ff3a91f7d20be318338f0757a6e5ff75d3290ca"
)
FINAL_DEFINITION_PIN = (
    5_659,
    "e93b0f3e7750c90a03cca5afe349ea04ae9790b607fa0b09de9ce394a1ad4533",
)
FINAL_MANIFEST_PIN = (
    9_720,
    "fbdd682a74cf762573fd607632c1f6b44a2ef2792db1fddb577e99ab8c2ba24c",
)
FINAL_TREE_PIN = "ab0cd348fd72700e012902f5130a3cbb3045e897d9609f32583fc4fa0a25209f"
FINAL_ARTIFACTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "2bfd471dae856e1abed03e9826b5095fac55a9ce8833dc56e562770058a6cc32",
    ),
    "README.md": (
        1_349,
        "95a382649e9225aa3905710e336d2f3827f7f6895e0070427e9826df49a4d494",
    ),
    "construction-master.csv": (
        189_900_522,
        "621658943aa9ae5f1405e5c06446f2cff1565e6c057daab1e1d803e5c9ce2bc9",
    ),
    "construction-master.jsonl": (
        325_780_400,
        "bab576bd07cdf6d1d0c120834fb8bb1ab764de09051ddf71b58f5626c2f9621b",
    ),
    "coverage.json": (
        8_550,
        "cf3fe9a5b8864a02900f5711617f18e6a496ce6e5cdbbfb53f42875f000f553a",
    ),
    "manifest.json": FINAL_MANIFEST_PIN,
    "manifest.sha256": (
        80,
        "7f8e4180587bf7aa9912fb9848f9a0f2465676ad3000208f13fe768c4b48cc18",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_master_v12.py": (
        27_459,
        "a08a75baad8a1a276f5347bd31f50a4bc64b697df2fbbd4c86e16cea30444c25",
    ),
    ROOT / "construction_master_v12.py": (
        241,
        "420ca27a1caba0cdf9dd1b6c4c6a0d6071159790a65acb9cfe9a20d99f1b7b08",
    ),
    ROOT / "scripts/build_construction_master_v12.py": (
        3_756,
        "8f2a4d9bdebe646566828c21a958da08e616a88490a98c611f3c85187ff498ca",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMasterV28Tests(unittest.TestCase):
    def test_v28_is_the_closed_v27_to_v71_successor(self) -> None:
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_text())
        current = master.construction_master_v28_definition()
        expected = deepcopy(predecessor)
        expected["expected"] = {
            **master.EXPECTED_FIXED,
            **master.EXPECTED_DIGESTS,
        }
        expected["generated_at"] = master.GENERATED_AT
        expected["inputs"]["replacement_release"] = deepcopy(
            master.REPLACEMENT_INPUTS
        )
        expected["master_id"] = master.MASTER_ID
        self.assertEqual(current, expected)
        self.assertEqual(current["scope"], predecessor["scope"])
        self.assertEqual(
            current["inputs"]["base_master"],
            predecessor["inputs"]["base_master"],
        )
        self.assertEqual(
            current["inputs"]["satellite_recovery_acceptance"],
            predecessor["inputs"]["satellite_recovery_acceptance"],
        )
        self.assertEqual(
            set(current),
            {
                "expected",
                "format",
                "generated_at",
                "inputs",
                "master_id",
                "schema_version",
                "scope",
            },
        )

    def test_checkpoint_only_children_are_not_master_provenance(self) -> None:
        master.validate_dependency_closure_v28()
        self.assertEqual(
            set(master.ACCEPTED_DEPENDENCY_CLOSURE),
            {
                "federation_v31",
                "identity_v8",
                "open_seed_v71",
                "predecessor_master_v27",
                "timeline_v5",
            },
        )
        raw = master.construction_master_v28_definition_bytes()
        for token in (
            b"federation-2026-07-21-public-open-v31",
            b"exact-identity-decisions-2026-07-21-public-open-v8",
            b"construction-timeline-2026-07-21-public-open-v5",
        ):
            self.assertNotIn(token, raw)
        self.assertIn(b"open-seed-2026-07-21-v71", raw)

    def test_actual_v71_counts_and_digests_are_exact(self) -> None:
        self.assertEqual(
            master.EXPECTED_FIXED,
            {
                "added_replacement_rows": 217,
                "base_replaced_rows": 199,
                "base_rows": 109111,
                "inherited_rows": 108912,
                "replacement_rows": 416,
                "replacement_rows_with_any_role": 145,
                "replacement_rows_with_customers": 2,
                "replacement_rows_with_operator": 59,
                "replacement_rows_with_owner": 48,
                "replacement_rows_with_source_role_tags": 106,
                "replacement_rows_with_tenants": 7,
                "replacement_rows_with_users": 36,
                "rows_with_contract_marker": 416,
                "satellite_recovery_control_plane_bytes": 15313,
                "satellite_recovery_rows": 0,
                "tier_a_rows": 536,
                "tier_b_rows": 6298,
                "tier_c_rows": 102494,
                "total_rows": 109328,
                "unchanged_replacement_rows": 199,
            },
        )
        self.assertEqual(
            master.EXPECTED_DIGESTS,
            {
                "added_source_record_ids_sha256": (
                    "3095a75223675a90e1c654b107bef1f8e29bce43505dc66572e72f93233869ea"
                ),
                "base_replaced_source_record_ids_sha256": (
                    "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
                ),
                "inherited_rows_without_roles_sha256": (
                    "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
                ),
                "replacement_role_projection_sha256": (
                    "9c566f52b2b9ca3c895b6669454924717424df17d09c03a637ab0e79794eaf08"
                ),
                "replacement_rows_without_roles_sha256": (
                    "6adb69e298ec760b996d34d801e53e406fb04de23bdfea6062c660630e89a9c0"
                ),
                "replacement_source_record_ids_sha256": (
                    "6ab7fd97029c5fa613f037608cc238186ec0198156efd2227132a0234d332b67"
                ),
                "tier_a_arithmetic_projection_sha256": (
                    "51398b146ebb1cb6f8f68e3a1804639a47609aec198a8e4ecf40faac18d31b06"
                ),
            },
        )

    def test_private_frozen_build_and_second_replay_are_byte_exact(self) -> None:
        published = master.DEFINITION_PATH.exists() or master.BUNDLE_PATH.exists()
        self.assertEqual(
            master.DEFINITION_PATH.exists(), master.BUNDLE_PATH.exists()
        )
        transaction = None
        if published:
            definition = master.DEFINITION_PATH
            bundle = master.BUNDLE_PATH
        else:
            transaction, definition, bundle = master.prepare_construction_master_v28()
        try:
            manifest = master.validate_construction_master_v12(
                bundle, definition_path=definition, reproduce=True
            )
            coverage = json.loads((bundle / "coverage.json").read_text())
            self.assertEqual(manifest["row_counts"]["total"], 109328)
            self.assertEqual(
                manifest["row_counts"]["by_tier"],
                {"A": 536, "B": 6298, "C": 102494},
            )
            self.assertEqual(
                coverage["role_counts"],
                {
                    "rows_with_any_role": 145,
                    "rows_with_contract_marker": 416,
                    "rows_with_source_role_tags": 106,
                    "with_core_role": {
                        "customers": 2,
                        "operator": 59,
                        "owner": 48,
                        "tenants": 7,
                        "users": 36,
                    },
                },
            )
            if master.GENERATED_AT == master.PREPARATION_GENERATED_AT:
                self.assertEqual(checkpoint(definition), PREPARATION_DEFINITION_PIN)
                self.assertEqual(
                    checkpoint(bundle / "manifest.json"), PREPARATION_MANIFEST_PIN
                )
                self.assertEqual(tree_digest(bundle), PREPARATION_TREE_PIN)
            if published:
                self.assertEqual(checkpoint(definition), FINAL_DEFINITION_PIN)
                self.assertEqual(checkpoint(bundle / "manifest.json"), FINAL_MANIFEST_PIN)
                self.assertEqual(tree_digest(bundle), FINAL_TREE_PIN)
                self.assertEqual(
                    {path.name: checkpoint(path) for path in bundle.iterdir()},
                    FINAL_ARTIFACTS,
                )
                target = master._v28_generated_epoch()
                for path in (definition, bundle, *bundle.iterdir()):
                    metadata = path.stat()
                    birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
                    self.assertLessEqual(birth, target + 0.000_001)
                    self.assertLessEqual(metadata.st_mtime, target + 0.000_001)
                self.assertGreaterEqual(definition.stat().st_ctime, target)
                self.assertGreaterEqual(bundle.stat().st_ctime, target)
            self.assertEqual(stat.S_IMODE(definition.stat().st_mode), 0o444)
            self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o444
                    for path in bundle.iterdir()
                )
            )
            for token in (
                b"federation-2026-07-21-public-open-v31",
                b"exact-identity-decisions-2026-07-21-public-open-v8",
                b"construction-timeline-2026-07-21-public-open-v5",
            ):
                self.assertNotIn(token, (bundle / "manifest.json").read_bytes())
                self.assertNotIn(token, (bundle / "coverage.json").read_bytes())
        finally:
            if transaction is not None:
                master.discard_construction_master_v28_stage(transaction)
        self.assertEqual(master.DEFINITION_PATH.exists(), published)
        self.assertEqual(master.BUNDLE_PATH.exists(), published)

    def test_preparation_timestamp_and_no_replace_fail_closed(self) -> None:
        if master.DEFINITION_PATH.exists() or master.BUNDLE_PATH.exists():
            frozen_definition = master.DEFINITION_PATH.read_bytes()
            frozen_manifest = (master.BUNDLE_PATH / "manifest.json").read_bytes()
            with self.assertRaisesRegex(
                master.ConstructionMasterV12Error,
                "refusing existing v28 definition",
            ):
                master.publish_construction_master_v28()
            self.assertEqual(master.DEFINITION_PATH.read_bytes(), frozen_definition)
            self.assertEqual(
                (master.BUNDLE_PATH / "manifest.json").read_bytes(),
                frozen_manifest,
            )
        elif master.GENERATED_AT == master.PREPARATION_GENERATED_AT:
            with self.assertRaisesRegex(
                master.ConstructionMasterV12Error,
                "preparation-only",
            ):
                master.publish_construction_master_v28()
            self.assertFalse(master.DEFINITION_PATH.exists())
            self.assertFalse(master.BUNDLE_PATH.exists())

        with tempfile.TemporaryDirectory(
            prefix="master-v28-no-replace-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.write_bytes(b"new\n")
            destination.write_bytes(b"accepted\n")
            with self.assertRaisesRegex(SystemExit, "late output collision"):
                master._v28_promote_noreplace(stage, destination)
            self.assertEqual(stage.read_bytes(), b"new\n")
            self.assertEqual(destination.read_bytes(), b"accepted\n")

    def test_workspace_shim_exports_hardened_v28(self) -> None:
        self.assertIs(
            shim.publish_construction_master_v28,
            master.publish_construction_master_v28,
        )
        self.assertIs(
            shim.validate_construction_master_v12,
            master.validate_construction_master_v12,
        )
        for path, expected in CODE_PINS.items():
            self.assertEqual(checkpoint(path), expected)


if __name__ == "__main__":
    unittest.main()
