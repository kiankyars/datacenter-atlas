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
from zipfile import ZipFile

from datacenter_atlas.italy_mase_via_vas import (
    CLASSIFICATIONS,
    ItalyMASEVIAVASError,
    PORTAL_FOOTER,
    QUERY_SPECS,
    RELEASE_ID,
    canonical_json,
    classify_record,
    derive_release_files,
    export_url,
    is_frozen_release,
    parse_export_xlsx,
    parse_search_html,
    search_url,
    sha256_bytes,
    source_definition,
    thaw_for_test,
    validate_capture,
    validate_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_RELEASE = PROJECT_ROOT / "source_assessments" / RELEASE_ID
SOURCE_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
EXPECTED_CAPTURE_WINDOW = {
    "closed": True,
    "completed_at": "2026-07-19T02:55:09Z",
    "started_at": "2026-07-19T02:53:58Z",
}
EXPECTED_QUERY_COUNTS = {
    "q01": 68,
    "q02": 66,
    "q03": 14,
    "q04": 68,
    "q05": 19,
    "q06": 3,
    "q07": 0,
    "q08": 134,
    "q09": 134,
    "q10": 130,
    "q11": 64,
    "q12": 18,
    "q13": 17,
}
EXPECTED_ANCILLARY_TITLES = {
    (
        "DATACENTER EDIFICIO A e EDIFICIO B RHO/PERO (MILANO) - inserimento "
        "pozzi e edificio trattamento acque."
    ),
    (
        "Installazione di gruppi elettrogeni di emergenza di potenza "
        "complessiva pari a 132 MWt - datacenter in Comune di Segrate "
        "nell'area ex-CISE."
    ),
    (
        "Installazione di gruppi elettrogeni presso il data center Aruba sito "
        "nel comune di Roma, in località Tecnopolo Tiburtino."
    ),
    (
        "Progetto di installazione di n.22 generatori con energia termica "
        "complessiva pari a 143 MW, presso il data center MXP2 Vantage Data "
        "Centers Europe - sito di Settimo Milanese (MI)."
    ),
    (
        "Progetto di installazione di n.22 generatori di emergenza presso il "
        "data center MXP1 Vantage Data Centers Europe - sito di Melegnano (MI)."
    ),
}
EXPECTED_DEFINITION_SHA256 = (
    "869ed1429b1d2662d6d5f56e80a3864e3caed85dca2e20c6d75e2334ce8e7550"
)
EXPECTED_OBSERVATIONS_SHA256 = (
    "f044da5040c01d9a9870d7fa3751cf8de6bf20c319c96d2dce2265b12dc1ee0f"
)
EXPECTED_MANIFEST_SHA256 = (
    "876c75f3b8818dc1034a60f791ba8dbaaea9d5b94f704151302a3b82cca940af"
)


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


def _minimal_xlsx(rows: list[list[str]]) -> bytes:
    strings = [value for row in rows for value in row]
    shared_items = "".join(f"<si><t>{value}</t></si>" for value in strings)
    sheet_rows: list[str] = []
    offset = 0
    for number, row in enumerate(rows, start=1):
        cells = []
        for column, _value in zip("ABCD", row, strict=True):
            cells.append(
                f'<c r="{column}{number}" t="s"><v>{offset}</v></c>'
            )
            offset += 1
        sheet_rows.append(f'<row r="{number}">{"".join(cells)}</row>')
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            (
                '<sst xmlns="http://schemas.openxmlformats.org/'
                f'spreadsheetml/2006/main">{shared_items}</sst>'
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheetData>'
                f'{"".join(sheet_rows)}</sheetData></worksheet>'
            ),
        )
    return output.getvalue()


