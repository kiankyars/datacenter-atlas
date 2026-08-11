"""Publish the fail-closed temporal correction for the Europe/LatAm tranche."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import discard_release_stage, promote_noreplace, tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "source_artifacts"
SOURCE_ROOT = ROOT / "sources"
V1_ARTIFACT_ID = "europe-latam-official-discovery-2026-07-21-v1"
V1_ARTIFACT = ARTIFACT_ROOT / V1_ARTIFACT_ID
INCIDENT_ID = "europe-latam-official-discovery-temporal-incident-2026-07-21-v1"
INCIDENT = ARTIFACT_ROOT / INCIDENT_ID
V2_ARTIFACT_ID = "europe-latam-official-discovery-2026-07-21-v2"
V2_ARTIFACT = ARTIFACT_ROOT / V2_ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".europe-latam-official-discovery-temporal-v2.lock"
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/dc-europe-latam-official-20260721.eA43A2"
)

V1_ARTIFACT_FILES = {
    "README.md": (2379, "82f947edcebd15f9c9cdbf3f9b4c0e8e5728a3dbcb12d1517df6c512acea3453"),
    "identity-and-capacity-guardrails.json": (2571, "26bbe24475261fa28ddc0182371ee278ed9edc72effbe36e88f6dd9e3cf5527e"),
    "manifest.json": (1569, "af62e982f6cc4522a87e3717b0a7ae86ef19d3cc0616af393a83de4921093cdc"),
    "manifest.sha256": (80, "03dd10030c89e36dda0445c07725a68e7bd17f8ed462a9213aeb2a2346677344"),
    "retrieval-inventory.json": (6313, "21d34594bd0fe18b451acee0d5790d364a0ea5c4b4865e2c4fe661a445a1e74c"),
    "rights-and-disposition.json": (1256, "25dea8c38d5f61fb3006d62d601413ce417b6d8bd47dbf8785865e8220559e1d"),
    "source-snapshot.json": (7808, "af7b62744238f0455e3c59297b634c1d5bf3ff69b3a3390da811ac6b2b6c6262"),
}
V1_ARTIFACT_TREE_SHA256 = (
    "4f3fa8d9aaa79d0c30b858df9d33fb0a51c0653e63638f498161a1fb28d8c53c"
)
V1_RECORDED_AT = "2026-07-21T09:54:12Z"

SOURCE_SUCCESSORS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-21-arnes-maribor-construction-start-v2.json": {
        "origin": "curated-official-2026-07-21-arnes-maribor-construction-start.json",
        "origin_bytes": 8971,
        "origin_sha256": "24be5cec5cdb1df39a4287a65e39f41053bc40976a06fa77fa45be3a717d6dac",
        "country": "Slovenia",
        "campus": "curated:arnes-maribor-data-center-site",
        "project": "curated:arnes-maribor-data-center-site:source-scoped-development",
        "lifecycle": [
            "under_construction",
            "2025-05-06",
            "authoritative_construction_start",
        ],
        "capacity_estimates": 0,
    },
    "curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json": {
        "origin": "curated-official-2026-07-21-kio-second-guatemala-construction-start.json",
        "origin_bytes": 7862,
        "origin_sha256": "5265afc6c6c3ed8947eee54de73f31328accd1badf513500b39acf65278bad4f",
        "country": "Guatemala",
        "campus": "curated:kio-tec-guatemala-campus",
        "project": "curated:kio-tec-guatemala-campus:second-data-center",
        "lifecycle": [
            "under_construction",
            "2025-09-25",
            "authoritative_construction_start",
        ],
        "capacity_estimates": 2,
    },
}

CAPTURE_TIMES: dict[str, dict[str, Any]] = {
    "arnes_government_start": {
        "body_birth_epoch": 1784627270,
        "body_birth_utc": "2026-07-21T09:47:50Z",
        "writeout_birth_epoch": 1784627267,
        "writeout_birth_utc": "2026-07-21T09:47:47Z",
        "writeout_mtime_epoch": 1784627270,
        "completed_at": "2026-07-21T09:47:50Z",
        "server_http_date": "2026-07-21T09:47:48Z",
        "body": (27297, "6b5055e992e3da2a53ae3e4af8a9e99d6fe10be14605d6187edc30812e2ac2c7"),
        "headers": (733, "ff078061f84dc56c060f7d33c2f157d895033478b181eced8360cb1704663fe1"),
        "writeout": (19036, "eac4cd409b2e80c49ce74a5b77afa4f7ad3821721c66441f46ab401892b4b3d6"),
    },
    "arnes_project_page": {
        "body_birth_epoch": 1784627271,
        "body_birth_utc": "2026-07-21T09:47:51Z",
        "writeout_birth_epoch": 1784627270,
        "writeout_birth_utc": "2026-07-21T09:47:50Z",
        "writeout_mtime_epoch": 1784627272,
        "completed_at": "2026-07-21T09:47:52Z",
        "server_http_date": "2026-07-21T09:47:50Z",
        "body": (219856, "50a56d47914b2a37f2b87609eb2380d7b6e6eaf518e2266ffcf670f6b77bc381"),
        "headers": (649, "871f70c574659ec71bef11fc1c4373dec56e50bbeb20a3158be0bd4a36d5401d"),
        "writeout": (13155, "7b6496872a569b2f8a2ab4fb3e02d839332f6c21fed2fada0ceff8e5984a3472"),
    },
    "kio_gtm2_start": {
        "body_birth_epoch": 1784627272,
        "body_birth_utc": "2026-07-21T09:47:52Z",
        "writeout_birth_epoch": 1784627272,
        "writeout_birth_utc": "2026-07-21T09:47:52Z",
        "writeout_mtime_epoch": 1784627272,
        "completed_at": "2026-07-21T09:47:52Z",
        "server_http_date": "2026-07-21T03:57:50Z",
        "body": (90398, "fb51bca41741462937c17104bf7884a45330fac58e3caa93e44fcfafb16ec6dd"),
        "headers": (591, "53ec8da0ae8eb2e34da8c11b0592cce86893734427b0f66de22fecb0d7963556"),
        "writeout": (16690, "4b8a2eca2fefadfc7b98a7e9f92b0844d4d3b592fa7334e2cc51eeca6360e428"),
    },
}

CORRECTION_METADATA_FIELDS = {
    "capture_body_birth_utc",
    "capture_writeout_birth_utc",
    "capture_writeout_mtime_utc",
    "retrieval_completed_at",
    "retrieval_timestamp_basis",
    "server_http_date_used_as_retrieved_at",
    "supersedes_non_accepted_source_path",
    "temporal_correction",
    "raw_capture_reused_from_non_accepted_publication",
}

INCIDENT_CONTENT_FILES = ("README.md", "incident.json")
INCIDENT_CLOSED_FILES = frozenset(
    (*INCIDENT_CONTENT_FILES, "manifest.json", "manifest.sha256")
)
V2_CONTENT_FILES = (
    "README.md",
    "identity-and-capacity-guardrails.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
V2_CLOSED_FILES = frozenset((*V2_CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _file_tree(rows: list[dict[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"pinned ordinary file is absent: {path}")
    actual = (len(path.read_bytes()), _sha256(path))
    if actual != expected:
        raise SystemExit(f"pinned file differs: {path}: {actual!r}")


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(f"active publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _validate_v1_preserved() -> None:
    if (
        not V1_ARTIFACT.is_dir()
        or V1_ARTIFACT.is_symlink()
        or stat.S_IMODE(V1_ARTIFACT.stat().st_mode) != 0o555
        or tree_digest(V1_ARTIFACT) != V1_ARTIFACT_TREE_SHA256
    ):
        raise SystemExit("preserved v1 artifact differs")
    if {path.name for path in V1_ARTIFACT.iterdir()} != set(V1_ARTIFACT_FILES):
        raise SystemExit("preserved v1 artifact closure differs")
    for name, expected in V1_ARTIFACT_FILES.items():
        path = V1_ARTIFACT / name
        _pin(path, expected)
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise SystemExit(f"preserved v1 artifact file mode differs: {name}")
    manifest = json.loads((V1_ARTIFACT / "manifest.json").read_text())
    if manifest.get("recorded_at") != V1_RECORDED_AT:
        raise SystemExit("preserved v1 recorded_at differs")
    for spec in SOURCE_SUCCESSORS.values():
        _pin(
            SOURCE_ROOT / spec["origin"],
            (spec["origin_bytes"], spec["origin_sha256"]),
        )


def _validate_raw_capture() -> None:
    capture = resolve_external_capture(CAPTURE_TRASH)
    if not capture.is_dir() or capture.is_symlink():
        raise SystemExit("recoverable raw capture directory is absent")
    if stat.S_IMODE(capture.stat().st_mode) != 0o700:
        raise SystemExit("recoverable raw capture directory mode differs")
    packaged_capture = capture != CAPTURE_TRASH
    expected_names = {
        f"{request_id}.{suffix}"
        for request_id in CAPTURE_TIMES
        for suffix in ("body", "headers", "writeout")
    }
    if {path.name for path in capture.iterdir()} != expected_names:
        raise SystemExit("recoverable raw capture closure differs")
    for request_id, spec in CAPTURE_TIMES.items():
        for suffix in ("body", "headers", "writeout"):
            carrier = capture / f"{request_id}.{suffix}"
            _pin(carrier, spec[suffix])
            if stat.S_IMODE(carrier.stat().st_mode) != 0o644:
                raise SystemExit(f"capture carrier mode differs: {carrier.name}")
        body = capture / f"{request_id}.body"
        writeout = capture / f"{request_id}.writeout"
        if (
            not packaged_capture
            and int(body.stat().st_birthtime) != spec["body_birth_epoch"]
        ):
            raise SystemExit(f"body birth pin differs: {request_id}")
        if (
            not packaged_capture
            and int(writeout.stat().st_birthtime) != spec["writeout_birth_epoch"]
        ):
            raise SystemExit(f"writeout birth pin differs: {request_id}")
        if int(writeout.stat().st_mtime) != spec["writeout_mtime_epoch"]:
            raise SystemExit(f"writeout completion mtime pin differs: {request_id}")
        completed = datetime.fromtimestamp(writeout.stat().st_mtime, timezone.utc)
        if completed.replace(microsecond=0) != _parse_utc(spec["completed_at"]):
            raise SystemExit(f"completion timestamp differs: {request_id}")


def _semantic_source(document: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(document)
    for evidence in normalized["evidence"]:
        evidence["retrieved_at"] = "<retrieval-completion>"
        metadata = evidence["metadata"]
        metadata["capture_artifact_id"] = "<capture-artifact>"
        for field in CORRECTION_METADATA_FIELDS:
            metadata.pop(field, None)
    return normalized


def _source_successor_documents() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for successor_name, successor_spec in SOURCE_SUCCESSORS.items():
        origin_path = SOURCE_ROOT / successor_spec["origin"]
        origin = json.loads(origin_path.read_text(encoding="utf-8"))
        successor = deepcopy(origin)
        for evidence in successor["evidence"]:
            request_id = evidence["metadata"]["capture_request_id"]
            timing = CAPTURE_TIMES[request_id]
            evidence["retrieved_at"] = timing["completed_at"]
            metadata = evidence["metadata"]
            metadata["capture_artifact_id"] = V2_ARTIFACT_ID
            metadata["capture_body_birth_utc"] = timing["body_birth_utc"]
            metadata["capture_writeout_birth_utc"] = timing["writeout_birth_utc"]
            metadata["capture_writeout_mtime_utc"] = timing["completed_at"]
            metadata["retrieval_completed_at"] = timing["completed_at"]
            metadata["retrieval_timestamp_basis"] = (
                "UTC whole-second mtime of the completed curl writeout, sampled "
                "after curl returned"
            )
            metadata["server_http_date_used_as_retrieved_at"] = False
            metadata["supersedes_non_accepted_source_path"] = (
                f"sources/{successor_spec['origin']}"
            )
            metadata["temporal_correction"] = (
                "File birth is retained only as file-creation/start evidence. "
                "retrieved_at now uses completed curl writeout mtime."
            )
            metadata["raw_capture_reused_from_non_accepted_publication"] = (
                V1_ARTIFACT_ID
            )
        if _semantic_source(successor) != _semantic_source(origin):
            raise SystemExit(f"source successor changed factual semantics: {successor_name}")
        documents[successor_name] = successor
    return documents


def _validate_source_successor(
    path: Path, successor_name: str, *, require_final_name: bool = False
) -> dict[str, Any]:
    successor_spec = SOURCE_SUCCESSORS[successor_name]
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document) or document.get("schema_version") != "1.1":
        raise ValueError(f"source successor is not canonical schema 1.1: {successor_name}")
    origin = json.loads(
        (SOURCE_ROOT / successor_spec["origin"]).read_text(encoding="utf-8")
    )
    if _semantic_source(document) != _semantic_source(origin):
        raise ValueError(f"source successor factual semantics differ: {successor_name}")
    if (
        document["campus"]["stable_key"] != successor_spec["campus"]
        or document["project"]["stable_key"] != successor_spec["project"]
        or len(document["capacities"]) != successor_spec["capacity_estimates"]
    ):
        raise ValueError(f"source successor identity or capacity differs: {successor_name}")
    for evidence in document["evidence"]:
        request_id = evidence["metadata"]["capture_request_id"]
        timing = CAPTURE_TIMES[request_id]
        metadata = evidence["metadata"]
        if evidence["retrieved_at"] != timing["completed_at"]:
            raise ValueError(f"source successor retrieval completion differs: {request_id}")
        expected_metadata = {
            "capture_body_birth_utc": timing["body_birth_utc"],
            "capture_writeout_birth_utc": timing["writeout_birth_utc"],
            "capture_writeout_mtime_utc": timing["completed_at"],
            "retrieval_completed_at": timing["completed_at"],
            "server_http_date_used_as_retrieved_at": False,
            "supersedes_non_accepted_source_path": f"sources/{successor_spec['origin']}",
            "raw_capture_reused_from_non_accepted_publication": V1_ARTIFACT_ID,
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise ValueError(f"source successor timing metadata differs: {request_id}")
        if metadata.get("retrieval_timestamp_basis") != (
            "UTC whole-second mtime of the completed curl writeout, sampled after curl returned"
        ):
            raise ValueError(f"source successor completion basis differs: {request_id}")
        if metadata.get("response_http_date") != timing["server_http_date"]:
            raise ValueError(f"source successor server Date differs: {request_id}")
    if successor_name.startswith("curated-official-2026-07-21-arnes"):
        project_evidence = next(
            row
            for row in document["evidence"]
            if row["metadata"]["capture_request_id"] == "arnes_project_page"
        )
        if project_evidence["retrieved_at"] == CAPTURE_TIMES["arnes_project_page"][
            "body_birth_utc"
        ]:
            raise ValueError("Arnes project successor confused body birth with completion")
    if require_final_name and path.name != successor_name:
        raise ValueError("source successor final name differs")
    return document


def _validate_source_collisions() -> None:
    claimed_stable: set[str] = set()
    claimed_evidence: set[str] = set()
    for name in SOURCE_SUCCESSORS:
        document = json.loads((SOURCE_ROOT / name).read_text(encoding="utf-8"))
        claimed_stable.update(
            {document["campus"]["stable_key"], document["project"]["stable_key"]}
        )
        claimed_evidence.update(row["key"] for row in document["evidence"])
    permitted = {
        spec["origin"] for spec in SOURCE_SUCCESSORS.values()
    } | set(SOURCE_SUCCESSORS)
    collisions: dict[str, dict[str, list[str]]] = {}
    for other in SOURCE_ROOT.glob("*.json"):
        if other.name in permitted:
            continue
        try:
            document = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        other_stable = {
            entity["stable_key"]
            for entity in (document.get("campus"), document.get("project"))
            if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str)
        }
        other_evidence = {
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        }
        stable_overlap = sorted(claimed_stable & other_stable)
        evidence_overlap = sorted(claimed_evidence & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[other.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise ValueError(f"v2 source collision outside superseded v1 pair: {collisions!r}")


def _rows(stage: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    result = []
    for name in names:
        payload = (stage / name).read_bytes()
        result.append(
            {
                "bytes": len(payload),
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return result


def _write_incident_stage(stage: Path, recorded_at: str) -> None:
    readme = f"""# Europe/LatAm discovery temporal incident

