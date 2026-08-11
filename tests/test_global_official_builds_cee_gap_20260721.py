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

from datacenter_atlas import global_official_builds_cee_gap_20260721 as tranche
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts" / tranche.ARTIFACT_ID
TRASH = Path("/Users/kian/.Trash/dc-official-cee-20260721.z5x8RN")

RECORDED_AT = "2026-07-21T17:18:25Z"
IMPLEMENTATION_PIN = (
    85_083,
    "3ec3dc098fcee4675946a2a006298265f05a09634046c0f49bf827a11dda80c6",
)
ARTIFACT_TREE_SHA256 = (
    "e23ecade126ad455d9b2819b614c7b45574f099c419f73cf3457adbb7091e91e"
)
LOGICAL_TREE_SHA256 = (
    "cdbb23055c9380ae7d1e64048529e4476e4f222afe6d599c09c1f9dcb78fa14d"
)
SOURCE_PINS = {
    "curated-official-2026-07-21-microsoft-ath04-spata-current-build.json": (
        8_386,
        "4368d6b67766cfdcddeeaf30cf7e70f4e82d1094ea8616952b0fa7a85bdc9c97",
    ),
    "curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json": (
        6_455,
        "1ec21ecde6660e3ff62b469693fe277998b85fc892127ca15d9612981381a65f",
    ),
    "curated-official-2026-07-21-ten-brinke-spata-current-build.json": (
        7_835,
        "feb7d0fb6fc9ef7da9fe06ab16177a75247b3220ffeba6572cf8dccebd61bed4",
    ),
    "curated-official-2026-07-21-ast-janciems-shell-fit-out.json": (
        4_296,
        "02b9f7c85d1a22ff4b290c01954adce2909295fd33517993496f4221fc61f206",
    ),
    (
        "curated-official-2026-07-21-serbia-state-dc-kragujevac-"
        "modules-3-4-operational.json"
    ): (
        6_280,
        "36cccf1eaa107e1581879722438ca1f22e5c371ae77cbaeb8d0a9bc76b5d38f2",
    ),
}
ARTIFACT_PINS = {
    "README.md": (
        2_795,
        "a897f24778f26266fe529a15f39660bd7e91aa57d983b149995734f69ab3402e",
    ),
    "candidate-assessment.json": (
        10_003,
        "0a5890b11b5b9b59bd353a1cbe9390941f36079cafa65f72351e700421e0dafd",
    ),
    "manifest.json": (
        1_744,
        "13ffdc16826e4fc1caf75b3b9c97fe8f2176193247512992254bd8ae114bc4f9",
    ),
    "manifest.sha256": (
        80,
        "6bd8031086eb12dddc7efb88542846d8a1995c4599fdecf23e53cd82996bbff1",
    ),
    "retrieval-inventory.json": (
        22_177,
        "da38f4f9a6930348b334101de3bd2c7610a47bea1a7227518ec4e7bff14fdbc1",
    ),
    "rights-and-disposition.json": (
        1_586,
        "d8bcb4d4769db10cd79a4ece47363e384305e7f654b243cfc117188d6015d1ea",
    ),
    "source-snapshot.json": (
        7_404,
        "39406b88e03e9e30d9bd91f9aeb979e16a6945cd561da63f45ec3a3021d37c70",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsCeeGapTests(unittest.TestCase):
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

    def test_frozen_artifact_exact_hashes_modes_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["tree_sha256"], LOGICAL_TREE_SHA256)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(
            (Path(tranche.__file__).stat().st_size, sha256(Path(tranche.__file__))),
            IMPLEMENTATION_PIN,
        )
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
                "evidence": 10,
                "lifecycle_observations": 5,
                "operating_model_observations": 2,
                "workload_observations": 2,
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
                    "FROM capacity_estimates AS c JOIN entities AS e "
                    "ON e.id=c.entity_id"
                ).fetchone()
            )
            self.assertEqual(
                capacity,
                (
                    "curated:serbia-state-data-center-kragujevac:"
                    "modules-3-4-commissioned-2026",
                    "generation_nameplate_mw",
                    "operational",
                    "MW",
                    0.3,
                ),
            )

    def test_semantic_boundaries_and_full_review_matrix(self) -> None:
        documents = tranche.expected_source_documents()
        microsoft, tet, ten_brinke, ast, serbia = [
            documents[name] for name in tranche.SOURCE_FILENAMES
        ]
        self.assertEqual(
            [row["value"] for document in documents.values() for row in document["lifecycle"]],
            ["under_construction", "under_construction", "under_construction", "shell", "operational"],
        )
        self.assertEqual(microsoft["lifecycle"][0]["as_of_date"], "2026-03-31")
        self.assertEqual(microsoft["operating_models"][0]["value"], "hyperscale_self_build")
        self.assertEqual(microsoft["workloads"][0]["value"], "general_cloud")
        self.assertIn("design/purpose", microsoft["evidence"][1]["metadata"]["workload_scope"])

        self.assertEqual(tet["lifecycle"][0]["as_of_date"], "2026-03-12")
        self.assertEqual(
            tet["lifecycle"][0]["evidence_key"],
            "tet-dc7-citrus-project-page-captured-2026-07-21",
        )
        self.assertIn(
            "does not anchor the DC7 lifecycle observation",
            tet["evidence"][1]["metadata"]["identity_scope"],
        )
        self.assertEqual(tet["capacities"], [])
        self.assertEqual(tet["workloads"], [])

        self.assertEqual(ten_brinke["lifecycle"][0]["as_of_date"], "2026-07-21")
        self.assertEqual(ten_brinke["capacities"], [])
        self.assertTrue(ten_brinke["evidence"][2]["metadata"]["resolution_candidate_only"])
        self.assertFalse(ten_brinke["evidence"][2]["metadata"]["identity_link_asserted"])

        self.assertEqual(ast["lifecycle"][0]["value"], "shell")
        self.assertEqual(ast["campus"]["address"], "Dārzciema iela 86, Rīga")
        ast_metadata = ast["evidence"][0]["metadata"]
        self.assertEqual(ast_metadata["content_hash_verification"], "unverified_assertion")
        self.assertFalse(
            ast_metadata["independent_live_page_open_verification"][
                "source_byte_hash_claimed"
            ]
        )

        self.assertEqual(serbia["lifecycle"][0]["value"], "operational")
        self.assertEqual(serbia["operating_models"][0]["value"], "sovereign_research")
        self.assertEqual(
            serbia["workloads"][0]["value"], "ai_specialized_unspecified"
        )
        self.assertEqual(serbia["capacities"][0]["metric"], "generation_nameplate_mw")
        self.assertEqual(serbia["capacities"][0]["base"], 0.3)
        self.assertEqual(serbia["capacities"][0]["stage"], "operational")
        self.assertIn("CC BY-NC-ND 3.0 RS", serbia["evidence"][0]["license"])
        reconciliation = serbia["evidence"][0]["metadata"][
            "prior_discovery_reconciliation"
        ]
        self.assertFalse(reconciliation["block_2_identity_asserted"])

        self.assertEqual(sum(len(row["capacities"]) for row in documents.values()), 1)
        for document in documents.values():
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])
        joined = json.dumps(documents, ensure_ascii=False)
        for text in ("19.2", "12.5", "25 MW", '"reported_module_energy_capacity_mw": 8', '"reported_total_energy_capacity_mw": 14'):
            self.assertIn(text, joined)
        stable_keys = {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
        self.assertNotIn(
            "curated:data-in-scale-spata-campus:phase-1-current-build", stable_keys
        )

        assessment = json.loads(
            (ARTIFACT / "candidate-assessment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(assessment["candidate_count"], 24)
        self.assertEqual(assessment["seed_eligible_count"], 5)
        self.assertEqual(assessment["review_only_count"], 19)
        self.assertFalse(assessment["regional_completeness_claimed"])
        review_ids = {
            row["candidate_id"]
            for row in assessment["candidates"]
            if not row["seed_eligible"]
        }
        self.assertEqual(
            review_ids,
            {
                "data4-jawczyce",
                "atman-waw3",
                "wbs-lublewo-choczewo",
                "vantage-poland-current-build-screen",
                "clusterpower-romania",
                "hungary-unnamed-relative-expansion",
                "slovakia-bounded-screen",
                "pantheon-croatia",
                "radomir-bulgaria-nis-serbia",
                "ppc-kozani",
                "cyprus-regulatory-screen",
                "ixcellerate-mos7",
                "ixcellerate-mos11",
                "sunly-risti",
                "cra-prague",
                "pozitrons",
                "telia-vilnius",
                "data4-ath1",
                "arnes-maribor",
            },
        )
        serbia_row = next(
            row
            for row in assessment["candidates"]
            if row["candidate_id"].endswith("modules-3-4-commissioned-2026")
        )
        self.assertFalse(
            serbia_row["prior_discovery_reconciliation"]["same_project_asserted"]
        )

    def test_rights_capture_disposition_v80_absence_and_no_residue(self) -> None:
        rights = json.loads(
            (ARTIFACT / "rights-and-disposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual(rights["cc_by_nc_nd_3_0_serbia_source_count"], 1)
        self.assertEqual(
            rights["serbia_license"]["displayed_terms"],
            "Ауторство-Некомерцијално-Без прерада 3.0 Србија",
        )
        self.assertFalse(rights["serbia_license"]["raw_redistributed"])
        self.assertFalse(rights["raw_capture_redistributed"])
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["capture_file_count"], 83)
        self.assertEqual(inventory["successful_http_200_body_captures"], 7)
        self.assertEqual(inventory["indexed_official_page_assertions"], 3)
        self.assertEqual(inventory["indexed_assertions_with_source_byte_hash"], 0)
        self.assertTrue(
            inventory["capture_protocol"].endswith("45-second wall-clock timeouts.")
        )

        witness = tranche._v80_duplicate_witness()
        self.assertEqual(witness["v80_name_or_alias_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v80_source_url_exact_normalized_collisions"], 0)
        self.assertEqual(witness["v80_stable_key_collisions"], 0)
        self.assertEqual(witness["v80_evidence_key_collisions"], 0)
        tranche._validate_v80_nonmutation()
        definition = json.loads(tranche.V80_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )
        self.assertEqual(tree_digest(tranche.V80_RELEASE), tranche.V80_TREE_SHA256)

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
            list((ROOT / "sources").glob(".official-builds-cee-gap.*")), []
        )
        self.assertEqual(
            list(
                (ROOT / "source_artifacts").glob(
                    ".global-official-builds-cee-gap-*"
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
                original_promote = tranche._promote_noreplace

                def inject_collision(stage: Path, final: Path) -> None:
                    if final == collision and not collision.exists():
                        collision.write_bytes(b"late unrelated occupant\n")
                    original_promote(stage, final)

                try:
                    with (
                        patch.object(tranche, "_wait_until", return_value=None),
                        patch.object(
                            tranche,
                            "_promote_noreplace",
                            side_effect=inject_collision,
                        ),
                        self.assertRaises(tranche.OfficialCeeGapError),
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
        with self.assertRaises(tranche.OfficialCeeGapError):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )
        with self.assertRaises(tranche.OfficialCeeGapError):
            tranche.build(
                recorded_at=(datetime.now(UTC) + timedelta(seconds=60))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

if __name__ == "__main__":
    unittest.main()
