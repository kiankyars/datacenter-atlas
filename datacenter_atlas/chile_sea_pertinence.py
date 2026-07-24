"""Restricted Chile SEA e-Pertinencia data-centre search assessment.

This lane preserves sanitized listing metadata from four closed search terms.
SEA process state never establishes a facility's physical lifecycle, identity,
operation, workload, power, energy use, or PUE.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable


SCHEMA_VERSION = 1
RELEASE_ID = "chile-sea-pertinence-data-centers-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-chile-sea-pertinence-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-chile-sea-pertinence-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-chile-sea-pertinence-assessment-v1"
SNAPSHOT_FORMAT = "datacenter-atlas-chile-sea-sanitized-search-snapshot-v1"
INVENTORY_FORMAT = "datacenter-atlas-chile-sea-pertinence-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-chile-sea-pertinence-schema-v1"

SEARCH_UI_URL = "https://pertinencia.sea.gob.cl/api/public/buscador"
SEARCH_API_URL = "https://pertinencia.sea.gob.cl/api/public/buscarCp"
DETAIL_URL_TEMPLATE = (
    "https://pertinencia.sea.gob.cl/api/proceso/obtener-pertinencia/{correlative_id}"
)
PRIVACY_URL = "https://www.sea.gob.cl/politicas-privacidad"
TERMS_URL = "https://www.sea.gob.cl/terminos-y-condiciones"

QUERY_TERMS = ("data center", "data centre", "datacenter", "centro de datos")
EXPECTED_HITS_BY_TERM = {
    "data center": 23,
    "data centre": 0,
    "datacenter": 4,
    "centro de datos": 1,
}
EXPECTED_RAW_HITS = 28
EXPECTED_UNIQUE_ROWS = 28
EXPECTED_REVIEW_CANDIDATES = 23
EXPECTED_TERMINAL_EXCLUSIONS = 5
EXPECTED_SUCCESSFUL_REQUESTS = 6
EXPECTED_CURRENT_ANALYSIS_IDS = {
    "PERTI-2025-9340",
    "PERTI-2026-5962",
    "PERTI-2026-7066",
}
TERMINAL_SUBSTATUS_COUNTS = {
    "Resuelta - Abandono": 4,
    "Resuelta - Desistida": 1,
}

MAX_NETWORK_REQUESTS = 10
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_ATTEMPTS_PER_REQUEST = 3

ALLOWED_LISTING_FIELDS = (
    "qidProcess",
    "name",
    "presentationDate",
    "dateResponse",
    "correlativeId",
    "projectType",
    "state",
    "subEstado",
    "primaryTypologyName",
    "regiones",
    "comunas",
)
EXPECTED_UPSTREAM_FIELDS = set(ALLOWED_LISTING_FIELDS) | {"titularName"}
PERSONAL_FIELD_NAMES = {
    "titularName",
    "email",
    "correo",
    "telefono",
    "phone",
    "contact",
    "contacto",
    "direccion",
    "address",
    "rut",
}

RIGHTS_POLICY = {
    "commercial_redistribution_permission_required": True,
    "general_terms_url": TERMS_URL,
    "legal_conclusion_claimed": False,
    "master_or_ledger_import_permitted": False,
    "privacy_policy_url": PRIVACY_URL,
    "publication_eligible": False,
    "rights_pages_retained_for_audit_only": True,
    "sanitized_listing_metadata_retained_for_audit_only": True,
    "source_terms_allow_personal_noncommercial_copying_subject_to_conditions": True,
    "third_party_material_may_have_separate_rights": True,
    "verified_local_date": "2026-07-18",
    "written_permission_required_for_commercial_copying_or_reuse": True,
}

INFERENCE_POLICY = {
    "annual_energy_mwh": None,
    "atlas_facility_identity": None,
    "atlas_lifecycle_status": None,
    "construction_verified": False,
    "data_centre_type": None,
    "gross_facility_power_mw": None,
    "identity_merge_performed": False,
    "it_capacity_mw": None,
    "operation_verified": False,
    "process_status_is_physical_lifecycle": False,
    "pue": None,
    "review_only": True,
    "unique_physical_site_count": None,
    "workload_type": None,
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "definition.json",
    "retrieval-inventory.json",
    "schema.json",
    "search-inventory.jsonl",
    "source-inventory.json",
}


class ChileSEAPertinenceError(ValueError):
    """Raised when the closed source or release contract changes."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(dict(row)) for row in rows)


