"""Build and publish the immutable official-coordinate assessment v5.

The assessment is deliberately separate from the accepted seed. It appends
coordinate evidence to three byte-pinned v73 curated records and leaves a
fourth record blocked. Raw response bodies remain in a private capture tree
and are preserved in Trash after atomic publication; repository artifacts
carry only hashes, metadata, and compact factual extractions.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from .external_captures import resolve_external_capture


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v5"
ARTIFACT_DIR = PUBLICATION_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = PUBLICATION_ROOT / f".{ARTIFACT_ID}.lock"
AS_OF_DATE = "2026-07-21"

CAPTURE_INPUT = Path("/private/tmp/coordinate-evidence.MctywO")
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/datacenter-atlas-coordinate-official-20260721-v5-MctywO"
)
CAPTURE_TOTAL_BYTES = 6_538_063
CAPTURE_TREE_SHA256 = (
    "0a0cc6dd755976590fea64b9d29e778159986ffb30a1bf0264376940eb4483d6"
)

BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
BASE_DEFINITION_BYTES = 88_004
BASE_DEFINITION_SHA256 = (
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d"
)
BASE_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v73/manifest.json"
BASE_MANIFEST_BYTES = 12_814
BASE_MANIFEST_SHA256 = (
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d"
)
PRIOR_COORDINATE_MANIFEST = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v4/manifest.json"
)
PRIOR_COORDINATE_MANIFEST_BYTES = 1_792
PRIOR_COORDINATE_MANIFEST_SHA256 = (
    "8bcd9842af00890e4820e2b011a9fa799a1c4d5c98b0a77c4dc874c79b4c04b8"
)
SOURCE_ARTIFACT_MANIFEST = (
    ROOT
    / "source_artifacts/global-official-builds-six-candidate-2026-07-21-v1"
    / "manifest.json"
)
SOURCE_ARTIFACT_MANIFEST_BYTES = 1_727
SOURCE_ARTIFACT_MANIFEST_SHA256 = (
    "20b0788dba18402cf1b6bb8874ec6cd66f86000ff85f620c7e0167bf7e1894cd"
)


class SiteCoordinateAssessmentV5Error(RuntimeError):
    """Raised when a v5 provenance, claim, or publication fuse fails closed."""


CAPTURE_FILES: dict[str, tuple[int, str, int, int]] = {
    "akashi_eco.body": (
        313_714,
        "de22fb8e3444bb0190c8eb91990a4537321729b294258f2729f79aaba4c2ffa7",
        1_784_645_753,
        1_784_645_757,
    ),
    "akashi_eco.headers": (
        298,
        "80b1187987efd3da7509bdbbb14d11ff7c8e990ba009f5ea21429b96b4c9fff2",
        1_784_645_752,
        1_784_645_753,
    ),
    "akashi_hearing.body": (
        5_609_010,
        "b181f73428e5287e5233f45f7a8da81da66c4de9ff46667a923f39f07fcd1ef4",
        1_784_645_758,
        1_784_645_761,
    ),
    "akashi_hearing.headers": (
        366,
        "e28001f46aaad8ba9c900450073125f14ee0e0d6962fafbe99e46e36403ff647",
        1_784_645_757,
        1_784_645_758,
    ),
    "bichuten_care.body": (
        141_835,
        "45e601838c265494e5816f4b41d5adb943b565f075ca6246d9b77baf85d50b73",
        1_784_645_764,
        1_784_645_765,
    ),
    "bichuten_care.headers": (
        536,
        "e9a0a6837391d1e834dd7155935997eaa25f81e65c92157aa9e5d2d17214aea4",
        1_784_645_763,
        1_784_645_764,
    ),
    "bichuten_ebps.body": (
        25_961,
        "8fe79c1ce1a24fa53f623e66ec8d92f16ec9f58c1ab54fbdcd505a5e320e2597",
        1_784_645_766,
        1_784_645_766,
    ),
    "bichuten_ebps.headers": (
        563,
        "fa008fd0c3a4638ae5c1824cafcb335d5558b37bb12f7cb235b9b1c611b296d9",
        1_784_645_765,
        1_784_645_766,
    ),
    "icatec_project.body": (
        49_455,
        "4691db5f0411aeaf05e5a131ffad1e8ae1a2b9f3c1777928c9e9f14efeabaf42",
        1_784_645_762,
        1_784_645_762,
    ),
    "icatec_project.headers": (
        1_238,
        "7a4fe8b8b76ce4cd85168765b1cafd582d15b2acfa33a72b0a4019838dc06822",
        1_784_645_761,
        1_784_645_762,
    ),
    "icatec_sedes.body": (
        117_632,
        "1f2b34ebeca900f66af27d30f180ee4ab164226027631229b99f308855d30c56",
        1_784_645_763,
        1_784_645_763,
    ),
    "icatec_sedes.headers": (
        1_601,
        "3da657599b0893ad2b868a68b1ec40135189bc94d4a6774bdb32fddf4935c410",
        1_784_645_762,
        1_784_645_763,
    ),
    "lvrtc_eis.body": (
        128_675,
        "91a933242a2d719ca70dce8539934cd86088c0eaf2f0b5943129797b3fe4631d",
        1_784_645_746,
        1_784_645_746,
    ),
    "lvrtc_eis.headers": (
        1_066,
        "b056892cc5bc4f287b48cb87a736133e6aab72a0f10d60bf51dabf7b868eca0a",
        1_784_645_745,
        1_784_645_746,
    ),
    "lvrtc_finances.body": (
        142_257,
        "1945125d13ec6cf2f825e6bfa9590a63d64f96d4adcda5c84e7114b033479a1e",
        1_784_645_749,
        1_784_645_750,
    ),
    "lvrtc_finances.headers": (
        1_050,
        "4006da430603a9aaf96c59b0078e457c0707f8051a4d5d05fc3f77d57d627679",
        1_784_645_746,
        1_784_645_749,
    ),
    "lvrtc_wfs.body": (
        2_187,
        "9f956cc7e9fd532156e7a093a047731507f29710996709854cf20d6365cf2f02",
        1_784_645_752,
        1_784_645_752,
    ),
    "lvrtc_wfs.headers": (
        619,
        "fa30e9dd3ee3b7ff99b6ea47347f476f6f9a16643b56c4c38a532d7b683a5c30",
        1_784_645_750,
        1_784_645_752,
    ),
}


COHORT: dict[str, tuple[int, str, str]] = {
    "curated-official-2026-07-21-akashi-astana-phase-1-current-build.json": (
        8_057,
        "7f93487075c06e359c8f41c264633393b64b731c4f5d89b4a804dc5476db2543",
        "accepted_official_same_parcel_substation_point",
    ),
    "curated-official-2026-07-21-bichuten-chovar-current-build.json": (
        5_339,
        "6c7b84b59da58cd5bcce44bff041578b22a243279db9e836bb6ce54c610ce1eb",
        "blocked_no_authoritative_coordinate",
    ),
    "curated-official-2026-07-21-icatec-ica-current-build.json": (
        7_745,
        "8a87e5271914fc351ff01576661e9e5f315ab783489c44cf75144c03451fa4e6",
        "accepted_official_destination_point",
    ),
    "curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-current-build.json": (
        8_203,
        "8653286bdfc853918125e1294483e9175a339cc44705422d68a9bd4709d27d9b",
        "accepted_official_cadastral_reference_point",
    ),
}


REQUESTS: dict[str, dict[str, Any]] = {
    "akashi_eco": {
        "url": "https://ecoportal.kz/Rubric/RubService/LoadFile/59205",
        "status": 200,
        "content_type": "application/pdf",
        "decision": "accepted_substation_point_and_same_parcel_bridge",
        "server_date": "2026-07-21T14:56:32Z",
        "server_date_used_as_retrieval_time": False,
    },
    "akashi_hearing": {
        "url": (
            "https://hearings.ndbecology.gov.kz/Disscusion/DisHearings/"
            "LoadFile/151666"
        ),
        "status": 200,
        "content_type": "application/pdf",
        "decision": "accepted_data_center_identity_and_same_parcel_context",
        "server_date": "2026-07-21T14:55:58Z",
        "server_date_used_as_retrieval_time": False,
    },
    "bichuten_care": {
        "url": (
            "https://www.careratingsnepal.com/upload/CompanyFiles/PR/"
            "202604100446_Bichuten_Data_Vault_Private_Limited_-_Bank_"
            "Facilities_Ratings_Assigned.pdf"
        ),
        "status": 200,
        "content_type": "application/pdf",
        "decision": "locality_only_chovar_06_kirtipur_no_parcel_or_address",
        "server_date": "2026-07-21T14:55:57Z",
        "server_date_used_as_retrieval_time": False,
    },
    "bichuten_ebps": {
        "url": "https://ebps.kirtipurmun.gov.np/Hom/BuildingPermit",
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "decision": "generic_municipal_page_no_bichuten_identity_bridge",
        "server_date": "2026-07-21T14:56:06Z",
        "server_date_used_as_retrieval_time": False,
    },
    "icatec_project": {
        "url": (
            "https://www.gob.pe/institucion/regionica/informes-publicaciones/"
            "5702750-proceso-de-seleccion-n-002-2024-ce-oxi-gore-ica-"
            "primera-convocatoria"
        ),
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "decision": "accepted_cui_and_sede_central_project_destination_bridge",
        "server_date": "2026-07-21T14:56:02Z",
        "server_date_used_as_retrieval_time": False,
    },
    "icatec_sedes": {
        "url": "https://www.gob.pe/institucion/regionica/sedes",
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "decision": "accepted_official_sede_central_destination_coordinate",
        "server_date": "2026-07-21T14:56:02Z",
        "server_date_used_as_retrieval_time": False,
    },
    "lvrtc_eis": {
        "url": "https://www.eis.gov.lv/EKEIS/supplier/Procurement/116514",
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "decision": "accepted_kurzeme_data_center_contract_site_bridge",
        "server_date": "2026-07-21T14:55:46Z",
        "server_date_used_as_retrieval_time": False,
    },
    "lvrtc_finances": {
        "url": "https://www.lvrtc.lv/par-lvrtc/finanses/",
        "status": 200,
        "content_type": "text/html; charset=UTF-8",
        "decision": "accepted_lvrtc_site_to_cadastral_parcel_bridge",
        "server_date": "2026-07-21T14:55:47Z",
        "server_date_used_as_retrieval_time": False,
    },
    "lvrtc_wfs": {
        "url": (
            "https://grafws.kadastrs.lv/geoserver/cp/wfs?service=WFS&"
            "version=2.0.0&request=GetFeature&typeNames=cp%3A"
            "CadastralParcel&outputFormat=application%2Fjson&"
            "CQL_FILTER=label%3D%2762740010343%27"
        ),
        "status": 200,
        "content_type": "application/json;charset=UTF-8",
        "decision": "accepted_vzd_parcel_reference_point",
        "server_date": "2026-07-21T14:55:51Z",
        "server_date_used_as_retrieval_time": False,
    },
}


ACCEPTED: dict[str, dict[str, Any]] = {
    "akashi": {
        "predecessor": (
            "curated-official-2026-07-21-akashi-astana-phase-1-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-akashi-astana-phase-1-current-build-"
            "coordinate-v5.json"
        ),
        "campus_key": "curated:akashi-astana-data-center-campus",
        "project_key": (
            "curated:akashi-astana-data-center-campus:phase-1-current-build"
        ),
        "changed_entities": ("campus", "project"),
        "latitude": 51.2067694444,
        "longitude": 71.4577083333,
        "horizontal_uncertainty_m": 500,
        "evidence_key": (
            "kazakhstan-akashi-same-parcel-substation-coordinate-"
            "captured-2026-07-21"
        ),
        "capture_stems": ("akashi_eco", "akashi_hearing"),
    },
    "icatec": {
        "predecessor": "curated-official-2026-07-21-icatec-ica-current-build.json",
        "successor": (
            "curated-official-2026-07-21-icatec-ica-current-build-coordinate-"
            "v5.json"
        ),
        "campus_key": "curated:icatec-ica-digital-transformation-data-center",
        "project_key": (
            "curated:icatec-ica-digital-transformation-data-center:"
            "four-storey-technology-center-build"
        ),
        "changed_entities": ("campus", "project"),
        "latitude": -14.075622,
        "longitude": -75.734798,
        "horizontal_uncertainty_m": 150,
        "evidence_key": (
            "peru-icatec-gore-ica-sede-central-destination-coordinate-"
            "captured-2026-07-21"
        ),
        "capture_stems": ("icatec_project", "icatec_sedes"),
    },
    "lvrtc": {
        "predecessor": (
            "curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-"
            "current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-lvrtc-pozitrons-kurzeme-"
            "current-build-coordinate-v5.json"
        ),
        "campus_key": "curated:lvrtc-pozitrons-kurzeme-data-center",
        "project_key": (
            "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build"
        ),
        "changed_entities": ("campus", "project"),
        "latitude": 56.9356302057,
        "longitude": 22.0132502617,
        "horizontal_uncertainty_m": 300,
        "evidence_key": (
            "latvia-lvrtc-pozitrons-vzd-parcel-reference-point-"
            "captured-2026-07-21"
        ),
        "capture_stems": ("lvrtc_eis", "lvrtc_finances", "lvrtc_wfs"),
    },
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SiteCoordinateAssessmentV5Error(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SiteCoordinateAssessmentV5Error(f"{label} is invalid") from error
    if parsed.microsecond:
        raise SiteCoordinateAssessmentV5Error(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _capture_root() -> Path:
    roots = [
        candidate
        for candidate in (CAPTURE_INPUT, CAPTURE_TRASH)
        if candidate.exists() or candidate.is_symlink()
    ]
    if len(roots) > 1:
        raise SiteCoordinateAssessmentV5Error(
            "exactly one private or preserved capture root must exist"
        )
    root = (
        roots[0]
        if roots
        else resolve_external_capture(CAPTURE_INPUT, CAPTURE_TRASH)
    )
    if root.is_symlink() or not root.is_dir():
        raise SiteCoordinateAssessmentV5Error(
            "capture root must be an ordinary directory"
        )
    return root


def _capture_rows(root: Path) -> list[dict[str, Any]]:
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise SiteCoordinateAssessmentV5Error("capture root mode differs")
    packaged_capture = root not in (CAPTURE_INPUT, CAPTURE_TRASH)
    entries = sorted(root.iterdir(), key=lambda candidate: candidate.name)
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise SiteCoordinateAssessmentV5Error("capture tree contains unsafe entries")
    if {entry.name for entry in entries} != set(CAPTURE_FILES):
        raise SiteCoordinateAssessmentV5Error("capture file inventory differs")
    closure = bytearray()
    rows: list[dict[str, Any]] = []
    total = 0
    for entry in entries:
        raw = entry.read_bytes()
        metadata = entry.stat(follow_symlinks=False)
        digest = _sha256(raw)
        expected_bytes, expected_sha256, expected_birth, expected_mtime = (
            CAPTURE_FILES[entry.name]
        )
        if (
            len(raw) != expected_bytes
            or digest != expected_sha256
            or int(metadata.st_mtime) != expected_mtime
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or (
                not packaged_capture
                and int(metadata.st_birthtime) != expected_birth
            )
        ):
            raise SiteCoordinateAssessmentV5Error(
                f"capture carrier differs: {entry.name}"
            )
        total += len(raw)
        closure.extend(f"{digest}  ./{entry.name}\n".encode())
        rows.append(
            {
                "capture_name": entry.name,
                "bytes": len(raw),
                "sha256": digest,
                "birth_epoch": expected_birth,
                "mtime_epoch": int(metadata.st_mtime),
            }
        )
    if total != CAPTURE_TOTAL_BYTES or _sha256(bytes(closure)) != CAPTURE_TREE_SHA256:
        raise SiteCoordinateAssessmentV5Error("capture byte closure differs")
    return rows


def _verify_lineage_and_cohort() -> dict[str, dict[str, Any]]:
    pins = (
        (
            BASE_DEFINITION,
            BASE_DEFINITION_BYTES,
            BASE_DEFINITION_SHA256,
            "accepted v73 definition",
        ),
        (
            BASE_MANIFEST,
            BASE_MANIFEST_BYTES,
            BASE_MANIFEST_SHA256,
            "accepted v73 manifest",
        ),
        (
            PRIOR_COORDINATE_MANIFEST,
            PRIOR_COORDINATE_MANIFEST_BYTES,
            PRIOR_COORDINATE_MANIFEST_SHA256,
            "accepted coordinate v4 manifest",
        ),
        (
            SOURCE_ARTIFACT_MANIFEST,
            SOURCE_ARTIFACT_MANIFEST_BYTES,
            SOURCE_ARTIFACT_MANIFEST_SHA256,
            "six-candidate source artifact manifest",
        ),
    )
    for filename, expected_bytes, expected_sha256, label in pins:
        raw = filename.read_bytes()
        if (len(raw), _sha256(raw)) != (expected_bytes, expected_sha256):
            raise SiteCoordinateAssessmentV5Error(f"{label} drifted")

    selected = {
        row["path"]: row["sha256"]
        for row in json.loads(BASE_DEFINITION.read_bytes())["curated_inputs"]
    }
    documents: dict[str, dict[str, Any]] = {}
    for name, (expected_bytes, expected_sha256, _disposition) in COHORT.items():
        filename = ROOT / "sources" / name
        raw = filename.read_bytes()
        if (
            filename.is_symlink()
            or stat.S_IMODE(filename.stat().st_mode) != 0o644
            or (len(raw), _sha256(raw)) != (expected_bytes, expected_sha256)
            or selected.get(f"sources/{name}") != expected_sha256
        ):
            raise SiteCoordinateAssessmentV5Error(f"v73 cohort pin differs: {name}")
        document = json.loads(raw)
        if document.get("schema_version") != "1.1":
            raise SiteCoordinateAssessmentV5Error(f"cohort schema differs: {name}")
        if document["campus"].get("coordinates") is not None or document[
            "project"
        ].get("coordinates") is not None:
            raise SiteCoordinateAssessmentV5Error(
                f"coordinate predecessor was already located: {name}"
            )
        documents[name] = document
    return documents


def _carrier(rows: Mapping[str, Mapping[str, Any]], name: str) -> dict[str, Any]:
    try:
        return dict(rows[name])
    except KeyError as error:
        raise SiteCoordinateAssessmentV5Error(
            f"capture carrier missing: {name}"
        ) from error


def _captured(
    specification: Mapping[str, Any], rows: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    return {
        stem: {
            suffix: _carrier(rows, f"{stem}.{suffix}")
            for suffix in ("body", "headers")
        }
        for stem in specification["capture_stems"]
    }


def _local_retrieved_at(
    captured: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> str:
    epoch = max(
        carrier["mtime_epoch"]
        for source in captured.values()
        for carrier in source.values()
    )
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _dms(degrees: str, minutes: str, seconds: str) -> float:
    value = Decimal(degrees) + Decimal(minutes) / 60 + Decimal(seconds) / 3600
    return float(value.quantize(Decimal("0.0000000001")))


def _validate_coordinate_extractions(capture: Path) -> None:
    lvrtc_eis = (capture / "lvrtc_eis.body").read_text(encoding="utf-8")
    lvrtc_finances = (capture / "lvrtc_finances.body").read_text(encoding="utf-8")
    lvrtc_wfs = json.loads((capture / "lvrtc_wfs.body").read_bytes())
    if not all(
        marker in lvrtc_eis
        for marker in (
            "Kurzemes datu centra projektēšana",
            "Kuldīgas Raidstacija",
            "Latvijas Valsts radio un televizijas centrs",
        )
    ):
        raise SiteCoordinateAssessmentV5Error("LVRTC procurement bridge differs")
    if not all(
        marker in lvrtc_finances
        for marker in ("Kuldīgas Raidstacija", "62740010343")
    ):
        raise SiteCoordinateAssessmentV5Error("LVRTC cadastral bridge differs")
    features = lvrtc_wfs.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise SiteCoordinateAssessmentV5Error("VZD parcel response differs")
    feature = features[0]
    properties = feature.get("properties", {})
    reference = properties.get("referencePoint", {})
    if (
        feature.get("id") != "CP62740010343"
        or properties.get("label") != "62740010343"
        or reference.get("coordinates") != [22.0132502617, 56.9356302057]
        or lvrtc_wfs.get("crs", {}).get("properties", {}).get("name")
        != "urn:ogc:def:crs:EPSG::4258"
    ):
        raise SiteCoordinateAssessmentV5Error("VZD reference point differs")

    if (_dms("51", "12", "24.37"), _dms("71", "27", "27.75")) != (
        51.2067694444,
        71.4577083333,
    ):
        raise SiteCoordinateAssessmentV5Error("Akashi DMS conversion differs")
    for name in ("akashi_eco.body", "akashi_hearing.body"):
        if not (capture / name).read_bytes().startswith(b"%PDF-"):
            raise SiteCoordinateAssessmentV5Error(f"Akashi carrier differs: {name}")

    project_html = html.unescape(
        (capture / "icatec_project.body").read_text(encoding="utf-8")
    )
    sedes_html = html.unescape(
        (capture / "icatec_sedes.body").read_text(encoding="utf-8")
    )
    if not all(
        marker in project_html
        for marker in ("SEDE CENTRAL DEL GOBIERNO REGIONAL DE ICA", "CUI: 2643810")
    ):
        raise SiteCoordinateAssessmentV5Error("ICATEC project bridge differs")
    if not all(
        marker in sedes_html
        for marker in (
            "Sede Central",
            "Av. Cutervo N°. 920",
            "daddr=-14.075622,-75.734798",
        )
    ):
        raise SiteCoordinateAssessmentV5Error("ICATEC destination point differs")

    bichuten = (capture / "bichuten_ebps.body").read_text(encoding="utf-8")
    if "Kirtipur e-BPS" not in bichuten or re.search(
        r"Bichuten|Chovar-?06", bichuten, re.IGNORECASE
    ):
        raise SiteCoordinateAssessmentV5Error("Bichuten municipal block differs")


def _evidence(
    label: str,
    specification: Mapping[str, Any],
    capture_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    captured = _captured(specification, capture_rows)
    common_metadata = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "capture_carriers": captured,
        "retrieval_time_basis": (
            "latest whole-second local filesystem mtime among the exact body and "
            "header carriers, sampled after each request completed; server Date "
            "headers are retained as metadata but are not retrieval timestamps"
        ),
        "stored_coordinate": {
            "latitude": specification["latitude"],
            "longitude": specification["longitude"],
        },
        "coordinate_reference_system": "EPSG:4326",
        "coordinate_method": "authoritative_site_plan",
        "horizontal_uncertainty_m": specification["horizontal_uncertainty_m"],
        "uncertainty_scope": (
            "Conservative analyst envelope for a site representative point; not "
            "publisher accuracy metadata and not a building footprint."
        ),
        "claim_guardrail": (
            "This evidence changes only campus and project coordinate snapshot "
            "fields. It adds no identity, lifecycle, current-status, owner, "
            "operator, tenant, operating-model, workload, capacity, load, "
            "generation, consumption, energy, or PUE claim."
        ),
        "raw_capture_guardrail": (
            "Exact response bodies and headers are hash-bound, kept outside the "
            "repository, and not redistributed."
        ),
        "osm_guardrail": (
            "No OpenStreetMap-derived point, geometry, address, or identity bridge "
            "was consumed, and this record is not an OSM-to-official-importer route."
        ),
    }
    retrieved_at = _local_retrieved_at(captured)
    if label == "lvrtc":
        body = captured["lvrtc_wfs"]["body"]
        return {
            "key": specification["evidence_key"],
            "kind": "government_record",
            "title": (
                "Latvian State Land Service parcel 62740010343 reference point "
                "with LVRTC Pozitrons site bridge"
            ),
            "source_url": REQUESTS["lvrtc_wfs"]["url"],
            "publisher": "Valsts zemes dienests",
            "source_family": "latvia_vzd_cadastre_and_lvrtc_site_records",
            "published_at": None,
            "retrieved_at": retrieved_at,
            "license": "CC-BY-4.0",
            "attribution": (
                "Valsts zemes dienests (State Land Service of Latvia), CC BY 4.0"
            ),
            "excerpt": (
                "LVRTC's procurement and property disclosures bridge the Kurzeme "
                "data-centre site to Kuldīgas Raidstacija and cadastral parcel "
                "62740010343; the official VZD WFS reports that parcel's reference "
                "point."
            ),
            "content_hash": body["sha256"],
            "metadata": {
                **common_metadata,
                "content_hash_scope": (
                    f"SHA-256 of the exact {body['bytes']}-byte VZD WFS response body"
                ),
                "content_hash_verification": "fetched_bytes_sha256",
                "supporting_source_urls": [
                    REQUESTS["lvrtc_eis"]["url"],
                    REQUESTS["lvrtc_finances"]["url"],
                ],
                "identity_chain": (
                    "The EIS procurement names LVRTC's Kurzeme data centre at "
                    "Kuldīgas Raidstacija; LVRTC's official property table assigns "
                    "that site cadastral parcel 62740010343; the VZD WFS returns "
                    "exactly that parcel."
                ),
                "coordinate_derivation": {
                    "kind": "source_reported_cadastral_reference_point",
                    "parcel_label": "62740010343",
                    "source_crs": "EPSG:4258",
                    "source_longitude_decimal_text": "22.0132502617",
                    "source_latitude_decimal_text": "56.9356302057",
                    "stored_without_numeric_shift": True,
                    "crs_scope": (
                        "The ETRS89 numeric point is stored as longitude/latitude; "
                        "any frame difference is immaterial within the 300 m "
                        "representative-point envelope."
                    ),
                },
                "representative_point_scope": (
                    "Publisher-reported cadastral reference point for the 113,200 "
                    "square-metre parcel; not a building centroid or footprint."
                ),
                "license_scope": (
                    "CC BY 4.0 applies to the VZD spatial-data response. No license "
                    "is asserted for the supporting EIS or LVRTC page bytes, which "
                    "are not redistributed."
                ),
            },
        }
    if label == "akashi":
        body = captured["akashi_eco"]["body"]
        return {
            "key": specification["evidence_key"],
            "kind": "government_record",
            "title": (
                "Akashi 110/10 kV substation center within Astana cadastral parcel "
                "21-324-059-695"
            ),
            "source_url": REQUESTS["akashi_eco"]["url"],
            "publisher": "Unified Environmental Portal of Kazakhstan",
            "source_family": "kazakhstan_environmental_project_records",
            "published_at": None,
            "retrieved_at": retrieved_at,
            "license": "no-license-stated-for-compact-factual-extraction",
            "attribution": "Unified Environmental Portal of Kazakhstan",
            "excerpt": (
                "The official notice locates the Akashi 110/10 kV substation at a "
                "reported DMS point inside the 11.0587-hectare parcel designated "
                "for a retail and data-processing centre; the detailed hearing "
                "file identifies the data-centre project on the same parcel."
            ),
            "content_hash": body["sha256"],
            "metadata": {
                **common_metadata,
                "content_hash_scope": (
                    f"SHA-256 of the exact {body['bytes']}-byte official PDF body"
                ),
                "content_hash_verification": "fetched_bytes_sha256",
                "supporting_source_urls": [REQUESTS["akashi_hearing"]["url"]],
                "identity_chain": (
                    "The environmental notice names PS Akashi, cadastral parcel "
                    "21-324-059-695, and the parcel's data-processing-centre use; "
                    "the detailed official design file identifies a data centre "
                    "and the same parcel."
                ),
                "coordinate_derivation": {
                    "kind": "source_reported_dms_point_converted_to_decimal_degrees",
                    "source_latitude_dms": "51°12'24.37\"N",
                    "source_longitude_dms": "71°27'27.75\"E",
                    "decimal_formula": "degrees + minutes/60 + seconds/3600",
                    "stored_decimal_places": 10,
                    "cadastral_parcel": "21-324-059-695",
                    "parcel_area_hectares_as_reported": 11.0587,
                },
                "representative_point_scope": (
                    "Center of the planned 110/10 kV substation within the same "
                    "data-centre parcel. It is a campus/AOI lead, not a data-hall "
                    "centroid, footprint, energized-load observation, or proof of "
                    "substation completion."
                ),
                "rights_scope": (
                    "Only hashes, source URLs, and compact factual extraction are "
                    "retained; neither official PDF is redistributed."
                ),
            },
        }
    if label == "icatec":
        body = captured["icatec_sedes"]["body"]
        return {
            "key": specification["evidence_key"],
            "kind": "government_record",
            "title": (
                "Gobierno Regional de Ica Sede Central destination point for "
                "ICATEC CUI 2643810"
            ),
            "source_url": REQUESTS["icatec_sedes"]["url"],
            "publisher": "Gobierno Regional de Ica",
            "source_family": "peru_gob_pe_region_ica_records",
            "published_at": None,
            "retrieved_at": retrieved_at,
            "license": "no-license-stated-for-compact-factual-extraction",
            "attribution": "Gobierno Regional de Ica",
            "excerpt": (
                "The official procurement page places ICATEC CUI 2643810 at the "
                "regional government's Sede Central, whose official branch-office "
                "page publishes a destination coordinate and street address."
            ),
            "content_hash": body["sha256"],
            "metadata": {
                **common_metadata,
                "content_hash_scope": (
                    f"SHA-256 of the exact {body['bytes']}-byte official page body"
                ),
                "content_hash_verification": "fetched_bytes_sha256",
                "supporting_source_urls": [REQUESTS["icatec_project"]["url"]],
                "identity_chain": (
                    "The official selection page identifies CUI 2643810 as the "
                    "digital-transformation and data-processing project of the "
                    "Gobierno Regional de Ica Sede Central; the same government's "
                    "Sedes page publishes the Sede Central destination."
                ),
                "coordinate_derivation": {
                    "kind": "source_published_destination_coordinate_string",
                    "official_page_destination_parameter": (
                        "daddr=-14.075622,-75.734798"
                    ),
                    "official_address": "Av. Cutervo N°. 920 - Ica - Ica - Ica - Perú",
                    "google_content_requested_or_captured": False,
                    "google_basemap_or_geocoder_used": False,
                },
                "representative_point_scope": (
                    "Official Sede Central destination/address point. It is not a "
                    "surveyed ICATEC boundary, building centroid, or footprint."
                ),
                "google_rights_guardrail": (
                    "The numeric destination parameter is present in the captured "
                    "Gobierno Regional de Ica page. No Google page, tile, basemap, "
                    "geocoder result, or Google-authored coordinate is captured, "
                    "copied, or redistributed."
                ),
            },
        }
    raise SiteCoordinateAssessmentV5Error(f"unknown accepted label: {label}")


def _successor(
    label: str,
    specification: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    capture_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    output = copy.deepcopy(predecessor)
    output["evidence"].append(_evidence(label, specification, capture_rows))
    point = {
        "latitude": specification["latitude"],
        "longitude": specification["longitude"],
    }
    geometry = {
        "type": "Point",
        "coordinates": [specification["longitude"], specification["latitude"]],
    }
    for entity_name in specification["changed_entities"]:
        entity = output[entity_name]
        entity["coordinates"] = copy.deepcopy(point)
        entity["geometry"] = copy.deepcopy(geometry)
        entity["evidence_key"] = specification["evidence_key"]
        entity["method"] = "authoritative_site_plan"
    return output


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    specification: Mapping[str, Any],
) -> None:
    if predecessor.get("schema_version") != "1.1" or successor.get(
        "schema_version"
    ) != "1.1":
        raise SiteCoordinateAssessmentV5Error("coordinate schema differs")
    if set(predecessor) != set(successor):
        raise SiteCoordinateAssessmentV5Error("coordinate successor root keys differ")
    if successor["evidence"][:-1] != predecessor["evidence"] or len(
        successor["evidence"]
    ) != len(predecessor["evidence"]) + 1:
        raise SiteCoordinateAssessmentV5Error("coordinate evidence append differs")
    added = successor["evidence"][-1]
    if (
        added.get("key") != specification["evidence_key"]
        or added.get("kind") != "government_record"
    ):
        raise SiteCoordinateAssessmentV5Error("coordinate evidence identity differs")

    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(predecessor["evidence"])
    for entity_name in ("campus", "project"):
        before = predecessor[entity_name]
        after = successor[entity_name]
        changed = {
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        if entity_name in specification["changed_entities"]:
            if changed != {"coordinates", "geometry", "evidence_key", "method"}:
                raise SiteCoordinateAssessmentV5Error(
                    f"coordinate-only delta differs for {entity_name}"
                )
            for key in changed:
                restored[entity_name][key] = copy.deepcopy(before[key])
        elif changed:
            raise SiteCoordinateAssessmentV5Error(
                f"unchanged coordinate entity drifted: {entity_name}"
            )
    if restored != predecessor:
        raise SiteCoordinateAssessmentV5Error("successor gained a non-coordinate claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section]:
            raise SiteCoordinateAssessmentV5Error(f"successor changed {section}")


def _inventory(capture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {row["capture_name"]: row for row in capture_rows}
    requests = []
    for stem, specification in REQUESTS.items():
        carriers = {
            suffix: by_name[f"{stem}.{suffix}"] for suffix in ("body", "headers")
        }
        retrieved_at = datetime.fromtimestamp(
            max(carrier["mtime_epoch"] for carrier in carriers.values()), UTC
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        requests.append(
            {
                "request_id": stem,
                "requested_url": specification["url"],
                "effective_url": specification["url"],
                "http_status": specification["status"],
                "content_type": specification["content_type"],
                "decision": specification["decision"],
                "retrieved_at": retrieved_at,
                "retrieval_time_basis": (
                    "latest whole-second local filesystem mtime among exact body "
                    "and header carriers after request completion"
                ),
                "server_date_header": specification["server_date"],
                "server_date_used_as_retrieval_time": specification[
                    "server_date_used_as_retrieval_time"
                ],
                "carriers": carriers,
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "capture": {
            "original_private_path": str(CAPTURE_INPUT),
            "preserved_recovery_path": str(CAPTURE_TRASH),
            "files": len(CAPTURE_FILES),
            "bytes": CAPTURE_TOTAL_BYTES,
            "tree_sha256": CAPTURE_TREE_SHA256,
            "tree_hash_algorithm": (
                "SHA-256 of sorted '<file-sha256>  ./<basename>\\n' rows"
            ),
            "raw_bytes_redistributed": False,
            "repository_contains_raw_capture": False,
        },
        "requests": requests,
    }


def build_payloads(recorded_at: str) -> dict[str, bytes]:
    """Reproduce every v5 artifact byte without network access."""

    recorded = _parse_utc(recorded_at, "v5 recorded_at")
    capture = _capture_root()
    capture_rows = _capture_rows(capture)
    _validate_coordinate_extractions(capture)
    capture_by_name = {row["capture_name"]: row for row in capture_rows}
    documents = _verify_lineage_and_cohort()

    successors: dict[str, bytes] = {}
    successor_rows: dict[str, dict[str, Any]] = {}
    for label, specification in ACCEPTED.items():
        predecessor = documents[specification["predecessor"]]
        successor = _successor(label, specification, predecessor, capture_by_name)
        _validate_successor(predecessor, successor, specification)
        relative = f"normalized-successors/{specification['successor']}"
        raw = _canonical_json(successor)
        successors[relative] = raw
        successor_rows[label] = {
            "path": relative,
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "predecessor": f"sources/{specification['predecessor']}",
            "predecessor_sha256": COHORT[specification["predecessor"]][1],
            "campus_key": specification["campus_key"],
            "project_key": specification["project_key"],
            "changed_entities": list(specification["changed_entities"]),
            "added_evidence_key": specification["evidence_key"],
        }

    observation_rows = []
    for name, (byte_count, digest, disposition) in COHORT.items():
        document = documents[name]
        accepted_label = next(
            (
                label
                for label, specification in ACCEPTED.items()
                if specification["predecessor"] == name
            ),
            None,
        )
        row: dict[str, Any] = {
            "predecessor": f"sources/{name}",
            "predecessor_bytes": byte_count,
            "predecessor_sha256": digest,
            "campus_key": document["campus"]["stable_key"],
            "project_key": document["project"]["stable_key"],
            "disposition": disposition,
            "successor": None,
        }
        if accepted_label is not None:
            specification = ACCEPTED[accepted_label]
            row.update(
                {
                    "successor": successor_rows[accepted_label]["path"],
                    "changed_entities": list(specification["changed_entities"]),
                    "coordinate": {
                        "latitude": specification["latitude"],
                        "longitude": specification["longitude"],
                        "horizontal_uncertainty_m": specification[
                            "horizontal_uncertainty_m"
                        ],
                    },
                }
            )
        else:
            row["block_reason"] = (
                "Official evidence reaches only Chovar-06, Kirtipur Municipality. "
                "No facility-specific parcel, address, or coordinate bridge was "
                "captured, so no locality centroid, generic municipal marker, "
                "OSM point, or analyst-selected point is accepted."
            )
        observation_rows.append(row)

    coordinate_observations = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "assessment_scope": {
            "project_rows": 4,
            "campus_identities": 4,
            "accepted_successors": 3,
            "accepted_project_locations": 3,
            "accepted_campus_location_mutations": 3,
            "blocked_project_rows": 1,
        },
        "rows": observation_rows,
    }
    blocked = [row for row in observation_rows if row["successor"] is None]
    publication_contract = {
        "recorded_at": recorded_at,
        "all_private_stage_birth_and_mtime_not_later_than_recorded_at": True,
        "final_paths_absent_until_recorded_at_live": True,
        "frozen_before_promotion": True,
        "atomic_no_replace_promotion": True,
        "final_root_ctime_not_earlier_than_recorded_at": True,
        "identity_safe_cleanup": True,
    }
    disposition = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "integration": "none",
        "accepted_seed_definition": None,
        "non_coordinate_claims_added": [],
        "accepted": {
            "successors": successor_rows,
            "policy": (
                "Only exact official-source bytes with a direct facility-to-site "
                "identity chain may create a coordinate-only successor."
            ),
        },
        "blocked": {
            "project_rows": len(blocked),
            "rows": blocked,
            "bichuten_policy": (
                "Chovar-06 and Kirtipur Municipality are retained only as locality "
                "evidence. Without a facility-specific parcel, address, or point, "
                "Bichuten remains unlocated."
            ),
        },
        "source_boundaries": {
            "osm_inputs_consumed": [],
            "osm_routed_through_curated_official_importer": False,
            "google_content_captured_or_redistributed": False,
            "raw_official_bodies_redistributed": False,
            "satellite_or_cv_claims_added": False,
        },
        "lineage": {
            "base_definition": {
                "path": "sources/open-seed-2026-07-21-v73.json",
                "bytes": BASE_DEFINITION_BYTES,
                "sha256": BASE_DEFINITION_SHA256,
            },
            "base_manifest": {
                "path": "releases/2026-07-21-open-seed-v73/manifest.json",
                "bytes": BASE_MANIFEST_BYTES,
                "sha256": BASE_MANIFEST_SHA256,
            },
            "source_artifact": {
                "path": (
                    "source_artifacts/global-official-builds-six-candidate-"
                    "2026-07-21-v1"
                ),
                "manifest_sha256": SOURCE_ARTIFACT_MANIFEST_SHA256,
                "preserved_unchanged": True,
            },
            "prior_coordinate_artifact": {
                "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v4",
                "manifest_sha256": PRIOR_COORDINATE_MANIFEST_SHA256,
                "preserved_unchanged": True,
            },
        },
        "publication_contract": publication_contract,
    }
    inventory = _inventory(capture_rows)
    inventory["publication_recorded_at"] = recorded_at

    readme = f"""# Site coordinate assessment 2026-07-21 v5

