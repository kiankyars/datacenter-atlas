#!/usr/bin/env python3
"""Fetch and verify one pinned OpenStreetMap planet PBF.

The downloader writes directly to the dated destination so an interrupted
transfer can be resumed with an HTTP Range request.  A completed file is not
trusted until its exact byte count and the official MD5 both match.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Sequence
import urllib.parse
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANET_SNAPSHOT_DATE = "2026-07-13"
PLANET_DATE_TOKEN = "260713"
PLANET_FILENAME = f"planet-{PLANET_DATE_TOKEN}.osm.pbf"
PLANET_MD5_FILENAME = f"{PLANET_FILENAME}.md5"
PLANET_URL = f"https://planet.openstreetmap.org/pbf/{PLANET_FILENAME}"
PLANET_MD5_URL = f"{PLANET_URL}.md5"

# Pinned from the official dated object and sidecar, not from planet-latest.
PLANET_SIZE_BYTES = 93_874_282_582
PLANET_MD5 = "f6b3e7b85e291713f1413442017e24a4"
DEFAULT_OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "source_cache" / f"osm-planet-{PLANET_DATE_TOKEN}"
)
DEFAULT_USER_AGENT = (
    "DataCenterAtlas/0.1 planet-fallback "
    "(+https://github.com/kiankyars/datacenter-atlas)"
)
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
OSM_LICENSE = "ODbL-1.0"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
MAX_SIDECAR_BYTES = 1_024


class VerificationError(ValueError):
    """Raised when pinned source metadata or downloaded bytes do not match."""


@dataclass(frozen=True, slots=True)
class DownloadResult:
    resumed_from_bytes: int
    downloaded_bytes: int
    http_status: int | None
    final_url: str | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_md5_sidecar(
    raw: bytes, *, expected_filename: str = PLANET_FILENAME
) -> str:
    """Parse a single GNU-style MD5 line and bind it to the pinned filename."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise VerificationError("planet MD5 sidecar is not ASCII") from error
    match = re.fullmatch(
        r"([0-9a-fA-F]{32})[ \t]+\*?([^\r\n]+)(?:\r?\n)?", text
    )
    if match is None:
        raise VerificationError("planet MD5 sidecar must contain exactly one checksum line")
    digest, filename = match.groups()
    if filename != expected_filename:
        raise VerificationError(
            f"planet MD5 sidecar names {filename!r}, expected {expected_filename!r}"
        )
    return digest.lower()


def hash_file(path: Path, algorithms: Sequence[str] = ("md5", "sha256")) -> dict[str, str]:
    hashers = {name: hashlib.new(name) for name in algorithms}
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {name: hasher.hexdigest() for name, hasher in hashers.items()}


def verify_exact_file(
    path: Path,
    *,
    expected_size: int = PLANET_SIZE_BYTES,
    expected_md5: str = PLANET_MD5,
) -> dict[str, Any]:
    """Verify exact size and digest, returning hashes for the manifest."""
    if path.is_symlink():
        raise VerificationError(f"refusing to verify symlink: {path}")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise VerificationError(f"planet PBF is missing: {path}") from error
    if not stat.S_ISREG(status.st_mode):
        raise VerificationError(f"planet PBF is not a regular file: {path}")
    actual_size = status.st_size
    if actual_size != expected_size:
        raise VerificationError(
            f"planet PBF is {actual_size} bytes; expected exactly {expected_size}"
        )
    hashes = hash_file(path)
    if not hmac.compare_digest(hashes["md5"], expected_md5.lower()):
        raise VerificationError(
            f"planet PBF MD5 is {hashes['md5']}; expected {expected_md5.lower()}"
        )
    return {"bytes": actual_size, **hashes}


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()
    if not isinstance(status, int):
        raise VerificationError("HTTP response did not provide a numeric status")
    return status


def _response_url(response: Any, fallback: str) -> str:
    getter = getattr(response, "geturl", None)
    value = getter() if callable(getter) else fallback
    parsed = urllib.parse.urlparse(str(value))
    if parsed.scheme != "https":
        raise VerificationError("planet download redirected away from HTTPS")
    return str(value)


