from __future__ import annotations

from contextlib import ExitStack
import copy
import csv
import hashlib
from itertools import islice, zip_longest
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_master_v8 as master_v8
from datacenter_atlas.construction_master_v8 import (
    ConstructionMasterV8Error,
    validate_construction_master_v8,
    validate_definition,
    write_construction_master_v8,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v24.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v24"
V23_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v23.json"
V23_MASTER = ROOT / "construction_master/2026-07-20-public-open-v23"
V55_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v55.json"
V55_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"
V56_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
V56_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"

GENERATED_AT = "2026-07-20T23:05:00Z"
PAIX_ID = "be826096-5b00-5454-a880-cb133fd9bdd5"
PENTAPOINT_ID = "a75eaf2b-790f-5266-be60-3f2bafee2eeb"
ADDED_IDS = {PAIX_ID, PENTAPOINT_ID}
FORBIDDEN = (
    "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json",
    "curated:google-bermuda-hundred-chesterfield-campus",
    "curated-official-2026-07-20-aligned-iad06-frederick-topout.json",
    "curated:aligned-quantum-frederick-campus:iad06",
)

FILE_PINS = {
    DEFINITION: (
        5_657,
        "5472a417b58547027e039df6b72bd8d4ee84bcfb186424781422f04e1c9736c0",
    ),
    V23_DEFINITION: (
        5_657,
        "6a72a8c44808ad6d276fed6141b15ee91e5708b5ff95f91aaf0c011e0c69d438",
    ),
    V55_DEFINITION: (
        67_472,
        "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba",
    ),
    V55_RELEASE / "manifest.json": (
        9_210,
        "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
    ),
    V56_DEFINITION: (
        67_918,
        "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c",
    ),
    V56_RELEASE / "manifest.json": (
        9_274,
        "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd",
    ),
    V56_RELEASE / "construction_pipeline.csv": (
        458_341,
        "42f07a6694edd50d3022ae4871dd6eb8ff0d783eb47f08f62c45709fdf62047d",
    ),
    V56_RELEASE / "evidence.csv": (
        149_384,
        "a99b5c0060b164f7215efb0220ef33b2d01402d4d43732d15c737f89f88d89f2",
    ),
    ROOT / "datacenter_atlas/construction_master_v7.py": (
        3_509,
        "80fb676a3f30b92a105a656b206b837360705a3ad2534a663bc53a5488e42f02",
    ),
    ROOT / "datacenter_atlas/construction_master_v8.py": (
        2_664,
        "c5e6d1573ca8af855a35f57e57e1579f6588370458a3cac5cddf1fde92157946",
    ),
    ROOT / "construction_master_v8.py": (
        239,
        "bf54d7eaf790d4b7f92cb2b8c3f7bc382df91d95f76d873761996647f2e801c8",
    ),
    ROOT / "scripts/build_construction_master_v8.py": (
        1_864,
        "81b01c4b3b56e5cc821380030273033cbfe941877250931c1b1adc50f7332a35",
    ),
}

OUTPUTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "6fbefa1323e92a2473fdd66822700282307ace12548c29d66971240c06d1b849",
    ),
    "README.md": (
        1_349,
        "76fd0fb00d895421e0978612e99de3dd90b5a41e47742920b533a5ddcaaa6d29",
    ),
    "construction-master.csv": (
        189_750_856,
        "a62cabf03f0e7f4a9bdd018208c2e577b2930134c1d48ac2098de5b319b47e55",
    ),
    "construction-master.jsonl": (
        325_543_337,
        "1ce3219e30b9c1ddbdd54167d879244f46a04f025f283214ba85976ccfbfe94c",
    ),
    "coverage.json": (
        8_548,
        "d3343af6363a491d8f2f7059ce90778e0e304b1e180aca3c44dd8192950f8811",
    ),
    "manifest.json": (
        9_719,
        "61f8c11ce3c782d63d02539b58ebfc2dd4f3e1c9f0957fe5ccda2bc5a5216705",
    ),
    "manifest.sha256": (
        80,
        "3dc464dfb48236936ef84d4adfe22c54382be15d20aa59868766e9ff047b2317",
    ),
}

TREE_SHA256 = "ee8d3994db5576363ae8bf3c58a990769702781e26d29f97f6775dda8bf95e40"
V23_TREE_SHA256 = "37100ba7e612e81b7aecc8516224a75d67f70af41ac3b9991b18912238a0f077"
V55_TREE_SHA256 = "44610a81fab0375255da9824975746ce301591a2b94e099f43f551eb7eb157b4"
V56_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"

