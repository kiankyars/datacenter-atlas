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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v81")
shim = importlib.import_module("datacenter_atlas.open_seed_v81")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v81.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v81"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v80.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v80"
BUILDER = ROOT / "scripts/build_open_seed_v81.py"
RECORDED_AT = "2026-07-21T17:13:30Z"

DEFINITION_PIN = (
    95_875,
    "f71ed7a189b6ba54d10bbed3353fb0baf680061bb3838771bbfd21fe4e6f066e",
)
MANIFEST_PIN = (
    14_362,
    "015c1758d9d6a44faf921fc4402dd5653c02dd96bb6a46ab3164aa83d183938d",
)
TREE_PIN = "50d98a2696119d722facbe3e0d017195b3251a147f0349f8ce96563c2fa84685"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_971,
        "b94b24f3c9e4948e4823d00ad7ca69c028e58772e2ace6d97864a25a3905deac",
    ),
    "README.md": (
        3_914,
        "0d8a80c24d0e5c3974fdde2f55810f2fcc67d56a31eba0dcdb8ec8cf82b0cc3e",
    ),
    "atlas.geojson": (
        3_077_868,
        "aae4cd92f939f1d6203759580647ad74e1662f2f8ce68fd66382359e420ced95",
    ),
    "capacity_estimates.csv": (
        260_224,
        "f584cf1f1774dfbdba88e8fe2acf2470dfdcf777466603bfce08a028e1b02ee8",
    ),
    "construction_pipeline.csv": (
        563_494,
        "a53ff59df68b255760ad0616df61448cf60790512a78b7cab1b94e90c407c674",
    ),
    "construction_source_signals.csv": (
        378_173,
        "21a808706540da60842cd3206e3780cccac8b4f5e3fe97103d338f1688afceeb",
    ),
    "entities.csv": (
        936_051,
        "d36809beb711f4a3f739cb596e5c66995f692666df7136b89190ae7d7b786d25",
    ),
    "evidence.csv": (
        224_175,
        "52670e4044cb90da07164eb2dcbf0f8c59684864533885686219a84047023e9e",
    ),
    "lifecycle_freshness.csv": (
        148_265,
        "211112a56aaeb0ca61ce46ddf29c2590d56b2f6dc6743657f20a32839ab999f0",
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
        356_558,
        "dd6aaf59cfab5e82b3bd4a3411f80a1c6e0d402183c2c2802e66dc802d3ee1aa",
    ),
    "summary.json": (
        3_413,
        "9748f30098678e1843081661ceb7ed0cc1d28665c6c7159cb167d3d1696dfbc5",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV81Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v81-test-"
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
        error = AssertionError("open seed v81 attempted network access")
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

    def test_exact_v80_adjacency_appends_only_five_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 423)
        self.assertEqual(len(after), 428)
        self.assertEqual(after[:423], before)
        self.assertEqual(
            [row["path"] for row in after[423:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[423:]}
        self.assertTrue(selected_paths.isdisjoint(core.EXCLUDED_SOURCE_PATHS))
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
            5,
        )
        self.assertEqual(
            sum(
                len(document["operating_models"])
                for document in documents.values()
            ),
            1,
        )
        self.assertEqual(
            sum(len(document["capacities"]) for document in documents.values()),
            1,
        )
        enka = documents[core.ADDITION_ORDER[0]]
        t964 = documents[core.ADDITION_ORDER[1]]
        self.assertEqual(enka["capacities"][0]["metric"], "critical_it_mw")
        self.assertEqual(enka["capacities"][0]["stage"], "design")
        self.assertEqual(enka["capacities"][0]["base"], 11)
        self.assertEqual(t964["operating_models"][0]["value"], "colocation")
        self.assertEqual(t964["operating_models"][0]["entity"], "campus")
        for document in documents.values():
            self.assertEqual(document["workloads"], [])
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])

    def test_ambiguous_power_and_review_candidates_contribute_zero(self) -> None:
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(
            [len(documents[path]["capacities"]) for path in core.ADDITION_ORDER],
            [1, 0, 0, 0, 0],
        )
        capacities = csv_rows(RELEASE / "capacity_estimates.csv")
        before_ids = {
            (
                row["entity_id"],
                row["metric"],
                row["stage"],
                row["as_of_date"],
                row["evidence_id"],
            )
            for row in csv_rows(BASE_RELEASE / "capacity_estimates.csv")
        }
        added = [
            row
            for row in capacities
            if (
                row["entity_id"],
                row["metric"],
                row["stage"],
                row["as_of_date"],
                row["evidence_id"],
            )
            not in before_ids
        ]
        self.assertEqual(len(added), 1)
        self.assertEqual(
            (added[0]["metric"], added[0]["stage"], float(added[0]["base"])),
            ("critical_it_mw", "design", 11.0),
        )
        assessment = core._validate_official_artifact()["assessment"]
        candidates = {
            row["candidate_id"]: row for row in assessment["candidates"]
        }
        self.assertEqual(
            set(candidates) - core.ADDED_PROJECT_KEYS,
            core.REVIEW_ONLY_CANDIDATE_IDS,
        )
        self.assertTrue(
            all(
                not candidates[key]["seed_eligible"]
                and not candidates[key]["source_record_created"]
                for key in core.REVIEW_ONLY_CANDIDATE_IDS
            )
        )

    def test_database_delta_is_exact_and_capacity_typed(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 880,
            "evidence": 709,
            "entity_snapshots": 900,
            "lifecycle_observations": 513,
            "capacity_estimates": 541,
            "operating_model_observations": 62,
            "workload_observations": 133,
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
        self.assertEqual(summary["entities_total"], 880)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 540)
        self.assertEqual(summary["evidence_total"], 709)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 568)

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
            if "v81" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v81-collision-") as td:
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
                    core.OpenSeedV81Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core, shim)
        self.assertIs(core.validate_open_seed_v81, shim.validate_open_seed_v81)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v81(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 880)
        with self.assertRaisesRegex(core.OpenSeedV81Error, "exactly two offline"):
            core.validate_open_seed_v81(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV81Error, "later than validation wall clock"
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
        self.assertEqual(
            (
                (BASE_RELEASE / "entities.csv").stat().st_size,
                sha256(BASE_RELEASE / "entities.csv"),
            ),
            core.BASE_ENTITIES_PIN,
        )
        with self.assertRaisesRegex(
            core.OpenSeedV81Error, "later than validation wall clock"
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
