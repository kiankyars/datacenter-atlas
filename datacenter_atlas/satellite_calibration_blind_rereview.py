"""Build and validate the closed algorithm-v2 identity-blind rereview audit.

The decision panel is resolved before the permission-sealed historical lineage is
opened.  The release is descriptive: it measures agreement with prior analyst
labels and makes no construction, identity, capacity, or production-calibration
claim.
"""

from __future__ import annotations

from collections import Counter
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
from typing import Any, Mapping, Sequence


DEFINITION_FORMAT = "datacenter-atlas-satellite-calibration-v2-blind-rereview-definition-v5"
RELEASE_FORMAT = "datacenter-atlas-satellite-calibration-v2-blind-rereview-v5"
SCHEMA_VERSION = 5
LABELS = frozenset(
    {
        "retain_site_scale_physical_change",
        "reject_non_site_or_unusable",
        "uncertain",
    }
)
EXPECTED = {
    "aggregate_rows": 43,
    "reviewed_rows": 36,
    "blocked_rows": 7,
    "ab_agreements": 28,
    "ab_disagreements": 8,
    "two_of_three": 7,
    "three_way_uncertain": 1,
    "final_retain": 16,
    "final_reject": 19,
    "final_uncertain": 1,
    "historical_retain_reviewed": 11,
    "historical_reject_reviewed": 25,
    "historical_retain_blocked": 1,
    "historical_reject_blocked": 6,
    "binary_comparable": 35,
    "binary_same": 30,
}
RELEASE_FILES = frozenset(
    {
        "ATTRIBUTION.txt",
        "README.md",
        "blind-decisions.jsonl",
        "blocked-multitile.jsonl",
        "calibration-records.jsonl",
        "manifest.json",
        "manifest.sha256",
        "protocol-deviations.json",
        "summary.json",
    }
)
BUILDER_FILES = (
    "datacenter_atlas/satellite_calibration_blind_rereview.py",
    "satellite_calibration_blind_rereview.py",
    "scripts/build_satellite_calibration_blind_rereview.py",
)
CLAIM_CONSTRAINTS = {
    "construction_truth_claim": False,
    "data_centre_identity_claim": False,
    "data_centre_type_claim": False,
    "energy_claim": False,
    "lifecycle_claim": False,
    "operator_claim": False,
    "power_claim": False,
    "production_calibration_claim": False,
    "pue_claim": False,
    "semianalysis_parity_claim": False,
    "threshold_validation_claim": False,
    "workload_claim": False,
}
_BLIND_ID = re.compile(r"v2rr-[0-9a-f]{24}")


