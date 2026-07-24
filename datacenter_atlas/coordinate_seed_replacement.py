"""Fail-closed curated-input replacement for coordinate-only seed successors."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CoordinateReplacement:
    """Bind one coordinate-only successor to its exact curated predecessor."""

    predecessor_path: str
    predecessor_sha256: str
    successor_path: str
    successor_bytes: int
    successor_sha256: str
    campus_key: str
    project_key: str
    added_evidence_key: str


def parse_utc(value: str, *, label: str) -> datetime:
    """Parse a canonical second-resolution UTC timestamp."""

    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} is not a valid timestamp") from error
    if parsed.microsecond:
        raise ValueError(f"{label} must use whole-second precision")
    return parsed.astimezone(timezone.utc)


def _document(
    path: Path, *, expected_mode: int, require_canonical: bool
) -> tuple[bytes, dict[str, Any]]:
    if (
        not path.is_file()
        or path.is_symlink()
        or not stat.S_ISREG(path.stat().st_mode)
    ):
        raise ValueError(f"curated input must be an ordinary file: {path}")
    if stat.S_IMODE(path.stat().st_mode) != expected_mode:
        raise ValueError(
            f"curated input mode must be {expected_mode:04o}: {path}"
        )
    raw = path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError(f"curated input root must be an object: {path}")
    expected = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
    if require_canonical and raw != expected:
        raise ValueError(f"curated input JSON is not canonical: {path}")
    return raw, document


def _validate_evidence_times(
    documents: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    recorded_at: str,
    validation_wall_clock: datetime,
) -> None:
    transaction = parse_utc(recorded_at, label="release recorded_at")
    if validation_wall_clock.tzinfo is None:
        raise ValueError("validation wall clock must include a timezone")
    wall_clock = validation_wall_clock.astimezone(timezone.utc)
    if transaction > wall_clock:
        raise ValueError("release recorded_at is later than the current build time")
    for relative, document in documents:
        evidence = document.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"curated input has no evidence: {relative}")
        for index, row in enumerate(evidence):
            if not isinstance(row, dict):
                raise ValueError(f"curated evidence is not an object: {relative}")
            observed = parse_utc(
                row.get("retrieved_at"),
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if observed > transaction:
                raise ValueError(
                    "source evidence retrieved_at is later than release recorded_at: "
                    f"{relative} evidence[{index}]"
                )
            if observed > wall_clock:
                raise ValueError(
                    "source evidence retrieved_at is later than the current build time: "
                    f"{relative} evidence[{index}]"
                )


def _validate_coordinate_only_delta(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    specification: CoordinateReplacement,
) -> None:
    if set(predecessor) != set(successor) or predecessor.get("schema_version") != "1.1":
        raise ValueError("coordinate successor schema differs from its predecessor")
    before_evidence = predecessor.get("evidence")
    after_evidence = successor.get("evidence")
    if (
        not isinstance(before_evidence, list)
        or not isinstance(after_evidence, list)
        or after_evidence[:-1] != before_evidence
        or len(after_evidence) != len(before_evidence) + 1
    ):
        raise ValueError("coordinate successor evidence is not an exact one-row append")
    added = after_evidence[-1]
    if (
        not isinstance(added, dict)
        or added.get("key") != specification.added_evidence_key
        or added.get("kind") != "government_record"
    ):
        raise ValueError("coordinate successor added evidence differs")

    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(before_evidence)
    expected_keys = {
        "campus": specification.campus_key,
        "project": specification.project_key,
    }
    for entity_name, stable_key in expected_keys.items():
        before = predecessor.get(entity_name)
        after = successor.get(entity_name)
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError(f"coordinate successor lacks {entity_name}")
        if before.get("stable_key") != stable_key or after.get("stable_key") != stable_key:
            raise ValueError(f"coordinate successor {entity_name} identity differs")
        changed = {
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        }
        if changed != {"coordinates", "geometry", "evidence_key", "method"}:
            raise ValueError(
                f"coordinate successor {entity_name} changed non-coordinate fields: "
                f"{sorted(changed)}"
            )
        if before.get("coordinates") is not None or before.get("geometry") is not None:
            raise ValueError(f"coordinate predecessor {entity_name} was already located")
        coordinates = after.get("coordinates")
        geometry = after.get("geometry")
        if (
            not isinstance(coordinates, dict)
            or set(coordinates) != {"latitude", "longitude"}
            or not isinstance(geometry, dict)
            or after.get("evidence_key") != specification.added_evidence_key
            or after.get("method") != "authoritative_site_plan"
        ):
            raise ValueError(f"coordinate successor {entity_name} location differs")
        for key in changed:
            restored[entity_name][key] = copy.deepcopy(before[key])

    if restored != predecessor:
        raise ValueError("coordinate successor contains a non-coordinate claim delta")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor.get(section) != predecessor.get(section):
            raise ValueError(f"coordinate successor changed {section}")
        for claim in successor.get(section, []):
            if claim.get("evidence_key") == specification.added_evidence_key:
                raise ValueError("coordinate evidence was used for a non-coordinate claim")


def replace_curated_inputs(
    root: Path,
    base_rows: Sequence[Mapping[str, str]],
    replacements: Sequence[CoordinateReplacement],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    """Replace exact predecessors in place and validate every selected source."""

    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    if not replacements:
        raise ValueError("at least one coordinate replacement is required")
    predecessor_paths = [row.predecessor_path for row in replacements]
    successor_paths = [row.successor_path for row in replacements]
    if len(set(predecessor_paths)) != len(predecessor_paths):
        raise ValueError("coordinate predecessor paths must be unique")
    if len(set(successor_paths)) != len(successor_paths):
        raise ValueError("coordinate successor paths must be unique")
    if set(predecessor_paths) & set(successor_paths):
        raise ValueError("a coordinate path cannot be both predecessor and successor")

    rows = [dict(row) for row in base_rows]
    if any(set(row) != {"path", "sha256"} for row in rows):
        raise ValueError("base curated input row schema differs")
    paths = [row["path"] for row in rows]
    if len(set(paths)) != len(paths):
        raise ValueError("base curated input inventory contains duplicate paths")
    if set(successor_paths) & set(paths):
        raise ValueError("predecessor and successor coexist in the base inventory")

    by_predecessor = {row.predecessor_path: row for row in replacements}
    if {path for path in paths if path in by_predecessor} != set(predecessor_paths):
        raise ValueError("coordinate predecessor inventory is not exact")

    selected_documents: list[tuple[str, Mapping[str, Any]]] = []
    selected_paths: list[Path] = []
    output: list[dict[str, str]] = []
    for row in rows:
        specification = by_predecessor.get(row["path"])
        if specification is None:
            path = root / row["path"]
            # V69 contains accepted legacy inputs whose original formatting is
            # not canonical JSON. Preserve those exact pinned bytes instead of
            # retroactively imposing the successor publication contract.
            raw, document = _document(
                path, expected_mode=0o644, require_canonical=False
            )
            if hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError(f"base curated input hash differs: {row['path']}")
            output.append(row)
        else:
            if row["sha256"] != specification.predecessor_sha256:
                raise ValueError(
                    f"coordinate predecessor hash differs: {specification.predecessor_path}"
                )
            predecessor_path = root / specification.predecessor_path
            predecessor_raw, predecessor = _document(
                predecessor_path, expected_mode=0o644, require_canonical=True
            )
            if hashlib.sha256(predecessor_raw).hexdigest() != row["sha256"]:
                raise ValueError(
                    f"coordinate predecessor bytes differ: {specification.predecessor_path}"
                )
            path = root / specification.successor_path
            raw, document = _document(
                path, expected_mode=0o444, require_canonical=True
            )
            if (len(raw), hashlib.sha256(raw).hexdigest()) != (
                specification.successor_bytes,
                specification.successor_sha256,
            ):
                raise ValueError(
                    f"coordinate successor bytes differ: {specification.successor_path}"
                )
            _validate_coordinate_only_delta(predecessor, document, specification)
            output.append(
                {
                    "path": specification.successor_path,
                    "sha256": specification.successor_sha256,
                }
            )
        selected_documents.append((output[-1]["path"], document))
        selected_paths.append(path)

    if len(output) != len(rows) or len({row["path"] for row in output}) != len(rows):
        raise ValueError("coordinate replacement changed input cardinality")
    if any(path in {row["path"] for row in output} for path in predecessor_paths):
        raise ValueError("coordinate predecessor remained selected")
    if not set(successor_paths) <= {row["path"] for row in output}:
        raise ValueError("coordinate successor selection is incomplete")
    _validate_evidence_times(
        selected_documents,
        recorded_at=recorded_at,
        validation_wall_clock=wall_clock,
    )
    return output, selected_paths
