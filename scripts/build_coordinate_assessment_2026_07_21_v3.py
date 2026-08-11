from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Callable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import build_coordinate_assessment_2026_07_21_v2 as previous
from datacenter_atlas.external_captures import resolve_external_capture


base = previous.base
ROOT = REPOSITORY_ROOT
PUBLICATION_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v3"
ARTIFACT_DIR = PUBLICATION_ROOT / ARTIFACT_ID
INCIDENT_ID = "site-coordinate-assessment-temporal-incident-2026-07-21-v1"
INCIDENT_DIR = PUBLICATION_ROOT / INCIDENT_ID
AS_OF_DATE = "2026-07-21"
DETECTED_AT = "2026-07-21T09:51:13Z"

V1_INCIDENT_PATH = (
    PUBLICATION_ROOT
    / "site-coordinate-assessment-publication-incident-2026-07-21-v1"
)
V1_INCIDENT_MANIFEST_SHA256 = (
    "8128a6be3fb6fbe7d9d576e8445524590ff53542530fc499c5d40588cd0bed1d"
)
V2_PATH = PUBLICATION_ROOT / "site-coordinate-assessment-2026-07-21-v2"
V2_MANIFEST_SHA256 = (
    "5b2e8c6d4ea3638ffb75ed3f00b4cdf672c2aaca04fd8fc899a4633506b09024"
)
V2_MANIFEST_BYTES = 1_592
V2_MANIFEST_HASH_FILE_SHA256 = (
    "44a4b539a784fd3fb8ff729762530b463d3fe7d148510f27aa35a6b4618c53bd"
)
V2_TREE_SHA256 = (
    "d104bd68bdb7e3d9fec7d748f639cad51f96a8a3421c0378ba0d86e6e294a1ca"
)
V2_ARTIFACT_BIRTH_EPOCH = 1_784_627_021
V2_ARTIFACT_BIRTH_AT = "2026-07-21T09:43:41Z"

CAPTURE_TRASH_PATH = Path(
    "/Users/kian/.Trash/datacenter-atlas-v68-coordinate-capture-"
    "20260721-1707Z-y0NdsP"
)
CAPTURE_TREE_SHA256 = (
    "25e73755344fb8e6db9ef32b6f1f967afc4a8db8f9e714971f00a1b8685adf49"
)
CAPTURE_FILE_COUNT = 79
CAPTURE_TOTAL_BYTES = 57_610_841


def _capture_path() -> Path:
    return resolve_external_capture(CAPTURE_TRASH_PATH)

SIMBIO_SEIA_WITNESS = {
    "local_capture_completed_at": "2026-07-21T09:26:39Z",
    "completion_mtime_epoch": 1_784_625_999,
    "server_response_http_date_as_reported": "2026-07-21T17:05:51Z",
    "server_clock_ahead_of_completion_seconds": 27_552,
    "body": {
        "capture_name": "simbio-seia-13-refetch.html",
        "bytes": 4_460_168,
        "sha256": (
            "f1725341e873eb005b8d3a9566980d9d0b10173b97b9c5527e0173bb2062ebd6"
        ),
        "birth_epoch": 1_784_625_998,
        "mtime_epoch": 1_784_625_999,
    },
    "headers": {
        "capture_name": "simbio-seia-13.headers",
        "bytes": 177,
        "sha256": (
            "d580f7cd5907e635b7e3a9d970d66446f93b9c5406f87433e8fd4eabe59355e1"
        ),
        "birth_epoch": 1_784_625_995,
        "mtime_epoch": 1_784_625_998,
    },
    "curl_writeout": {
        "capture_name": "simbio-seia-13.curl.json",
        "bytes": 18_656,
        "sha256": (
            "76c8af10bf6407a96a4a26b106f249e73618e85c0cbd9faf821482a2e89890d3"
        ),
        "birth_epoch": 1_784_625_995,
        "mtime_epoch": 1_784_625_999,
        "time_total_seconds": 4.279146,
        "time_starttransfer_seconds": 2.977943,
    },
}

