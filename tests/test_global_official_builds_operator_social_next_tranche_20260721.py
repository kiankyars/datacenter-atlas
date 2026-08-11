from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


try:
    tranche = importlib.import_module(
        "datacenter_atlas.datacenter_atlas."
        "global_official_builds_operator_social_next_tranche_20260721"
    )
except ModuleNotFoundError:
    tranche = importlib.import_module(
        "datacenter_atlas.global_official_builds_operator_social_next_tranche_20260721"
    )


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT / "source_artifacts/"
    "global-official-builds-operator-social-next-tranche-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-operator-social-next-20260721.HOCD94")
RECORDED_AT = "2026-07-21T19:50:53Z"
ARTIFACT_TREE_SHA256 = (
    "62ae7fa0fec98922068cadbb90af5dd26f3822ef85fe64f1ab222bfa569dbb2f"
)
ARTIFACT_PINS = {
    "README.md": (
        1_951,
        "9221f8c15fdd47b3c2976b487af9d8ba70c508a380ca815bf39b74ea139b85b2",
    ),
    "candidate-assessment.json": (
        6_085,
        "cca1476d69b9ead35efdbb5e9231354be947910ac788afd8bbae00f0704e5b11",
    ),
    "manifest.json": (
        1_755,
        "a6d20ce2f8a0eb16c86242f80d15f92addd328f4b04c9d2b5f7bb6d80abf19ff",
    ),
    "manifest.sha256": (
        80,
        "560af352387c2e0121f30dce7bf2ac47cfe447ea8f1d17a3add15ddac63bf23e",
    ),
    "retrieval-inventory.json": (
        20_582,
        "913bf60dabe51e5eb3db969a11c2c934c4cb678b6e833d295b5b19dd97c64c10",
    ),
    "rights-and-disposition.json": (
        1_216,
        "1cea3117990d90567f8d565b86eccd741f371604be3c9ec669b8aac2edae8d23",
    ),
    "source-snapshot.json": (
        6_498,
        "30aa3934301b4b5d092b044b15544b058ba1cad9cbcfb1725845fdd00d748d27",
    ),
}
SOURCE_PINS = {
    "curated-official-2026-07-21-stack-johor-first-120mw-current-build.json": (
        6_005,
        "171f44843154f28dc72ad3bcd1f066ec3becd5c36cb99c818716c82ab61883cc",
    ),
    "curated-official-2026-07-21-echelon-dub20-current-build.json": (
        5_601,
        "dd307d2df9ec64ddae59877e330dbaea97b43d604f8674500507395fdeaf79b7",
    ),
    "curated-official-2026-07-21-echelon-dub40-current-build.json": (
        3_603,
        "c3a7907e8708e2bb14c04b81fe7a23b79e02cca047328ab656cff2e4eac66810",
    ),
    "curated-official-2026-07-21-odata-sp04-phase2-current-build.json": (
        6_424,
        "e738abaae7e2263c2a3d73d0ac2517c714ce870821790f8729ba972e8844533d",
    ),
    "curated-official-2026-07-21-multidc-shoham-current-build.json": (
        6_372,
        "c9a0b9cbb83efaf7ada906054c67b3997b6d02b8c72c8203b9849e34918a8d16",
    ),
}


