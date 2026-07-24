"""Build open seed v85 as the strict coordinate-only successor to v84."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import copy
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v84 as v84
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import _current_rows, summarize


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v84.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v84"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v85.json"
RELEASE_ID = "2026-07-21-open-seed-v85"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v85.lock"
AS_OF = "2026-07-21"

BASE_RECORDED_AT = "2026-07-21T19:10:20Z"
BASE_DEFINITION_PIN = (
    100_280,
    "910b2f0d830106b274d8ec22849e2d637463ea5fc57c3481aca2d468218bf8ef",
)
BASE_MANIFEST_PIN = (
    15_118,
    "0c4b7b3979c5c3bcdfb3a9bef38b5b32f4da5df31633a0c38920ef937914e301",
)
BASE_TREE_SHA256 = "3ec1197343778c51609221aedbac6f4bf8942cb6620c80fc857b7b1f3124e52b"

COORDINATE_ARTIFACT = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v6"
)
COORDINATE_RECORDED_AT = "2026-07-21T19:41:03Z"
COORDINATE_MANIFEST_PIN = (
    3_013,
    "d44713078f9cf879e250d3696aaff59d702eaa1f4e8c77ec066b6b2dbc7dfd36",
)
COORDINATE_MANIFEST_TREE_SHA256 = (
    "838c968ba9a31dd1399798b00ef63ee1b231d059a6d6b1ced74dea9f4199a616"
)
COORDINATE_PHYSICAL_TREE_SHA256 = (
    "905ec4fb87f92106edfea595723a35507cddf654bc00cc60e1a4d50e46ce1ba0"
)


@dataclass(frozen=True)
class CoordinateReplacementV6:
    index: int
    predecessor_path: str
    predecessor_bytes: int
    predecessor_sha256: str
    successor_path: str
    successor_bytes: int
    successor_sha256: str
    campus_key: str
    project_key: str
    evidence_key: str
    evidence_kind: str
    source_family: str


_ARTIFACT_PREFIX = "source_artifacts/site-coordinate-assessment-2026-07-21-v6/"
REPLACEMENTS = (
    CoordinateReplacementV6(
        428,
        "sources/curated-official-2026-07-21-microsoft-ath04-spata-current-build.json",
        8_386,
        "4368d6b67766cfdcddeeaf30cf7e70f4e82d1094ea8616952b0fa7a85bdc9c97",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-microsoft-ath04-"
        "spata-current-build-coordinate-v6.json",
        17_276,
        "0cfec135b321bc0c7f10ff6660b7ff33e43a02634af1eefe0095d1d327e1ebf2",
        "curated:microsoft-ath04-spata-data-center",
        "curated:microsoft-ath04-spata-data-center:active-construction",
        "greece-microsoft-ath04-e31-e26-site-geometry-assessed-2026-07-21",
        "government_record",
        "greece_strategic_investment_site_plan_records",
    ),
    CoordinateReplacementV6(
        429,
        "sources/curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json",
        6_455,
        "1ec21ecde6660e3ff62b469693fe277998b85fc892127ca15d9612981381a65f",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-tet-dc7-salaspils-"
        "phase1-current-build-coordinate-v6.json",
        9_545,
        "ad64eebd072949695cab3051d70dccb80c637281807f22617a6c876a50ab27d0",
        "curated:tet-dc7-salaspils-data-center",
        "curated:tet-dc7-salaspils-data-center:phase-1-current-build",
        "latvia-vzd-tet-dc7-address-point-assessed-2026-07-21",
        "government_record",
        "latvia_vzd_address_register",
    ),
    CoordinateReplacementV6(
        430,
        "sources/curated-official-2026-07-21-ten-brinke-spata-current-build.json",
        7_835,
        "feb7d0fb6fc9ef7da9fe06ab16177a75247b3220ffeba6572cf8dccebd61bed4",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-ten-brinke-spata-"
        "current-build-coordinate-v6.json",
        10_642,
        "159a1326c5dabf9d87b62d0d72ab31f09d7591b6e148826879fc889e1dce9344",
        "curated:ten-brinke-spata-data-center",
        "curated:ten-brinke-spata-data-center:active-construction",
        "ten-brinke-spata-project-map-point-captured-2026-07-21",
        "company_disclosure",
        "ten_brinke_project_pages",
    ),
    CoordinateReplacementV6(
        431,
        "sources/curated-official-2026-07-21-ast-janciems-shell-fit-out.json",
        4_296,
        "02b9f7c85d1a22ff4b290c01954adce2909295fd33517993496f4221fc61f206",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-ast-janciems-"
        "shell-fit-out-coordinate-v6.json",
        7_213,
        "7e56879107d1ac8e47820047584503909e5dc304a5fd8ef6bfd6390e51a30388",
        "curated:ast-janciems-dispatcher-control-data-center",
        (
            "curated:ast-janciems-dispatcher-control-data-center:"
            "fit-out-after-building-completion"
        ),
        "latvia-vzd-ast-janciems-address-point-assessed-2026-07-21",
        "government_record",
        "latvia_vzd_address_register",
    ),
    CoordinateReplacementV6(
        433,
        "sources/curated-official-2026-07-21-airtrunk-syd3-current-build.json",
        7_293,
        "050cbf1db6b1ed0ba414a352ed89607b26277802fe339e2176f15fe04ddf09ff",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-airtrunk-syd3-"
        "current-build-coordinate-v6.json",
        10_864,
        "79206ac75bdc2dccb6a527289c029383b7f5114619ae107fd315aa44269a13d0",
        "curated:airtrunk-syd3-western-sydney-campus",
        "curated:airtrunk-syd3-western-sydney-campus:current-build",
        "nsw-airtrunk-syd3-drupal-geofield-coordinate-assessed-2026-07-21",
        "government_record",
        "nsw_major_projects_and_bcf_records",
    ),
    CoordinateReplacementV6(
        434,
        "sources/curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json",
        5_409,
        "af9c9fe758609be14a814d352aead1f78a1af7a3d5ab80ad990311c1ced03e16",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-cdc-eastern-creek-"
        "ec5-current-build-coordinate-v6.json",
        8_505,
        "3e104aa051e99fd4bf573579f8f81b1dc78012d1164094352de5be8e8f72c26f",
        "curated:cdc-eastern-creek-campus",
        "curated:cdc-eastern-creek-campus:ec5-current-build",
        "nsw-cdc-eastern-creek-ec5-campus-coordinate-assessed-2026-07-21",
        "government_record",
        "nsw_major_projects_records",
    ),
    CoordinateReplacementV6(
        435,
        "sources/curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json",
        5_414,
        "27852ea8af7bc6b3c3de64747041c93212e6f0515230ad64a89077c0e7463150",
        _ARTIFACT_PREFIX
        + "normalized-successors/curated-official-2026-07-21-cdc-eastern-creek-"
        "ec6-current-build-coordinate-v6.json",
        8_505,
        "536861d0e662892cfb9f3fafdf26af464a67639ec8bff62261ddc23ffad61ee6",
        "curated:cdc-eastern-creek-campus",
        "curated:cdc-eastern-creek-campus:ec6-current-build",
        "nsw-cdc-eastern-creek-ec6-campus-coordinate-assessed-2026-07-21",
        "government_record",
        "nsw_major_projects_records",
    ),
)

NEW_EVIDENCE_KEYS = frozenset(row.evidence_key for row in REPLACEMENTS)
NEW_SOURCE_FAMILIES = frozenset(row.source_family for row in REPLACEMENTS)
GOVERNMENT_EVIDENCE_KEYS = frozenset(
    row.evidence_key for row in REPLACEMENTS if row.evidence_kind == "government_record"
)
COMPANY_EVIDENCE_KEYS = NEW_EVIDENCE_KEYS - GOVERNMENT_EVIDENCE_KEYS
ATH04_KEYS = frozenset({REPLACEMENTS[0].campus_key, REPLACEMENTS[0].project_key})
AFFECTED_ENTITY_KEYS = frozenset(
    {key for row in REPLACEMENTS for key in (row.campus_key, row.project_key)}
)
AFFECTED_PROJECT_KEYS = frozenset(row.project_key for row in REPLACEMENTS)

POINT_CONTRACT: dict[str, tuple[float, float, str]] = {
    "curated:tet-dc7-salaspils-data-center": (
        56.8656322193,
        24.3802635323,
        "latvia_vzd_address_register",
    ),
    "curated:tet-dc7-salaspils-data-center:phase-1-current-build": (
        56.8656322193,
        24.3802635323,
        "latvia_vzd_address_register",
    ),
    "curated:ten-brinke-spata-data-center": (
        37.96626241294147,
        23.90870178233002,
        "ten_brinke_project_pages",
    ),
    "curated:ten-brinke-spata-data-center:active-construction": (
        37.96626241294147,
        23.90870178233002,
        "ten_brinke_project_pages",
    ),
    "curated:ast-janciems-dispatcher-control-data-center": (
        56.933100002,
        24.1814716538,
        "latvia_vzd_address_register",
    ),
    (
        "curated:ast-janciems-dispatcher-control-data-center:"
        "fit-out-after-building-completion"
    ): (56.933100002, 24.1814716538, "latvia_vzd_address_register"),
    "curated:airtrunk-syd3-western-sydney-campus": (
        -33.798627,
        150.876,
        "nsw_major_projects_and_bcf_records",
    ),
    "curated:airtrunk-syd3-western-sydney-campus:current-build": (
        -33.798627,
        150.876,
        "nsw_major_projects_and_bcf_records",
    ),
    "curated:cdc-eastern-creek-campus": (
        -33.818072,
        150.837668,
        "nsw_major_projects_records",
    ),
    "curated:cdc-eastern-creek-campus:ec5-current-build": (
        -33.818072,
        150.837668,
        "nsw_major_projects_records",
    ),
    "curated:cdc-eastern-creek-campus:ec6-current-build": (
        -33.818072,
        150.837668,
        "nsw_major_projects_records",
    ),
}

UNCHANGED_INDEX_PINS = {
    393: (
        "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
        "normalized-successors/curated-official-2026-07-21-akashi-astana-"
        "phase-1-current-build-coordinate-v5.json",
        "b1f3f37927895d6e7a02adc9afd8b93aac9e0a322d846158fe362c645a07e3a6",
    ),
    395: (
        "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
        "normalized-successors/curated-official-2026-07-21-icatec-ica-"
        "current-build-coordinate-v5.json",
        "88d05044c8a3ab7ad7c4f0a42227cb610b2b0fff43863672c5faf0a121d31e2a",
    ),
    396: (
        "source_artifacts/site-coordinate-assessment-2026-07-21-v5/"
        "normalized-successors/curated-official-2026-07-21-lvrtc-pozitrons-"
        "kurzeme-current-build-coordinate-v5.json",
        "5fce778372ee4d01b8e7990a11624ed2d588007c9a071e7f73a9e2a8a117e426",
    ),
    432: (
        "sources/curated-official-2026-07-21-serbia-state-dc-kragujevac-"
        "modules-3-4-operational.json",
        "36cccf1eaa107e1581879722438ca1f22e5c371ae77cbaeb8d0a9bc76b5d38f2",
    ),
    436: (
        "sources/curated-official-2026-07-21-cdc-marsden-park-current-build.json",
        "8ef701ac0b4346aed089996487a149dd1aea2545ce11b0b30c53faf5a1807322",
    ),
}

FRESHNESS_README = f"""
Open seed v85 is the exact accepted v84 successor with seven curated inputs
replaced in place by coordinate-only successors from
`source_artifacts/site-coordinate-assessment-2026-07-21-v6`. Input cardinality
and order remain 447. The coordinate artifact manifest is
`{COORDINATE_MANIFEST_PIN[1]}`, logical tree
`{COORDINATE_MANIFEST_TREE_SHA256}`, and physical tree
`{COORDINATE_PHYSICAL_TREE_SHA256}`.

