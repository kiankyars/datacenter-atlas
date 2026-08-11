"""Publish a governed Bitdeer SEC current-build source tranche.

The exact SEC-hosted issuer exhibit supports two dated physical observations.
Raw all-rights-reserved response bytes are represented only by exact pins and
compact factual extracts. No open-seed or downstream integration is performed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .external_captures import resolve_external_capture
from . import global_official_builds_six_candidate_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database

ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "bitdeer-official-wenatchee-massillon-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".bitdeer-wenatchee-massillon-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-bitdeer-sec-20260722.jDCZHn")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-bitdeer-sec-20260722.jDCZHn")
CAPTURE_FILE_COUNT = 12
CAPTURE_TOTAL_BYTES = 237_599
CAPTURE_TREE_SHA256 = (
    "11f0547aee610f197f4546e7bbd93bb5a19cf3f447adc646c9889b6cec1718a1"
)

SEC_ACCESSION = "0001213900-26-079816"
SEC_ACCESSION_COMPACT = "000121390026079816"
SEC_CIK = "0001899123"
SEC_FORM = "6-K"
SEC_FILED_DATE = "2026-07-21"
SEC_ACCEPTANCE_DATETIME_RAW = "20260721081023"
SEC_EXHIBIT_FILENAME = "ea029852701ex99-1.htm"
SEC_BASE_URL = (
    "https://www.sec.gov/Archives/edgar/data/1899123/000121390026079816"
)

V92_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v92.json"
V92_RELEASE = ROOT / "releases/2026-07-21-open-seed-v92"
V92_MANIFEST = V92_RELEASE / "manifest.json"
V92_ENTITIES = V92_RELEASE / "entities.csv"
V92_SOURCE_INPUTS = V92_RELEASE / "source_inputs.json"
V92_PINS = {
    V92_DEFINITION: (
        109_851,
        "2dab6d4a4bdac34f248268f9f2973ccac88b7fe25deb78b10cf5e44c11990516",
    ),
    V92_MANIFEST: (
        16_558,
        "3ac9a48eeb121e6ac8a462fb2d99de1a7f2267c6cf9f6b7bd4b74d2b74a25fd7",
    ),
    V92_ENTITIES: (
        1_025_359,
        "3e1bf82358ee1e037a7e8ce1a175eee3958dfb4f4d3f5dc6fbd7b92704fd7290",
    ),
    V92_SOURCE_INPUTS: (
        410_016,
        "f46dcc40074e9daef10c7ce59fa37b2be8ca9c081fe5d067645332b1e4d514e9",
    ),
}
V92_TREE_SHA256 = "52bdbd5ea299dbd845adfe8e05f739894bff914107ae8fec341551bdb800034b"
V92_INPUT_COUNT = 485
V92_ENTITY_COUNT = 988

FOX_CREEK_SOURCE = SOURCES_ROOT / (
    "curated-official-2026-07-19-bitdeer-fox-creek-alberta.json"
)
FOX_CREEK_PIN = (
    10_283,
    "6cbe4fb717074b711d244cc02b5b559a770f0a7911af362f5cfe789394186734",
    1_784_534_254_918_361_291,
    0o644,
)
FOX_CREEK_MTIME_NS = 1_784_494_008_917_990_810
FOX_CREEK_BIRTHTIME_NS = 1_784_494_008_917_936_384
FOX_CREEK_GIT_BLOB_SHA1 = "e51e6ddf266beb8e642c9790a8ea710623b2bf6c"
FOX_CREEK_PROVENANCE_WITNESS_ID = (
    "fox-creek-source-provenance-after-hard-link-ctime-incident-2026-07-24-v2"
)
FOX_CREEK_CTIME_INCIDENT_OBSERVED_NS = 1_784_930_560_401_323_499
FOX_CREEK_CTIME_INCIDENT_OBSERVED_NLINK = 4

_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_promote_noreplace = publication._promote_noreplace


CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "exhibit-image.jpg": (
        2_153,
        "fa6f90bfa83d3a721c4981854b5083d6b5c50e4ad951630989b15fab1a028f3e",
    ),
    "exhibit.headers": (
        588,
        "df64af9120d82002b5579485f60c006a22d1254c17339ffbc4286aae7baf761e",
    ),
    "exhibit99-1.htm": (
        77_261,
        "c8fe8dcc3d3e264850657dd741d185cc4450188bd0063cd218bf99810f3ea50d",
    ),
    "filing.headers": (
        611,
        "879177c49ac67d4214f47044a9b2641180a5f19f45009fdccb8685809affa470",
    ),
    "filing.htm": (
        14_241,
        "27ffe5867ce9fee005962ddbd23e7d6bdfe3fd69843979b356cc915e1b81eb8c",
    ),
    "image.headers": (
        675,
        "888dac1dabdb0ee19173fb0c1c69aca8ec0acda68e5cee8b4808e3bcddaf4335",
    ),
    "index.headers": (
        283,
        "46547fba1682bdb7452563377cd1461f5ef767a7033bdfb2bbd813b5ee578043",
    ),
    "index.json": (
        789,
        "8d53792d2f4c6e8ad641bc8601812d3243ec0671c5b44e05497b6edd1efdaef7",
    ),
    "submission.headers": (
        616,
        "68a4bb8be24b87b7c3cf170667685d8fee88f1d30c15b73fc2e94b7d4c3a62db",
    ),
    "submission.txt": (
        95_748,
        "d1cd2864de4eb8639f199fc31c1e4c47e518d8b90623997afc3fb330931b45a7",
    ),
    "submissions.headers": (
        447,
        "ab8d93c5cbcc7a390a2acab2eccbe44417757d03568823f06392d94c09714400",
    ),
    "submissions.json": (
        44_187,
        "a798171aeab05c3df12c43a70c9a4cf6c49d978958103aaea7ba9d46869518ca",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    body_name: str
    header_name: str
    url: str
    content_type: str
    claim_use: str


CAPTURES = (
    Capture(
        "sec_exhibit_99_1",
        "exhibit99-1.htm",
        "exhibit.headers",
        f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
        "text/html",
        "normalized_status_and_capacity_authority",
    ),
    Capture(
        "sec_filing_6k",
        "filing.htm",
        "filing.headers",
        f"{SEC_BASE_URL}/ea0298527-6k_bitdeer.htm",
        "text/html",
        "filing_identity_context",
    ),
    Capture(
        "sec_complete_submission",
        "submission.txt",
        "submission.headers",
        f"{SEC_BASE_URL}/{SEC_ACCESSION}.txt",
        "text/plain",
        "accession_and_exhibit_lineage",
    ),
    Capture(
        "sec_accession_index",
        "index.json",
        "index.headers",
        f"{SEC_BASE_URL}/index.json",
        "text/html; charset=UTF-8",
        "accession_closed_file_inventory",
    ),
    Capture(
        "sec_issuer_submissions",
        "submissions.json",
        "submissions.headers",
        f"https://data.sec.gov/submissions/CIK{SEC_CIK}.json",
        "application/json",
        "issuer_and_filing_metadata",
    ),
    Capture(
        "sec_exhibit_image",
        "exhibit-image.jpg",
        "image.headers",
        f"{SEC_BASE_URL}/ea029852701_ex99-1img1.jpg",
        "image/jpeg",
        "excluded_publisher_image_no_visual_claim",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}
RETRIEVED_AT = "2026-07-22T02:41:42Z"

WENATCHEE_FILENAME = (
    "curated-official-2026-07-22-bitdeer-wenatchee-ai-conversion-current-build.json"
)
MASSILLON_FILENAME = (
    "curated-official-2026-07-22-bitdeer-massillon-reconstruction-current-build.json"
)
SOURCE_FILENAMES = (WENATCHEE_FILENAME, MASSILLON_FILENAME)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

WENATCHEE_EVIDENCE = (
    "bitdeer-sec-wenatchee-ai-conversion-update-2026-07-21"
)
MASSILLON_EVIDENCE = (
    "bitdeer-sec-massillon-fire-damaged-buildings-reconstruction-2026-07-21"
)
WENATCHEE_CAMPUS = "curated:bitdeer-wenatchee-washington-campus"
WENATCHEE_PROJECT = f"{WENATCHEE_CAMPUS}:2026-ai-conversion-site-preparation"
MASSILLON_CAMPUS = "curated:bitdeer-massillon-ohio-campus"
MASSILLON_PROJECT = (
    f"{MASSILLON_CAMPUS}:2026-fire-damaged-buildings-reconstruction"
)


def _lineage_metadata() -> dict[str, Any]:
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": "sec_exhibit_99_1",
        "capture_method": "credential_free_sec_http_capture",
        "requested_url": f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
        "effective_url": f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": "text/html",
        "content_hash_scope": (
            "SHA-256 of the exact 77261-byte SEC-hosted issuer Exhibit 99.1 "
            "response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_bytes": CAPTURE_FILE_PINS["exhibit.headers"][0],
        "capture_headers_sha256": CAPTURE_FILE_PINS["exhibit.headers"][1],
        "sec_accession": SEC_ACCESSION,
        "sec_accession_compact": SEC_ACCESSION_COMPACT,
        "sec_cik": SEC_CIK,
        "sec_form": SEC_FORM,
        "sec_filed_date": SEC_FILED_DATE,
        "sec_acceptance_datetime_raw": SEC_ACCEPTANCE_DATETIME_RAW,
        "sec_exhibit_filename": SEC_EXHIBIT_FILENAME,
        "sec_filing_body_sha256": CAPTURE_FILE_PINS["filing.htm"][1],
        "sec_complete_submission_sha256": CAPTURE_FILE_PINS["submission.txt"][1],
        "sec_accession_index_sha256": CAPTURE_FILE_PINS["index.json"][1],
        "sec_issuer_submissions_sha256": CAPTURE_FILE_PINS["submissions.json"][1],
        "sec_exhibit_image_sha256": CAPTURE_FILE_PINS["exhibit-image.jpg"][1],
        "rights_scope": (
            "Compact factual extraction from an all-rights-reserved issuer exhibit "
            "hosted by the SEC; raw bodies, headers, and publisher image are not "
            "redistributed."
        ),
        "status_semantics": "dated_last_observed_current_status_unknown",
        "visual_guardrail": (
            "The exhibit image is capture-lineage only. No imagery, computer vision, "
            "satellite, aerial, map-click, coordinate, or geometry claim is made."
        ),
    }


def _wenatchee_evidence() -> dict[str, Any]:
    return {
        "key": WENATCHEE_EVIDENCE,
        "kind": "company_disclosure",
        "title": "Bitdeer July 2026 infrastructure update - Wenatchee",
        "source_url": f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
        "publisher": "Bitdeer Technologies Group",
        "source_family": "sec_edgar_bitdeer_exhibit",
        "published_at": SEC_FILED_DATE,
        "retrieved_at": RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": "Bitdeer Technologies Group via SEC EDGAR",
        "excerpt": (
            "The exhibit reports that dismantling of the Wenatchee crypto-mining "
            "data center started in March 2026."
        ),
        "content_hash": CAPTURE_FILE_PINS["exhibit99-1.htm"][1],
        "metadata": {
            **_lineage_metadata(),
            "section_label": "Online Electrical Capacity",
            "site_as_reported": "Wenatchee, WA",
            "physical_work_as_reported": (
                "Dismantling of the crypto mining datacenter started in March 2026."
            ),
            "underlying_start_precision": "month",
            "underlying_start_month": "2026-03",
            "observation_date_basis": (
                "The normalized site-preparation observation uses the exhibit's "
                "2026-07-21 filing date; it does not invent a day in March."
            ),
            "design_permit_equipment_context": (
                "AI data-center design documents and a building-permit application "
                "were submitted; core equipment was being delivered; GB300 cluster "
                "and completion language remain context only."
            ),
            "planned_usage_not_normalized": "Crypto to AI Cloud.",
            "online_electrical_capacity_as_reported": "13 MW.",
            "capacity_exclusion": (
                "The 13 MW appears under Online Electrical Capacity, not Pipeline "
                "Electrical Capacity, and is a site total rather than a conversion-"
                "project capacity. It creates no normalized capacity and is not "
                "current consumption, current draw, critical IT, grid connection, "
                "generation, or annual energy."
            ),
            "classification_guardrail": (
                "Planned usage and equipment language create no operating-model or "
                "workload observation."
            ),
        },
    }


def _massillon_evidence() -> dict[str, Any]:
    return {
        "key": MASSILLON_EVIDENCE,
        "kind": "company_disclosure",
        "title": "Bitdeer July 2026 infrastructure update - Massillon",
        "source_url": f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
        "publisher": "Bitdeer Technologies Group",
        "source_family": "sec_edgar_bitdeer_exhibit",
        "published_at": SEC_FILED_DATE,
        "retrieved_at": RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": "Bitdeer Technologies Group via SEC EDGAR",
        "excerpt": (
            "The exhibit reports reconstruction of two fire-damaged Massillon "
            "buildings, scoped at 26 MW, currently under way."
        ),
        "content_hash": CAPTURE_FILE_PINS["exhibit99-1.htm"][1],
        "metadata": {
            **_lineage_metadata(),
            "section_label": "Pipeline Electrical Capacity",
            "site_as_reported": "Massillon, OH",
            "table_capacity_cell_as_reported": "21 / 26",
            "physical_work_as_reported": (
                "Reconstruction of the two fire-damaged buildings (26 MW) is "
                "currently underway."
            ),
            "pipeline_capacity_scope": (
                "26 MW is textually bound to the two reconstructed buildings and "
                "normalized once as planned project gross-facility capacity."
            ),
            "twenty_one_mw_exclusion": (
                "The same row says 21 MW is expected to be energized in phases, but "
                "does not identity-bind that separate figure to the two-building "
                "reconstruction. No 21 MW row is created."
            ),
            "nonadditivity_guardrail": (
                "21 and 26 are not added. No 47 MW value or row is created."
            ),
            "campus_total_exclusion": (
                "The separate Online Electrical Capacity section lists Massillon at "
                "174 MW. That existing campus total is not reconstruction scope and "
                "creates no project or campus capacity row here."
            ),
            "consumption_guardrail": (
                "Neither 26 nor any other figure is current consumption, current "
                "draw, critical IT, grid connection, generation, or annual energy."
            ),
            "planned_usage_not_normalized": "Crypto.",
            "classification_guardrail": (
                "Planned usage creates no operating-model or workload observation."
            ),
        },
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    address: str,
    evidence_key: str,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": "United States",
        "address": address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": SEC_FILED_DATE,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _wenatchee_source() -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [_wenatchee_evidence()],
        "campus": _entity(
            stable_key=WENATCHEE_CAMPUS,
            name="Bitdeer Wenatchee Washington Campus",
            address="Wenatchee, Washington, United States",
            evidence_key=WENATCHEE_EVIDENCE,
        ),
        "project": _entity(
            stable_key=WENATCHEE_PROJECT,
            name="Bitdeer Wenatchee 2026 AI Conversion Site Preparation",
            address="Wenatchee, Washington, United States",
            evidence_key=WENATCHEE_EVIDENCE,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "site_preparation",
                "evidence_key": WENATCHEE_EVIDENCE,
                "as_of_date": SEC_FILED_DATE,
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _massillon_source() -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [_massillon_evidence()],
        "campus": _entity(
            stable_key=MASSILLON_CAMPUS,
            name="Bitdeer Massillon Ohio Campus",
            address="Massillon, Ohio, United States",
            evidence_key=MASSILLON_EVIDENCE,
        ),
        "project": _entity(
            stable_key=MASSILLON_PROJECT,
            name="Bitdeer Massillon 2026 Fire-Damaged Buildings Reconstruction",
            address="Massillon, Ohio, United States",
            evidence_key=MASSILLON_EVIDENCE,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": MASSILLON_EVIDENCE,
                "as_of_date": SEC_FILED_DATE,
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            {
                "entity": "project",
                "metric": "gross_facility_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 26.0,
                "base": 26.0,
                "high": 26.0,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": MASSILLON_EVIDENCE,
                "as_of_date": SEC_FILED_DATE,
                "target_date": None,
                "notes": (
                    "Source-reported pipeline electrical capacity textually scoped "
                    "to the two fire-damaged buildings under reconstruction. Treated "
                    "as planned gross-facility capacity only; not current draw or "
                    "consumption, grid connection, critical IT, generation, annual "
                    "energy, additive with 21 MW, or the 174 MW campus total."
                ),
            }
        ],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        WENATCHEE_FILENAME: _wenatchee_source(),
        MASSILLON_FILENAME: _massillon_source(),
    }


REVIEW_ONLY = (
    {
        "candidate_id": "bitdeer-knoxville-ai-conversion",
        "site": "Knoxville, Tennessee",
        "source_language": "Phase 1 AI data center conversion design work initiated.",
        "exclusion": "Design only; no physical data-center work is stated.",
    },
    {
        "candidate_id": "bitdeer-tydal-conversion",
        "site": "Tydal, Norway",
        "source_language": (
            "Planning and design advance; equipment ordered; contractor engaged; "
            "lease subject to conditions precedent."
        ),
        "exclusion": "Planning, design, procurement, contractor, and lease only.",
    },
    {
        "candidate_id": "bitdeer-clarington",
        "site": "Clarington, Ohio",
        "source_language": "Design and other preparation work continues.",
        "exclusion": (
            "Design/preparation language is not physical status; legal proceedings "
            "further qualify timing."
        ),
    },
    {
        "candidate_id": "bitdeer-niles",
        "site": "Niles, Ohio",
        "source_language": (
            "Grid-interconnected development site and transmission-line extension "
            "agreement."
        ),
        "exclusion": "Grid/site agreement only; no physical construction stated.",
    },
    {
        "candidate_id": "bitdeer-rockdale-pipeline",
        "site": "Rockdale, Texas",
        "source_language": "In Planning.",
        "exclusion": "Planning only; no new physical observation.",
    },
    {
        "candidate_id": "bitdeer-cyberjaya-pipeline",
        "site": "Cyberjaya, Malaysia",
        "source_language": "In Progress.",
        "exclusion": (
            "Ambiguous progress label does not distinguish design, procurement, "
            "permitting, or physical construction."
        ),
    },
    {
        "candidate_id": "bitdeer-johor-bahru-lease",
        "site": "Johor Bahru, Malaysia",
        "source_language": (
            "Ten-year lease signed; handover expected in Q1 2027."
        ),
        "exclusion": "Lease and future handover only; no physical status.",
    },
    {
        "candidate_id": "bitdeer-molde-ai-assessment",
        "site": "Molde, Norway",
        "source_language": "In early assessment of converting to AI Cloud.",
        "exclusion": "Early assessment only; no conversion work stated.",
    },
    {
        "candidate_id": "bitdeer-fox-creek-data-center-design",
        "site": "Fox Creek, Alberta",
        "source_language": (
            "Data-center design is underway following the power-plant groundbreaking."
        ),
        "exclusion": (
            "The physical event is the power-plant groundbreaking; data-center work "
            "is design only. No new observation and no mutation of the frozen prior "
            "Fox Creek source."
        ),
    },
)


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["campus"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": 0,
                "workload_observations": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return rows


def _planned_keys(
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str]]:
    stable = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence = {
        row["key"]
        for document in documents.values()
        for row in document["evidence"]
    }
    return stable, evidence


def _git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _fox_creek_metadata(path: Path) -> dict[str, int]:
    metadata = path.stat(follow_symlinks=False)
    birthtime = getattr(metadata, "st_birthtime", None)
    if birthtime is None:
        raise RuntimeError("Fox Creek source birth time is unavailable")
    return {
        "birthtime_ns": round(birthtime * 1_000_000_000),
        "ctime_ns": metadata.st_ctime_ns,
        "mode": stat.S_IMODE(metadata.st_mode),
        "mtime_ns": metadata.st_mtime_ns,
        "nlink": metadata.st_nlink,
        "raw_mode": metadata.st_mode,
        "size": metadata.st_size,
    }


def _require_fox_creek_provenance_v2() -> dict[str, Any]:
    size, digest, prior_ctime_ns, mode = FOX_CREEK_PIN
    if FOX_CREEK_SOURCE.is_symlink():
        raise RuntimeError("frozen prior Fox Creek source changed")
    metadata = _fox_creek_metadata(FOX_CREEK_SOURCE)
    raw = FOX_CREEK_SOURCE.read_bytes()
    if (
        not stat.S_ISREG(metadata["raw_mode"])
        or metadata["size"] != size
        or _sha256_bytes(raw) != digest
        or metadata["mode"] != mode
        or metadata["mtime_ns"] != FOX_CREEK_MTIME_NS
        or metadata["birthtime_ns"] != FOX_CREEK_BIRTHTIME_NS
        or _git_blob_sha1(raw) != FOX_CREEK_GIT_BLOB_SHA1
    ):
        raise RuntimeError("frozen prior Fox Creek source changed")

    for path, pin in V92_PINS.items():
        _pin(path, pin)
    if tree_digest(V92_RELEASE) != V92_TREE_SHA256:
        raise RuntimeError("v92 release tree differs")
    definition = json.loads(V92_DEFINITION.read_text())
    selected_input = {
        "path": f"sources/{FOX_CREEK_SOURCE.name}",
        "sha256": digest,
    }
    matches = [
        row
        for row in definition.get("curated_inputs", [])
        if row.get("path") == selected_input["path"]
    ]
    if matches != [selected_input]:
        raise RuntimeError("v92 Fox Creek input witness changed")

    return {
        "schema_version": "2.0",
        "witness_id": FOX_CREEK_PROVENANCE_WITNESS_ID,
        "status": "accepted_metadata_incident_no_content_change",
        "source_identity": {
            "path": selected_input["path"],
            "bytes": size,
            "sha256": digest,
            "mode": f"{mode:04o}",
            "mtime_ns": FOX_CREEK_MTIME_NS,
            "birthtime_ns": FOX_CREEK_BIRTHTIME_NS,
            "git_blob_sha1": FOX_CREEK_GIT_BLOB_SHA1,
        },
        "release_identity": {
            "definition_path": str(V92_DEFINITION.relative_to(ROOT)),
            "definition_sha256": V92_PINS[V92_DEFINITION][1],
            "release_path": str(V92_RELEASE.relative_to(ROOT)),
            "release_tree_sha256": V92_TREE_SHA256,
            "selected_input": selected_input,
        },
        "incident": {
            "kind": "ctime_changed_when_retained_temporary_hard_link_was_removed",
            "prior_ctime_witness_ns": prior_ctime_ns,
            "observed_ctime_ns": FOX_CREEK_CTIME_INCIDENT_OBSERVED_NS,
            "remaining_link_count_at_observation": (
                FOX_CREEK_CTIME_INCIDENT_OBSERVED_NLINK
            ),
            "classification": "inode_metadata_event_not_content_mutation",
            "content_or_semantic_mutation": False,
        },
        "integrity_contract": {
            "required_signals": [
                "ordinary_regular_file",
                "bytes",
                "sha256",
                "mode",
                "mtime_ns",
                "birthtime_ns",
                "git_blob_sha1",
                "v92_definition_sha256",
                "v92_release_tree_sha256",
                "v92_selected_input",
            ],
            "observational_not_nonmutation_signals": ["ctime_ns", "nlink"],
            "future_staging_policy": "fresh_exclusive_single_link_regular_inodes",
        },
        "current_inode_observation": {
            "ctime_ns": metadata["ctime_ns"],
            "nlink": metadata["nlink"],
        },
    }


def _require_fox_creek_nonmutation() -> dict[str, Any]:
    """Reproduce the frozen v1 payload after validating its v2 successor witness."""

    _require_fox_creek_provenance_v2()
    size, digest, ctime_ns, mode = FOX_CREEK_PIN
    return {
        "path": f"sources/{FOX_CREEK_SOURCE.name}",
        "bytes": size,
        "sha256": digest,
        "ctime_ns": ctime_ns,
        "mode": f"{mode:04o}",
        "mutated": False,
        "new_physical_observation_added": False,
    }


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for path, pin in V92_PINS.items():
        _pin(path, pin)
    if tree_digest(V92_RELEASE) != V92_TREE_SHA256:
        raise RuntimeError("v92 release tree differs")
    definition = json.loads(V92_DEFINITION.read_text())
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V92_INPUT_COUNT:
        raise RuntimeError("v92 selected inputs differ")
    with V92_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != V92_ENTITY_COUNT:
        raise RuntimeError("v92 entity count differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    base_stable = {row["stable_key"] for row in entity_rows}
    if planned_stable & base_stable:
        raise RuntimeError("Bitdeer planned stable key collides with v92")
    source_inputs = json.loads(V92_SOURCE_INPUTS.read_text())
    base_evidence = {
        key
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("Bitdeer evidence key collides with v92")
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in source_names:
            continue
        try:
            document = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := document.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"Bitdeer source collision detected: {collisions!r}")
    return {
        "v92_selected_input_count": len(selected),
        "v92_entity_count": len(entity_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v92_stable_key_collisions": [],
        "exact_v92_evidence_key_collisions": [],
        "unexpected_source_collisions": {},
        "fox_creek_nonmutation": _require_fox_creek_nonmutation(),
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    normalized = [
        {
            "candidate_id": "bitdeer-wenatchee-ai-conversion",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{WENATCHEE_FILENAME}"],
            "campus_stable_key": WENATCHEE_CAMPUS,
            "project_stable_key": WENATCHEE_PROJECT,
            "lifecycle": "site_preparation",
            "as_of_date": SEC_FILED_DATE,
            "normalized_capacity": None,
            "capacity_exclusion": (
                "13 MW is an Online Electrical Capacity site total, not Pipeline "
                "Electrical Capacity or project capacity."
            ),
        },
        {
            "candidate_id": "bitdeer-massillon-reconstruction",
            "decision": "seed_eligible_direct_authoritative_physical_update",
            "source_paths": [f"sources/{MASSILLON_FILENAME}"],
            "campus_stable_key": MASSILLON_CAMPUS,
            "project_stable_key": MASSILLON_PROJECT,
            "lifecycle": "under_construction",
            "as_of_date": SEC_FILED_DATE,
            "normalized_capacity": {
                "metric": "gross_facility_mw",
                "stage": "planned",
                "base": 26.0,
            },
            "capacity_exclusions": [
                "21 MW is not identity-bound to the reconstruction",
                "21 + 26 is not computed; no 47 MW value",
                "174 MW is a separate online campus total",
                "no current draw, consumption, grid, critical IT, generation, or energy",
            ],
        },
    ]
    review = [
        {
            **row,
            "decision": "review_only_no_direct_physical_data_center_observation",
            "source_paths": [],
            "source_authority": f"{SEC_BASE_URL}/{SEC_EXHIBIT_FILENAME}",
            "normalized_entity": None,
            "normalized_lifecycle": None,
            "normalized_capacity": None,
        }
        for row in REVIEW_ONLY
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 11,
        "seed_eligible_candidate_count": 2,
        "seed_eligible_source_record_count": 2,
        "review_only_count": 9,
        "regional_completeness_claimed": False,
        "candidates": [*normalized, *review],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 6,
        "failed_http_body_captures": 0,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [
            {
                "capture_id": capture.capture_id,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "retrieved_at": RETRIEVED_AT,
                "http_status": 200,
                "content_type": capture.content_type,
                "claim_use": capture.claim_use,
                "body": {
                    "path": capture.body_name,
                    "bytes": CAPTURE_FILE_PINS[capture.body_name][0],
                    "sha256": CAPTURE_FILE_PINS[capture.body_name][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": capture.header_name,
                    "bytes": CAPTURE_FILE_PINS[capture.header_name][0],
                    "sha256": CAPTURE_FILE_PINS[capture.header_name][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
            }
            for capture in CAPTURES
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(
        (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    )


def _artifact_documents(
    recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    collision = _collision_witness(documents)
    records = _source_records(documents)
    totals = {
        "candidate_assessments": 11,
        "source_records": 2,
        "seed_eligible_candidates": 2,
        "review_only_candidates": 9,
        "distinct_campuses": 2,
        "projects": 2,
        "distinct_entities": 4,
        "unique_imported_entity_snapshots": 4,
        "unique_evidence_records": 2,
        "lifecycle_observations": 2,
        "capacity_estimates": 1,
        "planned_gross_facility_mw_sum": 26.0,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
    }
    readme = f"""# Bitdeer SEC Wenatchee and Massillon current-build source tranche

