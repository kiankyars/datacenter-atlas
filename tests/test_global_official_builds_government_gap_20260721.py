from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import global_official_builds_government_gap_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts" / tranche.ARTIFACT_ID
TRASH = Path("/Users/kian/.Trash/dc-gov-builds-20260721.xwySIb")
RECORDED_AT = "2026-07-21T19:44:50Z"
LOGICAL_TREE_SHA256 = "c0044b3b2f328e33061a9543eb3961ea01659d956e6b39409df1a95f432a1cb7"
ARTIFACT_TREE_SHA256 = (
    "e9d1edb929c0745a7ae25a49ac0c16ee283a880df76679dae0ea4b7251f9e0ac"
)
ARTIFACT_PINS = {
    "README.md": (
        1_079,
        "7214b4365052f68e51b600bb55177ac74b6a5d918b246d1b0374eb11bb96c928",
    ),
    "candidate-assessment.json": (
        4_734,
        "b8baee8f60d2b155ed90f259be49f1942713c326181825e92db2adc786686086",
    ),
    "manifest.json": (
        1_905,
        "2f2354b05da5f92ba1af88a4d79a33064d4b2d730b6ddcae4c0eacbbf0a35039",
    ),
    "manifest.sha256": (
        80,
        "e4c8e7c3080ab2934082646a85909501138ba28320227f10721a9a64dd8655b3",
    ),
    "retrieval-inventory.json": (
        30_063,
        "7fbc0e28e874833e393661c3dcf9c2eff0460393e76e1d8c2d4c0e1961ef4cab",
    ),
    "rights-and-disposition.json": (
        912,
        "80a3c817e5b0548b1b7c65d33874c12bb70417252c9b68008ac91e9d56c3888d",
    ),
    "source-snapshot.json": (
        1_308,
        "b679b66eed0278d5d3b66b4cba0a8b4b9e54927714d6bb6c7558551c86452153",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GovernmentGapArtifactTests(unittest.TestCase):
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

    def test_frozen_hashes_temporal_publication_and_capture_disposition(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["tree_sha256"], LOGICAL_TREE_SHA256)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)

        self.assertEqual(set(ARTIFACT_PINS), {entry.name for entry in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            member = ARTIFACT / name
            self.assertFalse(member.is_symlink())
            self.assertEqual((member.stat().st_size, sha256(member)), expected)
            self.assertEqual(stat.S_IMODE(member.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

        target = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime), target
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target)
        for member in ARTIFACT.iterdir():
            metadata = member.stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)

        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertEqual(TRASH, tranche.CAPTURE_TRASH)
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        tranche._validate_capture_directory(capture)
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(capture.stat().st_mode), 0o700)

    def test_all_three_candidates_fail_closed_without_normalized_rows(self) -> None:
        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["curated_source_record_count"],
                assessment["seed_eligible_count"],
                assessment["review_only_count"],
                assessment["current_status_unknown_count"],
                assessment["capacity_row_count"],
            ),
            (3, 0, 0, 3, 3, 0),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertEqual(
            set(rows),
            {
                "changle-airport-comprehensive-bonded-zone-ai-computing-center",
                "bolivia-ministerio-publico-data-center-sucre",
                "fuzhou-phase-2-phase-3-program-candidate",
            },
        )
        self.assertEqual(
            rows[
                "changle-airport-comprehensive-bonded-zone-ai-computing-center"
            ]["decision"],
            "review_only_required_january_19_publisher_body_unavailable",
        )
        self.assertFalse(
            rows[
                "changle-airport-comprehensive-bonded-zone-ai-computing-center"
            ]["supplemental_claim_eligible"]
        )
        self.assertTrue(
            rows[
                "changle-airport-comprehensive-bonded-zone-ai-computing-center"
            ]["compute_figures_are_not_capacity_rows"]
        )
        bolivia = rows["bolivia-ministerio-publico-data-center-sucre"]
        self.assertEqual(
            bolivia["decision"],
            "review_only_required_progress_publisher_body_unavailable",
        )
        self.assertEqual(bolivia["parallel_interim_address"], "Calle Destacamento 317")
        self.assertFalse(bolivia["parallel_interim_address_normalized"])
        for row in rows.values():
            normalized = row["normalized"]
            self.assertFalse(normalized["source_record_created"])
            self.assertFalse(normalized["seed_eligible"])
            self.assertFalse(normalized["seeded"])
            self.assertEqual(normalized["current_status"], "unknown")
            self.assertFalse(normalized["confirmed_current_status"])
            for count_name in (
                "entity_rows",
                "evidence_rows",
                "lifecycle_rows",
                "operating_model_rows",
                "workload_rows",
                "capacity_rows",
            ):
                self.assertEqual(normalized[count_name], 0)
            self.assertFalse(normalized["coordinates_present"])
            self.assertFalse(normalized["geometry_present"])
        self.assertIsNone(assessment["unique_physical_site_count"])
        self.assertFalse(assessment["semi_analysis_parity_claimed"])

    def test_exact_transport_metadata_and_supplemental_mirror_boundary(self) -> None:
        inventory = json.loads((ARTIFACT / "retrieval-inventory.json").read_text())
        self.assertEqual(inventory["retrieval_attempt_count"], 20)
        self.assertEqual(inventory["successful_http_200_decoded_body_count"], 1)
        self.assertEqual(inventory["required_claim_bearing_http_200_body_count"], 0)
        self.assertEqual(inventory["identity_bound_http_200_body_count"], 1)
        self.assertEqual(inventory["claim_eligible_capture_count"], 0)
        self.assertFalse(inventory["search_snippets_used_for_claims"])
        self.assertFalse(inventory["transformed_web_text_used_for_claims"])
        self.assertFalse(inventory["publisher_media_used_for_claims"])

        rows = {row["request_id"]: row for row in inventory["requests"]}
        self.assertEqual(set(rows), set(tranche.REQUEST_IDS))
        for request_id in tranche.REQUIRED_REQUEST_IDS:
            row = rows[request_id]
            self.assertEqual(row["http_status"], 0)
            self.assertFalse(row["decoded_body_created"])
            self.assertEqual(row["decoded_body_bytes"], 0)
            self.assertIsNone(row["decoded_body_sha256"])
            self.assertFalse(row["identity_bound_http_200_body"])
            self.assertFalse(row["eligible_for_normalized_claims"])
            self.assertFalse(row["source_record_created"])

        mirror = rows["changle_swt_mirror"]
        self.assertEqual(mirror["http_status"], 200)
        self.assertEqual(mirror["effective_url"], tranche.CHANGLE_SUPPLEMENTAL_URL)
        self.assertEqual(mirror["content_type"], "text/html")
        self.assertEqual(
            (mirror["decoded_body_bytes"], mirror["decoded_body_sha256"]),
            tranche.MIRROR_BODY_PIN,
        )
        self.assertEqual(mirror["wire_download_bytes"], 12_207)
        self.assertTrue(mirror["identity_bound_http_200_body"])
        self.assertFalse(mirror["eligible_for_normalized_claims"])
        self.assertFalse(mirror["used_for_normalized_claims"])
        self.assertFalse(mirror["source_record_created"])
        self.assertEqual(
            inventory["changle_current_a_records_attempted"],
            list(tranche.CHANGLE_A_RECORDS),
        )
        self.assertEqual(
            (
                inventory["raw_capture"]["file_count"],
                inventory["raw_capture"]["total_bytes"],
                inventory["raw_capture"]["physical_tree_sha256"],
            ),
            (
                tranche.CAPTURE_FILE_COUNT,
                tranche.CAPTURE_TOTAL_BYTES,
                tranche.CAPTURE_TREE_SHA256,
            ),
        )

    def test_v84_exact_nonmutation_absence_and_zero_source_files(self) -> None:
        v84 = tranche._validate_v84_nonmutation()
        self.assertEqual(v84["recorded_at"], tranche.V84_RECORDED_AT)
        self.assertEqual(v84["selected_input_count"], tranche.V84_INPUT_COUNT)
        self.assertEqual(v84["release_tree_sha256"], tranche.V84_TREE_SHA256)
        self.assertEqual(v84["candidate_alias_collision_count"], 0)
        self.assertEqual(v84["candidate_url_collision_count"], 0)
        self.assertEqual(tranche.SOURCE_FILENAMES, ())

        snapshot = json.loads((ARTIFACT / "source-snapshot.json").read_text())
        self.assertEqual(snapshot["source_records"], [])
        self.assertEqual(snapshot["planned_source_filenames"], [])
        self.assertEqual(set(snapshot["normalized_counts"].values()), {0})
        self.assertFalse(snapshot["integration"]["open_seed_successor_created"])
        self.assertFalse(snapshot["integration"]["v84_mutated"])
        self.assertEqual(snapshot["integration"]["release_integration"], "none")
        self.assertEqual(snapshot["integration"]["downstream_product_integration"], "none")
        self.assertIsNone(snapshot["unique_physical_site_count"])
        self.assertFalse(snapshot["semi_analysis_parity_claimed"])

    def test_offline_replay_shim_and_no_stage_residue(self) -> None:
        try:
            core = importlib.import_module(
                "datacenter_atlas.datacenter_atlas."
                "global_official_builds_government_gap_20260721"
            )
            shim = importlib.import_module(
                "datacenter_atlas.global_official_builds_government_gap_20260721"
            )
        except ModuleNotFoundError:
            core = importlib.import_module(
                "datacenter_atlas.global_official_builds_government_gap_20260721"
            )
            shim = tranche
        self.assertIs(core.validate_artifact, shim.validate_artifact)
        with self._offline():
            first = tranche.validate_artifact(ARTIFACT)
            second = tranche.validate_artifact(ARTIFACT)
        self.assertEqual(first, second)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list(
                tranche.ARTIFACT_ROOT.glob(
                    f".{tranche.ARTIFACT_ID}.stage-*"
                )
            ),
            [],
        )

    def test_no_replace_collision_and_future_clock_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_root = Path(temporary)
            stage = temporary_root / "stage"
            final = temporary_root / "final"
            stage.write_bytes(b"owned-stage")
            final.write_bytes(b"late-collision")
            with self.assertRaisesRegex(Exception, "collision"):
                tranche._promote_noreplace(stage, final)
            self.assertEqual(stage.read_bytes(), b"owned-stage")
            self.assertEqual(final.read_bytes(), b"late-collision")

        with self.assertRaisesRegex(Exception, "not live"):
            tranche.validate_artifact(
                ARTIFACT,
                wall_clock=instant(RECORDED_AT) - timedelta(microseconds=1),
            )


if __name__ == "__main__":
    unittest.main()
