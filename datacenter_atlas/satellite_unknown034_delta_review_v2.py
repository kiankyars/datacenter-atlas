"""Unambiguous publication successor to the frozen Unknown034 review v1.

Version 2 preserves every review disposition and comparison byte from v1 while
separating two facts that v1 expressed ambiguously: the bound source batches
did execute 21 change analyses, and this review publication build did not
reexecute the numerical processor.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import Any, Mapping

from . import satellite_unknown034_delta_review_v1 as predecessor


REVIEW_ID = "2026-07-21-global-open-v3-unknown-034-delta-review-v2"
DEFINITION_PATH = Path(
    "definitions/satellite_change_reviews/"
    "2026-07-21-global-open-v3-unknown-034-delta-review-v2.json"
)
OUTPUT_PATH = Path("satellite_change_reviews") / REVIEW_ID
DEFINITION_SHA256 = "7b95c7437f9459bf82f50f67ebecfd2b4a15789c2c02ee69148602d28fcfd271"
PREDECESSOR_MANIFEST_SHA256 = (
    "a4f97b1f02c993fc22ec204ba923358970cbbcb6f59a57b88de52b9989e39c03"
)
PREDECESSOR_TREE_SHA256 = (
    "030cbabfeaacc0420d2d426578663fb091958108b6a910995dfe5ba715b28064"
)

MANIFEST_FILENAME = "review-manifest.json"
SIDECAR_FILENAME = "manifest.sha256"
README_FILENAME = "README.md"

SCOPE = {
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "change_analysis_reexecuted_during_review_build": False,
    "identical_aoi_scene_pair_deduplication": True,
    "imagery_construction_status_inference": False,
    "imagery_data_centre_type_inference": False,
    "imagery_energy_inference": False,
    "imagery_identity_inference": False,
    "imagery_it_capacity_inference": False,
    "imagery_lifecycle_inference": False,
    "imagery_load_inference": False,
    "imagery_operating_status_inference": False,
    "imagery_operator_inference": False,
    "imagery_power_inference": False,
    "imagery_pue_inference": False,
    "imagery_workload_inference": False,
    "network_access_during_build": False,
    "network_access_during_validation": False,
    "review_labels_are_visual_dispositions_only": True,
    "review_required": True,
    "source_change_analysis_executed": True,
    "source_comparison_images_copied_exactly": True,
    "unique_site_claim_created": False,
}

BUILDER_FILES = (
    "datacenter_atlas/satellite_unknown034_delta_review_v1.py",
    "satellite_unknown034_delta_review_v1.py",
    "datacenter_atlas/satellite_unknown034_delta_review_v2.py",
    "satellite_unknown034_delta_review_v2.py",
    "scripts/build_satellite_unknown034_delta_review_v2.py",
)


class Unknown034DeltaReviewV2Error(ValueError):
    """Raised when the frozen predecessor or corrected successor drifts."""


def _sha256(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256(raw)


def _safe_parts(value: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise Unknown034DeltaReviewV2Error(f"{label} is not a safe relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise Unknown034DeltaReviewV2Error(f"{label} is not a safe relative path")
    return pure.parts


def _regular_file(root: Path, relative: str, label: str) -> Path:
    path = root.joinpath(*_safe_parts(relative, label))
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    if resolved_root not in resolved.parents:
        raise Unknown034DeltaReviewV2Error(f"{label} escapes its root")
    current = root
    for part in _safe_parts(relative, label):
        current = current / part
        if current.is_symlink():
            raise Unknown034DeltaReviewV2Error(f"{label} traverses a symlink")
    if not path.is_file():
        raise Unknown034DeltaReviewV2Error(f"{label} is not a regular file")
    return path


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _path_record(root: Path, relative: str) -> dict[str, Any]:
    return {"path": relative, **_file_record(_regular_file(root, relative, relative))}


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Unknown034DeltaReviewV2Error(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise Unknown034DeltaReviewV2Error(f"{label} is not an object")
    return value


def _definition(path: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    expected = root / DEFINITION_PATH
    supplied = Path(os.path.abspath(os.fspath(path)))
    if supplied != expected or supplied.is_symlink() or not supplied.is_file():
        raise Unknown034DeltaReviewV2Error("v2 review definition path changed")
    raw = supplied.read_bytes()
    if _sha256(raw) != DEFINITION_SHA256:
        raise Unknown034DeltaReviewV2Error("v2 review definition bytes changed")
    value = _json_object(supplied, "v2 review definition")
    if raw != _canonical_json(value):
        raise Unknown034DeltaReviewV2Error(
            "v2 review definition is not canonical JSON"
        )
    if (
        set(value)
        != {
            "format",
            "generated_at",
            "predecessor_bundle",
            "review_id",
            "reviewed_at",
            "schema_version",
            "scope",
        }
        or value["format"]
        != "datacenter-atlas-unknown034-delta-review-definition-v2"
        or value["schema_version"] != 2
        or value["review_id"] != REVIEW_ID
        or value["predecessor_bundle"] != predecessor.OUTPUT_PATH.as_posix()
        or value["scope"] != SCOPE
    ):
        raise Unknown034DeltaReviewV2Error("v2 review definition semantics changed")
    predecessor._timestamp(value["generated_at"], "v2 generated_at")
    predecessor._timestamp(value["reviewed_at"], "v2 reviewed_at")
    return root, value


def _predecessor(
    root: Path,
    definition: Mapping[str, Any],
) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    directory = root.joinpath(
        *_safe_parts(definition["predecessor_bundle"], "predecessor bundle")
    )
    manifest = predecessor.validate_unknown034_delta_review_v1(
        directory, root / predecessor.DEFINITION_PATH
    )
    manifest_path = directory / predecessor.MANIFEST_FILENAME
    if _file_record(manifest_path)["sha256"] != PREDECESSOR_MANIFEST_SHA256:
        raise Unknown034DeltaReviewV2Error("predecessor manifest changed")
    if (
        manifest.get("review_id") != predecessor.REVIEW_ID
        or manifest.get("reviewed_at") != definition["reviewed_at"]
        or manifest.get("summary", {}).get("reviewed_comparisons") != 21
        or manifest.get("summary", {}).get("analysis_failures") != 0
        or manifest.get("scope", {}).get("change_analysis_executed_by_checkpoint")
        is not False
    ):
        raise Unknown034DeltaReviewV2Error("predecessor review semantics changed")
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        rows.append(
            {
                "path": path.relative_to(directory).as_posix(),
                **_file_record(path),
            }
        )
    if (
        len(rows) != 28
        or sum(row["bytes"] for row in rows) != 14_019_259
        or _canonical_hash(rows) != PREDECESSOR_TREE_SHA256
    ):
        raise Unknown034DeltaReviewV2Error("predecessor tree changed")
    return manifest, directory, rows


def _readme() -> bytes:
    return (
        "# Unknown034 bounded satellite delta review v2\n\n"
        "This collision-isolated successor preserves every v1 comparison and "
        "review disposition byte-for-byte while correcting one ambiguous scope "
        "field. The two bound source batches executed 21 "
        "`sentinel-2-l2a-change-v2` jobs successfully. This review publication "
        "build did not reexecute that numerical change analysis; it validates, "
        "binds, and copies the frozen outputs.\n\n"
        "The accounting remains 22 exact AOI plus accepted scene-pair review "
        "units, 21 reviewed comparisons, and one typed native-window blocker. "
        "There are no identical review-unit duplicates, and this is not a "
        "unique-site count.\n\n"
        "Review labels remain visual dispositions only. They create no identity, "
        "construction, lifecycle, operating-status, type, capacity, load, power, "
        "energy, PUE, workload, operator, or atlas claim.\n"
    ).encode("utf-8")


def _artifact_record(raw: bytes, *, records: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"bytes": len(raw), "sha256": _sha256(raw)}
    if records is not None:
        result["records"] = records
    return result


def build_unknown034_delta_review_v2(
    definition_path: str | Path,
) -> dict[str, bytes]:
    """Reproduce v2 from the frozen v1 bundle without network or numerical rerun."""

    root, definition = _definition(definition_path)
    prior, prior_directory, prior_tree = _predecessor(root, definition)
    files: dict[str, bytes] = {}
    for name, record in prior["artifacts"].items():
        if name == README_FILENAME:
            continue
        source = _regular_file(prior_directory, name, f"predecessor {name}")
        raw = source.read_bytes()
        expected = {key: record[key] for key in ("bytes", "sha256")}
        if _artifact_record(raw) != expected:
            raise Unknown034DeltaReviewV2Error(
                f"predecessor artifact changed: {name}"
            )
        files[name] = raw
    files[README_FILENAME] = _readme()

    artifacts = {
        name: _artifact_record(
            raw,
            records=len(raw.splitlines()) if name.endswith(".jsonl") else None,
        )
        for name, raw in sorted(files.items())
    }
    inventory_hash = _canonical_hash(
        [{"path": name, **record} for name, record in artifacts.items()]
    )
    builder = {
        relative: _path_record(root, relative) for relative in BUILDER_FILES
    }
    summary = dict(prior["summary"])
    summary.update(
        {
            "change_analysis_reexecutions_during_review_build": 0,
            "source_change_jobs_completed": 21,
            "source_change_jobs_failed": 0,
        }
    )
    manifest = {
        "artifacts": artifacts,
        "builder": {"files": builder},
        "catalog_delta": prior["catalog_delta"],
        "execution_semantics": {
            "bound_source_change_algorithm": "sentinel-2-l2a-change-v2",
            "bound_source_change_analysis_executed": True,
            "bound_source_change_jobs_completed": 21,
            "bound_source_change_jobs_failed": 0,
            "comparison_images_copied_from_bound_outputs": 21,
            "review_build_action": "offline_validate_bind_and_copy",
            "review_build_reexecuted_change_analysis": False,
        },
        "format": "datacenter-atlas-unknown034-delta-review-v2",
        "generated_at": definition["generated_at"],
        "input_pins": prior["input_pins"],
        "predecessor": {
            "bundle_inventory": {
                "bytes": sum(row["bytes"] for row in prior_tree),
                "files": len(prior_tree),
                "sha256": PREDECESSOR_TREE_SHA256,
            },
            "manifest": {
                "path": (
                    f"{predecessor.OUTPUT_PATH.as_posix()}/"
                    f"{predecessor.MANIFEST_FILENAME}"
                ),
                **_file_record(
                    prior_directory / predecessor.MANIFEST_FILENAME
                ),
            },
            "review_id": predecessor.REVIEW_ID,
            "superseded_for_publication": True,
            "supersession_reason": "ambiguous_change_analysis_execution_scope_field",
        },
        "review_id": REVIEW_ID,
        "reviewed_at": definition["reviewed_at"],
        "schema_version": 2,
        "scope": dict(SCOPE),
        "source_contracts": prior["source_contracts"],
        "summary": summary,
        "tree_inventory_sha256": inventory_hash,
    }
    files[MANIFEST_FILENAME] = _canonical_json(manifest)
    files[SIDECAR_FILENAME] = (
        f"{_sha256(files[MANIFEST_FILENAME])}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return files


def _closed_tree(directory: Path, expected: Mapping[str, bytes]) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise Unknown034DeltaReviewV2Error("v2 review is not a regular directory")
    files: set[str] = set()
    directories = [directory]
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise Unknown034DeltaReviewV2Error("v2 review contains a symlink")
        relative = path.relative_to(directory).as_posix()
        if path.is_file():
            files.add(relative)
            if stat.S_IMODE(path.stat().st_mode) != 0o444:
                raise Unknown034DeltaReviewV2Error(
                    f"v2 review file is not frozen: {relative}"
                )
        elif path.is_dir():
            directories.append(path)
        else:
            raise Unknown034DeltaReviewV2Error(
                f"v2 review contains a non-regular path: {relative}"
            )
    if files != set(expected):
        raise Unknown034DeltaReviewV2Error("v2 review file set changed")
    if any(stat.S_IMODE(path.stat().st_mode) != 0o555 for path in directories):
        raise Unknown034DeltaReviewV2Error("v2 review directory mode changed")


def _freeze_tree(directory: Path) -> None:
    for path in sorted(directory.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)
    directory.chmod(0o555)


def write_unknown034_delta_review_v2(
    definition_path: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    """Atomically publish v2 without replacing v1 or any other checkpoint."""

    if not freeze:
        raise Unknown034DeltaReviewV2Error("v2 publication requires freeze=True")
    root, _value = _definition(definition_path)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output != root / OUTPUT_PATH:
        raise Unknown034DeltaReviewV2Error("v2 review output path changed")
    if output.exists() or output.is_symlink():
        raise Unknown034DeltaReviewV2Error("v2 review output already exists")
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise Unknown034DeltaReviewV2Error("v2 review output parent is invalid")
    files = build_unknown034_delta_review_v2(definition_path)
    stage = output.with_name(f".{output.name}.staging-v2")
    if stage.exists() or stage.is_symlink():
        raise Unknown034DeltaReviewV2Error("v2 review staging path already exists")
    stage.mkdir(mode=0o755)
    moved = False
    try:
        for relative, raw in files.items():
            destination = stage.joinpath(*_safe_parts(relative, relative))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        _freeze_tree(stage)
        _closed_tree(stage, files)
        os.replace(stage, output)
        moved = True
        descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        if not moved and stage.exists() and not stage.is_symlink():
            for path in sorted(
                stage.rglob("*"), key=lambda item: len(item.parts), reverse=True
            ):
                if path.is_dir():
                    path.chmod(0o755)
                elif path.is_file():
                    path.chmod(0o644)
            stage.chmod(0o755)
            shutil.rmtree(stage)
        raise
    return validate_unknown034_delta_review_v2(output, definition_path)


def validate_unknown034_delta_review_v2(
    bundle_directory: str | Path,
    definition_path: str | Path,
) -> dict[str, Any]:
    """Offline-reproduce v2 and compare every published byte."""

    root, _value = _definition(definition_path)
    bundle = Path(os.path.abspath(os.fspath(bundle_directory)))
    if bundle != root / OUTPUT_PATH:
        raise Unknown034DeltaReviewV2Error("v2 review bundle path changed")
    expected = build_unknown034_delta_review_v2(definition_path)
    _closed_tree(bundle, expected)
    for relative, raw in expected.items():
        if _regular_file(bundle, relative, relative).read_bytes() != raw:
            raise Unknown034DeltaReviewV2Error(
                f"v2 review differs from offline replay: {relative}"
            )
    manifest = _json_object(bundle / MANIFEST_FILENAME, "v2 review manifest")
    if (
        manifest.get("review_id") != REVIEW_ID
        or manifest.get("scope") != SCOPE
        or manifest.get("execution_semantics", {}).get(
            "bound_source_change_analysis_executed"
        )
        is not True
        or manifest.get("execution_semantics", {}).get(
            "review_build_reexecuted_change_analysis"
        )
        is not False
    ):
        raise Unknown034DeltaReviewV2Error("v2 execution semantics changed")
    return manifest


__all__ = [
    "DEFINITION_PATH",
    "DEFINITION_SHA256",
    "OUTPUT_PATH",
    "PREDECESSOR_MANIFEST_SHA256",
    "PREDECESSOR_TREE_SHA256",
    "REVIEW_ID",
    "SCOPE",
    "Unknown034DeltaReviewV2Error",
    "build_unknown034_delta_review_v2",
    "validate_unknown034_delta_review_v2",
    "write_unknown034_delta_review_v2",
]
