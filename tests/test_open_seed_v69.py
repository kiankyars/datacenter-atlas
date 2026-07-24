from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v69")
shim = importlib.import_module("datacenter_atlas.open_seed_v69")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v69.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v69"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V68_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
V68_RELEASE = ROOT / "releases/2026-07-21-open-seed-v68"

DEFINITION_PIN = (
    86_041,
    "d72275d4d0c37f90bffa694ae15f2b58fc1c03d70f69501e2c16abde425748ff",
)
MANIFEST_PIN = (
    12_432,
    "1708696cb999baa00fba2f97b05277bb0156e6eebf878bd16cc8ad6cfe6153f0",
)
TREE_PIN = "765488c1c69b11bb5d38c5d5387aca2afa45e21e6c2ab995c1d92e8cecd56881"
RECORDED_AT = "2026-07-21T09:31:27Z"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_657,
        "8d357db7dd2756ecfe24c1ba54255643d3d92b66df98c831e51ce0f847fc6aca",
    ),
    "README.md": (
        3_816,
        "c4a72136430a184389ce7533b3f93a519015aeb19a83be8064c55e0145c7ad33",
    ),
    "atlas.geojson": (
        2_843_869,
        "7504fb7bd915f428411e14d41ae69ee6448715d0756562a118de84c75fa18902",
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
    "manifest.json": MANIFEST_PIN,
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
        "fd977629906e7c37f25cfef373e6575b9987dd374d65173a056d516875e8ba52",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_v69.py": (
        72_288,
        "885ab22069ef6b9a7429850e2abbdf85ab70dcfbb51f7f011de5905931f01e67",
    ),
    ROOT / "open_seed_v69.py": (
        138,
        "1dc0793afc60568478334adfbbbdadd5db24c2d0be2ae476e1f34ac8fb429cd3",
    ),
    ROOT / "scripts/build_open_seed_v69.py": (
        360,
        "cb9cba3a8b0a06f3ddde60704d817ec3fdf84fd6a3f9db7a089cd5ed5e17b447",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OpenSeedV69Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.v68 = json.loads(V68_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.recorded_at = cls.definition["build"]["recorded_at"]
        cls.selected_rows, paths = core.selected_inputs(
            cls.base, recorded_at=cls.recorded_at
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v69-test-db-")
        cls.connection = core._build_database(
            cls.base,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
            recorded_at=cls.recorded_at,
        )
        cls.selected_paths = paths

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_definition_release_tree_files_and_code_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual((RELEASE / "manifest.json").stat().st_size, MANIFEST_PIN[0])
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_PIN[1])
        self.assertEqual(core.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        for path, expected in CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_timestamp_is_between_artifact_birth_and_validation_wall_clock(self) -> None:
        recorded_at = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertEqual(self.recorded_at, RECORDED_AT)
        for path in (DEFINITION, RELEASE):
            birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
            self.assertLessEqual(birth, recorded_at)
        validation_wall_clock = datetime.now(timezone.utc)
        self.assertLessEqual(recorded_at, validation_wall_clock)
        self.assertLessEqual(
            core._max_selected_retrieved_at(self.base, self.selected_paths),
            recorded_at,
        )
        core.validate_open_seed_v69(
            DEFINITION,
            RELEASE,
            validation_wall_clock=validation_wall_clock,
        )

    def test_future_timestamp_and_late_birth_are_rejected(self) -> None:
        recorded_at = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        with self.assertRaisesRegex(ValueError, "later than validation wall clock"):
            core._validate_definition(
                self.definition,
                self.base,
                validation_wall_clock=recorded_at - timedelta(seconds=1),
            )
        with tempfile.TemporaryDirectory(prefix="v69-late-birth-") as temporary:
            copied_definition = Path(temporary) / DEFINITION.name
            shutil.copy2(DEFINITION, copied_definition)
            with self.assertRaisesRegex(ValueError, "definition was born after"):
                core.validate_open_seed_v69(copied_definition, RELEASE)

    def test_exact_v67_plus_thirteen_inputs_match_rejected_v68_data(self) -> None:
        self.assertEqual((len(self.base["curated_inputs"]), len(self.selected_rows)), (378, 391))
        self.assertEqual(self.selected_rows[:378], self.base["curated_inputs"])
        self.assertEqual(self.selected_rows, self.definition["curated_inputs"])
        self.assertEqual(self.selected_rows, self.v68["curated_inputs"])
        self.assertEqual(
            [row["path"] for row in self.selected_rows[378:]],
            sorted(core.ADDITION_PINS),
        )
        for key in ("epoch_capture", "expected_epoch_result", "schema_version", "scope"):
            self.assertEqual(self.definition[key], self.base[key])
        self.assertEqual(set(self.definition), set(self.base))

    def test_corrected_wrapper_and_immutable_v1_origin_mapping_is_explicit(self) -> None:
        state = core._validate_artifact_lineage()
        self.assertEqual(set(state), set(core.DISCOVERY_ARTIFACT_PINS))
        self.assertTrue(all("-v2" in path for path in state))
        self.assertNotIn(
            "source_artifacts/gap-region-official-discovery-2026-07-21-v2",
            state,
        )
        documents = [json.loads(path.read_text()) for path in self.selected_paths[-13:]]
        origin_ids = {
            evidence["metadata"]["capture_artifact_id"]
            for document in documents
            for evidence in document["evidence"]
            if "capture_artifact_id" in evidence["metadata"]
        }
        self.assertEqual(origin_ids, set(core.CORRECTED_ORIGIN_MAPPING))
        for origin_id, wrapper_path in core.CORRECTED_ORIGIN_MAPPING.items():
            manifest = json.loads((ROOT / wrapper_path / "manifest.json").read_text())
            self.assertEqual(manifest["retained_origin_ids"], [origin_id])
            self.assertEqual(
                manifest["supersedes_non_accepted_origin"]["incident_manifest_sha256"],
                core.INCIDENT_MANIFEST_SHA256,
            )

    def test_v68_remains_byte_exact_and_explicitly_non_accepted(self) -> None:
        lineage = core._validate_rejected_lineage()
        self.assertEqual(sha256(V68_DEFINITION), core.REJECTED_V68_DEFINITION_SHA256)
        self.assertEqual(core.tree_digest(V68_RELEASE), core.REJECTED_V68_TREE_SHA256)
        self.assertEqual(
            lineage["incident_manifest_sha256"], core.INCIDENT_MANIFEST_SHA256
        )
        incident = json.loads((core.INCIDENT / "incident.json").read_text())
        v68 = next(row for row in incident["subjects"] if row["subject_id"] == "open-seed-v68")
        self.assertEqual(v68["acceptance_status"], "non_accepted")
        self.assertIn(
            "passage of\nwall-clock time does not retroactively validate",
            (core.INCIDENT / "README.md").read_text().lower(),
        )
        self.assertNotEqual(self.definition["release_id"], self.v68["release_id"])

    def test_database_and_public_semantics_match_v68_except_timestamp_identity(self) -> None:
        core._validate_database_contract(self.connection)
        core._validate_prior_semantics(
            self.connection, self.base, recorded_at=self.recorded_at
        )
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
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
        self.assertEqual(counts, {
            "entities": 806,
            "evidence": 628,
            "lifecycle_observations": 472,
            "capacity_estimates": 531,
            "entity_snapshots": 826,
            "operating_model_observations": 56,
            "workload_observations": 128,
        })
        for filename in core.CSV_DELTA_COUNT_CONTRACT:
            with self.subTest(filename=filename):
                self.assertEqual(
                    core._normalized_csv_counter(
                        RELEASE / filename, recorded_at=self.recorded_at
                    ),
                    core._normalized_csv_counter(
                        V68_RELEASE / filename, recorded_at=self.recorded_at
                    ),
                )

    def test_release_semantics_remain_last_observed_unknown_and_bounded(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=self.recorded_at)
        core._validate_release_facts(RELEASE, recorded_at=self.recorded_at)
        readme = (RELEASE / "README.md").read_text()
        for phrase in (
            "current_construction_claim` remains `false",
            "no capacity arithmetic is valid",
            "corrected v2 discovery wrappers",
            "Rejected v68 is not a predecessor",
            "does not retroactively validate it",
        ):
            self.assertIn(phrase, readme)

    def test_parent_nested_layouts_and_exactly_two_offline_replays(self) -> None:
        self.assertNotEqual(core.__file__, shim.__file__)
        self.assertIs(core.selected_inputs, shim.selected_inputs)
        self.assertIs(core.validate_open_seed_v69, shim.validate_open_seed_v69)
        error = AssertionError("v69 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = shim.validate_open_seed_v69(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 806)
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core.validate_open_seed_v69(DEFINITION, RELEASE, replay_count=1)

    def test_idempotency_order_collision_tamper_and_symlink_fail_closed(self) -> None:
        first, first_paths = core.selected_inputs(self.base, recorded_at=self.recorded_at)
        second, second_paths = core.selected_inputs(self.base, recorded_at=self.recorded_at)
        self.assertEqual((first, first_paths), (second, second_paths))
        guard = core._guard_state()
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core.build_open_seed_v69()
        self.assertEqual(core._guard_state(), guard)
        reversed_pins = dict(reversed(tuple(core.ADDITION_PINS.items())))
        with patch.object(core, "ADDITION_PINS", reversed_pins):
            with self.assertRaisesRegex(SystemExit, "canonical additions"):
                core.selected_inputs(self.base, recorded_at=self.recorded_at)
        with tempfile.TemporaryDirectory(prefix="v69-tamper-") as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest hash"):
                core.validate_open_seed_v69(DEFINITION, copied, require_frozen=False)
        with tempfile.TemporaryDirectory(prefix="v69-symlink-") as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core.validate_open_seed_v69(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
