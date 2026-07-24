"""Publish timeline v9 as the exact four-observation successor to v8.

All 537 accepted v8 lifecycle rows and all 517 accepted v8 grouped timeline
rows are retained byte-for-byte.  The only additions are the four dated
project observations first accepted by open seed v87.  Their row-linked
evidence families remain distinct from the frozen v12 exact-identity lineage:
DataBank's lifecycle observations cite its official LinkedIn update, while the
singleton identity rows retain the DataBank facility-page source family.
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

from . import construction_timeline_v8 as previous
from . import exact_identity_decisions_v12 as identity_v12
from . import federation_v36
from . import open_seed_v87
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
CODEC = previous.previous.v5.v3
TIMELINE_CARRIER = previous.previous.carrier

TIMELINE_ID = "2026-07-21-public-open-v9"
AS_OF = "2026-07-21"
# Reserved one-time publication instant; staging must finish before it.
GENERATED_AT = "2026-07-22T01:20:00Z"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v9.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v9"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v9.lock"

OPEN_SEED_DEFINITION = open_seed_v87.DEFINITION
OPEN_SEED_RELEASE = open_seed_v87.RELEASE
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v87.py"
OPEN_SEED_RECORDED_AT = "2026-07-22T00:06:19Z"
OPEN_SEED_DEFINITION_PIN = (
    103_031,
    "bf0ef1b6bbe9f4f7edb4525de89d487de1e03ed5eaaccc1a0e122e24d5c9bf08",
)
OPEN_SEED_MANIFEST_PIN = (
    15_566,
    "6b2787e982049f1bcab139fce874880499c8610e2e71bb6bde091bcc101abf35",
)
OPEN_SEED_TREE_SHA256 = (
    "02be747070df5f998080ca7c54a94146649a54b84078850c4c31522ae05c6185"
)
OPEN_SEED_CORE_PIN = (
    51_129,
    "9603d8ef7bb626e10f14659a251231bbbf5f8c90d8b8cdfe5e2373d0ea20a9af",
)
OPEN_SEED_DEFINITION_SHA256 = OPEN_SEED_DEFINITION_PIN[1]
OPEN_SEED_MANIFEST_SHA256 = OPEN_SEED_MANIFEST_PIN[1]

PREDECESSOR_DEFINITION = previous.DEFINITION
PREDECESSOR_BUNDLE = previous.BUNDLE
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v8.py"
PREDECESSOR_DEFINITION_PIN = (
    2_881,
    "9f67b19847aadf326cdd3701c3e4a8aa5309a9b59c58d3d749a6369fdfc3ec97",
)
PREDECESSOR_MANIFEST_PIN = (
    3_881,
    "4a71dd94b0ab97a8b0e9add0b4688bececec285832de991f7c71a23a7dc8a02d",
)
PREDECESSOR_TREE_SHA256 = (
    "f3231947d338bd201bc416dd7d78cba51e5193d484a8fb84a0f2bab2b4b65f12"
)
PREDECESSOR_CORE_PIN = (
    67_029,
    "74864aebfd96ce65b7fe7e13037c93e30087b1652d7f63a562859590974fdc0f",
)
PREDECESSOR_DEFINITION_SHA256 = PREDECESSOR_DEFINITION_PIN[1]
PREDECESSOR_MANIFEST_SHA256 = PREDECESSOR_MANIFEST_PIN[1]

FEDERATION_DEFINITION = federation_v36.DEFINITION
FEDERATION_BUNDLE = federation_v36.INDEX_DIR
FEDERATION_CORE = ROOT / "datacenter_atlas/federation_v36.py"
FEDERATION_GENERATED_AT = "2026-07-22T00:30:00Z"
FEDERATION_DEFINITION_PIN = (
    1_788,
    "84edf2fd5691dbac5740372c63ed87fa1be91f12cf48675c262ebd7c0a9b57d0",
)
FEDERATION_INDEX_PIN = (
    36_486,
    "b5cc9f77f5b7eaef50631320ef748b4f246b79d19aa8b45a915911e54b122217",
)
FEDERATION_MANIFEST_PIN = (
    986,
    "e9d2d82b06a56090a4a1a9fc3471d0d3ecd08573b42180449d9ff3db6fdd834c",
)
FEDERATION_TREE_SHA256 = (
    "f0532a1ebfeef502948f634a88ca10962eb75f25a84fce7da7026693371fa1cb"
)
FEDERATION_CORE_PIN = (
    29_353,
    "bffef3ed7488896035bfb1c8ebdd3c050d2a29efd11acda3f495fea6a4000c1a",
)

IDENTITY_DEFINITION = identity_v12.DEFINITION
IDENTITY_BUNDLE = identity_v12.BUNDLE
IDENTITY_CORE = ROOT / "datacenter_atlas/exact_identity_decisions_v12.py"
IDENTITY_RECORDED_AT = "2026-07-22T01:00:00Z"
IDENTITY_DEFINITION_PIN = (
    1_736,
    "18a6717fb01b7db1f1b9424d3cb03d7628dc3b4b8b06979c8e7c0088010ac0c2",
)
IDENTITY_MANIFEST_PIN = (
    11_441,
    "2bb6c2699b53aa3f4e3a1e6cb966985e45419bdfd28fbef866745a3000f431a4",
)
IDENTITY_COMPONENT_MEMBERS_PIN = (
    3_708_569,
    "9a728937c8667bfb66110ab3235063ac73ec1b8c102ab6d489ff0de4d986a3ca",
)
IDENTITY_TREE_SHA256 = (
    "c045070811263c471d8b993f6712608412addf17e24cb68b243a83a0d0ba4891"
)
IDENTITY_CORE_PIN = (
    44_190,
    "200ece35ac1c66ae3c29de851ec083fded6b6b65359d36d69567d4d65dc698ed",
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v9"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v9"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v9"
SCHEMA_VERSION = 9

# The row schemas remain frozen so inherited rows can remain exact.
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
EVENT_CONTRACT_FIELDS = (*previous.EVENT_CONTRACT_FIELDS, "identity_source_family")
FROZEN_DIRECTORY_MODE = previous.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = previous.FROZEN_FILE_MODE
SCOPE = {
    **previous.SCOPE,
    "capacity_inference_applied": False,
}

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 521,
    "multi_observation_entities": 20,
    "raw_lifecycle_observations": 541,
    "repeated_status_multi_observation_entities": 7,
    "single_observation_entities": 501,
    "single_old_observation_entities": 29,
    # Lineage-aware union; row-linked evidence alone has 253 families.
    "source_families": 254,
    "status_changing_multi_observation_entities": 13,
}

FULL_V87_RAW_OBSERVATIONS = 541
PREDECESSOR_OBSERVATIONS = 537
PREDECESSOR_TIMELINES = 517
V87_SELECTED_INPUTS = 456
V86_SELECTED_INPUTS = 452
V87_ADDED_OBSERVATIONS = 4
V87_ADDED_PROJECTS = 4
V87_INHERITED_RECORDED_AT_REWRITES_IGNORED = 154
LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES = 253
LINEAGE_AWARE_SOURCE_FAMILIES = 254

V87_SOURCE_PATHS = tuple(open_seed_v87.ADDITION_ORDER)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
        "curated:riot-rockdale-site:amd-lease-first-phase",
        "curated:databank-lithia-springs-campus:atl5-current-build",
        "curated:databank-lithia-springs-campus:atl6-current-build",
    }
)
OPERATIONAL_CLOSURE_KEYS = frozenset(
    {"curated:riot-rockdale-site:amd-lease-first-phase"}
)
EXPECTED_LIFECYCLE_CONTRACT = frozenset(open_seed_v87.LIFECYCLE_CONTRACT)
EXPECTED_IDENTITY_SOURCE_FAMILIES = {
    key: identity_v12.NEW_ENTITY_CONTRACT[key][1] for key in ADDED_PROJECT_KEYS
}
V87_ADDITION_EVENT_CONTRACT_SHA256 = (
    "63506beac38fc28fc63670174c02a42a1e9a507a2c8c407707516678dff941b2"
)

INFERENCE_GUARDRAILS = {
    "capacity_inferences": 0,
    "cross_source_identity_merges": 0,
    "current_status_persistence_claims": 0,
    "forecast_conversions": 0,
    "satellite_or_cv_promotions": 0,
    "unique_physical_site_claims": 0,
}

DELTA_CONTRACT = {
    "full_v87_raw_lifecycle_observations": FULL_V87_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "lifecycle_row_linked_source_families": LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES,
    "lineage_aware_source_families": LINEAGE_AWARE_SOURCE_FAMILIES,
    "recorded_at_values_preserved_from_v8": True,
    "v87_added_lifecycle_observations": V87_ADDED_OBSERVATIONS,
    "v87_added_project_entities": V87_ADDED_PROJECTS,
    "v87_inherited_recorded_at_rewrites_ignored": (
        V87_INHERITED_RECORDED_AT_REWRITES_IGNORED
    ),
    "v87_selected_source_files": V87_SELECTED_INPUTS,
}

ConstructionTimelineError = previous.ConstructionTimelineError


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


def _file_pin(path: Path) -> tuple[int, str]:
    raw = CODEC._regular_bytes(path, str(path))
    return len(raw), CODEC._sha256_bytes(raw)


def _checkpoint_paths(
    definition_path: Path,
    document: Mapping[str, Any],
    *,
    label: str,
    definition: Path,
    bundle: Path,
    definition_sha256: str,
    manifest_sha256: str,
    tree_sha256: str,
    manifest_name: str = MANIFEST_FILENAME,
) -> None:
    if set(document) != {
        "bundle_path",
        "definition",
        "expected_bundle_tree_sha256",
        "manifest",
    }:
        raise ConstructionTimelineError(f"{label} checkpoint schema is invalid")
    definition_display, definition_digest = CODEC._checkpoint(
        document["definition"], f"{label} definition"
    )
    manifest_display, manifest_digest = CODEC._checkpoint(
        document["manifest"], f"{label} manifest"
    )
    resolved_definition = CODEC._resolve(
        definition_path, definition_display, f"{label} definition"
    )
    resolved_bundle = CODEC._resolve(
        definition_path, document["bundle_path"], f"{label} bundle"
    )
    resolved_manifest = CODEC._resolve(
        definition_path, manifest_display, f"{label} manifest"
    )
    if (
        resolved_definition != definition
        or resolved_bundle != bundle
        or resolved_manifest != bundle / manifest_name
        or definition_digest != definition_sha256
        or manifest_digest != manifest_sha256
        or document["expected_bundle_tree_sha256"] != tree_sha256
    ):
        raise ConstructionTimelineError(f"{label} checkpoint differs")


def _load_definition(
    path_value: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = CODEC._regular_bytes(path, "timeline definition")
    document = CODEC._json_object(raw, "timeline definition")
    if raw != CODEC._canonical_json(document):
        raise ConstructionTimelineError("timeline definition must be canonical JSON")
    if set(document) != {
        "as_of",
        "delta",
        "exact_identity",
        "expected",
        "federation",
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
        raise ConstructionTimelineError("timeline v9 definition contract differs")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if wall_clock.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    generated = _parse_utc(document["generated_at"], label="timeline generated_at")
    if generated <= _parse_utc(IDENTITY_RECORDED_AT, label="identity recorded_at"):
        raise ConstructionTimelineError("timeline generated_at must follow identity v12")
    if generated > wall_clock.astimezone(timezone.utc):
        raise ConstructionTimelineError(
            "timeline generated_at exceeds validation wall clock"
        )

    open_seed = document["open_seed"]
    if not isinstance(open_seed, Mapping) or set(open_seed) != {
        "definition",
        "expected_release_tree_sha256",
        "manifest",
        "release_path",
    }:
        raise ConstructionTimelineError("open seed checkpoint schema is invalid")
    seed_definition_display, seed_definition_digest = CODEC._checkpoint(
        open_seed["definition"], "open seed definition"
    )
    seed_manifest_display, seed_manifest_digest = CODEC._checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    seed_definition = CODEC._resolve(
        path, seed_definition_display, "open seed definition"
    )
    seed_release = CODEC._resolve(path, open_seed["release_path"], "open seed release")
    seed_manifest = CODEC._resolve(path, seed_manifest_display, "open seed manifest")
    if (
        seed_definition != OPEN_SEED_DEFINITION
        or seed_release != OPEN_SEED_RELEASE
        or seed_manifest != OPEN_SEED_RELEASE / MANIFEST_FILENAME
        or seed_definition_digest != OPEN_SEED_DEFINITION_SHA256
        or seed_manifest_digest != OPEN_SEED_MANIFEST_SHA256
        or open_seed["expected_release_tree_sha256"] != OPEN_SEED_TREE_SHA256
    ):
        raise ConstructionTimelineError("open seed v87 checkpoint differs")

    for key, label, definition, bundle, definition_sha, manifest_sha, tree_sha in (
        (
            "predecessor",
            "timeline v8",
            PREDECESSOR_DEFINITION,
            PREDECESSOR_BUNDLE,
            PREDECESSOR_DEFINITION_SHA256,
            PREDECESSOR_MANIFEST_SHA256,
            PREDECESSOR_TREE_SHA256,
        ),
        (
            "federation",
            "federation v36",
            FEDERATION_DEFINITION,
            FEDERATION_BUNDLE,
            FEDERATION_DEFINITION_PIN[1],
            FEDERATION_MANIFEST_PIN[1],
            FEDERATION_TREE_SHA256,
        ),
        (
            "exact_identity",
            "exact identity v12",
            IDENTITY_DEFINITION,
            IDENTITY_BUNDLE,
            IDENTITY_DEFINITION_PIN[1],
            IDENTITY_MANIFEST_PIN[1],
            IDENTITY_TREE_SHA256,
        ),
    ):
        checkpoint = document[key]
        if not isinstance(checkpoint, Mapping):
            raise ConstructionTimelineError(f"{label} checkpoint is invalid")
        _checkpoint_paths(
            path,
            checkpoint,
            label=label,
            definition=definition,
            bundle=bundle,
            definition_sha256=definition_sha,
            manifest_sha256=manifest_sha,
            tree_sha256=tree_sha,
        )
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=document["generated_at"],
        expected=EXPECTED_COUNTS,
    )


def _validate_inputs() -> None:
    checkpoints = {
        OPEN_SEED_DEFINITION: OPEN_SEED_DEFINITION_PIN,
        OPEN_SEED_RELEASE / MANIFEST_FILENAME: OPEN_SEED_MANIFEST_PIN,
        OPEN_SEED_CORE: OPEN_SEED_CORE_PIN,
        PREDECESSOR_DEFINITION: PREDECESSOR_DEFINITION_PIN,
        PREDECESSOR_BUNDLE / MANIFEST_FILENAME: PREDECESSOR_MANIFEST_PIN,
        PREDECESSOR_CORE: PREDECESSOR_CORE_PIN,
        FEDERATION_DEFINITION: FEDERATION_DEFINITION_PIN,
        FEDERATION_BUNDLE / "federated-index.json": FEDERATION_INDEX_PIN,
        FEDERATION_BUNDLE / MANIFEST_FILENAME: FEDERATION_MANIFEST_PIN,
        FEDERATION_CORE: FEDERATION_CORE_PIN,
        IDENTITY_DEFINITION: IDENTITY_DEFINITION_PIN,
        IDENTITY_BUNDLE / MANIFEST_FILENAME: IDENTITY_MANIFEST_PIN,
        IDENTITY_BUNDLE / "component-members.csv": IDENTITY_COMPONENT_MEMBERS_PIN,
        IDENTITY_CORE: IDENTITY_CORE_PIN,
    }
    for checkpoint, pin in checkpoints.items():
        if _file_pin(checkpoint) != pin:
            raise ConstructionTimelineError(f"frozen input changed: {checkpoint}")
    for directory, expected, label in (
        (OPEN_SEED_RELEASE, OPEN_SEED_TREE_SHA256, "open seed v87"),
        (PREDECESSOR_BUNDLE, PREDECESSOR_TREE_SHA256, "timeline v8"),
        (FEDERATION_BUNDLE, FEDERATION_TREE_SHA256, "federation v36"),
        (IDENTITY_BUNDLE, IDENTITY_TREE_SHA256, "exact identity v12"),
    ):
        if tree_digest(directory) != expected:
            raise ConstructionTimelineError(f"frozen {label} tree changed")
    try:
        predecessor_manifest = previous.validate_construction_timeline_bundle(
            PREDECESSOR_BUNDLE,
            definition_path=PREDECESSOR_DEFINITION,
        )
        federation_v36.validate_federation_v36()
        identity_v12.carrier.validate_exact_identity_decision_bundle(
            IDENTITY_BUNDLE
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("frozen input validation failed") from error
    frozen_predecessor = CODEC._json_object(
        CODEC._regular_bytes(
            PREDECESSOR_BUNDLE / MANIFEST_FILENAME, "timeline v8 manifest"
        ),
        "timeline v8 manifest",
    )
    if predecessor_manifest != frozen_predecessor:
        raise ConstructionTimelineError("validated timeline v8 manifest differs")


def _release_labels() -> dict[str, dict[str, str]]:
    raw = CODEC._regular_bytes(OPEN_SEED_RELEASE / "entities.csv", "v87 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v87 entities.csv is not UTF-8") from error
    if len(rows) != 933:
        raise ConstructionTimelineError("v87 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v87 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _v87_source_contract() -> dict[str, str]:
    raw = CODEC._regular_bytes(OPEN_SEED_DEFINITION, "v87 definition")
    if (len(raw), CODEC._sha256_bytes(raw)) != OPEN_SEED_DEFINITION_PIN:
        raise ConstructionTimelineError("frozen v87 definition changed")
    document = CODEC._json_object(raw, "v87 definition")
    inputs = document.get("curated_inputs")
    if not isinstance(inputs, list) or len(inputs) != V87_SELECTED_INPUTS:
        raise ConstructionTimelineError("v87 selected input inventory differs")
    additions = inputs[V86_SELECTED_INPUTS:]
    if tuple(row.get("path") for row in additions) != V87_SOURCE_PATHS:
        raise ConstructionTimelineError("v87 source path contract differs")
    if tuple(open_seed_v87.ADDITION_ORDER) != V87_SOURCE_PATHS:
        raise ConstructionTimelineError("v87 module source order differs")

    source_by_key: dict[str, str] = {}
    lifecycle_contract: set[tuple[str, str, str, str]] = set()
    for item in additions:
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ConstructionTimelineError("v87 source checkpoint differs")
        display = str(item["path"])
        path = ROOT / display
        if CODEC._sha256_file(path) != item["sha256"]:
            raise ConstructionTimelineError(f"v87 source changed: {display}")
        source = CODEC._json_object(CODEC._regular_bytes(path, display), display)
        project = source.get("project")
        lifecycle = source.get("lifecycle")
        evidence = source.get("evidence")
        if (
            not isinstance(project, Mapping)
            or not isinstance(project.get("stable_key"), str)
            or not isinstance(lifecycle, list)
            or len(lifecycle) != 1
            or not isinstance(evidence, list)
            or not evidence
        ):
            raise ConstructionTimelineError(
                f"v87 source is not one-row lifecycle-bearing: {display}"
            )
        event = lifecycle[0]
        if not isinstance(event, Mapping) or event.get("entity") != "project":
            raise ConstructionTimelineError("v87 lifecycle event contract differs")
        stable_key = str(project["stable_key"])
        if stable_key in source_by_key:
            raise ConstructionTimelineError("v87 project source is ambiguous")
        source_by_key[stable_key] = display
        lifecycle_contract.add(
            (
                stable_key,
                str(event["value"]),
                str(event["as_of_date"]),
                str(event["method"]),
            )
        )
    if (
        set(source_by_key) != set(ADDED_PROJECT_KEYS)
        or lifecycle_contract != set(EXPECTED_LIFECYCLE_CONTRACT)
    ):
        raise ConstructionTimelineError("v87 lifecycle accounting differs")
    return source_by_key


def _identity_source_family_contract() -> dict[str, str]:
    raw = CODEC._regular_bytes(
        IDENTITY_BUNDLE / "component-members.csv", "identity v12 component members"
    )
    try:
        rows = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
        selected = {
            row["stable_key"]: row
            for row in rows
            if row.get("release_id") == federation_v36.NEW_RELEASE_ID
            and row.get("stable_key") in ADDED_PROJECT_KEYS
        }
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("identity component members is not UTF-8") from error
    if set(selected) != set(ADDED_PROJECT_KEYS):
        raise ConstructionTimelineError("identity v12 project lineage inventory differs")
    result: dict[str, str] = {}
    for key, row in selected.items():
        family = str(row.get("source_family"))
        if (
            family != EXPECTED_IDENTITY_SOURCE_FAMILIES[key]
            or row.get("component_member_count") != "1"
            or row.get("identity_proof_parent_occurrence_id")
            or row.get("identity_proof_token")
        ):
            raise ConstructionTimelineError("identity v12 singleton lineage differs")
        result[key] = family
    return result


def _full_v87_observations() -> list[dict[str, Any]]:
    _validate_inputs()
    v87_document = CODEC._json_object(
        CODEC._regular_bytes(OPEN_SEED_DEFINITION, "v87 definition"), "v87 definition"
    )
    base = CODEC._json_object(
        CODEC._regular_bytes(open_seed_v87.BASE_DEFINITION, "v86 base definition"),
        "v86 base definition",
    )
    try:
        selected_rows, paths = open_seed_v87.selected_inputs(
            base, recorded_at=OPEN_SEED_RECORDED_AT
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("v87 source selection failed") from error
    if (
        v87_document.get("build")
        != {"as_of": AS_OF, "recorded_at": OPEN_SEED_RECORDED_AT}
        or selected_rows != v87_document.get("curated_inputs")
        or len(paths) != V87_SELECTED_INPUTS
    ):
        raise ConstructionTimelineError("fresh v87 source inventory differs")
    labels = _release_labels()
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v9-db-", dir="/private/tmp"
    ) as temporary:
        try:
            connection = open_seed_v87._build_database(
                base,
                paths,
                Path(temporary) / "atlas.sqlite",
                recorded_at=OPEN_SEED_RECORDED_AT,
            )
        except (OSError, ValueError, RuntimeError, SystemExit) as error:
            raise ConstructionTimelineError("fresh v87 database rebuild failed") from error
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
            raise ConstructionTimelineError("v87 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if len(observations) != FULL_V87_RAW_OBSERVATIONS or len(
        {row["observation_id"] for row in observations}
    ) != len(observations):
        raise ConstructionTimelineError("full v87 lifecycle inventory differs")
    return observations


def _predecessor_observations() -> list[dict[str, str]]:
    rows = CODEC._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("timeline v8 observation inventory differs")
    if CODEC._csv_bytes(rows) != CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME, "v8 observations"
    ):
        raise ConstructionTimelineError("timeline v8 observation bytes differ")
    return rows


def _predecessor_timelines() -> list[dict[str, Any]]:
    rows = CODEC._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("timeline v8 entity inventory differs")
    if b"".join(CODEC._canonical_json_line(row) for row in rows) != CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / TIMELINES_FILENAME, "v8 timelines"
    ):
        raise ConstructionTimelineError("timeline v8 JSONL bytes differ")
    return rows


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    source_by_key = _v87_source_contract()
    identity_families = _identity_source_family_contract()
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
                CODEC._freshness_class(age),
                identity_families[stable_key],
            )
        )
    return tuple(sorted(contract, key=lambda item: (item[1], item[3], item[2])))


def _event_contract_sha256(contract: tuple[tuple[Any, ...], ...]) -> str:
    return CODEC._sha256_bytes(CODEC._canonical_json([list(event) for event in contract]))


def _reconstruct_observations() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = _full_v87_observations()
    predecessor = _predecessor_observations()
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v87 dropped a timeline v8 observation")
    rewrite_count = 0
    for row in predecessor:
        fresh = CODEC._csv_row(full_by_id[row["observation_id"]])
        differences = {
            field for field in OBSERVATION_FIELDS if row[field] != fresh[field]
        }
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v87 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
    if rewrite_count != V87_INHERITED_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError("v87 inherited recorded_at rewrite count differs")

    additions = [
        row for row in full if str(row["observation_id"]) not in predecessor_ids
    ]
    contract = _event_contract(additions)
    if (
        len(additions) != V87_ADDED_OBSERVATIONS
        or {str(row["entity_stable_key"]) for row in additions}
        != set(ADDED_PROJECT_KEYS)
        or _event_contract_sha256(contract) != V87_ADDITION_EVENT_CONTRACT_SHA256
    ):
        raise ConstructionTimelineError("v87 addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids or set(full_by_id) - predecessor_ids != addition_ids:
        raise ConstructionTimelineError("v87 full-to-v8 delta boundary differs")
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
        raise ConstructionTimelineError("timeline v9 observation inventory differs")
    return combined, additions


def _timeline_rows(additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines()
    new_rows = TIMELINE_CARRIER._timeline_rows(additions, as_of=AS_OF)
    if len(new_rows) != V87_ADDED_PROJECTS or any(
        row["format"] != TIMELINE_FORMAT
        or row["schema_version"] != TIMELINE_SCHEMA_VERSION
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] is not False
        or row["latest_observation_persistence_assumed"] is not False
        or row["has_status_change"]
        or row["single_old_observation_current_unknown"]
        for row in new_rows
    ):
        raise ConstructionTimelineError("v87 addition timeline guardrails differ")
    operational = {
        row["entity_stable_key"]
        for row in new_rows
        if row["observations"][-1]["status"] == "operational"
    }
    if operational != OPERATIONAL_CLOSURE_KEYS:
        raise ConstructionTimelineError("v87 operational closure boundary differs")
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("timeline v9 entity collides with timeline v8")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _event_documents(contract: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
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


def _source_family_inventory(
    observations: list[dict[str, Any]], additions: list[dict[str, Any]]
) -> tuple[set[str], set[str], set[str]]:
    row_linked = {str(row["evidence_source_family"]) for row in observations}
    identity_families = set(_identity_source_family_contract().values())
    lineage_aware = row_linked | identity_families
    predecessor_families = {
        row["evidence_source_family"] for row in _predecessor_observations()
    }
    if (
        len(row_linked) != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or len(lineage_aware) != LINEAGE_AWARE_SOURCE_FAMILIES
        or row_linked - predecessor_families != {"riot_platforms_company_news"}
        or lineage_aware - predecessor_families
        != {"databank_facility_pages", "riot_platforms_company_news"}
        or {str(row["entity_stable_key"]) for row in additions}
        != set(ADDED_PROJECT_KEYS)
    ):
        raise ConstructionTimelineError("v9 source-family accounting differs")
    return row_linked, lineage_aware, predecessor_families


def _coverage(
    observations: list[dict[str, Any]],
    additions: list[dict[str, Any]],
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
    row_linked, lineage_aware, predecessor_families = _source_family_inventory(
        observations, additions
    )
    counts = {
        "entities_with_lifecycle_observations": len(timelines),
        "multi_observation_entities": len(multi),
        "raw_lifecycle_observations": len(observations),
        "repeated_status_multi_observation_entities": len(repeated),
        "single_observation_entities": len(single),
        "single_old_observation_entities": len(single_old),
        "source_families": len(lineage_aware),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineError(f"timeline coverage counts differ: {counts}")
    event_contract = _event_contract(additions)
    if _event_contract_sha256(event_contract) != V87_ADDITION_EVENT_CONTRACT_SHA256:
        raise ConstructionTimelineError("v87 coverage event contract differs")
    events = _event_documents(event_contract)
    additions_by_key = {str(event["entity_stable_key"]): event for event in events}
    predecessor_coverage = CODEC._json_object(
        CODEC._regular_bytes(PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v8 coverage"),
        "v8 coverage",
    )
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
        for key in sorted(OPERATIONAL_CLOSURE_KEYS)
    ]
    return {
        "as_of": definition.as_of,
        "counts": counts,
        "current_status_classification_counts": {"unknown": len(timelines)},
        "date_coverage": {
            "latest_observed_date": max(str(row["observed_date"]) for row in observations),
            "oldest_observed_date": min(str(row["observed_date"]) for row in observations),
        },
        "delta": DELTA_CONTRACT,
        "format": COVERAGE_FORMAT,
        "generated_at": definition.generated_at,
        "inherited_v8_delta_operational_lifecycle_closures": predecessor_coverage[
            "v8_delta_operational_lifecycle_closures"
        ],
        "lifecycle_row_linked_source_family_count": len(row_linked),
        "lineage_aware_source_family_count": len(lineage_aware),
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
                Counter(str(row["evidence_source_family"]) for row in observations).items()
            )
        ),
        "source_family_roles": {
            family: {
                "identity_lineage": family
                in set(_identity_source_family_contract().values()),
                "lifecycle_row_evidence": family in row_linked,
            }
            for family in sorted(lineage_aware)
        },
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v9_delta_inference_guardrails": INFERENCE_GUARDRAILS,
        "v9_delta_operational_lifecycle_closures": operational_closures,
        "v87_addition_event_contract_sha256": V87_ADDITION_EVENT_CONTRACT_SHA256,
        "v87_addition_events": events,
        "v87_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
        "v87_delta_new_lineage_source_families": sorted(
            lineage_aware - predecessor_families
        ),
        "v87_delta_new_row_linked_source_families": sorted(
            row_linked - predecessor_families
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v9\n\n"
        "This immutable exact successor preserves all 537 accepted v8 lifecycle "
        "observation rows and all 517 accepted v8 entity-timeline rows byte-for-byte, "
        "then appends exactly four source-scoped project observations first accepted "
        "in open seed v87. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} entities.\n\n"
        "A complete 541-row v87 lifecycle database is rebuilt offline. One hundred "
        "fifty-four v87 recorded_at rewrites are ignored so predecessor recording "
        "lineage is never replaced. Riot's first AMD lease phase has a dated "
        "operational closure on 2026-01-31; that is historical closure only and not "
        "a current-operational claim. Every current status remains unknown.\n\n"
        "Lifecycle rows link to 253 evidence source families. Frozen exact-identity "
        "v12 supplies singleton source lineage for the four new projects, yielding a "
        "254-family lineage-aware union: Riot Platforms company news and DataBank "
        "facility pages are new, while DataBank official LinkedIn was already present. "
        "The ATL5 and ATL6 lifecycle FKs remain their actual LinkedIn evidence; they are "
        "not rewritten to facility-page evidence.\n\n"
        "No current-status persistence, forecast conversion, cross-source identity "
        "merge, unique-site count, satellite or CV promotion, capacity inference, or "
        "missing-milestone interpolation is made. The only checkpoints are the "
        "hash-pinned timeline v8, open seed v87, federation v36, and exact identity v12.\n"
    ).encode("utf-8")


def _source_support_records() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for display in V87_SOURCE_PATHS:
        source = CODEC._json_object(
            CODEC._regular_bytes(ROOT / display, display), display
        )
        evidence = source.get("evidence")
        if not isinstance(evidence, list):
            raise ConstructionTimelineError("v87 supporting evidence differs")
        for row in evidence:
            if not isinstance(row, Mapping):
                raise ConstructionTimelineError("v87 evidence row differs")
            records.append(
                {
                    "evidence_attribution": str(row.get("attribution", "")),
                    "evidence_license": str(row.get("license", "")),
                    "evidence_publisher": str(row.get("publisher", "")),
                    "evidence_source_family": str(row.get("source_family", "")),
                }
            )
    return records


def _attribution(observations: list[dict[str, Any]]) -> bytes:
    by_family: dict[str, dict[str, set[str]]] = {}
    rows: list[Mapping[str, Any]] = [*observations, *_source_support_records()]
    for row in rows:
        record = by_family.setdefault(
            str(row["evidence_source_family"]),
            {"attributions": set(), "licenses": set(), "publishers": set()},
        )
        record["attributions"].add(str(row["evidence_attribution"]))
        record["licenses"].add(str(row["evidence_license"]))
        record["publishers"].add(str(row["evidence_publisher"]))
    if len(by_family) != LINEAGE_AWARE_SOURCE_FAMILIES:
        raise ConstructionTimelineError("attribution source-family inventory differs")
    lines = [
        "Derived only from hash-pinned timeline v8, open seed v87, federation v36, and exact identity v12 inputs.",
        "Every lifecycle row retains its accepted evidence identity and metadata; corroborating v87 evidence appears only in lineage-aware attribution.",
        "Source-family attribution inventory:",
    ]
    for family, values in sorted(by_family.items()):
        lines.append(
            f"- {family} | publishers: {'; '.join(sorted(values['publishers']))} "
            f"| licenses: {'; '.join(sorted(values['licenses']))} "
            f"| attribution: {'; '.join(sorted(values['attributions']))}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _input_manifest_documents() -> dict[str, Any]:
    return {
        "exact_identity_input": {
            "bundle_id": identity_v12.BUNDLE_ID,
            "definition": {
                "bytes": IDENTITY_DEFINITION_PIN[0],
                "file": IDENTITY_DEFINITION.name,
                "sha256": IDENTITY_DEFINITION_PIN[1],
            },
            "manifest": {
                "bytes": IDENTITY_MANIFEST_PIN[0],
                "file": MANIFEST_FILENAME,
                "sha256": IDENTITY_MANIFEST_PIN[1],
            },
            "recorded_at": IDENTITY_RECORDED_AT,
            "tree_sha256": IDENTITY_TREE_SHA256,
        },
        "federation_input": {
            "definition": {
                "bytes": FEDERATION_DEFINITION_PIN[0],
                "file": FEDERATION_DEFINITION.name,
                "sha256": FEDERATION_DEFINITION_PIN[1],
            },
            "generated_at": FEDERATION_GENERATED_AT,
            "index": {
                "bytes": FEDERATION_INDEX_PIN[0],
                "file": "federated-index.json",
                "sha256": FEDERATION_INDEX_PIN[1],
            },
            "manifest": {
                "bytes": FEDERATION_MANIFEST_PIN[0],
                "file": MANIFEST_FILENAME,
                "sha256": FEDERATION_MANIFEST_PIN[1],
            },
            "tree_sha256": FEDERATION_TREE_SHA256,
        },
        "open_seed_input": {
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
        },
        "predecessor_input": {
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
        },
    }


def _prepare_payloads(definition: _Definition) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations, additions = _reconstruct_observations()
    timelines = _timeline_rows(additions)
    coverage = _coverage(observations, additions, timelines, definition)
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
            "sha256": CODEC._sha256_bytes(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": CODEC._sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition.generated_at,
        **_input_manifest_documents(),
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = CODEC._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{CODEC._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _validate_payload_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    observations = CODEC._parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = CODEC._parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = CODEC._regular_bytes(directory / COVERAGE_FILENAME, COVERAGE_FILENAME)
    coverage = CODEC._json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != CODEC._canonical_json(coverage):
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
    timeline_order = [(row.get("entity_stable_key"), row.get("entity_id")) for row in timelines]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(timeline_order):
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
        if not isinstance(nested, list) or timeline.get("observation_count") != len(nested):
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

    predecessor_observations = _predecessor_observations()
    current_by_id = {row["observation_id"]: row for row in observations}
    for row in predecessor_observations:
        inherited = current_by_id.get(row["observation_id"])
        if inherited != row or CODEC._csv_bytes([inherited]) != CODEC._csv_bytes([row]):
            raise ConstructionTimelineError("inherited observation bytes changed")
    predecessor_timelines = _predecessor_timelines()
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    for row in predecessor_timelines:
        inherited = current_by_key.get(row["entity_stable_key"])
        if inherited != row or CODEC._canonical_json_line(inherited) != CODEC._canonical_json_line(row):
            raise ConstructionTimelineError("inherited timeline bytes changed")

    predecessor_ids = {row["observation_id"] for row in predecessor_observations}
    additions = [row for row in observations if row["observation_id"] not in predecessor_ids]
    contract = _event_contract(additions)
    if (
        len(additions) != V87_ADDED_OBSERVATIONS
        or _event_contract_sha256(contract) != V87_ADDITION_EVENT_CONTRACT_SHA256
        or coverage.get("v87_addition_events") != _event_documents(contract)
        or coverage.get("v87_addition_freshness_counts")
        != {"aging_91_365_days": 2, "recent_0_90_days": 2}
    ):
        raise ConstructionTimelineError("published v87 event contract differs")
    if (
        coverage.get("v9_delta_inference_guardrails") != INFERENCE_GUARDRAILS
        or coverage.get("lifecycle_row_linked_source_family_count")
        != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or coverage.get("lineage_aware_source_family_count")
        != LINEAGE_AWARE_SOURCE_FAMILIES
        or coverage.get("v87_delta_new_row_linked_source_families")
        != ["riot_platforms_company_news"]
        or coverage.get("v87_delta_new_lineage_source_families")
        != ["databank_facility_pages", "riot_platforms_company_news"]
    ):
        raise ConstructionTimelineError("v9 inference or source-family boundary differs")
    closures = coverage.get("v9_delta_operational_lifecycle_closures")
    if (
        not isinstance(closures, list)
        or {row.get("entity_stable_key") for row in closures} != OPERATIONAL_CLOSURE_KEYS
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
    if (
        coverage.get("current_status_classification_counts") != {"unknown": 521}
        or coverage.get("observation_entity_kind_counts")
        != {"campus": 83, "project": 458}
        or coverage.get("timeline_entity_kind_counts")
        != {"campus": 83, "project": 438}
        or coverage.get("observation_status_counts", {}).get("operational") != 49
        or coverage.get("observation_status_counts", {}).get("under_construction") != 376
    ):
        raise ConstructionTimelineError("timeline counts or current-status boundary differs")


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
        raise ConstructionTimelineError("timeline generated_at exceeds validation wall clock")
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
            if root.stat(follow_symlinks=False).st_ctime + 0.000_001 < generated.timestamp():
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
    """Validate the closed v9 bundle and optionally replay all accepted inputs."""

    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    definition = _load_definition(definition_path, validation_wall_clock=wall_clock)
    if require_frozen and stat.S_IMODE(definition.path.stat().st_mode) != FROZEN_FILE_MODE:
        raise ConstructionTimelineError("timeline definition must be mode 0444")
    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineError("timeline bundle must be an ordinary directory")
    if require_frozen and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise ConstructionTimelineError("timeline bundle directory must be mode 0555")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineError("timeline bundle file inventory differs")
    for entry in entries:
        CODEC._regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = CODEC._regular_bytes(directory / MANIFEST_FILENAME, MANIFEST_FILENAME)
    manifest = CODEC._json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != CODEC._canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = CODEC._regular_bytes(directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME)
    expected_sidecar = (
        f"{CODEC._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
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
        raw = CODEC._regular_bytes(directory / name, name)
        if files[name] != {"bytes": len(raw), "sha256": CODEC._sha256_bytes(raw)}:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if manifest.get("definition") != {
        "bytes": len(definition.raw),
        "file": DEFINITION.name,
        "sha256": CODEC._sha256_bytes(definition.raw),
    }:
        raise ConstructionTimelineError("timeline definition checkpoint differs")
    expected_inputs = _input_manifest_documents()
    if any(manifest.get(key) != value for key, value in expected_inputs.items()):
        raise ConstructionTimelineError("timeline lineage checkpoint differs")
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


def _bundle_checkpoint(
    definition: Path, bundle: Path, definition_pin: tuple[int, str], manifest_pin: tuple[int, str], tree: str
) -> dict[str, Any]:
    return {
        "bundle_path": f"../{bundle.parent.name}/{bundle.name}",
        "definition": {"path": definition.name, "sha256": definition_pin[1]},
        "expected_bundle_tree_sha256": tree,
        "manifest": {
            "path": f"../{bundle.parent.name}/{bundle.name}/{MANIFEST_FILENAME}",
            "sha256": manifest_pin[1],
        },
    }


def _definition_document() -> dict[str, Any]:
    return {
        "as_of": AS_OF,
        "delta": DELTA_CONTRACT,
        "exact_identity": _bundle_checkpoint(
            IDENTITY_DEFINITION,
            IDENTITY_BUNDLE,
            IDENTITY_DEFINITION_PIN,
            IDENTITY_MANIFEST_PIN,
            IDENTITY_TREE_SHA256,
        ),
        "expected": EXPECTED_COUNTS,
        "federation": _bundle_checkpoint(
            FEDERATION_DEFINITION,
            FEDERATION_BUNDLE,
            FEDERATION_DEFINITION_PIN,
            FEDERATION_MANIFEST_PIN,
            FEDERATION_TREE_SHA256,
        ),
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
        "predecessor": _bundle_checkpoint(
            PREDECESSOR_DEFINITION,
            PREDECESSOR_BUNDLE,
            PREDECESSOR_DEFINITION_PIN,
            PREDECESSOR_MANIFEST_PIN,
            PREDECESSOR_TREE_SHA256,
        ),
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
    while time.time() < target:
        time.sleep(min(0.25, target - time.time()))


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
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


def publish_construction_timeline_v9() -> dict[str, Any]:
    """Privately stage, double-rebuild, freeze, and no-replace publish v9."""

    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise ConstructionTimelineError(f"timeline output parent is invalid: {parent}")
    with _publication_lock():
        for target in (DEFINITION, BUNDLE):
            if target.exists() or target.is_symlink():
                raise ConstructionTimelineError(
                    f"timeline output already exists; refusing overwrite: {target}"
                )
        descriptor, definition_stage_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.private-stage-", dir=DEFINITION.parent
        )
        os.close(descriptor)
        definition_stage = Path(definition_stage_name)
        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.private-stage-", dir=BUNDLE.parent)
        )
        bundle_published = False
        definition_published = False
        try:
            definition_raw = CODEC._canonical_json(_definition_document())
            _write_definition_stage(definition_stage, definition_raw)
            planned_wall_clock = _parse_utc(GENERATED_AT, label="timeline generated_at")
            definition = _load_definition(
                definition_stage, validation_wall_clock=planned_wall_clock
            )
            payloads, manifest = _prepare_payloads(definition)
            replay_payloads, replay_manifest = _prepare_payloads(definition)
            if payloads != replay_payloads or manifest != replay_manifest:
                raise ConstructionTimelineError(
                    "v87 inputs changed or two offline reconstructions differ"
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
            if _latest_stage_time(definition_stage, bundle_stage) > planned_wall_clock.timestamp() + 0.000_001:
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
    """Publish only the reserved v9 definition and bundle paths."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineError("timeline v9 publication paths are reserved")
    return publish_construction_timeline_v9()


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
    "IDENTITY_TREE_SHA256",
    "LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES",
    "LINEAGE_AWARE_SOURCE_FAMILIES",
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
    "TIMELINES_FILENAME",
    "TIMELINE_ID",
    "V87_ADDITION_EVENT_CONTRACT_SHA256",
    "build_construction_timeline_bundle",
    "publish_construction_timeline_v9",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
