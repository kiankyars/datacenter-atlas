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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v78")
shim = importlib.import_module("datacenter_atlas.open_seed_v78")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v78.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v78"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v77.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v77"
BUILDER = ROOT / "scripts/build_open_seed_v78.py"
RECORDED_AT = "2026-07-21T16:35:37Z"

DEFINITION_PIN = (
    93_532,
    "97099a7d4b98a783c569e84f1f61295e16888081a44a21b0998b34e503b75e06",
)
MANIFEST_PIN = (
    13_773,
    "4f9e1323f8db9d440c0fe692b7d453fbcca4b02a5296eb7f4c7796e850a0e04f",
)
TREE_PIN = "fb69acb7be201c40a6cb82164524526bbe310d8dae1f0bfcbafd1156e20ff2fb"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_723,
        "ef57ca2fdbf14d12c247d0b8e12053a409af8586c39054c32863f19afca3dcca",
    ),
    "README.md": (
        4_038,
        "09fea81897d57c12443f126c43406eea42c44c945320a100a8fd0a55de258b5c",
    ),
    "atlas.geojson": (
        3_020_453,
        "628d894e908599846088508b1bcf25801d2d2f6f5a7b0454de305a86b1246d2a",
    ),
    "capacity_estimates.csv": (
        258_047,
        "d1d5d6b9bae0d836abd5dfd737bb56e438d8fdfad9cd8d58c6cd98efaf4e160a",
    ),
    "construction_pipeline.csv": (
        554_007,
        "5374c05c888bf0c7bfaf79e52a7f221c4746e0baaa8a36802770a0f26cecc5f8",
    ),
    "construction_source_signals.csv": (
        369_686,
        "b055e7521d5ac249d18e0d584d01dd4844e6750bb83940f5e992c58c9dea4e14",
    ),
    "entities.csv": (
        921_024,
        "e7ea5c254e530a574e417b3dbd3ead6f71b383bb06443f9d1e7f475d155d7b12",
    ),
    "evidence.csv": (
        218_180,
        "247494ed639564ef887c1f0a0153a1c42ab2353137b1129d1106a7d03f30697e",
    ),
    "lifecycle_freshness.csv": (
        145_537,
        "dac97481f2355c5c4284848fda14bf7aa68c2650cae59588a30c5a4ee1790964",
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
        344_957,
        "37a32f16ab0fa803c13df2f741fea66afff7a56086b7ca1e503fbeb6f787772c",
    ),
    "summary.json": (
        3_345,
        "5c2fd0c676af34e08bcffe4b2bcf9bde77d536618430719e328b00c36b1300a2",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV78Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v78-test-"
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
        error = AssertionError("open seed v78 attempted network access")
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

    def test_exact_v77_adjacency_appends_only_three_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 416)
        self.assertEqual(len(after), 419)
        self.assertEqual(after[:416], before)
        self.assertEqual(
            [row["path"] for row in after[416:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[416:]}
        for review_only in ("hyderabad", "noida", "evolution", "tan-phu"):
            self.assertFalse(any(review_only in path for path in selected_paths))
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
            3,
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
            2,
        )
        for document in documents.values():
            self.assertEqual(document["workloads"], [])
        jashore = documents[core.ADDITION_ORDER[0]]
        for name in ("campus", "project"):
            self.assertEqual(
                jashore[name]["coordinates"],
                {
                    "latitude": 23.156275210272007,
                    "longitude": 89.22246834914694,
                },
            )
        navi_mumbai = documents[core.ADDITION_ORDER[1]]
        pune = documents[core.ADDITION_ORDER[2]]
        self.assertEqual(navi_mumbai["capacities"][0]["base"], 1000)
        self.assertEqual(pune["capacities"][0]["base"], 250)
        for document in (navi_mumbai, pune):
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])

    def test_database_delta_is_exact_and_capacity_typed(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 862,
            "evidence": 685,
            "entity_snapshots": 882,
            "lifecycle_observations": 504,
            "capacity_estimates": 537,
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
            2,
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
        self.assertEqual(summary["entities_total"], 862)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 536)
        self.assertEqual(summary["evidence_total"], 685)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 551)

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
            if "v78" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v78-collision-") as td:
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
                    core.OpenSeedV78Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v78, shim.validate_open_seed_v78)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v78(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 862)
        with self.assertRaisesRegex(core.OpenSeedV78Error, "exactly two offline"):
            core.validate_open_seed_v78(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV78Error, "later than validation wall clock"
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
            core.OpenSeedV78Error, "later than validation wall clock"
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
