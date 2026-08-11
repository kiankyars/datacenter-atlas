from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas import global_official_builds_next_tranche_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-next-tranche-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-global-official-next-20260721.umOnmx")

RECORDED_AT = "2026-07-21T15:51:28Z"
ARTIFACT_TREE_SHA256 = (
    "2aaa975a538d088c81e1f3fe313042b2b58b0a3dfc815dec526c72a90cd3cacc"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-omnia-pecem-current-build.json": (
        11_627,
        "9bb41b3ff43b93ff5f2e09b89007ebc38170b0261192ad92cf2317dd50f892c9",
    ),
    "curated-official-2026-07-21-nxdata3-bucharest-source-scoped.json": (
        5_945,
        "5f99c454a53c26cb9c0f01cade1e90baabe2c7b86ddf1dcf7002360fad33b1c4",
    ),
    "curated-official-2026-07-21-cirion-rio2-current-build.json": (
        8_547,
        "11e617e2ae7fce8d48b3fb6b31104ef4b3ec0d970bbdf4eb1453bbf1db98102e",
    ),
    "curated-official-2026-07-21-cote-divoire-national-dc-vitib-current-build.json": (
        6_781,
        "8e685cbfaa9ffd3961bd02c4e9f73ff3a8f85ced6dbfa3716d551f5e3ebfc150",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_341,
        "df0661e91c9bc2d3651ae4609ef11b1088cee4e3f87c5cb821a322fdb1069d15",
    ),
    "candidate-assessment.json": (
        4_816,
        "b34960337b9a0f4822d94bbec431dfed26398324c30c925978f52da8f8fef315",
    ),
    "manifest.json": (
        1_791,
        "5cdf7bba0090ee2a67af2699257a6557ee1be16dcafb9d8560993127b714cce7",
    ),
    "manifest.sha256": (
        80,
        "64cdb685227768240261cea65b9cd6ae49dc9f29b1282860cfa3bf8a745c636f",
    ),
    "retrieval-inventory.json": (
        11_169,
        "78ddf575d94006133a5d9c08857d4459aeb09752054691a163c507c636a5def2",
    ),
    "rights-and-disposition.json": (
        1_319,
        "71ffb506429961d130d4410bb09661e10e307c3a8bca3e06d5bea2573272454e",
    ),
    "source-snapshot.json": (
        5_483,
        "f5cf7f31c89689051d39e9f4a244a3d76212e4ee89b33ef58835b5c1b8c29133",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsNextTrancheTests(unittest.TestCase):
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

    def test_frozen_artifact_exact_closure_hashes_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(set(ARTIFACT_PINS), {path.name for path in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            path = ARTIFACT / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

        target = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime), target
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target)
        for path in ARTIFACT.iterdir():
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
        for name in SOURCE_PINS:
            metadata = (ROOT / "sources" / name).stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
            self.assertGreaterEqual(metadata.st_ctime, target)

    def test_sources_are_exact_canonical_schema_v11_and_import_offline(self) -> None:
        expected_documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            raw = path.read_bytes()
            self.assertEqual(raw, tranche._canonical(expected_documents[name]))

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
                "entities": 8,
                "entity_snapshots": 8,
                "evidence": 10,
                "lifecycle_observations": 3,
                "operating_model_observations": 2,
                "workload_observations": 0,
                "capacity_estimates": 3,
            }
            actual_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)
            capacities = [
                tuple(row)
                for row in connection.execute(
                    "SELECT metric, stage, unit, base FROM capacity_estimates "
                    "ORDER BY metric, stage"
                )
            ]
            self.assertEqual(
                capacities,
                [
                    ("critical_it_mw", "planned", "MW", 3.0),
                    ("gross_facility_mw", "planned", "MW", 5.0),
                    ("pue", "design", "ratio", 1.3),
                ],
            )
            lifecycle = [
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, l.status, l.as_of_date "
                    "FROM lifecycle_observations AS l "
                    "JOIN entities AS e ON e.id = l.entity_id "
                    "ORDER BY e.stable_key"
                )
            ]
            self.assertEqual(
                lifecycle,
                [
                    (
                        "curated:cirion-rio-campus-rio-de-janeiro:"
                        "rio2-current-build",
                        "under_construction",
                        "2026-03-25",
                    ),
                    (
                        "curated:cote-divoire-national-data-center-vitib:"
                        "grand-bassam-current-build",
                        "under_construction",
                        "2025-12-09",
                    ),
                    (
                        "curated:omnia-pecem-data-center-campus:"
                        "initial-tiktok-bytedance-build",
                        "under_construction",
                        "2026-05-07",
                    ),
                ],
            )

    def test_claim_boundaries_and_candidate_dispositions(self) -> None:
        documents = tranche.expected_source_documents()
        by_project_key = {
            document["project"]["stable_key"]: document
            for document in documents.values()
        }
        omnia = by_project_key[
            "curated:omnia-pecem-data-center-campus:initial-tiktok-bytedance-build"
        ]
        nxdata = by_project_key[
            "curated:nxdata3-bucharest-ring-road-campus:nxdata3-buh3"
        ]
        cirion = by_project_key[
            "curated:cirion-rio-campus-rio-de-janeiro:rio2-current-build"
        ]
        cote = by_project_key[
            "curated:cote-divoire-national-data-center-vitib:grand-bassam-current-build"
        ]

        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in omnia["lifecycle"]],
            [("under_construction", "2026-05-07")],
        )
        self.assertEqual(omnia["capacities"], [])
        omnia_text = json.dumps(omnia, ensure_ascii=False, sort_keys=True)
        self.assertIn('"reported_data_center_capacity_mw_untyped": 200', omnia_text)
        self.assertIn('"reported_renewable_supply_mw_average": 300', omnia_text)
        self.assertIn("1.2 GW", omnia_text)

        self.assertEqual(nxdata["lifecycle"], [])
        self.assertEqual(
            [(row["metric"], row["stage"], row["base"]) for row in nxdata["capacities"]],
            [
                ("gross_facility_mw", "planned", 5),
                ("critical_it_mw", "planned", 3),
                ("pue", "design", 1.3),
            ],
        )
        self.assertNotIn(
            4,
            [row["base"] for row in nxdata["capacities"]],
        )

        self.assertEqual(cirion["capacities"], [])
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in cirion["lifecycle"]],
            [("under_construction", "2026-03-25")],
        )
        self.assertEqual(cote["capacities"], [])
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in cote["lifecycle"]],
            [("under_construction", "2025-12-09")],
        )

        for document in documents.values():
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])
            self.assertEqual(document["workloads"], [])

        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["seed_eligible_count"],
                assessment["identity_capacity_only_count"],
                assessment["review_only_count"],
                assessment["historical_operational_count"],
            ),
            (7, 3, 1, 2, 1),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertEqual(
            rows["odata-sp04-phase-2"]["decision"],
            "review_only_manual_publisher_capture_required",
        )
        self.assertFalse(rows["odata-sp04-phase-2"]["source_record_created"])
        self.assertFalse(
            rows["odata-sp04-phase-2"]["manual_capture_follow_up"][
                "automated_linkedin_capture_performed"
            ]
        )
        self.assertEqual(
            rows["nxdata3-buh3"]["decision"],
            "identity_capacity_only_no_governed_physical_update",
        )
        self.assertFalse(rows["nxdata3-buh3"]["seed_eligible"])
        self.assertEqual(
            rows["syntys-qdata-qatar-two-facility-aggregate"]["decision"],
            "review_only_aggregate_unallocated",
        )
        self.assertEqual(
            rows["wingu-tanzania-phase-2"]["decision"],
            "historical_operational_not_current_construction",
        )

    def test_capture_disposition_v73_nonmutation_and_no_staging_residue(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertFalse(tranche.CAPTURE_ORIGIN.is_symlink())
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        tranche._validate_capture_directory(capture)
        self.assertEqual(len(list(capture.iterdir())), 43)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(list(ROOT.glob("sources/.official-builds-next.*")), [])
        self.assertEqual(
            list(
                ROOT.glob(
                    "source_artifacts/.global-official-builds-next-tranche-"
                    "2026-07-21-v1.*"
                )
            ),
            [],
        )
        tranche._validate_v73_nonmutation()
        definition = json.loads(tranche.V73_DEFINITION.read_text())
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        snapshot = json.loads((ARTIFACT / "source-snapshot.json").read_text())
        self.assertFalse(snapshot["integration"]["open_seed_successor_created"])
        self.assertEqual(snapshot["integration"]["release_integration"], "none")
        self.assertEqual(
            snapshot["integration"]["downstream_product_integration"], "none"
        )

    def test_no_replace_collision_and_identity_safe_multi_output_rollback(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.write_bytes(b"owned")
            final.write_bytes(b"late")
            with self.assertRaisesRegex(tranche.OfficialTrancheError, "collision"):
                tranche._promote_noreplace(stage, final)
            self.assertEqual(stage.read_bytes(), b"owned")
            self.assertEqual(final.read_bytes(), b"late")

            stage_directory = root / "private"
            final_directory = root / "public"
            stage_directory.mkdir()
            final_directory.mkdir()
            promoted = []
            for name in ("one", "two"):
                source = stage_directory / name
                destination = final_directory / name
                source.write_text(name, encoding="utf-8")
                identity = tranche._identity(source, directory=False)
                tranche._promote_noreplace(source, destination)
                promoted.append((source, destination, identity, False))
            tranche._rollback_promotions(promoted)
            for name in ("one", "two"):
                self.assertTrue((stage_directory / name).is_file())
                self.assertFalse((final_directory / name).exists())


if __name__ == "__main__":
    unittest.main()