class SatelliteCalibrationBlindRereviewError(ValueError):
    """Raised when a source or release violates the closed audit contract."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def canonical_line(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _mode(path: Path) -> str:
    return f"{path.stat().st_mode & 0o777:04o}"


def _pin(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "mode": _mode(path), "sha256": _sha(raw)}


def _identity_from_stat(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _path_identity(path: Path, label: str, *, directory: bool) -> tuple[int, int]:
    try:
        value = path.lstat()
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} identity is unavailable"
        ) from error
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if stat.S_ISLNK(value.st_mode) or not expected_kind(value.st_mode):
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} filesystem kind is invalid"
        )
    return _identity_from_stat(value)


def _require_release_identity(
    path: Path,
    directory_identity: tuple[int, int],
    file_identities: Mapping[str, tuple[int, int]],
    label: str,
) -> None:
    if _path_identity(path, label, directory=True) != directory_identity:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} directory identity mismatch"
        )
    try:
        names = {child.name for child in path.iterdir()}
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} tree cannot be inspected"
        ) from error
    if names != set(file_identities):
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} file identity set mismatch"
        )
    for name, expected in file_identities.items():
        if _path_identity(path / name, f"{label}/{name}", directory=False) != expected:
            raise SatelliteCalibrationBlindRereviewError(
                f"{label}/{name} identity mismatch"
            )


def _is_relative(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _lexical_absolute(path: Path) -> Path:
    expanded = Path(path).expanduser()
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return Path(os.path.abspath(os.fspath(expanded)))


def _reject_lexical_symlink_aliases(path: Path, label: str) -> Path:
    """Reject every symlink prefix without resolving any part of ``path``."""

    lexical = _lexical_absolute(path)
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise SatelliteCalibrationBlindRereviewError(
                f"{label} lexical path traverses symlink alias: {current}"
            )
    return lexical


def _project_root(definition_path: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(definition_path.expanduser())))
    if lexical.parent.name != "sources":
        raise SatelliteCalibrationBlindRereviewError("definition must be inside sources/")
    root = lexical.parent.parent.resolve(strict=True)
    _reject_symlink_components(lexical, root, "definition")
    return root


def _reject_symlink_components(path: Path, root: Path, label: str) -> None:
    lexical = _reject_lexical_symlink_aliases(path, label)
    if not _is_relative(lexical, root):
        raise SatelliteCalibrationBlindRereviewError(f"{label} is outside the project")
    current = root
    for part in lexical.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise SatelliteCalibrationBlindRereviewError(f"{label} traverses a symlink")


def _inside(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SatelliteCalibrationBlindRereviewError(f"{label} path is invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise SatelliteCalibrationBlindRereviewError(f"{label} path escapes the project")
    lexical = Path(os.path.abspath(os.fspath(root / relative)))
    _reject_symlink_components(lexical, root, label)
    resolved = lexical.resolve(strict=False)
    if not _is_relative(resolved, root):
        raise SatelliteCalibrationBlindRereviewError(f"{label} path escapes the project")
    return resolved


def _read_json(path: Path, label: str, *, canonical: bool = False) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SatelliteCalibrationBlindRereviewError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise SatelliteCalibrationBlindRereviewError(f"{label} must be an object")
    if canonical and raw != canonical_json(value):
        raise SatelliteCalibrationBlindRereviewError(f"{label} is not canonical JSON")
    return value


def _read_jsonl(path: Path, label: str, *, sorted_keys: bool = False) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(f"{label} is unreadable") from error
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            value = json.loads(line.decode("utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise SatelliteCalibrationBlindRereviewError(f"{label} line {number} is invalid JSON") from error
        if not isinstance(value, dict):
            raise SatelliteCalibrationBlindRereviewError(f"{label} line {number} must be an object")
        rows.append(value)
    expected = canonical_jsonl(rows) if sorted_keys else b"".join(
        (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n").encode() for row in rows
    )
    if raw != expected:
        raise SatelliteCalibrationBlindRereviewError(f"{label} is not canonical JSONL")
    return rows


def _verify_pin(path: Path, expected: Mapping[str, Any], label: str) -> None:
    if set(expected) != {"bytes", "mode", "sha256"}:
        raise SatelliteCalibrationBlindRereviewError(f"{label} pin schema is invalid")
    if not path.is_file() or path.is_symlink():
        raise SatelliteCalibrationBlindRereviewError(f"{label} is not a regular file")
    if _pin(path) != dict(expected):
        raise SatelliteCalibrationBlindRereviewError(f"{label} pin mismatch")


def _validate_source_group(
    root: Path, name: str, group: Mapping[str, Any]
) -> Path:
    if set(group) != {"directories", "directory", "directory_mode", "files"}:
        raise SatelliteCalibrationBlindRereviewError(f"{name} source schema drift")
    directory = _inside(root, group["directory"], name)
    expected_root_mode = group["directory_mode"]
    if (
        not isinstance(expected_root_mode, str)
        or not directory.is_dir()
        or directory.is_symlink()
        or _mode(directory) != expected_root_mode
    ):
        raise SatelliteCalibrationBlindRereviewError(f"{name} directory drift")
    pins = group["files"]
    directory_modes = group["directories"]
    if not isinstance(pins, dict) or not pins:
        raise SatelliteCalibrationBlindRereviewError(f"{name} files are invalid")
    if not isinstance(directory_modes, dict):
        raise SatelliteCalibrationBlindRereviewError(
            f"{name} nested directories are invalid"
        )
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for node in directory.rglob("*"):
        relative = node.relative_to(directory).as_posix()
        if node.is_symlink():
            raise SatelliteCalibrationBlindRereviewError(
                f"{name}/{relative} is a symlink"
            )
        if node.is_dir():
            actual_directories.add(relative)
        elif node.is_file():
            actual_files.add(relative)
        else:
            raise SatelliteCalibrationBlindRereviewError(
                f"{name}/{relative} is not a regular filesystem node"
            )
    if actual_files != set(pins):
        raise SatelliteCalibrationBlindRereviewError(f"{name} file set drift")
    if actual_directories != set(directory_modes):
        raise SatelliteCalibrationBlindRereviewError(
            f"{name} nested directory set drift"
        )
    for relative, expected_mode in directory_modes.items():
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or not isinstance(expected_mode, str)
        ):
            raise SatelliteCalibrationBlindRereviewError(
                f"{name} nested directory pin is invalid"
            )
        path = _inside(
            root, str(Path(group["directory"]) / relative), f"{name}/{relative}"
        )
        if not path.is_dir() or path.is_symlink() or _mode(path) != expected_mode:
            raise SatelliteCalibrationBlindRereviewError(
                f"{name}/{relative} directory mode drift"
            )
    for relative, pin in pins.items():
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise SatelliteCalibrationBlindRereviewError(
                f"{name} file pin path is invalid"
            )
        path = _inside(
            root, str(Path(group["directory"]) / relative), f"{name}/{relative}"
        )
        _verify_pin(path, pin, f"{name}/{relative}")
    return directory


def _source_state(definition_path: Path, output_dir: Path | None = None) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    root = _project_root(definition_path)
    definition = _read_json(definition_path, "definition", canonical=True)
    if _mode(definition_path) != "0444":
        raise SatelliteCalibrationBlindRereviewError("definition mode must be 0444")
    if set(definition) != {"expected", "format", "protocol_deviations", "release_id", "schema_version", "sources"}:
        raise SatelliteCalibrationBlindRereviewError("definition schema drift")
    if definition["format"] != DEFINITION_FORMAT or definition["schema_version"] != SCHEMA_VERSION:
        raise SatelliteCalibrationBlindRereviewError("definition format mismatch")
    if definition["expected"] != EXPECTED:
        raise SatelliteCalibrationBlindRereviewError("expected arithmetic contract drift")
    source_groups = definition["sources"]
    required = {"preparation", "aggregate", "reviewer_a", "reviewer_b", "adjudicator_c"}
    if not isinstance(source_groups, dict) or set(source_groups) != required:
        raise SatelliteCalibrationBlindRereviewError("source group schema drift")
    directories: dict[str, Path] = {}
    for name in sorted(required):
        group = source_groups[name]
        if not isinstance(group, dict):
            raise SatelliteCalibrationBlindRereviewError(f"{name} source schema drift")
        directories[name] = _validate_source_group(root, name, group)
    paths = [("definition", definition_path.resolve()), *directories.items()]
    if output_dir is not None:
        paths.append(("output", output_dir.resolve(strict=False)))
    for index, (left_name, left) in enumerate(paths):
        for right_name, right in paths[index + 1 :]:
            if _is_relative(left, right) or _is_relative(right, left):
                raise SatelliteCalibrationBlindRereviewError(f"{left_name} overlaps {right_name}")
    return definition, root, directories


def _unique(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        blind_id = row.get("blind_item_id")
        if not isinstance(blind_id, str) or not _BLIND_ID.fullmatch(blind_id):
            raise SatelliteCalibrationBlindRereviewError(f"{label} has invalid blind ID")
        if blind_id in result:
            raise SatelliteCalibrationBlindRereviewError(f"{label} has duplicate blind ID")
        result[blind_id] = row
    return result


def _require_label(value: Any, label: str) -> str:
    if value not in LABELS:
        raise SatelliteCalibrationBlindRereviewError(f"{label} has invalid label")
    return str(value)


def resolve_panel(a_labels: Mapping[str, str], b_labels: Mapping[str, str], c_labels: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Apply the fixed A/B then independent-C decision rule."""
    if set(a_labels) != set(b_labels):
        raise SatelliteCalibrationBlindRereviewError("A/B ID sets differ")
    disagreements = {key for key in a_labels if a_labels[key] != b_labels[key]}
    if set(c_labels) != disagreements:
        raise SatelliteCalibrationBlindRereviewError("C IDs must equal A/B disagreements")
    finals: dict[str, str] = {}
    bases: dict[str, str] = {}
    for blind_id in sorted(a_labels):
        a = _require_label(a_labels[blind_id], "reviewer A")
        b = _require_label(b_labels[blind_id], "reviewer B")
        if a == b:
            finals[blind_id], bases[blind_id] = a, "ab_agreement"
            continue
        c = _require_label(c_labels[blind_id], "adjudicator C")
        if c == a or c == b:
            finals[blind_id], bases[blind_id] = c, "two_of_three_majority"
        else:
            finals[blind_id], bases[blind_id] = "uncertain", "three_way_uncertain"
    return finals, bases


