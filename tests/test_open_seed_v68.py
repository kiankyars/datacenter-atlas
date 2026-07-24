from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
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


core_v68 = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v68")
shim_v68 = importlib.import_module("datacenter_atlas.open_seed_v68")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v68"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"

DEFINITION_PIN = (
    86_041,
    "430544a894c0e529693699fe6db36387b690f621ee899a38bedd9ea093ec394f",
)
MANIFEST_SHA256 = "7aa9d511831509f953fdfe6bccd9380feeb2feac11ec529eb9b024243a7da3e7"
TREE_SHA256 = "855258248ab3af498ef6f6259d55a2ace093c8eacdcc7b6b1aafe03ac8f3b89b"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_657,
        "8d357db7dd2756ecfe24c1ba54255643d3d92b66df98c831e51ce0f847fc6aca",
    ),
    "README.md": (
        3_611,
        "32f72102d599a3aa8e0c33d0fec6790de9905f28d8a915b7ce6fcc6c95a59534",
    ),
    "atlas.geojson": (
        2_843_869,
        "4238e9b0658c37a46d735c38592592e7d7ddc68ca211272cd8c7138d1c09c362",
    ),
    "capacity_estimates.csv": (
        255_161,
        "63d5b8768bd105e30e4f9d4d27efecce2c0d64c66da08dd42b53234b2aff9169",
    ),
    "construction_pipeline.csv": (
        528_166,
        "1b71e0486b0efc03277e4cbd05eb8d15505df306769e3b7c1c8e7a0050401419",
    ),
    "construction_source_signals.csv": (
        340_097,
        "a2515d41e015283c258ff780afcc8e39fd2b8f13326eb924d169d1cde2e029ae",
    ),
    "entities.csv": (
        874_687,
        "2063df8e053d1391078368a26f10577901b8a9e8e1cf7e7ca67225c8c937425f",
    ),
    "evidence.csv": (
        199_205,
        "b470e0b2bf3834fc2e0331cb8be5312662a333e5325223240a629ef4a441722d",
    ),
    "lifecycle_freshness.csv": (
        136_421,
        "942d147d416dc3455457dca67babbfd875c58b94bcd74529f3e5d66f8d5f5ace",
    ),
    "manifest.json": (12_432, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        5_943,
        "3cfeca874cc5f1ef6e8c2731c80bf8552b7b410f4c79b7103c5c5650d68c67f4",
    ),
    "resolution_candidates.json": (
        8_870,
        "97cecb13f9f7adba721b499d9f1247fb85786be02a0c005acf1809c02c29cdab",
    ),
    "source_inputs.json": (
        313_665,
        "360f2b366f55437c44ce3c2d0413529e6eeaa9db83c2e27fe0323b5086e8ef47",
    ),
    "summary.json": (
        3_162,
        "239d77127577809c42e09376c47ebc8c3f88359cadf24d43312bba394fb6abb5",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_v68.py": (
        62_781,
        "fb3f801026da090af4466c4454d2f7b48d2c07347226deac9d8e5d9afd722f1e",
    ),
    ROOT / "open_seed_v68.py": (
        138,
        "cd8fad8c613d189d2120f88ccf06e032f763088c227c9ba93541b5b9324bdc5d",
    ),
    ROOT / "scripts/build_open_seed_v68.py": (
        363,
        "df61157701b7982030745fc28db83462e35491ff693025afb697c3e2a1d5e138",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


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


class OpenSeedV68Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.selected_rows, selected_paths = core_v68.selected_inputs(cls.base)
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v68-test-db-")
        cls.connection = core_v68._build_database(
            cls.base,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def _addition_documents(self) -> dict[str, dict[str, object]]:
        return {
            relative: json.loads((ROOT / relative).read_text(encoding="utf-8"))
            for relative in core_v68.ADDITION_PINS
        }

    def test_frozen_definition_release_tree_and_code_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(core_v68.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertTrue(output.is_file())
                self.assertFalse(output.is_symlink())
                self.assertEqual((output.stat().st_size, sha256(output)), expected)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
        for path, expected in CODE_PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(sha256(BASE_DEFINITION), core_v68.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"),
            core_v68.BASE_MANIFEST_SHA256,
        )
        self.assertEqual(core_v68.tree_digest(BASE_RELEASE), core_v68.BASE_TREE_SHA256)

    def test_exact_v67_plus_thirteen_canonical_selection(self) -> None:
        before = self.base["curated_inputs"]
        after = self.definition["curated_inputs"]
        self.assertEqual((len(before), len(after)), (378, 391))
        self.assertEqual(after[:378], before)
        self.assertEqual(
            [row["path"] for row in after[378:]],
            sorted(core_v68.ADDITION_PINS),
        )
        self.assertEqual(after, self.selected_rows)
        for relative, (size, digest) in core_v68.ADDITION_PINS.items():
            source = ROOT / relative
            with self.subTest(source=relative):
                self.assertEqual((source.stat().st_size, sha256(source)), (size, digest))
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                self.assertIn("2026-07-21", relative)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-21", "recorded_at": "2026-07-21T09:30:00Z"},
        )
        self.assertGreater(
            datetime.fromisoformat(self.definition["build"]["recorded_at"]),
            datetime.fromisoformat(self.base["build"]["recorded_at"]),
        )
        for key in ("epoch_capture", "expected_epoch_result", "schema_version", "scope"):
            self.assertEqual(self.definition[key], self.base[key])
        self.assertEqual(
            self.definition["freshness_contract"], self.base["freshness_contract"]
        )

    def test_two_artifact_lineage_and_controlled_reuse_are_exact(self) -> None:
        state = core_v68._validate_artifact_lineage()
        self.assertEqual(set(state), set(core_v68.DISCOVERY_ARTIFACT_PINS))
        core_v68._validate_additions()
        documents = self._addition_documents()
        self.assertEqual(len(documents), 13)
        evidence: dict[str, list[dict[str, object]]] = {}
        entities: dict[str, list[dict[str, object]]] = {}
        capacities = 0
        lifecycle = 0
        for relative, document in documents.items():
            self.assertEqual(document["schema_version"], "1.1", relative)
            capacities += len(document["capacities"])
            lifecycle += len(document["lifecycle"])
            self.assertFalse(document["workloads"])
            self.assertFalse(document["operating_models"])
            for record in document["evidence"]:
                evidence.setdefault(record["key"], []).append(record)
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                entities.setdefault(entity["stable_key"], []).append(entity)
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
        self.assertEqual((lifecycle, capacities), (13, 9))
        self.assertEqual((sum(map(len, evidence.values())), len(evidence)), (16, 13))
        self.assertEqual(
            {key: len(value) for key, value in evidence.items() if len(value) > 1},
            core_v68.SHARED_EVIDENCE_COUNTS,
        )
        self.assertEqual(set(entities), core_v68.ADDED_ENTITY_KEYS)
        self.assertEqual(
            {key: len(value) for key, value in entities.items() if len(value) > 1},
            {core_v68.SHARED_CAMPUS_KEY: 4},
        )
        for records in (*evidence.values(), *entities.values()):
            self.assertTrue(all(record == records[0] for record in records[1:]))

    def test_untyped_power_hardware_and_compute_remain_metadata_only(self) -> None:
        documents = self._addition_documents()
        observed: dict[str, dict[str, object]] = {}
        for document in documents.values():
            for evidence in document["evidence"]:
                expected = core_v68.UNTYPED_METADATA_CONTRACT.get(evidence["key"])
                if expected is not None:
                    observed[evidence["key"]] = {
                        key: evidence["metadata"].get(key) for key in expected
                    }
        self.assertEqual(observed, core_v68.UNTYPED_METADATA_CONTRACT)
        keys = tuple(sorted(core_v68.ADDED_ENTITY_KEYS))
        placeholders = ",".join("?" for _ in keys)
        capacity = self.connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, base, as_of_date
            FROM capacity_estimates JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        ).fetchall()
        self.assertEqual({tuple(row) for row in capacity}, core_v68.CAPACITY_CONTRACT)
        self.assertFalse(
            self.connection.execute(
                f"""
                SELECT 1 FROM workload_observations
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN ({placeholders}) LIMIT 1
                """,
                keys,
            ).fetchone()
        )
        self.assertFalse(
            self.connection.execute(
                f"""
                SELECT 1 FROM operating_model_observations
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN ({placeholders}) LIMIT 1
                """,
                keys,
            ).fetchone()
        )
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "no capacity arithmetic is valid",
            "unique-site",
            "satellite",
            "computer-vision",
        ):
            self.assertIn(phrase, readme)

    def test_database_delta_and_prior_semantics_are_exact(self) -> None:
        core_v68._validate_database_contract(self.connection)
        core_v68._validate_prior_semantics(self.connection, self.base)
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
                "entities": 806,
                "evidence": 628,
                "lifecycle_observations": 472,
                "capacity_estimates": 531,
                "entity_snapshots": 826,
                "operating_model_observations": 56,
                "workload_observations": 128,
            },
        )
        shared = self.connection.execute(
            """
            SELECT COUNT(*) FROM entity_snapshots
            JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key = ?
            """,
            (core_v68.SHARED_CAMPUS_KEY,),
        ).fetchone()[0]
        self.assertEqual(shared, 1)

    def test_public_csv_deltas_and_release_facts_are_exact(self) -> None:
        core_v68._validate_release_delta(RELEASE)
        core_v68._validate_release_facts(RELEASE)
        for filename, expected in core_v68.CSV_DELTA_CONTRACT.items():
            with self.subTest(filename=filename):
                before = csv_counter(BASE_RELEASE / filename)
                after = csv_counter(RELEASE / filename)
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
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
            )

    def test_freshness_preserves_prior_rows_and_never_infers_current(self) -> None:
        before = {
            row["stable_key"]: row
            for row in rows(BASE_RELEASE / "lifecycle_freshness.csv")
        }
        after = {
            row["stable_key"]: row
            for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual((len(before), len(after)), (443, 456))
        self.assertEqual(set(after) - set(before), set(core_v68.LIFECYCLE_WINNERS))
        self.assertTrue(all(after[key] == old for key, old in before.items()))
        self.assertEqual(
            Counter(row["freshness_class"] for row in after.values()),
            {
                "recent_0_90_days": 236,
                "aging_91_365_days": 191,
                "stale_over_365_days": 29,
            },
        )
        self.assertTrue(
            all(
                row["status_semantics"] == "last_observed"
                and row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in after.values()
            )
        )
        self.assertEqual(
            {
                key: after[key]["last_observed_status_as_of"]
                for key in core_v68.DATED_HISTORICAL_PROJECT_KEYS
            },
            {
                "curated:harch-intelligence-dakhla-campus:initial-development": "2026-03-15",
                "curated:firebird-ai-center-hrazdan-site:current-center-development": "2026-06-05",
                "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center": "2026-06-30",
            },
        )

    def test_parent_nested_layouts_and_two_offline_replays_are_exact(self) -> None:
        self.assertNotEqual(core_v68.__file__, shim_v68.__file__)
        self.assertIs(core_v68.selected_inputs, shim_v68.selected_inputs)
        self.assertIs(core_v68.validate_open_seed_v68, shim_v68.validate_open_seed_v68)
        error = AssertionError("v68 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = shim_v68.validate_open_seed_v68(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 806)
        self.assertFalse(manifest["current_status_inferred"])
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core_v68.validate_open_seed_v68(DEFINITION, RELEASE, replay_count=1)

    def test_idempotency_order_and_publication_collision_fail_closed(self) -> None:
        first_rows, first_paths = core_v68.selected_inputs(self.base)
        second_rows, second_paths = core_v68.selected_inputs(self.base)
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first_paths, second_paths)
        guard = core_v68._guard_state()
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core_v68.build_open_seed_v68()
        self.assertEqual(core_v68._guard_state(), guard)
        self.assertFalse(core_v68.PUBLICATION_LOCK.exists())
        reversed_pins = dict(reversed(tuple(core_v68.ADDITION_PINS.items())))
        with patch.object(core_v68, "ADDITION_PINS", reversed_pins):
            with self.assertRaisesRegex(SystemExit, "canonical additions"):
                core_v68._validate_additions()
        duplicate = json.loads(json.dumps(self.base))
        duplicate["curated_inputs"][-1] = dict(duplicate["curated_inputs"][0])
        with self.assertRaisesRegex(SystemExit, "inventory is invalid"):
            core_v68.selected_inputs(duplicate)

    def test_release_tamper_and_symlinks_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="v68-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest hash"):
                core_v68.validate_open_seed_v68(
                    DEFINITION, copied, require_frozen=False
                )
        with tempfile.TemporaryDirectory(
            prefix="v68-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core_v68.validate_open_seed_v68(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
