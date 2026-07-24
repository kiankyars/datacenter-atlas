#!/usr/bin/env python3
"""Create or validate a sealed, bounded satellite-batch recovery artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from datacenter_atlas.satellite_batch_recovery import (
    RecoveryIncident,
    recover_satellite_batch,
    validate_recovered_satellite_batch,
)


RECOVERY_DEFINITION_FORMAT = (
    "datacenter-atlas-satellite-batch-recovery-definition-v3"
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--queue-dir", type=Path, required=True)
    result.add_argument("--base-dir", type=Path, required=True)
    result.add_argument("--source-evidence-dir", type=Path)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--validate-only", action="store_true")
    result.add_argument(
        "--definition",
        type=Path,
        help="canonical recovery definition JSON (required in create mode)",
    )
    return result


def _required(arguments: argparse.Namespace, *names: str) -> None:
    missing = [name for name in names if getattr(arguments, name) is None]
    if missing:
        raise SystemExit(
            "create mode requires: " + ", ".join("--" + name.replace("_", "-") for name in missing)
        )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        manifest = validate_recovered_satellite_batch(
            arguments.queue_dir,
            arguments.base_dir,
            arguments.output_dir,
            source_evidence_directory=arguments.source_evidence_dir,
        )
    else:
        _required(arguments, "source_evidence_dir", "definition")
        definition_raw = arguments.definition.read_bytes()
        try:
            definition = json.loads(definition_raw)
        except json.JSONDecodeError as error:
            raise SystemExit("recovery definition is not valid JSON") from error
        canonical_definition = (
            json.dumps(definition, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        expected_keys = {
            "format",
            "artifact_id",
            "base_artifact_id",
            "source_evidence_artifact_id",
            "position_start",
            "position_end",
            "recovered_at",
            "source_manifest_pin",
            "incident",
        }
        if (
            not isinstance(definition, dict)
            or definition_raw != canonical_definition
            or set(definition) != expected_keys
            or definition.get("format") != RECOVERY_DEFINITION_FORMAT
        ):
            raise SystemExit("recovery definition has an invalid schema")
        incident = definition["incident"]
        if not isinstance(incident, dict) or set(incident) != {
            "handling",
            "interrupted_checkpoint_observation",
            "launchd_service_observations",
            "observed_writer_pids",
            "reported_guard_pid",
        }:
            raise SystemExit("recovery definition incident has an invalid schema")
        manifest = recover_satellite_batch(
            arguments.queue_dir,
            arguments.base_dir,
            arguments.source_evidence_dir,
            arguments.output_dir,
            artifact_id=definition["artifact_id"],
            base_artifact_id=definition["base_artifact_id"],
            source_evidence_artifact_id=definition[
                "source_evidence_artifact_id"
            ],
            position_start=definition["position_start"],
            position_end=definition["position_end"],
            recovered_at=definition["recovered_at"],
            incident=RecoveryIncident(
                observed_writer_pids=incident["observed_writer_pids"],
                launchd_service_observations=incident[
                    "launchd_service_observations"
                ],
                reported_guard_pid=incident.get("reported_guard_pid"),
                handling=incident["handling"],
                interrupted_checkpoint_observation=incident[
                    "interrupted_checkpoint_observation"
                ],
            ),
            source_manifest_pin=definition["source_manifest_pin"],
        )
    print(
        json.dumps(
            {
                "artifact_id": manifest["artifact_id"],
                "state": manifest["state"],
                "selection": manifest["selection"],
                "output": manifest["output"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