def _load_rows(directories: Mapping[str, Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    for name in ("preparation", "aggregate"):
        manifest_raw = (directories[name] / "manifest.json").read_bytes()
        expected_sidecar = f"{_sha(manifest_raw)}  manifest.json\n".encode("ascii")
        if (directories[name] / "manifest.sha256").read_bytes() != expected_sidecar:
            raise SatelliteCalibrationBlindRereviewError(f"{name} manifest sidecar mismatch")
    aggregate_manifest = _read_json(directories["aggregate"] / "manifest.json", "aggregate manifest", canonical=True)
    aggregate_sha = _sha((directories["aggregate"] / "manifest.json").read_bytes())
    queue = _read_jsonl(directories["aggregate"] / "reviewer-queue.jsonl", "aggregate reviewer queue", sorted_keys=True)
    blocked = _read_jsonl(directories["aggregate"] / "blocked-multitile.jsonl", "aggregate blocked rows", sorted_keys=True)
    a = _read_jsonl(directories["reviewer_a"] / "decisions.jsonl", "reviewer A decisions")
    b = _read_jsonl(directories["reviewer_b"] / "reviews.jsonl", "reviewer B reviews")
    c = _read_jsonl(directories["adjudicator_c"] / "decisions.jsonl", "adjudicator C decisions", sorted_keys=True)
    if len(queue) != EXPECTED["reviewed_rows"] or len(blocked) != EXPECTED["blocked_rows"]:
        raise SatelliteCalibrationBlindRereviewError("aggregate row partition mismatch")
    if aggregate_manifest.get("format") != "datacenter-atlas-satellite-calibration-v2-aggregate-v1" or aggregate_manifest.get("summary", {}).get("blind_items_ready_for_review") != 36 or aggregate_manifest.get("summary", {}).get("blind_items_blocked_multitile") != 7:
        raise SatelliteCalibrationBlindRereviewError("aggregate manifest semantic drift")
    qi, ai, bi, ci = (_unique(rows, name) for rows, name in ((queue,"queue"),(a,"A"),(b,"B"),(c,"C")))
    if set(qi) != set(ai) or set(qi) != set(bi):
        raise SatelliteCalibrationBlindRereviewError("review ID set mismatch")
    a_labels: dict[str, str] = {}
    b_labels: dict[str, str] = {}
    c_labels: dict[str, str] = {}
    a_keys = {"schema_version","review_status","aggregate_manifest_sha256","blind_item_id","comparison_png_path","comparison_png_bytes","comparison_png_sha256","label","reason_code","rationale","confidence","data_centre_identity_claim","lifecycle_claim","operator_claim","power_claim"}
    b_keys = {"blind_item_id","label","visual_rationale","comparison_sha256"}
    c_keys = {"blind_item_id","comparison_png","label","visual_basis"}
    queue_keys = {"algorithm_version","aoi_bbox_wgs84","artifacts","blind_item_id","entity","evidence_constraints","rerun_spec_sha256","schema_version","selected_scenes","source_shard","state"}
    blocked_keys = {"aoi_bbox_wgs84","attempts","blind_item_id","blocker","entity","failure_evidence_sha256","rerun_spec_sha256","schema_version","selected_scenes","source_shard","state"}
    for blind_id, qrow in qi.items():
        if set(qrow) != queue_keys or qrow.get("schema_version") != 1 or qrow.get("algorithm_version") != "sentinel-2-l2a-change-v2" or qrow.get("state") != "awaiting_blind_analyst_review":
            raise SatelliteCalibrationBlindRereviewError("aggregate reviewer queue schema drift")
        if set(ai[blind_id]) != a_keys or set(bi[blind_id]) != b_keys:
            raise SatelliteCalibrationBlindRereviewError("review schema drift")
        artifact = qrow.get("artifacts", {}).get("comparison.png", {})
        if ai[blind_id]["aggregate_manifest_sha256"] != aggregate_sha:
            raise SatelliteCalibrationBlindRereviewError("reviewer A aggregate hash mismatch")
        if any(ai[blind_id][key] is not False for key in ("data_centre_identity_claim","lifecycle_claim","operator_claim","power_claim")):
            raise SatelliteCalibrationBlindRereviewError("reviewer A claim flag is not false")
        if (ai[blind_id]["comparison_png_path"], ai[blind_id]["comparison_png_bytes"], ai[blind_id]["comparison_png_sha256"]) != (artifact.get("path"), artifact.get("bytes"), artifact.get("sha256")):
            raise SatelliteCalibrationBlindRereviewError("reviewer A comparison pin mismatch")
        if bi[blind_id]["comparison_sha256"] != artifact.get("sha256"):
            raise SatelliteCalibrationBlindRereviewError("reviewer B comparison pin mismatch")
        a_labels[blind_id] = _require_label(ai[blind_id]["label"], "reviewer A")
        b_labels[blind_id] = _require_label(bi[blind_id]["label"], "reviewer B")
    for blind_id, row in ci.items():
        if set(row) != c_keys or set(row.get("comparison_png", {})) != {"bytes", "sha256"}:
            raise SatelliteCalibrationBlindRereviewError("adjudicator C schema drift")
        if blind_id not in qi:
            raise SatelliteCalibrationBlindRereviewError("adjudicator C has extra ID")
        artifact = qi[blind_id]["artifacts"]["comparison.png"]
        if row["comparison_png"] != {"bytes": artifact["bytes"], "sha256": artifact["sha256"]}:
            raise SatelliteCalibrationBlindRereviewError("adjudicator C comparison pin mismatch")
        c_labels[blind_id] = _require_label(row["label"], "adjudicator C")
    finals, bases = resolve_panel(a_labels, b_labels, c_labels)
    if Counter(bases.values()) != {"ab_agreement": 28, "two_of_three_majority": 7, "three_way_uncertain": 1}:
        raise SatelliteCalibrationBlindRereviewError("decision-basis arithmetic mismatch")
    if Counter(finals.values()) != {"retain_site_scale_physical_change":16,"reject_non_site_or_unusable":19,"uncertain":1}:
        raise SatelliteCalibrationBlindRereviewError("final-label arithmetic mismatch")
    decisions: list[dict[str, Any]] = []
    for blind_id in sorted(qi):
        decisions.append({
            "blind_item_id": blind_id,
            "comparison_png": {key: qi[blind_id]["artifacts"]["comparison.png"][key] for key in ("bytes","path","sha256")},
            "reviewer_a": {key: ai[blind_id][key] for key in ("confidence","label","rationale","reason_code")},
            "reviewer_b": {key: bi[blind_id][key] for key in ("label","visual_rationale")},
            "adjudicator_c": None if blind_id not in ci else {key: ci[blind_id][key] for key in ("label","visual_basis")},
            "final_label": finals[blind_id],
            "decision_basis": bases[blind_id],
            "claim_constraints": CLAIM_CONSTRAINTS,
            "schema_version": SCHEMA_VERSION,
        })
    # Historical labels are deliberately opened only after the final decisions exist.
    lineage = _read_jsonl(directories["preparation"] / "sealed/lineage.jsonl", "sealed historical lineage", sorted_keys=True)
    li = _unique(lineage, "lineage")
    blocked_i = _unique(blocked, "blocked")
    if set(li) != set(qi) | set(blocked_i) or set(qi) & set(blocked_i):
        raise SatelliteCalibrationBlindRereviewError("historical one-to-one join mismatch")
    joined: list[dict[str, Any]] = []
    for decision in decisions:
        lineage_row = li[decision["blind_item_id"]]
        historical = lineage_row.get("prior_analyst_provenance", {}).get("outcome")
        if historical not in {"retain", "reject"}:
            raise SatelliteCalibrationBlindRereviewError("invalid historical label")
        joined.append({"blind_decision": decision, "historical_lineage": lineage_row, "historical_label": historical, "schema_version": SCHEMA_VERSION})
    blocked_joined = []
    for blind_id in sorted(blocked_i):
        if set(blocked_i[blind_id]) != blocked_keys or blocked_i[blind_id].get("schema_version") != 1 or blocked_i[blind_id].get("state") != "blocked_multitile_required" or blocked_i[blind_id].get("blocker") != "aoi_crosses_scene_asset_requires_multitile_mosaic":
            raise SatelliteCalibrationBlindRereviewError("blocked row schema drift")
        historical = li[blind_id].get("prior_analyst_provenance", {}).get("outcome")
        if historical not in {"retain", "reject"}:
            raise SatelliteCalibrationBlindRereviewError("invalid blocked historical label")
        blocked_joined.append({"blind_item_id": blind_id,"historical_label": historical,"historical_lineage": li[blind_id],"numerical_state": blocked_i[blind_id],"schema_version":SCHEMA_VERSION,"v2_decision":None})
    return decisions, joined, blocked_joined, queue, aggregate_manifest


def _summary(decisions: Sequence[Mapping[str, Any]], joined: Sequence[Mapping[str, Any]], blocked: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    basis = Counter(row["decision_basis"] for row in decisions)
    finals = Counter(row["final_label"] for row in decisions)
    transitions = Counter((row["historical_label"], row["blind_decision"]["final_label"]) for row in joined)
    historical_reviewed = Counter(row["historical_label"] for row in joined)
    historical_blocked = Counter(row["historical_label"] for row in blocked)
    binary = [row for row in joined if row["blind_decision"]["final_label"] != "uncertain"]
    same = sum((row["historical_label"] == "retain") == (row["blind_decision"]["final_label"] == "retain_site_scale_physical_change") for row in binary)
    result = {
        "agreement_measure": {"denominator":len(binary),"numerator":same,"raw_label_agreement_percent":same/len(binary)*100,"semantics":"descriptive raw binary label agreement; not accuracy, precision, recall, or truth"},
        "blocked_historical_labels": {"reject":historical_blocked["reject"],"retain":historical_blocked["retain"]},
        "decision_basis": {"ab_agreement":basis["ab_agreement"],"two_of_three_majority":basis["two_of_three_majority"],"three_way_uncertain":basis["three_way_uncertain"]},
        "final_labels": {"reject_non_site_or_unusable":finals["reject_non_site_or_unusable"],"retain_site_scale_physical_change":finals["retain_site_scale_physical_change"],"uncertain":finals["uncertain"]},
        "historical_labels_reviewed": {"reject":historical_reviewed["reject"],"retain":historical_reviewed["retain"]},
        "non_claims": CLAIM_CONSTRAINTS,
        "rows": {"aggregate":len(decisions)+len(blocked),"blocked_multitile_required":len(blocked),"reviewed":len(decisions)},
        "schema_version": SCHEMA_VERSION,
        "transition_matrix": {"reject_to_reject":transitions[("reject","reject_non_site_or_unusable")],"reject_to_retain":transitions[("reject","retain_site_scale_physical_change")],"reject_to_uncertain":transitions[("reject","uncertain")],"retain_to_reject":transitions[("retain","reject_non_site_or_unusable")],"retain_to_retain":transitions[("retain","retain_site_scale_physical_change")],"retain_to_uncertain":transitions[("retain","uncertain")]},
    }
    expected_checks = (result["rows"] == {"aggregate":43,"blocked_multitile_required":7,"reviewed":36} and result["final_labels"] == {"reject_non_site_or_unusable":19,"retain_site_scale_physical_change":16,"uncertain":1} and result["decision_basis"] == {"ab_agreement":28,"two_of_three_majority":7,"three_way_uncertain":1} and result["transition_matrix"] == {"reject_to_reject":19,"reject_to_retain":5,"reject_to_uncertain":1,"retain_to_reject":0,"retain_to_retain":11,"retain_to_uncertain":0} and (len(binary),same)==(35,30) and result["blocked_historical_labels"]=={"reject":6,"retain":1})
    if not expected_checks:
        raise SatelliteCalibrationBlindRereviewError("summary arithmetic mismatch")
    return result


def _readme(summary: Mapping[str, Any], deviations: Sequence[Mapping[str, Any]]) -> bytes:
    return ("""# Algorithm-v2 identity-blind rereview audit\n\nThis immutable release closes a descriptive comparison-image rereview of 36 algorithm-v2 numerical outputs. It is not accuracy, precision, recall, truth, production calibration, threshold validation, construction truth, or SemiAnalysis parity. Retention means only coherent site-scale physical change was visible; it does not identify a data centre or establish lifecycle, type, operator, power, energy, PUE, or workload.\n\nVersion 5 supersedes byte-preserved versions 1 through 4 only for publication mechanics. Version 4 is retained as rejected historical evidence because a target substitution during its successful parent-fsync path could evade its last identity check. Version 5 binds the output parent and release tree by open descriptors, uses an atomic no-clobber rename, fsyncs every directory-entry mutation, and revalidates the parent path, published target identity, exact frozen file identities, modes, and bytes after the publication fsync before returning success. Failure recovery never recursively deletes a pathname: it preserves unrelated substitutions and conservatively retains any writer-owned tree for explicit inspection, reporting the primary failure and every recovery or fsync failure together. The review arithmetic is unchanged.\n\nThe fixed rule was applied before historical labels were joined: A/B agreement wins; for the eight disagreements, C matching A or B gives a two-of-three majority; a three-way split becomes uncertain. The result is 16 retain, 19 reject, and one uncertain: 28 A/B agreements, seven two-of-three decisions, and one three-way uncertain. Seven additional rows remain `blocked_multitile_required` and have no v2 decision.\n\nAmong 35 binary-comparable reviewed rows, 30 labels were the same as the historical analyst label (85.71428571428571% raw label agreement). This is descriptive agreement only.\n\n## Protocol deviations\n\n- Reviewer B briefly exposed only blind `after.png` paths before schema clarification. No extra image or metadata was opened; identity blindness was not compromised.\n- After A and B finished but before C finished, the orchestration operator accidentally printed the first three sealed lineage rows: `v2rr-05d2f657bb54351175a429c7`, `v2rr-0b6e3c624b96fb431887b8d4`, and `v2rr-11a86c623834d73b2c563b8a`. C ran fork-isolated and received only the eight blind IDs, with no labels or history; the operator did not adjudicate. C's independent review therefore remained uncontaminated.\n\nThe same disclosures are structured in `protocol-deviations.json`. `blind-decisions.jsonl` contains the closed panel resolution, `calibration-records.jsonl` joins historical provenance only after that resolution, and `blocked-multitile.jsonl` preserves the seven unresolved rows without assigning decisions.\n""").encode("utf-8")


def _builder_pins(root: Path) -> dict[str, Any]:
    result = {}
    for relative in BUILDER_FILES:
        path = _inside(root, relative, f"builder {relative}")
        if not path.is_file() or path.is_symlink():
            raise SatelliteCalibrationBlindRereviewError("builder file missing")
        result[relative] = _pin(path)
    return result


def _payloads(definition_path: Path, output_dir: Path | None = None) -> tuple[dict[str, bytes], dict[str, Any], Path]:
    definition, root, directories = _source_state(definition_path, output_dir)
    decisions, joined, blocked, _, _ = _load_rows(directories)
    summary = _summary(decisions, joined, blocked)
    deviations = definition["protocol_deviations"]
    if not isinstance(deviations, list) or len(deviations) != 2 or not all(isinstance(row, dict) and row.get("occurred") is True for row in deviations):
        raise SatelliteCalibrationBlindRereviewError("protocol deviation disclosure drift")
    payloads = {
        "ATTRIBUTION.txt": b"Derived from the pinned local Sentinel comparison-review artifacts and prior analyst provenance. See manifest.json for exact source pins.\n",
        "README.md": _readme(summary, deviations),
        "blind-decisions.jsonl": canonical_jsonl(decisions),
        "blocked-multitile.jsonl": canonical_jsonl(blocked),
        "calibration-records.jsonl": canonical_jsonl(joined),
        "protocol-deviations.json": canonical_json({"protocol_deviations": deviations, "schema_version": SCHEMA_VERSION}),
        "summary.json": canonical_json(summary),
    }
    manifest = {
        "builder": _builder_pins(root),
        "definition": {"path":definition_path.resolve().relative_to(root).as_posix(), **_pin(definition_path)},
        "format": RELEASE_FORMAT,
        "outputs": {name:{"bytes":len(raw),"mode":"0444","sha256":_sha(raw)} for name,raw in sorted(payloads.items())},
        "release_id": definition["release_id"],
        "schema_version": SCHEMA_VERSION,
        "sources": definition["sources"],
        "summary": summary,
    }
    payloads["manifest.json"] = canonical_json(manifest)
    payloads["manifest.sha256"] = f"{_sha(payloads['manifest.json'])}  manifest.json\n".encode("ascii")
    return payloads, manifest, root


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_frozen_files(path: Path) -> None:
    """Persist every file inode after chmod has set the final 0444 mode."""

    for child in sorted(path.rglob("*")):
        if child.is_file() and not child.is_symlink():
            if _mode(child) != "0444":
                raise SatelliteCalibrationBlindRereviewError(
                    f"frozen file mode drift before fsync: {child.name}"
                )
            _fsync_file(child)


def _freeze(path: Path) -> None:
    for child in path.rglob("*"):
        if child.is_symlink():
            raise SatelliteCalibrationBlindRereviewError("staging tree contains symlink")
        os.chmod(child, 0o555 if child.is_dir() else 0o444)
    os.chmod(path, 0o555)


def _cleanup(path: Path) -> None:
    if path.exists():
        for child in path.rglob("*"):
            if not child.is_symlink(): os.chmod(child, 0o755 if child.is_dir() else 0o644)
        os.chmod(path, 0o755)
        shutil.rmtree(path)


_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_READ_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


def _identity_text(identity: tuple[int, int]) -> str:
    return f"device={identity[0]},inode={identity[1]}"


def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _stat_at(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _require_directory_identity_at(
    parent_fd: int,
    name: str,
    expected: tuple[int, int],
    label: str,
) -> os.stat_result:
    value = _stat_at(parent_fd, name)
    if value is None:
        raise SatelliteCalibrationBlindRereviewError(f"{label} is absent")
    if not stat.S_ISDIR(value.st_mode) or _identity_from_stat(value) != expected:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} identity mismatch: expected {_identity_text(expected)}, "
            f"found {_identity_text(_identity_from_stat(value))}"
        )
    return value


def _require_directory_path_identity(
    path: Path, expected: tuple[int, int], label: str
) -> os.stat_result:
    try:
        value = os.lstat(path)
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} path is unavailable"
        ) from error
    if not stat.S_ISDIR(value.st_mode) or _identity_from_stat(value) != expected:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} path identity mismatch: expected {_identity_text(expected)}, "
            f"found {_identity_text(_identity_from_stat(value))}"
        )
    return value


