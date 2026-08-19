"""Resumable ohsome extraction and offline OpenStreetMap GeoJSON import."""

from __future__ import annotations

import email.utils
import hashlib
import json
import math
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .adapters import ImportResult
from .models import (
    Building,
    Campus,
    EntityKind,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
    Project,
)
from .osm import (
    OSM_ATTRIBUTION,
    OSM_LICENSE,
    _explicit_operating_model,
    _explicit_workloads,
    extract_center,
    infer_entity_kind,
    infer_lifecycle,
    is_explicit_data_center,
)
from .repository import (
    add_building,
    add_campus,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_operating_model,
    add_project,
    add_snapshot,
    add_workload,
    stable_id,
)


OHSOME_ENDPOINT = "https://api.ohsome.org/v1/elements/geometry"
OHSOME_COPYRIGHT_URL = "https://ohsome.org/copyrights"
DEFAULT_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)
DATA_CENTER_VALUES = ("data_center", "data_centre", "datacenter", "datacentre")
DIRECT_KEYS = (
    "telecom",
    "building",
    "man_made",
    "landuse",
    "site",
    "amenity",
    "industrial",
)
DEVELOPMENT_PREFIXES = ("construction", "proposed")
MAX_TARGET_BATCH_SIZE = 100


def build_data_center_filter() -> str:
    """Return the explicit, auditable tag filter used for every shard request."""
    keys = [*DIRECT_KEYS, *DEVELOPMENT_PREFIXES]
    keys.extend(
        f"{prefix}:{key}"
        for prefix in DEVELOPMENT_PREFIXES
        for key in DIRECT_KEYS
    )
    # Equality terms are intentionally expanded.  The live ohsome parser
    # rejects ``key in (...)`` when none of the listed key/value pairs exists
    # in the current OSHDB tag dictionary, while equality expressions remain
    # valid and preserve future/rare combinations.
    return "(" + " or ".join(
        f"{key}={value}" for key in keys for value in DATA_CENTER_VALUES
    ) + ")"


DATA_CENTER_FILTER = build_data_center_filter()


@dataclass(frozen=True, slots=True)
class BoundingBox:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        values = (self.west, self.south, self.east, self.north)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("bounding-box coordinates must be finite")
        if not -180 <= self.west < self.east <= 180:
            raise ValueError("bounding-box longitude must satisfy -180 <= west < east <= 180")
        if not -90 <= self.south < self.north <= 90:
            raise ValueError("bounding-box latitude must satisfy -90 <= south < north <= 90")

    def api_value(self) -> str:
        return ",".join(_format_coordinate(value) for value in (
            self.west,
            self.south,
            self.east,
            self.north,
        ))

    def split(self) -> tuple["BoundingBox", ...]:
        middle_longitude = (self.west + self.east) / 2
        middle_latitude = (self.south + self.north) / 2
        return (
            BoundingBox(self.west, self.south, middle_longitude, middle_latitude),
            BoundingBox(middle_longitude, self.south, self.east, middle_latitude),
            BoundingBox(self.west, middle_latitude, middle_longitude, self.north),
            BoundingBox(middle_longitude, middle_latitude, self.east, self.north),
        )

    def can_split(self, minimum_span: float) -> bool:
        return (
            self.east - self.west > minimum_span
            and self.north - self.south > minimum_span
        )


def _format_coordinate(value: float) -> str:
    rendered = f"{value:.8f}".rstrip("0").rstrip(".")
    return "0" if rendered == "-0" else rendered


def initial_grid(bounds: BoundingBox, cell_degrees: float) -> list[tuple[str, BoundingBox]]:
    if not math.isfinite(cell_degrees) or cell_degrees <= 0:
        raise ValueError("cell_degrees must be positive")
    cells: list[tuple[str, BoundingBox]] = []
    row = 0
    south = bounds.south
    while south < bounds.north:
        north = min(bounds.north, south + cell_degrees)
        column = 0
        west = bounds.west
        while west < bounds.east:
            east = min(bounds.east, west + cell_degrees)
            cells.append((f"g{row:03d}_{column:03d}", BoundingBox(west, south, east, north)))
            west = east
            column += 1
        south = north
        row += 1
    return cells


class FetchFailure(Exception):
    def __init__(
        self,
        message: str,
        *,
        splittable: bool = False,
        transient: bool = False,
    ) -> None:
        super().__init__(message)
        self.splittable = splittable
        self.transient = transient


