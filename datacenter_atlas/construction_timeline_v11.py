"""Governed v10-to-v11 construction timeline successor.

V11 preserves every accepted v10 lifecycle-observation row byte-for-byte and
adds only the 36 lifecycle observations first accepted by open seeds v93-v97.
Thirty-three entity timelines are new.  FIN04 is the sole inherited grouped
timeline replaced: its 2026-07-20 and 2026-07-21 under-construction
observations are retained as a repeated-status history.  No dated observation
is promoted to a current-status, coordinate, capacity, or unique-site claim.

The default entry point is private prepublication.  Final publication is
available only through an explicit ``publication_authorized=True`` gate.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import errno
import io
import json
import os
import secrets
import shutil
import stat
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import construction_timeline_v10 as previous
from . import open_seed_v93, open_seed_v94, open_seed_v95, open_seed_v96, open_seed_v97
from .open_seed_v56 import tree_digest

ROOT = Path(__file__).resolve().parents[1]
CODEC = previous.CODEC
TIMELINE_CARRIER = previous.TIMELINE_CARRIER

TIMELINE_ID = "2026-07-22-public-open-v11"
AS_OF = "2026-07-22"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-22-public-open-v11.json"
BUNDLE = ROOT / "construction_timelines/2026-07-22-public-open-v11"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v11.lock"

PREDECESSOR_DEFINITION = previous.DEFINITION
PREDECESSOR_BUNDLE = previous.BUNDLE
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v10.py"
PREDECESSOR_DEFINITION_PIN = (
    7_042,
    "8c06566529d45cd209fb9f055a69b5146e79bbc1f83f15e9cbf9060a66cbf333",
)
PREDECESSOR_MANIFEST_PIN = (
    8_279,
    "c2fa0fb5041ebdea9ec320f5d922833bf53574f5efe6091db79e1db6cc304e28",
)
PREDECESSOR_TREE_SHA256 = (
    "6e4a42092f26736ad0db89c06259d419d7156c4e516a5dfb20a13507e2cafb9a"
)
PREDECESSOR_CORE_PIN = (
    60_584,
    "2d22ec31de3a4e50ec743ad4657a47deefff2e11ce9c9975dd3baa8ea25acd07",
)


@dataclass(frozen=True, slots=True)
class _ReleaseSpec:
    version: int
    module: Any
    recorded_at: str
    definition_pin: tuple[int, str]
    manifest_pin: tuple[int, str]
    tree_sha256: str
    core_pin: tuple[int, str]
    addition_order: tuple[str, ...]
    lifecycle_contract: frozenset[tuple[str, str, str, str]]
    added_observations: int
    added_timeline_entities: int

    @property
    def release_id(self) -> str:
        return str(self.module.RELEASE_ID)

    @property
    def definition(self) -> Path:
        return Path(self.module.DEFINITION)

    @property
    def release(self) -> Path:
        return Path(self.module.RELEASE)

    @property
    def core(self) -> Path:
        return ROOT / f"datacenter_atlas/open_seed_v{self.version}.py"


RELEASE_SPECS = (
    _ReleaseSpec(
        93,
        open_seed_v93,
        "2026-07-22T02:54:34Z",
        (110_743, "cf8ed21cd0816f457fa2cede36fbf1bf012d62ed61d03a5e3213de9946394e9c"),
        (16_832, "9a5b39004ab1a4c7994ad653d5d9603572b4a47a3c502ea222eeae38d32fa05c"),
        "71c531ffa7f8383e2ae553a71abe15e940e8d6251acccbf17556bc492df78f0d",
        (73_366, "eea98c7da445c3ea7106af77b266a5deb013533a154bea837cccbb6a3ba5dfe2"),
        tuple(open_seed_v93.ADDITION_ORDER),
        frozenset(open_seed_v93.LIFECYCLE_CONTRACT),
        3,
        3,
    ),
    _ReleaseSpec(
        94,
        open_seed_v94,
        "2026-07-22T03:35:54Z",
        (113_819, "c65f61b3708b4cdc1fb755eaf8d0edffab545526f206689e66056220b27cc0ff"),
        (17_866, "8315811764024f026eb2fc69f9ff06b738c554dcd9717aed6ba9254f6cf3fc65"),
        "e947ec413e1c43ea053f7766928ccab373f7e1f058be42fc5c433ea7dda49766",
        (97_187, "b5699e0e001a96255d4a38b9d199d77d837272e5a792f5584b9575fc31b378fb"),
        tuple(open_seed_v94.ADDITION_ORDER),
        frozenset(open_seed_v94.LIFECYCLE_CONTRACT),
        11,
        9,
    ),
    _ReleaseSpec(
        95,
        open_seed_v95,
        "2026-07-22T04:21:58Z",
        (117_088, "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15"),
        (19_195, "1181fa215be08c130bf237107c68a461a4762e020b7120041f19cd705b6b7af6"),
        "752593650007f602f2bd13f2bd0c3ac8702cdd74c4b6103ec2bdaa348c6ef17a",
        (80_379, "f10a6cf6e06e432bd0b660cbfcb3452603a60f2b9f8ad5cff55c67c62e3f923d"),
        tuple(open_seed_v95.ADDITION_ORDER),
        frozenset(open_seed_v95.LIFECYCLE_CONTRACT),
        9,
        9,
    ),
    _ReleaseSpec(
        96,
        open_seed_v96,
        "2026-07-22T05:29:06Z",
        (121_029, "d49c9de9aaded6af7c103375b71d07f0904fe6cc7a24785a678e82bfe5e6d6c0"),
        (21_007, "8407f11a8e414810cd7d56ee5fd6f7e95015771c72d3106e4ab96d1ddb41422e"),
        "8fdd260892474febf2ac3dc7a368b68ecda419d53f97357b54142b1c40bca558",
        (110_920, "d65711ef0a40216db8a811626369018df6f7216f0f54e49170663bcb9f50e9e1"),
        tuple(open_seed_v96.ALL_SUCCESSOR_ORDER),
        frozenset(open_seed_v96.EXPECTED_LIFECYCLE),
        10,
        9,
    ),
    _ReleaseSpec(
        97,
        open_seed_v97,
        "2026-07-22T06:06:40Z",
        (120_979, "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f"),
        (20_402, "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"),
        "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954",
        (88_620, "47ac8cacfebf6a9179be22db5368aae5066faf14e47e3bbd591208f331958466"),
        tuple(open_seed_v97.APPEND_ORDER),
        frozenset(open_seed_v97.EXPECTED_LIFECYCLE),
        3,
        3,
    ),
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v11"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v11"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v11"
SCHEMA_VERSION = 11

# The published row schema remains frozen so every inherited observation row
# and every unaffected inherited grouped timeline can remain byte-identical.
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
SCOPE = {**previous.SCOPE, "capacity_inference_applied": False}

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 583,
    "multi_observation_entities": 24,
    "raw_lifecycle_observations": 607,
    "repeated_status_multi_observation_entities": 9,
    "single_observation_entities": 559,
    "single_old_observation_entities": 38,
    "source_families": 297,
    "status_changing_multi_observation_entities": 15,
}

PREDECESSOR_OBSERVATIONS = 571
PREDECESSOR_TIMELINES = 550
ADDED_OBSERVATIONS = 36
ADDITION_EVENT_ENTITIES = 34
ADDED_TIMELINE_ENTITIES = 33
REPLACED_TIMELINES = 1
RELEASE_ADDITION_COUNTS = {
    spec.release_id: spec.added_observations for spec in RELEASE_SPECS
}
RELEASE_TIMELINE_ENTITY_COUNTS = {
    spec.release_id: spec.added_timeline_entities for spec in RELEASE_SPECS
}

FIN04_KEY = "curated:atnorth-fin04-kouvola-campus:phase-1"
WOOD_DALE_KEY = "curated:cyrusone-wood-dale-campus:phase-1-current-build"
BEALE_TULSA_KEY = (
    "curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build"
)
STALE_CURRENT_UNKNOWN_KEYS = frozenset(
    {
        "curated:cmc-creative-space-hanoi:data-center-tower",
        "curated:edgnex-second-jakarta-ai-data-center:phase-1-early-construction",
        "curated:oran-ai-data-center-campus:current-build",
    }
)

ADDITION_EVENT_CONTRACT_SHA256 = (
    "543cebf3d08c87975fac4997410e5540370d84c81c213d65c20a1bc4a6b79c69"
)
LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES = 296
LINEAGE_AWARE_SOURCE_FAMILIES = 297

INFERENCE_GUARDRAILS = {
    "capacity_inferences": 0,
    "coordinate_or_geometry_changes": 0,
    "cross_source_identity_merges": 0,
    "current_status_persistence_claims": 0,
    "forecast_conversions": 0,
    "lifecycle_valid_to_rewrites": 0,
    "satellite_or_cv_promotions": 0,
    "unique_physical_site_claims": 0,
}

DELTA_CONTRACT = {
    "added_lifecycle_observations": ADDED_OBSERVATIONS,
    "added_observation_entity_keys": ADDITION_EVENT_ENTITIES,
    "added_timeline_entities": ADDED_TIMELINE_ENTITIES,
    "append_only_predecessor_observations": previous.TIMELINE_ID,
    "fin04_grouped_timeline_replacements": REPLACED_TIMELINES,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "open_seed_release_additions": RELEASE_ADDITION_COUNTS,
    "predecessor_observations_preserved_exactly": True,
    "raw_lifecycle_observations": EXPECTED_COUNTS["raw_lifecycle_observations"],
    "unaffected_predecessor_timelines_preserved_exactly": True,
}

PROMOTION_CONTRACT = {
    "atomic_no_replace_required": True,
    "definition_and_bundle_same_filesystem_as_final_parent": True,
    "identity_checked_before_and_after_promotion": True,
    "rollback_uses_atomic_no_replace": True,
    "rollback_refuses_identity_mismatch": True,
    "replay_count": 2,
    "stage_adoption_allowed": False,
}

ParentBindings = Mapping[str, tuple[Path, tuple[int, int], int]]


class ConstructionTimelineV11Error(previous.ConstructionTimelineError):
    """Raised when v11 lineage, semantics, or publication differs."""


ConstructionTimelineError = ConstructionTimelineV11Error
_OPERATION_FAILURES = (
    AttributeError,
    AssertionError,
    ConstructionTimelineV11Error,
    KeyError,
    KeyboardInterrupt,
    MemoryError,
    OSError,
    RuntimeError,
    SystemExit,
    TypeError,
    ValueError,
)


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    timeline_id: str
    as_of: str
    generated_at: str
    expected: Mapping[str, Any]


def _parse_utc(value: Any, *, label: str) -> datetime:
    return previous._parse_utc(value, label=label)


def _sha256(raw: bytes) -> str:
    return CODEC._sha256_bytes(raw)


def _file_pin(path: Path) -> tuple[int, str]:
    raw = CODEC._regular_bytes(path, str(path))
    return len(raw), _sha256(raw)


def _canonical_document(path: Path, label: str) -> Mapping[str, Any]:
    raw = CODEC._regular_bytes(path, label)
    document = CODEC._json_object(raw, label)
    if raw != CODEC._canonical_json(document):
        raise ConstructionTimelineV11Error(f"{label} is not canonical JSON")
    return document


def _bundle_checkpoint(
    definition: Path,
    bundle: Path,
    definition_pin: tuple[int, str],
    manifest_pin: tuple[int, str],
    tree_sha256: str,
) -> dict[str, Any]:
    return {
        "bundle_path": f"../{bundle.parent.name}/{bundle.name}",
        "definition": {
            "bytes": definition_pin[0],
            "path": definition.name,
            "sha256": definition_pin[1],
        },
        "expected_bundle_tree_sha256": tree_sha256,
        "manifest": {
            "bytes": manifest_pin[0],
            "canonical_json_required": True,
            "path": f"../{bundle.parent.name}/{bundle.name}/{MANIFEST_FILENAME}",
            "sha256": manifest_pin[1],
        },
    }


def _release_checkpoint(spec: _ReleaseSpec) -> dict[str, Any]:
    return {
        "core": {
            "bytes": spec.core_pin[0],
            "path": f"../datacenter_atlas/{spec.core.name}",
            "sha256": spec.core_pin[1],
        },
        "definition": {
            "bytes": spec.definition_pin[0],
            "canonical_json_required": True,
            "path": spec.definition.name,
            "sha256": spec.definition_pin[1],
        },
        "expected_added_lifecycle_observations": spec.added_observations,
        "expected_added_timeline_entities": spec.added_timeline_entities,
        "expected_release_tree_sha256": spec.tree_sha256,
        "manifest": {
            "bytes": spec.manifest_pin[0],
            "canonical_json_required": True,
            "path": f"../releases/{spec.release.name}/{MANIFEST_FILENAME}",
            "sha256": spec.manifest_pin[1],
        },
        "recorded_at": spec.recorded_at,
        "release_id": spec.release_id,
        "release_path": f"../releases/{spec.release.name}",
    }


def _definition_document(generated_at: str) -> dict[str, Any]:
    return {
        "as_of": AS_OF,
        "delta": DELTA_CONTRACT,
        "expected": EXPECTED_COUNTS,
        "format": DEFINITION_FORMAT,
        "generated_at": generated_at,
        "open_seed_inputs": [_release_checkpoint(spec) for spec in RELEASE_SPECS],
        "predecessor": _bundle_checkpoint(
            PREDECESSOR_DEFINITION,
            PREDECESSOR_BUNDLE,
            PREDECESSOR_DEFINITION_PIN,
            PREDECESSOR_MANIFEST_PIN,
            PREDECESSOR_TREE_SHA256,
        ),
        "promotion_contract": PROMOTION_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": TIMELINE_ID,
    }


def _load_definition(
    path_value: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
    allow_future: bool = False,
) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = CODEC._regular_bytes(path, "timeline v11 definition")
    document = CODEC._json_object(raw, "timeline v11 definition")
    if raw != CODEC._canonical_json(document):
        raise ConstructionTimelineV11Error(
            "timeline v11 definition must be canonical JSON"
        )
    generated_at = document.get("generated_at")
    generated = _parse_utc(generated_at, label="timeline v11 generated_at")
    if document != _definition_document(str(generated_at)):
        raise ConstructionTimelineV11Error("timeline v11 definition contract differs")
    latest_input = max(
        _parse_utc(spec.recorded_at, label=f"open seed v{spec.version} recorded_at")
        for spec in RELEASE_SPECS
    )
    if generated <= latest_input:
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at must follow all inputs"
        )
    wall = validation_wall_clock or datetime.now(UTC)
    if wall.tzinfo is None:
        raise ConstructionTimelineV11Error(
            "validation wall clock must include a timezone"
        )
    if not allow_future and generated > wall.astimezone(UTC):
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at exceeds validation wall clock"
        )
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=str(generated_at),
        expected=EXPECTED_COUNTS,
    )


def _input_guard_state() -> dict[str, Any]:
    return {
        "predecessor": {
            "core": _file_pin(PREDECESSOR_CORE),
            "definition": _file_pin(PREDECESSOR_DEFINITION),
            "manifest": _file_pin(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
            "tree": tree_digest(PREDECESSOR_BUNDLE),
        },
        "releases": {
            spec.release_id: {
                "core": _file_pin(spec.core),
                "definition": _file_pin(spec.definition),
                "manifest": _file_pin(spec.release / MANIFEST_FILENAME),
                "tree": tree_digest(spec.release),
            }
            for spec in RELEASE_SPECS
        },
    }


def _reviewed_input_guard() -> dict[str, Any]:
    return {
        "predecessor": {
            "core": PREDECESSOR_CORE_PIN,
            "definition": PREDECESSOR_DEFINITION_PIN,
            "manifest": PREDECESSOR_MANIFEST_PIN,
            "tree": PREDECESSOR_TREE_SHA256,
        },
        "releases": {
            spec.release_id: {
                "core": spec.core_pin,
                "definition": spec.definition_pin,
                "manifest": spec.manifest_pin,
                "tree": spec.tree_sha256,
            }
            for spec in RELEASE_SPECS
        },
    }


def _validate_input_pins() -> None:
    state = _input_guard_state()
    if state != _reviewed_input_guard():
        raise ConstructionTimelineV11Error("timeline v11 frozen input guard differs")

    _canonical_document(PREDECESSOR_DEFINITION, "timeline v10 definition")
    _canonical_document(PREDECESSOR_BUNDLE / MANIFEST_FILENAME, "timeline v10 manifest")
    try:
        validated_predecessor = previous.validate_construction_timeline_bundle(
            PREDECESSOR_BUNDLE,
            definition_path=PREDECESSOR_DEFINITION,
            verify_inputs=False,
        )
    except previous.ConstructionTimelineError as error:
        raise ConstructionTimelineV11Error(
            f"timeline v10 predecessor validation failed: {error}"
        ) from error
    frozen_predecessor = _canonical_document(
        PREDECESSOR_BUNDLE / MANIFEST_FILENAME, "timeline v10 manifest"
    )
    if validated_predecessor != frozen_predecessor:
        raise ConstructionTimelineV11Error("validated timeline v10 manifest differs")

    for spec in RELEASE_SPECS:
        definition = _canonical_document(
            spec.definition, f"open seed v{spec.version} definition"
        )
        manifest = _canonical_document(
            spec.release / MANIFEST_FILENAME,
            f"open seed v{spec.version} full manifest",
        )
        if (
            definition.get("release_id") != spec.release_id
            or definition.get("build")
            != {"as_of": spec.module.AS_OF, "recorded_at": spec.recorded_at}
            or manifest.get("as_of") != AS_OF
            or manifest.get("recorded_at") != spec.recorded_at
        ):
            raise ConstructionTimelineV11Error(
                f"open seed v{spec.version} canonical manifest contract differs"
            )


def _predecessor_observations() -> list[dict[str, str]]:
    rows = CODEC._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    raw = CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME, "v10 observations"
    )
    if len(rows) != PREDECESSOR_OBSERVATIONS or CODEC._csv_bytes(rows) != raw:
        raise ConstructionTimelineV11Error("timeline v10 observation bytes differ")
    return rows


def _predecessor_timelines() -> list[dict[str, Any]]:
    rows = CODEC._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    raw = CODEC._regular_bytes(PREDECESSOR_BUNDLE / TIMELINES_FILENAME, "v10 timelines")
    rebuilt = b"".join(CODEC._canonical_json_line(row) for row in rows)
    if len(rows) != PREDECESSOR_TIMELINES or rebuilt != raw:
        raise ConstructionTimelineV11Error("timeline v10 grouped timeline bytes differ")
    return rows


def _source_path_contract(
    spec: _ReleaseSpec,
) -> dict[tuple[str, str, str, str], str]:
    result: dict[tuple[str, str, str, str], str] = {}
    for display in spec.addition_order:
        document = CODEC._json_object(
            CODEC._regular_bytes(ROOT / display, display), display
        )
        project = document.get("project")
        lifecycle = document.get("lifecycle")
        if not isinstance(project, Mapping) or not isinstance(lifecycle, list):
            raise ConstructionTimelineV11Error(
                f"open seed v{spec.version} source differs"
            )
        stable_key = str(project.get("stable_key"))
        for event in lifecycle:
            if not isinstance(event, Mapping) or event.get("entity") != "project":
                raise ConstructionTimelineV11Error("lifecycle source contract differs")
            key = (
                stable_key,
                str(event.get("value")),
                str(event.get("as_of_date")),
                str(event.get("method")),
            )
            if key in result:
                raise ConstructionTimelineV11Error("lifecycle source event collides")
            result[key] = str(display)
    if (
        set(result) != set(spec.lifecycle_contract)
        or len(result) != spec.added_observations
    ):
        raise ConstructionTimelineV11Error(
            f"open seed v{spec.version} source lifecycle contract differs"
        )
    return result


def _release_labels(spec: _ReleaseSpec) -> dict[str, dict[str, str]]:
    raw = CODEC._regular_bytes(
        spec.release / "entities.csv", f"open seed v{spec.version} entities"
    )
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineV11Error(
            f"open seed v{spec.version} entities are not UTF-8"
        ) from error
    labels = {row["entity_id"]: row for row in rows}
    if len(labels) != len(rows):
        raise ConstructionTimelineV11Error(
            f"open seed v{spec.version} entity labels collide"
        )
    return labels


def _release_additions(
    spec: _ReleaseSpec,
    temporary_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    definition = _canonical_document(
        spec.definition, f"open seed v{spec.version} definition"
    )
    base = _canonical_document(
        spec.module.BASE_DEFINITION, f"open seed v{spec.version} base definition"
    )
    try:
        selected, paths = spec.module.selected_inputs(
            base,
            recorded_at=spec.recorded_at,
        )
        if selected != definition.get("curated_inputs"):
            raise ConstructionTimelineV11Error(
                f"open seed v{spec.version} selected inputs differ"
            )
        connection = spec.module._build_database(
            base,
            paths,
            temporary_root / f"open-seed-v{spec.version}.sqlite",
            recorded_at=spec.recorded_at,
        )
    except ConstructionTimelineV11Error:
        raise
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineV11Error(
            f"open seed v{spec.version} lifecycle rebuild failed"
        ) from error

    source_paths = _source_path_contract(spec)
    labels = _release_labels(spec)
    rows: list[dict[str, Any]] = []
    provenance: dict[str, tuple[str, str]] = {}
    found_contract: set[tuple[str, str, str, str]] = set()
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

    for raw_row in raw_rows:
        row = dict(raw_row)
        event = (
            str(row["entity_stable_key"]),
            str(row["status"]),
            str(row["observed_date"]),
            str(row["method"]),
        )
        if event not in spec.lifecycle_contract:
            continue
        label = labels.get(str(row["entity_id"]))
        if (
            label is None
            or label.get("stable_key") != row["entity_stable_key"]
            or label.get("entity_kind") != row["entity_kind"]
            or not label.get("name")
            or not label.get("country")
            or row["recorded_at"] != spec.recorded_at
        ):
            raise ConstructionTimelineV11Error(
                f"open seed v{spec.version} lifecycle label or clock differs"
            )
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        selected_row = {field: row[field] for field in OBSERVATION_FIELDS}
        observation_id = str(row["observation_id"])
        if observation_id in provenance:
            raise ConstructionTimelineV11Error("release lifecycle observation collides")
        rows.append(selected_row)
        provenance[observation_id] = (spec.release_id, source_paths[event])
        found_contract.add(event)
    if (
        found_contract != set(spec.lifecycle_contract)
        or len(rows) != spec.added_observations
        or len(provenance) != len(rows)
    ):
        raise ConstructionTimelineV11Error(
            f"open seed v{spec.version} lifecycle delta differs"
        )
    return rows, provenance


EVENT_CONTRACT_FIELDS = (
    "source_release_id",
    "source_input_path",
    "entity_stable_key",
    "observation_id",
    "observed_date",
    "status",
    "method",
    "evidence_id",
    "evidence_source_family",
    "evidence_retrieved_at",
    "evidence_content_hash",
    "recorded_at",
    "age_days_at_as_of",
    "freshness_class",
)


def _event_contract(
    rows: Iterable[Mapping[str, Any]],
    provenance: Mapping[str, tuple[str, str]],
) -> tuple[tuple[Any, ...], ...]:
    as_of = date.fromisoformat(AS_OF)
    result: list[tuple[Any, ...]] = []
    for row in rows:
        observation_id = str(row["observation_id"])
        release_id, source_path = provenance[observation_id]
        age = (as_of - date.fromisoformat(str(row["observed_date"]))).days
        result.append(
            (
                release_id,
                source_path,
                str(row["entity_stable_key"]),
                observation_id,
                str(row["observed_date"]),
                str(row["status"]),
                str(row["method"]),
                str(row["evidence_id"]),
                str(row["evidence_source_family"]),
                str(row["evidence_retrieved_at"]),
                str(row["evidence_content_hash"]),
                str(row["recorded_at"]),
                age,
                CODEC._freshness_class(age),
            )
        )
    return tuple(sorted(result, key=lambda item: (item[2], item[4], item[3])))


def _event_contract_sha256(contract: tuple[tuple[Any, ...], ...]) -> str:
    return _sha256(CODEC._canonical_json([list(row) for row in contract]))


def _event_documents(contract: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in contract:
        row = dict(zip(EVENT_CONTRACT_FIELDS, event, strict=True))
        row.update(
            {
                "current_construction_claim": False,
                "current_status_classification": "unknown",
                "latest_observation_persistence_assumed": False,
                "status_semantics": "last_observed",
            }
        )
        result.append(row)
    return result


def _reconstruct_observations() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[str, str]]
]:
    _validate_input_pins()
    predecessor = _predecessor_observations()
    predecessor_ids = {row["observation_id"] for row in predecessor}
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    additions: list[dict[str, Any]] = []
    provenance: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v11-db-", dir="/private/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        for spec in RELEASE_SPECS:
            rows, release_provenance = _release_additions(spec, temporary_root)
            additions.extend(rows)
            if provenance.keys() & release_provenance.keys():
                raise ConstructionTimelineV11Error(
                    "cross-release lifecycle observation collision"
                )
            provenance.update(release_provenance)

    addition_ids = {str(row["observation_id"]) for row in additions}
    addition_keys = {str(row["entity_stable_key"]) for row in additions}
    inherited_collisions = predecessor_keys & addition_keys
    if (
        len(additions) != ADDED_OBSERVATIONS
        or len(addition_ids) != ADDED_OBSERVATIONS
        or len(addition_keys) != ADDITION_EVENT_ENTITIES
        or len(addition_keys - predecessor_keys) != ADDED_TIMELINE_ENTITIES
        or inherited_collisions != {FIN04_KEY}
        or predecessor_ids & addition_ids
        or set(provenance) != addition_ids
    ):
        raise ConstructionTimelineV11Error("timeline v11 append boundary differs")
    additions.sort(
        key=lambda row: (
            str(row["entity_stable_key"]),
            str(row["observed_date"]),
            str(row["recorded_at"]),
            str(row["observation_id"]),
        )
    )
    digest = _event_contract_sha256(_event_contract(additions, provenance))
    if (
        ADDITION_EVENT_CONTRACT_SHA256 != "TO_FILL"
        and digest != ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 addition event contract differs"
        )
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
        raise ConstructionTimelineV11Error("timeline v11 observation inventory differs")
    current_by_id = {str(row["observation_id"]): row for row in combined}
    for row in predecessor:
        inherited = current_by_id[str(row["observation_id"])]
        if inherited != row or CODEC._csv_bytes([inherited]) != CODEC._csv_bytes([row]):
            raise ConstructionTimelineV11Error(
                "timeline v10 lifecycle observation bytes changed"
            )
    return combined, additions, provenance


def _timeline_rows(
    observations: list[dict[str, Any]], additions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines()
    predecessor_by_key = {str(row["entity_stable_key"]): row for row in predecessor}
    if (
        len(predecessor_by_key) != PREDECESSOR_TIMELINES
        or FIN04_KEY not in predecessor_by_key
    ):
        raise ConstructionTimelineV11Error("timeline v10 grouped-key inventory differs")

    grouped_additions = TIMELINE_CARRIER._timeline_rows(additions, as_of=AS_OF)
    addition_by_key = {str(row["entity_stable_key"]): row for row in grouped_additions}
    if (
        len(grouped_additions) != ADDITION_EVENT_ENTITIES
        or len(addition_by_key) != ADDITION_EVENT_ENTITIES
        or FIN04_KEY not in addition_by_key
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 grouped addition boundary differs"
        )

    fin04_observations = [
        row for row in observations if str(row["entity_stable_key"]) == FIN04_KEY
    ]
    replacement_rows = TIMELINE_CARRIER._timeline_rows(fin04_observations, as_of=AS_OF)
    if len(replacement_rows) != 1:
        raise ConstructionTimelineV11Error(
            "FIN04 grouped replacement inventory differs"
        )
    fin04 = replacement_rows[0]
    fin04_history = [
        (item["observed_date"], item["status"]) for item in fin04["observations"]
    ]
    if (
        fin04_history
        != [
            ("2026-07-20", "under_construction"),
            ("2026-07-21", "under_construction"),
        ]
        or not fin04["has_multiple_observations"]
        or fin04["has_status_change"]
        or fin04["current_status_classification"] != "unknown"
        or fin04["current_construction_claim"] is not False
        or fin04["latest_observation_persistence_assumed"] is not False
    ):
        raise ConstructionTimelineV11Error("FIN04 repeated-status history differs")

    wood_dale = addition_by_key.get(WOOD_DALE_KEY)
    beale = addition_by_key.get(BEALE_TULSA_KEY)
    if (
        not isinstance(wood_dale, Mapping)
        or [item["status"] for item in wood_dale["observations"]]
        != ["shell", "under_construction"]
        or wood_dale["has_status_change"] is not True
        or not isinstance(beale, Mapping)
        or [item["status"] for item in beale["observations"]]
        != ["under_construction", "under_construction"]
        or beale["has_status_change"] is not False
    ):
        raise ConstructionTimelineV11Error(
            "v11 Wood Dale or Beale multi-observation history differs"
        )

    new_keys = set(addition_by_key) - {FIN04_KEY}
    if set(predecessor_by_key) & new_keys:
        raise ConstructionTimelineV11Error(
            "timeline v11 new entity collides with timeline v10"
        )
    if len(new_keys) != ADDED_TIMELINE_ENTITIES:
        raise ConstructionTimelineV11Error("timeline v11 new entity count differs")

    rows = [
        *(row for row in predecessor if row["entity_stable_key"] != FIN04_KEY),
        *(addition_by_key[key] for key in sorted(new_keys)),
        fin04,
    ]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    if len(rows) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]:
        raise ConstructionTimelineV11Error("timeline v11 grouped inventory differs")

    current_by_key = {str(row["entity_stable_key"]): row for row in rows}
    for row in predecessor:
        key = str(row["entity_stable_key"])
        if key == FIN04_KEY:
            continue
        inherited = current_by_key.get(key)
        if inherited != row or CODEC._canonical_json_line(
            inherited
        ) != CODEC._canonical_json_line(row):
            raise ConstructionTimelineV11Error(
                "unaffected timeline v10 grouped row changed"
            )
    return rows


def _source_family_state(
    observations: list[dict[str, Any]],
) -> tuple[set[str], set[str], dict[str, dict[str, bool]]]:
    predecessor_coverage = _canonical_document(
        PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "timeline v10 coverage"
    )
    inherited_roles = predecessor_coverage.get("source_family_roles")
    if not isinstance(inherited_roles, Mapping) or len(inherited_roles) != 270:
        raise ConstructionTimelineV11Error("timeline v10 source-family lineage differs")
    row_linked = {str(row["evidence_source_family"]) for row in observations}
    lineage = set(inherited_roles) | row_linked
    if (
        len(row_linked) != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or len(lineage) != LINEAGE_AWARE_SOURCE_FAMILIES
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 source-family accounting differs"
        )
    roles: dict[str, dict[str, bool]] = {}
    for family in sorted(lineage):
        inherited = inherited_roles.get(family, {})
        roles[family] = {
            "identity_lineage": bool(
                isinstance(inherited, Mapping) and inherited.get("identity_lineage")
            ),
            "lifecycle_row_evidence": family in row_linked,
        }
    return row_linked, lineage, roles


def _coverage(
    observations: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    provenance: Mapping[str, tuple[str, str]],
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
    row_linked, lineage, roles = _source_family_state(observations)
    counts = {
        "entities_with_lifecycle_observations": len(timelines),
        "multi_observation_entities": len(multi),
        "raw_lifecycle_observations": len(observations),
        "repeated_status_multi_observation_entities": len(repeated),
        "single_observation_entities": len(single),
        "single_old_observation_entities": len(single_old),
        "source_families": len(lineage),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineV11Error(
            f"timeline v11 coverage counts differ: {counts}"
        )

    contract = _event_contract(additions, provenance)
    digest = _event_contract_sha256(contract)
    if (
        ADDITION_EVENT_CONTRACT_SHA256 != "TO_FILL"
        and digest != ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 coverage event contract differs"
        )
    events = _event_documents(contract)
    release_counts = dict(
        sorted(Counter(row["source_release_id"] for row in events).items())
    )
    if release_counts != RELEASE_ADDITION_COUNTS:
        raise ConstructionTimelineV11Error(
            "timeline v11 release event accounting differs"
        )

    by_key = {str(row["entity_stable_key"]): row for row in timelines}
    for key in STALE_CURRENT_UNKNOWN_KEYS:
        row = by_key.get(key)
        if (
            not isinstance(row, Mapping)
            or row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
        ):
            raise ConstructionTimelineV11Error(
                f"stale current-unknown timeline differs: {key}"
            )

    predecessor_coverage = _canonical_document(
        PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "timeline v10 coverage"
    )
    wood_dale_events = [
        row for row in events if row["entity_stable_key"] == WOOD_DALE_KEY
    ]
    if [row["status"] for row in wood_dale_events] != ["shell", "under_construction"]:
        raise ConstructionTimelineV11Error("Wood Dale transition contract differs")

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
        "inherited_v10_authoritative_status_transitions": predecessor_coverage[
            "v10_authoritative_status_transitions"
        ],
        "inherited_v10_operational_lifecycle_closures": predecessor_coverage[
            "v10_delta_operational_lifecycle_closures"
        ],
        "lifecycle_row_linked_source_family_count": len(row_linked),
        "lineage_aware_source_family_count": len(lineage),
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
        "open_seed_release_event_counts": release_counts,
        "open_seed_release_new_timeline_entity_counts": RELEASE_TIMELINE_ENTITY_COUNTS,
        "predecessor": {
            "definition_sha256": PREDECESSOR_DEFINITION_PIN[1],
            "manifest_sha256": PREDECESSOR_MANIFEST_PIN[1],
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
        "source_family_roles": roles,
        "stale_current_unknown_project_keys": sorted(STALE_CURRENT_UNKNOWN_KEYS),
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v11_addition_event_contract_sha256": digest,
        "v11_addition_events": events,
        "v11_addition_freshness_counts": dict(
            sorted(Counter(str(row["freshness_class"]) for row in events).items())
        ),
        "v11_authoritative_status_transitions": [
            {
                "closed_at": wood_dale_events[1]["observed_date"],
                "current_status_classification": "unknown",
                "entity_stable_key": WOOD_DALE_KEY,
                "from_observed_date": wood_dale_events[0]["observed_date"],
                "from_status": "shell",
                "raw_valid_to_date_rewritten": False,
                "to_status": "under_construction",
                "transition_semantics": "closed_by_later_authoritative_observation",
            }
        ],
        "v11_delta_inference_guardrails": INFERENCE_GUARDRAILS,
        "v11_delta_operational_lifecycle_closures": [],
        "v11_grouped_timeline_replacements": [
            {
                "current_status_classification": "unknown",
                "entity_stable_key": FIN04_KEY,
                "inherited_observations": 1,
                "new_observations": 1,
                "replacement_reason": "second_dated_observation",
                "repeated_status": "under_construction",
            }
        ],
        "v11_repeated_status_histories_added": [BEALE_TULSA_KEY, FIN04_KEY],
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v11\n\n"
        "This governed successor preserves all 571 accepted v10 lifecycle "
        "observation rows byte-for-byte and adds exactly 36 dated observations "
        "first accepted by open seeds v93 through v97. The result contains "
        f"{counts['raw_lifecycle_observations']} observations for "
        f"{counts['entities_with_lifecycle_observations']} source-scoped "
        "entities.\n\n"
        "Thirty-three entity timelines are new. FIN04 is the sole inherited "
        "grouped row replaced: its 2026-07-20 and 2026-07-21 "
        "under-construction observations remain separate raw facts and form a "
        "repeated-status history. CyrusOne Wood Dale retains its shell-to-"
        "under-construction transition; Beale Tulsa retains both repeated "
        "under-construction observations.\n\n"
        "Every status remains a dated last-observed fact. Current status is "
        "unknown for every entity, including Hanoi, Jakarta, and Oran. No "
        "latest-state persistence, coordinate or geometry change, capacity "
        "inference, identity merge, forecast conversion, satellite/CV "
        "promotion, or unique-site claim is made.\n"
    ).encode()


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
    _row_linked, lineage, _roles = _source_family_state(observations)
    predecessor_lines: dict[str, str] = {}
    predecessor_text = CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / ATTRIBUTION_FILENAME, "v10 attribution"
    ).decode("utf-8")
    for line in predecessor_text.splitlines():
        if line.startswith("- ") and " | " in line:
            predecessor_lines[line[2:].split(" | ", 1)[0]] = line
    lines = [
        "Derived only from hash-pinned timeline v10 and open seeds v93-v97.",
        "Every lifecycle row retains its accepted evidence identity and metadata.",
        "Source-family attribution inventory:",
    ]
    for family in sorted(lineage):
        if family not in by_family:
            inherited = predecessor_lines.get(family)
            if inherited is None:
                raise ConstructionTimelineV11Error(
                    "inherited attribution family missing"
                )
            lines.append(inherited)
            continue
        values = by_family[family]
        lines.append(
            f"- {family} | publishers: {'; '.join(sorted(values['publishers']))} "
            f"| licenses: {'; '.join(sorted(values['licenses']))} "
            f"| attribution: {'; '.join(sorted(values['attributions']))}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _input_manifest_documents() -> dict[str, Any]:
    return {
        "open_seed_inputs": [_release_checkpoint(spec) for spec in RELEASE_SPECS],
        "predecessor_input": {
            **_bundle_checkpoint(
                PREDECESSOR_DEFINITION,
                PREDECESSOR_BUNDLE,
                PREDECESSOR_DEFINITION_PIN,
                PREDECESSOR_MANIFEST_PIN,
                PREDECESSOR_TREE_SHA256,
            ),
            "core": {
                "bytes": PREDECESSOR_CORE_PIN[0],
                "file": PREDECESSOR_CORE.name,
                "sha256": PREDECESSOR_CORE_PIN[1],
            },
            "timeline_id": previous.TIMELINE_ID,
        },
    }


def _prepare_payloads(
    definition: _Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations, additions, provenance = _reconstruct_observations()
    timelines = _timeline_rows(observations, additions)
    coverage = _coverage(observations, additions, provenance, timelines, definition)
    payloads = {
        ATTRIBUTION_FILENAME: _attribution(observations),
        COVERAGE_FILENAME: CODEC._canonical_json(coverage),
        OBSERVATIONS_FILENAME: CODEC._csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: b"".join(
            CODEC._canonical_json_line(row) for row in timelines
        ),
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw),
            "file": DEFINITION.name,
            "sha256": _sha256(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition.generated_at,
        **_input_manifest_documents(),
        "promotion_contract": PROMOTION_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = CODEC._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _validate_payload_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    observations = CODEC._parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = CODEC._parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = CODEC._regular_bytes(
        directory / COVERAGE_FILENAME, COVERAGE_FILENAME
    )
    coverage = CODEC._json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != CODEC._canonical_json(coverage):
        raise ConstructionTimelineV11Error(
            "timeline v11 coverage is not canonical JSON"
        )
    if (
        len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]
        or len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineV11Error("timeline v11 row inventory differs")
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
        raise ConstructionTimelineV11Error("timeline v11 observation order differs")
    timeline_order = [(row["entity_stable_key"], row["entity_id"]) for row in timelines]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(
        timeline_order
    ):
        raise ConstructionTimelineV11Error("timeline v11 grouped order differs")

    flattened: list[str] = []
    multi = 0
    changing = 0
    repeated = 0
    single_old = 0
    for row in timelines:
        nested = row.get("observations")
        if (
            row.get("format") != TIMELINE_FORMAT
            or row.get("schema_version") != TIMELINE_SCHEMA_VERSION
            or row.get("current_status_classification") != "unknown"
            or row.get("current_construction_claim") is not False
            or row.get("latest_observation_persistence_assumed") is not False
            or not isinstance(nested, list)
            or row.get("observation_count") != len(nested)
        ):
            raise ConstructionTimelineV11Error("timeline v11 grouped guardrails differ")
        flattened.extend(str(item["observation_id"]) for item in nested)
        if row["has_multiple_observations"]:
            multi += 1
            if row["has_status_change"]:
                changing += 1
            else:
                repeated += 1
        elif row["single_old_observation_current_unknown"]:
            single_old += 1
    if sorted(flattened) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineV11Error(
            "flat and grouped lifecycle inventories differ"
        )
    if (
        multi != EXPECTED_COUNTS["multi_observation_entities"]
        or changing != EXPECTED_COUNTS["status_changing_multi_observation_entities"]
        or repeated != EXPECTED_COUNTS["repeated_status_multi_observation_entities"]
        or single_old != EXPECTED_COUNTS["single_old_observation_entities"]
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 grouped classification counts differ"
        )
    if (
        coverage.get("format") != COVERAGE_FORMAT
        or coverage.get("schema_version") != SCHEMA_VERSION
        or coverage.get("scope") != SCOPE
        or coverage.get("counts") != EXPECTED_COUNTS
        or coverage.get("delta") != DELTA_CONTRACT
        or manifest.get("counts") != EXPECTED_COUNTS
        or manifest.get("delta") != DELTA_CONTRACT
        or manifest.get("promotion_contract") != PROMOTION_CONTRACT
    ):
        raise ConstructionTimelineV11Error("timeline v11 coverage or manifest differs")

    predecessor_observations = _predecessor_observations()
    predecessor_ids = {row["observation_id"] for row in predecessor_observations}
    current_by_id = {row["observation_id"]: row for row in observations}
    for row in predecessor_observations:
        inherited = current_by_id.get(row["observation_id"])
        if inherited != row or CODEC._csv_bytes([inherited]) != CODEC._csv_bytes([row]):
            raise ConstructionTimelineV11Error(
                "inherited v10 observation bytes changed"
            )

    predecessor_timelines = _predecessor_timelines()
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    for row in predecessor_timelines:
        key = row["entity_stable_key"]
        if key == FIN04_KEY:
            continue
        inherited = current_by_key.get(key)
        if inherited != row or CODEC._canonical_json_line(
            inherited
        ) != CODEC._canonical_json_line(row):
            raise ConstructionTimelineV11Error(
                "unaffected inherited v10 timeline changed"
            )

    additions = [
        row for row in observations if row["observation_id"] not in predecessor_ids
    ]
    events = coverage.get("v11_addition_events")
    if not isinstance(events, list):
        raise ConstructionTimelineV11Error("timeline v11 event contract is missing")
    event_by_id = {str(row["observation_id"]): row for row in events}
    provenance = {
        observation_id: (
            str(row["source_release_id"]),
            str(row["source_input_path"]),
        )
        for observation_id, row in event_by_id.items()
    }
    contract = _event_contract(additions, provenance)
    digest = _event_contract_sha256(contract)
    if (
        len(additions) != ADDED_OBSERVATIONS
        or len(event_by_id) != ADDED_OBSERVATIONS
        or _event_documents(contract) != events
        or coverage.get("v11_addition_event_contract_sha256") != digest
        or (
            ADDITION_EVENT_CONTRACT_SHA256 != "TO_FILL"
            and digest != ADDITION_EVENT_CONTRACT_SHA256
        )
        or coverage.get("open_seed_release_event_counts") != RELEASE_ADDITION_COUNTS
    ):
        raise ConstructionTimelineV11Error(
            "published timeline v11 event contract differs"
        )

    fin04 = current_by_key.get(FIN04_KEY)
    wood_dale = current_by_key.get(WOOD_DALE_KEY)
    beale = current_by_key.get(BEALE_TULSA_KEY)
    if (
        not isinstance(fin04, Mapping)
        or [item["status"] for item in fin04["observations"]]
        != ["under_construction", "under_construction"]
        or fin04["has_status_change"] is not False
        or not isinstance(wood_dale, Mapping)
        or [item["status"] for item in wood_dale["observations"]]
        != ["shell", "under_construction"]
        or not isinstance(beale, Mapping)
        or [item["status"] for item in beale["observations"]]
        != ["under_construction", "under_construction"]
        or coverage.get("v11_delta_operational_lifecycle_closures") != []
        or coverage.get("v11_delta_inference_guardrails") != INFERENCE_GUARDRAILS
        or coverage.get("current_status_classification_counts")
        != {"unknown": EXPECTED_COUNTS["entities_with_lifecycle_observations"]}
        or coverage.get("lifecycle_row_linked_source_family_count")
        != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or coverage.get("lineage_aware_source_family_count")
        != LINEAGE_AWARE_SOURCE_FAMILIES
        or coverage.get("stale_current_unknown_project_keys")
        != sorted(STALE_CURRENT_UNKNOWN_KEYS)
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 history or inference boundary differs"
        )


def _bundle_descendants(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def _validate_publication_times(
    definition_path: Path,
    bundle_path: Path,
    *,
    generated_at: str,
    validation_wall_clock: datetime,
    require_live: bool,
) -> None:
    generated = _parse_utc(generated_at, label="timeline v11 generated_at")
    if validation_wall_clock.tzinfo is None:
        raise ConstructionTimelineV11Error(
            "validation wall clock must include a timezone"
        )
    wall = validation_wall_clock.astimezone(UTC)
    if require_live and generated > wall:
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at exceeds validation wall clock"
        )
    for artifact in (
        definition_path,
        bundle_path,
        *_bundle_descendants(bundle_path),
    ):
        metadata = artifact.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise ConstructionTimelineV11Error(
                f"timeline v11 artifact post-dates generated_at: {artifact.name}"
            )
        if require_live and metadata.st_ctime + 0.000_001 < generated.timestamp():
            raise ConstructionTimelineV11Error(
                f"timeline v11 artifact ctime predates generated_at: {artifact.name}"
            )


def _validate_two_replays(
    definition: _Definition,
    directory: Path,
    *,
    replay_count: int = 2,
) -> str:
    if replay_count != 2:
        raise ConstructionTimelineV11Error(
            "timeline v11 requires exactly two offline replays"
        )
    staged = {path.name: path.read_bytes() for path in directory.iterdir()}
    digests: list[str] = []
    for _replay in range(replay_count):
        payloads, _manifest = _prepare_payloads(definition)
        if payloads != staged:
            raise ConstructionTimelineV11Error(
                "timeline v11 offline replay differs from staged bundle"
            )
        digests.append(_sha256(payloads[MANIFEST_FILENAME]))
    if len(set(digests)) != 1:
        raise ConstructionTimelineV11Error("timeline v11 replay digests differ")
    return digests[0]


def validate_construction_timeline_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path = DEFINITION,
    verify_inputs: bool = False,
    require_frozen: bool = True,
    verify_publication_times: bool = True,
    require_live: bool = True,
    validation_wall_clock: datetime | None = None,
    replay_count: int = 2,
    parent_bindings: ParentBindings | None = None,
) -> dict[str, Any]:
    """Validate a closed v11 bundle and its complete canonical lineage."""

    if replay_count != 2:
        raise ConstructionTimelineV11Error(
            "timeline v11 requires exactly two offline replays"
        )
    if parent_bindings is not None:
        _assert_parent_bindings(parent_bindings, label="before validation")
    wall = validation_wall_clock or datetime.now(UTC)
    definition = _load_definition(
        definition_path,
        validation_wall_clock=wall,
        allow_future=not require_live,
    )
    if (
        require_frozen
        and stat.S_IMODE(definition.path.stat().st_mode) != FROZEN_FILE_MODE
    ):
        raise ConstructionTimelineV11Error("timeline v11 definition must be mode 0444")
    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineV11Error(
            "timeline v11 bundle must be an ordinary directory"
        )
    if (
        require_frozen
        and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 bundle directory must be mode 0555"
        )
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineV11Error("timeline v11 bundle inventory differs")
    for entry in entries:
        CODEC._regular_bytes(entry, f"timeline v11 bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineV11Error(
                "timeline v11 bundle files must be mode 0444"
            )

    manifest_raw = CODEC._regular_bytes(
        directory / MANIFEST_FILENAME, MANIFEST_FILENAME
    )
    manifest = CODEC._json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != CODEC._canonical_json(manifest):
        raise ConstructionTimelineV11Error("timeline v11 manifest is not canonical")
    sidecar = CODEC._regular_bytes(
        directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME
    )
    expected_sidecar = (f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n").encode(
        "ascii"
    )
    if sidecar != expected_sidecar:
        raise ConstructionTimelineV11Error("timeline v11 manifest sidecar differs")
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
        raise ConstructionTimelineV11Error("timeline v11 manifest contract differs")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    files = manifest.get("files")
    if not isinstance(files, Mapping) or set(files) != payload_names:
        raise ConstructionTimelineV11Error(
            "timeline v11 manifest file inventory differs"
        )
    for name in payload_names:
        raw = CODEC._regular_bytes(directory / name, name)
        if files[name] != {"bytes": len(raw), "sha256": _sha256(raw)}:
            raise ConstructionTimelineV11Error(
                f"timeline v11 file checkpoint differs: {name}"
            )
    _validate_payload_semantics(directory, manifest)
    if manifest.get("definition") != {
        "bytes": len(definition.raw),
        "file": DEFINITION.name,
        "sha256": _sha256(definition.raw),
    }:
        raise ConstructionTimelineV11Error("timeline v11 definition checkpoint differs")
    expected_inputs = _input_manifest_documents()
    if any(manifest.get(key) != value for key, value in expected_inputs.items()):
        raise ConstructionTimelineV11Error("timeline v11 full input manifest differs")
    _validate_input_pins()
    if verify_publication_times:
        _validate_publication_times(
            definition.path,
            directory,
            generated_at=definition.generated_at,
            validation_wall_clock=wall,
            require_live=require_live,
        )
    if verify_inputs:
        _validate_two_replays(definition, directory, replay_count=replay_count)
    if parent_bindings is not None:
        _assert_parent_bindings(parent_bindings, label="after validation")
    return manifest


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    if path.is_symlink():
        raise ConstructionTimelineV11Error(
            f"symlinked timeline v11 publication member: {path}"
        )
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        kind = "directory" if directory else "file"
        raise ConstructionTimelineV11Error(
            f"timeline v11 member is not a {kind}: {path}"
        )
    return metadata.st_dev, metadata.st_ino


def _fstat_identity_with_retry(
    descriptor: int,
    *,
    expected_kind: str,
    label: str,
    expected_mode: int | None = None,
    attempts: int = 2,
) -> tuple[int, int, str]:
    if attempts < 1:
        raise ValueError("identity attempts must be positive")
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            metadata = os.fstat(descriptor)
        except OSError as error:
            last_error = error
            continue
        actual_kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if actual_kind != expected_kind:
            raise ConstructionTimelineV11Error(
                f"{label} is not an owned {expected_kind}; retained fail-closed"
            )
        if (
            expected_mode is not None
            and stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise ConstructionTimelineV11Error(
                f"{label} mode differs; retained fail-closed"
            )
        return metadata.st_dev, metadata.st_ino, actual_kind
    raise ConstructionTimelineV11Error(
        f"{label} identity unavailable after {attempts} attempts; retained fail-closed"
    ) from last_error


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        return _identity(path, directory=directory) == identity
    except (FileNotFoundError, ConstructionTimelineV11Error):
        return False


def _require_component(name: str, *, label: str) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise ConstructionTimelineV11Error(f"{label} must be a single path component")


def _stat_at(parent_descriptor: int, name: str) -> os.stat_result | None:
    _require_component(name, label="timeline v11 bound member")
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ConstructionTimelineV11Error(
            f"timeline v11 bound member presence is unavailable: {name}"
        ) from error


def _identity_at(
    parent_descriptor: int, name: str, *, directory: bool
) -> tuple[int, int]:
    metadata = _stat_at(parent_descriptor, name)
    if metadata is None:
        raise FileNotFoundError(name)
    expected = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        kind = "directory" if directory else "file"
        raise ConstructionTimelineV11Error(
            f"timeline v11 bound member is not a {kind}: {name}"
        )
    return metadata.st_dev, metadata.st_ino


def _has_identity_at(
    parent_descriptor: int,
    name: str,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> bool:
    try:
        return _identity_at(parent_descriptor, name, directory=directory) == identity
    except (FileNotFoundError, ConstructionTimelineV11Error):
        return False


def _parent_paths() -> dict[str, Path]:
    return {
        "definition": DEFINITION.parent,
        "bundle": BUNDLE.parent,
        "lock": PUBLICATION_LOCK.parent,
    }


def _assert_parent_descriptors(bindings: ParentBindings, *, label: str) -> None:
    expected_paths = _parent_paths()
    if set(bindings) != set(expected_paths):
        raise ConstructionTimelineV11Error(
            f"{label} timeline v11 parent-binding schema differs"
        )
    for name, expected_path in expected_paths.items():
        bound_path, bound_identity, descriptor = bindings[name]
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            label=f"{label} timeline v11 {name} parent descriptor",
        )
        if bound_path != expected_path or details[:2] != bound_identity:
            raise ConstructionTimelineV11Error(
                f"{label} timeline v11 {name} parent descriptor changed"
            )
    if bindings["definition"][1][0] != bindings["bundle"][1][0]:
        raise ConstructionTimelineV11Error(
            f"{label} timeline v11 output parents cross filesystems"
        )


def _binding_for_parent(
    bindings: ParentBindings, parent: Path
) -> tuple[Path, tuple[int, int], int]:
    matches = [binding for binding in bindings.values() if binding[0] == parent]
    if not matches:
        raise ConstructionTimelineV11Error(
            f"timeline v11 path is outside a bound output parent: {parent}"
        )
    if any(binding[1] != matches[0][1] for binding in matches[1:]):
        raise ConstructionTimelineV11Error(
            f"timeline v11 duplicate parent bindings disagree: {parent}"
        )
    return matches[0]


def _bound_identity(
    bindings: ParentBindings, path: Path, identity: tuple[int, int], *, directory: bool
) -> bool:
    _bound_path, _parent_identity, descriptor = _binding_for_parent(
        bindings, path.parent
    )
    return _has_identity_at(descriptor, path.name, identity, directory=directory)


def _bound_present(bindings: ParentBindings, path: Path) -> bool:
    _bound_path, _parent_identity, descriptor = _binding_for_parent(
        bindings, path.parent
    )
    return _stat_at(descriptor, path.name) is not None


def _capture_parent_bindings() -> dict[str, tuple[Path, tuple[int, int], int]]:
    bindings: dict[str, tuple[Path, tuple[int, int], int]] = {}
    try:
        for label, parent in _parent_paths().items():
            descriptor = os.open(
                parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
            )
            try:
                details = _fstat_identity_with_retry(
                    descriptor,
                    expected_kind="directory",
                    label=f"timeline v11 {label} parent",
                )
                identity = details[:2]
                if not _has_identity(parent, identity, directory=True):
                    raise ConstructionTimelineV11Error(
                        f"timeline v11 {label} parent identity changed at binding"
                    )
            except _OPERATION_FAILURES:
                os.close(descriptor)
                raise
            bindings[label] = (parent, identity, descriptor)
        if bindings["definition"][1][0] != bindings["bundle"][1][0]:
            raise ConstructionTimelineV11Error(
                "timeline v11 definition and bundle parents cross filesystems"
            )
        return bindings
    except _OPERATION_FAILURES as error:
        close_errors: list[OSError] = []
        for _path, _identity_value, descriptor in bindings.values():
            try:
                os.close(descriptor)
            except OSError as close_error:
                close_errors.append(close_error)
        for close_error in close_errors:
            error.add_note(
                f"timeline v11 parent descriptor close failed: {close_error}"
            )
        raise


def _assert_parent_bindings(bindings: ParentBindings, *, label: str) -> None:
    _assert_parent_descriptors(bindings, label=label)
    expected_paths = _parent_paths()
    for name, current_path in expected_paths.items():
        _bound_path, bound_identity, _descriptor = bindings[name]
        if not _has_identity(current_path, bound_identity, directory=True):
            raise ConstructionTimelineV11Error(
                f"{label} timeline v11 {name} parent identity changed"
            )


def _close_parent_bindings(
    bindings: ParentBindings, *, active_error: BaseException | None
) -> None:
    errors: list[OSError] = []
    for _path, _identity_value, descriptor in bindings.values():
        try:
            os.close(descriptor)
        except OSError as error:
            errors.append(error)
    if not errors:
        return
    if active_error is not None:
        for error in errors:
            active_error.add_note(
                f"timeline v11 parent descriptor close failed: {error}"
            )
        return
    primary = ConstructionTimelineV11Error(
        f"timeline v11 parent descriptor close failed: {errors[0]}"
    )
    for error in errors[1:]:
        primary.add_note(f"additional parent descriptor close failed: {error}")
    raise primary


@contextmanager
def _bound_output_parents() -> Iterator[ParentBindings]:
    bindings = _capture_parent_bindings()
    try:
        _assert_parent_bindings(bindings, label="initial")
        yield bindings
    finally:
        _close_parent_bindings(bindings, active_error=sys.exception())


def _tree_identities(root: Path) -> dict[str, tuple[str, int, int]]:
    identities: dict[str, tuple[str, int, int]] = {}
    for path in (root, *_bundle_descendants(root)):
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ConstructionTimelineV11Error(
                f"timeline v11 stage contains symlink: {relative}"
            )
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
        else:
            raise ConstructionTimelineV11Error(
                f"timeline v11 stage contains special member: {relative}"
            )
        identities[relative] = (kind, metadata.st_dev, metadata.st_ino)
    return identities


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[str, int, int]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise ConstructionTimelineV11Error(
            "timeline v11 recursive bundle identity changed"
        )


def _tree_identities_at(
    parent_descriptor: int, root_name: str
) -> dict[str, tuple[str, int, int]]:
    _require_component(root_name, label="timeline v11 bound bundle root")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        root_descriptor = os.open(root_name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise ConstructionTimelineV11Error(
            f"timeline v11 bound bundle root cannot be opened: {root_name}"
        ) from error
    identities: dict[str, tuple[str, int, int]] = {}

    def visit(descriptor: int, prefix: str) -> None:
        try:
            names = sorted(os.listdir(descriptor))
        except OSError as error:
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle inventory is unavailable"
            ) from error
        for name in names:
            _require_component(name, label="timeline v11 bound bundle member")
            metadata = _stat_at(descriptor, name)
            if metadata is None:
                raise ConstructionTimelineV11Error(
                    f"timeline v11 bound bundle member vanished: {name}"
                )
            relative = f"{prefix}/{name}" if prefix else name
            if stat.S_ISREG(metadata.st_mode):
                identities[relative] = ("file", metadata.st_dev, metadata.st_ino)
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                raise ConstructionTimelineV11Error(
                    f"timeline v11 bound bundle has special member: {relative}"
                )
            child_descriptor = os.open(name, flags, dir_fd=descriptor)
            try:
                details = _fstat_identity_with_retry(
                    child_descriptor,
                    expected_kind="directory",
                    label=f"timeline v11 bound bundle directory {relative}",
                )
                if details[:2] != (metadata.st_dev, metadata.st_ino):
                    raise ConstructionTimelineV11Error(
                        f"timeline v11 bound bundle directory changed: {relative}"
                    )
                identities[relative] = ("directory", *details[:2])
                visit(child_descriptor, relative)
            finally:
                os.close(child_descriptor)

    try:
        root_details = _fstat_identity_with_retry(
            root_descriptor,
            expected_kind="directory",
            label="timeline v11 bound bundle root",
        )
        bound_root = _stat_at(parent_descriptor, root_name)
        if (
            bound_root is None
            or not stat.S_ISDIR(bound_root.st_mode)
            or root_details[:2] != (bound_root.st_dev, bound_root.st_ino)
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle root identity changed"
            )
        identities["."] = ("directory", *root_details[:2])
        visit(root_descriptor, "")
    finally:
        os.close(root_descriptor)
    return identities


def _assert_bound_tree_identities(
    bindings: ParentBindings,
    root: Path,
    expected: Mapping[str, tuple[str, int, int]],
) -> None:
    _bound_path, _parent_identity, descriptor = _binding_for_parent(
        bindings, root.parent
    )
    if _tree_identities_at(descriptor, root.name) != dict(expected):
        raise ConstructionTimelineV11Error(
            "timeline v11 recursive bound bundle identity changed"
        )


def _fsync(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if path.is_dir():
        flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_definition_stage(
    payload: bytes, *, parent_bindings: ParentBindings
) -> tuple[Path, tuple[int, int]]:
    _assert_parent_bindings(parent_bindings, label="before definition-stage creation")
    _bound_path, _parent_identity, parent_descriptor = _binding_for_parent(
        parent_bindings, DEFINITION.parent
    )
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = -1
    stage_name: str | None = None
    for _attempt in range(100):
        candidate = f".{DEFINITION.name}.private-stage-{secrets.token_hex(8)}.json"
        try:
            descriptor = os.open(
                candidate,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError:
            continue
        stage_name = candidate
        break
    if descriptor < 0 or stage_name is None:
        raise ConstructionTimelineV11Error(
            "timeline v11 could not allocate a unique bound definition stage"
        )
    stage = DEFINITION.parent / stage_name
    identity: tuple[int, int] | None = None
    try:
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="timeline v11 definition stage",
        )
        identity = details[:2]
        if not _has_identity_at(
            parent_descriptor,
            stage_name,
            identity,
            directory=False,
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound definition stage differs from its descriptor; "
                "retained fail-closed"
            )
        if os.write(descriptor, payload) != len(payload):
            raise ConstructionTimelineV11Error(
                "short timeline v11 definition-stage write"
            )
        os.fsync(descriptor)
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="timeline v11 written definition stage",
        )
        if details[:2] != identity or not _has_identity_at(
            parent_descriptor,
            stage_name,
            identity,
            directory=False,
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound definition stage identity changed after write"
            )
        os.fsync(parent_descriptor)
        _assert_parent_bindings(
            parent_bindings, label="after definition-stage creation"
        )
        return stage, identity
    except _OPERATION_FAILURES as error:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        if identity is not None and _bound_identity(
            parent_bindings,
            stage,
            identity,
            directory=False,
        ):
            try:
                _discard_definition_stage_bound(stage, identity, parent_bindings)
            except _OPERATION_FAILURES as cleanup_error:
                error.add_note(
                    f"timeline v11 definition stage cleanup failed: {cleanup_error}"
                )
        else:
            error.add_note(
                f"unknown timeline v11 definition stage retained fail-closed: {stage}"
            )
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _write_new_stage_file(
    directory_descriptor: int,
    name: str,
    payload: bytes,
    *,
    identities: dict[str, tuple[str, int, int]],
    tracker_key: str,
) -> None:
    descriptor = os.open(
        name,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_descriptor,
    )
    try:
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label=f"timeline v11 bundle member {tracker_key}",
        )
        identity = details[:2]
        identities[tracker_key] = ("file", *identity)
        if not _has_identity_at(
            directory_descriptor,
            name,
            identity,
            directory=False,
        ):
            raise ConstructionTimelineV11Error(
                f"timeline v11 bound bundle member {tracker_key} was substituted; "
                "retained fail-closed"
            )
        if os.write(descriptor, payload) != len(payload):
            raise ConstructionTimelineV11Error(
                f"short timeline v11 bundle-member write: {tracker_key}"
            )
        os.fsync(descriptor)
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label=f"timeline v11 written bundle member {tracker_key}",
        )
        if details[:2] != identity or not _has_identity_at(
            directory_descriptor,
            name,
            identity,
            directory=False,
        ):
            raise ConstructionTimelineV11Error(
                f"timeline v11 bound bundle member {tracker_key} identity changed"
            )
    finally:
        os.close(descriptor)


def _write_bundle_stage(
    payloads: Mapping[str, bytes],
    *,
    parent_bindings: ParentBindings,
) -> tuple[Path, dict[str, tuple[str, int, int]]]:
    _assert_parent_bindings(parent_bindings, label="before bundle-stage creation")
    _bound_path, _parent_identity, parent_descriptor = _binding_for_parent(
        parent_bindings, BUNDLE.parent
    )
    stage_name: str | None = None
    for _attempt in range(100):
        candidate = f".{BUNDLE.name}.private-stage-{secrets.token_hex(8)}"
        try:
            os.mkdir(candidate, 0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        stage_name = candidate
        break
    if stage_name is None:
        raise ConstructionTimelineV11Error(
            "timeline v11 could not allocate a unique bound bundle stage"
        )
    stage = BUNDLE.parent / stage_name
    descriptor = -1
    root_identity: tuple[int, int] | None = None
    identities: dict[str, tuple[str, int, int]] = {}
    try:
        descriptor = os.open(
            stage_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            expected_mode=0o700,
            label="timeline v11 bundle stage root",
        )
        root_identity = details[:2]
        identities["."] = ("directory", *root_identity)
        if not _has_identity_at(
            parent_descriptor,
            stage_name,
            root_identity,
            directory=True,
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle stage differs from its descriptor; "
                "retained fail-closed"
            )
        os.fsync(parent_descriptor)
        _assert_parent_bindings(
            parent_bindings, label="after bundle-stage root creation"
        )
        for name, raw in payloads.items():
            if Path(name).name != name or name in {"", ".", ".."}:
                raise ConstructionTimelineV11Error(
                    f"unsafe timeline v11 bundle member name: {name!r}"
                )
            _write_new_stage_file(
                descriptor,
                name,
                raw,
                identities=identities,
                tracker_key=name,
            )
            _assert_parent_bindings(
                parent_bindings,
                label=f"after bundle-stage member creation {name}",
            )
        os.fsync(descriptor)
        if _tree_identities_at(parent_descriptor, stage_name) != identities:
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle member identities differ"
            )
        _assert_parent_bindings(parent_bindings, label="after bundle-stage creation")
        return stage, identities
    except _OPERATION_FAILURES as error:
        if descriptor >= 0:
            os.close(descriptor)
            descriptor = -1
        can_cleanup = root_identity is not None and _bound_identity(
            parent_bindings,
            stage,
            root_identity,
            directory=True,
        )
        if can_cleanup:
            try:
                can_cleanup = (
                    _tree_identities_at(parent_descriptor, stage_name) == identities
                )
            except (OSError, ConstructionTimelineV11Error):
                can_cleanup = False
        if can_cleanup:
            try:
                _discard_bundle_stage_bound(stage, identities, parent_bindings)
            except _OPERATION_FAILURES as cleanup_error:
                error.add_note(
                    f"timeline v11 bundle stage cleanup failed: {cleanup_error}"
                )
        else:
            error.add_note(
                f"unknown timeline v11 bundle stage retained fail-closed: {stage}"
            )
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _freeze(definition: Path, bundle: Path) -> None:
    definition.chmod(FROZEN_FILE_MODE)
    _fsync(definition)
    descendants = _bundle_descendants(bundle)
    for path in descendants:
        if path.is_file():
            path.chmod(FROZEN_FILE_MODE)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(FROZEN_DIRECTORY_MODE)
        _fsync(path)
    bundle.chmod(FROZEN_DIRECTORY_MODE)
    _fsync(bundle)


def _refresh_publication_ctimes(definition: Path, bundle: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(FROZEN_FILE_MODE)
    _fsync(definition)
    descendants = _bundle_descendants(bundle)
    for path in descendants:
        if path.is_file():
            path.chmod(0o400)
            path.chmod(FROZEN_FILE_MODE)
            _fsync(path)
    for path in sorted(
        (path for path in descendants if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o500)
        path.chmod(FROZEN_DIRECTORY_MODE)
        _fsync(path)
    bundle.chmod(0o500)
    bundle.chmod(FROZEN_DIRECTORY_MODE)
    _fsync(bundle)


def _discard_definition_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not _has_identity(path, identity, directory=False):
        raise ConstructionTimelineV11Error(
            "refusing substituted timeline v11 definition cleanup"
        )
    path.chmod(0o600)
    if not _has_identity(path, identity, directory=False):
        raise ConstructionTimelineV11Error(
            "refusing rehomed timeline v11 definition cleanup"
        )
    path.unlink()


def _discard_bundle_stage(
    root: Path, identities: Mapping[str, tuple[str, int, int]]
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_tree_identities(root, identities)
    root.chmod(0o700)
    for path in _bundle_descendants(root):
        path.chmod(0o700 if path.is_dir() else 0o600)
    _assert_tree_identities(root, identities)
    shutil.rmtree(root)


def _discard_definition_stage_bound(
    path: Path, identity: tuple[int, int], bindings: ParentBindings
) -> None:
    """Delete only the owned file entry in its originally bound parent."""

    _bound_parent, _parent_identity, parent_descriptor = _binding_for_parent(
        bindings, path.parent
    )
    metadata = _stat_at(parent_descriptor, path.name)
    if metadata is None:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (
            metadata.st_dev,
            metadata.st_ino,
        )
        != identity
    ):
        raise ConstructionTimelineV11Error(
            "refusing substituted bound timeline v11 definition cleanup"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
    try:
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            label="timeline v11 bound definition cleanup descriptor",
        )
        if details[:2] != identity:
            raise ConstructionTimelineV11Error(
                "refusing changed bound timeline v11 definition cleanup"
            )
        os.fchmod(descriptor, 0o600)
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="timeline v11 thawed bound definition cleanup descriptor",
        )
        if details[:2] != identity or not _has_identity_at(
            parent_descriptor, path.name, identity, directory=False
        ):
            raise ConstructionTimelineV11Error(
                "refusing rehomed bound timeline v11 definition cleanup"
            )
        os.unlink(path.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        if _stat_at(parent_descriptor, path.name) is not None:
            raise ConstructionTimelineV11Error(
                "bound timeline v11 definition cleanup did not remove its entry"
            )
    finally:
        os.close(descriptor)


def _expected_directory_children(
    expected: Mapping[str, tuple[str, int, int]], prefix: str
) -> dict[str, tuple[str, int, int]]:
    marker = f"{prefix}/" if prefix else ""
    children: dict[str, tuple[str, int, int]] = {}
    for relative, identity in expected.items():
        if relative == "." or (prefix and not relative.startswith(marker)):
            continue
        remainder = relative[len(marker) :] if prefix else relative
        if remainder and "/" not in remainder:
            children[remainder] = identity
    return children


def _discard_bound_directory_contents(
    descriptor: int,
    *,
    prefix: str,
    expected: Mapping[str, tuple[str, int, int]],
) -> None:
    expected_children = _expected_directory_children(expected, prefix)
    try:
        actual_names = set(os.listdir(descriptor))
    except OSError as error:
        raise ConstructionTimelineV11Error(
            "timeline v11 bound cleanup inventory is unavailable"
        ) from error
    if actual_names != set(expected_children):
        raise ConstructionTimelineV11Error(
            "refusing changed timeline v11 bound bundle cleanup inventory"
        )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    directory_flags = file_flags | getattr(os, "O_DIRECTORY", 0)
    for name in sorted(actual_names):
        kind, expected_device, expected_inode = expected_children[name]
        expected_identity = expected_device, expected_inode
        relative = f"{prefix}/{name}" if prefix else name
        metadata = _stat_at(descriptor, name)
        if metadata is None or (metadata.st_dev, metadata.st_ino) != expected_identity:
            raise ConstructionTimelineV11Error(
                f"refusing substituted timeline v11 bound cleanup member: {relative}"
            )
        if kind == "file":
            member_descriptor = os.open(name, file_flags, dir_fd=descriptor)
            try:
                details = _fstat_identity_with_retry(
                    member_descriptor,
                    expected_kind="file",
                    label=f"timeline v11 bound cleanup member {relative}",
                )
                if details[:2] != expected_identity:
                    raise ConstructionTimelineV11Error(
                        f"timeline v11 bound cleanup member changed: {relative}"
                    )
                os.fchmod(member_descriptor, 0o600)
                details = _fstat_identity_with_retry(
                    member_descriptor,
                    expected_kind="file",
                    expected_mode=0o600,
                    label=f"timeline v11 thawed bound cleanup member {relative}",
                )
                if details[:2] != expected_identity or not _has_identity_at(
                    descriptor, name, expected_identity, directory=False
                ):
                    raise ConstructionTimelineV11Error(
                        f"timeline v11 bound cleanup member was rehomed: {relative}"
                    )
                os.unlink(name, dir_fd=descriptor)
                if _stat_at(descriptor, name) is not None:
                    raise ConstructionTimelineV11Error(
                        f"timeline v11 bound cleanup member persisted: {relative}"
                    )
            finally:
                os.close(member_descriptor)
            continue
        if kind != "directory":
            raise ConstructionTimelineV11Error(
                f"timeline v11 bound cleanup member kind differs: {relative}"
            )
        child_descriptor = os.open(name, directory_flags, dir_fd=descriptor)
        try:
            details = _fstat_identity_with_retry(
                child_descriptor,
                expected_kind="directory",
                label=f"timeline v11 bound cleanup directory {relative}",
            )
            if details[:2] != expected_identity:
                raise ConstructionTimelineV11Error(
                    f"timeline v11 bound cleanup directory changed: {relative}"
                )
            os.fchmod(child_descriptor, 0o700)
            _discard_bound_directory_contents(
                child_descriptor, prefix=relative, expected=expected
            )
            if not _has_identity_at(
                descriptor, name, expected_identity, directory=True
            ):
                raise ConstructionTimelineV11Error(
                    f"timeline v11 bound cleanup directory was rehomed: {relative}"
                )
            os.rmdir(name, dir_fd=descriptor)
            if _stat_at(descriptor, name) is not None:
                raise ConstructionTimelineV11Error(
                    f"timeline v11 bound cleanup directory persisted: {relative}"
                )
        finally:
            os.close(child_descriptor)


def _discard_bundle_stage_bound(
    root: Path,
    identities: Mapping[str, tuple[str, int, int]],
    bindings: ParentBindings,
) -> None:
    """Recursively delete only the tracked tree in its bound parent."""

    _bound_parent, _parent_identity, parent_descriptor = _binding_for_parent(
        bindings, root.parent
    )
    metadata = _stat_at(parent_descriptor, root.name)
    if metadata is None:
        return
    root_expected = identities.get(".")
    if root_expected is None or root_expected[0] != "directory":
        raise ConstructionTimelineV11Error(
            "timeline v11 bound bundle cleanup root contract differs"
        )
    root_identity = root_expected[1], root_expected[2]
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (
            metadata.st_dev,
            metadata.st_ino,
        )
        != root_identity
    ):
        raise ConstructionTimelineV11Error(
            "refusing substituted bound timeline v11 bundle cleanup"
        )
    if _tree_identities_at(parent_descriptor, root.name) != dict(identities):
        raise ConstructionTimelineV11Error(
            "refusing changed bound timeline v11 bundle cleanup tree"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(root.name, flags, dir_fd=parent_descriptor)
    try:
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            label="timeline v11 bound bundle cleanup root",
        )
        if details[:2] != root_identity:
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle cleanup root changed"
            )
        os.fchmod(descriptor, 0o700)
        _discard_bound_directory_contents(descriptor, prefix="", expected=identities)
        if not _has_identity_at(
            parent_descriptor, root.name, root_identity, directory=True
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle cleanup root was rehomed"
            )
        os.rmdir(root.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        if _stat_at(parent_descriptor, root.name) is not None:
            raise ConstructionTimelineV11Error(
                "timeline v11 bound bundle cleanup root persisted"
            )
    finally:
        os.close(descriptor)


def _rename_noreplace_at(
    parent_descriptor: int, source_name: str, destination_name: str
) -> None:
    """Atomically rename within one already-bound parent without replacement."""

    _require_component(source_name, label="timeline v11 rename source")
    _require_component(destination_name, label="timeline v11 rename destination")
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        function = library.renameatx_np
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            source,
            parent_descriptor,
            destination,
            0x00000004,  # RENAME_EXCL
        )
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor,
            source,
            parent_descriptor,
            destination,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:  # pragma: no cover - supported publisher hosts are Darwin/Linux
        raise OSError(
            errno.ENOTSUP,
            "atomic descriptor-relative no-replace rename is unavailable",
        )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            destination_name,
        )


def _promote_noreplace_checked(
    stage: Path,
    destination: Path,
    *,
    directory: bool,
    parent_bindings: ParentBindings,
    require_current_parent_paths: bool = True,
) -> tuple[int, int]:
    if require_current_parent_paths:
        _assert_parent_bindings(parent_bindings, label="before promotion")
    else:
        _assert_parent_descriptors(parent_bindings, label="before bound rollback")
    if stage.parent != destination.parent:
        raise ConstructionTimelineV11Error(
            "timeline v11 promotion must remain within one bound parent"
        )
    _bound_parent, _parent_identity, parent_descriptor = _binding_for_parent(
        parent_bindings, stage.parent
    )
    identity = _identity_at(parent_descriptor, stage.name, directory=directory)
    if require_current_parent_paths and not _has_identity(
        stage, identity, directory=directory
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 promotion source differs from its bound parent entry"
        )
    if _stat_at(parent_descriptor, destination.name) is not None:
        raise ConstructionTimelineV11Error(
            f"timeline v11 no-replace destination exists: {destination}"
        )

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        owned_descriptor = os.open(stage.name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise ConstructionTimelineV11Error(
            f"timeline v11 promotion source cannot be bound: {stage.name}"
        ) from error
    operation_error: BaseException | None = None
    original_mode: int | None = None
    try:
        details = _fstat_identity_with_retry(
            owned_descriptor,
            expected_kind="directory" if directory else "file",
            label="timeline v11 promotion source descriptor",
        )
        if details[:2] != identity:
            raise ConstructionTimelineV11Error(
                "timeline v11 promotion source changed while opening"
            )
        original_mode = stat.S_IMODE(os.fstat(owned_descriptor).st_mode)
        # Darwin can reject RENAME_EXCL for a read-only directory root. Keep an
        # open inode handle, thaw only that inode, and restore it even if the
        # rename succeeds before a helper raises.
        if directory and not (original_mode & stat.S_IWUSR):
            os.fchmod(owned_descriptor, original_mode | stat.S_IWUSR)
        try:
            _rename_noreplace_at(parent_descriptor, stage.name, destination.name)
        except OSError as error:
            raise ConstructionTimelineV11Error(
                f"timeline v11 bound no-replace promotion failed: {destination}"
            ) from error
        os.fsync(parent_descriptor)
        if _has_identity_at(
            parent_descriptor, stage.name, identity, directory=directory
        ) or not _has_identity_at(
            parent_descriptor, destination.name, identity, directory=directory
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 bound promoted identity differs"
            )
    except _OPERATION_FAILURES as error:
        operation_error = error
    finally:
        if original_mode is not None:
            try:
                os.fchmod(owned_descriptor, original_mode)
                os.fsync(owned_descriptor)
            except _OPERATION_FAILURES as restore_error:
                if operation_error is None:
                    operation_error = restore_error
                else:
                    operation_error.add_note(
                        "timeline v11 promotion mode restoration failed: "
                        f"{restore_error}"
                    )
        try:
            os.close(owned_descriptor)
        except OSError as close_error:
            if operation_error is None:
                operation_error = close_error
            else:
                operation_error.add_note(
                    f"timeline v11 promotion descriptor close failed: {close_error}"
                )
        try:
            if require_current_parent_paths:
                _assert_parent_bindings(parent_bindings, label="after promotion")
            else:
                _assert_parent_descriptors(
                    parent_bindings, label="after bound rollback"
                )
        except _OPERATION_FAILURES as binding_error:
            if operation_error is None:
                operation_error = binding_error
            else:
                operation_error.add_note(
                    f"timeline v11 promotion parent check failed: {binding_error}"
                )
    if operation_error is not None:
        raise operation_error
    if not _has_identity_at(
        parent_descriptor, destination.name, identity, directory=directory
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 promoted bound identity differs"
        )
    if require_current_parent_paths and not _has_identity(
        destination, identity, directory=directory
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 promoted path identity differs"
        )
    return identity


def _rollback_noreplace(
    destination: Path,
    stage: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
    parent_bindings: ParentBindings,
) -> None:
    _assert_parent_descriptors(parent_bindings, label="before rollback")
    if destination.parent != stage.parent:
        raise ConstructionTimelineV11Error(
            "timeline v11 rollback must remain within one bound parent"
        )
    _bound_parent, _parent_identity, parent_descriptor = _binding_for_parent(
        parent_bindings, destination.parent
    )
    if not _has_identity_at(
        parent_descriptor, destination.name, identity, directory=directory
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 refuses identity-mismatched bound rollback"
        )
    if _stat_at(parent_descriptor, stage.name) is not None:
        raise ConstructionTimelineV11Error(
            "timeline v11 bound rollback stage is occupied"
        )
    _promote_noreplace_checked(
        destination,
        stage,
        directory=directory,
        parent_bindings=parent_bindings,
        require_current_parent_paths=False,
    )
    if not _has_identity_at(
        parent_descriptor, stage.name, identity, directory=directory
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 bound rollback identity differs"
        )


def _private_promotion_roundtrip(
    definition: Path,
    bundle: Path,
    *,
    definition_identity: tuple[int, int],
    bundle_identities: Mapping[str, tuple[str, int, int]],
    parent_bindings: ParentBindings,
) -> None:
    token = f"{os.getpid()}-{time.time_ns()}"
    moved_definition = definition.parent / f".{DEFINITION.name}.roundtrip-{token}"
    moved_bundle = bundle.parent / f".{BUNDLE.name}.roundtrip-{token}"
    bundle_identity = _identity(bundle, directory=True)
    if not _bound_identity(
        parent_bindings, bundle, bundle_identity, directory=True
    ) or not _bound_identity(
        parent_bindings, definition, definition_identity, directory=False
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 private roundtrip stages differ from bound parents"
        )
    definition_moved = False
    bundle_moved = False
    operation_error: BaseException | None = None
    try:
        _promote_noreplace_checked(
            bundle,
            moved_bundle,
            directory=True,
            parent_bindings=parent_bindings,
        )
        bundle_moved = True
        _assert_bound_tree_identities(parent_bindings, moved_bundle, bundle_identities)
        _promote_noreplace_checked(
            definition,
            moved_definition,
            directory=False,
            parent_bindings=parent_bindings,
        )
        definition_moved = True
        if not _bound_identity(
            parent_bindings,
            moved_definition,
            definition_identity,
            directory=False,
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 private definition identity changed"
            )
    except _OPERATION_FAILURES as error:
        operation_error = error
        definition_moved = definition_moved or _bound_identity(
            parent_bindings,
            moved_definition,
            definition_identity,
            directory=False,
        )
        bundle_moved = bundle_moved or _bound_identity(
            parent_bindings, moved_bundle, bundle_identity, directory=True
        )
        if _bound_present(parent_bindings, moved_definition) and not definition_moved:
            error.add_note(
                "retained substituted timeline v11 private definition destination"
            )
        if _bound_present(parent_bindings, moved_bundle) and not bundle_moved:
            error.add_note(
                "retained substituted timeline v11 private bundle destination"
            )

    rollback_errors: list[Exception] = []
    if definition_moved:
        try:
            _rollback_noreplace(
                moved_definition,
                definition,
                definition_identity,
                directory=False,
                parent_bindings=parent_bindings,
            )
        except _OPERATION_FAILURES as error:
            rollback_errors.append(error)
    if bundle_moved:
        try:
            _assert_bound_tree_identities(
                parent_bindings, moved_bundle, bundle_identities
            )
            _rollback_noreplace(
                moved_bundle,
                bundle,
                bundle_identity,
                directory=True,
                parent_bindings=parent_bindings,
            )
            _assert_bound_tree_identities(parent_bindings, bundle, bundle_identities)
        except _OPERATION_FAILURES as error:
            rollback_errors.append(error)
    if operation_error is not None:
        for error in rollback_errors:
            operation_error.add_note(f"timeline v11 private rollback failed: {error}")
        raise operation_error
    if rollback_errors:
        primary = rollback_errors[0]
        for error in rollback_errors[1:]:
            primary.add_note(
                f"additional timeline v11 private rollback failure: {error}"
            )
        raise primary
    if _bound_present(parent_bindings, moved_definition) or _bound_present(
        parent_bindings, moved_bundle
    ):
        raise ConstructionTimelineV11Error(
            "timeline v11 private promotion roundtrip left residue"
        )


def _stage_paths() -> list[Path]:
    patterns = (
        f".{DEFINITION.name}.private-stage-*",
        f".{BUNDLE.name}.private-stage-*",
        f".{DEFINITION.name}.roundtrip-*",
        f".{BUNDLE.name}.roundtrip-*",
    )
    return [
        path
        for parent, pattern in (
            (DEFINITION.parent, patterns[0]),
            (BUNDLE.parent, patterns[1]),
            (DEFINITION.parent, patterns[2]),
            (BUNDLE.parent, patterns[3]),
        )
        for path in parent.glob(pattern)
    ]


def _require_final_absent(label: str, *, include_lock: bool = False) -> None:
    paths = [DEFINITION, BUNDLE]
    if include_lock:
        paths.append(PUBLICATION_LOCK)
    present = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if present:
        raise ConstructionTimelineV11Error(
            f"{label} timeline v11 final path collision: {present!r}"
        )


def _require_stage_absent(label: str) -> None:
    stages = _stage_paths()
    if stages:
        raise ConstructionTimelineV11Error(
            f"{label} timeline v11 private stage residue: "
            f"{[str(path) for path in stages]!r}"
        )


@contextmanager
def _publication_lock(
    parent_bindings: ParentBindings | None = None,
) -> Iterator[None]:
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        if parent_bindings is not None:
            _assert_parent_bindings(parent_bindings, label="before publication lock")
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        details = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="timeline v11 publication lock",
        )
        identity = details[:2]
        payload = f"pid={os.getpid()}\n".encode("ascii")
        if os.write(descriptor, payload) != len(payload):
            raise ConstructionTimelineV11Error(
                "short timeline v11 publication-lock write"
            )
        os.fsync(descriptor)
        if parent_bindings is not None:
            _assert_parent_bindings(parent_bindings, label="inside publication lock")
        yield
    except FileExistsError as error:
        raise ConstructionTimelineV11Error(
            f"active timeline v11 publication lock exists: {PUBLICATION_LOCK}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if identity is not None:
            try:
                current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != identity
                ):
                    raise ConstructionTimelineV11Error(
                        "refusing substituted timeline v11 publication-lock cleanup"
                    )
                PUBLICATION_LOCK.unlink()
        if parent_bindings is not None:
            _assert_parent_bindings(
                parent_bindings, label="after publication lock cleanup"
            )


@contextmanager
def _publication_lock_with_recovery(
    parent_bindings: ParentBindings,
    recover: Callable[[BaseException], None],
) -> Iterator[None]:
    """Keep rollback live through lock cleanup and every body-side report."""

    try:
        with _publication_lock(parent_bindings):
            yield
    except _OPERATION_FAILURES as error:
        try:
            recover(error)
        except _OPERATION_FAILURES as recovery_error:
            error.add_note(
                f"timeline v11 outer publication recovery failed: {recovery_error}"
            )
        raise


def _target_timestamp(generated_at: str | None) -> tuple[str, datetime]:
    target = (
        _parse_utc(generated_at, label="timeline v11 generated_at")
        if generated_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    latest_input = max(
        _parse_utc(spec.recorded_at, label=f"open seed v{spec.version} recorded_at")
        for spec in RELEASE_SPECS
    )
    if target <= latest_input:
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at must follow open seed v97"
        )
    if target <= datetime.now(UTC):
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at must be future before staging"
        )
    canonical = (
        target.astimezone(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    if generated_at is not None and generated_at != canonical:
        raise ConstructionTimelineV11Error(
            "timeline v11 generated_at must be canonical whole-second UTC"
        )
    return canonical, target


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _bundle_report(bundle: Path) -> dict[str, dict[str, Any]]:
    return {
        path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path.read_bytes())}
        for path in sorted(bundle.iterdir(), key=lambda item: item.name)
    }


def _cleanup_private_stages(
    *,
    definition: Path | None,
    definition_identity: tuple[int, int] | None,
    bundle: Path | None,
    bundle_identities: Mapping[str, tuple[str, int, int]] | None,
    parent_bindings: ParentBindings,
    active_error: BaseException | None = None,
) -> None:
    errors: list[Exception] = []
    if (
        bundle is not None
        and bundle_identities is not None
        and _bound_present(parent_bindings, bundle)
    ):
        try:
            _discard_bundle_stage_bound(bundle, bundle_identities, parent_bindings)
        except _OPERATION_FAILURES as error:
            errors.append(error)
    if (
        definition is not None
        and definition_identity is not None
        and _bound_present(parent_bindings, definition)
    ):
        try:
            _discard_definition_stage_bound(
                definition, definition_identity, parent_bindings
            )
        except _OPERATION_FAILURES as error:
            errors.append(error)
    if errors:
        if active_error is not None:
            for error in errors:
                active_error.add_note(f"timeline v11 cleanup failed: {error}")
            return
        primary = errors[0]
        for error in errors[1:]:
            primary.add_note(f"additional timeline v11 cleanup failure: {error}")
        raise primary


def _prepare_construction_timeline_v11_bound(
    generated_at: str | None,
    *,
    replay_count: int,
    parent_bindings: ParentBindings,
) -> dict[str, Any]:
    """Validate a private v11 candidate and stop before final promotion."""

    if replay_count != 2:
        raise ConstructionTimelineV11Error(
            "timeline v11 requires exactly two offline replays"
        )
    _assert_parent_bindings(parent_bindings, label="prepublication start")
    _require_final_absent("prepublication", include_lock=True)
    _require_stage_absent("prepublication")
    timestamp, target = _target_timestamp(generated_at)
    guard = _input_guard_state()
    if guard != _reviewed_input_guard():
        raise ConstructionTimelineV11Error(
            "timeline v11 accepted-input guard differs before prepublication"
        )

    definition_stage: Path | None = None
    definition_identity: tuple[int, int] | None = None
    bundle_stage: Path | None = None
    bundle_identities: dict[str, tuple[str, int, int]] | None = None
    result: dict[str, Any]
    try:
        definition_raw = CODEC._canonical_json(_definition_document(timestamp))
        definition_stage, definition_identity = _write_definition_stage(
            definition_raw, parent_bindings=parent_bindings
        )
        definition = _load_definition(
            definition_stage,
            validation_wall_clock=target,
            allow_future=True,
        )
        payloads, manifest = _prepare_payloads(definition)
        bundle_stage, bundle_identities = _write_bundle_stage(
            payloads, parent_bindings=parent_bindings
        )
        _freeze(definition_stage, bundle_stage)
        _assert_tree_identities(bundle_stage, bundle_identities)
        validated = validate_construction_timeline_bundle(
            bundle_stage,
            definition_path=definition_stage,
            verify_inputs=False,
            require_live=False,
            validation_wall_clock=target,
            parent_bindings=parent_bindings,
        )
        if validated != manifest:
            raise ConstructionTimelineV11Error(
                "timeline v11 staged canonical manifest differs"
            )
        replay_digest = _validate_two_replays(
            definition, bundle_stage, replay_count=replay_count
        )
        _validate_publication_times(
            definition_stage,
            bundle_stage,
            generated_at=timestamp,
            validation_wall_clock=target,
            require_live=False,
        )
        frozen_definition = definition_stage.read_bytes()
        frozen_tree = tree_digest(bundle_stage)
        _private_promotion_roundtrip(
            definition_stage,
            bundle_stage,
            definition_identity=definition_identity,
            bundle_identities=bundle_identities,
            parent_bindings=parent_bindings,
        )
        if (
            definition_stage.read_bytes() != frozen_definition
            or tree_digest(bundle_stage) != frozen_tree
        ):
            raise ConstructionTimelineV11Error(
                "timeline v11 private bytes changed during roundtrip"
            )
        _assert_tree_identities(bundle_stage, bundle_identities)
        result = {
            "status": "prepublication-validated",
            "publication_authorized": False,
            "barrier": "stopped-before-final-no-replace-promotion",
            "generated_at": timestamp,
            "definition_bytes": len(frozen_definition),
            "definition_sha256": _sha256(frozen_definition),
            "bundle_files": _bundle_report(bundle_stage),
            "bundle_tree_sha256": frozen_tree,
            "two_replay_manifest_sha256": replay_digest,
            "addition_event_contract_sha256": ADDITION_EVENT_CONTRACT_SHA256,
            "counts": validated["counts"],
            "delta": dict(DELTA_CONTRACT),
            "private_no_replace_roundtrip_validated": True,
            "final_definition_absent": not DEFINITION.exists(),
            "final_bundle_absent": not BUNDLE.exists(),
            "publication_lock_absent": not PUBLICATION_LOCK.exists(),
        }
    finally:
        _cleanup_private_stages(
            definition=definition_stage,
            definition_identity=definition_identity,
            bundle=bundle_stage,
            bundle_identities=bundle_identities,
            parent_bindings=parent_bindings,
            active_error=sys.exception(),
        )
    if _input_guard_state() != guard:
        raise ConstructionTimelineV11Error(
            "timeline v11 prepublication mutated accepted inputs"
        )
    _require_final_absent("post-prepublication", include_lock=True)
    _require_stage_absent("post-prepublication")
    _assert_parent_bindings(parent_bindings, label="prepublication completion")
    return result


def prepare_construction_timeline_v11(
    generated_at: str | None = None, *, replay_count: int = 2
) -> dict[str, Any]:
    """Run publication-proof private validation and never promote a final."""

    with _bound_output_parents() as parent_bindings:
        return _prepare_construction_timeline_v11_bound(
            generated_at,
            replay_count=replay_count,
            parent_bindings=parent_bindings,
        )


def _existing_identical(
    generated_at: str | None, parent_bindings: ParentBindings
) -> dict[str, Any]:
    _assert_parent_bindings(parent_bindings, label="existing-identical validation")
    definition_document = _canonical_document(DEFINITION, "timeline v11 definition")
    existing_generated_at = definition_document.get("generated_at")
    if not isinstance(existing_generated_at, str):
        raise ConstructionTimelineV11Error(
            "existing timeline v11 generated_at is missing"
        )
    if generated_at is not None and generated_at != existing_generated_at:
        raise ConstructionTimelineV11Error("existing timeline v11 generated_at differs")
    manifest = validate_construction_timeline_bundle(
        BUNDLE,
        definition_path=DEFINITION,
        verify_inputs=True,
        require_live=True,
        parent_bindings=parent_bindings,
    )
    _assert_parent_bindings(parent_bindings, label="existing-identical completion")
    return {
        "status": "existing-identical",
        "definition": str(DEFINITION),
        "definition_sha256": _sha256(DEFINITION.read_bytes()),
        "bundle": str(BUNDLE),
        "bundle_files": _bundle_report(BUNDLE),
        "bundle_tree_sha256": tree_digest(BUNDLE),
        "generated_at": existing_generated_at,
        "counts": manifest["counts"],
    }


def _rollback_definition_after_error(
    error: BaseException,
    *,
    stage: Path,
    identity: tuple[int, int],
    parent_bindings: ParentBindings,
    may_have_left_stage: bool,
) -> bool:
    if _bound_identity(parent_bindings, DEFINITION, identity, directory=False):
        try:
            _rollback_noreplace(
                DEFINITION,
                stage,
                identity,
                directory=False,
                parent_bindings=parent_bindings,
            )
            return False
        except _OPERATION_FAILURES as rollback_error:
            error.add_note(f"timeline v11 definition rollback failed: {rollback_error}")
            return True
    if _bound_present(parent_bindings, DEFINITION):
        error.add_note("retained substituted timeline v11 definition during rollback")
    elif may_have_left_stage and not _bound_identity(
        parent_bindings, stage, identity, directory=False
    ):
        error.add_note(
            "published timeline v11 definition inode is outside known paths; "
            "retained fail-closed"
        )
    return not _bound_identity(parent_bindings, stage, identity, directory=False)


def _rollback_bundle_after_error(
    error: BaseException,
    *,
    stage: Path,
    identity: tuple[int, int],
    identities: Mapping[str, tuple[str, int, int]],
    parent_bindings: ParentBindings,
    may_have_left_stage: bool,
) -> bool:
    if _bound_identity(parent_bindings, BUNDLE, identity, directory=True):
        try:
            _assert_bound_tree_identities(parent_bindings, BUNDLE, identities)
            _rollback_noreplace(
                BUNDLE,
                stage,
                identity,
                directory=True,
                parent_bindings=parent_bindings,
            )
            _assert_bound_tree_identities(parent_bindings, stage, identities)
            return False
        except _OPERATION_FAILURES as rollback_error:
            error.add_note(f"timeline v11 bundle rollback failed: {rollback_error}")
            return True
    if _bound_present(parent_bindings, BUNDLE):
        error.add_note("retained substituted timeline v11 bundle during rollback")
    elif may_have_left_stage and not _bound_identity(
        parent_bindings, stage, identity, directory=True
    ):
        error.add_note(
            "published timeline v11 bundle inode is outside known paths; "
            "retained fail-closed"
        )
    return not _bound_identity(parent_bindings, stage, identity, directory=True)


def publish_construction_timeline_v11(
    generated_at: str | None = None, *, publication_authorized: bool = False
) -> dict[str, Any]:
    """Publish v11 only after explicit authorization and every governed gate."""

    if not publication_authorized:
        raise ConstructionTimelineV11Error(
            "timeline v11 publication requires explicit authorization"
        )
    with _bound_output_parents() as parent_bindings:
        _assert_parent_bindings(parent_bindings, label="publication entry")
        definition_stage: Path | None = None
        definition_identity: tuple[int, int] | None = None
        bundle_stage: Path | None = None
        bundle_identities: dict[str, tuple[str, int, int]] | None = None
        published_definition = False
        published_bundle = False
        bundle_identity: tuple[int, int] | None = None

        def recover_publication(error: BaseException) -> None:
            nonlocal published_bundle, published_definition
            if (
                definition_stage is not None
                and definition_identity is not None
                and (
                    published_definition
                    or _bound_identity(
                        parent_bindings,
                        DEFINITION,
                        definition_identity,
                        directory=False,
                    )
                )
            ):
                published_definition = _rollback_definition_after_error(
                    error,
                    stage=definition_stage,
                    identity=definition_identity,
                    parent_bindings=parent_bindings,
                    may_have_left_stage=True,
                )
            if (
                bundle_stage is not None
                and bundle_identities is not None
                and bundle_identity is not None
                and (
                    published_bundle
                    or _bound_identity(
                        parent_bindings,
                        BUNDLE,
                        bundle_identity,
                        directory=True,
                    )
                )
            ):
                published_bundle = _rollback_bundle_after_error(
                    error,
                    stage=bundle_stage,
                    identity=bundle_identity,
                    identities=bundle_identities,
                    parent_bindings=parent_bindings,
                    may_have_left_stage=True,
                )
            _cleanup_private_stages(
                definition=(None if published_definition else definition_stage),
                definition_identity=definition_identity,
                bundle=None if published_bundle else bundle_stage,
                bundle_identities=bundle_identities,
                parent_bindings=parent_bindings,
                active_error=error,
            )

        with _publication_lock_with_recovery(
            parent_bindings,
            recover_publication,
        ):
            # Presence and existing-identical handling are deliberately inside the
            # exclusive lock. A pre-existing active lock always wins, even when
            # both final paths would otherwise validate as existing-identical.
            definition_present = DEFINITION.exists() or DEFINITION.is_symlink()
            bundle_present = BUNDLE.exists() or BUNDLE.is_symlink()
            if definition_present and bundle_present:
                return _existing_identical(generated_at, parent_bindings)
            if definition_present or bundle_present:
                raise ConstructionTimelineV11Error(
                    "partial timeline v11 final-path collision"
                )
            _require_stage_absent("publication")
            timestamp, target = _target_timestamp(generated_at)
            guard = _input_guard_state()
            if guard != _reviewed_input_guard():
                raise ConstructionTimelineV11Error(
                    "timeline v11 accepted-input guard differs before publication"
                )
            _assert_parent_bindings(parent_bindings, label="before staging")

            manifest: dict[str, Any]
            try:
                definition_raw = CODEC._canonical_json(_definition_document(timestamp))
                definition_stage, definition_identity = _write_definition_stage(
                    definition_raw, parent_bindings=parent_bindings
                )
                definition = _load_definition(
                    definition_stage,
                    validation_wall_clock=target,
                    allow_future=True,
                )
                payloads, expected_manifest = _prepare_payloads(definition)
                bundle_stage, bundle_identities = _write_bundle_stage(
                    payloads, parent_bindings=parent_bindings
                )
                _freeze(definition_stage, bundle_stage)
                _assert_tree_identities(bundle_stage, bundle_identities)
                staged_manifest = validate_construction_timeline_bundle(
                    bundle_stage,
                    definition_path=definition_stage,
                    verify_inputs=False,
                    require_live=False,
                    validation_wall_clock=target,
                    parent_bindings=parent_bindings,
                )
                if staged_manifest != expected_manifest:
                    raise ConstructionTimelineV11Error(
                        "timeline v11 staged manifest differs before publication"
                    )
                _validate_two_replays(definition, bundle_stage, replay_count=2)
                _private_promotion_roundtrip(
                    definition_stage,
                    bundle_stage,
                    definition_identity=definition_identity,
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                )
                frozen_definition = definition_stage.read_bytes()
                frozen_tree = tree_digest(bundle_stage)
                _assert_parent_bindings(
                    parent_bindings, label="before publication wait"
                )
                _require_final_absent("pre-wait")
                _wait_until(target)
                _assert_parent_bindings(parent_bindings, label="after publication wait")
                _require_final_absent("late")
                if not _has_identity(
                    definition_stage, definition_identity, directory=False
                ):
                    raise ConstructionTimelineV11Error(
                        "timeline v11 definition stage identity changed"
                    )
                _assert_tree_identities(bundle_stage, bundle_identities)
                if (
                    definition_stage.read_bytes() != frozen_definition
                    or tree_digest(bundle_stage) != frozen_tree
                    or _input_guard_state() != guard
                ):
                    raise ConstructionTimelineV11Error(
                        "timeline v11 stage or inputs changed while waiting"
                    )
                _refresh_publication_ctimes(definition_stage, bundle_stage)
                _assert_tree_identities(bundle_stage, bundle_identities)
                _validate_publication_times(
                    definition_stage,
                    bundle_stage,
                    generated_at=timestamp,
                    validation_wall_clock=datetime.now(UTC),
                    require_live=True,
                )
                _assert_parent_bindings(parent_bindings, label="before final promotion")

                bundle_identity = _identity(bundle_stage, directory=True)
                try:
                    promoted_bundle_identity = _promote_noreplace_checked(
                        bundle_stage,
                        BUNDLE,
                        directory=True,
                        parent_bindings=parent_bindings,
                    )
                    published_bundle = True
                    if promoted_bundle_identity != bundle_identity:
                        raise ConstructionTimelineV11Error(
                            "timeline v11 bundle promotion identity differs"
                        )
                    _assert_tree_identities(BUNDLE, bundle_identities)
                    if tree_digest(BUNDLE) != frozen_tree:
                        raise ConstructionTimelineV11Error(
                            "timeline v11 promoted bundle bytes differ"
                        )
                    promoted_definition_identity = _promote_noreplace_checked(
                        definition_stage,
                        DEFINITION,
                        directory=False,
                        parent_bindings=parent_bindings,
                    )
                    published_definition = True
                    if promoted_definition_identity != definition_identity:
                        raise ConstructionTimelineV11Error(
                            "timeline v11 definition promotion identity differs"
                        )
                    if DEFINITION.read_bytes() != frozen_definition:
                        raise ConstructionTimelineV11Error(
                            "timeline v11 promoted definition bytes differ"
                        )
                except _OPERATION_FAILURES as error:
                    # A helper may raise after renameatx_np already succeeded.
                    # Derive state from inode identity, then roll back every owned
                    # final. Foreign substitutions are retained with explicit notes.
                    definition_left_stage = not _bound_identity(
                        parent_bindings,
                        definition_stage,
                        definition_identity,
                        directory=False,
                    )
                    bundle_left_stage = not _bound_identity(
                        parent_bindings,
                        bundle_stage,
                        bundle_identity,
                        directory=True,
                    )
                    published_definition = _rollback_definition_after_error(
                        error,
                        stage=definition_stage,
                        identity=definition_identity,
                        parent_bindings=parent_bindings,
                        may_have_left_stage=(
                            published_definition or definition_left_stage
                        ),
                    )
                    published_bundle = _rollback_bundle_after_error(
                        error,
                        stage=bundle_stage,
                        identity=bundle_identity,
                        identities=bundle_identities,
                        parent_bindings=parent_bindings,
                        may_have_left_stage=(published_bundle or bundle_left_stage),
                    )
                    raise

                try:
                    manifest = validate_construction_timeline_bundle(
                        BUNDLE,
                        definition_path=DEFINITION,
                        verify_inputs=True,
                        require_live=True,
                        parent_bindings=parent_bindings,
                    )
                    # This final guard is inside both the lock and rollback scope.
                    if _input_guard_state() != guard:
                        raise ConstructionTimelineV11Error(
                            "timeline v11 publication mutated accepted inputs"
                        )
                    _assert_parent_bindings(
                        parent_bindings, label="after final validation"
                    )
                    _assert_parent_bindings(
                        parent_bindings, label="publication completion"
                    )
                    _require_stage_absent("publication completion")
                    _assert_parent_bindings(parent_bindings, label="publisher return")
                    result = {
                        "status": "published",
                        "definition": str(DEFINITION),
                        "definition_sha256": _sha256(DEFINITION.read_bytes()),
                        "bundle": str(BUNDLE),
                        "bundle_files": _bundle_report(BUNDLE),
                        "bundle_tree_sha256": tree_digest(BUNDLE),
                        "generated_at": timestamp,
                        "counts": manifest["counts"],
                    }
                except _OPERATION_FAILURES as error:
                    published_definition = _rollback_definition_after_error(
                        error,
                        stage=definition_stage,
                        identity=definition_identity,
                        parent_bindings=parent_bindings,
                        may_have_left_stage=True,
                    )
                    published_bundle = _rollback_bundle_after_error(
                        error,
                        stage=bundle_stage,
                        identity=bundle_identity,
                        identities=bundle_identities,
                        parent_bindings=parent_bindings,
                        may_have_left_stage=True,
                    )
                    raise
            finally:
                _cleanup_private_stages(
                    definition=(None if published_definition else definition_stage),
                    definition_identity=definition_identity,
                    bundle=(None if published_bundle else bundle_stage),
                    bundle_identities=bundle_identities,
                    parent_bindings=parent_bindings,
                    active_error=sys.exception(),
                )
        return result


def write_construction_timeline_bundle(
    definition_path: str | Path = DEFINITION,
    output_directory: str | Path = BUNDLE,
    *,
    generated_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only the reserved v11 paths after explicit authorization."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineV11Error(
            "timeline v11 publication paths are reserved"
        )
    return publish_construction_timeline_v11(
        generated_at, publication_authorized=publication_authorized
    )


build_construction_timeline_bundle = write_construction_timeline_bundle


def prepare_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Publication-proof private preflight for timeline v11."
    )
    result.add_argument("--generated-at")
    result.add_argument("--replay-count", type=int, default=2)
    return result


def prepare_main(argv: Sequence[str] | None = None) -> int:
    arguments = prepare_parser().parse_args(argv)
    result = prepare_construction_timeline_v11(
        arguments.generated_at, replay_count=arguments.replay_count
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def publisher_parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Explicitly authorized final publisher for construction timeline v11."
        )
    )
    result.add_argument("--generated-at")
    result.add_argument("--publish-authorized", action="store_true")
    return result


def publisher_main(
    argv: Sequence[str] | None = None, *, publication_authorized: bool = False
) -> int:
    parser = publisher_parser()
    arguments = parser.parse_args(argv)
    if not (publication_authorized or arguments.publish_authorized):
        parser.error("final publication requires --publish-authorized")
    result = publish_construction_timeline_v11(
        arguments.generated_at, publication_authorized=True
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


main = prepare_main


if __name__ == "__main__":
    raise SystemExit(prepare_main())


__all__ = [
    "ADDED_OBSERVATIONS",
    "ADDED_TIMELINE_ENTITIES",
    "ADDITION_EVENT_CONTRACT_SHA256",
    "AS_OF",
    "ATTRIBUTION_FILENAME",
    "BEALE_TULSA_KEY",
    "BUNDLE",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COVERAGE_FILENAME",
    "DEFINITION",
    "DELTA_CONTRACT",
    "EXPECTED_COUNTS",
    "FIN04_KEY",
    "INFERENCE_GUARDRAILS",
    "LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES",
    "LINEAGE_AWARE_SOURCE_FAMILIES",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OBSERVATIONS_FILENAME",
    "OBSERVATION_FIELDS",
    "PREDECESSOR_TREE_SHA256",
    "PROMOTION_CONTRACT",
    "PUBLICATION_LOCK",
    "RELEASE_ADDITION_COUNTS",
    "RELEASE_SPECS",
    "STALE_CURRENT_UNKNOWN_KEYS",
    "TIMELINES_FILENAME",
    "TIMELINE_ID",
    "WOOD_DALE_KEY",
    "ConstructionTimelineError",
    "ConstructionTimelineV11Error",
    "build_construction_timeline_bundle",
    "prepare_construction_timeline_v11",
    "prepare_main",
    "publish_construction_timeline_v11",
    "publisher_main",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