def search_payload(term: str) -> dict[str, Any]:
    if term not in QUERY_TERMS:
        raise ChileSEAPertinenceError("search term is outside the closed query set")
    return {
        "pertinenciaFilter": {
            "estado": "",
            "fechaPresentacionDesde": "",
            "fechaPresentacionHasta": "",
            "fechaRespuestaDesde": "",
            "fechaRespuestaHasta": "",
            "id": "",
            "idLocalidades": [],
            "idTipologias": [],
            "nombre": term,
            "tipoProyecto": "",
            "titular": "",
            "regiones": [],
            "comunas": [],
        }
    }


def search_payload_bytes(term: str) -> bytes:
    return json.dumps(
        search_payload(term), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ChileSEAPertinenceError(f"listing field {field} changed type or is empty")
    return value


def _coded_label(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"id", "valor"}:
        raise ChileSEAPertinenceError(f"listing field {field} changed schema")
    return {
        "id": _text(value["id"], f"{field}.id", allow_empty=True),
        "valor": _text(value["valor"], f"{field}.valor"),
    }


def _places(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ChileSEAPertinenceError(f"listing field {field} changed schema")
    places: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"codigo", "nombre", "orden"}:
            raise ChileSEAPertinenceError(f"listing field {field} changed schema")
        places.append(
            {
                "codigo": _text(item["codigo"], f"{field}.codigo"),
                "nombre": _text(item["nombre"], f"{field}.nombre"),
                "orden": _text(item["orden"], f"{field}.orden"),
            }
        )
    return places


def sanitize_search_response(body: bytes, *, term: str) -> list[dict[str, Any]]:
    """Parse a listing response and immediately discard the upstream holder field."""

    if term not in QUERY_TERMS:
        raise ChileSEAPertinenceError("search term is outside the closed query set")
    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChileSEAPertinenceError("search response is not valid UTF-8 JSON") from error
    if not isinstance(decoded, list):
        raise ChileSEAPertinenceError("search response is not a list")
    if len(decoded) != EXPECTED_HITS_BY_TERM[term]:
        raise ChileSEAPertinenceError(f"search hit arithmetic changed for {term!r}")
    sanitized: list[dict[str, Any]] = []
    for upstream in decoded:
        if not isinstance(upstream, dict) or set(upstream) != EXPECTED_UPSTREAM_FIELDS:
            raise ChileSEAPertinenceError("upstream listing row schema changed")
        # Remove the only upstream holder field before constructing any retained row.
        upstream.pop("titularName")
        qid = _text(upstream["qidProcess"], "qidProcess")
        correlative = _text(upstream["correlativeId"], "correlativeId")
        if re.fullmatch(r"PERTI-\d{4}-\d+", correlative) is None:
            raise ChileSEAPertinenceError("correlativeId format changed")
        sanitized.append(
            {
                "comunas": _places(upstream["comunas"], "comunas"),
                "correlativeId": correlative,
                "dateResponse": _text(
                    upstream["dateResponse"], "dateResponse", allow_empty=True
                ),
                "name": _text(upstream["name"], "name"),
                "presentationDate": _text(
                    upstream["presentationDate"], "presentationDate"
                ),
                "primaryTypologyName": _text(
                    upstream["primaryTypologyName"],
                    "primaryTypologyName",
                    allow_empty=True,
                ),
                "projectType": _coded_label(upstream["projectType"], "projectType"),
                "qidProcess": qid,
                "regiones": _places(upstream["regiones"], "regiones"),
                "state": _coded_label(upstream["state"], "state"),
                "subEstado": (
                    None
                    if upstream["subEstado"] is None
                    else _text(upstream["subEstado"], "subEstado")
                ),
            }
        )
    return sanitized


def _assert_no_personal_fields(value: Any, *, context: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in PERSONAL_FIELD_NAMES:
                raise ChileSEAPertinenceError(f"personal field retained in {context}")
            _assert_no_personal_fields(child, context=context)
    elif isinstance(value, list):
        for child in value:
            _assert_no_personal_fields(child, context=context)


def make_sanitized_snapshot(
    query_captures: Iterable[Mapping[str, Any]], *, captured_at: str
) -> dict[str, Any]:
    captures = [dict(item) for item in query_captures]
    if [item.get("query_term") for item in captures] != list(QUERY_TERMS):
        raise ChileSEAPertinenceError("sanitized snapshot query order changed")
    queries: list[dict[str, Any]] = []
    for item in captures:
        term = item["query_term"]
        rows = item.get("rows")
        if not isinstance(rows, list) or len(rows) != EXPECTED_HITS_BY_TERM[term]:
            raise ChileSEAPertinenceError("sanitized query row count changed")
        queries.append(
            {
                "original_response_bytes": item["original_response_bytes"],
                "original_response_sha256": item["original_response_sha256"],
                "query_term": term,
                "rows": rows,
            }
        )
    snapshot = {
        "captured_at": captured_at,
        "format": SNAPSHOT_FORMAT,
        "queries": queries,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }
    _assert_no_personal_fields(snapshot, context="sanitized snapshot")
    return snapshot


def classify_snapshot(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Deduplicate the exact queries and add an explicit review decision per row."""

    if (
        snapshot.get("format") != SNAPSHOT_FORMAT
        or snapshot.get("release_id") != RELEASE_ID
        or snapshot.get("schema_version") != SCHEMA_VERSION
    ):
        raise ChileSEAPertinenceError("sanitized snapshot identity changed")
    queries = snapshot.get("queries")
    if not isinstance(queries, list) or [row.get("query_term") for row in queries] != list(
        QUERY_TERMS
    ):
        raise ChileSEAPertinenceError("sanitized snapshot query set changed")
    by_qid: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    raw_hits = 0
    for query in queries:
        term = query["query_term"]
        rows = query.get("rows")
        if not isinstance(rows, list) or len(rows) != EXPECTED_HITS_BY_TERM[term]:
            raise ChileSEAPertinenceError("sanitized snapshot hit arithmetic changed")
        raw_hits += len(rows)
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != set(ALLOWED_LISTING_FIELDS):
                raise ChileSEAPertinenceError("sanitized listing row schema changed")
            qid = row["qidProcess"]
            if qid not in by_qid:
                by_qid[qid] = dict(row) | {"query_terms": [term]}
                order.append(qid)
            else:
                existing = {key: value for key, value in by_qid[qid].items() if key != "query_terms"}
                if existing != dict(row):
                    raise ChileSEAPertinenceError("duplicate qidProcess metadata conflicts")
                by_qid[qid]["query_terms"].append(term)
    if raw_hits != EXPECTED_RAW_HITS or len(by_qid) != EXPECTED_UNIQUE_ROWS:
        raise ChileSEAPertinenceError("raw or unique search arithmetic changed")

    inventory: list[dict[str, Any]] = []
    for position, qid in enumerate(order, start=1):
        row = by_qid[qid]
        substatus = row["subEstado"]
        terminal = substatus in TERMINAL_SUBSTATUS_COUNTS
        classification = "terminal_process_exclusion" if terminal else "review_candidate"
        if terminal:
            reason = (
                f"SEA e-Pertinencia process substatus is {substatus}; retain the row "
                "as a terminal-process exclusion without a physical-lifecycle inference."
            )
        else:
            reason = (
                "Official listing metadata matches a closed data-centre query; process "
                "metadata alone does not establish facility identity or physical lifecycle."
            )
        inventory.append(
            {
                "atlas_inference": INFERENCE_POLICY,
                "classification": classification,
                "comunas": row["comunas"],
                "correlative_id": row["correlativeId"],
                "date_response_exact": row["dateResponse"],
                "name_exact": row["name"],
                "observation_id": f"cl-sea-pertinence-{row['correlativeId'].lower()}",
                "presentation_date_exact": row["presentationDate"],
                "primary_typology_name_exact": row["primaryTypologyName"],
                "process_state_exact": row["state"]["valor"],
                "process_status_is_physical_lifecycle": False,
                "process_substatus_exact": substatus,
                "project_type_exact": row["projectType"]["valor"],
                "qid_process": qid,
                "query_terms": row["query_terms"],
                "record_type": "chile_sea_pertinence_listing_observation",
                "regiones": row["regiones"],
                "result_position": position,
                "review_only": True,
                "review_reason": reason,
                "source": {
                    "detail_fetched": False,
                    "publisher": "Servicio de Evaluación Ambiental de Chile",
                    "search_api_url": SEARCH_API_URL,
                    "search_ui_url": SEARCH_UI_URL,
                },
                "unique_physical_site_id": None,
            }
        )
    counts = Counter(row["classification"] for row in inventory)
    if counts != Counter(
        {
            "review_candidate": EXPECTED_REVIEW_CANDIDATES,
            "terminal_process_exclusion": EXPECTED_TERMINAL_EXCLUSIONS,
        }
    ):
        raise ChileSEAPertinenceError("classification arithmetic changed")
    terminal_counts = Counter(
        row["process_substatus_exact"]
        for row in inventory
        if row["classification"] == "terminal_process_exclusion"
    )
    if terminal_counts != Counter(TERMINAL_SUBSTATUS_COUNTS):
        raise ChileSEAPertinenceError("terminal substatus arithmetic changed")
    analysis_ids = {
        row["correlative_id"]
        for row in inventory
        if row["process_state_exact"] == "En análisis"
    }
    if analysis_ids != EXPECTED_CURRENT_ANALYSIS_IDS:
        raise ChileSEAPertinenceError("current En análisis closed set changed")
    _assert_no_personal_fields(inventory, context="classified inventory")
    return inventory


def source_definition() -> dict[str, Any]:
    return {
        "coverage": {
            "complete_for_chile": False,
            "geography": "Chile",
            "scope": "four exact SEA e-Pertinencia public listing searches",
            "unique_physical_site_count": None,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "network_policy": {
            "backoff_seconds_by_retry": [2, 4],
            "expected_successful_requests": EXPECTED_SUCCESSFUL_REQUESTS,
            "maximum_attempts_per_request": MAX_ATTEMPTS_PER_REQUEST,
            "maximum_network_requests_per_run": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
        },
        "publisher": "Servicio de Evaluación Ambiental de Chile",
        "query": {
            "expected_hits_by_term": EXPECTED_HITS_BY_TERM,
            "http_method": "POST",
            "search_api_url": SEARCH_API_URL,
            "search_terms_in_order": list(QUERY_TERMS),
            "search_ui_url": SEARCH_UI_URL,
        },
        "release_id": RELEASE_ID,
        "retention": {
            "applicant_documents_fetched": False,
            "comments_fetched": False,
            "contact_or_personal_fields_retained": False,
            "detail_endpoints_fetched": False,
            "images_or_plans_fetched": False,
            "original_search_response_bodies_retained": False,
            "rights_page_html_retained_for_audit_only": True,
            "sanitized_listing_metadata_retained_for_audit_only": True,
            "third_party_material_fetched": False,
        },
        "rights": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_id": "chile-sea-pertinence-data-centers",
        "source_urls": {
            "privacy": PRIVACY_URL,
            "search_api": SEARCH_API_URL,
            "search_ui": SEARCH_UI_URL,
            "terms": TERMS_URL,
        },
        "title": "Chile SEA e-Pertinencia data-centre listing observations",
    }


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ChileSEAPertinenceError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChileSEAPertinenceError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChileSEAPertinenceError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_snapshot(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChileSEAPertinenceError("sanitized snapshot is not valid JSON") from error
    if not isinstance(value, dict) or canonical_json(value) != body:
        raise ChileSEAPertinenceError("sanitized snapshot is not canonical JSON")
    _assert_no_personal_fields(value, context="sanitized snapshot")
    classify_snapshot(value)
    return value


def _validate_capture(
    capture: Mapping[str, Any], retained_bodies: Mapping[str, bytes]
) -> dict[str, Any]:
    if capture.get("release_id") != RELEASE_ID:
        raise ChileSEAPertinenceError("capture release id changed")
    captured_at = _timestamp(capture.get("captured_at"), "captured_at")
    started_at = _timestamp(capture.get("batch_started_at"), "batch_started_at")
    if capture.get("minimum_request_interval_seconds") < MIN_REQUEST_INTERVAL_SECONDS:
        raise ChileSEAPertinenceError("capture pacing fell below one second")
    if capture.get("maximum_network_requests") != MAX_NETWORK_REQUESTS:
        raise ChileSEAPertinenceError("capture request cap changed")
    if capture.get("maximum_attempts_per_request") != MAX_ATTEMPTS_PER_REQUEST:
        raise ChileSEAPertinenceError("capture retry contract changed")
    if capture.get("successful_requests") != EXPECTED_SUCCESSFUL_REQUESTS:
        raise ChileSEAPertinenceError("successful request arithmetic changed")
    requests = capture.get("network_requests")
    if not isinstance(requests, int) or not EXPECTED_SUCCESSFUL_REQUESTS <= requests <= MAX_NETWORK_REQUESTS:
        raise ChileSEAPertinenceError("network request arithmetic is invalid")
    retrievals = capture.get("retrievals")
    expected_keys = {f"search_{index}" for index in range(1, 5)} | {"privacy", "terms"}
    if not isinstance(retrievals, Mapping) or set(retrievals) != expected_keys:
        raise ChileSEAPertinenceError("capture retrieval set changed")

    snapshot_filename = capture.get("sanitized_snapshot_filename")
    if snapshot_filename != "sanitized-search-snapshot.json":
        raise ChileSEAPertinenceError("sanitized snapshot filename changed")
    expected_retained = {
        snapshot_filename,
        "raw/sea-privacy.html",
        "raw/sea-terms.html",
    }
    if set(retained_bodies) != expected_retained:
        raise ChileSEAPertinenceError("retained capture artifact set changed")
    snapshot = _load_snapshot(retained_bodies[snapshot_filename])

    for index, term in enumerate(QUERY_TERMS, start=1):
        retrieval = retrievals[f"search_{index}"]
        query = snapshot["queries"][index - 1]
        if (
            retrieval.get("method") != "POST"
            or retrieval.get("url") != SEARCH_API_URL
            or retrieval.get("query_term") != term
            or retrieval.get("request_body_sha256") != sha256_bytes(search_payload_bytes(term))
            or retrieval.get("bytes") != query["original_response_bytes"]
            or retrieval.get("sha256") != query["original_response_sha256"]
            or retrieval.get("sanitized_snapshot_filename") != snapshot_filename
        ):
            raise ChileSEAPertinenceError("search retrieval contract changed")
        if "filename" in retrieval:
            raise ChileSEAPertinenceError("original search response body was retained")
    for key, url, filename in (
        ("privacy", PRIVACY_URL, "raw/sea-privacy.html"),
        ("terms", TERMS_URL, "raw/sea-terms.html"),
    ):
        retrieval = retrievals[key]
        body = retained_bodies[filename]
        if (
            retrieval.get("method") != "GET"
            or retrieval.get("url") != url
            or retrieval.get("filename") != filename
            or retrieval.get("bytes") != len(body)
            or retrieval.get("sha256") != sha256_bytes(body)
        ):
            raise ChileSEAPertinenceError("rights retrieval contract changed")
    if snapshot["captured_at"] != captured_at:
        raise ChileSEAPertinenceError("snapshot capture time changed")
    inventory = classify_snapshot(snapshot)
    return {
        "captured_at": captured_at,
        "started_at": started_at,
        "inventory": inventory,
        "snapshot": snapshot,
    }


def derive_release_files(
    capture: Mapping[str, Any], retained_bodies: Mapping[str, bytes]
) -> dict[str, bytes]:
    """Reproduce all derived release files from sanitized retained artifacts."""

    validated = _validate_capture(capture, retained_bodies)
    inventory = validated["inventory"]
    state_counts = Counter(row["process_state_exact"] for row in inventory)
    substatus_counts = Counter(
        row["process_substatus_exact"]
        for row in inventory
        if row["process_substatus_exact"] is not None
    )
    original_search_bytes = sum(
        query["original_response_bytes"] for query in validated["snapshot"]["queries"]
    )
    attempts_requiring_retry = sum(
        int(row.get("attempt", 1)) - 1 for row in capture["retrievals"].values()
    )
    assessment = {
        "assessed_at": validated["captured_at"],
        "atlas_decision": {
            "master_or_ledger_import_permitted": False,
            "publication_eligible": False,
            "status": "restricted_official_source_audit_index_only",
            "unique_site_count_published": False,
        },
        "coverage_assessment": {
            "construction_evidence_rows": 0,
            "current_en_analisis_rows": 3,
            "operation_evidence_rows": 0,
            "raw_query_hits": EXPECTED_RAW_HITS,
            "review_candidate_rows": EXPECTED_REVIEW_CANDIDATES,
            "terminal_process_exclusion_rows": EXPECTED_TERMINAL_EXCLUSIONS,
            "unique_listing_rows": EXPECTED_UNIQUE_ROWS,
            "unique_physical_site_count": None,
        },
        "format": ASSESSMENT_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "process_state_counts": dict(sorted(state_counts.items())),
        "process_substatus_counts": dict(sorted(substatus_counts.items())),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "attempts_requiring_retry": attempts_requiring_retry,
            "batch_completed_at": validated["captured_at"],
            "batch_started_at": validated["started_at"],
            "detail_requests": 0,
            "maximum_request_cap": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "network_requests": capture["network_requests"],
            "original_search_response_bodies_retained": False,
            "original_search_response_bytes": original_search_bytes,
            "rights_page_requests": 2,
            "search_requests": 4,
            "successful_requests": EXPECTED_SUCCESSFUL_REQUESTS,
            "validator_network_requests": 0,
        },
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "selection_assessment": {
            "query_hits_by_term": EXPECTED_HITS_BY_TERM,
            "raw_query_hits": EXPECTED_RAW_HITS,
            "review_candidate_rows": EXPECTED_REVIEW_CANDIDATES,
            "terminal_process_exclusion_rows": EXPECTED_TERMINAL_EXCLUSIONS,
            "terminal_substatus_counts": TERMINAL_SUBSTATUS_COUNTS,
            "unique_qid_process_rows": EXPECTED_UNIQUE_ROWS,
        },
        "source_definition": source_definition(),
    }
    artifacts = []
    for filename in sorted(retained_bodies):
        body = retained_bodies[filename]
        artifacts.append(
            {
                "bytes": len(body),
                "filename": filename,
                "retention": (
                    "sanitized_metadata_audit_only"
                    if filename == "sanitized-search-snapshot.json"
                    else "official_rights_page_html_audit_only"
                ),
                "sha256": sha256_bytes(body),
            }
        )
    source_inventory = {
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "format": INVENTORY_FORMAT,
        "original_search_response_bodies_retained": False,
        "original_search_responses": [
            {
                "bytes": query["original_response_bytes"],
                "query_term": query["query_term"],
                "sha256": query["original_response_sha256"],
            }
            for query in validated["snapshot"]["queries"]
        ],
        "release_id": RELEASE_ID,
    }
    schema = {
        "field_semantics": {
            "classification": "review candidate or terminal process exclusion; neither value is physical lifecycle",
            "process_state_exact": "SEA e-Pertinencia process metadata only",
            "process_substatus_exact": "SEA e-Pertinencia process substatus only",
            "query_terms": "closed search terms that returned the listing row",
            "unique_physical_site_id": "always null because the lane performs no identity merge",
        },
        "format": SCHEMA_FORMAT,
        "inference_policy": INFERENCE_POLICY,
        "privacy_boundary": "upstream holder names and personal or contact fields are omitted",
        "record_type": "chile_sea_pertinence_listing_observation",
        "schema_version": SCHEMA_VERSION,
    }
    attribution = (
        "Chile SEA e-Pertinencia data-centre listing assessment\n"
        "Source: Servicio de Evaluación Ambiental de Chile\n"
        f"Search interface: {SEARCH_UI_URL}\n"
        f"Privacy policy: {PRIVACY_URL}\n"
        f"Terms and conditions: {TERMS_URL}\n\n"
        "SEA permits copying under stated personal, noncommercial conditions and "
        "requires written permission for commercial copying or reuse. This release "
        "therefore keeps sanitized metadata and rights pages for internal audit only. "
        "It excludes holder names, personal/contact fields, original listing bodies, "
        "detail pages, applicant documents, attachments, plans, comments, and images.\n"
    ).encode("utf-8")
    readme = (
        "# Chile SEA e-Pertinencia data-centre listing assessment\n\n"
        "Four closed listing searches returned 28 rows: 23 review candidates and five "
        "terminal-process exclusions. Four exclusions have substatus `Resuelta - "
        "Abandono`; one has `Resuelta - Desistida`. Three rows have current process "
        "state `En análisis`: PERTI-2026-7066, PERTI-2026-5962, and PERTI-2025-9340.\n\n"
        "SEA process metadata does not establish construction, operation, site identity, "
        "data-centre type, workload, power, energy use, or PUE. The lane performs no "
        "identity merge and leaves unique physical site count null.\n\n"
        "The capture made four listing POST requests and two rights-page GET requests. "
        "It discarded holder names and original listing bodies before writing capture "
        "artifacts. The retained listing snapshot contains only the approved metadata "
        "fields. No detail endpoint, attachment, applicant document, comment, plan, or "
        "image was requested.\n\n"
        "SEA's terms make this release restricted and audit-only. It cannot feed the "
        "construction master or current coverage ledger without rights clearance.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": readme,
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(source_definition()),
        "retrieval-inventory.json": canonical_json(dict(capture)),
        "schema.json": canonical_json(schema),
        "search-inventory.jsonl": _jsonl(inventory),
        "source-inventory.json": canonical_json(source_inventory),
    }


def _artifact_role(filename: str) -> str:
    if filename == "sanitized-search-snapshot.json":
        return "sanitized_listing_metadata_internal_audit_only"
    if filename.startswith("raw/"):
        return "official_rights_page_internal_audit_evidence"
    if filename == "search-inventory.jsonl":
        return "complete_classified_listing_inventory_internal_audit_only"
    return "restricted_release_metadata"


def _manifest_for_directory(path: Path, assessed_at: str) -> bytes:
    files: dict[str, dict[str, Any]] = {}
    for entry in sorted(path.rglob("*")):
        if not entry.is_file():
            continue
        relative = entry.relative_to(path).as_posix()
        if relative in {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}:
            continue
        body = entry.read_bytes()
        files[relative] = {
            "bytes": len(body),
            "license_scope": "restricted_internal_audit_only_not_publication_eligible",
            "role": _artifact_role(relative),
            "sha256": sha256_bytes(body),
        }
    return canonical_json(
        {
            "assessed_at": assessed_at,
            "files": files,
            "format": RELEASE_FORMAT,
            "release_id": RELEASE_ID,
            "schema_version": SCHEMA_VERSION,
        }
    )


def _freeze_tree(path: Path) -> None:
    for entry in path.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    path.chmod(0o555)


def write_release_bundle(
    output: str | Path,
    capture: Mapping[str, Any],
    retained_bodies: Mapping[str, bytes],
    *,
    freeze: bool = True,
) -> Path:
    """Write a frozen release atomically without overwriting an existing path."""

    output_path = Path(output)
    if output_path.exists() or output_path.is_symlink():
        raise ChileSEAPertinenceError("output release already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validated = _validate_capture(capture, retained_bodies)
    derived = derive_release_files(capture, retained_bodies)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    )
    try:
        for filename, body in retained_bodies.items():
            destination = temporary / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        for filename, body in derived.items():
            destination = temporary / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
        manifest = _manifest_for_directory(temporary, validated["captured_at"])
        (temporary / MANIFEST_FILENAME).write_bytes(manifest)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n", encoding="utf-8"
        )
        os.replace(temporary, output_path)
        if freeze:
            _freeze_tree(output_path)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_path


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChileSEAPertinenceError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise ChileSEAPertinenceError(f"{label} is not canonical JSON")
    return value


def _load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ChileSEAPertinenceError(f"{label} is not valid JSONL") from error
    if any(not isinstance(row, dict) for row in rows) or path.read_bytes() != _jsonl(rows):
        raise ChileSEAPertinenceError(f"{label} is not canonical JSONL")
    return rows


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    """Validate and reproduce the restricted release without network access."""

    release = Path(path)
    if not release.is_dir() or release.is_symlink():
        raise ChileSEAPertinenceError("release must be a non-symlink directory")
    if any(entry.is_symlink() for entry in release.rglob("*")):
        raise ChileSEAPertinenceError("release cannot contain symlinks")
    capture = _load_canonical_json(
        release / "retrieval-inventory.json", "retrieval inventory"
    )
    retained_names = {
        capture.get("sanitized_snapshot_filename"),
        capture.get("retrievals", {}).get("privacy", {}).get("filename"),
        capture.get("retrievals", {}).get("terms", {}).get("filename"),
    }
    if any(not isinstance(name, str) for name in retained_names):
        raise ChileSEAPertinenceError("retained capture filename inventory is invalid")
    expected_files = retained_names | DERIVED_FILENAMES | {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    actual_files = {
        entry.relative_to(release).as_posix()
        for entry in release.rglob("*")
        if entry.is_file()
    }
    if actual_files != expected_files:
        raise ChileSEAPertinenceError("release file set changed")
    retained_bodies = {name: (release / name).read_bytes() for name in retained_names}
    validated = _validate_capture(capture, retained_bodies)

    manifest = _load_canonical_json(release / MANIFEST_FILENAME, "manifest")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("assessed_at") != validated["captured_at"]
    ):
        raise ChileSEAPertinenceError("manifest identity changed")
    expected_manifest = _manifest_for_directory(release, validated["captured_at"])
    if (release / MANIFEST_FILENAME).read_bytes() != expected_manifest:
        raise ChileSEAPertinenceError("manifest does not bind the release files")
    expected_sidecar = (
        f"{sha256_bytes(expected_manifest)}  {MANIFEST_FILENAME}\n".encode("utf-8")
    )
    if (release / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise ChileSEAPertinenceError("manifest SHA-256 sidecar changed")

    reproduced = derive_release_files(capture, retained_bodies)
    for filename, expected in reproduced.items():
        if (release / filename).read_bytes() != expected:
            raise ChileSEAPertinenceError(f"offline reproduction mismatch: {filename}")
    assessment = _load_canonical_json(release / "assessment.json", "assessment")
    if assessment.get("rights_assessment") != RIGHTS_POLICY:
        raise ChileSEAPertinenceError("rights boundary changed")
    if assessment.get("inference_policy") != INFERENCE_POLICY:
        raise ChileSEAPertinenceError("inference boundary changed")
    inventory = _load_jsonl(release / "search-inventory.jsonl", "search inventory")
    _assert_no_personal_fields(inventory, context="search inventory")
    return {
        "assessment": assessment,
        "definition": _load_canonical_json(release / "definition.json", "definition"),
        "manifest": manifest,
        "schema": _load_canonical_json(release / "schema.json", "schema"),
        "search_inventory": inventory,
        "source_inventory": _load_canonical_json(
            release / "source-inventory.json", "source inventory"
        ),
    }


def is_frozen_release(path: str | Path) -> bool:
    release = Path(path)
    if not release.is_dir() or release.stat().st_mode & 0o777 != 0o555:
        return False
    return all(
        entry.stat().st_mode & 0o777 == (0o555 if entry.is_dir() else 0o444)
        for entry in release.rglob("*")
    )


def thaw_for_test(path: str | Path) -> None:
    release = Path(path)
    release.chmod(stat.S_IRWXU)
    for entry in release.rglob("*"):
        entry.chmod(stat.S_IRWXU if entry.is_dir() else stat.S_IRUSR | stat.S_IWUSR)