This immutable artifact assesses the four unlocated official-source additions
that entered open seed v73. It accepts three coordinate-only successors and
does not integrate them into any seed or downstream product:

- LVRTC Pozitrons uses the official VZD reference point for cadastral parcel
  62740010343, linked through the LVRTC procurement site and property table,
  with a conservative ±300 m representative-point envelope. The VZD spatial
  response is attributed to Valsts zemes dienests under CC BY 4.0.
- Akashi Astana uses the reported center of the planned 110/10 kV substation
  within the same 11.0587-hectare data-centre parcel, with a conservative
  ±500 m campus/AOI envelope. It is not a building centroid or load claim.
- ICATEC uses the destination coordinate published on the Gobierno Regional de
  Ica Sede Central page, linked to CUI 2643810, with a conservative ±150 m
  address-point envelope. No Google page, tile, basemap, or geocoder result was
  requested, captured, copied, or redistributed.

Bichuten remains blocked. The official evidence reaches only Chovar-06 and
Kirtipur Municipality, with no facility-specific parcel, address, or coordinate.
No locality centroid, generic municipal marker, OSM point, or analyst-selected
point is accepted.

The three successors preserve schema 1.1 and every identity, lifecycle,
current-status, role, operating-model, workload, capacity, load, generation,
consumption, energy, and PUE field. Only coordinate snapshots and their evidence
references change. Raw response bodies remain outside the repository and are
pinned by the closed {len(CAPTURE_FILES)}-file, {CAPTURE_TOTAL_BYTES}-byte capture
tree `{CAPTURE_TREE_SHA256}`.

