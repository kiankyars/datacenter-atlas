"""Publish the governed Hut 8 River Bend current-build source artifact.

The source is a compact factual extraction from three official Hut 8 SEC
filings. Exact raw response bytes are pinned but never redistributed. This
module publishes only the corrected schema-1.1 source and its evidence
artifact; it performs no open-seed or downstream integration.
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

from . import global_official_builds_six_candidate_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
SOURCE_FILENAME = (
    "curated-official-2026-07-22-hut8-river-bend-current-build.json"
)
SOURCE = SOURCES_ROOT / SOURCE_FILENAME
ARTIFACT_ID = "hut8-river-bend-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".hut8-river-bend-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-hut8-riverbend-sec-20260722.7JfzTk")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-hut8-riverbend-sec-20260722.7JfzTk")
CAPTURE_FILE_COUNT = 26
CAPTURE_TOTAL_BYTES = 22_490_094
CAPTURE_TREE_SHA256 = (
    "c9cfdc146403585cfd5af8bad4bdf34bf493458da3574c907a482872fd7bd733"
)
RETRIEVED_AT = "2026-07-22T02:47:02Z"

SOURCE_PIN = (
    16_044,
    "0e5139ef2935accca6e0dafcbde324f5cfb730ff855c526f9b835afe9c7919f4",
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

BEACON_SOURCE = SOURCES_ROOT / (
    "curated-official-2026-07-20-hut8-beacon-point.json"
)
BEACON_PIN = (
    24_978,
    "b6209a4c9ebaefe562b541834c9d89a19482cfd79a4cf7de156df848ed7834f1",
    1_784_534_676_368_725_476,
    0o644,
)

CAMPUS_KEY = "curated:hut8-river-bend-ai-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:245mw-critical-it-current-build"
LEASE_EVIDENCE = "hut8-river-bend-lease-2025-12-17-captured-2026-07-22"
Q1_EVIDENCE = "hut8-river-bend-q1-2026-10q-captured-2026-07-22"
UPDATE_EVIDENCE = (
    "hut8-river-bend-construction-update-2026-05-06-captured-2026-07-22"
)
EVIDENCE_KEYS = (LEASE_EVIDENCE, Q1_EVIDENCE, UPDATE_EVIDENCE)

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


class Hut8RiverBendError(RuntimeError):
    """Raised when a source, semantic, or publication invariant differs."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Hut8RiverBendError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise Hut8RiverBendError(f"pinned ordinary file is absent: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise Hut8RiverBendError(f"pinned file differs: {path}: {actual!r}")


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
    "lease-8k.headers": (613, "55eb834c4b1d84cdb8f2d4dfba204875259241a9b7baf6c842c1eed7931dc2f5"),
    "lease-8k.htm": (42_889, "2ce19271a12aec5aebe3d9cf423a7c1a853ed592ec37f547a4b23d03351fa065"),
    "lease-index.headers": (284, "d44b7e0290b519e24d79fd1df1982ea181191c91718662406a3c98a648cf1698"),
    "lease-index.json": (3_829, "27cf4e0e1d70026f7711e6d6fde85ac5097100ce6ec4d864bb460f5f293859ee"),
    "lease-presentation.headers": (593, "793935bece563d05ab7bbc34394bb265bb48da89a75cb71278e821eb68f5ca7f"),
    "lease-presentation99-2.htm": (36_814, "2e9be8ab07ce26f3abda245947b391886fc5eb40bc82f1deef4c1896725a92a5"),
    "lease-press.headers": (570, "f5db7a91ff7ed157f2dc374248efe2287727c2c02227fa12e32d7da8a0f93e71"),
    "lease-press99-1.htm": (53_237, "27a86eec15d079dc6cf88b1dd97852752d685bb7ca7846c3751a9855473d1e4e"),
    "lease-submission.headers": (618, "7929a33660333e3032a1b85d08e60ddd02c4f8ce08fde63c42e7b2473329bf49"),
    "lease-submission.txt": (3_583_868, "90f90793f8234850a4dcd784f980b090c1e196f540a26ba9ea1676a35a153098"),
    "q1-10q.headers": (590, "251b6a031d23eb6d19bc401f4389c7bc74679f451c0ec4fc169968935b92d5f7"),
    "q1-10q.htm": (2_740_057, "b265afc7d71cbb4021f5024c2366a7c8e41ffc50b34e2641664350aa468eb468"),
    "q1-index.headers": (270, "13a1213689020cdb9b63f3a6895bb5415865ae811245b0fef26f3dda4f0e86a2"),
    "q1-index.json": (11_411, "0c99412c515b21bc32291fec59ed7eb322e7189bfba043f4ff69f7c62edd620e"),
    "q1-submission.headers": (638, "46606eef26a528a7c7fd1c2c6905b0a259efc950cb3349f0bae851ec120ce11d"),
    "q1-submission.txt": (15_274_961, "eed3906fe542c41ba23f9597f7d87aeaf16735afb34757794cee41896d702940"),
    "submissions.headers": (447, "679669e068c2c1b2b16355bd3b5897259d5fb85ebe2bce94c20cb3d1a4d2313b"),
    "submissions.json": (40_484, "6e69a1f52f377b5221741227b779e6f28e4ed33d0a771b5124203eb904412a6a"),
    "update-8k.headers": (613, "9524e3d2bfd902a65cdac7fa131dcb4857bee38476e58a8c4bdd47051fe36422"),
    "update-8k.htm": (36_938, "bda0ce4a362d85ba7ed81883882ec430b50bc5254d0c7076377a24971bcc63af"),
    "update-exhibit.headers": (590, "50c0bda9566578b5ebfc3af08c206a010ea0ee344c2a80a12eb090f3cc512616"),
    "update-exhibit99-1.htm": (162_054, "ceab7b5bb38bbc6198b787672cfcc6c69d703e9bbe1094d7d733560eb1a889d4"),
    "update-index.headers": (269, "cfbc40d5c706c8c2cf02457f62b8b4e0571d556ae81edcbc56dd129cf4cdd891"),
    "update-index.json": (2_014, "52057a6c7411633587e2579f2dafca8ca2f1ad788c3573f0c049bd5f5e362d5c"),
    "update-submission.headers": (618, "40bc951510059de9167a718ad5f096f57b87699b60d4ad23305930e9a46600e5"),
    "update-submission.txt": (494_825, "03d65dd18a9bd3ff4084a2e18dd114982d1243b8b3a094ee926ea8727587107d"),
}


