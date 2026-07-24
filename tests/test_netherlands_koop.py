from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.netherlands_koop import (
    ADVISORY_GROUPS,
    ARTIFACT_ORDER,
    CLASSIFICATION_CONTRACT,
    CONTEXT_CLASSIFICATION,
    DETAIL_IDENTIFIERS,
    DIRECT_CLASSIFICATION,
    EXPECTED_IDENTIFIERS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    RAW_PATHS,
    RELEASE_ID,
    REVIEW_POLICY,
    RIGHTS_POLICY,
    SRU_QUERY,
    NetherlandsKoopError,
    canonical_json,
    definition_from_capture,
    is_frozen_release,
    load_definition,
    sha256_bytes,
    thaw_for_test,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
EXPECTED_SRU_SHA256 = (
    "e4bd38159c1988d8ea8876b188d3c81ee519cb4581ac4e9b78f73e64e4483abb"
)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


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


class NetherlandsKoopTests(unittest.TestCase):
    def test_definition_is_canonical_and_matches_executable_contract(self) -> None:
        definition, raw = load_definition(SOURCE_DEFINITION)
        self.assertEqual(raw, canonical_json(definition, pretty=True))
        capture = {
            "artifacts": definition["raw_artifacts"],
            "request_log": definition["request_log"],
            "retrieval_policy": definition["retrieval_policy"],
            "retrieved_at": definition["retrieved_at"],
        }
        self.assertEqual(definition_from_capture(capture), definition)
        self.assertEqual(definition["query"]["query"], SRU_QUERY)
        self.assertTrue(definition["query"]["single_bounded_request"])
        self.assertEqual(definition["query"]["expected_number_of_records"], 20)

    def test_frozen_release_validates_with_exact_query_arithmetic(self) -> None:
        bundle = validate_release_bundle(
            PINNED_RELEASE, definition_path=SOURCE_DEFINITION
        )
        assessment = bundle["assessment"]
        inventory = bundle["inventory"]
        self.assertEqual(len(bundle["observations"]), 20)
        self.assertEqual(inventory["records"], 20)
        self.assertEqual(inventory["unique_identifiers"], 20)
        self.assertEqual(
            inventory["identifiers_in_sru_order"], list(EXPECTED_IDENTIFIERS)
        )
        self.assertEqual(
            assessment["classification_counts"],
            {
                CONTEXT_CLASSIFICATION: 7,
                DIRECT_CLASSIFICATION: 13,
            },
        )
        self.assertEqual(
            assessment["query_assessment"]["expected_result_count_precision"],
            "info:srw/vocabulary/resultCountPrecision/1/estimate",
        )
        self.assertTrue(
            assessment["query_assessment"]
            ["all_estimated_records_returned_in_one_request"]
        )
        sru = bundle["definition"]["raw_artifacts"]["sru_search"]
        self.assertEqual(sru["bytes"], 106_609)
        self.assertEqual(sru["sha256"], EXPECTED_SRU_SHA256)

    def test_every_record_preserves_original_and_enriched_metadata(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        observations = bundle["observations"]
        expected_manifestations = {
            "html",
            "metadata",
            "metadataowms",
            "odt",
            "pdf",
            "xml",
        }
        self.assertEqual(bundle["inventory"]["abstract_presence"], {"missing": 1, "present": 19})
        self.assertEqual(bundle["inventory"]["records_with_geometry"], 20)
        self.assertEqual(
            bundle["inventory"]["records_with_any_etrs89_location_point"], 16
        )
        for position, observation in enumerate(observations, 1):
            metadata = observation["metadata"]
            self.assertEqual(observation["source"]["record_position"], position)
            self.assertEqual(
                metadata["identifier"], EXPECTED_IDENTIFIERS[position - 1]
            )
            self.assertGreater(len(observation["original_metadata_leaf_elements"]), 20)
            self.assertEqual(len(observation["enriched_metadata_leaf_elements"]), 9)
            self.assertEqual(
                {item["manifestation"] for item in metadata["item_urls"]},
                expected_manifestations,
            )
            xml_url = next(
                item["url"]
                for item in metadata["item_urls"]
                if item["manifestation"] == "xml"
            )
            self.assertEqual(metadata["repository_url"], xml_url)
            self.assertRegex(observation["source"]["metadata_sha256"], r"^[0-9a-f]{64}$")
            for marker in metadata["geographic_markers"]:
                for point in marker["location_points"]:
                    self.assertEqual(point["crs"], "ETRS89")
                    self.assertEqual(point["source_order"], "latitude longitude")

        qts = next(
            row for row in observations if row["metadata"]["identifier"] == "prb-2026-11305"
        )
        self.assertIsNone(qts["metadata"]["abstract"])
        self.assertIsNotNone(qts["detail_evidence"])

        with (PINNED_RELEASE / "observations.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            csv_rows = list(csv.DictReader(source))
        self.assertEqual(len(csv_rows), 20)
        self.assertEqual(
            [row["identifier"] for row in csv_rows], list(EXPECTED_IDENTIFIERS)
        )

    def test_manual_classification_contract_covers_every_record_once(self) -> None:
        observations = validate_release_bundle(PINNED_RELEASE)["observations"]
        self.assertEqual(set(CLASSIFICATION_CONTRACT), set(EXPECTED_IDENTIFIERS))
        classified = {
            row["metadata"]["identifier"]: row["classification"]["label"]
            for row in observations
        }
        self.assertEqual(
            {
                identifier
                for identifier, label in classified.items()
                if label == CONTEXT_CLASSIFICATION
            },
            {
                "gmb-2026-162314",
                "gmb-2026-20613",
                "gmb-2026-299345",
                "gmb-2026-31793",
                "gmb-2026-334666",
                "gmb-2026-334667",
                "prb-2026-6693",
            },
        )
        self.assertEqual(Counter(classified.values()), Counter({DIRECT_CLASSIFICATION: 13, CONTEXT_CLASSIFICATION: 7}))
        for observation in observations:
            identifier = observation["metadata"]["identifier"]
            contract = CLASSIFICATION_CONTRACT[identifier]
            self.assertEqual(observation["classification"]["label"], contract["classification"])
            self.assertEqual(observation["permit_process"]["stage"], contract["process_stage"])
            self.assertEqual(
                observation["permit_process"]["stage_scope"],
                "official_publication_process_only",
            )

    def test_no_record_is_promoted_and_50_mw_remains_untyped_context(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        observations = bundle["observations"]
        self.assertEqual(bundle["assessment"]["untyped_context_statement_count"], 1)
        for observation in observations:
            self.assertTrue(observation["review_only"])
            self.assertFalse(observation["auto_merge"])
            self.assertFalse(observation["accepted_relationship"])
            self.assertFalse(observation["unique_site_counted"])
            self.assertEqual(
                observation["construction"],
                {"source_supported": False, "verified": False},
            )
            self.assertEqual(observation["promotion_boundaries"], REVIEW_POLICY)
            metrics = observation["facility_metrics"]
            for name in (
                "annual_energy_observations",
                "capacity_observations",
                "power_observations",
                "pue_observations",
                "workload_observations",
            ):
                self.assertEqual(metrics[name], [])

        am6 = next(
            row for row in observations if row["metadata"]["identifier"] == "prb-2026-6693"
        )
        self.assertEqual(am6["classification"]["label"], CONTEXT_CLASSIFICATION)
        self.assertEqual(
            am6["facility_metrics"]["untyped_context_statements"],
            [
                {
                    "metric_type": None,
                    "promoted_to_capacity_power_or_energy": False,
                    "reason": "Ancillary energy-generation threshold language is not data-centre facility power, IT capacity, or energy-consumption evidence.",
                    "text": "grootschalig opwekken energie (50 MW of meer) t.b.v. datacentrum Equinix AM6",
                    "unit": None,
                    "value": None,
                }
            ],
        )
        self.assertEqual(
            sum(
                len(row["facility_metrics"]["untyped_context_statements"])
                for row in observations
            ),
            1,
        )

    def test_advisory_relationships_never_merge_or_count_sites(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        relationships = bundle["relationships"]
        self.assertEqual(relationships["group_count"], 6)
        self.assertEqual(relationships["member_attachments"], 14)
        self.assertEqual(relationships["accepted_relationships"], 0)
        self.assertEqual(relationships["automatic_merges"], 0)
        self.assertIsNone(relationships["unique_physical_site_count"])
        self.assertEqual(
            {
                group["advisory_group_id"]: group["members"]
                for group in relationships["groups"]
            },
            {
                group["advisory_group_id"]: group["members"]
                for group in ADVISORY_GROUPS
            },
        )
        for group in relationships["groups"]:
            self.assertFalse(group["accepted"])
            self.assertFalse(group["automatic_merge"])
            self.assertFalse(group["identity_resolution_performed"])

    def test_rights_attachment_boundary_and_request_lineage_are_exact(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        rights = bundle["assessment"]["rights_assessment"]
        self.assertEqual(
            {key: rights[key] for key in RIGHTS_POLICY}, RIGHTS_POLICY
        )
        self.assertTrue(rights["rights_gate_passed_for_retained_scope"])
        self.assertEqual(rights["selected_detail_xml_count"], 8)
        self.assertFalse(rights["image_or_video_reuse_claimed"])
        self.assertFalse(rights["pdf_odt_and_other_publication_attachments_fetched"])
        self.assertFalse(rights["selected_details_contain_explicit_copyright_marker"])

        detail_files = sorted((PINNED_RELEASE / "raw/details").iterdir())
        self.assertEqual(len(detail_files), len(DETAIL_IDENTIFIERS))
        self.assertTrue(all(path.suffix == ".xml" for path in detail_files))
        self.assertEqual(
            [path for path in PINNED_RELEASE.rglob("*.pdf")],
            [PINNED_RELEASE / "raw/sru-guide.pdf"],
        )
        self.assertFalse(any(PINNED_RELEASE.rglob("*.odt")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.jpg")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.png")))

        request_log = _jsonl(PINNED_RELEASE / "request-log.jsonl")
        self.assertEqual(len(request_log), 12)
        self.assertEqual(
            [row["artifact_id"] for row in request_log], list(ARTIFACT_ORDER)
        )
        self.assertEqual(
            bundle["assessment"]["request_log"]["network_requests"], 12
        )
        self.assertEqual(
            bundle["assessment"]["request_log"]["validator_network_requests"], 0
        )
        for index, row in enumerate(request_log, 1):
            self.assertEqual(row["request_index"], index)
            self.assertEqual(row["attempt_count"], 1)
            self.assertEqual(row["retries_used"], 0)
            self.assertEqual(row["minimum_pacing_seconds"], 0.35)
            self.assertEqual(row["http_status"], 200)
            self.assertEqual(row["method"], "GET")

    def test_release_is_frozen_read_only(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))

    def test_offline_rebuild_reproduces_every_bundle_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rebuilt = write_release_bundle(
                SOURCE_DEFINITION,
                PINNED_RELEASE,
                Path(temporary) / "rebuilt",
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

    def test_raw_sru_tampering_fails_against_pinned_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            sru_path = copied / RAW_PATHS["sru_search"]
            sru_path.write_bytes(sru_path.read_bytes() + b"\n")
            _refresh_manifest_file(copied, RAW_PATHS["sru_search"])
            with self.assertRaisesRegex(
                NetherlandsKoopError, "captured artifact changed: sru_search"
            ):
                validate_release_bundle(copied, definition_path=SOURCE_DEFINITION)

    def test_observation_promotion_tampering_fails_offline_reproduction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            observations_path = copied / "observations.jsonl"
            observations = _jsonl(observations_path)
            observations[0]["construction"]["source_supported"] = True
            observations_path.write_bytes(
                b"".join(canonical_json(row) for row in observations)
            )
            _refresh_manifest_file(copied, "observations.jsonl")
            with self.assertRaisesRegex(
                NetherlandsKoopError,
                "offline reproduction mismatch: observations.jsonl",
            ):
                validate_release_bundle(copied, definition_path=SOURCE_DEFINITION)

    def test_existing_output_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(NetherlandsKoopError, "already exists"):
                write_release_bundle(
                    SOURCE_DEFINITION,
                    PINNED_RELEASE,
                    temporary,
                    freeze=False,
                )


if __name__ == "__main__":
    unittest.main()