class OhsomeFetcher:
    """Fetch API shards serially, checkpointing each completed request."""

    def __init__(
        self,
        *,
        endpoint: str = OHSOME_ENDPOINT,
        user_agent: str = DEFAULT_USER_AGENT,
        request_interval: float = 1.0,
        request_timeout: float = 120.0,
        max_retries: int = 3,
        max_response_bytes: int = 50_000_000,
        max_features: int = 25_000,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("ohsome endpoint must use HTTPS")
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if request_interval < 0 or request_timeout <= 0 or max_retries < 0:
            raise ValueError("invalid request timing or retry configuration")
        if max_response_bytes <= 0 or max_features <= 0:
            raise ValueError("response limits must be positive")
        self.endpoint = endpoint
        self.user_agent = user_agent
        self.request_interval = request_interval
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.max_response_bytes = max_response_bytes
        self.max_features = max_features
        self.opener = opener
        self.sleeper = sleeper
        self.monotonic = monotonic
        self._last_request_at: float | None = None

    def fetch(
        self,
        output_directory: str | Path,
        *,
        snapshot_time: str,
        bounds: BoundingBox = BoundingBox(-180, -90, 180, 90),
        cell_degrees: float = 20.0,
        minimum_span: float = 0.25,
        max_depth: int = 8,
        max_requests: int | None = None,
        target_bboxes: str | Path | None = None,
        target_bboxes_sha256: str | None = None,
        target_batch_size: int = 25,
        max_batch_span_degrees: float = 20.0,
        retry_failed: bool = False,
        transient_failure_limit: int = 3,
    ) -> dict[str, Any]:
        if not snapshot_time.strip() or "," in snapshot_time:
            raise ValueError("snapshot_time must be one non-empty ohsome timestamp")
        if minimum_span <= 0 or max_depth < 0:
            raise ValueError("invalid split configuration")
        if target_bboxes is None and target_bboxes_sha256 is not None:
            raise ValueError("target_bboxes_sha256 requires target_bboxes")
        if (
            isinstance(target_batch_size, bool)
            or not isinstance(target_batch_size, int)
            or not 1 <= target_batch_size <= MAX_TARGET_BATCH_SIZE
        ):
            raise ValueError(
                f"target_batch_size must be between 1 and {MAX_TARGET_BATCH_SIZE}"
            )
        if (
            isinstance(max_batch_span_degrees, bool)
            or not isinstance(max_batch_span_degrees, (int, float))
            or not math.isfinite(max_batch_span_degrees)
            or not 0 < max_batch_span_degrees <= 180
        ):
            raise ValueError("max_batch_span_degrees must be in (0, 180]")
        if (
            isinstance(transient_failure_limit, bool)
            or not isinstance(transient_failure_limit, int)
            or transient_failure_limit <= 0
        ):
            raise ValueError("transient_failure_limit must be a positive integer")

        target_input: dict[str, Any] | None = None
        if target_bboxes is not None:
            target_input = _read_target_bboxes(
                Path(target_bboxes), expected_sha256=target_bboxes_sha256
            )
            for target in target_input["targets"]:
                target_bounds = BoundingBox(*target["bbox"])
                if (
                    target_bounds.east - target_bounds.west > max_batch_span_degrees
                    or target_bounds.north - target_bounds.south > max_batch_span_degrees
                ):
                    raise ValueError(
                        f"target bbox {target['id']} exceeds max_batch_span_degrees"
                    )
        output_path = Path(output_directory)
        shard_path = output_path / "shards"
        shard_path.mkdir(parents=True, exist_ok=True)
        manifest_path = output_path / "manifest.json"
        if target_input is None:
            config = {
                "endpoint": self.endpoint,
                "filter": DATA_CENTER_FILTER,
                "time": snapshot_time,
                "properties": "tags,metadata",
                "clipGeometry": "false",
                "bounds": [bounds.west, bounds.south, bounds.east, bounds.north],
                "cell_degrees": cell_degrees,
                "minimum_span": minimum_span,
                "max_depth": max_depth,
            }
            manifest = self._load_or_create_manifest(
                manifest_path, config, bounds, cell_degrees
            )
        else:
            config = {
                "endpoint": self.endpoint,
                "filter": DATA_CENTER_FILTER,
                "time": snapshot_time,
                "properties": "tags,metadata",
                "clipGeometry": "false",
                "mode": "taginfo_target_bboxes",
                "minimum_span": minimum_span,
                "max_depth": max_depth,
                "target_batch_size": target_batch_size,
                "max_batch_span_degrees": max_batch_span_degrees,
                "target_bboxes": {
                    "schema_version": target_input["schema_version"],
                    "sha256": target_input["sha256"],
                    "bytes": len(target_input["raw"]),
                    "bbox_count": len(target_input["targets"]),
                },
            }
            manifest = self._load_or_create_target_manifest(
                output_path,
                manifest_path,
                config,
                target_input,
                target_batch_size=target_batch_size,
                max_batch_span_degrees=max_batch_span_degrees,
            )
        retried_task_ids: list[str] = []
        if retry_failed:
            retried_at = _utc_now()
            for task_id, task in manifest["tasks"].items():
                if task["state"] != "failed":
                    continue
                history = task.setdefault("failure_history", [])
                if not isinstance(history, list):
                    raise ValueError(f"failed task {task_id} has invalid failure history")
                history.append(
                    {
                        "error": task.get("error"),
                        "attempts_before_retry": task.get("attempts"),
                        "retried_at": retried_at,
                    }
                )
                task["state"] = "pending"
                task["error"] = None
                retried_task_ids.append(task_id)
            if retried_task_ids:
                manifest.setdefault("retry_events", []).append(
                    {
                        "retried_at": retried_at,
                        "task_ids": retried_task_ids,
                    }
                )
                _write_manifest(manifest_path, manifest)
        requests_made = 0
        consecutive_transient_failures = 0
        stop_reason = "complete"
        run_started_at = _utc_now()

        while True:
            pending = next(
                (
                    (task_id, task)
                    for task_id, task in manifest["tasks"].items()
                    if task["state"] == "pending"
                ),
                None,
            )
            if pending is None:
                break
            if max_requests is not None and requests_made >= max_requests:
                stop_reason = "max_requests_checkpoint"
                break
            task_id, task = pending
            request_boxes = _task_request_boxes(task)
            if target_input is not None:
                envelope = _request_envelope(request_boxes)
                if (
                    envelope[2] - envelope[0] > max_batch_span_degrees + 1e-9
                    or envelope[3] - envelope[1] > max_batch_span_degrees + 1e-9
                ):
                    raise ValueError(
                        f"task {task_id} request envelope exceeds max_batch_span_degrees"
                    )
            try:
                payload, request_count = self._request_boxes(
                    request_boxes, snapshot_time
                )
                requests_made += request_count
            except FetchFailure as error:
                requests_made += int(getattr(error, "request_count", 0))
                task["attempts"] += int(getattr(error, "request_count", 0))
                task["error"] = str(error)
                children = (
                    self._split_failed_task(
                        task_id,
                        task,
                        request_boxes,
                        minimum_span=minimum_span,
                        max_depth=max_depth,
                        targeted=target_input is not None,
                    )
                    if error.splittable
                    else []
                )
                if children:
                    task["state"] = "split"
                    task["children"] = [child_id for child_id, _ in children]
                    for child_id, child_task in children:
                        if child_id in manifest["tasks"]:
                            raise ValueError(f"split would overwrite task {child_id}")
                        manifest["tasks"][child_id] = child_task
                else:
                    task["state"] = "failed"
                _write_manifest(manifest_path, manifest)
                if error.transient and not children:
                    consecutive_transient_failures += 1
                    if consecutive_transient_failures >= transient_failure_limit:
                        stop_reason = "transient_service_circuit_break"
                        break
                else:
                    consecutive_transient_failures = 0
                continue

            consecutive_transient_failures = 0
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            destination = shard_path / f"{task_id}.geojson"
            temporary = destination.with_suffix(".geojson.tmp")
            temporary.write_bytes(body)
            temporary.replace(destination)
            task.update(
                {
                    "state": "completed",
                    "file": str(destination.relative_to(output_path)),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "feature_count": len(payload["features"]),
                    "attempts": task["attempts"] + request_count,
                    "error": None,
                    "fetched_at": _utc_now(),
                    "request_url": (payload.get("metadata") or {}).get("requestUrl"),
                    "request_bboxes_parameter": _bboxes_api_value(request_boxes),
                    "request_envelope": _request_envelope(request_boxes),
                    "target_ids": [
                        box["id"] for box in request_boxes if box["id"] is not None
                    ],
                }
            )
            _write_manifest(manifest_path, manifest)

        manifest["summary"] = {
            state: sum(task["state"] == state for task in manifest["tasks"].values())
            for state in ("pending", "completed", "split", "failed")
        }
        manifest["last_run"] = {
            "started_at": run_started_at,
            "finished_at": _utc_now(),
            "requests_made": requests_made,
            "retried_failed_task_ids": retried_task_ids,
            "stop_reason": stop_reason,
            "transient_failure_limit": transient_failure_limit,
        }
        _write_manifest(manifest_path, manifest)
        return manifest

    def _load_or_create_target_manifest(
        self,
        output_path: Path,
        manifest_path: Path,
        config: dict[str, Any],
        target_input: dict[str, Any],
        *,
        target_batch_size: int,
        max_batch_span_degrees: float,
    ) -> dict[str, Any]:
        input_record = {
            "path": "inputs/target_bboxes.json",
            "sha256": target_input["sha256"],
            "bytes": len(target_input["raw"]),
        }
        root_batches = _spatial_target_batches(
            target_input["targets"],
            batch_size=target_batch_size,
            max_span=max_batch_span_degrees,
        )
        root_task_ids = [f"b{index:05d}" for index in range(len(root_batches))]
        if manifest_path.exists():
            manifest = _load_json_object(manifest_path.read_bytes(), "ohsome manifest")
            if manifest.get("config") != config:
                raise ValueError("existing manifest configuration does not match this fetch")
            if manifest.get("config_sha256") != _json_sha256(config):
                raise ValueError("existing manifest config SHA256 does not match its config")
            inputs = manifest.get("inputs")
            if (
                not isinstance(inputs, dict)
                or inputs.get("target_bboxes") != input_record
            ):
                raise ValueError("existing manifest target input record does not match this fetch")
            if manifest.get("root_tasks") != root_task_ids:
                raise ValueError("existing manifest root task plan does not match this fetch")
            _verify_target_input_copy(output_path, input_record, target_input["raw"])
            _validate_manifest_task_graph(manifest.get("tasks"))
            _validate_root_target_plan(manifest, root_batches)
            _validate_completed_resume_shards(output_path, manifest["tasks"])
            return manifest

        input_path = output_path / input_record["path"]
        input_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_input = input_path.with_suffix(".json.tmp")
        temporary_input.write_bytes(target_input["raw"])
        temporary_input.replace(input_path)
        tasks = {
            task_id: _new_target_task(batch, depth=0, parent=None)
            for task_id, batch in zip(root_task_ids, root_batches, strict=True)
        }
        manifest = {
            "schema_version": 2,
            "created_at": _utc_now(),
            "config": config,
            "config_sha256": _json_sha256(config),
            "inputs": {"target_bboxes": input_record},
            "root_tasks": root_task_ids,
            "tasks": tasks,
        }
        _write_manifest(manifest_path, manifest)
        return manifest

    def _load_or_create_manifest(
        self,
        manifest_path: Path,
        config: dict[str, Any],
        bounds: BoundingBox,
        cell_degrees: float,
    ) -> dict[str, Any]:
        if manifest_path.exists():
            manifest = _load_json_object(manifest_path.read_bytes(), "ohsome manifest")
            if manifest.get("config") != config:
                raise ValueError("existing manifest configuration does not match this fetch")
            _validate_manifest_task_graph(manifest.get("tasks"))
            _validate_completed_resume_shards(manifest_path.parent, manifest["tasks"])
            return manifest
        manifest = {
            "schema_version": 1,
            "created_at": _utc_now(),
            "config": config,
            "tasks": {
                task_id: _new_task(bbox, depth=0, parent=None)
                for task_id, bbox in initial_grid(bounds, cell_degrees)
            },
        }
        _write_manifest(manifest_path, manifest)
        return manifest

    def _split_failed_task(
        self,
        task_id: str,
        task: dict[str, Any],
        request_boxes: list[dict[str, Any]],
        *,
        minimum_span: float,
        max_depth: int,
        targeted: bool,
    ) -> list[tuple[str, dict[str, Any]]]:
        if targeted and len(request_boxes) > 1:
            midpoint = (len(request_boxes) + 1) // 2
            halves = (request_boxes[:midpoint], request_boxes[midpoint:])
            return [
                (
                    f"{task_id}s{index}",
                    _new_target_task(
                        half,
                        depth=int(task["depth"]),
                        parent=task_id,
                    ),
                )
                for index, half in enumerate(halves)
            ]

        bbox = BoundingBox(*request_boxes[0]["bbox"])
        if task["depth"] >= max_depth or not bbox.can_split(minimum_span):
            return []
        if targeted:
            source_target_id = str(
                request_boxes[0].get("source_target_id") or request_boxes[0]["id"]
            )
            return [
                (
                    f"{task_id}q{index}",
                    _new_target_task(
                        [
                            {
                                "id": f"{request_boxes[0]['id']}q{index}",
                                "bbox": [child.west, child.south, child.east, child.north],
                                "source_target_id": source_target_id,
                            }
                        ],
                        depth=int(task["depth"]) + 1,
                        parent=task_id,
                    ),
                )
                for index, child in enumerate(bbox.split())
            ]
        return [
            (
                f"{task_id}q{index}",
                _new_task(child, depth=int(task["depth"]) + 1, parent=task_id),
            )
            for index, child in enumerate(bbox.split())
        ]

    def _request_shard(
        self, bbox: BoundingBox, snapshot_time: str
    ) -> tuple[dict[str, Any], int]:
        return self._request_boxes(
            [{"id": None, "bbox": [bbox.west, bbox.south, bbox.east, bbox.north]}],
            snapshot_time,
        )

    def _request_boxes(
        self, request_boxes: list[dict[str, Any]], snapshot_time: str
    ) -> tuple[dict[str, Any], int]:
        form = urllib.parse.urlencode(
            {
                "bboxes": _bboxes_api_value(request_boxes),
                "time": snapshot_time,
                "filter": DATA_CENTER_FILTER,
                "properties": "tags,metadata",
                "clipGeometry": "false",
            }
        ).encode("utf-8")
        request_count = 0
        last_error: FetchFailure | None = None
        for attempt in range(self.max_retries + 1):
            self._wait_for_request_slot()
            request = urllib.request.Request(
                self.endpoint,
                data=form,
                headers={
                    "Accept": "application/geo+json, application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self.user_agent,
                },
                method="POST",
            )
            request_count += 1
            self._last_request_at = self.monotonic()
            try:
                with self.opener(request, timeout=self.request_timeout) as response:
                    raw = response.read(self.max_response_bytes + 1)
                if len(raw) > self.max_response_bytes:
                    failure = FetchFailure(
                        f"response exceeded {self.max_response_bytes} bytes",
                        splittable=True,
                    )
                    failure.request_count = request_count
                    raise failure
                payload = json.loads(raw)
                if payload.get("type") != "FeatureCollection" or not isinstance(
                    payload.get("features"), list
                ):
                    raise FetchFailure("ohsome response was not a GeoJSON FeatureCollection")
                if len(payload["features"]) > self.max_features:
                    failure = FetchFailure(
                        f"response contained {len(payload['features'])} features; "
                        f"limit is {self.max_features}",
                        splittable=True,
                    )
                    failure.request_count = request_count
                    raise failure
                return payload, request_count
            except urllib.error.HTTPError as error:
                try:
                    body = error.read(4096).decode("utf-8", errors="replace")
                finally:
                    error.close()
                splittable = error.code in {408, 413, 504} or (
                    error.code >= 500 and "timeout" in body.lower()
                )
                last_error = FetchFailure(
                    f"ohsome HTTP {error.code}: {body[:300].strip()}",
                    splittable=splittable,
                    transient=error.code in {429, 500, 502, 503},
                )
                if error.code == 413:
                    break
                if error.code not in {408, 429, 500, 502, 503, 504} or attempt == self.max_retries:
                    break
                retry_after = _retry_after_seconds(error.headers.get("Retry-After"))
                self._sleep(retry_after if retry_after is not None else min(2**attempt, 30))
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = FetchFailure(f"ohsome request timed out or failed: {error}", splittable=True)
                if attempt == self.max_retries:
                    break
                self._sleep(min(2**attempt, 30))
            except json.JSONDecodeError as error:
                last_error = FetchFailure(f"ohsome returned invalid JSON: {error}")
                if attempt == self.max_retries:
                    break
                self._sleep(min(2**attempt, 30))
            except FetchFailure:
                raise
        assert last_error is not None
        last_error.request_count = request_count
        raise last_error

    def _wait_for_request_slot(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self.request_interval - (self.monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)

    def _sleep(self, duration: float) -> None:
        """Honor long server delays without one opaque blocking sleep."""
        remaining = duration
        while remaining > 0:
            interval = min(remaining, 60.0)
            self.sleeper(interval)
            remaining -= interval


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - datetime.now(UTC)).total_seconds())