@dataclass(frozen=True)
class EvidenceCapture:
    capture_id: str
    body_name: str
    header_name: str
    accession: str
    form: str
    filed_date: str
    acceptance_datetime_raw: str
    url: str


EVIDENCE_CAPTURES = (
    EvidenceCapture(
        "river_bend_lease_press_exhibit",
        "lease-press99-1.htm",
        "lease-press.headers",
        "0001104659-25-122052",
        "8-K",
        "2025-12-17",
        "20251217161522",
        "https://www.sec.gov/Archives/edgar/data/1964789/000110465925122052/hut-20251217xex99d1.htm",
    ),
    EvidenceCapture(
        "river_bend_q1_2026_10q",
        "q1-10q.htm",
        "q1-10q.headers",
        "0001104659-26-055891",
        "10-Q",
        "2026-05-06",
        "20260506064551",
        "https://www.sec.gov/Archives/edgar/data/1964789/000110465926055891/hut-20260331x10q.htm",
    ),
    EvidenceCapture(
        "river_bend_q1_results_exhibit",
        "update-exhibit99-1.htm",
        "update-exhibit.headers",
        "0001104659-26-055894",
        "8-K",
        "2026-05-06",
        "20260506065009",
        "https://www.sec.gov/Archives/edgar/data/1964789/000110465926055894/hut-20260506xex99d1.htm",
    ),
)