This immutable incident marks the complete `{V1_ARTIFACT_ID}` publication set nonaccepted. Its retrieval inventory states that `retrieved_at` is the filesystem birth second of a completed response body. File birth is creation/start evidence, not completion evidence. The Arnes project response makes the defect observable: its body birth is 2026-07-21T09:47:51Z, while the completed curl writeout mtime is 2026-07-21T09:47:52Z.

The v1 artifact and both v1 curated source files remain byte-exact and unmodified. Coincidental same-second birth and completion for the Arnes government and KIO responses does not make the claimed method true. Neither v1 source may be selected independently as accepted evidence.

The corrective v2 publication uses completed curl writeout mtime for `retrieved_at`, retains body/writeout birth separately, retains the server HTTP Date separately, and changes no non-temporal project fact. This incident was staged before its real UTC recording time `{recorded_at}`, frozen, and atomically published without replacement.
"""
    incident = {
        "incident_id": INCIDENT_ID,
        "format": "datacenter-atlas-temporal-integrity-incident-v1",
        "recorded_at": recorded_at,
        "acceptance_status": "accepted_technical_incident_record",
        "cause": "The v1 publication misdescribed filesystem birth as response completion; one evidence retrieved_at was one second earlier than completed curl writeout mtime.",
        "policy": {
            "subject_acceptance": "Every listed v1 subject is nonaccepted.",
            "preservation": "The v1 artifact and source bytes remain immutable and are neither deleted nor mutated.",
            "downstream_use": "V1 subjects must not be selected as accepted inputs or integrated downstream.",
            "file_birth_semantics": "File birth is file-creation or request-start evidence only, never response completion evidence.",
            "completion_semantics": "Completed curl writeout mtime, sampled after curl returned, is the retrieval completion second.",
            "server_date_semantics": "The server HTTP Date is retained separately and is never substituted for local acquisition timing.",
        },
        "subjects": [
            {
                "subject_id": V1_ARTIFACT_ID,
                "path": f"source_artifacts/{V1_ARTIFACT_ID}",
                "acceptance_status": "non_accepted",
                "disposition": "rejected_preserved",
                "manifest_bytes": V1_ARTIFACT_FILES["manifest.json"][0],
                "manifest_sha256": V1_ARTIFACT_FILES["manifest.json"][1],
                "physical_tree_sha256": V1_ARTIFACT_TREE_SHA256,
                "recorded_at": V1_RECORDED_AT,
                "reason": "retrieval-inventory.json asserts a false file-birth-as-completion method.",
            },
            {
                "subject_id": "arnes-maribor-construction-start-v1-source",
                "path": "sources/curated-official-2026-07-21-arnes-maribor-construction-start.json",
                "acceptance_status": "non_accepted",
                "disposition": "rejected_preserved",
                "bytes": SOURCE_SUCCESSORS[
                    "curated-official-2026-07-21-arnes-maribor-construction-start-v2.json"
                ]["origin_bytes"],
                "sha256": SOURCE_SUCCESSORS[
                    "curated-official-2026-07-21-arnes-maribor-construction-start-v2.json"
                ]["origin_sha256"],
                "reason": "The Arnes project evidence records 09:47:51Z from body birth; completed curl writeout mtime is 09:47:52Z.",
            },
            {
                "subject_id": "kio-second-guatemala-construction-start-v1-source",
                "path": "sources/curated-official-2026-07-21-kio-second-guatemala-construction-start.json",
                "acceptance_status": "non_accepted",
                "disposition": "rejected_preserved",
                "bytes": SOURCE_SUCCESSORS[
                    "curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json"
                ]["origin_bytes"],
                "sha256": SOURCE_SUCCESSORS[
                    "curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json"
                ]["origin_sha256"],
                "reason": "The coupled v1 publication uses a false timing method even though KIO file birth and completion happen to share one whole second.",
            },
        ],
        "observable_timing_witness": {
            request_id: {
                "body_birth_utc": timing["body_birth_utc"],
                "writeout_birth_utc": timing["writeout_birth_utc"],
                "writeout_mtime_completed_at": timing["completed_at"],
                "server_http_date": timing["server_http_date"],
            }
            for request_id, timing in CAPTURE_TIMES.items()
        },
        "corrective_publication": {
            "artifact_id": V2_ARTIFACT_ID,
            "source_paths": [f"sources/{name}" for name in SOURCE_SUCCESSORS],
            "semantic_delta": "retrieval timing and provenance-basis metadata only",
            "integration": "none",
        },
    }
    (stage / "README.md").write_bytes(readme.encode())
    (stage / "incident.json").write_bytes(_canonical(incident))
    rows = _rows(stage, INCIDENT_CONTENT_FILES)
    manifest = {
        "artifact_id": INCIDENT_ID,
        "format": "datacenter-atlas-temporal-integrity-incident-manifest-v1",
        "recorded_at": recorded_at,
        "acceptance_status": "accepted_technical_incident_record",
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(INCIDENT_CLOSED_FILES),
        "non_accepted_subjects": 3,
        "release_integration": "none",
    }
    (stage / "manifest.json").write_bytes(_canonical(manifest))
    (stage / "manifest.sha256").write_text(
        f"{_sha256(stage / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )


def _source_records(
    source_documents: Mapping[str, Mapping[str, Any]], source_stage: Path
) -> list[dict[str, Any]]:
    records = []
    for name, document in source_documents.items():
        spec = SOURCE_SUCCESSORS[name]
        payload = (source_stage / name).read_bytes()
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "schema_version": "1.1",
                "country": spec["country"],
                "campus_stable_key": spec["campus"],
                "project_stable_key": spec["project"],
                "lifecycle_status": spec["lifecycle"][0],
                "lifecycle_as_of_date": spec["lifecycle"][1],
                "lifecycle_method": spec["lifecycle"][2],
                "current_status_as_of_research_date": "unknown",
                "capacity_estimate_count": spec["capacity_estimates"],
                "supersedes_non_accepted_source_path": f"sources/{spec['origin']}",
                "seeded": False,
            }
        )
    return records


def _write_v2_stage(
    stage: Path,
    recorded_at: str,
    source_records: list[dict[str, Any]],
    incident_manifest_sha256: str,
    incident_tree_sha256: str,
) -> None:
    v1_guardrails = json.loads(
        (V1_ARTIFACT / "identity-and-capacity-guardrails.json").read_text()
    )
    v1_inventory = json.loads(
        (V1_ARTIFACT / "retrieval-inventory.json").read_text()
    )
    v1_rights = json.loads(
        (V1_ARTIFACT / "rights-and-disposition.json").read_text()
    )
    v1_snapshot = json.loads((V1_ARTIFACT / "source-snapshot.json").read_text())

    guardrails = deepcopy(v1_guardrails)
    guardrails["artifact_id"] = V2_ARTIFACT_ID
    guardrails["recorded_at"] = recorded_at
    guardrails["temporal_integrity"] = {
        "retrieved_at_basis": "completed_curl_writeout_mtime",
        "file_birth_is_completion": False,
        "server_http_date_is_retrieval_time": False,
        "arnes_project_birth_completion_delta_seconds": 1,
        "incident_id": INCIDENT_ID,
        "v1_publication_accepted": False,
    }
    guardrails["lineage"]["excluded_non_accepted_lineage"] = [
        *guardrails["lineage"]["excluded_non_accepted_lineage"],
        f"source_artifacts/{V1_ARTIFACT_ID}",
        *[
            f"sources/{spec['origin']}" for spec in SOURCE_SUCCESSORS.values()
        ],
    ]

    inventory = deepcopy(v1_inventory)
    inventory["artifact_id"] = V2_ARTIFACT_ID
    inventory["recorded_at"] = recorded_at
    inventory["capture_protocol"] = (
        "No new network request was made for v2. Exact recoverable v1 raw captures "
        "were revalidated by hash and filesystem timing. retrieved_at is completed "
        "curl writeout mtime; body/writeout birth and server HTTP Date remain separate."
    )
    inventory["v2_direct_request_attempts"] = 0
    inventory["raw_capture_reused_by_hash"] = True
    inventory["retrieval_timestamp_policy"] = {
        "retrieved_at": "UTC whole-second mtime of completed curl writeout, sampled after curl returned",
        "body_birth": "file-creation evidence only",
        "writeout_birth": "file-creation or request-start evidence only",
        "server_http_date": "server-reported metadata only",
    }
    for request in inventory["controlled_http_requests"]:
        timing = CAPTURE_TIMES[request["request_id"]]
        request["retrieved_at"] = timing["completed_at"]
        request["retrieval_completed_at"] = timing["completed_at"]
        request["retrieval_timestamp_basis"] = (
            "UTC whole-second mtime of the completed curl writeout, sampled after curl returned"
        )
        request["capture_body_birth_utc"] = timing["body_birth_utc"]
        request["capture_writeout_birth_utc"] = timing["writeout_birth_utc"]
        request["capture_writeout_mtime_utc"] = timing["completed_at"]
        request["response_http_date"] = timing["server_http_date"]
        request["response_http_date_used_as_retrieved_at"] = False

    rights = deepcopy(v1_rights)
    rights["artifact_id"] = V2_ARTIFACT_ID
    rights["recorded_at"] = recorded_at
    rights["v2_network_requests"] = 0
    rights["raw_capture_reused_by_hash"] = True
    rights["raw_capture_source_publication"] = V1_ARTIFACT_ID
    rights["raw_capture_source_publication_accepted"] = False
    rights["raw_capture_reuse_scope"] = (
        "Exact raw bytes remain valid evidence inputs; only the v1 temporal metadata "
        "and publication acceptance were rejected. Raw bytes were neither copied, "
        "deleted, nor modified for v2."
    )

    snapshot = deepcopy(v1_snapshot)
    snapshot["artifact_id"] = V2_ARTIFACT_ID
    snapshot["recorded_at"] = recorded_at
    snapshot["source_records"] = source_records
    snapshot["supersedes_non_accepted_publication"] = {
        "artifact_id": V1_ARTIFACT_ID,
        "manifest_sha256": V1_ARTIFACT_FILES["manifest.json"][1],
        "physical_tree_sha256": V1_ARTIFACT_TREE_SHA256,
        "incident_id": INCIDENT_ID,
        "incident_manifest_sha256": incident_manifest_sha256,
        "incident_tree_sha256": incident_tree_sha256,
        "factual_semantic_delta": "none",
        "temporal_delta": "Arnes project retrieved_at corrected from body birth 09:47:51Z to completed writeout mtime 09:47:52Z; all evidence now states the correct timing basis.",
    }
    snapshot["excluded_non_accepted_lineage"] = [
        *snapshot["excluded_non_accepted_lineage"],
        f"source_artifacts/{V1_ARTIFACT_ID}",
        *[
            f"sources/{spec['origin']}" for spec in SOURCE_SUCCESSORS.values()
        ],
    ]

    readme = f"""# Europe and Central America official-source discovery tranche v2

