from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.spain_boe import (
    EXPECTED_CLASS_COUNTS,
    EXPECTED_CLOSED_ID_SHA256,
    EXPECTED_QUERY_COUNTS,
    MANIFEST_FILENAME,
    RELEASE_ID,
    SEARCH_TERMS,
    SpainBOEError,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    observations,
    search_url,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    validate_snapshot,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"


class SpainBOETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = validate_release_bundle(PINNED_RELEASE)
        cls.rows = observations(cls.bundle["snapshot"])

    def test_closed_query_and_classification_arithmetic_are_exact(self) -> None:
        summary = json.loads((PINNED_RELEASE / "query-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["closed_set_count"], 658)
        self.assertEqual(summary["closed_id_sha256"], EXPECTED_CLOSED_ID_SHA256)
        self.assertEqual(summary["query_counts_before_union"], EXPECTED_QUERY_COUNTS)
        self.assertEqual(summary["classification_counts"], EXPECTED_CLASS_COUNTS)
        self.assertEqual(summary["query_membership_multiplicity"], {"1": 641, "2": 15, "3": 2})

    def test_search_plan_is_closed_and_uses_selected_sections(self) -> None:
        definition = source_definition()
        self.assertEqual(tuple(definition["query"]["exact_terms"]), SEARCH_TERMS)
        self.assertEqual(definition["coverage"]["official_sections_included"], ["I", "III", "V"])
        self.assertEqual(definition["coverage"]["official_sections_excluded"], ["II", "IV", "TC"])
        url = search_url("data center")
        self.assertIn("dato%5B3%5D=%22data+center%22", url)
        self.assertIn("dato%5B6%5D%5B0%5D=2016-01-01", url)
        with self.assertRaises(SpainBOEError):
            search_url("centro de computación")

    def test_publication_process_never_becomes_physical_lifecycle(self) -> None:
        self.assertTrue(all(row["physical_lifecycle_status"] is None for row in self.rows))
        self.assertTrue(all(row["unique_site_counted"] is False for row in self.rows))
        self.assertTrue(all(row["auto_merge"] is False for row in self.rows))
        self.assertTrue(all(row["publication_unit_preserved"] is True for row in self.rows))
        direct = [row for row in self.rows if row["classification"] == "direct_project_build_expansion_candidate"]
        self.assertEqual(len(direct), 19)
        self.assertTrue(all(row["process_status"] and row["project_units"] for row in direct))

    def test_facility_power_and_water_facts_are_typed_and_scoped(self) -> None:
        by_id = {row["boe_id"]: row for row in self.rows}
        ignis = by_id["BOE-B-2026-3291"]
        power = next(item for item in ignis["facility_metrics"] if item["metric"] == "facility_power_as_stated")
        self.assertEqual(power["value"], 181.62)
        self.assertEqual(power["unit"], "megawatt")
        self.assertIn("not IT power", power["scope"])
        amazon = by_id["BOE-B-2025-22920"]
        self.assertEqual({item["metric"] for item in amazon["facility_metrics"]}, {"water_flow", "water_volume"})
        self.assertTrue(all(row["it_power_mw"] is None for row in self.rows))
        self.assertTrue(all(row["annual_energy_mwh"] is None for row in self.rows))
        self.assertTrue(all(row["pue"] is None for row in self.rows))

    def test_multi_project_publications_preserve_project_units(self) -> None:
        by_id = {row["boe_id"]: row for row in self.rows}
        self.assertEqual(len(by_id["BOE-A-2022-8298"]["project_units"]), 2)
        self.assertEqual(len(by_id["BOE-A-2023-13746"]["project_units"]), 4)
        self.assertEqual(len(by_id["BOE-A-2026-5368"]["project_units"]), 2)

    def test_excluded_rows_are_metadata_minimal(self) -> None:
        excluded = [row for row in self.rows if row["classification"] == "excluded_non_build_or_non_datacentre"]
        self.assertEqual(len(excluded), 608)
        self.assertTrue(all(row["evidence_summary"] is None for row in excluded))
        self.assertTrue(all(row["process_status"] is None for row in excluded))
        self.assertTrue(all(not row["project_units"] for row in excluded))
        snapshot_text = (PINNED_RELEASE / "sanitized-search-snapshot.json").read_text(encoding="utf-8")
        self.assertNotIn('"title"', snapshot_text)

    def test_rights_and_retention_are_explicit(self) -> None:
        definition = source_definition()
        self.assertTrue(definition["rights"]["reuse_permitted"])
        self.assertTrue(definition["rights"]["personal_data_law_applies"])
        self.assertFalse(definition["retention"]["personal_or_contact_fields_retained"])
        self.assertFalse(definition["retention"]["raw_pdf_retained"])
        self.assertFalse(definition["retention"]["raw_detail_xml_retained"])
        self.assertEqual(json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")), definition)

    def test_retrieval_inventory_records_all_bounded_responses(self) -> None:
        inventory = self.bundle["inventory"]
        self.assertEqual(inventory["network_requests"], 429)
        self.assertEqual(inventory["maximum_network_requests"], 435)
        self.assertEqual(inventory["minimum_request_interval_seconds"], 0.75)
        self.assertEqual(len(inventory["responses"]), 429)
        self.assertTrue(all(row["body_retained"] is False for row in inventory["responses"] if row["kind"] != "support_policy"))

    def test_offline_derivation_matches_release(self) -> None:
        support = {path.name: path.read_bytes() for path in (PINNED_RELEASE / "support").iterdir() if path.is_file()}
        for name, expected in derive_release_files(self.bundle["snapshot"], self.bundle["inventory"], support).items():
            self.assertEqual((PINNED_RELEASE / name).read_bytes(), expected)

    def test_snapshot_tampering_fails_closed(self) -> None:
        tampered = deepcopy(self.bundle["snapshot"])
        tampered["rows"][0]["classification"] = "direct_project_build_expansion_candidate"
        with self.assertRaises(SpainBOEError):
            validate_snapshot(tampered)

    def test_frozen_modes_manifest_and_sidecar(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertEqual(entry.stat().st_mode & 0o777, 0o555 if entry.is_dir() else 0o444)
        manifest = (PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()
        self.assertEqual((PINNED_RELEASE / "manifest.sha256").read_text(encoding="utf-8"), f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n")

    def test_manifest_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            target = copied / "observations.csv"
            target.write_bytes(target.read_bytes() + b"\n")
            for entry in sorted(copied.rglob("*"), reverse=True):
                entry.chmod(0o555 if entry.is_dir() else 0o444)
            copied.chmod(0o555)
            with self.assertRaises(SpainBOEError):
                validate_release_bundle(copied)

    def test_external_definition_is_canonical(self) -> None:
        self.assertEqual(SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition()))


if __name__ == "__main__":
    unittest.main()
