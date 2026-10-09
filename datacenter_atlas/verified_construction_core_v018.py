"""Opt-in, additive v0.18 DRAFT builder. The public CLI remains on v0.17.

Two phases are intentionally separate:

1. ``validate_batch(contract_path, review_pins, root=ROOT)`` checks independently
   reviewed input pins, exact source facts, the fixed lifecycle cutoff, geometry
   semantics, distinct-campus review, and any pinned baseline correction. It
   returns a validated batch without writing anything or declaring the 200-site
   objective complete.
2. ``build_draft(contract_path, review_pins, output_dir, root=ROOT)`` derives all
   rows and denominators, validates a staged reconstruction, then publishes a
   new local draft directory. ``validate_draft`` reconstructs every output byte.
   Under schema v1 all inherited CSV bytes and GeoJSON features remain
   unchanged. Under schema v2 every inherited byte also remains unchanged except
   the exactly enumerated fields of rows named by a pinned baseline correction,
   its dropped superseded evidence row and the project association it adds to
   shared evidence rows (below). No default artifact, public CLI, baseline
   file, or researched candidate is modified.

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

Contract schema ``datacenter-atlas-v018-reviewed-batch-v2`` is v1 plus exactly
one more required key, a nonempty ``baseline_corrections`` array. A v1 contract
that carries the key is rejected, and every v1 draft stays byte-for-byte
reproducible. Each correction re-scopes the locator semantics of one inherited
v0.17 project on a single-project site:

    "baseline_corrections": [{
      "correction_id": "a-correction-name",
      "physical_site_stable_key": "frozen v0.17 site key",
      "project_stable_key": "frozen v0.17 project key",
      "frozen_rows": {
        "release_path": BASELINE_RELATIVE_DIR,
        "manifest_sha256": BASELINE_MANIFEST_SHA256,
        "projects_csv": {"file_line_number": 37, "project_stable_key": "...",
                         "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "sites_csv": {"file_line_number": 36, "physical_site_stable_key": "...",
                      "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "evidence_csv": {"file_line_number": 136, "evidence_id": "...",
                         "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "sites_geojson": {"feature_index": 34, "feature_canonical_sha256": "..."}
      },
      "geometry": {
        "source_id": "correction-source", "record_pointer": "/results/0",
        "record_sha256": "..."
      },
      "identity_source_id": "unchanged-frozen-identity-binding",
      "evidence_source_ids": ["correction-source", "other-geometry-source"],
      "reason": "Why the inherited locator semantics are corrected."
    }]

File line numbers count the CSV header as line 1; raw-line hashes cover the
line bytes without the newline. ``evidence_source_ids`` must equal the
correction record's ``geometry_source_ids``; those sources receive only the
``geometry`` role. The geometry source's document is the pinned correction
record. Besides ``evidence`` and ``results`` it carries ``source_bindings``,
``supersedes``, ``required_unchanged_identity_bindings``, ``exact_row_deltas``
(projects.csv, sites.csv, sites.geojson, evidence.csv and one
``counts_relative_to_*`` block) and ``preservation_invariants``, and states
``lifecycle_reference_date`` 2026-08-20, ``accepted_additional_sites`` 0 and a
``reviewed_at`` date between the cutoff and the contract's review date. Each
correction is validated fail-closed:

- Frozen rows: line numbers, canonical row hashes, raw-line hashes and the
  feature hash must match the files of the pinned v0.17 manifest, and the raw
  lines and feature must still match in the later release named by
  ``supersedes.inherited_unchanged_through``. That release must be a v0.18
  draft (manifest format v1 or v2) built on the pinned v0.17 manifest, never
  the frozen baseline itself.
- Supersedes: the superseded facts file must be a pinned v0.17 portable input,
  and its hash-bound evidence and geometry records must reproduce the frozen
  evidence row, geometry, display anchor and locator semantics.
- Identity: ``identity_source_id`` names an unchanged binding to the frozen v0.17
  curated input whose project, campus, lifecycle row and evidence reproduce the
  frozen status. It is never a contract source; its evidence row is unchanged.
- Geometry: a dedicated validator accepts location basis
  ``host_estate_locality_context``, entity kind ``host_estate`` and use scope
  ``host_estate_context`` ONLY for baseline corrections, never for acceptances.
  Geometry and display anchor must equal the frozen row exactly; authority is
  unchanged and no numeric uncertainty may be asserted.
- Reused capture: the primary correction source must reuse the superseded
  capture's URL, rights, publication value, retrieval value and content hash.
  Only such a source may keep an inherited date-only ``retrieved_at``.
- Deltas: corrected rows and feature are derived like acceptance rows and must
  differ from the frozen bytes in exactly the enumerated fields; each
  ``unchanged_includes`` entry must be a column of its table. The superseded
  evidence row is dropped, the enumerated correction evidence rows are added,
  and evidence already used by acceptances only gains the project association.
  Count effects must equal the enumerated block. Every other byte is unchanged.
- Invariants: every ``preservation_invariants`` key is machine-checked and
  unrecognized keys are rejected. Optional ``osm_way_version_unchanged`` must
  equal the superseded record's OSM way version; optional
  ``intersecting_site_rows_unchanged`` lists other site keys, each of which
  must intersect the corrected geometry and keep its project and site lines
  byte for byte from the inherited-through draft.

``host_estate_context`` maps to verification posture
``recent_authoritative_physical_observation_plus_host_estate_context_only``. It
is excluded from reviewed-locator and official-boundary counts, counted in
``host_estate_context_projects``, and reported in the selection report's
``baseline_corrections`` and ``locator_exceptions`` blocks; such a display
anchor is not a site position. A baseline correction never adds, removes, moves
or merges a site or project, refreshes a lifecycle observation, or certifies a
locator. v2 drafts use manifest format
``datacenter-atlas-verified-construction-core-v018-draft-v2`` and selection
format ``datacenter-atlas-v018-draft-selection-v2``; v1 formats are unchanged.

``ReviewPins(contract_sha256, source_sha256, acceptance_sha256,
baseline_correction_sha256={})`` is supplied separately by reviewed code, not
loaded from this contract. Its maps bind every source-spec row by source_id,
every acceptance row by project_stable_key, and every baseline correction by
correction_id; the optional correction map defaults to empty and must be empty
for v1. All record/row hashes use ``canonical_sha256``: sorted compact UTF-8
JSON plus one newline. File hashes use exact bytes. Campus-key-set hashes use
sorted lists through ``canonical_sha256``. Review pins must never be
automatically refreshed to make a validation error disappear.

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
document the allowed evidence/semantic classes. Locality centroids are excluded,
and the ``BASELINE_CORRECTION_*`` host-estate classes are never accepted here.

Every acceptance is one project on one NEW physical campus. Additional projects
on an already represented site require a different, explicitly reviewed update
workflow, not this expansion path. Alias sets must not collide with the baseline
or another acceptance. Exact coincident anchors fail closed. Geographic alias
review is still a human/source judgment: hashes cannot establish physical truth.
Shared evidence within the delta is supported; baseline evidence IDs may not be
reused because their inherited usage rows must remain byte-for-byte unchanged.
Only a pinned baseline correction may drop an inherited evidence row, and only
the superseded geometry row it names.

Draft output is CSV/GeoJSON plus provenance/report/schema/attribution and manifest.
No public map is generated. Target-count achievement and final-publication
eligibility are separate: this builder ALWAYS labels its output draft and
publishable_as_final=false, including at 200 or more sites. Imagery and blind
review gates are derived from retained rows/review records, never from a constant
success claim. No roles, workload, capacity, efficiency, or energy are inferred.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
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
from types import MappingProxyType
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
SCHEMA_VERSION_V2 = "datacenter-atlas-v018-reviewed-batch-v2"
CONTRACT_KEYS = frozenset(
    {
        "schema_version",
        "batch_id",
        "base_preview_manifest_sha256",
        "lifecycle_reference_date",
        "geometry_identity_reviewed_at",
        "sources",
        "acceptances",
    }
)
CONTRACT_KEYS_V2 = CONTRACT_KEYS | {"baseline_corrections"}
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
GEOMETRY_RECORD_KEYS = frozenset(
    {
        "project_stable_key",
        "parent_campus_stable_key",
        "geometry",
        "display_anchor",
        "geometry_source_ids",
        "identity_source_ids",
        "location_basis",
        "semantics",
    }
)
# Host-estate locality context is accepted ONLY through a pinned baseline
# correction of an inherited row, never as the locator of a new acceptance.
BASELINE_CORRECTION_LOCATION_BASES = frozenset({"host_estate_locality_context"})
BASELINE_CORRECTION_ENTITY_KINDS = frozenset({"host_estate"})
BASELINE_CORRECTION_USE_SCOPES = frozenset({"host_estate_context"})
HOST_ESTATE_CONTEXT_POSTURE = (
    "recent_authoritative_physical_observation_plus_host_estate_context_only"
)
BASELINE_CORRECTION_KEYS = frozenset(
    {
        "correction_id",
        "physical_site_stable_key",
        "project_stable_key",
        "frozen_rows",
        "geometry",
        "identity_source_id",
        "evidence_source_ids",
        "reason",
    }
)
SUPERSEDES_KEYS = frozenset(
    {
        "source_path",
        "source_file_sha256",
        "source_file_bytes",
        "evidence_pointer",
        "evidence_record_sha256",
        "evidence_source_id",
        "evidence_id",
        "geometry_pointer",
        "geometry_record_sha256",
        "locator_id",
        "frozen_baseline_rows",
        "inherited_unchanged_through",
        "correction_reason",
        "frozen_artifact_mutated",
    }
)
FROZEN_ROW_TABLES = (
    ("projects_csv", "projects", "project_stable_key"),
    ("sites_csv", "sites", "physical_site_stable_key"),
    ("evidence_csv", "evidence", "evidence_id"),
)
CAPTURE_FIELDS = (
    "kind",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)
BINDING_POINTERS = (
    ("evidence_pointer", "evidence_record_sha256"),
    ("project_pointer", "project_sha256"),
    ("campus_pointer", "campus_sha256"),
    ("lifecycle_pointer", "lifecycle_sha256"),
    ("acceptance_pointer", "acceptance_sha256"),
)
CORRECTION_COUNT_KEYS = frozenset(
    {
        "physical_sites",
        "projects",
        "evidence",
        "reviewed_site_locator_projects",
        "host_estate_context_projects",
        "official_boundary_projects",
        "countries",
        "non_us_sites",
    }
)
DRAFT_MANIFEST_FORMAT_V1 = "datacenter-atlas-verified-construction-core-v018-draft-v1"
DRAFT_MANIFEST_FORMAT_V2 = "datacenter-atlas-verified-construction-core-v018-draft-v2"
# Every key of a correction's preservation_invariants is machine-checked: the
# required keys against the frozen rows and records, these optional ones below.
OPTIONAL_PRESERVATION_INVARIANTS = frozenset(
    {"osm_way_version_unchanged", "intersecting_site_rows_unchanged"}
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


TABLE_FIELDS = {
    "projects": core.PROJECT_FIELDS,
    "sites": core.SITE_FIELDS,
    "evidence": core.EVIDENCE_FIELDS,
}


@dataclass(frozen=True)
class ReviewPins:
    contract_sha256: str
    source_sha256: Mapping[str, str]
    acceptance_sha256: Mapping[str, str]
    # One independent pin per v2 baseline correction_id; empty for v1 contracts.
    baseline_correction_sha256: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class ValidatedBatch:
    root: Path
    contract_path: Path
    pins: ReviewPins
    contract: dict[str, Any]
    baseline: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    acceptances: tuple[dict[str, Any], ...]
    baseline_corrections: tuple[dict[str, Any], ...] = ()


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


def _date_only(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def _source_evidence(
    evidence: Any, label: str, *, inherited_date_only_retrieval: bool = False
) -> dict[str, Any]:
    """Project curated evidence; date-only retrieval only for a reused v2 capture.

    ``inherited_date_only_retrieval`` is set solely by ``validate_batch`` for a
    v2 source whose literal ``retrieved_at`` is a calendar date. That source is
    later required to be a baseline correction's reused frozen capture; every
    other source keeps the timezone-bearing retrieval requirement.
    """
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
    if inherited_date_only_retrieval:
        # A reused frozen capture keeps its literal calendar date; no time of
        # day or timezone is invented, so comparisons below are day-level.
        _require(
            _date_only(evidence["retrieved_at"]),
            f"{label} inherited retrieval must be a calendar date",
        )
        retrieved = None
        retrieval_day = _calendar(
            evidence["retrieved_at"], f"{label} inherited retrieval date"
        )
    else:
        try:
            retrieved = datetime.fromisoformat(
                evidence["retrieved_at"].replace("Z", "+00:00")
            )
            _require(retrieved.tzinfo is not None, f"{label} retrieval needs timezone")
        except ValueError as exc:
            raise DraftValidationError(f"invalid {label} retrieval timestamp") from exc
        retrieval_day = retrieved.date()
    _require(
        "published_at" in evidence, f"{label} publication date must be explicit or null"
    )
    if evidence["published_at"] is not None:
        publication_text = _text(evidence["published_at"], f"{label} publication date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_text):
            publication_day = _calendar(publication_text, f"{label} publication date")
            publication_precedes_retrieval = publication_day <= retrieval_day
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
                if publication_time.tzinfo is not None and retrieved is not None
                else publication_time.date() <= retrieval_day
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


def _geometry_shape(record: Any, label: str = "geometry record") -> str:
    """Structural geometry/anchor checks shared by acceptances and corrections."""
    _keys(record, GEOMETRY_RECORD_KEYS, label)
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
    return kind


def _host_estate_semantics(record: Mapping[str, Any], semantics: Any) -> bool:
    basis = record.get("location_basis")
    return (
        (isinstance(basis, str) and basis in BASELINE_CORRECTION_LOCATION_BASES)
        or (
            isinstance(semantics, Mapping)
            and (
                semantics.get("geometry_source_entity_kind")
                in BASELINE_CORRECTION_ENTITY_KINDS
                or semantics.get("geometry_use_scope")
                in BASELINE_CORRECTION_USE_SCOPES
            )
        )
    )


def _geometry(record: dict[str, Any]) -> None:
    """Validate an ACCEPTANCE locator; host-estate context is always rejected."""
    kind = _geometry_shape(record)
    semantics = _keys(record["semantics"], SEMANTIC_FIELDS, "geometry semantics")
    for field in SEMANTIC_FIELDS - {
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
    }:
        _text(semantics[field], f"geometry semantics {field}")
    _require(
        not _host_estate_semantics(record, semantics),
        "host-estate locality context is accepted only through a pinned baseline "
        "correction, never as an acceptance locator",
    )
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


def _verification_posture(authority: str, use_scope: str) -> str:
    if use_scope in BASELINE_CORRECTION_USE_SCOPES:
        return HOST_ESTATE_CONTEXT_POSTURE
    return core._verification_posture(authority, use_scope)


def _is_host_estate_context(row: Mapping[str, Any]) -> bool:
    return row.get("geometry_use_scope") in BASELINE_CORRECTION_USE_SCOPES


def _is_reviewed_locator(row: Mapping[str, Any]) -> bool:
    return not _is_host_estate_context(row) and core._is_reviewed_locator(row)


def _json_cell(value: Any) -> str:
    return core._json_bytes(value).decode().strip()


def _json_field(text: Any, label: str) -> Any:
    _require(isinstance(text, str), f"{label} is not text")
    return _json(text.encode(), label)


def _csv_line(row: Mapping[str, Any], fields: Sequence[str]) -> bytes:
    """One CSV data line, without its newline, exactly as the table writer emits it."""
    line = core._csv_bytes([row], fields).split(b"\n", 1)[1]
    _require(
        line.count(b"\n") == 1 and line.endswith(b"\n") and b"\r" not in line,
        "CSV row would span lines",
    )
    return line[:-1]


def _csv_lines(raw: bytes, count: int, label: str) -> list[bytes]:
    lines = raw.split(b"\n")
    _require(
        len(lines) == count + 2 and lines[-1] == b"" and b"\r" not in raw,
        f"{label} line numbering is ambiguous",
    )
    return lines


def _pinned_v017_input(
    baseline: Mapping[str, Any], path: Any, sha256: Any, size: Any
) -> bool:
    inputs = baseline["manifest"].get("portable_source_inputs")
    return isinstance(inputs, list) and any(
        isinstance(item, dict)
        and item.get("path") == path
        and item.get("sha256") == sha256
        and type(item.get("bytes")) is int
        and item.get("bytes") == size
        for item in inputs
    )


def _frozen_rows(
    frozen: Any, baseline: Mapping[str, Any], project_key: str, site_key: str
) -> dict[str, Any]:
    """Locate and hash-check the frozen v0.17 rows and feature a correction names."""
    _keys(
        frozen,
        {
            "release_path",
            "manifest_sha256",
            "projects_csv",
            "sites_csv",
            "evidence_csv",
            "sites_geojson",
        },
        "baseline correction frozen rows",
    )
    _require(
        frozen["release_path"] == BASELINE_RELATIVE_DIR
        and frozen["manifest_sha256"] == BASELINE_MANIFEST_SHA256,
        "baseline correction must name rows of the pinned v0.17 manifest",
    )
    located: dict[str, Any] = {}
    for key, table, id_field in FROZEN_ROW_TABLES:
        spec = _keys(
            frozen[key],
            {"file_line_number", id_field, "row_canonical_sha256", "raw_line_sha256"},
            f"frozen {table} row",
        )
        rows = baseline[table]
        lines = _csv_lines(
            baseline["files"][f"{table}.csv"], len(rows), f"frozen {table}.csv"
        )
        number = spec["file_line_number"]
        _require(
            type(number) is int and 2 <= number <= len(rows) + 1,
            f"frozen {table} line number differs",
        )
        row = rows[number - 2]
        identifier = _text(spec[id_field], f"frozen {table} identifier")
        _require(
            row[id_field] == identifier
            and sum(item[id_field] == identifier for item in rows) == 1,
            f"frozen {table} row identity differs",
        )
        _require(
            canonical_sha256(row)
            == _hash(spec["row_canonical_sha256"], f"frozen {table} row hash"),
            f"frozen {table} row SHA-256 differs",
        )
        raw = lines[number - 1]
        _require(
            hashlib.sha256(raw).hexdigest()
            == _hash(spec["raw_line_sha256"], f"frozen {table} raw line hash"),
            f"frozen {table} raw line SHA-256 differs",
        )
        _require(
            _csv_line(row, TABLE_FIELDS[table]) == raw,
            f"frozen {table} row does not reproduce its raw line",
        )
        located[table] = {"index": number - 2, "line": number, "row": row}
    project, site, evidence = (
        located[name]["row"] for name in ("projects", "sites", "evidence")
    )
    _require(
        project["project_stable_key"] == project_key
        and site["physical_site_stable_key"] == site_key
        and project["physical_site_stable_key"] == site_key
        and project["site_id"] == site["site_id"],
        "baseline correction project/site rows differ",
    )
    _require(
        site["project_count"] == "1"
        and _json_field(site["project_ids_json"], "frozen site projects")
        == [project["project_id"]]
        and _json_field(site["project_stable_keys_json"], "frozen site project keys")
        == [project_key]
        and sum(
            row["physical_site_stable_key"] == site_key for row in baseline["projects"]
        )
        == 1,
        "baseline corrections support single-project sites only",
    )
    superseded = evidence["evidence_id"]
    _require(
        project["geometry_evidence_id"] == superseded
        and _json_field(site["geometry_evidence_ids_json"], "frozen site evidence")
        == [superseded]
        and _json_field(evidence["roles_json"], "frozen evidence roles") == ["geometry"]
        and _json_field(evidence["project_ids_json"], "frozen evidence projects")
        == [project["project_id"]],
        "superseded evidence row is not solely this project's geometry evidence",
    )
    for table in ("projects", "sites"):
        for index, row in enumerate(baseline[table]):
            _require(
                index == located[table]["index"]
                or not any(superseded in str(value) for value in row.values()),
                "superseded evidence row is referenced by another inherited row",
            )
    spec = _keys(
        frozen["sites_geojson"],
        {"feature_index", "feature_canonical_sha256"},
        "frozen GeoJSON feature",
    )
    geojson = _json(baseline["files"]["sites.geojson"], "baseline GeoJSON")
    features = geojson.get("features") if isinstance(geojson, dict) else None
    index = spec["feature_index"]
    _require(
        isinstance(features, list)
        and type(index) is int
        and 0 <= index < len(features),
        "frozen GeoJSON feature index differs",
    )
    feature = features[index]
    _require(
        canonical_sha256(feature)
        == _hash(spec["feature_canonical_sha256"], "frozen feature hash"),
        "frozen GeoJSON feature SHA-256 differs",
    )
    _require(
        feature == core._geojson([site])["features"][0],
        "frozen GeoJSON feature does not reproduce its site row",
    )
    located["feature"] = {"index": index, "feature": feature}
    return located


def _inherited_unchanged_through(
    spec: Any, root: Path, frozen: Mapping[str, Any]
) -> dict[str, frozenset[bytes]]:
    """Prove the frozen rows were still byte-identical in the named later draft.

    The release must be a v0.18 draft built on the pinned v0.17 manifest, never
    the frozen baseline itself. Returns that draft's project and site data lines.
    """
    _keys(
        spec,
        {"release_path", "manifest_sha256", "rows_byte_identical_to_v017"},
        "inherited-through release",
    )
    _require(
        spec["rows_byte_identical_to_v017"] is True,
        "inherited-through release must preserve the frozen rows",
    )
    release = spec["release_path"]
    directory = _portable_path(root, release, "inherited-through release path")
    _require(
        Path(release).parts[0] == "verified_construction_core"
        and not directory.is_symlink()
        and directory.is_dir(),
        "inherited-through release is not a release directory",
    )
    _require(
        Path(release).as_posix() != BASELINE_RELATIVE_DIR
        and directory.resolve() != (root / BASELINE_RELATIVE_DIR).resolve()
        and spec["manifest_sha256"] != BASELINE_MANIFEST_SHA256,
        "inherited-through release must be a later v0.18 draft, not the frozen baseline",
    )
    manifest = _json(
        _read_pinned(directory / "manifest.json", spec["manifest_sha256"]),
        "inherited-through manifest",
    )
    _require(
        isinstance(manifest, dict)
        and manifest.get("format") in {DRAFT_MANIFEST_FORMAT_V1, DRAFT_MANIFEST_FORMAT_V2}
        and manifest.get("release_status") == "draft"
        and manifest.get("base_preview_manifest_sha256") == BASELINE_MANIFEST_SHA256
        and manifest.get("base_preview_path") == BASELINE_RELATIVE_DIR,
        "inherited-through release is not a v0.18 draft of the pinned v0.17 baseline",
    )
    files = manifest.get("files")
    _require(isinstance(files, dict), "inherited-through manifest lacks files")
    data = {}
    for name in ("projects.csv", "sites.csv", "evidence.csv", "sites.geojson"):
        entry = files.get(name)
        _require(
            isinstance(entry, dict) and type(entry.get("bytes")) is int,
            f"inherited-through manifest lacks {name}",
        )
        data[name] = _read_pinned(directory / name, entry.get("sha256"), entry["bytes"])
    for key, table, _ in FROZEN_ROW_TABLES:
        lines = data[f"{table}.csv"].split(b"\n")
        number = frozen[key]["file_line_number"]
        _require(
            number < len(lines)
            and hashlib.sha256(lines[number - 1]).hexdigest()
            == frozen[key]["raw_line_sha256"],
            f"inherited {table} row changed after v0.17",
        )
    geojson = _json(data["sites.geojson"], "inherited-through GeoJSON")
    features = geojson.get("features") if isinstance(geojson, dict) else None
    index = frozen["sites_geojson"]["feature_index"]
    _require(
        isinstance(features, list)
        and index < len(features)
        and canonical_sha256(features[index])
        == frozen["sites_geojson"]["feature_canonical_sha256"],
        "inherited GeoJSON feature changed after v0.17",
    )
    return {
        table: frozenset(
            line for line in data[f"{table}.csv"].split(b"\n")[1:] if line
        )
        for table in ("projects", "sites")
    }


def _superseded(
    supersedes: Any,
    root: Path,
    baseline: Mapping[str, Any],
    located: Mapping[str, Any],
    correction: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, frozenset[bytes]]]:
    """Bind the frozen rows to the superseded record of the frozen v0.16 facts.

    Returns the superseded evidence record and the inherited-through draft's
    project and site data lines.
    """
    _keys(supersedes, SUPERSEDES_KEYS, "baseline correction supersedes")
    relative = supersedes["source_path"]
    path = _portable_path(root, relative, "superseded source path")
    _require(Path(relative).parts[0] == "sources", "superseded source must be under sources/")
    _require(
        _pinned_v017_input(
            baseline,
            relative,
            supersedes["source_file_sha256"],
            supersedes["source_file_bytes"],
        ),
        "superseded source is not a pinned v0.17 portable input",
    )
    document = _json(
        _read_pinned(
            path, supersedes["source_file_sha256"], supersedes["source_file_bytes"]
        ),
        "superseded source",
    )
    evidence = _pointer(document, supersedes["evidence_pointer"])
    _require(
        isinstance(evidence, dict)
        and canonical_sha256(evidence)
        == _hash(supersedes["evidence_record_sha256"], "superseded evidence hash"),
        "superseded evidence record SHA-256 differs",
    )
    project = located["projects"]["row"]
    site = located["sites"]["row"]
    frozen_evidence = located["evidence"]["row"]
    _require(
        evidence.get("source_id")
        == _text(supersedes["evidence_source_id"], "superseded evidence source")
        and evidence.get("evidence_id")
        == supersedes["evidence_id"]
        == frozen_evidence["evidence_id"],
        "superseded evidence identity differs",
    )
    _require(
        all(
            frozen_evidence[field] == value
            for field, value in core._v07_evidence_projection(evidence).items()
        ),
        "frozen evidence row is not the superseded record",
    )
    record = _pointer(document, supersedes["geometry_pointer"])
    _require(
        isinstance(record, dict)
        and canonical_sha256(record)
        == _hash(supersedes["geometry_record_sha256"], "superseded geometry hash"),
        "superseded geometry record SHA-256 differs",
    )
    _require(
        record.get("locator_id") == _text(supersedes["locator_id"], "superseded locator")
        and record.get("project_stable_key") == correction["project_stable_key"]
        and record.get("geometry_source_document_id")
        == supersedes["evidence_source_id"],
        "superseded geometry identity differs",
    )
    try:
        geometry = core._v15_result_geometry(record)
    except core.VerifiedConstructionCoreError as exc:
        raise DraftValidationError("superseded geometry cannot be decoded") from exc
    _require(
        _json_cell(geometry) == project["geometry_json"] == site["geometry_json"]
        and geometry["type"] == project["geometry_type"] == site["geometry_type"],
        "frozen geometry is not the superseded record",
    )
    anchor = record.get("display_anchor")
    _require(
        isinstance(anchor, dict)
        and anchor.get("coordinates")
        == [float(project["longitude"]), float(project["latitude"])],
        "frozen display anchor is not the superseded record",
    )
    semantics = record.get("semantics")
    _require(
        isinstance(semantics, dict)
        and all(
            project[field] == semantics.get(field)
            for field in sorted(SEMANTIC_FIELDS)
            if field.startswith("geometry_")
        )
        and project["geometry_precision_scope"] == semantics.get("precision_scope")
        and project["horizontal_uncertainty_unknown_reason"]
        == semantics.get("horizontal_uncertainty_unknown_reason")
        and project["horizontal_uncertainty_metres"] == ""
        and semantics.get("horizontal_uncertainty_metres") is None,
        "frozen locator semantics are not the superseded record",
    )
    _require(
        supersedes["frozen_baseline_rows"] == correction["frozen_rows"],
        "contract frozen rows differ from the correction record",
    )
    _text(supersedes["correction_reason"], "superseded correction reason")
    _require(
        supersedes["frozen_artifact_mutated"] is False,
        "a baseline correction cannot mutate a frozen artifact",
    )
    inherited_lines = _inherited_unchanged_through(
        supersedes["inherited_unchanged_through"], root, correction["frozen_rows"]
    )
    return evidence, inherited_lines


def _unchanged_bindings(
    document: Mapping[str, Any],
    root: Path,
    baseline: Mapping[str, Any],
    located: Mapping[str, Any],
    correction: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> None:
    """Check every unchanged binding and the frozen identity/status it preserves."""
    bindings = document.get("required_unchanged_identity_bindings")
    _require(
        isinstance(bindings, list) and bool(bindings),
        "baseline correction lacks unchanged identity bindings",
    )
    resolved: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        _require(isinstance(binding, dict), "unchanged binding is not an object")
        pairs = [pair for pair in BINDING_POINTERS if pair[0] in binding]
        expected = {"source_id", "source_path", "source_file_sha256", "source_file_bytes"}
        expected.update(key for pair in pairs for key in pair)
        if "note" in binding:
            expected.add("note")
            _text(binding["note"], "unchanged binding note")
        _keys(binding, expected, "unchanged binding")
        _require(bool(pairs), "unchanged binding pins no record")
        source_id = _text(binding["source_id"], "unchanged binding ID")
        _require(source_id not in resolved, "duplicate unchanged binding")
        relative = binding["source_path"]
        path = _portable_path(root, relative, "unchanged binding path")
        _require(
            Path(relative).parts[0] in {"sources", "definitions"},
            "unchanged binding must be a sources/ or definitions/ input",
        )
        bound = _json(
            _read_pinned(
                path, binding["source_file_sha256"], binding["source_file_bytes"]
            ),
            source_id,
        )
        records = {}
        for pointer_key, hash_key in pairs:
            value = _pointer(bound, binding[pointer_key])
            _require(
                isinstance(value, dict)
                and canonical_sha256(value)
                == _hash(binding[hash_key], f"{source_id} {hash_key}"),
                f"unchanged binding record SHA-256 differs: {source_id}",
            )
            records[pointer_key.removesuffix("_pointer")] = value
        resolved[source_id] = {
            "records": records,
            "v017_input": _pinned_v017_input(
                baseline,
                relative,
                binding["source_file_sha256"],
                binding["source_file_bytes"],
            ),
        }
    identity_id = correction["identity_source_id"]
    identity = resolved.get(identity_id)
    _require(
        identity is not None and identity_id not in sources,
        "identity source must be an unchanged frozen binding, not a contract source",
    )
    records = identity["records"]
    _require(
        identity["v017_input"]
        and set(records) == {"evidence", "project", "campus", "lifecycle"},
        "identity binding is not a pinned v0.17 curated input",
    )
    project = located["projects"]["row"]
    _require(
        records["project"].get("stable_key") == correction["project_stable_key"]
        and records["campus"].get("stable_key")
        == correction["physical_site_stable_key"],
        "identity binding project/campus differs",
    )
    status = records["lifecycle"]
    _require(
        status.get("entity") == "project"
        and status.get("value") == project["last_observed_physical_status"]
        and status.get("as_of_date") == project["status_as_of"]
        and status.get("method") == project["status_method"]
        and status.get("evidence_key") == records["evidence"].get("key"),
        "frozen lifecycle observation differs from the identity binding",
    )
    status_evidence = _source_evidence(records["evidence"], identity_id)
    frozen_status = [
        row
        for row in baseline["evidence"]
        if row["evidence_id"] == status_evidence["evidence_id"]
    ]
    _require(
        status_evidence["evidence_id"] == project["status_evidence_id"]
        and status_evidence["source_url"] == project["status_source_url"]
        and len(frozen_status) == 1
        and all(
            frozen_status[0][field] == value for field, value in status_evidence.items()
        ),
        "identity binding is not the frozen status evidence",
    )
    for source_id, item in resolved.items():
        if "acceptance" in item["records"]:
            _require(
                item["v017_input"]
                and item["records"]["acceptance"].get("project_stable_key")
                == correction["project_stable_key"],
                f"unchanged acceptance binding differs: {source_id}",
            )
        if source_id in sources:
            _require(
                "evidence" in item["records"]
                and sources[source_id]["evidence"] == item["records"]["evidence"],
                f"correction evidence differs from its bound original: {source_id}",
            )


def _baseline_correction_geometry(
    record: Any, correction: Mapping[str, Any], located: Mapping[str, Any]
) -> None:
    """Dedicated correction validator: host-estate context, frozen numbers only."""
    _geometry_shape(record, "baseline correction geometry record")
    semantics = _keys(
        record["semantics"], SEMANTIC_FIELDS, "baseline correction geometry semantics"
    )
    for field in sorted(
        SEMANTIC_FIELDS
        - {"horizontal_uncertainty_metres", "horizontal_uncertainty_unknown_reason"}
    ):
        _text(semantics[field], f"baseline correction semantics {field}")
    _require(
        isinstance(record["location_basis"], str)
        and record["location_basis"] in BASELINE_CORRECTION_LOCATION_BASES
        and semantics["geometry_source_entity_kind"] in BASELINE_CORRECTION_ENTITY_KINDS
        and semantics["geometry_use_scope"] in BASELINE_CORRECTION_USE_SCOPES,
        "baseline correction must re-scope its locator to host-estate locality context",
    )
    project = located["projects"]["row"]
    site = located["sites"]["row"]
    _require(
        record["project_stable_key"] == correction["project_stable_key"]
        and record["parent_campus_stable_key"] == correction["physical_site_stable_key"],
        "baseline correction geometry identity differs",
    )
    _require(
        semantics["geometry_authority_class"] in {"official_source", "community_source"}
        and semantics["geometry_authority_class"] == project["geometry_authority_class"],
        "baseline correction cannot change geometry authority",
    )
    _require(
        semantics["horizontal_uncertainty_metres"] is None
        and project["horizontal_uncertainty_metres"] == "",
        "host-estate context cannot assert a numeric site uncertainty",
    )
    _text(
        semantics["horizontal_uncertainty_unknown_reason"],
        "baseline correction unknown uncertainty reason",
    )
    geometry = record["geometry"]
    _require(
        _json_cell(geometry) == project["geometry_json"] == site["geometry_json"]
        and geometry["type"] == project["geometry_type"] == site["geometry_type"],
        "baseline correction geometry differs from the frozen row",
    )
    longitude, latitude = record["display_anchor"]["coordinates"]
    _require(
        repr(longitude) == project["longitude"] == site["longitude"]
        and repr(latitude) == project["latitude"] == site["latitude"]
        and [float(project["longitude"]), float(project["latitude"])]
        == [longitude, latitude],
        "baseline correction display anchor differs from the frozen row",
    )


def _correction_document(
    document: Any,
    sources: Mapping[str, Any],
    source_id: str,
    reviewed_at: date,
) -> None:
    _require(isinstance(document, dict), "correction record is not an object")
    _require(
        document.get("lifecycle_reference_date") == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "correction lifecycle cutoff cannot move",
    )
    _require(
        type(document.get("accepted_additional_sites")) is int
        and document["accepted_additional_sites"] == 0,
        "a baseline correction cannot add sites",
    )
    corrected_at = _calendar(document.get("reviewed_at"), "correction review date")
    _require(
        LIFECYCLE_REFERENCE_DATE <= corrected_at <= reviewed_at,
        "correction review date falls outside the checkpoint review",
    )
    path = sources[source_id]["spec"]["path"]
    bound = sorted(
        (other_id, source["spec"]["evidence_pointer"])
        for other_id, source in sources.items()
        if source["spec"]["path"] == path
    )
    declared = document.get("source_bindings")
    _require(
        isinstance(declared, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"source_id", "evidence_pointer"}
            and isinstance(item["source_id"], str)
            and isinstance(item["evidence_pointer"], str)
            for item in declared
        )
        and sorted((item["source_id"], item["evidence_pointer"]) for item in declared)
        == bound,
        "correction source bindings differ from the contract sources",
    )


def _reused_capture(
    evidence: Mapping[str, Any],
    superseded: Mapping[str, Any],
    supersedes: Mapping[str, Any],
) -> None:
    _require(
        all(evidence.get(field) == superseded.get(field) for field in CAPTURE_FIELDS),
        "primary correction source is not the reused frozen capture",
    )
    metadata = evidence.get("metadata")
    if isinstance(metadata, dict) and "supersedes" in metadata:
        claimed = metadata["supersedes"]
        _require(
            isinstance(claimed, dict)
            and all(
                key in supersedes and supersedes[key] == value
                for key, value in claimed.items()
            ),
            "reused capture metadata names a different superseded record",
        )


def _preservation_invariants(
    document: Mapping[str, Any],
    located: Mapping[str, Any],
    record: Mapping[str, Any],
    superseded: Mapping[str, Any],
    reused: Mapping[str, Any],
) -> dict[str, Any]:
    """Check every invariant key; unrecognized keys are rejected, not trusted.

    ``osm_way_version_unchanged`` must equal the superseded record's OSM way
    version (and the reused capture's, when its metadata states one).
    ``intersecting_site_rows_unchanged`` lists other site keys; after the
    batch is derived, each must intersect the corrected geometry and keep its
    project and site lines byte for byte from the inherited-through draft.
    """
    invariants = document.get("preservation_invariants")
    _require(isinstance(invariants, dict), "baseline correction lacks invariants")
    project = located["projects"]["row"]
    expected = {
        "raw_evidence_body_sha256_unchanged": superseded["content_hash"],
        "raw_capture_retrieved_at_unchanged": superseded["retrieved_at"],
        "numeric_geometry_unchanged": True,
        "display_anchor_unchanged": record["display_anchor"]["coordinates"],
        "geometry_authority_class_unchanged": project["geometry_authority_class"],
        "physical_campus_key_unchanged": True,
        "construction_project_key_unchanged": True,
        "lifecycle_observation_unchanged": {
            "value": project["last_observed_physical_status"],
            "as_of_date": project["status_as_of"],
            "method": project["status_method"],
        },
        "horizontal_uncertainty_metres": None,
        "site_count_unchanged": True,
        "old_file_not_modified": True,
        "frozen_v017_not_modified": True,
    }
    for key, value in expected.items():
        _require(
            key in invariants
            and canonical_sha256(invariants[key]) == canonical_sha256(value),
            f"baseline correction preservation invariant differs: {key}",
        )
    unchecked = set(invariants) - set(expected) - OPTIONAL_PRESERVATION_INVARIANTS
    _require(
        not unchecked,
        "baseline correction preservation invariant is not machine-checked: "
        + ", ".join(sorted(unchecked)),
    )
    if "osm_way_version_unchanged" in invariants:
        version = invariants["osm_way_version_unchanged"]
        facts = superseded.get("facts")
        metadata = reused.get("metadata")
        _require(
            type(version) is int
            and isinstance(facts, dict)
            and type(facts.get("version")) is int
            and facts["version"] == version
            and (
                not isinstance(metadata, dict)
                or "osm_version" not in metadata
                or (
                    type(metadata["osm_version"]) is int
                    and metadata["osm_version"] == version
                )
            ),
            "baseline correction preservation invariant differs: "
            "osm_way_version_unchanged",
        )
    if "intersecting_site_rows_unchanged" in invariants:
        keys = _unique_text(
            invariants["intersecting_site_rows_unchanged"],
            "intersecting unchanged site keys",
        )
        _require(
            keys == sorted(keys)
            and located["sites"]["row"]["physical_site_stable_key"] not in keys,
            "baseline correction preservation invariant differs: "
            "intersecting_site_rows_unchanged",
        )
    return invariants


def _intersecting_rows_unchanged(
    batch: ValidatedBatch, delta: Mapping[str, list[dict[str, Any]]]
) -> None:
    """Check each declared intersecting site against the inherited-through draft."""
    declared = [
        item
        for item in batch.baseline_corrections
        if "intersecting_site_rows_unchanged" in item["invariants"]
    ]
    if not declared:
        return
    inherited, _, _ = _inherited(batch)
    projects = [*inherited["projects"], *delta["projects"]]
    sites = {
        row["physical_site_stable_key"]: row
        for row in [*inherited["sites"], *delta["sites"]]
    }
    for item in declared:
        corrected = _json_field(item["site"]["geometry_json"], "corrected site geometry")
        through = item["inherited_through_lines"]
        for key in item["invariants"]["intersecting_site_rows_unchanged"]:
            site = sites.get(key)
            _require(
                site is not None
                and _geometries_intersect(
                    corrected, _json_field(site["geometry_json"], "site geometry")
                ),
                f"declared intersecting site does not intersect the correction: {key}",
            )
            rows = [row for row in projects if row["physical_site_stable_key"] == key]
            _require(
                bool(rows)
                and _csv_line(site, TABLE_FIELDS["sites"]) in through["sites"]
                and all(
                    _csv_line(row, TABLE_FIELDS["projects"]) in through["projects"]
                    for row in rows
                ),
                f"intersecting site rows changed after the inherited-through draft: {key}",
            )


def _corrected_rows(
    record: Mapping[str, Any],
    located: Mapping[str, Any],
    sources: Mapping[str, Any],
    primary_source_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Derive the corrected rows exactly as acceptance rows derive locator fields."""
    semantics = record["semantics"]
    primary = sources[primary_source_id]["projection"]
    posture = _verification_posture(
        semantics["geometry_authority_class"], semantics["geometry_use_scope"]
    )
    reason = semantics["horizontal_uncertainty_unknown_reason"]
    project = dict(located["projects"]["row"])
    project.update(
        {
            **{
                field: semantics[field]
                for field in sorted(SEMANTIC_FIELDS)
                if field.startswith("geometry_")
            },
            "geometry_precision_scope": semantics["precision_scope"],
            "horizontal_uncertainty_metres": "",
            "horizontal_uncertainty_unknown_reason": reason,
            "geometry_evidence_id": primary["evidence_id"],
            "verification_posture": posture,
            "geometry_source_url": primary["source_url"],
        }
    )
    site = dict(located["sites"]["row"])
    site.update(
        {
            "geometry_source_entity_kinds_json": _json_cell(
                [semantics["geometry_source_entity_kind"]]
            ),
            "geometry_derivations_json": _json_cell([semantics["geometry_derivation"]]),
            "geometry_methods_json": _json_cell([semantics["geometry_method"]]),
            "geometry_scope_classes_json": _json_cell(
                [semantics["geometry_scope_class"]]
            ),
            "geometry_authority_classes_json": _json_cell(
                [semantics["geometry_authority_class"]]
            ),
            "geometry_use_scopes_json": _json_cell([semantics["geometry_use_scope"]]),
            "geometry_precision_scopes_json": _json_cell([semantics["precision_scope"]]),
            "horizontal_uncertainty_metres": "",
            "horizontal_uncertainty_unknown_reason": reason,
            "geometry_evidence_ids_json": _json_cell(
                sorted(
                    {
                        sources[source_id]["projection"]["evidence_id"]
                        for source_id in record["geometry_source_ids"]
                    }
                )
            ),
            "verification_posture": posture,
        }
    )
    for row, table in ((project, "projects"), (site, "sites")):
        _csv_line(row, TABLE_FIELDS[table])
    return project, site, core._geojson([site])["features"][0]


def _changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list]:
    _require(set(before) == set(after), "corrected row fields differ")
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}


