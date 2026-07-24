from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

try:
    from datacenter_atlas.datacenter_atlas import construction_master_v29 as master
    from datacenter_atlas import construction_master_v29 as shim
except ModuleNotFoundError:
    from datacenter_atlas import construction_master_v29 as master
    import construction_master_v29 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v28.json"
)
FINAL_DEFINITION_PIN = (
    5_659,
    "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d",
)
FINAL_MANIFEST_PIN = (
    9_720,
    "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c",
)
FINAL_TREE_PIN = "09a76700020e35b1daa95e00cbd6c6bdf90aede9d9f794f5a4c70a607541eff8"
FINAL_ARTIFACTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "4f01546a2475cc5888f1e216c1afe9b56864a8e3f8d16add12c7af851c64fa0a",
    ),
    "README.md": (
        1_349,
        "4e9e943ebab4a7f96c156df5cc028f945349d27065ff717ba8439d21024b3220",
    ),
    "construction-master.csv": (
        189_910_881,
        "daee27715d12dbfc96a7b68a2d84ac4dbe224c5c3477a62435a71074e3894a7b",
    ),
    "construction-master.jsonl": (
        325_795_989,
        "a36b6de29a74030ff664b3dcf8918c2ad137998fc3c3a9947b2dd6b79441492b",
    ),
    "coverage.json": (
        8_550,
        "0f39569a5f0b17e1e90d2430704eb83f2653e2294c47c0cacacd9ef7b0f2d54d",
    ),
    "manifest.json": FINAL_MANIFEST_PIN,
    "manifest.sha256": (
        80,
        "f797bd1e65040470308e1c2306fc0e45db1915ee262ae9660715a0b9ff2fcec6",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_master_v29.py": (
        16_361,
        "2c34537338a8f710275a3dd08979fc13c6e63178df794070790f29cf03a71f0a",
    ),
    ROOT / "construction_master_v29.py": (
        249,
        "2c5ffcc59c8e35a1048788ce9a287b5348a5a8cb9432eab0c333ff1d3ea40bc8",
    ),
    ROOT / "scripts/build_construction_master_v29.py": (
        3_756,
        "219ad5b8176fa785000ace46ffbea26b7230e534df4ec7acd2a02c963a795cef",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMasterV29Tests(unittest.TestCase):
    def test_definition_is_the_strict_v28_to_v73_successor(self) -> None:
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_text())
        current = master.construction_master_v29_definition()
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

    def test_accepted_gates_and_rejected_guards_are_not_provenance(self) -> None:
        master.validate_dependency_closure_v29()
        self.assertEqual(
            set(master.ACCEPTED_DEPENDENCY_CLOSURE),
            {
                "federation_v33",
                "identity_v9",
                "open_seed_v73",
                "predecessor_master_v28",
                "timeline_v6",
            },
        )
        raw = master.construction_master_v29_definition_bytes()
        for token in (
            b"2026-07-21-public-open-v33",
            b"2026-07-21-public-open-v9",
            b"2026-07-21-public-open-v6",
            b"2026-07-21-public-open-v32",
            b"2026-07-21-public-open-v4",
        ):
            self.assertNotIn(token, raw)
        self.assertIn(b"open-seed-2026-07-21-v73", raw)
        self.assertNotIn(b"open-seed-2026-07-21-v71", raw)

    def test_exact_v73_counts_roles_and_digests(self) -> None:
        self.assertEqual(
            master.EXPECTED_FIXED,
            {
                "added_replacement_rows": 221,
                "base_replaced_rows": 199,
                "base_rows": 109111,
                "inherited_rows": 108912,
                "replacement_rows": 420,
                "replacement_rows_with_any_role": 149,
                "replacement_rows_with_customers": 2,
                "replacement_rows_with_operator": 62,
                "replacement_rows_with_owner": 48,
                "replacement_rows_with_source_role_tags": 110,
                "replacement_rows_with_tenants": 7,
                "replacement_rows_with_users": 36,
                "rows_with_contract_marker": 420,
                "satellite_recovery_control_plane_bytes": 15313,
                "satellite_recovery_rows": 0,
                "tier_a_rows": 540,
                "tier_b_rows": 6298,
                "tier_c_rows": 102494,
                "total_rows": 109332,
                "unchanged_replacement_rows": 199,
            },
        )
        self.assertEqual(
            master.EXPECTED_DIGESTS,
            {
                "added_source_record_ids_sha256": (
                    "3480d43754e33f76500fdf09bff59a864c641be0d15f1dcfb75480a9c9efe619"
                ),
                "base_replaced_source_record_ids_sha256": (
                    "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
                ),
                "inherited_rows_without_roles_sha256": (
                    "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
                ),
                "replacement_role_projection_sha256": (
                    "a084c49e69538b5a1424fbcca5a916c70bea24fdaa660b4e715b53f04d398c8e"
                ),
                "replacement_rows_without_roles_sha256": (
                    "44c9d5ebd7f3427e4fc735a75c1f0089c204ecd888437f90a0ba9a048190ee12"
                ),
                "replacement_source_record_ids_sha256": (
                    "60011ff904e5a430b963d033cf2ddc17aa014af4fb9ac499db8cf33d95d862b1"
                ),
                "tier_a_arithmetic_projection_sha256": (
                    "223c78144ce86d035623a46547e7bcbe6f9b3e1ca36496bd07065efa0852be77"
                ),
            },
        )

    def test_frozen_final_bundle_and_publication_time(self) -> None:
        manifest = master.validate_construction_master_v29(
            master.BUNDLE_PATH,
            definition_path=master.DEFINITION_PATH,
            reproduce=False,
        )
        coverage = json.loads((master.BUNDLE_PATH / "coverage.json").read_text())
        self.assertEqual(checkpoint(master.DEFINITION_PATH), FINAL_DEFINITION_PIN)
        self.assertEqual(
            checkpoint(master.BUNDLE_PATH / "manifest.json"), FINAL_MANIFEST_PIN
        )
        self.assertEqual(tree_digest(master.BUNDLE_PATH), FINAL_TREE_PIN)
        self.assertEqual(
            {path.name: checkpoint(path) for path in master.BUNDLE_PATH.iterdir()},
            FINAL_ARTIFACTS,
        )
        self.assertEqual(manifest["row_counts"]["total"], 109332)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 540, "B": 6298, "C": 102494},
        )
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 221,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v73",
                "replacement_rows": 420,
                "unchanged_source_record_ids": 199,
            },
        )
        self.assertEqual(
            coverage["role_counts"],
            {
                "rows_with_any_role": 149,
                "rows_with_contract_marker": 420,
                "rows_with_source_role_tags": 110,
                "with_core_role": {
                    "customers": 2,
                    "operator": 62,
                    "owner": 48,
                    "tenants": 7,
                    "users": 36,
                },
            },
        )
        target = datetime.fromisoformat(
            master.GENERATED_AT.replace("Z", "+00:00")
        ).astimezone(timezone.utc).timestamp()
        paths = (
            master.DEFINITION_PATH,
            master.BUNDLE_PATH,
            *master.BUNDLE_PATH.iterdir(),
        )
        for path in paths:
            metadata = path.stat()
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            self.assertLessEqual(birth, target + 0.000_001)
            self.assertLessEqual(metadata.st_mtime, target + 0.000_001)
        self.assertGreaterEqual(master.DEFINITION_PATH.stat().st_ctime, target)
        self.assertGreaterEqual(master.BUNDLE_PATH.stat().st_ctime, target)
        self.assertEqual(stat.S_IMODE(master.DEFINITION_PATH.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(master.BUNDLE_PATH.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in master.BUNDLE_PATH.iterdir()
            )
        )

    def test_no_replace_and_workspace_shim(self) -> None:
        frozen_definition = master.DEFINITION_PATH.read_bytes()
        frozen_manifest = (master.BUNDLE_PATH / "manifest.json").read_bytes()
        with self.assertRaisesRegex(
            master.ConstructionMasterV29Error,
            "refusing existing v29 definition",
        ):
            master.publish_construction_master_v29()
        self.assertEqual(master.DEFINITION_PATH.read_bytes(), frozen_definition)
        self.assertEqual(
            (master.BUNDLE_PATH / "manifest.json").read_bytes(), frozen_manifest
        )
        with tempfile.TemporaryDirectory(
            prefix="master-v29-no-replace-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.write_bytes(b"new\n")
            destination.write_bytes(b"accepted\n")
            with self.assertRaisesRegex(SystemExit, "late output collision"):
                master._v29_promote_noreplace(stage, destination)
            self.assertEqual(stage.read_bytes(), b"new\n")
            self.assertEqual(destination.read_bytes(), b"accepted\n")
        self.assertIs(
            shim.publish_construction_master_v29,
            master.publish_construction_master_v29,
        )
        self.assertIs(
            shim.validate_construction_master_v29,
            master.validate_construction_master_v29,
        )
        for path, expected in CODE_PINS.items():
            self.assertEqual(checkpoint(path), expected)


if __name__ == "__main__":
    unittest.main()
