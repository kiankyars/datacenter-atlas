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
from datacenter_atlas import global_official_builds_africa_gap_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts/global-official-builds-africa-gap-2026-07-21-v1"
TRASH = Path("/Users/kian/.Trash/dc-official-africa-20260721.vjYILG")

RECORDED_AT = "2026-07-21T16:55:54Z"
ARTIFACT_TREE_SHA256 = (
    "2c64c04f31f2001380a7f673a201447fbf522e2ee80ba939adccf3eedd3da152"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-icolo-nbo2-current-build.json": (
        10_196,
        "b7b003f7a4065572e9c3778b080b438955ea62fd066e346dc0608a2cdc54d221",
    ),
    "curated-official-2026-07-21-telecom-egypt-rdh2-commissioning.json": (
        9_305,
        "910f4a3240f17c33454a09746dc3d1761f33c4ce5c7b80ce423db1d8b6113d88",
    ),
    "curated-official-2026-07-21-teraco-jb7-review-only.json": (
        5_768,
        "e25a53734131c79d613af6e66dfa1a2c155033029f784ec1c4f4daf71b31a0b7",
    ),
    "curated-official-2026-07-21-adc-accra-review-only.json": (
        6_336,
        "fec49f1e1369d8bfbe67547c94214eef52bb2c75553305a4bef102fa912a024a",
    ),
    "curated-official-2026-07-21-ixafrica-nbox-phase2-review-only.json": (
        6_095,
        "96bc798869509bfc0a2f06a4b41068dd91ccd5b63c55960fcea4108b078b75dc",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_264,
        "97b6d608c835fb7280e9610ee1e84ee1ed366aee95ba2cff5b7aa3506fb38c5e",
    ),
    "candidate-assessment.json": (
        4_884,
        "2303075ead053484beca6033497d7614a6e94e2de19e67e16a4b67e4c25d10b2",
    ),
    "manifest.json": (
        1_817,
        "c859d9a429729710d92f43fadf2570551a9959485c5c3ace005b612376b1478a",
    ),
    "manifest.sha256": (
        80,
        "ad40d6b5aba5a4e9503db1b55b0c1debc8b51e1f67e9e123ed966fd3690d1933",
    ),
    "retrieval-inventory.json": (
        27_537,
        "6ae09ea7cd317012f05031fcd5d9b8089a77b8888da9a285c67529807ca0fc3e",
    ),
    "rights-and-disposition.json": (
        1_313,
        "967f1824b797456e0d96a1b0bd96522a2f03f29648d2e273bed7e39bf62878fc",
    ),
    "source-snapshot.json": (
        7_078,
        "5f23943c275aead25a26b225e27e437732499f82c80a014e4e718bf3021eb5a7",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsAfricaGapTests(unittest.TestCase):
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

    def test_frozen_artifact_exact_closure_hashes_and_temporal_publication(
        self,
    ) -> None:
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
        self.assertEqual(
            manifest["tree_sha256"],
            "b7e01474654331c4e178ada40e02c7c0ce28f578b5348b0ea5e5d790f229ecd4",
        )

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
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                path.read_bytes(), tranche._canonical(expected_documents[name])
            )

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
                "evidence": 12,
                "lifecycle_observations": 2,
                "operating_model_observations": 1,
                "workload_observations": 4,
                "capacity_estimates": 2,
            }
            actual_counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in expected_counts
            }
            self.assertEqual(actual_counts, expected_counts)

            capacities = connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                "FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id "
                "ORDER BY e.stable_key"
            ).fetchall()
            self.assertEqual(
                [tuple(row) for row in capacities],
                [
                    (
                        "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
                        "critical_it_mw",
                        "design",
                        "MW",
                        6.5,
                    ),
                    (
                        "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
                        "critical_it_mw",
                        "design",
                        "MW",
                        4.6,
                    ),
                ],
            )

    def test_semantic_boundaries_and_candidate_dispositions(self) -> None:
        documents = tranche.expected_source_documents()
        nbo2, rdh2, jb7, accra, nbox2 = [
            documents[name] for name in tranche.SOURCE_FILENAMES
        ]

        self.assertEqual(nbo2["lifecycle"][0]["value"], "under_construction")
        self.assertEqual(rdh2["lifecycle"][0]["value"], "commissioning")
        self.assertEqual(nbo2["capacities"][0]["base"], 6.5)
        self.assertEqual(rdh2["capacities"][0]["base"], 4.6)
        self.assertEqual(nbo2["operating_models"][0]["value"], "colocation")
        self.assertEqual(
            {row["value"] for row in nbo2["workloads"]},
            {"enterprise_it", "general_cloud"},
        )
        self.assertEqual(
            {row["value"] for row in rdh2["workloads"]},
            {"enterprise_it", "general_cloud"},
        )
        peering = nbo2["evidence"][2]["metadata"]
        self.assertFalse(peering["direct_release_permitted"])
        self.assertEqual(peering["record_values_released"], 0)
        self.assertEqual(peering["address_values_released"], 0)
        self.assertEqual(peering["coordinate_values_released"], 0)
        self.assertEqual(peering["placement_rows_created"], 0)

        for document in (jb7, accra, nbox2):
            self.assertEqual(document["lifecycle"], [])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
        self.assertEqual(
            {row["source_url"] for row in jb7["evidence"]},
            {
                "https://www.teraco.co.za/news/teraco-announces-jb7-and-a-new-r8-billion-syndicated-loan/",
                "https://www.sec.gov/Archives/edgar/data/1297996/000119312526291397/d100245d424b7.htm",
            },
        )
        self.assertIn("4.9", json.dumps(rdh2, ensure_ascii=False))
        self.assertIn("18", json.dumps(nbox2, ensure_ascii=False))
        self.assertIn("Asaase Radio", json.dumps(accra, ensure_ascii=False))
        for document in documents.values():
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])

        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 5)
        self.assertEqual(assessment["seed_eligible_count"], 2)
        self.assertEqual(assessment["review_only_count"], 3)
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertTrue(rows["icolo-nbo2-karen-nairobi"]["seed_eligible"])
        self.assertTrue(rows["telecom-egypt-rdh2-smart-village"]["seed_eligible"])
        self.assertFalse(rows["teraco-jb7-isando"]["seed_eligible"])
        self.assertFalse(rows["africa-data-centres-accra-trade-fair"]["seed_eligible"])
        self.assertFalse(rows["ixafrica-nbox2-phase-2"]["seed_eligible"])

    def test_private_capture_v79_nonmutation_and_no_residue(self) -> None:
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

        tranche._validate_v79_nonmutation()
        definition = json.loads(tranche.V79_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list((ROOT / "sources").glob(".official-builds-africa-gap.*")), []
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(".global-official-builds-africa-gap-*")
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
                        patch.object(
                            tranche, "_wait_until", side_effect=inject_collision
                        ),
                        self.assertRaises(tranche.OfficialAfricaGapError),
                    ):
                        tranche._publish(prepared)
                    self.assertEqual(
                        collision.read_bytes(), b"late unrelated occupant\n"
                    )
                    for name in tranche.SOURCE_FILENAMES:
                        if name != tranche.SOURCE_FILENAMES[1]:
                            self.assertFalse((sources / name).exists())
                    self.assertFalse(artifact.exists())
                    self.assertEqual(
                        {path.name for path in prepared.source_stage.iterdir()},
                        set(tranche.SOURCE_FILENAMES),
                    )
                finally:
                    collision.unlink(missing_ok=True)
                    tranche._cleanup_prepared(prepared)

    def test_future_wall_clock_and_republication_fail_closed(self) -> None:
        with self.assertRaises(tranche.OfficialAfricaGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialAfricaGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )


if __name__ == "__main__":
    unittest.main()
