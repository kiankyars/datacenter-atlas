"""Seal the rejected definition-only federation v32 publication incident."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from . import federated_release as legacy
from . import federated_release_v3 as federation
from . import federation_v32 as rejected


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "source_artifacts/federation-v32-partial-publication-incident-2026-07-21-v1"
)
RECORDED_AT = "2026-07-21T13:27:00Z"
DETECTED_AT = "2026-07-21T13:21:34.276170Z"

REJECTED_DEFINITION_PIN = (
    1_788,
    "29ff67c72cbe83f48ed28db6e4c059f1513358cf43d20c6039ae5e27cc924dc9",
)
RECONSTRUCTED_BUNDLE_PINS = {
    "federated-index.json": (
        31_626,
        "054f69c7e0bda9f1c7992dd89f5b6efb4323ac325d0dc91674c2ce9decf92b9f",
    ),
    "manifest.json": (
        986,
        "e759fe6f0de63b431f89b2bc4228d1d04b0146d6deed540e1be315efa9897fde",
    ),
    "manifest.sha256": (
        80,
        "3217cb5dedbe1a75adf525ad97e78f8c000e736a02c50c1038a32c6ced89284c",
    ),
}
RECONSTRUCTED_BUNDLE_TREE_SHA256 = (
    "912e20186d66ac1dadc7c9af330dac510124997a7708e8ba1dd6eae65f43dfcd"
)
ERROR_TEXT = (
    "datacenter_atlas.federated_release.FederatedReleaseError: atomic "
    "no-clobber publication failed: Permission denied"
)


class FederationV32IncidentError(RuntimeError):
    """Raised when incident evidence or publication boundaries differ."""


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _target_time() -> datetime:
    return datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))


def _validate_subject() -> None:
    definition = rejected.DEFINITION
    if definition.is_symlink() or not definition.is_file():
        raise FederationV32IncidentError("rejected v32 definition is absent")
    raw = definition.read_bytes()
    details = definition.stat()
    if (
        (len(raw), _sha256(raw)) != REJECTED_DEFINITION_PIN
        or stat.S_IMODE(details.st_mode) != 0o444
        or details.st_ctime_ns != 1_784_640_060_054_008_560
        or getattr(details, "st_birthtime", 0) != 1_784_639_890.2412617
        or details.st_mtime_ns != 1_784_639_890_241_302_308
    ):
        raise FederationV32IncidentError("rejected v32 definition evidence differs")
    if rejected.INDEX_DIR.exists() or rejected.INDEX_DIR.is_symlink():
        raise FederationV32IncidentError("rejected v32 bundle path is not absent")
    for path in (rejected.ROOT / "sources", rejected.ROOT / "federated_indexes"):
        if stat.S_IMODE(path.stat().st_mode) != 0o755:
            raise FederationV32IncidentError("v32 publication parent mode differs")


def _validate_reconstruction() -> None:
    with tempfile.TemporaryDirectory(
        prefix="federation-v32-incident-replay-", dir="/private/tmp"
    ) as temporary:
        bundle = Path(temporary) / "bundle"
        federation.write_federated_release_index(rejected.DEFINITION, bundle)
        if rejected.tree_digest(bundle) != RECONSTRUCTED_BUNDLE_TREE_SHA256:
            raise FederationV32IncidentError("v32 bundle reconstruction tree differs")
        for name, pin in RECONSTRUCTED_BUNDLE_PINS.items():
            raw = (bundle / name).read_bytes()
            if (len(raw), _sha256(raw)) != pin:
                raise FederationV32IncidentError(
                    f"v32 bundle reconstruction pin differs: {name}"
                )


def _payloads(stage_birth_at: str) -> dict[str, bytes]:
    incident = {
        "acceptance": "accepted_technical_incident_record",
        "affected_artifact": "federated-index-2026-07-21-public-open-v32",
        "corrective_successor": "federated-index-2026-07-21-public-open-v33",
        "detected_at": DETECTED_AT,
        "format": "datacenter-atlas-federation-partial-publication-incident-v1",
        "incident_id": "federation-v32-partial-publication-incident-2026-07-21-v1",
        "integration": "none",
        "policy": {
            "partial_publication": (
                "A namespace with only one of its required final artifacts is permanently "
                "non-accepted even when that artifact appeared after generated_at."
            ),
            "passage_of_time": "Passage of wall-clock time never repairs a partial publication.",
            "rejected_lineage": (
                "Federation v32 may not be an accepted predecessor, downstream input, "
                "or current federation."
            ),
        },
        "rejected_v32": {
            "acceptance": "non_accepted",
            "claimed_generated_at": rejected.GENERATED_AT,
            "definition": {
                "birth_epoch": 1_784_639_890.2412617,
                "birth_utc": "2026-07-21T13:18:10.241262Z",
                "bytes": REJECTED_DEFINITION_PIN[0],
                "ctime_epoch_ns": 1_784_640_060_054_008_560,
                "ctime_utc": "2026-07-21T13:21:00.054008Z",
                "mode": "0444",
                "mtime_epoch_ns": 1_784_639_890_241_302_308,
                "mtime_utc": "2026-07-21T13:18:10.241302Z",
                "path": "sources/federation-2026-07-21-public-open-v32.json",
                "sha256": REJECTED_DEFINITION_PIN[1],
            },
            "final_bundle": {
                "exists_at_detection": False,
                "path": "federated_indexes/2026-07-21-public-open-v32",
                "promotion_error": ERROR_TEXT,
                "type": "absent_expected_bundle",
            },
            "original_private_stage": {
                "bundle_file_modes": "0444",
                "bundle_root_mode_at_failed_promotion": "0555",
                "cleanup_after_failure": (
                    "The failure handler removed the original private bundle stage. This was "
                    "a secondary retention failure; no original stage inode is claimed retained."
                ),
                "definition_root_mode_at_promotion": "0444",
                "retained": False,
            },
            "deterministic_expected_bundle_reconstruction": {
                "claim_boundary": (
                    "These byte and tree pins are an offline deterministic reconstruction from "
                    "the retained rejected definition, not the original private-stage inode."
                ),
                "files": [
                    {"bytes": pin[0], "path": name, "sha256": pin[1]}
                    for name, pin in sorted(RECONSTRUCTED_BUNDLE_PINS.items())
                ],
                "tree_sha256": RECONSTRUCTED_BUNDLE_TREE_SHA256,
            },
        },
        "diagnosis": {
            "destination_parent": {
                "mode_at_detection": "0755",
                "path": "federated_indexes",
                "shell_writable_at_detection": True,
            },
            "exact_reproduction": {
                "source_bundle_root_0555": "renamex_np(RENAME_EXCL) returned EACCES",
                "source_bundle_root_0755": "the otherwise identical no-replace rename succeeded",
                "target_parent_mode_in_both_cases": "0755",
            },
            "minimum_corrective_mode_transition": {
                "final_bundle_root_after_promotion": "0555",
                "private_bundle_root_during_no_replace_rename": "0755",
                "private_bundle_root_members": "0444",
            },
            "root_cause": (
                "On this macOS filesystem, renamex_np(RENAME_EXCL) returned EACCES for "
                "the frozen 0555 source directory. The writable 0755 destination parent was "
                "not the cause."
            ),
        },
    }
    readme = f"""# Federation v32 partial-publication incident

