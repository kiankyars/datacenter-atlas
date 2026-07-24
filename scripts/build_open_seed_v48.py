#!/usr/bin/env python3
"""Build the collision-isolated open-seed v48 successor exactly once."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.epoch import EpochAIAdapter
from datacenter_atlas.publication_release import write_release
from datacenter_atlas.service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v46.json"
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v48.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v48"

BASE_DEFINITION_SHA256 = (
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293"
)
BASE_MANIFEST_SHA256 = (
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
)
RECORDED_AT = "2026-07-20T11:00:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T09:25:15Z"

ADDITIONS = {
    "sources/curated-official-2026-07-20-alto-sp01-granada.json": (
        "5e2f4e431b877d403d3f34d1d5de689450cfa58d1670c9e8b038f39f21d5cc80"
    ),
    "sources/curated-official-2026-07-20-digipower-columbiana-shell-v2.json": (
        "a137bd6356ead2052ad160aa50c7ab27d7871f4b2552dba276ffa86949f46ccd"
    ),
    "sources/curated-official-2026-07-20-galaxy-helios-phase2.json": (
        "5463da008a588bb9993310ee13ca82da039435cf5f3815c574d3ac0ee576f57f"
    ),
    "sources/curated-official-2026-07-20-hut8-beacon-point.json": (
        "b6209a4c9ebaefe562b541834c9d89a19482cfd79a4cf7de156df848ed7834f1"
    ),
    "sources/curated-official-2026-07-20-kasi-los1-commissioning.json": (
        "caaddbfbc641c00c87c7b7fcfb29c5f2af5df8f7ca541dcff6d94294e42afd01"
    ),
}

EXPECTED_RELEASE_FACTS = {
    "capacity_estimates": 456,
    "construction_pipeline_records": 322,
    "construction_source_signals": 228,
    "entities": 613,
    "entities_by_kind": {"campus": 329, "project": 284},
    "evidence_records": 336,
    "resolution_candidates": 4,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(document: object) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def main() -> int:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise SystemExit(f"definition already exists; refusing to overwrite: {DEFINITION}")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise SystemExit(f"release already exists; refusing to overwrite: {RELEASE}")
    if sha256(BASE_DEFINITION) != BASE_DEFINITION_SHA256:
        raise SystemExit("accepted v46 definition hash differs")
    base_manifest = ROOT / "releases/2026-07-20-open-seed-v46/manifest.json"
    if sha256(base_manifest) != BASE_MANIFEST_SHA256:
        raise SystemExit("accepted v46 manifest hash differs")

    base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
    base_pins = {row["path"]: row["sha256"] for row in base["curated_inputs"]}
    if len(base_pins) != 287:
        raise SystemExit(f"expected 287 v46 inputs, found {len(base_pins)}")
    if set(base_pins) & set(ADDITIONS):
        raise SystemExit("one or more v48 additions already occurs in v46")

    pins = base_pins | ADDITIONS
    if len(pins) != 292:
        raise SystemExit(f"expected 292 v48 inputs, found {len(pins)}")
    paths = sorted(pins)
    if sum("/curated-official-2026-07-20-goodman-" in path and not path.endswith("-v2.json") for path in paths) != 10:
        raise SystemExit("v48 must retain exactly ten Goodman v1 inputs")
    if sum("/curated-official-2026-07-20-vnet-" in path and not path.endswith("-v2.json") for path in paths) != 8:
        raise SystemExit("v48 must retain exactly eight VNET v1 inputs")
    forbidden = [
        path
        for path in paths
        if path.endswith("-v2.json")
        and ("/curated-official-2026-07-20-goodman-" in path or "/curated-official-2026-07-20-vnet-" in path)
    ]
    forbidden.extend(path for path in paths if "stack-stafford" in path)
    forbidden.extend(
        path
        for path in paths
        if path == "sources/curated-official-2026-07-20-digipower-columbiana-shell.json"
    )
    if forbidden:
        raise SystemExit("forbidden fork inputs selected: " + ", ".join(forbidden))

    retrieved_at = [base["epoch_capture"]["retrieved_at"]]
    curated_paths: list[Path] = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {relative}")
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {relative}")
        if sha256(path) != pins[relative]:
            raise SystemExit(f"input hash differs: {relative}")
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {row["retrieved_at"] for row in document.get("evidence", [])}
        if len(timestamps) != 1:
            raise SystemExit(f"input must use one evidence retrieved_at: {relative}")
        retrieved_at.extend(timestamps)
        curated_paths.append(path)
    if max(retrieved_at) != MAX_SELECTED_RETRIEVED_AT:
        raise SystemExit(
            "selected retrieval maximum differs: "
            f"{max(retrieved_at)} != {MAX_SELECTED_RETRIEVED_AT}"
        )
    cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
    if not all(
        datetime.fromisoformat(value.replace("Z", "+00:00")) < cutoff
        for value in retrieved_at
    ):
        raise SystemExit("recorded_at must be strictly after every selected retrieval")
    if datetime.now(timezone.utc) >= cutoff:
        raise SystemExit("recorded_at must be strictly after the build-start clock")

    staging_root = ROOT / ".staging"
    staging_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="open-seed-v48-", dir=staging_root) as temporary:
        temporary_root = Path(temporary)
        connection, _ = initialize(temporary_root / "atlas.sqlite")
        try:
            epoch = base["epoch_capture"]
            epoch_result = EpochAIAdapter().import_file(
                connection,
                ROOT / epoch["archive"],
                map_html=ROOT / epoch["map"],
                retrieved_at=epoch["retrieved_at"],
                as_of_date="2026-07-20",
            )
            normalized_epoch = json.loads(json.dumps(asdict(epoch_result)))
            if normalized_epoch != base["expected_epoch_result"]:
                raise SystemExit("fresh Epoch import result differs from v46")
            for path in curated_paths:
                document = json.loads(path.read_text(encoding="utf-8"))
                timestamp = {row["retrieved_at"] for row in document["evidence"]}.pop()
                result = CuratedOfficialSourceAdapter().import_file(
                    connection, path, retrieved_at=timestamp
                )
                if result.warnings:
                    raise SystemExit(f"curated import warnings for {path.name}: {result.warnings}")
            errors = validate_database(connection)
            if errors:
                raise SystemExit("fresh database validation failed: " + "; ".join(errors))

            temporary_release = temporary_root / RELEASE.name
            write_release(
                connection,
                temporary_release,
                as_of="2026-07-20",
                recorded_at=RECORDED_AT,
                publication_contract_version=4,
            )
            summary = summarize(
                connection, as_of="2026-07-20", recorded_at=RECORDED_AT
            )
        finally:
            connection.close()

        manifest_path = temporary_release / "manifest.json"
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        actual = {key: manifest[key] for key in EXPECTED_RELEASE_FACTS}
        if actual != EXPECTED_RELEASE_FACTS:
            raise SystemExit(
                "fresh release projection differs; refusing to publish:\n"
                + json.dumps({"actual": actual, "expected": EXPECTED_RELEASE_FACTS}, indent=2, sort_keys=True)
            )
        if len(manifest["source_families"]) != 168:
            raise SystemExit(
                "fresh source-family count differs; refusing to publish: "
                f"{len(manifest['source_families'])} != 168"
            )
        if len(list(temporary_release.iterdir())) != 13:
            raise SystemExit("fresh release must contain exactly 13 files")

        expected_release = {key: value for key, value in manifest.items() if key != "files"}
        expected_release["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
        definition = dict(base)
        definition["build"] = {"as_of": "2026-07-20", "recorded_at": RECORDED_AT}
        definition["curated_inputs"] = [
            {"path": path, "sha256": pins[path]} for path in paths
        ]
        definition["expected_release"] = expected_release
        definition["expected_summary"] = {
            "entities_by_status": summary["entities_by_status"],
            "entities_total": summary["entities_total"],
            "evidence_total": summary["evidence_total"],
            "projects_total": summary["projects_total"],
        }
        definition["release_id"] = RELEASE.name

        temporary_definition = temporary_root / DEFINITION.name
        temporary_definition.write_bytes(canonical_json(definition))
        os.chmod(temporary_definition, 0o644)
        shutil.move(temporary_release, RELEASE)
        shutil.move(temporary_definition, DEFINITION)

    for path in RELEASE.iterdir():
        os.chmod(path, 0o444)
    os.chmod(RELEASE, 0o555)
    print(
        json.dumps(
            {
                "definition": str(DEFINITION),
                "definition_sha256": sha256(DEFINITION),
                "manifest_sha256": sha256(RELEASE / "manifest.json"),
                "recorded_at": RECORDED_AT,
                "release": str(RELEASE),
                **EXPECTED_RELEASE_FACTS,
                "source_families": 168,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
