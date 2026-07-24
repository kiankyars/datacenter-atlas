"""Strict validator for the frozen open-seed v63 successor.

V63 remains on the 2026-07-20 local research day. It is the exact frozen-v62
successor that adds only four accepted schema-1.1 source packages: DataBank
IAD6, PowerHouse Irving Building 1, Core Scientific Dalton 4, and the bounded
QTS Fayetteville active-construction program.

The publication format remains contract version 4. Lifecycle values are
last-observed facts; this validator never turns them into current-status claims.
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
from . import open_seed_release_v7 as v7
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V62_DEFINITION = "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = "releases/2026-07-20-open-seed-v62"
V62_DEFINITION_SHA256 = (
    "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
)
V62_MANIFEST_SHA256 = "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
V62_TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"

RELEASE_ID = "2026-07-20-open-seed-v63"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T05:00:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS: dict[str, tuple[str, str]] = {}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json": (
        "ed121928047032b1740d7f6e30faa0fad7304cb6b5144c1b708812300ebe9a09"
    ),
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json": (
        "d5d1beb4bc0549b7921fa91d41f495a950439a61b9e464c704aa272e7798af31"
    ),
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json": (
        "03e3c1de817fba2a0b14d42ec5d063caf07ac23df4083b22bd0a99f6803d0990"
    ),
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json": (
        "d5210ad0ba71d90aef22128e4642cb2ab18fe78325d9491a8d58d97d010731a0"
    ),
}

STALE_EXCLUSIONS = v7.STALE_EXCLUSIONS
PENDING_NEXT_DAY_EXCLUSIONS = v7.PENDING_NEXT_DAY_EXCLUSIONS
OUT_OF_SCOPE_EXCLUSIONS: frozenset[str] = frozenset()


class OpenSeedReleaseV8Error(ValueError):
    """Raised when the v63 definition, inputs, or release differ."""


def freshness_contract() -> dict[str, Any]:
    """Return the unchanged last-observed and calendar-boundary contract."""

    return v7.freshness_contract()


def validate_frozen_v62(project_root: Path) -> dict[str, Any]:
    """Pin and fully replay the sole permitted v63 base."""

    definition = project_root / V62_DEFINITION
    release = project_root / V62_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v62 definition")) != (
        V62_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV8Error("frozen v62 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v62 manifest")) != (
        V62_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV8Error("frozen v62 manifest hash differs")
    if v2._tree_digest(release) != V62_TREE_SHA256:
        raise OpenSeedReleaseV8Error("frozen v62 release tree differs")
    try:
        return v7.validate_open_seed_release_v7(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV8Error("frozen v62 validation failed") from error


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
        raise OpenSeedReleaseV8Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV8Error("publication contract version must remain 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV8Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV8Error("release_id must identify frozen v63")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV8Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV8Error("v63 build timestamp contract differs")
    if document["freshness_contract"] != freshness_contract():
        raise OpenSeedReleaseV8Error("v63 freshness contract differs")
    return document, definition_path, project_root


def _expected_v63_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V62_DEFINITION, "v62 definition")
    base = v2._json_object(raw, "v62 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 350:
        raise OpenSeedReleaseV8Error("v62 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV8Error("v62 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV8Error("v62 curated inventory is invalid")
        selected[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV8Error("a v63 addition already occurs in v62")
        if v2._sha256(v2._ordinary_file(project_root / path, path)) != digest:
            raise OpenSeedReleaseV8Error(f"accepted v63 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV8Error(
            "an excluded stale or next-day source was selected"
        )
    if len(selected) != 354:
        raise OpenSeedReleaseV8Error(
            f"expected 354 unique v63 inputs, found {len(selected)}"
        )
    return [{"path": path, "sha256": selected[path]} for path in sorted(selected)]


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base = v2._json_object(
        v2._ordinary_file(project_root / V62_DEFINITION, "v62 definition"),
        "v62 definition",
        canonical=True,
    )
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV8Error("v63 must preserve the frozen v62 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")
    if definition["curated_inputs"] != _expected_v63_rows(project_root):
        raise OpenSeedReleaseV8Error("curated inputs are not the exact v63 successor")
    paths = [row["path"] for row in definition["curated_inputs"]]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV8Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in definition["curated_inputs"]:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV8Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV8Error(f"curated input changed: {record['path']}")
        source = v2._json_object(
            raw, f"curated input {record['path']}", canonical=False
        )
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV8Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 316, "1.1": 38}:
        raise OpenSeedReleaseV8Error(f"v63 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v63 import augment_release_documents

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v63-offline-", dir="/private/tmp"
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
                raise OpenSeedReleaseV8Error(
                    "Epoch import result or warning set differs"
                )
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV8Error(
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
                    raise OpenSeedReleaseV8Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV8Error(
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


def validate_open_seed_release_v8(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v62 lineage and reconstruct every v63 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v62(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV8Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV8Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV8Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if (
        not isinstance(expected_release, dict)
        or "manifest_sha256" not in expected_release
    ):
        raise OpenSeedReleaseV8Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV8Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV8Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV8Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV8Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV8Error(f"release file changed: {filename}")

    summary = v2._json_object(
        v2._ordinary_file(release / "summary.json", "release summary"),
        "release summary",
        canonical=True,
    )
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV8Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV8Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV8Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV8Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV8Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV8Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