def _new_task(bbox: BoundingBox, *, depth: int, parent: str | None) -> dict[str, Any]:
    return {
        "bbox": [bbox.west, bbox.south, bbox.east, bbox.north],
        "depth": depth,
        "parent": parent,
        "state": "pending",
        "attempts": 0,
        "error": None,
        "file": None,
        "sha256": None,
        "feature_count": None,
    }


def _new_target_task(
    boxes: list[dict[str, Any]], *, depth: int, parent: str | None
) -> dict[str, Any]:
    normalized = [
        {
            "id": str(box["id"]),
            "bbox": list(box["bbox"]),
            "source_target_id": str(box.get("source_target_id") or box["id"]),
        }
        for box in boxes
    ]
    _validate_named_boxes(normalized)
    return {
        "bboxes": normalized,
        "request_envelope": _request_envelope(normalized),
        "target_ids": [box["id"] for box in normalized],
        "depth": depth,
        "parent": parent,
        "state": "pending",
        "attempts": 0,
        "error": None,
        "file": None,
        "sha256": None,
        "feature_count": None,
    }


def _validate_named_boxes(boxes: Any) -> list[dict[str, Any]]:
    if not isinstance(boxes, list) or not boxes:
        raise ValueError("targeted ohsome task must contain a non-empty bboxes list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for box in boxes:
        if not isinstance(box, dict):
            raise ValueError("targeted ohsome task bboxes must be objects")
        identifier = box.get("id")
        if not isinstance(identifier, str) or not _SAFE_TASK_ID.fullmatch(identifier):
            raise ValueError(f"unsafe targeted ohsome bbox id: {identifier!r}")
        if identifier in seen_ids:
            raise ValueError(f"duplicate targeted ohsome bbox id: {identifier}")
        seen_ids.add(identifier)
        coordinates = box.get("bbox")
        if not isinstance(coordinates, list) or len(coordinates) != 4:
            raise ValueError(f"targeted ohsome bbox {identifier} has invalid coordinates")
        try:
            bounds = BoundingBox(*coordinates)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"targeted ohsome bbox {identifier} has invalid coordinates: {error}"
            ) from error
        source_target_id = box.get("source_target_id", identifier)
        if (
            not isinstance(source_target_id, str)
            or not _SAFE_TASK_ID.fullmatch(source_target_id)
        ):
            raise ValueError(
                f"unsafe source target id for targeted ohsome bbox {identifier}"
            )
        normalized.append(
            {
                "id": identifier,
                "bbox": [bounds.west, bounds.south, bounds.east, bounds.north],
                "source_target_id": source_target_id,
            }
        )
    return normalized


