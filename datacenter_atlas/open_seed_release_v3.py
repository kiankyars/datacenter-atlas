"""Strict additive validator for the frozen open-seed v58 release.

V58 is the exact seven-source successor of frozen v57.  The v57 validator
continues to own its release; this module pins and validates v57 first, then
reconstructs every v58 output byte twice without network access.
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
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V57_DEFINITION = "sources/open-seed-2026-07-20-v57.json"
V57_RELEASE = "releases/2026-07-20-open-seed-v57"
V57_DEFINITION_SHA256 = (
    "421a8992616cea1e0b9779d47ed1f7052465cbf59c22c3d00b8a79d9463c1bc8"
)
V57_MANIFEST_SHA256 = (
    "37f33308466d3707e2bf9f5225bd3c3546dcb2539e7f537286dd8237728d6403"
)
V57_TREE_SHA256 = "2651d54295954e4a791e0dbc44b9e2f6947f6b519473468bcec5277299f4c8fe"

RELEASE_ID = "2026-07-20-open-seed-v58"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T00:21:00Z"
V11_RECORDED_AT = "2026-07-20T23:56:00Z"

ADDITION_PINS = {
    "sources/curated-official-2026-07-20-cra-prague-gateway-first-building.json": (
        "ce19862d4e24e5c0c3006e842c9baaf89ea12137eceb2b579e40bcf716c1f64a"
    ),
    "sources/curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json": (
        "ea26383ca36ae92f83141d4877d4bd3c46adb24fbb51c1545e574678267c493d"
    ),
    "sources/curated-official-2026-07-20-maincubes-fra03-phase-2.json": (
        "ad5013be9eab2b0aad9d43883b3d7d39f297d9d8e7cbb256c4d12fb84179ebee"
    ),
    "sources/curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json": (
        "07c7a75bb64188a415ac143d8077939979e68fac6b27cae3ef93de70a9502922"
    ),
    "sources/curated-official-2026-07-20-penzance-chantilly-premier-current-build.json": (
        "b78c30cb8ed322dcdae3ce555c9c8f2e90c5de771184901643b64d2653e7aceb"
    ),
    "sources/curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json": (
        "4952c3aa872d8ec99f3b9526270b9cd129fdaf454759904eaea01d854d785dd2"
    ),
    "sources/curated-official-2026-07-20-verne-mantsala-current-development.json": (
        "7e993fbb78c72340127b6646ff90fa232595b3eb7d8c3c72c88153550d3e5203"
    ),
}
ADDITIONS = frozenset(ADDITION_PINS)


class OpenSeedReleaseV3Error(ValueError):
    """Raised when a v58 definition, input, or release differs."""


def validate_frozen_v57(project_root: Path) -> dict[str, Any]:
    """Pin and validate the sole permitted v58 base."""

    definition = project_root / V57_DEFINITION
    release = project_root / V57_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v57 definition")) != (
        V57_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV3Error("frozen v57 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v57 manifest")) != (
        V57_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV3Error("frozen v57 manifest hash differs")
    if v2._tree_digest(release) != V57_TREE_SHA256:
        raise OpenSeedReleaseV3Error("frozen v57 release tree differs")
    try:
        return v2.validate_open_seed_release_v2(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV3Error("frozen v57 validation failed") from error


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
        "publication_contract_version",
        "release_id",
        "schema_version",
        "scope",
    }
    if set(document) != expected_keys or document["schema_version"] != 1:
        raise OpenSeedReleaseV3Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV3Error("publication contract version must be 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV3Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV3Error("release_id must identify frozen v58")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV3Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV3Error("v58 build timestamp contract differs")
    return document, definition_path, project_root


def _expected_v58_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V57_DEFINITION, "v57 definition")
    base = v2._json_object(raw, "v57 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 320:
        raise OpenSeedReleaseV3Error("v57 curated inventory differs")
    base_by_path: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV3Error("v57 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if (
            not isinstance(path, str)
            or not isinstance(digest, str)
            or path in base_by_path
        ):
            raise OpenSeedReleaseV3Error("v57 curated inventory is invalid")
        base_by_path[path] = digest
    if ADDITIONS & set(base_by_path):
        raise OpenSeedReleaseV3Error("a v58 addition already occurs in v57")
    selected = [
        {"path": path, "sha256": digest}
        for path, digest in base_by_path.items()
    ]
    for path, digest in ADDITION_PINS.items():
        source = project_root / path
        if v2._sha256(v2._ordinary_file(source, path)) != digest:
            raise OpenSeedReleaseV3Error(f"accepted v58 source hash differs: {path}")
        selected.append({"path": path, "sha256": digest})
    return sorted(selected, key=lambda row: row["path"])


def _validate_selection(paths: list[str]) -> None:
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV3Error("curated paths must be sorted and unique")
    if not ADDITIONS.issubset(paths):
        raise OpenSeedReleaseV3Error("all seven v58 additions must be selected")
    v2._validate_selection(paths)


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base_raw = v2._ordinary_file(project_root / V57_DEFINITION, "v57 definition")
    base = v2._json_object(base_raw, "v57 definition", canonical=True)
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV3Error("v58 must preserve the frozen v57 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")

    inputs = definition["curated_inputs"]
    if inputs != _expected_v58_rows(project_root):
        raise OpenSeedReleaseV3Error(
            "curated inputs are not the exact seven-addition v57 successor"
        )
    if len(inputs) != 327:
        raise OpenSeedReleaseV3Error("v58 must contain exactly 327 curated inputs")
    paths = [row["path"] for row in inputs]
    _validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in inputs:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV3Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV3Error(f"curated input changed: {record['path']}")
        source = v2._json_object(raw, f"curated input {record['path']}", canonical=False)
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV3Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        source_times = v2._evidence_timestamps(
            source, cutoff=cutoff, label=record["path"]
        )
        timestamps.extend(source_times)
        parsed.append((path, source))
    if schema_counts != {"1.0": 322, "1.1": 5}:
        raise OpenSeedReleaseV3Error(f"v58 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v58-offline-", dir="/private/tmp"
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
            normalized = json.loads(json.dumps(asdict(epoch_result)))
            if normalized != definition["expected_epoch_result"]:
                raise OpenSeedReleaseV3Error(
                    "Epoch import result or warning set differs"
                )
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {
                        item["retrieved_at"] for item in source["evidence"]
                    }
                    CuratedOfficialSourceAdapter().import_file(
                        connection, path, retrieved_at=next(iter(timestamps))
                    )
                else:
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, path, recorded_at=V11_RECORDED_AT
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV3Error(
                    "reconstructed database is invalid: " + "; ".join(errors)
                )
            return build_release_documents(
                connection,
                as_of=definition["build"]["as_of"],
                recorded_at=definition["build"]["recorded_at"],
                publication_contract_version=4,
            )
        finally:
            connection.close()


def validate_open_seed_release_v3(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v57 lineage and reconstruct every v58 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v57(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV3Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV3Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV3Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseV3Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV3Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV3Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV3Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV3Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV3Error(f"release file changed: {filename}")

    summary_raw = v2._ordinary_file(release / "summary.json", "release summary")
    summary = v2._json_object(summary_raw, "release summary", canonical=True)
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV3Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV3Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV3Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV3Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV3Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV3Error(
                "release files must have mode 0444: "
                + ", ".join(sorted(wrong_modes))
            )
    return manifest
