"""Publish the governed Goodman/DataBank LAX01 enrichment source artifact.

The parent-authored source resolves the existing Goodman LAX01 program anchor
to DataBank's Vernon address and adds one brochure-typed planned critical-IT
observation. Exact raw response bytes are pinned but never redistributed. This
module publishes only the source and its evidence artifact; it performs no
open-seed or downstream integration.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from . import global_official_builds_six_candidate_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
SOURCE_FILENAME = "curated-official-2026-07-22-goodman-databank-lax01-enrichment.json"
SOURCE = SOURCES_ROOT / SOURCE_FILENAME
ARTIFACT_ID = "goodman-databank-lax01-official-enrichment-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".goodman-databank-lax01-official-enrichment.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-goodman-databank-lax01-20260722.KCRl0m")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-goodman-databank-lax01-20260722.KCRl0m")
CAPTURE_FILE_COUNT = 8
CAPTURE_TOTAL_BYTES = 20_896_741
CAPTURE_TREE_SHA256 = "8f55778085285ab01c40b0cb00c34f438162967ded753e70dbd1bc64de9d0a51"
RETRIEVED_AT = "2026-07-22T02:37:32Z"
LATEST_FAILED_CAPTURE_AT = "2026-07-22T02:53:33Z"

SOURCE_PIN = (
    13_595,
    "fc07e93af6357b754ee6b03d052958e9f73201c177459cf1d2c19b4ca4a5ebf5",
)

V93_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v93.json"
V93_RELEASE = ROOT / "releases/2026-07-21-open-seed-v93"
V93_MANIFEST = V93_RELEASE / "manifest.json"
V93_ENTITIES = V93_RELEASE / "entities.csv"
V93_SOURCE_INPUTS = V93_RELEASE / "source_inputs.json"
V93_PINS = {
    V93_DEFINITION: (
        110_743,
        "cf8ed21cd0816f457fa2cede36fbf1bf012d62ed61d03a5e3213de9946394e9c",
    ),
    V93_MANIFEST: (
        16_832,
        "9a5b39004ab1a4c7994ad653d5d9603572b4a47a3c502ea222eeae38d32fa05c",
    ),
    V93_ENTITIES: (
        1_029_791,
        "f690d838165ced6822b891f5099adea82db46fba97e53dbcb462328b5af6628b",
    ),
    V93_SOURCE_INPUTS: (
        414_095,
        "81cf558da4aef80bdc957116ceda84cd565960b6471db0ada95cddd02e0f483e",
    ),
}
V93_TREE_SHA256 = "71c531ffa7f8383e2ae553a71abe15e940e8d6251acccbf17556bc492df78f0d"
V93_INPUT_COUNT = 488
V93_ENTITY_COUNT = 994

PRIOR_SOURCE = SOURCES_ROOT / (
    "curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json"
)
PRIOR_PIN = (
    21_121,
    "296b17b45a9a6f56037b137ca68f37e549607317c2550b3e606a59e640528249",
    1_784_540_838_408_982_459,
    0o644,
)
PRIOR_RETRIEVED_AT = "2026-07-20T09:05:11Z"

CAMPUS_KEY = "curated:goodman-lax01-los-angeles-program-anchor"
PROJECT_KEY = f"{CAMPUS_KEY}:first-site-current-development"
DATABANK_EVIDENCE = "databank-goodman-lax01-vernon-jv-2026-04-07-captured-2026-07-22"
BROCHURE_EVIDENCE = "goodman-lax01-vernon-brochure-captured-2026-07-22"
EVIDENCE_KEYS = (DATABANK_EVIDENCE, BROCHURE_EVIDENCE)
EXACT_ADDRESS = "3094 E Vernon Avenue, Vernon, California 90058, United States"

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

_canonical = publication._canonical
_promote_noreplace = publication._promote_noreplace
_identity = publication._identity


class GoodmanLax01Error(RuntimeError):
    """Raised when a source, semantic, or publication invariant differs."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GoodmanLax01Error(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise GoodmanLax01Error(f"pinned ordinary file is absent: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise GoodmanLax01Error(f"pinned file differs: {path}: {actual!r}")


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _has_identity(
    path: Path, identity: tuple[int, int], *, directory: bool
) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    correct_type = (
        stat.S_ISDIR(metadata.st_mode)
        if directory
        else stat.S_ISREG(metadata.st_mode)
    )
    return correct_type and (metadata.st_dev, metadata.st_ino) == identity


CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "databank_lax01_2026.body": (125_542, "8fedac33e78cc295046652bf4526009fcc948f6a280e2d0866ac485ff3fa5630"),
    "databank_lax01_2026.headers": (6_973, "60baf569845687659ec83149891c9cf16dca1880312d694ae4890fad33b4061c"),
    "databank_lax01_press.body": (129_303, "7f1478a4fc00e088f48fa0c41fe63d7f159a754c5dd6577ce2b7b7a98da48a57"),
    "databank_lax01_press.headers": (6_973, "9f88fa1c4b4a707cf9c341bd4b2c98f527b3da783250315d380000d700355af4"),
    "goodman_ce_lax01_2026.headers": (2_212, "374023ad048fc1022ec0c415566ed1d04512617c3127bd5011f123ce79a2051e"),
    "goodman_lax01_brochure.body": (20_622_431, "5186b59c29c3b7d64b28dbbd1bb8cd8ec041e82232086b4e975ccc945b32314d"),
    "goodman_lax01_brochure.headers": (1_095, "79d97a2a546b0b247c785d96f3ee4639402b8dd4eccfabb92f2b9308dc61c2c6"),
    "goodman_lax01_topping_out.headers": (2_212, "04349769dee977e1e2a8cd7b9a7b448dbb416c7dc3a8974cacdf8d2a51ecc3c1"),
}


@dataclass(frozen=True)
class EvidenceCapture:
    capture_id: str
    body_name: str
    header_name: str
    url: str
    response_http_date: str
    content_type: str


EVIDENCE_CAPTURES = (
    EvidenceCapture(
        "databank_lax01_press",
        "databank_lax01_press.body",
        "databank_lax01_press.headers",
        "https://www.databank.com/resources/press-releases/databank-and-goodman-group-partner-to-open-new-landmark-data-center-in-los-angeles/",
        "2026-07-22T02:37:32Z",
        "text/html; charset=UTF-8",
    ),
    EvidenceCapture(
        "goodman_lax01_brochure",
        "goodman_lax01_brochure.body",
        "goodman_lax01_brochure.headers",
        "https://us.goodman.com/-/media/project/goodman/north-america/files/property/properties-for-lease/lax01/brochure/goodman-lax01-vernon_brochure_260309.pdf?rev=da0cf2a8b61040fd9b33a2ff902dbd41",
        "2026-07-22T02:37:14Z",
        "application/pdf",
    ),
)


def _read_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GoodmanLax01Error(f"invalid Goodman LAX01 source: {error}") from error
    if not isinstance(value, dict):
        raise GoodmanLax01Error("Goodman LAX01 source root must be an object")
    return value