def _task_request_boxes(task: dict[str, Any]) -> list[dict[str, Any]]:
    if "bboxes" in task:
        boxes = _validate_named_boxes(task["bboxes"])
        target_ids = task.get("target_ids")
        if target_ids != [box["id"] for box in boxes]:
            raise ValueError("targeted ohsome task target_ids do not match its bboxes")
        envelope = _request_envelope(boxes)
        if task.get("request_envelope") != envelope:
            raise ValueError("targeted ohsome task request_envelope does not match its bboxes")
        return boxes
    coordinates = task.get("bbox")
    if not isinstance(coordinates, list) or len(coordinates) != 4:
        raise ValueError("ohsome task has neither a valid bbox nor bboxes")
    bounds = BoundingBox(*coordinates)
    return [
        {
            "id": None,
            "bbox": [bounds.west, bounds.south, bounds.east, bounds.north],
            "source_target_id": None,
        }
    ]


def _bboxes_api_value(boxes: list[dict[str, Any]]) -> str:
    if not boxes:
        raise ValueError("cannot build an ohsome request without bboxes")
    identifiers = [box.get("id") for box in boxes]
    if any(identifier is None for identifier in identifiers):
        if len(boxes) != 1 or identifiers[0] is not None:
            raise ValueError("unnamed ohsome bboxes can only be requested singly")
        return BoundingBox(*boxes[0]["bbox"]).api_value()
    _validate_named_boxes(boxes)
    return "|".join(
        f"{box['id']}:{BoundingBox(*box['bbox']).api_value()}" for box in boxes
    )


def _request_envelope(boxes: list[dict[str, Any]]) -> list[float]:
    if not boxes:
        raise ValueError("cannot compute an empty bbox envelope")
    bounds = [BoundingBox(*box["bbox"]) for box in boxes]
    return [
        min(box.west for box in bounds),
        min(box.south for box in bounds),
        max(box.east for box in bounds),
        max(box.north for box in bounds),
    ]


def _spatial_target_batches(
    targets: list[dict[str, Any]], *, batch_size: int, max_span: float
) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    epsilon = 1e-9
    for target in targets:
        bounds = BoundingBox(*target["bbox"])
        x_index = math.floor((bounds.west + 180) / max_span)
        y_index = math.floor((bounds.south + 90) / max_span)
        tile_west = -180 + x_index * max_span
        tile_south = -90 + y_index * max_span
        fits_aligned_tile = (
            bounds.east <= tile_west + max_span + epsilon
            and bounds.north <= tile_south + max_span + epsilon
        )
        group_id = (
            f"tile:{y_index:05d}:{x_index:05d}"
            if fits_aligned_tile
            else f"singleton:{target['id']}"
        )
        groups.setdefault(group_id, []).append(
            {
                "id": target["id"],
                "bbox": list(target["bbox"]),
                "source_target_id": target["id"],
            }
        )

    batches: list[list[dict[str, Any]]] = []
    for group_id in sorted(groups):
        group = sorted(groups[group_id], key=lambda item: item["id"])
        for start in range(0, len(group), batch_size):
            batch = group[start : start + batch_size]
            envelope = _request_envelope(batch)
            if (
                envelope[2] - envelope[0] > max_span + epsilon
                or envelope[3] - envelope[1] > max_span + epsilon
            ):
                raise ValueError("spatial target batch exceeds its maximum request envelope")
            batches.append(batch)
    return batches


