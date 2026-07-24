"""Build and validate a conservative England Planning Data review lane.

The official Planning Data planning-application dataset is explicitly marked
incomplete and not ready for use.  This module therefore emits planning
observations for review, never facility records.  It preserves the exact bulk
CSV and source fields, applies a narrow phrase contract to descriptions, and
fails closed when the pinned snapshot, lineage, or OGL rights evidence changes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import csv
from datetime import UTC, datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from unicodedata import normalize as unicode_normalize
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "england-planning-data-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-england-planning-data-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-england-planning-data-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-england-planning-data-assessment-v1"
INVENTORY_FORMAT = "datacenter-atlas-england-planning-data-inventory-v1"
PHRASE_REVIEW_FORMAT = "datacenter-atlas-england-planning-data-phrase-review-v1"
SCHEMA_FORMAT = "datacenter-atlas-england-planning-data-schema-v1"

DATASET_PAGE_URL = (
    "https://www.planning.data.gov.uk/dataset/planning-application"
)
DATASET_METADATA_URL = f"{DATASET_PAGE_URL}.json"
BULK_CSV_URL = (
    "https://files.planning.data.gov.uk/dataset/planning-application.csv"
)
OGL3_URL = (
    "https://www.nationalarchives.gov.uk/doc/"
    "open-government-licence/version/3/"
)

PROVIDER_NAMES = {
    "26": "Adur District Council",
    "90": "London Borough of Camden",
    "109": "Doncaster Metropolitan Borough Council",
    "382": "Worthing Borough Council",
}
PROVIDER_ENTITY_URLS = {
    provider: f"https://www.planning.data.gov.uk/entity/{provider}.json"
    for provider in PROVIDER_NAMES
}

EXPLICIT_TERMS = (
    "data centre",
    "data center",
    "datacentre",
    "data-center",
)
OPTIONAL_TERMS = (
    "data hall",
    "server room",
    "data processing",
)

SOURCE_FIELDS = (
    "dataset",
    "end-date",
    "entity",
    "entry-date",
    "geojson",
    "geometry",
    "name",
    "organisation-entity",
    "point",
    "prefix",
    "reference",
    "start-date",
    "typology",
    "address-text",
    "decision-date",
    "description",
    "development-classification",
    "documentation-url",
    "ground-area",
    "notes",
    "organisation",
    "planning-application-status",
    "planning-application-type",
    "planning-decision",
    "planning-decision-type",
    "uprn",
)
DATE_FIELDS = (
    "entry-date",
    "start-date",
    "end-date",
    "decision-date",
)
STATUS_FIELDS = (
    "planning-application-status",
    "planning-application-type",
    "planning-decision",
    "planning-decision-type",
)
GEOMETRY_FIELDS = ("point", "geometry", "geojson")

EXPECTED_SOURCE_ROWS = 100_627
EXPECTED_PAGE_PROVIDER_COUNT = 6
EXPECTED_PROVIDER_ROW_COUNTS = {
    "26": 7_585,
    "90": 77_499,
    "109": 1_914,
    "382": 13_629,
}
EXPECTED_EXPLICIT_ENTITIES = (
    "10000009092",
    "10000057188",
    "10000088724",
    "10000090380",
)
EXPECTED_OPTIONAL_ENTITIES = {
    "data hall": (),
    "server room": (
        "10000035994",
        "10000035995",
        "10000092914",
    ),
    "data processing": (),
}
EXPECTED_CONTEXT_ASSESSMENT = {
    "10000009092": {
        "classification": "direct_data_centre_scope",
        "reason": "The description proposes construction of two data centre cabins.",
    },
    "10000057188": {
        "classification": "context_only_exclusion",
        "reason": (
            "The data centre is expressly excluded from the temporary change of use; "
            "the phrase is context, not evidence of new data-centre works."
        ),
    },
    "10000088724": {
        "classification": "direct_data_centre_scope",
        "reason": "The wider redevelopment description includes a relocated data centre.",
    },
    "10000090380": {
        "classification": "direct_data_centre_scope",
        "reason": (
            "The listed-building application describes an opening between an existing "
            "data centre and a lift motor room."
        ),
    },
}

EXPECTED_CSV_BYTES = 44_513_805
EXPECTED_CSV_SHA256 = (
    "c09847e03d0da35f41e4f3b9a0c9e815ddeb9c0460d35c4b75712651056a75aa"
)
EXPECTED_CSV_LAST_MODIFIED = "Tue, 09 Sep 2025 03:36:15 GMT"
EXPECTED_CSV_ETAG = '"29688ef098fc662123b1cfe5baab0db3-6"'
EXPECTED_CSV_VERSION_ID = "hHnEr9InrX7sadW2XR1YnbplPITGhhog"

RAW_ARTIFACTS = {
    "bulk_csv": {
        "filename": "raw/planning-application.csv",
        "url": BULK_CSV_URL,
        "content_type": "text/csv",
        "expected_bytes": EXPECTED_CSV_BYTES,
        "expected_sha256": EXPECTED_CSV_SHA256,
    },
    "dataset_metadata": {
        "filename": "raw/planning-application.dataset.json",
        "url": DATASET_METADATA_URL,
        "content_type": "application/json",
        "expected_bytes": 872,
        "expected_sha256": (
            "9517898caade52f31feaeabf26ecb068e0fd4549ac0aa5c0ec0086e6cb868403"
        ),
    },
    "dataset_page": {
        "filename": "raw/planning-application.dataset.html",
        "url": DATASET_PAGE_URL,
        "content_type": "text/html",
        "expected_bytes": 34_783,
        "expected_sha256": (
            "28fe538e84a740aaa1eec54bd18cf7cfa4ac58ec6319ed2c77b6890db04de27c"
        ),
    },
    "ogl3_legalcode": {
        "filename": "raw/open-government-licence-v3.html",
        "url": OGL3_URL,
        "content_type": "text/html",
        "expected_bytes": 10_450,
        "expected_sha256": (
            "f5b2b9f2af63647cde889fa6c3508f5705925295b74912c68caa28dd37e64aa5"
        ),
    },
    "provider_26": {
        "filename": "raw/provider-entity-26.json",
        "url": PROVIDER_ENTITY_URLS["26"],
        "content_type": "application/json",
        "expected_bytes": 704,
        "expected_sha256": (
            "e1b592ed0e79d909a38ac9fad22c5efe422484c19dc6f92b47f67f8625fd79aa"
        ),
    },
    "provider_90": {
        "filename": "raw/provider-entity-90.json",
        "url": PROVIDER_ENTITY_URLS["90"],
        "content_type": "application/json",
        "expected_bytes": 779,
        "expected_sha256": (
            "e713210cb4ed691936b83e8a9ab0b6d3a69749abe50f5a945c5505aa6f68623a"
        ),
    },
    "provider_109": {
        "filename": "raw/provider-entity-109.json",
        "url": PROVIDER_ENTITY_URLS["109"],
        "content_type": "application/json",
        "expected_bytes": 863,
        "expected_sha256": (
            "05201d50ee632de79f5d43a5ce33d8b5fbea846978d8fe158918c84a26174f75"
        ),
    },
    "provider_382": {
        "filename": "raw/provider-entity-382.json",
        "url": PROVIDER_ENTITY_URLS["382"],
        "content_type": "application/json",
        "expected_bytes": 764,
        "expected_sha256": (
            "b231fdfaf1cd4d78d5b685e3f4d81acb353bab8a799796a8e90832c2ef2b85a9"
        ),
    },
}

DERIVED_FILENAMES = {
    "assessment": "assessment.json",
    "attribution": "ATTRIBUTION.txt",
    "definition": "definition.json",
    "inventory": "source-inventory.json",
    "observations_csv": "observations.csv",
    "observations_jsonl": "observations.jsonl",
    "phrase_review": "phrase-review.json",
    "readme": "README.md",
    "schema": "schema.json",
}
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

OFFICIAL_HOSTS = frozenset(
    {
        "files.planning.data.gov.uk",
        "www.nationalarchives.gov.uk",
        "www.planning.data.gov.uk",
    }
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
POINT_RE = re.compile(
    r"^POINT\s*\(\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*\)$"
)

RIGHTS_POLICY = {
    "attribution_required": True,
    "commercial_reuse_permitted": True,
    "dataset_attribution_statement": "© Crown copyright and database right 2026",
    "dataset_license": "Open Government Licence v3.0",
    "dataset_license_url": OGL3_URL,
    "derivative_use_permitted": True,
    "exclusions_include_personal_data_and_unlicensed_third_party_rights": True,
    "licence_text_retained": True,
    "no_endorsement": True,
    "no_warranty": True,
    "raw_dataset_redistribution_permitted_with_attribution": True,
    "rights_gate_passed": True,
}

REVIEW_POLICY = {
    "auto_merge": False,
    "construction_evidence": False,
    "data_centre_identity": None,
    "data_centre_type": None,
    "energy_consumption": None,
    "facility_lifecycle_status": None,
    "facility_or_site_count": None,
    "gross_facility_power_mw": None,
    "independent_corroboration": False,
    "it_capacity_mw": None,
    "operation_evidence": False,
    "planning_status_is_facility_status": False,
    "promotion_permitted": False,
    "pue": None,
    "review_only": True,
}


class EnglandPlanningDataError(ValueError):
    """Raised when retrieval, derivation, or validation fails closed."""


def canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    """Return deterministic UTF-8 JSON with one trailing newline."""

    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        text = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return (text + "\n").encode("utf-8")


def jsonl_bytes(records: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(record) for record in records)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise EnglandPlanningDataError(f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EnglandPlanningDataError(
            f"{field} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EnglandPlanningDataError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EnglandPlanningDataError(f"{field} must be an object")
    return value


def _json_body(raw_bodies: Mapping[str, bytes], artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(raw_bodies[artifact_id].decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EnglandPlanningDataError(
            f"{artifact_id} must be valid UTF-8 JSON"
        ) from error
    if not isinstance(value, dict):
        raise EnglandPlanningDataError(f"{artifact_id} must contain an object")
    return value


def source_definition() -> dict[str, Any]:
    """Return the machine-readable, pinned source contract."""

    return {
        "format": DEFINITION_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "dataset": {
            "dataset_id": "planning-application",
            "jurisdiction": "England Planning Data platform snapshot",
            "publisher": "Ministry of Housing, Communities and Local Government",
            "source_page": DATASET_PAGE_URL,
        },
        "expected_snapshot": {
            "bulk_csv_bytes": EXPECTED_CSV_BYTES,
            "bulk_csv_etag": EXPECTED_CSV_ETAG,
            "bulk_csv_last_modified": EXPECTED_CSV_LAST_MODIFIED,
            "bulk_csv_sha256": EXPECTED_CSV_SHA256,
            "bulk_csv_version_id": EXPECTED_CSV_VERSION_ID,
            "page_provider_statistic": EXPECTED_PAGE_PROVIDER_COUNT,
            "row_count": EXPECTED_SOURCE_ROWS,
            "row_provider_counts": EXPECTED_PROVIDER_ROW_COUNTS,
        },
        "official_artifacts": {
            artifact_id: dict(specification)
            for artifact_id, specification in sorted(RAW_ARTIFACTS.items())
        },
        "selection": {
            "description_field": "description",
            "explicit_terms": list(EXPLICIT_TERMS),
            "explicit_terms_included": True,
            "match_normalization": (
                "NFKC, Unicode casefold, whitespace collapsed, ASCII "
                "alphanumeric token boundaries"
            ),
            "optional_terms": list(OPTIONAL_TERMS),
            "optional_terms_require_reviewed_precision": True,
        },
        "rights_gate": RIGHTS_POLICY,
        "review_policy": REVIEW_POLICY,
    }


def _validate_retrievals(
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
) -> dict[str, dict[str, Any]]:
    if set(retrievals) != set(RAW_ARTIFACTS):
        raise EnglandPlanningDataError("retrieval lineage artifact IDs changed")
    if set(raw_bodies) != set(RAW_ARTIFACTS):
        raise EnglandPlanningDataError("raw artifact IDs changed")

    validated: dict[str, dict[str, Any]] = {}
    for artifact_id, specification in RAW_ARTIFACTS.items():
        retrieval = _as_mapping(retrievals[artifact_id], artifact_id)
        body = raw_bodies[artifact_id]
        if not isinstance(body, bytes) or not body:
            raise EnglandPlanningDataError(f"{artifact_id} body is empty")
        url = retrieval.get("url")
        effective_url = retrieval.get("effective_url")
        status_code = retrieval.get("http_status")
        content_type = retrieval.get("content_type")
        if url != specification["url"] or effective_url != specification["url"]:
            raise EnglandPlanningDataError(
                f"{artifact_id} lineage URL does not match the official endpoint"
            )
        parsed = urlsplit(str(effective_url))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise EnglandPlanningDataError(f"{artifact_id} is not an official HTTPS URL")
        if status_code != 200:
            raise EnglandPlanningDataError(f"{artifact_id} HTTP status is not 200")
        if content_type != specification["content_type"]:
            raise EnglandPlanningDataError(f"{artifact_id} content type changed")
        if len(body) != specification["expected_bytes"]:
            raise EnglandPlanningDataError(f"{artifact_id} byte count changed")
        digest = sha256_bytes(body)
        if digest != specification["expected_sha256"]:
            raise EnglandPlanningDataError(f"{artifact_id} SHA-256 changed")
        headers = retrieval.get("headers", {})
        if not isinstance(headers, Mapping):
            raise EnglandPlanningDataError(f"{artifact_id} headers must be an object")
        normalized_headers = {
            str(key).lower(): str(value) for key, value in sorted(headers.items())
        }
        validated[artifact_id] = {
            "bytes": len(body),
            "content_type": content_type,
            "effective_url": effective_url,
            "headers": normalized_headers,
            "http_status": status_code,
            "raw_filename": specification["filename"],
            "sha256": digest,
            "url": url,
        }
    return validated


def _validate_rights_and_metadata(raw_bodies: Mapping[str, bytes]) -> dict[str, Any]:
    metadata = _json_body(raw_bodies, "dataset_metadata")
    expected_metadata = {
        "dataset": "planning-application",
        "entity-count": EXPECTED_SOURCE_ROWS,
        "licence": "ogl3",
        "attribution": "crown-copyright",
        "attribution-text": RIGHTS_POLICY["dataset_attribution_statement"],
        "phase": "alpha",
    }
    for field, expected in expected_metadata.items():
        if metadata.get(field) != expected:
            raise EnglandPlanningDataError(
                f"dataset metadata rights/lineage field changed: {field}"
            )
    licence_text = metadata.get("licence-text")
    if not isinstance(licence_text, str) or OGL3_URL not in licence_text:
        raise EnglandPlanningDataError("dataset metadata OGL link changed")

    try:
        page = raw_bodies["dataset_page"].decode("utf-8")
        legalcode = raw_bodies["ogl3_legalcode"].decode("utf-8")
    except UnicodeDecodeError as error:
        raise EnglandPlanningDataError("rights HTML must be UTF-8") from error

    page_markers = (
        "The planning application dataset is incomplete and is not yet ready for use.",
        ">100,627<br>",
        ">Data providers</th>",
        ">6</td>",
        ">2025-09-17</td>",
        "Data created by MHCLG. We will replace this with data from authoritative sources when it is available.",
        "Open Government Licence v.3.0",
        RIGHTS_POLICY["dataset_attribution_statement"],
        BULK_CSV_URL,
    )
    if any(marker not in page for marker in page_markers):
        raise EnglandPlanningDataError("dataset page metadata or rights markers changed")

    legal_markers = (
        "This is version 3.0 of the Open Government Licence.",
        "You are free to:",
        "copy</span>",
        "adapt the Information",
        "commercially and non-commercially",
        "acknowledge the source of the Information",
        "Contains public sector information licensed under the Open Government Licence v3.0.",
        "personal data in the Information",
        "third party rights the Information Provider is not authorised to license",
        "Non-endorsement",
        "No warranty",
    )
    if any(marker not in legalcode for marker in legal_markers):
        raise EnglandPlanningDataError("OGL v3 legal-code markers changed")

    return {
        **RIGHTS_POLICY,
        "assessed_from_dataset_metadata": DATASET_METADATA_URL,
        "assessed_from_dataset_page": DATASET_PAGE_URL,
        "assessed_from_legalcode": OGL3_URL,
        "current_at_retrieval": True,
        "dataset_phase": "alpha",
    }


def _validate_provider_documents(
    raw_bodies: Mapping[str, bytes],
) -> dict[str, dict[str, Any]]:
    providers: dict[str, dict[str, Any]] = {}
    for provider_id, provider_name in PROVIDER_NAMES.items():
        artifact_id = f"provider_{provider_id}"
        document = _json_body(raw_bodies, artifact_id)
        if (
            str(document.get("entity")) != provider_id
            or document.get("organisation-entity") != int(provider_id)
            or document.get("name") != provider_name
            or document.get("typology") != "organisation"
            or document.get("dataset") != "local-authority"
        ):
            raise EnglandPlanningDataError(
                f"provider entity {provider_id} lineage changed"
            )
        providers[provider_id] = {
            "entity": provider_id,
            "local_planning_authority": document.get("local-planning-authority"),
            "name": provider_name,
            "reference": document.get("reference"),
            "source_url": PROVIDER_ENTITY_URLS[provider_id],
        }
    return providers


def _normalized_text(value: str) -> str:
    normalized = unicode_normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")


TERM_PATTERNS = {
    term: _term_pattern(term) for term in EXPLICIT_TERMS + OPTIONAL_TERMS
}


def matched_terms(description: str, terms: Iterable[str]) -> list[str]:
    normalized = _normalized_text(description)
    return [term for term in terms if TERM_PATTERNS[term].search(normalized)]


def _record_hash(row: Mapping[str, str]) -> str:
    ordered = {field: row[field] for field in SOURCE_FIELDS}
    return sha256_bytes(canonical_json(ordered))


def _parse_point(value: str) -> dict[str, Any] | None:
    if not value:
        return None
    match = POINT_RE.fullmatch(value)
    if match is None:
        return {"crs": None, "latitude": None, "longitude": None, "raw": value}
    longitude = float(match.group(1))
    latitude = float(match.group(2))
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise EnglandPlanningDataError("source point is outside WGS84 bounds")
    return {
        "crs": "EPSG:4326",
        "latitude": latitude,
        "longitude": longitude,
        "raw": value,
    }


def _sorted_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _date_ranges(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for field in DATE_FIELDS:
        values = [row[field] for row in rows if row[field]]
        result[field] = {
            "maximum_raw": max(values) if values else None,
            "minimum_raw": min(values) if values else None,
            "nonempty_count": len(values),
        }
    return result


def _geometry_presence(row: Mapping[str, str]) -> str:
    present = [field for field in GEOMETRY_FIELDS if row[field]]
    if not present:
        return "none"
    if len(present) == 1:
        return present[0]
    return "+".join(present)


def _observation(
    row: dict[str, str],
    logical_row_number: int,
    terms: list[str],
    providers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    entity = row["entity"]
    provider_id = row["organisation-entity"]
    if entity not in EXPECTED_CONTEXT_ASSESSMENT:
        raise EnglandPlanningDataError("unreviewed explicit observation encountered")
    return {
        "auto_merge": False,
        "context_assessment": EXPECTED_CONTEXT_ASSESSMENT[entity],
        "manual_review_required": True,
        "matched_terms": terms,
        "observation_id": f"england-planning-data:{entity}",
        "promotion_boundaries": REVIEW_POLICY,
        "provider": dict(providers[provider_id]),
        "raw_dates": {field: row[field] for field in DATE_FIELDS},
        "raw_description": row["description"],
        "raw_geometry": {field: row[field] for field in GEOMETRY_FIELDS},
        "raw_status": {field: row[field] for field in STATUS_FIELDS},
        "record_type": "planning_application_observation",
        "review_only": True,
        "source": {
            "bulk_file_sha256": EXPECTED_CSV_SHA256,
            "dataset": "planning-application",
            "entity_url": f"https://www.planning.data.gov.uk/entity/{entity}",
            "logical_row_number_including_header": logical_row_number,
            "raw_field_hash_algorithm": (
                "sha256(canonical-json-utf8-of-all-26-source-fields)"
            ),
            "raw_field_hash_sha256": _record_hash(row),
            "release_id": RELEASE_ID,
            "source_url": BULK_CSV_URL,
        },
        "source_attributes": {field: row[field] for field in SOURCE_FIELDS},
        "source_point": _parse_point(row["point"]),
    }


def _optional_candidate(
    row: dict[str, str],
    logical_row_number: int,
    term: str,
) -> dict[str, Any]:
    return {
        "address_text": row["address-text"],
        "decision_date": row["decision-date"],
        "description": row["description"],
        "entity": row["entity"],
        "logical_row_number_including_header": logical_row_number,
        "organisation_entity": row["organisation-entity"],
        "planning_application_status": row["planning-application-status"],
        "planning_decision": row["planning-decision"],
        "raw_field_hash_sha256": _record_hash(row),
        "reference": row["reference"],
        "source_geometry": {field: row[field] for field in GEOMETRY_FIELDS},
        "term": term,
    }


def _parse_snapshot(
    body: bytes,
    providers: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise EnglandPlanningDataError("bulk CSV is not UTF-8") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != SOURCE_FIELDS:
        raise EnglandPlanningDataError("bulk CSV source fields changed")

    rows: list[dict[str, str]] = []
    provider_counts: Counter[str] = Counter()
    field_nonempty_counts: Counter[str] = Counter()
    status_counts = {field: Counter() for field in STATUS_FIELDS}
    geometry_counts: Counter[str] = Counter()
    entity_values: set[str] = set()
    observations: list[dict[str, Any]] = []
    optional_candidates = {term: [] for term in OPTIONAL_TERMS}
    explicit_term_counts: Counter[str] = Counter()

    for logical_row_number, raw_row in enumerate(reader, start=2):
        if None in raw_row or set(raw_row) != set(SOURCE_FIELDS):
            raise EnglandPlanningDataError("bulk CSV contains a malformed row")
        row = {field: raw_row[field] for field in SOURCE_FIELDS}
        if row["dataset"] != "planning-application":
            raise EnglandPlanningDataError("bulk CSV contains another dataset")
        if row["prefix"] != "planning-application" or row["typology"] != "geography":
            raise EnglandPlanningDataError("bulk CSV entity lineage changed")
        provider_id = row["organisation-entity"]
        if provider_id not in providers:
            raise EnglandPlanningDataError(
                f"bulk CSV references an unpinned provider: {provider_id!r}"
            )
        entity = row["entity"]
        if not entity.isdigit() or entity in entity_values:
            raise EnglandPlanningDataError("bulk CSV entity identifiers are invalid")
        entity_values.add(entity)
        rows.append(row)
        provider_counts[provider_id] += 1
        for field, value in row.items():
            if value:
                field_nonempty_counts[field] += 1
        for field in STATUS_FIELDS:
            status_counts[field][row[field]] += 1
        geometry_counts[_geometry_presence(row)] += 1

        explicit = matched_terms(row["description"], EXPLICIT_TERMS)
        optional = matched_terms(row["description"], OPTIONAL_TERMS)
        if explicit:
            explicit_term_counts.update(explicit)
            observations.append(
                _observation(row, logical_row_number, explicit, providers)
            )
        else:
            for term in optional:
                optional_candidates[term].append(
                    _optional_candidate(row, logical_row_number, term)
                )

    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise EnglandPlanningDataError("bulk CSV row count changed")
    if len(entity_values) != EXPECTED_SOURCE_ROWS:
        raise EnglandPlanningDataError("bulk CSV entity uniqueness changed")
    if _sorted_counts(provider_counts) != EXPECTED_PROVIDER_ROW_COUNTS:
        raise EnglandPlanningDataError("bulk CSV provider row counts changed")
    if tuple(row["source_attributes"]["entity"] for row in observations) != EXPECTED_EXPLICIT_ENTITIES:
        raise EnglandPlanningDataError("explicit phrase match set changed")
    for term, expected_entities in EXPECTED_OPTIONAL_ENTITIES.items():
        actual_entities = tuple(row["entity"] for row in optional_candidates[term])
        if actual_entities != expected_entities:
            raise EnglandPlanningDataError(f"optional phrase review set changed: {term}")

    inventory = {
        "format": INVENTORY_FORMAT,
        "source_dataset": "planning-application",
        "source_fields": list(SOURCE_FIELDS),
        "source_file": {
            "bytes": len(body),
            "etag": EXPECTED_CSV_ETAG,
            "last_modified": EXPECTED_CSV_LAST_MODIFIED,
            "sha256": EXPECTED_CSV_SHA256,
            "url": BULK_CSV_URL,
            "version_id": EXPECTED_CSV_VERSION_ID,
        },
        "source_rows": len(rows),
        "unique_entity_count": len(entity_values),
        "entity_minimum": min(map(int, entity_values)),
        "entity_maximum": max(map(int, entity_values)),
        "field_nonempty_counts": {
            field: field_nonempty_counts[field] for field in SOURCE_FIELDS
        },
        "date_ranges_raw": _date_ranges(rows),
        "geometry_field_presence_counts": _sorted_counts(geometry_counts),
        "raw_status_value_counts": {
            field: _sorted_counts(counter)
            for field, counter in status_counts.items()
        },
        "row_provider_inventory": [
            {
                **dict(providers[provider_id]),
                "row_count": provider_counts[provider_id],
            }
            for provider_id in sorted(providers, key=int)
        ],
        "provider_statistic_reconciliation": {
            "bulk_row_provider_entity_count": len(provider_counts),
            "official_page_data_provider_statistic": EXPECTED_PAGE_PROVIDER_COUNT,
            "reconciled": False,
            "reason": (
                "The official page supplies only the aggregate value 6, while the exact "
                "bulk rows contain four organisation-entity values. The source does not "
                "identify the other two counted providers or define this discrepancy."
            ),
        },
    }

    phrase_review = {
        "format": PHRASE_REVIEW_FORMAT,
        "description_field": "description",
        "normalization": (
            "NFKC, Unicode casefold, whitespace collapsed, ASCII alphanumeric boundaries"
        ),
        "explicit": {
            "context_classification_counts": _sorted_counts(
                Counter(
                    row["context_assessment"]["classification"]
                    for row in observations
                )
            ),
            "included_observation_count": len(observations),
            "terms": list(EXPLICIT_TERMS),
            "term_hit_counts": {
                term: explicit_term_counts[term] for term in EXPLICIT_TERMS
            },
            "manual_context_assessment": EXPECTED_CONTEXT_ASSESSMENT,
        },
        "optional_incremental_outside_explicit": {
            "data hall": {
                "candidates": optional_candidates["data hall"],
                "decision": "not_added_no_incremental_candidates",
                "incremental_count": len(optional_candidates["data hall"]),
            },
            "server room": {
                "candidates": optional_candidates["server room"],
                "decision": "excluded_after_review_low_precision",
                "incremental_count": len(optional_candidates["server room"]),
                "review_reason": (
                    "All three descriptions concern small internal server-room drainage "
                    "or partition works; the phrase does not establish a data centre."
                ),
            },
            "data processing": {
                "candidates": optional_candidates["data processing"],
                "decision": "not_added_no_incremental_candidates",
                "incremental_count": len(optional_candidates["data processing"]),
            },
        },
        "optional_observations_added": 0,
        "recall_claimed": False,
    }
    return observations, inventory, phrase_review


def _schema_document() -> dict[str, Any]:
    return {
        "format": SCHEMA_FORMAT,
        "schema_version": SCHEMA_VERSION,
        "record_type": "planning_application_observation",
        "required_observation_fields": [
            "auto_merge",
            "context_assessment",
            "manual_review_required",
            "matched_terms",
            "observation_id",
            "promotion_boundaries",
            "provider",
            "raw_dates",
            "raw_description",
            "raw_geometry",
            "raw_status",
            "record_type",
            "review_only",
            "source",
            "source_attributes",
            "source_point",
        ],
        "source_fields": list(SOURCE_FIELDS),
        "raw_field_hash_algorithm": (
            "sha256(canonical-json-utf8-of-all-26-source-fields)"
        ),
        "semantic_boundaries": REVIEW_POLICY,
        "notes": [
            "Raw strings are not normalized or repaired.",
            "A planning point is not asserted to be a building or campus centroid.",
            "Planning status and decision values are not facility lifecycle status.",
        ],
    }


def _observations_csv(observations: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "observation_id",
        "record_type",
        "review_only",
        "auto_merge",
        "matched_terms",
        "context_classification",
        "provider_entity",
        "provider_name",
        "source_logical_row_number",
        "source_raw_field_hash_sha256",
        "source_bulk_file_sha256",
        "source_point_longitude",
        "source_point_latitude",
    ] + [f"source_{field}" for field in SOURCE_FIELDS]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for observation in observations:
        point = observation["source_point"] or {}
        row = {
            "observation_id": observation["observation_id"],
            "record_type": observation["record_type"],
            "review_only": "true",
            "auto_merge": "false",
            "matched_terms": "|".join(observation["matched_terms"]),
            "context_classification": observation["context_assessment"][
                "classification"
            ],
            "provider_entity": observation["provider"]["entity"],
            "provider_name": observation["provider"]["name"],
            "source_logical_row_number": observation["source"][
                "logical_row_number_including_header"
            ],
            "source_raw_field_hash_sha256": observation["source"][
                "raw_field_hash_sha256"
            ],
            "source_bulk_file_sha256": observation["source"][
                "bulk_file_sha256"
            ],
            "source_point_longitude": point.get("longitude", ""),
            "source_point_latitude": point.get("latitude", ""),
        }
        row.update(
            {
                f"source_{field}": observation["source_attributes"][field]
                for field in SOURCE_FIELDS
            }
        )
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _attribution_text(retrieved_at: str) -> bytes:
    return (
        "England Planning Data planning-application source\n"
        "\n"
        f"Dataset page: {DATASET_PAGE_URL}\n"
        f"Bulk CSV: {BULK_CSV_URL}\n"
        f"Retrieved: {retrieved_at}\n"
        f"Source attribution: {RIGHTS_POLICY['dataset_attribution_statement']}\n"
        "Licence: Open Government Licence v3.0\n"
        f"Licence text: {OGL3_URL}\n"
        "\n"
        "Contains public sector information licensed under the Open Government "
        "Licence v3.0. Data Center Atlas filtered descriptions, preserved raw "
        "source values, added hashes and review boundaries, and made no facility "
        "identity, lifecycle, capacity, type, or energy inference.\n"
    ).encode("utf-8")


def _readme_text(retrieved_at: str) -> bytes:
    return f"""# England Planning Data planning observations