class ItalyMASEVIAVASTests(unittest.TestCase):
    def test_html_parser_extracts_exact_object_and_application_units(self) -> None:
        body = f"""
        <html><body>
          <h3 class="risultati">Risultati (1)</h3>
          <table class="table ElencoViaVasRicercaHome">
            <tr><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th><th>F</th><th>G</th></tr>
            <tr>
              <td>Progetto Data Center Test</td><td>Example S.r.l.</td>
              <td>Progetto</td><td>12345</td><td>Valutazione Impatto Ambientale</td>
              <td><a href="/it-IT/Oggetti/Info/100">info</a></td>
              <td><a href="/it-IT/Oggetti/Documentazione/100/200">docs</a></td>
            </tr>
          </table>
          <div>Pagina 1 di 1</div>
          <div>Il servizio è temporaneamente stato disabilitato</div>
          <footer>{PORTAL_FOOTER}</footer>
        </body></html>
        """.encode()
        parsed = parse_search_html(body)
        self.assertEqual((parsed["result_count"], parsed["page_count"]), (1, 1))
        self.assertTrue(parsed["footer_notice_present"])
        self.assertTrue(parsed["service_disabled_notice_present"])
        self.assertEqual(
            parsed["rows"][0]["source_record_key"], "100:200:12345"
        )
        self.assertEqual(parsed["rows"][0]["portal_object_id"], 100)
        self.assertEqual(parsed["rows"][0]["portal_documentation_id"], 200)

    def test_zero_result_portal_page_is_one_fetched_page(self) -> None:
        body = (
            '<h3 class="risultati">Risultati (0)</h3>'
            '<table class="ElencoViaVasRicercaHome"></table>'
            '<div>Pagina 1 di 0</div>'
            f'<footer>{PORTAL_FOOTER}</footer>'
        ).encode()
        parsed = parse_search_html(body)
        self.assertEqual(parsed["result_count"], 0)
        self.assertEqual(parsed["page_count"], 1)
        self.assertEqual(parsed["rows"], [])

    def test_xlsx_projection_collapses_source_whitespace(self) -> None:
        headers = [
            "Piano/Programma/Progetto/Installazione",
            "Proponente/Gestore",
            "Oggetto",
            "Ultima procedura",
        ]
        workbook = _minimal_xlsx(
            [
                headers,
                [
                    "Data  Center Test",
                    "Example S.r.l.",
                    "Progetto",
                    "Varianti  (Legge Obiettivo 443/2001)",
                ],
            ]
        )
        self.assertEqual(
            parse_export_xlsx(workbook),
            [
                [
                    "Data Center Test",
                    "Example S.r.l.",
                    "Progetto",
                    "Varianti (Legge Obiettivo 443/2001)",
                ]
            ],
        )

    def test_closed_query_plan_and_endpoint_encoding(self) -> None:
        self.assertEqual(len(QUERY_SPECS), 13)
        self.assertEqual(
            [row["query_id"] for row in QUERY_SPECS],
            [f"q{i:02d}" for i in range(1, 14)],
        )
        self.assertEqual(
            search_url("centro di elaborazione dati", page=2),
            (
                "https://va.mite.gov.it/it-IT/Ricerca/ViaVasAia?"
                "Testo=centro%20di%20elaborazione%20dati&pagina=2"
            ),
        )
        self.assertTrue(export_url("data center").endswith("&mode=export"))
        with self.assertRaisesRegex(ItalyMASEVIAVASError, "closed query plan"):
            search_url("cloud campus")

    def test_classification_contract_covers_all_four_outcomes(self) -> None:
        examples = {
            "direct_project": "Realizzazione Data Center MIL99",
            "ancillary_follow_up": (
                "Installazione di gruppi elettrogeni presso il data center Test"
            ),
            "context_only": "Elettrodotto per collegare il Data Center Test",
            "excluded": "Piano energetico regionale",
        }
        self.assertEqual(
            {classify_record({"title": title})[0] for title in examples.values()},
            set(CLASSIFICATIONS),
        )
        for expected, title in examples.items():
            self.assertEqual(classify_record({"title": title})[0], expected)

    def test_pinned_release_validates_with_exact_scope_arithmetic(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        assessment = bundle["assessment"]
        self.assertEqual(assessment["classification_counts"], {
            "ancillary_follow_up": 5,
            "context_only": 0,
            "direct_project": 38,
            "excluded": 143,
        })
        self.assertEqual(assessment["counts"]["raw_query_hits_by_query"], EXPECTED_QUERY_COUNTS)
        self.assertEqual(assessment["counts"]["raw_query_hits_total"], 735)
        self.assertEqual(assessment["counts"]["query_memberships"], 735)
        self.assertEqual(assessment["counts"]["exact_deduplicated_records"], 186)
        self.assertEqual(assessment["counts"]["exact_duplicates_removed"], 549)
        self.assertEqual(
            assessment["counts"]["object_kind_counts"],
            {"Installazione": 3, "Programma": 1, "Progetto": 182},
        )
        self.assertIsNone(assessment["counts"]["unique_physical_site_count"])
        self.assertEqual(bundle["capture"]["capture_window"], EXPECTED_CAPTURE_WINDOW)
        self.assertEqual(bundle["capture"]["network_attempt_count"], 93)
        self.assertEqual(
            assessment["atlas_decision"],
            {
                "assessment_artifact_indexing_permitted": True,
                "construction_map_import_permitted": False,
                "construction_master_import_permitted": False,
                "current_coverage_ledger_import_permitted": False,
                "reason": "portal-specific redistribution rights remain unclear",
                "status": "metadata_only_review_assessment",
            },
        )

    def test_every_exact_record_is_classified_and_ancillary_set_is_pinned(self) -> None:
        rows = _jsonl(PINNED_RELEASE / "observations.jsonl")
        self.assertEqual(len(rows), 186)
        self.assertEqual(
            {row["classification"] for row in rows},
            set(CLASSIFICATIONS) - {"context_only"},
        )
        self.assertEqual(
            {
                row["object_unit"]["title"]
                for row in rows
                if row["classification"] == "ancillary_follow_up"
            },
            EXPECTED_ANCILLARY_TITLES,
        )
        self.assertEqual(
            sum(row["classification"] != "excluded" for row in rows), 43
        )

    def test_regulatory_units_never_become_physical_status_or_metrics(self) -> None:
        rows = _jsonl(PINNED_RELEASE / "observations.jsonl")
        for row in rows:
            self.assertIn("object_unit", row)
            self.assertIn("application_unit", row)
            self.assertEqual(row["publication_units"], [])
            self.assertEqual(row["decision_units"], [])
            self.assertFalse(row["lifecycle_contract"]["physical_lifecycle_inferred"])
            self.assertIsNone(row["lifecycle_contract"]["normalized_physical_status"])
            self.assertFalse(row["metric_contract"]["numeric_title_mentions_converted"])
            self.assertIsNone(row["metric_contract"]["gross_facility_power_mw"])
            self.assertIsNone(row["metric_contract"]["annual_energy_mwh"])
            self.assertIsNone(row["metric_contract"]["it_capacity_mw"])
            self.assertIsNone(row["metric_contract"]["pue"])
            self.assertIsNone(row["unique_physical_site_id"])
            self.assertTrue(row["review_only"])

    def test_rights_and_retention_are_metadata_only(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        definition = source_definition()
        self.assertEqual(
            definition["rights"]["portal_footer_notice"], PORTAL_FOOTER
        )
        self.assertFalse(
            definition["rights"]["raw_response_redistribution_permitted"]
        )
        self.assertFalse(definition["rights"]["legal_conclusion_claimed"])
        self.assertEqual(
            definition["rights"]["retention_decision"],
            "derived_metadata_and_response_hashes_only",
        )
        self.assertFalse(bundle["capture"]["raw_response_bodies_retained"])
        requests = [bundle["capture"]["rights_evidence"]["sitemap_request"]]
        for query in bundle["capture"]["queries"]:
            requests.extend(query["html_requests"])
            requests.append(query["export_request"])
        self.assertEqual(len(requests), 93)
        self.assertTrue(all(request["body_retained"] is False for request in requests))
        self.assertFalse(
            any(
                path.suffix in {".html", ".xlsx", ".pdf"}
                for path in PINNED_RELEASE.iterdir()
            )
        )

    def test_capture_reproduces_all_payloads_offline(self) -> None:
        bundle = validate_release_bundle(PINNED_RELEASE)
        payloads = derive_release_files(bundle["capture"])
        for name, body in payloads.items():
            self.assertEqual((PINNED_RELEASE / name).read_bytes(), body)
        self.assertEqual(
            SOURCE_DEFINITION.read_bytes(), canonical_json(source_definition())
        )
        self.assertEqual(
            (PINNED_RELEASE / "definition.json").read_bytes(),
            SOURCE_DEFINITION.read_bytes(),
        )

    def test_frozen_modes_and_checkpoints_are_pinned(self) -> None:
        self.assertTrue(is_frozen_release(PINNED_RELEASE))
        self.assertEqual(
            sha256_bytes(SOURCE_DEFINITION.read_bytes()),
            EXPECTED_DEFINITION_SHA256,
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "observations.jsonl").read_bytes()),
            EXPECTED_OBSERVATIONS_SHA256,
        )
        self.assertEqual(
            sha256_bytes((PINNED_RELEASE / "manifest.json").read_bytes()),
            EXPECTED_MANIFEST_SHA256,
        )

    def test_capture_tampering_fails_closed(self) -> None:
        capture = validate_release_bundle(PINNED_RELEASE)["capture"]
        tampered = json.loads(json.dumps(capture))
        tampered["queries"][0]["html_requests"][0]["url"] = (
            "https://va.mite.gov.it/it-IT/Home/Mappa"
        )
        with self.assertRaisesRegex(ItalyMASEVIAVASError, "HTML request"):
            validate_capture(tampered)

        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "release"
            shutil.copytree(PINNED_RELEASE, copied)
            thaw_for_test(copied)
            observations = copied / "observations.jsonl"
            observations.write_bytes(observations.read_bytes() + b"\n")
            with self.assertRaisesRegex(ItalyMASEVIAVASError, "release output"):
                validate_release_bundle(copied)

    def test_offline_validator_and_repository_root_shim(self) -> None:
        validate_main = _load_script("validate_italy_mase_via_vas").main
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validate_main([str(PINNED_RELEASE)]), 0)
        summary = json.loads(output.getvalue())
        self.assertTrue(summary["frozen"])
        self.assertEqual(summary["counts"]["exact_deduplicated_records"], 186)

        command = (
            "from datacenter_atlas.italy_mase_via_vas import RELEASE_ID; "
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
