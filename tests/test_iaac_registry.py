from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.iaac_registry import (
    DIRECT_PROJECTS,
    EXPECTED_CLOSED_SET_SHA256,
    EXPECTED_RAW_INVENTORY_SHA256,
    EXPECTED_SEARCH_INVENTORY_SHA256,
    IAACRegistryError,
    INFERENCE_POLICY,
    MANIFEST_FILENAME,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_URL,
    canonical_json,
    classify_search_results,
    derive_release_files,
    is_frozen_release,
    parse_search_results,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _jsonl(filename: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (PINNED_RELEASE / filename).read_text(encoding="utf-8").splitlines()
    ]


def _capture_inputs() -> tuple[dict[str, object], dict[str, bytes]]:
    capture = json.loads(
        (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
    )
    raw = {
        value["filename"]: (PINNED_RELEASE / value["filename"]).read_bytes()
        for value in capture["retrievals"].values()
    }
    return capture, raw


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


class IAACRegistryTests(unittest.TestCase):
    def test_pinned_bundle_validates_offline_with_exact_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        self.assertEqual(len(bundle["search_inventory"]), 41)
        self.assertEqual(len(bundle["direct_observations"]), 4)
        self.assertEqual(len(bundle["geospatial_inventory"]), 3)
        self.assertEqual(
            assessment["selection_assessment"],
            {
                "closed_set_sha256": EXPECTED_CLOSED_SET_SHA256,
                "direct_rows": 4,
                "excluded_rows": 37,
                "exclusion_category_counts": {
                    "existing_data_centre_ancillary_work": 3,
                    "generic_data_centre_token_collision": 33,
                    "non_data_centre_data_processing_facility": 1,
                },
                "result_rows": 41,
                "search_inventory_sha256": EXPECTED_SEARCH_INVENTORY_SHA256,
            },
        )
        self.assertIsNone(
            assessment["coverage_assessment"]["unique_physical_site_count"]
        )

    def test_all_41_results_have_explicit_closed_set_decisions(self) -> None:
        rows = _jsonl("search-inventory.jsonl")
        self.assertEqual(
            [row["result_position"] for row in rows], list(range(1, 42))
        )
        self.assertEqual(
            {row["reference_number"] for row in rows if row["classification"] == "direct"},
            set(DIRECT_PROJECTS),
        )
        self.assertEqual(
            Counter(row["classification"] for row in rows),
            Counter({"excluded": 37, "direct": 4}),
        )
        self.assertTrue(all(row["review_reason"] for row in rows))
        excluded = [row for row in rows if row["classification"] == "excluded"]
        self.assertTrue(all(row["exclusion_category"] for row in excluded))
        ancillary = {
            row["reference_number"]
            for row in excluded
            if row["exclusion_category"] == "existing_data_centre_ancillary_work"
        }
        self.assertEqual(ancillary, {"81737", "83921", "81092"})

    def test_search_parser_reproduces_the_pinned_classification(self) -> None:
        body = (PINNED_RELEASE / "raw/search.html").read_bytes()
        parsed = classify_search_results(parse_search_results(body))
        stored = [
            {key: value for key, value in row.items() if key not in {"observation_id", "record_type", "source"}}
            for row in _jsonl("search-inventory.jsonl")
        ]
        self.assertEqual(parsed, stored)

    def test_supporting_generation_is_never_data_centre_load_or_energy(self) -> None:
        rows = {
            row["reference_number"]: row
            for row in _jsonl("direct-observations.jsonl")
        }
        self.assertEqual(
            {ref: rows[ref]["source_power_statement"]["value"] for ref in ("90036", "90123", "90121")},
            {"90036": 650, "90123": 920, "90121": 1494},
        )
        for reference in ("90036", "90123", "90121"):
            power = rows[reference]["source_power_statement"]
            self.assertEqual(power["metric"], "supporting_generation_production_capacity_mw")
            self.assertFalse(power["is_data_centre_load"])
            self.assertFalse(power["is_it_capacity"])
            self.assertFalse(power["is_annual_energy"])
            self.assertIsNone(rows[reference]["data_centre_capacity"])

    def test_bell_source_wording_and_construction_evidence_are_narrow(self) -> None:
        bell = next(
            row for row in _jsonl("direct-observations.jsonl")
            if row["reference_number"] == "90514"
        )
        self.assertEqual(bell["data_centre_capacity"]["value"], 300)
        self.assertFalse(bell["data_centre_capacity"]["is_it_capacity"])
        self.assertFalse(bell["data_centre_capacity"]["is_annual_energy"])
        self.assertIsNone(bell["source_power_statement"]["is_data_centre_load"])
        self.assertEqual(bell["site_area"]["value"], 65)
        self.assertEqual(bell["site_area"]["unit"], "ha")
        self.assertEqual(bell["construction_evidence"]["as_of_date"], "2026-06-05")
        self.assertIn(
            "physical activity has substantially begun",
            bell["construction_evidence"]["source_text"],
        )
        self.assertFalse(bell["construction_evidence"]["operation_evidence"])

    def test_completed_is_process_status_and_operation_is_never_inferred(self) -> None:
        rows = _jsonl("direct-observations.jsonl")
        for row in rows:
            process = row["assessment_process"]
            self.assertEqual(process["assessment_status_exact"], "Completed")
            self.assertFalse(process["assessment_status_is_physical_lifecycle"])
            self.assertTrue(row["proposal_wording_present"])
            self.assertIsNone(row["unique_physical_site_id"])
            self.assertIsNone(row["atlas_inference"]["atlas_lifecycle_status"])
            self.assertFalse(row["atlas_inference"]["operation_verified"])
        self.assertEqual(sum(row["construction_evidence"] is not None for row in rows), 1)

    def test_only_explicitly_licensed_geospatial_archives_are_retained(self) -> None:
        rows = {
            row["document_id"]: row
            for row in _jsonl("geospatial-inventory.jsonl")
        }
        self.assertEqual(set(rows), {"164351", "164355", "164503"})
        self.assertEqual(
            {document: row["archive_member_count"] for document, row in rows.items()},
            {"164351": 19, "164355": 111, "164503": 2},
        )
        for row in rows.values():
            self.assertEqual(row["license"]["id"], "OGL-Canada")
            self.assertTrue(row["license"]["explicit_on_landing"])
            self.assertFalse(row["attachment_bodies_inspected"])
            self.assertFalse(row["nested_archives_extracted"])
            self.assertFalse(row["site_identity_resolved"])

    def test_request_inventory_is_exact_bounded_and_excludes_forbidden_documents(self) -> None:
        capture = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(capture["network_requests"], 11)
        self.assertEqual(capture["maximum_network_requests"], 20)
        self.assertEqual(capture["minimum_request_interval_seconds"], 1.0)
        urls = [row["url"] for row in capture["retrievals"].values()]
        self.assertIn(SEARCH_URL, urls)
        self.assertEqual(sum("/evaluations/proj/" in url for url in urls), 4)
        self.assertEqual(sum("/evaluations/document/" in url for url in urls), 3)
        self.assertEqual(sum(url.lower().endswith(".zip") for url in urls), 3)
        self.assertFalse(any(url.lower().endswith(".pdf") for url in urls))
        self.assertFalse(any("comments" in url.lower() for url in urls))
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )

    def test_rights_and_inference_boundaries_are_pinned(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        self.assertEqual(assessment["rights_assessment"], RIGHTS_POLICY)
        self.assertEqual(assessment["inference_policy"], INFERENCE_POLICY)
        self.assertFalse(RIGHTS_POLICY["project_and_search_html_publication_eligible"])
        self.assertTrue(RIGHTS_POLICY["geospatial_archives_publication_eligible"])
        self.assertTrue(
            RIGHTS_POLICY["commercial_redistribution_permission_required_unless_otherwise_specified"]
        )
        self.assertIsNone(INFERENCE_POLICY["annual_energy_mwh"])
        self.assertIsNone(INFERENCE_POLICY["pue"])
        self.assertIsNone(INFERENCE_POLICY["unique_physical_site_count"])

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        capture, raw = _capture_inputs()
        reproduced = derive_release_files(capture, raw)
        for filename, body in reproduced.items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), body)

    def test_raw_and_derived_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            search = copied / "raw/search.html"
            search.write_bytes(search.read_bytes() + b"\n")
            with self.assertRaises(IAACRegistryError):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            with self.assertRaises(IAACRegistryError):
                validate_release_bundle(copied)

    def test_frozen_modes_and_manifest_sidecar_are_exact(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertEqual(
                entry.stat().st_mode & 0o777,
                0o555 if entry.is_dir() else 0o444,
            )
        manifest = (PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()
        sidecar = (PINNED_RELEASE / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(sidecar, f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n")
        source_inventory = json.loads(
            (PINNED_RELEASE / "source-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            source_inventory["raw_inventory_sha256"],
            EXPECTED_RAW_INVENTORY_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