Six successors add source-reported Point geometry. CDC EC5 and EC6 deliberately
share one campus-level point that is not facility-specific. ATH04 adds the
official E31 project Polygon and E31+E26 campus MultiPolygon while retaining
null representative coordinates. The schema-1.1 importer and this release
projection preserve that explicit absence; no polygon centroid or bounding-box
midpoint is published. Marsden Park remains unchanged and review-only because
its two official lot points cannot be represented without arbitrary selection
or a MultiPoint schema extension.

No identity, lifecycle, capacity, PUE, energy, consumption, ownership,
operator, tenant, workload, type, or current-status claim changes. No OSM,
Google, satellite, aerial, or computer-vision claim is integrated. Every
lifecycle value remains a dated last-observed fact;
`current_status_classification` remains `unknown` and
`current_construction_claim` remains `false`.
""".strip()


class OpenSeedV85Error(RuntimeError):
    """Raised when a v85 lineage, claim, or publication fuse fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise OpenSeedV85Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV85Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV85Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_coordinate_artifact() -> dict[str, dict[str, Any]]:
    artifact = COORDINATE_ARTIFACT
    if (
        artifact.is_symlink()
        or not artifact.is_dir()
        or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        or v69.tree_digest(artifact) != COORDINATE_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV85Error("coordinate v6 artifact is not exact and frozen")
    if any(
        path.is_symlink()
        or stat.S_IMODE(path.stat().st_mode) != (0o555 if path.is_dir() else 0o444)
        for path in artifact.rglob("*")
    ):
        raise OpenSeedV85Error("coordinate v6 artifact member mode differs")
    manifest_raw, manifest = _read_json(artifact / "manifest.json", mode=0o444)
    if (
        (len(manifest_raw), _sha256(manifest_raw)) != COORDINATE_MANIFEST_PIN
        or manifest.get("schema_version") != "1.2"
        or manifest.get("artifact_id")
        != "site-coordinate-assessment-2026-07-21-v6"
        or manifest.get("recorded_at") != COORDINATE_RECORDED_AT
        or manifest.get("integration") != "none"
        or manifest.get("publication_contract_version") != 6
        or manifest.get("tree_sha256") != COORDINATE_MANIFEST_TREE_SHA256
    ):
        raise OpenSeedV85Error("coordinate v6 manifest contract differs")
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise OpenSeedV85Error("coordinate v6 manifest inventory differs")
    actual = {
        path.relative_to(artifact).as_posix()
        for path in artifact.rglob("*")
        if path.is_file()
    }
    if actual != {row["path"] for row in listed} | {
        "manifest.json",
        "manifest.sha256",
    }:
        raise OpenSeedV85Error("coordinate v6 artifact is not closed")
    for row in listed:
        raw = (artifact / row["path"]).read_bytes()
        if (len(raw), _sha256(raw)) != (row["bytes"], row["sha256"]):
            raise OpenSeedV85Error(
                f"coordinate v6 file pin differs: {row['path']}"
            )
    if _sha256(_canonical(listed)) != COORDINATE_MANIFEST_TREE_SHA256:
        raise OpenSeedV85Error("coordinate v6 logical tree differs")
    if (artifact / "manifest.sha256").read_text() != (
        f"{COORDINATE_MANIFEST_PIN[1]}  manifest.json\n"
    ):
        raise OpenSeedV85Error("coordinate v6 sidecar differs")
    recorded = v70.parse_utc(COORDINATE_RECORDED_AT, label="coordinate recorded_at")
    if recorded > datetime.now(UTC) or artifact.stat().st_ctime + 1e-6 < recorded.timestamp():
        raise OpenSeedV85Error("coordinate v6 publication time differs")

    _, disposition = _read_json(artifact / "disposition.json", mode=0o444)
    accepted = disposition.get("accepted", {}).get("successors", {})
    not_accepted = disposition.get("not_accepted", {}).get("rows", [])
    guard = disposition.get("ath04_geometry_only_guard", {})
    boundaries = disposition.get("source_boundaries", {})
    if (
        disposition.get("integration") != "none"
        or disposition.get("accepted_seed_definition") is not None
        or disposition.get("non_coordinate_claims_added") != []
        or len(accepted) != 7
        or len(not_accepted) != 6
        or sum(
            row.get("predecessor")
            == UNCHANGED_INDEX_PINS[436][0]
            and row.get("successor") is None
            and row.get("disposition")
            == "review_two_official_lot_points_no_multipoint_schema"
            for row in not_accepted
        )
        != 1
        or guard.get("coordinates_remain_null") is not True
        or guard.get("representative_point_published") is not False
        or guard.get("curated_bbox_midpoint_synthesis_must_be_suppressed")
        is not True
        or guard.get("release_geometry_center_must_be_suppressed") is not True
        or boundaries.get("osm_inputs_consumed") != []
        or boundaries.get("google_content_captured_or_redistributed") is not False
        or boundaries.get("raw_official_or_company_bodies_redistributed")
        is not False
        or boundaries.get("satellite_or_cv_claims_added") is not False
    ):
        raise OpenSeedV85Error("coordinate v6 disposition boundary differs")

    documents: dict[str, dict[str, Any]] = {}
    accepted_by_predecessor = {
        row.get("predecessor"): row for row in accepted.values()
    }
    for replacement in REPLACEMENTS:
        artifact_relative = replacement.successor_path.removeprefix(_ARTIFACT_PREFIX)
        row = accepted_by_predecessor.get(replacement.predecessor_path)
        if row is None or (
            row.get("path") != artifact_relative
            or row.get("bytes") != replacement.successor_bytes
            or row.get("sha256") != replacement.successor_sha256
            or row.get("predecessor_sha256") != replacement.predecessor_sha256
            or row.get("campus_key") != replacement.campus_key
            or row.get("project_key") != replacement.project_key
            or row.get("added_evidence_key") != replacement.evidence_key
            or row.get("added_evidence_kind") != replacement.evidence_kind
        ):
            raise OpenSeedV85Error("coordinate v6 accepted successor differs")
        source = ROOT / replacement.successor_path
        raw, document = _read_json(source, mode=0o444)
        if (len(raw), _sha256(raw)) != (
            replacement.successor_bytes,
            replacement.successor_sha256,
        ):
            raise OpenSeedV85Error("coordinate v6 successor byte pin differs")
        predecessor_raw, predecessor = _read_json(
            ROOT / replacement.predecessor_path, mode=0o444
        )
        if (len(predecessor_raw), _sha256(predecessor_raw)) != (
            replacement.predecessor_bytes,
            replacement.predecessor_sha256,
        ):
            raise OpenSeedV85Error("coordinate v6 predecessor byte pin differs")
        _validate_successor(predecessor, document, replacement)
        documents[replacement.successor_path] = document
    return documents


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    replacement: CoordinateReplacementV6,
) -> None:
    if (
        predecessor.get("schema_version") != "1.1"
        or successor.get("schema_version") != "1.1"
        or set(predecessor) != set(successor)
    ):
        raise OpenSeedV85Error("coordinate v6 schema differs")
    before_evidence = predecessor.get("evidence")
    after_evidence = successor.get("evidence")
    if (
        not isinstance(before_evidence, list)
        or not isinstance(after_evidence, list)
        or after_evidence[:-1] != before_evidence
        or len(after_evidence) != len(before_evidence) + 1
    ):
        raise OpenSeedV85Error("coordinate v6 evidence append differs")
    evidence = after_evidence[-1]
    if (
        evidence.get("key") != replacement.evidence_key
        or evidence.get("kind") != replacement.evidence_kind
        or evidence.get("source_family") != replacement.source_family
        or evidence.get("metadata", {}).get("coordinate_assessment_artifact_id")
        != "site-coordinate-assessment-2026-07-21-v6"
        or "adds no identity" not in evidence.get("metadata", {}).get(
            "claim_guardrail", ""
        )
    ):
        raise OpenSeedV85Error("coordinate v6 evidence boundary differs")

    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(before_evidence)
    expected_changed = (
        {"geometry", "evidence_key", "method"}
        if replacement.campus_key in ATH04_KEYS
        else {"coordinates", "geometry", "evidence_key", "method"}
    )
    for entity_name, expected_key in (
        ("campus", replacement.campus_key),
        ("project", replacement.project_key),
    ):
        before = predecessor[entity_name]
        after = successor[entity_name]
        if before.get("stable_key") != expected_key or after.get(
            "stable_key"
        ) != expected_key:
            raise OpenSeedV85Error("coordinate v6 entity identity differs")
        changed = {
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        if changed != expected_changed:
            raise OpenSeedV85Error("coordinate v6 non-coordinate delta detected")
        if before.get("coordinates") is not None or before.get("geometry") is not None:
            raise OpenSeedV85Error("coordinate v6 predecessor was already located")
        if after.get("evidence_key") != replacement.evidence_key:
            raise OpenSeedV85Error("coordinate v6 snapshot evidence differs")
        if expected_key in ATH04_KEYS:
            expected_type = "MultiPolygon" if entity_name == "campus" else "Polygon"
            if (
                after.get("coordinates") is not None
                or after.get("geometry", {}).get("type") != expected_type
                or after.get("method") != "authoritative_site_plan"
            ):
                raise OpenSeedV85Error("ATH04 geometry-only contract differs")
        else:
            latitude, longitude, _family = POINT_CONTRACT[expected_key]
            if (
                after.get("coordinates")
                != {"latitude": latitude, "longitude": longitude}
                or after.get("geometry")
                != {"type": "Point", "coordinates": [longitude, latitude]}
                or after.get("method")
                not in {"authoritative_site_plan", "authoritative_address_geocode"}
            ):
                raise OpenSeedV85Error("coordinate v6 Point contract differs")
        for key in changed:
            restored[entity_name][key] = copy.deepcopy(before[key])
    if restored != predecessor:
        raise OpenSeedV85Error("coordinate v6 successor gained another claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section]:
            raise OpenSeedV85Error(f"coordinate v6 changed {section}")


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV85Error(f"accepted v84 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != "2026-07-21-open-seed-v84":
        raise OpenSeedV85Error("v85 base must be exactly accepted v84")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 447:
        raise OpenSeedV85Error("accepted v84 curated inventory differs")
    documents = _validate_coordinate_artifact()
    target = v70.parse_utc(recorded_at, label="v85 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or v70.parse_utc(COORDINATE_RECORDED_AT, label="coordinate recorded_at")
        > target
    ):
        raise OpenSeedV85Error("v85 publication time precedes an input")

    by_index = {replacement.index: replacement for replacement in REPLACEMENTS}
    if set(by_index) != {428, 429, 430, 431, 433, 434, 435}:
        raise OpenSeedV85Error("v85 replacement index inventory differs")
    selected: list[dict[str, str]] = []
    paths: list[Path] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedV85Error("accepted v84 curated row differs")
        replacement = by_index.get(index)
        if replacement is None:
            output = dict(row)
            path = ROOT / row["path"]
            if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
                raise OpenSeedV85Error(f"accepted v84 input drifted: {row['path']}")
        else:
            if row != {
                "path": replacement.predecessor_path,
                "sha256": replacement.predecessor_sha256,
            }:
                raise OpenSeedV85Error(f"v85 predecessor index differs: {index}")
            path = ROOT / replacement.successor_path
            if documents.get(replacement.successor_path) is None:
                raise OpenSeedV85Error("validated successor inventory differs")
            output = {
                "path": replacement.successor_path,
                "sha256": replacement.successor_sha256,
            }
        selected.append(output)
        paths.append(path)

    if len(selected) != 447 or len({row["path"] for row in selected}) != 447:
        raise OpenSeedV85Error("v85 selected inventory collides")
    for index, expected in UNCHANGED_INDEX_PINS.items():
        if (selected[index]["path"], selected[index]["sha256"]) != expected:
            raise OpenSeedV85Error(f"v85 changed protected index {index}")
    for relative, document in zip(
        (row["path"] for row in selected),
        (json.loads(path.read_text()) for path in paths),
        strict=True,
    ):
        for index, evidence in enumerate(document.get("evidence", [])):
            retrieved = v70.parse_utc(
                evidence.get("retrieved_at"),
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV85Error("v85 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_coordinate_artifact()
    return {
        "base_definition": (
            BASE_DEFINITION.stat().st_size,
            v69.sha256(BASE_DEFINITION),
        ),
        "base_manifest": (
            (BASE_RELEASE / "manifest.json").stat().st_size,
            v69.sha256(BASE_RELEASE / "manifest.json"),
        ),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "coordinate_manifest": (
            (COORDINATE_ARTIFACT / "manifest.json").stat().st_size,
            v69.sha256(COORDINATE_ARTIFACT / "manifest.json"),
        ),
        "coordinate_tree": v69.tree_digest(COORDINATE_ARTIFACT),
        "predecessors": {
            row.predecessor_path: (
                (ROOT / row.predecessor_path).stat().st_size,
                v69.sha256(ROOT / row.predecessor_path),
            )
            for row in REPLACEMENTS
        },
        "successors": {
            row.successor_path: (
                (ROOT / row.successor_path).stat().st_size,
                v69.sha256(ROOT / row.successor_path),
            )
            for row in REPLACEMENTS
        },
        "protected_indices": {
            index: tuple(json.loads(BASE_DEFINITION.read_text())["curated_inputs"][index].values())
            for index in UNCHANGED_INDEX_PINS
        },
    }


def _logical_rows(connection: sqlite3.Connection, table: str) -> Counter[tuple[Any, ...]]:
    if table == "lifecycle_observations":
        query = """
            SELECT entities.stable_key, status, evidence.title, evidence.source_url,
                   as_of_date, valid_to_date, lifecycle_observations.method,
                   lifecycle_observations.confidence, lifecycle_observations.notes
            FROM lifecycle_observations
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    elif table == "capacity_estimates":
        query = """
            SELECT entities.stable_key, metric, stage, unit, low, base, high,
                   capacity_estimates.method, capacity_estimates.confidence,
                   evidence.title, evidence.source_url, as_of_date, target_date,
                   valid_to_date, capacity_estimates.notes
            FROM capacity_estimates
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    elif table in {"operating_model_observations", "workload_observations"}:
        value = (
            "operating_model"
            if table == "operating_model_observations"
            else "workload"
        )
        query = f"""
            SELECT entities.stable_key, {value}, evidence.title, evidence.source_url,
                   as_of_date, valid_to_date, {table}.method, {table}.confidence,
                   {table}.notes
            FROM {table}
            JOIN entities ON entities.id = entity_id
            JOIN evidence ON evidence.id = evidence_id
        """
    else:  # pragma: no cover - internal misuse guard
        raise OpenSeedV85Error(f"unsupported logical table: {table}")
    return Counter(tuple(row) for row in connection.execute(query))


def _snapshot_rows(
    connection: sqlite3.Connection,
) -> dict[str, list[tuple[Any, ...]]]:
    rows: dict[str, list[tuple[Any, ...]]] = {}
    for row in connection.execute(
        """
        SELECT entities.stable_key, entity_snapshots.name, latitude, longitude,
               geometry_json, tags_json, evidence.source_family, evidence.title,
               evidence.source_url, as_of_date, valid_to_date,
               entity_snapshots.method, entity_snapshots.confidence
        FROM entity_snapshots
        JOIN entities ON entities.id = entity_id
        JOIN evidence ON evidence.id = evidence_id
        """
    ):
        rows.setdefault(row[0], []).append(tuple(row[1:]))
    for values in rows.values():
        values.sort(key=repr)
    return rows


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 917,
        "entity_snapshots": 938,
        "evidence": 754,
        "lifecycle_observations": 532,
        "capacity_estimates": 551,
        "operating_model_observations": 71,
        "workload_observations": 135,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV85Error(f"v85 database counts differ: {actual_counts}")

    selected_documents = _validate_coordinate_artifact()
    ath_geometry = {
        REPLACEMENTS[0].campus_key: selected_documents[
            REPLACEMENTS[0].successor_path
        ]["campus"]["geometry"],
        REPLACEMENTS[0].project_key: selected_documents[
            REPLACEMENTS[0].successor_path
        ]["project"]["geometry"],
    }
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v85-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v84.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "campuses",
                "facilities",
                "buildings",
                "projects",
                "administrative_assignments",
            ):
                before = {tuple(row) for row in prior.execute(f"SELECT * FROM {table}")}
                after = {
                    tuple(row) for row in connection.execute(f"SELECT * FROM {table}")
                }
                if before != after:
                    raise OpenSeedV85Error(f"v85 changed logical {table}")
            before_entities = {
                tuple(row)
                for row in prior.execute(
                    "SELECT id, kind, stable_key FROM entities"
                )
            }
            after_entities = {
                tuple(row)
                for row in connection.execute(
                    "SELECT id, kind, stable_key FROM entities"
                )
            }
            if before_entities != after_entities:
                raise OpenSeedV85Error("v85 entity identities changed")
            before_evidence_keys = set(v70._evidence_by_key(prior))
            after_evidence_keys = set(v70._evidence_by_key(connection))
            if (
                after_evidence_keys - before_evidence_keys != NEW_EVIDENCE_KEYS
                or before_evidence_keys - after_evidence_keys
            ):
                raise OpenSeedV85Error("v85 evidence-key delta differs")
            for table in (
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            ):
                if _logical_rows(prior, table) != _logical_rows(connection, table):
                    raise OpenSeedV85Error(f"v85 changed logical {table}")

            before_snapshots = _snapshot_rows(prior)
            after_snapshots = _snapshot_rows(connection)
            if set(before_snapshots) != set(after_snapshots):
                raise OpenSeedV85Error("v85 snapshot identities changed")
            for stable_key in before_snapshots:
                if stable_key not in AFFECTED_ENTITY_KEYS and (
                    before_snapshots[stable_key] != after_snapshots[stable_key]
                ):
                    raise OpenSeedV85Error(
                        f"v85 changed non-coordinate snapshot: {stable_key}"
                    )
            affected_after = [
                row
                for stable_key in AFFECTED_ENTITY_KEYS
                for row in after_snapshots[stable_key]
            ]
            if len(affected_after) != 14:
                raise OpenSeedV85Error("v85 affected snapshot count differs")
            if sum(
                row[1] is not None and row[2] is not None for row in affected_after
            ) != 12 or sum(row[3] not in {None, "null"} for row in affected_after) != 14:
                raise OpenSeedV85Error("v85 geometry/point snapshot partition differs")
            for stable_key in AFFECTED_ENTITY_KEYS:
                if any(
                    row[1] is not None
                    or row[2] is not None
                    or row[3] not in {None, "null"}
                    for row in before_snapshots[stable_key]
                ):
                    raise OpenSeedV85Error(
                        f"v85 predecessor was already located: {stable_key}"
                    )
                for row in after_snapshots[stable_key]:
                    if stable_key in ATH04_KEYS:
                        if (
                            row[1] is not None
                            or row[2] is not None
                            or json.loads(row[3]) != ath_geometry[stable_key]
                            or row[5]
                            != "greece_strategic_investment_site_plan_records"
                            or row[10] != "authoritative_site_plan"
                        ):
                            raise OpenSeedV85Error(
                                "ATH04 imported representative-point contract differs"
                            )
                    else:
                        latitude, longitude, family = POINT_CONTRACT[stable_key]
                        if (
                            row[1] != latitude
                            or row[2] != longitude
                            or json.loads(row[3])
                            != {
                                "type": "Point",
                                "coordinates": [longitude, latitude],
                            }
                            or row[5] != family
                        ):
                            raise OpenSeedV85Error(
                                f"v85 imported Point differs: {stable_key}"
                            )
        finally:
            prior.close()

    new_evidence: dict[str, sqlite3.Row] = {}
    for row in connection.execute(
        "SELECT id, kind, source_family, metadata_json FROM evidence"
    ):
        key = json.loads(row["metadata_json"] or "{}").get("curated_record_key")
        if key in NEW_EVIDENCE_KEYS:
            new_evidence[key] = row
    if (
        set(new_evidence) != NEW_EVIDENCE_KEYS
        or {
            key
            for key, row in new_evidence.items()
            if row["kind"] == "government_record"
        }
        != GOVERNMENT_EVIDENCE_KEYS
        or {
            key
            for key, row in new_evidence.items()
            if row["kind"] == "company_disclosure"
        }
        != COMPANY_EVIDENCE_KEYS
        or {row["source_family"] for row in new_evidence.values()}
        != NEW_SOURCE_FAMILIES
    ):
        raise OpenSeedV85Error("v85 new evidence classification differs")
    new_evidence_ids = {row["id"] for row in new_evidence.values()}
    placeholders = ",".join("?" for _ in new_evidence_ids)
    for table in (
        "lifecycle_observations",
        "capacity_estimates",
        "operating_model_observations",
        "workload_observations",
    ):
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE evidence_id IN ({placeholders})",
            tuple(sorted(new_evidence_ids)),
        ).fetchone()[0]
        if count:
            raise OpenSeedV85Error(f"coordinate evidence created {table}")

    current_snapshots = _current_rows(
        connection,
        "entity_snapshots",
        as_of=AS_OF,
        recorded_at=recorded_at,
    )
    entity_kinds = {
        row["id"]: row["kind"]
        for row in connection.execute("SELECT id, kind FROM entities")
    }
    located = [
        row
        for row in current_snapshots
        if row["latitude"] is not None and row["longitude"] is not None
    ]
    coordinate_entities = len(located)
    coordinate_campuses = sum(
        entity_kinds[row["entity_id"]] == "campus" for row in located
    )
    if (coordinate_entities, coordinate_campuses) != (213, 141):
        raise OpenSeedV85Error("v85 coordinate coverage differs")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(
        base, paths, sqlite_path, recorded_at=recorded_at
    )
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _csv_rows_text(text: str) -> tuple[list[str], list[dict[str, str]]]:
    stream = io.StringIO(text, newline="")
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        raise OpenSeedV85Error("release CSV has no header")
    return list(reader.fieldnames), list(reader)


def _csv_document(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _blank_geometry_only_representative_points(
    documents: Mapping[str, str],
) -> dict[str, str]:
    output = dict(documents)
    expected = {
        "entities.csv": ATH04_KEYS,
        "construction_pipeline.csv": {REPLACEMENTS[0].project_key},
    }
    for filename, expected_keys in expected.items():
        fields, rows = _csv_rows_text(output[filename])
        selected = {row["stable_key"] for row in rows if row["stable_key"] in ATH04_KEYS}
        if selected != expected_keys:
            raise OpenSeedV85Error(f"ATH04 {filename} row partition differs")
        for row in rows:
            if row["stable_key"] not in expected_keys:
                continue
            if not row["latitude"] or not row["longitude"]:
                raise OpenSeedV85Error(f"legacy ATH04 {filename} center is absent")
            geometry = json.loads(row["geometry_json"])
            expected_type = (
                "MultiPolygon"
                if row["stable_key"] == REPLACEMENTS[0].campus_key
                else "Polygon"
            )
            if geometry.get("type") != expected_type:
                raise OpenSeedV85Error(f"ATH04 {filename} geometry differs")
            row["latitude"] = ""
            row["longitude"] = ""
        output[filename] = _csv_document(fields, rows)

    fields, signals = _csv_rows_text(output["construction_source_signals.csv"])
    selected_signals = [
        row
        for row in signals
        if row["representative_stable_key"] == REPLACEMENTS[0].project_key
    ]
    if len(selected_signals) != 1:
        raise OpenSeedV85Error("ATH04 construction signal partition differs")
    signal = selected_signals[0]
    if not signal["representative_latitude"] or not signal["representative_longitude"]:
        raise OpenSeedV85Error("legacy ATH04 construction-signal center is absent")
    signal["representative_latitude"] = ""
    signal["representative_longitude"] = ""
    output["construction_source_signals.csv"] = _csv_document(fields, signals)

    atlas = json.loads(output["atlas.geojson"])
    ath_features = {
        feature["properties"]["stable_key"]: feature
        for feature in atlas["features"]
        if feature["properties"]["stable_key"] in ATH04_KEYS
    }
    if set(ath_features) != ATH04_KEYS:
        raise OpenSeedV85Error("ATH04 atlas feature partition differs")
    for stable_key, feature in ath_features.items():
        expected_type = (
            "MultiPolygon" if stable_key == REPLACEMENTS[0].campus_key else "Polygon"
        )
        if (
            feature["geometry"].get("type") != expected_type
            or feature["properties"].get("latitude") is not None
            or feature["properties"].get("longitude") is not None
        ):
            raise OpenSeedV85Error("ATH04 atlas representative-point contract differs")
    return output


def _curate_resolution_advisories(
    documents: Mapping[str, str],
) -> dict[str, str]:
    output = dict(documents)
    candidates = json.loads(output["resolution_candidates.json"])
    if not isinstance(candidates, list):
        raise OpenSeedV85Error("v85 resolution JSON shape differs")

    nextdc_pair = frozenset(
        {"NEXTDC S4 Sydney Data Center Campus", "CDC Eastern Creek Campus"}
    )
    airtrunk_pair = frozenset(
        {"AirTrunk SYD3 Western Sydney Campus", "CDC Eastern Creek Campus"}
    )
    nextdc_rows = [
        row
        for row in candidates
        if frozenset({row.get("left_name"), row.get("right_name")}) == nextdc_pair
    ]
    airtrunk_rows = [
        row
        for row in candidates
        if frozenset({row.get("left_name"), row.get("right_name")}) == airtrunk_pair
    ]
    if (
        len(nextdc_rows) != 1
        or len(airtrunk_rows) != 1
        or nextdc_rows[0].get("distance_m") != 1596.601
        or nextdc_rows[0].get("score") != 0.367287
        or nextdc_rows[0].get("relationship_suggestion") != "nearby_only"
        or nextdc_rows[0].get("signals", {}).get("name_similarity") != 0.218182
    ):
        raise OpenSeedV85Error("v85 raw NSW resolution partition differs")

    # NEXTDC's embedded ``CDC`` character run is not a standalone identity token.
    # Keep the candidate, but use the token-safe name similarity.  The AirTrunk and
    # CDC points derive from overlapping NSW major-project records, so that pair is
    # not an independent cross-source advisory and is omitted locally.
    nextdc_rows[0]["signals"]["name_similarity"] = 0.145455
    nextdc_rows[0]["score"] = 0.345469
    candidates.remove(airtrunk_rows[0])
    candidates.sort(key=lambda row: (row["left_entity_id"], row["right_entity_id"]))
    output["resolution_candidates.json"] = (
        json.dumps(candidates, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    fields, _rows = _csv_rows_text(output["resolution_candidates.csv"])
    csv_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        row["signals_json"] = json.dumps(
            row.pop("signals"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        csv_rows.append(row)
    output["resolution_candidates.csv"] = _csv_document(fields, csv_rows)
    return output


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    output = _curate_resolution_advisories(
        _blank_geometry_only_representative_points(documents)
    )
    freshness = build_freshness_csv(output["entities.csv"], as_of=AS_OF)
    output[FRESHNESS_FILENAME] = freshness
    output["README.md"] = (
        output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    )
    manifest = json.loads(output["manifest.json"])
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(
        list(csv.DictReader(io.StringIO(freshness)))
    )
    manifest["lifecycle_status_semantics"] = "last_observed"
    manifest["geometry_only_representative_point_inferred"] = False
    manifest["resolution_candidates"] = len(
        json.loads(output["resolution_candidates.json"])
    )
    for filename, text in output.items():
        if filename == "manifest.json":
            continue
        manifest["files"][filename] = {
            "bytes": len(text.encode()),
            "sha256": _sha256(text.encode()),
        }
    output["manifest.json"] = _canonical(manifest, sort_keys=True).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV85Error("precreated v85 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _csv_counter(
    path: Path, *, recorded_at_values: set[str]
) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(
            tuple(
                (
                    key,
                    "<recorded-at>" if value in recorded_at_values else value,
                )
                for key, value in row.items()
            )
            for row in csv.DictReader(stream)
        )


CSV_DELTA_COUNT_CONTRACT = {
    "entities.csv": (904, 13, 13),
    "evidence.csv": (596, 7, 1),
    "capacity_estimates.csv": (550, 0, 0),
    "construction_pipeline.csv": (457, 7, 7),
    "construction_source_signals.csv": (360, 6, 6),
    "lifecycle_freshness.csv": (512, 0, 0),
    "resolution_candidates.csv": (7, 2, 0),
}
REMOVED_PUBLIC_EVIDENCE_ID = "436b9bc3-1765-5a32-bd96-7a610beae227"
REMOVED_PUBLIC_SOURCE_KEY = (
    "airtrunk-syd3-current-facility-page-captured-2026-07-21"
)
REMOVED_PUBLIC_SOURCE_FAMILY = "airtrunk_current_location_pages"


def _coordinate_contracts() -> dict[str, dict[str, Any]]:
    contracts = {
        stable_key: {
            "latitude": latitude,
            "longitude": longitude,
            "geometry": {
                "type": "Point",
                "coordinates": [longitude, latitude],
            },
            "source_family": family,
        }
        for stable_key, (latitude, longitude, family) in POINT_CONTRACT.items()
    }
    ath04 = json.loads((ROOT / REPLACEMENTS[0].successor_path).read_text())
    for name in ("campus", "project"):
        row = ath04[name]
        contracts[row["stable_key"]] = {
            "latitude": None,
            "longitude": None,
            "geometry": row["geometry"],
            "source_family": REPLACEMENTS[0].source_family,
        }
    if set(contracts) != AFFECTED_ENTITY_KEYS:
        raise OpenSeedV85Error("v85 coordinate contract inventory differs")
    return contracts


def _validate_changed_rows(
    before: Mapping[str, dict[str, str]],
    after: Mapping[str, dict[str, str]],
    *,
    expected_keys: frozenset[str],
    allowed_fields: frozenset[str],
    label: str,
) -> None:
    if set(before) != set(after):
        raise OpenSeedV85Error(f"v85 {label} inventory differs")
    contracts = _coordinate_contracts()
    changed_keys: set[str] = set()
    for stable_key, prior in before.items():
        current = after[stable_key]
        changed = {key for key in prior if prior[key] != current[key]}
        if not changed:
            continue
        changed_keys.add(stable_key)
        if stable_key not in expected_keys or not changed <= allowed_fields:
            raise OpenSeedV85Error(f"v85 {label} non-coordinate delta: {stable_key}")
        restored = dict(current)
        for key in changed:
            restored[key] = prior[key]
        if restored != prior:
            raise OpenSeedV85Error(f"v85 {label} gained another delta: {stable_key}")
        contract = contracts[stable_key]
        if (
            current["latitude"]
            != ("" if contract["latitude"] is None else str(contract["latitude"]))
            or current["longitude"]
            != ("" if contract["longitude"] is None else str(contract["longitude"]))
            or json.loads(current["geometry_json"]) != contract["geometry"]
        ):
            raise OpenSeedV85Error(f"v85 {label} geometry differs: {stable_key}")
    if changed_keys != set(expected_keys):
        raise OpenSeedV85Error(f"v85 changed {label} set differs")


def _validate_release_delta(stage: Path, *, recorded_at: str) -> None:
    timestamps = {BASE_RECORDED_AT, recorded_at}
    for filename, expected in CSV_DELTA_COUNT_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename, recorded_at_values=timestamps)
        after = _csv_counter(stage / filename, recorded_at_values=timestamps)
        common = before & after
        actual = (
            sum(common.values()),
            sum((after - common).values()),
            sum((before - common).values()),
        )
        if actual != expected:
            raise OpenSeedV85Error(
                f"v85 public CSV delta differs: {filename}: {actual}"
            )
    for filename in ("capacity_estimates.csv", FRESHNESS_FILENAME):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV85Error(f"v85 changed invariant release file: {filename}")

    allowed = frozenset(
        {
            "latitude",
            "longitude",
            "geometry_json",
            "snapshot_evidence_id",
            "source_url",
            "source_publisher",
            "source_license",
            "source_retrieved_at",
        }
    )
    before_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    after_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    if len(after_entities) != 917:
        raise OpenSeedV85Error("v85 public entity count differs")
    _validate_changed_rows(
        before_entities,
        after_entities,
        expected_keys=AFFECTED_ENTITY_KEYS,
        allowed_fields=allowed,
        label="entity",
    )
    if sum(
        bool(row["latitude"] and row["longitude"])
        for row in after_entities.values()
    ) != 213:
        raise OpenSeedV85Error("v85 public coordinate coverage differs")
    for stable_key in ATH04_KEYS:
        row = after_entities[stable_key]
        if row["latitude"] or row["longitude"]:
            raise OpenSeedV85Error("ATH04 public representative point was inferred")

    before_evidence = {
        row["evidence_id"]: row for row in _csv_rows(BASE_RELEASE / "evidence.csv")
    }
    after_evidence = {
        row["evidence_id"]: row for row in _csv_rows(stage / "evidence.csv")
    }
    removed = set(before_evidence) - set(after_evidence)
    added_ids = set(after_evidence) - set(before_evidence)
    added_evidence = [after_evidence[key] for key in added_ids]
    if (
        removed != {REMOVED_PUBLIC_EVIDENCE_ID}
        or len(added_evidence) != 7
        or Counter(row["kind"] for row in added_evidence)
        != {"government_record": 6, "company_disclosure": 1}
        or Counter(row["source_family"] for row in added_evidence)
        != Counter(row.source_family for row in REPLACEMENTS)
        or any(
            after_evidence[key] != before_evidence[key]
            for key in set(before_evidence) & set(after_evidence)
        )
        or before_evidence[REMOVED_PUBLIC_EVIDENCE_ID]["source_family"]
        != REMOVED_PUBLIC_SOURCE_FAMILY
    ):
        raise OpenSeedV85Error("v85 public evidence projection differs")
    if any(
        after_entities[key]["snapshot_evidence_id"] not in added_ids
        for key in AFFECTED_ENTITY_KEYS
    ):
        raise OpenSeedV85Error("v85 coordinate snapshot evidence projection differs")

    before_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    after_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    _validate_changed_rows(
        before_pipeline,
        after_pipeline,
        expected_keys=AFFECTED_PROJECT_KEYS,
        allowed_fields=allowed,
        label="pipeline",
    )

    before_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_source_signals.csv")
    }
    after_signals = {
        row["source_observation_evidence_id"]: row
        for row in _csv_rows(stage / "construction_source_signals.csv")
    }
    if set(before_signals) != set(after_signals):
        raise OpenSeedV85Error("v85 construction-signal inventory differs")
    changed_signal_keys: set[str] = set()
    contracts = _coordinate_contracts()
    for evidence_id, prior in before_signals.items():
        current = after_signals[evidence_id]
        changed = {key for key in prior if prior[key] != current[key]}
        if not changed:
            continue
        stable_key = current["representative_stable_key"]
        changed_signal_keys.add(stable_key)
        contract = contracts.get(stable_key)
        if (
            changed != {"representative_latitude", "representative_longitude"}
            or contract is None
            or contract["latitude"] is None
            or current["representative_latitude"] != str(contract["latitude"])
            or current["representative_longitude"] != str(contract["longitude"])
        ):
            raise OpenSeedV85Error(
                f"v85 construction-signal coordinate differs: {stable_key}"
            )
    expected_signal_keys = set(AFFECTED_PROJECT_KEYS - ATH04_KEYS)
    if changed_signal_keys != expected_signal_keys:
        raise OpenSeedV85Error("v85 changed construction-signal set differs")
    ath_signal = [
        row
        for row in after_signals.values()
        if row["representative_stable_key"] == REPLACEMENTS[0].project_key
    ]
    if (
        len(ath_signal) != 1
        or ath_signal[0]["representative_latitude"]
        or ath_signal[0]["representative_longitude"]
    ):
        raise OpenSeedV85Error("ATH04 construction signal inferred a point")

    before_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text()
    )["sources"]
    after_sources = json.loads((stage / "source_inputs.json").read_text())["sources"]
    before_source_rows = Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in before_sources
    )
    after_source_rows = Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in after_sources
    )
    common_sources = before_source_rows & after_source_rows
    source_delta = (
        sum(common_sources.values()),
        sum((after_source_rows - common_sources).values()),
        sum((before_source_rows - common_sources).values()),
    )
    added_sources = [
        json.loads(row) for row in (after_source_rows - common_sources).elements()
    ]
    removed_sources = [
        json.loads(row) for row in (before_source_rows - common_sources).elements()
    ]
    if (
        source_delta != (523, 7, 1)
        or len(after_sources) != 530
        or {
            row.get("provenance", {}).get("curated_record_key")
            for row in added_sources
        }
        != NEW_EVIDENCE_KEYS
        or Counter(row["source_family"] for row in added_sources)
        != Counter(row.source_family for row in REPLACEMENTS)
        or len(removed_sources) != 1
        or removed_sources[0].get("provenance", {}).get("curated_record_key")
        != REMOVED_PUBLIC_SOURCE_KEY
    ):
        raise OpenSeedV85Error("v85 public source-input delta differs")

    before_resolution = json.loads(
        (BASE_RELEASE / "resolution_candidates.json").read_text()
    )
    after_resolution = json.loads((stage / "resolution_candidates.json").read_text())
    before_resolution_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in before_resolution
    }
    after_resolution_rows = {
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in after_resolution
    }
    added_resolution = [
        json.loads(row) for row in after_resolution_rows - before_resolution_rows
    ]
    if (
        before_resolution_rows - after_resolution_rows
        or len(after_resolution) != 9
        or len(added_resolution) != 2
    ):
        raise OpenSeedV85Error("v85 resolution advisory delta differs")
    added_by_pair = {
        (row["left_name"], row["right_name"]): row for row in added_resolution
    }
    nextdc = added_by_pair.get(
        ("NEXTDC S4 Sydney Data Center Campus", "CDC Eastern Creek Campus")
    )
    data4 = added_by_pair.get(
        ("DATA4 ATH1 Paiania Campus", "Ten Brinke Spata Data Center")
    )
    if (
        set(added_by_pair)
        != {
            ("NEXTDC S4 Sydney Data Center Campus", "CDC Eastern Creek Campus"),
            ("DATA4 ATH1 Paiania Campus", "Ten Brinke Spata Data Center"),
        }
        or nextdc is None
        or data4 is None
        or (nextdc["distance_m"], nextdc["score"], nextdc["relationship_suggestion"])
        != (1596.601, 0.345469, "nearby_only")
        or nextdc["signals"]["name_similarity"] != 0.145455
        or (data4["distance_m"], data4["score"], data4["relationship_suggestion"])
        != (4029.121, 0.148476, "nearby_only")
        or any(
            "ATH04" in str(row.get(field) or "")
            for row in after_resolution
            for field in ("left_name", "right_name")
        )
        or any(
            {row.get("left_name"), row.get("right_name")}
            == {"AirTrunk SYD3 Western Sydney Campus", "CDC Eastern Creek Campus"}
            for row in after_resolution
        )
    ):
        raise OpenSeedV85Error("v85 new resolution advisories differ")
    resolution_csv = _csv_rows(stage / "resolution_candidates.csv")
    if len(resolution_csv) != 9 or {
        (row["left_entity_id"], row["right_entity_id"])
        for row in resolution_csv
    } != {
        (row["left_entity_id"], row["right_entity_id"])
        for row in after_resolution
    }:
        raise OpenSeedV85Error("v85 resolution CSV/JSON parity differs")

    before_atlas = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    after_atlas = json.loads((stage / "atlas.geojson").read_text())
    before_features = {
        row["properties"]["stable_key"]: row for row in before_atlas["features"]
    }
    after_features = {
        row["properties"]["stable_key"]: row for row in after_atlas["features"]
    }
    if set(before_features) != set(after_features) or len(after_features) != 917:
        raise OpenSeedV85Error("v85 atlas inventory differs")
    allowed_properties = {
        "latitude",
        "longitude",
        "snapshot_evidence_id",
        "source_attribution",
        "source_family",
        "source_license",
        "source_published_at",
        "source_publisher",
        "source_retrieved_at",
        "source_url",
    }
    changed_features: set[str] = set()
    for stable_key, prior in before_features.items():
        current = after_features[stable_key]
        if current == prior:
            continue
        changed_features.add(stable_key)
        if stable_key not in AFFECTED_ENTITY_KEYS or prior["geometry"] is not None:
            raise OpenSeedV85Error(f"v85 changed non-coordinate feature: {stable_key}")
        property_changes = {
            key
            for key in prior["properties"]
            if prior["properties"][key] != current["properties"][key]
        }
        restored = copy.deepcopy(current)
        restored["geometry"] = prior["geometry"]
        for key in property_changes:
            restored["properties"][key] = copy.deepcopy(prior["properties"][key])
        contract = contracts[stable_key]
        if (
            not property_changes <= allowed_properties
            or restored != prior
            or current["geometry"] != contract["geometry"]
            or current["properties"]["latitude"] != contract["latitude"]
            or current["properties"]["longitude"] != contract["longitude"]
            or current["properties"]["source_family"]
            != contract["source_family"]
        ):
            raise OpenSeedV85Error(f"v85 atlas coordinate differs: {stable_key}")
    if changed_features != set(AFFECTED_ENTITY_KEYS):
        raise OpenSeedV85Error("v85 changed atlas feature set differs")
    geometry_types = Counter(
        row["geometry"]["type"]
        for row in after_features.values()
        if row["geometry"] is not None
    )
    if geometry_types != {"Point": 133, "Polygon": 81, "MultiPolygon": 1}:
        raise OpenSeedV85Error("v85 GeoJSON geometry partition differs")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
    expected_summary = copy.deepcopy(base_summary)
    expected_summary.update(
        {
            "campuses_with_coordinates": 141,
            "entities_with_coordinates": 213,
            "evidence_total": 754,
            "recorded_at": recorded_at,
        }
    )
    expected_summary["evidence_by_kind"].update(
        {"company_disclosure": 557, "government_record": 119}
    )
    summary = json.loads((stage / "summary.json").read_text())
    if summary != expected_summary:
        raise OpenSeedV85Error("v85 full summary delta differs")

    base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
    manifest = json.loads((stage / "manifest.json").read_text())
    expected_manifest = {
        key: copy.deepcopy(value)
        for key, value in base_manifest.items()
        if key != "files"
    }
    expected_families = (
        set(base_manifest["source_families"])
        - {REMOVED_PUBLIC_SOURCE_FAMILY}
    ) | NEW_SOURCE_FAMILIES
    expected_manifest.update(
        {
            "evidence_records": 603,
            "geometry_only_representative_point_inferred": False,
            "recorded_at": recorded_at,
            "resolution_candidates": 9,
            "source_families": sorted(expected_families),
        }
    )
    if (
        {key: value for key, value in manifest.items() if key != "files"}
        != expected_manifest
        or len(manifest.get("source_families", [])) != 361
        or manifest.get("geometry_only_representative_point_inferred") is not False
    ):
        raise OpenSeedV85Error("v85 full manifest delta differs")

    freshness = _csv_rows(stage / FRESHNESS_FILENAME)
    if (
        len(freshness) != 512
        or tuple(freshness[0]) != FRESHNESS_FIELDS
        or any(
            row["status_semantics"] != "last_observed"
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] != "false"
            for row in freshness
        )
    ):
        raise OpenSeedV85Error("v85 freshness/current-status boundary differs")
    readme = (stage / "README.md").read_text()
    for marker in (
        COORDINATE_MANIFEST_PIN[1],
        COORDINATE_MANIFEST_TREE_SHA256,
        COORDINATE_PHYSICAL_TREE_SHA256,
        "Input cardinality\nand order remain 447",
        "official E31 project Polygon and E31+E26 campus MultiPolygon",
        "no polygon centroid or bounding-box\nmidpoint is published",
        "Marsden Park remains unchanged and review-only",
        "No identity, lifecycle, capacity, PUE, energy, consumption",
        "current_status_classification` remains `unknown",
        "current_construction_claim` remains `false",
    ):
        if marker not in readme:
            raise OpenSeedV85Error(f"v85 README guardrail differs: {marker}")
    if len(list(stage.iterdir())) != 14:
        raise OpenSeedV85Error("v85 release file inventory count differs")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV85Error("v85 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV85Error("v85 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV85Error("v85 as_of differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v85 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV85Error("v85 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV85Error(f"v85 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v85 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV85Error(f"v85 staged inode post-dates recorded_at: {path.name}")
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV85Error("v85 recorded_at is not live")
        for path in (definition, release):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV85Error(
                    f"v85 final root ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    if (
        v84.DEFINITION != BASE_DEFINITION
        or v84.RELEASE != BASE_RELEASE
        or guard["base_definition"] != BASE_DEFINITION_PIN
    ):
        raise OpenSeedV85Error("accepted v84 definition pin differs")
    if (
        guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise OpenSeedV85Error("accepted v84 release pin differs")
    if (
        guard["coordinate_manifest"] != COORDINATE_MANIFEST_PIN
        or guard["coordinate_tree"] != COORDINATE_PHYSICAL_TREE_SHA256
    ):
        raise OpenSeedV85Error("coordinate v6 artifact pin differs")
    if guard["predecessors"] != {
        row.predecessor_path: (row.predecessor_bytes, row.predecessor_sha256)
        for row in REPLACEMENTS
    } or guard["successors"] != {
        row.successor_path: (row.successor_bytes, row.successor_sha256)
        for row in REPLACEMENTS
    }:
        raise OpenSeedV85Error("v85 coordinate source pin differs")
    if guard["protected_indices"] != UNCHANGED_INDEX_PINS:
        raise OpenSeedV85Error("v85 protected index pin differs")


def validate_open_seed_v85(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV85Error("v85 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    _definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV85Error("v85 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV85Error("v85 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV85Error("v85 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV85Error("v85 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in release_files.values()
    ):
        raise OpenSeedV85Error("v85 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get(
        "manifest_sha256"
    ):
        raise OpenSeedV85Error("v85 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {key: value for key, value in manifest.items() if key != "files"} != expected_release:
        raise OpenSeedV85Error("v85 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV85Error("v85 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV85Error(f"v85 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_delta(release_path, recorded_at=recorded_at)
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV85Error("v85 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v85-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                replay_release = root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_delta(replay_release, recorded_at=recorded_at)
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV85Error("v85 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV85Error(f"v85 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV85Error("v85 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode)
        if directory
        else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        raise OpenSeedV85Error(f"v85 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {
        path.name: _path_identity(path, directory=False) for path in root.iterdir()
    }


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV85Error("v85 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV85Error("v85 release stage member identity changed")


def _discard_release_stage(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_release_identities(root, root_identity, members)
    root.chmod(0o700)
    for path in root.iterdir():
        path.chmod(0o600)
        path.unlink()
    root.rmdir()


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _path_identity(path, directory=False) != identity:
        raise OpenSeedV85Error("refusing substituted v85 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV85Error("active v85 publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != identity:
                raise OpenSeedV85Error("refusing substituted v85 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV85Error(f"{label} v85 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV85Error(f"{label} v85 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV85Error("refusing rollback of substituted v85 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV85Error("v85 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def build_open_seed_v85(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the coordinate-only v84 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v85()
        return {
            "definition": str(DEFINITION),
            "definition_sha256": v69.sha256(DEFINITION),
            "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "release": str(RELEASE),
            "release_tree_sha256": v69.tree_digest(RELEASE),
            "status": "existing-identical",
        }
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
    ):
        raise OpenSeedV85Error("partial v85 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v85 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV85Error("v85 recorded_at must be future before staging")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")

    with _publication_lock():
        _require_absent("initial")
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.", suffix=".stage", dir=DEFINITION.parent
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        release_identity = _path_identity(release_stage, directory=True)
        release_members: dict[str, tuple[int, int]] = {}
        published_release = False
        published_definition = False
        try:
            os.close(descriptor)
            base = json.loads(BASE_DEFINITION.read_text())
            input_rows, paths = selected_inputs(
                base, recorded_at=recorded_at, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v85-db-", dir="/private/tmp"
            ) as temporary_database:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary_database) / "atlas.sqlite",
                    recorded_at=recorded_at,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=recorded_at
                    )
                finally:
                    connection.close()
            _validate_release_delta(release_stage, recorded_at=recorded_at)
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = _sha256(manifest_raw)
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            _fsync(definition_stage)
            for path in release_stage.iterdir():
                path.chmod(0o444)
                _fsync(path)
            release_stage.chmod(0o555)
            _fsync(release_stage)
            release_members = _release_identities(release_stage)
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            _require_absent("pre-wait")
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_absent("late")
            if _path_identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV85Error("v85 definition stage identity changed")
            _assert_release_identities(
                release_stage, release_identity, release_members
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV85Error("v85 private stage changed while waiting")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            try:
                v69.promote_noreplace(definition_stage, DEFINITION)
                published_definition = True
            except BaseException as error:
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v85 release rollback failed: {rollback_error}")
                raise
            manifest = validate_open_seed_v85(DEFINITION, RELEASE)
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    shutil.rmtree(release_stage)
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV85Error("v85 build mutated accepted inputs")
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build_open_seed_v85(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
