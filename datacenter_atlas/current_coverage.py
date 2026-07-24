"""Deterministic index of the Atlas artifacts that define current coverage.

The ledger is a content-addressed inventory, not another data federation.  It
copies no source rows and deliberately keeps publication rights separate from
evidentiary maturity so that an open review queue cannot be mistaken for a
confirmed data-centre release.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping


DEFINITION_SCHEMA_VERSION = 1
DEFINITION_SCHEMA_VERSION_V2 = 2
DEFINITION_SCHEMA_VERSION_V3 = 3
LEDGER_SCHEMA_VERSION = 1
LEDGER_SCHEMA_VERSION_V2 = 2
LEDGER_SCHEMA_VERSION_V3 = 3
LEDGER_FORMAT = "datacenter-atlas-current-coverage-ledger-v1"
LEDGER_FORMAT_V2 = "datacenter-atlas-current-coverage-ledger-v2"
LEDGER_FORMAT_V3 = "datacenter-atlas-current-coverage-ledger-v3"
BUNDLE_FORMAT = "datacenter-atlas-current-coverage-ledger-bundle-v1"
BUNDLE_FORMAT_V2 = "datacenter-atlas-current-coverage-ledger-bundle-v2"
BUNDLE_FORMAT_V3 = "datacenter-atlas-current-coverage-ledger-bundle-v3"
LEDGER_FILENAME = "current-coverage-ledger.json"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {LEDGER_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
)

SCOPE_POLICY = {
    "benchmark_parity_claimed": False,
    "cross_artifact_counts_are_additive": False,
    "global_completeness_claimed": False,
    "local_restricted_excluded_from_public_scope": True,
    "public_open_is_current_redistribution_scope": True,
    "review_only_is_confirmed_data_centre_evidence": False,
    "source_scoped_rows_are_unique_physical_sites": False,
    "unique_physical_site_count": None,
}

SCOPE_POLICY_V2 = {
    **SCOPE_POLICY,
    "construction_arithmetic_across_entity_levels_performed": False,
    "metadata_or_calibration_counts_are_public_row_release_counts": False,
    "non_site_record_units_are_unique_physical_sites": False,
    "parcels_applications_permits_and_footprints_are_additive": False,
    "publication_modes_are_kept_separate": True,
}

ARTIFACT_KINDS = frozenset(
    {
        "analyst_imagery_review",
        "bounded_discovery_pilot",
        "candidate_fusion",
        "construction_map",
        "construction_master",
        "coverage_audit",
        "cross_release_resolution",
        "federated_release_index",
        "source_rights_assessment",
        "source_scoped_release",
        "satellite_catalog_batch",
        "satellite_review_queue",
    }
)
ACCESS_TIERS = frozenset({"local_restricted", "public_open"})
REDISTRIBUTION_STATUSES = frozenset(
    {
        "eligible_with_upstream_terms",
        "metadata_only_no_source_rows",
        "quarantined_pending_rights",
    }
)
EVIDENCE_SCOPES = frozenset(
    {
        "metadata_only",
        "mixed_source_scoped_and_review",
        "review_only",
        "source_scoped",
    }
)
CURRENT_ROLES = frozenset(
    {
        "authoritative_public_core",
        "public_supporting_review_lane",
        "rights_gate",
        "local_restricted_research",
    }
)
PUBLICATION_MODES = frozenset(
    {
        "local_quarantined",
        "public_index_or_audit",
        "public_metadata_or_aggregate_only",
        "public_review_or_discovery",
        "public_row_release",
    }
)
RECORD_UNITS = frozenset(
    {
        "advertised_source_record",
        "aggregate_report_metric",
        "air_permit_application_record",
        "building_footprint_record",
        "building_record",
        "campus_project_record",
        "candidate_record",
        "catalog_job",
        "catalog_link",
        "capacity_observation",
        "construction_master_row",
        "construction_pipeline_record",
        "coverage_gap",
        "crosswalk_link",
        "facility_record",
        "issued_air_permit_record",
        "parcel_record",
        "planning_application_record",
        "planning_observation_record",
        "project_record",
        "review_record",
        "source_scoped_entity_row",
    }
)
PARITY_GAP_STATUSES = frozenset(
    {"not_computed", "partial_coverage", "review_backlog", "rights_blocked"}
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
V5_LEDGER_ID = "current-coverage-2026-07-18-v5"
V6_LEDGER_ID = "current-coverage-2026-07-19-v6"
V7_LEDGER_ID = "current-coverage-2026-07-19-v7"
V8_LEDGER_ID = "current-coverage-2026-07-19-v8"
V9_LEDGER_ID = "current-coverage-2026-07-19-v9"
V10_LEDGER_ID = "current-coverage-2026-07-20-v10"
V12_LEDGER_ID = "current-coverage-2026-07-20-v12"
V13_LEDGER_ID = "current-coverage-2026-07-20-v13"
_FROZEN_LEDGER_ID_RE = re.compile(r"^current-coverage-\d{4}-\d{2}-\d{2}-v\d+$")
_SUPPORTED_FROZEN_LEDGER_IDS = frozenset(
    {
        "current-coverage-2026-07-18-v1",
        "current-coverage-2026-07-18-v2",
        "current-coverage-2026-07-18-v3",
        "current-coverage-2026-07-18-v4",
        V5_LEDGER_ID,
        V6_LEDGER_ID,
        V7_LEDGER_ID,
        V8_LEDGER_ID,
        V9_LEDGER_ID,
        V10_LEDGER_ID,
        V12_LEDGER_ID,
        V13_LEDGER_ID,
    }
)
_V5_ARTIFACT_IDS = (
    "candidate-fusion-osm-planet-priority-v13",
    "cleanview-rights-assessment-v1",
    "construction-map-public-open-v5",
    "construction-master-public-open-v5",
    "coverage-audit-four-layer-v1",
    "coverage-audit-public-open-v1",
    "edgemode-sec-assessment-v1",
    "england-planning-data-2026-07-18-v1",
    "epa-echo-frs-local-review-v1",
    "federation-four-layer-v2",
    "federation-public-open-v1",
    "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1",
    "gdelt-news-review-pilot",
    "gdelt-news-triage-pilot",
    "global-open-v3",
    "ireland-planning-observations-v1",
    "loudoun-data-center-assessment-v1",
    "microsoft-global-ml-buildings-review-v1",
    "netherlands-koop-official-publications-2026-07-18-v1",
    "new-zealand-fast-track-2026-07-18-v1",
    "nsw-major-projects-data-storage-2026-07-18-v1",
    "open-buildings-temporal-review-v2",
    "open-buildings-temporal-source-v2",
    "osm-fuzzy-global-open-v3-crosswalk-v2",
    "osm-fuzzy-review-v2",
    "osm-planet-structural-construction-v3",
    "overture-memphis-pilot",
    "peeringdb-rights-assessment-v1",
    "pjm-large-load-assessment-v1",
    "pwc-build-out-assessment-v1",
    "satellite-active-batch-001",
    "satellite-calibration-analyst-reviews-v4",
    "satellite-proposed-batch-001",
    "satellite-queue-global-open-v3",
    "satellite-unknown-batch-015",
    "scrutica-global-open-v3-crosswalk-v3",
    "scrutica-release-2026-07-18",
    "seed-epoch-official-v1",
    "virginia-deq-air-permits-local-review-v1",
    "within-release-resolution-public-open-v1",
)
_V5_EXACT_CURRENT_CHECKPOINTS = {
    "candidate-fusion-osm-planet-priority-v13": {
        "coverage": (
            "candidate_fusion/2026-07-18-osm-planet-priority-v13/coverage.json",
            "c05f3eabf7afa0165d3fa2f9fbba3a3051ce88d2e7aed3bf46fdd8967e2942bf",
        ),
        "definition": (
            "sources/candidate-fusion-2026-07-18-osm-planet-v13.json",
            "63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33",
        ),
        "manifest": (
            "candidate_fusion/2026-07-18-osm-planet-priority-v13/manifest.json",
            "12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9",
        ),
    },
    "construction-map-public-open-v5": {
        "coverage": (
            "construction_maps/2026-07-18-public-open-v5/coverage.json",
            "1ba5141180acdac46c1c1b9c104c75f459f8252dc1b16d941c97f8df90b5c9de",
        ),
        "definition": (
            "sources/construction-map-2026-07-18-public-open-v5.json",
            "cc21bbc7f2ee0bd9e043dd8fde8c477632e9d6f301e9da77cb43500e8781da07",
        ),
        "manifest": (
            "construction_maps/2026-07-18-public-open-v5/manifest.json",
            "f1820bced7d1641ac9cb8821a70e0ba148c2b390980654accbef852fa8798030",
        ),
    },
    "construction-master-public-open-v5": {
        "coverage": (
            "construction_master/2026-07-18-public-open-v5/coverage.json",
            "8e791b8e7503e5e9f8674f1e82fd34b9641ff4453875e31205b1966758a1e5cb",
        ),
        "definition": (
            "sources/construction-master-2026-07-18-public-open-v5.json",
            "2438b76b58e985346e1c688d9a4fcba92fc4d0dbac23d383e0f52bbf529d88b4",
        ),
        "manifest": (
            "construction_master/2026-07-18-public-open-v5/manifest.json",
            "3f3b4fad0dc16e42d0e8a3507c6e9cc2d83a76ecf695032b6eb34f5a946a9cd5",
        ),
    },
    "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1": {
        "assessment": (
            "source_assessments/france-igedd-ae-data-centres-2009-2026-2026-07-18-v1/assessment.json",
            "9f0f7a9884662795eb14889f7b901098ce832cefddd4086204273e6b76473e32",
        ),
        "definition": (
            "sources/france-igedd-ae-data-centres-2009-2026-2026-07-18-v1.json",
            "1d8bc43fe7a1c9d4d88b87302c2fc292039e003f1b5e695c3fc898581ed12138",
        ),
        "manifest": (
            "source_assessments/france-igedd-ae-data-centres-2009-2026-2026-07-18-v1/manifest.json",
            "aef3c9b21a07d436bd48eafc26fb67e9ea81dbbb827f76429f66e65708307e49",
        ),
    },
    "netherlands-koop-official-publications-2026-07-18-v1": {
        "assessment": (
            "source_assessments/netherlands-koop-official-publications-2026-07-18-v1/assessment.json",
            "2cdf1f78b80173c369634936742e8ce9464d10dda7a8d791f770bc65095b0a1f",
        ),
        "definition": (
            "sources/netherlands-koop-official-publications-2026-07-18-v1.json",
            "ee23b0cd9b7e1584b48579f79a4451bf4de1b7392a1c58d13280cb7dbef78847",
        ),
        "manifest": (
            "source_assessments/netherlands-koop-official-publications-2026-07-18-v1/manifest.json",
            "2fc151a0088f4d03cba8985fb45552400236518cd9022672d49280ab9d4d9cd2",
        ),
    },
    "new-zealand-fast-track-2026-07-18-v1": {
        "assessment": (
            "source_assessments/new-zealand-fast-track-2026-07-18-v1/assessment.json",
            "40fb2a39f548cf8902aba1e991b6719291265a01e521ba200f1693061606b7d7",
        ),
        "definition": (
            "sources/new-zealand-fast-track-2026-07-18-v1.json",
            "d06491aa46e4eeab7f04a86f5a04477807dd179d572ac71a7e401f99a15fbe53",
        ),
        "manifest": (
            "source_assessments/new-zealand-fast-track-2026-07-18-v1/manifest.json",
            "97e9b78cc516acd48e6d3e3f80d367977bc7ae3b882820dc3e0f7e185b6cb264",
        ),
    },
    "satellite-calibration-analyst-reviews-v4": {
        "definition": (
            "sources/satellite-calibration-2026-07-18-analyst-reviews-v4.json",
            "876d88ff2c8ad137799714408b39016bf10b12820f637c3c2ff9ab3f30283414",
        ),
        "manifest": (
            "satellite_calibration/2026-07-18-analyst-reviews-v4/manifest.json",
            "a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41",
        ),
        "summary": (
            "satellite_calibration/2026-07-18-analyst-reviews-v4/summary.json",
            "6b8261b0f8040c156283f530232ac969ec079cd8b298bdde5b84ab638e331a0f",
        ),
    },
    "satellite-unknown-batch-015": {
        "manifest": (
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-015/batch-manifest.json",
            "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8",
        ),
    },
}
_V5_PARITY_GAP_IDS = {
    "benchmark-parity-not-computed",
    "global-construction-coverage-partial",
    "rights-blocked-source-lanes",
    "satellite-review-backlog",
    "site-resolution-partial",
    "type-power-energy-coverage-partial",
}
_V5_PUBLICATION_MODE_COUNTS = {
    "local_quarantined": 6,
    "public_index_or_audit": 4,
    "public_metadata_or_aggregate_only": 5,
    "public_review_or_discovery": 20,
    "public_row_release": 5,
}
_V6_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v5": "construction-map-public-open-v10",
    "construction-master-public-open-v5": "construction-master-public-open-v10",
    "coverage-audit-public-open-v1": "coverage-audit-public-open-v9",
    "federation-public-open-v1": "federation-public-open-v8",
    "satellite-unknown-batch-015": "satellite-unknown-batch-030",
    "seed-epoch-official-v1": "seed-epoch-official-v13",
}
_V6_ARTIFACT_IDS = tuple(
    _V6_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
    for artifact_id in _V5_ARTIFACT_IDS
)
_V6_EXACT_CURRENT_CHECKPOINTS = {
    "candidate-fusion-osm-planet-priority-v13": (
        _V5_EXACT_CURRENT_CHECKPOINTS["candidate-fusion-osm-planet-priority-v13"]
    ),
    "construction-map-public-open-v10": {
        "coverage": (
            "construction_maps/2026-07-19-public-open-v10/coverage.json",
            "6146cf3edcb985c67da872c76745f7346d20ca0c11bc8bc8b6964446c49069da",
        ),
        "definition": (
            "sources/construction-map-2026-07-19-public-open-v10.json",
            "e713cc3c18823c26cd3759fb5a1522b0c0d25771bacaf96cd0472af5fd960383",
        ),
        "manifest": (
            "construction_maps/2026-07-19-public-open-v10/manifest.json",
            "5b57a6655e11c424b79bf820673c2e55d9cd2eb4687ed1d1c9bca163421e556f",
        ),
    },
    "construction-master-public-open-v10": {
        "coverage": (
            "construction_master/2026-07-19-public-open-v10/coverage.json",
            "6c6bb9c0d90267003e0f376e7d79f13638687b7d81207371b774146dc6d7b061",
        ),
        "definition": (
            "sources/construction-master-2026-07-19-public-open-v10.json",
            "aa252132da08ee5f224097dfcbf50dbdbe9e7e5a1416b58e85af304030a3fa34",
        ),
        "manifest": (
            "construction_master/2026-07-19-public-open-v10/manifest.json",
            "739f340d9413c9a54b5f38174cc5808620326cd1cf6aa59a85738027ff5c2bbb",
        ),
    },
    "coverage-audit-public-open-v9": {
        "manifest": (
            "audits/2026-07-19-public-open-coverage-v9/manifest.json",
            "657216c910e300314f691e1e726a188c24095bd7b4ec000a97d2a4db7e4ff247",
        ),
    },
    "federation-public-open-v8": {
        "index": (
            "federated_indexes/2026-07-19-public-open-v8/federated-index.json",
            "75737e6175f4de03f84e9b0cead12e92cf5fcdfa9e59a85ba845bd0a7fa60bd4",
        ),
        "manifest": (
            "federated_indexes/2026-07-19-public-open-v8/manifest.json",
            "0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48",
        ),
    },
    "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1": (
        _V5_EXACT_CURRENT_CHECKPOINTS[
            "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1"
        ]
    ),
    "netherlands-koop-official-publications-2026-07-18-v1": (
        _V5_EXACT_CURRENT_CHECKPOINTS[
            "netherlands-koop-official-publications-2026-07-18-v1"
        ]
    ),
    "new-zealand-fast-track-2026-07-18-v1": (
        _V5_EXACT_CURRENT_CHECKPOINTS[
            "new-zealand-fast-track-2026-07-18-v1"
        ]
    ),
    "satellite-calibration-analyst-reviews-v4": (
        _V5_EXACT_CURRENT_CHECKPOINTS[
            "satellite-calibration-analyst-reviews-v4"
        ]
    ),
    "satellite-unknown-batch-030": {
        "manifest": (
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-030/batch-manifest.json",
            "18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053",
        ),
    },
    "seed-epoch-official-v13": {
        "manifest": (
            "releases/2026-07-19-open-seed-v13/manifest.json",
            "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7",
        ),
    },
}
_V6_PARITY_GAP_IDS = _V5_PARITY_GAP_IDS
_V6_PUBLICATION_MODE_COUNTS = _V5_PUBLICATION_MODE_COUNTS
_V7_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v10": "construction-map-public-open-v11",
    "construction-master-public-open-v10": "construction-master-public-open-v11",
    "coverage-audit-public-open-v9": "coverage-audit-public-open-v10",
    "federation-public-open-v8": "federation-public-open-v9",
    "seed-epoch-official-v13": "seed-epoch-official-v20",
}
_V7_ARTIFACT_IDS = tuple(
    _V7_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
    for artifact_id in _V6_ARTIFACT_IDS
)
_V7_EXACT_CURRENT_CHECKPOINTS = {
    artifact_id: checkpoints
    for artifact_id, checkpoints in _V6_EXACT_CURRENT_CHECKPOINTS.items()
    if artifact_id not in _V7_ARTIFACT_REPLACEMENTS
}
_V7_EXACT_CURRENT_CHECKPOINTS.update(
    {
        "construction-map-public-open-v11": {
            "coverage": (
                "construction_maps/2026-07-19-public-open-v11/coverage.json",
                "7b19c8a4303fe3b75e6075cf5d8b3167bbce22527de38ecbbb0e924ce68c2d3e",
            ),
            "definition": (
                "sources/construction-map-2026-07-19-public-open-v11.json",
                "2af41d8d846ea56fbf68a0489e708973ea087351349fb3adc386cc3e3c268986",
            ),
            "manifest": (
                "construction_maps/2026-07-19-public-open-v11/manifest.json",
                "e9aa6e9778edba365572eb92bc87b0612e6daf1f02387eac96046c935ce2c56c",
            ),
        },
        "construction-master-public-open-v11": {
            "coverage": (
                "construction_master/2026-07-19-public-open-v11/coverage.json",
                "38e4306a57127a412939532104255a881eb9d24671f47ee83420efcec949daa8",
            ),
            "definition": (
                "sources/construction-master-2026-07-19-public-open-v11.json",
                "1689dd992ae482dbf464c42300fb0b32289c2d795b6edce2d4b1ac8f6a7fb65c",
            ),
            "manifest": (
                "construction_master/2026-07-19-public-open-v11/manifest.json",
                "dd0648d98e27d2f11b1ce117c92e45647d00b9226083f54025c27e0979e5f951",
            ),
        },
        "coverage-audit-public-open-v10": {
            "manifest": (
                "audits/2026-07-19-public-open-coverage-v10/manifest.json",
                "ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e",
            ),
        },
        "federation-public-open-v9": {
            "index": (
                "federated_indexes/2026-07-19-public-open-v9/federated-index.json",
                "600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1",
            ),
            "manifest": (
                "federated_indexes/2026-07-19-public-open-v9/manifest.json",
                "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5",
            ),
        },
        "seed-epoch-official-v20": {
            "manifest": (
                "releases/2026-07-19-open-seed-v20/manifest.json",
                "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456",
            ),
        },
    }
)
_V7_PARITY_GAP_IDS = _V6_PARITY_GAP_IDS
_V7_PUBLICATION_MODE_COUNTS = _V6_PUBLICATION_MODE_COUNTS
_V8_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v11": "construction-map-public-open-v12",
    "construction-master-public-open-v11": "construction-master-public-open-v12",
    "coverage-audit-public-open-v10": "coverage-audit-public-open-v11",
    "federation-public-open-v9": "federation-public-open-v10",
    "seed-epoch-official-v20": "seed-epoch-official-v30",
}
_V8_ARTIFACT_IDS = tuple(
    _V8_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
    for artifact_id in _V7_ARTIFACT_IDS
)
_V8_EXACT_CURRENT_CHECKPOINTS = {
    artifact_id: checkpoints
    for artifact_id, checkpoints in _V7_EXACT_CURRENT_CHECKPOINTS.items()
    if artifact_id not in _V8_ARTIFACT_REPLACEMENTS
}
_V8_EXACT_CURRENT_CHECKPOINTS.update(
    {
        "construction-map-public-open-v12": {
            "coverage": (
                "construction_maps/2026-07-19-public-open-v12/coverage.json",
                "63af71077ec6712f5c1dcd2cdc4fcd7591a1530999750b4d11a3e9a62d01ef65",
            ),
            "definition": (
                "sources/construction-map-2026-07-19-public-open-v12.json",
                "aa94b20bd4e3264ead3756fd21e31fcea0a26fd8084e7511f970a9aad34644a2",
            ),
            "manifest": (
                "construction_maps/2026-07-19-public-open-v12/manifest.json",
                "2e5d68db464ef88cea1df4477b8adc75a4a79b197c246adeaa8771cef65756e7",
            ),
        },
        "construction-master-public-open-v12": {
            "coverage": (
                "construction_master/2026-07-19-public-open-v12/coverage.json",
                "be938a2ff916b2dc66dca75d19b48e3c27287101941d3282b12cc134cf66cf4d",
            ),
            "definition": (
                "sources/construction-master-2026-07-19-public-open-v12.json",
                "286e60979bb313d0ca085ae1980009427e50521b520c6d47425452f5af9c45c5",
            ),
            "manifest": (
                "construction_master/2026-07-19-public-open-v12/manifest.json",
                "f11a800cbaccacfc9204362d63ac08df1cdd580b5bbb5ede2d1da1e7f39a18cc",
            ),
        },
        "coverage-audit-public-open-v11": {
            "manifest": (
                "audits/2026-07-19-public-open-coverage-v11/manifest.json",
                "edf1b0cdf1e842b1ea8a848c1e07d0c5cb0860b34fe267798daeef0158a0ea2c",
            ),
        },
        "federation-public-open-v10": {
            "index": (
                "federated_indexes/2026-07-19-public-open-v10/federated-index.json",
                "aa6b55f29d237aa298cc6d2f3dfe5dfd57ed7bbd1ef6bd63688efd6be1e38251",
            ),
            "manifest": (
                "federated_indexes/2026-07-19-public-open-v10/manifest.json",
                "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2",
            ),
        },
        "seed-epoch-official-v30": {
            "manifest": (
                "releases/2026-07-19-open-seed-v30/manifest.json",
                "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619",
            ),
        },
    }
)
_V8_PARITY_GAP_IDS = _V7_PARITY_GAP_IDS
_V8_PUBLICATION_MODE_COUNTS = _V7_PUBLICATION_MODE_COUNTS
_V9_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v12": "construction-map-public-open-v13",
    "construction-master-public-open-v12": "construction-master-public-open-v13",
    "coverage-audit-public-open-v11": "coverage-audit-public-open-v12",
    "federation-public-open-v10": "federation-public-open-v11",
    "seed-epoch-official-v30": "seed-epoch-official-v32",
}
_V9_ARTIFACT_IDS = tuple(
    _V9_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
    for artifact_id in _V8_ARTIFACT_IDS
)
_V9_EXACT_CURRENT_CHECKPOINTS = {
    artifact_id: checkpoints
    for artifact_id, checkpoints in _V8_EXACT_CURRENT_CHECKPOINTS.items()
    if artifact_id not in _V9_ARTIFACT_REPLACEMENTS
}
_V9_EXACT_CURRENT_CHECKPOINTS.update(
    {
        "construction-map-public-open-v13": {
            "coverage": (
                "construction_maps/2026-07-19-public-open-v13/coverage.json",
                "c1b08000f674ff29598041433f5c2d88e1785bcfc5d9dbde6c11e27b57d59e51",
            ),
            "definition": (
                "sources/construction-map-2026-07-19-public-open-v13.json",
                "56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483",
            ),
            "manifest": (
                "construction_maps/2026-07-19-public-open-v13/manifest.json",
                "0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49",
            ),
        },
        "construction-master-public-open-v13": {
            "coverage": (
                "construction_master/2026-07-19-public-open-v13/coverage.json",
                "a55236fe69909486cc6457df186db43a5b86c24a85340658c28ab6a8f60607f8",
            ),
            "definition": (
                "sources/construction-master-2026-07-19-public-open-v13.json",
                "6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07",
            ),
            "manifest": (
                "construction_master/2026-07-19-public-open-v13/manifest.json",
                "d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0",
            ),
        },
        "coverage-audit-public-open-v12": {
            "manifest": (
                "audits/2026-07-19-public-open-coverage-v12/manifest.json",
                "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77",
            ),
        },
        "federation-public-open-v11": {
            "index": (
                "federated_indexes/2026-07-19-public-open-v11/federated-index.json",
                "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd",
            ),
            "manifest": (
                "federated_indexes/2026-07-19-public-open-v11/manifest.json",
                "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4",
            ),
        },
        "seed-epoch-official-v32": {
            "manifest": (
                "releases/2026-07-19-open-seed-v32/manifest.json",
                "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c",
            ),
        },
    }
)
_V9_PARITY_GAP_IDS = _V8_PARITY_GAP_IDS
_V9_PUBLICATION_MODE_COUNTS = _V8_PUBLICATION_MODE_COUNTS
_V10_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v13": "construction-map-public-open-v14",
    "construction-master-public-open-v13": "construction-master-public-open-v14",
    "coverage-audit-public-open-v12": "coverage-audit-public-open-v13",
    "federation-public-open-v11": "federation-public-open-v12",
    "seed-epoch-official-v32": "seed-epoch-official-v33",
}
_V10_RECOVERY_ARTIFACT_ID = "satellite-recovery-unknown033-review-v1"
_V10_ARTIFACT_IDS = tuple(
    sorted(
        [
            _V10_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in _V9_ARTIFACT_IDS
        ]
        + [_V10_RECOVERY_ARTIFACT_ID]
    )
)
_V10_EXACT_CURRENT_CHECKPOINTS = {
    artifact_id: checkpoints
    for artifact_id, checkpoints in _V9_EXACT_CURRENT_CHECKPOINTS.items()
    if artifact_id not in _V10_ARTIFACT_REPLACEMENTS
}
_V10_EXACT_CURRENT_CHECKPOINTS.update(
    {
        "construction-map-public-open-v14": {
            "coverage": (
                "construction_maps/2026-07-19-public-open-v14/coverage.json",
                "fe94ab7e269e7c3c345a13eea1b7949ba899f5b77ca82a100b5044695dffcf54",
            ),
            "definition": (
                "sources/construction-map-2026-07-19-public-open-v14.json",
                "7ad7320bbbb8d1ae4bef56363177fe904891be9527e35e31eedc9103b1122db9",
            ),
            "manifest": (
                "construction_maps/2026-07-19-public-open-v14/manifest.json",
                "85f102967b8a6329c6d4466e61d1773132ee71b92cad05fc014b475eb0ef75f1",
            ),
        },
        "construction-master-public-open-v14": {
            "coverage": (
                "construction_master/2026-07-19-public-open-v14/coverage.json",
                "ed141878efeedae901e86eeabf8e0ac15cb69f046af1f80fb80e0be16e95600c",
            ),
            "definition": (
                "sources/construction-master-2026-07-19-public-open-v14.json",
                "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4",
            ),
            "manifest": (
                "construction_master/2026-07-19-public-open-v14/manifest.json",
                "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b",
            ),
        },
        "coverage-audit-public-open-v13": {
            "manifest": (
                "audits/2026-07-19-public-open-coverage-v13/manifest.json",
                "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d",
            ),
        },
        "federation-public-open-v12": {
            "index": (
                "federated_indexes/2026-07-19-public-open-v12/federated-index.json",
                "266afde03fbb9eca16a0a9bfbd64c47fd50447b1b805da15542ff617f1629772",
            ),
            "manifest": (
                "federated_indexes/2026-07-19-public-open-v12/manifest.json",
                "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f",
            ),
        },
        "satellite-recovery-unknown033-review-v1": {
            "acceptance": (
                "definitions/satellite_recoveries/accepted-2026-07-20-v1.json",
                "507b606c4ab65605766d7726072d715649830467838d9d24d423ba3b8aac59ad",
            ),
            "definition": (
                "definitions/satellite_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25.json",
                "1b054ac9c1091e1470576fcf9f14df05a64cb6d679a22ab413430957ffbcb420",
            ),
            "manifest": (
                "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25/recovery-manifest.json",
                "178f52ad3c42117ea19561c123eef87fe1ed7331c79e9c5c1596bd8d2b7cbfb1",
            ),
        },
        "seed-epoch-official-v33": {
            "manifest": (
                "releases/2026-07-19-open-seed-v33/manifest.json",
                "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4",
            ),
        },
    }
)
_V10_PARITY_GAP_IDS = _V9_PARITY_GAP_IDS
_V10_PUBLICATION_MODE_COUNTS = {
    **_V9_PUBLICATION_MODE_COUNTS,
    "public_review_or_discovery": (
        _V9_PUBLICATION_MODE_COUNTS["public_review_or_discovery"] + 1
    ),
}
_V10_EXACT_RECOVERY_METRICS = {
    "atlas_release_integration": False,
    "recovered_batch_completed_jobs": 4_375,
    "recovered_batch_failed_jobs": 0,
    "recovered_batch_pending_jobs": 2_061,
    "recovered_batch_unavailable_no_scene_jobs": 300,
    "recovered_selected_jobs": 25,
    "selection_later_job_leakage": 0,
    "source_batch_promoted": False,
    "unique_physical_sites": None,
}
_V12_ARTIFACT_REPLACEMENTS = {
    "coverage-audit-public-open-v13": "coverage-audit-public-open-v17",
    "federation-public-open-v12": "federation-public-open-v18",
    "seed-epoch-official-v33": "seed-epoch-official-v42",
}
_V12_RECOVERY_ARTIFACT_ID = _V10_RECOVERY_ARTIFACT_ID
_V12_ARTIFACT_IDS = tuple(
    sorted(
        _V12_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
        for artifact_id in _V10_ARTIFACT_IDS
    )
)
_V12_EXACT_CURRENT_CHECKPOINTS = {
    artifact_id: checkpoints
    for artifact_id, checkpoints in _V10_EXACT_CURRENT_CHECKPOINTS.items()
    if artifact_id not in _V12_ARTIFACT_REPLACEMENTS
}
_V12_EXACT_CURRENT_CHECKPOINTS.update(
    {
        "coverage-audit-public-open-v17": {
            "manifest": (
                "audits/2026-07-20-public-open-coverage-v17/manifest.json",
                "37807873e8dc0009d31b1a1eb8d4d6cc4dd2dceb88a1ab52076c166e37f04755",
            ),
        },
        "federation-public-open-v18": {
            "index": (
                "federated_indexes/2026-07-20-public-open-v18/federated-index.json",
                "45048828bf4cc90e1c70fd0da86962c5a0bc0a00d588ad8c3f22e35e2597f6df",
            ),
            "manifest": (
                "federated_indexes/2026-07-20-public-open-v18/manifest.json",
                "3f52b09facdaa5bbea82bbef045e459901a6f3206452271482d0ea798a7f28d6",
            ),
        },
        "seed-epoch-official-v42": {
            "manifest": (
                "releases/2026-07-20-open-seed-v42/manifest.json",
                "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680",
            ),
        },
    }
)
_V12_EXACT_METRICS = {
    "coverage-audit-public-open-v17": {
        "coverage_groups": 526,
        "non_review_source_scoped_rows": 9_797,
        "open_gaps": 2_845,
        "review_only_source_scoped_rows": 6_130,
        "source_scoped_rows": 15_927,
        "unique_physical_sites": None,
    },
    "federation-public-open-v18": {
        "capacity_observations": 1_213,
        "construction_pipeline_records": 6_512,
        "non_review_construction_pipeline_records": 382,
        "non_review_source_scoped_rows": 9_797,
        "review_only_construction_pipeline_records": 6_130,
        "review_only_source_scoped_rows": 6_130,
        "source_scoped_rows": 15_927,
        "unique_physical_sites": None,
    },
    "satellite-recovery-unknown033-review-v1": _V10_EXACT_RECOVERY_METRICS,
    "seed-epoch-official-v42": {
        "capacity_observations": 427,
        "construction_pipeline_records": 262,
        "construction_source_signals": 187,
        "evidence_records": 273,
        "resolution_candidates": 4,
        "source_scoped_entity_rows": 502,
    },
}
_V12_EXACT_CHILD_DEFINITIONS = {
    "coverage": (
        "sources/coverage-audit-2026-07-20-public-open-v17.json",
        "964926e8432b4bf83233201c07cad0c40dc2fc34d9d4b1f89cd871f51c461f3d",
    ),
    "federation": (
        "sources/federation-2026-07-20-public-open-v18.json",
        "bab7ae5e2f09e34d658663112c70b88ac3ca3b02a075380356cfe3f7af7298d0",
    ),
    "seed": (
        "sources/open-seed-2026-07-20-v42.json",
        "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f",
    ),
}
_V12_COVERAGE_AUDIT_SHA256 = (
    "925abb9218e11a31a423348cb3ba29b722e98aa844d23f04e68569251faa9cf7"
)
_V12_PARITY_GAP_IDS = _V10_PARITY_GAP_IDS
_V12_PUBLICATION_MODE_COUNTS = _V10_PUBLICATION_MODE_COUNTS
_V12_DEFINITION_SHA256 = (
    "f1f365a517179b2526911665161c76ff59865b6e4fd14fcddf3361f490a3a72a"
)
_V13_GENERATED_AT = "2026-07-20T06:51:51Z"
_V13_DEFINITION_SHA256 = (
    "7e23abc7be3c6a3e898c640960912a308297bf02aee22b86638a66b350d19cc5"
)
_V13_BASE_LINEAGE = {
    "definition": {
        "bytes": 122_646,
        "path": "sources/current-coverage-2026-07-20-v12.json",
        "sha256": _V12_DEFINITION_SHA256,
    },
    "ledger": {
        "bytes": 82_572,
        "path": (
            "current_coverage_ledgers/2026-07-20-v12/"
            "current-coverage-ledger.json"
        ),
        "sha256": "ec93020a2794221961639b935003732568c10a5b4158143e7258a1d835d6a988",
    },
    "ledger_id": V12_LEDGER_ID,
    "manifest": {
        "bytes": 22_045,
        "path": "current_coverage_ledgers/2026-07-20-v12/manifest.json",
        "sha256": "a7b5e3522c90301020db2d47fa6e1f10830f82524be559967df9aa18896ff412",
    },
}
_V13_ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v14": "construction-map-public-open-v16",
    "construction-master-public-open-v14": "construction-master-public-open-v16",
}
_V13_OLD_CONSTRUCTION_IDS = frozenset(_V13_ARTIFACT_REPLACEMENTS)
_V13_NEW_CONSTRUCTION_IDS = frozenset(_V13_ARTIFACT_REPLACEMENTS.values())
_V13_ARTIFACT_IDS = tuple(
    sorted(
        _V13_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
        for artifact_id in _V12_ARTIFACT_IDS
    )
)
_V13_EXACT_CURRENT_CHECKPOINTS = {
    "construction-map-public-open-v16": {
        "coverage": (
            "construction_maps/2026-07-20-public-open-v16/coverage.json",
            "f293fea7fb94768932da8b3260901c8b7faed01485235e5ad6570cda497a32e1",
        ),
        "definition": (
            "sources/construction-map-2026-07-20-public-open-v16.json",
            "cdbcf7f9f71e451ef6a298102866ea6715cec022ab4f1315d61bea682939a0d4",
        ),
        "manifest": (
            "construction_maps/2026-07-20-public-open-v16/manifest.json",
            "ee8dbdd2c0a050695b739af59ee167fb40edefb4cc8c68261fb36eabc1a29fe2",
        ),
    },
    "construction-master-public-open-v16": {
        "coverage": (
            "construction_master/2026-07-20-public-open-v16/coverage.json",
            "c1870a0dfa329ae9bd204e623ceaf87f0844d0b1fb811674e19d317fde2fd9cd",
        ),
        "definition": (
            "sources/construction-master-2026-07-20-public-open-v16.json",
            "541fddec96e1ef309219ee648d6d9c8fa0e99dbf6db09619d89cb5d05b423be6",
        ),
        "manifest": (
            "construction_master/2026-07-20-public-open-v16/manifest.json",
            "a43846e71f07b4eb9ac10643caf71c907a837537ba1ec994caa70a366e45908f",
        ),
    },
}
_V13_EXACT_METRICS = {
    "construction-map-public-open-v16": {
        "added_replacement_rows_unmapped": 63,
        "default_visible_rows": 6_479,
        "mapped_replacement_rows": 80,
        "mapped_rows_with_any_role": 66,
        "mapped_tier_a_rows": 199,
        "mapped_tier_b_rows": 6_280,
        "mapped_tier_c_rows": 102_494,
        "mapped_total_rows": 108_973,
        "mapped_unknown_country_rows": 102_541,
        "master_total_rows": 109_174,
        "unique_physical_sites": None,
        "unmapped_rows": 201,
    },
    "construction-master-public-open-v16": {
        "added_replacement_rows": 63,
        "base_rows": 109_111,
        "contract_marked_rows": 262,
        "inherited_rows": 108_912,
        "publication_contract_version": 4,
        "replacement_rows": 262,
        "role_rows_with_any_role": 89,
        "role_rows_with_customers": 1,
        "role_rows_with_operator": 30,
        "role_rows_with_owner": 46,
        "role_rows_with_source_role_tags": 50,
        "role_rows_with_tenants": 4,
        "role_rows_with_users": 36,
        "satellite_recovery_control_plane_bytes": 15_313,
        "satellite_recovery_control_plane_files": 4,
        "satellite_recovery_rows": 0,
        "tier_a_rows": 382,
        "tier_b_rows": 6_298,
        "tier_c_rows": 102_494,
        "total_master_rows": 109_174,
        "unchanged_replacement_rows": 199,
        "unique_physical_sites": None,
    },
}
_V13_EXACT_FILES = {
    "construction-map definition": (
        "sources/construction-map-2026-07-20-public-open-v16.json",
        2_440,
        "cdbcf7f9f71e451ef6a298102866ea6715cec022ab4f1315d61bea682939a0d4",
    ),
    "construction-map coverage": (
        "construction_maps/2026-07-20-public-open-v16/coverage.json",
        7_342,
        "f293fea7fb94768932da8b3260901c8b7faed01485235e5ad6570cda497a32e1",
    ),
    "construction-map manifest": (
        "construction_maps/2026-07-20-public-open-v16/manifest.json",
        2_192,
        "ee8dbdd2c0a050695b739af59ee167fb40edefb4cc8c68261fb36eabc1a29fe2",
    ),
    "construction-master definition": (
        "sources/construction-master-2026-07-20-public-open-v16.json",
        5_655,
        "541fddec96e1ef309219ee648d6d9c8fa0e99dbf6db09619d89cb5d05b423be6",
    ),
    "construction-master coverage": (
        "construction_master/2026-07-20-public-open-v16/coverage.json",
        8_492,
        "c1870a0dfa329ae9bd204e623ceaf87f0844d0b1fb811674e19d317fde2fd9cd",
    ),
    "construction-master manifest": (
        "construction_master/2026-07-20-public-open-v16/manifest.json",
        9_667,
        "a43846e71f07b4eb9ac10643caf71c907a837537ba1ec994caa70a366e45908f",
    ),
}
_V13_PUBLICATION_MODE_COUNTS = _V12_PUBLICATION_MODE_COUNTS


class CurrentCoverageError(ValueError):
    """Raised when a definition, checkpoint, or ledger fails closed."""


@dataclass(frozen=True, slots=True)
class CurrentCoverageBundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CurrentCoverageError(f"{label} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageError(f"{label} must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CurrentCoverageError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise CurrentCoverageError(
            f"{label} must be canonical UTC with whole seconds"
        )
    return value


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CurrentCoverageError(f"{label} must be a JSON object")
    return value


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _package_relative_path(package_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CurrentCoverageError(f"{label} must be a non-empty path")
    supplied = Path(value)
    if supplied.is_absolute() or supplied != Path(*supplied.parts):
        raise CurrentCoverageError(f"{label} must be a normalized relative path")
    if any(part in {"", ".", ".."} for part in supplied.parts):
        raise CurrentCoverageError(f"{label} may not contain dot segments")
    resolved = (package_root / supplied).resolve()
    root = package_root.resolve()
    if root not in resolved.parents:
        raise CurrentCoverageError(f"{label} escapes the package root")
    return resolved


def _json_pointer(document: Any, pointer: Any, label: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise CurrentCoverageError(f"{label} must be a non-root JSON pointer")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise CurrentCoverageError(f"{label} does not resolve: {pointer}")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise CurrentCoverageError(f"{label} does not resolve: {pointer}")
            current = current[int(token)]
        else:
            raise CurrentCoverageError(f"{label} does not resolve: {pointer}")
    return current


def _validate_v5_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V5_LEDGER_ID:
        return
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v5 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v5 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V5_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v5 must contain exactly 40 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V5_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v5 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v5 {artifact_id} current checkpoint contract changed"
            )
    prohibited_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v5",
        "construction-master": "construction-master-public-open-v5",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-unknown-batch": "satellite-unknown-batch-015",
    }
    for prefix, expected_id in prohibited_families.items():
        family = [artifact_id for artifact_id in artifact_ids if artifact_id.startswith(prefix)]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v5 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v5 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V5_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V5_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v5 parity-gap inventory changed")


def _validate_v6_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V6_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-19T18:47:00Z":
        raise CurrentCoverageError("v6 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v6 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v6 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V6_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v6 must contain exactly 40 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V6_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v6 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v6 {artifact_id} current checkpoint contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v10",
        "construction-master": "construction-master-public-open-v10",
        "coverage-audit-public-open": "coverage-audit-public-open-v9",
        "federation-public-open": "federation-public-open-v8",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v13",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v6 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v6 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V6_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V6_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v6 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V6_ARTIFACT_REPLACEMENTS) or not set(
        _V6_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v6 parity gaps contain stale current artifacts")


def _validate_v7_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V7_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-19T21:20:00Z":
        raise CurrentCoverageError("v7 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v7 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v7 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V7_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v7 must contain exactly 40 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V7_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v7 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v7 {artifact_id} current checkpoint contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v11",
        "construction-master": "construction-master-public-open-v11",
        "coverage-audit-public-open": "coverage-audit-public-open-v10",
        "federation-public-open": "federation-public-open-v9",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v20",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v7 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v7 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V7_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V7_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v7 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V7_ARTIFACT_REPLACEMENTS) or not set(
        _V7_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v7 parity gaps contain stale current artifacts")


def _validate_v8_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V8_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-19T22:05:00Z":
        raise CurrentCoverageError("v8 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v8 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v8 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V8_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v8 must contain exactly 40 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V8_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v8 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v8 {artifact_id} current checkpoint contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v12",
        "construction-master": "construction-master-public-open-v12",
        "coverage-audit-public-open": "coverage-audit-public-open-v11",
        "federation-public-open": "federation-public-open-v10",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v30",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v8 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v8 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V8_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V8_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v8 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V8_ARTIFACT_REPLACEMENTS) or not set(
        _V8_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v8 parity gaps contain stale current artifacts")


def _validate_v9_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V9_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-19T22:55:00Z":
        raise CurrentCoverageError("v9 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v9 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v9 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V9_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v9 must contain exactly 40 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V9_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v9 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v9 {artifact_id} current checkpoint contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v13",
        "construction-master": "construction-master-public-open-v13",
        "coverage-audit-public-open": "coverage-audit-public-open-v12",
        "federation-public-open": "federation-public-open-v11",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v32",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v9 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "recovery",
        "satellite-recover",
        "satellite_recover",
        "spain-boe",
        "unknown-031",
        "unknown-032",
        "unknown-033",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v9 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V9_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V9_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v9 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V9_ARTIFACT_REPLACEMENTS) or not set(
        _V9_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v9 parity gaps contain stale current artifacts")


def _validate_v10_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V10_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-20T01:49:35Z":
        raise CurrentCoverageError("v10 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v10 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v10 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V10_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v10 must contain exactly 41 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V10_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v10 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v10 {artifact_id} current checkpoint contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v14",
        "construction-master": "construction-master-public-open-v14",
        "coverage-audit-public-open": "coverage-audit-public-open-v13",
        "federation-public-open": "federation-public-open-v12",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-recovery": _V10_RECOVERY_ARTIFACT_ID,
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v33",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v10 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
        "unknown-031",
        "unknown-032",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v10 includes an explicitly excluded source lane")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V10_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V10_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v10 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V10_ARTIFACT_REPLACEMENTS) or not set(
        _V10_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v10 parity gaps contain stale current artifacts")
    recovery_gap_ids = {
        gap.get("gap_id")
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        and _V10_RECOVERY_ARTIFACT_ID in gap.get("affected_artifact_ids", [])
    }
    if recovery_gap_ids != {
        "global-construction-coverage-partial",
        "satellite-review-backlog",
    }:
        raise CurrentCoverageError("v10 recovery parity-gap scope changed")


def _validate_v12_definition_contract(document: Mapping[str, Any]) -> None:
    if document.get("ledger_id") != V12_LEDGER_ID:
        return
    if document.get("generated_at") != "2026-07-20T05:45:00Z":
        raise CurrentCoverageError("v12 generation timestamp changed")
    if (
        document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V2
        or document.get("scope") != SCOPE_POLICY_V2
    ):
        raise CurrentCoverageError("v12 schema or scope contract changed")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CurrentCoverageError("v12 entries are absent")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V12_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v12 must contain exactly 41 current artifacts with no stale overlap"
        )
    entries_by_id = {
        str(entry["artifact_id"]): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    for artifact_id, expected_checkpoints in _V12_EXACT_CURRENT_CHECKPOINTS.items():
        checkpoints = entries_by_id[artifact_id].get("checkpoints")
        if not isinstance(checkpoints, list):
            raise CurrentCoverageError(
                f"v12 {artifact_id} checkpoints are absent"
            )
        actual = {
            str(checkpoint.get("checkpoint_id")): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in checkpoints
            if isinstance(checkpoint, Mapping)
        }
        if actual != expected_checkpoints:
            raise CurrentCoverageError(
                f"v12 {artifact_id} current checkpoint contract changed"
            )
    for artifact_id, expected_metrics in _V12_EXACT_METRICS.items():
        metrics = entries_by_id[artifact_id].get("metrics")
        if not isinstance(metrics, list):
            raise CurrentCoverageError(f"v12 {artifact_id} metrics are absent")
        actual_metrics = {
            metric.get("label"): metric.get("value")
            for metric in metrics
            if isinstance(metric, Mapping)
        }
        if len(actual_metrics) != len(metrics) or actual_metrics != expected_metrics:
            raise CurrentCoverageError(
                f"v12 {artifact_id} accepted metric contract changed"
            )
    current_families = {
        "candidate-fusion": "candidate-fusion-osm-planet-priority-v13",
        "construction-map": "construction-map-public-open-v14",
        "construction-master": "construction-master-public-open-v14",
        "coverage-audit-public-open": "coverage-audit-public-open-v17",
        "federation-public-open": "federation-public-open-v18",
        "satellite-calibration": "satellite-calibration-analyst-reviews-v4",
        "satellite-recovery": _V12_RECOVERY_ARTIFACT_ID,
        "satellite-unknown-batch": "satellite-unknown-batch-030",
        "seed-epoch-official": "seed-epoch-official-v42",
    }
    for prefix, expected_id in current_families.items():
        family = [
            artifact_id
            for artifact_id in artifact_ids
            if str(artifact_id).startswith(prefix)
        ]
        if family != [expected_id]:
            raise CurrentCoverageError(
                f"v12 {prefix} must have exactly one current version"
            )
    prohibited_lane_fragments = {
        "brazil-pncp",
        "chile-sea",
        "epbc",
        "germany-uvp",
        "iaac",
        "italy-mase",
        "spain-boe",
        "unknown-031",
        "unknown-032",
    }
    identity_and_paths = [
        *artifact_ids,
        *(
            checkpoint.get("path")
            for entry in entries
            if isinstance(entry, Mapping)
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ),
    ]
    if any(
        fragment in str(value).lower()
        for value in identity_and_paths
        for fragment in prohibited_lane_fragments
    ):
        raise CurrentCoverageError("v12 includes an explicitly excluded source lane")
    recovery = entries_by_id[_V12_RECOVERY_ARTIFACT_ID]
    if (
        recovery.get("artifact_kind") != "satellite_catalog_batch"
        or recovery.get("current_role") != "public_supporting_review_lane"
        or recovery.get("evidence_scope") != "review_only"
        or recovery.get("publication_mode") != "public_review_or_discovery"
        or recovery.get("record_units") != ["catalog_job"]
    ):
        raise CurrentCoverageError("v12 recovery review-only guardrails changed")
    parity_gaps = document.get("parity_gaps")
    if (
        not isinstance(parity_gaps, list)
        or {gap.get("gap_id") for gap in parity_gaps if isinstance(gap, Mapping)}
        != _V12_PARITY_GAP_IDS
        or len(parity_gaps) != len(_V12_PARITY_GAP_IDS)
    ):
        raise CurrentCoverageError("v12 parity-gap inventory changed")
    affected_ids = {
        artifact_id
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        for artifact_id in gap.get("affected_artifact_ids", [])
        if isinstance(artifact_id, str)
    }
    if affected_ids & set(_V12_ARTIFACT_REPLACEMENTS) or not set(
        _V12_ARTIFACT_REPLACEMENTS.values()
    ).issubset(affected_ids):
        raise CurrentCoverageError("v12 parity gaps contain stale current artifacts")
    recovery_gap_ids = {
        gap.get("gap_id")
        for gap in parity_gaps
        if isinstance(gap, Mapping)
        and _V12_RECOVERY_ARTIFACT_ID in gap.get("affected_artifact_ids", [])
    }
    if recovery_gap_ids != {
        "global-construction-coverage-partial",
        "satellite-review-backlog",
    }:
        raise CurrentCoverageError("v12 recovery parity-gap scope changed")
    if _sha256(_canonical_json(document)) != _V12_DEFINITION_SHA256:
        raise CurrentCoverageError("v12 definition content changed")


def _is_exact_v4_publication_marker(value: Any) -> bool:
    return type(value) is int and value == 4


def _validate_v12_publication_contract(package_root: Path) -> None:
    child_definition_raw: dict[str, bytes] = {}
    for label, (relative_path, expected_sha256) in (
        _V12_EXACT_CHILD_DEFINITIONS.items()
    ):
        raw = _regular_bytes(
            package_root / relative_path,
            f"v12 {label} definition",
        )
        if _sha256(raw) != expected_sha256:
            raise CurrentCoverageError(
                f"v12 {label} definition checkpoint changed"
            )
        child_definition_raw[label] = raw

    seed_manifest = _json_object(
        _regular_bytes(
            package_root / "releases/2026-07-20-open-seed-v42/manifest.json",
            "v12 seed manifest",
        ),
        "v12 seed manifest",
    )
    federation_index = _json_object(
        _regular_bytes(
            package_root
            / "federated_indexes/2026-07-20-public-open-v18/federated-index.json",
            "v12 federation index",
        ),
        "v12 federation index",
    )
    federation_manifest = _json_object(
        _regular_bytes(
            package_root
            / "federated_indexes/2026-07-20-public-open-v18/manifest.json",
            "v12 federation manifest",
        ),
        "v12 federation manifest",
    )
    coverage_manifest = _json_object(
        _regular_bytes(
            package_root
            / "audits/2026-07-20-public-open-coverage-v17/manifest.json",
            "v12 coverage manifest",
        ),
        "v12 coverage manifest",
    )
    coverage_audit_raw = _regular_bytes(
        package_root
        / "audits/2026-07-20-public-open-coverage-v17/coverage-audit.json",
        "v12 coverage audit",
    )
    coverage_audit = _json_object(coverage_audit_raw, "v12 coverage audit")

    release_descriptors = federation_index.get("releases")
    seed_descriptor = (
        next(
            (
                release
                for release in release_descriptors
                if isinstance(release, Mapping)
                and release.get("release_id") == "epoch-official-open-seed-v42"
            ),
            None,
        )
        if isinstance(release_descriptors, list)
        else None
    )
    descriptor_manifest = (
        seed_descriptor.get("manifest")
        if isinstance(seed_descriptor, Mapping)
        else None
    )
    seed_manifest_sha256 = _V12_EXACT_CURRENT_CHECKPOINTS[
        "seed-epoch-official-v42"
    ]["manifest"][1]
    if (
        not _is_exact_v4_publication_marker(
            seed_manifest.get("publication_contract_version")
        )
        or not isinstance(descriptor_manifest, Mapping)
        or not _is_exact_v4_publication_marker(
            descriptor_manifest.get("publication_contract_version")
        )
        or descriptor_manifest.get("sha256") != seed_manifest_sha256
    ):
        raise CurrentCoverageError(
            "v12 publication contract marker propagation changed"
        )

    federation_definition = federation_manifest.get("definition")
    coverage_definition = coverage_manifest.get("definition")
    coverage_inputs = coverage_manifest.get("inputs")
    coverage_artifacts = coverage_manifest.get("artifacts")
    coverage_audit_descriptor = (
        coverage_artifacts.get("coverage-audit.json")
        if isinstance(coverage_artifacts, Mapping)
        else None
    )
    child_hashes = (
        coverage_inputs.get("child_manifest_sha256")
        if isinstance(coverage_inputs, Mapping)
        else None
    )
    if (
        not isinstance(federation_definition, Mapping)
        or federation_definition.get("bytes")
        != len(child_definition_raw["federation"])
        or federation_definition.get("sha256")
        != _V12_EXACT_CHILD_DEFINITIONS["federation"][1]
        or not isinstance(coverage_definition, Mapping)
        or coverage_definition.get("bytes") != len(child_definition_raw["coverage"])
        or coverage_definition.get("sha256")
        != _V12_EXACT_CHILD_DEFINITIONS["coverage"][1]
        or not isinstance(child_hashes, Mapping)
        or child_hashes.get("epoch-official-open-seed-v42")
        != seed_manifest_sha256
        or coverage_inputs.get("federated_manifest_sha256")
        != _V12_EXACT_CURRENT_CHECKPOINTS["federation-public-open-v18"][
            "manifest"
        ][1]
        or not isinstance(coverage_audit_descriptor, Mapping)
        or coverage_audit_descriptor.get("bytes") != len(coverage_audit_raw)
        or coverage_audit_descriptor.get("sha256")
        != _V12_COVERAGE_AUDIT_SHA256
        or _sha256(coverage_audit_raw) != _V12_COVERAGE_AUDIT_SHA256
        or federation_manifest.get("generated_at") != "2026-07-20T05:00:00Z"
        or coverage_manifest.get("generated_at") != "2026-07-20T05:30:00Z"
    ):
        raise CurrentCoverageError("v12 accepted lineage contract changed")

    audit_inputs = coverage_audit.get("inputs")
    audit_children = (
        audit_inputs.get("children")
        if isinstance(audit_inputs, Mapping)
        else None
    )
    audit_federation = (
        audit_inputs.get("federated_index")
        if isinstance(audit_inputs, Mapping)
        else None
    )
    audit_seed_descriptor = (
        next(
            (
                child
                for child in audit_children
                if isinstance(child, Mapping)
                and child.get("release_id") == "epoch-official-open-seed-v42"
            ),
            None,
        )
        if isinstance(audit_children, list)
        else None
    )
    audit_seed_manifest = (
        audit_seed_descriptor.get("manifest")
        if isinstance(audit_seed_descriptor, Mapping)
        else None
    )
    audit_federation_index = (
        audit_federation.get("index")
        if isinstance(audit_federation, Mapping)
        else None
    )
    audit_federation_manifest = (
        audit_federation.get("manifest")
        if isinstance(audit_federation, Mapping)
        else None
    )
    if (
        not isinstance(audit_seed_manifest, Mapping)
        or not _is_exact_v4_publication_marker(
            audit_seed_manifest.get("publication_contract_version")
        )
        or audit_seed_manifest.get("sha256") != seed_manifest_sha256
        or not isinstance(audit_federation_index, Mapping)
        or audit_federation_index.get("sha256")
        != _V12_EXACT_CURRENT_CHECKPOINTS["federation-public-open-v18"][
            "index"
        ][1]
        or not isinstance(audit_federation_manifest, Mapping)
        or audit_federation_manifest.get("sha256")
        != _V12_EXACT_CURRENT_CHECKPOINTS["federation-public-open-v18"][
            "manifest"
        ][1]
    ):
        raise CurrentCoverageError(
            "v12 coverage publication contract marker propagation changed"
        )


def _v13_pinned_json(
    package_root: Path,
    spec: Mapping[str, Any],
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    if set(spec) != {"bytes", "path", "sha256"}:
        raise CurrentCoverageError(f"{label} checkpoint schema changed")
    relative = spec.get("path")
    if not isinstance(relative, str) or not relative:
        raise CurrentCoverageError(f"{label} checkpoint path is invalid")
    path = (package_root / relative).resolve()
    try:
        path.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageError(f"{label} checkpoint escapes package") from error
    raw = _regular_bytes(path, label)
    if (
        type(spec.get("bytes")) is not int
        or spec["bytes"] < 0
        or not isinstance(spec.get("sha256"), str)
        or not _SHA256_RE.fullmatch(spec["sha256"])
        or len(raw) != spec["bytes"]
        or _sha256(raw) != spec["sha256"]
    ):
        raise CurrentCoverageError(f"{label} checkpoint changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise CurrentCoverageError(f"{label} must use canonical JSON encoding")
    return raw, document


def _v13_base_documents(
    package_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    definition_raw, definition = _v13_pinned_json(
        package_root, _V13_BASE_LINEAGE["definition"], "v13 base definition"
    )
    ledger_raw, ledger = _v13_pinned_json(
        package_root, _V13_BASE_LINEAGE["ledger"], "v13 base ledger"
    )
    manifest_raw, manifest = _v13_pinned_json(
        package_root, _V13_BASE_LINEAGE["manifest"], "v13 base manifest"
    )
    if (
        definition.get("ledger_id") != V12_LEDGER_ID
        or ledger.get("ledger_id") != V12_LEDGER_ID
        or manifest.get("ledger_id") != V12_LEDGER_ID
        or manifest.get("definition") != _V13_BASE_LINEAGE["definition"]
        or manifest.get("artifacts", {}).get(LEDGER_FILENAME)
        != {
            "bytes": len(ledger_raw),
            "sha256": _sha256(ledger_raw),
        }
        or len(definition_raw) != _V13_BASE_LINEAGE["definition"]["bytes"]
        or len(manifest_raw) != _V13_BASE_LINEAGE["manifest"]["bytes"]
    ):
        raise CurrentCoverageError("v13 accepted v12 base lineage changed")
    base_directory = package_root / "current_coverage_ledgers/2026-07-20-v12"
    if (
        base_directory.is_symlink()
        or not base_directory.is_dir()
        or base_directory.stat().st_mode & 0o777 != 0o555
    ):
        raise CurrentCoverageError("v13 accepted v12 base bundle is not frozen")
    base_entries = list(base_directory.iterdir())
    if (
        {entry.name for entry in base_entries} != BUNDLE_FILES
        or any(
            entry.is_symlink()
            or not entry.is_file()
            or entry.stat().st_mode & 0o777 != 0o444
            for entry in base_entries
        )
    ):
        raise CurrentCoverageError("v13 accepted v12 base bundle is not frozen")
    return definition, ledger, manifest


def _validate_v13_publication_contract(package_root: Path) -> None:
    documents: dict[str, dict[str, Any]] = {}
    for label, (relative, expected_bytes, expected_sha256) in (
        _V13_EXACT_FILES.items()
    ):
        raw = _regular_bytes(package_root / relative, f"v13 {label}")
        if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
            raise CurrentCoverageError(f"v13 {label} changed")
        document = _json_object(raw, f"v13 {label}")
        if raw != _canonical_json(document):
            raise CurrentCoverageError(f"v13 {label} is not canonical")
        documents[label] = document

    master_definition = documents["construction-master definition"]
    master_coverage = documents["construction-master coverage"]
    master_manifest = documents["construction-master manifest"]
    map_definition = documents["construction-map definition"]
    map_coverage = documents["construction-map coverage"]
    map_manifest = documents["construction-map manifest"]
    replacement_marker = (
        master_definition.get("inputs", {})
        .get("replacement_release", {})
        .get("publication_contract_version")
    )
    coverage_marker = master_coverage.get("replacement", {}).get(
        "publication_contract_version"
    )
    if not all(
        _is_exact_v4_publication_marker(value)
        for value in (replacement_marker, coverage_marker)
    ):
        raise CurrentCoverageError("v13 v16 publication marker changed")

    if (
        master_definition.get("master_id") != "2026-07-20-public-open-v16"
        or master_definition.get("generated_at") != "2026-07-20T06:00:00Z"
        or master_definition.get("schema_version") != 2
        or master_definition.get("expected")
        != master_coverage.get("replacement_invariants")
        or master_definition.get("expected", {}).get("total_rows") != 109_174
        or master_definition.get("inputs", {})
        .get("replacement_release", {})
        .get("artifact_id")
        != "epoch-official-open-seed-v42"
        or master_manifest.get("master_id") != "2026-07-20-public-open-v16"
        or master_manifest.get("generated_at") != "2026-07-20T06:00:00Z"
        or master_manifest.get("definition")
        != {
            "bytes": 5_655,
            "path": "sources/construction-master-2026-07-20-public-open-v16.json",
            "sha256": _V13_EXACT_FILES["construction-master definition"][2],
        }
        or master_manifest.get("outputs", {}).get("coverage.json")
        != {
            "bytes": 8_492,
            "sha256": _V13_EXACT_FILES["construction-master coverage"][2],
        }
        or master_manifest.get("row_counts", {}).get("total") != 109_174
        or master_coverage.get("replacement_invariants", {}).get("base_rows")
        != 109_111
        or master_coverage.get("replacement_invariants", {}).get(
            "added_replacement_rows"
        )
        != 63
        or master_coverage.get("replacement_invariants", {}).get(
            "unchanged_replacement_rows"
        )
        != 199
        or master_coverage.get("row_counts", {}).get("by_tier")
        != {"A": 382, "B": 6_298, "C": 102_494}
        or master_coverage.get("role_counts")
        != {
            "rows_with_any_role": 89,
            "rows_with_contract_marker": 262,
            "rows_with_source_role_tags": 50,
            "with_core_role": {
                "customers": 1,
                "operator": 30,
                "owner": 46,
                "tenants": 4,
                "users": 36,
            },
        }
        or master_coverage.get("scope", {}).get("global_completeness_claimed")
        is not False
        or master_coverage.get("row_counts", {}).get("unique_physical_site_count")
        is not None
    ):
        raise CurrentCoverageError("v13 v16 master lineage or count contract changed")

    if (
        map_definition.get("map_id")
        != "2026-07-20-public-open-v16-construction-map-v2"
        or map_definition.get("generated_at") != "2026-07-20T06:15:00Z"
        or map_definition.get("schema_version") != 2
        or map_definition.get("master", {}).get("definition", {}).get("sha256")
        != _V13_EXACT_FILES["construction-master definition"][2]
        or map_definition.get("master", {}).get("manifest", {}).get("sha256")
        != _V13_EXACT_FILES["construction-master manifest"][2]
        or map_definition.get("expected_projection") != map_coverage.get("projection")
        or map_definition.get("expected_projection", {}).get("master_rows")
        != 109_174
        or map_definition.get("expected_projection", {}).get("mapped_rows")
        != 108_973
        or map_definition.get("expected_projection", {}).get("unmapped_rows") != 201
        or map_manifest.get("map_id")
        != "2026-07-20-public-open-v16-construction-map-v2"
        or map_manifest.get("generated_at") != "2026-07-20T06:15:00Z"
        or map_manifest.get("master", {}).get("manifest", {}).get("sha256")
        != _V13_EXACT_FILES["construction-master manifest"][2]
        or map_manifest.get("outputs", {}).get("coverage.json")
        != {
            "bytes": 7_342,
            "sha256": _V13_EXACT_FILES["construction-map coverage"][2],
        }
        or map_coverage.get("counts")
        != {
            "mapped_observation_rows": 108_973,
            "mapped_replacement_rows": 80,
            "mapped_rows_with_any_role": 66,
            "master_observation_rows": 109_174,
            "unique_physical_site_count": None,
            "unmapped_observation_rows": 201,
        }
        or map_coverage.get("projection", {}).get("added_replacement_rows_unmapped")
        != 63
        or map_coverage.get("scope", {}).get("global_completeness_claimed") is not False
    ):
        raise CurrentCoverageError("v13 v16 map lineage or count contract changed")

    for relative in (
        "construction_master/2026-07-20-public-open-v16",
        "construction_maps/2026-07-20-public-open-v16",
    ):
        directory = package_root / relative
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or directory.stat().st_mode & 0o777 != 0o555
        ):
            raise CurrentCoverageError("v13 accepted v16 bundle is not frozen")
        entries = list(directory.iterdir())
        if any(
            entry.is_symlink()
            or not entry.is_file()
            or entry.stat().st_mode & 0o777 != 0o444
            for entry in entries
        ):
            raise CurrentCoverageError("v13 accepted v16 bundle is not frozen")


def _v13_replaced_parity_gaps(parity_gaps: Any) -> Any:
    if not isinstance(parity_gaps, list):
        return None
    return [
        {
            **gap,
            "affected_artifact_ids": [
                _V13_ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in gap.get("affected_artifact_ids", [])
            ],
        }
        if isinstance(gap, Mapping)
        else gap
        for gap in parity_gaps
    ]


def _validate_v13_definition_contract(
    document: Mapping[str, Any],
    raw: bytes,
    package_root: Path,
) -> None:
    if document.get("ledger_id") != V13_LEDGER_ID:
        return
    if (
        document.get("generated_at") != _V13_GENERATED_AT
        or document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V3
        or document.get("scope") != SCOPE_POLICY_V2
        or document.get("base_ledger") != _V13_BASE_LINEAGE
    ):
        raise CurrentCoverageError("v13 identity, base, schema, or scope changed")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) != 41:
        raise CurrentCoverageError("v13 must contain exactly 41 entries")
    artifact_ids = tuple(
        entry.get("artifact_id") if isinstance(entry, Mapping) else None
        for entry in entries
    )
    if artifact_ids != _V13_ARTIFACT_IDS:
        raise CurrentCoverageError(
            "v13 must contain exactly 41 current artifacts with no stale overlap"
        )
    base_definition, base_ledger, _base_manifest = _v13_base_documents(package_root)
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    current_entries = {entry["artifact_id"]: entry for entry in entries}
    inherited_ids = set(base_entries) - _V13_OLD_CONSTRUCTION_IDS
    if set(current_entries) - _V13_NEW_CONSTRUCTION_IDS != inherited_ids:
        raise CurrentCoverageError("v13 non-construction entry inventory changed")
    for artifact_id in sorted(inherited_ids):
        if current_entries[artifact_id] != base_entries[artifact_id]:
            raise CurrentCoverageError(f"v13 inherited entry changed: {artifact_id}")
    for artifact_id in sorted(_V13_NEW_CONSTRUCTION_IDS):
        entry = current_entries[artifact_id]
        checkpoints = {
            checkpoint.get("checkpoint_id"): (
                checkpoint.get("path"),
                checkpoint.get("sha256"),
            )
            for checkpoint in entry.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        }
        metrics = {
            metric.get("label"): metric.get("value")
            for metric in entry.get("metrics", [])
            if isinstance(metric, Mapping)
        }
        if checkpoints != _V13_EXACT_CURRENT_CHECKPOINTS[artifact_id]:
            raise CurrentCoverageError(f"v13 {artifact_id} checkpoints changed")
        if metrics != _V13_EXACT_METRICS[artifact_id] or len(metrics) != len(
            entry.get("metrics", [])
        ):
            raise CurrentCoverageError(f"v13 {artifact_id} metrics changed")
    if document.get("parity_gaps") != _v13_replaced_parity_gaps(
        base_definition["parity_gaps"]
    ):
        raise CurrentCoverageError("v13 parity gaps differ beyond current IDs")
    if base_ledger.get("artifact_inventory_counts") is None:
        raise CurrentCoverageError("v13 accepted v12 base counts are absent")
    if _sha256(raw) != _V13_DEFINITION_SHA256:
        raise CurrentCoverageError("v13 definition content changed")
    rejected_markers = (
        b"construction-map-public-open-v14",
        b"construction-master-public-open-v14",
        b"construction_maps/2026-07-19-public-open-v14",
        b"construction_master/2026-07-19-public-open-v14",
        b"construction-map-public-open-v18",
        b"construction-master-public-open-v18",
        b"construction_maps/2026-07-20-public-open-v18",
        b"construction_master/2026-07-20-public-open-v18",
        b"construction-map-public-open-v15",
        b"construction-master-public-open-v15",
        b"construction_maps/2026-07-20-public-open-v15",
        b"construction_master/2026-07-20-public-open-v15",
        b"2026-07-20-public-open-v18-construction-map-v5",
        b"open-seed-2026-07-20-v41",
        b"2026-07-20-open-seed-v41",
    )
    if any(marker in raw for marker in rejected_markers):
        raise CurrentCoverageError("v13 contains rejected construction lineage")
    _validate_v13_publication_contract(package_root)


def _definition(path: Path) -> tuple[dict[str, Any], bytes, Path]:
    raw = _regular_bytes(path, "definition")
    document = _json_object(raw, "definition")
    if raw != _canonical_json(document):
        raise CurrentCoverageError("definition must use canonical JSON encoding")
    schema_version = document.get("schema_version")
    if schema_version == DEFINITION_SCHEMA_VERSION:
        expected_keys = {
            "entries",
            "generated_at",
            "ledger_id",
            "schema_version",
            "scope",
        }
        expected_scope = SCOPE_POLICY
    elif schema_version == DEFINITION_SCHEMA_VERSION_V2:
        expected_keys = {
            "entries",
            "generated_at",
            "ledger_id",
            "parity_gaps",
            "schema_version",
            "scope",
        }
        expected_scope = SCOPE_POLICY_V2
    elif schema_version == DEFINITION_SCHEMA_VERSION_V3:
        expected_keys = {
            "base_ledger",
            "entries",
            "generated_at",
            "ledger_id",
            "parity_gaps",
            "schema_version",
            "scope",
        }
        expected_scope = SCOPE_POLICY_V2
    else:
        raise CurrentCoverageError("unsupported definition schema version")
    if set(document) != expected_keys:
        raise CurrentCoverageError(
            f"definition keys differ from the v{schema_version} contract"
        )
    ledger_id = document.get("ledger_id")
    if not isinstance(ledger_id, str) or not _IDENTIFIER_RE.fullmatch(ledger_id):
        raise CurrentCoverageError("ledger_id is invalid")
    if (
        _FROZEN_LEDGER_ID_RE.fullmatch(ledger_id)
        and ledger_id not in _SUPPORTED_FROZEN_LEDGER_IDS
    ):
        raise CurrentCoverageError("unsupported frozen ledger_id")
    _timestamp(document.get("generated_at"), "generated_at")
    if document.get("scope") != expected_scope:
        raise CurrentCoverageError("definition scope weakens the fail-closed policy")
    package_root = path.parent.parent.resolve()
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise CurrentCoverageError("entries must be a non-empty list")
    if ledger_id == V13_LEDGER_ID:
        if path.resolve() != (
            package_root / "sources/current-coverage-2026-07-20-v13.json"
        ):
            raise CurrentCoverageError("v13 definition publication path changed")
        _validate_v13_definition_contract(document, raw, package_root)
    _validate_v12_definition_contract(document)
    if ledger_id == V12_LEDGER_ID:
        _validate_v12_publication_contract(package_root)
    _validate_v10_definition_contract(document)
    _validate_v9_definition_contract(document)
    _validate_v8_definition_contract(document)
    _validate_v7_definition_contract(document)
    _validate_v6_definition_contract(document)
    _validate_v5_definition_contract(document)
    return document, raw, package_root


def _validate_sidecar(path: Path, digest: str) -> None:
    if path.name != MANIFEST_FILENAME:
        return
    sidecar = path.with_name(MANIFEST_HASH_FILENAME)
    if not sidecar.exists():
        return
    raw = _regular_bytes(sidecar, "manifest sidecar")
    expected = f"{digest}  {MANIFEST_FILENAME}\n".encode("ascii")
    if raw != expected:
        raise CurrentCoverageError(f"manifest sidecar differs: {sidecar}")


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CurrentCoverageError(f"{label} must be a positive integer")
    return value


def _checkpoint_documents(
    package_root: Path,
    checkpoints: Any,
    artifact_id: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(checkpoints, list) or not checkpoints:
        raise CurrentCoverageError(f"{artifact_id} checkpoints must be non-empty")
    results: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(checkpoints):
        label = f"{artifact_id} checkpoints[{index}]"
        if not isinstance(spec, Mapping):
            raise CurrentCoverageError(f"{label} must be an object")
        allowed = {"binding", "bytes", "checkpoint_id", "path", "sha256"}
        required = {"bytes", "checkpoint_id", "path", "sha256"}
        if not required.issubset(spec) or not set(spec).issubset(allowed):
            raise CurrentCoverageError(f"{label} keys are invalid")
        checkpoint_id = spec.get("checkpoint_id")
        if (
            not isinstance(checkpoint_id, str)
            or not _IDENTIFIER_RE.fullmatch(checkpoint_id)
            or checkpoint_id in by_id
        ):
            raise CurrentCoverageError(f"{label} checkpoint_id is invalid or repeated")
        if results and checkpoint_id <= results[-1]["checkpoint_id"]:
            raise CurrentCoverageError(
                f"{artifact_id} checkpoints must be sorted by checkpoint_id"
            )
        relative = spec.get("path")
        path = _package_relative_path(package_root, relative, f"{label} path")
        raw = _regular_bytes(path, label)
        expected_bytes = _positive_integer(spec.get("bytes"), f"{label} bytes")
        expected_sha = spec.get("sha256")
        if not isinstance(expected_sha, str) or not _SHA256_RE.fullmatch(expected_sha):
            raise CurrentCoverageError(f"{label} sha256 is invalid")
        actual_sha = _sha256(raw)
        if len(raw) != expected_bytes or actual_sha != expected_sha:
            raise CurrentCoverageError(f"{label} checkpoint changed")
        _validate_sidecar(path, actual_sha)
        document = _json_object(raw, label)
        result = {
            "bytes": len(raw),
            "checkpoint_id": checkpoint_id,
            "path": relative,
            "sha256": actual_sha,
        }
        if "binding" in spec:
            binding = spec["binding"]
            if not isinstance(binding, Mapping) or set(binding) != {
                "checkpoint_id",
                "json_pointer",
            }:
                raise CurrentCoverageError(f"{label} binding is invalid")
            result["binding"] = dict(binding)
        results.append(result)
        by_id[checkpoint_id] = {"document": document, "result": result}

    for spec, result in zip(checkpoints, results, strict=True):
        binding = spec.get("binding")
        if binding is None:
            continue
        parent_id = binding.get("checkpoint_id")
        if parent_id == result["checkpoint_id"] or parent_id not in by_id:
            raise CurrentCoverageError(
                f"{artifact_id} checkpoint binding parent is invalid"
            )
        bound = _json_pointer(
            by_id[parent_id]["document"],
            binding.get("json_pointer"),
            f"{artifact_id} checkpoint binding",
        )
        if not isinstance(bound, Mapping):
            raise CurrentCoverageError(f"{artifact_id} checkpoint binding is not an object")
        if bound.get("bytes") != result["bytes"] or bound.get("sha256") != result["sha256"]:
            raise CurrentCoverageError(
                f"{artifact_id} checkpoint does not match its manifest binding"
            )
    return results, by_id


def _entry(
    package_root: Path,
    spec: Any,
    previous_id: str | None,
    definition_schema_version: int,
) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise CurrentCoverageError("entry must be an object")
    expected_keys = {
        "access_tier",
        "artifact_id",
        "artifact_kind",
        "checkpoints",
        "current_role",
        "evidence_scope",
        "limitations",
        "metrics",
        "redistribution_status",
    }
    if definition_schema_version in {
        DEFINITION_SCHEMA_VERSION_V2,
        DEFINITION_SCHEMA_VERSION_V3,
    }:
        expected_keys |= {"publication_mode", "record_units"}
    if set(spec) != expected_keys:
        raise CurrentCoverageError(
            f"entry keys differ from the v{definition_schema_version} contract"
        )
    artifact_id = spec.get("artifact_id")
    if not isinstance(artifact_id, str) or not _IDENTIFIER_RE.fullmatch(artifact_id):
        raise CurrentCoverageError("artifact_id is invalid")
    if previous_id is not None and artifact_id <= previous_id:
        raise CurrentCoverageError("entries must be sorted by unique artifact_id")
    artifact_kind = spec.get("artifact_kind")
    access_tier = spec.get("access_tier")
    redistribution_status = spec.get("redistribution_status")
    evidence_scope = spec.get("evidence_scope")
    current_role = spec.get("current_role")
    if artifact_kind not in ARTIFACT_KINDS:
        raise CurrentCoverageError(f"{artifact_id} artifact_kind is invalid")
    if access_tier not in ACCESS_TIERS:
        raise CurrentCoverageError(f"{artifact_id} access_tier is invalid")
    if redistribution_status not in REDISTRIBUTION_STATUSES:
        raise CurrentCoverageError(f"{artifact_id} redistribution_status is invalid")
    if evidence_scope not in EVIDENCE_SCOPES:
        raise CurrentCoverageError(f"{artifact_id} evidence_scope is invalid")
    if current_role not in CURRENT_ROLES:
        raise CurrentCoverageError(f"{artifact_id} current_role is invalid")
    if access_tier == "local_restricted":
        if redistribution_status != "quarantined_pending_rights":
            raise CurrentCoverageError(
                f"{artifact_id} local-restricted data must remain quarantined"
            )
        if current_role != "local_restricted_research":
            raise CurrentCoverageError(
                f"{artifact_id} local-restricted role must remain explicit"
            )
    elif redistribution_status == "quarantined_pending_rights":
        raise CurrentCoverageError(
            f"{artifact_id} quarantined data cannot be public_open"
        )
    if redistribution_status == "metadata_only_no_source_rows" and evidence_scope != "metadata_only":
        raise CurrentCoverageError(
            f"{artifact_id} metadata-only status requires metadata-only evidence scope"
        )

    publication_mode: str | None = None
    record_units: list[str] | None = None
    if definition_schema_version in {
        DEFINITION_SCHEMA_VERSION_V2,
        DEFINITION_SCHEMA_VERSION_V3,
    }:
        publication_mode = spec.get("publication_mode")
        if publication_mode not in PUBLICATION_MODES:
            raise CurrentCoverageError(
                f"{artifact_id} publication_mode is invalid"
            )
        raw_record_units = spec.get("record_units")
        if (
            not isinstance(raw_record_units, list)
            or not raw_record_units
            or raw_record_units != sorted(set(raw_record_units))
            or any(unit not in RECORD_UNITS for unit in raw_record_units)
        ):
            raise CurrentCoverageError(
                f"{artifact_id} record_units must be sorted unique known units"
            )
        record_units = list(raw_record_units)
        if access_tier == "local_restricted":
            expected_publication_mode = "local_quarantined"
        elif redistribution_status == "metadata_only_no_source_rows":
            expected_publication_mode = "public_metadata_or_aggregate_only"
        elif publication_mode == "public_index_or_audit":
            expected_publication_mode = "public_index_or_audit"
            if (
                redistribution_status != "eligible_with_upstream_terms"
                or artifact_kind
                not in {
                    "coverage_audit",
                    "cross_release_resolution",
                    "federated_release_index",
                }
                or evidence_scope == "metadata_only"
            ):
                raise CurrentCoverageError(
                    f"{artifact_id} public index/audit contract is invalid"
                )
        elif publication_mode == "public_row_release":
            expected_publication_mode = "public_row_release"
            if (
                redistribution_status != "eligible_with_upstream_terms"
                or current_role != "authoritative_public_core"
                or evidence_scope not in {
                    "mixed_source_scoped_and_review",
                    "source_scoped",
                }
            ):
                raise CurrentCoverageError(
                    f"{artifact_id} public row release contract is invalid"
                )
        else:
            expected_publication_mode = "public_review_or_discovery"
            if (
                access_tier != "public_open"
                or redistribution_status != "eligible_with_upstream_terms"
                or evidence_scope == "metadata_only"
            ):
                raise CurrentCoverageError(
                    f"{artifact_id} public review/discovery contract is invalid"
                )
        if publication_mode != expected_publication_mode:
            raise CurrentCoverageError(
                f"{artifact_id} publication mode conflicts with rights state"
            )

    limitations = spec.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(value, str) or not value for value in limitations)
        or limitations != sorted(set(limitations))
    ):
        raise CurrentCoverageError(
            f"{artifact_id} limitations must be sorted unique non-empty text"
        )
    checkpoints, checkpoint_by_id = _checkpoint_documents(
        package_root, spec.get("checkpoints"), artifact_id
    )

    metrics = spec.get("metrics")
    if not isinstance(metrics, list):
        raise CurrentCoverageError(f"{artifact_id} metrics must be a list")
    reported_metrics: dict[str, Any] = {}
    for index, metric in enumerate(metrics):
        label = f"{artifact_id} metrics[{index}]"
        required_metric_keys = {
            "checkpoint_id",
            "json_pointer",
            "label",
            "value",
        }
        if (
            not isinstance(metric, Mapping)
            or not required_metric_keys.issubset(metric)
            or not set(metric).issubset(required_metric_keys | {"operation"})
        ):
            raise CurrentCoverageError(f"{label} is invalid")
        metric_label = metric.get("label")
        if (
            not isinstance(metric_label, str)
            or not _IDENTIFIER_RE.fullmatch(metric_label)
            or metric_label in reported_metrics
        ):
            raise CurrentCoverageError(f"{label} label is invalid or repeated")
        if reported_metrics and metric_label <= next(reversed(reported_metrics)):
            raise CurrentCoverageError(f"{artifact_id} metrics must be sorted by label")
        checkpoint_id = metric.get("checkpoint_id")
        if checkpoint_id not in checkpoint_by_id:
            raise CurrentCoverageError(f"{label} names an unknown checkpoint")
        pointed_value = _json_pointer(
            checkpoint_by_id[checkpoint_id]["document"],
            metric.get("json_pointer"),
            f"{label} pointer",
        )
        operation = metric.get("operation", "identity")
        if operation == "identity":
            actual = pointed_value
        elif operation == "length":
            if not isinstance(pointed_value, (list, Mapping)):
                raise CurrentCoverageError(
                    f"{label} length operation requires an array or object"
                )
            actual = len(pointed_value)
        else:
            raise CurrentCoverageError(f"{label} operation is invalid")
        if actual != metric.get("value") or type(actual) is not type(metric.get("value")):
            raise CurrentCoverageError(f"{label} value differs from checkpoint")
        reported_metrics[metric_label] = actual

    result = {
        "access_tier": access_tier,
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "checkpoints": checkpoints,
        "current_role": current_role,
        "evidence_scope": evidence_scope,
        "limitations": limitations,
        "redistribution_status": redistribution_status,
        "reported_metrics": reported_metrics,
        "review_only": evidence_scope == "review_only",
    }
    if definition_schema_version in {
        DEFINITION_SCHEMA_VERSION_V2,
        DEFINITION_SCHEMA_VERSION_V3,
    }:
        result["publication_mode"] = publication_mode
        result["record_units"] = record_units
    return result


def _parity_gaps(value: Any, artifact_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise CurrentCoverageError("parity_gaps must be a non-empty list")
    results: list[dict[str, Any]] = []
    previous_id: str | None = None
    for index, raw in enumerate(value):
        label = f"parity_gaps[{index}]"
        if not isinstance(raw, Mapping) or set(raw) != {
            "affected_artifact_ids",
            "gap_id",
            "status",
            "summary",
        }:
            raise CurrentCoverageError(f"{label} contract is invalid")
        gap_id = raw.get("gap_id")
        status = raw.get("status")
        summary = raw.get("summary")
        affected = raw.get("affected_artifact_ids")
        if (
            not isinstance(gap_id, str)
            or not _IDENTIFIER_RE.fullmatch(gap_id)
            or (previous_id is not None and gap_id <= previous_id)
            or status not in PARITY_GAP_STATUSES
            or not isinstance(summary, str)
            or not summary
            or not isinstance(affected, list)
            or not affected
            or affected != sorted(set(affected))
            or any(artifact_id not in artifact_ids for artifact_id in affected)
        ):
            raise CurrentCoverageError(f"{label} value is invalid")
        results.append(
            {
                "affected_artifact_ids": list(affected),
                "gap_id": gap_id,
                "status": status,
                "summary": summary,
            }
        )
        previous_id = gap_id
    return results


def build_current_coverage_ledger(
    definition_path: str | Path,
) -> CurrentCoverageBundle:
    """Build an in-memory ledger after validating every pinned checkpoint."""

    path = Path(definition_path)
    definition, definition_raw, package_root = _definition(path)
    definition_schema_version = definition["schema_version"]
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    for spec in definition["entries"]:
        artifact = _entry(
            package_root, spec, previous_id, definition_schema_version
        )
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]

    access_counts = {
        tier: sum(artifact["access_tier"] == tier for artifact in artifacts)
        for tier in sorted(ACCESS_TIERS)
    }
    evidence_counts = {
        scope: sum(artifact["evidence_scope"] == scope for artifact in artifacts)
        for scope in sorted(EVIDENCE_SCOPES)
    }
    inventory_counts = {
        "artifacts": len(artifacts),
        "by_access_tier": access_counts,
        "by_evidence_scope": evidence_counts,
        "public_open_review_only_artifacts": sum(
            artifact["access_tier"] == "public_open" and artifact["review_only"]
            for artifact in artifacts
        ),
    }
    if definition_schema_version in {
        DEFINITION_SCHEMA_VERSION_V2,
        DEFINITION_SCHEMA_VERSION_V3,
    }:
        inventory_counts["by_publication_mode"] = {
            mode: sum(artifact["publication_mode"] == mode for artifact in artifacts)
            for mode in sorted(PUBLICATION_MODES)
        }
        inventory_counts["by_record_unit"] = {
            unit: sum(unit in artifact["record_units"] for artifact in artifacts)
            for unit in sorted(RECORD_UNITS)
        }
        inventory_counts["by_redistribution_status"] = {
            status: sum(
                artifact["redistribution_status"] == status
                for artifact in artifacts
            )
            for status in sorted(REDISTRIBUTION_STATUSES)
        }
        parity_gaps = _parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
        inventory_counts["parity_gaps_by_status"] = {
            status: sum(gap["status"] == status for gap in parity_gaps)
            for status in sorted(PARITY_GAP_STATUSES)
        }
        if definition.get("ledger_id") == V5_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 40
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 34}
                or inventory_counts["by_publication_mode"]
                != _V5_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 29,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 21
            ):
                raise CurrentCoverageError(
                    "v5 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V7_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 40
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 34}
                or inventory_counts["by_publication_mode"]
                != _V7_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 29,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 21
            ):
                raise CurrentCoverageError(
                    "v7 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V8_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 40
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 34}
                or inventory_counts["by_publication_mode"]
                != _V8_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 29,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 21
            ):
                raise CurrentCoverageError(
                    "v8 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V9_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 40
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 34}
                or inventory_counts["by_publication_mode"]
                != _V9_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 29,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 21
            ):
                raise CurrentCoverageError(
                    "v9 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V10_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 41
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 35}
                or inventory_counts["by_publication_mode"]
                != _V10_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 30,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 22
            ):
                raise CurrentCoverageError(
                    "v10 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V12_LEDGER_ID:
            if (
                inventory_counts["artifacts"] != 41
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 35}
                or inventory_counts["by_publication_mode"]
                != _V12_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 30,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 22
            ):
                raise CurrentCoverageError(
                    "v12 inventory or publication-mode arithmetic changed"
                )
        if definition.get("ledger_id") == V13_LEDGER_ID:
            _base_definition, base_ledger, _base_manifest = _v13_base_documents(
                package_root
            )
            if (
                inventory_counts != base_ledger.get("artifact_inventory_counts")
                or inventory_counts["artifacts"] != 41
                or inventory_counts["by_access_tier"]
                != {"local_restricted": 6, "public_open": 35}
                or inventory_counts["by_publication_mode"]
                != _V13_PUBLICATION_MODE_COUNTS
                or inventory_counts["by_redistribution_status"]
                != {
                    "eligible_with_upstream_terms": 30,
                    "metadata_only_no_source_rows": 5,
                    "quarantined_pending_rights": 6,
                }
                or inventory_counts["public_open_review_only_artifacts"] != 22
            ):
                raise CurrentCoverageError(
                    "v13 inventory differs from the sole accepted v12 baseline"
                )
        if definition_schema_version == DEFINITION_SCHEMA_VERSION_V3:
            ledger_format = LEDGER_FORMAT_V3
            ledger_schema_version = LEDGER_SCHEMA_VERSION_V3
            ledger_scope = SCOPE_POLICY_V2
            bundle_format = BUNDLE_FORMAT_V3
        else:
            ledger_format = LEDGER_FORMAT_V2
            ledger_schema_version = LEDGER_SCHEMA_VERSION_V2
            ledger_scope = SCOPE_POLICY_V2
            bundle_format = BUNDLE_FORMAT_V2
    else:
        parity_gaps = None
        ledger_format = LEDGER_FORMAT
        ledger_schema_version = LEDGER_SCHEMA_VERSION
        ledger_scope = SCOPE_POLICY
        bundle_format = BUNDLE_FORMAT

    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "format": ledger_format,
        "generated_at": definition["generated_at"],
        "ledger_id": definition["ledger_id"],
        "schema_version": ledger_schema_version,
        "scope": ledger_scope,
    }
    if parity_gaps is not None:
        ledger["parity_gaps"] = parity_gaps
    if definition_schema_version == DEFINITION_SCHEMA_VERSION_V3:
        ledger["base_ledger"] = _V13_BASE_LINEAGE
    ledger_bytes = _canonical_json(ledger)
    definition_relative = path.resolve().relative_to(package_root).as_posix()
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "definition": {
            "bytes": len(definition_raw),
            "path": definition_relative,
            "sha256": _sha256(definition_raw),
        },
        "format": bundle_format,
        "generated_at": definition["generated_at"],
        "input_checkpoints": {
            artifact["artifact_id"]: {
                checkpoint["checkpoint_id"]: {
                    "bytes": checkpoint["bytes"],
                    "path": checkpoint["path"],
                    "sha256": checkpoint["sha256"],
                }
                for checkpoint in artifact["checkpoints"]
            }
            for artifact in artifacts
        },
        "ledger_id": definition["ledger_id"],
        "schema_version": ledger_schema_version,
        "scope": ledger_scope,
    }
    if definition_schema_version == DEFINITION_SCHEMA_VERSION_V3:
        manifest["base_ledger"] = _V13_BASE_LINEAGE
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageBundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


def write_current_coverage_ledger(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = False,
) -> dict[str, Any]:
    """Atomically publish a new immutable current-coverage ledger bundle."""

    bundle = build_current_coverage_ledger(definition_path)
    destination = Path(output_path)
    if destination.exists() or destination.is_symlink():
        raise CurrentCoverageError(f"refusing existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    try:
        _write_file(stage / LEDGER_FILENAME, bundle.ledger_bytes)
        _write_file(stage / MANIFEST_FILENAME, bundle.manifest_bytes)
        _write_file(stage / MANIFEST_HASH_FILENAME, bundle.manifest_hash_bytes)
        stage.replace(destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    if freeze:
        for name in BUNDLE_FILES:
            (destination / name).chmod(0o444)
        destination.chmod(0o555)
    return dict(bundle.manifest)


def validate_current_coverage_ledger(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Validate a bundle and reproduce it byte-for-byte without network access."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageError("ledger bundle must be a regular directory")
    entries = list(directory.iterdir())
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise CurrentCoverageError("ledger bundle entries must be regular files")
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise CurrentCoverageError("ledger bundle file set differs")
    actual_ledger = _regular_bytes(directory / LEDGER_FILENAME, "ledger")
    actual_manifest = _regular_bytes(directory / MANIFEST_FILENAME, "manifest")
    actual_sidecar = _regular_bytes(directory / MANIFEST_HASH_FILENAME, "sidecar")
    _json_object(actual_ledger, "ledger")
    actual_manifest_document = _json_object(actual_manifest, "manifest")
    if actual_manifest_document.get("ledger_id") in {
        V5_LEDGER_ID,
        V7_LEDGER_ID,
        V8_LEDGER_ID,
        V9_LEDGER_ID,
        V10_LEDGER_ID,
        V12_LEDGER_ID,
        V13_LEDGER_ID,
    }:
        if directory.stat().st_mode & 0o777 != 0o555 or any(
            entry.stat().st_mode & 0o777 != 0o444 for entry in entries
        ):
            raise CurrentCoverageError("ledger bundle must be frozen 0555/0444")
    if actual_sidecar != f"{_sha256(actual_manifest)}  {MANIFEST_FILENAME}\n".encode(
        "ascii"
    ):
        raise CurrentCoverageError("ledger manifest sidecar differs")
    expected = build_current_coverage_ledger(definition_path)
    if actual_ledger != expected.ledger_bytes:
        raise CurrentCoverageError("ledger differs from offline reconstruction")
    if actual_manifest != expected.manifest_bytes:
        raise CurrentCoverageError("manifest differs from offline reconstruction")
    if actual_sidecar != expected.manifest_hash_bytes:
        raise CurrentCoverageError("manifest sidecar differs from reconstruction")
    return dict(expected.manifest)
