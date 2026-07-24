"""Publish a bounded regional-gap official-build assessment.

The publication is independent of open-seed and downstream products. It stages
every source and artifact byte before its declared recording instant, then uses
no-replace promotion with identity-checked rollback.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
from datetime import UTC, datetime
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-regional-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-regional-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-regional-gap-20260721.pz8R6c")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-regional-gap-20260721.pz8R6c")
BROWSER_PROFILE_ORIGIN = Path(
    "/private/tmp/dc-regional-gap-chrome-20260721.pz8R6c"
)
BROWSER_PROFILE_TRASH = Path(
    "/Users/kian/.Trash/dc-regional-gap-chrome-20260721.pz8R6c"
)
CAPTURE_TREE_SHA256 = (
    "cfa314d04f9ee9ea2872de7730caaffde8cf5b217b0706cd16ffb923512df15d"
)
CAPTURE_FILE_COUNT = 67

V73_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
V73_MANIFEST = V73_RELEASE / "manifest.json"
V73_ENTITIES = V73_RELEASE / "entities.csv"
V73_PINS = {
    V73_DEFINITION: (
        88_004,
        "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
    ),
    V73_MANIFEST: (
        12_814,
        "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
    ),
    V73_ENTITIES: (
        887_459,
        "8c50475f1a58a7f7623a4eef2706be3f63bca0175a5fe4fffecdd548442944e7",
    ),
}
V73_TREE_SHA256 = (
    "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"
)
V73_INPUT_COUNT = 397

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-niger-national-dc-pk5-current-build.json",
    "curated-official-2026-07-21-somalia-national-dc-site-unresolved-current-build.json",
    "curated-official-2026-07-21-congo-national-dc-bacongo-current-build.json",
    "curated-official-2026-07-21-telia-vilnius-current-build.json",
    "curated-official-2026-07-21-atnorth-ice02-phase-2-current-build.json",
    "curated-official-2026-07-21-borealis-blonduos-expansion-current-build.json",
)

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

class OfficialTrancheError(RuntimeError):
    """Raised when evidence or publication invariants fail closed."""


def _canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise OfficialTrancheError(f"timestamp lacks timezone: {value}")
    return result.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise OfficialTrancheError(f"pinned ordinary file is absent: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise OfficialTrancheError(f"pinned file differs: {path}: {actual!r}")


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    if not correct_type:
        raise OfficialTrancheError(f"staged path type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path,
    identity: tuple[int, int],
    *,
    directory: bool,
) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    correct_type = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    return correct_type and (metadata.st_dev, metadata.st_ino) == identity


def _promote_noreplace(source: Path, destination: Path) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    source_raw = os.fsencode(source)
    destination_raw = os.fsencode(destination)
    if sys.platform == "darwin":
        function = getattr(library, "renamex_np", None)
        if function is None:  # pragma: no cover
            raise OfficialTrancheError("atomic no-replace publication is unavailable")
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(source_raw, destination_raw, 0x00000004)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        if function is None:  # pragma: no cover
            raise OfficialTrancheError("atomic no-replace publication is unavailable")
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, source_raw, -100, destination_raw, 0x00000001)
    else:  # pragma: no cover
        raise OfficialTrancheError("atomic no-replace publication is unavailable")
    if result == 0:
        _fsync_directory(destination.parent)
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise OfficialTrancheError(
            f"late output collision; refusing replacement: {destination}"
        )
    raise OfficialTrancheError(
        f"atomic no-replace publication failed: {os.strerror(error_number)}"
    )


def _discard_owned_directory(
    path: Path,
    identity: tuple[int, int],
    member_identities: Mapping[str, tuple[int, int]],
) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(metadata.st_mode) or (
        metadata.st_dev,
        metadata.st_ino,
    ) != identity:
        raise OfficialTrancheError(f"refusing substituted staging directory: {path}")
    entries = list(path.iterdir())
    actual = {
        entry.name: _identity(entry, directory=False)
        for entry in entries
        if not entry.is_symlink() and entry.is_file()
    }
    expected_actual = {
        name: member_identities[name]
        for name in actual
        if name in member_identities
    }
    if len(actual) != len(entries) or actual != expected_actual:
        raise OfficialTrancheError(f"refusing contaminated staging cleanup: {path}")
    path.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    path.rmdir()


def _assert_stage_precedes_target(
    paths: Sequence[Path],
    target: datetime,
) -> None:
    target_epoch = target.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise OfficialTrancheError("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target_epoch + 0.000_001:
            raise OfficialTrancheError(f"private stage post-dates recorded_at: {path}")


def _assert_final_ctimes(paths: Sequence[Path], target: datetime) -> None:
    target_epoch = target.timestamp()
    for path in paths:
        if path.is_symlink() or not path.exists():
            raise OfficialTrancheError(f"published root is absent: {path}")
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target_epoch:
            raise OfficialTrancheError(
                f"published root rename predates recorded_at: {path}"
            )


def _require_finals_absent(finals: Sequence[Path], label: str) -> None:
    occupied = [path for path in finals if path.exists() or path.is_symlink()]
    if occupied:
        raise OfficialTrancheError(f"{label} final path occupied: {occupied!r}")


def _wait_until(target: float) -> None:
    while True:
        remaining = target - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _rollback_promotions(
    promoted: Sequence[tuple[Path, Path, tuple[int, int], bool]],
) -> None:
    for stage, final, identity, directory in reversed(promoted):
        if not _has_identity(final, identity, directory=directory):
            raise OfficialTrancheError(
                f"refusing rollback of substituted published path: {final}"
            )
        if stage.exists() or stage.is_symlink():
            raise OfficialTrancheError(
                f"refusing rollback over occupied private stage: {stage}"
            )
        _promote_noreplace(final, stage)
        if not _has_identity(stage, identity, directory=directory):
            raise OfficialTrancheError(
                f"rollback failed to restore private inode: {stage}"
            )


CAPTURE_BODIES: dict[str, dict[str, Any]] = {
    "niger_anp": {
        "filename": "niger_anp.body",
        "url": (
            "https://anp.ne/les-ministres-de-la-communication-du-niger-et-du-"
            "tchad-sur-le-chantier-de-construction-dun-data-center-dune-valeur-"
            "de-10-milliards-de-cfa-a-niamey/"
        ),
        "retrieved_at": "2026-07-21T15:53:30Z",
        "bytes": 556_887,
        "sha256": "5c81db27b891f9ebbf272a8ba50ae0c1665fb74c3cc380390f1f0863552f83c8",
        "content_type": "text/html",
        "wire_download_bytes": 62_512,
    },
    "niger_gov": {
        "filename": "niger_gov.body",
        "url": (
            "https://www.gouv.ne/index.php/actualite-des-ministeres/1200-"
            "communication-et-numerique-le-niger-ambitionne-de-devenir-un-hub-"
            "regional-des-telecommunications"
        ),
        "retrieved_at": "2026-07-21T15:53:35Z",
        "bytes": 89_460,
        "sha256": "96810113fba7a58ddffe4d8f1ce6fec016c7a58478ebd9db59594eb992e743bd",
        "content_type": "text/html; charset=utf-8",
        "wire_download_bytes": 13_786,
    },
    "somalia_moct": {
        "filename": "somalia_moct.body",
        "url": (
            "https://moct.gov.so/en/h-e-minister-mohamed-adam-moalim-ali-"
            "inspects-progress-of-the-national-data-center-construction/"
        ),
        "retrieved_at": "2026-07-21T15:53:37Z",
        "bytes": 177_379,
        "sha256": "c0b31ac976b480993b7f3e4be76546c26e45b37aa301a64c9037e8c48928fa05",
        "content_type": "text/html; charset=UTF-8",
        "wire_download_bytes": 28_779,
    },
    "somalia_moct_bid": {
        "filename": "somalia_moct_bid.body",
        "url": (
            "https://moct.gov.so/en/wp-content/uploads/2023/11/"
            "Bidding-Document-fo-MoCT-Data-Centre-FINAL-after-NOL-.pdf"
        ),
        "retrieved_at": "2026-07-21T15:55:00Z",
        "bytes": 2_709_190,
        "sha256": "f222d56834ff723a02f6137f0a423c3173be5cf37b9927baa7b34fb96b683133",
        "content_type": "application/pdf",
        "wire_download_bytes": 2_709_190,
    },
    "congo_bacongo": {
        "filename": "congo_afdb_bacongo.browser.body",
        "url": (
            "https://www.afdb.org/en/news-and-events/congo-new-data-centre-"
            "funded-african-development-bank-will-cement-national-and-"
            "subregional-digital-sovereignty-70847"
        ),
        "retrieved_at": "2026-07-21T15:56:49Z",
        "bytes": 106_330,
        "sha256": "32511c932279ad87a347061f485845e14560772477527135b14b0c9cd43bd09b",
        "content_type": "text/html; charset=utf-8",
        "capture_method": "curl_cffi_chrome136_browser_compatible_tls",
    },
    "congo_progress": {
        "filename": "congo_afdb_progress.browser.body",
        "url": (
            "https://www.afdb.org/en/news-and-events/press-releases/2026-"
            "annual-meetings-high-level-african-development-bank-delegation-"
            "consultation-mission-brazzaville-84918"
        ),
        "retrieved_at": "2026-07-21T15:53:19Z",
        "bytes": 106_820,
        "sha256": "d2ed5d6f9487fbc1a805f534e5b5567fdee5bc4873bae77fa3a6381c3e1549a2",
        "content_type": "text/html; charset=utf-8",
        "capture_method": "curl_cffi_chrome136_browser_compatible_tls",
    },
    "congo_visit": {
        "filename": "congo_afdb_visit.browser.body",
        "url": (
            "https://www.afdb.org/en/news-and-events/press-releases/african-"
            "development-bank-group-and-republic-congo-strengthen-partnership-"
            "economic-diversification-and-regional-integration-88261"
        ),
        "retrieved_at": "2026-07-21T15:55:39Z",
        "bytes": 106_767,
        "sha256": "e9f385831398d1694ba8034a4cd75b766cb4d76eb63fbbf58157a0508ad0ac88",
        "content_type": "text/html; charset=utf-8",
        "capture_method": "curl_cffi_chrome136_browser_compatible_tls",
    },
    "telia_q1": {
        "filename": "telia_q1.body",
        "url": (
            "https://www.teliacompany.com/assets/u5c1v3pt22v8/"
            "3ya78gxxNy9J2hKt0SQERx/"
            "beebf2a293ddaa7ba7b288e2809168e9/Telia_Company_Q1_2026_Eng.pdf"
        ),
        "retrieved_at": "2026-07-21T15:55:08Z",
        "bytes": 1_232_420,
        "sha256": "b0c2e8c934efcb3bf35a9f5598da267456a495c0a657ec349267a5ab6a923356",
        "content_type": "application/pdf",
        "wire_download_bytes": 1_168_755,
    },
    "atnorth_mannverk": {
        "filename": "atnorth_mannverk.body",
        "url": "https://www.mannverk.is/allprojects/atnorth2",
        "retrieved_at": "2026-07-21T15:52:30Z",
        "bytes": 238_652,
        "sha256": "2dbd1ea0ce742bb65780d0a496e8fffb7f32f9a5e92cfcea8e58d1863c0e6fe0",
        "content_type": "text/html;charset=utf-8",
        "wire_download_bytes": 36_031,
    },
    "borealis_hunabyggd": {
        "filename": "borealis_hunabyggd.body",
        "url": (
            "https://www.hunabyggd.is/is/stjornsysla/stjornskipulag/"
            "fundargerdir/skipulags-og-samgongunefnd-hunabyggdar/915"
        ),
        "retrieved_at": "2026-07-21T15:52:30Z",
        "bytes": 58_955,
        "sha256": "5c7fdc3598cdb745a6d3a6d6a9e5bf79d57912145f9ac06e1160b183e50ee6ec",
        "content_type": "text/html; charset=UTF-8",
        "wire_download_bytes": 13_734,
    },
    "borealis_landsvirkjun": {
        "filename": "borealis_landsvirkjun.body",
        "url": (
            "https://www.landsvirkjun.com/news/borealis-and-landsvirkjun-sign-a-"
            "12-mw-power-purchasing-agreement"
        ),
        "retrieved_at": "2026-07-21T15:52:31Z",
        "bytes": 109_768,
        "sha256": "698796d45b3d72a23c93127e5203bd956702f9a76d714b26e7548db583cc26af",
        "content_type": "text/html; charset=utf-8",
        "wire_download_bytes": 19_958,
    },
    "orel_tia_registry": {
        "filename": "orel_tia_registry.body",
        "url": "https://tiaonline.org/942-datacenter/orel-it-campus-data-center-nawinna/",
        "retrieved_at": "2026-07-21T15:53:37Z",
        "bytes": 113_400,
        "sha256": "a78ea922396fc041eaa44c0aaddc5e4104616f490dafaeef10b85d38832dd82c",
        "content_type": "text/html; charset=UTF-8",
        "wire_download_bytes": 25_496,
    },
    "orel_tia_certificate": {
        "filename": "orel_tia_certificate.body",
        "url": (
            "https://tiaonline.org/wp-content/uploads/2025/06/"
            "SriLanka_OREL-Nawinna_DCDV-GDCE_TIA942LK250610001-Signed.pdf"
        ),
        "retrieved_at": "2026-07-21T15:53:35Z",
        "bytes": 148_720,
        "sha256": "62f07c270cf1e754e4c4da957942245de540b511b66f87cbf26e603150a70621",
        "content_type": "application/pdf",
        "wire_download_bytes": 148_720,
    },
}


def _evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
    title: str,
    publisher: str,
    source_family: str,
    published_at: str | None,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURE_BODIES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "official response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": capture.get(
            "capture_method", "curl_location_compressed"
        ),
        "http_status": 200,
        "content_type": capture["content_type"],
        "wire_download_bytes": capture.get("wire_download_bytes"),
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "the response body and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "or analyst geolocation contributes to this record."
        ),
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": capture["url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": capture["retrieved_at"],
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": capture["sha256"],
        "metadata": common,
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    country: str,
    address: str,
    roles: Mapping[str, list[str]],
    evidence_key: str,
    as_of_date: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": dict(roles),
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _lifecycle(
    evidence_key: str,
    as_of_date: str,
    *,
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": "under_construction",
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": confidence,
    }


def _niger_source() -> dict[str, Any]:
    anp_key = "niger-national-dc-pk5-june-2025-build-captured-2026-07-21"
    government_key = (
        "niger-national-dc-equipment-installation-june-2026-captured-2026-07-21"
    )
    evidence = [
        _evidence(
            "niger_anp",
            key=anp_key,
            kind="government_record",
            title=(
                "Les ministres de la communication du Niger et du Tchad sur le "
                "chantier de construction d’un Data Center à Niamey"
            ),
            publisher="Agence Nigérienne de Presse",
            source_family="niger_official_data_center_updates",
            published_at="2025-06-19",
            excerpt=(
                "ANP reports a ministerial visit to the level-3 data-center "
                "construction site at PK5 in Niamey and reports the building at "
                "approximately 85 percent."
            ),
            metadata={
                "location_as_reported": "PK5, Niamey, Niger",
                "building_completion_percentage_as_reported": 85,
                "level_as_reported": 3,
                "project_cost_cfa_as_reported": 10_000_000_000,
                "physical_status_scope": (
                    "The dated construction-site visit supports only generic "
                    "under_construction as of 2025-06-19. The reported percentage "
                    "does not establish commissioning, completion, or operation."
                ),
                "classification_guardrail": (
                    "Level 3 is retained as reported resilience context, not an IT, "
                    "facility, grid, generation, consumption, or energy capacity."
                ),
                "cost_guardrail": (
                    "The CFA 10 billion project value is cost context and creates no "
                    "capacity or energy observation."
                ),
            },
        ),
        _evidence(
            "niger_gov",
            key=government_key,
            kind="government_record",
            title=(
                "Communication et numérique : le Niger ambitionne de devenir un "
                "hub régional des télécommunications"
            ),
            publisher="Gouvernement de la République du Niger",
            source_family="niger_official_data_center_updates",
            published_at="2026-06-18",
            excerpt=(
                "The Niger government says civil-engineering work for the National "
                "Data Center was finalized and technical equipment needed for "
                "operationalization was being installed progressively."
            ),
            metadata={
                "source_dateline": "2026-06-17",
                "status_wording_as_reported": (
                    "Civil-engineering works finalized; installation of technical "
                    "equipment necessary for operationalization progressing."
                ),
                "physical_status_scope": (
                    "Ongoing equipment installation supports generic "
                    "under_construction as of publication. Civil-works completion is "
                    "not whole-project completion, commissioning, energization, or "
                    "operation."
                ),
                "capacity_guardrail": (
                    "The separate 100-to-800 gigabit backbone statement concerns "
                    "telecommunications throughput and creates no data-center power, "
                    "IT-capacity, or consumption row."
                ),
            },
        ),
    ]
    campus_key = "curated:niger-national-data-center-pk5-niamey"
    project_key = f"{campus_key}:current-build"
    address = "PK5, Niamey, Niger"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Niger National Data Center PK5",
            country="Niger",
            address=address,
            roles={},
            evidence_key=government_key,
            as_of_date="2026-06-18",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Niger National Data Center PK5 Current Build",
            country="Niger",
            address=address,
            roles={},
            evidence_key=government_key,
            as_of_date="2026-06-18",
            confidence=0.99,
        ),
        "lifecycle": [
            _lifecycle(anp_key, "2025-06-19"),
            _lifecycle(government_key, "2026-06-18"),
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _somalia_source() -> dict[str, Any]:
    status_key = (
        "somalia-national-dc-mogadishu-progress-may-2025-captured-2026-07-21"
    )
    bid_key = "somalia-moct-primary-dr-site-bid-captured-2026-07-21"
    publisher = "Ministry of Communications and Technology, Somalia"
    evidence = [
        _evidence(
            "somalia_moct",
            key=status_key,
            kind="government_record",
            title=(
                "Minister Mohamed Adam Moalim Ali inspects progress of the National "
                "Data Center construction"
            ),
            publisher=publisher,
            source_family="somalia_moct_data_center_records",
            published_at="2025-05-06",
            excerpt=(
                "MoCT reports a field visit in Mogadishu to inspect ongoing "
                "construction of the National Data Center and says the project was "
                "nearing completion."
            ),
            metadata={
                "location_as_reported": "Mogadishu, Somalia",
                "site_resolution": "city_only",
                "physical_status_scope": (
                    "The dated field visit supports one site-unresolved Mogadishu "
                    "under_construction observation. Nearing-completion wording does "
                    "not establish completion, commissioning, energization, or "
                    "operation."
                ),
                "site_allocation_guardrail": (
                    "The update does not identify whether the observed work is the "
                    "procurement-defined primary Airport site, the DR site at MoCT, "
                    "both, or another scope. No primary/secondary allocation is made."
                ),
            },
        ),
        _evidence(
            "somalia_moct_bid",
            key=bid_key,
            kind="government_record",
            title=(
                "Bidding document: Supply, Installation, Commissioning and Support "
                "for Data Centre for Ministry of Communications and Technology"
            ),
            publisher=publisher,
            source_family="somalia_moct_data_center_records",
            published_at=None,
            excerpt=(
                "The MoCT procurement identifies a proposed primary site at "
                "Mogadishu Airport and a DR site at the Ministry of Communications "
                "and Technology."
            ),
            metadata={
                "upload_path_period": "2023-11",
                "named_place_of_final_destination": {
                    "primary_site": "Mogadishu Airport",
                    "dr_site": "Ministry of Communications and Technology",
                },
                "procurement_scope": (
                    "The document seeks turnkey primary and secondary modular data "
                    "centers and interconnection between them."
                ),
                "lifecycle_guardrail": (
                    "Tender requirements establish planned site identities and "
                    "design scope only. They do not establish that either site was "
                    "built, active in May 2025, complete, commissioned, or operating."
                ),
                "normalization_guardrail": (
                    "The bid-defined primary and DR sites remain candidate-level "
                    "review-only identities. They do not become separate normalized "
                    "entities or inherit the city-level lifecycle observation."
                ),
            },
        ),
    ]
    campus_key = "curated:somalia-national-data-center-mogadishu-site-unresolved"
    project_key = f"{campus_key}:current-build-site-unresolved"
    address = "Mogadishu, Somalia"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Somalia National Data Center (site unresolved)",
            country="Somalia",
            address=address,
            roles={},
            evidence_key=status_key,
            as_of_date="2025-05-06",
            confidence=0.96,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Somalia National Data Center Current Build (site unresolved)",
            country="Somalia",
            address=address,
            roles={},
            evidence_key=status_key,
            as_of_date="2025-05-06",
            confidence=0.96,
        ),
        "lifecycle": [_lifecycle(status_key, "2025-05-06", confidence=0.97)],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _congo_source() -> dict[str, Any]:
    bacongo_key = (
        "republic-congo-national-dc-bacongo-may-2024-captured-2026-07-21"
    )
    progress_key = (
        "republic-congo-national-dc-june-2025-progress-captured-2026-07-21"
    )
    visit_key = (
        "republic-congo-national-dc-october-2025-visit-captured-2026-07-21"
    )
    publisher = "African Development Bank Group"
    evidence = [
        _evidence(
            "congo_bacongo",
            key=bacongo_key,
            kind="government_record",
            title=(
                "Congo: new data centre funded by the African Development Bank will "
                "cement national and subregional digital sovereignty"
            ),
            publisher=publisher,
            source_family="afdb_republic_congo_national_data_center_updates",
            published_at="2024-05-17",
            excerpt=(
                "The African Development Bank places the National Data Center in the "
                "Bacongo district of Brazzaville and reports physical work, with "
                "civil engineering around 60 percent in early May 2024."
            ),
            metadata={
                "location_as_reported": (
                    "Bacongo district, Brazzaville, Republic of the Congo"
                ),
                "civil_engineering_percentage_as_reported": 60,
                "physical_status_scope": (
                    "The dated physical-work report supports generic "
                    "under_construction as of 2024-05-17. The percentage is not "
                    "converted to a finer stage and establishes neither whole-project "
                    "completion nor operation."
                ),
            },
        ),
        _evidence(
            "congo_progress",
            key=progress_key,
            kind="government_record",
            title=(
                "High-level African Development Bank delegation on consultation "
                "mission to Brazzaville"
            ),
            publisher=publisher,
            source_family="afdb_republic_congo_national_data_center_updates",
            published_at="2025-06-26",
            excerpt=(
                "The Bank reports a National Data Center construction-site visit and "
                "says the project was 90 percent complete while server rooms and "
                "civil engineering work remained."
            ),
            metadata={
                "project_completion_percentage_as_reported": 90,
                "installed_items_as_reported": [
                    "generators",
                    "transformers",
                    "regulators",
                ],
                "remaining_work_as_reported": [
                    "server rooms",
                    "civil engineering",
                ],
                "physical_status_scope": (
                    "Remaining server-room and civil work supports generic "
                    "under_construction as of 2025-06-26. Ninety-percent wording and "
                    "installed equipment do not establish completion, commissioning, "
                    "energization, acceptance, or operation."
                ),
                "slug_date_guardrail": (
                    "The URL slug references 2026 Annual Meetings, but the captured "
                    "publisher page is dated 2025-06-26; the page date governs."
                ),
            },
        ),
        _evidence(
            "congo_visit",
            key=visit_key,
            kind="government_record",
            title=(
                "African Development Bank Group and Republic of Congo strengthen "
                "partnership for economic diversification and regional integration"
            ),
            publisher=publisher,
            source_family="afdb_republic_congo_national_data_center_updates",
            published_at="2025-11-03",
            excerpt=(
                "The Bank says its delegation visited the National Data Center site "
                "during its 26–28 October 2025 mission."
            ),
            metadata={
                "visit_period": "2025-10-26/2025-10-28",
                "lifecycle_guardrail": (
                    "A site visit without explicit work or status wording supplies "
                    "identity continuity only. It creates no new lifecycle row and "
                    "does not make the June observation timeless or current."
                ),
            },
        ),
    ]
    campus_key = "curated:republic-congo-national-data-center-bacongo"
    project_key = f"{campus_key}:current-build"
    address = "Bacongo district, Brazzaville, Republic of the Congo"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Republic of the Congo National Data Center Bacongo",
            country="Republic of the Congo",
            address=address,
            roles={},
            evidence_key=bacongo_key,
            as_of_date="2024-05-17",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Republic of the Congo National Data Center Current Build",
            country="Republic of the Congo",
            address=address,
            roles={},
            evidence_key=progress_key,
            as_of_date="2025-06-26",
            confidence=0.99,
        ),
        "lifecycle": [
            _lifecycle(bacongo_key, "2024-05-17"),
            _lifecycle(progress_key, "2025-06-26"),
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _telia_source() -> dict[str, Any]:
    evidence_key = "lithuania-telia-vilnius-q1-2026-build-captured-2026-07-21"
    publisher = "Telia Company AB"
    evidence = [
        _evidence(
            "telia_q1",
            key=evidence_key,
            kind="company_disclosure",
            title="Telia Company Q1 2026 Interim Report",
            publisher=publisher,
            source_family="telia_company_interim_reports",
            published_at=None,
            excerpt=(
                "Telia's January–March 2026 interim report says construction started "
                "on a new data center in Vilnius during the quarter."
            ),
            metadata={
                "reporting_period": "2026-01-01/2026-03-31",
                "location_as_reported": "Vilnius, Lithuania",
                "status_wording_as_reported": (
                    "Construction started on a new data center in Vilnius."
                ),
                "physical_status_scope": (
                    "The issuer's quarter statement supports generic "
                    "under_construction at quarter-end, 2026-03-31. It does not "
                    "establish a finer stage, completion, commissioning, or operation."
                ),
                "location_guardrail": (
                    "The directly captured report supports Vilnius only. A Telia "
                    "Lithuania page that may provide Raisteniškės or street-level "
                    "detail returned Cloudflare challenges, so no finer locality or "
                    "address is normalized."
                ),
                "capacity_guardrail": (
                    "Media claims of 6 MW or 8 MW and challenge-blocked Telia page "
                    "claims of 3-to-10 MW and PUE below 1.2 are not present in the "
                    "governed selected body. None is normalized."
                ),
            },
        )
    ]
    campus_key = "curated:telia-vilnius-data-center"
    project_key = f"{campus_key}:new-data-center-current-build"
    address = "Vilnius, Lithuania"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Telia Vilnius Data Center",
            country="Lithuania",
            address=address,
            roles={},
            evidence_key=evidence_key,
            as_of_date="2026-03-31",
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Telia Vilnius New Data Center Current Build",
            country="Lithuania",
            address=address,
            roles={},
            evidence_key=evidence_key,
            as_of_date="2026-03-31",
            confidence=0.98,
        ),
        "lifecycle": [_lifecycle(evidence_key, "2026-03-31", confidence=0.99)],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _atnorth_source() -> dict[str, Any]:
    evidence_key = "iceland-atnorth-ice02-phase-2-ongoing-captured-2026-07-21"
    evidence = [
        _evidence(
            "atnorth_mannverk",
            key=evidence_key,
            kind="company_disclosure",
            title="atNorth ICE02 - Data Center",
            publisher="Mannverk",
            source_family="mannverk_project_pages",
            published_at=None,
            excerpt=(
                "Mannverk says it is currently expanding atNorth ICE02 in "
                "Reykjanesbær and that work continued into a still-ongoing second "
                "phase after phase one was delivered in mid-2025."
            ),
            metadata={
                "location_as_reported": "Reykjanesbær, Iceland",
                "phase_one_delivery_period_as_reported": "mid-2025",
                "phase_two_status_as_reported": "still ongoing",
                "status_date_basis": "retrieval_date_of_current_contractor_page",
                "role_scope": (
                    "The page explicitly describes Mannverk's design integration, "
                    "construction management, commissioning oversight, and handover "
                    "work for atNorth."
                ),
                "physical_status_scope": (
                    "The current contractor page supports phase-two "
                    "under_construction as of retrieval on 2026-07-21. It does not "
                    "establish a finer stage, completion, or operation."
                ),
                "capacity_guardrail": (
                    "Separately surfaced 83 MW campus and plus-35 MW expansion values "
                    "are not allocated by this selected body to phase two. They create "
                    "no phase capacity, load, or consumption row."
                ),
            },
        )
    ]
    campus_key = "curated:atnorth-ice02-reykjanesbaer-campus"
    project_key = f"{campus_key}:phase-2-expansion"
    roles = {
        "operator": ["atNorth"],
        "contractor": ["Mannverk"],
    }
    address = "Reykjanesbær, Iceland"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="atNorth ICE02 Reykjanesbær Campus",
            country="Iceland",
            address=address,
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-07-21",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="atNorth ICE02 Phase 2 Expansion",
            country="Iceland",
            address=address,
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-07-21",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle(evidence_key, "2026-07-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _borealis_source() -> dict[str, Any]:
    permit_key = (
        "iceland-borealis-blonduos-municipal-permit-june-2026-captured-2026-07-21"
    )
    works_key = (
        "iceland-borealis-blonduos-expansion-june-2026-captured-2026-07-21"
    )
    evidence = [
        _evidence(
            "borealis_hunabyggd",
            key=permit_key,
            kind="government_record",
            title="Skipulags- og samgöngunefnd Húnabyggðar meeting record 915",
            publisher="Húnabyggð",
            source_family="hunabyggd_planning_committee_records",
            published_at="2026-06-16",
            excerpt=(
                "The municipal record considers a temporary-road permit connected to "
                "Borealis' Blönduós expansion and movement of about 40,000 cubic "
                "metres of material."
            ),
            metadata={
                "material_volume_cubic_metres_as_reported": 40_000,
                "lifecycle_guardrail": (
                    "A permit application and committee recommendation do not prove "
                    "that the road, excavation, earth movement, or data-center works "
                    "occurred. This source supplies identity and planning context only."
                ),
                "capacity_guardrail": (
                    "Material volume is a civil quantity, not power, IT capacity, "
                    "generation, energy, or consumption."
                ),
            },
        ),
        _evidence(
            "borealis_landsvirkjun",
            key=works_key,
            kind="utility_record",
            title="Borealis and Landsvirkjun sign a 12 MW power purchasing agreement",
            publisher="Landsvirkjun",
            source_family="landsvirkjun_customer_updates",
            published_at="2026-06-23",
            excerpt=(
                "Landsvirkjun describes expansion of Borealis' Blönduós data-center "
                "campus and says the facility is being equipped for liquid-cooled "
                "NVIDIA infrastructure."
            ),
            metadata={
                "additional_firm_power_mw_as_reported": 12,
                "iceland_data_center_power_consumption_mw_as_reported": 70,
                "physical_status_scope": (
                    "The facility-being-equipped wording supports generic expansion "
                    "under_construction as of 2026-06-23. It does not establish a "
                    "finer stage, completion, commissioning, or operation."
                ),
                "capacity_guardrail": (
                    "The additional 12 MW is contracted firm power supply, not typed "
                    "facility load, critical IT, current demand, or consumption. The "
                    "70 MW value is an Iceland-wide data-center aggregate. Neither "
                    "creates a project capacity or energy row."
                ),
                "workload_guardrail": (
                    "Being equipped to support liquid-cooled NVIDIA infrastructure "
                    "does not establish an operating AI workload. No workload row is "
                    "emitted."
                ),
            },
        ),
    ]
    campus_key = "curated:borealis-blonduos-data-center-campus"
    project_key = f"{campus_key}:expansion-current-build"
    roles = {
        "operator": ["Borealis Data Center"],
        "utility": ["Landsvirkjun"],
    }
    address = "Blönduós, Húnabyggð, Iceland"
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Borealis Blönduós Data Center Campus",
            country="Iceland",
            address=address,
            roles=roles,
            evidence_key=works_key,
            as_of_date="2026-06-23",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="Borealis Blönduós Expansion Current Build",
            country="Iceland",
            address=address,
            roles=roles,
            evidence_key=works_key,
            as_of_date="2026-06-23",
            confidence=0.99,
        ),
        "lifecycle": [_lifecycle(works_key, "2026-06-23")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the six exact schema-1.1 source documents."""

    builders = (
        _niger_source,
        _somalia_source,
        _congo_source,
        _telia_source,
        _atnorth_source,
        _borealis_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


SOURCE_DISPOSITIONS = {
    name: "seed_eligible_fresh_official_physical_update"
    for name in SOURCE_FILENAMES
}


TECHNICAL_CAPTURES = {
    "somalia_world_bank_october_2025_missing": {
        "requested_url": (
            "https://documents1.worldbank.org/curated/en/099120225134533544/"
            "pdf/P176181-5a5a2225-0496-4024-9351-c8e649052f61.pdf"
        ),
        "http_status": 404,
        "body_file": "somalia_wb.body",
        "body_bytes": 100_826,
        "body_sha256": (
            "1c48e2bb0b650b57f50006624c8d3475a4a40c2fa9fcd6b21fb1f2d0c4b65bc1"
        ),
        "disposition": "failed_body_retained_private_not_used",
    },
    "somalia_world_bank_guid_lookup": {
        "requested_url": (
            "https://search.worldbank.org/api/v3/wds?format=json&fl=*&"
            "guid=099120225134533544&apilang=en"
        ),
        "http_status": 200,
        "body_file": "somalia_wb_2025_api.body",
        "body_bytes": 63,
        "body_sha256": (
            "ebfd19fc10f22d32d0f6886731f1875de58be4f0745c577b517da6e96a344f0d"
        ),
        "disposition": "zero_results_retained_private_not_used",
    },
    "somalia_world_bank_february_2025_missing": {
        "requested_url": (
            "https://documents1.worldbank.org/curated/en/099032525073016158/"
            "pdf/P176181-0d628a3b-fa9d-4404-ba75-c1a7b2d544d4.pdf"
        ),
        "http_status": 404,
        "body_file": "somalia_wb_2025_mar.body",
        "body_bytes": 100_826,
        "body_sha256": (
            "1c48e2bb0b650b57f50006624c8d3475a4a40c2fa9fcd6b21fb1f2d0c4b65bc1"
        ),
        "disposition": "failed_body_retained_private_not_used",
    },
    "somalia_world_bank_2026_nonmatching_pdf": {
        "requested_url": (
            "https://documents1.worldbank.org/curated/en/099063026190041665/"
            "pdf/P176181-2985ff27-1db6-45b2-aff8-800dbc38c5e4.pdf"
        ),
        "http_status": 200,
        "body_file": "somalia_wb_2026_pdf.body",
        "body_bytes": 266_386,
        "body_sha256": (
            "17bb140f26b5874a2296f1be08b8e2638165518bd73f0dc7b7fadc447b348ad0"
        ),
        "disposition": "eac_regional_document_no_somalia_data_center_claim_used",
    },
    "congo_afdb_direct_attempt": {
        "requested_url": CAPTURE_BODIES["congo_progress"]["url"],
        "http_status": 403,
        "body_file": "congo_afdb_progress.body",
        "body_bytes": 6_164,
        "body_sha256": (
            "00ea29aec0c7e11f657e3d0288b55bedc8a68ca35c101861cdcb5b8e12b00a1a"
        ),
        "disposition": "failed_attempt_retained_private_later_200_body_used",
    },
    "telia_lithuania_blog_direct_attempt": {
        "requested_url": (
            "https://www.telia.lt/blog/kuriamas-saugus-di-tinklas-svedijoje-"
            "uz-9-2-mlrd-euru"
        ),
        "http_status": 403,
        "body_file": "telia_lt.body",
        "body_bytes": 5_811,
        "body_sha256": (
            "54b34f170c65f053425d5d0a22a60d3635289d38925db719bbf9cd42c5e2e856"
        ),
        "disposition": "failed_body_retained_private_not_used",
    },
    "telia_ndc_direct_attempt": {
        "requested_url": "https://www.telia.lt/ndc",
        "http_status": 403,
        "body_file": "telia_ndc.body",
        "body_bytes": 5_561,
        "body_sha256": (
            "57a12e9ade0dd5bd5c87e83aab450d81034f4947c9847aeab26ad76ddc9c6646"
        ),
        "disposition": "failed_body_retained_private_not_used",
    },
    "telia_ndc_headless_challenge": {
        "requested_url": "https://www.telia.lt/ndc",
        "http_status": None,
        "body_file": "telia_ndc.chrome.body",
        "body_bytes": 27_429,
        "body_sha256": (
            "3a12196e7cb507963cca881fb5e8e7a29aa2f1ef7e44e5e0a1ab96119421dd1f"
        ),
        "disposition": "cloudflare_challenge_retained_private_not_used",
    },
}


def _source_records(
    documents: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["project"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": len(
                    document["operating_models"]
                ),
                "workload_observations": len(document["workloads"]),
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": SOURCE_DISPOSITIONS[name],
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-nine-candidate-regional-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 9,
        "seed_eligible_count": 6,
        "review_only_count": 3,
        "candidates": [
            {
                "candidate_id": "niger-national-dc-pk5-niamey",
                "country": "Niger",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "ANP places a construction site at PK5 in 2025; the Niger "
                    "government later says equipment installation was progressing "
                    "after civil works were finalized in June 2026."
                ),
                "capacity_disposition": (
                    "Level 3 and CFA 10 billion are resilience and cost context, not "
                    "capacity or consumption."
                ),
            },
            {
                "candidate_id": "somalia-national-dc-mogadishu-site-unresolved",
                "country": "Somalia",
                "decision": "seed_eligible_city_level_site_unresolved",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "MoCT reports ongoing National Data Center construction in "
                    "Mogadishu on 2025-05-06 but does not allocate the observation to "
                    "either procurement-defined site."
                ),
                "site_resolution": "Mogadishu only",
            },
            {
                "candidate_id": "somalia-national-dc-primary-mogadishu-airport",
                "country": "Somalia",
                "decision": "review_only_bid_identity_current_status_unknown",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "The MoCT bid identifies the Airport as proposed primary site, "
                    "but the 2025 status page does not allocate its observed works to "
                    "that site."
                ),
                "lifecycle_observation_created": False,
                "site_allocation_inferred": False,
            },
            {
                "candidate_id": "somalia-national-dc-dr-moct",
                "country": "Somalia",
                "decision": "review_only_bid_identity_current_status_unknown",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "The MoCT bid identifies a DR site at the ministry, but the 2025 "
                    "status page does not allocate its observed works to that site."
                ),
                "lifecycle_observation_created": False,
                "site_allocation_inferred": False,
            },
            {
                "candidate_id": "republic-congo-national-dc-bacongo",
                "country": "Republic of the Congo",
                "decision": "seed_eligible_fresh_official_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "African Development Bank pages place the National Data Center in "
                    "Bacongo and report remaining server-room and civil work in June "
                    "2025."
                ),
            },
            {
                "candidate_id": "telia-vilnius-new-data-center",
                "country": "Lithuania",
                "decision": "seed_eligible_city_level_official_report",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Telia's Q1 2026 issuer report says construction started on a new "
                    "data center in Vilnius."
                ),
                "location_disposition": (
                    "Vilnius only; Raisteniškės and street-level detail remain "
                    "unnormalized because the direct Telia Lithuania body was blocked."
                ),
                "capacity_disposition": (
                    "6 MW, 8 MW, 3-to-10 MW, and PUE claims are excluded because they "
                    "are absent from the governed selected body."
                ),
            },
            {
                "candidate_id": "atnorth-ice02-phase-2",
                "country": "Iceland",
                "decision": "seed_eligible_current_contractor_page",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Mannverk says ICE02 phase-two work at Reykjanesbær remains ongoing "
                    "on the page captured 2026-07-21."
                ),
                "capacity_disposition": (
                    "Campus 83 MW and plus-35 MW values are not allocated to phase two "
                    "by the selected body and are not normalized."
                ),
            },
            {
                "candidate_id": "borealis-blonduos-expansion",
                "country": "Iceland",
                "decision": "seed_eligible_utility_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Landsvirkjun describes the Blönduós campus expansion and says the "
                    "facility is being equipped on 2026-06-23."
                ),
                "capacity_disposition": (
                    "The 12 MW value is contracted firm supply, while 70 MW is an "
                    "Iceland-wide aggregate; neither becomes a project capacity row."
                ),
            },
            {
                "candidate_id": "orel-it-campus-data-center-nawinna",
                "country": "Sri Lanka",
                "decision": "review_only_identity_and_design_no_physical_status",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "TIA registry and certificate bytes support OREL Nawinna identity "
                    "and design review only. They do not establish physical work."
                ),
                "captured_sources": [
                    {
                        "url": CAPTURE_BODIES["orel_tia_registry"]["url"],
                        "bytes": CAPTURE_BODIES["orel_tia_registry"]["bytes"],
                        "sha256": CAPTURE_BODIES["orel_tia_registry"]["sha256"],
                    },
                    {
                        "url": CAPTURE_BODIES["orel_tia_certificate"]["url"],
                        "bytes": CAPTURE_BODIES["orel_tia_certificate"]["bytes"],
                        "sha256": CAPTURE_BODIES["orel_tia_certificate"]["sha256"],
                    },
                ],
                "classification_guardrail": (
                    "TIA-942 design certification or resilience classification is not "
                    "capacity, construction, completion, or operation."
                ),
                "manual_capture_follow_up": {
                    "source_url": (
                        "https://www.linkedin.com/pulse/leading-future-infrastructure-"
                        "orel-secures-sri-lankas-first-tia-942-c-hu3kc"
                    ),
                    "publisher_body_captured": False,
                    "automated_linkedin_capture_performed": False,
                    "used_for_normalized_claims": False,
                },
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    controlled = [
        {
            "capture_id": capture_id,
            "requested_url": spec["url"],
            "effective_url": spec["url"],
            "retrieved_at": spec["retrieved_at"],
            "http_status": 200,
            "content_type": spec["content_type"],
            "body": {
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "capture_method": spec.get(
                "capture_method", "curl_location_compressed"
            ),
            "request_credentials_supplied": False,
        }
        for capture_id, spec in sorted(CAPTURE_BODIES.items())
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public HTTP GETs used a transparent research User-Agent. "
            "AFDB pages required a credential-free browser-compatible TLS client after "
            "a direct 403. A separate isolated headless Chrome attempt reached only a "
            "Telia Cloudflare challenge."
        ),
        "successful_body_captures": len(CAPTURE_BODIES),
        "selected_source_evidence_bodies": 11,
        "assessment_only_bodies": 2,
        "technical_source_incident_groups": 3,
        "request_credentials_supplied": False,
        "automated_linkedin_capture_performed": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "isolated_browser_profile_original_path": str(BROWSER_PROFILE_ORIGIN),
        "isolated_browser_profile_moved_to_trash": True,
        "isolated_browser_profile_trash_path": str(BROWSER_PROFILE_TRASH),
        "controlled_captures": controlled,
        "technical_captures": [
            {"capture_id": key, **value}
            for key, value in sorted(TECHNICAL_CAPTURES.items())
        ],
        "technical_incidents": [
            {
                "incident_id": "somalia_world_bank_audited_body_missing",
                "status": (
                    "Two audited World Bank PDF URLs returned 404 and the October "
                    "2025 GUID API lookup returned zero results. Failed bodies and "
                    "response facts are preserved privately."
                ),
                "normalized_claims_created": False,
            },
            {
                "incident_id": "telia_lithuania_cloudflare_block",
                "status": (
                    "Direct Telia Lithuania requests returned 403, a curl-compatible "
                    "browser attempt failed, and isolated headless Chrome returned a "
                    "Cloudflare challenge. The issuer Q1 PDF alone governs."
                ),
                "normalized_claims_created": False,
            },
            {
                "incident_id": "afdb_direct_403_recovered",
                "status": (
                    "A direct AFDB request returned 403; a later credential-free "
                    "browser-compatible TLS request returned the publisher body used "
                    "for evidence. Both attempts remain in the private raw tree."
                ),
                "normalized_claims_created_from_failed_body": False,
            },
        ],
        "research_exclusions": [
            {
                "capture_id": "somalia_world_bank_2026_nonmatching_pdf",
                "reason": (
                    "The retrieved PDF concerns an East African regional program and "
                    "contains no Somalia National Data Center claim."
                ),
            }
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build regional-gap assessment

This immutable artifact records nine bounded candidate dispositions researched on 2026-07-21. Six direct official or contractor sources pass the physical-construction boundary: Niger National Data Center PK5, one site-unresolved Somalia National Data Center record in Mogadishu, the Republic of the Congo National Data Center in Bacongo, Telia's new Vilnius data center, atNorth ICE02 phase two, and the Borealis Blönduós expansion. Every lifecycle row is a dated last-observed fact, never a timeless current-status assertion.

Somalia is intentionally normalized once at city level. The 2025 MoCT update does not connect its observed construction to either site in the procurement document. Mogadishu Airport primary and the MoCT DR site therefore remain separate review-only candidate identities with current status unknown, no lifecycle rows, and no site allocation. Audited World Bank 2025 document URLs returned 404 and the October GUID lookup returned zero results; every failed body and response fact remains in the private raw capture tree.

Telia is likewise normalized only to Vilnius. The governed issuer report says construction started during Q1 2026. Direct Telia Lithuania attempts returned Cloudflare challenges, so Raisteniškės, street-level detail, 3-to-10 MW, PUE below 1.2, and media values of 6 MW or 8 MW are excluded. OREL Nawinna remains review-only because TIA registry and design-certificate bytes do not establish physical construction.

No capacity, workload, or operating-model row is emitted. Niger level 3 and project cost are not capacity. atNorth campus-scale 83 MW and plus-35 MW statements are not allocated to phase two. Borealis' 12 MW is contracted firm power supply and 70 MW is an Iceland-wide aggregate, not project load or consumption. TIA certification is resilience/design context only.

No source has coordinates or geometry. No publisher image, satellite image, aerial image, computer vision, or analyst geolocation contributes to identity, status, capacity, type, or roles.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. The accepted v73 seed and every downstream artifact remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete 67-file capture directory and the isolated Chrome profile were moved intact to the recoverable Trash paths in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 9,
            "source_records": 6,
            "seed_eligible_source_records": 6,
            "review_only_candidates": 3,
            "distinct_campuses": 6,
            "projects": 6,
            "entity_snapshots": 12,
            "unique_evidence_records": 11,
            "lifecycle_observations": 8,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v73_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v73.json",
                "bytes": V73_PINS[V73_DEFINITION][0],
                "sha256": V73_PINS[V73_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v73/manifest.json",
                "bytes": V73_PINS[V73_MANIFEST][0],
                "sha256": V73_PINS[V73_MANIFEST][1],
            },
            "release_tree_sha256": V73_TREE_SHA256,
            "v73_selected_input_count": V73_INPUT_COUNT,
            "new_source_paths_selected_by_v73": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v73_mutated": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "coordinate_integration": "none",
            "coverage_ledger_integration": "none",
            "downstream_product_integration": "none",
        },
        "publication_contract": {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "final_root_ctime_not_before_recorded_at": True,
            "source_file_mode": "0644",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured publisher response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "automated_linkedin_capture_performed": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "isolated_browser_profile_original_path": str(BROWSER_PROFILE_ORIGIN),
        "isolated_browser_profile_moved_to_trash": True,
        "isolated_browser_profile_trash_path": str(BROWSER_PROFILE_TRASH),
        "isolated_browser_profile_recoverable": True,
        "deletion_performed": False,
        "candidate_dispositions": {
            "seed_eligible": 6,
            "review_only": 3,
        },
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(
            _candidate_assessments(recorded_at)
        ),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return _sha256_bytes(payload)


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o644)
        _fsync_regular(output)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        output = stage / name
        output.write_bytes(payloads[name])
        output.chmod(0o444)
        _fsync_regular(output)
    rows = [
        {
            "bytes": (stage / name).stat().st_size,
            "path": name,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 9,
        "curated_source_records": 6,
        "seed_eligible_source_records": 6,
        "review_only_candidates": 3,
        "successful_raw_captures": len(CAPTURE_BODIES),
        "technical_source_incident_groups": 3,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "isolated_browser_profile_moved_intact_to_trash": True,
        "automated_linkedin_capture_performed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "publication_contract_version": 1,
    }
    manifest_raw = _canonical(manifest)
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(manifest_raw)
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    checksum_path = stage / "manifest.sha256"
    checksum_path.write_text(
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n",
        encoding="utf-8",
    )
    checksum_path.chmod(0o444)
    _fsync_regular(checksum_path)
    _fsync_directory(stage)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    if set(paths) != set(SOURCE_FILENAMES):
        raise OfficialTrancheError("source path set differs")
    expected = expected_source_documents()
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialTrancheError(f"curated source is absent or unsafe: {source}")
        raw = source.read_bytes()
        if raw != _canonical(expected[name]):
            raise OfficialTrancheError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise OfficialTrancheError(f"curated source mode differs: {name}")
        document = json.loads(raw)
        if document["capacities"] or document["workloads"]:
            raise OfficialTrancheError(
                f"source crosses capacity or workload boundary: {name}"
            )
        for entity in ("campus", "project"):
            if document[entity]["coordinates"] is not None:
                raise OfficialTrancheError(f"source invented coordinates: {name}")
            if document[entity]["geometry"] is not None:
                raise OfficialTrancheError(f"source invented geometry: {name}")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    stable_keys = {
        document[entity]["stable_key"]
        for document in planned.values()
        for entity in ("campus", "project")
    }
    evidence_keys = {
        evidence["key"]
        for document in planned.values()
        for evidence in document["evidence"]
    }
    if len(stable_keys) != 12 or len(evidence_keys) != 11:
        raise OfficialTrancheError("planned source keys are not unique")
    collisions: dict[str, dict[str, list[str]]] = {}
    for source in SOURCES_ROOT.glob("*.json"):
        if source.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        other_stable = {
            record.get("stable_key")
            for key in ("campus", "project")
            if isinstance((record := document.get(key)), dict)
        }
        other_evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        stable_overlap = sorted(stable_keys & other_stable)
        evidence_overlap = sorted(evidence_keys & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[source.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise OfficialTrancheError(f"curated source collision: {collisions!r}")


def _validate_v73_nonmutation() -> None:
    for source, pin in V73_PINS.items():
        _pin(source, pin)
    if tree_digest(V73_RELEASE) != V73_TREE_SHA256:
        raise OfficialTrancheError("accepted v73 release tree differs")
    definition = json.loads(V73_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V73_INPUT_COUNT:
        raise OfficialTrancheError("accepted v73 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialTrancheError("v73 unexpectedly selects a new source path")
    entities_text = V73_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialTrancheError("new source stable key collides with v73")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialTrancheError(f"capture directory is absent or unsafe: {directory}")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialTrancheError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialTrancheError("capture directory contains a non-ordinary file")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialTrancheError("capture directory tree differs")
    for spec in CAPTURE_BODIES.values():
        _pin(directory / spec["filename"], (spec["bytes"], spec["sha256"]))
    for spec in TECHNICAL_CAPTURES.values():
        _pin(
            directory / spec["body_file"],
            (spec["body_bytes"], spec["body_sha256"]),
        )


def _validate_browser_profile_disposition() -> None:
    if BROWSER_PROFILE_ORIGIN.exists():
        raise OfficialTrancheError("isolated browser profile remains in temporary path")
    if BROWSER_PROFILE_TRASH.is_symlink() or not BROWSER_PROFILE_TRASH.is_dir():
        raise OfficialTrancheError("isolated browser profile Trash directory is absent")


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
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
            "entities": 12,
            "entity_snapshots": 12,
            "evidence": 11,
            "lifecycle_observations": 8,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise OfficialTrancheError(f"offline import counts differ: {counts!r}")
        lifecycle = [
            tuple(row)
            for row in connection.execute(
                "SELECT e.stable_key, l.status, l.as_of_date "
                "FROM lifecycle_observations AS l "
                "JOIN entities AS e ON e.id = l.entity_id "
                "ORDER BY e.stable_key, l.as_of_date"
            )
        ]
        expected_lifecycle = [
            (
                "curated:atnorth-ice02-reykjanesbaer-campus:phase-2-expansion",
                "under_construction",
                "2026-07-21",
            ),
            (
                "curated:borealis-blonduos-data-center-campus:expansion-current-build",
                "under_construction",
                "2026-06-23",
            ),
            (
                "curated:niger-national-data-center-pk5-niamey:current-build",
                "under_construction",
                "2025-06-19",
            ),
            (
                "curated:niger-national-data-center-pk5-niamey:current-build",
                "under_construction",
                "2026-06-18",
            ),
            (
                "curated:republic-congo-national-data-center-bacongo:current-build",
                "under_construction",
                "2024-05-17",
            ),
            (
                "curated:republic-congo-national-data-center-bacongo:current-build",
                "under_construction",
                "2025-06-26",
            ),
            (
                "curated:somalia-national-data-center-mogadishu-site-unresolved:"
                "current-build-site-unresolved",
                "under_construction",
                "2025-05-06",
            ),
            (
                "curated:telia-vilnius-data-center:new-data-center-current-build",
                "under_construction",
                "2026-03-31",
            ),
        ]
        if lifecycle != expected_lifecycle:
            raise OfficialTrancheError(
                f"offline lifecycle rows differ: {lifecycle!r}"
            )
        return counts


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialTrancheError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialTrancheError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialTrancheError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialTrancheError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialTrancheError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise OfficialTrancheError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialTrancheError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 9
        or manifest.get("curated_source_records") != 6
        or manifest.get("seed_eligible_source_records") != 6
        or manifest.get("review_only_candidates") != 3
        or manifest.get("technical_source_incident_groups") != 3
        or manifest.get("automated_linkedin_capture_performed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialTrancheError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialTrancheError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialTrancheError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialTrancheError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialTrancheError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialTrancheError("artifact source pins differ")
    assessment = json.loads(
        entries["candidate-assessment.json"].read_text(encoding="utf-8")
    )
    rows = {row["candidate_id"]: row for row in assessment["candidates"]}
    for candidate_id in (
        "somalia-national-dc-primary-mogadishu-airport",
        "somalia-national-dc-dr-moct",
        "orel-it-campus-data-center-nawinna",
    ):
        if rows[candidate_id]["source_record_created"]:
            raise OfficialTrancheError(f"review-only candidate promoted: {candidate_id}")
    if not rows["somalia-national-dc-mogadishu-site-unresolved"]["seed_eligible"]:
        raise OfficialTrancheError("Somalia unresolved-source boundary differs")
    telia = expected_source_documents()[SOURCE_FILENAMES[3]]
    if telia["project"]["address"] != "Vilnius, Lithuania":
        raise OfficialTrancheError("Telia location crossed governed body boundary")
    if any(document["capacities"] for document in expected_source_documents().values()):
        raise OfficialTrancheError("a capacity row crossed the exclusion boundary")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialTrancheError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialTrancheError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for document in expected_source_documents().values():
        for evidence in document["evidence"]:
            if _instant(evidence["retrieved_at"]) > target:
                raise OfficialTrancheError("evidence retrieval post-dates recorded_at")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise OfficialTrancheError(
            f"active publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _all_stage_paths(source_stage: Path, artifact_stage: Path) -> tuple[Path, ...]:
    source_members = sorted(source_stage.iterdir(), key=lambda item: item.name)
    artifact_members = sorted(artifact_stage.iterdir(), key=lambda item: item.name)
    return (source_stage, *source_members, artifact_stage, *artifact_members)


@dataclass(frozen=True)
class _PreparedPublication:
    recorded_at: str
    target: datetime
    source_stage: Path
    source_stage_identity: tuple[int, int]
    source_identities: Mapping[str, tuple[int, int]]
    artifact_stage: Path
    artifact_identity: tuple[int, int]
    artifact_member_identities: Mapping[str, tuple[int, int]]


def _prepare_publication(recorded_at: str) -> _PreparedPublication:
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise OfficialTrancheError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-regional-gap.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    source_stage_identity = _identity(source_stage, directory=True)
    artifact_identity = _identity(artifact_stage, directory=True)
    try:
        documents = expected_source_documents()
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        source_paths = _source_paths(source_stage)
        _validate_sources(source_paths)
        _offline_import(source_paths, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=source_paths,
            require_live=False,
            wall_clock=datetime.now(UTC),
        )
        finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
        _require_finals_absent(finals, "staging")
        _assert_stage_precedes_target(
            _all_stage_paths(source_stage, artifact_stage),
            target,
        )
        if datetime.now(UTC) >= target:
            raise OfficialTrancheError("private staging did not finish before recorded_at")
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            source_stage=source_stage,
            source_stage_identity=source_stage_identity,
            source_identities={
                name: _identity(source_stage / name, directory=False)
                for name in SOURCE_FILENAMES
            },
            artifact_stage=artifact_stage,
            artifact_identity=artifact_identity,
            artifact_member_identities={
                name: _identity(artifact_stage / name, directory=False)
                for name in CLOSED_FILES
            },
        )
    except BaseException as primary_error:
        try:
            if artifact_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in artifact_stage.iterdir()
                }
                _discard_owned_directory(
                    artifact_stage,
                    artifact_identity,
                    members,
                )
            if source_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
                _discard_owned_directory(
                    source_stage,
                    source_stage_identity,
                    members,
                )
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _publish(prepared: _PreparedPublication) -> None:
    final_sources = {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}
    finals = tuple(final_sources.values()) + (ARTIFACT,)
    _require_finals_absent(finals, "pre-wait")
    _wait_until(prepared.target.timestamp())
    _require_finals_absent(finals, "publication")
    _assert_stage_precedes_target(
        _all_stage_paths(prepared.source_stage, prepared.artifact_stage),
        prepared.target,
    )
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            stage = prepared.source_stage / name
            final = final_sources[name]
            identity = prepared.source_identities[name]
            _promote_noreplace(stage, final)
            promoted.append((stage, final, identity, False))
            if not _has_identity(final, identity, directory=False):
                raise OfficialTrancheError(
                    f"source identity changed on promotion: {name}"
                )
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append(
            (
                prepared.artifact_stage,
                ARTIFACT,
                prepared.artifact_identity,
                True,
            )
        )
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialTrancheError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.artifact_stage.exists():
        _discard_owned_directory(
            prepared.artifact_stage,
            prepared.artifact_identity,
            prepared.artifact_member_identities,
        )
    if prepared.source_stage.exists():
        _discard_owned_directory(
            prepared.source_stage,
            prepared.source_stage_identity,
            prepared.source_identities,
        )


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialTrancheError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 20.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish six sources and the nine-candidate regional-gap assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v73_nonmutation()
    _validate_browser_profile_disposition()
    capture_directory = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture_directory)
    with _publication_lock():
        _require_finals_absent(finals, "locked initial")
        prepared = _prepare_publication(target_text)
        published = False
        try:
            _move_capture_to_trash()
            _publish(prepared)
            published = True
        finally:
            if not published:
                _cleanup_prepared(prepared)
        if prepared.source_stage.exists():
            _discard_owned_directory(
                prepared.source_stage,
                prepared.source_stage_identity,
                prepared.source_identities,
            )
    _validate_capture_directory(CAPTURE_TRASH)
    _validate_browser_profile_disposition()
    _validate_v73_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 9,
            "source_records": 6,
            "seed_eligible": 6,
            "review_only": 3,
            "evidence": 11,
            "entities": 12,
            "lifecycle": 8,
            "operating_models": 0,
            "workloads": 0,
            "capacities": 0,
            "coordinates": 0,
            "geometry": 0,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "browser_profile": str(BROWSER_PROFILE_TRASH),
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
