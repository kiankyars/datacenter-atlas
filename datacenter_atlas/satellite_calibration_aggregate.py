"""Build a label-blind aggregate of immutable algorithm-v2 rerun shards.

This module intentionally does not call the calibration-preparation validator:
that validator opens the permission-sealed historical lineage.  The aggregate
uses only the preparation's public manifest and rerun specifications, then
revalidates every numerical shard and output without reading a v1 review file.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .satellite_calibration_rerun import (
    CONFIGURATION_KEYS,
    EXPECTED_CHANGE_FILES,
    JOB_KEYS,
    MANIFEST_KEYS,
    OUTPUT_FORMAT as SHARD_FORMAT,
    PINNED_RUNTIME,
    SCOPE as SHARD_SCOPE,
    TARGET_ALGORITHM,
    _require_pinned_runtime,
    _runtime_lineage,
    _selected_features,
    _validated_change_output,
    _verify_runtime_snapshot,
)


DEFINITION_FORMAT = "datacenter-atlas-satellite-calibration-v2-aggregate-definition-v1"
RELEASE_FORMAT = "datacenter-atlas-satellite-calibration-v2-aggregate-v1"
SCHEMA_VERSION = 1
EXPECTED_SPEC_COUNT = 43
EXPECTED_SHARD_COUNT = 10
MULTITILE_MARKER = "a future multi-tile mosaic is required"
PREPARATION_FORMAT = "datacenter-atlas-satellite-calibration-rereview-preparation-v1"
RELEASE_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "blocked-multitile.jsonl",
        "manifest.json",
        "manifest.sha256",
        "numerical-inventory.jsonl",
        "reviewer-queue.jsonl",
        "summary.json",
    }
)
BUILDER_FILES = (
    "datacenter_atlas/satellite_calibration_aggregate.py",
    "scripts/build_satellite_calibration_aggregate.py",
)
REVIEWER_FORBIDDEN_KEYS = frozenset(
    {
        "decision",
        "historical_identity_sha256",
        "historical_queue_id",
        "label",
        "outcome",
        "reject",
        "retain",
        "reviewed_at",
        "source_run",
    }
)
REVIEW_CONSTRAINTS = {
    "data_centre_type_claim": False,
    "energy_claim": False,
    "identity_claim": False,
    "it_capacity_claim": False,
    "lifecycle_claim": False,
    "operating_status_claim": False,
    "operator_claim": False,
    "power_claim": False,
    "pue_claim": False,
    "review_required": True,
    "workload_claim": False,
}
RELEASE_SCOPE = {
    "adjudication_performed": False,
    "historical_labels_read": 0,
    "historical_labels_reused": 0,
    "numerical_change_evidence_only": True,
    "v2_calibration_claimed": False,
}
_RELEASE_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,127}")


class SatelliteCalibrationAggregateError(ValueError):
    """Raised when a label-blind aggregate fails closed."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _mode(path: Path) -> str:
    return f"{path.stat().st_mode & 0o777:04o}"


def _file_pin(path: Path) -> dict[str, Any]:
    return {**_checkpoint(path), "mode": _mode(path)}


def _path_pin(path: Path, project_root: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(project_root)), **_file_pin(path)}


def _normalize(path: Path, label: str) -> Path:
    try:
        return Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise SatelliteCalibrationAggregateError(
            f"{label} path cannot be normalized"
        ) from error


def _lexical_absolute(path: Path) -> Path:
    """Return an absolute path without resolving symlink components."""

    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(os.fspath(expanded)))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _inside_project(project_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SatelliteCalibrationAggregateError(f"{label} path is invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise SatelliteCalibrationAggregateError(f"{label} path escapes the project")
    lexical = _lexical_absolute(project_root / relative)
    if not _is_relative_to(lexical, project_root):
        raise SatelliteCalibrationAggregateError(f"{label} path escapes the project")
    _reject_symlink_components(lexical, project_root, label)
    path = _normalize(lexical, label)
    if not _is_relative_to(path, project_root):
        raise SatelliteCalibrationAggregateError(f"{label} path escapes the project")
    return path


def _reject_symlink_components(path: Path, project_root: Path, label: str) -> None:
    if not _is_relative_to(path, project_root):
        raise SatelliteCalibrationAggregateError(f"{label} is outside the project")
    current = project_root
    for part in path.relative_to(project_root).parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteCalibrationAggregateError(f"{label} traverses a symlink")


def _require_regular_file(path: Path, label: str, mode: str | None = None) -> None:
    if not path.is_file() or path.is_symlink():
        raise SatelliteCalibrationAggregateError(f"{label} is not a regular file")
    if mode is not None and _mode(path) != mode:
        raise SatelliteCalibrationAggregateError(f"{label} mode must be {mode}")


def _require_directory(path: Path, label: str, mode: str = "0555") -> None:
    if not path.is_dir() or path.is_symlink():
        raise SatelliteCalibrationAggregateError(f"{label} is not a regular directory")
    if _mode(path) != mode:
        raise SatelliteCalibrationAggregateError(f"{label} mode must be {mode}")


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                SatelliteCalibrationAggregateError(
                    f"{label} contains non-finite number {constant}"
                )
            ),
        )
    except SatelliteCalibrationAggregateError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteCalibrationAggregateError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteCalibrationAggregateError(f"{label} must be an object")
    return value


def _read_canonical_json(path: Path, label: str) -> dict[str, Any]:
    value = _read_json(path, label)
    if path.read_bytes() != canonical_json(value):
        raise SatelliteCalibrationAggregateError(f"{label} is not canonical JSON")
    return value


