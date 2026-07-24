"""Canonical timestamp boundaries for bitemporal persistence and reads."""

from __future__ import annotations

import re
import sqlite3
from collections import OrderedDict
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar


_FRACTION_RE = re.compile(r"[.,]([0-9]+)")
_PERSISTED_TIMESTAMP_COLUMNS = {
    "evidence": ("retrieved_at",),
    "entities": ("created_at",),
    "entity_snapshots": ("recorded_at", "superseded_at"),
    "lifecycle_observations": ("recorded_at", "superseded_at"),
    "operating_model_observations": ("recorded_at", "superseded_at"),
    "workload_observations": ("recorded_at", "superseded_at"),
    "capacity_estimates": ("recorded_at", "superseded_at"),
    "administrative_assignments": ("recorded_at", "superseded_at"),
}
_TEMPORAL_PARTITIONS = {
    "entity_snapshots": ("entity_id", "as_of_date"),
    "lifecycle_observations": ("entity_id", "as_of_date"),
    "operating_model_observations": ("entity_id", "as_of_date"),
    "workload_observations": ("entity_id", "workload", "as_of_date"),
    "capacity_estimates": ("entity_id", "metric", "stage", "as_of_date"),
    "administrative_assignments": ("entity_id", "as_of_date"),
}
_STATE_CACHE_LIMIT = 32
_StateToken = tuple[int, int]
_StateCacheEntry = tuple[sqlite3.Connection, _StateToken]
_state_cache: OrderedDict[int, _StateCacheEntry] = OrderedDict()

P = ParamSpec("P")
R = TypeVar("R")


def _aware_datetime(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    fractions = _FRACTION_RE.findall(value)
    if any(
        len(fraction) > 6 and any(digit != "0" for digit in fraction[6:])
        for fraction in fractions
    ):
        raise ValueError(f"{field} has precision finer than one microsecond")
    try:
        parsed = datetime.fromisoformat(
            value.replace(",", ".").replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def canonical_read_cutoff(value: str, field: str = "recorded_at") -> str:
    """Normalize a whole-second read cutoff to the persistence representation."""

    return canonical_storage_timestamp(value, field)


def canonical_storage_timestamp(value: str, field: str) -> str:
    """Normalize an aware whole-second timestamp for persisted chronology."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    if any(
        any(digit != "0" for digit in fraction)
        for fraction in _FRACTION_RE.findall(value)
    ):
        raise ValueError(f"{field} must use whole-second precision")
    parsed = _aware_datetime(value, field).astimezone(UTC)
    if parsed.microsecond:
        raise ValueError(f"{field} must use whole-second precision")
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def persistence_timestamp_errors(connection: sqlite3.Connection) -> list[str]:
    """Return legacy timestamp rows that are unsafe for raw TEXT chronology."""

    existing_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    errors: list[str] = []
    noncanonical_tables: set[str] = set()
    for table, columns in _PERSISTED_TIMESTAMP_COLUMNS.items():
        if table not in existing_tables:
            continue
        selected = ", ".join(("id", *columns))
        for row in connection.execute(f"SELECT {selected} FROM {table} ORDER BY id"):
            row_id = row[0]
            for index, column in enumerate(columns, start=1):
                value = row[index]
                if value is None:
                    continue
                field = f"{table}.{row_id}.{column}"
                try:
                    canonical = canonical_storage_timestamp(value, field)
                except ValueError as error:
                    errors.append(f"{error}; explicit timestamp migration required")
                    noncanonical_tables.add(table)
                    continue
                if canonical != value:
                    errors.append(
                        f"{field} is not canonical whole-second UTC Z: {value!r}; "
                        f"canonical form is {canonical!r}; explicit timestamp migration "
                        "required"
                    )
                    noncanonical_tables.add(table)

    for table, partition_columns in _TEMPORAL_PARTITIONS.items():
        if table not in existing_tables or table in noncanonical_tables:
            continue
        selected = ", ".join(
            ("id", *partition_columns, "recorded_at", "superseded_at")
        )
        order = ", ".join((*partition_columns, "recorded_at", "id"))
        partitions: dict[tuple[object, ...], list[tuple[str, str, str | None]]] = {}
        for row in connection.execute(
            f"SELECT {selected} FROM {table} ORDER BY {order}"
        ):
            partition_size = len(partition_columns)
            key = tuple(row[index] for index in range(1, partition_size + 1))
            partitions.setdefault(key, []).append(
                (
                    str(row[0]),
                    str(row[partition_size + 1]),
                    row[partition_size + 2],
                )
            )
        for key, rows in partitions.items():
            label = ", ".join(
                f"{column}={value!r}"
                for column, value in zip(partition_columns, key, strict=True)
            )
            by_recorded_at: dict[str, list[str]] = {}
            for row_id, recorded_at, _superseded_at in rows:
                by_recorded_at.setdefault(recorded_at, []).append(row_id)
            duplicates = {
                recorded_at: ids
                for recorded_at, ids in by_recorded_at.items()
                if len(ids) > 1
            }
            if duplicates:
                duplicate_text = ", ".join(
                    f"{recorded_at!r} in ids {sorted(ids)!r}"
                    for recorded_at, ids in sorted(duplicates.items())
                )
                errors.append(
                    f"{table} logical partition ({label}) has duplicate recorded_at: "
                    f"{duplicate_text}; explicit chronology repair required"
                )
                continue
            for index, (row_id, _recorded_at, superseded_at) in enumerate(rows):
                expected = rows[index + 1][1] if index + 1 < len(rows) else None
                if superseded_at != expected:
                    errors.append(
                        f"{table}.{row_id}.superseded_at is {superseded_at!r}, "
                        f"expected exact next recorded_at {expected!r} for logical "
                        f"partition ({label}); explicit chronology repair required"
                    )
    return errors


def _state_token(connection: sqlite3.Connection) -> _StateToken:
    data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
    return connection.total_changes, data_version


def _cache_state(
    connection: sqlite3.Connection,
    token: _StateToken,
) -> None:
    key = id(connection)
    _state_cache[key] = (connection, token)
    _state_cache.move_to_end(key)
    while len(_state_cache) > _STATE_CACHE_LIMIT:
        _state_cache.popitem(last=False)


def require_canonical_persistence_state(connection: sqlite3.Connection) -> None:
    """Fail before temporal reads or writes when legacy TEXT ordering is unsafe."""

    token = _state_token(connection)
    key = id(connection)
    cached = _state_cache.get(key)
    if cached is not None and cached[0] is connection and cached[1] == token:
        _state_cache.move_to_end(key)
        return
    errors = persistence_timestamp_errors(connection)
    if errors:
        raise ValueError(
            "persisted timestamp chronology is unsafe: "
            + "; ".join(errors)
        )
    _cache_state(connection, token)


def mark_canonical_persistence_state(connection: sqlite3.Connection) -> None:
    """Cache a successful repository write as preserving canonical chronology."""

    _cache_state(connection, _state_token(connection))


def canonical_persistence_write(
    function: Callable[P, R],
) -> Callable[P, R]:
    """Guard a repository mutation against unsafe legacy timestamp state."""

    @wraps(function)
    def guarded(connection: sqlite3.Connection, *args: Any, **kwargs: Any) -> R:
        require_canonical_persistence_state(connection)
        result = function(connection, *args, **kwargs)
        mark_canonical_persistence_state(connection)
        return result

    setattr(guarded, "canonical_persistence_preflight", True)
    return guarded  # type: ignore[return-value]
