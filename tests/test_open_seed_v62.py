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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v7 as release_v7
    from datacenter_atlas.datacenter_atlas import open_seed_v62 as v62
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v7 as release_v7
    from datacenter_atlas import open_seed_v62 as v62


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v61.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v61"
APPLIED_SOURCE = (
    ROOT
    / "sources/curated-official-2026-07-20-applied-digital-pf1-building-2-"
    "phase-1-operational.json"
)
DATABANK_SOURCE = ROOT / "sources/curated-official-2026-07-20-databank-iad5-culpeper.json"

DEFINITION_SHA256 = "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
MANIFEST_SHA256 = "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"
APPLIED_PARENT_KEY = "curated:applied-digital-polaris-forge-1:second-150mw-facility"
APPLIED_PHASE_KEY = f"{APPLIED_PARENT_KEY}:phase-1"
DATABANK_CAMPUS_KEY = "curated:databank-culpeper-campus"
DATABANK_PROJECT_KEY = f"{DATABANK_CAMPUS_KEY}:iad5-current-build"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (4_575, "1e0cf32accbc59eca321ca4801f1941c57264d071c3c0f3b4b1183f20f49c485"),
    "README.md": (3_372, "76664dd2187ddf045fbddd11c6d27f0d8cd347e79e92e28011439c3a9ae4c8c5"),
    "atlas.geojson": (2_584_504, "d211f8ec879de9562f529c333e81d6099d803b1c57d39ab00d1bbc296974e704"),
    "capacity_estimates.csv": (238_365, "b00d4c73702f30d7257b263a8464875874885f144d767955bdbe22fdac774b11"),
    "construction_pipeline.csv": (482_154, "c69af039c18c30ad858b952662cc2e838a373d98d74a21fe68536e9440e27891"),
    "construction_source_signals.csv": (304_152, "12ccec7d67f2e747c6eaac82afc341a19b5209520a8848b2eaf9f0dfad809bf1"),
    "entities.csv": (800_902, "776094d4fa2fcccdec19f6d3133d9818d0f220c6fc1743ea7520a1ce96070459"),
    "evidence.csv": (173_937, "4b3ba9c014d64a0ef9ff1d02463db6683a029cd096b2ecb1cb6942ca1814aa57"),
    "lifecycle_freshness.csv": (124_021, "070d1f18817ad01fcd366f48c6bd2ad51b59697ce96c4b5e04a00a7cc0df0c50"),
    "manifest.json": (10_934, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_989, "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264"),
    "resolution_candidates.json": (7_384, "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7"),
    "source_inputs.json": (267_861, "b0542ce7f76648624c55f4b4cabe48cbc40c28dcee3a5d0c974c1305ae173386"),
    "summary.json": (3_065, "37e33f90acddfd1bd504c52d842e812a90a12efb5b04654db4918cb105d9eba4"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV62Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v62-test-db-")
        cls.selected_rows, selected_paths = v62.selected_inputs(cls.base_definition)
        cls.connection = v62._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 76_824)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v62.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)

        self.assertEqual(self.definition["release_id"], release_v7.RELEASE_ID)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T04:35:00Z"},
        )
        self.assertEqual(self.definition["publication_contract_version"], 4)
        self.assertEqual(
            self.definition["freshness_contract"], release_v7.freshness_contract()
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
                "entities": 730,
                "evidence_records": 444,
                "capacity_estimates": 502,
                "construction_pipeline_records": 373,
                "construction_source_signals": 280,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 415,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v61_adjacency_and_calendar_boundary(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {row["path"]: row["sha256"] for row in self.definition["curated_inputs"]}
        self.assertEqual((len(before), len(after)), (348, 350))
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(set(after) - set(before), set(release_v7.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertFalse(
            (
                release_v7.STALE_EXCLUSIONS
                | release_v7.PENDING_NEXT_DAY_EXCLUSIONS
                | release_v7.OUT_OF_SCOPE_EXCLUSIONS
            )
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
        self.assertEqual(versions, {"1.0": 316, "1.1": 34})

    def test_database_contract_preserves_parent_phase_and_point_boundaries(self) -> None:
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
                "entities": 730,
                "evidence": 546,
                "lifecycle_observations": 430,
                "capacity_estimates": 503,
                "entity_snapshots": 750,
                "operating_model_observations": 53,
                "workload_observations": 123,
            },
        )
        v62._validate_database_delta(self.connection)
        lifecycle = {
            row[0]: (row[1], row[2])
            for row in self.connection.execute(
                "SELECT entities.stable_key, status, as_of_date "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id "
                "WHERE entities.stable_key IN (?, ?, ?)",
                (APPLIED_PARENT_KEY, APPLIED_PHASE_KEY, DATABANK_PROJECT_KEY),
            )
        }
        self.assertEqual(
            lifecycle,
            {
                APPLIED_PARENT_KEY: ("under_construction", "2026-04-08"),
                APPLIED_PHASE_KEY: ("operational", "2026-07-01"),
                DATABANK_PROJECT_KEY: ("under_construction", "2026-05-14"),
            },
        )
        capacities = {
            row[0]: tuple(row[1:])
            for row in self.connection.execute(
                "SELECT entities.stable_key, metric, stage, unit, base, as_of_date "
                "FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id "
                "WHERE entities.stable_key IN (?, ?)",
                (APPLIED_PHASE_KEY, DATABANK_PROJECT_KEY),
            )
        }
        self.assertEqual(
            capacities,
            {
                APPLIED_PHASE_KEY: (
                    "critical_it_mw",
                    "operational",
                    "MW",
                    75.0,
                    "2026-07-01",
                ),
                DATABANK_PROJECT_KEY: (
                    "critical_it_mw",
                    "planned",
                    "MW",
                    72.0,
                    "2026-05-14",
                ),
            },
        )
        points = list(
            self.connection.execute(
                "SELECT entities.stable_key, latitude, longitude, geometry_json "
                "FROM entity_snapshots JOIN entities "
                "ON entities.id = entity_snapshots.entity_id "
                "WHERE entities.stable_key IN (?, ?) ORDER BY entities.stable_key",
                (DATABANK_CAMPUS_KEY, DATABANK_PROJECT_KEY),
            )
        )
        self.assertEqual(
            [
                (
                    row[0],
                    row[1],
                    row[2],
                    json.loads(row[3]),
                )
                for row in points
            ],
            [
                (
                    DATABANK_CAMPUS_KEY,
                    38.45185992,
                    -77.98378765,
                    {
                        "type": "Point",
                        "coordinates": [-77.98378765, 38.45185992],
                    },
                ),
                (
                    DATABANK_PROJECT_KEY,
                    38.45185992,
                    -77.98378765,
                    {
                        "type": "Point",
                        "coordinates": [-77.98378765, 38.45185992],
                    },
                ),
            ],
        )
        applied = json.loads(APPLIED_SOURCE.read_text(encoding="utf-8"))
        databank = json.loads(DATABANK_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(
            applied["evidence"][0]["metadata"]["parent_project_stable_key"],
            APPLIED_PARENT_KEY,
        )
        coordinate_scope = databank["evidence"][2]["metadata"]["coordinate_scope"]
        self.assertIn("not a parcel", coordinate_scope)
        self.assertIn(
            "not a physical-site count",
            databank["evidence"][2]["metadata"]["site_count_guardrail"],
        )

    def test_release_delta_is_strict_and_common_rows_do_not_change(self) -> None:
        v62._validate_release_delta(RELEASE)
        v62._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v62.ADDED_ENTITY_KEYS)
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(
            {key for key in before if before[key] != after[key]},
            set(),
        )

    def test_last_observed_freshness_never_becomes_current_claim(self) -> None:
        freshness = {
            row["stable_key"]: row
            for row in rows(RELEASE / "lifecycle_freshness.csv")
        }
        self.assertEqual(len(freshness), 415)
        expected = {
            APPLIED_PHASE_KEY: ("operational", "2026-07-01", "19"),
            DATABANK_PROJECT_KEY: ("under_construction", "2026-05-14", "67"),
            APPLIED_PARENT_KEY: ("under_construction", "2026-04-08", "103"),
        }
        for key, (status, observed, age) in expected.items():
            row = freshness[key]
            with self.subTest(stable_key=key):
                self.assertEqual(row["last_observed_status"], status)
                self.assertEqual(row["last_observed_status_as_of"], observed)
                self.assertEqual(row["observation_age_days"], age)
                self.assertEqual(row["current_status_classification"], "unknown")
                self.assertEqual(row["current_construction_claim"], "false")
        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(entities[APPLIED_PHASE_KEY]["status"], "operational")
        self.assertEqual(entities[DATABANK_PROJECT_KEY]["status"], "under_construction")
        self.assertEqual(entities[APPLIED_PARENT_KEY]["status"], "under_construction")
        base_entities = {
            row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")
        }
        self.assertEqual(entities[APPLIED_PARENT_KEY], base_entities[APPLIED_PARENT_KEY])

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v62 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v7.validate_open_seed_release_v7(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 730)
        self.assertEqual(manifest["lifecycle_status_semantics"], "last_observed")
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
            [sys.executable, str(ROOT / "scripts/build_open_seed_v62.py")],
            cwd=WORKSPACE,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("definition already exists; refusing overwrite", result.stderr)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(v62.tree_digest(RELEASE), TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
