"""Publish the strict timeline-v7 successor derived only from open seed v86.

Every accepted v7 flat observation and grouped timeline is retained exactly.
The successor appends the six lifecycle observations first accepted in open
seed v84 and the five lifecycle observations first accepted in open seed v86.
Open seed v85 is coordinate-only and contributes no lifecycle row.  Every
status remains a dated last-observed fact; current status is unknown and
observation persistence is never inferred.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import io
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any

from . import construction_timeline_v7 as _timeline_v7
from . import open_seed_v84, open_seed_v86
from .open_seed_v56 import promote_noreplace, tree_digest


class _V7Carrier:
    """Expose v7 plus its frozen v6 codec carrier without mutating either."""

    v5 = _timeline_v7.previous.v5

    def __getattr__(self, name: str) -> Any:
        return getattr(_timeline_v7, name)


previous = _V7Carrier()


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-21-public-open-v8"
AS_OF = "2026-07-21"
# Staging must finish before this one-time publication instant.
GENERATED_AT = "2026-07-21T20:42:50Z"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v8.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v8"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v8.lock"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v86.py"
OPEN_SEED_RECORDED_AT = "2026-07-21T20:19:16Z"
OPEN_SEED_DEFINITION_PIN = (
    102_240,
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
)
OPEN_SEED_MANIFEST_PIN = (
    15_531,
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
)
OPEN_SEED_TREE_SHA256 = (
    "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
)
OPEN_SEED_CORE_PIN = (
    71_476,
    "f0cc4e389470bf611c0d5aa4b399a01dea59930a2a8242107968bb06bdf015fb",
)
OPEN_SEED_DEFINITION_SHA256 = OPEN_SEED_DEFINITION_PIN[1]
OPEN_SEED_MANIFEST_SHA256 = OPEN_SEED_MANIFEST_PIN[1]

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v7.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v7"
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v7.py"
PREDECESSOR_DEFINITION_PIN = (
    2_941,
    "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1",
)
PREDECESSOR_MANIFEST_PIN = (
    3_897,
    "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265",
)
PREDECESSOR_TREE_SHA256 = (
    "b7dd059de068366d12da84970ca750fc3a2872f59069b5563ac47c5e05ce568c"
)
PREDECESSOR_CORE_PIN = (
    68_784,
    "1c87b42c5798f95658b80b18e14b0b1459cdbd191febfd6bd85477723ce60692",
)
PREDECESSOR_DEFINITION_SHA256 = PREDECESSOR_DEFINITION_PIN[1]
PREDECESSOR_MANIFEST_SHA256 = PREDECESSOR_MANIFEST_PIN[1]

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v8"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v8"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v8"
SCHEMA_VERSION = 8

# The accepted row schema stays frozen so every inherited row can remain exact.
TIMELINE_FORMAT = previous.TIMELINE_FORMAT
TIMELINE_SCHEMA_VERSION = previous.TIMELINE_SCHEMA_VERSION
OBSERVATIONS_FILENAME = previous.OBSERVATIONS_FILENAME
TIMELINES_FILENAME = previous.TIMELINES_FILENAME
COVERAGE_FILENAME = previous.COVERAGE_FILENAME
README_FILENAME = previous.README_FILENAME
ATTRIBUTION_FILENAME = previous.ATTRIBUTION_FILENAME
MANIFEST_FILENAME = previous.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = previous.MANIFEST_HASH_FILENAME
BUNDLE_FILES = previous.BUNDLE_FILES
OBSERVATION_FIELDS = previous.OBSERVATION_FIELDS
EVENT_CONTRACT_FIELDS = previous.EVENT_CONTRACT_FIELDS
FROZEN_DIRECTORY_MODE = previous.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = previous.FROZEN_FILE_MODE
SCOPE = dict(previous.SCOPE)

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 517,
    "multi_observation_entities": 20,
    "raw_lifecycle_observations": 537,
    "repeated_status_multi_observation_entities": 7,
    "single_observation_entities": 497,
    "single_old_observation_entities": 29,
    "source_families": 252,
    "status_changing_multi_observation_entities": 13,
}

FULL_V86_RAW_OBSERVATIONS = 537
PREDECESSOR_OBSERVATIONS = 526
PREDECESSOR_TIMELINES = 506
V86_ADDED_OBSERVATIONS = 11
V86_ADDED_PROJECTS = 11
V86_INHERITED_RECORDED_AT_REWRITES_IGNORED = 143
V7_ACCEPTED_INPUTS = 441
V86_SELECTED_INPUTS = 452
V84_LIFECYCLE_SOURCES = 6
V85_LIFECYCLE_SOURCES = 0
V86_OPERATOR_SOCIAL_LIFECYCLE_SOURCES = 5

RECENT_OPERATIONAL_CLOSURE_KEYS = frozenset(
    {
        "curated:cologix-mtl8-montreal-data-center:initial-build",
        "curated:equinix-mo2-monterrey-data-center:phase-1",
        "curated:odata-dc-qr03-queretaro-campus:first-facility",
        "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
    }
)
STALE_LATEST_ADDITION_KEYS = frozenset(
    {"curated:odata-dc-qr03-queretaro-campus:first-facility"}
)
SINGLE_OLD_ADDITION_KEYS = STALE_LATEST_ADDITION_KEYS

POST_V83_SOURCE_PATHS = (
    "sources/curated-official-2026-07-21-qscale-q01-building-b-current-build.json",
    "sources/curated-official-2026-07-21-estructure-cal3-current-build.json",
    "sources/curated-official-2026-07-21-cologix-mtl8-operational-closure.json",
    "sources/curated-official-2026-07-21-odata-qr04-phase-1-operational-closure.json",
    "sources/curated-official-2026-07-21-equinix-mo2-phase-1-operational-closure.json",
    "sources/curated-official-2026-07-21-odata-qr03-first-facility-operational-closure.json",
    "sources/curated-official-2026-07-21-stack-johor-first-120mw-current-build.json",
    "sources/curated-official-2026-07-21-echelon-dub20-current-build.json",
    "sources/curated-official-2026-07-21-echelon-dub40-current-build.json",
    "sources/curated-official-2026-07-21-odata-sp04-phase2-current-build.json",
    "sources/curated-official-2026-07-21-multidc-shoham-current-build.json",
)

V86_ADDITION_EVENT_CONTRACT_SHA256 = (
    "fe277215fde57c63c383962c9c44b766a9c0974b7ceff8a6dfbf3452548c20c1"
)

DELTA_CONTRACT = {
    "full_v86_raw_lifecycle_observations": FULL_V86_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "non_lifecycle_sources_promoted_to_lifecycle": 0,
    "recorded_at_values_preserved_from_v7": True,
    "v84_lifecycle_sources": V84_LIFECYCLE_SOURCES,
    "v85_lifecycle_sources": V85_LIFECYCLE_SOURCES,
    "v86_added_lifecycle_observations": V86_ADDED_OBSERVATIONS,
    "v86_added_project_entities": V86_ADDED_PROJECTS,
    "v86_inherited_recorded_at_rewrites_ignored": (
        V86_INHERITED_RECORDED_AT_REWRITES_IGNORED
    ),
    "v86_operator_social_lifecycle_sources": (V86_OPERATOR_SOCIAL_LIFECYCLE_SOURCES),
    "v86_selected_source_files": V86_SELECTED_INPUTS,
}

ConstructionTimelineError = previous.ConstructionTimelineError


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    timeline_id: str
    as_of: str
    generated_at: str
    open_seed_definition: Path
    open_seed_release: Path
    predecessor_definition: Path
    predecessor_bundle: Path
    expected: Mapping[str, Any]


def _parse_utc(value: Any, *, label: str) -> datetime:
    return previous._parse_utc(value, label=label)


def _file_pin(path: Path) -> tuple[int, str]:
    raw = previous.v5.v3._regular_bytes(path, str(path))
    return len(raw), previous.v5.v3._sha256_bytes(raw)


def _load_definition(
    path_value: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = previous.v5.v3._regular_bytes(path, "timeline definition")
    document = previous.v5.v3._json_object(raw, "timeline definition")
    if raw != previous.v5.v3._canonical_json(document):
        raise ConstructionTimelineError("timeline definition must be canonical JSON")
    if set(document) != {
        "as_of",
        "delta",
        "expected",
        "format",
        "generated_at",
        "open_seed",
        "predecessor",
        "schema_version",
        "scope",
        "timeline_id",
    }:
        raise ConstructionTimelineError("timeline definition schema is invalid")
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["format"] != DEFINITION_FORMAT
        or document["timeline_id"] != TIMELINE_ID
        or document["as_of"] != AS_OF
        or document["generated_at"] != GENERATED_AT
        or document["scope"] != SCOPE
        or document["delta"] != DELTA_CONTRACT
        or document["expected"] != EXPECTED_COUNTS
    ):
        raise ConstructionTimelineError("timeline v8 definition contract differs")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if wall_clock.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    generated = _parse_utc(document["generated_at"], label="timeline generated_at")
    if generated <= _parse_utc(OPEN_SEED_RECORDED_AT, label="v86 recorded_at"):
        raise ConstructionTimelineError("timeline generated_at must follow v86")
    if generated > wall_clock.astimezone(timezone.utc):
        raise ConstructionTimelineError(
            "timeline generated_at exceeds validation wall clock"
        )

    open_seed = document["open_seed"]
    predecessor = document["predecessor"]
    if not isinstance(open_seed, Mapping) or set(open_seed) != {
        "definition",
        "expected_release_tree_sha256",
        "manifest",
        "release_path",
    }:
        raise ConstructionTimelineError("open seed checkpoint schema is invalid")
    if not isinstance(predecessor, Mapping) or set(predecessor) != {
        "bundle_path",
        "definition",
        "expected_bundle_tree_sha256",
        "manifest",
    }:
        raise ConstructionTimelineError("predecessor checkpoint schema is invalid")
    seed_definition_display, seed_definition_digest = previous.v5.v3._checkpoint(
        open_seed["definition"], "open seed definition"
    )
    seed_manifest_display, seed_manifest_digest = previous.v5.v3._checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    predecessor_definition_display, predecessor_definition_digest = (
        previous.v5.v3._checkpoint(predecessor["definition"], "predecessor definition")
    )
    predecessor_manifest_display, predecessor_manifest_digest = (
        previous.v5.v3._checkpoint(predecessor["manifest"], "predecessor manifest")
    )
    seed_definition = previous.v5.v3._resolve(
        path, seed_definition_display, "open seed definition"
    )
    seed_release = previous.v5.v3._resolve(
        path, open_seed["release_path"], "open seed release"
    )
    seed_manifest = previous.v5.v3._resolve(
        path, seed_manifest_display, "open seed manifest"
    )
    predecessor_definition = previous.v5.v3._resolve(
        path, predecessor_definition_display, "predecessor definition"
    )
    predecessor_bundle = previous.v5.v3._resolve(
        path, predecessor["bundle_path"], "predecessor bundle"
    )
    predecessor_manifest = previous.v5.v3._resolve(
        path, predecessor_manifest_display, "predecessor manifest"
    )
    if (
        seed_definition != OPEN_SEED_DEFINITION
        or seed_release != OPEN_SEED_RELEASE
        or seed_manifest != OPEN_SEED_RELEASE / MANIFEST_FILENAME
        or seed_definition_digest != OPEN_SEED_DEFINITION_SHA256
        or seed_manifest_digest != OPEN_SEED_MANIFEST_SHA256
        or open_seed["expected_release_tree_sha256"] != OPEN_SEED_TREE_SHA256
        or predecessor_definition != PREDECESSOR_DEFINITION
        or predecessor_bundle != PREDECESSOR_BUNDLE
        or predecessor_manifest != PREDECESSOR_BUNDLE / MANIFEST_FILENAME
        or predecessor_definition_digest != PREDECESSOR_DEFINITION_SHA256
        or predecessor_manifest_digest != PREDECESSOR_MANIFEST_SHA256
        or predecessor["expected_bundle_tree_sha256"] != PREDECESSOR_TREE_SHA256
    ):
        raise ConstructionTimelineError("accepted v86 or timeline v7 pins differ")
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=document["generated_at"],
        open_seed_definition=seed_definition,
        open_seed_release=seed_release,
        predecessor_definition=predecessor_definition,
        predecessor_bundle=predecessor_bundle,
        expected=EXPECTED_COUNTS,
    )


def _validate_inputs(definition: _Definition) -> None:
    checkpoints = {
        definition.open_seed_definition: OPEN_SEED_DEFINITION_PIN,
        definition.open_seed_release / MANIFEST_FILENAME: OPEN_SEED_MANIFEST_PIN,
        OPEN_SEED_CORE: OPEN_SEED_CORE_PIN,
        definition.predecessor_definition: PREDECESSOR_DEFINITION_PIN,
        definition.predecessor_bundle / MANIFEST_FILENAME: PREDECESSOR_MANIFEST_PIN,
        PREDECESSOR_CORE: PREDECESSOR_CORE_PIN,
    }
    for checkpoint, pin in checkpoints.items():
        if _file_pin(checkpoint) != pin:
            raise ConstructionTimelineError(f"frozen input changed: {checkpoint}")
    if tree_digest(definition.open_seed_release) != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen open seed v86 tree changed")
    if tree_digest(definition.predecessor_bundle) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v7 tree changed")
    try:
        seed_manifest = open_seed_v86.validate_open_seed_v86(
            definition.open_seed_definition,
            definition.open_seed_release,
            replay_count=2,
        )
        predecessor_manifest = previous.validate_construction_timeline_bundle(
            definition.predecessor_bundle,
            definition_path=definition.predecessor_definition,
            verify_inputs=True,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("frozen input validation failed") from error
    frozen_seed_manifest = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            definition.open_seed_release / MANIFEST_FILENAME, "v86 manifest"
        ),
        "v86 manifest",
    )
    frozen_predecessor_manifest = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            definition.predecessor_bundle / MANIFEST_FILENAME, "timeline v7 manifest"
        ),
        "timeline v7 manifest",
    )
    if (
        seed_manifest != frozen_seed_manifest
        or predecessor_manifest != frozen_predecessor_manifest
    ):
        raise ConstructionTimelineError("validated frozen input manifest differs")


def _release_labels(release: Path) -> dict[str, dict[str, str]]:
    raw = previous.v5.v3._regular_bytes(release / "entities.csv", "v86 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v86 entities.csv is not UTF-8") from error
    if len(rows) != 927:
        raise ConstructionTimelineError("v86 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v86 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _post_v83_source_contract() -> dict[str, str]:
    raw = previous.v5.v3._regular_bytes(OPEN_SEED_DEFINITION, "v86 definition")
    if (len(raw), previous.v5.v3._sha256_bytes(raw)) != OPEN_SEED_DEFINITION_PIN:
        raise ConstructionTimelineError("frozen v86 definition changed")
    document = previous.v5.v3._json_object(raw, "v86 definition")
    inputs = document.get("curated_inputs")
    if not isinstance(inputs, list) or len(inputs) != V86_SELECTED_INPUTS:
        raise ConstructionTimelineError("v86 selected input inventory differs")
    additions = inputs[V7_ACCEPTED_INPUTS:]
    if tuple(row.get("path") for row in additions) != POST_V83_SOURCE_PATHS:
        raise ConstructionTimelineError("post-v83 source path contract differs")
    if (
        tuple(open_seed_v84.ADDITION_ORDER) != POST_V83_SOURCE_PATHS[:6]
        or tuple(open_seed_v86.ADDITION_ORDER) != POST_V83_SOURCE_PATHS[6:]
    ):
        raise ConstructionTimelineError("v84/v86 source module contract differs")

    source_by_key: dict[str, str] = {}
    lifecycle_count = 0
    for item in additions:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ConstructionTimelineError("post-v83 source checkpoint differs")
        display = str(item["path"])
        path = ROOT / display
        if previous.v5.v3._sha256_file(path) != item["sha256"]:
            raise ConstructionTimelineError(f"post-v83 source changed: {display}")
        source = previous.v5.v3._json_object(
            previous.v5.v3._regular_bytes(path, display), display
        )
        project = source.get("project")
        lifecycle = source.get("lifecycle")
        if (
            not isinstance(project, Mapping)
            or not isinstance(project.get("stable_key"), str)
            or not isinstance(lifecycle, list)
            or len(lifecycle) != 1
            or any(
                not isinstance(row, Mapping) or row.get("entity") != "project"
                for row in lifecycle
            )
        ):
            raise ConstructionTimelineError(
                f"post-v83 source is not one-row lifecycle-bearing: {display}"
            )
        stable_key = str(project["stable_key"])
        if stable_key in source_by_key:
            raise ConstructionTimelineError("post-v83 project source is ambiguous")
        source_by_key[stable_key] = display
        lifecycle_count += len(lifecycle)
    if (
        len(source_by_key) != V86_ADDED_PROJECTS
        or lifecycle_count != V86_ADDED_OBSERVATIONS
    ):
        raise ConstructionTimelineError("post-v83 lifecycle accounting differs")
    return source_by_key


def _full_v86_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_inputs(definition)
    v86_document = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            definition.open_seed_definition, "v86 definition"
        ),
        "v86 definition",
    )
    base = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            open_seed_v86.BASE_DEFINITION, "v85 base definition"
        ),
        "v85 base definition",
    )
    try:
        selected_rows, paths = open_seed_v86.selected_inputs(
            base,
            recorded_at=OPEN_SEED_RECORDED_AT,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("v86 source selection failed") from error
    if (
        v86_document.get("build")
        != {"as_of": AS_OF, "recorded_at": OPEN_SEED_RECORDED_AT}
        or selected_rows != v86_document.get("curated_inputs")
        or len(paths) != V86_SELECTED_INPUTS
    ):
        raise ConstructionTimelineError("fresh v86 source inventory differs")
    labels = _release_labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v8-db-",
        dir="/private/tmp",
    ) as temporary:
        try:
            connection = open_seed_v86._build_database(
                base,
                paths,
                Path(temporary) / "atlas.sqlite",
                recorded_at=OPEN_SEED_RECORDED_AT,
            )
        except (OSError, ValueError, RuntimeError, SystemExit) as error:
            raise ConstructionTimelineError(
                "fresh v86 database rebuild failed"
            ) from error
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
        if (
            label is None
            or label.get("stable_key") != row["entity_stable_key"]
            or label.get("entity_kind") != row["entity_kind"]
            or not label.get("name")
            or not label.get("country")
        ):
            raise ConstructionTimelineError("v86 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if len(observations) != FULL_V86_RAW_OBSERVATIONS or len(
        {row["observation_id"] for row in observations}
    ) != len(observations):
        raise ConstructionTimelineError("full v86 lifecycle inventory differs")
    return observations


def _predecessor_observations(definition: _Definition) -> list[dict[str, str]]:
    rows = previous.v5.v3._parse_csv(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME
    )
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("timeline v7 observation inventory differs")
    if previous.v5.v3._csv_bytes(rows) != previous.v5.v3._regular_bytes(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME, "v7 observations"
    ):
        raise ConstructionTimelineError("timeline v7 observation bytes differ")
    return rows


def _predecessor_timelines(definition: _Definition) -> list[dict[str, Any]]:
    rows = previous.v5.v3._parse_jsonl(
        definition.predecessor_bundle / TIMELINES_FILENAME
    )
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("timeline v7 entity inventory differs")
    if b"".join(
        previous.v5.v3._canonical_json_line(row) for row in rows
    ) != previous.v5.v3._regular_bytes(
        definition.predecessor_bundle / TIMELINES_FILENAME, "v7 timelines"
    ):
        raise ConstructionTimelineError("timeline v7 JSONL bytes differ")
    return rows


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    source_by_key = _post_v83_source_contract()
    as_of = date.fromisoformat(AS_OF)
    contract = []
    for row in rows:
        stable_key = str(row["entity_stable_key"])
        age = (as_of - date.fromisoformat(str(row["observed_date"]))).days
        contract.append(
            (
                source_by_key[stable_key],
                stable_key,
                str(row["observation_id"]),
                str(row["observed_date"]),
                str(row["status"]),
                str(row["method"]),
                str(row["evidence_id"]),
                str(row["evidence_source_family"]),
                str(row["evidence_retrieved_at"]),
                str(row["evidence_content_hash"]),
                age,
                previous.v5.v3._freshness_class(age),
            )
        )
    return tuple(sorted(contract, key=lambda item: (item[1], item[3], item[2])))


def _event_contract_sha256(contract: tuple[tuple[Any, ...], ...]) -> str:
    raw = previous.v5.v3._canonical_json([list(event) for event in contract])
    return previous.v5.v3._sha256_bytes(raw)


def _reconstruct_observations(
    definition: _Definition,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = _full_v86_observations(definition)
    predecessor = _predecessor_observations(definition)
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v86 dropped a timeline v7 observation")
    rewrite_count = 0
    for row in predecessor:
        fresh = previous.v5.v3._csv_row(full_by_id[row["observation_id"]])
        differences = {
            field for field in OBSERVATION_FIELDS if row[field] != fresh[field]
        }
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v86 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
    if rewrite_count != V86_INHERITED_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError(
            "v86 inherited recorded_at rewrite count differs"
        )

    additions = [
        row for row in full if str(row["observation_id"]) not in predecessor_ids
    ]
    source_by_key = _post_v83_source_contract()
    contract = _event_contract(additions)
    if (
        len(additions) != V86_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in additions}) != V86_ADDED_PROJECTS
        or {str(row["entity_stable_key"]) for row in additions} != set(source_by_key)
        or _event_contract_sha256(contract) != V86_ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineError("v86 addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids:
        raise ConstructionTimelineError("v86 addition collides with timeline v7")
    if set(full_by_id) - predecessor_ids != addition_ids:
        raise ConstructionTimelineError("v86 full-to-v7 delta boundary differs")
    combined: list[dict[str, Any]] = [*predecessor, *additions]
    combined.sort(
        key=lambda row: (
            str(row["entity_stable_key"]),
            str(row["observed_date"]),
            str(row["recorded_at"]),
            str(row["observation_id"]),
        )
    )
    if len(combined) != EXPECTED_COUNTS["raw_lifecycle_observations"]:
        raise ConstructionTimelineError("timeline v8 observation inventory differs")
    return combined, additions


def _timeline_rows(
    definition: _Definition,
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines(definition)
    new_rows = previous.carrier._timeline_rows(additions, as_of=AS_OF)
    if len(new_rows) != V86_ADDED_PROJECTS or any(
        row["format"] != TIMELINE_FORMAT
        or row["schema_version"] != TIMELINE_SCHEMA_VERSION
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] is not False
        or row["latest_observation_persistence_assumed"] is not False
        for row in new_rows
    ):
        raise ConstructionTimelineError("v86 addition timeline guardrails differ")
    if any(row["has_status_change"] for row in new_rows):
        raise ConstructionTimelineError("v86 status-changing timeline boundary differs")
    operational = {
        row["entity_stable_key"]
        for row in new_rows
        if row["observations"][-1]["status"] == "operational"
    }
    stale_latest = {
        row["entity_stable_key"]
        for row in new_rows
        if (
            date.fromisoformat(AS_OF)
            - date.fromisoformat(row["observations"][-1]["observed_date"])
        ).days
        > 365
    }
    single_old = {
        row["entity_stable_key"]
        for row in new_rows
        if row["single_old_observation_current_unknown"]
    }
    if (
        operational != RECENT_OPERATIONAL_CLOSURE_KEYS
        or stale_latest != STALE_LATEST_ADDITION_KEYS
        or single_old != SINGLE_OLD_ADDITION_KEYS
    ):
        raise ConstructionTimelineError(
            "v86 terminal or stale timeline boundary differs"
        )
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("timeline v8 entity collides with timeline v7")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _event_documents(
    contract: tuple[tuple[Any, ...], ...],
) -> list[dict[str, Any]]:
    documents = []
    for event in contract:
        document = dict(zip(EVENT_CONTRACT_FIELDS, event, strict=True))
        document.update(
            {
                "current_construction_claim": False,
                "current_status_classification": "unknown",
                "latest_observation_persistence_assumed": False,
                "status_semantics": "last_observed",
            }
        )
        documents.append(document)
    return documents


def _coverage(
    observations: list[dict[str, Any]],
    timelines: list[dict[str, Any]],
    definition: _Definition,
) -> dict[str, Any]:
    multi = [row for row in timelines if row["has_multiple_observations"]]
    single = [row for row in timelines if not row["has_multiple_observations"]]
    changing = [row for row in multi if row["has_status_change"]]
    repeated = [row for row in multi if not row["has_status_change"]]
    single_old = [
        row for row in single if row["single_old_observation_current_unknown"]
    ]
    counts = {
        "entities_with_lifecycle_observations": len(timelines),
        "multi_observation_entities": len(multi),
        "raw_lifecycle_observations": len(observations),
        "repeated_status_multi_observation_entities": len(repeated),
        "single_observation_entities": len(single),
        "single_old_observation_entities": len(single_old),
        "source_families": len({row["evidence_source_family"] for row in observations}),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineError(f"timeline coverage counts differ: {counts}")
    source_by_key = _post_v83_source_contract()
    additions = [
        row for row in observations if str(row["entity_stable_key"]) in source_by_key
    ]
    event_contract = _event_contract(additions)
    if _event_contract_sha256(event_contract) != V86_ADDITION_EVENT_CONTRACT_SHA256:
        raise ConstructionTimelineError("v86 coverage event contract differs")
    events = _event_documents(event_contract)
    predecessor_coverage = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v7 coverage"
        ),
        "v7 coverage",
    )
    additions_by_key = {str(event["entity_stable_key"]): event for event in events}
    operational_closures = [
        {
            "construction_sequence_semantics": "closed_by_dated_operational_observation",
            "current_construction_claim": False,
            "current_operational_claim": False,
            "current_status_classification": "unknown",
            "entity_stable_key": key,
            "latest_observation_persistence_assumed": False,
            "observed_date": additions_by_key[key]["observed_date"],
            "status": "operational",
            "status_semantics": "last_observed",
        }
        for key in sorted(RECENT_OPERATIONAL_CLOSURE_KEYS)
    ]
    stale_latest_timelines = [
        {
            "current_construction_claim": False,
            "current_status_classification": "unknown",
            "entity_stable_key": key,
            "latest_observation_persistence_assumed": False,
            "latest_observed_date": additions_by_key[key]["observed_date"],
            "single_observation": key in SINGLE_OLD_ADDITION_KEYS,
            "status_semantics": "stale_last_observed",
        }
        for key in sorted(STALE_LATEST_ADDITION_KEYS)
    ]
    return {
        "as_of": definition.as_of,
        "counts": counts,
        "current_status_classification_counts": {"unknown": len(timelines)},
        "date_coverage": {
            "latest_observed_date": max(
                str(row["observed_date"]) for row in observations
            ),
            "oldest_observed_date": min(
                str(row["observed_date"]) for row in observations
            ),
        },
        "delta": DELTA_CONTRACT,
        "format": COVERAGE_FORMAT,
        "generated_at": definition.generated_at,
        "inherited_v7_recent_operational_lifecycle_closures": predecessor_coverage[
            "recent_operational_lifecycle_closures"
        ],
        "multi_observation_timelines": [
            {
                "entity_stable_key": row["entity_stable_key"],
                "observations": [
                    {"observed_date": item["observed_date"], "status": item["status"]}
                    for item in row["observations"]
                ],
                "status_change": row["has_status_change"],
            }
            for row in multi
        ],
        "observation_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in observations).items())
        ),
        "observation_status_counts": dict(
            sorted(Counter(str(row["status"]) for row in observations).items())
        ),
        "predecessor": {
            "definition_sha256": PREDECESSOR_DEFINITION_SHA256,
            "manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "timeline_id": previous.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "source_family_observation_counts": dict(
            sorted(
                Counter(
                    str(row["evidence_source_family"]) for row in observations
                ).items()
            )
        ),
        "stt_johor_historical_only": predecessor_coverage["stt_johor_historical_only"],
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v6_inherited_v72_coordinate_only_delta": predecessor_coverage[
            "v6_inherited_v72_coordinate_only_delta"
        ],
        "v8_delta_non_lifecycle_promotion": {
            "capacity_only_sources_promoted_to_lifecycle": 0,
            "coordinate_only_sources_promoted_to_lifecycle": 0,
        },
        "v8_delta_operational_lifecycle_closures": operational_closures,
        "v8_delta_stale_latest_timelines": stale_latest_timelines,
        "v86_addition_events": events,
        "v86_addition_event_contract_sha256": V86_ADDITION_EVENT_CONTRACT_SHA256,
        "v86_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v8\n\n"
        "This immutable exact successor preserves all 526 accepted v7 lifecycle "
        "observations and all 506 accepted v7 entity-timeline rows, then appends "
        "exactly 11 source-scoped project observations: six first accepted in v84 "
        "and five first accepted in v86. Open seed v85 is coordinate-only and adds "
        "no lifecycle row. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} entities.\n\n"
        "A complete 537-row v86 lifecycle database is rebuilt offline. One hundred "
        "forty-three v86 recorded_at rewrites never replace the predecessor's accepted "
        "recording lineage. Each of the 11 delta sources is independently hash-checked "
        "and contains exactly one explicit project lifecycle observation.\n\n"
        "Every lifecycle status remains a dated last-observed fact. Current status is "
        "unknown, current construction is never claimed, and the latest observation "
        "is never assumed to persist. Four delta observations are dated operational "
        "closures, but none becomes a current-operational claim. QR03's old closure and "
        "every other old observation remain current-unknown.\n\n"
        "Permits, forecasts, planned dates, satellite or CV review, capacity-only or "
        "coordinate-only evidence, and missing milestones are not promoted or "
        "interpolated into physical construction. Cross-source identities remain "
        "unresolved and unique physical sites remain null. Only the hash-pinned v7 "
        "timeline and v86 open seed are checkpoints.\n"
    ).encode("utf-8")


def _attribution(observations: list[dict[str, Any]]) -> bytes:
    by_family: dict[str, dict[str, set[str]]] = {}
    for row in observations:
        record = by_family.setdefault(
            str(row["evidence_source_family"]),
            {"attributions": set(), "licenses": set(), "publishers": set()},
        )
        record["attributions"].add(str(row["evidence_attribution"]))
        record["licenses"].add(str(row["evidence_license"]))
        record["publishers"].add(str(row["evidence_publisher"]))
    lines = [
        "Derived only from the hash-pinned construction timeline v7 and open seed v86 inputs.",
        "Every row retains its accepted or source-derived evidence identity, URL, publisher, license, attribution, content hash, and retrieval timestamp.",
        "Source-family attribution inventory:",
    ]
    for family, values in sorted(by_family.items()):
        lines.append(
            f"- {family} | publishers: {'; '.join(sorted(values['publishers']))} "
            f"| licenses: {'; '.join(sorted(values['licenses']))} "
            f"| attribution: {'; '.join(sorted(values['attributions']))}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _prepare_payloads(
    definition: _Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations, additions = _reconstruct_observations(definition)
    timelines = _timeline_rows(definition, additions)
    coverage = _coverage(observations, timelines, definition)
    payloads = {
        ATTRIBUTION_FILENAME: _attribution(observations),
        COVERAGE_FILENAME: previous.v5.v3._canonical_json(coverage),
        OBSERVATIONS_FILENAME: previous.v5.v3._csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: b"".join(
            previous.v5.v3._canonical_json_line(row) for row in timelines
        ),
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw),
            "file": DEFINITION.name,
            "sha256": previous.v5.v3._sha256_bytes(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": previous.v5.v3._sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition.generated_at,
        "open_seed_input": {
            "definition": {
                "bytes": OPEN_SEED_DEFINITION_PIN[0],
                "file": definition.open_seed_definition.name,
                "sha256": OPEN_SEED_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": OPEN_SEED_MANIFEST_PIN[0],
                "file": MANIFEST_FILENAME,
                "sha256": OPEN_SEED_MANIFEST_SHA256,
            },
            "recorded_at": OPEN_SEED_RECORDED_AT,
            "release_id": definition.open_seed_release.name,
            "release_tree_sha256": OPEN_SEED_TREE_SHA256,
        },
        "predecessor_input": {
            "definition": {
                "bytes": PREDECESSOR_DEFINITION_PIN[0],
                "file": definition.predecessor_definition.name,
                "sha256": PREDECESSOR_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": PREDECESSOR_MANIFEST_PIN[0],
                "file": MANIFEST_FILENAME,
                "sha256": PREDECESSOR_MANIFEST_SHA256,
            },
            "timeline_id": previous.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = previous.v5.v3._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{previous.v5.v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _validate_payload_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    observations = previous.v5.v3._parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = previous.v5.v3._parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = previous.v5.v3._regular_bytes(
        directory / COVERAGE_FILENAME, COVERAGE_FILENAME
    )
    coverage = previous.v5.v3._json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != previous.v5.v3._canonical_json(coverage):
        raise ConstructionTimelineError("coverage JSON is not canonical")
    if (
        len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]
        or len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("timeline row inventory differs")
    observation_order = [
        (
            row["entity_stable_key"],
            row["observed_date"],
            row["recorded_at"],
            row["observation_id"],
        )
        for row in observations
    ]
    if observation_order != sorted(observation_order):
        raise ConstructionTimelineError("observation CSV ordering differs")
    timeline_order = [
        (row.get("entity_stable_key"), row.get("entity_id")) for row in timelines
    ]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(
        timeline_order
    ):
        raise ConstructionTimelineError("timeline JSONL identity ordering differs")
    flattened_ids: list[str] = []
    for timeline in timelines:
        if (
            timeline.get("format") != TIMELINE_FORMAT
            or timeline.get("schema_version") != TIMELINE_SCHEMA_VERSION
            or timeline.get("current_status_classification") != "unknown"
            or timeline.get("current_construction_claim") is not False
            or timeline.get("latest_observation_persistence_assumed") is not False
            or timeline.get("source_scoped_identity_only") is not True
        ):
            raise ConstructionTimelineError("timeline JSONL guardrails differ")
        nested = timeline.get("observations")
        if not isinstance(nested, list) or timeline.get("observation_count") != len(
            nested
        ):
            raise ConstructionTimelineError("timeline observation accounting differs")
        flattened_ids.extend(str(item["observation_id"]) for item in nested)
    if sorted(flattened_ids) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineError("flat and grouped inventories differ")
    if (
        coverage.get("format") != COVERAGE_FORMAT
        or coverage.get("schema_version") != SCHEMA_VERSION
        or coverage.get("scope") != SCOPE
        or coverage.get("counts") != EXPECTED_COUNTS
        or coverage.get("delta") != DELTA_CONTRACT
        or manifest.get("counts") != EXPECTED_COUNTS
        or manifest.get("delta") != DELTA_CONTRACT
    ):
        raise ConstructionTimelineError("coverage or manifest contract differs")

    predecessor_observations = previous.v5.v3._parse_csv(
        PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME
    )
    current_by_id = {row["observation_id"]: row for row in observations}
    if any(
        current_by_id.get(row["observation_id"]) != row
        for row in predecessor_observations
    ):
        raise ConstructionTimelineError("inherited observation semantics changed")
    predecessor_timelines = previous.v5.v3._parse_jsonl(
        PREDECESSOR_BUNDLE / TIMELINES_FILENAME
    )
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    if any(
        current_by_key.get(row["entity_stable_key"]) != row
        for row in predecessor_timelines
    ):
        raise ConstructionTimelineError("inherited timeline semantics changed")

    source_by_key = _post_v83_source_contract()
    additions = [
        row for row in observations if row["entity_stable_key"] in source_by_key
    ]
    contract = _event_contract(additions)
    if (
        len(additions) != V86_ADDED_OBSERVATIONS
        or _event_contract_sha256(contract) != V86_ADDITION_EVENT_CONTRACT_SHA256
        or coverage.get("v86_addition_events") != _event_documents(contract)
        or coverage.get("v86_addition_event_contract_sha256")
        != V86_ADDITION_EVENT_CONTRACT_SHA256
        or coverage.get("v86_addition_freshness_counts")
        != {
            "aging_91_365_days": 6,
            "recent_0_90_days": 4,
            "stale_over_365_days": 1,
        }
    ):
        raise ConstructionTimelineError("published v86 event contract differs")
    if coverage.get("v8_delta_non_lifecycle_promotion") != {
        "capacity_only_sources_promoted_to_lifecycle": 0,
        "coordinate_only_sources_promoted_to_lifecycle": 0,
    }:
        raise ConstructionTimelineError("non-lifecycle promotion boundary differs")
    closures = coverage.get("v8_delta_operational_lifecycle_closures")
    if (
        not isinstance(closures, list)
        or {row.get("entity_stable_key") for row in closures}
        != RECENT_OPERATIONAL_CLOSURE_KEYS
        or any(
            row.get("status") != "operational"
            or row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("current_operational_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
            for row in closures
        )
    ):
        raise ConstructionTimelineError("operational closure contract differs")
    stale = coverage.get("v8_delta_stale_latest_timelines")
    if (
        not isinstance(stale, list)
        or {row.get("entity_stable_key") for row in stale} != STALE_LATEST_ADDITION_KEYS
        or any(
            row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
            for row in stale
        )
    ):
        raise ConstructionTimelineError("stale addition contract differs")
    if (
        coverage.get("current_status_classification_counts") != {"unknown": 517}
        or coverage.get("observation_entity_kind_counts")
        != {"campus": 83, "project": 454}
        or coverage.get("timeline_entity_kind_counts") != {"campus": 83, "project": 434}
    ):
        raise ConstructionTimelineError("timeline kind or current-status counts differ")


def _validate_publication_times(
    definition_path: Path,
    bundle_path: Path,
    *,
    generated_at: str,
    validation_wall_clock: datetime,
    require_live: bool,
) -> None:
    generated = _parse_utc(generated_at, label="timeline generated_at")
    if validation_wall_clock.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    if generated > validation_wall_clock.astimezone(timezone.utc):
        raise ConstructionTimelineError(
            "timeline generated_at exceeds validation wall clock"
        )
    for artifact in (definition_path, bundle_path, *bundle_path.iterdir()):
        metadata = artifact.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise ConstructionTimelineError("filesystem birth time is unavailable")
        if metadata.st_birthtime > generated.timestamp() + 0.000_001:
            raise ConstructionTimelineError(
                f"timeline artifact was born after generated_at: {artifact.name}"
            )
        if metadata.st_mtime > generated.timestamp() + 0.000_001:
            raise ConstructionTimelineError(
                f"timeline artifact mtime is after generated_at: {artifact.name}"
            )
    if require_live:
        for root in (definition_path, bundle_path):
            if (
                root.stat(follow_symlinks=False).st_ctime + 0.000_001
                < generated.timestamp()
            ):
                raise ConstructionTimelineError(
                    f"timeline final root ctime predates generated_at: {root.name}"
                )


def validate_construction_timeline_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path = DEFINITION,
    verify_inputs: bool = False,
    require_frozen: bool = True,
    verify_publication_times: bool = True,
    require_live: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate the closed v8 bundle and optionally replay both accepted inputs."""

    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    definition = _load_definition(definition_path, validation_wall_clock=wall_clock)
    if (
        require_frozen
        and stat.S_IMODE(definition.path.stat().st_mode) != FROZEN_FILE_MODE
    ):
        raise ConstructionTimelineError("timeline definition must be mode 0444")
    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineError("timeline bundle must be an ordinary directory")
    if (
        require_frozen
        and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE
    ):
        raise ConstructionTimelineError("timeline bundle directory must be mode 0555")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineError("timeline bundle file inventory differs")
    for entry in entries:
        previous.v5.v3._regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = previous.v5.v3._regular_bytes(
        directory / MANIFEST_FILENAME, MANIFEST_FILENAME
    )
    manifest = previous.v5.v3._json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != previous.v5.v3._canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = previous.v5.v3._regular_bytes(
        directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME
    )
    expected_sidecar = (
        f"{previous.v5.v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar != expected_sidecar:
        raise ConstructionTimelineError("timeline manifest sidecar differs")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("timeline_id") != TIMELINE_ID
        or manifest.get("as_of") != AS_OF
        or manifest.get("generated_at") != definition.generated_at
        or manifest.get("scope") != SCOPE
        or manifest.get("timeline_row_format") != TIMELINE_FORMAT
        or manifest.get("timeline_row_schema_version") != TIMELINE_SCHEMA_VERSION
    ):
        raise ConstructionTimelineError("timeline manifest contract differs")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    files = manifest.get("files")
    if not isinstance(files, Mapping) or set(files) != payload_names:
        raise ConstructionTimelineError("timeline manifest file inventory differs")
    for name in payload_names:
        raw = previous.v5.v3._regular_bytes(directory / name, name)
        if files[name] != {
            "bytes": len(raw),
            "sha256": previous.v5.v3._sha256_bytes(raw),
        }:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if manifest.get("definition") != {
        "bytes": len(definition.raw),
        "file": DEFINITION.name,
        "sha256": previous.v5.v3._sha256_bytes(definition.raw),
    }:
        raise ConstructionTimelineError("timeline definition checkpoint differs")
    if manifest.get("open_seed_input") != {
        "definition": {
            "bytes": OPEN_SEED_DEFINITION_PIN[0],
            "file": OPEN_SEED_DEFINITION.name,
            "sha256": OPEN_SEED_DEFINITION_SHA256,
        },
        "manifest": {
            "bytes": OPEN_SEED_MANIFEST_PIN[0],
            "file": MANIFEST_FILENAME,
            "sha256": OPEN_SEED_MANIFEST_SHA256,
        },
        "recorded_at": OPEN_SEED_RECORDED_AT,
        "release_id": OPEN_SEED_RELEASE.name,
        "release_tree_sha256": OPEN_SEED_TREE_SHA256,
    }:
        raise ConstructionTimelineError("open seed checkpoint differs")
    if manifest.get("predecessor_input") != {
        "definition": {
            "bytes": PREDECESSOR_DEFINITION_PIN[0],
            "file": PREDECESSOR_DEFINITION.name,
            "sha256": PREDECESSOR_DEFINITION_SHA256,
        },
        "manifest": {
            "bytes": PREDECESSOR_MANIFEST_PIN[0],
            "file": MANIFEST_FILENAME,
            "sha256": PREDECESSOR_MANIFEST_SHA256,
        },
        "timeline_id": previous.TIMELINE_ID,
        "tree_sha256": PREDECESSOR_TREE_SHA256,
    }:
        raise ConstructionTimelineError("predecessor checkpoint differs")
    if verify_publication_times:
        _validate_publication_times(
            definition.path,
            directory,
            generated_at=definition.generated_at,
            validation_wall_clock=wall_clock,
            require_live=require_live,
        )
    if verify_inputs:
        expected_payloads, expected_manifest = _prepare_payloads(definition)
        actual_payloads = {entry.name: entry.read_bytes() for entry in entries}
        if actual_payloads != expected_payloads or manifest != expected_manifest:
            raise ConstructionTimelineError("exact-input timeline rebuild differs")
    return manifest


