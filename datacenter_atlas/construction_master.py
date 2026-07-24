"""Deterministic public/open row ledger for construction discovery evidence.

The master is an observation ledger, not an entity-resolution product.  It
keeps source-supported construction rows, review leads, and structural or
imagery discovery candidates in explicit tiers.  Advisory links never merge
rows or change lifecycle, identity, capacity, or construction arithmetic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence, TextIO
import uuid


DEFINITION_SCHEMA_VERSION = 1
SCHEMA_VERSION = 1
FORMAT = "datacenter-atlas-construction-master-v1"
BUNDLE_FORMAT = "datacenter-atlas-construction-master-bundle-v1"
JSONL_FILENAME = "construction-master.jsonl"
CSV_FILENAME = "construction-master.csv"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {
        JSONL_FILENAME,
        CSV_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)
SCOPE_POLICY = {
    "automatic_entity_merges": False,
    "benchmark_parity_claimed": False,
    "candidate_or_review_rows_promoted": False,
    "construction_arithmetic_limited_to_tier_a": True,
    "cross_source_resolution_accepted": False,
    "fuzzy_review_rows_in_construction_arithmetic": False,
    "global_completeness_claimed": False,
    "public_open_redistribution_scope": True,
    "structural_or_cv_rows_in_construction_arithmetic": False,
    "unique_physical_site_count": None,
    "within_release_links_are_advisory_only": True,
}
ROW_NAMESPACE = uuid.UUID("bc01ce61-ab84-50d7-b21e-86dbe69154fd")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
V2_MASTER_ID = "2026-07-18-public-open-v2"
V3_MASTER_ID = "2026-07-18-public-open-v3"
V4_MASTER_ID = "2026-07-18-public-open-v4"
V5_MASTER_ID = "2026-07-18-public-open-v5"
V6_MASTER_ID = "2026-07-19-public-open-v6"
V7_MASTER_ID = "2026-07-19-public-open-v7"
V8_MASTER_ID = "2026-07-19-public-open-v8"
V9_MASTER_ID = "2026-07-19-public-open-v9"
V10_MASTER_ID = "2026-07-19-public-open-v10"
V11_MASTER_ID = "2026-07-19-public-open-v11"
V12_MASTER_ID = "2026-07-19-public-open-v12"
V13_MASTER_ID = "2026-07-19-public-open-v13"
V14_MASTER_ID = "2026-07-19-public-open-v14"
IRELAND_OBSERVATION_KIND = "official_planning_application_review_lead"
IRELAND_ARTIFACT_ID = "ireland-planning-applications-2026-07-18-v1"
ENGLAND_OBSERVATION_KIND = "official_england_planning_application_review_lead"
ENGLAND_ARTIFACT_ID = "england-planning-data-2026-07-18-v1"
NSW_OBSERVATION_KIND = "official_nsw_major_projects_planning_review_lead"
NSW_ARTIFACT_ID = "nsw-major-projects-data-storage-2026-07-18-v1"
NETHERLANDS_OBSERVATION_KIND = "official_netherlands_koop_permit_review_lead"
NETHERLANDS_ARTIFACT_ID = (
    "netherlands-koop-official-publications-2026-07-18-v1"
)
NEW_ZEALAND_OBSERVATION_KIND = "official_new_zealand_fast_track_review_lead"
NEW_ZEALAND_ARTIFACT_ID = "new-zealand-fast-track-2026-07-18-v1"
FRANCE_OBSERVATION_KIND = (
    "official_france_igedd_environmental_opinion_review_lead"
)
FRANCE_ARTIFACT_ID = (
    "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1"
)
_V2_INPUT_KEYS = {
    "analyst_reviews",
    "candidate_fusion",
    "coverage_context",
    "satellite_batches",
    "tier_a_releases",
    "tier_b_edgemode",
    "tier_b_fuzzy_release",
    "tier_b_ireland_planning",
    "tier_c_structural",
    "within_release_resolution",
}
_V2_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-007",
}
_V2_COUNT_CONTRACT = {
    "analyst_review_rows": 21,
    "fusion_overlay_rows": 14_324,
    "fuzzy_review_rows": 6_130,
    "ireland_planning_rows": 114,
    "resolution_advisory_links": 8_586,
    "structural_candidate_rows": 102_451,
    "tier_a_rows": 168,
    "tier_b_rows": 6_253,
    "tier_c_rows": 102_472,
    "total_rows": 108_893,
}
_V3_INPUT_KEYS = _V2_INPUT_KEYS | {"tier_b_england_planning"}
_V3_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-009",
}
_V3_COUNT_CONTRACT = {
    "analyst_review_rejected_rows": 18,
    "analyst_review_retained_rows": 7,
    "analyst_review_rows": 25,
    "england_context_only_excluded_rows": 1,
    "england_planning_rows": 3,
    "fusion_overlay_rows": 14_324,
    "fuzzy_review_rows": 6_130,
    "ireland_planning_rows": 114,
    "resolution_advisory_links": 8_586,
    "structural_candidate_rows": 102_451,
    "tier_a_rows": 168,
    "tier_b_rows": 6_256,
    "tier_c_rows": 102_476,
    "total_rows": 108_900,
}
_V3_ANALYST_REVIEW_CONTRACT = {
    "expected_decisions": {
        "reject_automated_mask_for_site_promotion": 18,
        "retain_site_aligned_change_candidate_for_manual_followup": 7,
    },
    "expected_rows": 25,
    "source": "candidate-fusion-osm-planet-priority-v9",
}
_V3_FUSION_DEFINITION_SHA256 = (
    "e525b85df09feea10a354d41a0c0896a59963d9916e106b106aef13098f03871"
)
_V3_FUSION_MANIFEST_SHA256 = (
    "ea0ad82b3082c7473282196246da616f2957247a80ddd126abee5a030375db11"
)
_V3_ENGLAND_MANIFEST_SHA256 = (
    "774c51894a2a46cbb10459cc1ebd777059c5bdab425599bfc48b6dd9d248676c"
)
_V4_INPUT_KEYS = _V3_INPUT_KEYS | {
    "tier_b_netherlands_koop",
    "tier_b_new_zealand_fast_track",
    "tier_b_nsw_major_projects",
}
_V4_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-011",
}
_V4_COUNT_CONTRACT = {
    "analyst_review_rejected_rows": 23,
    "analyst_review_retained_rows": 8,
    "analyst_review_rows": 31,
    "england_context_only_excluded_rows": 1,
    "england_planning_rows": 3,
    "fusion_overlay_rows": 14_324,
    "fuzzy_review_rows": 6_130,
    "ireland_planning_rows": 114,
    "netherlands_context_excluded_rows": 7,
    "netherlands_coordinate_rows": 12,
    "netherlands_mean_anchor_rows": 4,
    "netherlands_planning_rows": 13,
    "new_zealand_planning_rows": 3,
    "new_zealand_prior_related_rows": 1,
    "new_zealand_project_candidate_rows": 2,
    "nsw_planning_rows": 22,
    "nsw_untyped_power_statements": 10,
    "resolution_advisory_links": 8_586,
    "structural_candidate_rows": 102_451,
    "tier_a_rows": 168,
    "tier_b_rows": 6_294,
    "tier_c_rows": 102_482,
    "total_rows": 108_944,
}
_V4_ANALYST_REVIEW_CONTRACT = {
    "expected_decisions": {
        "reject_automated_mask_for_site_promotion": 23,
        "retain_site_aligned_change_candidate_for_manual_followup": 8,
    },
    "expected_rows": 31,
    "source": "candidate-fusion-osm-planet-priority-v10",
}
_V4_FUSION_DEFINITION_SHA256 = (
    "3e8c321f17a0ff915dc55e79dcdb511b034bf5b225a8d97c8d02c15a091340e1"
)
_V4_FUSION_MANIFEST_SHA256 = (
    "83b51f75f2063815422fce3c308af8975a134b68b93aefd0b5ccbcad5c7bf3d4"
)
_V4_FUSION_DATA_SHA256 = (
    "71578e0722bd1af07dee3fbb33fcbd1dae3b633ad95c12079a412dbd80a3070c"
)
_V4_FUSION_BATCH_PINS = {
    "satellite_review_runs/2026-07-18-global-open-v3-active-001": (
        "ff0323728733557727b8d07c9aae6e2801be8a430b0b5e4f4fe7d2a168079a5a"
    ),
    "satellite_review_runs/2026-07-18-global-open-v3-proposed-001": (
        "e012b06344c2332e1e3192f005db099f15058b973505e7be09907e2ff221e2f6"
    ),
    "satellite_review_runs/2026-07-18-global-open-v3-unknown-010": (
        "672a92b835d4884f26f849318b1c8766706895510c11edc00bc5dcc131ea35d5"
    ),
}
_V4_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "a4d97cecc43e4c61b1c1b325ee6aa8a3b16a66225b890713c5f39c4c71877bf0"
)
_V4_NSW_MANIFEST_SHA256 = (
    "650c9b6e194fea0dbe1ce28ecba0cb8f114b8ec7d6571a0ee1f31c41f0d660f2"
)
_V4_NETHERLANDS_MANIFEST_SHA256 = (
    "2fc151a0088f4d03cba8985fb45552400236518cd9022672d49280ab9d4d9cd2"
)
_V4_NEW_ZEALAND_MANIFEST_SHA256 = (
    "97e9b78cc516acd48e6d3e3f80d367977bc7ae3b882820dc3e0f7e185b6cb264"
)
_V5_INPUT_KEYS = _V4_INPUT_KEYS | {"tier_b_france_igedd"}
_V5_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-015",
}
_V5_COUNT_CONTRACT = {
    "analyst_review_rejected_rows": 31,
    "analyst_review_retained_rows": 12,
    "analyst_review_rows": 43,
    "england_context_only_excluded_rows": 1,
    "england_planning_rows": 3,
    "france_igedd_ancillary_rows": 1,
    "france_igedd_direct_rows": 3,
    "france_igedd_metric_observations": 13,
    "france_igedd_relationship_evidence": 1,
    "france_igedd_rows": 4,
    "fusion_overlay_rows": 14_324,
    "fuzzy_review_rows": 6_130,
    "ireland_planning_rows": 114,
    "netherlands_context_excluded_rows": 7,
    "netherlands_coordinate_rows": 12,
    "netherlands_mean_anchor_rows": 4,
    "netherlands_planning_rows": 13,
    "new_zealand_planning_rows": 3,
    "new_zealand_prior_related_rows": 1,
    "new_zealand_project_candidate_rows": 2,
    "nsw_planning_rows": 22,
    "nsw_untyped_power_statements": 10,
    "resolution_advisory_links": 8_586,
    "structural_candidate_rows": 102_451,
    "tier_a_rows": 168,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 108_960,
}
_V5_ANALYST_REVIEW_CONTRACT = {
    "expected_decisions": {
        "reject_automated_mask_for_site_promotion": 31,
        "retain_site_aligned_change_candidate_for_manual_followup": 12,
    },
    "expected_rows": 43,
    "source": "candidate-fusion-osm-planet-priority-v13",
}
_V5_FUSION_DEFINITION_SHA256 = (
    "63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33"
)
_V5_FUSION_MANIFEST_SHA256 = (
    "12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9"
)
_V5_FUSION_DATA_SHA256 = (
    "aa4204a2cbd865dd3bb6f9bbb249584f2d314882bfab397553f36807f0636f60"
)
_V5_FUSION_BATCH_PINS = {
    "satellite_review_runs/2026-07-18-global-open-v3-active-001": (
        "ff0323728733557727b8d07c9aae6e2801be8a430b0b5e4f4fe7d2a168079a5a"
    ),
    "satellite_review_runs/2026-07-18-global-open-v3-proposed-001": (
        "e012b06344c2332e1e3192f005db099f15058b973505e7be09907e2ff221e2f6"
    ),
    "satellite_review_runs/2026-07-18-global-open-v3-unknown-015": (
        "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8"
    ),
}
_V5_REVIEW_SOURCE_BATCH_PINS = {
    **_V5_FUSION_BATCH_PINS,
    "satellite_review_runs/2026-07-18-global-open-v3-unknown-010": (
        "672a92b835d4884f26f849318b1c8766706895510c11edc00bc5dcc131ea35d5"
    ),
    "satellite_review_runs/2026-07-18-global-open-v3-unknown-013": (
        "e3a99d23b74f56caa0eb817465f6c37a2d23cdb1927428152fdb000c0adcb9a6"
    ),
}
_V5_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8"
)
_V5_FRANCE_MANIFEST_SHA256 = (
    "aef3c9b21a07d436bd48eafc26fb67e9ea81dbbb827f76429f66e65708307e49"
)
_V5_FRANCE_ASSESSMENT_SHA256 = (
    "9f0f7a9884662795eb14889f7b901098ce832cefddd4086204273e6b76473e32"
)
_V5_FRANCE_DEFINITION_SHA256 = (
    "1d8bc43fe7a1c9d4d88b87302c2fc292039e003f1b5e695c3fc898581ed12138"
)
_V5_FRANCE_OBSERVATIONS_SHA256 = (
    "9f9e91325049f66e1ad7b65fe329030e9725518404aa10540bd66942fcf8522e"
)
_V5_FRANCE_SCHEMA_SHA256 = (
    "0a941358b21f701bc8a2574c9a154f1483f671e54ce92a09d02de3b30e12ab74"
)
_V6_INPUT_KEYS = _V5_INPUT_KEYS
_V6_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-020",
}
_V6_COUNT_CONTRACT = {
    **_V5_COUNT_CONTRACT,
    "tier_a_rows": 172,
    "total_rows": 108_964,
}
_V6_TIER_A_PROJECTION_SHA256 = (
    "b6bc6cd6afbb841e9b1f9a89cb1f4f59c6dcdc0d15af75d3ffff864e4316f6a0"
)
_V6_OPEN_SEED_MANIFEST_SHA256 = (
    "25c7fb0501db2753abf957830ef70d0aff2f36fbd7977405052dfa0856cfbf28"
)
_V6_OPEN_SEED_DATA_SHA256 = (
    "54dcad7d061a9b13962e9fe916cdf3684a0cf187dc01ede30b47d565f6a515e7"
)
_V6_OPEN_SEED_EVIDENCE_SHA256 = (
    "2e6e7398b04846c11247e3371153ab88daea82f02ffaee9f44a0ee2cecbc10e7"
)
_V6_GLOBAL_OPEN_MANIFEST_SHA256 = (
    "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
)
_V6_GLOBAL_OPEN_DATA_SHA256 = (
    "59c25d7192b024636ef8d3d27282866fcdd146ae5160e9f2c41f65bfcbbda29e"
)
_V6_GLOBAL_OPEN_EVIDENCE_SHA256 = (
    "92e69e382a45f0d8ecf797764198fb4c4b6df3b4457082a063859f16e0725cc9"
)
_V6_FEDERATION_MANIFEST_SHA256 = (
    "9dc150f8700a2176d0d602aedd56c2f55de1d8a3eb412453406a8de0cccfdb42"
)
_V6_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "add8093e90db0d6f34e7d44569bb21f51786b9ee9588c03e5098a065bce79745"
)
_V6_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "5130b2b3879e0eb6d5e0d03d8543ed053625e46162a9aa4109a6bb9224c1aeff"
)
_V7_INPUT_KEYS = _V6_INPUT_KEYS
_V7_COUNT_CONTRACT = {
    **_V6_COUNT_CONTRACT,
    "tier_a_rows": 178,
    "total_rows": 108_970,
}
_V7_TIER_A_PROJECTION_SHA256 = (
    "4eb28b56189e86dca6bb982c9f53153b300151858437919086d36a7913195efa"
)
_V7_OPEN_SEED_MANIFEST_SHA256 = (
    "94c7a7c8ad21261fa0eb4c6ffe51ad7b04888941cc02fdf0c377c791f5fbb1a2"
)
_V7_OPEN_SEED_DATA_SHA256 = (
    "6a044c1de240cd27f6c18ee56f48aabc83dafd66dcab1c38cc85066ce6c80d75"
)
_V7_OPEN_SEED_EVIDENCE_SHA256 = (
    "fd797173a859fa60ba16b1fd80cfea8cd27120672149082a8482e672395e8f3f"
)
_V8_INPUT_KEYS = _V7_INPUT_KEYS
_V8_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-022",
}
_V8_COUNT_CONTRACT = {
    **_V7_COUNT_CONTRACT,
    "tier_a_rows": 180,
    "total_rows": 108_972,
}
_V8_TIER_A_PROJECTION_SHA256 = (
    "c9d7110ac5ff37e6f3a6ca4d2e752dae6c3bbd9eb32f2bd75859ed24e9ce66f0"
)
_V8_OPEN_SEED_MANIFEST_SHA256 = (
    "2beb69207da8cf312b0d843ce576066ec786ca583b5039874876245e4032f451"
)
_V8_OPEN_SEED_DATA_SHA256 = (
    "2b763e6640c650826cf850dc8078652777afa13b68b4d384f6e580e7e71effdb"
)
_V8_OPEN_SEED_EVIDENCE_SHA256 = (
    "01c29e88c32bb908937ff9d31355b2cd566cd1ed4cba2bc819c7e3b745050ea6"
)
_V8_FEDERATION_MANIFEST_SHA256 = (
    "47dc6441265fd76f2d20fc826b5b13f80567db4b85976fc0680d4d07873cad7a"
)
_V8_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "60ed5943460b2603cc2e54461807cb49f9ab142083a509a680be95126256ffb3"
)
_V8_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "fe4d2c4978b803d14a22da3b28765a1376e94fedceeccf533541e9a5dae59365"
)
_V9_INPUT_KEYS = _V8_INPUT_KEYS
_V9_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-025",
}
_V9_COUNT_CONTRACT = {
    **_V8_COUNT_CONTRACT,
    "tier_a_rows": 193,
    "total_rows": 108_985,
}
_V9_TIER_A_PROJECTION_SHA256 = (
    "10c2dfb4732f31cc15fc85078e33512ce08d5381343fa614cf9e27a531618900"
)
_V9_OPEN_SEED_MANIFEST_SHA256 = (
    "8ecd11307337c72c6cdfe779b77d97ea51a6e4de9ca3c26f6e076dca18e0ed42"
)
_V9_OPEN_SEED_DATA_SHA256 = (
    "77cefba33066f37b7e94c26ba69f7ad46325b411bdf3ff267ba1e418fd628127"
)
_V9_OPEN_SEED_EVIDENCE_SHA256 = (
    "14fb165903142a73b824a409e9bdf995f07c2316a5588ad5ff4eb8bf4ac5fa71"
)
_V9_FEDERATION_MANIFEST_SHA256 = (
    "ce1d01cc0716c689e1cc3c71cab03d59519da9102072637d8cb867dcdada3f51"
)
_V9_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "193672219b641b5c8cf21092e563bbd1719fc4ee7c72b51007a3960f1b1ea853"
)
_V9_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "868c57f84975d05e81b40ef4f8b7d0a61e797005044f69a66c6f161b0e7693ca"
)
_V9_OPEN_SEED_SOURCE_ROOTS = frozenset(
    {
        "ada_infrastructure_location_pages",
        "ada_infrastructure_press_releases",
        "amazon_data_center_communities",
        "amazon_pennsylvania_innovation_campus_site",
        "applied_digital_sec_filings",
        "aragon_government_news",
        "crusoe_newsroom",
        "edgeconnex_press_releases",
        "environment_agency_permit_application_supporting_document",
        "epoch_ai",
        "google_infrastructure_blog",
        "indiana_idem_air_permit",
        "meta_newsroom",
        "microsoft_official_news",
        "north_carolina_deq_air_permit_public_notice",
        "nzx_company_announcement",
        "related_digital_official_news",
        "richmond_county_economic_development",
        "sunshine_coast_council_investment_news",
    }
)
_V9_OPEN_SEED_PUBLISHERS = frozenset(
    {
        "Ada Infrastructure",
        "Amazon",
        "Amazon Innovation Campuses in Pennsylvania",
        "Applied Digital Corporation",
        "Crusoe",
        "EdgeConneX",
        "Epoch AI",
        "Google",
        "Government of Aragón",
        "Impact Geotechnical Limited",
        "Indiana Department of Environmental Management",
        "Infratil Limited",
        "Meta",
        "Microsoft",
        "North Carolina Department of Environmental Quality",
        "Related Digital",
        "Richmond County, North Carolina",
        "Sunshine Coast Council",
    }
)
_V10_INPUT_KEYS = _V9_INPUT_KEYS
_V10_SATELLITE_BATCH_IDS = {
    "satellite-global-open-v3-active-001",
    "satellite-global-open-v3-proposed-001",
    "satellite-global-open-v3-unknown-030",
}
_V10_COUNT_CONTRACT = {
    **_V9_COUNT_CONTRACT,
    "tier_a_rows": 225,
    "total_rows": 109_017,
}
_V10_TIER_A_PROJECTION_SHA256 = (
    "1ed1fc94fcf31862a9e67625a1f30ee0081bbcfa02d7f0c4020b63bd047d14c5"
)
_V10_OPEN_SEED_MANIFEST_SHA256 = (
    "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7"
)
_V10_OPEN_SEED_DATA_SHA256 = (
    "66e2dc44de00ba6d43c4c25f00f53b974c56e8f673c9302bfc954a06376dddb3"
)
_V10_OPEN_SEED_EVIDENCE_SHA256 = (
    "04da01c144ac92088341846370de351b8ccd9c70c1f619ddc717847d20753da3"
)
_V10_FEDERATION_MANIFEST_SHA256 = (
    "0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48"
)
_V10_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "657216c910e300314f691e1e726a188c24095bd7b4ec000a97d2a4db7e4ff247"
)
_V10_UNKNOWN_CATALOG_MANIFEST_SHA256 = (
    "18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053"
)
_V10_OPEN_SEED_SOURCE_ROOTS = _V9_OPEN_SEED_SOURCE_ROOTS | frozenset(
    {
        "colt_data_centre_construction_timelines",
        "colt_data_centre_location_pages",
        "cyrusone_community_project_pages",
        "cyrusone_press_releases",
        "digital_realty_facility_pages",
        "digital_realty_press_releases",
        "digital_realty_project_pages",
        "finnish_municipal_data_center_updates",
        "gilbane_newsroom",
        "microsoft_local_project_updates",
        "ntt_global_data_center_location_pages",
        "qts_data_center_location_pages",
        "qts_newsroom",
        "stack_infrastructure_press_releases",
    }
)
_V10_OPEN_SEED_PUBLISHERS = _V9_OPEN_SEED_PUBLISHERS | frozenset(
    {
        "City of Espoo",
        "Colt Data Centre Services",
        "CyrusOne",
        "Digital Realty",
        "Gilbane Building Company",
        "Municipality of Vihti",
        "NTT DATA, Inc.",
        "QTS Data Centers",
        "STACK Infrastructure",
    }
)
_V11_INPUT_KEYS = _V10_INPUT_KEYS
_V11_SATELLITE_BATCH_IDS = _V10_SATELLITE_BATCH_IDS
_V11_COUNT_CONTRACT = {
    **_V10_COUNT_CONTRACT,
    "tier_a_rows": 271,
    "total_rows": 109_063,
}
_V11_TIER_A_PROJECTION_SHA256 = (
    "1a181a9b456fb65fc566e7dd029885055fd6071b93cfa81dba002d4435e12346"
)
_V11_OPEN_SEED_MANIFEST_SHA256 = (
    "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456"
)
_V11_OPEN_SEED_DATA_SHA256 = (
    "1ca01797c794e533308bb7c9c01545d94915a4f56b5384db37c65e617efe44b0"
)
_V11_OPEN_SEED_EVIDENCE_SHA256 = (
    "7217ae233f7aa2f55ffd4c612dee42065937ca674d91608efb4621266ab73585"
)
_V11_FEDERATION_MANIFEST_SHA256 = (
    "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5"
)
_V11_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e"
)
_V11_OPEN_SEED_SOURCE_ROOTS = _V10_OPEN_SEED_SOURCE_ROOTS | frozenset(
    {
        "aligned_data_centers_press_releases",
        "clune_press_coverage",
        "colt_dcs_sustainability_reports",
        "cyrusone_data_center_pages",
        "cyrusone_linkedin_company_posts",
        "equinix_newsroom",
        "khazna_data_centers_press_releases",
        "meta_newsroom_data_center_disclosures",
        "new_albany_project_updates",
        "nextdc_asx_results_presentations",
        "oracle_data_center_pages",
        "prime_data_centers_press_releases",
        "princeton_digital_group_newsroom",
        "retelit_press_releases",
        "skanska_cision_press_releases",
        "stt_gdc_facility_factsheets",
        "stt_gdc_newsroom",
        "wisconsin_dnr_environmental_review_pages",
        "xneelo_insights",
        "yondr_group_press_releases",
    }
)
_V11_OPEN_SEED_PUBLISHERS = _V10_OPEN_SEED_PUBLISHERS | frozenset(
    {
        "Aligned Data Centers",
        "City of New Albany, Ohio",
        "Clune Construction",
        "Equinix",
        "Khazna Data Centers",
        "NEXTDC",
        "Oracle",
        "Prime Data Centers",
        "Princeton Digital Group",
        "Retelit",
        "ST Telemedia Global Data Centres",
        "Skanska",
        "Wisconsin Department of Natural Resources",
        "Yondr Group",
        "xneelo",
    }
)
_V11_OPEN_SEED_LICENSES = frozenset(
    {"CC-BY-4.0", "all-rights-reserved", "public-government-record"}
)
_V12_INPUT_KEYS = _V11_INPUT_KEYS
_V12_SATELLITE_BATCH_IDS = _V11_SATELLITE_BATCH_IDS
_V12_COUNT_CONTRACT = {
    **_V11_COUNT_CONTRACT,
    "tier_a_rows": 304,
    "total_rows": 109_096,
}
_V12_TIER_A_PROJECTION_SHA256 = (
    "e68e660e78cfdea7e04ee01baefd1f51f6c3e4e9910d8d57a54e31c121a2cdfd"
)
_V12_OPEN_SEED_MANIFEST_SHA256 = (
    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
)
_V12_OPEN_SEED_DATA_SHA256 = (
    "cc5da1835ea48bafde6aba0b1fb19771885321ebaa955c04177fb15bc494f1fe"
)
_V12_OPEN_SEED_EVIDENCE_SHA256 = (
    "d92ecee64190ae1c1afee0a84f220b06c41f3bf5392e98a9fe225f3db1416e9a"
)
_V12_FEDERATION_MANIFEST_SHA256 = (
    "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2"
)
_V12_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "edf1b0cdf1e842b1ea8a848c1e07d0c5cb0860b34fe267798daeef0158a0ea2c"
)
_V12_OPEN_SEED_SOURCE_ROOTS = _V11_OPEN_SEED_SOURCE_ROOTS | frozenset(
    {
        "airtel_africa_data_centers",
        "atlasedge_press_releases",
        "bitdeer_globenewswire_distributions",
        "dayone_news",
        "elea_press_releases",
        "empyrion_digital_news",
        "equinix_sec_filings",
        "firstcolo_news",
        "independence_mo_monthly_building_permit_reports",
        "maincubes_data_center_factsheets",
        "maincubes_data_center_pages",
        "meeza_news_and_press_releases",
        "nebius_newsroom",
        "pure_dc_news",
        "saudi_press_agency_government_news",
        "sc_zeus_news",
        "takoda_corporate_financing_disclosures",
        "tecto_data_center_pages",
        "tecto_press_releases",
        "telekom_malaysia_news",
        "tokyo_tatemono_news",
        "true_idc_news",
    }
)
_V12_OPEN_SEED_PUBLISHERS = _V11_OPEN_SEED_PUBLISHERS | frozenset(
    {
        "Airtel Africa",
        "AtlasEdge",
        "Bitdeer Technologies Group",
        "City of Independence, Missouri",
        "DayOne Data Centers",
        "Elea Data Centers",
        "Empyrion Digital",
        "Equinix, Inc.",
        "MEEZA",
        "Nebius",
        "Pure DC",
        "SC Zeus Data Centers",
        "Saudi Press Agency",
        "Takoda Data Centers",
        "Tecto Data Centers",
        "Telekom Malaysia",
        "Tokyo Tatemono Co., Ltd.",
        "True IDC",
        "firstcolo",
        "maincubes",
    }
)
_V12_OPEN_SEED_LICENSES = _V11_OPEN_SEED_LICENSES
_V13_INPUT_KEYS = _V12_INPUT_KEYS
_V13_SATELLITE_BATCH_IDS = _V12_SATELLITE_BATCH_IDS
_V13_COUNT_CONTRACT = {
    **_V12_COUNT_CONTRACT,
    "tier_a_rows": 315,
    "total_rows": 109_107,
}
_V13_TIER_A_PROJECTION_SHA256 = (
    "0bdebf32e3df7af34aa1a234c90c1da8c2796ae9efb3b41e50b0bbb01d5b097c"
)
_V13_OPEN_SEED_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)
_V13_OPEN_SEED_DATA_SHA256 = (
    "f6edf9f30977e00d7d3be7ca2b96dadd767f70d58cb15ed6eab5339cea180500"
)
_V13_OPEN_SEED_EVIDENCE_SHA256 = (
    "ebcc3c98700d67dabff1ca6f1747f6cfa48167cfff364b23f9ee05804dfb5c7b"
)
_V13_FEDERATION_MANIFEST_SHA256 = (
    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
)
_V13_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
)
_V13_OPEN_SEED_SOURCE_ROOTS = _V12_OPEN_SEED_SOURCE_ROOTS | frozenset(
    {
        "data4_csr_reports",
        "data4_location_pages",
        "keppel_media",
        "larsen_toubro_press_releases",
        "servpac_press_releases",
        "telehouse_news",
        "uruguay_presidency_news",
        "vietnam_news_agency_vietnamplus",
        "viettel_official_linkedin",
    }
)
_V13_OPEN_SEED_PUBLISHERS = _V12_OPEN_SEED_PUBLISHERS | frozenset(
    {
        "DATA4",
        "Keppel",
        "Larsen & Toubro",
        "Presidencia Uruguay",
        "Servpac",
        "Telehouse",
        "VietnamPlus, Vietnam News Agency",
        "Viettel Group",
    }
)
_V13_OPEN_SEED_LICENSES = _V12_OPEN_SEED_LICENSES
_V14_INPUT_KEYS = _V13_INPUT_KEYS
_V14_SATELLITE_BATCH_IDS = _V13_SATELLITE_BATCH_IDS
_V14_COUNT_CONTRACT = {
    **_V13_COUNT_CONTRACT,
    "tier_a_rows": 319,
    "total_rows": 109_111,
}
_V14_TIER_A_PROJECTION_SHA256 = (
    "159584ad2097da71383831d4fad4983045d8b740106e32a60329b3d1fe650e4d"
)
_V14_OPEN_SEED_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)
_V14_OPEN_SEED_DATA_SHA256 = (
    "6ac090c5120ea4fa547545b31df35d66a3914acf1be3e3223c40da5dfa5dfdfc"
)
_V14_OPEN_SEED_EVIDENCE_SHA256 = (
    "4b10854a6b7069f9022ccea795eefb136e2e9fc272202f110984b151260635c7"
)
_V14_FEDERATION_MANIFEST_SHA256 = (
    "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
)
_V14_COVERAGE_AUDIT_MANIFEST_SHA256 = (
    "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d"
)
_V14_OPEN_SEED_SOURCE_ROOTS = _V13_OPEN_SEED_SOURCE_ROOTS | frozenset(
    {
        "adani_connect_magazine",
        "csc_news_and_blog",
        "esr_newsroom",
        "srv_cision_press_releases",
    }
)
_V14_OPEN_SEED_PUBLISHERS = _V13_OPEN_SEED_PUBLISHERS | frozenset(
    {
        "Adani Group",
        "CSC – IT Center for Science Ltd.",
        "ESR",
        "SRV Group Plc",
    }
)
_V14_OPEN_SEED_LICENSES = _V13_OPEN_SEED_LICENSES

CSV_FIELDS = (
    "row_id",
    "tier",
    "observation_kind",
    "source_artifact_id",
    "source_release_id",
    "source_record_id",
    "source_entity_id",
    "source_artifact_sha256",
    "source_manifest_sha256",
    "source_roots_json",
    "evidence_ids_json",
    "evidence_scope",
    "review_only",
    "entity_kind",
    "name",
    "address",
    "latitude",
    "longitude",
    "country",
    "country_iso_a2",
    "country_iso_a3",
    "coordinate_method",
    "reported_status",
    "reported_status_date",
    "normalized_status",
    "construction_source_supported",
    "construction_verified",
    "construction_verification_status",
    "construction_method",
    "construction_confidence",
    "identity_status",
    "identity_confidence",
    "source_evidence_json",
    "capacity_observations_json",
    "annual_energy_observations_json",
    "pue_observations_json",
    "untyped_capacity_statements_json",
    "operating_model_observation_json",
    "workload_observations_json",
    "satellite_links_json",
    "resolution_advisories_json",
    "fusion_overlay_json",
    "first_evidence_date",
    "last_evidence_date",
    "disposition_label",
    "construction_arithmetic_included",
    "exclusion_reason",
)


class ConstructionMasterError(ValueError):
    """Raised when a definition, pinned input, or output fails closed."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConstructionMasterError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConstructionMasterError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConstructionMasterError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if canonical != value:
        raise ConstructionMasterError(f"{label} must be canonical UTC whole seconds")
    return value