def _read_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Hut8RiverBendError(f"invalid River Bend source: {error}") from error
    if not isinstance(value, dict):
        raise Hut8RiverBendError("River Bend source root must be an object")
    return value


def _validate_source(path: Path, *, mode: int) -> dict[str, Any]:
    _pin(path, SOURCE_PIN)
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        raise Hut8RiverBendError("River Bend source mode differs")
    document = _read_document(path)
    if document.get("schema_version") != "1.1":
        raise Hut8RiverBendError("River Bend source must use strict schema 1.1")
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
        raise Hut8RiverBendError("River Bend source top-level shape differs")
    evidence = document["evidence"]
    if [row.get("key") for row in evidence] != list(EVIDENCE_KEYS):
        raise Hut8RiverBendError("River Bend evidence contract differs")
    expected_evidence = {
        LEASE_EVIDENCE: (
            "2025-12-17",
            "27a86eec15d079dc6cf88b1dd97852752d685bb7ca7846c3751a9855473d1e4e",
            "lease-press.headers",
            "river_bend_lease_press_exhibit",
        ),
        Q1_EVIDENCE: (
            "2026-05-06",
            "b265afc7d71cbb4021f5024c2366a7c8e41ffc50b34e2641664350aa468eb468",
            "q1-10q.headers",
            "river_bend_q1_2026_10q",
        ),
        UPDATE_EVIDENCE: (
            "2026-05-06",
            "ceab7b5bb38bbc6198b787672cfcc6c69d703e9bbe1094d7d733560eb1a889d4",
            "update-exhibit.headers",
            "river_bend_q1_results_exhibit",
        ),
    }
    for row in evidence:
        published, body_hash, header_name, request_id = expected_evidence[row["key"]]
        metadata = row.get("metadata", {})
        if (
            row.get("publisher") != "Hut 8 Corp."
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
            raise Hut8RiverBendError(f"River Bend evidence differs: {row['key']}")
    campus = document["campus"]
    project = document["project"]
    if campus.get("stable_key") != CAMPUS_KEY or project.get("stable_key") != PROJECT_KEY:
        raise Hut8RiverBendError("River Bend stable keys differ")
    if campus.get("roles") != {
        "developer": ["Hut 8"],
        "utility": ["Entergy Louisiana"],
    } or project.get("roles") != {
        "developer": ["Hut 8"],
        "tenant": ["Fluidstack"],
    }:
        raise Hut8RiverBendError("River Bend standardized roles differ")
    if any(
        entity.get(field) is not None
        for entity in (campus, project)
        for field in ("coordinates", "geometry")
    ):
        raise Hut8RiverBendError("River Bend source invented coordinates or geometry")
    if document["lifecycle"] != [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": UPDATE_EVIDENCE,
            "as_of_date": "2026-05-06",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]:
        raise Hut8RiverBendError("River Bend lifecycle contract differs")
    if [
        (row["entity"], row["value"], row["as_of_date"], row["evidence_key"])
        for row in document["operating_models"]
    ] != [("project", "hyperscale_lease", "2025-12-17", LEASE_EVIDENCE)]:
        raise Hut8RiverBendError("River Bend operating-model contract differs")
    if [
        (row["entity"], row["value"], row["as_of_date"], row["evidence_key"])
        for row in document["workloads"]
    ] != [
        ("project", "ai_specialized_unspecified", "2025-12-17", LEASE_EVIDENCE)
    ]:
        raise Hut8RiverBendError("River Bend workload contract differs")
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
        ("project", "critical_it_mw", "contracted", 245, 245, 245, None),
        ("campus", "grid_connection_mw", "contracted", 330, 330, 330, None),
    ]:
        raise Hut8RiverBendError("River Bend capacity contract differs")
    if {row["metric"] for row in capacities} & {
        "gross_facility_mw",
        "annual_energy_mwh",
        "generation_nameplate_mw",
        "pue",
        "wue_l_per_kwh",
    }:
        raise Hut8RiverBendError("River Bend source crossed the energy boundary")
    if any(row.get("stage") in {"operational", "measured"} for row in capacities):
        raise Hut8RiverBendError("River Bend source invented current consumption")
    return document


