"""Immutable v3-successor construction timeline derived from open seed v68.

The bundle preserves every accepted v3 flat observation and entity-timeline
row exactly, then appends the thirteen raw lifecycle observations introduced
by open seed v68.  All statuses remain dated, last-observed source facts;
current status is unknown and persistence is never assumed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass
from datetime import date
import io
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from . import construction_timeline_v2 as carrier
from . import construction_timeline_v3 as v3
from . import open_seed_v68
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-21-public-open-v4"
AS_OF = "2026-07-21"
GENERATED_AT = "2026-07-21T09:35:00Z"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-21-open-seed-v68"
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v68.py"
OPEN_SEED_DEFINITION_SHA256 = (
    "430544a894c0e529693699fe6db36387b690f621ee899a38bedd9ea093ec394f"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "7aa9d511831509f953fdfe6bccd9380feeb2feac11ec529eb9b024243a7da3e7"
)
OPEN_SEED_TREE_SHA256 = (
    "855258248ab3af498ef6f6259d55a2ace093c8eacdcc7b6b1aafe03ac8f3b89b"
)
OPEN_SEED_CORE_SHA256 = (
    "fb3f801026da090af4466c4454d2f7b48d2c07347226deac9d8e5d9afd722f1e"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v3.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v3"
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v3.py"
PREDECESSOR_DEFINITION_SHA256 = (
    "698648dda386a00e62247a4fdaf1aaf83ca2bc62f865ea366c5f51da2813d055"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "4dc0c03968d2b3b07db225df3b3388ebabaeedb3ecb4f1ca0e3996a4e5070d20"
)
PREDECESSOR_TREE_SHA256 = (
    "4b8bf25f4177bdeeacb87a17836060de225172db73731a2e73a192ce78ce773a"
)
PREDECESSOR_CORE_SHA256 = (
    "78735896a390f2cab9ba039d30968076f2eeac65f737686c8e3e0bc6dfb65e85"
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v4"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v4"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v4"
SCHEMA_VERSION = 4

# Entity rows retain the accepted carrier schema so inherited JSONL lines are
# byte-identical. V4 applies only to definition, bundle, coverage and manifest.
TIMELINE_FORMAT = v3.TIMELINE_FORMAT
TIMELINE_SCHEMA_VERSION = v3.TIMELINE_SCHEMA_VERSION
OBSERVATIONS_FILENAME = v3.OBSERVATIONS_FILENAME
TIMELINES_FILENAME = v3.TIMELINES_FILENAME
COVERAGE_FILENAME = v3.COVERAGE_FILENAME
README_FILENAME = v3.README_FILENAME
ATTRIBUTION_FILENAME = v3.ATTRIBUTION_FILENAME
MANIFEST_FILENAME = v3.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = v3.MANIFEST_HASH_FILENAME
BUNDLE_FILES = v3.BUNDLE_FILES
OBSERVATION_FIELDS = v3.OBSERVATION_FIELDS
FROZEN_DIRECTORY_MODE = v3.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = v3.FROZEN_FILE_MODE

SCOPE = dict(v3.SCOPE)

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 456,
    "multi_observation_entities": 16,
    "raw_lifecycle_observations": 472,
    "repeated_status_multi_observation_entities": 4,
    "single_observation_entities": 440,
    "single_old_observation_entities": 26,
    "source_families": 201,
    "status_changing_multi_observation_entities": 12,
}

FULL_V68_RAW_OBSERVATIONS = 472
PREDECESSOR_OBSERVATIONS = 459
PREDECESSOR_TIMELINES = 443
V68_ADDED_OBSERVATIONS = 13
V68_ADDED_PROJECTS = 13
V68_INHERITED_RECORDED_AT_REWRITES_IGNORED = 74

PROJECT_SOURCE_BY_KEY = {
    "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center": (
        "sources/curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json"
    ),
    "curated:firebird-ai-center-hrazdan-site:current-center-development": (
        "sources/curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json"
    ),
    "curated:green-mountain-fra-mainz-campus:current-three-building-development": (
        "sources/curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json"
    ),
    "curated:harch-intelligence-dakhla-campus:initial-development": (
        "sources/curated-official-2026-07-21-harch-dakhla-groundbreaking.json"
    ),
    "curated:scala-huechuraba-campus:ssclhb01": (
        "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json"
    ),
    "curated:scala-lampa-campus:sscllp01": (
        "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json"
    ),
    "curated:scala-praia-do-futuro-campus:sforpf01": (
        "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json"
    ),
    "curated:scala-smextp02-tepotzotlan-data-center:smextp02": (
        "sources/curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json"
    ),
    "curated:scala-tambore-campus:sgrutb07": (
        "sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json"
    ),
    "curated:scala-tambore-campus:sgrutb09": (
        "sources/curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json"
    ),
    "curated:scala-tambore-campus:sgrutb10": (
        "sources/curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json"
    ),
    "curated:scala-tambore-campus:sgrutb11": (
        "sources/curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json"
    ),
    "curated:scala-zona-franca-bogota-campus:sbogzb01": (
        "sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json"
    ),
}

EVENT_CONTRACT_FIELDS = v3.EVENT_CONTRACT_FIELDS

V68_ADDITION_EVENT_CONTRACT = (
    ("sources/curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json", "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center", "f60af7f1-62a6-52f3-b69c-690706120966", "2026-06-30", "under_construction", "authoritative_physical_status_update", "44d94a9a-8b9d-5dc7-9b40-c5c8a262ceb7", "azerbaijan_digital_development_ministry_news", "2026-07-21T08:20:34Z", "1ae75d6a28d1fcdfd5d718e36ca3638660c1cca64918135dd3d90d52ca7eea7c", 21, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json", "curated:firebird-ai-center-hrazdan-site:current-center-development", "6802335e-35ea-57c8-98c8-c75b831a1bac", "2026-06-05", "under_construction", "authoritative_physical_status_update", "5875ee3f-0fb2-5b61-b2fc-dde93a48c1e5", "armenia_high_tech_ministry_news", "2026-07-21T08:20:29Z", "f5c8279b14e8b52fdc00aef7897c773ba3f4bf78f89d94566b8559271027de23", 46, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json", "curated:green-mountain-fra-mainz-campus:current-three-building-development", "c2446678-861c-544a-9be1-98038fa7a9de", "2026-07-21", "under_construction", "authoritative_physical_status_update", "b6a4a704-8176-570e-8d48-4f118e5990b8", "green_mountain_data_center_pages", "2026-07-21T07:52:28Z", "f8720070b7d4048db848a9addbc489b34da0e75267e40813497dab14eccb1505", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-harch-dakhla-groundbreaking.json", "curated:harch-intelligence-dakhla-campus:initial-development", "2c79d1bb-6c39-5451-9043-7ce59752a874", "2026-03-15", "under_construction", "authoritative_construction_start", "8470d6d0-088e-534c-9094-566e3a974140", "harch_corp_newsroom", "2026-07-21T07:52:28Z", "e7a4383fe2a8ce31043978b22ec5d9e8e4063ee1e73e47583f40b65dca4ae73b", 128, "aging_91_365_days"),
    ("sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json", "curated:scala-huechuraba-campus:ssclhb01", "832b0742-92d7-53a7-aff4-c412f9348848", "2026-07-21", "under_construction", "authoritative_physical_status_update", "d4f91e87-3ea2-5833-b19d-fd5a3ca7b591", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json", "curated:scala-lampa-campus:sscllp01", "89881a3a-9bda-5a3b-8498-8fd851ffbaa3", "2026-07-21", "under_construction", "authoritative_physical_status_update", "97007edb-ddfc-5984-884a-8222ded41e29", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json", "curated:scala-praia-do-futuro-campus:sforpf01", "4b762d84-2972-505d-bd2f-c9bab2af7759", "2026-07-21", "under_construction", "authoritative_physical_status_update", "62b2a499-44a6-59c1-b956-78abbbc1b8d5", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json", "curated:scala-smextp02-tepotzotlan-data-center:smextp02", "fadaf4b6-a266-5721-8cec-146dadbd73f0", "2026-07-21", "under_construction", "authoritative_physical_status_update", "2ef11cfd-e291-5844-bbde-01ca5a7649b9", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json", "curated:scala-tambore-campus:sgrutb07", "90b9bad8-6745-5a70-afd8-c9fa67464466", "2026-07-21", "under_construction", "authoritative_physical_status_update", "26ec6a17-57c7-535d-949d-50b4cbfbfdb4", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json", "curated:scala-tambore-campus:sgrutb09", "b664a11d-92ee-51a0-aac7-b3b32e0af6ef", "2026-07-21", "under_construction", "authoritative_physical_status_update", "836f41ff-9153-51db-a76f-12b18f7c1942", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json", "curated:scala-tambore-campus:sgrutb10", "d19aa43e-8a00-51dd-a11b-bc7f13212e73", "2026-07-21", "under_construction", "authoritative_physical_status_update", "1c93e688-037b-5ac3-9592-973143e559d6", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json", "curated:scala-tambore-campus:sgrutb11", "4c97c3a5-8c5e-54b5-931e-affdb57acc95", "2026-07-21", "under_construction", "authoritative_physical_status_update", "87f972bc-b5a3-53ce-90f8-53e57c0bf7c7", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json", "curated:scala-zona-franca-bogota-campus:sbogzb01", "4112fcaf-5d22-5201-aea9-38e25bdc6497", "2026-07-21", "under_construction", "authoritative_physical_status_update", "4723a143-571a-5f76-97c2-12aea18b3a8b", "scala_data_center_portfolio_pages", "2026-07-21T07:52:27Z", "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b", 0, "recent_0_90_days"),
)

DELTA_CONTRACT = {
    "full_v68_raw_lifecycle_observations": FULL_V68_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "recorded_at_values_preserved_from_v3": True,
    "v68_added_lifecycle_observations": V68_ADDED_OBSERVATIONS,
    "v68_added_project_entities": V68_ADDED_PROJECTS,
    "v68_inherited_recorded_at_rewrites_ignored": (
        V68_INHERITED_RECORDED_AT_REWRITES_IGNORED
    ),
}

ConstructionTimelineError = v3.ConstructionTimelineError


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


def _load_definition(path_value: str | Path) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = v3._regular_bytes(path, "timeline definition")
    document = v3._json_object(raw, "timeline definition")
    if raw != v3._canonical_json(document):
        raise ConstructionTimelineError("timeline definition must be canonical JSON")
    if set(document) != {
        "as_of", "delta", "expected", "format", "generated_at", "open_seed",
        "predecessor", "schema_version", "scope", "timeline_id",
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
        raise ConstructionTimelineError("timeline v4 definition contract differs")
    if GENERATED_AT <= open_seed_v68.RECORDED_AT:
        raise ConstructionTimelineError("timeline generated_at must follow v68")

    open_seed = document["open_seed"]
    predecessor = document["predecessor"]
    if not isinstance(open_seed, Mapping) or set(open_seed) != {
        "definition", "expected_release_tree_sha256", "manifest", "release_path",
    }:
        raise ConstructionTimelineError("open seed checkpoint schema is invalid")
    if not isinstance(predecessor, Mapping) or set(predecessor) != {
        "bundle_path", "definition", "expected_bundle_tree_sha256", "manifest",
    }:
        raise ConstructionTimelineError("predecessor checkpoint schema is invalid")
    seed_definition_display, seed_definition_digest = v3._checkpoint(
        open_seed["definition"], "open seed definition"
    )
    seed_manifest_display, seed_manifest_digest = v3._checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    predecessor_definition_display, predecessor_definition_digest = v3._checkpoint(
        predecessor["definition"], "predecessor definition"
    )
    predecessor_manifest_display, predecessor_manifest_digest = v3._checkpoint(
        predecessor["manifest"], "predecessor manifest"
    )
    seed_definition = v3._resolve(path, seed_definition_display, "open seed definition")
    seed_release = v3._resolve(path, open_seed["release_path"], "open seed release")
    seed_manifest = v3._resolve(path, seed_manifest_display, "open seed manifest")
    predecessor_definition = v3._resolve(
        path, predecessor_definition_display, "predecessor definition"
    )
    predecessor_bundle = v3._resolve(
        path, predecessor["bundle_path"], "predecessor bundle"
    )
    predecessor_manifest = v3._resolve(
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
        raise ConstructionTimelineError("accepted v68 or timeline v3 pins differ")
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
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
    for path, digest in checkpoints.items():
        if v3._sha256_file(path) != digest:
            raise ConstructionTimelineError(f"frozen input changed: {path}")
    if tree_digest(definition.open_seed_release) != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen open seed v68 tree changed")
    if tree_digest(definition.predecessor_bundle) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v3 tree changed")
    try:
        seed_manifest = open_seed_v68.validate_open_seed_v68(
            definition.open_seed_definition, definition.open_seed_release
        )
        predecessor_manifest = v3.validate_construction_timeline_bundle(
            definition.predecessor_bundle,
            definition_path=definition.predecessor_definition,
            verify_inputs=True,
        )
    except (OSError, ValueError, SystemExit) as error:
        raise ConstructionTimelineError("frozen input validation failed") from error
    frozen_seed_manifest = v3._json_object(
        v3._regular_bytes(definition.open_seed_release / MANIFEST_FILENAME, "v68 manifest"),
        "v68 manifest",
    )
    frozen_predecessor_manifest = v3._json_object(
        v3._regular_bytes(
            definition.predecessor_bundle / MANIFEST_FILENAME, "timeline v3 manifest"
        ),
        "timeline v3 manifest",
    )
    if seed_manifest != frozen_seed_manifest or predecessor_manifest != frozen_predecessor_manifest:
        raise ConstructionTimelineError("validated frozen input manifest differs")


def _release_labels(release: Path) -> dict[str, dict[str, str]]:
    raw = v3._regular_bytes(release / "entities.csv", "v68 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v68 entities.csv is not UTF-8") from error
    if len(rows) != 806:
        raise ConstructionTimelineError("v68 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v68 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _full_v68_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_inputs(definition)
    v68_document = v3._json_object(
        v3._regular_bytes(definition.open_seed_definition, "v68 definition"),
        "v68 definition",
    )
    base = v3._json_object(
        v3._regular_bytes(open_seed_v68.BASE_DEFINITION, "v67 base definition"),
        "v67 base definition",
    )
    try:
        selected_rows, paths = open_seed_v68.selected_inputs(base)
    except (OSError, ValueError, SystemExit) as error:
        raise ConstructionTimelineError("v68 source selection failed") from error
    if selected_rows != v68_document.get("curated_inputs") or len(paths) != 391:
        raise ConstructionTimelineError("fresh v68 source inventory differs")
    labels = _release_labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(prefix="construction-timeline-v4-db-", dir="/private/tmp") as temporary:
        try:
            connection = open_seed_v68._build_database(
                base, paths, Path(temporary) / "atlas.sqlite"
            )
        except (OSError, ValueError, SystemExit) as error:
            raise ConstructionTimelineError("fresh v68 database rebuild failed") from error
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
            raise ConstructionTimelineError("v68 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if (
        len(observations) != FULL_V68_RAW_OBSERVATIONS
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("full v68 lifecycle inventory differs")
    return observations


def _predecessor_observations(definition: _Definition) -> list[dict[str, str]]:
    rows = v3._parse_csv(definition.predecessor_bundle / OBSERVATIONS_FILENAME)
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("timeline v3 observation inventory differs")
    if v3._csv_bytes(rows) != v3._regular_bytes(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME, "v3 observations"
    ):
        raise ConstructionTimelineError("timeline v3 observation bytes differ")
    return rows


def _predecessor_timelines(definition: _Definition) -> list[dict[str, Any]]:
    rows = v3._parse_jsonl(definition.predecessor_bundle / TIMELINES_FILENAME)
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("timeline v3 entity inventory differs")
    if b"".join(v3._canonical_json_line(row) for row in rows) != v3._regular_bytes(
        definition.predecessor_bundle / TIMELINES_FILENAME, "v3 timelines"
    ):
        raise ConstructionTimelineError("timeline v3 JSONL bytes differ")
    return rows


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    as_of = date.fromisoformat(AS_OF)
    contract = []
    for row in rows:
        stable_key = str(row["entity_stable_key"])
        age = (as_of - date.fromisoformat(str(row["observed_date"]))).days
        contract.append(
            (
                PROJECT_SOURCE_BY_KEY[stable_key], stable_key,
                str(row["observation_id"]), str(row["observed_date"]),
                str(row["status"]), str(row["method"]), str(row["evidence_id"]),
                str(row["evidence_source_family"]), str(row["evidence_retrieved_at"]),
                str(row["evidence_content_hash"]), age, v3._freshness_class(age),
            )
        )
    return tuple(sorted(contract, key=lambda item: (item[1], item[3], item[2])))


def _reconstruct_observations(
    definition: _Definition,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = _full_v68_observations(definition)
    predecessor = _predecessor_observations(definition)
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v68 dropped a timeline v3 observation")
    rewrite_count = 0
    for row in predecessor:
        fresh = v3._csv_row(full_by_id[row["observation_id"]])
        differences = {field for field in OBSERVATION_FIELDS if row[field] != fresh[field]}
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v68 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
    if rewrite_count != V68_INHERITED_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError("v68 inherited recorded_at rewrite count differs")

    additions = [row for row in full if row["entity_stable_key"] in PROJECT_SOURCE_BY_KEY]
    if (
        len(additions) != V68_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in additions}) != V68_ADDED_PROJECTS
        or _event_contract(additions) != V68_ADDITION_EVENT_CONTRACT
    ):
        raise ConstructionTimelineError("v68 addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids:
        raise ConstructionTimelineError("v68 addition collides with timeline v3")
    if set(full_by_id) - predecessor_ids != addition_ids:
        raise ConstructionTimelineError("v68 full-to-v3 delta boundary differs")
    combined: list[dict[str, Any]] = [*predecessor, *additions]
    combined.sort(
        key=lambda row: (
            str(row["entity_stable_key"]), str(row["observed_date"]),
            str(row["recorded_at"]), str(row["observation_id"]),
        )
    )
    if len(combined) != EXPECTED_COUNTS["raw_lifecycle_observations"]:
        raise ConstructionTimelineError("timeline v4 observation inventory differs")
    return combined, additions


def _timeline_rows(
    definition: _Definition, additions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines(definition)
    new_rows = carrier._timeline_rows(additions, as_of=AS_OF)
    if (
        len(new_rows) != V68_ADDED_PROJECTS
        or any(
            row["format"] != TIMELINE_FORMAT
            or row["schema_version"] != TIMELINE_SCHEMA_VERSION
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] is not False
            or row["latest_observation_persistence_assumed"] is not False
            for row in new_rows
        )
    ):
        raise ConstructionTimelineError("v68 addition timeline guardrails differ")
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("timeline v4 entity collides with timeline v3")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _event_documents() -> list[dict[str, Any]]:
    documents = []
    for event in V68_ADDITION_EVENT_CONTRACT:
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
        "source_families": len({row["evidence_source_family"] for row in observations}),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineError(f"timeline coverage counts differ: {counts}")
    events = _event_documents()
    predecessor_coverage = v3._json_object(
        v3._regular_bytes(PREDECESSOR_BUNDLE / COVERAGE_FILENAME, "v3 coverage"),
        "v3 coverage",
    )
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
            "timeline_id": v3.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "source_family_observation_counts": dict(
            sorted(Counter(str(row["evidence_source_family"]) for row in observations).items())
        ),
        "stt_johor_historical_only": predecessor_coverage["stt_johor_historical_only"],
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v68_addition_events": events,
        "v68_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v4\n\n"
        "This immutable exact successor preserves all 459 accepted v3 lifecycle "
        "observations and all 443 accepted v3 entity-timeline rows byte-for-byte, "
        "then appends the 13 raw v68 observations on 13 new project identities. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} source-scoped entities.\n\n"
        "A complete 472-row v68 lifecycle database is rebuilt offline. Seventy-four "
        "v68 recorded_at rewrites never replace the predecessor's accepted recording "
        "lineage. Every lifecycle status remains a dated last-observed fact. Current "
        "status is unknown, current construction is never claimed, and the latest "
        "observation is never assumed to persist. STT Johor remains stale, historical "
        "only, and 512 days old.\n\n"
        "Permits, forecasts, planned dates, satellite or CV review, and missing "
        "milestones are not promoted or interpolated into physical construction. "
        "Cross-source identities remain unresolved and unique physical sites remain "
        "null. The accepted entity-timeline row format is retained so inherited JSONL "
        "lines remain byte-identical; v4 applies to the outer contracts.\n"
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
        "Derived from the hash-pinned construction timeline v3 and open seed v68 inputs.",
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
        COVERAGE_FILENAME: v3._canonical_json(coverage),
        OBSERVATIONS_FILENAME: v3._csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: b"".join(v3._canonical_json_line(row) for row in timelines),
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw), "file": definition.path.name,
            "sha256": v3._sha256_bytes(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": v3._sha256_bytes(raw)}
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
                "file": MANIFEST_FILENAME, "sha256": OPEN_SEED_MANIFEST_SHA256,
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
                "bytes": (definition.predecessor_bundle / MANIFEST_FILENAME).stat().st_size,
                "file": MANIFEST_FILENAME, "sha256": PREDECESSOR_MANIFEST_SHA256,
            },
            "timeline_id": v3.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = v3._canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _validate_payload_semantics(directory: Path, manifest: Mapping[str, Any]) -> None:
    observations = v3._parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = v3._parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = v3._regular_bytes(directory / COVERAGE_FILENAME, COVERAGE_FILENAME)
    coverage = v3._json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != v3._canonical_json(coverage):
        raise ConstructionTimelineError("coverage JSON is not canonical")
    if (
        len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]
        or len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("timeline row inventory differs")
    stable_order = [
        (row["entity_stable_key"], row["observed_date"], row["recorded_at"], row["observation_id"])
        for row in observations
    ]
    if stable_order != sorted(stable_order):
        raise ConstructionTimelineError("observation CSV ordering differs")
    timeline_order = [(row.get("entity_stable_key"), row.get("entity_id")) for row in timelines]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(timeline_order):
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
    predecessor_rows = v3._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    current_by_id = {row["observation_id"]: row for row in observations}
    if any(current_by_id.get(row["observation_id"]) != row for row in predecessor_rows):
        raise ConstructionTimelineError("inherited observation semantics changed")
    predecessor_timelines = v3._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    if any(current_by_key.get(row["entity_stable_key"]) != row for row in predecessor_timelines):
        raise ConstructionTimelineError("inherited timeline semantics changed")
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


def validate_construction_timeline_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate a closed v4 bundle and optionally replay all inputs offline."""

    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineError("timeline bundle must be an ordinary directory")
    if require_frozen and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise ConstructionTimelineError("timeline bundle directory must be mode 0555")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineError("timeline bundle file inventory differs")
    for entry in entries:
        v3._regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = v3._regular_bytes(directory / MANIFEST_FILENAME, MANIFEST_FILENAME)
    manifest = v3._json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != v3._canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = v3._regular_bytes(directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME)
    expected_sidecar = (
        f"{v3._sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar != expected_sidecar:
        raise ConstructionTimelineError("timeline manifest sidecar differs")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("timeline_id") != TIMELINE_ID
        or manifest.get("as_of") != AS_OF
        or manifest.get("generated_at") != GENERATED_AT
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
        raw = v3._regular_bytes(directory / name, name)
        if files[name] != {"bytes": len(raw), "sha256": v3._sha256_bytes(raw)}:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if definition_path is not None:
        definition = _load_definition(definition_path)
        if manifest.get("definition") != {
            "bytes": len(definition.raw), "file": definition.path.name,
            "sha256": v3._sha256_bytes(definition.raw),
        }:
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
    """Double-rebuild, freeze and atomically publish construction timeline v4."""

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
            "v68 inputs changed or two offline timeline reconstructions differ"
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
            output, definition_path=definition.path, verify_inputs=True
        )
    finally:
        if not published:
            _discard_stage(stage)


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "AS_OF", "ATTRIBUTION_FILENAME", "BUNDLE_FILES", "BUNDLE_FORMAT",
    "COVERAGE_FILENAME", "ConstructionTimelineError", "DELTA_CONTRACT",
    "EXPECTED_COUNTS", "GENERATED_AT", "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME", "OBSERVATIONS_FILENAME", "OBSERVATION_FIELDS",
    "OPEN_SEED_DEFINITION_SHA256", "OPEN_SEED_MANIFEST_SHA256",
    "OPEN_SEED_TREE_SHA256", "PREDECESSOR_DEFINITION_SHA256",
    "PREDECESSOR_MANIFEST_SHA256", "PREDECESSOR_TREE_SHA256",
    "PROJECT_SOURCE_BY_KEY", "SCHEMA_VERSION", "SCOPE", "TIMELINES_FILENAME",
    "TIMELINE_FORMAT", "TIMELINE_ID", "TIMELINE_SCHEMA_VERSION",
    "V68_ADDITION_EVENT_CONTRACT", "build_construction_timeline_bundle",
    "validate_construction_timeline_bundle", "write_construction_timeline_bundle",
]
