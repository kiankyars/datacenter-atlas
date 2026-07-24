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

from datacenter_atlas.singapore_bca_green_mark import (
    CAPTURE_FORMAT,
    DATASET_ID,
    DATASET_URL,
    DATASTORE_ENDPOINT,
    DOWNSTREAM_IMPORT_POLICY,
    EXPECTED_FIELDS,
    EXPECTED_FILES,
    EXPECTED_LEAD_IDS,
    EXPECTED_LOGICAL_REQUESTS,
    EXPECTED_MATCH_COUNTS,
    EXPECTED_TOTAL,
    EXPECTED_UNIQUE_REFERENCE_COUNT,
    LICENCE_URL,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    PAGE_COUNTS,
    PAGE_OFFSETS,
    PAGE_SIZE,
    PHYSICAL_LIFECYCLE_BOUNDARY,
    RELEASE_ID,
    RIGHTS_POLICY,
    SingaporeBCAGreenMarkError,
    build_release_documents_from_snapshot,
    canonical_json,
    canonical_line,
    checkpoint,
    data_centre_phrase_match,
    is_frozen_release,
    load_capture,
    page_url,
    sha256_bytes,
    sha256_file,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
    write_release_bundle,
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


validate_main = _load_script("validate_singapore_bca_green_mark").main


def _minimal_evidence_body(kind: str) -> bytes:
    if kind == "dataset-metadata":
        return (
            f"{DATASET_ID} Green Mark Buildings Jan 2005 to Feb 2026 19 May 2026 "
            "Listing is based on voluntary Green Mark certification, excluding "
            "legislated projects and projects that have opted out of public "
            "disclosure. Building and Construction Authority"
        ).encode()
    return (
        "Singapore Open Data Licence version 1.0. You can use, access, download, "
        "copy, distribute, transmit, modify and adapt the datasets, whether "
        "commercially or non-commercially. any personal data in the dataset; "
        "third party rights that the Agency is not authorised to license; "
        "patents, trademarks and design rights. conspicuous notice acknowledging "
        "the source of the datasets"
    ).encode()


def _make_synthetic_capture(destination: Path) -> None:
    bundle = validate_release_bundle(PINNED_RELEASE)
    snapshot = bundle["snapshot"]
    raw = destination / "raw"
    raw.mkdir(parents=True)
    requests: list[dict[str, object]] = []
    plan: list[tuple[str, str, bytes, str]] = []
    fields = [{"id": field, "type": kind} for field, kind in EXPECTED_FIELDS]
    for offset, count in zip(PAGE_OFFSETS, PAGE_COUNTS, strict=True):
        body = canonical_json(
            {
                "result": {
                    "fields": fields,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "records": snapshot[offset : offset + count],
                    "resource_id": DATASET_ID,
                    "total": EXPECTED_TOTAL,
                },
                "success": True,
            }
        )
        plan.append((f"page-{offset}", page_url(offset), body, "application/json"))
    plan.extend(
        [
            (
                "dataset-metadata",
                DATASET_URL,
                _minimal_evidence_body("dataset-metadata"),
                "text/html; charset=utf-8",
            ),
            (
                "open-data-licence",
                LICENCE_URL,
                _minimal_evidence_body("open-data-licence"),
                "text/html; charset=utf-8",
            ),
        ]
    )
    for request_id, url, body, content_type in plan:
        body_file = f"raw/{request_id}.bin"
        (destination / body_file).write_bytes(body)
        requests.append(
            {
                "body_file": body_file,
                "bytes": len(body),
                "content_type": content_type,
                "finished_at": "2026-07-19T04:28:50Z",
                "http_request_count": 1,
                "redirect_count": 0,
                "request_id": request_id,
                "sha256": sha256_bytes(body),
                "started_at": "2026-07-19T04:28:50Z",
                "status": 200,
                "url": url,
            }
        )
    (destination / "capture.json").write_bytes(
        canonical_json(
            {
                "completed_logical_response_count": EXPECTED_LOGICAL_REQUESTS,
                "created_at": "2026-07-19T04:28:50Z",
                "format": CAPTURE_FORMAT,
                "http_request_count": EXPECTED_LOGICAL_REQUESTS,
                "http_requests_this_invocation": EXPECTED_LOGICAL_REQUESTS,
                "planned_logical_request_count": EXPECTED_LOGICAL_REQUESTS,
                "redirect_count": 0,
                "requests": requests,
                "resumed_body_count": 0,
            }
        )
    )


class SingaporeBCAGreenMarkTests(unittest.TestCase):
    def test_pinned_release_has_exact_complete_snapshot_arithmetic(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        assessment = bundle["assessment"]
        self.assertEqual(assessment["certification_observation_count"], 4793)
        self.assertEqual(len(bundle["snapshot"]), 4793)
        self.assertEqual(
            [row["_id"] for row in bundle["snapshot"]], list(range(1, 4794))
        )
        self.assertEqual(assessment["source_record_id_count"], 4793)
        self.assertEqual(
            assessment["reference_no_distinct_count"],
            EXPECTED_UNIQUE_REFERENCE_COUNT,
        )
        references = [row["Reference_No"] for row in bundle["snapshot"]]
        self.assertEqual(len(set(references)), 4786)
        self.assertGreater(max(Counter(references).values()), 1)
        self.assertIsNone(assessment["project_count"])
        self.assertIsNone(assessment["unique_site_count"])

    def test_closed_union_memberships_intersections_and_classes_are_exact(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        self.assertEqual(assessment["match_set_counts"], EXPECTED_MATCH_COUNTS)
        self.assertEqual(assessment["data_centre_match_union_count"], 101)
        self.assertEqual(len(bundle["observations"]), 101)
        self.assertEqual(len(bundle["memberships"]), 158)
        self.assertEqual(
            assessment["classification_counts"],
            {
                "additional_project_type_match": 2,
                "green_mark_data_centre_scheme": 94,
                "name_only_review": 5,
            },
        )
        self.assertEqual(
            assessment["intersection_counts"],
            {
                "all_three": 10,
                "project_type_and_name": 11,
                "scheme_and_name": 45,
                "scheme_and_project_type": 11,
            },
        )
        membership_counts = Counter(
            row["match_field_family"] for row in bundle["memberships"]
        )
        self.assertEqual(
            membership_counts, {"scheme": 94, "project_type": 13, "name": 51}
        )

    def test_phrase_predicate_has_closed_normalized_variants(self) -> None:
        for value in (
            "data centre",
            "DATA CENTER",
            "data-centres",
            "data-centers",
            "datacentre",
            "datacenters",
            "ＤＡＴＡ　ＣＥＮＴＲＥ",
            "New Data Centres (NDC: 2019)",
        ):
            self.assertTrue(data_centre_phrase_match(value), value)
        for value in (None, "database center", "DC", "server room", "cloud"):
            self.assertFalse(data_centre_phrase_match(value), value)
        definition = source_definition()
        self.assertEqual(
            definition["classification_contract"]["normalization"],
            ["NFKC", "casefold", "collapse_whitespace"],
        )

    def test_four_provisional_new_scheme_leads_are_exact_raw_certification_rows(self) -> None:
        leads = validate_release_bundle(PINNED_RELEASE)["leads"]
        self.assertEqual(
            [row["source_record_id"] for row in leads], list(EXPECTED_LEAD_IDS)
        )
        exact = {
            2: ("GM5107/1/2023", "JTC Jurong Island DC", None, None, "9/10/2025", "9/10/2028"),
            205: ("GM5530/1/2024", "LW-SIN10", "536213", "9706.06", "7/4/2025", "7/4/2028"),
            2439: ("GM5965/11/2024", "DayOne Data Centers SG1", "619478", "39860.75", "26/12/2025", "31/10/2029"),
            3908: ("GM5994/12/2024", "ST Engineering Data Centre at Boon Lay", "619523", "17165.24", "26/12/2025", "26/12/2028"),
        }
        for row in leads:
            self.assertEqual(
                (
                    row["reference_no"],
                    row["actual_project_name"],
                    row["postal_code_raw"],
                    row["gfa_raw"],
                    row["provisional_letter_date_raw"],
                    row["expiry_date_raw"],
                ),
                exact[row["source_record_id"]],
            )
            self.assertEqual(row["rating"], "Platinum")
            self.assertEqual(row["recertification_raw"], "No")
            self.assertIsNone(row["e_certificate_date_raw"])
            self.assertIsNone(row["gfa_unit"])

    def test_certification_fields_never_promote_physical_status_dates_or_metrics(self) -> None:
        observations = validate_release_bundle(PINNED_RELEASE)["observations"]
        for row in observations:
            self.assertEqual(row["physical_lifecycle"], PHYSICAL_LIFECYCLE_BOUNDARY)
            self.assertIsNone(row["project_count_contribution"])
            self.assertIsNone(row["unique_site_count_contribution"])
            self.assertIsNone(row["site_id"])
            self.assertIsNone(row["data_centre_type"])
            self.assertIsNone(row["operator"])
            self.assertIsNone(row["coordinates"])
            self.assertIsNone(row["power"])
            self.assertIsNone(row["it_capacity"])
            self.assertIsNone(row["pue"])
            self.assertIsNone(row["annual_energy_consumption"])
            self.assertIsNone(row["gfa_unit"])
        self.assertFalse(
            PHYSICAL_LIFECYCLE_BOUNDARY["provisional_letter_is_construction_evidence"]
        )
        self.assertFalse(
            PHYSICAL_LIFECYCLE_BOUNDARY["certification_dates_are_physical_dates"]
        )

    def test_voluntary_coverage_rights_pii_and_downstream_boundaries_are_exact(self) -> None:
        assessment = validate_release_bundle(PINNED_RELEASE)["assessment"]
        coverage = assessment["coverage"]
        self.assertEqual(coverage["coverage_start"], "2005-01")
        self.assertEqual(coverage["coverage_end"], "2026-02")
        self.assertEqual(coverage["dataset_last_updated"], "2026-05-19")
        self.assertTrue(coverage["voluntary_green_mark_listing_only"])
        self.assertTrue(coverage["legislated_projects_excluded"])
        self.assertTrue(coverage["opted_out_public_disclosure_projects_excluded"])
        self.assertFalse(coverage["national_data_centre_completeness_claimed"])
        self.assertEqual(assessment["rights_policy"], RIGHTS_POLICY)
        self.assertTrue(assessment["public_review_release_permitted"])
        self.assertFalse(RIGHTS_POLICY["raw_dataset_response_bodies_released"])
        self.assertTrue(RIGHTS_POLICY["source_dataset_snapshot_released"])
        self.assertEqual(assessment["downstream_import_policy"], DOWNSTREAM_IMPORT_POLICY)
        self.assertFalse(
            DOWNSTREAM_IMPORT_POLICY["automatic_construction_master_import_permitted"]
        )
        self.assertTrue(
            DOWNSTREAM_IMPORT_POLICY[
                "future_construction_master_tier_b_review_observation_import_permitted"
            ]
        )
        self.assertEqual(
            DOWNSTREAM_IMPORT_POLICY["future_master_requirements"]["tier"], "B"
        )
        self.assertTrue(
            DOWNSTREAM_IMPORT_POLICY["future_master_requirements"][
                "physical_lifecycle_status_must_be_null"
            ]
        )
        self.assertFalse(DOWNSTREAM_IMPORT_POLICY["construction_map_import_permitted"])
        self.assertTrue(DOWNSTREAM_IMPORT_POLICY["no_fuzzy_green_mark_geospatial_join"])
        scan = assessment["pii_and_schema_scan"]
        self.assertEqual(scan["email_pattern_match_count"], 0)
        self.assertEqual(scan["nric_fin_pattern_match_count"], 0)
        self.assertNotIn("nrci_fin_pattern_match_count", scan)
        self.assertEqual(scan["singapore_phone_pattern_match_count"], 0)
        self.assertEqual(scan["schema_person_or_contact_fields"], [])
        self.assertFalse(scan["personal_data_absence_claimed"])

    def test_retrieval_binds_five_exact_pages_metadata_licence_and_counters(self) -> None:
        retrieval = validate_release_bundle(PINNED_RELEASE)["retrieval"]
        self.assertEqual(retrieval["capture_logical_request_count"], 7)
        self.assertEqual(retrieval["capture_http_request_count"], 7)
        self.assertEqual(retrieval["capture_http_requests_this_invocation"], 7)
        self.assertEqual(retrieval["capture_redirect_count"], 0)
        self.assertEqual(retrieval["capture_resumed_body_count"], 0)
        self.assertEqual(retrieval["release_build_http_request_count"], 0)
        self.assertEqual(retrieval["offline_validation_http_request_count"], 0)
        responses = retrieval["network_responses"]
        self.assertEqual(
            [row["request_id"] for row in responses],
            [
                "page-0",
                "page-1000",
                "page-2000",
                "page-3000",
                "page-4000",
                "dataset-metadata",
                "open-data-licence",
            ],
        )
        pages = responses[:5]
        self.assertEqual([row["offset"] for row in pages], list(PAGE_OFFSETS))
        self.assertEqual([row["record_count"] for row in pages], list(PAGE_COUNTS))
        self.assertEqual({row["limit"] for row in pages}, {1000})
        self.assertEqual({row["api_total"] for row in pages}, {4793})
        self.assertEqual(len({row["field_schema_sha256"] for row in pages}), 1)
        self.assertEqual(sum(row["record_count"] for row in pages), 4793)
        self.assertEqual(responses[5]["url"], DATASET_URL)
        self.assertEqual(responses[6]["url"], LICENCE_URL)
        self.assertTrue(all(row["status"] == 200 for row in responses))
        self.assertTrue(all(row["http_request_count"] == 1 for row in responses))

    def test_release_reproduces_every_derived_byte_offline(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        reproduced = build_release_documents_from_snapshot(
            bundle["definition"], bundle["snapshot"], bundle["retrieval"]
        )
        for name, body in reproduced.items():
            self.assertEqual((PINNED_RELEASE / name).read_bytes(), body, name)

    def test_offline_validator_makes_zero_http_requests(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "offline_validate")
        self.assertEqual(payload["http_requests"], 0)
        self.assertEqual(payload["certification_observation_count"], 4793)
        self.assertEqual(payload["data_centre_match_union_count"], 101)
        self.assertEqual(payload["lead_count"], 4)

    def test_synthetic_capture_builds_atomically_and_freezes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture = root / "capture"
            _make_synthetic_capture(capture)
            loaded, bodies = load_capture(capture)
            self.assertEqual(loaded["http_request_count"], 7)
            self.assertEqual(len(bodies), 7)
            output = root / "release"
            write_release_bundle(SOURCE_DEFINITION, capture, output)
            self.assertTrue(is_frozen_release(output))
            bundle = validate_release_bundle(output, definition_path=SOURCE_DEFINITION)
            self.assertEqual(len(bundle["snapshot"]), 4793)
            self.assertEqual(len(bundle["observations"]), 101)
            with self.assertRaisesRegex(
                SingaporeBCAGreenMarkError, "refusing to overwrite output"
            ):
                write_release_bundle(SOURCE_DEFINITION, capture, output)

    def test_manifest_and_rebound_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            with self.assertRaisesRegex(SingaporeBCAGreenMarkError, "checkpoint"):
                validate_release_bundle(copied)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            observations_path = copied / "observations.jsonl"
            lines = observations_path.read_bytes().splitlines(keepends=True)
            first = json.loads(lines[0])
            first["exclusive_classification"] = "name_only_review"
            lines[0] = canonical_line(first)
            observations_path.write_bytes(b"".join(lines))
            manifest_path = copied / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["observations.jsonl"] = checkpoint(observations_path)
            manifest_body = canonical_json(manifest)
            manifest_path.write_bytes(manifest_body)
            (copied / MANIFEST_HASH_FILENAME).write_text(
                f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                SingaporeBCAGreenMarkError, "offline byte reproduction"
            ):
                validate_release_bundle(copied)

    def test_release_capture_and_definition_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release_link = root / "release-link"
            release_link.symlink_to(PINNED_RELEASE, target_is_directory=True)
            with self.assertRaisesRegex(SingaporeBCAGreenMarkError, "non-symlink"):
                validate_release_bundle(release_link)

            definition_link = root / "definition-link.json"
            definition_link.symlink_to(SOURCE_DEFINITION)
            with self.assertRaisesRegex(SingaporeBCAGreenMarkError, "non-symlink"):
                validate_release_bundle(PINNED_RELEASE, definition_path=definition_link)

            capture = root / "capture"
            _make_synthetic_capture(capture)
            target = root / "page-0-target.bin"
            original = capture / "raw" / "page-0.bin"
            original.rename(target)
            original.symlink_to(target)
            with self.assertRaisesRegex(SingaporeBCAGreenMarkError, "non-symlink"):
                load_capture(capture)

    def test_source_release_hashes_and_frozen_modes_are_pinned(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            {child.name for child in PINNED_RELEASE.iterdir()}, EXPECTED_FILES
        )
        self.assertEqual(
            sha256_file(SOURCE_DEFINITION),
            "b12ee571f2e62e170f436e4b65fa50784a9faa555c57608af55b8afe0313b0dd",
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "manifest.json"),
            "e5668ced3685e052208b14e4120f9045b60851f36f3012bda7e3d53f0beb63d3",
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "dataset-snapshot.jsonl"),
            "6474f62c01f0393d74263065306b2aaef5ba83f90bf30039886344b3b50fd123",
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "observations.jsonl"),
            "a3912f32e663c1076160f580c5eca4a61cb24fbbc53ffd2435b6cf1509dff6ac",
        )


if __name__ == "__main__":
    unittest.main()