def _require_open_directory_identity(
    descriptor: int, expected: tuple[int, int], label: str
) -> os.stat_result:
    value = os.fstat(descriptor)
    if not stat.S_ISDIR(value.st_mode) or _identity_from_stat(value) != expected:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} descriptor identity mismatch"
        )
    return value


def _open_bound_directory(
    path: Path, root: Path, label: str
) -> tuple[Path, int, tuple[int, int]]:
    lexical = _lexical_absolute(path)
    _reject_symlink_components(lexical, root, label)
    try:
        before = os.lstat(lexical)
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} is unavailable"
        ) from error
    if not stat.S_ISDIR(before.st_mode):
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} is not a regular directory"
        )
    identity = _identity_from_stat(before)
    try:
        descriptor = os.open(lexical, _DIRECTORY_OPEN_FLAGS)
    except OSError as error:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} cannot be opened safely"
        ) from error
    try:
        _require_open_directory_identity(descriptor, identity, label)
        _require_directory_path_identity(lexical, identity, label)
    except Exception:
        os.close(descriptor)
        raise
    return lexical, descriptor, identity


def _open_output_parent(
    output_dir: Path, root: Path
) -> tuple[Path, Path, int, tuple[int, int]]:
    output = _lexical_absolute(output_dir)
    _reject_symlink_components(output, root, "output")
    if output == root or output.name in {"", ".", ".."}:
        raise SatelliteCalibrationBlindRereviewError("output path is invalid")
    parent, parent_fd, parent_identity = _open_bound_directory(
        output.parent, root, "output parent"
    )
    try:
        if _stat_at(parent_fd, output.name) is not None:
            raise SatelliteCalibrationBlindRereviewError("output already exists")
    except Exception:
        os.close(parent_fd)
        raise
    return output, parent, parent_fd, parent_identity


