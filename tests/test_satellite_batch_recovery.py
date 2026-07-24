from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import datacenter_atlas.satellite_batch_recovery as recovery_module
from datacenter_atlas.satellite_batch import (
    BATCH_MANIFEST_FILENAME,
    PRIOR_BATCH_SCHEMA_VERSION,
    BatchConfig,
    _manifest_raw,
    execute_satellite_queue,
)
from datacenter_atlas.satellite_batch_recovery import (
    RECOVERY_MANIFEST_FILENAME,
    RECOVERY_MANIFEST_HASH_FILENAME,
    RECOVERY_SCOPE,
    RecoveryIncident,
    SatelliteBatchRecoveryError,
    recover_satellite_batch,
    validate_recovered_satellite_batch,
)
from datacenter_atlas.satellite_catalog import (
    CatalogQuery,
    Provider,
    build_pair_manifest,
    manifest_json,
)
from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    QueueConfig,
    build_queue_bundle,
)


def _feature(index: int) -> dict:
    entity_id = f"fixture-{index}"
    return {
        "type": "Feature",
        "id": entity_id,
        "geometry": None,
        "properties": {
            "entity_id": entity_id,
            "entity_kind": "facility",
            "stable_key": entity_id,
            "name": f"Site {index}",
            "latitude": 38.9 + index / 100,
            "longitude": -77.0,
            "status": "unknown",
            "status_as_of": "2026-07-01",
            "snapshot_evidence_id": f"snapshot-{index}",
            "status_evidence_id": f"status-{index}",
            "source_family": "fixture",
            "source_url": f"https://example.test/{index}",
            "source_license": "CC0-1.0",
            "country": "United States",
            "country_iso_a2": "US",
            "country_iso_a3": "USA",
        },
    }


def _queue(path: Path, count: int = 6) -> None:
    atlas = (
        json.dumps(
            {
                "type": "FeatureCollection",
                "atlas_as_of": "2026-07-18",
                "atlas_recorded_at": "2026-07-18T20:00:00Z",
                "attribution": ["Fixture"],
                "features": [_feature(index) for index in range(count)],
            }
        )
        + "\n"
    ).encode()
    bundle = build_queue_bundle(
        atlas,
        source_name="atlas.geojson",
        generated_at="2026-07-18T21:00:00Z",
        config=QueueConfig(
            baseline_target="2024-06-15",
            current_target="2026-06-15",
            query_window_days=30,
            aoi_half_side_km=2,
        ),
    )
    path.mkdir()
    (path / QUEUE_FILENAME).write_bytes(bundle.queue_bytes)
    (path / MANIFEST_FILENAME).write_bytes(bundle.manifest_bytes)
    (path / MANIFEST_HASH_FILENAME).write_bytes(bundle.manifest_hash_bytes)


def _item(item_id: str, timestamp: str, bbox: tuple[float, ...]) -> dict:
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "bbox": list(bbox),
        "properties": {
            "datetime": timestamp,
            "eo:cloud_cover": 1,
            "grid:code": "MGRS-18SUJ",
        },
        "assets": {
            band: {"href": f"https://example.test/{item_id}/{band}.tif"}
            for band in ("B02", "B03", "B04", "B08", "B11", "SCL")
        },
    }


