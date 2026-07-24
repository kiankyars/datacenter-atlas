"""Bounded Brazil PNCP data-centre procurement-publication assessment.

This lane inventories publication records returned by five closed PNCP search
queries.  It deliberately does not resolve publications into projects or
sites.  PNCP procurement publication is neither a construction milestone nor
evidence that a facility became operational.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any
from urllib.parse import urlencode, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "brazil-pncp-data-centre-publications-2016-2026-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-brazil-pncp-publications-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-brazil-pncp-publications-definition-v1"
CAPTURE_FORMAT = "datacenter-atlas-brazil-pncp-publications-capture-v1"
OBSERVATION_FORMAT = "datacenter-atlas-brazil-pncp-publication-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-brazil-pncp-publications-assessment-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-brazil-pncp-retrieval-inventory-v1"
SOURCE_INVENTORY_FORMAT = "datacenter-atlas-brazil-pncp-source-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-brazil-pncp-schema-v1"

PNCP_ORIGIN = "https://pncp.gov.br"
PNCP_SEARCH_ENDPOINT = f"{PNCP_ORIGIN}/api/search/"
PNCP_FRONTEND_URL = f"{PNCP_ORIGIN}/app/editais"
PNCP_LAW_URL = (
    "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"
)
OPEN_DATA_DECREE_URL = (
    "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/decreto/d8777.htm"
)
DOU_ROBOTS_URL = "https://www.in.gov.br/robots.txt"
DOU_OPEN_DATA_URL = (
    "https://www.gov.br/imprensanacional/pt-br/acesso-a-informacao/dados-abertos"
)
INLABS_URL = "https://www.gov.br/imprensanacional/pt-br/servicos/inlabs"

START_DATE = date(2016, 1, 1)
END_DATE = date(2026, 7, 18)
YEARS = tuple(range(START_DATE.year, END_DATE.year + 1))
DOCUMENT_TYPES = ("edital", "ata", "contrato", "pcaorgao")
QUERY_TERMS = (
    "centro de dados",
    "centros de dados",
    "centro de processamento de dados",
    "data center",
    "datacenter",
)
QUERY_IDS = {term: f"q{index:02d}" for index, term in enumerate(QUERY_TERMS, 1)}
PAGE_SIZE = 5000
MAX_NETWORK_REQUESTS = 11
EXPECTED_NETWORK_REQUESTS = 11
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_ATTEMPTS_PER_REQUEST = 4

CLASSIFICATIONS = (
    "direct_project",
    "ancillary_follow_up",
    "context_only",
    "excluded",
)

# Curated at publication-record level from the bounded result descriptions.
# These are signals, not resolved projects.  Contracts and atas remain
# follow-up publications even when their object is a physical facility.
DIRECT_PUBLICATION_IDS = frozenset(
    {
        "035748cbff6581c0c4790d1f19e1b438",
        "1d0269f1d926efe9fb4a749053bda3c6",
        "255aa901a9840dca09864b443e4123f8",
        "2f0c13864d7fe574005fb590bf19a1bb",
        "4296dd45d654726989a1641352349af0",
        "49e62a3fbb42f51c4914aa70f66f3e71",
        "4b43f0555103c647d4458d0b27ffe9e0",
        "4d65044c290355f4c58a49f1ca39ec18",
        "4ecdbff94b68f158c9737a7a5f9c36f8",
        "57bc18483a022d78996b190b548b05f6",
        "59e53f86f3fcebfb3bd068f9ddc0b453",
        "61a325dab3de5c1b06de41313309dd21",
        "6df17b7e008f6a8a66625b797d390679",
        "7690468e454b69fdeb69b67afa9daa1d",
        "87116730e81b199c3656b1e9d628bf04",
        "88b286bcee9fac4a5fb76396c9c73217",
        "8c0cb6826edf73c621186a0860e6f652",
        "93e8e8c263308caade3336bc31669f7b",
        "99f2f56c20e0c1a0924a7ca33db4facd",
        "9a360c65e2f16be6dae74259ab73dead",
        "9a7b97a6439ae58d05b684e09b176ff6",
        "b2dadd7b47a9c0e0b7b70f7d22f60fff",
        "b3d0b8e99612940db0c3ad40cc4fc480",
        "b47ef8761c18de323c63a97bb4703022",
        "ba22b0890701273796ed71704f72e0cf",
        "cbeac4c4122ab958e1eb31db214290cb",
        "d8ae94989e001ba89c07597107c68d81",
        "ddd4b43a162fa2dba1d4cdbee4ccd4bb",
    }
)

ANCILLARY_PUBLICATION_IDS = frozenset(
    {
        "0e13ad0890654cb393a643518898dd88",
        "0f4e4619237a242bfa655b623b7b32ce",
        "09016adee42d14a36ca046d683810fae",
        "09179940be0fde5505828309f0d88877",
        "10970f1ade92273b584c6c7162750f9e",
        "1440a2c612d47eb70601f68cb581d000",
        "19045183289f4b60029d3d1f0cf5835c",
        "1adf7c9db0bbe67a35a68fbf6834f7a1",
        "2a864f344b91c7c1dedc1d9088c563ed",
        "2b1a5d21309ad1a7f770aea86da54d9f",
        "32daf9333a3dff3fa503e26c59d99be5",
        "3347d09691250d12cb7baba9f7243715",
        "3b3e003821cfa6adf196115fd46ecc46",
        "3d8e06b5e7d3f91fe05b8863248e3d8d",
        "404c93de4db820d7943962445e50e9b0",
        "42671dd505e223543c4fdd30d6962854",
        "48aef3d91e8bcee65ef477ea52338590",
        "50a36a180acf38518f47c22bf86f1f00",
        "5e1b857057a5d5270bc558f4c4d2add6",
        "5fdf41bd28e6459e4061662ed0b93dfe",
        "6f71591e972c415dfea0cfe08fb12bde",
        "695ec359709f183e6560a000709ffa8e",
        "73a9db5185275a65e8e0f0ef8c7eba49",
        "73d0b03d296ce637249723b95aee5f89",
        "76e83420d92e9b2ab684fb1805629d6d",
        "779e65cb637b8282078ab3a57713aa67",
        "7de47fe6c8ccde77b5a97ce7b569ed7f",
        "81660ab8130583f1b2a75c3fd35e40e1",
        "81b5f72afe199918e3403608076396e1",
        "88a99a473028469e4d04e64c87289875",
        "89d55824087c3362e7cdf1350e4ed818",
        "8956f7fb33da7397954e95097150019e",
        "8a9aeaf14310e2b89f487a196275a934",
        "926420b8acd912f66b507eba6181d4d6",
        "9264d19b4de3dad8673d27a697b47b66",
        "9f39920fdb1843c709934530e07094ab",
        "a1eeaf21a753d1adf899c4ca0d6fc5be",
        "a431a710295d10882fdd4a1a7d1cd378",
        "ab814f2c68c12b689921559e8649654f",
        "b5f3b9f3e8f64a1768c6e589f98cd3b5",
        "b93ec55855792b18a85e810ecafb8164",
        "cd3886992a753ca3f0e1edfa6cc64adb",
        "ce1fcb9b234ae18e3db67d6af4f9e780",
        "d3645e02eb2091d3cfbb5d6de7f66b1f",
        "d3e132995cc9b75ce81d847e811a4ad8",
        "d77d8e9c05fc5963541b47a92ca8b89d",
        "db194df9c9c0657a4638ee47c7d005a2",
        "dfb93962fd85c0249c6174f5f5c93f02",
        "e758cf227d49c630ed8b79cff8054c1e",
        "eb750b6d57dbf11bcf17620796fa46ee",
        "efb7444044f56efae30be63914fe680c",
        "f5d86512f8a2c2b30a2c83f255d487da",
        "faae8aaadf0ff80063da6f03229709b2",
    }
)

CONTEXT_PUBLICATION_IDS = frozenset(
    {
        "282c981ee4dea7eb6a79c96519d0daf8",
        "2ff3f79a1c1e6bc987c65d1ca31333e6",
        "3606b91e1292d235ed683e96c65c246f",
        "64d6b908c27248f8128bbbe3fd129a38",
        "8a5a8e44e9b26d261e8b87b8154a8b37",
        "a7288db6f15441ab1ef5724f2db33faf",
        "b5656b562f649ab9cfc3e8383af25791",
        "c16773369109c0e0d458baca01ab98fc",
        "e7b649f932e6cd383db17fbef170c038",
        "f23f25ce4a0b309cd5da654a8ca3faf8",
    }
)

if DIRECT_PUBLICATION_IDS & ANCILLARY_PUBLICATION_IDS:
    raise RuntimeError("curated classification sets overlap")
if (DIRECT_PUBLICATION_IDS | ANCILLARY_PUBLICATION_IDS) & CONTEXT_PUBLICATION_IDS:
    raise RuntimeError("curated classification sets overlap")

RIGHTS_POLICY = {
    "attribution_required": True,
    "derived_factual_metadata_publication_eligible": True,
    "legal_conclusion_claimed": False,
    "notice_description_redistribution_permitted": False,
    "pncp_specific_license_identified": False,
    "raw_api_bodies_released": False,
    "statutory_basis": [
        {
            "citation": "Lei 14.133/2021, art. 174, paragraph 4",
            "url": PNCP_LAW_URL,
        },
        {
            "citation": "Decreto 8.777/2016, arts. 2 III and 4",
            "url": OPEN_DATA_DECREE_URL,
        },
    ],
    "verified_local_date": END_DATE.isoformat(),
}

DOWNSTREAM_IMPORT_POLICY = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "reason": (
        "review-only procurement-publication signals; no project/site resolution "
        "and no physical lifecycle verification"
    ),
}

LIFECYCLE_BOUNDARY = {
    "atlas_lifecycle_status": None,
    "construction_verified": False,
    "operation_verified": False,
    "procurement_publication_is_construction_start": False,
    "procurement_publication_is_completion": False,
    "procurement_publication_is_operation": False,
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "definition.json",
    "observations.jsonl",
    "query-membership.jsonl",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
}
EXPECTED_FILES = DERIVED_FILENAMES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class BrazilPNCPError(ValueError):
    """Raised when the PNCP capture or frozen release fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(dict(row)) for row in rows)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha256_file(path)}