def _read_canonical_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SatelliteCalibrationAggregateError(f"{label} is unreadable") from error
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            value = json.loads(
                line.decode("utf-8"),
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    SatelliteCalibrationAggregateError(
                        f"{label} line {number} contains non-finite number {constant}"
                    )
                ),
            )
        except SatelliteCalibrationAggregateError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SatelliteCalibrationAggregateError(
                f"{label} line {number} is invalid JSON"
            ) from error
        if not isinstance(value, dict):
            raise SatelliteCalibrationAggregateError(
                f"{label} line {number} must be an object"
            )
        rows.append(value)
    if raw != canonical_jsonl(rows):
        raise SatelliteCalibrationAggregateError(f"{label} is not canonical JSONL")
    return rows


def _verify_pin(path: Path, pin: Mapping[str, Any], label: str) -> None:
    if set(pin) != {"bytes", "mode", "sha256"}:
        raise SatelliteCalibrationAggregateError(f"{label} pin schema is invalid")
    _require_regular_file(path, label, str(pin.get("mode")))
    if _file_pin(path) != dict(pin):
        raise SatelliteCalibrationAggregateError(f"{label} pin mismatch")


def _verify_sidecar(manifest: Path, sidecar: Path, manifest_name: str, label: str) -> None:
    expected = f"{_sha256(manifest.read_bytes())}  {manifest_name}\n".encode("ascii")
    if sidecar.read_bytes() != expected:
        raise SatelliteCalibrationAggregateError(f"{label} sidecar mismatch")


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _reject_reviewer_leakage(value: Any, label: str) -> None:
    leaked = sorted(set(_walk_keys(value)) & REVIEWER_FORBIDDEN_KEYS)
    if leaked:
        raise SatelliteCalibrationAggregateError(
            f"{label} contains forbidden reviewer key {leaked[0]}"
        )


def _ensure_no_overlap(paths: Sequence[tuple[str, Path]]) -> None:
    for index, (left_label, left) in enumerate(paths):
        for right_label, right in paths[index + 1 :]:
            if _is_relative_to(left, right) or _is_relative_to(right, left):
                raise SatelliteCalibrationAggregateError(
                    f"{left_label} overlaps {right_label}"
                )


def _definition_project_root(definition_path: Path) -> Path:
    lexical = _lexical_absolute(definition_path)
    if lexical.parent.name != "sources":
        raise SatelliteCalibrationAggregateError("definition must be inside sources/")
    project_root = _normalize(lexical.parent.parent, "project root")
    if not _is_relative_to(lexical, project_root):
        raise SatelliteCalibrationAggregateError("definition is outside the project")
    _reject_symlink_components(lexical, project_root, "definition")
    return project_root