def _read_target_bboxes(
    path: Path, *, expected_sha256: str | None
) -> dict[str, Any]:
    raw = path.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_sha256
        ):
            raise ValueError("target_bboxes_sha256 must be a 64-character hexadecimal hash")
        if actual_sha256 != expected_sha256.lower():
            raise ValueError("target_bboxes SHA256 does not match the expected hash")
    document = _load_json_object(raw, "target_bboxes.json")
    if document.get("schema_version") != 1:
        raise ValueError("target_bboxes.json must use schema_version 1")
    targeting_signal = document.get("targeting_signal")
    if not isinstance(targeting_signal, str) or not targeting_signal.strip():
        raise ValueError("target_bboxes.json has no targeting_signal")
    cell_degrees = document.get("cell_degrees")
    if (
        isinstance(cell_degrees, bool)
        or not isinstance(cell_degrees, int)
        or cell_degrees <= 0
        or 180 % cell_degrees
        or 360 % cell_degrees
    ):
        raise ValueError("target_bboxes.json has an invalid cell_degrees")
    entries = document.get("bboxes")
    if not isinstance(entries, list) or not entries:
        raise ValueError("target_bboxes.json must contain a non-empty bboxes list")
    bbox_count = document.get("bbox_count")
    if isinstance(bbox_count, bool) or not isinstance(bbox_count, int):
        raise ValueError("target_bboxes.json has an invalid bbox_count")
    if bbox_count != len(entries):
        raise ValueError("target_bboxes.json bbox_count does not match bboxes")

    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_bboxes: set[tuple[float, float, float, float]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("target_bboxes.json contains a non-object bbox")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not _SAFE_TASK_ID.fullmatch(identifier):
            raise ValueError(f"unsafe target bbox id: {identifier!r}")
        if identifier in seen_ids:
            raise ValueError(f"duplicate target bbox id: {identifier}")
        seen_ids.add(identifier)
        coordinates = entry.get("bbox")
        if not isinstance(coordinates, list) or len(coordinates) != 4:
            raise ValueError(f"target bbox {identifier} has invalid coordinates")
        try:
            bounds = BoundingBox(*coordinates)
        except (TypeError, ValueError) as error:
            raise ValueError(f"target bbox {identifier} is invalid: {error}") from error
        bbox_tuple = (bounds.west, bounds.south, bounds.east, bounds.north)
        if (
            bounds.east - bounds.west != cell_degrees
            or bounds.north - bounds.south != cell_degrees
            or (bounds.west + 180) % cell_degrees
            or (bounds.south + 90) % cell_degrees
        ):
            raise ValueError(
                f"target bbox {identifier} is not aligned to cell_degrees"
            )
        if bbox_tuple in seen_bboxes:
            raise ValueError(f"duplicate target bbox coordinates for {identifier}")
        seen_bboxes.add(bbox_tuple)
        if any(
            entry.get(key) != value
            for key, value in zip(
                ("west", "south", "east", "north"), bbox_tuple, strict=True
            )
        ):
            raise ValueError(f"target bbox {identifier} coordinate fields do not match bbox")
        expected_api = f"{identifier}:{bounds.api_value()}"
        if entry.get("ohsome_bbox") != expected_api:
            raise ValueError(f"target bbox {identifier} has an invalid ohsome_bbox")
        if entry.get("targeting_signal") != targeting_signal:
            raise ValueError(f"target bbox {identifier} has a mismatched targeting_signal")
        occupied_count = entry.get("occupied_1deg_signal_cells")
        if (
            isinstance(occupied_count, bool)
            or not isinstance(occupied_count, int)
            or occupied_count <= 0
            or occupied_count > cell_degrees * cell_degrees
        ):
            raise ValueError(
                f"target bbox {identifier} has invalid occupied_1deg_signal_cells"
            )
        signals = entry.get("tag_signals")
        if not isinstance(signals, list) or not signals:
            raise ValueError(f"target bbox {identifier} has no tag_signals")
        seen_signals: set[tuple[str, str, str]] = set()
        for signal in signals:
            if not isinstance(signal, dict):
                raise ValueError(f"target bbox {identifier} contains a non-object tag signal")
            triple = (signal.get("key"), signal.get("value"), signal.get("element_type"))
            if (
                not all(isinstance(value, str) and value for value in triple)
                or triple[2] not in {"nodes", "ways"}
            ):
                raise ValueError(f"target bbox {identifier} contains an invalid tag signal")
            if triple in seen_signals:
                raise ValueError(f"target bbox {identifier} contains a duplicate tag signal")
            seen_signals.add(triple)
        targets.append({"id": identifier, "bbox": list(bbox_tuple)})

    expected_parameter = "|".join(
        f"{target['id']}:{BoundingBox(*target['bbox']).api_value()}"
        for target in targets
    )
    if document.get("ohsome_bboxes_parameter") != expected_parameter:
        raise ValueError("target_bboxes.json ohsome_bboxes_parameter does not match bboxes")
    return {
        "schema_version": 1,
        "sha256": actual_sha256,
        "raw": raw,
        "targets": targets,
    }


def _load_json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return document


def _json_sha256(document: Any) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_target_input_copy(
    output_path: Path, input_record: dict[str, Any], expected_raw: bytes
) -> None:
    if input_record.get("path") != "inputs/target_bboxes.json":
        raise ValueError("target input record has an unsafe path")
    root = output_path.resolve(strict=True)
    saved_path = output_path / input_record["path"]
    try:
        resolved = saved_path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError("saved target_bboxes input is missing") from error
    expected_path = root / "inputs" / "target_bboxes.json"
    if resolved != expected_path or not resolved.is_relative_to(root):
        raise ValueError("saved target_bboxes input path escapes output directory")
    saved_raw = resolved.read_bytes()
    if len(saved_raw) != input_record.get("bytes"):
        raise ValueError("saved target_bboxes byte count does not match manifest")
    if hashlib.sha256(saved_raw).hexdigest() != input_record.get("sha256"):
        raise ValueError("saved target_bboxes SHA256 does not match manifest")
    if saved_raw != expected_raw:
        raise ValueError("saved target_bboxes input does not match this fetch")


def _validate_root_target_plan(
    manifest: dict[str, Any], root_batches: list[list[dict[str, Any]]]
) -> None:
    tasks = manifest["tasks"]
    root_ids = manifest.get("root_tasks")
    if (
        not isinstance(root_ids, list)
        or len(root_ids) != len(root_batches)
        or any(
            not isinstance(task_id, str) or not _SAFE_TASK_ID.fullmatch(task_id)
            for task_id in root_ids
        )
        or len(set(root_ids)) != len(root_ids)
    ):
        raise ValueError("targeted ohsome manifest has an invalid root task plan")
    actual_roots = sorted(
        task_id for task_id, task in tasks.items() if task.get("parent") is None
    )
    if sorted(root_ids) != actual_roots:
        raise ValueError("targeted ohsome manifest contains undeclared root tasks")
    for task_id, expected in zip(root_ids, root_batches, strict=True):
        if _task_request_boxes(tasks[task_id]) != _validate_named_boxes(expected):
            raise ValueError(f"targeted ohsome root task {task_id} changed its targets")


def _validate_completed_resume_shards(
    output_path: Path, tasks: dict[str, Any]
) -> None:
    root = output_path.resolve(strict=True)
    for task_id, task in tasks.items():
        if task.get("state") != "completed":
            continue
        declared_file = task.get("file")
        if declared_file != f"shards/{task_id}.geojson":
            raise ValueError(f"completed ohsome task {task_id} has an invalid shard path")
        try:
            candidate = (output_path / declared_file).resolve(strict=True)
        except FileNotFoundError as error:
            raise ValueError(f"completed ohsome task {task_id} shard is missing") from error
        if not candidate.is_relative_to(root):
            raise ValueError(f"completed ohsome task {task_id} shard escapes output directory")
        raw = candidate.read_bytes()
        if hashlib.sha256(raw).hexdigest() != task.get("sha256"):
            raise ValueError(f"completed ohsome task {task_id} shard SHA256 does not match")
        try:
            document = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"completed ohsome task {task_id} shard is invalid JSON") from error
        if (
            not isinstance(document, dict)
            or document.get("type") != "FeatureCollection"
            or not isinstance(document.get("features"), list)
        ):
            raise ValueError(f"completed ohsome task {task_id} shard is not GeoJSON")
        if len(document["features"]) != task.get("feature_count"):
            raise ValueError(f"completed ohsome task {task_id} feature_count does not match")


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _feature_identity(feature: dict[str, Any]) -> tuple[str, str] | None:
    properties = feature.get("properties") or {}
    osm_id = str(properties.get("@osmId") or "")
    osm_type = str(properties.get("@osmType") or "")
    if "/" in osm_id:
        osm_type, identifier = osm_id.split("/", 1)
    else:
        identifier = osm_id
    if osm_type not in {"node", "way", "relation"} or not identifier.isdigit():
        return None
    return osm_type, identifier


def _feature_rank(feature: dict[str, Any]) -> tuple[str, int, str]:
    properties = feature.get("properties") or {}
    return (
        str(properties.get("@snapshotTimestamp") or properties.get("@timestamp") or ""),
        int(properties.get("@version") or 0),
        json.dumps(feature, sort_keys=True, separators=(",", ":")),
    )


def _tag_properties(properties: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in properties.items()
        if not str(key).startswith("@")
    }


