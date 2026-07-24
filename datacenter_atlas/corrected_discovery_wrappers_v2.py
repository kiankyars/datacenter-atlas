"""Build honest timestamp-corrected v2 wrappers for three rejected audits."""

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

from .open_seed_v56 import discard_release_stage, promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "source_artifacts"
PUBLICATION_LOCK = ROOT / ".corrected-discovery-wrappers-v2.lock"
INCIDENT = ARTIFACT_ROOT / "temporal-integrity-incident-2026-07-21-v1"
INCIDENT_MANIFEST_SHA256 = (
    "7876a3134daba719e7fd25afc330301ce7909ee91cdcecf118bc7340dc79c8f7"
)
INCIDENT_TREE_SHA256 = (
    "954cdcc7fa08a5cade9e4e64785f4fec3415743898885f09dfd9ad4c6b8448a7"
)

CONTENT_FILES = (
    "README.md",
    "identity-and-capacity-guardrails.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

WRAPPER_CONFIGS: dict[str, dict[str, Any]] = {
    "global-underrepresented-official-discovery-2026-07-21-v2": {
        "origin_id": "global-underrepresented-official-discovery-2026-07-21-v1",
        "origin_manifest_bytes": 1_364,
        "origin_manifest_sha256": (
            "2a55ae530cdb478fd922d6fad30ce836682671cb0fed95a040d2788e6292c7be"
        ),
        "origin_declared_tree_sha256": (
            "bf11d589deb0d3161254bbd688badbb859e419c4ff7a4458b7a0927fc323a07d"
        ),
        "origin_physical_tree_sha256": (
            "a68dab941f820fcb0caf4ab4003d0f3cb9028c68eaa0071fda82be3e33daf9f4"
        ),
        "origin_snapshot_sha256": (
            "e58a912dbc6a278872fa030fd684480ff1d50284538736fe79df52d1e9c49927"
        ),
        "rejected_recorded_at": "2026-07-21T08:15:00Z",
        "incident_subject_id": "global-underrepresented-official-discovery-v1",
        "open_seed_integration": "lineage_only",
    },
    "second-underrepresented-official-discovery-2026-07-21-v2": {
        "origin_id": "second-underrepresented-official-discovery-2026-07-21-v1",
        "origin_manifest_bytes": 1_423,
        "origin_manifest_sha256": (
            "df5e44d95af1fe7b81c10f3d58006b4db6cbe68816aa502673b93c863c1b9750"
        ),
        "origin_declared_tree_sha256": (
            "1a918b5045f90dbe7c6c66f9229fd7668bcb04979def38677d000017997c8cff"
        ),
        "origin_physical_tree_sha256": (
            "be65bd121c9ea3f74ad2f400287ff22a6cdcfb4df4cf97c4c41aa8ca77473b5e"
        ),
        "origin_snapshot_sha256": (
            "f96206e36891819b224d936bdf5fe9fdd6931d92d1ffd9b86bab62c1a477a349"
        ),
        "rejected_recorded_at": "2026-07-21T09:00:00Z",
        "incident_subject_id": "second-underrepresented-official-discovery-v1",
        "open_seed_integration": "lineage_only",
    },
    "gap-region-official-discovery-2026-07-21-v2": {
        "origin_id": "gap-region-official-discovery-2026-07-21-v1",
        "origin_manifest_bytes": 1_416,
        "origin_manifest_sha256": (
            "39f7bc33d99e9f65bddbb32cff711c2d784e7abb6d783afe9824e4a37da6d123"
        ),
        "origin_declared_tree_sha256": (
            "b8d0f7bd51fa6208c7382ccf241a161498a8befe4d342729da3b8321cdaa5903"
        ),
        "origin_physical_tree_sha256": (
            "c0c5dfdc745dcfb676f069436b9ae88e5132aa491dfcffe8464a0dd3f8df857c"
        ),
        "origin_snapshot_sha256": (
            "bf1f8743efb3d421c02496531a45dc29be490f94453d40efc2e79812810f4ea8"
        ),
        "rejected_recorded_at": "2026-07-21T09:00:00Z",
        "incident_subject_id": "gap-region-official-discovery-v1",
        "open_seed_integration": "none",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_document(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _file_tree(rows: list[dict[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


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


def _incident_subjects() -> dict[str, Mapping[str, Any]]:
    if (
        _sha256(INCIDENT / "manifest.json") != INCIDENT_MANIFEST_SHA256
        or tree_digest(INCIDENT) != INCIDENT_TREE_SHA256
    ):
        raise SystemExit("accepted temporal incident pin differs")
    incident = json.loads((INCIDENT / "incident.json").read_text(encoding="utf-8"))
    subjects = {row["subject_id"]: row for row in incident["subjects"]}
    if len(subjects) != 7 or any(
        row.get("acceptance_status") != "non_accepted" for row in subjects.values()
    ):
        raise SystemExit("temporal incident rejection set differs")
    return subjects


def _validate_origin(wrapper_id: str, config: Mapping[str, Any]) -> Path:
    origin = ARTIFACT_ROOT / config["origin_id"]
    if (
        not origin.is_dir()
        or origin.is_symlink()
        or stat.S_IMODE(origin.stat().st_mode) != 0o555
        or tree_digest(origin) != config["origin_physical_tree_sha256"]
    ):
        raise SystemExit(f"rejected origin wrapper pin differs: {wrapper_id}")
    entries = {path.name: path for path in origin.iterdir()}
    if set(entries) != CLOSED_FILES or any(
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != 0o444
        for path in entries.values()
    ):
        raise SystemExit(f"rejected origin wrapper closure differs: {wrapper_id}")
    manifest_raw = entries["manifest.json"].read_bytes()
    if (
        len(manifest_raw) != config["origin_manifest_bytes"]
        or hashlib.sha256(manifest_raw).hexdigest()
        != config["origin_manifest_sha256"]
    ):
        raise SystemExit(f"rejected origin manifest pin differs: {wrapper_id}")
    manifest = json.loads(manifest_raw)
    if (
        set(manifest["closed_file_set"]) != CLOSED_FILES
        or manifest["tree_sha256"] != config["origin_declared_tree_sha256"]
        or _file_tree(manifest["files"]) != manifest["tree_sha256"]
    ):
        raise SystemExit(f"rejected origin manifest contract differs: {wrapper_id}")
    snapshot = entries["source-snapshot.json"]
    if (
        _sha256(snapshot) != config["origin_snapshot_sha256"]
        or json.loads(snapshot.read_text())["recorded_at"]
        != config["rejected_recorded_at"]
    ):
        raise SystemExit(f"rejected origin snapshot pin differs: {wrapper_id}")
    subject = _incident_subjects().get(config["incident_subject_id"])
    if subject is None or subject.get("acceptance_status") != "non_accepted":
        raise SystemExit(f"origin lacks explicit incident rejection: {wrapper_id}")
    return origin


def _corrected_document(
    document: Mapping[str, Any], *, origin_id: str, wrapper_id: str, recorded_at: str
) -> dict[str, Any]:
    corrected = deepcopy(document)
    if corrected.get("artifact_id") == origin_id:
        corrected["artifact_id"] = wrapper_id
    if "recorded_at" in corrected:
        corrected["recorded_at"] = recorded_at
    return corrected


def _semantic_document(
    document: Mapping[str, Any], *, origin_id: str, wrapper_id: str
) -> dict[str, Any]:
    normalized = deepcopy(document)
    if normalized.get("artifact_id") in {origin_id, wrapper_id}:
        normalized["artifact_id"] = "<wrapper-id>"
    if "recorded_at" in normalized:
        normalized["recorded_at"] = "<recorded-at>"
    return normalized


def _write_wrapper_stage(
    stage: Path, wrapper_id: str, config: Mapping[str, Any], recorded_at: str
) -> None:
    if any(stage.iterdir()):
        raise SystemExit(f"corrected wrapper stage is not empty: {wrapper_id}")
    origin = _validate_origin(wrapper_id, config)
    (stage / "README.md").write_bytes((origin / "README.md").read_bytes())
    for filename in CONTENT_FILES[1:]:
        document = json.loads((origin / filename).read_text(encoding="utf-8"))
        corrected = _corrected_document(
            document,
            origin_id=config["origin_id"],
            wrapper_id=wrapper_id,
            recorded_at=recorded_at,
        )
        (stage / filename).write_bytes(_canonical_document(corrected))
    rows = []
    for filename in CONTENT_FILES:
        payload = (stage / filename).read_bytes()
        rows.append(
            {
                "bytes": len(payload),
                "path": filename,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    origin_manifest = json.loads((origin / "manifest.json").read_text())
    manifest = {
        "artifact_id": wrapper_id,
        "format": "datacenter-atlas-corrected-official-source-wrapper-v2",
        "recorded_at": recorded_at,
        "acceptance_status": "accepted_corrective_wrapper",
        "supersedes_non_accepted_origin": {
            "artifact_id": config["origin_id"],
            "manifest_bytes": config["origin_manifest_bytes"],
            "manifest_sha256": config["origin_manifest_sha256"],
            "physical_tree_sha256": config["origin_physical_tree_sha256"],
            "rejected_recorded_at": config["rejected_recorded_at"],
            "incident_manifest_sha256": INCIDENT_MANIFEST_SHA256,
            "incident_tree_sha256": INCIDENT_TREE_SHA256,
        },
        "retained_origin_ids": [config["origin_id"]],
        "retained_origin_id_semantics": (
            "Immutable curated-source capture_artifact_id and cross-wrapper origin "
            "references remain factual provenance only and are accepted solely "
            "through this explicit v2 supersession mapping."
        ),
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "curated_source_records": origin_manifest.get("curated_source_records"),
        "raw_capture_redistributed": origin_manifest["raw_capture_redistributed"],
        "release_integration": "none",
        "open_seed_integration": config["open_seed_integration"],
        "factual_semantic_delta_from_origin": "none",
        "corrected_fields": ["artifact_id", "recorded_at"],
    }
    (stage / "manifest.json").write_bytes(_canonical_document(manifest))
    manifest_hash = _sha256(stage / "manifest.json")
    (stage / "manifest.sha256").write_text(
        f"{manifest_hash}  manifest.json\n", encoding="utf-8"
    )


def validate_corrected_wrapper(
    wrapper_id: str,
    path: Path | None = None,
    *,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    config = WRAPPER_CONFIGS[wrapper_id]
    origin = _validate_origin(wrapper_id, config)
    wrapper = path or ARTIFACT_ROOT / wrapper_id
    if not wrapper.is_dir() or wrapper.is_symlink():
        raise ValueError(f"corrected wrapper must be an ordinary directory: {wrapper_id}")
    if require_frozen and stat.S_IMODE(wrapper.stat().st_mode) != 0o555:
        raise ValueError(f"corrected wrapper mode differs: {wrapper_id}")
    entries = {item.name: item for item in wrapper.iterdir()}
    if set(entries) != CLOSED_FILES or any(
        item.is_symlink() or not item.is_file() for item in entries.values()
    ):
        raise ValueError(f"corrected wrapper file closure differs: {wrapper_id}")
    if require_frozen and any(
        stat.S_IMODE(item.stat().st_mode) != 0o444 for item in entries.values()
    ):
        raise ValueError(f"corrected wrapper file mode differs: {wrapper_id}")
    for filename in CONTENT_FILES[1:]:
        raw = entries[filename].read_bytes()
        document = json.loads(raw)
        if raw != _canonical_document(document):
            raise ValueError(f"corrected wrapper JSON is not canonical: {filename}")
        origin_document = json.loads((origin / filename).read_text(encoding="utf-8"))
        if _semantic_document(
            document, origin_id=config["origin_id"], wrapper_id=wrapper_id
        ) != _semantic_document(
            origin_document, origin_id=config["origin_id"], wrapper_id=wrapper_id
        ):
            raise ValueError(f"corrected wrapper changed factual semantics: {filename}")
    if entries["README.md"].read_bytes() != (origin / "README.md").read_bytes():
        raise ValueError(f"corrected wrapper changed README evidence: {wrapper_id}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical_document(manifest):
        raise ValueError(f"corrected wrapper manifest is not canonical: {wrapper_id}")
    if (
        manifest.get("artifact_id") != wrapper_id
        or manifest.get("acceptance_status") != "accepted_corrective_wrapper"
        or manifest.get("factual_semantic_delta_from_origin") != "none"
        or manifest.get("release_integration") != "none"
        or manifest.get("open_seed_integration") != config["open_seed_integration"]
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise ValueError(f"corrected wrapper manifest contract differs: {wrapper_id}")
    predecessor = manifest.get("supersedes_non_accepted_origin", {})
    expected_predecessor = {
        "artifact_id": config["origin_id"],
        "manifest_bytes": config["origin_manifest_bytes"],
        "manifest_sha256": config["origin_manifest_sha256"],
        "physical_tree_sha256": config["origin_physical_tree_sha256"],
        "rejected_recorded_at": config["rejected_recorded_at"],
        "incident_manifest_sha256": INCIDENT_MANIFEST_SHA256,
        "incident_tree_sha256": INCIDENT_TREE_SHA256,
    }
    if predecessor != expected_predecessor:
        raise ValueError(f"corrected wrapper predecessor pin differs: {wrapper_id}")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            row["bytes"],
            row["sha256"],
        ):
            raise ValueError(f"corrected wrapper file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
    ):
        raise ValueError(f"corrected wrapper checksum differs: {wrapper_id}")
    recorded_at = _parse_utc(manifest["recorded_at"])
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot.get("recorded_at") != manifest["recorded_at"]:
        raise ValueError(f"corrected wrapper timestamp carriers differ: {wrapper_id}")
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    birth = datetime.fromtimestamp(wrapper.stat().st_birthtime, timezone.utc)
    if birth > recorded_at or recorded_at > wall_clock:
        raise ValueError(f"corrected wrapper temporal boundary differs: {wrapper_id}")
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


def build_corrected_discovery_wrappers_v2() -> dict[str, Any]:
    """Build and freeze all three corrected wrappers in one wall-clock capture."""

    for wrapper_id, config in WRAPPER_CONFIGS.items():
        _validate_origin(wrapper_id, config)
        target = ARTIFACT_ROOT / wrapper_id
        if target.exists() or target.is_symlink():
            raise SystemExit(f"corrected wrapper already exists: {target}")
    with publication_lock():
        stages = {
            wrapper_id: Path(
                tempfile.mkdtemp(prefix=f".{wrapper_id}.", dir=ARTIFACT_ROOT)
            )
            for wrapper_id in WRAPPER_CONFIGS
        }
        published: set[str] = set()
        try:
            recorded_at = _capture_after_stage_birth(list(stages.values()))
            for wrapper_id, config in WRAPPER_CONFIGS.items():
                stage = stages[wrapper_id]
                _write_wrapper_stage(stage, wrapper_id, config, recorded_at)
                for item in stage.iterdir():
                    item.chmod(0o444)
                stage.chmod(0o555)
                validate_corrected_wrapper(wrapper_id, stage)
            for wrapper_id, stage in stages.items():
                promote_noreplace(stage, ARTIFACT_ROOT / wrapper_id)
                published.add(wrapper_id)
            for wrapper_id in WRAPPER_CONFIGS:
                validate_corrected_wrapper(wrapper_id)
        finally:
            for wrapper_id, stage in stages.items():
                if wrapper_id not in published:
                    discard_release_stage(stage)
    return {
        wrapper_id: {
            "manifest_sha256": _sha256(ARTIFACT_ROOT / wrapper_id / "manifest.json"),
            "recorded_at": json.loads(
                (ARTIFACT_ROOT / wrapper_id / "manifest.json").read_text()
            )["recorded_at"],
            "tree_sha256": tree_digest(ARTIFACT_ROOT / wrapper_id),
        }
        for wrapper_id in WRAPPER_CONFIGS
    }


def main() -> int:
    print(json.dumps(build_corrected_discovery_wrappers_v2(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
