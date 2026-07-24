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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v76")
shim = importlib.import_module("datacenter_atlas.open_seed_v76")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v76.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v76"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v75.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v75"
BUILDER = ROOT / "scripts/build_open_seed_v76.py"
RECORDED_AT = "2026-07-21T16:17:09Z"

DEFINITION_PIN = (
    90_539,
    "2b6169aab475acd240025894bc0b46307e2c4bb1c041e9a1f4a9ae9ea38ae6d2",
)
MANIFEST_PIN = (
    13_348,
    "6d176800502f59f268d6ef1040e6701dc1d14e4f21f2d3ecbe8ec86cb4cf917b",
)
TREE_PIN = "44205d093451d221aea9cbc467a316c97a05a0dea9e0c635660aa411ed9f14ec"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_399,
        "3e3129fc0f36f1c26e304fe8258fe733c18df2b1434b06dcc3b913e992d0c7bd",
    ),
    "README.md": (
        3_942,
        "afb41588fce0b1c7f0bfb39a38425332612b77b02844046f11d3414822ae038e",
    ),
    "atlas.geojson": (
        2_941_342,
        "4d8bc608ea3b93be94573f8cbe3bb20b84f0a964ade40f0400cb29413dd2ad23",
    ),
    "capacity_estimates.csv": (
        257_212,
        "1fa99c1592e79966a2c9e823ec2ea9f5000e45a674471864bf2ad06331118cb6",
    ),
    "construction_pipeline.csv": (
        543_700,
        "9148e45b073d7ef56f65d371a3545615cb8fb90009b69bd43d9bb025ef183eaf",
    ),
    "construction_source_signals.csv": (
        355_933,
        "4110cd135bbe4957bb09c8820c985c61476ee81e70844fe61686a356e9ef2df4",
    ),
    "entities.csv": (
        901_497,
        "98978c642b41edbaa7c711bec55f13f8f7d786e93d716cdc2882a38d294b2f66",
    ),
    "evidence.csv": (
        211_789,
        "63b688ab8bab04bb4670e6540e36e28c5dd7ed0f064eb1f4c975b414765c1b2d",
    ),
    "lifecycle_freshness.csv": (
        141_169,
        "8171fb084c278e81b67f21bb5ecc4cfce54172587ba28a752db3ae705f8b502a",
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
        334_102,
        "a4bcb4b1ba896a81aec8123fdedd98b74d977935e14597704fe96ad82245aa3f",
    ),
    "summary.json": (
        3_322,
        "076b230e89ec738a466a43298942ea48da41a2861d3b93366035fd682cfcb56f",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV76Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v76-test-"
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
        error = AssertionError("open seed v76 attempted network access")
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

    def test_exact_v75_adjacency_appends_only_six_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 400)
        self.assertEqual(len(after), 406)
        self.assertEqual(after[:400], before)
        self.assertEqual(
            [row["path"] for row in after[400:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after}
        self.assertFalse(any("orel-nawinna" in path for path in selected_paths))
        self.assertFalse(any("primary-mogadishu-airport" in path for path in selected_paths))
        self.assertFalse(any("national-dc-dr-moct" in path for path in selected_paths))
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
            8,
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
        somalia = documents[core.ADDITION_ORDER[1]]
        self.assertEqual(
            somalia["campus"]["stable_key"],
            "curated:somalia-national-data-center-mogadishu-site-unresolved",
        )
        self.assertEqual(len(somalia["lifecycle"]), 1)

    def test_database_delta_is_exact_and_capacity_free(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 836,
            "evidence": 666,
            "entity_snapshots": 856,
            "lifecycle_observations": 490,
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
        self.assertEqual(summary["entities_total"], 836)
        self.assertEqual(summary["entities_with_coordinates"], 198)
        self.assertEqual(summary["campuses_with_coordinates"], 135)
        self.assertEqual(summary["capacity_estimates_current"], 534)
        self.assertEqual(summary["evidence_total"], 666)

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
            if "v76" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v76, shim.validate_open_seed_v76)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v76(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 836)
        with self.assertRaisesRegex(core.OpenSeedV76Error, "exactly two offline"):
            core.validate_open_seed_v76(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV76Error, "later than validation wall clock"
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
            core.BASE_DEFINITION_PIN,
        )
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)
        with self.assertRaisesRegex(
            core.OpenSeedV76Error, "later than validation wall clock"
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
