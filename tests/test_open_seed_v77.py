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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v77")
shim = importlib.import_module("datacenter_atlas.open_seed_v77")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v77.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v77"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v76.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v76"
BUILDER = ROOT / "scripts/build_open_seed_v77.py"
RECORDED_AT = "2026-07-21T16:25:22Z"

DEFINITION_PIN = (
    92_782,
    "7f228fc5b4cfd0beb2655519ffc28ac7a12d6185b81c61db3ef21ad9e6dce00a",
)
MANIFEST_PIN = (
    13_615,
    "a35f3c064aabda5598d336cda264e4b798a516afe96331074f51d33fada4b7bb",
)
TREE_PIN = "7eebe5bb4f83c40cdc1f113fa6dc8f5e71337aee02818565e2d276f307c160ce"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_628,
        "a5bc74485ad1230551e243beec83d0086effe7cd15454f7c24448db0e6aeb528",
    ),
    "README.md": (
        3_888,
        "f69c3a31df6e3d06e0ffa7f24c9e9eaca296da7eba9b7a438ace7eb718449190",
    ),
    "atlas.geojson": (
        3_001_448,
        "8a4e44f15566e4c36841b8379ac76d16f31f2bf4430cb52cb1ecd443b8cc27b2",
    ),
    "capacity_estimates.csv": (
        257_212,
        "1fa99c1592e79966a2c9e823ec2ea9f5000e45a674471864bf2ad06331118cb6",
    ),
    "construction_pipeline.csv": (
        551_632,
        "e1ba4ad679485ca43ccb0e0092fee76321d1b3538e4766d3fe55c9b13dbe31d2",
    ),
    "construction_source_signals.csv": (
        366_402,
        "a2de268007895167bc87da52fd21e80b5de996c5f4fdf8c8a8f54c482c7dcf43",
    ),
    "entities.csv": (
        916_052,
        "521263d704ff5d424c78e13fccb524838e8743cc0497ea74c2f1abbabd701dc4",
    ),
    "evidence.csv": (
        215_770,
        "1bc0ed5bcbbe967fd593eab8363f0a8a67924ec4a6673826fb6ee03b6103a397",
    ),
    "lifecycle_freshness.csv": (
        144_550,
        "1fee25fbb728d5e2a37addeab50e05da53ead928e927677907c78a1475320df4",
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
        340_801,
        "890aadf8b1355b9af5b0f570dac8a6700350128e46dd02b3ba2724ee446eb76f",
    ),
    "summary.json": (
        3_324,
        "2ced083e4d3584f34398f88ad8d13d400be478a7ae36fc73b659f225a72e7b26",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV77Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v77-test-"
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
        error = AssertionError("open seed v77 attempted network access")
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

    def test_exact_v76_adjacency_appends_only_ten_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 406)
        self.assertEqual(len(after), 416)
        self.assertEqual(after[:406], before)
        self.assertEqual(
            [row["path"] for row in after[406:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after}
        self.assertFalse(any("changle" in path for path in selected_paths))
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
            11,
        )
        self.assertEqual(
            sum(
                len(document["operating_models"])
                for document in documents.values()
            ),
            0,
        )
        for document in documents.values():
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["workloads"], [])
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])
        guizhou = documents[core.ADDITION_ORDER[1]]
        self.assertEqual(
            guizhou["campus"]["stable_key"],
            "curated:china-telecom-cloud-computing-guizhou-information-park",
        )
        self.assertIn(
            "governed solely by the direct CSCEC body",
            guizhou["evidence"][0]["metadata"]["china_telecom_capture_scope"],
        )

    def test_database_delta_is_exact_and_capacity_free(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 856,
            "evidence": 677,
            "entity_snapshots": 876,
            "lifecycle_observations": 501,
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
        self.assertEqual(summary["entities_total"], 856)
        self.assertEqual(summary["entities_with_coordinates"], 198)
        self.assertEqual(summary["campuses_with_coordinates"], 135)
        self.assertEqual(summary["capacity_estimates_current"], 534)
        self.assertEqual(summary["evidence_total"], 677)

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
            if "v77" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v77, shim.validate_open_seed_v77)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v77(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 856)
        with self.assertRaisesRegex(core.OpenSeedV77Error, "exactly two offline"):
            core.validate_open_seed_v77(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV77Error, "later than validation wall clock"
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
            core.OpenSeedV77Error, "later than validation wall clock"
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