This immutable v2 artifact is the sole accepted form of the two-record tranche. It preserves the Arnes Maribor and KIO second-Guatemala project facts while correcting retrieval timing only. The complete v1 publication set is nonaccepted under `{INCIDENT_ID}` and remains byte-exact.

`retrieved_at` now equals the UTC whole-second mtime of the completed curl writeout sampled after curl returned: Arnes government 09:47:50Z, Arnes project 09:47:52Z, and KIO 09:47:52Z. Body and writeout births are retained separately as creation/start evidence. Server HTTP Date is retained separately and is never used as local retrieval time.

The observable Arnes project witness prevents future birth/completion confusion: body birth 09:47:51Z differs from completed writeout mtime 09:47:52Z. No non-temporal identity, lifecycle, role, capacity, workload, location, rights, or country-screen fact changed.

The artifact was created in a unique sibling stage, assigned real UTC `{recorded_at}` only after the incident, source, and artifact stages existed, validated against birth and wall clock, frozen, and atomically published without replacement. Integration remains none for seed, release, construction timeline, federation, identity, coordinates, coverage ledger, and downstream products.
"""
    documents = {
        "README.md": readme.encode(),
        "identity-and-capacity-guardrails.json": _canonical(guardrails),
        "retrieval-inventory.json": _canonical(inventory),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }
    for name, payload in documents.items():
        (stage / name).write_bytes(payload)
    rows = _rows(stage, V2_CONTENT_FILES)
    manifest = {
        "artifact_id": V2_ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v2",
        "recorded_at": recorded_at,
        "acceptance_status": "accepted_temporal_successor",
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(V2_CLOSED_FILES),
        "curated_source_records": 2,
        "successful_raw_captures_reused": 3,
        "v2_network_requests": 0,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "supersedes_non_accepted_origin": {
            "artifact_id": V1_ARTIFACT_ID,
            "manifest_sha256": V1_ARTIFACT_FILES["manifest.json"][1],
            "physical_tree_sha256": V1_ARTIFACT_TREE_SHA256,
            "incident_id": INCIDENT_ID,
            "incident_manifest_sha256": incident_manifest_sha256,
            "incident_tree_sha256": incident_tree_sha256,
        },
        "release_integration": "none",
        "open_seed_integration": "none",
        "downstream_product_integration": "none",
    }
    (stage / "manifest.json").write_bytes(_canonical(manifest))
    (stage / "manifest.sha256").write_text(
        f"{_sha256(stage / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )


def _validate_frozen_bundle(
    path: Path,
    *,
    closed_files: frozenset[str],
    content_files: tuple[str, ...],
    require_frozen: bool,
    validation_wall_clock: datetime | None,
) -> dict[str, Any]:
    if not path.is_dir() or path.is_symlink():
        raise ValueError("bundle must be an ordinary directory")
    if require_frozen and stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise ValueError("bundle directory is not frozen")
    entries = {item.name: item for item in path.iterdir()}
    if set(entries) != closed_files:
        raise ValueError("bundle closed file set differs")
    if any(item.is_symlink() or not item.is_file() for item in entries.values()):
        raise ValueError("bundle contains a non-ordinary file")
    if require_frozen and any(
        stat.S_IMODE(item.stat().st_mode) != 0o444 for item in entries.values()
    ):
        raise ValueError("bundle file mode differs")
    for name in content_files:
        if name.endswith(".json"):
            raw = entries[name].read_bytes()
            if raw != _canonical(json.loads(raw)):
                raise ValueError(f"bundle JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise ValueError("bundle manifest is not canonical")
    if (
        set(manifest.get("closed_file_set", [])) != closed_files
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise ValueError("bundle manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            row["bytes"],
            row["sha256"],
        ):
            raise ValueError(f"bundle file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
    ):
        raise ValueError("bundle manifest checksum differs")
    recorded_at = _parse_utc(manifest["recorded_at"])
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
    if birth > recorded_at or recorded_at > wall_clock:
        raise ValueError("bundle temporal boundary differs")
    return manifest


def validate_incident(
    path: Path = INCIDENT,
    *,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _validate_v1_preserved()
    manifest = _validate_frozen_bundle(
        path,
        closed_files=INCIDENT_CLOSED_FILES,
        content_files=INCIDENT_CONTENT_FILES,
        require_frozen=require_frozen,
        validation_wall_clock=validation_wall_clock,
    )
    incident = json.loads((path / "incident.json").read_text())
    if (
        manifest.get("artifact_id") != INCIDENT_ID
        or manifest.get("acceptance_status") != "accepted_technical_incident_record"
        or incident.get("acceptance_status") != "accepted_technical_incident_record"
        or incident.get("recorded_at") != manifest.get("recorded_at")
        or any(row.get("acceptance_status") != "non_accepted" for row in incident["subjects"])
    ):
        raise ValueError("temporal incident contract differs")
    return manifest


def validate_v2_artifact(
    path: Path = V2_ARTIFACT,
    *,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    _validate_v1_preserved()
    _validate_raw_capture()
    incident_manifest = validate_incident(validation_wall_clock=validation_wall_clock)
    source_records = []
    for name, spec in SOURCE_SUCCESSORS.items():
        source_path = SOURCE_ROOT / name
        _validate_source_successor(source_path, name, require_final_name=True)
        payload = source_path.read_bytes()
        source_records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "schema_version": "1.1",
                "country": spec["country"],
                "campus_stable_key": spec["campus"],
                "project_stable_key": spec["project"],
                "lifecycle_status": spec["lifecycle"][0],
                "lifecycle_as_of_date": spec["lifecycle"][1],
                "lifecycle_method": spec["lifecycle"][2],
                "current_status_as_of_research_date": "unknown",
                "capacity_estimate_count": spec["capacity_estimates"],
                "supersedes_non_accepted_source_path": f"sources/{spec['origin']}",
                "seeded": False,
            }
        )
    _validate_source_collisions()
    manifest = _validate_frozen_bundle(
        path,
        closed_files=V2_CLOSED_FILES,
        content_files=V2_CONTENT_FILES,
        require_frozen=require_frozen,
        validation_wall_clock=validation_wall_clock,
    )
    if (
        manifest.get("artifact_id") != V2_ARTIFACT_ID
        or manifest.get("acceptance_status") != "accepted_temporal_successor"
        or manifest.get("release_integration") != "none"
        or manifest.get("open_seed_integration") != "none"
    ):
        raise ValueError("v2 artifact manifest contract differs")
    predecessor = manifest["supersedes_non_accepted_origin"]
    if (
        predecessor["artifact_id"] != V1_ARTIFACT_ID
        or predecessor["manifest_sha256"] != V1_ARTIFACT_FILES["manifest.json"][1]
        or predecessor["physical_tree_sha256"] != V1_ARTIFACT_TREE_SHA256
        or predecessor["incident_id"] != INCIDENT_ID
        or predecessor["incident_manifest_sha256"]
        != _sha256(INCIDENT / "manifest.json")
        or incident_manifest["artifact_id"] != INCIDENT_ID
    ):
        raise ValueError("v2 predecessor mapping differs")
    snapshot = json.loads((path / "source-snapshot.json").read_text())
    if snapshot["source_records"] != source_records:
        raise ValueError("v2 source snapshot pins differ")
    inventory = json.loads((path / "retrieval-inventory.json").read_text())
    recorded_at = _parse_utc(manifest["recorded_at"])
    for request in inventory["controlled_http_requests"]:
        timing = CAPTURE_TIMES[request["request_id"]]
        if (
            request["retrieved_at"] != timing["completed_at"]
            or request["capture_body_birth_utc"] != timing["body_birth_utc"]
            or request["capture_writeout_birth_utc"] != timing["writeout_birth_utc"]
            or request["capture_writeout_mtime_utc"] != timing["completed_at"]
            or request["response_http_date"] != timing["server_http_date"]
            or request["response_http_date_used_as_retrieved_at"] is not False
            or _parse_utc(request["retrieved_at"]) > recorded_at
        ):
            raise ValueError(f"v2 retrieval timing differs: {request['request_id']}")
    arnes_project = next(
        row
        for row in inventory["controlled_http_requests"]
        if row["request_id"] == "arnes_project_page"
    )
    if arnes_project["retrieved_at"] == arnes_project["capture_body_birth_utc"]:
        raise ValueError("v2 artifact confused Arnes project birth with completion")
    return manifest


def _capture_after_stage_birth(stages: list[Path]) -> str:
    latest_birth = max(stage.stat().st_birthtime for stage in stages)
    deadline = time.time() + 1.1
    rollover = math.ceil(latest_birth)
    while time.time() < rollover:
        if time.time() > deadline:
            raise SystemExit("filesystem rollover exceeded one second")
        time.sleep(0.005)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _offline_import(source_stage: Path, recorded_at: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        for _ in range(2):
            for name in SOURCE_SUCCESSORS:
                CuratedOfficialSourceAdapterV11().import_file(
                    connection,
                    source_stage / name,
                    recorded_at=recorded_at,
                )
        validate_database(connection)


def build() -> dict[str, Any]:
    _validate_v1_preserved()
    _validate_raw_capture()
    destinations = [INCIDENT, V2_ARTIFACT, *[SOURCE_ROOT / name for name in SOURCE_SUCCESSORS]]
    for destination in destinations:
        if destination.exists() or destination.is_symlink():
            raise SystemExit(f"correction output already exists; refusing replacement: {destination}")
    with publication_lock():
        incident_stage = Path(
            tempfile.mkdtemp(prefix=f".{INCIDENT_ID}.", dir=ARTIFACT_ROOT)
        )
        source_stage = Path(
            tempfile.mkdtemp(prefix=".europe-latam-source-v2.", dir=SOURCE_ROOT)
        )
        v2_stage = Path(
            tempfile.mkdtemp(prefix=f".{V2_ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
        )
        incident_published = False
        v2_published = False
        try:
            recorded_at = _capture_after_stage_birth(
                [incident_stage, source_stage, v2_stage]
            )
            source_documents = _source_successor_documents()
            for name, document in source_documents.items():
                (source_stage / name).write_bytes(_canonical(document))
                (source_stage / name).chmod(0o644)
                _validate_source_successor(source_stage / name, name)
            _offline_import(source_stage, recorded_at)
            _write_incident_stage(incident_stage, recorded_at)
            for item in incident_stage.iterdir():
                item.chmod(0o444)
            incident_stage.chmod(0o555)
            validate_incident(
                incident_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            incident_manifest_sha256 = _sha256(incident_stage / "manifest.json")
            incident_tree_sha256 = tree_digest(incident_stage)
            records = _source_records(source_documents, source_stage)
            _write_v2_stage(
                v2_stage,
                recorded_at,
                records,
                incident_manifest_sha256,
                incident_tree_sha256,
            )
            for item in v2_stage.iterdir():
                item.chmod(0o444)
            v2_stage.chmod(0o555)

            promote_noreplace(incident_stage, INCIDENT)
            incident_published = True
            for name in SOURCE_SUCCESSORS:
                promote_noreplace(source_stage / name, SOURCE_ROOT / name)
            validate_v2_artifact(
                v2_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            promote_noreplace(v2_stage, V2_ARTIFACT)
            v2_published = True
            manifest = validate_v2_artifact(
                V2_ARTIFACT,
                validation_wall_clock=datetime.now(timezone.utc),
            )
        finally:
            if not incident_published:
                discard_release_stage(incident_stage)
            discard_release_stage(source_stage)
            if not v2_published:
                discard_release_stage(v2_stage)
    return {
        "incident_id": INCIDENT_ID,
        "incident_manifest_sha256": _sha256(INCIDENT / "manifest.json"),
        "incident_tree_sha256": tree_digest(INCIDENT),
        "artifact_id": V2_ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(V2_ARTIFACT / "manifest.json"),
        "tree_sha256": tree_digest(V2_ARTIFACT),
        "source_records": {
            name: {
                "bytes": len((SOURCE_ROOT / name).read_bytes()),
                "sha256": _sha256(SOURCE_ROOT / name),
            }
            for name in SOURCE_SUCCESSORS
        },
        "integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