def _basic_frozen_source(path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require_directory(path, label)
    manifest_path = path / "batch-manifest.json"
    sidecar_path = path / "manifest.sha256"
    _require_regular_file(manifest_path, f"{label} manifest", "0444")
    _require_regular_file(sidecar_path, f"{label} sidecar", "0444")
    manifest = _read_canonical_json(manifest_path, f"{label} manifest")
    _verify_sidecar(manifest_path, sidecar_path, "batch-manifest.json", label)
    return manifest, {
        "directory": None,
        "manifest": _file_pin(manifest_path),
        "manifest_sidecar": _file_pin(sidecar_path),
    }


def write_satellite_calibration_aggregate_definition(
    preparation_dir: Path,
    shard_dirs: Sequence[Path],
    definition_path: Path,
    *,
    release_id: str,
) -> dict[str, Any]:
    """Atomically write a canonical source definition without opening lineage."""

    project_root = _definition_project_root(definition_path)
    definition_path = _normalize(definition_path, "definition")
    lexical_preparation = _lexical_absolute(preparation_dir)
    lexical_shards = [_lexical_absolute(path) for path in shard_dirs]
    for label, path in [
        ("preparation", lexical_preparation),
        *[("shard", path) for path in lexical_shards],
    ]:
        if not _is_relative_to(path, project_root):
            raise SatelliteCalibrationAggregateError(f"{label} is outside the project")
        _reject_symlink_components(path, project_root, label)
    preparation_dir = _normalize(lexical_preparation, "preparation")
    normalized_shards = [_normalize(path, "shard") for path in lexical_shards]
    if not _RELEASE_ID.fullmatch(release_id):
        raise SatelliteCalibrationAggregateError("release id is invalid")
    if len(normalized_shards) != EXPECTED_SHARD_COUNT:
        raise SatelliteCalibrationAggregateError("exactly 10 shard directories are required")
    if definition_path.exists() or definition_path.is_symlink():
        raise SatelliteCalibrationAggregateError("definition already exists")
    _ensure_no_overlap(
        [("preparation", preparation_dir)]
        + [(f"shard {index}", path) for index, path in enumerate(normalized_shards)]
    )
    _require_directory(preparation_dir, "preparation")
    preparation_manifest_path = preparation_dir / "manifest.json"
    preparation_sidecar_path = preparation_dir / "manifest.sha256"
    specs_path = preparation_dir / "rerun-specs.jsonl"
    for path, label in (
        (preparation_manifest_path, "preparation manifest"),
        (preparation_sidecar_path, "preparation sidecar"),
        (specs_path, "rerun specs"),
    ):
        _require_regular_file(path, label, "0444")
    _read_canonical_json(preparation_manifest_path, "preparation manifest")
    _verify_sidecar(
        preparation_manifest_path, preparation_sidecar_path, "manifest.json", "preparation"
    )
    shard_records: list[tuple[int, dict[str, Any]]] = []
    for path in normalized_shards:
        manifest, pin = _basic_frozen_source(path, f"shard {path.name}")
        configuration = manifest.get("configuration")
        if not isinstance(configuration, Mapping):
            raise SatelliteCalibrationAggregateError("shard configuration is missing")
        start = configuration.get("start_index")
        if isinstance(start, bool) or not isinstance(start, int):
            raise SatelliteCalibrationAggregateError("shard start index is invalid")
        pin["directory"] = str(path.relative_to(project_root))
        shard_records.append((start, pin))
    shard_records.sort(key=lambda item: (item[0], item[1]["directory"]))
    definition = {
        "expected": {
            "rerun_specs": EXPECTED_SPEC_COUNT,
            "shards": EXPECTED_SHARD_COUNT,
        },
        "format": DEFINITION_FORMAT,
        "preparation": {
            "directory": str(preparation_dir.relative_to(project_root)),
            "manifest": _file_pin(preparation_manifest_path),
            "manifest_sidecar": _file_pin(preparation_sidecar_path),
            "rerun_specs": _file_pin(specs_path),
        },
        "release_id": release_id,
        "schema_version": SCHEMA_VERSION,
        "shards": [pin for _, pin in shard_records],
    }
    raw = canonical_json(definition)
    definition_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{definition_path.name}.", dir=definition_path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        if definition_path.exists() or definition_path.is_symlink():
            raise SatelliteCalibrationAggregateError("definition appeared before publication")
        os.replace(temporary, definition_path)
        _fsync_path(definition_path.parent)
    except Exception:
        if temporary.exists():
            os.chmod(temporary, 0o600)
            temporary.unlink()
        raise
    return definition


def _load_definition(definition_path: Path) -> tuple[dict[str, Any], Path]:
    project_root = _definition_project_root(definition_path)
    definition_path = _normalize(definition_path, "definition")
    _require_regular_file(definition_path, "definition", "0444")
    definition = _read_canonical_json(definition_path, "definition")
    if set(definition) != {
        "expected",
        "format",
        "preparation",
        "release_id",
        "schema_version",
        "shards",
    }:
        raise SatelliteCalibrationAggregateError("definition schema is invalid")
    if definition["format"] != DEFINITION_FORMAT or definition["schema_version"] != 1:
        raise SatelliteCalibrationAggregateError("definition format is unsupported")
    if not isinstance(definition["release_id"], str) or not _RELEASE_ID.fullmatch(
        definition["release_id"]
    ):
        raise SatelliteCalibrationAggregateError("definition release id is invalid")
    if definition["expected"] != {
        "rerun_specs": EXPECTED_SPEC_COUNT,
        "shards": EXPECTED_SHARD_COUNT,
    }:
        raise SatelliteCalibrationAggregateError("definition expected counts are invalid")
    if not isinstance(definition["shards"], list) or len(definition["shards"]) != 10:
        raise SatelliteCalibrationAggregateError("definition must pin exactly 10 shards")
    return definition, project_root


def _load_preparation(
    definition: Mapping[str, Any], project_root: Path
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    descriptor = definition.get("preparation")
    if not isinstance(descriptor, Mapping) or set(descriptor) != {
        "directory",
        "manifest",
        "manifest_sidecar",
        "rerun_specs",
    }:
        raise SatelliteCalibrationAggregateError("preparation descriptor schema is invalid")
    preparation = _inside_project(project_root, descriptor["directory"], "preparation")
    _reject_symlink_components(preparation, project_root, "preparation")
    _require_directory(preparation, "preparation")
    manifest_path = preparation / "manifest.json"
    sidecar_path = preparation / "manifest.sha256"
    specs_path = preparation / "rerun-specs.jsonl"
    _verify_pin(manifest_path, descriptor["manifest"], "preparation manifest")
    _verify_pin(sidecar_path, descriptor["manifest_sidecar"], "preparation sidecar")
    _verify_pin(specs_path, descriptor["rerun_specs"], "rerun specs")
    manifest = _read_canonical_json(manifest_path, "preparation manifest")
    _verify_sidecar(manifest_path, sidecar_path, "manifest.json", "preparation")
    if manifest.get("format") != PREPARATION_FORMAT or manifest.get("schema_version") != 1:
        raise SatelliteCalibrationAggregateError("preparation format is unsupported")
    output_pin = manifest.get("outputs", {}).get("rerun-specs.jsonl")
    if output_pin != descriptor["rerun_specs"]:
        raise SatelliteCalibrationAggregateError("preparation rerun-spec binding mismatch")
    specs = _read_canonical_jsonl(specs_path, "rerun specs")
    if len(specs) != EXPECTED_SPEC_COUNT:
        raise SatelliteCalibrationAggregateError("expected exactly 43 rerun specs")
    blind_ids = [spec.get("blind_item_id") for spec in specs]
    if any(not isinstance(value, str) or not value for value in blind_ids):
        raise SatelliteCalibrationAggregateError("rerun blind identity is invalid")
    if len(set(blind_ids)) != EXPECTED_SPEC_COUNT:
        raise SatelliteCalibrationAggregateError("rerun blind identity is duplicated")
    processor = specs[0].get("processor")
    if not isinstance(processor, Mapping) or processor.get("algorithm_version") != TARGET_ALGORITHM:
        raise SatelliteCalibrationAggregateError("rerun processor is invalid")
    for spec in specs:
        if spec.get("schema_version") != 1 or spec.get("processor") != processor:
            raise SatelliteCalibrationAggregateError("rerun spec processor binding differs")
        if spec.get("status") != "ready_for_exact_algorithm_v2_rerun":
            raise SatelliteCalibrationAggregateError("rerun spec state is invalid")
        if set(spec.get("selected_scenes", {})) != {"baseline", "current"}:
            raise SatelliteCalibrationAggregateError("rerun selected scenes are invalid")
    return preparation, specs, manifest


def _expected_input_validation(
    preparation: Path,
    specs: Sequence[Mapping[str, Any]],
    preparation_manifest: Mapping[str, Any],
    runtime: Mapping[str, Any],
    project_root: Path,
) -> dict[str, Any]:
    total_bytes = 0
    modes: Counter[str] = Counter()
    historical_queue_ids: set[str] = set()
    aois: set[tuple[Any, ...]] = set()
    for spec in specs:
        queue_id = spec.get("historical_queue_id")
        if not isinstance(queue_id, str) or not queue_id:
            raise SatelliteCalibrationAggregateError("rerun lineage identity is invalid")
        historical_queue_ids.add(queue_id)
        aoi = spec.get("aoi_bbox_wgs84")
        if not isinstance(aoi, list) or len(aoi) != 4:
            raise SatelliteCalibrationAggregateError("rerun AOI is invalid")
        aois.add(tuple(aoi))
        files = spec.get("processor", {}).get("files")
        if not isinstance(files, Mapping):
            raise SatelliteCalibrationAggregateError("rerun processor files are invalid")
        for label, pin in files.items():
            path = _inside_project(project_root, pin.get("path"), f"processor {label}")
            _reject_symlink_components(path, project_root, f"processor {label}")
            _require_regular_file(path, f"processor {label}")
            if _checkpoint(path) != {"bytes": pin.get("bytes"), "sha256": pin.get("sha256")}:
                raise SatelliteCalibrationAggregateError(f"processor {label} checkpoint mismatch")
        artifacts = spec.get("source_catalog_artifacts")
        if not isinstance(artifacts, Mapping) or set(artifacts) != {
            "baseline-response.json",
            "current-response.json",
            "manifest.json",
        }:
            raise SatelliteCalibrationAggregateError("source catalog artifacts are invalid")
        for name, pin in artifacts.items():
            path = _inside_project(project_root, pin.get("path"), name)
            _reject_symlink_components(path, project_root, name)
            _require_regular_file(path, name)
            if _checkpoint(path) != {"bytes": pin.get("bytes"), "sha256": pin.get("sha256")}:
                raise SatelliteCalibrationAggregateError(f"{name} checkpoint mismatch")
            total_bytes += int(pin["bytes"])
            modes[_mode(path)] += 1
        try:
            _selected_features(spec, project_root)
        except Exception as error:
            raise SatelliteCalibrationAggregateError(
                "selected catalog feature validation failed"
            ) from error
    if len(historical_queue_ids) != EXPECTED_SPEC_COUNT or len(aois) != EXPECTED_SPEC_COUNT:
        raise SatelliteCalibrationAggregateError("rerun identities are not unique")
    return {
        "algorithm_version": TARGET_ALGORITHM,
        "catalog_artifact_bytes_verified": total_bytes,
        "catalog_artifact_mode_counts": dict(sorted(modes.items())),
        "input_validation_only": True,
        "numerical_jobs_executed": 0,
        "preparation_manifest": _checkpoint(preparation / "manifest.json"),
        "processor_files": specs[0]["processor"]["files"],
        "rerun_specs_validated": EXPECTED_SPEC_COUNT,
        "runtime": runtime,
        "source_catalog_artifacts_validated": EXPECTED_SPEC_COUNT * 3,
        "unique_aois": EXPECTED_SPEC_COUNT,
        "unique_blind_items": EXPECTED_SPEC_COUNT,
        "unique_historical_queue_ids": EXPECTED_SPEC_COUNT,
        "v2_calibration_claimed": False,
    }


def _validate_configuration(value: Any) -> tuple[int, int]:
    if not isinstance(value, Mapping) or set(value) != CONFIGURATION_KEYS:
        raise SatelliteCalibrationAggregateError("shard configuration schema is invalid")
    start = value.get("start_index")
    count = value.get("max_jobs")
    attempts = value.get("max_attempts")
    timeout = value.get("timeout_seconds")
    interval = value.get("minimum_interval_seconds")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise SatelliteCalibrationAggregateError("shard start index is invalid")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise SatelliteCalibrationAggregateError("shard job count is invalid")
    if start + count > EXPECTED_SPEC_COUNT:
        raise SatelliteCalibrationAggregateError("shard exceeds rerun specs")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 5:
        raise SatelliteCalibrationAggregateError("shard attempt limit is invalid")
    for number, label, allow_zero in (
        (timeout, "timeout", False),
        (interval, "minimum interval", True),
    ):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise SatelliteCalibrationAggregateError(f"shard {label} is invalid")
        if number < 0 or (not allow_zero and number == 0):
            raise SatelliteCalibrationAggregateError(f"shard {label} is invalid")
    return start, count


def _validate_multitile_failure(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "kind",
        "returncode",
        "stderr_tail",
    }:
        raise SatelliteCalibrationAggregateError("blocked job failure schema is invalid")
    if value.get("kind") != "process_exit":
        raise SatelliteCalibrationAggregateError("blocked job is not a process failure")
    returncode = value.get("returncode")
    stderr = value.get("stderr_tail")
    if isinstance(returncode, bool) or not isinstance(returncode, int) or returncode == 0:
        raise SatelliteCalibrationAggregateError("blocked job return code is invalid")
    if not isinstance(stderr, str) or MULTITILE_MARKER not in stderr or len(stderr) > 4000:
        raise SatelliteCalibrationAggregateError("blocked job is not a multi-tile failure")


def _validate_shard_tree(
    shard: Path, manifest: Mapping[str, Any], selected: Sequence[Mapping[str, Any]]
) -> None:
    expected_files = {"batch-manifest.json", "manifest.sha256"}
    expected_directories = {"jobs", "processor_runtime"}
    for pin in manifest["processor"]["files"].values():
        relative = Path("processor_runtime") / pin["path"]
        expected_files.add(relative.as_posix())
        expected_directories.update(
            parent.as_posix() for parent in relative.parents if parent.as_posix() != "."
        )
    for spec in selected:
        if manifest["jobs"][spec["blind_item_id"]]["state"] == "completed":
            blind_id = spec["blind_item_id"]
            expected_directories.update({f"jobs/{blind_id}", f"jobs/{blind_id}/change"})
            expected_files.update(
                f"jobs/{blind_id}/change/{name}" for name in EXPECTED_CHANGE_FILES
            )
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for path in shard.rglob("*"):
        if path.is_symlink():
            raise SatelliteCalibrationAggregateError("shard contains a symlink")
        relative = path.relative_to(shard).as_posix()
        if path.is_file():
            actual_files.add(relative)
            if _mode(path) != "0444":
                raise SatelliteCalibrationAggregateError(
                    f"shard file mode mismatch: {relative}"
                )
        elif path.is_dir():
            actual_directories.add(relative)
            if _mode(path) != "0555":
                raise SatelliteCalibrationAggregateError(
                    f"shard directory mode mismatch: {relative}"
                )
        else:
            raise SatelliteCalibrationAggregateError("shard contains a special file")
    if actual_files != expected_files or actual_directories != expected_directories:
        raise SatelliteCalibrationAggregateError("shard tree is not closed")


def _artifact_refs(
    shard: Path, blind_id: str, artifacts: Mapping[str, Any], project_root: Path
) -> dict[str, Any]:
    return {
        name: {
            "path": str(
                (shard / "jobs" / blind_id / "change" / name).relative_to(project_root)
            ),
            "bytes": pin["bytes"],
            "sha256": pin["sha256"],
        }
        for name, pin in sorted(artifacts.items())
    }


def _validate_shard(
    shard: Path,
    pin: Mapping[str, Any],
    preparation: Path,
    specs: Sequence[Mapping[str, Any]],
    preparation_manifest: Mapping[str, Any],
    project_root: Path,
    expected_runtime: Mapping[str, Any] | None,
) -> tuple[tuple[int, int], Mapping[str, Any], list[dict[str, Any]]]:
    if not isinstance(pin, Mapping) or set(pin) != {
        "directory",
        "manifest",
        "manifest_sidecar",
    }:
        raise SatelliteCalibrationAggregateError("shard descriptor schema is invalid")
    _reject_symlink_components(shard, project_root, "shard")
    _require_directory(shard, "shard")
    manifest_path = shard / "batch-manifest.json"
    sidecar_path = shard / "manifest.sha256"
    _verify_pin(manifest_path, pin["manifest"], "shard manifest")
    _verify_pin(sidecar_path, pin["manifest_sidecar"], "shard sidecar")
    manifest = _read_canonical_json(manifest_path, "shard manifest")
    _verify_sidecar(manifest_path, sidecar_path, "batch-manifest.json", "shard")
    if set(manifest) != MANIFEST_KEYS:
        raise SatelliteCalibrationAggregateError("shard manifest schema is invalid")
    if manifest["format"] != SHARD_FORMAT or manifest["schema_version"] != 1:
        raise SatelliteCalibrationAggregateError("shard format is unsupported")
    if manifest["scope"] != SHARD_SCOPE:
        raise SatelliteCalibrationAggregateError("shard scope is invalid")
    if manifest["preparation_dir"] != str(preparation.relative_to(project_root)):
        raise SatelliteCalibrationAggregateError("shard preparation binding mismatch")
    start, count = _validate_configuration(manifest["configuration"])
    selected = specs[start : start + count]
    if manifest["processor"] != selected[0]["processor"]:
        raise SatelliteCalibrationAggregateError("shard processor binding mismatch")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, Mapping):
        raise SatelliteCalibrationAggregateError("shard runtime is invalid")
    try:
        _require_pinned_runtime(runtime)
    except Exception as error:
        raise SatelliteCalibrationAggregateError("shard runtime is not pinned") from error
    if expected_runtime is not None and runtime != expected_runtime:
        raise SatelliteCalibrationAggregateError("shard runtimes differ")
    expected_validation = _expected_input_validation(
        preparation, specs, preparation_manifest, runtime, project_root
    )
    if manifest["input_validation"] != expected_validation:
        raise SatelliteCalibrationAggregateError("shard input validation binding mismatch")
    try:
        _verify_runtime_snapshot(shard / "processor_runtime", manifest["processor"])
    except Exception as error:
        raise SatelliteCalibrationAggregateError("shard processor snapshot is invalid") from error
    jobs = manifest.get("jobs")
    if not isinstance(jobs, Mapping) or set(jobs) != {
        spec["blind_item_id"] for spec in selected
    }:
        raise SatelliteCalibrationAggregateError("shard job set mismatch")
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for spec in selected:
        blind_id = spec["blind_item_id"]
        job = jobs[blind_id]
        if not isinstance(job, Mapping) or set(job) != JOB_KEYS:
            raise SatelliteCalibrationAggregateError("shard job schema is invalid")
        expected_binding = {
            "blind_item_id": blind_id,
            "historical_identity_sha256": spec["historical_identity_sha256"],
            "historical_queue_id": spec["historical_queue_id"],
            "rerun_spec_sha256": _sha256(canonical_line(spec)),
        }
        if any(job.get(key) != value for key, value in expected_binding.items()):
            raise SatelliteCalibrationAggregateError("shard job/spec binding mismatch")
        attempts = job.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not (
            1 <= attempts <= manifest["configuration"]["max_attempts"]
        ):
            raise SatelliteCalibrationAggregateError("shard attempt count is invalid")
        state = job.get("state")
        counts[state] += 1
        base = {
            "aoi_bbox_wgs84": spec["aoi_bbox_wgs84"],
            "blind_item_id": blind_id,
            "entity": spec["entity"],
            "rerun_spec_sha256": expected_binding["rerun_spec_sha256"],
            "schema_version": 1,
            "selected_scenes": spec["selected_scenes"],
            "source_shard": {
                "manifest_sha256": pin["manifest"]["sha256"],
                "path": str(shard.relative_to(project_root)),
            },
        }
        change_dir = shard / "jobs" / blind_id / "change"
        if state == "completed":
            if job.get("failure") is not None or not isinstance(job.get("artifacts"), Mapping):
                raise SatelliteCalibrationAggregateError("completed shard job is invalid")
            try:
                validated = _validated_change_output(change_dir, spec, project_root)
            except Exception as error:
                raise SatelliteCalibrationAggregateError(
                    f"completed numerical output is invalid: {blind_id}"
                ) from error
            if validated["artifacts"] != job["artifacts"]:
                raise SatelliteCalibrationAggregateError("shard artifact binding mismatch")
            rows.append(
                {
                    **base,
                    "artifacts": _artifact_refs(
                        shard, blind_id, validated["artifacts"], project_root
                    ),
                    "attempts": attempts,
                    "failure_evidence_sha256": None,
                    "state": "ready_for_blind_review",
                }
            )
        elif state == "failed":
            if job.get("artifacts") is not None or change_dir.exists() or change_dir.is_symlink():
                raise SatelliteCalibrationAggregateError("failed shard job published artifacts")
            _validate_multitile_failure(job.get("failure"))
            rows.append(
                {
                    **base,
                    "artifacts": None,
                    "attempts": attempts,
                    "blocker": "aoi_crosses_scene_asset_requires_multitile_mosaic",
                    "failure_evidence_sha256": _sha256(canonical_line(job["failure"])),
                    "state": "blocked_multitile_required",
                }
            )
        else:
            raise SatelliteCalibrationAggregateError("shard job state is invalid")
    expected_summary = {
        "jobs_completed": counts.get("completed", 0),
        "jobs_failed": counts.get("failed", 0),
        "jobs_selected": count,
    }
    expected_state = "completed" if expected_summary["jobs_failed"] == 0 else "completed_with_failures"
    if manifest["summary"] != expected_summary or manifest["state"] != expected_state:
        raise SatelliteCalibrationAggregateError("shard summary is invalid")
    _validate_shard_tree(shard, manifest, selected)
    return (start, start + count), runtime, rows


def _source_state(
    definition_path: Path,
    *,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], Path, list[dict[str, Any]], Mapping[str, Any], Path]:
    definition, project_root = _load_definition(definition_path)
    preparation, specs, preparation_manifest = _load_preparation(definition, project_root)
    shard_paths: list[Path] = []
    ranges: list[tuple[int, int]] = []
    rows: list[dict[str, Any]] = []
    runtime: Mapping[str, Any] | None = None
    for pin in definition["shards"]:
        if not isinstance(pin, Mapping):
            raise SatelliteCalibrationAggregateError("shard descriptor is invalid")
        shard = _inside_project(project_root, pin.get("directory"), "shard")
        shard_paths.append(shard)
        interval, shard_runtime, shard_rows = _validate_shard(
            shard,
            pin,
            preparation,
            specs,
            preparation_manifest,
            project_root,
            runtime,
        )
        runtime = shard_runtime
        ranges.append(interval)
        rows.extend(shard_rows)
    if len(set(shard_paths)) != EXPECTED_SHARD_COUNT:
        raise SatelliteCalibrationAggregateError("shard path is duplicated")
    _ensure_no_overlap(
        [("preparation", preparation)]
        + [(f"shard {index}", path) for index, path in enumerate(shard_paths)]
    )
    ordered_ranges = sorted(ranges)
    if ordered_ranges != [
        (0, 1),
        (1, 6),
        (6, 11),
        (11, 16),
        (16, 21),
        (21, 26),
        (26, 31),
        (31, 36),
        (36, 41),
        (41, 43),
    ]:
        raise SatelliteCalibrationAggregateError(
            "shard ranges do not form the exact 43-spec partition"
        )
    if len(rows) != EXPECTED_SPEC_COUNT or len({row["blind_item_id"] for row in rows}) != 43:
        raise SatelliteCalibrationAggregateError("aggregate job inventory is not exact")
    if runtime is None:
        raise SatelliteCalibrationAggregateError("aggregate runtime is missing")
    try:
        current_runtime = _runtime_lineage(require_packages=True)
    except Exception as error:
        raise SatelliteCalibrationAggregateError(
            "current runtime is not the pinned numerical runtime"
        ) from error
    if current_runtime != runtime:
        raise SatelliteCalibrationAggregateError("current numerical runtime drifted")
    if output_dir is not None:
        lexical_output = _lexical_absolute(output_dir)
        if not _is_relative_to(lexical_output, project_root):
            raise SatelliteCalibrationAggregateError("output is outside the project")
        _reject_symlink_components(lexical_output, project_root, "output")
        output_dir = _normalize(lexical_output, "output")
        _ensure_no_overlap(
            [("output", output_dir), ("preparation", preparation)]
            + [(f"shard {index}", path) for index, path in enumerate(shard_paths)]
        )
    return definition, project_root, sorted(rows, key=lambda row: row["blind_item_id"]), runtime, preparation


