from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/rejected_open_seed_v47_lineage.md"
V44_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v44.json"
V46_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v46.json"
V47_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v47.json"
V47_RELEASE = ROOT / "releases/2026-07-20-open-seed-v47"
CURRENT_LEDGER_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v15.json"

REJECTED_PINS = {
    V47_DEFINITION: (
        59_727,
        "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2",
    ),
    V47_RELEASE / "manifest.json": (
        8_024,
        "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1",
    ),
    ROOT / "sources/federation-2026-07-20-public-open-v22.json": (
        1_788,
        "87f8cf1b662431bcd3436ff89eaa8398b26d6cf42adfb1fdb9273d7fd06c37f6",
    ),
    ROOT / "federated_indexes/2026-07-20-public-open-v22/federated-index.json": (
        22_981,
        "d2d7518a5febb0c57a2ceaac78ecb71fe045d1578efefcdf34829a7db5866c7c",
    ),
    ROOT / "federated_indexes/2026-07-20-public-open-v22/manifest.json": (
        986,
        "bf281de1170bb709ebc33148c45d0c1c30ea535073e3193754f53f0c4ffd4a94",
    ),
    ROOT / "sources/coverage-audit-2026-07-20-public-open-v21.json": (
        3_871,
        "f26fa3dda1ed3447941154635d252d68b6355f826a17a6a4c4efaa887257cd02",
    ),
    ROOT / "audits/2026-07-20-public-open-coverage-v21/manifest.json": (
        2_240,
        "b40981593dab96613f7a35dd5e4e07aeb7c4f7e4727f41802bec6b8af0f88393",
    ),
    ROOT / "sources/construction-master-2026-07-20-public-open-v21.json": (
        5_657,
        "ca6258e96d72407d8aa24b94e3ac52c7c1f4d6b0c52e722b0f6d36bd2c16843a",
    ),
    ROOT / "construction_master/2026-07-20-public-open-v21/manifest.json": (
        9_694,
        "9af4215174275908f69f2f04302992be940277350e03924a1dda7fb089bab4f9",
    ),
    ROOT / "sources/construction-map-2026-07-20-public-open-v21.json": (
        2_441,
        "72e99c9a1734375e02ed8a4e31a975cfaaa1c9518267466d514b39ba83df78b5",
    ),
    ROOT / "construction_maps/2026-07-20-public-open-v21/manifest.json": (
        2_192,
        "a2110233083bfef5271225e77a75d2132eedb9d848ee59671c20d26eabd26ba4",
    ),
    ROOT / "datacenter_atlas/construction_master_v5.py": (
        3_325,
        "1f52ccc0d1436c818f40f4b6ef170e4f225124ee20d905a3d7dda9fd5f4ad82b",
    ),
    ROOT / "datacenter_atlas/construction_map_v5.py": (
        2_259,
        "a64ddbcea72743e5f181a5c6ccc45d3812f47bdcce8d575267d54257bd99138f",
    ),
}

ACCEPTED_PINS = {
    V46_DEFINITION: "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293",
    ROOT / "releases/2026-07-20-open-seed-v46/manifest.json": (
        "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
    ),
    ROOT / "federated_indexes/2026-07-20-public-open-v21/manifest.json": (
        "24210f9484ac7f0143a76395782e739c49ce75a95059920a8dedd62c43b9b4cc"
    ),
    ROOT / "audits/2026-07-20-public-open-coverage-v20/manifest.json": (
        "c1c18389c91e3f37cbc8311206881746c15d7e10b5fee24ec7ce945784dbfc05"
    ),
    ROOT / "construction_master/2026-07-20-public-open-v20/manifest.json": (
        "b558cf776693602ae51141ec0ac6445decf84d671447fa3743513d3d0551efe7"
    ),
    ROOT / "construction_maps/2026-07-20-public-open-v20/manifest.json": (
        "6dcc9c02a37200f9fec5894aaa97f0ce30e330225567168b5455fb3d4310070c"
    ),
    ROOT / "current_coverage_ledgers/2026-07-20-v15/manifest.json": (
        "e43aec4405486b1c53870f6b1b6d116ed62885d18e4aed553fd47adcf8e19e47"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input_map(path: Path) -> dict[str, str]:
    document = json.loads(path.read_text())
    return {row["path"]: row["sha256"] for row in document["curated_inputs"]}


class RejectedOpenSeedV47LineageTests(unittest.TestCase):
    def test_rejected_and_accepted_artifacts_are_byte_pinned(self) -> None:
        for path, (expected_size, expected_hash) in REJECTED_PINS.items():
            self.assertEqual(path.stat().st_size, expected_size, path)
            self.assertEqual(_sha256(path), expected_hash, path)
        for path, expected_hash in ACCEPTED_PINS.items():
            self.assertEqual(_sha256(path), expected_hash, path)
        self.assertEqual(stat.S_IMODE(V47_DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(V47_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                not path.is_symlink()
                and path.is_file()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in V47_RELEASE.iterdir()
            )
        )

    def test_v47_is_an_exact_v44_fork_and_not_a_v46_successor(self) -> None:
        v44 = _input_map(V44_DEFINITION)
        v46 = _input_map(V46_DEFINITION)
        v47 = _input_map(V47_DEFINITION)
        self.assertEqual((len(v44), len(v46), len(v47)), (269, 287, 283))
        self.assertFalse(set(v44) - set(v47))
        self.assertEqual(len(set(v47) - set(v44)), 14)
        self.assertFalse(
            {path for path in set(v44) & set(v47) if v44[path] != v47[path]}
        )
        removed_from_accepted = set(v46) - set(v47)
        self.assertEqual(len(removed_from_accepted), 18)
        self.assertEqual(
            sum("goodman-" in path and not path.endswith("-v2.json") for path in removed_from_accepted),
            10,
        )
        self.assertEqual(
            sum("vnet-" in path and not path.endswith("-v2.json") for path in removed_from_accepted),
            8,
        )
        self.assertEqual(len(set(v47) - set(v46)), 14)

    def test_rejected_downstream_definitions_all_bind_the_v47_fork(self) -> None:
        paths = (
            ROOT / "sources/federation-2026-07-20-public-open-v22.json",
            ROOT / "sources/coverage-audit-2026-07-20-public-open-v21.json",
            ROOT / "sources/construction-master-2026-07-20-public-open-v21.json",
        )
        for path in paths:
            serialized = path.read_text(encoding="utf-8")
            self.assertIn("open-seed-v47", serialized, path)
            self.assertNotIn("open-seed-v46", serialized, path)
        current = CURRENT_LEDGER_DEFINITION.read_text(encoding="utf-8")
        self.assertIn("seed-epoch-official-v46", current)
        self.assertNotIn("seed-epoch-official-v47", current)

    def test_quarantine_document_preserves_non_census_and_salvage_boundary(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for phrase in (
            "not accepted successors",
            "unique physical sites",
            "global-completeness",
            "retain Goodman v1 and VNET v1",
            "STACK and the VNET v2 migration remain excluded",
        ):
            self.assertIn(phrase, normalized)


if __name__ == "__main__":
    unittest.main()
