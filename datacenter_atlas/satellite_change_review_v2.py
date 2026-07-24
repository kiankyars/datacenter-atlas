"""Immutable analyst review for the v55 active satellite-change run.

This carrier creates a separate review bundle. It never writes into the source
change or catalog runs, never mutates atlas data, and never turns imagery into
an identity, lifecycle, construction-status, type, capacity, power, energy,
PUE, workload, operator, or unique-site claim. Failed multi-tile jobs are
recorded only as technical metadata and are not analyst decisions.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Iterator, Mapping, Sequence


REVIEW_ID = "2026-07-20-open-seed-v55-active-review-v1"
GENERATED_AT = "2026-07-20T22:12:00Z"
REVIEWED_AT = "2026-07-20T22:11:00Z"
DEFINITION_PATH = (
    "definitions/satellite_change_reviews/"
    "2026-07-20-open-seed-v55-active-review-v1.json"
)
OUTPUT_PATH = f"satellite_change_reviews/{REVIEW_ID}"
DEFINITION_SHA256 = "5dbe5e35da8af84a84e62717355c0d5b3c0cc228a2206f6dedb20b41eab83cc3"

SOURCE_RUN_PATH = "satellite_change_runs/2026-07-20-open-seed-v55-active-001"
SOURCE_MANIFEST = {
    "bytes": 41_744,
    "path": f"{SOURCE_RUN_PATH}/batch-manifest.json",
    "sha256": "99e58d7bcc09ca850c9add4bfc15635b9808d11eabce8c3782a35a4256ec3a8a",
}
SOURCE_TREE = {
    "directories": 14,
    "directory_mode": "0555",
    "file_bytes": 8_653_890,
    "file_mode": "0444",
    "files": 31,
    "inventory_sha256": (
        "7b1d86727ccd79677357aa5e57d485a1564026257d892a972c2bce4a23caf613"
    ),
    "path": SOURCE_RUN_PATH,
    "schema_version": 1,
}

QUEUE_RUN_PATH = "satellite_review_queues/2026-07-20-open-seed-v55"
QUEUE_TREE = {
    "directories": 1,
    "directory_mode": "0555",
    "file_bytes": 424_711,
    "file_mode": "0444",
    "files": 3,
    "inventory_sha256": (
        "da6508289f2e7271d42b116ea1cfd3b971e91d4f871fda58f69bc97b958827a5"
    ),
    "path": QUEUE_RUN_PATH,
    "schema_version": 1,
}
QUEUE_MANIFEST = {
    "bytes": 12_885,
    "path": f"{QUEUE_RUN_PATH}/manifest.json",
    "sha256": "22b94402724aa349cb908d438b9c05d523519afc3fe8ce262b8a616b541ff0a4",
}
QUEUE_FILE = {
    "bytes": 411_746,
    "path": f"{QUEUE_RUN_PATH}/satellite-review-queue.jsonl",
    "sha256": "38b5125a7dc3b4c1692d254907cbd716e953492832b6df1917d391c0a6ec876a",
}

CATALOG_RUN_PATH = "satellite_review_runs/2026-07-20-open-seed-v55-active-001"
CATALOG_MANIFEST = {
    "bytes": 46_010,
    "path": f"{CATALOG_RUN_PATH}/batch-manifest.json",
    "sha256": "2c31dadb3afcab54b03f2470fa6f1bbbb8386fcb3f0e483b10e22d0882d311f9",
}
CATALOG_TREE = {
    "directories": 16,
    "directory_mode": "0555",
    "file_bytes": 5_311_182,
    "file_mode": "0444",
    "files": 22,
    "inventory_sha256": (
        "2bae18db14137d838473af58388c0d32da1349f6ec933823f16146d4bcf3725e"
    ),
    "path": CATALOG_RUN_PATH,
    "schema_version": 1,
}

QUEUE_IDS = (
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-511257788faac7f8fe916b55",
    "satq-5feb20b3df63076cce05ab3f",
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-ef22ae26b5cba60034c8567f",
)
TECHNICAL_BLOCKER_QUEUE_IDS = (
    "satq-54c6402eb93d14f1ea754e66",
    "satq-cef871428da247c3ecfadec6",
)
SOURCE_SELECTED_QUEUE_IDS = (
    "satq-ac9d66dd45f3a868190ec4c1",
    "satq-02a713b5d0ec25375cffb0c3",
    "satq-54c6402eb93d14f1ea754e66",
    "satq-ef22ae26b5cba60034c8567f",
    "satq-511257788faac7f8fe916b55",
    "satq-5feb20b3df63076cce05ab3f",
    "satq-cef871428da247c3ecfadec6",
)

RETAIN_DECISION = "retain_for_site_aligned_visible_change_follow_up"
REJECT_DECISION = "reject_for_site_promotion"

SCOPE = {
    "atlas_claim_created": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_area_claim_created": False,
    "construction_status_claim_created": False,
    "data_centre_type_claim_created": False,
    "decision_applies_only_to_imagery_visible_change_triage": True,
    "energy_claim_created": False,
    "identity_claim_created": False,
    "imagery_change_is_construction_truth": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "manual_review_completed": True,
    "operating_status_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "separately_sourced_facts_negated": False,
    "site_count_claim_created": False,
    "source_change_artifacts_copied": False,
    "technical_blockers_are_review_decisions": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}

_SOURCE_LINEAGE_SHA256 = {
    "catalog_batches": "a7ed271c6f3dd86803230ed1aeebb44e4f1cf986b1d305fc9127a1cecfeaaca0",
    "processor": "2038aa418d0a036c4cdcd4b64a1accb08b14ff5d2d5518a4c72a6debf028b103",
    "queue_bundle": "befe44a75e3f9d1c642998332581f718683fdfb254b0bc29403edd7f8833c042",
}

_JOB_LINEAGE_SHA256 = {
    "satq-02a713b5d0ec25375cffb0c3": {
        "baseline": "1a73d9b32449990f130e7d39f044446d16b0370929f4075eb963564079a23a3d",
        "catalog_source": "7c9f99a344165f2948f4e273d3b8cfa0933cc60bde01c9ebc22ca2bbb481a549",
        "change_job": "691a27fcf0fc14d485b46835d6cb482fffcf48787a04a5f308eb54f231c300f7",
        "current": "b008a19ed8120a63d006f570fb8f03dc9f110379f177f8854dced58720f275ad",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
    "satq-511257788faac7f8fe916b55": {
        "baseline": "77167936f6156db462339969fcdd440586f2d0dac5d8767c231f6ad2c7d598aa",
        "catalog_source": "d1a4089352e19088d5c95a5ebf9d433c7edf6659856c39de93d2670d5bf7565b",
        "change_job": "c1c382fb962054264e9332af3c3d91af59402f19f69ad06058fd342237925b49",
        "current": "3960d984467debbb65261d3d810a0eeab89bc4537d2ee7a4be6096b03351c511",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
    "satq-5feb20b3df63076cce05ab3f": {
        "baseline": "ca5e9bd5a98a798d7d44ca157357efda525d85be524255f36a73f4b387abc64e",
        "catalog_source": "9821b9ef90b4986832c7582986b7e6221b4b441d320f8e9797c5b999d1a22aef",
        "change_job": "b20fa5c15c93caf477f00a3f013ce0d0e1ebef7041f237bd86f463d2fe759ef1",
        "current": "7e253cd22dffa868e713f6f4f6a40a55cc0e744af7fc9e8998cb8adc624e4760",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
    "satq-ac9d66dd45f3a868190ec4c1": {
        "baseline": "27cce93dc253f533755afd05d7e0158a25cff487e1f2c829983631b58ceae016",
        "catalog_source": "640e6d10401b95bd2304051fce6fc6f75a33a9a617d02233fac2d519f6a01b3e",
        "change_job": "01ded774e70a67de5506880a59674574ce4de1f6db25d6273f75151efd5bc89e",
        "current": "117d994529097e93ec57fff2460b2f4f1452944bb5a15bc637c2292a28b97d36",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
    "satq-ef22ae26b5cba60034c8567f": {
        "baseline": "9d79d2c11bcfa52faedfd56a2443ae224cd11a4ae2ef4ef2f94a6d2f33f711fb",
        "catalog_source": "6c0cbdcb6267866ae3313c54ba7233af3b15ffe6dd721dc32f001d7bd3eb5606",
        "change_job": "29f460381cad5e2d2b718a209638547ac9c776501923233b1e95c25ea6f41eaf",
        "current": "eea51de73c3887819c307e20a0528602d965f3382dbbe6e77e73425823c9809c",
        "report_source": "ad3322c0cb2c6f4f62aefa635b2aec975638ce860ba23da02638b5f48b13e4b8",
    },
}

_TECHNICAL_BLOCKER_LINEAGE_SHA256 = {
    "satq-54c6402eb93d14f1ea754e66": {
        "catalog_source": "6877eb1bf19aa0121c6d208633a8858970588b83418800e4ec3ef91ea9c42f31",
        "change_job": "30a2ece4a38529f4df56421ef0023a9f2f74dd5785e18e6404271ae533863b67",
        "failures": "1e0e2ab50dac1a7349f4e0f90042e55d7d061a94e112afe790d0b4a5b6b9eeda",
    },
    "satq-cef871428da247c3ecfadec6": {
        "catalog_source": "b5a4bcc1b98c09936bfaee3645a9500436d57b8e7e69c7ad87b9d8d8bc1c4082",
        "change_job": "7b6a6d1f6034decb149856a0521ab784497bb1fa22124918037061a5cf9c0f76",
        "failures": "2beb15c3d2dd7a83f8653137e5895f9a2b404abfc9d096a228f222d5a1eafcdb",
    },
}

_ARTIFACTS = {
    "satq-02a713b5d0ec25375cffb0c3": {
        "after.png": {
            "bytes": 155_537,
            "sha256": "2adca54933ada19c9d56b3c10252dfd1606fa9228b9f401b6c04fc003f869193",
        },
        "before.png": {
            "bytes": 163_285,
            "sha256": "0750e39d16e21a8d522b5649845fcbf1da050c375c236177597f0e0bd6a801c4",
        },
        "change-overlay.png": {
            "bytes": 157_487,
            "sha256": "f9d0f1dc1183ca77dc66d109214f65196fa9f3de8b96514739520311398654c6",
        },
        "change-proposals.geojson": {
            "bytes": 86_684,
            "sha256": "71113787e103599a4a63381a77a9e70dcfb0304c4288f378b7d38b81eb368afb",
        },
        "comparison.png": {
            "bytes": 339_262,
            "sha256": "3a49b928b1df16b15b129bde8a6e5387faeda68a40a5753d2e566a9d93ff9282",
        },
        "report.json": {
            "bytes": 6_671,
            "sha256": "ee8fab6dd7bd7d371f5ecfefaf98692448d07aaba986ecb372d59312cd5bb461",
        },
    },
    "satq-511257788faac7f8fe916b55": {
        "after.png": {
            "bytes": 361_599,
            "sha256": "cf88babc116d6af6467be3fe2761c260f9fb00413c8e895646121b142067cb20",
        },
        "before.png": {
            "bytes": 362_199,
            "sha256": "0d7a6bbb5f04b9d0d456c55432541ea9ed009d6defbd18b72448c668717f37c6",
        },
        "change-overlay.png": {
            "bytes": 362_585,
            "sha256": "56eed7585bc97123ed92dcfa03ff3cd559ba3d4bce8c87055988dd890f7ba72c",
        },
        "change-proposals.geojson": {
            "bytes": 55_875,
            "sha256": "d702423a0c743b06385c9125c9cd8b2cbbd75d8085f90f5d6f4cb59224f3dab1",
        },
        "comparison.png": {
            "bytes": 747_089,
            "sha256": "46fdec3623f5faefcc3305ab296018cd3d7ecbe1e8bc5541b606c991784ccc74",
        },
        "report.json": {
            "bytes": 6_656,
            "sha256": "8a74bf361213c43119af1e2bcf9c03d3d04e6bc4fbc611fcfd396b0162843780",
        },
    },
    "satq-5feb20b3df63076cce05ab3f": {
        "after.png": {
            "bytes": 328_214,
            "sha256": "9a398a14b894650c5dbbe6e5219b5b830a85cce928d07f195062cac3cce0bed8",
        },
        "before.png": {
            "bytes": 337_954,
            "sha256": "20f0289fd0317a28a78968748fe8361e1bd53fe0d1637cc2c49415783772c1a3",
        },
        "change-overlay.png": {
            "bytes": 335_324,
            "sha256": "73f1b1f4885e6315b43295b50b0d3e5b121e6c46583830f9daaa45a72a32652b",
        },
        "change-proposals.geojson": {
            "bytes": 335_345,
            "sha256": "aad5018785e2b0b9ec69f278032fc341cc3fff524a1ca91b25f1e575766967be",
        },
        "comparison.png": {
            "bytes": 722_617,
            "sha256": "3fece6caacd1507ced047e58716d49092cc29851259ec70b378bde473a72b868",
        },
        "report.json": {
            "bytes": 6_672,
            "sha256": "02b082efa5758651d93cf47535ef7f606764c4035145141eb2fdee1b0969e4d5",
        },
    },
    "satq-ac9d66dd45f3a868190ec4c1": {
        "after.png": {
            "bytes": 392_893,
            "sha256": "e628944cc2d3cb2d63cf168d2a5b79d21426f8b4c0c7b240deaaa412c9b24c72",
        },
        "before.png": {
            "bytes": 392_688,
            "sha256": "f179e1b5044d25ce547aa9e93c42b84dc923364e6e1937f8d1901b8c73880fac",
        },
        "change-overlay.png": {
            "bytes": 393_813,
            "sha256": "0bd7677352f983a09a17072c4358972ab18dc64fe268fbbb5e93c2db95f3fdcb",
        },
        "change-proposals.geojson": {
            "bytes": 45_545,
            "sha256": "758f81d713ea197739444b02f56435ea1f1c144f225e7a7229060d22ff29c247",
        },
        "comparison.png": {
            "bytes": 806_653,
            "sha256": "8184b12a6ab11db17e3db14f281c121631d66162a0b5efb34908d6798577c213",
        },
        "report.json": {
            "bytes": 6_631,
            "sha256": "d8517cbfe46410599612ef4cffa1ec5e3ba00a1255b0f305bc9756d560efa6d6",
        },
    },
    "satq-ef22ae26b5cba60034c8567f": {
        "after.png": {
            "bytes": 300_310,
            "sha256": "33d3faeb6147aa51ee3fed2f100fdf0eec8971616fd5f5dc63a281396fae6db2",
        },
        "before.png": {
            "bytes": 299_628,
            "sha256": "7acc407e5672742f91543f2380b6d5664c4f45b8e0dc4af70046b00abb4e954a",
        },
        "change-overlay.png": {
            "bytes": 300_211,
            "sha256": "59bc77ed0339ff6728470497a0450a550ca339dc42541809d4deeb387a14acba",
        },
        "change-proposals.geojson": {
            "bytes": 156_812,
            "sha256": "ce1955ba6f7102fbedad5c3c860899c6fd53213c90bbbcc426234aab359a25b9",
        },
        "comparison.png": {
            "bytes": 639_231,
            "sha256": "b630e35bf7a68b4e0e1d107f06ec7a365e65d8116dd92e5014fb4e20dc8f959b",
        },
        "report.json": {
            "bytes": 6_676,
            "sha256": "c2b53aad0322cc6fd9fb8d6f0fa16770f8bb1111651d3043e142dd3b1c9d5393",
        },
    },
}

_DECISIONS = (
    {
        "decision": RETAIN_DECISION,
        "entity": {
            "id": "1d95d387-1806-5dda-a619-a50e84852137",
            "name": "Amazon SBN100 New Carlisle Physical Build",
        },
        "observations": [
            "The comparison shows new or changed large-roof surfaces concentrated in the central and northern campus area, while substantial southern coverage is masked by invalid pixels.",
            "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
        ],
        "queue_id": "satq-02a713b5d0ec25375cffb0c3",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 394_200.0,
            "proposal_component_count": 22,
            "valid_pixel_fraction": 0.5435012086271619,
            "valid_pixel_percent_display": 54.35,
        },
    },
    {
        "decision": REJECT_DECISION,
        "entity": {
            "id": "97c55ef3-761e-52c1-ac61-24383954d5b4",
            "name": "Digital Realty FRA20 Current Facility Build",
        },
        "observations": [
            "The change mask is diffuse across unrelated roofs, fields, roads, and river-adjacent surfaces throughout the city-scale AOI.",
            "The automated proposals are not isolated to the named data-centre site and are rejected for imagery-based site promotion.",
        ],
        "queue_id": "satq-511257788faac7f8fe916b55",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 248_200.0,
            "proposal_component_count": 9,
            "valid_pixel_fraction": 0.9944647031323048,
            "valid_pixel_percent_display": 99.45,
        },
    },
    {
        "decision": REJECT_DECISION,
        "entity": {
            "id": "602110aa-bf38-509f-98e7-d2c9fcea8493",
            "name": "Google Wilbarger County Data Center Current Development",
        },
        "observations": [
            "The change mask is dominated by agricultural and seasonal field changes across the AOI rather than an isolated data-centre footprint.",
            "The automated proposals are not isolated to the named data-centre site and are rejected for imagery-based site promotion.",
        ],
        "queue_id": "satq-5feb20b3df63076cce05ab3f",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 1_401_600.0,
            "proposal_component_count": 36,
            "valid_pixel_fraction": 1.0,
            "valid_pixel_percent_display": 100.0,
        },
    },
    {
        "decision": RETAIN_DECISION,
        "entity": {
            "id": "8966a315-7510-5754-a5e4-71849896b96b",
            "name": "DATA4 ATH1 First Data Center",
        },
        "observations": [
            "The comparison shows central industrial-site roof and earthwork change near the named location, while some proposals cover ordinary industrial surfaces.",
            "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
        ],
        "queue_id": "satq-ac9d66dd45f3a868190ec4c1",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 108_600.0,
            "proposal_component_count": 7,
            "valid_pixel_fraction": 1.0,
            "valid_pixel_percent_display": 100.0,
        },
    },
    {
        "decision": RETAIN_DECISION,
        "entity": {
            "id": "c6c50c6d-b3b3-5e33-bed0-4da5b6372a9b",
            "name": "Amazon Energy Way Tech Campus Physical Build",
        },
        "observations": [
            "The comparison shows a large, spatially concentrated clearing and buildout pattern within the central site AOI.",
            "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
        ],
        "queue_id": "satq-ef22ae26b5cba60034c8567f",
        "report_metrics": {
            "interpretation": "report_derived_change_mask_metadata_not_construction_area",
            "proposal_area_m2_after_component_filter": 1_412_500.0,
            "proposal_component_count": 12,
            "valid_pixel_fraction": 0.9335876430492152,
            "valid_pixel_percent_display": 93.36,
        },
    },
)

_TECHNICAL_BLOCKERS = (
    {
        "artifacts_hash_bound": 0,
        "blocker": "multi_tile_mosaic_required",
        "detail": "AOI covering window crosses asset red; a future multi-tile mosaic is required",
        "entity": {
            "id": "6710faa1-0010-5269-b1f3-7d7ebcda1ced",
            "name": "Menlo Digital MD-PHX1 Current Site Preparation",
        },
        "metadata_only": True,
        "queue_id": "satq-54c6402eb93d14f1ea754e66",
        "review_decision_created": False,
        "source_state": "failed",
    },
    {
        "artifacts_hash_bound": 0,
        "blocker": "multi_tile_mosaic_required",
        "detail": "AOI covering window crosses asset red; a future multi-tile mosaic is required",
        "entity": {
            "id": "627a4c00-7a7a-5c0d-9f03-a76eb10df7b3",
            "name": "Ada Infrastructure Docklands Three-Building Development",
        },
        "metadata_only": True,
        "queue_id": "satq-cef871428da247c3ecfadec6",
        "review_decision_created": False,
        "source_state": "failed",
    },
)

REVIEWS_FILENAME = "analyst-reviews.jsonl"
SUMMARY_FILENAME = "summary.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {
        ATTRIBUTION_FILENAME,
        README_FILENAME,
        REVIEWS_FILENAME,
        SUMMARY_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)


class SatelliteChangeReviewV2Error(ValueError):
    """Raised when review inputs, semantics, or publication fail closed."""


@dataclass(frozen=True, slots=True)
class SatelliteChangeReviewV2Bundle:
    files: Mapping[str, bytes]
    manifest: Mapping[str, Any]


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SatelliteChangeReviewV2Error(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteChangeReviewV2Error(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteChangeReviewV2Error(f"{label} must be a JSON object")
    return value


def _tree_inventory(root: Path, label: str) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteChangeReviewV2Error(f"{label} must be a regular directory")
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SatelliteChangeReviewV2Error(
                f"{label} contains a symlink: {relative}"
            )
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            if mode != 0o555:
                raise SatelliteChangeReviewV2Error(
                    f"{label} directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
            directories += 1
        elif path.is_file():
            if mode != 0o444:
                raise SatelliteChangeReviewV2Error(
                    f"{label} file mode changed: {relative} is {mode:04o}"
                )
            raw = path.read_bytes()
            digest.update(
                (f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n").encode(
                    "utf-8"
                )
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise SatelliteChangeReviewV2Error(
                f"{label} contains unsupported entry: {relative}"
            )
    return {
        "directories": directories,
        "directory_mode": "0555",
        "file_bytes": file_bytes,
        "file_mode": "0444",
        "files": files,
        "inventory_sha256": digest.hexdigest(),
        "schema_version": 1,
    }


def _expected_inventory(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in spec.items() if key != "path"}


def _validate_tree(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> dict[str, Any]:
    inventory = _tree_inventory(package_root / str(spec["path"]), label)
    if inventory != _expected_inventory(spec):
        raise SatelliteChangeReviewV2Error(f"{label} closed tree changed")
    return inventory


def _artifact_paths(queue_id: str) -> dict[str, dict[str, Any]]:
    base = f"{SOURCE_RUN_PATH}/jobs/{queue_id}/change"
    return {
        name: {
            "bytes": spec["bytes"],
            "path": f"{base}/{name}",
            "sha256": spec["sha256"],
        }
        for name, spec in sorted(_ARTIFACTS[queue_id].items())
    }


def make_review_definition(
    decisions: Sequence[Mapping[str, Any]] | None = None,
    technical_blockers: Sequence[Mapping[str, Any]] | None = None,
) -> bytes:
    """Return canonical definition bytes, independent of caller row order."""

    selected = list(_DECISIONS if decisions is None else decisions)
    by_id = {str(decision.get("queue_id")): dict(decision) for decision in selected}
    if set(by_id) != set(QUEUE_IDS) or len(selected) != len(QUEUE_IDS):
        raise SatelliteChangeReviewV2Error(
            "definition decisions must contain exactly the five reviewed queue IDs"
        )
    rows = []
    for queue_id in QUEUE_IDS:
        row = dict(by_id[queue_id])
        row["input_artifacts"] = _artifact_paths(queue_id)
        row["review_method"] = (
            "completed_analyst_visual_inspection_of_before_after_comparison_overlay_"
            "and_proposals_at_original_resolution"
        )
        row["reviewed_at"] = REVIEWED_AT
        rows.append(row)

    blocker_rows = list(
        _TECHNICAL_BLOCKERS if technical_blockers is None else technical_blockers
    )
    blockers_by_id = {
        str(blocker.get("queue_id")): dict(blocker) for blocker in blocker_rows
    }
    if set(blockers_by_id) != set(TECHNICAL_BLOCKER_QUEUE_IDS) or len(
        blocker_rows
    ) != len(TECHNICAL_BLOCKER_QUEUE_IDS):
        raise SatelliteChangeReviewV2Error(
            "definition blockers must contain exactly the two technical queue IDs"
        )
    document = {
        "decisions": rows,
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "schema_version": 2,
        "scope": SCOPE,
        "source_catalog_run": {
            "closed_tree": CATALOG_TREE,
            "manifest": CATALOG_MANIFEST,
        },
        "source_change_run": {
            "closed_tree": SOURCE_TREE,
            "manifest": SOURCE_MANIFEST,
        },
        "source_queue_bundle": {
            "closed_tree": QUEUE_TREE,
            "manifest": QUEUE_MANIFEST,
            "queue": QUEUE_FILE,
        },
        "technical_blockers": [
            blockers_by_id[queue_id] for queue_id in TECHNICAL_BLOCKER_QUEUE_IDS
        ],
    }
    return _canonical_json(document)


def _contains_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, Mapping):
        return forbidden in value or any(
            _contains_key(child, forbidden) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


def _validate_definition(
    definition_path: str | Path,
) -> tuple[dict[str, Any], bytes, Path]:
    path = Path(definition_path).resolve()
    package_root = path.parents[2]
    if path != package_root / DEFINITION_PATH:
        raise SatelliteChangeReviewV2Error("review definition publication path changed")
    raw = _read_regular(path, "review definition")
    document = _json_object(raw, "review definition")
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV2Error("review definition is not canonical JSON")
    if _sha256(raw) != DEFINITION_SHA256:
        raise SatelliteChangeReviewV2Error("review definition content changed")
    if raw != make_review_definition():
        raise SatelliteChangeReviewV2Error("review definition semantics changed")
    if _contains_key(document, "confidence"):
        raise SatelliteChangeReviewV2Error("confidence is forbidden in this review")
    if set(document) != {
        "decisions",
        "generated_at",
        "review_id",
        "schema_version",
        "scope",
        "source_catalog_run",
        "source_change_run",
        "source_queue_bundle",
        "technical_blockers",
    }:
        raise SatelliteChangeReviewV2Error("review definition keys changed")
    if (
        document.get("review_id") != REVIEW_ID
        or document.get("generated_at") != GENERATED_AT
        or document.get("schema_version") != 2
        or document.get("scope") != SCOPE
        or document.get("source_catalog_run")
        != {"closed_tree": CATALOG_TREE, "manifest": CATALOG_MANIFEST}
        or document.get("source_change_run")
        != {"closed_tree": SOURCE_TREE, "manifest": SOURCE_MANIFEST}
        or document.get("source_queue_bundle")
        != {
            "closed_tree": QUEUE_TREE,
            "manifest": QUEUE_MANIFEST,
            "queue": QUEUE_FILE,
        }
    ):
        raise SatelliteChangeReviewV2Error(
            "review identity, sources, schema, or scope changed"
        )
    for timestamp in (GENERATED_AT, REVIEWED_AT):
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed > datetime.now(UTC):
            raise SatelliteChangeReviewV2Error("review timestamp is in the future")
    decisions = document.get("decisions")
    if not isinstance(decisions, list) or [
        row.get("queue_id") for row in decisions
    ] != list(QUEUE_IDS):
        raise SatelliteChangeReviewV2Error(
            "review decisions are missing or out of order"
        )
    expected_decisions = {row["queue_id"]: row for row in _DECISIONS}
    for row in decisions:
        queue_id = row["queue_id"]
        expected = expected_decisions[queue_id]
        if (
            row.get("decision") != expected["decision"]
            or row.get("entity") != expected["entity"]
            or row.get("observations") != expected["observations"]
            or row.get("report_metrics") != expected["report_metrics"]
            or row.get("reviewed_at") != REVIEWED_AT
            or row.get("input_artifacts") != _artifact_paths(queue_id)
        ):
            raise SatelliteChangeReviewV2Error(f"review decision changed: {queue_id}")
    blockers = document.get("technical_blockers")
    if blockers != list(_TECHNICAL_BLOCKERS):
        raise SatelliteChangeReviewV2Error("technical blocker metadata changed")
    return document, raw, package_root


def _canonical_object_sha256(value: Any) -> str:
    return _sha256(_canonical_line(value))


def _validate_false_claims(value: Mapping[str, Any], label: str) -> None:
    claim_keys = {
        "atlas_mutation",
        "data_centre_type_claim",
        "energy_claim",
        "identity_claim",
        "imagery_data_centre_type_inference",
        "imagery_energy_inference",
        "imagery_identity_inference",
        "imagery_it_capacity_inference",
        "imagery_lifecycle_inference",
        "imagery_load_inference",
        "imagery_operating_status_inference",
        "imagery_operator_inference",
        "imagery_power_inference",
        "imagery_pue_inference",
        "imagery_unique_site_inference",
        "imagery_workload_inference",
        "it_capacity_claim",
        "lifecycle_claim",
        "operating_status_claim",
        "operator_claim",
        "power_claim",
        "pue_claim",
        "workload_claim",
    }
    for key in claim_keys & set(value):
        if value[key] is not False:
            raise SatelliteChangeReviewV2Error(f"{label} enables claim: {key}")


def _validate_pinned_json(
    package_root: Path, spec: Mapping[str, Any], label: str
) -> dict[str, Any]:
    raw = _read_regular(package_root / str(spec["path"]), label)
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise SatelliteChangeReviewV2Error(f"{label} changed")
    document = _json_object(raw, label)
    if raw != _canonical_json(document):
        raise SatelliteChangeReviewV2Error(f"{label} is not canonical JSON")
    return document


def _validate_upstream_lineage(package_root: Path) -> dict[str, Any]:
    _validate_tree(package_root, QUEUE_TREE, "source queue bundle")
    queue_manifest = _validate_pinned_json(
        package_root, QUEUE_MANIFEST, "source queue manifest"
    )
    queue_raw = _read_regular(package_root / QUEUE_FILE["path"], "source queue")
    if (
        len(queue_raw) != QUEUE_FILE["bytes"]
        or _sha256(queue_raw) != QUEUE_FILE["sha256"]
    ):
        raise SatelliteChangeReviewV2Error("source queue changed")
    if (
        queue_manifest.get("pipeline") != "global_satellite_review_queue"
        or queue_manifest.get("schema_version") != 1
        or queue_manifest.get("counts", {}).get("queue_jobs") != 150
    ):
        raise SatelliteChangeReviewV2Error("source queue manifest contract changed")

    _validate_tree(package_root, CATALOG_TREE, "source catalog run")
    catalog_manifest = _validate_pinned_json(
        package_root, CATALOG_MANIFEST, "source catalog manifest"
    )
    if (
        catalog_manifest.get("pipeline") != "satellite_review_catalog_batch"
        or catalog_manifest.get("schema_version") != 3
        or catalog_manifest.get("state") != "incomplete"
        or catalog_manifest.get("summary")
        != {
            "jobs_completed": 7,
            "jobs_failed": 0,
            "jobs_pending": 74,
            "jobs_selected": 81,
            "jobs_unavailable_no_scene": 0,
        }
        or len(catalog_manifest.get("jobs", {})) != 81
        or {
            queue_id
            for queue_id, job in catalog_manifest.get("jobs", {}).items()
            if job.get("state") == "completed"
        }
        != set(SOURCE_SELECTED_QUEUE_IDS)
    ):
        raise SatelliteChangeReviewV2Error("source catalog manifest contract changed")
    if (
        catalog_manifest.get("queue_bundle", {}).get("manifest_sha256")
        != QUEUE_MANIFEST["sha256"]
        or catalog_manifest.get("queue_bundle", {}).get("queue_sha256")
        != QUEUE_FILE["sha256"]
    ):
        raise SatelliteChangeReviewV2Error("catalog-to-queue lineage changed")
    return catalog_manifest


def _validate_source_tree(package_root: Path) -> dict[str, Any]:
    inventory = _validate_tree(package_root, SOURCE_TREE, "source change run")
    expected_paths = {"batch-manifest.json"}
    for queue_id in QUEUE_IDS:
        expected_paths.update(
            f"jobs/{queue_id}/change/{name}" for name in _ARTIFACTS[queue_id]
        )
    root = package_root / SOURCE_RUN_PATH
    actual_paths = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual_paths != expected_paths:
        raise SatelliteChangeReviewV2Error("source change run file inventory changed")
    return inventory


def _validate_catalog_artifacts(
    package_root: Path,
    source_manifest: Mapping[str, Any],
    catalog_manifest: Mapping[str, Any],
) -> None:
    for queue_id in SOURCE_SELECTED_QUEUE_IDS:
        source_job = source_manifest["jobs"][queue_id]
        catalog_source = source_job["catalog_source"]
        catalog_job = catalog_manifest["jobs"][queue_id]
        if (
            catalog_source.get("catalog_batch_manifest_sha256")
            != CATALOG_MANIFEST["sha256"]
            or catalog_source.get("selected_ids") != catalog_job.get("selected_ids")
            or catalog_source.get("artifacts") != catalog_job.get("artifacts")
            or catalog_source.get("catalog_output_directory")
            != catalog_job.get("output_directory")
        ):
            raise SatelliteChangeReviewV2Error(
                f"source-to-catalog job lineage changed: {queue_id}"
            )
        for name, spec in catalog_source["artifacts"].items():
            path = (
                package_root / CATALOG_RUN_PATH / "jobs" / queue_id / "catalog" / name
            )
            raw = _read_regular(path, f"{queue_id} catalog {name}")
            if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
                raise SatelliteChangeReviewV2Error(
                    f"source catalog artifact changed: {queue_id} {name}"
                )


def _source_documents(
    package_root: Path,
    definition: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    catalog_manifest = _validate_upstream_lineage(package_root)
    manifest = _validate_pinned_json(
        package_root, SOURCE_MANIFEST, "source change manifest"
    )
    if (
        manifest.get("pipeline") != "satellite_review_change_batch"
        or manifest.get("schema_version") != 1
        or manifest.get("state") != "incomplete"
        or manifest.get("selection", {}).get("selected_queue_ids")
        != list(SOURCE_SELECTED_QUEUE_IDS)
        or manifest.get("summary")
        != {
            "catalog_completed_jobs": 7,
            "catalog_completed_jobs_excluded": 0,
            "catalog_completed_jobs_not_in_inclusion": 0,
            "exclusion_ids_without_completed_catalog": 0,
            "jobs_completed": 5,
            "jobs_exhausted": 0,
            "jobs_failed": 2,
            "jobs_pending": 0,
            "jobs_running": 0,
            "jobs_selected": 7,
        }
        or set(manifest.get("jobs", {}))
        != set(QUEUE_IDS) | set(TECHNICAL_BLOCKER_QUEUE_IDS)
    ):
        raise SatelliteChangeReviewV2Error("source change manifest contract changed")
    _validate_false_claims(manifest.get("scope", {}), "source manifest scope")
    for key, expected_sha256 in _SOURCE_LINEAGE_SHA256.items():
        if _canonical_object_sha256(manifest.get(key)) != expected_sha256:
            raise SatelliteChangeReviewV2Error(f"source lineage changed: {key}")
    catalog_batch = manifest["catalog_batches"][0]
    if (
        catalog_batch.get("manifest_sha256") != CATALOG_MANIFEST["sha256"]
        or catalog_batch.get("manifest_bytes") != CATALOG_MANIFEST["bytes"]
        or manifest.get("queue_bundle", {}).get("manifest_sha256")
        != QUEUE_MANIFEST["sha256"]
        or manifest.get("queue_bundle", {}).get("queue_sha256") != QUEUE_FILE["sha256"]
    ):
        raise SatelliteChangeReviewV2Error("source upstream lineage changed")
    _validate_catalog_artifacts(package_root, manifest, catalog_manifest)

    reports: dict[str, dict[str, Any]] = {}
    definition_decisions = {row["queue_id"]: row for row in definition["decisions"]}
    for queue_id in QUEUE_IDS:
        job = manifest["jobs"][queue_id]
        decision = definition_decisions[queue_id]
        if (
            job.get("queue_id") != queue_id
            or job.get("state") != "completed"
            or job.get("entity") != decision["entity"]
            or job.get("artifacts") != _ARTIFACTS[queue_id]
        ):
            raise SatelliteChangeReviewV2Error(f"source job changed: {queue_id}")
        for key in ("catalog_source", "change_job"):
            if (
                _canonical_object_sha256(job.get(key))
                != _JOB_LINEAGE_SHA256[queue_id][key]
            ):
                raise SatelliteChangeReviewV2Error(
                    f"source job lineage changed: {queue_id} {key}"
                )
        for name, spec in decision["input_artifacts"].items():
            raw = _read_regular(package_root / spec["path"], f"{queue_id} {name}")
            if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
                raise SatelliteChangeReviewV2Error(
                    f"source artifact changed: {queue_id} {name}"
                )
            if {"bytes": spec["bytes"], "sha256": spec["sha256"]} != job["artifacts"][
                name
            ]:
                raise SatelliteChangeReviewV2Error(
                    f"source manifest artifact binding changed: {queue_id} {name}"
                )
        report_spec = decision["input_artifacts"]["report.json"]
        report_raw = _read_regular(
            package_root / report_spec["path"], f"{queue_id} report"
        )
        report = _json_object(report_raw, f"{queue_id} report")
        if report_raw != _canonical_json(report):
            raise SatelliteChangeReviewV2Error(
                f"source report is not canonical: {queue_id}"
            )
        metrics = decision["report_metrics"]
        if (
            report.get("algorithm_version") != "sentinel-2-l2a-change-v2"
            or report.get("entity") != decision["entity"]
            or report.get("metrics", {}).get("proposal_component_count")
            != metrics["proposal_component_count"]
            or report.get("metrics", {}).get("proposal_area_m2_after_component_filter")
            != metrics["proposal_area_m2_after_component_filter"]
            or report.get("metrics", {}).get("valid_pixel_fraction")
            != metrics["valid_pixel_fraction"]
            or round(report["metrics"]["valid_pixel_fraction"] * 100, 2)
            != metrics["valid_pixel_percent_display"]
        ):
            raise SatelliteChangeReviewV2Error(f"report metrics changed: {queue_id}")
        _validate_false_claims(report.get("classification", {}), f"{queue_id} report")
        if report.get("outputs") != {
            name: _ARTIFACTS[queue_id][name]
            for name in sorted(_ARTIFACTS[queue_id])
            if name != "report.json"
        }:
            raise SatelliteChangeReviewV2Error(f"report outputs changed: {queue_id}")
        for key, source_key in (
            ("baseline", "baseline"),
            ("current", "current"),
            ("report_source", "source"),
        ):
            if (
                _canonical_object_sha256(report.get(source_key))
                != _JOB_LINEAGE_SHA256[queue_id][key]
            ):
                raise SatelliteChangeReviewV2Error(
                    f"report source lineage changed: {queue_id} {source_key}"
                )
        reports[queue_id] = report

    blocker_metadata = []
    definition_blockers = {
        row["queue_id"]: row for row in definition["technical_blockers"]
    }
    for queue_id in TECHNICAL_BLOCKER_QUEUE_IDS:
        job = manifest["jobs"][queue_id]
        blocker = definition_blockers[queue_id]
        if (
            job.get("queue_id") != queue_id
            or job.get("state") != "failed"
            or job.get("entity") != blocker["entity"]
            or job.get("attempts") != 1
            or job.get("artifacts") is not None
            or job.get("report") is not None
            or len(job.get("failures", [])) != 1
            or job["failures"][0].get("kind") != "command_exit"
            or not job["failures"][0].get("error", "").endswith(blocker["detail"])
        ):
            raise SatelliteChangeReviewV2Error(
                f"technical blocker source changed: {queue_id}"
            )
        for key in ("catalog_source", "change_job", "failures"):
            if (
                _canonical_object_sha256(job.get(key))
                != _TECHNICAL_BLOCKER_LINEAGE_SHA256[queue_id][key]
            ):
                raise SatelliteChangeReviewV2Error(
                    f"technical blocker lineage changed: {queue_id} {key}"
                )
        blocker_metadata.append(
            {
                **blocker,
                "source_lineage": {
                    "catalog_source_sha256": _TECHNICAL_BLOCKER_LINEAGE_SHA256[
                        queue_id
                    ]["catalog_source"],
                    "change_job_sha256": _TECHNICAL_BLOCKER_LINEAGE_SHA256[queue_id][
                        "change_job"
                    ],
                    "failures_sha256": _TECHNICAL_BLOCKER_LINEAGE_SHA256[queue_id][
                        "failures"
                    ],
                    "source_change_manifest": SOURCE_MANIFEST,
                },
            }
        )
    return manifest, reports, blocker_metadata


def _review_record(
    decision: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    queue_id = str(decision["queue_id"])
    job = source_manifest["jobs"][queue_id]
    return {
        "decision": decision["decision"],
        "decision_scope": "imagery_visible_change_triage_only",
        "entity": decision["entity"],
        "input_artifacts": decision["input_artifacts"],
        "observations": decision["observations"],
        "queue_id": queue_id,
        "report_metrics": decision["report_metrics"],
        "review_method": decision["review_method"],
        "reviewed_at": REVIEWED_AT,
        "schema_version": 2,
        "scope": SCOPE,
        "source_lineage": {
            "algorithm_version": report["algorithm_version"],
            "baseline": {
                key: report["baseline"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "catalog_batch_manifest": CATALOG_MANIFEST,
            "catalog_source_sha256": _JOB_LINEAGE_SHA256[queue_id]["catalog_source"],
            "change_job_sha256": _JOB_LINEAGE_SHA256[queue_id]["change_job"],
            "current": {
                key: report["current"][key]
                for key in ("datetime", "id", "mgrs_tile", "stac_item_sha256")
            },
            "processor_sha256": _SOURCE_LINEAGE_SHA256["processor"],
            "queue_manifest": QUEUE_MANIFEST,
            "queue_sha256": QUEUE_FILE["sha256"],
            "report_source": report["source"],
            "source_change_manifest": SOURCE_MANIFEST,
            "source_report_sha256": job["report"]["report_sha256"],
        },
    }


def _readme_bytes() -> bytes:
    return (
        "# Analyst review of v55 active satellite-change outputs\n\n"
        "This immutable bundle records five completed original-resolution manual "
        "visual-review decisions: three outputs are retained only for site-aligned "
        "visible-change follow-up, and two are rejected for imagery-based site "
        "promotion. Two additional source jobs failed because their AOIs require a "
        "future multi-tile mosaic; they are metadata-only technical blockers and are "
        "not review decisions.\n\n"
        "The source reports, PNGs, and GeoJSON remain in the frozen source change run; "
        "this bundle copies none of them and binds all 30 completed-job artifacts by "
        "path, byte count, and SHA-256. Reported component counts, proposal areas, and "
        "valid-pixel fractions are change-mask metadata, not construction areas.\n\n"
        "These decisions create no atlas, identity, lifecycle, construction-status, "
        "operating-status, operator, data-centre type, workload, capacity, power, "
        "energy, PUE, or site-count claim, and negate no separately sourced fact.\n"
    ).encode("utf-8")


def _attribution_bytes() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "Source imagery is not copied into this review bundle; exact source artifacts "
        "remain hash-linked under their upstream terms.\n"
    ).encode("utf-8")


def build_satellite_change_review_v2(
    definition_path: str | Path,
) -> SatelliteChangeReviewV2Bundle:
    """Build deterministic review bytes from the frozen source runs."""

    definition, definition_raw, package_root = _validate_definition(definition_path)
    source_inventory = _validate_source_tree(package_root)
    source_manifest, reports, blocker_metadata = _source_documents(
        package_root, definition
    )
    decisions = {row["queue_id"]: row for row in definition["decisions"]}
    review_records = [
        _review_record(decisions[queue_id], source_manifest, reports[queue_id])
        for queue_id in QUEUE_IDS
    ]
    reviews_bytes = b"".join(_canonical_line(record) for record in review_records)
    summary = {
        "counts": {
            "decisions": 5,
            "reject_for_site_promotion": 2,
            "retain_for_site_aligned_visible_change_follow_up": 3,
            "source_artifacts_hash_bound": 30,
            "technical_multitile_failures": 2,
        },
        "decisions": [
            {
                "decision": record["decision"],
                "entity": record["entity"],
                "queue_id": record["queue_id"],
                "report_metrics": record["report_metrics"],
            }
            for record in review_records
        ],
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 2,
        "scope": SCOPE,
        "source_catalog_run": {
            "closed_tree": CATALOG_TREE,
            "manifest": CATALOG_MANIFEST,
        },
        "source_change_run": {
            "closed_tree": {**source_inventory, "path": SOURCE_RUN_PATH},
            "manifest": SOURCE_MANIFEST,
        },
        "source_queue_bundle": {
            "closed_tree": QUEUE_TREE,
            "manifest": QUEUE_MANIFEST,
            "queue": QUEUE_FILE,
        },
        "technical_blockers": blocker_metadata,
    }
    summary_bytes = _canonical_json(summary)
    output_files = {
        ATTRIBUTION_FILENAME: _attribution_bytes(),
        README_FILENAME: _readme_bytes(),
        REVIEWS_FILENAME: reviews_bytes,
        SUMMARY_FILENAME: summary_bytes,
    }
    manifest = {
        "artifacts": {
            filename: {"bytes": len(raw), "sha256": _sha256(raw)}
            for filename, raw in sorted(output_files.items())
        },
        "definition": {
            "bytes": len(definition_raw),
            "path": DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": "datacenter-atlas-satellite-change-analyst-review-v2",
        "generated_at": GENERATED_AT,
        "review_id": REVIEW_ID,
        "reviewed_at": REVIEWED_AT,
        "schema_version": 2,
        "scope": SCOPE,
        "source_artifacts": {
            queue_id: _artifact_paths(queue_id) for queue_id in QUEUE_IDS
        },
        "source_catalog_run": {
            "closed_tree": CATALOG_TREE,
            "manifest": CATALOG_MANIFEST,
        },
        "source_change_run": {
            "closed_tree": {**source_inventory, "path": SOURCE_RUN_PATH},
            "manifest": SOURCE_MANIFEST,
        },
        "source_lineage": {
            "catalog_batches": source_manifest["catalog_batches"],
            "processor": source_manifest["processor"],
            "queue_bundle": source_manifest["queue_bundle"],
            "sha256": _SOURCE_LINEAGE_SHA256,
        },
        "source_queue_bundle": {
            "closed_tree": QUEUE_TREE,
            "manifest": QUEUE_MANIFEST,
            "queue": QUEUE_FILE,
        },
        "technical_blockers": blocker_metadata,
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar_bytes = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    files = {
        **output_files,
        MANIFEST_FILENAME: manifest_bytes,
        MANIFEST_HASH_FILENAME: sidecar_bytes,
    }
    if any(
        _contains_key(value, "confidence")
        for value in (review_records, summary, manifest)
    ):
        raise SatelliteChangeReviewV2Error("confidence leaked into review bundle")
    return SatelliteChangeReviewV2Bundle(files=files, manifest=manifest)


def _write_file(path: Path, raw: bytes) -> None:
    with path.open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())


@contextmanager
def _exclusive_output_lock(destination: Path) -> Iterator[None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise SatelliteChangeReviewV2Error(
            f"refusing active output lock: {lock}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def write_review_definition(
    package_root: str | Path,
    output_path: str | Path,
) -> str:
    """Atomically create, but never replace, the canonical review definition."""

    root = Path(package_root).resolve()
    destination = Path(output_path).resolve()
    if destination != root / DEFINITION_PATH:
        raise SatelliteChangeReviewV2Error("definition output path changed")
    raw = make_review_definition()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV2Error(
                f"refusing existing output: {destination}"
            )
        stage = destination.parent / f".{destination.name}.{os.getpid()}.tmp"
        try:
            _write_file(stage, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV2Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        finally:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass
    return _sha256(raw)


def write_satellite_change_review_v2(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish a frozen review bundle without replacing anything."""

    if freeze is not True:
        raise SatelliteChangeReviewV2Error("review publication requires freeze=True")
    bundle = build_satellite_change_review_v2(definition_path)
    destination = Path(output_path).resolve()
    with _exclusive_output_lock(destination):
        if destination.exists() or destination.is_symlink():
            raise SatelliteChangeReviewV2Error(
                f"refusing existing output: {destination}"
            )
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            for filename, raw in sorted(bundle.files.items()):
                _write_file(stage / filename, raw)
            if destination.exists() or destination.is_symlink():
                raise SatelliteChangeReviewV2Error(
                    f"refusing late output collision: {destination}"
                )
            stage.replace(destination)
            _fsync_directory(destination.parent)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    for filename in BUNDLE_FILES:
        (destination / filename).chmod(0o444)
    destination.chmod(0o555)
    return dict(bundle.manifest)


