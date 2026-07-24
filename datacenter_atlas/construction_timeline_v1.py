"""Immutable source-scoped lifecycle timeline derived from frozen open seed v60.

This carrier exports every raw lifecycle observation in the accepted v60
database.  It deliberately does not resolve identities across sources, infer a
current status, assume that a latest observation persists, interpolate missing
milestones, convert forecasts into observations, or promote satellite/CV review
results into lifecycle evidence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from . import open_seed_release_v5
from . import open_seed_v60
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-20-public-open-v1"
AS_OF = "2026-07-20"
GENERATED_AT = "2026-07-21T04:35:00Z"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-20-open-seed-v60"
OPEN_SEED_DEFINITION_SHA256 = (
    "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430"
)
OPEN_SEED_TREE_SHA256 = (
    "1d58652f691b8030717b7af6c61d2717b2b3427520f7d1b402b75b7670beb138"
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v1"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v1"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v1"
TIMELINE_FORMAT = "datacenter-atlas-source-scoped-entity-timeline-v1"
SCHEMA_VERSION = 1

OBSERVATIONS_FILENAME = "lifecycle-observations.csv"
TIMELINES_FILENAME = "entity-timelines.jsonl"
COVERAGE_FILENAME = "coverage.json"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUNDLE_FILES = frozenset(
    {
        OBSERVATIONS_FILENAME,
        TIMELINES_FILENAME,
        COVERAGE_FILENAME,
        README_FILENAME,
        ATTRIBUTION_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)

FROZEN_DIRECTORY_MODE = 0o555
FROZEN_FILE_MODE = 0o444

SCOPE = {
    "cross_source_identity_resolution_applied": False,
    "current_construction_claimed": False,
    "current_status_classification": "unknown",
    "forecast_conversion_applied": False,
    "interpolation_applied": False,
    "latest_observation_persistence_assumed": False,
    "lifecycle_status_semantics": "dated_raw_observation",
    "quarterly_2017_2032_parity_claimed": False,
    "satellite_cv_promoted_to_lifecycle": False,
    "single_old_observation_current_status": "unknown",
    "source_scoped_identity_only": True,
    "unique_physical_sites": None,
}

OBSERVATION_FIELDS = (
    "observation_id",
    "entity_id",
    "entity_stable_key",
    "entity_kind",
    "entity_name",
    "entity_country",
    "observed_date",
    "valid_to_date",
    "status",
    "method",
    "confidence",
    "notes",
    "recorded_at",
    "superseded_at",
    "evidence_id",
    "evidence_kind",
    "evidence_source_family",
    "evidence_title",
    "evidence_publisher",
    "evidence_source_url",
    "evidence_license",
    "evidence_attribution",
    "evidence_published_at",
    "evidence_retrieved_at",
    "evidence_content_hash",
)

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 412,
    "multi_observation_entities": 14,
    "raw_lifecycle_observations": 426,
    "repeated_status_multi_observation_entities": 4,
    "single_observation_entities": 398,
    "single_old_observation_entities": 24,
    "source_families": 175,
    "status_changing_multi_observation_entities": 10,
}


class ConstructionTimelineError(ValueError):
    """Raised when a timeline input, reconstruction, or bundle differs."""


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    timeline_id: str
    as_of: str
    generated_at: str
    open_seed_definition: Path
    open_seed_release: Path
    expected: Mapping[str, Any]


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(_regular_bytes(path, str(path)))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_json_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ConstructionTimelineError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionTimelineError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionTimelineError(f"{label} must be a JSON object")
    return value


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConstructionTimelineError(f"{label} must be non-empty text")
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _required_text(value, label)
    if not text.endswith("Z"):
        raise ConstructionTimelineError(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConstructionTimelineError(f"{label} must be a timestamp") from error
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical != text:
        raise ConstructionTimelineError(f"{label} must use second precision")
    return text


def _resolve(definition: Path, value: Any, label: str) -> Path:
    text = _required_text(value, label)
    path = Path(text)
    if not path.is_absolute():
        path = definition.parent / path
    return Path(os.path.abspath(os.fspath(path)))


def _checkpoint(value: Any, label: str) -> tuple[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise ConstructionTimelineError(f"{label} checkpoint schema is invalid")
    path = _required_text(value.get("path"), f"{label} path")
    digest = _required_text(value.get("sha256"), f"{label} SHA-256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ConstructionTimelineError(f"{label} SHA-256 is invalid")
    return path, digest


def _load_definition(path_value: str | Path) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = _regular_bytes(path, "timeline definition")
    document = _json_object(raw, "timeline definition")
    if raw != _canonical_json(document):
        raise ConstructionTimelineError("timeline definition must be canonical JSON")
    fields = {
        "as_of",
        "expected",
        "format",
        "generated_at",
        "open_seed",
        "schema_version",
        "scope",
        "timeline_id",
    }
    if set(document) != fields:
        raise ConstructionTimelineError("timeline definition schema is invalid")
    if document["schema_version"] != SCHEMA_VERSION or document["format"] != DEFINITION_FORMAT:
        raise ConstructionTimelineError("timeline definition format is unsupported")
    if document["timeline_id"] != TIMELINE_ID:
        raise ConstructionTimelineError("timeline_id differs from the accepted v1 ID")
    if document["as_of"] != AS_OF:
        raise ConstructionTimelineError("timeline as_of differs from open seed v60")
    generated_at = _timestamp(document["generated_at"], "generated_at")
    if generated_at != GENERATED_AT or generated_at <= open_seed_release_v5.RECORDED_AT:
        raise ConstructionTimelineError("timeline generated_at boundary is invalid")
    if document["scope"] != SCOPE:
        raise ConstructionTimelineError("timeline scope guardrails differ")
    expected = document["expected"]
    if not isinstance(expected, Mapping) or dict(expected) != EXPECTED_COUNTS:
        raise ConstructionTimelineError("timeline expected counts differ")
    open_seed = document["open_seed"]
    if not isinstance(open_seed, Mapping) or set(open_seed) != {
        "definition",
        "expected_release_tree_sha256",
        "manifest",
        "release_path",
    }:
        raise ConstructionTimelineError("open_seed checkpoint schema is invalid")
    definition_display, definition_digest = _checkpoint(
        open_seed["definition"], "open seed definition"
    )
    manifest_display, manifest_digest = _checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    release_path = _resolve(path, open_seed["release_path"], "open seed release_path")
    open_seed_definition = _resolve(path, definition_display, "open seed definition path")
    open_seed_manifest = _resolve(path, manifest_display, "open seed manifest path")
    if (
        open_seed_definition != OPEN_SEED_DEFINITION
        or release_path != OPEN_SEED_RELEASE
        or open_seed_manifest != OPEN_SEED_RELEASE / MANIFEST_FILENAME
        or definition_digest != OPEN_SEED_DEFINITION_SHA256
        or manifest_digest != OPEN_SEED_MANIFEST_SHA256
        or open_seed["expected_release_tree_sha256"] != OPEN_SEED_TREE_SHA256
    ):
        raise ConstructionTimelineError("open seed v60 accepted pins differ")
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=document["timeline_id"],
        as_of=document["as_of"],
        generated_at=generated_at,
        open_seed_definition=open_seed_definition,
        open_seed_release=release_path,
        expected=dict(expected),
    )


def _validate_open_seed(definition: _Definition) -> dict[str, Any]:
    if _sha256_file(definition.open_seed_definition) != OPEN_SEED_DEFINITION_SHA256:
        raise ConstructionTimelineError("frozen v60 definition hash differs")
    if _sha256_file(definition.open_seed_release / MANIFEST_FILENAME) != OPEN_SEED_MANIFEST_SHA256:
        raise ConstructionTimelineError("frozen v60 manifest hash differs")
    try:
        observed_tree = tree_digest(definition.open_seed_release)
    except SystemExit as error:
        raise ConstructionTimelineError("frozen v60 release tree is invalid") from error
    if observed_tree != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen v60 release tree differs")
    try:
        validated = open_seed_release_v5.validate_open_seed_release_v5(
            definition.open_seed_definition,
            definition.open_seed_release,
        )
    except (ValueError, OSError, SystemExit) as error:
        raise ConstructionTimelineError("frozen v60 validation failed") from error
    frozen_manifest = _json_object(
        _regular_bytes(
            definition.open_seed_release / MANIFEST_FILENAME,
            "frozen v60 manifest",
        ),
        "frozen v60 manifest",
    )
    if validated != frozen_manifest:
        raise ConstructionTimelineError("validated v60 manifest differs")
    return validated


def _labels(release: Path) -> dict[str, dict[str, str]]:
    raw = _regular_bytes(release / "entities.csv", "v60 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v60 entities.csv is not UTF-8") from error
    if len(rows) != 725:
        raise ConstructionTimelineError("v60 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v60 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _reconstruct_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_open_seed(definition)
    v60_document = _json_object(
        _regular_bytes(definition.open_seed_definition, "v60 definition"),
        "v60 definition",
    )
    base = _json_object(
        _regular_bytes(open_seed_v60.BASE_DEFINITION, "v59 base definition"),
        "v59 base definition",
    )
    try:
        selected_rows, paths = open_seed_v60.selected_inputs(base)
    except (ValueError, OSError, SystemExit) as error:
        raise ConstructionTimelineError("v60 source selection failed") from error
    if selected_rows != v60_document.get("curated_inputs"):
        raise ConstructionTimelineError("fresh v60 source inventory differs")
    labels = _labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v1-db-", dir="/private/tmp"
    ) as temporary:
        try:
            connection = open_seed_v60._build_database(
                base, paths, Path(temporary) / "atlas.sqlite"
            )
        except (ValueError, OSError, SystemExit) as error:
            raise ConstructionTimelineError("fresh v60 database rebuild failed") from error
        try:
            raw_rows = connection.execute(
                """
                SELECT lifecycle.id AS observation_id,
                       lifecycle.entity_id AS entity_id,
                       entities.stable_key AS entity_stable_key,
                       entities.kind AS entity_kind,
                       lifecycle.as_of_date AS observed_date,
                       lifecycle.valid_to_date AS valid_to_date,
                       lifecycle.status AS status,
                       lifecycle.method AS method,
                       lifecycle.confidence AS confidence,
                       lifecycle.notes AS notes,
                       lifecycle.recorded_at AS recorded_at,
                       lifecycle.superseded_at AS superseded_at,
                       evidence.id AS evidence_id,
                       evidence.kind AS evidence_kind,
                       evidence.source_family AS evidence_source_family,
                       evidence.title AS evidence_title,
                       evidence.publisher AS evidence_publisher,
                       evidence.source_url AS evidence_source_url,
                       evidence.license AS evidence_license,
                       evidence.attribution AS evidence_attribution,
                       evidence.published_at AS evidence_published_at,
                       evidence.retrieved_at AS evidence_retrieved_at,
                       evidence.content_hash AS evidence_content_hash
                FROM lifecycle_observations AS lifecycle
                JOIN entities ON entities.id = lifecycle.entity_id
                JOIN evidence ON evidence.id = lifecycle.evidence_id
                ORDER BY entities.stable_key, lifecycle.as_of_date,
                         lifecycle.recorded_at, lifecycle.id
                """
            ).fetchall()
        finally:
            connection.close()

    observations: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row = dict(raw_row)
        label = labels.get(row["entity_id"])
        if label is None:
            raise ConstructionTimelineError("lifecycle entity is absent from v60 labels")
        if (
            label.get("stable_key") != row["entity_stable_key"]
            or label.get("entity_kind") != row["entity_kind"]
            or not label.get("name")
            or not label.get("country")
        ):
            raise ConstructionTimelineError("v60 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        row = {field: row[field] for field in OBSERVATION_FIELDS}
        observations.append(row)
    if len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]:
        raise ConstructionTimelineError("raw v60 lifecycle count differs")
    if len({row["observation_id"] for row in observations}) != len(observations):
        raise ConstructionTimelineError("lifecycle observation IDs are not unique")
    return observations


def _csv_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return str(value)
    return value


def _csv_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=OBSERVATION_FIELDS,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_scalar(row[field]) for field in OBSERVATION_FIELDS})
    return stream.getvalue().encode("utf-8")


def _timeline_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: row[field]
        for field in OBSERVATION_FIELDS
        if field
        not in {
            "entity_id",
            "entity_stable_key",
            "entity_kind",
            "entity_name",
            "entity_country",
        }
    }


def _timeline_rows(
    observations: list[dict[str, Any]], *, as_of: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        grouped.setdefault(observation["entity_id"], []).append(observation)
    as_of_date = date.fromisoformat(as_of)
    rows: list[dict[str, Any]] = []
    for entity_id, timeline in grouped.items():
        first = timeline[0]
        statuses = {item["status"] for item in timeline}
        single_old = len(timeline) == 1 and (
            as_of_date - date.fromisoformat(timeline[0]["observed_date"])
        ).days > 365
        rows.append(
            {
                "current_construction_claim": False,
                "current_status_classification": "unknown",
                "entity_country": first["entity_country"],
                "entity_id": entity_id,
                "entity_kind": first["entity_kind"],
                "entity_name": first["entity_name"],
                "entity_stable_key": first["entity_stable_key"],
                "format": TIMELINE_FORMAT,
                "has_multiple_observations": len(timeline) > 1,
                "has_status_change": len(statuses) > 1,
                "latest_observation_persistence_assumed": False,
                "observation_count": len(timeline),
                "observations": [_timeline_observation(item) for item in timeline],
                "schema_version": SCHEMA_VERSION,
                "single_old_observation_current_unknown": single_old,
                "source_scoped_identity_only": True,
            }
        )
    rows.sort(key=lambda item: (item["entity_stable_key"], item["entity_id"]))
    return rows


def _coverage(
    observations: list[dict[str, Any]],
    timelines: list[dict[str, Any]],
    definition: _Definition,
) -> dict[str, Any]:
    multi = [row for row in timelines if row["has_multiple_observations"]]
    single = [row for row in timelines if not row["has_multiple_observations"]]
    changing = [row for row in multi if row["has_status_change"]]
    repeated = [row for row in multi if not row["has_status_change"]]
    single_old = [row for row in single if row["single_old_observation_current_unknown"]]
    counts = {
        "entities_with_lifecycle_observations": len(timelines),
        "multi_observation_entities": len(multi),
        "raw_lifecycle_observations": len(observations),
        "repeated_status_multi_observation_entities": len(repeated),
        "single_observation_entities": len(single),
        "single_old_observation_entities": len(single_old),
        "source_families": len(
            {row["evidence_source_family"] for row in observations}
        ),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineError(
            f"timeline coverage counts differ: {counts}"
        )
    return {
        "as_of": definition.as_of,
        "counts": counts,
        "current_status_classification_counts": {"unknown": len(timelines)},
        "date_coverage": {
            "latest_observed_date": max(row["observed_date"] for row in observations),
            "oldest_observed_date": min(row["observed_date"] for row in observations),
        },
        "format": COVERAGE_FORMAT,
        "generated_at": definition.generated_at,
        "multi_observation_timelines": [
            {
                "entity_stable_key": row["entity_stable_key"],
                "observations": [
                    {
                        "observed_date": observation["observed_date"],
                        "status": observation["status"],
                    }
                    for observation in row["observations"]
                ],
                "status_change": row["has_status_change"],
            }
            for row in multi
        ],
        "observation_entity_kind_counts": dict(
            sorted(Counter(row["entity_kind"] for row in observations).items())
        ),
        "observation_status_counts": dict(
            sorted(Counter(row["status"] for row in observations).items())
        ),
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "source_family_observation_counts": dict(
            sorted(
                Counter(
                    row["evidence_source_family"] for row in observations
                ).items()
            )
        ),
        "timeline_entity_kind_counts": dict(
            sorted(Counter(row["entity_kind"] for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v1\n\n"
        f"This immutable artifact reconstructs frozen open seed v60 and exports all "
        f"{counts['raw_lifecycle_observations']} raw lifecycle observations for "
        f"{counts['entities_with_lifecycle_observations']} source-scoped entities. "
        "`lifecycle-observations.csv` is the flat provenance-preserving carrier; "
        "`entity-timelines.jsonl` groups the same observations by exact v60 entity "
        "identity, and `coverage.json` reports deterministic coverage.\n\n"
        f"There are {counts['multi_observation_entities']} multi-observation entity "
        f"histories, including {counts['status_changing_multi_observation_entities']} "
        "with more than one observed status. Historical construction-to-operational "
        "sequences are dated evidence, not a claim that either status remains current.\n\n"
        "Name and country are the v60 release-projected entity labels used to make the "
        "raw lifecycle rows legible; they are not interpolated observation-time labels. "
        "Every timeline is source-scoped. Cross-source duplicates remain unresolved, "
        "unique physical sites remain null, current status remains unknown, and the "
        "latest observation is never assumed to persist. No forecast is converted into "
        "a milestone, no missing milestone is interpolated, no satellite/CV review is "
        "promoted, and no quarterly 2017–2032 parity claim is made.\n\n"
        f"The {counts['single_old_observation_entities']} single-observation timelines "
        "older than 365 days are explicitly labeled current-unknown. Blank CSV values "
        "represent null database values, including unsuperseded observations.\n"
    ).encode("utf-8")


def _attribution(observations: list[dict[str, Any]]) -> bytes:
    by_family: dict[str, dict[str, set[str]]] = {}
    for row in observations:
        record = by_family.setdefault(
            row["evidence_source_family"],
            {"attributions": set(), "licenses": set(), "publishers": set()},
        )
        record["attributions"].add(row["evidence_attribution"])
        record["licenses"].add(row["evidence_license"])
        record["publishers"].add(row["evidence_publisher"])
    lines = [
        "Derived only from the hash-pinned public-open source inventory in open seed v60.",
        "Each flat observation retains its exact evidence ID, source family, source URL, publisher, license, attribution, content hash, and retrieval timestamp.",
        "Source-family attribution inventory:",
    ]
    for family, values in sorted(by_family.items()):
        publishers = "; ".join(sorted(values["publishers"]))
        licenses = "; ".join(sorted(values["licenses"]))
        attributions = "; ".join(sorted(values["attributions"]))
        lines.append(
            f"- {family} | publishers: {publishers} | licenses: {licenses} | attribution: {attributions}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _prepare_payloads(
    definition: _Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations = _reconstruct_observations(definition)
    timelines = _timeline_rows(observations, as_of=definition.as_of)
    coverage = _coverage(observations, timelines, definition)
    timeline_raw = b"".join(_canonical_json_line(row) for row in timelines)
    payloads = {
        ATTRIBUTION_FILENAME: _attribution(observations),
        COVERAGE_FILENAME: _canonical_json(coverage),
        OBSERVATIONS_FILENAME: _csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: timeline_raw,
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw),
            "file": definition.path.name,
            "sha256": _sha256_bytes(definition.raw),
        },
        "files": {
            name: {"bytes": len(raw), "sha256": _sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition.generated_at,
        "open_seed_input": {
            "definition": {
                "bytes": definition.open_seed_definition.stat().st_size,
                "file": definition.open_seed_definition.name,
                "sha256": OPEN_SEED_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": (definition.open_seed_release / MANIFEST_FILENAME).stat().st_size,
                "file": MANIFEST_FILENAME,
                "sha256": OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": definition.open_seed_release.name,
            "release_tree_sha256": OPEN_SEED_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
    }
    manifest_raw = _canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _parse_csv(path: Path) -> list[dict[str, str]]:
    raw = _regular_bytes(path, OBSERVATIONS_FILENAME)
    try:
        stream = io.StringIO(raw.decode("utf-8"), newline="")
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("observation CSV is not UTF-8") from error
    reader = csv.DictReader(stream)
    if tuple(reader.fieldnames or ()) != OBSERVATION_FIELDS:
        raise ConstructionTimelineError("observation CSV header differs")
    return list(reader)


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _regular_bytes(path, TIMELINES_FILENAME)
    if not raw.endswith(b"\n"):
        raise ConstructionTimelineError("timeline JSONL must end with a newline")
    rows: list[dict[str, Any]] = []
    for position, line in enumerate(raw.splitlines(keepends=True), start=1):
        value = _json_object(line, f"timeline JSONL row {position}")
        if line != _canonical_json_line(value):
            raise ConstructionTimelineError("timeline JSONL row is not canonical")
        rows.append(value)
    return rows


def _validate_payload_semantics(
    directory: Path, manifest: Mapping[str, Any]
) -> None:
    observations = _parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = _parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = _regular_bytes(directory / COVERAGE_FILENAME, COVERAGE_FILENAME)
    coverage = _json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != _canonical_json(coverage):
        raise ConstructionTimelineError("coverage JSON is not canonical")
    if len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]:
        raise ConstructionTimelineError("observation CSV row count differs")
    if len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]:
        raise ConstructionTimelineError("timeline JSONL row count differs")
    if len({row["observation_id"] for row in observations}) != len(observations):
        raise ConstructionTimelineError("observation CSV IDs collide")
    stable_order = [
        (row["entity_stable_key"], row["observed_date"], row["recorded_at"], row["observation_id"])
        for row in observations
    ]
    if stable_order != sorted(stable_order):
        raise ConstructionTimelineError("observation CSV ordering differs")
    timeline_order = [
        (row.get("entity_stable_key"), row.get("entity_id")) for row in timelines
    ]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(timeline_order):
        raise ConstructionTimelineError("timeline JSONL identity ordering differs")
    flattened_ids: list[str] = []
    for timeline in timelines:
        required = {
            "current_construction_claim",
            "current_status_classification",
            "entity_country",
            "entity_id",
            "entity_kind",
            "entity_name",
            "entity_stable_key",
            "format",
            "has_multiple_observations",
            "has_status_change",
            "latest_observation_persistence_assumed",
            "observation_count",
            "observations",
            "schema_version",
            "single_old_observation_current_unknown",
            "source_scoped_identity_only",
        }
        if set(timeline) != required:
            raise ConstructionTimelineError("timeline JSONL schema differs")
        if (
            timeline["format"] != TIMELINE_FORMAT
            or timeline["schema_version"] != SCHEMA_VERSION
            or timeline["current_status_classification"] != "unknown"
            or timeline["current_construction_claim"] is not False
            or timeline["latest_observation_persistence_assumed"] is not False
            or timeline["source_scoped_identity_only"] is not True
        ):
            raise ConstructionTimelineError("timeline JSONL guardrails differ")
        nested = timeline["observations"]
        if not isinstance(nested, list) or timeline["observation_count"] != len(nested):
            raise ConstructionTimelineError("timeline observation accounting differs")
        flattened_ids.extend(item["observation_id"] for item in nested)
    if sorted(flattened_ids) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineError("flat and grouped observation inventories differ")
    if (
        coverage.get("format") != COVERAGE_FORMAT
        or coverage.get("scope") != SCOPE
        or coverage.get("counts") != EXPECTED_COUNTS
        or manifest.get("counts") != EXPECTED_COUNTS
    ):
        raise ConstructionTimelineError("coverage or manifest contract differs")


def validate_construction_timeline_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate a closed bundle and optionally replay all v60 inputs offline."""

    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineError("timeline bundle must be an ordinary directory")
    if require_frozen and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise ConstructionTimelineError("timeline bundle directory must be mode 0555")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineError("timeline bundle file inventory differs")
    for entry in entries:
        _regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = _regular_bytes(directory / MANIFEST_FILENAME, MANIFEST_FILENAME)
    manifest = _json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = _regular_bytes(directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME)
    expected_sidecar = f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    if sidecar != expected_sidecar:
        raise ConstructionTimelineError("timeline manifest sidecar differs")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("timeline_id") != TIMELINE_ID
        or manifest.get("as_of") != AS_OF
        or manifest.get("generated_at") != GENERATED_AT
        or manifest.get("scope") != SCOPE
    ):
        raise ConstructionTimelineError("timeline manifest contract differs")
    files = manifest.get("files")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(files, Mapping) or set(files) != payload_names:
        raise ConstructionTimelineError("timeline manifest file inventory differs")
    for name in payload_names:
        checkpoint = files[name]
        raw = _regular_bytes(directory / name, name)
        if checkpoint != {"bytes": len(raw), "sha256": _sha256_bytes(raw)}:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if definition_path is not None:
        definition = _load_definition(definition_path)
        expected_definition = {
            "bytes": len(definition.raw),
            "file": definition.path.name,
            "sha256": _sha256_bytes(definition.raw),
        }
        if manifest.get("definition") != expected_definition:
            raise ConstructionTimelineError("timeline definition checkpoint differs")
        if verify_inputs:
            expected_payloads, expected_manifest = _prepare_payloads(definition)
            actual_payloads = {entry.name: entry.read_bytes() for entry in entries}
            if actual_payloads != expected_payloads or manifest != expected_manifest:
                raise ConstructionTimelineError("exact-input timeline rebuild differs")
    elif verify_inputs:
        raise ConstructionTimelineError("verify_inputs requires definition_path")
    return manifest


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ConstructionTimelineError("refusing contaminated timeline stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(stage)


def write_construction_timeline_bundle(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Double-rebuild, freeze, and atomically publish the v60 timeline."""

    definition = _load_definition(definition_path)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.exists() or output.is_symlink():
        raise ConstructionTimelineError(
            f"timeline output already exists; refusing overwrite: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir() or not output.name:
        raise ConstructionTimelineError("timeline output parent is invalid")
    payloads, manifest = _prepare_payloads(definition)
    replay_payloads, replay_manifest = _prepare_payloads(definition)
    if payloads != replay_payloads or manifest != replay_manifest:
        raise ConstructionTimelineError(
            "v60 inputs changed or two offline timeline reconstructions differ"
        )
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    published = False
    try:
        for name, raw in payloads.items():
            target = stage / name
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        validate_construction_timeline_bundle(stage, require_frozen=False)
        for target in stage.iterdir():
            target.chmod(FROZEN_FILE_MODE)
        stage.chmod(FROZEN_DIRECTORY_MODE)
        validate_construction_timeline_bundle(stage)
        try:
            promote_noreplace(stage, output)
        except SystemExit as error:
            raise ConstructionTimelineError(str(error)) from error
        published = True
        return validate_construction_timeline_bundle(
            output,
            definition_path=definition.path,
            verify_inputs=True,
        )
    finally:
        if not published:
            _discard_stage(stage)


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "AS_OF",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "ConstructionTimelineError",
    "EXPECTED_COUNTS",
    "GENERATED_AT",
    "OBSERVATION_FIELDS",
    "SCOPE",
    "TIMELINE_ID",
    "build_construction_timeline_bundle",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