def _validate_source(path: Path, *, mode: int) -> dict[str, Any]:
    _pin(path, SOURCE_PIN)
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        raise GoodmanLax01Error("Goodman LAX01 source mode differs")
    document = _read_document(path)
    if document.get("schema_version") != "1.0":
        raise GoodmanLax01Error("Goodman LAX01 source schema differs")
    if set(document) != {
        "schema_version",
        "evidence",
        "campus",
        "project",
        "lifecycle",
        "operating_models",
        "workloads",
        "capacities",
    }:
        raise GoodmanLax01Error("Goodman LAX01 source top-level shape differs")
    evidence = document["evidence"]
    if [row.get("key") for row in evidence] != list(EVIDENCE_KEYS):
        raise GoodmanLax01Error("Goodman LAX01 evidence contract differs")
    expected_evidence = {
        DATABANK_EVIDENCE: (
            "DataBank",
            "2026-04-07T13:00:09Z",
            CAPTURE_FILE_PINS["databank_lax01_press.body"][1],
            "databank_lax01_press.headers",
            "databank_lax01_press",
        ),
        BROCHURE_EVIDENCE: (
            "Goodman Group",
            None,
            CAPTURE_FILE_PINS["goodman_lax01_brochure.body"][1],
            "goodman_lax01_brochure.headers",
            "goodman_lax01_brochure",
        ),
    }
    for row in evidence:
        publisher, published, body_hash, header_name, request_id = expected_evidence[
            row["key"]
        ]
        metadata = row.get("metadata", {})
        if (
            row.get("publisher") != publisher
            or row.get("published_at") != published
            or row.get("retrieved_at") != RETRIEVED_AT
            or row.get("license") != "all-rights-reserved"
            or row.get("content_hash") != body_hash
            or metadata.get("capture_artifact_id") != ARTIFACT_ID
            or metadata.get("capture_request_id") != request_id
            or metadata.get("capture_headers_sha256")
            != CAPTURE_FILE_PINS[header_name][1]
            or metadata.get("request_credentials_supplied") is not False
            or metadata.get("http_status") != 200
        ):
            raise GoodmanLax01Error(f"Goodman LAX01 evidence differs: {row['key']}")
    databank_metadata = evidence[0]["metadata"]
    brochure_metadata = evidence[1]["metadata"]
    if (
        databank_metadata.get("future_operator_guardrail")
        != "DataBank says it will operate the Vernon site. This is a future role and is not normalized before opening or independently observed operation."
        or brochure_metadata.get("critical_it_capacity_as_reported_mw") != 32
        or brochure_metadata.get("secured_power_as_reported_mw") != 49.5
        or brochure_metadata.get("pue_assumption_as_reported") != 1.5
        or brochure_metadata.get("http_last_modified_at")
        != "2026-03-17T19:28:02Z"
    ):
        raise GoodmanLax01Error("Goodman LAX01 evidence guardrails differ")
    campus = document["campus"]
    project = document["project"]
    if campus.get("stable_key") != CAMPUS_KEY or project.get("stable_key") != PROJECT_KEY:
        raise GoodmanLax01Error("Goodman LAX01 stable keys differ")
    if campus.get("roles") != {"owner": ["Goodman DataBank JV"]} or project.get(
        "roles"
    ) != {}:
        raise GoodmanLax01Error("Goodman LAX01 standardized roles differ")
    if any(entity.get("address") != EXACT_ADDRESS for entity in (campus, project)):
        raise GoodmanLax01Error("Goodman LAX01 exact address differs")
    if any(
        entity.get(field) is not None
        for entity in (campus, project)
        for field in ("coordinates", "geometry")
    ):
        raise GoodmanLax01Error("Goodman LAX01 source invented coordinates or geometry")
    if document["lifecycle"] != []:
        raise GoodmanLax01Error("Goodman LAX01 lifecycle contract differs")
    if document["operating_models"] != []:
        raise GoodmanLax01Error("Goodman LAX01 operating-model contract differs")
    if document["workloads"] != []:
        raise GoodmanLax01Error("Goodman LAX01 workload contract differs")
    capacities = document["capacities"]
    if [
        (
            row["entity"],
            row["metric"],
            row["stage"],
            row["low"],
            row["base"],
            row["high"],
            row["target_date"],
        )
        for row in capacities
    ] != [
        ("project", "critical_it_mw", "planned", 32, 32, 32, None),
    ]:
        raise GoodmanLax01Error("Goodman LAX01 capacity contract differs")
    capacity = capacities[0]
    if (
        capacity.get("evidence_key") != BROCHURE_EVIDENCE
        or capacity.get("as_of_date") != "2026-03-17"
        or capacity.get("unit") != "MW"
    ):
        raise GoodmanLax01Error("Goodman LAX01 capacity evidence/date differs")
    if {row["metric"] for row in capacities} & {
        "gross_facility_mw",
        "annual_energy_mwh",
        "generation_nameplate_mw",
        "pue",
        "wue_l_per_kwh",
    }:
        raise GoodmanLax01Error("Goodman LAX01 source crossed the energy boundary")
    if any(row.get("stage") in {"operational", "measured"} for row in capacities):
        raise GoodmanLax01Error("Goodman LAX01 source invented current consumption")
    return document


def _validate_author_draft() -> dict[str, Any]:
    return _validate_source(SOURCE, mode=0o644)


def _source_record(
    document: Mapping[str, Any], *, final_ctime_ns: int
) -> dict[str, Any]:
    return {
        "path": f"sources/{SOURCE_FILENAME}",
        "bytes": SOURCE_PIN[0],
        "sha256": SOURCE_PIN[1],
        "final_ctime_ns": final_ctime_ns,
        "schema_version": "1.0",
        "country": document["campus"]["country"],
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PROJECT_KEY,
        "evidence_records": 2,
        "lifecycle_observations": 0,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 1,
        "existing_entities_reused": 2,
        "new_entities_created": 0,
        "entity_snapshots_updated": 2,
        "coordinates_present": 0,
        "geometry_present": 0,
        "seed_eligible": True,
        "seeded": False,
    }


