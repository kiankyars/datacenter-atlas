"""Opt-in, additive v0.18 DRAFT builder. The public CLI remains on v0.17.

Two phases are intentionally separate:

1. ``validate_batch(contract_path, review_pins, root=ROOT)`` checks independently
   reviewed input pins, exact source facts, the fixed lifecycle cutoff, geometry
   semantics, and distinct-campus review. It returns a validated batch without
   writing anything or declaring the 200-site objective complete.
2. ``build_draft(contract_path, review_pins, output_dir, root=ROOT)`` derives all
   rows and denominators, validates a staged reconstruction, then publishes a
   new local draft directory. ``validate_draft`` reconstructs every output byte.
   All inherited CSV bytes and GeoJSON features remain unchanged. No default
   artifact, public CLI, baseline file, or researched candidate is modified.

Contract schema ``datacenter-atlas-v018-reviewed-batch-v1`` (all keys shown are
required; unrecognized keys at these levels are rejected):

    {
      "schema_version": "datacenter-atlas-v018-reviewed-batch-v1",
      "batch_id": "a-reviewed-batch-name",
      "base_preview_manifest_sha256": BASELINE_MANIFEST_SHA256,
      "lifecycle_reference_date": "2026-08-20",
      "geometry_identity_reviewed_at": "YYYY-MM-DD",
      "sources": [{
        "source_id": "status-source",
        "path": "sources/a-curated-file.json",
        "bytes": 1234, "sha256": "64 lower-case hex characters",
        "evidence_pointer": "/evidence/0", "evidence_sha256": "..."
      }],
      "acceptances": [{
        "project_stable_key": "curated:example:phase-1",
        "parent_campus_stable_key": "curated:example",
        "country_iso_a2": "US",
        "identity": {
          "source_id": "status-source",
          "project_pointer": "/project", "project_sha256": "...",
          "campus_pointer": "/campus", "campus_sha256": "..."
        },
        "status": {
          "source_id": "status-source", "record_pointer": "/lifecycle/0",
          "record_sha256": "..."
        },
        "geometry": {
          "source_id": "geometry-source", "record_pointer": "/results/0",
          "record_sha256": "..."
        },
        "distinctness_review": {
          "decision": "distinct_physical_site",
          "scope": "single_physical_site",
          "equivalent_campus_keys": ["curated:example"],
          "baseline_site_keys_sha256": "...",
          "batch_site_keys_sha256": "...",
          "evidence_source_ids": ["status-source", "geometry-source"],
          "reason": "Source-grounded physical-site and alias adjudication."
        }
      }]
    }

``ReviewPins(contract_sha256, source_sha256, acceptance_sha256)`` is supplied
separately by reviewed code, not loaded from this contract. Its maps bind every
source-spec row by source_id and every acceptance row by project_stable_key.
All record/row hashes use ``canonical_sha256``: sorted compact UTF-8 JSON plus
one newline. File hashes use exact bytes. Campus-key-set hashes use sorted lists
through ``canonical_sha256``. Review pins must never be automatically refreshed
to make a validation error disappear.

Source evidence objects use the existing curated shape: key, kind, title,
source_url, publisher, source_family, license, attribution, published_at (ISO date,
ISO datetime, or null), retrieved_at, content_hash; extra source metadata is
hash-preserved without normalizing a source publication timestamp.
Identity pointers select literal project/campus objects with stable_key, name,
country. Status selects a literal project lifecycle row with value, as_of_date,
method, evidence_key. Evidence IDs are derived from curated key/content_hash.

A geometry record has exactly project_stable_key, parent_campus_stable_key,
geometry, display_anchor, geometry_source_ids, identity_source_ids,
location_basis, and semantics. Geometry supports Point, Polygon, MultiPolygon.
The anchor is a Point; it must equal a Point geometry or lie within a polygon.
Semantics has exactly geometry_source_entity_kind, geometry_derivation,
geometry_method, geometry_scope_class, geometry_authority_class,
geometry_use_scope, precision_scope, horizontal_uncertainty_metres, and
horizontal_uncertainty_unknown_reason. ``LOCATION_BASES`` and ``USE_SCOPES``
document the allowed evidence/semantic classes. Locality centroids are excluded.

Every acceptance is one project on one NEW physical campus. Additional projects
on an already represented site require a different, explicitly reviewed update
workflow, not this expansion path. Alias sets must not collide with the baseline
or another acceptance. Exact coincident anchors fail closed. Geographic alias
review is still a human/source judgment: hashes cannot establish physical truth.
Shared evidence within the delta is supported; baseline evidence IDs may not be
reused because their inherited usage rows must remain byte-for-byte unchanged.

Draft output is CSV/GeoJSON plus provenance/report/schema/attribution and manifest.
No public map is generated. Target-count achievement and final-publication
eligibility are separate: this builder ALWAYS labels its output draft and
publishable_as_final=false, including at 200 or more sites. Imagery and blind
review gates are derived from retained rows/review records, never from a constant
success claim. No roles, workload, capacity, efficiency, or energy are inferred.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urlsplit

from . import verified_construction_core_v017 as v17


core = v17.v16
ROOT = v17.ROOT
BASELINE_RELATIVE_DIR = "verified_construction_core/2026-08-20-preview-v0.17"
BASELINE_MANIFEST_SHA256 = (
    "49cf79185742a2bd718a83683c924574ba8db4de1289d1228e56c5865154c8fc"
)
SCHEMA_VERSION = "datacenter-atlas-v018-reviewed-batch-v1"
LIFECYCLE_REFERENCE_DATE = date(2026, 8, 20)
TARGET_ADDITIONAL_SITES = 100
LOCATION_BASES = frozenset(
    {
        "first_party_site_coordinate",
        "official_address_geocode",
        "official_named_site_feature",
        "official_parcel",
        "community_named_site_feature",
        "authoritative_site_boundary",
    }
)
USE_SCOPES = frozenset(
    {"campus_locator", "project_locator", "reviewed_site_locator", "official_boundary"}
)
SEMANTIC_FIELDS = frozenset(
    {
        "geometry_source_entity_kind",
        "geometry_derivation",
        "geometry_method",
        "geometry_scope_class",
        "geometry_authority_class",
        "geometry_use_scope",
        "precision_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
    }
)
ISO_A2_CODES = frozenset(
    """
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ
BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM
DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS
GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN
KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM
PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV
SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI
VN VU WF WS YE YT ZA ZM ZW
""".split()
)


class DraftValidationError(core.VerifiedConstructionCoreError):
    """A reviewed input or draft invariant is missing or inconsistent."""


@dataclass(frozen=True)
class ReviewPins:
    contract_sha256: str
    source_sha256: Mapping[str, str]
    acceptance_sha256: Mapping[str, str]


@dataclass(frozen=True)
class ValidatedBatch:
    root: Path
    contract_path: Path
    pins: ReviewPins
    contract: dict[str, Any]
    baseline: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    acceptances: tuple[dict[str, Any], ...]


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(core._json_bytes(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DraftValidationError(message)


def _keys(
    value: Any, expected: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    _require(
        isinstance(value, dict) and set(value) == set(expected), f"{label} keys differ"
    )
    return value


def _text(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text"
    )
    return value


def _hash(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"{label} is not SHA-256",
    )
    return value


def _calendar(value: Any, label: str) -> date:
    _require(
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
        f"{label} must be YYYY-MM-DD",
    )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DraftValidationError(f"invalid {label}") from exc


def _unique_text(values: Any, label: str, *, empty: bool = False) -> list[str]:
    _require(
        isinstance(values, list) and (empty or bool(values)), f"{label} must be a list"
    )
    for value in values:
        _text(value, label)
    _require(len(values) == len(set(values)), f"duplicate {label}")
    return values


def _portable_path(root: Path, relative: Any, label: str) -> Path:
    _text(relative, label)
    parts = Path(relative)
    _require(
        not parts.is_absolute() and ".." not in parts.parts and "." not in parts.parts,
        f"nonportable {label}",
    )
    _require(
        parts.as_posix() == relative and bool(parts.parts), f"noncanonical {label}"
    )
    path = root / parts
    _require(path.resolve().is_relative_to(root.resolve()), f"{label} escapes root")
    cursor = root
    for part in parts.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"symlink in {label}")
    return path


def _read_pinned(path: Path, expected_sha256: str, size: int | None = None) -> bytes:
    _hash(expected_sha256, str(path))
    _require(not path.is_symlink() and path.is_file(), f"missing regular input: {path}")
    data = path.read_bytes()
    _require(
        hashlib.sha256(data).hexdigest() == expected_sha256,
        f"input SHA-256 differs: {path}",
    )
    if size is not None:
        _require(
            type(size) is int and size >= 0 and len(data) == size,
            f"input byte count differs: {path}",
        )
    return data


def _json(data: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            _require(key not in result, f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise DraftValidationError(f"nonfinite JSON in {label}: {value}")

    try:
        return json.loads(
            data, object_pairs_hook=pairs, parse_constant=invalid_constant
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise DraftValidationError(f"invalid JSON: {label}") from exc


def _pointer(document: Any, pointer: Any) -> Any:
    _require(
        isinstance(pointer, str) and (pointer == "" or pointer.startswith("/")),
        "invalid JSON pointer",
    )
    current = document
    for token in pointer.split("/")[1:]:
        _require(re.search(r"~(?![01])", token) is None, "invalid JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            _require(token in current, f"JSON pointer missing: {pointer}")
            current = current[token]
        elif isinstance(current, list):
            _require(
                re.fullmatch(r"0|[1-9][0-9]*", token) is not None,
                "invalid JSON pointer array index",
            )
            index = int(token)
            _require(index < len(current), f"JSON pointer outside array: {pointer}")
            current = current[index]
        else:
            raise DraftValidationError(f"JSON pointer crosses a scalar: {pointer}")
    return current


def _record(
    sources: Mapping[str, Any], source_id: str, pointer: str, digest: str, label: str
) -> dict[str, Any]:
    _require(source_id in sources, f"unbound {label} source: {source_id}")
    value = _pointer(sources[source_id]["document"], pointer)
    _require(isinstance(value, dict), f"{label} is not an object")
    _require(
        canonical_sha256(value) == _hash(digest, label),
        f"{label} record SHA-256 differs",
    )
    return value


def _load_baseline(root: Path) -> dict[str, Any]:
    directory = _portable_path(root, BASELINE_RELATIVE_DIR, "baseline path")
    raw_manifest = _read_pinned(directory / "manifest.json", BASELINE_MANIFEST_SHA256)
    manifest = _json(raw_manifest, "baseline manifest")
    _require(
        manifest["counts"]["physical_sites"] == 100
        and manifest["counts"]["projects"] == 103,
        "frozen baseline counts differ",
    )
    expected_checksum = f"{BASELINE_MANIFEST_SHA256}  manifest.json\n".encode()
    checksum = directory / "manifest.sha256"
    _require(
        not checksum.is_symlink()
        and checksum.is_file()
        and checksum.read_bytes() == expected_checksum,
        "baseline manifest checksum differs",
    )
    files = {}
    for name, spec in manifest["files"].items():
        _require(Path(name).name == name, "invalid baseline member")
        files[name] = _read_pinned(directory / name, spec["sha256"], spec["bytes"])
    _require(
        {path.name for path in directory.iterdir()}
        == set(files) | {"manifest.json", "manifest.sha256"},
        "baseline file inventory differs",
    )
    tables = {
        name: core._load_csv(directory / f"{name}.csv", fields)
        for name, fields in (
            ("projects", core.PROJECT_FIELDS),
            ("sites", core.SITE_FIELDS),
            ("evidence", core.EVIDENCE_FIELDS),
        )
    }
    _require(
        len(tables["sites"]) == 100 and len(tables["projects"]) == 103,
        "baseline table counts differ",
    )
    return {"manifest": manifest, "files": files, **tables}


def _source_evidence(evidence: Any, label: str) -> dict[str, Any]:
    _require(isinstance(evidence, dict), f"{label} evidence is not an object")
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
    ):
        _text(evidence.get(field), f"{label} evidence {field}")
    _hash(evidence.get("content_hash"), f"{label} content hash")
    url = urlsplit(evidence["source_url"])
    _require(
        url.scheme in {"https", "http"}
        and bool(url.hostname)
        and not url.username
        and not url.password,
        f"invalid {label} source URL",
    )
    try:
        retrieved = datetime.fromisoformat(
            evidence["retrieved_at"].replace("Z", "+00:00")
        )
        _require(retrieved.tzinfo is not None, f"{label} retrieval needs timezone")
    except ValueError as exc:
        raise DraftValidationError(f"invalid {label} retrieval timestamp") from exc
    _require(
        "published_at" in evidence, f"{label} publication date must be explicit or null"
    )
    if evidence["published_at"] is not None:
        publication_text = _text(evidence["published_at"], f"{label} publication date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_text):
            publication_day = _calendar(publication_text, f"{label} publication date")
            publication_precedes_retrieval = publication_day <= retrieved.date()
        else:
            _require(
                re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", publication_text)
                is not None,
                f"invalid {label} publication datetime",
            )
            try:
                publication_time = datetime.fromisoformat(
                    publication_text.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise DraftValidationError(
                    f"invalid {label} publication datetime"
                ) from exc
            # Preserve timezone-free source values without inventing a timezone.
            publication_precedes_retrieval = (
                publication_time <= retrieved
                if publication_time.tzinfo is not None
                else publication_time.date() <= retrieved.date()
            )
        _require(
            publication_precedes_retrieval,
            f"{label} publication follows retrieval",
        )
    identifier = core.atlas_stable_id(
        "evidence", "curated-official", evidence["key"], evidence["content_hash"]
    )
    return core._v07_evidence_projection({**evidence, "evidence_id": identifier})


def _point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(
            type(number) in {int, float} and math.isfinite(number) for number in value
        )
        and -180 <= value[0] <= 180
        and -90 <= value[1] <= 90
    )


def _ring(value: Any) -> bool:
    if not (
        isinstance(value, list)
        and len(value) >= 4
        and all(_point(point) for point in value)
        and value[0] == value[-1]
    ):
        return False
    if len({tuple(point) for point in value[:-1]}) != len(value) - 1:
        return False
    segments = list(zip(value, value[1:]))
    for index, (a, b) in enumerate(segments):
        for other_index, (c, d) in enumerate(segments):
            if other_index <= index + 1 or (
                index == 0 and other_index == len(segments) - 1
            ):
                continue
            if _segments_intersect(a, b, c, d):
                return False
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in segments)) > 1e-15


def _segments_intersect(a: list, b: list, c: list, d: list) -> bool:
    def side(p: list, q: list, r: list) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p: list, q: list, r: list) -> bool:
        return (
            abs(side(p, q, r)) < 1e-12
            and min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
            and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        )

    orientations = side(a, b, c), side(a, b, d), side(c, d, a), side(c, d, b)
    return (
        (
            orientations[0] * orientations[1] < 0
            and orientations[2] * orientations[3] < 0
        )
        or on_segment(a, b, c)
        or on_segment(a, b, d)
        or on_segment(c, d, a)
        or on_segment(c, d, b)
    )


def _inside_ring(point: list[float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if (
            abs(cross) < 1e-12
            and min(ax, bx) <= x <= max(ax, bx)
            and min(ay, by) <= y <= max(ay, by)
        ):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _geometry(record: dict[str, Any]) -> None:
    _keys(
        record,
        {
            "project_stable_key",
            "parent_campus_stable_key",
            "geometry",
            "display_anchor",
            "geometry_source_ids",
            "identity_source_ids",
            "location_basis",
            "semantics",
        },
        "geometry record",
    )
    geometry = _keys(record["geometry"], {"type", "coordinates"}, "geometry")
    anchor = _keys(record["display_anchor"], {"type", "coordinates"}, "display anchor")
    _require(
        anchor["type"] == "Point" and _point(anchor["coordinates"]),
        "invalid display anchor",
    )
    kind, coordinates = geometry["type"], geometry["coordinates"]
    _require(kind in {"Point", "Polygon", "MultiPolygon"}, "unsupported geometry type")
    if kind == "Point":
        _require(
            _point(coordinates) and coordinates == anchor["coordinates"],
            "Point display anchor differs",
        )
    else:
        polygons = [coordinates] if kind == "Polygon" else coordinates
        _require(
            isinstance(polygons, list) and bool(polygons), "empty polygon geometry"
        )
        for polygon in polygons:
            _require(
                isinstance(polygon, list)
                and bool(polygon)
                and all(_ring(ring) for ring in polygon),
                "invalid or degenerate polygon ring",
            )
            _require(
                all(
                    abs(a[0] - b[0]) <= 180
                    for ring in polygon
                    for a, b in zip(ring, ring[1:])
                ),
                "antimeridian polygon requires separate review support",
            )
            for index, ring in enumerate(polygon):
                if index:
                    _require(
                        _inside_ring(ring[0], polygon[0]),
                        "polygon hole lies outside exterior",
                    )
                for other in polygon[index + 1 :]:
                    _require(
                        not any(
                            _segments_intersect(a, b, c, d)
                            for a, b in zip(ring, ring[1:])
                            for c, d in zip(other, other[1:])
                        ),
                        "polygon rings intersect",
                    )
                    if index:
                        _require(
                            not _inside_ring(ring[0], other)
                            and not _inside_ring(other[0], ring),
                            "polygon holes overlap",
                        )
        _require(
            any(
                _inside_ring(anchor["coordinates"], polygon[0])
                and not any(
                    _inside_ring(anchor["coordinates"], hole) for hole in polygon[1:]
                )
                for polygon in polygons
            ),
            "polygon display anchor is outside its geometry",
        )
    semantics = _keys(record["semantics"], SEMANTIC_FIELDS, "geometry semantics")
    for field in SEMANTIC_FIELDS - {
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
    }:
        _text(semantics[field], f"geometry semantics {field}")
    _require(
        isinstance(record["location_basis"], str)
        and record["location_basis"] in LOCATION_BASES,
        "unsupported location basis; locality centroids are not accepted",
    )
    _require(
        semantics["geometry_source_entity_kind"] in {"project", "campus"},
        "geometry entity scope differs",
    )
    _require(
        semantics["geometry_authority_class"]
        in {"official_source", "community_source"},
        "geometry authority differs",
    )
    _require(
        semantics["geometry_use_scope"] in USE_SCOPES, "geometry use scope differs"
    )
    boundary = semantics["geometry_use_scope"] == "official_boundary"
    _require(
        boundary == (record["location_basis"] == "authoritative_site_boundary"),
        "boundary evidence/semantics differ",
    )
    if boundary:
        _require(
            kind in {"Polygon", "MultiPolygon"}
            and semantics["geometry_authority_class"] == "official_source",
            "official boundary requires official polygon evidence",
        )
    if record["location_basis"] == "community_named_site_feature":
        _require(
            semantics["geometry_authority_class"] == "community_source",
            "community geometry promoted to official",
        )
    else:
        _require(
            semantics["geometry_authority_class"] == "official_source",
            "official location basis has nonofficial authority",
        )
    uncertainty = semantics["horizontal_uncertainty_metres"]
    reason = semantics["horizontal_uncertainty_unknown_reason"]
    if uncertainty is None:
        _text(reason, "unknown horizontal uncertainty reason")
    else:
        _require(
            type(uncertainty) in {int, float}
            and math.isfinite(uncertainty)
            and uncertainty > 0
            and reason == "",
            "numeric uncertainty/reason differs",
        )


def validate_batch(
    contract_path: Path, review_pins: ReviewPins, *, root: Path = ROOT
) -> ValidatedBatch:
    """Phase one: read-only validation against independently supplied review pins."""
    supplied_root = Path(root).absolute()
    root = supplied_root.resolve()
    contract_path = Path(contract_path)
    if not contract_path.is_absolute():
        relative_contract = contract_path
    elif contract_path.is_relative_to(supplied_root):
        relative_contract = contract_path.relative_to(supplied_root)
    else:
        _require(contract_path.is_relative_to(root), "contract must be inside root")
        relative_contract = contract_path.relative_to(root)
    contract_path = _portable_path(root, relative_contract.as_posix(), "contract path")
    contract = _json(
        _read_pinned(contract_path, review_pins.contract_sha256), "batch contract"
    )
    _keys(
        contract,
        {
            "schema_version",
            "batch_id",
            "base_preview_manifest_sha256",
            "lifecycle_reference_date",
            "geometry_identity_reviewed_at",
            "sources",
            "acceptances",
        },
        "batch contract",
    )
    _require(
        contract["schema_version"] == SCHEMA_VERSION, "batch schema version differs"
    )
    _require(
        re.fullmatch(
            r"[a-z0-9][a-z0-9-]{0,95}", _text(contract["batch_id"], "batch ID")
        )
        is not None,
        "unsafe batch ID",
    )
    _require(
        contract["base_preview_manifest_sha256"] == BASELINE_MANIFEST_SHA256,
        "batch baseline pin differs",
    )
    _require(
        contract["lifecycle_reference_date"] == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "lifecycle cutoff cannot move",
    )
    reviewed_at = _calendar(
        contract["geometry_identity_reviewed_at"], "geometry review date"
    )
    _require(
        reviewed_at >= LIFECYCLE_REFERENCE_DATE,
        "geometry review predates lifecycle cutoff",
    )
    baseline = _load_baseline(root)
    base_campuses = {row["physical_site_stable_key"] for row in baseline["sites"]}
    base_projects = {row["project_stable_key"] for row in baseline["projects"]}
    base_evidence = {row["evidence_id"] for row in baseline["evidence"]}
    source_specs = contract["sources"]
    _require(
        isinstance(source_specs, list) and bool(source_specs), "batch sources missing"
    )
    sources = {}
    evidence_by_id = {}
    for spec in source_specs:
        _keys(
            spec,
            {
                "source_id",
                "path",
                "bytes",
                "sha256",
                "evidence_pointer",
                "evidence_sha256",
            },
            "source spec",
        )
        source_id = _text(spec["source_id"], "source ID")
        _require(source_id not in sources, "duplicate source ID")
        _require(
            canonical_sha256(spec) == review_pins.source_sha256.get(source_id),
            f"independent source review pin differs: {source_id}",
        )
        path = _portable_path(root, spec["path"], "source path")
        _require(
            Path(spec["path"]).parts[0] == "sources", "source must be under sources/"
        )
        document = _json(_read_pinned(path, spec["sha256"], spec["bytes"]), source_id)
        evidence = _pointer(document, spec["evidence_pointer"])
        _require(
            canonical_sha256(evidence)
            == _hash(spec["evidence_sha256"], "evidence record hash"),
            "evidence record SHA-256 differs",
        )
        projection = _source_evidence(evidence, source_id)
        identifier = projection["evidence_id"]
        _require(
            identifier not in base_evidence,
            "baseline evidence ID reuse would alter frozen usage rows",
        )
        _require(
            identifier not in evidence_by_id or evidence_by_id[identifier] == evidence,
            "conflicting evidence with the same derived ID",
        )
        evidence_by_id[identifier] = evidence
        retrieval_day = datetime.fromisoformat(
            evidence["retrieved_at"].replace("Z", "+00:00")
        ).date()
        _require(
            retrieval_day <= reviewed_at,
            "source retrieval follows geometry-identity review",
        )
        sources[source_id] = {
            "spec": spec,
            "document": document,
            "evidence": evidence,
            "projection": projection,
        }
    _require(
        set(sources) == set(review_pins.source_sha256),
        "source review pin inventory differs",
    )
    acceptances = contract["acceptances"]
    _require(
        isinstance(acceptances, list) and bool(acceptances), "batch acceptances missing"
    )
    campus_keys = [
        _text(item.get("parent_campus_stable_key"), "parent campus key")
        for item in acceptances
        if isinstance(item, dict)
    ]
    _require(
        len(campus_keys) == len(acceptances)
        and len(campus_keys) == len(set(campus_keys)),
        "duplicate or invalid batch campus",
    )
    batch_keys_sha = canonical_sha256(sorted(campus_keys))
    base_keys_sha = canonical_sha256(sorted(base_campuses))
    aliases_seen: set[str] = set(base_campuses)
    anchors_seen = {
        (float(row["longitude"]), float(row["latitude"])) for row in baseline["sites"]
    }
    projects_seen = set(base_projects)
    countries = {row["country"]: row["country_iso_a2"] for row in baseline["sites"]}
    names_by_iso = {iso: name for name, iso in countries.items()}
    used_sources: set[str] = set()
    validated = []
    for acceptance in acceptances:
        _keys(
            acceptance,
            {
                "project_stable_key",
                "parent_campus_stable_key",
                "country_iso_a2",
                "identity",
                "status",
                "geometry",
                "distinctness_review",
            },
            "acceptance",
        )
        project_key = _text(acceptance["project_stable_key"], "project key")
        campus_key = acceptance["parent_campus_stable_key"]
        _require(project_key not in projects_seen, "duplicate or baseline project key")
        projects_seen.add(project_key)
        _require(
            canonical_sha256(acceptance)
            == review_pins.acceptance_sha256.get(project_key),
            f"independent acceptance review pin differs: {project_key}",
        )
        identity = _keys(
            acceptance["identity"],
            {
                "source_id",
                "project_pointer",
                "project_sha256",
                "campus_pointer",
                "campus_sha256",
            },
            "identity binding",
        )
        project = _record(
            sources,
            identity["source_id"],
            identity["project_pointer"],
            identity["project_sha256"],
            "project identity",
        )
        campus = _record(
            sources,
            identity["source_id"],
            identity["campus_pointer"],
            identity["campus_sha256"],
            "campus identity",
        )
        _require(
            project.get("stable_key") == project_key
            and campus.get("stable_key") == campus_key,
            "source project/campus identity differs",
        )
        _text(project.get("name"), "project name")
        _text(campus.get("name"), "campus name")
        country = _text(project.get("country"), "project country")
        _require(campus.get("country") == country, "campus/project country differs")
        iso = acceptance["country_iso_a2"]
        _require(
            isinstance(iso, str) and iso in ISO_A2_CODES, "invalid ISO alpha-2 code"
        )
        _require(
            countries.get(country, iso) == iso
            and names_by_iso.get(iso, country) == country,
            "country/ISO mapping conflicts",
        )
        countries[country] = iso
        names_by_iso[iso] = country
        for entity in (project, campus):
            _require(
                entity.get("country_iso_a2", iso) == iso, "source country ISO differs"
            )
        status_binding = _keys(
            acceptance["status"],
            {"source_id", "record_pointer", "record_sha256"},
            "status binding",
        )
        status = _record(
            sources,
            status_binding["source_id"],
            status_binding["record_pointer"],
            status_binding["record_sha256"],
            "status",
        )
        _require(
            status.get("entity") == "project"
            and isinstance(status.get("value"), str)
            and status["value"] in core.PHYSICAL_STATUSES
            and isinstance(status.get("method"), str)
            and status["method"] in core.AUTHORITATIVE_STATUS_METHODS,
            "status is not authoritative physical work",
        )
        age = (
            LIFECYCLE_REFERENCE_DATE
            - _calendar(status.get("as_of_date"), "status date")
        ).days
        _require(0 <= age <= 90, "status outside fixed 90-day window")
        _require(
            status.get("evidence_key")
            == sources[status_binding["source_id"]]["evidence"]["key"],
            "status evidence key differs",
        )
        status_source_project = sources[status_binding["source_id"]]["document"].get(
            "project"
        )
        _require(
            isinstance(status_source_project, dict)
            and status_source_project.get("stable_key") == project_key,
            "status source does not bind exact project",
        )
        status_source_campus = sources[status_binding["source_id"]]["document"].get(
            "campus"
        )
        _require(
            isinstance(status_source_campus, dict)
            and status_source_campus.get("stable_key") == campus_key,
            "status source does not bind exact campus",
        )
        geometry_binding = _keys(
            acceptance["geometry"],
            {"source_id", "record_pointer", "record_sha256"},
            "geometry binding",
        )
        geometry = _record(
            sources,
            geometry_binding["source_id"],
            geometry_binding["record_pointer"],
            geometry_binding["record_sha256"],
            "geometry",
        )
        _geometry(geometry)
        _require(
            geometry["project_stable_key"] == project_key
            and geometry["parent_campus_stable_key"] == campus_key,
            "geometry project/campus identity differs",
        )
        geometry_ids = _unique_text(
            geometry["geometry_source_ids"], "geometry source IDs"
        )
        identity_ids = _unique_text(
            geometry["identity_source_ids"], "geometry identity source IDs"
        )
        _require(
            geometry_binding["source_id"] in geometry_ids,
            "primary geometry source is not a geometry evidence source",
        )
        _require(
            identity["source_id"] in identity_ids,
            "identity source missing from geometry identity bindings",
        )
        anchor = tuple(
            float(value) for value in geometry["display_anchor"]["coordinates"]
        )
        _require(
            anchor not in anchors_seen,
            "coincident baseline/batch locator needs duplicate-site adjudication",
        )
        anchors_seen.add(anchor)
        review = _keys(
            acceptance["distinctness_review"],
            {
                "decision",
                "scope",
                "equivalent_campus_keys",
                "baseline_site_keys_sha256",
                "batch_site_keys_sha256",
                "evidence_source_ids",
                "reason",
            },
            "distinctness review",
        )
        _require(
            review["decision"] == "distinct_physical_site"
            and review["scope"] == "single_physical_site",
            "distinct physical-site scope not resolved",
        )
        aliases = set(
            _unique_text(review["equivalent_campus_keys"], "equivalent campus keys")
        )
        _require(
            campus_key in aliases and not aliases.intersection(aliases_seen),
            "campus alias duplicates baseline or batch site",
        )
        aliases_seen.update(aliases)
        _require(
            review["baseline_site_keys_sha256"] == base_keys_sha
            and review["batch_site_keys_sha256"] == batch_keys_sha,
            "distinctness review comparison set differs",
        )
        review_sources = _unique_text(
            review["evidence_source_ids"], "distinctness evidence IDs"
        )
        _require(
            identity["source_id"] in review_sources
            and bool(set(geometry_ids).intersection(review_sources)),
            "distinctness review lacks identity and geometry evidence",
        )
        _text(review["reason"], "distinctness decision reason")
        used = set(
            geometry_ids
            + identity_ids
            + review_sources
            + [identity["source_id"], status_binding["source_id"]]
        )
        _require(used.issubset(sources), "unbound acceptance source ID")
        used_sources.update(used)
        validated.append(
            {
                "acceptance": acceptance,
                "project": project,
                "campus": campus,
                "status": status,
                "geometry": geometry,
            }
        )
    _require(
        set(review_pins.acceptance_sha256) == projects_seen - base_projects,
        "acceptance review pin inventory differs",
    )
    _require(used_sources == set(sources), "unused source documents are not allowed")
    return ValidatedBatch(
        root, contract_path, review_pins, contract, baseline, sources, tuple(validated)
    )


def _delta_rows(batch: ValidatedBatch) -> dict[str, list[dict[str, Any]]]:
    projects = []
    sites = []
    evidence_pool = {}
    usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "projects": set()}
    )
    for item in sorted(
        batch.acceptances, key=lambda value: value["acceptance"]["project_stable_key"]
    ):
        acceptance, project, campus, status, locator = (
            item[key]
            for key in ("acceptance", "project", "campus", "status", "geometry")
        )
        key, campus_key = (
            acceptance["project_stable_key"],
            acceptance["parent_campus_stable_key"],
        )
        project_id = core.atlas_stable_id("entity", key, "project")
        site_id = core._stable_id("vcc-site", campus_key)
        primary_geometry_id = acceptance["geometry"]["source_id"]
        status_source_id = acceptance["status"]["source_id"]
        roles_by_source: dict[str, set[str]] = defaultdict(set)
        roles_by_source[status_source_id].add("physical_status")
        for source_id in locator["geometry_source_ids"]:
            roles_by_source[source_id].add("geometry")
        for source_id in locator["identity_source_ids"]:
            roles_by_source[source_id].add("context:geometry_identity")
        for source_id in acceptance["distinctness_review"]["evidence_source_ids"]:
            roles_by_source[source_id].add("context:site_distinctness")
        for source_id, roles in roles_by_source.items():
            evidence = batch.sources[source_id]["projection"]
            identifier = evidence["evidence_id"]
            evidence_pool[identifier] = evidence
            usage[identifier]["roles"].update(roles)
            usage[identifier]["projects"].add(project_id)
        semantics = locator["semantics"]
        geometry = locator["geometry"]
        longitude, latitude = locator["display_anchor"]["coordinates"]
        uncertainty = semantics["horizontal_uncertainty_metres"]
        row = {field: "" for field in core.PROJECT_FIELDS}
        row.update(
            {
                "project_id": project_id,
                "project_stable_key": key,
                "site_id": site_id,
                "physical_site_stable_key": campus_key,
                "name": project["name"],
                "country": project["country"],
                "country_iso_a2": acceptance["country_iso_a2"],
                "latitude": latitude,
                "longitude": longitude,
                "geometry_json": core._json_bytes(geometry).decode().strip(),
                "geometry_type": geometry["type"],
                **{
                    field: semantics[field]
                    for field in SEMANTIC_FIELDS
                    if field.startswith("geometry_")
                },
                "geometry_precision_scope": semantics["precision_scope"],
                "horizontal_uncertainty_metres": ""
                if uncertainty is None
                else uncertainty,
                "horizontal_uncertainty_unknown_reason": semantics[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "geometry_evidence_id": batch.sources[primary_geometry_id][
                    "projection"
                ]["evidence_id"],
                "last_observed_physical_status": status["value"],
                "status_as_of": status["as_of_date"],
                "status_age_days_at_review": (
                    LIFECYCLE_REFERENCE_DATE - date.fromisoformat(status["as_of_date"])
                ).days,
                "status_method": status["method"],
                "status_evidence_id": batch.sources[status_source_id]["projection"][
                    "evidence_id"
                ],
                "verification_posture": core._verification_posture(
                    semantics["geometry_authority_class"],
                    semantics["geometry_use_scope"],
                ),
                "independent_imagery_verification": "false",
                "imagery_review_outcome": "not_reviewed_for_core_preview",
                "development_type": "unknown",
                "development_type_unknown_reason": "not selected by this reviewed draft batch",
                "operating_model": "unknown",
                "operating_model_unknown_reason": "not established by selected evidence",
                "workloads_json": "[]",
                "workload_unknown_reason": "not established by selected evidence",
                "role_claims_json": "[]",
                "power_observations_json": "[]",
                "power_unknown_reason": "no typed power observation selected; not estimated",
                "annual_energy_observations_json": "[]",
                "annual_energy_unknown_reason": "no scoped annual-energy inputs selected; not estimated",
                "efficiency_observations_json": "[]",
                "efficiency_unknown_reason": "no scoped PUE or WUE observation selected",
                "status_source_url": batch.sources[status_source_id]["projection"][
                    "source_url"
                ],
                "geometry_source_url": batch.sources[primary_geometry_id]["projection"][
                    "source_url"
                ],
            }
        )
        projects.append(row)
        site = {field: "" for field in core.SITE_FIELDS}
        site.update(
            {
                field: row[field]
                for field in (
                    "site_id",
                    "physical_site_stable_key",
                    "country",
                    "country_iso_a2",
                    "latitude",
                    "longitude",
                    "geometry_json",
                    "geometry_type",
                    "horizontal_uncertainty_metres",
                    "horizontal_uncertainty_unknown_reason",
                    "verification_posture",
                    "independent_imagery_verification",
                )
            }
        )
        site.update(
            {
                "name": campus["name"],
                "project_count": 1,
                "oldest_status_as_of": status["as_of_date"],
                "newest_status_as_of": status["as_of_date"],
            }
        )
        list_fields = {
            "geometry_source_entity_kinds_json": [
                semantics["geometry_source_entity_kind"]
            ],
            "geometry_derivations_json": [semantics["geometry_derivation"]],
            "geometry_methods_json": [semantics["geometry_method"]],
            "geometry_scope_classes_json": [semantics["geometry_scope_class"]],
            "geometry_authority_classes_json": [semantics["geometry_authority_class"]],
            "geometry_use_scopes_json": [semantics["geometry_use_scope"]],
            "geometry_precision_scopes_json": [semantics["precision_scope"]],
            "geometry_evidence_ids_json": sorted(
                {
                    batch.sources[source_id]["projection"]["evidence_id"]
                    for source_id in locator["geometry_source_ids"]
                }
            ),
            "project_ids_json": [project_id],
            "project_stable_keys_json": [key],
            "statuses_json": [status["value"]],
            "imagery_review_outcomes_json": ["not_reviewed_for_core_preview"],
        }
        site.update(
            {
                field: core._json_bytes(value).decode().strip()
                for field, value in list_fields.items()
            }
        )
        sites.append(site)
    evidence_rows = [
        {
            **evidence_pool[identifier],
            "roles_json": core._json_bytes(sorted(item["roles"])).decode().strip(),
            "project_ids_json": core._json_bytes(sorted(item["projects"]))
            .decode()
            .strip(),
        }
        for identifier, item in sorted(usage.items())
    ]
    return {"projects": projects, "sites": sites, "evidence": evidence_rows}


def _payloads(batch: ValidatedBatch) -> tuple[dict[str, bytes], dict[str, Any]]:
    delta = _delta_rows(batch)
    tables = {name: [*batch.baseline[name], *delta[name]] for name in delta}
    projects, sites, evidence = (
        tables[name] for name in ("projects", "sites", "evidence")
    )
    for name, field in (
        ("projects", "project_id"),
        ("sites", "site_id"),
        ("evidence", "evidence_id"),
    ):
        _require(
            len({row[field] for row in tables[name]}) == len(tables[name]),
            f"duplicate {name} output ID",
        )
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    imagery_counts = dict(
        sorted(Counter(row["imagery_review_outcome"] for row in projects).items())
    )
    reviewed_imagery = sum(
        count
        for outcome, count in imagery_counts.items()
        if outcome != "not_reviewed_for_core_preview"
    )
    base_report = _json(
        batch.baseline["files"]["selection-report.json"], "baseline report"
    )
    inherited_blind = base_report["final_release_gates"]["blind_review"]
    baseline_count = len(batch.baseline["sites"])
    target = baseline_count + TARGET_ADDITIONAL_SITES
    non_us = sum(row["country_iso_a2"] != "US" for row in sites)
    official_boundaries = sum(core._is_official_boundary(row) for row in projects)
    counts = {
        "physical_sites": len(sites),
        "projects": len(projects),
        "evidence": len(evidence),
        "countries": len(country_counts),
        "non_us_sites": non_us,
        "official_boundary_projects": official_boundaries,
        "reviewed_site_locator_projects": sum(
            core._is_reviewed_locator(row) for row in projects
        ),
    }
    gates = {
        "site_count": {
            "actual": len(sites),
            "required": target,
            "passed": len(sites) >= target,
        },
        "additional_site_count": {
            "actual": len(sites) - baseline_count,
            "required": TARGET_ADDITIONAL_SITES,
            "passed": len(sites) - baseline_count >= TARGET_ADDITIONAL_SITES,
        },
        "country_count": {
            "actual": len(country_counts),
            "required_minimum": 40,
            "passed": len(country_counts) >= 40,
        },
        "non_us_site_count": {
            "actual": non_us,
            "required_minimum": 100,
            "passed": non_us >= 100,
        },
        "maximum_single_country_share": {
            "actual": max(country_counts.values()) / len(sites),
            "required_maximum": 0.4,
            "passed": max(country_counts.values()) / len(sites) <= 0.4,
        },
        "imagery_outcomes_complete": {
            "actual": reviewed_imagery,
            "required": len(projects),
            "passed": reviewed_imagery == len(projects),
        },
        "blind_review": {
            "sample_size": 0,
            "agreements": 0,
            "required_sample_size": 20,
            "required_agreements": 19,
            "eligible_project_count": len(projects),
            "eligible_project_stable_keys": sorted(
                row["project_stable_key"] for row in projects
            ),
            "eligible_project_keys_sha256": canonical_sha256(
                sorted(row["project_stable_key"] for row in projects)
            ),
            "population_scope": "all expanded projects, including inherited baseline and reviewed draft additions",
            "sample_scope": "no expanded-population blind-review sample or agreement records supplied by this draft builder",
            "inherited_baseline_review": inherited_blind,
            "passed": False,
        },
        "clean_clone_rebuild": {
            "passed": False,
            "reason": "portable inputs are hash-bound; an actual clean-clone run is an external release check",
        },
        "publication_authorized": {
            "passed": False,
            "reason": "this builder emits opt-in drafts only",
        },
    }
    report = {
        "format": "datacenter-atlas-v018-draft-selection-v1",
        "batch_id": batch.contract["batch_id"],
        "release_status": "draft",
        "publishable_as_final": False,
        "objective_completion_claim": False,
        "accepted_into_published_core": False,
        "lifecycle_reference_date": LIFECYCLE_REFERENCE_DATE.isoformat(),
        "geometry_identity_reviewed_at": batch.contract[
            "geometry_identity_reviewed_at"
        ],
        "baseline_counts": batch.baseline["manifest"]["counts"],
        "counts": counts,
        "draft_delta_counts": {
            "physical_sites": len(delta["sites"]),
            "projects": len(delta["projects"]),
            "evidence": len(delta["evidence"]),
        },
        "country_counts": country_counts,
        "imagery_outcome_counts": imagery_counts,
        "final_release_gates": gates,
        "source_review_limits": "Pinned source facts and reviewer decisions are reproducible; machine validation does not independently establish physical truth or resolve undisclosed campus aliases.",
    }
    provenance = {
        "contract_path": batch.contract_path.relative_to(batch.root).as_posix(),
        "contract_sha256": batch.pins.contract_sha256,
        "independent_source_review_sha256": dict(batch.pins.source_sha256),
        "independent_acceptance_review_sha256": dict(batch.pins.acceptance_sha256),
        "source_inputs": batch.contract["sources"],
        "acceptances": batch.contract["acceptances"],
    }
    geojson = _json(batch.baseline["files"]["sites.geojson"], "baseline GeoJSON")
    geojson = {
        **geojson,
        "name": "Data Center Atlas v0.18 expansion draft",
        "release_status": "draft",
        "features": [*geojson["features"], *core._geojson(delta["sites"])["features"]],
    }
    schema = _json(batch.baseline["files"]["schema.json"], "baseline schema")
    schema["format"] = "datacenter-atlas-verified-construction-core-schema-v018-draft"
    schema["base_preview_id"] = schema.pop("preview_id")
    schema["draft_id"] = f"2026-08-20-v0.18-draft-{batch.contract['batch_id']}"
    schema.pop("map")
    inherited_annotation_keys = [key for key in schema if key.startswith("v0_")]
    schema["inherited_baseline_annotations"] = {
        "preview_id": schema["base_preview_id"],
        "manifest_sha256": BASELINE_MANIFEST_SHA256,
        "scope": "historical annotations and counts for frozen v0.17 records only; not current expanded-cohort accounting",
        "annotations": {key: schema.pop(key) for key in inherited_annotation_keys},
    }
    for table_name, table_schema in schema["tables"].items():
        current_rows = tables[table_name.removesuffix(".csv")]
        for field in table_schema["fields"]:
            if "allowed_values" in field and field["logical_type"] == "string":
                field["allowed_values"] = sorted(
                    set(field["allowed_values"])
                    | {row[field["name"]] for row in current_rows}
                )
                field["allowed_values_scope"] = (
                    "frozen baseline schema plus values in reviewed draft rows"
                )
    schema["v018_draft_contract"] = {
        "schema_version": SCHEMA_VERSION,
        "release_status": "draft",
        "publishable_as_final": False,
        "location_bases": sorted(LOCATION_BASES),
        "geometry_use_scopes": sorted(USE_SCOPES),
        "schema_documentation": "datacenter_atlas/verified_construction_core_v018.py module docstring",
    }
    attribution = (
        batch.baseline["files"]["ATTRIBUTION.txt"]
        + b"\n\nV0.18 DRAFT ADDITIONAL SOURCE ATTRIBUTION\n"
    )
    for source_id, source in sorted(batch.sources.items()):
        row = source["projection"]
        attribution += (
            f"\n{source_id}\n{row['attribution']}\n{row['license']}\n{row['source_url']}\nSource input: {source['spec']['path']}\n"
        ).encode()
    readme = (
        f"# Data Center Atlas v0.18 expansion draft\n\n"
        f"{counts['physical_sites']} physical sites, {counts['projects']} projects, {counts['countries']} countries. "
        f"The frozen v0.17 baseline has {baseline_count} sites; this reviewed draft adds {len(delta['sites'])}. "
        f"The requested expansion target remains {target} total sites ({TARGET_ADDITIONAL_SITES} additional).\n\n"
        "This is an opt-in local draft, not a public release or a claim of goal completion. "
        "The public builder still defaults to v0.17. All inherited rows and features are preserved. "
        "Locators are not building footprints or surveyed boundaries unless their explicit semantics say otherwise. "
        "No additional roles, workloads, capacities, energy, or efficiency observations are inferred.\n\n"
        f"Lifecycle cutoff: {LIFECYCLE_REFERENCE_DATE.isoformat()}. "
        f"Imagery outcomes: {reviewed_imagery}/{len(projects)}; additional blind reviews: 0. "
        "See selection-report.json for every gate and ATTRIBUTION.txt for source terms.\n"
    ).encode()
    files = {
        "README.md": readme,
        "ATTRIBUTION.txt": attribution,
        "sites.geojson": core._json_bytes(geojson),
        "schema.json": core._json_bytes(schema),
        "selection-report.json": core._json_bytes(report),
        "review-provenance.json": core._json_bytes(provenance),
    }
    for name, fields in (
        ("projects", core.PROJECT_FIELDS),
        ("sites", core.SITE_FIELDS),
        ("evidence", core.EVIDENCE_FIELDS),
    ):
        appended = core._csv_bytes(delta[name], fields).split(b"\n", 1)[1]
        files[f"{name}.csv"] = batch.baseline["files"][f"{name}.csv"] + appended
    manifest = {
        "format": "datacenter-atlas-verified-construction-core-v018-draft-v1",
        "draft_id": f"2026-08-20-v0.18-draft-{batch.contract['batch_id']}",
        "release_status": "draft",
        "publishable_as_final": False,
        "objective_completion_claim": False,
        "base_preview_manifest_sha256": BASELINE_MANIFEST_SHA256,
        "base_preview_path": BASELINE_RELATIVE_DIR,
        "contract_path": batch.contract_path.relative_to(batch.root).as_posix(),
        "contract_sha256": batch.pins.contract_sha256,
        "counts": counts,
        "files": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(files.items())
        },
    }
    files["manifest.json"] = core._json_bytes(manifest)
    files["manifest.sha256"] = (
        f"{hashlib.sha256(files['manifest.json']).hexdigest()}  manifest.json\n".encode()
    )
    return files, manifest


def _validate_output(path: Path, expected: dict[str, bytes]) -> None:
    _require(
        not path.is_symlink() and path.is_dir(),
        "draft output is not a regular directory",
    )
    _require(
        {item.name for item in path.iterdir()} == set(expected),
        "draft output inventory differs",
    )
    for name, raw in expected.items():
        member = path / name
        _require(
            not member.is_symlink() and member.is_file() and member.read_bytes() == raw,
            f"draft output bytes differ: {name}",
        )


def validate_draft(
    output_dir: Path, contract_path: Path, review_pins: ReviewPins, *, root: Path = ROOT
) -> dict[str, Any]:
    """Phase two: reproduce every output byte from reviewed inputs and frozen v17."""
    batch = validate_batch(contract_path, review_pins, root=root)
    expected, manifest = _payloads(batch)
    _validate_output(Path(output_dir), expected)
    return manifest


def build_draft(
    contract_path: Path, review_pins: ReviewPins, output_dir: Path, *, root: Path = ROOT
) -> dict[str, Any]:
    """Write only a new opt-in draft after validating a complete staged artifact."""
    output_dir = Path(output_dir).absolute()
    baseline_dir = (Path(root) / BASELINE_RELATIVE_DIR).resolve()
    _require(
        not output_dir.exists() and not output_dir.is_symlink(),
        f"refusing to overwrite {output_dir}",
    )
    _require(
        not output_dir.resolve().is_relative_to(baseline_dir),
        "cannot write inside frozen baseline",
    )
    batch = validate_batch(contract_path, review_pins, root=root)
    payloads, manifest = _payloads(batch)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            with (stage / name).open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        validate_draft(stage, contract_path, review_pins, root=root)
        _require(
            not output_dir.exists() and not output_dir.is_symlink(),
            "output appeared during draft build",
        )
        os.rename(stage, output_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return manifest
