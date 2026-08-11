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
from datacenter_atlas import (
    global_official_builds_middle_east_turkiye_gap_20260721 as tranche,
)
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "source_artifacts/global-official-builds-middle-east-turkiye-gap-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-official-middle-east-turkiye-20260721.0cD4aL")

RECORDED_AT = "2026-07-21T16:58:20Z"
ARTIFACT_TREE_SHA256 = (
    "ce36327c58f9447d99d0ce3d4de541197a12a42e1c0ea333510dd6e254bd62cf"
)
LOGICAL_TREE_SHA256 = (
    "eb53aef1dd0ec66d90ea0a8e33c5555e925e028b5e61c6d8d44b55bde06577dd"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-enka-eds-ist01-tuzla-current-build.json": (
        9_499,
        "9d8f0924edde254b9a4aaa2b9e84afcfccecddb3ebd8c320aa16dcc95d31a4cf",
    ),
    "curated-official-2026-07-21-t964-baghdad-phase1-current-build.json": (
        5_752,
        "8645f6ddaa271a644b0f78b0512c7b9a69bd31da2474eb8a0c9c9b0f01ad04b4",
    ),
    "curated-official-2026-07-21-ezditek-ruh01-pnu-phase1-current-build.json": (
        5_539,
        "19a81e9e3aaded792a1ad22bd0a58bde3056bbad6c29f5c4c69566dea44dc61a",
    ),
    "curated-official-2026-07-21-quantum-switch-doha-4-5mw-expansion-current-build.json": (
        5_138,
        "c2ce96921522be69e7f4903e8bec83d145e0355ad01d303fff483166f9b40507",
    ),
    "curated-official-2026-07-21-xds-desert-dragon-jeddah-current-build.json": (
        7_701,
        "b982725a447bde9ed629fb2b818d0db58be2c23f6a222f157705b2177260e283",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_287,
        "35988199d7d63e2b7163f707cc3487b3ce026030a7039486590772fe3ec2b6a0",
    ),
    "candidate-assessment.json": (
        8_949,
        "20da6a05fa6775dd968a88f56109a2c18cc2feb5e8622d866ef6464fda3d0b36",
    ),
    "manifest.json": (
        1_719,
        "11884537841f95d92042ac6438f837034ec51b3c249a1bb6929cd622d089cca2",
    ),
    "manifest.sha256": (
        80,
        "c8a2f195037e6446c2b824f44211fbfb1e13229039d31dedf25834eb7d2d9b88",
    ),
    "retrieval-inventory.json": (
        15_520,
        "c0cb9f4606d9579713e0221ec1e989c1f7d9e07d3c035b9f89c47722e7e889f8",
    ),
    "rights-and-disposition.json": (
        1_247,
        "b7933806549ce9c48d7d38bc4c03b10c16678b4fc8be05e5d3d137746ddf0be1",
    ),
    "source-snapshot.json": (
        6_578,
        "eb34aba2b0fcd558c1fa03b4752af3c9bae71db1c298ed0b2a3740b3fe49e34e",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsMiddleEastTurkiyeGapTests(unittest.TestCase):
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
        self.assertEqual(manifest["tree_sha256"], LOGICAL_TREE_SHA256)
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

    def test_sources_are_exact_schema_v11_and_import_twice_offline(self) -> None:
        expected_documents = tranche.expected_source_documents()
        self.assertEqual(tuple(SOURCE_PINS), tranche.SOURCE_FILENAMES)
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(path.read_bytes(), tranche._canonical(expected_documents[name]))

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
                "evidence": 13,
                "lifecycle_observations": 5,
                "operating_model_observations": 1,
                "workload_observations": 0,
                "capacity_estimates": 1,
            }
            actual_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)
            capacity = tuple(
                connection.execute(
                    "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                    "FROM capacity_estimates AS c "
                    "JOIN entities AS e ON e.id=c.entity_id"
                ).fetchone()
            )
            self.assertEqual(
                capacity,
                (
                    "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build",
                    "critical_it_mw",
                    "design",
                    "MW",
                    11.0,
                ),
            )

    def test_semantic_boundaries_and_full_review_matrix(self) -> None:
        documents = tranche.expected_source_documents()
        enka, t964, ezditek, quantum, xds = [
            documents[name] for name in tranche.SOURCE_FILENAMES
        ]
        self.assertEqual(enka["capacities"][0]["metric"], "critical_it_mw")
        self.assertEqual(enka["capacities"][0]["stage"], "design")
        self.assertEqual(enka["capacities"][0]["base"], 11)
        self.assertEqual(t964["operating_models"][0]["value"], "colocation")
        for document in (t964, ezditek, quantum, xds):
            self.assertEqual(document["capacities"], [])
        for document in documents.values():
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])
        joined = json.dumps(documents, ensure_ascii=False)
        for text in ("12 MW", "84 MW", "3MW", "24MW", "4.5 MW", "two 10MW"):
            self.assertIn(text, joined)

        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 22)
        self.assertEqual(assessment["seed_eligible_count"], 5)
        self.assertEqual(assessment["review_only_count"], 17)
        self.assertFalse(assessment["regional_completeness_claimed"])
        review_ids = {
            row["candidate_id"]
            for row in assessment["candidates"]
            if not row["seed_eligible"]
        }
        self.assertEqual(len(review_ids), 17)
        self.assertTrue(
            {
                "xds-riyadh-immersion-facility",
                "aws-saudi-region",
                "humain-saudi-program",
                "equinix-saudi-program",
                "uae-stargate",
                "uae-khazna-current-builds",
                "equinix-dx3-dubai",
                "moro-hub-warsan",
                "q-data-ooredoo-7-5mw-aggregate",
                "meeza-m-vault-7",
                "meeza-m-vault-8",
                "google-kuwait",
                "jordan-hashem-data-center",
                "jordan-ain-al-basha-data-center",
                "lebanon-dekwaneh-warehouse-rehabilitation",
                "turkcell-three-ankara-facilities",
                "turkcell-nevsehir",
            }.issubset(review_ids)
        )

    def test_v79_absence_capture_disposition_and_no_residue(self) -> None:
        witness = tranche._v79_duplicate_witness()
        self.assertEqual(witness["v79_name_or_alias_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v79_source_url_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v79_stable_key_collisions"], 0)
        self.assertEqual(witness["v79_evidence_key_collisions"], 0)
        tranche._validate_v79_nonmutation()
        definition = json.loads(tranche.V79_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )

        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        self.assertTrue(capture.is_dir())
        self.assertEqual(len(list(capture.iterdir())), tranche.CAPTURE_FILE_COUNT)
        self.assertEqual(
            sum(path.stat().st_size for path in capture.iterdir()),
            tranche.CAPTURE_TOTAL_BYTES,
        )
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        tranche._validate_capture_directory(capture)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list((ROOT / "sources").glob(".official-builds-middle-east-turkiye-gap.*")),
            [],
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-middle-east-turkiye-gap-*"
                )
            ),
            [],
        )

    def test_late_collision_rolls_back_owned_promotions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            artifacts = root / "source_artifacts"
            sources.mkdir()
            artifacts.mkdir()
            artifact = artifacts / tranche.ARTIFACT_ID
            with (
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
                        patch.object(tranche, "_wait_until", side_effect=inject_collision),
                        self.assertRaises(tranche.OfficialMiddleEastTurkiyeGapError),
                    ):
                        tranche._publish(prepared)
                    self.assertEqual(collision.read_bytes(), b"late unrelated occupant\n")
                    self.assertFalse((sources / tranche.SOURCE_FILENAMES[0]).exists())
                    self.assertFalse(artifact.exists())
                    self.assertEqual(
                        {path.name for path in prepared.source_stage.iterdir()},
                        set(tranche.SOURCE_FILENAMES),
                    )
                finally:
                    collision.unlink(missing_ok=True)
                    tranche._cleanup_prepared(prepared)

    def test_future_wall_clock_and_republication_fail_closed(self) -> None:
        with self.assertRaises(tranche.OfficialMiddleEastTurkiyeGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialMiddleEastTurkiyeGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )


if __name__ == "__main__":
    unittest.main()
