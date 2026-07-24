"""Publish the bounded CoreWeave/Chirisa Lancaster official-source tranche.

Only the Greenfield Road adaptive-reuse construction scope is seed eligible.
The separate Harrisburg Pike site remains review-only because the official
record describes planned work and land-development review, not physical start.
Raw all-rights-reserved responses are retained only in recoverable Trash and
are represented in the immutable artifact by exact hashes and factual extracts.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import google_official_current_build_gap_20260722 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "coreweave-official-lancaster-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".coreweave-official-lancaster-current-build-gap.lock"

SOURCE_FILENAME = (
    "curated-official-2026-07-22-coreweave-chirisa-lancaster-greenfield-"
    "adaptive-reuse-current-build.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

CAPTURE_ORIGIN = Path("/private/tmp/dc-coreweave-lancaster-20260722.tONYf2")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-coreweave-lancaster-20260722.tONYf2")
CAPTURE_FILE_COUNT = 16
CAPTURE_TOTAL_BYTES = 1_733_862
CAPTURE_TREE_SHA256 = "def9f3dd0a78d88b2154e79cf5be8da7d560415f238268f99b43a11f4ee936ba"

V90_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v90.json"
V90_RELEASE = ROOT / "releases/2026-07-21-open-seed-v90"
V90_MANIFEST = V90_RELEASE / "manifest.json"
V90_ENTITIES = V90_RELEASE / "entities.csv"
V90_PINS = {
    V90_DEFINITION: (
        107_554,
        "3e224d0560e7f82fc31f7bdf6eb6b723ce50ad8423e2296de8c509b75c0fbdda",
    ),
    V90_MANIFEST: (
        15_902,
        "40be71c613c74e4e843c5c60ad85ce172c206f72350df5a0996b7e971ca54b66",
    ),
    V90_ENTITIES: (
        1_014_802,
        "732b1e8414532bf5ff9498b694678c9f4e6cacb83a2df4cadb7d135141d49aa8",
    ),
}
V90_TREE_SHA256 = "18cda7d054789dde956a393959cde79349f835927b1e757da364e15d974b78f3"
V90_INPUT_COUNT = 477
V90_ENTITY_COUNT = 973

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "chirisa-locations-headers.txt": (
        389,
        "c0de689add65703059041d373ec7d453921aca845669852774247e4e0454efba",
    ),
    "chirisa-locations.body": (
        164_315,
        "6217db82caf16b110532ddd7ef4a4888f1803a8d590d4920289394b29392cdf3",
    ),
    "coreweave-announcement-headers.txt": (
        1_151,
        "bb71ad2006a9d416f54b872ff347695118b6fa4d412808593c29bcf20fc613d2",
    ),
    "coreweave-announcement.body": (
        244_517,
        "7515a342503599cdff18f7c6f2e9ad747324de1d5dbdc13d2a38a9ec94377b98",
    ),
    "coreweave-investor-announcement-headers.txt": (
        1_793,
        "e5027f7d5305347301c50680c7b4cb7f3b8d0fd0a6f8ddd18931f16f997d0c2f",
    ),
    "coreweave-investor-announcement.body": (
        5_956,
        "73a832811aed061946d07709fcad03053e8c561beb190ee2d239dc108bf29853",
    ),
    "coreweave-pennsylvania-ai-hub-headers.txt": (
        1_951,
        "7c6d2fd94590ff0373f40eeaad1d535ee8db68bd1c117f929d2f45f5691f91ff",
    ),
    "coreweave-pennsylvania-ai-hub.body": (
        358_251,
        "3f87b3558eec1e8ef9662c00461c5f69e4e874b8f3bd096df8239cc8b6ba728b",
    ),
    "coreweave-year-review-canonical-headers.txt": (
        1_959,
        "fd15b0d4f979115e1f8df2ef1443f82622a2d283dfc96ea82c3764a5e8309c53",
    ),
    "coreweave-year-review-canonical.body": (
        365_220,
        "89b38b125eab0fcffbbcf68c90c351174122e50690d8583105bab4c3de24ba24",
    ),
    "coreweave-year-review-headers.txt": (
        1_151,
        "789a53f3eefd2de5a6b0a3fa3823c2a8cfe3ef5cd60dfe3d8978bf546971e1d4",
    ),
    "coreweave-year-review.body": (
        244_517,
        "06a4b99722a15a6ae1cb62eb5f229dd585ca9c32759e1dc082fb8f32d2ec8a3f",
    ),
    "lancaster-faq-headers.txt": (
        1_402,
        "577770d8fe34d38ce6bed6695bc68641c36d23578a57cb4c288c63ba43f998a4",
    ),
    "lancaster-faq.body": (
        176_288,
        "776f5cac90068dd1f4fc141583332f2364fa0503f147ec28b9805605cf3dc255",
    ),
    "lancaster-overview-headers.txt": (
        1_414,
        "17709bc51c815adaa97a931fa3f8acc03050e61841b902cc8aff2b0829d1bcce",
    ),
    "lancaster-overview.body": (
        163_588,
        "19ec67ad2862cf666da534961f5202e45f390bb0135b0ea0ced569da303499ef",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    file_stem: str
    requested_url: str
    effective_url: str
    retrieved_at: str
    published_at: str | None
    http_status: int
    content_type: str
    use: str


CAPTURES = (
    Capture(
        "coreweave_announcement_alias",
        "coreweave-announcement",
        "https://www.coreweave.com/news/coreweave-to-invest-more-than-6-billion-in-new-data-center-in-lancaster-pennsylvania",
        "https://www.coreweave.com/news/coreweave-to-invest-more-than-6-billion-in-new-data-center-in-lancaster-pennsylvania",
        "2026-07-22T01:27:06Z",
        "2025-07-15",
        404,
        "text/html; charset=utf-8",
        "failed_alias_capture",
    ),
    Capture(
        "coreweave_year_review_alias",
        "coreweave-year-review",
        "https://www.coreweave.com/blog/2025-year-in-review",
        "https://www.coreweave.com/blog/2025-year-in-review",
        "2026-07-22T01:27:07Z",
        "2025-12-31",
        404,
        "text/html; charset=utf-8",
        "failed_alias_capture",
    ),
    Capture(
        "lancaster_city_overview",
        "lancaster-overview",
        "https://www.cityoflancasterpa.gov/data-center/",
        "https://www.cityoflancasterpa.gov/data-center/",
        "2026-07-22T01:27:10Z",
        None,
        200,
        "text/html; charset=UTF-8",
        "normalized_identity_context",
    ),
    Capture(
        "lancaster_city_faq",
        "lancaster-faq",
        "https://www.cityoflancasterpa.gov/data-center/frequently-asked-questions/",
        "https://www.cityoflancasterpa.gov/data-center/frequently-asked-questions/",
        "2026-07-22T01:27:12Z",
        None,
        200,
        "text/html; charset=UTF-8",
        "normalized_boundary_context",
    ),
    Capture(
        "coreweave_investor_announcement",
        "coreweave-investor-announcement",
        "https://investors.coreweave.com/news/news-details/2025/CoreWeave-Announces-Multi-Billion-Dollar-Commitment-to-AI-Infrastructure-in-Pennsylvania/default.aspx",
        "https://investors.coreweave.com/news/news-details/2025/CoreWeave-Announces-Multi-Billion-Dollar-Commitment-to-AI-Infrastructure-in-Pennsylvania/default.aspx",
        "2026-07-22T01:27:25Z",
        "2025-07-15",
        403,
        "text/html; charset=UTF-8",
        "failed_capture_metadata_only",
    ),
    Capture(
        "coreweave_year_review",
        "coreweave-year-review-canonical",
        "https://www.coreweave.com/blog/we-said-we-would-then-we-did-ceo-end-of-year-message-2025",
        "https://www.coreweave.com/blog/we-said-we-would-then-we-did-ceo-end-of-year-message-2025",
        "2026-07-22T01:27:25Z",
        "2025-12-31",
        200,
        "text/html; charset=utf-8",
        "normalized_construction_corroboration",
    ),
    Capture(
        "chirisa_locations",
        "chirisa-locations",
        "https://chirisatechnologyparks.com/",
        "https://chirisatechnologyparks.com/",
        "2026-07-22T01:27:58Z",
        None,
        200,
        "text/html; charset=UTF-8",
        "normalized_physical_status",
    ),
    Capture(
        "coreweave_pennsylvania_ai_hub",
        "coreweave-pennsylvania-ai-hub",
        "https://www.coreweave.com/blog/building-pennsylvania-into-the-mid-atlantic-ai-hub",
        "https://www.coreweave.com/blog/building-pennsylvania-into-the-mid-atlantic-ai-hub",
        "2026-07-22T01:28:58Z",
        "2025-07-15",
        200,
        "text/html; charset=utf-8",
        "normalized_project_context",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    capture_id: str
    title: str
    publisher: str
    source_family: str
    kind: str
    excerpt: str
    factual_extract: Mapping[str, Any]


EVIDENCE = (
    EvidenceSpec(
        "lancaster-city-two-data-center-sites-observed-2026-07-22",
        "lancaster_city_overview",
        "Lancaster data center information",
        "City of Lancaster, Pennsylvania",
        "lancaster_city_data_center_pages",
        "government_record",
        "Lancaster identifies two separate Chirisa data-center properties: 216 Greenfield Road and 1375 Harrisburg Pike.",
        {
            "identity_scope": "The City treats 216 Greenfield Road and 1375 Harrisburg Pike as separate properties and data-center sites within the overall Lancaster project.",
            "role_context_not_normalized": "The City says Chirisa Technology Parks is developing the two sites; no standardized role is emitted in this tranche.",
        },
    ),
    EvidenceSpec(
        "lancaster-city-greenfield-phase1-harrisburg-boundary-observed-2026-07-22",
        "lancaster_city_faq",
        "Lancaster data center frequently asked questions",
        "City of Lancaster, Pennsylvania",
        "lancaster_city_data_center_pages",
        "government_record",
        "The City identifies Greenfield Phase 1 as adaptive reuse under a building permit and says planned Harrisburg Pike work requires land-development review.",
        {
            "greenfield_scope": "Phase 1 at 216 Greenfield Road is adaptive reuse of an existing building; the City had reviewed its building permit.",
            "greenfield_phase2_boundary": "Phase 2 extends beyond the existing footprint and requires Planning Commission land-development review; no Phase 2 physical-start claim is emitted.",
            "harrisburg_boundary": "Planned work at 1375 Harrisburg Pike requires land-development review and Planning Commission approval; no physical-start claim or entity is emitted.",
            "permit_guardrail": "The permit alone is not treated as construction proof; physical status comes from Chirisa's separate in-construction disclosure.",
        },
    ),
    EvidenceSpec(
        "chirisa-lancaster-east-lpe01-in-construction-observed-2026-07-22",
        "chirisa_locations",
        "Chirisa Technology Parks data center locations",
        "Chirisa Technology Parks",
        "chirisa_technology_parks_locations",
        "company_disclosure",
        "Chirisa lists Lancaster East LPE-01 as in construction and describes it as adaptive reuse of an existing shell.",
        {
            "physical_status_as_reported": "Lancaster East LPE-01 - in construction.",
            "scope_as_reported": "Adaptive reuse of existing shell.",
            "floor_area_context_not_normalized": "450,000 square feet is retained only as evidence metadata.",
            "power_context_not_normalized": "130 MW utility power available immediately is retained only as untyped context; it is not critical IT, site load, grid draw, installed or energized capacity, generation, or annual energy.",
            "status_semantics": "Dated last-observed official page state; no persistence after the retrieval date is asserted.",
        },
    ),
    EvidenceSpec(
        "coreweave-pennsylvania-flagship-groundbreaking-2025-12-31",
        "coreweave_year_review",
        "We Said We Would. Then We Did.",
        "CoreWeave",
        "coreweave_company_blog",
        "company_disclosure",
        "CoreWeave says it broke ground on a flagship facility in Pennsylvania and links that statement to its Lancaster project page.",
        {
            "physical_status_as_reported": "CoreWeave reported a Pennsylvania flagship among facilities on which it broke ground.",
            "identity_scope": "The in-page link targets CoreWeave's Lancaster, Pennsylvania project article; Chirisa and City sources supply the Greenfield construction-scope boundary.",
            "aggregate_guardrail": "CoreWeave's fleet counts and aggregate active or contracted power are not allocated to Lancaster.",
        },
    ),
    EvidenceSpec(
        "coreweave-lancaster-project-context-2025-07-15",
        "coreweave_pennsylvania_ai_hub",
        "Building Pennsylvania Into the Mid-Atlantic AI Hub",
        "CoreWeave",
        "coreweave_company_blog",
        "company_disclosure",
        "CoreWeave describes a Lancaster AI data-center investment and says the facility has room to grow up to 300 MW.",
        {
            "project_context": "CoreWeave describes a new Lancaster data center intended for AI workloads.",
            "investment_context_not_normalized": "An initial $6 billion equipment commitment is metadata only.",
            "power_context_not_normalized": "Potential growth up to 300 MW is untyped forward-looking context, not critical IT, site load, current draw, installed or energized capacity, generation, or annual energy.",
            "workload_guardrail": "AI wording is metadata only and creates no normalized facility type or workload observation.",
        },
    ),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}
EVIDENCE_KEYS = tuple(evidence.key for evidence in EVIDENCE)

CAMPUS_KEY = "curated:coreweave-chirisa-lancaster-greenfield-road-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:phase-1-adaptive-reuse"
PRIMARY_EVIDENCE_KEY = "chirisa-lancaster-east-lpe01-in-construction-observed-2026-07-22"


def _capture_metadata(capture: Capture) -> dict[str, Any]:
    body_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}.body"]
    headers_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location",
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "request_credentials_supplied": False,
        "http_status": capture.http_status,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body_pin[0]}-byte credential-free public "
            "response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            f"SHA-256 of the exact {headers_pin[0]}-byte raw HTTP "
            "response-header capture"
        ),
        "capture_headers_sha256": headers_pin[1],
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official "
            "bytes; raw bodies, headers, telemetry, and publisher media are "
            "not redistributed."
        ),
        "normalization_guardrail": (
            "No capacity, energy use, generation, PUE, WUE, facility type, "
            "operating model, workload, role, coordinate, geometry, satellite, "
            "aerial, map-click, or computer-vision claim is normalized."
        ),
    }


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    metadata = {**_capture_metadata(capture), **spec.factual_extract}
    return {
        "key": spec.key,
        "kind": spec.kind,
        "title": spec.title,
        "source_url": capture.effective_url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
        "metadata": metadata,
    }


def _entity(*, project: bool) -> dict[str, Any]:
    return {
        "stable_key": PROJECT_KEY if project else CAMPUS_KEY,
        "name": (
            "CoreWeave/Chirisa Lancaster Greenfield Phase 1 Adaptive-Reuse Project"
            if project
            else "CoreWeave/Chirisa Lancaster Greenfield Road Campus"
        ),
        "country": "United States",
        "address": "216 Greenfield Road, Lancaster, Pennsylvania, United States",
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": PRIMARY_EVIDENCE_KEY,
        "as_of_date": "2026-07-22",
        "method": "authoritative_locality",
        "confidence": 0.97,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        SOURCE_FILENAME: {
            "schema_version": "1.1",
            "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in EVIDENCE_KEYS],
            "campus": _entity(project=False),
            "project": _entity(project=True),
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": PRIMARY_EVIDENCE_KEY,
                    "as_of_date": "2026-07-22",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
            "operating_models": [],
            "workloads": [],
            "capacities": [],
        }
    }


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    document = documents[SOURCE_FILENAME]
    payload = _canonical(document)
    return [
        {
            "path": f"sources/{SOURCE_FILENAME}",
            "bytes": len(payload),
            "sha256": _sha256_bytes(payload),
            "schema_version": "1.1",
            "country": "United States",
            "campus_stable_key": CAMPUS_KEY,
            "project_stable_key": PROJECT_KEY,
            "evidence_records": len(EVIDENCE),
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_bounded_adaptive_reuse_construction",
            "seed_eligible": True,
            "seeded": False,
        }
    ]


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


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for target, pin in V90_PINS.items():
        _pin(target, pin)
    if tree_digest(V90_RELEASE) != V90_TREE_SHA256:
        raise RuntimeError("v90 release tree differs")
    definition = json.loads(V90_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V90_INPUT_COUNT:
        raise RuntimeError("v90 selected input inventory differs")

    planned_stable, planned_evidence = _planned_keys(documents)
    with V90_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    if len(base_rows) != V90_ENTITY_COUNT:
        raise RuntimeError("v90 entity count differs")
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Lancaster stable key collides with v90")
    locality_hits = [
        {
            "stable_key": row["stable_key"],
            "name": row["name"],
            "address": row["address"],
        }
        for row in base_rows
        if "216 greenfield road" in (row.get("address") or "").lower()
        or "1375 harrisburg pike" in (row.get("address") or "").lower()
    ]
    if locality_hits:
        raise RuntimeError("v90 contains an exact Lancaster address witness")
    source_inputs = json.loads(
        (V90_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    ).get("sources")
    base_evidence = {
        key
        for row in source_inputs or []
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Lancaster evidence key collides with v90")
    return {
        "v90_selected_input_count": len(selected),
        "v90_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v90_stable_key_collisions": [],
        "exact_v90_evidence_key_collisions": [],
        "exact_v90_address_matches": [],
        "exact_existing_identity_keys_reused": [],
        "identity_resolution": (
            "New curated campus and project keys are used. No existing atlas "
            "identity, coordinate, geometry, capacity, role, or status is inherited."
        ),
        "official_join_boundary": (
            "The City identifies Greenfield Phase 1 as adaptive reuse and "
            "separates Harrisburg Pike as planned review work; Chirisa identifies "
            "Lancaster East LPE-01 adaptive reuse as in construction."
        ),
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 2,
        "seed_eligible_candidate_count": 1,
        "seed_eligible_source_record_count": 1,
        "review_only_count": 1,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "lancaster-greenfield-phase1-adaptive-reuse",
                "decision": "seed_eligible_bounded_adaptive_reuse_construction",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "existing_atlas_identity_link": None,
                "lifecycle": {
                    "status": "under_construction",
                    "as_of_date": "2026-07-22",
                    "method": "authoritative_physical_status_update",
                    "current_status_persisted": False,
                },
                "official_join": {
                    "city_greenfield_scope": (
                        "Phase 1 at 216 Greenfield Road is adaptive reuse of an "
                        "existing building under a City-reviewed building permit."
                    ),
                    "chirisa_physical_scope": (
                        "Lancaster East LPE-01 is in construction and is adaptive "
                        "reuse of an existing shell."
                    ),
                    "harrisburg_exclusion": (
                        "1375 Harrisburg Pike remains planned work requiring "
                        "land-development review and Planning Commission approval."
                    ),
                },
                "reported_power_context_not_normalized": [
                    {
                        "value": 100,
                        "unit": "MW",
                        "qualifier": "initial data-center figure",
                        "typing": "untyped_metadata_only",
                        "source_url": CAPTURE_BY_ID[
                            "coreweave_investor_announcement"
                        ].requested_url,
                        "retrieval_boundary": (
                            "The credential-free raw endpoint returned HTTP 403; "
                            "the figure is retained only as official announcement "
                            "context and is not source-record evidence."
                        ),
                    },
                    {
                        "value": 300,
                        "unit": "MW",
                        "qualifier": "potential growth up to",
                        "typing": "untyped_forward_looking_metadata_only",
                        "source_url": CAPTURE_BY_ID[
                            "coreweave_pennsylvania_ai_hub"
                        ].effective_url,
                    },
                    {
                        "value": 130,
                        "unit": "MW",
                        "qualifier": "utility power available immediately",
                        "typing": "utility_availability_metadata_only",
                        "source_url": CAPTURE_BY_ID["chirisa_locations"].effective_url,
                    },
                ],
                "role_context_not_normalized": {
                    "coreweave": "tenant/partner context only",
                    "chirisa_technology_parks": "developer context only",
                    "machine_investment_group": "co-development context only",
                },
                "withheld": [
                    "capacity or energy normalization",
                    "generation or grid-load inference",
                    "PUE or WUE",
                    "facility type or workload",
                    "standardized role",
                    "coordinates or geometry",
                    "satellite, aerial, or computer-vision claim",
                    "current-status persistence",
                ],
            },
            {
                "candidate_id": "lancaster-harrisburg-pike",
                "decision": "review_only_land_development_preconstruction",
                "source_paths": [],
                "seed_eligible": False,
                "address": (
                    "1375 Harrisburg Pike, Lancaster, Pennsylvania, United States"
                ),
                "official_factual_extract": (
                    "The City says planned work at this site requires land-"
                    "development review and Planning Commission approval."
                ),
                "boundary": (
                    "Planning, site control, proposed use, and land-development "
                    "review do not establish a physical construction start."
                ),
                "stable_key_created": False,
                "lifecycle_claim_created": False,
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": 5,
        "failed_http_body_captures": 3,
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
                "requested_url": capture.requested_url,
                "effective_url": capture.effective_url,
                "retrieved_at": capture.retrieved_at,
                "body": {
                    "path": f"{capture.file_stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.file_stem}-headers.txt",
                    "bytes": CAPTURE_FILE_PINS[
                        f"{capture.file_stem}-headers.txt"
                    ][0],
                    "sha256": CAPTURE_FILE_PINS[
                        f"{capture.file_stem}-headers.txt"
                    ][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "http_status": capture.http_status,
                "content_type": capture.content_type,
                "request_credentials_supplied": False,
                "claim_use": capture.use,
            }
            for capture in CAPTURES
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return _sha256_bytes(payload)


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 2,
        "source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 1,
        "distinct_campuses_in_source_records": 1,
        "projects": 1,
        "distinct_entities_in_source_records": 2,
        "new_entities_against_v90": 2,
        "exact_existing_identity_keys_reused": 0,
        "source_document_entity_snapshots": 2,
        "unique_imported_entity_snapshots": 2,
        "source_document_evidence_references": 5,
        "unique_evidence_records": 5,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "energy_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "satellite_observations": 0,
        "computer_vision_observations": 0,
    }
    readme = f"""# CoreWeave/Chirisa Lancaster official-source tranche