def _sync_parent(parent_fd: int, phase: str) -> None:
    try:
        os.fsync(parent_fd)
    except OSError as error:
        detail = error.strerror or str(error)
        raise OSError(error.errno, f"{phase}: {detail}") from error


def _rename_noreplace(parent_fd: int, source_name: str, target_name: str) -> None:
    if (
        not source_name
        or not target_name
        or "/" in source_name
        or "/" in target_name
        or source_name in {".", ".."}
        or target_name in {".", ".."}
    ):
        raise SatelliteCalibrationBlindRereviewError(
            "rename names must be single components"
        )
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    target = os.fsencode(target_name)
    if sys.platform == "darwin":
        function = library.renameatx_np
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(parent_fd, source, parent_fd, target, 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(parent_fd, source, parent_fd, target, 0x00000001)
    else:  # pragma: no cover - supported publication hosts are Darwin/Linux
        raise OSError(errno.ENOTSUP, "atomic no-clobber directory rename unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), target_name)


def _create_staging(
    parent_fd: int, target_name: str
) -> tuple[str, int, tuple[int, int]]:
    for _ in range(100):
        name = f".{target_name}.staging-{secrets.token_hex(8)}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            descriptor = -1
            value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = _identity_from_stat(value)
            descriptor = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd)
            _require_open_directory_identity(descriptor, identity, "staging")
            _require_directory_identity_at(parent_fd, name, identity, "staging")
        except Exception as primary_error:
            if descriptor >= 0:
                os.close(descriptor)
            errors = [f"staging open failed: {_error_text(primary_error)}"]
            try:
                _sync_parent(parent_fd, "failed staging creation parent fsync")
            except Exception as sync_error:
                errors.append(
                    f"staging creation parent fsync failed: {_error_text(sync_error)}"
                )
            errors.append(
                f"no deletion attempted; entry {name!r} was preserved for inspection"
            )
            raise SatelliteCalibrationBlindRereviewError(
                " | ".join(errors)
            ) from primary_error
        return name, descriptor, identity
    raise SatelliteCalibrationBlindRereviewError(
        "could not allocate a unique staging name"
    )


def _write_payloads(
    directory_fd: int, payloads: Mapping[str, bytes]
) -> dict[str, tuple[int, int]]:
    identities: dict[str, tuple[int, int]] = {}
    for name, raw in sorted(payloads.items()):
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            identities[name] = _identity_from_stat(os.fstat(descriptor))
            view = memoryview(raw)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError(errno.EIO, f"zero-byte write for {name}")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        after = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(after.st_mode)
            or _identity_from_stat(after) != identities[name]
        ):
            raise SatelliteCalibrationBlindRereviewError(
                f"staging file identity changed after write: {name}"
            )
    os.fsync(directory_fd)
    return identities


