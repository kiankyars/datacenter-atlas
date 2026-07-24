"""Strict validator for the frozen open-seed v59 narrow successor.

V59 is the exact 2026-07-20 successor of frozen v58.  It preserves the Epoch
observation date, replaces five coordinate-less curated records with their
audited coordinate successors, and adds seven official-source records.  The
next-local-day Pure record, stale STT Johor record, and separate historical
tranche are outside this release.
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
from . import open_seed_release_v3 as v3
from .publication_release import build_release_documents
from .service import validate_database


FROZEN_FILE_MODE = 0o444
FROZEN_DIRECTORY_MODE = 0o555

V58_DEFINITION = "sources/open-seed-2026-07-20-v58.json"
V58_RELEASE = "releases/2026-07-20-open-seed-v58"
V58_DEFINITION_SHA256 = (
    "76b9200c892c62a579007f7024a3802019c8b06ad34e0dbbd42e5529fb391a74"
)
V58_MANIFEST_SHA256 = (
    "52261833ac75e2153d4298352a517a0beecb4938f4098ca0f280da3cf367d83e"
)
V58_TREE_SHA256 = "6534726c7011dcf3af9664f4bd796509a4535cfbca75d507aa3ffea2a227bc0f"

RELEASE_ID = "2026-07-20-open-seed-v59"
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-21T03:00:00Z"
V11_RECORDED_AT = RECORDED_AT

REPLACEMENT_PINS = {
    "sources/curated-official-2026-07-20-verne-mantsala-current-development.json": (
        "sources/curated-official-2026-07-20-verne-mantsala-current-development-v2.json",
        "349e9d131a5f708359f062d929c9a762680682b3c23ffe35302e3b4fe653b64a",
    ),
    "sources/curated-official-2026-07-20-penzance-chantilly-premier-current-build.json": (
        "sources/curated-official-2026-07-20-penzance-chantilly-premier-current-build-v2.json",
        "4647a868f77c225b797502be216a12a1b977fd1657d8c996f9bc5e56bdb9cf85",
    ),
    "sources/curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json": (
        "sources/curated-official-2026-07-20-t5-chicago-iii-northlake-current-build-v2.json",
        "35734efff320ff37e70a2af66f1dd9ddb019178504de3d91f637b9e65778e565",
    ),
    "sources/curated-official-2026-07-20-cra-prague-gateway-first-building.json": (
        "sources/curated-official-2026-07-20-cra-prague-gateway-first-building-v2.json",
        "1b9d43d074e15effa188aca522acabb430e4b78954b99f23e6b53edce415cc2a",
    ),
    "sources/curated-official-2026-07-20-maincubes-fra03-phase-2.json": (
        "sources/curated-official-2026-07-20-maincubes-fra03-phase-2-v2.json",
        "cd6f10953cb892134e61384513821cc12ba5e66ce9a2ae1deb539e6d1a59ba38",
    ),
}

ADDITION_PINS = {
    "sources/curated-official-2026-07-20-kazakhstan-data-center-valley-ekibastuz.json": (
        "5ef79026207a4da1c904c39659e4cf700a09841c2c8c4979482c859d15d17abc"
    ),
    "sources/curated-official-2026-07-20-vantage-va4-fredericksburg-current-build.json": (
        "ddde1773cfa97ba3ed167ca1737c08bc5ac8d88657049852076b1a2d8ac0ea2b"
    ),
    "sources/curated-official-2026-07-20-stt-fairview-1-current-rollout.json": (
        "2a3d4a19385acd90f7b1f23480173bbddad52dbf348a9605e2ea40806202d249"
    ),
    "sources/curated-official-2026-07-20-stt-cavite-2-phase-1-current-status.json": (
        "b223cd9b9ac5e179dc4edaf4f1b8eefd18737d2149f5c28a4937a65f5752f0c9"
    ),
    "sources/curated-official-2026-07-20-kio-mex8-mexico-city-current-build.json": (
        "390e80122c70d90592488ad2dce0d95c90c9d5d01197659d34b8ba782b2828d1"
    ),
    "sources/curated-official-2026-07-20-google-saint-ghislain-seventh-building-expansion.json": (
        "23ae233655b96e7837919578318ff246af18bc9cfe96eaef4613983c0910623a"
    ),
    "sources/curated-official-2026-07-20-scala-smextp01-tepotzotlan-current-status.json": (
        "0c528badf9cdd2dd0a7d4a8cfef1fc883f5cbec85025c36a2ca2d46c5596ca86"
    ),
}

STALE_EXCLUSIONS = frozenset(
    {
        "sources/curated-official-2026-07-20-stt-johor-1-current-build.json",
    }
)
HISTORICAL_EXCLUSIONS = frozenset(
    {
        "sources/curated-official-2026-07-20-wingu-addis-ababa-groundbreaking.json",
        "sources/curated-official-2026-07-20-africa-data-centres-sameer-nairobi-expansion.json",
        "sources/curated-official-2026-07-20-raxio-civ1-abidjan.json",
        "sources/curated-official-2026-07-20-zdata-gp3-johor-building-1-topout.json",
        "sources/curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json",
        "sources/curated-official-2026-07-20-africa-data-centres-samrand-expansion.json",
        "sources/curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json",
        "sources/curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json",
    }
)
PENDING_NEXT_DAY_EXCLUSIONS = frozenset(
    {
        "sources/curated-official-2026-07-21-pure-dc-ams01-amsterdam-westpoort-current-build.json",
    }
)


class OpenSeedReleaseV4Error(ValueError):
    """Raised when the v59 definition, inputs, or release differ."""


def validate_frozen_v58(project_root: Path) -> dict[str, Any]:
    """Pin and validate the sole permitted v59 base."""

    definition = project_root / V58_DEFINITION
    release = project_root / V58_RELEASE
    if v2._sha256(v2._ordinary_file(definition, "v58 definition")) != (
        V58_DEFINITION_SHA256
    ):
        raise OpenSeedReleaseV4Error("frozen v58 definition hash differs")
    if v2._sha256(v2._ordinary_file(release / "manifest.json", "v58 manifest")) != (
        V58_MANIFEST_SHA256
    ):
        raise OpenSeedReleaseV4Error("frozen v58 manifest hash differs")
    if v2._tree_digest(release) != V58_TREE_SHA256:
        raise OpenSeedReleaseV4Error("frozen v58 release tree differs")
    try:
        return v3.validate_open_seed_release_v3(definition, release)
    except ValueError as error:
        raise OpenSeedReleaseV4Error("frozen v58 validation failed") from error


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
        raise OpenSeedReleaseV4Error("definition schema is invalid")
    if document["publication_contract_version"] != 4:
        raise OpenSeedReleaseV4Error("publication contract version must be 4")
    if definition_path.parent.name != "sources":
        raise OpenSeedReleaseV4Error("definition must reside in the sources directory")
    project_root = definition_path.parent.parent
    if document["release_id"] != RELEASE_ID:
        raise OpenSeedReleaseV4Error("release_id must identify frozen v59")
    if document["scope"] != {
        "commercial_census_parity_claimed": False,
        "epoch_selected_site_count_is_global_census": False,
        "orphan_timeline_imported": False,
        "source_scoped_estimates_only": True,
    }:
        raise OpenSeedReleaseV4Error("definition scope guardrails are invalid")
    if document["build"] != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise OpenSeedReleaseV4Error("v59 build timestamp contract differs")
    expected_freshness = {
        "current_construction_inferred": False,
        "current_status_classification": "unknown",
        "historical_inputs_excluded": sorted(HISTORICAL_EXCLUSIONS),
        "lifecycle_status_semantics": "last_observed",
        "next_local_day_inputs_pending": sorted(PENDING_NEXT_DAY_EXCLUSIONS),
        "recent_observation_max_age_days": 90,
        "stale_input_max_age_days": 365,
        "stale_inputs_excluded": sorted(STALE_EXCLUSIONS),
    }
    if document["freshness_contract"] != expected_freshness:
        raise OpenSeedReleaseV4Error("v59 freshness contract differs")
    return document, definition_path, project_root


def _expected_v59_rows(project_root: Path) -> list[dict[str, str]]:
    raw = v2._ordinary_file(project_root / V58_DEFINITION, "v58 definition")
    base = v2._json_object(raw, "v58 definition", canonical=True)
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 327:
        raise OpenSeedReleaseV4Error("v58 curated inventory differs")
    selected: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise OpenSeedReleaseV4Error("v58 curated row is invalid")
        path, digest = row["path"], row["sha256"]
        if not isinstance(path, str) or not isinstance(digest, str) or path in selected:
            raise OpenSeedReleaseV4Error("v58 curated inventory is invalid")
        selected[path] = digest
    for predecessor, (successor, digest) in REPLACEMENT_PINS.items():
        if predecessor not in selected or successor in selected:
            raise OpenSeedReleaseV4Error("coordinate replacement boundary differs")
        del selected[predecessor]
        source = project_root / successor
        if v2._sha256(v2._ordinary_file(source, successor)) != digest:
            raise OpenSeedReleaseV4Error(
                f"accepted coordinate successor hash differs: {successor}"
            )
        selected[successor] = digest
    for path, digest in ADDITION_PINS.items():
        if path in selected:
            raise OpenSeedReleaseV4Error("a v59 addition already occurs in v58")
        source = project_root / path
        if v2._sha256(v2._ordinary_file(source, path)) != digest:
            raise OpenSeedReleaseV4Error(f"accepted v59 source hash differs: {path}")
        selected[path] = digest
    excluded = STALE_EXCLUSIONS | HISTORICAL_EXCLUSIONS | PENDING_NEXT_DAY_EXCLUSIONS
    if excluded & set(selected):
        raise OpenSeedReleaseV4Error(
            "an excluded stale, historical, or next-local-day source was selected"
        )
    if len(selected) != 334:
        raise OpenSeedReleaseV4Error(
            f"expected 334 unique v59 inputs, found {len(selected)}"
        )
    return [
        {"path": path, "sha256": selected[path]} for path in sorted(selected)
    ]


def _validate_inputs(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, Path, list[tuple[Path, dict[str, Any]]], tuple[str, ...]]:
    base_raw = v2._ordinary_file(project_root / V58_DEFINITION, "v58 definition")
    base = v2._json_object(base_raw, "v58 definition", canonical=True)
    epoch = definition["epoch_capture"]
    if epoch != base["epoch_capture"]:
        raise OpenSeedReleaseV4Error("v59 must preserve the frozen v58 Epoch capture")
    archive = v2._repo_path(project_root, epoch["archive"], "Epoch archive")
    map_path = v2._repo_path(project_root, epoch["map"], "Epoch map")

    inputs = definition["curated_inputs"]
    if inputs != _expected_v59_rows(project_root):
        raise OpenSeedReleaseV4Error(
            "curated inputs are not the exact v59 replacement/addition successor"
        )
    paths = [row["path"] for row in inputs]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise OpenSeedReleaseV4Error("curated paths must be sorted and unique")
    v2._validate_selection(paths)

    cutoff = v2._instant(definition["build"]["recorded_at"], "build.recorded_at")
    parsed: list[tuple[Path, dict[str, Any]]] = []
    timestamps = [epoch["retrieved_at"]]
    schema_counts = {"1.0": 0, "1.1": 0}
    for record in inputs:
        path = v2._repo_path(project_root, record["path"], "curated input")
        raw = v2._ordinary_file(path, "curated input")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise OpenSeedReleaseV4Error(
                f"curated input mode must be 0644: {record['path']}"
            )
        if v2._sha256(raw) != record["sha256"]:
            raise OpenSeedReleaseV4Error(f"curated input changed: {record['path']}")
        source = v2._json_object(raw, f"curated input {record['path']}", canonical=False)
        version = source.get("schema_version")
        if version not in schema_counts:
            raise OpenSeedReleaseV4Error(f"unsupported curated schema: {version!r}")
        schema_counts[version] += 1
        timestamps.extend(
            v2._evidence_timestamps(source, cutoff=cutoff, label=record["path"])
        )
        parsed.append((path, source))
    if schema_counts != {"1.0": 317, "1.1": 17}:
        raise OpenSeedReleaseV4Error(f"v59 schema inventory differs: {schema_counts}")
    return archive, map_path, parsed, tuple(timestamps)


def _rebuild_documents(
    definition: Mapping[str, Any],
    archive: Path,
    map_path: Path,
    curated: list[tuple[Path, dict[str, Any]]],
) -> dict[str, str]:
    from .open_seed_v59 import augment_release_documents

    with tempfile.TemporaryDirectory(
        prefix="open-seed-v59-offline-", dir="/private/tmp"
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
                raise OpenSeedReleaseV4Error(
                    "Epoch import result or warning set differs"
                )
            for path, source in curated:
                if source["schema_version"] == "1.0":
                    timestamps = {item["retrieved_at"] for item in source["evidence"]}
                    if len(timestamps) != 1:
                        raise OpenSeedReleaseV4Error(
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
                    raise OpenSeedReleaseV4Error(
                        f"curated import warnings for {path.name}"
                    )
            errors = validate_database(connection)
            if errors:
                raise OpenSeedReleaseV4Error(
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


def validate_open_seed_release_v4(
    definition_path: str | Path,
    release_directory: str | Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate v58 lineage and reconstruct every v59 output byte twice."""

    definition, _, project_root = _definition(definition_path)
    validate_frozen_v58(project_root)
    archive, map_path, curated, timestamps = _validate_inputs(definition, project_root)
    if not timestamps:
        raise OpenSeedReleaseV4Error("retrieval inventory must not be empty")

    release = v2._lexical_absolute(release_directory)
    v2._reject_symlink_components(release, "release")
    is_private_stage = release.name.startswith(f".{definition['release_id']}.")
    if not release.is_dir() or (
        release.name != definition["release_id"] and not is_private_stage
    ):
        raise OpenSeedReleaseV4Error("release directory identity differs")
    entries = list(release.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise OpenSeedReleaseV4Error("release may contain only ordinary files")
    manifest_raw = v2._ordinary_file(release / "manifest.json", "release manifest")
    manifest = v2._json_object(manifest_raw, "release manifest", canonical=True)
    expected_release = definition["expected_release"]
    if not isinstance(expected_release, dict) or "manifest_sha256" not in expected_release:
        raise OpenSeedReleaseV4Error("expected_release definition is invalid")
    if v2._sha256(manifest_raw) != expected_release["manifest_sha256"]:
        raise OpenSeedReleaseV4Error("release manifest hash differs")
    for key, value in expected_release.items():
        if key != "manifest_sha256" and manifest.get(key) != value:
            raise OpenSeedReleaseV4Error(f"release manifest fact differs: {key}")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise OpenSeedReleaseV4Error("release manifest file inventory is invalid")
    expected_files = set(files) | {"manifest.json"}
    if {path.name for path in entries} != expected_files:
        raise OpenSeedReleaseV4Error("release file set differs from its manifest")
    for filename, record in files.items():
        raw = v2._ordinary_file(release / filename, f"release file {filename}")
        if not isinstance(record, dict) or record != {
            "bytes": len(raw),
            "sha256": v2._sha256(raw),
        }:
            raise OpenSeedReleaseV4Error(f"release file changed: {filename}")

    summary_raw = v2._ordinary_file(release / "summary.json", "release summary")
    summary = v2._json_object(summary_raw, "release summary", canonical=True)
    expected_summary = definition["expected_summary"]
    if not isinstance(expected_summary, dict) or any(
        summary.get(key) != value for key, value in expected_summary.items()
    ):
        raise OpenSeedReleaseV4Error("release summary facts differ")

    first = _rebuild_documents(definition, archive, map_path, curated)
    second = _rebuild_documents(definition, archive, map_path, curated)
    if first != second:
        raise OpenSeedReleaseV4Error("two offline reconstructions differ")
    if set(first) != expected_files:
        raise OpenSeedReleaseV4Error("offline reconstruction file set differs")
    for filename, text in first.items():
        if (release / filename).read_bytes() != text.encode("utf-8"):
            raise OpenSeedReleaseV4Error(
                f"offline reconstruction differs byte-for-byte: {filename}"
            )

    if require_frozen:
        if stat.S_IMODE(release.stat().st_mode) != FROZEN_DIRECTORY_MODE:
            raise OpenSeedReleaseV4Error("release root must have mode 0555")
        wrong_modes = [
            path.name
            for path in entries
            if stat.S_IMODE(path.stat().st_mode) != FROZEN_FILE_MODE
        ]
        if wrong_modes:
            raise OpenSeedReleaseV4Error(
                "release files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
