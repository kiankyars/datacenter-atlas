from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v71")
shim = importlib.import_module("datacenter_atlas.open_seed_v71")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v70.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v70"
RECORDED_AT = "2026-07-21T10:17:38Z"

DEFINITION_PIN = (
    86_839,
    "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38",
)
MANIFEST_PIN = (
    12_577,
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
)
TREE_PIN = "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"
RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_813,
        "67f9690a778af7d8552c4b03f58ebc017cce8e0588e9dd32102f2130eca9be3d",
    ),
    "README.md": (
        4_366,
        "9c8b237ec698b87cbb40cfc2b9154680883fb6b7af17d9980b20ee574f5ef803",
    ),
    "atlas.geojson": (
        2_858_831,
        "7eaf66f3f7a760901dd2ad75d3c7e07c90d4bdfea5120e35ea9f6f7225c31a8d",
    ),
    "capacity_estimates.csv": (
        256_289,
        "a517f58ceae4c8232fab6b9135e02f8096b2fa2cda3f77b053072adb78866729",
    ),
    "construction_pipeline.csv": (
        531_171,
        "2973f164b2e19b3f816fef7c5d6dddfb41922978bd1b28f1bab54c162907db32",
    ),
    "construction_source_signals.csv": (
        342_202,
        "3c5be2bade1394de4f0d3eaa611d84d757b51cdfbe0a23006e0a3b2f9b1ef93c",
    ),
    "entities.csv": (
        879_464,
        "a8ec778ce2abf5a89a7a9c6a006fa7bef9b8378d820cffcb794a10b195fd82f9",
    ),
    "evidence.csv": (
        201_471,
        "62bae2503599cc65fad1945dee28985b202c2c4bab60751af6bfd4a8a7b626dd",
    ),
    "lifecycle_freshness.csv": (
        137_020,
        "d3d035b9a24c6100b4a7363b76de3d77fc6b88041fe524c705f1f9c330192d37",
    ),
    "manifest.json": MANIFEST_PIN,
    "resolution_candidates.csv": (
        5_943,
        "3cfeca874cc5f1ef6e8c2731c80bf8552b7b410f4c79b7103c5c5650d68c67f4",
    ),
    "resolution_candidates.json": (
        8_870,
        "97cecb13f9f7adba721b499d9f1247fb85786be02a0c005acf1809c02c29cdab",
    ),
    "source_inputs.json": (
        317_371,
        "6c4fdf095da9c0b36102f9685e254ca74665bd5b5496c6043fef2f572e3a5288",
    ),
    "summary.json": (
        3_201,
        "e7763f341453a1b28899b404710a1a3249e9ca8b5ea19cb629d67e1f706415b1",
    ),
}

