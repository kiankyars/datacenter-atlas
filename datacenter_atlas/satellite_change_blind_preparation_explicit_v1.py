"""Frozen metadata-free visual-review preparation for explicit-v1 pixels.

This carrier copies only four PNG views for each of the eleven accepted
review-only machine-change jobs into a deterministic, randomized neutral-ID
order.  It intentionally withholds queue IDs, source paths, reports, catalog
metadata, identities, status, and all capacity/power fields.  A later analyst
review may unseal lineage only after visual judgments have been fixed.
"""

from __future__ import annotations

import ctypes
from datetime import UTC, datetime, timedelta
import errno
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
import tempfile
import time
from typing import Any, Mapping

from . import satellite_change_explicit_v1_disposition as disposition


class ExplicitV1BlindPreparationError(ValueError):
    """Raised when source, blinding, or frozen publication drifts."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PREPARATION_ID = "2026-07-21-open-seed-v71-active-explicit-11-blind-v1"
OUTPUT_PATH = PACKAGE_ROOT / "satellite_change_preparation" / PREPARATION_ID
SOURCE_RUN_PATH = disposition.CHANGE_RUN_PATH
SOURCE_DISPOSITION_PATH = disposition.DISPOSITION_PATH
SOURCE_DISPOSITION_MANIFEST_SHA256 = (
    "81117523744d802d50ad08d65d4192c1673b0508b421a44b3e969b6e268a00cc"
)
SOURCE_DISPOSITION_TREE_SHA256 = (
    "96d24ac0a97f6165f2def1271efb94d00095349c44bbe07d2b31ceab767d495c"
)
SOURCE_CHANGE_MANIFEST_SHA256 = disposition.CHANGE_MANIFEST_SHA256
SOURCE_CHANGE_TREE_SHA256 = disposition.CHANGE_TREE_SHA256
SOURCE_CHANGE_FILES = disposition.CHANGE_FILE_COUNT
SOURCE_CHANGE_BYTES = 19_106_330
SOURCE_QUEUE_IDS = disposition.SELECTED_QUEUE_IDS
SOURCE_JOB_COUNT = len(SOURCE_QUEUE_IDS)
ORDER_SALT = "dc-atlas-explicit-v1-blind-order-2026-07-21-v1"
ORDER_ALGORITHM = "ascending_sha256_utf8_salt_nul_queue_id"
BLIND_ID_PREFIX = "V71-X"
VISUAL_FILENAMES = (
    "before.png",
    "after.png",
    "comparison.png",
    "change-overlay.png",
)
PNG_FORBIDDEN_METADATA_CHUNKS = frozenset({b"eXIf", b"iTXt", b"tEXt", b"zTXt"})
DEFINITION_FILENAME = "definition.json"
UNITS_FILENAME = "review-units.jsonl"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = PACKAGE_ROOT / "satellite_change_blind_preparation_explicit_v1.py"
CLI_PATH = PACKAGE_ROOT / "scripts/build_satellite_change_blind_preparation_explicit_v1.py"

GUARDRAILS = {
    "analyst_identity_metadata_exposed": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_status_claim_created": False,
    "current_status_claim_created": False,
    "data_centre_identity_claim_created": False,
    "data_centre_type_claim_created": False,
    "energy_claim_created": False,
    "imagery_construction_truth_claim_created": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "pue_claim_created": False,
    "site_count_claim_created": False,
    "unique_site_claim_created": False,
    "workload_claim_created": False,
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _strict_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExplicitV1BlindPreparationError(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise ExplicitV1BlindPreparationError(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitV1BlindPreparationError(f"{label} is not valid JSON") from error


def _timestamp(value: str, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value:
        raise ExplicitV1BlindPreparationError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExplicitV1BlindPreparationError(
            f"{label} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ExplicitV1BlindPreparationError(f"{label} must be UTC")
    canonical = parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    return canonical, parsed.astimezone(UTC)


def suggested_generated_at() -> str:
    """Return a publication time far enough ahead to stage all bytes."""

    target = datetime.now(UTC) + timedelta(seconds=120)
    return target.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _exact_file(path: Path, expected_sha256: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV1BlindPreparationError(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if _sha256(raw) != expected_sha256:
        raise ExplicitV1BlindPreparationError(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV1BlindPreparationError(f"builder file missing: {path}")
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(PACKAGE_ROOT).as_posix(),
        "sha256": _sha256(raw),
    }


def _runtime_lineage() -> dict[str, Any]:
    packages: dict[str, dict[str, str]] = {}
    for module_name, distribution in (
        ("numpy", "numpy"),
        ("PIL", "Pillow"),
        ("rasterio", "rasterio"),
    ):
        packages[module_name] = {
            "distribution": distribution,
            "version": importlib.metadata.version(distribution),
        }
    return {
        "packages": packages,
        "platform": {
            "architecture": platform.architecture()[0],
            "descriptor": platform.platform(),
            "machine": platform.machine(),
            "release": platform.release(),
            "system": platform.system(),
        },
        "python": {
            "cache_tag": sys.implementation.cache_tag,
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
    }


def _png_chunks(raw: bytes, label: str) -> tuple[bytes, ...]:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ExplicitV1BlindPreparationError(f"{label} is not a PNG")
    chunks: list[bytes] = []
    cursor = 8
    while cursor < len(raw):
        if cursor + 12 > len(raw):
            raise ExplicitV1BlindPreparationError(f"{label} PNG is truncated")
        length = int.from_bytes(raw[cursor : cursor + 4], "big")
        chunk_type = raw[cursor + 4 : cursor + 8]
        end = cursor + 12 + length
        if end > len(raw):
            raise ExplicitV1BlindPreparationError(f"{label} PNG chunk is truncated")
        chunks.append(chunk_type)
        cursor = end
        if chunk_type == b"IEND":
            break
    if cursor != len(raw) or not chunks or chunks[-1] != b"IEND":
        raise ExplicitV1BlindPreparationError(f"{label} PNG framing changed")
    if PNG_FORBIDDEN_METADATA_CHUNKS.intersection(chunks):
        raise ExplicitV1BlindPreparationError(
            f"{label} contains textual or EXIF PNG metadata"
        )
    return tuple(chunks)


def _blind_order() -> tuple[tuple[str, str], ...]:
    ranked = sorted(
        SOURCE_QUEUE_IDS,
        key=lambda queue_id: hashlib.sha256(
            f"{ORDER_SALT}\0{queue_id}".encode("utf-8")
        ).digest(),
    )
    return tuple(
        (f"{BLIND_ID_PREFIX}{index:03d}", queue_id)
        for index, queue_id in enumerate(ranked, 1)
    )


def _lineage_commitment(
    manifest: Mapping[str, Any], order: tuple[tuple[str, str], ...]
) -> str:
    rows = []
    for blind_id, queue_id in order:
        rows.append(
            {
                "blind_id": blind_id,
                "queue_id": queue_id,
                "visual_artifacts": {
                    name: manifest["jobs"][queue_id]["artifacts"][name]
                    for name in VISUAL_FILENAMES
                },
            }
        )
    return _sha256(b"".join(_canonical_line(row) for row in rows))


def _read_source() -> tuple[dict[str, Any], tuple[tuple[str, str], ...]]:
    wrapper = disposition.validate_disposition(
        SOURCE_DISPOSITION_PATH,
        expected_generated_at="2026-07-21T14:06:45Z",
        expected_catalog_finalized_at="2026-07-21T14:05:15Z",
    )
    if _sha256((SOURCE_DISPOSITION_PATH / "manifest.json").read_bytes()) != (
        SOURCE_DISPOSITION_MANIFEST_SHA256
    ):
        raise ExplicitV1BlindPreparationError("accepted disposition manifest changed")
    if disposition.tree_sha256(SOURCE_DISPOSITION_PATH)[0] != (
        SOURCE_DISPOSITION_TREE_SHA256
    ):
        raise ExplicitV1BlindPreparationError("accepted disposition tree changed")
    if wrapper.get("status") != disposition.DISPOSITION_STATUS:
        raise ExplicitV1BlindPreparationError("accepted disposition status changed")
    raw = _exact_file(
        SOURCE_RUN_PATH / "batch-manifest.json",
        SOURCE_CHANGE_MANIFEST_SHA256,
        "source change manifest",
    )
    document = _strict_json(raw, "source change manifest")
    if not isinstance(document, dict):
        raise ExplicitV1BlindPreparationError("source change manifest must be an object")
    if disposition.tree_sha256(SOURCE_RUN_PATH) != (
        SOURCE_CHANGE_TREE_SHA256,
        SOURCE_CHANGE_FILES,
        SOURCE_CHANGE_BYTES,
    ):
        raise ExplicitV1BlindPreparationError("source change tree changed")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != set(SOURCE_QUEUE_IDS):
        raise ExplicitV1BlindPreparationError("source job inventory changed")
    if tuple(document.get("selection", {}).get("selected_queue_ids", ())) != (
        SOURCE_QUEUE_IDS
    ):
        raise ExplicitV1BlindPreparationError("source selected order changed")
    expected_artifacts = {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
        "report.json",
    }
    for queue_id, job in jobs.items():
        if (
            job.get("state") != "completed"
            or job.get("attempts") != 1
            or set(job.get("artifacts", {})) != expected_artifacts
        ):
            raise ExplicitV1BlindPreparationError(f"source job changed: {queue_id}")
        for name in VISUAL_FILENAMES:
            spec = job["artifacts"][name]
            source = SOURCE_RUN_PATH / "jobs" / queue_id / "change" / name
            raw_image = _exact_file(source, spec["sha256"], f"{queue_id}/{name}")
            if len(raw_image) != spec["bytes"]:
                raise ExplicitV1BlindPreparationError(
                    f"source visual artifact size changed: {queue_id}/{name}"
                )
            _png_chunks(raw_image, f"{queue_id}/{name}")
    return document, _blind_order()


def _readme() -> bytes:
    return (
        "# Identity-blind visual preparation for eleven explicit-v1 jobs\n\n"
        "This immutable bundle contains only before, after, comparison, and "
        "change-overlay PNG views under neutral randomized IDs. It deliberately "
        "contains no queue IDs, source paths, reports, identity, operator, type, "
        "status, lifecycle, capacity, power, energy, PUE, workload, priority, or "
        "site-count metadata.\n\n"
        "The analyst must fix image-quality flags and visible-change dispositions "
        "before lineage is unsealed. The images can support manual visible-change "
        "follow-up or rejection for imagery promotion only. They cannot establish "
        "a data-centre identity, construction truth, current status, or any other "
        "Atlas fact, and this bundle does not mutate the Atlas.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "The four PNG views per blind unit are byte-identical copies of the "
        "accepted review-only machine-change artifacts.\n"
    ).encode("utf-8")


def build_blind_preparation(generated_at: str) -> dict[str, bytes]:
    """Build deterministic metadata-free preparation bytes from accepted inputs."""

    generated_at, _ = _timestamp(generated_at, "generated_at")
    source, order = _read_source()
    source_runtime = source["processor"]["runtime"]
    current_runtime = _runtime_lineage()
    expected_runtime = {
        "packages": source_runtime["packages"],
        "platform": source_runtime["platform"],
        "python": source_runtime["python"],
    }
    if current_runtime != expected_runtime:
        raise ExplicitV1BlindPreparationError("pinned numerical runtime changed")

    images: dict[str, bytes] = {}
    units: list[dict[str, Any]] = []
    for blind_id, queue_id in order:
        artifacts: dict[str, Any] = {}
        for name in VISUAL_FILENAMES:
            spec = source["jobs"][queue_id]["artifacts"][name]
            raw = (
                SOURCE_RUN_PATH / "jobs" / queue_id / "change" / name
            ).read_bytes()
            relative = f"images/{blind_id}/{name}"
            images[relative] = raw
            artifacts[name] = {
                "bytes": len(raw),
                "path": relative,
                "sha256": _sha256(raw),
            }
            if artifacts[name] != {"path": relative, **spec}:
                raise ExplicitV1BlindPreparationError(
                    f"visual binding changed while staging: {blind_id}/{name}"
                )
        units.append(
            {
                "blind_id": blind_id,
                "inspection_order": int(blind_id[-3:]),
                "schema_version": 1,
                "views": artifacts,
            }
        )
    units_raw = b"".join(_canonical_line(unit) for unit in units)
    definition = {
        "blinding": {
            "blind_id_prefix": BLIND_ID_PREFIX,
            "lineage_commitment_sha256": _lineage_commitment(source, order),
            "order_algorithm": ORDER_ALGORITHM,
            "order_salt_sha256": _sha256(ORDER_SALT.encode("utf-8")),
            "per_unit_source_lineage_withheld": True,
            "queue_ids_exposed": False,
            "report_metadata_exposed": False,
        },
        "builder": {
            "files": {
                "module": _file_record(BUILDER_PATH),
                "root_shim": _file_record(ROOT_SHIM_PATH),
                "cli": _file_record(CLI_PATH),
            }
        },
        "format": "datacenter-atlas-explicit-v1-blind-preparation-definition",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "preparation_id": PREPARATION_ID,
        "runtime": expected_runtime,
        "schema_version": 1,
        "source": {
            "accepted_disposition": {
                "manifest_sha256": SOURCE_DISPOSITION_MANIFEST_SHA256,
                "path": SOURCE_DISPOSITION_PATH.relative_to(PACKAGE_ROOT).as_posix(),
                "tree_sha256": SOURCE_DISPOSITION_TREE_SHA256,
            },
            "change_run": {
                "files": SOURCE_CHANGE_FILES,
                "manifest_sha256": SOURCE_CHANGE_MANIFEST_SHA256,
                "path": SOURCE_RUN_PATH.relative_to(PACKAGE_ROOT).as_posix(),
                "tree_sha256": SOURCE_CHANGE_TREE_SHA256,
                "bytes": SOURCE_CHANGE_BYTES,
            },
        },
    }
    output: dict[str, bytes] = {
        ATTRIBUTION_FILENAME: _attribution(),
        DEFINITION_FILENAME: _canonical_json(definition),
        README_FILENAME: _readme(),
        UNITS_FILENAME: units_raw,
        **images,
    }
    manifest = {
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(output.items())
        },
        "blinding": definition["blinding"],
        "format": "datacenter-atlas-explicit-v1-blind-preparation",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "preparation_id": PREPARATION_ID,
        "schema_version": 1,
        "summary": {
            "blind_review_units": SOURCE_JOB_COUNT,
            "copied_visual_artifacts": SOURCE_JOB_COUNT * len(VISUAL_FILENAMES),
            "lineage_rows_exposed": 0,
            "queue_ids_exposed": 0,
            "report_artifacts_copied": 0,
        },
    }
    manifest_raw = _canonical_json(manifest)
    output[MANIFEST_FILENAME] = manifest_raw
    output[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    serialized = b"".join(output.values())
    for forbidden in (b"satq-", b'"queue_id"', b'"operator"', b'"current_status"'):
        if forbidden in serialized:
            raise ExplicitV1BlindPreparationError(
                f"identity-blind preparation leaked forbidden bytes: {forbidden!r}"
            )
    return output


def _write_file(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _freeze_tree(root: Path) -> None:
    for child in sorted(root.rglob("*"), reverse=True):
        child.chmod(0o555 if child.is_dir() else 0o444)
    root.chmod(0o555)


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:
            raise ExplicitV1BlindPreparationError("atomic no-replace unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:
            raise ExplicitV1BlindPreparationError("atomic no-replace unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 1)
    else:
        raise ExplicitV1BlindPreparationError("atomic no-replace unsupported")
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ExplicitV1BlindPreparationError(
                f"refusing existing output: {destination}"
            )
        raise OSError(code, os.strerror(code), destination)


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ExplicitV1BlindPreparationError("preparation must be a regular directory")
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    entries = [
        root,
        *sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()),
    ]
    for entry in entries:
        relative = "." if entry == root else entry.relative_to(root).as_posix()
        if entry.is_symlink():
            raise ExplicitV1BlindPreparationError(f"symlink in preparation: {relative}")
        mode = stat.S_IMODE(entry.stat().st_mode)
        if entry.is_dir():
            if mode != 0o555:
                raise ExplicitV1BlindPreparationError(
                    f"directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif entry.is_file():
            if mode != 0o444:
                raise ExplicitV1BlindPreparationError(
                    f"file mode changed: {relative} is {mode:04o}"
                )
            raw = entry.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n".encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise ExplicitV1BlindPreparationError(
                f"unsupported preparation entry: {relative}"
            )
    return {
        "directories": directories,
        "file_bytes": file_bytes,
        "files": files,
        "inventory_sha256": digest.hexdigest(),
    }


def publish_blind_preparation(
    generated_at: str,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    """Stage, time-gate, and atomically publish the frozen preparation."""

    canonical_time, target = _timestamp(generated_at, "generated_at")
    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV1BlindPreparationError("preparation output path changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ExplicitV1BlindPreparationError(f"active output lock: {lock}") from error
    stage: Path | None = None
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists() or destination.is_symlink():
            raise ExplicitV1BlindPreparationError(f"refusing existing output: {destination}")
        stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
        files = build_blind_preparation(canonical_time)
        for relative, raw in sorted(files.items()):
            _write_file(stage / relative, raw)
        newest = max(
            max(entry.stat().st_mtime, getattr(entry.stat(), "st_birthtime", 0.0))
            for entry in [stage, *stage.rglob("*")]
        )
        if newest > target.timestamp() + 1e-6:
            raise ExplicitV1BlindPreparationError(
                "staged preparation bytes postdate generated_at"
            )
        _freeze_tree(stage)
        while datetime.now(UTC) < target:
            remaining = (target - datetime.now(UTC)).total_seconds()
            time.sleep(min(max(remaining, 0.0), 0.25))
        _promote_noreplace(stage, destination)
        stage = None
        if destination.stat().st_ctime + 1e-6 < target.timestamp():
            raise ExplicitV1BlindPreparationError(
                "preparation root ctime precedes generated_at"
            )
        return validate_blind_preparation(destination)
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


def validate_blind_preparation(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    """Rebuild and verify the frozen blind preparation byte-for-byte offline."""

    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV1BlindPreparationError("preparation output path changed")
    definition_raw = (destination / DEFINITION_FILENAME).read_bytes()
    definition = _strict_json(definition_raw, "preparation definition")
    generated_at, target = _timestamp(definition.get("generated_at"), "generated_at")
    if destination.stat().st_ctime + 1e-6 < target.timestamp():
        raise ExplicitV1BlindPreparationError(
            "preparation root ctime precedes generated_at"
        )
    inventory = _tree_inventory(destination)
    actual = {
        entry.relative_to(destination).as_posix(): entry.read_bytes()
        for entry in destination.rglob("*")
        if entry.is_file()
    }
    expected = build_blind_preparation(generated_at)
    if actual != expected:
        raise ExplicitV1BlindPreparationError(
            "preparation differs from offline reconstruction"
        )
    manifest_raw = actual[MANIFEST_FILENAME]
    if actual[MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ExplicitV1BlindPreparationError("preparation sidecar changed")
    manifest = _strict_json(manifest_raw, "preparation manifest")
    return {**manifest, "tree_inventory": inventory}


def blind_image_paths(output_path: Path = OUTPUT_PATH) -> dict[str, tuple[Path, ...]]:
    """Return only neutral IDs and four frozen image paths for a fresh reviewer."""

    validate_blind_preparation(output_path)
    rows = [
        _strict_json(line, "review unit")
        for line in (output_path / UNITS_FILENAME).read_bytes().splitlines()
    ]
    return {
        row["blind_id"]: tuple(output_path / row["views"][name]["path"] for name in VISUAL_FILENAMES)
        for row in rows
    }
