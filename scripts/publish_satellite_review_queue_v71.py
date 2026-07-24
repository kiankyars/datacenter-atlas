#!/usr/bin/env python3
"""Publish the exact accepted open-seed v71 satellite-review queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_queue_v71 import (
    QUEUE,
    publish_satellite_queue_v71,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--generated-at",
        required=True,
        help="Canonical timezone-aware timestamp, still future when staging begins",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = publish_satellite_queue_v71(generated_at=arguments.generated_at)
    artifact = manifest["artifacts"]["satellite-review-queue.jsonl"]
    print(
        json.dumps(
            {
                "counts": manifest["counts"],
                "manifest": str((QUEUE / "manifest.json").resolve()),
                "queue": str((QUEUE / "satellite-review-queue.jsonl").resolve()),
                "queue_bytes": artifact["bytes"],
                "queue_sha256": artifact["sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
