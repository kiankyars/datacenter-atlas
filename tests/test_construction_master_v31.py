from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_master_v31 as master
    from datacenter_atlas import construction_master_v31 as shim
except ModuleNotFoundError:
    from datacenter_atlas import construction_master_v31 as master
    import construction_master_v31 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v30.json"
)
PREDECESSOR_JSONL = (
    ROOT
    / "construction_master/2026-07-21-public-open-v30/construction-master.jsonl"
)

FINAL_DEFINITION_PIN = (
    5_660,
    "a1b4761820aa6adb3406d5ff3ad6bc52898309fed72fe4f857aca01197597c25",
)
FINAL_MANIFEST_PIN = (
    9_721,
    "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e",
)
FINAL_TREE_PIN = "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
FINAL_ARTIFACTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "cbaffb9dfd41a5fefdca8fd8cb392b0c00912b28615572eb25a9d12f30123b91",
    ),
    "README.md": (
        1_349,
        "ef3492c2a98163f88acdb98687749bea105919ed0b5699efeda1723da5658543",
    ),
    "construction-master.csv": (
        190_003_570,
        "3c05febb4bc9ed6bc4fa0876e42e1b685269d6763b4c0bbf1f9ecefea3921e5c",
    ),
    "construction-master.jsonl": (
        325_951_779,
        "71fe0a7f054ca2329aa5747cada25cfdc51b52ca02396437cf9e34851552b035",
    ),
    "coverage.json": (
        8_550,
        "2705b2772b3e64891a73b3c07a56d54e3f94cfa6ed16495ca02825253bb29c68",
    ),
    "manifest.json": FINAL_MANIFEST_PIN,
    "manifest.sha256": (
        80,
        "0dc241d6c09767c58902e1f7ff328db614b58b919e822451302a73b87ad9f75b",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_master_v31.py": (
        16_820,
        "70e160500940712b8406f40907c6bf3d4b0ae8ad5a947d79bc4f63835be5a523",
    ),
    ROOT / "construction_master_v31.py": (
        249,
        "613ad80ad3476ece996da3d9f4f20200c98d7a66cdd3770fb0c1f2f6faafc17d",
    ),
    ROOT / "scripts/build_construction_master_v31.py": (
        3_756,
        "3e412c4b659c545c876a472ca68cb600e4d4bac0fe9538637389190f681dfe2f",
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


class ConstructionMasterV31Tests(unittest.TestCase):
    def test_definition_is_the_strict_v30_to_v86_successor(self) -> None:
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_text())
        current = master.construction_master_v31_definition()
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

    def test_dependency_gates_are_exact_prior_conservative_and_not_provenance(
        self,
    ) -> None:
        master.validate_dependency_closure_v31()
        self.assertEqual(
            set(master.ACCEPTED_DEPENDENCY_CLOSURE),
            {
                "federation_v35",
                "identity_v11",
                "open_seed_v86",
                "predecessor_master_v30",
                "timeline_v8",
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

        closure = master.ACCEPTED_DEPENDENCY_CLOSURE
        seed = json.loads((ROOT / closure["open_seed_v86"]["manifest"]["path"]).read_text())
        self.assertIs(seed["current_status_inferred"], False)
        self.assertIs(seed["geometry_only_representative_point_inferred"], False)
        federation = json.loads(
            (ROOT / closure["federation_v35"]["manifest"]["path"]).read_text()
        )
        self.assertIs(federation["scope"]["cross_source_deduplication"], False)
        self.assertIsNone(federation["scope"]["unique_physical_site_count"])
        identity = json.loads(
            (ROOT / closure["identity_v11"]["manifest"]["path"]).read_text()
        )
        self.assertIs(identity["scope"]["automatic_physical_site_merges"], False)
        self.assertIsNone(identity["counts"]["unique_physical_sites"])
        timeline = json.loads(
            (ROOT / closure["timeline_v8"]["manifest"]["path"]).read_text()
        )
        self.assertEqual(timeline["scope"]["current_status_classification"], "unknown")
        self.assertIs(timeline["scope"]["current_construction_claimed"], False)
        self.assertIs(timeline["scope"]["satellite_cv_promoted_to_lifecycle"], False)

        raw = master.construction_master_v31_definition_bytes()
        for token in master._CHECKPOINT_ONLY_TOKENS:
            self.assertNotIn(token, raw)
        for token in master._REJECTED_TOKENS:
            self.assertNotIn(token, raw)
        self.assertIn(b"open-seed-2026-07-21-v86", raw)
        self.assertNotIn(b"open-seed-2026-07-21-v83", raw)

        tampered = deepcopy(master.ACCEPTED_DEPENDENCY_CLOSURE)
        tampered["federation_v35"]["tree"]["sha256"] = "0" * 64
        with patch.object(master, "ACCEPTED_DEPENDENCY_CLOSURE", tampered):
            with self.assertRaisesRegex(
                master.ConstructionMasterV31Error,
                "accepted dependency tree changed",
            ):
                master.validate_dependency_closure_v31()

    def test_exact_v86_counts_roles_and_digests(self) -> None:
        self.assertEqual(
            master.EXPECTED_FIXED,
            {
                "added_replacement_rows": 270,
                "base_replaced_rows": 199,
                "base_rows": 109111,
                "inherited_rows": 108912,
                "replacement_rows": 469,
                "replacement_rows_with_any_role": 186,
                "replacement_rows_with_customers": 2,
                "replacement_rows_with_operator": 89,
                "replacement_rows_with_owner": 53,
                "replacement_rows_with_source_role_tags": 147,
                "replacement_rows_with_tenants": 7,
                "replacement_rows_with_users": 37,
                "rows_with_contract_marker": 469,
                "satellite_recovery_control_plane_bytes": 15313,
                "satellite_recovery_rows": 0,
                "tier_a_rows": 589,
                "tier_b_rows": 6298,
                "tier_c_rows": 102494,
                "total_rows": 109381,
                "unchanged_replacement_rows": 199,
            },
        )
        self.assertEqual(
            master.EXPECTED_DIGESTS,
            {
                "added_source_record_ids_sha256": (
                    "8fa67daabafb928828126aed931795be2f05b6b42eb4b67ec8141b74afe1351b"
                ),
                "base_replaced_source_record_ids_sha256": (
                    "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
                ),
                "inherited_rows_without_roles_sha256": (
                    "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
                ),
                "replacement_role_projection_sha256": (
                    "5f03315283a507acbbc93b6f99784ffa2a5055186345c9202efc48f37bce6184"
                ),
                "replacement_rows_without_roles_sha256": (
                    "5bcc3b34d2399bb34357caeb634b86eb11b3c6c1d86b7cec780bb724abd88a5e"
                ),
                "replacement_source_record_ids_sha256": (
                    "8308c8d677e0e0c6c3496d2b49ca5b3cd8bb2880e184fc04f8fcec7f6f1362c6"
                ),
                "tier_a_arithmetic_projection_sha256": (
                    "f124e8a9ed3c4a0ffd8987d663b2bb2a4bb4b8655efec71f30638e94821cc987"
                ),
            },
        )

    def test_frozen_final_bundle_and_exact_v30_delta(self) -> None:
        manifest = master.validate_construction_master_v31(
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
        self.assertEqual(manifest["row_counts"]["total"], 109381)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 589, "B": 6298, "C": 102494},
        )
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertEqual(coverage["satellite_recovery_acceptance"]["rows_created"], 0)
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 270,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v86",
                "replacement_rows": 469,
                "unchanged_source_record_ids": 199,
            },
        )
        old_ids = replacement_ids(PREDECESSOR_JSONL, 462)
        new_jsonl = master.BUNDLE_PATH / "construction-master.jsonl"
        new_ids = replacement_ids(new_jsonl, 469)
        self.assertEqual(len(new_ids - old_ids), 7)
        self.assertFalse(old_ids - new_ids)
        with PREDECESSOR_JSONL.open("rb") as old, new_jsonl.open("rb") as new:
            for _ in range(462):
                self.assertTrue(old.readline())
            for _ in range(469):
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

    def test_no_replace_workspace_shim_code_pins_and_residue(self) -> None:
        frozen_definition = master.DEFINITION_PATH.read_bytes()
        frozen_manifest = (master.BUNDLE_PATH / "manifest.json").read_bytes()
        with self.assertRaisesRegex(
            master.ConstructionMasterV31Error,
            "refusing existing v31 definition",
        ):
            master.publish_construction_master_v31()
        self.assertEqual(master.DEFINITION_PATH.read_bytes(), frozen_definition)
        self.assertEqual(
            (master.BUNDLE_PATH / "manifest.json").read_bytes(), frozen_manifest
        )
        with tempfile.TemporaryDirectory(
            prefix="master-v31-no-replace-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.write_bytes(b"new\n")
            destination.write_bytes(b"accepted\n")
            with self.assertRaisesRegex(SystemExit, "late output collision"):
                master._v31_promote_noreplace(stage, destination)
            self.assertEqual(stage.read_bytes(), b"new\n")
            self.assertEqual(destination.read_bytes(), b"accepted\n")
        self.assertIs(
            shim.publish_construction_master_v31,
            master.publish_construction_master_v31,
        )
        self.assertIs(
            shim.validate_construction_master_v31,
            master.validate_construction_master_v31,
        )
        for path, expected in CODE_PINS.items():
            self.assertEqual(checkpoint(path), expected)
        self.assertFalse(master.PUBLICATION_LOCK.exists())
        self.assertFalse(
            list(ROOT.glob(".construction-master-v31.transaction-*"))
        )


if __name__ == "__main__":
    unittest.main()