def _header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", {})
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    value = getter(name)
    return None if value is None else str(value)


def _validate_identity_encoding(response: Any) -> None:
    encoding = (_header(response, "Content-Encoding") or "identity").lower()
    if encoding != "identity":
        raise VerificationError(f"unexpected HTTP content encoding: {encoding}")


def fetch_md5_sidecar(
    destination: Path,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 120.0,
) -> dict[str, Any]:
    if destination.is_symlink():
        raise VerificationError(f"refusing to replace sidecar symlink: {destination}")
    request = urllib.request.Request(
        PLANET_MD5_URL,
        headers={"Accept-Encoding": "identity", "User-Agent": DEFAULT_USER_AGENT},
    )
    with opener(request, timeout=timeout) as response:
        status = _response_status(response)
        if status != 200:
            raise VerificationError(f"planet MD5 request returned HTTP {status}")
        final_url = _response_url(response, PLANET_MD5_URL)
        _validate_identity_encoding(response)
        raw = response.read(MAX_SIDECAR_BYTES + 1)
    if len(raw) > MAX_SIDECAR_BYTES:
        raise VerificationError("planet MD5 sidecar exceeds its size limit")
    digest = parse_md5_sidecar(raw)
    if not hmac.compare_digest(digest, PLANET_MD5):
        raise VerificationError(
            f"official sidecar MD5 is {digest}; pinned MD5 is {PLANET_MD5}"
        )
    _atomic_write_bytes(destination, raw)
    return {
        "url": PLANET_MD5_URL,
        "final_url": final_url,
        "path": destination.name,
        "bytes": len(raw),
        "md5": digest,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "http_status": status,
    }


