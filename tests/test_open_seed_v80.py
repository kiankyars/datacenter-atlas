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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v80")
shim = importlib.import_module("datacenter_atlas.open_seed_v80")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v80.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v80"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v79.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v79"
BUILDER = ROOT / "scripts/build_open_seed_v80.py"
RECORDED_AT = "2026-07-21T17:05:11Z"

DEFINITION_PIN = (
    94_529,
    "fb4e3fbcc1ec65a5abb516dbf1d71bf68c6a4d714374126f25f87ba78cc51548",
)
MANIFEST_PIN = (
    14_003,
    "a9a89bb89aa0febd32a90b7fb30134f499ad360e08e28eb358bcfd9fe74934d1",
)
TREE_PIN = "0215181c22ab0613b77820215fd98098c3c43c9b03ae40f88bd36acb2dec96ca"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_834,
        "be92490de49627685d1749595f4517ea663d6c61fe49d0fd087aca20aca45156",
    ),
    "README.md": (
        3_936,
        "55ef7efb0a8ff38b0b8b4b1706cf80a20a526e2ff4b066b64ffa69bee91d3219",
    ),
    "atlas.geojson": (
        3_047_443,
        "ef62868e3fd217871f6ac6df088146626d2820fa569ab4b158213a4ed4cb7764",
    ),
    "capacity_estimates.csv": (
        259_792,
        "67a3c98efcbb3799b4cb201621bb7a001bfecb6c81c23554123fadfa6c38679e",
    ),
    "construction_pipeline.csv": (
        559_316,
        "e91ecb951466f98570a1ad55067716eb6c20c41553a522e8c9f6d7d72ca8db37",
    ),
    "construction_source_signals.csv": (
        373_464,
        "12bfb85a4e314f00a65446c4130fa32db665c125892015a45bd5c14cdaed23c8",
    ),
    "entities.csv": (
        928_628,
        "9db1223c6b847509cf0b4bf1e88e0878bf8b37e9312120956b0c7e839760c9cd",
    ),
    "evidence.csv": (
        220_720,
        "d96b4033290731e491efe91d8c28338534419c38b174fcb74b3d1d3e73cca26c",
    ),
    "lifecycle_freshness.csv": (
        146_717,
        "69ba32cf570b1536dcf06cc0b25de227f805bdcd0f54490e0da401687d5b5eeb",
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
        349_778,
        "1e5ebfd82a1c1c030df8ffe45513c5f4a3c4990dc8f009bf23a071d40d35f483",
    ),
    "summary.json": (
        3_398,
        "358d5bf237b2bd89606e115dcd22f6b1704a19c8e08a1f1e9f7d299ba62472ea",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="open-seed-v80-test-"
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
        error = AssertionError("open seed v80 attempted network access")
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

    def test_exact_v79_adjacency_appends_only_two_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 421)
        self.assertEqual(len(after), 423)
        self.assertEqual(after[:421], before)
        self.assertEqual(
            [row["path"] for row in after[421:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after[421:]}
        self.assertTrue(selected_paths.isdisjoint(core.EXCLUDED_SOURCE_PATHS))
        self.assertFalse(
            any(
                token in path.lower()
                for path in selected_paths
                for token in ("jb7", "accra", "nbox")
            )
        )
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
            2,
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
            2,
        )
        nbo2 = documents[core.ADDITION_ORDER[0]]
        rdh2 = documents[core.ADDITION_ORDER[1]]
        self.assertEqual(nbo2["capacities"][0]["metric"], "critical_it_mw")
        self.assertEqual(nbo2["capacities"][0]["stage"], "design")
        self.assertEqual(nbo2["capacities"][0]["base"], 6.5)
        self.assertEqual(nbo2["operating_models"][0]["value"], "colocation")
        self.assertEqual(
            {row["value"] for row in nbo2["workloads"]},
            {"enterprise_it", "general_cloud"},
        )
        self.assertEqual(rdh2["capacities"][0]["metric"], "critical_it_mw")
        self.assertEqual(rdh2["capacities"][0]["stage"], "design")
        self.assertEqual(rdh2["capacities"][0]["base"], 4.6)
        self.assertFalse(
            any(row.get("base") == 4.9 for row in rdh2["capacities"])
        )
        self.assertEqual(rdh2["operating_models"], [])
        self.assertEqual(
            {row["value"] for row in rdh2["workloads"]},
            {"enterprise_it", "general_cloud"},
        )
        for document in (nbo2, rdh2):
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])
        for relative in core.EXCLUDED_ORDER:
            excluded = json.loads((ROOT / relative).read_text())
            for section in (
                "lifecycle",
                "capacities",
                "operating_models",
                "workloads",
            ):
                self.assertEqual(excluded[section], [])

    def test_peeringdb_values_and_review_records_contribute_zero(self) -> None:
        documents = core._validate_additions(RECORDED_AT)
        nbo2 = documents[core.ADDITION_ORDER[0]]
        peering = next(
            row
            for row in nbo2["evidence"]
            if row["source_family"] == "peeringdb_blocked_direct_lane_metadata"
        )
        metadata = peering["metadata"]
        for key in (
            "record_values_released",
            "address_values_released",
            "coordinate_values_released",
            "identity_values_released",
            "placement_rows_created",
        ):
            self.assertEqual(metadata[key], 0)
        self.assertFalse(metadata["direct_release_permitted"])
        self.assertFalse(metadata["publication_eligible"])
        projected = csv_rows(RELEASE / "evidence.csv")
        self.assertNotIn(peering["source_family"], {row["source_family"] for row in projected})
        public_text = "\n".join(
            (RELEASE / filename).read_text()
            for filename in (
                "entities.csv",
                "construction_pipeline.csv",
                "construction_source_signals.csv",
                "capacity_estimates.csv",
            )
        )
        for token in (
            "curated-review:africa-gap-teraco",
            "curated-review:africa-gap-adc",
            "curated-review:africa-gap-ixafrica",
        ):
            self.assertNotIn(token, public_text)

    def test_database_delta_is_exact_and_capacity_typed(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        expected_counts = {
            "entities": 870,
            "evidence": 696,
            "entity_snapshots": 890,
            "lifecycle_observations": 508,
            "capacity_estimates": 540,
            "operating_model_observations": 61,
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
        self.assertEqual(summary["entities_total"], 870)
        self.assertEqual(summary["entities_with_coordinates"], 200)
        self.assertEqual(summary["campuses_with_coordinates"], 136)
        self.assertEqual(summary["capacity_estimates_current"], 539)
        self.assertEqual(summary["evidence_total"], 696)
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["evidence_records"], 558)

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
            if "v80" in path.name
            and (
                path.name.startswith(".")
                or path.name == core.PUBLICATION_LOCK.name
            )
        ]
        self.assertEqual(leftovers, [])

    def test_no_replace_and_identity_checked_rollback_helpers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v80-collision-") as td:
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
                    core.OpenSeedV80Error, "refusing rollback of substituted"
                ):
                    core._rollback_release(identity, rollback_stage)
            self.assertTrue(final_release.is_dir())
            self.assertTrue(displaced.is_dir())

    def test_offline_replay_shim_idempotence_and_base_nonmutation(self) -> None:
        self.assertIs(core, shim)
        self.assertIs(core.validate_open_seed_v80, shim.validate_open_seed_v80)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v80(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 870)
        with self.assertRaisesRegex(core.OpenSeedV80Error, "exactly two offline"):
            core.validate_open_seed_v80(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV80Error, "later than validation wall clock"
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
            core.OpenSeedV80Error, "later than validation wall clock"
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
