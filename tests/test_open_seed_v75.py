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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v75")
shim = importlib.import_module("datacenter_atlas.open_seed_v75")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v75.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v75"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v74.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v74"
BUILDER = ROOT / "scripts/build_open_seed_v75.py"
RECORDED_AT = "2026-07-21T16:04:11Z"

DEFINITION_PIN = (
    89_129,
    "69faaee57c8e4d889d91bfcb5513141d7e19d1377b77d913ee8aa8d29189383f",
)
MANIFEST_PIN = (
    13_106,
    "7f121051b6af6c82a1c48011e7c471153b5047dd428addd7662dccb0c3a232de",
)
TREE_PIN = "bcc09e206798788d780b4cea2166aa91631f901bc970681f7f505f2282318c5d"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_238,
        "3795ea3d541c0bdbbf7830738a235ae23a3215c39804b289254c47ac669ac660",
    ),
    "README.md": (
        3_800,
        "4745db78647ae03945b894a7559386924442aa2369d60e94d58cf7441e52668b",
    ),
    "atlas.geojson": (
        2_905_408,
        "973cf7d1b8202b86baec758b348f4572fe7813ab70ab305757ea7a81a4a686d0",
    ),
    "capacity_estimates.csv": (
        257_212,
        "1fa99c1592e79966a2c9e823ec2ea9f5000e45a674471864bf2ad06331118cb6",
    ),
    "construction_pipeline.csv": (
        539_077,
        "b7169c79305f3a9e19fcc2a79a8217888a937e80aad273b9713c18d509240727",
    ),
    "construction_source_signals.csv": (
        349_583,
        "05d964213cd5bb1960660ddbb10f539e3d740a897d8f3966d7659527fcd0df24",
    ),
    "entities.csv": (
        893_070,
        "67cb8222b76f9b5a2ace738b1dc0451d8d89b66ef6b6911acece485b37dffd0b",
    ),
    "evidence.csv": (
        208_562,
        "bc61a9251e645540820577a90af29e0a06b79babf66735cf493067795103c8eb",
    ),
    "lifecycle_freshness.csv": (
        139_236,
        "506f9b29e444ac392d1bb5536b7b1534fbba16d9ec70334850759278923847d7",
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
        328_904,
        "c11c8c7c5cb995dcca5c924b57ba870d9a805021b9baa6c33d53f255582aebdd",
    ),
    "summary.json": (
        3_234,
        "73751a25af2ed593337f6496a430164af25df03504a6570469ffe7e42959c16b",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV75Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v75-test-"
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
        error = AssertionError("open seed v75 attempted network access")
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

    def test_exact_v74_adjacency_appends_only_three_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 397)
        self.assertEqual(len(after), 400)
        self.assertEqual(after[:397], before)
        self.assertEqual(
            [row["path"] for row in after[397:]], sorted(core.ADDITION_PINS)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after}
        self.assertFalse(selected_paths & core.EXCLUDED_SOURCE_PATHS)
        self.assertFalse(any("odata-sp04" in path for path in selected_paths))
        self.assertFalse(any("syntys" in path for path in selected_paths))
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
        self.assertEqual(set(documents), set(core.ADDITION_PINS))
        self.assertEqual(
            sum(len(document["lifecycle"]) for document in documents.values()),
            3,
        )
        self.assertEqual(
            sum(
                len(document["operating_models"])
                for document in documents.values()
            ),
            1,
        )
        for document in documents.values():
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["workloads"], [])
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])
        nxdata = ROOT / next(iter(core.EXCLUDED_SOURCE_PATHS))
        self.assertEqual(
            (nxdata.stat().st_size, sha256(nxdata)),
            next(iter(core.EXCLUDED_SOURCE_PINS.values())),
        )

    def test_database_delta_is_exact_and_capacity_free(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 824,
            "evidence": 655,
            "entity_snapshots": 844,
            "lifecycle_observations": 482,
            "capacity_estimates": 535,
            "operating_model_observations": 60,
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
            0,
        )

    def test_public_append_only_delta_counts_and_guardrails(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        core._validate_release_facts(RELEASE, recorded_at=RECORDED_AT)
        for filename in (
            "capacity_estimates.csv",
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
        self.assertEqual(set(after) - set(before), core.ADDED_ENTITY_KEYS)
        self.assertTrue(all(after[key] == row for key, row in before.items()))
        summary = json.loads((RELEASE / "summary.json").read_text())
        self.assertEqual(summary["entities_total"], 824)
        self.assertEqual(summary["entities_with_coordinates"], 198)
        self.assertEqual(summary["campuses_with_coordinates"], 135)
        self.assertEqual(summary["capacity_estimates_current"], 534)
        self.assertEqual(summary["evidence_total"], 655)

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
            if "v75" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v75, shim.validate_open_seed_v75)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v75(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 824)
        with self.assertRaisesRegex(core.OpenSeedV75Error, "exactly two offline"):
            core.validate_open_seed_v75(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV75Error, "later than validation wall clock"
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
            core.OpenSeedV75Error, "later than validation wall clock"
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
