from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.adapters import ImportResult
from datacenter_atlas.fuzzy_snapshot import (
    FuzzySnapshotError,
    build_fuzzy_review_snapshot,
    fuzzy_review_readme,
)
from datacenter_atlas.global_snapshot import validate_release_files
from datacenter_atlas.natural_earth import EnrichmentResult


class FuzzySnapshotTests(unittest.TestCase):
    def _source_manifest(self) -> dict[str, object]:
        return {
            "state": "completed",
            "review_only": True,
            "snapshot_date": "2026-07-13",
            "counts": {
                "broad_match_counts": {"total": 0},
                "classification_counts": {
                    "ambiguous": 0,
                    "exact_92_pair": 0,
                    "explicit_marker_variant": 0,
                    "textual_only": 0,
                    "unknown_key_explicit_value": 0,
                },
                "supplemental_eligible_count": 0,
                "exact_layer_duplicate_count": 0,
            },
        }

    def test_readme_keeps_candidates_out_of_confirmed_counts(self) -> None:
        readme = fuzzy_review_readme(
            as_of="2026-07-18",
            snapshot_date="2026-07-13",
            integrity={
                "broad_match_counts": {"total": 10},
                "classification_counts": {
                    "explicit_marker_variant": 2,
                    "unknown_key_explicit_value": 1,
                    "textual_only": 4,
                    "ambiguous": 1,
                },
                "supplemental_eligible_count": 8,
                "exact_layer_duplicate_count": 2,
            },
            summary={
                "entities_total": 8,
                "entities_by_status": {"under_construction": 1, "lead": 7},
            },
        )
        self.assertIn("review release contains 8 supplemental", readme)
        self.assertIn("not a census", readme)
        self.assertIn("18", fuzzy_review_readme(
            as_of="2026-07-18",
            snapshot_date="2026-07-13",
            integrity={
                "broad_match_counts": {"total": 18},
                "classification_counts": {"explicit_marker_variant": 18},
                "supplemental_eligible_count": 18,
                "exact_layer_duplicate_count": 0,
            },
            summary={"entities_total": 18, "entities_by_status": {"under_construction": 18}},
        ))
        self.assertIn("must not be reported as counts of projects being built", readme)
        self.assertIn("ODbL", readme)

    def test_builder_publishes_atomic_closed_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialization = root / "materialized"
            materialization.mkdir()
            (materialization / "manifest.json").write_text("{}")
            output = root / "release"
            empty = ImportResult(source="openstreetmap:fuzzy_discovery")
            country = EnrichmentResult(0, 0, 0, 0, 0, 0, 0, 0)
            with (
                patch(
                    "datacenter_atlas.fuzzy_snapshot.materialize_fuzzy_extract",
                    return_value=self._source_manifest(),
                ),
                patch(
                    "datacenter_atlas.fuzzy_snapshot.OpenStreetMapFuzzyDiscoveryAdapter"
                ) as adapter,
                patch(
                    "datacenter_atlas.fuzzy_snapshot.enrich_administrative_assignments",
                    return_value=country,
                ),
            ):
                adapter.return_value.import_file.return_value = empty
                result = build_fuzzy_review_snapshot(
                    extraction_manifest=root / "extract.json",
                    materialization=materialization,
                    natural_earth_input=root / "natural-earth",
                    output_directory=output,
                    as_of="2026-07-18",
                    recorded_at="2026-07-18T20:00:00Z",
                    retrieved_at="2026-07-18T18:15:02Z",
                )
            manifest = validate_release_files(output)
            self.assertTrue(result["review_only"])
            self.assertIn("atlas.sqlite", manifest["files"])
            self.assertIn("atlas.html", manifest["files"])
            self.assertIn("fuzzy_review_shortlist.csv", manifest["files"])
            self.assertIn("fuzzy_review_triage.json", manifest["files"])
            self.assertEqual(result["triage"]["counts"]["shortlisted_candidates"], 0)
            self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_builder_canonicalizes_equivalent_recorded_at_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialization = root / "materialized"
            materialization.mkdir()
            (materialization / "manifest.json").write_text("{}")
            output = root / "release"
            empty = ImportResult(source="openstreetmap:fuzzy_discovery")
            country = EnrichmentResult(0, 0, 0, 0, 0, 0, 0, 0)
            with (
                patch(
                    "datacenter_atlas.fuzzy_snapshot.materialize_fuzzy_extract",
                    return_value=self._source_manifest(),
                ),
                patch(
                    "datacenter_atlas.fuzzy_snapshot.OpenStreetMapFuzzyDiscoveryAdapter"
                ) as adapter,
                patch(
                    "datacenter_atlas.fuzzy_snapshot.enrich_administrative_assignments",
                    return_value=country,
                ),
            ):
                adapter.return_value.import_file.return_value = empty
                build_fuzzy_review_snapshot(
                    extraction_manifest=root / "extract.json",
                    materialization=materialization,
                    natural_earth_input=root / "natural-earth",
                    output_directory=output,
                    as_of="2026-07-18",
                    recorded_at="2026-07-18T21:00:00.000+01:00",
                    retrieved_at="2026-07-18T18:15:02Z",
                )
            manifest = validate_release_files(output)
            self.assertEqual(manifest["recorded_at"], "2026-07-18T20:00:00Z")

    def test_mismatched_source_counts_leave_no_release_or_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialization = root / "materialized"
            materialization.mkdir()
            (materialization / "manifest.json").write_text("{}")
            output = root / "release"
            source = self._source_manifest()
            source["counts"] = {
                "broad_match_counts": {"total": 1},
                "supplemental_eligible_count": 1,
                "exact_layer_duplicate_count": 0,
            }
            with (
                patch(
                    "datacenter_atlas.fuzzy_snapshot.materialize_fuzzy_extract",
                    return_value=source,
                ),
                patch(
                    "datacenter_atlas.fuzzy_snapshot.OpenStreetMapFuzzyDiscoveryAdapter"
                ) as adapter,
            ):
                adapter.return_value.import_file.return_value = ImportResult(
                    source="fixture", examined_elements=1, imported_elements=0, skipped_elements=1
                )
                with self.assertRaisesRegex(FuzzySnapshotError, "do not reconcile"):
                    build_fuzzy_review_snapshot(
                        extraction_manifest=root / "extract.json",
                        materialization=materialization,
                        natural_earth_input=root / "natural-earth",
                        output_directory=output,
                        as_of="2026-07-18",
                        recorded_at="2026-07-18T20:00:00Z",
                        retrieved_at="2026-07-18T18:15:02Z",
                    )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".release.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
