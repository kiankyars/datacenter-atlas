from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.england_planning_data import (
    DERIVED_FILENAMES,
    EXPECTED_CSV_SHA256,
    EXPECTED_EXPLICIT_ENTITIES,
    EXPECTED_PROVIDER_ROW_COUNTS,
    EXPLICIT_TERMS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    OPTIONAL_TERMS,
    RAW_ARTIFACTS,
    RELEASE_ID,
    REVIEW_POLICY,
    SOURCE_FIELDS,
    EnglandPlanningDataError,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    matched_terms,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _rebuild_inputs() -> tuple[
    dict[str, dict[str, object]], dict[str, bytes], str
]:
    assessment = json.loads(
        (PINNED_RELEASE / "assessment.json").read_text(encoding="utf-8")
    )
    artifacts = assessment["official_open_artifacts"]
    retrievals = {
        artifact_id: {
            "content_type": artifacts[artifact_id]["content_type"],
            "effective_url": artifacts[artifact_id]["effective_url"],
            "headers": artifacts[artifact_id]["headers"],
            "http_status": artifacts[artifact_id]["http_status"],
            "url": artifacts[artifact_id]["url"],
        }
        for artifact_id in RAW_ARTIFACTS
    }
    bodies = {
        artifact_id: (PINNED_RELEASE / specification["filename"]).read_bytes()
        for artifact_id, specification in RAW_ARTIFACTS.items()
    }
    return retrievals, bodies, assessment["assessed_at"]


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


def _refresh_manifest_file(copied: Path, filename: str) -> None:
    artifact = copied / filename
    manifest_path = copied / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][filename]["bytes"] = artifact.stat().st_size
    manifest["files"][filename]["sha256"] = sha256_bytes(artifact.read_bytes())
    body = canonical_json(manifest)
    manifest_path.write_bytes(body)
    (copied / MANIFEST_HASH_FILENAME).write_text(
        f"{sha256_bytes(body)}  {MANIFEST_FILENAME}\n", encoding="utf-8"
    )


