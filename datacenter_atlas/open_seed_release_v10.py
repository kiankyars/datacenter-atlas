"""Strict validator for the frozen open-seed v65 successor.

V65 remains on the 2026-07-20 local research day. It is the exact frozen-v64
successor that adds only the accepted Lancium/Crusoe/Oracle Abilene package.

The publication format remains contract version 4. Lifecycle values are
last-observed facts; this validator never turns them into current-status claims.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from . import open_seed_release_v2 as v2
from . import open_seed_release_v9 as v9
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V64_DEFINITION = "sources/open-seed-2026-07-20-v64.json"
V64_RELEASE = "releases/2026-07-20-open-seed-v64"
V64_DEFINITION_SHA256 = (
    "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e"
)
V64_MANIFEST_SHA256 = "5c5b19079ce237b859c2bdaf465bf1aec17392f52a75ad81805a919e1ee4cc1d"
V64_TREE_SHA256 = "05901f4760e452d5d3deb4134b3434e248f7e8f15873a5f27cdad559582385da"

RELEASE_ID = "2026-07-20-open-seed-v65"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T06:20:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS: dict[str, tuple[str, str]] = {}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json": (
        "bffd47864bb2d013caff5c8888974c761ca5abe3a03025f3b19c90d52fb92eaa"
    ),
}

SOURCE_ARTIFACT = "source_artifacts/oracle-abilene-official-2026-07-20-v1"
SOURCE_ARTIFACT_MANIFEST_SHA256 = (
    "46d2c0bdc89835457ec1619ed0d06dc41988d0193cc3b36212c199e481f49cc2"
)
SOURCE_ARTIFACT_TREE_SHA256 = (
    "34df1ccd0f80bd56333cb13487c671bb1c6c487373555451d7ccd91717a6d80d"
)

STALE_EXCLUSIONS = v9.STALE_EXCLUSIONS
PENDING_NEXT_DAY_EXCLUSIONS = v9.PENDING_NEXT_DAY_EXCLUSIONS
OUT_OF_SCOPE_EXCLUSIONS: frozenset[str] = frozenset()


class OpenSeedReleaseV10Error(ValueError):
    """Raised when the v65 definition, inputs, or release differ."""


def freshness_contract() -> dict[str, Any]:
    """Return the unchanged last-observed and calendar-boundary contract."""

    return v9.freshness_contract()


def validate_frozen_v64(project_root: Path) -> dict[str, Any]:
    """Pin and fully replay the sole permitted v65 base."""

    definition = project_root / V64_DEFINITION
    release = project_root / V64_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v64 definition")) != (
        V64_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV10Error("frozen v64 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v64 manifest")) != (
        V64_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV10Error("frozen v64 manifest hash differs")
    if v2._tree_digest(release) != V64_TREE_SHA256:
        raise OpenSeedReleaseV10Error("frozen v64 release tree differs")
    try:
        return v9.validate_open_seed_release_v9(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV10Error("frozen v64 validation failed") from error


def _definition(path: str | Path) -> tuple[dict[str, Any], Path, Path]:
    definition_path = v2._lexical_absolute(path)
    raw = v2._ordinary_file(definition_path, "definition")
    document = v2._json_object(raw, "definition", canonical=True)
    expected_keys = {
        "build",
        "curated_inputs",
        "epoch_capture",
        "expected_epoch_result",
        "expected_release",
        "expected_summary",
        "freshness_contract",
        "publication_contract_version",
        "release_id",
        "schema_version",
        "scope",
    }
    if set(document) != expected_keys or document["schema_version"] != 1:
        raise OpenSeedReleaseV10Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV10Error("publication contract version must remain 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV10Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV10Error("release_id must identify frozen v65")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV10Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV10Error("v65 build timestamp contract differs")
    if document["freshness_contract"] != freshness_contract():
        raise OpenSeedReleaseV10Error("v65 freshness contract differs")
    return document, definition_path, project_root


def _expected_v65_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V64_DEFINITION, "v64 definition")
    base = v2._json_object(raw, "v64 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 363:
        raise OpenSeedReleaseV10Error("v64 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV10Error("v64 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV10Error("v64 curated inventory is invalid")
        selected[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV10Error("a v65 addition already occurs in v64")
        if v2._sha256(v2._ordinary_file(project_root / path, path)) != digest:
            raise OpenSeedReleaseV10Error(f"accepted v65 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV10Error(
            "an excluded stale or next-day source was selected"
        )
    if len(selected) != 364:
        raise OpenSeedReleaseV10Error(
            f"expected 364 unique v65 inputs, found {len(selected)}"
        )
    return [{"path": path, "sha256": selected[path]} for path in sorted(selected)]


def _validate_local_research_day(source: Mapping[str, Any], label: str) -> None:
    """Reject UTC-date leakage into Jul 20 identifiers or normalized facts."""

    if "2026-07-21" in label:
        raise OpenSeedReleaseV10Error(
            f"next-day source identifier is forbidden: {label}"
        )
    cutoff = date.fromisoformat(AS_OF)
    dated_rows: list[Mapping[str, Any]] = []
    for field in ("campus", "project"):
        row = source.get(field)
        if isinstance(row, Mapping):
            dated_rows.append(row)
    for field in ("lifecycle", "capacities", "operating_models", "workloads"):
        rows = source.get(field, [])
        if not isinstance(rows, list):
            raise OpenSeedReleaseV10Error(
                f"invalid normalized row list: {label}: {field}"
            )
        dated_rows.extend(row for row in rows if isinstance(row, Mapping))
    for row in dated_rows:
        observed = row.get("as_of_date")
        if not isinstance(observed, str) or date.fromisoformat(observed) > cutoff:
            raise OpenSeedReleaseV10Error(
                f"normalized fact crosses the Jul 20 research day: {label}"
            )
        for key in ("stable_key", "evidence_key"):
            value = row.get(key)
            if isinstance(value, str) and "2026-07-21" in value:
                raise OpenSeedReleaseV10Error(
                    f"next-day normalized identifier is forbidden: {label}"
                )
    for evidence in source.get("evidence", []):
        if not isinstance(evidence, Mapping):
            raise OpenSeedReleaseV10Error(f"invalid evidence row: {label}")
        if "2026-07-21" in str(evidence.get("key", "")):
            raise OpenSeedReleaseV10Error(
                f"next-day evidence identifier is forbidden: {label}"
            )
        artifact_id = evidence.get("metadata", {}).get("capture_artifact_id")
        if isinstance(artifact_id, str) and "2026-07-21" in artifact_id:
            raise OpenSeedReleaseV10Error(
                f"next-day artifact identifier is forbidden: {label}"
            )


def _validate_source_artifact(project_root: Path) -> None:
    """Pin the compact, non-redistributive Abilene capture artifact."""

    artifact = project_root / SOURCE_ARTIFACT
    manifest_raw = v2._ordinary_file(
        artifact / "manifest.json", "Abilene artifact manifest"
    )
    if v2._sha256(manifest_raw) != SOURCE_ARTIFACT_MANIFEST_SHA256:
        raise OpenSeedReleaseV10Error("Abilene artifact manifest hash differs")
    manifest = v2._json_object(
        manifest_raw, "Abilene artifact manifest", canonical=False
    )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise OpenSeedReleaseV10Error("Abilene artifact file inventory is invalid")
    tree_payload = json.dumps(files, indent=2, sort_keys=True) + "\n"
    if hashlib.sha256(tree_payload.encode()).hexdigest() != SOURCE_ARTIFACT_TREE_SHA256:
        raise OpenSeedReleaseV10Error("Abilene artifact tree differs")
    if manifest.get("tree_sha256") != SOURCE_ARTIFACT_TREE_SHA256:
        raise OpenSeedReleaseV10Error("Abilene artifact tree pin differs")


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base = v2._json_object(
        v2._ordinary_file(project_root / V64_DEFINITION, "v64 definition"),
        "v64 definition",
        canonical=True,
    )
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV10Error("v65 must preserve the frozen v64 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")
    if definition["curated_inputs"] != _expected_v65_rows(project_root):
        raise OpenSeedReleaseV10Error("curated inputs are not the exact v65 successor")
    _validate_source_artifact(project_root)
    paths = [row["path"] for row in definition["curated_inputs"]]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV10Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in definition["curated_inputs"]:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV10Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV10Error(f"curated input changed: {record['path']}")
        source = v2._json_object(
            raw, f"curated input {record['path']}", canonical=False
        )
        if record["path"] in ADDITION_PINS:
            _validate_local_research_day(source, record["path"])
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV10Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 317, "1.1": 47}:
        raise OpenSeedReleaseV10Error(f"v65 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v65 import augment_release_documents

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v65-offline-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        try:
            epoch_result = EpochAIAdapter().import_file(
                connection,
                archive,
                map_html=map_path,
                retrieved_at=definition["epoch_capture"]["retrieved_at"],
                as_of_date=definition["build"]["as_of"],
            )
            if (
                json.loads(json.dumps(asdict(epoch_result)))
                != definition["expected_epoch_result"]
            ):
                raise OpenSeedReleaseV10Error(
                    "Epoch import result or warning set differs"
                )
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV10Error(
                            f"schema 1.0 source has multiple timestamps: {path.name}"
                        )
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection, path, retrieved_at=next(iter(timestamps))
                    )
                else:
                    result = CuratedOfficialSourceAdapterV11().import_file(
                        connection, path, recorded_at=V11_RECORDED_AT
                    )
                if result.warnings:
                    raise OpenSeedReleaseV10Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV10Error(
                    "reconstructed database is invalid: " + "; ".join(errors)
                )
            documents = build_release_documents(
                connection,
                as_of=definition["build"]["as_of"],
                recorded_at=definition["build"]["recorded_at"],
                publication_contract_version=4,
            )
            return augment_release_documents(
                documents, as_of=definition["build"]["as_of"]
            )
        finally:
            connection.close()


def validate_open_seed_release_v10(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v64 lineage and reconstruct every v65 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v64(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV10Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV10Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV10Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if (
        not isinstance(expected_release, dict)
        or "manifest_sha256" not in expected_release
    ):
        raise OpenSeedReleaseV10Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV10Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV10Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV10Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV10Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV10Error(f"release file changed: {filename}")

    summary = v2._json_object(
        v2._ordinary_file(release / "summary.json", "release summary"),
        "release summary",
        canonical=True,
    )
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV10Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV10Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV10Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV10Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV10Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV10Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