def _release_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = [dict(row) for row in rows]
    reviewers: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in inventory:
        if row["state"] == "ready_for_blind_review":
            reviewers.append(
                {
                    "algorithm_version": TARGET_ALGORITHM,
                    "aoi_bbox_wgs84": row["aoi_bbox_wgs84"],
                    "artifacts": row["artifacts"],
                    "blind_item_id": row["blind_item_id"],
                    "entity": row["entity"],
                    "evidence_constraints": REVIEW_CONSTRAINTS,
                    "rerun_spec_sha256": row["rerun_spec_sha256"],
                    "schema_version": 1,
                    "selected_scenes": row["selected_scenes"],
                    "source_shard": row["source_shard"],
                    "state": "awaiting_blind_analyst_review",
                }
            )
        else:
            blocked.append(
                {
                    "aoi_bbox_wgs84": row["aoi_bbox_wgs84"],
                    "attempts": row["attempts"],
                    "blind_item_id": row["blind_item_id"],
                    "blocker": row["blocker"],
                    "entity": row["entity"],
                    "failure_evidence_sha256": row["failure_evidence_sha256"],
                    "rerun_spec_sha256": row["rerun_spec_sha256"],
                    "schema_version": 1,
                    "selected_scenes": row["selected_scenes"],
                    "source_shard": row["source_shard"],
                    "state": "blocked_multitile_required",
                }
            )
    for label, values in (("inventory", inventory), ("reviewer queue", reviewers), ("blocked ledger", blocked)):
        _reject_reviewer_leakage(values, label)
    return inventory, reviewers, blocked