EXPECTED_COUNTS = {
    "added_replacement_rows": 149,
    "base_replaced_rows": 199,
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "replacement_rows": 348,
    "replacement_rows_with_any_role": 126,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 49,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 87,
    "replacement_rows_with_tenants": 6,
    "replacement_rows_with_users": 36,
    "rows_with_contract_marker": 348,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_rows": 468,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_260,
    "unchanged_replacement_rows": 199,
}

EXPECTED_DIGESTS = {
    "added_source_record_ids_sha256": (
        "fc45e2c62bc8d822dde30efec39110a065b5947a2e84cfec78d24fa76e3b68b7"
    ),
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "5529de11285f90acb466f2822c790914f1f84c8cfe7bd15c89d81b4498266c2c"
    ),
    "replacement_rows_without_roles_sha256": (
        "9b9651056771c33977ce67f97af6d9cdd90e450b8662cd4dd433fc519f0c7666"
    ),
    "replacement_source_record_ids_sha256": (
        "8e86ad197b924ff83bd3032eb9e31485559d8ffd82a22a864b9daf16de0e2802"
    ),
    "tier_a_arithmetic_projection_sha256": (
        "1596008bd8aeb270d645ed2e08f48d720e212e9e7b843421b83f7aa2433db5ae"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"bundle contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw_hash = sha256(path)
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{path.stat().st_size}\0{raw_hash}\n".encode()
            )
        else:
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"]: row for row in csv.DictReader(source)}


