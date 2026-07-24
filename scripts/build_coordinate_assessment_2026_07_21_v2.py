from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from typing import Any

import build_coordinate_assessment_2026_07_21_v1 as base


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v2"
ARTIFACT_DIR = PUBLICATION_ROOT / ARTIFACT_ID
INCIDENT_ID = "site-coordinate-assessment-publication-incident-2026-07-21-v1"
INCIDENT_DIR = PUBLICATION_ROOT / INCIDENT_ID
AS_OF_DATE = "2026-07-21"
DETECTED_AT = "2026-07-21T09:40:57Z"

V1_PATH = PUBLICATION_ROOT / "site-coordinate-assessment-2026-07-21-v1"
V1_FIRST_STATE_PATH = (
    PUBLICATION_ROOT / "site-coordinate-assessment-2026-07-21-v1-pre-accent"
)
V1_FIRST_STATE_TRASH_PATH = Path(
    "/Users/kian/.Trash/datacenter-atlas-site-coordinate-assessment-v1-"
    "first-published-20260721-0235Z"
)

V1_FIRST_STATE = {
    "manifest_bytes": 1_591,
    "manifest_sha256": (
        "e973cced3b9c2de838738ba0c238b940131678793f1dc9964efd2af5c1df1d7a"
    ),
    "manifest_hash_file_bytes": 80,
    "manifest_hash_file_sha256": (
        "a2f6d0bcca1ad185e4a3cbf16708809b6a3bef35448dcf85e9925d172ef0a8c7"
    ),
    "tree_sha256": (
        "e3e7e1e8d025659eae7584997f827417aec0783ed49624e5a94ba6424815836f"
    ),
    "disposition_bytes": 9_300,
    "disposition_sha256": (
        "e7d303c35eea1e1632fe67ce5c3a5b603cf985caa4abb929d20252b76c3b0028"
    ),
    "huechuraba_successor_bytes": 10_623,
    "huechuraba_successor_sha256": (
        "7acde122553af746dec9b01d5b8c7726198394d74495ccbb9a0f96618071eb65"
    ),
}

V1_CURRENT_STATE = {
    "manifest_bytes": 1_591,
    "manifest_sha256": (
        "448bd1943fd4a3332f7afcaefd17e098e359b9ec4e360cbe5f323a020fac2ec7"
    ),
    "manifest_hash_file_bytes": 80,
    "manifest_hash_file_sha256": (
        "234ee1d7155810e93cb77c4570edb76e8d0abcb9a5128742085edf6a0fb12cf8"
    ),
    "tree_sha256": (
        "1a6cbf2e694ca0667739181d0cc21d132e0025506a734d0d1efcaeb04ff0a624"
    ),
    "disposition_bytes": 9_300,
    "disposition_sha256": (
        "fcae8b38a30d1d7e3cbc03b526a77d103930e035c5f723d3ef4fa98519710cc0"
    ),
    "huechuraba_successor_bytes": 10_625,
    "huechuraba_successor_sha256": (
        "78a289a28b0d09a5e2918cc16be747de3b3bea1a1a5616bf931e5bb480d9b948"
    ),
}


class PublicationError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _successor_name(name: str) -> str:
    suffix = "-coordinate-v1.json"
    if not name.endswith(suffix):
        raise PublicationError(f"unexpected v1 successor name: {name}")
    return f"{name[:-len(suffix)]}-coordinate-v2.json"


def _manifest_payloads(
    artifact_id: str, payloads: dict[str, bytes]
) -> dict[str, bytes]:
    rows = [
        {"path": path, "bytes": len(raw), "sha256": _sha256(raw)}
        for path, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "files": rows,
        "tree_sha256": _sha256(_canonical_json(rows)),
    }
    manifest_raw = _canonical_json(manifest)
    return {
        **payloads,
        "manifest.json": manifest_raw,
        "manifest.sha256": (
            f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
        ),
    }


