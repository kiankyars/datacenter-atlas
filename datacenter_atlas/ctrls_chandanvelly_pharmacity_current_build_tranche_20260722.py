"""Governed publisher for the reviewed CtrlS Hyderabad campus-build tranche.

The module never fetches the network. It requires the byte-exact reviewed
prepublication stages and the frozen private capture bundle. It copies the two
reviewed source payloads byte-for-byte into new private inodes, renders a
redacted accepted artifact, and refuses publication unless
``publication_authorized=True``.

``preflight`` is the safe default: it renders exact final source and artifact
bytes in unique sibling stages, imports each source twice, freezes and validates
the stages, reports their pins, and identity-safely discards them. Complete
already-accepted final paths are compatible with preflight; partial finals fail.
The accepted records retain zero coordinate, geometry, facility
type, operating-model, workload, capacity, energy-consumption, or efficiency
rows. CtrlS's displayed MW and MVA values remain metadata only. The ten NTT,
AdaniConneX, and weaker CtrlS signals remain rejected review-only exclusions.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "ctrls-chandanvelly-pharmacity-current-build-tranche-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".ctrls-chandanvelly-pharmacity-publication.lock"

CHANDANVELLY_SOURCE_FILENAME = (
    "curated-official-2026-07-22-ctrls-chandanvelly-current-build.json"
)
PHARMACITY_SOURCE_FILENAME = (
    "curated-official-2026-07-22-ctrls-pharmacity-current-build.json"
)
SOURCE_FILENAMES = (
    CHANDANVELLY_SOURCE_FILENAME,
    PHARMACITY_SOURCE_FILENAME,
)

REVIEWED_CANDIDATE_ID = "ctrls-ntt-india-adaniconnex-prepublication-2026-07-22-v1"
REVIEWED_RECORDED_AT = "2026-07-22T04:58:20Z"
REVIEWED_SOURCE_STAGE = SOURCES_ROOT / ".ctrls-ntt-adani-sources.1gdjyfja"
REVIEWED_ARTIFACT_STAGE = (
    ARTIFACT_ROOT / ".ctrls-ntt-india-adaniconnex-prepublication-2026-07-22-v1.wbm2coy5"
)
RAW_CAPTURE = Path("/Users/kian/.Trash/dc-india-build-gap.0X6WIC")


def _raw_capture() -> Path:
    return resolve_external_capture(RAW_CAPTURE)

REVIEWED_SOURCE_TREE_SHA256 = (
    "152b7c5f1941043cc048f04a441b50c6eb4356bd31d28f5fa9fef1dccf89343c"
)
REVIEWED_ARTIFACT_TREE_SHA256 = (
    "da8f9bff9a1f7becaf38b554fb52d587703cec4e6b9f1664c6560666c96694eb"
)
RAW_CAPTURE_TREE_SHA256 = (
    "702b3c5257c81b60d2d5b16df0cf9c41df826012018bbe72d5f79942255bbecc"
)

REVIEWED_SOURCE_PINS: Mapping[str, tuple[int, str]] = {
    CHANDANVELLY_SOURCE_FILENAME: (
        7_825,
        "af57d566fde98ad81d52b89df6709bece2d6fa46a0f0e5302ae9df5e0ad40c37",
    ),
    PHARMACITY_SOURCE_FILENAME: (
        4_932,
        "fc9175408fff782eaedce12d5da04b5125caa103dfe194f6032b26d1ff6b737b",
    ),
}

REVIEWED_ARTIFACT_PINS: Mapping[str, tuple[int, str]] = {
    "README.md": (
        1_700,
        "5bea20457bea379eb162c1088ee229574b6e14b78d831eec810533525ce17520",
    ),
    "candidate-assessment.json": (
        7_026,
        "52421861d73271e52401474ac86cc8d7657d7df74f152a26f74ec08a5771f63e",
    ),
    "manifest.json": (
        1_599,
        "0830dc2f1a400432fc502d7fa94387940d322c786e71273ed85fda7f1214c001",
    ),
    "manifest.sha256": (
        80,
        "2239a4ae231b2cdb49ae696fe301ae81cbf5b0ad36dfc8a94ed2e3897fbbdcaf",
    ),
    "retrieval-inventory.json": (
        20_576,
        "77a03ef84ccba6d6501c461dd9434e47aec4a6264512fc12d0f4e310246c247f",
    ),
    "rights-and-disposition.json": (
        1_111,
        "2f77607b4cae417a7072d1ef96a82e87998f5f8ea224a8cebf4e10b62f374ccf",
    ),
    "source-snapshot.json": (
        4_312,
        "9dec0a9a7592ba2012470099c8235e2acd2b45f5cdc5107dc7a30279be57d7c7",
    ),
}

RAW_CAPTURE_PINS: Mapping[str, tuple[int, str]] = {
    "adani_data_centers.body": (
        48_315,
        "9f885f27c360c57287ffc1374447a9874a1bba2f6f0e6035792e684ab8fbbac5",
    ),
    "adani_data_centers.headers": (
        3_857,
        "969029707d759bffffeed7596d35bdd85995d96414c4e033527b28ff4fcb65a2",
    ),
    "adani_hyderabad_safety.body": (
        27_808,
        "0b9f17743a4f17bc7be49425a1c93c9b10adcb16c0de2e5b0dbe6ff6eca74f6d",
    ),
    "adani_hyderabad_safety.headers": (
        3_857,
        "3cb9dd869c90e8c40e531815b901d74132c87b251eb2c04b3e579d9d6071537f",
    ),
    "adani_phased_development.body": (
        69_731,
        "ec057dbf5efe7c0b5f8344cbdd7e74b1cf1d208c8ff2545c1f4f4dc45b6721ff",
    ),
    "adani_phased_development.headers": (
        2_617,
        "a2526763e45a0528ace7d01c046bf4ae59ccd4f9bea0270af4cdd9c3aff1ce6e",
    ),
    "ctrls_bhopal_virtual_groundbreaking.body": (
        160_538,
        "96616ad47ddc748e45bc99e01642bde87ab5dc230e864e6d1381bb043ba2d09f",
    ),
    "ctrls_bhopal_virtual_groundbreaking.headers": (
        3_594,
        "a269bee4ee37fb04d953e74c14cb5ec6f20da992d1f48ce1c6aea92f83d71942",
    ),
    "ctrls_chandanvelly_announcement.body": (
        162_353,
        "e88ccabf6f5b1d6afc8d52b04ab0a02c321b2eb9248c91994c3683da1e5c7246",
    ),
    "ctrls_chandanvelly_announcement.headers": (
        3_594,
        "5e3164020d3ff384e737ee8aab8199e1a9e83258bb3046d73793b5612896592b",
    ),
    "ctrls_current_india_linkedin.body": (
        311_176,
        "f98ba2fa19228243287a2845c0bdce83d6399864b447799c280791afc131cfa2",
    ),
    "ctrls_current_india_linkedin.headers": (
        5_301,
        "52cab4ee92fbd6ec46ffe10f1245a3e5d98c07559308851ae304f53fea521dd6",
    ),
    "ctrls_hyderabad.body": (
        272_884,
        "1822fb3465dd181fd8329f6d8b043a6e4c2bdf8eb1ba6e92633398095f0290fe",
    ),
    "ctrls_hyderabad.headers": (
        3_594,
        "a8e0037cf5282cf92aa95d02bb4a32a8704db7d7d219b169dd8c5c512ec59874",
    ),
    "ctrls_mumbai.body": (
        268_743,
        "4e29df9b315373330e27a4a8c3e141b6e502738088455943daf4ac0c5060636d",
    ),
    "ctrls_mumbai.headers": (
        3_594,
        "e74634c02e1eb86170c0db57ff35d3851a3fc6d0aaf893f475f52110e1ee204c",
    ),
    "ctrls_patna.body": (
        344_865,
        "083c3b4abe5179b2ceae984360442c9578f2ad44e091350f7175e193b6f1d5c9",
    ),
    "ctrls_patna.headers": (
        3_594,
        "9f792dd04733f0d7c70c020a0baec51dd7d7bfbe284e4f85c2915d2bebb69974",
    ),
    "ctrls_thailand_future.body": (
        133_075,
        "b7732ab9b141dced06cea5a3770542060232ae74b2992ccbb9db5443072c44a6",
    ),
    "ctrls_thailand_future.headers": (
        5_568,
        "ecf867d1752c20727a97525aa73b8d7ec3f7d0bcf3f22a5c9486b064cce415de",
    ),
    "ctrls_tier2_plans.body": (
        164_175,
        "610fc414f324b6730693da25ffbaad93f1e3b6b54b4fe51c5299f3b89241a2b3",
    ),
    "ctrls_tier2_plans.headers": (
        3_594,
        "967a5ecf450d91f3b9cb1e65e44b8e6319630c49829fd54915bcda2f94682b08",
    ),
    "ntt_bengaluru4.body": (
        403_449,
        "f2f0ac963a4e273d6840bdc31f50b331d8e41690055313320c976c295dbba379",
    ),
    "ntt_bengaluru4.headers": (
        19_099,
        "6f3b9e43061d3b94396394246aa22104d0256a00a25a9b83113357d6a0c5958f",
    ),
    "ntt_india_current_builds_linkedin.body": (
        161_718,
        "103fd3558df637bdf910d6873636b20a049c8d70a7bf4feebbd58bca51a65243",
    ),
    "ntt_india_current_builds_linkedin.headers": (
        5_301,
        "8ee0aec4ed08ddbaebf9f4145368fd8b3c1897150213588df187304763e00fb9",
    ),
    "ntt_india_locations.body": (
        399_226,
        "d11aeb900928e2d5c93a9f7a13d5694c8937cde488ba38ad1e4e69a72bb7866c",
    ),
    "ntt_india_locations.headers": (
        19_099,
        "f84f0d5868067ca68da46282a23093ca1a8ed3fc8831ac5651cd51c3247c6823",
    ),
    "ntt_noida2.body": (
        398_212,
        "d5ad2aaad2c7f3b40666cf94203efb75dc513300e90f64fc5150a73b9e448355",
    ),
    "ntt_noida2.headers": (
        19_097,
        "3241d8d1a8d67416eacea2dee5b6ae24dd45d1ba2d44e47ee92f8c1319c19f64",
    ),
}

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))
SOURCE_RIGHTS = (
    "Official and publisher-authored response bodies are treated as "
    "all-rights-reserved; no redistribution license was relied on."
)

CHANDANVELLY_CAMPUS_KEY = "curated:ctrls-chandanvelly-datacenter-campus"
CHANDANVELLY_PROJECT_KEY = f"{CHANDANVELLY_CAMPUS_KEY}:current-build"
PHARMACITY_CAMPUS_KEY = "curated:ctrls-pharmacity-datacenter-campus"
PHARMACITY_PROJECT_KEY = f"{PHARMACITY_CAMPUS_KEY}:current-build"


class CtrlSPublicationError(RuntimeError):
    """Fail-closed publication error."""


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _content_tree_sha256(root: Path) -> str:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat(follow_symlinks=False).st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]
    return _sha256_bytes(_canonical(rows))


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CtrlSPublicationError("recorded_at must be ISO 8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CtrlSPublicationError("recorded_at must be timezone aware")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], *, mode: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise CtrlSPublicationError(f"missing or unsafe pinned input: {path}")
    metadata = path.stat(follow_symlinks=False)
    if (metadata.st_size, _sha256(path)) != expected:
        raise CtrlSPublicationError(f"pinned input differs: {path}")
    if stat.S_IMODE(metadata.st_mode) != mode:
        raise CtrlSPublicationError(f"pinned input mode differs: {path}")


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(path: Path, *, directory: bool | None = None) -> tuple[int, int]:
    if path.is_symlink():
        raise CtrlSPublicationError(f"symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise CtrlSPublicationError(f"expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise CtrlSPublicationError(f"expected regular file: {path}")
    return metadata.st_dev, metadata.st_ino


def _fstat_identity_with_retry(
    descriptor: int,
    *,
    expected_kind: str,
    label: str,
    expected_mode: int | None = None,
    attempts: int = 2,
) -> tuple[int, int, str]:
    """Capture one open descriptor's identity without rediscovering its path."""

    if attempts < 1:
        raise ValueError("identity attempts must be positive")
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            metadata = os.fstat(descriptor)
        except OSError as error:
            last_error = error
            continue
        actual_kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if actual_kind != expected_kind:
            raise CtrlSPublicationError(
                f"{label} is not an owned {expected_kind}; path retained for manual review"
            )
        if (
            expected_mode is not None
            and stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise CtrlSPublicationError(
                f"{label} mode differs; path retained for manual review"
            )
        return metadata.st_dev, metadata.st_ino, actual_kind
    raise CtrlSPublicationError(
        f"{label} identity unavailable after {attempts} attempts; "
        "path retained for manual review"
    ) from last_error


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        if path.is_symlink():
            return False
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        return False
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        return False
    return (metadata.st_dev, metadata.st_ino) == expected


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise CtrlSPublicationError(f"unsafe tree root: {root}")
    result: dict[str, tuple[int, int, str]] = {}
    for candidate in (root, *sorted(root.rglob("*"))):
        if candidate.is_symlink():
            raise CtrlSPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        kind = (
            "directory"
            if stat.S_ISDIR(metadata.st_mode)
            else "file"
            if stat.S_ISREG(metadata.st_mode)
            else "other"
        )
        if kind == "other":
            raise CtrlSPublicationError(f"special file in governed tree: {candidate}")
        relative = "." if candidate == root else candidate.relative_to(root).as_posix()
        result[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return result


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise CtrlSPublicationError(f"tree identity changed: {root}")


def _record_owned_stage_identity(
    stage: Path,
    identities: dict[str, tuple[int, int, str]],
    *,
    label: str,
) -> None:
    """Record the inode returned by an open handle to a freshly created stage."""

    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(stage, flags)
    except OSError as error:
        raise CtrlSPublicationError(
            f"{label} identity unavailable; path retained for manual review"
        ) from error
    try:
        identity = _fstat_identity_with_retry(
            descriptor,
            expected_kind="directory",
            expected_mode=0o700,
            label=label,
        )
        identities["."] = identity
        if not _has_identity(stage, identity[:2], directory=True):
            raise CtrlSPublicationError(
                f"{label} identity changed; path retained for manual review"
            )
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class ReviewedInputIdentities:
    sources: Mapping[str, tuple[int, int, str]]
    artifact: Mapping[str, tuple[int, int, str]]
    captures: Mapping[str, tuple[int, int, str]]


def _validate_reviewed_inputs() -> ReviewedInputIdentities:
    if (
        REVIEWED_SOURCE_STAGE.is_symlink()
        or not REVIEWED_SOURCE_STAGE.is_dir()
        or stat.S_IMODE(REVIEWED_SOURCE_STAGE.stat().st_mode) != 0o700
    ):
        raise CtrlSPublicationError("reviewed source stage is missing or unsafe")
    source_entries = {path.name: path for path in REVIEWED_SOURCE_STAGE.iterdir()}
    if set(source_entries) != set(REVIEWED_SOURCE_PINS):
        raise CtrlSPublicationError("reviewed source stage inventory differs")
    for name, pin in REVIEWED_SOURCE_PINS.items():
        _pin(source_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_SOURCE_STAGE) != REVIEWED_SOURCE_TREE_SHA256:
        raise CtrlSPublicationError("reviewed source stage tree differs")

    if (
        REVIEWED_ARTIFACT_STAGE.is_symlink()
        or not REVIEWED_ARTIFACT_STAGE.is_dir()
        or stat.S_IMODE(REVIEWED_ARTIFACT_STAGE.stat().st_mode) != 0o700
    ):
        raise CtrlSPublicationError("reviewed artifact stage is missing or unsafe")
    artifact_entries = {path.name: path for path in REVIEWED_ARTIFACT_STAGE.iterdir()}
    if set(artifact_entries) != set(REVIEWED_ARTIFACT_PINS):
        raise CtrlSPublicationError("reviewed artifact stage inventory differs")
    for name, pin in REVIEWED_ARTIFACT_PINS.items():
        _pin(artifact_entries[name], pin, mode=0o600)
    if tree_digest(REVIEWED_ARTIFACT_STAGE) != REVIEWED_ARTIFACT_TREE_SHA256:
        raise CtrlSPublicationError("reviewed artifact stage tree differs")
    reviewed_manifest = json.loads(
        artifact_entries["manifest.json"].read_text(encoding="utf-8")
    )
    if (
        reviewed_manifest.get("artifact_id") != REVIEWED_CANDIDATE_ID
        or reviewed_manifest.get("published") is not False
        or reviewed_manifest.get("recorded_at") != REVIEWED_RECORDED_AT
        or reviewed_manifest.get("candidate_assessments") != 12
        or reviewed_manifest.get("curated_source_candidates") != 2
        or reviewed_manifest.get("review_only_candidates") != 10
    ):
        raise CtrlSPublicationError("reviewed candidate manifest differs")
    if artifact_entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{REVIEWED_ARTIFACT_PINS['manifest.json'][1]}  manifest.json\n"
    ):
        raise CtrlSPublicationError("reviewed candidate checksum differs")

    if (
        _raw_capture().is_symlink()
        or not _raw_capture().is_dir()
        or stat.S_IMODE(_raw_capture().stat().st_mode) != 0o555
    ):
        raise CtrlSPublicationError("raw capture bundle is missing or unsafe")
    raw_entries = {path.name: path for path in _raw_capture().iterdir()}
    if set(raw_entries) != set(RAW_CAPTURE_PINS):
        raise CtrlSPublicationError("raw capture inventory differs")
    for name, pin in RAW_CAPTURE_PINS.items():
        _pin(raw_entries[name], pin, mode=0o444)
    if (
        len(RAW_CAPTURE_PINS) != 30
        or sum(pin[0] for pin in RAW_CAPTURE_PINS.values()) != 3_431_628
    ):
        raise CtrlSPublicationError("raw capture pin contract differs")
    if tree_digest(_raw_capture()) != RAW_CAPTURE_TREE_SHA256:
        raise CtrlSPublicationError("raw capture tree differs")

    identities = ReviewedInputIdentities(
        _tree_identities(REVIEWED_SOURCE_STAGE),
        _tree_identities(REVIEWED_ARTIFACT_STAGE),
        _tree_identities(_raw_capture()),
    )
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(_raw_capture(), identities.captures)
    return identities


def _assert_reviewed_input_identities(
    identities: ReviewedInputIdentities,
) -> None:
    _assert_tree_identities(REVIEWED_SOURCE_STAGE, identities.sources)
    _assert_tree_identities(REVIEWED_ARTIFACT_STAGE, identities.artifact)
    _assert_tree_identities(_raw_capture(), identities.captures)


def _walk_strings(
    value: Any, path: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_strings(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, (*path, str(index)))


def _assert_accepted_carrier_redacted(value: Any) -> None:
    banned_text = (
        "/users/",
        "/private/",
        "prepublication",
        "prospective-sources",
        str(REVIEWED_SOURCE_STAGE).lower(),
        str(REVIEWED_ARTIFACT_STAGE).lower(),
        str(_raw_capture()).lower(),
    )
    banned_keys = {
        "artifact_stage",
        "source_stage",
        "prepublication_contract",
        "curated_source_candidates",
        "governed_prepublication_candidates",
        "prospective_final_artifact_exists",
        "prospective_final_source_exists",
    }
    for path, text in _walk_strings(value):
        if any(component in banned_keys for component in path):
            raise CtrlSPublicationError(f"candidate-only carrier key leaked: {path!r}")
        lowered = text.lower()
        if any(token in lowered for token in banned_text):
            raise CtrlSPublicationError(f"private or candidate text leaked: {path!r}")


def _assert_claim_boundaries(documents: Mapping[str, Mapping[str, Any]]) -> None:
    if tuple(documents) != SOURCE_FILENAMES:
        raise CtrlSPublicationError("accepted source inventory differs")
    if sum(len(document["evidence"]) for document in documents.values()) != 3:
        raise CtrlSPublicationError("accepted evidence count differs")
    if sum(len(document["lifecycle"]) for document in documents.values()) != 2:
        raise CtrlSPublicationError("accepted lifecycle count differs")
    for document in documents.values():
        if (
            document["schema_version"] != "1.1"
            or document["operating_models"]
            or document["workloads"]
            or document["capacities"]
        ):
            raise CtrlSPublicationError(
                "accepted type/workload/capacity/energy boundary differs"
            )
        for entity in ("campus", "project"):
            if (
                document[entity]["coordinates"] is not None
                or document[entity]["geometry"] is not None
            ):
                raise CtrlSPublicationError("accepted spatial boundary differs")

            if document[entity]["roles"] != {"developer": ["CtrlS Datacenters Ltd"]}:
                raise CtrlSPublicationError("accepted developer-role boundary differs")

    chandan = documents[CHANDANVELLY_SOURCE_FILENAME]
    current = next(
        row
        for row in chandan["evidence"]
        if row["key"]
        == "ctrls-chandanvelly-building-page-modified-2026-07-21-captured-2026-07-22"
    )
    announcement = next(
        row
        for row in chandan["evidence"]
        if row["key"]
        == "ctrls-chandanvelly-announcement-2025-01-20-captured-2026-07-22"
    )
    if (
        chandan["campus"]["stable_key"] != CHANDANVELLY_CAMPUS_KEY
        or chandan["project"]["stable_key"] != CHANDANVELLY_PROJECT_KEY
        or chandan["lifecycle"]
        != [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": current["key"],
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ]
        or current["metadata"]["current_page_capacity_not_normalized"][
            "capacity_row_created"
        ]
        is not False
        or current["metadata"]["sanctioned_power_not_normalized"][
            "capacity_row_created"
        ]
        is not False
        or announcement["metadata"]["announcement_only"] is not True
        or announcement["metadata"]["lifecycle_claim_from_this_evidence"] is not False
        or announcement["metadata"]["reported_potential_it_load"][
            "capacity_row_created"
        ]
        is not False
    ):
        raise CtrlSPublicationError("Chandanvelly claim boundary differs")

    pharmacity = documents[PHARMACITY_SOURCE_FILENAME]
    evidence = pharmacity["evidence"][0]
    if (
        pharmacity["campus"]["stable_key"] != PHARMACITY_CAMPUS_KEY
        or pharmacity["project"]["stable_key"] != PHARMACITY_PROJECT_KEY
        or pharmacity["lifecycle"]
        != [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": evidence["key"],
                "as_of_date": "2026-07-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.98,
            }
        ]
        or evidence["metadata"]["capacity_not_normalized"]["capacity_row_created"]
        is not False
        or evidence["metadata"]["green_power_not_normalized"][
            "energy_or_efficiency_row_created"
        ]
        is not False
    ):
        raise CtrlSPublicationError("Pharmacity claim boundary differs")


def _load_reviewed_documents() -> dict[str, dict[str, Any]]:
    identities = _validate_reviewed_inputs()
    documents: dict[str, dict[str, Any]] = {}
    for name in SOURCE_FILENAMES:
        raw = (REVIEWED_SOURCE_STAGE / name).read_bytes()
        document = json.loads(raw)
        if document.get("schema_version") != "1.1":
            raise CtrlSPublicationError(f"reviewed source schema differs: {name}")
        if _canonical(document) != raw:
            raise CtrlSPublicationError(f"reviewed source is not canonical: {name}")
        documents[name] = document
    _assert_reviewed_input_identities(identities)
    _assert_claim_boundaries(documents)
    return documents


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return _load_reviewed_documents()


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dispositions = {
        CHANDANVELLY_SOURCE_FILENAME: "accepted_official_current_physical_build",
        PHARMACITY_SOURCE_FILENAME: "accepted_official_current_physical_build",
    }
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = (REVIEWED_SOURCE_STAGE / name).read_bytes()
        if payload != _canonical(document):
            raise CtrlSPublicationError(f"accepted source bytes differ: {name}")
        rows.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["campus"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": len(document["workloads"]),
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": sum(
                    document[entity]["coordinates"] is not None
                    for entity in ("campus", "project")
                ),
                "geometry_present": sum(
                    document[entity]["geometry"] is not None
                    for entity in ("campus", "project")
                ),
                "disposition": dispositions[name],
                "accepted": True,
                "published": True,
                "seeded": False,
            }
        )
    return rows


