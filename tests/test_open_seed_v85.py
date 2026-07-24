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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v85")
shim = importlib.import_module("datacenter_atlas.open_seed_v85")
curated_v11 = importlib.import_module("datacenter_atlas.datacenter_atlas.curated_v11")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v85.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v85"
BUILDER = ROOT / "scripts/build_open_seed_v85.py"
DRY_RUN_RECORDED_AT = "2026-07-21T20:00:00Z"

RECORDED_AT = "2026-07-21T20:00:55Z"
DEFINITION_PIN = (
    101_105,
    "e61641a6364e86f011f31b8a81e2fbc53979cdf80ada219fc1538ade99b22b1b",
)
MANIFEST_PIN = (
    15_331,
    "fc89a45fcc9a7ce00c1d523b124cb3253d9de52f7ff11faad32f8ba42e6934c8",
)
TREE_PIN = "010075fac16363fa61845f7b10fef4db09442ffefc46a5b90002fec11e922900"
RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        7_510,
        "8045598e08c20df1c58293e1b120e486c6674f42c0afa58b9f36226d3b21f085",
    ),
    "README.md": (
        4_075,
        "1c616de80e9c4723f089226b6ae10ab3d39ae118da01a01aad91d7c151f28d9a",
    ),
    "atlas.geojson": (
        3_200_907,
        "829470458b9ce64fbbe2845ba537d3e745ee29f0d216dbdb7ffc5cb52369d663",
    ),
    "capacity_estimates.csv": (
        264_653,
        "8e0385503ed9e7447b71c5c6676a1c0a55d69f1f008f84f11a06f0704dfb5dab",
    ),
    "construction_pipeline.csv": (
        576_333,
        "8956156816bd76d5b74a690ecb76acf2a39e1ffce7116f28a56d85787026a4d8",
    ),
    "construction_source_signals.csv": (
        390_134,
        "3e3b9f77835bda3559d797cc23ff6d6841d62a1e2696ea656455c6f5df39387d",
    ),
    "entities.csv": (
        970_598,
        "1ba3646193915e568eaea72fb14b16ba101d2a238cc2f67d9470bd7a2b225d7e",
    ),
    "evidence.csv": (
        237_439,
        "e26dd7b4ff1de82ab0493cda3db0f890477b43387d07775539081b6843e3d09b",
    ),
    "lifecycle_freshness.csv": (
        153_786,
        "b806c1ff2b0e5f718e14599ad4903efeb5bd26ab5a8a6a46c12e31af8a3ed8ac",
    ),
    "manifest.json": MANIFEST_PIN,
    "resolution_candidates.csv": (
        8_749,
        "ac5b26629b02892e8f5a950221a2f0fcffcb848f40cfc47ae3ae6fb4da14e0cc",
    ),
    "resolution_candidates.json": (
        13_272,
        "a5d26da56b133ffe32f7b6f9d57f123af7bb3f647636301e678036fcb029e87d",
    ),
    "source_inputs.json": (
        380_974,
        "1296776ea53ccc8fb4e5a815577c696c258475208984402f5db94c8acd6f651a",
    ),
    "summary.json": (
        3_446,
        "782959d7494664ad26d0c88d90a8db029eb9462c04d70d612c2c821e35ae6dfc",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV85Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(core.BASE_DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base,
            recorded_at=DRY_RUN_RECORDED_AT,
            validation_wall_clock=datetime.fromisoformat(
                DRY_RUN_RECORDED_AT.replace("Z", "+00:00")
            ),
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v85-test-")
        root = Path(cls.temporary.name)
        cls.connection = core._build_database(
            cls.base,
            paths,
            root / "atlas.sqlite",
            recorded_at=DRY_RUN_RECORDED_AT,
        )
        cls.release = root / "release"
        core._write_release(
            cls.connection,
            cls.release,
            recorded_at=DRY_RUN_RECORDED_AT,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("open seed v85 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_exact_v84_adjacency_replaces_only_coordinate_v6_indices(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 447)
        self.assertEqual(len(after), 447)
        changed = [
            (index, old, new)
            for index, (old, new) in enumerate(zip(before, after, strict=True))
            if old != new
        ]
        self.assertEqual(
            [index for index, _old, _new in changed],
            [428, 429, 430, 431, 433, 434, 435],
        )
        self.assertEqual(
            [new["path"] for _index, _old, new in changed],
            [row.successor_path for row in core.REPLACEMENTS],
        )
        for index, expected in core.UNCHANGED_INDEX_PINS.items():
            self.assertEqual(
                (after[index]["path"], after[index]["sha256"]), expected
            )

    def test_curated_v11_preserves_geometry_only_null_coordinates(self) -> None:
        document = json.loads((ROOT / core.REPLACEMENTS[0].successor_path).read_text())
        for name, geometry_type in (("campus", "MultiPolygon"), ("project", "Polygon")):
            record = curated_v11._entity_record(
                document[name], f"fixture.{name}", "fixture"
            )
            self.assertIsNone(record.latitude)
            self.assertIsNone(record.longitude)
            self.assertEqual(record.geometry["type"], geometry_type)

        snapshots = {
            row["stable_key"]: row
            for row in self.connection.execute(
                """
                SELECT entities.stable_key, latitude, longitude, geometry_json
                FROM entity_snapshots
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN (?, ?)
                """,
                tuple(sorted(core.ATH04_KEYS)),
            )
        }
        self.assertEqual(set(snapshots), core.ATH04_KEYS)
        self.assertEqual(
            {json.loads(row["geometry_json"])["type"] for row in snapshots.values()},
            {"Polygon", "MultiPolygon"},
        )
        self.assertTrue(
            all(
                row["latitude"] is None and row["longitude"] is None
                for row in snapshots.values()
            )
        )

    def test_database_and_public_coordinate_only_contract(self) -> None:
        expected_counts = {
            "entities": 917,
            "entity_snapshots": 938,
            "evidence": 754,
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
        core._validate_release_delta(
            self.release, recorded_at=DRY_RUN_RECORDED_AT
        )
        core._validate_release_facts(
            self.release, recorded_at=DRY_RUN_RECORDED_AT
        )
        manifest = json.loads((self.release / "manifest.json").read_text())
        summary = json.loads((self.release / "summary.json").read_text())
        atlas = json.loads((self.release / "atlas.geojson").read_text())
        geometry_types: dict[str, int] = {}
        for feature in atlas["features"]:
            if feature["geometry"] is None:
                continue
            kind = feature["geometry"]["type"]
            geometry_types[kind] = geometry_types.get(kind, 0) + 1
        self.assertEqual(
            geometry_types, {"Point": 133, "Polygon": 81, "MultiPolygon": 1}
        )
        self.assertEqual(summary["entities_with_coordinates"], 213)
        self.assertEqual(summary["campuses_with_coordinates"], 141)
        self.assertEqual(summary["evidence_by_kind"]["government_record"], 119)
        self.assertEqual(summary["evidence_by_kind"]["company_disclosure"], 557)
        self.assertEqual(manifest["evidence_records"], 603)
        self.assertEqual(manifest["resolution_candidates"], 9)
        self.assertIs(manifest["geometry_only_representative_point_inferred"], False)
        self.assertEqual(
            len(json.loads((self.release / "source_inputs.json").read_text())["sources"]),
            530,
        )

    def test_resolution_advisories_and_ath04_point_suppression(self) -> None:
        candidates = json.loads(
            (self.release / "resolution_candidates.json").read_text()
        )
        by_pair = {
            (row["left_name"], row["right_name"]): row for row in candidates
        }
        self.assertEqual(
            (
                by_pair[
                    (
                        "NEXTDC S4 Sydney Data Center Campus",
                        "CDC Eastern Creek Campus",
                    )
                ]["distance_m"],
                by_pair[
                    (
                        "NEXTDC S4 Sydney Data Center Campus",
                        "CDC Eastern Creek Campus",
                    )
                ]["score"],
            ),
            (1596.601, 0.345469),
        )
        self.assertEqual(
            (
                by_pair[
                    ("DATA4 ATH1 Paiania Campus", "Ten Brinke Spata Data Center")
                ]["distance_m"],
                by_pair[
                    ("DATA4 ATH1 Paiania Campus", "Ten Brinke Spata Data Center")
                ]["score"],
            ),
            (4029.121, 0.148476),
        )
        self.assertNotIn(
            ("AirTrunk SYD3 Western Sydney Campus", "CDC Eastern Creek Campus"),
            by_pair,
        )
        entities = {
            row["stable_key"]: row for row in csv_rows(self.release / "entities.csv")
        }
        for stable_key in core.ATH04_KEYS:
            self.assertEqual(entities[stable_key]["latitude"], "")
            self.assertEqual(entities[stable_key]["longitude"], "")
        signals = [
            row
            for row in csv_rows(self.release / "construction_source_signals.csv")
            if row["representative_stable_key"] == core.REPLACEMENTS[0].project_key
        ]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["representative_latitude"], "")
        self.assertEqual(signals[0]["representative_longitude"], "")

    def test_v84_replay_is_unchanged_under_curated_v11_wrapper(self) -> None:
        with self._network_guard():
            manifest = core.v84.validate_open_seed_v84()
        self.assertEqual(manifest["recorded_at"], core.BASE_RECORDED_AT)
        self.assertEqual(
            (
                (core.BASE_RELEASE / "manifest.json").stat().st_size,
                sha256(core.BASE_RELEASE / "manifest.json"),
            ),
            core.BASE_MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(core.BASE_RELEASE), core.BASE_TREE_SHA256)

    def test_publication_collision_rolls_back_without_residue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v85-collision-") as temporary:
            root = Path(temporary)
            sources = root / "sources"
            releases = root / "releases"
            sources.mkdir()
            releases.mkdir()
            definition = sources / core.DEFINITION.name
            release = releases / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            original_promote = core.v69.promote_noreplace

            def collide_on_definition(source: Path, destination: Path) -> None:
                if Path(destination) == definition:
                    raise FileExistsError("injected definition collision")
                original_promote(source, destination)

            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
            target_text = target.isoformat(timespec="seconds").replace("+00:00", "Z")
            with (
                self._network_guard(),
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                patch.object(core, "_wait_until", return_value=None),
                patch.object(core.v69, "promote_noreplace", side_effect=collide_on_definition),
            ):
                with self.assertRaisesRegex(FileExistsError, "injected"):
                    core.build_open_seed_v85(recorded_at=target_text)
            self.assertFalse(definition.exists())
            self.assertFalse(release.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(sources.iterdir()), [])
            self.assertEqual(list(releases.iterdir()), [])

    def test_frozen_publication_or_clean_prepublication_state(self) -> None:
        present = (DEFINITION.exists(), RELEASE.exists())
        self.assertNotIn(present, {(True, False), (False, True)})
        if present == (False, False):
            return
        self.assertIsNotNone(RECORDED_AT)
        self.assertIsNotNone(DEFINITION_PIN)
        self.assertIsNotNone(MANIFEST_PIN)
        self.assertIsNotNone(TREE_PIN)
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
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
        with self._network_guard():
            manifest = shim.validate_open_seed_v85(DEFINITION, RELEASE)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")


if __name__ == "__main__":
    unittest.main()
