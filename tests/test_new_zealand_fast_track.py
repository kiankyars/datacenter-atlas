from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from datacenter_atlas.new_zealand_fast_track import (
    ARTIFACT_ORDER,
    BROWSER_ARTIFACTS,
    CURRENT_AUCKLAND_ID,
    DATAGRID_ID,
    DIRECT_ARTIFACTS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    OBSERVATION_ORDER,
    PRIOR_AUCKLAND_ID,
    PRIOR_RELATED,
    PROJECT_CANDIDATE,
    RAW_PATHS,
    RELEASE_ID,
    REVIEW_POLICY,
    RIGHTS_POLICY,
    NewZealandFastTrackError,
    canonical_json,
    definition_from_capture,
    is_frozen_release,
    load_definition,
    sha256_bytes,
    thaw_for_test,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
SCRIPT = PROJECT_ROOT / "scripts" / "fetch_build_new_zealand_fast_track.py"
EXPECTED_MANIFEST_SHA256 = (
    "97e9b78cc516acd48e6d3e3f80d367977bc7ae3b882820dc3e0f7e185b6cb264"
)


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
    manifest["files"][filename]["sha256"] = sha256_bytes(
        artifact.read_bytes()
    )
    manifest_raw = canonical_json(manifest, pretty=True)
    manifest_path.write_bytes(manifest_raw)
    (copied / MANIFEST_HASH_FILENAME).write_text(
        f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n",
        encoding="ascii",
    )


class NewZealandFastTrackTests(unittest.TestCase):
    def test_definition_is_canonical_and_matches_capture_contract(self) -> None:
        definition, raw = load_definition(SOURCE_DEFINITION)
        self.assertEqual(raw, canonical_json(definition, pretty=True))
        capture = {
            "artifacts": definition["raw_artifacts"],
            "request_log": definition["request_log"],
            "retrieval_policy": definition["retrieval_policy"],
            "retrieved_at": definition["retrieved_at"],
        }
        self.assertEqual(definition_from_capture(capture), definition)
        self.assertEqual(definition["observation_ids_in_order"], list(OBSERVATION_ORDER))
        self.assertFalse(definition["scope"]["coverage_complete"])
        self.assertIsNone(definition["scope"]["unique_physical_site_count"])

    def test_frozen_release_validates_and_reproduces_offline(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        self.assertEqual(
            [item["observation_id"] for item in bundle["observations"]],
            list(OBSERVATION_ORDER),
        )
        self.assertEqual(
            bundle["assessment"]["candidate_classification_counts"],
            {PROJECT_CANDIDATE: 2, PRIOR_RELATED: 1},
        )
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()),
            EXPECTED_MANIFEST_SHA256,
        )

    def test_current_auckland_process_and_declared_type_are_qualified(self) -> None:
        observations = validate_release_bundle(PINNED_RELEASE)["observations"]
        current = next(
            item for item in observations if item["observation_id"] == CURRENT_AUCKLAND_ID
        )
        self.assertEqual(current["candidate_classification"], PROJECT_CANDIDATE)
        self.assertEqual(current["physical_status"]["label"], "proposed")
        self.assertFalse(current["physical_status"]["construction_source_supported"])
        self.assertFalse(current["physical_status"]["operation_source_supported"])
        self.assertEqual(
            current["data_centre_characterisation"]["declared_facility_type"],
            "hyperscale",
        )
        self.assertEqual(
            current["data_centre_characterisation"]["declared_workload"],
            "artificial_intelligence",
        )
        self.assertFalse(
            current["data_centre_characterisation"]["operationally_verified"]
        )
        self.assertIsNone(
            current["mixed_project_context"]["project_area_hectares"]
        )
        self.assertFalse(
            current["mixed_project_context"]["data_centre_land_area_promoted"]
        )
        self.assertEqual(
            [(event["date"], event["event"]) for event in current["planning_process"]["events"]],
            [
                ("2025-03-21", "referral_application_lodged"),
                ("2025-06-24", "referred_to_fast_track"),
                ("2026-03-11", "first_substantive_application_made"),
                ("2026-04-01", "first_substantive_application_withdrawn"),
                ("2026-05-07", "second_substantive_application_lodged"),
                (
                    "2026-05-28",
                    "second_substantive_application_returned_for_section_46_2_noncompliance",
                ),
                ("2026-06-19", "third_substantive_application_lodged"),
                (
                    "2026-07-09",
                    "third_substantive_application_deemed_complete_under_section_46_2",
                ),
            ],
        )

    def test_datagrid_has_no_capacity_power_or_energy_metric(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        datagrid = next(
            item
            for item in bundle["observations"]
            if item["observation_id"] == DATAGRID_ID
        )
        self.assertEqual(datagrid["project"]["application_id"], "FTA104")
        self.assertEqual(datagrid["project"]["location"], "Southland, New Zealand")
        self.assertEqual(
            datagrid["planning_process"]["current_state"],
            "older_official_application_metadata_only",
        )
        for field in (
            "annual_energy_observations",
            "capacity_observations",
            "power_observations",
            "pue_observations",
        ):
            self.assertEqual(datagrid["facility_metrics"][field], [])
        boundary = bundle["assessment"]["advisory_report_boundary"]
        self.assertFalse(boundary["optional_advisory_report_retained"])
        self.assertFalse(boundary["capacity_statement_retained"])
        self.assertFalse(boundary["power_or_energy_metric_emitted"])

    def test_prior_auckland_is_context_not_a_separate_site(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        prior = next(
            item
            for item in bundle["observations"]
            if item["observation_id"] == PRIOR_AUCKLAND_ID
        )
        self.assertEqual(prior["candidate_classification"], PRIOR_RELATED)
        context = prior["facility_metrics"]["untyped_context_statements"]
        self.assertEqual(len(context), 1)
        self.assertIsNone(context[0]["metric_type"])
        self.assertIsNone(context[0]["value"])
        self.assertIsNone(context[0]["unit"])
        self.assertFalse(context[0]["promoted_to_data_centre_power_or_energy"])
        relationship = bundle["relationships"]
        self.assertEqual(relationship["group_count"], 1)
        self.assertFalse(relationship["groups"][0]["accepted"])
        self.assertFalse(
            relationship["groups"][0]["counted_as_separate_unique_site"]
        )
        self.assertIsNone(relationship["unique_physical_site_count"])

    def test_retained_scope_is_text_only_with_exact_request_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        definition = bundle["definition"]
        self.assertEqual(set(definition["raw_artifacts"]), set(ARTIFACT_ORDER))
        self.assertEqual(
            Counter(
                spec["capture_method"]
                for spec in definition["raw_artifacts"].values()
            ),
            Counter(
                {
                    "browser_text_extraction_from_official_url": 2,
                    "direct_https_get_text_extraction_from_official_html": 3,
                }
            ),
        )
        self.assertEqual(len(BROWSER_ARTIFACTS), 2)
        self.assertEqual(len(DIRECT_ARTIFACTS), 3)
        self.assertTrue(all(path.endswith(".json") for path in RAW_PATHS.values()))
        files = {
            path.relative_to(PINNED_RELEASE).as_posix()
            for path in PINNED_RELEASE.rglob("*")
            if path.is_file()
        }
        self.assertFalse(any(path.endswith((".pdf", ".html")) for path in files))
        self.assertEqual(
            bundle["assessment"]["request_lineage"]["capture_events"], 5
        )
        self.assertEqual(
            bundle["assessment"]["request_lineage"]["validator_network_requests"],
            0,
        )

    def test_rights_and_review_boundaries_are_exact(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        rights = bundle["assessment"]["rights_assessment"]
        for key, value in RIGHTS_POLICY.items():
            self.assertEqual(rights[key], value)
        self.assertTrue(rights["rights_gate_passed_for_retained_scope"])
        self.assertTrue(rights["retained_artifacts_are_text_extracts"])
        for observation in bundle["observations"]:
            self.assertEqual(observation["promotion_boundaries"], REVIEW_POLICY)
            self.assertTrue(observation["review_only"])
            self.assertFalse(observation["unique_site_counted"])

    def test_validate_only_cli_reports_zero_network_requests(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-only"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["network_requests"], 0)
        self.assertEqual(payload["observations"], 3)
        self.assertEqual(payload["manifest_sha256"], EXPECTED_MANIFEST_SHA256)

    def test_raw_or_derived_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            raw_relative = RAW_PATHS["fasttrack_auckland_stage2"]
            raw_path = copied / raw_relative
            raw_path.write_bytes(raw_path.read_bytes() + b" ")
            _refresh_manifest_file(copied, raw_relative)
            with self.assertRaisesRegex(
                NewZealandFastTrackError, "captured artifact changed"
            ):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            observations_path = copied / "observations.jsonl"
            observations = [
                json.loads(line)
                for line in observations_path.read_text(encoding="utf-8").splitlines()
            ]
            observations[0]["physical_status"]["construction_source_supported"] = True
            observations_path.write_bytes(
                b"".join(canonical_json(item) for item in observations)
            )
            _refresh_manifest_file(copied, "observations.jsonl")
            with self.assertRaisesRegex(
                NewZealandFastTrackError, "offline reproduction mismatch"
            ):
                validate_release_bundle(copied)


if __name__ == "__main__":
    unittest.main()