def _freeze_bound_staging(
    parent_fd: int,
    staging_name: str,
    staging_fd: int,
    staging_identity: tuple[int, int],
    file_identities: Mapping[str, tuple[int, int]],
) -> None:
    _require_directory_identity_at(
        parent_fd, staging_name, staging_identity, "staging"
    )
    _require_open_directory_identity(staging_fd, staging_identity, "staging")
    if set(os.listdir(staging_fd)) != set(file_identities) or set(file_identities) != RELEASE_FILES:
        raise SatelliteCalibrationBlindRereviewError(
            "staging file set is not closed"
        )
    for name in sorted(file_identities):
        before = os.stat(name, dir_fd=staging_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or _identity_from_stat(before) != file_identities[name]
        ):
            raise SatelliteCalibrationBlindRereviewError(
                f"staging file identity mismatch before freeze: {name}"
            )
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=staging_fd)
        try:
            opened = os.fstat(descriptor)
            if _identity_from_stat(opened) != file_identities[name]:
                raise SatelliteCalibrationBlindRereviewError(
                    f"staging file changed while opening: {name}"
                )
            os.fchmod(descriptor, 0o444)
            os.fsync(descriptor)
            frozen = os.fstat(descriptor)
            if (
                _identity_from_stat(frozen) != file_identities[name]
                or frozen.st_mode & 0o777 != 0o444
            ):
                raise SatelliteCalibrationBlindRereviewError(
                    f"staging file did not freeze durably: {name}"
                )
        finally:
            os.close(descriptor)
        after = os.stat(name, dir_fd=staging_fd, follow_symlinks=False)
        if _identity_from_stat(after) != file_identities[name]:
            raise SatelliteCalibrationBlindRereviewError(
                f"staging file path changed after freeze: {name}"
            )
    os.fchmod(staging_fd, 0o555)
    os.fsync(staging_fd)
    frozen_root = _require_directory_identity_at(
        parent_fd, staging_name, staging_identity, "staging"
    )
    if frozen_root.st_mode & 0o777 != 0o555:
        raise SatelliteCalibrationBlindRereviewError(
            "staging directory mode mismatch"
        )


