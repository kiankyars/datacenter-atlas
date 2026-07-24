"""Build and freeze official open seed v68 as the exact v67 successor.

V68 preserves every frozen v67 input and appends exactly thirteen schema-1.1
curated sources from the two accepted 2026-07-21 discovery artifacts. Lifecycle
values remain dated, last-observed facts and never become current-status claims.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import asdict
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Iterator, Mapping

from .curated import CuratedOfficialSourceAdapter
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .epoch import EpochAIAdapter
from .open_seed_v56 import (
    canonical_json,
    discard_release_stage,
    promote_noreplace,
    sha256,
    tree_digest,
)
from .open_seed_v61 import FRESHNESS_FIELDS, FRESHNESS_FILENAME, build_freshness_csv
from .publication_release import build_release_documents
from .service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
RELEASE_ID = "2026-07-21-open-seed-v68"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v68.lock"

AS_OF = "2026-07-21"
RECORDED_AT = "2026-07-21T09:30:00Z"
V11_RECORDED_AT = RECORDED_AT
EPOCH_AS_OF = "2026-07-20"
SOURCE_LINEAGE_DATE = "2026-07-21"

BASE_DEFINITION_SHA256 = (
    "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5"
)
BASE_MANIFEST_SHA256 = (
    "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb"
)
BASE_TREE_SHA256 = "fb4a8016c3c0c143cef2e5ac35d0787bb2b0dbd45115e27a83a70167ccb0b4fb"

DISCOVERY_ARTIFACT_PINS: dict[str, dict[str, Any]] = {
    "source_artifacts/global-underrepresented-official-discovery-2026-07-21-v1": {
        "manifest_bytes": 1364,
        "manifest_sha256": (
            "2a55ae530cdb478fd922d6fad30ce836682671cb0fed95a040d2788e6292c7be"
        ),
        "tree_sha256": (
            "bf11d589deb0d3161254bbd688badbb859e419c4ff7a4458b7a0927fc323a07d"
        ),
        "source_snapshot_bytes": 8902,
        "source_snapshot_sha256": (
            "e58a912dbc6a278872fa030fd684480ff1d50284538736fe79df52d1e9c49927"
        ),
        "source_paths": frozenset(
            {
                "sources/curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json",
                "sources/curated-official-2026-07-21-harch-dakhla-groundbreaking.json",
                "sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json",
                "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json",
                "sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json",
                "sources/curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json",
                "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json",
                "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json",
            }
        ),
    },
    "source_artifacts/second-underrepresented-official-discovery-2026-07-21-v1": {
        "manifest_bytes": 1423,
        "manifest_sha256": (
            "df5e44d95af1fe7b81c10f3d58006b4db6cbe68816aa502673b93c863c1b9750"
        ),
        "tree_sha256": (
            "1a918b5045f90dbe7c6c66f9229fd7668bcb04979def38677d000017997c8cff"
        ),
        "source_snapshot_bytes": 8358,
        "source_snapshot_sha256": (
            "f96206e36891819b224d936bdf5fe9fdd6931d92d1ffd9b86bab62c1a477a349"
        ),
        "source_paths": frozenset(
            {
                "sources/curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json",
                "sources/curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json",
                "sources/curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json",
                "sources/curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json",
                "sources/curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json",
            }
        ),
    },
}

FRESHNESS_README = (
    "`lifecycle_freshness.csv` treats every published lifecycle value as a "
    "dated, last-observed historical fact on the 2026-07-21 release date and "
    "makes no current-construction inference. Its 0–90, 91–365, and over-365-"
    "day bands are review queues, not evidence that a status persisted. "
    "`current_status_classification` remains `unknown` and "
    "`current_construction_claim` remains `false` for every row, including "
    "the thirteen added project observations. Harch Dakhla, Firebird Hrazdan, "
    "and the unnamed Azerbaijan data center retain their dated publication-"
    "day observations; retrieval on 2026-07-21 is not a fresh status assertion. "
    "No workload, operating-model, hardware, unique-site, coordinate, geometry, "
    "satellite, aerial, computer-vision, or analyst-geolocation claim is added. "
    "The nine typed capacity rows retain their reported metric and stage; no "
    "capacity arithmetic is valid. The two hash-only discovery artifacts and "
    "all added source/capture identifiers retain 2026-07-21 lineage."
)

ADDITION_PINS: dict[str, tuple[int, str]] = {
    "sources/curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json": (
        6_583,
        "dc887d47d91abbd7e53da238414cf387263569cded4079a0db04f3881c4c2b56",
    ),
    "sources/curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json": (
        6_687,
        "154ea1798c6926ac48d2528f0e2dbe5fd9651fa2b0f547b01e0e364acb13cb95",
    ),
    "sources/curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json": (
        7_048,
        "0e976c4fd1e47bdd60495bbb1b9d98c0d9fc76b15d0aa7450b58088203a01b8f",
    ),
    "sources/curated-official-2026-07-21-harch-dakhla-groundbreaking.json": (
        6_882,
        "15fd52022e98268ff7911dd6a013e5a22d0d6eeea5da411c670b271dbf44712e",
    ),
    "sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json": (
        5_334,
        "2ff597a72913f8650f7c4bfad476388972c087f4a92bb557900ab187ce56d5f5",
    ),
    "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json": (
        6_032,
        "aaf91ac612720e5aaaf66fcc13a5061701b4f95ee5cd4499485b347f9a3d314c",
    ),
    "sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json": (
        5_998,
        "d87b556c1dd1aa9f979eaf37dd4d432b8f90884564e08cc8c32f8f619df3724b",
    ),
    "sources/curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json": (
        10_805,
        "1b43db6573bac2d62848abd8775a9542ca46e282a7057be7afc1353293c65763",
    ),
    "sources/curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json": (
        10_968,
        "7858e23a565879feb9e5fd4254b9f793809735e5fdd3b96717bfb77f3f3ddc14",
    ),
    "sources/curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json": (
        10_971,
        "3c1d13af526ff67b54af365252d25639352cca6608d6ca4e76a2f69a4b81624c",
    ),
    "sources/curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json": (
        6_033,
        "5d8ffb54fbf33f9eead89b21f1d69f148f8f69ed1047a6adc8a160e24801a23c",
    ),
    "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json": (
        5_666,
        "1894b5625adfa95f03a4a3ba981fa0a5e28010ef1cfa0fe1e7ba858e9a877699",
    ),
    "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json": (
        5_948,
        "04c1747343928095b9c2901c6ed95717766e8c6abce3e480d1157959791ab8c1",
    ),
}

ADDED_ENTITY_KEYS = frozenset(
    {
        "curated:azerbaijan-undisclosed-new-data-center-site",
        "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center",
        "curated:firebird-ai-center-hrazdan-site",
        "curated:firebird-ai-center-hrazdan-site:current-center-development",
        "curated:green-mountain-fra-mainz-campus",
        "curated:green-mountain-fra-mainz-campus:current-three-building-development",
        "curated:harch-intelligence-dakhla-campus",
        "curated:harch-intelligence-dakhla-campus:initial-development",
        "curated:scala-huechuraba-campus",
        "curated:scala-huechuraba-campus:ssclhb01",
        "curated:scala-lampa-campus",
        "curated:scala-lampa-campus:sscllp01",
        "curated:scala-praia-do-futuro-campus",
        "curated:scala-praia-do-futuro-campus:sforpf01",
        "curated:scala-smextp02-tepotzotlan-data-center",
        "curated:scala-smextp02-tepotzotlan-data-center:smextp02",
        "curated:scala-tambore-campus",
        "curated:scala-tambore-campus:sgrutb07",
        "curated:scala-tambore-campus:sgrutb09",
        "curated:scala-tambore-campus:sgrutb10",
        "curated:scala-tambore-campus:sgrutb11",
        "curated:scala-zona-franca-bogota-campus",
        "curated:scala-zona-franca-bogota-campus:sbogzb01",
    }
)
ADDED_PROJECT_KEYS = frozenset(
    {
        "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center",
        "curated:firebird-ai-center-hrazdan-site:current-center-development",
        "curated:green-mountain-fra-mainz-campus:current-three-building-development",
        "curated:harch-intelligence-dakhla-campus:initial-development",
        "curated:scala-huechuraba-campus:ssclhb01",
        "curated:scala-lampa-campus:sscllp01",
        "curated:scala-praia-do-futuro-campus:sforpf01",
        "curated:scala-smextp02-tepotzotlan-data-center:smextp02",
        "curated:scala-tambore-campus:sgrutb07",
        "curated:scala-tambore-campus:sgrutb09",
        "curated:scala-tambore-campus:sgrutb10",
        "curated:scala-tambore-campus:sgrutb11",
        "curated:scala-zona-franca-bogota-campus:sbogzb01",
    }
)
ADDED_COORDINATE_KEYS: frozenset[str] = frozenset()

LIFECYCLE_WINNERS = {
    "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center": (
        "under_construction",
        "2026-06-30",
    ),
    "curated:firebird-ai-center-hrazdan-site:current-center-development": (
        "under_construction",
        "2026-06-05",
    ),
    "curated:green-mountain-fra-mainz-campus:current-three-building-development": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:harch-intelligence-dakhla-campus:initial-development": (
        "under_construction",
        "2026-03-15",
    ),
    "curated:scala-huechuraba-campus:ssclhb01": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-lampa-campus:sscllp01": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-praia-do-futuro-campus:sforpf01": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-smextp02-tepotzotlan-data-center:smextp02": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-tambore-campus:sgrutb07": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-tambore-campus:sgrutb09": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-tambore-campus:sgrutb10": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-tambore-campus:sgrutb11": (
        "under_construction",
        "2026-07-21",
    ),
    "curated:scala-zona-franca-bogota-campus:sbogzb01": (
        "under_construction",
        "2026-07-21",
    ),
}

DATED_HISTORICAL_PROJECT_KEYS = frozenset(
    {
        "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center",
        "curated:firebird-ai-center-hrazdan-site:current-center-development",
        "curated:harch-intelligence-dakhla-campus:initial-development",
    }
)

CAPACITY_CONTRACT = {
    (
        "curated:green-mountain-fra-mainz-campus:current-three-building-development",
        "gross_facility_mw",
        "planned",
        54.0,
        "2026-07-21",
    ),
    (
        "curated:scala-huechuraba-campus:ssclhb01",
        "critical_it_mw",
        "design",
        4.8,
        "2026-07-21",
    ),
    (
        "curated:scala-lampa-campus:sscllp01",
        "critical_it_mw",
        "design",
        48.0,
        "2026-07-21",
    ),
    (
        "curated:scala-praia-do-futuro-campus:sforpf01",
        "critical_it_mw",
        "design",
        7.2,
        "2026-07-21",
    ),
    (
        "curated:scala-smextp02-tepotzotlan-data-center:smextp02",
        "critical_it_mw",
        "design",
        2.0,
        "2026-07-21",
    ),
    (
        "curated:scala-tambore-campus:sgrutb07",
        "critical_it_mw",
        "design",
        36.0,
        "2026-07-21",
    ),
    (
        "curated:scala-tambore-campus:sgrutb09",
        "critical_it_mw",
        "design",
        36.0,
        "2026-07-21",
    ),
    (
        "curated:scala-tambore-campus:sgrutb10",
        "critical_it_mw",
        "design",
        36.0,
        "2026-07-21",
    ),
    (
        "curated:scala-tambore-campus:sgrutb11",
        "critical_it_mw",
        "design",
        12.0,
        "2026-07-21",
    ),
}

WORKLOAD_CONTRACT: set[tuple[str, str, str, str]] = set()
SHARED_CAMPUS_KEY = "curated:scala-tambore-campus"
SHARED_CAMPUS_EVIDENCE_KEY = (
    "scala-sgrutb07-current-portfolio-captured-2026-07-21"
)
SHARED_EVIDENCE_COUNTS = {SHARED_CAMPUS_EVIDENCE_KEY: 4}
UNTYPED_METADATA_CONTRACT = {
    "harch-dakhla-groundbreaking-2026-03-15-captured-2026-07-21": {
        "pipeline_capacity_mw_untyped_as_reported": 500,
        "first_module_mw_untyped_as_reported": 100,
        "gpu_count_as_reported": 1_798,
    },
    "armenia-firebird-hrazdan-progress-2026-06-05-captured-2026-07-21": {
        "phase_one_gpu_count_more_than_as_reported": 6_000,
        "phase_two_additional_gpu_count_more_than_as_reported": 41_000,
        "capacity_mw_untyped_as_reported": 18,
        "compute_fp4_tensor_exaflops_up_to_as_reported": 110.6,
    },
}
FRESHNESS_CLASS_TRANSITION: dict[str, tuple[str, str]] = {}

# Derived from a fresh mutable v67-to-v68 comparison before publication.
CSV_DELTA_CONTRACT: dict[str, tuple[int, int, str, int, str]] = {
    "entities.csv": (
        783,
        23,
        "8c4dd1cfa3af23be4b4eb3561dd0c1d30970f98cbd1be1f66005a0bf2b9339eb",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        494,
        13,
        "882f8d22c61fdf6da8f96f625f30c50ae3468cfeeafcf36312653f59a1b63682",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        521,
        9,
        "60a43436f3345cb6b3281371fa87aef0e26780608695c982d0c81036c01a4d53",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        401,
        13,
        "8fdc77073cbf8174cfa02651f27a19a9a734580044cb0a35972e0ca72dfeefda",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        303,
        13,
        "c2c1969c4e24c24f018cb3579b2abd8c0552edaeaed2c8f832b1708e8317115f",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "resolution_candidates.csv": (
        6,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "lifecycle_freshness.csv": (
        443,
        13,
        "0ccc704478231df0ffd9aed0dbfcdf9dd74072431e2ea4006efb1146e9ea3f48",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}

NEW_SOURCE_FAMILIES = {
    "armenia_high_tech_ministry_news",
    "azerbaijan_digital_development_ministry_news",
    "green_mountain_data_center_pages",
    "harch_corp_newsroom",
}


def freshness_contract() -> dict[str, Any]:
    """Preserve the exact frozen v67 freshness contract."""

    base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
    contract = base.get("freshness_contract")
    if not isinstance(contract, dict):
        raise SystemExit("frozen v67 freshness contract is invalid")
    return contract


@contextmanager
def publication_lock() -> Iterator[None]:
    """Hold an exclusive v68 publication lock without replacing any file."""

    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(
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


def _load_addition(relative: str, size: int, digest: str) -> dict[str, Any]:
    source = ROOT / relative
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"addition must be an ordinary file: {relative}")
    if stat.S_IMODE(source.stat().st_mode) != 0o644:
        raise SystemExit(f"addition mode must be 0644: {relative}")
    raw = source.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit(f"addition byte pin differs: {relative}")
    document = json.loads(raw)
    if raw.decode("utf-8") != json.dumps(
        document, indent=2, ensure_ascii=False
    ) + "\n":
        raise SystemExit(f"addition JSON is not canonical: {relative}")
    return document


def _validate_artifact_lineage() -> dict[str, dict[str, str | int]]:
    """Validate the two closed discovery artifacts and their source inventories."""

    expected_files = {
        "README.md",
        "identity-and-capacity-guardrails.json",
        "manifest.json",
        "manifest.sha256",
        "retrieval-inventory.json",
        "rights-and-disposition.json",
        "source-snapshot.json",
    }
    source_union: set[str] = set()
    state: dict[str, dict[str, str | int]] = {}
    for relative, pin in DISCOVERY_ARTIFACT_PINS.items():
        artifact = ROOT / relative
        if (
            not artifact.is_dir()
            or artifact.is_symlink()
            or stat.S_IMODE(artifact.stat().st_mode) != 0o555
        ):
            raise SystemExit(f"v68 discovery artifact is not frozen: {relative}")
        entries = {path.name: path for path in artifact.iterdir()}
        if set(entries) != expected_files or any(
            path.is_symlink() or not path.is_file() for path in entries.values()
        ):
            raise SystemExit(f"v68 discovery artifact file set differs: {relative}")
        if any(stat.S_IMODE(path.stat().st_mode) != 0o444 for path in entries.values()):
            raise SystemExit(f"v68 discovery artifact file mode differs: {relative}")

        manifest_raw = entries["manifest.json"].read_bytes()
        if (
            len(manifest_raw) != pin["manifest_bytes"]
            or hashlib.sha256(manifest_raw).hexdigest() != pin["manifest_sha256"]
        ):
            raise SystemExit(f"v68 discovery manifest pin differs: {relative}")
        manifest = json.loads(manifest_raw)
        if manifest_raw.decode("utf-8") != (
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        ):
            raise SystemExit(f"v68 discovery manifest is not canonical: {relative}")
        if (
            set(manifest.get("closed_file_set", [])) != expected_files
            or manifest.get("raw_capture_redistributed") is not False
            or manifest.get("tree_sha256") != pin["tree_sha256"]
        ):
            raise SystemExit(f"v68 discovery manifest contract differs: {relative}")
        listed = manifest.get("files")
        if not isinstance(listed, list):
            raise SystemExit(f"v68 discovery manifest file pins differ: {relative}")
        for row in listed:
            path = entries.get(row.get("path"))
            if path is None:
                raise SystemExit(f"v68 discovery manifest names an unknown file: {relative}")
            payload = path.read_bytes()
            if (len(payload), hashlib.sha256(payload).hexdigest()) != (
                row.get("bytes"),
                row.get("sha256"),
            ):
                raise SystemExit(f"v68 discovery file pin differs: {relative}")
        tree_payload = (
            json.dumps(listed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if hashlib.sha256(tree_payload).hexdigest() != pin["tree_sha256"]:
            raise SystemExit(f"v68 discovery tree pin differs: {relative}")
        expected_checksum = f"{pin['manifest_sha256']}  manifest.json\n"
        if entries["manifest.sha256"].read_text(encoding="utf-8") != expected_checksum:
            raise SystemExit(f"v68 discovery checksum carrier differs: {relative}")

        snapshot_raw = entries["source-snapshot.json"].read_bytes()
        if (
            len(snapshot_raw) != pin["source_snapshot_bytes"]
            or hashlib.sha256(snapshot_raw).hexdigest()
            != pin["source_snapshot_sha256"]
        ):
            raise SystemExit(f"v68 discovery snapshot pin differs: {relative}")
        snapshot = json.loads(snapshot_raw)
        if snapshot_raw.decode("utf-8") != (
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        ):
            raise SystemExit(f"v68 discovery snapshot is not canonical: {relative}")
        if any(
            snapshot.get(field) != "none"
            for field in (
                "release_integration",
                "open_seed_integration",
                "downstream_product_integration",
            )
        ) or snapshot.get("v67_selected_input_count") != 378:
            raise SystemExit(f"v68 discovery snapshot lineage differs: {relative}")
        records = snapshot.get("source_records")
        if not isinstance(records, list):
            raise SystemExit(f"v68 discovery source records differ: {relative}")
        record_paths = {row.get("path") for row in records}
        if record_paths != pin["source_paths"] or len(record_paths) != len(records):
            raise SystemExit(f"v68 discovery source inventory differs: {relative}")
        if source_union & record_paths:
            raise SystemExit("v68 discovery artifacts overlap source paths")
        source_union.update(record_paths)
        for row in records:
            addition_pin = ADDITION_PINS.get(row["path"])
            if addition_pin != (row.get("bytes"), row.get("sha256")):
                raise SystemExit(f"v68 artifact/source pin differs: {row['path']}")
            if row.get("schema_version") != "1.1" or row.get("seeded") is not False:
                raise SystemExit(f"v68 discovery source state differs: {row['path']}")
        state[relative] = {
            "manifest_bytes": len(manifest_raw),
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "source_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
            "tree_sha256": manifest["tree_sha256"],
        }
    if source_union != set(ADDITION_PINS):
        raise SystemExit("v68 discovery lineage does not close over all additions")
    return state


def _validate_additions() -> None:
    if len(ADDITION_PINS) != 13 or tuple(ADDITION_PINS) != tuple(sorted(ADDITION_PINS)):
        raise SystemExit("v68 must contain exactly thirteen canonical additions")
    _validate_artifact_lineage()
    documents = {
        relative: _load_addition(relative, size, digest)
        for relative, (size, digest) in ADDITION_PINS.items()
    }
    entities_by_key: dict[str, list[dict[str, Any]]] = {}
    evidence_by_key: dict[str, list[dict[str, Any]]] = {}
    lifecycle_rows: list[tuple[str, str, str]] = []
    capacity_rows: set[tuple[str, str, str, float, str]] = set()
    workload_rows: set[tuple[str, str, str, str]] = set()
    coordinate_keys: set[str] = set()
    operating_model_count = 0
    metadata_seen: dict[str, dict[str, Any]] = {}
    for relative, document in documents.items():
        if document.get("schema_version") != "1.1":
            raise SystemExit(f"v68 addition schema differs: {relative}")
        if "2026-07-21" not in relative or "2026-07-20" in relative:
            raise SystemExit(f"v68 addition path loses Jul21 lineage: {relative}")
        for evidence in document["evidence"]:
            evidence_by_key.setdefault(evidence["key"], []).append(evidence)
            if "captured-2026-07-21" not in evidence["key"]:
                raise SystemExit(f"v68 evidence key loses Jul21 lineage: {relative}")
            if evidence["retrieved_at"] > RECORDED_AT:
                raise SystemExit(f"v68 evidence is newer than publication: {relative}")
            expected_metadata = UNTYPED_METADATA_CONTRACT.get(evidence["key"])
            if expected_metadata is not None:
                metadata = evidence.get("metadata", {})
                metadata_seen[evidence["key"]] = {
                    key: metadata.get(key) for key in expected_metadata
                }
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            entities_by_key.setdefault(entity["stable_key"], []).append(entity)
            if date.fromisoformat(entity["as_of_date"]) > date.fromisoformat(AS_OF):
                raise SystemExit(f"v68 entity crosses release day: {relative}")
            if entity["coordinates"] is not None:
                coordinate_keys.add(entity["stable_key"])
            if entity["geometry"] is not None:
                raise SystemExit(f"v68 addition gained unsupported geometry: {relative}")
        for row in document["lifecycle"]:
            stable_key = document[row["entity"]]["stable_key"]
            lifecycle_rows.append((stable_key, row["value"], row["as_of_date"]))
            if date.fromisoformat(row["as_of_date"]) > date.fromisoformat(AS_OF):
                raise SystemExit(f"v68 lifecycle crosses release day: {relative}")
        for row in document["capacities"]:
            stable_key = document[row["entity"]]["stable_key"]
            capacity_rows.add(
                (
                    stable_key,
                    row["metric"],
                    row["stage"],
                    float(row["base"]),
                    row["as_of_date"],
                )
            )
            if (row["metric"], row["stage"]) not in {
                ("critical_it_mw", "design"),
                ("gross_facility_mw", "planned"),
            }:
                raise SystemExit(f"v68 promoted a conflicting or untyped metric: {relative}")
        for row in document["workloads"]:
            stable_key = document[row["entity"]]["stable_key"]
            workload_rows.add(
                (stable_key, row["value"], row["as_of_date"], row["method"])
            )
        operating_model_count += len(document["operating_models"])

    if set(entities_by_key) != ADDED_ENTITY_KEYS:
        raise SystemExit("v68 added entity identity set differs")
    shared_entities = {
        key: len(rows) for key, rows in entities_by_key.items() if len(rows) > 1
    }
    if shared_entities != {SHARED_CAMPUS_KEY: 4}:
        raise SystemExit(f"v68 intended shared campus differs: {shared_entities}")
    for key, rows in entities_by_key.items():
        if any(row != rows[0] for row in rows[1:]):
            raise SystemExit(f"v68 shared entity payload conflicts: {key}")
    if coordinate_keys != ADDED_COORDINATE_KEYS:
        raise SystemExit("v68 additions must not add coordinates")
    if len(lifecycle_rows) != 13:
        raise SystemExit("v68 lifecycle observation count differs")
    winners: dict[str, tuple[str, str]] = {}
    for stable_key, status, observed in sorted(
        lifecycle_rows, key=lambda row: (row[0], row[2])
    ):
        winners[stable_key] = (status, observed)
    if winners != LIFECYCLE_WINNERS:
        raise SystemExit(f"v68 lifecycle winners differ: {winners}")
    if capacity_rows != CAPACITY_CONTRACT:
        raise SystemExit(f"v68 capacity contract differs: {capacity_rows}")
    if workload_rows != WORKLOAD_CONTRACT:
        raise SystemExit(f"v68 workload contract differs: {workload_rows}")
    if operating_model_count:
        raise SystemExit("v68 additions gained an operating-model claim")
    if metadata_seen != UNTYPED_METADATA_CONTRACT:
        raise SystemExit(f"v68 untyped metadata contract differs: {metadata_seen}")

    occurrences = sum(len(rows) for rows in evidence_by_key.values())
    shared_counts = {
        key: len(rows) for key, rows in evidence_by_key.items() if len(rows) > 1
    }
    if occurrences != 16 or len(evidence_by_key) != 13:
        raise SystemExit("v68 evidence occurrence/dedup arithmetic differs")
    if shared_counts != SHARED_EVIDENCE_COUNTS:
        raise SystemExit(f"v68 intended shared evidence keys differ: {shared_counts}")
    for key, rows in evidence_by_key.items():
        if any(row != rows[0] for row in rows[1:]):
            raise SystemExit(f"v68 shared evidence payload conflicts: {key}")


def selected_inputs(base: Mapping[str, Any]) -> tuple[list[dict[str, str]], list[Path]]:
    """Return the exact thirteen-addition, 391-input v67 successor."""

    if base.get("release_id") != "2026-07-21-open-seed-v67":
        raise SystemExit("v68 base must be exactly frozen v67")
    rows = base.get("curated_inputs")
    if not isinstance(rows, list) or len(rows) != 378:
        raise SystemExit("frozen v67 curated inventory differs")
    pins: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise SystemExit("frozen v67 curated row is invalid")
        source_path, digest = row["path"], row["sha256"]
        if (
            not isinstance(source_path, str)
            or not isinstance(digest, str)
            or source_path in pins
        ):
            raise SystemExit("frozen v67 curated inventory is invalid")
        pins[source_path] = digest

    _validate_additions()
    for source_path, (_, digest) in ADDITION_PINS.items():
        if source_path in pins:
            raise SystemExit(f"v68 addition already occurs in v67: {source_path}")
        pins[source_path] = digest
    if len(pins) != 391:
        raise SystemExit(f"expected 391 unique v68 inputs, found {len(pins)}")

    rows_out = [dict(row) for row in rows]
    rows_out.extend(
        {"path": source_path, "sha256": ADDITION_PINS[source_path][1]}
        for source_path in sorted(ADDITION_PINS)
    )
    if rows_out[:378] != rows or [row["path"] for row in rows_out[378:]] != sorted(
        ADDITION_PINS
    ):
        raise SystemExit("v68 did not preserve and canonically append inputs")
    paths: list[Path] = []
    for row in rows_out:
        source = ROOT / row["path"]
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"input must be an ordinary file: {row['path']}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise SystemExit(f"input mode must be 0644: {row['path']}")
        if sha256(source) != row["sha256"]:
            raise SystemExit(f"input hash differs: {row['path']}")
        paths.append(source)
    return rows_out, paths


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in base["curated_inputs"]:
        source = ROOT / row["path"]
        if sha256(source) != row["sha256"]:
            raise SystemExit(f"frozen v67 source hash differs: {row['path']}")
        paths.append(source)
    return paths


def _import_curated(connection: sqlite3.Connection, source: Path) -> object:
    document = json.loads(source.read_text(encoding="utf-8"))
    timestamps = {item["retrieved_at"] for item in document["evidence"]}
    if document["schema_version"] == "1.0":
        if len(timestamps) != 1:
            raise SystemExit(f"schema 1.0 source has multiple timestamps: {source.name}")
        return CuratedOfficialSourceAdapter().import_file(
            connection, source, retrieved_at=next(iter(timestamps))
        )
    if document["schema_version"] == "1.1":
        return CuratedOfficialSourceAdapterV11().import_file(
            connection, source, recorded_at=V11_RECORDED_AT
        )
    raise SystemExit(f"unsupported curated schema: {source.name}")


def _populate_database(
    base: Mapping[str, Any], paths: list[Path], sqlite_path: Path
) -> sqlite3.Connection:
    connection, _ = initialize(sqlite_path)
    epoch = base["epoch_capture"]
    result = EpochAIAdapter().import_file(
        connection,
        ROOT / epoch["archive"],
        map_html=ROOT / epoch["map"],
        retrieved_at=epoch["retrieved_at"],
        as_of_date=EPOCH_AS_OF,
    )
    if json.loads(json.dumps(asdict(result))) != base["expected_epoch_result"]:
        connection.close()
        raise SystemExit("frozen Epoch import result differs from v67")
    try:
        for source in paths:
            imported = _import_curated(connection, source)
            if getattr(imported, "warnings"):
                raise SystemExit(f"curated import warnings for {source.name}")
        errors = validate_database(connection)
        if errors:
            raise SystemExit("fresh database validation failed: " + "; ".join(errors))
        return connection
    except Exception:
        connection.close()
        raise


def _semantic_state(
    connection: sqlite3.Connection, stable_keys: tuple[str, ...]
) -> dict[str, tuple[tuple[Any, ...], ...]]:
    placeholders = ",".join("?" for _ in stable_keys)
    queries = {
        "entities": f"""
            SELECT stable_key, kind, created_from_evidence_id
            FROM entities WHERE stable_key IN ({placeholders})
        """,
        "snapshots": f"""
            SELECT entities.stable_key, name, latitude, longitude, geometry_json,
                   tags_json, evidence_id, as_of_date, valid_to_date, method, confidence
            FROM entity_snapshots JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "lifecycle": f"""
            SELECT entities.stable_key, status, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM lifecycle_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "capacity": f"""
            SELECT entities.stable_key, metric, stage, unit, low, base, high,
                   method, confidence, evidence_id, as_of_date, target_date,
                   valid_to_date, notes
            FROM capacity_estimates JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "models": f"""
            SELECT entities.stable_key, operating_model, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM operating_model_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "workloads": f"""
            SELECT entities.stable_key, workload, evidence_id, as_of_date,
                   valid_to_date, method, confidence, notes
            FROM workload_observations JOIN entities ON entities.id = entity_id
            WHERE entities.stable_key IN ({placeholders})
        """,
        "projects": f"""
            SELECT project_entity.stable_key, target_entity.stable_key
            FROM projects
            JOIN entities AS project_entity ON project_entity.id = projects.entity_id
            JOIN entities AS target_entity ON target_entity.id = projects.target_entity_id
            WHERE project_entity.stable_key IN ({placeholders})
        """,
    }
    return {
        name: tuple(sorted((tuple(row) for row in connection.execute(query, stable_keys)), key=repr))
        for name, query in queries.items()
    }


def _validate_prior_semantics(
    connection: sqlite3.Connection, base: Mapping[str, Any]
) -> None:
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v68-base-compare-", dir="/private/tmp"
    ) as temporary:
        base_connection = _populate_database(
            base, _base_paths(base), Path(temporary) / "v67.sqlite"
        )
        try:
            base_keys = tuple(
                row[0]
                for row in base_connection.execute(
                    "SELECT stable_key FROM entities ORDER BY stable_key"
                )
            )
            if len(base_keys) != 783:
                raise SystemExit("frozen v67 identity count differs")
            if _semantic_state(connection, base_keys) != _semantic_state(
                base_connection, base_keys
            ):
                raise SystemExit("v68 changed a prior semantic entity row")
            base_evidence = {
                row[0]: tuple(row[1:])
                for row in base_connection.execute("SELECT * FROM evidence")
            }
            current_evidence = {
                row[0]: tuple(row[1:]) for row in connection.execute("SELECT * FROM evidence")
            }
            if any(current_evidence.get(key) != value for key, value in base_evidence.items()):
                raise SystemExit("v68 changed a prior evidence row")
        finally:
            base_connection.close()


def _validate_database_contract(connection: sqlite3.Connection) -> None:
    expected = {
        "entities": 806,
        "evidence": 628,
        "lifecycle_observations": 472,
        "capacity_estimates": 531,
        "entity_snapshots": 826,
        "operating_model_observations": 56,
        "workload_observations": 128,
    }
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected
    }
    if counts != expected:
        raise SystemExit(f"fresh v68 database projection differs: {counts}")

    keys = tuple(sorted(ADDED_ENTITY_KEYS))
    placeholders = ",".join("?" for _ in keys)
    entity_rows = connection.execute(
        f"SELECT stable_key, kind FROM entities WHERE stable_key IN ({placeholders})",
        keys,
    ).fetchall()
    if {row[0] for row in entity_rows} != ADDED_ENTITY_KEYS:
        raise SystemExit("v68 added identity set differs")
    if {row[0] for row in entity_rows if row[1] == "project"} != ADDED_PROJECT_KEYS:
        raise SystemExit("v68 added project set differs")

    lifecycle = connection.execute(
        f"""
        SELECT entities.stable_key, status, as_of_date
        FROM lifecycle_observations JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        ORDER BY entities.stable_key, as_of_date
        """,
        keys,
    ).fetchall()
    if len(lifecycle) != 13:
        raise SystemExit("v68 lifecycle database delta differs")
    capacity = connection.execute(
        f"""
        SELECT entities.stable_key, metric, stage, base, as_of_date
        FROM capacity_estimates JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    if {tuple(row) for row in capacity} != CAPACITY_CONTRACT:
        raise SystemExit("v68 capacity database delta differs")
    workloads = connection.execute(
        f"""
        SELECT entities.stable_key, workload, as_of_date, method
        FROM workload_observations JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    if {tuple(row) for row in workloads} != WORKLOAD_CONTRACT:
        raise SystemExit("v68 workload database delta differs")
    models = connection.execute(
        f"""
        SELECT COUNT(*) FROM operating_model_observations
        JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchone()[0]
    if models:
        raise SystemExit("v68 additions gained an operating-model row")

    snapshots = connection.execute(
        f"""
        SELECT entities.stable_key, latitude, longitude, geometry_json, method
        FROM entity_snapshots JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key IN ({placeholders})
        """,
        keys,
    ).fetchall()
    coordinate_rows = {
        row[0]: (row[1], row[2], row[3], row[4])
        for row in snapshots
        if row[1] is not None or row[2] is not None or row[3] is not None
    }
    if coordinate_rows or set(coordinate_rows) != ADDED_COORDINATE_KEYS:
        raise SystemExit(f"v68 coordinate-free addition boundary differs: {coordinate_rows}")
    shared_snapshot_count = connection.execute(
        """
        SELECT COUNT(*) FROM entity_snapshots
        JOIN entities ON entities.id = entity_id
        WHERE entities.stable_key = ?
        """,
        (SHARED_CAMPUS_KEY,),
    ).fetchone()[0]
    if shared_snapshot_count != 1:
        raise SystemExit("v68 shared Tambore campus did not deduplicate exactly once")


def _build_database(base: Mapping[str, Any], paths: list[Path], sqlite_path: Path):
    connection = _populate_database(base, paths, sqlite_path)
    try:
        _validate_database_contract(connection)
        _validate_prior_semantics(connection, base)
        return connection
    except Exception:
        connection.close()
        raise


def augment_release_documents(
    documents: Mapping[str, str], *, as_of: str
) -> dict[str, str]:
    """Add the release-day last-observed carrier and bind it into the manifest."""

    output = dict(documents)
    if FRESHNESS_FILENAME in output:
        raise RuntimeError("freshness filename already exists")
    freshness = build_freshness_csv(output["entities.csv"], as_of=as_of)
    output[FRESHNESS_FILENAME] = freshness
    readme = output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    output["README.md"] = readme
    manifest = json.loads(output["manifest.json"])
    manifest["files"]["README.md"] = {
        "bytes": len(readme.encode("utf-8")),
        "sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
    }
    manifest["files"][FRESHNESS_FILENAME] = {
        "bytes": len(freshness.encode("utf-8")),
        "sha256": hashlib.sha256(freshness.encode("utf-8")).hexdigest(),
    }
    freshness_rows = list(csv.DictReader(io.StringIO(freshness)))
    manifest["current_status_inferred"] = False
    manifest["lifecycle_freshness_records"] = len(freshness_rows)
    manifest["lifecycle_status_semantics"] = "last_observed"
    output["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return output


def _write_augmented_release(connection: sqlite3.Connection, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
        publication_contract_version=4,
    )
    for filename, text in augment_release_documents(documents, as_of=AS_OF).items():
        (output / filename).write_text(text, encoding="utf-8")


def _csv_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return Counter(tuple(row.items()) for row in csv.DictReader(stream))


def _counter_hash(counter: Counter[tuple[tuple[str, str], ...]]) -> str:
    rows = [dict(packed) for packed in counter.elements()]
    rows.sort(
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    )
    raw = (
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rows_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row[key]: row for row in csv.DictReader(stream)}


def _validate_release_delta(stage: Path) -> None:
    for filename, expected in CSV_DELTA_CONTRACT.items():
        before = _csv_counter(BASE_RELEASE / filename)
        after = _csv_counter(stage / filename)
        common = before & after
        added = after - common
        removed = before - common
        actual = (
            sum(common.values()),
            sum(added.values()),
            _counter_hash(added),
            sum(removed.values()),
            _counter_hash(removed),
        )
        if actual != expected:
            raise SystemExit(f"fresh v68 CSV delta differs: {filename}: {actual}")

    before_entities = _rows_by_key(BASE_RELEASE / "entities.csv", "stable_key")
    after_entities = _rows_by_key(stage / "entities.csv", "stable_key")
    if set(after_entities) - set(before_entities) != ADDED_ENTITY_KEYS:
        raise SystemExit("v68 public added entity set differs")
    if set(before_entities) - set(after_entities):
        raise SystemExit("v68 removed a prior entity")
    if any(before_entities[key] != after_entities[key] for key in before_entities):
        raise SystemExit("v68 changed a prior entity/claim/snapshot row")

    if (stage / "resolution_candidates.csv").read_bytes() != (
        BASE_RELEASE / "resolution_candidates.csv"
    ).read_bytes() or (stage / "resolution_candidates.json").read_bytes() != (
        BASE_RELEASE / "resolution_candidates.json"
    ).read_bytes():
        raise SystemExit("v68 changed a resolution advisory")


def _validate_freshness(stage: Path) -> None:
    before = _rows_by_key(BASE_RELEASE / FRESHNESS_FILENAME, "stable_key")
    after = _rows_by_key(stage / FRESHNESS_FILENAME, "stable_key")
    if len(after) != 456 or tuple(next(iter(after.values()))) != FRESHNESS_FIELDS:
        raise SystemExit(f"fresh v68 freshness shape differs: {len(after)}")
    if set(after) - set(before) != set(LIFECYCLE_WINNERS):
        raise SystemExit("v68 added freshness identity set differs")
    if set(before) - set(after):
        raise SystemExit("v68 removed a prior freshness row")
    class_transitions: dict[str, tuple[str, str]] = {}
    for stable_key, old in before.items():
        new = after[stable_key]
        for field in old:
            if old[field] != new[field]:
                raise SystemExit(f"v68 changed prior freshness semantics: {stable_key}")
        if new["freshness_class"] != old["freshness_class"]:
            class_transitions[stable_key] = (
                old["freshness_class"],
                new["freshness_class"],
            )
    if class_transitions != FRESHNESS_CLASS_TRANSITION:
        raise SystemExit(
            f"v68 inherited freshness-class transition differs: {class_transitions}"
        )
    for stable_key, (status, observed) in LIFECYCLE_WINNERS.items():
        row = after[stable_key]
        if (
            row["last_observed_status"] != status
            or row["last_observed_status_as_of"] != observed
        ):
            raise SystemExit(f"v68 last-observed winner differs: {stable_key}")
    if {
        key: after[key]["last_observed_status_as_of"]
        for key in DATED_HISTORICAL_PROJECT_KEYS
    } != {
        "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center": "2026-06-30",
        "curated:firebird-ai-center-hrazdan-site:current-center-development": "2026-06-05",
        "curated:harch-intelligence-dakhla-campus:initial-development": "2026-03-15",
    }:
        raise SystemExit("v68 dated historical lifecycle boundary differs")
    if any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in after.values()
    ):
        raise SystemExit("v68 freshness rows infer current construction")
    classes = Counter(row["freshness_class"] for row in after.values())
    if classes != {
        "recent_0_90_days": 236,
        "aging_91_365_days": 191,
        "stale_over_365_days": 29,
    }:
        raise SystemExit(f"v68 freshness distribution differs: {classes}")


def _validate_release_facts(stage: Path) -> None:
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "campuses_total": 425,
        "campuses_with_coordinates": 128,
        "capacity_estimates_current": 530,
        "construction_pipeline_records": 414,
        "construction_source_signals": 316,
        "entities_total": 806,
        "entities_with_coordinates": 183,
        "evidence_total": 628,
        "lifecycle_observations_current": 456,
        "projects_total": 381,
        "recorded_at": RECORDED_AT,
    }
    actual = {key: summary.get(key) for key in expected}
    if actual != expected:
        raise SystemExit(f"fresh v68 summary facts differ: {actual}")
    if summary["entities_by_status"] != {
        "announced": 6,
        "civil_works": 3,
        "commissioning": 2,
        "expansion": 29,
        "foundations": 2,
        "mep_electrical": 19,
        "operational": 42,
        "permitted": 3,
        "proposed": 2,
        "shell": 28,
        "site_control": 1,
        "site_preparation": 12,
        "under_construction": 307,
    }:
        raise SystemExit("fresh v68 status summary differs")
    if summary["capacity_estimates_by_metric"].get("critical_it_mw") != 265:
        raise SystemExit("fresh v68 critical-IT count differs")
    if summary["capacity_estimates_by_metric"].get("gross_facility_mw") != 133:
        raise SystemExit("fresh v68 gross-facility count differs")
    if summary["capacity_estimates_by_stage"].get("planned") != 155:
        raise SystemExit("fresh v68 planned-capacity count differs")
    if summary["capacity_estimates_by_stage"].get("design") != 15:
        raise SystemExit("fresh v68 design-capacity count differs")

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    expected_manifest = {
        "entities": 806,
        "evidence_records": 507,
        "capacity_estimates": 530,
        "construction_pipeline_records": 414,
        "construction_source_signals": 316,
        "resolution_candidates": 6,
        "lifecycle_freshness_records": 456,
        "lifecycle_status_semantics": "last_observed",
        "current_status_inferred": False,
    }
    actual_manifest = {key: manifest.get(key) for key in expected_manifest}
    if actual_manifest != expected_manifest:
        raise SystemExit(f"fresh v68 manifest facts differ: {actual_manifest}")
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != (
        NEW_SOURCE_FAMILIES
    ):
        raise SystemExit("fresh v68 source-family delta differs")
    if set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise SystemExit("fresh v68 removed a source family")
    if len(manifest["source_families"]) != 284:
        raise SystemExit("fresh v68 source-family count differs")
    if len(list(stage.iterdir())) != 14:
        raise SystemExit("fresh v68 release must contain exactly 14 files")
    _validate_freshness(stage)


