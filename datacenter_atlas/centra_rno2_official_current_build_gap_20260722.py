"""Publish a bounded official-source record for CENTRA RNO2 in Reno.

The governed source record maps CENTRA's dated top-out disclosure to the
``shell`` lifecycle state and records generic colocation from direct official
carrier-neutral/colocation language.  The repeatedly reported 4.4 MW remains
untyped metadata because no captured official source calls it critical IT load
or IT capacity.  Novva West Jordan phases 2 and 3 are documented as review-only:
their last phase-specific physical observations date to the March 2025 release,
despite a later CMS update date.  No open seed or downstream release is changed.
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
from . import official_nordic_iren_current_build_gap_20260722 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "centra-rno2-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".centra-rno2-official-current-build-gap.lock"

SOURCE_FILENAME = (
    "curated-official-2026-07-22-centra-rno2-reno-shell-current-build.json"
)
SOURCE_FILENAMES = (SOURCE_FILENAME,)

CAPTURE_ORIGIN = Path("/private/tmp/dc-centra-novva-20260722.Szu08f")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-centra-novva-20260722.Szu08f")
CAPTURE_FILE_COUNT = 14
CAPTURE_TOTAL_BYTES = 4_717_075
CAPTURE_TREE_SHA256 = (
    "c88a934b5c43bf274fc46497e0b215a2e3ac3e87636c16bdbf098e9fb8203579"
)

V94_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v94.json"
V94_RELEASE = ROOT / "releases/2026-07-21-open-seed-v94"
V94_MANIFEST = V94_RELEASE / "manifest.json"
V94_ENTITIES = V94_RELEASE / "entities.csv"
V94_SOURCE_INPUTS = V94_RELEASE / "source_inputs.json"
V94_PINS: Mapping[Path, tuple[int, str]] = {
    V94_DEFINITION: (
        113_819,
        "c65f61b3708b4cdc1fb755eaf8d0edffab545526f206689e66056220b27cc0ff",
    ),
    V94_MANIFEST: (
        17_866,
        "8315811764024f026eb2fc69f9ff06b738c554dcd9717aed6ba9254f6cf3fc65",
    ),
    V94_ENTITIES: (
        1_044_783,
        "87d2320671a5773c8d7619be972b5434f82adb12a28f3afe383e2e1bd63605f4",
    ),
    V94_SOURCE_INPUTS: (
        423_750,
        "9001ec0544a5f7d86d62472fcd71c5cff584587599058c07bfa4111cf6a8ea33",
    ),
}
V94_TREE_SHA256 = (
    "e947ec413e1c43ea053f7766928ccab373f7e1f058be42fc5c433ea7dda49766"
)
V94_INPUT_COUNT = 498
V94_ENTITY_COUNT = 1_011

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
_identity = prior._identity
_has_identity = prior._has_identity


CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "centra_datacenters.body": (
        2_071_141,
        "b4b8b6dffa1666ac9a921296b5dbf9134fc059fb161e51ca88f86f2153cd306e",
    ),
    "centra_datacenters.headers": (
        1_607,
        "15d8fa8cd55bcad7bf2221e9c9170751cc5c4b06b8b3f355cd5c52daccba36ff",
    ),
    "centra_groundbreaking.body": (
        1_481_582,
        "c31389e7db45b2b96fb3aded23129521f77dbcf1c05d5841bf01ebe7c4833605",
    ),
    "centra_groundbreaking.headers": (
        1_551,
        "3e2ac166bc95dc72422fc6b62178ceb431762d8dc62091f3e4be35462e2068fb",
    ),
    "centra_topout.body": (
        169_234,
        "f110986fdd271c6845c669a399a7741b9f3b115a23b166dd4179501093d0673b",
    ),
    "centra_topout.headers": (
        5_348,
        "4713bb3c46bd4a09bbbec675bacf75f565aa415d6fe3fce617edb2c7fc932f84",
    ),
    "cim_financing.body": (
        115_262,
        "08329057f5c0442a7319fcf3cbce0141fd727d9d06654f3b7d8997da68317af2",
    ),
    "cim_financing.headers": (
        1_342,
        "51fcd6377b3bfa1813c06204628ca6729b01c1602ddab4eae4e875fc033ed552",
    ),
    "novva_financing.body": (
        218_203,
        "7a046396096ceb9ee88dbab7fa2413f4a38ee85615321ae0b304358f755f9ee9",
    ),
    "novva_financing.headers": (
        546,
        "bfbaff06943ac0741eb554425e40b954b850a0f1a7d188573a491af6dde7ee24",
    ),
    "novva_media.body": (
        264_389,
        "e78f63636b35f7e30f33a9de79d4eb00db601ebf0d09c122c583cb352f90ab69",
    ),
    "novva_media.headers": (
        544,
        "33d862a22244166e8e903a9297c495b4cd80fd44833e4699fd64ee5b67aa5bd6",
    ),
    "novva_utah.body": (
        385_782,
        "43722583ffcadcac6db5ed071a2fab3f797f68f2c35663bb363b4e42d92cce6d",
    ),
    "novva_utah.headers": (
        544,
        "57eb0662634828ca3fb40ba603ce19ebf4235d9ff6261fb216520890ecb0d7f1",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    requested_url: str
    effective_url: str
    retrieved_at: str
    published_at: str | None
    publisher: str
    use: str
    content_type: str


CAPTURES = (
    Capture(
        "centra_topout",
        "centra_topout",
        "https://www.linkedin.com/posts/centradigitalinterconnect_"
        "datacenters-digitalinfrastructure-interconnection-activity-"
        "7455674234259030016-C3Y1",
        "https://www.linkedin.com/posts/centradigitalinterconnect_"
        "datacenters-digitalinfrastructure-interconnection-activity-"
        "7455674234259030016-C3Y1",
        "2026-07-22T03:56:15Z",
        "2026-04-30T17:47:37.152Z",
        "CENTRA via LinkedIn",
        "normalized_physical_status_and_operating_model",
        "text/html; charset=utf-8",
    ),
    Capture(
        "centra_datacenters",
        "centra_datacenters",
        "https://www.centradigital.com/datacenters",
        "https://www.centradigital.com/datacenters",
        "2026-07-22T03:56:16Z",
        None,
        "CENTRA",
        "normalized_identity_context_and_untyped_schedule_metadata",
        "text/html; charset=UTF-8",
    ),
    Capture(
        "centra_groundbreaking",
        "centra_groundbreaking",
        "https://www.centradigital.com/post/centra-breaks-ground-on-rno2",
        "https://www.centradigital.com/post/centra-breaks-ground-on-rno2",
        "2026-07-22T03:56:16Z",
        "2025-11-18",
        "CENTRA",
        "normalized_lineage_and_operating_model_context",
        "text/html; charset=UTF-8",
    ),
    Capture(
        "novva_financing",
        "novva_financing",
        "https://www.novva.com/media-center/cim-group-novva-data-centers-"
        "secure-2b-to-expand-sustainable-data-centers-in-the-western-u-s/",
        "https://www.novva.com/media-center/cim-group-novva-data-centers-"
        "secure-2b-to-expand-sustainable-data-centers-in-the-western-u-s/",
        "2026-07-22T03:56:16Z",
        "2025-03-05",
        "Novva Data Centers",
        "review_only_old_phase_specific_physical_observation",
        "text/html; charset=UTF-8",
    ),
    Capture(
        "cim_financing",
        "cim_financing",
        "https://www.cimgroup.com/press-releases/cim-group-and-novva-data-"
        "centers-announce-2-billion-in-new-financing-to-accelerate-growth-in-"
        "delivering-sustainable-efficient-data-centers-across-the-western-u-s",
        "https://www.cimgroup.com/press-releases/cim-group-and-novva-data-"
        "centers-announce-2-billion-in-new-financing-to-accelerate-growth-in-"
        "delivering-sustainable-efficient-data-centers-across-the-western-u-s",
        "2026-07-22T03:56:16Z",
        "2025-03-05",
        "CIM Group",
        "review_only_old_phase_specific_physical_corroboration",
        "text/html; charset=utf-8",
    ),
    Capture(
        "novva_media",
        "novva_media",
        "https://www.novva.com/media-center/",
        "https://www.novva.com/media-center/",
        "2026-07-22T03:56:17Z",
        None,
        "Novva Data Centers",
        "review_only_current_official_media_inventory",
        "text/html; charset=UTF-8",
    ),
    Capture(
        "novva_utah",
        "novva_utah",
        "https://www.novva.com/data-center-facilities/utah/",
        "https://www.novva.com/data-center-facilities/utah/",
        "2026-07-22T03:56:17Z",
        None,
        "Novva Data Centers",
        "review_only_current_campus_page_without_phase_status",
        "text/html; charset=UTF-8",
    ),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    capture_id: str
    title: str
    source_family: str
    excerpt: str
    metadata: Mapping[str, Any]


TOPOUT_EVIDENCE_KEY = "centra-rno2-topout-2026-04-30-captured-2026-07-22"
LOCATIONS_EVIDENCE_KEY = (
    "centra-rno2-current-location-page-captured-2026-07-22"
)
GROUNDBREAKING_EVIDENCE_KEY = (
    "centra-rno2-groundbreaking-2025-11-18-captured-2026-07-22"
)

EVIDENCE = (
    EvidenceSpec(
        TOPOUT_EVIDENCE_KEY,
        "centra_topout",
        "CENTRA RNO2 top-out disclosure",
        "centra_official_linkedin_company_posts",
        "CENTRA says RNO2 officially topped out and describes the milestone as structural completion while work moves toward completion.",
        {
            "linkedin_activity_id": "7455674234259030016",
            "linkedin_schema_org_date_published": "2026-04-30T17:47:37.152Z",
            "physical_status_as_reported": "officially topped out; structural completion",
            "lifecycle_mapping": (
                "Top-out and structural completion map to shell only; completion, "
                "commissioning, energization, occupancy, and operation are not inferred."
            ),
            "operating_model_scope": (
                "The company directly calls RNO2 a carrier-neutral interconnection "
                "data center. Together with its official colocation-environment and "
                "cabinets/cages/data-halls language, this supports generic colocation "
                "only; wholesale versus retail is not inferred."
            ),
            "reported_power_context_not_normalized": {
                "value": 4.4,
                "unit": "MW",
                "source_wording": "4.4 MW, AI-ready facility",
                "typing": "untyped_metadata_only",
                "exclusion": (
                    "The top-out disclosure does not call 4.4 MW critical IT load or "
                    "IT capacity. No grid, gross-facility, generation, consumption, "
                    "annual-energy, installed, energized, or current-load meaning is inferred."
                ),
            },
            "workload_guardrail": (
                "AI-ready and support for next-generation workloads describe design "
                "intent, not an installed workload, tenant, contract, or active compute."
            ),
            "status_semantics": (
                "Dated last-observed shell state on 2026-04-30; persistence after "
                "that date and current status at retrieval are not asserted."
            ),
        },
    ),
    EvidenceSpec(
        LOCATIONS_EVIDENCE_KEY,
        "centra_datacenters",
        "CENTRA data center locations",
        "centra_official_data_center_locations",
        "CENTRA lists RNO2 in Reno with 4.4 MW in Q4 2026 and offers cabinets, cages, data halls, power, and interconnection.",
        {
            "identity_scope": "RNO2, Reno, Nevada",
            "floor_area_as_reported": "230K SF",
            "reported_power_context_not_normalized": {
                "value": 4.4,
                "unit": "MW",
                "qualifier": "in Q4 '26",
                "typing": "untyped_forward_looking_metadata_only",
            },
            "schedule_guardrail": (
                "Q4 2026 is a future availability statement, not evidence of "
                "completion, commissioning, energization, occupancy, or operation."
            ),
            "address_guardrail": (
                "Only Reno, Nevada is normalized. No street address, map target, "
                "coordinate, or geometry is copied or inferred."
            ),
        },
    ),
    EvidenceSpec(
        GROUNDBREAKING_EVIDENCE_KEY,
        "centra_groundbreaking",
        "CENTRA Breaks Ground on RNO2",
        "centra_official_news",
        "CENTRA reported the RNO2 groundbreaking in Reno and described a carrier-neutral interconnection data center for colocation environments.",
        {
            "construction_lineage": "Official groundbreaking reported 2025-11-18.",
            "operating_model_language": (
                "carrier-neutral interconnection data center; modern, high-resiliency "
                "colocation environments; racks, cages, and custom suites"
            ),
            "critical_capacity_wording_as_reported": (
                "4.4 MW of scalable critical capacity"
            ),
            "capacity_exclusion": (
                "Critical capacity is not the schema's critical_it_mw metric. The "
                "source does not say critical IT load or IT capacity, so no capacity "
                "estimate is normalized."
            ),
            "energy_context_not_normalized": (
                "Green-power procurement and energy-efficient cooling are narrative "
                "design statements, not energy consumption, annual MWh, generation, "
                "grid draw, renewable share, or measured efficiency."
            ),
        },
    ),
)

CAMPUS_KEY = "curated:centra-rno2-reno-data-center"
PROJECT_KEY = f"{CAMPUS_KEY}:current-build"


def _capture_metadata(capture: Capture) -> dict[str, Any]:
    body = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
    headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": (
            "credential_free_curl_location_compressed_desktop_user_agent"
        ),
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": capture.content_type,
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte content-decoded public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_bytes": headers[0],
        "capture_headers_sha256": headers[1],
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bodies, headers, scripts, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "map widget, analyst geolocation, or inferred address contributes."
        ),
    }


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    return {
        "key": spec.key,
        "kind": "company_disclosure",
        "title": spec.title,
        "source_url": capture.effective_url,
        "publisher": capture.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": capture.publisher,
        "excerpt": spec.excerpt,
        "content_hash": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
        "metadata": {**_capture_metadata(capture), **spec.metadata},
    }


def _entity(*, project: bool) -> dict[str, Any]:
    return {
        "stable_key": PROJECT_KEY if project else CAMPUS_KEY,
        "name": (
            "CENTRA RNO2 Current Build" if project else "CENTRA RNO2 Reno Data Center"
        ),
        "country": "United States",
        "address": "Reno, Nevada, United States",
        "roles": {"developer": ["CENTRA"]},
        "coordinates": None,
        "geometry": None,
        "evidence_key": TOPOUT_EVIDENCE_KEY,
        "as_of_date": "2026-04-30",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {
        SOURCE_FILENAME: {
            "schema_version": "1.1",
            "evidence": [_evidence(spec) for spec in EVIDENCE],
            "campus": _entity(project=False),
            "project": _entity(project=True),
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": TOPOUT_EVIDENCE_KEY,
                    "as_of_date": "2026-04-30",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
            "operating_models": [
                {
                    "entity": "project",
                    "value": "colocation",
                    "evidence_key": TOPOUT_EVIDENCE_KEY,
                    "as_of_date": "2026-04-30",
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ],
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
            "evidence_records": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_official_shell_current_build",
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
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    return stable, evidence


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for target, pin in V94_PINS.items():
        _pin(target, pin)
    if tree_digest(V94_RELEASE) != V94_TREE_SHA256:
        raise RuntimeError("v94 release tree differs")
    definition = json.loads(V94_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V94_INPUT_COUNT:
        raise RuntimeError("v94 selected input inventory differs")

    planned_stable, planned_evidence = _planned_keys(documents)
    with V94_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    if len(base_rows) != V94_ENTITY_COUNT:
        raise RuntimeError("v94 entity count differs")
    base_stable = {row["stable_key"] for row in base_rows}
    stable_collisions = sorted(planned_stable & base_stable)
    if stable_collisions:
        raise RuntimeError(f"planned CENTRA stable keys collide: {stable_collisions!r}")
    identity_hits = [
        {
            "stable_key": row["stable_key"],
            "name": row.get("name"),
            "address": row.get("address"),
        }
        for row in base_rows
        if "rno2" in (row.get("name") or "").lower()
        or "centra rno2" in (row.get("address") or "").lower()
    ]
    if identity_hits:
        raise RuntimeError(f"v94 contains an exact RNO2 identity witness: {identity_hits!r}")
    source_inputs = json.loads(V94_SOURCE_INPUTS.read_text(encoding="utf-8")).get(
        "sources"
    )
    base_evidence = {
        key
        for row in source_inputs or []
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    evidence_collisions = sorted(planned_evidence & base_evidence)
    if evidence_collisions:
        raise RuntimeError(
            f"planned CENTRA evidence keys collide: {evidence_collisions!r}"
        )
    return {
        "v94_selected_input_count": len(selected),
        "v94_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v94_stable_key_collisions": [],
        "exact_v94_evidence_key_collisions": [],
        "exact_v94_rno2_identity_matches": [],
        "exact_existing_identity_keys_reused": [],
        "identity_resolution": (
            "New curated campus and project keys are used. No existing identity, "
            "address, coordinate, geometry, capacity, or status is inherited."
        ),
    }


def _review_source(capture_id: str) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[capture_id]
    return {
        "capture_id": capture.capture_id,
        "url": capture.effective_url,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "body_bytes": CAPTURE_FILE_PINS[f"{capture.stem}.body"][0],
        "body_sha256": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    novva_common = {
        "decision": "review_only_no_post_2025_phase_specific_physical_observation",
        "source_paths": [],
        "stable_key_created": False,
        "lifecycle_claim_created": False,
        "capacity_claim_created": False,
        "normalized_entity": None,
        "normalized_lifecycle": None,
        "normalized_capacity": None,
        "last_phase_specific_physical_observation": "2025-03-05",
        "later_official_physical_observation_found": False,
        "official_sources_checked": [
            _review_source("novva_financing"),
            _review_source("cim_financing"),
            _review_source("novva_media"),
            _review_source("novva_utah"),
        ],
        "cms_update_guardrail": (
            "The Novva financing page displays a July 7, 2026 CMS-updated date, "
            "but its phase-specific text still reports only a December 2023 start "
            "for phase 2 and January 2024 start for phase 3, in a release published "
            "March 5, 2025. A CMS edit date is not a later physical observation."
        ),
        "current_location_page_guardrail": (
            "The current Utah page markets a four-phase planned development and "
            "campus-wide specifications but gives no dated phase-2 or phase-3 "
            "physical condition, completion, commissioning, or operation statement."
        ),
        "status_semantics": (
            "Old construction starts do not establish current construction in July "
            "2026. Current phase status remains unknown pending a later official "
            "physical observation."
        ),
    }
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 3,
        "seed_eligible_candidate_count": 1,
        "seed_eligible_source_record_count": 1,
        "review_only_count": 2,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "centra-rno2-reno-current-build",
                "decision": "seed_eligible_official_shell_current_build",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "existing_atlas_identity_link": None,
                "lifecycle": {
                    "status": "shell",
                    "as_of_date": "2026-04-30",
                    "method": "authoritative_physical_status_update",
                    "current_status_persisted": False,
                },
                "operating_model": {
                    "value": "colocation",
                    "scope": "generic only; no wholesale or retail subtype",
                    "evidence_key": TOPOUT_EVIDENCE_KEY,
                },
                "reported_power_context_not_normalized": [
                    {
                        "value": 4.4,
                        "unit": "MW",
                        "source_wording": "4.4 MW, AI-ready facility",
                        "typing": "untyped_metadata_only",
                    },
                    {
                        "value": 4.4,
                        "unit": "MW",
                        "source_wording": "4.4 MW of scalable critical capacity",
                        "typing": "untyped_metadata_only_not_critical_it",
                    },
                ],
                "capacity_claim_created": False,
                "workload_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
                "address_scope": "Reno, Nevada, United States only",
            },
            {
                "candidate_id": "novva-west-jordan-phase-2",
                "reported_old_start": "December 2023",
                "reported_critical_it_mw_not_normalized": 72,
                **novva_common,
            },
            {
                "candidate_id": "novva-west-jordan-phase-3",
                "reported_old_start": "January 2024",
                "reported_critical_it_mw_not_normalized": 72,
                **novva_common,
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
                "publisher": capture.publisher,
                "requested_url": capture.requested_url,
                "effective_url": capture.effective_url,
                "retrieved_at": capture.retrieved_at,
                "published_at": capture.published_at,
                "http_status": 200,
                "content_type": capture.content_type,
                "claim_use": capture.use,
                "body": {
                    "path": f"{capture.stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": f"{capture.stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{capture.stem}.headers"][1],
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
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    assessment = _candidate_assessment(recorded_at)
    totals = {
        "candidate_assessments": 3,
        "source_records": 1,
        "seed_eligible_candidates": 1,
        "seed_eligible_source_records": 1,
        "review_only_candidates": 2,
        "distinct_campuses_in_source_records": 1,
        "projects": 1,
        "distinct_entities_in_source_records": 2,
        "new_entities_against_v94": 2,
        "source_document_entity_snapshots": 2,
        "unique_evidence_records": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 1,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "coordinate_observations": 0,
        "geometry_observations": 0,
        "satellite_observations": 0,
    }
    readme = f"""# CENTRA RNO2 official current-build gap