def _accepted_assessment(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "candidate-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = copy.deepcopy(reviewed["candidates"])
    accepted = {
        "ctrls-chandanvelly-current-build": CHANDANVELLY_SOURCE_FILENAME,
        "ctrls-pharmacity-current-build": PHARMACITY_SOURCE_FILENAME,
    }
    expected_rejected = {
        "ctrls-mumbai-dc6-dc7",
        "ctrls-bhopal-greenfield",
        "ctrls-patna-edge-dc2",
        "ctrls-tier2-planned-sites",
        "ctrls-thailand-chonburi-campus",
        "ntt-india-four-unnamed-builds",
        "ntt-bengaluru-4b-4c",
        "ntt-noida-2-building-b",
        "adaniconnex-hyderabad-future-phases",
        "adaniconnex-noida-future-phases",
    }
    for row in rows:
        candidate_id = row["candidate_id"]
        if candidate_id in accepted:
            filename = accepted[candidate_id]
            row["decision"] = "accepted_official_current_physical_build"
            row["source_paths"] = [f"sources/{filename}"]
            row["accepted"] = True
            row["published"] = True
            row["rejected"] = False
        else:
            if candidate_id not in expected_rejected:
                raise CtrlSPublicationError(
                    f"unexpected reviewed candidate: {candidate_id}"
                )
            decision = str(row["decision"])
            row["decision"] = (
                decision if decision.startswith("rejected_") else f"rejected_{decision}"
            )
            row["source_paths"] = []
            row["stable_key_created"] = False
            row["evidence_record_created"] = False
            row["lifecycle_claim_created"] = False
            row["capacity_claim_created"] = False
            row["energy_claim_created"] = False
            row["accepted"] = False
            row["published"] = False
            row["rejected"] = True
    if {row["candidate_id"] for row in rows if row["rejected"]} != expected_rejected:
        raise CtrlSPublicationError("rejected exclusion inventory differs")
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 12,
        "accepted_source_record_count": 2,
        "published_source_record_count": 2,
        "rejected_review_only_count": 10,
        "operator_completeness_claimed": False,
        "candidates": rows,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    reviewed = json.loads(
        (REVIEWED_ARTIFACT_STAGE / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
    )
    reviewed["artifact_id"] = ARTIFACT_ID
    reviewed["recorded_at"] = recorded_at
    reviewed.pop("capture_directory", None)
    reviewed["raw_capture_storage_path_redacted"] = True
    reviewed["raw_capture_retained_private"] = True
    reviewed["raw_capture_redistributed"] = False
    return reviewed


def _reviewed_candidate_lineage() -> dict[str, Any]:
    return {
        "purpose": "hash_only_reviewed_candidate_lineage",
        "reviewed_identifier_sha256": _sha256_bytes(
            REVIEWED_CANDIDATE_ID.encode("utf-8")
        ),
        "reviewed_artifact_manifest_sha256": REVIEWED_ARTIFACT_PINS["manifest.json"][1],
        "reviewed_artifact_tree_sha256": REVIEWED_ARTIFACT_TREE_SHA256,
        "reviewed_source_tree_sha256": REVIEWED_SOURCE_TREE_SHA256,
        "reviewed_source_file_pins": [
            {"bytes": pin[0], "sha256": pin[1]}
            for _name, pin in sorted(REVIEWED_SOURCE_PINS.items())
        ],
        "reviewed_artifact_file_pins": [
            {"bytes": pin[0], "sha256": pin[1]}
            for _name, pin in sorted(REVIEWED_ARTIFACT_PINS.items())
        ],
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "raw_capture_file_pins": [
            {"bytes": pin[0], "sha256": pin[1]}
            for _name, pin in sorted(RAW_CAPTURE_PINS.items())
        ],
        "reviewed_source_payloads_byte_identical": True,
        "reviewed_input_inodes_promoted": False,
    }


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(documents)
    assessment = _accepted_assessment(recorded_at)
    readme = f"""# CtrlS Chandanvelly and Pharmacity current-build tranche

This immutable accepted source artifact publishes two official-source records at {recorded_at}: the CtrlS Chandanvelly Datacenter Campus and CtrlS Pharmacity Datacenter Campus near Hyderabad, India.

The records contain four entity snapshots, three evidence rows, and two generic `under_construction` lifecycle observations as of 2026-07-21. They contain zero facility-type, operating-model, workload, capacity, energy-consumption, efficiency, coordinate, geometry, satellite, aerial, map-derived, or computer-vision rows. Displayed capacity, sanctioned-power, potential IT-load, green-power, and design-PUE statements remain source metadata only.

Ten weaker signals remain rejected review-only exclusions: CtrlS Mumbai DC6/DC7, Bhopal, Patna DC2, the tier-2 planned portfolio, and Chonburi; NTT's four unnamed India builds, Bengaluru 4B/4C, and Noida 2B; and phase-ambiguous AdaniConneX Hyderabad and Noida successors. They create no source record, stable key, evidence row, lifecycle observation, capacity claim, or energy claim.

Publication is limited to the two byte-identical reviewed source payloads copied into fresh governed inodes and this redacted artifact. No open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or other downstream file is created or modified. The frozen 30-file official-response bundle remains private in place and is not redistributed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "operator_completeness_claimed": False,
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 12,
            "accepted_source_records": 2,
            "published_source_records": 2,
            "rejected_review_only_candidates": 10,
            "distinct_campuses": 2,
            "projects": 2,
            "distinct_entity_snapshots": 4,
            "new_entities_against_v95": 4,
            "reused_existing_entities": 0,
            "evidence_records": 3,
            "lifecycle_observations": 2,
            "facility_type_observations": 0,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        },
        "reviewed_candidate_lineage": _reviewed_candidate_lineage(),
        "integration": {
            "published": True,
            "accepted": True,
            "open_seed_successor_created": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
            "downstream_files_touched": [],
        },
        "publication_contract": {
            "version": 1,
            "authorization_required": True,
            "unique_sibling_stages": True,
            "lock_required": True,
            "future_recorded_at_required": True,
            "wait_live_before_freeze": True,
            "same_filesystem_private_stages": True,
            "recursive_inode_recheck_before_freeze": True,
            "byte_and_tree_recheck_before_and_after_freeze": True,
            "exactly_two_offline_import_passes": True,
            "atomic_no_replace_promotion": True,
            "identity_checked_rollback": True,
            "all_recursive_stage_birthtimes_and_mtimes_at_or_before_recorded_at": True,
            "all_recursive_final_ctimes_at_or_after_recorded_at": True,
            "source_file_mode": "0444",
            "source_stage_transport_directory_mode": "0700",
            "artifact_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "existing_identical_replay": True,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": SOURCE_RIGHTS,
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "raw_capture_storage_path_redacted": True,
        "raw_capture_retained_private": True,
        "raw_capture_file_count": 30,
        "raw_capture_total_bytes": 3_431_628,
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "publication_performed": True,
        "deletion_performed": False,
    }
    payloads = {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }
    carrier = {
        name: json.loads(raw)
        for name, raw in payloads.items()
        if name.endswith(".json")
    }
    _assert_accepted_carrier_redacted(carrier)
    for name, raw in payloads.items():
        lowered = raw.decode("utf-8").lower()
        for token in ("/users/", "/private/", "prepublication", "prospective-sources"):
            if token in lowered:
                raise CtrlSPublicationError(
                    f"private or candidate text leaked into accepted {name}"
                )
    return payloads


def _offline_import(
    source_paths: Mapping[str, Path], recorded_at: str
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="ctrls-accepted-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(
                    connection, source_paths[name], recorded_at=recorded_at
                )
        errors = validate_database(connection)
        if errors:
            raise CtrlSPublicationError(
                f"offline database validation failed: {errors!r}"
            )
        tables = (
            "entities",
            "entity_snapshots",
            "evidence",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 4,
            "entity_snapshots": 4,
            "evidence": 3,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise CtrlSPublicationError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _write_new_file(
    path: Path,
    payload: bytes,
    identities: dict[str, tuple[int, int, str]],
    relative: str,
) -> None:
    if relative in identities:
        raise CtrlSPublicationError(f"duplicate owned-stage member: {relative}")
    descriptor = os.open(
        path,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        identity = _fstat_identity_with_retry(
            stream.fileno(),
            expected_kind="file",
            expected_mode=0o600,
            label=f"owned stage member {relative}",
        )
        identities[relative] = identity
        if not _has_identity(path, identity[:2], directory=False):
            raise CtrlSPublicationError(
                f"owned stage member identity changed: {relative}"
            )
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if not _has_identity(path, identity[:2], directory=False):
        raise CtrlSPublicationError(f"owned stage member identity changed: {relative}")


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
    identities: dict[str, tuple[int, int, str]],
) -> None:
    for name in SOURCE_FILENAMES:
        reviewed = (REVIEWED_SOURCE_STAGE / name).read_bytes()
        if reviewed != _canonical(documents[name]):
            raise CtrlSPublicationError(f"reviewed source bytes changed: {name}")
        _write_new_file(stage / name, reviewed, identities, name)
    stage.chmod(0o700)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
    identities: dict[str, tuple[int, int, str]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        _write_new_file(stage / name, payloads[name], identities, name)
    rows = [
        {
            "path": name,
            "bytes": (stage / name).stat().st_size,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = _expected_manifest(recorded_at, rows)
    manifest_path = stage / "manifest.json"
    _write_new_file(
        manifest_path,
        _canonical(manifest),
        identities,
        "manifest.json",
    )
    _write_new_file(
        stage / "manifest.sha256",
        f"{_sha256(manifest_path)}  manifest.json\n".encode("utf-8"),
        identities,
        "manifest.sha256",
    )
    stage.chmod(0o700)
    _fsync_directory(stage)


def _expected_manifest(recorded_at: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 12,
        "accepted_source_records": 2,
        "published_source_records": 2,
        "rejected_review_only_candidates": 10,
        "successful_http_200_body_captures": 15,
        "raw_capture_file_count": len(RAW_CAPTURE_PINS),
        "raw_capture_total_bytes": sum(pin[0] for pin in RAW_CAPTURE_PINS.values()),
        "raw_capture_tree_sha256": RAW_CAPTURE_TREE_SHA256,
        "source_rights": SOURCE_RIGHTS,
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "published": True,
        "accepted": True,
        "operator_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "authorization_required": True,
    }


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    if root.is_symlink():
        raise CtrlSPublicationError(f"symlink is not allowed: {root}")
    for candidate in (root, *root.rglob("*")):
        if candidate.is_symlink():
            raise CtrlSPublicationError(f"symlink in governed tree: {candidate}")
        metadata = candidate.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birthtime, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise CtrlSPublicationError(
                f"private stage post-dates recorded_at: {candidate}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    if root.is_symlink():
        raise CtrlSPublicationError(f"symlink is not allowed: {root}")
    for candidate in (root, *root.rglob("*")):
        if candidate.is_symlink():
            raise CtrlSPublicationError(f"symlink in governed tree: {candidate}")
        if (
            candidate.stat(follow_symlinks=False).st_ctime + 0.000_001
            < target.timestamp()
        ):
            raise CtrlSPublicationError(
                f"final member ctime predates recorded_at: {candidate}"
            )


def _freeze_stages(
    source_stage: Path,
    artifact_stage: Path,
    source_identities: Mapping[str, tuple[int, int, str]],
    artifact_identities: Mapping[str, tuple[int, int, str]],
) -> None:
    for root, identities, root_mode in (
        (source_stage, source_identities, 0o700),
        (artifact_stage, artifact_identities, 0o555),
    ):
        _assert_tree_identities(root, identities)
        for relative, expected in sorted(identities.items()):
            if expected[2] != "file":
                continue
            path = root / relative
            if not _has_identity(path, expected[:2], directory=False):
                raise CtrlSPublicationError(
                    f"refusing identity-mismatched stage freeze: {path}"
                )
            path.chmod(0o444)
            _fsync_regular(path)
        directories = [
            (relative, expected)
            for relative, expected in identities.items()
            if relative != "." and expected[2] == "directory"
        ]
        for relative, expected in sorted(
            directories,
            key=lambda item: len(Path(item[0]).parts),
            reverse=True,
        ):
            path = root / relative
            if not _has_identity(path, expected[:2], directory=True):
                raise CtrlSPublicationError(
                    f"refusing identity-mismatched stage freeze: {path}"
                )
            path.chmod(0o555)
            _fsync_directory(path)
        root_identity = identities.get(".")
        if root_identity is None or root_identity[2] != "directory":
            raise CtrlSPublicationError("owned stage root identity is missing")
        if not _has_identity(root, root_identity[:2], directory=True):
            raise CtrlSPublicationError(
                f"refusing identity-mismatched stage freeze: {root}"
            )
        root.chmod(root_mode)
        _fsync_directory(root)
        _assert_tree_identities(root, identities)


def _validate_sources(
    paths: Mapping[str, Path],
    documents: Mapping[str, Mapping[str, Any]],
    *,
    frozen: bool,
    recorded_at: str,
    run_offline_import: bool,
) -> list[dict[str, Any]]:
    if set(paths) != set(SOURCE_FILENAMES):
        raise CtrlSPublicationError("accepted source inventory differs")
    expected_mode = 0o444 if frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise CtrlSPublicationError(f"accepted source is missing or unsafe: {name}")
        if stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise CtrlSPublicationError(f"accepted source mode differs: {name}")
        if path.read_bytes() != (REVIEWED_SOURCE_STAGE / name).read_bytes():
            raise CtrlSPublicationError(f"accepted source differs: {name}")
    if run_offline_import:
        _offline_import(paths, recorded_at)
    return _source_records(documents)


def _validate_artifact(
    artifact: Path,
    source_paths: Mapping[str, Path],
    *,
    frozen: bool,
    require_live: bool,
    require_final_chronology: bool,
    run_offline_import: bool,
    documents: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = dict(documents or expected_source_documents())
    _assert_claim_boundaries(documents)
    if artifact.is_symlink() or not artifact.is_dir():
        raise CtrlSPublicationError("accepted artifact is missing or unsafe")
    expected_directory_mode = 0o555 if frozen else 0o700
    expected_file_mode = 0o444 if frozen else 0o600
    if stat.S_IMODE(artifact.stat().st_mode) != expected_directory_mode:
        raise CtrlSPublicationError("accepted artifact directory mode differs")
    entries = {path.name: path for path in artifact.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise CtrlSPublicationError("accepted artifact closed file set differs")
    for name, path in entries.items():
        if path.is_symlink() or not path.is_file():
            raise CtrlSPublicationError(f"unsafe accepted artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != expected_file_mode:
            raise CtrlSPublicationError(
                f"accepted artifact member mode differs: {name}"
            )
    manifest_raw = entries["manifest.json"].read_bytes()
    try:
        manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CtrlSPublicationError(
            "accepted manifest is not canonical JSON"
        ) from error
    if not isinstance(manifest, dict) or not isinstance(
        manifest.get("recorded_at"), str
    ):
        raise CtrlSPublicationError("accepted manifest recorded_at differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], documents)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise CtrlSPublicationError(f"accepted artifact content differs: {name}")
    expected_rows = [
        {
            "path": name,
            "bytes": len(expected_payloads[name]),
            "sha256": _sha256_bytes(expected_payloads[name]),
        }
        for name in CONTENT_FILES
    ]
    expected_manifest = _expected_manifest(manifest["recorded_at"], expected_rows)
    if manifest_raw != _canonical(expected_manifest):
        raise CtrlSPublicationError("accepted manifest differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise CtrlSPublicationError("accepted manifest checksum differs")
    source_records = _validate_sources(
        source_paths,
        documents,
        frozen=frozen,
        recorded_at=manifest["recorded_at"],
        run_offline_import=run_offline_import,
    )
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise CtrlSPublicationError("accepted source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    carrier = {
        name: json.loads(path.read_bytes())
        for name, path in entries.items()
        if name.endswith(".json")
    }
    _assert_accepted_carrier_redacted(carrier)
    rejected = [row for row in assessment["candidates"] if row["rejected"]]
    if len(rejected) != 10:
        raise CtrlSPublicationError("rejected review-only count differs")
    for row in rejected:
        if (
            row["accepted"] is not False
            or row["published"] is not False
            or row["source_paths"]
            or row["stable_key_created"] is not False
            or row["lifecycle_claim_created"] is not False
            or row["evidence_record_created"] is not False
            or row["capacity_claim_created"] is not False
            or row["energy_claim_created"] is not False
        ):
            raise CtrlSPublicationError("rejected claim boundary differs")
    target = _instant(manifest["recorded_at"])
    if require_live and datetime.now(UTC) < target:
        raise CtrlSPublicationError("accepted recorded_at is not live")
    if require_final_chronology:
        _assert_stage_precedes(artifact, target)
        _assert_recursive_ctimes_at_or_after(artifact, target)
        for path in source_paths.values():
            _assert_stage_precedes(path, target)
            _assert_recursive_ctimes_at_or_after(path, target)
    return manifest


@dataclass(frozen=True)
class PreparedPublication:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str
    documents: Mapping[str, Mapping[str, Any]]
    source_identities: Mapping[str, tuple[int, int, str]]
    artifact_identities: Mapping[str, tuple[int, int, str]]
    reviewed_input_identities: ReviewedInputIdentities
    source_tree_sha256: str
    artifact_tree_sha256: str


def _final_source_paths() -> dict[str, Path]:
    return {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}


def _final_presence() -> tuple[bool, list[str]]:
    paths = {"artifact": ARTIFACT, **_final_source_paths()}
    present = [
        name for name, path in paths.items() if path.exists() or path.is_symlink()
    ]
    return len(present) == len(paths), present


def _assert_final_absent() -> None:
    complete, present = _final_presence()
    if complete or present:
        raise CtrlSPublicationError(f"final-path collision: {present!r}")


def _assert_no_later_source_collisions() -> None:
    stable_keys = {
        CHANDANVELLY_CAMPUS_KEY,
        CHANDANVELLY_PROJECT_KEY,
        PHARMACITY_CAMPUS_KEY,
        PHARMACITY_PROJECT_KEY,
    }
    evidence_keys = {
        "ctrls-chandanvelly-building-page-modified-2026-07-21-captured-2026-07-22",
        "ctrls-chandanvelly-announcement-2025-01-20-captured-2026-07-22",
        "ctrls-pharmacity-building-page-modified-2026-07-21-captured-2026-07-22",
    }
    collisions: list[str] = []
    for path in sorted(SOURCES_ROOT.glob("curated-*.json")):
        if path.name in SOURCE_FILENAMES:
            continue
        if path.is_symlink() or not path.is_file():
            collisions.append(f"unsafe:{path.name}")
            continue
        try:
            document = json.loads(path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            collisions.append(f"unreadable:{path.name}")
            continue
        for entity_name in ("campus", "project"):
            entity = document.get(entity_name)
            if not isinstance(entity, dict):
                continue
            if entity.get("stable_key") in stable_keys:
                collisions.append(f"stable-key:{path.name}:{entity_name}")
            identity = " ".join(
                str(entity.get(field, "")) for field in ("name", "address")
            ).lower()
            if "chandanvelly" in identity or "pharmacity" in identity:
                collisions.append(f"identity:{path.name}:{entity_name}")
        for evidence in document.get("evidence", []):
            if isinstance(evidence, dict) and evidence.get("key") in evidence_keys:
                collisions.append(f"evidence:{path.name}")
    if collisions:
        raise CtrlSPublicationError(
            f"accepted source collides with a later curated source: {collisions!r}"
        )


def _prepare(
    recorded_at: str, *, allow_complete_finals: bool = False
) -> PreparedPublication:
    complete, present = _final_presence()
    if present and not complete:
        raise CtrlSPublicationError(f"partial final-path collision: {present!r}")
    if complete and not allow_complete_finals:
        raise CtrlSPublicationError(f"final-path collision: {present!r}")
    _assert_no_later_source_collisions()
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise CtrlSPublicationError("recorded_at must be future before staging")
    reviewed_identities = _validate_reviewed_inputs()
    documents = expected_source_documents()
    source_stage: Path | None = None
    artifact_stage: Path | None = None
    source_identities: dict[str, tuple[int, int, str]] = {}
    artifact_identities: dict[str, tuple[int, int, str]] = {}
    try:
        source_stage = Path(
            tempfile.mkdtemp(
                prefix=".ctrls-chandanvelly-pharmacity-source-stage-",
                dir=SOURCES_ROOT,
            )
        )
        _record_owned_stage_identity(
            source_stage, source_identities, label="created source stage"
        )
        artifact_stage = Path(
            tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
        )
        _record_owned_stage_identity(
            artifact_stage, artifact_identities, label="created artifact stage"
        )
        if source_identities["."][0] != SOURCES_ROOT.stat().st_dev:
            raise CtrlSPublicationError("source stage is not on target filesystem")
        if artifact_identities["."][0] != ARTIFACT_ROOT.stat().st_dev:
            raise CtrlSPublicationError("artifact stage is not on target filesystem")
        _write_source_stage(source_stage, documents, source_identities)
        _write_artifact_stage(
            artifact_stage, recorded_at, documents, artifact_identities
        )
        _assert_stage_precedes(source_stage, target)
        _assert_stage_precedes(artifact_stage, target)
        _assert_tree_identities(source_stage, source_identities)
        _assert_tree_identities(artifact_stage, artifact_identities)
        source_tree = _content_tree_sha256(source_stage)
        artifact_tree = _content_tree_sha256(artifact_stage)
        _validate_artifact(
            artifact_stage,
            _source_paths(source_stage),
            frozen=False,
            require_live=False,
            require_final_chronology=False,
            run_offline_import=True,
            documents=documents,
        )
        _assert_tree_identities(source_stage, source_identities)
        _assert_tree_identities(artifact_stage, artifact_identities)
        _assert_reviewed_input_identities(reviewed_identities)
        return PreparedPublication(
            source_stage,
            artifact_stage,
            recorded_at,
            documents,
            dict(source_identities),
            dict(artifact_identities),
            reviewed_identities,
            source_tree,
            artifact_tree,
        )
    except BaseException as error:
        _cleanup_owned_stage_after_error(
            artifact_stage, artifact_identities, "artifact", error
        )
        _cleanup_owned_stage_after_error(
            source_stage, source_identities, "source", error
        )
        raise


def _assert_prepared_exact(prepared: PreparedPublication, *, frozen: bool) -> None:
    _assert_tree_identities(prepared.source_stage, prepared.source_identities)
    _assert_tree_identities(prepared.artifact_stage, prepared.artifact_identities)
    if _content_tree_sha256(prepared.source_stage) != prepared.source_tree_sha256:
        raise CtrlSPublicationError("prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise CtrlSPublicationError("prepared artifact tree differs")
    _assert_stage_precedes(prepared.source_stage, _instant(prepared.recorded_at))
    _assert_stage_precedes(prepared.artifact_stage, _instant(prepared.recorded_at))
    _validate_artifact(
        prepared.artifact_stage,
        _source_paths(prepared.source_stage),
        frozen=frozen,
        require_live=False,
        require_final_chronology=False,
        run_offline_import=False,
        documents=prepared.documents,
    )


def _cleanup_owned_stage_after_error(
    root: Path | None,
    identities: Mapping[str, tuple[int, int, str]],
    label: str,
    error: BaseException,
) -> None:
    if root is None or not (root.exists() or root.is_symlink()):
        return
    if "." not in identities:
        error.add_note(
            f"CtrlS {label} stage retained because its creation-time identity "
            "is unavailable"
        )
        return
    try:
        _discard_owned_tree(root, identities)
    except Exception as cleanup_error:
        error.add_note(
            f"CtrlS {label} stage cleanup refused; retained for manual review: "
            f"{cleanup_error}"
        )


def _discard_owned_tree(
    root: Path, expected_identities: Mapping[str, tuple[int, int, str]]
) -> None:
    identities = dict(expected_identities)
    root_identity = identities.get(".")
    if root_identity is None or root_identity[2] != "directory":
        raise CtrlSPublicationError("owned stage root identity is missing")
    _assert_tree_identities(root, identities)
    directories = [
        (relative, identity)
        for relative, identity in identities.items()
        if identity[2] == "directory"
    ]
    files = [
        (relative, identity)
        for relative, identity in identities.items()
        if identity[2] == "file"
    ]
    for relative, identity in sorted(
        directories,
        key=lambda item: len(Path(item[0]).parts),
        reverse=True,
    ):
        directory = root if relative == "." else root / relative
        if not _has_identity(directory, identity[:2], directory=True):
            raise CtrlSPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.chmod(0o700)
    for relative, identity in files:
        path = root / relative
        if not _has_identity(path, identity[:2], directory=False):
            raise CtrlSPublicationError(
                f"refusing identity-mismatched stage cleanup: {path}"
            )
        path.unlink()
    for relative, identity in sorted(
        directories,
        key=lambda item: len(Path(item[0]).parts),
        reverse=True,
    ):
        directory = root if relative == "." else root / relative
        if not _has_identity(directory, identity[:2], directory=True):
            raise CtrlSPublicationError(
                f"refusing identity-mismatched stage cleanup: {directory}"
            )
        directory.rmdir()


def preflight(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Render, import twice, freeze, validate, and discard exact final bytes."""

    complete_before, present_before = _final_presence()
    if present_before and not complete_before:
        raise CtrlSPublicationError(f"partial final-path collision: {present_before!r}")
    if complete_before:
        _existing_identical(None)
    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    )
    if datetime.now(UTC) >= target:
        raise CtrlSPublicationError("preflight recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared = _prepare(timestamp, allow_complete_finals=True)
    source_stage = prepared.source_stage
    artifact_stage = prepared.artifact_stage
    try:
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
        _assert_prepared_exact(prepared, frozen=False)
        _freeze_stages(
            source_stage,
            artifact_stage,
            prepared.source_identities,
            prepared.artifact_identities,
        )
        _assert_prepared_exact(prepared, frozen=True)
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
        manifest_sha256 = _sha256(artifact_stage / "manifest.json")
        artifact_tree_sha256 = tree_digest(artifact_stage)
        source_tree_sha256 = tree_digest(source_stage)
        source_pins = [
            {
                "path": f"sources/{name}",
                "bytes": (source_stage / name).stat().st_size,
                "sha256": _sha256(source_stage / name),
            }
            for name in SOURCE_FILENAMES
        ]
        result = {
            "status": "PREFLIGHT_VALIDATED_AND_DISCARDED",
            "recorded_at": timestamp,
            "artifact_id": ARTIFACT_ID,
            "artifact_manifest_sha256": manifest_sha256,
            "artifact_tree_sha256": artifact_tree_sha256,
            "source_tree_sha256": source_tree_sha256,
            "source_pins": source_pins,
            "rows": {
                "entity_snapshots": 4,
                "evidence": 3,
                "lifecycle": 2,
                "facility_types": 0,
                "operating_models": 0,
                "workloads": 0,
                "capacities": 0,
                "energy_consumption": 0,
                "coordinates": 0,
                "geometry": 0,
            },
            "published": False,
            "accepted_final_already_present": complete_before,
        }
    finally:
        if source_stage.exists() or source_stage.is_symlink():
            if not _has_identity(
                source_stage, prepared.source_identities["."][:2], directory=True
            ):
                raise CtrlSPublicationError(
                    "refusing identity-mismatched source-stage cleanup"
                )
            _discard_owned_tree(source_stage, prepared.source_identities)
        if artifact_stage.exists() or artifact_stage.is_symlink():
            if not _has_identity(
                artifact_stage,
                prepared.artifact_identities["."][:2],
                directory=True,
            ):
                raise CtrlSPublicationError(
                    "refusing identity-mismatched artifact-stage cleanup"
                )
            _discard_owned_tree(artifact_stage, prepared.artifact_identities)
    complete_after, present_after = _final_presence()
    if (complete_after, present_after) != (complete_before, present_before):
        raise CtrlSPublicationError("preflight changed final-path presence")
    if complete_after:
        _existing_identical(None)
    _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    _validate_reviewed_inputs()
    result["source_stage_discarded"] = not source_stage.exists()
    result["artifact_stage_discarded"] = not artifact_stage.exists()
    result["reviewed_source_stage_retained"] = REVIEWED_SOURCE_STAGE.exists()
    result["reviewed_artifact_stage_retained"] = REVIEWED_ARTIFACT_STAGE.exists()
    result["raw_capture_retained"] = _raw_capture().exists()
    result["final_artifact_exists"] = ARTIFACT.exists()
    result["final_source_exists"] = all(
        path.exists() for path in _final_source_paths().values()
    )
    return result


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(source: Path, destination: Path) -> None:
    try:
        promote_noreplace(source, destination)
    except SystemExit as error:
        raise CtrlSPublicationError(str(error)) from error


def _publish_prepared(prepared: PreparedPublication) -> dict[str, Any]:
    target = _instant(prepared.recorded_at)
    _assert_prepared_exact(prepared, frozen=False)
    _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    _assert_final_absent()
    _wait_until(target)
    _assert_final_absent()
    _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    _validate_reviewed_inputs()
    _assert_prepared_exact(prepared, frozen=False)
    _freeze_stages(
        prepared.source_stage,
        prepared.artifact_stage,
        prepared.source_identities,
        prepared.artifact_identities,
    )
    _assert_prepared_exact(prepared, frozen=True)
    _assert_recursive_ctimes_at_or_after(prepared.source_stage, target)
    _assert_recursive_ctimes_at_or_after(prepared.artifact_stage, target)
    _assert_final_absent()

    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            identity = _identity(staged, directory=False)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=False):
                raise CtrlSPublicationError(f"promoted source identity differs: {name}")
            promoted.append((final, staged, identity, False))
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise CtrlSPublicationError("promoted artifact identity differs")
        _assert_tree_identities(ARTIFACT, prepared.artifact_identities)
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
        manifest = _validate_artifact(
            ARTIFACT,
            _final_source_paths(),
            frozen=True,
            require_live=True,
            require_final_chronology=True,
            run_offline_import=False,
            documents=prepared.documents,
        )
        _assert_reviewed_input_identities(prepared.reviewed_input_identities)
    except BaseException as error:
        if _has_identity(
            prepared.source_stage,
            prepared.source_identities["."][:2],
            directory=True,
        ):
            prepared.source_stage.chmod(0o700)
            _fsync_directory(prepared.source_stage)
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise CtrlSPublicationError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise CtrlSPublicationError(
                        f"rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(f"CtrlS rollback failed for {final}: {rollback_error}")
        raise
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
    except FileExistsError as error:
        raise CtrlSPublicationError("active CtrlS publication lock exists") from error
    identity: tuple[int, int] | None = None
    try:
        identity = _fstat_identity_with_retry(
            descriptor,
            expected_kind="file",
            expected_mode=0o600,
            label="CtrlS publication lock",
        )[:2]
        payload = f"pid={os.getpid()}\n".encode("ascii")
        if os.write(descriptor, payload) != len(payload):
            raise CtrlSPublicationError("short CtrlS publication-lock write")
        os.fsync(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            if identity is not None:
                try:
                    current = PUBLICATION_LOCK.stat(follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if (
                        not stat.S_ISREG(current.st_mode)
                        or (current.st_dev, current.st_ino) != identity
                    ):
                        raise CtrlSPublicationError(
                            "refusing substituted CtrlS publication-lock cleanup"
                        )
                    PUBLICATION_LOCK.unlink()


def _existing_identical(recorded_at: str | None) -> dict[str, Any]:
    _assert_no_later_source_collisions()
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise CtrlSPublicationError("existing recorded_at is missing")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise CtrlSPublicationError("existing recorded_at differs")
    inputs = _validate_reviewed_inputs()
    documents = expected_source_documents()
    _validate_artifact(
        ARTIFACT,
        _final_source_paths(),
        frozen=True,
        require_live=True,
        require_final_chronology=True,
        run_offline_import=False,
        documents=documents,
    )
    _assert_reviewed_input_identities(inputs)
    return {
        "status": "existing-identical",
        "artifact": str(ARTIFACT),
        "recorded_at": existing_recorded_at,
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 2,
        "rejected_review_only_candidates": 10,
        "raw_capture_retained": _raw_capture().exists(),
    }


def build(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish only with explicit authorization; otherwise fail closed."""

    if not publication_authorized:
        raise CtrlSPublicationError(
            "CtrlS publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical(recorded_at)
    if present:
        raise CtrlSPublicationError(f"partial final-path collision: {present!r}")

    target = (
        _instant(recorded_at)
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise CtrlSPublicationError("recorded_at must be future before publication")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _publication_lock():
        prepared = _prepare(timestamp)
        try:
            manifest = _publish_prepared(prepared)
        except BaseException:
            if _has_identity(
                prepared.source_stage,
                prepared.source_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(prepared.source_stage, prepared.source_identities)
            if _has_identity(
                prepared.artifact_stage,
                prepared.artifact_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(
                    prepared.artifact_stage, prepared.artifact_identities
                )
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise CtrlSPublicationError("source stage not empty after publication")
            identity = prepared.source_identities["."][:2]
            if not _has_identity(prepared.source_stage, identity, directory=True):
                raise CtrlSPublicationError("source stage identity differs")
            prepared.source_stage.rmdir()
    return {
        "status": "published",
        "artifact": str(ARTIFACT),
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "published": True,
        "accepted_source_records": 2,
        "rejected_review_only_candidates": 10,
        "raw_capture_retained": _raw_capture().exists(),
    }


def main() -> int:
    print(json.dumps(preflight(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
