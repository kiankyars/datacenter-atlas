"""Build and validate the public Verified Construction Core preview.

The preview is intentionally separate from the historical publication-carrier
chain.  It selects only manually reviewed project/site pairs from open-seed
v97 and refuses to describe the small cohort as the final 100-site product.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

from .repository import stable_id as atlas_stable_id


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELEASE_ID = "2026-07-22-open-seed-v97"
SOURCE_RELEASE = ROOT / "releases" / SOURCE_RELEASE_ID
GEOMETRY_RELEASES = {
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
}
LEGACY_PREVIEW_V01_DIR = (
    ROOT / "verified_construction_core" / "2026-08-19-preview-v0.1"
)
LEGACY_PREVIEW_V01_MANIFEST_SHA256 = (
    "50c37999d6e14156910cdd0c66fb973c554414dcc29917226746afc15dc673b7"
)
LEGACY_PREVIEW_V02_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.2"
)
LEGACY_PREVIEW_V02_MANIFEST_SHA256 = (
    "e69b6d0570710dd3ef4802601652852d24047fb19f1e9bf6ebd5dad9ac29ae8d"
)
LEGACY_PREVIEW_V03_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.3"
)
LEGACY_PREVIEW_V03_MANIFEST_SHA256 = (
    "8a17e9e4d126bc210a34c2b9a0bd2fd1737402ca9d1069dd5411067831e6d1ac"
)
LEGACY_PREVIEW_V03_COMMIT = "f2964d751c25f28cea04c56d8feefb1a029fd371"
LEGACY_PREVIEW_V04_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.4"
)
LEGACY_PREVIEW_V04_MANIFEST_SHA256 = (
    "26bdf0930f21acd8db8b52d6f58803206d3ef8f0cde83d5d2ae80abc113895a7"
)
LEGACY_PREVIEW_V05_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.5"
)
LEGACY_PREVIEW_V05_MANIFEST_SHA256 = (
    "be699da97cc8386c30ff2414fcaa8264870e663197a039a1371a3bcc20fbc23c"
)
LEGACY_PREVIEW_V05_COMMIT = "30d4259bca2557da81fb85b805eff0ddd35868a4"
LEGACY_PREVIEW_V06_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.6"
)
LEGACY_PREVIEW_V06_MANIFEST_SHA256 = (
    "05070fab668b1ddd575745cefe3dc36600cd27b48f90702939229c1372674bd5"
)
LEGACY_PREVIEW_V06_COMMIT = "ec9cfe665e79cf76ea6b209a5a6e33c8fd1553c6"
CURRENT_V07_PREVIEW_ID = "2026-08-20-preview-v0.7"
CURRENT_V07_PREVIEW_DIR = ROOT / "verified_construction_core" / CURRENT_V07_PREVIEW_ID
CURRENT_V07_REVIEW_DATE = date(2026, 8, 20)
CURRENT_V07_DEFINITION_PATHS = (
    (
        "review_definition_sha256",
        ROOT / "definitions" / "verified-construction-core-v0.7-reviewed-sites.json",
    ),
    (
        "imagery_review_definition_sha256",
        ROOT / "definitions" / "verified-construction-core-v0.7-imagery-reviews.json",
    ),
    (
        "provenance_definition_sha256",
        ROOT / "definitions" / "verified-construction-core-v0.7-provenance.json",
    ),
    (
        "overlay_definition_sha256",
        ROOT / "definitions" / "verified-construction-core-reviewed-overlays-v5.json",
    ),
)
V07_REVIEW_DEFINITION_SHA256 = (
    "e6fd80ddb57b49f40cc939a56bc4764e265b2580dc95cba22a4a07cfbd7cb096"
)
V07_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "93afb53f21a7931202237d0688237a74fd8b7aa01646700785c1f368d69f4e42"
)
V07_PROVENANCE_DEFINITION_SHA256 = (
    "ef4d730fe87bcf2f2e6a99831f2a045023d4f7024d273fc0c82ba52b52648d6f"
)
V07_OVERLAY_DEFINITION_SHA256 = (
    "aa857c31d1b747749fec75b94afc16c48f8a0b28bc025d66f4a58b830cdfff3d"
)
V07_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.7-reviewed-sites.json"
)
V07_IMAGERY_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.7-imagery-reviews.json"
)
V07_PROVENANCE_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.7-provenance.json"
)
V07_OVERLAY_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-reviewed-overlays-v5.json"
)
REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.6-reviewed-sites.json"
)
IMAGERY_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.6-imagery-reviews.json"
)
PROVENANCE_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.6-provenance.json"
)
OVERLAY_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-reviewed-overlays-v4.json"
)
V03_REVIEW_DEFINITION_SHA256 = (
    "ee56ff41dc6ea59df67de6ab462540c8a3fe3747ca3e1504cb9228481c25c06b"
)
V03_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "eec896bd0c1b26fe95110ab3023e3d713c9ff4c6965412683b4d5e945ad09d7a"
)
V03_PROVENANCE_DEFINITION_SHA256 = (
    "50c3e82d2a9ae6a759b36344e34556ed527027b5c6397153d051adf61dce6561"
)
V03_OVERLAY_DEFINITION_SHA256 = (
    "57540f73c5cac475bd8e9e64fc5d8eb2188158ef977b477a0c0e8d7158caf1b7"
)
V04_REVIEW_DEFINITION_SHA256 = (
    "cc71ed6bc107fa585caf3726f7625fd0fdd982c5699a5e19218bbeb1dec7c97c"
)
V04_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "897a9cbe1f85dea871a3c267069390d5db7ab1206691068769a14fb0b7882798"
)
V04_PROVENANCE_DEFINITION_SHA256 = (
    "9d51d2e998c6d902a6410dfb3a2ce8dde8ee4b722d483bec65de4fda1d6e636e"
)
V04_OVERLAY_DEFINITION_SHA256 = (
    "65b01f335e60c1f7a886100089bd3a4fe4da79c074233a49bb60b9b65ab8129f"
)
V05_REVIEW_DEFINITION_SHA256 = (
    "ec1c7dfc9f9516567ca2c58e29b631cf11df4bba4212df3fc875d0a4b5236775"
)
V05_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "90969eb2e15210b7a398ff2cc1a2d12ba1b2aa5213e5f4cfe31021ec71c2b083"
)
V05_PROVENANCE_DEFINITION_SHA256 = (
    "bbd0e4665605e7af6389d6730211d096c737ee038886cfdacf848f87a2ee16af"
)
V05_OVERLAY_DEFINITION_SHA256 = (
    "d71ce264327ccf523cb7f000d559c0a4953524d0224dbdcc7e91e36d8e4b98c5"
)
V06_REVIEW_DEFINITION_SHA256 = (
    "494b7d92638678aa991e15c81e52f9f5e5955ffab0e84e20f1df83dd82ecc06c"
)
V06_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "0fe6726cbca33ec95e90bc669d5f25383ab14a84fb9c2d668b77ff643861cb00"
)
V06_PROVENANCE_DEFINITION_SHA256 = (
    "5f504762991ea5c20854eab17a017cf97587bd47b6b11974d7681b37cd869ee4"
)
V06_OVERLAY_DEFINITION_SHA256 = (
    "f495067d8cef674b88d82b8b2554ccd7a043b68b7df527f8fd6d8ef49beda5a8"
)
PREVIEW_ID = "2026-08-20-preview-v0.6"
PREVIEW_DIR = ROOT / "verified_construction_core" / PREVIEW_ID
REVIEW_DATE = date(2026, 8, 20)
MAX_STATUS_AGE_DAYS = 90
CURRENT_DELTA_COUNTRY_ISO_A2 = {
    "Hong Kong": "HK",
    "India": "IN",
    "Indonesia": "ID",
    "Norway": "NO",
}

PHYSICAL_STATUSES = {
    "civil_works",
    "commissioning",
    "expansion",
    "foundations",
    "mep_electrical",
    "shell",
    "site_preparation",
    "under_construction",
}
AUTHORITATIVE_STATUS_METHODS = {
    "authoritative_construction_start",
    "authoritative_physical_status_update",
    "government_record",
    "physical_observation",
}
POWER_METRICS = {
    "grid_connection_mw",
    "gross_facility_mw",
    "critical_it_mw",
    "generation_nameplate_mw",
}
ENERGY_METRICS = {"annual_energy_mwh"}
EFFICIENCY_METRICS = {"pue"}
METRIC_UNITS = {
    "grid_connection_mw": "MW",
    "gross_facility_mw": "MW",
    "critical_it_mw": "MW",
    "generation_nameplate_mw": "MW",
    "annual_energy_mwh": "MWh/year",
    "pue": "ratio",
}
ESTIMATE_METHODS = {
    "reported",
    "calculated",
    "permit_inference",
    "equipment_inference",
    "imagery_inference",
    "modeled",
    "unknown",
}
CAPACITY_STAGES = {
    "requested",
    "contracted",
    "design",
    "planned",
    "installed",
    "energized",
    "operational",
    "measured",
    "forecast",
    "unknown",
}
FINAL_REQUIREMENTS = {
    "site_count": 100,
    "country_count": 40,
    "non_us_site_count": 50,
    "maximum_single_country_share": 0.40,
    "blind_review_sample_size": 20,
    "blind_review_minimum_agreements": 19,
}
PREVIEW_SOURCE_PIPELINE_ROW_COUNT = 531
PREVIEW_SELECTION_FIRST_FAILURE_COUNTS = {
    "entity_kind_not_project": 49,
    "not_in_reviewed_site_geometry_allowlist": 114,
    "selected": 29,
    "status_not_physical": 12,
    "status_outside_90_day_window": 327,
}
CLEAN_CLONE_REBUILD_REASON = (
    "v97 source payloads remain local-only; the preview is clean-clone validatable "
    "but not clean-clone rebuildable"
)
SEMANTIC_GUARDRAILS = {
    "legacy_construction_verified_changed": False,
    "current_status_inferred": False,
    "imagery_creates_lifecycle_claim": False,
    "campus_geometry_misrepresented_as_project_footprint": False,
    "locality_centroids_accepted": False,
    "model_only_status_accepted": False,
    "unadjudicated_imagery_conflict_resolved": False,
}

PROJECT_FIELDS = (
    "project_id",
    "project_stable_key",
    "site_id",
    "physical_site_stable_key",
    "name",
    "country",
    "country_iso_a2",
    "latitude",
    "longitude",
    "geometry_json",
    "geometry_type",
    "geometry_source_entity_kind",
    "geometry_derivation",
    "geometry_method",
    "geometry_scope_class",
    "geometry_authority_class",
    "geometry_use_scope",
    "geometry_precision_scope",
    "horizontal_uncertainty_metres",
    "horizontal_uncertainty_unknown_reason",
    "geometry_evidence_id",
    "last_observed_physical_status",
    "status_as_of",
    "status_age_days_at_review",
    "status_method",
    "status_evidence_id",
    "verification_posture",
    "independent_imagery_verification",
    "imagery_review_outcome",
    "development_type",
    "development_type_unknown_reason",
    "operating_model",
    "operating_model_unknown_reason",
    "operating_model_evidence_id",
    "workloads_json",
    "workload_unknown_reason",
    "role_claims_json",
    "power_observations_json",
    "power_unknown_reason",
    "annual_energy_observations_json",
    "annual_energy_unknown_reason",
    "efficiency_observations_json",
    "efficiency_unknown_reason",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "status_source_url",
    "geometry_source_url",
)

SITE_FIELDS = (
    "site_id",
    "physical_site_stable_key",
    "name",
    "country",
    "country_iso_a2",
    "latitude",
    "longitude",
    "geometry_json",
    "geometry_type",
    "geometry_source_entity_kinds_json",
    "geometry_derivations_json",
    "geometry_methods_json",
    "geometry_scope_classes_json",
    "geometry_authority_classes_json",
    "geometry_use_scopes_json",
    "geometry_precision_scopes_json",
    "horizontal_uncertainty_metres",
    "horizontal_uncertainty_unknown_reason",
    "geometry_evidence_ids_json",
    "project_count",
    "project_ids_json",
    "project_stable_keys_json",
    "statuses_json",
    "oldest_status_as_of",
    "newest_status_as_of",
    "verification_posture",
    "independent_imagery_verification",
    "imagery_review_outcomes_json",
)

LEGACY_PROJECT_FIELDS_V03 = tuple(
    field
    for field in PROJECT_FIELDS
    if field not in {"geometry_authority_class", "geometry_use_scope"}
)
LEGACY_SITE_FIELDS_V03 = tuple(
    field
    for field in SITE_FIELDS
    if field
    not in {"geometry_authority_classes_json", "geometry_use_scopes_json"}
)

EVIDENCE_FIELDS = (
    "evidence_id",
    "roles_json",
    "project_ids_json",
    "kind",
    "title",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)

GLOBAL_GEOMETRY_ENTITY_FIELDS = (
    "entity_id",
    "entity_kind",
    "stable_key",
    "name",
    "latitude",
    "longitude",
    "country",
    "country_iso_a2",
    "country_iso_a3",
    "country_assignment_status",
    "country_assignment_method",
    "country_assignment_confidence",
    "country_assignment_evidence_id",
    "country_boundary_feature_id",
    "source_country_tag",
    "source_country_method",
    "source_country_qid",
    "address",
    "owner",
    "operator",
    "users",
    "status",
    "status_as_of",
    "status_confidence",
    "status_method",
    "status_evidence_id",
    "operating_model",
    "operating_model_confidence",
    "operating_model_evidence_id",
    "workloads_json",
    "capacity_estimates_json",
    "geometry_json",
    "tags_json",
    "snapshot_as_of",
    "snapshot_confidence",
    "snapshot_evidence_id",
    "source_url",
    "source_publisher",
    "source_license",
    "source_retrieved_at",
)
GLOBAL_GEOMETRY_EVIDENCE_FIELDS = (
    "evidence_id",
    "kind",
    "title",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)
SOURCE_ENTITY_FIELDS = (
    "entity_id",
    "entity_kind",
    "stable_key",
    "name",
    "latitude",
    "longitude",
    "country",
    "country_iso_a2",
    "country_iso_a3",
    "country_assignment_status",
    "country_assignment_method",
    "country_assignment_confidence",
    "country_assignment_evidence_id",
    "country_boundary_feature_id",
    "source_country_tag",
    "source_country_method",
    "source_country_qid",
    "address",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "status",
    "status_as_of",
    "status_confidence",
    "status_method",
    "status_evidence_id",
    "operating_model",
    "operating_model_confidence",
    "operating_model_evidence_id",
    "workloads_json",
    "capacity_estimates_json",
    "geometry_json",
    "tags_json",
    "snapshot_as_of",
    "snapshot_confidence",
    "snapshot_evidence_id",
    "source_url",
    "source_publisher",
    "source_license",
    "source_retrieved_at",
)
EXACT_COMPONENT_FIELDS = (
    "component_id",
    "occurrence_id",
    "release_id",
    "entity_id",
    "entity_kind",
    "stable_key",
    "source_family",
    "source_root",
    "snapshot_evidence_id",
    "component_member_count",
    "identity_proof_parent_occurrence_id",
    "identity_proof_token",
    "typed_identity_tokens_json",
    "ambiguous_identity_tokens_json",
)
EXACT_RELATIONSHIP_FIELDS = (
    "relationship_id",
    "relationship_type",
    "subject_component_id",
    "subject_kind",
    "object_component_id",
    "object_kind",
    "decision_basis",
    "typed_identity_tokens_json",
    "source_release_ids_json",
    "raw_relationship_count",
)
QSCALE_IDENTITY_EVIDENCE = {
    "key": "qscale-contact-q01-campus-address-captured-2026-08-20",
    "kind": "company_disclosure",
    "title": "QScale contact page: Headquarters - Q01 Campus",
    "source_url": "https://www.qscale.com/company/contact",
    "publisher": "QScale",
    "source_family": "qscale_company_contact",
    "published_at": None,
    "retrieved_at": "2026-08-20T17:23:05Z",
    "license": "all-rights-reserved",
    "attribution": "QScale",
    "excerpt": (
        "QScale labels 2280 Albert-Dion St, Levis, Quebec G7A 5M9 as "
        "Headquarters - Q01 Campus."
    ),
    "content_hash": "c68dfa97bf860f780ad80e345d346591b33bc4ecde699154059c8fb1480bb9aa",
    "content_hash_scope": (
        "SHA-256 of the exact 41398-byte content-decoded credential-free public "
        "response body captured at retrieved_at."
    ),
    "captured_bytes": 41398,
    "rights_scope": (
        "Only this compact factual extraction and the response-body hash are "
        "redistributed; the HTML and publisher media are not."
    ),
    "address_extraction": {
        "site_label": "Headquarters - Q01 Campus",
        "house_number": "2280",
        "street": "Albert-Dion St",
        "locality": "Levis",
        "region": "Quebec",
        "postcode": "G7A 5M9",
    },
}
GREEN_IDENTITY_EVIDENCE = {
    "key": "green-contact-enterprise-campus-zrh1-address-captured-2026-08-20",
    "kind": "company_disclosure",
    "title": "Green enterprise contact page: Campus ZRH1",
    "source_url": "https://www.green.ch/en/contact-enterprise",
    "publisher": "Green",
    "source_family": "green_company_contact",
    "published_at": None,
    "retrieved_at": "2026-08-20T18:40:35Z",
    "license": "all-rights-reserved",
    "attribution": "Green",
    "excerpt": (
        "Green labels its Campus ZRH1 data-center site at Industriestrasse 31, "
        "5242 Lupfig, Switzerland."
    ),
    "content_hash": "19144da94289763ead81898082377a4c1e735155e706b70debc5e012e41ca043",
    "content_hash_scope": (
        "SHA-256 of the exact 215015-byte content-decoded credential-free public "
        "response body captured at retrieved_at."
    ),
    "captured_bytes": 215015,
    "rights_scope": (
        "Only this compact factual extraction and the response-body hash are "
        "redistributed; the HTML and publisher media are not."
    ),
    "address_extraction": {
        "site_label": "Campus ZRH1",
        "organization": "Green Datacenter AG",
        "house_number": "31",
        "street": "Industriestrasse",
        "postcode": "5242",
        "locality": "Lupfig",
        "country_as_published": "Schweiz",
    },
}
BRIDGE_REVIEW_SEMANTICS = {
    "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion": {
        "geometry_method": "openstreetmap_named_campus_fence_boundary",
        "geometry_scope_class": "reviewed_openstreetmap_named_campus_fence",
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "The curated source names atNorth ICE02 in Reykjanesbær and the OSM "
            "object names ICE02 Campus with operator atNorth in Iceland. This is "
            "a manual branded-campus identity review, not an automated fuzzy merge."
        ),
        "precision_scope": (
            "The frozen global-open-v3 Polygon is a reviewed named ICE02 campus "
            "fence/site locator inherited by the phase-two project through the "
            "explicit project_targets relationship. It is not an official, "
            "cadastral, or survey boundary; a complete current campus extent; a "
            "building footprint; or a Phase 2 footprint."
        ),
    },
    "curated:qscale-q01-levis-campus:building-b": {
        "geometry_method": (
            "openstreetmap_named_addressed_facility_polygon_as_campus_locator"
        ),
        "geometry_scope_class": (
            "reviewed_openstreetmap_named_addressed_qscale_facility_building_polygon"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "The v97 project explicitly targets the Q01 campus; QScale's first-party "
            "contact page names the exact OSM-tagged address as Headquarters - Q01 "
            "Campus; the OSM feature is named QScale and carries the same house "
            "number, street and postal code."
        ),
        "precision_scope": (
            "Contributor-mapped polygon for one named QScale data-centre building "
            "at Q01's exact first-party address, used only to locate the Q01 "
            "campus. It is not the Building B footprint or centroid, the Q01 "
            "campus boundary, a parcel, a construction extent, or a survey-accuracy "
            "claim."
        ),
    },
    "curated:green-campus-zrh1-lupfig:data-center-4": {
        "geometry_method": (
            "openstreetmap_exactly_addressed_data_center_building_polygon_as_campus_locator"
        ),
        "geometry_scope_class": (
            "reviewed_openstreetmap_addressed_green_data_center_building_polygon"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "The v97 DC4 project explicitly targets Campus ZRH1; Green's first-party "
            "enterprise contact page labels Campus ZRH1 at Industriestrasse 31, 5242 "
            "Lupfig; the OSM data-center building carries the same house number, "
            "street, postcode, and locality and is described as Green Datacenter "
            "Lupfig."
        ),
        "precision_scope": (
            "Contributor-mapped polygon for one data-center building at Green's exact "
            "first-party Campus ZRH1 address, used only to locate Campus ZRH1. It is "
            "not the DC4 footprint or centroid, the Campus ZRH1 boundary, a parcel, "
            "a construction extent, or a survey-accuracy claim."
        ),
    },
    "curated:related-openai-oracle-stargate-michigan-saline:current-build": {
        "geometry_method": (
            "openstreetmap_named_website_tagged_construction_site_polygon_as_campus_locator"
        ),
        "geometry_scope_class": (
            "reviewed_openstreetmap_named_website_tagged_barn_construction_site_polygon"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "The v97 project explicitly targets The Barn Stargate campus; the curated "
            "Related Digital source names The Barn in Saline Township; and the OSM "
            "feature in the same locality is named The Barn Data Center and carries "
            "the Saline Barn website. This is a manual distinctive-name, locality, "
            "and website-tag identity review, not an automated fuzzy merge."
        ),
        "precision_scope": (
            "The frozen global-open-v3 Polygon is a contributor-mapped "
            "construction-site locator for the named Barn data-center campus, "
            "inherited by the current-build project through the explicit v14 "
            "project_targets relationship. It is not an official, cadastral, or "
            "survey boundary; a verified complete 250-acre campus extent; a building "
            "or project footprint; a construction extent; or a source of lifecycle, "
            "capacity, energy, operating-status, or imagery claims."
        ),
    },
    "curated:microsoft-mount-pleasant-datacenter-campus:second-facility": {
        "geometry_method": (
            "openstreetmap_named_construction_area_polygon_as_campus_locator"
        ),
        "geometry_scope_class": (
            "reviewed_openstreetmap_named_microsoft_fairwater_phase_2_construction_area_polygon"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "Microsoft's first-party source places the ongoing second facility "
            "immediately adjacent to its first Mount Pleasant facility. The OSM "
            "object is named Microsoft Fairwater AI Phase 2, is tagged as data-centre "
            "construction, and lies in the same Mount Pleasant Fairwater development. "
            "This supports a manual branded-campus association only; the OSM Phase 2 "
            "label is not treated as proof that the polygon is the official "
            "second-facility footprint or that the two naming systems are "
            "phase-equivalent."
        ),
        "precision_scope": (
            "Contributor-mapped polygon for a named Microsoft Fairwater Phase 2 "
            "construction area, used only to locate the Mount Pleasant datacenter "
            "campus. It is not an official campus boundary, the complete campus "
            "extent, a parcel, a building footprint, the official second-facility "
            "footprint, a construction-progress extent, or a survey-accuracy claim."
        ),
    },
    "curated:amazon-salem-township-innovation-campus:active-buildout": {
        "geometry_method": (
            "openstreetmap_named_addressed_aws_building_polygon_as_campus_locator"
        ),
        "geometry_scope_class": (
            "reviewed_openstreetmap_named_addressed_aws_data_centre_building_polygon"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "OpenStreetMap does not state horizontal positional accuracy; "
            "community-mapped geometry is not a cadastral or survey product."
        ),
        "identity_basis": (
            "Amazon's first-party project page identifies an AWS Salem Township "
            "innovation campus with an active buildout and an already operating "
            "campus at the same location. The OSM feature is a named Amazon AWS "
            "data-centre building operated by Amazon Web Services at 1125 Electron "
            "Avenue, Berwick, within the official source's approximate Salem Township "
            "campus locality. This is a manual operator-and-proximity campus "
            "association only; it does not identify the mapped building as part of "
            "the active buildout."
        ),
        "precision_scope": (
            "Contributor-mapped polygon for one named and addressed Amazon AWS "
            "data-centre building, used only to locate the Salem Township innovation "
            "campus. It is not an official campus boundary, the complete campus "
            "extent, a parcel, the active-buildout footprint or centroid, a "
            "construction extent, a current-building count, or a survey-accuracy "
            "claim."
        ),
    },
}
BRIDGE_IMAGERY_OUTCOMES = {
    "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion": (
        "not_reviewed_for_core_preview"
    ),
    "curated:qscale-q01-levis-campus:building-b": "not_reviewed_for_core_preview",
    "curated:green-campus-zrh1-lupfig:data-center-4": (
        "not_reviewed_for_core_preview"
    ),
    "curated:related-openai-oracle-stargate-michigan-saline:current-build": (
        "tracked_identity_bound_visible_change_followup_only_no_construction_claim"
    ),
    "curated:microsoft-mount-pleasant-datacenter-campus:second-facility": (
        "tracked_identity_bound_uncertain_unsuperseded_no_construction_claim"
    ),
    "curated:amazon-salem-township-innovation-campus:active-buildout": (
        "tracked_identity_bound_uncertain_unsuperseded_no_construction_claim"
    ),
}
BRIDGE_PARENT_ROW_BINDINGS = {
    "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/1223207434",
            "line": 8529,
            "bytes": 1041,
            "sha256": "df6f4e13b51c13e5d42a01918c65893db20b6fa72086b84b72599b5b4a242694",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "6aa2c3ec-e7cc-59f0-8cd1-4b6e68a51fef",
            "line": 2862,
            "bytes": 333,
            "sha256": "4ec5acd6326b3e1534f717f4a42bbe7b41fc8fd53e5c28fb0f1a4491e851da54",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:e13f118626f658c577834962767191a8d02916b82c2b56252aba6c6dfa69ea8d",
            "line": 2201,
            "bytes": 305,
            "sha256": "4b5dd1fcc3a031ccb2a26ffb733a9371ef52a2a015c2c5bfa584295109c08bff",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion",
            "line": 634,
            "bytes": 357,
            "sha256": "c5db41475a1f19ddf83aef195464aac5e2b9cc295de340ee7dabefdd351ad8b1",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:atnorth-ice02-reykjanesbaer-campus",
            "line": 72,
            "bytes": 338,
            "sha256": "31642e06408faca71e067c65f792c9abc354e440f11c431878dcbe00570ebc1d",
        },
    },
    "curated:qscale-q01-levis-campus:building-b": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/1171439340",
            "line": 3493,
            "bytes": 942,
            "sha256": "899b6788c3b7aab63173ce3e33f6300b6f8464eadb855a69be697650011a2c78",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "8dff3085-994d-5629-b19b-7f2f88c44967",
            "line": 3833,
            "bytes": 327,
            "sha256": "fe74862dd4748f3b7445509439962abc71f804e4dd254bd172680ea137de1536",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:92fd864b2df171e3ddc065c7bf679f124c1d512b77be7174f97b4045d48f6718",
            "line": 1478,
            "bytes": 305,
            "sha256": "4ff08880b94a0cc65fa96067bfab90ed43f7c335f88902e60b719a3a06782379",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:qscale-q01-levis-campus:building-b",
            "line": 693,
            "bytes": 333,
            "sha256": "3f2443cee768e393a21cd54276fcda34a6c34c5b4dc9ee128bc40e363112fe26",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:qscale-q01-levis-campus",
            "line": 295,
            "bytes": 321,
            "sha256": "48e517fcf239ab01cfd81f7884e124095a0645cc0bbbddbde357e6d77f0496ea",
        },
    },
    "curated:green-campus-zrh1-lupfig:data-center-4": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/242248627",
            "line": 1482,
            "bytes": 1204,
            "sha256": "0089e033a00ea6034decfebd8ca8700c1c57413424b6982a4ab416922312cf31",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "a488471c-6dc2-593f-92df-db707862cbfc",
            "line": 4457,
            "bytes": 346,
            "sha256": "217bc4b5fea78cbfc2ecec2dbd5658dedbf47aa47484b58ec9c8f35704ce1a3b",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:a20d17ac9a8b24d64952d63afc20e386dfe9b087ec25685d7a38695c2e2b62a6",
            "line": 1628,
            "bytes": 305,
            "sha256": "545ac14096b373e3b47fe3f3b292ee7d82f9c7fe9ff62ad742f027f87fa583b5",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:green-campus-zrh1-lupfig:data-center-4",
            "line": 355,
            "bytes": 363,
            "sha256": "292e8e6b0c1027b8b501d720689a96cffdd77b46b558211dee9810aa3666f6ea",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:green-campus-zrh1-lupfig",
            "line": 438,
            "bytes": 348,
            "sha256": "f8788e9d68ddf1468f9c988a0b7a35ec2bed0bd87f2f8140162cfd6009989af1",
        },
    },
    "curated:related-openai-oracle-stargate-michigan-saline:current-build": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/1528327802",
            "line": 7488,
            "bytes": 1046,
            "sha256": "b1d287181b8b9c1efaa0de257c0d1ccde33e7c440e62fc5fc5192b07891d208c",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "2c1a0857-1368-581b-adfa-96bf72cc9c16",
            "line": 1243,
            "bytes": 341,
            "sha256": "c10955e4fae8fbc890eb24711dac9f54b97c3655cb2b49b0902e7b16256ad781",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:3bcf7d690a6c8e7b1dddf8e45ddb457847d5a589a3dd753a50107343b065279f",
            "line": 633,
            "bytes": 305,
            "sha256": "5b391e31ace079b39e0249fe7d5eec4c4e4af2df5022cb283d18ea5827707159",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": (
                "curated:related-openai-oracle-stargate-michigan-saline:current-build"
            ),
            "line": 509,
            "bytes": 379,
            "sha256": "0e0fa97fd888d1bd69cb57225e2db4997166d46f27211f4532d14c69f4d35b92",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:related-openai-oracle-stargate-michigan-saline",
            "line": 432,
            "bytes": 364,
            "sha256": "0d7f6ee7355975f4a7bfde019f296bf96e9e8c87e93d3a07e437fa8c4fe8d72f",
        },
    },
    "curated:microsoft-mount-pleasant-datacenter-campus:second-facility": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/1528490094",
            "line": 8156,
            "bytes": 951,
            "sha256": "4e10305dbbf68253152eedaa22f5b4bca66fc86116761d4f638371a032cb9652",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "ab38ac59-f17b-5f63-b060-392d2bebd078",
            "line": 4620,
            "bytes": 351,
            "sha256": "ae126f114e1132c8ba0a5e9e22602087d414d0718133c89eabbf9e361b8b67bb",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:5331540b613864aed98b22addbeaec3104ec83a5007a409654a27454209d4fd1",
            "line": 854,
            "bytes": 305,
            "sha256": "b6abab4859428f9a5227cc7999b1db23accd6e4e723500ae50853747451fa595",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": (
                "curated:microsoft-mount-pleasant-datacenter-campus:second-facility"
            ),
            "line": 858,
            "bytes": 365,
            "sha256": "d7ee099cc646e475fa89f534761968463dc89a0bc89ae603074991ce928077e2",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:microsoft-mount-pleasant-datacenter-campus",
            "line": 700,
            "bytes": 348,
            "sha256": "32417f946e727399cf83a3a3990130f664689da823646c359b3ba158ac740c07",
        },
    },
    "curated:amazon-salem-township-innovation-campus:active-buildout": {
        "geometry_entity": {
            "release_id": "global-open-v3",
            "member": "entities.csv",
            "stable_key": "osm:way/1334234458",
            "line": 4855,
            "bytes": 1184,
            "sha256": "a26c3cfb01c137b816d7e03c8407c87494c89de93cd4ddab492fa30e9728956c",
        },
        "geometry_evidence": {
            "release_id": "global-open-v3",
            "member": "evidence.csv",
            "evidence_id": "13a65a07-1b3a-58a3-9ca7-b98723686f7c",
            "line": 583,
            "bytes": 335,
            "sha256": "9186bac4aa9570f15608a0e0098d9c7fb898876d380fcaa6f0c06102de32943a",
        },
        "relationship": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "relationships.csv",
            "relationship_id": "relationship:3f242c8c7209bd11809916cebef051602992a3db7d4e0e6ea4e0f5f1da706b62",
            "line": 662,
            "bytes": 305,
            "sha256": "52efa9753c85574c744875734ef69bb5ea40160f5d23f64fb462303ef9220f62",
        },
        "subject_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:amazon-salem-township-innovation-campus:active-buildout",
            "line": 834,
            "bytes": 400,
            "sha256": "d8488e3961f15786331a0845a17fd1fae927d47a0c14dc95e4ccf5e0ac8d8c66",
        },
        "object_member": {
            "release_id": "2026-07-22-public-open-v14",
            "member": "component-members.csv",
            "stable_key": "curated:amazon-salem-township-innovation-campus",
            "line": 590,
            "bytes": 383,
            "sha256": "f6cd0c01918b12bb068e4a650204ae250964ab065baebcfd3bd55b2afba14084",
        },
    },
}


class VerifiedConstructionCoreError(ValueError):
    """Raised when a source, review decision, or preview violates the contract."""


@dataclass(frozen=True)
class PreviewProfile:
    preview_id: str
    preview_dir: Path
    reviewed_at: date
    base_preview_id: str
    base_preview_dir: Path
    base_manifest_sha256: str
    base_commit: str
    definition_pins: tuple[tuple[str, Path, str], ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_current_v07_profile(
    definition_sha256: Mapping[str, str],
) -> PreviewProfile:
    """Load v0.7 only after its exact definition hashes are supplied."""
    expected_fields = {field for field, _ in CURRENT_V07_DEFINITION_PATHS}
    if set(definition_sha256) != expected_fields:
        raise VerifiedConstructionCoreError(
            "current v0.7 definition pins are incomplete"
        )
    pins: list[tuple[str, Path, str]] = []
    for field, path in CURRENT_V07_DEFINITION_PATHS:
        expected_sha256 = definition_sha256[field]
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise VerifiedConstructionCoreError(
                f"current v0.7 {field} pin is invalid"
            )
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha256_file(path) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"current v0.7 {field} source hash differs"
            )
        pins.append((field, path, expected_sha256))
    return PreviewProfile(
        preview_id=CURRENT_V07_PREVIEW_ID,
        preview_dir=CURRENT_V07_PREVIEW_DIR,
        reviewed_at=CURRENT_V07_REVIEW_DATE,
        base_preview_id="2026-08-20-preview-v0.6",
        base_preview_dir=LEGACY_PREVIEW_V06_DIR,
        base_manifest_sha256=LEGACY_PREVIEW_V06_MANIFEST_SHA256,
        base_commit=LEGACY_PREVIEW_V06_COMMIT,
        definition_pins=tuple(pins),
    )


def _current_definition_pins() -> tuple[tuple[str, Path, str], ...]:
    return (
        (
            "review_definition_sha256",
            REVIEW_DEFINITION,
            V06_REVIEW_DEFINITION_SHA256,
        ),
        (
            "imagery_review_definition_sha256",
            IMAGERY_REVIEW_DEFINITION,
            V06_IMAGERY_REVIEW_DEFINITION_SHA256,
        ),
        (
            "provenance_definition_sha256",
            PROVENANCE_DEFINITION,
            V06_PROVENANCE_DEFINITION_SHA256,
        ),
        (
            "overlay_definition_sha256",
            OVERLAY_DEFINITION,
            V06_OVERLAY_DEFINITION_SHA256,
        ),
    )


def _validate_current_definition_pins() -> None:
    for field, definition, expected_sha256 in _current_definition_pins():
        if (
            definition.is_symlink()
            or not definition.is_file()
            or _sha256_file(definition) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"preview {field} source hash differs"
            )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return buffer.getvalue().encode("utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerifiedConstructionCoreError(f"cannot read canonical JSON {path}") from error


def _load_csv(
    path: Path, expected_fields: Sequence[str] | None = None
) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if expected_fields is not None and tuple(reader.fieldnames or ()) != tuple(
                expected_fields
            ):
                raise VerifiedConstructionCoreError(
                    f"CSV field order differs: {path}"
                )
            return list(reader)
    except OSError as error:
        raise VerifiedConstructionCoreError(f"cannot read CSV {path}") from error


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise VerifiedConstructionCoreError(f"cannot read JSONL {path}") from error
    if any(not isinstance(row, dict) for row in rows):
        raise VerifiedConstructionCoreError(f"JSONL row differs: {path}")
    return rows


def _calendar_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise VerifiedConstructionCoreError(f"{field} must be YYYY-MM-DD") from error
    return parsed


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _parse_json_field(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise VerifiedConstructionCoreError(f"invalid {field} JSON") from error


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _validate_typed_observation(
    observation: Any, allowed_metrics: set[str]
) -> dict[str, Any]:
    fields = {
        "as_of_date",
        "base",
        "confidence",
        "evidence_id",
        "high",
        "low",
        "method",
        "metric",
        "notes",
        "stage",
        "target_date",
        "unit",
    }
    if not isinstance(observation, dict) or set(observation) != fields:
        raise VerifiedConstructionCoreError("typed-metric observation schema differs")
    metric = observation["metric"]
    if metric not in allowed_metrics or observation["unit"] != METRIC_UNITS[metric]:
        raise VerifiedConstructionCoreError("typed-metric metric/unit differs")
    low = observation["low"]
    base = observation["base"]
    high = observation["high"]
    if not all(_finite_number(value) for value in (low, base, high)):
        raise VerifiedConstructionCoreError("typed-metric interval is not finite")
    if low < 0 or not low <= base <= high or (metric == "pue" and low <= 0):
        raise VerifiedConstructionCoreError("typed-metric interval differs")
    confidence = observation["confidence"]
    if not _finite_number(confidence) or not 0 <= confidence <= 1:
        raise VerifiedConstructionCoreError("typed-metric confidence differs")
    if observation["method"] not in ESTIMATE_METHODS:
        raise VerifiedConstructionCoreError("typed-metric method differs")
    if observation["stage"] not in CAPACITY_STAGES:
        raise VerifiedConstructionCoreError("typed-metric stage differs")
    if not isinstance(observation["evidence_id"], str) or not observation[
        "evidence_id"
    ]:
        raise VerifiedConstructionCoreError("typed-metric evidence id differs")
    if not isinstance(observation["notes"], str):
        raise VerifiedConstructionCoreError("typed-metric notes differ")
    _calendar_date(observation["as_of_date"], "typed-metric as_of_date")
    target_date = observation["target_date"]
    if target_date is not None:
        _calendar_date(target_date, "typed-metric target_date")
    return observation


SOURCE_WORKLOAD_FIELDS = {
    "as_of_date",
    "confidence",
    "evidence_id",
    "method",
    "workload",
}


def _validate_source_workload_observation(observation: Any) -> dict[str, Any]:
    if not isinstance(observation, dict) or set(observation) != SOURCE_WORKLOAD_FIELDS:
        raise VerifiedConstructionCoreError("workload observation schema differs")
    confidence = observation["confidence"]
    if not _finite_number(confidence) or not 0 <= confidence <= 1:
        raise VerifiedConstructionCoreError("workload confidence differs")
    for field in ("evidence_id", "method", "workload"):
        if not isinstance(observation[field], str) or not observation[field]:
            raise VerifiedConstructionCoreError(f"workload {field} differs")
    _calendar_date(observation["as_of_date"], "workload as_of_date")
    return observation


def _validate_workload_observation(observation: Any) -> dict[str, Any]:
    fields = SOURCE_WORKLOAD_FIELDS | {"deployment_scope"}
    if not isinstance(observation, dict) or set(observation) != fields:
        raise VerifiedConstructionCoreError("workload observation schema differs")
    _validate_source_workload_observation(
        {field: observation[field] for field in SOURCE_WORKLOAD_FIELDS}
    )
    if observation["deployment_scope"] not in {
        "intended",
        "operational",
        "unknown",
    }:
        raise VerifiedConstructionCoreError("workload deployment scope differs")
    return observation


def _validate_role_claim(claim: Any) -> dict[str, Any]:
    fields = {"evidence_id", "party", "relationship_scope", "role"}
    if not isinstance(claim, dict) or set(claim) != fields:
        raise VerifiedConstructionCoreError("role claim schema differs")
    for field in ("evidence_id", "party", "relationship_scope", "role"):
        if not isinstance(claim[field], str) or not claim[field]:
            raise VerifiedConstructionCoreError(f"role claim {field} differs")
    if claim["role"] not in ROLE_COLUMNS or claim["relationship_scope"] not in {
        "intended",
        "current",
        "unknown",
    }:
        raise VerifiedConstructionCoreError("role claim semantics differ")
    return claim


def _verify_source_release() -> dict[str, Any]:
    manifest_path = SOURCE_RELEASE / "manifest.json"
    manifest = _load_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("source release manifest has no files map")
    for name in ("entities.csv", "construction_pipeline.csv", "evidence.csv"):
        metadata = files.get(name)
        if not isinstance(metadata, dict):
            raise VerifiedConstructionCoreError(f"source manifest does not bind {name}")
        path = SOURCE_RELEASE / name
        if not path.is_file():
            raise VerifiedConstructionCoreError(f"source payload is not hydrated: {path}")
        if path.stat().st_size != metadata.get("bytes"):
            raise VerifiedConstructionCoreError(f"source payload byte count differs: {name}")
        if _sha256_file(path) != metadata.get("sha256"):
            raise VerifiedConstructionCoreError(f"source payload hash differs: {name}")
    return manifest


def _geometry_release_manifest(
    release_id: str, expected_sha256: str
) -> tuple[Path, dict[str, Any]]:
    release = GEOMETRY_RELEASES.get(release_id)
    if release is None:
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release is unknown: {release_id}"
        )
    manifest_path = release / "manifest.json"
    manifest = _load_json(manifest_path)
    if _sha256_file(manifest_path) != expected_sha256:
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release manifest differs: {release_id}"
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or not isinstance(files.get("entities.csv"), dict):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release does not bind entities.csv: {release_id}"
        )
    return release, manifest


def _geometry_release_entities(
    release_id: str,
    expected_manifest_sha256: str,
    cache: dict[tuple[str, str], dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    cache_key = (release_id, expected_manifest_sha256)
    if cache_key in cache:
        return cache[cache_key]
    release, manifest = _geometry_release_manifest(
        release_id, expected_manifest_sha256
    )
    entities_path = release / "entities.csv"
    metadata = manifest["files"]["entities.csv"]
    if not entities_path.is_file():
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry payload is not hydrated: {entities_path}"
        )
    if entities_path.stat().st_size != metadata.get("bytes") or _sha256_file(
        entities_path
    ) != metadata.get("sha256"):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry payload differs: {release_id}"
        )
    entities = _load_csv(entities_path)
    entities_by_key = {row["stable_key"]: row for row in entities}
    if len(entities_by_key) != len(entities):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry stable keys are not unique: {release_id}"
        )
    cache[cache_key] = entities_by_key
    return entities_by_key


REVIEWED_SITE_LEGACY_FIELDS = {
    "project_stable_key",
    "physical_site_stable_key",
    "source_input_path",
    "source_input_sha256",
    "geometry_evidence_key",
    "geometry_method",
    "geometry_scope_class",
    "horizontal_uncertainty_metres",
    "precision_scope",
    "decision_basis",
}
REVIEWED_SITE_FIELDS = REVIEWED_SITE_LEGACY_FIELDS | {
    "geometry_entity",
    "geometry_derivation",
}
REVIEWED_SITE_OVERLAY_FIELDS = REVIEWED_SITE_FIELDS | {"geometry_overlay_id"}


def _reviewed_acceptances_from(
    path: Path, seen: frozenset[Path] = frozenset()
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = path.resolve()
    definitions_root = (ROOT / "definitions").resolve()
    if path.parent != definitions_root or path in seen:
        raise VerifiedConstructionCoreError("reviewed-site contract path or cycle differs")
    if not path.is_file():
        raise VerifiedConstructionCoreError("reviewed-site contract is absent")
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict):
        raise VerifiedConstructionCoreError("reviewed-site contract differs")
    contract_id = reviewed.get("contract_id")
    expected_id = path.stem
    if contract_id != expected_id:
        raise VerifiedConstructionCoreError("reviewed-site contract id differs")
    reviewed_as_of = _calendar_date(
        reviewed.get("reviewed_as_of"), "reviewed-site reviewed_as_of"
    )
    if reviewed_as_of > REVIEW_DATE:
        raise VerifiedConstructionCoreError("reviewed-site contract date differs")
    acceptances = reviewed.get("acceptances")
    if not isinstance(acceptances, list) or not acceptances:
        raise VerifiedConstructionCoreError("reviewed-site acceptances are empty")

    if "base_contract" not in reviewed:
        if set(reviewed) != {
            "contract_id",
            "review_scope",
            "reviewed_as_of",
            "acceptances",
        } or contract_id != "verified-construction-core-v0.1-reviewed-sites":
            raise VerifiedConstructionCoreError("reviewed-site leaf contract differs")
        normalized: list[dict[str, Any]] = []
        for index, acceptance in enumerate(acceptances):
            if not isinstance(acceptance, dict) or set(acceptance) != REVIEWED_SITE_LEGACY_FIELDS:
                raise VerifiedConstructionCoreError(
                    f"reviewed-site leaf acceptance {index} has unexpected fields"
                )
            normalized.append(
                {
                    **acceptance,
                    "geometry_entity": "project",
                    "geometry_derivation": "direct_geometry",
                }
            )
        return normalized, normalized

    if set(reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "acceptances",
    }:
        raise VerifiedConstructionCoreError("reviewed-site successor fields differ")
    base = reviewed["base_contract"]
    if not isinstance(base, dict) or set(base) != {
        "path",
        "sha256",
        "default_geometry_entity",
        "default_geometry_derivation",
    }:
        raise VerifiedConstructionCoreError("reviewed-site base contract differs")
    if base.get("default_geometry_entity") != "project" or base.get(
        "default_geometry_derivation"
    ) != "direct_geometry":
        raise VerifiedConstructionCoreError("reviewed-site base defaults differ")
    relative = Path(base.get("path", ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise VerifiedConstructionCoreError("reviewed-site base path differs")
    base_path = (ROOT / relative).resolve()
    if (
        base_path.parent != definitions_root
        or not base_path.is_file()
        or _sha256_file(base_path) != base.get("sha256")
    ):
        raise VerifiedConstructionCoreError("reviewed-site base hash differs")
    inherited, _ = _reviewed_acceptances_from(base_path, seen | {path})
    delta: list[dict[str, Any]] = []
    for index, acceptance in enumerate(acceptances):
        if not isinstance(acceptance, dict) or frozenset(acceptance) not in {
            frozenset(REVIEWED_SITE_FIELDS),
            frozenset(REVIEWED_SITE_OVERLAY_FIELDS),
        }:
            raise VerifiedConstructionCoreError(
                f"reviewed-site delta acceptance {index} has unexpected fields"
            )
        delta.append({**acceptance, "geometry_overlay_id": acceptance.get("geometry_overlay_id")})
    flattened = [*inherited, *delta]
    keys = [row["project_stable_key"] for row in flattened]
    if len(set(keys)) != len(keys):
        raise VerifiedConstructionCoreError("reviewed-site project keys are not unique")
    for acceptance in flattened:
        acceptance.setdefault("geometry_overlay_id", None)
        if acceptance["geometry_entity"] not in {"project", "campus"}:
            raise VerifiedConstructionCoreError("reviewed-site geometry entity differs")
        if acceptance["geometry_derivation"] not in {
            "direct_geometry",
            "coordinates_to_point",
            "cross_source_overlay",
            "official_parcel_union",
        }:
            raise VerifiedConstructionCoreError("reviewed-site geometry derivation differs")
        overlay_id = acceptance.get("geometry_overlay_id")
        if overlay_id is not None:
            if (
                not isinstance(overlay_id, str)
                or not overlay_id
                or acceptance.get("geometry_evidence_key") is not None
            ):
                raise VerifiedConstructionCoreError(
                    "reviewed-site overlay geometry source differs"
                )
        elif acceptance["geometry_derivation"] in {
            "cross_source_overlay",
            "official_parcel_union",
        }:
            raise VerifiedConstructionCoreError("reviewed-site overlay geometry source differs")
    return flattened, delta


def _reviewed_acceptances() -> list[dict[str, Any]]:
    acceptances, _ = _reviewed_acceptances_from(REVIEW_DEFINITION)
    if REVIEW_DEFINITION.stem != "verified-construction-core-v0.6-reviewed-sites":
        raise VerifiedConstructionCoreError("current reviewed-site contract differs")
    reviewed = _load_json(REVIEW_DEFINITION)
    if reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("current reviewed-site date differs")
    return acceptances


ROLE_COLUMNS = {
    "owner": "owner",
    "operator": "operator",
    "user": "users",
    "tenant": "tenants",
    "customer": "customers",
}


def _repository_input(path_text: str, expected_sha256: str, field: str) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise VerifiedConstructionCoreError(f"{field} path escapes the repository")
    path = ROOT / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or _sha256_file(path) != expected_sha256
    ):
        raise VerifiedConstructionCoreError(f"{field} source hash differs")
    return path


def _evidence_from_pinned_source(
    binding: Mapping[str, Any], *, evidence_key_field: str, evidence_id_field: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _repository_input(
        str(binding["source_input_path"]),
        str(binding["source_input_sha256"]),
        "provenance",
    )
    source = _load_json(path)
    project = source.get("project")
    if not isinstance(project, dict) or project.get("stable_key") != binding.get(
        "project_stable_key"
    ):
        raise VerifiedConstructionCoreError("provenance project identity differs")
    evidence = source.get("evidence")
    if not isinstance(evidence, list):
        raise VerifiedConstructionCoreError("provenance source evidence differs")
    key = binding[evidence_key_field]
    matches = [row for row in evidence if isinstance(row, dict) and row.get("key") == key]
    if len(matches) != 1:
        raise VerifiedConstructionCoreError("provenance evidence key differs")
    pinned = matches[0]
    evidence_id = binding[evidence_id_field]
    if evidence_id != atlas_stable_id(
        "evidence", "curated-official", key, pinned.get("content_hash")
    ):
        raise VerifiedConstructionCoreError("provenance evidence id differs")
    required = {
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "retrieved_at",
        "content_hash",
    }
    if any(not isinstance(pinned.get(field), str) or not pinned[field] for field in required):
        raise VerifiedConstructionCoreError("provenance evidence fields differ")
    published_at = pinned.get("published_at")
    if published_at is not None and not isinstance(published_at, str):
        raise VerifiedConstructionCoreError("provenance evidence publication date differs")
    row = {
        "evidence_id": evidence_id,
        "kind": pinned["kind"],
        "title": pinned["title"],
        "source_url": pinned["source_url"],
        "publisher": pinned["publisher"],
        "source_family": pinned["source_family"],
        "license": pinned["license"],
        "attribution": pinned["attribution"],
        "published_at": published_at or "",
        "retrieved_at": pinned["retrieved_at"],
        "content_hash": pinned["content_hash"],
    }
    return row, pinned


def _provenance_contract_v03(path: Path) -> dict[str, Any]:
    validate_frozen_v02(LEGACY_PREVIEW_V02_DIR)
    reviewed = _load_json(path)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "workload_scope_bindings",
        "role_bindings",
        "excluded_source_roles",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("provenance contract fields differ")
    if (
        reviewed.get("contract_id") != "verified-construction-core-v0.3-provenance"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
    ):
        raise VerifiedConstructionCoreError("provenance contract identity differs")
    base = reviewed.get("base_contract")
    if not isinstance(base, dict) or set(base) != {
        "preview_manifest",
        "reviewed_sites_definition",
    }:
        raise VerifiedConstructionCoreError("provenance base contract differs")
    expected_base = {
        "preview_manifest": (
            "verified_construction_core/2026-08-20-preview-v0.2/manifest.json",
            LEGACY_PREVIEW_V02_MANIFEST_SHA256,
        ),
        "reviewed_sites_definition": (
            "definitions/verified-construction-core-v0.2-reviewed-sites.json",
            "13f4d6e82c9057b1dd95319e19e30c2bae0ac0f1848d6e6dee2bbc10b5dde1d0",
        ),
    }
    for name, (expected_path, expected_sha256) in expected_base.items():
        item = base.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise VerifiedConstructionCoreError("provenance base item differs")
        if item != {"path": expected_path, "sha256": expected_sha256}:
            raise VerifiedConstructionCoreError("provenance base pin differs")
        _repository_input(expected_path, expected_sha256, "provenance base")

    workload_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "evidence_key",
        "evidence_id",
        "workload",
        "as_of_date",
        "method",
        "confidence",
        "deployment_scope",
        "semantic_scope",
    }
    role_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "evidence_key",
        "evidence_id",
        "relationship_scope",
        "semantic_scope",
    }
    excluded_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "candidate_evidence_key",
        "candidate_evidence_id",
        "relationship_scope",
        "semantic_scope",
        "reason",
    }
    workload_bindings = reviewed.get("workload_scope_bindings")
    role_bindings = reviewed.get("role_bindings")
    exclusions = reviewed.get("excluded_source_roles")
    if not all(isinstance(rows, list) for rows in (workload_bindings, role_bindings, exclusions)):
        raise VerifiedConstructionCoreError("provenance binding collections differ")
    evidence_rows: dict[str, dict[str, Any]] = {}
    workload_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(workload_bindings):
        if not isinstance(binding, dict) or set(binding) != workload_fields:
            raise VerifiedConstructionCoreError(
                f"workload provenance binding {index} differs"
            )
        key = (
            binding["project_stable_key"],
            binding["evidence_id"],
            binding["workload"],
        )
        if key in workload_keys or binding["deployment_scope"] != "intended":
            raise VerifiedConstructionCoreError("workload provenance identity differs")
        workload_keys.add(key)
        _calendar_date(binding["as_of_date"], "workload provenance as_of_date")
        if not _finite_number(binding["confidence"]) or not 0 <= binding["confidence"] <= 1:
            raise VerifiedConstructionCoreError("workload provenance confidence differs")
        evidence_row, pinned = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        metadata = pinned.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("workload_scope") != binding[
            "semantic_scope"
        ]:
            raise VerifiedConstructionCoreError("workload provenance scope differs")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row

    role_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(role_bindings):
        if not isinstance(binding, dict) or set(binding) != role_fields:
            raise VerifiedConstructionCoreError(f"role provenance binding {index} differs")
        key = (
            binding["project_stable_key"],
            binding["role"],
            binding["party"],
        )
        if (
            key in role_keys
            or binding["role"] not in ROLE_COLUMNS
            or binding["relationship_scope"] != "intended"
        ):
            raise VerifiedConstructionCoreError("role provenance identity differs")
        role_keys.add(key)
        evidence_row, pinned = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        metadata = pinned.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("role_scope") != binding[
            "semantic_scope"
        ]:
            raise VerifiedConstructionCoreError("role provenance scope differs")
        existing = evidence_rows.get(evidence_row["evidence_id"])
        if existing is not None and existing != evidence_row:
            raise VerifiedConstructionCoreError("provenance evidence collision")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row

    excluded_keys: set[tuple[str, str, str]] = set()
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict) or set(exclusion) != excluded_fields:
            raise VerifiedConstructionCoreError(f"role exclusion {index} differs")
        key = (
            exclusion["project_stable_key"],
            exclusion["role"],
            exclusion["party"],
        )
        if (
            key in excluded_keys
            or key in role_keys
            or exclusion["role"] not in ROLE_COLUMNS
            or exclusion["relationship_scope"] != "not_established"
            or not isinstance(exclusion["reason"], str)
            or not exclusion["reason"]
        ):
            raise VerifiedConstructionCoreError("role exclusion identity differs")
        excluded_keys.add(key)
        _evidence_from_pinned_source(
            exclusion,
            evidence_key_field="candidate_evidence_key",
            evidence_id_field="candidate_evidence_id",
        )
    base_projects = {
        row["project_stable_key"]: row
        for row in _load_csv(LEGACY_PREVIEW_V02_DIR / "projects.csv")
    }
    base_workloads: set[tuple[str, str, str, str, str, float]] = set()
    base_roles: set[tuple[str, str, str]] = set()
    for project_key, project in base_projects.items():
        workloads = _parse_json_field(project["workloads_json"], "base workloads")
        if not isinstance(workloads, list):
            raise VerifiedConstructionCoreError("provenance base workloads differ")
        for workload in workloads:
            _validate_source_workload_observation(workload)
            base_workloads.add(
                (
                    project_key,
                    workload["evidence_id"],
                    workload["workload"],
                    workload["as_of_date"],
                    workload["method"],
                    workload["confidence"],
                )
            )
        for role, column in ROLE_COLUMNS.items():
            for party in project[column].split(";"):
                if party.strip():
                    base_roles.add((project_key, role, party.strip()))
    bound_workloads = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
            row["as_of_date"],
            row["method"],
            row["confidence"],
        )
        for row in workload_bindings
    }
    if bound_workloads != base_workloads:
        raise VerifiedConstructionCoreError(
            "provenance workload bindings differ from frozen v0.2"
        )
    if role_keys | excluded_keys != base_roles:
        raise VerifiedConstructionCoreError(
            "provenance role decisions differ from frozen v0.2"
        )
    return {
        "workload_scope_bindings": workload_bindings,
        "role_bindings": role_bindings,
        "excluded_source_roles": exclusions,
        "evidence_rows": evidence_rows,
    }


def _provenance_contract_v04(path: Path) -> dict[str, Any]:
    reviewed = _load_json(path)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "workload_scope_bindings",
        "role_bindings",
        "excluded_source_roles",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("provenance contract fields differ")
    if (
        reviewed.get("contract_id") != "verified-construction-core-v0.4-provenance"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or reviewed.get("workload_scope_bindings") != []
        or reviewed.get("role_bindings") != []
    ):
        raise VerifiedConstructionCoreError("provenance current contract differs")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.3-provenance.json",
        "sha256": V03_PROVENANCE_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("provenance base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "provenance base"
    )
    base = _provenance_contract_v03(base_path)
    exclusions = reviewed.get("excluded_source_roles")
    expected_projects = {
        "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion": "atNorth",
        "curated:qscale-q01-levis-campus:building-b": "QScale",
    }
    excluded_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "candidate_evidence_key",
        "candidate_evidence_id",
        "relationship_scope",
        "semantic_scope",
        "reason",
    }
    if not isinstance(exclusions, list) or len(exclusions) != len(expected_projects):
        raise VerifiedConstructionCoreError("provenance current exclusions differ")
    seen: set[str] = set()
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict) or set(exclusion) != excluded_fields:
            raise VerifiedConstructionCoreError(
                f"provenance current exclusion {index} differs"
            )
        project_key = exclusion["project_stable_key"]
        if (
            project_key in seen
            or exclusion.get("party") != expected_projects.get(project_key)
            or exclusion.get("role") != "operator"
            or exclusion.get("relationship_scope") != "not_established"
            or not isinstance(exclusion.get("semantic_scope"), str)
            or not exclusion["semantic_scope"]
            or not isinstance(exclusion.get("reason"), str)
            or not exclusion["reason"]
        ):
            raise VerifiedConstructionCoreError(
                "provenance current exclusion identity differs"
            )
        seen.add(project_key)
        _evidence_from_pinned_source(
            exclusion,
            evidence_key_field="candidate_evidence_key",
            evidence_id_field="candidate_evidence_id",
        )
    if seen != set(expected_projects):
        raise VerifiedConstructionCoreError("provenance current cohort differs")
    base_exclusion_keys = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in base["excluded_source_roles"]
    }
    current_exclusion_keys = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in exclusions
    }
    if base_exclusion_keys & current_exclusion_keys:
        raise VerifiedConstructionCoreError("provenance inherited exclusion differs")
    return {
        "workload_scope_bindings": base["workload_scope_bindings"],
        "role_bindings": base["role_bindings"],
        "excluded_source_roles": [*base["excluded_source_roles"], *exclusions],
        "evidence_rows": base["evidence_rows"],
    }


def _provenance_contract_v05(path: Path) -> dict[str, Any]:
    reviewed = _load_json(path)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "workload_scope_bindings",
        "role_bindings",
        "excluded_source_roles",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("provenance contract fields differ")
    if (
        reviewed.get("contract_id") != "verified-construction-core-v0.5-provenance"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
    ):
        raise VerifiedConstructionCoreError("provenance current contract differs")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.4-provenance.json",
        "sha256": V04_PROVENANCE_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("provenance base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "provenance base"
    )
    base = _provenance_contract_v04(base_path)
    workload_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "evidence_key",
        "evidence_id",
        "workload",
        "as_of_date",
        "method",
        "confidence",
        "deployment_scope",
        "semantic_scope",
    }
    role_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "evidence_key",
        "evidence_id",
        "relationship_scope",
        "semantic_scope",
    }
    excluded_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "candidate_evidence_key",
        "candidate_evidence_id",
        "relationship_scope",
        "semantic_scope",
        "reason",
    }
    workload_bindings = reviewed.get("workload_scope_bindings")
    role_bindings = reviewed.get("role_bindings")
    exclusions = reviewed.get("excluded_source_roles")
    if (
        not isinstance(workload_bindings, list)
        or not isinstance(role_bindings, list)
        or not isinstance(exclusions, list)
        or len(workload_bindings) != 2
        or len(role_bindings) != 2
        or len(exclusions) != 2
    ):
        raise VerifiedConstructionCoreError("provenance current collections differ")
    evidence_rows = dict(base["evidence_rows"])

    def pinned_source(binding: Mapping[str, Any]) -> dict[str, Any]:
        path = _repository_input(
            binding["source_input_path"],
            binding["source_input_sha256"],
            "provenance current source",
        )
        source = _load_json(path)
        if not isinstance(source, dict):
            raise VerifiedConstructionCoreError("provenance current source differs")
        return source

    expected_workloads = {
        "curated:related-openai-oracle-stargate-michigan-saline:current-build": (
            "ai_specialized_unspecified"
        ),
        "curated:amazon-salem-township-innovation-campus:active-buildout": "mixed",
    }
    workload_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(workload_bindings):
        if not isinstance(binding, dict) or set(binding) != workload_fields:
            raise VerifiedConstructionCoreError(
                f"provenance current workload {index} differs"
            )
        project_key = binding["project_stable_key"]
        key = (project_key, binding["evidence_id"], binding["workload"])
        if (
            key in workload_keys
            or binding["workload"] != expected_workloads.get(project_key)
            or binding["deployment_scope"] != "intended"
            or not isinstance(binding["semantic_scope"], str)
            or not binding["semantic_scope"]
        ):
            raise VerifiedConstructionCoreError(
                "provenance current workload identity differs"
            )
        workload_keys.add(key)
        source = pinned_source(binding)
        matches = [
            row
            for row in source.get("workloads", [])
            if isinstance(row, dict)
            and row.get("entity") == "project"
            and row.get("value") == binding["workload"]
            and row.get("evidence_key") == binding["evidence_key"]
        ]
        if len(matches) != 1 or any(
            matches[0].get(field) != binding[field]
            for field in ("as_of_date", "method", "confidence")
        ):
            raise VerifiedConstructionCoreError(
                "provenance current workload projection differs"
            )
        evidence_row, _ = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        existing = evidence_rows.get(evidence_row["evidence_id"])
        if existing is not None and existing != evidence_row:
            raise VerifiedConstructionCoreError("provenance evidence collision")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row
    if {key[0] for key in workload_keys} != set(expected_workloads):
        raise VerifiedConstructionCoreError("provenance current workload cohort differs")

    expected_roles = {
        (
            "curated:related-openai-oracle-stargate-michigan-saline:current-build",
            "customer",
            "OpenAI",
        ),
        (
            "curated:related-openai-oracle-stargate-michigan-saline:current-build",
            "customer",
            "Oracle",
        ),
    }
    role_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(role_bindings):
        if not isinstance(binding, dict) or set(binding) != role_fields:
            raise VerifiedConstructionCoreError(
                f"provenance current role {index} differs"
            )
        key = (
            binding["project_stable_key"],
            binding["role"],
            binding["party"],
        )
        source = pinned_source(binding)
        source_roles = source.get("project", {}).get("roles", {})
        if (
            key not in expected_roles
            or key in role_keys
            or binding["relationship_scope"] != "intended"
            or not isinstance(binding["semantic_scope"], str)
            or not binding["semantic_scope"]
            or not isinstance(source_roles, dict)
            or binding["party"] not in source_roles.get(binding["role"], [])
        ):
            raise VerifiedConstructionCoreError(
                "provenance current role identity differs"
            )
        role_keys.add(key)
        evidence_row, _ = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        existing = evidence_rows.get(evidence_row["evidence_id"])
        if existing is not None and existing != evidence_row:
            raise VerifiedConstructionCoreError("provenance evidence collision")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row
    if role_keys != expected_roles:
        raise VerifiedConstructionCoreError("provenance current role cohort differs")

    expected_exclusions = {
        (
            "curated:microsoft-mount-pleasant-datacenter-campus:second-facility",
            "operator",
            "Microsoft",
        ),
        (
            "curated:amazon-salem-township-innovation-campus:active-buildout",
            "operator",
            "Amazon Web Services",
        ),
    }
    exclusion_keys: set[tuple[str, str, str]] = set()
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict) or set(exclusion) != excluded_fields:
            raise VerifiedConstructionCoreError(
                f"provenance current exclusion {index} differs"
            )
        key = (
            exclusion["project_stable_key"],
            exclusion["role"],
            exclusion["party"],
        )
        source = pinned_source(exclusion)
        source_roles = source.get("project", {}).get("roles", {})
        if (
            key not in expected_exclusions
            or key in exclusion_keys
            or exclusion["relationship_scope"] != "not_established"
            or not isinstance(exclusion["semantic_scope"], str)
            or not exclusion["semantic_scope"]
            or not isinstance(exclusion["reason"], str)
            or not exclusion["reason"]
            or not isinstance(source_roles, dict)
            or exclusion["party"] not in source_roles.get(exclusion["role"], [])
        ):
            raise VerifiedConstructionCoreError(
                "provenance current exclusion identity differs"
            )
        exclusion_keys.add(key)
        _evidence_from_pinned_source(
            exclusion,
            evidence_key_field="candidate_evidence_key",
            evidence_id_field="candidate_evidence_id",
        )
    if exclusion_keys != expected_exclusions:
        raise VerifiedConstructionCoreError(
            "provenance current exclusion cohort differs"
        )
    base_workload_keys = {
        (row["project_stable_key"], row["evidence_id"], row["workload"])
        for row in base["workload_scope_bindings"]
    }
    base_role_keys = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in [*base["role_bindings"], *base["excluded_source_roles"]]
    }
    if base_workload_keys & workload_keys or base_role_keys & (
        role_keys | exclusion_keys
    ):
        raise VerifiedConstructionCoreError("provenance inherited decision differs")
    return {
        "workload_scope_bindings": [
            *base["workload_scope_bindings"],
            *workload_bindings,
        ],
        "role_bindings": [*base["role_bindings"], *role_bindings],
        "excluded_source_roles": [
            *base["excluded_source_roles"],
            *exclusions,
        ],
        "evidence_rows": evidence_rows,
    }


def _provenance_contract() -> dict[str, Any]:
    reviewed = _load_json(PROVENANCE_DEFINITION)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "workload_scope_bindings",
        "role_bindings",
        "excluded_source_roles",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("provenance contract fields differ")
    if (
        reviewed.get("contract_id") != "verified-construction-core-v0.6-provenance"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or reviewed.get("workload_scope_bindings") != []
        or reviewed.get("excluded_source_roles") != []
    ):
        raise VerifiedConstructionCoreError("provenance current contract differs")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.5-provenance.json",
        "sha256": V05_PROVENANCE_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("provenance base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "provenance base"
    )
    base = _provenance_contract_v05(base_path)
    role_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "evidence_key",
        "evidence_id",
        "relationship_scope",
        "semantic_scope",
    }
    bindings = reviewed.get("role_bindings")
    if not isinstance(bindings, list) or len(bindings) != 1:
        raise VerifiedConstructionCoreError("provenance current collections differ")
    binding = bindings[0]
    expected_key = (
        "curated:skygard-osl1-hovinbyen-campus:phase-2",
        "operator",
        "Skygard",
    )
    if (
        not isinstance(binding, dict)
        or set(binding) != role_fields
        or (
            binding.get("project_stable_key"),
            binding.get("role"),
            binding.get("party"),
        )
        != expected_key
        or binding.get("relationship_scope") != "intended"
        or not isinstance(binding.get("semantic_scope"), str)
        or not binding["semantic_scope"]
    ):
        raise VerifiedConstructionCoreError("provenance current role differs")
    source_path = _repository_input(
        binding["source_input_path"],
        binding["source_input_sha256"],
        "provenance current source",
    )
    source = _load_json(source_path)
    roles = source.get("project", {}).get("roles", {})
    if not isinstance(roles, dict) or binding["party"] not in roles.get(
        binding["role"], []
    ):
        raise VerifiedConstructionCoreError("provenance source role differs")
    evidence_row, _ = _evidence_from_pinned_source(
        binding,
        evidence_key_field="evidence_key",
        evidence_id_field="evidence_id",
    )
    evidence_rows = dict(base["evidence_rows"])
    existing = evidence_rows.get(evidence_row["evidence_id"])
    if existing is not None and existing != evidence_row:
        raise VerifiedConstructionCoreError("provenance evidence collision")
    evidence_rows[evidence_row["evidence_id"]] = evidence_row
    inherited_keys = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in [*base["role_bindings"], *base["excluded_source_roles"]]
    }
    if expected_key in inherited_keys:
        raise VerifiedConstructionCoreError("provenance inherited decision differs")
    return {
        "workload_scope_bindings": base["workload_scope_bindings"],
        "role_bindings": [*base["role_bindings"], binding],
        "excluded_source_roles": base["excluded_source_roles"],
        "evidence_rows": evidence_rows,
    }


def _portable_source_inputs() -> list[dict[str, Any]]:
    _, delta = _reviewed_acceptances_from(REVIEW_DEFINITION)
    rows_by_path: dict[str, dict[str, Any]] = {}

    def add_input(
        path_text: str,
        expected_sha256: str,
        *,
        parents: Sequence[Mapping[str, str]] = (),
    ) -> None:
        path = _repository_input(path_text, expected_sha256, "portable source")
        deduplicated = {
            (item["path"], item["sha256"]): dict(item) for item in parents
        }
        for parent in deduplicated.values():
            _repository_input(parent["path"], parent["sha256"], "portable parent")
        row = {
            "path": path_text,
            "bytes": path.stat().st_size,
            "sha256": expected_sha256,
            "parent_manifests": sorted(
                deduplicated.values(), key=lambda item: item["path"]
            ),
        }
        existing = rows_by_path.get(path_text)
        if existing is not None and existing != row:
            raise VerifiedConstructionCoreError("portable source binding collision")
        rows_by_path[path_text] = row

    for acceptance in delta:
        add_input(
            acceptance["source_input_path"], acceptance["source_input_sha256"]
        )
    overlays = _reviewed_overlays(hydrated_crosscheck=False)
    for overlay in overlays["delta_overlays"]:
        bridge = overlays["bridges_by_overlay_id"][overlay["overlay_id"]]
        parents = [
            {
                "path": bridge["construction_source"]["release"]["manifest"]["path"],
                "sha256": bridge["construction_source"]["release"]["manifest"]["sha256"],
            }
        ]
        relationship_manifest = bridge["construction_source"]["project_to_campus"].get(
            "manifest"
        )
        if isinstance(relationship_manifest, dict):
            parents.append(
                {
                    "path": relationship_manifest["path"],
                    "sha256": relationship_manifest["sha256"],
                }
            )
        geometry_release = bridge.get("geometry_release")
        if isinstance(geometry_release, dict) and isinstance(
            geometry_release.get("manifest"), dict
        ):
            geometry_manifest = geometry_release["manifest"]
            parents.append(
                {
                    "path": geometry_manifest["path"],
                    "sha256": geometry_manifest["sha256"],
                }
            )
            if str(geometry_manifest["path"]).startswith("sources/"):
                add_input(geometry_manifest["path"], geometry_manifest["sha256"])
                for binding in geometry_release.get("members", {}).values():
                    add_input(
                        binding["path"],
                        binding["sha256"],
                        parents=(
                            {
                                "path": geometry_manifest["path"],
                                "sha256": geometry_manifest["sha256"],
                            },
                        ),
                    )
        elif isinstance(geometry_release, dict) and isinstance(
            geometry_release.get("capture"), dict
        ):
            capture = geometry_release["capture"]
            add_input(capture["path"], capture["sha256"])
        add_input(
            overlay["bridge_path"],
            overlay["bridge_sha256"],
            parents=parents,
        )
    return sorted(rows_by_path.values(), key=lambda row: row["path"])


def _validate_v06_inheritance(
    projects: Sequence[Mapping[str, str]],
    sites: Sequence[Mapping[str, str]],
    evidence: Sequence[Mapping[str, str]],
) -> None:
    validate_frozen_v05(LEGACY_PREVIEW_V05_DIR)
    base_projects = {
        row["project_stable_key"]: row
        for row in _load_csv(
            LEGACY_PREVIEW_V05_DIR / "projects.csv", PROJECT_FIELDS
        )
    }
    current = {row["project_stable_key"]: row for row in projects}
    if not set(base_projects) < set(current):
        raise VerifiedConstructionCoreError("preview v0.5 inheritance cohort differs")
    for key, base in base_projects.items():
        inherited = current[key]
        for field, value in base.items():
            if inherited.get(field) != value:
                raise VerifiedConstructionCoreError(
                    f"preview inherited project field differs: {field}"
                )

    base_sites = {
        row["site_id"]: row
        for row in _load_csv(
            LEGACY_PREVIEW_V05_DIR / "sites.csv", SITE_FIELDS
        )
    }
    current_sites = {row["site_id"]: row for row in sites}
    if not set(base_sites) < set(current_sites):
        raise VerifiedConstructionCoreError("preview v0.5 site inheritance differs")
    for site_id, base in base_sites.items():
        if any(current_sites[site_id].get(field) != value for field, value in base.items()):
            raise VerifiedConstructionCoreError(
                "preview inherited site fields differ"
            )

    base_evidence = {
        row["evidence_id"]: row
        for row in _load_csv(
            LEGACY_PREVIEW_V05_DIR / "evidence.csv", EVIDENCE_FIELDS
        )
    }
    current_evidence = {row["evidence_id"]: row for row in evidence}
    if not set(base_evidence) < set(current_evidence):
        raise VerifiedConstructionCoreError("preview v0.5 evidence inheritance differs")
    for evidence_id, base in base_evidence.items():
        inherited = current_evidence[evidence_id]
        if inherited != base:
            raise VerifiedConstructionCoreError(
                "preview inherited evidence content differs"
            )


def _validate_v06_delta_project(
    row: Mapping[str, str],
    acceptance: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, str]],
    expected_imagery_outcome: str,
    bridge: Mapping[str, Any],
    workload_binding_by_key: Mapping[
        tuple[str, str, str], Mapping[str, Any]
    ],
    role_bindings_by_project: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    source_path = _repository_input(
        acceptance["source_input_path"],
        acceptance["source_input_sha256"],
        "current reviewed-site",
    )
    source = _load_json(source_path)
    project = source.get("project")
    campus = source.get("campus")
    source_evidence = source.get("evidence")
    if not all(isinstance(value, dict) for value in (project, campus)) or not isinstance(
        source_evidence, list
    ):
        raise VerifiedConstructionCoreError("current reviewed-site source differs")
    if (
        project["stable_key"] != row["project_stable_key"]
        or campus["stable_key"] != row["physical_site_stable_key"]
        or project["name"] != row["name"]
        or project["country"] != row["country"]
    ):
        raise VerifiedConstructionCoreError("current reviewed-site identity differs")
    geometry_source = bridge["geometry_entity"]
    expected_geometry = geometry_source["geometry"]
    if (
        _parse_json_field(row["geometry_json"], "geometry") != expected_geometry
        or float(row["latitude"]) != float(geometry_source["latitude"])
        or float(row["longitude"]) != float(geometry_source["longitude"])
    ):
        raise VerifiedConstructionCoreError("current reviewed-site geometry differs")

    evidence_by_key = {
        item["key"]: item
        for item in source_evidence
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }

    def verify_evidence(key: str, evidence_id: str) -> None:
        pinned = evidence_by_key.get(key)
        if pinned is None or evidence_id != atlas_stable_id(
            "evidence", "curated-official", key, pinned.get("content_hash")
        ):
            raise VerifiedConstructionCoreError(
                "current reviewed-site evidence identity differs"
            )
        expected = {
            "evidence_id": evidence_id,
            "kind": pinned["kind"],
            "title": pinned["title"],
            "source_url": pinned["source_url"],
            "publisher": pinned["publisher"],
            "source_family": pinned["source_family"],
            "license": pinned["license"],
            "attribution": pinned["attribution"],
            "published_at": pinned.get("published_at") or "",
            "retrieved_at": pinned["retrieved_at"],
            "content_hash": pinned["content_hash"],
        }
        actual = evidence_by_id.get(evidence_id)
        if actual is None or any(actual.get(field) != value for field, value in expected.items()):
            raise VerifiedConstructionCoreError(
                "current reviewed-site evidence content differs"
            )

    bridge_evidence = _geometry_evidence_projection(bridge)
    if (
        row["geometry_evidence_id"] != bridge_evidence["evidence_id"]
        or row["geometry_source_url"] != bridge_evidence["source_url"]
    ):
        raise VerifiedConstructionCoreError("current reviewed-site geometry evidence differs")
    published_bridge_evidence = evidence_by_id.get(bridge_evidence["evidence_id"])
    if published_bridge_evidence is None or any(
        published_bridge_evidence.get(field) != value
        for field, value in bridge_evidence.items()
    ):
        raise VerifiedConstructionCoreError(
            "current reviewed-site bridge evidence content differs"
        )
    lifecycle = [
        item
        for item in source.get("lifecycle", [])
        if isinstance(item, dict) and item.get("entity") == "project"
    ]
    if not lifecycle:
        raise VerifiedConstructionCoreError("current reviewed-site lifecycle differs")
    latest = max(lifecycle, key=lambda item: item["as_of_date"])
    status_evidence = evidence_by_key.get(latest["evidence_key"])
    expected_status_id = atlas_stable_id(
        "evidence",
        "curated-official",
        latest["evidence_key"],
        status_evidence.get("content_hash") if status_evidence else None,
    )
    if (
        row["last_observed_physical_status"] != latest["value"]
        or row["status_as_of"] != latest["as_of_date"]
        or row["status_method"] != latest["method"]
        or row["status_evidence_id"] != expected_status_id
    ):
        raise VerifiedConstructionCoreError("current reviewed-site status differs")
    verify_evidence(latest["evidence_key"], expected_status_id)
    if row["status_source_url"] != evidence_by_key[latest["evidence_key"]]["source_url"]:
        raise VerifiedConstructionCoreError("current reviewed-site status URL differs")

    expected_capacity: list[dict[str, Any]] = []
    for observation in source.get("capacities", []):
        if not isinstance(observation, dict) or observation.get("entity") != "project":
            continue
        evidence_key = observation["evidence_key"]
        pinned = evidence_by_key[evidence_key]
        evidence_id = atlas_stable_id(
            "evidence", "curated-official", evidence_key, pinned["content_hash"]
        )
        verify_evidence(evidence_key, evidence_id)
        expected_capacity.append(
            {
                **{
                    field: (
                        float(value)
                        if field in {"low", "base", "high"} and value is not None
                        else value
                    )
                    for field, value in observation.items()
                    if field not in {"entity", "evidence_key"}
                },
                "evidence_id": evidence_id,
            }
        )
    actual_capacity = []
    for field in (
        "power_observations_json",
        "annual_energy_observations_json",
        "efficiency_observations_json",
    ):
        actual_capacity.extend(_parse_json_field(row[field], field))
    if actual_capacity != expected_capacity:
        raise VerifiedConstructionCoreError(
            "current reviewed-site typed metrics differ"
        )
    project_operating_models = [
        item
        for item in source.get("operating_models", [])
        if isinstance(item, dict) and item.get("entity") == "project"
    ]
    if project_operating_models:
        raise VerifiedConstructionCoreError(
            "current reviewed-site unsupported normalized claims differ"
        )
    expected_workloads: list[dict[str, Any]] = []
    source_workloads = source.get("workloads", [])
    if not isinstance(source_workloads, list) or any(
        not isinstance(item, dict) or item.get("entity") != "project"
        for item in source_workloads
    ):
        raise VerifiedConstructionCoreError(
            "current reviewed-site workload source differs"
        )
    for source_workload in source_workloads:
        evidence_key = source_workload.get("evidence_key")
        pinned = evidence_by_key.get(evidence_key)
        if pinned is None:
            raise VerifiedConstructionCoreError(
                "current reviewed-site workload evidence differs"
            )
        evidence_id = atlas_stable_id(
            "evidence", "curated-official", evidence_key, pinned["content_hash"]
        )
        verify_evidence(evidence_key, evidence_id)
        projected = {
            "as_of_date": source_workload["as_of_date"],
            "confidence": float(source_workload["confidence"]),
            "evidence_id": evidence_id,
            "method": source_workload["method"],
            "workload": source_workload["value"],
        }
        binding = workload_binding_by_key.get(
            (project["stable_key"], evidence_id, source_workload["value"])
        )
        if binding is None or any(
            binding.get(field) != value for field, value in projected.items()
        ):
            raise VerifiedConstructionCoreError(
                "current reviewed-site workload binding differs"
            )
        expected_workloads.append(
            {**projected, "deployment_scope": binding["deployment_scope"]}
        )
    expected_role_claims = sorted(
        [
            {
                "evidence_id": binding["evidence_id"],
                "party": binding["party"],
                "relationship_scope": binding["relationship_scope"],
                "role": binding["role"],
            }
            for binding in role_bindings_by_project.get(
                project["stable_key"], []
            )
        ],
        key=lambda claim: (claim["role"], claim["party"], claim["evidence_id"]),
    )
    role_projection: dict[str, list[str]] = {
        role: [] for role in ROLE_COLUMNS
    }
    for claim in expected_role_claims:
        role_projection[claim["role"]].append(claim["party"])

    country_iso_a2 = CURRENT_DELTA_COUNTRY_ISO_A2.get(project["country"])
    if country_iso_a2 is None:
        raise VerifiedConstructionCoreError(
            "current reviewed-site country code differs"
        )
    power = [item for item in expected_capacity if item["metric"] in POWER_METRICS]
    energy = [item for item in expected_capacity if item["metric"] in ENERGY_METRICS]
    efficiency = [
        item for item in expected_capacity if item["metric"] in EFFICIENCY_METRICS
    ]
    uncertainty = acceptance["horizontal_uncertainty_metres"]
    expected_row = {
        "project_id": atlas_stable_id(
            "entity", project["stable_key"], "project"
        ),
        "project_stable_key": project["stable_key"],
        "site_id": _stable_id("vcc-site", campus["stable_key"]),
        "physical_site_stable_key": campus["stable_key"],
        "name": project["name"],
        "country": project["country"],
        "country_iso_a2": country_iso_a2,
        "latitude": str(geometry_source["latitude"]),
        "longitude": str(geometry_source["longitude"]),
        "geometry_json": _json_bytes(expected_geometry).decode().strip(),
        "geometry_type": expected_geometry["type"],
        "geometry_source_entity_kind": acceptance["geometry_entity"],
        "geometry_derivation": acceptance["geometry_derivation"],
        "geometry_method": acceptance["geometry_method"],
        "geometry_scope_class": acceptance["geometry_scope_class"],
        "geometry_authority_class": bridge["review_decision"][
            "geometry_authority_class"
        ],
        "geometry_use_scope": bridge["review_decision"]["geometry_use_scope"],
        "geometry_precision_scope": acceptance["precision_scope"],
        "horizontal_uncertainty_metres": (
            "" if uncertainty is None else str(uncertainty)
        ),
        "horizontal_uncertainty_unknown_reason": bridge["review_decision"][
            "horizontal_uncertainty_unknown_reason"
        ],
        "geometry_evidence_id": row["geometry_evidence_id"],
        "last_observed_physical_status": latest["value"],
        "status_as_of": latest["as_of_date"],
        "status_age_days_at_review": str(
            (REVIEW_DATE - _calendar_date(latest["as_of_date"], "status_as_of")).days
        ),
        "status_method": latest["method"],
        "status_evidence_id": expected_status_id,
        "verification_posture": _verification_posture(
            bridge["review_decision"]["geometry_authority_class"],
            bridge["review_decision"]["geometry_use_scope"],
        ),
        "independent_imagery_verification": "false",
        "imagery_review_outcome": expected_imagery_outcome,
        "development_type": "unknown",
        "development_type_unknown_reason": (
            "source evidence does not distinguish greenfield, expansion, or retrofit"
        ),
        "operating_model": "unknown",
        "operating_model_unknown_reason": "not established by selected evidence",
        "operating_model_evidence_id": "",
        "workloads_json": _json_bytes(expected_workloads).decode().strip(),
        "workload_unknown_reason": (
            "" if expected_workloads else "not established by selected evidence"
        ),
        "role_claims_json": _json_bytes(expected_role_claims).decode().strip(),
        "power_observations_json": _json_bytes(power).decode().strip(),
        "power_unknown_reason": (
            "" if power else "no typed project power observation; not estimated"
        ),
        "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
        "annual_energy_unknown_reason": (
            "" if energy else "no scoped annual-energy inputs; not estimated"
        ),
        "efficiency_observations_json": _json_bytes(efficiency).decode().strip(),
        "efficiency_unknown_reason": (
            "" if efficiency else "no scoped PUE or WUE observation"
        ),
        "owner": "; ".join(sorted(role_projection["owner"])),
        "operator": "; ".join(sorted(role_projection["operator"])),
        "users": "; ".join(sorted(role_projection["user"])),
        "tenants": "; ".join(sorted(role_projection["tenant"])),
        "customers": "; ".join(sorted(role_projection["customer"])),
        "status_source_url": evidence_by_key[latest["evidence_key"]]["source_url"],
        "geometry_source_url": bridge_evidence["source_url"],
    }
    if dict(row) != expected_row:
        differing = sorted(
            field for field in PROJECT_FIELDS if row.get(field) != expected_row[field]
        )
        raise VerifiedConstructionCoreError(
            f"current reviewed-site project projection differs: {differing}"
        )


def _imagery_contract_v03(
    path: Path,
) -> tuple[str, list[dict[str, Any]]]:
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "default_outcome",
        "records",
    }:
        raise VerifiedConstructionCoreError("imagery-review contract fields differ")
    if reviewed.get("contract_id") != "verified-construction-core-v0.3-imagery-reviews":
        raise VerifiedConstructionCoreError("imagery-review contract id differs")
    if reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("imagery-review contract date differs")
    base = reviewed.get("base_contract")
    if not isinstance(base, dict) or set(base) != {"path", "sha256"}:
        raise VerifiedConstructionCoreError("imagery-review base contract differs")
    if base != {
        "path": "definitions/verified-construction-core-v0.2-imagery-reviews.json",
        "sha256": "0516a3281d0a3a1734a4bacb8f8d9e5419d0ae8dc22df36c098c5375f84ee613",
    }:
        raise VerifiedConstructionCoreError("imagery-review base pin differs")
    base_path = _repository_input(base["path"], base["sha256"], "imagery-review base")
    base_reviewed = _load_json(base_path)
    if not isinstance(base_reviewed, dict) or set(base_reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "default_outcome",
        "records",
    }:
        raise VerifiedConstructionCoreError("imagery-review base fields differ")
    if (
        base_reviewed.get("contract_id")
        != "verified-construction-core-v0.2-imagery-reviews"
        or base_reviewed.get("default_outcome") != reviewed.get("default_outcome")
    ):
        raise VerifiedConstructionCoreError("imagery-review base identity differs")
    default_outcome = reviewed.get("default_outcome")
    if default_outcome != "not_reviewed_for_core_preview":
        raise VerifiedConstructionCoreError("imagery-review default differs")
    base_records = base_reviewed.get("records")
    delta_records = reviewed.get("records")
    if (
        not isinstance(base_records, list)
        or not base_records
        or not isinstance(delta_records, list)
        or not delta_records
    ):
        raise VerifiedConstructionCoreError("imagery-review records are empty")
    records = [*base_records, *delta_records]
    expected_delta_outcomes = {
        "curated:kao-data-harlow-campus:klon-03-building": (
            "tracked_identity_bound_uncertain_with_unadjudicated_later_clear_"
            "conflict_no_construction_claim"
        ),
    }
    required = {
        "project_stable_key",
        "project_entity_id",
        "outcome",
        "portable_identity_binding",
        "identity_binding_basis",
        "primary_review_source_path",
        "primary_review_source_sha256",
        "primary_review_id",
        "primary_blind_id",
        "primary_queue_id",
        "source_comparison_sha256",
        "primary_verdict",
        "local_identity_lineage",
        "later_review_conflict",
        "no_claim_guardrail",
    }
    keys: set[str] = set()
    delta_keys: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != required:
            raise VerifiedConstructionCoreError(
                f"imagery-review record {index} has unexpected fields"
            )
        key = record["project_stable_key"]
        if not isinstance(key, str) or not key or key in keys:
            raise VerifiedConstructionCoreError("imagery-review project key differs")
        keys.add(key)
        if index >= len(base_records):
            delta_keys.add(key)
            if record["outcome"] != expected_delta_outcomes.get(key):
                raise VerifiedConstructionCoreError(
                    "imagery-review delta outcome differs"
                )
        try:
            if str(UUID(record["project_entity_id"])) != record["project_entity_id"]:
                raise ValueError
        except (ValueError, AttributeError) as error:
            raise VerifiedConstructionCoreError(
                "imagery-review project entity id differs"
            ) from error
        if record["no_claim_guardrail"] is not True or not isinstance(
            record["portable_identity_binding"], bool
        ):
            raise VerifiedConstructionCoreError("imagery-review guardrail differs")
        for field in (
            "outcome",
            "identity_binding_basis",
            "primary_review_id",
            "primary_blind_id",
            "primary_queue_id",
            "source_comparison_sha256",
        ):
            if not isinstance(record[field], str) or not record[field]:
                raise VerifiedConstructionCoreError(
                    f"imagery-review {field} differs"
                )
        relative_path = Path(record["primary_review_source_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise VerifiedConstructionCoreError("imagery-review source path escapes")
        source_path = ROOT / relative_path
        if not source_path.is_file() or _sha256_file(source_path) != record[
            "primary_review_source_sha256"
        ]:
            raise VerifiedConstructionCoreError("imagery-review source hash differs")
        source_review = _load_json(source_path)
        if source_review.get("review_id") != record["primary_review_id"]:
            raise VerifiedConstructionCoreError("imagery-review source id differs")
        blind_id = record["primary_blind_id"]
        decisions = source_review.get("decisions")
        lineage = source_review.get("lineage_records")
        if isinstance(decisions, list):
            matches = [row for row in decisions if row.get("blind_id") == blind_id]
            if len(matches) != 1 or any(
                matches[0].get(field) != value
                for field, value in record["primary_verdict"].items()
            ):
                raise VerifiedConstructionCoreError("imagery-review verdict differs")
        elif isinstance(lineage, list):
            matches = [row for row in lineage if row.get("blind_id") == blind_id]
            if len(matches) != 1:
                raise VerifiedConstructionCoreError("imagery-review lineage differs")
            match = matches[0]
            members = match.get("members")
            if not isinstance(members, list) or len(members) != 1:
                raise VerifiedConstructionCoreError("imagery-review member differs")
            member = members[0]
            semantics = source_review.get("decision_semantics", {}).get(
                match.get("visual_verdict")
            )
            expected_verdict = {
                "semantics": semantics,
                "visual_verdict": match.get("visual_verdict"),
            }
            if (
                member.get("stable_key") != key
                or member.get("entity_id") != record["project_entity_id"]
                or member.get("queue_id") != record["primary_queue_id"]
                or match.get("source_comparison_sha256")
                != record["source_comparison_sha256"]
                or expected_verdict != record["primary_verdict"]
            ):
                raise VerifiedConstructionCoreError(
                    "imagery-review identity-bound lineage differs"
                )
        else:
            raise VerifiedConstructionCoreError("imagery-review source format differs")
        local_lineage = record["local_identity_lineage"]
        if record["portable_identity_binding"]:
            if local_lineage is not None:
                raise VerifiedConstructionCoreError(
                    "portable imagery-review identity has local-only lineage"
                )
        else:
            if not isinstance(local_lineage, dict) or set(local_lineage) != {
                "analyst_review_path",
                "analyst_review_sha256",
                "queue_path",
                "queue_sha256",
            }:
                raise VerifiedConstructionCoreError(
                    "local imagery-review identity lineage differs"
                )
            analyst_path = ROOT / local_lineage["analyst_review_path"]
            queue_path = ROOT / local_lineage["queue_path"]
            if analyst_path.exists() != queue_path.exists():
                raise VerifiedConstructionCoreError(
                    "local imagery-review identity lineage is partially hydrated"
                )
            if analyst_path.exists():
                if (
                    _sha256_file(analyst_path)
                    != local_lineage["analyst_review_sha256"]
                    or _sha256_file(queue_path) != local_lineage["queue_sha256"]
                ):
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage hash differs"
                    )
                analyst_matches = [
                    row
                    for row in _load_jsonl(analyst_path)
                    if row.get("blind_id") == blind_id
                ]
                queue_matches = [
                    row
                    for row in _load_jsonl(queue_path)
                    if row.get("queue_id") == record["primary_queue_id"]
                ]
                if len(analyst_matches) != 1 or len(queue_matches) != 1:
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage is not unique"
                    )
                queue_entity = queue_matches[0].get("entity", {})
                if (
                    analyst_matches[0].get("queue_id")
                    != record["primary_queue_id"]
                    or analyst_matches[0]
                    .get("input_artifacts", {})
                    .get("comparison.png", {})
                    .get("sha256")
                    != record["source_comparison_sha256"]
                    or queue_entity.get("stable_key") != key
                    or queue_entity.get("id") != record["project_entity_id"]
                ):
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage differs"
                    )
        conflict = record["later_review_conflict"]
        if conflict is not None:
            if not isinstance(conflict, dict) or set(conflict) != {
                "blind_id",
                "identity_binding_status",
                "local_analyst_review_path",
                "local_analyst_review_sha256",
                "local_queue_path",
                "local_queue_sha256",
                "queue_id",
                "review_source_path",
                "review_source_sha256",
                "source_comparison_sha256",
                "supersedes_primary",
                "verdict",
            }:
                raise VerifiedConstructionCoreError("imagery-review conflict differs")
            if conflict["supersedes_primary"] is not False:
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict cannot supersede without adjudication"
                )
            conflict_path = ROOT / conflict["review_source_path"]
            if not conflict_path.is_file() or _sha256_file(conflict_path) != conflict[
                "review_source_sha256"
            ]:
                raise VerifiedConstructionCoreError("imagery-review conflict hash differs")
            conflict_source = _load_json(conflict_path)
            conflict_matches = [
                row
                for row in conflict_source.get("decisions", [])
                if row.get("blind_id") == conflict["blind_id"]
            ]
            if len(conflict_matches) != 1 or any(
                conflict_matches[0].get(field) != value
                for field, value in conflict["verdict"].items()
            ):
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict verdict differs"
                )
            conflict_analyst_path = ROOT / conflict["local_analyst_review_path"]
            conflict_queue_path = ROOT / conflict["local_queue_path"]
            if conflict_analyst_path.exists() != conflict_queue_path.exists():
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict lineage is partially hydrated"
                )
            if conflict_analyst_path.exists():
                if (
                    _sha256_file(conflict_analyst_path)
                    != conflict["local_analyst_review_sha256"]
                    or _sha256_file(conflict_queue_path)
                    != conflict["local_queue_sha256"]
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict lineage hash differs"
                    )
                conflict_analyst_matches = [
                    row
                    for row in _load_jsonl(conflict_analyst_path)
                    if row.get("blind_id") == conflict["blind_id"]
                ]
                conflict_queue_matches = [
                    row
                    for row in _load_jsonl(conflict_queue_path)
                    if row.get("queue_id") == conflict["queue_id"]
                ]
                if (
                    len(conflict_analyst_matches) != 1
                    or len(conflict_queue_matches) != 1
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict lineage is not unique"
                    )
                conflict_analyst = conflict_analyst_matches[0]
                conflict_entity = conflict_queue_matches[0].get("entity", {})
                if (
                    conflict_analyst.get("queue_id") != conflict["queue_id"]
                    or conflict_analyst.get("source_entity_lineage", {}).get("id")
                    != record["project_entity_id"]
                    or conflict_analyst
                    .get("input_artifacts", {})
                    .get("comparison.png", {})
                    .get("sha256")
                    != conflict["source_comparison_sha256"]
                    or conflict["source_comparison_sha256"]
                    != record["source_comparison_sha256"]
                    or conflict_entity.get("stable_key") != key
                    or conflict_entity.get("id") != record["project_entity_id"]
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict identity lineage differs"
                    )
    if delta_keys != set(expected_delta_outcomes):
        raise VerifiedConstructionCoreError("imagery-review delta cohort differs")
    return default_outcome, records


def _imagery_contract_v04(path: Path) -> tuple[str, list[dict[str, Any]]]:
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "default_outcome",
        "records",
    }:
        raise VerifiedConstructionCoreError("imagery-review contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-v0.4-imagery-reviews"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or reviewed.get("default_outcome") != "not_reviewed_for_core_preview"
        or reviewed.get("records") != []
    ):
        raise VerifiedConstructionCoreError("imagery-review current contract differs")
    base = reviewed.get("base_contract")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.3-imagery-reviews.json",
        "sha256": V03_IMAGERY_REVIEW_DEFINITION_SHA256,
    }
    if base != expected_base:
        raise VerifiedConstructionCoreError("imagery-review base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "imagery-review base"
    )
    default_outcome, records = _imagery_contract_v03(base_path)
    if default_outcome != reviewed["default_outcome"]:
        raise VerifiedConstructionCoreError("imagery-review default differs")
    return default_outcome, records


def _imagery_contract_v05(path: Path) -> tuple[str, list[dict[str, Any]]]:
    reviewed = _load_json(path)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "default_outcome",
        "records",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("imagery-review contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-v0.5-imagery-reviews"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or reviewed.get("default_outcome") != "not_reviewed_for_core_preview"
    ):
        raise VerifiedConstructionCoreError("imagery-review current contract differs")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.4-imagery-reviews.json",
        "sha256": V04_IMAGERY_REVIEW_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("imagery-review base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "imagery-review base"
    )
    default_outcome, inherited = _imagery_contract_v04(base_path)
    delta = reviewed.get("records")
    if not isinstance(delta, list) or len(delta) != 3:
        raise VerifiedConstructionCoreError("imagery-review current cohort differs")
    required = {
        "project_stable_key",
        "project_entity_id",
        "outcome",
        "portable_identity_binding",
        "identity_binding_basis",
        "primary_review_source_path",
        "primary_review_source_sha256",
        "primary_review_id",
        "primary_blind_id",
        "primary_queue_id",
        "source_comparison_sha256",
        "primary_verdict",
        "local_identity_lineage",
        "later_review_conflict",
        "no_claim_guardrail",
    }
    expected_outcomes = {
        "curated:related-openai-oracle-stargate-michigan-saline:current-build": (
            "tracked_identity_bound_visible_change_followup_only_no_construction_claim"
        ),
        "curated:microsoft-mount-pleasant-datacenter-campus:second-facility": (
            "tracked_identity_bound_uncertain_unsuperseded_no_construction_claim"
        ),
        "curated:amazon-salem-township-innovation-campus:active-buildout": (
            "tracked_identity_bound_uncertain_unsuperseded_no_construction_claim"
        ),
    }
    inherited_keys = {row["project_stable_key"] for row in inherited}
    delta_keys: set[str] = set()
    for index, record in enumerate(delta):
        if not isinstance(record, dict) or set(record) != required:
            raise VerifiedConstructionCoreError(
                f"imagery-review current record {index} differs"
            )
        key = record["project_stable_key"]
        if (
            key in inherited_keys
            or key in delta_keys
            or record["outcome"] != expected_outcomes.get(key)
            or record["portable_identity_binding"] is not True
            or record["local_identity_lineage"] is not None
            or record["later_review_conflict"] is not None
            or record["no_claim_guardrail"] is not True
            or not isinstance(record["identity_binding_basis"], str)
            or not record["identity_binding_basis"]
            or record["project_entity_id"]
            != atlas_stable_id("entity", key, "project")
        ):
            raise VerifiedConstructionCoreError(
                "imagery-review current identity differs"
            )
        delta_keys.add(key)
        source_path = _repository_input(
            record["primary_review_source_path"],
            record["primary_review_source_sha256"],
            "imagery-review current source",
        )
        source = _load_json(source_path)
        if source.get("review_id") != record["primary_review_id"]:
            raise VerifiedConstructionCoreError(
                "imagery-review current source id differs"
            )
        matches = [
            row
            for row in source.get("lineage_records", [])
            if isinstance(row, dict)
            and row.get("blind_id") == record["primary_blind_id"]
        ]
        if len(matches) != 1:
            raise VerifiedConstructionCoreError(
                "imagery-review current lineage differs"
            )
        match = matches[0]
        members = match.get("members")
        if not isinstance(members, list) or len(members) != 1:
            raise VerifiedConstructionCoreError(
                "imagery-review current member differs"
            )
        member = members[0]
        expected_verdict = {
            "semantics": source.get("decision_semantics", {}).get(
                match.get("visual_verdict")
            ),
            "visual_verdict": match.get("visual_verdict"),
        }
        if (
            member.get("stable_key") != key
            or member.get("entity_id") != record["project_entity_id"]
            or member.get("queue_id") != record["primary_queue_id"]
            or match.get("source_comparison_sha256")
            != record["source_comparison_sha256"]
            or expected_verdict != record["primary_verdict"]
        ):
            raise VerifiedConstructionCoreError(
                "imagery-review current identity-bound lineage differs"
            )
    if delta_keys != set(expected_outcomes):
        raise VerifiedConstructionCoreError("imagery-review current cohort differs")
    if default_outcome != reviewed["default_outcome"]:
        raise VerifiedConstructionCoreError("imagery-review default differs")
    return default_outcome, [*inherited, *delta]


def _imagery_contract() -> tuple[str, list[dict[str, Any]]]:
    reviewed = _load_json(IMAGERY_REVIEW_DEFINITION)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "default_outcome",
        "records",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("imagery-review contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-v0.6-imagery-reviews"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or reviewed.get("default_outcome") != "not_reviewed_for_core_preview"
    ):
        raise VerifiedConstructionCoreError("imagery-review current contract differs")
    expected_base = {
        "path": "definitions/verified-construction-core-v0.5-imagery-reviews.json",
        "sha256": V05_IMAGERY_REVIEW_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("imagery-review base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "imagery-review base"
    )
    default_outcome, inherited = _imagery_contract_v05(base_path)
    records = reviewed.get("records")
    fields = {
        "project_stable_key",
        "project_entity_id",
        "review_type",
        "outcome",
        "portable_identity_binding",
        "identity_binding_basis",
        "source_path",
        "source_sha256",
        "source_role",
        "publisher",
        "publisher_source_url",
        "publisher_media_redistributed",
        "independent_imagery_verification",
        "used_for_geometry",
        "used_for_status",
        "used_for_capacity",
        "used_for_progress",
        "used_for_building_count",
        "semantic_scope",
        "no_claim_guardrail",
    }
    project_key = (
        "curated:green-mountain-undheim-campus:current-two-building-development"
    )
    if not isinstance(records, list) or len(records) != 1:
        raise VerifiedConstructionCoreError("imagery-review current cohort differs")
    record = records[0]
    if (
        not isinstance(record, dict)
        or set(record) != fields
        or record.get("project_stable_key") != project_key
        or record.get("project_entity_id")
        != atlas_stable_id("entity", project_key, "project")
        or record.get("review_type") != "publisher_contractor_drone_context"
        or record.get("outcome")
        != "first_party_contractor_drone_imagery_present_not_independently_verified"
        or record.get("portable_identity_binding") is not True
        or record.get("source_role")
        != "portable_geometry_bridge_with_publisher_imagery_context"
        or record.get("publisher") != "Backe"
        or record.get("publisher_media_redistributed") is not False
        or record.get("independent_imagery_verification") is not False
        or any(
            record.get(field) is not False
            for field in (
                "used_for_geometry",
                "used_for_status",
                "used_for_capacity",
                "used_for_progress",
                "used_for_building_count",
            )
        )
        or record.get("no_claim_guardrail") is not True
        or any(
            not isinstance(record.get(field), str) or not record[field]
            for field in (
                "identity_binding_basis",
                "publisher_source_url",
                "semantic_scope",
            )
        )
    ):
        raise VerifiedConstructionCoreError("imagery-review current record differs")
    source_path = _repository_input(
        record["source_path"], record["source_sha256"], "imagery-review source"
    )
    bridge = _load_json(source_path)
    imagery = bridge.get("imagery_posture") if isinstance(bridge, dict) else None
    if (
        bridge.get("construction_source", {}).get("project", {}).get("stable_key")
        != project_key
        or not isinstance(imagery, dict)
        or imagery.get("outcome") != record["outcome"]
        or imagery.get("independent_imagery_verification") is not False
        or imagery.get("publisher_imagery", {}).get("publisher") != record["publisher"]
        or imagery.get("publisher_imagery", {}).get("media_redistributed") is not False
        or imagery.get("publisher_imagery", {}).get("source_page")
        != record["publisher_source_url"]
    ):
        raise VerifiedConstructionCoreError("imagery-review bridge binding differs")
    inherited_keys = {row["project_stable_key"] for row in inherited}
    if project_key in inherited_keys or default_outcome != reviewed["default_outcome"]:
        raise VerifiedConstructionCoreError("imagery-review inheritance differs")
    return default_outcome, [*inherited, record]


def _manifest_binding(
    binding: Mapping[str, Any], *, label: str
) -> tuple[Path, dict[str, Any]]:
    if set(binding) != {"path", "bytes", "sha256"}:
        raise VerifiedConstructionCoreError(f"{label} manifest binding differs")
    path = _repository_input(str(binding["path"]), str(binding["sha256"]), label)
    if path.stat().st_size != binding["bytes"]:
        raise VerifiedConstructionCoreError(f"{label} manifest byte count differs")
    manifest = _load_json(path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise VerifiedConstructionCoreError(f"{label} manifest differs")
    return path, manifest


def _validate_manifest_members(
    manifest: Mapping[str, Any], members: Mapping[str, Any], *, label: str
) -> None:
    if not isinstance(members, dict) or not members:
        raise VerifiedConstructionCoreError(f"{label} members differ")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict):
        raise VerifiedConstructionCoreError(f"{label} files differ")
    for name, binding in members.items():
        if not isinstance(binding, dict) or set(binding) != {
            "path",
            "bytes",
            "sha256",
        }:
            raise VerifiedConstructionCoreError(f"{label} member binding differs")
        relative = Path(str(binding["path"]))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.name != name
            or manifest_files.get(name)
            != {"bytes": binding["bytes"], "sha256": binding["sha256"]}
        ):
            raise VerifiedConstructionCoreError(f"{label} member metadata differs")


def _validate_polygon(geometry: Any, *, label: str) -> None:
    if not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"}:
        raise VerifiedConstructionCoreError(f"{label} geometry differs")
    if geometry.get("type") != "Polygon":
        raise VerifiedConstructionCoreError(f"{label} geometry type differs")
    coordinates = geometry.get("coordinates")
    if (
        not isinstance(coordinates, list)
        or len(coordinates) != 1
        or not isinstance(coordinates[0], list)
        or len(coordinates[0]) < 4
        or coordinates[0][0] != coordinates[0][-1]
    ):
        raise VerifiedConstructionCoreError(f"{label} polygon ring differs")
    for point in coordinates[0]:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in point
            )
            or not -180 <= point[0] <= 180
            or not -90 <= point[1] <= 90
        ):
            raise VerifiedConstructionCoreError(f"{label} polygon coordinate differs")


def _parent_row_binding(
    source_row: Any, *, release_id: Any, member: str, **identity: Any
) -> dict[str, Any]:
    if not isinstance(source_row, dict) or set(source_row) != {
        "line",
        "bytes",
        "sha256",
        "raw_csv_record_base64",
    }:
        raise VerifiedConstructionCoreError(
            "geometry bridge parent source-row binding differs"
        )
    return {
        "release_id": release_id,
        "member": member,
        **identity,
        "line": source_row["line"],
        "bytes": source_row["bytes"],
        "sha256": source_row["sha256"],
    }


def _validate_bridge_parent_row_bindings(
    bridge: Mapping[str, Any], project_stable_key: str
) -> None:
    expected = BRIDGE_PARENT_ROW_BINDINGS.get(project_stable_key)
    construction = bridge["construction_source"]
    topology = construction["project_to_campus"]
    geometry_release = bridge["geometry_release"]
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    relationship = topology.get("relationship")
    subject = topology.get("subject_member")
    object_member = topology.get("object_member")
    if (
        expected is None
        or not isinstance(geometry_release, dict)
        or not isinstance(entity, dict)
        or not isinstance(evidence, dict)
        or not isinstance(relationship, dict)
        or not isinstance(subject, dict)
        or not isinstance(object_member, dict)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge parent source-row binding differs"
        )
    actual = {
        "geometry_entity": _parent_row_binding(
            entity.get("source_row"),
            release_id=geometry_release.get("release_id"),
            member="entities.csv",
            stable_key=entity.get("stable_key"),
        ),
        "geometry_evidence": _parent_row_binding(
            evidence.get("source_row"),
            release_id=geometry_release.get("release_id"),
            member="evidence.csv",
            evidence_id=evidence.get("evidence_id"),
        ),
        "relationship": _parent_row_binding(
            relationship.get("source_row"),
            release_id=topology.get("bundle_id"),
            member="relationships.csv",
            relationship_id=relationship.get("relationship_id"),
        ),
        "subject_member": _parent_row_binding(
            subject.get("source_row"),
            release_id=topology.get("bundle_id"),
            member="component-members.csv",
            stable_key=subject.get("stable_key"),
        ),
        "object_member": _parent_row_binding(
            object_member.get("source_row"),
            release_id=topology.get("bundle_id"),
            member="component-members.csv",
            stable_key=object_member.get("stable_key"),
        ),
    }
    if actual != expected:
        raise VerifiedConstructionCoreError(
            "geometry bridge parent source-row binding differs"
        )


def _embedded_csv_source_row(
    binding: Any, expected_fields: Sequence[str], *, label: str
) -> dict[str, str]:
    if not isinstance(binding, dict) or set(binding) != {
        "line",
        "bytes",
        "sha256",
        "raw_csv_record_base64",
    }:
        raise VerifiedConstructionCoreError(f"{label} source-row binding differs")
    line = binding["line"]
    encoded_record = binding["raw_csv_record_base64"]
    if (
        isinstance(line, bool)
        or not isinstance(line, int)
        or line < 2
        or not isinstance(encoded_record, str)
        or not encoded_record
    ):
        raise VerifiedConstructionCoreError(f"{label} source-row payload differs")
    try:
        payload = base64.b64decode(encoded_record, validate=True)
        if base64.b64encode(payload).decode("ascii") != encoded_record:
            raise ValueError("non-canonical base64")
        raw_record = payload.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise VerifiedConstructionCoreError(
            f"{label} source-row payload differs"
        ) from error
    if not raw_record.endswith("\n") or "\r" in raw_record:
        raise VerifiedConstructionCoreError(f"{label} source-row payload differs")
    if (
        isinstance(binding["bytes"], bool)
        or not isinstance(binding["bytes"], int)
        or len(payload) != binding["bytes"]
        or not isinstance(binding["sha256"], str)
        or _sha256_bytes(payload) != binding["sha256"]
    ):
        raise VerifiedConstructionCoreError(f"{label} source-row hash differs")
    try:
        rows = list(csv.reader(io.StringIO(raw_record, newline="")))
    except csv.Error as error:
        raise VerifiedConstructionCoreError(
            f"{label} source-row CSV differs"
        ) from error
    if len(rows) != 1 or len(rows[0]) != len(expected_fields):
        raise VerifiedConstructionCoreError(f"{label} source-row CSV differs")
    canonical = io.StringIO(newline="")
    csv.writer(canonical, lineterminator="\n").writerow(rows[0])
    if canonical.getvalue() != raw_record:
        raise VerifiedConstructionCoreError(f"{label} source-row encoding differs")
    return dict(zip(expected_fields, rows[0], strict=True))


def _validate_hydrated_source_row(
    path: Path,
    binding: Mapping[str, Any],
    expected_fields: Sequence[str],
    *,
    label: str,
) -> dict[str, str]:
    row = _embedded_csv_source_row(binding, expected_fields, label=label)
    lines = path.read_bytes().splitlines(keepends=True)
    if not lines or lines[0] != _csv_bytes([], expected_fields):
        raise VerifiedConstructionCoreError(f"{label} source header differs")
    line = binding["line"]
    if not 1 <= line <= len(lines):
        raise VerifiedConstructionCoreError(f"{label} source-row line differs")
    payload = lines[line - 1]
    if payload != base64.b64decode(binding["raw_csv_record_base64"], validate=True):
        raise VerifiedConstructionCoreError(f"{label} source-row membership differs")
    return row


def _nullable_csv_value(value: str) -> str | None:
    return value if value else None


def _csv_float(value: str, *, label: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as error:
        raise VerifiedConstructionCoreError(f"{label} numeric field differs") from error
    if not math.isfinite(parsed):
        raise VerifiedConstructionCoreError(f"{label} numeric field differs")
    return parsed


def _csv_integer(value: str, *, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise VerifiedConstructionCoreError(f"{label} integer field differs") from error
    if str(parsed) != value:
        raise VerifiedConstructionCoreError(f"{label} integer field differs")
    return parsed


def _csv_json(value: str, *, label: str) -> Any:
    def object_without_duplicates(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def reject_nonfinite(constant: str) -> None:
        raise ValueError(f"non-finite JSON number: {constant}")

    try:
        return json.loads(
            value,
            object_pairs_hook=object_without_duplicates,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise VerifiedConstructionCoreError(f"{label} JSON field differs") from error


def _global_geometry_entity_projection(row: Mapping[str, str]) -> dict[str, Any]:
    float_fields = {
        "latitude",
        "longitude",
        "country_assignment_confidence",
        "status_confidence",
        "operating_model_confidence",
        "snapshot_confidence",
    }
    json_fields = {
        "workloads_json": "workloads_json",
        "capacity_estimates_json": "capacity_estimates_json",
        "geometry_json": "geometry",
        "tags_json": "tags",
    }
    projection: dict[str, Any] = {}
    for field in GLOBAL_GEOMETRY_ENTITY_FIELDS:
        target = json_fields.get(field, field)
        if field in float_fields:
            projection[target] = _csv_float(
                row[field], label=f"geometry entity {field}"
            )
        elif field in json_fields:
            projection[target] = _csv_json(
                row[field], label=f"geometry entity {field}"
            )
        else:
            projection[target] = _nullable_csv_value(row[field])
    projection["source_family"] = "openstreetmap"
    projection["source_attribution"] = "© OpenStreetMap contributors"
    if (
        not isinstance(projection["workloads_json"], list)
        or not isinstance(projection["capacity_estimates_json"], list)
        or not isinstance(projection["geometry"], dict)
        or not isinstance(projection["tags"], dict)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge entity JSON projection differs"
        )
    return projection


def _global_geometry_evidence_projection(row: Mapping[str, str]) -> dict[str, Any]:
    return {field: _nullable_csv_value(row[field]) for field in row}


def _exact_component_id(kind: str, occurrence_id: str) -> str:
    payload = "\x1f".join(("exact-component-v1", kind, occurrence_id)).encode()
    return f"exact:{hashlib.sha256(payload).hexdigest()}"


def _exact_relationship_id(
    relationship_type: str, subject_component_id: str, object_component_id: str
) -> str:
    payload = "\x1f".join(
        (
            "exact-relationship-v1",
            relationship_type,
            subject_component_id,
            object_component_id,
        )
    ).encode()
    return f"relationship:{hashlib.sha256(payload).hexdigest()}"


def _exact_relationship_projection(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        **{
            field: row[field]
            for field in EXACT_RELATIONSHIP_FIELDS
            if field
            not in {
                "typed_identity_tokens_json",
                "source_release_ids_json",
                "raw_relationship_count",
            }
        },
        "typed_identity_tokens": _csv_json(
            row["typed_identity_tokens_json"],
            label="geometry bridge relationship typed tokens",
        ),
        "source_release_ids": _csv_json(
            row["source_release_ids_json"],
            label="geometry bridge relationship releases",
        ),
        "raw_relationship_count": _csv_integer(
            row["raw_relationship_count"],
            label="geometry bridge relationship count",
        ),
    }


def _normalized_address_part(value: str, *, drop_road_types: bool = False) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", normalized.casefold())
    if drop_road_types:
        tokens = [token for token in tokens if token not in {"rue", "st", "street"}]
    return "".join(tokens)


def _canonical_address_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(
        str.maketrans("‐‑‒–—―−", "-------")
    )
    return " ".join(normalized.casefold().split())


def _canonical_street(value: str) -> str:
    normalized = _canonical_address_text(value)
    tokens = normalized.split()
    if tokens and tokens[0] == "rue":
        tokens = tokens[1:]
    elif tokens and tokens[-1] in {"st", "st.", "street"}:
        tokens = tokens[:-1]
    return " ".join(tokens)


def _canonical_canadian_postcode(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).upper())


def _validate_exact_component_projection(
    member: Any,
    *,
    entity: Mapping[str, Any],
    entity_kind: str,
    source_family: str,
    snapshot_evidence_id: str,
    label: str,
) -> dict[str, str]:
    if not isinstance(member, dict) or set(member) != {
        "component_id",
        "entity_id",
        "stable_key",
        "source_row",
    }:
        raise VerifiedConstructionCoreError(f"{label} projection fields differ")
    row = _embedded_csv_source_row(
        member["source_row"], EXACT_COMPONENT_FIELDS, label=label
    )
    occurrence_id = f"{SOURCE_RELEASE_ID}:{entity['entity_id']}"
    component_id = _exact_component_id(entity_kind, occurrence_id)
    if (
        member["component_id"] != row["component_id"]
        or member["entity_id"] != row["entity_id"]
        or member["stable_key"] != row["stable_key"]
        or row["component_id"] != component_id
        or row["occurrence_id"] != occurrence_id
        or row["release_id"] != SOURCE_RELEASE_ID
        or row["entity_id"] != entity["entity_id"]
        or row["entity_kind"] != entity_kind
        or row["stable_key"] != entity["stable_key"]
        or row["source_family"] != source_family
        or row["source_root"] != source_family
        or row["snapshot_evidence_id"] != snapshot_evidence_id
        or _csv_integer(row["component_member_count"], label=label) != 1
        or row["identity_proof_parent_occurrence_id"]
        or row["identity_proof_token"]
        or _csv_json(row["typed_identity_tokens_json"], label=label) != []
        or _csv_json(row["ambiguous_identity_tokens_json"], label=label) != []
    ):
        raise VerifiedConstructionCoreError(f"{label} projection differs")
    return row


def _validate_identity_bridge(
    bridge: Mapping[str, Any],
    project: Mapping[str, Any],
    campus: Mapping[str, Any],
    entity: Mapping[str, Any],
) -> None:
    identity_evidence = bridge["identity_bridge_evidence"]
    if entity.get("country") not in {project.get("country"), campus.get("country")}:
        raise VerifiedConstructionCoreError("geometry bridge identity country differs")
    project_key = str(project["stable_key"])
    if project_key == "curated:qscale-q01-levis-campus:building-b":
        if (
            not isinstance(identity_evidence, list)
            or len(identity_evidence) != 1
            or _json_bytes(identity_evidence[0]) != _json_bytes(QSCALE_IDENTITY_EVIDENCE)
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge identity evidence differs"
            )
        extraction = identity_evidence[0]["address_extraction"]
        tags = entity.get("tags")
        house_number = _canonical_address_text(extraction["house_number"])
        postcode = _canonical_canadian_postcode(extraction["postcode"])
        osm_house_number = _canonical_address_text(
            str(tags.get("addr:housenumber", "")) if isinstance(tags, dict) else ""
        )
        osm_postcode = _canonical_canadian_postcode(
            str(tags.get("addr:postcode", "")) if isinstance(tags, dict) else ""
        )
        if (
            not isinstance(tags, dict)
            or not re.fullmatch(r"[0-9]+[a-z]?", house_number)
            or not re.fullmatch(r"[A-Z][0-9][A-Z][0-9][A-Z][0-9]", postcode)
            or (house_number, _canonical_street(extraction["street"]), postcode)
            != ("2280", "albert-dion", "G7A5M9")
            or (osm_house_number, _canonical_street(str(tags.get("addr:street", ""))), osm_postcode)
            != ("2280", "albert-dion", "G7A5M9")
            or _canonical_address_text(str(entity.get("name", ""))) != "qscale"
            or _canonical_address_text(extraction["site_label"])
            != "headquarters - q01 campus"
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge QScale address identity differs"
            )
    elif project_key == "curated:green-campus-zrh1-lupfig:data-center-4":
        if (
            not isinstance(identity_evidence, list)
            or len(identity_evidence) != 1
            or _json_bytes(identity_evidence[0]) != _json_bytes(GREEN_IDENTITY_EVIDENCE)
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge identity evidence differs"
            )
        extraction = identity_evidence[0]["address_extraction"]
        tags = entity.get("tags")
        if (
            not isinstance(tags, dict)
            or (
                _canonical_address_text(extraction["house_number"]),
                _canonical_address_text(extraction["street"]),
                _canonical_address_text(extraction["postcode"]),
                _canonical_address_text(extraction["locality"]),
            )
            != ("31", "industriestrasse", "5242", "lupfig")
            or (
                _canonical_address_text(str(tags.get("addr:housenumber", ""))),
                _canonical_address_text(str(tags.get("addr:street", ""))),
                _canonical_address_text(str(tags.get("addr:postcode", ""))),
                _canonical_address_text(str(tags.get("addr:city", ""))),
            )
            != ("31", "industriestrasse", "5242", "lupfig")
            or _canonical_address_text(extraction["site_label"]) != "campus zrh1"
            or _canonical_address_text(str(tags.get("building", "")))
            != "data_center"
            or _canonical_address_text(str(tags.get("description", "")))
            != "green datacenter lupfig"
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Green address identity differs"
            )
    else:
        if identity_evidence != []:
            raise VerifiedConstructionCoreError(
                "geometry bridge identity evidence differs"
            )
        normalized_names = _normalized_address_part(
            " ".join(
                str(value)
                for value in (
                    project.get("name"),
                    campus.get("name"),
                    entity.get("name"),
                )
            )
        )
        tags = entity.get("tags")
        if not isinstance(tags, dict):
            raise VerifiedConstructionCoreError(
                "geometry bridge campus identity differs"
            )
        if project_key == (
            "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion"
        ):
            valid = (
                "ice02" in normalized_names
                and "atnorth" in normalized_names
                and _normalized_address_part(str(entity.get("operator", "")))
                == "atnorth"
            )
        elif project_key == (
            "curated:related-openai-oracle-stargate-michigan-saline:current-build"
        ):
            valid = (
                "thebarn" in normalized_names
                and _canonical_address_text(str(entity.get("name", "")))
                == "the barn data center"
                and tags.get("website") == "https://www.thesalinebarn.com/"
                and tags.get("landuse") == "construction"
                and tags.get("industrial") == "data_centre"
            )
        elif project_key == (
            "curated:microsoft-mount-pleasant-datacenter-campus:second-facility"
        ):
            valid = (
                "microsoftmountpleasant" in normalized_names
                and _canonical_address_text(str(entity.get("name", "")))
                == "microsoft fairwater ai phase 2"
                and tags.get("landuse") == "construction"
                and tags.get("industrial") == "data_centre"
            )
        elif project_key == (
            "curated:amazon-salem-township-innovation-campus:active-buildout"
        ):
            valid = (
                "amazonsalemtownship" in normalized_names
                and _canonical_address_text(str(entity.get("name", "")))
                == "amazon aws phl"
                and _canonical_address_text(str(entity.get("operator", "")))
                == "amazon web services"
                and tags.get("addr:housenumber") == "1125"
                and tags.get("addr:street") == "Electron Avenue"
                and tags.get("addr:postcode") == "18603"
                and tags.get("addr:city") == "Berwick"
            )
        else:
            valid = False
        if not valid:
            raise VerifiedConstructionCoreError(
                "geometry bridge campus identity differs"
            )


def _validate_bridge_acceptance_semantics(
    acceptance: Mapping[str, Any], bridge: Mapping[str, Any], *, label: str
) -> None:
    decision = bridge["review_decision"]
    if (
        acceptance.get("geometry_entity")
        != decision["geometry_target_entity_kind"]
        or any(
            acceptance.get(field) != decision[decision_field]
            for field, decision_field in (
                ("geometry_derivation", "geometry_derivation"),
                ("geometry_method", "geometry_method"),
                ("geometry_scope_class", "geometry_scope_class"),
                ("horizontal_uncertainty_metres", "horizontal_uncertainty_metres"),
                ("precision_scope", "precision_scope"),
            )
        )
    ):
        raise VerifiedConstructionCoreError(f"{label} overlay semantics differ")


def _geometry_evidence_projection(bridge: Mapping[str, Any]) -> dict[str, Any]:
    evidence = bridge["geometry_evidence"]
    return {
        field: evidence[field] if evidence[field] is not None else ""
        for field in EVIDENCE_FIELDS
        if field not in {"roles_json", "project_ids_json"}
    }


V06_BRIDGE_SEMANTICS = {
    "curated:adaniconnex-pune-data-center-campus:pnq04-current-build": {
        "decision": "accepted_as_project_locator",
        "geometry_target_entity_kind": "project",
        "geometry_derivation": "direct_geometry",
        "geometry_method": "official_project_report_coordinate_to_point",
        "geometry_scope_class": "official_source_reported_project_reference_point",
        "geometry_authority_class": "official_source",
        "geometry_use_scope": "project_locator",
        "geometry_stable_key": (
            "curated:adaniconnex-pune-data-center-campus:pnq04-current-build"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "The report does not identify the coordinate's datum, reference "
            "feature, collection method, or horizontal accuracy."
        ),
        "imagery_outcome": "not_reviewed_for_core_preview",
    },
    "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment": {
        "decision": "accepted_as_campus_locator",
        "geometry_target_entity_kind": "campus",
        "geometry_derivation": "cross_source_overlay",
        "geometry_method": (
            "official_company_exact_address_to_lands_department_location_search_"
            "and_official_hk80_wgs84_transform"
        ),
        "geometry_scope_class": (
            "official_lands_department_address_building_reference_point"
        ),
        "geometry_authority_class": "official_source",
        "geometry_use_scope": "campus_locator",
        "geometry_stable_key": "curated:goodman-hkg09-kwai-chung-data-centre",
        "horizontal_uncertainty_unknown_reason": (
            "The Location Search API and transformation API do not publish "
            "numeric horizontal accuracy for this selected result; the "
            "transformation service warns against precise-point applications."
        ),
        "imagery_outcome": "not_reviewed_for_core_preview",
    },
    "curated:green-mountain-undheim-campus:current-two-building-development": {
        "decision": "accepted_as_official_boundary",
        "geometry_target_entity_kind": "campus",
        "geometry_derivation": "official_parcel_union",
        "geometry_method": "authoritative_kartverket_cadastral_parcel_union",
        "geometry_scope_class": (
            "official_cadastral_project_site_parcel_union_boundary"
        ),
        "geometry_authority_class": "official_source",
        "geometry_use_scope": "official_boundary",
        "geometry_stable_key": (
            "kartverket:matrikkelteig-union/1121-46/316+317+319"
        ),
        "horizontal_uncertainty_unknown_reason": (
            "Kartverket supplies only a coarse green accuracy class and "
            "explicitly does not expose boundary-line type or detailed boundary "
            "quality."
        ),
        "imagery_outcome": (
            "first_party_contractor_drone_imagery_present_not_independently_verified"
        ),
    },
    "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build": {
        "decision": "accepted_as_campus_locator",
        "geometry_target_entity_kind": "campus",
        "geometry_derivation": "cross_source_overlay",
        "geometry_method": (
            "kartverket_official_cadastral_parcel_polygon_as_campus_locator"
        ),
        "geometry_scope_class": "official_cadastral_parcel_as_campus_locator",
        "geometry_authority_class": "official_source",
        "geometry_use_scope": "campus_locator",
        "geometry_stable_key": "kartverket:matrikkelen-teig/6508960482",
        "horizontal_uncertainty_unknown_reason": (
            "The captured WFS publishes accuracy class “Grønt” but no numeric "
            "horizontal uncertainty in metres; the bridge does not convert that "
            "class into survey accuracy."
        ),
        "imagery_outcome": "not_reviewed_for_core_preview",
    },
    "curated:skygard-osl1-hovinbyen-campus:phase-2": {
        "decision": "accepted_as_campus_locator",
        "geometry_target_entity_kind": "campus",
        "geometry_derivation": "cross_source_overlay",
        "geometry_method": (
            "official_nve_site_address_to_matrikkelen_epsg4326_address_point"
        ),
        "geometry_scope_class": (
            "official_matrikkelen_verified_address_representative_point"
        ),
        "geometry_authority_class": "official_source",
        "geometry_use_scope": "campus_locator",
        "geometry_stable_key": "curated:skygard-osl1-hovinbyen-campus",
        "horizontal_uncertainty_unknown_reason": (
            "The response marks the address point verified but does not publish "
            "numeric horizontal accuracy for this record."
        ),
        "imagery_outcome": "not_reviewed_for_core_preview",
    },
    **{
        f"curated:stt-jakarta-data-centre-campus:stt-jakarta-{number}": {
            "decision": "accepted_as_campus_locator",
            "geometry_target_entity_kind": "campus",
            "geometry_derivation": "cross_source_overlay",
            "geometry_method": (
                "openstreetmap_exactly_named_stt_jakarta_1_facility_polygon_as_"
                "shared_campus_locator"
            ),
            "geometry_scope_class": (
                "reviewed_openstreetmap_stt_jakarta_1_building_polygon"
            ),
            "geometry_authority_class": "community_mapped",
            "geometry_use_scope": "campus_locator",
            "geometry_stable_key": "osm:way/1533569836",
            "horizontal_uncertainty_unknown_reason": (
                "OpenStreetMap does not state horizontal positional accuracy; "
                "community-mapped geometry is not cadastral or survey geometry."
            ),
            "imagery_outcome": "not_reviewed_for_core_preview",
        }
        for number in (3, 5, 6)
    },
}


def _official_evidence_id(evidence: Mapping[str, Any]) -> str:
    return atlas_stable_id(
        "evidence",
        "curated-official",
        evidence.get("key"),
        evidence.get("content_hash"),
    )


def _validate_v06_fact_evidence(evidence: Any, *, label: str) -> None:
    if not isinstance(evidence, dict):
        raise VerifiedConstructionCoreError(f"{label} differs")
    for field in (
        "key",
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "retrieved_at",
        "content_hash",
    ):
        if not isinstance(evidence.get(field), str) or not evidence[field]:
            raise VerifiedConstructionCoreError(f"{label} {field} differs")
    content_hash = evidence["content_hash"]
    if re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
        raise VerifiedConstructionCoreError(f"{label} content hash differs")
    evidence_id = evidence.get("evidence_id")
    if evidence_id is not None and evidence_id != _official_evidence_id(evidence):
        raise VerifiedConstructionCoreError(f"{label} evidence identity differs")
    if "fact_payload" in evidence:
        if (
            evidence.get("fact_payload_canonical_sha256")
            != _sha256_bytes(_json_bytes(evidence["fact_payload"]))
            or not isinstance(evidence.get("fact_payload_hash_scope"), str)
            or not evidence["fact_payload_hash_scope"]
        ):
            raise VerifiedConstructionCoreError(f"{label} fact payload differs")
    captured_bytes = evidence.get("captured_bytes")
    if captured_bytes is not None and (
        isinstance(captured_bytes, bool)
        or not isinstance(captured_bytes, int)
        or captured_bytes <= 0
    ):
        raise VerifiedConstructionCoreError(f"{label} byte count differs")


def _projected_bridge_observations(
    source: Mapping[str, Any],
    evidence_by_key: Mapping[str, Mapping[str, Any]],
    *,
    collection: str,
    entity_kind: str,
) -> list[dict[str, Any]]:
    rows = source.get(collection, [])
    if not isinstance(rows, list):
        raise VerifiedConstructionCoreError(
            f"geometry bridge {collection} source differs"
        )
    projected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise VerifiedConstructionCoreError(
                f"geometry bridge {collection} observation differs"
            )
        if row.get("entity") != entity_kind:
            continue
        pinned = evidence_by_key.get(str(row.get("evidence_key")))
        if pinned is None:
            raise VerifiedConstructionCoreError(
                f"geometry bridge {collection} evidence differs"
            )
        evidence_id = _official_evidence_id(pinned)
        if collection == "capacities":
            observation = {
                **{
                    field: (
                        float(value)
                        if field in {"low", "base", "high"} and value is not None
                        else value
                    )
                    for field, value in row.items()
                    if field not in {"entity", "evidence_key"}
                },
                "evidence_id": evidence_id,
            }
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
        else:
            observation = {
                **{
                    ("workload" if field == "value" else field): value
                    for field, value in row.items()
                    if field not in {"entity", "evidence_key"}
                },
                "evidence_id": evidence_id,
            }
            _validate_source_workload_observation(observation)
        projected.append(observation)
    return projected


def _validate_v06_embedded_release_rows(
    rows: Any,
    members: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> None:
    if not isinstance(rows, dict) or not rows:
        raise VerifiedConstructionCoreError("geometry bridge release rows differ")
    for label, binding in rows.items():
        if not isinstance(binding, dict) or set(binding) != {
            "member",
            "source_row",
            *(
                {"evidence_id"}
                if binding.get("member") == "evidence.csv"
                else ({"stable_key"} if "stable_key" in binding else {"entity_id"})
            ),
        }:
            raise VerifiedConstructionCoreError(
                f"geometry bridge release row differs: {label}"
            )
        member = binding["member"]
        fields = (
            GLOBAL_GEOMETRY_EVIDENCE_FIELDS
            if member == "evidence.csv"
            else SOURCE_ENTITY_FIELDS
        )
        if member not in members or member not in {
            "construction_pipeline.csv",
            "entities.csv",
            "evidence.csv",
        }:
            raise VerifiedConstructionCoreError(
                f"geometry bridge release row member differs: {label}"
            )
        row = _embedded_csv_source_row(
            binding["source_row"], fields, label=f"geometry bridge {label}"
        )
        identity_field = next(
            field for field in ("evidence_id", "stable_key", "entity_id") if field in binding
        )
        if row[identity_field] != binding[identity_field]:
            raise VerifiedConstructionCoreError(
                f"geometry bridge release row identity differs: {label}"
            )
        if hydrated_crosscheck:
            metadata = members[member]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], f"geometry bridge {member}"
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"geometry bridge hydrated release differs: {member}"
                )
            _validate_hydrated_source_row(
                payload_path,
                binding["source_row"],
                fields,
                label=f"geometry bridge {label}",
            )


def _validate_v06_topology(
    bridge: Mapping[str, Any],
    project: Mapping[str, Any],
    campus: Mapping[str, Any],
    *,
    project_source_family: str,
    project_evidence_id: str,
    campus_source_family: str,
    campus_evidence_id: str,
    hydrated_crosscheck: bool,
) -> None:
    topology = bridge["construction_source"]["project_to_campus"]
    if not isinstance(topology, dict) or set(topology) != {
        "basis",
        "target_entity_id",
        "bundle_id",
        "manifest",
        "members",
        "relationship",
        "subject_member",
        "object_member",
        "supplemental_v97_atlas_feature",
    }:
        raise VerifiedConstructionCoreError("geometry bridge topology fields differ")
    if (
        topology.get("basis") != "v14_project_targets_explicit_parent"
        or topology.get("bundle_id") != "2026-07-22-public-open-v14"
        or topology.get("target_entity_id") != campus.get("entity_id")
        or topology.get("supplemental_v97_atlas_feature") is not None
    ):
        raise VerifiedConstructionCoreError("geometry bridge topology identity differs")
    _, manifest = _manifest_binding(
        topology["manifest"], label="geometry bridge topology release"
    )
    if (
        manifest.get("bundle_id") != topology["bundle_id"]
        or manifest.get("format")
        != "datacenter-atlas-exact-identity-decision-bundle-v1"
        or set(topology["members"])
        != {"component-members.csv", "relationships.csv"}
    ):
        raise VerifiedConstructionCoreError("geometry bridge topology release differs")
    _validate_manifest_members(
        manifest, topology["members"], label="geometry bridge topology release"
    )
    subject = topology["subject_member"]
    object_member = topology["object_member"]
    _validate_exact_component_projection(
        subject,
        entity=project,
        entity_kind="project",
        source_family=project_source_family,
        snapshot_evidence_id=project_evidence_id,
        label="geometry bridge topology subject",
    )
    _validate_exact_component_projection(
        object_member,
        entity=campus,
        entity_kind="campus",
        source_family=campus_source_family,
        snapshot_evidence_id=campus_evidence_id,
        label="geometry bridge topology object",
    )
    relationship = topology["relationship"]
    if not isinstance(relationship, dict) or set(relationship) != {
        "relationship_id",
        "relationship_type",
        "subject_component_id",
        "subject_kind",
        "object_component_id",
        "object_kind",
        "decision_basis",
        "typed_identity_tokens",
        "source_release_ids",
        "raw_relationship_count",
        "source_row",
    }:
        raise VerifiedConstructionCoreError(
            "geometry bridge topology relationship fields differ"
        )
    row = _embedded_csv_source_row(
        relationship["source_row"],
        EXACT_RELATIONSHIP_FIELDS,
        label="geometry bridge topology relationship",
    )
    projection = _exact_relationship_projection(row)
    if (
        {field: value for field, value in relationship.items() if field != "source_row"}
        != projection
        or relationship.get("relationship_type") != "project_targets"
        or relationship.get("subject_component_id") != subject.get("component_id")
        or relationship.get("subject_kind") != "project"
        or relationship.get("object_component_id")
        != object_member.get("component_id")
        or relationship.get("object_kind") != "campus"
        or relationship.get("decision_basis") != "explicit_parent"
        or relationship.get("typed_identity_tokens") != []
        or relationship.get("source_release_ids") != [SOURCE_RELEASE_ID]
        or relationship.get("raw_relationship_count") != 1
        or relationship.get("relationship_id")
        != _exact_relationship_id(
            "project_targets", subject["component_id"], object_member["component_id"]
        )
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge topology relationship differs"
        )
    if hydrated_crosscheck:
        for name, record, fields in (
            ("relationships.csv", relationship, EXACT_RELATIONSHIP_FIELDS),
            ("component-members.csv", subject, EXACT_COMPONENT_FIELDS),
            ("component-members.csv", object_member, EXACT_COMPONENT_FIELDS),
        ):
            metadata = topology["members"][name]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], f"geometry bridge {name}"
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"geometry bridge hydrated topology differs: {name}"
                )
            _validate_hydrated_source_row(
                payload_path,
                record["source_row"],
                fields,
                label=f"geometry bridge {name}",
            )


def _validate_v06_construction_source(
    bridge: Mapping[str, Any], *, hydrated_crosscheck: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    construction = bridge["construction_source"]
    allowed_fields = {
        "input",
        "release",
        "project",
        "campus",
        "project_to_campus",
        "status_evidence",
    }
    if not isinstance(construction, dict) or set(construction) not in {
        frozenset(allowed_fields),
        frozenset(allowed_fields | {"release_rows"}),
    }:
        raise VerifiedConstructionCoreError("geometry bridge construction source differs")
    source_input = construction["input"]
    if not isinstance(source_input, dict) or set(source_input) != {
        "path",
        "bytes",
        "sha256",
    }:
        raise VerifiedConstructionCoreError("geometry bridge source input differs")
    source_path = _repository_input(
        source_input["path"], source_input["sha256"], "geometry bridge source"
    )
    if source_path.stat().st_size != source_input["bytes"]:
        raise VerifiedConstructionCoreError("geometry bridge source byte count differs")
    source = _load_json(source_path)
    source_project = source.get("project") if isinstance(source, dict) else None
    source_campus = source.get("campus") if isinstance(source, dict) else None
    source_evidence = source.get("evidence") if isinstance(source, dict) else None
    if (
        not isinstance(source_project, dict)
        or not isinstance(source_campus, dict)
        or not isinstance(source_evidence, list)
    ):
        raise VerifiedConstructionCoreError("geometry bridge source record differs")
    evidence_by_key = {
        row["key"]: row
        for row in source_evidence
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    if len(evidence_by_key) != len(source_evidence):
        raise VerifiedConstructionCoreError("geometry bridge source evidence differs")
    lifecycle = [
        row
        for row in source.get("lifecycle", [])
        if isinstance(row, dict) and row.get("entity") == "project"
    ]
    if not lifecycle:
        raise VerifiedConstructionCoreError("geometry bridge lifecycle differs")
    latest = max(lifecycle, key=lambda row: row.get("as_of_date", ""))
    pinned_status = evidence_by_key.get(latest.get("evidence_key"))
    if pinned_status is None:
        raise VerifiedConstructionCoreError("geometry bridge status evidence differs")
    status_id = _official_evidence_id(pinned_status)
    campus_source_evidence = evidence_by_key.get(source_campus.get("evidence_key"))
    if campus_source_evidence is None:
        raise VerifiedConstructionCoreError(
            "geometry bridge campus source evidence differs"
        )
    campus_source_evidence_id = _official_evidence_id(campus_source_evidence)
    project_capacities = _projected_bridge_observations(
        source, evidence_by_key, collection="capacities", entity_kind="project"
    )
    project_workloads = _projected_bridge_observations(
        source, evidence_by_key, collection="workloads", entity_kind="project"
    )
    project = construction["project"]
    expected_project: dict[str, Any] = {
        "stable_key": source_project["stable_key"],
        "entity_id": atlas_stable_id(
            "entity", source_project["stable_key"], "project"
        ),
        "name": source_project["name"],
        "country": source_project["country"],
        "address": source_project["address"],
        "status": latest["value"],
        "status_as_of": latest["as_of_date"],
        "status_age_days_at_review": (
            REVIEW_DATE - _calendar_date(latest["as_of_date"], "bridge status")
        ).days,
        "status_method": latest["method"],
        "status_confidence": latest["confidence"],
        "status_evidence_id": status_id,
        "workloads_json": project_workloads,
        "capacity_estimates_json": project_capacities,
    }
    if isinstance(project, dict) and "capacity_semantics" in project:
        by_metric = {row["metric"]: row["base"] for row in project_capacities}
        expected_semantics = project["capacity_semantics"]
        if (
            not isinstance(expected_semantics, dict)
            or set(expected_semantics)
            != {
                "non_additive",
                "critical_it_mw",
                "gross_facility_mw",
                "annual_energy_observation",
                "guardrail",
            }
            or expected_semantics.get("non_additive") is not True
            or expected_semantics.get("critical_it_mw")
            != by_metric.get("critical_it_mw")
            or expected_semantics.get("gross_facility_mw")
            != by_metric.get("gross_facility_mw")
            or expected_semantics.get("annual_energy_observation") is not None
            or not isinstance(expected_semantics.get("guardrail"), str)
            or not expected_semantics["guardrail"]
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge capacity semantics differ"
            )
        expected_project["capacity_semantics"] = expected_semantics
    if not isinstance(project, dict) or project != expected_project:
        raise VerifiedConstructionCoreError(
            "geometry bridge construction project projection differs"
        )

    campus_models = [
        row
        for row in source.get("operating_models", [])
        if isinstance(row, dict) and row.get("entity") == "campus"
    ]
    if len(campus_models) > 1:
        raise VerifiedConstructionCoreError("geometry bridge campus model differs")
    model = campus_models[0] if campus_models else None
    model_id = (
        _official_evidence_id(evidence_by_key[model["evidence_key"]])
        if model is not None
        else None
    )
    campus = construction["campus"]
    expected_campus: dict[str, Any] = {
        "stable_key": source_campus["stable_key"],
        "entity_id": atlas_stable_id(
            "entity", source_campus["stable_key"], "campus"
        ),
        "name": source_campus["name"],
        "country": source_campus["country"],
        "address": source_campus["address"],
        "operating_model": model["value"] if model else None,
        "operating_model_confidence": model["confidence"] if model else None,
        "operating_model_evidence_id": model_id,
    }
    campus_workloads = _projected_bridge_observations(
        source, evidence_by_key, collection="workloads", entity_kind="campus"
    )
    campus_capacities = _projected_bridge_observations(
        source, evidence_by_key, collection="capacities", entity_kind="campus"
    )
    if isinstance(campus, dict) and "workloads_json" in campus:
        expected_campus["workloads_json"] = campus_workloads
    elif campus_workloads:
        raise VerifiedConstructionCoreError("geometry bridge campus workloads differ")
    if isinstance(campus, dict) and "capacity_estimates_json" in campus:
        expected_campus["capacity_estimates_json"] = campus_capacities
    elif campus_capacities:
        raise VerifiedConstructionCoreError("geometry bridge campus capacities differ")
    if not isinstance(campus, dict) or campus != expected_campus:
        raise VerifiedConstructionCoreError(
            "geometry bridge construction campus projection differs"
        )

    status = construction["status_evidence"]
    required_status_fields = {
        "evidence_id",
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "published_at",
        "retrieved_at",
        "content_hash",
    }
    if (
        not isinstance(status, dict)
        or not required_status_fields <= set(status)
        or frozenset(set(status) - required_status_fields)
        not in {frozenset(), frozenset({"key"}), frozenset({"key", "content_hash_scope"})}
        or status.get("evidence_id") != status_id
        or project["status_evidence_id"] != status_id
    ):
        raise VerifiedConstructionCoreError("geometry bridge status projection differs")
    for field in required_status_fields - {"evidence_id"}:
        if status.get(field) != pinned_status.get(field):
            raise VerifiedConstructionCoreError(
                "geometry bridge status evidence content differs"
            )
    if "key" in status and status["key"] != pinned_status["key"]:
        raise VerifiedConstructionCoreError("geometry bridge status evidence key differs")

    release = construction["release"]
    if not isinstance(release, dict) or set(release) not in {
        frozenset({"release_id", "manifest", "members"}),
        frozenset({"release_id", "manifest", "members", "raw_rows"}),
    } or release.get("release_id") != SOURCE_RELEASE_ID:
        raise VerifiedConstructionCoreError("geometry bridge source release differs")
    _, release_manifest = _manifest_binding(
        release["manifest"], label="geometry bridge source release"
    )
    if set(release["members"]) != {
        "construction_pipeline.csv",
        "entities.csv",
        "evidence.csv",
    }:
        raise VerifiedConstructionCoreError("geometry bridge source members differ")
    _validate_manifest_members(
        release_manifest, release["members"], label="geometry bridge source release"
    )
    embedded_rows = release.get("raw_rows", construction.get("release_rows"))
    if embedded_rows is not None:
        _validate_v06_embedded_release_rows(
            embedded_rows,
            release["members"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
    _validate_v06_topology(
        bridge,
        project,
        campus,
        project_source_family=pinned_status["source_family"],
        project_evidence_id=status_id,
        campus_source_family=campus_source_evidence["source_family"],
        campus_evidence_id=campus_source_evidence_id,
        hydrated_crosscheck=hydrated_crosscheck,
    )
    return project, campus


def _point_inside_ring(point: Sequence[float], ring: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = first
        x2, y2 = second
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) <= 1e-12 and min(x1, x2) <= x <= max(x1, x2) and min(
            y1, y2
        ) <= y <= max(y1, y2):
            return True
        if (y1 > y) != (y2 > y):
            intersection = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < intersection:
                inside = not inside
    return inside


def _validate_v06_official_point_geometry(
    bridge: Mapping[str, Any],
    project: Mapping[str, Any],
    campus: Mapping[str, Any],
) -> None:
    if bridge["geometry_release"] is not None:
        raise VerifiedConstructionCoreError(
            "geometry bridge official point release must be absent"
        )
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    expected_entity_fields = {
        "entity_id",
        "entity_kind",
        "stable_key",
        "name",
        "latitude",
        "longitude",
        "country",
        "address",
        "geometry",
        "source_evidence_id",
        "source_url",
        "source_publisher",
        "source_license",
        "source_retrieved_at",
    }
    target = project if entity.get("entity_kind") == "project" else campus
    if (
        not isinstance(entity, dict)
        or set(entity) != expected_entity_fields
        or entity.get("entity_kind") not in {"project", "campus"}
        or any(
            entity.get(field) != target.get(field)
            for field in ("entity_id", "stable_key", "name", "country")
        )
        or not isinstance(evidence, dict)
    ):
        raise VerifiedConstructionCoreError("geometry bridge official point differs")
    geometry = entity["geometry"]
    if (
        not isinstance(geometry, dict)
        or geometry != {
            "type": "Point",
            "coordinates": [entity["longitude"], entity["latitude"]],
        }
        or not _finite_number(entity["latitude"])
        or not _finite_number(entity["longitude"])
        or not -90 <= entity["latitude"] <= 90
        or not -180 <= entity["longitude"] <= 180
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge official point coordinates differ"
        )
    _validate_v06_fact_evidence(evidence, label="geometry bridge point evidence")
    if (
        evidence.get("evidence_id") != entity.get("source_evidence_id")
        or evidence.get("source_url") != entity.get("source_url")
        or evidence.get("publisher") != entity.get("source_publisher")
        or evidence.get("license") != entity.get("source_license")
        or evidence.get("retrieved_at") != entity.get("source_retrieved_at")
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge official point evidence differs"
        )
    fact_payload = evidence.get("fact_payload")
    if not isinstance(fact_payload, dict):
        raise VerifiedConstructionCoreError(
            "geometry bridge official point fact payload differs"
        )
    source_family = evidence.get("source_family")
    expected_evidence = {
        "curated:adaniconnex-pune-data-center-campus:pnq04-current-build": (
            "india-adaniconnex-pune-pnq04-compliance-captured-2026-07-21",
            "adaniconnex_environmental_compliance_reports",
            "406e7134f896a916f6ac978a888183f67de62218cbfbd24a90248af52af544f4",
        ),
        "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment": (
            "hk-landsd-hk80-to-wgs84-hkg09-address-point-captured-2026-08-20",
            "hong_kong_lands_department_coordinate_transformation_api",
            "8db2983a30966dedfb7470b0712deb3bb82505e82ef65ac1b786f052ad8efb9e",
        ),
        "curated:skygard-osl1-hovinbyen-campus:phase-2": (
            "norway-geonorge-ostre-aker-vei-24c-address-epsg4326-captured-2026-08-20",
            "kartverket_matrikkelen_address_rest_api",
            "de1397fe0cf91cb53d0330d4b1cfbb589b868122b2602100a375c69f4b506de1",
        ),
    }.get(project.get("stable_key"))
    if expected_evidence is None or (
        evidence.get("key"), source_family, evidence.get("content_hash")
    ) != expected_evidence:
        raise VerifiedConstructionCoreError(
            "geometry bridge official point evidence contract differs"
        )
    official_source_contract = {
        "curated:adaniconnex-pune-data-center-campus:pnq04-current-build": {
            "license": "all-rights-reserved",
            "license_url": None,
            "publisher": "Pune Data Center Limited",
            "attribution": "Pune Data Center Limited",
            "published_at": None,
            "retrieved_at": "2026-07-21T16:11:57Z",
            "kind": "company_disclosure",
            "title": "Compliance to Stipulated Conditions in Environment Clearance, October 2024 to March 2025 — Development of Data Center PNQ04",
            "source_url": "https://www.adaniconnex.com/-/media/Project/AdaniConneX/AdaniConneX-AboutUs-Assets/Certifications/Post-EC-compliance-report-PNQ26--with-Anneure.pdf",
            "geometry_license_url": None,
            "geometry_source": "The geometry is an arithmetic normalization of the coordinate printed in the official PNQ04 PDF; the PDF is not redistributed.",
            "fact_payload_sha256": "1d8dfc91502babb1ca58cbfc140d03b25c79197eb00eb47a6f247dc85f45103e",
        },
        "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment": {
            "license": "Hong-Kong-DATA.GOV.HK-Terms-of-Use",
            "license_url": "https://data.gov.hk/en/terms-and-conditions",
            "publisher": "Geodetic Survey Section, Lands Department, Government of the Hong Kong SAR",
            "attribution": "Government of the Hong Kong SAR / Lands Department / DATA.GOV.HK",
            "published_at": None,
            "retrieved_at": "2026-08-20T19:57:28Z",
            "kind": "government_coordinate_transformation",
            "title": "Lands Department HK1980 Grid to WGS84 transformation",
            "source_url": "https://www.geodetic.gov.hk/transform/v2/?inSys=hkgrid&outSys=wgsgeog&e=832091&n=825415",
            "geometry_license_url": "https://data.gov.hk/en/terms-and-conditions",
            "geometry_source": "The exact two-field official transformation response is distributed under DATA.GOV.HK terms with Government, Lands Department, and DATA.GOV.HK attribution.",
            "fact_payload_sha256": "ab876378ef271567f2cc44e9d052ac6a6cbb8da2ae3dc48fe785fbdc7718e50c",
        },
        "curated:skygard-osl1-hovinbyen-campus:phase-2": {
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "publisher": "Kartverket / Statens kartverk",
            "attribution": "Kartverket",
            "published_at": None,
            "retrieved_at": "2026-08-20T19:58:01Z",
            "kind": "government_address_register",
            "title": "Matrikkelen address lookup: Østre Aker vei 24C, Oslo",
            "source_url": "https://ws.geonorge.no/adresser/v1/sok?sok=%C3%98stre%20Aker%20vei%2024C%2C%200581%20Oslo&utkoordsys=4326&treffPerSide=10",
            "geometry_license_url": "https://creativecommons.org/licenses/by/4.0/",
            "geometry_source": "The exact Kartverket address fields are open government data under CC BY 4.0 and require Kartverket attribution.",
            "fact_payload_sha256": "ebceb1b62f367711d095f3fb07ad843944f2ec01f0d3125b805c3ead92ea827e",
        },
    }[project["stable_key"]]
    rights = bridge.get("rights")
    if (
        evidence.get("license") != official_source_contract["license"]
        or evidence.get("license_url") != official_source_contract["license_url"]
        or evidence.get("publisher") != official_source_contract["publisher"]
        or evidence.get("attribution") != official_source_contract["attribution"]
        or evidence.get("published_at") != official_source_contract["published_at"]
        or evidence.get("retrieved_at") != official_source_contract["retrieved_at"]
        or evidence.get("kind") != official_source_contract["kind"]
        or evidence.get("title") != official_source_contract["title"]
        or evidence.get("source_url") != official_source_contract["source_url"]
        or evidence.get("fact_payload_canonical_sha256")
        != official_source_contract["fact_payload_sha256"]
        or entity.get("source_license") != official_source_contract["license"]
        or not isinstance(rights, dict)
        or rights.get("geometry_license_url")
        != official_source_contract["geometry_license_url"]
        or rights.get("geometry_source")
        != official_source_contract["geometry_source"]
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge official point rights contract differs"
        )
    if source_family == "adaniconnex_environmental_compliance_reports":
        dms_pattern = re.compile(r"^([0-9]+)º([0-9]+)ʹ([0-9]+(?:\.[0-9]+)?)ʺ$")

        def decimal_from_dms(value: object) -> float:
            match = dms_pattern.fullmatch(str(value))
            if match is None:
                raise VerifiedConstructionCoreError(
                    "geometry bridge official DMS coordinate differs"
                )
            degrees, minutes, seconds = match.groups()
            if int(minutes) >= 60 or float(seconds) >= 60:
                raise VerifiedConstructionCoreError(
                    "geometry bridge official DMS coordinate differs"
                )
            return int(degrees) + int(minutes) / 60 + float(seconds) / 3600

        latitude = decimal_from_dms(fact_payload.get("latitude_dms"))
        longitude = decimal_from_dms(fact_payload.get("longitude_dms"))
        if (
            fact_payload.get("latitude_decimal") != entity["latitude"]
            or fact_payload.get("longitude_decimal") != entity["longitude"]
            or not math.isclose(latitude, entity["latitude"], abs_tol=1e-10)
            or not math.isclose(longitude, entity["longitude"], abs_tol=1e-10)
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge official DMS derivation differs"
            )
    elif source_family == "hong_kong_lands_department_coordinate_transformation_api":
        request = fact_payload.get("request_input")
        response = fact_payload.get("response")
        address_facts = next(
            (
                item.get("fact_payload")
                for item in bridge["identity_bridge_evidence"]
                if item.get("source_family")
                == "hong_kong_lands_department_location_search_api"
            ),
            None,
        )
        selected = (
            address_facts.get("selected_result")
            if isinstance(address_facts, dict)
            else None
        )
        if (
            not isinstance(request, dict)
            or not isinstance(response, dict)
            or not isinstance(selected, dict)
            or request
            != {
                "inSys": "hkgrid",
                "outSys": "wgsgeog",
                "e": selected.get("x"),
                "n": selected.get("y"),
            }
            or response
            != {"wgsLat": entity["latitude"], "wgsLong": entity["longitude"]}
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge official coordinate transform differs"
            )
    elif source_family == "kartverket_matrikkelen_address_rest_api":
        address = fact_payload.get("address")
        point = address.get("representasjonspunkt") if isinstance(address, dict) else None
        if (
            not isinstance(point, dict)
            or point
            != {
                "epsg": "EPSG:4326",
                "lat": entity["latitude"],
                "lon": entity["longitude"],
            }
            or address.get("stedfestingverifisert") is not True
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge official address point differs"
            )
    else:
        raise VerifiedConstructionCoreError(
            "geometry bridge official point source family differs"
        )


def _validate_v06_osm_geometry(
    bridge: Mapping[str, Any], *, hydrated_crosscheck: bool
) -> None:
    release = bridge["geometry_release"]
    if not isinstance(release, dict) or set(release) != {
        "release_id",
        "as_of",
        "recorded_at",
        "manifest",
        "members",
    } or release.get("release_id") != "global-open-v3":
        raise VerifiedConstructionCoreError("geometry bridge OSM release differs")
    _, manifest = _manifest_binding(
        release["manifest"], label="geometry bridge OSM release"
    )
    if set(release["members"]) != {"entities.csv", "evidence.csv"}:
        raise VerifiedConstructionCoreError("geometry bridge OSM members differ")
    _validate_manifest_members(manifest, release["members"], label="geometry bridge OSM")
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    if not isinstance(entity, dict) or not isinstance(evidence, dict):
        raise VerifiedConstructionCoreError("geometry bridge OSM records differ")
    entity_row = _embedded_csv_source_row(
        entity.get("source_row"),
        GLOBAL_GEOMETRY_ENTITY_FIELDS,
        label="geometry bridge OSM entity",
    )
    evidence_row = _embedded_csv_source_row(
        evidence.get("source_row"),
        GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
        label="geometry bridge OSM evidence",
    )
    if (
        {field: value for field, value in entity.items() if field != "source_row"}
        != _global_geometry_entity_projection(entity_row)
        or {field: value for field, value in evidence.items() if field != "source_row"}
        != _global_geometry_evidence_projection(evidence_row)
    ):
        raise VerifiedConstructionCoreError("geometry bridge OSM projection differs")
    match = re.fullmatch(r"osm:(node|way|relation)/([1-9][0-9]*)", entity["stable_key"])
    if match is None:
        raise VerifiedConstructionCoreError("geometry bridge OSM identity differs")
    osm_type, osm_id = match.group(1), int(match.group(2))
    if (
        {field: entity["source_row"].get(field) for field in ("line", "bytes", "sha256")}
        != {
            "line": 8940,
            "bytes": 1154,
            "sha256": "ef3547df7dba55a747f603c66fdef578b680fa70fab621c731a9f076c73a0884",
        }
        or {
            field: evidence["source_row"].get(field)
            for field in ("line", "bytes", "sha256")
        }
        != {
            "line": 6483,
            "bytes": 334,
            "sha256": "3d22a24cad9f59f7d76bf858a7e9a6586ea4501a2264e09343900928b3831786",
        }
        or entity.get("name") != "STT Jakarta 1"
        or entity.get("latitude") != -6.37400965
        or entity.get("longitude") != 107.20106675
        or entity.get("tags")
        != {
            "building": "yes",
            "name": "STT Jakarta 1",
            "operator": "Singapore Technologies Telemedia",
            "operator:wikidata": "Q138426438",
            "ref": "Jakarta 1",
            "telecom": "data_center",
        }
        or evidence.get("content_hash")
        != "dcf9e3616e24371f0d9b0b49ff61da6ee1a31e4be3484826b967ae8b64357016"
        or not _point_inside_ring(
            [entity.get("longitude"), entity.get("latitude")],
            entity.get("geometry", {}).get("coordinates", [[]])[0],
        )
        or
        entity.get("entity_id")
        != atlas_stable_id("entity", entity["stable_key"], entity["entity_kind"])
        or entity.get("source_url")
        != f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        or entity.get("source_family") != "openstreetmap"
        or entity.get("source_license") != "ODbL-1.0"
        or entity.get("source_attribution") != "© OpenStreetMap contributors"
        or entity.get("status") != "unknown"
        or entity.get("status_method")
        != "osm_geometry_only_no_operational_inference"
        or entity.get("capacity_estimates_json") != []
        or entity.get("workloads_json") != []
        or evidence.get("evidence_id")
        != atlas_stable_id(
            "evidence",
            "osm",
            osm_type,
            str(osm_id),
            evidence.get("retrieved_at"),
            evidence.get("content_hash"),
        )
        or evidence.get("evidence_id") != entity.get("snapshot_evidence_id")
        or evidence.get("source_url") != entity.get("source_url")
        or evidence.get("license") != "ODbL-1.0"
        or evidence.get("attribution") != "© OpenStreetMap contributors"
    ):
        raise VerifiedConstructionCoreError("geometry bridge OSM semantics differ")
    _validate_polygon(entity.get("geometry"), label="geometry bridge OSM")
    rights = bridge.get("rights")
    if (
        not isinstance(rights, dict)
        or rights.get("geometry_license_url")
        != "https://www.openstreetmap.org/copyright"
        or rights.get("geometry_source")
        != "The frozen OSM geometry and object metadata are derived from OpenStreetMap under ODbL 1.0 and require attribution: © OpenStreetMap contributors."
        or rights.get("mixed_rights")
        != "Each upstream source retains its own rights; STT facts are not relicensed under ODbL."
    ):
        raise VerifiedConstructionCoreError("geometry bridge STT rights differ")
    if hydrated_crosscheck:
        for name, record, fields in (
            ("entities.csv", entity, GLOBAL_GEOMETRY_ENTITY_FIELDS),
            ("evidence.csv", evidence, GLOBAL_GEOMETRY_EVIDENCE_FIELDS),
        ):
            metadata = release["members"][name]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], f"geometry bridge OSM {name}"
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"geometry bridge hydrated OSM payload differs: {name}"
                )
            _validate_hydrated_source_row(
                payload_path,
                record["source_row"],
                fields,
                label=f"geometry bridge OSM {name}",
            )


def _validate_v06_kvandal_geometry(bridge: Mapping[str, Any]) -> None:
    release = bridge["geometry_release"]
    if not isinstance(release, dict) or set(release) != {
        "release_id",
        "as_of",
        "recorded_at",
        "capture",
        "upstream_payload",
    }:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal release differs")
    capture_binding = release["capture"]
    if (
        not isinstance(capture_binding, dict)
        or capture_binding
        != {
            "path": "sources/verified-construction-core-v0.6-kvandal-kartverket-wfs-capture.json",
            "bytes": 13990,
            "sha256": "677b6285401124aebccd95f0291987b843aa9866c04f18981fae3f451c4d529e",
        }
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal capture differs")
    capture_path = _repository_input(
        capture_binding["path"], capture_binding["sha256"], "Kvandal WFS capture"
    )
    if capture_path.stat().st_size != capture_binding["bytes"]:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal capture bytes differ")
    capture = _load_json(capture_path)
    raw = capture.get("raw_capture") if isinstance(capture, dict) else None
    if not isinstance(raw, dict) or set(raw) != {
        "content_encoding",
        "transfer_decoding",
        "storage_encoding",
        "bytes",
        "sha256",
        "payload_base64",
    }:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal payload differs")
    try:
        payload = base64.b64decode(raw["payload_base64"], validate=True)
    except (binascii.Error, TypeError) as error:
        raise VerifiedConstructionCoreError(
            "geometry bridge Kvandal payload differs"
        ) from error
    if (
        base64.b64encode(payload).decode("ascii") != raw["payload_base64"]
        or len(payload) != raw["bytes"]
        or _sha256_bytes(payload) != raw["sha256"]
        or raw["bytes"] != 4378
        or raw["sha256"]
        != "8d835fa69725193def708489f681c84bb12c384d71e263fca1739c3c539f997b"
        or release["upstream_payload"]
        != {"encoding": "base64", "bytes": raw["bytes"], "sha256": raw["sha256"]}
        or capture.get("captured_at") != release.get("recorded_at")
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal payload hash differs")
    wfs_namespace = "http://www.opengis.net/wfs/2.0"
    gml_namespace = "http://www.opengis.net/gml/3.2"
    app_namespace = (
        "http://skjema.geonorge.no/SOSI/produktspesifikasjon/"
        "Matrikkelen-Eiendomskart-Teig/20211101"
    )
    namespaces = {"wfs": wfs_namespace, "gml": gml_namespace, "app": app_namespace}
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise VerifiedConstructionCoreError(
            "geometry bridge Kvandal XML differs"
        ) from error
    members = root.findall("wfs:member", namespaces)
    if (
        root.tag != f"{{{wfs_namespace}}}FeatureCollection"
        or len(members) != 1
        or len(members[0]) != 1
        or members[0][0].tag != f"{{{app_namespace}}}Teig"
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal XML member differs")
    teig = members[0][0]

    def one_text(path: str) -> str:
        matches = teig.findall(path, namespaces)
        if len(matches) != 1 or matches[0].text is None:
            raise VerifiedConstructionCoreError(
                "geometry bridge Kvandal XML feature differs"
            )
        return matches[0].text.strip()

    points = teig.findall("app:representasjonspunkt/gml:Point", namespaces)
    polygons = teig.findall("app:område/gml:Polygon", namespaces)
    if len(points) != 1 or len(polygons) != 1:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal XML geometry differs")
    point = points[0]
    polygon = polygons[0]
    point_positions = point.findall("gml:pos", namespaces)
    polygon_positions = polygon.findall(
        "gml:exterior/gml:LinearRing/gml:posList", namespaces
    )
    if len(point_positions) != 1 or len(polygon_positions) != 1:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal XML geometry differs")
    try:
        point_values = [float(value) for value in (point_positions[0].text or "").split()]
        polygon_values = [
            float(value) for value in (polygon_positions[0].text or "").split()
        ]
        stored_area = float(one_text("app:teigareal/app:Areal/app:lagretBeregnetAreal"))
    except ValueError as error:
        raise VerifiedConstructionCoreError(
            "geometry bridge Kvandal XML coordinate differs"
        ) from error
    if len(point_values) != 2 or len(polygon_values) < 8 or len(polygon_values) % 2:
        raise VerifiedConstructionCoreError("geometry bridge Kvandal XML coordinate differs")
    raw_point = {"type": "Point", "coordinates": point_values}
    raw_geometry = {
        "type": "Polygon",
        "coordinates": [
            [polygon_values[index : index + 2] for index in range(0, len(polygon_values), 2)]
        ],
    }
    gml_id = teig.get(f"{{{gml_namespace}}}id")
    teig_id = one_text("app:identTeig/app:IdentTeig/app:teigId")
    if (
        not gml_id
        or gml_id != f"teig.{teig_id}"
        or point.get(f"{{{gml_namespace}}}id")
        != f"{gml_id}_APP_REPRESENTASJONSPUNKT"
        or polygon.get(f"{{{gml_namespace}}}id") != f"{gml_id}_APP_OMRÅDE"
        or point.get("srsName") != "EPSG:4326"
        or polygon.get("srsName") != "EPSG:4326"
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal XML identity differs")
    feature = capture.get("feature")
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    if (
        not isinstance(feature, dict)
        or not isinstance(entity, dict)
        or not isinstance(evidence, dict)
        or capture.get("request", {}).get("parameters", {}).get("service") != "WFS"
        or capture.get("request", {}).get("parameters", {}).get("version") != "2.0.0"
        or capture.get("request", {}).get("parameters", {}).get("request")
        != "GetFeature"
        or capture.get("request", {}).get("parameters", {}).get("typeNames")
        != "app:Teig"
        or capture.get("request", {}).get("parameters", {}).get("srsName")
        != "EPSG:4326"
        or "<fes:Literal>1806</fes:Literal>"
        not in capture.get("request", {}).get("parameters", {}).get("FILTER", "")
        or "<fes:Literal>10/760</fes:Literal>"
        not in capture.get("request", {}).get("parameters", {}).get("FILTER", "")
        or feature.get("gml_id") != gml_id
        or feature.get("teig_id") != teig_id
        or feature.get("uuid_teig") != one_text("app:uuidTeig")
        or feature.get("update_timestamp") != one_text("app:oppdateringsdato")
        or feature.get("municipality_number") != one_text("app:kommunenummer")
        or feature.get("municipality_name") != one_text("app:kommunenavn")
        or feature.get("cadastral_number_text")
        != one_text("app:matrikkelnummerTekst")
        or feature.get("property_type")
        != one_text("app:matrikkelenhet/app:Matrikkelenhet/app:matrikkelenhetstype")
        or str(feature.get("matrikkelenhet_id"))
        != one_text("app:matrikkelenhet/app:Matrikkelenhet/app:matrikkelenhetId")
        or feature.get("uuid_matrikkelenhet")
        != one_text("app:matrikkelenhet/app:Matrikkelenhet/app:uuidMatrikkelenhet")
        or feature.get("stored_calculated_area_square_metres") != stored_area
        or feature.get("accuracy_class_as_published")
        != one_text("app:noyaktighetsklasseTeig")
        or feature.get("coordinate_reference_system") != "EPSG:4326"
        or feature.get("coordinate_order_as_emitted") != "longitude_latitude"
        or feature.get("geometry") != raw_geometry
        or feature.get("geometry") != entity.get("geometry")
        or feature.get("official_representative_point") != raw_point
        or feature.get("official_representative_point")
        != {"type": "Point", "coordinates": [entity["longitude"], entity["latitude"]]}
        or entity.get("stable_key")
        != f"kartverket:matrikkelen-teig/{feature.get('teig_id')}"
        or entity.get("entity_id")
        != atlas_stable_id("entity", entity["stable_key"], "parcel")
        or entity.get("entity_kind") != "parcel"
        or entity.get("tags", {}).get("cadastral_number_text")
        != feature.get("cadastral_number_text")
        or entity.get("source_capture")
        != {
            **capture_binding,
            "raw_payload_bytes": raw["bytes"],
            "raw_payload_sha256": raw["sha256"],
        }
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal feature differs")
    _validate_polygon(entity["geometry"], label="geometry bridge Kvandal")
    if not _point_inside_ring(raw_point["coordinates"], raw_geometry["coordinates"][0]):
        raise VerifiedConstructionCoreError(
            "geometry bridge Kvandal representative point differs"
        )
    expected_evidence_id = atlas_stable_id(
        "evidence",
        "kartverket",
        "teig",
        feature["teig_id"],
        release["recorded_at"],
        raw["sha256"],
    )
    if (
        evidence.get("evidence_id") != expected_evidence_id
        or evidence.get("content_hash") != raw["sha256"]
        or evidence.get("capture_path") != capture_binding["path"]
        or entity.get("snapshot_evidence_id") != expected_evidence_id
        or entity.get("status_evidence_id") != expected_evidence_id
        or evidence.get("source_url") != entity.get("source_url")
        or evidence.get("publisher") != entity.get("source_publisher")
        or evidence.get("license") != "CC-BY-4.0"
        or evidence.get("attribution") != "Kartverket"
        or evidence.get("publisher") != "Kartverket / Statens kartverk"
        or evidence.get("kind") != "government_record"
        or evidence.get("title") != "Kartverket Matrikkelen parcel 1806-10/760"
        or evidence.get("source_family")
        != "kartverket_matrikkelen_eiendomskart_teig_wfs"
        or evidence.get("published_at") != "2026-04-10T07:48:05.975"
        or evidence.get("retrieved_at") != "2026-08-20T19:58:00Z"
        or evidence.get("source_url") != capture.get("request", {}).get("effective_url")
        or entity.get("source_url") != capture.get("request", {}).get("effective_url")
        or entity.get("source_publisher") != capture.get("source", {}).get("publisher")
        or capture.get("source", {}).get("publisher")
        != "Kartverket / Statens kartverk"
        or capture.get("source", {}).get("license") != "CC-BY-4.0"
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal evidence differs")
    rights = bridge.get("rights")
    if (
        not isinstance(rights, dict)
        or rights.get("geometry_license_url")
        != "https://creativecommons.org/licenses/by/4.0/"
        or rights.get("geometry_service_metadata_url")
        != capture.get("source", {}).get("service_metadata_url")
        or rights.get("geometry_dataset_metadata_url")
        != capture.get("source", {}).get("dataset_metadata_url")
        or rights.get("geometry_source")
        != "The exact Kartverket Matrikkelen-Eiendomskart-Teig WFS response and extracted parcel geometry are redistributed under Creative Commons Attribution 4.0 with attribution to Kartverket."
        or rights.get("mixed_rights")
        != "Each upstream source retains its own rights. The CC BY 4.0 geometry license does not relicense Nscale, Sentia, or NVE source-linked material."
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal rights differ")
    identity = bridge["identity_bridge_evidence"]
    if (
        not isinstance(identity, list)
        or len(identity) != 1
        or identity[0].get("map_identity", {}).get(
            "point_inside_captured_parcel_10_760"
        )
        is not True
        or not _point_inside_ring(
            [
                identity[0]["map_identity"]["derived_wgs84_longitude"],
                identity[0]["map_identity"]["derived_wgs84_latitude"],
            ],
            entity["geometry"]["coordinates"][0],
        )
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal identity differs")


def _parcel_union(rings: Sequence[Sequence[Sequence[float]]]) -> list[list[float]]:
    edge_counts: Counter[tuple[tuple[float, float], tuple[float, float]]] = Counter()
    for ring in rings:
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise VerifiedConstructionCoreError("geometry bridge parcel ring differs")
        for first, second in zip(ring, ring[1:]):
            edge = tuple(sorted((tuple(first), tuple(second))))
            edge_counts[edge] += 1
    adjacency: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    for (first, second), count in edge_counts.items():
        if count == 1:
            adjacency[first].add(second)
            adjacency[second].add(first)
        elif count != 2:
            raise VerifiedConstructionCoreError("geometry bridge parcel topology differs")
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise VerifiedConstructionCoreError("geometry bridge parcel union differs")
    start = min(adjacency)
    ring: list[tuple[float, float]] = [start]
    previous: tuple[float, float] | None = None
    current = start
    while True:
        following = sorted(point for point in adjacency[current] if point != previous)[0]
        if following == start:
            ring.append(start)
            break
        if following in ring or len(ring) > len(adjacency):
            raise VerifiedConstructionCoreError("geometry bridge parcel union differs")
        ring.append(following)
        previous, current = current, following
    if len(ring) != len(adjacency) + 1:
        raise VerifiedConstructionCoreError("geometry bridge parcel union differs")
    signed_area = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(ring, ring[1:])
    )
    points = ring[:-1] if signed_area > 0 else list(reversed(ring[:-1]))
    offset = points.index(min(points))
    points = points[offset:] + points[:offset]
    return [list(point) for point in [*points, points[0]]]


def _polygon_area_centroid(
    ring: Sequence[Sequence[float]],
) -> tuple[float, list[float]]:
    origin_x, origin_y = ring[0]
    shifted = [(x - origin_x, y - origin_y) for x, y in ring]
    crosses = [
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(shifted, shifted[1:])
    ]
    area = sum(crosses) / 2
    if area <= 0:
        raise VerifiedConstructionCoreError("geometry bridge parcel area differs")
    centroid_x = origin_x + sum(
        (first[0] + second[0]) * cross
        for first, second, cross in zip(shifted, shifted[1:], crosses)
    ) / (6 * area)
    centroid_y = origin_y + sum(
        (first[1] + second[1]) * cross
        for first, second, cross in zip(shifted, shifted[1:], crosses)
    ) / (6 * area)
    return area, [centroid_x, centroid_y]


def _validate_v06_undheim_geometry(bridge: Mapping[str, Any]) -> None:
    release = bridge["geometry_release"]
    if not isinstance(release, dict) or set(release) != {
        "release_id",
        "as_of",
        "recorded_at",
        "manifest",
        "members",
    }:
        raise VerifiedConstructionCoreError("geometry bridge Undheim release differs")
    manifest_binding = release["manifest"]
    if not isinstance(manifest_binding, dict) or set(manifest_binding) != {
        "path",
        "bytes",
        "sha256",
    }:
        raise VerifiedConstructionCoreError(
            "geometry bridge Undheim capture manifest binding differs"
        )
    manifest_path = _repository_input(
        manifest_binding["path"],
        manifest_binding["sha256"],
        "geometry bridge Undheim capture manifest",
    )
    if manifest_path.stat().st_size != manifest_binding["bytes"]:
        raise VerifiedConstructionCoreError(
            "geometry bridge Undheim capture manifest bytes differ"
        )
    manifest = _load_json(manifest_path)
    manifest_members = manifest.get("members")
    expected_member_facts = {
        "openapi.json": {
            "bytes": 15558,
            "sha256": "933a65c7f47348f4490899f539481d9e88ee3d50b98f3d6531b34321d57d14bc",
            "url": "https://api.kartverket.no/eiendom/v1/openapi.json",
        },
        "1121-46-316-epsg4258.json": {
            "bytes": 1381,
            "sha256": "46c662a0a110ec84b7bbd550852892d975373597341955c5c95feab57445e3ea",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F316&omrade=true&utkoordsys=4258",
        },
        "1121-46-316-epsg25832.json": {
            "bytes": 1509,
            "sha256": "24ab438f6bce9a6656a697c1bf367c4c7042f74b17ae9c4f9db6e0ba8ffde14c",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F316&omrade=true&utkoordsys=25832",
        },
        "1121-46-317-epsg4258.json": {
            "bytes": 1630,
            "sha256": "15533ed85e1f3268feea36417158c8024078dcb61c1770162f19cb22128bfeff",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F317&omrade=true&utkoordsys=4258",
        },
        "1121-46-317-epsg25832.json": {
            "bytes": 1775,
            "sha256": "1d9cf20ac76ae509fe51420f2ca33847565a778c38a19af38fb9cd349947f252",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F317&omrade=true&utkoordsys=25832",
        },
        "1121-46-319-epsg4258.json": {
            "bytes": 944,
            "sha256": "5be1e9b90190df40d27d5b1e640cd736f151e4dd7a5a1d40bf7f58cdf9ced11f",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F319&omrade=true&utkoordsys=4258",
        },
        "1121-46-319-epsg25832.json": {
            "bytes": 1030,
            "sha256": "332139a1c5f55a343fcc23f0e5aa353e81d197404a22026589f68de2179701f0",
            "url": "https://api.kartverket.no/eiendom/v1/geokoding?matrikkelnummer=1121-46%2F319&omrade=true&utkoordsys=25832",
        },
    }
    if (
        manifest_path.name != "manifest.json"
        or not isinstance(manifest_members, dict)
        or set(manifest_members) != set(expected_member_facts)
        or manifest.get("schema_id")
        != "datacenter-atlas-public-api-capture-manifest-v1"
        or manifest.get("capture_id")
        != "verified-construction-core-v0.6-undheim-kartverket-capture"
        or not isinstance(manifest.get("source"), dict)
        or manifest["source"].get("api_base_url")
        != "https://api.kartverket.no/eiendom/v1"
        or manifest["source"].get("license") != "CC-BY-4.0"
        or not isinstance(manifest.get("capture"), dict)
        or manifest["capture"].get("authentication") != "none"
        or manifest["capture"].get("http_status") != 200
        or manifest["capture"].get("last_response_at")
        != release.get("recorded_at")
        or release["members"]
        != {
            name: {field: binding[field] for field in ("path", "bytes", "sha256")}
            for name, binding in manifest_members.items()
        }
        or any(
            binding.get("bytes") != expected_member_facts[name]["bytes"]
            or binding.get("sha256") != expected_member_facts[name]["sha256"]
            or binding.get("url") != expected_member_facts[name]["url"]
            for name, binding in manifest_members.items()
        )
    ):
        raise VerifiedConstructionCoreError("geometry bridge Undheim members differ")
    member_payloads: dict[str, dict[str, Any]] = {}
    for name, binding in release["members"].items():
        path = _repository_input(
            binding["path"], binding["sha256"], f"Undheim capture {name}"
        )
        if path.stat().st_size != binding["bytes"]:
            raise VerifiedConstructionCoreError(
                f"geometry bridge Undheim member bytes differ: {name}"
            )
        member_payloads[name] = _load_json(path)
    display_names = [
        f"1121-46-{number}-epsg4258.json" for number in (316, 317, 319)
    ]
    metric_names = [
        f"1121-46-{number}-epsg25832.json" for number in (316, 317, 319)
    ]
    parcel_facts = {
        316: (6492542413, "2025-07-02T10:05:05"),
        317: (6458360571, "2025-07-01T10:08:08"),
        319: (6461028274, "2025-07-01T09:20:20"),
    }

    def capture_feature(name: str, parcel_number: int, epsg: int) -> dict[str, Any]:
        payload = member_payloads[name]
        features = payload.get("features") if isinstance(payload, dict) else None
        expected_crs = (
            None
            if epsg == 4258
            else {"properties": {"name": "EPSG:25832"}, "type": "name"}
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != ({"features", "type"} if epsg == 4258 else {"crs", "features", "type"})
            or payload.get("type") != "FeatureCollection"
            or payload.get("crs") != expected_crs
            or not isinstance(features, list)
            or len(features) != 1
        ):
            raise VerifiedConstructionCoreError(
                f"geometry bridge Undheim capture differs: {name}"
            )
        feature = features[0]
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        properties = feature.get("properties") if isinstance(feature, dict) else None
        local_id, updated_at = parcel_facts[parcel_number]
        expected_properties = {
            "bruksnummer": parcel_number,
            "festenummer": 0,
            "gardsnummer": 46,
            "hovedområde": True,
            "kommunenummer": "1121",
            "lokalid": local_id,
            "matrikkelnummertekst": f"46/{parcel_number}",
            "nøyaktighetsklasseteig": "Grønt",
            "objekttype": "Teig",
            "oppdateringsdato": updated_at,
            "seksjonsnummer": 0,
            "teigmedflerematrikkelenheter": False,
            "uregistrertjordsameie": False,
        }
        if (
            set(feature) != {"geometry", "properties", "type"}
            or feature.get("type") != "Feature"
            or properties != expected_properties
            or not isinstance(geometry, dict)
        ):
            raise VerifiedConstructionCoreError(
                f"geometry bridge Undheim feature differs: {name}"
            )
        if epsg == 4258:
            _validate_polygon(geometry, label=f"geometry bridge Undheim {name}")
        else:
            coordinates = geometry.get("coordinates")
            ring = coordinates[0] if isinstance(coordinates, list) and len(coordinates) == 1 else None
            if (
                geometry.get("type") != "Polygon"
                or not isinstance(ring, list)
                or len(ring) < 4
                or ring[0] != ring[-1]
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    or not all(_finite_number(value) for value in point)
                    for point in ring
                )
            ):
                raise VerifiedConstructionCoreError(
                    f"geometry bridge Undheim metric geometry differs: {name}"
                )
        return feature

    display_features = [
        capture_feature(name, parcel_number, 4258)
        for name, parcel_number in zip(display_names, (316, 317, 319))
    ]
    metric_features = [
        capture_feature(name, parcel_number, 25832)
        for name, parcel_number in zip(metric_names, (316, 317, 319))
    ]
    for display_feature, metric_feature in zip(display_features, metric_features):
        if display_feature["properties"] != metric_feature["properties"]:
            raise VerifiedConstructionCoreError(
                "geometry bridge Undheim paired feature differs"
            )
    display_ring = _parcel_union(
        [feature["geometry"]["coordinates"][0] for feature in display_features]
    )
    metric_ring = _parcel_union(
        [feature["geometry"]["coordinates"][0] for feature in metric_features]
    )
    area, centroid = _polygon_area_centroid(metric_ring)
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    derivation = entity.get("derivation") if isinstance(entity, dict) else None
    geometry = {"type": "Polygon", "coordinates": [display_ring]}
    metric_geometry = {"type": "Polygon", "coordinates": [metric_ring]}
    canonical_geometry = json.dumps(
        geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    canonical_metric = json.dumps(
        metric_geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if (
        not isinstance(entity, dict)
        or not isinstance(evidence, dict)
        or not isinstance(derivation, dict)
        or entity.get("entity_kind") != "campus"
        or entity.get("geometry") != geometry
        or [entity.get("longitude"), entity.get("latitude")]
        != [5.7940859, 58.6593348]
        or derivation.get("method") != "exact_shared_edge_cancellation_union"
        or derivation.get("display_crs") != 4258
        or derivation.get("metric_crs") != 25832
        or derivation.get("union_geometry_type") != "Polygon"
        or derivation.get("union_ring_vertices_including_closure") != 102
        or derivation.get("area_m2") != round(area, 6)
        or derivation.get("area_m2") != 64015.998576
        or any(
            not math.isclose(actual, expected, abs_tol=1e-9)
            for actual, expected in zip(derivation.get("centroid_epsg25832", []), centroid)
        )
        or derivation.get("centroid_epsg25832")
        != [314041.3340706079, 6506564.987444305]
        or derivation.get("representative_point_epsg4258")
        != [5.7940859, 58.6593348]
        or derivation.get("canonical_geometry_bytes") != len(canonical_geometry)
        or derivation.get("canonical_geometry_sha256")
        != _sha256_bytes(canonical_geometry)
        or derivation.get("canonical_geometry_sha256")
        != "fd26948d9030a8c944e64759e6e9dc3d513969d8a8fe4e82563f75b14ff52c37"
        or derivation.get("canonical_metric_geometry_bytes") != len(canonical_metric)
        or derivation.get("canonical_metric_geometry_sha256")
        != _sha256_bytes(canonical_metric)
        or derivation.get("canonical_metric_geometry_sha256")
        != "de076d1ae86ace9ca28b8eda72e8254e695be68b2b0bdae74255e38c128d7b0c"
        or not _point_inside_ring(
            [entity.get("longitude"), entity.get("latitude")], display_ring
        )
    ):
        raise VerifiedConstructionCoreError("geometry bridge Undheim union differs")
    source_features = entity.get("source_features")
    expected_source_features = []
    for parcel_number in (316, 317, 319):
        local_id = parcel_facts[parcel_number][0]
        for epsg in (4258, 25832):
            member = f"1121-46-{parcel_number}-epsg{epsg}.json"
            binding = expected_member_facts[member]
            expected_source_features.append(
                {
                    "member": member,
                    "json_pointer": "/features/0",
                    "matrikkelnummer": f"1121-46/{parcel_number}",
                    "epsg": epsg,
                    "lokalid": local_id,
                    "response_bytes": binding["bytes"],
                    "response_sha256": binding["sha256"],
                }
            )
    if source_features != expected_source_features:
        raise VerifiedConstructionCoreError("geometry bridge Undheim sources differ")
    for row in source_features:
        binding = release["members"].get(row["member"])
        if binding is None or (
            row.get("response_bytes") != binding["bytes"]
            or row.get("response_sha256") != binding["sha256"]
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Undheim source binding differs"
            )
    capture_set = manifest.get("geometry_capture_set")
    capture_set_payload = {
        "schema": capture_set.get("schema") if isinstance(capture_set, dict) else None,
        "members": {
            name: {
                "bytes": manifest_members[name]["bytes"],
                "sha256": manifest_members[name]["sha256"],
            }
            for name in manifest_members
            if name != "openapi.json"
        },
    }
    canonical_capture_set = json.dumps(
        capture_set_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if (
        not isinstance(capture_set, dict)
        or set(capture_set)
        != {"schema", "member_scope", "canonicalization", "canonical_bytes", "sha256"}
        or capture_set.get("schema")
        != "kartverket-open-property-api-capture-set-v1"
        or capture_set.get("canonical_bytes") != len(canonical_capture_set)
        or capture_set.get("sha256") != _sha256_bytes(canonical_capture_set)
        or capture_set.get("sha256")
        != "6bcd905d036ecde8e55ef4933bf1502f58a58701e5784583fdc3bccc5c6edd1f"
        or evidence.get("content_hash") != capture_set.get("sha256")
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge Undheim evidence hash differs"
        )
    expected_member_order = [
        "1121-46-316-epsg4258.json",
        "1121-46-316-epsg25832.json",
        "1121-46-317-epsg4258.json",
        "1121-46-317-epsg25832.json",
        "1121-46-319-epsg4258.json",
        "1121-46-319-epsg25832.json",
    ]
    manifest_source = manifest["source"]
    if (
        evidence.get("source_members") != expected_member_order
        or evidence.get("license") != "CC-BY-4.0"
        or evidence.get("attribution") != "© Kartverket"
        or evidence.get("publisher") != "Kartverket"
        or evidence.get("kind") != "government_cadastral_api"
        or evidence.get("title")
        != "Kartverket matrikkelteig union 1121-46/316, 1121-46/317 and 1121-46/319"
        or evidence.get("source_family") != "kartverket_open_property_api"
        or evidence.get("published_at") is not None
        or evidence.get("retrieved_at") != "2026-08-20T19:49:51Z"
        or evidence.get("source_url") != manifest_source.get("api_base_url")
        or entity.get("source_url") != manifest_source.get("api_base_url")
        or entity.get("source_publisher") != manifest_source.get("publisher")
        or entity.get("source_license") != manifest_source.get("license")
    ):
        raise VerifiedConstructionCoreError("geometry bridge Undheim evidence differs")
    rights = bridge.get("rights")
    if (
        not isinstance(rights, dict)
        or rights.get("geometry_license_url")
        != "https://www.kartverket.no/en/api-and-data/terms-of-use"
        or rights.get("geometry_source")
        != "The exact Kartverket API response bodies and derived cadastral geometry are redistributed under CC BY 4.0 with attribution: © Kartverket."
        or rights.get("mixed_rights")
        != "Each upstream source retains its own rights; this bridge does not relicense Green Mountain, Time municipality, JoB Arkitekter, or Backe material under CC BY 4.0."
    ):
        raise VerifiedConstructionCoreError("geometry bridge Undheim rights differ")
    constituents = entity.get("constituent_parcels")
    if not isinstance(constituents, list) or len(constituents) != 3:
        raise VerifiedConstructionCoreError(
            "geometry bridge Undheim constituent parcels differ"
        )
    for row, parcel_number, feature in zip(
        constituents, (316, 317, 319), metric_features
    ):
        ring = feature["geometry"]["coordinates"][0]
        origin_x, origin_y = ring[0]
        shifted_ring = [
            [point[0] - origin_x, point[1] - origin_y] for point in ring
        ]
        signed_area = sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(shifted_ring, shifted_ring[1:])
        ) / 2
        local_id, updated_at = parcel_facts[parcel_number]
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "matrikkelnummer",
                "lokalid",
                "oppdateringsdato",
                "nøyaktighetsklasseteig",
                "area_m2",
            }
            or row.get("matrikkelnummer") != f"1121-46/{parcel_number}"
            or row.get("lokalid") != local_id
            or row.get("oppdateringsdato") != updated_at
            or row.get("nøyaktighetsklasseteig") != "Grønt"
            or not math.isclose(
                row.get("area_m2", -1), abs(signed_area), abs_tol=1e-6
            )
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Undheim constituent parcels differ"
            )


def _validate_v06_review_semantics(
    bridge: Mapping[str, Any], project: Mapping[str, Any]
) -> None:
    expected = V06_BRIDGE_SEMANTICS.get(project.get("stable_key"))
    decision = bridge["review_decision"]
    expected_fields = {
        "decision",
        "geometry_target_entity_kind",
        "geometry_derivation",
        "geometry_method",
        "geometry_scope_class",
        "geometry_authority_class",
        "geometry_use_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "identity_basis",
        "precision_scope",
        "rejected_claims",
    }
    if not isinstance(decision, dict) or set(decision) not in {
        frozenset(expected_fields),
        frozenset(expected_fields | {"accepted_claims"}),
    } or expected is None:
        raise VerifiedConstructionCoreError("geometry bridge v0.6 review fields differ")
    if any(
        decision.get(field) != expected[field]
        for field in (
            "decision",
            "geometry_target_entity_kind",
            "geometry_derivation",
            "geometry_method",
            "geometry_scope_class",
            "geometry_authority_class",
            "geometry_use_scope",
            "horizontal_uncertainty_unknown_reason",
        )
    ) or bridge["geometry_entity"].get("stable_key") != expected[
        "geometry_stable_key"
    ]:
        raise VerifiedConstructionCoreError("geometry bridge v0.6 semantics differ")
    rejected = decision.get("rejected_claims")
    if (
        decision.get("horizontal_uncertainty_metres") is not None
        or not isinstance(decision.get("horizontal_uncertainty_unknown_reason"), str)
        or not decision["horizontal_uncertainty_unknown_reason"]
        or not isinstance(decision.get("identity_basis"), str)
        or not decision["identity_basis"]
        or not isinstance(decision.get("precision_scope"), str)
        or not decision["precision_scope"]
        or not isinstance(rejected, list)
        or len(rejected) != len(set(rejected))
        or not any("footprint" in claim for claim in rejected)
        or not any("construction_extent" in claim for claim in rejected)
        or not any("geometry_derived" in claim for claim in rejected)
    ):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 guardrails differ")
    imagery = bridge["imagery_posture"]
    if (
        not isinstance(imagery, dict)
        or not {"outcome", "independent_imagery_verification", "basis"}
        <= set(imagery)
        or imagery.get("outcome") != expected["imagery_outcome"]
        or imagery.get("independent_imagery_verification") is not False
        or not isinstance(imagery.get("basis"), str)
        or not imagery["basis"]
    ):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 imagery differs")
    guardrails = bridge.get("claim_guardrails")
    if guardrails is not None and (
        not isinstance(guardrails, dict)
        or set(guardrails)
        != {"capacity_scope", "energy_scope", "role_scope", "workload_scope"}
        or any(not isinstance(value, str) or not value for value in guardrails.values())
    ):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 claim guardrails differ")


def _validate_v06_identity_evidence(
    bridge: Mapping[str, Any], project: Mapping[str, Any]
) -> None:
    project_key = project.get("stable_key")
    expected_contracts = {
        "curated:adaniconnex-pune-data-center-campus:pnq04-current-build": [],
        "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment": [
            (
                "goodman-hkg09-current-pipeline-address-captured-2026-08-20",
                "goodman_hong_kong_data_centre_pipeline",
                "3b2c00da63973852fd2ede105850be9a439760b06f1f6fa2a2e9718a9abef16f",
            ),
            (
                "hk-landsd-location-search-57-61-ta-chuen-ping-street-captured-2026-08-20",
                "hong_kong_lands_department_location_search_api",
                "69d3478b64d1fd693368ba681e32b8f9bd9cbd1f5dc3b689f1145365c78402ce",
            ),
        ],
        "curated:green-mountain-undheim-campus:current-two-building-development": [
            (
                "time-municipality-case-2025-1487-captured-2026-08-20",
                "time_municipality_public_archive",
                "6fb7fb7c78b8dc083bcd3617cafad6acff9cd8cb98cf456c269b2773d2c130fd",
            ),
            (
                "time-municipality-undheim-permit-vuu1-captured-2026-08-20",
                "time_municipality_public_archive",
                "a8e374f9b26193c9810816fec3edc41854e8cbc69ecd31a5a5bf733dc540b847",
            ),
            (
                "time-municipality-undheim-approved-situation-plan-green-mountain-captured-2026-08-20",
                "time_municipality_public_archive",
                "3e6f0f59d3bd8112f2351f3a45fbce57d1c4b0383fc1798e86279e7a7df27bb2",
            ),
            (
                "time-municipality-undheim-approved-area-overview-green-mountain-captured-2026-08-20",
                "time_municipality_public_archive",
                "b5567fc90c922ced1a1eff3aa0bbf9d8e762538045496f0a1d16fe4a1ffee680",
            ),
            (
                "backe-undheim-green-mountain-contractor-page-captured-2026-08-20",
                "backe_project_pages",
                "5aeecd8c2bdaa189b46dddb6e6366a2f16847cb0e024f575146770efb7f06d86",
            ),
        ],
        "curated:nscale-kvandal-narvik-ai-data-center-campus:initial-25mw-epc-current-build": [
            (
                "nve-202521094-kvandal-two-data-centers-application-captured-2026-08-20",
                "nve_concession_case_files",
                "8ee750f67e722e6d6ea0fdf415eb30140651c020c994ec4596a852793f65c58a",
            )
        ],
        "curated:skygard-osl1-hovinbyen-campus:phase-2": [
            (
                "skygard-osl1-current-page-captured-2026-08-20",
                "skygard_official_facility_page",
                "b6af40e5edbf7edb82fa9ee5c6b97a2342aea9907a4de1c2ca032e8c09aa6f51",
            ),
            (
                "nve-skygard-ostre-aker-vei-24c-case-captured-2026-08-20",
                "nve_concession_cases",
                "8c3c3e1fc35ed9429510a8d93413a25dbe00f12f1017f075997bc13ed6ad0eae",
            ),
        ],
    }
    stt_contract = [
        (
            "stt-jakarta-campus-expansion-2026-06-10-captured-2026-07-19",
            "stt_gdc_newsroom",
            "f56371010a4c86f72e48fec5078c3b0bb8441cf46d97fb43a1e85f52980fc676",
        ),
        (
            "stt-jakarta-1-factsheet-august-2025-captured-2026-08-20",
            "stt_gdc_facility_factsheets",
            "31aed9991d53e01b94ff65b9e06b1bd3ba0f7c3da0ec7a90de8b6a1e5e068f60",
        ),
    ]
    if project_key in {
        f"curated:stt-jakarta-data-centre-campus:stt-jakarta-{number}"
        for number in (3, 5, 6)
    }:
        expected = stt_contract
    else:
        expected = expected_contracts.get(project_key)
    evidence = bridge.get("identity_bridge_evidence")
    if (
        expected is None
        or not isinstance(evidence, list)
        or [
            (item.get("key"), item.get("source_family"), item.get("content_hash"))
            for item in evidence
            if isinstance(item, dict)
        ]
        != expected
        or any(not isinstance(item, dict) for item in evidence)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge v0.6 identity evidence cohort differs"
        )
    by_key = {item["key"]: item for item in evidence}

    def object_field(item: Mapping[str, Any], field: str) -> dict[str, Any]:
        value = item.get(field)
        return value if isinstance(value, dict) else {}

    if project_key and "stt-jakarta-data-centre-campus" in project_key:
        expansion = object_field(by_key[stt_contract[0][0]], "fact_payload")
        factsheet = object_field(by_key[stt_contract[1][0]], "fact_payload")
        if (
            expansion.get("campus_expansion_events")
            != {
                "STT Jakarta 3": "topping out",
                "STT Jakarta 5": "groundbreaking",
                "STT Jakarta 6": "groundbreaking",
            }
            or expansion.get("campus_name_as_reported")
            != "STT Jakarta data centre campus"
            or factsheet.get("facility_name") != "STT Jakarta 1"
            or factsheet.get("campus_relation_as_reported")
            != "Interconnected within the STT Jakarta data centre campus"
            or not str(factsheet.get("location_as_reported", "")).startswith(
                "Block EA-1, Greenland International Industrial Centre"
            )
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge STT identity facts differ"
            )
    elif project_key == "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment":
        goodman = object_field(by_key[expected[0][0]], "fact_payload")
        lands = object_field(by_key[expected[1][0]], "fact_payload")
        selected_result = object_field(lands, "selected_result")
        if (
            goodman.get("facility_code") != "HKG09"
            or goodman.get("address_as_reported")
            != "57-61 Ta Chuen Ping St, Kwai Chung, Hong Kong"
            or lands.get("selected_result_index") != 0
            or selected_result.get("addressEN") != "57-61 TA CHUEN PING STREET  "
            or selected_result.get("x") != 832091.0
            or selected_result.get("y") != 825415.0
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Goodman identity facts differ"
            )
    elif project_key == "curated:skygard-osl1-hovinbyen-campus:phase-2":
        skygard = object_field(by_key[expected[0][0]], "fact_payload")
        nve = object_field(by_key[expected[1][0]], "fact_payload")
        if (
            skygard.get("site_code") != "OSL1"
            or skygard.get("site_label") != "OSL1 - Hovinbyen, Oslo"
            or nve.get("case_number") != "19357"
            or nve.get("case_title") != "Datasenter Østre Aker vei 24C"
            or nve.get("applicant") != "SKYGARD 1 AS"
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Skygard identity facts differ"
            )
    elif project_key == "curated:green-mountain-undheim-campus:current-two-building-development":
        permit = object_field(by_key[expected[1][0]], "extraction")
        situation = object_field(by_key[expected[2][0]], "extraction")
        overview = object_field(by_key[expected[3][0]], "extraction")
        contractor = object_field(by_key[expected[4][0]], "extraction")
        parcels = ["1121-46/316", "1121-46/317", "1121-46/319"]
        if (
            by_key[expected[0][0]].get("case_number") != "2025/1487"
            or permit.get("applicant") != "VUU1 AS"
            or permit.get("permit_parcels") != parcels[1:]
            or situation.get("client_project_owner") != "Green Mountain AS"
            or situation.get("project_parcels") != parcels
            or overview.get("client_project_owner") != "Green Mountain AS"
            or overview.get("project_parcels") != parcels
            or overview.get("reported_parcel_area_sum_m2") != 64016.0
            or contractor.get("client") != "Green Mountain AS"
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Undheim identity facts differ"
            )
    elif project_key == (
        "curated:nscale-kvandal-narvik-ai-data-center-campus:"
        "initial-25mw-epc-current-build"
    ):
        nve = evidence[0]
        case_facts = object_field(nve, "case_facts")
        map_identity = object_field(nve, "map_identity")
        if (
            case_facts.get("nve_case_number") != "202521094"
            or case_facts.get("location")
            != "Skoglund industrial area in Kvandal, north of Bjerkvik, Narvik municipality"
            or map_identity.get("figures") != [3, 4]
            or map_identity.get("source_coordinate_reference_system")
            != "EPSG:25833"
            or map_identity.get("map_center_easting") != 605178.71
            or map_identity.get("map_center_northing") != 7609294.92
            or map_identity.get("derived_wgs84_longitude")
            != 17.580864522839857
            or map_identity.get("derived_wgs84_latitude") != 68.5760344679832
            or map_identity.get("point_inside_captured_parcel_10_760") is not True
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge Kvandal identity facts differ"
            )


def _validate_v06_geometry_bridge(
    path_text: str,
    expected_sha256: str,
    *,
    hydrated_crosscheck: bool,
) -> dict[str, Any]:
    path = _repository_input(path_text, expected_sha256, "geometry bridge")
    bridge = _load_json(path)
    expected_top = {
        "schema_version",
        "bridge_id",
        "reviewed_at",
        "construction_source",
        "identity_bridge_evidence",
        "geometry_release",
        "geometry_entity",
        "geometry_evidence",
        "lineage_context",
        "imagery_posture",
        "review_decision",
        "rights",
    }
    if not isinstance(bridge, dict) or set(bridge) not in {
        frozenset(expected_top),
        frozenset(expected_top | {"claim_guardrails"}),
    }:
        raise VerifiedConstructionCoreError("geometry bridge v0.6 fields differ")
    if (
        bridge.get("schema_version") not in {1, 2}
        or bridge.get("reviewed_at") != REVIEW_DATE.isoformat()
        or not str(bridge.get("bridge_id", "")).startswith(
            "verified-construction-core-v0.6-"
        )
        or bridge.get("lineage_context") is not None
    ):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 identity differs")
    project, campus = _validate_v06_construction_source(
        bridge, hydrated_crosscheck=hydrated_crosscheck
    )
    _validate_v06_review_semantics(bridge, project)
    _validate_v06_identity_evidence(bridge, project)
    geometry_stable_key = bridge["geometry_entity"].get("stable_key")
    if geometry_stable_key == "osm:way/1533569836":
        _validate_v06_osm_geometry(
            bridge, hydrated_crosscheck=hydrated_crosscheck
        )
    elif geometry_stable_key == "kartverket:matrikkelen-teig/6508960482":
        _validate_v06_kvandal_geometry(bridge)
    elif geometry_stable_key == (
        "kartverket:matrikkelteig-union/1121-46/316+317+319"
    ):
        _validate_v06_undheim_geometry(bridge)
    else:
        _validate_v06_official_point_geometry(bridge, project, campus)
    identity_evidence = bridge["identity_bridge_evidence"]
    if not isinstance(identity_evidence, list):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 identity evidence differs")
    for index, evidence in enumerate(identity_evidence):
        if "fact_payload" in evidence:
            _validate_v06_fact_evidence(
                evidence, label=f"geometry bridge identity evidence {index}"
            )
        elif (
            not isinstance(evidence, dict)
            or not isinstance(evidence.get("source_url"), str)
            or not evidence["source_url"]
            or not isinstance(evidence.get("content_hash"), str)
            or re.fullmatch(r"[0-9a-f]{64}", evidence["content_hash"]) is None
        ):
            raise VerifiedConstructionCoreError(
                f"geometry bridge identity evidence {index} differs"
            )
    rights = bridge["rights"]
    base_rights_fields = {
        "construction_source",
        "identity_bridge_evidence",
        "geometry_source",
        "geometry_license_url",
        "lineage_context",
        "mixed_rights",
    }
    kvandal_rights_fields = base_rights_fields | {
        "geometry_service_metadata_url",
        "geometry_dataset_metadata_url",
        "required_attribution",
    }
    if (
        not isinstance(rights, dict)
        or set(rights)
        != (
            kvandal_rights_fields
            if geometry_stable_key == "kartverket:matrikkelen-teig/6508960482"
            else base_rights_fields
        )
        or rights.get("lineage_context") is not None
        or any(
            not isinstance(rights.get(field), str) or not rights[field]
            for field in ("construction_source", "geometry_source", "mixed_rights")
        )
    ):
        raise VerifiedConstructionCoreError("geometry bridge v0.6 rights differ")
    if geometry_stable_key == "kartverket:matrikkelen-teig/6508960482" and (
        "Kartverket" not in str(rights.get("required_attribution"))
        or not all(
            isinstance(rights.get(field), str) and rights[field].startswith("https://")
            for field in (
                "geometry_service_metadata_url",
                "geometry_dataset_metadata_url",
                "geometry_license_url",
            )
        )
    ):
        raise VerifiedConstructionCoreError("geometry bridge Kvandal rights differ")
    if set(_geometry_evidence_projection(bridge)) != set(EVIDENCE_FIELDS) - {
        "roles_json",
        "project_ids_json",
    }:
        raise VerifiedConstructionCoreError(
            "geometry bridge v0.6 evidence projection differs"
        )
    return bridge


def _validate_geometry_bridge(
    path_text: str,
    expected_sha256: str,
    *,
    hydrated_crosscheck: bool,
) -> dict[str, Any]:
    if Path(path_text).stem.startswith("verified-construction-core-v0.6-"):
        return _validate_v06_geometry_bridge(
            path_text,
            expected_sha256,
            hydrated_crosscheck=hydrated_crosscheck,
        )
    return _validate_legacy_geometry_bridge(
        path_text,
        expected_sha256,
        hydrated_crosscheck=hydrated_crosscheck,
    )


def _validate_legacy_geometry_bridge(
    path_text: str,
    expected_sha256: str,
    *,
    hydrated_crosscheck: bool,
) -> dict[str, Any]:
    path = _repository_input(path_text, expected_sha256, "geometry bridge")
    bridge = _load_json(path)
    expected_top = {
        "schema_version",
        "bridge_id",
        "reviewed_at",
        "construction_source",
        "identity_bridge_evidence",
        "geometry_release",
        "geometry_entity",
        "geometry_evidence",
        "lineage_context",
        "imagery_posture",
        "review_decision",
        "rights",
    }
    if not isinstance(bridge, dict) or set(bridge) != expected_top:
        raise VerifiedConstructionCoreError("geometry bridge fields differ")
    if (
        bridge.get("schema_version") != 1
        or bridge.get("bridge_id") != Path(path_text).stem
        or bridge.get("reviewed_at") != REVIEW_DATE.isoformat()
    ):
        raise VerifiedConstructionCoreError("geometry bridge identity differs")

    construction = bridge["construction_source"]
    if not isinstance(construction, dict) or set(construction) != {
        "input",
        "release",
        "project",
        "campus",
        "project_to_campus",
        "status_evidence",
    }:
        raise VerifiedConstructionCoreError("geometry bridge construction source differs")
    source_input = construction["input"]
    if not isinstance(source_input, dict) or set(source_input) != {
        "path",
        "bytes",
        "sha256",
    }:
        raise VerifiedConstructionCoreError("geometry bridge source input differs")
    source_path = _repository_input(
        source_input["path"], source_input["sha256"], "geometry bridge source"
    )
    if source_path.stat().st_size != source_input["bytes"]:
        raise VerifiedConstructionCoreError("geometry bridge source byte count differs")
    source = _load_json(source_path)
    source_project = source.get("project")
    source_campus = source.get("campus")
    source_evidence = source.get("evidence")
    if (
        not isinstance(source_project, dict)
        or not isinstance(source_campus, dict)
        or not isinstance(source_evidence, list)
    ):
        raise VerifiedConstructionCoreError("geometry bridge source record differs")
    project = construction["project"]
    campus = construction["campus"]
    expected_campus_fields = {
        "stable_key",
        "entity_id",
        "name",
        "country",
        "address",
        "operating_model",
        "operating_model_confidence",
        "operating_model_evidence_id",
    }
    if source_project.get("stable_key") == (
        "curated:related-openai-oracle-stargate-michigan-saline:current-build"
    ):
        expected_campus_fields.add("capacity_estimates_json")
    if (
        not isinstance(project, dict)
        or not isinstance(campus, dict)
        or set(project)
        != {
            "stable_key",
            "entity_id",
            "name",
            "country",
            "address",
            "status",
            "status_as_of",
            "status_age_days_at_review",
            "status_method",
            "status_confidence",
            "status_evidence_id",
            "workloads_json",
            "capacity_estimates_json",
        }
        or set(campus) != expected_campus_fields
        or project.get("stable_key") != source_project.get("stable_key")
        or campus.get("stable_key") != source_campus.get("stable_key")
        or project.get("entity_id")
        != atlas_stable_id("entity", source_project.get("stable_key"), "project")
        or campus.get("entity_id")
        != atlas_stable_id("entity", source_campus.get("stable_key"), "campus")
        or project.get("name") != source_project.get("name")
        or campus.get("name") != source_campus.get("name")
        or project.get("country") != source_project.get("country")
        or campus.get("country") != source_campus.get("country")
    ):
        raise VerifiedConstructionCoreError("geometry bridge construction identity differs")
    project_to_campus = construction["project_to_campus"]
    if (
        not isinstance(project_to_campus, dict)
        or set(project_to_campus)
        != {
            "basis",
            "target_entity_id",
            "bundle_id",
            "manifest",
            "members",
            "relationship",
            "subject_member",
            "object_member",
            "supplemental_v97_atlas_feature",
        }
        or project_to_campus.get("target_entity_id") != campus["entity_id"]
        or project_to_campus.get("basis")
        != "v14_project_targets_explicit_parent"
        or project_to_campus.get("bundle_id") != "2026-07-22-public-open-v14"
    ):
        raise VerifiedConstructionCoreError("geometry bridge site relationship differs")
    _validate_bridge_parent_row_bindings(bridge, project["stable_key"])

    release = construction["release"]
    if not isinstance(release, dict) or set(release) != {
        "release_id",
        "manifest",
        "members",
    } or release.get("release_id") != SOURCE_RELEASE_ID:
        raise VerifiedConstructionCoreError("geometry bridge source release differs")
    _, source_manifest = _manifest_binding(
        release["manifest"], label="geometry bridge source release"
    )
    _validate_manifest_members(
        source_manifest, release["members"], label="geometry bridge source release"
    )
    if set(release["members"]) != {
        "construction_pipeline.csv",
        "entities.csv",
        "evidence.csv",
    }:
        raise VerifiedConstructionCoreError("geometry bridge source members differ")

    status_evidence = construction["status_evidence"]
    if not isinstance(status_evidence, dict) or set(status_evidence) != {
        "evidence_id",
        "key",
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "published_at",
        "retrieved_at",
        "content_hash",
    }:
        raise VerifiedConstructionCoreError("geometry bridge status fields differ")
    status_key = status_evidence.get("key") if isinstance(status_evidence, dict) else None
    matches = [
        row
        for row in source_evidence
        if isinstance(row, dict) and row.get("key") == status_key
    ]
    if len(matches) != 1:
        raise VerifiedConstructionCoreError("geometry bridge status evidence differs")
    pinned_status = matches[0]
    expected_status_id = atlas_stable_id(
        "evidence", "curated-official", status_key, pinned_status.get("content_hash")
    )
    lifecycle = [
        row
        for row in source.get("lifecycle", [])
        if isinstance(row, dict) and row.get("entity") == "project"
    ]
    if len(lifecycle) != 1:
        raise VerifiedConstructionCoreError("geometry bridge lifecycle differs")
    latest = lifecycle[0]
    if (
        status_evidence.get("evidence_id") != expected_status_id
        or project.get("status_evidence_id") != expected_status_id
        or project.get("status") != latest.get("value")
        or project.get("status_as_of") != latest.get("as_of_date")
        or project.get("status_method") != latest.get("method")
        or project.get("status_confidence") != latest.get("confidence")
        or project.get("status_age_days_at_review")
        != (REVIEW_DATE - _calendar_date(latest.get("as_of_date"), "bridge status")).days
    ):
        raise VerifiedConstructionCoreError("geometry bridge status projection differs")
    for field in (
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "published_at",
        "retrieved_at",
        "content_hash",
    ):
        if status_evidence.get(field) != pinned_status.get(field):
            raise VerifiedConstructionCoreError("geometry bridge status content differs")

    def projected_evidence_id(evidence_key: Any, label: str) -> str:
        evidence_matches = [
            row
            for row in source_evidence
            if isinstance(row, dict) and row.get("key") == evidence_key
        ]
        if len(evidence_matches) != 1:
            raise VerifiedConstructionCoreError(f"geometry bridge {label} evidence differs")
        return atlas_stable_id(
            "evidence",
            "curated-official",
            evidence_key,
            evidence_matches[0].get("content_hash"),
        )

    def projected_capacities(entity_kind: str) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for observation in source.get("capacities", []):
            if not isinstance(observation, dict):
                raise VerifiedConstructionCoreError(
                    "geometry bridge capacity observation differs"
                )
            if observation.get("entity") != entity_kind:
                continue
            evidence_id = projected_evidence_id(
                observation.get("evidence_key"), "capacity"
            )
            projected.append(
                {
                    **{
                        field: (
                            float(value)
                            if field in {"low", "base", "high"} and value is not None
                            else value
                        )
                        for field, value in observation.items()
                        if field not in {"entity", "evidence_key"}
                    },
                    "evidence_id": evidence_id,
                }
            )
        return sorted(
            projected,
            key=lambda row: (
                row.get("metric", ""),
                row.get("stage", ""),
                row.get("evidence_id", ""),
            ),
        )

    expected_capacity = projected_capacities("project")
    expected_workloads: list[dict[str, Any]] = []
    for observation in source.get("workloads", []):
        if not isinstance(observation, dict):
            raise VerifiedConstructionCoreError(
                "geometry bridge workload observation differs"
            )
        if observation.get("entity") != "project":
            continue
        evidence_id = projected_evidence_id(
            observation.get("evidence_key"), "workload"
        )
        expected_workloads.append(
            {
                **{
                    ("workload" if field == "value" else field): value
                    for field, value in observation.items()
                    if field not in {"entity", "evidence_key"}
                },
                "evidence_id": evidence_id,
            }
        )
    expected_project = {
        "stable_key": source_project["stable_key"],
        "entity_id": atlas_stable_id(
            "entity", source_project["stable_key"], "project"
        ),
        "name": source_project["name"],
        "country": source_project["country"],
        "address": source_project["address"],
        "status": latest["value"],
        "status_as_of": latest["as_of_date"],
        "status_age_days_at_review": (
            REVIEW_DATE - _calendar_date(latest["as_of_date"], "bridge status")
        ).days,
        "status_method": latest["method"],
        "status_confidence": latest["confidence"],
        "status_evidence_id": expected_status_id,
        "workloads_json": expected_workloads,
        "capacity_estimates_json": expected_capacity,
    }
    campus_models = [
        row
        for row in source.get("operating_models", [])
        if isinstance(row, dict) and row.get("entity") == "campus"
    ]
    if len(campus_models) > 1:
        raise VerifiedConstructionCoreError("geometry bridge campus model differs")
    campus_model = campus_models[0] if campus_models else None
    campus_model_evidence_id = (
        projected_evidence_id(campus_model["evidence_key"], "campus model")
        if campus_model
        else None
    )
    expected_campus: dict[str, Any] = {
        "stable_key": source_campus["stable_key"],
        "entity_id": atlas_stable_id(
            "entity", source_campus["stable_key"], "campus"
        ),
        "name": source_campus["name"],
        "country": source_campus["country"],
        "address": source_campus["address"],
        "operating_model": campus_model["value"] if campus_model else None,
        "operating_model_confidence": (
            campus_model["confidence"] if campus_model else None
        ),
        "operating_model_evidence_id": campus_model_evidence_id,
    }
    expected_campus_capacity = projected_capacities("campus")
    if project["stable_key"] == (
        "curated:related-openai-oracle-stargate-michigan-saline:current-build"
    ):
        if len(expected_campus_capacity) != 2:
            raise VerifiedConstructionCoreError(
                "geometry bridge Saline campus capacity differs"
            )
        for observation in expected_campus_capacity:
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
        expected_campus["capacity_estimates_json"] = expected_campus_capacity
    elif expected_campus_capacity:
        raise VerifiedConstructionCoreError(
            "geometry bridge unexpected campus capacity differs"
        )
    if (
        _json_bytes(project) != _json_bytes(expected_project)
        or _json_bytes(campus) != _json_bytes(expected_campus)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge construction projection differs"
        )

    _, relationship_manifest = _manifest_binding(
        project_to_campus["manifest"], label="geometry bridge topology release"
    )
    if (
        relationship_manifest.get("bundle_id") != project_to_campus["bundle_id"]
        or relationship_manifest.get("format")
        != "datacenter-atlas-exact-identity-decision-bundle-v1"
        or set(project_to_campus["members"])
        != {"component-members.csv", "relationships.csv"}
    ):
        raise VerifiedConstructionCoreError("geometry bridge topology release differs")
    _validate_manifest_members(
        relationship_manifest,
        project_to_campus["members"],
        label="geometry bridge topology release",
    )
    subject_member = project_to_campus["subject_member"]
    object_member = project_to_campus["object_member"]
    _validate_exact_component_projection(
        subject_member,
        entity=project,
        entity_kind="project",
        source_family=pinned_status["source_family"],
        snapshot_evidence_id=expected_status_id,
        label="geometry bridge topology subject",
    )
    _validate_exact_component_projection(
        object_member,
        entity=campus,
        entity_kind="campus",
        source_family=pinned_status["source_family"],
        snapshot_evidence_id=expected_status_id,
        label="geometry bridge topology object",
    )
    relationship = project_to_campus["relationship"]
    if not isinstance(relationship, dict) or set(relationship) != {
        "relationship_id",
        "relationship_type",
        "subject_component_id",
        "subject_kind",
        "object_component_id",
        "object_kind",
        "decision_basis",
        "typed_identity_tokens",
        "source_release_ids",
        "raw_relationship_count",
        "source_row",
    }:
        raise VerifiedConstructionCoreError(
            "geometry bridge topology relationship fields differ"
        )
    relationship_row = _embedded_csv_source_row(
        relationship["source_row"],
        EXACT_RELATIONSHIP_FIELDS,
        label="geometry bridge topology relationship",
    )
    relationship_projection = _exact_relationship_projection(relationship_row)
    actual_relationship_projection = {
        field: value for field, value in relationship.items() if field != "source_row"
    }
    if (
        _json_bytes(actual_relationship_projection)
        != _json_bytes(relationship_projection)
        or relationship["relationship_type"] != "project_targets"
        or relationship["subject_component_id"] != subject_member["component_id"]
        or relationship["subject_kind"] != "project"
        or relationship["object_component_id"] != object_member["component_id"]
        or relationship["object_kind"] != "campus"
        or relationship["decision_basis"] != "explicit_parent"
        or relationship["typed_identity_tokens"] != []
        or relationship["source_release_ids"] != [SOURCE_RELEASE_ID]
        or relationship["raw_relationship_count"] != 1
        or relationship["relationship_id"]
        != _exact_relationship_id(
            relationship["relationship_type"],
            relationship["subject_component_id"],
            relationship["object_component_id"],
        )
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge topology relationship differs"
        )
    supplemental = project_to_campus["supplemental_v97_atlas_feature"]
    if supplemental is not None:
        raise VerifiedConstructionCoreError(
            "geometry bridge supplemental topology must be absent"
        )

    geometry_release = bridge["geometry_release"]
    if not isinstance(geometry_release, dict) or set(geometry_release) != {
        "release_id",
        "as_of",
        "recorded_at",
        "manifest",
        "members",
    } or geometry_release.get("release_id") != "global-open-v3":
        raise VerifiedConstructionCoreError("geometry bridge geometry release differs")
    _, geometry_manifest = _manifest_binding(
        geometry_release["manifest"], label="geometry bridge geometry release"
    )
    if set(geometry_release["members"]) != {"entities.csv", "evidence.csv"}:
        raise VerifiedConstructionCoreError("geometry bridge geometry members differ")
    _validate_manifest_members(
        geometry_manifest,
        geometry_release["members"],
        label="geometry bridge geometry release",
    )

    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    if not isinstance(entity, dict) or not isinstance(evidence, dict):
        raise VerifiedConstructionCoreError("geometry bridge geometry records differ")
    entity_row = _embedded_csv_source_row(
        entity.get("source_row"),
        GLOBAL_GEOMETRY_ENTITY_FIELDS,
        label="geometry bridge entities.csv",
    )
    evidence_row = _embedded_csv_source_row(
        evidence.get("source_row"),
        GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
        label="geometry bridge evidence.csv",
    )
    expected_entity_projection = _global_geometry_entity_projection(entity_row)
    expected_evidence_projection = _global_geometry_evidence_projection(evidence_row)
    actual_entity_projection = {
        field: value
        for field, value in entity.items()
        if field != "source_row"
    }
    actual_evidence_projection = {
        field: value for field, value in evidence.items() if field != "source_row"
    }
    if (
        set(entity)
        != {*expected_entity_projection, "source_row"}
        or _json_bytes(actual_entity_projection)
        != _json_bytes(expected_entity_projection)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge entity source projection differs"
        )
    if (
        set(evidence) != {*expected_evidence_projection, "source_row"}
        or _json_bytes(actual_evidence_projection)
        != _json_bytes(expected_evidence_projection)
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge evidence source projection differs"
        )
    stable_key = entity.get("stable_key")
    osm_match = re.fullmatch(r"osm:(node|way|relation)/([1-9][0-9]*)", str(stable_key))
    osm_type = osm_match.group(1) if osm_match else None
    osm_id = int(osm_match.group(2)) if osm_match else None
    expected_entity_kind = (
        "building"
        if project["stable_key"] == "curated:green-campus-zrh1-lupfig:data-center-4"
        else "facility"
    )
    if (
        not isinstance(stable_key, str)
        or osm_match is None
        or entity.get("entity_kind") != expected_entity_kind
        or entity.get("entity_id")
        != atlas_stable_id("entity", stable_key, expected_entity_kind)
        or entity.get("source_url")
        != f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        or entity.get("source_family") != "openstreetmap"
        or entity.get("source_license") != "ODbL-1.0"
        or entity.get("source_attribution") != "© OpenStreetMap contributors"
        or entity.get("status") != "unknown"
        or entity.get("status_method") != "osm_geometry_only_no_operational_inference"
        or entity.get("operating_model") is not None
        or entity.get("capacity_estimates_json") != []
        or entity.get("workloads_json") != []
    ):
        raise VerifiedConstructionCoreError("geometry bridge OSM entity differs")
    _validate_polygon(entity.get("geometry"), label="geometry bridge")
    for value, lower, upper in (
        (entity.get("latitude"), -90, 90),
        (entity.get("longitude"), -180, 180),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not lower <= value <= upper
        ):
            raise VerifiedConstructionCoreError(
                "geometry bridge representative coordinates differ"
            )
    if (
        evidence.get("evidence_id")
        != atlas_stable_id(
            "evidence",
            "osm",
            osm_type,
            str(osm_id),
            evidence.get("retrieved_at"),
            evidence.get("content_hash"),
        )
        or evidence.get("evidence_id") != entity.get("snapshot_evidence_id")
        or evidence.get("evidence_id") != entity.get("status_evidence_id")
        or evidence.get("source_url") != entity.get("source_url")
        or evidence.get("publisher") != entity.get("source_publisher")
        or evidence.get("source_family") != "openstreetmap"
        or evidence.get("license") != "ODbL-1.0"
        or evidence.get("attribution") != "© OpenStreetMap contributors"
        or not isinstance(evidence.get("published_at"), str)
        or evidence["published_at"][:10] != entity.get("status_as_of")
        or evidence.get("retrieved_at") != entity.get("source_retrieved_at")
    ):
        raise VerifiedConstructionCoreError("geometry bridge OSM evidence differs")
    projection = _geometry_evidence_projection(bridge)
    if set(projection) != set(EVIDENCE_FIELDS) - {"roles_json", "project_ids_json"}:
        raise VerifiedConstructionCoreError("geometry bridge evidence projection differs")

    decision = bridge["review_decision"]
    if not isinstance(decision, dict) or set(decision) != {
        "decision",
        "geometry_target_entity_kind",
        "geometry_derivation",
        "geometry_method",
        "geometry_scope_class",
        "geometry_authority_class",
        "geometry_use_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "identity_basis",
        "precision_scope",
        "rejected_claims",
    }:
        raise VerifiedConstructionCoreError("geometry bridge review fields differ")
    rejected = decision.get("rejected_claims")
    required_rejections = {
        "official_or_cadastral_boundary",
        "project_or_phase_footprint",
        "construction_extent",
        "geometry_derived_lifecycle_or_capacity",
        "imagery_verification",
    }
    if (
        decision.get("decision") != "accepted_as_campus_locator"
        or decision.get("geometry_target_entity_kind") != "campus"
        or decision.get("geometry_derivation") != "cross_source_overlay"
        or not isinstance(decision.get("geometry_method"), str)
        or not decision["geometry_method"]
        or not isinstance(decision.get("geometry_scope_class"), str)
        or not decision["geometry_scope_class"]
        or decision.get("geometry_authority_class") != "community_mapped"
        or decision.get("geometry_use_scope") != "campus_locator"
        or decision.get("horizontal_uncertainty_metres") is not None
        or not isinstance(decision.get("horizontal_uncertainty_unknown_reason"), str)
        or not decision["horizontal_uncertainty_unknown_reason"]
        or not isinstance(decision.get("identity_basis"), str)
        or not decision["identity_basis"]
        or not isinstance(decision.get("precision_scope"), str)
        or not decision["precision_scope"]
        or not isinstance(rejected, list)
        or len(set(rejected)) != len(rejected)
        or not required_rejections <= set(rejected)
    ):
        raise VerifiedConstructionCoreError("geometry bridge review decision differs")
    expected_semantics = BRIDGE_REVIEW_SEMANTICS.get(project["stable_key"])
    if expected_semantics is None or any(
        decision.get(field) != value for field, value in expected_semantics.items()
    ):
        raise VerifiedConstructionCoreError(
            "geometry bridge allowlisted review semantics differ"
        )
    if bridge["lineage_context"] is not None:
        raise VerifiedConstructionCoreError(
            "geometry bridge unbound lineage context must be absent"
        )
    imagery = bridge["imagery_posture"]
    expected_imagery_outcome = BRIDGE_IMAGERY_OUTCOMES.get(project["stable_key"])
    if (
        not isinstance(imagery, dict)
        or set(imagery) != {"outcome", "independent_imagery_verification", "basis"}
        or expected_imagery_outcome is None
        or imagery.get("outcome") != expected_imagery_outcome
        or imagery.get("independent_imagery_verification") is not False
        or not isinstance(imagery.get("basis"), str)
        or not imagery["basis"]
    ):
        raise VerifiedConstructionCoreError("geometry bridge imagery posture differs")
    rights = bridge["rights"]
    if (
        not isinstance(rights, dict)
        or set(rights)
        != {
            "construction_source",
            "identity_bridge_evidence",
            "geometry_source",
            "geometry_license_url",
            "lineage_context",
            "mixed_rights",
        }
        or rights.get("geometry_license_url")
        != "https://www.openstreetmap.org/copyright"
        or "OpenStreetMap contributors" not in str(rights.get("geometry_source"))
        or rights.get("lineage_context") is not None
    ):
        raise VerifiedConstructionCoreError("geometry bridge rights differ")
    _validate_identity_bridge(bridge, project, campus, entity)

    if hydrated_crosscheck:
        for name, record, fields in (
            ("entities.csv", entity, GLOBAL_GEOMETRY_ENTITY_FIELDS),
            ("evidence.csv", evidence, GLOBAL_GEOMETRY_EVIDENCE_FIELDS),
        ):
            metadata = geometry_release["members"][name]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], f"geometry bridge {name}"
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"geometry bridge hydrated payload differs: {name}"
                )
            _validate_hydrated_source_row(
                payload_path,
                record["source_row"],
                fields,
                label=f"geometry bridge {name}",
            )
        topology_members = project_to_campus["members"]
        for name, record, fields in (
            ("relationships.csv", relationship, EXACT_RELATIONSHIP_FIELDS),
            ("component-members.csv", subject_member, EXACT_COMPONENT_FIELDS),
            ("component-members.csv", object_member, EXACT_COMPONENT_FIELDS),
        ):
            metadata = topology_members[name]
            payload_path = _repository_input(
                metadata["path"],
                metadata["sha256"],
                f"geometry bridge topology {name}",
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"geometry bridge hydrated topology differs: {name}"
                )
            _validate_hydrated_source_row(
                payload_path,
                record["source_row"],
                fields,
                label=f"geometry bridge {name}",
            )
    return bridge


def _reviewed_overlays_v04(
    path: Path, *, hydrated_crosscheck: bool
) -> dict[str, Any]:
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "purpose",
        "reviewed_as_of",
        "base_contract",
        "required_fields",
        "allowed_decisions",
        "overlays",
    }:
        raise VerifiedConstructionCoreError("reviewed-overlay contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v2"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or set(reviewed.get("allowed_decisions", []))
        != {"queued", "accepted", "excluded"}
    ):
        raise VerifiedConstructionCoreError("reviewed-overlay contract identity differs")
    expected_base = {
        "path": "definitions/verified-construction-core-reviewed-overlays-v1.json",
        "sha256": V03_OVERLAY_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("reviewed-overlay base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "reviewed-overlay base"
    )
    base = _load_json(base_path)
    base_rows = base.get("overlays") if isinstance(base, dict) else None
    if (
        base.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v1"
        or not isinstance(base_rows, list)
        or any(row.get("decision") == "accepted" for row in base_rows)
    ):
        raise VerifiedConstructionCoreError("reviewed-overlay base differs")
    required = {
        "overlay_id",
        "source_project_stable_key",
        "source_project_entity_id",
        "physical_site_stable_key",
        "physical_site_entity_id",
        "bridge_path",
        "bridge_sha256",
        "decision",
        "decision_reason",
        "reviewed_at",
    }
    if set(reviewed.get("required_fields", [])) != required:
        raise VerifiedConstructionCoreError("reviewed-overlay required fields differ")
    delta = reviewed.get("overlays")
    if not isinstance(delta, list) or len(delta) != 2:
        raise VerifiedConstructionCoreError("reviewed-overlay current cohort differs")
    ids = {row.get("overlay_id") for row in base_rows if isinstance(row, dict)}
    bridges: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(delta):
        if not isinstance(row, dict) or set(row) != required:
            raise VerifiedConstructionCoreError(
                f"reviewed-overlay current row {index} differs"
            )
        overlay_id = row["overlay_id"]
        if (
            not isinstance(overlay_id, str)
            or not overlay_id
            or overlay_id in ids
            or row.get("decision") != "accepted"
            or row.get("reviewed_at") != REVIEW_DATE.isoformat()
            or not isinstance(row.get("decision_reason"), str)
            or not row["decision_reason"]
        ):
            raise VerifiedConstructionCoreError("reviewed-overlay current identity differs")
        ids.add(overlay_id)
        bridge = _validate_geometry_bridge(
            row["bridge_path"],
            row["bridge_sha256"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
        construction = bridge["construction_source"]
        if (
            row["source_project_stable_key"]
            != construction["project"]["stable_key"]
            or row["source_project_entity_id"]
            != construction["project"]["entity_id"]
            or row["physical_site_stable_key"]
            != construction["campus"]["stable_key"]
            or row["physical_site_entity_id"]
            != construction["campus"]["entity_id"]
        ):
            raise VerifiedConstructionCoreError(
                "reviewed-overlay bridge identity differs"
            )
        bridges[overlay_id] = bridge
    return {
        "overlays": [*base_rows, *delta],
        "delta_overlays": delta,
        "bridges_by_overlay_id": bridges,
    }


def _reviewed_overlays_v05(
    path: Path, *, hydrated_crosscheck: bool
) -> dict[str, Any]:
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "purpose",
        "reviewed_as_of",
        "base_contract",
        "required_fields",
        "allowed_decisions",
        "overlays",
    }:
        raise VerifiedConstructionCoreError("reviewed-overlay contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v3"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or set(reviewed.get("allowed_decisions", []))
        != {"queued", "accepted", "excluded"}
    ):
        raise VerifiedConstructionCoreError("reviewed-overlay contract identity differs")
    expected_base = {
        "path": "definitions/verified-construction-core-reviewed-overlays-v2.json",
        "sha256": V04_OVERLAY_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("reviewed-overlay base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "reviewed-overlay base"
    )
    base = _reviewed_overlays_v04(
        base_path, hydrated_crosscheck=hydrated_crosscheck
    )
    required = {
        "overlay_id",
        "source_project_stable_key",
        "source_project_entity_id",
        "physical_site_stable_key",
        "physical_site_entity_id",
        "bridge_path",
        "bridge_sha256",
        "decision",
        "decision_reason",
        "reviewed_at",
    }
    if set(reviewed.get("required_fields", [])) != required:
        raise VerifiedConstructionCoreError("reviewed-overlay required fields differ")
    delta = reviewed.get("overlays")
    if not isinstance(delta, list) or len(delta) != 4:
        raise VerifiedConstructionCoreError("reviewed-overlay current cohort differs")
    ids = {
        row.get("overlay_id")
        for row in base["overlays"]
        if isinstance(row, dict)
    }
    bridges = dict(base["bridges_by_overlay_id"])
    for index, row in enumerate(delta):
        if not isinstance(row, dict) or set(row) != required:
            raise VerifiedConstructionCoreError(
                f"reviewed-overlay current row {index} differs"
            )
        overlay_id = row["overlay_id"]
        if (
            not isinstance(overlay_id, str)
            or not overlay_id
            or overlay_id in ids
            or row.get("decision") != "accepted"
            or row.get("reviewed_at") != REVIEW_DATE.isoformat()
            or not isinstance(row.get("decision_reason"), str)
            or not row["decision_reason"]
        ):
            raise VerifiedConstructionCoreError(
                "reviewed-overlay current identity differs"
            )
        ids.add(overlay_id)
        bridge = _validate_geometry_bridge(
            row["bridge_path"],
            row["bridge_sha256"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
        construction = bridge["construction_source"]
        if (
            row["source_project_stable_key"]
            != construction["project"]["stable_key"]
            or row["source_project_entity_id"]
            != construction["project"]["entity_id"]
            or row["physical_site_stable_key"]
            != construction["campus"]["stable_key"]
            or row["physical_site_entity_id"]
            != construction["campus"]["entity_id"]
        ):
            raise VerifiedConstructionCoreError(
                "reviewed-overlay bridge identity differs"
            )
        bridges[overlay_id] = bridge
    return {
        "overlays": [*base["overlays"], *delta],
        "delta_overlays": delta,
        "bridges_by_overlay_id": bridges,
    }


def _reviewed_overlays(*, hydrated_crosscheck: bool) -> dict[str, Any]:
    reviewed = _load_json(OVERLAY_DEFINITION)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "purpose",
        "reviewed_as_of",
        "base_contract",
        "required_fields",
        "allowed_decisions",
        "overlays",
    }:
        raise VerifiedConstructionCoreError("reviewed-overlay contract fields differ")
    if (
        reviewed.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v4"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
        or set(reviewed.get("allowed_decisions", []))
        != {"queued", "accepted", "excluded"}
    ):
        raise VerifiedConstructionCoreError("reviewed-overlay contract identity differs")
    expected_base = {
        "path": "definitions/verified-construction-core-reviewed-overlays-v3.json",
        "sha256": V05_OVERLAY_DEFINITION_SHA256,
    }
    if reviewed.get("base_contract") != expected_base:
        raise VerifiedConstructionCoreError("reviewed-overlay base pin differs")
    base_path = _repository_input(
        expected_base["path"], expected_base["sha256"], "reviewed-overlay base"
    )
    base = _reviewed_overlays_v05(
        base_path, hydrated_crosscheck=hydrated_crosscheck
    )
    required = {
        "overlay_id",
        "source_project_stable_key",
        "source_project_entity_id",
        "physical_site_stable_key",
        "physical_site_entity_id",
        "bridge_path",
        "bridge_sha256",
        "decision",
        "decision_reason",
        "reviewed_at",
    }
    if set(reviewed.get("required_fields", [])) != required:
        raise VerifiedConstructionCoreError("reviewed-overlay required fields differ")
    delta = reviewed.get("overlays")
    if not isinstance(delta, list) or len(delta) != len(V06_BRIDGE_SEMANTICS):
        raise VerifiedConstructionCoreError("reviewed-overlay current cohort differs")
    ids = {
        row.get("overlay_id")
        for row in base["overlays"]
        if isinstance(row, dict)
    }
    bridges = dict(base["bridges_by_overlay_id"])
    project_keys: set[str] = set()
    for index, row in enumerate(delta):
        if not isinstance(row, dict) or set(row) != required:
            raise VerifiedConstructionCoreError(
                f"reviewed-overlay current row {index} differs"
            )
        overlay_id = row["overlay_id"]
        project_key = row["source_project_stable_key"]
        if (
            not isinstance(overlay_id, str)
            or not overlay_id
            or overlay_id in ids
            or project_key in project_keys
            or project_key not in V06_BRIDGE_SEMANTICS
            or row.get("decision") != "accepted"
            or row.get("reviewed_at") != REVIEW_DATE.isoformat()
            or not isinstance(row.get("decision_reason"), str)
            or not row["decision_reason"]
        ):
            raise VerifiedConstructionCoreError(
                "reviewed-overlay current identity differs"
            )
        ids.add(overlay_id)
        project_keys.add(project_key)
        bridge = _validate_geometry_bridge(
            row["bridge_path"],
            row["bridge_sha256"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
        construction = bridge["construction_source"]
        if (
            row["source_project_stable_key"]
            != construction["project"]["stable_key"]
            or row["source_project_entity_id"]
            != construction["project"]["entity_id"]
            or row["physical_site_stable_key"]
            != construction["campus"]["stable_key"]
            or row["physical_site_entity_id"]
            != construction["campus"]["entity_id"]
        ):
            raise VerifiedConstructionCoreError(
                "reviewed-overlay bridge identity differs"
            )
        bridges[overlay_id] = bridge
    if project_keys != set(V06_BRIDGE_SEMANTICS):
        raise VerifiedConstructionCoreError("reviewed-overlay current cohort differs")
    return {
        "overlays": [*base["overlays"], *delta],
        "delta_overlays": delta,
        "bridges_by_overlay_id": bridges,
    }


def _review_contracts() -> tuple[
    list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]
]:
    acceptances = _reviewed_acceptances()
    overlays = _reviewed_overlays(hydrated_crosscheck=True)
    required = {
        "project_stable_key",
        "physical_site_stable_key",
        "source_input_path",
        "source_input_sha256",
        "geometry_entity",
        "geometry_derivation",
        "geometry_evidence_key",
        "geometry_overlay_id",
        "geometry_method",
        "geometry_scope_class",
        "horizontal_uncertainty_metres",
        "precision_scope",
        "decision_basis",
    }
    keys: set[str] = set()
    source_records: dict[str, dict[str, Any]] = {}
    for index, acceptance in enumerate(acceptances):
        if not isinstance(acceptance, dict) or set(acceptance) != required:
            raise VerifiedConstructionCoreError(
                f"reviewed-site acceptance {index} has unexpected fields"
            )
        key = acceptance["project_stable_key"]
        if key in keys:
            raise VerifiedConstructionCoreError(f"duplicate reviewed project: {key}")
        keys.add(key)
        relative_path = Path(acceptance["source_input_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source path escapes the repository: {relative_path}"
            )
        source_path = ROOT / relative_path
        if not source_path.is_file():
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source is not hydrated: {source_path}"
            )
        if _sha256_file(source_path) != acceptance["source_input_sha256"]:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source hash differs: {source_path}"
            )
        source_record = _load_json(source_path)
        if not isinstance(source_record, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source is not an object: {source_path}"
            )
        project = source_record.get("project")
        campus = source_record.get("campus")
        source_evidence = source_record.get("evidence")
        if not isinstance(project, dict) or not isinstance(campus, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source lacks project/campus: {source_path}"
            )
        if not isinstance(source_evidence, list):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source lacks evidence: {source_path}"
            )
        if project.get("stable_key") != key:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry project identity differs: {source_path}"
            )
        if campus.get("stable_key") != acceptance["physical_site_stable_key"]:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry campus identity differs: {source_path}"
            )
        if acceptance["geometry_overlay_id"] is None:
            geometry_source_record = (
                project if acceptance["geometry_entity"] == "project" else campus
            )
            if geometry_source_record.get("evidence_key") != acceptance[
                "geometry_evidence_key"
            ]:
                raise VerifiedConstructionCoreError(
                    f"reviewed geometry-source evidence differs: {source_path}"
                )
            matching_evidence = [
                row
                for row in source_evidence
                if isinstance(row, dict)
                and row.get("key") == acceptance["geometry_evidence_key"]
            ]
            if len(matching_evidence) != 1:
                raise VerifiedConstructionCoreError(
                    f"reviewed geometry evidence is not unique: {source_path}"
                )
        uncertainty = acceptance["horizontal_uncertainty_metres"]
        if uncertainty is not None and (
            isinstance(uncertainty, bool)
            or not isinstance(uncertainty, (int, float))
            or uncertainty < 0
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry uncertainty is invalid: {source_path}"
            )
        overlay_id = acceptance["geometry_overlay_id"]
        if overlay_id is not None:
            bridge = overlays["bridges_by_overlay_id"].get(overlay_id)
            if bridge is None:
                raise VerifiedConstructionCoreError(
                    f"reviewed geometry overlay is absent: {source_path}"
                )
            _validate_bridge_acceptance_semantics(
                acceptance, bridge, label=f"reviewed geometry {source_path}"
            )
        source_records[key] = source_record
    referenced_overlays = {
        row["geometry_overlay_id"]
        for row in acceptances
        if row["geometry_overlay_id"] is not None
    }
    if referenced_overlays != set(overlays["bridges_by_overlay_id"]):
        raise VerifiedConstructionCoreError("reviewed overlay references differ")
    return acceptances, overlays, source_records


def _first_failure(row: Mapping[str, str], accepted: set[str]) -> str:
    if row.get("entity_kind") != "project":
        return "entity_kind_not_project"
    if row.get("status") not in PHYSICAL_STATUSES:
        return "status_not_physical"
    if row.get("status_method") not in AUTHORITATIVE_STATUS_METHODS:
        return "status_method_not_authoritative"
    try:
        age = (REVIEW_DATE - date.fromisoformat(row["status_as_of"])).days
    except (KeyError, ValueError):
        return "invalid_status_date"
    if age < 0 or age > MAX_STATUS_AGE_DAYS:
        return "status_outside_90_day_window"
    if row.get("stable_key") not in accepted:
        return "not_in_reviewed_site_geometry_allowlist"
    return "selected"


def _imagery_outcome(
    project_key: str,
    default_outcome: str,
    records_by_key: Mapping[str, Mapping[str, Any]],
) -> str:
    record = records_by_key.get(project_key)
    return default_outcome if record is None else str(record["outcome"])


def _direct_geometry_semantics(geometry_type: str) -> tuple[str, str]:
    if geometry_type in {"Polygon", "MultiPolygon"}:
        return "official_source", "official_boundary"
    return "official_source", "reviewed_site_locator"


def _verification_posture(
    geometry_authority_class: str, geometry_use_scope: str
) -> str:
    if (
        geometry_authority_class == "official_source"
        and geometry_use_scope == "official_boundary"
    ):
        return "recent_authoritative_physical_observation_plus_official_boundary"
    return "recent_authoritative_physical_observation_plus_reviewed_site_locator"


def _is_official_boundary(row: Mapping[str, Any]) -> bool:
    return (
        row.get("geometry_authority_class") == "official_source"
        and row.get("geometry_use_scope") == "official_boundary"
    )


def _is_reviewed_locator(row: Mapping[str, Any]) -> bool:
    return row.get("geometry_use_scope") in {
        "reviewed_site_locator",
        "project_locator",
        "campus_locator",
    }


def _point_from_coordinates(coordinates: Any, project_key: str) -> dict[str, Any]:
    if not isinstance(coordinates, dict) or set(coordinates) != {
        "latitude",
        "longitude",
    }:
        raise VerifiedConstructionCoreError(
            f"reviewed coordinates differ: {project_key}"
        )
    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]
    for value, lower, upper in (
        (latitude, -90, 90),
        (longitude, -180, 180),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < lower
            or value > upper
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed coordinates are invalid: {project_key}"
            )
    return {"type": "Point", "coordinates": [longitude, latitude]}


def _resolve_reviewed_geometry(
    acceptance: Mapping[str, Any],
    source_record: Mapping[str, Any],
    project_release_row: Mapping[str, str],
    campus_release_row: Mapping[str, str],
    bridge: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    project_key = acceptance["project_stable_key"]
    entity_kind = acceptance["geometry_entity"]
    source_entity = source_record[entity_kind]
    release_entity = (
        project_release_row if entity_kind == "project" else campus_release_row
    )
    if release_entity.get("entity_kind") != entity_kind:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry release entity differs: {project_key}"
        )
    derivation = acceptance["geometry_derivation"]
    if bridge is not None:
        geometry_entity = bridge["geometry_entity"]
        decision = bridge["review_decision"]
        if (
            decision["geometry_target_entity_kind"] != entity_kind
            or decision["geometry_derivation"] != derivation
            or bridge["construction_source"]["project"]["stable_key"]
            != project_key
            or bridge["construction_source"]["campus"]["stable_key"]
            != acceptance["physical_site_stable_key"]
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry bridge identity differs: {project_key}"
            )
        geometry = geometry_entity["geometry"]
        return geometry, geometry_entity
    if derivation in {"cross_source_overlay", "official_parcel_union"}:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry bridge is absent: {project_key}"
        )
    if derivation == "direct_geometry":
        geometry = source_entity.get("geometry")
        if not isinstance(geometry, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed direct geometry is absent: {project_key}"
            )
        if geometry.get("type") == "Point":
            source_point = _point_from_coordinates(
                source_entity.get("coordinates"), project_key
            )
            if source_point != geometry:
                raise VerifiedConstructionCoreError(
                    f"reviewed point geometry and coordinates differ: {project_key}"
                )
    elif derivation == "coordinates_to_point":
        if source_entity.get("geometry") is not None:
            raise VerifiedConstructionCoreError(
                f"coordinate-derived geometry source is not null: {project_key}"
            )
        geometry = _point_from_coordinates(source_entity.get("coordinates"), project_key)
    else:  # The review-contract parser rejects this before geometry resolution.
        raise VerifiedConstructionCoreError(
            f"reviewed geometry derivation differs: {project_key}"
        )
    if geometry.get("type") not in {"Point", "Polygon", "MultiPolygon"}:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry type differs: {project_key}"
        )
    release_geometry = _parse_json_field(
        release_entity.get("geometry_json", ""), "geometry"
    )
    if release_geometry != geometry:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry no longer matches its pinned source: {project_key}"
        )
    try:
        release_latitude = float(release_entity["latitude"])
        release_longitude = float(release_entity["longitude"])
    except (KeyError, TypeError, ValueError) as error:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry representative coordinates differ: {project_key}"
        ) from error
    if (
        not math.isfinite(release_latitude)
        or not math.isfinite(release_longitude)
        or not -90 <= release_latitude <= 90
        or not -180 <= release_longitude <= 180
    ):
        raise VerifiedConstructionCoreError(
            f"reviewed geometry representative coordinates differ: {project_key}"
        )
    if geometry["type"] == "Point" and geometry["coordinates"] != [
        release_longitude,
        release_latitude,
    ]:
        raise VerifiedConstructionCoreError(
            f"reviewed point coordinates no longer match their pinned source: {project_key}"
        )
    return geometry, release_entity


def _preferred_site_geometry_member(
    members: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    geometry_rank = {"Point": 1, "Polygon": 2, "MultiPolygon": 3}
    semantic_rank = {
        ("official_source", "official_boundary"): 4,
        ("official_source", "reviewed_site_locator"): 3,
        ("official_source", "project_locator"): 3,
        ("official_source", "campus_locator"): 3,
        ("community_mapped", "campus_locator"): 2,
    }
    try:
        highest_semantic_rank = max(
            semantic_rank[
                (row["geometry_authority_class"], row["geometry_use_scope"])
            ]
            for row in members
        )
    except (KeyError, ValueError) as error:
        raise VerifiedConstructionCoreError("preview site geometry rank differs") from error
    candidates = [
        row
        for row in members
        if semantic_rank[
            (row["geometry_authority_class"], row["geometry_use_scope"])
        ]
        == highest_semantic_rank
    ]
    highest_geometry_rank = max(geometry_rank[row["geometry_type"]] for row in candidates)
    candidates = [
        row
        for row in candidates
        if geometry_rank[row["geometry_type"]] == highest_geometry_rank
    ]
    signatures = {
        (row["geometry_json"], str(row["latitude"]), str(row["longitude"]))
        for row in candidates
    }
    if len(signatures) != 1:
        raise VerifiedConstructionCoreError(
            "preview site has conflicting highest-ranked reviewed geometries"
        )
    return candidates[0]


def _final_release_gates(
    sites: Sequence[Mapping[str, Any]], projects: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    country_counts = Counter(row["country"] for row in sites)
    site_count = len(sites)
    non_us_count = sum(row["country_iso_a2"] != "US" for row in sites)
    max_share = max(country_counts.values(), default=0) / site_count if site_count else 0
    imagery_count = sum(
        row["imagery_review_outcome"] != "not_reviewed_for_core_preview"
        for row in projects
    )
    return {
        "site_count": {
            "actual": site_count,
            "required": FINAL_REQUIREMENTS["site_count"],
            "passed": site_count == FINAL_REQUIREMENTS["site_count"],
        },
        "country_count": {
            "actual": len(country_counts),
            "required_minimum": FINAL_REQUIREMENTS["country_count"],
            "passed": len(country_counts) >= FINAL_REQUIREMENTS["country_count"],
        },
        "non_us_site_count": {
            "actual": non_us_count,
            "required_minimum": FINAL_REQUIREMENTS["non_us_site_count"],
            "passed": non_us_count >= FINAL_REQUIREMENTS["non_us_site_count"],
        },
        "maximum_single_country_share": {
            "actual": round(max_share, 6),
            "required_maximum": FINAL_REQUIREMENTS["maximum_single_country_share"],
            "passed": max_share <= FINAL_REQUIREMENTS["maximum_single_country_share"],
        },
        "imagery_outcomes_complete": {
            "actual": imagery_count,
            "required": len(projects),
            "passed": imagery_count == len(projects),
        },
        "blind_review": {
            "sample_size": 0,
            "agreements": 0,
            "required_sample_size": FINAL_REQUIREMENTS["blind_review_sample_size"],
            "required_agreements": FINAL_REQUIREMENTS[
                "blind_review_minimum_agreements"
            ],
            "passed": False,
        },
        "clean_clone_rebuild": {
            "passed": False,
            "reason": CLEAN_CLONE_REBUILD_REASON,
        },
    }


def _build_rows() -> dict[str, Any]:
    _validate_current_definition_pins()
    source_manifest = _verify_source_release()
    acceptances, overlays, source_records = _review_contracts()
    default_imagery_outcome, imagery_records = _imagery_contract()
    provenance = _provenance_contract()
    pipeline = _load_csv(SOURCE_RELEASE / "construction_pipeline.csv")
    entities = _load_csv(SOURCE_RELEASE / "entities.csv")
    evidence_rows = _load_csv(SOURCE_RELEASE / "evidence.csv")

    pipeline_by_key = {row["stable_key"]: row for row in pipeline}
    entities_by_key = {row["stable_key"]: row for row in entities}
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}
    if len(pipeline_by_key) != len(pipeline):
        raise VerifiedConstructionCoreError("source pipeline stable keys are not unique")
    if len(entities_by_key) != len(entities):
        raise VerifiedConstructionCoreError("source entity stable keys are not unique")
    if len(evidence_by_id) != len(evidence_rows):
        raise VerifiedConstructionCoreError("source evidence identifiers are not unique")
    for evidence_id, provenance_evidence in provenance["evidence_rows"].items():
        existing = evidence_by_id.get(evidence_id)
        if existing is not None and existing != provenance_evidence:
            raise VerifiedConstructionCoreError(
                "source and provenance evidence differ"
            )
        evidence_by_id[evidence_id] = provenance_evidence
    for bridge in overlays["bridges_by_overlay_id"].values():
        geometry_evidence = _geometry_evidence_projection(bridge)
        evidence_id = geometry_evidence["evidence_id"]
        existing = evidence_by_id.get(evidence_id)
        if existing is not None and existing != geometry_evidence:
            raise VerifiedConstructionCoreError(
                "source and bridge geometry evidence differ"
            )
        evidence_by_id[evidence_id] = geometry_evidence
    accepted_keys = {row["project_stable_key"] for row in acceptances}
    imagery_by_key = {row["project_stable_key"]: row for row in imagery_records}
    if not set(imagery_by_key) <= accepted_keys:
        raise VerifiedConstructionCoreError(
            "imagery-review contract references a non-selected project"
        )
    reason_counts = Counter(_first_failure(row, accepted_keys) for row in pipeline)

    projects: list[dict[str, Any]] = []
    acceptance_by_key = {row["project_stable_key"]: row for row in acceptances}
    evidence_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    workload_bindings = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
        ): row
        for row in provenance["workload_scope_bindings"]
    }
    role_bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    role_exclusions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provenance["role_bindings"]:
        role_bindings[row["project_stable_key"]].append(row)
    for row in provenance["excluded_source_roles"]:
        role_exclusions[row["project_stable_key"]].append(row)
    used_workload_bindings: set[tuple[str, str, str]] = set()
    used_role_bindings: set[tuple[str, str, str]] = set()
    used_role_exclusions: set[tuple[str, str, str]] = set()

    for project_key in sorted(accepted_keys):
        acceptance = acceptance_by_key[project_key]
        source = pipeline_by_key.get(project_key)
        if source is None:
            raise VerifiedConstructionCoreError(f"reviewed project is absent: {project_key}")
        failure = _first_failure(source, accepted_keys)
        if failure != "selected":
            raise VerifiedConstructionCoreError(
                f"reviewed project no longer passes {failure}: {project_key}"
            )
        site_key = acceptance["physical_site_stable_key"]
        site_source = entities_by_key.get(site_key)
        if site_source is None or site_source.get("entity_kind") != "campus":
            raise VerifiedConstructionCoreError(f"reviewed physical site is absent: {site_key}")
        source_record = source_records[project_key]
        bridge = overlays["bridges_by_overlay_id"].get(
            acceptance["geometry_overlay_id"]
        )
        geometry, geometry_release = _resolve_reviewed_geometry(
            acceptance, source_record, source, site_source, bridge
        )
        project_id = source["entity_id"]
        imagery_record = imagery_by_key.get(project_key)
        if imagery_record is not None and imagery_record["project_entity_id"] != project_id:
            raise VerifiedConstructionCoreError(
                f"imagery-review project identity differs: {project_key}"
            )
        site_id = _stable_id("vcc-site", site_key)
        status_evidence_id = source["status_evidence_id"]
        geometry_evidence_id = (
            bridge["geometry_evidence"]["evidence_id"]
            if bridge is not None
            else geometry_release["snapshot_evidence_id"]
        )
        for evidence_id, role in (
            (status_evidence_id, "physical_status"),
            (geometry_evidence_id, "geometry"),
        ):
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"project references absent {role} evidence: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add(role)
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        pinned_geometry_evidence = (
            _geometry_evidence_projection(bridge)
            if bridge is not None
            else next(
                row
                for row in source_record["evidence"]
                if row.get("key") == acceptance["geometry_evidence_key"]
            )
        )
        published_geometry_evidence = evidence_by_id[geometry_evidence_id]
        for field in (
            "kind",
            "title",
            "source_url",
            "publisher",
            "source_family",
            "license",
            "attribution",
            "published_at",
            "retrieved_at",
            "content_hash",
        ):
            pinned_value = pinned_geometry_evidence.get(field)
            if pinned_value is None:
                pinned_value = ""
            if published_geometry_evidence.get(field, "") != pinned_value:
                raise VerifiedConstructionCoreError(
                    f"reviewed geometry evidence field {field} differs: {project_key}"
                )

        observations = _parse_json_field(
            source["capacity_estimates_json"], "capacity_estimates"
        )
        if not isinstance(observations, list):
            raise VerifiedConstructionCoreError("capacity observations are not a list")
        if any(not isinstance(row, dict) for row in observations):
            raise VerifiedConstructionCoreError("capacity observation is not an object")
        for observation in observations:
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
        unexpected_metrics = {
            row.get("metric")
            for row in observations
            if row.get("metric")
            not in POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
        }
        if unexpected_metrics:
            raise VerifiedConstructionCoreError(
                f"unclassified typed metrics {sorted(unexpected_metrics)}: {project_key}"
            )
        power = [row for row in observations if row.get("metric") in POWER_METRICS]
        energy = [row for row in observations if row.get("metric") in ENERGY_METRICS]
        efficiency = [
            row for row in observations if row.get("metric") in EFFICIENCY_METRICS
        ]
        source_workloads = _parse_json_field(source["workloads_json"], "workloads")
        if not isinstance(source_workloads, list):
            raise VerifiedConstructionCoreError("workloads are not a list")
        if any(not isinstance(row, dict) for row in source_workloads):
            raise VerifiedConstructionCoreError("workload observation is not an object")
        for observation in observations:
            evidence_id = observation.get("evidence_id")
            metric = observation.get("metric")
            if not evidence_id or evidence_id not in evidence_by_id or not metric:
                raise VerifiedConstructionCoreError(
                    f"typed metric evidence is absent: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add(f"typed_metric:{metric}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        workloads: list[dict[str, Any]] = []
        for source_workload in source_workloads:
            _validate_source_workload_observation(source_workload)
            binding_key = (
                project_key,
                source_workload["evidence_id"],
                source_workload["workload"],
            )
            binding = workload_bindings.get(binding_key)
            if binding is None or any(
                source_workload[field] != binding[field]
                for field in SOURCE_WORKLOAD_FIELDS
            ):
                raise VerifiedConstructionCoreError(
                    f"workload provenance is absent or differs: {project_key}"
                )
            workload = {
                **source_workload,
                "deployment_scope": binding["deployment_scope"],
            }
            _validate_workload_observation(workload)
            workloads.append(workload)
            used_workload_bindings.add(binding_key)
            evidence_id = workload["evidence_id"]
            if not evidence_id or evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"workload evidence is absent: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add("workload")
            evidence_usage[evidence_id]["roles"].add(
                f"workload_scope:{workload['deployment_scope']}"
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        operating_model_evidence_id = source["operating_model_evidence_id"]
        if operating_model_evidence_id:
            if operating_model_evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"operating-model evidence is absent: {project_key}"
                )
            evidence_usage[operating_model_evidence_id]["roles"].add(
                "operating_model"
            )
            evidence_usage[operating_model_evidence_id]["project_ids"].add(
                project_id
            )
        source_role_keys: set[tuple[str, str, str]] = set()
        for role, column in ROLE_COLUMNS.items():
            parties = [
                party.strip()
                for party in source[column].split(";")
                if party.strip()
            ]
            if len(parties) != len(set(parties)):
                raise VerifiedConstructionCoreError(
                    f"source role parties are not unique: {project_key}"
                )
            source_role_keys.update((project_key, role, party) for party in parties)
        accepted_role_keys = {
            (project_key, row["role"], row["party"])
            for row in role_bindings.get(project_key, [])
        }
        excluded_role_keys = {
            (project_key, row["role"], row["party"])
            for row in role_exclusions.get(project_key, [])
        }
        if source_role_keys != accepted_role_keys | excluded_role_keys:
            raise VerifiedConstructionCoreError(
                f"source role provenance coverage differs: {project_key}"
            )
        role_claims: list[dict[str, str]] = []
        projected_roles: dict[str, list[str]] = {
            role: [] for role in ROLE_COLUMNS
        }
        for binding in role_bindings.get(project_key, []):
            binding_key = (project_key, binding["role"], binding["party"])
            used_role_bindings.add(binding_key)
            evidence_id = binding["evidence_id"]
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"role evidence is absent: {project_key}"
                )
            role_claims.append(
                {
                    "evidence_id": evidence_id,
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
            )
            projected_roles[binding["role"]].append(binding["party"])
            evidence_usage[evidence_id]["roles"].add(f"role:{binding['role']}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        used_role_exclusions.update(excluded_role_keys)
        role_claims.sort(key=lambda row: (row["role"], row["party"], row["evidence_id"]))
        role_projection = {
            column: "; ".join(sorted(projected_roles[role]))
            for role, column in ROLE_COLUMNS.items()
        }
        status_date = _calendar_date(source["status_as_of"], "status_as_of")
        geometry_type = geometry["type"]
        uncertainty = acceptance["horizontal_uncertainty_metres"]
        if bridge is None:
            geometry_authority_class, geometry_use_scope = (
                _direct_geometry_semantics(geometry_type)
            )
            uncertainty_unknown_reason = (
                "official source does not state positional accuracy"
                if uncertainty is None
                else ""
            )
        else:
            decision = bridge["review_decision"]
            geometry_authority_class = decision["geometry_authority_class"]
            geometry_use_scope = decision["geometry_use_scope"]
            uncertainty_unknown_reason = decision[
                "horizontal_uncertainty_unknown_reason"
            ]
        projects.append(
            {
                "project_id": project_id,
                "project_stable_key": project_key,
                "site_id": site_id,
                "physical_site_stable_key": site_key,
                "name": source["name"],
                "country": source["country"],
                "country_iso_a2": source["country_iso_a2"],
                "latitude": geometry_release["latitude"],
                "longitude": geometry_release["longitude"],
                "geometry_json": _json_bytes(geometry).decode().strip(),
                "geometry_type": geometry_type,
                "geometry_source_entity_kind": acceptance["geometry_entity"],
                "geometry_derivation": acceptance["geometry_derivation"],
                "geometry_method": acceptance["geometry_method"],
                "geometry_scope_class": acceptance["geometry_scope_class"],
                "geometry_authority_class": geometry_authority_class,
                "geometry_use_scope": geometry_use_scope,
                "geometry_precision_scope": acceptance["precision_scope"],
                "horizontal_uncertainty_metres": (
                    "" if uncertainty is None else uncertainty
                ),
                "horizontal_uncertainty_unknown_reason": uncertainty_unknown_reason,
                "geometry_evidence_id": geometry_evidence_id,
                "last_observed_physical_status": source["status"],
                "status_as_of": source["status_as_of"],
                "status_age_days_at_review": (REVIEW_DATE - status_date).days,
                "status_method": source["status_method"],
                "status_evidence_id": status_evidence_id,
                "verification_posture": _verification_posture(
                    geometry_authority_class, geometry_use_scope
                ),
                "independent_imagery_verification": "false",
                "imagery_review_outcome": _imagery_outcome(
                    project_key, default_imagery_outcome, imagery_by_key
                ),
                "development_type": "unknown",
                "development_type_unknown_reason": (
                    "source evidence does not distinguish greenfield, expansion, or retrofit"
                ),
                "operating_model": source["operating_model"] or "unknown",
                "operating_model_unknown_reason": (
                    "" if source["operating_model"] else "not established by selected evidence"
                ),
                "operating_model_evidence_id": operating_model_evidence_id,
                "workloads_json": _json_bytes(workloads).decode().strip(),
                "workload_unknown_reason": (
                    "" if workloads else "not established by selected evidence"
                ),
                "role_claims_json": _json_bytes(role_claims).decode().strip(),
                "power_observations_json": _json_bytes(power).decode().strip(),
                "power_unknown_reason": (
                    "" if power else "no typed project power observation; not estimated"
                ),
                "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
                "annual_energy_unknown_reason": (
                    "" if energy else "no scoped annual-energy inputs; not estimated"
                ),
                "efficiency_observations_json": _json_bytes(efficiency)
                .decode()
                .strip(),
                "efficiency_unknown_reason": (
                    "" if efficiency else "no scoped PUE or WUE observation"
                ),
                "owner": role_projection["owner"],
                "operator": role_projection["operator"],
                "users": role_projection["users"],
                "tenants": role_projection["tenants"],
                "customers": role_projection["customers"],
                "status_source_url": evidence_by_id[status_evidence_id]["source_url"],
                "geometry_source_url": evidence_by_id[geometry_evidence_id]["source_url"],
            }
        )

    if used_workload_bindings != set(workload_bindings):
        raise VerifiedConstructionCoreError("workload provenance has unused bindings")
    expected_role_bindings = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in provenance["role_bindings"]
    }
    expected_role_exclusions = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in provenance["excluded_source_roles"]
    }
    if (
        used_role_bindings != expected_role_bindings
        or used_role_exclusions != expected_role_exclusions
    ):
        raise VerifiedConstructionCoreError("role provenance has unused decisions")

    by_site: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        by_site[project["physical_site_stable_key"]].append(project)
    sites: list[dict[str, Any]] = []
    for site_key in sorted(by_site):
        members = sorted(by_site[site_key], key=lambda row: row["project_id"])
        site_source = entities_by_key[site_key]
        geometry_member = _preferred_site_geometry_member(members)
        sites.append(
            {
                "site_id": members[0]["site_id"],
                "physical_site_stable_key": site_key,
                "name": site_source["name"],
                "country": site_source["country"],
                "country_iso_a2": site_source["country_iso_a2"],
                "latitude": geometry_member["latitude"],
                "longitude": geometry_member["longitude"],
                "geometry_json": geometry_member["geometry_json"],
                "geometry_type": geometry_member["geometry_type"],
                "geometry_source_entity_kinds_json": _json_bytes(
                    sorted({row["geometry_source_entity_kind"] for row in members})
                ).decode().strip(),
                "geometry_derivations_json": _json_bytes(
                    sorted({row["geometry_derivation"] for row in members})
                ).decode().strip(),
                "geometry_methods_json": _json_bytes(
                    sorted({row["geometry_method"] for row in members})
                ).decode().strip(),
                "geometry_scope_classes_json": _json_bytes(
                    sorted({row["geometry_scope_class"] for row in members})
                ).decode().strip(),
                "geometry_authority_classes_json": _json_bytes(
                    sorted({row["geometry_authority_class"] for row in members})
                ).decode().strip(),
                "geometry_use_scopes_json": _json_bytes(
                    sorted({row["geometry_use_scope"] for row in members})
                ).decode().strip(),
                "geometry_precision_scopes_json": _json_bytes(
                    sorted({row["geometry_precision_scope"] for row in members})
                ).decode().strip(),
                "horizontal_uncertainty_metres": geometry_member[
                    "horizontal_uncertainty_metres"
                ],
                "horizontal_uncertainty_unknown_reason": geometry_member[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "geometry_evidence_ids_json": _json_bytes(
                    sorted({row["geometry_evidence_id"] for row in members})
                ).decode().strip(),
                "project_count": len(members),
                "project_ids_json": _json_bytes(
                    [row["project_id"] for row in members]
                ).decode().strip(),
                "project_stable_keys_json": _json_bytes(
                    [row["project_stable_key"] for row in members]
                ).decode().strip(),
                "statuses_json": _json_bytes(
                    sorted({row["last_observed_physical_status"] for row in members})
                ).decode().strip(),
                "oldest_status_as_of": min(row["status_as_of"] for row in members),
                "newest_status_as_of": max(row["status_as_of"] for row in members),
                "verification_posture": geometry_member["verification_posture"],
                "independent_imagery_verification": "false",
                "imagery_review_outcomes_json": _json_bytes(
                    sorted({row["imagery_review_outcome"] for row in members})
                ).decode().strip(),
            }
        )

    selected_evidence: list[dict[str, Any]] = []
    for evidence_id in sorted(evidence_usage):
        source = evidence_by_id[evidence_id]
        usage = evidence_usage[evidence_id]
        selected_evidence.append(
            {
                **source,
                "roles_json": _json_bytes(sorted(usage["roles"])).decode().strip(),
                "project_ids_json": _json_bytes(
                    sorted(usage["project_ids"])
                ).decode().strip(),
            }
        )

    country_counts = Counter(row["country"] for row in sites)
    gates = _final_release_gates(sites, projects)
    selection_report = {
        "format": "datacenter-atlas-verified-construction-core-selection-v6",
        "release_status": "preview",
        "publishable_as_final": all(gate.get("passed", False) for gate in gates.values()),
        "source_release_id": SOURCE_RELEASE_ID,
        "reviewed_at": REVIEW_DATE.isoformat(),
        "maximum_status_age_days": MAX_STATUS_AGE_DAYS,
        "source_pipeline_row_count": len(pipeline),
        "selected_project_count": len(projects),
        "selected_physical_site_count": len(sites),
        "official_boundary_project_count": sum(
            _is_official_boundary(row) for row in projects
        ),
        "reviewed_site_locator_project_count": sum(
            _is_reviewed_locator(row) for row in projects
        ),
        "non_selected_source_row_count": len(pipeline) - len(projects),
        "selection_first_failure_counts": dict(sorted(reason_counts.items())),
        "country_counts": dict(sorted(country_counts.items())),
        "final_release_gates": gates,
        "imagery_review_provenance": imagery_records,
        "provenance_decisions": {
            "workload_scope_bindings": provenance["workload_scope_bindings"],
            "role_bindings": provenance["role_bindings"],
            "excluded_source_roles": provenance["excluded_source_roles"],
        },
        "reviewed_overlay_queue": overlays.get("overlays", []),
        "semantic_guardrails": SEMANTIC_GUARDRAILS,
    }
    return {
        "source_manifest": source_manifest,
        "projects": projects,
        "sites": sites,
        "evidence": selected_evidence,
        "selection_report": selection_report,
    }


def _geojson(sites: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "Data Center Atlas Verified Construction Core preview",
        "release_status": "preview",
        "features": [
            {
                "type": "Feature",
                "id": row["site_id"],
                "geometry": json.loads(row["geometry_json"]),
                "properties": {
                    "site_id": row["site_id"],
                    "physical_site_stable_key": row["physical_site_stable_key"],
                    "name": row["name"],
                    "country": row["country"],
                    "project_count": int(row["project_count"]),
                    "geometry_type": row["geometry_type"],
                    "geometry_scope_classes": json.loads(
                        row["geometry_scope_classes_json"]
                    ),
                    "geometry_authority_classes": json.loads(
                        row["geometry_authority_classes_json"]
                    ),
                    "geometry_use_scopes": json.loads(
                        row["geometry_use_scopes_json"]
                    ),
                    "geometry_precision_scopes": json.loads(
                        row["geometry_precision_scopes_json"]
                    ),
                    "horizontal_uncertainty_metres": (
                        None
                        if row["horizontal_uncertainty_metres"] == ""
                        else float(row["horizontal_uncertainty_metres"])
                    ),
                    "statuses": json.loads(row["statuses_json"]),
                    "newest_status_as_of": row["newest_status_as_of"],
                    "verification_posture": row["verification_posture"],
                    "independent_imagery_verification": False,
                },
            }
            for row in sites
        ],
    }


def _map_attribution_notices(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    source_families = {
        str(row.get("source_family", ""))
        for row in evidence
        if "geometry" in json.loads(str(row.get("roles_json", "[]")))
    }
    notices: list[tuple[str, str, str]] = []
    if "openstreetmap" in source_families:
        notices.append(
            (
                "© OpenStreetMap contributors",
                "ODbL 1.0",
                "https://www.openstreetmap.org/copyright",
            )
        )
    if any(source_family.startswith("kartverket_") for source_family in source_families):
        notices.append(
            (
                "© Kartverket",
                "CC BY 4.0",
                "https://www.kartverket.no/en/api-and-data/terms-of-use",
            )
        )
    return tuple(notices)


def _map_html(
    geojson: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
) -> bytes:
    data = json.dumps(geojson, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    site_count = len(geojson.get("features", []))
    attribution = " · ".join(
        f'<a href="{url}">{label}</a> — {license_name}'
        for label, license_name, url in _map_attribution_notices(evidence)
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verified Construction Core preview</title>
<style>body{{font:14px system-ui;margin:0;color:#17202a}}header{{padding:18px 22px;background:#eef4f7}}main{{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:16px;padding:16px}}footer{{padding:0 16px 18px;color:#46545f}}svg{{width:100%;height:auto;background:#f8fafb;border:1px solid #ccd6dc}}.grid{{stroke:#dce4e8;stroke-width:1}}circle{{fill:#b6412e;stroke:#fff;stroke-width:1.5;cursor:pointer}}circle:focus{{outline:2px solid #173b57}}table{{border-collapse:collapse;width:100%}}th,td{{padding:6px;border-bottom:1px solid #ddd;text-align:left}}code{{font-size:12px}}.warning{{color:#7b2d1d;font-weight:700}}@media(max-width:800px){{main{{grid-template-columns:1fr}}}}</style></head>
<body><header><h1>Verified Construction Core v0.6 preview</h1><p class="warning">{site_count} physical sites. This is not the 100-site final release and does not claim independent imagery verification.</p></header>
<main><section><svg id="map" viewBox="0 0 1000 500" role="img" aria-label="Global plot of selected sites"></svg></section><aside><h2 id="name">Select a site</h2><div id="detail"></div><h3>Sites</h3><table><tbody id="rows"></tbody></table></aside></main>
<footer><strong>Map data attribution:</strong> {attribution}. <a href="ATTRIBUTION.txt">Full attribution and source terms</a>.</footer>
<script>const atlas={data};const svg=document.getElementById('map');const ns='http://www.w3.org/2000/svg';
for(let lon=-180;lon<=180;lon+=30){{const l=document.createElementNS(ns,'line');l.setAttribute('x1',(lon+180)/360*1000);l.setAttribute('x2',(lon+180)/360*1000);l.setAttribute('y1',0);l.setAttribute('y2',500);l.setAttribute('class','grid');svg.appendChild(l)}}
for(let lat=-60;lat<=60;lat+=30){{const l=document.createElementNS(ns,'line');l.setAttribute('x1',0);l.setAttribute('x2',1000);l.setAttribute('y1',(90-lat)/180*500);l.setAttribute('y2',(90-lat)/180*500);l.setAttribute('class','grid');svg.appendChild(l)}}
function point(g){{if(g.type==='Point')return g.coordinates;if(g.type==='Polygon'){{const a=g.coordinates[0];return [a.reduce((s,p)=>s+p[0],0)/a.length,a.reduce((s,p)=>s+p[1],0)/a.length]}}const a=g.coordinates[0][0];return [a.reduce((s,p)=>s+p[0],0)/a.length,a.reduce((s,p)=>s+p[1],0)/a.length]}}
function show(f){{document.getElementById('name').textContent=f.properties.name;const d=document.getElementById('detail');d.textContent='';for(const [k,v] of Object.entries(f.properties)){{const p=document.createElement('p');const b=document.createElement('b');b.textContent=k+': ';p.appendChild(b);p.appendChild(document.createTextNode(Array.isArray(v)?v.join(', '):String(v)));d.appendChild(p)}}}}
const tbody=document.getElementById('rows');for(const f of atlas.features){{const [lon,lat]=point(f.geometry);const c=document.createElementNS(ns,'circle');c.setAttribute('cx',(lon+180)/360*1000);c.setAttribute('cy',(90-lat)/180*500);c.setAttribute('r',6);c.setAttribute('tabindex',0);c.setAttribute('aria-label',f.properties.name);c.onclick=()=>show(f);c.onkeydown=e=>{{if(e.key==='Enter')show(f)}};svg.appendChild(c);const tr=document.createElement('tr');const td=document.createElement('td');const a=document.createElement('button');a.textContent=f.properties.name+' — '+f.properties.country;a.onclick=()=>show(f);td.appendChild(a);tr.appendChild(td);tbody.appendChild(tr)}}
</script></body></html>"""
    return document.encode("utf-8")


def _readme(report: Mapping[str, Any]) -> bytes:
    gates = report["final_release_gates"]
    boundary_count = report["official_boundary_project_count"]
    locator_count = report["reviewed_site_locator_project_count"]
    text = f"""# Verified Construction Core v0.6 preview

This tracked preview contains **{report['selected_physical_site_count']} physical sites** and
**{report['selected_project_count']} linked projects** selected from `{SOURCE_RELEASE_ID}`.
Every selected project has a physical-status observation no more than {MAX_STATUS_AGE_DAYS} days
old at the {REVIEW_DATE.isoformat()} review date. {boundary_count} project rows carry official
parcel or surveyed boundary geometry; this describes the geometry attached to the row, not a claim
that construction occupies the entire parcel. The other {locator_count} use explicitly labelled
reviewed locators with their precision limits preserved. Nine selected project rows use
contributor-mapped OSM polygon locators (seven distinct polygons), accepted only as campus locators:
they are not official boundaries, project or phase
footprints, construction extents, or lifecycle evidence. Locality centroids and model-only lifecycle
states fail the selector.

The v0.6 delta adds an official PNQ04 project reference point; official Goodman HKG09 and Skygard
OSL1 campus address/reference points; an official current Kvandal parcel used only as a campus
locator; one shared STT Jakarta 1 OSM campus locator for Jakarta 3, 5, and 6; and the official
three-parcel Undheim project-site union. None of those locator geometries is promoted to a current
building footprint. The Undheim parcel union is an official boundary, but still not a claim that
construction fills the parcels.

This is **not** the final Verified Construction Core v1. It does not change the historical Atlas
`construction_verified=false` field, infer a continuously current state, claim independent imagery
verification, or claim completeness. The final release remains blocked at
{gates['site_count']['actual']}/{gates['site_count']['required']} sites,
{gates['country_count']['actual']}/{gates['country_count']['required_minimum']} countries, and
{gates['non_us_site_count']['actual']}/{gates['non_us_site_count']['required_minimum']} non-US sites.

Files:

- `sites.csv` and `projects.csv`: the reviewed physical-site/project cohort.
- `sites.geojson` and `map.html`: matching clean-clone-readable map products.
- `evidence.csv`: status, geometry, operating-model, workload, and typed-metric evidence.
- `schema.json`: machine-readable field, relationship, GeoJSON, and map contract.
- `selection-report.json`: accounting for every source pipeline row and every final gate.
- `manifest.json` and `manifest.sha256`: byte and SHA-256 bindings.

Missing power, annual energy, operating model, workload, and development type remain explicit
unknowns; the builder never converts missing values to zero. Existing satellite reviews remain
non-claiming analyst evidence. The selection report binds each non-default imagery outcome to its
exact tracked review source and preserves locally unsealed identity lineage and unadjudicated
conflicts explicitly. Two exact Canadian geometry overlays were reviewed but excluded: one recent
scene was unusable and one usable comparison showed no filtered recent-change component.
Backe-published Undheim contractor drone photography is source-linked context only: no image bytes
are redistributed, no independent imagery review is claimed, and it supports no geometry, status,
capacity, progress, or building-count field.

Every workload observation carries a validator-bound `deployment_scope`; all five selected
observations are `intended`, never operational. `role_claims_json` binds each published role to an
evidence ID and relationship scope. Six intended-operator and two intended-customer claims pass
that gate. Four prior CDC/AST owner or operator strings lacked role-specific evidence, so the preview
clears them and preserves the rejected claims and reasons in the provenance contract rather than
laundering status evidence into role evidence. The same conservative rule clears the atNorth,
QScale, Microsoft Mount Pleasant, and Amazon Salem operator candidates; OSM operator tags, campus
operating models, and branded status evidence are identity context, not project-role proof.

Saline's source-level 1,400 MW contracted grid-load observation and modeled annual-energy range are
retained only in the closed bridge as campus-scoped provenance. They are not promoted to project or
site power or energy, and the modeled range is not measured consumption.

The preview validates from a public clean clone. Rebuilding it still requires the locally hydrated
v97 payload, so clean-clone rebuildability is an explicit failed final-release gate rather than an
implied capability.
"""
    return text.encode("utf-8")


def _field_contract(name: str) -> dict[str, Any]:
    json_array_fields = {
        "workloads_json",
        "role_claims_json",
        "power_observations_json",
        "annual_energy_observations_json",
        "efficiency_observations_json",
        "geometry_source_entity_kinds_json",
        "geometry_derivations_json",
        "geometry_methods_json",
        "geometry_scope_classes_json",
        "geometry_authority_classes_json",
        "geometry_use_scopes_json",
        "geometry_precision_scopes_json",
        "geometry_evidence_ids_json",
        "project_ids_json",
        "project_stable_keys_json",
        "statuses_json",
        "imagery_review_outcomes_json",
        "roles_json",
    }
    logical_type = "string"
    if name in json_array_fields:
        logical_type = "json_array"
    elif name == "geometry_json":
        logical_type = "geojson_geometry"
    elif name in {"latitude", "longitude", "horizontal_uncertainty_metres"}:
        logical_type = "number"
    elif name in {"project_count", "status_age_days_at_review"}:
        logical_type = "integer"
    elif name == "independent_imagery_verification":
        logical_type = "boolean"
    elif name in {"status_as_of", "oldest_status_as_of", "newest_status_as_of"}:
        logical_type = "date"
    elif name in {"published_at", "retrieved_at"}:
        logical_type = "date_or_datetime"
    elif name in {"status_source_url", "geometry_source_url", "source_url"}:
        logical_type = "uri"
    elif name == "content_hash":
        logical_type = "sha256"
    allows_empty = name in {
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "operating_model_unknown_reason",
        "operating_model_evidence_id",
        "workload_unknown_reason",
        "power_unknown_reason",
        "annual_energy_unknown_reason",
        "efficiency_unknown_reason",
        "owner",
        "operator",
        "users",
        "tenants",
        "customers",
        "license",
        "attribution",
        "published_at",
    }
    contract: dict[str, Any] = {
        "name": name,
        "logical_type": logical_type,
        "allows_empty_string": allows_empty,
    }
    enumerations = {
        "geometry_type": ["Point", "Polygon", "MultiPolygon"],
        "geometry_source_entity_kind": ["project", "campus"],
        "geometry_derivation": [
            "direct_geometry",
            "coordinates_to_point",
            "cross_source_overlay",
            "official_parcel_union",
        ],
        "geometry_authority_class": ["official_source", "community_mapped"],
        "geometry_use_scope": [
            "official_boundary",
            "reviewed_site_locator",
            "project_locator",
            "campus_locator",
        ],
        "last_observed_physical_status": sorted(PHYSICAL_STATUSES),
        "status_method": sorted(AUTHORITATIVE_STATUS_METHODS),
        "independent_imagery_verification": [False],
    }
    if name in enumerations:
        contract["allowed_values"] = enumerations[name]
    return contract


def _schema() -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-verified-construction-core-schema-v6",
        "preview_id": PREVIEW_ID,
        "csv_encoding": "UTF-8",
        "csv_dialect": {
            "delimiter": ",",
            "quote_character": '"',
            "line_terminator": "LF",
            "header": True,
        },
        "tables": {
            "projects.csv": {
                "fields": [_field_contract(name) for name in PROJECT_FIELDS],
                "primary_key": ["project_id"],
            },
            "sites.csv": {
                "fields": [_field_contract(name) for name in SITE_FIELDS],
                "primary_key": ["site_id"],
            },
            "evidence.csv": {
                "fields": [_field_contract(name) for name in EVIDENCE_FIELDS],
                "primary_key": ["evidence_id"],
            },
        },
        "foreign_keys": [
            {
                "from": ["projects.csv", "site_id"],
                "to": ["sites.csv", "site_id"],
            },
            {
                "from": ["projects.csv", "status_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
            },
            {
                "from": ["projects.csv", "geometry_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
            },
            {
                "from": ["projects.csv", "operating_model_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
                "allows_empty_string": True,
            },
        ],
        "json_embedded_evidence_fields": [
            ["projects.csv", "workloads_json", "evidence_id"],
            ["projects.csv", "role_claims_json", "evidence_id"],
            ["projects.csv", "power_observations_json", "evidence_id"],
            ["projects.csv", "annual_energy_observations_json", "evidence_id"],
            ["projects.csv", "efficiency_observations_json", "evidence_id"],
        ],
        "embedded_array_items": {
            "projects.csv:power_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(POWER_METRICS),
            },
            "projects.csv:annual_energy_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(ENERGY_METRICS),
            },
            "projects.csv:efficiency_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(EFFICIENCY_METRICS),
            },
            "projects.csv:workloads_json": {
                "item_type": "workload_observation"
            },
            "projects.csv:role_claims_json": {
                "item_type": "role_claim"
            },
        },
        "embedded_types": {
            "typed_metric_observation": {
                "required_fields": [
                    "as_of_date",
                    "base",
                    "confidence",
                    "evidence_id",
                    "high",
                    "low",
                    "method",
                    "metric",
                    "notes",
                    "stage",
                    "target_date",
                    "unit",
                ],
                "unit_by_metric": METRIC_UNITS,
                "allowed_methods": sorted(ESTIMATE_METHODS),
                "allowed_stages": sorted(CAPACITY_STAGES),
                "interval_constraint": "0 <= low <= base <= high",
                "confidence_constraint": "0 <= confidence <= 1",
                "target_date_allows_null": True,
            },
            "workload_observation": {
                "required_fields": [
                    "as_of_date",
                    "confidence",
                    "deployment_scope",
                    "evidence_id",
                    "method",
                    "workload",
                ],
                "allowed_deployment_scopes": [
                    "intended",
                    "operational",
                    "unknown",
                ],
                "confidence_constraint": "0 <= confidence <= 1",
            },
            "role_claim": {
                "required_fields": [
                    "evidence_id",
                    "party",
                    "relationship_scope",
                    "role",
                ],
                "allowed_relationship_scopes": [
                    "current",
                    "intended",
                    "unknown",
                ],
                "allowed_roles": sorted(ROLE_COLUMNS),
            },
        },
        "geojson": {
            "path": "sites.geojson",
            "feature_id_equals": ["sites.csv", "site_id"],
            "geometry_equals": ["sites.csv", "geometry_json"],
            "allowed_geometry_types": ["Point", "Polygon", "MultiPolygon"],
        },
        "map": {
            "path": "map.html",
            "derived_from": ["sites.geojson", "evidence.csv"],
        },
    }


def _attribution(
    evidence: Sequence[Mapping[str, Any]],
    overlays: Sequence[Mapping[str, Any]],
    imagery_records: Sequence[Mapping[str, Any]],
) -> bytes:
    rows = {
        (row["publisher"], row["license"], row["source_url"])
        for row in evidence
    }
    if any(row.get("source_family") == "openstreetmap" for row in evidence) or any(
        str(row.get("geometry_stable_key", "")).startswith("osm:")
        for row in overlays
    ):
        rows.add(
            (
                "© OpenStreetMap contributors",
                "ODbL-1.0",
                "https://www.openstreetmap.org/copyright",
            )
        )
    lines = [
        f"Data Center Atlas Verified Construction Core {PREVIEW_ID.rsplit('-', 1)[-1]} preview",
        "",
        "Compact derived facts only; third-party terms remain controlling.",
        "",
    ]
    lines.extend(
        f"- {publisher} | {license_name} | {url}"
        for publisher, license_name, url in sorted(rows)
    )
    if imagery_records:
        lines.extend(
            [
                "",
                "Imagery review attribution:",
                "Contains modified Copernicus Sentinel data 2024 and 2026.",
                "Dataset: Copernicus Sentinel-2 Level-2A, accessed through Element 84 Earth Search.",
                "Sentinel Data Legal Notice: https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
            ]
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_preview(output_dir: Path = PREVIEW_DIR) -> dict[str, Any]:
    """Build the preview atomically and refuse to overwrite an existing path."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise VerifiedConstructionCoreError(f"refusing to overwrite {output_dir}")
    data = _build_rows()
    sites = data["sites"]
    projects = data["projects"]
    evidence = data["evidence"]
    report = data["selection_report"]
    geojson = _geojson(sites)
    payloads = {
        "ATTRIBUTION.txt": _attribution(
            evidence,
            report["reviewed_overlay_queue"],
            report["imagery_review_provenance"],
        ),
        "README.md": _readme(report),
        "evidence.csv": _csv_bytes(evidence, EVIDENCE_FIELDS),
        "map.html": _map_html(geojson, evidence),
        "projects.csv": _csv_bytes(projects, PROJECT_FIELDS),
        "schema.json": _json_bytes(_schema()),
        "selection-report.json": _json_bytes(report),
        "sites.csv": _csv_bytes(sites, SITE_FIELDS),
        "sites.geojson": _json_bytes(geojson),
    }
    manifest = {
        "format": "datacenter-atlas-verified-construction-core-preview-v6",
        "preview_id": PREVIEW_ID,
        "release_status": "preview",
        "publishable_as_final": report["publishable_as_final"],
        "source_release_id": SOURCE_RELEASE_ID,
        "source_release_manifest_path": str(
            (SOURCE_RELEASE / "manifest.json").relative_to(ROOT)
        ),
        "source_release_manifest_sha256": _sha256_file(SOURCE_RELEASE / "manifest.json"),
        "definition_paths": {
            "imagery_reviews": str(IMAGERY_REVIEW_DEFINITION.relative_to(ROOT)),
            "provenance": str(PROVENANCE_DEFINITION.relative_to(ROOT)),
            "reviewed_overlays": str(OVERLAY_DEFINITION.relative_to(ROOT)),
            "reviewed_sites": str(REVIEW_DEFINITION.relative_to(ROOT)),
        },
        "review_definition_sha256": _sha256_file(REVIEW_DEFINITION),
        "imagery_review_definition_sha256": _sha256_file(
            IMAGERY_REVIEW_DEFINITION
        ),
        "provenance_definition_sha256": _sha256_file(PROVENANCE_DEFINITION),
        "overlay_definition_sha256": _sha256_file(OVERLAY_DEFINITION),
        "portable_source_inputs": _portable_source_inputs(),
        "reviewed_at": REVIEW_DATE.isoformat(),
        "counts": {
            "physical_sites": len(sites),
            "projects": len(projects),
            "evidence": len(evidence),
            "countries": len({row["country"] for row in sites}),
            "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
            "official_boundary_projects": sum(
                _is_official_boundary(row) for row in projects
            ),
            "reviewed_site_locator_projects": sum(
                _is_reviewed_locator(row) for row in projects
            ),
        },
        "files": {
            name: {"bytes": len(payload), "sha256": _sha256_bytes(payload)}
            for name, payload in sorted(payloads.items())
        },
    }
    manifest_bytes = _json_bytes(manifest)
    payloads["manifest.json"] = manifest_bytes
    payloads["manifest.sha256"] = (
        f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode()
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, payload in payloads.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(payload)
        os.replace(stage, output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_preview(output_dir)
    return manifest


def _validate_frozen_preview_inventory(
    path: Path,
    *,
    preview_id: str,
    manifest_sha256: str,
    version_label: str,
) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} manifest trust root differs"
        )
    if _sha256_file(manifest_path) != manifest_sha256:
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} manifest hash differs"
        )
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("preview_id") != preview_id:
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} identity differs"
        )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} files map is absent"
        )
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} inventory differs"
        )
    for name, metadata in files.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise VerifiedConstructionCoreError(
                f"frozen {version_label} member differs: {name}"
            )
        candidate = path / name
        if (
            not isinstance(metadata, dict)
            or candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen {version_label} member differs: {name}"
            )
    expected_sum = f"{manifest_sha256}  manifest.json\n"
    if checksum_path.read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError(
            f"frozen {version_label} checksum differs"
        )
    return manifest


def validate_frozen_v01(
    path: Path = LEGACY_PREVIEW_V01_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.1 inventory without applying v0.2 semantics."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.1 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V01_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.1 manifest hash differs")
    manifest = _load_json(manifest_path)
    if (
        manifest.get("format")
        != "datacenter-atlas-verified-construction-core-preview-v1"
        or manifest.get("preview_id") != "2026-08-19-preview-v0.1"
        or manifest.get("reviewed_at") != "2026-08-19"
    ):
        raise VerifiedConstructionCoreError("frozen v0.1 identity differs")
    legacy_definition = (
        ROOT / "definitions" / "verified-construction-core-v0.1-reviewed-sites.json"
    )
    if not legacy_definition.is_file() or manifest.get(
        "review_definition_sha256"
    ) != _sha256_file(legacy_definition):
        raise VerifiedConstructionCoreError("frozen v0.1 review definition differs")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.1 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.1 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.1 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V01_MANIFEST_SHA256}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.1 checksum differs")
    return manifest


def validate_frozen_v02(
    path: Path = LEGACY_PREVIEW_V02_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.2 inventory using only immutable pins."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.2 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V02_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.2 manifest hash differs")
    manifest = _load_json(manifest_path)
    expected_pins = {
        "format": "datacenter-atlas-verified-construction-core-preview-v2",
        "preview_id": "2026-08-20-preview-v0.2",
        "reviewed_at": "2026-08-20",
        "source_release_id": "2026-07-22-open-seed-v97",
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "review_definition_sha256": (
            "13f4d6e82c9057b1dd95319e19e30c2bae0ac0f1848d6e6dee2bbc10b5dde1d0"
        ),
        "imagery_review_definition_sha256": (
            "0516a3281d0a3a1734a4bacb8f8d9e5419d0ae8dc22df36c098c5375f84ee613"
        ),
        "overlay_definition_sha256": (
            "57540f73c5cac475bd8e9e64fc5d8eb2188158ef977b477a0c0e8d7158caf1b7"
        ),
    }
    if any(manifest.get(field) != value for field, value in expected_pins.items()):
        raise VerifiedConstructionCoreError("frozen v0.2 identity differs")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.2 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.2 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.2 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V02_MANIFEST_SHA256}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.2 checksum differs")
    return manifest


def validate_frozen_v03(
    path: Path = LEGACY_PREVIEW_V03_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.3 inventory using only immutable pins."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.3 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V03_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.3 manifest hash differs")
    manifest = _load_json(manifest_path)
    expected_pins = {
        "format": "datacenter-atlas-verified-construction-core-preview-v3",
        "preview_id": "2026-08-20-preview-v0.3",
        "reviewed_at": "2026-08-20",
        "source_release_id": "2026-07-22-open-seed-v97",
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "review_definition_sha256": (
            "ee56ff41dc6ea59df67de6ab462540c8a3fe3747ca3e1504cb9228481c25c06b"
        ),
        "imagery_review_definition_sha256": (
            "eec896bd0c1b26fe95110ab3023e3d713c9ff4c6965412683b4d5e945ad09d7a"
        ),
        "provenance_definition_sha256": (
            "50c3e82d2a9ae6a759b36344e34556ed527027b5c6397153d051adf61dce6561"
        ),
        "overlay_definition_sha256": (
            "57540f73c5cac475bd8e9e64fc5d8eb2188158ef977b477a0c0e8d7158caf1b7"
        ),
    }
    if any(manifest.get(field) != value for field, value in expected_pins.items()):
        raise VerifiedConstructionCoreError("frozen v0.3 identity differs")
    expected_definition_paths = {
        "imagery_reviews": (
            "definitions/verified-construction-core-v0.3-imagery-reviews.json"
        ),
        "provenance": "definitions/verified-construction-core-v0.3-provenance.json",
        "reviewed_overlays": (
            "definitions/verified-construction-core-reviewed-overlays-v1.json"
        ),
        "reviewed_sites": (
            "definitions/verified-construction-core-v0.3-reviewed-sites.json"
        ),
    }
    if manifest.get("definition_paths") != expected_definition_paths:
        raise VerifiedConstructionCoreError("frozen v0.3 definition paths differ")
    definition_hashes = {
        expected_definition_paths["reviewed_sites"]: expected_pins[
            "review_definition_sha256"
        ],
        expected_definition_paths["imagery_reviews"]: expected_pins[
            "imagery_review_definition_sha256"
        ],
        expected_definition_paths["provenance"]: expected_pins[
            "provenance_definition_sha256"
        ],
        expected_definition_paths["reviewed_overlays"]: expected_pins[
            "overlay_definition_sha256"
        ],
        "releases/2026-07-22-open-seed-v97/manifest.json": expected_pins[
            "source_release_manifest_sha256"
        ],
    }
    for relative, expected_sha256 in definition_hashes.items():
        candidate = ROOT / relative
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or _sha256_file(candidate) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.3 repository input differs: {relative}"
            )
    portable = manifest.get("portable_source_inputs")
    if not isinstance(portable, list) or len(portable) != 3:
        raise VerifiedConstructionCoreError("frozen v0.3 portable inputs differ")
    for item in portable:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "bytes",
            "sha256",
            "parent_manifest_path",
            "parent_manifest_sha256",
        }:
            raise VerifiedConstructionCoreError("frozen v0.3 portable input differs")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise VerifiedConstructionCoreError("frozen v0.3 portable path differs")
        candidate = ROOT / relative
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != item["bytes"]
            or _sha256_file(candidate) != item["sha256"]
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.3 portable member differs: {relative}"
            )
        parent_text = item["parent_manifest_path"]
        parent_sha256 = item["parent_manifest_sha256"]
        if parent_text is None:
            if parent_sha256 is not None:
                raise VerifiedConstructionCoreError(
                    "frozen v0.3 portable parent differs"
                )
        else:
            parent = ROOT / parent_text
            if (
                not isinstance(parent_sha256, str)
                or parent.is_symlink()
                or not parent.is_file()
                or _sha256_file(parent) != parent_sha256
            ):
                raise VerifiedConstructionCoreError(
                    "frozen v0.3 portable parent differs"
                )
            parent_manifest = _load_json(parent)
            member_path = str(relative.relative_to(Path(parent_text).parent))
            matches = [
                row
                for row in parent_manifest.get("files", [])
                if isinstance(row, dict) and row.get("path") == member_path
            ]
            if matches != [
                {
                    "path": member_path,
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
            ]:
                raise VerifiedConstructionCoreError(
                    "frozen v0.3 portable parent membership differs"
                )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.3 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.3 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.3 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V03_MANIFEST_SHA256}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.3 checksum differs")
    return manifest


def validate_frozen_v04(
    path: Path = LEGACY_PREVIEW_V04_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.4 inventory using only immutable pins."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.4 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError(
            "frozen v0.4 manifest trust root differs"
        )
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V04_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.4 manifest hash differs")
    manifest = _load_json(manifest_path)
    expected_pins = {
        "format": "datacenter-atlas-verified-construction-core-preview-v4",
        "preview_id": "2026-08-20-preview-v0.4",
        "reviewed_at": "2026-08-20",
        "source_release_id": "2026-07-22-open-seed-v97",
        "source_release_manifest_path": (
            "releases/2026-07-22-open-seed-v97/manifest.json"
        ),
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "review_definition_sha256": (
            "cc71ed6bc107fa585caf3726f7625fd0fdd982c5699a5e19218bbeb1dec7c97c"
        ),
        "imagery_review_definition_sha256": (
            "897a9cbe1f85dea871a3c267069390d5db7ab1206691068769a14fb0b7882798"
        ),
        "provenance_definition_sha256": (
            "9d51d2e998c6d902a6410dfb3a2ce8dde8ee4b722d483bec65de4fda1d6e636e"
        ),
        "overlay_definition_sha256": (
            "65b01f335e60c1f7a886100089bd3a4fe4da79c074233a49bb60b9b65ab8129f"
        ),
    }
    if any(manifest.get(field) != value for field, value in expected_pins.items()):
        raise VerifiedConstructionCoreError("frozen v0.4 identity differs")
    expected_definition_paths = {
        "imagery_reviews": (
            "definitions/verified-construction-core-v0.4-imagery-reviews.json"
        ),
        "provenance": "definitions/verified-construction-core-v0.4-provenance.json",
        "reviewed_overlays": (
            "definitions/verified-construction-core-reviewed-overlays-v2.json"
        ),
        "reviewed_sites": (
            "definitions/verified-construction-core-v0.4-reviewed-sites.json"
        ),
    }
    if manifest.get("definition_paths") != expected_definition_paths:
        raise VerifiedConstructionCoreError("frozen v0.4 definition paths differ")
    repository_pins = {
        expected_definition_paths["reviewed_sites"]: expected_pins[
            "review_definition_sha256"
        ],
        expected_definition_paths["imagery_reviews"]: expected_pins[
            "imagery_review_definition_sha256"
        ],
        expected_definition_paths["provenance"]: expected_pins[
            "provenance_definition_sha256"
        ],
        expected_definition_paths["reviewed_overlays"]: expected_pins[
            "overlay_definition_sha256"
        ],
        expected_pins["source_release_manifest_path"]: expected_pins[
            "source_release_manifest_sha256"
        ],
    }
    for relative, expected_sha256 in repository_pins.items():
        candidate = ROOT / relative
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or _sha256_file(candidate) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.4 repository input differs: {relative}"
            )
    portable = manifest.get("portable_source_inputs")
    if not isinstance(portable, list) or len(portable) != 4:
        raise VerifiedConstructionCoreError("frozen v0.4 portable inputs differ")
    for item in portable:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "bytes",
            "sha256",
            "parent_manifests",
        }:
            raise VerifiedConstructionCoreError("frozen v0.4 portable input differs")
        relative = Path(item["path"])
        candidate = ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != item["bytes"]
            or _sha256_file(candidate) != item["sha256"]
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.4 portable member differs: {relative}"
            )
        parents = item["parent_manifests"]
        if not isinstance(parents, list):
            raise VerifiedConstructionCoreError("frozen v0.4 portable parents differ")
        for parent in parents:
            if not isinstance(parent, dict) or set(parent) != {"path", "sha256"}:
                raise VerifiedConstructionCoreError(
                    "frozen v0.4 portable parent differs"
                )
            parent_relative = Path(parent["path"])
            parent_path = ROOT / parent_relative
            if (
                parent_relative.is_absolute()
                or ".." in parent_relative.parts
                or parent_path.is_symlink()
                or not parent_path.is_file()
                or _sha256_file(parent_path) != parent["sha256"]
            ):
                raise VerifiedConstructionCoreError(
                    "frozen v0.4 portable parent differs"
                )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.4 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.4 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.4 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V04_MANIFEST_SHA256}  manifest.json\n"
    if checksum_path.read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.4 checksum differs")
    return manifest


def validate_frozen_v05(
    path: Path = LEGACY_PREVIEW_V05_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.5 inventory using only immutable pins."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.5 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError(
            "frozen v0.5 manifest trust root differs"
        )
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V05_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.5 manifest hash differs")
    manifest = _load_json(manifest_path)
    expected_pins = {
        "format": "datacenter-atlas-verified-construction-core-preview-v5",
        "preview_id": "2026-08-20-preview-v0.5",
        "reviewed_at": "2026-08-20",
        "source_release_id": "2026-07-22-open-seed-v97",
        "source_release_manifest_path": (
            "releases/2026-07-22-open-seed-v97/manifest.json"
        ),
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "review_definition_sha256": (
            "ec1c7dfc9f9516567ca2c58e29b631cf11df4bba4212df3fc875d0a4b5236775"
        ),
        "imagery_review_definition_sha256": (
            "90969eb2e15210b7a398ff2cc1a2d12ba1b2aa5213e5f4cfe31021ec71c2b083"
        ),
        "provenance_definition_sha256": (
            "bbd0e4665605e7af6389d6730211d096c737ee038886cfdacf848f87a2ee16af"
        ),
        "overlay_definition_sha256": (
            "d71ce264327ccf523cb7f000d559c0a4953524d0224dbdcc7e91e36d8e4b98c5"
        ),
    }
    if any(manifest.get(field) != value for field, value in expected_pins.items()):
        raise VerifiedConstructionCoreError("frozen v0.5 identity differs")
    expected_definition_paths = {
        "imagery_reviews": (
            "definitions/verified-construction-core-v0.5-imagery-reviews.json"
        ),
        "provenance": "definitions/verified-construction-core-v0.5-provenance.json",
        "reviewed_overlays": (
            "definitions/verified-construction-core-reviewed-overlays-v3.json"
        ),
        "reviewed_sites": (
            "definitions/verified-construction-core-v0.5-reviewed-sites.json"
        ),
    }
    if manifest.get("definition_paths") != expected_definition_paths:
        raise VerifiedConstructionCoreError("frozen v0.5 definition paths differ")
    repository_pins = {
        expected_definition_paths["reviewed_sites"]: expected_pins[
            "review_definition_sha256"
        ],
        expected_definition_paths["imagery_reviews"]: expected_pins[
            "imagery_review_definition_sha256"
        ],
        expected_definition_paths["provenance"]: expected_pins[
            "provenance_definition_sha256"
        ],
        expected_definition_paths["reviewed_overlays"]: expected_pins[
            "overlay_definition_sha256"
        ],
        expected_pins["source_release_manifest_path"]: expected_pins[
            "source_release_manifest_sha256"
        ],
    }
    for relative, expected_sha256 in repository_pins.items():
        candidate = ROOT / relative
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or _sha256_file(candidate) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.5 repository input differs: {relative}"
            )
    portable = manifest.get("portable_source_inputs")
    if not isinstance(portable, list) or len(portable) != 8:
        raise VerifiedConstructionCoreError("frozen v0.5 portable inputs differ")
    for item in portable:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "bytes",
            "sha256",
            "parent_manifests",
        }:
            raise VerifiedConstructionCoreError("frozen v0.5 portable input differs")
        relative = Path(item["path"])
        candidate = ROOT / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != item["bytes"]
            or _sha256_file(candidate) != item["sha256"]
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.5 portable member differs: {relative}"
            )
        parents = item["parent_manifests"]
        if not isinstance(parents, list):
            raise VerifiedConstructionCoreError("frozen v0.5 portable parents differ")
        for parent in parents:
            if not isinstance(parent, dict) or set(parent) != {"path", "sha256"}:
                raise VerifiedConstructionCoreError(
                    "frozen v0.5 portable parent differs"
                )
            parent_relative = Path(parent["path"])
            parent_path = ROOT / parent_relative
            if (
                parent_relative.is_absolute()
                or ".." in parent_relative.parts
                or parent_path.is_symlink()
                or not parent_path.is_file()
                or _sha256_file(parent_path) != parent["sha256"]
            ):
                raise VerifiedConstructionCoreError(
                    "frozen v0.5 portable parent differs"
                )
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.5 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.5 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.5 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V05_MANIFEST_SHA256}  manifest.json\n"
    if checksum_path.read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.5 checksum differs")
    return manifest


def validate_frozen_v06(
    path: Path = LEGACY_PREVIEW_V06_DIR,
) -> dict[str, Any]:
    """Validate byte-frozen v0.6 using only its immutable inventory pins."""
    return _validate_frozen_preview_inventory(
        path,
        preview_id="2026-08-20-preview-v0.6",
        manifest_sha256=(
            "05070fab668b1ddd575745cefe3dc36600cd27b48f90702939229c1372674bd5"
        ),
        version_label="v0.6",
    )


_FROZEN_PREVIEW_VALIDATORS = (
    ("2026-08-19-preview-v0.1", validate_frozen_v01),
    ("2026-08-20-preview-v0.2", validate_frozen_v02),
    ("2026-08-20-preview-v0.3", validate_frozen_v03),
    ("2026-08-20-preview-v0.4", validate_frozen_v04),
    ("2026-08-20-preview-v0.5", validate_frozen_v05),
    ("2026-08-20-preview-v0.6", validate_frozen_v06),
)


def _frozen_preview_validator(
    preview_id: object,
) -> Callable[[Path], dict[str, Any]] | None:
    for frozen_id, validator in _FROZEN_PREVIEW_VALIDATORS:
        if preview_id == frozen_id:
            return validator
    return None


def validate_frozen_preview(path: Path) -> dict[str, Any]:
    """Dispatch a frozen preview through the immutable literal version table."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise VerifiedConstructionCoreError("frozen preview manifest trust root differs")
    manifest = _load_json(manifest_path)
    preview_id = manifest.get("preview_id") if isinstance(manifest, dict) else None
    validator = _frozen_preview_validator(preview_id)
    if validator is None:
        raise VerifiedConstructionCoreError("frozen preview id differs")
    return validator(path)


def validate_preview(path: Path = PREVIEW_DIR) -> dict[str, Any]:
    """Dispatch frozen previews by manifest identity and validate the current one."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(f"preview is not a regular directory: {path}")
    manifest_path = path / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise VerifiedConstructionCoreError("preview manifest trust root differs")
    manifest = _load_json(manifest_path)
    preview_id = manifest.get("preview_id")
    if preview_id == PREVIEW_ID:
        return _validate_current_preview(path)
    validator = _frozen_preview_validator(preview_id)
    if validator is not None:
        return validator(path)
    raise VerifiedConstructionCoreError("preview id differs")


def _validate_current_preview(path: Path) -> dict[str, Any]:
    """Validate the tracked preview without requiring the ignored source corpus."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(f"preview is not a regular directory: {path}")
    _validate_current_definition_pins()
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError("preview manifest trust root differs")
    manifest = _load_json(manifest_path)
    expected_manifest_fields = {
        "format",
        "preview_id",
        "release_status",
        "publishable_as_final",
        "source_release_id",
        "source_release_manifest_path",
        "source_release_manifest_sha256",
        "definition_paths",
        "review_definition_sha256",
        "imagery_review_definition_sha256",
        "provenance_definition_sha256",
        "overlay_definition_sha256",
        "portable_source_inputs",
        "reviewed_at",
        "counts",
        "files",
    }
    if set(manifest) != expected_manifest_fields:
        raise VerifiedConstructionCoreError("preview manifest fields differ")
    if manifest.get("format") != "datacenter-atlas-verified-construction-core-preview-v6":
        raise VerifiedConstructionCoreError("preview format differs")
    if manifest.get("preview_id") != PREVIEW_ID:
        raise VerifiedConstructionCoreError("preview id differs")
    if manifest.get("release_status") != "preview" or manifest.get(
        "publishable_as_final"
    ) is not False:
        raise VerifiedConstructionCoreError("preview promotion posture differs")
    if manifest.get("source_release_id") != SOURCE_RELEASE_ID:
        raise VerifiedConstructionCoreError("preview source release differs")
    if manifest.get("reviewed_at") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("preview review date differs")
    for field, _, expected_sha256 in _current_definition_pins():
        if manifest.get(field) != expected_sha256:
            raise VerifiedConstructionCoreError(f"preview {field} differs")
    expected_definition_paths = {
        "imagery_reviews": str(IMAGERY_REVIEW_DEFINITION.relative_to(ROOT)),
        "provenance": str(PROVENANCE_DEFINITION.relative_to(ROOT)),
        "reviewed_overlays": str(OVERLAY_DEFINITION.relative_to(ROOT)),
        "reviewed_sites": str(REVIEW_DEFINITION.relative_to(ROOT)),
    }
    if manifest.get("definition_paths") != expected_definition_paths:
        raise VerifiedConstructionCoreError("preview definition paths differ")
    source_manifest_path = SOURCE_RELEASE / "manifest.json"
    if (
        manifest.get("source_release_manifest_path")
        != str(source_manifest_path.relative_to(ROOT))
        or not source_manifest_path.is_file()
        or manifest.get(
        "source_release_manifest_sha256"
        )
        != _sha256_file(source_manifest_path)
    ):
        raise VerifiedConstructionCoreError("preview source manifest hash differs")
    if manifest.get("portable_source_inputs") != _portable_source_inputs():
        raise VerifiedConstructionCoreError("preview portable source inputs differ")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("preview files map is absent")
    required_payloads = {
        "ATTRIBUTION.txt",
        "README.md",
        "evidence.csv",
        "map.html",
        "projects.csv",
        "schema.json",
        "selection-report.json",
        "sites.csv",
        "sites.geojson",
    }
    if set(files) != required_payloads:
        raise VerifiedConstructionCoreError("preview payload inventory differs")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    actual_names = {item.name for item in path.iterdir()}
    if actual_names != expected_names:
        raise VerifiedConstructionCoreError("preview closed inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if candidate.is_symlink() or not candidate.is_file():
            raise VerifiedConstructionCoreError(f"preview member differs: {name}")
        if candidate.stat().st_size != metadata.get("bytes"):
            raise VerifiedConstructionCoreError(f"preview member byte count differs: {name}")
        if _sha256_file(candidate) != metadata.get("sha256"):
            raise VerifiedConstructionCoreError(f"preview member hash differs: {name}")
    expected_sum = f"{_sha256_file(manifest_path)}  manifest.json\n"
    if checksum_path.read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("preview manifest checksum differs")

    sites = _load_csv(path / "sites.csv", SITE_FIELDS)
    projects = _load_csv(path / "projects.csv", PROJECT_FIELDS)
    evidence = _load_csv(path / "evidence.csv", EVIDENCE_FIELDS)
    schema = _load_json(path / "schema.json")
    geojson = _load_json(path / "sites.geojson")
    report = _load_json(path / "selection-report.json")
    if schema != _schema():
        raise VerifiedConstructionCoreError("preview machine-readable schema differs")
    counts = manifest.get("counts", {})
    if not isinstance(counts, dict) or set(counts) != {
        "physical_sites",
        "projects",
        "evidence",
        "countries",
        "non_us_sites",
        "official_boundary_projects",
        "reviewed_site_locator_projects",
    }:
        raise VerifiedConstructionCoreError("preview count fields differ")
    if counts.get("physical_sites") != len(sites) or counts.get("projects") != len(
        projects
    ) or counts.get("evidence") != len(evidence):
        raise VerifiedConstructionCoreError("preview manifest counts differ")
    site_ids = {row["site_id"] for row in sites}
    project_ids = {row["project_id"] for row in projects}
    evidence_ids = {row["evidence_id"] for row in evidence}
    if len(site_ids) != len(sites) or len(project_ids) != len(projects):
        raise VerifiedConstructionCoreError("preview identifiers are not unique")
    if any(row["site_id"] not in site_ids for row in projects):
        raise VerifiedConstructionCoreError("preview project references absent site")
    if {row["site_id"] for row in projects} != site_ids:
        raise VerifiedConstructionCoreError("preview contains a site without a project")
    site_by_id = {row["site_id"]: row for row in sites}
    reviewed_acceptances = _reviewed_acceptances()
    _, reviewed_delta = _reviewed_acceptances_from(REVIEW_DEFINITION)
    reviewed_delta_by_key = {
        row["project_stable_key"]: row for row in reviewed_delta
    }
    reviewed_by_key = {
        row["project_stable_key"]: row for row in reviewed_acceptances
    }
    reviewed_keys = set(reviewed_by_key)
    if {row["project_stable_key"] for row in projects} != reviewed_keys:
        raise VerifiedConstructionCoreError("preview reviewed-project cohort differs")
    default_imagery_outcome, imagery_records = _imagery_contract()
    imagery_by_key = {row["project_stable_key"]: row for row in imagery_records}
    provenance = _provenance_contract()
    overlays = _reviewed_overlays(hydrated_crosscheck=False)
    workload_binding_by_key = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
        ): row
        for row in provenance["workload_scope_bindings"]
    }
    role_bindings_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in provenance["role_bindings"]:
        role_bindings_by_project[binding["project_stable_key"]].append(binding)
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    if len(evidence_by_id) != len(evidence):
        raise VerifiedConstructionCoreError("preview evidence identifiers are not unique")
    _validate_v06_inheritance(projects, sites, evidence)
    for row in projects:
        acceptance = reviewed_by_key[row["project_stable_key"]]
        if row["project_id"] != atlas_stable_id(
            "entity", row["project_stable_key"], "project"
        ):
            raise VerifiedConstructionCoreError("preview project id differs")
        expected_imagery_outcome = _imagery_outcome(
            row["project_stable_key"], default_imagery_outcome, imagery_by_key
        )
        if row["project_stable_key"] in reviewed_delta_by_key:
            overlay_id = reviewed_delta_by_key[row["project_stable_key"]][
                "geometry_overlay_id"
            ]
            bridge = overlays["bridges_by_overlay_id"].get(overlay_id)
            if bridge is None:
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry bridge is absent"
                )
            _validate_bridge_acceptance_semantics(
                reviewed_delta_by_key[row["project_stable_key"]],
                bridge,
                label="preview reviewed geometry",
            )
            _validate_v06_delta_project(
                row,
                reviewed_delta_by_key[row["project_stable_key"]],
                evidence_by_id,
                expected_imagery_outcome,
                bridge,
                workload_binding_by_key,
                role_bindings_by_project,
            )
        if acceptance.get("geometry_overlay_id") is None:
            expected_authority, expected_use_scope = _direct_geometry_semantics(
                row["geometry_type"]
            )
        else:
            decision = overlays["bridges_by_overlay_id"][
                acceptance["geometry_overlay_id"]
            ]["review_decision"]
            expected_authority = decision["geometry_authority_class"]
            expected_use_scope = decision["geometry_use_scope"]
        if (
            row["geometry_source_entity_kind"] != acceptance["geometry_entity"]
            or row["geometry_derivation"] != acceptance["geometry_derivation"]
            or row["geometry_method"] != acceptance["geometry_method"]
            or row["geometry_scope_class"] != acceptance["geometry_scope_class"]
            or row["geometry_authority_class"] != expected_authority
            or row["geometry_use_scope"] != expected_use_scope
            or row["geometry_precision_scope"] != acceptance["precision_scope"]
            or row["imagery_review_outcome"] != expected_imagery_outcome
        ):
            raise VerifiedConstructionCoreError(
                "preview reviewed geometry or imagery contract differs"
            )
        expected_uncertainty = acceptance["horizontal_uncertainty_metres"]
        if expected_uncertainty is None:
            overlay_id = acceptance.get("geometry_overlay_id")
            expected_unknown_reason = (
                overlays["bridges_by_overlay_id"][overlay_id]["review_decision"][
                    "horizontal_uncertainty_unknown_reason"
                ]
                if overlay_id is not None
                else "official source does not state positional accuracy"
            )
            if row["horizontal_uncertainty_metres"] or row[
                "horizontal_uncertainty_unknown_reason"
            ] != expected_unknown_reason:
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                )
        else:
            try:
                actual_uncertainty = float(row["horizontal_uncertainty_metres"])
            except ValueError as error:
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                ) from error
            if (
                actual_uncertainty != float(expected_uncertainty)
                or row["horizontal_uncertainty_unknown_reason"]
            ):
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                )
        imagery_record = imagery_by_key.get(row["project_stable_key"])
        if imagery_record is not None and imagery_record["project_entity_id"] != row[
            "project_id"
        ]:
            raise VerifiedConstructionCoreError("preview imagery identity differs")
        if row["status_evidence_id"] not in evidence_ids or row[
            "geometry_evidence_id"
        ] not in evidence_ids:
            raise VerifiedConstructionCoreError("preview evidence reference is absent")
        age = (REVIEW_DATE - _calendar_date(row["status_as_of"], "status_as_of")).days
        if int(row["status_age_days_at_review"]) != age:
            raise VerifiedConstructionCoreError("preview status age differs")
        if age < 0 or age > MAX_STATUS_AGE_DAYS:
            raise VerifiedConstructionCoreError("preview status freshness differs")
        if row["last_observed_physical_status"] not in PHYSICAL_STATUSES or row[
            "status_method"
        ] not in AUTHORITATIVE_STATUS_METHODS:
            raise VerifiedConstructionCoreError("preview physical-status gate differs")
        if row["independent_imagery_verification"] != "false":
            raise VerifiedConstructionCoreError("preview imagery claim differs")
        geometry = _parse_json_field(row["geometry_json"], "geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != row[
            "geometry_type"
        ] or row["geometry_type"] not in {"Point", "Polygon", "MultiPolygon"}:
            raise VerifiedConstructionCoreError("preview geometry type differs")
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except ValueError as error:
            raise VerifiedConstructionCoreError(
                "preview geometry representative coordinates differ"
            ) from error
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
            or (
                geometry["type"] == "Point"
                and geometry.get("coordinates") != [longitude, latitude]
            )
        ):
            raise VerifiedConstructionCoreError(
                "preview geometry representative coordinates differ"
            )
        if row["verification_posture"] != _verification_posture(
            row["geometry_authority_class"], row["geometry_use_scope"]
        ):
            raise VerifiedConstructionCoreError("preview verification posture differs")
        if row["site_id"] != _stable_id(
            "vcc-site", row["physical_site_stable_key"]
        ):
            raise VerifiedConstructionCoreError("preview physical-site id differs")
        site = site_by_id[row["site_id"]]
        if site["physical_site_stable_key"] != row["physical_site_stable_key"]:
            raise VerifiedConstructionCoreError("preview project/site identity differs")
        if row["horizontal_uncertainty_metres"]:
            if row["horizontal_uncertainty_unknown_reason"]:
                raise VerifiedConstructionCoreError("preview geometry precision conflicts")
            if float(row["horizontal_uncertainty_metres"]) < 0:
                raise VerifiedConstructionCoreError("preview geometry precision differs")
        elif not row["horizontal_uncertainty_unknown_reason"]:
            raise VerifiedConstructionCoreError("preview geometry precision reason is absent")
        if row["operating_model"] == "unknown":
            if not row["operating_model_unknown_reason"] or row[
                "operating_model_evidence_id"
            ]:
                raise VerifiedConstructionCoreError(
                    "preview operating-model unknown posture differs"
                )
        else:
            operating_evidence_id = row["operating_model_evidence_id"]
            if row["operating_model_unknown_reason"] or operating_evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview operating-model evidence differs"
                )
            operating_evidence = evidence_by_id[operating_evidence_id]
            if "operating_model" not in _parse_json_field(
                operating_evidence["roles_json"], "roles"
            ) or row["project_id"] not in _parse_json_field(
                operating_evidence["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError(
                    "preview operating-model evidence usage differs"
                )
        for evidence_id, role in (
            (row["status_evidence_id"], "physical_status"),
            (row["geometry_evidence_id"], "geometry"),
        ):
            evidence_row = evidence_by_id[evidence_id]
            source_url_field = (
                "status_source_url"
                if role == "physical_status"
                else "geometry_source_url"
            )
            if row[source_url_field] != evidence_row["source_url"]:
                raise VerifiedConstructionCoreError(
                    "preview evidence source URL differs"
                )
            if role not in _parse_json_field(evidence_row["roles_json"], "roles") or row[
                "project_id"
            ] not in _parse_json_field(
                evidence_row["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError("preview evidence usage differs")
        typed_observations: list[dict[str, Any]] = []
        for field, reason_field, allowed_metrics in (
            ("power_observations_json", "power_unknown_reason", POWER_METRICS),
            (
                "annual_energy_observations_json",
                "annual_energy_unknown_reason",
                ENERGY_METRICS,
            ),
            (
                "efficiency_observations_json",
                "efficiency_unknown_reason",
                EFFICIENCY_METRICS,
            ),
        ):
            observations = _parse_json_field(row[field], field)
            if not isinstance(observations, list) or any(
                not isinstance(observation, dict)
                for observation in observations
            ):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric category differs"
                )
            for observation in observations:
                _validate_typed_observation(observation, allowed_metrics)
            if bool(observations) == bool(row[reason_field]):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric unknown posture differs"
                )
            typed_observations.extend(observations)
        for observation in typed_observations:
            evidence_id = observation.get("evidence_id")
            role = f"typed_metric:{observation.get('metric')}"
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview typed-metric evidence usage differs"
                )
            metric_evidence = evidence_by_id[evidence_id]
            if role not in _parse_json_field(
                metric_evidence["roles_json"], "roles"
            ) or row["project_id"] not in _parse_json_field(
                metric_evidence["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric evidence usage differs"
                )
        workloads = _parse_json_field(row["workloads_json"], "workloads")
        if not isinstance(workloads, list):
            raise VerifiedConstructionCoreError("preview workload list differs")
        for workload in workloads:
            _validate_workload_observation(workload)
            evidence_id = workload.get("evidence_id")
            binding = workload_binding_by_key.get(
                (row["project_stable_key"], evidence_id, workload.get("workload"))
            )
            if binding is None or any(
                workload[field] != binding[field]
                for field in SOURCE_WORKLOAD_FIELDS | {"deployment_scope"}
            ):
                raise VerifiedConstructionCoreError(
                    "preview workload provenance differs"
                )
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview workload evidence usage differs"
                )
            workload_evidence = evidence_by_id[evidence_id]
            workload_roles = _parse_json_field(workload_evidence["roles_json"], "roles")
            if (
                "workload" not in workload_roles
                or f"workload_scope:{workload['deployment_scope']}" not in workload_roles
                or row["project_id"] not in _parse_json_field(
                workload_evidence["project_ids_json"], "project_ids"
                )
            ):
                raise VerifiedConstructionCoreError(
                    "preview workload evidence usage differs"
                )
        role_claims = _parse_json_field(row["role_claims_json"], "role claims")
        if not isinstance(role_claims, list):
            raise VerifiedConstructionCoreError("preview role claims differ")
        for claim in role_claims:
            _validate_role_claim(claim)
        if role_claims != sorted(
            role_claims,
            key=lambda claim: (claim["role"], claim["party"], claim["evidence_id"]),
        ) or len({(claim["role"], claim["party"]) for claim in role_claims}) != len(
            role_claims
        ):
            raise VerifiedConstructionCoreError("preview role claim ordering differs")
        expected_role_claims = sorted(
            [
                {
                    "evidence_id": binding["evidence_id"],
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
                for binding in role_bindings_by_project.get(
                    row["project_stable_key"], []
                )
            ],
            key=lambda claim: (claim["role"], claim["party"], claim["evidence_id"]),
        )
        if role_claims != expected_role_claims:
            raise VerifiedConstructionCoreError("preview role provenance differs")
        projected: dict[str, list[str]] = {role: [] for role in ROLE_COLUMNS}
        for claim in role_claims:
            projected[claim["role"]].append(claim["party"])
            role_evidence = evidence_by_id.get(claim["evidence_id"])
            if role_evidence is None or (
                f"role:{claim['role']}"
                not in _parse_json_field(role_evidence["roles_json"], "roles")
                or row["project_id"]
                not in _parse_json_field(
                    role_evidence["project_ids_json"], "project_ids"
                )
            ):
                raise VerifiedConstructionCoreError(
                    "preview role evidence usage differs"
                )
        for role, column in ROLE_COLUMNS.items():
            if row[column] != "; ".join(sorted(projected[role])):
                raise VerifiedConstructionCoreError(
                    "preview role projection differs"
                )
    for evidence_id, expected in provenance["evidence_rows"].items():
        actual = evidence_by_id.get(evidence_id)
        if actual is None or any(
            actual.get(field) != value
            for field, value in expected.items()
            if field not in {"roles_json", "project_ids_json"}
        ):
            raise VerifiedConstructionCoreError(
                "preview provenance evidence content differs"
            )
    expected_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    for project in projects:
        project_id = project["project_id"]
        for evidence_id, role in (
            (project["status_evidence_id"], "physical_status"),
            (project["geometry_evidence_id"], "geometry"),
        ):
            expected_usage[evidence_id]["roles"].add(role)
            expected_usage[evidence_id]["project_ids"].add(project_id)
        if project["operating_model_evidence_id"]:
            evidence_id = project["operating_model_evidence_id"]
            expected_usage[evidence_id]["roles"].add("operating_model")
            expected_usage[evidence_id]["project_ids"].add(project_id)
        for field in (
            "power_observations_json",
            "annual_energy_observations_json",
            "efficiency_observations_json",
        ):
            for observation in _parse_json_field(project[field], field):
                evidence_id = observation["evidence_id"]
                expected_usage[evidence_id]["roles"].add(
                    f"typed_metric:{observation['metric']}"
                )
                expected_usage[evidence_id]["project_ids"].add(project_id)
        for workload in _parse_json_field(project["workloads_json"], "workloads"):
            evidence_id = workload["evidence_id"]
            expected_usage[evidence_id]["roles"].update(
                {"workload", f"workload_scope:{workload['deployment_scope']}"}
            )
            expected_usage[evidence_id]["project_ids"].add(project_id)
        for claim in _parse_json_field(project["role_claims_json"], "role claims"):
            evidence_id = claim["evidence_id"]
            expected_usage[evidence_id]["roles"].add(f"role:{claim['role']}")
            expected_usage[evidence_id]["project_ids"].add(project_id)
    if set(expected_usage) != evidence_ids:
        raise VerifiedConstructionCoreError("preview evidence closure differs")
    for evidence_id, usage in expected_usage.items():
        evidence_row = evidence_by_id[evidence_id]
        if (
            _parse_json_field(evidence_row["roles_json"], "roles")
            != sorted(usage["roles"])
            or _parse_json_field(
                evidence_row["project_ids_json"], "project_ids"
            )
            != sorted(usage["project_ids"])
        ):
            raise VerifiedConstructionCoreError("preview evidence usage closure differs")
    delta_site_names: dict[str, str] = {}
    for acceptance in reviewed_delta:
        source = _load_json(
            _repository_input(
                acceptance["source_input_path"],
                acceptance["source_input_sha256"],
                "current reviewed-site",
            )
        )
        campus = source.get("campus")
        if (
            not isinstance(campus, dict)
            or campus.get("stable_key") != acceptance["physical_site_stable_key"]
            or not isinstance(campus.get("name"), str)
            or not campus["name"]
        ):
            raise VerifiedConstructionCoreError(
                "current reviewed-site campus identity differs"
            )
        previous = delta_site_names.setdefault(campus["stable_key"], campus["name"])
        if previous != campus["name"]:
            raise VerifiedConstructionCoreError(
                "current reviewed-site campus name differs"
            )
    projects_by_site: dict[str, list[dict[str, str]]] = defaultdict(list)
    for project in projects:
        projects_by_site[project["site_id"]].append(project)
    for site in sites:
        members = sorted(
            projects_by_site[site["site_id"]], key=lambda row: row["project_id"]
        )
        geometry_member = _preferred_site_geometry_member(members)
        expected_arrays = {
            "geometry_source_entity_kinds_json": sorted(
                {row["geometry_source_entity_kind"] for row in members}
            ),
            "geometry_derivations_json": sorted(
                {row["geometry_derivation"] for row in members}
            ),
            "geometry_methods_json": sorted(
                {row["geometry_method"] for row in members}
            ),
            "geometry_scope_classes_json": sorted(
                {row["geometry_scope_class"] for row in members}
            ),
            "geometry_authority_classes_json": sorted(
                {row["geometry_authority_class"] for row in members}
            ),
            "geometry_use_scopes_json": sorted(
                {row["geometry_use_scope"] for row in members}
            ),
            "geometry_precision_scopes_json": sorted(
                {row["geometry_precision_scope"] for row in members}
            ),
            "geometry_evidence_ids_json": sorted(
                {row["geometry_evidence_id"] for row in members}
            ),
            "project_ids_json": [row["project_id"] for row in members],
            "project_stable_keys_json": [
                row["project_stable_key"] for row in members
            ],
            "statuses_json": sorted(
                {row["last_observed_physical_status"] for row in members}
            ),
            "imagery_review_outcomes_json": sorted(
                {row["imagery_review_outcome"] for row in members}
            ),
        }
        if any(
            _parse_json_field(site[field], field) != expected
            for field, expected in expected_arrays.items()
        ):
            raise VerifiedConstructionCoreError("preview site membership differs")
        if int(site["project_count"]) != len(members):
            raise VerifiedConstructionCoreError("preview site project count differs")
        expected_scalars = {
            "physical_site_stable_key": geometry_member[
                "physical_site_stable_key"
            ],
            "country": geometry_member["country"],
            "country_iso_a2": geometry_member["country_iso_a2"],
            "latitude": geometry_member["latitude"],
            "longitude": geometry_member["longitude"],
            "geometry_json": geometry_member["geometry_json"],
            "geometry_type": geometry_member["geometry_type"],
            "horizontal_uncertainty_metres": geometry_member[
                "horizontal_uncertainty_metres"
            ],
            "horizontal_uncertainty_unknown_reason": geometry_member[
                "horizontal_uncertainty_unknown_reason"
            ],
            "oldest_status_as_of": min(row["status_as_of"] for row in members),
            "newest_status_as_of": max(row["status_as_of"] for row in members),
            "verification_posture": geometry_member["verification_posture"],
            "independent_imagery_verification": "false",
        }
        if site["physical_site_stable_key"] in delta_site_names:
            expected_scalars["name"] = delta_site_names[
                site["physical_site_stable_key"]
            ]
        if any(site[field] != expected for field, expected in expected_scalars.items()):
            raise VerifiedConstructionCoreError("preview site projection differs")
        if site["site_id"] != _stable_id(
            "vcc-site", site["physical_site_stable_key"]
        ):
            raise VerifiedConstructionCoreError("preview site id differs")
    if geojson != _geojson(sites):
        raise VerifiedConstructionCoreError("preview GeoJSON and site table differ")
    if (path / "map.html").read_bytes() != _map_html(geojson, evidence):
        raise VerifiedConstructionCoreError("preview map and GeoJSON differ")
    report_fields = {
        "country_counts",
        "final_release_gates",
        "format",
        "imagery_review_provenance",
        "maximum_status_age_days",
        "non_selected_source_row_count",
        "official_boundary_project_count",
        "provenance_decisions",
        "publishable_as_final",
        "release_status",
        "reviewed_at",
        "reviewed_overlay_queue",
        "reviewed_site_locator_project_count",
        "selected_physical_site_count",
        "selected_project_count",
        "selection_first_failure_counts",
        "semantic_guardrails",
        "source_pipeline_row_count",
        "source_release_id",
    }
    if not isinstance(report, dict) or set(report) != report_fields:
        raise VerifiedConstructionCoreError("preview selection-report fields differ")
    expected_gates = _final_release_gates(sites, projects)
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    expected_values = {
        "format": "datacenter-atlas-verified-construction-core-selection-v6",
        "release_status": "preview",
        "publishable_as_final": all(
            gate.get("passed", False) for gate in expected_gates.values()
        ),
        "source_release_id": SOURCE_RELEASE_ID,
        "reviewed_at": REVIEW_DATE.isoformat(),
        "maximum_status_age_days": MAX_STATUS_AGE_DAYS,
        "source_pipeline_row_count": PREVIEW_SOURCE_PIPELINE_ROW_COUNT,
        "selected_project_count": len(projects),
        "selected_physical_site_count": len(sites),
        "official_boundary_project_count": sum(
            _is_official_boundary(row) for row in projects
        ),
        "reviewed_site_locator_project_count": sum(
            _is_reviewed_locator(row) for row in projects
        ),
        "non_selected_source_row_count": PREVIEW_SOURCE_PIPELINE_ROW_COUNT
        - len(projects),
        "selection_first_failure_counts": PREVIEW_SELECTION_FIRST_FAILURE_COUNTS,
        "country_counts": country_counts,
        "final_release_gates": expected_gates,
        "imagery_review_provenance": imagery_records,
        "provenance_decisions": {
            "workload_scope_bindings": provenance["workload_scope_bindings"],
            "role_bindings": provenance["role_bindings"],
            "excluded_source_roles": provenance["excluded_source_roles"],
        },
        "semantic_guardrails": SEMANTIC_GUARDRAILS,
    }
    if any(report.get(field) != value for field, value in expected_values.items()):
        raise VerifiedConstructionCoreError("preview selection-report values differ")
    if (path / "README.md").read_bytes() != _readme(report):
        raise VerifiedConstructionCoreError("preview README differs")
    expected_overlays = overlays["overlays"]
    if report.get("reviewed_overlay_queue") != expected_overlays:
        raise VerifiedConstructionCoreError("preview reviewed-overlay queue differs")
    if not isinstance(expected_overlays, list):
        raise VerifiedConstructionCoreError("preview reviewed-overlay definition differs")
    if (path / "ATTRIBUTION.txt").read_bytes() != _attribution(
        evidence, expected_overlays, imagery_records
    ):
        raise VerifiedConstructionCoreError("preview attribution differs")
    for overlay in expected_overlays:
        if "geometry_release_id" in overlay:
            _geometry_release_manifest(
                overlay.get("geometry_release_id", ""),
                overlay.get("geometry_release_manifest_sha256", ""),
            )
    derived_counts = {
        "physical_sites": len(sites),
        "projects": len(projects),
        "evidence": len(evidence),
        "countries": len({row["country"] for row in sites}),
        "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
        "official_boundary_projects": sum(
            _is_official_boundary(row) for row in projects
        ),
        "reviewed_site_locator_projects": sum(
            _is_reviewed_locator(row) for row in projects
        ),
    }
    if counts != derived_counts:
        raise VerifiedConstructionCoreError("preview derived counts differ")
    if counts != {
        "physical_sites": 26,
        "projects": 29,
        "evidence": 63,
        "countries": 17,
        "non_us_sites": 20,
        "official_boundary_projects": 4,
        "reviewed_site_locator_projects": 25,
    }:
        raise VerifiedConstructionCoreError("preview expected cohort counts differ")
    return manifest


V07_COUNTRY_ISO_A2 = {
    "France": "FR",
    "Italy": "IT",
    "Korea, Republic of": "KR",
    "South Africa": "ZA",
    "Spain": "ES",
    "Sweden": "SE",
}
V07_SELECTION_FIRST_FAILURE_COUNTS = {
    "entity_kind_not_project": 49,
    "not_in_reviewed_site_geometry_allowlist": 107,
    "selected": 36,
    "status_not_physical": 12,
    "status_outside_90_day_window": 327,
}
V07_OVERLAY_REQUIRED_FIELDS = frozenset(
    {
        "bridge_bytes",
        "bridge_decision",
        "bridge_id",
        "bridge_path",
        "bridge_schema",
        "bridge_sha256",
        "country",
        "decision",
        "decision_reason",
        "geometry_authority_class",
        "geometry_derivation",
        "geometry_entity",
        "geometry_entity_id",
        "geometry_entity_stable_key",
        "geometry_evidence_id",
        "geometry_evidence_key",
        "geometry_method",
        "geometry_scope_class",
        "geometry_source_kind",
        "geometry_use_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "official_boundary",
        "overlay_id",
        "physical_site_entity_id",
        "physical_site_stable_key",
        "portable_capture_binding",
        "portable_input_binding",
        "precision_scope",
        "project_to_campus_decision_basis",
        "project_to_campus_relationship_id",
        "project_to_campus_relationship_type",
        "rejected_claims",
        "reviewed_at",
        "source_input_bytes",
        "source_input_path",
        "source_input_sha256",
        "source_project_entity_id",
        "source_project_stable_key",
    }
)
V07_POINT_COORDINATES = {
    "curated:aws-walqa-huesca-data-center:current-build": (
        -0.4564361111111111,
        42.11381388888889,
    ),
    "curated:atnorth-swe02-stockholm-campus:current-development": (
        17.919052862381037,
        59.42019318407011,
    ),
    "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it": (
        -3.7520406,
        37.0832838,
    ),
    "curated:teraco-ct1-rondebosch-data-centre:current-expansion": (
        18.4649,
        -33.9712,
    ),
    "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2": (
        126.7109,
        37.518,
    ),
}
V07_BRIDGE_INPUT_SHA256 = {
    "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it": (
        "1159f75260a833f0c212501c3212c5ca091b3628c3829a78ad955898ad220272",
        "5e2f4e431b877d403d3f34d1d5de689450cfa58d1670c9e8b038f39f21d5cc80",
    ),
    "curated:atnorth-swe02-stockholm-campus:current-development": (
        "dcb8bbd8cda0018e5c8e9f28ca56d43ade9ae5e7dfa26aaef0dec85f19024b35",
        "c69edf4c7c7b7f705ce3489f3ee1f112fab2032c0483a3a1b4ace77d84283169",
    ),
    "curated:aws-walqa-huesca-data-center:current-build": (
        "b52be2ca48aa422529372ce6b721ff98c00d8b0aa4fea0a0e15b79fb1fb4b65a",
        "31048bd15869c30f78292a709f2d18e1b8423eacdbfda2faff9a9e04c0983698",
    ),
    "curated:colt-villebon-sur-yvette-campus:paris2-current-facility-build": (
        "37d8b17fc6fa2de15acf57065e3b8b225ef57d45a2d9d6a9cba33662140d6ed9",
        "aac09ee130b7d721f0605d8ea0f9916955baf6666f692eb397f7fcb6dc6737ff",
    ),
    "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2": (
        "3fb6ea1c02d44a60e1c48289f5cc089965eb3596e90fd0ce46d018a6701a4a6a",
        "b8f6ff6a9cebe6630bf9757eb78c56af1cd63cd0b949c9f72615bb0ae44ff67b",
    ),
    "curated:microsoft-san-bovio-italy-datacenter:initial-development": (
        "913510cdb274ffd280425a0b2cdefa9e8f7b8abb7562ed38a8e7bb924c33b9a8",
        "00c9e055f0df79ea1226033b40aca969f8b2948e5f5b4d9f8a913ea735f11e9f",
    ),
    "curated:teraco-ct1-rondebosch-data-centre:current-expansion": (
        "96db9e011ef5c895bb7c20e83b9d23c5e25fac4574082c26c9617393b75f9d3b",
        "2a73a6dacb84bfcd5cee8e51bf08955f9863dca328117833d94d06634fa43eea",
    ),
}


def _v07_repository_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise VerifiedConstructionCoreError("v0.7 repository path escapes")
    resolved = (ROOT / path).resolve()
    if resolved.parent == ROOT.resolve() or ROOT.resolve() not in resolved.parents:
        raise VerifiedConstructionCoreError("v0.7 repository path differs")
    return resolved


def _v07_definition_paths() -> dict[str, tuple[Path, str]]:
    return {
        "review_definition_sha256": (
            ROOT / "definitions/verified-construction-core-v0.7-reviewed-sites.json",
            V07_REVIEW_DEFINITION_SHA256,
        ),
        "imagery_review_definition_sha256": (
            ROOT / "definitions/verified-construction-core-v0.7-imagery-reviews.json",
            V07_IMAGERY_REVIEW_DEFINITION_SHA256,
        ),
        "provenance_definition_sha256": (
            ROOT / "definitions/verified-construction-core-v0.7-provenance.json",
            V07_PROVENANCE_DEFINITION_SHA256,
        ),
        "overlay_definition_sha256": (
            ROOT / "definitions/verified-construction-core-reviewed-overlays-v5.json",
            V07_OVERLAY_DEFINITION_SHA256,
        ),
    }


def _validate_v07_definition_pins() -> None:
    for field, (path, expected) in _v07_definition_paths().items():
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != expected:
            raise VerifiedConstructionCoreError(f"current v0.7 {field} source hash differs")


def _v07_hydrated_crosscheck_available() -> bool:
    required = (
        ROOT / "releases/2026-07-22-open-seed-v97/construction_pipeline.csv",
        ROOT / "releases/2026-07-22-open-seed-v97/entities.csv",
        ROOT / "releases/2026-07-22-open-seed-v97/evidence.csv",
        ROOT / "releases/2026-07-18-global-open-v3/entities.csv",
        ROOT / "releases/2026-07-18-global-open-v3/evidence.csv",
        ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/component-members.csv",
        ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/relationships.csv",
    )
    present = [path.is_file() for path in required]
    if any(present) and not all(present):
        raise VerifiedConstructionCoreError(
            "v0.7 hydrated cross-check inputs are only partially present"
        )
    return all(present)


def _v07_source_evidence(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = source.get("evidence")
    if not isinstance(rows, list) or not rows:
        raise VerifiedConstructionCoreError("v0.7 source evidence differs")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise VerifiedConstructionCoreError("v0.7 source evidence differs")
        evidence_id = _official_evidence_id(row)
        projected = {
            field: (row.get(field) if row.get(field) is not None else "")
            for field in EVIDENCE_FIELDS
            if field not in {"evidence_id", "roles_json", "project_ids_json"}
        }
        projected["evidence_id"] = evidence_id
        if evidence_id in result:
            raise VerifiedConstructionCoreError("v0.7 source evidence is not unique")
        result[evidence_id] = projected
    return result


def _v07_source_roles(project: Mapping[str, Any]) -> dict[str, list[str]]:
    normalized = project.get("normalized_roles")
    if normalized is not None:
        if not isinstance(normalized, dict):
            raise VerifiedConstructionCoreError("v0.7 normalized roles differ")
        source = normalized
    else:
        source = project
    result: dict[str, list[str]] = {}
    for role, column in ROLE_COLUMNS.items():
        value = source.get(column)
        if value is None:
            parties: list[str] = []
        elif isinstance(value, str):
            parties = [party.strip() for party in value.split(";") if party.strip()]
        elif isinstance(value, list) and all(isinstance(party, str) for party in value):
            parties = [party.strip() for party in value if party.strip()]
        else:
            raise VerifiedConstructionCoreError("v0.7 source roles differ")
        if len(parties) != len(set(parties)):
            raise VerifiedConstructionCoreError("v0.7 source roles are not unique")
        result[role] = sorted(parties)
    return result


def _v07_validate_capture_binding(binding: Any, *, required: bool) -> Path | None:
    if binding is None:
        if required:
            raise VerifiedConstructionCoreError("v0.7 portable capture is absent")
        return None
    if not isinstance(binding, dict) or not {"path", "bytes", "sha256"} <= set(binding):
        raise VerifiedConstructionCoreError("v0.7 portable capture binding differs")
    path = _repository_input(binding["path"], binding["sha256"], "v0.7 capture")
    if path.stat().st_size != binding["bytes"]:
        raise VerifiedConstructionCoreError("v0.7 portable capture byte count differs")
    return path


def _validate_v07_colt_capture(
    bridge: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    path = _v07_validate_capture_binding(binding, required=True)
    capture = _load_json(path)
    selection = capture.get("selection") if isinstance(capture, dict) else None
    feature = selection.get("selected_feature") if isinstance(selection, dict) else None
    if (
        capture.get("capture_id")
        != "verified-construction-core-v0.7-colt-paris2-dgfip-ap8-capture"
        or capture.get("schema_version") != 1
        or not isinstance(feature, dict)
        or feature.get("id") != "91661000AP0008"
        or selection.get("selected_feature_count") != 1
        or selection.get("selected_feature_canonical_sha256")
        != _sha256_bytes(_json_bytes(feature))
        or selection.get("selected_feature_canonical_bytes") != len(_json_bytes(feature))
        or feature.get("geometry") != bridge["geometry_entity"]["geometry"]
        or capture.get("source", {}).get("license") != "etalab-2.0"
    ):
        raise VerifiedConstructionCoreError("v0.7 Colt capture replay differs")
    fact = bridge["geometry_evidence"]["fact_payload"]
    ring = feature["geometry"]["coordinates"][0]
    origin = ring[0]
    translated_ring = [
        [point[0] - origin[0], point[1] - origin[1]] for point in ring
    ]
    twice_area = sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(translated_ring, translated_ring[1:])
    )
    centroid = [
        round(
            origin[index]
            +
            sum(
                (left[index] + right[index])
                * (left[0] * right[1] - right[0] * left[1])
                for left, right in zip(translated_ring, translated_ring[1:])
            )
            / (3 * twice_area),
            10,
        )
        for index in (0, 1)
    ]
    if (
        fact.get("selected_feature_canonical_sha256")
        != selection["selected_feature_canonical_sha256"]
        or fact.get("cadastral_feature_id") != feature["id"]
        or fact.get("contenance_m2_as_reported")
        != feature.get("properties", {}).get("contenance")
        or centroid != [2.2199845682, 48.690997187]
        or [
            bridge["geometry_entity"].get("longitude"),
            bridge["geometry_entity"].get("latitude"),
        ]
        != centroid
    ):
        raise VerifiedConstructionCoreError("v0.7 Colt fact projection differs")


def _validate_v07_san_capture(
    bridge: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    path = _v07_validate_capture_binding(binding, required=True)
    capture = _load_json(path)
    try:
        raw = base64.b64decode(
            capture["payload"]["raw_response_body_base64"], validate=True
        )
        payload = json.loads(raw)
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError) as error:
        raise VerifiedConstructionCoreError("v0.7 San Bovio capture differs") from error
    response = capture.get("response", {})
    if (
        len(raw) != binding.get("raw_payload_bytes")
        or _sha256_bytes(raw) != binding.get("raw_payload_sha256")
        or len(raw) != response.get("decoded_body_bytes")
        or _sha256_bytes(raw) != response.get("decoded_body_sha256")
    ):
        raise VerifiedConstructionCoreError("v0.7 San Bovio raw capture differs")
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise VerifiedConstructionCoreError("v0.7 San Bovio capture elements differ")
    ways = [row for row in elements if row.get("type") == "way"]
    nodes = {row.get("id"): row for row in elements if row.get("type") == "node"}
    if len(ways) != 1 or ways[0].get("id") != 554352050 or len(nodes) != 13:
        raise VerifiedConstructionCoreError("v0.7 San Bovio capture object differs")
    way = ways[0]
    try:
        ring = [[nodes[node_id]["lon"], nodes[node_id]["lat"]] for node_id in way["nodes"]]
    except (KeyError, TypeError) as error:
        raise VerifiedConstructionCoreError("v0.7 San Bovio capture ring differs") from error
    entity = bridge["geometry_entity"]
    representative = entity.get("representative_point", {})
    projected = representative.get("projected_centroid", {})
    tools = representative.get("toolchain", {})
    if (
        entity.get("geometry") != {"type": "Polygon", "coordinates": [ring]}
        or representative.get("coordinates")
        != [9.310638890241082, 45.46212956614725]
        or [entity.get("longitude"), entity.get("latitude")]
        != [9.310638890241082, 45.46212956614725]
        or projected
        != {
            "crs": "EPSG:32632",
            "easting_m": 524285.4851843531,
            "northing_m": 5034336.149184176,
        }
        or tools != {"pyproj": "3.7.2", "proj": "9.5.1", "shapely": "2.1.2"}
        or entity.get("geometry_metrics", {}).get("area_m2") != 84562.7109
        or way.get("tags") != {"landuse": "industrial", "name": "Ex Postal Market"}
        or way.get("timestamp") != "2022-07-19T17:15:33Z"
    ):
        raise VerifiedConstructionCoreError("v0.7 San Bovio geometry replay differs")


def _validate_v07_topology(
    bridge: Mapping[str, Any],
    project: Mapping[str, Any],
    campus: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> None:
    topology = bridge["construction_source"]["project_to_campus"]
    if not isinstance(topology, dict) or set(topology) != {
        "basis",
        "target_entity_id",
        "bundle_id",
        "manifest",
        "members",
        "relationship",
        "subject_member",
        "object_member",
        "supplemental_v97_atlas_feature",
    }:
        raise VerifiedConstructionCoreError("v0.7 topology fields differ")
    if (
        topology.get("basis") != "v14_project_targets_explicit_parent"
        or topology.get("bundle_id") != "2026-07-22-public-open-v14"
        or topology.get("target_entity_id") != campus.get("entity_id")
        or topology.get("supplemental_v97_atlas_feature") is not None
    ):
        raise VerifiedConstructionCoreError("v0.7 topology identity differs")
    _, manifest = _manifest_binding(
        topology["manifest"], label="v0.7 topology release"
    )
    if (
        manifest.get("bundle_id") != topology["bundle_id"]
        or manifest.get("format")
        != "datacenter-atlas-exact-identity-decision-bundle-v1"
        or set(topology["members"])
        != {"component-members.csv", "relationships.csv"}
    ):
        raise VerifiedConstructionCoreError("v0.7 topology release differs")
    _validate_manifest_members(
        manifest, topology["members"], label="v0.7 topology release"
    )
    component_records = (
        ("subject", topology["subject_member"], project, "project"),
        ("object", topology["object_member"], campus, "campus"),
    )
    for label, record, entity, kind in component_records:
        if not isinstance(record, dict) or set(record) != {
            "component_id",
            "entity_id",
            "stable_key",
            "source_row",
        }:
            raise VerifiedConstructionCoreError(
                f"v0.7 topology {label} fields differ"
            )
        row = _embedded_csv_source_row(
            record["source_row"],
            EXACT_COMPONENT_FIELDS,
            label=f"v0.7 topology {label}",
        )
        occurrence_id = f"{SOURCE_RELEASE_ID}:{entity['entity_id']}"
        if (
            record["entity_id"] != entity["entity_id"]
            or record["stable_key"] != entity["stable_key"]
            or row["release_id"] != SOURCE_RELEASE_ID
            or row["entity_id"] != entity["entity_id"]
            or row["entity_kind"] != kind
            or row["stable_key"] != entity["stable_key"]
            or row["occurrence_id"] != occurrence_id
            or row["component_id"] != _exact_component_id(kind, occurrence_id)
            or record["component_id"] != row["component_id"]
            or row["component_member_count"] != "1"
            or row["identity_proof_parent_occurrence_id"]
            or _csv_json(row["typed_identity_tokens_json"], label="v0.7 topology tokens")
            != []
            or _csv_json(row["ambiguous_identity_tokens_json"], label="v0.7 topology ambiguity")
            != []
            or not row["source_root"]
            or row["source_family"] != row["source_root"]
            or not row["snapshot_evidence_id"]
        ):
            raise VerifiedConstructionCoreError(
                f"v0.7 topology {label} projection differs"
            )
    relationship = topology["relationship"]
    row = _embedded_csv_source_row(
        relationship.get("source_row"),
        EXACT_RELATIONSHIP_FIELDS,
        label="v0.7 topology relationship",
    )
    projection = _exact_relationship_projection(row)
    subject = topology["subject_member"]
    object_member = topology["object_member"]
    if (
        not isinstance(relationship, dict)
        or {field: value for field, value in relationship.items() if field != "source_row"}
        != projection
        or relationship.get("relationship_type") != "project_targets"
        or relationship.get("subject_component_id") != subject["component_id"]
        or relationship.get("subject_kind") != "project"
        or relationship.get("object_component_id") != object_member["component_id"]
        or relationship.get("object_kind") != "campus"
        or relationship.get("decision_basis") != "explicit_parent"
        or relationship.get("typed_identity_tokens") != []
        or relationship.get("source_release_ids") != [SOURCE_RELEASE_ID]
        or relationship.get("raw_relationship_count") != 1
        or relationship.get("relationship_id")
        != _exact_relationship_id(
            "project_targets", subject["component_id"], object_member["component_id"]
        )
    ):
        raise VerifiedConstructionCoreError("v0.7 topology relationship differs")
    if hydrated_crosscheck:
        for name, record, fields in (
            ("relationships.csv", relationship, EXACT_RELATIONSHIP_FIELDS),
            ("component-members.csv", subject, EXACT_COMPONENT_FIELDS),
            ("component-members.csv", object_member, EXACT_COMPONENT_FIELDS),
        ):
            metadata = topology["members"][name]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], f"v0.7 {name}"
            )
            if payload_path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"v0.7 hydrated topology differs: {name}"
                )
            _validate_hydrated_source_row(
                payload_path,
                record["source_row"],
                fields,
                label=f"v0.7 {name}",
            )


def _validate_v07_bridge(
    acceptance: Mapping[str, Any],
    overlay: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    project_key = acceptance["project_stable_key"]
    immutable_pins = V07_BRIDGE_INPUT_SHA256.get(project_key)
    if immutable_pins != (
        acceptance["bridge_sha256"],
        acceptance["source_input_sha256"],
    ):
        raise VerifiedConstructionCoreError("v0.7 immutable bridge profile differs")
    path = _repository_input(
        acceptance["bridge_path"], acceptance["bridge_sha256"], "geometry bridge"
    )
    if path.stat().st_size != acceptance["bridge_bytes"]:
        raise VerifiedConstructionCoreError("v0.7 bridge byte count differs")
    bridge = _load_json(path)
    expected_top = {
        "bridge_id",
        "bridge_schema",
        "claim_guardrails",
        "construction_source",
        "geometry_capture",
        "geometry_entity",
        "geometry_evidence",
        "geometry_release",
        "identity_bridge_evidence",
        "imagery_posture",
        "lineage_context",
        "review_decision",
        "reviewed_at",
        "rights",
        "schema_version",
    }
    if (
        not isinstance(bridge, dict)
        or set(bridge) != expected_top
        or bridge.get("schema_version") != 1
        or bridge.get("bridge_id") != acceptance["bridge_id"]
        or bridge.get("bridge_schema") != acceptance["bridge_schema"]
        or bridge.get("reviewed_at") != CURRENT_V07_REVIEW_DATE.isoformat()
        or bridge.get("geometry_release") is not None
    ):
        raise VerifiedConstructionCoreError("v0.7 bridge identity differs")
    schema = bridge["bridge_schema"]
    allowed_schemas = {
        "verified-construction-core-v0.7-direct-official-geometry-bridge-v1",
        "verified-construction-core-v0.7-cross-source-campus-geometry-bridge-v1",
        "verified-construction-core-v0.7-capture-replayed-campus-geometry-bridge-v1",
    }
    if schema not in allowed_schemas:
        raise VerifiedConstructionCoreError("v0.7 bridge schema differs")
    construction = bridge["construction_source"]
    source_input = construction.get("input")
    expected_input = {
        "path": acceptance["source_input_path"],
        "bytes": acceptance["source_input_bytes"],
        "sha256": acceptance["source_input_sha256"],
    }
    if source_input != expected_input or acceptance["portable_input_binding"] != expected_input:
        raise VerifiedConstructionCoreError("v0.7 bridge source input differs")
    source_path = _repository_input(
        expected_input["path"], expected_input["sha256"], "v0.7 source input"
    )
    if source_path.stat().st_size != expected_input["bytes"]:
        raise VerifiedConstructionCoreError("v0.7 source input byte count differs")
    source = _load_json(source_path)
    source_project = source.get("project") if isinstance(source, dict) else None
    source_campus = source.get("campus") if isinstance(source, dict) else None
    if (
        not isinstance(source_project, dict)
        or not isinstance(source_campus, dict)
        or source_project.get("stable_key") != acceptance["project_stable_key"]
        or source_campus.get("stable_key") != acceptance["physical_site_stable_key"]
        or atlas_stable_id("entity", acceptance["project_stable_key"], "project")
        != acceptance["project_entity_id"]
        or atlas_stable_id("entity", acceptance["physical_site_stable_key"], "campus")
        != acceptance["physical_site_entity_id"]
    ):
        raise VerifiedConstructionCoreError("v0.7 source identity differs")
    source_evidence = _v07_source_evidence(source)
    project = construction.get("project")
    campus = construction.get("campus")
    if (
        not isinstance(project, dict)
        or not isinstance(campus, dict)
        or project.get("stable_key") != acceptance["project_stable_key"]
        or project.get("entity_id") != acceptance["project_entity_id"]
        or campus.get("stable_key") != acceptance["physical_site_stable_key"]
        or campus.get("entity_id") != acceptance["physical_site_entity_id"]
        or project.get("country") != acceptance["country"]
        or campus.get("country") != acceptance["country"]
    ):
        raise VerifiedConstructionCoreError("v0.7 bridge construction identity differs")
    status = construction.get("status_evidence")
    if (
        not isinstance(status, dict)
        or status.get("evidence_id") != project.get("status_evidence_id")
        or status.get("evidence_id") not in source_evidence
    ):
        raise VerifiedConstructionCoreError("v0.7 status evidence differs")
    for field in GLOBAL_GEOMETRY_EVIDENCE_FIELDS:
        expected = source_evidence[status["evidence_id"]].get(field, "")
        actual = status.get(field)
        if actual is None:
            actual = ""
        if actual != expected:
            raise VerifiedConstructionCoreError("v0.7 status projection differs")
    release = construction.get("release")
    if not isinstance(release, dict) or release.get("release_id") != SOURCE_RELEASE_ID:
        raise VerifiedConstructionCoreError("v0.7 source release differs")
    _, release_manifest = _manifest_binding(
        release["manifest"], label="v0.7 source release"
    )
    _validate_manifest_members(
        release_manifest, release["members"], label="v0.7 source release"
    )
    embedded_rows = release.get("raw_rows", construction.get("release_rows"))
    if embedded_rows is not None:
        _validate_v06_embedded_release_rows(
            embedded_rows,
            release["members"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
    else:
        for label, record, member in (
            ("project", project, "construction_pipeline.csv"),
            ("campus", campus, "entities.csv"),
        ):
            row = _embedded_csv_source_row(
                record.get("source_row"),
                SOURCE_ENTITY_FIELDS,
                label=f"v0.7 {label}",
            )
            if (
                row["stable_key"] != record["stable_key"]
                or row["entity_id"] != record["entity_id"]
            ):
                raise VerifiedConstructionCoreError(
                    f"v0.7 {label} source-row projection differs"
                )
            if hydrated_crosscheck:
                metadata = release["members"][member]
                payload_path = _repository_input(
                    metadata["path"], metadata["sha256"], f"v0.7 {member}"
                )
                _validate_hydrated_source_row(
                    payload_path,
                    record["source_row"],
                    SOURCE_ENTITY_FIELDS,
                    label=f"v0.7 {label}",
                )
        status_row = _embedded_csv_source_row(
            status.get("source_row"),
            GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
            label="v0.7 status",
        )
        if status_row["evidence_id"] != status["evidence_id"]:
            raise VerifiedConstructionCoreError(
                "v0.7 status source-row projection differs"
            )
        if hydrated_crosscheck:
            metadata = release["members"]["evidence.csv"]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], "v0.7 evidence.csv"
            )
            _validate_hydrated_source_row(
                payload_path,
                status["source_row"],
                GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
                label="v0.7 status",
            )
    evidence_by_key = {
        row["key"]: row for row in source["evidence"] if isinstance(row, dict)
    }
    campus_evidence = evidence_by_key.get(source_campus.get("evidence_key"))
    if campus_evidence is None:
        raise VerifiedConstructionCoreError("v0.7 campus evidence differs")
    _validate_v07_topology(
        bridge, project, campus, hydrated_crosscheck=hydrated_crosscheck
    )
    topology = construction["project_to_campus"]
    relationship = topology["relationship"]
    if (
        relationship.get("relationship_id")
        != acceptance["project_to_campus_relationship_id"]
        or relationship.get("relationship_type")
        != acceptance["project_to_campus_relationship_type"]
        or relationship.get("decision_basis")
        != acceptance["project_to_campus_decision_basis"]
    ):
        raise VerifiedConstructionCoreError("v0.7 topology definition differs")
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    _validate_v06_fact_evidence(evidence, label="v0.7 geometry evidence")
    if (
        entity.get("entity_kind") != acceptance["geometry_entity"]
        or entity.get("stable_key") != acceptance["geometry_entity_stable_key"]
        or entity.get("entity_id") != acceptance["geometry_entity_id"]
        or entity.get("source_evidence_id") != acceptance["geometry_evidence_id"]
        or evidence.get("key") != acceptance["geometry_evidence_key"]
        or evidence.get("evidence_id") != acceptance["geometry_evidence_id"]
        or evidence.get("kind") != acceptance["geometry_source_kind"]
        or evidence.get("evidence_id") != _official_evidence_id(evidence)
        or entity.get("geometry", {}).get("type") not in {"Point", "Polygon"}
    ):
        raise VerifiedConstructionCoreError("v0.7 geometry projection differs")
    decision = bridge["review_decision"]
    decision_bindings = {
        "decision": "bridge_decision",
        "geometry_target_entity_kind": "geometry_entity",
        "geometry_derivation": "geometry_derivation",
        "geometry_method": "geometry_method",
        "geometry_scope_class": "geometry_scope_class",
        "geometry_authority_class": "geometry_authority_class",
        "geometry_use_scope": "geometry_use_scope",
        "horizontal_uncertainty_metres": "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason": "horizontal_uncertainty_unknown_reason",
        "precision_scope": "precision_scope",
        "rejected_claims": "rejected_claims",
    }
    if any(decision.get(field) != acceptance[target] for field, target in decision_bindings.items()):
        raise VerifiedConstructionCoreError("v0.7 review semantics differ")
    if decision.get("official_boundary", acceptance["official_boundary"]) != acceptance[
        "official_boundary"
    ]:
        raise VerifiedConstructionCoreError("v0.7 official-boundary semantics differ")
    if project_key in V07_POINT_COORDINATES:
        expected_point = list(V07_POINT_COORDINATES[project_key])
        fact = evidence["fact_payload"]
        if project_key == "curated:atnorth-swe02-stockholm-campus:current-development":
            fact_point = [
                fact.get("coordinate_transform", {}).get("longitude"),
                fact.get("coordinate_transform", {}).get("latitude"),
            ]
        elif project_key == "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it":
            fact_point = [
                fact.get("location_link_resolution", {}).get("longitude"),
                fact.get("location_link_resolution", {}).get("latitude"),
            ]
        else:
            fact_point = [
                fact.get("longitude_decimal"),
                fact.get("latitude_decimal"),
            ]
        if (
            entity["geometry"] != {"type": "Point", "coordinates": expected_point}
            or [entity["longitude"], entity["latitude"]] != expected_point
            or fact_point != expected_point
        ):
            raise VerifiedConstructionCoreError("v0.7 point transform differs")
    if project_key == "curated:aws-walqa-huesca-data-center:current-build":
        fact = evidence["fact_payload"]
        expected_lat = 42 + 6 / 60 + 49.73 / 3600
        expected_lon = -(0 + 27 / 60 + 23.17 / 3600)
        if fact.get("latitude_decimal") != expected_lat or fact.get("longitude_decimal") != expected_lon:
            raise VerifiedConstructionCoreError("v0.7 Walqa DMS conversion differs")
    if project_key == "curated:atnorth-swe02-stockholm-campus:current-development":
        transform_fact = evidence["fact_payload"].get("coordinate_transform", {})
        source_point = evidence["fact_payload"].get("source_map_point", {})
        if (
            source_point != {"crs": "EPSG:3011", "x": 145404.34988421336, "y": 6589480.87816898}
            or transform_fact.get("tool") != "pyproj 3.7.2 / PROJ 9.5.1"
            or transform_fact.get("longitude") != 17.919052862381037
            or transform_fact.get("latitude") != 59.42019318407011
        ):
            raise VerifiedConstructionCoreError("v0.7 SWE02 transform differs")
    portable_capture = acceptance["portable_capture_binding"]
    if project_key == "curated:colt-villebon-sur-yvette-campus:paris2-current-facility-build":
        if bridge["geometry_capture"] != {
            field: portable_capture[field] for field in ("path", "bytes", "sha256")
        }:
            raise VerifiedConstructionCoreError("v0.7 Colt capture binding differs")
        _validate_v07_colt_capture(bridge, portable_capture)
    elif project_key == "curated:microsoft-san-bovio-italy-datacenter:initial-development":
        if bridge["geometry_capture"] != portable_capture:
            raise VerifiedConstructionCoreError("v0.7 San capture binding differs")
        _validate_v07_san_capture(bridge, portable_capture)
    elif bridge["geometry_capture"] is not None or portable_capture is not None:
        raise VerifiedConstructionCoreError("v0.7 compact-fact capture posture differs")
    for index, identity in enumerate(bridge["identity_bridge_evidence"]):
        _validate_v06_fact_evidence(
            identity, label=f"v0.7 identity evidence {index}"
        )
    if (
        not isinstance(bridge["claim_guardrails"], dict)
        or not bridge["claim_guardrails"]
        or any(not isinstance(value, str) or not value for value in bridge["claim_guardrails"].values())
        or not isinstance(bridge["rights"], dict)
        or bridge["imagery_posture"].get("independent_imagery_verification") is not False
    ):
        raise VerifiedConstructionCoreError("v0.7 guardrails differ")
    if project_key == "curated:microsoft-san-bovio-italy-datacenter:initial-development" and (
        bridge["rights"].get("geometry_attribution_url")
        != "https://www.openstreetmap.org/copyright"
        or bridge["rights"].get("geometry_license_url")
        != "https://opendatacommons.org/licenses/odbl/1-0/"
    ):
        raise VerifiedConstructionCoreError("v0.7 OSM rights differ")
    if project_key == "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2" and (
        entity.get("country") != "Korea, Republic of"
        or "SEL2" not in decision.get("identity_basis", "")
        or "adjacent" not in decision.get("identity_basis", "")
    ):
        raise VerifiedConstructionCoreError("v0.7 SEL3 shared-campus identity differs")
    return bridge, source


def _v07_contracts(*, hydrated_crosscheck: bool) -> dict[str, Any]:
    _validate_v07_definition_pins()
    reviewed = _load_json(
        ROOT / "definitions/verified-construction-core-v0.7-reviewed-sites.json"
    )
    overlays = _load_json(
        ROOT / "definitions/verified-construction-core-reviewed-overlays-v5.json"
    )
    provenance = _load_json(
        ROOT / "definitions/verified-construction-core-v0.7-provenance.json"
    )
    imagery = _load_json(
        ROOT / "definitions/verified-construction-core-v0.7-imagery-reviews.json"
    )
    if (
        set(reviewed) != {"contract_id", "review_scope", "reviewed_as_of", "base_contract", "acceptances"}
        or reviewed.get("contract_id") != "verified-construction-core-v0.7-reviewed-sites"
        or reviewed.get("reviewed_as_of") != CURRENT_V07_REVIEW_DATE.isoformat()
        or reviewed.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.6-reviewed-sites.json",
            "sha256": V06_REVIEW_DEFINITION_SHA256,
            "default_geometry_entity": "project",
            "default_geometry_derivation": "direct_geometry",
        }
        or not isinstance(reviewed.get("acceptances"), list)
        or len(reviewed["acceptances"]) != 7
    ):
        raise VerifiedConstructionCoreError("v0.7 reviewed-site contract differs")
    if (
        set(overlays)
        != {"contract_id", "purpose", "reviewed_as_of", "base_contract", "required_fields", "allowed_decisions", "overlays"}
        or overlays.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v5"
        or overlays.get("reviewed_as_of") != CURRENT_V07_REVIEW_DATE.isoformat()
        or overlays.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-reviewed-overlays-v4.json",
            "sha256": V06_OVERLAY_DEFINITION_SHA256,
        }
        or set(overlays.get("allowed_decisions", [])) != {"queued", "accepted", "excluded"}
        or not isinstance(overlays.get("overlays"), list)
        or len(overlays["overlays"]) != 7
    ):
        raise VerifiedConstructionCoreError("v0.7 overlay contract differs")
    required_overlay_fields = set(overlays["required_fields"])
    if required_overlay_fields != V07_OVERLAY_REQUIRED_FIELDS:
        raise VerifiedConstructionCoreError("v0.7 overlay required fields differ")
    if any(not isinstance(row, dict) or set(row) != required_overlay_fields for row in overlays["overlays"]):
        raise VerifiedConstructionCoreError("v0.7 overlay row schema differs")
    acceptances = reviewed["acceptances"]
    acceptance_by_key = {row.get("project_stable_key"): row for row in acceptances}
    overlay_by_key = {row.get("source_project_stable_key"): row for row in overlays["overlays"]}
    if (
        len(acceptance_by_key) != 7
        or len(overlay_by_key) != 7
        or set(acceptance_by_key) != set(overlay_by_key)
    ):
        raise VerifiedConstructionCoreError("v0.7 definition cohort differs")
    bridges: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    for project_key in sorted(acceptance_by_key):
        acceptance = acceptance_by_key[project_key]
        overlay = overlay_by_key[project_key]
        crosswalk = {
            "country": "country",
            "physical_site_stable_key": "physical_site_stable_key",
            "physical_site_entity_id": "physical_site_entity_id",
            "source_input_path": "source_input_path",
            "source_input_bytes": "source_input_bytes",
            "source_input_sha256": "source_input_sha256",
            "bridge_id": "bridge_id",
            "bridge_schema": "bridge_schema",
            "bridge_path": "bridge_path",
            "bridge_bytes": "bridge_bytes",
            "bridge_sha256": "bridge_sha256",
            "project_to_campus_relationship_id": "project_to_campus_relationship_id",
            "project_to_campus_relationship_type": "project_to_campus_relationship_type",
            "project_to_campus_decision_basis": "project_to_campus_decision_basis",
            "geometry_entity": "geometry_entity",
            "geometry_entity_stable_key": "geometry_entity_stable_key",
            "geometry_entity_id": "geometry_entity_id",
            "geometry_evidence_key": "geometry_evidence_key",
            "geometry_evidence_id": "geometry_evidence_id",
            "geometry_source_kind": "geometry_source_kind",
            "geometry_derivation": "geometry_derivation",
            "geometry_method": "geometry_method",
            "geometry_scope_class": "geometry_scope_class",
            "geometry_authority_class": "geometry_authority_class",
            "geometry_use_scope": "geometry_use_scope",
            "official_boundary": "official_boundary",
            "horizontal_uncertainty_metres": "horizontal_uncertainty_metres",
            "horizontal_uncertainty_unknown_reason": "horizontal_uncertainty_unknown_reason",
            "precision_scope": "precision_scope",
            "bridge_decision": "bridge_decision",
            "portable_input_binding": "portable_input_binding",
            "portable_capture_binding": "portable_capture_binding",
            "rejected_claims": "rejected_claims",
        }
        if (
            any(acceptance[a] != overlay[o] for a, o in crosswalk.items())
            or acceptance["project_entity_id"] != overlay["source_project_entity_id"]
            or acceptance["project_stable_key"] != overlay["source_project_stable_key"]
            or acceptance["geometry_overlay_id"] != overlay["overlay_id"]
            or acceptance["decision_basis"] != overlay["decision_reason"]
            or overlay["decision"] != "accepted"
            or overlay["reviewed_at"] != CURRENT_V07_REVIEW_DATE.isoformat()
        ):
            raise VerifiedConstructionCoreError("v0.7 acceptance-overlay binding differs")
        bridge, source = _validate_v07_bridge(
            acceptance, overlay, hydrated_crosscheck=hydrated_crosscheck
        )
        bridges[project_key] = bridge
        sources[project_key] = source
    if (
        provenance.get("contract_id") != "verified-construction-core-v0.7-provenance"
        or provenance.get("reviewed_as_of") != CURRENT_V07_REVIEW_DATE.isoformat()
        or provenance.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.6-provenance.json",
            "sha256": V06_PROVENANCE_DEFINITION_SHA256,
        }
        or len(provenance.get("workload_scope_bindings", [])) != 3
        or len(provenance.get("role_bindings", [])) != 1
        or len(provenance.get("excluded_source_roles", [])) != 1
    ):
        raise VerifiedConstructionCoreError("v0.7 provenance contract differs")
    workload_keys = {
        (row["project_stable_key"], row["evidence_id"], row["workload"])
        for row in provenance["workload_scope_bindings"]
    }
    expected_workloads = {
        (
            "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it",
            "f9be097a-99d8-5f60-9672-146a49d37f53",
            workload,
        )
        for workload in ("ai_specialized_unspecified", "general_cloud", "hpc")
    }
    role = provenance["role_bindings"][0]
    exclusion = provenance["excluded_source_roles"][0]
    if (
        workload_keys != expected_workloads
        or any(row.get("deployment_scope") != "intended" for row in provenance["workload_scope_bindings"])
        or (role["project_stable_key"], role["role"], role["party"], role["relationship_scope"])
        != (
            "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it",
            "operator",
            "Alto Infrastructure",
            "intended",
        )
        or (exclusion["project_stable_key"], exclusion["role"], exclusion["party"], exclusion["relationship_scope"])
        != (
            "curated:aws-walqa-huesca-data-center:current-build",
            "operator",
            "Amazon Web Services",
            "not_established",
        )
    ):
        raise VerifiedConstructionCoreError("v0.7 provenance semantics differ")
    for project_key, bridge in bridges.items():
        source_roles = _v07_source_roles(bridge["construction_source"]["project"])
        accepted = {
            (row["role"], row["party"])
            for row in provenance["role_bindings"]
            if row["project_stable_key"] == project_key
        }
        excluded = {
            (row["role"], row["party"])
            for row in provenance["excluded_source_roles"]
            if row["project_stable_key"] == project_key
        }
        observed = {(role_name, party) for role_name, parties in source_roles.items() for party in parties}
        if observed != accepted | excluded:
            raise VerifiedConstructionCoreError("v0.7 source role coverage differs")
    if (
        imagery.get("contract_id") != "verified-construction-core-v0.7-imagery-reviews"
        or imagery.get("reviewed_as_of") != CURRENT_V07_REVIEW_DATE.isoformat()
        or imagery.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.6-imagery-reviews.json",
            "sha256": V06_IMAGERY_REVIEW_DEFINITION_SHA256,
        }
        or imagery.get("default_outcome") != "not_reviewed_for_core_preview"
        or len(imagery.get("records", [])) != 1
    ):
        raise VerifiedConstructionCoreError("v0.7 imagery contract differs")
    image = imagery["records"][0]
    primary_path = _repository_input(
        image["primary_review_source_path"],
        image["primary_review_source_sha256"],
        "v0.7 imagery review",
    )
    primary = _load_json(primary_path)
    matches = [
        row
        for row in primary.get("lineage_records", [])
        if row.get("blind_id") == image["primary_blind_id"]
    ]
    if (
        image.get("project_stable_key")
        != "curated:aws-walqa-huesca-data-center:current-build"
        or image.get("portable_identity_binding") is not False
        or image.get("primary_blind_id") != "V57-S003"
        or image.get("primary_queue_id") != "satq-78500568b1f6227789ae36f4"
        or image.get("source_comparison_sha256")
        != "c383fcd9f922a2b232ea72f58694517273ec9cc986077f541641eff4a51ba123"
        or image.get("primary_verdict")
        != {"semantics": "reject_imagery_promotion", "visual_verdict": "R"}
        or image.get("independent_imagery_verification") is not False
        or image.get("no_claim_guardrail") is not True
        or len(matches) != 1
        or matches[0].get("queue_id") != image["primary_queue_id"]
        or matches[0].get("visual_verdict") != "R"
        or matches[0].get("source_visual_artifacts", {}).get("comparison.png", {}).get("sha256")
        != image["source_comparison_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.7 Walqa imagery lineage differs")
    local = image["local_identity_lineage"]
    local_path = ROOT / local["singleton_ready_path"]
    if local_path.exists():
        if local_path.is_symlink() or _sha256_file(local_path) != local["singleton_ready_sha256"]:
            raise VerifiedConstructionCoreError("v0.7 Walqa local imagery lineage differs")
        lines = local_path.read_bytes().splitlines(keepends=True)
        line_number = local["singleton_ready_line_number"]
        if not 1 <= line_number <= len(lines) or _sha256_bytes(lines[line_number - 1]) != local["singleton_ready_line_sha256"]:
            raise VerifiedConstructionCoreError("v0.7 Walqa local imagery line differs")
    return {
        "reviewed": reviewed,
        "overlays": overlays,
        "provenance": provenance,
        "imagery": imagery,
        "acceptance_by_key": acceptance_by_key,
        "overlay_by_key": overlay_by_key,
        "bridges": bridges,
        "sources": sources,
    }


def _v07_evidence_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: (row.get(field) if row.get(field) is not None else "")
        for field in EVIDENCE_FIELDS
        if field not in {"roles_json", "project_ids_json"}
    }


def _v07_build_delta_rows(contracts: Mapping[str, Any]) -> dict[str, Any]:
    provenance = contracts["provenance"]
    imagery = contracts["imagery"]
    workload_by_key = {
        (row["project_stable_key"], row["evidence_id"], row["workload"]): row
        for row in provenance["workload_scope_bindings"]
    }
    roles_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provenance["role_bindings"]:
        roles_by_project[row["project_stable_key"]].append(row)
    image_by_project = {row["project_stable_key"]: row for row in imagery["records"]}
    evidence_pool: dict[str, dict[str, Any]] = {}
    evidence_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    projects: list[dict[str, Any]] = []
    sites: list[dict[str, Any]] = []
    for project_key in sorted(contracts["bridges"]):
        bridge = contracts["bridges"][project_key]
        source = contracts["sources"][project_key]
        acceptance = contracts["acceptance_by_key"][project_key]
        construction = bridge["construction_source"]
        source_evidence = _v07_source_evidence(source)
        evidence_pool.update(source_evidence)
        geometry_evidence = _v07_evidence_projection(bridge["geometry_evidence"])
        evidence_pool[geometry_evidence["evidence_id"]] = geometry_evidence
        project = construction["project"]
        campus = construction["campus"]
        project_id = project["entity_id"]
        site_id = _stable_id("vcc-site", campus["stable_key"])
        status_evidence_id = project["status_evidence_id"]
        geometry_evidence_id = bridge["geometry_evidence"]["evidence_id"]
        evidence_usage[status_evidence_id]["roles"].add("physical_status")
        evidence_usage[status_evidence_id]["project_ids"].add(project_id)
        evidence_usage[geometry_evidence_id]["roles"].add("geometry")
        evidence_usage[geometry_evidence_id]["project_ids"].add(project_id)
        observations = project.get("capacity_estimates_json", [])
        if not isinstance(observations, list):
            raise VerifiedConstructionCoreError("v0.7 capacity observations differ")
        for observation in observations:
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
            evidence_id = observation["evidence_id"]
            if evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError("v0.7 capacity evidence differs")
            evidence_usage[evidence_id]["roles"].add(
                f"typed_metric:{observation['metric']}"
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        power = [row for row in observations if row["metric"] in POWER_METRICS]
        energy = [row for row in observations if row["metric"] in ENERGY_METRICS]
        efficiency = [row for row in observations if row["metric"] in EFFICIENCY_METRICS]
        workloads: list[dict[str, Any]] = []
        for source_workload in project.get("workloads_json", []):
            binding = workload_by_key.get(
                (project_key, source_workload["evidence_id"], source_workload["workload"])
            )
            if binding is None or any(
                source_workload[field] != binding[field]
                for field in SOURCE_WORKLOAD_FIELDS
            ):
                raise VerifiedConstructionCoreError("v0.7 workload provenance differs")
            workload = {**source_workload, "deployment_scope": binding["deployment_scope"]}
            _validate_workload_observation(workload)
            workloads.append(workload)
            evidence_id = workload["evidence_id"]
            evidence_usage[evidence_id]["roles"].update(
                {"workload", f"workload_scope:{workload['deployment_scope']}"}
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        role_claims: list[dict[str, str]] = []
        projected_roles = {role: [] for role in ROLE_COLUMNS}
        for binding in roles_by_project.get(project_key, []):
            evidence_id = binding["evidence_id"]
            if evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError("v0.7 role evidence differs")
            role_claims.append(
                {
                    "evidence_id": evidence_id,
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
            )
            projected_roles[binding["role"]].append(binding["party"])
            evidence_usage[evidence_id]["roles"].add(f"role:{binding['role']}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        role_claims.sort(key=lambda row: (row["role"], row["party"], row["evidence_id"]))
        entity = bridge["geometry_entity"]
        geometry = entity["geometry"]
        status_date = _calendar_date(project["status_as_of"], "v0.7 status_as_of")
        image = image_by_project.get(project_key)
        image_outcome = (
            image["outcome"]
            if image is not None
            else imagery["default_outcome"]
        )
        row = {
            "project_id": project_id,
            "project_stable_key": project_key,
            "site_id": site_id,
            "physical_site_stable_key": campus["stable_key"],
            "name": project["name"],
            "country": acceptance["country"],
            "country_iso_a2": V07_COUNTRY_ISO_A2[acceptance["country"]],
            "latitude": entity["latitude"],
            "longitude": entity["longitude"],
            "geometry_json": _json_bytes(geometry).decode().strip(),
            "geometry_type": geometry["type"],
            "geometry_source_entity_kind": acceptance["geometry_entity"],
            "geometry_derivation": acceptance["geometry_derivation"],
            "geometry_method": acceptance["geometry_method"],
            "geometry_scope_class": acceptance["geometry_scope_class"],
            "geometry_authority_class": acceptance["geometry_authority_class"],
            "geometry_use_scope": acceptance["geometry_use_scope"],
            "geometry_precision_scope": acceptance["precision_scope"],
            "horizontal_uncertainty_metres": (
                "" if acceptance["horizontal_uncertainty_metres"] is None else acceptance["horizontal_uncertainty_metres"]
            ),
            "horizontal_uncertainty_unknown_reason": acceptance["horizontal_uncertainty_unknown_reason"],
            "geometry_evidence_id": geometry_evidence_id,
            "last_observed_physical_status": project["status"],
            "status_as_of": project["status_as_of"],
            "status_age_days_at_review": (CURRENT_V07_REVIEW_DATE - status_date).days,
            "status_method": project["status_method"],
            "status_evidence_id": status_evidence_id,
            "verification_posture": _verification_posture(
                acceptance["geometry_authority_class"], acceptance["geometry_use_scope"]
            ),
            "independent_imagery_verification": "false",
            "imagery_review_outcome": image_outcome,
            "development_type": "unknown",
            "development_type_unknown_reason": "source evidence does not distinguish greenfield, expansion, or retrofit",
            "operating_model": project.get("operating_model") or "unknown",
            "operating_model_unknown_reason": (
                "" if project.get("operating_model") else "not established by selected evidence"
            ),
            "operating_model_evidence_id": project.get("operating_model_evidence_id") or "",
            "workloads_json": _json_bytes(workloads).decode().strip(),
            "workload_unknown_reason": "" if workloads else "not established by selected evidence",
            "role_claims_json": _json_bytes(role_claims).decode().strip(),
            "power_observations_json": _json_bytes(power).decode().strip(),
            "power_unknown_reason": "" if power else "no typed project power observation; not estimated",
            "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
            "annual_energy_unknown_reason": "" if energy else "no scoped annual-energy inputs; not estimated",
            "efficiency_observations_json": _json_bytes(efficiency).decode().strip(),
            "efficiency_unknown_reason": "" if efficiency else "no scoped PUE or WUE observation",
            "owner": "; ".join(sorted(projected_roles["owner"])),
            "operator": "; ".join(sorted(projected_roles["operator"])),
            "users": "; ".join(sorted(projected_roles["user"])),
            "tenants": "; ".join(sorted(projected_roles["tenant"])),
            "customers": "; ".join(sorted(projected_roles["customer"])),
            "status_source_url": evidence_pool[status_evidence_id]["source_url"],
            "geometry_source_url": geometry_evidence["source_url"],
        }
        projects.append(row)
        sites.append(
            {
                "site_id": site_id,
                "physical_site_stable_key": campus["stable_key"],
                "name": campus["name"],
                "country": row["country"],
                "country_iso_a2": row["country_iso_a2"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "geometry_json": row["geometry_json"],
                "geometry_type": row["geometry_type"],
                "geometry_source_entity_kinds_json": _json_bytes([row["geometry_source_entity_kind"]]).decode().strip(),
                "geometry_derivations_json": _json_bytes([row["geometry_derivation"]]).decode().strip(),
                "geometry_methods_json": _json_bytes([row["geometry_method"]]).decode().strip(),
                "geometry_scope_classes_json": _json_bytes([row["geometry_scope_class"]]).decode().strip(),
                "geometry_authority_classes_json": _json_bytes([row["geometry_authority_class"]]).decode().strip(),
                "geometry_use_scopes_json": _json_bytes([row["geometry_use_scope"]]).decode().strip(),
                "geometry_precision_scopes_json": _json_bytes([row["geometry_precision_scope"]]).decode().strip(),
                "horizontal_uncertainty_metres": row["horizontal_uncertainty_metres"],
                "horizontal_uncertainty_unknown_reason": row["horizontal_uncertainty_unknown_reason"],
                "geometry_evidence_ids_json": _json_bytes([geometry_evidence_id]).decode().strip(),
                "project_count": 1,
                "project_ids_json": _json_bytes([project_id]).decode().strip(),
                "project_stable_keys_json": _json_bytes([project_key]).decode().strip(),
                "statuses_json": _json_bytes([row["last_observed_physical_status"]]).decode().strip(),
                "oldest_status_as_of": row["status_as_of"],
                "newest_status_as_of": row["status_as_of"],
                "verification_posture": row["verification_posture"],
                "independent_imagery_verification": "false",
                "imagery_review_outcomes_json": _json_bytes([image_outcome]).decode().strip(),
            }
        )
    evidence = [
        {
            **evidence_pool[evidence_id],
            "roles_json": _json_bytes(sorted(usage["roles"])).decode().strip(),
            "project_ids_json": _json_bytes(sorted(usage["project_ids"])).decode().strip(),
        }
        for evidence_id, usage in sorted(evidence_usage.items())
    ]
    return {"projects": projects, "sites": sites, "evidence": evidence}


def _v07_portable_source_inputs(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    base_manifest = _load_json(LEGACY_PREVIEW_V06_DIR / "manifest.json")
    rows = list(base_manifest["portable_source_inputs"])
    new: dict[str, dict[str, Any]] = {}
    for acceptance in contracts["reviewed"]["acceptances"]:
        for binding in (
            acceptance["portable_input_binding"],
            {
                "path": acceptance["bridge_path"],
                "bytes": acceptance["bridge_bytes"],
                "sha256": acceptance["bridge_sha256"],
            },
            acceptance["portable_capture_binding"],
        ):
            if binding is None:
                continue
            record = {
                "path": binding["path"],
                "bytes": binding["bytes"],
                "sha256": binding["sha256"],
                "parent_manifests": [],
            }
            previous = new.get(record["path"])
            if previous is not None and previous != record:
                raise VerifiedConstructionCoreError("v0.7 portable input differs")
            new[record["path"]] = record
    rows.extend(new.values())
    rows.sort(key=lambda row: row["path"])
    if len(rows) != 41 or len({row["path"] for row in rows}) != 41:
        raise VerifiedConstructionCoreError("v0.7 portable input count differs")
    for row in rows:
        path = _repository_input(row["path"], row["sha256"], "v0.7 portable input")
        if path.stat().st_size != row["bytes"]:
            raise VerifiedConstructionCoreError("v0.7 portable input byte count differs")
    return rows


def _v07_map_attribution_notices(
    evidence: Sequence[Mapping[str, Any]],
) -> tuple[tuple[str, str, str], ...]:
    families = {
        row["source_family"]
        for row in evidence
        if "geometry" in json.loads(row["roles_json"])
    }
    notices = list(_map_attribution_notices(evidence))
    if "etalab_dgfip_cadastre_geojson" in families:
        notices.append(
            (
                "Direction générale des Finances publiques (DGFiP) — Cadastre Etalab — millésime 1 June 2026",
                "Licence Ouverte 2.0",
                "https://www.data.gouv.fr/pages/legal/licences/etalab-2.0",
            )
        )
    if "hong_kong_lands_department_coordinate_transformation_api" in families:
        notices.append(
            (
                "Government of the Hong Kong SAR — Lands Department",
                "DATA.GOV.HK Terms of Use",
                "https://data.gov.hk/en/terms-and-conditions",
            )
        )
    if families & {
        "latvia_vzd_address_register",
        "latvia_vzd_cadastre_and_lvrtc_site_records",
    }:
        notices.append(
            (
                "Valsts zemes dienests (State Land Service of Latvia)",
                "CC BY 4.0",
                "https://www.vzd.gov.lv/en",
            )
        )
    if "denver_open_data_property_parcels" in families:
        notices.append(
            (
                "City and County of Denver",
                "CC BY 3.0",
                "https://www.denvergov.org/opendata",
            )
        )
    return tuple(notices)


def _v07_map_html(
    geojson: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> bytes:
    document = _map_html(geojson, evidence).decode("utf-8")
    document = document.replace(
        "Verified Construction Core v0.6 preview",
        "Verified Construction Core v0.7 preview",
    )
    old = " · ".join(
        f'<a href="{url}">{label}</a> — {license_name}'
        for label, license_name, url in _map_attribution_notices(evidence)
    )
    new = " · ".join(
        f'<a href="{url}">{label}</a> — {license_name}'
        for label, license_name, url in _v07_map_attribution_notices(evidence)
    )
    if old not in document:
        raise VerifiedConstructionCoreError("v0.7 map attribution seam differs")
    return document.replace(old, new, 1).encode("utf-8")


def _v07_schema() -> dict[str, Any]:
    schema = _schema()
    schema["format"] = "datacenter-atlas-verified-construction-core-schema-v7"
    schema["preview_id"] = CURRENT_V07_PREVIEW_ID
    fields = schema["tables"]["projects.csv"]["fields"]
    derivation = next(row for row in fields if row["name"] == "geometry_derivation")
    derivation["allowed_values"] = [
        "capture_replayed_geometry",
        "coordinates_to_point",
        "cross_source_geometry",
        "cross_source_overlay",
        "direct_geometry",
        "official_parcel_union",
    ]
    schema["map"]["derived_from"] = ["sites.geojson", "evidence.csv"]
    return schema


def _v07_readme(report: Mapping[str, Any]) -> bytes:
    return f"""# Verified Construction Core v0.7 preview

This tracked, non-final preview contains **{report['selected_physical_site_count']} physical sites**
and **{report['selected_project_count']} linked projects** in {len(report['country_counts'])}
countries. Every project retains a dated authoritative physical-status observation and an exact
reviewed geometry scope. Five project rows carry official boundaries; the remaining 31 are
explicit project or campus locators, never construction footprints by implication.

The seven-row v0.7 delta adds Colt PAR2, AWS Walqa, atNorth SWE02, Alto SP01, Teraco CT1,
Digital Edge SEL3, and Microsoft San Bovio. Colt uses an Etalab cadastral parcel as its official
project boundary. Walqa, SWE02, Alto, Teraco, and SEL3 use narrowly scoped official-source points.
SEL3 inherits only a shared-campus locator from adjacent SEL2. San Bovio uses a capture-replayed
OpenStreetMap former-industrial-site polygon only as a community-mapped campus locator.

Alto contributes three intended-only workloads and one intended-operator claim. AWS branding and
its campus operating model do not establish a project operator. Walqa's V57-S003 imagery verdict
remains a locally unsealed blind rejection and creates no construction, identity, geometry, role,
workload, capacity, or lifecycle claim.

The artifact is deterministic and rebuildable in a clean clone from the 41 manifest-bound portable
inputs plus the frozen v0.6 artifact. Ignored v97, global-v3, and v14 payloads are optional hydrated
cross-checks, not build dependencies. Missing power, energy, PUE, WUE, workloads, roles, operating
models, and development types remain explicit unknowns rather than zero.

This is not the final 100-site Verified Construction Core v1. Its final-release gates remain
unsatisfied and `publishable_as_final` is false.
""".encode("utf-8")


def _v07_attribution(evidence: Sequence[Mapping[str, Any]]) -> bytes:
    rows = {(row["publisher"], row["license"], row["source_url"]) for row in evidence}
    lines = [
        "Data Center Atlas Verified Construction Core v0.7 preview",
        "",
        "Compact derived facts only; third-party terms remain controlling.",
        "",
        *(
            f"- {publisher} | {license_name} | {url}"
            for publisher, license_name, url in sorted(rows)
        ),
        "",
        "Map-provider terms:",
        *(
            f"- {label} | {license_name} | {url}"
            for label, license_name, url in _v07_map_attribution_notices(evidence)
        ),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _v07_payloads() -> tuple[dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
    validate_frozen_v06(LEGACY_PREVIEW_V06_DIR)
    contracts = _v07_contracts(
        hydrated_crosscheck=_v07_hydrated_crosscheck_available()
    )
    base_projects = _load_csv(LEGACY_PREVIEW_V06_DIR / "projects.csv", PROJECT_FIELDS)
    base_sites = _load_csv(LEGACY_PREVIEW_V06_DIR / "sites.csv", SITE_FIELDS)
    base_evidence = _load_csv(LEGACY_PREVIEW_V06_DIR / "evidence.csv", EVIDENCE_FIELDS)
    base_report = _load_json(LEGACY_PREVIEW_V06_DIR / "selection-report.json")
    delta = _v07_build_delta_rows(contracts)
    projects = sorted([*base_projects, *delta["projects"]], key=lambda row: row["project_stable_key"])
    sites = sorted([*base_sites, *delta["sites"]], key=lambda row: row["physical_site_stable_key"])
    evidence = sorted([*base_evidence, *delta["evidence"]], key=lambda row: row["evidence_id"])
    if (
        len(projects) != 36
        or len(sites) != 33
        or len(evidence) != 79
        or len({row["project_id"] for row in projects}) != 36
        or len({row["site_id"] for row in sites}) != 33
        or len({row["evidence_id"] for row in evidence}) != 79
    ):
        raise VerifiedConstructionCoreError("v0.7 cohort count or uniqueness differs")
    gates = _final_release_gates(sites, projects)
    gates["clean_clone_rebuild"] = {
        "passed": True,
        "reason": "all current-delta inputs and the frozen base artifact are tracked and hash-bound",
    }
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    report = {
        **base_report,
        "format": "datacenter-atlas-verified-construction-core-selection-v7",
        "publishable_as_final": all(gate.get("passed", False) for gate in gates.values()),
        "reviewed_at": CURRENT_V07_REVIEW_DATE.isoformat(),
        "selected_project_count": 36,
        "selected_physical_site_count": 33,
        "official_boundary_project_count": 5,
        "reviewed_site_locator_project_count": 31,
        "non_selected_source_row_count": 495,
        "selection_first_failure_counts": V07_SELECTION_FIRST_FAILURE_COUNTS,
        "country_counts": country_counts,
        "final_release_gates": gates,
        "imagery_review_provenance": [
            *base_report["imagery_review_provenance"],
            *contracts["imagery"]["records"],
        ],
        "provenance_decisions": {
            key: [
                *base_report["provenance_decisions"][key],
                *contracts["provenance"][key],
            ]
            for key in ("workload_scope_bindings", "role_bindings", "excluded_source_roles")
        },
        "reviewed_overlay_queue": [
            *base_report["reviewed_overlay_queue"],
            *contracts["overlays"]["overlays"],
        ],
    }
    if (
        len(country_counts) != 23
        or sum(row["country_iso_a2"] != "US" for row in sites) != 27
        or sum(_is_official_boundary(row) for row in projects) != 5
        or sum(_is_reviewed_locator(row) for row in projects) != 31
        or sum(V07_SELECTION_FIRST_FAILURE_COUNTS.values()) != 531
    ):
        raise VerifiedConstructionCoreError("v0.7 expected accounting differs")
    geojson = _geojson(sites)
    geojson["name"] = "Data Center Atlas Verified Construction Core v0.7 preview"
    payloads = {
        "ATTRIBUTION.txt": _v07_attribution(evidence),
        "README.md": _v07_readme(report),
        "evidence.csv": _csv_bytes(evidence, EVIDENCE_FIELDS),
        "map.html": _v07_map_html(geojson, evidence),
        "projects.csv": _csv_bytes(projects, PROJECT_FIELDS),
        "schema.json": _json_bytes(_v07_schema()),
        "selection-report.json": _json_bytes(report),
        "sites.csv": _csv_bytes(sites, SITE_FIELDS),
        "sites.geojson": _json_bytes(geojson),
    }
    portable = _v07_portable_source_inputs(contracts)
    return payloads, report, portable


def _v07_manifest(
    payloads: Mapping[str, bytes],
    report: Mapping[str, Any],
    portable: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-verified-construction-core-preview-v7",
        "preview_id": CURRENT_V07_PREVIEW_ID,
        "release_status": "preview",
        "publishable_as_final": report["publishable_as_final"],
        "base_preview_id": "2026-08-20-preview-v0.6",
        "base_preview_manifest_sha256": LEGACY_PREVIEW_V06_MANIFEST_SHA256,
        "base_preview_commit": LEGACY_PREVIEW_V06_COMMIT,
        "source_release_id": SOURCE_RELEASE_ID,
        "source_release_manifest_path": "releases/2026-07-22-open-seed-v97/manifest.json",
        "source_release_manifest_sha256": "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
        "definition_paths": {
            "imagery_reviews": "definitions/verified-construction-core-v0.7-imagery-reviews.json",
            "provenance": "definitions/verified-construction-core-v0.7-provenance.json",
            "reviewed_overlays": "definitions/verified-construction-core-reviewed-overlays-v5.json",
            "reviewed_sites": "definitions/verified-construction-core-v0.7-reviewed-sites.json",
        },
        "review_definition_sha256": V07_REVIEW_DEFINITION_SHA256,
        "imagery_review_definition_sha256": V07_IMAGERY_REVIEW_DEFINITION_SHA256,
        "provenance_definition_sha256": V07_PROVENANCE_DEFINITION_SHA256,
        "overlay_definition_sha256": V07_OVERLAY_DEFINITION_SHA256,
        "portable_source_inputs": list(portable),
        "reviewed_at": CURRENT_V07_REVIEW_DATE.isoformat(),
        "counts": {
            "physical_sites": 33,
            "projects": 36,
            "evidence": 79,
            "countries": 23,
            "non_us_sites": 27,
            "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 31,
        },
        "files": {
            name: {"bytes": len(payload), "sha256": _sha256_bytes(payload)}
            for name, payload in sorted(payloads.items())
        },
    }


_build_v06_preview = build_preview
_validate_v06_preview_dispatch = validate_preview


def build_preview(output_dir: Path = CURRENT_V07_PREVIEW_DIR) -> dict[str, Any]:
    """Build the current v0.7 preview from tracked, hash-bound inputs."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise VerifiedConstructionCoreError(f"refusing to overwrite {output_dir}")
    payloads, report, portable = _v07_payloads()
    manifest = _v07_manifest(payloads, report, portable)
    manifest_bytes = _json_bytes(manifest)
    complete = {
        **payloads,
        "manifest.json": manifest_bytes,
        "manifest.sha256": f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode(),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, payload in complete.items():
            with (stage / name).open("xb") as handle:
                handle.write(payload)
        os.replace(stage, output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_preview(output_dir)
    return manifest


def _validate_v07_preview(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError("v0.7 preview directory differs")
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError("v0.7 manifest trust root differs")
    manifest_bytes = manifest_path.read_bytes()
    if checksum_path.read_bytes() != f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode():
        raise VerifiedConstructionCoreError("v0.7 manifest checksum differs")
    manifest = _load_json(manifest_path)
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("v0.7 manifest files differ")
    expected_inventory = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_inventory:
        raise VerifiedConstructionCoreError("v0.7 preview inventory differs")
    for name, metadata in files.items():
        member = path / name
        if (
            Path(name).name != name
            or member.is_symlink()
            or not member.is_file()
            or member.stat().st_size != metadata.get("bytes")
            or _sha256_file(member) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(f"v0.7 member differs: {name}")
    payloads, report, portable = _v07_payloads()
    expected_manifest = _v07_manifest(payloads, report, portable)
    if manifest != expected_manifest:
        raise VerifiedConstructionCoreError("v0.7 manifest semantics differ")
    for name, expected in payloads.items():
        if (path / name).read_bytes() != expected:
            raise VerifiedConstructionCoreError(f"v0.7 generated member differs: {name}")
    return manifest


def validate_preview(path: Path = CURRENT_V07_PREVIEW_DIR) -> dict[str, Any]:
    """Validate current v0.7 or dispatch an immutable v0.1-v0.6 preview."""
    path = Path(path)
    manifest_path = path / "manifest.json"
    if path.is_symlink() or not path.is_dir() or manifest_path.is_symlink() or not manifest_path.is_file():
        raise VerifiedConstructionCoreError("preview manifest trust root differs")
    manifest = _load_json(manifest_path)
    preview_id = manifest.get("preview_id") if isinstance(manifest, dict) else None
    if preview_id == CURRENT_V07_PREVIEW_ID:
        return _validate_v07_preview(path)
    if _frozen_preview_validator(preview_id) is not None:
        return validate_frozen_preview(path)
    raise VerifiedConstructionCoreError("preview id differs")


__all__ = [
    "CURRENT_V07_DEFINITION_PATHS",
    "CURRENT_V07_PREVIEW_DIR",
    "CURRENT_V07_PREVIEW_ID",
    "CURRENT_V07_REVIEW_DATE",
    "IMAGERY_REVIEW_DEFINITION",
    "LEGACY_PREVIEW_V01_DIR",
    "LEGACY_PREVIEW_V02_DIR",
    "LEGACY_PREVIEW_V03_DIR",
    "LEGACY_PREVIEW_V04_DIR",
    "LEGACY_PREVIEW_V05_COMMIT",
    "LEGACY_PREVIEW_V05_DIR",
    "LEGACY_PREVIEW_V06_COMMIT",
    "LEGACY_PREVIEW_V06_DIR",
    "LEGACY_PREVIEW_V06_MANIFEST_SHA256",
    "PREVIEW_DIR",
    "PreviewProfile",
    "PROVENANCE_DEFINITION",
    "VerifiedConstructionCoreError",
    "build_preview",
    "load_current_v07_profile",
    "validate_frozen_preview",
    "validate_frozen_v01",
    "validate_frozen_v02",
    "validate_frozen_v03",
    "validate_frozen_v04",
    "validate_frozen_v05",
    "validate_frozen_v06",
    "validate_preview",
]


_build_v07_preview = build_preview
_validate_v07_preview_dispatch = validate_preview

LEGACY_PREVIEW_V07_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.7"
)
LEGACY_PREVIEW_V07_MANIFEST_SHA256 = (
    "36d3f40d2a6ce8c4cf960adb680a3788a216552ca2e53c72fedc7aa3d5d97d6a"
)
LEGACY_PREVIEW_V07_COMMIT = "86bb4c589a0a6bf3e6d07a2a94c399b69fb016d6"
CURRENT_V08_PREVIEW_ID = "2026-08-20-preview-v0.8"
CURRENT_V08_PREVIEW_DIR = ROOT / "verified_construction_core" / CURRENT_V08_PREVIEW_ID
CURRENT_V08_REVIEW_DATE = date(2026, 8, 20)
V08_REVIEW_DEFINITION_SHA256 = (
    "8171064f679bc5c000079e88259ec7ec6379c267593c4f602ac3788ed9f8b4cb"
)
V08_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "69f2aa259fb7b5d03c2d0bda25847f74255fde182bd5b89e673bf532b9dd14b6"
)
V08_PROVENANCE_DEFINITION_SHA256 = (
    "a4a8fbda2d06a368f6030127d6f3e3eb73f22b95626e31c6719d88515f15fe48"
)
V08_OVERLAY_DEFINITION_SHA256 = (
    "e270e02e49f6d17313d32edce5d3348af9e301b407065861650fedcd7a9bdcc7"
)
V08_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.8-reviewed-sites.json"
)
V08_IMAGERY_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.8-imagery-reviews.json"
)
V08_PROVENANCE_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.8-provenance.json"
)
V08_OVERLAY_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-reviewed-overlays-v6.json"
)
CURRENT_V08_DEFINITION_PATHS = (
    ("review_definition_sha256", V08_REVIEW_DEFINITION),
    ("imagery_review_definition_sha256", V08_IMAGERY_REVIEW_DEFINITION),
    ("provenance_definition_sha256", V08_PROVENANCE_DEFINITION),
    ("overlay_definition_sha256", V08_OVERLAY_DEFINITION),
)
V08_COUNTRY_ISO_A2 = {
    "Australia": "AU",
    "Austria": "AT",
    "Germany": "DE",
    "Iceland": "IS",
    "Türkiye": "TR",
    "United Kingdom": "GB",
}
V08_SELECTION_FIRST_FAILURE_COUNTS = {
    "entity_kind_not_project": 49,
    "not_in_reviewed_site_geometry_allowlist": 99,
    "selected": 44,
    "status_not_physical": 12,
    "status_outside_90_day_window": 327,
}
V08_OVERLAY_REQUIRED_FIELDS = frozenset(
    {
        "bridge_bytes",
        "bridge_decision",
        "bridge_id",
        "bridge_path",
        "bridge_schema",
        "bridge_sha256",
        "country",
        "decision",
        "decision_reason",
        "geometry_authority_class",
        "geometry_derivation",
        "geometry_entity",
        "geometry_entity_id",
        "geometry_entity_stable_key",
        "geometry_evidence_id",
        "geometry_evidence_key",
        "geometry_method",
        "geometry_scope_class",
        "geometry_source_kind",
        "geometry_target_entity_id",
        "geometry_target_entity_kind",
        "geometry_target_entity_stable_key",
        "geometry_use_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "official_boundary",
        "overlay_id",
        "physical_site_entity_id",
        "physical_site_stable_key",
        "portable_capture_binding",
        "portable_input_binding",
        "precision_scope",
        "project_to_campus_decision_basis",
        "project_to_campus_relationship_id",
        "project_to_campus_relationship_type",
        "rejected_claims",
        "reviewed_at",
        "source_input_bytes",
        "source_input_path",
        "source_input_sha256",
        "source_project_entity_id",
        "source_project_stable_key",
    }
)
V08_BRIDGE_PROFILES = {
    "curated:borealis-blonduos-data-center-campus:expansion-current-build": {
        "bridge_sha256": "096d5b905a62ff0254c98db90d2028245b6f3c5ffd45e509517fce60d916b295",
        "geometry_projection_sha256": "0288cb983ee8bd39898ab3a946debfbb9fc61ceccbd6edcff0e237a3a4ca7c63",
        "rights_sha256": "5f21ca2812fc601cfb7583208917a17c5e5cb171b7b0d13fca17e22b2a2e6312",
        "review_decision_sha256": "8f01aa13bc02f4bbae6ca35de5ff58e4a161409e48e01443cb97745d091a75c7",
        "claim_guardrails_sha256": "d62e7eec83bcb74b61474e0405600d9b69e1363ad27999660486220b050ae521",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "9f6a3292d2c3b7df30574bd27af1837f906a60bc2de30ca43b402619d2465680",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "facility",
        "geometry_stable_key": "osm:way/1227173411",
        "target_kind": "campus",
        "target_stable_key": "curated:borealis-blonduos-data-center-campus",
        "geometry_evidence_id": "b24c0246-2488-55e4-9022-3609124fd8c8",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": -20.24300365,
        "latitude": 65.64727965,
    },
    "curated:cdc-laverton-melbourne-campus:current-build": {
        "bridge_sha256": "c6d0058184bdecdeb175e18b0c72c5c31ef9cee26ee735abc9d90239e2967f82",
        "geometry_projection_sha256": "88446ad2c9be9b91848504919b8ef5f88ca9279f43801b21af725762b540e5e8",
        "rights_sha256": "1f04323b5ab29f2f3ec80a9fd5a38db8a0adab5ce3c04a9004cfeed91347f7a5",
        "review_decision_sha256": "a047d1eb2c5fd315ae3e31af5d447493137d976ef4304283937177f33d2d4a7f",
        "claim_guardrails_sha256": "ca71d023349a5e2a85b8459d11df79e5885af0fe9491e5b5a9c19000996d261d",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "27f91ee149d0932fc73894a71364924dd00aed0640513f8df6af0717769309e6",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "facility",
        "geometry_stable_key": "osm:way/263915226",
        "target_kind": "campus",
        "target_stable_key": "curated:cdc-laverton-melbourne-campus",
        "geometry_evidence_id": "e07bd94a-9734-5f78-a7b6-d69e757357c2",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": 144.7753871,
        "latitude": -37.8415726,
    },
    "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build": {
        "bridge_sha256": "3b9c2f22dd3a52c4160d12904f373ab5d972eddd40f3023de8f174f24d85dcbe",
        "geometry_projection_sha256": "f49f56f20997d62fe9eee47a47d9b4fc050360d9af05baabba25aac7f4dde360",
        "rights_sha256": "f95d3ae2bfe2d41944d0918c2bf25193f541510abfed43949e79d6cdf18151b0",
        "review_decision_sha256": "9a26c9955ec05eb2551a4e2ce4bb3d0d61568144afd5f3fce900448d44848978",
        "claim_guardrails_sha256": "a183b9be6a3e91489e895e27964198c6bd3e9eada054cf2a2ea83117f81057cf",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "322e3929b2542204ed2f543fd9462f9f2cf9cd2afeb76b9448ece38a82295c9d",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "building",
        "geometry_stable_key": "osm:way/1417621831",
        "target_kind": "project",
        "target_stable_key": "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build",
        "geometry_evidence_id": "d0865f65-7e1e-59ab-989c-2d49ec5ce196",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": 8.5875645,
        "latitude": 50.124526200000005,
    },
    "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build": {
        "bridge_sha256": "24f7609d2eee8cc8d6e14412cdb2db3681539026b97f2a1ae6c2827684b41af1",
        "geometry_projection_sha256": "a39f3314397a86182d1074f6b566bb72e1178bee11155fa9365ca080e3df5241",
        "rights_sha256": "b6ac3f0a471f7b905a41b04c5d8fe73d18a767b7eb85eacfe39834266337aec6",
        "review_decision_sha256": "8f2d1e83d8c4022d1f6e36cb891bfbaab6563a0fb5a1bf3988e164e459127406",
        "claim_guardrails_sha256": "5a25977ec0fb1578248bd483a0bea48cf9ad3aaeaab83efe664ee99d0739fae6",
        "imagery_posture_sha256": "c2529484418d5da1dbacfed6ad4cbde2da340618680dee45966f03818a101642",
        "source_sha256": "ddf94f3bbf02d4a4d9a4afeafc4c9eb5ce76f817f8d93b1f9033869801d14e4e",
        "schema": "verified-construction-core-v0.8-direct-first-party-geometry-bridge-v1",
        "geometry_kind": "project",
        "geometry_stable_key": "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build",
        "target_kind": "project",
        "target_stable_key": "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build",
        "geometry_evidence_id": "4bbf6d0c-4fcb-5dd0-9504-4322a80117b8",
        "geometry_evidence_key": "digital-realty-vie13-live-facility-page-point-captured-2026-08-20",
        "geometry_source_kind": "company_facility_page",
        "direct_source_url": "https://www.digitalrealty.com/data-centers/emea/vienna/vie13",
        "direct_source_publisher": "Digital Realty",
        "direct_source_license": "all-rights-reserved",
        "direct_source_retrieved_at": "2026-08-20T22:43:07Z",
        "direct_source_family": "digital_realty_facility_pages",
        "direct_source_kind": "company_facility_page",
        "longitude": 16.424095,
        "latitude": 48.270994,
    },
    "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build": {
        "bridge_sha256": "038899bbb54371dbdc6a9769a568366dbb1a9b2b8b939e5dc6571850b32f142d",
        "geometry_projection_sha256": "8322e698ba3f72009c3f4ad5498043bbcc7ce26aab7ae45e265ee125664b1d89",
        "rights_sha256": "b6ac3f0a471f7b905a41b04c5d8fe73d18a767b7eb85eacfe39834266337aec6",
        "review_decision_sha256": "0c4d4c1a410203fa9df4af246be94079948a6ee90e017a9e8af3c6ec8f16275d",
        "claim_guardrails_sha256": "f2df10329d983cf2830c9d063714d15af22a192888554f55f4ca7a214491bb82",
        "imagery_posture_sha256": "c2529484418d5da1dbacfed6ad4cbde2da340618680dee45966f03818a101642",
        "source_sha256": "9d8f0924edde254b9a4aaa2b9e84afcfccecddb3ebd8c320aa16dcc95d31a4cf",
        "schema": "verified-construction-core-v0.8-direct-first-party-geometry-bridge-v1",
        "geometry_kind": "project",
        "geometry_stable_key": "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build",
        "target_kind": "project",
        "target_stable_key": "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build",
        "geometry_evidence_id": "959963fd-1d27-5927-a972-8a04fd97727e",
        "geometry_evidence_key": "enka-eds-ist01-tuzla-live-facility-page-point-captured-2026-08-20",
        "geometry_source_kind": "company_facility_page",
        "direct_source_url": "https://enkadatasolutions.com/locations/eds-ist-01-tuzla/",
        "direct_source_publisher": "ENKA Data Solutions",
        "direct_source_license": "all-rights-reserved",
        "direct_source_retrieved_at": "2026-08-20T22:43:43Z",
        "direct_source_family": "enka_data_solutions_facility_pages",
        "direct_source_kind": "company_facility_page",
        "longitude": 29.323671897992956,
        "latitude": 40.835152897406935,
    },
    "curated:equinix-mu4-munich-data-center:phase-3": {
        "bridge_sha256": "d7979e4127902b2ed5996426a1e0f3677e6cffb490a3367f4a16340ac8748faf",
        "geometry_projection_sha256": "1b9886331a90e7d8d8c374ad3643bbf9f3ca2867010483d7a31da9fec5f73e22",
        "rights_sha256": "c511f452a115e7fc1b69b80fe6069a1a3c4d79f1ed8e706d04f946f870b4b33b",
        "review_decision_sha256": "cb74f8f530c3078313cf922c4e258d4ff9d7d967f41ce9ba811935da745dabb3",
        "claim_guardrails_sha256": "ba78f4a33929db737d0256c07226f3cc8d9f9ea705f374dd96e78f7e0e05d2aa",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "87caf33997afbd8663486511815a141e6c7cb18d59ee5951648a21d3591a27d2",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "facility",
        "geometry_stable_key": "osm:way/899514480",
        "target_kind": "campus",
        "target_stable_key": "curated:equinix-mu4-munich-data-center",
        "geometry_evidence_id": "efe5b5c9-7394-5f0c-951b-051197168c49",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": 11.6824555,
        "latitude": 48.14701805,
    },
    "curated:macquarie-ic3-super-west-facility:phase-1-build": {
        "bridge_sha256": "6ba2c6a538d4d834adcceac45a080cda70391f0fcceb5b5d3420d37812caa540",
        "geometry_projection_sha256": "f4e560883e133af90207a95d436fbffb95eeec71f053eddad76844f11c44678b",
        "rights_sha256": "52c4af65d27973d84dd439dc5259fd6446edba19b55e4a0ac68c3822da5d1bf3",
        "review_decision_sha256": "827ab2b061ed3a187b041cbd266a354046515ff791e6f0370f58aacc9e649a0d",
        "claim_guardrails_sha256": "6b01772208a5e1c7e4b6bd59084d39f31683e6067a30eae38115fc80bc61e2f9",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "9fe5625d1cbb2d59dbeb8d329ab1b79fb65a7e43346161f2c92901076cc7cb4f",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "project",
        "geometry_stable_key": "osm:way/1298979790:development-project",
        "target_kind": "campus",
        "target_stable_key": "curated:macquarie-ic3-super-west-facility",
        "geometry_evidence_id": "7b2675bd-76c0-54b0-82d1-3f5d6cb328b2",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": 151.12696035,
        "latitude": -33.780962349999996,
    },
    "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build": {
        "bridge_sha256": "6cb44cf1473741da182fbd348eef4ecef6ccf53f37467cbc32728a7c03143858",
        "geometry_projection_sha256": "c27131cdd11fff31aab83f5192c85c2d126cdf177d22ab5ff6e7af4b70cc4c1a",
        "rights_sha256": "149978275e4abba2f03ca7a33e296793cb3408edd02e0c6be05649193cf1782f",
        "review_decision_sha256": "73463377039f09cd0707aebbac502670dc294c838e7f3f50e318008bee1f323d",
        "claim_guardrails_sha256": "c99c773cb4444e129918ab57cc09d1d39fd15379754dc17094045bba08c2eadd",
        "imagery_posture_sha256": "cf3a5a5f1100ce1b6972d1ba83f645b119307fe1b6c5ce91ba50484d84816493",
        "source_sha256": "792dc6b6db721fd7efd4bf00493b6546264acfe8a563b6b4ad222be282834c1d",
        "schema": "verified-construction-core-v0.8-global-v3-geometry-bridge-v1",
        "geometry_kind": "building",
        "geometry_stable_key": "osm:way/38246899",
        "target_kind": "campus",
        "target_stable_key": "curated:pure-dc-brent-cross-lon01-campus",
        "geometry_evidence_id": "ee256a2f-4e9b-5224-a6ce-e4f95c4a11ed",
        "geometry_evidence_key": None,
        "geometry_source_kind": "openstreetmap",
        "longitude": -0.23718785,
        "latitude": 51.570622900000004,
    },
}
V08_SOURCE_PROFILES = {
    "curated:borealis-blonduos-data-center-campus:expansion-current-build": {
        "v97_rows_sha256": "d7a4932a72f9b1bc80fee09cfb77a58dcd23bc18270b2e397c5991f98ae516f4",
        "topology_sha256": "11fde75491f34af08e0be60d93d59c74dd586879cd7a2ace4c16c70b3ab9e70f",
        "used_evidence_ids": ("bd494c0b-3936-5cc0-844a-67cd0db22812",),
        "used_evidence_sha256": "f34d4dfb3c8c2270d094b0804a825e40c964966bbe1444af75b39091eb7b592a",
    },
    "curated:cdc-laverton-melbourne-campus:current-build": {
        "v97_rows_sha256": "2bdd8625f73161025b25ab956b839bb340757c897bac88474c10b0b86a36898e",
        "topology_sha256": "4a5f52dc25a6764a3ff12a6bcb52dbf3e260dbcd07c18f82d28fcd1904ad5b11",
        "used_evidence_ids": ("d05112cf-0117-5f1a-9b7a-4087ec4f5c8f",),
        "used_evidence_sha256": "2143a3b9b7822f63732972f36e0998492d11e0103119eb421d7b4a2c8b69b48b",
    },
    "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build": {
        "v97_rows_sha256": "a1fb22af9f00a6a6073bc66a7e7179f0cf9aa5898ffa59be89259f6578220759",
        "topology_sha256": "961b6c9e06b59c0d24789c06744f052c281a3756cf1de677a836793e736a8dcf",
        "used_evidence_ids": ("bf2135c6-1aa5-58e8-a318-7e67915aa1bb",),
        "used_evidence_sha256": "dc2b8c404e3e1d2e91ec700c3540869f98ed45b6d6a2b04070e13f28f996122a",
    },
    "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build": {
        "v97_rows_sha256": "c78e9e3efd52d49c87563e422042a81865ad0d9d97ed6a0abd77bb0482379f39",
        "topology_sha256": "0bf10f26fc56ec6b7caf6512a5ada28f5156fc7148434a555955545dd9db17e1",
        "used_evidence_ids": (
            "7305379e-4152-58ec-9152-c2d7af3d39c1",
            "9ef151e3-b5f8-5421-b9df-f5ac0bfca4a6",
        ),
        "used_evidence_sha256": "ea0d78a9b3d95606883cc5c09bb4204013ae9f07bcbdfe08b6f4f74dda20a688",
    },
    "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build": {
        "v97_rows_sha256": "b6808debfde6f9e4e72d37fde65544481672a714b95ba53ef16f365d9ae15e2c",
        "topology_sha256": "cf9d533494cf5d786a7b1555f3dfc40568a58ca284f5f15f9f6d79ba1f22981c",
        "used_evidence_ids": (
            "0dd3dc39-1457-5bc3-b7d2-7ff44183aed3",
            "6b7130b5-f5f5-50c8-9689-6b8e348e0015",
            "a63792de-87ff-5a78-8a99-e53260b301f1",
        ),
        "used_evidence_sha256": "0a7772feb89273c22be7b4786aa85c01a74a67089b4e4b79ad8771c4ec16053d",
    },
    "curated:equinix-mu4-munich-data-center:phase-3": {
        "v97_rows_sha256": "3075f7428ea79979de7220a1c8816b60e6d675b457e942e389af8045fa844330",
        "topology_sha256": "5d9ee2ab8bca06a70390215ce8345591342cce5b0356db59b475fc2a28c21ca5",
        "used_evidence_ids": ("4302b7fb-1bf4-5dc7-abf5-9ba24f4556fa",),
        "used_evidence_sha256": "82d9f4c9760d2cbb45a87ae0d823a6d91098a50bf47e751d30c2a15306165552",
    },
    "curated:macquarie-ic3-super-west-facility:phase-1-build": {
        "v97_rows_sha256": "f13e64b833052e1b5e5693a858f56878aaa1e8e087a85e0f6c0d132df7b0344f",
        "topology_sha256": "af8b04506c7140f2fcde1291829b7229a6fa9f810eb35c96d042f109124e5d67",
        "used_evidence_ids": (
            "0ba37f72-6f9b-5d8f-8b8e-8b66e03dbb11",
            "10cad266-3d5e-591d-a1c4-8ded1e082c7b",
            "654559c0-3ba5-519b-8215-80eaaf854f5a",
        ),
        "used_evidence_sha256": "e9aa5225cfd73aa886e85c01d380ae325e9018e4f5763fabfaa0663ab6e20a9e",
    },
    "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build": {
        "v97_rows_sha256": "2ca481bb4be7c2016cf8089ad3f1620bb74673c6264405eceb4000213a6942f8",
        "topology_sha256": "3d9e0c4eceeaeb0aa42bfe5b4e21c0de6d67bc55cc091059d0e86e49e294047f",
        "used_evidence_ids": ("a9d0173c-a00c-5936-b2d2-493a61fc0d53",),
        "used_evidence_sha256": "eb0eed606135148cc774dc50b45524354fa7c56939600172a82e6e842ba2ea29",
    },
}
V08_EVIDENCE_IDS = frozenset(
    {
        "0ba37f72-6f9b-5d8f-8b8e-8b66e03dbb11",
        "0dd3dc39-1457-5bc3-b7d2-7ff44183aed3",
        "10cad266-3d5e-591d-a1c4-8ded1e082c7b",
        "4302b7fb-1bf4-5dc7-abf5-9ba24f4556fa",
        "4bbf6d0c-4fcb-5dd0-9504-4322a80117b8",
        "654559c0-3ba5-519b-8215-80eaaf854f5a",
        "6b7130b5-f5f5-50c8-9689-6b8e348e0015",
        "7305379e-4152-58ec-9152-c2d7af3d39c1",
        "7b2675bd-76c0-54b0-82d1-3f5d6cb328b2",
        "959963fd-1d27-5927-a972-8a04fd97727e",
        "9ef151e3-b5f8-5421-b9df-f5ac0bfca4a6",
        "a63792de-87ff-5a78-8a99-e53260b301f1",
        "a9d0173c-a00c-5936-b2d2-493a61fc0d53",
        "b24c0246-2488-55e4-9022-3609124fd8c8",
        "bd494c0b-3936-5cc0-844a-67cd0db22812",
        "bf2135c6-1aa5-58e8-a318-7e67915aa1bb",
        "d05112cf-0117-5f1a-9b7a-4087ec4f5c8f",
        "d0865f65-7e1e-59ab-989c-2d49ec5ce196",
        "e07bd94a-9734-5f78-a7b6-d69e757357c2",
        "ee256a2f-4e9b-5224-a6ce-e4f95c4a11ed",
        "efe5b5c9-7394-5f0c-951b-051197168c49",
    }
)


def load_current_v08_profile(
    definition_sha256: Mapping[str, str],
) -> PreviewProfile:
    """Load v0.8 only after all exact definition hashes are supplied."""
    expected_fields = {field for field, _ in CURRENT_V08_DEFINITION_PATHS}
    if set(definition_sha256) != expected_fields:
        raise VerifiedConstructionCoreError(
            "current v0.8 definition pins are incomplete"
        )
    pins: list[tuple[str, Path, str]] = []
    for field, path in CURRENT_V08_DEFINITION_PATHS:
        expected_sha256 = definition_sha256[field]
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise VerifiedConstructionCoreError(f"current v0.8 {field} pin is invalid")
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != expected_sha256:
            raise VerifiedConstructionCoreError(
                f"current v0.8 {field} source hash differs"
            )
        pins.append((field, path, expected_sha256))
    return PreviewProfile(
        preview_id=CURRENT_V08_PREVIEW_ID,
        preview_dir=CURRENT_V08_PREVIEW_DIR,
        reviewed_at=CURRENT_V08_REVIEW_DATE,
        base_preview_id="2026-08-20-preview-v0.7",
        base_preview_dir=LEGACY_PREVIEW_V07_DIR,
        base_manifest_sha256=LEGACY_PREVIEW_V07_MANIFEST_SHA256,
        base_commit=LEGACY_PREVIEW_V07_COMMIT,
        definition_pins=tuple(pins),
    )


def validate_frozen_v07(
    path: Path = LEGACY_PREVIEW_V07_DIR,
) -> dict[str, Any]:
    """Validate byte-frozen v0.7 using only its immutable inventory pins."""
    return _validate_frozen_preview_inventory(
        path,
        preview_id="2026-08-20-preview-v0.7",
        manifest_sha256=LEGACY_PREVIEW_V07_MANIFEST_SHA256,
        version_label="v0.7",
    )


_FROZEN_PREVIEW_VALIDATORS = (
    *_FROZEN_PREVIEW_VALIDATORS,
    ("2026-08-20-preview-v0.7", validate_frozen_v07),
)


def _v08_definition_paths() -> dict[str, tuple[Path, str]]:
    return {
        "review_definition_sha256": (
            V08_REVIEW_DEFINITION,
            V08_REVIEW_DEFINITION_SHA256,
        ),
        "imagery_review_definition_sha256": (
            V08_IMAGERY_REVIEW_DEFINITION,
            V08_IMAGERY_REVIEW_DEFINITION_SHA256,
        ),
        "provenance_definition_sha256": (
            V08_PROVENANCE_DEFINITION,
            V08_PROVENANCE_DEFINITION_SHA256,
        ),
        "overlay_definition_sha256": (
            V08_OVERLAY_DEFINITION,
            V08_OVERLAY_DEFINITION_SHA256,
        ),
    }


def _validate_v08_definition_pins() -> None:
    for field, (path, expected) in _v08_definition_paths().items():
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != expected:
            raise VerifiedConstructionCoreError(
                f"current v0.8 {field} source hash differs"
            )


def _v08_hydrated_crosscheck_available() -> bool:
    required = (
        ROOT / "releases/2026-07-22-open-seed-v97/construction_pipeline.csv",
        ROOT / "releases/2026-07-22-open-seed-v97/entities.csv",
        ROOT / "releases/2026-07-22-open-seed-v97/evidence.csv",
        ROOT / "releases/2026-07-18-global-open-v3/entities.csv",
        ROOT / "releases/2026-07-18-global-open-v3/evidence.csv",
        ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/component-members.csv",
        ROOT
        / "exact_identity_decisions/2026-07-22-public-open-v14/relationships.csv",
    )
    present = [path.is_file() for path in required]
    if any(present) and not all(present):
        raise VerifiedConstructionCoreError(
            "v0.8 hydrated cross-check inputs are only partially present"
        )
    return all(present)


def _v08_source_evidence(source: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _v07_source_evidence(source)


def _v08_normalized_roles(entity: Mapping[str, Any]) -> dict[str, Any]:
    source_roles = entity.get("roles") or {}
    if not isinstance(source_roles, dict):
        raise VerifiedConstructionCoreError("v0.8 source roles differ")
    values: dict[str, list[str]] = {}
    for role in ("owner", "operator", "users", "tenants", "customers"):
        aliases = (role, role[:-1]) if role.endswith("s") else (role,)
        parties: list[str] = []
        for alias in aliases:
            observed = source_roles.get(alias, [])
            if observed is None:
                continue
            if isinstance(observed, str):
                observed = [observed]
            if not isinstance(observed, list) or any(
                not isinstance(party, str) or not party.strip() for party in observed
            ):
                raise VerifiedConstructionCoreError("v0.8 source roles differ")
            parties.extend(party.strip() for party in observed)
        if len(parties) != len(set(parties)):
            raise VerifiedConstructionCoreError("v0.8 source roles are not unique")
        values[role] = sorted(parties)
    return {
        "owner": "; ".join(values["owner"]) or None,
        "operator": "; ".join(values["operator"]) or None,
        "users": values["users"],
        "tenants": values["tenants"],
        "customers": values["customers"],
    }


def _v08_source_entity_projection(
    source: Mapping[str, Any],
    evidence_by_key: Mapping[str, Mapping[str, Any]],
    *,
    entity_kind: str,
) -> dict[str, Any]:
    entity = source.get(entity_kind)
    if not isinstance(entity, dict):
        raise VerifiedConstructionCoreError(
            f"v0.8 {entity_kind} source record differs"
        )
    models = [
        row
        for row in source.get("operating_models", [])
        if isinstance(row, dict) and row.get("entity") == entity_kind
    ]
    if len(models) > 1:
        raise VerifiedConstructionCoreError(
            f"v0.8 {entity_kind} operating model differs"
        )
    model = models[0] if models else None
    model_evidence_id = None
    if model is not None:
        evidence = evidence_by_key.get(model.get("evidence_key"))
        if evidence is None:
            raise VerifiedConstructionCoreError(
                f"v0.8 {entity_kind} operating-model evidence differs"
            )
        model_evidence_id = _official_evidence_id(evidence)
    result = {
        "stable_key": entity["stable_key"],
        "entity_id": atlas_stable_id("entity", entity["stable_key"], entity_kind),
        "name": entity["name"],
        "country": entity["country"],
        "address": entity["address"],
        "operating_model": model["value"] if model else None,
        "operating_model_confidence": model["confidence"] if model else None,
        "operating_model_evidence_id": model_evidence_id,
        "workloads_json": _projected_bridge_observations(
            source,
            evidence_by_key,
            collection="workloads",
            entity_kind=entity_kind,
        ),
        "capacity_estimates_json": _projected_bridge_observations(
            source,
            evidence_by_key,
            collection="capacities",
            entity_kind=entity_kind,
        ),
    }
    if entity_kind == "project":
        lifecycle = [
            row
            for row in source.get("lifecycle", [])
            if isinstance(row, dict) and row.get("entity") == "project"
        ]
        if not lifecycle:
            raise VerifiedConstructionCoreError("v0.8 lifecycle differs")
        latest = max(lifecycle, key=lambda row: row.get("as_of_date", ""))
        status_evidence = evidence_by_key.get(latest.get("evidence_key"))
        if status_evidence is None:
            raise VerifiedConstructionCoreError("v0.8 status evidence differs")
        result.update(
            {
                "status": latest["value"],
                "status_as_of": latest["as_of_date"],
                "status_age_days_at_review": (
                    CURRENT_V08_REVIEW_DATE
                    - _calendar_date(latest["as_of_date"], "v0.8 status")
                ).days,
                "status_method": latest["method"],
                "status_confidence": latest["confidence"],
                "status_evidence_id": _official_evidence_id(status_evidence),
            }
        )
    return result


def _v08_construction_row_bindings(
    construction: Mapping[str, Any],
) -> Mapping[str, Any]:
    embedded = construction.get("release_rows")
    if embedded is not None:
        if not isinstance(embedded, dict):
            raise VerifiedConstructionCoreError("v0.8 release rows differ")
        return embedded
    return {
        "project": construction["project"].get("source_row"),
        "campus": construction["campus"].get("source_row"),
        "status_evidence": construction["status_evidence"].get("source_row"),
    }


def _v08_csv_roles(row: Mapping[str, str]) -> dict[str, Any]:
    roles = _v07_source_roles(row)
    return {
        "owner": "; ".join(roles["owner"]) or None,
        "operator": "; ".join(roles["operator"]) or None,
        "users": roles["user"],
        "tenants": roles["tenant"],
        "customers": roles["customer"],
    }


def _v08_csv_entity_projection(
    row: Mapping[str, str], *, entity_kind: str
) -> dict[str, Any]:
    if (
        row.get("entity_kind") != entity_kind
        or row.get("entity_id")
        != atlas_stable_id("entity", row.get("stable_key", ""), entity_kind)
    ):
        raise VerifiedConstructionCoreError(
            f"v0.8 v97 {entity_kind} identity differs"
        )
    workloads = _csv_json(
        row["workloads_json"], label=f"v0.8 v97 {entity_kind} workloads"
    )
    capacities = _csv_json(
        row["capacity_estimates_json"],
        label=f"v0.8 v97 {entity_kind} capacities",
    )
    if not isinstance(workloads, list) or not isinstance(capacities, list):
        raise VerifiedConstructionCoreError(
            f"v0.8 v97 {entity_kind} observations differ"
        )
    for observation in workloads:
        _validate_source_workload_observation(observation)
    for observation in capacities:
        _validate_typed_observation(
            observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
        )
    result = {
        "stable_key": row["stable_key"],
        "entity_id": row["entity_id"],
        "name": row["name"],
        "country": row["country"],
        "address": row["address"],
        "operating_model": _nullable_csv_value(row["operating_model"]),
        "operating_model_confidence": _csv_float(
            row["operating_model_confidence"],
            label=f"v0.8 v97 {entity_kind} operating model",
        ),
        "operating_model_evidence_id": _nullable_csv_value(
            row["operating_model_evidence_id"]
        ),
        "workloads_json": workloads,
        "capacity_estimates_json": capacities,
        "normalized_roles": _v08_csv_roles(row),
    }
    if entity_kind == "project":
        status_as_of = _nullable_csv_value(row["status_as_of"])
        if status_as_of is None:
            raise VerifiedConstructionCoreError("v0.8 v97 project status differs")
        result.update(
            {
                "status": _nullable_csv_value(row["status"]),
                "status_as_of": status_as_of,
                "status_age_days_at_review": (
                    CURRENT_V08_REVIEW_DATE
                    - _calendar_date(status_as_of, "v0.8 v97 status")
                ).days,
                "status_confidence": _csv_float(
                    row["status_confidence"], label="v0.8 v97 status"
                ),
                "status_method": _nullable_csv_value(row["status_method"]),
                "status_evidence_id": _nullable_csv_value(
                    row["status_evidence_id"]
                ),
            }
        )
        if any(result[field] is None for field in ("status", "status_method", "status_evidence_id")):
            raise VerifiedConstructionCoreError("v0.8 v97 project status differs")
    elif any(
        row[field]
        for field in (
            "status",
            "status_as_of",
            "status_confidence",
            "status_method",
            "status_evidence_id",
        )
    ):
        raise VerifiedConstructionCoreError("v0.8 v97 campus status differs")
    return result


def _v08_actual_entity_projection(
    entity: Mapping[str, Any], *, entity_kind: str
) -> dict[str, Any]:
    result = {
        field: entity.get(field)
        for field in (
            "stable_key",
            "entity_id",
            "name",
            "country",
            "address",
            "operating_model",
            "operating_model_confidence",
            "operating_model_evidence_id",
            "workloads_json",
            "capacity_estimates_json",
        )
    }
    result["normalized_roles"] = entity.get(
        "normalized_roles",
        {
            field: entity.get(field)
            for field in ("owner", "operator", "users", "tenants", "customers")
        },
    )
    if entity_kind == "project":
        result.update(
            {
                field: entity.get(field)
                for field in (
                    "status",
                    "status_as_of",
                    "status_age_days_at_review",
                    "status_confidence",
                    "status_method",
                    "status_evidence_id",
                )
            }
        )
    return result


def _v08_validate_embedded_construction_rows(
    bridge: Mapping[str, Any], *, hydrated_crosscheck: bool
) -> dict[str, Any]:
    construction = bridge["construction_source"]
    release = construction["release"]
    embedded = construction.get("release_rows")
    if embedded is not None:
        _validate_v06_embedded_release_rows(
            embedded,
            release["members"],
            hydrated_crosscheck=hydrated_crosscheck,
        )
        if not {
            "construction_pipeline_project",
            "entities_project",
            "entities_campus",
            "evidence_snapshot",
        } <= set(embedded):
            raise VerifiedConstructionCoreError("v0.8 release-row inventory differs")
        project_row = _embedded_csv_source_row(
            embedded["construction_pipeline_project"]["source_row"],
            SOURCE_ENTITY_FIELDS,
            label="v0.8 construction pipeline project",
        )
        entities_project_row = _embedded_csv_source_row(
            embedded["entities_project"]["source_row"],
            SOURCE_ENTITY_FIELDS,
            label="v0.8 entities project",
        )
        if project_row != entities_project_row:
            raise VerifiedConstructionCoreError(
                "v0.8 v97 project rows differ"
            )
        campus_row = _embedded_csv_source_row(
            embedded["entities_campus"]["source_row"],
            SOURCE_ENTITY_FIELDS,
            label="v0.8 entities campus",
        )
        evidence_rows: dict[str, dict[str, str]] = {}
        for label, binding in embedded.items():
            if binding.get("member") != "evidence.csv":
                continue
            row = _embedded_csv_source_row(
                binding["source_row"],
                GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
                label=f"v0.8 {label}",
            )
            evidence_id = row["evidence_id"]
            if evidence_id in evidence_rows:
                raise VerifiedConstructionCoreError(
                    "v0.8 embedded evidence rows are not unique"
                )
            evidence_rows[evidence_id] = row
    else:
        entity_rows: dict[str, dict[str, str]] = {}
        for label, record, member, kind in (
            (
                "project",
                construction["project"],
                "construction_pipeline.csv",
                "project",
            ),
            ("campus", construction["campus"], "entities.csv", "campus"),
        ):
            row = _embedded_csv_source_row(
                record.get("source_row"),
                SOURCE_ENTITY_FIELDS,
                label=f"v0.8 {label}",
            )
            if (
                row["stable_key"] != record["stable_key"]
                or row["entity_id"] != record["entity_id"]
                or row["entity_kind"] != kind
            ):
                raise VerifiedConstructionCoreError(
                    f"v0.8 {label} source-row projection differs"
                )
            entity_rows[kind] = row
            if hydrated_crosscheck:
                metadata = release["members"][member]
                payload_path = _repository_input(
                    metadata["path"], metadata["sha256"], f"v0.8 {member}"
                )
                _validate_hydrated_source_row(
                    payload_path,
                    record["source_row"],
                    SOURCE_ENTITY_FIELDS,
                    label=f"v0.8 {label}",
                )
        project_row = entity_rows["project"]
        campus_row = entity_rows["campus"]
        status = construction["status_evidence"]
        status_row = _embedded_csv_source_row(
            status.get("source_row"),
            GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
            label="v0.8 status",
        )
        if status_row["evidence_id"] != status["evidence_id"]:
            raise VerifiedConstructionCoreError(
                "v0.8 status source-row projection differs"
            )
        evidence_rows = {status_row["evidence_id"]: status_row}
        if hydrated_crosscheck:
            metadata = release["members"]["evidence.csv"]
            payload_path = _repository_input(
                metadata["path"], metadata["sha256"], "v0.8 evidence.csv"
            )
            _validate_hydrated_source_row(
                payload_path,
                status["source_row"],
                GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
                label="v0.8 status",
            )
    status_id = construction["status_evidence"].get("evidence_id")
    if status_id not in evidence_rows:
        raise VerifiedConstructionCoreError("v0.8 embedded status evidence differs")
    return {
        "project": project_row,
        "campus": campus_row,
        "evidence": evidence_rows,
    }


def _v08_hydrated_evidence_rows(
    release: Mapping[str, Any], evidence_ids: Sequence[str]
) -> dict[str, dict[str, str]]:
    metadata = release["members"]["evidence.csv"]
    path = _repository_input(
        metadata["path"], metadata["sha256"], "v0.8 evidence.csv"
    )
    if path.stat().st_size != metadata["bytes"]:
        raise VerifiedConstructionCoreError("v0.8 hydrated evidence differs")
    expected = set(evidence_ids)
    result: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(GLOBAL_GEOMETRY_EVIDENCE_FIELDS):
            raise VerifiedConstructionCoreError(
                "v0.8 hydrated evidence header differs"
            )
        for row in reader:
            evidence_id = row["evidence_id"]
            if evidence_id not in expected:
                continue
            if evidence_id in result:
                raise VerifiedConstructionCoreError(
                    "v0.8 hydrated evidence is not unique"
                )
            result[evidence_id] = row
    if set(result) != expected:
        raise VerifiedConstructionCoreError("v0.8 hydrated evidence row differs")
    return result


def _v08_validate_construction_source(
    bridge: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    project_key = acceptance["project_stable_key"]
    source_profile = V08_SOURCE_PROFILES.get(project_key)
    if source_profile is None:
        raise VerifiedConstructionCoreError("v0.8 source profile differs")
    construction = bridge.get("construction_source")
    if not isinstance(construction, dict) or set(construction) not in {
        frozenset(
            {"input", "release", "project", "campus", "project_to_campus", "status_evidence"}
        ),
        frozenset(
            {
                "input",
                "release",
                "release_rows",
                "project",
                "campus",
                "project_to_campus",
                "status_evidence",
            }
        ),
    }:
        raise VerifiedConstructionCoreError("v0.8 construction source differs")
    if (
        _sha256_bytes(_json_bytes(_v08_construction_row_bindings(construction)))
        != source_profile["v97_rows_sha256"]
        or _sha256_bytes(_json_bytes(construction.get("project_to_campus")))
        != source_profile["topology_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 immutable source profile differs")
    expected_input = {
        "path": acceptance["source_input_path"],
        "bytes": acceptance["source_input_bytes"],
        "sha256": acceptance["source_input_sha256"],
    }
    if (
        construction.get("input") != expected_input
        or acceptance.get("portable_input_binding") != expected_input
    ):
        raise VerifiedConstructionCoreError("v0.8 source input binding differs")
    source_path = _repository_input(
        expected_input["path"], expected_input["sha256"], "v0.8 source input"
    )
    if source_path.stat().st_size != expected_input["bytes"]:
        raise VerifiedConstructionCoreError("v0.8 source input byte count differs")
    source = _load_json(source_path)
    if not isinstance(source, dict):
        raise VerifiedConstructionCoreError("v0.8 source record differs")
    source_evidence = source.get("evidence")
    if not isinstance(source_evidence, list) or not source_evidence:
        raise VerifiedConstructionCoreError("v0.8 source evidence differs")
    evidence_by_key = {
        row["key"]: row
        for row in source_evidence
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    if len(evidence_by_key) != len(source_evidence):
        raise VerifiedConstructionCoreError("v0.8 source evidence differs")
    expected_project = _v08_source_entity_projection(
        source, evidence_by_key, entity_kind="project"
    )
    expected_campus = _v08_source_entity_projection(
        source, evidence_by_key, entity_kind="campus"
    )
    project = construction.get("project")
    campus = construction.get("campus")
    if not isinstance(project, dict) or not isinstance(campus, dict):
        raise VerifiedConstructionCoreError("v0.8 construction entities differ")
    for actual, expected, source_entity, label in (
        (project, expected_project, source["project"], "project"),
        (campus, expected_campus, source["campus"], "campus"),
    ):
        for field, value in expected.items():
            if actual.get(field) != value:
                raise VerifiedConstructionCoreError(
                    f"v0.8 construction {label} projection differs"
                )
        roles = _v08_normalized_roles(source_entity)
        if "normalized_roles" in actual:
            if actual["normalized_roles"] != roles:
                raise VerifiedConstructionCoreError(
                    f"v0.8 construction {label} roles differ"
                )
        elif any(actual.get(field) != value for field, value in roles.items()):
            raise VerifiedConstructionCoreError(
                f"v0.8 construction {label} roles differ"
            )
    if (
        project.get("stable_key") != acceptance["project_stable_key"]
        or project.get("entity_id") != acceptance["project_entity_id"]
        or campus.get("stable_key") != acceptance["physical_site_stable_key"]
        or campus.get("entity_id") != acceptance["physical_site_entity_id"]
        or project.get("country") != acceptance["country"]
        or campus.get("country") != acceptance["country"]
    ):
        raise VerifiedConstructionCoreError(
            "v0.8 publication target projection differs"
        )
    if "status" in campus and any(
        campus.get(field) is not None
        for field in (
            "status",
            "status_as_of",
            "status_age_days_at_review",
            "status_method",
            "status_confidence",
            "status_evidence_id",
        )
    ):
        raise VerifiedConstructionCoreError("v0.8 campus status leakage differs")
    status = construction.get("status_evidence")
    evidence_pool = _v08_source_evidence(source)
    status_id = expected_project["status_evidence_id"]
    if not isinstance(status, dict) or status.get("evidence_id") != status_id:
        raise VerifiedConstructionCoreError("v0.8 status evidence differs")
    expected_status = evidence_pool.get(status_id)
    if expected_status is None or any(
        ("" if status.get(field) is None else status.get(field))
        != expected_status[field]
        for field in GLOBAL_GEOMETRY_EVIDENCE_FIELDS
    ):
        raise VerifiedConstructionCoreError("v0.8 status evidence projection differs")
    release = construction.get("release")
    if (
        not isinstance(release, dict)
        or release.get("release_id") != SOURCE_RELEASE_ID
        or set(release.get("members", {}))
        != {"construction_pipeline.csv", "entities.csv", "evidence.csv"}
    ):
        raise VerifiedConstructionCoreError("v0.8 source release differs")
    _, manifest = _manifest_binding(release["manifest"], label="v0.8 source release")
    _validate_manifest_members(manifest, release["members"], label="v0.8 source release")
    raw_rows = _v08_validate_embedded_construction_rows(
        bridge, hydrated_crosscheck=hydrated_crosscheck
    )
    for entity_kind, actual in (("project", project), ("campus", campus)):
        raw_projection = _v08_csv_entity_projection(
            raw_rows[entity_kind], entity_kind=entity_kind
        )
        if _v08_actual_entity_projection(
            actual, entity_kind=entity_kind
        ) != raw_projection:
            raise VerifiedConstructionCoreError(
                f"v0.8 v97 {entity_kind} projection differs"
            )
    used_evidence_ids = tuple(source_profile["used_evidence_ids"])
    if tuple(sorted(used_evidence_ids)) != used_evidence_ids:
        raise VerifiedConstructionCoreError("v0.8 source evidence profile differs")
    try:
        used_evidence = [evidence_pool[evidence_id] for evidence_id in used_evidence_ids]
    except KeyError as error:
        raise VerifiedConstructionCoreError(
            "v0.8 used source evidence differs"
        ) from error
    if (
        _sha256_bytes(_json_bytes(used_evidence))
        != source_profile["used_evidence_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 used source evidence differs")
    for evidence_id, row in raw_rows["evidence"].items():
        projected = evidence_pool.get(evidence_id)
        if projected is None or any(
            projected[field] != row[field]
            for field in GLOBAL_GEOMETRY_EVIDENCE_FIELDS
        ):
            raise VerifiedConstructionCoreError(
                "v0.8 embedded evidence projection differs"
            )
    if hydrated_crosscheck:
        hydrated_evidence = _v08_hydrated_evidence_rows(
            release, used_evidence_ids
        )
        for evidence_id, projected in zip(
            used_evidence_ids, used_evidence, strict=True
        ):
            if any(
                projected[field] != hydrated_evidence[evidence_id][field]
                for field in GLOBAL_GEOMETRY_EVIDENCE_FIELDS
            ):
                raise VerifiedConstructionCoreError(
                    "v0.8 hydrated evidence projection differs"
                )
    _validate_v07_topology(
        bridge,
        project,
        campus,
        hydrated_crosscheck=hydrated_crosscheck,
    )
    relationship = construction["project_to_campus"]["relationship"]
    if (
        relationship.get("relationship_id")
        != acceptance["project_to_campus_relationship_id"]
        or relationship.get("relationship_type")
        != acceptance["project_to_campus_relationship_type"]
        or relationship.get("decision_basis")
        != acceptance["project_to_campus_decision_basis"]
    ):
        raise VerifiedConstructionCoreError("v0.8 topology definition differs")
    return project, campus, source


def _validate_v08_direct_geometry(
    bridge: Mapping[str, Any], acceptance: Mapping[str, Any]
) -> None:
    if bridge.get("geometry_release") is not None:
        raise VerifiedConstructionCoreError("v0.8 direct geometry release differs")
    entity = bridge.get("geometry_entity")
    evidence = bridge.get("geometry_evidence")
    if not isinstance(entity, dict) or not isinstance(evidence, dict):
        raise VerifiedConstructionCoreError("v0.8 direct geometry differs")
    profile = V08_BRIDGE_PROFILES.get(acceptance.get("project_stable_key"))
    if profile is None:
        raise VerifiedConstructionCoreError("v0.8 direct source profile differs")
    expected_source = {
        "source_url": profile.get("direct_source_url"),
        "source_publisher": profile.get("direct_source_publisher"),
        "source_license": profile.get("direct_source_license"),
        "source_retrieved_at": profile.get("direct_source_retrieved_at"),
    }
    entity_source = {
        field: entity.get(field)
        for field in (
            "source_url",
            "source_publisher",
            "source_license",
            "source_retrieved_at",
        )
    }
    evidence_source = {
        "source_url": evidence.get("source_url"),
        "source_publisher": evidence.get("publisher"),
        "source_license": evidence.get("license"),
        "source_retrieved_at": evidence.get("retrieved_at"),
    }
    if (
        None in expected_source.values()
        or entity_source != expected_source
        or evidence_source != expected_source
        or evidence.get("effective_url") != expected_source["source_url"]
        or evidence.get("source_family") != profile.get("direct_source_family")
        or evidence.get("kind") != profile.get("direct_source_kind")
        or evidence.get("license_url") is not None
        or evidence.get("published_at") is not None
    ):
        raise VerifiedConstructionCoreError("v0.8 direct source metadata differs")
    _validate_v06_fact_evidence(evidence, label="v0.8 direct geometry evidence")
    fact = evidence.get("fact_payload")
    geometry = entity.get("geometry")
    if not isinstance(fact, dict) or not isinstance(geometry, dict):
        raise VerifiedConstructionCoreError("v0.8 direct geometry fact differs")
    geometry_bytes = _json_bytes(geometry)[:-1]
    try:
        reported_point = [
            float(fact["longitude_as_reported"]),
            float(fact["latitude_as_reported"]),
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise VerifiedConstructionCoreError(
            "v0.8 direct coordinate strings differ"
        ) from error
    point = [entity.get("longitude"), entity.get("latitude")]
    if (
        entity.get("entity_kind") != "project"
        or entity.get("entity_id") != acceptance["geometry_entity_id"]
        or entity.get("stable_key") != acceptance["geometry_entity_stable_key"]
        or entity.get("entity_id")
        != atlas_stable_id("entity", entity.get("stable_key", ""), "project")
        or acceptance.get("geometry_target_entity_kind") != "project"
        or entity.get("stable_key")
        != acceptance.get("geometry_target_entity_stable_key")
        or entity.get("entity_id") != acceptance.get("geometry_target_entity_id")
        or entity.get("source_evidence_id") != evidence.get("evidence_id")
        or geometry != {"type": "Point", "coordinates": point}
        or reported_point != point
        or [fact.get("longitude"), fact.get("latitude")] != point
        or evidence.get("geometry_canonical_bytes") != len(geometry_bytes)
        or evidence.get("geometry_canonical_sha256")
        != _sha256_bytes(geometry_bytes)
        or evidence.get("evidence_id") != _official_evidence_id(evidence)
        or evidence.get("key") != acceptance["geometry_evidence_key"]
        or evidence.get("kind") != acceptance["geometry_source_kind"]
        or evidence.get("capture_reference") is not None
    ):
        raise VerifiedConstructionCoreError("v0.8 direct geometry projection differs")


def _validate_v08_osm_geometry(
    bridge: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> None:
    release = bridge.get("geometry_release")
    if (
        not isinstance(release, dict)
        or set(release)
        != {"release_id", "as_of", "recorded_at", "manifest", "members"}
        or release.get("release_id") != "global-open-v3"
        or set(release.get("members", {})) != {"entities.csv", "evidence.csv"}
    ):
        raise VerifiedConstructionCoreError("v0.8 OSM release differs")
    _, manifest = _manifest_binding(release["manifest"], label="v0.8 OSM release")
    _validate_manifest_members(manifest, release["members"], label="v0.8 OSM release")
    entity = bridge.get("geometry_entity")
    evidence = bridge.get("geometry_evidence")
    if not isinstance(entity, dict) or not isinstance(evidence, dict):
        raise VerifiedConstructionCoreError("v0.8 OSM records differ")
    entity_row = _embedded_csv_source_row(
        entity.get("source_row"),
        GLOBAL_GEOMETRY_ENTITY_FIELDS,
        label="v0.8 OSM entity",
    )
    evidence_row = _embedded_csv_source_row(
        evidence.get("source_row"),
        GLOBAL_GEOMETRY_EVIDENCE_FIELDS,
        label="v0.8 OSM evidence",
    )
    if (
        {field: value for field, value in entity.items() if field != "source_row"}
        != _global_geometry_entity_projection(entity_row)
        or {field: value for field, value in evidence.items() if field != "source_row"}
        != _global_geometry_evidence_projection(evidence_row)
    ):
        raise VerifiedConstructionCoreError("v0.8 OSM source projection differs")
    geometry = entity.get("geometry")
    _validate_polygon(geometry, label="v0.8 OSM geometry")
    ring = geometry["coordinates"][0]
    midpoint = [
        (min(point[0] for point in ring) + max(point[0] for point in ring)) / 2,
        (min(point[1] for point in ring) + max(point[1] for point in ring)) / 2,
    ]
    url_match = re.fullmatch(
        r"https://www\.openstreetmap\.org/(node|way|relation)/([1-9][0-9]*)",
        str(entity.get("source_url")),
    )
    if url_match is None:
        raise VerifiedConstructionCoreError("v0.8 OSM source URL differs")
    osm_type, osm_id = url_match.groups()
    expected_osm_status = (
        ("under_construction", "osm_explicit_construction_tag")
        if entity.get("stable_key")
        == "osm:way/1298979790:development-project"
        else ("unknown", "osm_geometry_only_no_operational_inference")
    )
    if (
        entity.get("entity_kind") != acceptance["geometry_entity"]
        or entity.get("stable_key") != acceptance["geometry_entity_stable_key"]
        or entity.get("entity_id") != acceptance["geometry_entity_id"]
        or entity.get("entity_id")
        != atlas_stable_id("entity", entity["stable_key"], entity["entity_kind"])
        or [entity.get("longitude"), entity.get("latitude")] != midpoint
        or evidence.get("evidence_id") != acceptance["geometry_evidence_id"]
        or acceptance["geometry_evidence_key"] is not None
        or evidence.get("evidence_id")
        != atlas_stable_id(
            "evidence",
            "osm",
            osm_type,
            osm_id,
            evidence.get("retrieved_at"),
            evidence.get("content_hash"),
        )
        or evidence.get("evidence_id") != entity.get("snapshot_evidence_id")
        or evidence.get("source_url") != entity.get("source_url")
        or evidence.get("publisher") != entity.get("source_publisher")
        or evidence.get("source_family") != "openstreetmap"
        or entity.get("source_family") != "openstreetmap"
        or evidence.get("license") != "ODbL-1.0"
        or entity.get("source_license") != "ODbL-1.0"
        or evidence.get("attribution") != "© OpenStreetMap contributors"
        or entity.get("source_attribution") != "© OpenStreetMap contributors"
        or (entity.get("status"), entity.get("status_method"))
        != expected_osm_status
        or entity.get("capacity_estimates_json") != []
        or entity.get("workloads_json") != []
    ):
        raise VerifiedConstructionCoreError("v0.8 OSM semantics differ")
    rights = bridge.get("rights")
    if (
        not isinstance(rights, dict)
        or rights.get("geometry_license_url")
        != "https://opendatacommons.org/licenses/odbl/1-0/"
        or rights.get("geometry_attribution_url")
        != "https://www.openstreetmap.org/copyright"
        or "OpenStreetMap contributors" not in str(rights.get("geometry_source"))
    ):
        raise VerifiedConstructionCoreError("v0.8 OSM rights differ")
    if hydrated_crosscheck:
        for name, record, fields in (
            ("entities.csv", entity, GLOBAL_GEOMETRY_ENTITY_FIELDS),
            ("evidence.csv", evidence, GLOBAL_GEOMETRY_EVIDENCE_FIELDS),
        ):
            metadata = release["members"][name]
            path = _repository_input(
                metadata["path"], metadata["sha256"], f"v0.8 OSM {name}"
            )
            if path.stat().st_size != metadata["bytes"]:
                raise VerifiedConstructionCoreError(
                    f"v0.8 hydrated OSM payload differs: {name}"
                )
            _validate_hydrated_source_row(
                path,
                record["source_row"],
                fields,
                label=f"v0.8 OSM {name}",
            )


def _validate_v08_bridge(
    acceptance: Mapping[str, Any],
    overlay: Mapping[str, Any],
    *,
    hydrated_crosscheck: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    project_key = acceptance["project_stable_key"]
    profile = V08_BRIDGE_PROFILES.get(project_key)
    if (
        profile is None
        or acceptance.get("bridge_sha256") != profile["bridge_sha256"]
        or acceptance.get("source_input_sha256") != profile["source_sha256"]
        or acceptance.get("bridge_schema") != profile["schema"]
        or acceptance.get("geometry_entity") != profile["geometry_kind"]
        or acceptance.get("geometry_entity_stable_key")
        != profile["geometry_stable_key"]
        or acceptance.get("geometry_target_entity_kind") != profile["target_kind"]
        or acceptance.get("geometry_target_entity_stable_key")
        != profile["target_stable_key"]
        or acceptance.get("geometry_evidence_id")
        != profile["geometry_evidence_id"]
        or acceptance.get("geometry_evidence_key")
        != profile["geometry_evidence_key"]
        or acceptance.get("geometry_source_kind")
        != profile["geometry_source_kind"]
    ):
        raise VerifiedConstructionCoreError("v0.8 immutable bridge profile differs")
    path = _repository_input(
        acceptance["bridge_path"], acceptance["bridge_sha256"], "geometry bridge"
    )
    if path.stat().st_size != acceptance["bridge_bytes"]:
        raise VerifiedConstructionCoreError("v0.8 bridge byte count differs")
    bridge = _load_json(path)
    expected_top = {
        "bridge_id",
        "bridge_schema",
        "claim_guardrails",
        "construction_source",
        "geometry_capture",
        "geometry_entity",
        "geometry_evidence",
        "geometry_release",
        "identity_bridge_evidence",
        "imagery_posture",
        "lineage_context",
        "review_decision",
        "reviewed_at",
        "rights",
        "schema_version",
    }
    if (
        not isinstance(bridge, dict)
        or set(bridge) != expected_top
        or bridge.get("schema_version") != 1
        or bridge.get("bridge_id") != acceptance["bridge_id"]
        or bridge.get("bridge_schema") != acceptance["bridge_schema"]
        or bridge.get("reviewed_at") != CURRENT_V08_REVIEW_DATE.isoformat()
        or bridge.get("geometry_capture") is not None
        or acceptance.get("portable_capture_binding") is not None
        or bridge.get("identity_bridge_evidence") != []
    ):
        raise VerifiedConstructionCoreError("v0.8 bridge identity differs")
    geometry_projection = {
        field: bridge[field]
        for field in ("geometry_release", "geometry_entity", "geometry_evidence")
    }
    if (
        _sha256_bytes(_json_bytes(geometry_projection))
        != profile["geometry_projection_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 geometry profile differs")
    rights = bridge.get("rights")
    if (
        not isinstance(rights, dict)
        or _sha256_bytes(_json_bytes(rights)) != profile["rights_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 rights profile differs")
    if (
        _sha256_bytes(_json_bytes(bridge.get("review_decision")))
        != profile["review_decision_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 review decision profile differs")
    if (
        _sha256_bytes(_json_bytes(bridge.get("claim_guardrails")))
        != profile["claim_guardrails_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 claim guardrails profile differs")
    if (
        _sha256_bytes(_json_bytes(bridge.get("imagery_posture")))
        != profile["imagery_posture_sha256"]
    ):
        raise VerifiedConstructionCoreError("v0.8 imagery posture profile differs")
    project, campus, source = _v08_validate_construction_source(
        bridge,
        acceptance,
        hydrated_crosscheck=hydrated_crosscheck,
    )
    entity = bridge["geometry_entity"]
    evidence = bridge["geometry_evidence"]
    if (
        entity.get("entity_kind") != acceptance["geometry_entity"]
        or entity.get("stable_key") != acceptance["geometry_entity_stable_key"]
        or entity.get("entity_id") != acceptance["geometry_entity_id"]
        or evidence.get("evidence_id") != acceptance["geometry_evidence_id"]
        or [entity.get("longitude"), entity.get("latitude")]
        != [profile["longitude"], profile["latitude"]]
    ):
        raise VerifiedConstructionCoreError("v0.8 geometry source identity differs")
    target = project if profile["target_kind"] == "project" else campus
    if (
        target["stable_key"] != acceptance["geometry_target_entity_stable_key"]
        or target["entity_id"] != acceptance["geometry_target_entity_id"]
        or target["stable_key"] != profile["target_stable_key"]
    ):
        raise VerifiedConstructionCoreError("v0.8 geometry target identity differs")
    decision = bridge.get("review_decision")
    decision_bindings = {
        "decision": "bridge_decision",
        "geometry_target_entity_kind": "geometry_target_entity_kind",
        "geometry_derivation": "geometry_derivation",
        "geometry_method": "geometry_method",
        "geometry_scope_class": "geometry_scope_class",
        "geometry_authority_class": "geometry_authority_class",
        "geometry_use_scope": "geometry_use_scope",
        "horizontal_uncertainty_metres": "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason": "horizontal_uncertainty_unknown_reason",
        "precision_scope": "precision_scope",
        "rejected_claims": "rejected_claims",
    }
    if not isinstance(decision, dict) or any(
        decision.get(field) != acceptance[target_field]
        for field, target_field in decision_bindings.items()
    ):
        raise VerifiedConstructionCoreError("v0.8 review semantics differ")
    if (
        decision.get("official_boundary") is not False
        or acceptance.get("official_boundary") is not False
        or (
            profile["target_kind"] == "campus"
            and acceptance.get("geometry_use_scope") != "campus_locator"
        )
        or (
            profile["target_kind"] == "project"
            and acceptance.get("geometry_use_scope") != "project_locator"
        )
    ):
        raise VerifiedConstructionCoreError("v0.8 geometry scope differs")
    if profile["schema"].endswith("direct-first-party-geometry-bridge-v1"):
        _validate_v08_direct_geometry(bridge, acceptance)
    else:
        _validate_v08_osm_geometry(
            bridge,
            acceptance,
            hydrated_crosscheck=hydrated_crosscheck,
        )
    imagery = bridge.get("imagery_posture")
    if (
        not isinstance(imagery, dict)
        or imagery.get("outcome") != "not_reviewed_for_core_preview"
        or imagery.get("independent_imagery_verification") is not False
        or not isinstance(imagery.get("basis"), str)
        or not imagery["basis"]
        or not isinstance(bridge.get("claim_guardrails"), dict)
        or not bridge["claim_guardrails"]
        or any(
            not isinstance(value, str) or not value
            for value in bridge["claim_guardrails"].values()
        )
    ):
        raise VerifiedConstructionCoreError("v0.8 imagery or guardrails differ")
    return bridge, source


def _v08_contracts(*, hydrated_crosscheck: bool) -> dict[str, Any]:
    _validate_v08_definition_pins()
    reviewed = _load_json(V08_REVIEW_DEFINITION)
    overlays = _load_json(V08_OVERLAY_DEFINITION)
    provenance = _load_json(V08_PROVENANCE_DEFINITION)
    imagery = _load_json(V08_IMAGERY_REVIEW_DEFINITION)
    if (
        not isinstance(reviewed, dict)
        or set(reviewed)
        != {"contract_id", "review_scope", "reviewed_as_of", "base_contract", "acceptances"}
        or reviewed.get("contract_id")
        != "verified-construction-core-v0.8-reviewed-sites"
        or reviewed.get("reviewed_as_of") != CURRENT_V08_REVIEW_DATE.isoformat()
        or reviewed.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.7-reviewed-sites.json",
            "sha256": V07_REVIEW_DEFINITION_SHA256,
            "default_geometry_entity": "project",
            "default_geometry_derivation": "direct_geometry",
        }
        or not isinstance(reviewed.get("acceptances"), list)
        or len(reviewed["acceptances"]) != 8
    ):
        raise VerifiedConstructionCoreError("v0.8 reviewed-site contract differs")
    if (
        not isinstance(overlays, dict)
        or set(overlays)
        != {
            "contract_id",
            "purpose",
            "reviewed_as_of",
            "base_contract",
            "required_fields",
            "allowed_decisions",
            "overlays",
        }
        or overlays.get("contract_id")
        != "verified-construction-core-reviewed-overlays-v6"
        or overlays.get("reviewed_as_of") != CURRENT_V08_REVIEW_DATE.isoformat()
        or overlays.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-reviewed-overlays-v5.json",
            "sha256": V07_OVERLAY_DEFINITION_SHA256,
        }
        or set(overlays.get("allowed_decisions", []))
        != {"queued", "accepted", "excluded"}
        or not isinstance(overlays.get("overlays"), list)
        or len(overlays["overlays"]) != 8
    ):
        raise VerifiedConstructionCoreError("v0.8 overlay contract differs")
    if set(overlays.get("required_fields", [])) != V08_OVERLAY_REQUIRED_FIELDS:
        raise VerifiedConstructionCoreError("v0.8 overlay required fields differ")
    if any(
        not isinstance(row, dict) or set(row) != V08_OVERLAY_REQUIRED_FIELDS
        for row in overlays["overlays"]
    ):
        raise VerifiedConstructionCoreError("v0.8 overlay row schema differs")
    acceptances = reviewed["acceptances"]
    acceptance_by_key = {
        row.get("project_stable_key"): row
        for row in acceptances
        if isinstance(row, dict)
    }
    overlay_by_key = {
        row.get("source_project_stable_key"): row
        for row in overlays["overlays"]
        if isinstance(row, dict)
    }
    if (
        len(acceptance_by_key) != 8
        or len(overlay_by_key) != 8
        or set(acceptance_by_key) != set(V08_BRIDGE_PROFILES)
        or set(overlay_by_key) != set(V08_BRIDGE_PROFILES)
        or set(V08_SOURCE_PROFILES) != set(V08_BRIDGE_PROFILES)
    ):
        raise VerifiedConstructionCoreError("v0.8 definition cohort differs")
    profiled_evidence_ids = {
        evidence_id
        for profile in V08_SOURCE_PROFILES.values()
        for evidence_id in profile["used_evidence_ids"]
    } | {
        profile["geometry_evidence_id"]
        for profile in V08_BRIDGE_PROFILES.values()
    }
    if profiled_evidence_ids != V08_EVIDENCE_IDS:
        raise VerifiedConstructionCoreError("v0.8 evidence profile differs")
    bridges: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    crosswalk = {
        "country": "country",
        "physical_site_stable_key": "physical_site_stable_key",
        "physical_site_entity_id": "physical_site_entity_id",
        "source_input_path": "source_input_path",
        "source_input_bytes": "source_input_bytes",
        "source_input_sha256": "source_input_sha256",
        "bridge_id": "bridge_id",
        "bridge_schema": "bridge_schema",
        "bridge_path": "bridge_path",
        "bridge_bytes": "bridge_bytes",
        "bridge_sha256": "bridge_sha256",
        "project_to_campus_relationship_id": "project_to_campus_relationship_id",
        "project_to_campus_relationship_type": "project_to_campus_relationship_type",
        "project_to_campus_decision_basis": "project_to_campus_decision_basis",
        "geometry_entity": "geometry_entity",
        "geometry_entity_stable_key": "geometry_entity_stable_key",
        "geometry_entity_id": "geometry_entity_id",
        "geometry_target_entity_kind": "geometry_target_entity_kind",
        "geometry_target_entity_stable_key": "geometry_target_entity_stable_key",
        "geometry_target_entity_id": "geometry_target_entity_id",
        "geometry_evidence_key": "geometry_evidence_key",
        "geometry_evidence_id": "geometry_evidence_id",
        "geometry_source_kind": "geometry_source_kind",
        "geometry_derivation": "geometry_derivation",
        "geometry_method": "geometry_method",
        "geometry_scope_class": "geometry_scope_class",
        "geometry_authority_class": "geometry_authority_class",
        "geometry_use_scope": "geometry_use_scope",
        "official_boundary": "official_boundary",
        "horizontal_uncertainty_metres": "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason": "horizontal_uncertainty_unknown_reason",
        "precision_scope": "precision_scope",
        "bridge_decision": "bridge_decision",
        "portable_input_binding": "portable_input_binding",
        "portable_capture_binding": "portable_capture_binding",
        "rejected_claims": "rejected_claims",
    }
    for project_key in sorted(acceptance_by_key):
        acceptance = acceptance_by_key[project_key]
        overlay = overlay_by_key[project_key]
        if (
            any(acceptance[left] != overlay[right] for left, right in crosswalk.items())
            or acceptance["project_entity_id"]
            != overlay["source_project_entity_id"]
            or acceptance["project_stable_key"]
            != overlay["source_project_stable_key"]
            or acceptance["geometry_overlay_id"] != overlay["overlay_id"]
            or acceptance["decision_basis"] != overlay["decision_reason"]
            or overlay["decision"] != "accepted"
            or overlay["reviewed_at"] != CURRENT_V08_REVIEW_DATE.isoformat()
        ):
            raise VerifiedConstructionCoreError(
                "v0.8 acceptance-overlay binding differs"
            )
        bridge, source = _validate_v08_bridge(
            acceptance,
            overlay,
            hydrated_crosscheck=hydrated_crosscheck,
        )
        bridges[project_key] = bridge
        sources[project_key] = source
    if (
        not isinstance(provenance, dict)
        or set(provenance)
        != {
            "contract_id",
            "review_scope",
            "reviewed_as_of",
            "base_contract",
            "workload_scope_bindings",
            "role_bindings",
            "excluded_source_roles",
            "context_evidence_bindings",
        }
        or provenance.get("contract_id")
        != "verified-construction-core-v0.8-provenance"
        or provenance.get("reviewed_as_of") != CURRENT_V08_REVIEW_DATE.isoformat()
        or provenance.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.7-provenance.json",
            "sha256": V07_PROVENANCE_DEFINITION_SHA256,
        }
        or provenance.get("workload_scope_bindings") != []
        or len(provenance.get("role_bindings", [])) != 1
        or len(provenance.get("excluded_source_roles", [])) != 2
        or len(provenance.get("context_evidence_bindings", [])) != 2
    ):
        raise VerifiedConstructionCoreError("v0.8 provenance contract differs")
    role = provenance["role_bindings"][0]
    exclusions = {
        (
            row.get("project_stable_key"),
            row.get("role"),
            row.get("party"),
            row.get("candidate_evidence_id"),
            row.get("relationship_scope"),
        )
        for row in provenance["excluded_source_roles"]
    }
    contexts = {
        (
            row.get("project_stable_key"),
            row.get("evidence_id"),
            row.get("usage_role"),
        )
        for row in provenance["context_evidence_bindings"]
    }
    if (
        (
            role.get("project_stable_key"),
            role.get("role"),
            role.get("party"),
            role.get("evidence_id"),
            role.get("relationship_scope"),
        )
        != (
            "curated:cdc-laverton-melbourne-campus:current-build",
            "operator",
            "CDC Data Centres",
            "d05112cf-0117-5f1a-9b7a-4087ec4f5c8f",
            "intended",
        )
        or exclusions
        != {
            (
                "curated:borealis-blonduos-data-center-campus:expansion-current-build",
                "operator",
                "Borealis Data Center",
                "bd494c0b-3936-5cc0-844a-67cd0db22812",
                "not_established",
            ),
            (
                "curated:borealis-blonduos-data-center-campus:expansion-current-build",
                "utility",
                "Landsvirkjun",
                "bd494c0b-3936-5cc0-844a-67cd0db22812",
                "not_established",
            ),
        }
        or contexts
        != {
            (
                "curated:enka-data-solutions-eds-ist-01-tuzla-data-center:initial-build",
                "0dd3dc39-1457-5bc3-b7d2-7ff44183aed3",
                "geometry_identity",
            ),
            (
                "curated:macquarie-ic3-super-west-facility:phase-1-build",
                "0ba37f72-6f9b-5d8f-8b8e-8b66e03dbb11",
                "project_context",
            ),
        }
    ):
        raise VerifiedConstructionCoreError("v0.8 provenance semantics differ")
    for collection, evidence_field in (
        (provenance["role_bindings"], "evidence_id"),
        (provenance["excluded_source_roles"], "candidate_evidence_id"),
        (provenance["context_evidence_bindings"], "evidence_id"),
    ):
        for binding in collection:
            project_key = binding["project_stable_key"]
            acceptance = acceptance_by_key[project_key]
            source_evidence = _v08_source_evidence(sources[project_key])
            if (
                binding.get("source_input_path") != acceptance["source_input_path"]
                or binding.get("source_input_sha256")
                != acceptance["source_input_sha256"]
                or binding[evidence_field] not in source_evidence
            ):
                raise VerifiedConstructionCoreError(
                    "v0.8 provenance evidence binding differs"
                )
    if (
        not isinstance(imagery, dict)
        or set(imagery)
        != {
            "contract_id",
            "review_scope",
            "reviewed_as_of",
            "base_contract",
            "default_outcome",
            "records",
        }
        or imagery.get("contract_id")
        != "verified-construction-core-v0.8-imagery-reviews"
        or imagery.get("reviewed_as_of") != CURRENT_V08_REVIEW_DATE.isoformat()
        or imagery.get("base_contract")
        != {
            "path": "definitions/verified-construction-core-v0.7-imagery-reviews.json",
            "sha256": V07_IMAGERY_REVIEW_DEFINITION_SHA256,
        }
        or imagery.get("default_outcome") != "not_reviewed_for_core_preview"
        or imagery.get("records") != []
    ):
        raise VerifiedConstructionCoreError("v0.8 imagery contract differs")
    return {
        "reviewed": reviewed,
        "overlays": overlays,
        "provenance": provenance,
        "imagery": imagery,
        "acceptance_by_key": acceptance_by_key,
        "overlay_by_key": overlay_by_key,
        "bridges": bridges,
        "sources": sources,
    }


def _v08_build_delta_rows(contracts: Mapping[str, Any]) -> dict[str, Any]:
    provenance = contracts["provenance"]
    roles_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provenance["role_bindings"]:
        roles_by_project[row["project_stable_key"]].append(row)
    contexts_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provenance["context_evidence_bindings"]:
        contexts_by_project[row["project_stable_key"]].append(row)
    evidence_pool: dict[str, dict[str, Any]] = {}
    evidence_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    projects: list[dict[str, Any]] = []
    sites: list[dict[str, Any]] = []
    for project_key in sorted(contracts["bridges"]):
        bridge = contracts["bridges"][project_key]
        source = contracts["sources"][project_key]
        acceptance = contracts["acceptance_by_key"][project_key]
        construction = bridge["construction_source"]
        source_evidence = _v08_source_evidence(source)
        evidence_pool.update(source_evidence)
        geometry_evidence = _v07_evidence_projection(bridge["geometry_evidence"])
        evidence_pool[geometry_evidence["evidence_id"]] = geometry_evidence
        project = construction["project"]
        campus = construction["campus"]
        project_id = project["entity_id"]
        site_id = _stable_id("vcc-site", campus["stable_key"])
        status_evidence_id = project["status_evidence_id"]
        geometry_evidence_id = bridge["geometry_evidence"]["evidence_id"]
        evidence_usage[status_evidence_id]["roles"].add("physical_status")
        evidence_usage[status_evidence_id]["project_ids"].add(project_id)
        evidence_usage[geometry_evidence_id]["roles"].add("geometry")
        evidence_usage[geometry_evidence_id]["project_ids"].add(project_id)
        observations = project.get("capacity_estimates_json", [])
        if not isinstance(observations, list):
            raise VerifiedConstructionCoreError("v0.8 capacity observations differ")
        for observation in observations:
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
            evidence_id = observation["evidence_id"]
            if evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError("v0.8 capacity evidence differs")
            evidence_usage[evidence_id]["roles"].add(
                f"typed_metric:{observation['metric']}"
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        power = [row for row in observations if row["metric"] in POWER_METRICS]
        energy = [row for row in observations if row["metric"] in ENERGY_METRICS]
        efficiency = [
            row for row in observations if row["metric"] in EFFICIENCY_METRICS
        ]
        if project.get("workloads_json") != []:
            raise VerifiedConstructionCoreError("v0.8 workload promotion differs")
        role_claims: list[dict[str, str]] = []
        projected_roles = {role: [] for role in ROLE_COLUMNS}
        for binding in roles_by_project.get(project_key, []):
            evidence_id = binding["evidence_id"]
            if evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError("v0.8 role evidence differs")
            role_claims.append(
                {
                    "evidence_id": evidence_id,
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
            )
            projected_roles[binding["role"]].append(binding["party"])
            evidence_usage[evidence_id]["roles"].add(f"role:{binding['role']}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        role_claims.sort(key=lambda row: (row["role"], row["party"], row["evidence_id"]))
        operating_model = project.get("operating_model")
        operating_model_evidence_id = project.get("operating_model_evidence_id")
        if operating_model:
            if operating_model_evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError(
                    "v0.8 operating-model evidence differs"
                )
            evidence_usage[operating_model_evidence_id]["roles"].add(
                "operating_model"
            )
            evidence_usage[operating_model_evidence_id]["project_ids"].add(project_id)
        elif operating_model_evidence_id is not None:
            raise VerifiedConstructionCoreError(
                "v0.8 operating-model identity differs"
            )
        for binding in contexts_by_project.get(project_key, []):
            evidence_id = binding["evidence_id"]
            if evidence_id not in evidence_pool:
                raise VerifiedConstructionCoreError("v0.8 context evidence differs")
            evidence_usage[evidence_id]["roles"].add(
                f"context:{binding['usage_role']}"
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        entity = bridge["geometry_entity"]
        geometry = entity["geometry"]
        status_date = _calendar_date(project["status_as_of"], "v0.8 status_as_of")
        image_outcome = contracts["imagery"]["default_outcome"]
        row = {
            "project_id": project_id,
            "project_stable_key": project_key,
            "site_id": site_id,
            "physical_site_stable_key": campus["stable_key"],
            "name": project["name"],
            "country": acceptance["country"],
            "country_iso_a2": V08_COUNTRY_ISO_A2[acceptance["country"]],
            "latitude": entity["latitude"],
            "longitude": entity["longitude"],
            "geometry_json": _json_bytes(geometry).decode().strip(),
            "geometry_type": geometry["type"],
            "geometry_source_entity_kind": acceptance["geometry_entity"],
            "geometry_derivation": acceptance["geometry_derivation"],
            "geometry_method": acceptance["geometry_method"],
            "geometry_scope_class": acceptance["geometry_scope_class"],
            "geometry_authority_class": acceptance["geometry_authority_class"],
            "geometry_use_scope": acceptance["geometry_use_scope"],
            "geometry_precision_scope": acceptance["precision_scope"],
            "horizontal_uncertainty_metres": (
                ""
                if acceptance["horizontal_uncertainty_metres"] is None
                else acceptance["horizontal_uncertainty_metres"]
            ),
            "horizontal_uncertainty_unknown_reason": acceptance[
                "horizontal_uncertainty_unknown_reason"
            ],
            "geometry_evidence_id": geometry_evidence_id,
            "last_observed_physical_status": project["status"],
            "status_as_of": project["status_as_of"],
            "status_age_days_at_review": (
                CURRENT_V08_REVIEW_DATE - status_date
            ).days,
            "status_method": project["status_method"],
            "status_evidence_id": status_evidence_id,
            "verification_posture": _verification_posture(
                acceptance["geometry_authority_class"],
                acceptance["geometry_use_scope"],
            ),
            "independent_imagery_verification": "false",
            "imagery_review_outcome": image_outcome,
            "development_type": "unknown",
            "development_type_unknown_reason": "source evidence does not distinguish greenfield, expansion, or retrofit",
            "operating_model": operating_model or "unknown",
            "operating_model_unknown_reason": (
                "" if operating_model else "not established by selected evidence"
            ),
            "operating_model_evidence_id": operating_model_evidence_id or "",
            "workloads_json": "[]",
            "workload_unknown_reason": "not established by selected evidence",
            "role_claims_json": _json_bytes(role_claims).decode().strip(),
            "power_observations_json": _json_bytes(power).decode().strip(),
            "power_unknown_reason": "" if power else "no typed project power observation; not estimated",
            "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
            "annual_energy_unknown_reason": "" if energy else "no scoped annual-energy inputs; not estimated",
            "efficiency_observations_json": _json_bytes(efficiency).decode().strip(),
            "efficiency_unknown_reason": "" if efficiency else "no scoped PUE or WUE observation",
            "owner": "; ".join(sorted(projected_roles["owner"])),
            "operator": "; ".join(sorted(projected_roles["operator"])),
            "users": "; ".join(sorted(projected_roles["user"])),
            "tenants": "; ".join(sorted(projected_roles["tenant"])),
            "customers": "; ".join(sorted(projected_roles["customer"])),
            "status_source_url": evidence_pool[status_evidence_id]["source_url"],
            "geometry_source_url": geometry_evidence["source_url"],
        }
        projects.append(row)
        sites.append(
            {
                "site_id": site_id,
                "physical_site_stable_key": campus["stable_key"],
                "name": campus["name"],
                "country": row["country"],
                "country_iso_a2": row["country_iso_a2"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "geometry_json": row["geometry_json"],
                "geometry_type": row["geometry_type"],
                "geometry_source_entity_kinds_json": _json_bytes(
                    [row["geometry_source_entity_kind"]]
                ).decode().strip(),
                "geometry_derivations_json": _json_bytes(
                    [row["geometry_derivation"]]
                ).decode().strip(),
                "geometry_methods_json": _json_bytes(
                    [row["geometry_method"]]
                ).decode().strip(),
                "geometry_scope_classes_json": _json_bytes(
                    [row["geometry_scope_class"]]
                ).decode().strip(),
                "geometry_authority_classes_json": _json_bytes(
                    [row["geometry_authority_class"]]
                ).decode().strip(),
                "geometry_use_scopes_json": _json_bytes(
                    [row["geometry_use_scope"]]
                ).decode().strip(),
                "geometry_precision_scopes_json": _json_bytes(
                    [row["geometry_precision_scope"]]
                ).decode().strip(),
                "horizontal_uncertainty_metres": row[
                    "horizontal_uncertainty_metres"
                ],
                "horizontal_uncertainty_unknown_reason": row[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "geometry_evidence_ids_json": _json_bytes(
                    [geometry_evidence_id]
                ).decode().strip(),
                "project_count": 1,
                "project_ids_json": _json_bytes([project_id]).decode().strip(),
                "project_stable_keys_json": _json_bytes([project_key]).decode().strip(),
                "statuses_json": _json_bytes(
                    [row["last_observed_physical_status"]]
                ).decode().strip(),
                "oldest_status_as_of": row["status_as_of"],
                "newest_status_as_of": row["status_as_of"],
                "verification_posture": row["verification_posture"],
                "independent_imagery_verification": "false",
                "imagery_review_outcomes_json": _json_bytes(
                    [image_outcome]
                ).decode().strip(),
            }
        )
    if set(evidence_usage) != V08_EVIDENCE_IDS:
        raise VerifiedConstructionCoreError("v0.8 projected evidence allowlist differs")
    evidence = [
        {
            **evidence_pool[evidence_id],
            "roles_json": _json_bytes(sorted(usage["roles"])).decode().strip(),
            "project_ids_json": _json_bytes(
                sorted(usage["project_ids"])
            ).decode().strip(),
        }
        for evidence_id, usage in sorted(evidence_usage.items())
    ]
    return {"projects": projects, "sites": sites, "evidence": evidence}


def _v08_portable_source_inputs(
    contracts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    base_manifest = _load_json(LEGACY_PREVIEW_V07_DIR / "manifest.json")
    rows = list(base_manifest["portable_source_inputs"])
    new: dict[str, dict[str, Any]] = {}
    for acceptance in contracts["reviewed"]["acceptances"]:
        for binding in (
            acceptance["portable_input_binding"],
            {
                "path": acceptance["bridge_path"],
                "bytes": acceptance["bridge_bytes"],
                "sha256": acceptance["bridge_sha256"],
            },
        ):
            record = {
                "path": binding["path"],
                "bytes": binding["bytes"],
                "sha256": binding["sha256"],
                "parent_manifests": [],
            }
            previous = new.get(record["path"])
            if previous is not None and previous != record:
                raise VerifiedConstructionCoreError("v0.8 portable input differs")
            new[record["path"]] = record
    rows.extend(new.values())
    rows.sort(key=lambda row: row["path"])
    if len(rows) != 57 or len({row["path"] for row in rows}) != 57:
        raise VerifiedConstructionCoreError("v0.8 portable input count differs")
    for row in rows:
        path = _repository_input(row["path"], row["sha256"], "v0.8 portable input")
        if path.stat().st_size != row["bytes"]:
            raise VerifiedConstructionCoreError(
                "v0.8 portable input byte count differs"
            )
    return rows


def _v08_map_html(
    geojson: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> bytes:
    document = _v07_map_html(geojson, evidence).decode("utf-8")
    if "Verified Construction Core v0.7 preview" not in document:
        raise VerifiedConstructionCoreError("v0.8 map title seam differs")
    return document.replace(
        "Verified Construction Core v0.7 preview",
        "Verified Construction Core v0.8 preview",
    ).encode("utf-8")


def _v08_schema() -> dict[str, Any]:
    schema = _v07_schema()
    schema["format"] = "datacenter-atlas-verified-construction-core-schema-v8"
    schema["preview_id"] = CURRENT_V08_PREVIEW_ID
    return schema


def _v08_readme(report: Mapping[str, Any]) -> bytes:
    return f"""# Verified Construction Core v0.8 preview

This tracked, non-final preview contains **{report['selected_physical_site_count']} physical sites**
and **{report['selected_project_count']} linked projects** in {len(report['country_counts'])}
countries. Every project retains a dated authoritative physical-status observation and an exact
reviewed geometry scope. Five project rows carry official boundaries; the remaining 39 are
explicit project or campus locators, never construction footprints by implication.

The eight-row v0.8 delta adds Digital Realty VIE13, ENKA EDS IST 01, Colt FRA3, Macquarie IC3
Super West Phase 1, Equinix MU4 Phase 3, CDC Laverton, Pure DC LON01 B2, and the Borealis
Blönduós expansion. VIE13 and IST 01 use direct first-party facility-page points as project
locators. Six frozen OpenStreetMap polygons are retained as contributor-mapped geometry: Colt's
named building is a project locator, while Macquarie, Equinix, CDC, Pure DC, and Borealis use
explicit parent-campus locators. None is an official boundary or current construction extent.

Digital Realty VIE13 retains a source-bound colocation operating model. CDC contributes one
intended operator claim. Borealis operator and utility strings remain explicit non-publication
decisions. ENKA identity context and Macquarie's parent-facility design PUE remain context-only;
campus capacity and PUE values are not promoted into project metrics. No v0.8 workload is added.

The artifact is deterministic and rebuildable in a clean clone from the 57 manifest-bound portable
inputs plus the frozen v0.7 artifact. Ignored v97, global-v3, and v14 payloads are optional hydrated
cross-checks, not build dependencies. All eight v0.8 rows inherit the not-reviewed imagery outcome
and remain `independent_imagery_verification=false`.

This is not the final 100-site Verified Construction Core v1. Its final-release gates remain
unsatisfied and `publishable_as_final` is false.
""".encode("utf-8")


def _v08_attribution(evidence: Sequence[Mapping[str, Any]]) -> bytes:
    rows = {(row["publisher"], row["license"], row["source_url"]) for row in evidence}
    lines = [
        "Data Center Atlas Verified Construction Core v0.8 preview",
        "",
        "Compact derived facts only; third-party terms remain controlling.",
        "",
        *(
            f"- {publisher} | {license_name} | {url}"
            for publisher, license_name, url in sorted(rows)
        ),
        "",
        "Map-provider terms:",
        *(
            f"- {label} | {license_name} | {url}"
            for label, license_name, url in _v07_map_attribution_notices(evidence)
        ),
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _v08_payloads() -> tuple[dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
    validate_frozen_v07(LEGACY_PREVIEW_V07_DIR)
    contracts = _v08_contracts(
        hydrated_crosscheck=_v08_hydrated_crosscheck_available()
    )
    base_projects = _load_csv(LEGACY_PREVIEW_V07_DIR / "projects.csv", PROJECT_FIELDS)
    base_sites = _load_csv(LEGACY_PREVIEW_V07_DIR / "sites.csv", SITE_FIELDS)
    base_evidence = _load_csv(LEGACY_PREVIEW_V07_DIR / "evidence.csv", EVIDENCE_FIELDS)
    base_report = _load_json(LEGACY_PREVIEW_V07_DIR / "selection-report.json")
    delta = _v08_build_delta_rows(contracts)
    projects = sorted(
        [*base_projects, *delta["projects"]],
        key=lambda row: row["project_stable_key"],
    )
    sites = sorted(
        [*base_sites, *delta["sites"]],
        key=lambda row: row["physical_site_stable_key"],
    )
    evidence = sorted(
        [*base_evidence, *delta["evidence"]],
        key=lambda row: row["evidence_id"],
    )
    if (
        len(projects) != 44
        or len(sites) != 41
        or len(evidence) != 100
        or len({row["project_id"] for row in projects}) != 44
        or len({row["site_id"] for row in sites}) != 41
        or len({row["evidence_id"] for row in evidence}) != 100
    ):
        raise VerifiedConstructionCoreError("v0.8 cohort count or uniqueness differs")
    gates = _final_release_gates(sites, projects)
    gates["clean_clone_rebuild"] = {
        "passed": True,
        "reason": "all current-delta inputs and the frozen base artifact are tracked and hash-bound",
    }
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    provenance_decisions = {
        key: [
            *base_report["provenance_decisions"][key],
            *contracts["provenance"][key],
        ]
        for key in ("workload_scope_bindings", "role_bindings", "excluded_source_roles")
    }
    provenance_decisions["context_evidence_bindings"] = contracts["provenance"][
        "context_evidence_bindings"
    ]
    report = {
        **base_report,
        "format": "datacenter-atlas-verified-construction-core-selection-v8",
        "publishable_as_final": all(
            gate.get("passed", False) for gate in gates.values()
        ),
        "reviewed_at": CURRENT_V08_REVIEW_DATE.isoformat(),
        "selected_project_count": 44,
        "selected_physical_site_count": 41,
        "official_boundary_project_count": 5,
        "reviewed_site_locator_project_count": 39,
        "non_selected_source_row_count": 487,
        "selection_first_failure_counts": V08_SELECTION_FIRST_FAILURE_COUNTS,
        "country_counts": country_counts,
        "final_release_gates": gates,
        "imagery_review_provenance": list(
            base_report["imagery_review_provenance"]
        ),
        "provenance_decisions": provenance_decisions,
        "reviewed_overlay_queue": [
            *base_report["reviewed_overlay_queue"],
            *contracts["overlays"]["overlays"],
        ],
    }
    if (
        len(country_counts) != 25
        or sum(row["country_iso_a2"] != "US" for row in sites) != 35
        or sum(_is_official_boundary(row) for row in projects) != 5
        or sum(_is_reviewed_locator(row) for row in projects) != 39
        or sum(V08_SELECTION_FIRST_FAILURE_COUNTS.values()) != 531
    ):
        raise VerifiedConstructionCoreError("v0.8 expected accounting differs")
    geojson = _geojson(sites)
    geojson["name"] = "Data Center Atlas Verified Construction Core v0.8 preview"
    payloads = {
        "ATTRIBUTION.txt": _v08_attribution(evidence),
        "README.md": _v08_readme(report),
        "evidence.csv": _csv_bytes(evidence, EVIDENCE_FIELDS),
        "map.html": _v08_map_html(geojson, evidence),
        "projects.csv": _csv_bytes(projects, PROJECT_FIELDS),
        "schema.json": _json_bytes(_v08_schema()),
        "selection-report.json": _json_bytes(report),
        "sites.csv": _csv_bytes(sites, SITE_FIELDS),
        "sites.geojson": _json_bytes(geojson),
    }
    portable = _v08_portable_source_inputs(contracts)
    return payloads, report, portable


def _v08_manifest(
    payloads: Mapping[str, bytes],
    report: Mapping[str, Any],
    portable: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-verified-construction-core-preview-v8",
        "preview_id": CURRENT_V08_PREVIEW_ID,
        "release_status": "preview",
        "publishable_as_final": report["publishable_as_final"],
        "base_preview_id": "2026-08-20-preview-v0.7",
        "base_preview_manifest_sha256": LEGACY_PREVIEW_V07_MANIFEST_SHA256,
        "base_preview_commit": LEGACY_PREVIEW_V07_COMMIT,
        "source_release_id": SOURCE_RELEASE_ID,
        "source_release_manifest_path": "releases/2026-07-22-open-seed-v97/manifest.json",
        "source_release_manifest_sha256": "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
        "definition_paths": {
            "imagery_reviews": "definitions/verified-construction-core-v0.8-imagery-reviews.json",
            "provenance": "definitions/verified-construction-core-v0.8-provenance.json",
            "reviewed_overlays": "definitions/verified-construction-core-reviewed-overlays-v6.json",
            "reviewed_sites": "definitions/verified-construction-core-v0.8-reviewed-sites.json",
        },
        "review_definition_sha256": V08_REVIEW_DEFINITION_SHA256,
        "imagery_review_definition_sha256": V08_IMAGERY_REVIEW_DEFINITION_SHA256,
        "provenance_definition_sha256": V08_PROVENANCE_DEFINITION_SHA256,
        "overlay_definition_sha256": V08_OVERLAY_DEFINITION_SHA256,
        "portable_source_inputs": list(portable),
        "reviewed_at": CURRENT_V08_REVIEW_DATE.isoformat(),
        "counts": {
            "physical_sites": 41,
            "projects": 44,
            "evidence": 100,
            "countries": 25,
            "non_us_sites": 35,
            "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 39,
        },
        "files": {
            name: {"bytes": len(payload), "sha256": _sha256_bytes(payload)}
            for name, payload in sorted(payloads.items())
        },
    }


def build_preview(output_dir: Path = CURRENT_V08_PREVIEW_DIR) -> dict[str, Any]:
    """Build the current v0.8 preview from tracked, hash-bound inputs."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise VerifiedConstructionCoreError(f"refusing to overwrite {output_dir}")
    payloads, report, portable = _v08_payloads()
    manifest = _v08_manifest(payloads, report, portable)
    manifest_bytes = _json_bytes(manifest)
    complete = {
        **payloads,
        "manifest.json": manifest_bytes,
        "manifest.sha256": f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode(),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, payload in complete.items():
            with (stage / name).open("xb") as handle:
                handle.write(payload)
        os.replace(stage, output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_preview(output_dir)
    return manifest


def _validate_v08_preview(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError("v0.8 preview directory differs")
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError("v0.8 manifest trust root differs")
    manifest_bytes = manifest_path.read_bytes()
    if checksum_path.read_bytes() != (
        f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode()
    ):
        raise VerifiedConstructionCoreError("v0.8 manifest checksum differs")
    manifest = _load_json(manifest_path)
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("v0.8 manifest files differ")
    expected_inventory = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_inventory:
        raise VerifiedConstructionCoreError("v0.8 preview inventory differs")
    for name, metadata in files.items():
        member = path / name
        if (
            Path(name).name != name
            or member.is_symlink()
            or not member.is_file()
            or member.stat().st_size != metadata.get("bytes")
            or _sha256_file(member) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(f"v0.8 member differs: {name}")
    payloads, report, portable = _v08_payloads()
    if manifest != _v08_manifest(payloads, report, portable):
        raise VerifiedConstructionCoreError("v0.8 manifest semantics differ")
    for name, expected in payloads.items():
        if (path / name).read_bytes() != expected:
            raise VerifiedConstructionCoreError(
                f"v0.8 generated member differs: {name}"
            )
    return manifest


def validate_preview(path: Path = CURRENT_V08_PREVIEW_DIR) -> dict[str, Any]:
    """Validate current v0.8 or dispatch an immutable v0.1-v0.7 preview."""
    path = Path(path)
    manifest_path = path / "manifest.json"
    if (
        path.is_symlink()
        or not path.is_dir()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        raise VerifiedConstructionCoreError("preview manifest trust root differs")
    manifest = _load_json(manifest_path)
    preview_id = manifest.get("preview_id") if isinstance(manifest, dict) else None
    if preview_id == CURRENT_V08_PREVIEW_ID:
        return _validate_v08_preview(path)
    validator = _frozen_preview_validator(preview_id)
    if validator is not None:
        return validator(path)
    raise VerifiedConstructionCoreError("preview id differs")


__all__ = [
    "CURRENT_V07_DEFINITION_PATHS",
    "CURRENT_V07_PREVIEW_DIR",
    "CURRENT_V07_PREVIEW_ID",
    "CURRENT_V07_REVIEW_DATE",
    "CURRENT_V08_DEFINITION_PATHS",
    "CURRENT_V08_PREVIEW_DIR",
    "CURRENT_V08_PREVIEW_ID",
    "CURRENT_V08_REVIEW_DATE",
    "IMAGERY_REVIEW_DEFINITION",
    "LEGACY_PREVIEW_V01_DIR",
    "LEGACY_PREVIEW_V02_DIR",
    "LEGACY_PREVIEW_V03_DIR",
    "LEGACY_PREVIEW_V04_DIR",
    "LEGACY_PREVIEW_V05_COMMIT",
    "LEGACY_PREVIEW_V05_DIR",
    "LEGACY_PREVIEW_V06_COMMIT",
    "LEGACY_PREVIEW_V06_DIR",
    "LEGACY_PREVIEW_V06_MANIFEST_SHA256",
    "LEGACY_PREVIEW_V07_COMMIT",
    "LEGACY_PREVIEW_V07_DIR",
    "LEGACY_PREVIEW_V07_MANIFEST_SHA256",
    "PREVIEW_DIR",
    "PreviewProfile",
    "PROVENANCE_DEFINITION",
    "VerifiedConstructionCoreError",
    "build_preview",
    "load_current_v07_profile",
    "load_current_v08_profile",
    "validate_frozen_preview",
    "validate_frozen_v01",
    "validate_frozen_v02",
    "validate_frozen_v03",
    "validate_frozen_v04",
    "validate_frozen_v05",
    "validate_frozen_v06",
    "validate_frozen_v07",
    "validate_preview",
]
