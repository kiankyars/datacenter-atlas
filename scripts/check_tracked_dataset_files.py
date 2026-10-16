#!/usr/bin/env python3
"""Fail when a file that a dataset manifest lists is not tracked by Git.

A clean clone holds only tracked files and ``.gitignore`` is default-deny, so a manifest-listed
file that was never added (or that ``.gitignore`` hides) breaks every clean checkout: the site
build and the ``--validate-only`` reproductions then stop with a less obvious missing-file or
checksum error. This check names each such file and says how to fix it.

For every dataset directory under the versions root of ``site/config.json`` (a direct child with
a ``manifest.json``) it checks ``manifest.json``, ``manifest.sha256`` and every file listed in the
manifest's ``files``; for date-based updates also the definition (``input_path``) and the pinned
source files (``source_files[].path``) that ``scripts/build_dataset_update.py --validate-only``
reads. Standard library only; it needs ``git`` and a Git checkout.

Usage::

    python3 scripts/check_tracked_dataset_files.py [--root .]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TrackingError(RuntimeError):
    pass


def tracked_files(root: Path) -> set[str]:
    """Repository-relative POSIX paths of every file in the Git index of ``root``."""
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--full-name"],
                                capture_output=True, check=False)
    except OSError as error:
        raise TrackingError(f"cannot run git: {error}") from None
    if result.returncode:
        raise TrackingError(f"{root} is not a Git checkout: {result.stderr.decode('utf-8', 'replace').strip()}")
    return {name for name in result.stdout.decode("utf-8").split("\0") if name}


def _repository_path(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise TrackingError(f"{where}: expected a repository-relative path, got {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise TrackingError(f"{where}: unsafe path {value!r}")
    return path.as_posix()


def manifest_paths(root: Path, versions_root: str) -> dict[str, list[str]]:
    """Every repository path each dataset manifest needs, keyed by the manifest's path."""
    directory = root / versions_root
    if not directory.is_dir():
        raise TrackingError(f"versions root {directory} is not a directory")
    needed: dict[str, list[str]] = {}
    for manifest_path in sorted(directory.glob("*/manifest.json")):
        dataset = manifest_path.parent.relative_to(root).as_posix()
        where = f"{dataset}/manifest.json"
        try:
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, ValueError) as error:
            raise TrackingError(f"{where}: unreadable manifest: {error}") from None
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, dict):
            raise TrackingError(f"{where}: 'files' must be an object")
        paths = [f"{dataset}/manifest.json", f"{dataset}/manifest.sha256"]
        for name in sorted(files):
            if not isinstance(name, str) or "/" in name or name in {"", ".", ".."}:
                raise TrackingError(f"{where}: unsafe file name {name!r}")
            paths.append(f"{dataset}/{name}")
        if manifest.get("format") == "datacenter-atlas-update-v1":
            paths.append(_repository_path(manifest.get("input_path"), f"{where} input_path"))
            for index, item in enumerate(manifest.get("source_files") or []):
                path = item.get("path") if isinstance(item, dict) else None
                paths.append(_repository_path(path, f"{where} source_files[{index}]"))
        needed[where] = paths
    if not needed:
        raise TrackingError(f"no dataset manifests found under {directory}")
    return needed


def untracked_manifest_files(root: Path, versions_root: str | None = None) -> list[str]:
    """One message per manifest-listed path that Git does not track (empty when all are)."""
    if versions_root is None:
        config = json.loads((root / "site" / "config.json").read_text(encoding="utf-8"))
        versions_root = config["versions_root"]
    tracked = tracked_files(root)
    problems = []
    for manifest, paths in manifest_paths(root, versions_root).items():
        for path in paths:
            if path not in tracked:
                problems.append(f"{path} (listed by {manifest}) is not tracked by Git")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)
    try:
        problems = untracked_manifest_files(args.root.resolve())
    except (TrackingError, OSError, ValueError, KeyError) as error:
        print(f"check_tracked_dataset_files: {error}", file=sys.stderr)
        return 1
    if problems:
        print(f"{len(problems)} manifest-listed file(s) are missing from Git, so a clean clone cannot "
              "build or validate the data:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        print("Add a .gitignore allow rule if the name is new, then `git add` the file.", file=sys.stderr)
        return 1
    print("Every manifest-listed dataset file is tracked by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
