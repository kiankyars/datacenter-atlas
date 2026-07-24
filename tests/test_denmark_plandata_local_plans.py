from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from datacenter_atlas.denmark_plandata_local_plans import (
    CAPABILITIES_URL,
    EXPECTED_FILES,
    EXPECTED_SCHEMA_FIELD_COUNTS,
    EXPECTED_SCHEMA_SHA256,
    FEATURE_PROPERTIES,
    LAYER_SPECS,
    LICENSE_URI,
    MAX_CONTROLLED_REQUESTS,
    MAX_FEATURES,
    MAX_PAGES_PER_QUERY,
    MIN_REQUEST_INTERVAL_SECONDS,
    RELEASE_ID,
    SEARCH_LITERALS,
    DenmarkPlandataError,
    canonical_json,
    derive_observations,
    derive_release_files,
    feature_page_url,
    hits_url,
    is_frozen_release,
    parse_hits_xml,
    property_is_like_filter,
    query_plan,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_capture,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
EXPECTED_DEFINITION_SHA256 = (
    "4b2fe510da9fd301568cf066b507645c97ccebffd0746ffbf71ccc7071b4a97e"
)
EXPECTED_CAPTURE_SHA256 = (
    "5c45c8e2302fec5b58227411062e036647ead7c2e2853103638b4c82bde5d0e5"
)
EXPECTED_OBSERVATIONS_SHA256 = (
    "eabb29a585c014962114da0dd7877ffd6fca3a5ca1c39481dafedea613449799"
)
EXPECTED_MANIFEST_SHA256 = (
    "793f95d04afae18898280c54e8726cf9c5fdedef8d914c06764e5e186df78880"
)
EXPECTED_NAMES = {
    "Datacenter ved Sæby Varmeværk",
    "Datacenter og rekreativt område",
    "Erhvervsområde til datacentre",
    "Udvidelse af datacenter i Tietgenbyen",
    "Datacentre i Høje Taastrup",
}


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _request_sequence(capture: dict[str, object]) -> list[dict[str, object]]:
    control = capture["control"]
    assert isinstance(control, dict)
    requests = [
        control["licence_jsonld"]["request"],
        control["robots"]["request"],
        control["capabilities"]["request"],
        *(row["request"] for row in control["schemas"]),
    ]
    for layer in capture["layers"]:
        for query in layer["queries"]:
            requests.append(query["hits_request"])
            requests.extend(page["request"] for page in query["pages"])
    return requests


class DenmarkPlandataLocalPlanTests(unittest.TestCase):
    def test_closed_plan_is_exactly_three_by_nine(self) -> None:
        plan = query_plan()
        self.assertEqual(plan["query_count"], 27)
        self.assertEqual(len(plan["rows"]), 27)
        self.assertEqual(
            [(row["layer"], row["literal"]) for row in plan["rows"]],
            [
                (layer["layer"], literal)
                for layer in LAYER_SPECS
                for literal in SEARCH_LITERALS
            ],
        )
        self.assertEqual(
            [row["query_id"] for row in plan["rows"]],
            [f"q{index:02d}" for index in range(1, 28)],
        )

    def test_ogc_filter_and_urls_are_literal_and_bounded(self) -> None:
        xml = property_is_like_filter("data center")
        self.assertIn('matchCase="false"', xml)
        self.assertIn("<fes:ValueReference>plannavn</fes:ValueReference>", xml)
        self.assertIn("<fes:Literal>*data center*</fes:Literal>", xml)
        url = hits_url(LAYER_SPECS[0]["layer"], "data center")
        self.assertIn("resultType=hits", url)
        self.assertIn("PropertyIsLike", url)
        page = feature_page_url(
            LAYER_SPECS[0]["layer"], "data center", page=3
        )
        self.assertIn("count=100", page)
        self.assertIn("startIndex=200", page)
        self.assertIn("sortBy=id%20A", page)
        self.assertNotIn("megawatt", page)
        self.assertNotIn("maxbyg", page)
        with self.assertRaises(DenmarkPlandataError):
            property_is_like_filter("cloud campus")
        with self.assertRaises(DenmarkPlandataError):
            feature_page_url(LAYER_SPECS[0]["layer"], "datacenter", page=4)

    def test_hits_parser_accepts_counts_and_rejects_html(self) -> None:
        body = (
            b'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
            b'numberMatched="7" numberReturned="0" '
            b'timeStamp="2026-07-19T07:00:00Z"/>'
        )
        self.assertEqual(parse_hits_xml(body)["number_matched"], 7)
        with self.assertRaisesRegex(DenmarkPlandataError, "HTML"):
            parse_hits_xml(b"<html><body>error</body></html>")

    def test_pinned_capture_counts_and_positive_queries(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        capture = bundle["capture"]
        self.assertEqual(capture["controlled_request_count"], 35)
        self.assertEqual(capture["feature_rows_retrieved"], 5)
        positives = [
            (
                query["query_id"],
                query["literal"],
                query["hits"]["number_matched"],
                len(query["pages"]),
            )
            for layer in capture["layers"]
            for query in layer["queries"]
            if query["hits"]["number_matched"]
        ]
        self.assertEqual(
            positives,
            [("q10", "datacenter", 3, 1), ("q11", "datacentre", 2, 1)],
        )
        self.assertTrue(
            all(
                not query["truncated"] and query["complete"]
                for layer in capture["layers"]
                for query in layer["queries"]
            )
        )

    def test_control_evidence_is_exact_and_current_capture_is_paced(self) -> None:
        capture = validate_release_bundle(PINNED_RELEASE)["capture"]
        control = capture["control"]
        self.assertEqual(
            control["licence_jsonld"]["summary"]["licence_uri"], LICENSE_URI
        )
        self.assertEqual(
            control["licence_jsonld"]["summary"]["distribution_count"], 4
        )
        self.assertEqual(control["robots"]["request"]["http_status"], 404)
        self.assertFalse(control["robots"]["summary"]["robots_rule_published"])
        self.assertEqual(control["capabilities"]["request"]["url"], CAPABILITIES_URL)
        self.assertTrue(
            control["capabilities"]["summary"]["implements_result_paging"]
        )
        self.assertEqual(control["capabilities"]["summary"]["count_default"], 1_000_000)
        requests = _request_sequence(capture)
        self.assertEqual(len(requests), 35)
        self.assertTrue(all(row["redirect_count"] == 0 for row in requests))
        self.assertTrue(all(row["body_retained"] is False for row in requests))
        from datetime import datetime

        starts = [
            datetime.fromisoformat(row["requested_at"].replace("Z", "+00:00"))
            for row in requests
        ]
        self.assertTrue(
            all(
                (later - earlier).total_seconds() >= MIN_REQUEST_INTERVAL_SECONDS
                for earlier, later in zip(starts, starts[1:], strict=False)
            )
        )

    def test_all_three_schema_hashes_counts_and_semantic_fields_are_pinned(self) -> None:
        control = validate_release_bundle(PINNED_RELEASE)["capture"]["control"]
        for row, layer_spec in zip(control["schemas"], LAYER_SPECS, strict=True):
            layer = layer_spec["layer"]
            self.assertEqual(row["summary"]["raw_sha256"], EXPECTED_SCHEMA_SHA256[layer])
            self.assertEqual(
                row["summary"]["field_count"], EXPECTED_SCHEMA_FIELD_COUNTS[layer]
            )
            critical = row["summary"]["critical_fields"]
            self.assertEqual(critical["megawatt"]["type"], "xsd:decimal")
            self.assertEqual(critical["maxbygnhjd"]["type"], "xsd:decimal")
            self.assertEqual(critical["geometri"]["type"], "gml:MultiSurfacePropertyType")

    def test_five_observations_are_planning_units_not_atlas_facts(self) -> None:
        rows = _jsonl(PINNED_RELEASE / "observations.jsonl")
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["plan_name_raw"] for row in rows}, EXPECTED_NAMES)
        for row in rows:
            self.assertEqual(row["planning_status"], "adopted")
            self.assertEqual(row["planning_status_raw"], "V")
            self.assertFalse(row["planning_status_is_construction"])
            self.assertFalse(row["physical_lifecycle_inferred"])
            self.assertFalse(row["cancelled_planning_negative"])
            self.assertIsNone(row["atlas_identity"])
            self.assertIsNone(row["construction_status"])
            self.assertIsNone(row["operator"])
            self.assertIsNone(row["data_centre_type"])
            self.assertIsNone(row["gross_facility_power_mw"])
            self.assertIsNone(row["it_capacity_mw"])
            self.assertIsNone(row["pue"])
            self.assertIsNone(row["annual_energy_consumption_mwh"])
            self.assertIsNone(row["workload"])
            self.assertFalse(row["planning_maxima_captured"])
            self.assertFalse(row["planning_maxima_are_observed_actuals"])
            self.assertFalse(row["source_megawatt_captured"])
            self.assertFalse(row["source_megawatt_is_capacity_or_consumption"])
            self.assertIsNone(row["facility_coordinates"])
            self.assertIn(row["planning_area_geometry"]["type"], {"Polygon", "MultiPolygon"})

    def test_source_projection_omits_undefined_metrics_and_maxima(self) -> None:
        self.assertNotIn("megawatt", FEATURE_PROPERTIES)
        self.assertNotIn("maxetager", FEATURE_PROPERTIES)
        self.assertNotIn("maxbygnhjd", FEATURE_PROPERTIES)
        schema = json.loads((PINNED_RELEASE / "schema.json").read_text())
        self.assertFalse(schema["source_megawatt_and_planning_maxima_projected"])

    def test_no_documents_pdfs_or_downstream_import(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        capture = bundle["capture"]
        self.assertEqual(capture["document_requests"], 0)
        self.assertEqual(capture["pdf_requests"], 0)
        self.assertEqual(capture["detail_requests"], 0)
        decision = bundle["assessment"]["atlas_decision"]
        self.assertFalse(decision["construction_master_import_permitted"])
        self.assertFalse(decision["construction_map_import_permitted"])
        self.assertFalse(decision["current_coverage_ledger_import_permitted"])
        self.assertIsNone(bundle["assessment"]["counts"]["unique_physical_site_count"])
        self.assertFalse(bundle["assessment"]["coverage"]["complete_for_denmark"])
        self.assertFalse(
            bundle["assessment"]["coverage"][
                "national_data_centre_completeness_claimed"
            ]
        )

    def test_network_caps_leave_no_pressure_to_expand_first_pass(self) -> None:
        definition = source_definition()
        policy = definition["network_policy"]
        self.assertEqual(policy["maximum_controlled_requests"], MAX_CONTROLLED_REQUESTS)
        self.assertEqual(policy["maximum_features"], MAX_FEATURES)
        self.assertEqual(
            policy["maximum_pages_per_positive_query"], MAX_PAGES_PER_QUERY
        )
        self.assertEqual(policy["minimum_request_interval_seconds"], 5.0)
        self.assertEqual(policy["retry_attempts"], 0)
        capture = validate_release_bundle(PINNED_RELEASE)["capture"]
        self.assertLess(capture["controlled_request_count"], MAX_CONTROLLED_REQUESTS)
        self.assertLess(capture["feature_rows_retrieved"], MAX_FEATURES)

    def test_task_request_accounting_reconciles_every_derived_surface(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        accounting = bundle["assessment"]["task_request_accounting"]
        self.assertEqual(accounting["frozen_hash_bound_capture_gets"], 35)
        self.assertEqual(accounting["unfrozen_gets_not_coverage_evidence"], 32)
        self.assertEqual(accounting["direct_local_official_endpoint_gets_total"], 67)
        self.assertEqual(
            accounting["minimum_request_interval_applies_to"],
            "frozen_hash_bound_capture_only",
        )
        self.assertTrue(accounting["direct_local_total_below_predeclared_115_hard_cap"])
        self.assertEqual(accounting["aborted_capture_attempt"]["request_count"], 17)
        self.assertFalse(
            accounting["aborted_capture_attempt"]["artifact_or_coverage_evidence"]
        )
        source_inventory = json.loads(
            (PINNED_RELEASE / "source-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            source_inventory["task_direct_local_request_accounting"], accounting
        )
        readme = (PINNED_RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("35 + 32 = 67 direct local GETs", readme)
        self.assertIn("five-second interval applies", readme)

    def test_capture_reproduces_every_derived_byte(self) -> None:
        capture = validate_release_bundle(PINNED_RELEASE)["capture"]
        for name, body in derive_release_files(capture).items():
            self.assertEqual((PINNED_RELEASE / name).read_bytes(), body)
        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )

    def test_frozen_file_set_and_hashes_are_pinned(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual({entry.name for entry in PINNED_RELEASE.iterdir()}, EXPECTED_FILES)
        self.assertEqual(sha256_bytes(SOURCE_DEFINITION.read_bytes()), EXPECTED_DEFINITION_SHA256)
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "capture-metadata.json").read_bytes()),
            EXPECTED_CAPTURE_SHA256,
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "observations.jsonl").read_bytes()),
            EXPECTED_OBSERVATIONS_SHA256,
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes()),
            EXPECTED_MANIFEST_SHA256,
        )

    def test_tampering_fails_closed(self) -> None:
        capture = validate_release_bundle(PINNED_RELEASE)["capture"]
        tampered = json.loads(json.dumps(capture))
        tampered["layers"][1]["queries"][0]["hits"]["number_matched"] = 4
        with self.assertRaises(DenmarkPlandataError):
            validate_capture(tampered)
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            observations = copied / "observations.jsonl"
            observations.write_bytes(observations.read_bytes() + b"\n")
            with self.assertRaisesRegex(DenmarkPlandataError, "derived file"):
                validate_release_bundle(copied, require_frozen=False)

    def test_offline_validator_and_repository_root_shim(self) -> None:
        validate_main = _load_script("validate_denmark_plandata_local_plans").main
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([str(PINNED_RELEASE)]), 0)
        summary = json.loads(output.getvalue())
        self.assertTrue(summary["frozen"])
        self.assertEqual(summary["http_requests"], 0)
        self.assertEqual(summary["counts"]["exact_deduplicated_source_observations"], 5)
        command = (
            "from datacenter_atlas.denmark_plandata_local_plans import RELEASE_ID; "
            "print(RELEASE_ID)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=PROJECT_ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
            env={**dict(os.environ), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(completed.stdout.strip(), RELEASE_ID)


if __name__ == "__main__":
    unittest.main()
