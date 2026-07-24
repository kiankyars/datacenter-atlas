from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.germany_uvp_verbund import (
    GermanyUVPVerbundError,
    MANIFEST_FILENAME,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    SEARCH_TERMS,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    query_plan,
    search_url,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    validate_retrieval_inventory,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


def _mutable_copy(temporary: str) -> Path:
    destination = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, destination)
    thaw_for_test(destination)
    return destination


class GermanyUVPVerbundTests(unittest.TestCase):
    def test_pinned_restricted_bundle_validates_offline(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        coverage = assessment["coverage_assessment"]
        self.assertEqual(
            assessment["atlas_decision"]["status"],
            "rights_and_access_blocked_metadata_only",
        )
        self.assertTrue(
            assessment["atlas_decision"]["assessment_artifact_indexing_permitted"]
        )
        self.assertFalse(
            assessment["atlas_decision"]["construction_master_import_permitted"]
        )
        self.assertFalse(
            assessment["atlas_decision"][
                "current_coverage_ledger_import_permitted"
            ]
        )
        self.assertFalse(coverage["closed_query_completed"])
        self.assertIsNone(coverage["result_count"])
        self.assertIsNone(coverage["unique_physical_site_count"])

    def test_exact_four_term_plan_preserves_null_counts(self) -> None:
        plan = query_plan()
        self.assertEqual([row["search_term"] for row in plan["rows"]], list(SEARCH_TERMS))
        self.assertEqual(
            [row["exact_url"] for row in plan["rows"]],
            [
                "https://www.uvp-verbund.de/freitextsuche?q=Rechenzentrum",
                "https://www.uvp-verbund.de/freitextsuche?q=Rechenzentren",
                "https://www.uvp-verbund.de/freitextsuche?q=Datacenter",
                "https://www.uvp-verbund.de/freitextsuche?q=Data%20Center",
            ],
        )
        self.assertEqual(plan["rows"][0]["status"], "blocked_http_429")
        self.assertTrue(
            all(row["result_count"] is None for row in plan["rows"])
        )
        self.assertTrue(
            all(
                set(row["classification_counts"].values()) == {None}
                for row in plan["rows"]
            )
        )

    def test_search_url_rejects_terms_outside_closed_plan(self) -> None:
        with self.assertRaises(GermanyUVPVerbundError):
            search_url("Rechenzentrum Berlin")

    def test_controlled_retrieval_inventory_is_exact_and_bounded(self) -> None:
        validate_retrieval_inventory(PINNED_RETRIEVAL_INVENTORY)
        requests = PINNED_RETRIEVAL_INVENTORY["controlled_http_requests"]
        self.assertEqual(PINNED_RETRIEVAL_INVENTORY["network_requests"], 3)
        self.assertEqual(PINNED_RETRIEVAL_INVENTORY["maximum_network_requests"], 8)
        self.assertEqual(
            PINNED_RETRIEVAL_INVENTORY["minimum_request_interval_seconds"], 1.0
        )
        self.assertEqual([row["http_status"] for row in requests], [429, 429, 302])
        self.assertTrue(all(row["body_retained"] is False for row in requests))
        self.assertTrue(all(len(row["sha256"]) == 64 for row in requests))
        self.assertEqual(
            PINNED_RETRIEVAL_INVENTORY["pre_capture_note"]["count"], 1
        )

    def test_rights_and_retention_fail_closed(self) -> None:
        definition = source_definition()
        rights = definition["rights"]
        retention = definition["retention"]
        self.assertTrue(rights["prior_author_consent_required_by_portal_notice"])
        self.assertFalse(rights["commercial_reuse_permission_clear"])
        self.assertFalse(rights["source_content_publication_permitted"])
        self.assertFalse(rights["master_or_ledger_import_permitted"])
        self.assertTrue(all(value is False for value in retention.values()))
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")), definition
        )

    def test_no_rows_or_metrics_can_be_emitted(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        schema = bundle["schema"]
        self.assertEqual(schema["classification_rows"], [])
        self.assertEqual(schema["facility_lead_count"], 0)
        self.assertEqual(schema["metric_contract"]["numeric_statements_retained"], 0)
        self.assertIsNone(schema["metric_contract"]["it_capacity_mw"])
        self.assertIsNone(schema["metric_contract"]["gross_facility_power_mw"])
        self.assertIsNone(schema["metric_contract"]["annual_energy_mwh"])
        self.assertFalse(
            schema["lifecycle_contract"]["regulatory_status_is_physical_lifecycle"]
        )

    def test_offline_reproduction_matches_all_derived_files(self) -> None:
        inventory = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        for filename, expected in derive_release_files(inventory).items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), expected)

    def test_inventory_tampering_fails_closed(self) -> None:
        tampered = deepcopy(PINNED_RETRIEVAL_INVENTORY)
        tampered["controlled_http_requests"][0]["http_status"] = 200
        with self.assertRaisesRegex(GermanyUVPVerbundError, "differs"):
            validate_retrieval_inventory(tampered)

    def test_derived_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            with self.assertRaises(GermanyUVPVerbundError):
                validate_release_bundle(copied)

    def test_frozen_modes_manifest_and_sidecar_are_exact(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertEqual(
                entry.stat().st_mode & 0o777,
                0o555 if entry.is_dir() else 0o444,
            )
        manifest = (PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()
        self.assertEqual(
            (PINNED_RELEASE / "manifest.sha256").read_text(encoding="utf-8"),
            f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n",
        )

    def test_external_definition_is_canonical(self) -> None:
        self.assertEqual(SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition()))


if __name__ == "__main__":
    unittest.main()