def _ordinary_file(path: Path, label: str) -> bytes:
    if not path.is_file() or path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _guard_state() -> dict[str, Any]:
    artifacts = _validate_artifact_lineage()
    additions: dict[str, tuple[int, str]] = {}
    for relative, pin in ADDITION_PINS.items():
        source = ROOT / relative
        additions[relative] = (source.stat().st_size, sha256(source))
        if additions[relative] != pin:
            raise SystemExit(f"v68 addition pin differs: {relative}")
    return {
        "base_definition": sha256(BASE_DEFINITION),
        "base_manifest": sha256(BASE_RELEASE / "manifest.json"),
        "base_tree": tree_digest(BASE_RELEASE),
        "discovery_artifacts": artifacts,
        "additions": additions,
    }


def _validate_definition(document: Mapping[str, Any], base: Mapping[str, Any]) -> None:
    if set(document) != set(base):
        raise ValueError("v68 definition schema differs from v67")
    if document.get("release_id") != RELEASE_ID:
        raise ValueError("release_id must identify frozen v68")
    if document.get("build") != {"as_of": AS_OF, "recorded_at": RECORDED_AT}:
        raise ValueError("v68 build timestamp contract differs")
    if document.get("publication_contract_version") != 4:
        raise ValueError("v68 publication contract differs")
    if document.get("freshness_contract") != freshness_contract():
        raise ValueError("v68 freshness contract differs")
    for key in ("epoch_capture", "expected_epoch_result", "schema_version", "scope"):
        if document.get(key) != base.get(key):
            raise ValueError(f"v68 inherited definition field differs: {key}")


