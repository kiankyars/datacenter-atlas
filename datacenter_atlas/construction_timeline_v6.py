"""Publish the strict timeline-v5 successor derived only from open seed v73.

The bundle preserves every accepted v5 flat observation and grouped timeline
byte-for-byte. It appends only the five lifecycle observations introduced by
the four official-build records in v73. The two coordinate-only replacements
already carried by v72 are acknowledged and validated as lifecycle-neutral.
Every status remains a dated, last-observed fact; no current status is inferred.
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
from . import construction_timeline_v5 as v5
from . import open_seed_v73
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-21-public-open-v6"
AS_OF = "2026-07-21"
# Set shortly before the one-time publisher is run. Staging must finish first.
GENERATED_AT = "2026-07-21T13:28:20Z"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v6.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v6"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v6.lock"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v73.py"
OPEN_SEED_RECORDED_AT = "2026-07-21T13:15:51Z"
OPEN_SEED_DEFINITION_SHA256 = (
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
OPEN_SEED_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
OPEN_SEED_CORE_SHA256 = (
    "c0343b6ba7c99022e5f436b78ddd9926587a0b2711569148da328d2aa881cfcd"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v5.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v5"
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v5.py"
PREDECESSOR_DEFINITION_SHA256 = (
    "f70f520e3ab887f0efea717c6850cb05dc26ce9b6b0697f96e0e6a9b8670a739"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "aa378cde74d50b6016c5cd040a32a24e044489c0eb0fe9b412450d8abb038dba"
)
PREDECESSOR_TREE_SHA256 = (
    "06ea50e5675c9931459fff09fd8bcfab92ebc3c0d9346fd5f5564fa65fa9641d"
)
PREDECESSOR_CORE_SHA256 = (
    "610833a77516b3747790f001a561583610d259536ee15f66192fa333614a2455"
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v6"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v6"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v6"
SCHEMA_VERSION = 6

# The accepted row schema is retained so inherited JSONL lines remain exact.
TIMELINE_FORMAT = v5.TIMELINE_FORMAT
TIMELINE_SCHEMA_VERSION = v5.TIMELINE_SCHEMA_VERSION
OBSERVATIONS_FILENAME = v5.OBSERVATIONS_FILENAME
TIMELINES_FILENAME = v5.TIMELINES_FILENAME
COVERAGE_FILENAME = v5.COVERAGE_FILENAME
README_FILENAME = v5.README_FILENAME
ATTRIBUTION_FILENAME = v5.ATTRIBUTION_FILENAME
MANIFEST_FILENAME = v5.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = v5.MANIFEST_HASH_FILENAME
BUNDLE_FILES = v5.BUNDLE_FILES
OBSERVATION_FIELDS = v5.OBSERVATION_FIELDS
FROZEN_DIRECTORY_MODE = v5.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = v5.FROZEN_FILE_MODE

SCOPE = dict(v5.SCOPE)

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 462,
    "multi_observation_entities": 17,
    "raw_lifecycle_observations": 479,
    "repeated_status_multi_observation_entities": 4,
    "single_observation_entities": 445,
    "single_old_observation_entities": 27,
    "source_families": 207,
    "status_changing_multi_observation_entities": 13,
}

FULL_V73_RAW_OBSERVATIONS = 479
PREDECESSOR_OBSERVATIONS = 474
PREDECESSOR_TIMELINES = 458
V73_ADDED_OBSERVATIONS = 5
V73_ADDED_PROJECTS = 4
V73_INHERITED_RECORDED_AT_REWRITES_IGNORED = 91

V72_COORDINATE_PROJECT_KEYS = frozenset(
    {
        "curated:nextdc-s4-sydney:early-works",
        "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out",
    }
)
V72_COORDINATE_ONLY_DELTA = {
    "accepted_coordinate_replacements": 2,
    "changed_entity_snapshots": 3,
    "coordinate_project_observations_verified": 2,
    "lifecycle_observations_added": 0,
    "lifecycle_semantic_changes": 0,
    "status_or_current_claims_added": 0,
    "timeline_rows_changed": 0,
}

PROJECT_SOURCE_BY_KEY = {
    "curated:akashi-astana-data-center-campus:phase-1-current-build": (
        "sources/curated-official-2026-07-21-akashi-astana-phase-1-current-build.json"
    ),
    "curated:bichuten-chovar-data-center:initial-container-build": (
        "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json"
    ),
    "curated:icatec-ica-digital-transformation-data-center:"
    "four-storey-technology-center-build": (
        "sources/curated-official-2026-07-21-icatec-ica-current-build.json"
    ),
    "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build": (
        "sources/curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json"
    ),
}

EVENT_CONTRACT_FIELDS = v5.EVENT_CONTRACT_FIELDS

V73_ADDITION_EVENT_CONTRACT = (
    (
        "sources/curated-official-2026-07-21-akashi-astana-phase-1-current-build.json",
        "curated:akashi-astana-data-center-campus:phase-1-current-build",
        "42723311-29cf-5f21-8192-347414b2cd89",
        "2026-07-21",
        "under_construction",
        "authoritative_physical_status_update",
        "ad6f9a56-ffa6-527d-bcd3-a7d8932c31b9",
        "akashi_data_center_project_pages",
        "2026-07-21T12:22:07Z",
        "a2f3f281a66151c90b6a6ea0a089e9cab9361b586f60cde06febb1d49fee6b9f",
        0,
        "recent_0_90_days",
    ),
    (
        "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json",
        "curated:bichuten-chovar-data-center:initial-container-build",
        "b0bc2844-1270-5a99-bf97-2235fe4a3b80",
        "2026-03-31",
        "under_construction",
        "authoritative_physical_status_update",
        "dba73b72-d5b4-5964-97a6-432068e72b00",
        "care_ratings_nepal_releases",
        "2026-07-21T12:22:09Z",
        "45e601838c265494e5816f4b41d5adb943b565f075ca6246d9b77baf85d50b73",
        112,
        "aging_91_365_days",
    ),
    (
        "sources/curated-official-2026-07-21-icatec-ica-current-build.json",
        "curated:icatec-ica-digital-transformation-data-center:"
        "four-storey-technology-center-build",
        "7f5c38b0-d991-54ec-b5d1-563ef11e4b7b",
        "2026-02-12",
        "foundations",
        "authoritative_physical_status_update",
        "1ec5b74c-8ec7-5adc-98ec-4d2df56ad108",
        "peru_gob_pe_region_ica_news",
        "2026-07-21T12:22:10Z",
        "00979a2a34878605fd682a2cde8f925f654bf6cbf18dcb6597df0723d176a0fb",
        159,
        "aging_91_365_days",
    ),
    (
        "sources/curated-official-2026-07-21-icatec-ica-current-build.json",
        "curated:icatec-ica-digital-transformation-data-center:"
        "four-storey-technology-center-build",
        "416e8fce-165b-58c9-ba5a-91acc65f52ce",
        "2026-04-07",
        "under_construction",
        "authoritative_physical_status_update",
        "7db7fb4b-f91a-57e2-9d15-7dd4b28b1d5f",
        "peru_gob_pe_region_ica_news",
        "2026-07-21T12:22:11Z",
        "5d21ed8ba6961f819538a0c2dfdef63d6a2a601c97d259c96c4734455952ea9f",
        105,
        "aging_91_365_days",
    ),
    (
        "sources/curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json",
        "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
        "bd10c0a6-10cc-5c2e-a822-8ce5595ea479",
        "2026-06-30",
        "under_construction",
        "authoritative_physical_status_update",
        "aff4b014-b3dd-5ba0-b90b-ad3cde08f30a",
        "lvrtc_pozitrons_project_pages",
        "2026-07-21T12:22:03Z",
        "4d00948cfc2a582004e38bcee3425c4ea5da5ce8dc31d3da326e6ba0a8b9d9e1",
        21,
        "recent_0_90_days",
    ),
)

DELTA_CONTRACT = {
    "full_v73_raw_lifecycle_observations": FULL_V73_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "recorded_at_values_preserved_from_v5": True,
    "v72_coordinate_only": V72_COORDINATE_ONLY_DELTA,
    "v73_added_lifecycle_observations": V73_ADDED_OBSERVATIONS,
    "v73_added_project_entities": V73_ADDED_PROJECTS,
    "v73_inherited_recorded_at_rewrites_ignored": (
        V73_INHERITED_RECORDED_AT_REWRITES_IGNORED
    ),
}

ConstructionTimelineError = v5.ConstructionTimelineError


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
    return v5._parse_utc(value, label=label)


def _load_definition(
    path_value: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = v5.v3._regular_bytes(path, "timeline definition")
    document = v5.v3._json_object(raw, "timeline definition")
    if raw != v5.v3._canonical_json(document):
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
        raise ConstructionTimelineError("timeline v6 definition contract differs")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if wall_clock.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    generated = _parse_utc(document["generated_at"], label="timeline generated_at")
    if generated <= _parse_utc(OPEN_SEED_RECORDED_AT, label="v73 recorded_at"):
        raise ConstructionTimelineError("timeline generated_at must follow v73")
    if generated > wall_clock.astimezone(timezone.utc):
        raise ConstructionTimelineError("timeline generated_at exceeds validation wall clock")

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
    seed_definition_display, seed_definition_digest = v5.v3._checkpoint(
        open_seed["definition"], "open seed definition"
    )
    seed_manifest_display, seed_manifest_digest = v5.v3._checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    predecessor_definition_display, predecessor_definition_digest = v5.v3._checkpoint(
        predecessor["definition"], "predecessor definition"
    )
    predecessor_manifest_display, predecessor_manifest_digest = v5.v3._checkpoint(
        predecessor["manifest"], "predecessor manifest"
    )
    seed_definition = v5.v3._resolve(
        path, seed_definition_display, "open seed definition"
    )
    seed_release = v5.v3._resolve(path, open_seed["release_path"], "open seed release")
    seed_manifest = v5.v3._resolve(path, seed_manifest_display, "open seed manifest")
    predecessor_definition = v5.v3._resolve(
        path, predecessor_definition_display, "predecessor definition"
    )
    predecessor_bundle = v5.v3._resolve(
        path, predecessor["bundle_path"], "predecessor bundle"
    )
    predecessor_manifest = v5.v3._resolve(
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
        raise ConstructionTimelineError("accepted v73 or timeline v5 pins differ")
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
        if v5.v3._sha256_file(checkpoint) != digest:
            raise ConstructionTimelineError(f"frozen input changed: {checkpoint}")
    if tree_digest(definition.open_seed_release) != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen open seed v73 tree changed")
    if tree_digest(definition.predecessor_bundle) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v5 tree changed")
    try:
        seed_manifest = open_seed_v73.validate_open_seed_v73(
            definition.open_seed_definition,
            definition.open_seed_release,
        )
        predecessor_manifest = v5.validate_construction_timeline_bundle(
            definition.predecessor_bundle,
            definition_path=definition.predecessor_definition,
            verify_inputs=True,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("frozen input validation failed") from error
    frozen_seed_manifest = v5.v3._json_object(
        v5.v3._regular_bytes(
            definition.open_seed_release / MANIFEST_FILENAME, "v73 manifest"
        ),
        "v73 manifest",
    )
    frozen_predecessor_manifest = v5.v3._json_object(
        v5.v3._regular_bytes(
            definition.predecessor_bundle / MANIFEST_FILENAME, "timeline v5 manifest"
        ),
        "timeline v5 manifest",
    )
    if (
        seed_manifest != frozen_seed_manifest
        or predecessor_manifest != frozen_predecessor_manifest
    ):
        raise ConstructionTimelineError("validated frozen input manifest differs")


def _release_labels(release: Path) -> dict[str, dict[str, str]]:
    raw = v5.v3._regular_bytes(release / "entities.csv", "v73 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v73 entities.csv is not UTF-8") from error
    if len(rows) != 818:
        raise ConstructionTimelineError("v73 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v73 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _full_v73_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_inputs(definition)
    v73_document = v5.v3._json_object(
        v5.v3._regular_bytes(definition.open_seed_definition, "v73 definition"),
        "v73 definition",
    )
    base = v5.v3._json_object(
        v5.v3._regular_bytes(open_seed_v73.BASE_DEFINITION, "v72 base definition"),
        "v72 base definition",
    )
    try:
        selected_rows, paths = open_seed_v73.selected_inputs(
            base,
            recorded_at=OPEN_SEED_RECORDED_AT,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError("v73 source selection failed") from error
    if (
        v73_document.get("build")
        != {"as_of": AS_OF, "recorded_at": OPEN_SEED_RECORDED_AT}
        or selected_rows != v73_document.get("curated_inputs")
        or len(paths) != 397
    ):
        raise ConstructionTimelineError("fresh v73 source inventory differs")
    labels = _release_labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v6-db-",
        dir="/private/tmp",
    ) as temporary:
        try:
            connection = open_seed_v73._build_database(
                base,
                paths,
                Path(temporary) / "atlas.sqlite",
                recorded_at=OPEN_SEED_RECORDED_AT,
            )
        except (OSError, ValueError, RuntimeError, SystemExit) as error:
            raise ConstructionTimelineError("fresh v73 database rebuild failed") from error
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
            raise ConstructionTimelineError("v73 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if (
        len(observations) != FULL_V73_RAW_OBSERVATIONS
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("full v73 lifecycle inventory differs")
    return observations


def _predecessor_observations(definition: _Definition) -> list[dict[str, str]]:
    rows = v5.v3._parse_csv(definition.predecessor_bundle / OBSERVATIONS_FILENAME)
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("timeline v5 observation inventory differs")
    if v5.v3._csv_bytes(rows) != v5.v3._regular_bytes(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME, "v5 observations"
    ):
        raise ConstructionTimelineError("timeline v5 observation bytes differ")
    return rows


def _predecessor_timelines(definition: _Definition) -> list[dict[str, Any]]:
    rows = v5.v3._parse_jsonl(definition.predecessor_bundle / TIMELINES_FILENAME)
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("timeline v5 entity inventory differs")
    if b"".join(v5.v3._canonical_json_line(row) for row in rows) != v5.v3._regular_bytes(
        definition.predecessor_bundle / TIMELINES_FILENAME, "v5 timelines"
    ):
        raise ConstructionTimelineError("timeline v5 JSONL bytes differ")
    return rows


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    as_of = date.fromisoformat(AS_OF)
    contract = []
    for row in rows:
        stable_key = str(row["entity_stable_key"])
        age = (as_of - date.fromisoformat(str(row["observed_date"]))).days
        contract.append(
            (
                PROJECT_SOURCE_BY_KEY[stable_key],
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
                v5.v3._freshness_class(age),
            )
        )
    return tuple(sorted(contract, key=lambda item: (item[1], item[3], item[2])))


def _reconstruct_observations(
    definition: _Definition,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = _full_v73_observations(definition)
    predecessor = _predecessor_observations(definition)
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v73 dropped a timeline v5 observation")
    rewrite_count = 0
    coordinate_rows = 0
    for row in predecessor:
        fresh = v5.v3._csv_row(full_by_id[row["observation_id"]])
        differences = {
            field for field in OBSERVATION_FIELDS if row[field] != fresh[field]
        }
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v73 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
        if row["entity_stable_key"] in V72_COORDINATE_PROJECT_KEYS:
            coordinate_rows += 1
            if differences != {"recorded_at"}:
                raise ConstructionTimelineError(
                    "v72 coordinate-only lifecycle neutrality differs"
                )
    if rewrite_count != V73_INHERITED_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError("v73 inherited recorded_at rewrite count differs")
    if coordinate_rows != V72_COORDINATE_ONLY_DELTA[
        "coordinate_project_observations_verified"
    ]:
        raise ConstructionTimelineError("v72 coordinate observation inventory differs")

    additions = [row for row in full if row["entity_stable_key"] in PROJECT_SOURCE_BY_KEY]
    if (
        len(additions) != V73_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in additions}) != V73_ADDED_PROJECTS
        or _event_contract(additions) != V73_ADDITION_EVENT_CONTRACT
    ):
        raise ConstructionTimelineError("v73 addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids:
        raise ConstructionTimelineError("v73 addition collides with timeline v5")
    if set(full_by_id) - predecessor_ids != addition_ids:
        raise ConstructionTimelineError("v73 full-to-v5 delta boundary differs")
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
        raise ConstructionTimelineError("timeline v6 observation inventory differs")
    return combined, additions


def _timeline_rows(
    definition: _Definition,
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines(definition)
    new_rows = carrier._timeline_rows(additions, as_of=AS_OF)
    if (
        len(new_rows) != V73_ADDED_PROJECTS
        or any(
            row["format"] != TIMELINE_FORMAT
            or row["schema_version"] != TIMELINE_SCHEMA_VERSION
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] is not False
            or row["latest_observation_persistence_assumed"] is not False
            for row in new_rows
        )
    ):
        raise ConstructionTimelineError("v73 addition timeline guardrails differ")
    icatec_key = (
        "curated:icatec-ica-digital-transformation-data-center:"
        "four-storey-technology-center-build"
    )
    changing_keys = {row["entity_stable_key"] for row in new_rows if row["has_status_change"]}
    if changing_keys != {icatec_key}:
        raise ConstructionTimelineError("v73 status-changing timeline boundary differs")
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("timeline v6 entity collides with timeline v5")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _event_documents() -> list[dict[str, Any]]:
    documents = []
    for event in V73_ADDITION_EVENT_CONTRACT:
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
        raise ConstructionTimelineError(f"timeline coverage counts differ: {counts}")
    events = _event_documents()
    predecessor_coverage = v5.v3._json_object(
        v5.v3._regular_bytes(PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v5 coverage"),
        "v5 coverage",
    )
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
            "timeline_id": v5.TIMELINE_ID,
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
        "stt_johor_historical_only": predecessor_coverage[
            "stt_johor_historical_only"
        ],
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v72_coordinate_only_delta": {
            **V72_COORDINATE_ONLY_DELTA,
            "current_construction_claim": False,
            "current_status_classification": "unknown",
            "project_keys": sorted(V72_COORDINATE_PROJECT_KEYS),
            "status_semantics": "no_lifecycle_delta",
        },
        "v73_addition_events": events,
        "v73_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v6\n\n"
        "This immutable exact successor preserves all 474 accepted v5 lifecycle "
        "observations and all 458 accepted v5 entity-timeline rows byte-for-byte, "
        "then appends the five raw v73 observations on four new project identities. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} source-scoped entities.\n\n"
        "A complete 479-row v73 lifecycle database is rebuilt offline. Ninety-one "
        "v73 recorded_at rewrites never replace the predecessor's accepted recording "
        "lineage. V72's two accepted coordinate-only replacements change three entity "
        "snapshots but add no lifecycle fact, status, or timeline-row mutation. The "
        "timeline schema does not carry coordinates.\n\n"
        "Every lifecycle status remains a dated last-observed fact. Current status is "
        "unknown, current construction is never claimed, and the latest observation "
        "is never assumed to persist. ICATEC's foundations and later construction "
        "observations form a dated status-changing sequence, not a current-status "
        "claim. STT Johor remains stale and historical only. Old starts without later "
        "physical evidence remain current-unknown.\n\n"
        "Permits, forecasts, planned dates, satellite or CV review, and missing "
        "milestones are not promoted or interpolated into physical construction. "
        "Cross-source identities remain unresolved and unique physical sites remain "
        "null. Only the hash-pinned v5 timeline and v73 open seed are checkpoints.\n"
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
        "Derived only from the hash-pinned construction timeline v5 and open seed v73 inputs.",
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
        COVERAGE_FILENAME: v5.v3._canonical_json(coverage),
        OBSERVATIONS_FILENAME: v5.v3._csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: b"".join(
            v5.v3._canonical_json_line(row) for row in timelines
        ),
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw),
            "file": DEFINITION.name,
            "sha256": v5.v3._sha256_bytes(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": v5.v3._sha256_bytes(raw)}
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
                "bytes": (
                    definition.open_seed_release / MANIFEST_FILENAME
                ).stat().st_size,
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
                "bytes": (
                    definition.predecessor_bundle / MANIFEST_FILENAME
                ).stat().st_size,
                "file": MANIFEST_FILENAME,
                "sha256": PREDECESSOR_MANIFEST_SHA256,
            },
            "timeline_id": v5.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = v5.v3._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{v5.v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _validate_payload_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    observations = v5.v3._parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = v5.v3._parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = v5.v3._regular_bytes(directory / COVERAGE_FILENAME, COVERAGE_FILENAME)
    coverage = v5.v3._json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != v5.v3._canonical_json(coverage):
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
        if not isinstance(nested, list) or timeline.get("observation_count") != len(nested):
            raise ConstructionTimelineError("timeline observation accounting differs")
        flattened_ids.extend(str(item["observation_id"]) for item in nested)
    if sorted(flattened_ids) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineError("flat and grouped observation inventories differ")
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
    predecessor_rows = v5.v3._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    current_by_id = {row["observation_id"]: row for row in observations}
    if any(current_by_id.get(row["observation_id"]) != row for row in predecessor_rows):
        raise ConstructionTimelineError("inherited observation semantics changed")
    predecessor_timelines = v5.v3._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    if any(
        current_by_key.get(row["entity_stable_key"]) != row
        for row in predecessor_timelines
    ):
        raise ConstructionTimelineError("inherited timeline semantics changed")
    additions = [
        row for row in observations if row["entity_stable_key"] in PROJECT_SOURCE_BY_KEY
    ]
    if _event_contract(additions) != V73_ADDITION_EVENT_CONTRACT:
        raise ConstructionTimelineError("published v73 event contract differs")
    coordinate_delta = coverage.get("v72_coordinate_only_delta")
    if not isinstance(coordinate_delta, Mapping) or coordinate_delta != {
        **V72_COORDINATE_ONLY_DELTA,
        "current_construction_claim": False,
        "current_status_classification": "unknown",
        "project_keys": sorted(V72_COORDINATE_PROJECT_KEYS),
        "status_semantics": "no_lifecycle_delta",
    }:
        raise ConstructionTimelineError("v72 coordinate-only coverage differs")
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
    """Validate the closed v6 bundle and optionally replay both accepted inputs."""

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
        v5.v3._regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = v5.v3._regular_bytes(directory / MANIFEST_FILENAME, MANIFEST_FILENAME)
    manifest = v5.v3._json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != v5.v3._canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = v5.v3._regular_bytes(
        directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME
    )
    expected_sidecar = (
        f"{v5.v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
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
        raw = v5.v3._regular_bytes(directory / name, name)
        if files[name] != {"bytes": len(raw), "sha256": v5.v3._sha256_bytes(raw)}:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if manifest.get("definition") != {
        "bytes": len(definition.raw),
        "file": DEFINITION.name,
        "sha256": v5.v3._sha256_bytes(definition.raw),
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
    v5._discard_stage(stage)


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
        except BaseException as error:  # pragma: no cover - catastrophic filesystem path
            errors.append(f"definition rollback failed: {error}")
    if bundle_published:
        try:
            promote_noreplace(BUNDLE, bundle_stage)
        except BaseException as error:  # pragma: no cover - catastrophic filesystem path
            errors.append(f"bundle rollback failed: {error}")
    if errors:
        raise ConstructionTimelineError("; ".join(errors))


def publish_construction_timeline_v6() -> dict[str, Any]:
    """Privately stage, double-rebuild, freeze, and no-replace publish v6."""

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
            definition_raw = v5.v3._canonical_json(_definition_document())
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
                    "v73 inputs changed or two offline timeline reconstructions differ"
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
    """Publish only the reserved v6 definition and bundle paths."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineError("timeline v6 publication paths are reserved")
    return publish_construction_timeline_v6()


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
    "PROJECT_SOURCE_BY_KEY",
    "SCHEMA_VERSION",
    "SCOPE",
    "TIMELINES_FILENAME",
    "TIMELINE_FORMAT",
    "TIMELINE_ID",
    "TIMELINE_SCHEMA_VERSION",
    "V72_COORDINATE_ONLY_DELTA",
    "V72_COORDINATE_PROJECT_KEYS",
    "V73_ADDITION_EVENT_CONTRACT",
    "build_construction_timeline_bundle",
    "publish_construction_timeline_v6",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