class EnglandPlanningDataTests(unittest.TestCase):
    def test_source_definition_matches_executable_contract(self) -> None:
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )

    def test_frozen_release_validates_offline(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["inventory"]["source_rows"], 100_627)
        self.assertEqual(bundle["inventory"]["unique_entity_count"], 100_627)
        self.assertEqual(
            {
                row["entity"]: row["row_count"]
                for row in bundle["inventory"]["row_provider_inventory"]
            },
            EXPECTED_PROVIDER_ROW_COUNTS,
        )
        discrepancy = bundle["inventory"]["provider_statistic_reconciliation"]
        self.assertEqual(discrepancy["official_page_data_provider_statistic"], 6)
        self.assertEqual(discrepancy["bulk_row_provider_entity_count"], 4)
        self.assertFalse(discrepancy["reconciled"])
        self.assertTrue(
            bundle["assessment"]["rights_assessment"]["rights_gate_passed"]
        )
        self.assertEqual(
            bundle["assessment"]["retrieval_batch"]["network_requests"], 8
        )
        self.assertEqual(
            bundle["assessment"]["retrieval_batch"][
                "validator_network_requests"
            ],
            0,
        )

    def test_observations_preserve_raw_values_and_forbid_promotion(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        observations = bundle["observations"]
        self.assertEqual(
            tuple(row["source_attributes"]["entity"] for row in observations),
            EXPECTED_EXPLICIT_ENTITIES,
        )
        self.assertEqual(len(observations), 4)
        for observation in observations:
            self.assertEqual(observation["record_type"], "planning_application_observation")
            self.assertTrue(observation["review_only"])
            self.assertFalse(observation["auto_merge"])
            self.assertTrue(observation["manual_review_required"])
            self.assertEqual(observation["promotion_boundaries"], REVIEW_POLICY)
            self.assertEqual(
                set(observation["source_attributes"]), set(SOURCE_FIELDS)
            )
            self.assertEqual(
                observation["raw_description"],
                observation["source_attributes"]["description"],
            )
            self.assertEqual(
                observation["source"]["bulk_file_sha256"], EXPECTED_CSV_SHA256
            )
            self.assertRegex(
                observation["source"]["raw_field_hash_sha256"], r"^[0-9a-f]{64}$"
            )
        context_only = next(
            row
            for row in observations
            if row["source_attributes"]["entity"] == "10000057188"
        )
        self.assertEqual(
            context_only["context_assessment"]["classification"],
            "context_only_exclusion",
        )
        self.assertIsNone(
            context_only["promotion_boundaries"]["facility_lifecycle_status"]
        )
        self.assertFalse(
            context_only["promotion_boundaries"]["construction_evidence"]
        )

        with (PINNED_RELEASE / "observations.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            csv_rows = list(csv.DictReader(source))
        self.assertEqual(len(csv_rows), 4)
        self.assertEqual(csv_rows[0]["source_description"], observations[0]["raw_description"])
        self.assertEqual(
            csv_rows[0]["source_raw_field_hash_sha256"],
            observations[0]["source"]["raw_field_hash_sha256"],
        )

    def test_phrase_contract_and_optional_review_are_exact(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        review = bundle["phrase_review"]
        self.assertEqual(review["explicit"]["included_observation_count"], 4)
        self.assertEqual(
            review["explicit"]["context_classification_counts"],
            {"context_only_exclusion": 1, "direct_data_centre_scope": 3},
        )
        self.assertEqual(
            review["explicit"]["term_hit_counts"],
            {
                "data center": 0,
                "data centre": 4,
                "data-center": 0,
                "datacentre": 0,
            },
        )
        optional = review["optional_incremental_outside_explicit"]
        self.assertEqual(
            {term: optional[term]["incremental_count"] for term in OPTIONAL_TERMS},
            {"data hall": 0, "server room": 3, "data processing": 0},
        )
        self.assertEqual(
            optional["server room"]["decision"],
            "excluded_after_review_low_precision",
        )
        self.assertEqual(len(optional["server room"]["candidates"]), 3)
        self.assertEqual(review["optional_observations_added"], 0)

        self.assertEqual(matched_terms("A DATA\nCENTRE extension", EXPLICIT_TERMS), ["data centre"])
        self.assertEqual(matched_terms("a data-center", EXPLICIT_TERMS), ["data-center"])
        self.assertEqual(matched_terms("a datacenter", EXPLICIT_TERMS), [])
        self.assertEqual(matched_terms("metadata centre", EXPLICIT_TERMS), [])

    def test_release_is_frozen_read_only(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))

    def test_offline_rebuild_reproduces_every_bundle_byte(self) -> None:
        retrievals, bodies, retrieved_at = _rebuild_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = write_release_bundle(
                Path(temporary) / "rebuilt",
                retrievals,
                bodies,
                retrieved_at,
                freeze=False,
            )
            original_files = sorted(
                path.relative_to(PINNED_RELEASE)
                for path in PINNED_RELEASE.rglob("*")
                if path.is_file()
            )
            rebuilt_files = sorted(
                path.relative_to(rebuilt)
                for path in rebuilt.rglob("*")
                if path.is_file()
            )
            self.assertEqual(rebuilt_files, original_files)
            for filename in original_files:
                self.assertEqual(
                    (rebuilt / filename).read_bytes(),
                    (PINNED_RELEASE / filename).read_bytes(),
                    str(filename),
                )

    def test_rights_policy_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment_path = copied / DERIVED_FILENAMES["assessment"]
            assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
            assessment["rights_assessment"]["rights_gate_passed"] = False
            assessment_path.write_bytes(canonical_json(assessment))
            _refresh_manifest_file(copied, DERIVED_FILENAMES["assessment"])
            with self.assertRaisesRegex(EnglandPlanningDataError, "rights gate"):
                validate_release_bundle(copied)

    def test_observation_promotion_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            observations_path = copied / DERIVED_FILENAMES["observations_jsonl"]
            observations = [
                json.loads(line)
                for line in observations_path.read_text(encoding="utf-8").splitlines()
            ]
            observations[0]["auto_merge"] = True
            observations_path.write_bytes(
                b"".join(canonical_json(row) for row in observations)
            )
            _refresh_manifest_file(copied, DERIVED_FILENAMES["observations_jsonl"])
            with self.assertRaisesRegex(
                EnglandPlanningDataError, "offline reproduction mismatch"
            ):
                validate_release_bundle(copied)

    def test_lineage_url_drift_fails_closed(self) -> None:
        retrievals, bodies, retrieved_at = _rebuild_inputs()
        retrievals["bulk_csv"]["effective_url"] = (
            "https://example.invalid/planning-application.csv"
        )
        with self.assertRaisesRegex(EnglandPlanningDataError, "lineage URL"):
            derive_release_files(retrievals, bodies, retrieved_at)

    def test_existing_output_is_never_overwritten(self) -> None:
        retrievals, bodies, retrieved_at = _rebuild_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(EnglandPlanningDataError, "already exists"):
                write_release_bundle(temporary, retrievals, bodies, retrieved_at)


if __name__ == "__main__":
    unittest.main()
