"""Publish the strict timeline-v6 successor derived only from open seed v83.

Every accepted v6 flat observation and grouped timeline is retained byte-for-
byte. The successor appends the exact 47-row lifecycle delta introduced by 44
post-v73 official-source records through v83. Coordinate-only and capacity-only
records cannot enter the timeline. Every status remains a dated last-observed
fact; current status is unknown and observation persistence is never inferred.
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

from . import construction_timeline_v2 as carrier
from . import construction_timeline_v6 as previous
from . import open_seed_v83
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-21-public-open-v7"
AS_OF = "2026-07-21"
# Staging must finish before this one-time publication instant.
GENERATED_AT = "2026-07-21T17:50:50Z"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v7.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v7"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v7.lock"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v83.py"
OPEN_SEED_RECORDED_AT = "2026-07-21T17:38:10Z"
OPEN_SEED_DEFINITION_SHA256 = (
    "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5"
)
OPEN_SEED_TREE_SHA256 = (
    "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"
)
OPEN_SEED_CORE_SHA256 = (
    "43bad2af3baecbb9afe8cc0d5d01bfd926efc6180e88ae59bee01aa9dc8da159"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v6.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v6"
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v6.py"
PREDECESSOR_DEFINITION_SHA256 = (
    "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543"
)
PREDECESSOR_TREE_SHA256 = (
    "6f754dcaa6f9d0df7ded14a90da70b2eb7c14d75634ec7bd1c503d47ed060e8f"
)
PREDECESSOR_CORE_SHA256 = (
    "a00f4946d0c3581a8fcfe25b80e817d4156d961bd14fe45a762b4e466bb2296f"
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v7"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v7"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v7"
SCHEMA_VERSION = 7

# The accepted row schema is retained so inherited JSONL lines remain exact.
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
FROZEN_DIRECTORY_MODE = previous.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = previous.FROZEN_FILE_MODE

SCOPE = dict(previous.SCOPE)

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 506,
    "multi_observation_entities": 20,
    "raw_lifecycle_observations": 526,
    "repeated_status_multi_observation_entities": 7,
    "single_observation_entities": 486,
    "single_old_observation_entities": 28,
    "source_families": 244,
    "status_changing_multi_observation_entities": 13,
}

FULL_V83_RAW_OBSERVATIONS = 526
PREDECESSOR_OBSERVATIONS = 479
PREDECESSOR_TIMELINES = 462
V83_ADDED_OBSERVATIONS = 47
V83_ADDED_PROJECTS = 44
V83_INHERITED_RECORDED_AT_REWRITES_IGNORED = 96
V6_ACCEPTED_INPUTS = 397
V83_SELECTED_INPUTS = 441
POST_V73_SELECTED_SOURCES = 44

RECENT_OPERATIONAL_CLOSURE_KEYS = frozenset(
    {
        "curated:gta-gu3-alupang-data-center:initial-build",
        "curated:serbia-state-data-center-kragujevac:modules-3-4-commissioned-2026",
    }
)
STALE_LATEST_ADDITION_KEYS = frozenset(
    {
        "curated:republic-congo-national-data-center-bacongo:current-build",
        "curated:somalia-national-data-center-mogadishu-site-unresolved:"
        "current-build-site-unresolved",
    }
)
SINGLE_OLD_ADDITION_KEYS = frozenset(
    {
        "curated:somalia-national-data-center-mogadishu-site-unresolved:"
        "current-build-site-unresolved",
    }
)

POST_V73_SOURCE_PATHS = (
    "sources/curated-official-2026-07-21-cirion-rio2-current-build.json",
    "sources/curated-official-2026-07-21-cote-divoire-national-dc-vitib-current-build.json",
    "sources/curated-official-2026-07-21-omnia-pecem-current-build.json",
    "sources/curated-official-2026-07-21-niger-national-dc-pk5-current-build.json",
    "sources/curated-official-2026-07-21-somalia-national-dc-site-unresolved-current-build.json",
    "sources/curated-official-2026-07-21-congo-national-dc-bacongo-current-build.json",
    "sources/curated-official-2026-07-21-telia-vilnius-current-build.json",
    "sources/curated-official-2026-07-21-atnorth-ice02-phase-2-current-build.json",
    "sources/curated-official-2026-07-21-borealis-blonduos-expansion-current-build.json",
    "sources/curated-official-2026-07-21-runze-chongqing-phase-2-p6-current-build.json",
    "sources/curated-official-2026-07-21-china-telecom-guizhou-b5-b6-current-build.json",
    "sources/curated-official-2026-07-21-baoji-digital-building-mobile-dc-current-build.json",
    "sources/curated-official-2026-07-21-digital-qinghai-telecom-phase-2-current-build.json",
    "sources/curated-official-2026-07-21-mobile-plateau-haidong-phase-2-current-build.json",
    "sources/curated-official-2026-07-21-zhipu-iflytek-haidong-ai-base-current-build.json",
    "sources/curated-official-2026-07-21-haidong-training-inference-ai-current-build.json",
    "sources/curated-official-2026-07-21-wuhu-longteng-ai-park-current-build.json",
    "sources/curated-official-2026-07-21-china-telecom-tongling-dated-build.json",
    "sources/curated-official-2026-07-21-runze-hong-kong-sandy-ridge-current-build.json",
    "sources/curated-official-2026-07-21-bcc-jashore-dr-data-center-current-build.json",
    "sources/curated-official-2026-07-21-adaniconnex-navi-mumbai-current-development.json",
    "sources/curated-official-2026-07-21-adaniconnex-pune-pnq04-current-build.json",
    "sources/curated-official-2026-07-21-hive-yguazu-100mw-expansion-current-build.json",
    "sources/curated-official-2026-07-21-puntonet-epicentro-quito-current-build.json",
    "sources/curated-official-2026-07-21-icolo-nbo2-current-build.json",
    "sources/curated-official-2026-07-21-telecom-egypt-rdh2-commissioning.json",
    "sources/curated-official-2026-07-21-enka-eds-ist01-tuzla-current-build.json",
    "sources/curated-official-2026-07-21-t964-baghdad-phase1-current-build.json",
    "sources/curated-official-2026-07-21-ezditek-ruh01-pnu-phase1-current-build.json",
    "sources/curated-official-2026-07-21-quantum-switch-doha-4-5mw-expansion-current-build.json",
    "sources/curated-official-2026-07-21-xds-desert-dragon-jeddah-current-build.json",
    "sources/curated-official-2026-07-21-microsoft-ath04-spata-current-build.json",
    "sources/curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json",
    "sources/curated-official-2026-07-21-ten-brinke-spata-current-build.json",
    "sources/curated-official-2026-07-21-ast-janciems-shell-fit-out.json",
    "sources/curated-official-2026-07-21-serbia-state-dc-kragujevac-modules-3-4-operational.json",
    "sources/curated-official-2026-07-21-airtrunk-syd3-current-build.json",
    "sources/curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json",
    "sources/curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json",
    "sources/curated-official-2026-07-21-cdc-marsden-park-current-build.json",
    "sources/curated-official-2026-07-21-cdc-laverton-current-build.json",
    "sources/curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json",
    "sources/curated-official-2026-07-21-cdc-maddington-current-build.json",
    "sources/curated-official-2026-07-21-gta-gu3-alupang-operational-closure.json",
)

EVENT_CONTRACT_FIELDS = previous.EVENT_CONTRACT_FIELDS
V83_ADDITION_EVENT_CONTRACT_SHA256 = (
    "7e861a39470a2dd849be25bd76496b720fb168c2ad138effcd62c88ff91995e7"
)

DELTA_CONTRACT = {
    "full_v83_raw_lifecycle_observations": FULL_V83_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "post_v73_capacity_only_sources_promoted_to_lifecycle": 0,
    "post_v73_coordinate_only_sources_promoted_to_lifecycle": 0,
    "post_v73_selected_source_files": POST_V73_SELECTED_SOURCES,
    "post_v73_sources_with_lifecycle": POST_V73_SELECTED_SOURCES,
    "recorded_at_values_preserved_from_v6": True,
    "v83_added_lifecycle_observations": V83_ADDED_OBSERVATIONS,
    "v83_added_project_entities": V83_ADDED_PROJECTS,
    "v83_inherited_recorded_at_rewrites_ignored": (
        V83_INHERITED_RECORDED_AT_REWRITES_IGNORED
    ),
    "v83_recent_operational_lifecycle_closures": len(RECENT_OPERATIONAL_CLOSURE_KEYS),
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
        raise ConstructionTimelineError("timeline v7 definition contract differs")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if wall_clock.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    generated = _parse_utc(document["generated_at"], label="timeline generated_at")
    if generated <= _parse_utc(OPEN_SEED_RECORDED_AT, label="v83 recorded_at"):
        raise ConstructionTimelineError("timeline generated_at must follow v83")
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
        raise ConstructionTimelineError("accepted v83 or timeline v6 pins differ")
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
        definition.open_seed_definition: OPEN_SEED_DEFINITION_SHA256,
        definition.open_seed_release / MANIFEST_FILENAME: OPEN_SEED_MANIFEST_SHA256,
        OPEN_SEED_CORE: OPEN_SEED_CORE_SHA256,
        definition.predecessor_definition: PREDECESSOR_DEFINITION_SHA256,
        definition.predecessor_bundle / MANIFEST_FILENAME: PREDECESSOR_MANIFEST_SHA256,
        PREDECESSOR_CORE: PREDECESSOR_CORE_SHA256,
    }
    for checkpoint, digest in checkpoints.items():
        if previous.v5.v3._sha256_file(checkpoint) != digest:
            raise ConstructionTimelineError(f"frozen input changed: {checkpoint}")
    if tree_digest(definition.open_seed_release) != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen open seed v83 tree changed")
    if tree_digest(definition.predecessor_bundle) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v6 tree changed")
    try:
        seed_manifest = open_seed_v83.validate_open_seed_v83(
            definition.open_seed_definition,
            definition.open_seed_release,
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
            definition.open_seed_release / MANIFEST_FILENAME, "v83 manifest"
        ),
        "v83 manifest",
    )
    frozen_predecessor_manifest = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            definition.predecessor_bundle / MANIFEST_FILENAME, "timeline v6 manifest"
        ),
        "timeline v6 manifest",
    )
    if (
        seed_manifest != frozen_seed_manifest
        or predecessor_manifest != frozen_predecessor_manifest
    ):
        raise ConstructionTimelineError("validated frozen input manifest differs")


def _release_labels(release: Path) -> dict[str, dict[str, str]]:
    raw = previous.v5.v3._regular_bytes(release / "entities.csv", "v83 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v83 entities.csv is not UTF-8") from error
    if len(rows) != 905:
        raise ConstructionTimelineError("v83 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v83 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _post_v73_source_contract() -> dict[str, str]:
    raw = previous.v5.v3._regular_bytes(OPEN_SEED_DEFINITION, "v83 definition")
    if previous.v5.v3._sha256_bytes(raw) != OPEN_SEED_DEFINITION_SHA256:
        raise ConstructionTimelineError("frozen v83 definition changed")
    document = previous.v5.v3._json_object(raw, "v83 definition")
    inputs = document.get("curated_inputs")
    if not isinstance(inputs, list) or len(inputs) != V83_SELECTED_INPUTS:
        raise ConstructionTimelineError("v83 selected input inventory differs")
    additions = inputs[V6_ACCEPTED_INPUTS:]
    if tuple(row.get("path") for row in additions) != POST_V73_SOURCE_PATHS:
        raise ConstructionTimelineError("post-v73 source path contract differs")

    source_by_key: dict[str, str] = {}
    lifecycle_count = 0
    for item in additions:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ConstructionTimelineError("post-v73 source checkpoint differs")
        display = str(item["path"])
        path = ROOT / display
        if previous.v5.v3._sha256_file(path) != item["sha256"]:
            raise ConstructionTimelineError(f"post-v73 source changed: {display}")
        source = previous.v5.v3._json_object(
            previous.v5.v3._regular_bytes(path, display), display
        )
        project = source.get("project")
        lifecycle = source.get("lifecycle")
        if (
            not isinstance(project, Mapping)
            or not isinstance(project.get("stable_key"), str)
            or not isinstance(lifecycle, list)
            or not lifecycle
            or any(
                not isinstance(row, Mapping) or row.get("entity") != "project"
                for row in lifecycle
            )
        ):
            raise ConstructionTimelineError(
                f"post-v73 source is not lifecycle-bearing: {display}"
            )
        stable_key = str(project["stable_key"])
        if stable_key in source_by_key:
            raise ConstructionTimelineError("post-v73 project source is ambiguous")
        source_by_key[stable_key] = display
        lifecycle_count += len(lifecycle)
    if (
        len(source_by_key) != V83_ADDED_PROJECTS
        or lifecycle_count != V83_ADDED_OBSERVATIONS
    ):
        raise ConstructionTimelineError("post-v73 lifecycle source accounting differs")
    return source_by_key


def _full_v83_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_inputs(definition)
    v83_document = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            definition.open_seed_definition, "v83 definition"
        ),
        "v83 definition",
    )
    base = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            open_seed_v83.BASE_DEFINITION, "v82 base definition"
        ),
        "v82 base definition",
    )
    try:
        selected_rows, paths = open_seed_v83.selected_inputs(
            base,
            recorded_at=OPEN_SEED_RECORDED_AT,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("v83 source selection failed") from error
    if (
        v83_document.get("build")
        != {"as_of": AS_OF, "recorded_at": OPEN_SEED_RECORDED_AT}
        or selected_rows != v83_document.get("curated_inputs")
        or len(paths) != V83_SELECTED_INPUTS
    ):
        raise ConstructionTimelineError("fresh v83 source inventory differs")
    labels = _release_labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v7-db-",
        dir="/private/tmp",
    ) as temporary:
        try:
            connection = open_seed_v83._build_database(
                base,
                paths,
                Path(temporary) / "atlas.sqlite",
                recorded_at=OPEN_SEED_RECORDED_AT,
            )
        except (OSError, ValueError, RuntimeError, SystemExit) as error:
            raise ConstructionTimelineError(
                "fresh v83 database rebuild failed"
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
            raise ConstructionTimelineError("v83 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if len(observations) != FULL_V83_RAW_OBSERVATIONS or len(
        {row["observation_id"] for row in observations}
    ) != len(observations):
        raise ConstructionTimelineError("full v83 lifecycle inventory differs")
    return observations


def _predecessor_observations(definition: _Definition) -> list[dict[str, str]]:
    rows = previous.v5.v3._parse_csv(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME
    )
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("timeline v6 observation inventory differs")
    if previous.v5.v3._csv_bytes(rows) != previous.v5.v3._regular_bytes(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME, "v6 observations"
    ):
        raise ConstructionTimelineError("timeline v6 observation bytes differ")
    return rows


def _predecessor_timelines(definition: _Definition) -> list[dict[str, Any]]:
    rows = previous.v5.v3._parse_jsonl(
        definition.predecessor_bundle / TIMELINES_FILENAME
    )
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("timeline v6 entity inventory differs")
    if b"".join(
        previous.v5.v3._canonical_json_line(row) for row in rows
    ) != previous.v5.v3._regular_bytes(
        definition.predecessor_bundle / TIMELINES_FILENAME, "v6 timelines"
    ):
        raise ConstructionTimelineError("timeline v6 JSONL bytes differ")
    return rows


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    source_by_key = _post_v73_source_contract()
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
    full = _full_v83_observations(definition)
    predecessor = _predecessor_observations(definition)
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v83 dropped a timeline v6 observation")
    rewrite_count = 0
    for row in predecessor:
        fresh = previous.v5.v3._csv_row(full_by_id[row["observation_id"]])
        differences = {
            field for field in OBSERVATION_FIELDS if row[field] != fresh[field]
        }
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v83 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
    if rewrite_count != V83_INHERITED_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError(
            "v83 inherited recorded_at rewrite count differs"
        )

    additions = [
        row for row in full if str(row["observation_id"]) not in predecessor_ids
    ]
    source_by_key = _post_v73_source_contract()
    contract = _event_contract(additions)
    if (
        len(additions) != V83_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in additions}) != V83_ADDED_PROJECTS
        or {str(row["entity_stable_key"]) for row in additions} != set(source_by_key)
        or _event_contract_sha256(contract) != V83_ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineError("v83 addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids:
        raise ConstructionTimelineError("v83 addition collides with timeline v6")
    if set(full_by_id) - predecessor_ids != addition_ids:
        raise ConstructionTimelineError("v83 full-to-v6 delta boundary differs")
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
        raise ConstructionTimelineError("timeline v7 observation inventory differs")
    return combined, additions


def _timeline_rows(
    definition: _Definition,
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines(definition)
    new_rows = carrier._timeline_rows(additions, as_of=AS_OF)
    if len(new_rows) != V83_ADDED_PROJECTS or any(
        row["format"] != TIMELINE_FORMAT
        or row["schema_version"] != TIMELINE_SCHEMA_VERSION
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] is not False
        or row["latest_observation_persistence_assumed"] is not False
        for row in new_rows
    ):
        raise ConstructionTimelineError("v83 addition timeline guardrails differ")
    changing_keys = {
        row["entity_stable_key"] for row in new_rows if row["has_status_change"]
    }
    if changing_keys:
        raise ConstructionTimelineError("v83 status-changing timeline boundary differs")
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
            "v83 terminal or stale timeline boundary differs"
        )
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("timeline v7 entity collides with timeline v6")
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
    source_by_key = _post_v73_source_contract()
    additions = [
        row for row in observations if str(row["entity_stable_key"]) in source_by_key
    ]
    event_contract = _event_contract(additions)
    if _event_contract_sha256(event_contract) != V83_ADDITION_EVENT_CONTRACT_SHA256:
        raise ConstructionTimelineError("v83 coverage event contract differs")
    events = _event_documents(event_contract)
    predecessor_coverage = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v6 coverage"
        ),
        "v6 coverage",
    )
    additions_by_key: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        additions_by_key.setdefault(str(event["entity_stable_key"]), []).append(event)
    recent_operational_closures = [
        {
            "construction_sequence_semantics": "closed_by_dated_operational_observation",
            "current_construction_claim": False,
            "current_operational_claim": False,
            "current_status_classification": "unknown",
            "entity_stable_key": key,
            "latest_observation_persistence_assumed": False,
            "observed_date": additions_by_key[key][-1]["observed_date"],
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
            "latest_observed_date": additions_by_key[key][-1]["observed_date"],
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
        "post_v73_non_lifecycle_promotion": {
            "capacity_only_sources_promoted_to_lifecycle": 0,
            "coordinate_only_sources_promoted_to_lifecycle": 0,
        },
        "recent_operational_lifecycle_closures": recent_operational_closures,
        "stale_latest_addition_timelines": stale_latest_timelines,
        "v6_inherited_v72_coordinate_only_delta": predecessor_coverage[
            "v72_coordinate_only_delta"
        ],
        "v83_addition_events": events,
        "v83_addition_event_contract_sha256": V83_ADDITION_EVENT_CONTRACT_SHA256,
        "v83_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v7\n\n"
        "This immutable exact successor preserves all 479 accepted v6 lifecycle "
        "observations and all 462 accepted v6 entity-timeline rows byte-for-byte, "
        "then appends 47 raw v83 observations on 44 new project identities. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} source-scoped entities.\n\n"
        "A complete 526-row v83 lifecycle database is rebuilt offline. Ninety-six "
        "v83 recorded_at rewrites never replace the predecessor's accepted recording "
        "lineage. All 44 post-v73 selected sources are independently hash-checked and "
        "carry explicit project lifecycle observations. Coordinate-only and capacity-"
        "only records contribute no timeline row.\n\n"
        "Every lifecycle status remains a dated last-observed fact. Current status is "
        "unknown, current construction is never claimed, and the latest observation "
        "is never assumed to persist. GU3 and Serbia modules 3/4 have dated operational "
        "observations that close their source-scoped construction sequences; neither "
        "becomes a current-operational claim. The stale Congo and Somalia sequences, "
        "STT Johor, and every other old start remain current-unknown.\n\n"
        "Permits, forecasts, planned dates, satellite or CV review, and missing "
        "milestones are not promoted or interpolated into physical construction. "
        "Cross-source identities remain unresolved and unique physical sites remain "
        "null. Only the hash-pinned v6 timeline and v83 open seed are checkpoints.\n"
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
        "Derived only from the hash-pinned construction timeline v6 and open seed v83 inputs.",
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
                "bytes": definition.open_seed_definition.stat().st_size,
                "file": definition.open_seed_definition.name,
                "sha256": OPEN_SEED_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": (definition.open_seed_release / MANIFEST_FILENAME)
                .stat()
                .st_size,
                "file": MANIFEST_FILENAME,
                "sha256": OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": definition.open_seed_release.name,
            "release_tree_sha256": OPEN_SEED_TREE_SHA256,
        },
        "predecessor_input": {
            "definition": {
                "bytes": definition.predecessor_definition.stat().st_size,
                "file": definition.predecessor_definition.name,
                "sha256": PREDECESSOR_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": (definition.predecessor_bundle / MANIFEST_FILENAME)
                .stat()
                .st_size,
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
    stable_order = [
        (
            row["entity_stable_key"],
            row["observed_date"],
            row["recorded_at"],
            row["observation_id"],
        )
        for row in observations
    ]
    if stable_order != sorted(stable_order):
        raise ConstructionTimelineError("observation CSV ordering differs")
    timeline_order = [
        (row.get("entity_stable_key"), row.get("entity_id")) for row in timelines
    ]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(
        timeline_order
    ):
        raise ConstructionTimelineError("timeline JSONL identity ordering differs")
    flattened_ids = []
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
        raise ConstructionTimelineError(
            "flat and grouped observation inventories differ"
        )
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
    predecessor_rows = previous.v5.v3._parse_csv(
        PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME
    )
    current_by_id = {row["observation_id"]: row for row in observations}
    if any(current_by_id.get(row["observation_id"]) != row for row in predecessor_rows):
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
    source_by_key = _post_v73_source_contract()
    additions = [
        row for row in observations if row["entity_stable_key"] in source_by_key
    ]
    contract = _event_contract(additions)
    if (
        len(additions) != V83_ADDED_OBSERVATIONS
        or _event_contract_sha256(contract) != V83_ADDITION_EVENT_CONTRACT_SHA256
        or coverage.get("v83_addition_events") != _event_documents(contract)
        or coverage.get("v83_addition_event_contract_sha256")
        != V83_ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineError("published v83 event contract differs")
    if coverage.get("post_v73_non_lifecycle_promotion") != {
        "capacity_only_sources_promoted_to_lifecycle": 0,
        "coordinate_only_sources_promoted_to_lifecycle": 0,
    }:
        raise ConstructionTimelineError("post-v73 non-lifecycle boundary differs")
    predecessor_coverage = previous.v5.v3._json_object(
        previous.v5.v3._regular_bytes(
            PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v6 coverage"
        ),
        "v6 coverage",
    )
    if coverage.get(
        "v6_inherited_v72_coordinate_only_delta"
    ) != predecessor_coverage.get("v72_coordinate_only_delta"):
        raise ConstructionTimelineError("inherited coordinate-only contract differs")
    closures = coverage.get("recent_operational_lifecycle_closures")
    if (
        not isinstance(closures, list)
        or {row.get("entity_stable_key") for row in closures}
        != RECENT_OPERATIONAL_CLOSURE_KEYS
        or any(
            row.get("status") != "operational"
            or row.get("status_semantics") != "last_observed"
            or row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("current_operational_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
            for row in closures
        )
    ):
        raise ConstructionTimelineError(
            "operational lifecycle closure contract differs"
        )
    stale = coverage.get("stale_latest_addition_timelines")
    if (
        not isinstance(stale, list)
        or {row.get("entity_stable_key") for row in stale} != STALE_LATEST_ADDITION_KEYS
        or any(
            row.get("status_semantics") != "stale_last_observed"
            or row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
            for row in stale
        )
    ):
        raise ConstructionTimelineError("stale addition timeline contract differs")
    stt = coverage.get("stt_johor_historical_only")
    if (
        not isinstance(stt, Mapping)
        or stt.get("observation_age_days") != 512
        or stt.get("freshness_class") != "stale_over_365_days"
        or stt.get("status_semantics") != "last_observed"
        or stt.get("current_status_classification") != "unknown"
        or stt.get("current_construction_claim") is not False
        or stt.get("latest_observation_persistence_assumed") is not False
    ):
        raise ConstructionTimelineError("STT Johor historical-only contract differs")


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
    """Validate the closed v7 bundle and optionally replay both accepted inputs."""

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
    files = manifest.get("files")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
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
        except (
            BaseException
        ) as error:  # pragma: no cover - catastrophic filesystem path
            errors.append(f"definition rollback failed: {error}")
    if bundle_published:
        try:
            promote_noreplace(BUNDLE, bundle_stage)
        except (
            BaseException
        ) as error:  # pragma: no cover - catastrophic filesystem path
            errors.append(f"bundle rollback failed: {error}")
    if errors:
        raise ConstructionTimelineError("; ".join(errors))


def publish_construction_timeline_v7() -> dict[str, Any]:
    """Privately stage, double-rebuild, freeze, and no-replace publish v7."""

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
            planned_wall_clock = _parse_utc(
                GENERATED_AT,
                label="timeline generated_at",
            )
            definition = _load_definition(
                definition_stage,
                validation_wall_clock=planned_wall_clock,
            )
            payloads, manifest = _prepare_payloads(definition)
            replay_payloads, replay_manifest = _prepare_payloads(definition)
            if payloads != replay_payloads or manifest != replay_manifest:
                raise ConstructionTimelineError(
                    "v83 inputs changed or two offline timeline reconstructions differ"
                )
            _write_bundle_stage(bundle_stage, payloads)
            validate_construction_timeline_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_frozen=False,
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
    """Publish only the reserved v7 definition and bundle paths."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineError("timeline v7 publication paths are reserved")
    return publish_construction_timeline_v7()


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "AS_OF",
    "ATTRIBUTION_FILENAME",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COVERAGE_FILENAME",
    "ConstructionTimelineError",
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
    "PREDECESSOR_DEFINITION_SHA256",
    "PREDECESSOR_MANIFEST_SHA256",
    "PREDECESSOR_TREE_SHA256",
    "POST_V73_SOURCE_PATHS",
    "RECENT_OPERATIONAL_CLOSURE_KEYS",
    "SCHEMA_VERSION",
    "SCOPE",
    "TIMELINES_FILENAME",
    "TIMELINE_FORMAT",
    "TIMELINE_ID",
    "TIMELINE_SCHEMA_VERSION",
    "STALE_LATEST_ADDITION_KEYS",
    "V83_ADDITION_EVENT_CONTRACT_SHA256",
    "build_construction_timeline_bundle",
    "publish_construction_timeline_v7",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