def _validate_author_draft() -> dict[str, Any]:
    return _validate_source(SOURCE, mode=0o644)


def _source_record(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": f"sources/{SOURCE_FILENAME}",
        "bytes": SOURCE_PIN[0],
        "sha256": SOURCE_PIN[1],
        "schema_version": "1.1",
        "schema_correction": {
            "from": "1.0",
            "to": "1.1",
            "reason": (
                "The source retains per-evidence retrieval timestamps; the strict "
                "schema-1.1 adapter permits them when none post-dates recorded_at."
            ),
        },
        "country": document["campus"]["country"],
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PROJECT_KEY,
        "evidence_records": 3,
        "lifecycle_observations": 1,
        "operating_model_observations": 1,
        "workload_observations": 1,
        "capacity_estimates": 2,
        "coordinates_present": 0,
        "geometry_present": 0,
        "seed_eligible": True,
        "seeded": False,
    }


def _require_beacon_nonmutation() -> dict[str, Any]:
    size, digest, ctime_ns, mode = BEACON_PIN
    if BEACON_SOURCE.is_symlink() or not BEACON_SOURCE.is_file():
        raise Hut8RiverBendError("frozen Beacon Point source is absent")
    metadata = BEACON_SOURCE.stat(follow_symlinks=False)
    if (
        metadata.st_size != size
        or _sha256(BEACON_SOURCE) != digest
        or metadata.st_ctime_ns != ctime_ns
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise Hut8RiverBendError("frozen Beacon Point source changed")
    definition = json.loads(V92_DEFINITION.read_text())
    witness = [
        row
        for row in definition.get("curated_inputs", [])
        if row.get("path") == f"sources/{BEACON_SOURCE.name}"
    ]
    if witness != [{"path": f"sources/{BEACON_SOURCE.name}", "sha256": digest}]:
        raise Hut8RiverBendError("v92 Beacon Point input witness changed")
    return {
        "path": f"sources/{BEACON_SOURCE.name}",
        "bytes": size,
        "sha256": digest,
        "ctime_ns": ctime_ns,
        "mode": f"{mode:04o}",
        "v92_lifecycle": "announced",
        "mutated": False,
        "new_physical_observation_added": False,
        "new_capacity_added": False,
    }


def _planned_keys(document: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    stable = {document[name]["stable_key"] for name in ("campus", "project")}
    evidence = {row["key"] for row in document["evidence"]}
    return stable, evidence


def _collision_witness(document: Mapping[str, Any]) -> dict[str, Any]:
    for path, pin in V92_PINS.items():
        _pin(path, pin)
    if tree_digest(V92_RELEASE) != V92_TREE_SHA256:
        raise Hut8RiverBendError("v92 release tree differs")
    definition = json.loads(V92_DEFINITION.read_text())
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V92_INPUT_COUNT:
        raise Hut8RiverBendError("v92 selected input inventory differs")
    with V92_ENTITIES.open(encoding="utf-8", newline="") as stream:
        entity_rows = list(csv.DictReader(stream))
    if len(entity_rows) != V92_ENTITY_COUNT:
        raise Hut8RiverBendError("v92 entity inventory differs")
    planned_stable, planned_evidence = _planned_keys(document)
    base_stable = {row["stable_key"] for row in entity_rows}
    if planned_stable & base_stable:
        raise Hut8RiverBendError("River Bend stable key collides with v92")
    source_inputs = json.loads(V92_SOURCE_INPUTS.read_text())
    base_evidence = {
        key
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise Hut8RiverBendError("River Bend evidence key collides with v92")
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in {SOURCE_FILENAME, BEACON_SOURCE.name}:
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
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise Hut8RiverBendError(f"River Bend source collision: {collisions!r}")
    return {
        "v92_selected_input_count": len(selected),
        "v92_entity_count": len(entity_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v92_stable_key_collisions": [],
        "exact_v92_evidence_key_collisions": [],
        "unexpected_source_collisions": {},
        "beacon_point_nonmutation": _require_beacon_nonmutation(),
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
                "candidate_id": "hut8-river-bend-current-build",
                "decision": "seed_eligible_direct_authoritative_physical_update",
                "source_paths": [f"sources/{SOURCE_FILENAME}"],
                "campus_stable_key": CAMPUS_KEY,
                "project_stable_key": PROJECT_KEY,
                "lifecycle": "under_construction",
                "as_of_date": "2026-05-06",
                "capacities": [
                    {
                        "entity": "project",
                        "metric": "critical_it_mw",
                        "stage": "contracted",
                        "base": 245,
                    },
                    {
                        "entity": "campus",
                        "metric": "grid_connection_mw",
                        "stage": "contracted",
                        "base": 330,
                    },
                ],
                "capacity_nonadditivity": (
                    "245 MW critical IT and 330 MW grid connection are different, "
                    "nested dimensions and are never summed."
                ),
            },
            {
                "candidate_id": "hut8-beacon-point-q1-context",
                "decision": "review_only_existing_announced_record_unchanged",
                "source_paths": [f"sources/{BEACON_SOURCE.name}"],
                "source_language": (
                    "The May release reports substation construction and includes "
                    "Beacon Point in Hut 8's internal Energy Capacity Under "
                    "Construction category."
                ),
                "exclusion": (
                    "Neither statement directly establishes data-center footprint "
                    "construction. The existing announced record remains unchanged."
                ),
                "excluded_capacity_context_mw": [352, 500, 1000],
                "normalized_entity": None,
                "normalized_lifecycle": None,
                "normalized_capacity": None,
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
        "successful_evidence_body_captures": 3,
        "failed_evidence_body_captures": 0,
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
                "accession": capture.accession,
                "form": capture.form,
                "filed_date": capture.filed_date,
                "acceptance_datetime_raw": capture.acceptance_datetime_raw,
                "requested_url": capture.url,
                "effective_url": capture.url,
                "retrieved_at": RETRIEVED_AT,
                "http_status": 200,
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
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(_canonical(list(rows)))


def _artifact_documents(
    recorded_at: str, document: Mapping[str, Any]
) -> dict[str, bytes]:
    collision = _collision_witness(document)
    source_record = _source_record(document)
    readme = f"""# Hut 8 River Bend current-build source tranche

This immutable source artifact is grounded in three official Hut 8 Corp. SEC records: the December 17, 2025 lease exhibit, the May 6, 2026 Q1 10-Q, and the May 6 Q1 results exhibit. The results exhibit explicitly says Hut 8 continued and advanced construction at the River Bend AI data-center campus. Exactly one project-level under-construction observation is dated 2026-05-06. It is dated evidence, not a persisted assertion of current status.

The executed Fluidstack lease supports 245 MW of contracted project critical IT and a hyperscale-lease operating model. Entergy Louisiana's secured initial utility capacity supports 330 MW of contracted campus grid connection. These are nonadditive dimensions: they are never summed and neither is current draw, measured consumption, energized capacity, gross facility load, generation, or annual energy. The only workload classification is ai_specialized_unspecified. The future 1,000 MW ROFO and utility expansion, 2027 delivery forecasts, and presentation-only 1.35 PUE are excluded.

Standardized roles are limited to Hut 8 as developer, Fluidstack as tenant, and Entergy Louisiana as utility. Google's financial backstop remains metadata only. No owner, operator, user, customer, contractor, investor, coordinates, geometry, PUE, WUE, annual energy, current load, imagery, satellite, aerial, map-click, or computer-vision claim is added.

Beacon Point remains review-only context. Substation construction and Hut 8's internal Energy Capacity Under Construction category do not establish physical data-center footprint construction. Its existing v92 announced record is exact-pinned and untouched; no 352, 500, or 1,000 MW Beacon Point value is imported here.

The parent-authored source first existed at its destination as a draft. Governance corrected only its schema declaration from 1.0 to 1.1, then withdrew the exact audited bytes into hidden staging before the recorded-at barrier. The artifact path and governed source publication path were absent at the barrier; both were promoted without replacement only after {recorded_at}. Raw all-rights-reserved bodies, headers, indexes, submissions, presentation material, and possible HTTP state are not redistributed. The intact 26-file raw directory moves to recoverable Trash only after successful live validation. No open-seed or downstream integration is performed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 2,
            "source_records": 1,
            "seed_eligible_candidates": 1,
            "review_only_candidates": 1,
            "distinct_campuses": 1,
            "projects": 1,
            "distinct_entities": 2,
            "unique_imported_entity_snapshots": 2,
            "unique_evidence_records": 3,
            "lifecycle_observations": 1,
            "capacity_estimates": 2,
            "operating_model_observations": 1,
            "workload_observations": 1,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "capacity_boundary": {
            "normalized": [
                {
                    "entity": PROJECT_KEY,
                    "metric": "critical_it_mw",
                    "stage": "contracted",
                    "base": 245,
                },
                {
                    "entity": CAMPUS_KEY,
                    "metric": "grid_connection_mw",
                    "stage": "contracted",
                    "base": 330,
                },
            ],
            "nonadditive": True,
            "forbidden_arithmetic_sum_mw": 575,
            "current_consumption_or_draw_rows": 0,
            "energized_capacity_rows": 0,
            "gross_facility_rows": 0,
            "generation_rows": 0,
            "annual_energy_rows": 0,
            "pue_rows": 0,
            "wue_rows": 0,
            "future_expansion_rows": 0,
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
            "version": 3,
            "source_existed_as_parent_authored_draft_before_governance": True,
            "source_withdrawn_to_hidden_stage_before_barrier": True,
            "artifact_final_absent_before_barrier": True,
            "governed_source_final_absent_at_barrier": True,
            "all_final_member_ctimes_at_or_after_recorded_at": True,
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
            "Compact factual extraction from all-rights-reserved Hut 8 issuer "
            "filings hosted by SEC EDGAR. No redistribution license is relied on."
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
        raise Hut8RiverBendError("River Bend capture directory is absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise Hut8RiverBendError("River Bend capture closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise Hut8RiverBendError("River Bend capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="hut8-river-bend-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            adapter.import_file(connection, path, recorded_at=recorded_at)
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
            "workload_observations": 1,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise Hut8RiverBendError(f"offline import counts differ: {counts!r}")
        return counts


def _assert_chronology(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise Hut8RiverBendError(f"member ctime predates recorded_at: {path}")


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_path: Path = SOURCE,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    document = _validate_source(source_path, mode=0o444 if require_frozen else 0o600)
    _require_beacon_nonmutation()
    if path.is_symlink() or not path.is_dir():
        raise Hut8RiverBendError("River Bend artifact must be an ordinary directory")
    if stat.S_IMODE(path.stat().st_mode) != (0o555 if require_frozen else 0o700):
        raise Hut8RiverBendError("River Bend artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise Hut8RiverBendError("River Bend artifact member contract differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("curated_source_records") != 1
        or manifest.get("candidate_assessments") != 2
        or manifest.get("review_only_candidates") != 1
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise Hut8RiverBendError("River Bend manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise Hut8RiverBendError(f"manifest pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text() != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise Hut8RiverBendError("River Bend manifest checksum differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], document)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise Hut8RiverBendError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != [_source_record(document)]:
        raise Hut8RiverBendError("River Bend source snapshot pin differs")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise Hut8RiverBendError("wall clock must be timezone aware")
    if require_live and now.astimezone(UTC) < target:
        raise Hut8RiverBendError("River Bend recorded_at is not live")
    if _instant(RETRIEVED_AT) > target:
        raise Hut8RiverBendError("River Bend capture post-dates recorded_at")
    replay = [_offline_import(source_path, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise Hut8RiverBendError("River Bend offline replay differs")
    if require_frozen:
        _assert_chronology(
            [path, *entries.values(), source_path], manifest["recorded_at"]
        )
    return manifest


def _write_artifact_stage(
    stage: Path, recorded_at: str, document: Mapping[str, Any]
) -> None:
    payloads = _artifact_documents(recorded_at, document)
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
        "candidate_assessments": 2,
        "curated_source_records": 1,
        "seed_eligible_candidates": 1,
        "review_only_candidates": 1,
        "successful_evidence_body_captures": 3,
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
        raise Hut8RiverBendError("active River Bend publication lock exists") from error
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
                raise Hut8RiverBendError("refusing substituted publication lock cleanup")
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
            raise Hut8RiverBendError(
                f"cannot restore authored source over late collision; retained at {staged}"
            )
        _promote_noreplace(staged, SOURCE)
    if prepared.source_stage.exists() and not any(prepared.source_stage.iterdir()):
        prepared.source_stage.rmdir()
    _discard_artifact_stage(prepared.artifact_stage)


def _prepare(recorded_at: str) -> _Prepared:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise Hut8RiverBendError("River Bend artifact final-path collision")
    document = _validate_author_draft()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    _collision_witness(document)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".hut8-river-bend-source.", dir=SOURCES_ROOT)
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
        _write_artifact_stage(artifact_stage, recorded_at, document)
        validate_artifact(
            artifact_stage,
            source_path=staged_source,
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        if SOURCE.exists() or SOURCE.is_symlink() or ARTIFACT.exists() or ARTIFACT.is_symlink():
            raise Hut8RiverBendError("final paths were not hidden before barrier")
        return prepared
    except Exception as error:
        try:
            _restore_author_draft(prepared)
        except Exception as restore_error:
            error.add_note(f"River Bend draft restoration failed: {restore_error}")
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    source = prepared.source_stage / SOURCE_FILENAME
    source.chmod(0o444)
    _fsync_regular(source)
    for member in prepared.artifact_stage.iterdir():
        member.chmod(0o444)
        _fsync_regular(member)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_chronology(
        [source, prepared.artifact_stage, *prepared.artifact_stage.iterdir()],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if SOURCE.exists() or SOURCE.is_symlink() or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise Hut8RiverBendError("late River Bend final-path collision")
    staged_source = prepared.source_stage / SOURCE_FILENAME
    operations = (
        (staged_source, SOURCE, False),
        (prepared.artifact_stage, ARTIFACT, True),
    )
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for staged, final, directory in operations:
            identity = _identity(staged, directory=directory)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=directory):
                raise Hut8RiverBendError(f"promoted identity differs: {final}")
            promoted.append((final, staged, identity, directory))
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise Hut8RiverBendError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"River Bend rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise Hut8RiverBendError("both raw origin and Trash destination exist")
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
        "logical_tree_sha256": manifest["tree_sha256"],
        "recorded_at": manifest["recorded_at"],
        "source_records": 1,
        "unique_entities": 2,
        "evidence_records": 3,
        "lifecycle_observations": 1,
        "capacity_estimates": 2,
        "operating_model_observations": 1,
        "workload_observations": 1,
        "review_only_candidates": 1,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        if not SOURCE.exists() or SOURCE.is_symlink():
            raise Hut8RiverBendError("partial River Bend final-path collision")
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if not SOURCE.exists() or SOURCE.is_symlink():
        raise Hut8RiverBendError("partial River Bend final-path collision")
    _validate_author_draft()
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise Hut8RiverBendError("River Bend recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            _publish(prepared)
        except BaseException as error:
            try:
                _restore_author_draft(prepared)
            except Exception as restore_error:
                error.add_note(f"River Bend draft restoration failed: {restore_error}")
            raise
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise Hut8RiverBendError("River Bend source stage not empty")
            prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