def _read_all(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _snapshot_file_identities(
    directory_fd: int,
) -> dict[str, tuple[int, int]]:
    names = set(os.listdir(directory_fd))
    if names != RELEASE_FILES:
        raise SatelliteCalibrationBlindRereviewError(
            "release file set is not closed"
        )
    identities: dict[str, tuple[int, int]] = {}
    for name in sorted(names):
        value = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(value.st_mode):
            raise SatelliteCalibrationBlindRereviewError(
                f"release node is not a regular file: {name}"
            )
        identities[name] = _identity_from_stat(value)
    return identities


def _require_frozen_release(
    directory_fd: int,
    directory_identity: tuple[int, int],
    file_identities: Mapping[str, tuple[int, int]],
    payloads: Mapping[str, bytes],
    label: str,
) -> None:
    root_before = _require_open_directory_identity(
        directory_fd, directory_identity, label
    )
    if root_before.st_mode & 0o777 != 0o555:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} directory mode mismatch"
        )
    names = set(os.listdir(directory_fd))
    if (
        names != RELEASE_FILES
        or names != set(file_identities)
        or names != set(payloads)
    ):
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} file set is not closed"
        )
    for name in sorted(names):
        before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_mode & 0o777 != 0o444
            or _identity_from_stat(before) != file_identities[name]
        ):
            raise SatelliteCalibrationBlindRereviewError(
                f"{label} file mode, type, or identity mismatch: {name}"
            )
        descriptor = os.open(name, _FILE_READ_FLAGS, dir_fd=directory_fd)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_mode & 0o777 != 0o444
                or _identity_from_stat(opened) != file_identities[name]
            ):
                raise SatelliteCalibrationBlindRereviewError(
                    f"{label} file changed while opening: {name}"
                )
            raw = _read_all(descriptor)
            after = os.fstat(descriptor)
            if (
                _identity_from_stat(after) != file_identities[name]
                or after.st_mode & 0o777 != 0o444
                or after.st_size != len(raw)
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns
            ):
                raise SatelliteCalibrationBlindRereviewError(
                    f"{label} file changed while reading: {name}"
                )
        finally:
            os.close(descriptor)
        rebound = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if _identity_from_stat(rebound) != file_identities[name]:
            raise SatelliteCalibrationBlindRereviewError(
                f"{label} file pathname changed: {name}"
            )
        if raw != payloads[name]:
            raise SatelliteCalibrationBlindRereviewError(
                f"{name} differs from deterministic reproduction"
            )
    root_after = _require_open_directory_identity(
        directory_fd, directory_identity, label
    )
    if root_after.st_mode & 0o777 != 0o555:
        raise SatelliteCalibrationBlindRereviewError(
            f"{label} directory mode changed during validation"
        )


def _safe_stat_for_recovery(
    parent_fd: int,
    name: str,
    label: str,
    errors: list[str],
) -> tuple[bool, os.stat_result | None]:
    try:
        return True, _stat_at(parent_fd, name)
    except BaseException as error:
        errors.append(f"{label} inspection failed: {_error_text(error)}")
        return False, None


def _recovery_name(parent_fd: int, target_name: str) -> str:
    for _ in range(100):
        name = f".{target_name}.failed-owned-{secrets.token_hex(12)}"
        if _stat_at(parent_fd, name) is None:
            return name
    raise SatelliteCalibrationBlindRereviewError(
        "could not allocate recovery quarantine name"
    )


def _quarantine_owned_target(
    *,
    parent_fd: int,
    target_name: str,
    tree_identity: tuple[int, int],
    errors: list[str],
) -> str | None:
    """Detach a public target without ever deleting the detached entry.

    The ownership check and rename cannot be made one atomic conditional POSIX
    operation.  If a racing substitute is renamed instead, its identity is
    detected after the rename and restoration is attempted with no-clobber
    semantics.  Regardless of restoration outcome, neither the substitute nor
    the writer-owned tree is recursively deleted.
    """

    try:
        quarantine_name = _recovery_name(parent_fd, target_name)
        _rename_noreplace(parent_fd, target_name, quarantine_name)
    except BaseException as error:
        errors.append(f"target quarantine rename failed: {_error_text(error)}")
        return None
    try:
        _sync_parent(parent_fd, "target quarantine parent fsync")
    except BaseException as error:
        errors.append(f"target quarantine parent fsync failed: {_error_text(error)}")
    known, quarantined = _safe_stat_for_recovery(
        parent_fd, quarantine_name, "quarantined entry", errors
    )
    if not known or quarantined is None:
        errors.append(
            f"quarantine rename returned but {quarantine_name!r} could not be proven"
        )
        return quarantine_name
    quarantined_identity = _identity_from_stat(quarantined)
    if stat.S_ISDIR(quarantined.st_mode) and quarantined_identity == tree_identity:
        errors.append(
            f"writer-owned tree retained for inspection at {quarantine_name!r}"
        )
        return quarantine_name

    errors.append(
        "a racing unrelated replacement was moved to recovery quarantine and "
        f"preserved: {quarantine_name!r} ({_identity_text(quarantined_identity)})"
    )
    target_known, target = _safe_stat_for_recovery(
        parent_fd, target_name, "target before substitute restoration", errors
    )
    if target_known and target is None:
        try:
            _rename_noreplace(parent_fd, quarantine_name, target_name)
        except BaseException as error:
            errors.append(f"substitute restoration rename failed: {_error_text(error)}")
        else:
            try:
                _sync_parent(parent_fd, "substitute restoration parent fsync")
            except BaseException as error:
                errors.append(
                    f"substitute restoration parent fsync failed: {_error_text(error)}"
                )
            restored_known, restored = _safe_stat_for_recovery(
                parent_fd, target_name, "restored substitute", errors
            )
            if (
                restored_known
                and restored is not None
                and _identity_from_stat(restored) == quarantined_identity
            ):
                errors.append("unrelated replacement restored to its original target name")
            else:
                errors.append("unrelated replacement restoration identity was not proven")
    elif target_known:
        errors.append(
            "target was occupied during substitute restoration; unrelated "
            f"replacement remains preserved at {quarantine_name!r}"
        )
    return quarantine_name


