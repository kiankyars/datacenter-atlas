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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v84")
shim = importlib.import_module("datacenter_atlas.open_seed_v84")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v84.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v84"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
BUILDER = ROOT / "scripts/build_open_seed_v84.py"
RECORDED_AT = "2026-07-21T19:10:20Z"

DEFINITION_PIN = (
    100_280,
    "910b2f0d830106b274d8ec22849e2d637463ea5fc57c3481aca2d468218bf8ef",
)
MANIFEST_PIN = (
    15_118,
    "0c4b7b3979c5c3bcdfb3a9bef38b5b32f4da5df31633a0c38920ef937914e301",
)
TREE_PIN = "3ec1197343778c51609221aedbac6f4bf8942cb6620c80fc857b7b1f3124e52b"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        7_272,
        "c62bd6e66bc296e23c06b838cdfea5bec535bc6cb5b3a6b368bd70de750f7666",
    ),
    "README.md": (
        3_811,
        "97e743ec6a410fee79eb18eaf835e356ff4890eaf43525e628346076a20e07c9",
    ),
    "atlas.geojson": (
        3_195_120,
        "03434baa9f9b5d410a201c45cf9e4fce116bd89d6aa3b9c51e9e0beb557eb613",
    ),
    "capacity_estimates.csv": (
        264_653,
        "8e0385503ed9e7447b71c5c6676a1c0a55d69f1f008f84f11a06f0704dfb5dab",
    ),
    "construction_pipeline.csv": (
        574_950,
        "9dec7babf13064065a4986ff2a59d9c27cc4d7a2fbe22f30f003484a3147e06c",
    ),
    "construction_source_signals.csv": (
        389_992,
        "fbb9aea7ee86b3a99e422635127e216fc6f67c14b506c5553b971230a2e8806d",
    ),
    "entities.csv": (
        967_751,
        "89413800f6fa000b6efe1c37335a3ce6bf2ab307497d5604372cc8eed07dc213",
    ),
    "evidence.csv": (
        234_438,
        "30e87d3e74f33651d6d999d7e408b5d7be8d09ddee03ea7508ebc505090a55bc",
    ),
    "lifecycle_freshness.csv": (
        153_786,
        "b806c1ff2b0e5f718e14599ad4903efeb5bd26ab5a8a6a46c12e31af8a3ed8ac",
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
        376_420,
        "530dc478e46615edd5736c95898e5d96315341ea153137d0081e5ce5456fd646",
    ),
    "summary.json": (
        3_446,
        "659405e565ebf826b43c2385a3c964c1e4e4212288ca9deb9c185c80af9d8c5a",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV84Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v84-test-"
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
        error = AssertionError("open seed v84 attempted network access")
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

    def test_exact_v83_adjacency_appends_only_six_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 441)
        self.assertEqual(len(after), 447)
        self.assertEqual(after[:441], before)
        self.assertEqual(
            [row["path"] for row in after[441:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[441:]}
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
            6,
        )
        self.assertEqual(
            sum(
                len(document["operating_models"])
                for document in documents.values()
            ),
            6,
        )
        self.assertEqual(
            sum(len(document["capacities"]) for document in documents.values()),
            8,
        )
        self.assertEqual(
            sum(len(document["workloads"]) for document in documents.values()),
            0,
        )
        cal3 = documents[core.ADDITION_ORDER[1]]
        qr04 = documents[core.ADDITION_ORDER[3]]
        mo2 = documents[core.ADDITION_ORDER[4]]
        self.assertEqual(
            qr04["project"]["coordinates"],
            {"latitude": 20.907398, "longitude": -100.62028},
        )
        self.assertEqual(
            mo2["project"]["coordinates"],
            {
                "latitude": 25.725216372664335,
                "longitude": -100.13271303039684,
            },
        )
        self.assertIsNone(cal3["project"]["coordinates"])
        for document in documents.values():
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["geometry"])

    def test_ambiguous_power_and_review_candidates_contribute_zero(self) -> None:
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(
            [len(documents[path]["capacities"]) for path in core.ADDITION_ORDER],
            [1, 2, 1, 2, 0, 2],
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
        self.assertEqual(len(added), 8)
        self.assertEqual(
            {
                (row["metric"], row["stage"], float(row["base"]))
                for row in added
            },
            {
                ("critical_it_mw", "design", 60.0),
                ("gross_facility_mw", "design", 90.0),
                ("gross_facility_mw", "design", 21.0),
                ("critical_it_mw", "operational", 12.0),
                ("critical_it_mw", "design", 24.0),
                ("critical_it_mw", "operational", 72.0),
                ("critical_it_mw", "design", 300.0),
            },
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
            "entities": 917,
            "evidence": 747,
            "entity_snapshots": 938,
            "lifecycle_observations": 532,
            "capacity_estimates": 551,
            "operating_model_observations": 71,
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
            8,
        )
        self.assertEqual(
            self.connection.execute(
                """
                SELECT COUNT(*)
                FROM entity_snapshots
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN (?, ?)
                """,
                tuple(sorted(core.COORDINATE_CONTRACT)),
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
        self.assertEqual(summary["entities_total"], 917)
        self.assertEqual(summary["entities_with_coordinates"], 202)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 550)
        self.assertEqual(summary["evidence_total"], 747)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 597)
        before_sources = json.loads(
            (BASE_RELEASE / "source_inputs.json").read_text()
        )["sources"]
        after_sources = json.loads((RELEASE / "source_inputs.json").read_text())[
            "sources"
        ]
        before_rows = {json.dumps(row, sort_keys=True) for row in before_sources}
        added_sources = [
            row
            for row in after_sources
            if json.dumps(row, sort_keys=True) not in before_rows
        ]
        self.assertEqual(len(added_sources), 11)
        self.assertEqual(
            {
                row["provenance"]["curated_record_key"]
                for row in added_sources
            },
            core.PROJECTED_EVIDENCE_KEYS,
        )
        self.assertTrue(
            all(
                row["provenance"]["content_hash_verification"]
                == "fetched_bytes_sha256"
                for row in added_sources
            )
        )

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
            if "v84" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v84-collision-") as td:
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
                    core.OpenSeedV84Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core, shim)
        self.assertIs(core.validate_open_seed_v84, shim.validate_open_seed_v84)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v84(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 917)
        with self.assertRaisesRegex(core.OpenSeedV84Error, "exactly two offline"):
            core.validate_open_seed_v84(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV84Error, "later than validation wall clock"
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
        self.assertEqual(
            (
                core.CHECKPOINT_DEFINITION.stat().st_size,
                sha256(core.CHECKPOINT_DEFINITION),
            ),
            core.CHECKPOINT_DEFINITION_PIN,
        )
        self.assertEqual(
            (
                (core.CHECKPOINT_BUNDLE / "manifest.json").stat().st_size,
                sha256(core.CHECKPOINT_BUNDLE / "manifest.json"),
            ),
            core.CHECKPOINT_MANIFEST_PIN,
        )
        self.assertEqual(
            core.v69.tree_digest(core.CHECKPOINT_BUNDLE),
            core.CHECKPOINT_TREE_SHA256,
        )
        with self.assertRaisesRegex(
            core.OpenSeedV84Error, "later than validation wall clock"
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
