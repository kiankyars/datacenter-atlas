from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v8 as release_v8
    from datacenter_atlas.datacenter_atlas import open_seed_v63 as v63
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v8 as release_v8
    from datacenter_atlas import open_seed_v63 as v63


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v63"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"

DEFINITION_SHA256 = "13bfdcbda96769de1a39e1bc41e67ad7e0a6e98d026fedda3384fbd89bc8adff"
MANIFEST_SHA256 = "8ee3539f639641c7f97827ba7a21c13b7e907881ba858970e701675510eab4ba"
TREE_SHA256 = "44e7df9300c40fc76a0f9e55bc6de05f1a3f11a1ef39926e38fff7bb8b8127f4"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        4_683,
        "27c21cb7d55c1759f85d407a63297728ec469c0ad588d5140cd7ed5048edaef9",
    ),
    "README.md": (
        3_549,
        "083edc8b9eebef545683563d79d6e153c81de602aa146b8b6fc16568b8a790d3",
    ),
    "atlas.geojson": (
        2_609_443,
        "3679868da7d9ca40bbc91683a2b425ee3052763156dc2263c638a0fb2ae5f029",
    ),
    "capacity_estimates.csv": (
        240_892,
        "6b80fab5455299c135d348c29e08c3806df4f9e07b595570e2134ab7a16e2055",
    ),
    "construction_pipeline.csv": (
        487_682,
        "5c92937e41664886069ebb21c2633ba7e56f765142e3e7811e7efdd8fa35cf07",
    ),
    "construction_source_signals.csv": (
        308_307,
        "3c03e64e2679e9cce3f2b0a51e9a85fe0309f629bab0ef417ac2097ced9bf1c9",
    ),
    "entities.csv": (
        808_969,
        "f5a43b681b23dff49e17d7ddf27c66a92ee376d1a2637a638a828e49f96162f9",
    ),
    "evidence.csv": (
        177_048,
        "49d718285da84628546ba1e3440a69596efe7d09ea24027ce9b7dd6f04aa317b",
    ),
    "lifecycle_freshness.csv": (
        125_309,
        "9695753a1510bbe819451fc4df55131ca74744c6d2218d72aa14bc306c49661d",
    ),
    "manifest.json": (11_078, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_989,
        "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264",
    ),
    "resolution_candidates.json": (
        7_384,
        "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7",
    ),
    "source_inputs.json": (
        273_644,
        "e8f04ec9a032c1abf538c16b8bf67559fe65634383b6da36b3b0dc32da36640c",
    ),
    "summary.json": (
        3_065,
        "bdbf84274779165aa4e741df6e182a8caf12facfbe328b832f7e1aa2168f725c",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_release_v8.py": (
        16_145,
        "d3eb870eb77d627b86d0e8065793ef319d3cd866d61094bd4555a94c51f50d88",
    ),
    ROOT / "datacenter_atlas/open_seed_v63.py": (
        40_588,
        "6b9399a6fda928ec2b2d6598518500f683ff846a98cc56b6dcd30711cf6a86b3",
    ),
    ROOT / "open_seed_v63.py": (
        138,
        "453a6e9c8197b3b1801a4c55322bff8ea27e16d1f51278a01083da03cc0e8c55",
    ),
    ROOT / "scripts/build_open_seed_v63.py": (
        363,
        "281bb2e8d91b60eebbea8017afebd0abadedc2446eb485a6f4626c23e826f52d",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV63Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v63-test-db-")
        cls.selected_rows, selected_paths = v63.selected_inputs(cls.base_definition)
        cls.connection = v63._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_tree_and_code_are_exact(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 77_719)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v63.tree_digest(RELEASE), TREE_SHA256)
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
            self.assertEqual(path.stat().st_size, size, path)
            self.assertEqual(sha256(path), digest, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(sha256(BASE_DEFINITION), v63.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), v63.BASE_MANIFEST_SHA256
        )
        self.assertEqual(v63.tree_digest(BASE_RELEASE), v63.BASE_TREE_SHA256)
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
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
                "entities": 737,
                "evidence_records": 452,
                "capacity_estimates": 506,
                "construction_pipeline_records": 377,
                "construction_source_signals": 284,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 419,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v62_adjacency_source_boundaries_and_calendar_gate(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        self.assertEqual((len(before), len(after)), (350, 354))
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(set(after) - set(before), set(release_v8.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T05:00:00Z"},
        )
        self.assertEqual(
            self.definition["epoch_capture"], self.base_definition["epoch_capture"]
        )
        self.assertEqual(
            self.definition["expected_epoch_result"],
            self.base_definition["expected_epoch_result"],
        )
        excluded = (
            release_v8.STALE_EXCLUSIONS
            | release_v8.PENDING_NEXT_DAY_EXCLUSIONS
            | {
                "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
                "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
            }
        )
        self.assertFalse(excluded & set(after))
        self.assertTrue(all("2026-07-21" not in path for path in after))
        versions = Counter(
            json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for row in self.selected_rows
        )
        self.assertEqual(versions, {"1.0": 316, "1.1": 38})
        for relative, expected in v63.SOURCE_BOUNDARIES.items():
            source = ROOT / relative
            self.assertEqual(sha256(source), release_v8.ADDITION_PINS[relative])
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            document = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(v63._projected_source(document), expected)

    def test_database_contract_preserves_identity_metric_and_role_boundaries(
        self,
    ) -> None:
        v63._validate_database_delta(self.connection)
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
                "entities": 737,
                "evidence": 557,
                "lifecycle_observations": 434,
                "capacity_estimates": 507,
                "entity_snapshots": 757,
                "operating_model_observations": 55,
                "workload_observations": 124,
            },
        )
        relevant = tuple(sorted(v63.RELEVANT_ENTITY_KEYS))
        placeholders = ",".join("?" for _ in relevant)
        capacities = {
            tuple(row)
            for row in self.connection.execute(
                f"""
                SELECT entities.stable_key, capacity_estimates.metric,
                       capacity_estimates.stage, capacity_estimates.unit,
                       capacity_estimates.low, capacity_estimates.base,
                       capacity_estimates.high, capacity_estimates.as_of_date
                FROM capacity_estimates
                JOIN entities ON entities.id = capacity_estimates.entity_id
                WHERE entities.stable_key IN ({placeholders})
                """,
                relevant,
            )
        }
        self.assertEqual(capacities, v63.CAPACITY_CONTRACT)
        self.assertFalse(
            {
                row[0]
                for row in capacities
                if row[0] in {v63.POWERHOUSE_PROJECT_KEY, v63.QTS_PROJECT_KEY}
            }
        )
        qts_roles = self.connection.execute(
            """
            SELECT tags_json FROM entity_snapshots
            JOIN entities ON entities.id = entity_snapshots.entity_id
            WHERE entities.stable_key = ?
            """,
            (v63.QTS_PROJECT_KEY,),
        ).fetchone()[0]
        self.assertFalse(any(key.startswith("role:") for key in json.loads(qts_roles)))

    def test_release_delta_is_additive_and_frozen_v62_rows_are_unchanged(self) -> None:
        v63._validate_release_delta(RELEASE)
        v63._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v63.ADDED_ENTITY_KEYS)
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(
            {key for key in before if before[key] != after[key]},
            set(),
        )
        self.assertEqual(after[v63.DATABANK_IAD5_KEY], before[v63.DATABANK_IAD5_KEY])

    def test_freshness_is_last_observed_and_never_a_current_claim(self) -> None:
        freshness = {
            row["stable_key"]: row for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual(len(freshness), 419)
        expected = {
            v63.CORE_PROJECT_KEY: ("under_construction", "2026-05-06", "75"),
            v63.DATABANK_IAD6_KEY: ("under_construction", "2026-02-19", "151"),
            v63.POWERHOUSE_PROJECT_KEY: ("shell", "2026-03-27", "115"),
            v63.QTS_PROJECT_KEY: ("under_construction", "2026-05-13", "68"),
        }
        for key, (status, observed, age) in expected.items():
            row = freshness[key]
            with self.subTest(stable_key=key):
                self.assertEqual(row["last_observed_status"], status)
                self.assertEqual(row["last_observed_status_as_of"], observed)
                self.assertEqual(row["observation_age_days"], age)
                self.assertEqual(row["current_status_classification"], "unknown")
                self.assertEqual(row["current_construction_claim"], "false")
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness.values()
            )
        )

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v63 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v8.validate_open_seed_release_v8(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 737)
        self.assertEqual(manifest["lifecycle_status_semantics"], "last_observed")
        self.assertFalse(manifest["current_status_inferred"])

    def test_collision_tamper_and_symlink_fail_closed(self) -> None:
        before_definition = sha256(DEFINITION)
        before_tree = v63.tree_digest(RELEASE)
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            v63.build_open_seed_v63()
        self.assertEqual(sha256(DEFINITION), before_definition)
        self.assertEqual(v63.tree_digest(RELEASE), before_tree)
        self.assertFalse(v63.PUBLICATION_LOCK.exists())

        with tempfile.TemporaryDirectory(
            prefix="v63-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "release manifest"):
                release_v8.validate_open_seed_release_v8(
                    DEFINITION, copied, require_frozen=False
                )

        with tempfile.TemporaryDirectory(
            prefix="v63-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                release_v8.validate_open_seed_release_v8(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
