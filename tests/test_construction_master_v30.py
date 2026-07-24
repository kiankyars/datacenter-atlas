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
    from datacenter_atlas.datacenter_atlas import construction_master_v30 as master
    from datacenter_atlas import construction_master_v30 as shim
except ModuleNotFoundError:
    from datacenter_atlas import construction_master_v30 as master
    import construction_master_v30 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v29.json"
)
PREDECESSOR_JSONL = (
    ROOT
    / "construction_master/2026-07-21-public-open-v29/construction-master.jsonl"
)

FINAL_DEFINITION_PIN = (
    5_659,
    "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63",
)
FINAL_MANIFEST_PIN = (
    9_720,
    "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f",
)
FINAL_TREE_PIN = "32d3370e3604434886d305c2a0b129458bfbe1c4e823760f0ccc3a16a3519e30"
FINAL_ARTIFACTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "e5aa519e14e4a3dccb2856e98c324832c1c2269599b2c31b645347e28be5bb0d",
    ),
    "README.md": (
        1_349,
        "e9e73220871c0ba6f1605065b511676ca7c85abb8446f60f91a9499ee09714df",
    ),
    "construction-master.csv": (
        189_986_074,
        "59c3af8b013878fb9f079e258a5b85e308a1086c8bce248f04f3ff7243737169",
    ),
    "construction-master.jsonl": (
        325_925_334,
        "15f8b61dec37d658f338e83193908c96343893ba6cfc5eabc547cdf71a5f37cb",
    ),
    "coverage.json": (
        8_550,
        "db046e49a5590fdbae810343d9efa9d4f34401a2c2bfdb513d8c552d8507a5aa",
    ),
    "manifest.json": FINAL_MANIFEST_PIN,
    "manifest.sha256": (
        80,
        "47021d2337360b72b4656f90b5d7b4dd4bcfeadc0fef8bcf9b9024ac8e60bf11",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_master_v30.py": (
        17_799,
        "70590b5b6c3b675207dd2caff64d4234c8289823fcef4441e32c88f0bd5f288f",
    ),
    ROOT / "construction_master_v30.py": (
        249,
        "2a60cf1c7ef22a044d3c24c50e041558a4daf65f53d0df7b3d96afce99f47c29",
    ),
    ROOT / "scripts/build_construction_master_v30.py": (
        3_756,
        "3082e3bdb2e089008e39d45aefcca00140a89ccb2e3a45807342f38674305f0c",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def replacement_ids(path: Path, count: int) -> set[str]:
    result: set[str] = set()
    with path.open("rb") as source:
        for _ in range(count):
            row = json.loads(source.readline())
            result.add(row["source"]["record_id"])
    return result


class ConstructionMasterV30Tests(unittest.TestCase):
    def test_definition_is_the_strict_v29_to_v83_successor(self) -> None:
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_text())
        current = master.construction_master_v30_definition()
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
            current["inputs"]["base_master"], predecessor["inputs"]["base_master"]
        )
        self.assertEqual(
            current["inputs"]["satellite_recovery_acceptance"],
            predecessor["inputs"]["satellite_recovery_acceptance"],
        )

    def test_dependency_gates_are_exact_temporally_prior_and_not_provenance(
        self,
    ) -> None:
        master.validate_dependency_closure_v30()
        self.assertEqual(
            set(master.ACCEPTED_DEPENDENCY_CLOSURE),
            {
                "federation_v34",
                "identity_v10",
                "open_seed_v83",
                "predecessor_master_v29",
                "timeline_v7",
            },
        )
        target = datetime.fromisoformat(
            master.GENERATED_AT.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        for lane, (field, expected) in master.ACCEPTED_DEPENDENCY_TIMESTAMPS.items():
            self.assertLess(
                datetime.fromisoformat(expected.replace("Z", "+00:00")), target, lane
            )
            self.assertTrue(field)
        raw = master.construction_master_v30_definition_bytes()
        for token in (
            b"2026-07-21-public-open-v34",
            b"2026-07-21-public-open-v10",
            b"2026-07-21-public-open-v7",
            b"2026-07-21-public-open-v33",
            b"2026-07-21-public-open-v9",
            b"2026-07-21-public-open-v6",
            b"2026-07-21-public-open-v29",
            b"2026-07-21-public-open-v32",
            b"2026-07-21-public-open-v4",
        ):
            self.assertNotIn(token, raw)
        self.assertIn(b"open-seed-2026-07-21-v83", raw)
        self.assertNotIn(b"open-seed-2026-07-21-v73", raw)

    def test_exact_v83_counts_roles_and_digests(self) -> None:
        self.assertEqual(
            master.EXPECTED_FIXED,
            {
                "added_replacement_rows": 263,
                "base_replaced_rows": 199,
                "base_rows": 109111,
                "inherited_rows": 108912,
                "replacement_rows": 462,
                "replacement_rows_with_any_role": 179,
                "replacement_rows_with_customers": 2,
                "replacement_rows_with_operator": 82,
                "replacement_rows_with_owner": 53,
                "replacement_rows_with_source_role_tags": 140,
                "replacement_rows_with_tenants": 7,
                "replacement_rows_with_users": 37,
                "rows_with_contract_marker": 462,
                "satellite_recovery_control_plane_bytes": 15313,
                "satellite_recovery_rows": 0,
                "tier_a_rows": 582,
                "tier_b_rows": 6298,
                "tier_c_rows": 102494,
                "total_rows": 109374,
                "unchanged_replacement_rows": 199,
            },
        )
        self.assertEqual(
            master.EXPECTED_DIGESTS,
            {
                "added_source_record_ids_sha256": (
                    "b91fc2d15d8124eb031e92b6328c9e562b89b20966ee65988dec35a4d6de14bc"
                ),
                "base_replaced_source_record_ids_sha256": (
                    "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
                ),
                "inherited_rows_without_roles_sha256": (
                    "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
                ),
                "replacement_role_projection_sha256": (
                    "3a8f2f7b1504516d9868436e031ad117d2f2dca8ab8c2eb856023ab8c65d9a79"
                ),
                "replacement_rows_without_roles_sha256": (
                    "2f2d00871fc49dedc914050775719453ba3d8f4f419ed79eb1eea168167526f2"
                ),
                "replacement_source_record_ids_sha256": (
                    "dd532fc205956cdc0695bef880b7410f0d66b503d27e864ac262401c6c279c4e"
                ),
                "tier_a_arithmetic_projection_sha256": (
                    "64ca9b92bf53a0b4eb6886b304b4685f8d791e6b6ac5afbf6d9ddda1cd58b815"
                ),
            },
        )

    def test_frozen_final_bundle_and_exact_v29_delta(self) -> None:
        if FINAL_DEFINITION_PIN is None:
            self.skipTest("v30 remains preparation-only")
        assert FINAL_MANIFEST_PIN is not None
        assert FINAL_TREE_PIN is not None
        assert FINAL_ARTIFACTS is not None
        manifest = master.validate_construction_master_v30(
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
        self.assertEqual(manifest["row_counts"]["total"], 109374)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 582, "B": 6298, "C": 102494},
        )
        self.assertEqual(coverage["row_counts"]["unique_physical_site_count"], None)
        self.assertEqual(coverage["satellite_recovery_acceptance"]["rows_created"], 0)
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 263,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v83",
                "replacement_rows": 462,
                "unchanged_source_record_ids": 199,
            },
        )
        old_ids = replacement_ids(PREDECESSOR_JSONL, 420)
        new_jsonl = master.BUNDLE_PATH / "construction-master.jsonl"
        new_ids = replacement_ids(new_jsonl, 462)
        self.assertEqual(len(new_ids - old_ids), 42)
        self.assertFalse(old_ids - new_ids)
        with PREDECESSOR_JSONL.open("rb") as old, new_jsonl.open("rb") as new:
            for _ in range(420):
                self.assertTrue(old.readline())
            for _ in range(462):
                self.assertTrue(new.readline())
            while chunk := old.read(1024 * 1024):
                self.assertEqual(new.read(len(chunk)), chunk)
            self.assertEqual(new.read(1), b"")
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

    def test_no_replace_workspace_shim_and_code_pins(self) -> None:
        if CODE_PINS is None:
            self.skipTest("v30 remains preparation-only")
        frozen_definition = master.DEFINITION_PATH.read_bytes()
        frozen_manifest = (master.BUNDLE_PATH / "manifest.json").read_bytes()
        with self.assertRaisesRegex(
            master.ConstructionMasterV30Error,
            "refusing existing v30 definition",
        ):
            master.publish_construction_master_v30()
        self.assertEqual(master.DEFINITION_PATH.read_bytes(), frozen_definition)
        self.assertEqual(
            (master.BUNDLE_PATH / "manifest.json").read_bytes(), frozen_manifest
        )
        with tempfile.TemporaryDirectory(
            prefix="master-v30-no-replace-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.write_bytes(b"new\n")
            destination.write_bytes(b"accepted\n")
            with self.assertRaisesRegex(SystemExit, "late output collision"):
                master._v30_promote_noreplace(stage, destination)
            self.assertEqual(stage.read_bytes(), b"new\n")
            self.assertEqual(destination.read_bytes(), b"accepted\n")
        self.assertIs(
            shim.publish_construction_master_v30,
            master.publish_construction_master_v30,
        )
        self.assertIs(
            shim.validate_construction_master_v30,
            master.validate_construction_master_v30,
        )
        for path, expected in CODE_PINS.items():
            self.assertEqual(checkpoint(path), expected)


if __name__ == "__main__":
    unittest.main()