This immutable artifact accepts one bounded official source record for CENTRA RNO2 in Reno. CENTRA's official company post was published at 2026-04-30T17:47:37.152Z and says RNO2 officially topped out, explicitly describing structural completion and continued work toward completion. That evidence maps to `shell` only. It does not establish completion, commissioning, energization, occupancy, or operation, and status after 2026-04-30 remains unknown.

Generic `colocation` is supported by the official carrier-neutral interconnection, colocation-environment, cabinets, cages, and data-halls language. Wholesale versus retail is not inferred. The 4.4 MW figure remains untyped metadata: one source says only "4.4 MW, AI-ready facility" and another says "4.4 MW of scalable critical capacity," neither of which explicitly identifies critical IT load or IT capacity. No normalized capacity, energy consumption, annual energy, generation, grid demand, PUE, workload, tenant, coordinate, geometry, map-derived address, satellite, aerial, or computer-vision claim is emitted.

Novva West Jordan phases 2 and 3 remain review-only. The official March 5, 2025 release reports December 2023 and January 2024 starts, respectively. Although Novva's page displays a July 7, 2026 CMS-updated date, the phase-specific physical text is still the old start disclosure. The current Utah page describes a planned four-phase development but gives no dated phase-specific physical condition. Old starts and a CMS timestamp do not establish a July 2026 current-build state.

