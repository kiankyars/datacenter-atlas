from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
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

try:
    from datacenter_atlas.datacenter_atlas import open_seed_release_v5 as release_v5
    from datacenter_atlas.datacenter_atlas import open_seed_v60 as v60
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v5 as release_v5
    from datacenter_atlas import open_seed_v60 as v60


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v60"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"

DEFINITION_SHA256 = "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66"
MANIFEST_SHA256 = "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430"
TREE_SHA256 = "1d58652f691b8030717b7af6c61d2717b2b3427520f7d1b402b75b7670beb138"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (4_501, "aa39078cf3f145472a316c9e34a52f2af4ebffbc90c28cf1134c8e7360c9ff99"),
    "README.md": (3_341, "d069e21ff18a9c241e28c07acc6adfa068938d627fe45681303fb306227e61fe"),
    "atlas.geojson": (2_566_802, "69584e2c693bff78fc3480964289c23c974dba9fd895ab19f34e27ec12b13882"),
    "capacity_estimates.csv": (237_082, "8e649f66e1bf4926bfa51916926e51de0613a98fbe56dfb0d5e7b6e49d809d07"),
    "construction_pipeline.csv": (479_747, "99436a031144619c08bf6e44ab775bc926d184d935aeab6f5fc12a3af0f72974"),
    "construction_source_signals.csv": (302_086, "15ffca5ee1ee428b93dfd61ad05f0ac8ce59bb882f203aa87f2a47700485853a"),
    "entities.csv": (795_186, "215ce7ec17ac064ed45f891666f5d9a66ec9180005e34403e2a40895003084f3"),
    "evidence.csv": (171_805, "3a7b9209146f605294521a42035e96e14453f967a105dbb37bc5209f32587544"),
    "lifecycle_freshness.csv": (123_099, "028aa2c3e2ab08d3b712a5f30c932f67a000f3fae61dea673a593c3fb64a9fc5"),
    "manifest.json": (10_775, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_989, "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264"),
    "resolution_candidates.json": (7_384, "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7"),
    "source_inputs.json": (264_143, "f6d490f0b2ce1d57910e4bf1c8286d36b64ce680187a04253ebc94b7bb58c631"),
    "summary.json": (3_065, "d881f57f9451bc3211ed33ff344c95067dcf553647f725999958a939b600e905"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV60Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v60-test-db-")
        cls.selected_rows, selected_paths = v60.selected_inputs(cls.base_definition)
        cls.connection = v60._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 76_089)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v60.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)

        self.assertEqual(self.definition["release_id"], release_v5.RELEASE_ID)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T03:40:00Z"},
        )
        self.assertEqual(self.definition["publication_contract_version"], 4)
        self.assertEqual(
            self.definition["freshness_contract"], release_v5.freshness_contract()
        )
        self.assertFalse(self.definition["scope"]["commercial_census_parity_claimed"])

        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "entities",
                    "evidence_records",
                    "capacity_estimates",
                    "construction_pipeline_records",
                    "construction_source_signals",
                    "resolution_candidates",
                    "lifecycle_freshness_records",
                    "lifecycle_status_semantics",
                    "current_status_inferred",
                )
            },
            {
                "entities": 725,
                "evidence_records": 439,
                "capacity_estimates": 500,
                "construction_pipeline_records": 371,
                "construction_source_signals": 278,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 412,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v59_adjacency_and_calendar_boundary(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {row["path"]: row["sha256"] for row in self.definition["curated_inputs"]}
        successors = {successor for successor, _ in release_v5.REPLACEMENT_PINS.values()}
        self.assertEqual((len(before), len(after)), (334, 347))
        self.assertEqual(set(before) - set(after), set(release_v5.REPLACEMENT_PINS))
        self.assertEqual(
            set(after) - set(before), successors | set(release_v5.ADDITION_PINS)
        )
        common = set(before) & set(after)
        self.assertEqual(
            {key: after[key] for key in common},
            {key: before[key] for key in common},
        )
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertFalse(
            (release_v5.STALE_EXCLUSIONS | release_v5.PENDING_NEXT_DAY_EXCLUSIONS)
            & set(after)
        )
        self.assertTrue(all("2026-07-21" not in path for path in after))
        self.assertEqual(
            self.definition["epoch_capture"], self.base_definition["epoch_capture"]
        )
        self.assertEqual(
            self.definition["expected_epoch_result"],
            self.base_definition["expected_epoch_result"],
        )
        versions = Counter(
            json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for row in self.selected_rows
        )
        self.assertEqual(versions, {"1.0": 316, "1.1": 31})

    def test_database_contract_preserves_boundaries_and_history(self) -> None:
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
        self.assertEqual(
            counts,
            {
                "entities": 725,
                "evidence": 540,
                "lifecycle_observations": 426,
                "capacity_estimates": 501,
                "entity_snapshots": 744,
                "operating_model_observations": 50,
                "workload_observations": 122,
            },
        )
        v60._validate_database_delta(self.connection)
        bahrain = list(
            self.connection.execute(
                "SELECT status, as_of_date FROM lifecycle_observations "
                "JOIN entities ON entities.id = lifecycle_observations.entity_id "
                "WHERE entities.stable_key = ? ORDER BY as_of_date",
                ("curated:stc-bahrain-data-center:facility-build",),
            )
        )
        self.assertEqual(
            [tuple(row) for row in bahrain],
            [("under_construction", "2024-12-31"), ("operational", "2025-12-31")],
        )

    def test_release_delta_is_strict_and_only_bahrain_common_rows_change(self) -> None:
        v60._validate_release_delta(RELEASE)
        v60._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v60.ADDED_ENTITY_KEYS)
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(
            {
                key
                for key in set(before) & set(after)
                if before[key] != after[key]
            },
            v60.MUTATED_ENTITY_KEYS,
        )

    def test_historical_rows_never_become_current_construction_claims(self) -> None:
        freshness = {row["stable_key"]: row for row in rows(RELEASE / "lifecycle_freshness.csv")}
        self.assertEqual(len(freshness), 412)
        for key in v60.HISTORICAL_UNRESOLVED_KEYS:
            with self.subTest(stable_key=key):
                self.assertEqual(
                    freshness[key]["current_status_classification"], "unknown"
                )
                self.assertEqual(freshness[key]["current_construction_claim"], "false")
        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        for key, as_of in v60.OPERATIONAL_WINNERS.items():
            with self.subTest(stable_key=key):
                self.assertEqual(entities[key]["status"], "operational")
                self.assertEqual(entities[key]["status_as_of"], as_of)
                self.assertEqual(freshness[key]["current_construction_claim"], "false")

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v60 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v5.validate_open_seed_release_v5(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 725)
        self.assertFalse(manifest["current_status_inferred"])

    def test_builder_refuses_definition_and_release_collisions(self) -> None:
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONPATH": str(ROOT),
                "UV_OFFLINE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_open_seed_v60.py")],
            cwd=WORKSPACE,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("definition already exists; refusing overwrite", result.stderr)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(v60.tree_digest(RELEASE), TREE_SHA256)

        with tempfile.TemporaryDirectory(prefix="open-seed-v60-collision-") as temporary:
            root = Path(temporary)
            definition = root / "sources/open-seed-2026-07-20-v60.json"
            release = root / "releases/2026-07-20-open-seed-v60"
            lock = root / ".open-seed-v60.lock"
            definition.parent.mkdir()
            release.parent.mkdir()
            with (
                patch.object(v60, "DEFINITION", definition),
                patch.object(v60, "RELEASE", release),
                patch.object(v60, "PUBLICATION_LOCK", lock),
            ):
                definition.write_text("collision\n", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "definition already exists"):
                    v60.build_open_seed_v60()
                definition.unlink()
                release.mkdir()
                with self.assertRaisesRegex(SystemExit, "release already exists"):
                    v60.build_open_seed_v60()
            self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()