def validate_open_seed_v68(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
) -> dict[str, Any]:
    """Validate exact adjacency, frozen bytes, and deterministic offline replay."""

    if replay_count != 2:
        raise ValueError("v68 requires exactly two offline replays")
    guard = _guard_state()
    if (
        guard["base_definition"] != BASE_DEFINITION_SHA256
        or guard["base_manifest"] != BASE_MANIFEST_SHA256
        or guard["base_tree"] != BASE_TREE_SHA256
    ):
        raise ValueError("accepted v67 base pin differs")
    base = json.loads(_ordinary_file(BASE_DEFINITION, "v67 definition"))
    raw = _ordinary_file(definition_path, "v68 definition")
    document = json.loads(raw)
    if raw != canonical_json(document):
        raise ValueError("v68 definition JSON is not canonical")
    _validate_definition(document, base)
    selected_rows, paths = selected_inputs(base)
    if document.get("curated_inputs") != selected_rows:
        raise ValueError("v68 selected input inventory differs")

    if not release_path.is_dir() or release_path.is_symlink():
        raise ValueError("v68 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise ValueError("v68 release directory mode must be 0555")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise ValueError("v68 release contains a symlink or non-file entry")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise ValueError("v68 release file mode must be 0444")

    manifest_raw = _ordinary_file(release_path / "manifest.json", "v68 manifest")
    manifest = json.loads(manifest_raw)
    if hashlib.sha256(manifest_raw).hexdigest() != document["expected_release"].get(
        "manifest_sha256"
    ):
        raise ValueError("v68 release manifest hash differs")
    expected_release = {
        key: value
        for key, value in document["expected_release"].items()
        if key != "manifest_sha256"
    }
    actual_release = {key: value for key, value in manifest.items() if key != "files"}
    if actual_release != expected_release:
        raise ValueError("v68 expected release facts differ")
    expected_names = set(manifest["files"]) | {"manifest.json"}
    if set(release_files) != expected_names:
        raise ValueError("v68 release file inventory differs")
    for filename, pin in manifest["files"].items():
        payload = _ordinary_file(release_path / filename, filename)
        if len(payload) != pin["bytes"] or hashlib.sha256(payload).hexdigest() != pin[
            "sha256"
        ]:
            raise ValueError(f"v68 release file pin differs: {filename}")
    _validate_release_delta(release_path)
    _validate_release_facts(release_path)

    summary = json.loads((release_path / "summary.json").read_text(encoding="utf-8"))
    if {
        key: summary[key] for key in document["expected_summary"]
    } != document["expected_summary"]:
        raise ValueError("v68 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v68-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            temporary_path = Path(temporary)
            connection = _build_database(
                base, paths, temporary_path / "atlas.sqlite"
            )
            try:
                replay_release = temporary_path / "release"
                _write_augmented_release(connection, replay_release)
            finally:
                connection.close()
            _validate_release_delta(replay_release)
            _validate_release_facts(replay_release)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise ValueError("v68 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise ValueError(f"v68 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise ValueError("v68 validation mutated v67 or an accepted source")
    return manifest


def build_open_seed_v68() -> dict[str, object]:
    """Build and freeze v68 exactly once, refusing every publication collision."""

    guard = _guard_state()
    with publication_lock():
        if DEFINITION.exists() or DEFINITION.is_symlink():
            raise SystemExit(
                f"definition already exists; refusing overwrite: {DEFINITION}"
            )
        if RELEASE.exists() or RELEASE.is_symlink():
            raise SystemExit(f"release already exists; refusing overwrite: {RELEASE}")
        if guard["base_definition"] != BASE_DEFINITION_SHA256:
            raise SystemExit("accepted v67 definition hash differs")
        if guard["base_manifest"] != BASE_MANIFEST_SHA256:
            raise SystemExit("accepted v67 manifest hash differs")
        if guard["base_tree"] != BASE_TREE_SHA256:
            raise SystemExit("accepted v67 release tree differs")

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, paths = selected_inputs(base)
        staging_root = ROOT / ".staging"
        staging_root.mkdir(exist_ok=True)
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        release_stage.rmdir()
        definition_stage = DEFINITION.parent / f".{DEFINITION.name}.{os.getpid()}.tmp"
        published_release = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v68-db-", dir=staging_root
            ) as temporary:
                connection = _build_database(
                    base, paths, Path(temporary) / "atlas.sqlite"
                )
                try:
                    _write_augmented_release(connection, release_stage)
                    summary = summarize(
                        connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    )
                finally:
                    connection.close()

            _validate_release_delta(release_stage)
            _validate_release_facts(release_stage)
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            expected_summary = {key: summary[key] for key in base["expected_summary"]}
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": RECORDED_AT}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = expected_summary
            definition["freshness_contract"] = freshness_contract()
            definition["publication_contract_version"] = 4
            definition["release_id"] = RELEASE.name
            with definition_stage.open("xb") as stream:
                stream.write(canonical_json(definition))
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o644)

            for output in release_stage.iterdir():
                output.chmod(0o444)
            release_stage.chmod(0o555)
            validate_open_seed_v68(definition_stage, release_stage)
            promote_noreplace(release_stage, RELEASE)
            published_release = True
            promote_noreplace(definition_stage, DEFINITION)
            validate_open_seed_v68(DEFINITION, RELEASE)
        finally:
            if not published_release:
                discard_release_stage(release_stage)
            try:
                definition_stage.unlink()
            except FileNotFoundError:
                pass
    if _guard_state() != guard:
        raise SystemExit("v68 build mutated v67 or an accepted source")

    manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
    return {
        "definition": str(DEFINITION),
        "definition_sha256": sha256(DEFINITION),
        "manifest_sha256": sha256(RELEASE / "manifest.json"),
        "recorded_at": RECORDED_AT,
        "release": str(RELEASE),
        "release_tree_sha256": tree_digest(RELEASE),
        **{
            key: value
            for key, value in manifest.items()
            if key not in {"files", "source_families"}
        },
        "source_families": len(manifest["source_families"]),
    }


def main() -> int:
    print(json.dumps(build_open_seed_v68(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