This frozen bundle is a conservative review lane, not a data-centre or
construction inventory. It retains the exact official Planning Data
`planning-application` bulk CSV retrieved at `{retrieved_at}`. The official
source warns that the dataset is incomplete and not yet ready for use and says
its MHCLG-created data will be replaced by authoritative sources when available.

The snapshot contains 100,627 planning rows. The official page reports six data
providers, but the bulk rows contain four organisation entities: Adur (7,585),
Camden (77,499), Doncaster (1,914), and Worthing (13,629). The source does not
identify or explain the two-count difference, so this bundle leaves it
unreconciled.

Description matching uses the explicit phrases `data centre`, `data center`,
`datacentre`, and `data-center`, with NFKC/case/whitespace normalization and
token boundaries. Four rows match. They remain planning observations; one uses
the phrase only to exclude an existing data centre from the proposed change of
use. The exact-match audit therefore comprises three direct-scope mentions and
one context-only exclusion, not four construction or data-centre leads.
Optional incremental review found zero `data hall` rows, three `server
room` rows, and zero `data processing` rows outside the explicit set. The three
server-room rows are excluded because they concern small internal drainage or
partition works and do not establish a data centre.

Every observation is `review_only: true` and `auto_merge: false`. Planning
status and decisions are not construction or operating status. The release
does not establish facility identity, unique sites, lifecycle, type, capacity,
power, energy consumption, PUE, ownership, operator, workload, or completion.