This immutable source artifact is grounded only in Bitdeer Technologies Group's official Exhibit 99.1 to accession {SEC_ACCESSION}, filed on {SEC_FILED_DATE} and hosted by SEC EDGAR. It publishes exactly two schema-1.1 campus/project records. Wenatchee receives one site-preparation observation because the exhibit says dismantling of the crypto-mining data center started in March 2026. The normalized observation is dated to the exhibit's filing date; no day in March is invented. Massillon receives one under-construction observation because reconstruction of two fire-damaged buildings is currently under way.

Only one capacity is normalized: 26 MW planned gross-facility capacity on the Massillon two-building reconstruction project. Wenatchee's 13 MW is in the Online Electrical Capacity section, not Pipeline Electrical Capacity, and remains site-total metadata only. Massillon's separate 21 MW phased-energization forecast is not identity-bound to the reconstruction; it is neither normalized nor added to 26. No 47 MW value exists. The separate 174 MW online Massillon campus total is not reconstruction capacity and is not normalized. None of these figures is current draw, consumption, grid connection, critical IT, generation, or annual energy.

Nine additional candidates remain review-only: Knoxville design; Tydal planning/design/procurement/contractor/lease; Clarington design/preparation/legal; Niles grid/site agreement; Rockdale planning; ambiguous Cyberjaya “In Progress”; Johor lease/future handover; Molde early assessment; and Fox Creek data-center design following a power-plant groundbreaking. The existing Fox Creek source is exact-pinned and untouched. Planned usage, equipment, and platform language create no operating-model or workload rows. No roles, PUE, WUE, energy, current-status persistence, coordinates, geometry, imagery, satellite, aerial, map-click, or computer-vision claims are added.