This immutable artifact accepts only the 216 Greenfield Road Phase 1 adaptive-reuse construction scope. The official City record identifies Greenfield Phase 1 as adaptive reuse and separates 1375 Harrisburg Pike as planned work requiring land-development review. Chirisa's official locations page identifies Lancaster East LPE-01 as in construction and adaptive reuse of an existing shell. New curated campus/project keys are used; no existing atlas identity is linked or inherited.

Harrisburg Pike remains review-only. The reported 100 MW initial figure, potential 300 MW expansion, and 130 MW utility-availability statement remain untyped metadata only. CoreWeave and Chirisa role language also remains metadata only. No normalized capacity, energy, generation, PUE, WUE, facility type, operating model, workload, role, coordinate, geometry, satellite, aerial, map-click, computer-vision, completion, commissioning, occupancy, or operation claim is emitted. Under-construction is a dated last-observed fact; current status after the retrieval date is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v90_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v90.json",
                "bytes": V90_PINS[V90_DEFINITION][0],
                "sha256": V90_PINS[V90_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v90/manifest.json",
                "bytes": V90_PINS[V90_MANIFEST][0],
                "sha256": V90_PINS[V90_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v90/entities.csv",
                "bytes": V90_PINS[V90_ENTITIES][0],
                "sha256": V90_PINS[V90_ENTITIES][1],
            },
            "release_tree_sha256": V90_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v90_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_to_trash_after_source_publication": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": (
            "All captured official response bodies are treated as all-rights-"
            "reserved; no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        target = paths[name]
        if (
            target.is_symlink()
            or not target.is_file()
            or target.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(target.stat().st_mode) != 0o444
        ):
            raise RuntimeError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("source invented coordinates or geometry")
    if any(
        document[entity]["roles"]
        for document in documents
        for entity in ("campus", "project")
    ):
        raise RuntimeError("source invented roles")
    if any(
        document[collection]
        for document in documents
        for collection in ("operating_models", "workloads", "capacities")
    ):
        raise RuntimeError("source invented normalized non-lifecycle claims")
    document = documents[0]
    if document["campus"]["stable_key"] != CAMPUS_KEY:
        raise RuntimeError("campus key differs")
    if document["project"]["stable_key"] != PROJECT_KEY:
        raise RuntimeError("project key differs")
    if document["lifecycle"] != [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": PRIMARY_EVIDENCE_KEY,
            "as_of_date": "2026-07-22",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]:
        raise RuntimeError("lifecycle contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for target in SOURCES_ROOT.glob("*.json"):
        if target.name in source_names:
            continue
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
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
            collisions[str(target.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"source collision detected: {collisions!r}")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("capture directory closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("capture directory aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="coreweave-lancaster-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(
                connection, paths[SOURCE_FILENAME], recorded_at=recorded_at
            )
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
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 5,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
    ):
        raise RuntimeError("artifact must be a frozen ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries.values()
    ):
        raise RuntimeError("artifact closed frozen set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 2
        or manifest.get("curated_source_records") != 1
        or manifest.get("seed_eligible_candidates") != 1
        or manifest.get("review_only_candidates") != 1
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise RuntimeError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise RuntimeError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    if assessment["candidates"][1]["source_paths"] != []:
        raise RuntimeError("Harrisburg review-only boundary differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
    if require_live and path == ARTIFACT and path.stat().st_ctime + 1e-6 < target.timestamp():
        raise RuntimeError("artifact final root predates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("offline replay differs")
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        target = stage / name
        target.write_bytes(_canonical(documents[name]))
        target.chmod(0o444)
        _fsync_regular(target)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        target = stage / name
        target.write_bytes(payloads[name])
        target.chmod(0o444)
        _fsync_regular(target)
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
        "candidate_assessments": 2,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 1,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": 5,
        "failed_http_body_captures": 3,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_source_publication": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _assert_stage_precedes(stage: Path, recorded_at: str) -> None:
    target = _instant(recorded_at).timestamp()
    entries = [stage, *stage.rglob("*")]
    if any(entry.stat(follow_symlinks=False).st_mtime > target for entry in entries):
        raise RuntimeError("staged byte post-dates recorded_at")


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active Lancaster source publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if (
        any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("Lancaster source final-path collision")
    _validate_source_collisions()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".coreweave-lancaster-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        _assert_stage_precedes(source_stage, recorded_at)
        _assert_stage_precedes(artifact_stage, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            wall_clock=_instant(recorded_at),
        )
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
        raise


def _publish(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    if (
        any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("late Lancaster source final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
        _fsync_directory(SOURCES_ROOT)
        _fsync_directory(ARTIFACT_ROOT)
        if ARTIFACT.stat().st_ctime + 1e-6 < target.timestamp():
            raise RuntimeError("artifact final root predates recorded_at")
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both raw capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    source_exists = all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES)
    if ARTIFACT.exists() and source_exists:
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {
            "artifact": str(ARTIFACT),
            "artifact_tree_sha256": tree_digest(ARTIFACT),
            "capture_trash": str(CAPTURE_TRASH),
            "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "source_records": 1,
            "status": "existing-identical",
        }
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial Lancaster source final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("source stage not empty after publication")
        prepared.source_stage.rmdir()
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 1,
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
