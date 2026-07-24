from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import open_seed_release_v9 as release_v9
    from datacenter_atlas.datacenter_atlas import open_seed_v64 as v64
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v9 as release_v9
    from datacenter_atlas import open_seed_v64 as v64


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v64.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v64"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v63"

DEFINITION_SHA256 = "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e"
MANIFEST_SHA256 = "5c5b19079ce237b859c2bdaf465bf1aec17392f52a75ad81805a919e1ee4cc1d"
TREE_SHA256 = "05901f4760e452d5d3deb4134b3434e248f7e8f15873a5f27cdad559582385da"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        4_755,
        "620fb4584ec55898084135259202d306aa5ef4e1ec32eed1a1b22a450ca3203a",
    ),
    "README.md": (
        3_536,
        "6ae546cf73ecb059df724cfcd7fa3a195e49007c560b64d1e9bab3f2b127c2c8",
    ),
    "atlas.geojson": (
        2_660_121,
        "91a0a29774b0efe9f2fecdc5510b7c95392abaa81e9381fd444f61395adf3ad1",
    ),
    "capacity_estimates.csv": (
        244_223,
        "fb7656dc75f8f33c7195a7fd02669c5512a728a5f6427c8d9ca0f3269aa3b67b",
    ),
    "construction_pipeline.csv": (
        495_373,
        "b345ac0445906d812d4c0eb2ee19afe7d08ba6afc68beb3073aea5bc6a81ca64",
    ),
    "construction_source_signals.csv": (
        315_718,
        "b72b45a85f2b94b77cf5faeb890ae4b827d948bdf8ba86080f7d46045cf2a7af",
    ),
    "entities.csv": (
        822_694,
        "57ce524b280e3bca04c80f4d7c53892832396c7a73db29e983031da2352ca54f",
    ),
    "evidence.csv": (
        181_252,
        "41bf9c35a780231ad9aa28915e1aa667f6a848cb6e5b75f3fd11408041ecd648",
    ),
    "lifecycle_freshness.csv": (
        128_154,
        "ffb1cdb575be350158948209019a605d4d98611c2b8d8f0856cb88e662237024",
    ),
    "manifest.json": (11_390, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_989,
        "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264",
    ),
    "resolution_candidates.json": (
        7_384,
        "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7",
    ),
    "source_inputs.json": (
        282_154,
        "51f0a9dc11fb6004b09ff3c8b90c3c7d6a549b479bac6fd9454f57e89b2a7dab",
    ),
    "summary.json": (
        3_066,
        "4ab7bcdef740f4a42dc970879823f7642c8a26ad301ef7c61ee7710d8bb525db",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_release_v9.py": (
        19_174,
        "d5c6f17460ae4a975bf1c2cc839e8bf7eab154b0c6bb66a387222a4317dfa8b1",
    ),
    ROOT / "datacenter_atlas/open_seed_v64.py": (
        40_131,
        "4adb4507f6ed4d828a1a0db7417ac8bab81c6a5e67e062fe4ab7f438c70add82",
    ),
    ROOT / "open_seed_v64.py": (
        138,
        "60ed5363642518840fe363e9cf13bdd660c002f6112925939e3acd843d49178f",
    ),
    ROOT / "scripts/build_open_seed_v64.py": (
        363,
        "7e6d094d9ff4f03bcc5297cd1a18901688ad04424538c112700e08255c0b4e63",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV64Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v64-test-db-")
        cls.selected_rows, selected_paths = v64.selected_inputs(cls.base_definition)
        cls.connection = v64._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_tree_and_code_are_exact(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 79_698)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v64.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(
            set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()}
        )
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
        for path, (size, digest) in CODE_PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(sha256(BASE_DEFINITION), v64.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), v64.BASE_MANIFEST_SHA256
        )
        self.assertEqual(v64.tree_digest(BASE_RELEASE), v64.BASE_TREE_SHA256)
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "entities",
                    "evidence_records",
                    "capacity_estimates",
                    "construction_pipeline_records",
                    "construction_source_signals",
                    "resolution_candidates",
                    "lifecycle_freshness_records",
                    "lifecycle_status_semantics",
                    "current_status_inferred",
                )
            },
            {
                "entities": 753,
                "evidence_records": 464,
                "capacity_estimates": 511,
                "construction_pipeline_records": 386,
                "construction_source_signals": 291,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 428,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v63_adjacency_source_boundaries_and_calendar_gate(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        self.assertEqual((len(before), len(after)), (354, 363))
        self.assertFalse(set(before) - set(after))
        self.assertEqual(set(after) - set(before), set(release_v9.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T05:50:00Z"},
        )
        self.assertEqual(
            self.definition["epoch_capture"], self.base_definition["epoch_capture"]
        )
        self.assertEqual(
            self.definition["expected_epoch_result"],
            self.base_definition["expected_epoch_result"],
        )
        excluded = (
            release_v9.STALE_EXCLUSIONS
            | release_v9.PENDING_NEXT_DAY_EXCLUSIONS
            | release_v9.OUT_OF_SCOPE_EXCLUSIONS
        )
        self.assertFalse(excluded & set(after))
        self.assertTrue(all("2026-07-21" not in path for path in after))
        versions = Counter(
            json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for row in self.selected_rows
        )
        self.assertEqual(versions, {"1.0": 316, "1.1": 47})
        for relative, expected in v64.SOURCE_BOUNDARIES.items():
            source = ROOT / relative
            self.assertEqual(sha256(source), release_v9.ADDITION_PINS[relative])
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            document = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(v64._projected_source(document), expected)
            release_v9._validate_local_research_day(document, relative)
            self.assertLessEqual(
                max(item["retrieved_at"] for item in document["evidence"]),
                release_v9.RECORDED_AT,
            )

        tampered = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-cdc-beard-be1.json").read_text(
                encoding="utf-8"
            )
        )
        tampered["campus"]["as_of_date"] = "2026-07-21"
        with self.assertRaisesRegex(
            release_v9.OpenSeedReleaseV9Error, "crosses the Jul 20"
        ):
            release_v9._validate_local_research_day(tampered, "calendar-test")

    def test_database_and_nonpromotion_contracts_are_exact(self) -> None:
        v64._validate_database_delta(self.connection)
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                0
            ]
            for table in (
                "entities",
                "evidence",
                "lifecycle_observations",
                "capacity_estimates",
                "entity_snapshots",
                "operating_model_observations",
                "workload_observations",
            )
        }
        self.assertEqual(
            counts,
            {
                "entities": 753,
                "evidence": 572,
                "lifecycle_observations": 443,
                "capacity_estimates": 512,
                "entity_snapshots": 773,
                "operating_model_observations": 56,
                "workload_observations": 124,
            },
        )
        self.assertEqual(len(v64.ADDED_ENTITY_KEYS), 16)
        self.assertEqual(len(v64.ADDED_PROJECT_KEYS), 9)
        self.assertFalse(v64.MUTATED_ENTITY_KEYS)
        self.assertEqual(len(v64.CAPACITY_CONTRACT), 5)
        for relative in release_v9.ADDITION_PINS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertIsNone(document["campus"]["coordinates"])
            self.assertIsNone(document["campus"]["geometry"])
            self.assertIsNone(document["project"]["coordinates"])
            self.assertIsNone(document["project"]["geometry"])
            self.assertFalse(document["workloads"])
        for relative in (
            "sources/curated-official-2026-07-20-cdc-beard-be1.json",
            "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json",
            "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json",
            "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
            "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
        ):
            self.assertFalse(
                json.loads((ROOT / relative).read_text(encoding="utf-8"))["capacities"]
            )

    def test_release_delta_is_additive_and_v63_rows_are_unchanged(self) -> None:
        v64._validate_release_delta(RELEASE)
        v64._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v64.ADDED_ENTITY_KEYS)
        self.assertFalse(set(before) - set(after))
        self.assertFalse({key for key in before if before[key] != after[key]})

    def test_freshness_is_dated_and_never_a_current_claim(self) -> None:
        freshness = {
            row["stable_key"]: row for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual(len(freshness), 428)
        expected_ages = {
            v64.CDC_PROJECT_KEY: 0,
            v64.VIE_PROJECT_KEY: 32,
            v64.BORLANGE_B1_KEY: 201,
            v64.BORLANGE_B2_KEY: 201,
            v64.FALUN_E_KEY: 201,
            v64.FALUN_F_KEY: 201,
            v64.BUPYEONG_PROJECT_KEY: 242,
            v64.HK1_PROJECT_KEY: 115,
            v64.TERACO_PROJECT_KEY: 3,
        }
        for key, age in expected_ages.items():
            row = freshness[key]
            self.assertEqual(row["observation_age_days"], str(age))
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertEqual(row["current_construction_claim"], "false")
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness.values()
            )
        )
        self.assertEqual(
            Counter(row["freshness_class"] for row in freshness.values()),
            {
                "recent_0_90_days": 218,
                "aging_91_365_days": 183,
                "stale_over_365_days": 27,
            },
        )
        self.assertLessEqual(
            max(
                date.fromisoformat(row["last_observed_status_as_of"])
                for row in freshness.values()
            ),
            date.fromisoformat("2026-07-20"),
        )

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v64 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v9.validate_open_seed_release_v9(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 753)
        self.assertEqual(manifest["lifecycle_status_semantics"], "last_observed")
        self.assertFalse(manifest["current_status_inferred"])

    def test_collision_tamper_and_symlink_fail_closed(self) -> None:
        before_definition = sha256(DEFINITION)
        before_tree = v64.tree_digest(RELEASE)
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            v64.build_open_seed_v64()
        self.assertEqual(sha256(DEFINITION), before_definition)
        self.assertEqual(v64.tree_digest(RELEASE), before_tree)
        self.assertFalse(v64.PUBLICATION_LOCK.exists())

        with tempfile.TemporaryDirectory(
            prefix="v64-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "release manifest"):
                release_v9.validate_open_seed_release_v9(
                    DEFINITION, copied, require_frozen=False
                )

        with tempfile.TemporaryDirectory(
            prefix="v64-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                release_v9.validate_open_seed_release_v9(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