def _arguments(command: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    values = command[2:]
    index = 0
    while index < len(values):
        flag = values[index]
        if flag.startswith("--") and "=" in flag:
            name, value = flag.split("=", 1)
            result[name] = value
            index += 1
        else:
            result[flag] = values[index + 1]
            index += 2
    return result


class _CatalogRunner:
    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        arguments = _arguments(command)
        output = Path(arguments["--output-dir"])
        output.mkdir(parents=True)
        bbox = tuple(float(value) for value in arguments["--bbox"].split(","))
        baseline_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _item(
                        f"baseline-{output.parent.name}",
                        f"{arguments['--baseline-target']}T12:00:00Z",
                        bbox,
                    )
                ],
            }
        ).encode()
        current_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _item(
                        f"current-{output.parent.name}",
                        f"{arguments['--current-target']}T12:00:00Z",
                        bbox,
                    )
                ],
            }
        ).encode()
        provider = Provider(arguments["--provider"])
        baseline_query = CatalogQuery(
            bbox,
            arguments["--baseline-start"],
            arguments["--baseline-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        current_query = CatalogQuery(
            bbox,
            arguments["--current-start"],
            arguments["--current-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        manifest = build_pair_manifest(
            provider,
            baseline_query,
            baseline_raw,
            current_query,
            current_raw,
            baseline_date=arguments["--baseline-target"],
            current_date=arguments["--current-target"],
            retrieved_at="2026-07-19T21:00:00Z",
            temporal_window_days=int(arguments["--temporal-window-days"]),
        )
        (output / "baseline-response.json").write_bytes(baseline_raw)
        (output / "current-response.json").write_bytes(current_raw)
        (output / "manifest.json").write_text(manifest_json(manifest), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "ok", "")


class _Clock:
    def __init__(self, start: str) -> None:
        self.value = datetime.fromisoformat(start.replace("Z", "+00:00"))

    def __call__(self) -> str:
        result = self.value.astimezone(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        self.value += timedelta(seconds=1)
        return result


def _freeze(root: Path) -> None:
    files: list[Path] = []
    directories: list[Path] = []
    for parent, names, filenames in os.walk(root):
        directories.append(Path(parent))
        files.extend(Path(parent) / name for name in filenames)
        directories.extend(Path(parent) / name for name in names)
    for path in files:
        path.chmod(0o444)
    for path in sorted(set(directories), key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555)


def _thaw(root: Path) -> None:
    for parent, names, filenames in os.walk(root):
        Path(parent).chmod(0o755)
        for name in names:
            (Path(parent) / name).chmod(0o755)
        for name in filenames:
            (Path(parent) / name).chmod(0o644)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tree_metadata(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in [root, *sorted(root.rglob("*"))]:
        metadata = path.stat(follow_symlinks=False)
        row: dict[str, object] = {
            "path": "." if path == root else path.relative_to(root).as_posix(),
            "kind": "directory" if path.is_dir() else "file",
            "mode": stat.S_IMODE(metadata.st_mode),
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "mtime_ns": metadata.st_mtime_ns,
        }
        if path.is_file():
            raw = path.read_bytes()
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        rows.append(row)
    return rows


def _resign_recovery_manifest(
    output: Path, mutate: Callable[[dict], None]
) -> None:
    _thaw(output)
    manifest_path = output / RECOVERY_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    (output / RECOVERY_MANIFEST_HASH_FILENAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {RECOVERY_MANIFEST_FILENAME}\n",
        encoding="ascii",
    )
    _freeze(output)


def _incident() -> RecoveryIncident:
    return RecoveryIncident(
        observed_writer_pids=[101, 202],
        launchd_service_observations=[
            {"label": "fixture.launchd.service", "status": "booted out"}
        ],
        reported_guard_pid=303,
        interrupted_checkpoint_observation={
            "manifest_sha256": "a" * 64,
            "manifest_bytes": 1234,
            "updated_at": "2026-07-19T22:55:34Z",
            "summary": {
                "jobs_selected": 6,
                "jobs_completed": 3,
                "jobs_failed": 0,
                "jobs_pending": 3,
                "jobs_unavailable_no_scene": 0,
            },
            "last_run": {
                "started_at": "2026-07-19T22:52:27Z",
                "finished_at": None,
                "max_jobs": 147,
                "max_http_attempts": 294,
                "job_attempts": 3,
                "http_attempts_reserved": 6,
                "jobs_completed": 2,
                "jobs_failed": 0,
                "jobs_unavailable_no_scene": 0,
                "budget_exhausted": False,
            },
        },
    )


def _pin(path: Path) -> dict[str, int | str]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "mtime_ns": path.stat().st_mtime_ns,
    }


def _fixture(root: Path) -> tuple[Path, Path, Path, dict[str, int | str]]:
    queue = root / "queue"
    base = root / "base"
    source = root / "source"
    _queue(queue)
    config = BatchConfig(priority_tiers=["unknown"], minimum_interval_seconds=0.1)
    execute_satellite_queue(
        queue,
        base,
        config=config,
        max_jobs=1,
        max_http_attempts=2,
        command_runner=_CatalogRunner(),
        sleep=lambda _: None,
        timestamp=_Clock("2026-07-19T20:00:00Z"),
    )
    manifest_path = base / BATCH_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = PRIOR_BATCH_SCHEMA_VERSION
    manifest["configuration"].pop("max_response_bytes")
    manifest.pop("response_limit_migration")
    manifest_path.write_bytes(_manifest_raw(manifest))
    shutil.copytree(base, source)
    _freeze(base)
    execute_satellite_queue(
        queue,
        source,
        config=config,
        max_jobs=4,
        max_http_attempts=8,
        command_runner=_CatalogRunner(),
        sleep=lambda _: None,
        timestamp=_Clock("2026-07-19T22:00:00Z"),
    )
    return queue, base, source, _pin(source / BATCH_MANIFEST_FILENAME)


def _recover(
    queue: Path,
    base: Path,
    source: Path,
    output: Path,
    source_pin: dict[str, int | str],
) -> dict:
    return recover_satellite_batch(
        queue,
        base,
        source,
        output,
        artifact_id=output.name,
        base_artifact_id=base.name,
        source_evidence_artifact_id=source.name,
        position_start=2,
        position_end=3,
        recovered_at="2026-07-19T23:00:00Z",
        incident=_incident(),
        source_manifest_pin=source_pin,
    )


class SatelliteBatchRecoveryTests(unittest.TestCase):
    def test_exact_delta_is_sealed_review_only_and_reproduces_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            base_before = _tree_hashes(base)
            source_before = _tree_hashes(source)
            first_parent = root / "first-parent"
            first_parent.mkdir()
            first = first_parent / "recovered"
            manifest = _recover(queue, base, source, first, source_pin)

            self.assertEqual(_tree_hashes(base), base_before)
            self.assertEqual(_tree_hashes(source), source_before)
            self.assertEqual(manifest["scope"], RECOVERY_SCOPE)
            self.assertEqual(manifest["artifact_id"], first.name)
            self.assertEqual(manifest["base"]["artifact_id"], base.name)
            self.assertEqual(manifest["source_evidence"]["artifact_id"], source.name)
            self.assertEqual(
                manifest["source_evidence"]["source_directory_name"], source.name
            )
            self.assertEqual(manifest["selection"]["jobs"], 2)
            self.assertEqual(manifest["reconciliation"]["later_job_leakage"], 0)
            self.assertIsNone(manifest["reconciliation"]["batch_last_run"])
            self.assertTrue(manifest["source_evidence"]["snapshot_last_run_finished"])
            batch = json.loads((first / "batch" / BATCH_MANIFEST_FILENAME).read_text())
            self.assertEqual(batch["updated_at"], manifest["recovered_at"])
            self.assertEqual(
                batch["response_limit_migration"]["migrated_at"],
                manifest["recovered_at"],
            )
            self.assertEqual(
                batch["response_limit_migration"][
                    "enforced_for_subsequent_attempts_at_or_after"
                ],
                manifest["recovered_at"],
            )
            by_position = {
                task["queue_position"]: task for task in batch["jobs"].values()
            }
            self.assertEqual(by_position[2]["state"], "completed")
            self.assertEqual(by_position[3]["state"], "completed")
            self.assertEqual(by_position[4]["state"], "pending")
            self.assertEqual(by_position[5]["state"], "pending")
            for position in (4, 5):
                self.assertFalse(
                    (first / "batch" / by_position[position]["output_directory"]).exists()
                )
            offline = validate_recovered_satellite_batch(queue, base, first)
            self.assertEqual(offline, manifest)

            second_parent = root / "second-parent"
            second_parent.mkdir()
            second = second_parent / "recovered"
            _recover(queue, base, source, second, source_pin)
            self.assertEqual(_tree_hashes(first), _tree_hashes(second))

    def test_creation_rejects_directory_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            output = root / "recovered"
            valid = {
                "artifact_id": output.name,
                "base_artifact_id": base.name,
                "source_evidence_artifact_id": source.name,
            }
            mutations = {
                "artifact_id": "fabricated-recovery",
                "base_artifact_id": "fabricated-base",
                "source_evidence_artifact_id": "fabricated-source",
            }
            for field, value in mutations.items():
                arguments = {**valid, field: value}
                with self.subTest(field=field), self.assertRaisesRegex(
                    SatelliteBatchRecoveryError, field
                ):
                    recover_satellite_batch(
                        queue,
                        base,
                        source,
                        output,
                        **arguments,
                        position_start=2,
                        position_end=3,
                        recovered_at="2026-07-19T23:00:00Z",
                        incident=_incident(),
                        source_manifest_pin=source_pin,
                    )
                self.assertFalse(output.exists())

    def test_later_catalog_directory_injection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            output = root / "recovered"
            _recover(queue, base, source, output, source_pin)
            tampered_parent = root / "tampered-parent"
            tampered_parent.mkdir()
            tampered = tampered_parent / output.name
            shutil.copytree(output, tampered)
            _thaw(tampered)
            source_manifest = json.loads(
                (source / BATCH_MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            leaked = next(
                task
                for task in source_manifest["jobs"].values()
                if task["queue_position"] == 4
            )
            source_catalog = source / leaked["output_directory"]
            destination = tampered / "batch" / leaked["output_directory"]
            destination.parent.mkdir(parents=True)
            shutil.copytree(source_catalog, destination)
            _freeze(tampered)
            with self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "later-job|unexpected catalog output"
            ):
                validate_recovered_satellite_batch(queue, base, tampered)

    def test_overlapping_later_timestamp_and_wrong_pin_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            wrong_pin = dict(source_pin)
            wrong_pin["sha256"] = "0" * 64
            with self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "post-guard pin"
            ):
                _recover(queue, base, source, root / "wrong-pin", wrong_pin)

            manifest_path = source / BATCH_MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            by_position = {
                task["queue_position"]: task for task in manifest["jobs"].values()
            }
            by_position[4]["completed_at"] = by_position[3]["completed_at"]
            manifest_path.write_bytes(_manifest_raw(manifest))
            with self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "not temporally distinguishable"
            ):
                _recover(
                    queue,
                    base,
                    source,
                    root / "overlap",
                    _pin(manifest_path),
                )

    def test_symlink_ancestor_output_is_rejected_without_source_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            (source / "existing-parent").mkdir()
            source_before = _tree_metadata(source)
            alias = root / "source-alias"
            alias.symlink_to(source, target_is_directory=True)
            output = alias / "existing-parent" / "recovered"

            with self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "symlink component"
            ):
                _recover(queue, base, source, output, source_pin)

            self.assertFalse((source / "existing-parent" / "recovered").exists())
            self.assertEqual(_tree_metadata(source), source_before)

    def test_unrelated_symlink_ancestor_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            safe_target = root / "unrelated-safe-target"
            safe_target.mkdir()
            safe_before = _tree_metadata(safe_target)
            alias = root / "unrelated-safe-alias"
            alias.symlink_to(safe_target, target_is_directory=True)

            with self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "symlink component"
            ):
                _recover(
                    queue,
                    base,
                    source,
                    alias / "recovered",
                    source_pin,
                )

            self.assertEqual(_tree_metadata(safe_target), safe_before)
            self.assertFalse((safe_target / "recovered").exists())

    def test_malformed_incident_checkpoint_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            template = _incident()
            observations: dict[str, dict] = {}
            for name in ("invalid-hash", "summary-mismatch", "future"):
                observations[name] = json.loads(
                    json.dumps(template.interrupted_checkpoint_observation)
                )
            observations["invalid-hash"]["manifest_sha256"] = "z" * 64
            observations["summary-mismatch"]["summary"]["jobs_selected"] += 1
            observations["future"]["updated_at"] = "2099-01-01T00:00:00Z"

            for name, observation in observations.items():
                with self.subTest(name=name), self.assertRaises(
                    SatelliteBatchRecoveryError
                ):
                    recover_satellite_batch(
                        queue,
                        base,
                        source,
                        root / f"rejected-{name}",
                        artifact_id="fixture-rejected",
                        base_artifact_id="fixture-base",
                        source_evidence_artifact_id="fixture-source",
                        position_start=2,
                        position_end=3,
                        recovered_at="2026-07-19T23:00:00Z",
                        incident=RecoveryIncident(
                            observed_writer_pids=template.observed_writer_pids,
                            launchd_service_observations=(
                                template.launchd_service_observations
                            ),
                            reported_guard_pid=template.reported_guard_pid,
                            handling=template.handling,
                            interrupted_checkpoint_observation=observation,
                        ),
                        source_manifest_pin=source_pin,
                    )

    def test_rehashed_nested_provenance_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            original = root / "recovered"
            _recover(queue, base, source, original, source_pin)
            mutations = {
                "prior-format": lambda manifest: manifest.__setitem__(
                    "format", "datacenter-atlas-satellite-batch-recovery-v2"
                ),
                "prior-schema-version": lambda manifest: manifest.__setitem__(
                    "schema_version", 2
                ),
                "empty-artifact-id": lambda manifest: manifest.__setitem__(
                    "artifact_id", ""
                ),
                "nonempty-artifact-id": lambda manifest: manifest.__setitem__(
                    "artifact_id", "fabricated-recovery"
                ),
                "nonempty-base-artifact-id": lambda manifest: manifest[
                    "base"
                ].__setitem__("artifact_id", "fabricated-base"),
                "nonempty-source-artifact-id": lambda manifest: manifest[
                    "source_evidence"
                ].__setitem__("artifact_id", "fabricated-source"),
                "source-directory-name": lambda manifest: manifest[
                    "source_evidence"
                ].__setitem__("source_directory_name", "fabricated-source"),
                "later-recovered-at": lambda manifest: manifest.__setitem__(
                    "recovered_at", "2026-07-20T00:00:00Z"
                ),
                "snapshot-summary": lambda manifest: manifest[
                    "source_evidence"
                ].__setitem__("snapshot_summary", {"fabricated": 999}),
                "run-history": lambda manifest: manifest[
                    "source_evidence"
                ].__setitem__("run_history_limitation", "fabricated"),
                "outside-count": lambda manifest: manifest[
                    "reconciliation"
                ].__setitem__("source_changes_outside_selection_observed", 999999),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    tampered_parent = root / f"tampered-{name}"
                    tampered_parent.mkdir()
                    tampered = tampered_parent / original.name
                    shutil.copytree(original, tampered)
                    _resign_recovery_manifest(tampered, mutate)
                    with self.assertRaises(SatelliteBatchRecoveryError):
                        validate_recovered_satellite_batch(queue, base, tampered)

    def test_failure_path_preserves_source_path_hash_and_mode_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            source_before = _tree_metadata(source)
            output = root / "failed-recovery"

            with patch.object(
                recovery_module,
                "_copy_catalog",
                side_effect=RuntimeError("injected offline copy failure"),
            ), self.assertRaisesRegex(RuntimeError, "injected offline copy failure"):
                _recover(queue, base, source, output, source_pin)

            self.assertEqual(_tree_metadata(source), source_before)
            self.assertFalse(output.exists())
            self.assertFalse(
                output.with_name(f".{output.name}.recovery-staging").exists()
            )

    def test_wrapper_validation_failure_leaves_no_final_named_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            source_before = _tree_metadata(source)
            output = root / "validation-failed-recovery"

            with patch.object(
                recovery_module,
                "validate_recovered_satellite_batch",
                side_effect=SatelliteBatchRecoveryError(
                    "injected wrapper validation failure"
                ),
            ), self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "injected wrapper validation failure"
            ):
                _recover(queue, base, source, output, source_pin)

            self.assertEqual(_tree_metadata(source), source_before)
            self.assertFalse(output.exists())
            self.assertFalse(
                output.with_name(f".{output.name}.recovery-staging").exists()
            )

    def test_race_created_output_is_never_overwritten_or_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            queue, base, source, source_pin = _fixture(root)
            output = root / "race-recovery"
            original_promote = recovery_module._promote_directory_exclusive

            def create_target_then_promote(stage: Path, destination: Path) -> None:
                destination.mkdir()
                (destination / "racer-owned.txt").write_text(
                    "racer-owned\n", encoding="utf-8"
                )
                original_promote(stage, destination)

            with patch.object(
                recovery_module,
                "_promote_directory_exclusive",
                side_effect=create_target_then_promote,
            ), self.assertRaisesRegex(
                SatelliteBatchRecoveryError, "appeared before exclusive promotion"
            ):
                _recover(queue, base, source, output, source_pin)

            self.assertEqual(
                (output / "racer-owned.txt").read_text(encoding="utf-8"),
                "racer-owned\n",
            )
            self.assertFalse(
                output.with_name(f".{output.name}.recovery-staging").exists()
            )


if __name__ == "__main__":
    unittest.main()
