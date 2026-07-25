from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import csv
import hashlib
import importlib
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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v79")
shim = importlib.import_module("datacenter_atlas.open_seed_v79")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v79.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v79"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v78.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v78"
BUILDER = ROOT / "scripts/build_open_seed_v79.py"
RECORDED_AT = "2026-07-21T16:49:49Z"

DEFINITION_PIN = (
    94_039,
    "3a8cfb0d6ed9f858f5be3ac8cfda7502673241ede8f0aa23715714a09a7d462e",
)
MANIFEST_PIN = (
    13_885,
    "4eaceee00a0ed0e9073bc6cd19a8f82c97a442f05e773615ee1bb470a95a5c71",
)
TREE_PIN = "f5cfdebad04ccb8347cdf9cd965e88f096dc44699b938ecc111acc28348858a2"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_804,
        "6259c3f48c01b77bb7718acdc1a9896249274e7d4c5d0bbd69f1067591acbf0f",
    ),
    "README.md": (
        3_862,
        "ffc2412eff282ff73acc070b8f5b1a261c392f0af91108abcbb499c662931154",
    ),
    "atlas.geojson": (
        3_033_305,
        "5703a6ea2eb6bb76b2eaeb739ed090ce0edb27d465415ebd56f4ffff09c674a6",
    ),
    "capacity_estimates.csv": (
        258_741,
        "747b4b7e3e56eb102809e813cd68f398ea8b9f9eecb7da0e1e1c7e47b8a3d1a6",
    ),
    "construction_pipeline.csv": (
        556_258,
        "62827e97dad751edbcd1fce08e94217822fb60afad61f4b0ce7a182131f27edd",
    ),
    "construction_source_signals.csv": (
        371_666,
        "8d9c4bd3a2a733561d9ed64daa2741b93fbdcf8791439438802815d5c2a90dae",
    ),
    "entities.csv": (
        924_382,
        "33ba938178fcc6405f2ca44736cb9b3ba29139ef34a4adbf93e555c2b90ddd2f",
    ),
    "evidence.csv": (
        219_310,
        "0b24d0c603204ad8348564eefeef50fec21acea3a82413cafc9545239ae97aec",
    ),
    "lifecycle_freshness.csv": (
        146_134,
        "2306f5eea64841cae92284d6277ebb0e63384f0afb05aedfb40fbe78f4e6c794",
    ),
    "manifest.json": MANIFEST_PIN,
    "resolution_candidates.csv": (
        6_889,
        "b893812c703ea3bfe6beba6c56d121a2fab8f75e142313f7562bb92239564009",
    ),
    "resolution_candidates.json": (
        10_348,
        "948ea2d6989115e71f2d56cb827d430b8379b721e6a40872ed4f22665acf83f2",
    ),
    "source_inputs.json": (
        347_015,
        "a337bc0dc5903f43fc08123865f64db666e810e419a038bca18f829a1ce87a5b",
    ),
    "summary.json": (
        3_382,
        "363d8efc7fc53eddd6a5219e4586e31bbd2faece3f73bbe46ad853f2da1424ab",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV79Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v79-test-"
        )
        cls.connection = core._build_database(
            cls.base,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
            recorded_at=RECORDED_AT,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("open seed v79 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_frozen_definition_release_and_every_file_are_exact(self) -> None:
        self.assertEqual(
            (DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN
        )
        self.assertEqual(
            (
                (RELEASE / "manifest.json").stat().st_size,
                sha256(RELEASE / "manifest.json"),
            ),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(
            set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()}
        )
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, sha256(path)), expected)

    def test_exact_v78_adjacency_appends_only_two_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 419)
        self.assertEqual(len(after), 421)
        self.assertEqual(after[:419], before)
        self.assertEqual(
            [row["path"] for row in after[419:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[419:]}
        self.assertTrue(selected_paths.isdisjoint(core.EXCLUDED_SOURCE_PATHS))
        self.assertFalse(any("telcosub" in path for path in selected_paths))
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "freshness_contract",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(self.definition[key], self.base[key])
        self.assertEqual(set(self.definition), set(self.base))

    def test_official_artifact_and_claim_boundaries_are_exact(self) -> None:
        carrier = core._validate_official_artifact()
        self.assertEqual(
            carrier["manifest"]["recorded_at"], core.OFFICIAL_RECORDED_AT
        )
        self.assertEqual(
            core.v69.tree_digest(core.OFFICIAL_ARTIFACT),
            core.OFFICIAL_PHYSICAL_TREE_SHA256,
        )
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(tuple(documents), core.ADDITION_ORDER)
        self.assertEqual(
            sum(len(document["lifecycle"]) for document in documents.values()),
            2,
        )
        self.assertEqual(
            sum(
                len(document["operating_models"])
                for document in documents.values()
            ),
            0,
        )
        self.assertEqual(
            sum(len(document["capacities"]) for document in documents.values()),
            1,
        )
        hive = documents[core.ADDITION_ORDER[0]]
        puntonet = documents[core.ADDITION_ORDER[1]]
        self.assertEqual(hive["capacities"][0]["metric"], "grid_connection_mw")
        self.assertEqual(hive["capacities"][0]["stage"], "contracted")
        self.assertEqual(hive["capacities"][0]["base"], 100)
        self.assertEqual(hive["workloads"][0]["value"], "crypto_mining")
        self.assertEqual(puntonet["capacities"], [])
        self.assertEqual(puntonet["workloads"], [])
        for document in (hive, puntonet):
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])
        excluded_path = ROOT / next(iter(core.EXCLUDED_SOURCE_PATHS))
        excluded = json.loads(excluded_path.read_text())
        self.assertEqual(excluded["lifecycle"], [])

    def test_database_delta_is_exact_and_capacity_typed(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 866,
            "evidence": 690,
            "entity_snapshots": 886,
            "lifecycle_observations": 506,
            "capacity_estimates": 538,
            "operating_model_observations": 60,
            "workload_observations": 129,
        }
        self.assertEqual(
            {
                table: self.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in expected_counts
            },
            expected_counts,
        )
        self.assertEqual(
            set(core.v70._evidence_by_key(self.connection))
            & core.ADDED_EVIDENCE_KEYS,
            core.ADDED_EVIDENCE_KEYS,
        )
        placeholders = ",".join("?" for _ in core.ADDED_ENTITY_KEYS)
        keys = tuple(sorted(core.ADDED_ENTITY_KEYS))
        self.assertEqual(
            self.connection.execute(
                f"SELECT COUNT(*) FROM capacity_estimates WHERE entity_id IN "
                f"(SELECT id FROM entities WHERE stable_key IN ({placeholders}))",
                keys,
            ).fetchone()[0],
            1,
        )

    def test_public_append_only_delta_counts_and_guardrails(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        core._validate_release_facts(RELEASE, recorded_at=RECORDED_AT)
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
            )
        before = {
            row["stable_key"]: row
            for row in csv_rows(BASE_RELEASE / "entities.csv")
        }
        after = {
            row["stable_key"]: row for row in csv_rows(RELEASE / "entities.csv")
        }
        self.assertEqual(set(after) - set(before), core.ADDED_ENTITY_KEYS)
        self.assertTrue(all(after[key] == row for key, row in before.items()))
        summary = json.loads((RELEASE / "summary.json").read_text())
        self.assertEqual(summary["entities_total"], 866)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 537)
        self.assertEqual(summary["evidence_total"], 690)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 554)

    def test_publication_time_contract_and_no_private_stage_or_lock(self) -> None:
        target = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(target, datetime.now(UTC))
        for path in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            with self.subTest(path=path.name):
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_birthtime, UTC), target
                )
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_mtime, UTC), target
                )
        self.assertGreaterEqual(
            datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), target
        )
        self.assertGreaterEqual(
            datetime.fromtimestamp(RELEASE.stat().st_ctime, UTC), target
        )
        core._validate_publication_times(
            DEFINITION, RELEASE, recorded_at=RECORDED_AT, require_live=True
        )
        leftovers = [
            path.name
            for parent in (ROOT / "sources", ROOT / "releases", ROOT)
            for path in parent.iterdir()
            if "v79" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v79-collision-") as td:
            root = Path(td)
            source = root / "source"
            destination = root / "destination"
            source.write_text("source")
            destination.write_text("destination")
            with self.assertRaisesRegex(SystemExit, "late output collision"):
                core.v69.promote_noreplace(source, destination)
            self.assertEqual(source.read_text(), "source")
            self.assertEqual(destination.read_text(), "destination")

            final_release = root / "release"
            rollback_stage = root / "release.stage"
            final_release.mkdir()
            (final_release / "member").write_text("frozen")
            identity = core._path_identity(final_release, directory=True)
            with patch.object(core, "RELEASE", final_release):
                core._rollback_release(identity, rollback_stage)
            self.assertFalse(final_release.exists())
            self.assertEqual((rollback_stage / "member").read_text(), "frozen")

            core.v69.promote_noreplace(rollback_stage, final_release)
            displaced = root / "displaced"
            final_release.rename(displaced)
            final_release.mkdir()
            with patch.object(core, "RELEASE", final_release):
                with self.assertRaisesRegex(
                    core.OpenSeedV79Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v79, shim.validate_open_seed_v79)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v79(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 866)
        with self.assertRaisesRegex(core.OpenSeedV79Error, "exactly two offline"):
            core.validate_open_seed_v79(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV79Error, "later than validation wall clock"
        ):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-22T00:00:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 23, 59, 59, tzinfo=UTC
                ),
            )
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")
        self.assertEqual(core._guard_state(), guard)
        self.assertEqual(
            (BASE_DEFINITION.stat().st_size, sha256(BASE_DEFINITION)),
            core.BASE_DEFINITION_PIN,
        )
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)
        with self.assertRaisesRegex(
            core.OpenSeedV79Error, "later than validation wall clock"
        ):
            core._validate_definition(
                self.definition,
                self.base,
                validation_wall_clock=(
                    datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
                    - timedelta(seconds=1)
                ),
            )


if __name__ == "__main__":
    unittest.main()