def _summary(release_id: str, inventory: Sequence[Mapping[str, Any]], reviewers: Sequence[Mapping[str, Any]], blocked: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "adjudication_performed": False,
        "algorithm_version": TARGET_ALGORITHM,
        "blind_items_blocked_multitile": len(blocked),
        "blind_items_ready_for_review": len(reviewers),
        "historical_labels_read": 0,
        "historical_labels_reused": 0,
        "numerical_items": len(inventory),
        "release_id": release_id,
        "schema_version": 1,
        "shards": EXPECTED_SHARD_COUNT,
        "v2_calibration_claimed": False,
    }


def _readme(summary: Mapping[str, Any]) -> bytes:
    return (
        "# Label-blind algorithm-v2 numerical aggregate\n\n"
        f"Release `{summary['release_id']}` binds exactly 10 immutable numerical shards "
        f"covering 43 unique rerun specifications. {summary['blind_items_ready_for_review']} "
        "successful numerical outputs are exposed in `reviewer-queue.jsonl`; "
        f"{summary['blind_items_blocked_multitile']} AOIs that require a multi-tile mosaic "
        "are listed separately in `blocked-multitile.jsonl`.\n\n"
        "The reviewer queue contains algorithm-v2 numerical change evidence only. It does "
        "not contain or reuse any historical retain/reject decision. No analyst adjudication "
        "has been performed, and this release does not establish algorithm-v2 calibration.\n\n"
        "Satellite imagery change cannot by itself identify a data centre or establish its "
        "operator, lifecycle, type, IT capacity, PUE, workload, power, or energy consumption.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Derived numerical evidence retains the source Sentinel-2/STAC provenance recorded "
        "in each pinned report and source shard. Consult the source catalog artifacts for "
        "provider-specific terms. No historical analyst label is distributed here.\n"
    ).encode("utf-8")