def _definition_document() -> dict[str, Any]:
    return {
        "as_of": AS_OF,
        "delta": DELTA_CONTRACT,
        "expected": EXPECTED_COUNTS,
        "format": DEFINITION_FORMAT,
        "generated_at": GENERATED_AT,
        "open_seed": {
            "definition": {
                "path": OPEN_SEED_DEFINITION.name,
                "sha256": OPEN_SEED_DEFINITION_SHA256,
            },
            "expected_release_tree_sha256": OPEN_SEED_TREE_SHA256,
            "manifest": {
                "path": f"../releases/{OPEN_SEED_RELEASE.name}/{MANIFEST_FILENAME}",
                "sha256": OPEN_SEED_MANIFEST_SHA256,
            },
            "release_path": f"../releases/{OPEN_SEED_RELEASE.name}",
        },
        "predecessor": {
            "bundle_path": f"../construction_timelines/{PREDECESSOR_BUNDLE.name}",
            "definition": {
                "path": PREDECESSOR_DEFINITION.name,
                "sha256": PREDECESSOR_DEFINITION_SHA256,
            },
            "expected_bundle_tree_sha256": PREDECESSOR_TREE_SHA256,
            "manifest": {
                "path": (
                    f"../construction_timelines/{PREDECESSOR_BUNDLE.name}/"
                    f"{MANIFEST_FILENAME}"
                ),
                "sha256": PREDECESSOR_MANIFEST_SHA256,
            },
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": TIMELINE_ID,
    }


def _write_definition_stage(path: Path, raw: bytes) -> None:
    with path.open("r+b") as stream:
        stream.write(raw)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())


