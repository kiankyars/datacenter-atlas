#!/usr/bin/env python3
"""Build an immutable index of separately licensed atlas releases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.federated_release import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    write_federated_release_index,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--definition",
        required=True,
        type=Path,
        help="Hash-pinned federation definition JSON",
    )
    result.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New immutable federation output directory",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    index = write_federated_release_index(
        arguments.definition, arguments.output_dir
    )
    print(
        json.dumps(
            {
                "index": str((arguments.output_dir / INDEX_FILENAME).resolve()),
                "manifest": str(
                    (arguments.output_dir / MANIFEST_FILENAME).resolve()
                ),
                "manifest_sha256": str(
                    (arguments.output_dir / MANIFEST_HASH_FILENAME).resolve()
                ),
                "counts": index["counts"],
                "release_ids": [
                    release["release_id"] for release in index["releases"]
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
