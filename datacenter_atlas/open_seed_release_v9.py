"""Strict validator for the frozen open-seed v64 successor.

V64 remains on the 2026-07-20 local research day. It is the exact frozen-v63
successor that adds only nine accepted schema-1.1 packages: four sibling
EcoDataCenter project records plus ESR Bupyeong KR1, ESR Kwai Chung HK1 Phase
2, Teraco CT1, CDC Beard BE1, and Digital Realty VIE13 Phase 1.

The publication format remains contract version 4. Lifecycle values are
last-observed facts; this validator never turns them into current-status claims.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
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
from . import open_seed_release_v8 as v8
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V63_DEFINITION = "sources/open-seed-2026-07-20-v63.json"
V63_RELEASE = "releases/2026-07-20-open-seed-v63"
V63_DEFINITION_SHA256 = (
    "13bfdcbda96769de1a39e1bc41e67ad7e0a6e98d026fedda3384fbd89bc8adff"
)
V63_MANIFEST_SHA256 = "8ee3539f639641c7f97827ba7a21c13b7e907881ba858970e701675510eab4ba"
V63_TREE_SHA256 = "44e7df9300c40fc76a0f9e55bc6de05f1a3f11a1ef39926e38fff7bb8b8127f4"

RELEASE_ID = "2026-07-20-open-seed-v64"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T05:50:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS: dict[str, tuple[str, str]] = {}
ADDITION_PINS = {
    "sources/curated-official-2026-07-20-cdc-beard-be1.json": (
        "0ba3f8fc5bc23a82b6b2b49c578a1518f94aa8122bcd19c6a6f5246f24989b5a"
    ),
    "sources/curated-official-2026-07-20-digital-realty-vie13-phase-1.json": (
        "ddf94f3bbf02d4a4d9a4afeafc4c9eb5ce76f817f8d93b1f9033869801d14e4e"
    ),
    "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json": (
        "2dfcc8c092e81150910adc00e3122c383cc21067a521def2a10c65ad08846e1d"
    ),
    "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json": (
        "e3d5cee16c35d708847b084f3993e60f41ae12281c7aca5a411792110e7ff41f"
    ),
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json": (
        "9d45a25c2eff5eebc59d9a070f741f2173acab709b633509b2e66e61583478d0"
    ),
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json": (
        "72c1901834a6d8f31c985b342572d8de008772117704fa5e5ab5c2f4d9e79af3"
    ),
    "sources/curated-official-2026-07-20-esr-bupyeong-kr1.json": (
        "7deff254b1367a8e84e8ed68c766d617cf5061732ca230b625cec23fbb7448cf"
    ),
    "sources/curated-official-2026-07-20-esr-kwai-chung-hk1-phase-2.json": (
        "ecee59847d664d6ca65856cdce1f83c6755218db6cd74449dcce1540111c69f2"
    ),
    "sources/curated-official-2026-07-20-teraco-ct1-rondebosch-expansion.json": (
        "2a73a6dacb84bfcd5cee8e51bf08955f9863dca328117833d94d06634fa43eea"
    ),
}

STALE_EXCLUSIONS = v8.STALE_EXCLUSIONS
PENDING_NEXT_DAY_EXCLUSIONS = v8.PENDING_NEXT_DAY_EXCLUSIONS
OUT_OF_SCOPE_EXCLUSIONS: frozenset[str] = frozenset()


class OpenSeedReleaseV9Error(ValueError):
    """Raised when the v64 definition, inputs, or release differ."""


def freshness_contract() -> dict[str, Any]:
    """Return the unchanged last-observed and calendar-boundary contract."""

    return v8.freshness_contract()


def validate_frozen_v63(project_root: Path) -> dict[str, Any]:
    """Pin and fully replay the sole permitted v64 base."""

    definition = project_root / V63_DEFINITION
    release = project_root / V63_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v63 definition")) != (
        V63_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV9Error("frozen v63 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v63 manifest")) != (
        V63_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV9Error("frozen v63 manifest hash differs")
    if v2._tree_digest(release) != V63_TREE_SHA256:
        raise OpenSeedReleaseV9Error("frozen v63 release tree differs")
    try:
        return v8.validate_open_seed_release_v8(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV9Error("frozen v63 validation failed") from error


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
        raise OpenSeedReleaseV9Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV9Error("publication contract version must remain 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV9Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV9Error("release_id must identify frozen v64")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV9Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV9Error("v64 build timestamp contract differs")
    if document["freshness_contract"] != freshness_contract():
        raise OpenSeedReleaseV9Error("v64 freshness contract differs")
    return document, definition_path, project_root


def _expected_v64_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V63_DEFINITION, "v63 definition")
    base = v2._json_object(raw, "v63 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 354:
        raise OpenSeedReleaseV9Error("v63 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV9Error("v63 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV9Error("v63 curated inventory is invalid")
        selected[path] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV9Error("a v64 addition already occurs in v63")
        if v2._sha256(v2._ordinary_file(project_root / path, path)) != digest:
            raise OpenSeedReleaseV9Error(f"accepted v64 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS | OUT_OF_SCOPE_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV9Error(
            "an excluded stale or next-day source was selected"
        )
    if len(selected) != 363:
        raise OpenSeedReleaseV9Error(
            f"expected 363 unique v64 inputs, found {len(selected)}"
        )
    return [{"path": path, "sha256": selected[path]} for path in sorted(selected)]


def _validate_local_research_day(source: Mapping[str, Any], label: str) -> None:
    """Reject UTC-date leakage into Jul 20 identifiers or normalized facts."""

    if "2026-07-21" in label:
        raise OpenSeedReleaseV9Error(
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
            raise OpenSeedReleaseV9Error(
                f"invalid normalized row list: {label}: {field}"
            )
        dated_rows.extend(row for row in rows if isinstance(row, Mapping))
    for row in dated_rows:
        observed = row.get("as_of_date")
        if not isinstance(observed, str) or date.fromisoformat(observed) > cutoff:
            raise OpenSeedReleaseV9Error(
                f"normalized fact crosses the Jul 20 research day: {label}"
            )
        for key in ("stable_key", "evidence_key"):
            value = row.get(key)
            if isinstance(value, str) and "2026-07-21" in value:
                raise OpenSeedReleaseV9Error(
                    f"next-day normalized identifier is forbidden: {label}"
                )
    for evidence in source.get("evidence", []):
        if not isinstance(evidence, Mapping):
            raise OpenSeedReleaseV9Error(f"invalid evidence row: {label}")
        if "2026-07-21" in str(evidence.get("key", "")):
            raise OpenSeedReleaseV9Error(
                f"next-day evidence identifier is forbidden: {label}"
            )
        artifact_id = evidence.get("metadata", {}).get("capture_artifact_id")
        if isinstance(artifact_id, str) and "2026-07-21" in artifact_id:
            raise OpenSeedReleaseV9Error(
                f"next-day artifact identifier is forbidden: {label}"
            )


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base = v2._json_object(
        v2._ordinary_file(project_root / V63_DEFINITION, "v63 definition"),
        "v63 definition",
        canonical=True,
    )
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV9Error("v64 must preserve the frozen v63 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")
    if definition["curated_inputs"] != _expected_v64_rows(project_root):
        raise OpenSeedReleaseV9Error("curated inputs are not the exact v64 successor")
    paths = [row["path"] for row in definition["curated_inputs"]]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV9Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in definition["curated_inputs"]:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV9Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV9Error(f"curated input changed: {record['path']}")
        source = v2._json_object(
            raw, f"curated input {record['path']}", canonical=False
        )
        if record["path"] in ADDITION_PINS:
            _validate_local_research_day(source, record["path"])
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV9Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 316, "1.1": 47}:
        raise OpenSeedReleaseV9Error(f"v64 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v64 import augment_release_documents

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v64-offline-", dir="/private/tmp"
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
                raise OpenSeedReleaseV9Error(
                    "Epoch import result or warning set differs"
                )
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV9Error(
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
                    raise OpenSeedReleaseV9Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV9Error(
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


def validate_open_seed_release_v9(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v63 lineage and reconstruct every v64 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v63(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV9Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV9Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV9Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if (
        not isinstance(expected_release, dict)
        or "manifest_sha256" not in expected_release
    ):
        raise OpenSeedReleaseV9Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV9Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV9Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV9Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV9Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV9Error(f"release file changed: {filename}")

    summary = v2._json_object(
        v2._ordinary_file(release / "summary.json", "release summary"),
        "release summary",
        canonical=True,
    )
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV9Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV9Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV9Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV9Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV9Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV9Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