SIMBIO_CONTEXT_WITNESS = {
    "local_capture_completed_at": "2026-07-21T09:27:17Z",
    "completion_mtime_epoch": 1_784_626_037,
    "server_response_http_date_as_reported": "2026-07-21T17:06:29Z",
    "server_clock_ahead_of_completion_seconds": 27_552,
    "body": {
        "capture_name": "simbio-rm-refetch.html",
        "bytes": 3_162_804,
        "sha256": (
            "e05d13b56b25b28b2e42c670df31b8bb63b5d378fcd23a8c6c2624a9382cde3c"
        ),
        "birth_epoch": 1_784_626_036,
        "mtime_epoch": 1_784_626_037,
    },
    "headers": {
        "capture_name": "simbio-rm.headers",
        "bytes": 177,
        "sha256": (
            "7f17a1addc030bb7fadce1eafc84ebde62e1d37aa0c43706d6f96710e9159c27"
        ),
        "birth_epoch": 1_784_626_034,
        "mtime_epoch": 1_784_626_036,
    },
    "curl_writeout": {
        "capture_name": "simbio-rm.curl.json",
        "bytes": 18_652,
        "sha256": (
            "3fa06ee67af0c3acfb7411741812c3b7ef20941c966f928afc8639d48b241e0f"
        ),
        "birth_epoch": 1_784_626_033,
        "mtime_epoch": 1_784_626_037,
        "time_total_seconds": 3.667310,
        "time_starttransfer_seconds": 2.509627,
    },
}

FORTALEZA_WITNESS = {
    "local_capture_completed_at": "2026-07-21T09:27:36Z",
    "completion_mtime_epoch": 1_784_626_056,
    "server_response_http_date_as_reported": "2026-07-21T09:27:32Z",
    "body": {
        "capture_name": "fortaleza-site-plan-refetch.pdf",
        "bytes": 2_965_297,
        "sha256": (
            "039df7d2426a28c602fcdb2bafee8cb9bb2ce72ca3d3d2d55d1d44442c2d8b24"
        ),
        "birth_epoch": 1_784_626_052,
        "mtime_epoch": 1_784_626_056,
    },
    "headers": {
        "capture_name": "fortaleza-site-plan.headers",
        "bytes": 369,
        "sha256": (
            "37626eb25e33e5274cff2c4ea0a4e00804c6e8fca92bce99ccf65156895b306d"
        ),
        "birth_epoch": 1_784_626_052,
        "mtime_epoch": 1_784_626_052,
    },
    "curl_writeout": {
        "capture_name": "fortaleza-site-plan.curl.json",
        "bytes": 14_524,
        "sha256": (
            "7b42d06afcd44c63e772f434353c3a26e58e552120a2773ec299ffd5aa74b6a8"
        ),
        "birth_epoch": 1_784_626_052,
        "mtime_epoch": 1_784_626_056,
        "time_total_seconds": 4.054345,
        "time_starttransfer_seconds": 0.835194,
    },
}