All eight official inputs are retained byte-for-byte under `raw/`. The OGL v3
rights gate, source-page warning, dataset metadata, four provider lookups, CSV
object metadata, exact request lineage, and raw hashes are recorded in
`assessment.json`. `source-inventory.json` inventories rows, providers, fields,
status values, dates, and geometry presence. `phrase-review.json` preserves the
optional candidates and inclusion decisions. `observations.jsonl` and
`observations.csv` preserve all 26 raw fields and a canonical raw-field hash.

Validate with zero network requests:

```sh
python3 scripts/validate_england_planning_data.py
```

The manifest binds every retained and derived byte. Source drift requires a
new release definition rather than mutation of this frozen bundle.
""".encode("utf-8")


def derive_release_files(
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
    retrieved_at: str,
) -> dict[str, bytes]:
    """Validate raw inputs and derive every non-manifest release artifact."""

    retrieved_at = _timestamp(retrieved_at, "retrieved_at")
    official_artifacts = _validate_retrievals(retrievals, raw_bodies)
    rights = _validate_rights_and_metadata(raw_bodies)
    providers = _validate_provider_documents(raw_bodies)
    observations, inventory, phrase_review = _parse_snapshot(
        raw_bodies["bulk_csv"], providers
    )

    csv_headers = official_artifacts["bulk_csv"]["headers"]
    if csv_headers.get("last-modified") != EXPECTED_CSV_LAST_MODIFIED:
        raise EnglandPlanningDataError("bulk CSV Last-Modified changed")
    if csv_headers.get("etag") != EXPECTED_CSV_ETAG:
        raise EnglandPlanningDataError("bulk CSV ETag changed")
    if csv_headers.get("x-amz-version-id") != EXPECTED_CSV_VERSION_ID:
        raise EnglandPlanningDataError("bulk CSV S3 version ID changed")

    assessment = {
        "format": ASSESSMENT_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "assessed_at": retrieved_at,
        "source": {
            "bulk_csv_url": BULK_CSV_URL,
            "collector_last_ran_on": "2025-09-17",
            "dataset_id": "planning-application",
            "dataset_page_url": DATASET_PAGE_URL,
            "dataset_phase": "alpha",
            "new_data_last_found_on": "2025-09-17",
            "origin_statement": (
                "Data created by MHCLG. We will replace this with data from "
                "authoritative sources when it is available."
            ),
            "publisher": "Ministry of Housing, Communities and Local Government",
        },
        "coverage_assessment": {
            "complete_england_coverage_claimed": False,
            "global_coverage_claimed": False,
            "official_page_data_provider_statistic": EXPECTED_PAGE_PROVIDER_COUNT,
            "represented_bulk_row_provider_entities": len(providers),
            "source_row_count": inventory["source_rows"],
            "source_warning": (
                "The planning application dataset is incomplete and is not yet "
                "ready for use."
            ),
            "warning_acknowledged": True,
        },
        "official_open_artifacts": official_artifacts,
        "retrieval_batch": {
            "network_requests": len(RAW_ARTIFACTS),
            "official_first_party_requests": len(RAW_ARTIFACTS),
            "raw_artifacts_retained": len(RAW_ARTIFACTS),
            "retrieval_mode": "bounded_fetch_build",
            "validator_network_requests": 0,
        },
        "rights_assessment": rights,
        "selection_assessment": {
            "description_field": "description",
            "explicit_context_classification_counts": phrase_review["explicit"][
                "context_classification_counts"
            ],
            "explicit_observations": len(observations),
            "explicit_terms": list(EXPLICIT_TERMS),
            "optional_incremental_counts": {
                term: phrase_review["optional_incremental_outside_explicit"][term][
                    "incremental_count"
                ]
                for term in OPTIONAL_TERMS
            },
            "optional_observations_added": 0,
            "recall_claimed": False,
        },
        "inference_policy": REVIEW_POLICY,
        "reproducibility": {
            "all_source_rows_retained_in_exact_bulk_file": True,
            "all_observation_source_fields_retained": True,
            "manifest_hashes_every_bundle_file_except_itself_and_sidecar": True,
            "offline_rederivation_supported": True,
            "raw_field_hash_algorithm": (
                "sha256(canonical-json-utf8-of-all-26-source-fields)"
            ),
        },
    }

    return {
        DERIVED_FILENAMES["assessment"]: canonical_json(assessment),
        DERIVED_FILENAMES["attribution"]: _attribution_text(retrieved_at),
        DERIVED_FILENAMES["definition"]: canonical_json(source_definition()),
        DERIVED_FILENAMES["inventory"]: canonical_json(inventory),
        DERIVED_FILENAMES["observations_csv"]: _observations_csv(observations),
        DERIVED_FILENAMES["observations_jsonl"]: jsonl_bytes(observations),
        DERIVED_FILENAMES["phrase_review"]: canonical_json(phrase_review),
        DERIVED_FILENAMES["readme"]: _readme_text(retrieved_at),
        DERIVED_FILENAMES["schema"]: canonical_json(_schema_document()),
    }


def _artifact_role(filename: str) -> str:
    if filename.startswith("raw/"):
        if "open-government-licence" in filename:
            return "rights_evidence"
        if "dataset.html" in filename or "dataset.json" in filename:
            return "source_metadata_and_rights_evidence"
        if "provider-entity" in filename:
            return "provider_lineage"
        return "open_source_data"
    if filename == "ATTRIBUTION.txt":
        return "attribution"
    if filename == "observations.jsonl" or filename == "observations.csv":
        return "review_only_planning_observations"
    return "derived_assessment"


def _license_scope(filename: str) -> str:
    if filename.startswith("raw/") and "open-government-licence" in filename:
        return "rights_evidence_copy"
    if filename.startswith("raw/") and (
        "dataset.html" in filename or "dataset.json" in filename
    ):
        return "rights_and_metadata_evidence_copy"
    if filename.startswith("raw/"):
        return "OGL-3.0"
    return "derived_by_datacenter_atlas_with_source_attribution"


def _manifest_for_directory(path: Path, retrieved_at: str) -> bytes:
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
            "license_scope": _license_scope(relative),
            "role": _artifact_role(relative),
            "sha256": sha256_bytes(body),
        }
    return canonical_json(
        {
            "format": RELEASE_FORMAT,
            "release_id": RELEASE_ID,
            "retrieved_at": retrieved_at,
            "schema_version": SCHEMA_VERSION,
            "files": files,
        }
    )


def _freeze_tree(path: Path) -> None:
    for entry in path.rglob("*"):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    path.chmod(0o555)


def write_release_bundle(
    output: str | Path,
    retrievals: Mapping[str, Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
    retrieved_at: str,
    *,
    freeze: bool = True,
) -> Path:
    """Write a new release atomically; existing outputs are never overwritten."""

    output_path = Path(output)
    if output_path.exists() or output_path.is_symlink():
        raise EnglandPlanningDataError("output release already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    retrieved_at = _timestamp(retrieved_at, "retrieved_at")
    derived = derive_release_files(retrievals, raw_bodies, retrieved_at)

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    )
    try:
        for artifact_id, specification in RAW_ARTIFACTS.items():
            destination = temporary / specification["filename"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw_bodies[artifact_id])
        for filename, body in derived.items():
            (temporary / filename).write_bytes(body)
        manifest_body = _manifest_for_directory(temporary, retrieved_at)
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        os.replace(temporary, output_path)
        if freeze:
            _freeze_tree(output_path)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_path


def _expected_file_set() -> set[str]:
    return {
        *(specification["filename"] for specification in RAW_ARTIFACTS.values()),
        *DERIVED_FILENAMES.values(),
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EnglandPlanningDataError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise EnglandPlanningDataError(f"{label} is not canonical JSON")
    return value


def validate_release_bundle(path: str | Path) -> dict[str, Any]:
    """Validate a frozen release with no network access."""

    release = Path(path)
    if not release.is_dir() or release.is_symlink():
        raise EnglandPlanningDataError("release must be a non-symlink directory")
    actual_files = {
        entry.relative_to(release).as_posix()
        for entry in release.rglob("*")
        if entry.is_file()
    }
    if actual_files != _expected_file_set():
        raise EnglandPlanningDataError("release file set changed")

    manifest = _load_canonical_json(release / MANIFEST_FILENAME, "manifest")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise EnglandPlanningDataError("manifest identity changed")
    retrieved_at = _timestamp(manifest.get("retrieved_at"), "manifest.retrieved_at")
    expected_manifest = _manifest_for_directory(release, retrieved_at)
    if (release / MANIFEST_FILENAME).read_bytes() != expected_manifest:
        raise EnglandPlanningDataError("manifest does not bind the release files")
    expected_sidecar = (
        f"{sha256_bytes(expected_manifest)}  {MANIFEST_FILENAME}\n".encode("utf-8")
    )
    if (release / MANIFEST_HASH_FILENAME).read_bytes() != expected_sidecar:
        raise EnglandPlanningDataError("manifest SHA-256 sidecar changed")

    assessment = _load_canonical_json(
        release / DERIVED_FILENAMES["assessment"], "assessment"
    )
    if assessment.get("inference_policy") != REVIEW_POLICY:
        raise EnglandPlanningDataError("review-only inference policy changed")
    if assessment.get("rights_assessment", {}).get("rights_gate_passed") is not True:
        raise EnglandPlanningDataError("rights gate is not passed")
    if assessment.get("retrieval_batch", {}).get("validator_network_requests") != 0:
        raise EnglandPlanningDataError("offline validator network boundary changed")

    artifacts = _as_mapping(
        assessment.get("official_open_artifacts"), "official_open_artifacts"
    )
    retrievals = {
        artifact_id: {
            "content_type": artifacts[artifact_id]["content_type"],
            "effective_url": artifacts[artifact_id]["effective_url"],
            "headers": artifacts[artifact_id]["headers"],
            "http_status": artifacts[artifact_id]["http_status"],
            "url": artifacts[artifact_id]["url"],
        }
        for artifact_id in RAW_ARTIFACTS
    }
    raw_bodies = {
        artifact_id: (release / specification["filename"]).read_bytes()
        for artifact_id, specification in RAW_ARTIFACTS.items()
    }
    reproduced = derive_release_files(retrievals, raw_bodies, retrieved_at)
    for filename, expected_body in reproduced.items():
        if (release / filename).read_bytes() != expected_body:
            raise EnglandPlanningDataError(
                f"offline reproduction mismatch: {filename}"
            )

    observations = [
        json.loads(line)
        for line in (release / DERIVED_FILENAMES["observations_jsonl"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    if len(observations) != len(EXPECTED_EXPLICIT_ENTITIES):
        raise EnglandPlanningDataError("observation count changed")
    for observation in observations:
        if (
            observation.get("record_type") != "planning_application_observation"
            or observation.get("review_only") is not True
            or observation.get("auto_merge") is not False
            or observation.get("promotion_boundaries") != REVIEW_POLICY
        ):
            raise EnglandPlanningDataError("observation promotion boundary changed")

    return {
        "assessment": assessment,
        "definition": _load_canonical_json(
            release / DERIVED_FILENAMES["definition"], "definition"
        ),
        "inventory": _load_canonical_json(
            release / DERIVED_FILENAMES["inventory"], "inventory"
        ),
        "manifest": manifest,
        "observations": observations,
        "phrase_review": _load_canonical_json(
            release / DERIVED_FILENAMES["phrase_review"], "phrase review"
        ),
        "schema": _load_canonical_json(
            release / DERIVED_FILENAMES["schema"], "schema"
        ),
    }


def is_frozen_release(path: str | Path) -> bool:
    """Return whether every bundle directory/file has the pinned read-only mode."""

    release = Path(path)
    if release.stat().st_mode & 0o777 != 0o555:
        return False
    return all(
        entry.stat().st_mode & 0o777 == (0o555 if entry.is_dir() else 0o444)
        for entry in release.rglob("*")
    )


def thaw_for_test(path: str | Path) -> None:
    """Make a copied bundle mutable for negative tests only."""

    release = Path(path)
    release.chmod(stat.S_IRWXU)
    for entry in release.rglob("*"):
        entry.chmod(stat.S_IRWXU if entry.is_dir() else stat.S_IRUSR | stat.S_IWUSR)
