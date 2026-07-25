from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v72")
shim = importlib.import_module("datacenter_atlas.open_seed_v72")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v72.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v72"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
BUILDER = ROOT / "scripts/build_open_seed_v72.py"
RECORDED_AT = "2026-07-21T13:06:15Z"

DEFINITION_PIN = (
    87_104,
    "33fa28074d38ad00810be9717fac2a12ac04b68c9309254ce8bc5bdfc32b7c2a",
)
MANIFEST_PIN = (
    12_667,
    "114b79b4ce95457ec772a5d96d0fb385433b15e8ccd7668a9289aede2cad1801",
)
TREE_PIN = "0cbd0a804cf7085a09a55cc9a6d83d78470d4b4ccfd12f3e3dbbb69ba09303e3"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_866,
        "8d220a53476e5692df1513dc05a44e028603f5bdb7ec0ab92c4d32f1efed2735",
    ),
    "README.md": (
        3_947,
        "31c8441b7b313d1c9558615c451207ac69fa3794e7017263aad9a7a7cfabf0c8",
    ),
    "atlas.geojson": (
        2_859_663,
        "0b8bc1b3793bf3b8b176ef77e4054d046a9c0b382af683402c862109858a157f",
    ),
    "capacity_estimates.csv": (
        256_289,
        "a517f58ceae4c8232fab6b9135e02f8096b2fa2cda3f77b053072adb78866729",
    ),
    "construction_pipeline.csv": (
        531_587,
        "4419f48b31813cac4a0c66dd3fd43f32aba0a8bca1be487d711d5d27b5c5d515",
    ),
    "construction_source_signals.csv": (
        342_224,
        "fb60d6c31c6db43dbf0f3af31be553cb9993ac71772a57010b11ce4db46ba401",
    ),
    "entities.csv": (
        880_060,
        "17e9edc7d4634303a7553ea753887773aabdcbfd1751a11bd52883bb3bcb4d11",
    ),
    "evidence.csv": (
        202_484,
        "cfd61b8725216f1215e0458b8076301a6114edb72508ed37812a34cf68109d4e",
    ),
    "lifecycle_freshness.csv": (
        137_020,
        "d3d035b9a24c6100b4a7363b76de3d77fc6b88041fe524c705f1f9c330192d37",
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
        318_957,
        "cdc659428b03c321e247bcc9df1ef6e24ba3b55da3093a2ae5f5edd3bf679370",
    ),
    "summary.json": (
        3_201,
        "e9caaaafdde402c797f74f86fe4ab8acb4f06584ebb5bcd4141b780f1498ba1d",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OpenSeedV72Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v72-test-")
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
        error = AssertionError("open seed v72 attempted network access")
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
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(
            ((RELEASE / "manifest.json").stat().st_size, sha256(RELEASE / "manifest.json")),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, sha256(path)), expected)

    def test_exact_v71_adjacency_replaces_two_rows_in_place(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 393)
        self.assertEqual(len(after), 393)
        self.assertEqual(self.definition["curated_inputs"], after)
        before_paths = [row["path"] for row in before]
        after_paths = [row["path"] for row in after]
        positions = set()
        for replacement in core.REPLACEMENTS:
            position = before_paths.index(replacement.predecessor_path)
            positions.add(position)
            self.assertEqual(after_paths[position], replacement.successor_path)
            self.assertEqual(after[position]["sha256"], replacement.successor_sha256)
            self.assertNotIn(replacement.predecessor_path, after_paths)
        self.assertEqual(len(positions), 2)
        for index, row in enumerate(before):
            if index not in positions:
                self.assertEqual(after[index], row)
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
        self.assertEqual(self.definition["release_id"], core.RELEASE_ID)
        self.assertEqual(self.definition["build"]["recorded_at"], RECORDED_AT)

    def test_coordinate_v4_is_exact_lineage_and_exclusions_stay_unselected(self) -> None:
        manifest = core._validate_coordinate_artifact()
        self.assertEqual(manifest["recorded_at"], core.COORDINATE_RECORDED_AT)
        self.assertEqual(
            sha256(core.COORDINATE_ARTIFACT / "manifest.json"),
            core.COORDINATE_MANIFEST_SHA256,
        )
        self.assertEqual(
            core.v69.tree_digest(core.COORDINATE_ARTIFACT),
            core.COORDINATE_PHYSICAL_TREE_SHA256,
        )
        disposition = json.loads(
            (core.COORDINATE_ARTIFACT / "disposition.json").read_text()
        )
        self.assertEqual(disposition["review_only"]["project_rows"], 18)
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        successor_paths = {replacement.successor_path for replacement in core.REPLACEMENTS}
        self.assertEqual(
            successor_paths,
            {row["path"] for row in self.selected if "coordinate-v4" in row["path"]},
        )
        self.assertFalse(any("openstreetmap" in path.casefold() for path in successor_paths))
        self.assertFalse(any("ld14" in path.casefold() for path in successor_paths))

    def test_database_delta_is_two_evidence_and_three_locations_only(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            )
        }
        self.assertEqual(
            counts,
            {
                "entities": 810,
                "evidence": 636,
                "entity_snapshots": 830,
                "lifecycle_observations": 474,
                "capacity_estimates": 533,
                "operating_model_observations": 56,
                "workload_observations": 128,
            },
        )
        located = {
            row[0]: (row[1], row[2])
            for row in self.connection.execute(
                """
                SELECT entities.stable_key, latitude, longitude
                FROM entity_snapshots JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN (?, ?, ?)
                """,
                tuple(sorted(core.COORDINATE_CONTRACT)),
            )
        }
        self.assertEqual(set(located), set(core.COORDINATE_CONTRACT))
        for stable_key, contract in core.COORDINATE_CONTRACT.items():
            self.assertEqual(
                located[stable_key],
                (contract["latitude"], contract["longitude"]),
            )

    def test_public_delta_counts_resolution_and_current_status_guardrails(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        summary = json.loads((RELEASE / "summary.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(
            {
                "entities": summary["entities_total"],
                "database_evidence": summary["evidence_total"],
                "exported_evidence": manifest["evidence_records"],
                "located_entities": summary["entities_with_coordinates"],
                "located_campuses": summary["campuses_with_coordinates"],
                "capacity": manifest["capacity_estimates"],
                "pipeline": manifest["construction_pipeline_records"],
                "signals": manifest["construction_source_signals"],
                "freshness": manifest["lifecycle_freshness_records"],
                "resolution": manifest["resolution_candidates"],
            },
            {
                "entities": 810,
                "database_evidence": 636,
                "exported_evidence": 514,
                "located_entities": 192,
                "located_campuses": 132,
                "capacity": 532,
                "pipeline": 416,
                "signals": 318,
                "freshness": 458,
                "resolution": 7,
            },
        )
        freshness = (RELEASE / "lifecycle_freshness.csv").read_text()
        self.assertNotIn(",true,", freshness)
        self.assertIn("current_status_classification", freshness.splitlines()[0])
        candidates = json.loads((RELEASE / "resolution_candidates.json").read_text())
        added = [
            row
            for row in candidates
            if {row["left_name"], row["right_name"]}
            == {
                "NEXTDC S4 Sydney Data Center Campus",
                "Microsoft Kemps Creek Data Centre",
            }
        ]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["relationship_suggestion"], "nearby_only")

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
        self.assertGreaterEqual(datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), target)
        self.assertGreaterEqual(datetime.fromtimestamp(RELEASE.stat().st_ctime, UTC), target)
        core._validate_publication_times(
            DEFINITION,
            RELEASE,
            recorded_at=RECORDED_AT,
            require_live=True,
        )
        leftovers = [
            path.name
            for parent in (ROOT / "sources", ROOT / "releases", ROOT)
            for path in parent.iterdir()
            if "v72" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_and_idempotent_builder(self) -> None:
        self.assertIs(core.validate_open_seed_v72, shim.validate_open_seed_v72)
        with self._network_guard():
            manifest = shim.validate_open_seed_v72(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 810)
        with self.assertRaisesRegex(core.OpenSeedV72Error, "exactly two offline"):
            core.validate_open_seed_v72(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV72Error, "later than validation wall clock"
        ):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-22T00:00:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 23, 59, 59, tzinfo=UTC
                ),
            )
        guard = core._guard_state()
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

    def test_accepted_v71_base_remains_byte_exact(self) -> None:
        self.assertEqual(
            (BASE_DEFINITION.stat().st_size, sha256(BASE_DEFINITION)),
            (core.BASE_DEFINITION_BYTES, core.BASE_DEFINITION_SHA256),
        )
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BASE_DEFINITION.stat().st_mode), 0o644)
        with self.assertRaisesRegex(
            core.OpenSeedV72Error, "later than validation wall clock"
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