class TemporalPublicationError(previous.PublicationError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _format_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _birth_instant(path: Path) -> datetime:
    metadata = path.stat()
    if not hasattr(metadata, "st_birthtime"):
        raise TemporalPublicationError("filesystem birth time is unavailable")
    return datetime.fromtimestamp(metadata.st_birthtime, timezone.utc)


def _successor_name(name: str) -> str:
    suffix = "-coordinate-v1.json"
    if not name.endswith(suffix):
        raise TemporalPublicationError(f"unexpected coordinate source name: {name}")
    return f"{name[:-len(suffix)]}-coordinate-v3.json"


def _manifest_payloads(
    artifact_id: str,
    payloads: dict[str, bytes],
    *,
    recorded_at: str,
    stage_birth_at: str,
) -> dict[str, bytes]:
    rows = [
        {"path": path, "bytes": len(raw), "sha256": _sha256(raw)}
        for path, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.1",
        "artifact_id": artifact_id,
        "as_of_date": AS_OF_DATE,
        "recorded_at": recorded_at,
        "integration": "none",
        "publication": {
            "stage_birth_at": stage_birth_at,
            "recorded_after_stage_birth": True,
            "frozen_before_promotion": True,
            "atomic_no_replace_promotion": True,
        },
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


def _verify_prior_publications() -> dict[str, Any]:
    if _sha256((V1_INCIDENT_PATH / "manifest.json").read_bytes()) != (
        V1_INCIDENT_MANIFEST_SHA256
    ):
        raise TemporalPublicationError("v1 publication incident drifted")
    v2_manifest_raw = (V2_PATH / "manifest.json").read_bytes()
    if (
        len(v2_manifest_raw) != V2_MANIFEST_BYTES
        or _sha256(v2_manifest_raw) != V2_MANIFEST_SHA256
        or _sha256((V2_PATH / "manifest.sha256").read_bytes())
        != V2_MANIFEST_HASH_FILE_SHA256
    ):
        raise TemporalPublicationError("rejected v2 publication drifted")
    manifest = json.loads(v2_manifest_raw)
    if manifest["tree_sha256"] != V2_TREE_SHA256:
        raise TemporalPublicationError("rejected v2 tree pin drifted")
    if int(_birth_instant(V2_PATH).timestamp()) != V2_ARTIFACT_BIRTH_EPOCH:
        raise TemporalPublicationError("rejected v2 filesystem birth drifted")
    return manifest


def _verify_capture_witness(witness: dict[str, Any]) -> None:
    root = _capture_path()
    packaged_capture = root != CAPTURE_TRASH_PATH
    for carrier in ("body", "headers", "curl_writeout"):
        expected = witness[carrier]
        path = root / expected["capture_name"]
        raw = path.read_bytes()
        metadata = path.stat()
        if (
            len(raw) != expected["bytes"]
            or _sha256(raw) != expected["sha256"]
            or int(metadata.st_mtime) != expected["mtime_epoch"]
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or (
                not packaged_capture
                and int(metadata.st_birthtime) != expected["birth_epoch"]
            )
        ):
            raise TemporalPublicationError(f"capture witness drifted: {path}")
    if witness["completion_mtime_epoch"] != witness["curl_writeout"]["mtime_epoch"]:
        raise TemporalPublicationError("completion witness mismatch")
    if int(_instant(witness["local_capture_completed_at"]).timestamp()) != witness[
        "completion_mtime_epoch"
    ]:
        raise TemporalPublicationError("completion timestamp mismatch")


def _verify_capture_tree() -> None:
    root = _capture_path()
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise TemporalPublicationError("capture root mode drifted")
    paths = sorted(path for path in root.rglob("*") if path.is_file())
    if len(paths) != CAPTURE_FILE_COUNT:
        raise TemporalPublicationError("capture tree file count drifted")
    total_bytes = 0
    rows = bytearray()
    for path in paths:
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise TemporalPublicationError(f"capture carrier mode drifted: {path}")
        raw = path.read_bytes()
        total_bytes += len(raw)
        relative = path.relative_to(root).as_posix()
        rows.extend(f"{_sha256(raw)}  ./{relative}\n".encode("utf-8"))
    if total_bytes != CAPTURE_TOTAL_BYTES or _sha256(bytes(rows)) != CAPTURE_TREE_SHA256:
        raise TemporalPublicationError("capture tree byte closure drifted")


def _corrected_successor(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    document = base._successor(label, spec)
    evidence = document["evidence"][-1]
    metadata = evidence["metadata"]
    if label in {"lampa", "huechuraba"}:
        evidence["retrieved_at"] = SIMBIO_SEIA_WITNESS[
            "local_capture_completed_at"
        ]
        metadata["server_response_http_date_as_reported"] = metadata.pop(
            "response_http_date"
        )
        metadata["context_page_server_response_http_date_as_reported"] = metadata.pop(
            "context_page_response_http_date"
        )
        metadata["retrieval_time_basis"] = (
            "local filesystem completion mtime of the exact byte-identical refetch; "
            "the curl writeout is emitted only after transfer completion"
        )
        metadata["local_capture_witness"] = copy.deepcopy(SIMBIO_SEIA_WITNESS)
        metadata["context_page_local_capture_witness"] = copy.deepcopy(
            SIMBIO_CONTEXT_WITNESS
        )
        metadata["server_date_guardrail"] = (
            "The SIMBIO Date header is 27552 seconds ahead of the local completed "
            "capture and is retained only as server_response_http_date_as_reported. "
            "It is never used as retrieved_at or recorded_at."
        )
    else:
        evidence["retrieved_at"] = FORTALEZA_WITNESS[
            "local_capture_completed_at"
        ]
        metadata["server_response_http_date_as_reported"] = metadata.pop(
            "response_http_date"
        )
        metadata["retrieval_time_basis"] = (
            "local filesystem completion mtime of the exact byte-identical refetch; "
            "the server Date corroborates transfer start but is not retrieved_at"
        )
        metadata["local_capture_witness"] = copy.deepcopy(FORTALEZA_WITNESS)
        metadata["server_date_guardrail"] = (
            "The server Date is retained only as server_response_http_date_as_reported; "
            "retrieved_at is the later local completed-capture timestamp."
        )
    return document


def _incident_payloads(
    *, recorded_at: str, stage_birth_at: str, v2_manifest: dict[str, Any]
) -> dict[str, bytes]:
    incident = {
        "schema_version": "1.0",
        "incident_id": INCIDENT_ID,
        "detected_at": DETECTED_AT,
        "recorded_at": recorded_at,
        "severity": "temporal_integrity",
        "acceptance": "non_accepted",
        "integration": "none",
        "affected_artifact": "site-coordinate-assessment-2026-07-21-v2",
        "summary": (
            "V2 used two clock-ahead SIMBIO server Date headers as evidence "
            "retrieved_at values. Those values post-dated the frozen artifact birth "
            "and the detection wall clock, so v2 is permanently non-accepted."
        ),
        "rejected_v2": {
            "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v2",
            "artifact_birth_at": V2_ARTIFACT_BIRTH_AT,
            "artifact_birth_epoch": V2_ARTIFACT_BIRTH_EPOCH,
            "manifest_bytes": V2_MANIFEST_BYTES,
            "manifest_sha256": V2_MANIFEST_SHA256,
            "manifest_hash_file_sha256": V2_MANIFEST_HASH_FILE_SHA256,
            "tree_sha256": V2_TREE_SHA256,
            "files": v2_manifest["files"],
            "acceptance": "non_accepted",
        },
        "invalid_temporal_metadata": {
            "evidence_keys": [
                base.RESOLVED["lampa"]["evidence_key"],
                base.RESOLVED["huechuraba"]["evidence_key"],
            ],
            "v2_retrieved_at": "2026-07-21T17:05:51Z",
            "v2_context_server_date": "2026-07-21T17:06:29Z",
            "artifact_birth_at": V2_ARTIFACT_BIRTH_AT,
            "detection_wall_clock_at": DETECTED_AT,
            "failure": "retrieved_at_later_than_artifact_birth_and_detection_clock",
            "passage_of_time_guardrail": (
                "A later wall clock can never cure metadata that was false when the "
                "artifact was published. V2 remains non-accepted permanently."
            ),
        },
        "truthful_capture_witness": {
            "capture_tree_sha256": CAPTURE_TREE_SHA256,
            "capture_recovery_path": str(CAPTURE_TRASH_PATH),
            "filesystem_method": (
                "macOS st_birthtime and st_mtime on the preserved exact response body, "
                "header, and curl-writeout files; completion is the curl-writeout mtime"
            ),
            "simbio_seia": SIMBIO_SEIA_WITNESS,
            "simbio_context": SIMBIO_CONTEXT_WITNESS,
            "fortaleza_site_plan": FORTALEZA_WITNESS,
        },
        "root_cause": (
            "The v1/v2 normalizer copied response HTTP Date values into retrieved_at "
            "without comparing them to the local clock or artifact publication birth."
        ),
        "containment": {
            "v2_accepted": False,
            "v2_bytes_preserved": True,
            "v1_publication_incident_manifest_sha256": (
                V1_INCIDENT_MANIFEST_SHA256
            ),
            "v1_remains_rejected": True,
            "downstream_selection": "none",
            "corrected_artifact": ARTIFACT_ID,
        },
    }
    readme = """# Coordinate temporal-integrity incident 2026-07-21 v1

Coordinate-assessment v2 is permanently non-accepted because its two SIMBIO
coordinate evidence records used future-dated server `Date` headers as
`retrieved_at`. V2 bytes remain frozen and are pinned here; passage of time cannot
cure false-at-publication metadata.

The exact local response-body, header, and curl-writeout birth/mtime witnesses show
capture completion at 09:26:39Z for the SEIA response, 09:27:17Z for its context,
and 09:27:36Z for the Fortaleza plan. V3 uses those completion times, retains server
dates only as reported metadata, and remains integration `none`.
""".encode("utf-8")
    return _manifest_payloads(
        INCIDENT_ID,
        {"README.md": readme, "incident.json": _canonical_json(incident)},
        recorded_at=recorded_at,
        stage_birth_at=stage_birth_at,
    )


def _v3_payloads(
    *,
    recorded_at: str,
    stage_birth_at: str,
    incident_manifest_sha256: str,
) -> dict[str, bytes]:
    for name in base.COHORT:
        base._load_source(name)

    successors: dict[str, bytes] = {}
    successor_pins: dict[str, dict[str, Any]] = {}
    for label, spec in base.RESOLVED.items():
        successor_name = _successor_name(spec["successor"])
        relative = f"normalized-successors/{successor_name}"
        raw = _canonical_json(_corrected_successor(label, spec))
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
        "v2_accepted": False,
        "temporal_incident_artifact": f"source_artifacts/{INCIDENT_ID}",
        "recorded_at": recorded_at,
        "integration": "none",
    }
    for row in observations["rows"]:
        row["successor"] = row["successor"].replace(
            "-coordinate-v1.json", "-coordinate-v3.json"
        )

    disposition = copy.deepcopy(base._disposition(successor_pins))
    disposition["artifact_id"] = ARTIFACT_ID
    disposition["publication_integrity"] = {
        "recorded_at": recorded_at,
        "v1_accepted": False,
        "v1_incident_artifact": (
            "source_artifacts/site-coordinate-assessment-publication-incident-"
            "2026-07-21-v1"
        ),
        "v1_incident_manifest_sha256": V1_INCIDENT_MANIFEST_SHA256,
        "v2_accepted": False,
        "v2_manifest_sha256": V2_MANIFEST_SHA256,
        "v2_reason": "future_retrieved_at_metadata_at_publication",
        "temporal_incident_artifact": f"source_artifacts/{INCIDENT_ID}",
        "temporal_incident_manifest_sha256": incident_manifest_sha256,
        "publication_contract": (
            "unique_sibling_stage_then_recorded_at_then_freeze_then_atomic_no_replace"
        ),
    }
    disposition["lineage"]["rejected_as_lineage"].extend(
        [
            {
                "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v1",
                "reason": "rejected_publication_identity_mutation_incident",
            },
            {
                "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v2",
                "reason": "rejected_future_retrieved_at_metadata_at_publication",
            },
        ]
    )

    inventory = copy.deepcopy(base._retrieval_inventory())
    inventory["artifact_id"] = ARTIFACT_ID
    inventory["publication_recorded_at"] = recorded_at
    inventory["temporal_incident_artifact"] = f"source_artifacts/{INCIDENT_ID}"
    inventory["capture_time_correction"] = {
        "method": "local_completed_capture_filesystem_mtime",
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "simbio_seia": SIMBIO_SEIA_WITNESS,
        "simbio_context": SIMBIO_CONTEXT_WITNESS,
        "fortaleza_site_plan": FORTALEZA_WITNESS,
        "server_date_guardrail": (
            "Server Date values are retained only with _as_reported names and never "
            "substituted for local completed-capture retrieved_at."
        ),
    }
    corrected_times = {
        "chile_simbio_region_13_seia": SIMBIO_SEIA_WITNESS[
            "local_capture_completed_at"
        ],
        "chile_simbio_region_context": SIMBIO_CONTEXT_WITNESS[
            "local_capture_completed_at"
        ],
        "fortaleza_sforpf01_site_plan": FORTALEZA_WITNESS[
            "local_capture_completed_at"
        ],
    }
    for request in inventory["accepted_capture_requests"]:
        request["retrieved_at"] = corrected_times[request["request_id"]]

    readme = f"""# Site coordinate assessment 2026-07-21 v3

This artifact assesses ten campuses and thirteen explicitly parented projects in
thirteen directly pinned curated files. It accepts only the official SIMBIO
representative points for Lampa and Huechuraba and the Fortaleza surveyed SFORPF01
boundary. Their three explicitly parented projects receive the same site anchors.

Seven campuses and ten projects remain unresolved. Locality centroids, street
midpoints, Google-derived coordinates, unlicensed directory points, coordinates
from distinct facilities, and non-deterministic OSM matches remain excluded.

V1 is rejected for publication-identity mutation. V2 is permanently rejected because
clock-ahead SIMBIO server Date headers were used as `retrieved_at`; `{INCIDENT_ID}`
pins that temporal incident and the preserved local filesystem/curl witnesses. V3
uses completed-capture times of 09:26:39Z, 09:27:17Z, and 09:27:36Z. Server dates are
retained only as `_as_reported` metadata.

The v3 manifest records publication time after stage birth and before frozen atomic
no-replace promotion. Integration remains `none`; successors live only here and add
no lifecycle, capacity, operator, owner, workload, type, energy, consumption, or
current-status claim. Raw captures remain hash-only and recoverable from Trash.
""".encode("utf-8")

    payloads = {
        "README.md": readme,
        "coordinate-observations.json": _canonical_json(observations),
        "disposition.json": _canonical_json(disposition),
        "retrieval-inventory.json": _canonical_json(inventory),
        **successors,
    }
    return _manifest_payloads(
        ARTIFACT_ID,
        payloads,
        recorded_at=recorded_at,
        stage_birth_at=stage_birth_at,
    )


def _validate_temporal_payloads(
    payloads: dict[str, bytes], *, recorded_at: str, stage_birth_at: str
) -> None:
    recorded = _instant(recorded_at)
    stage_birth = _instant(stage_birth_at)
    now = datetime.now(timezone.utc)
    if not stage_birth <= recorded <= now:
        raise TemporalPublicationError(
            "publication time must follow stage birth and not exceed wall clock"
        )
    manifest = json.loads(payloads["manifest.json"])
    if (
        manifest["recorded_at"] != recorded_at
        or manifest["publication"]["stage_birth_at"] != stage_birth_at
    ):
        raise TemporalPublicationError("manifest publication time mismatch")
    for relative, raw in payloads.items():
        if not relative.endswith(".json") or relative == "manifest.json":
            continue
        document = json.loads(raw)
        for evidence in document.get("evidence", []):
            if _instant(evidence["retrieved_at"]) > recorded:
                raise TemporalPublicationError(
                    f"future evidence retrieved_at in {relative}: {evidence['key']}"
                )
        if relative == "retrieval-inventory.json":
            for request in document["accepted_capture_requests"]:
                if _instant(request["retrieved_at"]) > recorded:
                    raise TemporalPublicationError(
                        f"future inventory retrieved_at: {request['request_id']}"
                    )


PayloadBuilder = Callable[[str, str], dict[str, bytes]]


def _publish_dynamic(destination: Path, builder: PayloadBuilder) -> tuple[str, dict[str, bytes]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        recorded_at = manifest["recorded_at"]
        stage_birth_at = manifest["publication"]["stage_birth_at"]
        payloads = builder(recorded_at, stage_birth_at)
        _validate_temporal_payloads(
            payloads, recorded_at=recorded_at, stage_birth_at=stage_birth_at
        )
        previous._inspect_exact(destination, payloads)
        artifact_birth = _birth_instant(destination)
        if artifact_birth > _instant(recorded_at):
            raise TemporalPublicationError("artifact birth exceeds recorded_at")
        return "existing-identical", payloads

    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    stage_birth = _birth_instant(stage)
    recorded = datetime.now(timezone.utc)
    if recorded < stage_birth:
        previous._discard_stage(stage)
        raise TemporalPublicationError("wall clock precedes stage birth")
    stage_birth_at = _format_instant(stage_birth)
    recorded_at = _format_instant(recorded)
    payloads = builder(recorded_at, stage_birth_at)
    _validate_temporal_payloads(
        payloads, recorded_at=recorded_at, stage_birth_at=stage_birth_at
    )
    try:
        previous._write_stage(stage, payloads)
        previous._inspect_exact(stage, payloads)
        previous._promote_noreplace(stage, destination)
    except Exception:
        previous._discard_stage(stage)
        raise
    previous._inspect_exact(destination, payloads)
    artifact_birth = _birth_instant(destination)
    if artifact_birth > recorded:
        raise TemporalPublicationError("promoted artifact birth exceeds recorded_at")
    if datetime.now(timezone.utc) < recorded:
        raise TemporalPublicationError("recorded_at exceeds post-promotion wall clock")
    return "published", payloads


def publish_all(publication_root: Path = PUBLICATION_ROOT) -> dict[str, str]:
    v2_manifest = _verify_prior_publications()
    _verify_capture_tree()
    for witness in (SIMBIO_SEIA_WITNESS, SIMBIO_CONTEXT_WITNESS, FORTALEZA_WITNESS):
        _verify_capture_witness(witness)

    incident_status, incident_payloads = _publish_dynamic(
        publication_root / INCIDENT_ID,
        lambda recorded_at, stage_birth_at: _incident_payloads(
            recorded_at=recorded_at,
            stage_birth_at=stage_birth_at,
            v2_manifest=v2_manifest,
        ),
    )
    incident_manifest_sha256 = _sha256(incident_payloads["manifest.json"])
    artifact_status, _ = _publish_dynamic(
        publication_root / ARTIFACT_ID,
        lambda recorded_at, stage_birth_at: _v3_payloads(
            recorded_at=recorded_at,
            stage_birth_at=stage_birth_at,
            incident_manifest_sha256=incident_manifest_sha256,
        ),
    )
    return {"incident": incident_status, "assessment": artifact_status}


def main() -> None:
    print(json.dumps(publish_all(), sort_keys=True))


if __name__ == "__main__":
    main()
