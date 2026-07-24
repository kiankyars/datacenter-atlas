#!/usr/bin/env python3
"""Fetch the bounded official GHSL 2020 1 km blind-frame auxiliaries."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, BinaryIO, Sequence
import urllib.error
import urllib.parse
import urllib.request
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "source_cache" / "ghsl-r2023a-2020-1km"
MANIFEST_FILENAME = "fetch-manifest.json"
USER_AGENT = (
    "DataCenterAtlas/0.1 blind-tile-GHSL-auxiliary "
    "(+https://github.com/kiankyars/semiconductors)"
)
ALLOWED_HOST = "jeodpp.jrc.ec.europa.eu"
MAX_REDIRECTS = 3
COPYRIGHT_BYTES = 540
COPYRIGHT_SHA256 = "f20723519a580fb35b3499870f0b1baea54f483195105416e547f0014f1610d2"
FROZEN_DIRECTORY_MODE = 0o555
FROZEN_FILE_MODE = 0o444
ASSESSMENT_FILES = {
    "README.md": (
        1_753,
        "54390f19dd4f28135f534fcc11d3500e4e0773f220441f5cf7597452bcc91610",
    ),
    "raster-metadata.json": (
        3_532,
        "1343f3199e1ee42d29be326bc2e593ee600b1c53e67875c8675880efacf5cf99",
    ),
}


@dataclass(frozen=True, slots=True)
class Artifact:
    artifact_id: str
    filename: str
    url: str
    expected_bytes: int
    expected_sha256: str
    copyright_filename: str
    copyright_url: str


ARTIFACTS = (
    Artifact(
        "ghs-built-s-2020-1km-v1-0",
        "GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000_V1_0.zip",
        "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
        "GHS_BUILT_S_GLOBE_R2023A/GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000/"
        "V1-0/GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000_V1_0.zip",
        152_527_564,
        "5ab899936b560f1b803778fffe6912a28de50036e2bfa0338d55ed34e502d8a2",
        "GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000.copyright.txt",
        "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
        "GHS_BUILT_S_GLOBE_R2023A/GHS_BUILT_S_E2020_GLOBE_R2023A_54009_1000/"
        "copyright.txt",
    ),
    Artifact(
        "ghs-smod-2020-1km-v2-0",
        "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip",
        "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
        "GHS_SMOD_GLOBE_R2023A/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000/"
        "V2-0/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip",
        35_853_870,
        "5a81c3827c9bbc9109159b4c3f92ac7722705944e43038219f142b410431a852",
        "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000.copyright.txt",
        "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
        "GHS_SMOD_GLOBE_R2023A/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000/"
        "copyright.txt",
    ),
)


class GhslFetchError(ValueError):
    """Raised when the bounded GHSL fetch or cache validation fails closed."""


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, maximum: int = MAX_REDIRECTS) -> None:
        super().__init__()
        self.maximum = maximum
        self.count = 0

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        self.count += 1
        if self.count > self.maximum:
            raise GhslFetchError("GHSL request exceeded the redirect cap")
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise GhslFetchError("GHSL redirect left the pinned HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path, label: str) -> os.stat_result:
    if path.is_symlink():
        raise GhslFetchError(f"{label} must not be a symlink")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise GhslFetchError(f"{label} is missing") from error
    if not stat.S_ISREG(status.st_mode):
        raise GhslFetchError(f"{label} must be a regular file")
    return status


def _response_metadata(response: Any, requested_url: str) -> dict[str, Any]:
    status = getattr(response, "status", response.getcode())
    if status not in {200, 206}:
        raise GhslFetchError(f"GHSL response returned HTTP {status}")
    final_url = response.geturl()
    parsed = urllib.parse.urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise GhslFetchError("GHSL response left the pinned HTTPS host")
    encoding = (response.headers.get("Content-Encoding") or "identity").lower()
    if encoding != "identity":
        raise GhslFetchError("GHSL response used an unexpected content encoding")
    return {
        "accept_ranges": response.headers.get("Accept-Ranges"),
        "content_length": response.headers.get("Content-Length"),
        "content_range": response.headers.get("Content-Range"),
        "content_type": response.headers.get("Content-Type"),
        "etag": response.headers.get("ETag"),
        "final_url": final_url,
        "last_modified": response.headers.get("Last-Modified"),
        "requested_url": requested_url,
        "status": status,
    }


def _opener() -> tuple[Any, _BoundedRedirectHandler]:
    handler = _BoundedRedirectHandler()
    return urllib.request.build_opener(handler), handler


def _archive_request(
    artifact: Artifact,
    destination: Path,
    *,
    timeout: float,
    chunk_size: int,
) -> dict[str, Any]:
    partial = destination.with_name(f".{destination.name}.partial")
    if destination.exists() or destination.is_symlink():
        raise GhslFetchError(f"refusing to overwrite GHSL archive: {destination}")
    if partial.is_symlink() or (partial.exists() and not partial.is_file()):
        raise GhslFetchError("GHSL partial path is unsafe")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > artifact.expected_bytes:
        raise GhslFetchError("GHSL partial archive exceeds the pinned byte count")
    headers = {"Accept-Encoding": "identity", "User-Agent": USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(artifact.url, headers=headers)
    opener, redirects = _opener()
    try:
        response_context = opener.open(request, timeout=timeout)
    except urllib.error.URLError as error:
        raise GhslFetchError(f"GHSL archive request failed: {error}") from error
    with response_context as response:
        metadata = _response_metadata(response, artifact.url)
        expected_status = 206 if offset else 200
        if metadata["status"] != expected_status:
            raise GhslFetchError(
                f"GHSL archive returned HTTP {metadata['status']}; expected {expected_status}"
            )
        remaining = artifact.expected_bytes - offset
        if metadata["content_length"] != str(remaining):
            raise GhslFetchError("GHSL archive Content-Length changed")
        if offset:
            expected_range = (
                f"bytes {offset}-{artifact.expected_bytes - 1}/{artifact.expected_bytes}"
            )
            if metadata["content_range"] != expected_range:
                raise GhslFetchError("GHSL archive byte range was not honored exactly")
        written = 0
        mode = "ab" if partial.exists() else "xb"
        with partial.open(mode) as output:
            while chunk := response.read(min(chunk_size, remaining - written + 1)):
                if written + len(chunk) > remaining:
                    raise GhslFetchError("GHSL archive exceeded the pinned byte count")
                output.write(chunk)
                written += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if written != remaining:
            raise GhslFetchError("GHSL archive transfer ended before the pinned byte count")
    if partial.stat().st_size != artifact.expected_bytes:
        raise GhslFetchError("GHSL archive size changed after transfer")
    partial.replace(destination)
    return {
        **metadata,
        "downloaded_bytes": written,
        "redirect_count": redirects.count,
        "resumed_from_bytes": offset,
    }


def _copyright_request(
    artifact: Artifact, destination: Path, *, timeout: float
) -> dict[str, Any]:
    if destination.exists() or destination.is_symlink():
        raise GhslFetchError(f"refusing to overwrite copyright file: {destination}")
    request = urllib.request.Request(
        artifact.copyright_url,
        headers={"Accept-Encoding": "identity", "User-Agent": USER_AGENT},
    )
    opener, redirects = _opener()
    try:
        response_context = opener.open(request, timeout=timeout)
    except urllib.error.URLError as error:
        raise GhslFetchError(f"GHSL copyright request failed: {error}") from error
    with response_context as response:
        metadata = _response_metadata(response, artifact.copyright_url)
        if metadata["status"] != 200:
            raise GhslFetchError("GHSL copyright request did not return HTTP 200")
        raw = response.read(COPYRIGHT_BYTES + 1)
    if len(raw) != COPYRIGHT_BYTES or hashlib.sha256(raw).hexdigest() != COPYRIGHT_SHA256:
        raise GhslFetchError("GHSL copyright bytes changed")
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise GhslFetchError("GHSL copyright temporary path is unsafe")
    with temporary.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(destination)
    return {**metadata, "downloaded_bytes": len(raw), "redirect_count": redirects.count}


def _zip_inventory(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                member = Path(item.filename)
                if member.is_absolute() or ".." in member.parts or "\\" in item.filename:
                    raise GhslFetchError("GHSL ZIP contains an unsafe member path")
                if stat.S_ISLNK((item.external_attr >> 16) & 0xFFFF):
                    raise GhslFetchError("GHSL ZIP contains a symbolic-link member")
                if item.is_dir():
                    continue
                rows.append(
                    {
                        "compressed_bytes": item.compress_size,
                        "crc32": f"{item.CRC:08x}",
                        "path": item.filename,
                        "uncompressed_bytes": item.file_size,
                    }
                )
    except zipfile.BadZipFile as error:
        raise GhslFetchError("GHSL archive is not a valid ZIP") from error
    if not rows:
        raise GhslFetchError("GHSL ZIP contains no files")
    return rows


def _artifact_checkpoint(artifact: Artifact, directory: Path) -> dict[str, Any]:
    archive = directory / artifact.filename
    copyright_path = directory / artifact.copyright_filename
    archive_status = _regular_file(archive, "GHSL archive")
    copyright_status = _regular_file(copyright_path, "GHSL copyright")
    if archive_status.st_size != artifact.expected_bytes:
        raise GhslFetchError("cached GHSL archive byte count changed")
    archive_sha256 = _sha256_file(archive)
    if archive_sha256 != artifact.expected_sha256:
        raise GhslFetchError("cached GHSL archive SHA-256 changed")
    copyright_raw = copyright_path.read_bytes()
    if (
        copyright_status.st_size != COPYRIGHT_BYTES
        or hashlib.sha256(copyright_raw).hexdigest() != COPYRIGHT_SHA256
    ):
        raise GhslFetchError("cached GHSL copyright bytes changed")
    return {
        "artifact_id": artifact.artifact_id,
        "archive": {
            "bytes": archive_status.st_size,
            "path": artifact.filename,
            "sha256": archive_sha256,
            "url": artifact.url,
            "zip_inventory": _zip_inventory(archive),
        },
        "copyright": {
            "bytes": copyright_status.st_size,
            "path": artifact.copyright_filename,
            "sha256": hashlib.sha256(copyright_raw).hexdigest(),
            "url": artifact.copyright_url,
        },
    }


def _validate_manifest(document: Any, directory: Path) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise GhslFetchError("GHSL fetch manifest must be an object")
    if (
        document.get("schema_version") != 1
        or document.get("pipeline") != "ghsl_blind_tile_auxiliary_fetch"
        or document.get("state") != "completed"
        or document.get("production_frame_built") is not False
    ):
        raise GhslFetchError("GHSL fetch manifest identity or accounting changed")
    expected = [_artifact_checkpoint(artifact, directory) for artifact in ARTIFACTS]
    if document.get("artifacts") != expected:
        raise GhslFetchError("GHSL fetch manifest checkpoints changed")
    requests = document.get("requests")
    if not isinstance(requests, list) or len(requests) != 4:
        raise GhslFetchError("GHSL request inventory changed")
    request_count = sum(row.get("status") is not None for row in requests if isinstance(row, dict))
    archive_count = sum(
        row.get("type") == "archive_get" and row.get("downloaded_bytes", 0) > 0
        for row in requests
        if isinstance(row, dict)
    )
    if (
        document.get("http_request_count") != request_count
        or not 0 <= request_count <= 4
        or document.get("downloaded_archive_count") != archive_count
        or not 0 <= archive_count <= 2
    ):
        raise GhslFetchError("GHSL request/download accounting changed")
    return document


def _expected_frozen_inventory() -> set[str]:
    filenames = {MANIFEST_FILENAME, *ASSESSMENT_FILES}
    for artifact in ARTIFACTS:
        filenames.add(artifact.filename)
        filenames.add(artifact.copyright_filename)
    return filenames


def _validate_frozen_inventory(directory: Path) -> None:
    if directory.is_symlink():
        raise GhslFetchError("frozen GHSL cache directory must not be a symlink")
    status = directory.stat()
    if stat.S_IMODE(status.st_mode) != FROZEN_DIRECTORY_MODE:
        raise GhslFetchError("frozen GHSL cache directory mode must be 0555")
    actual = {entry.name for entry in directory.iterdir()}
    expected = _expected_frozen_inventory()
    if actual != expected:
        raise GhslFetchError("frozen GHSL cache file inventory changed")
    for filename in sorted(expected):
        path = directory / filename
        file_status = _regular_file(path, f"frozen GHSL cache file {filename}")
        if stat.S_IMODE(file_status.st_mode) != FROZEN_FILE_MODE:
            raise GhslFetchError(f"frozen GHSL cache file mode changed: {filename}")
    for filename, (expected_bytes, expected_sha256) in ASSESSMENT_FILES.items():
        path = directory / filename
        if path.stat().st_size != expected_bytes or _sha256_file(path) != expected_sha256:
            raise GhslFetchError(f"frozen GHSL assessment file changed: {filename}")
    metadata_path = directory / "raster-metadata.json"
    try:
        metadata = json.loads(metadata_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GhslFetchError("frozen GHSL raster metadata is invalid JSON") from error
    if metadata_path.read_bytes() != _canonical_json(metadata):
        raise GhslFetchError("frozen GHSL raster metadata must be canonical JSON")


def validate_cache(
    directory: Path = OUTPUT_DIRECTORY, *, require_frozen_inventory: bool = True
) -> dict[str, Any]:
    manifest_path = directory / MANIFEST_FILENAME
    _regular_file(manifest_path, "GHSL fetch manifest")
    try:
        document = json.loads(manifest_path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GhslFetchError("GHSL fetch manifest is invalid JSON") from error
    if manifest_path.read_bytes() != _canonical_json(document):
        raise GhslFetchError("GHSL fetch manifest must be canonical JSON")
    validated = _validate_manifest(document, directory)
    if require_frozen_inventory:
        _validate_frozen_inventory(directory)
    return validated


def fetch_cache(
    directory: Path = OUTPUT_DIRECTORY,
    *,
    timeout: float = 120.0,
    chunk_size: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    if timeout <= 0 or chunk_size <= 0:
        raise ValueError("timeout and chunk size must be positive")
    if directory.exists() and not directory.is_dir():
        raise GhslFetchError("GHSL output must be a directory")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / MANIFEST_FILENAME
    if manifest_path.exists() or manifest_path.is_symlink():
        return validate_cache(directory, require_frozen_inventory=False)
    started_at = _utc_now()
    requests: list[dict[str, Any]] = []
    for artifact in ARTIFACTS:
        archive_path = directory / artifact.filename
        copyright_path = directory / artifact.copyright_filename
        if archive_path.exists():
            if archive_path.stat().st_size != artifact.expected_bytes:
                raise GhslFetchError("pre-existing GHSL archive has the wrong size")
            archive_request = {
                "downloaded_bytes": 0,
                "final_url": None,
                "requested_url": artifact.url,
                "resumed_from_bytes": artifact.expected_bytes,
                "status": None,
                "type": "archive_cached_before_run",
            }
        else:
            archive_request = {
                **_archive_request(
                    artifact,
                    archive_path,
                    timeout=timeout,
                    chunk_size=chunk_size,
                ),
                "type": "archive_get",
            }
        requests.append(archive_request)
        if copyright_path.exists():
            _artifact_checkpoint(artifact, directory)
            copyright_request = {
                "downloaded_bytes": 0,
                "final_url": None,
                "requested_url": artifact.copyright_url,
                "status": None,
                "type": "copyright_cached_before_run",
            }
        else:
            copyright_request = {
                **_copyright_request(artifact, copyright_path, timeout=timeout),
                "type": "copyright_get",
            }
        requests.append(copyright_request)
    manifest = {
        "artifacts": [_artifact_checkpoint(artifact, directory) for artifact in ARTIFACTS],
        "downloaded_archive_count": sum(
            row["type"] == "archive_get" and row["downloaded_bytes"] > 0
            for row in requests
        ),
        "finished_at": _utc_now(),
        "http_request_count": sum(row["status"] is not None for row in requests),
        "invocation": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "pipeline": "ghsl_blind_tile_auxiliary_fetch",
        "production_frame_built": False,
        "requests": requests,
        "rights": {
            "attribution": "European Union / European Commission, Joint Research Centre (JRC)",
            "license": "CC-BY-4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0",
            "source_copyright_sha256": COPYRIGHT_SHA256,
        },
        "schema_version": 1,
        "started_at": started_at,
        "state": "completed",
    }
    temporary = manifest_path.with_name(f".{MANIFEST_FILENAME}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise GhslFetchError("GHSL manifest temporary path is unsafe")
    with temporary.open("xb") as output:
        output.write(_canonical_json(manifest))
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(manifest_path)
    return validate_cache(directory, require_frozen_inventory=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=OUTPUT_DIRECTORY)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--chunk-size", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args(argv)
    result = (
        validate_cache(arguments.output_directory)
        if arguments.verify_only
        else fetch_cache(
            arguments.output_directory,
            timeout=arguments.timeout,
            chunk_size=arguments.chunk_size,
        )
    )
    print(
        json.dumps(
            {
                "artifact_count": len(result["artifacts"]),
                "http_request_count": result["http_request_count"],
                "mode": "verify_only" if arguments.verify_only else "fetch_and_verify",
                "output": str(arguments.output_directory),
                "production_frame_built": False,
                "state": result["state"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
