from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v70")
shim = importlib.import_module("datacenter_atlas.open_seed_v70")

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v70.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v70"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v69.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v69"
RECORDED_AT = "2026-07-21T10:12:57Z"

DEFINITION_PIN = (
    86_383,
    "88cb1163b0a4c2dafc5c09a19a1a5dbc24bd73ab6d3069e78411041eb5f58441",
)
MANIFEST_PIN = (
    12_512,
    "56ec8c0ba5eff23ebc259326041de037bd656f6fa40bf878319dcfd03543d2ca",
)
TREE_PIN = "740526d433a3970071fc5d91129982804796cb2ba6de6d0c3036e06a60f94656"
RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        5_757,
        "61aa07d2663a6c2d2f0f9f5a537e3b69ddbfd530e5296258977c08868a0a0141",
    ),
    "README.md": (
        4_384,
        "ce0c6e90cbd1d3094a03739db8543f4c3ddfe7185ab38529404d5afef06134ff",
    ),
    "atlas.geojson": (
        2_845_679,
        "9ba202d07487cd109c46f886f31f46aff9164395504141a3eefb1bb2c02f9d57",
    ),
    "capacity_estimates.csv": (
        255_161,
        "63d5b8768bd105e30e4f9d4d27efecce2c0d64c66da08dd42b53234b2aff9169",
    ),
    "construction_pipeline.csv": (
        528_706,
        "2017c3cc381de3a016c35b856782db5ac6c5c3f5d0d5b41b6eac74565240fd68",
    ),
    "construction_source_signals.csv": (
        340_154,
        "bce3d33a6f2e5d98334cf870cf1bddb828cace6486ca3bd6acf84c82e648d526",
    ),
    "entities.csv": (
        875_669,
        "1a61e7bd04b1447f4cf8c5351630ace01b0c49402764f96e40b8d85743009baa",
    ),
    "evidence.csv": (
        200_550,
        "de420a3fdbe0d28e4d1ea8632008e570f13cf197ae6dfe2ffb98fa3e8825cf97",
    ),
    "lifecycle_freshness.csv": (
        136_421,
        "942d147d416dc3455457dca67babbfd875c58b94bcd74529f3e5d66f8d5f5ace",
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
        315_870,
        "058ba98f1aa14944597e7d84af71ab524194b1ba759fea0f6a8ff140ff4d91c8",
    ),
    "summary.json": (
        3_162,
        "87435bcb40ad8ae4ddf19cf4543d3b51097f3898a00e3cc0f7523f82533b68fa",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OpenSeedV70Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.selected, paths = core.selected_inputs(
            cls.base, recorded_at=RECORDED_AT
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v70-test-")
        cls.connection = core._build_database(
            cls.base,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
            recorded_at=RECORDED_AT,
        )
        cls.base_connection = core.v69._populate_database(
            cls.base,
            core._base_paths(cls.base),
            Path(cls.temporary.name) / "v69.sqlite",
            recorded_at=RECORDED_AT,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.base_connection.close()
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_definition_release_and_every_file_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(
            ((RELEASE / "manifest.json").stat().st_size, sha256(RELEASE / "manifest.json")),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_exact_v69_adjacency_replaces_three_rows_in_place(self) -> None:
        self.assertEqual(len(self.base["curated_inputs"]), 391)
        self.assertEqual(len(self.selected), 391)
        self.assertEqual(self.definition["curated_inputs"], self.selected)
        before_paths = [row["path"] for row in self.base["curated_inputs"]]
        after_paths = [row["path"] for row in self.selected]
        replaced_positions = set()
        for replacement in core.REPLACEMENTS:
            position = before_paths.index(replacement.predecessor_path)
            replaced_positions.add(position)
            self.assertEqual(after_paths[position], replacement.successor_path)
            self.assertNotIn(replacement.predecessor_path, after_paths)
            self.assertEqual(
                self.selected[position]["sha256"], replacement.successor_sha256
            )
        self.assertEqual(len(replaced_positions), 3)
        for index, row in enumerate(self.base["curated_inputs"]):
            if index not in replaced_positions:
                self.assertEqual(self.selected[index], row)
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
        self.assertNotIn("coordinate-v2.json", DEFINITION.read_text())

    def test_coordinate_v3_and_both_incidents_are_exact_lineage(self) -> None:
        state = core._validate_source_lineage()
        self.assertEqual(
            state,
            {
                "coordinate_manifest_sha256": core.COORDINATE_MANIFEST_SHA256,
                "coordinate_tree_sha256": core.COORDINATE_PHYSICAL_TREE_SHA256,
                "publication_incident_manifest_sha256": (
                    core.PUBLICATION_INCIDENT_MANIFEST_SHA256
                ),
                "temporal_incident_manifest_sha256": (
                    core.TEMPORAL_INCIDENT_MANIFEST_SHA256
                ),
            },
        )
        self.assertEqual(
            sha256(core.COORDINATE_ARTIFACT / "manifest.json"),
            core.COORDINATE_MANIFEST_SHA256,
        )
        self.assertEqual(
            core.v69.tree_digest(core.COORDINATE_ARTIFACT),
            core.COORDINATE_PHYSICAL_TREE_SHA256,
        )
        disposition = json.loads(
            (core.COORDINATE_ARTIFACT / "disposition.json").read_text()
        )
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])
        rejected = {
            row["path"]: row["reason"]
            for row in disposition["lineage"]["rejected_as_lineage"]
        }
        self.assertEqual(
            rejected["source_artifacts/site-coordinate-assessment-2026-07-21-v2"],
            "rejected_future_retrieved_at_metadata_at_publication",
        )

    def test_database_delta_is_three_evidence_and_six_located_snapshots_only(self) -> None:
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
                "entities": 806,
                "evidence": 631,
                "entity_snapshots": 826,
                "lifecycle_observations": 472,
                "capacity_estimates": 531,
                "operating_model_observations": 56,
                "workload_observations": 128,
            },
        )
        added = core._evidence_by_key(self.connection)
        evidence_ids = {added[key][0] for key in core.NEW_EVIDENCE_KEYS}
        self.assertEqual(
            set(core.NEW_EVIDENCE_KEYS),
            set(added) - set(core._evidence_by_key(self.base_connection)),
        )
        for table in (
            "lifecycle_observations",
            "capacity_estimates",
            "operating_model_observations",
            "workload_observations",
        ):
            placeholders = ",".join("?" for _ in evidence_ids)
            count = self.connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE evidence_id IN ({placeholders})",
                tuple(evidence_ids),
            ).fetchone()[0]
            self.assertEqual(count, 0, table)

    def test_public_delta_counts_and_current_status_guardrails(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        core._validate_release_facts(RELEASE, recorded_at=RECORDED_AT)
        summary = json.loads((RELEASE / "summary.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(
            {
                "entities": summary["entities_total"],
                "database_evidence": summary["evidence_total"],
                "exported_evidence": manifest["evidence_records"],
                "located_entities": summary["entities_with_coordinates"],
                "located_campuses": summary["campuses_with_coordinates"],
                "capacity": manifest["capacity_estimates"],
                "pipeline": manifest["construction_pipeline_records"],
                "signals": manifest["construction_source_signals"],
                "freshness": manifest["lifecycle_freshness_records"],
            },
            {
                "entities": 806,
                "database_evidence": 631,
                "exported_evidence": 510,
                "located_entities": 189,
                "located_campuses": 131,
                "capacity": 530,
                "pipeline": 414,
                "signals": 316,
                "freshness": 456,
            },
        )

    def test_publication_time_is_live_and_after_every_birth_and_mtime(self) -> None:
        recorded = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(recorded, datetime.now(timezone.utc))
        for path in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            with self.subTest(path=path.name):
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc),
                    recorded,
                )
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
                    recorded,
                )
        core._validate_publication_times(
            DEFINITION, RELEASE, recorded_at=RECORDED_AT
        )
        with self.assertRaisesRegex(ValueError, "later than validation wall clock"):
            core._validate_definition(
                self.definition,
                self.base,
                validation_wall_clock=recorded - timedelta(seconds=1),
            )

    def test_offline_replay_collision_order_and_future_fail_closed(self) -> None:
        self.assertIs(core.validate_open_seed_v70, shim.validate_open_seed_v70)
        error = AssertionError("v70 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            manifest = shim.validate_open_seed_v70(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 806)
        with self.assertRaisesRegex(ValueError, "exactly two offline replays"):
            core.validate_open_seed_v70(replay_count=1)
        guard = core._guard_state()
        with self.assertRaisesRegex(SystemExit, "definition already exists"):
            core.build_open_seed_v70()
        self.assertEqual(core._guard_state(), guard)

        reversed_replacements = tuple(reversed(core.REPLACEMENTS))
        with patch.object(core, "REPLACEMENTS", reversed_replacements):
            selected, _ = core.selected_inputs(
                self.base, recorded_at=RECORDED_AT
            )
        self.assertEqual(selected, self.selected)
        with self.assertRaisesRegex(ValueError, "later than the current build time"):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-22T00:00:00Z",
                validation_wall_clock=datetime.now(timezone.utc),
            )

    def test_accepted_v69_base_remains_byte_exact(self) -> None:
        self.assertEqual(sha256(BASE_DEFINITION), core.BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
