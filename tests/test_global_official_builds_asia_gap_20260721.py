from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
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
from datacenter_atlas import global_official_builds_asia_gap_20260721 as gap
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts/global-official-builds-asia-gap-2026-07-21-v1"
TRASH = Path("/Users/kian/.Trash/dc-global-official-asia-20260721.mSVmaD")

RECORDED_AT = "2026-07-21T16:19:10Z"
ARTIFACT_TREE_SHA256 = (
    "cf88eab81111add6f6ef72a09dc9925452cf8ae744e93cfcdfda9bf2310d3c63"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-bcc-jashore-dr-data-center-current-build.json": (
        7_600,
        "534bf10ddf8139391d7b511a2b739a88cf1e6ca46d3ce4fb5a2e0e4d0540c100",
    ),
    "curated-official-2026-07-21-adaniconnex-navi-mumbai-current-development.json": (
        9_423,
        "8b1dbf8482117b8f6ce042ec1d7e3b1d67b1773f606281e1e9767e6e2b768bf0",
    ),
    "curated-official-2026-07-21-adaniconnex-pune-pnq04-current-build.json": (
        9_737,
        "af517f434c7f259f721b1458282524e8d1b1817fa9f5167b63da40a2dcd3fbc7",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_449,
        "8a8ab717b2ea88b944431a0cc21022abf69c7f8e42ace8819e26792de2be35a9",
    ),
    "candidate-assessment.json": (
        7_331,
        "d2f2b9921e9d263c2f158494ae19943a31f38cb63842bdbfdb8486b2dc523553",
    ),
    "manifest.json": (
        1_663,
        "ad12e66986122bd4d0076be6d94e116a7c38d2d4d78ef5300ea357d4851ac37b",
    ),
    "manifest.sha256": (
        80,
        "2144170e38517a85cc6546bbc5e6e9075e222824a95b0fbefa24c71bda9b102d",
    ),
    "retrieval-inventory.json": (
        11_849,
        "a6a62941e867c091bc1773ccdec6fb2f20d1cb752bfd5b112e5ed17b74a8c19e",
    ),
    "rights-and-disposition.json": (
        1_245,
        "28ed9fc3d6b363aac3499281cbe7bb4207dbf919ad71daef893ec74cd78dcee8",
    ),
    "source-snapshot.json": (
        4_609,
        "aecff855f6903b9121625ae79f68ca46d0d6b0dfbd6f5b1f8b4e235bd19f478b",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsAsiaGapTests(unittest.TestCase):
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
            manifest = gap.validate_artifact(ARTIFACT)
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

    def test_sources_are_exact_schema_v11_and_double_import_offline(self) -> None:
        expected_documents = gap.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(path.read_bytes(), gap._canonical(expected_documents[name]))

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
                "entities": 6,
                "entity_snapshots": 6,
                "evidence": 8,
                "lifecycle_observations": 3,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 2,
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
                    "SELECT e.stable_key, c.metric, c.stage, c.base "
                    "FROM capacity_estimates AS c "
                    "JOIN entities AS e ON e.id=c.entity_id ORDER BY e.stable_key"
                )
            ]
            self.assertEqual(
                capacities,
                [
                    (
                        "curated:adaniconnex-navi-mumbai-data-center-campus",
                        "critical_it_mw",
                        "planned",
                        1000.0,
                    ),
                    (
                        "curated:adaniconnex-pune-data-center-campus",
                        "critical_it_mw",
                        "planned",
                        250.0,
                    ),
                ],
            )
            lifecycle = [
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, l.status, l.as_of_date "
                    "FROM lifecycle_observations AS l "
                    "JOIN entities AS e ON e.id=l.entity_id ORDER BY e.stable_key"
                )
            ]
            self.assertEqual(
                lifecycle,
                [
                    (
                        "curated:adaniconnex-navi-mumbai-data-center-campus:"
                        "current-phased-development",
                        "under_construction",
                        "2026-06-01",
                    ),
                    (
                        "curated:adaniconnex-pune-data-center-campus:"
                        "pnq04-current-build",
                        "under_construction",
                        "2026-06-01",
                    ),
                    (
                        "curated:bcc-jashore-software-technology-park-dr-data-center:"
                        "rebuild-expansion-current-build",
                        "under_construction",
                        "2026-01-25",
                    ),
                ],
            )

    def test_claim_boundaries_coordinates_and_candidate_dispositions(self) -> None:
        documents = gap.expected_source_documents()
        by_project = {
            document["project"]["stable_key"]: document
            for document in documents.values()
        }
        jashore = by_project[
            "curated:bcc-jashore-software-technology-park-dr-data-center:"
            "rebuild-expansion-current-build"
        ]
        navi = by_project[
            "curated:adaniconnex-navi-mumbai-data-center-campus:"
            "current-phased-development"
        ]
        pune = by_project[
            "curated:adaniconnex-pune-data-center-campus:pnq04-current-build"
        ]

        expected_point = {
            "latitude": 23.156275210272007,
            "longitude": 89.22246834914694,
        }
        self.assertEqual(jashore["campus"]["coordinates"], expected_point)
        self.assertEqual(jashore["project"]["coordinates"], expected_point)
        self.assertEqual(jashore["capacities"], [])
        jashore_text = json.dumps(jashore, ensure_ascii=False, sort_keys=True)
        self.assertIn('"reported_phase_1_it_loading_kva_approximate": 600', jashore_text)
        self.assertIn(
            '"reported_it_cabinet_and_rack_count_lower_bound_exclusive": 200',
            jashore_text,
        )

        self.assertIsNone(navi["campus"]["coordinates"])
        self.assertIsNone(pune["campus"]["coordinates"])
        self.assertEqual(
            [(row["entity"], row["metric"], row["base"]) for row in navi["capacities"]],
            [("campus", "critical_it_mw", 1000)],
        )
        self.assertEqual(
            [(row["entity"], row["metric"], row["base"]) for row in pune["capacities"]],
            [("campus", "critical_it_mw", 250)],
        )
        self.assertIn(
            '"reported_project_capacity_mw_untyped": 30',
            json.dumps(navi, sort_keys=True),
        )
        for document in documents.values():
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])

        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["seed_eligible_count"],
                assessment["review_only_count"],
            ),
            (7, 3, 4),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        for candidate_id in (
            "adaniconnex-hyderabad-future-phases",
            "adaniconnex-noida-future-phases",
            "evolution-dc-vn-hcm-vn02",
            "aic-kbc-tan-phu-trung-ai-data-center",
        ):
            self.assertFalse(rows[candidate_id]["source_record_created"])
            self.assertFalse(rows[candidate_id]["seed_eligible"])
        incident = rows[
            "bcc-jashore-dr-data-center-rebuild-expansion"
        ]["technical_incident"]
        self.assertTrue(incident["two_direct_attempts_returned_http_404"])
        self.assertFalse(incident["used_for_claims"])
        self.assertFalse(incident["search_transformed_text_used"])

    def test_capture_disposition_v75_nonmutation_and_no_staging_residue(self) -> None:
        capture = gap.resolve_external_capture(gap.CAPTURE_ORIGIN, TRASH)
        self.assertFalse(gap.CAPTURE_ORIGIN.exists())
        self.assertFalse(gap.CAPTURE_ORIGIN.is_symlink())
        gap._validate_capture_directory(capture)
        self.assertEqual(len(list(capture.iterdir())), 35)
        self.assertFalse(gap.PUBLICATION_LOCK.exists())
        self.assertEqual(list(ROOT.glob("sources/.official-builds-asia-gap.*")), [])
        self.assertEqual(
            list(
                ROOT.glob(
                    "source_artifacts/.global-official-builds-asia-gap-"
                    "2026-07-21-v1.*"
                )
            ),
            [],
        )
        gap._validate_v75_nonmutation()
        definition = json.loads(gap.V75_DEFINITION.read_text())
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in gap.SOURCE_FILENAMES}
        )
        snapshot = json.loads((ARTIFACT / "source-snapshot.json").read_text())
        self.assertFalse(snapshot["integration"]["open_seed_successor_created"])
        self.assertEqual(snapshot["integration"]["release_integration"], "none")
        self.assertEqual(
            snapshot["integration"]["downstream_product_integration"], "none"
        )

    def test_published_replay_is_collision_safe_and_nonmutating(self) -> None:
        before = {
            path: (path.stat().st_size, sha256(path))
            for path in [
                ARTIFACT / "manifest.json",
                *(ROOT / "sources" / name for name in SOURCE_PINS),
            ]
        }
        future = (datetime.now(UTC) + timedelta(minutes=1)).isoformat().replace(
            "+00:00", "Z"
        )
        with self.assertRaisesRegex(gap.OfficialAsiaGapError, "final path occupied"):
            gap.build(recorded_at=future)
        after = {
            path: (path.stat().st_size, sha256(path))
            for path in before
        }
        self.assertEqual(after, before)

    def test_no_replace_collision_and_identity_safe_multi_output_rollback(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.write_bytes(b"owned")
            final.write_bytes(b"late")
            with self.assertRaisesRegex(gap.OfficialAsiaGapError, "collision"):
                gap._promote_noreplace(stage, final)
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
                identity = gap._identity(source, directory=False)
                gap._promote_noreplace(source, destination)
                promoted.append((source, destination, identity, False))
            gap._rollback_promotions(promoted)
            for name in ("one", "two"):
                self.assertTrue((stage_directory / name).is_file())
                self.assertFalse((final_directory / name).exists())


if __name__ == "__main__":
    unittest.main()
