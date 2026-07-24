from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from datacenter_atlas.ireland_planning import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    MATCHED_PAGE_URL,
    RAW_ARTIFACTS,
    RELEASE_ID,
    IrelandPlanningError,
    canonical_json,
    sha256_bytes,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    body = "".join(
        json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
        for record in records
    )
    path.write_text(body, encoding="utf-8")


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    copied.chmod(0o755)
    for entry in copied.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)
    return copied


def _refresh_manifest(copied: Path, filename: str) -> None:
    artifact = copied / filename
    manifest_path = copied / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][filename]["bytes"] = artifact.stat().st_size
    manifest["files"][filename]["sha256"] = sha256_bytes(
        artifact.read_bytes()
    )
    manifest_body = canonical_json(manifest)
    manifest_path.write_bytes(manifest_body)
    copied.joinpath(MANIFEST_HASH_FILENAME).write_text(
        f"{sha256_bytes(manifest_body)}  manifest.json\n",
        encoding="utf-8",
    )


class IrelandPlanningReleaseTests(unittest.TestCase):
    def test_pinned_release_validates_offline_with_exact_boundaries(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        summary = bundle["summary"]
        self.assertEqual(summary["matched_observation_count"], 114)
        self.assertEqual(summary["baseline_exact_phrase_count"], 102)
        self.assertEqual(summary["extension_count"], 12)
        self.assertEqual(
            assessment["coverage_assessment"]["source_total_rows"], 499_712
        )
        self.assertIsNone(summary["unique_site_count"])
        self.assertEqual(
            assessment["retrieval_batch"]["open_raw_artifacts_retained"], 15
        )
        self.assertEqual(
            assessment["retrieval_batch"]["precision_review_rows_retrieved"],
            2,
        )
        self.assertEqual(assessment["query_assessment"]["feature_page_count"], 2)
        self.assertFalse(
            assessment["retrieval_batch"][
                "restricted_calibration_raw_retained"
            ]
        )
        self.assertFalse(any(PINNED_RELEASE.rglob("*.pdf")))

    def test_observations_remain_planning_evidence_not_facilities(self) -> None:
        observations = _jsonl(PINNED_RELEASE / "observations.jsonl")
        self.assertEqual(len(observations), 114)
        self.assertEqual(
            [row["source_attributes"]["OBJECTID"] for row in observations],
            sorted(row["source_attributes"]["OBJECTID"] for row in observations),
        )
        for observation in observations:
            self.assertEqual(
                observation["evidence_scope"],
                {
                    "construction_evidence": False,
                    "facility_lifecycle_status": None,
                    "operation_evidence": False,
                    "record_type": "planning_application_observation",
                },
            )
            self.assertEqual(len(observation["source_attributes"]), 37)
            self.assertEqual(observation["coordinates"]["crs"], "EPSG:4326")
            self.assertTrue(observation["matched_terms"])
            self.assertEqual(
                observation["source_numeric_fields"]["AreaofSite"]["unit"],
                "unknown_source_unit",
            )
            self.assertEqual(
                observation["source_numeric_fields"]["FloorArea"]["unit"],
                "unknown_source_unit",
            )

        with PINNED_RELEASE.joinpath("observations.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            csv_rows = list(csv.DictReader(source))
        self.assertEqual(len(csv_rows), 114)
        self.assertIn("date_ReceivedDate_utc", csv_rows[0])
        self.assertEqual(
            csv_rows[0]["date_ReceivedDate_utc"],
            observations[0]["dates"]["ReceivedDate"]["utc"],
        )
        self.assertEqual(
            csv_rows[0]["source_ReceivedDate"],
            str(observations[0]["source_attributes"]["ReceivedDate"]),
        )

    def test_query_and_precision_review_are_exactly_pinned(self) -> None:
        parameters = parse_qs(urlsplit(MATCHED_PAGE_URL).query)
        self.assertEqual(parameters["outFields"], ["*"])
        self.assertEqual(parameters["returnGeometry"], ["true"])
        self.assertEqual(parameters["outSR"], ["4326"])
        self.assertEqual(parameters["orderByFields"], ["OBJECTID ASC"])
        self.assertEqual(parameters["resultOffset"], ["0"])
        self.assertEqual(parameters["resultRecordCount"], ["2000"])

        assessment = json.loads(
            (PINNED_RELEASE / "assessment.json").read_text(encoding="utf-8")
        )
        review = assessment["vocabulary_assessment"][
            "manual_precision_review"
        ]
        self.assertEqual(review["data hall"]["incremental_count"], 11)
        self.assertEqual(
            review["data processing centre"]["incremental_count"], 1
        )
        self.assertEqual(
            review["co-location facility"]["review_candidate_objectids"],
            [355889, 387473],
        )
        self.assertEqual(review["co-location facility"]["decision"], "excluded")
        self.assertEqual(review["server room"]["incremental_count"], 14)

    def test_relationship_suggestions_are_review_only(self) -> None:
        suggestions = _jsonl(
            PINNED_RELEASE / "relationship-suggestions.jsonl"
        )
        summary = json.loads(
            (PINNED_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(suggestions), 32)
        self.assertEqual(
            summary["relationship_suggestion_counts_by_basis"],
            {
                "shared_authority_application_number": 2,
                "shared_authority_normalized_address": 15,
                "shared_exact_wgs84_coordinate": 14,
                "shared_source_site_id": 1,
            },
        )
        for suggestion in suggestions:
            self.assertTrue(suggestion["review_only"])
            self.assertFalse(suggestion["auto_merge_permitted"])
            self.assertGreaterEqual(len(suggestion["member_observation_ids"]), 2)

    def test_offline_rebuild_recreates_every_bundle_byte(self) -> None:
        assessment = json.loads(
            (PINNED_RELEASE / "assessment.json").read_text(encoding="utf-8")
        )
        artifacts = assessment["official_open_artifacts"]
        retrievals = {
            artifact_id: {
                "content_type": artifacts[artifact_id]["content_type"],
                "effective_url": artifacts[artifact_id]["effective_url"],
                "http_status": artifacts[artifact_id]["http_status"],
                "url": artifacts[artifact_id]["url"],
            }
            for artifact_id in RAW_ARTIFACTS
        }
        raw_bodies = {
            artifact_id: PINNED_RELEASE.joinpath(
                specification["filename"]
            ).read_bytes()
            for artifact_id, specification in RAW_ARTIFACTS.items()
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rebuilt"
            write_release_bundle(
                output,
                retrievals,
                raw_bodies,
                assessment["restricted_operational_calibration"],
                assessment["assessed_at"],
            )
            original_files = sorted(
                path.relative_to(PINNED_RELEASE)
                for path in PINNED_RELEASE.rglob("*")
                if path.is_file()
            )
            rebuilt_files = sorted(
                path.relative_to(output)
                for path in output.rglob("*")
                if path.is_file()
            )
            self.assertEqual(rebuilt_files, original_files)
            for filename in original_files:
                self.assertEqual(
                    (output / filename).read_bytes(),
                    (PINNED_RELEASE / filename).read_bytes(),
                )

    def test_release_is_frozen_read_only(self) -> None:
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            expected = 0o555 if entry.is_dir() else 0o444
            self.assertEqual(entry.stat().st_mode & 0o777, expected)

    def test_rights_boundary_cannot_be_relaxed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment_path = copied / "assessment.json"
            assessment = json.loads(
                assessment_path.read_text(encoding="utf-8")
            )
            assessment["rights_assessment"]["attribution_required"] = False
            assessment_path.write_bytes(canonical_json(assessment))
            _refresh_manifest(copied, "assessment.json")
            with self.assertRaisesRegex(IrelandPlanningError, "rights"):
                validate_release_bundle(copied)

    def test_lifecycle_promotion_breaks_offline_reproduction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            observations_path = copied / "observations.jsonl"
            observations = _jsonl(observations_path)
            observations[0]["evidence_scope"][
                "facility_lifecycle_status"
            ] = "under_construction"
            observations[0]["evidence_scope"]["construction_evidence"] = True
            _write_jsonl(observations_path, observations)
            _refresh_manifest(copied, "observations.jsonl")
            with self.assertRaisesRegex(
                IrelandPlanningError, "offline reproduction"
            ):
                validate_release_bundle(copied)

    def test_review_suggestion_cannot_become_an_automatic_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            suggestions_path = copied / "relationship-suggestions.jsonl"
            suggestions = _jsonl(suggestions_path)
            suggestions[0]["auto_merge_permitted"] = True
            suggestions[0]["review_only"] = False
            _write_jsonl(suggestions_path, suggestions)
            _refresh_manifest(copied, "relationship-suggestions.jsonl")
            with self.assertRaisesRegex(
                IrelandPlanningError, "offline reproduction"
            ):
                validate_release_bundle(copied)

    def test_raw_count_tampering_is_rejected_after_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            count_path = copied / "raw/final-count.json"
            count_path.write_bytes(b'{"count":115}')
            _refresh_manifest(copied, "raw/final-count.json")
            with self.assertRaisesRegex(IrelandPlanningError, "final_count"):
                validate_release_bundle(copied)

    def test_unpinned_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            (copied / "restricted-report.pdf").write_bytes(b"not retained")
            with self.assertRaisesRegex(IrelandPlanningError, "file set"):
                validate_release_bundle(copied)


if __name__ == "__main__":
    unittest.main()