All source and artifact bytes were privately staged before {recorded_at}, frozen only after that barrier, and promoted without replacement. Every frozen source, artifact member, and artifact root has a ctime at or after the declared instant. Raw all-rights-reserved captures are represented only by exact pins; the intact {CAPTURE_FILE_COUNT}-file directory is moved to recoverable Trash after successful live validation. This artifact performs no open-seed, release, federation, identity, timeline, master, map, or coverage integration.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v94_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v94.json",
                "bytes": V94_PINS[V94_DEFINITION][0],
                "sha256": V94_PINS[V94_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v94/manifest.json",
                "bytes": V94_PINS[V94_MANIFEST][0],
                "sha256": V94_PINS[V94_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v94/entities.csv",
                "bytes": V94_PINS[V94_ENTITIES][0],
                "sha256": V94_PINS[V94_ENTITIES][1],
            },
            "release_source_inputs": {
                "path": "releases/2026-07-21-open-seed-v94/source_inputs.json",
                "bytes": V94_PINS[V94_SOURCE_INPUTS][0],
                "sha256": V94_PINS[V94_SOURCE_INPUTS][1],
            },
            "release_tree_sha256": V94_TREE_SHA256,
            **collision,
        },
        "review_negative_finding": {
            "candidate_ids": [
                "novva-west-jordan-phase-2",
                "novva-west-jordan-phase-3",
            ],
            "decision": (
                "No current seed: no later official phase-specific physical "
                "observation found after the March 5, 2025 release."
            ),
            "assessment_rows": assessment["candidates"][1:],
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v94_mutated": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
        },
        "publication_contract": {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "freeze_performed_after_recorded_at_barrier": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "all_source_and_artifact_member_ctimes_at_or_after_recorded_at": True,
            "raw_capture_moved_after_successful_live_validation": True,
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
            "Captured official response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_and_factual_extract_only": True,
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
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(
    paths: Mapping[str, Path], *, require_frozen: bool = True
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("CENTRA source path inventory differs")
    wanted_mode = 0o444 if require_frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != wanted_mode
        ):
            raise RuntimeError(f"CENTRA source differs: {name}")
    document = expected[SOURCE_FILENAME]
    if any(
        document[entity][field] is not None
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise RuntimeError("CENTRA source invented coordinate or geometry")
    if document["capacities"] or document["workloads"]:
        raise RuntimeError("CENTRA source normalized excluded capacity or workload")
    if document["lifecycle"] != [
        {
            "entity": "project",
            "value": "shell",
            "evidence_key": TOPOUT_EVIDENCE_KEY,
            "as_of_date": "2026-04-30",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]:
        raise RuntimeError("CENTRA lifecycle contract differs")
    if document["operating_models"] != [
        {
            "entity": "project",
            "value": "colocation",
            "evidence_key": TOPOUT_EVIDENCE_KEY,
            "as_of_date": "2026-04-30",
            "method": "company_disclosure",
            "confidence": 0.99,
        }
    ]:
        raise RuntimeError("CENTRA operating-model contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
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
        raise RuntimeError(f"CENTRA source collision detected: {collisions!r}")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("CENTRA capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise RuntimeError("CENTRA capture closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise RuntimeError("CENTRA capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="centra-rno2-import-", dir="/private/tmp"
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
            "evidence": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"CENTRA offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise RuntimeError(f"CENTRA final member ctime predates recorded_at: {path}")


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
    _collision_witness(expected_source_documents())
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("CENTRA artifact must be an ordinary directory")
    wanted_root = 0o555 if require_frozen else 0o700
    if stat.S_IMODE(path.stat().st_mode) != wanted_root:
        raise RuntimeError("CENTRA artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise RuntimeError("CENTRA artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 1
        or manifest.get("candidate_assessments") != 3
        or manifest.get("review_only_candidates") != 2
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise RuntimeError("CENTRA manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise RuntimeError(f"CENTRA manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("CENTRA manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"CENTRA artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != records:
        raise RuntimeError("CENTRA artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    if any(row["source_paths"] for row in assessment["candidates"][1:]):
        raise RuntimeError("Novva review-only source path boundary differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise RuntimeError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise RuntimeError("CENTRA recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("CENTRA capture post-dates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("CENTRA offline replay differs")
    if require_frozen:
        _assert_chronology(
            [path, *entries.values(), *paths.values()], manifest["recorded_at"]
        )
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = stage / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)
        _fsync_regular(path)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
        _fsync_regular(path)
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
        "candidate_assessments": 3,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "review_only_candidates": 2,
        "successful_http_200_body_captures": 7,
        "raw_capture_redistributed": False,
        "raw_capture_moved_after_successful_live_validation": True,
        "all_member_and_root_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o600)
    _fsync_regular(sidecar)
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise RuntimeError("active CENTRA publication lock exists") from error
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
                raise RuntimeError("refusing substituted CENTRA lock cleanup")
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
        raise RuntimeError("CENTRA final-path collision")
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    _validate_source_collisions()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".centra-rno2-sources.", dir=SOURCES_ROOT)
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
        raise RuntimeError("late CENTRA final-path collision")
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            identity = _identity(staged, directory=False)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=False):
                raise RuntimeError(f"promoted CENTRA source identity differs: {final}")
            promoted.append((final, staged, identity, False))
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise RuntimeError("promoted CENTRA artifact identity differs")
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise RuntimeError(
                        f"refusing identity-mismatched CENTRA rollback: {final}"
                    )
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"CENTRA rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both CENTRA raw origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "capture_trash": str(CAPTURE_TRASH),
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "source_records": 1,
        "unique_entities": 2,
        "evidence_records": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 1,
        "capacity_estimates": 0,
        "review_only_candidates": 2,
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
        raise RuntimeError("partial CENTRA final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise RuntimeError("CENTRA recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("CENTRA source stage not empty")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
