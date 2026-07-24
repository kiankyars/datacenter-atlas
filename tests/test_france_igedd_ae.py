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
from unittest import mock
from urllib.error import URLError

from datacenter_atlas.france_igedd_ae import (
    ANNUAL_INDEX_URLS,
    ASSESSMENT_FORMAT,
    DERIVED_FILENAMES,
    DOCUMENTS,
    EXPECTED_ARCHIVE_MATCH_COUNTS,
    EXPECTED_ARCHIVE_MATCHES,
    EXPECTED_NETWORK_REQUESTS,
    EXPECTED_OBSERVATIONS_SHA256,
    EXPECTED_PLANNED_DATA_CENTRE_UNITS,
    EXPECTED_SUCCESSFUL_REQUESTS,
    EXPECTED_UNIQUE_PROJECT_SITES,
    FranceIGEDDAEError,
    LIFECYCLE_BOUNDARY,
    MANIFEST_FILENAME,
    MAX_NETWORK_REQUESTS,
    RELEASE_ID,
    RIGHTS_POLICY,
    TITLE_TERMS_EXACT,
    build_release_documents,
    canonical_json,
    curated_observations,
    is_frozen_release,
    parse_annual_index,
    sha256_bytes,
    sha256_file,
    source_definition,
    thaw_for_test,
    title_matches_exact_terms,
    validate_capture_state_hash,
    validate_release_bundle,
    verify_rights_page,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
EXPECTED_DEFINITION_SHA256 = (
    "1d8bc43fe7a1c9d4d88b87302c2fc292039e003f1b5e695c3fc898581ed12138"
)
EXPECTED_ANNUAL_INVENTORY_SHA256 = (
    "332ef69d90c0635389431ee9e5e015e6b7eb93eb1ce453d85854e305558c3d90"
)
EXPECTED_MANIFEST_SHA256 = (
    "aef3c9b21a07d436bd48eafc26fb67e9ea81dbbb827f76429f66e65708307e49"
)


def _load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FETCH_MODULE = _load_script("fetch_build_france_igedd_ae")
BoundedFetcher = _FETCH_MODULE.BoundedFetcher
validate_main = _load_script("validate_france_igedd_ae").main


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _mutable_copy(temporary: str) -> Path:
    copied = Path(temporary) / "release"
    shutil.copytree(PINNED_RELEASE, copied)
    thaw_for_test(copied)
    return copied


class FranceIGEDDAETests(unittest.TestCase):
    def test_pinned_release_validates_with_exact_scope_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["format"], ASSESSMENT_FORMAT)
        self.assertEqual(
            bundle["assessment"]["classification_counts"],
            {
                "ancillary_grid_connection_follow_up": 1,
                "direct_data_centre_project": 3,
            },
        )
        coverage = bundle["assessment"]["coverage_assessment"]
        self.assertEqual(
            coverage["planned_data_centre_units_in_direct_projects"],
            EXPECTED_PLANNED_DATA_CENTRE_UNITS,
        )
        self.assertEqual(
            coverage["unique_project_site_count"], EXPECTED_UNIQUE_PROJECT_SITES
        )
        self.assertTrue(coverage["archive_2009_2025_closed_scan_complete"])
        self.assertFalse(coverage["current_2026_origin_capture_complete"])
        self.assertFalse(coverage["france_complete"])
        self.assertFalse(coverage["regional_mrae_coverage_included"])

    def test_all_17_archive_pages_and_2026_anomaly_are_explicit(self) -> None:
        annual = validate_release_bundle(PINNED_RELEASE)["annual_index"]
        rows = annual["rows"]
        self.assertEqual([row["year"] for row in rows], list(range(2009, 2027)))
        self.assertEqual([row["http_status"] for row in rows[:17]], [200] * 17)
        self.assertEqual(rows[17]["http_status"], 404)
        self.assertEqual(rows[17]["matches"], [])
        self.assertEqual(annual["archive_closed_match_count"], 3)
        self.assertEqual(annual["archive_pages_fetched"], 17)
        self.assertFalse(annual["current_2026_origin_capture_complete"])
        self.assertEqual(
            {row["year"]: len(row["matches"]) for row in rows[:17]},
            EXPECTED_ARCHIVE_MATCH_COUNTS,
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "annual-index-inventory.json"),
            EXPECTED_ANNUAL_INVENTORY_SHA256,
        )

    def test_exact_multilingual_title_contract_is_not_fuzzy(self) -> None:
        for term in TITLE_TERMS_EXACT:
            self.assertTrue(title_matches_exact_terms(f"Projet {term} exemple"), term)
        for nonmatch in (
            "centre culturel de données ouvertes",
            "digital hub without the explicit facility term",
            "centre de traitement des données routières",
            "database center",
        ):
            self.assertFalse(title_matches_exact_terms(nonmatch), nonmatch)

        expected = EXPECTED_ARCHIVE_MATCHES[2021]
        body = (
            "<html><body><h1>Les avis rendus en 2021</h1>"
            f'<a href="{expected["url"]}">{expected["title"]} pdf - 1.2 Mio</a>'
            "</body></html>"
        ).encode()
        self.assertEqual(
            parse_annual_index(
                body,
                year=2021,
                source_url=ANNUAL_INDEX_URLS[2021],
            ),
            [expected],
        )
        unexpected = body.replace(
            b"</body>",
            b'<a href="https://www.igedd.developpement-durable.gouv.fr/IMG/pdf/x.pdf">'
            b"Another data center pdf - 1 Mio</a></body>",
        )
        with self.assertRaisesRegex(FranceIGEDDAEError, "match count"):
            parse_annual_index(
                unexpected,
                year=2021,
                source_url=ANNUAL_INDEX_URLS[2021],
            )

    def test_project_site_and_unit_multiplicity_are_not_conflated(self) -> None:
        rows = _jsonl(PINNED_RELEASE / "observations.jsonl")
        direct = [row for row in rows if row["classification"] == "direct_data_centre_project"]
        self.assertEqual(len(direct), 3)
        self.assertEqual(sum(row["data_centre_unit_count"] for row in direct), 6)
        self.assertEqual(len({row["project_group_id"] for row in direct}), 3)
        self.assertEqual(len({row["site_group_id"] for row in direct}), 3)
        self.assertEqual(
            {row["project_name"]: row["data_centre_unit_count"] for row in direct},
            {"Digital Les Ulis": 2, "Dugny Digital Hub": 3, "Digital MRS6": 1},
        )

        follow_up = next(
            row
            for row in rows
            if row["classification"] == "ancillary_grid_connection_follow_up"
        )
        self.assertEqual(follow_up["data_centre_unit_count"], 0)
        self.assertEqual(
            follow_up["related_direct_observation_id"], "fr-igedd-ae-2025-058"
        )
        self.assertEqual(follow_up["project_group_id"], "digital-mrs6")
        self.assertEqual(follow_up["physical_unique_site_count_contribution"], 0)

    def test_environmental_review_never_becomes_physical_lifecycle(self) -> None:
        rows = _jsonl(PINNED_RELEASE / "observations.jsonl")
        for row in rows:
            self.assertEqual(row["environmental_review"], LIFECYCLE_BOUNDARY)
            self.assertIsNone(row["environmental_review"]["atlas_lifecycle_status"])
            self.assertFalse(row["environmental_review"]["construction_verified"])
            self.assertFalse(row["environmental_review"]["operation_verified"])
            self.assertFalse(
                row["environmental_review"][
                    "environmental_opinion_is_development_consent"
                ]
            )

    def test_power_energy_and_pue_scopes_remain_typed(self) -> None:
        rows = {row["observation_id"]: row for row in curated_observations()}
        ulis = rows["fr-igedd-ae-2021-104"]
        self.assertIsNone(ulis["planned_annual_electricity_consumption"])
        self.assertEqual(
            [
                metric["value"]
                for metric in ulis["metrics"]
                if metric["metric_type"] == "it_power_capacity"
            ],
            [60, 36],
        )

        dugny = rows["fr-igedd-ae-2024-08"]
        full_load = next(
            metric
            for metric in dugny["metrics"]
            if metric["metric_type"]
            == "projected_full_load_annual_electricity_consumption"
        )
        self.assertEqual((full_load["value"], full_load["unit"]), (1930, "GWh/year"))
        self.assertIn("not measured", full_load["qualifier"])
        pue = next(metric for metric in dugny["metrics"] if metric["metric_type"] == "target_pue")
        self.assertEqual(pue["value"], 1.3)
        self.assertIn("not measured", pue["qualifier"])

        mrs6 = rows["fr-igedd-ae-2025-058"]
        self.assertEqual(
            mrs6["planned_annual_electricity_consumption"],
            {
                "qualifier": "source_reported_project_not_measured",
                "unit": "GWh/year",
                "value": 245,
            },
        )
        follow_up = rows["fr-igedd-ae-2026-33"]
        connection = follow_up["metrics"][0]
        self.assertEqual(connection["metric_type"], "requested_grid_connection_power")
        self.assertEqual((connection["value"], connection["unit"]), (80, "MW"))
        self.assertIn("not IT capacity", connection["qualifier"])

        for row in rows.values():
            for metric in row["metrics"]:
                if metric["metric_type"].startswith("backup_"):
                    self.assertIn("never mapped", metric["qualifier"])

    def test_rights_allow_derived_facts_but_pdf_files_are_excluded(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        self.assertEqual(bundle["assessment"]["rights_assessment"], RIGHTS_POLICY)
        self.assertTrue(RIGHTS_POLICY["derived_factual_rows_publication_eligible"])
        self.assertFalse(RIGHTS_POLICY["document_redistribution_in_release"])
        self.assertFalse(RIGHTS_POLICY["raw_html_or_pdf_released"])
        self.assertFalse(RIGHTS_POLICY["legal_conclusion_claimed"])
        self.assertTrue(
            all(
                document["pdf_released"] is False
                for document in bundle["source_inventory"]["documents"]
            )
        )
        self.assertFalse(any(PINNED_RELEASE.rglob("*.pdf")))
        self.assertFalse(any(PINNED_RELEASE.rglob("*.html")))

        synthetic = """
        <p>Sauf mention explicite de propriété intellectuelle, les contenus de ce
        site sont proposés sous licence ouverte.</p>
        <p>La reproduction des documents doit respecter la gratuité de la diffusion ;
        le respect de l’intégrité des documents reproduits ; la citation explicite du
        site de l’IGEDD comme source et mention que les droits de reproduction sont
        réservés et strictement limités.</p>
        """.encode()
        self.assertTrue(all(verify_rights_page(synthetic).values()))
        with self.assertRaisesRegex(FranceIGEDDAEError, "rights language"):
            verify_rights_page(synthetic.replace(b"gratuit", b"payant"))

    def test_pdf_source_hashes_and_urls_are_exact_without_pdf_release(self) -> None:
        documents = validate_release_bundle(PINNED_RELEASE)["source_inventory"][
            "documents"
        ]
        self.assertEqual({row["document_id"] for row in documents}, set(DOCUMENTS))
        for row in documents:
            expected = DOCUMENTS[row["document_id"]]
            for field in ("bytes", "docket_number_exact", "pages", "sha256", "url"):
                self.assertEqual(row[field], expected[field])
            self.assertFalse(row["pdf_released"])

    def test_retrieval_is_bounded_paced_and_keeps_raw_only_in_quarantine(self) -> None:
        retrieval = validate_release_bundle(PINNED_RELEASE)["retrieval_inventory"]
        self.assertEqual(retrieval["network_attempt_count"], EXPECTED_NETWORK_REQUESTS)
        self.assertEqual(
            retrieval["successful_request_count"], EXPECTED_SUCCESSFUL_REQUESTS
        )
        self.assertEqual(retrieval["maximum_network_requests"], MAX_NETWORK_REQUESTS)
        self.assertGreaterEqual(retrieval["minimum_request_interval_seconds"], 1)
        self.assertEqual(retrieval["raw_artifacts_released"], 0)
        self.assertTrue(
            all(
                row["raw_artifact_retained_in_operator_quarantine"]
                for row in retrieval["retrievals"]
            )
        )
        self.assertEqual(
            Counter(row["http_status"] for row in retrieval["retrievals"]),
            Counter({200: 22, 404: 1}),
        )

    def test_fetcher_enforces_host_interval_cap_and_attempt_accounting(self) -> None:
        with self.assertRaisesRegex(FranceIGEDDAEError, "interval"):
            BoundedFetcher(
                timeout=1,
                minimum_interval=0,
                request_cap=1,
                maximum_attempts=1,
            )
        with self.assertRaisesRegex(FranceIGEDDAEError, "cap"):
            BoundedFetcher(
                timeout=1,
                minimum_interval=1,
                request_cap=MAX_NETWORK_REQUESTS + 1,
                maximum_attempts=1,
            )
        fetcher = BoundedFetcher(
            timeout=1,
            minimum_interval=1,
            request_cap=1,
            maximum_attempts=2,
        )
        with self.assertRaisesRegex(FranceIGEDDAEError, "official IGEDD host"):
            fetcher.fetch(
                request_id="outside",
                endpoint_kind="test",
                url="https://example.com/",
            )
        fetcher._opener = mock.Mock()
        fetcher._opener.open.side_effect = URLError("synthetic")
        with mock.patch.object(_FETCH_MODULE.time, "sleep"):
            with self.assertRaisesRegex(FranceIGEDDAEError, "cap reached"):
                fetcher.fetch(
                    request_id="failure",
                    endpoint_kind="test",
                    url=ANNUAL_INDEX_URLS[2009],
                )
        self.assertEqual(fetcher.network_attempts, 1)

    def test_capture_state_hash_binds_every_field(self) -> None:
        unhashed = {"format": "synthetic", "attempts": 23}
        capture = unhashed | {
            "capture_state_sha256": sha256_bytes(canonical_json(unhashed))
        }
        self.assertEqual(
            validate_capture_state_hash(capture), capture["capture_state_sha256"]
        )
        capture["attempts"] += 1
        with self.assertRaisesRegex(FranceIGEDDAEError, "hash mismatch"):
            validate_capture_state_hash(capture)

    def test_source_definition_and_frozen_hashes_are_exact(self) -> None:
        self.assertEqual(
            json.loads(SOURCE_DEFINITION.read_text(encoding="utf-8")),
            source_definition(),
        )
        self.assertEqual(sha256_file(SOURCE_DEFINITION), EXPECTED_DEFINITION_SHA256)
        self.assertEqual(
            sha256_file(PINNED_RELEASE / "observations.jsonl"),
            EXPECTED_OBSERVATIONS_SHA256,
        )
        self.assertEqual(
            sha256_file(PINNED_RELEASE / MANIFEST_FILENAME),
            EXPECTED_MANIFEST_SHA256,
        )
        self.assertTrue(is_frozen_release(PINNED_RELEASE))

    def test_release_rebuild_is_byte_identical_and_refuses_overwrite(self) -> None:
        documents = {
            name: (PINNED_RELEASE / name).read_bytes() for name in DERIVED_FILENAMES
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            write_release_bundle(output, documents)
            for child in PINNED_RELEASE.iterdir():
                self.assertEqual((output / child.name).read_bytes(), child.read_bytes())
            with self.assertRaisesRegex(FranceIGEDDAEError, "already exists"):
                write_release_bundle(output, documents)

    def test_validator_rejects_tamper_extra_files_and_writable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            assessment = copied / "assessment.json"
            assessment.write_bytes(assessment.read_bytes() + b" ")
            copied.chmod(0o555)
            for child in copied.iterdir():
                child.chmod(0o444)
            with self.assertRaises(FranceIGEDDAEError):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            (copied / "extra.txt").write_text("unexpected", encoding="utf-8")
            copied.chmod(0o555)
            for child in copied.iterdir():
                child.chmod(0o444)
            with self.assertRaisesRegex(FranceIGEDDAEError, "file set"):
                validate_release_bundle(copied)
        with tempfile.TemporaryDirectory() as temporary:
            copied = _mutable_copy(temporary)
            with self.assertRaisesRegex(FranceIGEDDAEError, "frozen"):
                validate_release_bundle(copied)

    def test_validator_cli_is_offline(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([str(PINNED_RELEASE)]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["archive_matches"], 3)
        self.assertFalse(payload["current_2026_origin_capture_complete"])
        self.assertEqual(payload["unique_project_sites"], 3)


if __name__ == "__main__":
    unittest.main()