def query_url(term: str) -> str:
    if term not in QUERY_TERMS:
        raise BrazilPNCPError("term outside closed query plan")
    parameters = {
        "q": f'"{term}"',
        "tipos_documento": "|".join(DOCUMENT_TYPES),
        "ordenacao": "-data",
        "pagina": "1",
        "tam_pagina": str(PAGE_SIZE),
        "anos": "|".join(str(year) for year in YEARS),
    }
    return f"{PNCP_SEARCH_ENDPOINT}?{urlencode(parameters)}"


def _official_url(url: str) -> str:
    parsed = urlsplit(url)
    allowed = {"pncp.gov.br", "www.in.gov.br", "www.gov.br", "www.planalto.gov.br"}
    if parsed.scheme != "https" or parsed.hostname not in allowed:
        raise BrazilPNCPError(f"non-official URL outside capture policy: {url}")
    return url


def source_definition() -> dict[str, Any]:
    return {
        "coverage_contract": {
            "bounded_date_end": END_DATE.isoformat(),
            "bounded_date_start": START_DATE.isoformat(),
            "dou_automated_search_completed": False,
            "dou_blocker": (
                "official robots.txt disallows automated crawling; INLABS XML "
                "download requires an authenticated registration"
            ),
            "national_completeness_claimed": False,
            "pncp_created_in_2021": True,
            "pncp_index_hits_2016_2020": 0,
            "pncp_procurement_publications_only": True,
            "procurement_entity_count": None,
            "project_count": None,
            "site_count": None,
        },
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_consumption": None,
            "automatic_lifecycle_promotion_permitted": False,
            "data_centre_type": None,
            "entity_resolution_performed": False,
            "gross_facility_power": None,
            "it_capacity": None,
            "metrics_extracted": False,
            "project_count": None,
            "publication_count_is_project_count": False,
            "pue": None,
            "procurement_entity_count": None,
            "site_count": None,
        },
        "network_policy": {
            "maximum_attempts_per_request": MAX_ATTEMPTS_PER_REQUEST,
            "maximum_network_requests": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "page_size": PAGE_SIZE,
        },
        "publisher": "Portal Nacional de Contratações Públicas (PNCP), Brazil",
        "query_plan": [
            {
                "api_url": query_url(term),
                "local_literal_postfilter": True,
                "phrase": term,
                "query_id": QUERY_IDS[term],
            }
            for term in QUERY_TERMS
        ],
        "release_id": RELEASE_ID,
        "rights_policy": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source": "PNCP official search API",
        "source_frontend_url": PNCP_FRONTEND_URL,
    }


