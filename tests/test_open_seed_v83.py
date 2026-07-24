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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v83")
shim = importlib.import_module("datacenter_atlas.open_seed_v83")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v82.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v82"
BUILDER = ROOT / "scripts/build_open_seed_v83.py"
RECORDED_AT = "2026-07-21T17:38:10Z"

DEFINITION_PIN = (
    98_808,
    "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7",
)
MANIFEST_PIN = (
    14_812,
    "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
)
TREE_PIN = "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        7_208,
        "7d27f379925a190a1c45e53baf581ab61ed685261880e5f1153b13998c7b6d57",
    ),
    "README.md": (
        3_984,
        "e9ca432b29c69ecaef6d1a3c026a60e0636d1707a2c6a793ff6cd4938bbd84f7",
    ),
    "atlas.geojson": (
        3_154_971,
        "79f8b647629f0898ce9ae43ebf82216f4c4e838adbaac2d4b112a3e8217bbdb8",
    ),
    "capacity_estimates.csv": (
        261_286,
        "c7fb4196aeece951de6da19cb4f840226dba0222c496b2cd69d37947def9e546",
    ),
    "construction_pipeline.csv": (
        572_434,
        "f1504f274daf6e41427f4417e540c3d679f712a4e96730b43ec2b0ec12775307",
    ),
    "construction_source_signals.csv": (
        388_293,
        "2728ca90e63d2a7280c35eabea2cb5130e21f44114c8b96254801c44f94af3a7",
    ),
    "entities.csv": (
        955_982,
        "ea6b78cbe55d1424f97d2ba76ae10c3cb134ee44a98f3bde223dd141dd1a68da",
    ),
    "evidence.csv": (
        230_666,
        "897743f94f8e529dcd569e9b5d370523f34ed417cd00bb10c6ce658e918a43a9",
    ),
    "lifecycle_freshness.csv": (
        152_155,
        "7b1e8c5e583067b0c71e95707a284fe63f154a0aa0e2ae2c12cb4f520b11b2f0",
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
        368_961,
        "96191178034837d485a98864c85adc02e614122b0468f33e8e879cd937b02012",
    ),
    "summary.json": (
        3_445,
        "090d920395315bd7ee7449e8bd31d2320bbf4e9be1211f566a330693283939ba",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV83Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v83-test-"
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
        error = AssertionError("open seed v83 attempted network access")
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

    def test_exact_v82_adjacency_appends_only_eight_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 433)
        self.assertEqual(len(after), 441)
        self.assertEqual(after[:433], before)
        self.assertEqual(
            [row["path"] for row in after[433:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[433:]}
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
            8,
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
        self.assertEqual(
            sum(len(document["workloads"]) for document in documents.values()),
            0,
        )
        airtrunk = documents[core.ADDITION_ORDER[0]]
        ec5 = documents[core.ADDITION_ORDER[1]]
        ec6 = documents[core.ADDITION_ORDER[2]]
        gu3 = documents[core.ADDITION_ORDER[7]]
        self.assertEqual(
            airtrunk["evidence"][1]["metadata"]["capacity_label_as_reported"],
            "400+MW total capacity",
        )
        self.assertEqual(
            airtrunk["evidence"][2]["metadata"]["capacity_label_as_reported"],
            "320+ MW of IT load",
        )
        self.assertEqual(ec5["campus"]["stable_key"], ec6["campus"]["stable_key"])
        self.assertEqual(gu3["capacities"][0]["metric"], "gross_facility_mw")
        self.assertEqual(gu3["capacities"][0]["stage"], "design")
        self.assertEqual(gu3["capacities"][0]["base"], 4.0)
        self.assertEqual(
            gu3["operating_models"][0]["value"],
            "colocation",
        )
        for document in documents.values():
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])

    def test_ambiguous_power_and_review_candidates_contribute_zero(self) -> None:
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(
            [len(documents[path]["capacities"]) for path in core.ADDITION_ORDER],
            [0, 0, 0, 0, 0, 0, 0, 1],
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
            ("gross_facility_mw", "design", 4.0),
        )
        gu3 = documents[core.ADDITION_ORDER[7]]
        self.assertEqual(
            gu3["lifecycle"][0]["evidence_key"],
            "gta-gu3-alupang-running-on-genset-captured-2026-07-21",
        )
        self.assertIn(
            "retrieval-date corroboration",
            gu3["evidence"][1]["metadata"]["publication_version_guardrail"],
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
            "entities": 905,
            "evidence": 736,
            "entity_snapshots": 926,
            "lifecycle_observations": 526,
            "capacity_estimates": 543,
            "operating_model_observations": 65,
            "workload_observations": 135,
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
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*)
                FROM entity_snapshots
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key = ?
                """,
                ("curated:cdc-eastern-creek-campus",),
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
        self.assertEqual(summary["entities_total"], 905)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 542)
        self.assertEqual(summary["evidence_total"], 736)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 586)
        added_sources = [
            row
            for row in json.loads((RELEASE / "source_inputs.json").read_text())[
                "sources"
            ]
            if row["source_family"] in core.PROJECTED_SOURCE_FAMILIES
        ]
        about = next(
            row
            for row in added_sources
            if row["source_family"] == "gta_current_newsroom_about_sections"
        )
        self.assertEqual(
            about["provenance"]["content_hash_verification"],
            "fetched_bytes_sha256",
        )
        self.assertEqual(len(added_sources), 12)

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
            if "v83" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v83-collision-") as td:
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
                    core.OpenSeedV83Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core, shim)
        self.assertIs(core.validate_open_seed_v83, shim.validate_open_seed_v83)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v83(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 905)
        with self.assertRaisesRegex(core.OpenSeedV83Error, "exactly two offline"):
            core.validate_open_seed_v83(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV83Error, "later than validation wall clock"
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
        self.assertEqual(
            (
                (BASE_RELEASE / "entities.csv").stat().st_size,
                sha256(BASE_RELEASE / "entities.csv"),
            ),
            core.BASE_ENTITIES_PIN,
        )
        with self.assertRaisesRegex(
            core.OpenSeedV83Error, "later than validation wall clock"
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
