#!/usr/bin/env python3
"""Run a bounded, resumable catalog-only satellite-review batch."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
from typing import Iterator, Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_batch import (
    BATCH_MANIFEST_FILENAME,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
    BatchConfig,
    execute_satellite_queue,
)
from datacenter_atlas.satellite_queue import PRIORITY_POLICY


PRIORITY_TIERS = [str(item["tier"]) for item in PRIORITY_POLICY]


class SatelliteRunnerLockError(RuntimeError):
    """Raised when the process cannot establish exclusive runner ownership."""


def _validated_lock_path(
    lock_file: Path, output_directory: Path, queue_directory: Path
) -> Path:
    try:
        path = Path(os.path.abspath(os.fspath(lock_file))).resolve(strict=False)
        output = Path(os.path.abspath(os.fspath(output_directory))).resolve(
            strict=False
        )
        queue = Path(os.path.abspath(os.fspath(queue_directory))).resolve(
            strict=False
        )
    except (OSError, RuntimeError) as error:
        raise SatelliteRunnerLockError(
            "runner lock, output, or queue path could not be resolved safely"
        ) from error
    if (
        path == output
        or output in path.parents
        or path == queue
        or queue in path.parents
    ):
        raise SatelliteRunnerLockError(
            "runner lock file must be outside the batch output and queue directories"
        )
    try:
        canonical = output.with_name(f"{output.name}.lock").resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise SatelliteRunnerLockError(
            "canonical runner lock path could not be derived from batch output"
        ) from error
    if path != canonical:
        raise SatelliteRunnerLockError(
            f"runner lock file must equal the canonical output sibling: {canonical}"
        )
    return path


@contextmanager
def _single_writer_lock(lock_file: Path) -> Iterator[None]:
    """Hold a crash-releasing, non-blocking advisory lock for one full run."""
    path = Path(os.path.abspath(os.fspath(lock_file)))
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise SatelliteRunnerLockError(
            f"runner lock file could not be opened safely: {path}"
        ) from error

    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SatelliteRunnerLockError(
                f"runner lock path is not a regular file: {path}"
            )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise SatelliteRunnerLockError(
                    f"runner lock could not be acquired: {path}"
                ) from error
            raise SatelliteRunnerLockError(
                f"another satellite review queue runner holds lock: {path}"
            ) from error
        descriptor_stat = os.fstat(descriptor)
        try:
            path_stat = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise SatelliteRunnerLockError(
                f"runner lock path changed while acquiring ownership: {path}"
            ) from error
        if (descriptor_stat.st_dev, descriptor_stat.st_ino) != (
            path_stat.st_dev,
            path_stat.st_ino,
        ):
            raise SatelliteRunnerLockError(
                f"runner lock path changed while acquiring ownership: {path}"
            )
        yield
    finally:
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--queue-dir", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument(
        "--lock-file",
        required=True,
        type=Path,
        help=(
            "Persistent regular file used for a non-blocking single-writer lock; "
            "the file is never unlinked by the runner"
        ),
    )
    result.add_argument(
        "--priority-tier",
        action="append",
        choices=PRIORITY_TIERS,
        help="Run only this tier; repeat to select multiple tiers (default: all)",
    )
    result.add_argument("--max-jobs", type=int, default=25)
    result.add_argument("--max-http-attempts", type=int, default=50)
    result.add_argument("--max-job-attempts", type=int, default=3)
    result.add_argument("--catalog-retries", type=int, default=0)
    result.add_argument("--timeout-seconds", type=float, default=60.0)
    result.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=DEFAULT_MINIMUM_INTERVAL_SECONDS,
    )
    result.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        lock_file = _validated_lock_path(
            arguments.lock_file, arguments.output_dir, arguments.queue_dir
        )
        with _single_writer_lock(lock_file):
            config = BatchConfig(
                priority_tiers=arguments.priority_tier,
                user_agent=arguments.user_agent,
                minimum_interval_seconds=arguments.minimum_interval_seconds,
                timeout_seconds=arguments.timeout_seconds,
                catalog_retries=arguments.catalog_retries,
                max_job_attempts=arguments.max_job_attempts,
                max_response_bytes=arguments.max_response_bytes,
            )
            manifest = execute_satellite_queue(
                arguments.queue_dir,
                arguments.output_dir,
                config=config,
                max_jobs=arguments.max_jobs,
                max_http_attempts=arguments.max_http_attempts,
            )
            print(
                json.dumps(
                    {
                        "manifest": str(
                            (arguments.output_dir / BATCH_MANIFEST_FILENAME).resolve()
                        ),
                        "state": manifest["state"],
                        "summary": manifest["summary"],
                        "last_run": manifest["last_run"],
                        "scope": manifest["scope"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
    except SatelliteRunnerLockError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
