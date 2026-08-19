"""Resumable Wikidata discovery and conservative offline import.

The discovery boundary is deliberately mechanical and reviewable: an item is
included when the Wikidata Query Service exposes a truthy ``instance of``
statement whose class is the data-center class (Q671224) or one of its truthy
``subclass of`` descendants::

    ?item wdt:P31/wdt:P279* wd:Q671224

Wikidata's class graph is community-maintained and can contain products,
organizations, or other modelling mistakes.  A query match is consequently a
source-scoped candidate, not proof that the item is a physical facility and not
independent corroboration of any underlying claim.

The fetcher checkpoints the exact SPARQL and Action API responses.  Full entity
JSON retains statement IDs, ranks, qualifiers, and references.  The adapter
never infers lifecycle, data-center type, operating model, workload, or energy
from labels.  It maps only two narrowly defined structured fields:

* state of use (P5817) Q12377751 -> under construction;
* state of use (P5817) Q811683 -> proposed;
* power consumed (P2791), expressed in a recognized SI power unit (W, kW, MW,
  or GW), -> gross facility MW with unknown stage.  This is electrical power,
  not annual energy or critical IT load.

All other lifecycle values remain UNKNOWN.  Inception (P571), dissolution
(P576), owner (P127), operator (P137), country (P17), coordinates (P625), and
instance classes (P31) are retained as explicit source claims without further
inference.

Authoritative references:

* https://www.wikidata.org/entity/Q671224
* https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual
* https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
* https://www.wikidata.org/wiki/Wikidata:Licensing
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .adapters import ImportResult
from .models import (
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
)
from .repository import (
    add_capacity,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_snapshot,
    stable_id,
    utc_now,
)


WIKIDATA_ROOT_QID = "Q671224"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_API_ENDPOINT = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_DATA_URL = (
    "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json?revision={revision}"
)
WIKIDATA_LICENSE = "CC0-1.0"
WIKIDATA_SOURCE_FAMILY = "wikidata"
WIKIDATA_PUBLISHER = "Wikidata contributors / Wikimedia Foundation"
WIKIDATA_ATTRIBUTION = "Wikidata contributors"
WIKIDATA_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)
WIKIDATA_MANIFEST = "manifest.json"
WIKIDATA_SCHEMA_VERSION = 1
WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG = "wikidata:country_fallback_label"
WIKIDATA_COUNTRY_FALLBACK_QID_TAG = "wikidata:country_fallback_qid"
WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG = "wikidata:country_fallback_method"
WIKIDATA_COUNTRY_FALLBACK_METHOD = "wikidata_explicit_single_truthy_P17"

P_INSTANCE_OF = "P31"
P_COORDINATE = "P625"
P_OPERATOR = "P137"
P_OWNER = "P127"
P_COUNTRY = "P17"
P_INCEPTION = "P571"
P_DISSOLUTION = "P576"
P_STATE_OF_USE = "P5817"
P_POWER_CONSUMED = "P2791"
P_FLOOR_AREA = "P2046"

Q_UNDER_CONSTRUCTION = "Q12377751"
Q_PROPOSED = "Q811683"
Q_WATT = "Q25236"
Q_KILOWATT = "Q3320608"
Q_MEGAWATT = "Q6982035"
Q_GIGAWATT = "Q5879479"
EARTH_GLOBE = "http://www.wikidata.org/entity/Q2"

POWER_UNIT_TO_MW = {
    Q_WATT: Decimal("0.000001"),
    Q_KILOWATT: Decimal("0.001"),
    Q_MEGAWATT: Decimal("1"),
    Q_GIGAWATT: Decimal("1000"),
}

SELECTED_PROPERTIES = (
    P_INSTANCE_OF,
    P_COORDINATE,
    P_OPERATOR,
    P_OWNER,
    P_COUNTRY,
    P_INCEPTION,
    P_DISSOLUTION,
    P_STATE_OF_USE,
    P_POWER_CONSUMED,
    P_FLOOR_AREA,
)
LOOKUP_ENTITY_PROPERTIES = (
    P_INSTANCE_OF,
    P_OPERATOR,
    P_OWNER,
    P_COUNTRY,
    P_STATE_OF_USE,
)

CLASS_QUERY = """SELECT DISTINCT ?class WHERE {
  ?class wdt:P279* wd:Q671224 .
  FILTER(STRSTARTS(STR(?class), "http://www.wikidata.org/entity/Q"))
}
ORDER BY STR(?class)
"""

ITEM_QUERY = """SELECT DISTINCT ?item WHERE {
  ?item wdt:P31/wdt:P279* wd:Q671224 .
  FILTER(STRSTARTS(STR(?item), "http://www.wikidata.org/entity/Q"))
}
ORDER BY STR(?item)
"""

QUERY_SPECS = {
    "class_pages": ("queries/class-closure.rq", CLASS_QUERY, "class"),
    "item_pages": ("queries/items.rq", ITEM_QUERY, "item"),
}

TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_QID_PREFIX = "http://www.wikidata.org/entity/"


class WikidataBundleError(ValueError):
    """The cached bundle is incomplete, inconsistent, or tampered with."""


class WikidataFetchError(RuntimeError):
    """A live Wikidata request could not be completed safely."""


@dataclass(frozen=True, slots=True)
class BundleView:
    path: Path
    manifest: dict[str, Any]
    class_qids: tuple[str, ...]
    candidate_qids: tuple[str, ...]
    entities: dict[str, dict[str, Any]]
    lookup_entities: dict[str, dict[str, Any]]


@dataclass(frozen=True, slots=True)
class WikidataCandidate:
    qid: str
    entity: dict[str, Any]
    name: str | None
    description: str | None
    latitude: float | None
    longitude: float | None
    selected_claims: dict[str, list[dict[str, Any]]]
    content_hash: str
    raw_batch_file: str
    raw_batch_sha256: str
    fetched_at: str


@dataclass(frozen=True, slots=True)
class _Response:
    raw: bytes
    document: dict[str, Any]
    endpoint_metadata: dict[str, Any]


class _TransientFailure(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(raw)


def _write_bytes_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)


def _write_json_atomic(path: Path, document: Any) -> None:
    _write_bytes_atomic(
        path,
        (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _require_timestamp(value: Any, field: str) -> str:
    from datetime import datetime

    if not isinstance(value, str) or not value.strip():
        raise WikidataBundleError(f"{field} must be a non-empty ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WikidataBundleError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WikidataBundleError(f"{field} must include a timezone")
    return value


def _retrieval_date(timestamp: str) -> str:
    return _require_timestamp(timestamp, "retrieval timestamp")[:10]


def _require_qid(value: Any, field: str = "QID") -> str:
    if (
        not isinstance(value, str)
        or len(value) < 2
        or value[0] != "Q"
        or not value[1:].isdigit()
        or value[1] == "0"
    ):
        raise WikidataBundleError(f"{field} must be a canonical item QID")
    return value


def _qid_from_uri(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith(_QID_PREFIX):
        raise WikidataBundleError(f"{field} must be a Wikidata item URI")
    return _require_qid(value[len(_QID_PREFIX) :], field)


def _render_query(base_query: str, page_size: int, offset: int) -> str:
    return f"{base_query}LIMIT {page_size}\nOFFSET {offset}\n"


def _response_headers(response: Any) -> Mapping[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    try:
        return {str(key).lower(): str(value) for key, value in headers.items()}
    except AttributeError:
        return {}


def _endpoint_metadata(response: Any, requested_url: str) -> dict[str, Any]:
    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else 200
    final_url = getattr(response, "url", None)
    if final_url is None:
        geturl = getattr(response, "geturl", None)
        final_url = geturl() if callable(geturl) else requested_url
    headers = _response_headers(response)
    retained_headers = {
        key: headers[key]
        for key in (
            "content-type",
            "content-length",
            "date",
            "etag",
            "last-modified",
            "server",
        )
        if key in headers
    }
    return {
        "requested_url": requested_url,
        "final_url": str(final_url),
        "http_status": int(status or 200),
        "response_headers": retained_headers,
    }


def _json_object(raw: bytes, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WikidataBundleError(f"{field} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise WikidataBundleError(f"{field} must be a JSON object")
    return value


def _parse_sparql_page(
    document: dict[str, Any], variable: str, field: str
) -> list[str]:
    head = document.get("head")
    results = document.get("results")
    if not isinstance(head, dict) or head.get("vars") != [variable]:
        raise WikidataBundleError(f"{field} has unexpected SPARQL head")
    if not isinstance(results, dict) or not isinstance(results.get("bindings"), list):
        raise WikidataBundleError(f"{field} has unexpected SPARQL results")
    qids: list[str] = []
    for index, binding in enumerate(results["bindings"]):
        if not isinstance(binding, dict):
            raise WikidataBundleError(f"{field} binding {index} must be an object")
        value = binding.get(variable)
        if (
            not isinstance(value, dict)
            or value.get("type") != "uri"
            or "value" not in value
        ):
            raise WikidataBundleError(
                f"{field} binding {index} has an invalid {variable} value"
            )
        qids.append(_qid_from_uri(value["value"], f"{field} binding {index}"))
    if qids != sorted(qids, key=lambda qid: f"{_QID_PREFIX}{qid}"):
        raise WikidataBundleError(f"{field} is not ordered by item URI")
    if len(qids) != len(set(qids)):
        raise WikidataBundleError(f"{field} contains duplicate QIDs")
    return qids


def _parse_entity_response(
    document: dict[str, Any], expected_qids: Iterable[str], field: str
) -> dict[str, dict[str, Any]]:
    expected = tuple(expected_qids)
    entities = document.get("entities")
    if not isinstance(entities, dict):
        raise WikidataBundleError(f"{field} is missing its entities object")
    if set(entities) != set(expected):
        raise WikidataBundleError(f"{field} entity IDs do not match the request")
    parsed: dict[str, dict[str, Any]] = {}
    for qid in expected:
        entity = entities[qid]
        if not isinstance(entity, dict) or entity.get("id") != qid:
            raise WikidataBundleError(f"{field} has a malformed entity {qid}")
        if entity.get("missing") is not None:
            raise WikidataBundleError(f"{field} reports missing entity {qid}")
        entity_type = entity.get("type")
        if entity_type is not None and entity_type != "item":
            raise WikidataBundleError(f"{field} entity {qid} is not an item")
        parsed[qid] = entity
    return parsed


def _claim_qid(statement: Any) -> str | None:
    if not isinstance(statement, dict):
        return None
    snak = statement.get("mainsnak")
    if not isinstance(snak, dict) or snak.get("snaktype") != "value":
        return None
    datavalue = snak.get("datavalue")
    value = datavalue.get("value") if isinstance(datavalue, dict) else None
    if not isinstance(value, dict):
        return None
    qid = value.get("id")
    try:
        return _require_qid(qid) if qid is not None else None
    except WikidataBundleError:
        return None


def _truthy_statements(entity: dict[str, Any], property_id: str) -> list[dict[str, Any]]:
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        return []
    statements = claims.get(property_id, [])
    if not isinstance(statements, list):
        return []
    usable = [
        statement
        for statement in statements
        if isinstance(statement, dict)
        and statement.get("rank") in {"normal", "preferred"}
    ]
    preferred = [statement for statement in usable if statement.get("rank") == "preferred"]
    return preferred or [statement for statement in usable if statement.get("rank") == "normal"]


def _entity_revision(entity: dict[str, Any], qid: str) -> int:
    revision = entity.get("lastrevid")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
        raise WikidataBundleError(f"candidate {qid} is missing a positive lastrevid")
    return revision


def _all_selected_lookup_qids(
    class_qids: Iterable[str], entities: Mapping[str, dict[str, Any]]
) -> list[str]:
    result = set(class_qids)
    for entity in entities.values():
        for property_id in LOOKUP_ENTITY_PROPERTIES:
            for statement in _truthy_statements(entity, property_id):
                qid = _claim_qid(statement)
                if qid:
                    result.add(qid)
        for statement in _truthy_statements(entity, P_POWER_CONSUMED):
            snak = statement.get("mainsnak", {})
            datavalue = snak.get("datavalue", {})
            value = datavalue.get("value", {})
            unit = value.get("unit") if isinstance(value, dict) else None
            if isinstance(unit, str) and unit.startswith(_QID_PREFIX):
                try:
                    result.add(_qid_from_uri(unit, "quantity unit"))
                except WikidataBundleError:
                    pass
    result.difference_update(entities)
    return sorted(result, key=lambda qid: f"{_QID_PREFIX}{qid}")


def _new_manifest(
    *, page_size: int, batch_size: int, started_at: str
) -> dict[str, Any]:
    return {
        "schema_version": WIKIDATA_SCHEMA_VERSION,
        "state": "in_progress",
        "dataset": "Wikidata data-center candidate extraction",
        "source_family": WIKIDATA_SOURCE_FAMILY,
        "license": WIKIDATA_LICENSE,
        "root_class": {
            "qid": WIKIDATA_ROOT_QID,
            "url": f"https://www.wikidata.org/entity/{WIKIDATA_ROOT_QID}",
        },
        "selection_rule": "?item wdt:P31/wdt:P279* wd:Q671224",
        "independent_corroboration": False,
        "claim_independence_requires_reference_review": True,
        "retrieved_started_at": started_at,
        "retrieved_completed_at": None,
        "endpoints": {
            "sparql": WIKIDATA_SPARQL_ENDPOINT,
            "action_api": WIKIDATA_API_ENDPOINT,
            "documentation": [
                "https://www.mediawiki.org/wiki/Wikidata_Query_Service/User_Manual",
                "https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities",
                "https://www.wikidata.org/wiki/Wikidata:Licensing",
            ],
        },
        "queries": {
            lane: {
                "file": spec[0],
                "sha256": _sha256_bytes(spec[1].encode("utf-8")),
                "page_size": page_size,
            }
            for lane, spec in QUERY_SPECS.items()
        },
        "batch_size": batch_size,
        "class_pages": [],
        "item_pages": [],
        "candidate_qids": None,
        "entity_batches": [],
        "lookup_qids": None,
        "lookup_batches": [],
        "counts": {},
        "failure_history": [],
        "last_run": None,
        "limitations": [
            "WDQS and Action API responses are retrieved over a time window, not a transactional snapshot.",
            "Community ontology membership is a candidate signal and can include non-facility items.",
            "Wikidata references vary by statement; host identity does not establish claim independence.",
            "Labels never establish lifecycle, type, workload, or capacity.",
        ],
    }


def _batch_chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _validate_query_files(bundle: Path, manifest: dict[str, Any]) -> None:
    queries = manifest.get("queries")
    if not isinstance(queries, dict) or set(queries) != set(QUERY_SPECS):
        raise WikidataBundleError("manifest query definitions are incomplete")
    for lane, (relative, expected_text, _variable) in QUERY_SPECS.items():
        checkpoint = queries[lane]
        if not isinstance(checkpoint, dict):
            raise WikidataBundleError(f"manifest {lane} query checkpoint is invalid")
        expected_hash = _sha256_bytes(expected_text.encode("utf-8"))
        if checkpoint.get("file") != relative or checkpoint.get("sha256") != expected_hash:
            raise WikidataBundleError(f"manifest {lane} query does not match the adapter")
        page_size = checkpoint.get("page_size")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            raise WikidataBundleError(f"manifest {lane} page size is invalid")
        query_path = bundle / relative
        if not query_path.is_file() or query_path.read_text(encoding="utf-8") != expected_text:
            raise WikidataBundleError(f"cached {lane} query text does not match the manifest")


def _validate_page_lane(
    bundle: Path,
    manifest: dict[str, Any],
    lane: str,
) -> tuple[list[str], bool]:
    pages = manifest.get(lane)
    if not isinstance(pages, list):
        raise WikidataBundleError(f"manifest {lane} must be a list")
    _relative, base_query, variable = QUERY_SPECS[lane]
    page_size = manifest["queries"][lane]["page_size"]
    expected_offset = 0
    qids: list[str] = []
    terminal = False
    for index, checkpoint in enumerate(pages):
        if terminal:
            raise WikidataBundleError(f"manifest {lane} has pages after its terminal page")
        if not isinstance(checkpoint, dict):
            raise WikidataBundleError(f"manifest {lane} page {index} is invalid")
        expected_query = _render_query(base_query, page_size, expected_offset)
        expected_query_hash = _sha256_bytes(expected_query.encode("utf-8"))
        if checkpoint.get("offset") != expected_offset:
            raise WikidataBundleError(f"manifest {lane} offsets are not contiguous")
        if checkpoint.get("query_sha256") != expected_query_hash:
            raise WikidataBundleError(f"manifest {lane} page query hash is invalid")
        relative_file = checkpoint.get("file")
        if not isinstance(relative_file, str) or Path(relative_file).is_absolute():
            raise WikidataBundleError(f"manifest {lane} page file is invalid")
        raw_path = bundle / relative_file
        if not raw_path.is_file():
            raise WikidataBundleError(f"cached {lane} page is missing: {relative_file}")
        raw = raw_path.read_bytes()
        if checkpoint.get("sha256") != _sha256_bytes(raw):
            raise WikidataBundleError(f"cached {lane} page hash does not match")
        _require_timestamp(checkpoint.get("retrieved_at"), f"{lane} retrieved_at")
        document = _json_object(raw, f"cached {lane} page")
        page_qids = _parse_sparql_page(document, variable, f"cached {lane} page")
        if checkpoint.get("result_count") != len(page_qids):
            raise WikidataBundleError(f"manifest {lane} result count does not match")
        if set(qids).intersection(page_qids):
            raise WikidataBundleError(f"cached {lane} repeats QIDs across pages")
        qids.extend(page_qids)
        terminal = len(page_qids) < page_size
        expected_offset += page_size
    return qids, terminal


def _validate_qid_checkpoint(
    bundle: Path,
    checkpoint: Any,
    expected_qids: list[str],
    field: str,
) -> None:
    if not isinstance(checkpoint, dict):
        raise WikidataBundleError(f"manifest {field} checkpoint is missing")
    relative_file = checkpoint.get("file")
    if not isinstance(relative_file, str):
        raise WikidataBundleError(f"manifest {field} file is invalid")
    path = bundle / relative_file
    if not path.is_file():
        raise WikidataBundleError(f"cached {field} file is missing")
    raw = path.read_bytes()
    if checkpoint.get("sha256") != _sha256_bytes(raw):
        raise WikidataBundleError(f"cached {field} hash does not match")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WikidataBundleError(f"cached {field} is invalid JSON") from error
    if document != expected_qids or checkpoint.get("count") != len(expected_qids):
        raise WikidataBundleError(f"cached {field} values do not match raw pages")


def _validate_batches(
    bundle: Path,
    manifest: dict[str, Any],
    field: str,
    qids: list[str],
) -> tuple[dict[str, dict[str, Any]], bool]:
    batches = manifest.get(field)
    if not isinstance(batches, list):
        raise WikidataBundleError(f"manifest {field} must be a list")
    batch_size = manifest.get("batch_size")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
        raise WikidataBundleError("manifest batch_size must be between 1 and 50")
    expected_chunks = list(_batch_chunks(qids, batch_size))
    if len(batches) > len(expected_chunks):
        raise WikidataBundleError(f"manifest {field} has too many batches")
    entities: dict[str, dict[str, Any]] = {}
    for index, checkpoint in enumerate(batches):
        expected = expected_chunks[index]
        if not isinstance(checkpoint, dict) or checkpoint.get("index") != index:
            raise WikidataBundleError(f"manifest {field} batch indexes are invalid")
        if checkpoint.get("qids") != expected or checkpoint.get("count") != len(expected):
            raise WikidataBundleError(f"manifest {field} batch {index} IDs do not match")
        relative_file = checkpoint.get("file")
        if not isinstance(relative_file, str):
            raise WikidataBundleError(f"manifest {field} batch file is invalid")
        raw_path = bundle / relative_file
        if not raw_path.is_file():
            raise WikidataBundleError(f"cached {field} batch is missing")
        raw = raw_path.read_bytes()
        if checkpoint.get("sha256") != _sha256_bytes(raw):
            raise WikidataBundleError(f"cached {field} batch hash does not match")
        _require_timestamp(checkpoint.get("retrieved_at"), f"{field} retrieved_at")
        parsed = _parse_entity_response(
            _json_object(raw, f"cached {field} batch"), expected, f"cached {field} batch"
        )
        entities.update(parsed)
    return entities, len(batches) == len(expected_chunks)


def validate_wikidata_bundle(
    path: str | Path, *, require_complete: bool = True
) -> BundleView:
    """Validate every query, raw response, checkpoint, and derived QID list."""
    bundle = Path(path)
    manifest_path = bundle / WIKIDATA_MANIFEST
    if not bundle.is_dir() or not manifest_path.is_file():
        raise WikidataBundleError("Wikidata bundle must be a directory with manifest.json")
    manifest = _json_object(manifest_path.read_bytes(), "Wikidata manifest")
    fixed = {
        "schema_version": WIKIDATA_SCHEMA_VERSION,
        "dataset": "Wikidata data-center candidate extraction",
        "source_family": WIKIDATA_SOURCE_FAMILY,
        "license": WIKIDATA_LICENSE,
        "selection_rule": "?item wdt:P31/wdt:P279* wd:Q671224",
        "independent_corroboration": False,
        "claim_independence_requires_reference_review": True,
    }
    for key, expected in fixed.items():
        if manifest.get(key) != expected:
            raise WikidataBundleError(f"Wikidata manifest has unexpected {key}")
    if manifest.get("root_class") != {
        "qid": WIKIDATA_ROOT_QID,
        "url": f"https://www.wikidata.org/entity/{WIKIDATA_ROOT_QID}",
    }:
        raise WikidataBundleError("Wikidata manifest root class is invalid")
    endpoints = manifest.get("endpoints")
    if not isinstance(endpoints, dict) or endpoints.get("sparql") != WIKIDATA_SPARQL_ENDPOINT or endpoints.get("action_api") != WIKIDATA_API_ENDPOINT:
        raise WikidataBundleError("Wikidata manifest endpoints are invalid")
    _require_timestamp(manifest.get("retrieved_started_at"), "retrieved_started_at")
    _validate_query_files(bundle, manifest)
    class_qids, classes_terminal = _validate_page_lane(bundle, manifest, "class_pages")
    candidate_qids, items_terminal = _validate_page_lane(bundle, manifest, "item_pages")

    if classes_terminal:
        if WIKIDATA_ROOT_QID not in class_qids:
            raise WikidataBundleError("class closure does not include its root class")
    candidate_checkpoint_present = manifest.get("candidate_qids") is not None
    if items_terminal and candidate_checkpoint_present:
        _validate_qid_checkpoint(
            bundle, manifest.get("candidate_qids"), candidate_qids, "candidate_qids"
        )
    elif items_terminal and (require_complete or manifest.get("state") == "complete"):
        raise WikidataBundleError("terminal item pages are missing candidate_qids")

    entities: dict[str, dict[str, Any]] = {}
    entity_batches_complete = False
    if items_terminal and candidate_checkpoint_present:
        entities, entity_batches_complete = _validate_batches(
            bundle, manifest, "entity_batches", candidate_qids
        )
        if entity_batches_complete:
            class_set = set(class_qids)
            for qid, entity in entities.items():
                _entity_revision(entity, qid)
                _require_timestamp(entity.get("modified"), f"candidate {qid} modified")
                instance_qids = {
                    value
                    for statement in _truthy_statements(entity, P_INSTANCE_OF)
                    if (value := _claim_qid(statement)) is not None
                }
                if not instance_qids.intersection(class_set):
                    raise WikidataBundleError(
                        f"candidate {qid} no longer has a truthy instance class in the cached closure"
                    )

    lookup_qids: list[str] = []
    lookup_entities: dict[str, dict[str, Any]] = {}
    lookup_batches_complete = False
    lookup_checkpoint_present = manifest.get("lookup_qids") is not None
    if classes_terminal and entity_batches_complete and lookup_checkpoint_present:
        lookup_qids = _all_selected_lookup_qids(class_qids, entities)
        _validate_qid_checkpoint(
            bundle, manifest.get("lookup_qids"), lookup_qids, "lookup_qids"
        )
        lookup_entities, lookup_batches_complete = _validate_batches(
            bundle, manifest, "lookup_batches", lookup_qids
        )
    elif (
        classes_terminal
        and entity_batches_complete
        and (require_complete or manifest.get("state") == "complete")
    ):
        raise WikidataBundleError("complete entity batches are missing lookup_qids")

    complete = (
        manifest.get("state") == "complete"
        and classes_terminal
        and items_terminal
        and entity_batches_complete
        and lookup_batches_complete
    )
    if require_complete and not complete:
        raise WikidataBundleError("Wikidata bundle is not complete")
    if manifest.get("state") == "complete":
        _require_timestamp(manifest.get("retrieved_completed_at"), "retrieved_completed_at")
        expected_counts = {
            "classes": len(class_qids),
            "candidates": len(candidate_qids),
            "candidates_with_coordinates": sum(
                bool(_truthy_statements(entity, P_COORDINATE))
                for entity in entities.values()
            ),
            "lookup_entities": len(lookup_qids),
            "power_consumed_claim_items": sum(
                bool(_truthy_statements(entity, P_POWER_CONSUMED))
                for entity in entities.values()
            ),
            "state_of_use_claim_items": sum(
                bool(_truthy_statements(entity, P_STATE_OF_USE))
                for entity in entities.values()
            ),
        }
        if manifest.get("counts") != expected_counts:
            raise WikidataBundleError("Wikidata manifest counts do not match raw responses")
    return BundleView(
        path=bundle,
        manifest=manifest,
        class_qids=tuple(class_qids),
        candidate_qids=tuple(candidate_qids),
        entities=entities,
        lookup_entities=lookup_entities,
    )


class WikidataFetcher:
    """Fetch WDQS QIDs, full entity statements, and selected label lookups."""

    def __init__(
        self,
        *,
        user_agent: str = WIKIDATA_USER_AGENT,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        transient_failure_limit: int = 3,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a transparent Wikidata User-Agent is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")
        if transient_failure_limit <= 0:
            raise ValueError("transient_failure_limit must be positive")
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.transient_failure_limit = transient_failure_limit
        self.opener = opener
        self.sleeper = sleeper
        self.clock = clock

    def _request(self, url: str, *, accept: str) -> _Response:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                headers={"Accept": accept, "User-Agent": self.user_agent},
                method="GET",
            )
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    metadata = _endpoint_metadata(response, url)
                    status = metadata["http_status"]
                    if status in TRANSIENT_HTTP_STATUSES:
                        raise _TransientFailure(
                            f"Wikidata returned HTTP {status}", status=status
                        )
                    if status >= 400:
                        raise WikidataFetchError(f"Wikidata returned HTTP {status}")
                    raw = response.read()
                document = _json_object(raw, "Wikidata response")
                return _Response(raw, document, metadata)
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                if status not in TRANSIENT_HTTP_STATUSES:
                    raise WikidataFetchError(
                        f"Wikidata returned permanent HTTP {status}"
                    ) from error
                last_error = _TransientFailure(
                    f"Wikidata returned HTTP {status}", status=status
                )
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = _TransientFailure(f"Wikidata transport failure: {error}")
            except _TransientFailure as error:
                last_error = error
            if attempt < self.max_retries:
                self.sleeper(self.retry_base_seconds * (2**attempt))
        assert last_error is not None
        raise last_error

    def fetch(
        self,
        output_directory: str | Path,
        *,
        page_size: int = 200,
        batch_size: int = 50,
        max_requests: int | None = None,
    ) -> dict[str, Any]:
        if page_size <= 0 or page_size > 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        if batch_size <= 0 or batch_size > 50:
            raise ValueError("batch_size must be between 1 and 50")
        if max_requests is not None and max_requests <= 0:
            raise ValueError("max_requests must be positive")

        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir():
            raise ValueError(f"Wikidata output is not a directory: {output}")
        manifest_path = output / WIKIDATA_MANIFEST
        for _lane, (relative, text, _variable) in QUERY_SPECS.items():
            query_path = output / relative
            if query_path.exists() and query_path.read_text(encoding="utf-8") != text:
                raise WikidataBundleError(f"existing query file is incompatible: {relative}")
            if not query_path.exists():
                _write_bytes_atomic(query_path, text.encode("utf-8"))

        if manifest_path.exists():
            manifest = validate_wikidata_bundle(
                output, require_complete=False
            ).manifest
            if manifest.get("state") == "complete":
                validate_wikidata_bundle(output)
                return manifest
            if manifest["queries"]["class_pages"]["page_size"] != page_size:
                raise WikidataBundleError("page_size cannot change while resuming a bundle")
            if manifest.get("batch_size") != batch_size:
                raise WikidataBundleError("batch_size cannot change while resuming a bundle")
        else:
            started_at = _require_timestamp(self.clock(), "retrieved_started_at")
            manifest = _new_manifest(
                page_size=page_size, batch_size=batch_size, started_at=started_at
            )
            _write_json_atomic(manifest_path, manifest)

        run_started_at = _require_timestamp(self.clock(), "run_started_at")
        requests_completed = 0
        consecutive_transient_failures = 0
        manifest["last_run"] = {
            "started_at": run_started_at,
            "finished_at": None,
            "requests_completed": 0,
            "stop_reason": None,
        }
        _write_json_atomic(manifest_path, manifest)

        def checkpoint(stop_reason: str | None = None) -> dict[str, Any]:
            manifest["last_run"] = {
                "started_at": run_started_at,
                "finished_at": _require_timestamp(self.clock(), "run_finished_at"),
                "requests_completed": requests_completed,
                "stop_reason": stop_reason,
            }
            _write_json_atomic(manifest_path, manifest)
            return manifest

        def allowed() -> bool:
            return max_requests is None or requests_completed < max_requests

        def request_with_circuit(url: str, *, accept: str, task: str) -> _Response:
            nonlocal requests_completed, consecutive_transient_failures
            while True:
                try:
                    response = self._request(url, accept=accept)
                except _TransientFailure as error:
                    consecutive_transient_failures += 1
                    manifest["failure_history"].append(
                        {
                            "at": _require_timestamp(self.clock(), "failure timestamp"),
                            "task": task,
                            "transient": True,
                            "http_status": error.status,
                            "message": str(error),
                        }
                    )
                    _write_json_atomic(manifest_path, manifest)
                    if consecutive_transient_failures >= self.transient_failure_limit:
                        checkpoint("transient_circuit_break")
                        raise WikidataFetchError(
                            "Wikidata transient-failure circuit breaker opened"
                        ) from error
                    continue
                consecutive_transient_failures = 0
                requests_completed += 1
                return response

        for lane, (relative_query, base_query, variable) in QUERY_SPECS.items():
            page_size_value = manifest["queries"][lane]["page_size"]
            _existing_qids, terminal = _validate_page_lane(output, manifest, lane)
            while not terminal:
                if not allowed():
                    return checkpoint("max_requests")
                offset = len(manifest[lane]) * page_size_value
                query = _render_query(base_query, page_size_value, offset)
                url = WIKIDATA_SPARQL_ENDPOINT + "?" + urllib.parse.urlencode(
                    {"query": query, "format": "json"}
                )
                response = request_with_circuit(
                    url,
                    accept="application/sparql-results+json",
                    task=f"{lane}:{offset}",
                )
                qids = _parse_sparql_page(response.document, variable, lane)
                page_index = len(manifest[lane])
                relative_file = f"sparql/{lane[:-6]}-{page_index:05d}.json"
                _write_bytes_atomic(output / relative_file, response.raw)
                manifest[lane].append(
                    {
                        "file": relative_file,
                        "offset": offset,
                        "query_sha256": _sha256_bytes(query.encode("utf-8")),
                        "result_count": len(qids),
                        "sha256": _sha256_bytes(response.raw),
                        "retrieved_at": _require_timestamp(
                            self.clock(), f"{lane} retrieved_at"
                        ),
                        "endpoint_metadata": response.endpoint_metadata,
                    }
                )
                _write_json_atomic(manifest_path, manifest)
                terminal = len(qids) < page_size_value

        view = validate_wikidata_bundle(output, require_complete=False)
        candidate_qids = list(view.candidate_qids)
        if manifest.get("candidate_qids") is None:
            relative = "candidate-qids.json"
            raw = (json.dumps(candidate_qids, indent=2) + "\n").encode("utf-8")
            _write_bytes_atomic(output / relative, raw)
            manifest["candidate_qids"] = {
                "file": relative,
                "count": len(candidate_qids),
                "sha256": _sha256_bytes(raw),
            }
            _write_json_atomic(manifest_path, manifest)

        expected_entity_chunks = list(_batch_chunks(candidate_qids, batch_size))
        for batch_index in range(len(manifest["entity_batches"]), len(expected_entity_chunks)):
            if not allowed():
                return checkpoint("max_requests")
            qids = expected_entity_chunks[batch_index]
            params = {
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "info|labels|descriptions|claims",
                "format": "json",
                "formatversion": "2",
            }
            url = WIKIDATA_API_ENDPOINT + "?" + urllib.parse.urlencode(params)
            response = request_with_circuit(
                url, accept="application/json", task=f"entity_batch:{batch_index}"
            )
            _parse_entity_response(response.document, qids, "entity response")
            relative_file = f"entities/batch-{batch_index:05d}.json"
            _write_bytes_atomic(output / relative_file, response.raw)
            manifest["entity_batches"].append(
                {
                    "file": relative_file,
                    "index": batch_index,
                    "qids": qids,
                    "count": len(qids),
                    "sha256": _sha256_bytes(response.raw),
                    "retrieved_at": _require_timestamp(
                        self.clock(), "entity batch retrieved_at"
                    ),
                    "endpoint_metadata": response.endpoint_metadata,
                }
            )
            _write_json_atomic(manifest_path, manifest)

        view = validate_wikidata_bundle(output, require_complete=False)
        lookup_qids = _all_selected_lookup_qids(view.class_qids, view.entities)
        if manifest.get("lookup_qids") is None:
            relative = "lookup-qids.json"
            raw = (json.dumps(lookup_qids, indent=2) + "\n").encode("utf-8")
            _write_bytes_atomic(output / relative, raw)
            manifest["lookup_qids"] = {
                "file": relative,
                "count": len(lookup_qids),
                "sha256": _sha256_bytes(raw),
            }
            _write_json_atomic(manifest_path, manifest)

        expected_lookup_chunks = list(_batch_chunks(lookup_qids, batch_size))
        for batch_index in range(len(manifest["lookup_batches"]), len(expected_lookup_chunks)):
            if not allowed():
                return checkpoint("max_requests")
            qids = expected_lookup_chunks[batch_index]
            params = {
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "info|labels|descriptions",
                "format": "json",
                "formatversion": "2",
            }
            url = WIKIDATA_API_ENDPOINT + "?" + urllib.parse.urlencode(params)
            response = request_with_circuit(
                url, accept="application/json", task=f"lookup_batch:{batch_index}"
            )
            _parse_entity_response(response.document, qids, "lookup response")
            relative_file = f"lookups/batch-{batch_index:05d}.json"
            _write_bytes_atomic(output / relative_file, response.raw)
            manifest["lookup_batches"].append(
                {
                    "file": relative_file,
                    "index": batch_index,
                    "qids": qids,
                    "count": len(qids),
                    "sha256": _sha256_bytes(response.raw),
                    "retrieved_at": _require_timestamp(
                        self.clock(), "lookup batch retrieved_at"
                    ),
                    "endpoint_metadata": response.endpoint_metadata,
                }
            )
            _write_json_atomic(manifest_path, manifest)

        complete_view = validate_wikidata_bundle(output, require_complete=False)
        manifest["counts"] = {
            "classes": len(complete_view.class_qids),
            "candidates": len(complete_view.candidate_qids),
            "candidates_with_coordinates": sum(
                bool(_truthy_statements(entity, P_COORDINATE))
                for entity in complete_view.entities.values()
            ),
            "lookup_entities": len(complete_view.lookup_entities),
            "power_consumed_claim_items": sum(
                bool(_truthy_statements(entity, P_POWER_CONSUMED))
                for entity in complete_view.entities.values()
            ),
            "state_of_use_claim_items": sum(
                bool(_truthy_statements(entity, P_STATE_OF_USE))
                for entity in complete_view.entities.values()
            ),
        }
        manifest["state"] = "complete"
        manifest["retrieved_completed_at"] = _require_timestamp(
            self.clock(), "retrieved_completed_at"
        )
        checkpoint("complete")
        validate_wikidata_bundle(output)
        return manifest


def _language_value(entity: dict[str, Any], field: str) -> str | None:
    values = entity.get(field)
    if not isinstance(values, dict) or not values:
        return None
    preferred_languages = ("en", "en-gb", "en-ca", "en-us")
    for language in preferred_languages:
        value = values.get(language)
        if isinstance(value, dict) and isinstance(value.get("value"), str) and value["value"].strip():
            return value["value"]
    for language in sorted(values):
        value = values[language]
        if isinstance(value, dict) and isinstance(value.get("value"), str) and value["value"].strip():
            return value["value"]
    return None


def _coordinate(entity: dict[str, Any]) -> tuple[float | None, float | None]:
    for statement in sorted(
        _truthy_statements(entity, P_COORDINATE), key=lambda item: str(item.get("id", ""))
    ):
        snak = statement.get("mainsnak", {})
        datavalue = snak.get("datavalue", {})
        value = datavalue.get("value", {}) if isinstance(datavalue, dict) else {}
        if not isinstance(value, dict):
            continue
        if value.get("globe", EARTH_GLOBE) != EARTH_GLOBE:
            continue
        latitude = value.get("latitude")
        longitude = value.get("longitude")
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            continue
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        latitude = float(latitude)
        longitude = float(longitude)
        if math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    return None, None


def read_wikidata_candidates(
    path: str | Path,
) -> tuple[BundleView, list[WikidataCandidate]]:
    """Read and normalize a fully verified bundle without network access."""
    view = validate_wikidata_bundle(path)
    batch_by_qid: dict[str, dict[str, Any]] = {}
    for checkpoint in view.manifest["entity_batches"]:
        for qid in checkpoint["qids"]:
            batch_by_qid[qid] = checkpoint
    candidates: list[WikidataCandidate] = []
    for qid in view.candidate_qids:
        entity = view.entities[qid]
        claims = entity.get("claims")
        if not isinstance(claims, dict):
            claims = {}
        selected_claims = {
            property_id: claims[property_id]
            for property_id in SELECTED_PROPERTIES
            if isinstance(claims.get(property_id), list)
        }
        latitude, longitude = _coordinate(entity)
        checkpoint = batch_by_qid[qid]
        candidates.append(
            WikidataCandidate(
                qid=qid,
                entity=entity,
                name=_language_value(entity, "labels"),
                description=_language_value(entity, "descriptions"),
                latitude=latitude,
                longitude=longitude,
                selected_claims=selected_claims,
                content_hash=_canonical_hash(entity),
                raw_batch_file=checkpoint["file"],
                raw_batch_sha256=checkpoint["sha256"],
                fetched_at=checkpoint["retrieved_at"],
            )
        )
    return view, candidates


def _labels_by_qid(view: BundleView) -> dict[str, str]:
    labels: dict[str, str] = {}
    for qid, entity in {**view.lookup_entities, **view.entities}.items():
        label = _language_value(entity, "labels")
        if label:
            labels[qid] = label
    return labels


def _qid_values(entity: dict[str, Any], property_id: str) -> list[str]:
    return [
        qid
        for statement in _truthy_statements(entity, property_id)
        if (qid := _claim_qid(statement)) is not None
    ]


def _claim_time_values(entity: dict[str, Any], property_id: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for statement in _truthy_statements(entity, property_id):
        snak = statement.get("mainsnak", {})
        datavalue = snak.get("datavalue", {})
        value = datavalue.get("value") if isinstance(datavalue, dict) else None
        if isinstance(value, dict) and isinstance(value.get("time"), str):
            values.append(value)
    return values


def _qid_labels(qids: Iterable[str], labels: Mapping[str, str]) -> str:
    values = []
    for qid in qids:
        label = labels.get(qid)
        values.append(f"{qid}|{label}" if label else qid)
    return ";".join(values)


def _candidate_tags(
    candidate: WikidataCandidate, labels: Mapping[str, str]
) -> dict[str, str]:
    entity = candidate.entity
    tags = {
        "wikidata:qid": candidate.qid,
        "wikidata:url": f"https://www.wikidata.org/entity/{candidate.qid}",
        "wikidata:selection_rule": "P31/P279* Q671224",
        "wikidata:selected_claims_json": json.dumps(
            candidate.selected_claims, sort_keys=True, separators=(",", ":")
        ),
        "wikidata:selected_claims_sha256": _canonical_hash(candidate.selected_claims),
        "wikidata:claim_independence": "unverified",
    }
    labels_document = entity.get("labels")
    if isinstance(labels_document, dict):
        tags["wikidata:labels_json"] = json.dumps(
            labels_document, sort_keys=True, separators=(",", ":")
        )
    if candidate.description:
        tags["wikidata:description"] = candidate.description
    for property_id, key in (
        (P_INSTANCE_OF, "instance_of"),
        (P_OPERATOR, "operator"),
        (P_OWNER, "owner"),
        (P_STATE_OF_USE, "state_of_use"),
    ):
        values = _qid_values(entity, property_id)
        if values:
            tags[f"wikidata:{key}"] = _qid_labels(values, labels)
    country_qids = _qid_values(entity, P_COUNTRY)
    if country_qids:
        tags["wikidata:country"] = _qid_labels(country_qids, labels)
        unique_country_qids = tuple(dict.fromkeys(country_qids))
        if len(unique_country_qids) == 1:
            country_qid = unique_country_qids[0]
            country_label = labels.get(country_qid)
            if country_label:
                tags[WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG] = country_label
                tags[WIKIDATA_COUNTRY_FALLBACK_QID_TAG] = country_qid
                tags[WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG] = (
                    WIKIDATA_COUNTRY_FALLBACK_METHOD
                )
    for property_id, key in (
        (P_INCEPTION, "inception_json"),
        (P_DISSOLUTION, "dissolution_json"),
    ):
        values = _claim_time_values(entity, property_id)
        if values:
            tags[f"wikidata:{key}"] = json.dumps(
                values, sort_keys=True, separators=(",", ":")
            )
    return tags


def _lifecycle(entity: dict[str, Any]) -> tuple[LifecycleStatus, float, str]:
    state_qids = _qid_values(entity, P_STATE_OF_USE)
    unique = set(state_qids)
    mapping = {
        Q_UNDER_CONSTRUCTION: LifecycleStatus.UNDER_CONSTRUCTION,
        Q_PROPOSED: LifecycleStatus.PROPOSED,
    }
    if len(unique) == 1 and next(iter(unique), None) in mapping:
        qid = next(iter(unique))
        return mapping[qid], 0.75, f"wikidata_explicit_P5817_{qid}"
    return (
        LifecycleStatus.UNKNOWN,
        1.0,
        "wikidata_no_unambiguous_supported_P5817_no_label_inference",
    )


def _decimal(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _power_estimates(
    candidate: WikidataCandidate,
    *,
    entity_id: str,
    evidence_id: str,
    recorded_at: str,
) -> tuple[list[CapacityEstimate], int]:
    estimates: list[CapacityEstimate] = []
    unmapped = 0
    as_of_date = _retrieval_date(candidate.fetched_at)
    for statement in _truthy_statements(candidate.entity, P_POWER_CONSUMED):
        snak = statement.get("mainsnak", {})
        datavalue = snak.get("datavalue", {})
        value = datavalue.get("value") if isinstance(datavalue, dict) else None
        if not isinstance(value, dict):
            unmapped += 1
            continue
        unit = value.get("unit")
        unit_qid = None
        if isinstance(unit, str) and unit.startswith(_QID_PREFIX):
            try:
                unit_qid = _qid_from_uri(unit, "P2791 unit")
            except WikidataBundleError:
                unit_qid = None
        factor = POWER_UNIT_TO_MW.get(unit_qid or "")
        if factor is None:
            unmapped += 1
            continue
        base_native = _decimal(value.get("amount"))
        low_native = _decimal(value.get("lowerBound"))
        high_native = _decimal(value.get("upperBound"))
        if low_native is None:
            low_native = base_native
        if high_native is None:
            high_native = base_native
        if (
            base_native is None
            or low_native is None
            or high_native is None
            or low_native < 0
            or not low_native <= base_native <= high_native
        ):
            unmapped += 1
            continue
        base_mw = base_native * factor
        low_mw = low_native * factor
        high_mw = high_native * factor
        statement_id = str(statement.get("id") or _canonical_hash(statement))
        reference_count = len(statement.get("references", [])) if isinstance(statement.get("references", []), list) else 0
        qualifier_properties = sorted(statement.get("qualifiers", {})) if isinstance(statement.get("qualifiers"), dict) else []
        estimates.append(
            CapacityEstimate(
                id=stable_id(
                    "capacity",
                    entity_id,
                    evidence_id,
                    P_POWER_CONSUMED,
                    statement_id,
                ),
                entity_id=entity_id,
                metric=CapacityMetric.GROSS_FACILITY_MW,
                low=float(low_mw),
                base=float(base_mw),
                high=float(high_mw),
                method=EstimateMethod.REPORTED,
                confidence=0.70,
                evidence_id=evidence_id,
                as_of_date=as_of_date,
                recorded_at=recorded_at,
                stage=CapacityStage.UNKNOWN,
                notes=(
                    f"Wikidata P2791 power consumed; source_unit={unit_qid}; "
                    f"statement={statement_id}; "
                    f"rank={statement.get('rank')}; references={reference_count}; "
                    f"qualifier_properties={','.join(qualifier_properties) or 'none'}. "
                    "Mapped to gross facility MW with unknown stage; not critical IT "
                    "load and not annual energy consumption."
                ),
            )
        )
    return estimates, unmapped


class WikidataAdapter:
    """Import verified Wikidata matches as unmerged source candidates."""

    source_name = "wikidata"

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        _require_timestamp(retrieved_at, "retrieved_at")
        view, candidates = read_wikidata_candidates(path)
        completed_at = view.manifest["retrieved_completed_at"]
        if retrieved_at != completed_at:
            raise WikidataBundleError(
                "retrieved_at must equal the bundle retrieved_completed_at to keep import IDs idempotent"
            )
        labels = _labels_by_qid(view)
        entities_created = 0
        evidence_created = 0
        capacities_created = 0
        unmapped_power_claims = 0
        warnings = [
            (
                "Wikidata ontology matches are source-scoped candidates; item type and "
                "individual claim independence require review before corroboration or merge"
            )
        ]
        manifest_sha256 = _sha256_file(view.path / WIKIDATA_MANIFEST)

        with connection:
            for candidate in candidates:
                stable_key = f"wikidata:{candidate.qid}"
                evidence_id = stable_id(
                    "evidence",
                    WIKIDATA_SOURCE_FAMILY,
                    candidate.qid,
                    candidate.fetched_at,
                    candidate.content_hash,
                )
                title = f"Wikidata item {candidate.qid}"
                if candidate.name:
                    title += f": {candidate.name}"
                evidence_created += int(
                    add_evidence(
                        connection,
                        Evidence(
                            id=evidence_id,
                            kind=EvidenceKind.THIRD_PARTY_DATASET,
                            title=title,
                            source_url=WIKIDATA_ENTITY_DATA_URL.format(
                                qid=candidate.qid,
                                revision=_entity_revision(
                                    candidate.entity, candidate.qid
                                ),
                            ),
                            publisher=WIKIDATA_PUBLISHER,
                            source_family=WIKIDATA_SOURCE_FAMILY,
                            license=WIKIDATA_LICENSE,
                            attribution=WIKIDATA_ATTRIBUTION,
                            published_at=candidate.entity["modified"],
                            retrieved_at=candidate.fetched_at,
                            excerpt=(
                                "Source-scoped candidate selected by a truthy P31/P279* "
                                f"path to {WIKIDATA_ROOT_QID}; claim independence unverified."
                            ),
                        ),
                        content_hash=candidate.content_hash,
                        metadata={
                            "qid": candidate.qid,
                            "entity_url": f"https://www.wikidata.org/entity/{candidate.qid}",
                            "entity_data_url": WIKIDATA_ENTITY_DATA_URL.format(
                                qid=candidate.qid,
                                revision=_entity_revision(
                                    candidate.entity, candidate.qid
                                ),
                            ),
                            "lastrevid": candidate.entity.get("lastrevid"),
                            "modified": candidate.entity.get("modified"),
                            "raw_batch_file": candidate.raw_batch_file,
                            "raw_batch_sha256": candidate.raw_batch_sha256,
                            "bundle_manifest_sha256": manifest_sha256,
                            "provenance": {
                                "bundle_manifest_sha256": manifest_sha256,
                                "raw_batch_file": candidate.raw_batch_file,
                                "raw_batch_sha256": candidate.raw_batch_sha256,
                                "entity_data_url": WIKIDATA_ENTITY_DATA_URL.format(
                                    qid=candidate.qid,
                                    revision=_entity_revision(
                                        candidate.entity, candidate.qid
                                    ),
                                ),
                                "qid": candidate.qid,
                                "lastrevid": _entity_revision(
                                    candidate.entity, candidate.qid
                                ),
                            },
                            "selection_rule": view.manifest["selection_rule"],
                            "selected_claims": candidate.selected_claims,
                            "statement_ranks_qualifiers_references_preserved": True,
                            "independent_corroboration": False,
                            "claim_independence_requires_reference_review": True,
                        },
                    )
                )
                entity_id = stable_id("entity", stable_key, "facility")
                entities_created += int(
                    add_facility(
                        connection,
                        Facility(entity_id, stable_key, evidence_id),
                        created_at=retrieved_at,
                    )
                )
                geometry = None
                if candidate.latitude is not None and candidate.longitude is not None:
                    geometry = {
                        "type": "Point",
                        "coordinates": [candidate.longitude, candidate.latitude],
                    }
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id),
                    entity_id=entity_id,
                    name=candidate.name or f"Wikidata {candidate.qid}",
                    latitude=candidate.latitude,
                    longitude=candidate.longitude,
                    geometry=geometry,
                    tags=_candidate_tags(candidate, labels),
                    evidence_id=evidence_id,
                    as_of_date=_retrieval_date(candidate.fetched_at),
                    recorded_at=retrieved_at,
                    method="wikidata_source_scoped_candidate",
                    confidence=0.65,
                )
                lifecycle_status, confidence, method = _lifecycle(candidate.entity)
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id(
                            "lifecycle", entity_id, evidence_id, lifecycle_status.value
                        ),
                        entity_id=entity_id,
                        status=lifecycle_status,
                        evidence_id=evidence_id,
                        as_of_date=_retrieval_date(candidate.fetched_at),
                        recorded_at=retrieved_at,
                        method=method,
                        confidence=confidence,
                    ),
                )
                estimates, unmapped = _power_estimates(
                    candidate,
                    entity_id=entity_id,
                    evidence_id=evidence_id,
                    recorded_at=retrieved_at,
                )
                unmapped_power_claims += unmapped
                for estimate in estimates:
                    capacities_created += int(add_capacity(connection, estimate))

        if unmapped_power_claims:
            warnings.append(
                f"retained but did not map {unmapped_power_claims} P2791 statement(s) "
                "whose quantity was invalid or not expressed in a recognized SI power unit"
            )
        warnings.append(
            f"created {capacities_created} explicit P2791 power estimate row(s); "
            "no annual energy or critical IT load was inferred"
        )
        return ImportResult(
            source=self.source_name,
            examined_elements=len(candidates),
            imported_elements=len(candidates),
            skipped_elements=0,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )


WikidataCandidateAdapter = WikidataAdapter
