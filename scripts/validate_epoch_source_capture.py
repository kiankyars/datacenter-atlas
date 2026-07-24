#!/usr/bin/env python3
"""Validate the bounded Epoch AI source capture without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.epoch_source_capture import MANIFEST_FILENAME, validate_epoch_source_capture


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("capture", type=Path)
    result.add_argument("--allow-mutable", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    manifest = validate_epoch_source_capture(
        arguments.capture, require_frozen=not arguments.allow_mutable
    )
    raw = (arguments.capture / MANIFEST_FILENAME).read_bytes()
    print(
        json.dumps(
            {
                "archive_files": len(manifest["archive_inventory"]),
                "data_center_rows": manifest["dataset_inventory"]["data_center_rows"],
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "mode": "offline_validate",
                "network_requests": 0,
                "timeline_rows": manifest["dataset_inventory"]["timeline_rows"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
