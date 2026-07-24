"""Strict validator for the frozen open-seed v62 successor.

V62 remains on the 2026-07-20 local research day. It is the exact frozen-v61
successor that adds only Applied Digital Polaris Forge 1 Building 2 Phase 1
and DataBank IAD5 Culpeper. Next-local-day Pure AMS01 remains outside the
release.

The publication format remains contract version 4.  Lifecycle values are
published only as last-observed facts; this validator never treats an old
construction start as proof of current construction.
"""

from __future__ import annotations

from dataclasses import asdict
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
from . import open_seed_release_v6 as v6
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V61_DEFINITION = "sources/open-seed-2026-07-20-v61.json"
V61_RELEASE = "releases/2026-07-20-open-seed-v61"
V61_DEFINITION_SHA256 = (
    "c407c73a069783ea75de8e3bc86bbfb8a15d71abb67de33e8ba3d3acc5a428e6"
)
V61_MANIFEST_SHA256 = (
    "6388b58b043f43fa2cdc02af31504cf18cc2ec334e14f2f2075f52b15204fd14"
)
V61_TREE_SHA256 = "de9a924113b5fae4ace596fdbd469f52a79646d0de677e7bcf17aedfa09693f2"

RELEASE_ID = "2026-07-20-open-seed-v62"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T04:35:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS: dict[str, tuple[str, str]] = {}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-applied-digital-pf1-building-2-phase-1-operational.json": (
        "e85a0998f34e851c03991434a048e40e140ce0de22d2600c0a5bf3b3b6429fd4"
    ),
    "sources/curated-official-2026-07-20-databank-iad5-culpeper.json": (
        "4e32216ede500acb5a75e64a6c4a8b29c655e5d6d505894d90dbafab85d3c747"
    ),
}

STALE_EXCLUSIONS = frozenset(
    {"sources/curated-official-2026-07-20-stt-johor-1-current-build.json"}
)
PENDING_NEXT_DAY_EXCLUSIONS = frozenset(
    {
        "sources/curated-official-2026-07-21-pure-dc-ams01-amsterdam-westpoort-current-build.json"
    }
)
OUT_OF_SCOPE_EXCLUSIONS: frozenset[str] = frozenset()


class OpenSeedReleaseV7Error(ValueError):
    """Raised when the v62 definition, inputs, or release differ."""


def freshness_contract() -> dict[str, Any]:
    """Return the exact v62 last-observed and calendar-boundary contract."""

    return v6.freshness_contract()


def validate_frozen_v61(project_root: Path) -> dict[str, Any]:
    """Pin and fully validate the sole permitted v62 base."""

    definition = project_root / V61_DEFINITION
    release = project_root / V61_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v61 definition")) != (
        V61_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV7Error("frozen v61 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v61 manifest")) != (
        V61_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV7Error("frozen v61 manifest hash differs")
    if v2._tree_digest(release) != V61_TREE_SHA256:
        raise OpenSeedReleaseV7Error("frozen v61 release tree differs")
    try:
        return v6.validate_open_seed_release_v6(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV7Error("frozen v61 validation failed") from error


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
        raise OpenSeedReleaseV7Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV7Error("publication contract version must remain 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV7Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV7Error("release_id must identify frozen v62")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV7Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV7Error("v62 build timestamp contract differs")
    if document["freshness_contract"] != freshness_contract():
        raise OpenSeedReleaseV7Error("v62 freshness contract differs")
    return document, definition_path, project_root


def _expected_v62_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V61_DEFINITION, "v61 definition")
    base = v2._json_object(raw, "v61 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 348:
        raise OpenSeedReleaseV7Error("v61 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV7Error("v61 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV7Error("v61 curated inventory is invalid")
        selected[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV7Error("a v62 addition already occurs in v61")
        if v2._sha256(v2._ordinary_file(project_root / path, path)) != digest:
            raise OpenSeedReleaseV7Error(f"accepted v62 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV7Error("an excluded stale or next-day source was selected")
    if len(selected) != 350:
        raise OpenSeedReleaseV7Error(
            f"expected 350 unique v62 inputs, found {len(selected)}"
        )
    return [{"path": path, "sha256": selected[path]} for path in sorted(selected)]


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base = v2._json_object(
        v2._ordinary_file(project_root / V61_DEFINITION, "v61 definition"),
        "v61 definition",
        canonical=True,
    )
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV7Error("v62 must preserve the frozen v61 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")
    if definition["curated_inputs"] != _expected_v62_rows(project_root):
        raise OpenSeedReleaseV7Error("curated inputs are not the exact v62 successor")
    paths = [row["path"] for row in definition["curated_inputs"]]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV7Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in definition["curated_inputs"]:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV7Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV7Error(f"curated input changed: {record['path']}")
        source = v2._json_object(raw, f"curated input {record['path']}", canonical=False)
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV7Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 316, "1.1": 34}:
        raise OpenSeedReleaseV7Error(f"v62 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v62 import augment_release_documents

    with tempfile.TemporaryDirectory(prefix="open-seed-v62-offline-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        try:
            epoch_result = EpochAIAdapter().import_file(
                connection,
                archive,
                map_html=map_path,
                retrieved_at=definition["epoch_capture"]["retrieved_at"],
                as_of_date=definition["build"]["as_of"],
            )
            if json.loads(json.dumps(asdict(epoch_result))) != definition["expected_epoch_result"]:
                raise OpenSeedReleaseV7Error("Epoch import result or warning set differs")
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV7Error(
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
                    raise OpenSeedReleaseV7Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV7Error(
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


def validate_open_seed_release_v7(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v61 lineage and reconstruct every v62 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v61(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV7Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV7Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV7Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseV7Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV7Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV7Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV7Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV7Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV7Error(f"release file changed: {filename}")

    summary = v2._json_object(
        v2._ordinary_file(release / "summary.json", "release summary"),
        "release summary",
        canonical=True,
    )
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV7Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV7Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV7Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV7Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV7Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV7Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
