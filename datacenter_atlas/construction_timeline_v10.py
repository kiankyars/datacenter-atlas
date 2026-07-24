"""Publish timeline v10 as the exact 30-observation successor to v9.

Every accepted v9 observation and grouped timeline row is retained exactly.
The only additions are the internal lifecycle observations first accepted by
open seeds v88 through v92.  Lifecycle states remain dated observations; this
module never promotes the latest state to a current-status assertion.
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

from . import construction_timeline_v9 as previous
from . import open_seed_v88, open_seed_v89, open_seed_v90, open_seed_v91, open_seed_v92
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
CODEC = previous.CODEC
TIMELINE_CARRIER = previous.TIMELINE_CARRIER

TIMELINE_ID = "2026-07-21-public-open-v10"
AS_OF = "2026-07-22"
# Reserved one-time publication instant. Private staging must finish first.
GENERATED_AT = "2026-07-22T02:20:00Z"

DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v10.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v10"
PUBLICATION_LOCK = ROOT / ".construction-timeline-v10.lock"

PREDECESSOR_DEFINITION = previous.DEFINITION
PREDECESSOR_BUNDLE = previous.BUNDLE
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v9.py"
PREDECESSOR_DEFINITION_PIN = (
    3_981,
    "fe5d4ff2d842e00911ffd352b6d6416e9164a00b03950ef33fe88927a4e7eb35",
)
PREDECESSOR_MANIFEST_PIN = (
    5_094,
    "d4ce768af05b6a5ea0a4b955f5fb2a3a38dad98b5fa383655d762491982e0fae",
)
PREDECESSOR_TREE_SHA256 = (
    "de8ddc533922852ee39e901d01552174bc2367fe8532ebf065bb5389f577f227"
)
PREDECESSOR_CORE_PIN = (
    71_108,
    "d242575beb38fc053a3835b74f12abb7163b0da9237f7e7376fc83f8b548fd2a",
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
    added_observations: int

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
        88,
        open_seed_v88,
        "2026-07-22T00:43:03Z",
        (104_159, "7267e71dc26581eb8f62bf11525475c3ccc732494c4cca0cea58c0f30b0232da"),
        (15_706, "63bdeac96b5f3cebac092a63cff40de2d928d0643d42fe5b041fd649fc9955e0"),
        "aae34cbd2b8111a498ef529b08d0be6937c837b70025bdba6c097735b606073e",
        (51_579, "9c2494cf18ac4043093e4958086292063dc09169c1d2cc6c56931ac977065d1d"),
        5,
    ),
    _ReleaseSpec(
        89,
        open_seed_v89,
        "2026-07-22T00:57:44Z",
        (105_962, "1c9be663976b1b5e93f31868df73f76e66498f14ef9eff157baefb8144b8289b"),
        (15_707, "07f2f521f365b4427c08a7393f72977a68137aa87f9ea015ccf480cac455f9b2"),
        "83b721b2066c3be6cbf3cf3bfb255abb8ed4427ad5ebd17da8dcc5214551fdad",
        (48_914, "feb320a1345f114a67ca2f083b9ef20bd9a1e7d3af727e60c25671cbecd132e8"),
        9,
    ),
    _ReleaseSpec(
        90,
        open_seed_v90,
        "2026-07-22T01:16:53Z",
        (107_554, "3e224d0560e7f82fc31f7bdf6eb6b723ce50ad8423e2296de8c509b75c0fbdda"),
        (15_902, "40be71c613c74e4e843c5c60ad85ce172c206f72350df5a0996b7e971ca54b66"),
        "18cda7d054789dde956a393959cde79349f835927b1e757da364e15d974b78f3",
        (48_981, "e462230948288519524f84b5a278be9c4fdaa52b672ca4949a6b01cc866087e1"),
        7,
    ),
    _ReleaseSpec(
        91,
        open_seed_v91,
        "2026-07-22T01:33:29Z",
        (108_188, "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a"),
        (15_954, "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9"),
        "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e",
        (49_982, "b1fc8dcfa3dabefd97ea599a6c9caa2e32dcecbf0970b81031320ee3c8f77884"),
        3,
    ),
    _ReleaseSpec(
        92,
        open_seed_v92,
        "2026-07-22T02:00:23Z",
        (109_851, "2dab6d4a4bdac34f248268f9f2973ccac88b7fe25deb78b10cf5e44c11990516"),
        (16_558, "3ac9a48eeb121e6ac8a462fb2d99de1a7f2267c6cf9f6b7bd4b74d2b74a25fd7"),
        "52bdbd5ea299dbd845adfe8e05f739894bff914107ae8fec341551bdb800034b",
        (69_392, "93a3ba71eac30f455a5d5258096b236e3078c4ec75400e141f6e6b1803c56b7a"),
        6,
    ),
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v10"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v10"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v10"
SCHEMA_VERSION = 10

# The row schemas stay frozen so inherited rows can remain exact.
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
    "entities_with_lifecycle_observations": 550,
    "multi_observation_entities": 21,
    "raw_lifecycle_observations": 571,
    "repeated_status_multi_observation_entities": 7,
    "single_observation_entities": 529,
    "single_old_observation_entities": 35,
    "source_families": 270,
    "status_changing_multi_observation_entities": 14,
}

PREDECESSOR_OBSERVATIONS = 541
PREDECESSOR_TIMELINES = 521
ADDED_OBSERVATIONS = 30
ADDED_PROJECTS = 29
RELEASE_ADDITION_COUNTS = {
    spec.release_id: spec.added_observations for spec in RELEASE_SPECS
}
SABEY_AUSTIN_KEY = (
    "curated:sabey-sdc-austin-round-rock-campus:building-b-current-build"
)
ADDITION_EVENT_CONTRACT_SHA256 = (
    "499becdbe98bd94eb564a0c2ed211c92e34b7535a70fbb5f93464cecb078f031"
)
LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES = 269
LINEAGE_AWARE_SOURCE_FAMILIES = 270

INFERENCE_GUARDRAILS = {
    "capacity_inferences": 0,
    "cross_source_identity_merges": 0,
    "current_status_persistence_claims": 0,
    "forecast_conversions": 0,
    "lifecycle_valid_to_rewrites": 0,
    "satellite_or_cv_promotions": 0,
    "unique_physical_site_claims": 0,
}

DELTA_CONTRACT = {
    "added_lifecycle_observations": ADDED_OBSERVATIONS,
    "added_project_entities": ADDED_PROJECTS,
    "append_only_predecessor": previous.TIMELINE_ID,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "open_seed_release_additions": RELEASE_ADDITION_COUNTS,
    "predecessor_rows_preserved_exactly": True,
    "raw_lifecycle_observations": EXPECTED_COUNTS["raw_lifecycle_observations"],
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
            "path": spec.definition.name,
            "sha256": spec.definition_pin[1],
        },
        "expected_added_lifecycle_observations": spec.added_observations,
        "expected_release_tree_sha256": spec.tree_sha256,
        "manifest": {
            "bytes": spec.manifest_pin[0],
            "path": f"../releases/{spec.release.name}/{MANIFEST_FILENAME}",
            "sha256": spec.manifest_pin[1],
        },
        "recorded_at": spec.recorded_at,
        "release_id": spec.release_id,
        "release_path": f"../releases/{spec.release.name}",
    }


def _definition_document() -> dict[str, Any]:
    return {
        "as_of": AS_OF,
        "delta": DELTA_CONTRACT,
        "expected": EXPECTED_COUNTS,
        "format": DEFINITION_FORMAT,
        "generated_at": GENERATED_AT,
        "open_seed_inputs": [_release_checkpoint(spec) for spec in RELEASE_SPECS],
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
    if document != _definition_document():
        raise ConstructionTimelineError("timeline v10 definition contract differs")
    wall = validation_wall_clock or datetime.now(timezone.utc)
    if wall.tzinfo is None:
        raise ConstructionTimelineError("validation wall clock must include a timezone")
    generated = _parse_utc(document["generated_at"], label="timeline generated_at")
    if generated <= max(
        _parse_utc(spec.recorded_at, label=f"open seed v{spec.version} recorded_at")
        for spec in RELEASE_SPECS
    ):
        raise ConstructionTimelineError("timeline generated_at must follow all inputs")
    if generated > wall.astimezone(timezone.utc):
        raise ConstructionTimelineError("timeline generated_at exceeds validation wall clock")
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        expected=EXPECTED_COUNTS,
    )


def _validate_input_pins() -> None:
    pins = {
        PREDECESSOR_DEFINITION: PREDECESSOR_DEFINITION_PIN,
        PREDECESSOR_BUNDLE / MANIFEST_FILENAME: PREDECESSOR_MANIFEST_PIN,
        PREDECESSOR_CORE: PREDECESSOR_CORE_PIN,
    }
    for spec in RELEASE_SPECS:
        pins[spec.definition] = spec.definition_pin
        pins[spec.release / MANIFEST_FILENAME] = spec.manifest_pin
        pins[spec.core] = spec.core_pin
    for path, expected in pins.items():
        if _file_pin(path) != expected:
            raise ConstructionTimelineError(f"frozen input changed: {path}")
    if tree_digest(PREDECESSOR_BUNDLE) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v9 tree changed")
    for spec in RELEASE_SPECS:
        if tree_digest(spec.release) != spec.tree_sha256:
            raise ConstructionTimelineError(
                f"frozen open seed v{spec.version} tree changed"
            )
    predecessor_manifest = previous.validate_construction_timeline_bundle(
        PREDECESSOR_BUNDLE,
        definition_path=PREDECESSOR_DEFINITION,
    )
    frozen = CODEC._json_object(
        CODEC._regular_bytes(
            PREDECESSOR_BUNDLE / MANIFEST_FILENAME, "timeline v9 manifest"
        ),
        "timeline v9 manifest",
    )
    if predecessor_manifest != frozen:
        raise ConstructionTimelineError("validated timeline v9 manifest differs")


def _predecessor_observations() -> list[dict[str, str]]:
    rows = CODEC._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    raw = CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME, "v9 observations"
    )
    if len(rows) != PREDECESSOR_OBSERVATIONS or CODEC._csv_bytes(rows) != raw:
        raise ConstructionTimelineError("timeline v9 observation bytes differ")
    return rows


def _predecessor_timelines() -> list[dict[str, Any]]:
    rows = CODEC._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    raw = CODEC._regular_bytes(PREDECESSOR_BUNDLE / TIMELINES_FILENAME, "v9 timelines")
    if (
        len(rows) != PREDECESSOR_TIMELINES
        or b"".join(CODEC._canonical_json_line(row) for row in rows) != raw
    ):
        raise ConstructionTimelineError("timeline v9 grouped timeline bytes differ")
    return rows


def _source_path_contract(spec: _ReleaseSpec) -> dict[tuple[str, str, str, str], str]:
    result: dict[tuple[str, str, str, str], str] = {}
    for display in spec.module.ADDITION_ORDER:
        document = CODEC._json_object(
            CODEC._regular_bytes(ROOT / display, display), display
        )
        project = document.get("project")
        lifecycle = document.get("lifecycle")
        if not isinstance(project, Mapping) or not isinstance(lifecycle, list):
            raise ConstructionTimelineError(f"open seed v{spec.version} source differs")
        stable_key = str(project.get("stable_key"))
        for event in lifecycle:
            if not isinstance(event, Mapping) or event.get("entity") != "project":
                raise ConstructionTimelineError("lifecycle source contract differs")
            key = (
                stable_key,
                str(event.get("value")),
                str(event.get("as_of_date")),
                str(event.get("method")),
            )
            if key in result:
                raise ConstructionTimelineError("lifecycle source event collides")
            result[key] = str(display)
    expected = set(spec.module.LIFECYCLE_CONTRACT)
    if set(result) != expected or len(result) != spec.added_observations:
        raise ConstructionTimelineError(
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
        raise ConstructionTimelineError(
            f"open seed v{spec.version} entities are not UTF-8"
        ) from error
    labels = {row["entity_id"]: row for row in rows}
    if len(labels) != len(rows):
        raise ConstructionTimelineError(
            f"open seed v{spec.version} entity labels collide"
        )
    return labels


def _release_additions(
    spec: _ReleaseSpec,
    temporary_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    definition = CODEC._json_object(
        CODEC._regular_bytes(spec.definition, f"open seed v{spec.version} definition"),
        f"open seed v{spec.version} definition",
    )
    base = CODEC._json_object(
        CODEC._regular_bytes(
            spec.module.BASE_DEFINITION,
            f"open seed v{spec.version} base definition",
        ),
        f"open seed v{spec.version} base definition",
    )
    if definition.get("build") != {"as_of": spec.module.AS_OF, "recorded_at": spec.recorded_at}:
        raise ConstructionTimelineError(
            f"open seed v{spec.version} recorded-at contract differs"
        )
    try:
        selected, paths = spec.module.selected_inputs(
            base,
            recorded_at=spec.recorded_at,
        )
        if selected != definition.get("curated_inputs"):
            raise ConstructionTimelineError(
                f"open seed v{spec.version} selected inputs differ"
            )
        connection = spec.module._build_database(
            base,
            paths,
            temporary_root / f"open-seed-v{spec.version}.sqlite",
            recorded_at=spec.recorded_at,
        )
    except (OSError, ValueError, RuntimeError, SystemExit) as error:
        raise ConstructionTimelineError(
            f"open seed v{spec.version} lifecycle rebuild failed"
        ) from error
    source_paths = _source_path_contract(spec)
    labels = _release_labels(spec)
    contract = set(spec.module.LIFECYCLE_CONTRACT)
    rows: list[dict[str, Any]] = []
    provenance: dict[str, tuple[str, str]] = {}
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
    found_contract: set[tuple[str, str, str, str]] = set()
    for raw_row in raw_rows:
        row = dict(raw_row)
        event = (
            str(row["entity_stable_key"]),
            str(row["status"]),
            str(row["observed_date"]),
            str(row["method"]),
        )
        if event not in contract:
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
            raise ConstructionTimelineError(
                f"open seed v{spec.version} lifecycle label or clock differs"
            )
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        selected_row = {field: row[field] for field in OBSERVATION_FIELDS}
        observation_id = str(row["observation_id"])
        if observation_id in provenance:
            raise ConstructionTimelineError("release lifecycle observation collides")
        rows.append(selected_row)
        provenance[observation_id] = (spec.release_id, source_paths[event])
        found_contract.add(event)
    if (
        found_contract != contract
        or len(rows) != spec.added_observations
        or len(provenance) != len(rows)
    ):
        raise ConstructionTimelineError(
            f"open seed v{spec.version} lifecycle delta differs"
        )
    return rows, provenance


def _reconstruct_observations() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[str, str]]
]:
    _validate_input_pins()
    predecessor = _predecessor_observations()
    predecessor_ids = {row["observation_id"] for row in predecessor}
    additions: list[dict[str, Any]] = []
    provenance: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v10-db-", dir="/private/tmp"
    ) as temporary:
        temporary_root = Path(temporary)
        for spec in RELEASE_SPECS:
            rows, release_provenance = _release_additions(spec, temporary_root)
            additions.extend(rows)
            if provenance.keys() & release_provenance.keys():
                raise ConstructionTimelineError("cross-release observation collision")
            provenance.update(release_provenance)
    addition_ids = {str(row["observation_id"]) for row in additions}
    if (
        len(additions) != ADDED_OBSERVATIONS
        or len(addition_ids) != ADDED_OBSERVATIONS
        or len({str(row["entity_stable_key"]) for row in additions}) != ADDED_PROJECTS
        or predecessor_ids & addition_ids
        or set(provenance) != addition_ids
    ):
        raise ConstructionTimelineError("timeline v10 append boundary differs")
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
        raise ConstructionTimelineError("timeline v10 addition event contract differs")
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
        raise ConstructionTimelineError("timeline v10 observation inventory differs")
    return combined, additions, provenance


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
    return CODEC._sha256_bytes(CODEC._canonical_json([list(row) for row in contract]))


def _event_documents(contract: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    result = []
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


def _timeline_rows(additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines()
    new_rows = TIMELINE_CARRIER._timeline_rows(additions, as_of=AS_OF)
    changing = {row["entity_stable_key"] for row in new_rows if row["has_status_change"]}
    multi = {row["entity_stable_key"] for row in new_rows if row["has_multiple_observations"]}
    if (
        len(new_rows) != ADDED_PROJECTS
        or changing != {SABEY_AUSTIN_KEY}
        or multi != {SABEY_AUSTIN_KEY}
        or sum(row["single_old_observation_current_unknown"] for row in new_rows) != 6
        or any(
            row["format"] != TIMELINE_FORMAT
            or row["schema_version"] != TIMELINE_SCHEMA_VERSION
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] is not False
            or row["latest_observation_persistence_assumed"] is not False
            for row in new_rows
        )
        or any(
            item["status"] == "operational"
            for row in new_rows
            for item in row["observations"]
        )
    ):
        raise ConstructionTimelineError("timeline v10 grouped addition contract differs")
    austin = next(row for row in new_rows if row["entity_stable_key"] == SABEY_AUSTIN_KEY)
    if [item["status"] for item in austin["observations"]] != [
        "under_construction",
        "shell",
    ]:
        raise ConstructionTimelineError("Sabey Austin lifecycle history differs")
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    new_keys = {row["entity_stable_key"] for row in new_rows}
    if predecessor_keys & new_keys:
        raise ConstructionTimelineError("timeline v10 entity collides with timeline v9")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _source_family_state(
    observations: list[dict[str, Any]],
) -> tuple[set[str], set[str], dict[str, dict[str, bool]]]:
    predecessor_coverage = CODEC._json_object(
        CODEC._regular_bytes(PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v9 coverage"),
        "v9 coverage",
    )
    inherited_roles = predecessor_coverage.get("source_family_roles")
    if not isinstance(inherited_roles, Mapping) or len(inherited_roles) != 254:
        raise ConstructionTimelineError("timeline v9 source-family lineage differs")
    row_linked = {str(row["evidence_source_family"]) for row in observations}
    lineage = set(inherited_roles) | row_linked
    if (
        len(row_linked) != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or len(lineage) != LINEAGE_AWARE_SOURCE_FAMILIES
    ):
        raise ConstructionTimelineError("timeline v10 source-family accounting differs")
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
    single_old = [row for row in single if row["single_old_observation_current_unknown"]]
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
        raise ConstructionTimelineError(f"timeline v10 coverage counts differ: {counts}")
    contract = _event_contract(additions, provenance)
    digest = _event_contract_sha256(contract)
    if ADDITION_EVENT_CONTRACT_SHA256 != "TO_FILL" and digest != ADDITION_EVENT_CONTRACT_SHA256:
        raise ConstructionTimelineError("timeline v10 coverage event contract differs")
    events = _event_documents(contract)
    predecessor_coverage = CODEC._json_object(
        CODEC._regular_bytes(PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v9 coverage"),
        "v9 coverage",
    )
    release_counts = dict(sorted(Counter(row["source_release_id"] for row in events).items()))
    if release_counts != RELEASE_ADDITION_COUNTS:
        raise ConstructionTimelineError("timeline v10 release event accounting differs")
    austin_events = [row for row in events if row["entity_stable_key"] == SABEY_AUSTIN_KEY]
    if [row["status"] for row in austin_events] != ["under_construction", "shell"]:
        raise ConstructionTimelineError("Sabey Austin transition contract differs")
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
        "inherited_v9_operational_lifecycle_closures": predecessor_coverage[
            "v9_delta_operational_lifecycle_closures"
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
        "predecessor": {
            "definition_sha256": PREDECESSOR_DEFINITION_PIN[1],
            "manifest_sha256": PREDECESSOR_MANIFEST_PIN[1],
            "timeline_id": previous.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "source_family_observation_counts": dict(
            sorted(Counter(str(row["evidence_source_family"]) for row in observations).items())
        ),
        "source_family_roles": roles,
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v10_addition_event_contract_sha256": digest,
        "v10_addition_events": events,
        "v10_addition_freshness_counts": dict(
            sorted(Counter(str(row["freshness_class"]) for row in events).items())
        ),
        "v10_authoritative_status_transitions": [
            {
                "closed_at": austin_events[1]["observed_date"],
                "current_status_classification": "unknown",
                "entity_stable_key": SABEY_AUSTIN_KEY,
                "from_observed_date": austin_events[0]["observed_date"],
                "from_status": "under_construction",
                "raw_valid_to_date_rewritten": False,
                "to_status": "shell",
                "transition_semantics": "closed_by_later_authoritative_observation",
            }
        ],
        "v10_delta_inference_guardrails": INFERENCE_GUARDRAILS,
        "v10_delta_operational_lifecycle_closures": [],
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v10\n\n"
        "This immutable append-only successor preserves all 541 accepted v9 "
        "lifecycle rows and all 521 accepted v9 entity-timeline rows exactly. It "
        "adds exactly 30 internal lifecycle observations first accepted by open "
        "seeds v88 through v92, yielding "
        f"{counts['raw_lifecycle_observations']} observations for "
        f"{counts['entities_with_lifecycle_observations']} entities.\n\n"
        "The 30-row delta is rebuilt from each accepted release at its original "
        "recorded_at: v88 adds 5, v89 adds 9, v90 adds 7, v91 adds 3, and v92 "
        "adds 6. Sabey Austin retains both its under-construction and later shell "
        "observations. The later authoritative shell observation closes the earlier "
        "sequence interval without rewriting either raw row.\n\n"
        "Every status remains a dated last-observed fact. Current status is unknown "
        "for every entity; no latest-state persistence, capacity inference, identity "
        "merge, forecast conversion, satellite/CV promotion, or unique-site claim is "
        "made. Historical operational observations inherited from v9 remain intact.\n"
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
    _row_linked, lineage, _roles = _source_family_state(observations)
    predecessor_lines: dict[str, str] = {}
    predecessor_text = CODEC._regular_bytes(
        PREDECESSOR_BUNDLE / ATTRIBUTION_FILENAME, "v9 attribution"
    ).decode("utf-8")
    for line in predecessor_text.splitlines():
        if line.startswith("- ") and " | " in line:
            predecessor_lines[line[2:].split(" | ", 1)[0]] = line
    lines = [
        "Derived only from hash-pinned timeline v9 and open seeds v88-v92.",
        "Every lifecycle row retains its accepted evidence identity and metadata.",
        "Source-family attribution inventory:",
    ]
    for family in sorted(lineage):
        if family not in by_family:
            inherited = predecessor_lines.get(family)
            if inherited is None:
                raise ConstructionTimelineError("inherited attribution family missing")
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


def _prepare_payloads(definition: _Definition) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations, additions, provenance = _reconstruct_observations()
    timelines = _timeline_rows(additions)
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
        raise ConstructionTimelineError("timeline coverage is not canonical JSON")
    if (
        len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]
        or len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("timeline v10 row inventory differs")
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
        raise ConstructionTimelineError("timeline observation order differs")
    timeline_order = [(row["entity_stable_key"], row["entity_id"]) for row in timelines]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(timeline_order):
        raise ConstructionTimelineError("grouped timeline order differs")
    flattened: list[str] = []
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
            raise ConstructionTimelineError("grouped timeline guardrails differ")
        flattened.extend(str(item["observation_id"]) for item in nested)
    if sorted(flattened) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineError("flat and grouped lifecycle inventories differ")
    if (
        coverage.get("format") != COVERAGE_FORMAT
        or coverage.get("schema_version") != SCHEMA_VERSION
        or coverage.get("scope") != SCOPE
        or coverage.get("counts") != EXPECTED_COUNTS
        or coverage.get("delta") != DELTA_CONTRACT
        or manifest.get("counts") != EXPECTED_COUNTS
        or manifest.get("delta") != DELTA_CONTRACT
    ):
        raise ConstructionTimelineError("timeline coverage or manifest differs")

    predecessor_observations = _predecessor_observations()
    predecessor_ids = {row["observation_id"] for row in predecessor_observations}
    current_by_id = {row["observation_id"]: row for row in observations}
    for row in predecessor_observations:
        inherited = current_by_id.get(row["observation_id"])
        if inherited != row or CODEC._csv_bytes([inherited]) != CODEC._csv_bytes([row]):
            raise ConstructionTimelineError("inherited v9 observation bytes changed")
    predecessor_timelines = _predecessor_timelines()
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    for row in predecessor_timelines:
        inherited = current_by_key.get(row["entity_stable_key"])
        if inherited != row or CODEC._canonical_json_line(inherited) != CODEC._canonical_json_line(row):
            raise ConstructionTimelineError("inherited v9 timeline bytes changed")

    additions = [row for row in observations if row["observation_id"] not in predecessor_ids]
    events = coverage.get("v10_addition_events")
    if not isinstance(events, list):
        raise ConstructionTimelineError("timeline v10 event contract is missing")
    event_by_id = {str(row["observation_id"]): row for row in events}
    provenance = {
        observation_id: (str(row["source_release_id"]), str(row["source_input_path"]))
        for observation_id, row in event_by_id.items()
    }
    contract = _event_contract(additions, provenance)
    digest = _event_contract_sha256(contract)
    expected_digest = coverage.get("v10_addition_event_contract_sha256")
    if (
        len(additions) != ADDED_OBSERVATIONS
        or len(event_by_id) != ADDED_OBSERVATIONS
        or _event_documents(contract) != events
        or expected_digest != digest
        or (
            ADDITION_EVENT_CONTRACT_SHA256 != "TO_FILL"
            and digest != ADDITION_EVENT_CONTRACT_SHA256
        )
        or coverage.get("open_seed_release_event_counts") != RELEASE_ADDITION_COUNTS
    ):
        raise ConstructionTimelineError("published v10 event contract differs")
    austin = current_by_key.get(SABEY_AUSTIN_KEY)
    if (
        not isinstance(austin, Mapping)
        or [row["status"] for row in austin["observations"]]
        != ["under_construction", "shell"]
        or coverage.get("v10_delta_operational_lifecycle_closures") != []
        or coverage.get("v10_delta_inference_guardrails") != INFERENCE_GUARDRAILS
        or coverage.get("current_status_classification_counts") != {"unknown": 550}
        or coverage.get("lifecycle_row_linked_source_family_count")
        != LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES
        or coverage.get("lineage_aware_source_family_count")
        != LINEAGE_AWARE_SOURCE_FAMILIES
    ):
        raise ConstructionTimelineError("v10 history or inference boundary differs")
    if (
        coverage.get("observation_entity_kind_counts") != {"campus": 83, "project": 488}
        or coverage.get("timeline_entity_kind_counts") != {"campus": 83, "project": 467}
        or coverage.get("observation_status_counts", {}).get("under_construction") != 402
        or coverage.get("observation_status_counts", {}).get("shell") != 36
        or coverage.get("observation_status_counts", {}).get("site_preparation") != 15
        or coverage.get("observation_status_counts", {}).get("operational") != 49
    ):
        raise ConstructionTimelineError("timeline v10 status or kind counts differ")


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
    artifacts = (definition_path, bundle_path, *bundle_path.iterdir())
    for artifact in artifacts:
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
        if require_live and metadata.st_ctime + 0.000_001 < generated.timestamp():
            raise ConstructionTimelineError(
                f"timeline final artifact ctime predates generated_at: {artifact.name}"
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
    """Validate the closed v10 bundle and optionally replay every accepted input."""

    wall = validation_wall_clock or datetime.now(timezone.utc)
    definition = _load_definition(definition_path, validation_wall_clock=wall)
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
            validation_wall_clock=wall,
            require_live=require_live,
        )
    if verify_inputs:
        expected_payloads, expected_manifest = _prepare_payloads(definition)
        actual_payloads = {entry.name: entry.read_bytes() for entry in entries}
        if actual_payloads != expected_payloads or manifest != expected_manifest:
            raise ConstructionTimelineError("exact-input timeline rebuild differs")
    return manifest


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
        except BaseException as error:  # pragma: no cover
            errors.append(f"definition rollback failed: {error}")
    if bundle_published:
        try:
            promote_noreplace(BUNDLE, bundle_stage)
        except BaseException as error:  # pragma: no cover
            errors.append(f"bundle rollback failed: {error}")
    if errors:
        raise ConstructionTimelineError("; ".join(errors))


def publish_construction_timeline_v10() -> dict[str, Any]:
    """Privately stage, double-rebuild, freeze, and no-replace publish v10."""

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
            planned = _parse_utc(GENERATED_AT, label="timeline generated_at")
            definition = _load_definition(definition_stage, validation_wall_clock=planned)
            payloads, manifest = _prepare_payloads(definition)
            replay_payloads, replay_manifest = _prepare_payloads(definition)
            if payloads != replay_payloads or manifest != replay_manifest:
                raise ConstructionTimelineError(
                    "open-seed inputs changed or two offline reconstructions differ"
                )
            _write_bundle_stage(bundle_stage, payloads)
            validate_construction_timeline_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_frozen=False,
                verify_publication_times=False,
                require_live=False,
                validation_wall_clock=planned,
            )
            if _latest_stage_time(definition_stage, bundle_stage) > planned.timestamp() + 0.000_001:
                raise ConstructionTimelineError(
                    "timeline staging exceeded generated_at; refusing publication"
                )
            _wait_until_generated_at()
            # Freeze after the barrier so every final member has ctime >= generated_at.
            definition_stage.chmod(FROZEN_FILE_MODE)
            for target in bundle_stage.iterdir():
                target.chmod(FROZEN_FILE_MODE)
            bundle_stage.chmod(FROZEN_DIRECTORY_MODE)
            validate_construction_timeline_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_live=True,
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
    """Publish only the reserved v10 definition and bundle paths."""

    definition = Path(os.path.abspath(os.fspath(definition_path)))
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if definition != DEFINITION or output != BUNDLE:
        raise ConstructionTimelineError("timeline v10 publication paths are reserved")
    return publish_construction_timeline_v10()


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "ADDITION_EVENT_CONTRACT_SHA256",
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
    "LIFECYCLE_ROW_LINKED_SOURCE_FAMILIES",
    "LINEAGE_AWARE_SOURCE_FAMILIES",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OBSERVATIONS_FILENAME",
    "OBSERVATION_FIELDS",
    "PREDECESSOR_TREE_SHA256",
    "RELEASE_ADDITION_COUNTS",
    "SABEY_AUSTIN_KEY",
    "TIMELINES_FILENAME",
    "TIMELINE_ID",
    "build_construction_timeline_bundle",
    "publish_construction_timeline_v10",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