Federation v32 is permanently non-accepted. At `{rejected.GENERATED_AT}`, its
definition was atomically promoted to the final source path, but the required
bundle promotion failed with `EACCES`; the final bundle path remained absent.

The target parent was writable mode 0755. Reproduction isolated the failure to
macOS no-replace rename of the 0555 source bundle root. The v33 correction uses
0755 only for that private root during rename, keeps all bundle members 0444,
and immediately freezes the promoted final root to 0555.

The original failed private bundle stage was removed by the failure handler.
`incident.json` labels the listed bundle pins as a deterministic reconstruction,
not retained original-stage inode evidence. Integration is none.
""".encode("utf-8")
    return {"README.md": readme, "incident.json": _canonical_json(incident)}


def _manifest(payloads: Mapping[str, bytes], stage_birth_at: str) -> bytes:
    files = [
        {"bytes": len(raw), "path": name, "sha256": _sha256(raw)}
        for name, raw in sorted(payloads.items())
    ]
    tree_sha256 = _sha256(_canonical_json(files))
    return _canonical_json(
        {
            "acceptance_status": "accepted_technical_incident_record",
            "artifact_id": ARTIFACT.name,
            "closed_file_set": [
                "README.md",
                "incident.json",
                "manifest.json",
                "manifest.sha256",
            ],
            "files": files,
            "format": "datacenter-atlas-technical-incident-manifest-v1",
            "integration": "none",
            "publication": {
                "atomic_no_replace_promotion": True,
                "final_root_mode": "0555",
                "member_files_frozen_before_promotion": True,
                "recorded_after_stage_birth": True,
                "root_mode_during_promotion": "0755",
                "stage_birth_at": stage_birth_at,
            },
            "raw_capture_redistributed": False,
            "recorded_at": RECORDED_AT,
            "rejected_subject_count": 1,
            "tree_sha256": tree_sha256,
        }
    )


def build_incident() -> dict[str, Any]:
    _validate_subject()
    _validate_reconstruction()
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise FederationV32IncidentError("incident final path collision")
    target = _target_time()
    if target <= datetime.now(UTC):
        raise FederationV32IncidentError("incident recorded_at must be future before staging")
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{ARTIFACT.name}.stage-", dir=ARTIFACT.parent
        )
    )
    published = False
    try:
        born = datetime.fromtimestamp(stage.stat().st_birthtime, UTC)
        stage_birth_at = born.isoformat(timespec="microseconds").replace("+00:00", "Z")
        payloads = _payloads(stage_birth_at)
        manifest = _manifest(payloads, stage_birth_at)
        all_payloads = {
            **payloads,
            "manifest.json": manifest,
            "manifest.sha256": f"{_sha256(manifest)}  manifest.json\n".encode("ascii"),
        }
        for name, raw in all_payloads.items():
            legacy._write_bytes(stage / name, raw)
            (stage / name).chmod(0o444)
        for path in (stage, *stage.iterdir()):
            details = path.stat()
            latest = max(details.st_birthtime, details.st_mtime)
            if latest > target.timestamp():
                raise FederationV32IncidentError("incident stage post-dates recorded_at")
        while datetime.now(UTC) < target:
            time.sleep(min((target - datetime.now(UTC)).total_seconds(), 0.25))
        federation._promote_noreplace(stage, ARTIFACT)
        published = True
        ARTIFACT.chmod(0o555)
        if datetime.fromtimestamp(ARTIFACT.stat().st_ctime, UTC) < target:
            raise FederationV32IncidentError("incident final root predates recorded_at")
        return json.loads(manifest)
    finally:
        if not published and stage.exists() and not stage.is_symlink():
            for path in stage.iterdir():
                path.chmod(0o600)
            stage.chmod(0o700)
            shutil.rmtree(stage)


def main() -> int:
    print(json.dumps(build_incident(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
