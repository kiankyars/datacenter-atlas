"""Publish the bounded AWS Clinton adaptive-reuse official-source tranche.

The tranche joins a March 3, 2026 City of Clinton statement that physical
building rehabilitation had begun, while the operator remained undisclosed,
to the City's June 9 disclosure identifying AWS and the former Delphi plant.
It emits one dated ``under_construction`` observation and no normalized
capacity, energy, efficiency, operating-model, workload, role, or location
claim.
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
from . import vantage_official_reno_nv1_current_build_gap_20260722 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "aws-official-clinton-adaptive-reuse-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".aws-official-clinton-adaptive-reuse-current-build-gap.lock"

SOURCE_FILENAME = (
    "curated-official-2026-07-22-aws-clinton-former-delphi-"
    "adaptive-reuse-current-build.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

CAPTURE_ORIGIN = Path("/private/tmp/dc-aws-clinton-20260722.wfMnfg")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-aws-clinton-20260722.wfMnfg")
CAPTURE_FILE_COUNT = 8
CAPTURE_TOTAL_BYTES = 1_960_857
CAPTURE_TREE_SHA256 = "e54e74d3513a4b8a95e181ca2d58c70008e81433e70fd70142d062f0f199f66d"

V91_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v91.json"
V91_RELEASE = ROOT / "releases/2026-07-21-open-seed-v91"
V91_MANIFEST = V91_RELEASE / "manifest.json"
V91_ENTITIES = V91_RELEASE / "entities.csv"
V91_PINS = {
    V91_DEFINITION: (
        108_188,
        "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a",
    ),
    V91_MANIFEST: (
        15_954,
        "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9",
    ),
    V91_ENTITIES: (
        1_018_118,
        "b1f07223ff1a61e64670aaf23bc9b3a7ee5834c2131e031a59401b404acebe75",
    ),
}
V91_TREE_SHA256 = "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e"
V91_INPUT_COUNT = 480
V91_ENTITY_COUNT = 978

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
    "amazon_context.body": (
        202_472,
        "bb3541b69ca2622d32cd96612df1c8c0cb1a571ea45398f8c98c3de8005d46b3",
    ),
    "amazon_context.headers": (
        2_393,
        "709b29591e6848940307c09378c65c9785efdf9d0c4287b33e3d90d1686417e9",
    ),
    "amazon_liveblog.body": (
        1_163_552,
        "e0e57468bcf21591e3f74e2961f835a4b4bdf3237659bd031292e941c1f12b5a",
    ),
    "amazon_liveblog.headers": (
        2_408,
        "eb303052854f196830a7425d994bc1265a31f474817b6ac182be41e076411138",
    ),
    "city_june.body": (
        293_967,
        "3347ac1d110793d8d07af54a06342652b4cbac97680ada69ae39b7bd5b8d83ed",
    ),
    "city_june.headers": (
        1_385,
        "5914ee5a2ebb6288c8362ae500fbd1dcbcd200d466c4269184c511ffdbd4e930",
    ),
    "city_march.body": (
        293_295,
        "ac8b9ec26ea4771c92f90da200ea9dc59a408589e3ed9b68128c6b4662460d32",
    ),
    "city_march.headers": (
        1_385,
        "6df26520342671478bdab9977a77904205a7066d4c4e9fa3b384cbdc435d19aa",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    file_stem: str
    url: str
    retrieved_at: str
    published_at: str | None
    content_type: str
    use: str


CAPTURES = (
    Capture(
        "city_march_physical_start",
        "city_march",
        "https://clintonms.org/industrialparkdevelopment/",
        "2026-07-22T01:40:10Z",
        "2026-03-03",
        "text/html; charset=UTF-8",
        "normalized_physical_start_operator_withheld",
    ),
    Capture(
        "city_june_identity_resolution",
        "city_june",
        "https://clintonms.org/awsdatacenter/",
        "2026-07-22T01:40:10Z",
        "2026-06-09",
        "text/html; charset=UTF-8",
        "normalized_aws_former_delphi_identity_join",
    ),
    Capture(
        "amazon_clinton_liveblog_item",
        "amazon_liveblog",
        "https://www.aboutamazon.com/news/aws/amazon-data-centers-locations-news?p=amazon-retrofit-of-closed-manufacturing-plant-in-clinton-mississippi-to-create-100-full-time-jobs",
        "2026-07-22T01:40:11Z",
        "2026-06-09",
        "text/html; charset=utf-8",
        "adaptive_reuse_identity_context_only",
    ),
    Capture(
        "amazon_mississippi_investment_context",
        "amazon_context",
        "https://www.aboutamazon.com/news/company-news/amazon-25-billion-mississippi-data-centers",
        "2026-07-22T01:40:11Z",
        "2026-04-09",
        "text/html; charset=utf-8",
        "investment_jobs_grid_water_context_only",
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
        "city-clinton-industrial-building-rehabilitation-begun-2026-03-03",
        "city_march_physical_start",
        "Clinton Industrial Park development update",
        "City of Clinton, Mississippi",
        "city_of_clinton_industrial_park",
        "government_record",
        "The City said some construction activities to rehabilitate the building had begun while the developer remained undisclosed.",
        {
            "physical_status_as_reported": "Some construction activities to rehabilitate the building had begun by March 3, 2026.",
            "operator_identity_at_observation": "Withheld by the City while negotiations continued; AWS is joined only through the later City disclosure.",
            "power_context_not_normalized": "The project was described as having no on-site power plant and using Entergy's existing grid; this creates no power, utility-role, generation, capacity, or energy observation.",
            "water_context_not_normalized": "The City said no potable water would be used for cooling and office use would be the only potable-water demand; no WUE, water volume, cooling type, or measured-use field is normalized.",
            "status_semantics": "Dated physical start only; status persistence after March 3 is not asserted.",
        },
    ),
    EvidenceSpec(
        "city-clinton-aws-former-delphi-adaptive-reuse-2026-06-09",
        "city_june_identity_resolution",
        "AWS announces $1 billion data center investment in Clinton",
        "City of Clinton, Mississippi",
        "city_of_clinton_aws_former_delphi",
        "government_record",
        "The City identifies AWS as repurposing the former Delphi manufacturing facility into a data center and describes construction activity.",
        {
            "identity_resolution": "The later City disclosure resolves the previously undisclosed Clinton Industrial Park rehabilitation project to AWS at the former Delphi manufacturing facility.",
            "adaptive_reuse_context": "AWS is repurposing the existing former Delphi plant rather than constructing a new facility from the ground up.",
            "investment_context_not_normalized": "$1 billion is investment metadata only; it is not allocated to capacity, energy, buildings, or phases.",
            "jobs_context_not_normalized": "At least 100 full-operation positions and broader construction employment are metadata only.",
            "water_and_utility_context_not_normalized": "Water-positive and Entergy-cost statements create no WUE, water-use, capacity, energy, operating-model, or role observation.",
            "type_workload_guardrail": "State-of-the-art and AWS data-center wording creates no normalized facility type or workload.",
        },
    ),
    EvidenceSpec(
        "amazon-clinton-former-delphi-liveblog-item-2026-06-09",
        "amazon_clinton_liveblog_item",
        "Amazon retrofit of closed manufacturing plant in Clinton, Mississippi",
        "Amazon",
        "amazon_data_center_communities_liveblog",
        "company_disclosure",
        "Amazon's Clinton item says the former Delphi industrial building is being fully retrofitted into a functioning data center through adaptive reuse.",
        {
            "liveblog_item_binding": "Only the Clinton section headed 'Amazon retrofit of closed manufacturing plant in Clinton, Mississippi to create 100 full-time jobs' is bound.",
            "item_timestamp": "2026-06-09T16:33:15Z",
            "page_date_guardrail": "The rolling liveblog's page-level publication metadata and unrelated items are not used as the Clinton item's publication date or status evidence.",
            "identity_context": "Former Delphi facility in Clinton, closed in 2009, is described as an Amazon adaptive-reuse retrofit.",
            "jobs_context_not_normalized": "At least 100 full-time jobs is metadata only.",
        },
    ),
    EvidenceSpec(
        "amazon-mississippi-investment-context-2026-04-09",
        "amazon_mississippi_investment_context",
        "Amazon plans $25 billion in Mississippi data centers",
        "Amazon",
        "amazon_mississippi_data_centers",
        "company_disclosure",
        "Amazon identifies a $1 billion Hinds County investment transforming the former Delphi plant within a $25 billion statewide plan.",
        {
            "identity_context": "The former Delphi plant is identified as the Hinds County data-center facility transformation.",
            "investment_context_not_normalized": "$1 billion is project context and $25 billion is a statewide aggregate; neither is allocated or treated as capacity or energy.",
            "jobs_context_not_normalized": "2,000 jobs is a statewide aggregate and is not attributed to the Clinton project.",
            "grid_context_not_normalized": "Entergy grid investments and energy-project figures are statewide context, not Clinton capacity, generation, draw, or annual energy.",
            "water_context_not_normalized": "Statewide and Canton cooling statements are not attributed to Clinton and create no Clinton WUE or water-use observation.",
        },
    ),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}
EVIDENCE_KEYS = tuple(evidence.key for evidence in EVIDENCE)

CAMPUS_KEY = "curated:aws-clinton-former-delphi-adaptive-reuse-campus"
PROJECT_KEY = (
    "curated:aws-clinton-former-delphi-adaptive-reuse-campus:"
    "existing-building-retrofit"
)
PRIMARY_EVIDENCE_KEY = (
    "city-clinton-industrial-building-rehabilitation-begun-2026-03-03"
)
IDENTITY_EVIDENCE_KEY = (
    "city-clinton-aws-former-delphi-adaptive-reuse-2026-06-09"
)
SOURCE_ADDRESS = (
    "Former Delphi manufacturing facility, Clinton, Mississippi, United States"
)


def _capture_metadata(capture: Capture) -> dict[str, Any]:
    body_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}.body"]
    headers_pin = CAPTURE_FILE_PINS[f"{capture.file_stem}.headers"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location",
        "requested_url": capture.url,
        "effective_url": capture.url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body_pin[0]}-byte credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            f"SHA-256 of the exact {headers_pin[0]}-byte raw HTTP response-header capture"
        ),
        "capture_headers_sha256": headers_pin[1],
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bodies, headers, telemetry, and publisher media are not redistributed.",
        "normalization_guardrail": "Only one dated project under_construction lifecycle is normalized; no capacity, annual energy, PUE, WUE, operating model, workload, facility type, role, coordinate, geometry, satellite, aerial, map-click, computer-vision, persistence, or unique-site claim is normalized.",
    }


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    return {
        "key": spec.key,
        "kind": spec.kind,
        "title": spec.title,
        "source_url": capture.url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
        "metadata": {**_capture_metadata(capture), **spec.factual_extract},
    }


def _entity(*, project: bool) -> dict[str, Any]:
    return {
        "stable_key": PROJECT_KEY if project else CAMPUS_KEY,
        "name": (
            "AWS Clinton Former Delphi Existing-Building Retrofit"
            if project
            else "AWS Clinton Former Delphi Adaptive-Reuse Campus"
        ),
        "country": "United States",
        "address": SOURCE_ADDRESS,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": IDENTITY_EVIDENCE_KEY,
        "as_of_date": "2026-06-09",
        "method": "authoritative_locality",
        "confidence": 0.96,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        SOURCE_FILENAME: {
            "schema_version": "1.1",
            "evidence": [
                _evidence(EVIDENCE_BY_KEY[key]) for key in EVIDENCE_KEYS
            ],
            "campus": _entity(project=False),
            "project": _entity(project=True),
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": PRIMARY_EVIDENCE_KEY,
                    "as_of_date": "2026-03-03",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.95,
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
    payload = _canonical(documents[SOURCE_FILENAME])
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
            "disposition": "seed_eligible_dated_adaptive_reuse_construction_start",
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


def _collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for target, pin in V91_PINS.items():
        _pin(target, pin)
    if tree_digest(V91_RELEASE) != V91_TREE_SHA256:
        raise RuntimeError("v91 release tree differs")
    definition = json.loads(V91_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V91_INPUT_COUNT:
        raise RuntimeError("v91 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V91_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    if len(base_rows) != V91_ENTITY_COUNT:
        raise RuntimeError("v91 entity count differs")
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned AWS Clinton stable key collides with v91")
    exact_address_hits = [
        row
        for row in base_rows
        if (row.get("address") or "").strip().casefold()
        == SOURCE_ADDRESS.casefold()
    ]
    keyword_hits = [
        row
        for row in base_rows
        if any(
            token in " ".join(
                (
                    row.get("name") or "",
                    row.get("address") or "",
                    row.get("stable_key") or "",
                )
            ).casefold()
            for token in ("former delphi", "aws clinton", "clinton former delphi")
        )
    ]
    if exact_address_hits or keyword_hits:
        raise RuntimeError("v91 contains an AWS Clinton/Former Delphi identity witness")
    source_inputs = json.loads(
        (V91_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    ).get("sources")
    base_evidence = {
        key
        for row in source_inputs or []
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned AWS Clinton evidence key collides with v91")
    return {
        "v91_selected_input_count": len(selected),
        "v91_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v91_stable_key_collisions": [],
        "exact_v91_evidence_key_collisions": [],
        "exact_v91_address_matches": [],
        "v91_clinton_delphi_keyword_matches": [],
        "exact_existing_identity_keys_reused": [],
        "identity_resolution": "New curated campus and retrofit-project keys are used. The March physical-start statement is joined to AWS/former-Delphi identity only through the later City disclosure; no capacity, status persistence, role, coordinate, or geometry is inherited.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 1,
        "seed_eligible_candidate_count": 1,
        "seed_eligible_source_record_count": 1,
        "review_only_count": 0,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "aws-clinton-former-delphi-existing-building-retrofit",
                "decision": "seed_eligible_dated_adaptive_reuse_construction_start",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "existing_atlas_identity_link": None,
                "identity_join": {
                    "physical_observation_evidence_key": PRIMARY_EVIDENCE_KEY,
                    "identity_resolution_evidence_key": IDENTITY_EVIDENCE_KEY,
                    "physical_observation_date": "2026-03-03",
                    "identity_resolution_date": "2026-06-09",
                    "operator_withheld_at_physical_observation": True,
                    "resolved_operator_context": "AWS",
                    "resolved_asset_context": "former Delphi manufacturing facility",
                },
                "lifecycle": {
                    "status": "under_construction",
                    "as_of_date": "2026-03-03",
                    "method": "authoritative_physical_status_update",
                    "current_status_persisted": False,
                },
                "normalized_capacity": None,
                "reported_context_not_normalized": [
                    {
                        "value": 1_000_000_000,
                        "unit": "USD",
                        "scope": "AWS Clinton/Hinds County investment",
                        "reason": "investment metadata, not capacity or energy",
                    },
                    {
                        "value": 25_000_000_000,
                        "unit": "USD",
                        "scope": "Amazon Mississippi statewide planned investment",
                        "reason": "statewide non-additive aggregate",
                    },
                    {
                        "value": 100,
                        "unit": "jobs",
                        "scope": "at least full-operation Clinton positions",
                        "reason": "employment metadata",
                    },
                    {
                        "value": 2_000,
                        "unit": "jobs",
                        "scope": "statewide Mississippi operations",
                        "reason": "statewide aggregate not allocated to Clinton",
                    },
                ],
                "water_utility_context_not_normalized": {
                    "city_march": "No on-site power plant; Entergy existing-grid and no-potable-water-for-cooling statements are metadata only.",
                    "city_june": "Water-positive pledge and utility cost/allocation statements are metadata only.",
                    "amazon_context": "Statewide grid, renewable-energy, and Canton water statements are not attributed to Clinton.",
                },
                "withheld": [
                    "critical-IT, utility, installed, energized, or draw capacity",
                    "annual energy or generation",
                    "PUE or WUE",
                    "facility type or workload",
                    "operating model or standardized role",
                    "coordinates or geometry",
                    "satellite, aerial, or computer-vision claim",
                    "current-status persistence",
                    "unique physical-site claim",
                ],
            }
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
        "successful_http_200_body_captures": len(CAPTURES),
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
                "retrieved_at": capture.retrieved_at,
                "published_at": capture.published_at,
                "body": {
                    "path": f"{capture.file_stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.file_stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.headers"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "http_status": 200,
                "content_type": capture.content_type,
                "request_credentials_supplied": False,
                "claim_use": capture.use,
                "liveblog_section_binding": (
                    "clinton_item_only"
                    if capture.capture_id == "amazon_clinton_liveblog_item"
                    else None
                ),
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
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 1,
        "source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 0,
        "distinct_campuses_in_source_records": 1,
        "projects": 1,
        "distinct_entities_in_source_records": 2,
        "new_entities_against_v91": 2,
        "exact_existing_identity_keys_reused": 0,
        "source_document_entity_snapshots": 2,
        "unique_imported_entity_snapshots": 2,
        "source_document_evidence_references": 4,
        "unique_evidence_records": 4,
        "lifecycle_observations": 1,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "normalized_critical_it_mw_sum": 0,
        "annual_energy_estimates": 0,
        "pue_estimates": 0,
        "wue_estimates": 0,
        "coordinates_present": 0,
        "geometry_present": 0,
        "satellite_observations": 0,
        "computer_vision_observations": 0,
        "unique_physical_sites_claimed": 0,
    }
    readme = f"""# AWS Clinton former-Delphi adaptive-reuse tranche