def _snapshot_time(document: dict[str, Any], properties: dict[str, Any], retrieved_at: str) -> str:
    if properties.get("@snapshotTimestamp"):
        return str(properties["@snapshotTimestamp"])
    request_url = str((document.get("metadata") or {}).get("requestUrl") or "")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(request_url).query)
    if query.get("time"):
        return query["time"][0]
    return str(properties.get("@timestamp") or retrieved_at)


@dataclass(frozen=True, slots=True)
class _ShardSpec:
    path: Path
    sha256: str | None = None
    feature_count: int | None = None


_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MANIFEST_STATES = {"pending", "completed", "split", "failed"}


def _validate_manifest_task_graph(tasks: Any) -> dict[str, tuple[str, ...]]:
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError("ohsome manifest must contain a non-empty tasks object")
    if any(not isinstance(task, dict) for task in tasks.values()):
        raise ValueError("ohsome manifest tasks must be objects")
    for task_id in tasks:
        if not isinstance(task_id, str) or not _SAFE_TASK_ID.fullmatch(task_id):
            raise ValueError(f"unsafe ohsome task id: {task_id!r}")

    unknown_states = {
        str(task.get("state"))
        for task in tasks.values()
        if task.get("state") not in _MANIFEST_STATES
    }
    if unknown_states:
        raise ValueError(
            "ohsome manifest contains unknown task state(s): "
            + ", ".join(sorted(unknown_states))
        )

    actual_children: dict[str, set[str]] = {task_id: set() for task_id in tasks}
    for task_id, task in tasks.items():
        parent = task.get("parent")
        if parent is None:
            continue
        if not isinstance(parent, str) or not _SAFE_TASK_ID.fullmatch(parent):
            raise ValueError(f"ohsome task {task_id} has an unsafe parent id")
        if parent not in tasks:
            raise ValueError(f"ohsome task {task_id} has an undeclared parent {parent}")
        actual_children[parent].add(task_id)

    child_plan: dict[str, tuple[str, ...]] = {}
    for task_id, task in tasks.items():
        children = actual_children[task_id]
        declared = task.get("children")
        if task.get("state") != "split":
            if declared is not None or children:
                raise ValueError(f"non-split ohsome task {task_id} declares or owns children")
            continue

        if declared is None:
            expected = tuple(f"{task_id}q{index}" for index in range(4))
            unexpected = children - set(expected)
            if unexpected:
                raise ValueError(
                    f"legacy split ohsome task {task_id} has undeclared children: "
                    + ", ".join(sorted(unexpected))
                )
            child_plan[task_id] = expected
            continue
        if not isinstance(declared, list) or len(declared) not in {2, 4}:
            raise ValueError(
                f"split ohsome task {task_id} must declare exactly 2 or 4 children"
            )
        if any(
            not isinstance(child_id, str) or not _SAFE_TASK_ID.fullmatch(child_id)
            for child_id in declared
        ):
            raise ValueError(f"split ohsome task {task_id} declares an unsafe child id")
        if len(set(declared)) != len(declared):
            raise ValueError(f"split ohsome task {task_id} declares duplicate children")
        if any(child_id not in tasks for child_id in declared):
            raise ValueError(f"split ohsome task {task_id} declares a missing child")
        if set(declared) != children:
            raise ValueError(
                f"split ohsome task {task_id} has undeclared or mis-parented children"
            )
        child_plan[task_id] = tuple(declared)

    colors: dict[str, int] = {}

    def visit(task_id: str) -> None:
        color = colors.get(task_id, 0)
        if color == 1:
            raise ValueError("ohsome manifest task graph contains a cycle")
        if color == 2:
            return
        colors[task_id] = 1
        for child_id in actual_children[task_id]:
            visit(child_id)
        colors[task_id] = 2

    for task_id in tasks:
        visit(task_id)

    _validate_declared_split_queries(tasks, child_plan)
    return child_plan


def _validate_declared_split_queries(
    tasks: dict[str, Any], child_plan: dict[str, tuple[str, ...]]
) -> None:
    for task_id, child_ids in child_plan.items():
        if not all(child_id in tasks for child_id in child_ids):
            continue
        parent = tasks[task_id]
        if "bbox" not in parent and "bboxes" not in parent:
            continue
        try:
            parent_boxes = _task_request_boxes(parent)
            child_boxes = [_task_request_boxes(tasks[child_id]) for child_id in child_ids]
        except ValueError:
            raise
        if len(child_ids) == 2:
            if len(parent_boxes) <= 1:
                raise ValueError(
                    f"two-child ohsome split {task_id} does not split a bbox batch"
                )
            flattened = [box for group in child_boxes for box in group]
            if flattened != parent_boxes or any(not group for group in child_boxes):
                raise ValueError(
                    f"two-child ohsome split {task_id} does not preserve its targets"
                )
            continue
        if len(parent_boxes) != 1 or any(len(group) != 1 for group in child_boxes):
            raise ValueError(
                f"four-child ohsome split {task_id} is not a singleton subdivision"
            )
        parent_bounds = BoundingBox(*parent_boxes[0]["bbox"])
        expected_bounds = [
            [child.west, child.south, child.east, child.north]
            for child in parent_bounds.split()
        ]
        if [group[0]["bbox"] for group in child_boxes] != expected_bounds:
            raise ValueError(
                f"four-child ohsome split {task_id} does not preserve its bbox"
            )
        parent_source = parent_boxes[0].get("source_target_id")
        if parent_source is not None and any(
            group[0].get("source_target_id") != parent_source for group in child_boxes
        ):
            raise ValueError(
                f"four-child ohsome split {task_id} changed its source target id"
            )


def _split_is_complete(
    task_id: str,
    tasks: dict[str, Any],
    child_plan: dict[str, tuple[str, ...]],
    memo: dict[str, bool],
) -> bool:
    if task_id in memo:
        return memo[task_id]
    child_ids = child_plan[task_id]
    if any(child_id not in tasks for child_id in child_ids):
        memo[task_id] = False
        return False
    complete = all(
        tasks[child_id].get("state") == "completed"
        or (
            tasks[child_id].get("state") == "split"
            and _split_is_complete(child_id, tasks, child_plan, memo)
        )
        for child_id in child_ids
    )
    memo[task_id] = complete
    return complete


