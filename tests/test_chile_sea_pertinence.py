from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.chile_sea_pertinence import (
    ALLOWED_LISTING_FIELDS,
    ChileSEAPertinenceError,
    DETAIL_URL_TEMPLATE,
    EXPECTED_CURRENT_ANALYSIS_IDS,
    EXPECTED_HITS_BY_TERM,
    INFERENCE_POLICY,
    MANIFEST_FILENAME,
    QUERY_TERMS,
    RELEASE_ID,
    RIGHTS_POLICY,
    SEARCH_API_URL,
    canonical_json,
    derive_release_files,
    is_frozen_release,
    sanitize_search_response,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
EXPECTED_MANIFEST_SHA256 = (
    "d76f32818414478c0cc220a792e516b35fedae1f13cb1859c8940d86a2fd2a47"
)
EXPECTED_SNAPSHOT_SHA256 = (
    "4fd98d7999af8889ecc02192b77dca49eca9eb2703eb0283be0c2401e1044915"
)
EXPECTED_SEARCH_INVENTORY_SHA256 = (
    "9614e3a5f7585880b243cd42f001d5c081642593c8c8156075be9788036a3669"
)


def _jsonl(filename: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (PINNED_RELEASE / filename).read_text(encoding="utf-8").splitlines()
    ]


def _capture_inputs() -> tuple[dict[str, object], dict[str, bytes]]:
    capture = json.loads(
        (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
    )
    filenames = {
        capture["sanitized_snapshot_filename"],
        capture["retrievals"]["privacy"]["filename"],
        capture["retrievals"]["terms"]["filename"],
    }
    retained = {name: (PINNED_RELEASE / name).read_bytes() for name in filenames}
    return capture, retained


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


class ChileSEAPertinenceTests(unittest.TestCase):
    def test_pinned_release_validates_with_exact_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        selection = bundle["assessment"]["selection_assessment"]
        self.assertEqual(
            selection,
            {
                "query_hits_by_term": EXPECTED_HITS_BY_TERM,
                "raw_query_hits": 28,
                "review_candidate_rows": 23,
                "terminal_process_exclusion_rows": 5,
                "terminal_substatus_counts": {
                    "Resuelta - Abandono": 4,
                    "Resuelta - Desistida": 1,
                },
                "unique_qid_process_rows": 28,
            },
        )
        self.assertEqual(len(bundle["search_inventory"]), 28)
        self.assertIsNone(
            bundle["assessment"]["coverage_assessment"][
                "unique_physical_site_count"
            ]
        )

    def test_all_28_rows_have_explicit_closed_set_decisions(self) -> None:
        rows = _jsonl("search-inventory.jsonl")
        self.assertEqual([row["result_position"] for row in rows], list(range(1, 29)))
        self.assertEqual(len({row["qid_process"] for row in rows}), 28)
        self.assertEqual(
            Counter(row["classification"] for row in rows),
            Counter({"review_candidate": 23, "terminal_process_exclusion": 5}),
        )
        self.assertTrue(all(row["review_reason"] for row in rows))
        self.assertTrue(all(row["review_only"] for row in rows))
        self.assertTrue(all(row["unique_physical_site_id"] is None for row in rows))

    def test_terminal_substatuses_and_current_analysis_set_are_exact(self) -> None:
        rows = _jsonl("search-inventory.jsonl")
        terminal = [
            row for row in rows if row["classification"] == "terminal_process_exclusion"
        ]
        self.assertEqual(
            Counter(row["process_substatus_exact"] for row in terminal),
            Counter({"Resuelta - Abandono": 4, "Resuelta - Desistida": 1}),
        )
        analysis = {
            row["correlative_id"]
            for row in rows
            if row["process_state_exact"] == "En análisis"
        }
        self.assertEqual(analysis, EXPECTED_CURRENT_ANALYSIS_IDS)
        for row in rows:
            self.assertFalse(row["process_status_is_physical_lifecycle"])
            self.assertEqual(row["atlas_inference"], INFERENCE_POLICY)
            self.assertFalse(row["atlas_inference"]["construction_verified"])
            self.assertFalse(row["atlas_inference"]["operation_verified"])

    def test_query_order_counts_and_original_hashes_are_preserved(self) -> None:
        snapshot_path = PINNED_RELEASE / "sanitized-search-snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [query["query_term"] for query in snapshot["queries"]], list(QUERY_TERMS)
        )
        self.assertEqual(
            {query["query_term"]: len(query["rows"]) for query in snapshot["queries"]},
            EXPECTED_HITS_BY_TERM,
        )
        self.assertEqual(sha256_bytes(snapshot_path.read_bytes()), EXPECTED_SNAPSHOT_SHA256)
        for query in snapshot["queries"]:
            self.assertIsInstance(query["original_response_bytes"], int)
            self.assertRegex(query["original_response_sha256"], r"^[0-9a-f]{64}$")

    def test_upstream_holder_field_is_removed_before_retention(self) -> None:
        snapshot_body = (PINNED_RELEASE / "sanitized-search-snapshot.json").read_bytes()
        for artifact in PINNED_RELEASE.rglob("*"):
            if not artifact.is_file():
                continue
            body = artifact.read_bytes()
            self.assertNotIn(b"titularName", body)
        snapshot = json.loads(snapshot_body)
        one_row = dict(snapshot["queries"][3]["rows"][0])
        one_row["titularName"] = "discard me"
        sanitized = sanitize_search_response(
            json.dumps([one_row], ensure_ascii=False).encode("utf-8"),
            term="centro de datos",
        )
        self.assertEqual(set(sanitized[0]), set(ALLOWED_LISTING_FIELDS))
        self.assertNotIn("titularName", sanitized[0])

    def test_original_search_bodies_and_forbidden_endpoints_are_absent(self) -> None:
        capture = json.loads(
            (PINNED_RELEASE / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(capture["network_requests"], 6)
        self.assertEqual(capture["successful_requests"], 6)
        self.assertEqual(capture["maximum_network_requests"], 10)
        self.assertEqual(capture["maximum_attempts_per_request"], 3)
        self.assertEqual(capture["minimum_request_interval_seconds"], 1.0)
        searches = [capture["retrievals"][f"search_{index}"] for index in range(1, 5)]
        self.assertTrue(all(row["method"] == "POST" for row in searches))
        self.assertTrue(all(row["url"] == SEARCH_API_URL for row in searches))
        self.assertTrue(all("filename" not in row for row in searches))
        self.assertTrue(all(row["headers"]["x-ratelimit-limit"] == "6000" for row in searches))
        urls = [row["url"] for row in capture["retrievals"].values()]
        self.assertFalse(any("obtener-pertinencia" in url for url in urls))
        self.assertFalse(any("document" in url.lower() for url in urls))
        self.assertFalse(any(url.lower().endswith((".pdf", ".zip")) for url in urls))
        self.assertIn("{correlative_id}", DETAIL_URL_TEMPLATE)

    def test_rights_and_inference_boundaries_are_pinned(self) -> None:
        assessment = validate_release_bundle(PINNED_RELEASE)["assessment"]
        self.assertEqual(assessment["rights_assessment"], RIGHTS_POLICY)
        self.assertEqual(assessment["inference_policy"], INFERENCE_POLICY)
        self.assertFalse(RIGHTS_POLICY["publication_eligible"])
        self.assertTrue(RIGHTS_POLICY["commercial_redistribution_permission_required"])
        self.assertTrue(RIGHTS_POLICY["written_permission_required_for_commercial_copying_or_reuse"])
        self.assertFalse(RIGHTS_POLICY["master_or_ledger_import_permitted"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        self.assertEqual(assessment["atlas_decision"]["status"], "restricted_official_source_audit_index_only")

    def test_offline_reproduction_matches_every_derived_file(self) -> None:
        capture, retained = _capture_inputs()
        reproduced = derive_release_files(capture, retained)
        for filename, body in reproduced.items():
            self.assertEqual((PINNED_RELEASE / filename).read_bytes(), body)

    def test_schema_and_tampering_fail_closed(self) -> None:
        with self.assertRaises(ChileSEAPertinenceError):
            sanitize_search_response(b"[{}]", term="centro de datos")
        with self.assertRaises(ChileSEAPertinenceError):
            sanitize_search_response(b"[]", term="data center")
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            snapshot = copied / "sanitized-search-snapshot.json"
            snapshot.write_bytes(snapshot.read_bytes() + b" ")
            with self.assertRaises(ChileSEAPertinenceError):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            with self.assertRaises(ChileSEAPertinenceError):
                validate_release_bundle(copied)

    def test_definition_manifest_hash_and_frozen_modes_are_exact(self) -> None:
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(PINNED_RELEASE.stat().st_mode & 0o777, 0o555)
        for entry in PINNED_RELEASE.rglob("*"):
            self.assertEqual(
                entry.stat().st_mode & 0o777,
                0o555 if entry.is_dir() else 0o444,
            )
        manifest = (PINNED_RELEASE / MANIFEST_FILENAME).read_bytes()
        self.assertEqual(sha256_bytes(manifest), EXPECTED_MANIFEST_SHA256)
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "search-inventory.jsonl").read_bytes()),
            EXPECTED_SEARCH_INVENTORY_SHA256,
        )
        sidecar = (PINNED_RELEASE / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(sidecar, f"{EXPECTED_MANIFEST_SHA256}  {MANIFEST_FILENAME}\n")


if __name__ == "__main__":
    unittest.main()
