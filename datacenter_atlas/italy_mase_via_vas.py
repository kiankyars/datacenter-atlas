"""Bounded metadata-only assessment of Italy's MASE VIA/VAS portal.

The portal-specific footer states that all rights are reserved and exposes no
reuse licence. This module therefore retains derived search-result metadata and
response hashes only. It does not retain or redistribute HTML, XLSX, attached
documents, or other response bodies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import quote, urljoin, urlsplit
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


SCHEMA_VERSION = 1
RELEASE_ID = "italy-mase-via-vas-data-centre-search-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-italy-mase-via-vas-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-italy-mase-via-vas-definition-v1"
CAPTURE_FORMAT = "datacenter-atlas-italy-mase-via-vas-capture-metadata-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-italy-mase-via-vas-query-plan-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-italy-mase-via-vas-retrieval-inventory-v1"
OBSERVATION_FORMAT = "datacenter-atlas-italy-mase-via-vas-observation-v1"
MEMBERSHIP_FORMAT = "datacenter-atlas-italy-mase-via-vas-query-membership-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-italy-mase-via-vas-assessment-summary-v1"
SOURCE_INVENTORY_FORMAT = "datacenter-atlas-italy-mase-via-vas-source-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-italy-mase-via-vas-schema-v1"

PORTAL_ORIGIN = "https://va.mite.gov.it"
SEARCH_PATH = "/it-IT/Ricerca/ViaVasAia"
SEARCH_ENDPOINT = f"{PORTAL_ORIGIN}{SEARCH_PATH}"
SITEMAP_URL = f"{PORTAL_ORIGIN}/it-IT/Home/Mappa"
PORTAL_URL = f"{PORTAL_ORIGIN}/it-IT"
PORTAL_FOOTER = "Copyright M.A.T.T.M 2017. Tutti i diritti riservati"
EXPORT_CONTENT_DISPOSITION = "attachment; filename=Export.xlsx"
PAGE_SIZE = 10
MAX_PAGES_PER_QUERY = 50
MAX_NETWORK_REQUESTS = 120
MIN_REQUEST_INTERVAL_SECONDS = 0.2
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

QUERY_SPECS = (
    {"query_id": "q01", "phrase": "data center", "language": "common_english"},
    {"query_id": "q02", "phrase": "data centre", "language": "common_english"},
    {"query_id": "q03", "phrase": "datacenter", "language": "common_english"},
    {"query_id": "q04", "phrase": "data-center", "language": "common_english"},
    {"query_id": "q05", "phrase": "server farm", "language": "common_english"},
    {"query_id": "q06", "phrase": "server room", "language": "common_english"},
    {"query_id": "q07", "phrase": "computer room", "language": "common_english"},
    {
        "query_id": "q08",
        "phrase": "centro elaborazione dati",
        "language": "italian",
    },
    {
        "query_id": "q09",
        "phrase": "centro di elaborazione dati",
        "language": "italian",
    },
    {"query_id": "q10", "phrase": "centro dati", "language": "italian"},
    {"query_id": "q11", "phrase": "centro di calcolo", "language": "italian"},
    {"query_id": "q12", "phrase": "sala server", "language": "italian"},
    {"query_id": "q13", "phrase": "sale server", "language": "italian"},
)

CLASSIFICATIONS = (
    "direct_project",
    "ancillary_follow_up",
    "context_only",
    "excluded",
)

EXPECTED_FILES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "capture-metadata.json",
    "definition.json",
    "observations.jsonl",
    "query-membership.jsonl",
    "query-plan.json",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_INFO_RE = re.compile(r"^/it-IT/Oggetti/Info/(?P<object_id>[1-9][0-9]*)$")
_DOCUMENTATION_RE = re.compile(
    r"^/it-IT/Oggetti/Documentazione/(?P<object_id>[1-9][0-9]*)/"
    r"(?P<documentation_id>[1-9][0-9]*)$"
)
_DIRECT_PHRASE_RE = re.compile(
    r"(?<!\w)data[\s-]*cent(?:er|re)(?!\w)"
    r"|(?<!\w)datacenter(?!\w)"
    r"|centro(?:\s+di)?\s+elaborazione\s+dati"
    r"|server\s+farm",
    re.IGNORECASE,
)
_ANCILLARY_PREFIX_RE = re.compile(
    r"^(?:"
    r"datacenter edificio .*inserimento pozzi"
    r"|installazione di gruppi elettrogeni"
    r"|progetto di installazione di .*generatori"
    r")",
    re.IGNORECASE,
)
_CONTEXT_PREFIX_RE = re.compile(
    r"^(?:elettrodotto|metanodotto|gasdotto|acquedotto|collegamento)",
    re.IGNORECASE,
)


class ItalyMASEVIAVASError(ValueError):
    """Raised when the source capture or frozen assessment fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _checkpoint_bytes(body: bytes) -> dict[str, Any]:
    return {"bytes": len(body), "sha256": sha256_bytes(body)}


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ItalyMASEVIAVASError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ItalyMASEVIAVASError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ItalyMASEVIAVASError(f"{field} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise ItalyMASEVIAVASError(f"{field} must use canonical UTC whole seconds")
    return canonical


def _require_official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ItalyMASEVIAVASError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "va.mite.gov.it":
        raise ItalyMASEVIAVASError(f"{field} must use the official portal host")
    return value


def search_url(phrase: str, *, page: int = 1) -> str:
    if phrase not in {spec["phrase"] for spec in QUERY_SPECS}:
        raise ItalyMASEVIAVASError("phrase is outside the closed query plan")
    if not 1 <= page <= MAX_PAGES_PER_QUERY:
        raise ItalyMASEVIAVASError("page is outside the bounded query plan")
    url = f"{SEARCH_ENDPOINT}?Testo={quote(phrase, safe='')}"
    if page > 1:
        url += f"&pagina={page}"
    return url


def export_url(phrase: str) -> str:
    if phrase not in {spec["phrase"] for spec in QUERY_SPECS}:
        raise ItalyMASEVIAVASError("phrase is outside the closed query plan")
    return f"{SEARCH_ENDPOINT}?Testo={quote(phrase, safe='')}&mode=export"


def source_definition() -> dict[str, Any]:
    return {
        "coverage_contract": {
            "attached_document_full_text_searched": False,
            "current_recall_claimed": False,
            "global_recall_claimed": False,
            "national_recall_claimed": False,
            "portal_scope": (
                "MASE portal objects exposed by the combined VIA/VAS/AIA search; "
                "regional and local assessment portals are outside this release"
            ),
            "query_engine_match_semantics_documented": False,
            "unique_physical_site_count": None,
        },
        "endpoint_contract": {
            "export_content_disposition": EXPORT_CONTENT_DISPOSITION,
            "export_content_type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            "export_parameter": {"mode": "export"},
            "html_parameters": ["Testo", "pagina"],
            "method": "GET",
            "page_size_observed": PAGE_SIZE,
            "path": SEARCH_PATH,
            "search_parameter": "Testo",
            "sort": "portal default; no documented stable sort parameter",
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_mwh": None,
            "application_or_decision_is_physical_lifecycle": False,
            "automatic_promotion_permitted": False,
            "construction_status": None,
            "data_centre_type": None,
            "gross_facility_power_mw": None,
            "identity_merge_performed": False,
            "it_capacity_mw": None,
            "numeric_title_mentions_converted": False,
            "pue": None,
            "review_only": True,
            "unique_physical_site_count": None,
        },
        "network_policy": {
            "maximum_network_requests": MAX_NETWORK_REQUESTS,
            "maximum_pages_per_query": MAX_PAGES_PER_QUERY,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "maximum_attempts_per_request": 3,
            "retryable_http_statuses": [500, 502, 503, 504],
        },
        "publisher": (
            "Ministero dell'Ambiente e della Sicurezza Energetica, "
            "Direzione Generale Valutazioni Ambientali"
        ),
        "query_contract": {
            "classification_contract": {
                "ancillary_prefix_regex": _ANCILLARY_PREFIX_RE.pattern,
                "context_prefix_regex": _CONTEXT_PREFIX_RE.pattern,
                "direct_facility_phrase_regex": _DIRECT_PHRASE_RE.pattern,
                "evaluation_order": [
                    "excluded_when_no_direct_facility_phrase_in_title",
                    "ancillary_follow_up_when_ancillary_prefix_matches",
                    "context_only_when_context_prefix_matches",
                    "direct_project_otherwise",
                ],
                "input_field": "normalized portal result title only",
                "manual_overrides": [],
                "regex_case_insensitive": True,
            },
            "classification_values": list(CLASSIFICATIONS),
            "deduplication_key": [
                "portal_object_id",
                "portal_documentation_id",
                "latest_procedure_code",
            ],
            "phrases": [dict(spec) for spec in QUERY_SPECS],
            "predeclared_before_bounded_capture": True,
        },
        "release_id": RELEASE_ID,
        "retention": {
            "attached_documents_retained": False,
            "html_response_bodies_retained": False,
            "raw_response_redistribution_permitted": False,
            "third_party_material_retained": False,
            "xlsx_response_bodies_retained": False,
        },
        "rights": {
            "legal_conclusion_claimed": False,
            "portal_footer_notice": PORTAL_FOOTER,
            "portal_specific_open_licence_found": False,
            "raw_response_redistribution_permitted": False,
            "reason": (
                "The portal footer states that all rights are reserved and its "
                "sitemap exposes no portal-specific reuse licence."
            ),
            "retention_decision": "derived_metadata_and_response_hashes_only",
            "verified_local_date": "2026-07-18",
        },
        "schema_version": SCHEMA_VERSION,
        "source_id": "italy-mase-via-vas-data-centre-search",
        "source_urls": {
            "portal": PORTAL_URL,
            "search": SEARCH_ENDPOINT,
            "sitemap": SITEMAP_URL,
        },
        "unit_contract": {
            "application_unit": (
                "latest procedure code, label, and documentation-route ID shown "
                "on the search result"
            ),
            "decision_units_extracted": False,
            "exact_search_record_is_unique_site": False,
            "object_unit": "portal Piano/Programma/Progetto/Installazione object",
            "publication_units_extracted": False,
        },
    }


class _SearchHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_result_heading = False
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._heading_parts: list[str] = []
        self._page_parts: list[str] = []
        self._cell_parts: list[str] = []
        self._cell_links: list[str] = []
        self._row_cells: list[tuple[str, list[str]]] = []
        self.rows: list[dict[str, Any]] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        classes = self._classes(attrs)
        if tag == "h3" and "risultati" in classes:
            self._in_result_heading = True
        if tag == "table" and "ElencoViaVasRicercaHome" in classes:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._row_cells = []
        elif self._in_row and tag == "td":
            self._in_cell = True
            self._cell_parts = []
            self._cell_links = []
        elif self._in_cell and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._cell_links.append(href)

    def handle_data(self, data: str) -> None:
        self._page_parts.append(data)
        if self._in_result_heading:
            self._heading_parts.append(data)
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3" and self._in_result_heading:
            self._in_result_heading = False
        elif tag == "td" and self._in_cell:
            text = " ".join(" ".join(self._cell_parts).split())
            self._row_cells.append((text, list(self._cell_links)))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            self._consume_row()
            self._in_row = False
        elif tag == "table" and self._in_table:
            self._in_table = False

    def _consume_row(self) -> None:
        if not self._row_cells:
            return
        if len(self._row_cells) != 7:
            raise ItalyMASEVIAVASError("search-result table row width changed")
        values = [cell[0] for cell in self._row_cells]
        info_links = self._row_cells[5][1]
        document_links = self._row_cells[6][1]
        if len(info_links) != 1 or len(document_links) != 1:
            raise ItalyMASEVIAVASError("search-result row links changed")
        info_url = urljoin(PORTAL_ORIGIN, info_links[0])
        documentation_url = urljoin(PORTAL_ORIGIN, document_links[0])
        info_match = _OBJECT_INFO_RE.fullmatch(urlsplit(info_url).path)
        document_match = _DOCUMENTATION_RE.fullmatch(
            urlsplit(documentation_url).path
        )
        if (
            info_match is None
            or document_match is None
            or info_match.group("object_id")
            != document_match.group("object_id")
            or not values[0]
            or not values[2]
            or not values[3].isdigit()
            or not values[4]
        ):
            raise ItalyMASEVIAVASError("search-result row identity changed")
        object_id = int(info_match.group("object_id"))
        documentation_id = int(document_match.group("documentation_id"))
        procedure_code = values[3]
        self.rows.append(
            {
                "documentation_url": documentation_url,
                "info_url": info_url,
                "latest_procedure": values[4],
                "latest_procedure_code": procedure_code,
                "object_kind": values[2],
                "portal_documentation_id": documentation_id,
                "portal_object_id": object_id,
                "proponent": values[1] or None,
                "source_record_key": (
                    f"{object_id}:{documentation_id}:{procedure_code}"
                ),
                "title": values[0],
            }
        )

    def result(self) -> dict[str, Any]:
        heading = " ".join(" ".join(self._heading_parts).split())
        count_match = re.fullmatch(r"Risultati\s*\(([0-9]+)\)", heading)
        if count_match is None:
            raise ItalyMASEVIAVASError("search-result count heading changed")
        page_text = " ".join(" ".join(self._page_parts).split())
        page_match = re.search(r"Pagina\s+[0-9]+\s+di\s+([0-9]+)", page_text)
        result_count = int(count_match.group(1))
        reported_page_count = int(page_match.group(1)) if page_match else 1
        expected_page_count = max(1, math.ceil(result_count / PAGE_SIZE))
        if result_count == 0 and reported_page_count in {0, 1}:
            page_count = 1
        else:
            page_count = reported_page_count
        if page_count != expected_page_count:
            raise ItalyMASEVIAVASError("search pagination arithmetic changed")
        return {
            "footer_notice_present": PORTAL_FOOTER in page_text,
            "legal_or_licence_link_present": any(
                token in page_text.casefold()
                for token in ("note legali", "licenza", "licence", "license")
            ),
            "page_count": page_count,
            "result_count": result_count,
            "rows": self.rows,
            "service_disabled_notice_present": (
                "Il servizio è temporaneamente stato disabilitato" in page_text
            ),
        }


def parse_search_html(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ItalyMASEVIAVASError("search HTML must be UTF-8") from error
    parser = _SearchHTMLParser()
    try:
        parser.feed(text)
        parser.close()
    except ItalyMASEVIAVASError:
        raise
    except Exception as error:
        raise ItalyMASEVIAVASError("search HTML parsing failed") from error
    return parser.result()


_XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_EXPORT_HEADERS = (
    "Piano/Programma/Progetto/Installazione",
    "Proponente/Gestore",
    "Oggetto",
    "Ultima procedura",
)


def _column_number(cell_reference: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[1-9][0-9]*", cell_reference)
    if match is None:
        raise ItalyMASEVIAVASError("XLSX cell reference changed")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def parse_export_xlsx(body: bytes) -> list[list[str]]:
    try:
        with ZipFile(io.BytesIO(body)) as archive:
            names = set(archive.namelist())
            if not {
                "xl/sharedStrings.xml",
                "xl/worksheets/sheet1.xml",
            }.issubset(names):
                raise ItalyMASEVIAVASError("XLSX workbook members changed")
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(
                    node.text or "" for node in item.findall(".//x:t", _XLSX_NS)
                )
                for item in shared_root.findall("x:si", _XLSX_NS)
            ]
            sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (BadZipFile, ET.ParseError, KeyError, IndexError) as error:
        raise ItalyMASEVIAVASError("XLSX export is invalid") from error
    rows: list[list[str]] = []
    for row in sheet_root.findall(".//x:sheetData/x:row", _XLSX_NS):
        values = [""] * 4
        for cell in row.findall("x:c", _XLSX_NS):
            column = _column_number(cell.get("r", ""))
            if column >= 4:
                raise ItalyMASEVIAVASError("XLSX export column count changed")
            raw_value = cell.findtext("x:v", default="", namespaces=_XLSX_NS)
            if cell.get("t") != "s" or not raw_value.isdigit():
                raise ItalyMASEVIAVASError("XLSX export cell type changed")
            try:
                values[column] = " ".join(shared[int(raw_value)].split())
            except IndexError as error:
                raise ItalyMASEVIAVASError(
                    "XLSX shared-string reference changed"
                ) from error
        rows.append(values)
    if not rows or tuple(rows[0]) != _EXPORT_HEADERS:
        raise ItalyMASEVIAVASError("XLSX export headers changed")
    return rows[1:]


def classify_record(row: Mapping[str, Any]) -> tuple[str, str]:
    title = row.get("title")
    if not isinstance(title, str) or not title:
        raise ItalyMASEVIAVASError("classification requires a title")
    if _DIRECT_PHRASE_RE.search(title) is None:
        return "excluded", "no_predeclared_data_centre_phrase_in_result_title"
    if _ANCILLARY_PREFIX_RE.search(title):
        return "ancillary_follow_up", "title_primary_work_is_site_ancillary"
    if _CONTEXT_PREFIX_RE.search(title):
        return "context_only", "data_centre_appears_as_context_for_other_work"
    return "direct_project", "portal_object_title_directly_names_data_centre_work"


def _request_metadata_valid(record: Mapping[str, Any], field: str) -> None:
    required = {
        "body_retained",
        "bytes",
        "content_type",
        "http_status",
        "method",
        "request_id",
        "response_date",
        "sha256",
        "url",
    }
    if set(record) - (required | {"content_disposition"}) or not required.issubset(
        record
    ):
        raise ItalyMASEVIAVASError(f"{field} request metadata schema changed")
    _require_official_url(record.get("url"), f"{field}.url")
    _timestamp(record.get("response_date"), f"{field}.response_date")
    if (
        record.get("body_retained") is not False
        or record.get("http_status") != 200
        or record.get("method") != "GET"
        or isinstance(record.get("bytes"), bool)
        or not isinstance(record.get("bytes"), int)
        or record["bytes"] <= 0
        or not isinstance(record.get("request_id"), str)
        or not record["request_id"]
        or not isinstance(record.get("content_type"), str)
        or (
            "content_disposition" in record
            and (
                not isinstance(record["content_disposition"], str)
                or not record["content_disposition"]
            )
        )
        or not isinstance(record.get("sha256"), str)
        or _SHA256_RE.fullmatch(record["sha256"]) is None
    ):
        raise ItalyMASEVIAVASError(f"{field} request metadata is invalid")


def _validate_capture_row(row: Mapping[str, Any], query_id: str, rank: int) -> None:
    expected = {
        "documentation_url",
        "info_url",
        "latest_procedure",
        "latest_procedure_code",
        "object_kind",
        "portal_documentation_id",
        "portal_object_id",
        "proponent",
        "query_rank",
        "source_record_key",
        "title",
    }
    if set(row) != expected or row.get("query_rank") != rank:
        raise ItalyMASEVIAVASError(f"{query_id} row schema or rank changed")
    info = _require_official_url(row.get("info_url"), f"{query_id}.info_url")
    documentation = _require_official_url(
        row.get("documentation_url"), f"{query_id}.documentation_url"
    )
    info_match = _OBJECT_INFO_RE.fullmatch(urlsplit(info).path)
    document_match = _DOCUMENTATION_RE.fullmatch(urlsplit(documentation).path)
    object_id = row.get("portal_object_id")
    documentation_id = row.get("portal_documentation_id")
    procedure_code = row.get("latest_procedure_code")
    if (
        info_match is None
        or document_match is None
        or isinstance(object_id, bool)
        or not isinstance(object_id, int)
        or object_id <= 0
        or isinstance(documentation_id, bool)
        or not isinstance(documentation_id, int)
        or documentation_id <= 0
        or info_match.group("object_id") != str(object_id)
        or document_match.group("object_id") != str(object_id)
        or document_match.group("documentation_id") != str(documentation_id)
        or not isinstance(procedure_code, str)
        or not procedure_code.isdigit()
        or row.get("source_record_key")
        != f"{object_id}:{documentation_id}:{procedure_code}"
        or not isinstance(row.get("title"), str)
        or not row["title"]
        or not isinstance(row.get("object_kind"), str)
        or not row["object_kind"]
        or not isinstance(row.get("latest_procedure"), str)
        or not row["latest_procedure"]
        or (row.get("proponent") is not None and not isinstance(row["proponent"], str))
    ):
        raise ItalyMASEVIAVASError(f"{query_id} row identity changed")


def validate_capture(capture: Mapping[str, Any]) -> None:
    if set(capture) != {
        "capture_window",
        "format",
        "network_attempt_count",
        "queries",
        "raw_response_bodies_retained",
        "release_id",
        "rights_evidence",
        "schema_version",
        "source_endpoint",
    }:
        raise ItalyMASEVIAVASError("capture metadata schema changed")
    if (
        capture.get("format") != CAPTURE_FORMAT
        or capture.get("release_id") != RELEASE_ID
        or capture.get("schema_version") != SCHEMA_VERSION
        or capture.get("raw_response_bodies_retained") is not False
        or capture.get("source_endpoint") != SEARCH_ENDPOINT
        or isinstance(capture.get("network_attempt_count"), bool)
        or not isinstance(capture.get("network_attempt_count"), int)
    ):
        raise ItalyMASEVIAVASError("capture identity or retention changed")
    window = capture.get("capture_window")
    if not isinstance(window, Mapping) or set(window) != {
        "closed",
        "completed_at",
        "started_at",
    }:
        raise ItalyMASEVIAVASError("capture window schema changed")
    started = _timestamp(window.get("started_at"), "capture_window.started_at")
    completed = _timestamp(window.get("completed_at"), "capture_window.completed_at")
    if window.get("closed") is not True or started > completed:
        raise ItalyMASEVIAVASError("capture window is not closed")
    rights = capture.get("rights_evidence")
    if not isinstance(rights, Mapping) or set(rights) != {
        "footer_notice",
        "portal_specific_open_licence_found",
        "raw_redistribution_permitted",
        "sitemap_request",
    }:
        raise ItalyMASEVIAVASError("rights evidence schema changed")
    if (
        rights.get("footer_notice") != PORTAL_FOOTER
        or rights.get("portal_specific_open_licence_found") is not False
        or rights.get("raw_redistribution_permitted") is not False
        or not isinstance(rights.get("sitemap_request"), Mapping)
    ):
        raise ItalyMASEVIAVASError("rights decision changed")
    _request_metadata_valid(rights["sitemap_request"], "sitemap_request")
    if (
        rights["sitemap_request"]["request_id"] != "rights-sitemap"
        or rights["sitemap_request"]["url"] != SITEMAP_URL
        or rights["sitemap_request"]["content_type"] != "text/html"
    ):
        raise ItalyMASEVIAVASError("sitemap request contract changed")

    queries = capture.get("queries")
    if not isinstance(queries, list) or len(queries) != len(QUERY_SPECS):
        raise ItalyMASEVIAVASError("capture query count changed")
    request_ids: set[str] = {rights["sitemap_request"]["request_id"]}
    response_dates = [rights["sitemap_request"]["response_date"]]
    for query, spec in zip(queries, QUERY_SPECS, strict=True):
        if not isinstance(query, Mapping) or set(query) != {
            "export_projection_sha256",
            "export_request",
            "export_row_count",
            "html_page_count",
            "html_projection_sha256",
            "html_requests",
            "language",
            "phrase",
            "query_id",
            "result_count",
            "rows",
            "service_disabled_notice_present",
        }:
            raise ItalyMASEVIAVASError("capture query schema changed")
        query_id = spec["query_id"]
        if (
            query.get("query_id") != query_id
            or query.get("phrase") != spec["phrase"]
            or query.get("language") != spec["language"]
            or query.get("service_disabled_notice_present") is not True
            or isinstance(query.get("result_count"), bool)
            or not isinstance(query.get("result_count"), int)
            or query["result_count"] < 0
            or query.get("export_row_count") != query["result_count"]
            or query.get("html_page_count")
            != max(1, math.ceil(query["result_count"] / PAGE_SIZE))
            or not isinstance(query.get("rows"), list)
            or len(query["rows"]) != query["result_count"]
        ):
            raise ItalyMASEVIAVASError(f"{query_id} coverage changed")
        if not isinstance(query.get("html_requests"), list) or len(
            query["html_requests"]
        ) != query["html_page_count"]:
            raise ItalyMASEVIAVASError(f"{query_id} HTML request count changed")
        for page, request in enumerate(query["html_requests"], start=1):
            if (
                not isinstance(request, Mapping)
                or request.get("request_id") != f"{query_id}-html-{page:02d}"
                or request.get("url") != search_url(spec["phrase"], page=page)
            ):
                raise ItalyMASEVIAVASError(f"{query_id} HTML request changed")
        export_request = query.get("export_request")
        if (
            not isinstance(export_request, Mapping)
            or export_request.get("request_id") != f"{query_id}-export"
            or export_request.get("url") != export_url(spec["phrase"])
        ):
            raise ItalyMASEVIAVASError(f"{query_id} export request changed")
        for request in [*query["html_requests"], query.get("export_request")]:
            if not isinstance(request, Mapping):
                raise ItalyMASEVIAVASError(f"{query_id} request row changed")
            _request_metadata_valid(request, f"{query_id}.request")
            if request["request_id"] in request_ids:
                raise ItalyMASEVIAVASError("capture repeats a request ID")
            request_ids.add(request["request_id"])
            response_dates.append(request["response_date"])
        if any(
            request["content_type"] != "text/html"
            for request in query["html_requests"]
        ):
            raise ItalyMASEVIAVASError(f"{query_id} HTML content type changed")
        if query["export_request"]["content_type"] != source_definition()[
            "endpoint_contract"
        ]["export_content_type"]:
            raise ItalyMASEVIAVASError(f"{query_id} export content type changed")
        if (
            query["export_request"].get("content_disposition")
            != EXPORT_CONTENT_DISPOSITION
        ):
            raise ItalyMASEVIAVASError(
                f"{query_id} export content disposition changed"
            )
        keys: set[str] = set()
        for rank, row in enumerate(query["rows"], start=1):
            if not isinstance(row, Mapping):
                raise ItalyMASEVIAVASError(f"{query_id} row changed")
            _validate_capture_row(row, query_id, rank)
            if row["source_record_key"] in keys:
                raise ItalyMASEVIAVASError(f"{query_id} repeats an exact record")
            keys.add(row["source_record_key"])
        projection = [
            [
                row["title"],
                row["proponent"] or "",
                row["object_kind"],
                row["latest_procedure"],
            ]
            for row in query["rows"]
        ]
        projection_sha = sha256_bytes(canonical_json(projection))
        if (
            query.get("html_projection_sha256") != projection_sha
            or query.get("export_projection_sha256") != projection_sha
        ):
            raise ItalyMASEVIAVASError(f"{query_id} projections do not reconcile")
    if not len(request_ids) <= capture["network_attempt_count"] <= MAX_NETWORK_REQUESTS:
        raise ItalyMASEVIAVASError("capture exceeds the network request cap")
    if any(value < started or value > completed for value in response_dates):
        raise ItalyMASEVIAVASError("response date is outside the capture window")


def _deduplicate(capture: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact: dict[str, dict[str, Any]] = {}
    memberships: list[dict[str, Any]] = []
    matched_queries: dict[str, list[str]] = {}
    for query in capture["queries"]:
        query_id = query["query_id"]
        for row in query["rows"]:
            key = row["source_record_key"]
            projected = {name: value for name, value in row.items() if name != "query_rank"}
            if key in exact and exact[key] != projected:
                raise ItalyMASEVIAVASError("exact record fields differ across queries")
            exact[key] = projected
            matched_queries.setdefault(key, []).append(query_id)
            memberships.append(
                {
                    "format": MEMBERSHIP_FORMAT,
                    "query_id": query_id,
                    "query_rank": row["query_rank"],
                    "schema_version": SCHEMA_VERSION,
                    "source_record_key": key,
                }
            )
    observations: list[dict[str, Any]] = []
    for key, row in sorted(
        exact.items(),
        key=lambda item: (
            item[1]["portal_object_id"],
            item[1]["portal_documentation_id"],
            int(item[1]["latest_procedure_code"]),
        ),
    ):
        classification, reason = classify_record(row)
        observations.append(
            {
                "application_unit": {
                    "documentation_url": row["documentation_url"],
                    "latest_procedure_code": row["latest_procedure_code"],
                    "latest_procedure_label": row["latest_procedure"],
                    "portal_documentation_id": row["portal_documentation_id"],
                },
                "classification": classification,
                "classification_reason": reason,
                "decision_units": [],
                "format": OBSERVATION_FORMAT,
                "lifecycle_contract": {
                    "normalized_physical_status": None,
                    "physical_lifecycle_inferred": False,
                    "source_regulatory_label": row["latest_procedure"],
                },
                "matched_query_ids": matched_queries[key],
                "metric_contract": {
                    "annual_energy_mwh": None,
                    "gross_facility_power_mw": None,
                    "it_capacity_mw": None,
                    "numeric_title_mentions_converted": False,
                    "pue": None,
                },
                "object_unit": {
                    "info_url": row["info_url"],
                    "object_kind": row["object_kind"],
                    "portal_object_id": row["portal_object_id"],
                    "proponent": row["proponent"],
                    "title": row["title"],
                },
                "publication_units": [],
                "record_id": f"mase-via-vas:{key}",
                "review_only": True,
                "schema_version": SCHEMA_VERSION,
                "source_record_key": key,
                "unique_physical_site_id": None,
            }
        )
    return observations, memberships


def _query_plan(capture: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for query in capture["queries"]:
        rows.append(
            {
                "export_response_sha256": query["export_request"]["sha256"],
                "first_page_url": search_url(query["phrase"]),
                "html_page_count": query["html_page_count"],
                "language": query["language"],
                "phrase": query["phrase"],
                "query_id": query["query_id"],
                "result_count": query["result_count"],
            }
        )
    return {
        "deduplication_key": source_definition()["query_contract"][
            "deduplication_key"
        ],
        "format": QUERY_PLAN_FORMAT,
        "predeclared_before_bounded_capture": True,
        "rows": rows,
        "schema_version": SCHEMA_VERSION,
    }


def _retrieval_inventory(capture: Mapping[str, Any]) -> dict[str, Any]:
    requests = [capture["rights_evidence"]["sitemap_request"]]
    for query in capture["queries"]:
        requests.extend(query["html_requests"])
        requests.append(query["export_request"])
    return {
        "capture_window": dict(capture["capture_window"]),
        "format": RETRIEVAL_FORMAT,
        "network_attempt_count": capture["network_attempt_count"],
        "network_request_limit": MAX_NETWORK_REQUESTS,
        "successful_response_count": len(requests),
        "raw_response_bodies_retained": False,
        "requests": requests,
        "schema_version": SCHEMA_VERSION,
    }


def _assessment(
    capture: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    classifications = Counter(row["classification"] for row in observations)
    object_kinds = Counter(row["object_unit"]["object_kind"] for row in observations)
    query_counts = {
        query["query_id"]: query["result_count"] for query in capture["queries"]
    }
    return {
        "atlas_decision": {
            "assessment_artifact_indexing_permitted": True,
            "construction_map_import_permitted": False,
            "construction_master_import_permitted": False,
            "current_coverage_ledger_import_permitted": False,
            "reason": "portal-specific redistribution rights remain unclear",
            "status": "metadata_only_review_assessment",
        },
        "classification_counts": {
            name: classifications[name] for name in CLASSIFICATIONS
        },
        "coverage": {
            "attached_document_full_text_searched": False,
            "capture_window": dict(capture["capture_window"]),
            "current_recall_claimed": False,
            "global_recall_claimed": False,
            "national_recall_claimed": False,
            "query_engine_match_semantics_documented": False,
            "regional_or_local_portals_covered": False,
            "service_disabled_notice_present_on_all_search_pages": True,
            "unique_physical_site_count": None,
        },
        "counts": {
            "exact_deduplicated_records": len(observations),
            "exact_duplicates_removed": len(memberships) - len(observations),
            "object_kind_counts": dict(sorted(object_kinds.items())),
            "query_memberships": len(memberships),
            "raw_query_hits_by_query": query_counts,
            "raw_query_hits_total": len(memberships),
            "unique_physical_site_count": None,
        },
        "format": ASSESSMENT_FORMAT,
        "inference_boundary": source_definition()["inference_policy"],
        "release_id": RELEASE_ID,
        "rights_decision": source_definition()["rights"],
        "schema_version": SCHEMA_VERSION,
        "unit_boundary": source_definition()["unit_contract"],
    }


def _source_inventory(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "endpoint_contract": source_definition()["endpoint_contract"],
        "format": SOURCE_INVENTORY_FORMAT,
        "publisher": source_definition()["publisher"],
        "rights_evidence": dict(capture["rights_evidence"]),
        "schema_version": SCHEMA_VERSION,
        "source_urls": source_definition()["source_urls"],
    }


def _schema() -> dict[str, Any]:
    return {
        "classification_values": list(CLASSIFICATIONS),
        "format": SCHEMA_FORMAT,
        "lifecycle_rule": (
            "Keep the portal procedure label as regulatory metadata; leave physical "
            "construction and operating status null."
        ),
        "metric_rule": (
            "Keep numeric strings in source titles as text; emit no power, energy, "
            "PUE, or IT-capacity conversion."
        ),
        "record_units": {
            "application_unit": "one latest procedure reference from the search row",
            "decision_units": "empty; the search row does not enumerate decisions",
            "object_unit": "one portal plan, programme, project, or installation object",
            "publication_units": "empty; the search row does not enumerate publications",
        },
        "schema_version": SCHEMA_VERSION,
        "site_grouping_rule": "No physical-site grouping is performed.",
        "unique_physical_site_count": None,
    }


def _readme(assessment: Mapping[str, Any]) -> bytes:
    counts = assessment["counts"]
    classes = assessment["classification_counts"]
    return (
        "# Italy MASE VIA/VAS data-centre search assessment\n\n"
        f"The bounded 13-phrase capture returned {counts['raw_query_hits_total']} query "
        f"memberships and {counts['exact_deduplicated_records']} exact portal records. "
        f"Title review classified {classes['direct_project']} as direct projects, "
        f"{classes['ancillary_follow_up']} as ancillary or follow-up, "
        f"{classes['context_only']} as context-only, and {classes['excluded']} as "
        "excluded matches.\n\n"
        "The portal footer states that all rights are reserved and exposes no "
        "portal-specific reuse licence. This bundle contains derived metadata and "
        "response hashes. It contains no raw HTML, XLSX, attachments, or decision "
        "documents.\n\n"
        "A VIA, VAS, or AIA procedure describes a regulatory unit. The assessment "
        "does not infer physical construction or operation, convert numeric title "
        "text into power or energy, merge records into sites, or claim national, "
        "current, or global recall.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Derived search-result metadata: Ministero dell'Ambiente e della Sicurezza "
        "Energetica, Portale Valutazioni e Autorizzazioni Ambientali.\n"
        "Portal-specific redistribution rights were not established; no raw source "
        "response or attachment is included.\n"
    ).encode("utf-8")


def derive_release_files(capture: Mapping[str, Any]) -> dict[str, bytes]:
    validate_capture(capture)
    observations, memberships = _deduplicate(capture)
    assessment = _assessment(capture, observations, memberships)
    return {
        "ATTRIBUTION.txt": _attribution(),
        "README.md": _readme(assessment),
        "assessment.json": canonical_json(assessment),
        "capture-metadata.json": canonical_json(capture),
        "definition.json": canonical_json(source_definition()),
        "observations.jsonl": b"".join(
            canonical_line(row) for row in observations
        ),
        "query-membership.jsonl": b"".join(
            canonical_line(row) for row in memberships
        ),
        "query-plan.json": canonical_json(_query_plan(capture)),
        "retrieval-inventory.json": canonical_json(_retrieval_inventory(capture)),
        "schema.json": canonical_json(_schema()),
        "source-inventory.json": canonical_json(_source_inventory(capture)),
    }


def _manifest(capture: Mapping[str, Any], payloads: Mapping[str, bytes]) -> dict[str, Any]:
    assessment = json.loads(payloads["assessment.json"])
    return {
        "capture": _checkpoint_bytes(payloads["capture-metadata.json"]),
        "counts": assessment["counts"],
        "definition": {
            "filename": f"{RELEASE_ID}.json",
            **_checkpoint_bytes(payloads["definition.json"]),
        },
        "format": RELEASE_FORMAT,
        "generated_at": capture["capture_window"]["completed_at"],
        "outputs": {
            name: _checkpoint_bytes(body) for name, body in sorted(payloads.items())
        },
        "release_id": RELEASE_ID,
        "rights_decision": "derived_metadata_and_response_hashes_only",
        "schema_version": SCHEMA_VERSION,
    }


def write_release_bundle(
    capture: Mapping[str, Any], output_directory: str | Path, *, freeze: bool = True
) -> dict[str, Any]:
    payloads = derive_release_files(capture)
    manifest = _manifest(capture, payloads)
    manifest_raw = canonical_json(manifest)
    sidecar = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ItalyMASEVIAVASError(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for name, body in payloads.items():
            (stage / name).write_bytes(body)
        (stage / MANIFEST_FILENAME).write_bytes(manifest_raw)
        (stage / MANIFEST_HASH_FILENAME).write_bytes(sidecar)
        validate_release_bundle(stage)
        if freeze:
            for entry in stage.iterdir():
                entry.chmod(0o444)
            stage.chmod(0o555)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            stage.chmod(0o755)
            for entry in stage.iterdir():
                if not entry.is_symlink():
                    entry.chmod(0o644)
            shutil.rmtree(stage)
        raise
    return manifest


def _load_json_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ItalyMASEVIAVASError(f"{label} must be a regular file")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ItalyMASEVIAVASError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ItalyMASEVIAVASError(f"{label} must be canonical JSON")
    return value, raw


def validate_release_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ItalyMASEVIAVASError("release must be a regular directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != EXPECTED_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ItalyMASEVIAVASError("release closed file set changed")
    manifest, manifest_raw = _load_json_object(
        root / MANIFEST_FILENAME, "manifest"
    )
    if (root / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ItalyMASEVIAVASError("manifest sidecar changed")
    if (
        set(manifest)
        != {
            "capture",
            "counts",
            "definition",
            "format",
            "generated_at",
            "outputs",
            "release_id",
            "rights_decision",
            "schema_version",
        }
        or manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("rights_decision")
        != "derived_metadata_and_response_hashes_only"
    ):
        raise ItalyMASEVIAVASError("manifest identity changed")
    _timestamp(manifest.get("generated_at"), "manifest.generated_at")
    payload_names = EXPECTED_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != payload_names:
        raise ItalyMASEVIAVASError("manifest output inventory changed")
    for name, checkpoint in manifest["outputs"].items():
        if _checkpoint(root / name) != {
            "bytes": checkpoint.get("bytes"),
            "sha256": checkpoint.get("sha256"),
        }:
            raise ItalyMASEVIAVASError(f"release output changed: {name}")
    capture, capture_raw = _load_json_object(
        root / "capture-metadata.json", "capture metadata"
    )
    validate_capture(capture)
    expected_payloads = derive_release_files(capture)
    for name, expected in expected_payloads.items():
        if (root / name).read_bytes() != expected:
            raise ItalyMASEVIAVASError(f"release output does not reproduce: {name}")
    expected_manifest = _manifest(capture, expected_payloads)
    if manifest != expected_manifest:
        raise ItalyMASEVIAVASError("manifest does not reproduce")
    if manifest["capture"] != _checkpoint_bytes(capture_raw):
        raise ItalyMASEVIAVASError("capture checkpoint changed")
    if (root / "definition.json").read_bytes() != canonical_json(
        source_definition()
    ):
        raise ItalyMASEVIAVASError("embedded definition changed")
    return {
        "assessment": json.loads((root / "assessment.json").read_text()),
        "capture": capture,
        "manifest": manifest,
    }


def is_frozen_release(directory: str | Path) -> bool:
    root = Path(directory)
    if root.stat().st_mode & 0o777 != 0o555:
        return False
    return all(
        entry.stat().st_mode & 0o777 == 0o444 for entry in root.iterdir()
    )


def thaw_for_test(directory: str | Path) -> None:
    root = Path(directory)
    root.chmod(stat.S_IRWXU)
    for entry in root.iterdir():
        entry.chmod(stat.S_IRUSR | stat.S_IWUSR)


__all__ = [
    "CAPTURE_FORMAT",
    "CLASSIFICATIONS",
    "ItalyMASEVIAVASError",
    "MAX_NETWORK_REQUESTS",
    "MIN_REQUEST_INTERVAL_SECONDS",
    "PORTAL_FOOTER",
    "QUERY_SPECS",
    "RELEASE_ID",
    "SEARCH_ENDPOINT",
    "SITEMAP_URL",
    "canonical_json",
    "classify_record",
    "derive_release_files",
    "export_url",
    "is_frozen_release",
    "parse_export_xlsx",
    "parse_search_html",
    "search_url",
    "sha256_bytes",
    "source_definition",
    "thaw_for_test",
    "validate_capture",
    "validate_release_bundle",
    "write_release_bundle",
]
