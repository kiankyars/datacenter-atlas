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

from datacenter_atlas import global_official_builds_unresolved_four_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts" / tranche.ARTIFACT_ID
TRASH = Path("/Users/kian/.Trash/dc-unresolved-four-20260721.VMKPdG")
RECORDED_AT = "2026-07-21T19:56:09Z"
LOGICAL_TREE_SHA256 = "cea5a576bd564914264f7918fec000ce8305a8a992a03eb80554861e830b4df5"
ARTIFACT_TREE_SHA256 = (
    "2c43fd1e0184c4416290f6d51c5da5d561bb252187d8f0d032945386001c3d38"
)
ARTIFACT_PINS = {
    "README.md": (
        1_405,
        "29b8c8761f2dde8e7825e49181c28bcd2e17df8fab0692e1ffd275d0925cd9ec",
    ),
    "candidate-assessment.json": (
        8_206,
        "5c23478318928652afc74ebc4840d6c259f10846666bc30880125d4be05c532b",
    ),
    "manifest.json": (
        1_911,
        "6cfb363be86305d97a394533a8e1c157cd540f5c32b11b4a2643240f1b65ba6e",
    ),
    "manifest.sha256": (
        80,
        "e416033f4ad92cf756a07183c896099501816191c09fd7c52ec64d220a9b7d07",
    ),
    "retrieval-inventory.json": (
        31_246,
        "3a8e2383e953f764293484f0be7647566384c34b75b8a9491deb471fd09fd545",
    ),
    "rights-and-disposition.json": (
        869,
        "60fd1534e340d1e8f1f74da925fb2a5bca1ef920a897c693f7216cf4f3975e55",
    ),
    "source-snapshot.json": (
        1_341,
        "ab8e58d3653c8750789ce43d067918324601bb345901a0065092ad2a4364524c",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class UnresolvedFourArtifactTests(unittest.TestCase):
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
        metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
        self.assertGreaterEqual(metadata.st_ctime, target)
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertEqual(TRASH, tranche.CAPTURE_TRASH)
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        tranche._validate_capture_directory(capture)
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(capture.stat().st_mode), 0o700)

    def test_all_four_candidates_are_review_only_with_zero_normalized_rows(self) -> None:
        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["curated_source_record_count"],
                assessment["seed_eligible_count"],
                assessment["review_only_count"],
                assessment["current_status_unknown_count"],
                assessment["capacity_row_count"],
                assessment["coordinate_row_count"],
            ),
            (4, 0, 0, 4, 4, 0, 0),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        self.assertEqual(
            set(rows),
            {
                "hannam-ax-cluster-ai-gpu-hub-daejeon",
                "eg-ai-corp-dallas-immersion-gpu-facility",
                "qts-richmond-technology-park-dc5-ric5",
                "segro-slough-powered-shell-prelet-2026",
            },
        )
        for row in rows.values():
            self.assertTrue(row["decision"].startswith("review_only_"))
            self.assertFalse(row["direct_physical_work_body_available"])
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

    def test_source_native_boundaries_do_not_become_normalized_claims(self) -> None:
        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}

        hannam = rows["hannam-ax-cluster-ai-gpu-hub-daejeon"]
        self.assertFalse(
            hannam["source_native_process_facts"][
                "ceremony_is_physical_work_observation"
            ]
        )
        self.assertIn("320,000 GPU count or GPU model", hannam["withheld_claims"])

        egai = rows["eg-ai-corp-dallas-immersion-gpu-facility"]
        egai_power = egai["planned_power_candidate_metadata"]
        self.assertEqual((egai_power["value"], egai_power["unit"]), (2.5, "MW"))
        self.assertEqual(egai_power["metric_type"], "unspecified")
        self.assertIsNone(egai_power["is_it_load"])
        self.assertFalse(egai_power["normalized_capacity_row_created"])

        qts = rows["qts-richmond-technology-park-dc5-ric5"]
        self.assertEqual(qts["required_page_http_status"], 403)
        coordinate = qts["coordinate_candidate_metadata"]
        self.assertEqual(
            (coordinate["latitude"], coordinate["longitude"]),
            (37.505653, -77.265146),
        )
        self.assertFalse(coordinate["required_body_captured"])
        self.assertFalse(coordinate["verified_in_captured_body"])
        self.assertFalse(coordinate["seeded"])
        self.assertFalse(coordinate["geometry_created"])

        segro = rows["segro-slough-powered-shell-prelet-2026"]
        segro_power = segro["power_candidate_metadata"]
        self.assertEqual((segro_power["value"], segro_power["unit"]), (50, "MVA"))
        self.assertFalse(segro_power["converted_to_mw"])
        self.assertIsNone(segro_power["is_it_load"])
        self.assertFalse(segro_power["normalized_capacity_row_created"])
        self.assertIn(
            "Premier Park",
            segro["source_native_process_facts"]["separate_project_excluded"],
        )

    def test_transport_inventory_is_fresh_primary_only_and_fail_closed(self) -> None:
        inventory = json.loads((ARTIFACT / "retrieval-inventory.json").read_text())
        self.assertEqual(inventory["retrieval_attempt_count"], 19)
        self.assertEqual(inventory["successful_http_200_decoded_body_count"], 11)
        self.assertEqual(inventory["failed_http_403_body_count"], 8)
        self.assertEqual(inventory["direct_physical_work_body_count"], 0)
        self.assertEqual(inventory["claim_eligible_capture_count"], 0)
        self.assertFalse(inventory["search_snippets_used_for_claims"])
        self.assertFalse(inventory["transformed_web_text_used_for_claims"])
        self.assertFalse(inventory["publisher_media_used_for_claims"])

        rows = {row["request_id"]: row for row in inventory["requests"]}
        self.assertEqual(set(rows), set(tranche.REQUEST_IDS))
        for request_id, spec in tranche.REQUEST_SPECS.items():
            row = rows[request_id]
            self.assertEqual(row["http_status"], spec["expected_http_status"])
            self.assertEqual(row["requested_url"], spec["requested_url"])
            self.assertFalse(row["direct_physical_work_observation"])
            self.assertFalse(row["eligible_for_normalized_claims"])
            self.assertFalse(row["used_for_normalized_claims"])
            self.assertFalse(row["source_record_created"])
            self.assertFalse(row["raw_redistributed"])
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

    def test_v84_nonmutation_zero_sources_and_no_v85_integration(self) -> None:
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
        self.assertFalse(snapshot["integration"]["v85_mutated"])
        self.assertEqual(snapshot["integration"]["release_integration"], "none")
        self.assertEqual(
            snapshot["integration"]["downstream_product_integration"], "none"
        )

    def test_offline_replay_shim_no_residue_collision_and_future_clock(self) -> None:
        try:
            core = importlib.import_module(
                "datacenter_atlas.datacenter_atlas."
                "global_official_builds_unresolved_four_20260721"
            )
            shim = importlib.import_module(
                "datacenter_atlas.global_official_builds_unresolved_four_20260721"
            )
        except ModuleNotFoundError:
            core = importlib.import_module(
                "datacenter_atlas.global_official_builds_unresolved_four_20260721"
            )
            shim = tranche
        self.assertIs(core.validate_artifact, shim.validate_artifact)
        with self._offline():
            first = tranche.validate_artifact(ARTIFACT)
            second = tranche.validate_artifact(ARTIFACT)
        self.assertEqual(first, second)
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(
            list(tranche.ARTIFACT_ROOT.glob(f".{tranche.ARTIFACT_ID}.stage-*")),
            [],
        )

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