def _write_bundle_stage(stage: Path, payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        target = stage / name
        with target.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _discard_stage(stage: Path) -> None:
    previous._discard_stage(stage)


def _latest_stage_time(definition_stage: Path, bundle_stage: Path) -> float:
    timestamps: list[float] = []
    for artifact in (definition_stage, bundle_stage, *bundle_stage.iterdir()):
        metadata = artifact.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise ConstructionTimelineError("filesystem birth time is unavailable")
        timestamps.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(timestamps)


def _wait_until_generated_at() -> None:
    target = _parse_utc(GENERATED_AT, label="timeline generated_at").timestamp()
    remaining = target - time.time()
    if remaining > 60:
        raise ConstructionTimelineError(
            "timeline generated_at is more than 60 seconds ahead of wall clock"
        )
    while time.time() < target:
        time.sleep(min(0.05, target - time.time()))


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise ConstructionTimelineError(
            f"active timeline publication lock exists: {PUBLICATION_LOCK}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _rollback_published(
    definition_stage: Path,
    bundle_stage: Path,
    *,
    definition_published: bool,
    bundle_published: bool,
) -> None:
    errors: list[str] = []
    if definition_published:
        try:
            promote_noreplace(DEFINITION, definition_stage)
        except BaseException as error:  # pragma: no cover - catastrophic path
            errors.append(f"definition rollback failed: {error}")
    if bundle_published:
        try:
            promote_noreplace(BUNDLE, bundle_stage)
        except BaseException as error:  # pragma: no cover - catastrophic path
            errors.append(f"bundle rollback failed: {error}")
    if errors:
        raise ConstructionTimelineError("; ".join(errors))


def publish_construction_timeline_v8() -> dict[str, Any]:
    """Privately stage, double-rebuild, freeze, and no-replace publish v8."""

    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise ConstructionTimelineError(
                f"timeline output parent is invalid: {parent}"
            )
    with _publication_lock():
        for target in (DEFINITION, BUNDLE):
            if target.exists() or target.is_symlink():
                raise ConstructionTimelineError(
                    f"timeline output already exists; refusing overwrite: {target}"
                )
        descriptor, definition_stage_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.private-stage-",
            dir=DEFINITION.parent,
        )
        os.close(descriptor)
        definition_stage = Path(definition_stage_name)
        bundle_stage = Path(
            tempfile.mkdtemp(
                prefix=f".{BUNDLE.name}.private-stage-",
                dir=BUNDLE.parent,
            )
        )
        bundle_published = False
        definition_published = False
        try:
            definition_raw = previous.v5.v3._canonical_json(_definition_document())
            _write_definition_stage(definition_stage, definition_raw)
            planned_wall_clock = _parse_utc(GENERATED_AT, label="timeline generated_at")
            definition = _load_definition(
                definition_stage,
                validation_wall_clock=planned_wall_clock,
            )
            payloads, manifest = _prepare_payloads(definition)
            replay_payloads, replay_manifest = _prepare_payloads(definition)
            if payloads != replay_payloads or manifest != replay_manifest:
                raise ConstructionTimelineError(
                    "v86 inputs changed or two offline reconstructions differ"
                )
            _write_bundle_stage(bundle_stage, payloads)
            validate_construction_timeline_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_frozen=False,
                verify_publication_times=False,
                require_live=False,
                validation_wall_clock=planned_wall_clock,
            )
            definition_stage.chmod(FROZEN_FILE_MODE)
            for target in bundle_stage.iterdir():
                target.chmod(FROZEN_FILE_MODE)
            bundle_stage.chmod(FROZEN_DIRECTORY_MODE)
            if _latest_stage_time(definition_stage, bundle_stage) > (
                planned_wall_clock.timestamp() + 0.000_001
            ):
                raise ConstructionTimelineError(
                    "timeline staging exceeded generated_at; refusing publication"
                )
            _wait_until_generated_at()
            validate_construction_timeline_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_live=False,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            for target in (DEFINITION, BUNDLE):
                if target.exists() or target.is_symlink():
                    raise ConstructionTimelineError(
                        f"late timeline collision; refusing overwrite: {target}"
                    )
            try:
                promote_noreplace(bundle_stage, BUNDLE)
                bundle_published = True
                promote_noreplace(definition_stage, DEFINITION)
                definition_published = True
                result = validate_construction_timeline_bundle(
                    BUNDLE,
                    definition_path=DEFINITION,
                    verify_inputs=True,
                    validation_wall_clock=datetime.now(timezone.utc),
                )
            except BaseException as error:
                try:
                    _rollback_published(
                        definition_stage,
                        bundle_stage,
                        definition_published=definition_published,
                        bundle_published=bundle_published,
                    )
                    definition_published = False
                    bundle_published = False
                except BaseException as rollback_error:
                    error.add_note(str(rollback_error))
                if isinstance(error, SystemExit):
                    raise ConstructionTimelineError(str(error)) from error
                raise
            return result
        finally:
            if not bundle_published:
                _discard_stage(bundle_stage)
            if not definition_published and definition_stage.exists():
                definition_stage.chmod(0o600)
                definition_stage.unlink()


