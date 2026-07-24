from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.satellite_batch import BATCH_MANIFEST_FILENAME
from datacenter_atlas.satellite_batch_recovery import (
    RECOVERY_FORMAT,
    RECOVERY_SCHEMA_VERSION,
    RECOVERY_SCOPE,
    RecoveryIncident,
    recover_satellite_batch,
    validate_recovered_satellite_batch,
)


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-18-global-open-v3"
BASE = ROOT / "satellite_review_runs/2026-07-18-global-open-v3-unknown-030"
SOURCE = ROOT / "satellite_review_runs/2026-07-18-global-open-v3-unknown-031"
RECOVERY = (
    ROOT
    / "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25"
)
DEFINITION = (
    ROOT
    / "definitions/satellite_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25.json"
)
STAGING = RECOVERY.parent / f".{RECOVERY.name}.recovery-staging"

DEFINITION_SHA256 = "1b054ac9c1091e1470576fcf9f14df05a64cb6d679a22ab413430957ffbcb420"
RECOVERY_MANIFEST_SHA256 = (
    "178f52ad3c42117ea19561c123eef87fe1ed7331c79e9c5c1596bd8d2b7cbfb1"
)
RECOVERY_SIDECAR_SHA256 = (
    "97f6521b003d5daa4ddb571c0793e1378522bf01b2fe909aebfa28cb06062204"
)
SOURCE_SNAPSHOT_SHA256 = (
    "b13c3fa7ec0f87265b2149e12e643ea8d512fbc7387bda4b5f468f66cae2d97d"
)
SELECTED_QUEUE_SHA256 = (
    "c54bcbbf4a651e919a6bc671adc10ffef9f55b82d1f78999ba3402421f1a7b90"
)
PAYLOAD_INVENTORY_SHA256 = (
    "340b68a17ba9e90820f1214b220366e5b4b5fe5f31db0e3b63689e8245e48aed"
)
BATCH_MANIFEST_SHA256 = (
    "797ef873d519b9a8e503cf4ad79231d0ca42ea50fcf9159b65db8993a2322c7d"
)
BASE_MANIFEST_SHA256 = (
    "18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_document(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    document = json.loads(raw)
    canonical = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise AssertionError(f"not canonical JSON: {path}")
    return document


def _tree_contract(root: Path) -> tuple[int, int, int, int, set[int], set[int]]:
    files = 0
    directories = 0
    symlinks = 0
    specials = 0
    file_modes: set[int] = set()
    directory_modes: set[int] = set()
    for parent, directory_names, file_names in os.walk(root, followlinks=False):
        parent_path = Path(parent)
        parent_metadata = parent_path.lstat()
        if stat.S_ISLNK(parent_metadata.st_mode):
            symlinks += 1
        elif stat.S_ISDIR(parent_metadata.st_mode):
            directories += 1
            directory_modes.add(stat.S_IMODE(parent_metadata.st_mode))
        else:
            specials += 1
        for name in directory_names:
            metadata = (parent_path / name).lstat()
            if stat.S_ISLNK(metadata.st_mode):
                symlinks += 1
            elif not stat.S_ISDIR(metadata.st_mode):
                specials += 1
        for name in file_names:
            metadata = (parent_path / name).lstat()
            if stat.S_ISLNK(metadata.st_mode):
                symlinks += 1
            elif stat.S_ISREG(metadata.st_mode):
                files += 1
                file_modes.add(stat.S_IMODE(metadata.st_mode))
            else:
                specials += 1
    return files, directories, symlinks, specials, file_modes, directory_modes


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int, int | None, str | None]]:
    snapshot: dict[str, tuple[str, int, int | None, str | None]] = {}
    for parent, directory_names, file_names in os.walk(root, followlinks=False):
        parent_path = Path(parent)
        relative_parent = parent_path.relative_to(root).as_posix()
        snapshot["." if relative_parent == "." else relative_parent] = (
            "directory",
            stat.S_IMODE(parent_path.lstat().st_mode),
            None,
            None,
        )
        for name in directory_names:
            path = parent_path / name
            if path.is_symlink():
                snapshot[path.relative_to(root).as_posix()] = (
                    "symlink",
                    stat.S_IMODE(path.lstat().st_mode),
                    None,
                    os.readlink(path),
                )
        for name in file_names:
            path = parent_path / name
            metadata = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISREG(metadata.st_mode):
                raw = path.read_bytes()
                snapshot[relative] = (
                    "file",
                    stat.S_IMODE(metadata.st_mode),
                    len(raw),
                    hashlib.sha256(raw).hexdigest(),
                )
            elif stat.S_ISLNK(metadata.st_mode):
                snapshot[relative] = (
                    "symlink",
                    stat.S_IMODE(metadata.st_mode),
                    None,
                    os.readlink(path),
                )
            else:
                snapshot[relative] = (
                    "special",
                    stat.S_IMODE(metadata.st_mode),
                    None,
                    None,
                )
    return snapshot


