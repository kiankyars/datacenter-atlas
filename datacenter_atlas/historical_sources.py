"""Read frozen source provenance independently of the maintained Python package.

The archive contains original source bytes named by historical manifests. These
functions verify that historical evidence; they do not validate or execute the
current implementation. Dataset files are never stored in the source archive.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = Path(__file__).with_name("historical-sources.zip")
ARCHIVE_SHA256 = "755f14b0b677e07221687df841d84de0b4ca08a3b3d27876380db3146887303c"


class HistoricalSourceError(ValueError):
    """The frozen source archive does not match its integrity contract."""


@lru_cache(maxsize=1)
def _load_archive(identity: tuple[str, int, int, int, int]) -> dict[str, tuple[bytes, str]]:
    path = Path(identity[0])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise HistoricalSourceError("historical source archive SHA-256 mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            entries = manifest["files"]
            if manifest["format"] != 1 or set(archive.namelist()) != {"manifest.json", *entries}:
                raise HistoricalSourceError("historical source archive inventory mismatch")
            if len(archive.namelist()) != len(entries) + 1:
                raise HistoricalSourceError("historical source archive has duplicate entries")
            result = {}
            for name, expected in entries.items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py":
                    raise HistoricalSourceError("historical source archive contains a non-source path")
                source = archive.read(name)
                actual = {"bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()}
                if actual != {key: expected[key] for key in actual} or expected["mode"] not in {"0644", "0755"}:
                    raise HistoricalSourceError(f"historical source entry mismatch: {name}")
                result[name] = (source, expected["mode"])
            return result
    except (KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise HistoricalSourceError("invalid historical source archive") from error


def _archive() -> dict[str, tuple[bytes, str]]:
    metadata = ARCHIVE_PATH.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise HistoricalSourceError("historical source archive must be a regular file")
    return _load_archive((str(ARCHIVE_PATH), metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns))


def _source(path: str | Path, root: Path | None) -> tuple[Path, str | None]:
    base = ROOT if root is None else Path(root).absolute()
    target = Path(path)
    if not target.is_absolute():
        target = base / target
    if ".." in target.parts:
        raise ValueError("historical source paths must not contain '..'")
    try:
        relative = target.relative_to(base).as_posix()
    except ValueError:
        relative = None
    return target, relative


def is_archived_source(path: str | Path, *, root: Path | None = None) -> bool:
    """Whether this logical source path has an immutable historical snapshot."""
    _, relative = _source(path, root)
    return relative is not None and relative in _archive()


def read_source_bytes(path: str | Path, *, root: Path | None = None) -> bytes:
    """Read historical source bytes, or an unarchived ordinary source file.

    Use only for source-provenance checks. A snapshot deliberately remains
    independent of subsequent edits to the executable implementation.
    """
    target, relative = _source(path, root)
    archived = _archive().get(relative)
    if archived is not None:
        return archived[0]
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(f"source is not a regular file: {target}")
    return target.read_bytes()


def source_fingerprint(
    path: str | Path, *, root: Path | None = None, include_mode: bool = False
) -> dict[str, int | str]:
    """Fingerprint historical source bytes while retaining their original mode."""
    target, relative = _source(path, root)
    raw = read_source_bytes(path, root=root)
    result: dict[str, int | str] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if include_mode:
        archived = _archive().get(relative)
        result["mode"] = archived[1] if archived is not None else f"{stat.S_IMODE(target.stat().st_mode):04o}"
    return result
