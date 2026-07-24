from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import open_seed_release_v10 as release_v10
    from datacenter_atlas.datacenter_atlas import open_seed_v65 as v65
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v10 as release_v10
    from datacenter_atlas import open_seed_v65 as v65


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v65.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v65"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v64.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v64"

DEFINITION_SHA256 = "7431234bac3158ceada1f9545c841a5c59557ed97ec602695e0a3849da9c3d7d"
MANIFEST_SHA256 = "38fcfc7fbd051decdb73c071762c2bb38e430ea43a4f9054489f51b6cb55c92b"
TREE_SHA256 = "8448b30e9909e5f752c50c3b6c568445d1c963a11d97a62f1e4bf4bc3bca6e11"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        4_812,
        "85ccf64c2477094c50dd8b269373828e1c6b98697405eacd7b56dc1d2348597c",
    ),
    "README.md": (
        3_387,
        "1becaf5ab819d090ad179e44e73462e0e7fd458e8fd4e05a55aa5cd352bc46c4",
    ),
    "atlas.geojson": (
        2_667_369,
        "2cdbc4050dd43efa1fadac48043e93faec7a4ef62755b943eb6a5e8fa7abeaa1",
    ),
    "capacity_estimates.csv": (
        244_826,
        "d035125d47abecf144e1bd1c1322a240b7dc21e3aae1cea6a5e5c0d85a66306d",
    ),
    "construction_pipeline.csv": (
        496_437,
        "c391adef0f127d7c959a29b08cc272e353a536e76ed9be9f56509c1cdf1f70e0",
    ),
    "construction_source_signals.csv": (
        316_704,
        "327c091708d8b12cb659af19d3db010bf37379fbecec65a18a46a7086a44f6b3",
    ),
    "entities.csv": (
        825_011,
        "a56425dd846a56df78504d7fa6394671f64d4be9fa30d79a6b1989e2e5595072",
    ),
    "evidence.csv": (
        182_669,
        "5e62f44aa94d494a966ae3d9e440b4dae6cb57abbdffcf3102acfa7d8bc168bb",
    ),
    "lifecycle_freshness.csv": (
        128_512,
        "69f9ca9878ca7eeb30fb51c8688973330b380fd0a33e66c5e07f9afdaa557aa8",
    ),
    "manifest.json": (11_430, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_989,
        "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264",
    ),
    "resolution_candidates.json": (
        7_384,
        "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7",
    ),
    "source_inputs.json": (
        284_789,
        "82fa1c4b7ffb36540a05cf30e832b152274dd16e18ba7d4706a8a9d2bd6f58c5",
    ),
    "summary.json": (
        3_066,
        "191c4d20d5473dd1457e5ccf9bb49a2907b72924587cd899870d3038ceaf82f7",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/open_seed_release_v10.py": (
        19_216,
        "db2b0027985872e2405f3f98f182a2efd09732fd54bee082008f0ac64d39065b",
    ),
    ROOT / "datacenter_atlas/open_seed_v65.py": (
        33_245,
        "5d3de172b2b80726e636bd7ecc787e8961b7b2d5011da130a31fe35ba871f2e6",
    ),
    ROOT / "open_seed_v65.py": (
        138,
        "43eb45603e75234b7bd6107ef2342152c63eb0d7c2d363e691132c362fa25bbe",
    ),
    ROOT / "scripts/build_open_seed_v65.py": (
        363,
        "283a295b27f3b2d83a950ded399582f176125713132261d81728e4d65a3e5112",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV65Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v65-test-db-")
        cls.selected_rows, selected_paths = v65.selected_inputs(cls.base_definition)
        cls.connection = v65._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_tree_and_code_are_exact(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 79_924)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v65.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(
            set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()}
        )
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)
        for path, (size, digest) in CODE_PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual(sha256(BASE_DEFINITION), v65.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), v65.BASE_MANIFEST_SHA256
        )
        self.assertEqual(v65.tree_digest(BASE_RELEASE), v65.BASE_TREE_SHA256)
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
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
                "entities": 755,
                "evidence_records": 468,
                "capacity_estimates": 512,
                "construction_pipeline_records": 387,
                "construction_source_signals": 292,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 429,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v64_adjacency_source_boundaries_and_calendar_gate(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        self.assertEqual((len(before), len(after)), (363, 364))
        self.assertFalse(set(before) - set(after))
        self.assertEqual(set(after) - set(before), set(release_v10.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T06:20:00Z"},
        )
        self.assertEqual(
            self.definition["epoch_capture"], self.base_definition["epoch_capture"]
        )
        self.assertEqual(
            self.definition["expected_epoch_result"],
            self.base_definition["expected_epoch_result"],
        )
        excluded = (
            release_v10.STALE_EXCLUSIONS
            | release_v10.PENDING_NEXT_DAY_EXCLUSIONS
            | release_v10.OUT_OF_SCOPE_EXCLUSIONS
        )
        self.assertFalse(excluded & set(after))
        self.assertTrue(all("2026-07-21" not in path for path in after))
        versions = Counter(
            json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for row in self.selected_rows
        )
        self.assertEqual(versions, {"1.0": 317, "1.1": 47})
        for relative, expected in v65.SOURCE_BOUNDARIES.items():
            source = ROOT / relative
            self.assertEqual(sha256(source), release_v10.ADDITION_PINS[relative])
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            document = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(v65._projected_source(document), expected)
            release_v10._validate_local_research_day(document, relative)
            self.assertLessEqual(
                max(item["retrieved_at"] for item in document["evidence"]),
                release_v10.RECORDED_AT,
            )

        tampered = json.loads(
            (
                ROOT
                / "sources/curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json"
            ).read_text(encoding="utf-8")
        )
        tampered["campus"]["as_of_date"] = "2026-07-21"
        with self.assertRaisesRegex(
            release_v10.OpenSeedReleaseV10Error, "crosses the Jul 20"
        ):
            release_v10._validate_local_research_day(tampered, "calendar-test")

    def test_database_and_nonpromotion_contracts_are_exact(self) -> None:
        v65._validate_database_delta(self.connection)
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                0
            ]
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
                "entities": 755,
                "evidence": 577,
                "lifecycle_observations": 444,
                "capacity_estimates": 513,
                "entity_snapshots": 775,
                "operating_model_observations": 56,
                "workload_observations": 125,
            },
        )
        self.assertEqual(len(v65.ADDED_ENTITY_KEYS), 2)
        self.assertEqual(len(v65.ADDED_PROJECT_KEYS), 1)
        self.assertFalse(v65.MUTATED_ENTITY_KEYS)
        self.assertEqual(len(v65.CAPACITY_CONTRACT), 1)
        for relative in release_v10.ADDITION_PINS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertIsNone(document["campus"]["coordinates"])
            self.assertIsNone(document["campus"]["geometry"])
            self.assertIsNone(document["project"]["coordinates"])
            self.assertIsNone(document["project"]["geometry"])
            self.assertEqual(
                [(row["entity"], row["value"]) for row in document["workloads"]],
                [("project", "ai_specialized_unspecified")],
            )
            self.assertFalse(document["operating_models"])
            self.assertEqual(document["capacities"][0]["metric"], "grid_connection_mw")
        release_v10._validate_source_artifact(ROOT)

    def test_release_delta_is_additive_and_v64_rows_are_unchanged(self) -> None:
        v65._validate_release_delta(RELEASE)
        v65._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v65.ADDED_ENTITY_KEYS)
        self.assertFalse(set(before) - set(after))
        self.assertFalse({key for key in before if before[key] != after[key]})

    def test_freshness_is_dated_and_never_a_current_claim(self) -> None:
        freshness = {
            row["stable_key"]: row for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual(len(freshness), 429)
        expected_ages = {v65.ABILENE_PROJECT_KEY: 46}
        for key, age in expected_ages.items():
            row = freshness[key]
            self.assertEqual(row["observation_age_days"], str(age))
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertEqual(row["current_construction_claim"], "false")
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness.values()
            )
        )
        self.assertEqual(
            Counter(row["freshness_class"] for row in freshness.values()),
            {
                "recent_0_90_days": 219,
                "aging_91_365_days": 183,
                "stale_over_365_days": 27,
            },
        )
        self.assertLessEqual(
            max(
                date.fromisoformat(row["last_observed_status_as_of"])
                for row in freshness.values()
            ),
            date.fromisoformat("2026-07-20"),
        )

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v65 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v10.validate_open_seed_release_v10(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 755)
        self.assertEqual(manifest["lifecycle_status_semantics"], "last_observed")
        self.assertFalse(manifest["current_status_inferred"])

    def test_collision_tamper_and_symlink_fail_closed(self) -> None:
        before_definition = sha256(DEFINITION)
        before_tree = v65.tree_digest(RELEASE)
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            v65.build_open_seed_v65()
        self.assertEqual(sha256(DEFINITION), before_definition)
        self.assertEqual(v65.tree_digest(RELEASE), before_tree)
        self.assertFalse(v65.PUBLICATION_LOCK.exists())

        with tempfile.TemporaryDirectory(
            prefix="v65-tamper-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "release manifest"):
                release_v10.validate_open_seed_release_v10(
                    DEFINITION, copied, require_frozen=False
                )

        with tempfile.TemporaryDirectory(
            prefix="v65-symlink-", dir="/private/tmp"
        ) as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                release_v10.validate_open_seed_release_v10(DEFINITION, linked)


if __name__ == "__main__":
    unittest.main()
