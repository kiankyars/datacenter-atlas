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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v6 as release_v6
    from datacenter_atlas.datacenter_atlas import open_seed_v61 as v61
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v6 as release_v6
    from datacenter_atlas import open_seed_v61 as v61


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v61.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v61"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v60"
SOURCE = ROOT / next(iter(release_v6.ADDITION_PINS))

DEFINITION_SHA256 = "c407c73a069783ea75de8e3bc86bbfb8a15d71abb67de33e8ba3d3acc5a428e6"
MANIFEST_SHA256 = "6388b58b043f43fa2cdc02af31504cf18cc2ec334e14f2f2075f52b15204fd14"
TREE_SHA256 = "de9a924113b5fae4ace596fdbd469f52a79646d0de677e7bcf17aedfa09693f2"
CAMPUS_KEY = "curated:batelco-qareeb-beyon-data-oasis-edge-data-center"
PROJECT_KEY = f"{CAMPUS_KEY}:facility-build"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (4_518, "acbb856b2ed6c678933ddb10326b692cab45fe303b81d7117e331f60a31eec66"),
    "README.md": (3_453, "25120aebbff441c79c5d91474f17f105bd5b8f0de52d689f58053df09fad8ddb"),
    "atlas.geojson": (2_572_933, "620b691407ef3d6f40bac6cc4ea8734b26fe6b9e11f488f4302ef9bfc2677572"),
    "capacity_estimates.csv": (237_082, "8e649f66e1bf4926bfa51916926e51de0613a98fbe56dfb0d5e7b6e49d809d07"),
    "construction_pipeline.csv": (480_645, "944f8e8a3812918c7ca58b84d576cc156f108be692c8210e11bc33e39c07d965"),
    "construction_source_signals.csv": (303_188, "d1267b2b36a8f484f8ad652a970f426e1bf7627fe8d61a006d9b6cc7f3819bd6"),
    "entities.csv": (796_819, "bb563cd50dc8f346c3e6ce195d8c14f1a09dfffd620d5afc6548d5267426bfed"),
    "evidence.csv": (172_297, "7239fb6a52642155171d69be0f8f24d0170d589dd00dc00d47ef7a5576e48c79"),
    "lifecycle_freshness.csv": (123_420, "8d0a6addec940fc65ea8ae02885c8ad0105600618dc9c78f02153182c44581b2"),
    "manifest.json": (10_804, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_989, "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264"),
    "resolution_candidates.json": (7_384, "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7"),
    "source_inputs.json": (264_910, "0b40b976c175e7341a04b9fd56a84b9e810dec6bc11a049c12d541c49351afa8"),
    "summary.json": (3_065, "dfbc07691f54e80e5b04334083965895434b9fce32bb0e735e57e1eb020b14b2"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV61Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v61-test-db-")
        cls.selected_rows, selected_paths = v61.selected_inputs(cls.base_definition)
        cls.connection = v61._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 76_306)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v61.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)

        self.assertEqual(self.definition["release_id"], release_v6.RELEASE_ID)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T04:10:00Z"},
        )
        self.assertEqual(self.definition["publication_contract_version"], 4)
        self.assertEqual(
            self.definition["freshness_contract"], release_v6.freshness_contract()
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
                "entities": 727,
                "evidence_records": 440,
                "capacity_estimates": 500,
                "construction_pipeline_records": 372,
                "construction_source_signals": 279,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 413,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )

    def test_exact_v60_adjacency_and_calendar_boundary(self) -> None:
        before = {
            row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]
        }
        after = {row["path"]: row["sha256"] for row in self.definition["curated_inputs"]}
        self.assertEqual((len(before), len(after)), (347, 348))
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(set(after) - set(before), set(release_v6.ADDITION_PINS))
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertFalse(
            (
                release_v6.STALE_EXCLUSIONS
                | release_v6.PENDING_NEXT_DAY_EXCLUSIONS
                | release_v6.OUT_OF_SCOPE_EXCLUSIONS
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
        self.assertEqual(versions, {"1.0": 316, "1.1": 32})

    def test_database_contract_preserves_qareeb_boundaries(self) -> None:
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
                "entities": 727,
                "evidence": 542,
                "lifecycle_observations": 428,
                "capacity_estimates": 501,
                "entity_snapshots": 746,
                "operating_model_observations": 51,
                "workload_observations": 122,
            },
        )
        v61._validate_database_delta(self.connection)
        lifecycle = list(
            self.connection.execute(
                "SELECT status, as_of_date FROM lifecycle_observations "
                "JOIN entities ON entities.id = lifecycle_observations.entity_id "
                "WHERE entities.stable_key = ? ORDER BY as_of_date",
                (PROJECT_KEY,),
            )
        )
        self.assertEqual(
            [tuple(row) for row in lifecycle],
            [("under_construction", "2025-02-05"), ("commissioning", "2026-01-13")],
        )
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(source["capacities"], [])
        self.assertEqual(source["workloads"], [])
        self.assertEqual(
            source["evidence"][1]["metadata"]["reported_scalable_space_square_metres"],
            6000,
        )
        stc_keys = {
            "curated:stc-bahrain-data-center",
            "curated:stc-bahrain-data-center:facility-build",
        }
        self.assertTrue({CAMPUS_KEY, PROJECT_KEY}.isdisjoint(stc_keys))
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM entities WHERE stable_key IN (?, ?, ?, ?)",
                (CAMPUS_KEY, PROJECT_KEY, *sorted(stc_keys)),
            ).fetchone()[0],
            4,
        )

    def test_release_delta_is_strict_and_common_rows_do_not_change(self) -> None:
        v61._validate_release_delta(RELEASE)
        v61._validate_release_facts(RELEASE)
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(set(after) - set(before), v61.ADDED_ENTITY_KEYS)
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
        self.assertEqual(len(freshness), 413)
        qareeb = freshness[PROJECT_KEY]
        self.assertEqual(qareeb["last_observed_status"], "commissioning")
        self.assertEqual(qareeb["last_observed_status_as_of"], "2026-01-13")
        self.assertEqual(qareeb["observation_age_days"], "188")
        self.assertEqual(qareeb["current_status_classification"], "unknown")
        self.assertEqual(qareeb["current_construction_claim"], "false")
        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(entities[PROJECT_KEY]["status"], "commissioning")
        self.assertEqual(entities[PROJECT_KEY]["status_as_of"], "2026-01-13")
        self.assertEqual(
            (RELEASE / "capacity_estimates.csv").read_bytes(),
            (BASE_RELEASE / "capacity_estimates.csv").read_bytes(),
        )

    def test_offline_double_rebuild_validator(self) -> None:
        error = AssertionError("v61 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = release_v6.validate_open_seed_release_v6(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 727)
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
            [sys.executable, str(ROOT / "scripts/build_open_seed_v61.py")],
            cwd=WORKSPACE,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("definition already exists; refusing overwrite", result.stderr)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(v61.tree_digest(RELEASE), TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