def _exact_row_deltas(
    document: Mapping[str, Any],
    located: Mapping[str, Any],
    corrected: Mapping[str, Any],
    correction: Mapping[str, Any],
    sources: Mapping[str, Any],
    geometry_ids: list[str],
) -> dict[str, Any]:
    """Require the derived correction to equal the enumerated exact deltas."""
    deltas = document.get("exact_row_deltas")
    _require(isinstance(deltas, dict), "baseline correction lacks exact row deltas")
    count_keys = [key for key in deltas if key.startswith("counts_relative_to_")]
    _require(len(count_keys) == 1, "baseline correction needs one count-effect block")
    _keys(
        deltas,
        {"projects.csv", "sites.csv", "sites.geojson", "evidence.csv", *count_keys},
        "exact row deltas",
    )
    changed_fields = {}
    for name, table in (("projects.csv", "projects"), ("sites.csv", "sites")):
        spec = _keys(
            deltas[name],
            {"file_line_number", "changed", "unchanged_includes"},
            f"{name} exact delta",
        )
        changed = _changed(located[table]["row"], corrected[table])
        _require(
            spec["file_line_number"] == located[table]["line"]
            and spec["changed"] == changed,
            f"{name} correction differs from its enumerated exact delta",
        )
        unchanged = _unique_text(spec["unchanged_includes"], f"{name} unchanged fields")
        _require(
            set(unchanged).issubset(TABLE_FIELDS[table]),
            f"{name} exact delta lists an unchanged field that is not a column",
        )
        _require(
            not set(unchanged).intersection(changed),
            f"{name} exact delta lists a changed field as unchanged",
        )
        changed_fields[name] = sorted(changed)
    spec = _keys(
        deltas["sites.geojson"],
        {"feature_index", "changed_properties", "geometry_unchanged"},
        "sites.geojson exact delta",
    )
    frozen_feature = located["feature"]["feature"]
    feature = corrected["feature"]
    properties = _changed(frozen_feature["properties"], feature["properties"])
    _require(
        {key: value for key, value in frozen_feature.items() if key != "properties"}
        == {key: value for key, value in feature.items() if key != "properties"}
        and spec["feature_index"] == located["feature"]["index"]
        and spec["geometry_unchanged"] is True
        and spec["changed_properties"] == properties,
        "sites.geojson correction differs from its enumerated exact delta",
    )
    changed_fields["sites.geojson"] = sorted(properties)
    evidence = _keys(
        deltas["evidence.csv"],
        {"removed", "added", "association_only"},
        "evidence.csv exact delta",
    )
    frozen = correction["frozen_rows"]["evidence_csv"]
    _require(
        evidence["removed"]
        == [
            {
                "evidence_id": frozen["evidence_id"],
                "file_line_number": frozen["file_line_number"],
                "row_canonical_sha256": frozen["row_canonical_sha256"],
            }
        ],
        "evidence delta must remove exactly the superseded row",
    )
    by_id = {
        sources[source_id]["projection"]["evidence_id"]: sources[source_id]
        for source_id in geometry_ids
    }
    project_id = corrected["projects"]["project_id"]
    added, shared = evidence["added"], evidence["association_only"]
    _require(
        isinstance(added, list) and isinstance(shared, list),
        "evidence delta lists differ",
    )
    for item in added:
        _keys(item, {"evidence_id", "key", "roles", "project_ids"}, "added evidence")
        source = by_id.get(_text(item["evidence_id"], "added evidence ID"))
        _require(
            source is not None
            and item["key"] == source["evidence"]["key"]
            and item["roles"] == ["geometry"]
            and item["project_ids"] == [project_id],
            "added correction evidence differs from its enumerated delta",
        )
    for item in shared:
        _require(isinstance(item, dict), "association-only evidence is not an object")
        expected = {"evidence_id", "key", "changed_field", "after_adds_project_id"}
        if "note" in item:
            expected.add("note")
            _text(item["note"], "association-only evidence note")
        _keys(item, expected, "association-only evidence")
        source = by_id.get(_text(item["evidence_id"], "association-only evidence ID"))
        _require(
            source is not None
            and item["key"] == source["evidence"]["key"]
            and item["changed_field"] == "project_ids_json"
            and item["after_adds_project_id"] == project_id,
            "association-only correction evidence differs from its enumerated delta",
        )
    added_ids = [item["evidence_id"] for item in added]
    shared_ids = [item["evidence_id"] for item in shared]
    _require(
        len(set(added_ids)) == len(added_ids)
        and len(set(shared_ids)) == len(shared_ids)
        and not set(added_ids).intersection(shared_ids)
        and set(added_ids) | set(shared_ids) == set(by_id),
        "evidence delta does not cover exactly the correction evidence",
    )
    before, after = located["projects"]["row"], corrected["projects"]
    effect = {
        "physical_sites": 0,
        "projects": 0,
        "evidence": len(added) - len(evidence["removed"]),
        "reviewed_site_locator_projects": int(_is_reviewed_locator(after))
        - int(_is_reviewed_locator(before)),
        "host_estate_context_projects": int(_is_host_estate_context(after))
        - int(_is_host_estate_context(before)),
        "official_boundary_projects": int(core._is_official_boundary(after))
        - int(core._is_official_boundary(before)),
        "countries": 0,
        "non_us_sites": 0,
    }
    counts = _keys(deltas[count_keys[0]], CORRECTION_COUNT_KEYS, "correction count effect")
    _require(
        canonical_sha256(counts) == canonical_sha256(effect),
        "baseline correction count effect differs from its enumerated delta",
    )
    return {"changed_fields": changed_fields, "evidence": evidence, "effect": effect}


def _baseline_correction(
    entry: Any,
    root: Path,
    baseline: Mapping[str, Any],
    sources: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
) -> dict[str, Any]:
    """Validate one v2 baseline correction fail-closed and derive its rows."""
    _keys(entry, BASELINE_CORRECTION_KEYS, "baseline correction")
    correction_id = _text(entry["correction_id"], "correction ID")
    _require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", correction_id) is not None,
        "unsafe correction ID",
    )
    _require(
        canonical_sha256(entry)
        == review_pins.baseline_correction_sha256.get(correction_id),
        f"independent baseline correction review pin differs: {correction_id}",
    )
    project_key = _text(entry["project_stable_key"], "corrected project key")
    site_key = _text(entry["physical_site_stable_key"], "corrected site key")
    _text(entry["reason"], "baseline correction reason")
    identity_id = _text(entry["identity_source_id"], "correction identity source")
    located = _frozen_rows(entry["frozen_rows"], baseline, project_key, site_key)
    binding = _keys(
        entry["geometry"],
        {"source_id", "record_pointer", "record_sha256"},
        "baseline correction geometry binding",
    )
    source_id = _text(binding["source_id"], "correction geometry source")
    record = _record(
        sources,
        source_id,
        binding["record_pointer"],
        binding["record_sha256"],
        "baseline correction geometry",
    )
    _baseline_correction_geometry(record, entry, located)
    _require(
        _unique_text(record["identity_source_ids"], "correction identity source IDs")
        == [identity_id],
        "baseline correction identity binding differs",
    )
    geometry_ids = _unique_text(
        record["geometry_source_ids"], "correction geometry source IDs"
    )
    evidence_ids = _unique_text(entry["evidence_source_ids"], "correction evidence IDs")
    _require(
        source_id in geometry_ids
        and set(evidence_ids) == set(geometry_ids)
        and set(geometry_ids).issubset(sources),
        "baseline correction evidence sources differ from its geometry sources",
    )
    document = sources[source_id]["document"]
    _correction_document(document, sources, source_id, reviewed_at)
    supersedes = document.get("supersedes")
    superseded, inherited_lines = _superseded(
        supersedes, root, baseline, located, entry
    )
    reused = sources[source_id]["evidence"]
    _reused_capture(reused, superseded, supersedes)
    _unchanged_bindings(document, root, baseline, located, entry, sources)
    invariants = _preservation_invariants(
        document, located, record, superseded, reused
    )
    project, site, feature = _corrected_rows(record, located, sources, source_id)
    corrected = {"projects": project, "sites": site, "feature": feature}
    deltas = _exact_row_deltas(document, located, corrected, entry, sources, geometry_ids)
    return {
        "entry": entry,
        "correction_id": correction_id,
        "located": located,
        "record": record,
        "supersedes": supersedes,
        "primary_source_id": source_id,
        "geometry_source_ids": geometry_ids,
        "project": project,
        "site": site,
        "feature": feature,
        "changed_fields": deltas["changed_fields"],
        "evidence_delta": deltas["evidence"],
        "count_effect": deltas["effect"],
        "invariants": invariants,
        "inherited_through_lines": inherited_lines,
    }


