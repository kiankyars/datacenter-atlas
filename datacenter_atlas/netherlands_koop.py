"""Build and validate a conservative Netherlands KOOP publication review lane.

The source is the official KOOP SRU 2.0 collection of official publications.
Every selected publication remains a review-only permit-process observation.
Publication stages, project language, geometry, and ancillary power language are
preserved without promoting facility identity, lifecycle, construction,
operation, type, capacity, power, energy, PUE, workload, or unique-site counts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
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
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


SCHEMA_VERSION = 1
RELEASE_ID = "netherlands-koop-official-publications-2026-07-18-v1"
DEFINITION_FORMAT = "datacenter-atlas-netherlands-koop-definition-v1"
RELEASE_FORMAT = "datacenter-atlas-netherlands-koop-release-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-netherlands-koop-assessment-v1"
INVENTORY_FORMAT = "datacenter-atlas-netherlands-koop-inventory-v1"
RELATIONSHIP_FORMAT = "datacenter-atlas-netherlands-koop-advisories-v1"
SCHEMA_FORMAT = "datacenter-atlas-netherlands-koop-schema-v1"

SRU_ENDPOINT = "https://repository.overheid.nl/sru"
SRU_QUERY = (
    'c.product-area=="officielepublicaties" AND '
    'dt.title any "datacenter datacentrum" AND '
    'dt.type=="omgevingsvergunning" AND '
    'dt.available>="2026-01-01"'
)
SRU_PARAMETERS = {
    "httpAccept": "application/xml",
    "maximumRecords": "100",
    "operation": "searchRetrieve",
    "query": SRU_QUERY,
    "recordSchema": "gzd",
    "startRecord": "1",
    "version": "2.0",
}
SRU_REQUEST_URL = SRU_ENDPOINT + "?" + urlencode(
    SRU_PARAMETERS, quote_via=quote
)
SRU_RESULT_PRECISION = "info:srw/vocabulary/resultCountPrecision/1/estimate"

SRU_GUIDE_URL = (
    "https://data.overheid.nl/sites/default/files/dataset/"
    "d0cca537-44ea-48cf-9880-fa21e1a7058f/resources/HandleidingSRU2.0.pdf"
)
KOOP_COPYRIGHT_URL = "https://www.koopoverheid.nl/service/copyright"
DATASET_PAGE_URL = "https://data.overheid.nl/dataset/officiele-bekendmakingen"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

EXPECTED_IDENTIFIERS = (
    "gmb-2026-31793",
    "gmb-2026-334667",
    "prb-2026-6693",
    "prb-2026-1555",
    "prb-2026-5306",
    "gmb-2026-175789",
    "gmb-2026-334666",
    "gmb-2026-135103",
    "prb-2026-1810",
    "prb-2026-11665",
    "prb-2026-2233",
    "prb-2026-11305",
    "prb-2026-1413",
    "prb-2026-10866",
    "prb-2026-11319",
    "prb-2026-11662",
    "gmb-2026-299345",
    "gmb-2026-162314",
    "gmb-2026-20613",
    "prb-2026-11613",
)

DIRECT_CLASSIFICATION = "direct_project_build_expansion_candidate"
CONTEXT_CLASSIFICATION = "ancillary_or_context_exclusion"


def _classification(
    classification: str,
    process_stage: str,
    project_label: str,
    reason: str,
    advisory_group_id: str | None = None,
    untyped_context_statements: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "advisory_group_id": advisory_group_id,
        "classification": classification,
        "process_stage": process_stage,
        "project_label": project_label,
        "reason": reason,
        "untyped_context_statements": list(untyped_context_statements),
    }


CLASSIFICATION_CONTRACT = {
    "gmb-2026-31793": _classification(
        CONTEXT_CLASSIFICATION,
        "application_received",
        "Ecoracks EOS battery systems",
        "The permit concerns two battery systems beside an existing data centre, not construction or expansion of the data centre.",
        "koop-adv-ecoracks-eos-batteries",
    ),
    "gmb-2026-334667": _classification(
        CONTEXT_CLASSIFICATION,
        "decision_on_application",
        "Ecoracks EOS battery systems",
        "The decision concerns two battery systems beside an existing data centre, not construction or expansion of the data centre.",
        "koop-adv-ecoracks-eos-batteries",
    ),
    "prb-2026-6693": _classification(
        CONTEXT_CLASSIFICATION,
        "application_received",
        "Equinix AM6 energy generation",
        "The permit concerns energy generation for an existing data centre; it does not establish data-centre construction or expansion.",
        None,
        ("grootschalig opwekken energie (50 MW of meer) t.b.v. datacentrum Equinix AM6",),
    ),
    "prb-2026-1555": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "Linieweg building B data-centre permit",
        "The official abstract describes realization of building B within a data-centre campus.",
    ),
    "prb-2026-5306": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "AMS11 phase 1",
        "The official title and abstract describe establishing data centre AMS11 phase 1.",
        "koop-adv-ams11-koolhovenlaan-1",
    ),
    "gmb-2026-175789": _classification(
        DIRECT_CLASSIFICATION,
        "decision_period_extended",
        "Boerhaaveweg 10 data-centre application",
        "The publication extends the decision period for an application to realize a data centre.",
        "koop-adv-boerhaaveweg-10",
    ),
    "gmb-2026-334666": _classification(
        CONTEXT_CLASSIFICATION,
        "application_received",
        "Cateringweg 5 existing data-centre legalization",
        "The full text says the application seeks legalization of an existing data centre, not a new build or expansion.",
    ),
    "gmb-2026-135103": _classification(
        DIRECT_CLASSIFICATION,
        "application_received",
        "Boerhaaveweg 10 data-centre application",
        "The official title and abstract describe an application to realize a data centre.",
        "koop-adv-boerhaaveweg-10",
    ),
    "prb-2026-1810": _classification(
        DIRECT_CLASSIFICATION,
        "application_received",
        "Archangelkade Serverfarm phase 3",
        "The publication concerns changing a granted permit to rebuild a data centre and identifies Serverfarm phase 3.",
        "koop-adv-archangelkade-serverfarm",
    ),
    "prb-2026-11665": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "Koolhovenlaan 142 data-centre project",
        "The granted permit expressly concerns realization of a data centre.",
        "koop-adv-koolhovenlaan-142",
    ),
    "prb-2026-2233": _classification(
        DIRECT_CLASSIFICATION,
        "permit_modified",
        "Goodman De Liede data-centre permit modification",
        "The publication concerns modification of a granted permit for establishing and operating a data centre.",
    ),
    "prb-2026-11305": _classification(
        DIRECT_CLASSIFICATION,
        "final_permit_decision",
        "QTS EEMS02 boundary modification",
        "The full text confirms a granted permit to change the boundary of data centre QTS EEMS02.",
    ),
    "prb-2026-1413": _classification(
        DIRECT_CLASSIFICATION,
        "application_received",
        "Archangelkade Serverfarm phase 3",
        "The official title and abstract describe an application to realize a data centre.",
        "koop-adv-archangelkade-serverfarm",
    ),
    "prb-2026-10866": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "AMS11 phase 1",
        "The official title and abstract describe construction of data centre AMS11 with an office.",
        "koop-adv-ams11-koolhovenlaan-1",
    ),
    "prb-2026-11319": _classification(
        DIRECT_CLASSIFICATION,
        "draft_decision_open_for_inspection",
        "Equinix AM9 and AM10",
        "The draft decision concerns establishment of Equinix data centres AM9 and AM10.",
    ),
    "prb-2026-11662": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "Koolhovenlaan 142 data-centre project",
        "The granted permit expressly concerns realization of data-centre phase 2.",
        "koop-adv-koolhovenlaan-142",
    ),
    "gmb-2026-299345": _classification(
        CONTEXT_CLASSIFICATION,
        "application_received",
        "De Kwakel medium-voltage connection",
        "The permit concerns an external medium-voltage connection to a named data centre, not data-centre construction or expansion.",
        "koop-adv-de-kwakel-grid-connection",
    ),
    "gmb-2026-162314": _classification(
        CONTEXT_CLASSIFICATION,
        "application_rejected",
        "De Kwakel medium-voltage connection",
        "The publication rejects or leaves unprocessed an application for an external grid connection, not data-centre construction or expansion.",
        "koop-adv-de-kwakel-grid-connection",
    ),
    "gmb-2026-20613": _classification(
        CONTEXT_CLASSIFICATION,
        "application_received",
        "De Kwakel medium-voltage connection",
        "The permit concerns an external medium-voltage connection to a named data centre, not data-centre construction or expansion.",
        "koop-adv-de-kwakel-grid-connection",
    ),
    "prb-2026-11613": _classification(
        DIRECT_CLASSIFICATION,
        "permit_granted",
        "Koolhovenlaan 142 data-centre project",
        "The granted permit expressly concerns establishing data-centre phase 1.",
        "koop-adv-koolhovenlaan-142",
    ),
}

ADVISORY_GROUPS = (
    {
        "advisory_group_id": "koop-adv-ecoracks-eos-batteries",
        "basis": "Same EHV-ZP2026-000644 case, description, address, and source point; application and decision publications.",
        "members": ["gmb-2026-31793", "gmb-2026-334667"],
        "relationship_type": "same_permit_case_sequence_candidate",
    },
    {
        "advisory_group_id": "koop-adv-ams11-koolhovenlaan-1",
        "basis": "Same Koolhovenlaan 1 location and AMS11 label across environment and building permits.",
        "members": ["prb-2026-5306", "prb-2026-10866"],
        "relationship_type": "same_project_multi_permit_candidate",
    },
    {
        "advisory_group_id": "koop-adv-boerhaaveweg-10",
        "basis": "Same Boerhaaveweg 10 title, geometry, and point across application and decision-period extension.",
        "members": ["gmb-2026-135103", "gmb-2026-175789"],
        "relationship_type": "same_permit_process_sequence_candidate",
    },
    {
        "advisory_group_id": "koop-adv-archangelkade-serverfarm",
        "basis": "Same Archangelkade 1 geometry and points; initial realization and permit-change publications.",
        "members": ["prb-2026-1413", "prb-2026-1810"],
        "relationship_type": "same_project_permit_sequence_candidate",
    },
    {
        "advisory_group_id": "koop-adv-koolhovenlaan-142",
        "basis": "Same Koolhovenlaan 142 point with phase 1, phase 2, and spatial permit publications.",
        "members": ["prb-2026-11613", "prb-2026-11662", "prb-2026-11665"],
        "relationship_type": "same_project_multi_phase_or_permit_candidate",
    },
    {
        "advisory_group_id": "koop-adv-de-kwakel-grid-connection",
        "basis": "Same named medium-voltage connection route; two stages share case Z2026-00000358 and a later application has Z2026-00006143.",
        "members": ["gmb-2026-20613", "gmb-2026-162314", "gmb-2026-299345"],
        "relationship_type": "same_ancillary_project_sequence_candidate",
    },
)

DETAIL_IDENTIFIERS = (
    "gmb-2026-31793",
    "gmb-2026-334667",
    "prb-2026-6693",
    "gmb-2026-334666",
    "gmb-2026-299345",
    "gmb-2026-162314",
    "gmb-2026-20613",
    "prb-2026-11305",
)

DETAIL_MARKERS = {
    "gmb-2026-31793": ("EHV-ZP2026-000644", "2 EOS batterijsystemen"),
    "gmb-2026-334667": ("EHV-ZP2026-000644", "Besluit: Verleend"),
    "prb-2026-6693": ("50 MW of meer", "datacentrum Equinix AM6"),
    "gmb-2026-334666": ("bestaande datacenter", "OD2026-0043791"),
    "gmb-2026-299345": ("Z2026-00006143", "middenspanningsverbinding"),
    "gmb-2026-162314": ("Z2026-00000358", "buiten behandeling gelaten"),
    "gmb-2026-20613": ("Z2026-00000358", "middenspanningsverbinding"),
    "prb-2026-11305": ("Quality Technology Service", "verandering begrenzing datacenter"),
}

RIGHTS_POLICY = {
    "attachments_assessed_or_redistributed": False,
    "cc0_reference_url": CC0_URL,
    "dataset_catalog_license": "CC-0 (1.0)",
    "express_text_copyright_not_overridden": True,
    "image_or_video_reuse_claimed": False,
    "koop_site_text_policy": "CC0 1.0 subject to express copyright notices",
    "metadata_and_selected_official_text_retained": True,
    "pdf_odt_and_other_publication_attachments_fetched": False,
    "rights_gate_passed_for_retained_scope": True,
}

REVIEW_POLICY = {
    "accepted_relationships": 0,
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
    "permit_stage_is_facility_status": False,
    "promotion_permitted": False,
    "pue": None,
    "review_only": True,
    "source_supported_construction": False,
    "unique_physical_site_count": None,
    "workload": None,
}

RAW_PATHS = {
    "sru_search": "raw/sru-search.xml",
    **{
        f"detail_{identifier}": f"raw/details/{identifier}.xml"
        for identifier in DETAIL_IDENTIFIERS
    },
    "sru_guide": "raw/sru-guide.pdf",
    "koop_copyright": "raw/koop-copyright.html",
    "dataset_page": "raw/data-overheid-officiele-bekendmakingen.html",
}

ARTIFACT_URLS = {
    "sru_search": SRU_REQUEST_URL,
    **{
        f"detail_{identifier}": (
            "https://repository.overheid.nl/frbr/officielepublicaties/"
            f"{identifier.split('-', 1)[0]}/2026/{identifier}/1/xml/{identifier}.xml"
        )
        for identifier in DETAIL_IDENTIFIERS
    },
    "sru_guide": SRU_GUIDE_URL,
    "koop_copyright": KOOP_COPYRIGHT_URL,
    "dataset_page": DATASET_PAGE_URL,
}

ARTIFACT_PURPOSES = {
    "sru_search": "single bounded canonical SRU result set",
    **{
        f"detail_{identifier}": "selected XML detail needed for classification boundary review"
        for identifier in DETAIL_IDENTIFIERS
    },
    "sru_guide": "official SRU 2.0 technical documentation",
    "koop_copyright": "official KOOP text and image copyright policy",
    "dataset_page": "official open-data catalog license evidence for the collection",
}

RIGHTS_SCOPES = {
    "sru_search": "CC0_collection_metadata",
    **{
        f"detail_{identifier}": "selected_official_XML_text_only_no_attachments"
        for identifier in DETAIL_IDENTIFIERS
    },
    "sru_guide": "official_documentation_listed_CC0",
    "koop_copyright": "rights_evidence",
    "dataset_page": "dataset_license_evidence",
}

ARTIFACT_ORDER = tuple(RAW_PATHS)
OFFICIAL_HOSTS = frozenset(
    {"repository.overheid.nl", "www.koopoverheid.nl", "data.overheid.nl"}
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

DERIVED_FILENAMES = {
    "assessment": "assessment.json",
    "attribution": "ATTRIBUTION.txt",
    "definition": "definition.json",
    "inventory": "source-inventory.json",
    "observations_csv": "observations.csv",
    "observations_jsonl": "observations.jsonl",
    "readme": "README.md",
    "relationships": "advisory-relationships.json",
    "request_log": "request-log.jsonl",
    "schema": "schema.json",
}
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"


class NetherlandsKoopError(ValueError):
    """Raised when retrieval, derivation, or validation fails closed."""


def canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=True,
    )
    return (text + "\n").encode("utf-8")


def jsonl_bytes(values: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(value) for value in values)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NetherlandsKoopError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NetherlandsKoopError(f"{label} is not RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NetherlandsKoopError(f"{label} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256_bytes(raw)}


def _detail_artifact_id(identifier: str) -> str:
    return f"detail_{identifier}"


def _capture_specs() -> list[dict[str, str]]:
    return [
        {
            "artifact_id": artifact_id,
            "path": RAW_PATHS[artifact_id],
            "request_purpose": ARTIFACT_PURPOSES[artifact_id],
            "rights_scope": RIGHTS_SCOPES[artifact_id],
            "url": ARTIFACT_URLS[artifact_id],
        }
        for artifact_id in ARTIFACT_ORDER
    ]


def _fetch(
    url: str,
    *,
    timeout: float,
    max_attempts: int,
    user_agent: str,
) -> tuple[dict[str, Any], bytes]:
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        request = Request(
            url,
            headers={
                "Accept": "application/xml,application/pdf,text/html;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": user_agent,
            },
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                completed = time.monotonic()
                result = {
                    "attempt_count": attempt,
                    "content_type": response.headers.get_content_type(),
                    "effective_url": response.geturl(),
                    "elapsed_ms": round((completed - started) * 1000),
                    "http_status": response.status,
                    "response_headers": {
                        name.lower(): response.headers[name]
                        for name in (
                            "Content-Length",
                            "Content-Type",
                            "Date",
                            "ETag",
                            "Last-Modified",
                        )
                        if response.headers.get(name) is not None
                    },
                }
                if response.status != 200 or not body:
                    raise NetherlandsKoopError(
                        f"unexpected response status/body for {url}"
                    )
                return result, body
        except (HTTPError, URLError, TimeoutError, NetherlandsKoopError) as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(0.75 * attempt)
    raise NetherlandsKoopError(f"failed to retrieve {url}") from last_error


def capture_live_sources(
    capture_directory: str | Path,
    *,
    timeout: float = 120.0,
    max_attempts: int = 4,
    pacing_seconds: float = 0.35,
    user_agent: str = "datacenter-atlas-netherlands-koop/1.0",
) -> Path:
    """Fetch the bounded official source set into a new capture directory."""

    destination = Path(capture_directory)
    if destination.exists() or destination.is_symlink():
        raise NetherlandsKoopError("capture directory already exists")
    if timeout <= 0 or max_attempts <= 0 or pacing_seconds < 0:
        raise NetherlandsKoopError("capture retry, pacing, or timeout policy is invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    request_log: list[dict[str, Any]] = []
    artifacts: dict[str, dict[str, Any]] = {}
    previous_completion: float | None = None
    try:
        for request_index, spec in enumerate(_capture_specs(), 1):
            if previous_completion is not None:
                elapsed = time.monotonic() - previous_completion
                if elapsed < pacing_seconds:
                    time.sleep(pacing_seconds - elapsed)
            requested_at = _now()
            response, body = _fetch(
                spec["url"],
                timeout=timeout,
                max_attempts=max_attempts,
                user_agent=user_agent,
            )
            completed_at = _now()
            previous_completion = time.monotonic()
            raw_path = destination / spec["path"]
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(body)
            checkpoint = {"bytes": len(body), "sha256": sha256_bytes(body)}
            artifacts[spec["artifact_id"]] = {
                **spec,
                **checkpoint,
                "content_type": response["content_type"],
                "effective_url": response["effective_url"],
            }
            request_log.append(
                {
                    "artifact_id": spec["artifact_id"],
                    "attempt_count": response["attempt_count"],
                    "bytes": len(body),
                    "completed_at": completed_at,
                    "content_type": response["content_type"],
                    "effective_url": response["effective_url"],
                    "elapsed_ms": response["elapsed_ms"],
                    "http_status": response["http_status"],
                    "method": "GET",
                    "minimum_pacing_seconds": pacing_seconds,
                    "request_index": request_index,
                    "request_purpose": spec["request_purpose"],
                    "requested_at": requested_at,
                    "response_headers": response["response_headers"],
                    "retries_used": response["attempt_count"] - 1,
                    "sha256": checkpoint["sha256"],
                    "url": spec["url"],
                    "user_agent": user_agent,
                }
            )
        request_log_raw = jsonl_bytes(request_log)
        (destination / DERIVED_FILENAMES["request_log"]).write_bytes(
            request_log_raw
        )
        retrieved_at = request_log[-1]["completed_at"]
        capture = {
            "artifacts": artifacts,
            "format": "datacenter-atlas-netherlands-koop-capture-v1",
            "network_requests": len(request_log),
            "release_id": RELEASE_ID,
            "request_log": {
                "bytes": len(request_log_raw),
                "path": DERIVED_FILENAMES["request_log"],
                "sha256": sha256_bytes(request_log_raw),
            },
            "retrieval_policy": {
                "maximum_attempts_per_request": max_attempts,
                "minimum_pacing_seconds": pacing_seconds,
                "timeout_seconds": timeout,
                "user_agent": user_agent,
            },
            "retrieved_at": retrieved_at,
            "schema_version": SCHEMA_VERSION,
        }
        (destination / "capture.json").write_bytes(canonical_json(capture, pretty=True))
        candidate = definition_from_capture(capture)
        (destination / "definition-candidate.json").write_bytes(
            canonical_json(candidate, pretty=True)
        )
        return destination
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def definition_from_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical definition candidate from a completed live capture."""

    artifacts = capture.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(ARTIFACT_ORDER):
        raise NetherlandsKoopError("capture artifact inventory changed")
    return {
        "advisory_relationship_contract": list(ADVISORY_GROUPS),
        "classification_contract": CLASSIFICATION_CONTRACT,
        "expected_identifiers_in_sru_order": list(EXPECTED_IDENTIFIERS),
        "format": DEFINITION_FORMAT,
        "query": {
            "endpoint": SRU_ENDPOINT,
            "expected_number_of_records": 20,
            "expected_result_count_precision": SRU_RESULT_PRECISION,
            "parameters": SRU_PARAMETERS,
            "query": SRU_QUERY,
            "request_url": SRU_REQUEST_URL,
            "single_bounded_request": True,
        },
        "raw_artifacts": {
            artifact_id: dict(artifacts[artifact_id])
            for artifact_id in ARTIFACT_ORDER
        },
        "release_id": RELEASE_ID,
        "request_log": dict(capture["request_log"]),
        "retrieval_policy": dict(capture["retrieval_policy"]),
        "retrieved_at": capture["retrieved_at"],
        "review_policy": REVIEW_POLICY,
        "rights_policy": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
    }


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NetherlandsKoopError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise NetherlandsKoopError(f"{label} must be a JSON object")
    return value


