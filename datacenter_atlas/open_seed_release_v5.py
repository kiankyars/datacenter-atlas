"""Strict validator for the frozen open-seed v60 successor.

V60 remains on the 2026-07-20 local research day.  It is an exact successor
of frozen v59: one Bahrain record is replaced by its operational-status
successor, five current Israel projects and eight historical-build records are
added, and the next-local-day Pure AMS01 record remains outside the release.

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
from . import open_seed_release_v4 as v4
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V59_DEFINITION = "sources/open-seed-2026-07-20-v59.json"
V59_RELEASE = "releases/2026-07-20-open-seed-v59"
V59_DEFINITION_SHA256 = (
    "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
)
V59_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
V59_TREE_SHA256 = "53cb173fb0e07b8dba8f9bb974cc533b38ba006590583725baf122cb8ba8d636"

RELEASE_ID = "2026-07-20-open-seed-v60"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T03:40:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS = {
    "sources/curated-official-2026-07-20-stc-bahrain-dc.json": (
        "sources/curated-official-2026-07-20-stc-bahrain-dc-v2.json",
        "4d8976e26d77a9b5aa9b4a247456af3b9274991e9f0751a73b64f862fc2af02e",
    ),
}

ISRAEL_ADDITION_PINS = {
    "sources/curated-official-2026-07-20-israel-medone-ky1-kfar-yona.json": (
        "ee16cdba9d19828e32384806c2a59836d390c26470867f1be9512689f4270424"
    ),
    "sources/curated-official-2026-07-20-israel-mega-mdcil1-modiin-phase-b.json": (
        "3b8a95689406e24a26dc2e8ca6bdb6d6d10c2324fdc6e77b091c4ccb1fcf6830"
    ),
    "sources/curated-official-2026-07-20-israel-mega-mdcil2-masmiyya-phase-a.json": (
        "d390596c5e8371b89c0f632f426645cf098c55605f9940bceae4d98cc7c896ba"
    ),
    "sources/curated-official-2026-07-20-israel-mega-mdcil4-beit-shemesh-phase-a.json": (
        "365d02ff0a8078568249570fd2149aa65b2dd80309e354e6aabe1ff3f2cd3d4e"
    ),
    "sources/curated-official-2026-07-20-israel-ned-levinstein-alfa-netanya-phase-a.json": (
        "33d2cc327590ba2180fc0de3893f43e9ee6b939809f28aec1d11c3c12e8eb876"
    ),
}

HISTORICAL_ADDITION_PINS = {
    "sources/curated-official-2026-07-20-africa-data-centres-sameer-nairobi-expansion.json": (
        "6ac50d29d73e8fe6ed1ff88703d5d26c9435d8a7526e983b4e40097a1fdeb7e2"
    ),
    "sources/curated-official-2026-07-20-africa-data-centres-samrand-expansion.json": (
        "41abf2616b0ec557131be6af84d5223bb033bcafa2e0ba2e62c124cbd07453a4"
    ),
    "sources/curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json": (
        "48eead465a7de1af47770a14cf41579ffd822d7b8b1bf0a9ca2307701beb5d7d"
    ),
    "sources/curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json": (
        "757642d2a9bdfb64464eb143444d27bd38341e95c251f7763ecd711b5099b984"
    ),
    "sources/curated-official-2026-07-20-raxio-civ1-abidjan.json": (
        "56ac63bf426f61034703d24a5e2b9213b0fc737cd487909fd565d3f3302200f3"
    ),
    "sources/curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json": (
        "a1aa648483ac151ce6d385cbfe842debddd32216f87b9032d70e9fcd0d2920a2"
    ),
    "sources/curated-official-2026-07-20-wingu-addis-ababa-groundbreaking.json": (
        "22c7b4c3f63971afd896a468d23d37cff5f22ee740ef606e48ebc1e20c97bf3f"
    ),
    "sources/curated-official-2026-07-20-zdata-gp3-johor-building-1-topout.json": (
        "9b74c0b49088b5de4c5041ae71d6b217cc333ec9e206ef180cb5a8659e1be6e1"
    ),
}

ADDITION_PINS = ISRAEL_ADDITION_PINS | HISTORICAL_ADDITION_PINS

STALE_EXCLUSIONS = frozenset(
    {"sources/curated-official-2026-07-20-stt-johor-1-current-build.json"}
)
PENDING_NEXT_DAY_EXCLUSIONS = frozenset(
    {
        "sources/curated-official-2026-07-21-pure-dc-ams01-amsterdam-westpoort-current-build.json"
    }
)


class OpenSeedReleaseV5Error(ValueError):
    """Raised when the v60 definition, inputs, or release differ."""


def freshness_contract() -> dict[str, Any]:
    """Return the exact v60 last-observed and calendar-boundary contract."""

    return {
        "current_construction_inferred": False,
        "current_status_classification": "unknown",
        "historical_inputs_included_as_last_observed": sorted(
            HISTORICAL_ADDITION_PINS
        ),
        "lifecycle_status_semantics": "last_observed",
        "next_local_day_inputs_pending": sorted(PENDING_NEXT_DAY_EXCLUSIONS),
        "recent_observation_max_age_days": 90,
        "stale_input_max_age_days": 365,
        "stale_inputs_excluded": sorted(STALE_EXCLUSIONS),
    }


def validate_frozen_v59(project_root: Path) -> dict[str, Any]:
    """Pin and fully validate the sole permitted v60 base."""

    definition = project_root / V59_DEFINITION
    release = project_root / V59_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v59 definition")) != (
        V59_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV5Error("frozen v59 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v59 manifest")) != (
        V59_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV5Error("frozen v59 manifest hash differs")
    if v2._tree_digest(release) != V59_TREE_SHA256:
        raise OpenSeedReleaseV5Error("frozen v59 release tree differs")
    try:
        return v4.validate_open_seed_release_v4(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV5Error("frozen v59 validation failed") from error


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
        raise OpenSeedReleaseV5Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV5Error("publication contract version must remain 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV5Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV5Error("release_id must identify frozen v60")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV5Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV5Error("v60 build timestamp contract differs")
    if document["freshness_contract"] != freshness_contract():
        raise OpenSeedReleaseV5Error("v60 freshness contract differs")
    return document, definition_path, project_root


def _expected_v60_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V59_DEFINITION, "v59 definition")
    base = v2._json_object(raw, "v59 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 334:
        raise OpenSeedReleaseV5Error("v59 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV5Error("v59 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV5Error("v59 curated inventory is invalid")
        selected[path] = digest
    for predecessor, (successor, digest) in REPLACEMENT_PINS.items():
        if predecessor not in selected or successor in selected:
            raise OpenSeedReleaseV5Error("Bahrain replacement boundary differs")
        del selected[predecessor]
        if v2._sha256(v2._ordinary_file(project_root / successor, successor)) != digest:
            raise OpenSeedReleaseV5Error("accepted Bahrain successor hash differs")
        selected[successor] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV5Error("a v60 addition already occurs in v59")
        if v2._sha256(v2._ordinary_file(project_root / path, path)) != digest:
            raise OpenSeedReleaseV5Error(f"accepted v60 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV5Error("an excluded stale or next-day source was selected")
    if len(selected) != 347:
        raise OpenSeedReleaseV5Error(
            f"expected 347 unique v60 inputs, found {len(selected)}"
        )
    return [{"path": path, "sha256": selected[path]} for path in sorted(selected)]


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base = v2._json_object(
        v2._ordinary_file(project_root / V59_DEFINITION, "v59 definition"),
        "v59 definition",
        canonical=True,
    )
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV5Error("v60 must preserve the frozen v59 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")
    if definition["curated_inputs"] != _expected_v60_rows(project_root):
        raise OpenSeedReleaseV5Error("curated inputs are not the exact v60 successor")
    paths = [row["path"] for row in definition["curated_inputs"]]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV5Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in definition["curated_inputs"]:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV5Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV5Error(f"curated input changed: {record['path']}")
        source = v2._json_object(raw, f"curated input {record['path']}", canonical=False)
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV5Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 316, "1.1": 31}:
        raise OpenSeedReleaseV5Error(f"v60 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v60 import augment_release_documents

    with tempfile.TemporaryDirectory(prefix="open-seed-v60-offline-", dir="/private/tmp") as temporary:
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
                raise OpenSeedReleaseV5Error("Epoch import result or warning set differs")
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV5Error(
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
                    raise OpenSeedReleaseV5Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV5Error(
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


def validate_open_seed_release_v5(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v59 lineage and reconstruct every v60 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v59(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV5Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV5Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV5Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseV5Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV5Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV5Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV5Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV5Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV5Error(f"release file changed: {filename}")

    summary = v2._json_object(
        v2._ordinary_file(release / "summary.json", "release summary"),
        "release summary",
        canonical=True,
    )
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV5Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV5Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV5Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV5Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV5Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV5Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
