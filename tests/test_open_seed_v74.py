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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v74")
shim = importlib.import_module("datacenter_atlas.open_seed_v74")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v74.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v74"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
BUILDER = ROOT / "scripts/build_open_seed_v74.py"
RECORDED_AT = "2026-07-21T15:54:52Z"

DEFINITION_PIN = (
    88_404,
    "92b2d0e0b403e43d8e68ac022891affb58aa12718fe90a59b6bf078adc4d8401",
)
MANIFEST_PIN = (
    12_950,
    "7167225f3d530ea404a8334d63c18e037364e38d22cfef49773129e81cbeba56",
)
TREE_PIN = "bbfcfa4bf24f1292332646422174077de038bf4d274004ecaa7c689f453d6a59"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_121,
        "263210b409de95498fc7bf5e71a95637b15faae9f87128419b29e536a5c1ab96",
    ),
    "README.md": (
        3_933,
        "2caccc7f73504386cf16e2546689285ec22955bec5cbe9aef81e5674105ada50",
    ),
    "atlas.geojson": (
        2_886_687,
        "1f20ed76949ccb5e5973e61828d02ba38d31b317910cc4140b5f74c8aacb3545",
    ),
    "capacity_estimates.csv": (
        257_212,
        "1fa99c1592e79966a2c9e823ec2ea9f5000e45a674471864bf2ad06331118cb6",
    ),
    "construction_pipeline.csv": (
        536_325,
        "8b0e3a38dd1646a044d4636d5126e85fa20a83efb878cb42c908e8f03312d2b2",
    ),
    "construction_source_signals.csv": (
        346_376,
        "55418354fab74d8ca92b603734b7e6a33f0b6a732b7c16070f20a652509da552",
    ),
    "entities.csv": (
        888_035,
        "f65c7e7b0dff20005b9fe5ed3fdb2af643ea1eed181eb96b17d4d9c46717c6a1",
    ),
    "evidence.csv": (
        206_304,
        "59d9f604a7de43d8ab71aa9955ea03555f66b0b80a008a85203d8cdb679a19e5",
    ),
    "lifecycle_freshness.csv": (
        138_270,
        "b286292746c17cea1f8794373fde599f4c2ff9ce1a728440d701da490b311770",
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
        325_368,
        "ffb732de6fcd0533d6e5fe3a2c896c5573f8decccd06f13467cfad150287ea3d",
    ),
    "summary.json": (
        3_234,
        "a628ff25c4361ea206fc160ff04f0952cff5c87fcfe0b5d9cdfb4b23c80e68e3",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV74Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v74-test-"
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
        error = AssertionError("open seed v74 attempted network access")
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

    def test_exact_v73_adjacency_replaces_only_three_inputs_in_place(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 397)
        self.assertEqual(len(after), 397)
        changed = [
            (index, old, new)
            for index, (old, new) in enumerate(zip(before, after, strict=True))
            if old != new
        ]
        self.assertEqual(len(changed), 3)
        self.assertEqual(
            {old["path"] for _, old, _ in changed},
            {row.predecessor_path for row in core.REPLACEMENTS},
        )
        self.assertEqual(
            {new["path"] for _, _, new in changed},
            {row.successor_path for row in core.REPLACEMENTS},
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        bichuten_index = next(
            index
            for index, row in enumerate(before)
            if row["path"] == core.BICHUTEN_PATH
        )
        self.assertEqual(after[bichuten_index], before[bichuten_index])
        self.assertEqual(
            (
                (ROOT / core.BICHUTEN_PATH).stat().st_size,
                sha256(ROOT / core.BICHUTEN_PATH),
            ),
            core.BICHUTEN_PIN,
        )
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

    def test_coordinate_v5_artifact_and_successors_are_exactly_bounded(self) -> None:
        manifest = core._validate_coordinate_artifact()
        self.assertEqual(manifest["recorded_at"], core.COORDINATE_RECORDED_AT)
        self.assertEqual(
            manifest["tree_sha256"], core.COORDINATE_MANIFEST_TREE_SHA256
        )
        self.assertEqual(
            core.v69.tree_digest(core.COORDINATE_ARTIFACT),
            core.COORDINATE_PHYSICAL_TREE_SHA256,
        )
        for replacement in core.REPLACEMENTS:
            predecessor = json.loads(
                (ROOT / replacement.predecessor_path).read_text()
            )
            successor = json.loads((ROOT / replacement.successor_path).read_text())
            core._validate_successor(predecessor, successor, replacement)
            self.assertEqual(
                (
                    (ROOT / replacement.successor_path).stat().st_size,
                    sha256(ROOT / replacement.successor_path),
                ),
                (replacement.successor_bytes, replacement.successor_sha256),
            )
            self.assertEqual(successor["lifecycle"], predecessor["lifecycle"])
            self.assertEqual(successor["capacities"], predecessor["capacities"])
            self.assertEqual(successor["workloads"], predecessor["workloads"])

    def test_database_delta_is_six_locations_and_three_evidence_only(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 818,
            "evidence": 646,
            "entity_snapshots": 838,
            "lifecycle_observations": 479,
            "capacity_estimates": 535,
            "operating_model_observations": 59,
            "workload_observations": 128,
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
        located = {
            row[0]
            for row in self.connection.execute(
                """
                SELECT entities.stable_key
                FROM entity_snapshots
                JOIN entities ON entities.id = entity_id
                WHERE latitude IS NOT NULL
                  AND entities.stable_key IN ({})
                """.format(
                    ",".join("?" for _ in core.COORDINATE_CONTRACT)
                ),
                tuple(sorted(core.COORDINATE_CONTRACT)),
            )
        }
        self.assertEqual(located, set(core.COORDINATE_CONTRACT))
        self.assertEqual(
            set(core.v70._evidence_by_key(self.connection))
            & core.NEW_EVIDENCE_KEYS,
            core.NEW_EVIDENCE_KEYS,
        )

    def test_public_delta_changes_only_coordinate_carriers(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        for filename in (
            "capacity_estimates.csv",
            "lifecycle_freshness.csv",
            "resolution_candidates.csv",
            "resolution_candidates.json",
        ):
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
        changed = {
            key
            for key in before
            if before[key] != after[key]
        }
        self.assertEqual(changed, set(core.COORDINATE_CONTRACT))
        for key in changed:
            for field in (
                "status",
                "status_as_of",
                "status_method",
                "capacity_estimates_json",
                "workloads_json",
                "operating_model",
            ):
                self.assertEqual(after[key][field], before[key][field])
        summary = json.loads((RELEASE / "summary.json").read_text())
        self.assertEqual(summary["entities_with_coordinates"], 198)
        self.assertEqual(summary["campuses_with_coordinates"], 135)
        self.assertEqual(summary["evidence_total"], 646)

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
            if "v74" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_idempotence_and_predecessor_nonmutation(
        self,
    ) -> None:
        self.assertIs(core.validate_open_seed_v74, shim.validate_open_seed_v74)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v74(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 818)
        with self.assertRaisesRegex(core.OpenSeedV74Error, "exactly two offline"):
            core.validate_open_seed_v74(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV74Error, "later than validation wall clock"
        ):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-22T00:00:00Z",
                validation_wall_clock=datetime.now(UTC),
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
            (core.BASE_DEFINITION_BYTES, core.BASE_DEFINITION_SHA256),
        )
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)
        with self.assertRaisesRegex(
            core.OpenSeedV74Error, "later than validation wall clock"
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