Publication uses a future-dated private stage. Every staged inode is frozen and
must be born and modified no later than `recorded_at`; final paths remain absent
until that instant is live, then atomic no-replace promotion establishes a final
root ctime at or after publication. The private capture is then moved intact to
Trash with no replacement.
""".encode()

    payloads = {
        "README.md": readme,
        "coordinate-observations.json": _canonical_json(coordinate_observations),
        "disposition.json": _canonical_json(disposition),
        "retrieval-inventory.json": _canonical_json(inventory),
        **successors,
    }
    files = [
        {"path": relative, "bytes": len(raw), "sha256": _sha256(raw)}
        for relative, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.2",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "recorded_at": recorded_at,
        "integration": "none",
        "publication_contract_version": 5,
        "publication": publication_contract,
        "files": files,
        "tree_sha256": _sha256(_canonical_json(files)),
    }
    manifest_raw = _canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    latest_capture = max(
        datetime.fromtimestamp(pin[3], UTC) for pin in CAPTURE_FILES.values()
    )
    if recorded < latest_capture:
        raise SiteCoordinateAssessmentV5Error("recorded_at precedes source capture")
    return payloads


def _expected_directories(payloads: Mapping[str, bytes]) -> set[str]:
    directories = {"."}
    for relative in payloads:
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _inspect_exact(root: Path, payloads: Mapping[str, bytes], *, frozen: bool) -> None:
    if root.is_symlink() or not root.is_dir():
        raise SiteCoordinateAssessmentV5Error(
            "artifact root must be an ordinary directory"
        )
    files = {
        candidate.relative_to(root).as_posix(): candidate
        for candidate in root.rglob("*")
        if candidate.is_file()
    }
    if set(files) != set(payloads):
        raise SiteCoordinateAssessmentV5Error("artifact file set differs")
    for relative, raw in payloads.items():
        candidate = files[relative]
        if candidate.is_symlink() or candidate.read_bytes() != raw:
            raise SiteCoordinateAssessmentV5Error(
                f"artifact payload differs: {relative}"
            )
        if frozen and stat.S_IMODE(candidate.stat().st_mode) != 0o444:
            raise SiteCoordinateAssessmentV5Error(
                f"artifact file is not frozen: {relative}"
            )
    directories = {
        ".": root,
        **{
            candidate.relative_to(root).as_posix(): candidate
            for candidate in root.rglob("*")
            if candidate.is_dir()
        },
    }
    if set(directories) != _expected_directories(payloads):
        raise SiteCoordinateAssessmentV5Error("artifact directory set differs")
    if frozen and any(
        candidate.is_symlink() or stat.S_IMODE(candidate.stat().st_mode) != 0o555
        for candidate in directories.values()
    ):
        raise SiteCoordinateAssessmentV5Error("artifact directory is not frozen")


def _path_identities(root: Path) -> dict[str, tuple[int, int]]:
    candidates = [
        root,
        *sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()),
    ]
    return {
        "." if candidate == root else candidate.relative_to(root).as_posix(): (
            candidate.stat(follow_symlinks=False).st_dev,
            candidate.stat(follow_symlinks=False).st_ino,
        )
        for candidate in candidates
    }


def _assert_identities(root: Path, expected: Mapping[str, tuple[int, int]]) -> None:
    if _path_identities(root) != dict(expected):
        raise SiteCoordinateAssessmentV5Error("private stage identity changed")


def _discard_stage(root: Path, identities: Mapping[str, tuple[int, int]]) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_identities(root, identities)
    for candidate in sorted(
        root.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        candidate.chmod(0o700 if candidate.is_dir() else 0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


def _fsync(filename: Path) -> None:
    descriptor = os.open(filename, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_stage(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, raw in payloads.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for directory in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_dir()),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
        _fsync(directory)
    for filename in (
        candidate for candidate in root.rglob("*") if candidate.is_file()
    ):
        filename.chmod(0o444)
        _fsync(filename)
    root.chmod(0o555)
    _fsync(root)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        metadata = candidate.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise SiteCoordinateAssessmentV5Error(
                f"private stage post-dates recorded_at: {candidate.name}"
            )


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(source: Path, destination: Path) -> None:
    from .open_seed_v69 import promote_noreplace

    try:
        promote_noreplace(source, destination)
    except SystemExit as error:
        raise SiteCoordinateAssessmentV5Error(str(error)) from error


def _verify_live_artifact(root: Path, payloads: Mapping[str, bytes]) -> None:
    _inspect_exact(root, payloads, frozen=True)
    manifest = json.loads(payloads["manifest.json"])
    target = _parse_utc(manifest["recorded_at"], "v5 recorded_at")
    if datetime.now(UTC) < target:
        raise SiteCoordinateAssessmentV5Error("v5 recorded_at is not live")
    if root.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
        raise SiteCoordinateAssessmentV5Error("final root ctime predates recorded_at")


def _preserve_capture() -> None:
    capture = _capture_root()
    _capture_rows(capture)
    if capture != CAPTURE_INPUT:
        return
    if CAPTURE_TRASH.exists() or CAPTURE_TRASH.is_symlink():
        raise SiteCoordinateAssessmentV5Error("capture Trash collision")
    _promote_noreplace(CAPTURE_INPUT, CAPTURE_TRASH)
    if CAPTURE_INPUT.exists() or CAPTURE_INPUT.is_symlink():
        raise SiteCoordinateAssessmentV5Error("capture origin survived preservation")
    _capture_rows(CAPTURE_TRASH)


def publish(recorded_at: str | None = None) -> dict[str, Any]:
    """Publish v5 once, or prove an existing artifact is byte-identical."""

    if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
        manifest = json.loads((ARTIFACT_DIR / "manifest.json").read_text())
        existing_recorded_at = manifest["recorded_at"]
        if recorded_at is not None and recorded_at != existing_recorded_at:
            raise SiteCoordinateAssessmentV5Error("existing recorded_at differs")
        payloads = build_payloads(existing_recorded_at)
        _verify_live_artifact(ARTIFACT_DIR, payloads)
        _preserve_capture()
        return {
            "artifact": str(ARTIFACT_DIR),
            "manifest_sha256": _sha256(payloads["manifest.json"]),
            "recorded_at": existing_recorded_at,
            "capture_preserved_at": str(CAPTURE_TRASH),
            "status": "existing-identical",
        }

    target = (
        _parse_utc(recorded_at, "v5 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=20)
    )
    if datetime.now(UTC) >= target:
        raise SiteCoordinateAssessmentV5Error(
            "recorded_at must be future before private staging starts"
        )
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    payloads = build_payloads(recorded_at)
    PUBLICATION_ROOT.mkdir(parents=True, exist_ok=True)

    lock_descriptor: int | None = None
    lock_identity: tuple[int, int] | None = None
    try:
        lock_descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.write(lock_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_descriptor)
        lock_metadata = os.fstat(lock_descriptor)
        lock_identity = (lock_metadata.st_dev, lock_metadata.st_ino)
    except FileExistsError as error:
        raise SiteCoordinateAssessmentV5Error(
            "active v5 publication lock exists"
        ) from error

    stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=PUBLICATION_ROOT)
    )
    stage_identities: dict[str, tuple[int, int]] | None = None
    published = False
    try:
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV5Error("initial final path collision")
        _write_stage(stage, payloads)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        stage_identities = _path_identities(stage)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV5Error("pre-wait final path collision")
        _wait_until(target)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV5Error("late final path collision")
        _assert_identities(stage, stage_identities)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        _promote_noreplace(stage, ARTIFACT_DIR)
        published = True
        _verify_live_artifact(ARTIFACT_DIR, payloads)
        _preserve_capture()
    finally:
        if not published and stage.exists() and stage_identities is not None:
            _discard_stage(stage, stage_identities)
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if lock_identity is not None:
            try:
                metadata = PUBLICATION_LOCK.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino) != lock_identity
                ):
                    raise SiteCoordinateAssessmentV5Error(
                        "refusing substituted publication-lock cleanup"
                    )
                PUBLICATION_LOCK.unlink()
    return {
        "artifact": str(ARTIFACT_DIR),
        "manifest_sha256": _sha256(payloads["manifest.json"]),
        "recorded_at": recorded_at,
        "capture_preserved_at": str(CAPTURE_TRASH),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(publish(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
