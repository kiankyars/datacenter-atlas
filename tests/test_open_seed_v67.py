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


core_v67 = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v67")
shim_v67 = importlib.import_module("datacenter_atlas.open_seed_v67")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v66.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v66"

DEFINITION_PIN = (
    83_386,
    "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5",
)
MANIFEST_SHA256 = "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb"
TREE_SHA256 = "fb4a8016c3c0c143cef2e5ac35d0787bb2b0dbd45115e27a83a70167ccb0b4fb"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_512,
        "f1de28fbf7bbbf543e13750a25614bf411c6747cd17079807f0db575a4345c44",
    ),
    "README.md": (
        3_406,
        "3df2d2970c44494bbb2867ae08006ebb79ceb997eccd8b27fd2daf968f07a81b",
    ),
    "atlas.geojson": (
        2_771_678,
        "09e2d5b28883af85e7b74bd98ebaece53d0a4b79ad766d012b119fcc61007dc8",
    ),
    "capacity_estimates.csv": (
        250_435,
        "4c260acf2b631d9045d3ab6dddf19069b48854decdd92885425f0e18a224c611",
    ),
    "construction_pipeline.csv": (
        515_271,
        "c779947452aed97132ec466fba58e35d2f9b289d5f8ba37d829307ace31b215f",
    ),
    "construction_source_signals.csv": (
        328_594,
        "260a114c29a5078dd2e7e5918520a49e1cc3aa61e907b93ac3bedcc563341649",
    ),
    "entities.csv": (
        856_563,
        "e01c20f1d8b7f42a5da427c759b2edcaa1fc0bdac23c533ce97b82567e687f7c",
    ),
    "evidence.csv": (
        194_610,
        "4e3549c276aee889c43196b7e817bb7837500bfdf4bfca4377ae6a85491b3514",
    ),
    "lifecycle_freshness.csv": (
        132_795,
        "3f61073cf228aa6212a1b352a46d7203cbf9b6ba6a458796433afb52390a6027",
    ),
    "manifest.json": (12_274, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        5_943,
        "3cfeca874cc5f1ef6e8c2731c80bf8552b7b410f4c79b7103c5c5650d68c67f4",
    ),
    "resolution_candidates.json": (
        8_870,
        "97cecb13f9f7adba721b499d9f1247fb85786be02a0c005acf1809c02c29cdab",
    ),
    "source_inputs.json": (
        304_965,
        "3b675db6bacedccf26330fbf7dd8c14c45ce2302fc4d044b556dcb4b2fe054c2",
    ),
    "summary.json": (
        3_104,
        "8ccbc19892c967e1b1bd9c4f32e51b09ac63bcb14d337fd52c6fd8776d50203b",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_v67.py": (
        53_678,
        "3bdba3404182bed32f5491826d027344d2b9d4cea01ef9670cb8ffa44bc67259",
    ),
    ROOT / "open_seed_v67.py": (
        138,
        "94e5ae0f391351d47bd63a2a6246c1e4d8af92689b98ac505764515ed8269ff2",
    ),
    ROOT / "scripts/build_open_seed_v67.py": (
        363,
        "9278c79ac3a2e8ddd63a4ba0bb2a72f8a897bc58ecd83fc305c65b7a35655fdb",
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


class OpenSeedV67Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.selected_rows, selected_paths = core_v67.selected_inputs(cls.base)
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v67-test-db-")
        cls.connection = core_v67._build_database(
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
            for relative in core_v67.ADDITION_PINS
        }

    def test_frozen_hashes_modes_tree_and_code_are_exact(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, DEFINITION_PIN[0])
        self.assertEqual(sha256(DEFINITION), DEFINITION_PIN[1])
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(core_v67.tree_digest(RELEASE), TREE_SHA256)
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
        self.assertEqual(sha256(BASE_DEFINITION), core_v67.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core_v67.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core_v67.tree_digest(BASE_RELEASE), core_v67.BASE_TREE_SHA256)

    def test_exact_v66_plus_fourteen_selection_and_source_pins(self) -> None:
        before = {row["path"]: row["sha256"] for row in self.base["curated_inputs"]}
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        self.assertEqual((len(before), len(after)), (364, 378))
        self.assertFalse(set(before) - set(after))
        self.assertEqual(set(after) - set(before), set(core_v67.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        for relative, (size, digest) in core_v67.ADDITION_PINS.items():
            source = ROOT / relative
            with self.subTest(source=relative):
                self.assertEqual(source.stat().st_size, size)
                self.assertEqual(sha256(source), digest)
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                self.assertNotIn("2026-07-21", relative)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-21", "recorded_at": "2026-07-21T07:30:00Z"},
        )
        self.assertGreater(
            datetime.fromisoformat(self.definition["build"]["recorded_at"]),
            datetime.fromisoformat(self.base["build"]["recorded_at"]),
        )
        self.assertEqual(
            self.definition["epoch_capture"], self.base["epoch_capture"]
        )
        self.assertEqual(core_v67.EPOCH_AS_OF, "2026-07-20")
        pure_dc = (
            "sources/curated-official-2026-07-21-pure-dc-ams01-"
            "amsterdam-westpoort-current-build.json"
        )
        self.assertNotIn(pure_dc, after)

    def test_stt_is_the_only_freshness_policy_transition(self) -> None:
        before = self.base["freshness_contract"]
        after = self.definition["freshness_contract"]
        self.assertEqual(set(before), set(after))
        unchanged = set(before) - {
            "historical_inputs_included_as_last_observed",
            "stale_inputs_excluded",
        }
        for key in unchanged:
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(
            set(after["historical_inputs_included_as_last_observed"])
            - set(before["historical_inputs_included_as_last_observed"]),
            {core_v67.STT_JOHOR_SOURCE},
        )
        self.assertFalse(
            set(before["historical_inputs_included_as_last_observed"])
            - set(after["historical_inputs_included_as_last_observed"])
        )
        self.assertEqual(
            set(before["stale_inputs_excluded"])
            - set(after["stale_inputs_excluded"]),
            {core_v67.STT_JOHOR_SOURCE},
        )
        self.assertFalse(set(after["stale_inputs_excluded"]))
        self.assertEqual(
            after["next_local_day_inputs_pending"],
            before["next_local_day_inputs_pending"],
        )

    def test_source_semantics_and_evidence_dedup_are_exact(self) -> None:
        core_v67._validate_additions()
        documents = self._addition_documents()
        self.assertEqual(len(documents), 14)
        evidence: dict[str, list[dict[str, object]]] = {}
        entity_keys: set[str] = set()
        coordinate_keys: set[str] = set()
        occurrences = 0
        for relative, document in documents.items():
            self.assertEqual(document["schema_version"], "1.1")
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("captured-2026-07-21", text)
            for record in document["evidence"]:
                occurrences += 1
                evidence.setdefault(record["key"], []).append(record)
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                entity_keys.add(entity["stable_key"])
                if entity["coordinates"] is not None:
                    coordinate_keys.add(entity["stable_key"])
        self.assertEqual(occurrences, 36)
        self.assertEqual(len(evidence), 32)
        self.assertEqual(entity_keys, core_v67.ADDED_ENTITY_KEYS)
        self.assertEqual(coordinate_keys, core_v67.SYD06_COORDINATE_KEYS)
        self.assertEqual(
            {key: len(value) for key, value in evidence.items() if len(value) > 1},
            core_v67.SHARED_EVIDENCE_COUNTS,
        )
        for records in evidence.values():
            self.assertTrue(all(record == records[0] for record in records[1:]))

    def test_database_delta_and_prior_semantics_are_exact(self) -> None:
        core_v67._validate_database_contract(self.connection)
        core_v67._validate_prior_semantics(self.connection, self.base)
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
                "entities": 783,
                "evidence": 615,
                "lifecycle_observations": 459,
                "capacity_estimates": 522,
                "entity_snapshots": 803,
                "operating_model_observations": 56,
                "workload_observations": 128,
            },
        )

    def test_workloads_and_conflicting_metrics_remain_bounded(self) -> None:
        keys = tuple(sorted(core_v67.ADDED_ENTITY_KEYS))
        placeholders = ",".join("?" for _ in keys)
        workload_rows = self.connection.execute(
            f"""
            SELECT entities.stable_key, workload, as_of_date, method
            FROM workload_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        ).fetchall()
        self.assertEqual({tuple(row) for row in workload_rows}, core_v67.WORKLOAD_CONTRACT)
        capacity_rows = self.connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, base, as_of_date
            FROM capacity_estimates JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            keys,
        ).fetchall()
        self.assertEqual({tuple(row) for row in capacity_rows}, core_v67.CAPACITY_CONTRACT)
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
        documents = self._addition_documents()
        workload_documents = [
            document for document in documents.values() if document["workloads"]
        ]
        self.assertEqual(len(workload_documents), 2)
        guards = [
            record["metadata"]["workload_guardrail"]
            for document in workload_documents
            for record in document["evidence"]
            if "workload_guardrail" in record["metadata"]
        ]
        self.assertEqual(len(guards), 2)
        for guard in guards:
            for phrase in (
                "intended",
                "current runtime",
                "tenant or customer",
                "installed accelerator hardware",
                "utilization",
                "operational load",
                "training or inference workload",
            ):
                self.assertIn(phrase, guard)
        added_entities = [
            row
            for row in rows(RELEASE / "entities.csv")
            if row["stable_key"] in core_v67.ADDED_ENTITY_KEYS
        ]
        self.assertEqual(len(added_entities), 28)
        self.assertTrue(
            all(not row["users"] and not row["tenants"] and not row["customers"] for row in added_entities)
        )

    def test_public_csv_deltas_and_resolution_advisories_are_exact(self) -> None:
        core_v67._validate_release_delta(RELEASE)
        for filename, expected in core_v67.CSV_DELTA_CONTRACT.items():
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
        before_entities = {
            row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")
        }
        after_entities = {
            row["stable_key"]: row for row in rows(RELEASE / "entities.csv")
        }
        self.assertEqual(set(after_entities) - set(before_entities), core_v67.ADDED_ENTITY_KEYS)
        self.assertTrue(
            all(before_entities[key] == after_entities[key] for key in before_entities)
        )
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
            )

    def test_freshness_is_historical_unknown_and_advances_once(self) -> None:
        core_v67._validate_release_facts(RELEASE)
        before = {
            row["stable_key"]: row
            for row in rows(BASE_RELEASE / "lifecycle_freshness.csv")
        }
        after = {
            row["stable_key"]: row
            for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual(len(after), 443)
        self.assertEqual(set(after) - set(before), set(core_v67.LIFECYCLE_WINNERS))
        transitions = {}
        for key, old in before.items():
            new = after[key]
            self.assertEqual(
                int(new["observation_age_days"]),
                int(old["observation_age_days"]) + 1,
            )
            for field in old:
                if field not in {"observation_age_days", "freshness_class"}:
                    self.assertEqual(new[field], old[field])
            if new["freshness_class"] != old["freshness_class"]:
                transitions[key] = (old["freshness_class"], new["freshness_class"])
        self.assertEqual(transitions, core_v67.FRESHNESS_CLASS_TRANSITION)
        self.assertTrue(
            all(
                row["status_semantics"] == "last_observed"
                and row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in after.values()
            )
        )
        stt = after["curated:stt-johor-data-centre-campus:stt-johor-1"]
        self.assertEqual(stt["last_observed_status_as_of"], "2025-02-24")
        self.assertEqual(stt["observation_age_days"], "512")
        self.assertEqual(stt["freshness_class"], "stale_over_365_days")
        alps = after["curated:alps-middle-east-duqm-data-center:initial-80mw-build"]
        self.assertEqual(alps["observation_age_days"], "0")
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertFalse(manifest["current_status_inferred"])

    def test_both_import_layouts_and_double_offline_replay_are_exact(self) -> None:
        self.assertNotEqual(core_v67.__file__, shim_v67.__file__)
        self.assertIs(core_v67.selected_inputs, shim_v67.selected_inputs)
        self.assertIs(core_v67.validate_open_seed_v67, shim_v67.validate_open_seed_v67)
        error = AssertionError("v67 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = shim_v67.validate_open_seed_v67(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 783)
        self.assertFalse(manifest["current_status_inferred"])
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core_v67.validate_open_seed_v67(DEFINITION, RELEASE, replay_count=1)

    def test_collision_tamper_symlink_and_prior_mutation_fail_closed(self) -> None:
        guard = core_v67._guard_state()
        definition_hash = sha256(DEFINITION)
        release_tree = core_v67.tree_digest(RELEASE)
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core_v67.build_open_seed_v67()
        self.assertEqual(core_v67._guard_state(), guard)
        self.assertEqual(sha256(DEFINITION), definition_hash)
        self.assertEqual(core_v67.tree_digest(RELEASE), release_tree)
        self.assertFalse(core_v67.PUBLICATION_LOCK.exists())

        with tempfile.TemporaryDirectory(
            prefix="v67-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest hash"):
                core_v67.validate_open_seed_v67(
                    DEFINITION, copied, require_frozen=False
                )

        with tempfile.TemporaryDirectory(
            prefix="v67-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core_v67.validate_open_seed_v67(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