def validate_satellite_change_review_v2(
    output_path: str | Path,
    *,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce a frozen review bundle byte-for-byte."""

    directory = Path(output_path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteChangeReviewV2Error("review bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise SatelliteChangeReviewV2Error("review bundle file set changed")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != 0o444
        for entry in entries
    ):
        raise SatelliteChangeReviewV2Error("review bundle must be frozen 0555/0444")
    actual = {
        filename: _read_regular(directory / filename, f"review {filename}")
        for filename in BUNDLE_FILES
    }
    manifest = _json_object(actual[MANIFEST_FILENAME], "review manifest")
    expected_sidecar = (
        f"{_sha256(actual[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    if actual[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise SatelliteChangeReviewV2Error("review manifest sidecar changed")
    expected = build_satellite_change_review_v2(definition_path)
    if actual != expected.files:
        raise SatelliteChangeReviewV2Error(
            "review bundle differs from offline reconstruction"
        )
    if manifest != expected.manifest:
        raise SatelliteChangeReviewV2Error("review manifest semantics changed")
    return dict(expected.manifest)


__all__ = [
    "BUNDLE_FILES",
    "CATALOG_MANIFEST",
    "CATALOG_RUN_PATH",
    "CATALOG_TREE",
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "GENERATED_AT",
    "OUTPUT_PATH",
    "QUEUE_FILE",
    "QUEUE_IDS",
    "QUEUE_MANIFEST",
    "QUEUE_RUN_PATH",
    "QUEUE_TREE",
    "REJECT_DECISION",
    "RETAIN_DECISION",
    "REVIEWED_AT",
    "REVIEW_ID",
    "SCOPE",
    "SOURCE_MANIFEST",
    "SOURCE_RUN_PATH",
    "SOURCE_TREE",
    "TECHNICAL_BLOCKER_QUEUE_IDS",
    "SatelliteChangeReviewV2Bundle",
    "SatelliteChangeReviewV2Error",
    "build_satellite_change_review_v2",
    "make_review_definition",
    "validate_satellite_change_review_v2",
    "write_review_definition",
    "write_satellite_change_review_v2",
]