def load_definition(path: str | Path) -> tuple[dict[str, Any], bytes]:
    definition_path = Path(path)
    raw = definition_path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NetherlandsKoopError("source definition is invalid JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value, pretty=True):
        raise NetherlandsKoopError("source definition is not canonical")
    _validate_definition(value)
    return value, raw


def _validate_checkpoint(spec: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(spec, Mapping):
        raise NetherlandsKoopError(f"{label} checkpoint is absent")
    if not isinstance(spec.get("bytes"), int) or spec["bytes"] <= 0:
        raise NetherlandsKoopError(f"{label} byte count is invalid")
    digest = spec.get("sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise NetherlandsKoopError(f"{label} SHA-256 is invalid")
    return spec


def _validate_definition(definition: Mapping[str, Any]) -> None:
    expected_keys = {
        "advisory_relationship_contract",
        "classification_contract",
        "expected_identifiers_in_sru_order",
        "format",
        "query",
        "raw_artifacts",
        "release_id",
        "request_log",
        "retrieval_policy",
        "retrieved_at",
        "review_policy",
        "rights_policy",
        "schema_version",
    }
    if set(definition) != expected_keys:
        raise NetherlandsKoopError("source definition keys changed")
    if (
        definition.get("format") != DEFINITION_FORMAT
        or definition.get("release_id") != RELEASE_ID
        or definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("expected_identifiers_in_sru_order")
        != list(EXPECTED_IDENTIFIERS)
        or definition.get("classification_contract") != CLASSIFICATION_CONTRACT
        or definition.get("advisory_relationship_contract")
        != list(ADVISORY_GROUPS)
        or definition.get("review_policy") != REVIEW_POLICY
        or definition.get("rights_policy") != RIGHTS_POLICY
    ):
        raise NetherlandsKoopError("definition identity or review contract changed")
    expected_query = {
        "endpoint": SRU_ENDPOINT,
        "expected_number_of_records": 20,
        "expected_result_count_precision": SRU_RESULT_PRECISION,
        "parameters": SRU_PARAMETERS,
        "query": SRU_QUERY,
        "request_url": SRU_REQUEST_URL,
        "single_bounded_request": True,
    }
    if definition.get("query") != expected_query:
        raise NetherlandsKoopError("canonical SRU query contract changed")
    _timestamp(definition.get("retrieved_at"), "retrieved_at")
    artifacts = definition.get("raw_artifacts")
    if not isinstance(artifacts, Mapping) or tuple(artifacts) != tuple(
        sorted(ARTIFACT_ORDER)
    ):
        # Canonical JSON sorts object keys, so loaded order must also be sorted.
        if not isinstance(artifacts, Mapping) or set(artifacts) != set(ARTIFACT_ORDER):
            raise NetherlandsKoopError("raw artifact inventory changed")
    for artifact_id in ARTIFACT_ORDER:
        spec = _validate_checkpoint(artifacts[artifact_id], artifact_id)
        required = {
            "artifact_id",
            "bytes",
            "content_type",
            "effective_url",
            "path",
            "request_purpose",
            "rights_scope",
            "sha256",
            "url",
        }
        if (
            set(spec) != required
            or spec.get("artifact_id") != artifact_id
            or spec.get("path") != RAW_PATHS[artifact_id]
            or spec.get("url") != ARTIFACT_URLS[artifact_id]
            or spec.get("request_purpose") != ARTIFACT_PURPOSES[artifact_id]
            or spec.get("rights_scope") != RIGHTS_SCOPES[artifact_id]
        ):
            raise NetherlandsKoopError(f"raw artifact contract changed: {artifact_id}")
        parsed = urlsplit(str(spec.get("effective_url")))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise NetherlandsKoopError(f"raw artifact is not official HTTPS: {artifact_id}")
    log_spec = _validate_checkpoint(definition.get("request_log"), "request log")
    if set(log_spec) != {"bytes", "path", "sha256"} or log_spec.get(
        "path"
    ) != DERIVED_FILENAMES["request_log"]:
        raise NetherlandsKoopError("request-log contract changed")
    retrieval = definition.get("retrieval_policy")
    if (
        not isinstance(retrieval, Mapping)
        or retrieval.get("maximum_attempts_per_request") != 4
        or retrieval.get("minimum_pacing_seconds") != 0.35
        or retrieval.get("timeout_seconds") != 120.0
        or retrieval.get("user_agent")
        != "datacenter-atlas-netherlands-koop/1.0"
    ):
        raise NetherlandsKoopError("retrieval policy changed")


def _canonical_jsonl_objects(raw: bytes, label: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NetherlandsKoopError(
                f"{label} line {line_number} is invalid"
            ) from error
        if not isinstance(value, dict) or line != canonical_json(value):
            raise NetherlandsKoopError(
                f"{label} line {line_number} is not canonical"
            )
        values.append(value)
    return values


def _validate_capture_inputs(
    definition: Mapping[str, Any], capture: Path
) -> tuple[dict[str, bytes], bytes, list[dict[str, Any]]]:
    raw_bodies: dict[str, bytes] = {}
    artifacts = definition["raw_artifacts"]
    for artifact_id in ARTIFACT_ORDER:
        spec = artifacts[artifact_id]
        path = capture / spec["path"]
        if path.is_symlink() or not path.is_file():
            raise NetherlandsKoopError(f"capture input is absent: {artifact_id}")
        raw = path.read_bytes()
        if {"bytes": len(raw), "sha256": sha256_bytes(raw)} != {
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }:
            raise NetherlandsKoopError(f"captured artifact changed: {artifact_id}")
        raw_bodies[artifact_id] = raw
    log_path = capture / definition["request_log"]["path"]
    request_log_raw = log_path.read_bytes()
    if {"bytes": len(request_log_raw), "sha256": sha256_bytes(request_log_raw)} != {
        "bytes": definition["request_log"]["bytes"],
        "sha256": definition["request_log"]["sha256"],
    }:
        raise NetherlandsKoopError("request log changed")
    request_log = _canonical_jsonl_objects(request_log_raw, "request log")
    if len(request_log) != len(ARTIFACT_ORDER):
        raise NetherlandsKoopError("request-log count changed")
    for index, (artifact_id, entry) in enumerate(
        zip(ARTIFACT_ORDER, request_log, strict=True), 1
    ):
        spec = artifacts[artifact_id]
        if (
            entry.get("artifact_id") != artifact_id
            or entry.get("request_index") != index
            or entry.get("method") != "GET"
            or entry.get("http_status") != 200
            or entry.get("url") != spec["url"]
            or entry.get("effective_url") != spec["effective_url"]
            or entry.get("bytes") != spec["bytes"]
            or entry.get("sha256") != spec["sha256"]
            or entry.get("content_type") != spec["content_type"]
            or entry.get("request_purpose") != spec["request_purpose"]
            or not isinstance(entry.get("attempt_count"), int)
            or not 1 <= entry["attempt_count"] <= 4
            or entry.get("retries_used") != entry["attempt_count"] - 1
            or entry.get("minimum_pacing_seconds") != 0.35
        ):
            raise NetherlandsKoopError(f"request lineage changed: {artifact_id}")
        _timestamp(entry.get("requested_at"), "request requested_at")
        _timestamp(entry.get("completed_at"), "request completed_at")
    if request_log[-1]["completed_at"] != definition["retrieved_at"]:
        raise NetherlandsKoopError("retrieval timestamp and request log differ")
    return raw_bodies, request_log_raw, request_log


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str | None:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _text(element: ET.Element) -> str:
    return (element.text or "").strip()


def _values(element: ET.Element, local_name: str) -> list[str]:
    return [_text(item) for item in element.iter() if _local_name(item.tag) == local_name]


def _one(element: ET.Element, local_name: str, *, optional: bool = False) -> str | None:
    values = _values(element, local_name)
    if optional and not values:
        return None
    if len(values) != 1:
        raise NetherlandsKoopError(
            f"SRU record field {local_name} has {len(values)} values"
        )
    return values[0]


def _leaf_elements(element: ET.Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for ordinal, item in enumerate(element.iter(), 1):
        if list(item):
            continue
        result.append(
            {
                "attributes": dict(sorted(item.attrib.items())),
                "local_name": _local_name(item.tag),
                "namespace": _namespace(item.tag),
                "ordinal": ordinal,
                "text": _text(item),
            }
        )
    return result


def _location_point(value: str) -> dict[str, Any]:
    parts = value.split()
    if len(parts) != 2:
        return {"crs": None, "latitude": None, "longitude": None, "raw": value}
    try:
        latitude, longitude = map(float, parts)
    except ValueError:
        return {"crs": None, "latitude": None, "longitude": None, "raw": value}
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise NetherlandsKoopError("SRU ETRS89 location point is out of bounds")
    return {
        "crs": "ETRS89",
        "latitude": latitude,
        "longitude": longitude,
        "raw": value,
        "source_order": "latitude longitude",
    }


def _geography(original: ET.Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for marker in original.iter():
        if _local_name(marker.tag) != "gebiedsmarkering":
            continue
        children = list(marker)
        if len(children) != 1:
            raise NetherlandsKoopError("SRU geographic marker structure changed")
        shape = children[0]
        result.append(
            {
                "geometry": _values(shape, "geometrie"),
                "geometry_labels": _values(shape, "geometrielabel"),
                "kind": _local_name(shape.tag),
                "lies_in_municipality": _values(shape, "ligtInGemeente"),
                "location_points": [
                    _location_point(value) for value in _values(shape, "locatiepunt")
                ],
                "raw_location_points": _values(shape, "locatiepunt"),
            }
        )
    return result


def _parse_sru(raw: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise NetherlandsKoopError("SRU response is invalid XML") from error
    if (
        _local_name(root.tag) != "searchRetrieveResponse"
        or _one(root, "version") != "2.0"
        or _one(root, "numberOfRecords") != "20"
        or _one(root, "query") != SRU_QUERY
        or _one(root, "startRecord") != "1"
        or _one(root, "maximumRecords") != "100"
        or _one(root, "recordXMLEscaping") != "xml"
        or _one(root, "resultCountPrecision") != SRU_RESULT_PRECISION
        or _values(root, "nextRecordPosition")
    ):
        raise NetherlandsKoopError("bounded SRU response contract changed")
    records = [item for item in root.iter() if _local_name(item.tag) == "record"]
    if len(records) != 20:
        raise NetherlandsKoopError("SRU response did not return all 20 records")
    parsed: list[dict[str, Any]] = []
    for expected_position, record in enumerate(records, 1):
        record_data = next(
            (item for item in record if _local_name(item.tag) == "recordData"),
            None,
        )
        if record_data is None or len(record_data) != 1:
            raise NetherlandsKoopError("SRU record data changed")
        gzd = record_data[0]
        original = next(
            (item for item in gzd if _local_name(item.tag) == "originalData"),
            None,
        )
        enriched = next(
            (item for item in gzd if _local_name(item.tag) == "enrichedData"),
            None,
        )
        if original is None or enriched is None:
            raise NetherlandsKoopError("SRU original/enriched data is absent")
        position = int(_one(record, "recordPosition") or 0)
        if position != expected_position:
            raise NetherlandsKoopError("SRU record positions changed")
        item_urls = [
            {
                "manifestation": item.attrib.get("manifestation"),
                "url": _text(item),
            }
            for item in enriched.iter()
            if _local_name(item.tag) == "itemUrl"
        ]
        if len(item_urls) != 6 or {item["manifestation"] for item in item_urls} != {
            "html",
            "metadata",
            "metadataowms",
            "odt",
            "pdf",
            "xml",
        }:
            raise NetherlandsKoopError("SRU publication manifestation set changed")
        leaf_elements = _leaf_elements(original)
        enriched_leaf_elements = _leaf_elements(enriched)
        metadata = {
            "abstract": _one(original, "abstract", optional=True),
            "activities": _values(original, "activiteit"),
            "authority": _one(original, "authority"),
            "available": _one(original, "available"),
            "content_area": _one(original, "content-area"),
            "creator": _one(original, "creator"),
            "date": _one(original, "date"),
            "geographic_markers": _geography(original),
            "has_version": _one(original, "hasVersion"),
            "identifier": _one(original, "identifier"),
            "item_urls": item_urls,
            "language": _one(original, "language"),
            "modified": _one(original, "modified"),
            "organisation_type": _one(original, "organisatietype"),
            "preferred_url": _one(enriched, "preferredUrl"),
            "product_area": _one(original, "product-area"),
            "publication_name": _one(original, "publicatienaam"),
            "publication_number": _one(original, "publicatienummer"),
            "publication_year": _one(original, "jaargang"),
            "publisher": _one(original, "publisher"),
            "repository_url": _one(enriched, "url"),
            "subject": _one(original, "subject"),
            "title": _one(original, "title"),
            "type": _one(original, "type"),
        }
        parsed.append(
            {
                "enriched_metadata_leaf_elements": enriched_leaf_elements,
                "metadata": metadata,
                "original_metadata_leaf_elements": leaf_elements,
                "record_position": position,
                "record_timestamp": _one(enriched, "timestamp"),
                "source_metadata_sha256": sha256_bytes(
                    canonical_json(
                        {
                            "enriched_leaf_elements": enriched_leaf_elements,
                            "leaf_elements": leaf_elements,
                            "metadata": metadata,
                        }
                    )
                ),
            }
        )
    identifiers = tuple(item["metadata"]["identifier"] for item in parsed)
    if identifiers != EXPECTED_IDENTIFIERS:
        raise NetherlandsKoopError("SRU identifier/order set changed")
    return parsed


def _detail_text(raw: bytes, identifier: str) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise NetherlandsKoopError(f"detail XML is invalid: {identifier}") from error
    if _local_name(root.tag) != "officiele-publicatie":
        raise NetherlandsKoopError(f"detail XML root changed: {identifier}")
    text = " ".join(
        value.strip() for value in root.itertext() if value and value.strip()
    )
    if any(marker not in text for marker in DETAIL_MARKERS[identifier]):
        raise NetherlandsKoopError(f"detail evidence markers changed: {identifier}")
    return text


def _validate_rights(raw_bodies: Mapping[str, bytes]) -> dict[str, Any]:
    try:
        copyright_page = raw_bodies["koop_copyright"].decode("utf-8")
        dataset_page = raw_bodies["dataset_page"].decode("utf-8")
    except UnicodeDecodeError as error:
        raise NetherlandsKoopError("rights evidence is not UTF-8") from error
    copyright_markers = (
        'DCTERMS.rights" content="CC0 1.0 Universal"',
        "Voor deze website geldt de Creative Commons zero-verklaring (CC0 1.0)",
        "Staat er bij een tekst dat er auteursrecht op zit? Dan mag het niet.",
        "Beeldmateriaal (zoals foto’s en video's) mag u bijna nooit gebruiken.",
    )
    dataset_markers = (
        "Officiele bekendmakingen",
        "CC-0 (1.0)",
        "Officiele bekendmakingen SRU 2.0",
        "HandleidingSRU2.0.pdf",
    )
    if any(marker not in copyright_page for marker in copyright_markers):
        raise NetherlandsKoopError("KOOP copyright policy markers changed")
    if any(marker not in dataset_page for marker in dataset_markers):
        raise NetherlandsKoopError("official dataset license markers changed")
    guide = raw_bodies["sru_guide"]
    if not guide.startswith(b"%PDF-") or b"%%EOF" not in guide[-1024:]:
        raise NetherlandsKoopError("official SRU guide is not a complete PDF")
    return {
        **RIGHTS_POLICY,
        "assessed_from_collection_catalog": DATASET_PAGE_URL,
        "assessed_from_koop_copyright_page": KOOP_COPYRIGHT_URL,
        "assessed_from_sru_guide": SRU_GUIDE_URL,
        "selected_detail_xml_count": len(DETAIL_IDENTIFIERS),
        "selected_details_contain_explicit_copyright_marker": any(
            b"auteursrecht" in raw_bodies[_detail_artifact_id(identifier)].lower()
            for identifier in DETAIL_IDENTIFIERS
        ),
    }


def _observations(
    records: Sequence[Mapping[str, Any]],
    raw_bodies: Mapping[str, bytes],
    definition: Mapping[str, Any],
) -> list[dict[str, Any]]:
    details = {
        identifier: _detail_text(
            raw_bodies[_detail_artifact_id(identifier)], identifier
        )
        for identifier in DETAIL_IDENTIFIERS
    }
    result: list[dict[str, Any]] = []
    sru_spec = definition["raw_artifacts"]["sru_search"]
    for record in records:
        metadata = dict(record["metadata"])
        identifier = str(metadata["identifier"])
        review = CLASSIFICATION_CONTRACT[identifier]
        detail_artifact_id = (
            _detail_artifact_id(identifier)
            if identifier in DETAIL_IDENTIFIERS
            else None
        )
        untyped = [
            {
                "metric_type": None,
                "promoted_to_capacity_power_or_energy": False,
                "reason": (
                    "Ancillary energy-generation threshold language is not data-centre "
                    "facility power, IT capacity, or energy-consumption evidence."
                ),
                "text": text,
                "unit": None,
                "value": None,
            }
            for text in review["untyped_context_statements"]
        ]
        result.append(
            {
                "accepted_relationship": False,
                "advisory_group_ids": (
                    [review["advisory_group_id"]]
                    if review["advisory_group_id"]
                    else []
                ),
                "auto_merge": False,
                "classification": {
                    "label": review["classification"],
                    "reason": review["reason"],
                },
                "construction": {
                    "source_supported": False,
                    "verified": False,
                },
                "detail_evidence": (
                    {
                        "artifact_id": detail_artifact_id,
                        "full_text_sha256": sha256_bytes(
                            details[identifier].encode("utf-8")
                        ),
                        "markers": list(DETAIL_MARKERS[identifier]),
                        "raw_bytes": definition["raw_artifacts"][detail_artifact_id][
                            "bytes"
                        ],
                        "raw_sha256": definition["raw_artifacts"][detail_artifact_id][
                            "sha256"
                        ],
                        "url": definition["raw_artifacts"][detail_artifact_id]["url"],
                    }
                    if detail_artifact_id
                    else None
                ),
                "enriched_metadata_leaf_elements": record[
                    "enriched_metadata_leaf_elements"
                ],
                "facility_metrics": {
                    "annual_energy_observations": [],
                    "capacity_observations": [],
                    "power_observations": [],
                    "pue_observations": [],
                    "untyped_context_statements": untyped,
                    "workload_observations": [],
                },
                "metadata": metadata,
                "observation_id": f"netherlands-koop:{identifier}",
                "original_metadata_leaf_elements": record[
                    "original_metadata_leaf_elements"
                ],
                "permit_process": {
                    "facility_lifecycle_status_promoted": False,
                    "stage": review["process_stage"],
                    "stage_scope": "official_publication_process_only",
                },
                "project_review_label": review["project_label"],
                "promotion_boundaries": REVIEW_POLICY,
                "record_type": "official_publication_permit_review_observation",
                "review_only": True,
                "source": {
                    "collection": "officielepublicaties",
                    "identifier": identifier,
                    "metadata_sha256": record["source_metadata_sha256"],
                    "record_position": record["record_position"],
                    "record_timestamp": record["record_timestamp"],
                    "sru_response_sha256": sru_spec["sha256"],
                    "sru_url": SRU_REQUEST_URL,
                },
                "unique_site_counted": False,
            }
        )
    return result


def _relationships_document() -> dict[str, Any]:
    return {
        "accepted_relationships": 0,
        "automatic_merges": 0,
        "format": RELATIONSHIP_FORMAT,
        "groups": [
            {
                **group,
                "accepted": False,
                "automatic_merge": False,
                "identity_resolution_performed": False,
            }
            for group in ADVISORY_GROUPS
        ],
        "group_count": len(ADVISORY_GROUPS),
        "member_attachments": sum(len(group["members"]) for group in ADVISORY_GROUPS),
        "unique_physical_site_count": None,
    }


def _inventory(
    records: Sequence[Mapping[str, Any]], observations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    metadata = [record["metadata"] for record in records]
    return {
        "abstract_presence": {
            "missing": sum(item["abstract"] is None for item in metadata),
            "present": sum(item["abstract"] is not None for item in metadata),
        },
        "activity_value_counts_exact": dict(
            sorted(Counter(value for item in metadata for value in item["activities"]).items())
        ),
        "classification_counts": dict(
            sorted(Counter(item["classification"]["label"] for item in observations).items())
        ),
        "creator_counts_exact": dict(
            sorted(Counter(str(item["creator"]) for item in metadata).items())
        ),
        "detail_identifiers": list(DETAIL_IDENTIFIERS),
        "format": INVENTORY_FORMAT,
        "identifiers_in_sru_order": [item["identifier"] for item in metadata],
        "item_url_manifestations_per_record": {
            str(item["identifier"]): [entry["manifestation"] for entry in item["item_urls"]]
            for item in metadata
        },
        "process_stage_counts": dict(
            sorted(Counter(item["permit_process"]["stage"] for item in observations).items())
        ),
        "publication_name_counts_exact": dict(
            sorted(Counter(str(item["publication_name"]) for item in metadata).items())
        ),
        "records": len(records),
        "records_with_any_etrs89_location_point": sum(
            any(marker["location_points"] for marker in item["geographic_markers"])
            for item in metadata
        ),
        "records_with_geometry": sum(
            any(marker["geometry"] for marker in item["geographic_markers"])
            for item in metadata
        ),
        "schema_version": SCHEMA_VERSION,
        "unique_identifiers": len({item["identifier"] for item in metadata}),
    }


def _schema_document() -> dict[str, Any]:
    return {
        "format": SCHEMA_FORMAT,
        "record_type": "official_publication_permit_review_observation",
        "required_fields": [
            "accepted_relationship",
            "advisory_group_ids",
            "auto_merge",
            "classification",
            "construction",
            "detail_evidence",
            "enriched_metadata_leaf_elements",
            "facility_metrics",
            "metadata",
            "observation_id",
            "original_metadata_leaf_elements",
            "permit_process",
            "project_review_label",
            "promotion_boundaries",
            "record_type",
            "review_only",
            "source",
            "unique_site_counted",
        ],
        "schema_version": SCHEMA_VERSION,
        "semantic_boundaries": REVIEW_POLICY,
    }


def _observations_csv(observations: Sequence[Mapping[str, Any]]) -> bytes:
    fields = (
        "observation_id",
        "identifier",
        "classification",
        "process_stage",
        "project_review_label",
        "title",
        "abstract",
        "creator",
        "available",
        "publication_name",
        "publication_number",
        "activities_json",
        "geographic_markers_json",
        "preferred_url",
        "item_urls_json",
        "advisory_group_ids_json",
        "untyped_context_statements_json",
        "review_only",
        "construction_source_supported",
        "unique_site_counted",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for observation in observations:
        metadata = observation["metadata"]
        writer.writerow(
            {
                "observation_id": observation["observation_id"],
                "identifier": metadata["identifier"],
                "classification": observation["classification"]["label"],
                "process_stage": observation["permit_process"]["stage"],
                "project_review_label": observation["project_review_label"],
                "title": metadata["title"],
                "abstract": metadata["abstract"] or "",
                "creator": metadata["creator"],
                "available": metadata["available"],
                "publication_name": metadata["publication_name"],
                "publication_number": metadata["publication_number"],
                "activities_json": json.dumps(metadata["activities"], ensure_ascii=False, separators=(",", ":")),
                "geographic_markers_json": json.dumps(metadata["geographic_markers"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "preferred_url": metadata["preferred_url"],
                "item_urls_json": json.dumps(metadata["item_urls"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "advisory_group_ids_json": json.dumps(observation["advisory_group_ids"], separators=(",", ":")),
                "untyped_context_statements_json": json.dumps(observation["facility_metrics"]["untyped_context_statements"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "review_only": "true",
                "construction_source_supported": "false",
                "unique_site_counted": "false",
            }
        )
    return buffer.getvalue().encode("utf-8")


def _attribution(retrieved_at: str) -> bytes:
    return f"""Netherlands KOOP official-publications review lane

Canonical SRU endpoint: {SRU_ENDPOINT}
Collection: officielepublicaties
Retrieved: {retrieved_at}
Collection catalog: {DATASET_PAGE_URL}
KOOP copyright policy: {KOOP_COPYRIGHT_URL}
Catalog licence: CC-0 (1.0)

The bundle retains SRU metadata and eight selected official XML text details.
KOOP's copyright page applies CC0 1.0 to website text subject to express
copyright notices, while warning that images and videos generally may not be
reused. This bundle therefore makes no reuse claim for images, PDFs, ODTs, or
other attachments and does not redistribute them.
""".encode("utf-8")


def _readme(retrieved_at: str) -> bytes:
    return f"""# Netherlands KOOP official-publications assessment

This frozen release preserves one bounded KOOP SRU 2.0 response retrieved at
`{retrieved_at}`. The canonical query returned an estimated 20 records and all
20 were returned in one request (`maximumRecords=100`). It searches the
`officielepublicaties` collection for 2026 environmental-permit publications
whose titles contain `datacenter` or `datacentrum`.

All 20 records are retained and classified after manual scope review: 13 are
direct project/build/expansion or modification review candidates and seven are
ancillary/context exclusions. The exclusions comprise two EOS battery-system
publications, one Equinix AM6 energy-generation application, three De Kwakel
grid-connection publications, and one legalization application for an existing
data centre. The `50 MW of meer` wording is preserved only as an untyped
ancillary statement; it is not facility power, IT capacity, or energy use.

Eight full-text XML publications were fetched only where needed to resolve a
classification boundary. PDF, ODT, image, and other attachments were not
fetched. Every network request is recorded with pacing, retries, timestamps,
headers, byte count, and SHA-256 in `request-log.jsonl`.

Permit portal stages are process evidence only. Every observation is
`review_only: true`, `construction.source_supported: false`, `auto_merge:
false`, and `unique_site_counted: false`. No record establishes facility
identity, lifecycle, operation, type, power, energy, PUE, workload, or a unique
physical-site count.

Six obvious same-case, same-project, or multi-phase sequences are recorded as
advisory groups. They do not merge records or accept identity relationships.
The raw SRU XML, selected XML details, official SRU guide, KOOP copyright page,
and official collection-license page are retained byte-for-byte under `raw/`.

Validate and reproduce every derived byte offline with:

```sh
python3 scripts/fetch_build_netherlands_koop.py --validate-only
```
""".encode("utf-8")


def derive_release_files(
    definition: Mapping[str, Any],
    raw_bodies: Mapping[str, bytes],
    request_log_raw: bytes,
    request_log: Sequence[Mapping[str, Any]],
) -> dict[str, bytes]:
    """Derive all non-manifest files from pinned raw bytes without network use."""

    rights = _validate_rights(raw_bodies)
    records = _parse_sru(raw_bodies["sru_search"])
    observations = _observations(records, raw_bodies, definition)
    relationships = _relationships_document()
    inventory = _inventory(records, observations)
    classification_counts = inventory["classification_counts"]
    if classification_counts != {
        CONTEXT_CLASSIFICATION: 7,
        DIRECT_CLASSIFICATION: 13,
    }:
        raise NetherlandsKoopError("classification accounting changed")
    assessment = {
        "advisory_relationships": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "group_count": relationships["group_count"],
            "member_attachments": relationships["member_attachments"],
            "unique_physical_site_count": None,
        },
        "assessed_at": definition["retrieved_at"],
        "classification_counts": classification_counts,
        "detail_selection": {
            "fetched_identifiers": list(DETAIL_IDENTIFIERS),
            "official_xml_details_fetched": len(DETAIL_IDENTIFIERS),
            "reason": "Only ancillary/context boundaries and the direct QTS record lacking an SRU abstract required full-text confirmation.",
            "unfetched_attachment_manifestations": ["html", "metadata", "metadataowms", "odt", "pdf"],
        },
        "format": ASSESSMENT_FORMAT,
        "query_assessment": {
            **definition["query"],
            "all_estimated_records_returned_in_one_request": True,
            "identifiers_in_response_order": list(EXPECTED_IDENTIFIERS),
        },
        "raw_artifacts": definition["raw_artifacts"],
        "release_id": RELEASE_ID,
        "request_log": {
            **definition["request_log"],
            "network_requests": len(request_log),
            "validator_network_requests": 0,
        },
        "review_policy": REVIEW_POLICY,
        "rights_assessment": rights,
        "schema_version": SCHEMA_VERSION,
        "untyped_context_statement_count": sum(
            len(item["facility_metrics"]["untyped_context_statements"])
            for item in observations
        ),
    }
    return {
        DERIVED_FILENAMES["assessment"]: canonical_json(assessment, pretty=True),
        DERIVED_FILENAMES["attribution"]: _attribution(definition["retrieved_at"]),
        DERIVED_FILENAMES["definition"]: canonical_json(definition, pretty=True),
        DERIVED_FILENAMES["inventory"]: canonical_json(inventory, pretty=True),
        DERIVED_FILENAMES["observations_csv"]: _observations_csv(observations),
        DERIVED_FILENAMES["observations_jsonl"]: jsonl_bytes(observations),
        DERIVED_FILENAMES["readme"]: _readme(definition["retrieved_at"]),
        DERIVED_FILENAMES["relationships"]: canonical_json(relationships, pretty=True),
        DERIVED_FILENAMES["request_log"]: request_log_raw,
        DERIVED_FILENAMES["schema"]: canonical_json(_schema_document(), pretty=True),
    }


def _artifact_role(filename: str) -> str:
    if filename.startswith("raw/"):
        if filename.endswith(".pdf"):
            return "official_documentation_evidence"
        if "/details/" in filename:
            return "selected_official_XML_text_evidence"
        return "raw_official_source_or_rights_evidence"
    return {
        "assessment.json": "derived_assessment",
        "ATTRIBUTION.txt": "attribution",
        "definition.json": "source_definition",
        "source-inventory.json": "derived_inventory",
        "observations.csv": "review_observations",
        "observations.jsonl": "review_observations",
        "README.md": "documentation",
        "advisory-relationships.json": "advisory_relationships",
        "request-log.jsonl": "request_lineage",
        "schema.json": "schema",
    }[filename]


def _license_scope(filename: str) -> str:
    if filename.endswith((".odt", ".pdf")) and filename != "raw/sru-guide.pdf":
        return "not_redistributed"
    if filename.startswith("raw/details/"):
        return "selected_official_XML_text_CC0_scope_subject_to_express_notices"
    if filename.startswith("raw/"):
        return "official_source_or_rights_evidence"
    return "derived_by_datacenter_atlas"


def _manifest(path: Path, retrieved_at: str) -> bytes:
    files: dict[str, Any] = {}
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file.relative_to(path).as_posix()
        if relative in {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}:
            continue
        files[relative] = {
            **_checkpoint(file),
            "license_scope": _license_scope(relative),
            "role": _artifact_role(relative),
        }
    return canonical_json(
        {
            "files": files,
            "format": RELEASE_FORMAT,
            "release_id": RELEASE_ID,
            "retrieved_at": retrieved_at,
            "schema_version": SCHEMA_VERSION,
        },
        pretty=True,
    )


def _freeze(path: Path) -> None:
    for entry in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    path.chmod(0o555)


def write_release_bundle(
    definition_path: str | Path,
    capture_directory: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = True,
) -> Path:
    """Build a new immutable release from a pinned live capture."""

    definition, _ = load_definition(definition_path)
    capture = Path(capture_directory)
    raw_bodies, request_log_raw, request_log = _validate_capture_inputs(
        definition, capture
    )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise NetherlandsKoopError("output release already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for artifact_id in ARTIFACT_ORDER:
            relative = Path(definition["raw_artifacts"][artifact_id]["path"])
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw_bodies[artifact_id])
        for filename, raw in derive_release_files(
            definition, raw_bodies, request_log_raw, request_log
        ).items():
            target = stage / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        manifest_raw = _manifest(stage, definition["retrieved_at"])
        (stage / MANIFEST_FILENAME).write_bytes(manifest_raw)
        (stage / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n",
            encoding="ascii",
        )
        if freeze:
            _freeze(stage)
        stage.replace(destination)
        return destination
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def _expected_files(definition: Mapping[str, Any]) -> set[str]:
    return {
        *(spec["path"] for spec in definition["raw_artifacts"].values()),
        *DERIVED_FILENAMES.values(),
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }


def validate_release_bundle(
    path: str | Path, *, definition_path: str | Path | None = None
) -> dict[str, Any]:
    """Validate and reproduce the frozen release with zero network requests."""

    release = Path(path)
    if release.is_symlink() or not release.is_dir():
        raise NetherlandsKoopError("release must be a regular directory")
    bundle_definition = release / DERIVED_FILENAMES["definition"]
    definition, definition_raw = load_definition(
        definition_path if definition_path is not None else bundle_definition
    )
    if bundle_definition.read_bytes() != definition_raw:
        raise NetherlandsKoopError("bundle and source definitions differ")
    actual_files = {
        item.relative_to(release).as_posix()
        for item in release.rglob("*")
        if item.is_file()
    }
    if actual_files != _expected_files(definition):
        raise NetherlandsKoopError("release file inventory changed")
    manifest = _load_json(release / MANIFEST_FILENAME, "manifest")
    manifest_raw = (release / MANIFEST_FILENAME).read_bytes()
    if manifest_raw != canonical_json(manifest, pretty=True):
        raise NetherlandsKoopError("manifest is not canonical")
    if (release / MANIFEST_HASH_FILENAME).read_text(encoding="ascii") != (
        f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ):
        raise NetherlandsKoopError("manifest sidecar changed")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("retrieved_at") != definition["retrieved_at"]
        or set(manifest.get("files", {}))
        != actual_files - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    ):
        raise NetherlandsKoopError("manifest identity or file inventory changed")
    for filename, checkpoint in manifest["files"].items():
        if _checkpoint(release / filename) != {
            "bytes": checkpoint.get("bytes"),
            "sha256": checkpoint.get("sha256"),
        }:
            raise NetherlandsKoopError(f"release file changed: {filename}")
    if manifest_raw != _manifest(release, definition["retrieved_at"]):
        raise NetherlandsKoopError("manifest metadata changed")
    raw_bodies, request_log_raw, request_log = _validate_capture_inputs(
        definition, release
    )
    reproduced = derive_release_files(
        definition, raw_bodies, request_log_raw, request_log
    )
    for filename, expected in reproduced.items():
        if (release / filename).read_bytes() != expected:
            raise NetherlandsKoopError(f"offline reproduction mismatch: {filename}")
    observations = _canonical_jsonl_objects(
        (release / DERIVED_FILENAMES["observations_jsonl"]).read_bytes(),
        "observations",
    )
    if len(observations) != 20:
        raise NetherlandsKoopError("observation count changed")
    for observation in observations:
        if (
            observation.get("review_only") is not True
            or observation.get("auto_merge") is not False
            or observation.get("accepted_relationship") is not False
            or observation.get("unique_site_counted") is not False
            or observation.get("construction")
            != {"source_supported": False, "verified": False}
            or observation.get("promotion_boundaries") != REVIEW_POLICY
        ):
            raise NetherlandsKoopError("observation promotion boundary changed")
    assessment = _load_json(
        release / DERIVED_FILENAMES["assessment"], "assessment"
    )
    if not assessment.get("rights_assessment", {}).get(
        "rights_gate_passed_for_retained_scope"
    ):
        raise NetherlandsKoopError("rights gate failed")
    return {
        "assessment": assessment,
        "definition": definition,
        "inventory": _load_json(
            release / DERIVED_FILENAMES["inventory"], "inventory"
        ),
        "manifest": manifest,
        "observations": observations,
        "relationships": _load_json(
            release / DERIVED_FILENAMES["relationships"], "relationships"
        ),
    }


def is_frozen_release(path: str | Path) -> bool:
    release = Path(path)
    return (
        release.stat().st_mode & 0o777 == 0o555
        and all(
            item.stat().st_mode & 0o777 == (0o555 if item.is_dir() else 0o444)
            for item in release.rglob("*")
        )
    )


def thaw_for_test(path: str | Path) -> None:
    release = Path(path)
    release.chmod(stat.S_IRWXU)
    for item in release.rglob("*"):
        item.chmod(stat.S_IRWXU if item.is_dir() else stat.S_IRUSR | stat.S_IWUSR)


__all__ = [
    "ADVISORY_GROUPS",
    "ARTIFACT_ORDER",
    "CLASSIFICATION_CONTRACT",
    "CONTEXT_CLASSIFICATION",
    "DETAIL_IDENTIFIERS",
    "DIRECT_CLASSIFICATION",
    "EXPECTED_IDENTIFIERS",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "RAW_PATHS",
    "RELEASE_ID",
    "REVIEW_POLICY",
    "RIGHTS_POLICY",
    "SRU_QUERY",
    "NetherlandsKoopError",
    "canonical_json",
    "capture_live_sources",
    "definition_from_capture",
    "derive_release_files",
    "is_frozen_release",
    "load_definition",
    "sha256_bytes",
    "thaw_for_test",
    "validate_release_bundle",
    "write_release_bundle",
]