def write_construction_timeline_bundle(
    definition_path: str | Path = DEFINITION,
    output_directory: str | Path = BUNDLE,
) -> dict[str, Any]:
    """Publish only the reserved v8 definition and bundle paths."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineError("timeline v8 publication paths are reserved")
    return publish_construction_timeline_v8()


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "AS_OF",
    "ATTRIBUTION_FILENAME",
    "BUNDLE",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COVERAGE_FILENAME",
    "ConstructionTimelineError",
    "DEFINITION",
    "DELTA_CONTRACT",
    "EXPECTED_COUNTS",
    "GENERATED_AT",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OBSERVATIONS_FILENAME",
    "OBSERVATION_FIELDS",
    "OPEN_SEED_DEFINITION_SHA256",
    "OPEN_SEED_MANIFEST_SHA256",
    "OPEN_SEED_TREE_SHA256",
    "POST_V83_SOURCE_PATHS",
    "PREDECESSOR_DEFINITION_SHA256",
    "PREDECESSOR_MANIFEST_SHA256",
    "PREDECESSOR_TREE_SHA256",
    "TIMELINES_FILENAME",
    "TIMELINE_ID",
    "V86_ADDITION_EVENT_CONTRACT_SHA256",
    "build_construction_timeline_bundle",
    "publish_construction_timeline_v8",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