def _incident_payloads() -> dict[str, bytes]:
    incident = {
        "schema_version": "1.0",
        "incident_id": INCIDENT_ID,
        "detected_at": DETECTED_AT,
        "severity": "publication_integrity",
        "affected_artifact": "site-coordinate-assessment-2026-07-21-v1",
        "acceptance": "rejected",
        "integration": "none",
        "summary": (
            "The immutable v1 final path exposed two different frozen, internally "
            "consistent byte states. The path was vacated and republished after a "
            "source-name correction, violating final-path immutability."
        ),
        "observed_states": {
            "first_published": {
                **V1_FIRST_STATE,
                "logical_path_at_observation": (
                    "source_artifacts/site-coordinate-assessment-2026-07-21-v1"
                ),
                "preserved_recovery_path": str(V1_FIRST_STATE_TRASH_PATH),
            },
            "current_preserved": {
                **V1_CURRENT_STATE,
                "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v1",
            },
        },
        "exact_factual_delta": {
            "changed_payloads": [
                "normalized-successors/curated-official-2026-07-21-scala-"
                "ssclhb01-huechuraba-current-build-coordinate-v1.json",
                "disposition.json",
                "manifest.json",
                "manifest.sha256",
            ],
            "semantic_change": (
                "Two strings in the Huechuraba successor changed from 'Ampliacion' "
                "to the source-reported 'Ampliación': the evidence excerpt and "
                "metadata returned_project_name."
            ),
            "huechuraba_byte_delta": 2,
            "coordinate_or_geometry_delta": False,
            "non_coordinate_claim_delta": False,
            "cascading_pin_only_files": [
                "disposition.json",
                "manifest.json",
                "manifest.sha256",
            ],
        },
        "root_cause": (
            "The v1 builder wrote directly into its final directory and froze that "
            "directory. A later exact-source transcription correction was made by "
            "renaming the first directory aside and rebuilding the same logical final "
            "path. Per-file refusal was insufficient to protect final-path identity."
        ),
        "containment": {
            "v1_accepted": False,
            "v1_current_bytes_preserved": True,
            "v1_first_bytes_preserved_recoverably": True,
            "downstream_selection": "none",
            "replacement_artifact": ARTIFACT_ID,
        },
        "corrective_publication_contract": {
            "build_in_unique_sibling_stage": True,
            "freeze_before_promotion": True,
            "atomic_no_replace_promotion": True,
            "existing_identical_publication_is_read_only_idempotent": True,
            "existing_nonidentical_publication_is_rejected": True,
        },
    }
    readme = """# Coordinate publication integrity incident 2026-07-21 v1

The frozen `site-coordinate-assessment-2026-07-21-v1` final path exposed two
different byte states. Both were internally consistent, but changing a published
logical path violates immutable publication identity. V1 is rejected and has no
downstream integration.

The first and current manifest, tree, disposition, and Huechuraba payload hashes
are pinned in `incident.json`. The current v1 bytes remain untouched at their final
path; the first state is preserved at the recovery path recorded there. V2 is the
only candidate publication and uses staged, frozen, atomic no-replace promotion.
""".encode("utf-8")
    return _manifest_payloads(
        INCIDENT_ID,
        {"README.md": readme, "incident.json": _canonical_json(incident)},
    )


def _v2_payloads(incident_manifest_sha256: str) -> dict[str, bytes]:
    for name in base.COHORT:
        base._load_source(name)

    successors: dict[str, bytes] = {}
    successor_pins: dict[str, dict[str, Any]] = {}
    for label, spec in base.RESOLVED.items():
        successor_name = _successor_name(spec["successor"])
        relative = f"normalized-successors/{successor_name}"
        raw = _canonical_json(base._successor(label, spec))
        successors[relative] = raw
        successor_pins[label] = {
            "path": relative,
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "predecessor": f"sources/{spec['predecessor']}",
            "campus_key": spec["campus_key"],
            "project_key": spec["project_key"],
        }

    observations = copy.deepcopy(base._coordinate_observations())
    observations["artifact_id"] = ARTIFACT_ID
    observations["publication_integrity"] = {
        "v1_accepted": False,
        "incident_artifact": f"source_artifacts/{INCIDENT_ID}",
        "integration": "none",
    }
    for row in observations["rows"]:
        row["successor"] = row["successor"].replace(
            "-coordinate-v1.json", "-coordinate-v2.json"
        )

    disposition = copy.deepcopy(base._disposition(successor_pins))
    disposition["artifact_id"] = ARTIFACT_ID
    disposition["publication_integrity"] = {
        "v1_accepted": False,
        "v1_reason": "immutable_final_path_exposed_two_different_byte_states",
        "v1_current_manifest_sha256": V1_CURRENT_STATE["manifest_sha256"],
        "v1_first_manifest_sha256": V1_FIRST_STATE["manifest_sha256"],
        "incident_artifact": f"source_artifacts/{INCIDENT_ID}",
        "incident_manifest_sha256": incident_manifest_sha256,
        "publication_contract": (
            "unique_sibling_stage_then_freeze_then_atomic_no_replace"
        ),
    }
    disposition["lineage"]["rejected_as_lineage"].append(
        {
            "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v1",
            "reason": "rejected_publication_identity_mutation_incident",
        }
    )

    inventory = copy.deepcopy(base._retrieval_inventory())
    inventory["artifact_id"] = ARTIFACT_ID
    inventory["publication_incident_artifact"] = f"source_artifacts/{INCIDENT_ID}"

    readme = f"""# Site coordinate assessment 2026-07-21 v2

This collision-isolated artifact assesses ten campuses and thirteen explicitly
parented projects in thirteen directly pinned curated files. It accepts only three
official site anchors: the SIMBIO representative points for Lampa and Huechuraba,
and the Fortaleza municipal surveyed SFORPF01 boundary. Their three explicitly
parented projects receive the same site anchors with explicit geometry semantics.

Seven campuses and ten projects remain unresolved. Generic locality centroids,
street midpoints, Google-derived coordinates, unlicensed directory points,
coordinates from distinct facilities, and non-deterministic OSM matches are excluded.

Integration is `none`. Open-seed v68, both discovery-wrapper v1 artifacts, and the
coordinate-assessment v1 publication are rejected as lineage. V1 exposed two byte
states at one frozen final path; `{INCIDENT_ID}` pins the incident. V2 was written in
a unique sibling stage, frozen, and atomically promoted without replacement.

The thirteen unchanged curated files are pinned directly. Successors live only in
this artifact and add no lifecycle, capacity, operator, owner, workload, data-center
type, energy, consumption, or current-status claim. Restricted raw captures are
hash-only; the intact analysis capture directory is recoverable from the Trash path
recorded in `retrieval-inventory.json`.
""".encode("utf-8")

    return _manifest_payloads(
        ARTIFACT_ID,
        {
            "README.md": readme,
            "coordinate-observations.json": _canonical_json(observations),
            "disposition.json": _canonical_json(disposition),
            "retrieval-inventory.json": _canonical_json(inventory),
            **successors,
        },
    )


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_stage(stage: Path, payloads: dict[str, bytes]) -> None:
    for relative, raw in sorted(payloads.items()):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            raise PublicationError(f"stage path collision: {path}")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        path.chmod(0o444)
    directories = [stage, *(path for path in stage.rglob("*") if path.is_dir())]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _sync_directory(directory)
        directory.chmod(0o555)