def _classification(publication_id: str, literal_terms: list[str]) -> tuple[str, str]:
    if publication_id in DIRECT_PUBLICATION_IDS:
        return "direct_project", "curated_initial_physical_facility_procurement"
    if publication_id in ANCILLARY_PUBLICATION_IDS:
        return "ancillary_follow_up", "curated_contract_capital_follow_up_or_planning"
    if publication_id in CONTEXT_PUBLICATION_IDS:
        return "context_only", "curated_related_or_ambiguous_facility_context"
    if not literal_terms:
        return "excluded", "backend_match_without_literal_query_phrase"
    return "excluded", "generic_it_service_hardware_maintenance_or_non_build_procurement"


def _literal_terms(description: str) -> list[str]:
    folded = " ".join(description.casefold().split())
    return [term for term in QUERY_TERMS if term.casefold() in folded]


def _parse_published_at(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        raise BrazilPNCPError("data_publicacao_pncp must be a string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise BrazilPNCPError("invalid PNCP publication timestamp") from error
    published_date = parsed.date()
    if not START_DATE <= published_date <= END_DATE:
        raise BrazilPNCPError(f"publication outside bounded dates: {value}")
    return value, published_date.isoformat()


def _validate_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise BrazilPNCPError("API item must be an object")
    publication_id = item.get("id")
    if not isinstance(publication_id, str) or not _PUBLICATION_ID_RE.fullmatch(
        publication_id
    ):
        raise BrazilPNCPError("invalid exact PNCP search-document ID")
    if item.get("document_type") not in DOCUMENT_TYPES:
        raise BrazilPNCPError("unexpected PNCP document type")
    item_url = item.get("item_url")
    if not isinstance(item_url, str) or not item_url.startswith("/"):
        raise BrazilPNCPError("invalid PNCP item URL")
    description = item.get("description")
    if description is not None and not isinstance(description, str):
        raise BrazilPNCPError("PNCP description must be text")
    _parse_published_at(item.get("data_publicacao_pncp"))
    normalized = dict(item)
    normalized["description"] = description or ""
    return normalized


def load_capture(capture_directory: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    capture_path = capture_directory / "capture.json"
    if not capture_path.is_file():
        raise BrazilPNCPError("capture.json missing")
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    if capture.get("format") != CAPTURE_FORMAT:
        raise BrazilPNCPError("unexpected capture format")
    requests = capture.get("requests")
    if not isinstance(requests, list) or len(requests) != EXPECTED_NETWORK_REQUESTS:
        raise BrazilPNCPError("capture request count changed")
    bodies: dict[str, bytes] = {}
    for row in requests:
        if not isinstance(row, dict):
            raise BrazilPNCPError("capture request must be an object")
        request_id = row.get("request_id")
        body_file = row.get("body_file")
        if not isinstance(request_id, str) or not isinstance(body_file, str):
            raise BrazilPNCPError("capture request identity missing")
        body_path = capture_directory / body_file
        body = body_path.read_bytes()
        if row.get("bytes") != len(body) or row.get("sha256") != sha256_bytes(body):
            raise BrazilPNCPError(f"capture checkpoint mismatch: {request_id}")
        _official_url(str(row.get("url")))
        bodies[request_id] = body
    return capture, bodies


def build_rows(
    capture: Mapping[str, Any], bodies: Mapping[str, bytes]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    memberships: defaultdict[str, set[str]] = defaultdict(set)
    query_inventory: list[dict[str, Any]] = []

    for term in QUERY_TERMS:
        query_id = QUERY_IDS[term]
        body = bodies.get(query_id)
        if body is None:
            raise BrazilPNCPError(f"missing query response: {query_id}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise BrazilPNCPError(f"invalid query JSON: {query_id}") from error
        items = payload.get("items")
        total = payload.get("total")
        if not isinstance(items, list) or not isinstance(total, int) or total < 0:
            raise BrazilPNCPError(f"invalid result envelope: {query_id}")
        if total >= PAGE_SIZE:
            raise BrazilPNCPError(f"query reached result ceiling: {query_id}")
        if len(items) != total:
            raise BrazilPNCPError(f"query is not a complete one-page capture: {query_id}")
        query_ids: set[str] = set()
        literal_count = 0
        for raw_item in items:
            item = _validate_item(raw_item)
            publication_id = item["id"]
            if publication_id in query_ids:
                raise BrazilPNCPError(f"duplicate ID inside query: {query_id}")
            query_ids.add(publication_id)
            memberships[publication_id].add(term)
            literal_count += int(term in _literal_terms(item["description"]))
            existing = by_id.get(publication_id)
            if existing is not None and canonical_line(existing) != canonical_line(item):
                raise BrazilPNCPError(f"conflicting metadata for ID: {publication_id}")
            by_id[publication_id] = item
        query_inventory.append(
            {
                "api_total": total,
                "backend_only_nonliteral_count": total - literal_count,
                "literal_phrase_count": literal_count,
                "phrase": term,
                "query_id": query_id,
                "response_bytes": len(body),
                "response_sha256": sha256_bytes(body),
            }
        )

    curated = DIRECT_PUBLICATION_IDS | ANCILLARY_PUBLICATION_IDS | CONTEXT_PUBLICATION_IDS
    missing_curated = sorted(curated - by_id.keys())
    if missing_curated:
        raise BrazilPNCPError(f"curated IDs missing from bounded union: {missing_curated}")

    rows: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    for publication_id, item in by_id.items():
        description = item["description"]
        literal = _literal_terms(description)
        classification, reason = _classification(publication_id, literal)
        published_at, publication_date = _parse_published_at(
            item["data_publicacao_pncp"]
        )
        terms = sorted(memberships[publication_id], key=QUERY_TERMS.index)
        row = {
            "agency_cnpj": item.get("orgao_cnpj"),
            "agency_name": item.get("orgao_nome"),
            "atlas_lifecycle": LIFECYCLE_BOUNDARY,
            "classification": classification,
            "classification_reason_code": reason,
            "data_centre_type": None,
            "description_sha256": sha256_bytes(description.encode("utf-8")),
            "document_type": item["document_type"],
            "format": OBSERVATION_FORMAT,
            "license_count_contribution": 0,
            "literal_query_terms": literal,
            "matched_query_terms": terms,
            "metrics": [],
            "municipality": item.get("municipio_nome"),
            "pncp_control_number": item.get("numero_controle_pncp"),
            "project_count_contribution": None,
            "project_id": None,
            "procurement_entity_count_contribution": None,
            "procurement_entity_id": None,
            "publication_count_contribution": 1,
            "publication_date": publication_date,
            "publication_id": publication_id,
            "published_at_source_precision": published_at,
            "site_id": None,
            "source_record_url": f"{PNCP_ORIGIN}{item['item_url']}",
            "state": item.get("uf"),
            "title": item.get("title"),
            "unique_site_count_contribution": None,
            "unit_code": item.get("unidade_codigo"),
            "unit_name": item.get("unidade_nome"),
        }
        rows.append(row)
        for term in terms:
            membership_rows.append(
                {
                    "literal_phrase_present": term in literal,
                    "publication_id": publication_id,
                    "query_id": QUERY_IDS[term],
                    "query_term": term,
                }
            )

    rows.sort(key=lambda row: (row["publication_date"], row["publication_id"]))
    membership_rows.sort(key=lambda row: (row["query_id"], row["publication_id"]))
    return rows, membership_rows, query_inventory


def _rights_evidence(capture: Mapping[str, Any], bodies: Mapping[str, bytes]) -> None:
    requests = {row["request_id"]: row for row in capture["requests"]}
    robots = bodies["dou-robots"].decode("utf-8", errors="replace").casefold()
    if "user-agent: *" not in robots or "disallow: /" not in robots:
        raise BrazilPNCPError("DOU robots blocker evidence changed")
    if requests["pncp-frontend"].get("status") != 200:
        raise BrazilPNCPError("PNCP frontend unavailable")
    for request_id in ("pncp-law", "open-data-decree", "dou-open-data", "inlabs"):
        if requests[request_id].get("status") != 200:
            raise BrazilPNCPError(f"official evidence unavailable: {request_id}")


def build_release_documents(
    definition: Mapping[str, Any], capture: Mapping[str, Any], bodies: Mapping[str, bytes]
) -> dict[str, bytes]:
    if definition != source_definition():
        raise BrazilPNCPError("checked-in definition differs from module contract")
    _rights_evidence(capture, bodies)
    rows, membership_rows, query_inventory = build_rows(capture, bodies)
    classifications = Counter(row["classification"] for row in rows)
    document_types = Counter(row["document_type"] for row in rows)
    literal_union = sum(bool(row["literal_query_terms"]) for row in rows)
    dates = [row["publication_date"] for row in rows]
    query_memberships = len(membership_rows)
    assessment = {
        "classification_counts": {
            classification: classifications.get(classification, 0)
            for classification in CLASSIFICATIONS
        },
        "coverage": {
            "backend_query_memberships": query_memberships,
            "bounded_publication_union_count": len(rows),
            "date_max": max(dates),
            "date_min": min(dates),
            "dou_automated_search_completed": False,
            "literal_phrase_publication_union_count": literal_union,
            "national_completeness_claimed": False,
            "pncp_index_hits_2016_2020": sum(
                row["publication_date"][:4] in {str(year) for year in range(2016, 2021)}
                for row in rows
            ),
            "project_count": None,
            "site_count": None,
        },
        "document_type_counts": dict(sorted(document_types.items())),
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": ASSESSMENT_FORMAT,
        "initial_notice_publication_count": document_types.get("edital", 0),
        "license_count": 0,
        "lifecycle_boundary": LIFECYCLE_BOUNDARY,
        "metric_count": 0,
        "non_null_pncp_control_number_count": sum(
            row["pncp_control_number"] is not None for row in rows
        ),
        "procurement_entity_count": None,
        "project_count": None,
        "publication_count": len(rows),
        "query_inventory": query_inventory,
        "release_id": RELEASE_ID,
        "rights_policy": RIGHTS_POLICY,
        "unique_site_count": None,
    }
    retrieval = {
        "capture_created_at": capture["created_at"],
        "format": RETRIEVAL_FORMAT,
        "network_requests": [
            {
                key: row[key]
                for key in ("bytes", "content_type", "request_id", "sha256", "status", "url")
            }
            for row in capture["requests"]
        ],
        "query_inventory": query_inventory,
        "raw_bodies_released": False,
        "release_build_network_requests": 0,
    }
    source_inventory = {
        "format": SOURCE_INVENTORY_FORMAT,
        "official_sources": [
            {"role": "publication_search", "url": PNCP_FRONTEND_URL},
            {"role": "pncp_open_data_law", "url": PNCP_LAW_URL},
            {"role": "federal_open_data_definition", "url": OPEN_DATA_DECREE_URL},
            {"role": "dou_transport_policy", "url": DOU_ROBOTS_URL},
            {"role": "dou_open_data_description", "url": DOU_OPEN_DATA_URL},
            {"role": "inlabs_registration_description", "url": INLABS_URL},
        ],
        "publisher_responsibility_note": (
            "PNCP centralizes mandatory publications; source contracting bodies "
            "remain responsible for the published record metadata."
        ),
    }
    schema = {
        "format": SCHEMA_FORMAT,
        "invariants": {
            "description_released": False,
            "exact_publication_id_dedupe": True,
            "license_count_is_project_count": False,
            "metrics_must_be_typed": True,
            "notice_contract_and_ata_units_collapsed": False,
            "procurement_entity_count_is_null": True,
            "project_count_is_null": True,
            "publication_count_is_project_count": False,
            "site_count_is_null": True,
        },
        "observation_format": OBSERVATION_FORMAT,
        "schema_version": SCHEMA_VERSION,
    }
    readme = f"""# Brazil PNCP data-centre publication assessment

This frozen release contains **{len(rows):,} PNCP publication records** returned by
five bounded official search queries for {START_DATE.isoformat()} through
{END_DATE.isoformat()}. It contains {query_memberships:,} query memberships;
{literal_union:,} union records contain a literal queried phrase. Search-document
ID is the sole deduplication key. Editais, atas, and contracts remain separate
publication units.

The classification is publication-level review triage. `direct_project` means
the publication object explicitly procures a physical data-centre facility or
safe-room build/installation. `ancillary_follow_up` includes capital work,
planning, contracts, and atas. It is not a project count. Generic software,
cloud, hosting, hardware, maintenance, and false/broad search matches are not
promoted. Project count and unique-site count are null; no entity resolution was
performed. Procurement-entity count is also null: PNCP control numbers are
retained as publication metadata, not treated as resolved procurement chains.
No procurement wording is converted into construction, completion,
or operation status. No power, energy, PUE, or facility-type metric is inferred.

DOU was assessed first but not crawled: its official robots.txt disallows all
automated crawling and INLABS requires authenticated registration. PNCP is an
authoritative federal publication fallback created by Lei 14.133/2021. The
absence of PNCP records in 2016-2020 is a portal-era blind spot, not evidence of
no procurements.

Only derived factual metadata is released. Raw responses and notice descriptions
remain in operator quarantine. Rights treatment relies on Lei 14.133/2021 art.
174 paragraph 4 and Decreto 8.777/2016; this is not a legal conclusion.

This review-only release may **not** be imported into the construction master,
construction map, or current coverage ledger.
""".encode("utf-8")
    attribution = (
        "Source: Portal Nacional de Contratações Públicas (PNCP), Brazil.\n"
        f"Official search frontend: {PNCP_FRONTEND_URL}\n"
        f"PNCP law: {PNCP_LAW_URL}\n"
        f"Federal open-data decree: {OPEN_DATA_DECREE_URL}\n"
        "Derived factual metadata only; raw API bodies and notice descriptions "
        "are not redistributed.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(definition),
        "observations.jsonl": jsonl(rows),
        "query-membership.jsonl": jsonl(membership_rows),
        "retrieval-inventory.json": canonical_json(retrieval),
        "schema.json": canonical_json(schema),
        "source-inventory.json": canonical_json(source_inventory),
    }


def _manifest(documents: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "files": {
            name: {"bytes": len(body), "sha256": sha256_bytes(body)}
            for name, body in sorted(documents.items())
        },
        "format": RELEASE_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def freeze_release(path: Path) -> None:
    for child in path.rglob("*"):
        child.chmod(0o555 if child.is_dir() else 0o444)
    path.chmod(0o555)


def thaw_for_test(path: Path) -> None:
    path.chmod(0o755)
    for child in path.rglob("*"):
        child.chmod(0o755 if child.is_dir() else 0o644)


def is_frozen_release(path: Path) -> bool:
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        return False
    return all(
        stat.S_IMODE(child.stat().st_mode) == (0o555 if child.is_dir() else 0o444)
        for child in path.rglob("*")
    )


def write_release_bundle(
    definition_path: Path,
    capture_directory: Path,
    output: Path,
    *,
    freeze: bool = True,
) -> Path:
    definition = json.loads(definition_path.read_text(encoding="utf-8"))
    capture, bodies = load_capture(capture_directory)
    documents = build_release_documents(definition, capture, bodies)
    manifest = _manifest(documents)
    documents[MANIFEST_FILENAME] = canonical_json(manifest)
    documents[MANIFEST_HASH_FILENAME] = (
        f"{sha256_bytes(documents[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{RELEASE_ID}-", dir=output.parent))
    try:
        for name, body in documents.items():
            (staging / name).write_bytes(body)
        validate_release_bundle(staging, definition_path=definition_path)
        if output.exists():
            if is_frozen_release(output):
                raise BrazilPNCPError(f"refusing to overwrite frozen release: {output}")
            shutil.rmtree(output)
        staging.replace(output)
        if freeze:
            freeze_release(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return output


def validate_release_bundle(
    path: Path, *, definition_path: Path | None = None
) -> dict[str, Any]:
    if not path.is_dir():
        raise BrazilPNCPError("release directory missing")
    actual_files = {child.name for child in path.iterdir() if child.is_file()}
    if actual_files != EXPECTED_FILES:
        raise BrazilPNCPError(
            f"release file set mismatch: {sorted(actual_files ^ EXPECTED_FILES)}"
        )
    manifest_raw = (path / MANIFEST_FILENAME).read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest.get("format") != RELEASE_FORMAT or manifest.get("release_id") != RELEASE_ID:
        raise BrazilPNCPError("manifest identity mismatch")
    expected_hash_line = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    if (path / MANIFEST_HASH_FILENAME).read_text(encoding="ascii") != expected_hash_line:
        raise BrazilPNCPError("manifest hash mismatch")
    if set(manifest.get("files", {})) != DERIVED_FILENAMES:
        raise BrazilPNCPError("manifest file inventory mismatch")
    for name, expected in manifest["files"].items():
        actual = checkpoint(path / name)
        if actual != expected or not _SHA256_RE.fullmatch(actual["sha256"]):
            raise BrazilPNCPError(f"file checkpoint mismatch: {name}")

    definition = json.loads((path / "definition.json").read_text(encoding="utf-8"))
    if definition != source_definition():
        raise BrazilPNCPError("release definition differs from module contract")
    if definition_path is not None:
        checked_in = json.loads(definition_path.read_text(encoding="utf-8"))
        if checked_in != definition:
            raise BrazilPNCPError("release definition differs from checked-in definition")
    assessment = json.loads((path / "assessment.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (path / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    memberships = [
        json.loads(line)
        for line in (path / "query-membership.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    ids = [row["publication_id"] for row in rows]
    ordering = [(row["publication_date"], row["publication_id"]) for row in rows]
    if len(ids) != len(set(ids)) or ordering != sorted(ordering):
        raise BrazilPNCPError("observation identity/order mismatch")
    counts = Counter(row["classification"] for row in rows)
    expected_counts = {
        classification: counts.get(classification, 0) for classification in CLASSIFICATIONS
    }
    if assessment.get("classification_counts") != expected_counts:
        raise BrazilPNCPError("classification arithmetic mismatch")
    if assessment.get("publication_count") != len(rows):
        raise BrazilPNCPError("publication count mismatch")
    if assessment["coverage"].get("backend_query_memberships") != len(memberships):
        raise BrazilPNCPError("query membership arithmetic mismatch")
    for row in rows:
        if row["project_id"] is not None or row["site_id"] is not None:
            raise BrazilPNCPError("project/site identity must remain null")
        if row["metrics"] or row["data_centre_type"] is not None:
            raise BrazilPNCPError("unsupported metrics/type inference")
        if row["atlas_lifecycle"] != LIFECYCLE_BOUNDARY:
            raise BrazilPNCPError("physical lifecycle boundary changed")
        if row["publication_count_contribution"] != 1:
            raise BrazilPNCPError("publication contribution mismatch")
        if row["project_count_contribution"] is not None:
            raise BrazilPNCPError("publication became a project count")
        if row["procurement_entity_id"] is not None:
            raise BrazilPNCPError("publication became a procurement entity")
        if row["procurement_entity_count_contribution"] is not None:
            raise BrazilPNCPError("publication became a procurement entity count")
    if assessment.get("downstream_import_policy") != DOWNSTREAM_IMPORT_POLICY:
        raise BrazilPNCPError("downstream import policy changed")
    return {
        "assessment": assessment,
        "definition": definition,
        "manifest": manifest,
        "memberships": memberships,
        "observations": rows,
    }


def _capture_request(
    url: str,
    *,
    timeout: float,
    max_attempts: int,
) -> tuple[int, str, bytes]:
    _official_url(url)
    with tempfile.TemporaryDirectory(prefix="brazil-pncp-request-") as temporary:
        output = Path(temporary) / "body.bin"
        command = [
            "curl",
            "--http1.1",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
            "--retry",
            str(max_attempts - 1),
            "--retry-all-errors",
            "--max-time",
            str(timeout),
            "--user-agent",
            "Mozilla/5.0 (compatible; datacenter-atlas-official-source-audit/1.0)",
            "--header",
            "Accept: application/json,text/html,text/plain,*/*",
            "--output",
            str(output),
            "--write-out",
            "%{http_code}\n%{content_type}",
            url,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=(timeout + 10) * max_attempts,
        )
        if completed.returncode != 0 or not output.is_file():
            detail = completed.stderr.strip() or f"curl exit {completed.returncode}"
            raise BrazilPNCPError(f"request failed: {url}: {detail}")
        metadata = completed.stdout.splitlines()
        if not metadata or len(metadata) > 2 or not metadata[0].isdigit():
            raise BrazilPNCPError(f"invalid curl response metadata: {url}")
        content_type = metadata[1] if len(metadata) == 2 else ""
        return int(metadata[0]), content_type, output.read_bytes()


def capture_live_sources(
    capture_directory: Path,
    *,
    timeout: float = 120.0,
    max_attempts: int = MAX_ATTEMPTS_PER_REQUEST,
    pacing_seconds: float = MIN_REQUEST_INTERVAL_SECONDS,
) -> Path:
    if max_attempts < 1 or max_attempts > MAX_ATTEMPTS_PER_REQUEST:
        raise BrazilPNCPError("max attempts outside bounded policy")
    if pacing_seconds < MIN_REQUEST_INTERVAL_SECONDS:
        raise BrazilPNCPError("pacing below bounded policy")
    raw = capture_directory / "raw"
    requests_plan = [
        ("pncp-frontend", PNCP_FRONTEND_URL),
        *((QUERY_IDS[term], query_url(term)) for term in QUERY_TERMS),
        ("dou-robots", DOU_ROBOTS_URL),
        ("dou-open-data", DOU_OPEN_DATA_URL),
        ("inlabs", INLABS_URL),
        ("pncp-law", PNCP_LAW_URL),
        ("open-data-decree", OPEN_DATA_DECREE_URL),
    ]
    if len(requests_plan) > MAX_NETWORK_REQUESTS:
        raise BrazilPNCPError("request plan exceeds cap")
    expected_raw_names = {f"{request_id}.bin" for request_id, _ in requests_plan}
    if capture_directory.exists():
        if (capture_directory / "capture.json").exists() or not raw.is_dir():
            raise BrazilPNCPError("capture directory is not a resumable partial capture")
        existing_names = {path.name for path in raw.iterdir() if path.is_file()}
        if existing_names - expected_raw_names or any(path.is_dir() for path in raw.iterdir()):
            raise BrazilPNCPError("unexpected artifact in partial capture")
    else:
        raw.mkdir(parents=True)
    capture_directory.chmod(0o700)
    raw.chmod(0o700)
    rows: list[dict[str, Any]] = []
    resumed_body_count = 0
    network_requests_this_invocation = 0
    for index, (request_id, url) in enumerate(requests_plan):
        body_file = f"raw/{request_id}.bin"
        path = capture_directory / body_file
        resumed = path.is_file()
        if resumed:
            body = path.read_bytes()
            if not body:
                raise BrazilPNCPError(f"empty partial body cannot be resumed: {request_id}")
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(
                timespec="seconds"
            ).replace("+00:00", "Z")
            started_at = modified
            finished_at = modified
            status = 200
            if request_id.startswith("q"):
                content_type = "application/json"
            elif request_id == "dou-robots":
                content_type = ""
            else:
                content_type = "text/html"
            resumed_body_count += 1
        else:
            if index:
                time.sleep(pacing_seconds)
            started = datetime.now(UTC)
            status, content_type, body = _capture_request(
                url, timeout=timeout, max_attempts=max_attempts
            )
            path.write_bytes(body)
            path.chmod(0o600)
            started_at = started.isoformat(timespec="seconds").replace("+00:00", "Z")
            finished_at = datetime.now(UTC).isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            )
            network_requests_this_invocation += 1
        rows.append(
            {
                "body_file": body_file,
                "bytes": len(body),
                "content_type": content_type,
                "finished_at": finished_at,
                "request_id": request_id,
                "resumed_from_prior_successful_body": resumed,
                "sha256": sha256_bytes(body),
                "started_at": started_at,
                "status": status,
                "url": url,
            }
        )
    capture = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "format": CAPTURE_FORMAT,
        "network_request_count": len(rows),
        "network_requests_this_invocation": network_requests_this_invocation,
        "raw_bodies_released": False,
        "resumed_body_count": resumed_body_count,
        "requests": rows,
    }
    capture_path = capture_directory / "capture.json"
    capture_path.write_bytes(canonical_json(capture))
    capture_path.chmod(0o600)
    # Parse and validate before the caller can use this capture for a release.
    loaded, bodies = load_capture(capture_directory)
    _rights_evidence(loaded, bodies)
    build_rows(loaded, bodies)
    return capture_directory