def _make_tree_writable(root: Path) -> None:
    for parent, directory_names, file_names in os.walk(root, topdown=False):
        parent_path = Path(parent)
        for name in file_names:
            (parent_path / name).chmod(0o600)
        for name in directory_names:
            path = parent_path / name
            if not path.is_symlink():
                path.chmod(0o700)
        parent_path.chmod(0o700)


class Unknown033Recovered25Tests(unittest.TestCase):
    def test_pinned_artifact_is_the_accepted_v3_recovery(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(
            _sha256(RECOVERY / "recovery-manifest.json"),
            RECOVERY_MANIFEST_SHA256,
        )
        self.assertEqual(
            _sha256(RECOVERY / "manifest.sha256"), RECOVERY_SIDECAR_SHA256
        )
        self.assertEqual(
            _sha256(RECOVERY / "source-evidence-manifest-snapshot.json"),
            SOURCE_SNAPSHOT_SHA256,
        )
        self.assertEqual(
            _sha256(RECOVERY / "selected-queue-jobs.jsonl"),
            SELECTED_QUEUE_SHA256,
        )
        self.assertEqual(
            _sha256(RECOVERY / "inventory.jsonl"), PAYLOAD_INVENTORY_SHA256
        )
        self.assertEqual(
            _sha256(RECOVERY / "batch" / BATCH_MANIFEST_FILENAME),
            BATCH_MANIFEST_SHA256,
        )
        self.assertEqual(_sha256(BASE / BATCH_MANIFEST_FILENAME), BASE_MANIFEST_SHA256)
        self.assertEqual(
            (RECOVERY / "manifest.sha256").read_text(encoding="ascii"),
            f"{RECOVERY_MANIFEST_SHA256}  recovery-manifest.json\n",
        )

        definition = _canonical_document(DEFINITION)
        manifest = _canonical_document(RECOVERY / "recovery-manifest.json")
        self.assertEqual(
            definition["format"],
            "datacenter-atlas-satellite-batch-recovery-definition-v3",
        )
        self.assertEqual(manifest["format"], RECOVERY_FORMAT)
        self.assertEqual(manifest["schema_version"], RECOVERY_SCHEMA_VERSION)
        self.assertEqual(definition["artifact_id"], RECOVERY.name)
        self.assertEqual(manifest["artifact_id"], RECOVERY.name)
        self.assertEqual(definition["base_artifact_id"], BASE.name)
        self.assertEqual(manifest["base"]["artifact_id"], BASE.name)
        self.assertEqual(definition["source_evidence_artifact_id"], SOURCE.name)
        self.assertEqual(manifest["source_evidence"]["artifact_id"], SOURCE.name)
        self.assertEqual(
            manifest["source_evidence"]["source_directory_name"], SOURCE.name
        )

        source_manifest = SOURCE / BATCH_MANIFEST_FILENAME
        source_raw = source_manifest.read_bytes()
        source_pin = {
            "bytes": len(source_raw),
            "mtime_ns": source_manifest.stat().st_mtime_ns,
            "sha256": hashlib.sha256(source_raw).hexdigest(),
        }
        self.assertEqual(source_pin, definition["source_manifest_pin"])
        self.assertEqual(
            source_pin, manifest["source_evidence"]["post_guard_manifest_pin"]
        )
        self.assertEqual(
            manifest["source_evidence"]["manifest_snapshot"]["sha256"],
            SOURCE_SNAPSHOT_SHA256,
        )

        self.assertEqual(definition["recovered_at"], "2026-07-19T23:56:32Z")
        self.assertEqual(manifest["recovered_at"], definition["recovered_at"])
        batch_manifest = _canonical_document(
            RECOVERY / "batch" / BATCH_MANIFEST_FILENAME
        )
        self.assertEqual(batch_manifest["updated_at"], definition["recovered_at"])
        self.assertEqual(
            batch_manifest["response_limit_migration"]["migrated_at"],
            definition["recovered_at"],
        )
        self.assertEqual(
            batch_manifest["response_limit_migration"][
                "enforced_for_subsequent_attempts_at_or_after"
            ],
            definition["recovered_at"],
        )

        self.assertEqual(manifest["scope"], RECOVERY_SCOPE)
        false_scope_fields = {
            "network_requests_performed",
            "source_batch_promoted",
            "source_evidence_accepted_for_release",
            "atlas_mutation",
            "change_analysis_executed",
            "imagery_identity_inference",
            "imagery_lifecycle_inference",
            "imagery_operating_status_inference",
            "imagery_power_inference",
        }
        self.assertTrue(all(manifest["scope"][field] is False for field in false_scope_fields))
        self.assertTrue(manifest["scope"]["review_required"])

        self.assertFalse(STAGING.exists())
        self.assertFalse(STAGING.is_symlink())
        self.assertEqual(
            _tree_contract(RECOVERY),
            (13376, 9088, 0, 0, {0o444}, {0o555}),
        )

        recovered = validate_recovered_satellite_batch(
            QUEUE,
            BASE,
            RECOVERY,
            source_evidence_directory=SOURCE,
        )
        self.assertEqual(recovered, manifest)
        selection = recovered["selection"]
        self.assertEqual(
            (selection["queue_position_start"], selection["queue_position_end"]),
            (4745, 4769),
        )
        self.assertEqual(selection["jobs"], 25)
        self.assertEqual(selection["clean_first_attempt_completed"], 25)
        self.assertEqual(selection["unavailable_no_scene"], 0)
        self.assertTrue(selection["selected_terminals_strictly_predate_outside_delta"])

        base_manifest = _canonical_document(BASE / BATCH_MANIFEST_FILENAME)
        changed_queue_ids = [
            queue_id
            for queue_id, task in batch_manifest["jobs"].items()
            if task != base_manifest["jobs"][queue_id]
        ]
        changed_positions = sorted(
            batch_manifest["jobs"][queue_id]["queue_position"]
            for queue_id in changed_queue_ids
        )
        self.assertEqual(changed_positions, list(range(4745, 4770)))
        self.assertEqual(set(changed_queue_ids), set(selection["queue_ids"]))
        for queue_id in changed_queue_ids:
            task = batch_manifest["jobs"][queue_id]
            self.assertEqual(task["state"], "completed")
            self.assertEqual(task["attempts"], 1)
            self.assertEqual(task["failures"], [])
            self.assertIsNone(task["unavailability"])

        reconciliation = recovered["reconciliation"]
        self.assertEqual(reconciliation["selected_task_delta"], 25)
        self.assertEqual(reconciliation["selected_catalog_files_copied"], 75)
        self.assertEqual(
            reconciliation["source_changes_outside_selection_observed"], 138
        )
        self.assertEqual(reconciliation["source_changes_outside_selection_copied"], 0)
        self.assertEqual(reconciliation["later_job_leakage"], 0)
        self.assertEqual(reconciliation["live_catalog_requests"], 0)
        self.assertIsNone(reconciliation["batch_last_run"])
        self.assertEqual(
            recovered["output"]["batch_summary"],
            {
                "jobs_selected": 6736,
                "jobs_completed": 4375,
                "jobs_failed": 0,
                "jobs_pending": 2061,
                "jobs_unavailable_no_scene": 300,
            },
        )

    @unittest.skipUnless(
        os.environ.get("DATACENTER_ATLAS_RUN_RECOVERY_REPRODUCTION") == "1",
        "set DATACENTER_ATLAS_RUN_RECOVERY_REPRODUCTION=1 for the 3 GB byte reproduction",
    )
    def test_offline_byte_reproduction_from_guarded_inputs(self) -> None:
        definition = _canonical_document(DEFINITION)
        incident = definition["incident"]
        base_before = _sha256(BASE / BATCH_MANIFEST_FILENAME)
        source_before = _sha256(SOURCE / BATCH_MANIFEST_FILENAME)
        with tempfile.TemporaryDirectory(
            dir=RECOVERY.parent,
            prefix=".unknown033-reproduction-",
        ) as temporary:
            reproduced = Path(temporary) / definition["artifact_id"]
            recover_satellite_batch(
                QUEUE,
                BASE,
                SOURCE,
                reproduced,
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
                    reported_guard_pid=incident["reported_guard_pid"],
                    handling=incident["handling"],
                    interrupted_checkpoint_observation=incident[
                        "interrupted_checkpoint_observation"
                    ],
                ),
                source_manifest_pin=definition["source_manifest_pin"],
            )
            try:
                self.assertEqual(_tree_snapshot(reproduced), _tree_snapshot(RECOVERY))
            finally:
                _make_tree_writable(reproduced)
        self.assertEqual(_sha256(BASE / BATCH_MANIFEST_FILENAME), base_before)
        self.assertEqual(_sha256(SOURCE / BATCH_MANIFEST_FILENAME), source_before)


if __name__ == "__main__":
    unittest.main()