def _baseline_corrections(
    entries: Any,
    root: Path,
    baseline: Mapping[str, Any],
    sources: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
    acceptance_sources: set[str],
    date_only_sources: set[str],
) -> list[dict[str, Any]]:
    _require(
        isinstance(entries, list) and bool(entries),
        "v2 contracts need at least one baseline correction",
    )
    validated = []
    for entry in entries:
        item = _baseline_correction(
            entry, root, baseline, sources, review_pins, reviewed_at
        )
        _require(
            all(
                item[key] != other[key]
                for other in validated
                for key in ("correction_id", "primary_source_id")
            )
            and all(
                item["entry"][key] != other["entry"][key]
                for other in validated
                for key in ("project_stable_key", "physical_site_stable_key")
            ),
            "duplicate baseline correction target",
        )
        validated.append(item)
    _require(
        set(review_pins.baseline_correction_sha256)
        == {item["correction_id"] for item in validated},
        "baseline correction review pin inventory differs",
    )
    reused = {item["primary_source_id"] for item in validated}
    for source_id in date_only_sources:
        _require(
            source_id in reused and source_id not in acceptance_sources,
            "date-only retrieval is accepted only for a baseline correction's "
            "reused frozen capture",
        )
    return validated


def _geometry_positions(geometry: Mapping[str, Any]) -> list[list[float]]:
    kind, coordinates = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return [coordinates]
    polygons = [coordinates] if kind == "Polygon" else coordinates
    return [point for polygon in polygons for ring in polygon for point in ring]