def verify_cached_sidecar(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise VerificationError(f"refusing to verify sidecar symlink: {path}")
    try:
        status = path.stat()
    except FileNotFoundError as error:
        raise VerificationError(f"planet MD5 sidecar is missing: {path}") from error
    if not stat.S_ISREG(status.st_mode):
        raise VerificationError(f"planet MD5 sidecar is not a regular file: {path}")
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise VerificationError(f"planet MD5 sidecar is missing: {path}") from error
    if len(raw) > MAX_SIDECAR_BYTES:
        raise VerificationError("planet MD5 sidecar exceeds its size limit")
    digest = parse_md5_sidecar(raw)
    if not hmac.compare_digest(digest, PLANET_MD5):
        raise VerificationError(
            f"cached sidecar MD5 is {digest}; pinned MD5 is {PLANET_MD5}"
        )
    return {
        "url": PLANET_MD5_URL,
        "path": path.name,
        "bytes": len(raw),
        "md5": digest,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "http_status": None,
    }


def download_resumable(
    destination: Path,
    *,
    url: str = PLANET_URL,
    expected_size: int = PLANET_SIZE_BYTES,
    opener: Callable[..., Any] = urllib.request.urlopen,
    timeout: float = 120.0,
    chunk_size: int = 8 * 1024 * 1024,
) -> DownloadResult:
    """Download to ``destination``, strictly validating Range semantics."""
    if expected_size <= 0 or chunk_size <= 0 or timeout <= 0:
        raise ValueError("download size, chunk size, and timeout must be positive")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("planet URL must use HTTPS")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise VerificationError(f"refusing to append to symlink: {destination}")
    if destination.exists() and not destination.is_file():
        raise VerificationError(f"refusing to append to non-file: {destination}")
    offset = destination.stat().st_size if destination.exists() else 0
    if offset > expected_size:
        raise VerificationError(
            f"partial planet PBF is {offset} bytes, larger than expected {expected_size}"
        )
    if offset == expected_size:
        return DownloadResult(offset, 0, None, None)

    headers = {"Accept-Encoding": "identity", "User-Agent": DEFAULT_USER_AGENT}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    with opener(request, timeout=timeout) as response:
        status = _response_status(response)
        final_url = _response_url(response, url)
        _validate_identity_encoding(response)
        expected_status = 206 if offset else 200
        if status != expected_status:
            raise VerificationError(
                f"planet request returned HTTP {status}; expected {expected_status}"
            )
        remaining = expected_size - offset
        content_length = _header(response, "Content-Length")
        if content_length is None or not content_length.isdigit():
            raise VerificationError("planet response has no exact Content-Length")
        if int(content_length) != remaining:
            raise VerificationError(
                f"planet response is {content_length} bytes; expected {remaining}"
            )
        if offset:
            expected_range = f"bytes {offset}-{expected_size - 1}/{expected_size}"
            if _header(response, "Content-Range") != expected_range:
                raise VerificationError(
                    "planet server did not honor the requested byte range exactly"
                )

        written = 0
        mode = "ab" if offset else "wb"
        with destination.open(mode) as output:
            while chunk := response.read(min(chunk_size, remaining - written + 1)):
                if written + len(chunk) > remaining:
                    raise VerificationError("planet response exceeded the pinned byte count")
                output.write(chunk)
                written += len(chunk)
            output.flush()
            os.fsync(output.fileno())
    if written != expected_size - offset:
        raise VerificationError(
            f"planet transfer ended after {written} bytes; expected {expected_size - offset}"
        )
    return DownloadResult(offset, written, status, final_url)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise VerificationError(f"refusing to replace symlink: {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.is_symlink():
        raise VerificationError(f"refusing temporary-file symlink: {temporary}")
    try:
        with temporary.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise VerificationError(f"temporary file already exists: {temporary}") from error
    temporary.replace(path)


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    payload = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resume and verify the pinned 2026-07-13 official OpenStreetMap planet PBF."
        )
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help=f"download directory (default: {DEFAULT_OUTPUT_DIRECTORY})",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--chunk-size", type=int, default=8 * 1024 * 1024)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify the cached sidecar and PBF without making network requests",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    planet_path = output_directory / PLANET_FILENAME
    sidecar_path = output_directory / PLANET_MD5_FILENAME
    manifest_path = output_directory / "fetch-manifest.json"
    started_at = utc_now()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "pipeline": "openstreetmap_planet_fetch",
        "state": "running",
        "started_at": started_at,
        "snapshot_date": PLANET_SNAPSHOT_DATE,
        "invocation": [sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:])],
        "source": {
            "url": PLANET_URL,
            "md5_url": PLANET_MD5_URL,
            "filename": PLANET_FILENAME,
            "expected_bytes": PLANET_SIZE_BYTES,
            "expected_md5": PLANET_MD5,
        },
        "rights": {
            "license": OSM_LICENSE,
            "attribution": OSM_ATTRIBUTION,
            "copyright_url": OSM_COPYRIGHT_URL,
        },
    }
    try:
        sidecar = (
            verify_cached_sidecar(sidecar_path)
            if args.verify_only
            else fetch_md5_sidecar(sidecar_path, timeout=args.timeout)
        )
        if args.verify_only:
            download = DownloadResult(planet_path.stat().st_size, 0, None, None)
        else:
            download = download_resumable(
                planet_path,
                timeout=args.timeout,
                chunk_size=args.chunk_size,
            )
        verified = verify_exact_file(planet_path)
        manifest.update(
            {
                "state": "completed",
                "finished_at": utc_now(),
                "sidecar": sidecar,
                "download": asdict(download),
                "input": {"path": planet_path.name, **verified},
                "verification": {
                    "exact_size": True,
                    "official_md5": True,
                    "verified_before_extraction": True,
                },
            }
        )
        _atomic_write_json(manifest_path, manifest)
    except Exception as error:
        manifest.update(
            {
                "state": "failed",
                "finished_at": utc_now(),
                "error": {"type": type(error).__name__, "message": str(error)},
            }
        )
        _atomic_write_json(manifest_path, manifest)
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
