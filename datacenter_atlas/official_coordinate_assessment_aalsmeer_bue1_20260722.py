"""Publish the governed Aalsmeer/BUE1 official-coordinate assessment.

This immutable, non-integrated overlay accepts one coordinate-only successor:
the exact NorthC Aalsmeer publisher address is bridged to one current PDOK/BAG
address record.  The Cirion BUE1 USIG result remains review evidence because
Buenos Aires Data explicitly marks all API/GTFS datasets suspended for review
and correction.  Raw response bodies are hash-bound in a private capture and
are never copied into the released artifact.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from .external_captures import resolve_external_capture
from .open_seed_v69 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "official-coordinate-assessment-aalsmeer-bue1-2026-07-22-v2"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ARTIFACT_ROOT / f".{ARTIFACT_ID}.lock"
AS_OF_DATE = "2026-07-22"

REJECTED_V1 = ARTIFACT_ROOT / (
    "official-coordinate-assessment-aalsmeer-bue1-2026-07-22-v1"
)
REJECTED_V1_RECORDED_AT = "2026-07-22T03:59:29Z"
REJECTED_V1_MANIFEST_PIN = (
    1_610,
    "3699fbc4e79e6249328f996ffefd1669f6189ed9685a804cc5d64a7ef16ad80f",
)
REJECTED_V1_LOGICAL_TREE_SHA256 = (
    "40ee4787b95d3fe2df97ed5b903d2eda4ade1091150eb8ce0a1fec1efc6684ee"
)
REJECTED_V1_PHYSICAL_TREE_SHA256 = (
    "e5ab998fae4e3c761160a3dee4ecce1cf957b215cdb057a640cb49bc30575d05"
)
REJECTED_V1_PATH_PINS: Mapping[str, Mapping[str, Any]] = {
    ".": {"kind": "directory", "mode": "0555", "ctime_ns": 1_784_692_769_016_466_373},
    "README.md": {
        "kind": "file",
        "mode": "0444",
        "bytes": 1_988,
        "sha256": "6102ca0048d21ae6c2ad17c02255978ddb7d12f45320fe0e1509291bcea3a9be",
        "ctime_ns": 1_784_692_749_612_805_498,
    },
    "coordinate-observations.json": {
        "kind": "file",
        "mode": "0444",
        "bytes": 3_207,
        "sha256": "6cdaaa945c8a9273177bec5003ee4a05eda411fe2b9d75cf32150d04ff414051",
        "ctime_ns": 1_784_692_749_612_908_414,
    },
    "disposition.json": {
        "kind": "file",
        "mode": "0444",
        "bytes": 6_094,
        "sha256": "ad2d98fe2780f7bfeec659928a61fc8a0fcbec1a88bff79d5514c644c4eef497",
        "ctime_ns": 1_784_692_749_612_775_623,
    },
    "manifest.json": {
        "kind": "file",
        "mode": "0444",
        "bytes": 1_610,
        "sha256": REJECTED_V1_MANIFEST_PIN[1],
        "ctime_ns": 1_784_692_749_612_833_290,
    },
    "manifest.sha256": {
        "kind": "file",
        "mode": "0444",
        "bytes": 80,
        "sha256": "8022b7be8487048696f453ccba3eaff7007fee36bb744e1c7ea30c3855a66d7f",
        "ctime_ns": 1_784_692_749_612_744_040,
    },
    "normalized-successors": {
        "kind": "directory",
        "mode": "0555",
        "ctime_ns": 1_784_692_749_613_155_996,
    },
    (
        "normalized-successors/curated-official-2026-07-22-northc-aalsmeer-"
        "phase-2-expansion-coordinate-v1.json"
    ): {
        "kind": "file",
        "mode": "0444",
        "bytes": 12_373,
        "sha256": "3f5725d9ea75a3db0b7c0e38a58241b0a48e80aeee0a1964e7a9f00135a3b806",
        "ctime_ns": 1_784_692_749_612_999_080,
    },
    "retrieval-inventory.json": {
        "kind": "file",
        "mode": "0444",
        "bytes": 5_604,
        "sha256": "e61598057c079193e9c48aa33944e040a42418f1ed119da52938aa5e470b62b8",
        "ctime_ns": 1_784_692_749_612_862_414,
    },
}

NORTHC_SOURCE_NAME = (
    "curated-official-2026-07-22-northc-aalsmeer-phase-2-expansion.json"
)
NORTHC_SOURCE = SOURCES_ROOT / NORTHC_SOURCE_NAME
NORTHC_SOURCE_PIN = (
    8_019,
    "ee4fbdb6952d475542c194228c6e36e1735b68ee35514aafb974c6170a3f18df",
)
NORTHC_ARTIFACT = ARTIFACT_ROOT / "official-nordic-iren-current-build-gap-2026-07-22-v1"
NORTHC_ARTIFACT_RECORDED_AT = "2026-07-22T03:51:00Z"
NORTHC_MANIFEST_PIN = (
    1_731,
    "0731687c2b2d69a9bf5300d9bbed7be5d6795e0495819d3087a25bbbcb9abe11",
)
NORTHC_LOGICAL_TREE_SHA256 = (
    "c803dc2195607a4fa674cef118c57c8c033681567027cb6cf3ed200cb6cdc185"
)
NORTHC_PHYSICAL_TREE_SHA256 = (
    "061dc5ef83fcaa4a4d4cfd75eb206904ab7eeaf798ae297ed4c33213727bf470"
)

BUE1_SOURCE_NAME = "curated-official-2026-07-22-cirion-bue1-expansion-current-build.json"
BUE1_SOURCE = SOURCES_ROOT / BUE1_SOURCE_NAME
BUE1_SOURCE_PIN = (
    7_436,
    "71b173a1e5b3ffed5a018f7541a88fce51cc409092996c01ce2f13d368ab634b",
)
BUE1_ARTIFACT = ARTIFACT_ROOT / (
    "global-official-batam-jakarta-hanoi-bue1-current-build-gap-2026-07-22-v1"
)
BUE1_ARTIFACT_RECORDED_AT = "2026-07-22T03:56:03Z"
BUE1_MANIFEST_PIN = (
    2_091,
    "eb8713267c4c94a473107cd9459abfba5c2aad19284c3c74c9206fba33acb13c",
)
BUE1_LOGICAL_TREE_SHA256 = (
    "6304447459783043e3afb4f1d488451074bb65833d6a403f1458440e241d4192"
)
BUE1_PHYSICAL_TREE_SHA256 = (
    "e3bfd0d237e044acebe9b8d7dcaf5f5863329fb71f9e5314287a0b89fd667214"
)

NORTHC_CAMPUS_KEY = "curated:northc-aalsmeer-data-center"
NORTHC_PROJECT_KEY = (
    "curated:northc-aalsmeer-data-center:phase-2-first-floor-expansion"
)
NORTHC_ADDRESS = "Lakenblekerstraat 13, 1431 GE Aalsmeer, Netherlands"
BUE1_CAMPUS_KEY = "curated:cirion-bue1-buenos-aires-data-center"
BUE1_PROJECT_KEY = f"{BUE1_CAMPUS_KEY}:2025-expansion"
BUE1_ADDRESS = (
    "Av. del Campo 1301, C1427 Cdad. Autónoma de Buenos Aires, Argentina"
)
BUE1_PROJECT_ADDRESS = "Buenos Aires, Argentina"

PDOK_RECORD_ID = "adr-e3f59d6c3f9bdb2c2554f9fbe48a7546"
PDOK_NUMBER_DESIGNATION_ID = "0358200018935114"
PDOK_ADDRESSABLE_OBJECT_ID = "0358010018975673"
PDOK_DISPLAY_ADDRESS = "Lakenblekerstraat 13, 1431GE Aalsmeer"
PDOK_POINT = [4.77335841, 52.25979593]
PDOK_RD_POINT = [113090.853, 474817.885]
PDOK_LOOKUP_URL = (
    "https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup?"
    f"id={PDOK_RECORD_ID}&fl=%2A"
)
PDOK_EVIDENCE_KEY = "pdok-bag-aalsmeer-address-point-captured-2026-07-22"
PDOK_RETRIEVED_AT = "2026-07-22T03:38:40Z"

CAPTURE_ORIGIN = Path("/private/tmp/dc-official-coordinate-gap-20260722.4CXd7D")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-coordinate-gap-20260722.4CXd7D")
CAPTURE_FILE_COUNT = 16
CAPTURE_TOTAL_BYTES = 182_028
CAPTURE_INVENTORY_SHA256 = (
    "4f149f8ddf9e22021da6ddce80dc53aed82e3efa9ebab3722d4a57aa27726d53"
)
CAPTURE_TREE_SHA256 = (
    "6e36f3a99fc051451149e761c19dad39228b06c93b2eb71d941aa74f74f57184"
)

CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "buenos_aires_open_data_license.headers": (
        809,
        "da917fc685b7d3c3ac302bd2c3508bb0edfec358de1a04efbe574738acb9620e",
    ),
    "buenos_aires_open_data_license.html": (
        22_373,
        "e6cfc7f6db4e078bc0d958d2d98e3665efcd71e43fb3f9bda35cc614a4b8ea61",
    ),
    "pdok_aalsmeer_address.headers": (
        628,
        "a38b87a9cdda00123c646626477023b4c86440e43f1ebebf8b0a5bfbfdd5eca1",
    ),
    "pdok_aalsmeer_address.json": (
        6_966,
        "3cde247ce3d192b396f7788f80fa35b1bbf45306b9dd338aaa87b225495026ad",
    ),
    "pdok_aalsmeer_exact_lookup.headers": (
        628,
        "568985b1a9b085ceefa53b0b67be8be1cbcddf2ad8ec70318353aa450188b4a3",
    ),
    "pdok_aalsmeer_exact_lookup.json": (
        1_752,
        "c072470e29cb0750779ac3a5f8bac21363af774af35bed93831e57b528c1f253",
    ),
    "pdok_bag_api_metadata.headers": (
        864,
        "827501d505fa2af0a12a2f7972341ba9c706ec338424bb458607a215a81649c7",
    ),
    "pdok_bag_api_metadata.html": (
        18_695,
        "c7daf86599d8d1dcca98067ddb74bc61b9d359528701360bee5fd348aa0fefc3",
    ),
    "pdok_locatieserver_docs.headers": (
        2_530,
        "2106d971f5592381c006a259d9c1f4ce5abfc1810a6c49123f09aad9bc40bb30",
    ),
    "pdok_locatieserver_docs.html": (
        71_839,
        "fa02eaf904ee0054ef2b440e83b7e39ed01aaedae9c5a033bd57fd33e5c4c076",
    ),
    "pdok_openapi_metadata.headers": (
        279,
        "63ee81bf8630dce5f8444920217752e17520c704efb27a05ecf67579406eb00e",
    ),
    "pdok_openapi_metadata.json": (
        22_442,
        "480e69690267852fea18bfe544321d95ae49c271f64b494002172dc7ac03e6a3",
    ),
    "usig_api_docs.headers": (
        322,
        "7f1c97a0e17d8eccfe90511f7b065315c13b69e12c4db62295121780ea518d86",
    ),
    "usig_api_docs.html": (
        29_615,
        "ca6472d5f8b5b11156a96f4e41989e215e2ed4dcb3daadb7ce8aefdf6e38f1c5",
    ),
    "usig_bue1_address.headers": (
        431,
        "66618ec2a68ad7905f465e7dd31e032cefeb2357aeaa7c101c7230b7c3858870",
    ),
    "usig_bue1_address.json": (
        1_855,
        "5b67baccd8a42bf218948881dcf9697aad946cc63b75c620d4e6f1870e52d670",
    ),
}


class OfficialCoordinateAssessmentError(RuntimeError):
    """Raised when a lineage, semantic, capture, or publication fuse fails."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OfficialCoordinateAssessmentError(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OfficialCoordinateAssessmentError(f"{label} is invalid") from error
    if parsed.microsecond:
        raise OfficialCoordinateAssessmentError(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OfficialCoordinateAssessmentError(f"{label} is not an ordinary file")
    raw = path.read_bytes()
    if (len(raw), _sha256_bytes(raw)) != expected:
        raise OfficialCoordinateAssessmentError(f"{label} drifted")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OfficialCoordinateAssessmentError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise OfficialCoordinateAssessmentError(f"{label} root differs")
    return value


def _verify_source_artifact(
    root: Path,
    *,
    manifest_pin: tuple[int, str],
    recorded_at: str,
    logical_tree_sha256: str,
    physical_tree_sha256: str,
    label: str,
) -> None:
    manifest = _pin(root / "manifest.json", manifest_pin, f"{label} manifest")
    if (
        manifest.get("recorded_at") != recorded_at
        or manifest.get("tree_sha256") != logical_tree_sha256
        or tree_digest(root) != physical_tree_sha256
    ):
        raise OfficialCoordinateAssessmentError(f"{label} closure drifted")


def _verify_rejected_v1_incident() -> None:
    paths = [REJECTED_V1, *sorted(REJECTED_V1.rglob("*"), key=lambda path: path.as_posix())]
    actual = {
        "." if path == REJECTED_V1 else path.relative_to(REJECTED_V1).as_posix(): path
        for path in paths
    }
    if set(actual) != set(REJECTED_V1_PATH_PINS):
        raise OfficialCoordinateAssessmentError("rejected v1 incident path set drifted")
    for relative, expected in REJECTED_V1_PATH_PINS.items():
        path = actual[relative]
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or metadata.st_ctime_ns != expected["ctime_ns"]:
            raise OfficialCoordinateAssessmentError(
                f"rejected v1 incident identity metadata drifted: {relative}"
            )
        if f"{stat.S_IMODE(metadata.st_mode):04o}" != expected["mode"]:
            raise OfficialCoordinateAssessmentError(
                f"rejected v1 incident mode drifted: {relative}"
            )
        if expected["kind"] == "directory":
            if not path.is_dir():
                raise OfficialCoordinateAssessmentError(
                    f"rejected v1 incident directory differs: {relative}"
                )
        elif (
            not path.is_file()
            or metadata.st_size != expected["bytes"]
            or _sha256(path) != expected["sha256"]
        ):
            raise OfficialCoordinateAssessmentError(
                f"rejected v1 incident file differs: {relative}"
            )


def _verify_lineage() -> tuple[dict[str, Any], dict[str, Any]]:
    northc = _pin(NORTHC_SOURCE, NORTHC_SOURCE_PIN, "NorthC predecessor")
    bue1 = _pin(BUE1_SOURCE, BUE1_SOURCE_PIN, "BUE1 predecessor")
    _verify_source_artifact(
        NORTHC_ARTIFACT,
        manifest_pin=NORTHC_MANIFEST_PIN,
        recorded_at=NORTHC_ARTIFACT_RECORDED_AT,
        logical_tree_sha256=NORTHC_LOGICAL_TREE_SHA256,
        physical_tree_sha256=NORTHC_PHYSICAL_TREE_SHA256,
        label="NorthC source artifact",
    )
    _verify_source_artifact(
        BUE1_ARTIFACT,
        manifest_pin=BUE1_MANIFEST_PIN,
        recorded_at=BUE1_ARTIFACT_RECORDED_AT,
        logical_tree_sha256=BUE1_LOGICAL_TREE_SHA256,
        physical_tree_sha256=BUE1_PHYSICAL_TREE_SHA256,
        label="BUE1 source artifact",
    )
    _verify_source_artifact(
        REJECTED_V1,
        manifest_pin=REJECTED_V1_MANIFEST_PIN,
        recorded_at=REJECTED_V1_RECORDED_AT,
        logical_tree_sha256=REJECTED_V1_LOGICAL_TREE_SHA256,
        physical_tree_sha256=REJECTED_V1_PHYSICAL_TREE_SHA256,
        label="rejected coordinate v1 artifact",
    )
    _verify_rejected_v1_incident()
    for document, campus_key, project_key, campus_address, project_address, label in (
        (
            northc,
            NORTHC_CAMPUS_KEY,
            NORTHC_PROJECT_KEY,
            NORTHC_ADDRESS,
            NORTHC_ADDRESS,
            "NorthC",
        ),
        (
            bue1,
            BUE1_CAMPUS_KEY,
            BUE1_PROJECT_KEY,
            BUE1_ADDRESS,
            BUE1_PROJECT_ADDRESS,
            "BUE1",
        ),
    ):
        if document.get("schema_version") != "1.1":
            raise OfficialCoordinateAssessmentError(f"{label} schema differs")
        if (
            document["campus"].get("stable_key") != campus_key
            or document["project"].get("stable_key") != project_key
        ):
            raise OfficialCoordinateAssessmentError(f"{label} identity differs")
        if (
            document["campus"].get("address") != campus_address
            or document["project"].get("address") != project_address
        ):
            raise OfficialCoordinateAssessmentError(f"{label} publisher address differs")
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity.get("coordinates") is not None or entity.get("geometry") is not None:
                raise OfficialCoordinateAssessmentError(
                    f"{label} predecessor already has coordinates"
                )
    return northc, bue1


def _capture_location() -> Path:
    candidates = [
        candidate
        for candidate in (CAPTURE_TRASH, CAPTURE_ORIGIN)
        if candidate.exists() or candidate.is_symlink()
    ]
    if len(candidates) > 1:
        raise OfficialCoordinateAssessmentError(
            "exactly one preserved raw-capture location must exist"
        )
    if candidates:
        return candidates[0]
    return resolve_external_capture(CAPTURE_TRASH, CAPTURE_ORIGIN)


def verify_private_capture() -> Path:
    """Verify every private raw capture byte without redistributing it."""

    root = _capture_location()
    if root.is_symlink() or not root.is_dir():
        raise OfficialCoordinateAssessmentError("raw-capture root differs")
    files = {
        path.name: path
        for path in root.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if set(files) != set(CAPTURE_FILE_PINS) or any(
        path.is_dir() or path.is_symlink() for path in root.iterdir()
    ):
        raise OfficialCoordinateAssessmentError("raw-capture file set differs")
    for name, expected in CAPTURE_FILE_PINS.items():
        path = files[name]
        if (path.stat().st_size, _sha256(path)) != expected:
            raise OfficialCoordinateAssessmentError(f"raw capture drifted: {name}")
    if (
        len(files) != CAPTURE_FILE_COUNT
        or sum(path.stat().st_size for path in files.values()) != CAPTURE_TOTAL_BYTES
    ):
        raise OfficialCoordinateAssessmentError("raw-capture totals differ")
    rows = [
        {"path": name, "bytes": expected[0], "sha256": expected[1]}
        for name, expected in sorted(CAPTURE_FILE_PINS.items())
    ]
    if _sha256_bytes(_canonical(rows)) != CAPTURE_INVENTORY_SHA256:
        raise OfficialCoordinateAssessmentError("raw-capture inventory digest differs")
    if CAPTURE_TREE_SHA256 != "PENDING" and tree_digest(root) != CAPTURE_TREE_SHA256:
        raise OfficialCoordinateAssessmentError("raw-capture physical tree differs")
    return root


def _pdok_response() -> dict[str, Any]:
    root = verify_private_capture()
    response = _pin(
        root / "pdok_aalsmeer_exact_lookup.json",
        CAPTURE_FILE_PINS["pdok_aalsmeer_exact_lookup.json"],
        "exact PDOK lookup response",
    )
    result = response.get("response")
    if not isinstance(result, dict):
        raise OfficialCoordinateAssessmentError("PDOK response envelope differs")
    documents = result.get("docs")
    if (
        result.get("numFound") != 1
        or result.get("numFoundExact") is not True
        or not isinstance(documents, list)
        or len(documents) != 1
    ):
        raise OfficialCoordinateAssessmentError("PDOK exact-cardinality fuse failed")
    row = documents[0]
    expected = {
        "bron": "BAG",
        "type": "adres",
        "id": PDOK_RECORD_ID,
        "weergavenaam": PDOK_DISPLAY_ADDRESS,
        "nummeraanduiding_id": PDOK_NUMBER_DESIGNATION_ID,
        "adresseerbaarobject_id": PDOK_ADDRESSABLE_OBJECT_ID,
        "centroide_ll": "POINT(4.77335841 52.25979593)",
        "geometrie_ll": "POINT(4.77335841 52.25979593)",
        "centroide_rd": "POINT(113090.853 474817.885)",
        "geometrie_rd": "POINT(113090.853 474817.885)",
        "postcode": "1431GE",
        "huisnummer": 13,
        "straatnaam": "Lakenblekerstraat",
        "woonplaatsnaam": "Aalsmeer",
    }
    if not isinstance(row, dict) or any(row.get(key) != value for key, value in expected.items()):
        raise OfficialCoordinateAssessmentError("PDOK exact BAG row differs")
    return row


def _bue1_review() -> dict[str, Any]:
    root = verify_private_capture()
    response = _pin(
        root / "usig_bue1_address.json",
        CAPTURE_FILE_PINS["usig_bue1_address.json"],
        "USIG BUE1 response",
    )
    rows = response.get("direccionesNormalizadas")
    if not isinstance(rows, list) or len(rows) != 5:
        raise OfficialCoordinateAssessmentError("USIG result cardinality differs")
    first = rows[0]
    if (
        first.get("direccion") != "DEL CAMPO AV. 1301, CABA"
        or first.get("cod_partido") != "caba"
        or first.get("coordenadas")
        != {"srid": 4326, "x": "-58.467248", "y": "-34.590172"}
    ):
        raise OfficialCoordinateAssessmentError("USIG CABA candidate differs")
    return {
        "predecessor": f"sources/{BUE1_SOURCE_NAME}",
        "predecessor_bytes": BUE1_SOURCE_PIN[0],
        "predecessor_sha256": BUE1_SOURCE_PIN[1],
        "campus_key": BUE1_CAMPUS_KEY,
        "project_key": BUE1_PROJECT_KEY,
        "successor": None,
        "disposition": "review_api_dataset_suspended_pending_reactivation",
        "candidate_coordinate": {
            "longitude": -58.467248,
            "latitude": -34.590172,
            "source_crs": "EPSG:4326",
            "address": "DEL CAMPO AV. 1301, CABA",
            "accepted": False,
        },
        "reason": (
            "The live USIG endpoint returned HTTP 200, but the official Buenos "
            "Aires Data dataset page was updated on 2026-06-17 to state that all "
            "API and GTFS datasets are suspended while under review and correction, "
            "with reactivation to be announced. No stronger current official "
            "reactivation notice was captured. The initial request URL was not "
            "preserved, providing an additional reproducibility blocker."
        ),
        "rights": {
            "dataset_license": "CC-BY-2.5-AR",
            "license_does_not_override_reliability_disposition": True,
        },
        "source_pins": {
            "response": {
                "bytes": CAPTURE_FILE_PINS["usig_bue1_address.json"][0],
                "sha256": CAPTURE_FILE_PINS["usig_bue1_address.json"][1],
            },
            "response_headers": {
                "bytes": CAPTURE_FILE_PINS["usig_bue1_address.headers"][0],
                "sha256": CAPTURE_FILE_PINS["usig_bue1_address.headers"][1],
                "http_status": 200,
                "http_date": "2026-07-22T03:33:32Z",
            },
            "dataset_page": {
                "url": (
                    "https://data.buenosaires.gob.ar/dataset/"
                    "api-geocodificador-direcciones-caba"
                ),
                "bytes": CAPTURE_FILE_PINS["buenos_aires_open_data_license.html"][0],
                "sha256": CAPTURE_FILE_PINS["buenos_aires_open_data_license.html"][1],
                "retrieved_at": "2026-07-22T03:33:34Z",
                "metadata_updated_at": "2026-06-17",
            },
        },
    }


def _evidence() -> dict[str, Any]:
    _pdok_response()
    return {
        "key": PDOK_EVIDENCE_KEY,
        "kind": "government_record",
        "title": "PDOK/BAG exact address point for Lakenblekerstraat 13",
        "source_url": PDOK_LOOKUP_URL,
        "publisher": "PDOK / Kadaster (LV-BAG)",
        "source_family": "pdok_locatieserver_bag",
        "published_at": None,
        "retrieved_at": PDOK_RETRIEVED_AT,
        "license": "Public Domain Mark 1.0",
        "attribution": "Kadaster (LV-BAG), provided through PDOK",
        "excerpt": (
            "The exact PDOK lookup returns one BAG address record for "
            "Lakenblekerstraat 13, 1431GE Aalsmeer and supplies the same WGS84 "
            "point in its centroide_ll and geometrie_ll fields."
        ),
        "content_hash": CAPTURE_FILE_PINS["pdok_aalsmeer_exact_lookup.json"][1],
        "metadata": {
            "content_hash_scope": "SHA-256 of the exact 1752-byte lookup response",
            "content_hash_verification": "fetched_bytes_sha256",
            "coordinate_assessment_artifact_id": ARTIFACT_ID,
            "coordinate_reference_system": "EPSG:4326",
            "coordinate_method": "authoritative_address_geocode",
            "facility_specific_address_bridge": True,
            "lookup_request": {
                "url": PDOK_LOOKUP_URL,
                "record_id": PDOK_RECORD_ID,
                "fields": "*",
            },
            "lookup_response": {
                "bytes": CAPTURE_FILE_PINS["pdok_aalsmeer_exact_lookup.json"][0],
                "sha256": CAPTURE_FILE_PINS["pdok_aalsmeer_exact_lookup.json"][1],
                "headers_bytes": CAPTURE_FILE_PINS[
                    "pdok_aalsmeer_exact_lookup.headers"
                ][0],
                "headers_sha256": CAPTURE_FILE_PINS[
                    "pdok_aalsmeer_exact_lookup.headers"
                ][1],
                "http_status": 200,
                "http_date": PDOK_RETRIEVED_AT,
                "num_found": 1,
                "num_found_exact": True,
            },
            "bag_record": {
                "source": "BAG",
                "type": "adres",
                "id": PDOK_RECORD_ID,
                "number_designation_id": PDOK_NUMBER_DESIGNATION_ID,
                "addressable_object_id": PDOK_ADDRESSABLE_OBJECT_ID,
                "display_address": PDOK_DISPLAY_ADDRESS,
                "centroide_ll": "POINT(4.77335841 52.25979593)",
                "geometrie_ll": "POINT(4.77335841 52.25979593)",
                "centroide_rd": "POINT(113090.853 474817.885)",
                "geometrie_rd": "POINT(113090.853 474817.885)",
            },
            "stored_coordinate": {
                "longitude": PDOK_POINT[0],
                "latitude": PDOK_POINT[1],
            },
            "source_rd_coordinate": {"x": PDOK_RD_POINT[0], "y": PDOK_RD_POINT[1]},
            "horizontal_uncertainty_m": 50,
            "coordinate_scope": (
                "Official BAG address-result point for the exact publisher address. "
                "The provider field is named centroide; this assessment treats the "
                "returned Point only as an address point, not as a data-centre, "
                "building, floor, footprint, parcel, campus, or site boundary/centroid."
            ),
            "rights_evidence": {
                "url": "https://api.pdok.nl/kadaster/bag/ogc/v2?f=html&lang=en",
                "license": "Public Domain Mark 1.0",
                "bytes": CAPTURE_FILE_PINS["pdok_bag_api_metadata.html"][0],
                "sha256": CAPTURE_FILE_PINS["pdok_bag_api_metadata.html"][1],
                "headers_bytes": CAPTURE_FILE_PINS["pdok_bag_api_metadata.headers"][0],
                "headers_sha256": CAPTURE_FILE_PINS[
                    "pdok_bag_api_metadata.headers"
                ][1],
                "retrieved_at": "2026-07-22T03:39:14Z",
            },
            "claim_guardrail": (
                "This evidence changes only coordinate/geometry snapshot fields "
                "and their evidence reference. It adds no identity, construction "
                "status, operating-model, workload, capacity, load, generation, "
                "consumption, annual-energy, PUE, satellite, aerial, or CV claim."
            ),
            "excluded_sources": {
                "openstreetmap": True,
                "peeringdb": True,
                "map_clicks": True,
                "satellite_or_cv_inference": True,
            },
        },
    }


def _successor(predecessor: Mapping[str, Any]) -> dict[str, Any]:
    successor = copy.deepcopy(predecessor)
    successor["evidence"].append(_evidence())
    coordinates = {"latitude": PDOK_POINT[1], "longitude": PDOK_POINT[0]}
    geometry = {"type": "Point", "coordinates": PDOK_POINT}
    for entity_name in ("campus", "project"):
        entity = successor[entity_name]
        entity["coordinates"] = copy.deepcopy(coordinates)
        entity["geometry"] = copy.deepcopy(geometry)
        entity["evidence_key"] = PDOK_EVIDENCE_KEY
        entity["method"] = "authoritative_address_geocode"
    _validate_successor(predecessor, successor)
    return successor


def _validate_successor(
    predecessor: Mapping[str, Any], successor: Mapping[str, Any]
) -> None:
    if set(predecessor) != set(successor):
        raise OfficialCoordinateAssessmentError("NorthC successor root keys differ")
    if (
        successor["evidence"][:-1] != predecessor["evidence"]
        or len(successor["evidence"]) != len(predecessor["evidence"]) + 1
    ):
        raise OfficialCoordinateAssessmentError("NorthC evidence append differs")
    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(predecessor["evidence"])
    expected_changed = {"coordinates", "geometry", "evidence_key", "method"}
    for entity_name in ("campus", "project"):
        before = predecessor[entity_name]
        after = successor[entity_name]
        changed = {
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        if changed != expected_changed:
            raise OfficialCoordinateAssessmentError(
                f"NorthC coordinate-only delta differs for {entity_name}"
            )
        for key in changed:
            restored[entity_name][key] = copy.deepcopy(before[key])
    if restored != predecessor:
        raise OfficialCoordinateAssessmentError("NorthC gained a non-coordinate claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section]:
            raise OfficialCoordinateAssessmentError(
                f"NorthC successor changed {section}"
            )


def _successor_name() -> str:
    return NORTHC_SOURCE_NAME.removesuffix(".json") + "-coordinate-v2.json"


def _retrieval_inventory(recorded_at: str, capture_root: Path) -> dict[str, Any]:
    file_rows = [
        {"path": name, "bytes": pin[0], "sha256": pin[1]}
        for name, pin in sorted(CAPTURE_FILE_PINS.items())
    ]
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "raw_source_bodies_redistributed": False,
        "repository_contains_raw_capture": False,
        "private_capture": {
            "preserved_path": str(capture_root),
            "files": CAPTURE_FILE_COUNT,
            "bytes": CAPTURE_TOTAL_BYTES,
            "inventory_sha256": CAPTURE_INVENTORY_SHA256,
            "physical_tree_sha256": (
                None if CAPTURE_TREE_SHA256 == "PENDING" else CAPTURE_TREE_SHA256
            ),
            "file_inventory": file_rows,
        },
        "request_reproducibility": {
            "accepted_pdok_exact_lookup_url_preserved": True,
            "initial_pdok_search_url_preserved": False,
            "initial_usig_query_url_preserved": False,
            "policy": (
                "The initial broad PDOK and USIG request URLs were not preserved "
                "and are not reconstructed. Only the separately captured exact "
                "PDOK lookup is accepted. The USIG response remains review-only."
            ),
        },
        "claim_bearing_sources": [
            {
                "source_id": "pdok_aalsmeer_exact_lookup",
                "url": PDOK_LOOKUP_URL,
                "response_file": "pdok_aalsmeer_exact_lookup.json",
                "response_headers_file": "pdok_aalsmeer_exact_lookup.headers",
                "retrieved_at": PDOK_RETRIEVED_AT,
                "rights": "Public Domain Mark 1.0",
                "disposition": "accepted_address_point_only",
            },
            {
                "source_id": "pdok_bag_current_api_metadata",
                "url": "https://api.pdok.nl/kadaster/bag/ogc/v2?f=html&lang=en",
                "body_file": "pdok_bag_api_metadata.html",
                "headers_file": "pdok_bag_api_metadata.headers",
                "retrieved_at": "2026-07-22T03:39:14Z",
                "rights": "Public Domain Mark 1.0",
                "disposition": "accepted_rights_evidence_only",
            },
            {
                "source_id": "buenos_aires_data_geocoder_dataset_page",
                "url": (
                    "https://data.buenosaires.gob.ar/dataset/"
                    "api-geocodificador-direcciones-caba"
                ),
                "body_file": "buenos_aires_open_data_license.html",
                "headers_file": "buenos_aires_open_data_license.headers",
                "retrieved_at": "2026-07-22T03:33:34Z",
                "rights": "CC-BY-2.5-AR",
                "disposition": "review_suspension_notice_blocks_coordinate",
            },
            {
                "source_id": "usig_bue1_live_response",
                "request_url": "not_preserved",
                "body_file": "usig_bue1_address.json",
                "headers_file": "usig_bue1_address.headers",
                "retrieved_at": "2026-07-22T03:33:32Z",
                "rights": "CC-BY-2.5-AR",
                "disposition": "review_only_not_accepted",
            },
        ],
        "rights_guardrail": (
            "Only URLs, exact hashes, byte counts, rights metadata, and compact "
            "factual extractions are released. No response body, publisher page, "
            "map tile, satellite image, aerial image, or CV output is copied."
        ),
    }


def _publication_incident() -> dict[str, Any]:
    recorded_ns = 1_784_692_769_000_000_000
    paths = []
    for relative, pin in REJECTED_V1_PATH_PINS.items():
        row = {"path": relative, **copy.deepcopy(dict(pin))}
        row["ctime_delta_from_recorded_at_ns"] = pin["ctime_ns"] - recorded_ns
        row["ctime_contract_passed"] = pin["ctime_ns"] >= recorded_ns
        paths.append(row)
    failed = [row["path"] for row in paths if not row["ctime_contract_passed"]]
    return {
        "schema_version": "1.0",
        "incident_id": "aalsmeer-bue1-coordinate-v1-child-ctime-before-barrier",
        "status": "rejected_immutable_no_integration",
        "rejected_artifact": {
            "path": f"source_artifacts/{REJECTED_V1.name}",
            "recorded_at": REJECTED_V1_RECORDED_AT,
            "manifest_bytes": REJECTED_V1_MANIFEST_PIN[0],
            "manifest_sha256": REJECTED_V1_MANIFEST_PIN[1],
            "logical_tree_sha256": REJECTED_V1_LOGICAL_TREE_SHA256,
            "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
            "paths": paths,
        },
        "failure": {
            "contract": (
                "Every recursive final file, directory, and root ctime must be "
                "at or after the declared recorded_at while every staged birth "
                "time and mtime is at or before it."
            ),
            "failed_paths": failed,
            "failed_path_count": len(failed),
            "passing_root_only": failed == [
                relative for relative in REJECTED_V1_PATH_PINS if relative != "."
            ],
            "cause": (
                "V1 froze the private stage before waiting for recorded_at. "
                "Directory promotion advanced only the final root ctime; the "
                "recursive member ctimes remained about 19.387 seconds early."
            ),
        },
        "disposition": {
            "v1_must_not_be_integrated": True,
            "v1_successor_path_must_not_be_selected": True,
            "semantic_claims_are_not_the_failure": True,
            "replacement_artifact_id": ARTIFACT_ID,
            "replacement_successor": f"normalized-successors/{_successor_name()}",
        },
    }


def build_payloads(recorded_at: str) -> dict[str, bytes]:
    """Reproduce the complete artifact offline from pinned local inputs."""

    recorded = _instant(recorded_at, "assessment recorded_at")
    latest_input = max(
        _instant("2026-07-22T03:39:14Z", "latest raw retrieval"),
        _instant(NORTHC_ARTIFACT_RECORDED_AT, "NorthC artifact recorded_at"),
        _instant(BUE1_ARTIFACT_RECORDED_AT, "BUE1 artifact recorded_at"),
    )
    if recorded < latest_input:
        raise OfficialCoordinateAssessmentError("recorded_at precedes an input")
    northc, _bue1 = _verify_lineage()
    capture_root = verify_private_capture()
    successor = _successor(northc)
    bue1_review = _bue1_review()
    successor_relative = f"normalized-successors/{_successor_name()}"
    successor_raw = _canonical(successor)
    successor_row = {
        "path": successor_relative,
        "bytes": len(successor_raw),
        "sha256": _sha256_bytes(successor_raw),
        "predecessor": f"sources/{NORTHC_SOURCE_NAME}",
        "predecessor_bytes": NORTHC_SOURCE_PIN[0],
        "predecessor_sha256": NORTHC_SOURCE_PIN[1],
        "campus_key": NORTHC_CAMPUS_KEY,
        "project_key": NORTHC_PROJECT_KEY,
        "added_evidence_key": PDOK_EVIDENCE_KEY,
        "added_evidence_kind": "government_record",
        "method": "authoritative_address_geocode",
        "coordinate_scope": "one exact official BAG address point",
        "changed_entities": ["campus", "project"],
        "changed_snapshot_fields": [
            "coordinates",
            "geometry",
            "evidence_key",
            "method",
        ],
    }
    observations = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "assessment_scope": {
            "candidate_project_rows": 2,
            "accepted_successors": 1,
            "accepted_address_points": 1,
            "review_only_rows": 1,
        },
        "rows": [
            {
                "predecessor": f"sources/{NORTHC_SOURCE_NAME}",
                "predecessor_bytes": NORTHC_SOURCE_PIN[0],
                "predecessor_sha256": NORTHC_SOURCE_PIN[1],
                "campus_key": NORTHC_CAMPUS_KEY,
                "project_key": NORTHC_PROJECT_KEY,
                "disposition": "accepted_official_address_point",
                "successor": successor_relative,
                "coordinate": {
                    "longitude": PDOK_POINT[0],
                    "latitude": PDOK_POINT[1],
                    "horizontal_uncertainty_m": 50,
                },
                "coordinate_scope": (
                    "Exact BAG address-result point; not a footprint, parcel, "
                    "site boundary, facility centroid, building centroid, or "
                    "floor-specific point."
                ),
            },
            bue1_review,
        ],
    }
    publication_contract = {
        "recorded_at": recorded_at,
        "all_private_stage_birth_and_mtime_not_later_than_recorded_at": True,
        "final_paths_absent_until_recorded_at_live": True,
        "frozen_at_or_after_recorded_at_before_promotion": True,
        "atomic_no_replace_promotion": True,
        "all_recursive_final_member_and_root_ctimes_not_earlier_than_recorded_at": True,
        "identity_safe_cleanup": True,
        "existing_identical_replay_only": True,
    }
    disposition = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "integration": "none",
        "accepted_seed_definition": None,
        "accepted": {
            "successors": {"northc_aalsmeer": successor_row},
            "project_rows": 1,
            "campus_identities": 1,
            "policy": (
                "An exact first-party publisher address and one-cardinality "
                "official BAG lookup may support an address-point-only successor."
            ),
        },
        "not_accepted": {
            "rows": [bue1_review],
            "policy": (
                "A live endpoint response does not override a newer explicit "
                "official suspension/review notice. Unpreserved request URLs "
                "and unresolved source status remain fail-closed."
            ),
        },
        "non_coordinate_claims_added": [],
        "source_boundaries": {
            "openstreetmap_inputs_consumed": [],
            "peeringdb_inputs_consumed": [],
            "map_clicks_consumed": [],
            "satellite_or_cv_claims_added": False,
            "raw_official_or_company_bodies_redistributed": False,
        },
        "lineage": {
            "predecessor_sources": [
                {
                    "path": f"sources/{NORTHC_SOURCE_NAME}",
                    "bytes": NORTHC_SOURCE_PIN[0],
                    "sha256": NORTHC_SOURCE_PIN[1],
                },
                {
                    "path": f"sources/{BUE1_SOURCE_NAME}",
                    "bytes": BUE1_SOURCE_PIN[0],
                    "sha256": BUE1_SOURCE_PIN[1],
                },
            ],
            "source_artifacts": [
                {
                    "path": f"source_artifacts/{NORTHC_ARTIFACT.name}",
                    "recorded_at": NORTHC_ARTIFACT_RECORDED_AT,
                    "manifest_bytes": NORTHC_MANIFEST_PIN[0],
                    "manifest_sha256": NORTHC_MANIFEST_PIN[1],
                    "logical_tree_sha256": NORTHC_LOGICAL_TREE_SHA256,
                    "physical_tree_sha256": NORTHC_PHYSICAL_TREE_SHA256,
                },
                {
                    "path": f"source_artifacts/{BUE1_ARTIFACT.name}",
                    "recorded_at": BUE1_ARTIFACT_RECORDED_AT,
                    "manifest_bytes": BUE1_MANIFEST_PIN[0],
                    "manifest_sha256": BUE1_MANIFEST_PIN[1],
                    "logical_tree_sha256": BUE1_LOGICAL_TREE_SHA256,
                    "physical_tree_sha256": BUE1_PHYSICAL_TREE_SHA256,
                },
            ],
            "rejected_publication_incident": {
                "path": f"source_artifacts/{REJECTED_V1.name}",
                "recorded_at": REJECTED_V1_RECORDED_AT,
                "manifest_bytes": REJECTED_V1_MANIFEST_PIN[0],
                "manifest_sha256": REJECTED_V1_MANIFEST_PIN[1],
                "logical_tree_sha256": REJECTED_V1_LOGICAL_TREE_SHA256,
                "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
                "integration": "forbidden",
            },
        },
        "publication_contract": publication_contract,
    }
    readme = f"""# Official-coordinate assessment: Aalsmeer and BUE1

This immutable, non-integrated overlay assesses two accepted official-source
predecessors. It publishes one coordinate-only successor for NorthC Aalsmeer
and retains the Cirion BUE1 candidate in review.

NorthC's exact publisher address, `{NORTHC_ADDRESS}`, is bridged to the current
PDOK/BAG record `{PDOK_RECORD_ID}` through a separately captured exact lookup.
The lookup returns exactly one record and the same WGS84 Point in its
`centroide_ll` and `geometrie_ll` fields. The Point is stored only as an
official address point for both campus and project rows. It is not a data-centre
or building centroid, floor point, footprint, parcel, campus, or site boundary.
PDOK's current BAG API metadata labels the data Public Domain Mark 1.0.

The live USIG response for BUE1 returned a CABA candidate, but Buenos Aires
Data's official dataset page was updated on 17 June 2026 to state that all API
and GTFS datasets are suspended during review and correction. No stronger
current official reactivation notice was captured, and the initial USIG request
URL was not preserved. BUE1 therefore has no successor and no accepted point.

The NorthC successor appends one government-record evidence row and changes
only campus/project `coordinates`, `geometry`, `evidence_key`, and `method`.
Identity, address, roles, confidence, dates, lifecycle, operating-model,
workload, capacity, load, generation, consumption, energy, and PUE claims are
unchanged. No OSM, PeeringDB, map click, satellite image, aerial image, or CV
inference contributes to this assessment.

The prior immutable v1 publication is rejected and must not be integrated. Its
root ctime passed the declared barrier, but every recursive member ctime was
about 19.387 seconds early because v1 froze its private stage before waiting.
`publication-incident.json` pins every v1 path, byte count, hash, mode, ctime,
and exact failure. V2 uses a distinct successor path and is the only eligible
coordinate overlay from this assessment.

Raw responses and headers remain outside the repository. The retrieval
inventory records their exact byte counts, SHA-256 hashes, rights, and
dispositions. Publication uses a future-dated private stage, freezes every
inode before waiting, and performs atomic no-replace promotion only after the
declared `recorded_at` is live.
""".encode("utf-8")
    payloads = {
        "README.md": readme,
        "coordinate-observations.json": _canonical(observations),
        "disposition.json": _canonical(disposition),
        "publication-incident.json": _canonical(_publication_incident()),
        "retrieval-inventory.json": _canonical(
            _retrieval_inventory(recorded_at, capture_root)
        ),
        successor_relative: successor_raw,
    }
    files = [
        {"path": relative, "bytes": len(raw), "sha256": _sha256_bytes(raw)}
        for relative, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.2",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "recorded_at": recorded_at,
        "integration": "none",
        "publication_contract_version": 6,
        "publication": publication_contract,
        "files": files,
        "tree_sha256": _sha256_bytes(_canonical(files)),
    }
    manifest_raw = _canonical(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n".encode("ascii")
    )
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
        raise OfficialCoordinateAssessmentError("artifact root differs")
    files = {
        candidate.relative_to(root).as_posix(): candidate
        for candidate in root.rglob("*")
        if candidate.is_file()
    }
    if set(files) != set(payloads):
        raise OfficialCoordinateAssessmentError("artifact file set differs")
    for relative, raw in payloads.items():
        candidate = files[relative]
        if candidate.is_symlink() or candidate.read_bytes() != raw:
            raise OfficialCoordinateAssessmentError(f"artifact payload differs: {relative}")
        if frozen and stat.S_IMODE(candidate.stat().st_mode) != 0o444:
            raise OfficialCoordinateAssessmentError(f"artifact file is not frozen: {relative}")
    directories = {
        ".": root,
        **{
            candidate.relative_to(root).as_posix(): candidate
            for candidate in root.rglob("*")
            if candidate.is_dir()
        },
    }
    if set(directories) != _expected_directories(payloads):
        raise OfficialCoordinateAssessmentError("artifact directory set differs")
    if frozen and any(
        candidate.is_symlink() or stat.S_IMODE(candidate.stat().st_mode) != 0o555
        for candidate in directories.values()
    ):
        raise OfficialCoordinateAssessmentError("artifact directory is not frozen")


def _path_identities(root: Path) -> dict[str, tuple[int, int]]:
    candidates = [root, *sorted(root.rglob("*"), key=lambda path: path.as_posix())]
    return {
        "." if candidate == root else candidate.relative_to(root).as_posix(): (
            candidate.stat(follow_symlinks=False).st_dev,
            candidate.stat(follow_symlinks=False).st_ino,
        )
        for candidate in candidates
    }


def _assert_identities(root: Path, expected: Mapping[str, tuple[int, int]]) -> None:
    if _path_identities(root) != dict(expected):
        raise OfficialCoordinateAssessmentError("private stage identity changed")


def _discard_stage(root: Path, identities: Mapping[str, tuple[int, int]]) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_identities(root, identities)
    for candidate in sorted(root.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        candidate.chmod(0o700 if candidate.is_dir() else 0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_stage(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, raw in payloads.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for directory in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o700)
        _fsync(directory)
    root.chmod(0o700)
    _fsync(root)


def _freeze_stage(root: Path) -> None:
    for filename in (candidate for candidate in root.rglob("*") if candidate.is_file()):
        filename.chmod(0o444)
        _fsync(filename)
    for directory in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
        _fsync(directory)
    root.chmod(0o555)
    _fsync(root)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        metadata = candidate.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OfficialCoordinateAssessmentError(
                f"private stage post-dates recorded_at: {candidate.name}"
            )


def _assert_recursive_ctimes_at_or_after(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        if candidate.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
            raise OfficialCoordinateAssessmentError(
                f"final member ctime predates recorded_at: {candidate.name}"
            )


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
        raise OfficialCoordinateAssessmentError(str(error)) from error


def _verify_live(root: Path, payloads: Mapping[str, bytes]) -> None:
    _inspect_exact(root, payloads, frozen=True)
    manifest = json.loads(payloads["manifest.json"])
    target = _instant(manifest["recorded_at"], "assessment recorded_at")
    if datetime.now(UTC) < target:
        raise OfficialCoordinateAssessmentError("recorded_at is not live")
    _assert_recursive_ctimes_at_or_after(root, target)


def publish(recorded_at: str | None = None) -> dict[str, Any]:
    """Publish exactly once, or prove the existing artifact byte-identical."""

    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        existing_recorded_at = manifest["recorded_at"]
        if recorded_at is not None and recorded_at != existing_recorded_at:
            raise OfficialCoordinateAssessmentError("existing recorded_at differs")
        payloads = build_payloads(existing_recorded_at)
        _verify_live(ARTIFACT, payloads)
        return {
            "artifact": str(ARTIFACT),
            "manifest_sha256": _sha256_bytes(payloads["manifest.json"]),
            "recorded_at": existing_recorded_at,
            "status": "existing-identical",
        }

    target = (
        _instant(recorded_at, "assessment recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=20)
    )
    if datetime.now(UTC) >= target:
        raise OfficialCoordinateAssessmentError(
            "recorded_at must be future before private staging starts"
        )
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    payloads = build_payloads(recorded_at)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
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
        raise OfficialCoordinateAssessmentError("active publication lock exists") from error

    stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT))
    stage_identities: dict[str, tuple[int, int]] | None = None
    published = False
    try:
        if ARTIFACT.exists() or ARTIFACT.is_symlink():
            raise OfficialCoordinateAssessmentError("initial final path collision")
        _write_stage(stage, payloads)
        _inspect_exact(stage, payloads, frozen=False)
        _assert_stage_precedes(stage, target)
        stage_identities = _path_identities(stage)
        if ARTIFACT.exists() or ARTIFACT.is_symlink():
            raise OfficialCoordinateAssessmentError("pre-wait final path collision")
        _wait_until(target)
        if ARTIFACT.exists() or ARTIFACT.is_symlink():
            raise OfficialCoordinateAssessmentError("late final path collision")
        _assert_identities(stage, stage_identities)
        _inspect_exact(stage, payloads, frozen=False)
        _assert_stage_precedes(stage, target)
        _freeze_stage(stage)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        _assert_recursive_ctimes_at_or_after(stage, target)
        _promote_noreplace(stage, ARTIFACT)
        published = True
        _verify_live(ARTIFACT, payloads)
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
                    raise OfficialCoordinateAssessmentError(
                        "refusing substituted publication-lock cleanup"
                    )
                PUBLICATION_LOCK.unlink()
    return {
        "artifact": str(ARTIFACT),
        "manifest_sha256": _sha256_bytes(payloads["manifest.json"]),
        "recorded_at": recorded_at,
        "status": "published",
    }


def main() -> int:
    print(json.dumps(publish(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