def _geometry_polygons(geometry: Mapping[str, Any]) -> list[list[list[list[float]]]]:
    kind, coordinates = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return []
    return [coordinates] if kind == "Polygon" else coordinates


def _on_ring(point: list[float], ring: list[list[float]]) -> bool:
    x, y = point
    return any(
        abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) < 1e-12
        and min(ax, bx) <= x <= max(ax, bx)
        and min(ay, by) <= y <= max(ay, by)
        for (ax, ay), (bx, by) in zip(ring, ring[1:])
    )


def _covers(polygons: list, point: list[float]) -> bool:
    return any(
        _inside_ring(point, polygon[0])
        and not any(
            _inside_ring(point, hole) and not _on_ring(point, hole)
            for hole in polygon[1:]
        )
        for polygon in polygons
    )


def _geometries_intersect(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Closed-set intersection of two validated Point/Polygon/MultiPolygon values."""
    boxes = []
    for geometry in (first, second):
        points = _geometry_positions(geometry)
        boxes.append(
            (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            )
        )
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = boxes
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return False
    first_polygons, second_polygons = (
        _geometry_polygons(first),
        _geometry_polygons(second),
    )
    if not first_polygons and not second_polygons:
        return first["coordinates"] == second["coordinates"]
    if not first_polygons:
        return _covers(second_polygons, first["coordinates"])
    if not second_polygons:
        return _covers(first_polygons, second["coordinates"])

    def edges(polygons: list, box: tuple) -> list:
        x0, y0, x1, y1 = box
        return [
            (a, b)
            for polygon in polygons
            for ring in polygon
            for a, b in zip(ring, ring[1:])
            if max(a[0], b[0]) >= x0
            and min(a[0], b[0]) <= x1
            and max(a[1], b[1]) >= y0
            and min(a[1], b[1]) <= y1
        ]

    if any(
        _segments_intersect(a, b, c, d)
        for a, b in edges(first_polygons, boxes[1])
        for c, d in edges(second_polygons, boxes[0])
    ):
        return True
    return any(_covers(first_polygons, polygon[0][0]) for polygon in second_polygons) or any(
        _covers(second_polygons, polygon[0][0]) for polygon in first_polygons
    )


def _locator_exceptions(
    projects: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    corrections: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    by_project = {item["entry"]["project_stable_key"]: item for item in corrections}
    geometries = {
        row["physical_site_stable_key"]: _json_field(row["geometry_json"], "site geometry")
        for row in sites
    }
    rows = []
    for project in projects:
        if not _is_host_estate_context(project):
            continue
        correction = by_project.get(project["project_stable_key"])
        _require(
            correction is not None,
            "host-estate context requires a pinned baseline correction",
        )
        site_key = project["physical_site_stable_key"]
        rows.append(
            {
                "project_stable_key": project["project_stable_key"],
                "project_id": project["project_id"],
                "physical_site_stable_key": site_key,
                "site_id": project["site_id"],
                "correction_id": correction["correction_id"],
                "geometry_use_scope": project["geometry_use_scope"],
                "verification_posture": project["verification_posture"],
                "counted_as_physical_site": True,
                "counted_as_reviewed_site_locator": False,
                "counted_as_official_boundary": False,
                "display_anchor_is_site_position": False,
                "geometry_intersects_site_keys": sorted(
                    key
                    for key, other in geometries.items()
                    if key != site_key
                    and _geometries_intersect(geometries[site_key], other)
                ),
            }
        )
    return {
        "scope": "Counted projects whose inherited geometry is host-estate locality context only, set by a pinned baseline correction. They are excluded from reviewed_site_locator_projects and official_boundary_projects; the display anchor is not a site position, and other selected sites may lie inside the host estate. A site-count claim must disclose them.",
        "host_estate_context_projects": len(rows),
        "projects": rows,
    }


def _correction_report(
    correction: Mapping[str, Any], batch: ValidatedBatch
) -> dict[str, Any]:
    entry = correction["entry"]
    spec = batch.sources[correction["primary_source_id"]]["spec"]
    supersedes = correction["supersedes"]
    delta = correction["evidence_delta"]
    return {
        "correction_id": correction["correction_id"],
        "physical_site_stable_key": entry["physical_site_stable_key"],
        "project_stable_key": entry["project_stable_key"],
        "site_id": correction["site"]["site_id"],
        "project_id": correction["project"]["project_id"],
        "correction_record": {
            "source_id": correction["primary_source_id"],
            "path": spec["path"],
            "sha256": spec["sha256"],
            "record_pointer": entry["geometry"]["record_pointer"],
            "record_sha256": entry["geometry"]["record_sha256"],
        },
        "superseded_record": {
            "source_path": supersedes["source_path"],
            "source_file_sha256": supersedes["source_file_sha256"],
            "evidence_id": supersedes["evidence_id"],
            "locator_id": supersedes["locator_id"],
        },
        "frozen_rows": entry["frozen_rows"],
        "changed_fields": correction["changed_fields"],
        "evidence_rows": {
            "removed": [item["evidence_id"] for item in delta["removed"]],
            "added": sorted(item["evidence_id"] for item in delta["added"]),
            "association_only": sorted(
                item["evidence_id"] for item in delta["association_only"]
            ),
        },
        "count_effect": correction["count_effect"],
        "unchanged": [
            "physical_site",
            "project",
            "geometry",
            "display_anchor",
            "geometry_authority",
            "lifecycle_observation",
            "status_evidence",
        ],
        "additional_sites": 0,
        "reason": entry["reason"],
    }


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
    # Only a v2 contract may carry baseline_corrections; v1 keeps its exact keys.
    corrections_enabled = (
        isinstance(contract, dict) and contract.get("schema_version") == SCHEMA_VERSION_V2
    )
    _keys(
        contract,
        CONTRACT_KEYS_V2 if corrections_enabled else CONTRACT_KEYS,
        "batch contract",
    )
    _require(
        contract["schema_version"] == SCHEMA_VERSION or corrections_enabled,
        "batch schema version differs",
    )
    _require(
        isinstance(review_pins.baseline_correction_sha256, Mapping)
        and (corrections_enabled or not review_pins.baseline_correction_sha256),
        "baseline correction review pins require a v2 contract",
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
    date_only_sources: set[str] = set()
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
        # A v2 date-only retrieval must later prove it is a correction's reused
        # frozen capture; v1 and every other source keep the timezone rule.
        inherited_date = (
            corrections_enabled
            and isinstance(evidence, dict)
            and _date_only(evidence.get("retrieved_at"))
        )
        projection = _source_evidence(
            evidence, source_id, inherited_date_only_retrieval=inherited_date
        )
        if inherited_date:
            date_only_sources.add(source_id)
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
    corrections: list[dict[str, Any]] = []
    if corrections_enabled:
        corrections = _baseline_corrections(
            contract["baseline_corrections"],
            root,
            baseline,
            sources,
            review_pins,
            reviewed_at,
            set(used_sources),
            date_only_sources,
        )
        for correction in corrections:
            used_sources.update(correction["geometry_source_ids"])
    _require(used_sources == set(sources), "unused source documents are not allowed")
    batch = ValidatedBatch(
        root,
        contract_path,
        review_pins,
        contract,
        baseline,
        sources,
        tuple(validated),
        tuple(corrections),
    )
    if corrections:
        # The evidence deltas depend on acceptance usage, so phase one derives
        # them once here; build and validate_draft derive them again identically.
        _intersecting_rows_unchanged(batch, _delta_rows(batch))
    return batch


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
                "verification_posture": _verification_posture(
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
    # Baseline corrections: geometry-only usage of the correction sources. A row
    # enumerated as added must be new; a shared row must already exist through
    # an acceptance with that role and only gains the project association.
    acceptance_roles = {
        identifier: frozenset(item["roles"]) for identifier, item in usage.items()
    }
    for correction in batch.baseline_corrections:
        project_id = correction["project"]["project_id"]
        delta = correction["evidence_delta"]
        added = {item["evidence_id"] for item in delta["added"]}
        shared = {item["evidence_id"] for item in delta["association_only"]}
        for source_id in correction["geometry_source_ids"]:
            evidence = batch.sources[source_id]["projection"]
            identifier = evidence["evidence_id"]
            if identifier in shared:
                _require(
                    "geometry" in acceptance_roles.get(identifier, frozenset()),
                    "association-only correction evidence must already carry its role",
                )
            else:
                _require(
                    identifier in added and identifier not in acceptance_roles,
                    "added correction evidence is already used by an acceptance",
                )
            evidence_pool[identifier] = evidence
            usage[identifier]["roles"].add("geometry")
            usage[identifier]["projects"].add(project_id)
    for correction in batch.baseline_corrections:
        for item in correction["evidence_delta"]["added"]:
            usage_item = usage[item["evidence_id"]]
            _require(
                sorted(usage_item["roles"]) == item["roles"]
                and sorted(usage_item["projects"]) == item["project_ids"],
                "added correction evidence row differs from its enumerated delta",
            )
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


def _inherited(
    batch: ValidatedBatch,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes], list[Any]]:
    """Inherited rows, raw CSV bytes and features, with pinned corrections applied.

    Without corrections these are the frozen v0.17 rows, bytes and features.
    A correction replaces exactly its project/site lines and feature with the
    validated derivations and drops the superseded evidence line; every other
    inherited line keeps its frozen bytes.
    """
    rows = {name: batch.baseline[name] for name in TABLE_FIELDS}
    raw = {name: batch.baseline["files"][f"{name}.csv"] for name in TABLE_FIELDS}
    features = _json(batch.baseline["files"]["sites.geojson"], "baseline GeoJSON")[
        "features"
    ]
    if not batch.baseline_corrections:
        return rows, raw, features
    rows = {name: list(value) for name, value in rows.items()}
    lines = {
        name: _csv_lines(raw[name], len(rows[name]), f"frozen {name}.csv")
        for name in TABLE_FIELDS
    }
    features = list(features)
    dropped: set[int] = set()
    for correction in batch.baseline_corrections:
        located = correction["located"]
        for table, key in (("projects", "project"), ("sites", "site")):
            index = located[table]["index"]
            rows[table][index] = correction[key]
            lines[table][index + 1] = _csv_line(correction[key], TABLE_FIELDS[table])
        dropped.add(located["evidence"]["index"])
        features[located["feature"]["index"]] = correction["feature"]
    rows["evidence"] = [
        row for index, row in enumerate(rows["evidence"]) if index not in dropped
    ]
    lines["evidence"] = [
        line for number, line in enumerate(lines["evidence"]) if number - 1 not in dropped
    ]
    return rows, {name: b"\n".join(value) for name, value in lines.items()}, features


def _payloads(batch: ValidatedBatch) -> tuple[dict[str, bytes], dict[str, Any]]:
    corrected = batch.contract["schema_version"] == SCHEMA_VERSION_V2
    delta = _delta_rows(batch)
    inherited_rows, inherited_raw, inherited_features = _inherited(batch)
    tables = {name: [*inherited_rows[name], *delta[name]] for name in delta}
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
    if batch.baseline_corrections:
        output_evidence = {row["evidence_id"] for row in evidence}
        for correction in batch.baseline_corrections:
            referenced = {
                correction["project"]["geometry_evidence_id"],
                correction["project"]["status_evidence_id"],
                *_json_field(
                    correction["site"]["geometry_evidence_ids_json"],
                    "corrected site evidence",
                ),
            }
            _require(
                referenced.issubset(output_evidence)
                and correction["located"]["evidence"]["row"]["evidence_id"]
                not in output_evidence,
                "corrected rows and output evidence differ",
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
            _is_reviewed_locator(row) for row in projects
        ),
    }
    if corrected:
        counts["host_estate_context_projects"] = sum(
            _is_host_estate_context(row) for row in projects
        )
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
        "format": "datacenter-atlas-v018-draft-selection-v2"
        if corrected
        else "datacenter-atlas-v018-draft-selection-v1",
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
    if corrected:
        report["baseline_corrections"] = [
            _correction_report(correction, batch)
            for correction in batch.baseline_corrections
        ]
        report["locator_exceptions"] = _locator_exceptions(
            projects, sites, batch.baseline_corrections
        )
        provenance["independent_baseline_correction_review_sha256"] = dict(
            batch.pins.baseline_correction_sha256
        )
        provenance["baseline_corrections"] = batch.contract["baseline_corrections"]
    geojson = _json(batch.baseline["files"]["sites.geojson"], "baseline GeoJSON")
    geojson = {
        **geojson,
        "name": "Data Center Atlas v0.18 expansion draft",
        "release_status": "draft",
        "features": [
            *inherited_features,
            *core._geojson(delta["sites"])["features"],
        ],
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
                    + (" and pinned baseline corrections" if corrected else "")
                )
    schema["v018_draft_contract"] = {
        "schema_version": batch.contract["schema_version"],
        "release_status": "draft",
        "publishable_as_final": False,
        "location_bases": sorted(LOCATION_BASES),
        "geometry_use_scopes": sorted(USE_SCOPES),
        "schema_documentation": "datacenter_atlas/verified_construction_core_v018.py module docstring",
    }
    if corrected:
        schema["v018_draft_contract"].update(
            {
                "baseline_correction_location_bases": sorted(
                    BASELINE_CORRECTION_LOCATION_BASES
                ),
                "baseline_correction_geometry_source_entity_kinds": sorted(
                    BASELINE_CORRECTION_ENTITY_KINDS
                ),
                "baseline_correction_geometry_use_scopes": sorted(
                    BASELINE_CORRECTION_USE_SCOPES
                ),
                "baseline_correction_verification_postures": [
                    HOST_ESTATE_CONTEXT_POSTURE
                ],
                "baseline_correction_scope": "Accepted only through pinned baseline corrections of inherited v0.17 rows, never for acceptances. Host-estate context is not a reviewed site locator, official boundary or site position, and is excluded from reviewed_site_locator_projects.",
            }
        )
    attribution = (
        batch.baseline["files"]["ATTRIBUTION.txt"]
        + b"\n\nV0.18 DRAFT ADDITIONAL SOURCE ATTRIBUTION\n"
    )
    for source_id, source in sorted(batch.sources.items()):
        row = source["projection"]
        attribution += (
            f"\n{source_id}\n{row['attribution']}\n{row['license']}\n{row['source_url']}\nSource input: {source['spec']['path']}\n"
        ).encode()
    preservation = "All inherited rows and features are preserved. "
    if corrected:
        rescoped = len(batch.baseline_corrections)
        removed = sum(
            len(item["evidence_delta"]["removed"]) for item in batch.baseline_corrections
        )
        shared = sum(
            len(item["evidence_delta"]["association_only"])
            for item in batch.baseline_corrections
        )

        def plural(count: int, noun: str) -> str:
            return f"{count} {noun}{'' if count == 1 else 's'}"

        preservation = (
            "All inherited rows and features are preserved, except the changes made "
            "by pinned baseline corrections: the enumerated fields of "
            f"{plural(rescoped, 're-scoped project row')}, "
            f"{plural(rescoped, 'site row')} and {plural(rescoped, 'feature')}; "
            f"{plural(removed, 'superseded evidence row')} dropped; and "
            f"{plural(shared, 'shared evidence row')} gaining only the corrected "
            "project association. "
        )
    corrections_text = ""
    if corrected:
        correction_count = len(batch.baseline_corrections)
        host_estate = counts["host_estate_context_projects"]
        correction_ids = ", ".join(
            sorted(item["correction_id"] for item in batch.baseline_corrections)
        )
        corrections_text = (
            f"Baseline corrections: {correction_count} pinned versioned "
            f"correction{'' if correction_count == 1 else 's'} ({correction_ids}) "
            f"re-scope{'s' if correction_count == 1 else ''} inherited locator "
            "semantics and evidence only; no site, project, geometry, display anchor "
            "or lifecycle observation is added, removed or moved. "
            f"{host_estate} counted project{'' if host_estate == 1 else 's'} "
            f"{'has' if host_estate == 1 else 'have'} host-estate locality context only, "
            "not a reviewed site locator; such a display anchor is not a site position. "
            "See selection-report.json baseline_corrections and locator_exceptions.\n\n"
        )
    readme = (
        f"# Data Center Atlas v0.18 expansion draft\n\n"
        f"{counts['physical_sites']} physical sites, {counts['projects']} projects, {counts['countries']} countries. "
        f"The frozen v0.17 baseline has {baseline_count} sites; this reviewed draft adds {len(delta['sites'])}. "
        f"The requested expansion target remains {target} total sites ({TARGET_ADDITIONAL_SITES} additional).\n\n"
        "This is an opt-in local draft, not a public release or a claim of goal completion. "
        "The public builder still defaults to v0.17. "
        f"{preservation}"
        "Locators are not building footprints or surveyed boundaries unless their explicit semantics say otherwise. "
        "No additional roles, workloads, capacities, energy, or efficiency observations are inferred.\n\n"
        f"{corrections_text}"
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
        files[f"{name}.csv"] = inherited_raw[name] + appended
    manifest = {
        "format": DRAFT_MANIFEST_FORMAT_V2 if corrected else DRAFT_MANIFEST_FORMAT_V1,
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