def _builder_files(project_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in BUILDER_FILES:
        path = project_root / relative
        _require_regular_file(path, f"builder file {relative}")
        result[relative] = _checkpoint(path)
    return result


def _expected_manifest(
    definition_path: Path,
    definition: Mapping[str, Any],
    project_root: Path,
    runtime: Mapping[str, Any],
    summary: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "builder_files": _builder_files(project_root),
        "definition": _path_pin(definition_path, project_root),
        "format": RELEASE_FORMAT,
        "outputs": dict(outputs),
        "preparation": definition["preparation"],
        "processor": {
            "algorithm_version": TARGET_ALGORITHM,
            "runtime": runtime,
        },
        "release_id": definition["release_id"],
        "schema_version": 1,
        "scope": RELEASE_SCOPE,
        "shards": definition["shards"],
        "summary": dict(summary),
    }


def _write_release_files(
    staging: Path,
    definition_path: Path,
    definition: Mapping[str, Any],
    project_root: Path,
    rows: Sequence[Mapping[str, Any]],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    inventory, reviewers, blocked = _release_rows(rows)
    summary = _summary(definition["release_id"], inventory, reviewers, blocked)
    payloads = {
        "ATTRIBUTION.txt": _attribution(),
        "README.md": _readme(summary),
        "blocked-multitile.jsonl": canonical_jsonl(blocked),
        "numerical-inventory.jsonl": canonical_jsonl(inventory),
        "reviewer-queue.jsonl": canonical_jsonl(reviewers),
        "summary.json": canonical_json(summary),
    }
    for name, raw in payloads.items():
        (staging / name).write_bytes(raw)
    outputs = {
        name: {**_checkpoint(staging / name), "mode": "0444"}
        for name in sorted(payloads)
    }
    manifest = _expected_manifest(
        definition_path, definition, project_root, runtime, summary, outputs
    )
    manifest_raw = canonical_json(manifest)
    (staging / "manifest.json").write_bytes(manifest_raw)
    (staging / "manifest.sha256").write_bytes(
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return manifest


def _validate_release_tree(output_dir: Path) -> None:
    _require_directory(output_dir, "aggregate output")
    actual: set[str] = set()
    for path in output_dir.rglob("*"):
        if path.is_symlink():
            raise SatelliteCalibrationAggregateError("aggregate output contains a symlink")
        relative = path.relative_to(output_dir).as_posix()
        if path.is_dir():
            raise SatelliteCalibrationAggregateError("aggregate output contains a directory")
        if not path.is_file():
            raise SatelliteCalibrationAggregateError("aggregate output contains a special file")
        actual.add(relative)
        if _mode(path) != "0444":
            raise SatelliteCalibrationAggregateError(
                f"aggregate file mode mismatch: {relative}"
            )
    if actual != RELEASE_FILES:
        raise SatelliteCalibrationAggregateError("aggregate output tree is not closed")


def validate_satellite_calibration_aggregate(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    """Validate the complete aggregate offline without opening historical labels."""

    original_definition_path = Path(definition_path)
    original_output_dir = Path(output_dir)
    definition, project_root, source_rows, runtime, _ = _source_state(
        original_definition_path, output_dir=original_output_dir
    )
    definition_path = _normalize(original_definition_path, "definition")
    output_dir = _normalize(original_output_dir, "output")
    _validate_release_tree(output_dir)
    inventory, reviewers, blocked = _release_rows(source_rows)
    expected_summary = _summary(definition["release_id"], inventory, reviewers, blocked)
    expected_payloads = {
        "ATTRIBUTION.txt": _attribution(),
        "README.md": _readme(expected_summary),
        "blocked-multitile.jsonl": canonical_jsonl(blocked),
        "numerical-inventory.jsonl": canonical_jsonl(inventory),
        "reviewer-queue.jsonl": canonical_jsonl(reviewers),
        "summary.json": canonical_json(expected_summary),
    }
    for name, raw in expected_payloads.items():
        if (output_dir / name).read_bytes() != raw:
            raise SatelliteCalibrationAggregateError(f"aggregate {name} differs")
    manifest_path = output_dir / "manifest.json"
    sidecar_path = output_dir / "manifest.sha256"
    manifest = _read_canonical_json(manifest_path, "aggregate manifest")
    _verify_sidecar(manifest_path, sidecar_path, "manifest.json", "aggregate")
    output_pins = {
        name: _file_pin(output_dir / name) for name in sorted(expected_payloads)
    }
    expected_manifest = _expected_manifest(
        definition_path,
        definition,
        project_root,
        runtime,
        expected_summary,
        output_pins,
    )
    if manifest != expected_manifest:
        raise SatelliteCalibrationAggregateError("aggregate manifest differs")
    return manifest


def _fsync_path(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        _fsync_path(path)
    for path in sorted(
        [root, *(path for path in root.rglob("*") if path.is_dir())],
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        _fsync_path(path)


def _freeze_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)
    for path in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda value: len(value.parts),
        reverse=True,
    ):
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _cleanup_staging(staging: Path) -> None:
    if not staging.exists():
        return
    for path in staging.rglob("*"):
        try:
            os.chmod(path, 0o755 if path.is_dir() else 0o644)
        except OSError:
            pass
    os.chmod(staging, 0o755)
    shutil.rmtree(staging)


def write_satellite_calibration_aggregate(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    """Stage, validate, freeze, and atomically publish one aggregate release."""

    original_definition_path = Path(definition_path)
    original_output_dir = Path(output_dir)
    lexical_output = _lexical_absolute(original_output_dir)
    if lexical_output.exists() or lexical_output.is_symlink():
        raise SatelliteCalibrationAggregateError("aggregate output already exists")
    definition, project_root, rows, runtime, _ = _source_state(
        original_definition_path, output_dir=original_output_dir
    )
    definition_path = _normalize(original_definition_path, "definition")
    output_dir = _normalize(original_output_dir, "output")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        _write_release_files(
            staging, definition_path, definition, project_root, rows, runtime
        )
        _fsync_tree(staging)
        _freeze_tree(staging)
        _fsync_tree(staging)
        manifest = validate_satellite_calibration_aggregate(
            staging, definition_path=definition_path
        )
        if output_dir.exists() or output_dir.is_symlink():
            raise SatelliteCalibrationAggregateError(
                "aggregate output appeared before publication"
            )
        os.replace(staging, output_dir)
        _fsync_path(output_dir.parent)
        return manifest
    except Exception:
        _cleanup_staging(staging)
        raise
