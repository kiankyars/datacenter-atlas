"""Resolve historical external-capture paths into the local data tree."""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any


PACKAGE_NAME = "atlas-critical-v1-external-captures-2026-08-04"
PACKAGE_ROOT_ENV = "DATACENTER_ATLAS_EXTERNAL_CAPTURES_ROOT"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE_ROOT = (
    REPOSITORY_ROOT / "local_data" / "external-captures" / PACKAGE_NAME
)


class ExternalCaptureError(FileNotFoundError):
    """Raised when a declared historical capture cannot be resolved safely."""


def external_capture_package_root() -> Path:
    """Return the configured package directory without requiring it to exist."""

    configured = os.environ.get(PACKAGE_ROOT_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_PACKAGE_ROOT


@lru_cache(maxsize=8)
def _manifest_mapping(package_root: Path) -> dict[Path, PurePosixPath]:
    manifest_path = package_root / "MANIFEST.json"
    try:
        document: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExternalCaptureError(
            f"external-capture manifest is unavailable or invalid: {manifest_path}"
        ) from error

    if not isinstance(document, dict) or not isinstance(document.get("items"), list):
        raise ExternalCaptureError(
            f"external-capture manifest has no item list: {manifest_path}"
        )

    mapping: dict[Path, PurePosixPath] = {}
    for item in document["items"]:
        if not isinstance(item, dict):
            raise ExternalCaptureError(
                f"external-capture manifest contains a non-object item: {manifest_path}"
            )
        original_raw = item.get("original_absolute_path")
        relative_raw = item.get("payload_relative_path")
        if not isinstance(original_raw, str) or not isinstance(relative_raw, str):
            raise ExternalCaptureError(
                f"external-capture manifest item lacks path fields: {manifest_path}"
            )
        original = Path(original_raw)
        relative = PurePosixPath(relative_raw)
        if not original.is_absolute():
            raise ExternalCaptureError(
                f"external-capture origin is not absolute: {original_raw!r}"
            )
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.parts[0] != "payload"
            or ".." in relative.parts
        ):
            raise ExternalCaptureError(
                f"external-capture payload path is unsafe: {relative_raw!r}"
            )
        if original in mapping:
            raise ExternalCaptureError(
                f"external-capture origin is duplicated: {original}"
            )
        mapping[original] = relative
    return mapping


def resolve_external_capture(
    *historical_paths: str | Path,
    package_root: str | Path | None = None,
) -> Path:
    """Resolve one of ``historical_paths`` to live or packaged evidence.

    Existing historical paths win so an original capture remains reproducible
    in place. Otherwise, the first path represented by the package manifest is
    mapped below ``payload/``. Historical path objects and strings remain
    unchanged for provenance; callers should use only this return value for I/O.
    """

    if not historical_paths:
        raise ValueError("at least one historical capture path is required")

    candidates = tuple(Path(path).expanduser() for path in historical_paths)
    for candidate in candidates:
        if ".." in candidate.parts:
            raise ExternalCaptureError(
                f"historical capture path contains traversal: {candidate}"
            )
        if candidate.exists() or candidate.is_symlink():
            return candidate

    root = (
        Path(package_root).expanduser()
        if package_root is not None
        else external_capture_package_root()
    )
    mapping = _manifest_mapping(root)
    mapped_missing: list[Path] = []
    ordered_roots = sorted(mapping, key=lambda value: len(value.parts), reverse=True)
    for candidate in candidates:
        for original_root in ordered_roots:
            try:
                suffix = candidate.relative_to(original_root)
            except ValueError:
                continue
            if ".." in suffix.parts:
                raise ExternalCaptureError(
                    f"historical capture suffix contains traversal: {candidate}"
                )
            resolved = root.joinpath(*mapping[original_root].parts, *suffix.parts)
            if resolved.exists() or resolved.is_symlink():
                return resolved
            mapped_missing.append(resolved)
            break

    if mapped_missing:
        locations = ", ".join(str(path) for path in mapped_missing)
        raise ExternalCaptureError(
            f"packaged external capture is missing: {locations}"
        )
    origins = ", ".join(str(path) for path in candidates)
    raise ExternalCaptureError(
        f"historical capture is absent and not declared by the package: {origins}"
    )
