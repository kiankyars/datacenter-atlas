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

from datacenter_atlas import global_official_builds_oceania_gap_20260721 as tranche
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts" / tranche.ARTIFACT_ID
TRASH = Path("/Users/kian/.Trash/dc-official-oceania-20260721.xLyZD6")
RECORDED_AT = "2026-07-21T17:22:11Z"
ARTIFACT_TREE_SHA256 = "063602c77cafc7305803f41551b6224d0b7e6a5197e274ed4b285fa66fd82615"
LOGICAL_TREE_SHA256 = "6eb4e2d73270fedc07113e3f3d483b9c8fd307768e230d7ab54862308e38cdba"
SOURCE_PINS = {
    "curated-official-2026-07-21-airtrunk-syd3-current-build.json": (7_293, "050cbf1db6b1ed0ba414a352ed89607b26277802fe339e2176f15fe04ddf09ff"),
    "curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json": (5_409, "af9c9fe758609be14a814d352aead1f78a1af7a3d5ab80ad990311c1ced03e16"),
    "curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json": (5_414, "27852ea8af7bc6b3c3de64747041c93212e6f0515230ad64a89077c0e7463150"),
    "curated-official-2026-07-21-cdc-marsden-park-current-build.json": (3_529, "8ef701ac0b4346aed089996487a149dd1aea2545ce11b0b30c53faf5a1807322"),
    "curated-official-2026-07-21-cdc-laverton-current-build.json": (3_570, "27f91ee149d0932fc73894a71364924dd00aed0640513f8df6af0717769309e6"),
    "curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json": (3_717, "b28d52ff6f4ba56fcfe9d52295464f18c76030bc41d9a4c12998aa101cd75c14"),
    "curated-official-2026-07-21-cdc-maddington-current-build.json": (7_511, "6b35ab149f542912d59750092903324bf8d1dcdc62ed4aa271dad8fdcb4159c8"),
    "curated-official-2026-07-21-gta-gu3-alupang-operational-closure.json": (10_101, "92f0a23086354133f4f9387f3f169ecf23cbacd7268e2c477611eefceeeb7d2c"),
}
ARTIFACT_PINS = {
    "README.md": (2_882, "7860230a9bbb45a0e7ce36604f1c8eb6bc06c257656f142597f31da498a080ee"),
    "candidate-assessment.json": (10_999, "2299fd31b4e78de9cec90d26530c5773d0187e08d82adce0d1eb4ba2bb506c2e"),
    "manifest.json": (1_708, "4c60b65554242278784ff726c6e176cb2ed70d9a2d1d1c062a3d729d87d77c85"),
    "manifest.sha256": (80, "f50b355560fd0964033d04355eebc2f1f509dcda986539f8eb4bb219d20e2806"),
    "retrieval-inventory.json": (23_140, "19bd185e10f42226a27b0fab514f23d8f86e61ee6c3c99d1d6acaf6174c55e2f"),
    "rights-and-disposition.json": (1_192, "7bbbcc4eab7f0f87ce834e01a41c663a3e6b3136f6a6ebcf98be520eb3b63173"),
    "source-snapshot.json": (8_725, "a3528e89f90965af5a5a1081ed5cedd6a483b93769aa2d3df31dee0a27007f6b"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsOceaniaGapTests(unittest.TestCase):
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

    def test_frozen_artifact_hashes_temporal_publication_and_sources(self) -> None:
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

    def test_full_candidate_matrix_and_immutable_disposition(self) -> None:
        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 25)
        self.assertEqual(assessment["seed_eligible_count"], 8)
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
                "datagrid-makarewa-ai-factory",
                "dci-akl02-auckland",
                "nextdc-ak1-auckland",
                "tdf-papeete-expansion",
                "vanuatu-government-data-centre",
                "bounded-official-sweep-fiji",
                "bounded-official-sweep-papua-new-guinea",
                "bounded-official-sweep-samoa",
                "bounded-official-sweep-tonga",
                "bounded-official-sweep-palau",
                "bounded-official-sweep-new-caledonia",
            }.issubset(review_ids)
        )

        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertEqual(TRASH, tranche.CAPTURE_TRASH)
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        self.assertTrue(capture.is_dir())
        tranche._validate_capture_directory(capture)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list((ROOT / "sources").glob(".official-builds-oceania-gap.*")), []
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-oceania-gap-*"
                )
            ),
            [],
        )

        with self.assertRaises(tranche.OfficialOceaniaGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialOceaniaGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

    def test_exact_schema_v11_semantic_contract_and_offline_replay(self) -> None:
        documents = tranche.expected_source_documents()
        self.assertEqual(tuple(documents), tranche.SOURCE_FILENAMES)
        self.assertEqual(len(documents), 8)

        stable_keys = {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
        evidence_keys = {
            evidence["key"]
            for document in documents.values()
            for evidence in document["evidence"]
        }
        self.assertEqual(len(stable_keys), 15)
        self.assertEqual(len(evidence_keys), 17)

        ec5 = documents[tranche.SOURCE_FILENAMES[1]]
        ec6 = documents[tranche.SOURCE_FILENAMES[2]]
        self.assertEqual(ec5["campus"]["stable_key"], ec6["campus"]["stable_key"])
        self.assertNotEqual(ec5["project"]["stable_key"], ec6["project"]["stable_key"])

        statuses = [
            document["lifecycle"][0]["value"] for document in documents.values()
        ]
        self.assertEqual(statuses.count("under_construction"), 6)
        self.assertEqual(statuses.count("shell"), 1)
        self.assertEqual(statuses.count("operational"), 1)

        gta = documents[tranche.SOURCE_FILENAMES[-1]]
        self.assertEqual(gta["operating_models"][0]["value"], "colocation")
        self.assertEqual(
            (
                gta["capacities"][0]["metric"],
                gta["capacities"][0]["stage"],
                gta["capacities"][0]["base"],
            ),
            ("gross_facility_mw", "design", 4.0),
        )
        self.assertEqual(gta["lifecycle"][0]["as_of_date"], "2026-04-16")
        current_about = next(
            row for row in gta["evidence"] if "current-about" in row["key"]
        )
        self.assertIn(
            "retrieval-date corroboration",
            current_about["metadata"]["publication_version_guardrail"],
        )

        airtrunk = documents[tranche.SOURCE_FILENAMES[0]]
        self.assertEqual(airtrunk["capacities"], [])
        joined = json.dumps(documents, ensure_ascii=False)
        for label in ("320+ MW", "400+MW", "200 MW+", "4.0 MW"):
            self.assertIn(label, joined)
        for document in documents.values():
            self.assertEqual(document["workloads"], [])
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])

        recorded_at = (datetime.now(UTC) + timedelta(seconds=120)).replace(
            microsecond=0
        ).isoformat().replace("+00:00", "Z")
        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            connection, _ = initialize(root / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for name, document in documents.items():
                path = root / name
                path.write_bytes(tranche._canonical(document))
                for _ in range(2):
                    adapter.import_file(connection, path, recorded_at=recorded_at)
            validate_database(connection)
            expected = {
                "entities": 15,
                "entity_snapshots": 16,
                "evidence": 17,
                "lifecycle_observations": 8,
                "operating_model_observations": 1,
                "workload_observations": 0,
                "capacity_estimates": 1,
            }
            actual = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in expected
            }
            self.assertEqual(actual, expected)
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
                    "curated:gta-gu3-alupang-data-center:initial-build",
                    "gross_facility_mw",
                    "design",
                    "MW",
                    4.0,
                ),
            )

    def test_v81_nonmutation_absence_and_capture_closure(self) -> None:
        with self._offline():
            tranche._validate_v81_nonmutation()
            witness = tranche._v81_duplicate_witness()
        self.assertEqual(witness["v81_name_or_alias_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v81_source_url_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v81_stable_key_collisions"], 0)
        self.assertEqual(witness["v81_evidence_key_collisions"], 0)

        definition = json.loads(tranche.V81_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertEqual(len(selected), 428)
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        capture = (
            tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
        )
        tranche._validate_capture_directory(capture)

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
                        patch.object(tranche, "_wait_until", side_effect=inject_collision),
                        self.assertRaises(tranche.OfficialOceaniaGapError),
                    ):
                        tranche._publish(prepared)
                    self.assertEqual(
                        collision.read_bytes(), b"late unrelated occupant\n"
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