class FrozenConstructionMasterV24Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v24 construction master attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_frozen_modes_and_tree_digests(self) -> None:
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(set(OUTPUTS), master_v8.BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(MASTER.stat().st_mode), 0o555)
        self.assertEqual(set(path.name for path in MASTER.iterdir()), set(OUTPUTS))
        for name, expected in OUTPUTS.items():
            path = MASTER / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(checkpoint(path), expected)
        self.assertEqual(tree_digest(MASTER), TREE_SHA256)
        self.assertEqual(tree_digest(V23_MASTER), V23_TREE_SHA256)
        self.assertEqual(tree_digest(V55_RELEASE), V55_TREE_SHA256)
        self.assertEqual(tree_digest(V56_RELEASE), V56_TREE_SHA256)

    def test_definition_is_exact_v23_successor_with_live_v56_invariants(self) -> None:
        old = json.loads(V23_DEFINITION.read_text())
        new = json.loads(DEFINITION.read_text())
        self.assertEqual(new, json.loads(canonical_json(new)))
        self.assertEqual(old["inputs"]["base_master"], new["inputs"]["base_master"])
        self.assertEqual(
            old["inputs"]["satellite_recovery_acceptance"],
            new["inputs"]["satellite_recovery_acceptance"],
        )
        self.assertEqual(old["scope"], new["scope"])
        replacement = new["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v56")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v56")
        self.assertEqual(replacement["publication_contract_version"], 4)
        self.assertEqual(
            replacement["manifest"]["sha256"],
            FILE_PINS[V56_RELEASE / "manifest.json"][1],
        )
        self.assertEqual(
            {key: new["expected"][key] for key in EXPECTED_COUNTS},
            EXPECTED_COUNTS,
        )
        self.assertEqual(
            {key: new["expected"][key] for key in EXPECTED_DIGESTS},
            EXPECTED_DIGESTS,
        )
        self.assertEqual(new["master_id"], "2026-07-20-public-open-v24")
        self.assertEqual(new["generated_at"], GENERATED_AT)
        v56 = json.loads(V56_DEFINITION.read_text())
        self.assertLess(v56["build"]["recorded_at"], GENERATED_AT)

        carrier = (ROOT / "datacenter_atlas/construction_master_v8.py").read_text()
        self.assertIn('with_name("construction_master_v7.py")', carrier)
        serialized = DEFINITION.read_text() + carrier
        for marker in (
            "federated_indexes/",
            "coverage-audit-",
            "current-coverage-",
            "construction-map-",
            "exact_identity_decisions/",
        ):
            self.assertNotIn(marker, serialized)

    def test_v56_adds_only_paix_and_pentapoint_and_inherited_rows_are_exact(
        self,
    ) -> None:
        old_rows = csv_rows(V55_RELEASE / "construction_pipeline.csv")
        new_rows = csv_rows(V56_RELEASE / "construction_pipeline.csv")
        self.assertEqual(len(old_rows), 346)
        self.assertEqual(len(new_rows), 348)
        self.assertFalse(set(old_rows) - set(new_rows))
        self.assertEqual(set(new_rows) - set(old_rows), ADDED_IDS)
        for entity_id in old_rows:
            self.assertEqual(old_rows[entity_id], new_rows[entity_id])

        paix = new_rows[PAIX_ID]
        pentapoint = new_rows[PENTAPOINT_ID]
        self.assertEqual(
            (paix["name"], paix["status"], paix["country"]),
            ("PAIX DKR-1 Dakar Data Center Development", "site_control", "Senegal"),
        )
        self.assertEqual(
            (pentapoint["name"], pentapoint["status"], pentapoint["country"]),
            (
                "PentaPoint EMD BKK-01 Development",
                "under_construction",
                "Thailand",
            ),
        )
        self.assertEqual(pentapoint["operator"], "AIMS Data Center")
        self.assertEqual(
            json.loads(paix["tags_json"])["role:developer"], "PAIX Data Centres"
        )
        pentapoint_tags = json.loads(pentapoint["tags_json"])
        self.assertEqual(pentapoint_tags["country"], "Thailand")
        self.assertEqual(pentapoint_tags["role:developer"], "PentaPoint Corporation")
        self.assertEqual(pentapoint_tags["role:operator"], "AIMS Data Center")
        self.assertEqual(pentapoint_tags["source_dataset"], "curated_official_sources")

        source_text = V56_DEFINITION.read_text() + DEFINITION.read_text()
        for marker in FORBIDDEN:
            self.assertNotIn(marker, source_text)

        with (MASTER / "construction-master.jsonl").open("rb") as source:
            replacement = [json.loads(raw) for raw in islice(source, 348)]
        self.assertEqual(
            {row["source"]["record_id"] for row in replacement}, set(new_rows)
        )
        by_record = {row["source"]["record_id"]: row for row in replacement}
        self.assertEqual(
            by_record[PAIX_ID]["lifecycle"]["normalized_status"], "site_control"
        )
        self.assertEqual(
            by_record[PENTAPOINT_ID]["lifecycle"]["normalized_status"],
            "under_construction",
        )
        self.assertTrue(
            by_record[PENTAPOINT_ID]["disposition"]["construction_arithmetic_included"]
        )
        self.assertEqual(
            by_record[PENTAPOINT_ID]["roles"]["operator"], "AIMS Data Center"
        )

        with (
            (V23_MASTER / "construction-master.jsonl").open("rb") as old,
            (MASTER / "construction-master.jsonl").open("rb") as new,
        ):
            for _ in range(346):
                next(old)
            for _ in range(348):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

    def test_counts_roles_status_scope_and_satellite_boundaries(self) -> None:
        definition, _raw, _root, _resolved, context = validate_definition(DEFINITION)
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])
        self.assertEqual(
            definition["expected"], {**EXPECTED_COUNTS, **EXPECTED_DIGESTS}
        )

        coverage = json.loads((MASTER / "coverage.json").read_text())
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 149,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v56",
                "replacement_rows": 348,
                "unchanged_source_record_ids": 199,
            },
        )
        self.assertEqual(
            coverage["role_counts"],
            {
                "rows_with_any_role": 126,
                "rows_with_contract_marker": 348,
                "rows_with_source_role_tags": 87,
                "with_core_role": {
                    "customers": 2,
                    "operator": 49,
                    "owner": 47,
                    "tenants": 6,
                    "users": 36,
                },
            },
        )
        self.assertEqual(
            coverage["row_counts"]["by_tier"], {"A": 468, "B": 6298, "C": 102494}
        )
        self.assertEqual(coverage["row_counts"]["total"], 109_260)
        self.assertEqual(
            coverage["row_counts"]["by_normalized_status"]["site_control"], 1
        )
        self.assertEqual(
            coverage["row_counts"]["by_normalized_status"]["under_construction"],
            349,
        )
        self.assertIsNone(coverage["row_counts"]["unique_physical_site_count"])
        self.assertEqual(
            coverage["satellite_recovery_acceptance"],
            json.loads((V23_MASTER / "coverage.json").read_text())[
                "satellite_recovery_acceptance"
            ],
        )
        for key in (
            "automatic_entity_merges",
            "candidate_or_review_rows_promoted",
            "cross_source_resolution_accepted",
            "fuzzy_review_rows_in_construction_arithmetic",
            "structural_or_cv_rows_in_construction_arithmetic",
        ):
            self.assertFalse(coverage["scope"][key])
        self.assertTrue(
            coverage["scope"]["historical_status_is_not_current_status_claim"]
        )
        self.assertTrue(coverage["scope"]["construction_arithmetic_limited_to_tier_a"])
        self.assertTrue(coverage["scope"]["satellite_recovery_control_plane_only"])

    def test_double_offline_reproduction_is_byte_exact(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="construction-v24-reproduce-", dir="/private/tmp"
            ) as temporary,
            ExitStack() as stack,
        ):
            self._offline(stack)
            root = Path(temporary)
            for name in ("first", "second"):
                rebuilt = root / name
                write_construction_master_v8(DEFINITION, rebuilt, freeze=True)
                self.assertEqual(tree_digest(rebuilt), TREE_SHA256)
                for filename, expected in OUTPUTS.items():
                    self.assertEqual(checkpoint(rebuilt / filename), expected)
            validate_construction_master_v8(
                MASTER, definition_path=DEFINITION, reproduce=False
            )
        for filename, expected in OUTPUTS.items():
            self.assertEqual(checkpoint(MASTER / filename), expected)

    def test_existing_lock_late_collision_and_fault_cleanup_fail_closed(self) -> None:
        with self.assertRaisesRegex(ConstructionMasterV8Error, "existing output"):
            write_construction_master_v8(DEFINITION, MASTER)
        with tempfile.TemporaryDirectory(
            prefix="construction-v24-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("held\n")
            with self.assertRaisesRegex(
                ConstructionMasterV8Error, "active output lock"
            ):
                write_construction_master_v8(DEFINITION, locked)
            self.assertEqual(lock.read_text(), "held\n")
            self.assertFalse(locked.exists())

            late = root / "late"

            def late_build(_definition: Path, _stage: Path) -> dict:
                late.mkdir()
                return {}

            with (
                patch.object(master_v8, "_build_into", side_effect=late_build),
                patch.object(master_v8, "_validate_static", return_value={}),
            ):
                with self.assertRaisesRegex(
                    ConstructionMasterV8Error, "late output collision"
                ):
                    write_construction_master_v8(DEFINITION, late, freeze=True)
            self.assertTrue(late.is_dir())
            self.assertFalse((root / ".late.lock").exists())
            self.assertFalse(
                any(".late.stage-" in path.name for path in root.iterdir())
            )

            fault = root / "fault"
            with patch.object(
                master_v8, "_build_into", side_effect=RuntimeError("boom")
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    write_construction_master_v8(DEFINITION, fault)
            self.assertFalse(fault.exists())
            self.assertFalse((root / ".fault.lock").exists())
            self.assertFalse(
                any(".fault.stage-" in path.name for path in root.iterdir())
            )

    def test_semantic_mutations_are_rejected(self) -> None:
        document = json.loads(DEFINITION.read_text())
        with tempfile.TemporaryDirectory(
            prefix="construction-v24-mutations-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            cases = []
            changed = copy.deepcopy(document)
            changed["inputs"]["replacement_release"]["artifact_id"] = (
                "epoch-official-open-seed-v55"
            )
            cases.append((changed, "base or replacement lane changed"))
            changed = copy.deepcopy(document)
            changed["scope"]["unique_physical_site_count"] = 348
            cases.append((changed, "identity or scope changed"))
            changed = copy.deepcopy(document)
            changed["expected"]["replacement_rows_with_any_role"] = 125
            cases.append((changed, "fixed count contract changed"))
            for index, (changed, message) in enumerate(cases):
                path = root / f"case-{index}.json"
                path.write_bytes(canonical_json(changed))
                with self.assertRaisesRegex(ConstructionMasterV8Error, message):
                    validate_definition(path)

        _definition, _raw, _root, resolved, _context = validate_definition(DEFINITION)
        changed_recovery = copy.deepcopy(
            document["inputs"]["satellite_recovery_acceptance"]
        )
        changed_recovery["artifact_id"] = "promoted-satellite-payload"
        with self.assertRaisesRegex(
            ConstructionMasterV8Error, "Unknown033 control-plane definition changed"
        ):
            master_v8._validate_recovery_control_plane(changed_recovery, resolved)

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.construction_master_v8"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.construction_master_v8"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_construction_master_v8; "
                f"result=validate_construction_master_v8(Path({str(MASTER)!r}), "
                f"definition_path=Path({str(DEFINITION)!r}), reproduce=False); "
                "assert result['row_counts']['total']==109260; "
                "assert result['row_counts']['by_tier']=={'A':468,'B':6298,'C':102494}; "
                "assert result['row_counts']['unique_physical_site_count'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
