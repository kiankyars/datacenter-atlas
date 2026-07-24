#!/usr/bin/env python3
"""Build a deterministic open-seed release from offline Epoch and curated inputs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
from typing import Sequence


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.epoch import EpochAIAdapter
from datacenter_atlas.publication_release import write_release
from datacenter_atlas.service import summarize, validate_database


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--epoch-input", required=True, type=Path)
    result.add_argument("--epoch-map", type=Path)
    result.add_argument("--epoch-retrieved-at", required=True)
    result.add_argument("--curated-dir", required=True, type=Path)
    result.add_argument("--curated-pattern", default="curated-official-*.json")
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--as-of", required=True)
    result.add_argument("--recorded-at", required=True)
    result.add_argument(
        "--publication-contract-version",
        choices=(1, 2, 3, 4),
        default=2,
        type=int,
        help="bundled documentation and attribution contract (default: 2)",
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.output_dir.exists() or arguments.output_dir.is_symlink():
        raise SystemExit("output directory already exists; refusing to overwrite")
    curated_paths = sorted(arguments.curated_dir.glob(arguments.curated_pattern))
    if not curated_paths:
        raise SystemExit("no curated input files matched")

    with tempfile.TemporaryDirectory(prefix="datacenter-atlas-build-") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        try:
            epoch_result = EpochAIAdapter().import_file(
                connection,
                arguments.epoch_input,
                map_html=arguments.epoch_map,
                retrieved_at=arguments.epoch_retrieved_at,
                as_of_date=arguments.as_of,
            )
            curated_results = []
            for path in curated_paths:
                document = json.loads(path.read_text(encoding="utf-8"))
                timestamps = {
                    evidence["retrieved_at"] for evidence in document.get("evidence", [])
                }
                if len(timestamps) != 1:
                    raise ValueError(
                        f"{path} must contain one shared evidence retrieved_at timestamp"
                    )
                import_result = CuratedOfficialSourceAdapter().import_file(
                    connection,
                    path,
                    retrieved_at=next(iter(timestamps)),
                )
                curated_results.append({"path": str(path), "result": asdict(import_result)})
            errors = validate_database(connection)
            if errors:
                raise ValueError("database validation failed: " + "; ".join(errors))
            release = write_release(
                connection,
                arguments.output_dir,
                as_of=arguments.as_of,
                recorded_at=arguments.recorded_at,
                publication_contract_version=arguments.publication_contract_version,
            )
            summary = summarize(
                connection,
                as_of=arguments.as_of,
                recorded_at=arguments.recorded_at,
            )
        finally:
            connection.close()

    print(
        json.dumps(
            {
                "curated": curated_results,
                "epoch": asdict(epoch_result),
                "release": release,
                "summary": summary,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