This immutable artifact publishes one newly keyed AWS Clinton campus and one existing-building retrofit project. A March 3, 2026 City of Clinton statement says physical rehabilitation had begun while the operator remained undisclosed. The City's June 9 disclosure identifies AWS and the former Delphi manufacturing facility, supporting the bounded identity join. One dated `under_construction` lifecycle observation is normalized at March 3; status persistence is false.

The $1 billion project investment, $25 billion statewide investment, project and statewide job figures, water statements, and utility/grid statements remain non-additive, unallocated metadata only. No capacity, annual energy, PUE, WUE, facility type, workload, operating model, standardized role, coordinate, geometry, satellite, aerial, map-click, computer-vision, current-status persistence, or unique-site claim is emitted. The Amazon rolling liveblog capture is bound only to its Clinton section and that section's June 9 timestamp; unrelated liveblog items and page-level dates are excluded.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication. No open-seed definition or release was created or mutated.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v91_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v91.json",
                "bytes": V91_PINS[V91_DEFINITION][0],
                "sha256": V91_PINS[V91_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v91/manifest.json",
                "bytes": V91_PINS[V91_MANIFEST][0],
                "sha256": V91_PINS[V91_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v91/entities.csv",
                "bytes": V91_PINS[V91_ENTITIES][0],
                "sha256": V91_PINS[V91_ENTITIES][1],
            },
            "release_tree_sha256": V91_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v91_mutated": False,
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
        "source_rights": "All captured official response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
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
        "candidate-assessment.json": _canonical(
            _candidate_assessment(recorded_at)
        ),
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
    document = expected[SOURCE_FILENAME]
    if any(
        document[entity][field] is not None
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("source invented coordinates or geometry")
    if any(document[entity]["roles"] for entity in ("campus", "project")):
        raise RuntimeError("source invented roles")
    if (
        document["operating_models"]
        or document["workloads"]
        or document["capacities"]
    ):
        raise RuntimeError("source invented model, workload, or capacity")
    expected_lifecycle = [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": PRIMARY_EVIDENCE_KEY,
            "as_of_date": "2026-03-03",
            "method": "authoritative_physical_status_update",
            "confidence": 0.95,
        }
    ]
    if document["lifecycle"] != expected_lifecycle:
        raise RuntimeError("lifecycle contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    collisions: dict[str, Any] = {}
    for target in SOURCES_ROOT.glob("*.json"):
        if target.name in SOURCE_FILENAMES:
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
        prefix="aws-clinton-import-", dir="/private/tmp"
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
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 4,
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
        or manifest.get("candidate_assessments") != 1
        or manifest.get("curated_source_records") != 1
        or manifest.get("seed_eligible_candidates") != 1
        or manifest.get("review_only_candidates") != 0
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
    expected = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise RuntimeError(f"artifact content differs: {name}")
    snapshot = json.loads(
        entries["source-snapshot.json"].read_text(encoding="utf-8")
    )
    totals = snapshot["totals"]
    if snapshot["source_records"] != source_records or any(
        totals[key] != 0
        for key in (
            "capacity_estimates",
            "normalized_critical_it_mw_sum",
            "annual_energy_estimates",
            "pue_estimates",
            "wue_estimates",
            "operating_model_observations",
            "workload_observations",
            "coordinates_present",
            "geometry_present",
            "satellite_observations",
            "computer_vision_observations",
            "unique_physical_sites_claimed",
        )
    ):
        raise RuntimeError("artifact zero-normalization contract differs")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    candidate = assessment["candidates"][0]
    if (
        candidate["lifecycle"]["current_status_persisted"] is not False
        or candidate["normalized_capacity"] is not None
        or candidate["identity_join"]["operator_withheld_at_physical_observation"]
        is not True
    ):
        raise RuntimeError("identity join or lifecycle persistence differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
    if (
        require_live
        and path == ARTIFACT
        and path.stat().st_ctime + 1e-6 < target.timestamp()
    ):
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
        "candidate_assessments": 1,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 0,
        "controlled_capture_count": len(CAPTURES),
        "successful_http_200_body_captures": len(CAPTURES),
        "failed_http_body_captures": 0,
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
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8"
    )
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _assert_stage_precedes(stage: Path, recorded_at: str) -> None:
    target = _instant(recorded_at).timestamp()
    if any(
        entry.stat(follow_symlinks=False).st_mtime > target
        for entry in [stage, *stage.rglob("*")]
    ):
        raise RuntimeError("staged byte post-dates recorded_at")


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active AWS Clinton source publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    identity = (
        os.fstat(descriptor).st_dev,
        os.fstat(descriptor).st_ino,
    )
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
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("AWS Clinton source final-path collision")
    _validate_source_collisions()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".aws-clinton-sources.", dir=SOURCES_ROOT)
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
        time.sleep(
            min(0.25, (target - datetime.now(UTC)).total_seconds())
        )
    if (
        any(
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
        or ARTIFACT.exists()
        or ARTIFACT.is_symlink()
    ):
        raise RuntimeError("late AWS Clinton source final-path collision")
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
    source_exists = all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    )
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
            (SOURCES_ROOT / name).exists()
            or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise RuntimeError("partial AWS Clinton source final-path collision")
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
