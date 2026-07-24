"""Offline adapter for Epoch AI's CC BY 4.0 AI Data Centers export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from math import isfinite
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .adapters import ImportResult
from .models import (
    Campus,
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    LifecycleObservation,
    LifecycleStatus,
    Workload,
)
from .repository import (
    add_campus,
    add_capacity,
    add_evidence,
    add_lifecycle,
    add_snapshot,
    add_workload,
    stable_id,
)


EPOCH_DATASET_URL = "https://epoch.ai/data/ai-data-centers"
EPOCH_METHODOLOGY_URL = "https://epoch.ai/data/data-centers-documentation/methodology"
EPOCH_LICENSE = "CC-BY-4.0"
EPOCH_ATTRIBUTION = 'Epoch AI, "AI Data Centers" (2026)'
CAPACITY_INTERVAL_FACTOR = 1.4
CAPACITY_INTERVAL_COVERAGE = 0.80
FORECAST_INTERVAL_COVERAGE = 0.50
ANNUAL_LOAD_FACTOR_LOW = 0.50
ANNUAL_LOAD_FACTOR_BASE = 0.80
ANNUAL_LOAD_FACTOR_HIGH = 1.00
HOURS_PER_YEAR = 8760

DATA_CENTERS_FILE = "data_centers.csv"
TIMELINES_FILE = "data_center_timelines.csv"
DATA_CENTER_COLUMNS = {
    "Name",
    "Owner",
    "Users",
    "Selected Sources",
    "Country",
    "Address",
}
TIMELINE_COLUMNS = {
    "Data center",
    "Date",
    "Buildings operational",
    "IT power (MW)",
    "Power (MW)",
}


@dataclass(frozen=True, slots=True)
class EpochMapLocation:
    longitude: float
    latitude: float
    bounds: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class _SourceFiles:
    data_centers: bytes
    timelines: bytes
    provenance: dict[str, str]


@dataclass(frozen=True, slots=True)
class _TimelineRow:
    data_center: str
    as_of: date
    buildings_operational: float | None
    critical_it_mw: float | None
    gross_facility_mw: float | None
    raw: dict[str, str]

    def sanitized(self) -> dict[str, str | float]:
        result: dict[str, str | float] = {"date": self.as_of.isoformat()}
        if self.buildings_operational is not None:
            result["buildings_operational"] = self.buildings_operational
        if self.critical_it_mw is not None:
            result["critical_it_mw"] = self.critical_it_mw
        if self.gross_facility_mw is not None:
            result["gross_facility_mw"] = self.gross_facility_mw
        return result


class _SearchFilterMapPropsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.props: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "astro-island":
            return
        attributes = dict(attrs)
        if "SearchFilterMap" not in (attributes.get("component-url") or ""):
            return
        props = attributes.get("props")
        if props is not None:
            self.props.append(props)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _required_columns(
    fieldnames: Iterable[str] | None,
    required: set[str],
    filename: str,
) -> None:
    present = set(fieldnames or ())
    missing = sorted(required - present)
    if missing:
        raise ValueError(f"{filename} is missing required columns: {', '.join(missing)}")


def _read_csv(raw: bytes, filename: str, required: set[str]) -> list[dict[str, str]]:
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    _required_columns(reader.fieldnames, required, filename)
    return [
        {str(key): str(value or "") for key, value in row.items() if key is not None}
        for row in reader
    ]


def _zip_member(archive: zipfile.ZipFile, filename: str) -> bytes:
    matches = [
        member
        for member in archive.namelist()
        if not member.endswith("/") and PurePosixPath(member).name == filename
    ]
    if len(matches) != 1:
        raise ValueError(f"Epoch ZIP must contain exactly one {filename}")
    return archive.read(matches[0])


def _read_source_files(path: Path) -> _SourceFiles:
    if path.is_dir():
        centers_path = path / DATA_CENTERS_FILE
        timelines_path = path / TIMELINES_FILE
        if not centers_path.is_file() or not timelines_path.is_file():
            raise ValueError(
                "Epoch directory must contain data_centers.csv and "
                "data_center_timelines.csv"
            )
        centers = centers_path.read_bytes()
        timelines = timelines_path.read_bytes()
        provenance = {"input_type": "directory"}
    elif path.is_file():
        archive_bytes = path.read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                centers = _zip_member(archive, DATA_CENTERS_FILE)
                timelines = _zip_member(archive, TIMELINES_FILE)
        except zipfile.BadZipFile as error:
            raise ValueError("Epoch input file must be a valid ZIP archive") from error
        provenance = {"input_type": "zip", "input_sha256": _sha256(archive_bytes)}
    else:
        raise ValueError(f"Epoch input does not exist: {path}")

    provenance["data_centers_sha256"] = _sha256(centers)
    provenance["data_center_timelines_sha256"] = _sha256(timelines)
    return _SourceFiles(centers, timelines, provenance)


def _canonical_metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _container_neutral_metadata_json(metadata: dict[str, Any]) -> str | None:
    comparable = dict(metadata)
    provenance = comparable.get("provenance")
    if not isinstance(provenance, dict):
        return None

    input_type = provenance.get("input_type")
    if input_type == "directory":
        if "input_sha256" in provenance:
            return None
    elif input_type == "zip":
        input_sha256 = provenance.get("input_sha256")
        if not (
            isinstance(input_sha256, str)
            and len(input_sha256) == 64
            and all(character in "0123456789abcdef" for character in input_sha256)
        ):
            return None
    else:
        return None

    comparable["provenance"] = {
        key: value
        for key, value in provenance.items()
        if key not in {"input_type", "input_sha256"}
    }
    return _canonical_metadata_json(comparable)


def _reconcile_existing_evidence_metadata(
    connection: sqlite3.Connection,
    evidence_id: str,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT metadata_json FROM evidence WHERE id = ?", (evidence_id,)
    ).fetchone()
    if row is None:
        return incoming
    try:
        existing = json.loads(row["metadata_json"])
    except (json.JSONDecodeError, TypeError):
        return incoming
    if not isinstance(existing, dict):
        return incoming

    # Preserve the first capture's container audit while allowing the same
    # extracted Epoch payload to be re-imported from a directory or repacked ZIP.
    existing_comparable = _container_neutral_metadata_json(existing)
    incoming_comparable = _container_neutral_metadata_json(incoming)
    if (
        existing_comparable is not None
        and incoming_comparable is not None
        and existing_comparable == incoming_comparable
    ):
        return existing
    return incoming


def _add_epoch_evidence(
    connection: sqlite3.Connection,
    evidence: Evidence,
    *,
    content_hash: str,
    metadata: dict[str, Any],
) -> bool:
    reconciled = _reconcile_existing_evidence_metadata(
        connection, evidence.id, metadata
    )
    try:
        return add_evidence(
            connection,
            evidence,
            content_hash=content_hash,
            metadata=reconciled,
        )
    except ValueError as error:
        conflict_prefix = f"evidence.{evidence.id} conflicts on persisted fields:"
        if not str(error).startswith(conflict_prefix):
            raise

        # Another writer may have inserted the equivalent record after the first
        # lookup. Reconcile against that committed row and retry exactly once.
        retry_metadata = _reconcile_existing_evidence_metadata(
            connection, evidence.id, metadata
        )
        if _canonical_metadata_json(retry_metadata) == _canonical_metadata_json(
            reconciled
        ):
            raise
        return add_evidence(
            connection,
            evidence,
            content_hash=content_hash,
            metadata=retry_metadata,
        )


def _encoded_value(value: Any, expected_tag: int) -> Any:
    if not isinstance(value, list) or len(value) != 2 or value[0] != expected_tag:
        raise ValueError("unsupported Astro serialized value")
    return value[1]


def _astro_object(value: Any) -> dict[str, Any]:
    decoded = _encoded_value(value, 0)
    if not isinstance(decoded, dict):
        raise ValueError("expected an Astro serialized object")
    return decoded


def _astro_array(value: Any) -> list[Any]:
    decoded = _encoded_value(value, 1)
    if not isinstance(decoded, list):
        raise ValueError("expected an Astro serialized array")
    return decoded


def _astro_scalar(value: Any) -> Any:
    decoded = _encoded_value(value, 0)
    if isinstance(decoded, (dict, list)):
        raise ValueError("expected an Astro serialized scalar")
    return decoded


def _astro_number_array(value: Any, *, length: int) -> tuple[float, ...]:
    encoded_items = _astro_array(value)
    if len(encoded_items) != length:
        raise ValueError(f"expected {length} coordinates in Astro map props")
    result = []
    for encoded_item in encoded_items:
        item = _astro_scalar(encoded_item)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("Astro map coordinate must be numeric")
        number = float(item)
        if not isfinite(number):
            raise ValueError("Astro map coordinate must be finite")
        result.append(number)
    return tuple(result)


def _validate_map_location(
    longitude: float,
    latitude: float,
    bounds: tuple[float, float, float, float] | None,
) -> EpochMapLocation:
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("Epoch map longitude/latitude is out of range")
    if bounds is not None:
        west, south, east, north = bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Epoch map bounds are invalid")
    return EpochMapLocation(longitude, latitude, bounds)


def parse_epoch_map_html(path: str | Path) -> dict[str, EpochMapLocation]:
    """Extract only record IDs and coordinates from saved SearchFilterMap props."""

    parser = _SearchFilterMapPropsParser()
    try:
        parser.feed(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"could not read Epoch map HTML: {path}") from error
    if len(parser.props) != 1:
        raise ValueError("Epoch map HTML must contain exactly one SearchFilterMap island")

    try:
        props = json.loads(parser.props[0])
        encoded_records = _astro_array(props["dataCenters"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Epoch map HTML has invalid SearchFilterMap props") from error

    locations: dict[str, EpochMapLocation] = {}
    normalized_ids: set[str] = set()
    for encoded_record in encoded_records:
        record = _astro_object(encoded_record)
        if "id" not in record or "lngLat" not in record:
            continue
        name = str(_astro_scalar(record["id"])).strip()
        if not name:
            continue
        normalized = _normalized_name(name)
        if normalized in normalized_ids:
            raise ValueError(f"duplicate Epoch map record ID: {name}")
        longitude, latitude = _astro_number_array(record["lngLat"], length=2)
        bounds = None
        if "bounds" in record:
            bounds = _astro_number_array(record["bounds"], length=4)
        locations[normalized] = _validate_map_location(longitude, latitude, bounds)
        normalized_ids.add(normalized)
    return locations


def _nonnegative_float(value: str, *, field: str, record: str) -> float | None:
    if not value.strip():
        return None
    try:
        result = float(value)
    except ValueError as error:
        raise ValueError(f"invalid {field} for {record}: {value}") from error
    if not isfinite(result) or result < 0:
        raise ValueError(f"invalid {field} for {record}: {value}")
    return result


def _timeline_rows(
    rows: list[dict[str, str]], warnings: list[str]
) -> dict[str, list[_TimelineRow]]:
    grouped: dict[str, list[_TimelineRow]] = defaultdict(list)
    seen: set[tuple[str, date]] = set()
    for row in rows:
        name = row["Data center"].strip()
        if not name:
            warnings.append("skipped timeline row without a data center name")
            continue
        try:
            row_date = date.fromisoformat(row["Date"].strip())
        except ValueError:
            warnings.append(f"skipped timeline row with invalid date for {name}")
            continue
        identity = (_normalized_name(name), row_date)
        if identity in seen:
            raise ValueError(f"duplicate Epoch timeline row for {name} on {row_date}")
        seen.add(identity)
        grouped[identity[0]].append(
            _TimelineRow(
                data_center=name,
                as_of=row_date,
                buildings_operational=_nonnegative_float(
                    row["Buildings operational"],
                    field="Buildings operational",
                    record=name,
                ),
                critical_it_mw=_nonnegative_float(
                    row["IT power (MW)"], field="IT power (MW)", record=name
                ),
                gross_facility_mw=_nonnegative_float(
                    row["Power (MW)"], field="Power (MW)", record=name
                ),
                raw=row,
            )
        )
    for timeline in grouped.values():
        timeline.sort(key=lambda item: item.as_of)
    return grouped


def _has_power(row: _TimelineRow) -> bool:
    values = (row.critical_it_mw, row.gross_facility_mw)
    return any(value is not None and value > 0 for value in values)


def _has_future_growth(current: _TimelineRow, future: Iterable[_TimelineRow]) -> bool:
    current_it = current.critical_it_mw or 0.0
    current_gross = current.gross_facility_mw or 0.0
    return any(
        (row.critical_it_mw or 0.0) > current_it
        or (row.gross_facility_mw or 0.0) > current_gross
        for row in future
    )


def infer_epoch_lifecycle(
    current: _TimelineRow | None,
    future: Iterable[_TimelineRow],
) -> tuple[LifecycleStatus, float, str]:
    if current is None:
        return LifecycleStatus.UNKNOWN, 0.30, "epoch_no_timeline_at_or_before_as_of"
    if not _has_power(current):
        return (
            LifecycleStatus.UNDER_CONSTRUCTION,
            0.55,
            "epoch_inclusion_with_zero_current_power",
        )
    if _has_future_growth(current, future):
        return LifecycleStatus.EXPANSION, 0.70, "epoch_positive_power_with_future_growth"
    return LifecycleStatus.OPERATIONAL, 0.75, "epoch_positive_power_without_future_growth"


def _bounds_geometry(location: EpochMapLocation) -> dict[str, Any]:
    if location.bounds is None:
        return {
            "type": "Point",
            "coordinates": [location.longitude, location.latitude],
        }
    west, south, east, north = location.bounds
    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]],
    }


def _record_hash(
    record: dict[str, str],
    timeline: Iterable[_TimelineRow],
    location: EpochMapLocation | None,
) -> str:
    payload = {
        "data_center": record,
        "timeline": [row.raw for row in timeline],
        "map_location": (
            {
                "lng_lat": [location.longitude, location.latitude],
                "bounds": list(location.bounds) if location.bounds else None,
            }
            if location
            else None
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(canonical)


def _interval(base: float) -> tuple[float, float, float]:
    return base / CAPACITY_INTERVAL_FACTOR, base, base * CAPACITY_INTERVAL_FACTOR


def _future_peak(
    rows: Iterable[_TimelineRow], attribute: str, current_value: float | None
) -> tuple[_TimelineRow, float] | None:
    candidates = [
        (row, value)
        for row in rows
        if (value := getattr(row, attribute)) is not None
        and value > (current_value or 0.0)
    ]
    if not candidates:
        return None
    peak_value = max(value for _, value in candidates)
    return next((row, value) for row, value in candidates if value == peak_value)


def _annual_energy_interval(
    power_low: float, power_base: float, power_high: float
) -> tuple[float, float, float]:
    return (
        power_low * ANNUAL_LOAD_FACTOR_LOW * HOURS_PER_YEAR,
        power_base * ANNUAL_LOAD_FACTOR_BASE * HOURS_PER_YEAR,
        power_high * ANNUAL_LOAD_FACTOR_HIGH * HOURS_PER_YEAR,
    )


class EpochAIAdapter:
    """Import a bounded, previously downloaded Epoch AI dataset without network access."""

    source_name = "epoch_ai_data_centers"

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
        as_of_date: str,
        map_html: str | Path | None = None,
    ) -> ImportResult:
        try:
            cutoff = date.fromisoformat(as_of_date)
        except ValueError as error:
            raise ValueError("as_of_date must use YYYY-MM-DD") from error

        source_files = _read_source_files(Path(path))
        records = _read_csv(source_files.data_centers, DATA_CENTERS_FILE, DATA_CENTER_COLUMNS)
        raw_timelines = _read_csv(
            source_files.timelines, TIMELINES_FILE, TIMELINE_COLUMNS
        )
        warnings: list[str] = []
        timelines = _timeline_rows(raw_timelines, warnings)

        map_locations: dict[str, EpochMapLocation] = {}
        provenance = dict(source_files.provenance)
        if map_html is not None:
            map_path = Path(map_html)
            map_bytes = map_path.read_bytes()
            provenance["map_html_sha256"] = _sha256(map_bytes)
            map_locations = parse_epoch_map_html(map_path)

        named_records: dict[str, dict[str, str]] = {}
        skipped = 0
        for record in records:
            name = record["Name"].strip()
            if not name:
                skipped += 1
                warnings.append("skipped data center record without a name")
                continue
            normalized = _normalized_name(name)
            if normalized in named_records:
                raise ValueError(f"duplicate Epoch data center name: {name}")
            named_records[normalized] = record

        for orphan in sorted(set(timelines) - set(named_records)):
            warnings.append(
                "ignored timeline for unknown data center: "
                f"{timelines[orphan][0].data_center}"
            )
        if map_html is not None:
            for missing in sorted(set(named_records) - set(map_locations)):
                warnings.append(
                    "no map coordinates for Epoch data center: "
                    f"{named_records[missing]['Name'].strip()}"
                )

        imported = 0
        entities_created = 0
        evidence_created = 0
        with connection:
            for normalized, record in named_records.items():
                name = record["Name"].strip()
                timeline = timelines.get(normalized, [])
                current_rows = [row for row in timeline if row.as_of <= cutoff]
                future_rows = [row for row in timeline if row.as_of > cutoff]
                current = current_rows[-1] if current_rows else None
                location = map_locations.get(normalized)

                source_record_id = stable_id(
                    "source-record", "epoch-ai", "data-centers", normalized
                )
                stable_key = f"epoch-ai:data-center:{source_record_id}"
                entity_id = stable_id("entity", stable_key, "campus")
                content_hash = _record_hash(record, timeline, location)
                evidence_id = stable_id(
                    "evidence",
                    "epoch-ai",
                    source_record_id,
                    retrieved_at,
                    content_hash,
                )

                metadata: dict[str, Any] = {
                    "source_record_id": source_record_id,
                    "record": {
                        "name": name,
                        "address": record["Address"].strip(),
                        "country": record["Country"].strip(),
                        "owner": record["Owner"].strip(),
                        "users": record["Users"].strip(),
                        "selected_sources": record["Selected Sources"].strip(),
                    },
                    "provenance": provenance,
                    "selected_timeline": current.sanitized() if current else None,
                    "future_timeline_rows": [row.sanitized() for row in future_rows],
                    "capacity_interval": {
                        "coverage": CAPACITY_INTERVAL_COVERAGE,
                        "factor": CAPACITY_INTERVAL_FACTOR,
                        "formula": "low=base/1.4; high=base*1.4",
                        "methodology_url": EPOCH_METHODOLOGY_URL,
                    },
                    "workload_basis": (
                        "Epoch AI defines included sites as running AI-specialized hardware; "
                        "training versus inference is not asserted by this import."
                    ),
                }
                if location:
                    metadata["map_location"] = {
                        "lng_lat": [location.longitude, location.latitude],
                        "bounds": list(location.bounds) if location.bounds else None,
                    }

                evidence = Evidence(
                    id=evidence_id,
                    kind=EvidenceKind.THIRD_PARTY_DATASET,
                    title=f"Epoch AI data center record: {name}",
                    source_url=EPOCH_DATASET_URL,
                    publisher="Epoch AI",
                    source_family="epoch_ai_data_centers",
                    license=EPOCH_LICENSE,
                    attribution=EPOCH_ATTRIBUTION,
                    retrieved_at=retrieved_at,
                    excerpt=f"Epoch AI record selected through {as_of_date}: {name}",
                )
                evidence_created += int(
                    _add_epoch_evidence(
                        connection,
                        evidence,
                        content_hash=content_hash,
                        metadata=metadata,
                    )
                )
                entities_created += int(
                    add_campus(
                        connection,
                        Campus(entity_id, stable_key, evidence_id),
                        created_at=retrieved_at,
                    )
                )

                tags = {
                    "source_dataset": "Epoch AI Data Centers",
                    "source_record_id": source_record_id,
                    "country": record["Country"].strip(),
                    "address": record["Address"].strip(),
                    "owner": record["Owner"].strip(),
                    "users": record["Users"].strip(),
                }
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id, as_of_date),
                    entity_id=entity_id,
                    name=name,
                    latitude=location.latitude if location else None,
                    longitude=location.longitude if location else None,
                    geometry=_bounds_geometry(location) if location else None,
                    tags=tags,
                    evidence_id=evidence_id,
                    as_of_date=as_of_date,
                    recorded_at=retrieved_at,
                    method=(
                        "epoch_dataset_with_saved_map_coordinates"
                        if location
                        else "epoch_dataset_record"
                    ),
                    confidence=0.80 if location else 0.70,
                )

                lifecycle, lifecycle_confidence, lifecycle_method = infer_epoch_lifecycle(
                    current, future_rows
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id(
                            "lifecycle", entity_id, evidence_id, as_of_date, lifecycle.value
                        ),
                        entity_id=entity_id,
                        status=lifecycle,
                        evidence_id=evidence_id,
                        as_of_date=as_of_date,
                        recorded_at=retrieved_at,
                        method=lifecycle_method,
                        confidence=lifecycle_confidence,
                    ),
                )
                add_workload(
                    connection,
                    observation_id=stable_id(
                        "workload",
                        entity_id,
                        evidence_id,
                        as_of_date,
                        Workload.AI_SPECIALIZED_UNSPECIFIED.value,
                    ),
                    entity_id=entity_id,
                    workload=Workload.AI_SPECIALIZED_UNSPECIFIED,
                    evidence_id=evidence_id,
                    as_of_date=as_of_date,
                    recorded_at=retrieved_at,
                    method="epoch_ai_dataset_scope_without_training_inference_subtype",
                    confidence=0.60,
                )

                if current is not None:
                    capacity_stage = (
                        CapacityStage.OPERATIONAL
                        if _has_power(current)
                        else CapacityStage.UNKNOWN
                    )
                    for metric, value in (
                        (CapacityMetric.CRITICAL_IT_MW, current.critical_it_mw),
                        (CapacityMetric.GROSS_FACILITY_MW, current.gross_facility_mw),
                    ):
                        if value is None:
                            warnings.append(
                                f"missing {metric.value} for {name} on {current.as_of}"
                            )
                            continue
                        low, base, high = _interval(value)
                        add_capacity(
                            connection,
                            CapacityEstimate(
                                id=stable_id(
                                    "capacity",
                                    entity_id,
                                    evidence_id,
                                    metric.value,
                                    capacity_stage.value,
                                    current.as_of,
                                ),
                                entity_id=entity_id,
                                metric=metric,
                                low=low,
                                base=base,
                                high=high,
                                method=EstimateMethod.MODELED,
                                confidence=CAPACITY_INTERVAL_COVERAGE,
                                evidence_id=evidence_id,
                                as_of_date=current.as_of.isoformat(),
                                recorded_at=retrieved_at,
                                stage=capacity_stage,
                                notes=(
                                    "Epoch AI modeled current capacity; 80% interval is "
                                    "base divided/multiplied by 1.4."
                                ),
                            ),
                        )
                    if current.gross_facility_mw is not None and current.gross_facility_mw > 0:
                        gross_interval = _interval(current.gross_facility_mw)
                        annual_low, annual_base, annual_high = _annual_energy_interval(
                            *gross_interval
                        )
                        add_capacity(
                            connection,
                            CapacityEstimate(
                                id=stable_id(
                                    "capacity",
                                    entity_id,
                                    evidence_id,
                                    CapacityMetric.ANNUAL_ENERGY_MWH.value,
                                    CapacityStage.OPERATIONAL.value,
                                    current.as_of,
                                ),
                                entity_id=entity_id,
                                metric=CapacityMetric.ANNUAL_ENERGY_MWH,
                                low=annual_low,
                                base=annual_base,
                                high=annual_high,
                                method=EstimateMethod.MODELED,
                                confidence=0.40,
                                evidence_id=evidence_id,
                                as_of_date=current.as_of.isoformat(),
                                recorded_at=retrieved_at,
                                stage=CapacityStage.OPERATIONAL,
                                notes=(
                                    "Atlas modeled annual consumption from Epoch gross facility "
                                    "power using 50%/80%/100% load factors for low/base/high and "
                                    "8,760 hours. This is not metered energy."
                                ),
                            ),
                        )
                    for metric, attribute, current_value in (
                        (
                            CapacityMetric.CRITICAL_IT_MW,
                            "critical_it_mw",
                            current.critical_it_mw,
                        ),
                        (
                            CapacityMetric.GROSS_FACILITY_MW,
                            "gross_facility_mw",
                            current.gross_facility_mw,
                        ),
                    ):
                        peak = _future_peak(future_rows, attribute, current_value)
                        if peak is None:
                            continue
                        target_row, value = peak
                        add_capacity(
                            connection,
                            CapacityEstimate(
                                id=stable_id(
                                    "capacity",
                                    entity_id,
                                    evidence_id,
                                    metric.value,
                                    CapacityStage.FORECAST.value,
                                    cutoff,
                                    target_row.as_of,
                                ),
                                entity_id=entity_id,
                                metric=metric,
                                low=0.0,
                                base=value,
                                high=value * CAPACITY_INTERVAL_FACTOR,
                                method=EstimateMethod.MODELED,
                                confidence=FORECAST_INTERVAL_COVERAGE,
                                evidence_id=evidence_id,
                                as_of_date=cutoff.isoformat(),
                                recorded_at=retrieved_at,
                                stage=CapacityStage.FORECAST,
                                target_date=target_row.as_of.isoformat(),
                                notes=(
                                    "Epoch AI future modeled capacity. Atlas assigns a zero "
                                    "downside bound because future phases can be delayed or "
                                    "cancelled; the upper bound uses Epoch's current-estimate "
                                    "factor only as a provisional heuristic."
                                ),
                            ),
                        )
                    future_gross = _future_peak(
                        future_rows, "gross_facility_mw", current.gross_facility_mw
                    )
                    if future_gross is not None:
                        target_row, gross_value = future_gross
                        annual_low, annual_base, annual_high = _annual_energy_interval(
                            0.0,
                            gross_value,
                            gross_value * CAPACITY_INTERVAL_FACTOR,
                        )
                        add_capacity(
                            connection,
                            CapacityEstimate(
                                id=stable_id(
                                    "capacity",
                                    entity_id,
                                    evidence_id,
                                    CapacityMetric.ANNUAL_ENERGY_MWH.value,
                                    CapacityStage.FORECAST.value,
                                    cutoff,
                                    target_row.as_of,
                                ),
                                entity_id=entity_id,
                                metric=CapacityMetric.ANNUAL_ENERGY_MWH,
                                low=annual_low,
                                base=annual_base,
                                high=annual_high,
                                method=EstimateMethod.MODELED,
                                confidence=0.30,
                                evidence_id=evidence_id,
                                as_of_date=cutoff.isoformat(),
                                recorded_at=retrieved_at,
                                stage=CapacityStage.FORECAST,
                                target_date=target_row.as_of.isoformat(),
                                notes=(
                                    "Atlas modeled target-year annual consumption from Epoch "
                                    "future gross facility power using 50%/80%/100% load factors "
                                    "and 8,760 hours. This is not metered energy and the downside "
                                    "bound is zero for delay or cancellation."
                                ),
                            ),
                        )
                imported += 1

        return ImportResult(
            source=self.source_name,
            examined_elements=len(records),
            imported_elements=imported,
            skipped_elements=skipped,
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )
