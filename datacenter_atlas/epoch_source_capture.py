"""Offline integrity validator for a bounded Epoch AI source capture."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import zipfile


MANIFEST_FILENAME = "fetch-manifest.json"
README_FILENAME = "README.md"
ARCHIVE_FILENAME = "data_centers.zip"
DATA_CENTERS_FILENAME = "data_centers.csv"
TIMELINES_FILENAME = "data_center_timelines.csv"
EXPECTED_SOURCE_URLS = {
    "data_centers.zip": "https://epoch.ai/data/data_centers/data_centers.zip",
    "landing.html": "https://epoch.ai/data/ai-data-centers",
    "map.html": "https://epoch.ai/data/ai-data-centers/map",
    "methodology.html": "https://epoch.ai/data/data-centers-documentation/methodology",
}
EXPECTED_FILES = frozenset({MANIFEST_FILENAME, README_FILENAME, *EXPECTED_SOURCE_URLS})
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 10_000_000


class EpochSourceCaptureError(ValueError):
    """Raised when the saved capture does not match its closed manifest."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EpochSourceCaptureError("retrieved_at must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EpochSourceCaptureError("retrieved_at must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EpochSourceCaptureError("retrieved_at must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EpochSourceCaptureError(f"{field} must be a positive integer")
    return value


def _archive_inventory(path: Path) -> tuple[list[dict[str, Any]], int, bytes, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise EpochSourceCaptureError("archive CRC validation failed")
            records: list[dict[str, Any]] = []
            names: set[str] = set()
            centers = b""
            timelines = b""
            for member in archive.infolist():
                pure = PurePosixPath(member.filename)
                file_type = (member.external_attr >> 16) & 0o170000
                if (
                    member.is_dir()
                    or pure.is_absolute()
                    or len(pure.parts) != 1
                    or pure.name in {"", ".", ".."}
                    or "\\" in member.filename
                    or file_type not in {0, stat.S_IFREG}
                ):
                    raise EpochSourceCaptureError(
                        f"unsafe or non-regular archive member: {member.filename}"
                    )
                if member.filename in names:
                    raise EpochSourceCaptureError(
                        f"duplicate archive member: {member.filename}"
                    )
                names.add(member.filename)
                records.append(
                    {
                        "bytes": member.file_size,
                        "crc32": f"{member.CRC:08x}",
                        "name": member.filename,
                    }
                )
                if member.filename == DATA_CENTERS_FILENAME:
                    centers = archive.read(member)
                elif member.filename == TIMELINES_FILENAME:
                    timelines = archive.read(member)
            total = sum(record["bytes"] for record in records)
            if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise EpochSourceCaptureError("archive exceeds the bounded size ceiling")
            if not centers or not timelines:
                raise EpochSourceCaptureError(
                    "archive lacks the required center or timeline table"
                )
            return records, total, centers, timelines
    except zipfile.BadZipFile as error:
        raise EpochSourceCaptureError("data_centers.zip is not a valid ZIP") from error


def _csv_rows(raw: bytes, filename: str) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(
            io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
        )
        return [
            {str(key): str(value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]
    except UnicodeDecodeError as error:
        raise EpochSourceCaptureError(f"{filename} is not valid UTF-8 CSV") from error


def _dataset_inventory(centers_raw: bytes, timelines_raw: bytes) -> dict[str, Any]:
    centers = _csv_rows(centers_raw, DATA_CENTERS_FILENAME)
    timelines = _csv_rows(timelines_raw, TIMELINES_FILENAME)
    if not centers or "Name" not in centers[0]:
        raise EpochSourceCaptureError("data_centers.csv lacks the Name column")
    if not timelines or "Data center" not in timelines[0]:
        raise EpochSourceCaptureError(
            "data_center_timelines.csv lacks the Data center column"
        )
    center_names = {row["Name"].strip().casefold() for row in centers if row["Name"].strip()}
    missing: dict[str, str] = {}
    for row in timelines:
        name = row["Data center"].strip()
        if name and name.casefold() not in center_names:
            missing.setdefault(name.casefold(), name)
    return {
        "data_center_rows": len(centers),
        "timeline_names_missing_from_data_centers": sorted(missing.values()),
        "timeline_rows": len(timelines),
    }


def validate_epoch_source_capture(
    directory: str | Path, *, require_frozen: bool = True
) -> dict[str, Any]:
    """Validate exact files, hashes, archive closure, table accounting, and modes."""
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise EpochSourceCaptureError("capture root must be a regular directory")
    entries = list(root.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise EpochSourceCaptureError("capture may contain only ordinary files")
    actual_files = {path.name for path in entries}
    if actual_files != EXPECTED_FILES:
        raise EpochSourceCaptureError(
            f"capture file set differs: expected {sorted(EXPECTED_FILES)}, "
            f"found {sorted(actual_files)}"
        )

    manifest_path = root / MANIFEST_FILENAME
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EpochSourceCaptureError("fetch manifest is not valid JSON") from error
    expected_keys = {
        "archive_inventory",
        "archive_uncompressed_bytes",
        "dataset_inventory",
        "mode",
        "request_count",
        "retrieved_at",
        "schema_version",
        "sources",
        "support_files",
        "user_agent",
    }
    if not isinstance(manifest, dict) or set(manifest) != expected_keys:
        raise EpochSourceCaptureError("fetch manifest schema is invalid")
    if raw != _canonical_json(manifest):
        raise EpochSourceCaptureError("fetch manifest is not canonical JSON")
    if manifest["schema_version"] != 1 or manifest["mode"] != "bounded_direct_fetch":
        raise EpochSourceCaptureError("fetch manifest mode or schema is invalid")
    if _timestamp(manifest["retrieved_at"]) != manifest["retrieved_at"]:
        raise EpochSourceCaptureError("retrieved_at is not canonical UTC")
    if not isinstance(manifest["user_agent"], str) or not manifest["user_agent"].strip():
        raise EpochSourceCaptureError("user_agent must be non-empty")

    sources = manifest["sources"]
    if not isinstance(sources, list) or len(sources) != len(EXPECTED_SOURCE_URLS):
        raise EpochSourceCaptureError("source inventory length is invalid")
    observed_sources: dict[str, dict[str, Any]] = {}
    for record in sources:
        if not isinstance(record, dict) or set(record) != {
            "bytes",
            "filename",
            "sha256",
            "url",
        }:
            raise EpochSourceCaptureError("source record schema is invalid")
        filename = record["filename"]
        if not isinstance(filename, str) or filename in observed_sources:
            raise EpochSourceCaptureError("source filenames must be unique strings")
        observed_sources[filename] = record
    if set(observed_sources) != set(EXPECTED_SOURCE_URLS):
        raise EpochSourceCaptureError("source filenames differ from the declared request set")
    for filename, url in EXPECTED_SOURCE_URLS.items():
        record = observed_sources[filename]
        if record["url"] != url or _file_record(root / filename) != {
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        }:
            raise EpochSourceCaptureError(f"source artifact changed: {filename}")
    if manifest["request_count"] != len(sources):
        raise EpochSourceCaptureError("request_count does not match the source inventory")

    support = manifest["support_files"]
    if not isinstance(support, list) or len(support) != 1:
        raise EpochSourceCaptureError("support file inventory is invalid")
    readme_record = support[0]
    if not isinstance(readme_record, dict) or set(readme_record) != {
        "bytes",
        "filename",
        "sha256",
    }:
        raise EpochSourceCaptureError("support file record schema is invalid")
    if readme_record["filename"] != README_FILENAME or _file_record(
        root / README_FILENAME
    ) != {"bytes": readme_record["bytes"], "sha256": readme_record["sha256"]}:
        raise EpochSourceCaptureError("README support artifact changed")

    archive_records, archive_bytes, centers_raw, timelines_raw = _archive_inventory(
        root / ARCHIVE_FILENAME
    )
    if archive_records != manifest["archive_inventory"]:
        raise EpochSourceCaptureError("archive inventory differs from the manifest")
    if archive_bytes != _positive_integer(
        manifest["archive_uncompressed_bytes"], "archive_uncompressed_bytes"
    ):
        raise EpochSourceCaptureError("archive uncompressed byte count differs")
    if _dataset_inventory(centers_raw, timelines_raw) != manifest["dataset_inventory"]:
        raise EpochSourceCaptureError("dataset row or orphan-name accounting differs")

    if require_frozen:
        if root.stat().st_mode & 0o777 != 0o555:
            raise EpochSourceCaptureError("capture root must have mode 0555")
        wrong_modes = [
            path.name for path in entries if path.stat().st_mode & 0o777 != 0o444
        ]
        if wrong_modes:
            raise EpochSourceCaptureError(
                "capture files must have mode 0444: " + ", ".join(sorted(wrong_modes))
            )
    return manifest