def _manifest_shards(
    path: Path,
    *,
    allow_partial: bool,
) -> tuple[list[_ShardSpec], list[str]]:
    manifest_path = path / "manifest.json"
    manifest = _load_json_object(manifest_path.read_bytes(), "ohsome manifest")
    tasks = manifest.get("tasks")
    child_plan = _validate_manifest_task_graph(tasks)
    assert isinstance(tasks, dict)

    manifest_config = manifest.get("config")
    if isinstance(manifest_config, dict) and manifest_config.get("mode") == "taginfo_target_bboxes":
        config = manifest_config
        if manifest.get("schema_version") != 2:
            raise ValueError("targeted ohsome manifest must use schema_version 2")
        if manifest.get("config_sha256") != _json_sha256(config):
            raise ValueError("targeted ohsome manifest config SHA256 does not match")
        inputs = manifest.get("inputs")
        input_record = inputs.get("target_bboxes") if isinstance(inputs, dict) else None
        if not isinstance(input_record, dict):
            raise ValueError("targeted ohsome manifest has no target input record")
        if input_record.get("path") != "inputs/target_bboxes.json":
            raise ValueError("targeted ohsome manifest has an unsafe target input path")
        root = path.resolve(strict=True)
        input_path = path / input_record["path"]
        try:
            resolved_input = input_path.resolve(strict=True)
        except FileNotFoundError as error:
            raise ValueError("targeted ohsome input is missing") from error
        expected_input = root / "inputs" / "target_bboxes.json"
        if resolved_input != expected_input or not resolved_input.is_relative_to(root):
            raise ValueError("targeted ohsome input path escapes input directory")
        raw_input = resolved_input.read_bytes()
        if len(raw_input) != input_record.get("bytes"):
            raise ValueError("targeted ohsome input byte count does not match manifest")
        if hashlib.sha256(raw_input).hexdigest() != input_record.get("sha256"):
            raise ValueError("targeted ohsome input SHA256 does not match manifest")
        parsed_input = _read_target_bboxes(
            resolved_input, expected_sha256=input_record["sha256"]
        )
        target_config = config.get("target_bboxes")
        if not isinstance(target_config, dict) or target_config != {
            "schema_version": parsed_input["schema_version"],
            "sha256": parsed_input["sha256"],
            "bytes": len(parsed_input["raw"]),
            "bbox_count": len(parsed_input["targets"]),
        }:
            raise ValueError("targeted ohsome config does not match its saved input")
        batch_size = config.get("target_batch_size")
        max_span = config.get("max_batch_span_degrees")
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= MAX_TARGET_BATCH_SIZE
        ):
            raise ValueError("targeted ohsome manifest has an invalid target_batch_size")
        if (
            isinstance(max_span, bool)
            or not isinstance(max_span, (int, float))
            or not math.isfinite(max_span)
            or not 0 < max_span <= 180
        ):
            raise ValueError("targeted ohsome manifest has an invalid max batch span")
        root_batches = _spatial_target_batches(
            parsed_input["targets"],
            batch_size=batch_size,
            max_span=max_span,
        )
        _validate_root_target_plan(manifest, root_batches)
        for task_id, task in tasks.items():
            envelope = _request_envelope(_task_request_boxes(task))
            if (
                envelope[2] - envelope[0] > max_span + 1e-9
                or envelope[3] - envelope[1] > max_span + 1e-9
            ):
                raise ValueError(
                    f"targeted ohsome task {task_id} exceeds its request envelope limit"
                )
            if task.get("state") == "completed":
                expected_parameter = _bboxes_api_value(_task_request_boxes(task))
                if task.get("request_bboxes_parameter") != expected_parameter:
                    raise ValueError(
                        f"completed targeted ohsome task {task_id} changed its request bboxes"
                    )

    counts = {
        state: sum(task.get("state") == state for task in tasks.values())
        for state in _MANIFEST_STATES
    }
    memo: dict[str, bool] = {}
    incomplete_splits = sum(
        task.get("state") == "split"
        and not _split_is_complete(task_id, tasks, child_plan, memo)
        for task_id, task in tasks.items()
    )
    error_count = sum(bool(task.get("error")) for task in tasks.values())
    incomplete = counts["pending"] + counts["failed"] + incomplete_splits
    if incomplete and not allow_partial:
        raise ValueError(
            "ohsome manifest is incomplete: "
            f"pending={counts['pending']}, failed={counts['failed']}, "
            f"incomplete_split={incomplete_splits}, errors={error_count}"
        )

    warnings = []
    if incomplete:
        warnings.append(
            "partial ohsome manifest import: "
            f"completed={counts['completed']}, pending={counts['pending']}, "
            f"failed={counts['failed']}, incomplete_split={incomplete_splits}, "
            f"errors={error_count}"
        )

    root = path.resolve(strict=True)
    shards: list[_ShardSpec] = []
    seen_paths: set[Path] = set()
    for task_id, task in sorted(tasks.items()):
        if task.get("state") != "completed":
            continue
        if not isinstance(task_id, str) or not _SAFE_TASK_ID.fullmatch(task_id):
            raise ValueError(f"unsafe completed ohsome task id: {task_id!r}")
        declared_file = task.get("file")
        if not isinstance(declared_file, str) or not declared_file:
            raise ValueError(f"completed ohsome task {task_id} has no shard file")
        declared_path = Path(declared_file)
        if declared_path.is_absolute():
            raise ValueError(f"completed ohsome task {task_id} has an absolute shard path")
        candidate = (path / declared_path).resolve(strict=True)
        if not candidate.is_relative_to(root):
            raise ValueError(
                f"completed ohsome task {task_id} shard path escapes input directory"
            )
        expected = (root / "shards" / f"{task_id}.geojson").resolve(strict=False)
        if candidate != expected or declared_path.as_posix() != f"shards/{task_id}.geojson":
            raise ValueError(
                f"completed ohsome task {task_id} does not use its expected shard path"
            )
        if candidate in seen_paths:
            raise ValueError(f"multiple completed ohsome tasks reference {declared_file}")
        seen_paths.add(candidate)

        expected_hash = task.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_hash
        ):
            raise ValueError(f"completed ohsome task {task_id} has an invalid SHA256")
        expected_count = task.get("feature_count")
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count < 0
        ):
            raise ValueError(f"completed ohsome task {task_id} has an invalid feature_count")
        shards.append(_ShardSpec(candidate, expected_hash, expected_count))
    return shards, warnings


def _shard_specs(
    path: Path,
    *,
    allow_partial: bool,
) -> tuple[list[_ShardSpec], list[str]]:
    if path.is_file():
        return [_ShardSpec(path)], []
    manifest_path = path / "manifest.json"
    if manifest_path.exists():
        return _manifest_shards(path, allow_partial=allow_partial)
    return [_ShardSpec(shard) for shard in sorted(path.rglob("*.geojson"))], []