OBSERVATION_CONTRACT = {
    "curated:arnes-maribor-data-center-site:source-scoped-development": (
        "baf0d5dc-9f35-5fa7-be2c-0a80dce74d0d",
        "2025-05-06",
    ),
    "curated:kio-tec-guatemala-campus:second-data-center": (
        "87cd441a-81fa-530e-8038-684037cf451d",
        "2025-09-25",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OpenSeedV71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v71-test-")
        cls.connection = core._build_database(
            cls.base,
            paths,
            Path(cls.temporary.name) / "v71.sqlite",
            recorded_at=RECORDED_AT,
        )
        cls.base_connection = core.v69._populate_database(
            cls.base,
            core._base_paths(cls.base),
            Path(cls.temporary.name) / "v70.sqlite",
            recorded_at=RECORDED_AT,
        )
        cls.paths = paths

    @classmethod
    def tearDownClass(cls) -> None:
        cls.base_connection.close()
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_definition_release_and_every_file_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(
            (
                (RELEASE / "manifest.json").stat().st_size,
                sha256(RELEASE / "manifest.json"),
            ),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {item.name for item in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            item = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual((item.stat().st_size, sha256(item)), expected)
                self.assertFalse(item.is_symlink())
                self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o444)

    def test_exact_v70_adjacency_preserves_coordinates_and_appends_two(self) -> None:
        self.assertEqual((len(self.base["curated_inputs"]), len(self.selected)), (391, 393))
        self.assertEqual(self.selected[:391], self.base["curated_inputs"])
        self.assertEqual(self.selected, self.definition["curated_inputs"])
        self.assertEqual(
            self.selected[-2:],
            [
                {"path": relative, "sha256": core.ADDITION_PINS[relative][1]}
                for relative in sorted(core.ADDITION_PINS)
            ],
        )
        selected_paths = {row["path"] for row in self.selected}
        self.assertTrue(
            {replacement.successor_path for replacement in core.v70.REPLACEMENTS}
            <= selected_paths
        )
        self.assertFalse(
            {replacement.predecessor_path for replacement in core.v70.REPLACEMENTS}
            & selected_paths
        )
        self.assertFalse(set(core.REJECTED_V1_SOURCE_PINS) & selected_paths)
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

    def test_corrective_wrapper_and_rejected_v1_lineage_are_exact(self) -> None:
        state = core._validate_lineage()
        self.assertEqual(
            state,
            {
                "regional_manifest_sha256": core.REGIONAL_MANIFEST_SHA256,
                "regional_tree_sha256": core.REGIONAL_PHYSICAL_TREE_SHA256,
                "incident_manifest_sha256": core.TEMPORAL_INCIDENT_MANIFEST_SHA256,
                "incident_tree_sha256": core.TEMPORAL_INCIDENT_PHYSICAL_TREE_SHA256,
                "rejected_v1_manifest_sha256": core.REJECTED_V1_MANIFEST_SHA256,
                "rejected_v1_tree_sha256": core.REJECTED_V1_PHYSICAL_TREE_SHA256,
            },
        )
        incident = json.loads((core.TEMPORAL_INCIDENT / "incident.json").read_text())
        self.assertTrue(
            all(
                row["acceptance_status"] == "non_accepted"
                for row in incident["subjects"]
            )
        )
        snapshot = json.loads((core.REGIONAL_ARTIFACT / "source-snapshot.json").read_text())
        self.assertEqual(
            {row["path"] for row in snapshot["source_records"]},
            set(core.ADDITION_PINS),
        )
        self.assertTrue(all(row["seeded"] is False for row in snapshot["source_records"]))

    def test_database_delta_roles_capacity_and_observation_ids_are_exact(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            )
        }
        self.assertEqual(
            counts,
            {
                "entities": 810,
                "evidence": 634,
                "entity_snapshots": 830,
                "lifecycle_observations": 474,
                "capacity_estimates": 533,
                "operating_model_observations": 56,
                "workload_observations": 128,
            },
        )
        before_evidence = set(core.v70._evidence_by_key(self.base_connection))
        after_evidence = set(core.v70._evidence_by_key(self.connection))
        self.assertEqual(after_evidence - before_evidence, core.ADDED_EVIDENCE_KEYS)

        placeholders = ",".join("?" for _ in OBSERVATION_CONTRACT)
        rows = self.connection.execute(
            f"""
            SELECT entities.stable_key, lifecycle_observations.id,
                   lifecycle_observations.as_of_date,
                   lifecycle_observations.recorded_at
            FROM lifecycle_observations
            JOIN entities ON entities.id = lifecycle_observations.entity_id
            WHERE entities.stable_key IN ({placeholders})
            """,
            tuple(OBSERVATION_CONTRACT),
        ).fetchall()
        self.assertEqual(
            {
                row[0]: (row[1], row[2], row[3]) for row in rows
            },
            {
                key: (observation_id, as_of_date, RECORDED_AT)
                for key, (observation_id, as_of_date) in OBSERVATION_CONTRACT.items()
            },
        )
        regional_keys = tuple(sorted(core.ADDED_ENTITY_KEYS))
        regional_placeholders = ",".join("?" for _ in regional_keys)
        regional_text = " ".join(
            str(value)
            for row in self.connection.execute(
                f"""
                SELECT entities.stable_key, entity_snapshots.name,
                       entity_snapshots.tags_json
                FROM entity_snapshots JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN ({regional_placeholders})
                """,
                regional_keys,
            )
            for value in row
        )
        self.assertNotIn("gtm2", regional_text.casefold())

    def test_public_delta_is_last_observed_and_coordinate_neutral(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        core._validate_release_facts(RELEASE, recorded_at=RECORDED_AT)
        summary = json.loads((RELEASE / "summary.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(
            {
                "entities": summary["entities_total"],
                "database_evidence": summary["evidence_total"],
                "exported_evidence": manifest["evidence_records"],
                "capacity": manifest["capacity_estimates"],
                "pipeline": manifest["construction_pipeline_records"],
                "signals": manifest["construction_source_signals"],
                "freshness": manifest["lifecycle_freshness_records"],
                "located_entities": summary["entities_with_coordinates"],
                "located_campuses": summary["campuses_with_coordinates"],
                "families": len(manifest["source_families"]),
            },
            {
                "entities": 810,
                "database_evidence": 634,
                "exported_evidence": 512,
                "capacity": 532,
                "pipeline": 416,
                "signals": 318,
                "freshness": 458,
                "located_entities": 189,
                "located_campuses": 131,
                "families": 288,
            },
        )

    def test_temporal_chain_includes_source_birth_and_evidence_completion(self) -> None:
        recorded = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(recorded, datetime.now(timezone.utc))
        for item in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            self.assertLessEqual(
                datetime.fromtimestamp(item.stat().st_birthtime, timezone.utc),
                recorded,
            )
            self.assertLessEqual(
                datetime.fromtimestamp(item.stat().st_mtime, timezone.utc),
                recorded,
            )
        for relative in core.ADDITION_PINS:
            source = ROOT / relative
            self.assertLessEqual(
                datetime.fromtimestamp(source.stat().st_birthtime, timezone.utc),
                recorded,
            )
            document = json.loads(source.read_text())
            for evidence in document["evidence"]:
                retrieved = datetime.fromisoformat(
                    evidence["retrieved_at"].replace("Z", "+00:00")
                )
                self.assertLessEqual(retrieved, recorded)
        with self.assertRaisesRegex(ValueError, "later than validation wall clock"):
            core._validate_definition(
                self.definition,
                self.base,
                validation_wall_clock=recorded - timedelta(seconds=1),
            )

    def test_offline_double_replay_publication_collision_and_symlink_fail_closed(self) -> None:
        self.assertIs(core.validate_open_seed_v71, shim.validate_open_seed_v71)
        error = AssertionError("v71 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = shim.validate_open_seed_v71(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 810)
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core.validate_open_seed_v71(replay_count=1)
        guard = core._guard_state()
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core.build_open_seed_v71()
        self.assertEqual(core._guard_state(), guard)
        with tempfile.TemporaryDirectory(prefix="v71-symlink-") as temporary:
            linked = Path(temporary) / RELEASE.name
            os.symlink(RELEASE, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core.validate_open_seed_v71(DEFINITION, linked)

    def test_input_order_is_canonical_and_import_order_is_semantically_stable(self) -> None:
        first, first_paths = core.selected_inputs(self.base, recorded_at=RECORDED_AT)
        second, second_paths = core.selected_inputs(self.base, recorded_at=RECORDED_AT)
        self.assertEqual((first, first_paths), (second, second_paths))
        with patch.object(core, "ADDITION_PINS", dict(reversed(core.ADDITION_PINS.items()))):
            with self.assertRaisesRegex(ValueError, "canonical additions"):
                core.selected_inputs(self.base, recorded_at=RECORDED_AT)

        reversed_paths = self.paths[:-2] + list(reversed(self.paths[-2:]))
        with tempfile.TemporaryDirectory(prefix="v71-reversed-") as temporary:
            reverse = core.v69._populate_database(
                self.base,
                reversed_paths,
                Path(temporary) / "atlas.sqlite",
                recorded_at=RECORDED_AT,
            )
            try:
                for table in (
                    "entities",
                    "evidence",
                    "campuses",
                    "projects",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                ):
                    self.assertEqual(
                        core._table_state(self.connection, table),
                        core._table_state(reverse, table),
                        table,
                    )
            finally:
                reverse.close()

    def test_v1_and_v2_coexistence_conflicts_instead_of_silent_merge(self) -> None:
        with tempfile.TemporaryDirectory(prefix="v71-v1-v2-collision-") as temporary:
            connection = core.v69._populate_database(
                self.base,
                core._base_paths(self.base),
                Path(temporary) / "atlas.sqlite",
                recorded_at=RECORDED_AT,
            )
            try:
                core.v69._import_curated(
                    connection,
                    ROOT
                    / "sources/curated-official-2026-07-21-arnes-maribor-construction-start.json",
                    recorded_at=RECORDED_AT,
                )
                with self.assertRaisesRegex(ValueError, "conflicts on persisted fields"):
                    core.v69._import_curated(
                        connection,
                        ROOT
                        / "sources/curated-official-2026-07-21-arnes-maribor-construction-start-v2.json",
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

    def test_accepted_v70_base_remains_byte_exact(self) -> None:
        self.assertEqual(sha256(BASE_DEFINITION), core.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
