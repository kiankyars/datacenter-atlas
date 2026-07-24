from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import copy
import csv
from datetime import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch


core_v66 = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v66")
shim_v66 = importlib.import_module("datacenter_atlas.open_seed_v66")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v66.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v66"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v65.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v65"

DEFINITION_PIN = (
    80_110,
    "c75d74fa6e1362c0a4fa2cb650c7a57a210c45caa578e51d84d77c36ed86e50d",
)
MANIFEST_SHA256 = "b8df0f535df3d65efd675d3419b59c78638b21d67084a763550305a8d9005ea7"
TREE_SHA256 = "2ee1853cb92118ffc8422151173aa6c0bb7c768a870d890169f05a162d11969a"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        4_898,
        "aa6cfde5fe1037774e23a844e185efa4dd7bf7d5ca942d883edf48f2be75acd6",
    ),
    "README.md": (
        3_271,
        "8614e140ff85421d567c0a01736cd2bf45ca7c0acf9fc65679a4c881706e7f5a",
    ),
    "atlas.geojson": (
        2_680_515,
        "1aecace5e296e0a8fd839de4bf8db55f7e208e5d58246407bf88dc5e1c7f60cf",
    ),
    "capacity_estimates.csv": (
        244_826,
        "d035125d47abecf144e1bd1c1322a240b7dc21e3aae1cea6a5e5c0d85a66306d",
    ),
    "construction_pipeline.csv": (
        499_770,
        "0b88a8e74649638d8b010709fc603d2c909df4f42f210ac104a888626fb0957f",
    ),
    "construction_source_signals.csv": (
        316_827,
        "2e3eb15f366584e23a1a7f733e2455641de07990b37142e25ca95a9627c512fd",
    ),
    "entities.csv": (
        831_742,
        "8ac6eff808c972bf9b1b70f49b537399a8d4ad99befa1a28be483221cf5d78cc",
    ),
    "evidence.csv": (
        184_874,
        "f9012a46f1edd393780775539edc3578be1198448b195d97b7fd7de68c5a72d1",
    ),
    "lifecycle_freshness.csv": (
        128_512,
        "69f9ca9878ca7eeb30fb51c8688973330b380fd0a33e66c5e07f9afdaa557aa8",
    ),
    "manifest.json": (11_596, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        5_943,
        "3cfeca874cc5f1ef6e8c2731c80bf8552b7b410f4c79b7103c5c5650d68c67f4",
    ),
    "resolution_candidates.json": (
        8_870,
        "97cecb13f9f7adba721b499d9f1247fb85786be02a0c005acf1809c02c29cdab",
    ),
    "source_inputs.json": (
        287_971,
        "569e1a7771ced14c6b7c41c6027017b19363348fe6f5ecabb4d4e97dc53e077d",
    ),
    "summary.json": (
        3_066,
        "0ed96cf47d8e90847ff2da4317798118cf359be22ac7fe42529aeaa84380f0a0",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_v66.py": (
        43_215,
        "7b1fbacb5e451529db9e6e1eac47065bbdec0626edc056f458c070e0f1aec98f",
    ),
    ROOT / "open_seed_v66.py": (
        138,
        "8d83403900bb92fdfddf1cad8b313d687b9713f1584cd76240254867b5fb69f8",
    ),
    ROOT / "scripts/build_open_seed_v66.py": (
        363,
        "598ffeeede3f702b919e70cfbb491e1b3addc96610684ba6c772a27f26394a86",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def counter_hash(counter: Counter[tuple[tuple[str, str], ...]]) -> str:
    unpacked = [dict(packed) for packed in counter.elements()]
    unpacked.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    payload = (
        json.dumps(
            unpacked, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        + "\n"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


class OpenSeedV66Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.selected_rows, selected_paths = core_v66.selected_inputs(cls.base)
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v66-test-db-")
        cls.connection = core_v66._build_database(
            cls.base,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_tree_and_code_are_exact(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, DEFINITION_PIN[0])
        self.assertEqual(sha256(DEFINITION), DEFINITION_PIN[1])
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(core_v66.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(
            set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()}
        )
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertTrue(output.is_file())
                self.assertFalse(output.is_symlink())
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
        for path, (size, digest) in CODE_PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(sha256(BASE_DEFINITION), core_v66.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core_v66.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core_v66.tree_digest(BASE_RELEASE), core_v66.BASE_TREE_SHA256)

    def test_exact_v65_selection_adjacency_and_all_eight_source_pins(self) -> None:
        before = {row["path"]: row["sha256"] for row in self.base["curated_inputs"]}
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        old_paths = set(core_v66.REPLACEMENT_PINS)
        new_paths = {
            successor for _, successor, _ in core_v66.REPLACEMENT_PINS.values()
        }
        self.assertEqual((len(before), len(after)), (364, 364))
        self.assertEqual(set(before) - set(after), old_paths)
        self.assertEqual(set(after) - set(before), new_paths)
        self.assertEqual(
            {key: before[key] for key in set(before) & set(after)},
            {key: after[key] for key in set(before) & set(after)},
        )
        for predecessor, (old_hash, successor, new_hash) in (
            core_v66.REPLACEMENT_PINS.items()
        ):
            with self.subTest(predecessor=predecessor):
                self.assertEqual(before[predecessor], old_hash)
                self.assertEqual(after[successor], new_hash)
                self.assertEqual(sha256(ROOT / predecessor), old_hash)
                self.assertEqual(sha256(ROOT / successor), new_hash)
                self.assertNotIn(predecessor, after)
                self.assertNotIn(successor, before)
        rejected, rejected_hash = core_v66.REJECTED_EDGED_V2
        self.assertEqual(sha256(ROOT / rejected), rejected_hash)
        self.assertNotIn(rejected, before)
        self.assertNotIn(rejected, after)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T07:00:00Z"},
        )
        self.assertGreater(
            datetime.fromisoformat(self.definition["build"]["recorded_at"]),
            datetime.fromisoformat(self.base["build"]["recorded_at"]),
        )
        versions = Counter(
            json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for row in self.selected_rows
        )
        self.assertEqual(versions, {"1.0": 315, "1.1": 49})

    def test_successors_have_only_six_appended_coordinate_evidence_rows(self) -> None:
        core_v66._validate_source_successors()
        appended_total = 0
        for predecessor_path, (_, successor_path, _) in (
            core_v66.REPLACEMENT_PINS.items()
        ):
            predecessor = json.loads((ROOT / predecessor_path).read_text())
            successor = json.loads((ROOT / successor_path).read_text())
            inherited = len(predecessor["evidence"])
            appended_total += len(successor["evidence"]) - inherited
            self.assertEqual(successor["evidence"][:inherited], predecessor["evidence"])
            for section in (
                "lifecycle",
                "capacities",
                "workloads",
                "operating_models",
            ):
                self.assertEqual(successor[section], predecessor[section])
            for entity_name in ("campus", "project"):
                before = predecessor[entity_name]
                after = successor[entity_name]
                self.assertEqual(after["stable_key"], before["stable_key"])
                self.assertEqual(after["address"], before["address"])
                self.assertEqual(after["roles"], before["roles"])
            restored = copy.deepcopy(successor)
            restored["schema_version"] = predecessor["schema_version"]
            restored["evidence"] = copy.deepcopy(predecessor["evidence"])
            restored["campus"] = copy.deepcopy(predecessor["campus"])
            restored["project"] = copy.deepcopy(predecessor["project"])
            self.assertEqual(restored, predecessor)
        self.assertEqual(appended_total, 6)

    def test_database_counts_and_coordinate_snapshot_contract_are_exact(self) -> None:
        core_v66._validate_database_contract(self.connection)
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
                "entities": 755,
                "evidence": 583,
                "lifecycle_observations": 444,
                "capacity_estimates": 513,
                "entity_snapshots": 775,
                "operating_model_observations": 56,
                "workload_observations": 125,
            },
        )
        self.assertEqual(len(core_v66.MUTATED_ENTITY_KEYS), 8)
        self.assertEqual(len(core_v66.MUTATED_PROJECT_KEYS), 4)

    def test_csv_deltas_and_allowed_entity_fields_are_exact(self) -> None:
        core_v66._validate_release_delta(RELEASE)
        for filename, expected in core_v66.CSV_DELTA_CONTRACT.items():
            with self.subTest(filename=filename):
                before = Counter(
                    tuple(row.items()) for row in rows(BASE_RELEASE / filename)
                )
                after = Counter(tuple(row.items()) for row in rows(RELEASE / filename))
                common = before & after
                added = after - common
                removed = before - common
                self.assertEqual(
                    (
                        sum(common.values()),
                        sum(added.values()),
                        counter_hash(added),
                        sum(removed.values()),
                        counter_hash(removed),
                    ),
                    expected,
                )
        evidence_before = Counter(
            tuple(row.items()) for row in rows(BASE_RELEASE / "evidence.csv")
        )
        evidence_after = Counter(
            tuple(row.items()) for row in rows(RELEASE / "evidence.csv")
        )
        added_evidence = {
            row["evidence_id"]: (
                row["source_family"],
                row["title"],
                row["content_hash"],
            )
            for row in map(dict, (evidence_after - evidence_before).elements())
        }
        removed_evidence = {
            row["evidence_id"]: (
                row["source_family"],
                row["title"],
                row["content_hash"],
            )
            for row in map(dict, (evidence_before - evidence_after).elements())
        }
        self.assertEqual(added_evidence, core_v66.PUBLIC_EVIDENCE_ADDED)
        self.assertEqual(removed_evidence, core_v66.PUBLIC_EVIDENCE_REMOVED)

        resolution_before = Counter(
            tuple(row.items())
            for row in rows(BASE_RELEASE / "resolution_candidates.csv")
        )
        resolution_after = Counter(
            tuple(row.items())
            for row in rows(RELEASE / "resolution_candidates.csv")
        )
        added_candidate = dict(next((resolution_after - resolution_before).elements()))
        self.assertEqual(
            {
                key: added_candidate[key]
                for key in core_v66.RESOLUTION_CANDIDATE_ADDED
            },
            core_v66.RESOLUTION_CANDIDATE_ADDED,
        )
        self.assertFalse(resolution_before - resolution_after)
        before_entities = {
            row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")
        }
        after_entities = {
            row["stable_key"]: row for row in rows(RELEASE / "entities.csv")
        }
        changed = {
            key for key in before_entities if before_entities[key] != after_entities[key]
        }
        self.assertEqual(changed, core_v66.MUTATED_ENTITY_KEYS)
        for key in changed:
            fields = {
                field
                for field in before_entities[key]
                if before_entities[key][field] != after_entities[key][field]
            }
            self.assertTrue(fields)
            self.assertLessEqual(fields, core_v66.ENTITY_SNAPSHOT_CHANGE_FIELDS)

    def test_release_facts_and_freshness_statuses_are_unchanged(self) -> None:
        core_v66._validate_release_facts(RELEASE)
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "entities",
                    "evidence_records",
                    "resolution_candidates",
                    "lifecycle_freshness_records",
                    "lifecycle_status_semantics",
                    "current_status_inferred",
                )
            },
            {
                "entities": 755,
                "evidence_records": 471,
                "resolution_candidates": 6,
                "lifecycle_freshness_records": 429,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )
        self.assertEqual(
            (RELEASE / "lifecycle_freshness.csv").read_bytes(),
            (BASE_RELEASE / "lifecycle_freshness.csv").read_bytes(),
        )
        freshness = rows(RELEASE / "lifecycle_freshness.csv")
        self.assertEqual(len(freshness), 429)
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness
            )
        )

    def test_both_import_layouts_resolve_the_same_v66_contract(self) -> None:
        self.assertNotEqual(core_v66.__file__, shim_v66.__file__)
        self.assertIs(core_v66.selected_inputs, shim_v66.selected_inputs)
        self.assertIs(core_v66.validate_open_seed_v66, shim_v66.validate_open_seed_v66)
        self.assertEqual(core_v66.RELEASE_ID, shim_v66.RELEASE_ID)
        core_rows, _ = core_v66.selected_inputs(self.base)
        shim_rows, _ = shim_v66.selected_inputs(self.base)
        self.assertEqual(core_rows, shim_rows)

    def test_double_offline_replay_is_exact(self) -> None:
        error = AssertionError("v66 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = core_v66.validate_open_seed_v66(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 755)
        self.assertFalse(manifest["current_status_inferred"])
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core_v66.validate_open_seed_v66(DEFINITION, RELEASE, replay_count=1)

    def test_collision_tamper_symlink_and_stale_mutation_fail_closed(self) -> None:
        frozen_guard = core_v66._guard_state()
        definition_hash = sha256(DEFINITION)
        release_tree = core_v66.tree_digest(RELEASE)
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core_v66.build_open_seed_v66()
        self.assertEqual(core_v66._guard_state(), frozen_guard)
        self.assertEqual(sha256(DEFINITION), definition_hash)
        self.assertEqual(core_v66.tree_digest(RELEASE), release_tree)
        self.assertFalse(core_v66.PUBLICATION_LOCK.exists())

        with tempfile.TemporaryDirectory(
            prefix="v66-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest hash"):
                core_v66.validate_open_seed_v66(
                    DEFINITION, copied, require_frozen=False
                )

        with tempfile.TemporaryDirectory(
            prefix="v66-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core_v66.validate_open_seed_v66(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