def _inspect_exact(
    destination: Path, payloads: dict[str, bytes], *, require_frozen: bool = True
) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise PublicationError(f"publication path is not a directory: {destination}")
    expected_files = {destination / relative for relative in payloads}
    actual_files = {path for path in destination.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise PublicationError(f"publication file set mismatch: {destination}")
    actual_directories = {destination, *(path for path in destination.rglob("*") if path.is_dir())}
    expected_directories = {destination, *(path.parent for path in expected_files)}
    if actual_directories != expected_directories:
        raise PublicationError(f"publication directory set mismatch: {destination}")
    for relative, expected in payloads.items():
        path = destination / relative
        if path.is_symlink() or path.read_bytes() != expected:
            raise PublicationError(f"publication byte mismatch: {path}")
        if require_frozen and stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise PublicationError(f"publication file is not frozen: {path}")
    if require_frozen:
        for path in actual_directories:
            if stat.S_IMODE(path.stat().st_mode) != 0o555:
                raise PublicationError(f"publication directory is not frozen: {path}")


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:
            raise PublicationError("atomic no-replace publication is unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:
            raise PublicationError("atomic no-replace publication is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 0x00000001)
    else:
        raise PublicationError("atomic no-replace publication is unavailable")
    if result == 0:
        _sync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise PublicationError(
            f"late publication collision; refusing overwrite: {destination}"
        )
    raise PublicationError(
        f"atomic no-replace publication failed: {os.strerror(error_number)}"
    )


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    for path in sorted(stage.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o700 if path.is_dir() else 0o600)
    stage.chmod(0o700)
    shutil.rmtree(stage)


def _publish(destination: Path, payloads: dict[str, bytes]) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        _inspect_exact(destination, payloads)
        return "existing-identical"
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        _write_stage(stage, payloads)
        _inspect_exact(stage, payloads)
        _promote_noreplace(stage, destination)
    except Exception:
        _discard_stage(stage)
        raise
    _inspect_exact(destination, payloads)
    return "published"


def _verify_state(path: Path, expected: dict[str, Any]) -> None:
    manifest_path = path / "manifest.json"
    manifest_hash_path = path / "manifest.sha256"
    if (
        len(manifest_path.read_bytes()) != expected["manifest_bytes"]
        or _sha256(manifest_path.read_bytes()) != expected["manifest_sha256"]
        or len(manifest_hash_path.read_bytes()) != expected["manifest_hash_file_bytes"]
        or _sha256(manifest_hash_path.read_bytes())
        != expected["manifest_hash_file_sha256"]
    ):
        raise PublicationError(f"observed v1 state drifted: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["tree_sha256"] != expected["tree_sha256"]:
        raise PublicationError(f"observed v1 tree pin drifted: {path}")


def publish_all(publication_root: Path = PUBLICATION_ROOT) -> dict[str, str]:
    _verify_state(V1_PATH, V1_CURRENT_STATE)
    first_path = (
        V1_FIRST_STATE_PATH
        if V1_FIRST_STATE_PATH.exists()
        else V1_FIRST_STATE_TRASH_PATH
    )
    _verify_state(first_path, V1_FIRST_STATE)

    incident_payloads = _incident_payloads()
    incident_manifest_sha256 = _sha256(incident_payloads["manifest.json"])
    v2_payloads = _v2_payloads(incident_manifest_sha256)
    return {
        "incident": _publish(publication_root / INCIDENT_ID, incident_payloads),
        "assessment": _publish(publication_root / ARTIFACT_ID, v2_payloads),
    }


def main() -> None:
    print(json.dumps(publish_all(), sort_keys=True))


if __name__ == "__main__":
    main()
