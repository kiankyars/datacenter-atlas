from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.brazil_pncp_publications import (
    ANCILLARY_PUBLICATION_IDS,
    DIRECT_PUBLICATION_IDS,
    DOCUMENT_TYPES,
    DOWNSTREAM_IMPORT_POLICY,
    END_DATE,
    EXPECTED_FILES,
    LIFECYCLE_BOUNDARY,
    PAGE_SIZE,
    QUERY_TERMS,
    RELEASE_ID,
    RIGHTS_POLICY,
    START_DATE,
    BrazilPNCPError,
    is_frozen_release,
    query_url,
    sha256_file,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_main = _load_script("validate_brazil_pncp_publications").main


class BrazilPNCPPublicationTests(unittest.TestCase):
    def test_pinned_release_has_exact_bounded_arithmetic(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        assessment = bundle["assessment"]
        self.assertEqual(assessment["publication_count"], 6270)
        self.assertEqual(
            assessment["classification_counts"],
            {
                "ancillary_follow_up": 53,
                "context_only": 10,
                "direct_project": 28,
                "excluded": 6179,
            },
        )
        self.assertEqual(
            assessment["document_type_counts"],
            {"ata": 208, "contrato": 2090, "edital": 3969, "pcaorgao": 3},
        )
        coverage = assessment["coverage"]
        self.assertEqual(coverage["backend_query_memberships"], 6609)
        self.assertEqual(coverage["literal_phrase_publication_union_count"], 4847)
        self.assertEqual(coverage["date_min"], "2021-10-28")
        self.assertEqual(coverage["date_max"], "2026-07-17")
        self.assertEqual(coverage["pncp_index_hits_2016_2020"], 0)
        self.assertIsNone(coverage["project_count"])
        self.assertIsNone(coverage["site_count"])
        self.assertIsNone(assessment["procurement_entity_count"])
        self.assertIsNone(assessment["project_count"])
        self.assertIsNone(assessment["unique_site_count"])
        self.assertEqual(assessment["initial_notice_publication_count"], 3969)
        self.assertEqual(assessment["non_null_pncp_control_number_count"], 6267)

    def test_query_plan_is_closed_exact_and_below_ceiling(self) -> None:
        definition = source_definition()
        self.assertEqual(
            [row["phrase"] for row in definition["query_plan"]], list(QUERY_TERMS)
        )
        self.assertEqual(len(definition["query_plan"]), 5)
        for term, row in zip(QUERY_TERMS, definition["query_plan"], strict=True):
            self.assertEqual(row["api_url"], query_url(term))
            self.assertIn("tam_pagina=5000", row["api_url"])
            self.assertIn("anos=2016%7C2017", row["api_url"])
            self.assertTrue(row["local_literal_postfilter"])
        inventory = validate_release_bundle(PINNED_RELEASE)["assessment"][
            "query_inventory"
        ]
        self.assertEqual([row["api_total"] for row in inventory], [151, 151, 458, 2961, 2888])
        self.assertTrue(all(row["api_total"] < PAGE_SIZE for row in inventory))

    def test_publication_notice_contract_project_and_site_units_stay_separate(self) -> None:
        rows = validate_release_bundle(PINNED_RELEASE)["observations"]
        self.assertEqual(len(rows), len({row["publication_id"] for row in rows}))
        self.assertEqual({row["document_type"] for row in rows}, set(DOCUMENT_TYPES))
        self.assertEqual(sum(row["publication_count_contribution"] for row in rows), 6270)
        self.assertTrue(all(row["project_count_contribution"] is None for row in rows))
        self.assertTrue(all(row["unique_site_count_contribution"] is None for row in rows))
        self.assertTrue(all(row["project_id"] is None for row in rows))
        self.assertTrue(all(row["site_id"] is None for row in rows))
        self.assertTrue(all(row["procurement_entity_id"] is None for row in rows))
        self.assertTrue(
            all(row["procurement_entity_count_contribution"] is None for row in rows)
        )
        control_counts = Counter(
            row["pncp_control_number"]
            for row in rows
            if row["pncp_control_number"] is not None
        )
        self.assertEqual(len(control_counts), 6267)
        self.assertEqual(max(control_counts.values()), 1)

    def test_curated_facility_signals_are_explicit_not_generic_it(self) -> None:
        rows = {
            row["publication_id"]: row
            for row in validate_release_bundle(PINNED_RELEASE)["observations"]
        }
        self.assertEqual(
            {identifier for identifier, row in rows.items() if row["classification"] == "direct_project"},
            set(DIRECT_PUBLICATION_IDS),
        )
        self.assertEqual(
            {identifier for identifier, row in rows.items() if row["classification"] == "ancillary_follow_up"},
            set(ANCILLARY_PUBLICATION_IDS),
        )
        self.assertEqual(
            rows["2164baab500e56b1075fed1834977970"]["classification"],
            "excluded",
        )
        self.assertEqual(
            rows["3606b91e1292d235ed683e96c65c246f"]["classification"],
            "context_only",
        )
        self.assertEqual(
            rows["ce1fcb9b234ae18e3db67d6af4f9e780"]["document_type"],
            "contrato",
        )
        self.assertEqual(
            rows["ce1fcb9b234ae18e3db67d6af4f9e780"]["classification"],
            "ancillary_follow_up",
        )

    def test_no_procurement_wording_becomes_lifecycle_type_or_metric(self) -> None:
        rows = validate_release_bundle(PINNED_RELEASE)["observations"]
        for row in rows:
            self.assertEqual(row["atlas_lifecycle"], LIFECYCLE_BOUNDARY)
            self.assertIsNone(row["data_centre_type"])
            self.assertEqual(row["metrics"], [])
            self.assertEqual(row["license_count_contribution"], 0)
        assessment = validate_release_bundle(PINNED_RELEASE)["assessment"]
        self.assertEqual(assessment["metric_count"], 0)
        self.assertEqual(assessment["license_count"], 0)

    def test_rights_and_downstream_import_flags_fail_closed(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["rights_policy"], RIGHTS_POLICY)
        self.assertTrue(RIGHTS_POLICY["derived_factual_metadata_publication_eligible"])
        self.assertFalse(RIGHTS_POLICY["raw_api_bodies_released"])
        self.assertFalse(RIGHTS_POLICY["notice_description_redistribution_permitted"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        self.assertEqual(
            bundle["assessment"]["downstream_import_policy"],
            DOWNSTREAM_IMPORT_POLICY,
        )
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["construction_master_import_permitted"])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["construction_map_import_permitted"])
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["current_coverage_ledger_import_permitted"])
        observations = (PINNED_RELEASE / "observations.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"description":', observations)

    def test_definition_dates_and_dou_blind_spot_are_explicit(self) -> None:
        definition = source_definition()
        self.assertEqual(definition["coverage_contract"]["bounded_date_start"], START_DATE.isoformat())
        self.assertEqual(definition["coverage_contract"]["bounded_date_end"], END_DATE.isoformat())
        self.assertFalse(definition["coverage_contract"]["dou_automated_search_completed"])
        self.assertIn("robots.txt", definition["coverage_contract"]["dou_blocker"])
        self.assertFalse(definition["coverage_contract"]["national_completeness_claimed"])

    def test_manifest_detects_tampering_and_bundle_is_frozen(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            {child.name for child in PINNED_RELEASE.iterdir() if child.is_file()},
            EXPECTED_FILES,
        )
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            with self.assertRaisesRegex(BrazilPNCPError, "checkpoint"):
                validate_release_bundle(copied)

    def test_offline_validator_makes_zero_network_requests(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "offline_validate")
        self.assertEqual(payload["network_requests"], 0)
        self.assertEqual(payload["publication_count"], 6270)

    def test_source_and_release_hashes_are_pinned(self) -> None:
        # Exact values make accidental release regeneration visible in review.
        self.assertEqual(
            sha256_file(SOURCE_DEFINITION),
            "32c2ceb714bd07752122693479246b6d0d271dd8f277937d807b412fe23d50bf",
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "manifest.json"),
            "11ab602617c2187618951bfb59f54a81e9112248c0986bc45f047e40e51c35c3",
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "observations.jsonl"),
            "9a46bc5b064be95da16a1c947963b29d3ecaa8a96ea1f08362579a7ffeaaf892",
        )


if __name__ == "__main__":
    unittest.main()
