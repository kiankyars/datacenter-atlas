#!/usr/bin/env python3
"""Run the immutable eleven-job open-seed v71 catalog selection."""

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
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MINIMUM_INTERVAL_SECONDS,
    DEFAULT_USER_AGENT,
)
from datacenter_atlas.satellite_batch_explicit_v1 import (
    DEFAULT_MAX_HTTP_ATTEMPTS,
    DEFAULT_MAX_JOBS,
    ExplicitBatchConfig,
    execute_explicit_satellite_batch_v1,
)
from datacenter_atlas.satellite_queue_v71 import QUEUE


class ExplicitRunnerLockError(RuntimeError):
    """Raised when exclusive runner ownership cannot be established."""


@contextmanager
def _single_writer_lock(output: Path) -> Iterator[None]:
    lock = output.with_name(f"{output.name}.lock")
    if lock.is_symlink():
        raise ExplicitRunnerLockError("explicit runner lock may not be a symlink")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock, flags, 0o600)
    locked = False
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ExplicitRunnerLockError("explicit runner lock is not a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise ExplicitRunnerLockError(
                f"another explicit satellite runner holds {lock}"
            ) from error
        opened = os.fstat(descriptor)
        current = os.stat(lock, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ExplicitRunnerLockError("explicit runner lock changed during open")
        yield
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--queue-dir", type=Path, default=QUEUE)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS)
    result.add_argument(
        "--max-http-attempts", type=int, default=DEFAULT_MAX_HTTP_ATTEMPTS
    )
    result.add_argument("--timeout-seconds", type=float, default=60.0)
    result.add_argument(
        "--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES
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
    config = ExplicitBatchConfig(
        user_agent=arguments.user_agent,
        minimum_interval_seconds=arguments.minimum_interval_seconds,
        timeout_seconds=arguments.timeout_seconds,
        max_response_bytes=arguments.max_response_bytes,
    )
    try:
        with _single_writer_lock(arguments.output_dir.resolve(strict=False)):
            manifest = execute_explicit_satellite_batch_v1(
                arguments.queue_dir,
                arguments.output_dir,
                config=config,
                max_jobs=arguments.max_jobs,
                max_http_attempts=arguments.max_http_attempts,
            )
    except ExplicitRunnerLockError as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            {
                "manifest": str(
                    (arguments.output_dir / "batch-manifest.json").resolve()
                ),
                "state": manifest["state"],
                "summary": manifest["summary"],
                "lifetime_budget": manifest["lifetime_budget"],
                "last_run": manifest["last_run"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
