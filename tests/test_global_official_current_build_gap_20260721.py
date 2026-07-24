from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import stat
import tempfile
import unittest

try:
    from datacenter_atlas.datacenter_atlas import (
        global_official_current_build_gap_20260721 as gap,
    )
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import global_official_current_build_gap_20260721 as gap
    from datacenter_atlas.open_seed_v56 import tree_digest


class OfficialCurrentBuildGapTests(unittest.TestCase):
    def test_candidates_collision_and_normalized_contract_are_exact(self) -> None:
        documents = gap.expected_source_documents()
        self.assertEqual(tuple(documents), gap.SOURCE_FILENAMES)
        witness = gap._base_collision_witness(documents)
        self.assertEqual(
            witness["exact_stable_key_collisions"], [gap.DENTON_CAMPUS]
        )
        self.assertEqual(witness["exact_evidence_key_collisions"], [])
        self.assertEqual(
            witness["candidate_alias_matches"]["webster_county"], []
        )
        self.assertEqual(witness["candidate_alias_matches"]["rowan_identity"], [])
        with tempfile.TemporaryDirectory(
            prefix="official-current-build-gap-test-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            gap._write_source_stage(root, documents)
            paths = gap._source_paths(root)
            records = gap._validate_sources(paths)
            self.assertEqual(len(records), 5)
            self.assertEqual(
                gap._offline_import(paths, "2026-07-22T00:31:00Z"),
                {
                    "entities": 9,
                    "entity_snapshots": 9,
                    "evidence": 6,
                    "lifecycle_observations": 5,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 2,
                },
            )

    def test_capture_is_closed_hash_bound_and_recoverable(self) -> None:
        capture = (
            gap.CAPTURE_ORIGIN if gap.CAPTURE_ORIGIN.exists() else gap.CAPTURE_TRASH
        )
        gap._validate_capture_directory(capture)
        self.assertEqual(len(list(capture.iterdir())), 18)
        self.assertEqual(tree_digest(capture), gap.CAPTURE_TREE_SHA256)

    def test_private_artifact_replays_twice_and_preserves_review_holds(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="official-current-build-gap-artifact-test-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            artifact = root / "artifact"
            sources.mkdir()
            artifact.mkdir()
            documents = gap.expected_source_documents()
            gap._write_source_stage(sources, documents)
            gap._write_artifact_stage(
                artifact, "2026-07-22T00:31:00Z", documents
            )
            manifest = gap.validate_artifact(
                artifact,
                source_paths=gap._source_paths(sources),
                require_live=False,
                wall_clock=gap._instant("2026-07-22T00:31:00Z"),
            )
            self.assertEqual(manifest["curated_source_records"], 5)
            assessment = json.loads(
                (artifact / "candidate-assessment.json").read_text(encoding="utf-8")
            )
            decisions = {
                row["candidate_id"]: row["decision"]
                for row in assessment["candidates"]
            }
            self.assertEqual(
                decisions["dc-blox-palm-coast-cable-landing-station"],
                "review_only_facility_type_schema_boundary",
            )
            self.assertEqual(
                decisions[
                    "fort-worth-council-district-7-anonymous-current-build"
                ],
                "review_only_anonymous_count_level_evidence",
            )
            artifact.chmod(0o700)

    def test_past_wall_and_partial_final_collision_fail_without_mutation(self) -> None:
        before = {
            "v87_definition": gap._sha256(gap.V87_DEFINITION),
            "v87_tree": tree_digest(gap.V87_RELEASE),
            "capture_tree": tree_digest(
                gap.CAPTURE_ORIGIN
                if gap.CAPTURE_ORIGIN.exists()
                else gap.CAPTURE_TRASH
            ),
        }
        past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        if gap.ARTIFACT.exists():
            manifest = json.loads(
                (gap.ARTIFACT / "manifest.json").read_text(encoding="utf-8")
            )
            with self.assertRaises(gap.OfficialCurrentBuildGapError):
                gap.validate_artifact(
                    wall_clock=gap._instant(manifest["recorded_at"])
                    - timedelta(seconds=1)
                )
            self.assertEqual(gap.build(recorded_at=past)["status"], "existing-identical")
        else:
            with self.assertRaises(gap.OfficialCurrentBuildGapError):
                gap.build(recorded_at=past)
        after = {
            "v87_definition": gap._sha256(gap.V87_DEFINITION),
            "v87_tree": tree_digest(gap.V87_RELEASE),
            "capture_tree": tree_digest(
                gap.CAPTURE_ORIGIN
                if gap.CAPTURE_ORIGIN.exists()
                else gap.CAPTURE_TRASH
            ),
        }
        self.assertEqual(before, after)

    @unittest.skipUnless(gap.ARTIFACT.exists(), "final artifact not published yet")
    def test_final_artifact_is_frozen_live_and_exact(self) -> None:
        manifest = gap.validate_artifact()
        self.assertEqual(manifest["candidate_assessments"], 6)
        self.assertEqual(manifest["seed_eligible_source_records"], 5)
        self.assertEqual(manifest["review_only_candidates"], 2)
        self.assertEqual(stat.S_IMODE(gap.ARTIFACT.stat().st_mode), 0o555)
        self.assertTrue(gap.CAPTURE_TRASH.is_dir())
        self.assertFalse(gap.CAPTURE_ORIGIN.exists())
        self.assertTrue(
            all(
                stat.S_IMODE((gap.SOURCES_ROOT / name).stat().st_mode) == 0o444
                for name in gap.SOURCE_FILENAMES
            )
        )


if __name__ == "__main__":
    unittest.main()