class OhsomeGeoJSONAdapter:
    """Import one saved ohsome shard or a completed-shard directory offline."""

    source_name = "openstreetmap_ohsome"

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult:
        return self.import_path(connection, path, retrieved_at=retrieved_at)

    def import_path(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
        allow_partial: bool = False,
    ) -> ImportResult:
        shard_specs, manifest_warnings = _shard_specs(
            Path(path), allow_partial=allow_partial
        )
        if not shard_specs:
            raise ValueError("no saved ohsome GeoJSON shards found")
        records: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any], str, str]] = {}
        examined = 0
        duplicates = 0
        warnings = list(manifest_warnings)
        for shard_spec in sorted(shard_specs, key=lambda spec: spec.path):
            shard = shard_spec.path
            raw = shard.read_bytes()
            shard_hash = hashlib.sha256(raw).hexdigest()
            if shard_spec.sha256 is not None and shard_hash != shard_spec.sha256:
                raise ValueError(f"{shard}: SHA256 does not match ohsome manifest")
            document = json.loads(raw)
            if document.get("type") != "FeatureCollection" or not isinstance(
                document.get("features"), list
            ):
                raise ValueError(f"{shard} is not an ohsome GeoJSON FeatureCollection")
            if (
                shard_spec.feature_count is not None
                and len(document["features"]) != shard_spec.feature_count
            ):
                raise ValueError(f"{shard}: feature_count does not match ohsome manifest")
            for feature in document["features"]:
                examined += 1
                if not isinstance(feature, dict):
                    warnings.append(f"{shard.name}: skipped non-object feature")
                    continue
                identity = _feature_identity(feature)
                if identity is None:
                    warnings.append(f"{shard.name}: skipped feature without a valid @osmId")
                    continue
                previous = records.get(identity)
                candidate = (feature, document, shard_hash, shard.name)
                if previous is not None:
                    duplicates += 1
                    if _feature_rank(feature) <= _feature_rank(previous[0]):
                        continue
                records[identity] = candidate

        imported = 0
        skipped = examined - len(records)
        entities_created = 0
        evidence_created = 0
        with connection:
            for (osm_type, identifier), (feature, document, shard_hash, shard_name) in sorted(
                records.items()
            ):
                properties = feature.get("properties") or {}
                tags = _tag_properties(properties)
                if not is_explicit_data_center(tags):
                    skipped += 1
                    continue
                geometry = feature.get("geometry")
                if geometry is not None and not isinstance(geometry, dict):
                    warnings.append(f"{shard_name}: {osm_type}/{identifier} has invalid geometry")
                    geometry = None
                latitude, longitude = extract_center({"type": osm_type}, geometry)
                name = tags.get("name") or f"OpenStreetMap {osm_type} {identifier}"
                source_url = f"https://www.openstreetmap.org/{osm_type}/{identifier}"
                api_request_url = str((document.get("metadata") or {}).get("requestUrl") or "")
                snapshot_at = _snapshot_time(document, properties, retrieved_at)
                as_of_date = snapshot_at[:10]
                last_edit = properties.get("@timestamp")
                feature_blob = json.dumps(feature, sort_keys=True, separators=(",", ":")).encode()
                feature_hash = hashlib.sha256(feature_blob).hexdigest()
                evidence_id = stable_id(
                    "evidence", "ohsome", osm_type, identifier, retrieved_at, feature_hash
                )
                evidence_created += int(
                    add_evidence(
                        connection,
                        Evidence(
                            id=evidence_id,
                            kind=EvidenceKind.OPENSTREETMAP,
                            title=f"OpenStreetMap {osm_type} {identifier}: {name}",
                            source_url=source_url,
                            publisher="OpenStreetMap contributors",
                            source_family="openstreetmap",
                            license=OSM_LICENSE,
                            attribution=OSM_ATTRIBUTION,
                            published_at=str(last_edit) if last_edit else None,
                            retrieved_at=retrieved_at,
                            excerpt=json.dumps(tags, sort_keys=True),
                        ),
                        content_hash=feature_hash,
                        metadata={
                            "api": "ohsome",
                            "api_version": document.get("apiVersion"),
                            "api_request_url": api_request_url,
                            "copyright_url": OHSOME_COPYRIGHT_URL,
                            "input_sha256": shard_hash,
                            "input_shard": shard_name,
                            "osm_type": osm_type,
                            "osm_id": identifier,
                            "osm_version": properties.get("@version"),
                            "changeset_id": properties.get("@changesetId"),
                            "last_edit_at": last_edit,
                            "snapshot_at": snapshot_at,
                        },
                    )
                )
                stable_key = f"osm:{osm_type}/{identifier}"
                kind = infer_entity_kind({"type": osm_type}, tags)
                status, status_confidence, status_method = infer_lifecycle(tags)
                primary_id, created = self._add_primary(
                    connection,
                    kind=kind,
                    stable_key=stable_key,
                    evidence_id=evidence_id,
                    created_at=retrieved_at,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    tags=tags,
                    as_of_date=as_of_date,
                )
                entities_created += created
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", primary_id, evidence_id),
                    entity_id=primary_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    tags=tags,
                    evidence_id=evidence_id,
                    as_of_date=as_of_date,
                    recorded_at=retrieved_at,
                    method="ohsome_explicit_osm_data_center_tag",
                    confidence=0.80,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", primary_id, evidence_id, status.value),
                        entity_id=primary_id,
                        status=status,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method=status_method,
                        confidence=status_confidence,
                    ),
                )
                operating_model = _explicit_operating_model(tags)
                if operating_model:
                    add_operating_model(
                        connection,
                        observation_id=stable_id(
                            "operating-model", primary_id, evidence_id, operating_model.value
                        ),
                        entity_id=primary_id,
                        operating_model=operating_model,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_explicit_classification_tag",
                        confidence=0.70,
                    )
                for workload in _explicit_workloads(tags):
                    add_workload(
                        connection,
                        observation_id=stable_id(
                            "workload", primary_id, evidence_id, workload.value
                        ),
                        entity_id=primary_id,
                        workload=workload,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_explicit_classification_tag",
                        confidence=0.65,
                    )
                if status in {LifecycleStatus.PROPOSED, LifecycleStatus.UNDER_CONSTRUCTION}:
                    project_key = f"{stable_key}:development-project"
                    project_id = stable_id("entity", project_key, "project")
                    entities_created += int(
                        add_project(
                            connection,
                            Project(project_id, project_key, evidence_id, primary_id),
                            created_at=retrieved_at,
                        )
                    )
                    add_snapshot(
                        connection,
                        snapshot_id=stable_id("snapshot", project_id, evidence_id),
                        entity_id=project_id,
                        name=f"{name} development project",
                        latitude=latitude,
                        longitude=longitude,
                        geometry=geometry,
                        tags=tags,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method="osm_lifecycle_project",
                        confidence=status_confidence,
                    )
                    add_lifecycle(
                        connection,
                        LifecycleObservation(
                            id=stable_id("lifecycle", project_id, evidence_id, status.value),
                            entity_id=project_id,
                            status=status,
                            evidence_id=evidence_id,
                            as_of_date=as_of_date,
                            recorded_at=retrieved_at,
                            method=status_method,
                            confidence=status_confidence,
                        ),
                    )
                imported += 1

        if duplicates:
            warnings.append(f"deduplicated {duplicates} boundary-overlap feature(s) by @osmId")
        return ImportResult(
            source=self.source_name,
            examined_elements=examined,
            imported_elements=imported,
            skipped_elements=skipped,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _add_primary(
        connection: sqlite3.Connection,
        *,
        kind: EntityKind,
        stable_key: str,
        evidence_id: str,
        created_at: str,
        name: str,
        latitude: float | None,
        longitude: float | None,
        geometry: dict[str, Any] | None,
        tags: dict[str, str],
        as_of_date: str,
    ) -> tuple[str, int]:
        if kind is EntityKind.CAMPUS:
            entity_id = stable_id("entity", stable_key, "campus")
            return entity_id, int(
                add_campus(connection, Campus(entity_id, stable_key, evidence_id), created_at=created_at)
            )
        if kind is EntityKind.BUILDING:
            facility_key = f"{stable_key}:facility-container"
            facility_id = stable_id("entity", facility_key, "facility")
            created = int(
                add_facility(
                    connection,
                    Facility(facility_id, facility_key, evidence_id),
                    created_at=created_at,
                )
            )
            add_snapshot(
                connection,
                snapshot_id=stable_id("snapshot", facility_id, evidence_id),
                entity_id=facility_id,
                name=f"{name} facility",
                latitude=latitude,
                longitude=longitude,
                geometry=geometry,
                tags=tags,
                evidence_id=evidence_id,
                as_of_date=as_of_date,
                recorded_at=created_at,
                method="osm_synthetic_facility_container",
                confidence=0.60,
            )
            entity_id = stable_id("entity", stable_key, "building")
            created += int(
                add_building(
                    connection,
                    Building(entity_id, stable_key, evidence_id, facility_id),
                    created_at=created_at,
                )
            )
            return entity_id, created
        entity_id = stable_id("entity", stable_key, "facility")
        return entity_id, int(
            add_facility(
                connection,
                Facility(entity_id, stable_key, evidence_id),
                created_at=created_at,
            )
        )
