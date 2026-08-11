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

from datacenter_atlas import (
    global_official_builds_canada_mexico_caribbean_gap_20260721 as tranche,
)
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts" / tranche.ARTIFACT_ID
TRASH = Path("/Users/kian/.Trash/dc-official-canada-mexico-20260721.pGmRVm")
RECORDED_AT = "2026-07-21T18:34:27Z"
ARTIFACT_TREE_SHA256 = (
    "4b6a15ba20ce8a5134952f4dcdfbaa7096600dcfbce6d5397d3b0007126fad3b"
)
LOGICAL_TREE_SHA256 = "ec5d90a123796b410da3693e48180104e590a26b956ce87c0e5e17f7ba4107a6"
SOURCE_PINS = {
    "curated-official-2026-07-21-qscale-q01-building-b-current-build.json": (
        4_988,
        "a663bfcede320da49a6df829aac09fe46721272b2f77c95125c4751752e10f5a",
    ),
    "curated-official-2026-07-21-estructure-cal3-current-build.json": (
        7_176,
        "b4d3bda3bea1800dade03346d599595f7d64efe4cfd0ed62aeaaa36041441330",
    ),
    "curated-official-2026-07-21-cologix-mtl8-operational-closure.json": (
        6_613,
        "5878d23898bb463e50b0493209fdedff3665ac547b252180271ef3d2a49228ec",
    ),
    "curated-official-2026-07-21-odata-qr04-phase-1-operational-closure.json": (
        9_822,
        "6857eb44314237864402c1ab7e4f6cf67a25adc95b6c0fd8f271edb34b6c2adc",
    ),
    "curated-official-2026-07-21-equinix-mo2-phase-1-operational-closure.json": (
        6_431,
        "d0c46a787ad2ba5f56f6a51b7423b562abcc06779a17a7b7c9c9dd338efe7825",
    ),
    "curated-official-2026-07-21-odata-qr03-first-facility-operational-closure.json": (
        5_423,
        "4f9db123f19694e428b4f096ed60d85a231d31ed6978940e734d08fcbfb1892d",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        3_265,
        "1da0f3c018d553a7f35ef5b21a7938e96f0f1ff63d288abe7ca583434a943ba0",
    ),
    "candidate-assessment.json": (
        10_378,
        "c5106014eb07c96b4efc47a8b59d899f604920c08e8a9a9732b6f50d9307f2ac",
    ),
    "manifest.json": (
        1_809,
        "0a38f1fd7f269c568a7db1f05416766ef56e5285a0000cd7b4219fb12361584a",
    ),
    "manifest.sha256": (
        80,
        "0d7759bd162a886165336b1de6feea1d35c9ae1a793f2420ea0063b78b6ddfd6",
    ),
    "retrieval-inventory.json": (
        25_627,
        "30d3a47306960f4d05cd21ecb2943a8f89cb974887f01a52960c67d6d0aea77c",
    ),
    "rights-and-disposition.json": (
        1_220,
        "d84fd13ced3f04e424cc1397e5e8ec03633fa15a907789769591b4a627a278f2",
    ),
    "source-snapshot.json": (
        7_633,
        "6dbec37c85dad6d23586b63c5973f8cdf3129cabb338eab165a00240ca010a37",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsCanadaMexicoCaribbeanGapTests(unittest.TestCase):
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

    def test_frozen_hashes_temporal_publication_and_sources(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["tree_sha256"], LOGICAL_TREE_SHA256)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)

        self.assertEqual(
            set(ARTIFACT_PINS),
            {path.name for path in ARTIFACT.iterdir()},
        )
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            path = ARTIFACT / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

        documents = tranche.expected_source_documents()
        self.assertEqual(tuple(SOURCE_PINS), tranche.SOURCE_FILENAMES)
        for name, expected in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(path.read_bytes(), tranche._canonical(documents[name]))

        target = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime),
            target,
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target)
        for path in ARTIFACT.iterdir():
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime),
                target,
            )
        for name in SOURCE_PINS:
            metadata = (ROOT / "sources" / name).stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime),
                target,
            )
            self.assertGreaterEqual(metadata.st_ctime, target)

    def test_complete_candidate_matrix_and_bounded_negatives(self) -> None:
        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 18)
        self.assertEqual(assessment["seed_eligible_count"], 6)
        self.assertEqual(assessment["review_only_count"], 12)
        self.assertFalse(assessment["regional_completeness_claimed"])
        self.assertFalse(assessment["caribbean_completeness_claimed"])

        review = {
            row["candidate_id"]: row
            for row in assessment["candidates"]
            if not row["seed_eligible"]
        }
        self.assertEqual(
            set(review),
            {
                "kio-qro2-queretaro",
                "microsoft-two-unnamed-queretaro-builds",
                "ellisdon-confidential-ontario-hyperscale-data-center",
                "kio-second-guatemala-data-center",
                "vantage-qc24-quebec",
                "cloudhq-six-queretaro-facilities",
                "layer9-falcon-queretaro",
                "ascenty-third-queretaro-facility",
                "liberty-gold-data-dominicana",
                "bluenap-ai-curacao-existing-facility",
                "puerto-rico-data-center-equipment-replacement",
                "jamaica-colocation-procurement",
            },
        )
        self.assertEqual(
            review["kio-second-guatemala-data-center"]["existing_project_stable_key"],
            tranche.KIO_GUATEMALA_STABLE_KEY,
        )
        self.assertEqual(
            review["kio-second-guatemala-data-center"]["existing_evidence_id"],
            tranche.KIO_GUATEMALA_EVIDENCE_ID,
        )
        for candidate_id in (
            "vantage-qc24-quebec",
            "cloudhq-six-queretaro-facilities",
            "layer9-falcon-queretaro",
            "ascenty-third-queretaro-facility",
            "liberty-gold-data-dominicana",
            "bluenap-ai-curacao-existing-facility",
            "puerto-rico-data-center-equipment-replacement",
            "jamaica-colocation-procurement",
        ):
            self.assertFalse(review[candidate_id]["source_url_recovered"])
            self.assertIn("bounded_search", review[candidate_id])

    def test_exact_schema_semantics_capacity_and_placement_boundaries(self) -> None:
        documents = tranche.expected_source_documents()
        self.assertEqual(tuple(documents), tranche.SOURCE_FILENAMES)
        self.assertEqual(len(documents), 6)
        stable_keys = {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
        evidence_keys = {
            row["key"]
            for document in documents.values()
            for row in document["evidence"]
        }
        self.assertEqual(len(stable_keys), 12)
        self.assertEqual(len(evidence_keys), 11)

        statuses = [
            document["lifecycle"][0]["value"] for document in documents.values()
        ]
        self.assertEqual(statuses.count("under_construction"), 2)
        self.assertEqual(statuses.count("operational"), 4)
        self.assertEqual(
            {
                row["value"]
                for document in documents.values()
                for row in document["operating_models"]
            },
            {"colocation"},
        )
        self.assertFalse(any(document["workloads"] for document in documents.values()))
        self.assertEqual(
            sum(len(document["capacities"]) for document in documents.values()),
            8,
        )
        self.assertEqual(
            tranche._expected_capacity_rows(list(documents.values())),
            {
                (
                    "curated:qscale-q01-levis-campus:building-b",
                    "critical_it_mw",
                    "design",
                    60.0,
                ),
                (
                    "curated:estructure-cal3-rocky-view-campus:initial-build",
                    "critical_it_mw",
                    "design",
                    60.0,
                ),
                (
                    "curated:estructure-cal3-rocky-view-campus:initial-build",
                    "gross_facility_mw",
                    "design",
                    90.0,
                ),
                (
                    "curated:cologix-mtl8-montreal-data-center:initial-build",
                    "gross_facility_mw",
                    "design",
                    21.0,
                ),
                (
                    "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
                    "critical_it_mw",
                    "operational",
                    12.0,
                ),
                (
                    "curated:odata-dc-qr04-san-miguel-de-allende",
                    "critical_it_mw",
                    "design",
                    24.0,
                ),
                (
                    "curated:odata-dc-qr03-queretaro-campus:first-facility",
                    "critical_it_mw",
                    "operational",
                    72.0,
                ),
                (
                    "curated:odata-dc-qr03-queretaro-campus",
                    "critical_it_mw",
                    "design",
                    300.0,
                ),
            },
        )

        coordinate_rows = {
            (
                document[entity]["stable_key"],
                document[entity]["coordinates"]["latitude"],
                document[entity]["coordinates"]["longitude"],
            )
            for document in documents.values()
            for entity in ("campus", "project")
            if document[entity]["coordinates"] is not None
        }
        self.assertEqual(
            coordinate_rows,
            {
                (
                    "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
                    20.907398,
                    -100.62028,
                ),
                (
                    "curated:equinix-mo2-monterrey-data-center:phase-1",
                    25.725216372664335,
                    -100.13271303039684,
                ),
            },
        )
        cal3 = documents[tranche.SOURCE_FILENAMES[1]]
        self.assertIsNone(cal3["campus"]["coordinates"])
        self.assertIsNone(cal3["project"]["coordinates"])
        mo2 = documents[tranche.SOURCE_FILENAMES[4]]
        self.assertEqual(mo2["capacities"], [])

    def test_offline_v11_replay_counts(self) -> None:
        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for name in tranche.SOURCE_FILENAMES:
                adapter.import_file(
                    connection,
                    ROOT / "sources" / name,
                    recorded_at=RECORDED_AT,
                )
            validate_database(connection)
            self.assertEqual(
                {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "entities",
                        "entity_snapshots",
                        "evidence",
                        "lifecycle_observations",
                        "operating_model_observations",
                        "workload_observations",
                        "capacity_estimates",
                    )
                },
                {
                    "entities": 12,
                    "entity_snapshots": 12,
                    "evidence": 11,
                    "lifecycle_observations": 6,
                    "operating_model_observations": 6,
                    "workload_observations": 0,
                    "capacity_estimates": 8,
                },
            )

    def test_exact_v83_absence_and_duplicate_witness(self) -> None:
        with self._offline():
            tranche._validate_v83_nonmutation()
            witness = tranche._v83_duplicate_witness()
        self.assertEqual(
            witness,
            {
                "planned_identity_aliases_checked": 12,
                "planned_source_urls_checked": 11,
                "planned_stable_keys_checked": 12,
                "planned_evidence_keys_checked": 11,
                "v83_name_or_alias_exact_normalized_collisions": 0,
                "v83_source_url_exact_normalized_collisions": 0,
                "v83_stable_key_collisions": 0,
                "v83_evidence_key_collisions": 0,
            },
        )
        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        duplicate = snapshot["frozen_v83_non_mutation_witness"][
            "kio_guatemala_duplicate"
        ]
        self.assertEqual(
            duplicate["project_stable_key"],
            tranche.KIO_GUATEMALA_STABLE_KEY,
        )
        self.assertEqual(
            duplicate["evidence_id"],
            tranche.KIO_GUATEMALA_EVIDENCE_ID,
        )

    def test_capture_rights_incidents_and_closed_private_inventory(self) -> None:
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertEqual(TRASH, tranche.CAPTURE_TRASH)
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        self.assertTrue(capture.is_dir())
        tranche._validate_capture_directory(capture)
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["capture_requests"], 16)
        self.assertEqual(inventory["successful_http_200_body_captures"], 15)
        self.assertEqual(inventory["accepted_identity_bound_captures"], 14)
        self.assertEqual(inventory["captures_used_for_normalized_claims"], 11)
        self.assertEqual(inventory["failed_or_partial_captures"], 2)
        self.assertFalse(inventory["raw_capture_redistributed"])
        incidents = {row["capture_id"]: row for row in inventory["technical_incidents"]}
        self.assertEqual(
            incidents["kio_qro2_news"]["result"],
            "redirect_identity_mismatch",
        )
        self.assertEqual(incidents["kio_qro2_spec"]["result"], "http_404")
        self.assertEqual(
            {row["path"] for row in inventory["complete_private_file_inventory"]},
            set(tranche.CAPTURE_FILE_PINS),
        )
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list(
                (ROOT / "sources").glob(
                    ".official-builds-canada-mexico-caribbean-gap.*"
                )
            ),
            [],
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-canada-mexico-caribbean-gap-*"
                )
            ),
            [],
        )

    def test_rejects_prepublication_clock_and_rebuild_collision(self) -> None:
        with self.assertRaises(tranche.OfficialCanadaMexicoCaribbeanGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialCanadaMexicoCaribbeanGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

    def test_private_staging_and_late_collision_rollback_are_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            artifacts = root / "source_artifacts"
            sources.mkdir()
            artifacts.mkdir()
            artifact = artifacts / tranche.ARTIFACT_ID
            with (
                self._offline(),
                patch.object(tranche, "SOURCES_ROOT", sources),
                patch.object(tranche, "ARTIFACT_ROOT", artifacts),
                patch.object(tranche, "ARTIFACT", artifact),
            ):
                target = (datetime.now(UTC) + timedelta(seconds=30)).replace(
                    microsecond=0
                )
                prepared = tranche._prepare_publication(
                    target.isoformat().replace("+00:00", "Z")
                )
                collision = sources / tranche.SOURCE_FILENAMES[1]

                def inject_collision(_: float) -> None:
                    collision.write_bytes(b"late unrelated occupant\n")

                try:
                    with (
                        patch.object(
                            tranche,
                            "_wait_until",
                            side_effect=inject_collision,
                        ),
                        self.assertRaises(
                            tranche.OfficialCanadaMexicoCaribbeanGapError
                        ),
                    ):
                        tranche._publish(prepared)
                    self.assertEqual(
                        collision.read_bytes(),
                        b"late unrelated occupant\n",
                    )
                    self.assertFalse((sources / tranche.SOURCE_FILENAMES[0]).exists())
                    self.assertFalse(artifact.exists())
                    self.assertEqual(
                        {path.name for path in prepared.source_stage.iterdir()},
                        set(tranche.SOURCE_FILENAMES),
                    )
                finally:
                    collision.unlink(missing_ok=True)
                    tranche._cleanup_prepared(prepared)


if __name__ == "__main__":
    unittest.main()
