#!/usr/bin/env python3
"""Publish the immutable explicit-v1 catalog copy and change disposition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_change_explicit_v1_disposition import (
    publish_all,
    suggested_publication_times,
)


def parser() -> argparse.ArgumentParser:
    suggested_catalog, suggested_disposition = suggested_publication_times()
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--catalog-finalized-at", default=suggested_catalog)
    result.add_argument("--disposition-generated-at", default=suggested_disposition)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    result = publish_all(
        arguments.catalog_finalized_at,
        arguments.disposition_generated_at,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