def sha256(target: Path) -> str:
    return hashlib.sha256(target.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsOperatorSocialNextTrancheTests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        stack.enter_context(
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        return stack

    def test_frozen_artifact_exact_closure_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(set(ARTIFACT_PINS), {item.name for item in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            target = ARTIFACT / name
            self.assertEqual((target.stat().st_size, sha256(target)), expected)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

        target_time = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime),
            target_time,
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target_time)
        for item in ARTIFACT.iterdir():
            metadata = item.stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime), target_time
            )
        for name in SOURCE_PINS:
            metadata = (ROOT / "sources" / name).stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime), target_time
            )
            self.assertGreaterEqual(metadata.st_ctime, target_time)

    def test_sources_are_exact_schema_v11_and_import_idempotently_offline(self) -> None:
        documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(documents))
        for name, expected in SOURCE_PINS.items():
            target = ROOT / "sources" / name
            self.assertFalse(target.is_symlink())
            self.assertEqual((target.stat().st_size, sha256(target)), expected)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o444)
            self.assertEqual(target.read_bytes(), tranche._canonical(documents[name]))
            for entity in ("campus", "project"):
                self.assertIsNone(documents[name][entity]["coordinates"])
                self.assertIsNone(documents[name][entity]["geometry"])
            self.assertEqual(documents[name]["operating_models"], [])
            self.assertEqual(documents[name]["workloads"], [])

        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for _ in range(2):
                for name in SOURCE_PINS:
                    adapter.import_file(
                        connection,
                        ROOT / "sources" / name,
                        recorded_at=RECORDED_AT,
                    )
            validate_database(connection)
            expected_counts = {
                "entities": 10,
                "entity_snapshots": 10,
                "evidence": 9,
                "lifecycle_observations": 5,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 2,
            }
            actual_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)
            capacities = [
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                    "FROM capacity_estimates AS c "
                    "JOIN entities AS e ON e.id=c.entity_id ORDER BY c.base"
                )
            ]
            self.assertEqual(
                capacities,
                [
                    (
                        "curated:multidc-shoham-campus",
                        "critical_it_mw",
                        "design",
                        "MW",
                        30.0,
                    ),
                    (
                        "curated:odata-dc-sp04-osasco-campus",
                        "critical_it_mw",
                        "design",
                        "MW",
                        48.0,
                    ),
                ],
            )
            lifecycle = [
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, l.status, l.as_of_date "
                    "FROM lifecycle_observations AS l "
                    "JOIN entities AS e ON e.id=l.entity_id "
                    "ORDER BY e.stable_key"
                )
            ]
            self.assertEqual(
                lifecycle,
                [
                    (
                        "curated:echelon-dub20-arklow-campus:current-build",
                        "under_construction",
                        "2026-03-27",
                    ),
                    (
                        "curated:echelon-dub40-dublin-campus:current-build",
                        "shell",
                        "2026-01-14",
                    ),
                    (
                        "curated:multidc-shoham-campus:current-build",
                        "under_construction",
                        "2026-06-03",
                    ),
                    (
                        "curated:odata-dc-sp04-osasco-campus:phase-2-expansion",
                        "under_construction",
                        "2026-06-18",
                    ),
                    (
                        "curated:stack-johor-iskandar-puteri-campus:first-building-current-build",
                        "under_construction",
                        "2026-01-27",
                    ),
                ],
            )

    def test_candidate_and_capacity_guardrails_are_exact(self) -> None:
        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["seed_eligible_count"],
                assessment["review_only_count"],
            ),
            (5, 5, 0),
        )
        self.assertTrue(all(row["seed_eligible"] for row in assessment["candidates"]))
        self.assertTrue(
            all(row["source_record_created"] for row in assessment["candidates"])
        )
        withheld = {
            value
            for row in assessment["candidates"]
            for value in row["withheld_non_normalized_power_labels"]
        }
        self.assertEqual(
            withheld,
            {
                "120MW building",
                "220MW campus",
                "300MW substation",
                "Phase 2 24 MW wording",
                "32MVA+32MVA",
                "16MVA",
                "150MVA",
            },
        )
        normalized = [
            capacity
            for row in assessment["candidates"]
            for capacity in row["normalized_capacities"]
        ]
        self.assertEqual(
            sorted((row["metric"], row["stage"], row["base"]) for row in normalized),
            [
                ("critical_it_mw", "design", 30.0),
                ("critical_it_mw", "design", 48.0),
            ],
        )
        serialized = json.dumps(assessment, sort_keys=True).casefold()
        for forbidden in (
            '"metric": "pue"',
            '"metric": "annual_energy_mwh"',
            '"metric": "generation_nameplate_mw"',
            '"metric": "gross_facility_mw"',
            '"metric": "grid_connection_mw"',
            '"coordinates": [',
            '"geometry": {',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_capture_tree_binds_direct_bodies_and_404s_create_no_claim(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        tranche._validate_capture_directory(capture)
        self.assertEqual(len(list(capture.iterdir())), 60)
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        bodies = {
            "stack_social_physical.body": "Construction is progressing on the first 120MW data center",
            "echelon_dub20_green_energy_park.body": "Construction is underway and due to be completed by 2028",
            "echelon_dub40_social.body": "structural steel and core progressing",
            "odata_sp04_phase2_social.body": "mobilização do canteiro",
            "multidc_social.body": "Construction is progressing on site",
            "odata_sp04_facility.body": "Potencia de TI",
            "multidc_geva_project.body": "30MWIT",
        }
        for name, witness in bodies.items():
            self.assertIn(witness, (capture / name).read_text(errors="replace"))
        for capture_id in ("echelon_dub20_facility", "echelon_dub40_facility"):
            writeout = json.loads(
                (capture / f"{capture_id}.writeout").read_text()
            )
            self.assertEqual(writeout["http_code"], 404)

        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            (
                inventory["successful_http_200_body_captures"],
                inventory["http_error_body_captures"],
                inventory["http_error_capture_claims"],
            ),
            (10, 2, 0),
        )
        self.assertEqual(
            {row["path"] for row in inventory["complete_private_file_inventory"]},
            set(tranche.CAPTURE_FILE_PINS),
        )
        artifact_names = {item.name for item in ARTIFACT.iterdir()}
        self.assertFalse(any(name.endswith(".body") for name in artifact_names))
        self.assertFalse(any(name.endswith(".headers") for name in artifact_names))

    def test_frozen_v84_prior_review_and_collision_witnesses_remain_intact(
        self,
    ) -> None:
        with self._offline():
            tranche._validate_frozen_witnesses()
            tranche._validate_source_collisions()
        witness = tranche._v84_duplicate_witness()
        self.assertEqual(witness["v84_selected_input_count"], 447)
        self.assertEqual(witness["exact_collisions_with_v84_selected_documents"], 0)

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            snapshot["totals"],
            {
                "candidate_assessments": 5,
                "capacity_estimates": 2,
                "coordinates_present": 0,
                "distinct_campuses": 5,
                "entity_snapshots": 10,
                "geometry_present": 0,
                "lifecycle_observations": 5,
                "operating_model_observations": 0,
                "placement_observations": 0,
                "projects": 5,
                "review_only_candidates": 0,
                "seed_eligible_source_records": 5,
                "source_records": 5,
                "unique_evidence_records": 9,
                "workload_observations": 0,
            },
        )
        self.assertEqual(
            snapshot["prior_review_only_resolution"]["prior_decision"],
            "review_only_uncaptured_official_linkedin",
        )
        self.assertFalse(
            snapshot["prior_review_only_resolution"]["prior_artifact_mutated"]
        )
        integration = snapshot["integration"]
        self.assertFalse(integration["open_seed_successor_created"])
        self.assertFalse(integration["open_seed_v84_mutated"])
        self.assertTrue(
            all(
                value == "none"
                for key, value in integration.items()
                if key.endswith("integration")
            )
        )


if __name__ == "__main__":
    unittest.main()