All two source files and all seven artifact members received frozen modes at or after {recorded_at}; the artifact root did as well. Final paths were promoted without replacement only after that instant. Raw all-rights-reserved issuer/SEC response bytes and the publisher image are not redistributed; the intact twelve-file raw directory is moved to recoverable Trash only after successful live validation. No open-seed, release, construction-master, map, federation, coverage, or review integration is performed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": records,
        "totals": totals,
        "sec_lineage": {
            "accession": SEC_ACCESSION,
            "cik": SEC_CIK,
            "form": SEC_FORM,
            "filed_date": SEC_FILED_DATE,
            "acceptance_datetime_raw": SEC_ACCEPTANCE_DATETIME_RAW,
            "exhibit_filename": SEC_EXHIBIT_FILENAME,
            "exhibit_body_sha256": CAPTURE_FILE_PINS["exhibit99-1.htm"][1],
            "complete_submission_sha256": CAPTURE_FILE_PINS["submission.txt"][1],
            "accession_index_sha256": CAPTURE_FILE_PINS["index.json"][1],
            "issuer_submissions_sha256": CAPTURE_FILE_PINS["submissions.json"][1],
        },
        "capacity_boundary": {
            "normalized": [
                {
                    "entity": MASSILLON_PROJECT,
                    "metric": "gross_facility_mw",
                    "stage": "planned",
                    "base": 26.0,
                }
            ],
            "withheld": {
                "wenatchee_online_electrical_site_total_mw": 13,
                "massillon_unbound_phased_energization_mw": 21,
                "forbidden_arithmetic_sum_mw": 47,
                "massillon_online_campus_total_mw": 174,
            },
            "current_consumption_or_draw_rows": 0,
            "critical_it_rows": 0,
            "grid_connection_rows": 0,
            "generation_rows": 0,
            "annual_energy_rows": 0,
        },
        "frozen_v92_non_mutation_witness": {
            "release_tree_sha256": V92_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v92_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 2,
            "all_source_and_artifact_member_ctimes_at_or_after_recorded_at": True,
            "artifact_root_ctime_at_or_after_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_after_successful_live_validation": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_rights": (
            "Compact factual extraction from an all-rights-reserved Bitdeer issuer "
            "exhibit hosted by SEC EDGAR. No redistribution license is relied on."
        ),
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_image_retained_in_artifact": False,
        "raw_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "raw_capture_file_count": CAPTURE_FILE_COUNT,
        "raw_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "raw_capture_original_path": str(CAPTURE_ORIGIN),
        "raw_capture_recoverable_trash_path": str(CAPTURE_TRASH),
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(
    paths: Mapping[str, Path], *, require_frozen: bool
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("Bitdeer source path inventory differs")
    wanted_mode = 0o444 if require_frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != wanted_mode
            or path.stat(follow_symlinks=False).st_nlink != 1
        ):
            raise RuntimeError(f"Bitdeer source differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("Bitdeer source invented coordinates or geometry")
    if any(
        document[entity]["roles"]
        for document in documents
        for entity in ("campus", "project")
    ):
        raise RuntimeError("Bitdeer source invented roles")
    if any(
        document[key]
        for document in documents
        for key in ("operating_models", "workloads")
    ):
        raise RuntimeError("Bitdeer source invented classification observations")
    lifecycle = [
        (document["project"]["stable_key"], row["value"], row["as_of_date"])
        for document in documents
        for row in document["lifecycle"]
    ]
    if lifecycle != [
        (WENATCHEE_PROJECT, "site_preparation", SEC_FILED_DATE),
        (MASSILLON_PROJECT, "under_construction", SEC_FILED_DATE),
    ]:
        raise RuntimeError("Bitdeer lifecycle contract differs")
    capacities = [row for document in documents for row in document["capacities"]]
    if [
        (row["entity"], row["metric"], row["stage"], row["base"])
        for row in capacities
    ] != [("project", "gross_facility_mw", "planned", 26.0)]:
        raise RuntimeError("Bitdeer capacity contract differs")
    serialized = json.dumps(documents, sort_keys=True)
    if "No 47 MW value" not in serialized or "174 MW" not in serialized:
        raise RuntimeError("Bitdeer nonadditivity guardrails differ")
    return _source_records(expected)


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("Bitdeer capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("Bitdeer capture closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("Bitdeer capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="bitdeer-sec-current-build-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = (
            "entities",
            "entity_snapshots",
            "evidence",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 4,
            "entity_snapshots": 4,
            "evidence": 2,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise RuntimeError(f"Bitdeer offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise RuntimeError(f"Bitdeer member ctime predates recorded_at: {path}")


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    records = _validate_sources(paths, require_frozen=require_frozen)
    _require_fox_creek_nonmutation()
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("Bitdeer artifact must be an ordinary directory")
    wanted_root = 0o555 if require_frozen else 0o700
    if stat.S_IMODE(path.stat().st_mode) != wanted_root:
        raise RuntimeError("Bitdeer artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        or entry.stat(follow_symlinks=False).st_nlink != 1
        for entry in entries.values()
    ):
        raise RuntimeError("Bitdeer artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 2
        or manifest.get("candidate_assessments") != 11
        or manifest.get("review_only_candidates") != 9
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("Bitdeer manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"Bitdeer manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text() != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("Bitdeer manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"Bitdeer artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != records:
        raise RuntimeError("Bitdeer source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("Bitdeer recorded_at is not live")
    if _instant(RETRIEVED_AT) > target:
        raise RuntimeError("Bitdeer capture post-dates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("Bitdeer offline replay differs")
    if require_frozen:
        _assert_chronology(
            [path, *entries.values(), *paths.values()], manifest["recorded_at"]
        )
    return manifest


def _write_fresh_stage_file(path: Path, raw: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError(f"short Bitdeer stage write: {path}")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeError(f"Bitdeer stage file is not a fresh inode: {path}")
    finally:
        os.close(descriptor)


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = stage / name
        _write_fresh_stage_file(path, _canonical(documents[name]))
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        _write_fresh_stage_file(path, payloads[name])
    rows = [
        {
            "bytes": (stage / name).stat().st_size,
            "path": name,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 11,
        "curated_source_records": 2,
        "seed_eligible_candidates": 2,
        "review_only_candidates": 9,
        "successful_http_200_body_captures": 6,
        "raw_capture_redistributed": False,
        "raw_capture_moved_after_successful_live_validation": True,
        "all_member_and_root_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    _write_fresh_stage_file(manifest_path, _canonical(manifest))
    sidecar = stage / "manifest.sha256"
    _write_fresh_stage_file(
        sidecar, f"{_sha256(manifest_path)}  manifest.json\n".encode()
    )
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active Bitdeer publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted Bitdeer lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("Bitdeer final-path collision")
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    _collision_witness(documents)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".bitdeer-sec-current-build-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    for name in SOURCE_FILENAMES:
        path = prepared.source_stage / name
        path.chmod(0o444)
        _fsync_regular(path)
    for path in prepared.artifact_stage.iterdir():
        path.chmod(0o444)
        _fsync_regular(path)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
            *prepared.source_stage.iterdir(),
        ],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("late Bitdeer final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"Bitdeer rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both Bitdeer raw origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 2,
        "unique_entities": 4,
        "lifecycle_observations": 2,
        "capacity_estimates": 1,
        "review_only_candidates": 9,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    ):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial Bitdeer final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("Bitdeer recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("Bitdeer source stage not empty")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
