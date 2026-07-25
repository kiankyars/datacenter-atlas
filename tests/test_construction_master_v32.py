from __future__ import annotations

import hashlib
import json
import shutil
import stat
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from datacenter_atlas import construction_master_v32 as shim
    from datacenter_atlas.datacenter_atlas import construction_master_v32 as master
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    import construction_master_v32 as shim
    from datacenter_atlas import construction_master_v32 as master
    from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
TRANSACTION = ROOT / ".construction-master-v32.transaction-wghbbjy8"
PRIVATE_DEFINITION = TRANSACTION / "construction-master-2026-07-22-public-open-v32.json"
PRIVATE_BUNDLE = TRANSACTION / "bundle"
PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v31.json"
)
PREDECESSOR_JSONL = (
    ROOT / "construction_master/2026-07-21-public-open-v31/construction-master.jsonl"
)

DEFINITION_PIN = (
    5_661,
    "47d3752d5b78601e786d6fb942d2b9f2f6a689433b45754cc5c9cda20d0f0241",
)
BUNDLE_TREE_PIN = "f4cdd4352d48c87a9fb269214cf47482b61459f68d0a941b9916b5b09837947f"
BUNDLE_PINS = {
    "ATTRIBUTION.txt": (
        5_814,
        "90035aa24b2b68cc54bdc54741cfd36c446975ae517094b8c33256812386b78a",
    ),
    "README.md": (
        1_349,
        "97b9208e80c84cfb20cee9ca53a5ad314b1d3267a28ac976756d24cf67d676bd",
    ),
    "construction-master.csv": (
        190_114_922,
        "50b192c91d3f31c0e281b4a806c735aa654fbc5639e78698c2ebeb1efb8b223f",
    ),
    "construction-master.jsonl": (
        326_143_453,
        "60388e1a111a880ab04ab4ec6aa95bd3cf2a04eaa77b16a1bcd0b85533a32eae",
    ),
    "coverage.json": (
        8_552,
        "a8eb504d91f762bc0a2cfc02fc336cc2cd6559960286c17f0ac2b5e7f7405074",
    ),
    "manifest.json": (
        9_721,
        "2282a8200d4bf9ed260123ec55b6f54676384728c091cbea1065f3708a644cdc",
    ),
    "manifest.sha256": (
        80,
        "be42324b6cb3ad7e1fb0f02ea40170a44190d54f89c776b21b5ebe4e3ee5f6c4",
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


class ConstructionMasterV32Tests(unittest.TestCase):
    def test_definition_is_exact_v31_to_v97_successor(self) -> None:
        current = master.construction_master_v32_definition()
        with patch.object(
            master, "_identity_final_state", return_value=(False, False, False)
        ):
            prospective = master.construction_master_v32_definition(
                allow_prospective_identity=True
            )
            with self.assertRaisesRegex(
                master.ConstructionMasterV32Error,
                "accepted identity v14 final is absent",
            ):
                master.construction_master_v32_definition()
        self.assertEqual(prospective, current)
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_bytes())
        expected = deepcopy(predecessor)
        expected["expected"] = {
            **master.EXPECTED_FIXED,
            **master.EXPECTED_DIGESTS,
        }
        expected["generated_at"] = master.GENERATED_AT
        expected["inputs"]["replacement_release"] = deepcopy(master.REPLACEMENT_INPUTS)
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

    def test_private_candidate_exact_pins_counts_and_freeze(self) -> None:
        manifest = master.validate_construction_master_v32(
            PRIVATE_BUNDLE,
            definition_path=PRIVATE_DEFINITION,
            reproduce=False,
            allow_prospective_identity=False,
        )
        self.assertEqual(checkpoint(PRIVATE_DEFINITION), DEFINITION_PIN)
        self.assertEqual(
            {path.name: checkpoint(path) for path in PRIVATE_BUNDLE.iterdir()},
            BUNDLE_PINS,
        )
        self.assertEqual(tree_digest(PRIVATE_BUNDLE), BUNDLE_TREE_PIN)
        self.assertEqual(manifest["row_counts"]["total"], 109_443)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 651, "B": 6_298, "C": 102_494},
        )
        coverage = json.loads((PRIVATE_BUNDLE / "coverage.json").read_bytes())
        self.assertEqual(
            coverage["role_counts"]["rows_with_any_role"],
            205,
        )
        self.assertEqual(stat.S_IMODE(PRIVATE_DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(PRIVATE_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PRIVATE_BUNDLE.iterdir()
            )
        )
        self.assertFalse(master.DEFINITION_PATH.exists())
        self.assertFalse(master.BUNDLE_PATH.exists())

    def test_exact_62_row_replacement_delta_and_unchanged_inherited_bytes(
        self,
    ) -> None:
        old_ids = replacement_ids(PREDECESSOR_JSONL, 469)
        new_jsonl = PRIVATE_BUNDLE / "construction-master.jsonl"
        new_ids = replacement_ids(new_jsonl, 531)
        self.assertFalse(old_ids - new_ids)
        self.assertEqual(len(new_ids - old_ids), 62)
        with PREDECESSOR_JSONL.open("rb") as old, new_jsonl.open("rb") as new:
            for _ in range(469):
                self.assertTrue(old.readline())
            for _ in range(531):
                self.assertTrue(new.readline())
            while chunk := old.read(1024 * 1024):
                self.assertEqual(new.read(len(chunk)), chunk)
            self.assertEqual(new.read(1), b"")

    def test_shim_and_publication_surfaces_remain_unpublished(self) -> None:
        self.assertIs(
            shim.publish_construction_master_v32,
            master.publish_construction_master_v32,
        )
        self.assertIs(
            shim.validate_construction_master_v32,
            master.validate_construction_master_v32,
        )
        self.assertFalse(master.PUBLICATION_LOCK.exists())
        self.assertFalse(master.DEFINITION_PATH.exists())
        self.assertFalse(master.BUNDLE_PATH.exists())
        with self.assertRaisesRegex(
            master.ConstructionMasterV32Error,
            "requires authorization",
        ):
            master.publish_construction_master_v32()
        with self.assertRaisesRegex(
            master.ConstructionMasterV32Error,
            "private to validated reproduction",
        ):
            master.write_construction_master_v32(
                PRIVATE_DEFINITION,
                master.BUNDLE_PATH,
                freeze=True,
            )
        with TemporaryDirectory(prefix="master-v32-writer-alias-") as temporary:
            alias = Path(temporary) / "alias"
            alias.symlink_to(master.BUNDLE_PATH.parent, target_is_directory=True)
            with self.assertRaisesRegex(
                master.ConstructionMasterV32Error,
                "private to validated reproduction",
            ):
                master.write_construction_master_v32(
                    PRIVATE_DEFINITION,
                    alias / master.BUNDLE_PATH.name,
                    freeze=True,
                )

    def test_final_validation_failure_rolls_back_both_owned_finals(self) -> None:
        with TemporaryDirectory(prefix="construction-master-v32-publish-") as temporary:
            root = Path(temporary)
            sources = root / "sources"
            masters = root / "construction_master"
            sources.mkdir()
            masters.mkdir()
            definition_final = sources / "master.json"
            bundle_final = masters / "master"
            lock = root / ".master.lock"
            target = (datetime.now(UTC) + timedelta(seconds=2)).replace(
                microsecond=0
            )
            generated_at = target.isoformat().replace("+00:00", "Z")

            def prepare(
                *,
                allow_prospective_identity: bool,
            ) -> tuple[Path, Path, Path]:
                self.assertFalse(allow_prospective_identity)
                transaction = root / ".master.transaction"
                bundle = transaction / "bundle"
                nested = bundle / "nested"
                nested.mkdir(parents=True)
                definition = transaction / definition_final.name
                definition.write_bytes(b"definition\n")
                (nested / "payload.json").write_bytes(b'{"ok":true}\n')
                definition.chmod(0o444)
                (nested / "payload.json").chmod(0o444)
                nested.chmod(0o555)
                bundle.chmod(0o555)
                return transaction, definition, bundle

            validations = [{}, master.ConstructionMasterV32Error("final validation")]
            with (
                patch.multiple(
                    master,
                    DEFINITION_PATH=definition_final,
                    BUNDLE_PATH=bundle_final,
                    PUBLICATION_LOCK=lock,
                    GENERATED_AT=generated_at,
                ),
                patch.object(
                    master,
                    "prepare_construction_master_v32",
                    side_effect=prepare,
                ),
                patch.object(master, "_v32_tree_digest", return_value="tree"),
                patch.object(
                    master,
                    "validate_construction_master_v32",
                    side_effect=validations,
                ),
                self.assertRaisesRegex(
                    master.ConstructionMasterV32Error,
                    "final validation",
                ) as raised,
            ):
                master.publish_construction_master_v32(
                    publication_authorized=True
                )

            self.assertFalse(definition_final.exists())
            self.assertFalse(
                bundle_final.exists(),
                getattr(raised.exception, "__notes__", ()),
            )
            self.assertFalse(lock.exists())
            transaction = root / ".master.transaction"
            self.assertTrue((transaction / definition_final.name).is_file())
            self.assertTrue((transaction / "bundle").is_dir())
            (transaction / definition_final.name).chmod(0o600)
            bundle_stage = transaction / "bundle"
            bundle_stage.chmod(0o700)
            for path in bundle_stage.rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
            shutil.rmtree(transaction)

    def test_obstructed_or_rehomed_definition_never_leaves_marker_only(
        self,
    ) -> None:
        for scenario in ("occupied-stage", "parent-swap"):
            with (
                self.subTest(scenario=scenario),
                TemporaryDirectory(
                    prefix=f"construction-master-v32-{scenario}-"
                ) as temporary,
            ):
                root = Path(temporary)
                sources = root / "sources"
                masters = root / "construction_master"
                sources.mkdir()
                masters.mkdir()
                definition_final = sources / "master.json"
                bundle_final = masters / "master"
                lock = root / ".master.lock"
                transaction = root / ".master.transaction"
                target = (datetime.now(UTC) + timedelta(seconds=2)).replace(
                    microsecond=0
                )
                generated_at = target.isoformat().replace("+00:00", "Z")

                def prepare(
                    *,
                    allow_prospective_identity: bool,
                    _transaction: Path = transaction,
                    _definition_final: Path = definition_final,
                ) -> tuple[Path, Path, Path]:
                    self.assertFalse(allow_prospective_identity)
                    bundle = _transaction / "bundle"
                    nested = bundle / "nested"
                    nested.mkdir(parents=True)
                    definition = _transaction / _definition_final.name
                    definition.write_bytes(b"definition\n")
                    (nested / "payload.json").write_bytes(b'{"ok":true}\n')
                    definition.chmod(0o444)
                    (nested / "payload.json").chmod(0o444)
                    nested.chmod(0o555)
                    bundle.chmod(0o555)
                    return _transaction, definition, bundle

                moved_sources = root / "sources.moved"

                def completion(
                    _result: dict[str, object],
                    *,
                    _scenario: str = scenario,
                    _transaction: Path = transaction,
                    _definition_final: Path = definition_final,
                    _sources: Path = sources,
                    _moved_sources: Path = moved_sources,
                ) -> None:
                    if _scenario == "occupied-stage":
                        (_transaction / _definition_final.name).write_bytes(
                            b"occupied"
                        )
                        raise master.ConstructionMasterV32Error("callback failure")
                    _sources.rename(_moved_sources)
                    _sources.mkdir()

                expected_error = (
                    "callback failure" if scenario == "occupied-stage" else "swapped"
                )
                with (
                    patch.multiple(
                        master,
                        DEFINITION_PATH=definition_final,
                        BUNDLE_PATH=bundle_final,
                        PUBLICATION_LOCK=lock,
                        GENERATED_AT=generated_at,
                    ),
                    patch.object(
                        master,
                        "prepare_construction_master_v32",
                        side_effect=prepare,
                    ),
                    patch.object(master, "_v32_tree_digest", return_value="tree"),
                    patch.object(
                        master,
                        "validate_construction_master_v32",
                        return_value={},
                    ),
                    self.assertRaisesRegex(
                        master.ConstructionMasterV32Error,
                        expected_error,
                    ),
                ):
                    master.publish_construction_master_v32(
                        publication_authorized=True,
                        completion_callback=completion,
                    )

                self.assertTrue(bundle_final.is_dir())
                if scenario == "occupied-stage":
                    self.assertTrue(definition_final.is_file())
                else:
                    self.assertFalse(definition_final.exists())
                    self.assertTrue((moved_sources / definition_final.name).is_file())
                self.assertFalse(lock.exists())

                bundle_final.chmod(0o700)
                for path in bundle_final.rglob("*"):
                    path.chmod(0o700 if path.is_dir() else 0o600)
                shutil.rmtree(bundle_final)
                for definition in (
                    definition_final,
                    moved_sources / definition_final.name,
                    transaction / definition_final.name,
                ):
                    if definition.exists():
                        definition.chmod(0o600)
                        definition.unlink()
                if moved_sources.exists():
                    moved_sources.rmdir()
                if transaction.exists():
                    transaction.rmdir()


if __name__ == "__main__":
    unittest.main()