def _require_prior_nonmutation() -> dict[str, Any]:
    size, digest, ctime_ns, mode = PRIOR_PIN
    if PRIOR_SOURCE.is_symlink() or not PRIOR_SOURCE.is_file():
        raise GoodmanLax01Error("prior Goodman LAX01 source is absent")
    metadata = PRIOR_SOURCE.stat(follow_symlinks=False)
    if (
        metadata.st_size != size
        or _sha256(PRIOR_SOURCE) != digest
        or metadata.st_ctime_ns != ctime_ns
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise GoodmanLax01Error("prior Goodman LAX01 source changed")
    definition = json.loads(V93_DEFINITION.read_text())
    witness = [
        row
        for row in definition.get("curated_inputs", [])
        if row.get("path") == f"sources/{PRIOR_SOURCE.name}"
    ]
    if witness != [{"path": f"sources/{PRIOR_SOURCE.name}", "sha256": digest}]:
        raise GoodmanLax01Error("v93 prior Goodman LAX01 input witness changed")
    return {
        "path": f"sources/{PRIOR_SOURCE.name}",
        "bytes": size,
        "sha256": digest,
        "ctime_ns": ctime_ns,
        "mode": f"{mode:04o}",
        "v93_lifecycle": "mep_electrical",
        "v93_lifecycle_as_of_date": "2026-03-31",
        "mutated": False,
        "preserved_by_enrichment_replay": True,
    }


def _planned_keys(document: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    stable = {document[name]["stable_key"] for name in ("campus", "project")}
    evidence = {row["key"] for row in document["evidence"]}
    return stable, evidence


def _collision_witness(document: Mapping[str, Any]) -> dict[str, Any]:
    for path, pin in V93_PINS.items():
        _pin(path, pin)
    if tree_digest(V93_RELEASE) != V93_TREE_SHA256:
        raise GoodmanLax01Error("v93 release tree differs")
    definition = json.loads(V93_DEFINITION.read_text())
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V93_INPUT_COUNT:
        raise GoodmanLax01Error("v93 selected input inventory differs")
    with V93_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != V93_ENTITY_COUNT:
        raise GoodmanLax01Error("v93 entity inventory differs")
    planned_stable, planned_evidence = _planned_keys(document)
    base_stable = {row["stable_key"] for row in entity_rows}
    if planned_stable & base_stable != planned_stable:
        raise GoodmanLax01Error("Goodman LAX01 expected v93 identity reuse differs")
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in {
            SOURCE_FILENAME,
            PRIOR_SOURCE.name,
            "curated-official-2026-07-20-goodman-lax01-los-angeles.json",
        }:
            continue
        try:
            other = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(other, dict):
            continue
        stable = {
            row.get("stable_key")
            for key in ("campus", "facility", "building", "project")
            if isinstance((row := other.get(key)), dict)
        }
        evidence = {
            row.get("key")
            for row in other.get("evidence", [])
            if isinstance(row, dict)
        }
        if planned_evidence & evidence or planned_stable & stable:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise GoodmanLax01Error(f"Goodman LAX01 source collision: {collisions!r}")
    return {
        "v93_selected_input_count": len(selected),
        "v93_entity_count": len(entity_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "expected_v93_stable_key_reuse": sorted(planned_stable),
        "unexpected_v93_stable_key_collisions": [],
        "unexpected_v93_evidence_key_collisions": [],
        "unexpected_source_collisions": {},
        "prior_lax01_nonmutation": _require_prior_nonmutation(),
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
                "candidate_id": "goodman-databank-lax01-vernon-enrichment",
                "decision": "seed_eligible_existing_identity_enrichment",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "new_entities": 0,
                "updated_entity_snapshots": 2,
                "address": EXACT_ADDRESS,
                "lifecycle_observations": 0,
                "preserved_prior_lifecycle": {
                    "value": "mep_electrical",
                    "as_of_date": "2026-03-31",
                },
                "capacities": [
                    {
                        "entity": "project",
                        "metric": "critical_it_mw",
                        "stage": "planned",
                        "base": 32,
                        "as_of_date": "2026-03-17",
                    },
                ],
                "forbidden_normalized_claims": {
                    "total_power_mw_49_5": True,
                    "pue_1_5": True,
                    "phase_mw_6_and_26": True,
                    "coordinates_or_geometry": True,
                    "future_databank_operator_role": True,
                },
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
        "successful_evidence_body_captures": 2,
        "successful_context_body_captures": 1,
        "failed_header_only_captures": 2,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "evidence_captures": [
            {
                "capture_id": capture.capture_id,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "retrieved_at": RETRIEVED_AT,
                "response_http_date": capture.response_http_date,
                "http_status": 200,
                "content_type": capture.content_type,
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
            for capture in EVIDENCE_CAPTURES
        ],
        "non_evidence_captures": [
            {
                "capture_id": "databank_lax01_initial_same_canonical_page",
                "retrieved_at": "2026-07-22T02:37:14Z",
                "http_status": 200,
                "normalization_use": "none_later_capture_selected",
                "body": {
                    "path": "databank_lax01_2026.body",
                    "bytes": CAPTURE_FILE_PINS["databank_lax01_2026.body"][0],
                    "sha256": CAPTURE_FILE_PINS["databank_lax01_2026.body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "path": "databank_lax01_2026.headers",
                    "bytes": CAPTURE_FILE_PINS["databank_lax01_2026.headers"][0],
                    "sha256": CAPTURE_FILE_PINS["databank_lax01_2026.headers"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
            },
            {
                "capture_id": "goodman_ce_lax01_cloudflare_challenge",
                "retrieved_at": "2026-07-22T02:37:15Z",
                "http_status": 403,
                "body_captured": False,
                "normalization_use": "none",
                "headers": {
                    "path": "goodman_ce_lax01_2026.headers",
                    "bytes": CAPTURE_FILE_PINS["goodman_ce_lax01_2026.headers"][0],
                    "sha256": CAPTURE_FILE_PINS["goodman_ce_lax01_2026.headers"][1],
                    "contains_response_cookie_not_redistributed": True,
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
            },
            {
                "capture_id": "goodman_lax01_topping_out_cloudflare_challenge",
                "retrieved_at": LATEST_FAILED_CAPTURE_AT,
                "http_status": 403,
                "body_captured": False,
                "normalization_use": "none",
                "headers": {
                    "path": "goodman_lax01_topping_out.headers",
                    "bytes": CAPTURE_FILE_PINS["goodman_lax01_topping_out.headers"][0],
                    "sha256": CAPTURE_FILE_PINS["goodman_lax01_topping_out.headers"][1],
                    "contains_response_cookie_not_redistributed": True,
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
            },
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(_canonical(list(rows)))


def _artifact_documents(
    recorded_at: str,
    document: Mapping[str, Any],
    *,
    source_final_ctime_ns: int,
) -> dict[str, bytes]:
    collision = _collision_witness(document)
    source_record = _source_record(
        document, final_ctime_ns=source_final_ctime_ns
    )
    readme = f"""# Goodman/DataBank LAX01 official enrichment

This immutable source artifact joins DataBank's April 7, 2026 disclosure to Goodman's LAX01 property brochure. It reuses the two stable identities already selected through the frozen v93 base and resolves both source snapshots to `3094 E Vernon Avenue, Vernon, California 90058, United States`. It creates no new campus, project, site, building, or facility identity.

The source adds exactly two evidence records and one planned project `critical_it_mw` observation of 32 MW dated 2026-03-17, the brochure's HTTP Last-Modified date. It adds no lifecycle row; the earlier source's project-level `mep_electrical` observation dated 2026-03-31 remains unchanged. It adds no operating model, workload, coordinate, geometry, current load, consumption, annual energy, generation, PUE, WUE, or current-status persistence.

The brochure's 49.5 MW secured-power statement remains untyped metadata. Its 1.5 PUE is a marketing calculation assumption. The 6 MW and 26 MW delivery components are nested forecasts and create no capacity, lifecycle, energization, target-date, commissioning, or operation row. DataBank's future operator language remains metadata and creates no operator role. Publisher imagery, maps, satellite imagery, aerial imagery, computer vision, and analyst geolocation add no claim.

The parent-authored source first existed at its destination as an exact {SOURCE_PIN[0]}-byte draft with SHA-256 `{SOURCE_PIN[1]}`. Governance changes no semantic or source bytes. It withdraws that inode into hidden staging before the barrier, freezes it at or after {recorded_at}, then no-replace promotes the identical inode back. The artifact pins the governed source's final ctime `{source_final_ctime_ns}` and hash. Rollback restores the original path on any failed pre-barrier or promotion step.

All eight private raw files are individually pinned, including both 403 header-only captures. Response bodies, raw headers, cookies, PDF bytes, and publisher media are not redistributed. The intact raw directory moves to recoverable Trash only after successful live validation. No open-seed or downstream integration is performed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 1,
            "source_records": 1,
            "seed_eligible_candidates": 1,
            "review_only_candidates": 0,
            "distinct_campuses": 1,
            "projects": 1,
            "existing_entities_reused": 2,
            "new_entities_created": 0,
            "updated_entity_snapshots": 2,
            "unique_evidence_records": 2,
            "lifecycle_observations_added": 0,
            "capacity_estimates_added": 1,
            "operating_model_observations_added": 0,
            "workload_observations_added": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "capacity_boundary": {
            "normalized": [
                {
                    "entity": PROJECT_KEY,
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "base": 32,
                    "as_of_date": "2026-03-17",
                },
            ],
            "secured_power_49_5_mw_rows": 0,
            "nested_phase_6_mw_rows": 0,
            "nested_phase_26_mw_rows": 0,
            "current_consumption_or_draw_rows": 0,
            "energized_capacity_rows": 0,
            "gross_facility_rows": 0,
            "generation_rows": 0,
            "annual_energy_rows": 0,
            "pue_rows": 0,
            "wue_rows": 0,
            "future_operator_role_rows": 0,
        },
        "frozen_v93_identity_lineage": {
            "release_tree_sha256": V93_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v93_mutated": False,
            "release_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "coverage_integration": "none",
            "review_integration": "none",
        },
        "publication_contract": {
            "version": 3,
            "source_existed_as_parent_authored_draft_before_governance": True,
            "source_withdrawn_to_hidden_stage_before_barrier": True,
            "artifact_final_absent_before_barrier": True,
            "governed_source_final_absent_at_barrier": True,
            "all_final_member_ctimes_at_or_after_recorded_at": True,
            "all_staged_birthtimes_and_mtimes_at_or_before_recorded_at": True,
            "artifact_root_ctime_at_or_after_recorded_at": True,
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
            "Compact factual extraction from all-rights-reserved DataBank and "
            "Goodman company disclosures. No redistribution license is relied on."
        ),
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "cookies_or_http_state_retained_in_artifact": False,
        "raw_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "raw_capture_file_count": CAPTURE_FILE_COUNT,
        "raw_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "raw_capture_original_path": str(CAPTURE_ORIGIN),
        "raw_capture_recoverable_trash_path": str(CAPTURE_TRASH),
        "deletion_performed": False,
        "failed_403_header_captures_inventoried": 2,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise GoodmanLax01Error("Goodman LAX01 capture directory is absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise GoodmanLax01Error("Goodman LAX01 capture closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise GoodmanLax01Error("Goodman LAX01 capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="goodman-databank-lax01-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        prior_result = adapter.import_file(
            connection, PRIOR_SOURCE, recorded_at=PRIOR_RETRIEVED_AT
        )
        first_result = adapter.import_file(
            connection, path, recorded_at=RETRIEVED_AT
        )
        second_result = adapter.import_file(
            connection, path, recorded_at=RETRIEVED_AT
        )
        if (
            prior_result.entities_created != 2
            or prior_result.evidence_created != 1
            or first_result.entities_created != 0
            or first_result.evidence_created != 2
            or second_result.entities_created != 0
            or second_result.evidence_created != 0
            or prior_result.warnings
            or first_result.warnings
            or second_result.warnings
        ):
            raise GoodmanLax01Error("Goodman LAX01 import delta differs")
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
            "entity_snapshots": 4,
            "evidence": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise GoodmanLax01Error(f"offline import counts differ: {counts!r}")
        current_snapshots = [
            dict(row)
            for row in connection.execute(
                """
                SELECT e.stable_key, s.as_of_date, s.tags_json
                FROM entity_snapshots AS s
                JOIN entities AS e ON e.id = s.entity_id
                WHERE s.as_of_date = '2026-04-07'
                ORDER BY e.stable_key
                """
            )
        ]
        if [row["stable_key"] for row in current_snapshots] != sorted(
            [CAMPUS_KEY, PROJECT_KEY]
        ) or any(
            json.loads(row["tags_json"]).get("address") != EXACT_ADDRESS
            for row in current_snapshots
        ):
            raise GoodmanLax01Error("Goodman LAX01 address snapshot replay differs")
        lifecycle = [
            tuple(row)
            for row in connection.execute(
                """
                SELECT e.stable_key, l.status, l.as_of_date
                FROM lifecycle_observations AS l
                JOIN entities AS e ON e.id = l.entity_id
                """
            )
        ]
        if lifecycle != [(PROJECT_KEY, "mep_electrical", "2026-03-31")]:
            raise GoodmanLax01Error("Goodman LAX01 prior lifecycle was not preserved")
        capacities = [
            tuple(row)
            for row in connection.execute(
                """
                SELECT e.stable_key, c.metric, c.stage, c.base, c.as_of_date
                FROM capacity_estimates AS c
                JOIN entities AS e ON e.id = c.entity_id
                """
            )
        ]
        if capacities != [
            (PROJECT_KEY, "critical_it_mw", "planned", 32.0, "2026-03-17")
        ]:
            raise GoodmanLax01Error("Goodman LAX01 replayed capacity differs")
        counts.update(
            {
                "new_entities_from_enrichment": first_result.entities_created,
                "new_evidence_from_enrichment": first_result.evidence_created,
                "updated_entity_snapshots_from_enrichment": 2,
            }
        )
        return counts


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if birth > threshold + 0.000_001 or metadata.st_mtime > threshold + 0.000_001:
            raise GoodmanLax01Error(f"member birth/mtime post-dates recorded_at: {path}")
        if metadata.st_ctime + 0.000_001 < threshold:
            raise GoodmanLax01Error(f"member ctime predates recorded_at: {path}")


def _assert_stage_precedes(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if birth > threshold + 0.000_001 or metadata.st_mtime > threshold + 0.000_001:
            raise GoodmanLax01Error(
                f"staged member birth/mtime post-dates recorded_at: {path}"
            )


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_path: Path = SOURCE,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    document = _validate_source(source_path, mode=0o444 if require_frozen else 0o600)
    _require_prior_nonmutation()
    if path.is_symlink() or not path.is_dir():
        raise GoodmanLax01Error("Goodman LAX01 artifact must be an ordinary directory")
    if stat.S_IMODE(path.stat().st_mode) != (0o555 if require_frozen else 0o700):
        raise GoodmanLax01Error("Goodman LAX01 artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise GoodmanLax01Error("Goodman LAX01 artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 1
        or manifest.get("candidate_assessments") != 1
        or manifest.get("review_only_candidates") != 0
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise GoodmanLax01Error("Goodman LAX01 manifest contract differs")
    source_pin = manifest.get("governed_source")
    if source_pin != {
        "bytes": SOURCE_PIN[0],
        "final_ctime_ns": source_path.stat(follow_symlinks=False).st_ctime_ns,
        "path": f"sources/{SOURCE_FILENAME}",
        "sha256": SOURCE_PIN[1],
    }:
        raise GoodmanLax01Error("Goodman LAX01 final source manifest pin differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise GoodmanLax01Error(f"manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text() != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise GoodmanLax01Error("Goodman LAX01 manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"],
        document,
        source_final_ctime_ns=source_path.stat(follow_symlinks=False).st_ctime_ns,
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise GoodmanLax01Error(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != [
        _source_record(
            document,
            final_ctime_ns=source_path.stat(follow_symlinks=False).st_ctime_ns,
        )
    ]:
        raise GoodmanLax01Error("Goodman LAX01 source snapshot pin differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise GoodmanLax01Error("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise GoodmanLax01Error("Goodman LAX01 recorded_at is not live")
    if _instant(LATEST_FAILED_CAPTURE_AT) > target:
        raise GoodmanLax01Error("Goodman LAX01 capture post-dates recorded_at")
    replay = [_offline_import(source_path, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise GoodmanLax01Error("Goodman LAX01 offline replay differs")
    if require_frozen:
        _assert_chronology(
            [path, *entries.values(), source_path], manifest["recorded_at"]
        )
    return manifest


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    document: Mapping[str, Any],
    *,
    source_path: Path,
) -> None:
    source_ctime_ns = source_path.stat(follow_symlinks=False).st_ctime_ns
    payloads = _artifact_documents(
        recorded_at, document, source_final_ctime_ns=source_ctime_ns
    )
    for name in CONTENT_FILES:
        member = stage / name
        member.write_bytes(payloads[name])
        member.chmod(0o600)
        _fsync_regular(member)
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
        "governed_source": {
            "bytes": SOURCE_PIN[0],
            "final_ctime_ns": source_ctime_ns,
            "path": f"sources/{SOURCE_FILENAME}",
            "sha256": SOURCE_PIN[1],
        },
        "candidate_assessments": 1,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "review_only_candidates": 0,
        "successful_evidence_body_captures": 2,
        "successful_context_body_captures": 1,
        "failed_header_only_captures": 2,
        "raw_capture_redistributed": False,
        "raw_capture_moved_after_successful_live_validation": True,
        "all_final_member_and_root_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n")
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
        raise GoodmanLax01Error("active Goodman LAX01 publication lock exists") from error
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
                raise GoodmanLax01Error("refusing substituted publication lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _discard_artifact_stage(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir() and not path.is_symlink():
        path.chmod(0o700)
        for member in path.iterdir():
            if member.is_file() and not member.is_symlink():
                member.chmod(0o600)
        shutil.rmtree(path)


def _restore_author_draft(prepared: _Prepared) -> None:
    staged = prepared.source_stage / SOURCE_FILENAME
    if staged.exists():
        staged.chmod(0o644)
        if SOURCE.exists() or SOURCE.is_symlink():
            raise GoodmanLax01Error(
                f"cannot restore authored source over late collision; retained at {staged}"
            )
        _promote_noreplace(staged, SOURCE)
    if prepared.source_stage.exists() and not any(prepared.source_stage.iterdir()):
        prepared.source_stage.rmdir()
    _discard_artifact_stage(prepared.artifact_stage)


def _prepare(recorded_at: str) -> _Prepared:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise GoodmanLax01Error("Goodman LAX01 artifact final-path collision")
    document = _validate_author_draft()
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    _collision_witness(document)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".goodman-databank-lax01-source.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    prepared = _Prepared(source_stage, artifact_stage, recorded_at)
    try:
        staged_source = source_stage / SOURCE_FILENAME
        _promote_noreplace(SOURCE, staged_source)
        staged_source.chmod(0o600)
        _fsync_regular(staged_source)
        _fsync_directory(source_stage)
        document = _validate_source(staged_source, mode=0o600)
        _write_artifact_stage(
            artifact_stage,
            recorded_at,
            document,
            source_path=staged_source,
        )
        _assert_stage_precedes(
            [
                source_stage,
                staged_source,
                artifact_stage,
                *artifact_stage.iterdir(),
            ],
            recorded_at,
        )
        validate_artifact(
            artifact_stage,
            source_path=staged_source,
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        if SOURCE.exists() or SOURCE.is_symlink() or ARTIFACT.exists() or ARTIFACT.is_symlink():
            raise GoodmanLax01Error("final paths were not hidden before barrier")
        return prepared
    except Exception as error:
        try:
            _restore_author_draft(prepared)
        except Exception as restore_error:
            error.add_note(f"Goodman LAX01 draft restoration failed: {restore_error}")
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    source = prepared.source_stage / SOURCE_FILENAME
    source.chmod(0o444)
    _fsync_regular(source)
    _fsync_directory(prepared.source_stage)
    _assert_chronology([source], prepared.recorded_at)


def _finalize_artifact_after_source_promotion(prepared: _Prepared) -> None:
    document = _validate_source(SOURCE, mode=0o444)
    _write_artifact_stage(
        prepared.artifact_stage,
        prepared.recorded_at,
        document,
        source_path=SOURCE,
    )
    target_ns = int(_instant(prepared.recorded_at).timestamp() * 1_000_000_000)
    for member in prepared.artifact_stage.iterdir():
        member.chmod(0o444)
        os.utime(
            member,
            ns=(member.stat(follow_symlinks=False).st_atime_ns, target_ns),
            follow_symlinks=False,
        )
        _fsync_regular(member)
    prepared.artifact_stage.chmod(0o555)
    os.utime(
        prepared.artifact_stage,
        ns=(
            prepared.artifact_stage.stat(follow_symlinks=False).st_atime_ns,
            target_ns,
        ),
        follow_symlinks=False,
    )
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [
            SOURCE,
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
        ],
        prepared.recorded_at,
    )
    validate_artifact(
        prepared.artifact_stage,
        source_path=SOURCE,
        require_live=True,
        require_frozen=True,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if SOURCE.exists() or SOURCE.is_symlink() or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise GoodmanLax01Error("late Goodman LAX01 final-path collision")
    staged_source = prepared.source_stage / SOURCE_FILENAME
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        source_identity = _identity(staged_source, directory=False)
        _promote_noreplace(staged_source, SOURCE)
        if not _has_identity(SOURCE, source_identity, directory=False):
            raise GoodmanLax01Error(f"promoted identity differs: {SOURCE}")
        promoted.append((SOURCE, staged_source, source_identity, False))

        _finalize_artifact_after_source_promotion(prepared)
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise GoodmanLax01Error(f"promoted identity differs: {ARTIFACT}")
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise GoodmanLax01Error(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"Goodman LAX01 rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise GoodmanLax01Error("both raw origin and Trash destination exist")
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
        "logical_tree_sha256": manifest["tree_sha256"],
        "recorded_at": manifest["recorded_at"],
        "source_records": 1,
        "existing_entities_reused": 2,
        "new_entities": 0,
        "updated_entity_snapshots": 2,
        "evidence_records_added": 2,
        "lifecycle_observations_added": 0,
        "capacity_estimates_added": 1,
        "operating_model_observations_added": 0,
        "workload_observations_added": 0,
        "review_only_candidates": 0,
        "source_final_ctime_ns": manifest["governed_source"]["final_ctime_ns"],
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        if not SOURCE.exists() or SOURCE.is_symlink():
            raise GoodmanLax01Error("partial Goodman LAX01 final-path collision")
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if not SOURCE.exists() or SOURCE.is_symlink():
        raise GoodmanLax01Error("partial Goodman LAX01 final-path collision")
    _validate_author_draft()
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise GoodmanLax01Error("Goodman LAX01 recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            _publish(prepared)
        except BaseException as error:
            try:
                _restore_author_draft(prepared)
            except Exception as restore_error:
                error.add_note(f"Goodman LAX01 draft restoration failed: {restore_error}")
            raise
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise GoodmanLax01Error("Goodman LAX01 source stage not empty")
            prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
