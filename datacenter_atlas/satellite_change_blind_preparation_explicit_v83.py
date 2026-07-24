"""Prepare the exact 68 v83 proposals for identity-blind visual review.

Only four metadata-free PNG views are copied for each accepted proposal.  The
reviewer-facing release uses deterministic neutral IDs and withholds queue IDs,
entity identity, source paths per unit, reports, coordinates, status, priority,
and every Atlas fact.  It is a review carrier, never an inference or promotion.
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
import zlib


class ExplicitV83BlindPreparationError(ValueError):
    """Raised when accepted inputs, blinding, or publication drift."""


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PREPARATION_ID = (
    "2026-07-21-open-seed-v83-active-unreviewed-single-68-blind-v1"
)
OUTPUT_PATH = PACKAGE_ROOT / "satellite_change_preparation" / PREPARATION_ID

SOURCE_RUN_PATH = (
    PACKAGE_ROOT
    / "satellite_change_runs"
    / "2026-07-21-open-seed-v83-active-unreviewed-remaining-001"
)
SOURCE_RUN_MANIFEST_BYTES = 386_657
SOURCE_RUN_MANIFEST_SHA256 = (
    "399d66cec56ac57aabd097b8d9c16e302a94f47b3651c2aca6afa1dfcb29bb8a"
)
SOURCE_RUN_TREE = {
    "directories": 138,
    "file_bytes": 108_590_556,
    "files": 409,
    "inventory_sha256": (
        "83096e75f913d79b9a2db63110d1dc53d3e5db58c27e8590f52009c4caa091af"
    ),
}

SOURCE_PREPARATION_PATH = (
    PACKAGE_ROOT
    / "satellite_change_preparation"
    / "2026-07-21-open-seed-v83-active-v2"
)
SOURCE_PREPARATION_DEFINITION_PATH = (
    PACKAGE_ROOT
    / "sources"
    / "satellite-change-preparation-2026-07-21-open-seed-v83-active-v2.json"
)
SOURCE_PREPARATION_DEFINITION_BYTES = 5_710
SOURCE_PREPARATION_DEFINITION_SHA256 = (
    "3074d54f9082c539d70db7313e6534a13794dc2d52ead99a131f1215eed21f53"
)
SOURCE_PREPARATION_MANIFEST_BYTES = 8_214
SOURCE_PREPARATION_MANIFEST_SHA256 = (
    "9d7df8ad8393556b172b5fda49174750e0d9ce17d6c560c692003af5c0e33430"
)
SOURCE_PREPARATION_TREE = {
    "directories": 1,
    "file_bytes": 1_551_547,
    "files": 11,
    "inventory_sha256": (
        "929bd1b79beb2226961ebf652610159a56058c4aa135ee2203cb9eef4e15a227"
    ),
}

SOURCE_JOB_COUNT = 68
SOURCE_SELECTION_SHA256 = (
    "1d84eb34d3783f810eab1c59d41719d437de7b11fa41c22c40c3b488dcbee7f1"
)
SOURCE_RUN_SUMMARY = {
    "catalog_completed_jobs": 101,
    "catalog_completed_jobs_excluded": 0,
    "catalog_completed_jobs_not_in_inclusion": 33,
    "exclusion_ids_without_completed_catalog": 0,
    "jobs_completed": 68,
    "jobs_exhausted": 0,
    "jobs_failed": 0,
    "jobs_pending": 0,
    "jobs_running": 0,
    "jobs_selected": 68,
}
SOURCE_ARTIFACT_FILENAMES = frozenset(
    {
        "after.png",
        "before.png",
        "change-overlay.png",
        "change-proposals.geojson",
        "comparison.png",
        "report.json",
    }
)
VISUAL_FILENAMES = (
    "before.png",
    "after.png",
    "comparison.png",
    "change-overlay.png",
)
PNG_ALLOWED_CHUNKS = frozenset({b"IHDR", b"IDAT", b"IEND"})

ORDER_SALT = "dc-atlas-v83-unreviewed-single-68-blind-order-2026-07-21-v1"
ORDER_ALGORITHM = "ascending_sha256_utf8_salt_nul_queue_id"
BLIND_ID_PREFIX = "V83-X"

DEFINITION_FILENAME = "definition.json"
UNITS_FILENAME = "review-units.jsonl"
README_FILENAME = "README.md"
ATTRIBUTION_FILENAME = "ATTRIBUTION.txt"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = (
    PACKAGE_ROOT / "satellite_change_blind_preparation_explicit_v83.py"
)
CLI_PATH = (
    PACKAGE_ROOT
    / "scripts"
    / "build_satellite_change_blind_preparation_explicit_v83.py"
)

GUARDRAILS = {
    "analyst_identity_metadata_exposed": False,
    "atlas_mutation": False,
    "automated_promotion_allowed": False,
    "capacity_claim_created": False,
    "construction_status_claim_created": False,
    "coordinate_metadata_exposed": False,
    "current_status_claim_created": False,
    "data_centre_identity_claim_created": False,
    "data_centre_type_claim_created": False,
    "energy_claim_created": False,
    "imagery_construction_truth_claim_created": False,
    "it_capacity_claim_created": False,
    "lifecycle_status_claim_created": False,
    "operator_claim_created": False,
    "power_claim_created": False,
    "priority_metadata_exposed": False,
    "pue_claim_created": False,
    "site_count_claim_created": False,
    "site_metadata_exposed": False,
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
        raise ExplicitV83BlindPreparationError(f"{label} is not UTF-8") from error

    def reject_constant(value: str) -> None:
        raise ExplicitV83BlindPreparationError(
            f"{label} contains non-finite number {value}"
        )

    try:
        return json.loads(text, parse_constant=reject_constant)
    except json.JSONDecodeError as error:
        raise ExplicitV83BlindPreparationError(
            f"{label} is not valid JSON"
        ) from error


def _timestamp(value: str, label: str) -> tuple[str, datetime]:
    if not isinstance(value, str) or not value:
        raise ExplicitV83BlindPreparationError(
            f"{label} must be an RFC 3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExplicitV83BlindPreparationError(
            f"{label} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ExplicitV83BlindPreparationError(f"{label} must be UTC")
    canonical = parsed.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    return canonical, parsed.astimezone(UTC)


def suggested_generated_at() -> str:
    """Return a publication time far enough ahead to stage all release bytes."""

    target = datetime.now(UTC) + timedelta(seconds=120)
    return target.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _exact_file(
    path: Path,
    expected_bytes: int,
    expected_sha256: str,
    label: str,
) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV83BlindPreparationError(
            f"{label} must be a regular non-symlink file"
        )
    raw = path.read_bytes()
    if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
        raise ExplicitV83BlindPreparationError(f"{label} changed")
    return raw


def _file_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV83BlindPreparationError(f"builder file missing: {path}")
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
        raise ExplicitV83BlindPreparationError(f"{label} is not a PNG")
    chunks: list[bytes] = []
    cursor = 8
    while cursor < len(raw):
        if cursor + 12 > len(raw):
            raise ExplicitV83BlindPreparationError(f"{label} PNG is truncated")
        length = int.from_bytes(raw[cursor : cursor + 4], "big")
        chunk_type = raw[cursor + 4 : cursor + 8]
        payload_end = cursor + 8 + length
        end = payload_end + 4
        if end > len(raw):
            raise ExplicitV83BlindPreparationError(
                f"{label} PNG chunk is truncated"
            )
        expected_crc = int.from_bytes(raw[payload_end:end], "big")
        actual_crc = zlib.crc32(raw[cursor + 4 : payload_end]) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise ExplicitV83BlindPreparationError(
                f"{label} PNG chunk checksum changed"
            )
        if chunk_type not in PNG_ALLOWED_CHUNKS:
            raise ExplicitV83BlindPreparationError(
                f"{label} contains non-pixel PNG metadata chunk {chunk_type!r}"
            )
        chunks.append(chunk_type)
        cursor = end
        if chunk_type == b"IEND":
            break
    if (
        cursor != len(raw)
        or not chunks
        or chunks[0] != b"IHDR"
        or chunks[-1] != b"IEND"
        or b"IDAT" not in chunks
    ):
        raise ExplicitV83BlindPreparationError(f"{label} PNG framing changed")
    return tuple(chunks)


def _tree_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ExplicitV83BlindPreparationError("tree must be a regular directory")
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
            raise ExplicitV83BlindPreparationError(f"symlink in tree: {relative}")
        mode = stat.S_IMODE(entry.stat().st_mode)
        if entry.is_dir():
            if mode != 0o555:
                raise ExplicitV83BlindPreparationError(
                    f"directory mode changed: {relative} is {mode:04o}"
                )
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
            directories += 1
        elif entry.is_file():
            if mode != 0o444:
                raise ExplicitV83BlindPreparationError(
                    f"file mode changed: {relative} is {mode:04o}"
                )
            raw = entry.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n".encode()
            )
            files += 1
            file_bytes += len(raw)
        else:
            raise ExplicitV83BlindPreparationError(
                f"unsupported tree entry: {relative}"
            )
    return {
        "directories": directories,
        "file_bytes": file_bytes,
        "files": files,
        "inventory_sha256": digest.hexdigest(),
    }


def _jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ExplicitV83BlindPreparationError(f"{label} is missing")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(path.read_bytes().splitlines(), 1):
        value = _strict_json(raw, f"{label} line {index}")
        if not isinstance(value, dict):
            raise ExplicitV83BlindPreparationError(
                f"{label} line {index} must be an object"
            )
        rows.append(value)
    return rows


def _blind_order(queue_ids: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    ranked = sorted(
        queue_ids,
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
    if _tree_inventory(SOURCE_PREPARATION_PATH) != SOURCE_PREPARATION_TREE:
        raise ExplicitV83BlindPreparationError(
            "accepted v83 metadata preparation tree changed"
        )
    _exact_file(
        SOURCE_PREPARATION_DEFINITION_PATH,
        SOURCE_PREPARATION_DEFINITION_BYTES,
        SOURCE_PREPARATION_DEFINITION_SHA256,
        "accepted v83 metadata preparation definition",
    )
    _exact_file(
        SOURCE_PREPARATION_PATH / MANIFEST_FILENAME,
        SOURCE_PREPARATION_MANIFEST_BYTES,
        SOURCE_PREPARATION_MANIFEST_SHA256,
        "accepted v83 metadata preparation manifest",
    )
    if _tree_inventory(SOURCE_RUN_PATH) != SOURCE_RUN_TREE:
        raise ExplicitV83BlindPreparationError("accepted change-run tree changed")
    manifest_raw = _exact_file(
        SOURCE_RUN_PATH / "batch-manifest.json",
        SOURCE_RUN_MANIFEST_BYTES,
        SOURCE_RUN_MANIFEST_SHA256,
        "accepted change-run manifest",
    )
    manifest = _strict_json(manifest_raw, "accepted change-run manifest")
    if not isinstance(manifest, dict):
        raise ExplicitV83BlindPreparationError(
            "accepted change-run manifest must be an object"
        )
    selection = manifest.get("selection")
    if not isinstance(selection, dict):
        raise ExplicitV83BlindPreparationError("source selection is missing")
    selected = tuple(selection.get("selected_queue_ids", ()))
    included = tuple(selection.get("include_queue_ids", ()))
    if (
        manifest.get("state") != "completed"
        or manifest.get("summary") != SOURCE_RUN_SUMMARY
        or selection.get("mode") != "explicit_inclusion"
        or selection.get("exclude_queue_ids") != []
        or selected != included
        or len(selected) != SOURCE_JOB_COUNT
        or len(set(selected)) != SOURCE_JOB_COUNT
        or set(manifest.get("jobs", {})) != set(selected)
    ):
        raise ExplicitV83BlindPreparationError("source exact selection drift")
    selection_sha256 = _sha256(_canonical_json(sorted(selected)))
    if selection_sha256 != SOURCE_SELECTION_SHA256:
        raise ExplicitV83BlindPreparationError("source selection identity changed")

    ready_rows = _jsonl(
        SOURCE_PREPARATION_PATH / "single-tile-ready.jsonl",
        "accepted v83 single-tile-ready rows",
    )
    exact_unreviewed_ready = {
        row.get("queue_id")
        for row in ready_rows
        if row.get("analyst_review_coverage", {}).get("status") == "unreviewed"
    }
    if (
        len(ready_rows) != 88
        or len(exact_unreviewed_ready) != SOURCE_JOB_COUNT
        or exact_unreviewed_ready != set(selected)
    ):
        raise ExplicitV83BlindPreparationError(
            "source run is not exactly the 68 unreviewed single-tile-ready rows"
        )

    for queue_id in selected:
        job = manifest["jobs"][queue_id]
        expected_output = Path("jobs") / queue_id / "change"
        if (
            job.get("state") != "completed"
            or job.get("attempts") != 1
            or set(job.get("artifacts", {})) != SOURCE_ARTIFACT_FILENAMES
            or Path(job.get("change_job", {}).get("output_directory", ""))
            != expected_output
        ):
            raise ExplicitV83BlindPreparationError(
                f"source completed-job contract changed: {queue_id}"
            )
        classification = job.get("report", {}).get("classification", {})
        claims = {
            key: value
            for key, value in classification.items()
            if key.endswith("_claim")
        }
        if not classification.get("review_required") or not claims or any(
            value is not False for value in claims.values()
        ):
            raise ExplicitV83BlindPreparationError(
                f"source proposal claim boundary changed: {queue_id}"
            )
        for name in VISUAL_FILENAMES:
            spec = job["artifacts"][name]
            source = SOURCE_RUN_PATH / expected_output / name
            raw = _exact_file(
                source,
                spec["bytes"],
                spec["sha256"],
                f"source visual {queue_id}/{name}",
            )
            _png_chunks(raw, f"source visual {queue_id}/{name}")

    order = _blind_order(selected)
    if tuple(queue_id for _blind_id, queue_id in order) == selected:
        raise ExplicitV83BlindPreparationError("blind order did not permute source")
    return manifest, order


def _readme() -> bytes:
    return (
        "# Identity-blind visual preparation for 68 v83 proposals\n\n"
        "This immutable reviewer bundle contains only before, after, comparison, "
        "and change-overlay PNG views under neutral randomized IDs. It contains "
        "no queue IDs, entity or site identity, source path per unit, report, "
        "coordinates, operator, type, status, lifecycle, priority, capacity, "
        "power, energy, PUE, workload, or site-count metadata.\n\n"
        "The analyst must fix image-quality flags and visible-change dispositions "
        "before lineage is unsealed. A visual decision can only accept or reject "
        "an imagery-change proposal for later evidence handling. It cannot "
        "establish construction, identity, current status, or any Atlas fact, and "
        "this preparation does not mutate the Atlas.\n"
    ).encode("utf-8")


def _attribution() -> bytes:
    return (
        "Contains modified Copernicus Sentinel data 2024 and 2026.\n"
        "Catalog: Element 84 Earth Search v1.\n"
        "Dataset: Copernicus Sentinel-2 Level-2A.\n"
        "The four PNG views per neutral unit are byte-identical copies of the "
        "accepted review-only machine-change artifacts.\n"
    ).encode("utf-8")


def _assert_no_identity_leak(
    output: Mapping[str, bytes], source: Mapping[str, Any]
) -> None:
    forbidden_literals = (
        b"satq-",
        b'"queue_id"',
        b'"entity"',
        b'"entity_id"',
        b'"entity_name"',
        b'"aoi_bbox_wgs84"',
        b'"priority"',
        b'"operator"',
        b'"current_status"',
        b'"report.json"',
        b'"change-proposals.geojson"',
    )
    dynamic_literals: set[bytes] = set()
    for job in source["jobs"].values():
        entity = job["entity"]
        for value in (entity["id"], entity["name"]):
            encoded = value.encode("utf-8")
            if len(encoded) >= 8:
                dynamic_literals.add(encoded)
    for relative, raw in output.items():
        for forbidden in (*forbidden_literals, *dynamic_literals):
            if forbidden in raw:
                raise ExplicitV83BlindPreparationError(
                    f"identity-blind preparation leaked forbidden bytes in "
                    f"{relative}: {forbidden!r}"
                )


def build_blind_preparation(generated_at: str) -> dict[str, bytes]:
    """Build deterministic identity-blind bytes from the two pinned inputs."""

    generated_at, _ = _timestamp(generated_at, "generated_at")
    source, order = _read_source()
    source_runtime = source["processor"]["runtime"]
    expected_runtime = {
        "packages": source_runtime["packages"],
        "platform": source_runtime["platform"],
        "python": source_runtime["python"],
    }
    if _runtime_lineage() != expected_runtime:
        raise ExplicitV83BlindPreparationError("pinned numerical runtime changed")

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
                raise ExplicitV83BlindPreparationError(
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
    definition = {
        "blinding": {
            "blind_id_prefix": BLIND_ID_PREFIX,
            "coordinate_metadata_exposed": False,
            "entity_identity_exposed": False,
            "lineage_commitment_sha256": _lineage_commitment(source, order),
            "order_algorithm": ORDER_ALGORITHM,
            "order_salt_sha256": _sha256(ORDER_SALT.encode("utf-8")),
            "per_unit_source_lineage_withheld": True,
            "queue_ids_exposed": False,
            "report_metadata_exposed": False,
            "site_metadata_exposed": False,
            "status_metadata_exposed": False,
        },
        "builder": {
            "files": {
                "cli": _file_record(CLI_PATH),
                "module": _file_record(BUILDER_PATH),
                "root_shim": _file_record(ROOT_SHIM_PATH),
            }
        },
        "format": "datacenter-atlas-explicit-v83-blind-preparation-definition",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "membership_proof": {
            "accepted_change_run_selected_jobs": SOURCE_JOB_COUNT,
            "accepted_preparation_unreviewed_single_tile_ready_jobs": (
                SOURCE_JOB_COUNT
            ),
            "exact_set_equality": True,
            "selected_queue_ids_sha256": SOURCE_SELECTION_SHA256,
        },
        "preparation_id": PREPARATION_ID,
        "runtime": expected_runtime,
        "schema_version": 1,
        "source": {
            "accepted_change_run": {
                "bytes": SOURCE_RUN_TREE["file_bytes"],
                "files": SOURCE_RUN_TREE["files"],
                "manifest_sha256": SOURCE_RUN_MANIFEST_SHA256,
                "path": SOURCE_RUN_PATH.relative_to(PACKAGE_ROOT).as_posix(),
                "tree_sha256": SOURCE_RUN_TREE["inventory_sha256"],
            },
            "accepted_metadata_preparation": {
                "definition_sha256": SOURCE_PREPARATION_DEFINITION_SHA256,
                "manifest_sha256": SOURCE_PREPARATION_MANIFEST_SHA256,
                "path": SOURCE_PREPARATION_PATH.relative_to(PACKAGE_ROOT).as_posix(),
                "tree_sha256": SOURCE_PREPARATION_TREE["inventory_sha256"],
            },
        },
    }
    output: dict[str, bytes] = {
        ATTRIBUTION_FILENAME: _attribution(),
        DEFINITION_FILENAME: _canonical_json(definition),
        README_FILENAME: _readme(),
        UNITS_FILENAME: b"".join(_canonical_line(unit) for unit in units),
        **images,
    }
    manifest = {
        "artifacts": {
            name: {"bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(output.items())
        },
        "blinding": definition["blinding"],
        "format": "datacenter-atlas-explicit-v83-blind-preparation",
        "generated_at": generated_at,
        "guardrails": GUARDRAILS,
        "membership_proof": definition["membership_proof"],
        "preparation_id": PREPARATION_ID,
        "schema_version": 1,
        "summary": {
            "blind_review_units": SOURCE_JOB_COUNT,
            "copied_visual_artifacts": SOURCE_JOB_COUNT * len(VISUAL_FILENAMES),
            "coordinate_metadata_fields_exposed": 0,
            "geojson_artifacts_copied": 0,
            "lineage_rows_exposed": 0,
            "queue_ids_exposed": 0,
            "report_artifacts_copied": 0,
            "site_identity_fields_exposed": 0,
            "status_metadata_fields_exposed": 0,
        },
    }
    manifest_raw = _canonical_json(manifest)
    output[MANIFEST_FILENAME] = manifest_raw
    output[MANIFEST_HASH_FILENAME] = (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    _assert_no_identity_leak(output, source)
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


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _promote_noreplace(stage: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(stage)
    target = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:
            raise ExplicitV83BlindPreparationError("atomic no-replace unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source, target, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:
            raise ExplicitV83BlindPreparationError("atomic no-replace unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source, -100, target, 1)
    else:  # pragma: no cover - publication platform guard
        raise ExplicitV83BlindPreparationError("atomic no-replace unsupported")
    if result == 0:
        _fsync_directory(destination.parent)
        return
    code = ctypes.get_errno()
    if code in {errno.EEXIST, errno.ENOTEMPTY}:
        raise ExplicitV83BlindPreparationError(
            f"refusing existing output: {destination}"
        )
    raise OSError(code, os.strerror(code), destination)


def _thaw_and_remove(path: Path) -> None:
    if not path.exists() or path.is_symlink():
        return
    for child in sorted(path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        if not child.is_symlink():
            child.chmod(0o700 if child.is_dir() else 0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


def publish_blind_preparation(
    generated_at: str,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    """Stage, time-gate, and atomically publish the frozen preparation."""

    canonical_time, target = _timestamp(generated_at, "generated_at")
    if target <= datetime.now(UTC):
        raise ExplicitV83BlindPreparationError(
            "generated_at must be in the future at build start"
        )
    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV83BlindPreparationError("preparation output path changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / f".{destination.name}.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ExplicitV83BlindPreparationError(f"active output lock: {lock}") from error
    stage: Path | None = None
    promoted = False
    identity: tuple[int, int] | None = None
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists() or destination.is_symlink():
            raise ExplicitV83BlindPreparationError(
                f"refusing existing output: {destination}"
            )
        first = build_blind_preparation(canonical_time)
        second = build_blind_preparation(canonical_time)
        if first != second:
            raise ExplicitV83BlindPreparationError("two offline replays differ")
        del second
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        for relative, raw in sorted(first.items()):
            _write_file(stage / relative, raw)
        newest = max(
            max(entry.stat().st_mtime, getattr(entry.stat(), "st_birthtime", 0.0))
            for entry in [stage, *stage.rglob("*")]
        )
        if newest > target.timestamp() + 1e-6:
            raise ExplicitV83BlindPreparationError(
                "staged preparation bytes postdate generated_at"
            )
        _freeze_tree(stage)
        frozen_inventory = _tree_inventory(stage)
        while datetime.now(UTC) < target:
            remaining = (target - datetime.now(UTC)).total_seconds()
            time.sleep(min(max(remaining, 0.001), 0.25))
        if _tree_inventory(stage) != frozen_inventory:
            raise ExplicitV83BlindPreparationError(
                "private stage changed while waiting"
            )
        if destination.exists() or destination.is_symlink():
            raise ExplicitV83BlindPreparationError(
                f"preparation output appeared during publication: {destination}"
            )
        status = stage.stat()
        identity = (status.st_dev, status.st_ino)
        stage.chmod(0o755)
        _promote_noreplace(stage, destination)
        stage = None
        promoted = True
        destination.chmod(0o555)
        if destination.stat().st_ctime + 1e-6 < target.timestamp():
            raise ExplicitV83BlindPreparationError(
                "preparation root ctime precedes generated_at"
            )
        return validate_blind_preparation(destination)
    except BaseException:
        if promoted and destination.exists() and not destination.is_symlink() and identity:
            status = destination.stat()
            if (status.st_dev, status.st_ino) == identity:
                rollback = destination.parent / (
                    f".{destination.name}.rollback-{os.getpid()}"
                )
                if not rollback.exists() and not rollback.is_symlink():
                    destination.chmod(0o755)
                    _promote_noreplace(destination, rollback)
                    _thaw_and_remove(rollback)
        if stage is not None:
            _thaw_and_remove(stage)
        raise
    finally:
        os.close(descriptor)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def validate_blind_preparation(output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    """Rebuild and verify the frozen blind preparation byte-for-byte offline."""

    destination = output_path.resolve()
    if destination != OUTPUT_PATH.resolve():
        raise ExplicitV83BlindPreparationError("preparation output path changed")
    definition_raw = _exact_file(
        destination / DEFINITION_FILENAME,
        (destination / DEFINITION_FILENAME).stat().st_size,
        _sha256((destination / DEFINITION_FILENAME).read_bytes()),
        "preparation definition",
    )
    definition = _strict_json(definition_raw, "preparation definition")
    generated_at, target = _timestamp(definition.get("generated_at"), "generated_at")
    if destination.stat().st_ctime + 1e-6 < target.timestamp():
        raise ExplicitV83BlindPreparationError(
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
        raise ExplicitV83BlindPreparationError(
            "preparation differs from offline reconstruction"
        )
    manifest_raw = actual[MANIFEST_FILENAME]
    if actual[MANIFEST_HASH_FILENAME] != (
        f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n".encode("ascii")
    ):
        raise ExplicitV83BlindPreparationError("preparation sidecar changed")
    manifest = _strict_json(manifest_raw, "preparation manifest")
    return {**manifest, "tree_inventory": inventory}


def blind_image_paths(output_path: Path = OUTPUT_PATH) -> dict[str, tuple[Path, ...]]:
    """Return only neutral IDs and four frozen paths for fresh reviewers."""

    validate_blind_preparation(output_path)
    rows = [
        _strict_json(line, "review unit")
        for line in (output_path / UNITS_FILENAME).read_bytes().splitlines()
    ]
    return {
        row["blind_id"]: tuple(
            output_path / row["views"][name]["path"]
            for name in VISUAL_FILENAMES
        )
        for row in rows
    }


__all__ = [
    "ATTRIBUTION_FILENAME",
    "BLIND_ID_PREFIX",
    "DEFINITION_FILENAME",
    "ExplicitV83BlindPreparationError",
    "GUARDRAILS",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OUTPUT_PATH",
    "PREPARATION_ID",
    "README_FILENAME",
    "SOURCE_JOB_COUNT",
    "SOURCE_SELECTION_SHA256",
    "UNITS_FILENAME",
    "VISUAL_FILENAMES",
    "blind_image_paths",
    "build_blind_preparation",
    "publish_blind_preparation",
    "suggested_generated_at",
    "validate_blind_preparation",
]
