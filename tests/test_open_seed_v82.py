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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v82")
shim = importlib.import_module("datacenter_atlas.open_seed_v82")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v82.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v82"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v81.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v81"
BUILDER = ROOT / "scripts/build_open_seed_v82.py"
RECORDED_AT = "2026-07-21T17:29:03Z"

DEFINITION_PIN = (
    97_043,
    "29b83aa6b5b571d65a26246c74f5747789acc9d9af79f43b07a5a36ba921c26f",
)
MANIFEST_PIN = (
    14_564,
    "2a0ddb8a9ded0e8ce9d01a56cfbfd16d9550decabdb141e96f849f404c2de295",
)
TREE_PIN = "7948ab06c0018827de799170d6bd85089902e188674b4a20e7040c48efd21da0"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        7_117,
        "8f0f7a22aaf43a568b55e28f4ec3b08e195689f3e88e340c6365e5a2018872bf",
    ),
    "README.md": (
        4_095,
        "b5a822f0282c77131c02d684a6ab85a769d40211e576598b3abf3b463fd151e2",
    ),
    "atlas.geojson": (
        3_109_982,
        "a87ba20ed641fa51506333fc629f853012eb1f7aeccf90d109c147947f966e68",
    ),
    "capacity_estimates.csv": (
        260_866,
        "002d519c07edf5ef2e2476f7994088965d19ebda2e10d50f2974f8182c6b9345",
    ),
    "construction_pipeline.csv": (
        567_043,
        "348295c2df430360669b084f5a9ca84d5bc994397b1a25771e1955af2db922f1",
    ),
    "construction_source_signals.csv": (
        382_131,
        "a5d1f526a0d30ca41e8e9a9b8f46261e1579ae21ce535142f715b91b22fc9366",
    ),
    "entities.csv": (
        945_021,
        "1d2775454e2dbb91199fb5d6afcec33e142cbae6ea94ea78945842cbab7541ef",
    ),
    "evidence.csv": (
        226_631,
        "d8b127cb31ad3ef7046a5881c1e7ec3a07da818115580dea174e9bc39043537e",
    ),
    "lifecycle_freshness.csv": (
        149_839,
        "b55027b3ce8861f1efd15923afeab13fcf3aa1fc5cb1e175d7aebe6bd0ee7653",
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
        360_962,
        "e0f83fa2333b743a75b79da06589bb77d44b7021316b1ceaf7af588de63f0d3c",
    ),
    "summary.json": (
        3_430,
        "7f94892ea3ff35bb267cee5941b953e26a7d0ac971744f80825d4fe95be53e4d",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV82Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v82-test-"
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
        error = AssertionError("open seed v82 attempted network access")
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

    def test_exact_v81_adjacency_appends_only_five_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 428)
        self.assertEqual(len(after), 433)
        self.assertEqual(after[:428], before)
        self.assertEqual(
            [row["path"] for row in after[428:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[428:]}
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
            2,
        )
        self.assertEqual(
            sum(len(document["capacities"]) for document in documents.values()),
            1,
        )
        self.assertEqual(
            sum(len(document["workloads"]) for document in documents.values()),
            2,
        )
        microsoft = documents[core.ADDITION_ORDER[0]]
        ast = documents[core.ADDITION_ORDER[3]]
        serbia = documents[core.ADDITION_ORDER[4]]
        self.assertEqual(
            microsoft["operating_models"][0]["value"], "hyperscale_self_build"
        )
        self.assertEqual(microsoft["workloads"][0]["value"], "general_cloud")
        self.assertEqual(
            serbia["capacities"][0]["metric"], "generation_nameplate_mw"
        )
        self.assertEqual(serbia["capacities"][0]["stage"], "operational")
        self.assertEqual(serbia["capacities"][0]["base"], 0.3)
        self.assertEqual(
            ast["evidence"][0]["metadata"]["content_hash_verification"],
            "unverified_assertion",
        )
        for document in documents.values():
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])

    def test_ambiguous_power_and_review_candidates_contribute_zero(self) -> None:
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(
            [len(documents[path]["capacities"]) for path in core.ADDITION_ORDER],
            [0, 0, 0, 0, 1],
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
            ("generation_nameplate_mw", "operational", 0.3),
        )
        ten_brinke = documents[core.ADDITION_ORDER[2]]
        ppc = ten_brinke["evidence"][1:]
        self.assertTrue(
            all(
                row["metadata"]["content_hash_verification"]
                == "unverified_assertion"
                for row in ppc
            )
        )
        self.assertFalse(ppc[1]["metadata"]["identity_link_asserted"])
        self.assertFalse(ppc[1]["metadata"]["role_link_asserted"])
        serbia = documents[core.ADDITION_ORDER[4]]
        self.assertFalse(
            serbia["evidence"][0]["metadata"]["prior_discovery_reconciliation"][
                "block_2_identity_asserted"
            ]
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
            "entities": 890,
            "evidence": 719,
            "entity_snapshots": 910,
            "lifecycle_observations": 518,
            "capacity_estimates": 542,
            "operating_model_observations": 64,
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
        self.assertEqual(summary["entities_total"], 890)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 541)
        self.assertEqual(summary["evidence_total"], 719)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 574)
        added_sources = [
            row
            for row in json.loads((RELEASE / "source_inputs.json").read_text())[
                "sources"
            ]
            if row["source_family"] in core.PROJECTED_SOURCE_FAMILIES
        ]
        ast = next(
            row for row in added_sources if row["source_family"] == "ast_official_events"
        )
        self.assertEqual(
            ast["provenance"]["content_hash_verification"],
            "unverified_assertion",
        )
        self.assertTrue(
            {row["source_family"] for row in added_sources}.isdisjoint(
                {"ppc_investor_presentations", "ppc_stock_news"}
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
            if "v82" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v82-collision-") as td:
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
                    core.OpenSeedV82Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core, shim)
        self.assertIs(core.validate_open_seed_v82, shim.validate_open_seed_v82)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v82(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 890)
        with self.assertRaisesRegex(core.OpenSeedV82Error, "exactly two offline"):
            core.validate_open_seed_v82(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV82Error, "later than validation wall clock"
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
            core.OpenSeedV82Error, "later than validation wall clock"
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