def _json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMasterError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMasterError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionMasterError(f"{label} must be a JSON object")
    return value, raw


def _jsonl_objects(path: Path, label: str) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMasterError(f"{label} must be a regular file")
    values: list[dict[str, Any]] = []
    with path.open("rb") as source:
        for line_number, raw_line in enumerate(source, 1):
            try:
                value = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ConstructionMasterError(
                    f"{label} line {line_number} is invalid"
                ) from error
            if not isinstance(value, dict) or raw_line != _canonical_line(value):
                raise ConstructionMasterError(
                    f"{label} line {line_number} is not canonical object JSON"
                )
            values.append(value)
    return values


def _safe_path(package_root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ConstructionMasterError(f"{label} path must be non-empty text")
    supplied = Path(raw)
    if supplied.is_absolute() or any(part in {"", ".", ".."} for part in supplied.parts):
        raise ConstructionMasterError(f"{label} path must be normalized and relative")
    resolved = (package_root / supplied).resolve()
    root = package_root.resolve()
    if root not in resolved.parents:
        raise ConstructionMasterError(f"{label} path escapes package root")
    return resolved


def _checkpoint_specs(value: Any, label: str = "inputs") -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        if "path" in value:
            if set(value) != {"bytes", "path", "sha256"}:
                raise ConstructionMasterError(f"{label} checkpoint keys differ")
            yield label, value
            return
        for key in sorted(value):
            yield from _checkpoint_specs(value[key], f"{label}.{key}")
    elif isinstance(value, list):
        for index, member in enumerate(value):
            yield from _checkpoint_specs(member, f"{label}[{index}]")


def _is_v2_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V2_MASTER_ID


def _is_v3_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V3_MASTER_ID


def _is_v4_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V4_MASTER_ID


def _is_v5_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V5_MASTER_ID


def _is_v6_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V6_MASTER_ID


def _is_v7_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V7_MASTER_ID


def _is_v8_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V8_MASTER_ID


def _is_v9_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V9_MASTER_ID


def _is_v10_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V10_MASTER_ID


def _is_v11_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V11_MASTER_ID


def _is_v12_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V12_MASTER_ID


def _is_v13_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V13_MASTER_ID


def _is_v14_definition(document: Mapping[str, Any]) -> bool:
    return document.get("master_id") == V14_MASTER_ID


def _validate_v2_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V2_MASTER_ID:
        raise ConstructionMasterError("v2 master identity changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V2_INPUT_KEYS:
        raise ConstructionMasterError("v2 input lanes changed")
    expected = document.get("expected_counts")
    if not isinstance(expected, Mapping):
        raise ConstructionMasterError("v2 expected counts are absent")
    expected_projection = expected.get("tier_a_arithmetic_projection_sha256")
    if (
        {key: expected.get(key) for key in _V2_COUNT_CONTRACT}
        != _V2_COUNT_CONTRACT
        or set(expected)
        != {*_V2_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or not isinstance(expected_projection, str)
        or not _SHA_RE.fullmatch(expected_projection)
    ):
        raise ConstructionMasterError("v2 count or Tier-A parity contract changed")

    ireland = inputs["tier_b_ireland_planning"]
    if not isinstance(ireland, Mapping) or set(ireland) != {
        "artifact_id",
        "assessment",
        "manifest",
        "observations",
        "relationship_suggestions",
        "release_id",
    }:
        raise ConstructionMasterError("Ireland planning input contract changed")
    if (
        ireland.get("artifact_id") != IRELAND_ARTIFACT_ID
        or ireland.get("release_id")
        != "ireland-planning-data-centres-2026-07-18-v1"
    ):
        raise ConstructionMasterError("Ireland planning release identity changed")

    fusion = inputs["candidate_fusion"]
    if not isinstance(fusion, Mapping) or set(fusion) != {
        "artifact_id",
        "data",
        "definition",
        "expected_structural_candidates",
        "manifest",
    }:
        raise ConstructionMasterError("candidate-fusion v8 input contract changed")
    if (
        fusion.get("artifact_id") != "candidate-fusion-osm-planet-priority-v8"
        or fusion.get("expected_structural_candidates") != 102_451
        or not isinstance(fusion.get("definition"), Mapping)
        or not isinstance(fusion.get("manifest"), Mapping)
        or not isinstance(fusion.get("data"), Mapping)
        or "candidate-fusion-2026-07-18-osm-planet-v8.json"
        not in str(fusion["definition"].get("path"))
        or "2026-07-18-osm-planet-priority-v8"
        not in str(fusion["manifest"].get("path"))
        or "2026-07-18-osm-planet-priority-v8"
        not in str(fusion["data"].get("path"))
    ):
        raise ConstructionMasterError("construction master must pin candidate-fusion v8")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v2 satellite batch set changed")
    batch_ids = {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if batch_ids != _V2_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v2 requires active, proposed, and unknown007 batches only"
        )
    for batch in batches:
        artifact_id = str(batch.get("artifact_id"))
        manifest = batch.get("manifest")
        if not isinstance(manifest, Mapping):
            raise ConstructionMasterError("satellite batch manifest is invalid")
        path = str(manifest.get("path"))
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if path_marker not in path:
            raise ConstructionMasterError("satellite batch identity/path mismatch")

    reviews = inputs["analyst_reviews"]
    if not isinstance(reviews, list) or len(reviews) != 21:
        raise ConstructionMasterError("v2 must use exactly 21 analyst reviews")
    queue_ids: set[str] = set()
    for review in reviews:
        if not isinstance(review, Mapping):
            raise ConstructionMasterError("analyst review specification is invalid")
        queue_id = review.get("queue_id")
        batch_id = review.get("batch_artifact_id")
        if (
            not isinstance(queue_id, str)
            or queue_id in queue_ids
            or batch_id not in _V2_SATELLITE_BATCH_IDS
        ):
            raise ConstructionMasterError("analyst reviews are not distinct")
        queue_ids.add(queue_id)
        batch_marker = str(batch_id).removeprefix("satellite-global-open-v3-")
        for checkpoint_name in ("report", "review"):
            checkpoint = review.get(checkpoint_name)
            if not isinstance(checkpoint, Mapping):
                raise ConstructionMasterError(
                    "analyst review checkpoint is invalid"
                )
            path = str(checkpoint.get("path"))
            if batch_marker not in path or re.search(r"unknown-00[1-6]", path):
                raise ConstructionMasterError(
                    "v2 analyst reviews must exclude cumulative unknown001-006"
                )


def _validate_v3_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V3_MASTER_ID:
        raise ConstructionMasterError("v3 master identity changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V3_INPUT_KEYS:
        raise ConstructionMasterError("v3 input lanes changed")
    expected = document.get("expected_counts")
    if not isinstance(expected, Mapping):
        raise ConstructionMasterError("v3 expected counts are absent")
    expected_projection = expected.get("tier_a_arithmetic_projection_sha256")
    if (
        {key: expected.get(key) for key in _V3_COUNT_CONTRACT}
        != _V3_COUNT_CONTRACT
        or set(expected)
        != {*_V3_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or not isinstance(expected_projection, str)
        or not _SHA_RE.fullmatch(expected_projection)
    ):
        raise ConstructionMasterError("v3 count or Tier-A parity contract changed")

    ireland = inputs["tier_b_ireland_planning"]
    if (
        not isinstance(ireland, Mapping)
        or ireland.get("artifact_id") != IRELAND_ARTIFACT_ID
        or ireland.get("release_id")
        != "ireland-planning-data-centres-2026-07-18-v1"
    ):
        raise ConstructionMasterError("v3 Ireland planning release changed")

    england = inputs["tier_b_england_planning"]
    if not isinstance(england, Mapping) or set(england) != {
        "artifact_id",
        "assessment",
        "manifest",
        "observations",
        "phrase_review",
        "release_id",
    }:
        raise ConstructionMasterError("England planning input contract changed")
    if (
        england.get("artifact_id") != ENGLAND_ARTIFACT_ID
        or england.get("release_id") != ENGLAND_ARTIFACT_ID
        or not isinstance(england.get("manifest"), Mapping)
        or england["manifest"].get("sha256") != _V3_ENGLAND_MANIFEST_SHA256
        or "england-planning-data-2026-07-18-v1"
        not in str(england["manifest"].get("path"))
    ):
        raise ConstructionMasterError("England planning release identity changed")

    fusion = inputs["candidate_fusion"]
    if not isinstance(fusion, Mapping) or set(fusion) != {
        "artifact_id",
        "data",
        "definition",
        "expected_structural_candidates",
        "manifest",
    }:
        raise ConstructionMasterError("candidate-fusion v9 input contract changed")
    if (
        fusion.get("artifact_id") != "candidate-fusion-osm-planet-priority-v9"
        or fusion.get("expected_structural_candidates") != 102_451
        or not isinstance(fusion.get("definition"), Mapping)
        or fusion["definition"].get("sha256")
        != _V3_FUSION_DEFINITION_SHA256
        or not isinstance(fusion.get("manifest"), Mapping)
        or fusion["manifest"].get("sha256") != _V3_FUSION_MANIFEST_SHA256
        or not isinstance(fusion.get("data"), Mapping)
        or "candidate-fusion-2026-07-18-osm-planet-v9.json"
        not in str(fusion["definition"].get("path"))
        or "2026-07-18-osm-planet-priority-v9"
        not in str(fusion["manifest"].get("path"))
        or "2026-07-18-osm-planet-priority-v9"
        not in str(fusion["data"].get("path"))
    ):
        raise ConstructionMasterError("construction master must pin candidate-fusion v9")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v3 satellite batch set changed")
    batch_ids = {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if batch_ids != _V3_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v3 requires active, proposed, and unknown009 batches only"
        )
    for batch in batches:
        artifact_id = str(batch.get("artifact_id"))
        manifest = batch.get("manifest")
        if not isinstance(manifest, Mapping):
            raise ConstructionMasterError("v3 satellite manifest is invalid")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if path_marker not in str(manifest.get("path")):
            raise ConstructionMasterError("v3 satellite identity/path mismatch")

    if inputs.get("analyst_reviews") != _V3_ANALYST_REVIEW_CONTRACT:
        raise ConstructionMasterError(
            "v3 analyst reviews must derive exactly from candidate-fusion v9"
        )


def _validate_v4_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V4_MASTER_ID:
        raise ConstructionMasterError("v4 master identity changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V4_INPUT_KEYS:
        raise ConstructionMasterError("v4 input lanes changed")
    expected = document.get("expected_counts")
    if not isinstance(expected, Mapping):
        raise ConstructionMasterError("v4 expected counts are absent")
    expected_projection = expected.get("tier_a_arithmetic_projection_sha256")
    if (
        {key: expected.get(key) for key in _V4_COUNT_CONTRACT}
        != _V4_COUNT_CONTRACT
        or set(expected)
        != {*_V4_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected_projection
        != "5ff330359d276f2cee6e0f603321d390395564827900d16a9e1a9df2d59abe13"
    ):
        raise ConstructionMasterError("v4 count or Tier-A parity contract changed")

    ireland = inputs["tier_b_ireland_planning"]
    if (
        not isinstance(ireland, Mapping)
        or ireland.get("artifact_id") != IRELAND_ARTIFACT_ID
        or ireland.get("release_id")
        != "ireland-planning-data-centres-2026-07-18-v1"
    ):
        raise ConstructionMasterError("v4 Ireland planning release changed")

    england = inputs["tier_b_england_planning"]
    if (
        not isinstance(england, Mapping)
        or set(england)
        != {
            "artifact_id",
            "assessment",
            "manifest",
            "observations",
            "phrase_review",
            "release_id",
        }
        or england.get("artifact_id") != ENGLAND_ARTIFACT_ID
        or england.get("release_id") != ENGLAND_ARTIFACT_ID
        or not isinstance(england.get("manifest"), Mapping)
        or england["manifest"].get("sha256") != _V3_ENGLAND_MANIFEST_SHA256
    ):
        raise ConstructionMasterError("v4 England planning release changed")

    lane_contracts = {
        "tier_b_nsw_major_projects": (
            NSW_ARTIFACT_ID,
            _V4_NSW_MANIFEST_SHA256,
        ),
        "tier_b_netherlands_koop": (
            NETHERLANDS_ARTIFACT_ID,
            _V4_NETHERLANDS_MANIFEST_SHA256,
        ),
        "tier_b_new_zealand_fast_track": (
            NEW_ZEALAND_ARTIFACT_ID,
            _V4_NEW_ZEALAND_MANIFEST_SHA256,
        ),
    }
    for key, (artifact_id, manifest_sha256) in lane_contracts.items():
        lane = inputs[key]
        if (
            not isinstance(lane, Mapping)
            or set(lane)
            != {
                "artifact_id",
                "assessment",
                "manifest",
                "observations",
                "release_id",
            }
            or lane.get("artifact_id") != artifact_id
            or lane.get("release_id") != artifact_id
            or not isinstance(lane.get("manifest"), Mapping)
            or lane["manifest"].get("sha256") != manifest_sha256
            or artifact_id not in str(lane["manifest"].get("path"))
        ):
            raise ConstructionMasterError(f"v4 {key} release changed")

    fusion = inputs["candidate_fusion"]
    if (
        not isinstance(fusion, Mapping)
        or set(fusion)
        != {
            "artifact_id",
            "data",
            "definition",
            "expected_structural_candidates",
            "manifest",
        }
        or fusion.get("artifact_id")
        != "candidate-fusion-osm-planet-priority-v10"
        or fusion.get("expected_structural_candidates") != 102_451
        or not isinstance(fusion.get("definition"), Mapping)
        or fusion["definition"].get("sha256")
        != _V4_FUSION_DEFINITION_SHA256
        or not isinstance(fusion.get("manifest"), Mapping)
        or fusion["manifest"].get("sha256") != _V4_FUSION_MANIFEST_SHA256
        or not isinstance(fusion.get("data"), Mapping)
        or fusion["data"].get("sha256") != _V4_FUSION_DATA_SHA256
        or "candidate-fusion-2026-07-18-osm-planet-v10.json"
        not in str(fusion["definition"].get("path"))
        or "2026-07-18-osm-planet-priority-v10"
        not in str(fusion["manifest"].get("path"))
        or "2026-07-18-osm-planet-priority-v10"
        not in str(fusion["data"].get("path"))
    ):
        raise ConstructionMasterError("construction master must pin candidate-fusion v10")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v4 satellite batch set changed")
    batch_ids = {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if batch_ids != _V4_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v4 requires active, proposed, and cumulative unknown011 batches"
        )
    expected_batch_hashes = {
        "satellite-global-open-v3-active-001": (
            _V4_FUSION_BATCH_PINS[
                "satellite_review_runs/2026-07-18-global-open-v3-active-001"
            ]
        ),
        "satellite-global-open-v3-proposed-001": (
            _V4_FUSION_BATCH_PINS[
                "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
            ]
        ),
        "satellite-global-open-v3-unknown-011": (
            _V4_UNKNOWN_CATALOG_MANIFEST_SHA256
        ),
    }
    for batch in batches:
        if not isinstance(batch, Mapping) or set(batch) != {
            "artifact_id",
            "manifest",
        }:
            raise ConstructionMasterError("v4 satellite batch specification changed")
        artifact_id = str(batch["artifact_id"])
        manifest = batch.get("manifest")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("sha256") != expected_batch_hashes.get(artifact_id)
            or path_marker not in str(manifest.get("path"))
        ):
            raise ConstructionMasterError("v4 satellite identity or hash changed")

    if inputs.get("analyst_reviews") != _V4_ANALYST_REVIEW_CONTRACT:
        raise ConstructionMasterError(
            "v4 analyst reviews must derive exactly from candidate-fusion v10"
        )


def _validate_v5_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V5_MASTER_ID:
        raise ConstructionMasterError("v5 master identity changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V5_INPUT_KEYS:
        raise ConstructionMasterError("v5 input lanes changed")
    expected = document.get("expected_counts")
    if not isinstance(expected, Mapping):
        raise ConstructionMasterError("v5 expected counts are absent")
    expected_projection = expected.get("tier_a_arithmetic_projection_sha256")
    if (
        {key: expected.get(key) for key in _V5_COUNT_CONTRACT}
        != _V5_COUNT_CONTRACT
        or set(expected)
        != {*_V5_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected_projection
        != "5ff330359d276f2cee6e0f603321d390395564827900d16a9e1a9df2d59abe13"
    ):
        raise ConstructionMasterError("v5 count or Tier-A parity contract changed")

    ireland = inputs["tier_b_ireland_planning"]
    if (
        not isinstance(ireland, Mapping)
        or ireland.get("artifact_id") != IRELAND_ARTIFACT_ID
        or ireland.get("release_id")
        != "ireland-planning-data-centres-2026-07-18-v1"
    ):
        raise ConstructionMasterError("v5 Ireland planning release changed")

    england = inputs["tier_b_england_planning"]
    if (
        not isinstance(england, Mapping)
        or set(england)
        != {
            "artifact_id",
            "assessment",
            "manifest",
            "observations",
            "phrase_review",
            "release_id",
        }
        or england.get("artifact_id") != ENGLAND_ARTIFACT_ID
        or england.get("release_id") != ENGLAND_ARTIFACT_ID
        or not isinstance(england.get("manifest"), Mapping)
        or england["manifest"].get("sha256") != _V3_ENGLAND_MANIFEST_SHA256
    ):
        raise ConstructionMasterError("v5 England planning release changed")

    lane_contracts = {
        "tier_b_nsw_major_projects": (
            NSW_ARTIFACT_ID,
            _V4_NSW_MANIFEST_SHA256,
        ),
        "tier_b_netherlands_koop": (
            NETHERLANDS_ARTIFACT_ID,
            _V4_NETHERLANDS_MANIFEST_SHA256,
        ),
        "tier_b_new_zealand_fast_track": (
            NEW_ZEALAND_ARTIFACT_ID,
            _V4_NEW_ZEALAND_MANIFEST_SHA256,
        ),
    }
    for key, (artifact_id, manifest_sha256) in lane_contracts.items():
        lane = inputs[key]
        if (
            not isinstance(lane, Mapping)
            or set(lane)
            != {
                "artifact_id",
                "assessment",
                "manifest",
                "observations",
                "release_id",
            }
            or lane.get("artifact_id") != artifact_id
            or lane.get("release_id") != artifact_id
            or not isinstance(lane.get("manifest"), Mapping)
            or lane["manifest"].get("sha256") != manifest_sha256
            or artifact_id not in str(lane["manifest"].get("path"))
        ):
            raise ConstructionMasterError(f"v5 {key} release changed")

    france = inputs["tier_b_france_igedd"]
    france_checkpoints = {
        "assessment": _V5_FRANCE_ASSESSMENT_SHA256,
        "definition": _V5_FRANCE_DEFINITION_SHA256,
        "manifest": _V5_FRANCE_MANIFEST_SHA256,
        "observations": _V5_FRANCE_OBSERVATIONS_SHA256,
        "schema": _V5_FRANCE_SCHEMA_SHA256,
    }
    if (
        not isinstance(france, Mapping)
        or set(france)
        != {
            "artifact_id",
            "assessment",
            "definition",
            "manifest",
            "observations",
            "release_id",
            "schema",
        }
        or france.get("artifact_id") != FRANCE_ARTIFACT_ID
        or france.get("release_id") != FRANCE_ARTIFACT_ID
        or any(
            not isinstance(france.get(name), Mapping)
            or france[name].get("sha256") != digest
            or FRANCE_ARTIFACT_ID not in str(france[name].get("path"))
            for name, digest in france_checkpoints.items()
        )
    ):
        raise ConstructionMasterError("v5 France IGEDD release changed")

    fusion = inputs["candidate_fusion"]
    if (
        not isinstance(fusion, Mapping)
        or set(fusion)
        != {
            "artifact_id",
            "data",
            "definition",
            "expected_structural_candidates",
            "manifest",
        }
        or fusion.get("artifact_id")
        != "candidate-fusion-osm-planet-priority-v13"
        or fusion.get("expected_structural_candidates") != 102_451
        or not isinstance(fusion.get("definition"), Mapping)
        or fusion["definition"].get("sha256")
        != _V5_FUSION_DEFINITION_SHA256
        or not isinstance(fusion.get("manifest"), Mapping)
        or fusion["manifest"].get("sha256") != _V5_FUSION_MANIFEST_SHA256
        or not isinstance(fusion.get("data"), Mapping)
        or fusion["data"].get("sha256") != _V5_FUSION_DATA_SHA256
        or "candidate-fusion-2026-07-18-osm-planet-v13.json"
        not in str(fusion["definition"].get("path"))
        or "2026-07-18-osm-planet-priority-v13"
        not in str(fusion["manifest"].get("path"))
        or "2026-07-18-osm-planet-priority-v13"
        not in str(fusion["data"].get("path"))
    ):
        raise ConstructionMasterError("construction master must pin candidate-fusion v13")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v5 satellite batch set changed")
    batch_ids = {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if batch_ids != _V5_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v5 requires active, proposed, and cumulative unknown015 batches"
        )
    expected_batch_hashes = {
        "satellite-global-open-v3-active-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-active-001"
        ],
        "satellite-global-open-v3-proposed-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
        ],
        "satellite-global-open-v3-unknown-015": (
            _V5_UNKNOWN_CATALOG_MANIFEST_SHA256
        ),
    }
    for batch in batches:
        if not isinstance(batch, Mapping) or set(batch) != {
            "artifact_id",
            "manifest",
        }:
            raise ConstructionMasterError("v5 satellite batch specification changed")
        artifact_id = str(batch["artifact_id"])
        manifest = batch.get("manifest")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("sha256") != expected_batch_hashes.get(artifact_id)
            or path_marker not in str(manifest.get("path"))
        ):
            raise ConstructionMasterError("v5 satellite identity or hash changed")

    if inputs.get("analyst_reviews") != _V5_ANALYST_REVIEW_CONTRACT:
        raise ConstructionMasterError(
            "v5 analyst reviews must derive exactly from candidate-fusion v13"
        )
    forbidden_fragments = (
        "brazil",
        "chile-sea",
        "epbc-public",
        "germany-uvp",
        "iaac-data",
        "italy-mase",
        "spain-boe",
    )
    serialized = _compact(inputs).lower()
    if any(fragment in serialized for fragment in forbidden_fragments):
        raise ConstructionMasterError("v5 includes an excluded source lane")


def _validate_v6_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V6_MASTER_ID:
        raise ConstructionMasterError("v6 master identity changed")
    if document.get("generated_at") != "2026-07-19T12:30:00Z":
        raise ConstructionMasterError("v6 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V6_INPUT_KEYS:
        raise ConstructionMasterError("v6 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V6_COUNT_CONTRACT}
        != _V6_COUNT_CONTRACT
        or set(expected)
        != {*_V6_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V6_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v6 count or Tier-A projection contract changed")

    # Reuse the complete v5 validation of every unchanged official/review lane
    # and the frozen candidate-fusion v13 lineage. The synthetic current-catalog
    # entry is checked only by that inherited contract; the real v6 Unknown020
    # checkpoint is validated below and by the generic checkpoint closure.
    inherited_inputs = dict(inputs)
    inherited_inputs["satellite_batches"] = [
        batch
        for batch in inputs["satellite_batches"]
        if isinstance(batch, Mapping)
        and batch.get("artifact_id")
        in {
            "satellite-global-open-v3-active-001",
            "satellite-global-open-v3-proposed-001",
        }
    ] + [
        {
            "artifact_id": "satellite-global-open-v3-unknown-015",
            "manifest": {
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-unknown-015/batch-manifest.json"
                ),
                "sha256": _V5_UNKNOWN_CATALOG_MANIFEST_SHA256,
            },
        }
    ]
    _validate_v5_definition_contract(
        {
            "expected_counts": {
                **_V5_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    "5ff330359d276f2cee6e0f603321d390395564827900d16a9e1a9df2d59abe13"
                ),
            },
            "inputs": inherited_inputs,
            "master_id": V5_MASTER_ID,
        }
    )

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v6 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v2",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v6 Tier-A release identities changed")
    open_seed = tier_a_by_artifact["epoch-official-open-seed-v2"]
    if (
        set(open_seed) != {
            "artifact_id",
            "data",
            "evidence",
            "manifest",
            "release_id",
        }
        or open_seed.get("release_id") != "epoch-official-open-seed-v2"
        or not isinstance(open_seed.get("data"), Mapping)
        or open_seed["data"].get("sha256") != _V6_OPEN_SEED_DATA_SHA256
        or open_seed["data"].get("path")
        != "releases/2026-07-19-open-seed-v2/construction_pipeline.csv"
        or not isinstance(open_seed.get("evidence"), Mapping)
        or open_seed["evidence"].get("sha256")
        != _V6_OPEN_SEED_EVIDENCE_SHA256
        or open_seed["evidence"].get("path")
        != "releases/2026-07-19-open-seed-v2/evidence.csv"
        or not isinstance(open_seed.get("manifest"), Mapping)
        or open_seed["manifest"].get("sha256")
        != _V6_OPEN_SEED_MANIFEST_SHA256
        or open_seed["manifest"].get("path")
        != "releases/2026-07-19-open-seed-v2/manifest.json"
    ):
        raise ConstructionMasterError("v6 open-seed v2 checkpoints changed")
    global_open = tier_a_by_artifact["global-open-v3"]
    if (
        set(global_open) != {
            "artifact_id",
            "data",
            "evidence",
            "manifest",
            "release_id",
        }
        or global_open.get("release_id") != "global-open-v3"
        or not isinstance(global_open.get("data"), Mapping)
        or global_open["data"].get("sha256") != _V6_GLOBAL_OPEN_DATA_SHA256
        or global_open["data"].get("path")
        != "releases/2026-07-18-global-open-v3/construction_pipeline.csv"
        or not isinstance(global_open.get("evidence"), Mapping)
        or global_open["evidence"].get("sha256")
        != _V6_GLOBAL_OPEN_EVIDENCE_SHA256
        or global_open["evidence"].get("path")
        != "releases/2026-07-18-global-open-v3/evidence.csv"
        or not isinstance(global_open.get("manifest"), Mapping)
        or global_open["manifest"].get("sha256")
        != _V6_GLOBAL_OPEN_MANIFEST_SHA256
        or global_open["manifest"].get("path")
        != "releases/2026-07-18-global-open-v3/manifest.json"
    ):
        raise ConstructionMasterError("v6 global-open v3 checkpoint changed")

    coverage_context = inputs["coverage_context"]
    if (
        not isinstance(coverage_context, Mapping)
        or set(coverage_context) != {"audit_manifest", "federation_manifest"}
        or not isinstance(coverage_context.get("audit_manifest"), Mapping)
        or coverage_context["audit_manifest"].get("sha256")
        != _V6_COVERAGE_AUDIT_MANIFEST_SHA256
        or coverage_context["audit_manifest"].get("path")
        != "audits/2026-07-19-public-open-coverage-v2/manifest.json"
        or not isinstance(coverage_context.get("federation_manifest"), Mapping)
        or coverage_context["federation_manifest"].get("sha256")
        != _V6_FEDERATION_MANIFEST_SHA256
        or coverage_context["federation_manifest"].get("path")
        != "federated_indexes/2026-07-19-public-open-v2/manifest.json"
    ):
        raise ConstructionMasterError("v6 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v6 satellite batch set changed")
    batch_by_id = {
        batch.get("artifact_id"): batch
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if set(batch_by_id) != _V6_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v6 requires active, proposed, and cumulative Unknown020 batches"
        )
    expected_batch_hashes = {
        "satellite-global-open-v3-active-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-active-001"
        ],
        "satellite-global-open-v3-proposed-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
        ],
        "satellite-global-open-v3-unknown-020": (
            _V6_UNKNOWN_CATALOG_MANIFEST_SHA256
        ),
    }
    for artifact_id, batch in batch_by_id.items():
        manifest = batch.get("manifest")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if (
            set(batch) != {"artifact_id", "manifest"}
            or not isinstance(manifest, Mapping)
            or manifest.get("sha256") != expected_batch_hashes[artifact_id]
            or path_marker not in str(manifest.get("path"))
        ):
            raise ConstructionMasterError("v6 satellite identity or hash changed")


def _validate_v7_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V7_MASTER_ID:
        raise ConstructionMasterError("v7 master identity changed")
    if document.get("generated_at") != "2026-07-19T13:00:00Z":
        raise ConstructionMasterError("v7 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V7_INPUT_KEYS:
        raise ConstructionMasterError("v7 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V7_COUNT_CONTRACT}
        != _V7_COUNT_CONTRACT
        or set(expected)
        != {*_V7_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V7_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v7 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v7 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v4",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v7 Tier-A release identities changed")

    # Validate every unchanged lane against v6 by substituting only its exact
    # former open-seed checkpoint. This makes the v7 delta mechanically narrow:
    # no current catalog, review lineage, review lane, or global-open drift.
    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v2",
            "data": {
                "bytes": 177920,
                "path": "releases/2026-07-19-open-seed-v2/construction_pipeline.csv",
                "sha256": _V6_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 25032,
                "path": "releases/2026-07-19-open-seed-v2/evidence.csv",
                "sha256": _V6_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 2263,
                "path": "releases/2026-07-19-open-seed-v2/manifest.json",
                "sha256": _V6_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v2",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    _validate_v6_definition_contract(
        {
            "expected_counts": {
                **_V6_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V6_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T12:30:00Z",
            "inputs": inherited_inputs,
            "master_id": V6_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v4"]
    if (
        set(open_seed)
        != {"artifact_id", "data", "evidence", "manifest", "release_id"}
        or open_seed.get("release_id") != "epoch-official-open-seed-v4"
        or not isinstance(open_seed.get("data"), Mapping)
        or open_seed["data"].get("sha256") != _V7_OPEN_SEED_DATA_SHA256
        or open_seed["data"].get("path")
        != "releases/2026-07-19-open-seed-v4/construction_pipeline.csv"
        or not isinstance(open_seed.get("evidence"), Mapping)
        or open_seed["evidence"].get("sha256")
        != _V7_OPEN_SEED_EVIDENCE_SHA256
        or open_seed["evidence"].get("path")
        != "releases/2026-07-19-open-seed-v4/evidence.csv"
        or not isinstance(open_seed.get("manifest"), Mapping)
        or open_seed["manifest"].get("sha256")
        != _V7_OPEN_SEED_MANIFEST_SHA256
        or open_seed["manifest"].get("path")
        != "releases/2026-07-19-open-seed-v4/manifest.json"
    ):
        raise ConstructionMasterError("v7 open-seed v4 checkpoints changed")


def _validate_v8_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V8_MASTER_ID:
        raise ConstructionMasterError("v8 master identity changed")
    if document.get("generated_at") != "2026-07-19T13:35:00Z":
        raise ConstructionMasterError("v8 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V8_INPUT_KEYS:
        raise ConstructionMasterError("v8 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V8_COUNT_CONTRACT}
        != _V8_COUNT_CONTRACT
        or set(expected)
        != {*_V8_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V8_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v8 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v8 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v5",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v8 Tier-A release identities changed")

    # Mechanically validate every lane inherited from v7 by substituting the
    # exact former open seed, contextual manifests, and cumulative catalog.
    # Candidate-fusion v13 still resolves reviews from its own pinned
    # Unknown010/013/015 batches; Unknown022 is catalog context only.
    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v4",
            "data": {
                "bytes": 183652,
                "path": "releases/2026-07-19-open-seed-v4/construction_pipeline.csv",
                "sha256": _V7_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 26970,
                "path": "releases/2026-07-19-open-seed-v4/evidence.csv",
                "sha256": _V7_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 2299,
                "path": "releases/2026-07-19-open-seed-v4/manifest.json",
                "sha256": _V7_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v4",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2235,
            "path": "audits/2026-07-19-public-open-coverage-v2/manifest.json",
            "sha256": _V6_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v2/manifest.json",
            "sha256": _V6_FEDERATION_MANIFEST_SHA256,
        },
    }
    inherited_inputs["satellite_batches"] = [
        batch
        for batch in inputs["satellite_batches"]
        if isinstance(batch, Mapping)
        and batch.get("artifact_id")
        in {
            "satellite-global-open-v3-active-001",
            "satellite-global-open-v3-proposed-001",
        }
    ] + [
        {
            "artifact_id": "satellite-global-open-v3-unknown-020",
            "manifest": {
                "bytes": 4651907,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-unknown-020/batch-manifest.json"
                ),
                "sha256": _V6_UNKNOWN_CATALOG_MANIFEST_SHA256,
            },
        }
    ]
    _validate_v7_definition_contract(
        {
            "expected_counts": {
                **_V7_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V7_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T13:00:00Z",
            "inputs": inherited_inputs,
            "master_id": V7_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v5"]
    if (
        set(open_seed)
        != {"artifact_id", "data", "evidence", "manifest", "release_id"}
        or open_seed.get("release_id") != "epoch-official-open-seed-v5"
        or not isinstance(open_seed.get("data"), Mapping)
        or open_seed["data"].get("sha256") != _V8_OPEN_SEED_DATA_SHA256
        or open_seed["data"].get("path")
        != "releases/2026-07-19-open-seed-v5/construction_pipeline.csv"
        or not isinstance(open_seed.get("evidence"), Mapping)
        or open_seed["evidence"].get("sha256")
        != _V8_OPEN_SEED_EVIDENCE_SHA256
        or open_seed["evidence"].get("path")
        != "releases/2026-07-19-open-seed-v5/evidence.csv"
        or not isinstance(open_seed.get("manifest"), Mapping)
        or open_seed["manifest"].get("sha256")
        != _V8_OPEN_SEED_MANIFEST_SHA256
        or open_seed["manifest"].get("path")
        != "releases/2026-07-19-open-seed-v5/manifest.json"
    ):
        raise ConstructionMasterError("v8 open-seed v5 checkpoints changed")

    coverage_context = inputs["coverage_context"]
    if (
        not isinstance(coverage_context, Mapping)
        or set(coverage_context) != {"audit_manifest", "federation_manifest"}
        or not isinstance(coverage_context.get("audit_manifest"), Mapping)
        or coverage_context["audit_manifest"].get("sha256")
        != _V8_COVERAGE_AUDIT_MANIFEST_SHA256
        or coverage_context["audit_manifest"].get("path")
        != "audits/2026-07-19-public-open-coverage-v5/manifest.json"
        or not isinstance(coverage_context.get("federation_manifest"), Mapping)
        or coverage_context["federation_manifest"].get("sha256")
        != _V8_FEDERATION_MANIFEST_SHA256
        or coverage_context["federation_manifest"].get("path")
        != "federated_indexes/2026-07-19-public-open-v5/manifest.json"
    ):
        raise ConstructionMasterError("v8 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v8 satellite batch set changed")
    batch_by_id = {
        batch.get("artifact_id"): batch
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if set(batch_by_id) != _V8_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v8 requires active, proposed, and cumulative Unknown022 batches"
        )
    expected_batch_hashes = {
        "satellite-global-open-v3-active-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-active-001"
        ],
        "satellite-global-open-v3-proposed-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
        ],
        "satellite-global-open-v3-unknown-022": (
            _V8_UNKNOWN_CATALOG_MANIFEST_SHA256
        ),
    }
    for artifact_id, batch in batch_by_id.items():
        manifest = batch.get("manifest")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if (
            set(batch) != {"artifact_id", "manifest"}
            or not isinstance(manifest, Mapping)
            or manifest.get("sha256") != expected_batch_hashes[artifact_id]
            or path_marker not in str(manifest.get("path"))
        ):
            raise ConstructionMasterError("v8 satellite identity or hash changed")


def _validate_v9_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V9_MASTER_ID:
        raise ConstructionMasterError("v9 master identity changed")
    if document.get("generated_at") != "2026-07-19T15:10:00Z":
        raise ConstructionMasterError("v9 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V9_INPUT_KEYS:
        raise ConstructionMasterError("v9 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V9_COUNT_CONTRACT}
        != _V9_COUNT_CONTRACT
        or set(expected)
        != {*_V9_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V9_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v9 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v9 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v9",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v9 Tier-A release identities changed")

    # Revalidate every inherited lane through the complete v8 contract. The
    # v9 delta is limited to the current seed, contextual manifests, and the
    # cumulative catalog checkpoint; historical review evidence stays pinned.
    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v5",
            "data": {
                "bytes": 185574,
                "path": "releases/2026-07-19-open-seed-v5/construction_pipeline.csv",
                "sha256": _V8_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 27841,
                "path": "releases/2026-07-19-open-seed-v5/evidence.csv",
                "sha256": _V8_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 2335,
                "path": "releases/2026-07-19-open-seed-v5/manifest.json",
                "sha256": _V8_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v5",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2235,
            "path": "audits/2026-07-19-public-open-coverage-v5/manifest.json",
            "sha256": _V8_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v5/manifest.json",
            "sha256": _V8_FEDERATION_MANIFEST_SHA256,
        },
    }
    inherited_inputs["satellite_batches"] = [
        batch
        for batch in inputs["satellite_batches"]
        if isinstance(batch, Mapping)
        and batch.get("artifact_id")
        in {
            "satellite-global-open-v3-active-001",
            "satellite-global-open-v3-proposed-001",
        }
    ] + [
        {
            "artifact_id": "satellite-global-open-v3-unknown-022",
            "manifest": {
                "bytes": 5001151,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-unknown-022/batch-manifest.json"
                ),
                "sha256": _V8_UNKNOWN_CATALOG_MANIFEST_SHA256,
            },
        }
    ]
    _validate_v8_definition_contract(
        {
            "expected_counts": {
                **_V8_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V8_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T13:35:00Z",
            "inputs": inherited_inputs,
            "master_id": V8_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v9"]
    if (
        set(open_seed)
        != {"artifact_id", "data", "evidence", "manifest", "release_id"}
        or open_seed.get("release_id") != "epoch-official-open-seed-v9"
        or not isinstance(open_seed.get("data"), Mapping)
        or open_seed["data"].get("sha256") != _V9_OPEN_SEED_DATA_SHA256
        or open_seed["data"].get("path")
        != "releases/2026-07-19-open-seed-v9/construction_pipeline.csv"
        or not isinstance(open_seed.get("evidence"), Mapping)
        or open_seed["evidence"].get("sha256")
        != _V9_OPEN_SEED_EVIDENCE_SHA256
        or open_seed["evidence"].get("path")
        != "releases/2026-07-19-open-seed-v9/evidence.csv"
        or not isinstance(open_seed.get("manifest"), Mapping)
        or open_seed["manifest"].get("sha256")
        != _V9_OPEN_SEED_MANIFEST_SHA256
        or open_seed["manifest"].get("path")
        != "releases/2026-07-19-open-seed-v9/manifest.json"
    ):
        raise ConstructionMasterError("v9 open-seed v9 checkpoints changed")

    coverage_context = inputs["coverage_context"]
    if (
        not isinstance(coverage_context, Mapping)
        or set(coverage_context) != {"audit_manifest", "federation_manifest"}
        or not isinstance(coverage_context.get("audit_manifest"), Mapping)
        or coverage_context["audit_manifest"].get("sha256")
        != _V9_COVERAGE_AUDIT_MANIFEST_SHA256
        or coverage_context["audit_manifest"].get("path")
        != "audits/2026-07-19-public-open-coverage-v8/manifest.json"
        or not isinstance(coverage_context.get("federation_manifest"), Mapping)
        or coverage_context["federation_manifest"].get("sha256")
        != _V9_FEDERATION_MANIFEST_SHA256
        or coverage_context["federation_manifest"].get("path")
        != "federated_indexes/2026-07-19-public-open-v7/manifest.json"
    ):
        raise ConstructionMasterError("v9 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v9 satellite batch set changed")
    batch_by_id = {
        batch.get("artifact_id"): batch
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if set(batch_by_id) != _V9_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v9 requires active, proposed, and cumulative Unknown025 batches"
        )
    expected_batch_hashes = {
        "satellite-global-open-v3-active-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-active-001"
        ],
        "satellite-global-open-v3-proposed-001": _V5_FUSION_BATCH_PINS[
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
        ],
        "satellite-global-open-v3-unknown-025": (
            _V9_UNKNOWN_CATALOG_MANIFEST_SHA256
        ),
    }
    for artifact_id, batch in batch_by_id.items():
        manifest = batch.get("manifest")
        path_marker = "2026-07-18-" + artifact_id.removeprefix("satellite-")
        if (
            set(batch) != {"artifact_id", "manifest"}
            or not isinstance(manifest, Mapping)
            or manifest.get("sha256") != expected_batch_hashes[artifact_id]
            or path_marker not in str(manifest.get("path"))
        ):
            raise ConstructionMasterError("v9 satellite identity or hash changed")


def _validate_v10_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V10_MASTER_ID:
        raise ConstructionMasterError("v10 master identity changed")
    if document.get("generated_at") != "2026-07-19T18:30:00Z":
        raise ConstructionMasterError("v10 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V10_INPUT_KEYS:
        raise ConstructionMasterError("v10 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V10_COUNT_CONTRACT}
        != _V10_COUNT_CONTRACT
        or set(expected)
        != {*_V10_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V10_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v10 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v10 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v13",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v10 Tier-A release identities changed")

    # Revalidate all inherited lanes through v9. V10 substitutes only the
    # current seed, contextual manifests, and cumulative satellite catalog;
    # candidate-fusion and its historical analyst-review evidence stay frozen.
    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v9",
            "data": {
                "bytes": 202657,
                "path": "releases/2026-07-19-open-seed-v9/construction_pipeline.csv",
                "sha256": _V9_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 34545,
                "path": "releases/2026-07-19-open-seed-v9/evidence.csv",
                "sha256": _V9_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 2872,
                "path": "releases/2026-07-19-open-seed-v9/manifest.json",
                "sha256": _V9_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v9",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2235,
            "path": "audits/2026-07-19-public-open-coverage-v8/manifest.json",
            "sha256": _V9_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v7/manifest.json",
            "sha256": _V9_FEDERATION_MANIFEST_SHA256,
        },
    }
    inherited_inputs["satellite_batches"] = [
        batch
        for batch in inputs["satellite_batches"]
        if isinstance(batch, Mapping)
        and batch.get("artifact_id")
        in {
            "satellite-global-open-v3-active-001",
            "satellite-global-open-v3-proposed-001",
        }
    ] + [
        {
            "artifact_id": "satellite-global-open-v3-unknown-025",
            "manifest": {
                "bytes": 5550029,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-unknown-025/batch-manifest.json"
                ),
                "sha256": _V9_UNKNOWN_CATALOG_MANIFEST_SHA256,
            },
        }
    ]
    _validate_v9_definition_contract(
        {
            "expected_counts": {
                **_V9_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V9_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T15:10:00Z",
            "inputs": inherited_inputs,
            "master_id": V9_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v13"]
    if open_seed != {
        "artifact_id": "epoch-official-open-seed-v13",
        "data": {
            "bytes": 228437,
            "path": "releases/2026-07-19-open-seed-v13/construction_pipeline.csv",
            "sha256": _V10_OPEN_SEED_DATA_SHA256,
        },
        "evidence": {
            "bytes": 49544,
            "path": "releases/2026-07-19-open-seed-v13/evidence.csv",
            "sha256": _V10_OPEN_SEED_EVIDENCE_SHA256,
        },
        "manifest": {
            "bytes": 3477,
            "path": "releases/2026-07-19-open-seed-v13/manifest.json",
            "sha256": _V10_OPEN_SEED_MANIFEST_SHA256,
        },
        "release_id": "epoch-official-open-seed-v13",
    }:
        raise ConstructionMasterError("v10 open-seed v13 checkpoints changed")

    if inputs["coverage_context"] != {
        "audit_manifest": {
            "bytes": 2237,
            "path": "audits/2026-07-19-public-open-coverage-v9/manifest.json",
            "sha256": _V10_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v8/manifest.json",
            "sha256": _V10_FEDERATION_MANIFEST_SHA256,
        },
    }:
        raise ConstructionMasterError("v10 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v10 satellite batch set changed")
    batch_by_id = {
        batch.get("artifact_id"): batch
        for batch in batches
        if isinstance(batch, Mapping)
    }
    if set(batch_by_id) != _V10_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v10 requires active, proposed, and cumulative Unknown030 batches"
        )
    expected_batches = {
        "satellite-global-open-v3-active-001": {
            "artifact_id": "satellite-global-open-v3-active-001",
            "manifest": {
                "bytes": 94619,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-active-001/batch-manifest.json"
                ),
                "sha256": _V5_FUSION_BATCH_PINS[
                    "satellite_review_runs/2026-07-18-global-open-v3-active-001"
                ],
            },
        },
        "satellite-global-open-v3-proposed-001": {
            "artifact_id": "satellite-global-open-v3-proposed-001",
            "manifest": {
                "bytes": 28779,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-proposed-001/batch-manifest.json"
                ),
                "sha256": _V5_FUSION_BATCH_PINS[
                    "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
                ],
            },
        },
        "satellite-global-open-v3-unknown-030": {
            "artifact_id": "satellite-global-open-v3-unknown-030",
            "manifest": {
                "bytes": 6453228,
                "path": (
                    "satellite_review_runs/"
                    "2026-07-18-global-open-v3-unknown-030/batch-manifest.json"
                ),
                "sha256": _V10_UNKNOWN_CATALOG_MANIFEST_SHA256,
            },
        },
    }
    if batch_by_id != expected_batches:
        raise ConstructionMasterError("v10 satellite identity or hash changed")


def _validate_v11_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V11_MASTER_ID:
        raise ConstructionMasterError("v11 master identity changed")
    if document.get("generated_at") != "2026-07-19T21:00:00Z":
        raise ConstructionMasterError("v11 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V11_INPUT_KEYS:
        raise ConstructionMasterError("v11 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V11_COUNT_CONTRACT}
        != _V11_COUNT_CONTRACT
        or set(expected)
        != {*_V11_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V11_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v11 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v11 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v20",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v11 Tier-A release identities changed")

    # Revalidate every inherited lane through v10. V11 substitutes only the
    # current seed and the contextual federation/coverage manifests; the
    # Unknown030 catalog and candidate-fusion v13 review lineage remain frozen.
    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v13",
            "data": {
                "bytes": 228437,
                "path": "releases/2026-07-19-open-seed-v13/construction_pipeline.csv",
                "sha256": _V10_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 49544,
                "path": "releases/2026-07-19-open-seed-v13/evidence.csv",
                "sha256": _V10_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 3477,
                "path": "releases/2026-07-19-open-seed-v13/manifest.json",
                "sha256": _V10_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v13",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2237,
            "path": "audits/2026-07-19-public-open-coverage-v9/manifest.json",
            "sha256": _V10_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v8/manifest.json",
            "sha256": _V10_FEDERATION_MANIFEST_SHA256,
        },
    }
    _validate_v10_definition_contract(
        {
            "expected_counts": {
                **_V10_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V10_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T18:30:00Z",
            "inputs": inherited_inputs,
            "master_id": V10_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v20"]
    if open_seed != {
        "artifact_id": "epoch-official-open-seed-v20",
        "data": {
            "bytes": 276056,
            "path": "releases/2026-07-19-open-seed-v20/construction_pipeline.csv",
            "sha256": _V11_OPEN_SEED_DATA_SHA256,
        },
        "evidence": {
            "bytes": 67039,
            "path": "releases/2026-07-19-open-seed-v20/evidence.csv",
            "sha256": _V11_OPEN_SEED_EVIDENCE_SHA256,
        },
        "manifest": {
            "bytes": 4293,
            "path": "releases/2026-07-19-open-seed-v20/manifest.json",
            "sha256": _V11_OPEN_SEED_MANIFEST_SHA256,
        },
        "release_id": "epoch-official-open-seed-v20",
    }:
        raise ConstructionMasterError("v11 open-seed v20 checkpoints changed")

    if inputs["coverage_context"] != {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v10/manifest.json",
            "sha256": _V11_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v9/manifest.json",
            "sha256": _V11_FEDERATION_MANIFEST_SHA256,
        },
    }:
        raise ConstructionMasterError("v11 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v11 satellite batch set changed")
    if {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    } != _V11_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v11 requires active, proposed, and cumulative Unknown030 batches"
        )


def _validate_v12_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V12_MASTER_ID:
        raise ConstructionMasterError("v12 master identity changed")
    if document.get("generated_at") != "2026-07-19T21:45:00Z":
        raise ConstructionMasterError("v12 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V12_INPUT_KEYS:
        raise ConstructionMasterError("v12 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V12_COUNT_CONTRACT}
        != _V12_COUNT_CONTRACT
        or set(expected)
        != {*_V12_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V12_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v12 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v12 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v30",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v12 Tier-A release identities changed")

    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v20",
            "data": {
                "bytes": 276056,
                "path": "releases/2026-07-19-open-seed-v20/construction_pipeline.csv",
                "sha256": _V11_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 67039,
                "path": "releases/2026-07-19-open-seed-v20/evidence.csv",
                "sha256": _V11_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 4293,
                "path": "releases/2026-07-19-open-seed-v20/manifest.json",
                "sha256": _V11_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v20",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v10/manifest.json",
            "sha256": _V11_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 985,
            "path": "federated_indexes/2026-07-19-public-open-v9/manifest.json",
            "sha256": _V11_FEDERATION_MANIFEST_SHA256,
        },
    }
    _validate_v11_definition_contract(
        {
            "expected_counts": {
                **_V11_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V11_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T21:00:00Z",
            "inputs": inherited_inputs,
            "master_id": V11_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v30"]
    if open_seed != {
        "artifact_id": "epoch-official-open-seed-v30",
        "data": {
            "bytes": 303236,
            "path": "releases/2026-07-19-open-seed-v30/construction_pipeline.csv",
            "sha256": _V12_OPEN_SEED_DATA_SHA256,
        },
        "evidence": {
            "bytes": 80616,
            "path": "releases/2026-07-19-open-seed-v30/evidence.csv",
            "sha256": _V12_OPEN_SEED_EVIDENCE_SHA256,
        },
        "manifest": {
            "bytes": 4980,
            "path": "releases/2026-07-19-open-seed-v30/manifest.json",
            "sha256": _V12_OPEN_SEED_MANIFEST_SHA256,
        },
        "release_id": "epoch-official-open-seed-v30",
    }:
        raise ConstructionMasterError("v12 open-seed v30 checkpoints changed")

    if inputs["coverage_context"] != {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v11/manifest.json",
            "sha256": _V12_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-19-public-open-v10/manifest.json",
            "sha256": _V12_FEDERATION_MANIFEST_SHA256,
        },
    }:
        raise ConstructionMasterError("v12 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v12 satellite batch set changed")
    if {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    } != _V12_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v12 requires active, proposed, and cumulative Unknown030 batches"
        )


def _validate_v13_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V13_MASTER_ID:
        raise ConstructionMasterError("v13 master identity changed")
    if document.get("generated_at") != "2026-07-19T22:50:00Z":
        raise ConstructionMasterError("v13 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V13_INPUT_KEYS:
        raise ConstructionMasterError("v13 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V13_COUNT_CONTRACT}
        != _V13_COUNT_CONTRACT
        or set(expected)
        != {*_V13_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V13_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v13 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v13 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v32",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v13 Tier-A release identities changed")

    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v30",
            "data": {
                "bytes": 303236,
                "path": "releases/2026-07-19-open-seed-v30/construction_pipeline.csv",
                "sha256": _V12_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 80616,
                "path": "releases/2026-07-19-open-seed-v30/evidence.csv",
                "sha256": _V12_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 4980,
                "path": "releases/2026-07-19-open-seed-v30/manifest.json",
                "sha256": _V12_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v30",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v11/manifest.json",
            "sha256": _V12_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-19-public-open-v10/manifest.json",
            "sha256": _V12_FEDERATION_MANIFEST_SHA256,
        },
    }
    _validate_v12_definition_contract(
        {
            "expected_counts": {
                **_V12_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V12_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T21:45:00Z",
            "inputs": inherited_inputs,
            "master_id": V12_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v32"]
    if open_seed != {
        "artifact_id": "epoch-official-open-seed-v32",
        "data": {
            "bytes": 310708,
            "path": "releases/2026-07-19-open-seed-v32/construction_pipeline.csv",
            "sha256": _V13_OPEN_SEED_DATA_SHA256,
        },
        "evidence": {
            "bytes": 84731,
            "path": "releases/2026-07-19-open-seed-v32/evidence.csv",
            "sha256": _V13_OPEN_SEED_EVIDENCE_SHA256,
        },
        "manifest": {
            "bytes": 5245,
            "path": "releases/2026-07-19-open-seed-v32/manifest.json",
            "sha256": _V13_OPEN_SEED_MANIFEST_SHA256,
        },
        "release_id": "epoch-official-open-seed-v32",
    }:
        raise ConstructionMasterError("v13 open-seed v32 checkpoints changed")

    if inputs["coverage_context"] != {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v12/manifest.json",
            "sha256": _V13_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-19-public-open-v11/manifest.json",
            "sha256": _V13_FEDERATION_MANIFEST_SHA256,
        },
    }:
        raise ConstructionMasterError("v13 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v13 satellite batch set changed")
    if {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    } != _V13_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v13 requires active, proposed, and cumulative Unknown030 batches"
        )


def _validate_v14_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("master_id") != V14_MASTER_ID:
        raise ConstructionMasterError("v14 master identity changed")
    if document.get("generated_at") != "2026-07-19T23:59:55Z":
        raise ConstructionMasterError("v14 generation timestamp changed")
    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != _V14_INPUT_KEYS:
        raise ConstructionMasterError("v14 input lanes changed")
    expected = document.get("expected_counts")
    if (
        not isinstance(expected, Mapping)
        or {key: expected.get(key) for key in _V14_COUNT_CONTRACT}
        != _V14_COUNT_CONTRACT
        or set(expected)
        != {*_V14_COUNT_CONTRACT, "tier_a_arithmetic_projection_sha256"}
        or expected.get("tier_a_arithmetic_projection_sha256")
        != _V14_TIER_A_PROJECTION_SHA256
    ):
        raise ConstructionMasterError("v14 count or Tier-A projection contract changed")

    tier_a = inputs["tier_a_releases"]
    if not isinstance(tier_a, list) or len(tier_a) != 2:
        raise ConstructionMasterError("v14 Tier-A release set changed")
    tier_a_by_artifact = {
        item.get("artifact_id"): item
        for item in tier_a
        if isinstance(item, Mapping)
    }
    if set(tier_a_by_artifact) != {
        "epoch-official-open-seed-v33",
        "global-open-v3",
    }:
        raise ConstructionMasterError("v14 Tier-A release identities changed")

    inherited_inputs = dict(inputs)
    inherited_inputs["tier_a_releases"] = [
        {
            "artifact_id": "epoch-official-open-seed-v32",
            "data": {
                "bytes": 310708,
                "path": "releases/2026-07-19-open-seed-v32/construction_pipeline.csv",
                "sha256": _V13_OPEN_SEED_DATA_SHA256,
            },
            "evidence": {
                "bytes": 84731,
                "path": "releases/2026-07-19-open-seed-v32/evidence.csv",
                "sha256": _V13_OPEN_SEED_EVIDENCE_SHA256,
            },
            "manifest": {
                "bytes": 5245,
                "path": "releases/2026-07-19-open-seed-v32/manifest.json",
                "sha256": _V13_OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": "epoch-official-open-seed-v32",
        },
        tier_a_by_artifact["global-open-v3"],
    ]
    inherited_inputs["coverage_context"] = {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v12/manifest.json",
            "sha256": _V13_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-19-public-open-v11/manifest.json",
            "sha256": _V13_FEDERATION_MANIFEST_SHA256,
        },
    }
    _validate_v13_definition_contract(
        {
            "expected_counts": {
                **_V13_COUNT_CONTRACT,
                "tier_a_arithmetic_projection_sha256": (
                    _V13_TIER_A_PROJECTION_SHA256
                ),
            },
            "generated_at": "2026-07-19T22:50:00Z",
            "inputs": inherited_inputs,
            "master_id": V13_MASTER_ID,
        }
    )

    open_seed = tier_a_by_artifact["epoch-official-open-seed-v33"]
    if open_seed != {
        "artifact_id": "epoch-official-open-seed-v33",
        "data": {
            "bytes": 314176,
            "path": "releases/2026-07-19-open-seed-v33/construction_pipeline.csv",
            "sha256": _V14_OPEN_SEED_DATA_SHA256,
        },
        "evidence": {
            "bytes": 86375,
            "path": "releases/2026-07-19-open-seed-v33/evidence.csv",
            "sha256": _V14_OPEN_SEED_EVIDENCE_SHA256,
        },
        "manifest": {
            "bytes": 5353,
            "path": "releases/2026-07-19-open-seed-v33/manifest.json",
            "sha256": _V14_OPEN_SEED_MANIFEST_SHA256,
        },
        "release_id": "epoch-official-open-seed-v33",
    }:
        raise ConstructionMasterError("v14 open-seed v33 checkpoints changed")

    if inputs["coverage_context"] != {
        "audit_manifest": {
            "bytes": 2240,
            "path": "audits/2026-07-19-public-open-coverage-v13/manifest.json",
            "sha256": _V14_COVERAGE_AUDIT_MANIFEST_SHA256,
        },
        "federation_manifest": {
            "bytes": 986,
            "path": "federated_indexes/2026-07-19-public-open-v12/manifest.json",
            "sha256": _V14_FEDERATION_MANIFEST_SHA256,
        },
    }:
        raise ConstructionMasterError("v14 federation or coverage-audit context changed")

    batches = inputs["satellite_batches"]
    if not isinstance(batches, list) or len(batches) != 3:
        raise ConstructionMasterError("v14 satellite batch set changed")
    if {
        batch.get("artifact_id")
        for batch in batches
        if isinstance(batch, Mapping)
    } != _V14_SATELLITE_BATCH_IDS:
        raise ConstructionMasterError(
            "v14 requires active, proposed, and cumulative Unknown030 batches"
        )


def _definition(path: Path) -> tuple[dict[str, Any], bytes, Path, dict[str, Path]]:
    document, raw = _json_file(path, "construction-master definition")
    if raw != _canonical_json(document):
        raise ConstructionMasterError("definition must use canonical JSON")
    if set(document) != {
        "expected_counts",
        "format",
        "generated_at",
        "inputs",
        "master_id",
        "schema_version",
        "scope",
    }:
        raise ConstructionMasterError("definition keys differ from v1 contract")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION:
        raise ConstructionMasterError("unsupported definition schema version")
    if document.get("format") != "datacenter-atlas-construction-master-definition-v1":
        raise ConstructionMasterError("definition format changed")
    if document.get("scope") != SCOPE_POLICY:
        raise ConstructionMasterError("definition weakens construction-master safeguards")
    _timestamp(document.get("generated_at"), "generated_at")
    if not isinstance(document.get("master_id"), str) or not document["master_id"]:
        raise ConstructionMasterError("master_id must be non-empty text")
    if _is_v14_definition(document):
        _validate_v14_definition_contract(document)
    elif _is_v13_definition(document):
        _validate_v13_definition_contract(document)
    elif _is_v12_definition(document):
        _validate_v12_definition_contract(document)
    elif _is_v11_definition(document):
        _validate_v11_definition_contract(document)
    elif _is_v10_definition(document):
        _validate_v10_definition_contract(document)
    elif _is_v9_definition(document):
        _validate_v9_definition_contract(document)
    elif _is_v8_definition(document):
        _validate_v8_definition_contract(document)
    elif _is_v7_definition(document):
        _validate_v7_definition_contract(document)
    elif _is_v6_definition(document):
        _validate_v6_definition_contract(document)
    elif _is_v5_definition(document):
        _validate_v5_definition_contract(document)
    elif _is_v4_definition(document):
        _validate_v4_definition_contract(document)
    elif _is_v3_definition(document):
        _validate_v3_definition_contract(document)
    elif _is_v2_definition(document):
        _validate_v2_definition_contract(document)
    package_root = path.parent.parent.resolve()
    resolved: dict[str, Path] = {}
    seen_paths: set[str] = set()
    checkpoints = list(_checkpoint_specs(document.get("inputs")))
    if not checkpoints:
        raise ConstructionMasterError("definition has no pinned inputs")
    for label, spec in checkpoints:
        supplied = str(spec.get("path"))
        if supplied in seen_paths:
            raise ConstructionMasterError(f"input path repeated: {supplied}")
        seen_paths.add(supplied)
        expected_sha = spec.get("sha256")
        expected_bytes = spec.get("bytes")
        if not isinstance(expected_sha, str) or not _SHA_RE.fullmatch(expected_sha):
            raise ConstructionMasterError(f"{label} sha256 is invalid")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ConstructionMasterError(f"{label} bytes is invalid")
        input_path = _safe_path(package_root, spec.get("path"), label)
        if input_path.is_symlink() or not input_path.is_file():
            raise ConstructionMasterError(f"{label} is not a regular file")
        if _checkpoint(input_path) != {"bytes": expected_bytes, "sha256": expected_sha}:
            raise ConstructionMasterError(f"pinned input changed: {supplied}")
        resolved[supplied] = input_path
    expected = document.get("expected_counts")
    if not isinstance(expected, Mapping):
        raise ConstructionMasterError("expected_counts must be an object")
    return document, raw, package_root, resolved


def _path(spec: Mapping[str, Any], resolved: Mapping[str, Path]) -> Path:
    return resolved[str(spec["path"])]


def _feature_collection(path: Path) -> Iterator[dict[str, Any]]:
    """Stream the canonical features-first GeoJSON used by the OSM shortlist."""

    decoder = json.JSONDecoder()
    prefix = '{"features":['
    with path.open("r", encoding="utf-8") as source:
        buffer = source.read(1024 * 1024)
        if not buffer.startswith(prefix):
            raise ConstructionMasterError("structural shortlist is not features-first")
        position = len(prefix)
        while True:
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position >= len(buffer):
                more = source.read(1024 * 1024)
                if not more:
                    raise ConstructionMasterError("structural feature array is truncated")
                buffer = buffer[position:] + more
                position = 0
                continue
            if buffer[position] == "]":
                suffix = buffer[position + 1 :] + source.read()
                try:
                    metadata = json.loads('{"features":[]' + suffix)
                except json.JSONDecodeError as error:
                    raise ConstructionMasterError("structural collection suffix is invalid") from error
                if metadata.get("type") != "FeatureCollection":
                    raise ConstructionMasterError("structural collection type changed")
                return
            if buffer[position] == ",":
                position += 1
                continue
            try:
                feature, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                more = source.read(1024 * 1024)
                if not more:
                    raise ConstructionMasterError("structural feature is truncated")
                buffer = buffer[position:] + more
                position = 0
                continue
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ConstructionMasterError("structural collection member is not a feature")
            yield feature
            position = end
            if position > 4 * 1024 * 1024:
                buffer = buffer[position:]
                position = 0


def _csv_rows(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ConstructionMasterError(f"CSV has no header: {path}")
        for row in reader:
            yield dict(row)


def _json_array(raw: str, label: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as error:
        raise ConstructionMasterError(f"{label} is invalid JSON") from error
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ConstructionMasterError(f"{label} must be an array of objects")
    return value


def _float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ConstructionMasterError(f"expected numeric value, got {value!r}") from error


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ConstructionMasterError(f"expected boolean value, got {value!r}")


def _date(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    candidate = value[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _date_bounds(values: Iterable[Any]) -> tuple[str | None, str | None]:
    dates = sorted({parsed for value in values if (parsed := _date(value)) is not None})
    return (dates[0], dates[-1]) if dates else (None, None)


def _source_root(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith(("openstreetmap", "osm")):
        return "openstreetmap"
    if lowered.startswith("epoch"):
        return "epoch_ai"
    if lowered.startswith("wikidata"):
        return "wikidata"
    if lowered.startswith(("sec", "edgar")):
        return "sec_edgar"
    if lowered.startswith("natural_earth"):
        return "natural_earth"
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_") or "unknown"


def _row_id(observation_kind: str, artifact_id: str, record_id: str) -> str:
    return str(uuid.uuid5(ROW_NAMESPACE, f"{observation_kind}|{artifact_id}|{record_id}"))


def _evidence_map(path: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in _csv_rows(path):
        evidence_id = row.get("evidence_id", "")
        if not evidence_id or evidence_id in result:
            raise ConstructionMasterError(f"evidence ID missing or repeated: {evidence_id!r}")
        result[evidence_id] = row
    return result


def _compact_evidence(row: Mapping[str, str]) -> dict[str, Any]:
    return {
        "content_hash": row.get("content_hash") or None,
        "evidence_id": row.get("evidence_id") or None,
        "kind": row.get("kind") or None,
        "license": row.get("license") or None,
        "published_at": row.get("published_at") or None,
        "publisher": row.get("publisher") or None,
        "retrieved_at": row.get("retrieved_at") or None,
        "source_family": row.get("source_family") or None,
        "source_url": row.get("source_url") or None,
        "title": row.get("title") or None,
    }


def _capacity_split(items: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    capacity: list[dict[str, Any]] = []
    annual: list[dict[str, Any]] = []
    pue: list[dict[str, Any]] = []
    for raw in items:
        observation = {
            "as_of_date": raw.get("as_of_date"),
            "confidence": raw.get("confidence"),
            "evidence_id": raw.get("evidence_id"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "method": raw.get("method"),
            "metric": raw.get("metric"),
            "notes": raw.get("notes"),
            "scope": "source_scoped_entity",
            "stage": raw.get("stage"),
            "target_date": raw.get("target_date"),
            "unit": raw.get("unit"),
            "value": raw.get("base"),
        }
        metric = str(raw.get("metric") or "").lower()
        if metric in {"annual_energy_mwh", "annual_energy"}:
            annual.append(observation)
        elif metric in {"pue", "power_usage_effectiveness"}:
            pue.append(observation)
        else:
            capacity.append(observation)
    return capacity, annual, pue


def _selected_evidence(
    source_row: Mapping[str, str],
    workloads: Sequence[Mapping[str, Any]],
    capacities: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, str]],
) -> tuple[list[str], list[dict[str, Any]]]:
    ids = {
        value
        for key in (
            "country_assignment_evidence_id",
            "operating_model_evidence_id",
            "snapshot_evidence_id",
            "status_evidence_id",
        )
        if (value := source_row.get(key))
    }
    ids.update(
        str(item["evidence_id"])
        for item in [*workloads, *capacities]
        if item.get("evidence_id")
    )
    missing = sorted(ids - evidence.keys())
    if missing:
        raise ConstructionMasterError(f"row references absent evidence IDs: {missing}")
    ordered = sorted(ids)
    return ordered, [_compact_evidence(evidence[evidence_id]) for evidence_id in ordered]


def _source_roots(source_row: Mapping[str, str], evidence_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    roots = {
        _source_root(str(item.get("source_family")))
        for item in evidence_rows
        if item.get("source_family")
    }
    if not roots:
        roots.add(_source_root(source_row.get("stable_key", "unknown").split(":", 1)[0]))
    return sorted(roots)


def _validate_v9_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V9_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V9_OPEN_SEED_PUBLISHERS
        or source_licenses != {"CC-BY-4.0", "all-rights-reserved"}
    ):
        raise ConstructionMasterError("v9 open-seed source allowlist changed")


def _validate_v10_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V10_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V10_OPEN_SEED_PUBLISHERS
        or source_licenses != {"CC-BY-4.0", "all-rights-reserved"}
    ):
        raise ConstructionMasterError("v10 open-seed source allowlist changed")


def _validate_v11_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V11_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V11_OPEN_SEED_PUBLISHERS
        or source_licenses != _V11_OPEN_SEED_LICENSES
    ):
        raise ConstructionMasterError("v11 open-seed source allowlist changed")


def _validate_v12_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V12_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V12_OPEN_SEED_PUBLISHERS
        or source_licenses != _V12_OPEN_SEED_LICENSES
    ):
        raise ConstructionMasterError("v12 open-seed source allowlist changed")


def _validate_v13_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V13_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V13_OPEN_SEED_PUBLISHERS
        or source_licenses != _V13_OPEN_SEED_LICENSES
    ):
        raise ConstructionMasterError("v13 open-seed source allowlist changed")


def _validate_v14_open_seed_source_allowlist(
    rows: Sequence[Mapping[str, str]],
    evidence: Mapping[str, Mapping[str, str]],
) -> None:
    source_roots: set[str] = set()
    publishers: set[str] = set()
    source_licenses: set[str] = set()
    for source_row in rows:
        workloads = _json_array(
            source_row.get("workloads_json", "[]"), "workloads_json"
        )
        capacities = _json_array(
            source_row.get("capacity_estimates_json", "[]"),
            "capacity_estimates_json",
        )
        _evidence_ids, selected = _selected_evidence(
            source_row, workloads, capacities, evidence
        )
        source_roots.update(_source_roots(source_row, selected))
        publishers.update(
            str(item["publisher"])
            for item in selected
            if item.get("publisher")
        )
        source_license = source_row.get("source_license")
        if source_license:
            source_licenses.add(source_license)
    if (
        source_roots != _V14_OPEN_SEED_SOURCE_ROOTS
        or publishers != _V14_OPEN_SEED_PUBLISHERS
        or source_licenses != _V14_OPEN_SEED_LICENSES
    ):
        raise ConstructionMasterError("v14 open-seed source allowlist changed")


def _release_row(
    source_row: Mapping[str, str],
    *,
    artifact: Mapping[str, Any],
    artifact_sha: str,
    manifest_sha: str,
    evidence: Mapping[str, Mapping[str, str]],
    satellite_by_entity: Mapping[str, list[dict[str, Any]]],
    advisories_by_entity: Mapping[str, list[dict[str, Any]]],
    tier: str,
) -> dict[str, Any]:
    workloads = _json_array(source_row.get("workloads_json", "[]"), "workloads_json")
    capacity_raw = _json_array(source_row.get("capacity_estimates_json", "[]"), "capacity_estimates_json")
    capacity, annual, pue = _capacity_split(capacity_raw)
    evidence_ids, source_evidence = _selected_evidence(source_row, workloads, capacity_raw, evidence)
    evidence_dates: list[Any] = [
        source_row.get("status_as_of"),
        source_row.get("snapshot_as_of"),
        source_row.get("source_retrieved_at"),
    ]
    for item in source_evidence:
        evidence_dates.extend((item.get("published_at"), item.get("retrieved_at")))
    first_date, last_date = _date_bounds(evidence_dates)
    entity_id = source_row.get("entity_id", "")
    if not entity_id:
        raise ConstructionMasterError("source release row has no entity_id")
    review_only = tier == "B"
    if review_only:
        normalized = "review_lead"
        construction = {
            "confidence": None,
            "method": "review_only_source_signal_not_verified",
            "source_supported": False,
            "verification_status": "review_only_not_verified",
            "verified": False,
        }
        identity = {
            "confidence": _float(source_row.get("status_confidence")),
            "status": "unverified_fuzzy_review_lead",
        }
        disposition = {
            "construction_arithmetic_included": False,
            "exclusion_reason": "review_only_fuzzy_identity_signal",
            "label": "included_review_lead_only",
            "unique_site_counted": False,
        }
        evidence_scope = "source_supported_identity_or_lifecycle_review_lead"
    else:
        normalized = source_row.get("status") or "unknown"
        construction = {
            "confidence": _float(source_row.get("status_confidence")),
            "method": source_row.get("status_method") or None,
            "source_supported": True,
            "verification_status": "source_supported_not_independently_verified",
            "verified": False,
        }
        identity = {
            "confidence": _float(source_row.get("snapshot_confidence")),
            "status": "source_scoped_identity_not_cross_source_resolved",
        }
        disposition = {
            "construction_arithmetic_included": True,
            "exclusion_reason": None,
            "label": "included_source_supported_construction_arithmetic",
            "unique_site_counted": False,
        }
        evidence_scope = "source_supported_construction_pipeline_observation"
    operating = None
    if source_row.get("operating_model"):
        operating = {
            "confidence": _float(source_row.get("operating_model_confidence")),
            "evidence_id": source_row.get("operating_model_evidence_id") or None,
            "value": source_row.get("operating_model"),
        }
    return {
        "annual_energy_observations": annual,
        "capacity_observations": capacity,
        "construction": construction,
        "disposition": disposition,
        "entity": {
            "address": source_row.get("address") or None,
            "coordinate_method": "source_scoped_release_coordinate",
            "country": source_row.get("country") or None,
            "country_iso_a2": source_row.get("country_iso_a2") or None,
            "country_iso_a3": source_row.get("country_iso_a3") or None,
            "kind": source_row.get("entity_kind") or None,
            "latitude": _float(source_row.get("latitude")),
            "longitude": _float(source_row.get("longitude")),
            "name": source_row.get("name") or None,
        },
        "evidence_scope": evidence_scope,
        "first_evidence_date": first_date,
        "fusion_overlay": None,
        "identity": identity,
        "last_evidence_date": last_date,
        "lifecycle": {
            "normalized_status": normalized,
            "reported_status": source_row.get("status") or None,
            "reported_status_date": source_row.get("status_as_of") or None,
        },
        "observation_kind": "source_construction_pipeline" if tier == "A" else "fuzzy_identity_lifecycle_review_lead",
        "operating_model_observation": operating,
        "pue_observations": pue,
        "resolution_advisories": [] if review_only else advisories_by_entity.get(entity_id, []),
        "review_only": review_only,
        "row_id": _row_id(
            "source_construction_pipeline" if tier == "A" else "fuzzy_identity_lifecycle_review_lead",
            str(artifact["artifact_id"]),
            entity_id,
        ),
        "satellite_links": satellite_by_entity.get(entity_id, []),
        "source": {
            "artifact_id": artifact["artifact_id"],
            "artifact_path": artifact["data"]["path"],
            "artifact_sha256": artifact_sha,
            "evidence_ids": evidence_ids,
            "manifest_sha256": manifest_sha,
            "record_id": entity_id,
            "release_id": artifact["release_id"],
            "source_entity_id": entity_id,
            "source_license": source_row.get("source_license") or None,
            "source_retrieved_at": source_row.get("source_retrieved_at") or None,
            "source_roots": _source_roots(source_row, source_evidence),
            "source_url": source_row.get("source_url") or None,
        },
        "source_evidence": source_evidence,
        "tier": tier,
        "untyped_capacity_statements": [],
        "workload_observations": workloads,
    }


def _edge_rows(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> Iterator[dict[str, Any]]:
    pilot, _ = _json_file(_path(spec["pilot"], resolved), "EdgeMode pilot")
    documents = {
        item["evidence_id"]: item for item in pilot.get("evidence_documents", [])
    }
    if len(documents) != len(pilot.get("evidence_documents", [])):
        raise ConstructionMasterError("EdgeMode evidence IDs repeat")
    country_names = {"ES": "Spain", "PA": "Panama"}
    for lead in sorted(pilot.get("leads", []), key=lambda item: item["lead_id"]):
        evidence_ids = sorted(set(lead.get("evidence_ids", [])))
        if any(evidence_id not in documents for evidence_id in evidence_ids):
            raise ConstructionMasterError("EdgeMode lead references absent evidence")
        source_evidence = [
            {
                "content_hash": documents[evidence_id]["sha256"],
                "evidence_id": evidence_id,
                "filed_on": documents[evidence_id]["filed_on"],
                "form": documents[evidence_id]["form"],
                "license": "US_SEC_public_filing_metadata_and_factual_claims_only",
                "publisher": "U.S. Securities and Exchange Commission",
                "source_family": "sec_edgar_edgemode",
                "source_url": documents[evidence_id]["url"],
            }
            for evidence_id in evidence_ids
        ]
        first_date, last_date = _date_bounds(
            item.get("filed_on") for item in source_evidence
        )
        lead_id = lead["lead_id"]
        country_code = lead.get("country_code")
        yield {
            "annual_energy_observations": [],
            "capacity_observations": [],
            "construction": {
                "confidence": None,
                "method": "sec_filing_review_physical_construction_not_evidenced",
                "source_supported": False,
                "verification_status": "review_lead_not_verified",
                "verified": False,
            },
            "disposition": {
                "construction_arithmetic_included": False,
                "exclusion_reason": "physical_construction_and_typed_capacity_not_verified",
                "label": "included_sec_filing_review_lead_only",
                "unique_site_counted": False,
            },
            "entity": {
                "address": lead.get("locality_label"),
                "coordinate_method": "coordinates_not_available",
                "country": country_names.get(country_code),
                "country_iso_a2": country_code,
                "country_iso_a3": None,
                "kind": "project_lead",
                "latitude": None,
                "longitude": None,
                "name": lead.get("name"),
            },
            "evidence_scope": "source_supported_identity_or_lifecycle_review_lead",
            "first_evidence_date": first_date,
            "fusion_overlay": None,
            "identity": {
                "confidence": None,
                "status": lead.get("project_identity_status") or "unresolved_project_lead",
            },
            "last_evidence_date": last_date,
            "lifecycle": {
                "normalized_status": "review_lead",
                "reported_status": lead.get("source_status"),
                "reported_status_date": last_date,
            },
            "observation_kind": "sec_filing_project_review_lead",
            "operating_model_observation": None,
            "pue_observations": [],
            "resolution_advisories": [],
            "review_only": True,
            "row_id": _row_id("sec_filing_project_review_lead", spec["artifact_id"], lead_id),
            "satellite_links": [],
            "source": {
                "artifact_id": spec["artifact_id"],
                "artifact_path": spec["pilot"]["path"],
                "artifact_sha256": spec["pilot"]["sha256"],
                "evidence_ids": evidence_ids,
                "manifest_sha256": spec["manifest"]["sha256"],
                "record_id": lead_id,
                "release_id": None,
                "source_entity_id": None,
                "source_license": "US_SEC_public_filing_metadata_and_factual_claims_only",
                "source_retrieved_at": None,
                "source_roots": ["sec_edgar"],
                "source_url": None,
            },
            "source_evidence": source_evidence,
            "tier": "B",
            "untyped_capacity_statements": lead.get("source_power_statements", []),
            "workload_observations": [
                {
                    "operationally_verified": False,
                    "stage": "intended",
                    "workload": workload,
                }
                for workload in lead.get("intended_type_and_workload", [])
            ],
        }


def _ireland_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .ireland_planning import validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    expected_paths = {
        "manifest": release_root / "manifest.json",
        "observations": release_root / "observations.jsonl",
        "relationship_suggestions": (
            release_root / "relationship-suggestions.jsonl"
        ),
    }
    if any(
        _path(spec[key], resolved) != expected_path
        for key, expected_path in expected_paths.items()
    ):
        raise ConstructionMasterError("Ireland planning checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    summary = bundle["summary"]
    if (
        assessment.get("release_id") != spec.get("release_id")
        or summary.get("matched_observation_count") != 114
        or summary.get("unique_site_count") is not None
    ):
        raise ConstructionMasterError("Ireland planning release boundary changed")

    observations = _jsonl_objects(
        _path(spec["observations"], resolved), "Ireland planning observations"
    )
    suggestions = _jsonl_objects(
        _path(spec["relationship_suggestions"], resolved),
        "Ireland planning relationship suggestions",
    )
    observation_ids = [str(item.get("observation_id")) for item in observations]
    if (
        len(observations) != 114
        or len(set(observation_ids)) != len(observation_ids)
        or any(item.get("observation_type") != "planning_application" for item in observations)
    ):
        raise ConstructionMasterError("Ireland planning observations changed")

    suggestion_ids: set[str] = set()
    by_observation: dict[str, list[str]] = defaultdict(list)
    basis_counts: Counter[str] = Counter()
    for suggestion in suggestions:
        suggestion_id = suggestion.get("suggestion_id")
        members = suggestion.get("member_observation_ids")
        if (
            not isinstance(suggestion_id, str)
            or suggestion_id in suggestion_ids
            or suggestion.get("review_only") is not True
            or suggestion.get("auto_merge_permitted") is not False
            or not isinstance(members, list)
            or len(members) < 2
            or any(member not in observation_ids for member in members)
        ):
            raise ConstructionMasterError(
                "Ireland planning relationships must remain advisory and unaccepted"
            )
        suggestion_ids.add(suggestion_id)
        basis_counts[str(suggestion.get("basis"))] += 1
        for member in members:
            by_observation[str(member)].append(suggestion_id)
    if len(suggestions) != 32:
        raise ConstructionMasterError("Ireland relationship suggestion count changed")
    for values in by_observation.values():
        values.sort()
    return {
        "assessment": assessment,
        "observations": observations,
        "relationship_ids_by_observation": dict(by_observation),
        "relationship_summary": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "observations_in_suggestions": len(by_observation),
            "suggestion_groups": len(suggestions),
            "suggestion_groups_by_basis": dict(sorted(basis_counts.items())),
            "suggestions_are_advisory_only": True,
            "unique_physical_site_count": None,
        },
    }


def _ireland_row(
    observation: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    relationship_suggestion_ids: Sequence[str],
) -> dict[str, Any]:
    observation_id = observation.get("observation_id")
    attributes = observation.get("source_attributes")
    coordinates = observation.get("coordinates")
    dates = observation.get("dates")
    if (
        not isinstance(observation_id, str)
        or not isinstance(attributes, Mapping)
        or not isinstance(coordinates, Mapping)
        or not isinstance(dates, Mapping)
        or observation.get("evidence_scope")
        != {
            "construction_evidence": False,
            "facility_lifecycle_status": None,
            "operation_evidence": False,
            "record_type": "planning_application_observation",
        }
    ):
        raise ConstructionMasterError("Ireland planning observation contract changed")
    if coordinates.get("crs") != "EPSG:4326":
        raise ConstructionMasterError("Ireland planning coordinate CRS changed")
    longitude = _float(coordinates.get("longitude"))
    latitude = _float(coordinates.get("latitude"))
    if longitude is None or latitude is None:
        raise ConstructionMasterError("Ireland planning coordinate is absent")
    date_values = [
        value.get("utc")
        for value in dates.values()
        if isinstance(value, Mapping)
    ]
    first_date, last_date = _date_bounds(date_values)
    application_number = attributes.get("ApplicationNumber")
    planning_metadata = {
        "normalized_dates": dict(dates),
        "relationship_suggestion_ids": list(relationship_suggestion_ids),
        "source_attributes": dict(attributes),
        "source_geometry": observation.get("source_geometry"),
        "source_status_fields_are_planning_process_only": True,
    }
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "construction": {
            "confidence": None,
            "method": "planning_application_is_not_construction_or_operation_evidence",
            "source_supported": False,
            "verification_status": (
                "official_planning_process_observation_not_construction_verified"
            ),
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": (
                "planning_process_observation_does_not_establish_facility_identity_"
                "lifecycle_type_power_energy_pue_or_workload"
            ),
            "label": "included_official_planning_application_review_lead_only",
            "unique_site_counted": False,
        },
        "entity": {
            "address": attributes.get("DevelopmentAddress"),
            "coordinate_method": "official_planning_application_point_epsg4326",
            "country": "Ireland",
            "country_iso_a2": "IE",
            "country_iso_a3": "IRL",
            "kind": "planning_application_observation",
            "latitude": latitude,
            "longitude": longitude,
            "name": (
                f"Irish planning application {application_number}"
                if application_number
                else f"Irish planning observation {observation_id}"
            ),
        },
        "evidence_scope": IRELAND_OBSERVATION_KIND,
        "first_evidence_date": first_date,
        "fusion_overlay": None,
        "identity": {
            "confidence": None,
            "status": "planning_observation_not_resolved_to_unique_facility",
        },
        "last_evidence_date": last_date,
        "lifecycle": {
            "normalized_status": "planning_application_review_lead",
            "reported_status": None,
            "reported_status_date": None,
        },
        "observation_kind": IRELAND_OBSERVATION_KIND,
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id(
            IRELAND_OBSERVATION_KIND, str(spec["artifact_id"]), observation_id
        ),
        "satellite_links": [],
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["observations"]["path"],
            "artifact_sha256": spec["observations"]["sha256"],
            "evidence_ids": [observation_id],
            "manifest_sha256": spec["manifest"]["sha256"],
            "record_id": observation_id,
            "release_id": spec["release_id"],
            "source_entity_id": None,
            "source_license": "CC-BY-4.0",
            "source_retrieved_at": observation.get("retrieved_at"),
            "source_roots": ["ireland_national_planning_applications"],
            "source_url": (
                "https://data.gov.ie/en_GB/dataset/irishplanningapplications1"
            ),
        },
        "source_evidence": [
            {
                "evidence_id": observation_id,
                "evidence_type": "official_planning_application_observation",
                "license": dict(observation.get("license") or {}),
                "planning_metadata": planning_metadata,
                "source_record_url": attributes.get("LinkAppDetails"),
            }
        ],
        "tier": "B",
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _england_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .england_planning_data import REVIEW_POLICY, validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    expected_paths = {
        "manifest": release_root / "manifest.json",
        "observations": release_root / "observations.jsonl",
        "phrase_review": release_root / "phrase-review.json",
    }
    if any(
        _path(spec[key], resolved) != expected_path
        for key, expected_path in expected_paths.items()
    ):
        raise ConstructionMasterError("England planning checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    phrase_review = bundle["phrase_review"]
    observations = bundle["observations"]
    rights = assessment.get("rights_assessment")
    if (
        assessment.get("release_id") != spec.get("release_id")
        or not isinstance(rights, Mapping)
        or rights.get("rights_gate_passed") is not True
        or rights.get("dataset_license") != "Open Government Licence v3.0"
        or rights.get("dataset_attribution_statement")
        != "© Crown copyright and database right 2026"
        or len(observations) != 4
    ):
        raise ConstructionMasterError("England planning release boundary changed")

    direct: list[dict[str, Any]] = []
    context_only: list[dict[str, Any]] = []
    for observation in observations:
        context = observation.get("context_assessment")
        if (
            not isinstance(context, Mapping)
            or observation.get("record_type")
            != "planning_application_observation"
            or observation.get("review_only") is not True
            or observation.get("auto_merge") is not False
            or observation.get("promotion_boundaries") != REVIEW_POLICY
            or not isinstance(observation.get("source_attributes"), Mapping)
            or not isinstance(observation.get("provider"), Mapping)
        ):
            raise ConstructionMasterError(
                "England planning observation safeguards changed"
            )
        classification = context.get("classification")
        if classification == "direct_data_centre_scope":
            direct.append(observation)
        elif classification == "context_only_exclusion":
            context_only.append(observation)
        else:
            raise ConstructionMasterError(
                "England planning context classification changed"
            )
    context_entities = [
        str(item["source_attributes"].get("entity")) for item in context_only
    ]
    optional = phrase_review.get("optional_incremental_outside_explicit")
    if (
        len(direct) != 3
        or len(context_only) != 1
        or context_entities != ["10000057188"]
        or not isinstance(optional, Mapping)
        or optional.get("server room", {}).get("incremental_count") != 3
        or phrase_review.get("optional_observations_added") != 0
    ):
        raise ConstructionMasterError(
            "England direct-scope inclusion or exclusion contract changed"
        )
    return {
        "assessment": assessment,
        "direct_observations": direct,
        "summary": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "context_only_entity_ids_excluded": context_entities,
            "context_only_exact_phrase_rows_excluded": len(context_only),
            "direct_scope_rows_included": len(direct),
            "exact_phrase_rows_assessed": len(observations),
            "optional_server_room_rows_excluded": 3,
            "rights": {
                "attribution": rights["dataset_attribution_statement"],
                "license": rights["dataset_license"],
                "license_url": rights["dataset_license_url"],
            },
            "unique_physical_site_count": None,
        },
    }


def _england_row(
    observation: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    observation_id = observation.get("observation_id")
    attributes = observation.get("source_attributes")
    provider = observation.get("provider")
    raw_dates = observation.get("raw_dates")
    raw_status = observation.get("raw_status")
    raw_geometry = observation.get("raw_geometry")
    source_record = observation.get("source")
    point = observation.get("source_point")
    context = observation.get("context_assessment")
    if (
        not isinstance(observation_id, str)
        or not isinstance(attributes, Mapping)
        or not isinstance(provider, Mapping)
        or not isinstance(raw_dates, Mapping)
        or not isinstance(raw_status, Mapping)
        or not isinstance(raw_geometry, Mapping)
        or not isinstance(source_record, Mapping)
        or not isinstance(context, Mapping)
        or context.get("classification") != "direct_data_centre_scope"
    ):
        raise ConstructionMasterError("England planning observation contract changed")
    latitude = None
    longitude = None
    coordinate_method = "official_planning_data_source_point_absent"
    if point is not None:
        if not isinstance(point, Mapping) or point.get("crs") != "EPSG:4326":
            raise ConstructionMasterError("England planning point CRS changed")
        latitude = _float(point.get("latitude"))
        longitude = _float(point.get("longitude"))
        if latitude is None or longitude is None:
            raise ConstructionMasterError("England planning point is incomplete")
        coordinate_method = "official_planning_data_point_epsg4326"
    first_date, last_date = _date_bounds(raw_dates.values())
    reference = attributes.get("reference")
    planning_metadata = {
        "auto_merge": observation.get("auto_merge"),
        "context_assessment": dict(context),
        "matched_terms": list(observation.get("matched_terms") or []),
        "provider": dict(provider),
        "raw_dates": dict(raw_dates),
        "raw_description": observation.get("raw_description"),
        "raw_geometry": dict(raw_geometry),
        "raw_status": dict(raw_status),
        "review_only": observation.get("review_only"),
        "source_attributes": dict(attributes),
        "source_point": None if point is None else dict(point),
        "source_record": dict(source_record),
        "source_status_fields_are_planning_process_only": True,
    }
    rights = assessment["rights_assessment"]
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "construction": {
            "confidence": None,
            "method": "planning_application_is_not_construction_or_operation_evidence",
            "source_supported": False,
            "verification_status": (
                "official_planning_process_observation_not_construction_verified"
            ),
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": (
                "planning_process_observation_does_not_establish_facility_identity_"
                "lifecycle_construction_operation_type_capacity_power_energy_pue_"
                "workload_or_unique_site"
            ),
            "label": "included_official_england_planning_review_lead_only",
            "unique_site_counted": False,
        },
        "entity": {
            "address": attributes.get("address-text"),
            "coordinate_method": coordinate_method,
            "country": "England",
            "country_iso_a2": "GB",
            "country_iso_a3": "GBR",
            "kind": "planning_application_observation",
            "latitude": latitude,
            "longitude": longitude,
            "name": (
                f"England planning application {reference}"
                if reference
                else f"England planning observation {observation_id}"
            ),
        },
        "evidence_scope": ENGLAND_OBSERVATION_KIND,
        "first_evidence_date": first_date,
        "fusion_overlay": None,
        "identity": {
            "confidence": None,
            "status": "planning_observation_not_resolved_to_unique_facility",
        },
        "last_evidence_date": last_date,
        "lifecycle": {
            "normalized_status": "planning_application_review_lead",
            "reported_status": None,
            "reported_status_date": None,
        },
        "observation_kind": ENGLAND_OBSERVATION_KIND,
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id(
            ENGLAND_OBSERVATION_KIND, str(spec["artifact_id"]), observation_id
        ),
        "satellite_links": [],
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["observations"]["path"],
            "artifact_sha256": spec["observations"]["sha256"],
            "evidence_ids": [observation_id],
            "manifest_sha256": spec["manifest"]["sha256"],
            "record_id": observation_id,
            "release_id": spec["release_id"],
            "source_entity_id": None,
            "source_license": "Open Government Licence v3.0",
            "source_retrieved_at": assessment.get("assessed_at"),
            "source_roots": ["england_planning_data"],
            "source_url": (
                "https://www.planning.data.gov.uk/dataset/planning-application"
            ),
        },
        "source_evidence": [
            {
                "evidence_id": observation_id,
                "evidence_type": (
                    "official_england_planning_application_observation"
                ),
                "license": {
                    "attribution": rights["dataset_attribution_statement"],
                    "name": rights["dataset_license"],
                    "url": rights["dataset_license_url"],
                },
                "planning_metadata": planning_metadata,
                "source_record_url": source_record.get("entity_url"),
            }
        ],
        "tier": "B",
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _validate_england_output_row(row: Mapping[str, Any]) -> None:
    entity = row.get("entity")
    identity = row.get("identity")
    lifecycle = row.get("lifecycle")
    source = row.get("source")
    evidence = row.get("source_evidence")
    if (
        row.get("evidence_scope") != ENGLAND_OBSERVATION_KIND
        or not isinstance(entity, Mapping)
        or entity.get("kind") != "planning_application_observation"
        or not isinstance(identity, Mapping)
        or identity.get("confidence") is not None
        or identity.get("status")
        != "planning_observation_not_resolved_to_unique_facility"
        or lifecycle
        != {
            "normalized_status": "planning_application_review_lead",
            "reported_status": None,
            "reported_status_date": None,
        }
        or row.get("capacity_observations") != []
        or row.get("annual_energy_observations") != []
        or row.get("pue_observations") != []
        or row.get("untyped_capacity_statements") != []
        or row.get("operating_model_observation") is not None
        or row.get("workload_observations") != []
        or row.get("satellite_links") != []
        or row.get("resolution_advisories") != []
        or row.get("fusion_overlay") is not None
        or not isinstance(source, Mapping)
        or source.get("source_entity_id") is not None
        or source.get("source_license") != "Open Government Licence v3.0"
        or source.get("source_roots") != ["england_planning_data"]
        or not isinstance(evidence, list)
        or len(evidence) != 1
        or not isinstance(evidence[0], Mapping)
    ):
        raise ConstructionMasterError("England planning row was promoted")
    license_record = evidence[0].get("license")
    planning_metadata = evidence[0].get("planning_metadata")
    if (
        license_record
        != {
            "attribution": "© Crown copyright and database right 2026",
            "name": "Open Government Licence v3.0",
            "url": (
                "https://www.nationalarchives.gov.uk/doc/"
                "open-government-licence/version/3/"
            ),
        }
        or not isinstance(planning_metadata, Mapping)
        or planning_metadata.get("auto_merge") is not False
        or planning_metadata.get("review_only") is not True
        or planning_metadata.get("source_status_fields_are_planning_process_only")
        is not True
        or planning_metadata.get("context_assessment", {}).get("classification")
        != "direct_data_centre_scope"
        or not isinstance(planning_metadata.get("source_attributes"), Mapping)
        or not isinstance(planning_metadata.get("provider"), Mapping)
        or planning_metadata.get("raw_description")
        != planning_metadata["source_attributes"].get("description")
        or not isinstance(planning_metadata.get("raw_status"), Mapping)
        or not isinstance(planning_metadata.get("raw_dates"), Mapping)
        or not isinstance(planning_metadata.get("raw_geometry"), Mapping)
    ):
        raise ConstructionMasterError(
            "England description, provider, rights, status, date, or geometry lineage changed"
        )


def _official_planning_review_row(
    *,
    observation_kind: str,
    spec: Mapping[str, Any],
    record_id: str,
    entity: Mapping[str, Any],
    normalized_status: str,
    reported_status: str | None,
    reported_status_date: str | None,
    first_evidence_date: str | None,
    last_evidence_date: str | None,
    construction_method: str,
    source_license: str,
    source_retrieved_at: str | None,
    source_roots: Sequence[str],
    source_url: str,
    source_evidence: Mapping[str, Any],
    untyped_capacity_statements: Sequence[Mapping[str, Any]] = (),
    workload_observations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "construction": {
            "confidence": None,
            "method": construction_method,
            "source_supported": False,
            "verification_status": (
                "official_process_observation_not_construction_verified"
            ),
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": (
                "official_process_record_does_not_establish_physical_lifecycle_or_operation"
            ),
            "label": "included_official_planning_review_observation_only",
            "unique_site_counted": False,
        },
        "entity": dict(entity),
        "evidence_scope": observation_kind,
        "first_evidence_date": first_evidence_date,
        "fusion_overlay": None,
        "identity": {
            "confidence": None,
            "status": "planning_observation_not_resolved_to_unique_facility",
        },
        "last_evidence_date": last_evidence_date,
        "lifecycle": {
            "normalized_status": normalized_status,
            "reported_status": reported_status,
            "reported_status_date": reported_status_date,
        },
        "observation_kind": observation_kind,
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id(observation_kind, str(spec["artifact_id"]), record_id),
        "satellite_links": [],
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["observations"]["path"],
            "artifact_sha256": spec["observations"]["sha256"],
            "evidence_ids": [record_id],
            "manifest_sha256": spec["manifest"]["sha256"],
            "record_id": record_id,
            "release_id": spec["release_id"],
            "source_entity_id": None,
            "source_license": source_license,
            "source_retrieved_at": source_retrieved_at,
            "source_roots": list(source_roots),
            "source_url": source_url,
        },
        "source_evidence": [dict(source_evidence)],
        "tier": "B",
        "untyped_capacity_statements": [
            dict(item) for item in untyped_capacity_statements
        ],
        "workload_observations": [dict(item) for item in workload_observations],
    }


def _nsw_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .nsw_major_projects import validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    if (
        _path(spec["manifest"], resolved) != release_root / "manifest.json"
        or _path(spec["observations"], resolved)
        != release_root / "active-planning-observations.jsonl"
    ):
        raise ConstructionMasterError("NSW planning checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    observations = bundle["active_observations"]
    if (
        assessment.get("release_id") != spec.get("release_id")
        or assessment.get("atlas_decision", {}).get(
            "planning_observations_publication_eligible"
        )
        is not True
        or assessment.get("atlas_decision", {}).get(
            "construction_status_promotion_permitted"
        )
        is not False
        or assessment.get("atlas_decision", {}).get(
            "typed_power_or_energy_promotion_permitted"
        )
        is not False
        or assessment.get("coverage_assessment", {}).get("active_detail_rows")
        != 22
        or assessment.get("coverage_assessment", {}).get(
            "unique_physical_site_count"
        )
        is not None
    ):
        raise ConstructionMasterError("NSW planning publication boundary changed")
    observation_ids: set[str] = set()
    untyped_statement_count = 0
    for observation in observations:
        observation_id = observation.get("observation_id")
        detail = observation.get("detail_metadata")
        source = observation.get("source")
        if (
            not isinstance(observation_id, str)
            or observation_id in observation_ids
            or observation.get("evidence_scope")
            != assessment.get("inference_policy")
            or not isinstance(detail, Mapping)
            or not isinstance(detail.get("coordinates"), Mapping)
            or detail["coordinates"].get("crs") != "EPSG:4326"
            or not isinstance(detail.get("power_statements"), list)
            or not isinstance(source, Mapping)
            or not isinstance(source.get("url"), str)
            or observation.get("selection_workflow_stage_exact")
            not in {
                "Assessment",
                "Exhibition",
                "Prepare EIS",
                "Response to Submissions",
            }
        ):
            raise ConstructionMasterError("NSW planning observation contract changed")
        observation_ids.add(observation_id)
        untyped_statement_count += len(detail["power_statements"])
    if len(observations) != 22 or untyped_statement_count != 10:
        raise ConstructionMasterError("NSW planning row or untyped statement count changed")
    return {
        "assessment": assessment,
        "observations": observations,
        "summary": {
            "observation_rows": 22,
            "portal_process_stages_are_lifecycle": False,
            "untyped_power_statements": 10,
            "unique_physical_site_count": None,
        },
    }


def _nsw_row(
    observation: Mapping[str, Any], *, spec: Mapping[str, Any], assessment: Mapping[str, Any]
) -> dict[str, Any]:
    observation_id = str(observation["observation_id"])
    detail = observation["detail_metadata"]
    coordinates = detail["coordinates"]
    source = observation["source"]
    first_date, last_date = _date_bounds([source.get("fetched_at")])
    return _official_planning_review_row(
        observation_kind=NSW_OBSERVATION_KIND,
        spec=spec,
        record_id=observation_id,
        entity={
            "address": observation.get("address"),
            "coordinate_method": (
                "official_nsw_detail_page_point_review_only"
            ),
            "country": "Australia",
            "country_iso_a2": "AU",
            "country_iso_a3": "AUS",
            "kind": "planning_application_observation",
            "latitude": _float(coordinates.get("latitude")),
            "longitude": _float(coordinates.get("longitude")),
            "name": observation.get("title"),
        },
        normalized_status="planning_application_review_lead",
        reported_status=None,
        reported_status_date=None,
        first_evidence_date=first_date,
        last_evidence_date=last_date,
        construction_method=(
            "nsw_major_projects_workflow_is_not_physical_lifecycle_evidence"
        ),
        source_license="CC-BY-4.0",
        source_retrieved_at=assessment.get("assessed_at"),
        source_roots=["nsw_major_projects"],
        source_url=str(source["url"]),
        source_evidence={
            "evidence_id": observation_id,
            "evidence_type": "official_nsw_major_projects_planning_observation",
            "license": {
                "attribution": assessment["rights_assessment"][
                    "attribution_text"
                ],
                "name": assessment["rights_assessment"]["license_name"],
                "url": assessment["rights_assessment"]["license_url"],
            },
            "planning_metadata": {
                "portal_process_fields_are_physical_lifecycle": False,
                "source_observation": dict(observation),
                "typed_power_or_energy_promoted": False,
            },
        },
        untyped_capacity_statements=detail["power_statements"],
    )


def _netherlands_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .netherlands_koop import validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    if (
        _path(spec["manifest"], resolved) != release_root / "manifest.json"
        or _path(spec["observations"], resolved)
        != release_root / "observations.jsonl"
    ):
        raise ConstructionMasterError("Netherlands KOOP checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    direct = [
        observation
        for observation in bundle["observations"]
        if observation.get("classification", {}).get("label")
        == "direct_project_build_expansion_candidate"
    ]
    excluded = [
        observation
        for observation in bundle["observations"]
        if observation.get("classification", {}).get("label")
        == "ancillary_or_context_exclusion"
    ]
    if (
        assessment.get("release_id") != spec.get("release_id")
        or assessment.get("classification_counts")
        != {
            "ancillary_or_context_exclusion": 7,
            "direct_project_build_expansion_candidate": 13,
        }
        or assessment.get("rights_assessment", {}).get(
            "rights_gate_passed_for_retained_scope"
        )
        is not True
        or len(direct) != 13
        or len(excluded) != 7
        or bundle["relationships"].get("accepted_relationships") != 0
        or bundle["relationships"].get("automatic_merges") != 0
        or bundle["relationships"].get("unique_physical_site_count") is not None
    ):
        raise ConstructionMasterError("Netherlands KOOP selection boundary changed")
    for observation in direct:
        metrics = observation.get("facility_metrics")
        if (
            observation.get("review_only") is not True
            or observation.get("construction")
            != {"source_supported": False, "verified": False}
            or observation.get("permit_process", {}).get(
                "facility_lifecycle_status_promoted"
            )
            is not False
            or not isinstance(metrics, Mapping)
            or any(
                metrics.get(key) != []
                for key in (
                    "annual_energy_observations",
                    "capacity_observations",
                    "power_observations",
                    "pue_observations",
                    "untyped_context_statements",
                    "workload_observations",
                )
            )
        ):
            raise ConstructionMasterError("Netherlands KOOP row was promoted")
    return {
        "assessment": assessment,
        "direct_observations": direct,
        "summary": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "context_rows_excluded": 7,
            "direct_review_rows": 13,
            "permit_process_stages_are_lifecycle": False,
            "unique_physical_site_count": None,
        },
    }


def _netherlands_coordinates(
    metadata: Mapping[str, Any],
) -> tuple[float | None, float | None, str | None]:
    points: set[tuple[float, float]] = set()
    markers = metadata.get("geographic_markers")
    if isinstance(markers, list):
        for marker in markers:
            if not isinstance(marker, Mapping):
                continue
            location_points = marker.get("location_points")
            if not isinstance(location_points, list):
                continue
            for point in location_points:
                if not isinstance(point, Mapping) or point.get("crs") != "ETRS89":
                    continue
                latitude = _float(point.get("latitude"))
                longitude = _float(point.get("longitude"))
                if latitude is not None and longitude is not None:
                    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                        raise ConstructionMasterError(
                            "Netherlands KOOP coordinate is out of range"
                        )
                    points.add((latitude, longitude))
    if not points:
        return None, None, None
    ordered = sorted(points)
    if len(ordered) == 1:
        latitude, longitude = ordered[0]
        return latitude, longitude, "official_koop_single_unambiguous_etrs89_point"

    def distance_metres(left: tuple[float, float], right: tuple[float, float]) -> float:
        left_latitude, left_longitude = map(math.radians, left)
        right_latitude, right_longitude = map(math.radians, right)
        latitude_delta = right_latitude - left_latitude
        longitude_delta = right_longitude - left_longitude
        haversine = (
            math.sin(latitude_delta / 2) ** 2
            + math.cos(left_latitude)
            * math.cos(right_latitude)
            * math.sin(longitude_delta / 2) ** 2
        )
        return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(haversine)))

    maximum_span_metres = max(
        distance_metres(left, right)
        for index, left in enumerate(ordered)
        for right in ordered[index + 1 :]
    )
    if maximum_span_metres > 100:
        return None, None, None
    return (
        sum(point[0] for point in ordered) / len(ordered),
        sum(point[1] for point in ordered) / len(ordered),
        "official_koop_mean_of_nearby_etrs89_points_review_only",
    )


def _netherlands_row(
    observation: Mapping[str, Any], *, spec: Mapping[str, Any], assessment: Mapping[str, Any]
) -> dict[str, Any]:
    observation_id = str(observation["observation_id"])
    metadata = observation["metadata"]
    latitude, longitude, coordinate_method = _netherlands_coordinates(metadata)
    first_date, last_date = _date_bounds(
        [metadata.get("available"), metadata.get("date"), metadata.get("modified")]
    )
    return _official_planning_review_row(
        observation_kind=NETHERLANDS_OBSERVATION_KIND,
        spec=spec,
        record_id=observation_id,
        entity={
            "address": None,
            "coordinate_method": coordinate_method,
            "country": "Netherlands",
            "country_iso_a2": "NL",
            "country_iso_a3": "NLD",
            "kind": "permit_publication_observation",
            "latitude": latitude,
            "longitude": longitude,
            "name": observation.get("project_review_label"),
        },
        normalized_status="permit_process_review_lead",
        reported_status=None,
        reported_status_date=None,
        first_evidence_date=first_date,
        last_evidence_date=last_date,
        construction_method="koop_permit_process_is_not_physical_lifecycle_evidence",
        source_license="CC0-1.0",
        source_retrieved_at=assessment.get("assessed_at"),
        source_roots=["netherlands_koop_official_publications"],
        source_url=str(metadata["preferred_url"]),
        source_evidence={
            "evidence_id": observation_id,
            "evidence_type": "official_netherlands_permit_publication_observation",
            "license": {
                "name": assessment["rights_assessment"]["dataset_catalog_license"],
                "scope": (
                    "official metadata and selected official text; express notices control"
                ),
                "url": assessment["rights_assessment"]["cc0_reference_url"],
            },
            "permit_metadata": {
                "permit_stage_is_physical_lifecycle": False,
                "source_observation": dict(observation),
            },
        },
    )


def _new_zealand_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .new_zealand_fast_track import validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    if (
        _path(spec["manifest"], resolved) != release_root / "manifest.json"
        or _path(spec["observations"], resolved)
        != release_root / "observations.jsonl"
    ):
        raise ConstructionMasterError("New Zealand checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    observations = bundle["observations"]
    classifications = Counter(
        str(observation.get("candidate_classification"))
        for observation in observations
    )
    if (
        assessment.get("release_id") != spec.get("release_id")
        or assessment.get("rights_assessment", {}).get(
            "rights_gate_passed_for_retained_scope"
        )
        is not True
        or assessment.get("coverage", {}).get("coverage_complete") is not False
        or assessment.get("coverage", {}).get("unique_physical_site_count")
        is not None
        or classifications
        != Counter(
            {
                "direct_data_centre_project_candidate": 2,
                "prior_related_planning_observation": 1,
            }
        )
        or bundle["relationships"].get("accepted_relationships") != 0
        or bundle["relationships"].get("automatic_merges") != 0
    ):
        raise ConstructionMasterError("New Zealand selection boundary changed")
    for observation in observations:
        characterisation = observation.get("data_centre_characterisation")
        metrics = observation.get("facility_metrics")
        if (
            observation.get("review_only") is not True
            or observation.get("physical_status", {}).get("label") != "proposed"
            or observation.get("physical_status", {}).get(
                "construction_source_supported"
            )
            is not False
            or observation.get("physical_status", {}).get(
                "operation_source_supported"
            )
            is not False
            or observation.get("planning_process", {}).get(
                "facility_lifecycle_status_promoted"
            )
            is not False
            or not isinstance(characterisation, Mapping)
            or characterisation.get("operationally_verified") is not False
            or not isinstance(metrics, Mapping)
            or any(
                metrics.get(key) != []
                for key in (
                    "annual_energy_observations",
                    "capacity_observations",
                    "power_observations",
                    "pue_observations",
                )
            )
        ):
            raise ConstructionMasterError("New Zealand row was promoted")
    return {
        "assessment": assessment,
        "observations": observations,
        "summary": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "prior_related_observations": 1,
            "project_candidate_observations": 2,
            "unique_physical_site_count": None,
        },
    }


def _new_zealand_row(
    observation: Mapping[str, Any], *, spec: Mapping[str, Any], assessment: Mapping[str, Any]
) -> dict[str, Any]:
    observation_id = str(observation["observation_id"])
    project = observation["project"]
    source = observation["source"]
    process = observation["planning_process"]
    characterisation = observation["data_centre_characterisation"]
    first_date, last_date = _date_bounds(
        event.get("date")
        for event in process.get("events", [])
        if isinstance(event, Mapping)
    )
    declared_workload = characterisation.get("declared_workload")
    workload_observations = (
        [
            {
                "operationally_verified": False,
                "scope": characterisation.get("scope"),
                "stage": "proposed",
                "workload": declared_workload,
            }
        ]
        if declared_workload is not None
        else []
    )
    fasttrack = source.get("artifact_id") == "fasttrack_auckland_stage2"
    return _official_planning_review_row(
        observation_kind=NEW_ZEALAND_OBSERVATION_KIND,
        spec=spec,
        record_id=observation_id,
        entity={
            "address": project.get("location"),
            "coordinate_method": None,
            "country": "New Zealand",
            "country_iso_a2": "NZ",
            "country_iso_a3": "NZL",
            "kind": "planning_application_observation",
            "latitude": None,
            "longitude": None,
            "name": project.get("name"),
        },
        normalized_status="proposed_review_lead",
        reported_status="proposed",
        reported_status_date=None,
        first_evidence_date=first_date,
        last_evidence_date=last_date,
        construction_method=(
            "new_zealand_fast_track_process_is_not_construction_evidence"
        ),
        source_license="CC-BY-SA-4.0" if fasttrack else "CC-BY-4.0",
        source_retrieved_at=assessment.get("assessed_at"),
        source_roots=["new_zealand_fast_track"],
        source_url=str(source["url"]),
        source_evidence={
            "evidence_id": observation_id,
            "evidence_type": "official_new_zealand_fast_track_observation",
            "license": {
                "name": (
                    assessment["rights_assessment"]["fasttrack_license"]
                    if fasttrack
                    else assessment["rights_assessment"]["mfe_license"]
                ),
                "scope": "official page text only",
                "url": (
                    assessment["rights_assessment"]["fasttrack_license_url"]
                    if fasttrack
                    else assessment["rights_assessment"]["mfe_license_url"]
                ),
            },
            "planning_metadata": {
                "facility_lifecycle_from_process_stage": False,
                "land_area_promoted_to_data_centre_area_or_power": False,
                "source_observation": dict(observation),
            },
        },
        workload_observations=workload_observations,
    )


def _france_context(
    spec: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    from .france_igedd_ae import validate_release_bundle

    assessment_path = _path(spec["assessment"], resolved)
    release_root = assessment_path.parent
    expected_paths = {
        "assessment": release_root / "assessment.json",
        "definition": release_root / "definition.json",
        "manifest": release_root / "manifest.json",
        "observations": release_root / "observations.jsonl",
        "schema": release_root / "schema.json",
    }
    if any(_path(spec[name], resolved) != path for name, path in expected_paths.items()):
        raise ConstructionMasterError("France IGEDD checkpoints cross releases")
    bundle = validate_release_bundle(release_root)
    assessment = bundle["assessment"]
    observations = bundle["observations"]
    decision = assessment.get("atlas_decision", {})
    rights = assessment.get("rights_assessment", {})
    if (
        assessment.get("release_id") != spec.get("release_id")
        or decision.get("derived_rows_publication_eligible") is not True
        or decision.get("pdf_redistribution_permitted_by_this_release") is not False
        or rights.get("derived_factual_rows_publication_eligible") is not True
        or rights.get("document_redistribution_in_release") is not False
        or assessment.get("classification_counts")
        != {
            "ancillary_grid_connection_follow_up": 1,
            "direct_data_centre_project": 3,
        }
        or any(
            value is not False
            for value in assessment.get("inference_boundary", {}).values()
        )
        or len(observations) != 4
    ):
        raise ConstructionMasterError("France IGEDD publication boundary changed")
    classifications = Counter()
    metric_types = Counter()
    observation_ids: set[str] = set()
    relationship_evidence = 0
    for observation in observations:
        observation_id = observation.get("observation_id")
        classification = observation.get("classification")
        metrics = observation.get("metrics")
        environmental_review = observation.get("environmental_review")
        if (
            not isinstance(observation_id, str)
            or observation_id in observation_ids
            or classification
            not in {
                "ancillary_grid_connection_follow_up",
                "direct_data_centre_project",
            }
            or not isinstance(metrics, list)
            or any(not isinstance(metric, Mapping) for metric in metrics)
            or environmental_review
            != {
                "atlas_lifecycle_status": None,
                "construction_verified": False,
                "environmental_opinion_is_development_consent": False,
                "environmental_opinion_is_physical_construction_evidence": False,
                "operation_verified": False,
                "source_process_status": "environmental_authority_opinion_issued",
            }
            or observation.get("atlas_data_centre_type") is not None
        ):
            raise ConstructionMasterError("France IGEDD observation contract changed")
        observation_ids.add(observation_id)
        classifications[str(classification)] += 1
        metric_types.update(str(metric.get("metric_type")) for metric in metrics)
        related_id = observation.get("related_direct_observation_id")
        if classification == "ancillary_grid_connection_follow_up":
            if related_id != "fr-igedd-ae-2025-058":
                raise ConstructionMasterError("France IGEDD relationship changed")
            relationship_evidence += 1
        elif related_id is not None:
            raise ConstructionMasterError("France IGEDD direct row gained a relationship")
    expected_metric_types = {
        "backup_generation_electrical_capacity": 2,
        "backup_generation_thermal_capacity": 3,
        "battery_maximum_recharge_power": 1,
        "it_power_capacity": 2,
        "projected_annual_site_electricity_consumption": 1,
        "projected_full_load_annual_electricity_consumption": 1,
        "requested_grid_connection_power": 1,
        "target_pue": 1,
        "ups_and_battery_power": 1,
    }
    if (
        classifications != Counter(assessment["classification_counts"])
        or dict(sorted(metric_types.items())) != expected_metric_types
        or relationship_evidence != 1
    ):
        raise ConstructionMasterError("France IGEDD row or metric arithmetic changed")
    return {
        "assessment": assessment,
        "observations": observations,
        "summary": {
            "automatic_merges": 0,
            "classification_counts": dict(sorted(classifications.items())),
            "construction_arithmetic_rows": 0,
            "derived_rows_publication_eligible": True,
            "lifecycle_status_coordinate_promotions": 0,
            "metric_observations": sum(metric_types.values()),
            "metric_types_exact": expected_metric_types,
            "observation_rows": 4,
            "relationship_evidence_records": relationship_evidence,
            "unique_physical_site_count": None,
        },
    }


def _france_metric_buckets(
    observation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    capacity: list[dict[str, Any]] = []
    annual: list[dict[str, Any]] = []
    pue: list[dict[str, Any]] = []
    annual_types = {
        "projected_annual_site_electricity_consumption",
        "projected_full_load_annual_electricity_consumption",
    }
    for raw in observation["metrics"]:
        metric = dict(raw)
        metric_type = metric.get("metric_type")
        if metric_type in annual_types:
            annual.append(metric)
        elif metric_type == "target_pue":
            pue.append(metric)
        else:
            capacity.append(metric)
    return capacity, annual, pue


def _france_row(
    observation: Mapping[str, Any], *, spec: Mapping[str, Any], assessment: Mapping[str, Any]
) -> dict[str, Any]:
    observation_id = str(observation["observation_id"])
    classification = str(observation["classification"])
    capacity, annual, pue = _france_metric_buckets(observation)
    related_id = observation.get("related_direct_observation_id")
    relationship = (
        {
            "advisory_only": True,
            "automatic_merge_permitted": False,
            "relationship_type": "related_direct_observation",
            "related_observation_id": related_id,
            "source_stated": True,
        }
        if isinstance(related_id, str)
        else None
    )
    rights = assessment["rights_assessment"]
    return {
        "annual_energy_observations": annual,
        "capacity_observations": capacity,
        "construction": {
            "confidence": None,
            "method": "environmental_authority_opinion_is_not_physical_construction_evidence",
            "source_supported": False,
            "verification_status": "official_environmental_review_not_construction_verified",
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": (
                "ancillary_grid_connection_opinion_is_relationship_evidence_only"
                if classification == "ancillary_grid_connection_follow_up"
                else "environmental_opinion_does_not_establish_physical_lifecycle_or_operation"
            ),
            "label": (
                "included_ancillary_grid_connection_follow_up_evidence_only"
                if classification == "ancillary_grid_connection_follow_up"
                else "included_official_environmental_opinion_review_observation_only"
            ),
            "unique_site_counted": False,
        },
        "entity": {
            "address": observation.get("location"),
            "coordinate_method": None,
            "country": "France",
            "country_iso_a2": "FR",
            "country_iso_a3": "FRA",
            "kind": "environmental_opinion_observation",
            "latitude": None,
            "longitude": None,
            "name": observation.get("project_name"),
        },
        "evidence_scope": FRANCE_OBSERVATION_KIND,
        "first_evidence_date": observation.get("opinion_date"),
        "fusion_overlay": None,
        "identity": {
            "confidence": None,
            "status": "environmental_opinion_observation_not_resolved_to_unique_facility",
        },
        "last_evidence_date": observation.get("opinion_date"),
        "lifecycle": {
            "normalized_status": None,
            "reported_status": None,
            "reported_status_date": None,
        },
        "observation_kind": FRANCE_OBSERVATION_KIND,
        "operating_model_observation": None,
        "pue_observations": pue,
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id(FRANCE_OBSERVATION_KIND, str(spec["artifact_id"]), observation_id),
        "satellite_links": [],
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["observations"]["path"],
            "artifact_sha256": spec["observations"]["sha256"],
            "evidence_ids": [observation_id],
            "manifest_sha256": spec["manifest"]["sha256"],
            "record_id": observation_id,
            "release_id": spec["release_id"],
            "source_entity_id": None,
            "source_license": rights["license_name"],
            "source_retrieved_at": assessment.get("assessed_at"),
            "source_roots": ["france_igedd_ae"],
            "source_url": observation["document_url"],
        },
        "source_evidence": [
            {
                "environmental_review_metadata": {
                    "automatic_merge": False,
                    "classification": classification,
                    "source_observation": dict(observation),
                    "source_process_status_promoted_to_lifecycle": False,
                    "typed_metric_semantics_preserved_without_conversion": True,
                    "unique_site_counted": False,
                    "within_source_relationship": relationship,
                },
                "evidence_id": observation_id,
                "evidence_type": "official_france_igedd_environmental_opinion_observation",
                "license": {
                    "name": rights["license_name"],
                    "url": rights["license_url"],
                },
            }
        ],
        "tier": "B",
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _validate_france_output_row(row: Mapping[str, Any]) -> None:
    source = row.get("source")
    evidence = row.get("source_evidence")
    entity = row.get("entity")
    construction = row.get("construction")
    identity = row.get("identity")
    if (
        row.get("evidence_scope") != FRANCE_OBSERVATION_KIND
        or not isinstance(source, Mapping)
        or source.get("artifact_id") != FRANCE_ARTIFACT_ID
        or source.get("release_id") != FRANCE_ARTIFACT_ID
        or source.get("source_entity_id") is not None
        or source.get("source_license")
        != "Licence Ouverte / Open Licence Etalab 2.0"
        or source.get("source_roots") != ["france_igedd_ae"]
        or not isinstance(entity, Mapping)
        or entity.get("kind") != "environmental_opinion_observation"
        or entity.get("country") != "France"
        or entity.get("country_iso_a2") != "FR"
        or entity.get("country_iso_a3") != "FRA"
        or entity.get("latitude") is not None
        or entity.get("longitude") is not None
        or entity.get("coordinate_method") is not None
        or row.get("lifecycle")
        != {
            "normalized_status": None,
            "reported_status": None,
            "reported_status_date": None,
        }
        or construction
        != {
            "confidence": None,
            "method": "environmental_authority_opinion_is_not_physical_construction_evidence",
            "source_supported": False,
            "verification_status": "official_environmental_review_not_construction_verified",
            "verified": False,
        }
        or identity
        != {
            "confidence": None,
            "status": "environmental_opinion_observation_not_resolved_to_unique_facility",
        }
        or row.get("operating_model_observation") is not None
        or row.get("workload_observations") != []
        or row.get("untyped_capacity_statements") != []
        or row.get("satellite_links") != []
        or row.get("resolution_advisories") != []
        or row.get("fusion_overlay") is not None
        or not isinstance(evidence, list)
        or len(evidence) != 1
        or not isinstance(evidence[0], Mapping)
    ):
        raise ConstructionMasterError("France IGEDD row was promoted")
    metadata = evidence[0].get("environmental_review_metadata")
    if not isinstance(metadata, Mapping):
        raise ConstructionMasterError("France IGEDD evidence metadata changed")
    observation = metadata.get("source_observation")
    classification = metadata.get("classification")
    if (
        not isinstance(observation, Mapping)
        or classification != observation.get("classification")
        or classification
        not in {
            "ancillary_grid_connection_follow_up",
            "direct_data_centre_project",
        }
        or metadata.get("automatic_merge") is not False
        or metadata.get("unique_site_counted") is not False
        or metadata.get("source_process_status_promoted_to_lifecycle") is not False
        or metadata.get("typed_metric_semantics_preserved_without_conversion")
        is not True
        or observation.get("atlas_data_centre_type") is not None
        or observation.get("environmental_review", {}).get(
            "atlas_lifecycle_status"
        )
        is not None
        or observation.get("environmental_review", {}).get(
            "construction_verified"
        )
        is not False
        or observation.get("environmental_review", {}).get("operation_verified")
        is not False
    ):
        raise ConstructionMasterError("France IGEDD evidence boundary changed")
    expected_capacity, expected_annual, expected_pue = _france_metric_buckets(
        observation
    )
    if (
        row.get("capacity_observations") != expected_capacity
        or row.get("annual_energy_observations") != expected_annual
        or row.get("pue_observations") != expected_pue
    ):
        raise ConstructionMasterError("France IGEDD metric semantics changed")
    non_it_types = {
        "backup_generation_electrical_capacity",
        "backup_generation_thermal_capacity",
        "battery_maximum_recharge_power",
        "requested_grid_connection_power",
        "ups_and_battery_power",
    }
    if any(
        metric.get("metric_type") not in {"it_power_capacity", *non_it_types}
        for metric in expected_capacity
    ):
        raise ConstructionMasterError("France IGEDD capacity type changed")
    relationship = metadata.get("within_source_relationship")
    related_id = observation.get("related_direct_observation_id")
    expected_relationship = (
        {
            "advisory_only": True,
            "automatic_merge_permitted": False,
            "relationship_type": "related_direct_observation",
            "related_observation_id": related_id,
            "source_stated": True,
        }
        if isinstance(related_id, str)
        else None
    )
    if relationship != expected_relationship:
        raise ConstructionMasterError("France IGEDD relationship evidence changed")


def _validate_v4_official_output_row(row: Mapping[str, Any]) -> None:
    observation_kind = row.get("observation_kind")
    source = row.get("source")
    evidence = row.get("source_evidence")
    entity = row.get("entity")
    if (
        row.get("evidence_scope") != observation_kind
        or not isinstance(source, Mapping)
        or source.get("source_entity_id") is not None
        or not isinstance(entity, Mapping)
        or not isinstance(evidence, list)
        or len(evidence) != 1
        or not isinstance(evidence[0], Mapping)
        or row.get("capacity_observations") != []
        or row.get("annual_energy_observations") != []
        or row.get("pue_observations") != []
        or row.get("operating_model_observation") is not None
        or row.get("satellite_links") != []
        or row.get("resolution_advisories") != []
        or row.get("fusion_overlay") is not None
    ):
        raise ConstructionMasterError("v4 official planning row was promoted")

    if observation_kind == NSW_OBSERVATION_KIND:
        metadata = evidence[0].get("planning_metadata", {})
        observation = metadata.get("source_observation", {})
        detail = observation.get("detail_metadata", {})
        if (
            source.get("source_license") != "CC-BY-4.0"
            or source.get("source_roots") != ["nsw_major_projects"]
            or entity.get("kind") != "planning_application_observation"
            or row.get("lifecycle")
            != {
                "normalized_status": "planning_application_review_lead",
                "reported_status": None,
                "reported_status_date": None,
            }
            or row.get("workload_observations") != []
            or row.get("untyped_capacity_statements")
            != detail.get("power_statements")
            or metadata.get("portal_process_fields_are_physical_lifecycle")
            is not False
            or metadata.get("typed_power_or_energy_promoted") is not False
        ):
            raise ConstructionMasterError("NSW planning row was promoted")
        return

    if observation_kind == NETHERLANDS_OBSERVATION_KIND:
        metadata = evidence[0].get("permit_metadata", {})
        observation = metadata.get("source_observation", {})
        if (
            source.get("source_license") != "CC0-1.0"
            or source.get("source_roots")
            != ["netherlands_koop_official_publications"]
            or entity.get("kind") != "permit_publication_observation"
            or row.get("lifecycle")
            != {
                "normalized_status": "permit_process_review_lead",
                "reported_status": None,
                "reported_status_date": None,
            }
            or row.get("untyped_capacity_statements") != []
            or row.get("workload_observations") != []
            or observation.get("classification", {}).get("label")
            != "direct_project_build_expansion_candidate"
            or metadata.get("permit_stage_is_physical_lifecycle") is not False
        ):
            raise ConstructionMasterError("Netherlands KOOP row was promoted")
        return

    if observation_kind != NEW_ZEALAND_OBSERVATION_KIND:
        raise ConstructionMasterError("unsupported v4 official observation kind")
    metadata = evidence[0].get("planning_metadata", {})
    observation = metadata.get("source_observation", {})
    characterisation = observation.get("data_centre_characterisation", {})
    declared_workload = characterisation.get("declared_workload")
    expected_workload = (
        [
            {
                "operationally_verified": False,
                "scope": characterisation.get("scope"),
                "stage": "proposed",
                "workload": declared_workload,
            }
        ]
        if declared_workload is not None
        else []
    )
    if (
        source.get("source_license") not in {"CC-BY-4.0", "CC-BY-SA-4.0"}
        or source.get("source_roots") != ["new_zealand_fast_track"]
        or entity.get("kind") != "planning_application_observation"
        or row.get("lifecycle")
        != {
            "normalized_status": "proposed_review_lead",
            "reported_status": "proposed",
            "reported_status_date": None,
        }
        or row.get("untyped_capacity_statements") != []
        or row.get("workload_observations") != expected_workload
        or characterisation.get("operationally_verified") is not False
        or metadata.get("facility_lifecycle_from_process_stage") is not False
        or metadata.get("land_area_promoted_to_data_centre_area_or_power")
        is not False
    ):
        raise ConstructionMasterError("New Zealand planning row was promoted")


def _tier_a_arithmetic_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"fusion_overlay", "resolution_advisories", "satellite_links"}
    }


def _validate_output_row(row: Mapping[str, Any]) -> None:
    tier = row.get("tier")
    disposition = row.get("disposition")
    construction = row.get("construction")
    if not isinstance(disposition, Mapping) or not isinstance(
        construction, Mapping
    ):
        raise ConstructionMasterError("row safeguards are absent")
    if disposition.get("unique_site_counted") is not False:
        raise ConstructionMasterError("construction master cannot count unique sites")
    if construction.get("verified") is not False:
        raise ConstructionMasterError(
            "construction verification cannot be promoted in this master"
        )
    if tier == "A":
        if (
            row.get("review_only") is not False
            or disposition.get("construction_arithmetic_included") is not True
            or construction.get("source_supported") is not True
        ):
            raise ConstructionMasterError("Tier A arithmetic safeguards changed")
    elif tier in {"B", "C"}:
        if (
            row.get("review_only") is not True
            or disposition.get("construction_arithmetic_included") is not False
            or construction.get("source_supported") is not False
        ):
            raise ConstructionMasterError("review-only row was promoted")
    else:
        raise ConstructionMasterError(f"unsupported construction-master tier: {tier}")

    if row.get("observation_kind") == ENGLAND_OBSERVATION_KIND:
        _validate_england_output_row(row)
        return
    if row.get("observation_kind") == FRANCE_OBSERVATION_KIND:
        _validate_france_output_row(row)
        return
    if row.get("observation_kind") in {
        NSW_OBSERVATION_KIND,
        NETHERLANDS_OBSERVATION_KIND,
        NEW_ZEALAND_OBSERVATION_KIND,
    }:
        _validate_v4_official_output_row(row)
        return
    if row.get("observation_kind") != IRELAND_OBSERVATION_KIND:
        return
    entity = row.get("entity")
    identity = row.get("identity")
    lifecycle = row.get("lifecycle")
    source = row.get("source")
    evidence = row.get("source_evidence")
    if (
        row.get("evidence_scope") != IRELAND_OBSERVATION_KIND
        or not isinstance(entity, Mapping)
        or entity.get("kind") != "planning_application_observation"
        or not isinstance(identity, Mapping)
        or identity.get("confidence") is not None
        or identity.get("status")
        != "planning_observation_not_resolved_to_unique_facility"
        or lifecycle
        != {
            "normalized_status": "planning_application_review_lead",
            "reported_status": None,
            "reported_status_date": None,
        }
        or row.get("capacity_observations") != []
        or row.get("annual_energy_observations") != []
        or row.get("pue_observations") != []
        or row.get("untyped_capacity_statements") != []
        or row.get("operating_model_observation") is not None
        or row.get("workload_observations") != []
        or row.get("satellite_links") != []
        or row.get("resolution_advisories") != []
        or row.get("fusion_overlay") is not None
        or not isinstance(source, Mapping)
        or source.get("source_entity_id") is not None
        or source.get("source_license") != "CC-BY-4.0"
        or source.get("source_roots")
        != ["ireland_national_planning_applications"]
        or not isinstance(evidence, list)
        or len(evidence) != 1
        or not isinstance(evidence[0], Mapping)
    ):
        raise ConstructionMasterError("Ireland planning row was promoted")
    planning_metadata = evidence[0].get("planning_metadata")
    if (
        not isinstance(planning_metadata, Mapping)
        or planning_metadata.get(
            "source_status_fields_are_planning_process_only"
        )
        is not True
        or not isinstance(planning_metadata.get("source_attributes"), Mapping)
        or any(
            field not in planning_metadata["source_attributes"]
            for field in ("PlanningAuthority", "ApplicationStatus", "Decision")
        )
    ):
        raise ConstructionMasterError(
            "Ireland authority, decision, and status must remain planning metadata"
        )


def _geometry_center(geometry: Mapping[str, Any]) -> tuple[float, float]:
    points: list[tuple[float, float]] = []

    def visit(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, list):
            for member in value:
                visit(member)

    visit(geometry.get("coordinates"))
    if not points:
        raise ConstructionMasterError("structural geometry has no coordinates")
    west = min(point[0] for point in points)
    east = max(point[0] for point in points)
    south = min(point[1] for point in points)
    north = max(point[1] for point in points)
    return ((west + east) / 2.0, (south + north) / 2.0)


def _structural_row(
    feature: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    overlay: Mapping[str, Any] | None,
) -> dict[str, Any]:
    candidate_id = feature.get("id")
    properties = feature.get("properties")
    geometry = feature.get("geometry")
    if not isinstance(candidate_id, str) or not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
        raise ConstructionMasterError("structural feature contract changed")
    if properties.get("review_only") is not True or properties.get("data_centre_identity_inferred") is not False:
        raise ConstructionMasterError("structural candidate safeguards changed")
    longitude, latitude = _geometry_center(geometry)
    families = list(properties.get("source_tag_families") or [])
    normalized = (
        "structural_construction_signal"
        if "construction" in families
        else "structural_proposed_signal"
    )
    evidence_id = f"osm-planet:{candidate_id}"
    satellite_links = list((overlay or {}).get("satellite_links", []))
    compact_overlay = (
        {key: value for key, value in overlay.items() if key != "satellite_links"}
        if overlay is not None
        else None
    )
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "construction": {
            "confidence": None,
            "method": "osm_structural_tag_and_geometry_review_signal",
            "source_supported": False,
            "verification_status": "structural_signal_not_verified",
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": "structural_signal_does_not_establish_data_centre_identity_or_lifecycle",
            "label": "included_structural_discovery_candidate_only",
            "unique_site_counted": False,
        },
        "entity": {
            "address": None,
            "coordinate_method": "geometry_bbox_center_review_only",
            "country": None,
            "country_iso_a2": None,
            "country_iso_a3": None,
            "kind": "structural_candidate",
            "latitude": latitude,
            "longitude": longitude,
            "name": f"OpenStreetMap structural candidate {candidate_id}",
        },
        "evidence_scope": "structural_or_cv_discovery_candidate",
        "first_evidence_date": None,
        "fusion_overlay": compact_overlay,
        "identity": {"confidence": None, "status": "data_centre_identity_not_inferred"},
        "last_evidence_date": None,
        "lifecycle": {
            "normalized_status": normalized,
            "reported_status": "construction_signal" if "construction" in families else "proposed_signal",
            "reported_status_date": None,
        },
        "observation_kind": "osm_planet_structural_candidate",
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id("osm_planet_structural_candidate", spec["artifact_id"], candidate_id),
        "satellite_links": satellite_links,
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["data"]["path"],
            "artifact_sha256": spec["data"]["sha256"],
            "evidence_ids": [evidence_id],
            "manifest_sha256": spec["manifest"]["sha256"],
            "record_id": candidate_id,
            "release_id": spec["release_id"],
            "source_entity_id": None,
            "source_license": "ODbL-1.0",
            "source_retrieved_at": None,
            "source_roots": ["openstreetmap"],
            "source_url": properties.get("source_url"),
        },
        "source_evidence": [
            {
                "artifact_sha256": spec["data"]["sha256"],
                "evidence_id": evidence_id,
                "footprint_square_metres": properties.get("footprint_square_metres"),
                "review_reasons": properties.get("review_reasons", []),
                "review_score": properties.get("review_score"),
                "source_tag_families": families,
                "source_tags": properties.get("source_tags", {}),
                "source_url": properties.get("source_url"),
            }
        ],
        "tier": "C",
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _analyst_row(
    spec: Mapping[str, Any],
    resolved: Mapping[str, Path],
    batch_jobs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    report, _ = _json_file(_path(spec["report"], resolved), "imagery report")
    review, _ = _json_file(_path(spec["review"], resolved), "imagery analyst review")
    queue_id = spec["queue_id"]
    if review.get("input_report_sha256") != spec["report"]["sha256"]:
        raise ConstructionMasterError(f"review/report hash mismatch for {queue_id}")
    if review.get("atlas_claims_created") is not False or review.get("automated_promotion_allowed") is not False:
        raise ConstructionMasterError(f"imagery review safeguards changed for {queue_id}")
    scope = review.get("scope")
    if not isinstance(scope, Mapping) or any(
        scope.get(key) is not False
        for key in (
            "data_center_identity_confirmed",
            "lifecycle_status_confirmed",
            "operating_status_inferred",
            "power_or_energy_inferred",
        )
    ):
        raise ConstructionMasterError(f"imagery review claim boundary changed for {queue_id}")
    bbox = report.get("aoi_bbox_wgs84")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ConstructionMasterError(f"imagery report AOI changed for {queue_id}")
    decision = review.get("decision")
    retained = decision == "retain_site_aligned_change_candidate_for_manual_followup"
    if not retained and decision != "reject_automated_mask_for_site_promotion":
        raise ConstructionMasterError(f"unsupported imagery decision for {queue_id}")
    baseline = report.get("baseline", {})
    current = report.get("current", {})
    first_date, last_date = _date_bounds(
        (baseline.get("datetime"), current.get("datetime"), review.get("reviewed_at"))
    )
    entity = report.get("entity", {})
    job = batch_jobs.get(queue_id, {})
    normalized = (
        "imagery_change_candidate_retained_for_manual_followup"
        if retained
        else "imagery_change_candidate_rejected_for_site_promotion"
    )
    satellite_link = {
        "analyst_decision": decision,
        "batch_artifact_id": spec["batch_artifact_id"],
        "catalog_state": job.get("state"),
        "priority_tier": job.get("priority_tier"),
        "queue_id": queue_id,
        "selected_scene_ids": job.get("selected_scene_ids"),
    }
    if "catalog_batch_artifact_id" in spec:
        satellite_link["catalog_batch_artifact_id"] = spec[
            "catalog_batch_artifact_id"
        ]
        satellite_link["catalog_batch_manifest_sha256"] = spec[
            "catalog_batch_manifest_sha256"
        ]
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "construction": {
            "confidence": None,
            "method": review.get("review_method"),
            "source_supported": False,
            "verification_status": "imagery_change_review_does_not_verify_construction",
            "verified": False,
        },
        "disposition": {
            "construction_arithmetic_included": False,
            "exclusion_reason": "imagery_change_does_not_confirm_identity_lifecycle_power_or_operation",
            "label": "included_imagery_review_observation_only",
            "unique_site_counted": False,
        },
        "entity": {
            "address": None,
            "coordinate_method": "analyst_report_aoi_bbox_center_review_only",
            "country": None,
            "country_iso_a2": None,
            "country_iso_a3": None,
            "kind": "imagery_review_aoi",
            "latitude": (float(bbox[1]) + float(bbox[3])) / 2.0,
            "longitude": (float(bbox[0]) + float(bbox[2])) / 2.0,
            "name": entity.get("name"),
        },
        "evidence_scope": "structural_or_cv_discovery_candidate",
        "first_evidence_date": first_date,
        "fusion_overlay": None,
        "identity": {
            "confidence": None,
            "status": "source_entity_reference_not_verified_by_imagery",
        },
        "last_evidence_date": last_date,
        "lifecycle": {
            "normalized_status": normalized,
            "reported_status": decision,
            "reported_status_date": _date(review.get("reviewed_at")),
        },
        "observation_kind": "sentinel_analyst_change_review",
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": True,
        "row_id": _row_id("sentinel_analyst_change_review", spec["artifact_id"], queue_id),
        "satellite_links": [satellite_link],
        "source": {
            "artifact_id": spec["artifact_id"],
            "artifact_path": spec["report"]["path"],
            "artifact_sha256": spec["report"]["sha256"],
            "evidence_ids": [f"sentinel-report:{queue_id}", f"analyst-review:{queue_id}"],
            "manifest_sha256": spec["batch_manifest_sha256"],
            "record_id": queue_id,
            "release_id": None,
            "source_entity_id": entity.get("id"),
            "source_license": "Copernicus_Sentinel_data_with_attribution",
            "source_retrieved_at": review.get("reviewed_at"),
            "source_roots": ["copernicus_sentinel_2"],
            "source_url": report.get("source", {}).get("catalog_url"),
        },
        "source_evidence": [
            {
                "baseline_scene": {
                    "datetime": baseline.get("datetime"),
                    "id": baseline.get("id"),
                    "stac_item_sha256": baseline.get("stac_item_sha256"),
                },
                "classification": report.get("classification", {}).get("label"),
                "current_scene": {
                    "datetime": current.get("datetime"),
                    "id": current.get("id"),
                    "stac_item_sha256": current.get("stac_item_sha256"),
                },
                "decision": decision,
                "metrics": report.get("metrics", {}),
                "report_sha256": spec["report"]["sha256"],
                "review_method": review.get("review_method"),
                "review_sha256": spec["review"]["sha256"],
            }
        ],
        "tier": "C",
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _satellite_context(
    specs: Sequence[Mapping[str, Any]], resolved: Mapping[str, Path]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, Any]]:
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_queue: dict[str, dict[str, Any]] = {}
    counts: dict[str, Any] = {}
    for spec in specs:
        manifest, _ = _json_file(_path(spec["manifest"], resolved), "satellite batch")
        jobs = manifest.get("jobs")
        if not isinstance(jobs, Mapping):
            raise ConstructionMasterError("satellite batch jobs changed")
        state_counts = Counter()
        for queue_id, job in sorted(jobs.items()):
            if queue_id in by_queue:
                raise ConstructionMasterError(f"satellite queue ID repeats across cumulative lanes: {queue_id}")
            compact = {
                "batch_artifact_id": spec["artifact_id"],
                "catalog_state": job.get("state"),
                "entity_id": job.get("entity_id"),
                "priority_tier": job.get("priority_tier"),
                "queue_id": queue_id,
                "selected_scene_ids": job.get("selected_ids"),
            }
            by_queue[queue_id] = {
                "state": job.get("state"),
                "priority_tier": job.get("priority_tier"),
                "selected_scene_ids": job.get("selected_ids"),
                "batch_artifact_id": spec["artifact_id"],
                "entity_id": job.get("entity_id"),
            }
            if job.get("entity_id"):
                by_entity[str(job["entity_id"])].append(compact)
            state_counts[str(job.get("state"))] += 1
        counts[spec["artifact_id"]] = {
            "jobs": len(jobs),
            "states": dict(sorted(state_counts.items())),
        }
    for links in by_entity.values():
        links.sort(key=lambda item: item["queue_id"])
    return dict(by_entity), by_queue, counts


def _review_decisions(
    specs: Sequence[Mapping[str, Any]], resolved: Mapping[str, Path]
) -> dict[str, str]:
    decisions: dict[str, str] = {}
    report_hashes: set[str] = set()
    review_hashes: set[str] = set()
    for spec in specs:
        queue_id = spec["queue_id"]
        if (
            queue_id in decisions
            or spec["report"]["sha256"] in report_hashes
            or spec["review"]["sha256"] in review_hashes
        ):
            raise ConstructionMasterError("analyst reviews are not deduplicated")
        report_hashes.add(spec["report"]["sha256"])
        review_hashes.add(spec["review"]["sha256"])
        review, _ = _json_file(_path(spec["review"], resolved), "analyst review")
        decisions[queue_id] = str(review.get("decision"))
    return decisions


def _candidate_relative_path(raw: Any, label: str) -> str:
    """Map a candidate-fusion `../` path to the package-root path contract."""

    if not isinstance(raw, str):
        raise ConstructionMasterError(f"{label} path is absent")
    supplied = Path(raw)
    if not supplied.parts or supplied.parts[0] != "..":
        raise ConstructionMasterError(f"{label} must be package-relative via ../")
    remaining = supplied.parts[1:]
    if not remaining or any(part in {"", ".", ".."} for part in remaining):
        raise ConstructionMasterError(f"{label} path is not normalized")
    return Path(*remaining).as_posix()


def _v3_analyst_review_specs(
    fusion_spec: Mapping[str, Any],
    contract: Mapping[str, Any],
    satellite_specs: Sequence[Mapping[str, Any]],
    resolved: Mapping[str, Path],
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    """Derive and verify frozen review checkpoints without a duplicate list."""

    definition_path = _path(fusion_spec["definition"], resolved)
    fusion_artifact_id = fusion_spec.get("artifact_id")
    if fusion_artifact_id == "candidate-fusion-osm-planet-priority-v9":
        fusion_label = "candidate-fusion v9"
        expected_definition_sha256 = _V3_FUSION_DEFINITION_SHA256
        expected_manifest_sha256 = _V3_FUSION_MANIFEST_SHA256
    elif fusion_artifact_id == "candidate-fusion-osm-planet-priority-v10":
        fusion_label = "candidate-fusion v10"
        expected_definition_sha256 = _V4_FUSION_DEFINITION_SHA256
        expected_manifest_sha256 = _V4_FUSION_MANIFEST_SHA256
    elif fusion_artifact_id == "candidate-fusion-osm-planet-priority-v13":
        fusion_label = "candidate-fusion v13"
        expected_definition_sha256 = _V5_FUSION_DEFINITION_SHA256
        expected_manifest_sha256 = _V5_FUSION_MANIFEST_SHA256
    else:
        raise ConstructionMasterError("unsupported candidate-fusion review lineage")
    candidate_definition, _ = _json_file(
        definition_path, f"{fusion_label} definition"
    )
    candidate_manifest, _ = _json_file(
        _path(fusion_spec["manifest"], resolved), f"{fusion_label} manifest"
    )
    if (
        fusion_spec["manifest"].get("sha256") != expected_manifest_sha256
        or candidate_manifest.get("definition")
        != {
            "bytes": fusion_spec["definition"]["bytes"],
            "filename": Path(fusion_spec["definition"]["path"]).name,
            "sha256": expected_definition_sha256,
        }
        or candidate_definition.get("schema_version") != 3
    ):
        raise ConstructionMasterError(f"{fusion_label} review lineage changed")
    candidate_inputs = candidate_definition.get("inputs")
    if not isinstance(candidate_inputs, Mapping):
        raise ConstructionMasterError(f"{fusion_label} inputs are absent")
    review_sources = candidate_inputs.get("satellite_analyst_reviews")
    batch_sources = candidate_inputs.get("satellite_batch_bundles")
    manifest_inputs = candidate_manifest.get("inputs")
    if (
        not isinstance(review_sources, list)
        or len(review_sources) != contract.get("expected_rows")
        or not isinstance(batch_sources, list)
        or len(batch_sources) != 3
        or not isinstance(manifest_inputs, list)
    ):
        raise ConstructionMasterError(
            f"{fusion_label} review or batch inventory changed"
        )

    manifest_reviews: dict[str, Mapping[str, Any]] = {}
    for entry in manifest_inputs:
        if not isinstance(entry, Mapping) or entry.get("lane") != "sentinel_analyst_review":
            continue
        queue_id = entry.get("queue_id")
        if not isinstance(queue_id, str) or queue_id in manifest_reviews:
            raise ConstructionMasterError(
                f"{fusion_label} review manifest repeats a queue ID"
            )
        manifest_reviews[queue_id] = entry
    if len(manifest_reviews) != contract.get("expected_rows"):
        raise ConstructionMasterError(
            f"{fusion_label} manifest review count changed"
        )

    package_root = definition_path.parent.parent.resolve()
    batch_by_directory: dict[str, Mapping[str, Any]] = {}
    for batch in satellite_specs:
        if not isinstance(batch, Mapping) or not isinstance(
            batch.get("manifest"), Mapping
        ):
            raise ConstructionMasterError("satellite batch specification changed")
        directory = Path(str(batch["manifest"]["path"])).parent.as_posix()
        if directory in batch_by_directory:
            raise ConstructionMasterError("satellite batch directory repeats")
        batch_by_directory[directory] = batch
    candidate_batch_pins = {
        _candidate_relative_path(item.get("path"), "candidate batch"):
        item.get("manifest_sha256")
        for item in batch_sources
        if isinstance(item, Mapping)
    }
    if fusion_artifact_id == "candidate-fusion-osm-planet-priority-v9":
        expected_batch_pins = {
            directory: batch["manifest"]["sha256"]
            for directory, batch in batch_by_directory.items()
        }
        source_batch_pins = expected_batch_pins
        review_directory_to_catalog_directory = {
            directory: directory for directory in batch_by_directory
        }
    elif fusion_artifact_id == "candidate-fusion-osm-planet-priority-v10":
        expected_batch_pins = _V4_FUSION_BATCH_PINS
        source_batch_pins = _V4_FUSION_BATCH_PINS
        review_directory_to_catalog_directory = {
            "satellite_review_runs/2026-07-18-global-open-v3-active-001": (
                "satellite_review_runs/2026-07-18-global-open-v3-active-001"
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001": (
                "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-010": (
                "satellite_review_runs/2026-07-18-global-open-v3-unknown-011"
            ),
        }
        if set(batch_by_directory) != set(
            review_directory_to_catalog_directory.values()
        ):
            raise ConstructionMasterError(
                "candidate-fusion v10 review batches do not map to current catalog batches"
            )
    else:
        expected_batch_pins = _V5_FUSION_BATCH_PINS
        source_batch_pins = _V5_REVIEW_SOURCE_BATCH_PINS
        unknown_catalog_directories = sorted(
            directory
            for directory in batch_by_directory
            if directory.startswith(
                "satellite_review_runs/2026-07-18-global-open-v3-unknown-"
            )
        )
        if unknown_catalog_directories not in [
            ["satellite_review_runs/2026-07-18-global-open-v3-unknown-015"],
            ["satellite_review_runs/2026-07-18-global-open-v3-unknown-020"],
            ["satellite_review_runs/2026-07-18-global-open-v3-unknown-022"],
            ["satellite_review_runs/2026-07-18-global-open-v3-unknown-025"],
            ["satellite_review_runs/2026-07-18-global-open-v3-unknown-030"],
        ]:
            raise ConstructionMasterError(
                "candidate-fusion v13 has no approved current unknown catalog"
            )
        current_unknown_directory = unknown_catalog_directories[0]
        review_directory_to_catalog_directory = {
            "satellite_review_runs/2026-07-18-global-open-v3-active-001": (
                "satellite_review_runs/2026-07-18-global-open-v3-active-001"
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-proposed-001": (
                "satellite_review_runs/2026-07-18-global-open-v3-proposed-001"
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-010": (
                current_unknown_directory
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-013": (
                current_unknown_directory
            ),
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-015": (
                current_unknown_directory
            ),
        }
        if set(batch_by_directory) != set(
            review_directory_to_catalog_directory.values()
        ):
            raise ConstructionMasterError(
                "candidate-fusion v13 review batches do not map to current catalog batches"
            )
        for directory, expected_sha in source_batch_pins.items():
            source_manifest = _safe_path(
                package_root,
                f"{directory}/batch-manifest.json",
                "candidate-fusion review source batch manifest",
            )
            if (
                source_manifest.is_symlink()
                or not source_manifest.is_file()
                or _checkpoint(source_manifest)["sha256"] != expected_sha
            ):
                raise ConstructionMasterError(
                    "candidate-fusion v13 review source batch changed"
                )
    if candidate_batch_pins != expected_batch_pins:
        raise ConstructionMasterError(
            f"{fusion_label} satellite batch pins changed"
        )

    dynamic_resolved = dict(resolved)
    specs: list[dict[str, Any]] = []
    queue_ids: set[str] = set()
    for index, review_source in enumerate(review_sources):
        if not isinstance(review_source, Mapping):
            raise ConstructionMasterError("candidate-fusion review entry changed")
        queue_id = review_source.get("queue_id")
        manifest_entry = manifest_reviews.get(str(queue_id))
        if (
            not isinstance(queue_id, str)
            or queue_id in queue_ids
            or not isinstance(manifest_entry, Mapping)
        ):
            raise ConstructionMasterError(
                f"{fusion_label} reviews are not distinct"
            )
        queue_ids.add(queue_id)
        review_path = _candidate_relative_path(
            review_source.get("path"), f"candidate review {index}"
        )
        report_path = _candidate_relative_path(
            review_source.get("report_path"), f"candidate report {index}"
        )
        if (
            manifest_entry.get("path") != review_source.get("path")
            or not isinstance(manifest_entry.get("review"), Mapping)
            or not isinstance(manifest_entry.get("report"), Mapping)
            or manifest_entry["review"].get("sha256")
            != review_source.get("sha256")
            or manifest_entry["report"].get("sha256")
            != review_source.get("report_sha256")
        ):
            raise ConstructionMasterError(
                f"{fusion_label} review checkpoint changed"
            )
        matching_review_directories = [
            directory
            for directory in review_directory_to_catalog_directory
            if review_path.startswith(directory + "/")
            and report_path.startswith(directory + "/")
        ]
        if len(matching_review_directories) != 1:
            raise ConstructionMasterError(
                "candidate-fusion review does not resolve to one source batch"
            )
        review_directory = matching_review_directories[0]
        catalog_directory = review_directory_to_catalog_directory[review_directory]
        batch = batch_by_directory[catalog_directory]
        review_checkpoint = {
            "bytes": manifest_entry["review"].get("bytes"),
            "path": review_path,
            "sha256": manifest_entry["review"].get("sha256"),
        }
        report_checkpoint = {
            "bytes": manifest_entry["report"].get("bytes"),
            "path": report_path,
            "sha256": manifest_entry["report"].get("sha256"),
        }
        for label, checkpoint in (
            ("review", review_checkpoint),
            ("report", report_checkpoint),
        ):
            expected_bytes = checkpoint.get("bytes")
            expected_sha = checkpoint.get("sha256")
            if (
                not isinstance(expected_bytes, int)
                or expected_bytes <= 0
                or not isinstance(expected_sha, str)
                or _SHA_RE.fullmatch(expected_sha) is None
            ):
                raise ConstructionMasterError(
                    f"{fusion_label} {label} checkpoint is invalid"
                )
            actual_path = _safe_path(
                package_root, checkpoint["path"], f"analyst {label}"
            )
            if actual_path.is_symlink() or not actual_path.is_file():
                raise ConstructionMasterError(
                    f"{fusion_label} {label} file is absent"
                )
            if _checkpoint(actual_path) != {
                "bytes": expected_bytes,
                "sha256": expected_sha,
            }:
                raise ConstructionMasterError(
                    f"{fusion_label} {label} file changed"
                )
            dynamic_resolved[checkpoint["path"]] = actual_path
        source_batch_artifact_id = "satellite-" + Path(
            review_directory
        ).name.removeprefix("2026-07-18-")
        spec = {
            "artifact_id": f"sentinel-review-{queue_id}",
            "batch_artifact_id": source_batch_artifact_id,
            "batch_manifest_sha256": source_batch_pins[review_directory],
            "queue_id": queue_id,
            "report": report_checkpoint,
            "review": review_checkpoint,
        }
        if source_batch_artifact_id != batch["artifact_id"]:
            spec["catalog_batch_artifact_id"] = batch["artifact_id"]
            spec["catalog_batch_manifest_sha256"] = batch["manifest"]["sha256"]
        specs.append(spec)
    return specs, dynamic_resolved


def _fusion_context(
    spec: Mapping[str, Any],
    resolved: Mapping[str, Path],
    batch_jobs: Mapping[str, Mapping[str, Any]],
    decisions: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    if "definition" in spec:
        manifest, _ = _json_file(
            _path(spec["manifest"], resolved), "candidate-fusion manifest"
        )
        definition_checkpoint = spec["definition"]
        counts = manifest.get("counts")
        outputs = manifest.get("outputs")
        artifact_id = spec.get("artifact_id")
        expected_reviews = {
            "candidate-fusion-osm-planet-priority-v8": 21,
            "candidate-fusion-osm-planet-priority-v9": 25,
            "candidate-fusion-osm-planet-priority-v10": 31,
            "candidate-fusion-osm-planet-priority-v13": 43,
        }.get(artifact_id)
        if (
            manifest.get("format") != "datacenter-atlas-candidate-fusion-v3"
            or manifest.get("definition")
            != {
                "bytes": definition_checkpoint["bytes"],
                "filename": Path(definition_checkpoint["path"]).name,
                "sha256": definition_checkpoint["sha256"],
            }
            or not isinstance(counts, Mapping)
            or counts.get("primary_shortlist", {}).get("candidates_examined")
            != 102_451
            or counts.get("primary_shortlist", {}).get(
                "candidates_with_any_fusion_opportunity"
            )
            != 14_324
            or not isinstance(outputs, Mapping)
            or outputs.get("fusion-candidates.jsonl")
            != {
                "bytes": spec["data"]["bytes"],
                "records": 14_324,
                "sha256": spec["data"]["sha256"],
            }
            or counts.get("sentinel_lane", {}).get("analyst_reviews_examined")
            != expected_reviews
            or counts.get("sentinel_lane", {}).get(
                "retained_visible_change_review_confirms_candidate_identity_or_status"
            )
            is not False
        ):
            raise ConstructionMasterError(
                "candidate-fusion manifest or safeguards changed"
            )
        if artifact_id == "candidate-fusion-osm-planet-priority-v9" and counts.get(
            "sentinel_lane", {}
        ).get("analyst_reviews_examined_by_outcome") != {
            "rejected_for_site_promotion": 18,
            "retained_visible_change_aoi_followup": 7,
        }:
            raise ConstructionMasterError(
                "candidate-fusion v9 review outcomes changed"
            )
        if artifact_id == "candidate-fusion-osm-planet-priority-v10" and counts.get(
            "sentinel_lane", {}
        ).get("analyst_reviews_examined_by_outcome") != {
            "rejected_for_site_promotion": 23,
            "retained_visible_change_aoi_followup": 8,
        }:
            raise ConstructionMasterError(
                "candidate-fusion v10 review outcomes changed"
            )
        if artifact_id == "candidate-fusion-osm-planet-priority-v13" and counts.get(
            "sentinel_lane", {}
        ).get("analyst_reviews_examined_by_outcome") != {
            "rejected_for_site_promotion": 31,
            "retained_visible_change_aoi_followup": 12,
        }:
            raise ConstructionMasterError(
                "candidate-fusion v13 review outcomes changed"
            )
    overlays: dict[str, dict[str, Any]] = {}
    path = _path(spec["data"], resolved)
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ConstructionMasterError(f"fusion JSONL line {line_number} is invalid") from error
            candidate_id = row.get("candidate_id")
            if not isinstance(candidate_id, str) or candidate_id in overlays:
                raise ConstructionMasterError("fusion candidate ID missing or repeated")
            opportunities = row.get("evidence_opportunities", {})
            satellite_links: list[dict[str, Any]] = []
            for link in opportunities.get("sentinel_queue_or_review", []):
                queue_id = link.get("queue_id")
                current = batch_jobs.get(str(queue_id), {})
                decision = decisions.get(str(queue_id), link.get("analyst_review_decision"))
                if decision == "retain_site_aligned_change_candidate_for_manual_followup":
                    outcome = "retained_visible_change_aoi_followup"
                elif decision == "reject_automated_mask_for_site_promotion":
                    outcome = "rejected_for_site_promotion"
                else:
                    outcome = link.get("analyst_review_outcome_class")
                satellite_links.append(
                    {
                        "analyst_decision": decision,
                        "analyst_review_outcome_class": outcome,
                        "batch_artifact_id": current.get("batch_artifact_id"),
                        "catalog_state": current.get("state", link.get("catalog_state")),
                        "priority_tier": current.get("priority_tier", link.get("priority_tier")),
                        "queue_id": queue_id,
                        "relationship": link.get("relationship"),
                        "selected_scene_ids": current.get("selected_scene_ids"),
                    }
                )
            priority = row.get("review_priority", {})
            overlays[candidate_id] = {
                "candidate_fusion_artifact_id": spec["artifact_id"],
                "distinct_non_osm_source_roots": priority.get("distinct_non_osm_source_roots", []),
                "fusion_rank": priority.get("fusion_rank"),
                "opportunity_counts": {
                    "atlas_reference_proximity": len(opportunities.get("atlas_reference_proximity", [])),
                    "open_buildings_temporal_aoi": len(opportunities.get("open_buildings_temporal_aoi", [])),
                    "overture_footprint_bounds": len(opportunities.get("overture_footprint_bounds", [])),
                    "sentinel_queue_or_review": len(opportunities.get("sentinel_queue_or_review", [])),
                },
                "priority_tier": priority.get("tier"),
                "satellite_links": satellite_links,
            }
    return overlays


def _resolution_context(
    spec: Mapping[str, Any],
    resolved: Mapping[str, Path],
    master_entity_ids: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relationship_counts = Counter()
    attached_links = 0
    endpoint_attachments = 0
    total = 0
    for row in _csv_rows(_path(spec["data"], resolved)):
        total += 1
        if not _bool(row.get("advisory_only")) or _bool(row.get("automatic_merge_allowed")):
            raise ConstructionMasterError("within-release advisory safeguards changed")
        relationship_counts[row.get("candidate_class", "unknown")] += 1
        endpoints = [
            entity_id
            for entity_id in (row.get("left_entity_id"), row.get("right_entity_id"))
            if entity_id in master_entity_ids
        ]
        if endpoints:
            attached_links += 1
        endpoint_attachments += len(endpoints)
        for entity_id in endpoints:
            other = row.get("right_entity_id") if entity_id == row.get("left_entity_id") else row.get("left_entity_id")
            by_entity[entity_id].append(
                {
                    "advisory_only": True,
                    "candidate_class": row.get("candidate_class"),
                    "candidate_id": row.get("candidate_id"),
                    "counterpart_entity_id": other,
                    "distance_m": _float(row.get("distance_m")),
                    "relationship_suggestion": row.get("relationship_suggestion"),
                    "score": _float(row.get("score")),
                }
            )
    for advisories in by_entity.values():
        advisories.sort(key=lambda item: item["candidate_id"] or "")
    return dict(by_entity), {
        "advisory_links": total,
        "advisory_links_attached_to_at_least_one_master_row": attached_links,
        "advisory_links_unattached_to_master_rows": total - attached_links,
        "master_row_endpoint_attachments": endpoint_attachments,
        "master_rows_with_advisory_links": len(by_entity),
        "relationships_by_class": dict(sorted(relationship_counts.items())),
        "accepted_relationships": 0,
        "automatic_merges": 0,
        "unique_physical_site_count": None,
    }


def _flatten(row: Mapping[str, Any]) -> dict[str, Any]:
    source = row["source"]
    entity = row["entity"]
    lifecycle = row["lifecycle"]
    construction = row["construction"]
    identity = row["identity"]
    disposition = row["disposition"]
    return {
        "row_id": row["row_id"],
        "tier": row["tier"],
        "observation_kind": row["observation_kind"],
        "source_artifact_id": source["artifact_id"],
        "source_release_id": source["release_id"],
        "source_record_id": source["record_id"],
        "source_entity_id": source["source_entity_id"],
        "source_artifact_sha256": source["artifact_sha256"],
        "source_manifest_sha256": source["manifest_sha256"],
        "source_roots_json": _compact(source["source_roots"]),
        "evidence_ids_json": _compact(source["evidence_ids"]),
        "evidence_scope": row["evidence_scope"],
        "review_only": str(row["review_only"]).lower(),
        "entity_kind": entity["kind"],
        "name": entity["name"],
        "address": entity["address"],
        "latitude": entity["latitude"],
        "longitude": entity["longitude"],
        "country": entity["country"],
        "country_iso_a2": entity["country_iso_a2"],
        "country_iso_a3": entity["country_iso_a3"],
        "coordinate_method": entity["coordinate_method"],
        "reported_status": lifecycle["reported_status"],
        "reported_status_date": lifecycle["reported_status_date"],
        "normalized_status": lifecycle["normalized_status"],
        "construction_source_supported": str(construction["source_supported"]).lower(),
        "construction_verified": str(construction["verified"]).lower(),
        "construction_verification_status": construction["verification_status"],
        "construction_method": construction["method"],
        "construction_confidence": construction["confidence"],
        "identity_status": identity["status"],
        "identity_confidence": identity["confidence"],
        "source_evidence_json": _compact(row["source_evidence"]),
        "capacity_observations_json": _compact(row["capacity_observations"]),
        "annual_energy_observations_json": _compact(row["annual_energy_observations"]),
        "pue_observations_json": _compact(row["pue_observations"]),
        "untyped_capacity_statements_json": _compact(row["untyped_capacity_statements"]),
        "operating_model_observation_json": _compact(row["operating_model_observation"]),
        "workload_observations_json": _compact(row["workload_observations"]),
        "satellite_links_json": _compact(row["satellite_links"]),
        "resolution_advisories_json": _compact(row["resolution_advisories"]),
        "fusion_overlay_json": _compact(row["fusion_overlay"]),
        "first_evidence_date": row["first_evidence_date"],
        "last_evidence_date": row["last_evidence_date"],
        "disposition_label": disposition["label"],
        "construction_arithmetic_included": str(disposition["construction_arithmetic_included"]).lower(),
        "exclusion_reason": disposition["exclusion_reason"],
    }


class _Counts:
    def __init__(self) -> None:
        self.rows = 0
        self.row_ids: set[str] = set()
        self.tiers: Counter[str] = Counter()
        self.kinds: Counter[str] = Counter()
        self.statuses: Counter[str] = Counter()
        self.artifacts: Counter[str] = Counter()
        self.entity_kinds: Counter[str] = Counter()
        self.tier_a_statuses: Counter[str] = Counter()
        self.analyst_decisions: Counter[str] = Counter()
        self.typed_capacity_observations = 0
        self.annual_energy_observations = 0
        self.pue_observations = 0
        self.untyped_capacity_statements = 0
        self.workload_observations = 0
        self.operating_model_observations = 0
        self.source_evidence_records = 0
        self.satellite_links = 0
        self.resolution_advisory_attachments = 0
        self.construction_source_supported_rows = 0
        self.construction_verified_rows = 0
        self.fusion_overlays = 0
        self.satellite_linked_rows = 0
        self.advisory_linked_rows = 0
        self.fuzzy_reported_statuses: Counter[str] = Counter()
        self.ireland_application_statuses: Counter[str] = Counter()
        self.ireland_decisions: Counter[str] = Counter()
        self.ireland_planning_authorities: Counter[str] = Counter()
        self.england_application_statuses: Counter[str] = Counter()
        self.england_decisions: Counter[str] = Counter()
        self.england_decision_types: Counter[str] = Counter()
        self.england_providers: Counter[str] = Counter()
        self.nsw_workflow_stages: Counter[str] = Counter()
        self.nsw_modification_rows = 0
        self.netherlands_permit_stages: Counter[str] = Counter()
        self.netherlands_coordinate_rows = 0
        self.netherlands_mean_anchor_rows = 0
        self.new_zealand_candidate_classifications: Counter[str] = Counter()
        self.france_classifications: Counter[str] = Counter()
        self.france_metric_types: Counter[str] = Counter()
        self.france_relationship_evidence = 0
        self.tier_a_projection_digest = hashlib.sha256()
        self.presence: Counter[str] = Counter()
        self.tier_presence: dict[str, Counter[str]] = defaultdict(Counter)

    def add(self, row: Mapping[str, Any]) -> None:
        _validate_output_row(row)
        row_id = str(row["row_id"])
        if row_id in self.row_ids:
            raise ConstructionMasterError(f"row ID repeats: {row_id}")
        self.row_ids.add(row_id)
        self.rows += 1
        tier = str(row["tier"])
        self.tiers[tier] += 1
        self.kinds[str(row["observation_kind"])] += 1
        self.statuses[str(row["lifecycle"]["normalized_status"])] += 1
        self.artifacts[str(row["source"]["artifact_id"])] += 1
        self.entity_kinds[str(row["entity"]["kind"])] += 1
        if tier == "A":
            self.tier_a_statuses[str(row["lifecycle"]["normalized_status"])] += 1
            self.tier_a_projection_digest.update(
                _canonical_line(_tier_a_arithmetic_projection(row))
            )
        if row["observation_kind"] == "sentinel_analyst_change_review":
            self.analyst_decisions[str(row["lifecycle"]["reported_status"])] += 1
        if row["observation_kind"] == "fuzzy_identity_lifecycle_review_lead":
            self.fuzzy_reported_statuses[str(row["lifecycle"]["reported_status"])] += 1
        if row["observation_kind"] == IRELAND_OBSERVATION_KIND:
            attributes = row["source_evidence"][0]["planning_metadata"][
                "source_attributes"
            ]
            self.ireland_application_statuses[
                "<null>"
                if attributes.get("ApplicationStatus") is None
                else str(attributes.get("ApplicationStatus"))
            ] += 1
            self.ireland_decisions[
                "<null>"
                if attributes.get("Decision") is None
                else str(attributes.get("Decision"))
            ] += 1
            self.ireland_planning_authorities[
                "<null>"
                if attributes.get("PlanningAuthority") is None
                else str(attributes.get("PlanningAuthority"))
            ] += 1
        if row["observation_kind"] == ENGLAND_OBSERVATION_KIND:
            planning_metadata = row["source_evidence"][0]["planning_metadata"]
            raw_status = planning_metadata["raw_status"]
            provider = planning_metadata["provider"]

            def exact(value: Any) -> str:
                return "<null>" if value is None else str(value)

            self.england_application_statuses[
                exact(raw_status.get("planning-application-status"))
            ] += 1
            self.england_decisions[
                exact(raw_status.get("planning-decision"))
            ] += 1
            self.england_decision_types[
                exact(raw_status.get("planning-decision-type"))
            ] += 1
            self.england_providers[
                _compact(
                    {
                        "entity": provider.get("entity"),
                        "local_planning_authority": provider.get(
                            "local_planning_authority"
                        ),
                        "name": provider.get("name"),
                        "reference": provider.get("reference"),
                    }
                )
            ] += 1
        if row["observation_kind"] == NSW_OBSERVATION_KIND:
            observation = row["source_evidence"][0]["planning_metadata"][
                "source_observation"
            ]
            self.nsw_workflow_stages[
                str(observation["selection_workflow_stage_exact"])
            ] += 1
            self.nsw_modification_rows += observation.get("is_modification") is True
        if row["observation_kind"] == NETHERLANDS_OBSERVATION_KIND:
            observation = row["source_evidence"][0]["permit_metadata"][
                "source_observation"
            ]
            self.netherlands_permit_stages[
                str(observation["permit_process"]["stage"])
            ] += 1
            self.netherlands_coordinate_rows += (
                row["entity"]["latitude"] is not None
                and row["entity"]["longitude"] is not None
            )
            self.netherlands_mean_anchor_rows += row["entity"].get(
                "coordinate_method"
            ) == "official_koop_mean_of_nearby_etrs89_points_review_only"
        if row["observation_kind"] == NEW_ZEALAND_OBSERVATION_KIND:
            observation = row["source_evidence"][0]["planning_metadata"][
                "source_observation"
            ]
            self.new_zealand_candidate_classifications[
                str(observation["candidate_classification"])
            ] += 1
        if row["observation_kind"] == FRANCE_OBSERVATION_KIND:
            metadata = row["source_evidence"][0][
                "environmental_review_metadata"
            ]
            observation = metadata["source_observation"]
            self.france_classifications[str(metadata["classification"])] += 1
            self.france_metric_types.update(
                str(metric["metric_type"])
                for metric in observation["metrics"]
            )
            self.france_relationship_evidence += (
                metadata["within_source_relationship"] is not None
            )
        self.typed_capacity_observations += len(row["capacity_observations"])
        self.annual_energy_observations += len(row["annual_energy_observations"])
        self.pue_observations += len(row["pue_observations"])
        self.untyped_capacity_statements += len(row["untyped_capacity_statements"])
        self.workload_observations += len(row["workload_observations"])
        self.operating_model_observations += row["operating_model_observation"] is not None
        self.source_evidence_records += len(row["source_evidence"])
        self.satellite_links += len(row["satellite_links"])
        self.resolution_advisory_attachments += len(row["resolution_advisories"])
        self.construction_source_supported_rows += row["construction"]["source_supported"] is True
        self.construction_verified_rows += row["construction"]["verified"] is True
        self.fusion_overlays += row["fusion_overlay"] is not None
        self.satellite_linked_rows += bool(row["satellite_links"])
        self.advisory_linked_rows += bool(row["resolution_advisories"])
        fields = {
            "address": row["entity"]["address"] is not None,
            "annual_energy": bool(row["annual_energy_observations"]),
            "capacity": bool(row["capacity_observations"]),
            "construction_confidence": row["construction"]["confidence"] is not None,
            "coordinates": row["entity"]["latitude"] is not None and row["entity"]["longitude"] is not None,
            "country": row["entity"]["country"] is not None,
            "evidence_ids": bool(row["source"]["evidence_ids"]),
            "first_evidence_date": row["first_evidence_date"] is not None,
            "identity_confidence": row["identity"]["confidence"] is not None,
            "last_evidence_date": row["last_evidence_date"] is not None,
            "name": row["entity"]["name"] is not None,
            "operating_model": row["operating_model_observation"] is not None,
            "pue": bool(row["pue_observations"]),
            "reported_status": row["lifecycle"]["reported_status"] is not None,
            "reported_status_date": row["lifecycle"]["reported_status_date"] is not None,
            "satellite_link": bool(row["satellite_links"]),
            "typed_or_untyped_capacity": bool(row["capacity_observations"] or row["annual_energy_observations"] or row["pue_observations"] or row["untyped_capacity_statements"]),
            "workload": bool(row["workload_observations"]),
        }
        for field, present in fields.items():
            if present:
                self.presence[field] += 1
                self.tier_presence[tier][field] += 1

    @staticmethod
    def _gaps(total: int, presence: Mapping[str, int]) -> dict[str, Any]:
        return {
            field: {
                "missing": total - int(presence.get(field, 0)),
                "null_or_gap_rate": round((total - int(presence.get(field, 0))) / total, 9) if total else None,
                "present": int(presence.get(field, 0)),
                "rows": total,
            }
            for field in sorted(
                {
                    "address",
                    "annual_energy",
                    "capacity",
                    "construction_confidence",
                    "coordinates",
                    "country",
                    "evidence_ids",
                    "first_evidence_date",
                    "identity_confidence",
                    "last_evidence_date",
                    "name",
                    "operating_model",
                    "pue",
                    "reported_status",
                    "reported_status_date",
                    "satellite_link",
                    "typed_or_untyped_capacity",
                    "workload",
                }
            )
        }

    def document(self, context: Mapping[str, Any]) -> dict[str, Any]:
        document = {
            "construction_arithmetic": {
                "rows": self.tiers["A"],
                "source_supported_rows": self.construction_source_supported_rows,
                "statuses": dict(sorted(self.tier_a_statuses.items())),
                "unit": "source_supported_observation_row",
                "unique_physical_sites": None,
                "verified_by_independent_master_review": self.construction_verified_rows,
            },
            "evidence_observations": {
                "annual_energy": self.annual_energy_observations,
                "operating_model": self.operating_model_observations,
                "pue": self.pue_observations,
                "source_evidence_records": self.source_evidence_records,
                "typed_capacity_excluding_annual_energy_and_pue": self.typed_capacity_observations,
                "untyped_capacity_statements": self.untyped_capacity_statements,
                "workload": self.workload_observations,
            },
            "fusion": {
                "rows_with_opportunity_overlay": self.fusion_overlays,
                "structural_rows_without_opportunity_overlay": self.kinds["osm_planet_structural_candidate"] - self.fusion_overlays,
            },
            "null_and_gap_rates": {
                "all_rows": self._gaps(self.rows, self.presence),
                "by_tier": {
                    tier: self._gaps(count, self.tier_presence[tier])
                    for tier, count in sorted(self.tiers.items())
                },
            },
            "row_counts": {
                "by_entity_kind": dict(sorted(self.entity_kinds.items())),
                "by_normalized_status": dict(sorted(self.statuses.items())),
                "by_observation_kind": dict(sorted(self.kinds.items())),
                "by_source_artifact": dict(sorted(self.artifacts.items())),
                "by_tier": dict(sorted(self.tiers.items())),
                "review_only": self.tiers["B"] + self.tiers["C"],
                "total": self.rows,
            },
            "review_leads": {
                "edgemode_sec_rows": self.artifacts["edgemode-sec-assessment-v1"],
                "fuzzy_reported_statuses_preserved_but_not_promoted": dict(
                    sorted(self.fuzzy_reported_statuses.items())
                ),
                "fuzzy_rows": self.kinds["fuzzy_identity_lifecycle_review_lead"],
                "normalized_review_lead_rows": self.statuses["review_lead"],
            },
            "satellite": {
                "analyst_decisions": dict(sorted(self.analyst_decisions.items())),
                "analyst_review_rows": self.kinds["sentinel_analyst_change_review"],
                "batch_accounting": context["satellite_counts"],
                "cumulative_unknown_batch_policy": context[
                    "satellite_unknown_policy"
                ],
                "row_link_records": self.satellite_links,
                "rows_with_satellite_links": self.satellite_linked_rows,
            },
            "scope": SCOPE_POLICY,
            "upstream_context": context["upstream_context"],
            "within_release_resolution": {
                **context["resolution_counts"],
                "row_advisory_records": self.resolution_advisory_attachments,
            },
        }
        if (
            context["is_v2"]
            or context["is_v3"]
            or context["is_v4"]
            or context["is_v5"]
            or context["is_v6"]
        ):
            document["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ] = self.tier_a_projection_digest.hexdigest()
            document["review_leads"]["ireland_planning"] = {
                "application_statuses_exact": dict(
                    sorted(self.ireland_application_statuses.items())
                ),
                "construction_lifecycle_operation_type_and_metrics_promoted": False,
                "decisions_exact": dict(sorted(self.ireland_decisions.items())),
                "observation_rows": self.kinds[IRELAND_OBSERVATION_KIND],
                "planning_authorities_exact": dict(
                    sorted(self.ireland_planning_authorities.items())
                ),
                "relationship_suggestions": context["ireland"][
                    "relationship_summary"
                ],
                "reported_statuses_are_planning_metadata_only": True,
                "unique_physical_site_count": None,
            }
        if (
            context["is_v3"]
            or context["is_v4"]
            or context["is_v5"]
            or context["is_v6"]
        ):
            document["review_leads"]["england_planning"] = {
                "accepted_relationships": 0,
                "application_statuses_exact": dict(
                    sorted(self.england_application_statuses.items())
                ),
                "construction_lifecycle_operation_type_and_metrics_promoted": False,
                "context_assessment": context["england"]["summary"],
                "decision_types_exact": dict(
                    sorted(self.england_decision_types.items())
                ),
                "decisions_exact": dict(sorted(self.england_decisions.items())),
                "observation_rows": self.kinds[ENGLAND_OBSERVATION_KIND],
                "providers_exact": dict(sorted(self.england_providers.items())),
                "raw_descriptions_statuses_dates_points_and_provider_preserved": True,
                "reported_statuses_are_planning_metadata_only": True,
                "unique_physical_site_count": None,
            }
        if context["is_v4"] or context["is_v5"] or context["is_v6"]:
            document["review_leads"]["nsw_major_projects"] = {
                "construction_lifecycle_operation_type_and_metrics_promoted": False,
                "modification_rows": self.nsw_modification_rows,
                "observation_rows": self.kinds[NSW_OBSERVATION_KIND],
                "portal_process_stages_are_lifecycle": False,
                "untyped_power_statements": sum(
                    len(row["detail_metadata"]["power_statements"])
                    for row in context["nsw"]["observations"]
                ),
                "unique_physical_site_count": None,
                "workflow_stages_exact": dict(
                    sorted(self.nsw_workflow_stages.items())
                ),
            }
            document["review_leads"]["netherlands_koop"] = {
                "accepted_relationships": 0,
                "automatic_merges": 0,
                "construction_lifecycle_operation_type_and_metrics_promoted": False,
                "coordinate_rows": self.netherlands_coordinate_rows,
                "context_rows_excluded": context["netherlands"]["summary"][
                    "context_rows_excluded"
                ],
                "mean_anchor_rows_with_maximum_source_point_span_100m": (
                    self.netherlands_mean_anchor_rows
                ),
                "observation_rows": self.kinds[NETHERLANDS_OBSERVATION_KIND],
                "permit_process_stages_are_lifecycle": False,
                "permit_stages_exact": dict(
                    sorted(self.netherlands_permit_stages.items())
                ),
                "unique_physical_site_count": None,
            }
            document["review_leads"]["new_zealand_fast_track"] = {
                "accepted_relationships": 0,
                "automatic_merges": 0,
                "candidate_classifications_exact": dict(
                    sorted(self.new_zealand_candidate_classifications.items())
                ),
                "construction_or_operation_promoted": False,
                "observation_rows": self.kinds[NEW_ZEALAND_OBSERVATION_KIND],
                "planning_process_stage_promoted_to_lifecycle": False,
                "source_declared_proposed_characterisation_only": True,
                "unique_physical_site_count": None,
            }
        if context["is_v5"] or context["is_v6"]:
            document["review_leads"]["france_igedd"] = {
                "accepted_relationships": 0,
                "annual_energy_values_are_projected_not_measured": True,
                "automatic_merges": 0,
                "backup_support_and_grid_metrics_promoted_to_it_or_facility_load": False,
                "classification_counts_exact": dict(
                    sorted(self.france_classifications.items())
                ),
                "construction_lifecycle_operation_or_type_promoted": False,
                "coordinates_promoted": False,
                "derived_rows_publication_eligible": context["france"][
                    "summary"
                ]["derived_rows_publication_eligible"],
                "metric_observations": sum(self.france_metric_types.values()),
                "metric_types_exact": dict(
                    sorted(self.france_metric_types.items())
                ),
                "observation_rows": self.kinds[FRANCE_OBSERVATION_KIND],
                "relationship_evidence_records": self.france_relationship_evidence,
                "relationship_evidence_is_advisory_only": True,
                "target_pue_is_projected_not_measured": True,
                "unit_conversions_applied": False,
                "unique_physical_site_count": None,
            }
        return document


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["row_counts"]
    if FRANCE_OBSERVATION_KIND in counts["by_observation_kind"]:
        if "satellite-global-open-v3-unknown-030" in coverage["satellite"][
            "batch_accounting"
        ]:
            if counts["by_tier"].get("A") == 319:
                return (
                    "# Public/open construction master\n\n"
                    f"This immutable observation ledger contains {counts['total']:,} rows: "
                    f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                    f"{counts['by_tier']['B']:,} Tier B review leads, and "
                    f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                    "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                    "The v14 Tier-A delta is four source-supported project observations: three reported under "
                    "construction and one reported in site preparation. Every addition is coordinate-null and "
                    "not independently verified. The sole typed-capacity addition is a planned 65 MW gross-facility "
                    "observation for Minoh Phase 1; it is contained within and non-additive to the source release's "
                    "130 MW campus observation. Neither value is current load, critical-IT load, grid connection, "
                    "generation, or annual energy. The source release carries Colt DCS as the Phase 1 operator; "
                    "the construction-master schema introduces no role observation and promotes no developer or "
                    "contractor tag.\n\n"
                    "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                    "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                    "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                    "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown030 remains the "
                    "cumulative catalog context and makes no imagery-derived identity, lifecycle, operating-status, "
                    "type, capacity, or power inference.\n\n"
                    "The federation-v12 and permit-aware coverage-audit-v13 manifests are contextual accounting "
                    "inputs only; their arithmetic totals are not copied as rows or sites.\n\n"
                    "`construction-master.jsonl` is the canonical nested row representation. "
                    "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                    "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                    "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
                ).encode("utf-8")
            if counts["by_tier"].get("A") == 315:
                return (
                    "# Public/open construction master\n\n"
                    f"This immutable observation ledger contains {counts['total']:,} rows: "
                    f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                    f"{counts['by_tier']['B']:,} Tier B review leads, and "
                    f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                    "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                    "The v13 Tier-A delta is 11 source-supported project observations, all reported under "
                    "construction. Every addition is coordinate-null and retains no typed capacity, annual-energy, "
                    "PUE, untyped-power, workload, role, or operating-model observation. These are source-scoped "
                    "lifecycle claims, not imagery inference or independently verified construction measurements.\n\n"
                    "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                    "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                    "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                    "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown030 remains the "
                    "cumulative catalog context and makes no imagery-derived identity, lifecycle, operating-status, "
                    "type, capacity, or power inference.\n\n"
                    "The federation-v11 and permit-aware coverage-audit-v12 manifests are contextual accounting "
                    "inputs only; their arithmetic totals are not copied as rows or sites.\n\n"
                    "`construction-master.jsonl` is the canonical nested row representation. "
                    "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                    "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                    "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
                ).encode("utf-8")
            if counts["by_tier"].get("A") == 304:
                return (
                    "# Public/open construction master\n\n"
                    f"This immutable observation ledger contains {counts['total']:,} rows: "
                    f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                    f"{counts['by_tier']['B']:,} Tier B review leads, and "
                    f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                    "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                    "The v12 Tier-A delta is 33 source-supported project observations: 29 under construction, "
                    "one permitted, one proposed, one shell, and one site preparation. Five additions retain "
                    "source-reported planned critical-IT observations; four retain broad AI-specialized workload "
                    "classification and one retains crypto-mining classification. These are source-scoped claims, "
                    "not current operating load, grid demand, generation, annual energy, or independently verified "
                    "construction measurements.\n\n"
                    "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                    "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                    "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                    "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown030 remains the "
                    "cumulative catalog context and makes no imagery-derived identity, lifecycle, operating-status, "
                    "type, capacity, or power inference.\n\n"
                    "The federation-v10 and permit-aware coverage-audit-v11 manifests are contextual accounting "
                    "inputs only; their arithmetic totals are not copied as rows or sites.\n\n"
                    "`construction-master.jsonl` is the canonical nested row representation. "
                    "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                    "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                    "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
                ).encode("utf-8")
            if counts["by_tier"].get("A") == 271:
                return (
                    "# Public/open construction master\n\n"
                    f"This immutable observation ledger contains {counts['total']:,} rows: "
                    f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                    f"{counts['by_tier']['B']:,} Tier B review leads, and "
                    f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                    "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                    "The v11 Tier-A delta is 46 source-supported observations: 27 under construction, twelve "
                    "MEP/electrical, three shell, three site preparation, and one announced. These are "
                    "source-reported lifecycle observations, not imagery inference. Typed capacity, workload, "
                    "and operating-model observations remain source-scoped; they are not current operating load, "
                    "grid demand, generation, annual energy, or independently verified construction measurements.\n\n"
                    "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                    "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                    "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                    "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown030 remains the "
                    "cumulative catalog context and makes no imagery-derived identity, lifecycle, operating-status, "
                    "type, capacity, or power inference.\n\n"
                    "The federation-v9 and permit-aware coverage-audit-v10 manifests are contextual accounting "
                    "inputs only; their arithmetic totals are not copied as rows or sites.\n\n"
                    "`construction-master.jsonl` is the canonical nested row representation. "
                    "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                    "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                    "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
                ).encode("utf-8")
            return (
                "# Public/open construction master\n\n"
                f"This immutable observation ledger contains {counts['total']:,} rows: "
                f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                f"{counts['by_tier']['B']:,} Tier B review leads, and "
                f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                "The v10 Tier-A delta is 32 source-supported observations: 16 under construction, five site "
                "preparation, three MEP/electrical, two shell, two foundations, two civil works, and two "
                "permitted. These are source-reported lifecycle observations, not imagery inference. Five "
                "additions retain planned critical-IT observations: 31 MW for London 4, 27 MW for MIL1, "
                "176 MW for the Dugny campus, approximately 16 MW for FRA20, and 7.3 MW of additional "
                "critical-IT load for the Frankfurt 1 expansion. They are facility- or project-scope planning "
                "values, not current operating load, grid demand, generation, annual energy, or independently "
                "verified construction measurements.\n\n"
                "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown030 supplies only "
                "the later incomplete cumulative catalog state and makes no imagery-derived identity, lifecycle, "
                "operating-status, type, capacity, or power inference.\n\n"
                "The federation-v8 and permit-aware coverage-audit-v9 manifests are contextual accounting inputs "
                "only; their arithmetic totals are not copied as rows or sites.\n\n"
                "`construction-master.jsonl` is the canonical nested row representation. "
                "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
            ).encode("utf-8")
        if "satellite-global-open-v3-unknown-025" in coverage["satellite"][
            "batch_accounting"
        ]:
            return (
                "# Public/open construction master\n\n"
                f"This immutable observation ledger contains {counts['total']:,} rows: "
                f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                f"{counts['by_tier']['B']:,} Tier B review leads, and "
                f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                "The v9 Tier-A delta is thirteen source-reported under-construction project observations. "
                "Five Applied Digital rows preserve five explicit critical-IT observations: 600 MW contracted "
                "across Polaris Forge 1 and Delta Forge 1, plus 300 MW planned across two Polaris Forge 2 "
                "buildings. They are not gross facility load, grid service, generation, annual energy, or "
                "operating load. The remaining eight additions are metric-free; all thirteen add no annual "
                "energy, PUE, untyped power, operating model, or independent construction verification. "
                "A shared CoreWeave Ellendale campus row separately gains one source-supported "
                "wholesale-colocation operating-model observation without lifecycle or metric change.\n\n"
                "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown025 supplies only "
                "the later incomplete cumulative catalog state and makes no imagery-derived identity, lifecycle, "
                "operating-status, or power inference.\n\n"
                "The federation-v7 and permit-aware coverage-audit-v8 manifests are contextual accounting inputs "
                "only; their arithmetic totals are not copied as rows or sites. The separately recorded 576 MW "
                "Polaris Forge 2 planned backup-generation nameplate is absent from the construction pipeline and "
                "is not promoted to data-centre load.\n\n"
                "`construction-master.jsonl` is the canonical nested row representation. "
                "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
            ).encode("utf-8")
        if "satellite-global-open-v3-unknown-022" in coverage["satellite"][
            "batch_accounting"
        ]:
            return (
                "# Public/open construction master\n\n"
                f"This immutable observation ledger contains {counts['total']:,} rows: "
                f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                f"{counts['by_tier']['B']:,} Tier B review leads, and "
                f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                "The v8 Tier-A delta is two Microsoft project observations: the Mount Pleasant second "
                "facility is source-reported under construction and the Pecos campus development is "
                "source-reported announced. Both use approximate locality points and add no typed capacity, "
                "annual energy, PUE, untyped power, operating model, or independent construction verification. "
                "Only Pecos retains an explicit source-scoped mixed-workload observation.\n\n"
                "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                "their frozen Unknown010, Unknown013, and Unknown015 source lineage; Unknown022 supplies only "
                "the later cumulative catalog state.\n\n"
                "The federation-v5 and coverage-audit-v5 manifests are contextual accounting inputs only; their "
                "arithmetic totals are not copied as rows or sites. Spain BOE, Italy MASE VIA/VAS, Brazil, "
                "Germany UVP, IAAC, Chile SEA, and EPBC lanes remain excluded.\n\n"
                "`construction-master.jsonl` is the canonical nested row representation. "
                "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
            ).encode("utf-8")
        if "satellite-global-open-v3-unknown-020" in coverage["satellite"][
            "batch_accounting"
        ]:
            return (
                "# Public/open construction master\n\n"
                f"This immutable observation ledger contains {counts['total']:,} rows: "
                f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
                f"{counts['by_tier']['B']:,} Tier B review leads, and "
                f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
                "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
                "The v6 Tier-A delta is four Meta project observations explicitly reported under construction "
                "on April 28, 2026. They share one source evidence record, use named-locality centroid "
                "coordinates, and add no typed capacity, annual energy, PUE, or independent construction "
                "verification. The official process lanes remain 114 Ireland, 3 England, 22 NSW, 13 "
                "Netherlands, 3 New Zealand, and 4 France IGEDD observations outside construction arithmetic.\n\n"
                "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
                "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
                "not merge rows or produce a unique-site count. Candidate-fusion v13 and its analyst rows keep "
                "their frozen unknown010, unknown013, and unknown015 source lineage; Unknown020 supplies only "
                "the later cumulative catalog state.\n\n"
                "Spain BOE, Italy MASE VIA/VAS, Brazil, Germany UVP, IAAC, Chile SEA, and EPBC lanes are excluded "
                "from this release.\n\n"
                "`construction-master.jsonl` is the canonical nested row representation. "
                "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
                "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
                "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
            ).encode("utf-8")
        return (
            "# Public/open construction master\n\n"
            f"This immutable observation ledger contains {counts['total']:,} rows: "
            f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
            f"{counts['by_tier']['B']:,} Tier B review leads, and "
            f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
            "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
            "The official process lanes contain 114 Ireland, 3 England, 22 NSW, 13 Netherlands, 3 New "
            "Zealand, and 4 France IGEDD observations. France preserves three direct environmental-opinion "
            "observations and one ancillary grid-connection follow-up without site merging. Their lifecycle "
            "status and coordinates remain null. The 13 France metrics retain the source metric type, value, "
            "unit, scope, and qualifier without conversion: only explicit IT capacity remains IT capacity; "
            "backup, support, and grid values remain distinct; annual energy and target PUE remain projections.\n\n"
            "Resolution suggestions, 43 satellite analyst reviews (12 retained for manual follow-up and 31 "
            "rejected for site promotion), and candidate-fusion v13 opportunities remain advisory. They do "
            "not merge rows or produce a unique-site count. The Tier-A arithmetic projection matches v1-v4. "
            "Unknown015 supplies current cumulative catalog accounting while candidate-fusion v13 preserves "
            "its frozen unknown010, unknown013, and unknown015 review lineage.\n\n"
            "Spain BOE, Italy MASE VIA/VAS, Brazil, Germany UVP, IAAC, Chile SEA, and EPBC lanes are excluded "
            "from this release.\n\n"
            "`construction-master.jsonl` is the canonical nested row representation. "
            "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
            "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
            "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
        ).encode("utf-8")
    if NSW_OBSERVATION_KIND in counts["by_observation_kind"]:
        return (
            "# Public/open construction master\n\n"
            f"This immutable observation ledger contains {counts['total']:,} rows: "
            f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
            f"{counts['by_tier']['B']:,} Tier B review leads, and "
            f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
            "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
            "The official planning lanes contain 114 Ireland, 3 England, 22 NSW, 13 Netherlands, and "
            "3 New Zealand observations. Their portal or permit stages do not establish physical lifecycle, "
            "construction, or operation. The NSW rows retain ten source numeric phrases as untyped text. "
            "The New Zealand rows keep source-declared AI and hyperscale wording within proposal scope.\n\n"
            "Resolution suggestions, 31 satellite analyst reviews (8 retained for manual follow-up and 23 "
            "rejected for site promotion), and candidate-fusion v10 opportunities remain advisory. They do "
            "not merge rows or produce a unique-site count. The Tier-A arithmetic projection matches v1-v3. "
            "Unknown011 supplies current catalog accounting while candidate-fusion v10 preserves its frozen "
            "unknown010 review lineage.\n\n"
            "`construction-master.jsonl` is the canonical nested row representation. "
            "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
            "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
            "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
        ).encode("utf-8")
    if ENGLAND_OBSERVATION_KIND in counts["by_observation_kind"]:
        return (
            "# Public/open construction master\n\n"
            f"This immutable observation ledger contains {counts['total']:,} rows: "
            f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
            f"{counts['by_tier']['B']:,} Tier B review leads, and "
            f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
            "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
            "The 114 official Ireland planning rows and 3 direct-scope official England planning rows "
            "preserve planning-process metadata without promoting facility identity, lifecycle, construction, "
            "operation, type, capacity, power, energy, PUE, workload, or unique-site status. The one England "
            "context-only exact-phrase record and three optional server-room records are explicitly excluded.\n\n"
            "Resolution suggestions, 25 satellite analyst reviews (7 retained for manual follow-up and 18 "
            "rejected for site promotion), and candidate-fusion v9 opportunities are advisory context; they "
            "never merge rows or produce a unique-site count. The Tier-A arithmetic projection is hash-checked "
            "against v1 and v2 while unknown009 replaces all earlier cumulative unknown batches.\n\n"
            "`construction-master.jsonl` is the canonical nested row representation. "
            "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
            "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
            "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
        ).encode("utf-8")
    if IRELAND_OBSERVATION_KIND in counts["by_observation_kind"]:
        return (
            "# Public/open construction master\n\n"
            f"This immutable observation ledger contains {counts['total']:,} rows: "
            f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
            f"{counts['by_tier']['B']:,} Tier B review leads, and "
            f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
            "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
            "The 114 official Ireland planning rows preserve planning-process metadata and coordinates "
            "without promoting facility identity, lifecycle, construction, operation, type, power, energy, "
            "PUE, or workload. Ireland relationship suggestions remain advisory and unaccepted.\n\n"
            "Resolution suggestions, satellite reviews, and candidate-fusion v8 opportunities are advisory "
            "context; they never merge rows or produce a unique-site count. The Tier-A arithmetic projection "
            "is hash-checked against v1 while unknown007 replaces all earlier cumulative unknown batches.\n\n"
            "`construction-master.jsonl` is the canonical nested row representation. "
            "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
            "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
            "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
        ).encode("utf-8")
    return (
        "# Public/open construction master\n\n"
        f"This immutable observation ledger contains {counts['total']:,} rows: "
        f"{counts['by_tier']['A']:,} Tier A source-supported construction/pipeline observations, "
        f"{counts['by_tier']['B']:,} Tier B identity/lifecycle review leads, and "
        f"{counts['by_tier']['C']:,} Tier C structural or computer-vision discovery observations.\n\n"
        "Only Tier A participates in construction arithmetic. Tier B and C rows remain review-only. "
        "Resolution suggestions and fusion opportunities are attached as advisory context; they never merge rows, infer identity or lifecycle, or produce a unique-site count.\n\n"
        "`construction-master.jsonl` is the canonical nested row representation. "
        "`construction-master.csv` is a lossless flattened view whose nested fields are canonical JSON. "
        "`coverage.json` reports exact row accounting and null/gap rates.\n\n"
        "This artifact makes no claim of global completeness or parity with a commercial benchmark.\n"
    ).encode("utf-8")


def _attribution(
    *,
    includes_ireland_planning: bool = False,
    includes_england_planning: bool = False,
    includes_v4_official_lanes: bool = False,
    includes_france_igedd: bool = False,
    includes_google: bool = False,
    includes_meta: bool = False,
    includes_microsoft: bool = False,
    includes_v9_official_sources: bool = False,
    includes_v10_official_sources: bool = False,
    includes_v11_official_sources: bool = False,
    includes_v12_official_sources: bool = False,
    includes_v13_official_sources: bool = False,
    includes_v14_official_sources: bool = False,
) -> bytes:
    ireland = (
        "Ireland planning observations are derived from IrishPlanningApplications, "
        "Department of Housing, Local Government and Heritage, under CC BY 4.0. "
        "Filtering and normalization changes are documented in the pinned source release.\n"
        if includes_ireland_planning
        else ""
    )
    england = (
        "England planning observations are derived from Planning Data, "
        "Department for Levelling Up, Housing and Communities, under the "
        "Open Government Licence v3.0. © Crown copyright and database right 2026. "
        "Filtering and review-only normalization are documented in the pinned source assessment.\n"
        if includes_england_planning
        else ""
    )
    v4_official_lanes = (
        "NSW Major Projects observations contain department metadata under CC BY 4.0, "
        "with State of New South Wales and Department of Planning, Housing and "
        "Infrastructure attribution; mixed-rights raw HTML and attachments are excluded.\n"
        "Netherlands KOOP observations contain official-publication metadata and selected "
        "official text in the assessed CC0 1.0 scope, subject to express notices; publication "
        "attachments and images are excluded.\n"
        "New Zealand observations contain bounded official page text. Environmental Protection "
        "Authority Fast-track text uses CC BY-SA 4.0, and Ministry for the Environment text uses "
        "CC BY 4.0. Logos, images, plans, comments, attachments, and third-party material are excluded.\n"
        if includes_v4_official_lanes
        else ""
    )
    france_igedd = (
        "France IGEDD environmental-opinion rows contain derived factual observations "
        "under the Licence Ouverte / Open Licence Etalab 2.0. Source citation is retained "
        "per row; raw HTML and PDF documents are not redistributed.\n"
        if includes_france_igedd
        else ""
    )
    meta = (
        "Meta rows contain compact factual project-status observations from one official "
        "newsroom disclosure. The source page remains all-rights-reserved; its prose and "
        "images are not redistributed or relicensed.\n"
        if includes_meta
        else ""
    )
    google = (
        "Google rows contain compact factual project-status and workload observations "
        "from official infrastructure disclosures. The source pages remain "
        "all-rights-reserved; their prose and images are not redistributed or relicensed.\n"
        if includes_google
        else ""
    )
    microsoft = (
        "Microsoft rows contain compact factual project-status and workload observations "
        "from official company disclosures. The source pages remain all-rights-reserved; "
        "their prose and images are not redistributed or relicensed.\n"
        if includes_microsoft
        else ""
    )
    v9_official_sources = (
        "V9 project rows contain compact factual lifecycle, workload, critical-IT, and operating-model "
        "observations attributed per row to Indiana IDEM, Applied Digital SEC disclosures, Sunshine Coast "
        "Council, the Government of Aragón, Impact Geotechnical via an Environment Agency consultation, "
        "Infratil via NZX, Related Digital, Amazon Innovation Campuses in Pennsylvania, Amazon, North Carolina "
        "DEQ, and Richmond County. Source pages, filings, supporting documents, prose, and images remain under "
        "their source-specific terms and are not redistributed or relicensed.\n"
        if includes_v9_official_sources
        else ""
    )
    v10_official_sources = (
        "V10 project rows add compact factual observations attributed per row to City of Espoo, "
        "Municipality of Vihti, Microsoft, NTT DATA, Inc., QTS Data Centers, STACK Infrastructure, "
        "Digital Realty, CyrusOne, Colt Data Centre Services, and Gilbane Building Company. Source "
        "pages, releases, project pages, prose, documents, and images remain under their source-specific "
        "terms and are not redistributed or relicensed.\n"
        if includes_v10_official_sources
        else ""
    )
    v11_official_sources = (
        "V11 project rows add compact factual observations attributed per row to Aligned Data Centers, "
        "City of New Albany, Clune Construction, Colt Data Centre Services, CyrusOne, Equinix, Khazna "
        "Data Centers, Meta, NEXTDC, Oracle, Prime Data Centers, Princeton Digital Group, Retelit, "
        "Skanska, ST Telemedia Global Data Centres, Wisconsin Department of Natural Resources, Yondr "
        "Group, and xneelo. Public-government-record material and all-rights-reserved source pages remain "
        "under their source-specific terms; prose, documents, and images are not redistributed or relicensed.\n"
        if includes_v11_official_sources
        else ""
    )
    v12_official_sources = (
        "V12 project rows add compact factual observations attributed per row to Airtel Africa, "
        "AtlasEdge, Bitdeer Technologies Group, City of Independence, DayOne Data Centers, Elea "
        "Data Centers, Empyrion Digital, Equinix, firstcolo, maincubes, MEEZA, Microsoft, Nebius, "
        "Pure DC, Saudi Press Agency, SC Zeus Data Centers, Takoda Data Centers, Tecto Data Centers, "
        "Telekom Malaysia, Tokyo Tatemono, True IDC, and ST Telemedia Global Data Centres. Source "
        "pages, releases, filings, permit reports, prose, documents, and images remain under their "
        "source-specific terms and are not redistributed or relicensed.\n"
        if includes_v12_official_sources
        else ""
    )
    v13_official_sources = (
        "V13 project rows add compact factual lifecycle observations attributed per row to DATA4, "
        "Equinix, Keppel, Larsen & Toubro, Presidencia Uruguay, Servpac, Telehouse, VietnamPlus / "
        "Vietnam News Agency, and Viettel Group. Source pages, reports, releases, filings, posts, "
        "prose, documents, and images remain under their source-specific terms and are not "
        "redistributed or relicensed.\n"
        if includes_v13_official_sources
        else ""
    )
    v14_official_sources = (
        "V14 project rows add compact factual lifecycle and planned gross-facility observations "
        "attributed per row to Adani Group, CSC – IT Center for Science Ltd., ESR, and SRV Group "
        "Plc. Source pages, releases, blog and magazine items, prose, documents, and images remain "
        "under their source-specific terms and are not redistributed or relicensed.\n"
        if includes_v14_official_sources
        else ""
    )
    return (
        "Contains source-scoped records derived from OpenStreetMap (ODbL 1.0), Epoch AI (CC BY 4.0), Wikidata (CC0), public-domain boundary context, and source-linked factual claims from public disclosures.\n"
        "Structural discovery uses OpenStreetMap. Imagery review metadata contains modified Copernicus Sentinel-2 data attribution and Element 84 Earth Search catalog references.\n"
        "SEC/EdgeMode rows contain only public-filing metadata and compact factual assessment fields; underlying filing text is not redistributed. Upstream attribution and license fields remain attached per row.\n"
        + ireland
        + england
        + v4_official_lanes
        + france_igedd
        + google
        + meta
        + microsoft
        + v9_official_sources
        + v10_official_sources
        + v11_official_sources
        + v12_official_sources
        + v13_official_sources
        + v14_official_sources
    ).encode("utf-8")


def _context(
    definition: Mapping[str, Any], resolved: Mapping[str, Path]
) -> dict[str, Any]:
    inputs = definition["inputs"]
    is_v2 = _is_v2_definition(definition)
    is_v3 = _is_v3_definition(definition)
    is_v4 = _is_v4_definition(definition)
    is_v5 = _is_v5_definition(definition)
    is_v14 = _is_v14_definition(definition)
    is_v13 = _is_v13_definition(definition) or is_v14
    is_v12 = _is_v12_definition(definition) or is_v13
    is_v11 = _is_v11_definition(definition) or is_v12
    is_v10 = _is_v10_definition(definition) or is_v11
    is_v9 = _is_v9_definition(definition) or is_v10
    is_v8 = _is_v8_definition(definition) or is_v9
    is_v7 = _is_v7_definition(definition) or is_v8
    # V7 through v14 change pinned current inputs while consuming the complete v6
    # processing/policy lineage.
    is_v6 = _is_v6_definition(definition) or is_v7
    tier_a_rows: list[tuple[Mapping[str, Any], dict[str, str]]] = []
    evidence_by_artifact: dict[str, dict[str, dict[str, str]]] = {}
    master_entity_ids: set[str] = set()
    for artifact in inputs["tier_a_releases"]:
        rows = list(_csv_rows(_path(artifact["data"], resolved)))
        evidence_by_artifact[artifact["artifact_id"]] = _evidence_map(
            _path(artifact["evidence"], resolved)
        )
        if is_v14 and artifact["artifact_id"] == "epoch-official-open-seed-v33":
            _validate_v14_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        elif is_v13 and artifact["artifact_id"] == "epoch-official-open-seed-v32":
            _validate_v13_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        elif is_v12 and artifact["artifact_id"] == "epoch-official-open-seed-v30":
            _validate_v12_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        elif is_v11 and artifact["artifact_id"] == "epoch-official-open-seed-v20":
            _validate_v11_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        elif is_v10 and artifact["artifact_id"] == "epoch-official-open-seed-v13":
            _validate_v10_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        elif is_v9 and artifact["artifact_id"] == "epoch-official-open-seed-v9":
            _validate_v9_open_seed_source_allowlist(
                rows, evidence_by_artifact[artifact["artifact_id"]]
            )
        for row in rows:
            entity_id = row.get("entity_id", "")
            if not entity_id or entity_id in master_entity_ids:
                raise ConstructionMasterError("Tier A entity ID missing or repeated")
            master_entity_ids.add(entity_id)
            tier_a_rows.append((artifact, row))
    analyst_review_specs: Sequence[Mapping[str, Any]]
    effective_resolved: Mapping[str, Path]
    if is_v3 or is_v4 or is_v5 or is_v6:
        analyst_review_specs, effective_resolved = _v3_analyst_review_specs(
            inputs["candidate_fusion"],
            inputs["analyst_reviews"],
            inputs["satellite_batches"],
            resolved,
        )
    else:
        analyst_review_specs = inputs["analyst_reviews"]
        effective_resolved = resolved
    satellite_by_entity, batch_jobs, satellite_counts = _satellite_context(
        inputs["satellite_batches"], resolved
    )
    decisions = _review_decisions(analyst_review_specs, effective_resolved)
    fusion = _fusion_context(
        inputs["candidate_fusion"], effective_resolved, batch_jobs, decisions
    )
    advisories, resolution_counts = _resolution_context(
        inputs["within_release_resolution"], resolved, master_entity_ids
    )
    federation, _ = _json_file(
        _path(inputs["coverage_context"]["federation_manifest"], resolved),
        "federation manifest",
    )
    audit, _ = _json_file(
        _path(inputs["coverage_context"]["audit_manifest"], resolved),
        "coverage audit manifest",
    )
    ireland = (
        _ireland_context(inputs["tier_b_ireland_planning"], resolved)
        if is_v2 or is_v3 or is_v4 or is_v5 or is_v6
        else None
    )
    england = (
        _england_context(inputs["tier_b_england_planning"], resolved)
        if is_v3 or is_v4 or is_v5 or is_v6
        else None
    )
    nsw = (
        _nsw_context(inputs["tier_b_nsw_major_projects"], resolved)
        if is_v4 or is_v5 or is_v6
        else None
    )
    netherlands = (
        _netherlands_context(inputs["tier_b_netherlands_koop"], resolved)
        if is_v4 or is_v5 or is_v6
        else None
    )
    new_zealand = (
        _new_zealand_context(inputs["tier_b_new_zealand_fast_track"], resolved)
        if is_v4 or is_v5 or is_v6
        else None
    )
    france = (
        _france_context(inputs["tier_b_france_igedd"], resolved)
        if is_v5 or is_v6
        else None
    )
    upstream_context = {
        "candidate_fusion": {
            "analyst_reviews_in_frozen_overlay": (
                43
                if is_v5 or is_v6
                else 31
                if is_v4
                else 25
                if is_v3
                else 21
                if is_v2
                else 6
            ),
            "opportunity_overlay_rows": len(fusion),
            "structural_candidates_examined": inputs["candidate_fusion"]["expected_structural_candidates"],
        },
        "coverage_audit": audit.get("counts"),
        "federation": {
            "child_payloads_copied": federation.get("scope", {}).get("child_payloads_copied"),
            "source_scoped_rows": audit.get("counts", {}).get("source_scoped_entity_records"),
            "unique_physical_sites": None,
        },
        "review_lane_policy": (
            "6,130 fuzzy rows, 9 SEC leads, 114 Ireland observations, 3 England "
            "observations, 22 NSW observations, 13 Netherlands observations, "
            "3 New Zealand observations, and 4 France IGEDD observations remain "
            "outside construction arithmetic"
            if is_v5 or is_v6
            else "6,130 fuzzy rows, 9 SEC leads, 114 Ireland observations, 3 England "
            "observations, 22 NSW observations, 13 Netherlands observations, and "
            "3 New Zealand observations remain outside construction arithmetic"
            if is_v4
            else "6,130 fuzzy rows, 9 SEC leads, 114 Ireland planning observations, "
            "and 3 direct-scope England planning observations remain outside "
            "construction arithmetic; the 1 England context-only row is excluded"
            if is_v3
            else (
                "6,130 fuzzy rows, 9 SEC leads, and 114 Ireland planning "
                "observations remain outside construction arithmetic"
                if is_v2
                else "6,130 fuzzy rows and 9 SEC leads remain outside construction arithmetic"
            )
        ),
    }
    if is_v2 or is_v3 or is_v4 or is_v5 or is_v6:
        upstream_context["ireland_planning"] = {
            "matched_planning_observations": 114,
            "relationship_suggestions_are_advisory_only": True,
            "unique_physical_site_count": None,
        }
    if is_v3 or is_v4 or is_v5 or is_v6:
        upstream_context["england_planning"] = england["summary"]
    if is_v4 or is_v5 or is_v6:
        upstream_context["nsw_major_projects"] = nsw["summary"]
        upstream_context["netherlands_koop"] = netherlands["summary"]
        upstream_context["new_zealand_fast_track"] = new_zealand["summary"]
    if is_v5 or is_v6:
        upstream_context["france_igedd"] = france["summary"]
    return {
        "advisories": advisories,
        "analyst_review_specs": analyst_review_specs,
        "batch_jobs": batch_jobs,
        "effective_resolved": effective_resolved,
        "england": england,
        "evidence_by_artifact": evidence_by_artifact,
        "fusion": fusion,
        "france": france,
        "ireland": ireland,
        "is_v2": is_v2,
        "is_v3": is_v3,
        "is_v4": is_v4,
        "is_v5": is_v5,
        "is_v6": is_v6,
        "is_v7": is_v7,
        "is_v8": is_v8,
        "is_v9": is_v9,
        "is_v10": is_v10,
        "is_v11": is_v11,
        "is_v12": is_v12,
        "is_v13": is_v13,
        "is_v14": is_v14,
        "netherlands": netherlands,
        "new_zealand": new_zealand,
        "nsw": nsw,
        "resolution_counts": resolution_counts,
        "satellite_by_entity": satellite_by_entity,
        "satellite_counts": satellite_counts,
        "satellite_unknown_policy": (
            "unknown-030 is the sole current cumulative unknown catalog batch; candidate-fusion "
            "v13 preserves frozen unknown-010, unknown-013, and unknown-015 review lineage"
            if is_v10
            else "unknown-025 is the sole current cumulative unknown catalog batch; candidate-fusion "
            "v13 preserves frozen unknown-010, unknown-013, and unknown-015 review lineage"
            if is_v9
            else "unknown-022 is the sole current cumulative unknown catalog batch; candidate-fusion "
            "v13 preserves frozen unknown-010, unknown-013, and unknown-015 review lineage"
            if is_v8
            else "unknown-020 is the sole current cumulative unknown catalog batch; candidate-fusion "
            "v13 preserves frozen unknown-010, unknown-013, and unknown-015 review lineage"
            if is_v6
            else "unknown-015 is the sole cumulative unknown catalog batch; candidate-fusion "
            "v13 preserves frozen unknown-010, unknown-013, and unknown-015 review lineage"
            if is_v5
            else
            "unknown-011 is the sole cumulative unknown catalog batch; candidate-fusion "
            "v10 and its analyst-review lineage remain pinned to unknown-010"
            if is_v4
            else "unknown-009 is the sole cumulative unknown batch; unknown-001 "
            "through unknown-008 are excluded and counts are not additive"
            if is_v3
            else (
                "unknown-007 is the sole cumulative unknown batch; unknown-001 "
                "through unknown-006 are excluded and counts are not additive"
                if is_v2
                else "unknown-003 replaces unknown-002; counts are not additive"
            )
        ),
        "tier_a_rows": tier_a_rows,
        "upstream_context": upstream_context,
    }


def _rows(
    definition: Mapping[str, Any], resolved: Mapping[str, Path], context: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    inputs = definition["inputs"]
    for artifact, source_row in context["tier_a_rows"]:
        yield _release_row(
            source_row,
            artifact=artifact,
            artifact_sha=artifact["data"]["sha256"],
            manifest_sha=artifact["manifest"]["sha256"],
            evidence=context["evidence_by_artifact"][artifact["artifact_id"]],
            satellite_by_entity=context["satellite_by_entity"],
            advisories_by_entity=context["advisories"],
            tier="A",
        )
    fuzzy = inputs["tier_b_fuzzy_release"]
    fuzzy_evidence = _evidence_map(_path(fuzzy["evidence"], resolved))
    for source_row in _csv_rows(_path(fuzzy["data"], resolved)):
        yield _release_row(
            source_row,
            artifact=fuzzy,
            artifact_sha=fuzzy["data"]["sha256"],
            manifest_sha=fuzzy["manifest"]["sha256"],
            evidence=fuzzy_evidence,
            satellite_by_entity={},
            advisories_by_entity={},
            tier="B",
        )
    yield from _edge_rows(inputs["tier_b_edgemode"], resolved)
    if context["ireland"] is not None:
        ireland_spec = inputs["tier_b_ireland_planning"]
        relationship_ids = context["ireland"][
            "relationship_ids_by_observation"
        ]
        for observation in context["ireland"]["observations"]:
            observation_id = str(observation["observation_id"])
            yield _ireland_row(
                observation,
                spec=ireland_spec,
                relationship_suggestion_ids=relationship_ids.get(
                    observation_id, []
                ),
            )
    if context["england"] is not None:
        england_spec = inputs["tier_b_england_planning"]
        for observation in context["england"]["direct_observations"]:
            yield _england_row(
                observation,
                spec=england_spec,
                assessment=context["england"]["assessment"],
            )
    if context["nsw"] is not None:
        nsw_spec = inputs["tier_b_nsw_major_projects"]
        for observation in context["nsw"]["observations"]:
            yield _nsw_row(
                observation,
                spec=nsw_spec,
                assessment=context["nsw"]["assessment"],
            )
    if context["netherlands"] is not None:
        netherlands_spec = inputs["tier_b_netherlands_koop"]
        for observation in context["netherlands"]["direct_observations"]:
            yield _netherlands_row(
                observation,
                spec=netherlands_spec,
                assessment=context["netherlands"]["assessment"],
            )
    if context["new_zealand"] is not None:
        new_zealand_spec = inputs["tier_b_new_zealand_fast_track"]
        for observation in context["new_zealand"]["observations"]:
            yield _new_zealand_row(
                observation,
                spec=new_zealand_spec,
                assessment=context["new_zealand"]["assessment"],
            )
    if context["france"] is not None:
        france_spec = inputs["tier_b_france_igedd"]
        for observation in context["france"]["observations"]:
            yield _france_row(
                observation,
                spec=france_spec,
                assessment=context["france"]["assessment"],
            )
    structural = inputs["tier_c_structural"]
    seen_candidates: set[str] = set()
    for feature in _feature_collection(_path(structural["data"], resolved)):
        candidate_id = feature.get("id")
        if candidate_id in seen_candidates:
            raise ConstructionMasterError(f"structural candidate repeats: {candidate_id}")
        seen_candidates.add(str(candidate_id))
        yield _structural_row(
            feature,
            spec=structural,
            overlay=context["fusion"].get(candidate_id),
        )
    absent_overlays = set(context["fusion"]) - seen_candidates
    if absent_overlays:
        raise ConstructionMasterError("fusion overlays reference absent structural candidates")
    for review_spec in sorted(
        context["analyst_review_specs"], key=lambda item: item["queue_id"]
    ):
        yield _analyst_row(
            review_spec, context["effective_resolved"], context["batch_jobs"]
        )


def _input_lineage(
    definition: Mapping[str, Any], context: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    lineage = [
        {
            "bytes": spec["bytes"],
            "label": label,
            "path": spec["path"],
            "sha256": spec["sha256"],
        }
        for label, spec in _checkpoint_specs(definition["inputs"])
    ]
    if context is not None and (
        context.get("is_v3")
        or context.get("is_v4")
        or context.get("is_v5")
        or context.get("is_v6")
    ):
        fusion_version = (
            "v13"
            if context.get("is_v5") or context.get("is_v6")
            else "v10"
            if context.get("is_v4")
            else "v9"
        )
        for index, review_spec in enumerate(context["analyst_review_specs"]):
            for checkpoint_name in ("report", "review"):
                spec = review_spec[checkpoint_name]
                lineage.append(
                    {
                        "bytes": spec["bytes"],
                        "label": (
                            "inputs.analyst_reviews_derived_from_candidate_fusion_"
                            f"{fusion_version}"
                            f"[{index}].{checkpoint_name}"
                        ),
                        "path": spec["path"],
                        "sha256": spec["sha256"],
                    }
                )
    return lineage


def _assert_expected(coverage: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    actual = {
        "analyst_review_rows": coverage["satellite"]["analyst_review_rows"],
        "fuzzy_review_rows": coverage["row_counts"]["by_source_artifact"].get("osm-fuzzy-review-v2", 0),
        "fusion_overlay_rows": coverage["fusion"]["rows_with_opportunity_overlay"],
        "resolution_advisory_links": coverage["within_release_resolution"]["advisory_links"],
        "structural_candidate_rows": coverage["row_counts"]["by_observation_kind"].get("osm_planet_structural_candidate", 0),
        "tier_a_rows": coverage["row_counts"]["by_tier"].get("A", 0),
        "tier_b_rows": coverage["row_counts"]["by_tier"].get("B", 0),
        "tier_c_rows": coverage["row_counts"]["by_tier"].get("C", 0),
        "total_rows": coverage["row_counts"]["total"],
    }
    if "ireland_planning_rows" in expected:
        actual["ireland_planning_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(IRELAND_OBSERVATION_KIND, 0)
    if "england_planning_rows" in expected:
        actual["england_planning_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(ENGLAND_OBSERVATION_KIND, 0)
    if "england_context_only_excluded_rows" in expected:
        actual["england_context_only_excluded_rows"] = coverage["review_leads"][
            "england_planning"
        ]["context_assessment"]["context_only_exact_phrase_rows_excluded"]
    if "nsw_planning_rows" in expected:
        actual["nsw_planning_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(NSW_OBSERVATION_KIND, 0)
    if "nsw_untyped_power_statements" in expected:
        actual["nsw_untyped_power_statements"] = coverage["review_leads"][
            "nsw_major_projects"
        ]["untyped_power_statements"]
    if "netherlands_planning_rows" in expected:
        actual["netherlands_planning_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(NETHERLANDS_OBSERVATION_KIND, 0)
    if "netherlands_context_excluded_rows" in expected:
        actual["netherlands_context_excluded_rows"] = coverage["review_leads"][
            "netherlands_koop"
        ]["context_rows_excluded"]
    if "netherlands_coordinate_rows" in expected:
        actual["netherlands_coordinate_rows"] = coverage["review_leads"][
            "netherlands_koop"
        ]["coordinate_rows"]
    if "netherlands_mean_anchor_rows" in expected:
        actual["netherlands_mean_anchor_rows"] = coverage["review_leads"][
            "netherlands_koop"
        ]["mean_anchor_rows_with_maximum_source_point_span_100m"]
    if "new_zealand_planning_rows" in expected:
        actual["new_zealand_planning_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(NEW_ZEALAND_OBSERVATION_KIND, 0)
    if "new_zealand_project_candidate_rows" in expected:
        actual["new_zealand_project_candidate_rows"] = coverage["review_leads"][
            "new_zealand_fast_track"
        ]["candidate_classifications_exact"].get(
            "direct_data_centre_project_candidate", 0
        )
    if "new_zealand_prior_related_rows" in expected:
        actual["new_zealand_prior_related_rows"] = coverage["review_leads"][
            "new_zealand_fast_track"
        ]["candidate_classifications_exact"].get(
            "prior_related_planning_observation", 0
        )
    if "france_igedd_rows" in expected:
        actual["france_igedd_rows"] = coverage["row_counts"][
            "by_observation_kind"
        ].get(FRANCE_OBSERVATION_KIND, 0)
    if "france_igedd_direct_rows" in expected:
        actual["france_igedd_direct_rows"] = coverage["review_leads"][
            "france_igedd"
        ]["classification_counts_exact"].get("direct_data_centre_project", 0)
    if "france_igedd_ancillary_rows" in expected:
        actual["france_igedd_ancillary_rows"] = coverage["review_leads"][
            "france_igedd"
        ]["classification_counts_exact"].get(
            "ancillary_grid_connection_follow_up", 0
        )
    if "france_igedd_metric_observations" in expected:
        actual["france_igedd_metric_observations"] = coverage["review_leads"][
            "france_igedd"
        ]["metric_observations"]
    if "france_igedd_relationship_evidence" in expected:
        actual["france_igedd_relationship_evidence"] = coverage["review_leads"][
            "france_igedd"
        ]["relationship_evidence_records"]
    if "analyst_review_retained_rows" in expected:
        actual["analyst_review_retained_rows"] = coverage["satellite"][
            "analyst_decisions"
        ].get("retain_site_aligned_change_candidate_for_manual_followup", 0)
    if "analyst_review_rejected_rows" in expected:
        actual["analyst_review_rejected_rows"] = coverage["satellite"][
            "analyst_decisions"
        ].get("reject_automated_mask_for_site_promotion", 0)
    if "tier_a_arithmetic_projection_sha256" in expected:
        actual["tier_a_arithmetic_projection_sha256"] = coverage[
            "construction_arithmetic"
        ].get("tier_a_arithmetic_projection_sha256")
    if actual != dict(expected):
        raise ConstructionMasterError(
            f"construction-master counts changed: expected {dict(expected)!r}, got {actual!r}"
        )


def _build_into(
    definition_path: Path, directory: Path
) -> dict[str, Any]:
    definition, definition_raw, package_root, resolved = _definition(definition_path)
    context = _context(definition, resolved)
    counts = _Counts()
    jsonl_path = directory / JSONL_FILENAME
    csv_path = directory / CSV_FILENAME
    with jsonl_path.open("xb") as jsonl, csv_path.open(
        "x", encoding="utf-8", newline=""
    ) as csv_output:
        writer = csv.DictWriter(
            csv_output, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        for row in _rows(definition, resolved, context):
            counts.add(row)
            jsonl.write(_canonical_line(row))
            writer.writerow(_flatten(row))
        jsonl.flush()
        os.fsync(jsonl.fileno())
        csv_output.flush()
        os.fsync(csv_output.fileno())
    coverage = counts.document(context)
    _assert_expected(coverage, definition["expected_counts"])
    coverage_raw = _canonical_json(coverage)
    readme_raw = _readme(coverage)
    attribution_raw = _attribution(
        includes_ireland_planning=(
            context["is_v2"]
            or context["is_v3"]
            or context["is_v4"]
            or context["is_v5"]
            or context["is_v6"]
        ),
        includes_england_planning=(
            context["is_v3"]
            or context["is_v4"]
            or context["is_v5"]
            or context["is_v6"]
        ),
        includes_v4_official_lanes=(
            context["is_v4"] or context["is_v5"] or context["is_v6"]
        ),
        includes_france_igedd=context["is_v5"] or context["is_v6"],
        includes_google=context["is_v7"],
        includes_meta=context["is_v6"],
        includes_microsoft=context["is_v8"],
        includes_v9_official_sources=context["is_v9"],
        includes_v10_official_sources=context["is_v10"],
        includes_v11_official_sources=context["is_v11"],
        includes_v12_official_sources=context["is_v12"],
        includes_v13_official_sources=context["is_v13"],
        includes_v14_official_sources=context["is_v14"],
    )
    _write_file(directory / COVERAGE_FILENAME, coverage_raw)
    _write_file(directory / README_FILENAME, readme_raw)
    _write_file(directory / ATTRIBUTION_FILENAME, attribution_raw)
    output_names = {
        JSONL_FILENAME,
        CSV_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
    }
    outputs = {name: _checkpoint(directory / name) for name in sorted(output_names)}
    outputs[JSONL_FILENAME]["records"] = counts.rows
    outputs[CSV_FILENAME]["records"] = counts.rows
    manifest = {
        "definition": {
            "bytes": len(definition_raw),
            "path": definition_path.resolve().relative_to(package_root).as_posix(),
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition["generated_at"],
        "input_checkpoints": _input_lineage(definition, context),
        "master_id": definition["master_id"],
        "outputs": outputs,
        "row_counts": coverage["row_counts"],
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE_POLICY,
    }
    manifest_raw = _canonical_json(manifest)
    _write_file(directory / MANIFEST_FILENAME, manifest_raw)
    _write_file(
        directory / MANIFEST_HASH_FILENAME,
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii"),
    )
    return manifest


def write_construction_master(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = False,
) -> dict[str, Any]:
    """Atomically publish a new immutable construction-master bundle."""

    definition_file = Path(definition_path)
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise ConstructionMasterError(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        manifest = _build_into(definition_file, stage)
        _validate_static(stage)
        if freeze:
            for entry in stage.iterdir():
                entry.chmod(0o444)
            stage.chmod(0o555)
        stage.replace(destination)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return manifest


def _validate_v2_frozen_permissions(directory: Path) -> None:
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise ConstructionMasterError("construction master must be frozen 0555")
    for entry in directory.iterdir():
        if stat.S_IMODE(entry.stat().st_mode) != 0o444:
            raise ConstructionMasterError(
                "construction-master files must be frozen 0444"
            )


def _validate_static(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionMasterError("construction-master bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise ConstructionMasterError("construction-master closed file set changed")
    manifest, manifest_raw = _json_file(directory / MANIFEST_FILENAME, "manifest")
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionMasterError("manifest is not canonical")
    if (directory / MANIFEST_HASH_FILENAME).read_bytes() != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ConstructionMasterError("manifest sidecar changed")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("scope") != SCOPE_POLICY
    ):
        raise ConstructionMasterError("manifest identity or safeguards changed")
    expected_outputs = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if set(manifest.get("outputs", {})) != expected_outputs:
        raise ConstructionMasterError("manifest output inventory changed")
    for name in expected_outputs:
        expected = manifest["outputs"][name]
        checkpoint = _checkpoint(directory / name)
        if checkpoint != {"bytes": expected.get("bytes"), "sha256": expected.get("sha256")}:
            raise ConstructionMasterError(f"output changed: {name}")
    coverage, coverage_raw = _json_file(directory / COVERAGE_FILENAME, "coverage")
    if coverage_raw != _canonical_json(coverage):
        raise ConstructionMasterError("coverage is not canonical")
    if coverage.get("scope") != SCOPE_POLICY or coverage.get("row_counts") != manifest.get("row_counts"):
        raise ConstructionMasterError("coverage and manifest counts differ")
    if manifest["outputs"][JSONL_FILENAME].get("records") != coverage["row_counts"]["total"]:
        raise ConstructionMasterError("JSONL record count does not reconcile")
    if manifest["outputs"][CSV_FILENAME].get("records") != coverage["row_counts"]["total"]:
        raise ConstructionMasterError("CSV record count does not reconcile")
    return manifest


def validate_construction_master(
    directory: str | Path, *, definition_path: str | Path
) -> dict[str, Any]:
    """Validate and reproduce a bundle byte-for-byte without network access."""

    root = Path(directory)
    manifest = _validate_static(root)
    if manifest.get("master_id") in {
        V2_MASTER_ID,
        V3_MASTER_ID,
        V4_MASTER_ID,
        V5_MASTER_ID,
        V6_MASTER_ID,
        V7_MASTER_ID,
        V8_MASTER_ID,
        V9_MASTER_ID,
        V10_MASTER_ID,
        V11_MASTER_ID,
        V12_MASTER_ID,
        V13_MASTER_ID,
        V14_MASTER_ID,
    }:
        _validate_v2_frozen_permissions(root)
    with tempfile.TemporaryDirectory(prefix="construction-master-reproduce-") as temporary:
        reproduced = Path(temporary) / "bundle"
        write_construction_master(definition_path, reproduced)
        for name in sorted(BUNDLE_FILES):
            if _checkpoint(root / name) != _checkpoint(reproduced / name):
                raise ConstructionMasterError(
                    f"output differs from offline byte reproduction: {name}"
                )
    return manifest


__all__ = [
    "ConstructionMasterError",
    "validate_construction_master",
    "write_construction_master",
]