def _recover_publication_failure(
    *,
    primary_error: BaseException,
    parent_path: Path,
    parent_fd: int,
    parent_identity: tuple[int, int],
    staging_name: str,
    target_name: str,
    tree_identity: tuple[int, int],
) -> None:
    errors = [f"primary failure: {_error_text(primary_error)}"]
    try:
        _require_open_directory_identity(parent_fd, parent_identity, "output parent")
    except BaseException as error:
        errors.append(f"parent descriptor identity check failed: {_error_text(error)}")
    try:
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
    except BaseException as error:
        errors.append(f"parent path identity check failed: {_error_text(error)}")

    target_known, target = _safe_stat_for_recovery(
        parent_fd, target_name, "target", errors
    )
    staging_known, staging = _safe_stat_for_recovery(
        parent_fd, staging_name, "staging", errors
    )
    target_owned = (
        target_known
        and target is not None
        and stat.S_ISDIR(target.st_mode)
        and _identity_from_stat(target) == tree_identity
    )
    staging_owned = (
        staging_known
        and staging is not None
        and stat.S_ISDIR(staging.st_mode)
        and _identity_from_stat(staging) == tree_identity
    )
    quarantine_name: str | None = None
    if target_owned:
        quarantine_name = _quarantine_owned_target(
            parent_fd=parent_fd,
            target_name=target_name,
            tree_identity=tree_identity,
            errors=errors,
        )
    elif target_known and target is not None:
        errors.append(
            "target path contains an unrelated replacement that was preserved: "
            f"{_identity_text(_identity_from_stat(target))}"
        )
    if staging_owned:
        errors.append(
            f"writer-owned staging tree retained for inspection at {staging_name!r}"
        )
    elif staging_known and staging is not None:
        errors.append(
            "staging path contains an unrelated replacement that was preserved: "
            f"{_identity_text(_identity_from_stat(staging))}"
        )
    if not target_owned and not staging_owned:
        errors.append(
            "writer-owned tree is no longer bound to the target or staging name; "
            "no pathname deletion was attempted"
        )

    # Re-inspect every public/recovery name. Inspection failures are appended,
    # never allowed to replace the primary publication error.
    final_names = [
        (target_name, "final target"),
        (staging_name, "final staging"),
    ]
    if quarantine_name is not None:
        final_names.append((quarantine_name, "final quarantine"))
    for name, label in final_names:
        _safe_stat_for_recovery(parent_fd, name, label, errors)
    try:
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
    except BaseException as error:
        errors.append(f"final parent identity check failed: {_error_text(error)}")
    raise SatelliteCalibrationBlindRereviewError(
        "publication failed | " + " | ".join(errors)
    ) from primary_error


def validate_satellite_calibration_blind_rereview(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = _project_root(definition_path)
    output, directory_fd, output_identity = _open_bound_directory(
        output_dir, root, "output"
    )
    try:
        expected, manifest, _ = _payloads(definition_path, output)
        file_identities = _snapshot_file_identities(directory_fd)
        _require_frozen_release(
            directory_fd,
            output_identity,
            file_identities,
            expected,
            "output",
        )
        _require_open_directory_identity(directory_fd, output_identity, "output")
        _require_directory_path_identity(output, output_identity, "output")
        parsed = json.loads(expected["manifest.json"].decode("utf-8"))
        if parsed != manifest:
            raise SatelliteCalibrationBlindRereviewError(
                "manifest semantic mismatch"
            )
        return manifest
    finally:
        os.close(directory_fd)


def write_satellite_calibration_blind_rereview(
    output_dir: Path, *, definition_path: Path
) -> dict[str, Any]:
    root = _project_root(definition_path)
    output = _lexical_absolute(output_dir)
    _reject_symlink_components(output, root, "output")
    if output.exists() or output.is_symlink():
        raise SatelliteCalibrationBlindRereviewError("output already exists")
    # Source closure, output overlap, definition, and deterministic payload
    # checks complete before any directory entry is created.
    payloads, manifest, _ = _payloads(definition_path, output)
    output, parent_path, parent_fd, parent_identity = _open_output_parent(
        output, root
    )
    staging_name: str | None = None
    staging_fd: int | None = None
    staging_identity: tuple[int, int] | None = None
    try:
        _require_open_directory_identity(parent_fd, parent_identity, "output parent")
        _require_directory_path_identity(parent_path, parent_identity, "output parent")
        staging_name, staging_fd, staging_identity = _create_staging(
            parent_fd, output.name
        )
        try:
            _sync_parent(parent_fd, "staging creation parent fsync")
            file_identities = _write_payloads(staging_fd, payloads)
            _freeze_bound_staging(
                parent_fd,
                staging_name,
                staging_fd,
                staging_identity,
                file_identities,
            )
            _sync_parent(parent_fd, "frozen staging parent fsync")
            _require_directory_path_identity(
                parent_path, parent_identity, "output parent"
            )
            _require_directory_identity_at(
                parent_fd, staging_name, staging_identity, "staging"
            )
            staging_path = parent_path / staging_name
            validated = validate_satellite_calibration_blind_rereview(
                staging_path, definition_path=definition_path
            )
            if validated != manifest:
                raise SatelliteCalibrationBlindRereviewError(
                    "frozen staging validation returned a differing manifest"
                )
            _require_frozen_release(
                staging_fd,
                staging_identity,
                file_identities,
                payloads,
                "validated staging",
            )
            _require_directory_identity_at(
                parent_fd, staging_name, staging_identity, "validated staging"
            )
            _require_directory_path_identity(
                parent_path, parent_identity, "output parent"
            )
            if _stat_at(parent_fd, output.name) is not None:
                raise SatelliteCalibrationBlindRereviewError(
                    "output appeared before publication"
                )
            _rename_noreplace(parent_fd, staging_name, output.name)
            _require_directory_identity_at(
                parent_fd, output.name, staging_identity, "published target"
            )
            if _stat_at(parent_fd, staging_name) is not None:
                raise SatelliteCalibrationBlindRereviewError(
                    "staging name remains after publication rename"
                )
            _sync_parent(parent_fd, "publication parent fsync")

            # This is the v5 repair boundary. A successful fsync is not enough:
            # re-prove the path bindings and every frozen byte after that call,
            # then recheck the public target after the byte walk before success.
            _require_open_directory_identity(
                parent_fd, parent_identity, "output parent"
            )
            _require_directory_path_identity(
                parent_path, parent_identity, "output parent"
            )
            _require_directory_identity_at(
                parent_fd, output.name, staging_identity, "post-fsync target"
            )
            if _stat_at(parent_fd, staging_name) is not None:
                raise SatelliteCalibrationBlindRereviewError(
                    "post-fsync staging name unexpectedly exists"
                )
            _require_frozen_release(
                staging_fd,
                staging_identity,
                file_identities,
                payloads,
                "post-fsync published release",
            )
            _require_directory_identity_at(
                parent_fd, output.name, staging_identity, "final published target"
            )
            _require_directory_path_identity(
                parent_path, parent_identity, "final output parent"
            )
            _require_directory_identity_at(
                parent_fd,
                output.name,
                staging_identity,
                "return-bound published target",
            )
            return manifest
        except BaseException as primary_error:
            assert staging_name is not None and staging_identity is not None
            _recover_publication_failure(
                primary_error=primary_error,
                parent_path=parent_path,
                parent_fd=parent_fd,
                parent_identity=parent_identity,
                staging_name=staging_name,
                target_name=output.name,
                tree_identity=staging_identity,
            )
            raise AssertionError("unreachable")
    finally:
        if staging_fd is not None:
            os.close(staging_fd)
        os.close(parent_fd)
