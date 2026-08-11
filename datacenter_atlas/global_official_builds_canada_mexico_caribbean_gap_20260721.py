"""Publish the bounded Canada, Mexico, Central America, and Caribbean gap.

Six direct-source records carry only last-observed lifecycle, explicitly typed
capacity, operating-model, and source-reported placement observations. Named
but unresolved candidates and bounded negatives remain review-only. Publication
is collision-failing, time-gated, no-replace, and immutable.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-canada-mexico-caribbean-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = (
    ROOT / ".global-official-builds-canada-mexico-caribbean-gap-20260721.lock"
)
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-canada-mexico-20260721.pGmRVm")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-canada-mexico-20260721.pGmRVm")
CAPTURE_TREE_SHA256 = "5ec2134258527cdae6f4641fd6c4a2374d2458ea179ad9dfad60f95397583805"
CAPTURE_FILE_COUNT = 64
CAPTURE_TOTAL_BYTES = 9_699_824

V83_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v83.json"
V83_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
V83_MANIFEST = V83_RELEASE / "manifest.json"
V83_ENTITIES = V83_RELEASE / "entities.csv"
V83_PINS = {
    V83_DEFINITION: (
        98_808,
        "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7",
    ),
    V83_MANIFEST: (
        14_812,
        "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
    ),
    V83_ENTITIES: (
        955_982,
        "ea6b78cbe55d1424f97d2ba76ae10c3cb134ee44a98f3bde223dd141dd1a68da",
    ),
}
V83_TREE_SHA256 = "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d"
V83_INPUT_COUNT = 441
KIO_GUATEMALA_SOURCE = (
    SOURCES_ROOT
    / "curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json"
)
KIO_GUATEMALA_PIN = (
    8_402,
    "10e17a3fb0619031a124dc3f58800b3b51c6a43671b071a4f5363d4558eb95fc",
)
KIO_GUATEMALA_STABLE_KEY = "curated:kio-tec-guatemala-campus:second-data-center"
KIO_GUATEMALA_EVIDENCE_ID = "3030fc69-fc51-5e41-9cce-353f4c7ebda7"

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-qscale-q01-building-b-current-build.json",
    "curated-official-2026-07-21-estructure-cal3-current-build.json",
    "curated-official-2026-07-21-cologix-mtl8-operational-closure.json",
    "curated-official-2026-07-21-odata-qr04-phase-1-operational-closure.json",
    "curated-official-2026-07-21-equinix-mo2-phase-1-operational-closure.json",
    "curated-official-2026-07-21-odata-qr03-first-facility-operational-closure.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialCanadaMexicoCaribbeanGapError = publication.OfficialTrancheError
_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_identity = publication._identity
_has_identity = publication._has_identity
_promote_noreplace = publication._promote_noreplace
_discard_owned_directory = publication._discard_owned_directory
_assert_stage_precedes_target = publication._assert_stage_precedes_target
_assert_final_ctimes = publication._assert_final_ctimes
_require_finals_absent = publication._require_finals_absent
_wait_until = publication._wait_until
_rollback_promotions = publication._rollback_promotions


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "cologix_mtl8_facility.body": (
        512_522,
        "057941f7016c5bca9db77443514f77f1b51191a8f11ba407bd1c4467fbf41e89",
    ),
    "cologix_mtl8_facility.headers": (
        912,
        "7c3d612a50fa7bed5de1152ecfdfd5a808c162a7d139a4dc771304ba9b82b8e4",
    ),
    "cologix_mtl8_facility.stderr": (
        554,
        "8d482ed6fd451b948c1b9e3a7565b061724bb3f20871ec254a45a8db1bc92ed6",
    ),
    "cologix_mtl8_facility.telemetry": (
        86,
        "02fa66ebe3264dba6f84492f589eed391376724cd78858b30ebf7f71ffcff6ce",
    ),
    "cologix_mtl8_status.body": (
        508_845,
        "e75a2f515c64f94a6135a4d3e696573501d8ee59042ba394b1369450b4d18145",
    ),
    "cologix_mtl8_status.headers": (
        909,
        "f0ac7ad6a088bfeccbde0215a73dbeeec75a259e086d3c9c8be20cccb36a993f",
    ),
    "cologix_mtl8_status.stderr": (
        396,
        "4d5a08d58bf1646564372d8f5a9d24d0a0a83a68bb437a40acd04f14bd49a9f1",
    ),
    "cologix_mtl8_status.telemetry": (
        156,
        "5520f6c60da6cdb1323f811d73d82ec24c6bbebfcd2da6414ddc578dac9b2870",
    ),
    "ellisdon_confidential.body": (
        305_151,
        "985bbdbeda3e7666faa91d8e1483f12d206f2ff4ecd5a1e35ce3a98cb9053c1b",
    ),
    "ellisdon_confidential.headers": (
        627,
        "bedd349476772eeca02b97ef9fe0dca07e5762b5b2fb8c7708d321fbed6a99fc",
    ),
    "ellisdon_confidential.stderr": (
        554,
        "e9f083a554c31987e10eb27da326b3eff4b3351e461eb84ab2da30855008c2e4",
    ),
    "ellisdon_confidential.telemetry": (
        90,
        "aac7a58837898f49d52143bfbb4467b0d76dc117fecf731cb43fceacbb3b31cf",
    ),
    "equinix_mo2_facility.body": (
        247_470,
        "62d301791309af09a8eeb64ad11aabc2218d1f910e05bfd02d2795de4ed284db",
    ),
    "equinix_mo2_facility.headers": (
        856,
        "d3f6296f186f536aa614aa269b9e3f020f1e955b45a2a73e625ff8d19c968e94",
    ),
    "equinix_mo2_facility.stderr": (
        396,
        "bd309e7f361a0ac745e643d2b46ccaeda6c6749f18cf581841934195f2035576",
    ),
    "equinix_mo2_facility.telemetry": (
        136,
        "3df30d68dc02f815b6e7f51142514c59145fe70b38ed6a5b9e1d2bfea591dbde",
    ),
    "equinix_mo2_opening.body": (
        123_562,
        "068789d2f327be758c40f6c290056eac929c52d7a188155d7a83d7dc5d40eef5",
    ),
    "equinix_mo2_opening.headers": (
        711,
        "7ddb29b4f2dd371a279619140038a02fcdaeae15b4ddd72b31e70172fb328b95",
    ),
    "equinix_mo2_opening.stderr": (
        317,
        "f75818fcaeadd8d49717a7108a8efa32a6f2f75989ec97c5efa0811f4ed79f48",
    ),
    "equinix_mo2_opening.telemetry": (
        152,
        "238011cef121a6685d6f7f77b57e49926ed55b000f718e5f0ab35be8169973fc",
    ),
    "estructure_cal3.body": (
        95_172,
        "22f3c128450cc56c1662e26b6b91a41ab28106874d74a56d5e4de8ec1d284dee",
    ),
    "estructure_cal3.headers": (
        3_002,
        "1bdce127e43d7764694bc5a0cb9b5753b73e11028a247bd5a323c7d0ea0adf5c",
    ),
    "estructure_cal3.stderr": (
        317,
        "d69b4624d87fe2e840081a233bbc9028689a7491ea7eb84491c37762f6db9f62",
    ),
    "estructure_cal3.telemetry": (
        89,
        "e407541886ce9ad0ef94e868eae3a074ac3c9df1ccb3543b7e1e22da844617d5",
    ),
    "estructure_cal3_datasheet.body": (
        577_477,
        "befe2961598a8c4e307abea854dc288c804b4db0a7ba8945a20b49fed5adaad4",
    ),
    "estructure_cal3_datasheet.headers": (
        1_667,
        "75d55c41fc51ff60c3b74918bdf3bafcf6dc05ea7da613a56c538596cb8a288c",
    ),
    "estructure_cal3_datasheet.stderr": (
        396,
        "2203a025867167dcc81d8e2b765352dde084cc3728bcc7bd3c16a2b18269639a",
    ),
    "estructure_cal3_datasheet.telemetry": (
        118,
        "402d34653b80f512589ce091799ba3758f0fe3140ba2de3390548658e8127040",
    ),
    "estructure_locations_map.body": (
        95_327,
        "eaa99c1119c86c498552c340babd9bd4253a313e0a6d44b255a8f50863a143c8",
    ),
    "estructure_locations_map.headers": (
        2_934,
        "406821cea33a3cd7a0b91d3691d98303b460a2770bf11453d5f2e71eb3bb49ef",
    ),
    "estructure_locations_map.stderr": (
        317,
        "d4f0c462dfcd2b5b6db58fe5b92c8c593296b042c43df948c6a9c5f12dcba24a",
    ),
    "estructure_locations_map.telemetry": (
        75,
        "f585dbbc21898367cbf4d55e96817ec87c36502e6dbfc2bfba96fbf8c2e0a0e0",
    ),
    "kio_qro2_news.body": (
        90_628,
        "1311bd0f7212321cced84bd5435f9838ccf9722887d97b3c51e3b224a354bc07",
    ),
    "kio_qro2_news.headers": (
        1_027,
        "33b47c5d099d8e8355ab66f67a1c0b403b911422b78792992f1483944d5f10cf",
    ),
    "kio_qro2_news.stderr": (
        397,
        "bbe386f44441505e8c7af1d297bcd3abc5044da16ba6b1d7fc5151b654d7794a",
    ),
    "kio_qro2_news.telemetry": (
        67,
        "249cb79f28c9b90702685bbba77a09226ff0e10cf1b8e7d97d8f4656ecc4e0da",
    ),
    "kio_qro2_spec.body": (
        78_715,
        "3ad402ba9e147779dfe222616bcea58d1af106530defd7f96569af58082fce37",
    ),
    "kio_qro2_spec.headers": (
        701,
        "67cfb379aaf978ce068e9d2437ea811d5af479872ad95803e75c5678196a9546",
    ),
    "kio_qro2_spec.stderr": (
        317,
        "285065a0de2f3a2622f2063a232c86195fd9440c31d0f95edd84471aba9fd9ed",
    ),
    "kio_qro2_spec.telemetry": (
        109,
        "4b8e6ad87dc76cc3ac096e46d2dc5b3dec6dd018e2929418f05f39895f6a4acf",
    ),
    "microsoft_mexico_pdf.body": (
        6_582_855,
        "221f33c0204ef0d6c201aab9344c904115a9cc3463f22f334ab3adf2968b325e",
    ),
    "microsoft_mexico_pdf.headers": (
        801,
        "7a4f3b1bfb644dda5a6cb46167c0f6331640e91c1898479c5a2f695c1c581b51",
    ),
    "microsoft_mexico_pdf.stderr": (
        396,
        "3e3759094cd2a2266942575b9a6e8f63ee7bef415ad8ac2a03e8f1ef65ec2d99",
    ),
    "microsoft_mexico_pdf.telemetry": (
        119,
        "5809868fec2db7362aaea926c93aee7105079cc8830c4f85cd6e84915ebfe3c2",
    ),
    "odata_qr03_opening.body": (
        85_759,
        "57b6dabe461332a926666cb4792652590ea567819b3c4438568a5b0991e0f73d",
    ),
    "odata_qr03_opening.headers": (
        739,
        "93af192c9193d9077f97edcc90a6e4ac1407c3b9883ac37b6cf134c4cd67aa54",
    ),
    "odata_qr03_opening.stderr": (
        396,
        "96b68d5782da76df3e01a22a94c275e726c5331ebfb54ec62b754bf1c4aea815",
    ),
    "odata_qr03_opening.telemetry": (
        171,
        "94b58ed4b376dd5f35758281e7d7e3b47d8fe0f724debf9a9b3d59f44f9b8350",
    ),
    "odata_qr04_facility.body": (
        48_604,
        "a6bea2cfed4db25a55a0fc2fa25e3c1e281f71b8c7a9ea9f48fd5f7b4b520568",
    ),
    "odata_qr04_facility.headers": (
        742,
        "ff784965817115c4572a38a1e2cb600a39c19523cb4e34ffd768fa324677262c",
    ),
    "odata_qr04_facility.stderr": (
        396,
        "f449eb66de8cfeb0a1ab4192440291168a3fedb3d07bd9279015b44133e9358e",
    ),
    "odata_qr04_facility.telemetry": (
        92,
        "460a8b117f99f6b31004d5a672465da9705cc16c9ed4843aef7af5ac825d515c",
    ),
    "odata_qr04_operator_map.body": (
        186_043,
        "dd7e5b0599f049a5a2fc88fe2af76e3242a05731606c4065438ae80fea7b7ec4",
    ),
    "odata_qr04_operator_map.headers": (
        2_894,
        "9fbfd3cff11d562a21cdc344c26d0e9cdad01e13372efc6c682a07081b885a41",
    ),
    "odata_qr04_operator_map.stderr": (
        397,
        "b1d1646bf3b41d3d9c301e100b165962049a31c164c2190af026a91c85d39f6f",
    ),
    "odata_qr04_operator_map.telemetry": (
        329,
        "2bce0e8bd29aae7a0a99425824939b4375b376d8df56ab2b7003925b00b1e3e1",
    ),
    "odata_qr04_status.body": (
        85_496,
        "d8a5be6d49f9b073765a55551c1a493a1faa60610a1ea51d46b4a5bca9ef9b9e",
    ),
    "odata_qr04_status.headers": (
        739,
        "8af28c645d9cbf5fa9d38b9beeb3741733692dd40d1a930e216e4055b3d6e63f",
    ),
    "odata_qr04_status.stderr": (
        396,
        "4e9e52fbc478bdadde0bd18859ec2a3dc335c8f23db92657157255aa6f804407",
    ),
    "odata_qr04_status.telemetry": (
        163,
        "04e9d80abac0c28e8ee5b43f8f85380e82283f2b8c84b7e8224435d30bdfe298",
    ),
    "qscale_q01b.body": (
        47_723,
        "71cd3c449fce72037b102a9832ab0366ddfb3296002b3783f4d3be28831fe5db",
    ),
    "qscale_q01b.headers": (
        896,
        "75673b93c44c5947480b80ad642373cf9a9f02f52f498f1f85155bbaacfbc9d0",
    ),
    "qscale_q01b.stderr": (
        317,
        "d0aac87de293f740cd1eb6ac06d422db9743167b8ab0628f08000c18e30a48e9",
    ),
    "qscale_q01b.telemetry": (
        107,
        "69da393990a03af259fd8372f8568a23409e2cdadb21b125ec1ef4da05689638",
    ),
}


def _capture(
    capture_id: str,
    url: str,
    *,
    effective_url: str | None = None,
    retrieved_at: str = "2026-07-21T18:24:44Z",
    published_at: str | None = None,
    http_status: int = 200,
    content_type: str = "text/html",
    used_for_normalized_claims: bool = True,
    identity_bound: bool = True,
) -> dict[str, Any]:
    size, digest = CAPTURE_FILE_PINS[f"{capture_id}.body"]
    return {
        "filename": f"{capture_id}.body",
        "url": url,
        "effective_url": effective_url or url,
        "retrieved_at": retrieved_at,
        "published_at": published_at,
        "http_status": http_status,
        "content_type": content_type,
        "bytes": size,
        "sha256": digest,
        "used_for_normalized_claims": used_for_normalized_claims,
        "identity_bound": identity_bound,
    }


CAPTURES = {
    "qscale_q01b": _capture(
        "qscale_q01b",
        "https://www.qscale.com/news/q01-building-b-60mw-ai-ready-infrastructure",
        published_at="2026-06-04",
    ),
    "estructure_cal3": _capture(
        "estructure_cal3",
        "https://www.estruxture.com/data-centers/calgary/cal-3",
    ),
    "estructure_cal3_datasheet": _capture(
        "estructure_cal3_datasheet",
        "https://info.estruxture.com/hubfs/eStruxture_Datasheet_CAL3%20EN%20V1%202024.pdf?hsLang=en",
        content_type="application/pdf",
    ),
    "estructure_locations_map": _capture(
        "estructure_locations_map",
        "https://www.estruxture.com/data-centers",
        retrieved_at="2026-07-21T18:25:40Z",
        used_for_normalized_claims=False,
    ),
    "cologix_mtl8_status": _capture(
        "cologix_mtl8_status",
        "https://fr.cologix.com/news/la-caisse-invests-cad-240-million-to-advance-cologixs-ai-ready-mtl8-data-centre-in-montreal/",
        published_at="2026-03-05",
    ),
    "cologix_mtl8_facility": _capture(
        "cologix_mtl8_facility",
        "https://fr.cologix.com/data-centers/montreal/mtl8/",
    ),
    "odata_qr04_status": _capture(
        "odata_qr04_status",
        "https://odatacolocation.com/en/blog/imprensa/odata-expands-digital-infrastructure-with-fourth-hyperscale-data-center-in-mexico/",
        published_at="2025-08-14",
    ),
    "odata_qr04_facility": _capture(
        "odata_qr04_facility",
        "https://odatacolocation.com/en/blog/data-center/dc-qr04/",
        published_at="2025-08-13",
    ),
    "odata_qr04_operator_map": _capture(
        "odata_qr04_operator_map",
        "https://maps.app.goo.gl/ZeiffYzow68Jk87C7",
        effective_url=(
            "https://www.google.com/maps/place/Data+Center+ODATA+QR04/"
            "@20.9076843,-100.6217649,1033m/data=!3m1!1e3!4m6!3m5!1s0x842b530024a12323:0x25d741732ef97f32!8m2!3d20.907398!4d-100.62028!16s%2Fg%2F11w8qxh2r2"
        ),
        retrieved_at="2026-07-21T18:25:33Z",
    ),
    "equinix_mo2_opening": _capture(
        "equinix_mo2_opening",
        "https://newsroom.equinix.com/2025-10-30-Equinix-Mexico-invierte-US-81-millones-en-nuevo-centro-de-datos-en-Monterrey",
        published_at="2025-10-30",
    ),
    "equinix_mo2_facility": _capture(
        "equinix_mo2_facility",
        "https://www.equinix.com/data-centers/americas-colocation/mexico-colocation/monterrey-data-centers/mo2",
    ),
    "odata_qr03_opening": _capture(
        "odata_qr03_opening",
        "https://odatacolocation.com/en/blog/imprensa/odata-announces-the-launch-of-its-largest-data-center-in-mexico-with-300mw-of-it-capacity/",
        published_at="2025-04-30",
    ),
    "kio_qro2_news": _capture(
        "kio_qro2_news",
        "https://kiodatacenters.com/prensa/kio-data-centers-inaugura-qro2-y-consolida-el-hub-digital-mas-relevante-para-industrias-criticas-en-mexico",
        effective_url="https://kiodatacenters.com/blog",
        used_for_normalized_claims=False,
        identity_bound=False,
    ),
    "kio_qro2_spec": _capture(
        "kio_qro2_spec",
        "https://kiodatacenters.com/hubfs/spec-sheeets-2025/spec-sheet-qro2-en.pdf",
        http_status=404,
        used_for_normalized_claims=False,
        identity_bound=False,
    ),
    "microsoft_mexico_pdf": _capture(
        "microsoft_mexico_pdf",
        "https://local.microsoft.com/wp-content/uploads/2025/10/Microsoft-datacenters-in-Mexico.pdf",
        content_type="application/pdf",
        used_for_normalized_claims=False,
    ),
    "ellisdon_confidential": _capture(
        "ellisdon_confidential",
        "https://www.ellisdon.com/project/hyperscale-data-center",
        used_for_normalized_claims=False,
    ),
}

PLANNED_ALIASES = frozenset(
    {
        "QScale Q01 Building B",
        "Q01-Building-B",
        "eStruxture CAL-3",
        "CAL-3",
        "Cologix MTL8",
        "MTL8",
        "ODATA QR04",
        "DC QR04",
        "Equinix MO2",
        "MO2",
        "ODATA QR03",
        "DC QR03",
    }
)
PLANNED_URLS = frozenset(
    capture["url"]
    for capture in CAPTURES.values()
    if capture["used_for_normalized_claims"]
)


def _evidence(
    capture_id: str,
    *,
    key: str,
    title: str,
    publisher: str,
    source_family: str,
    excerpt: str,
    metadata: Mapping[str, Any],
    kind: str = "company_disclosure",
) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "network_timeout_contract": "connect_timeout_10s_wall_clock_timeout_45s",
        "http_status": capture["http_status"],
        "effective_url": capture["effective_url"],
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "raw bytes, headers, telemetry, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "or analyst geolocation contributes to a normalized claim."
        ),
        "status_semantics": "last_observed_current_status_unknown",
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": capture["url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": capture["published_at"],
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
    coordinates: tuple[float, float] | None = None,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": dict(roles),
        "coordinates": (
            None
            if coordinates is None
            else {"latitude": coordinates[0], "longitude": coordinates[1]}
        ),
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": (
            "authoritative_locality"
            if coordinates is None
            else "authoritative_site_plan"
        ),
        "confidence": 0.99,
    }


def _observation(
    entity: str,
    value: str,
    evidence_key: str,
    as_of_date: str,
    method: str,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": method,
        "confidence": 0.99,
    }


def _capacity(
    entity: str,
    metric: str,
    stage: str,
    value: float,
    evidence_key: str,
    as_of_date: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "metric": metric,
        "stage": stage,
        "unit": "MW",
        "low": value,
        "base": value,
        "high": value,
        "method": "reported",
        "confidence": 0.99,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "target_date": None,
        "notes": notes,
    }


def _document(
    *,
    campus: dict[str, Any],
    project: dict[str, Any],
    evidence: list[dict[str, Any]],
    lifecycle: dict[str, Any],
    operating_model: dict[str, Any],
    capacities: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": campus,
        "project": project,
        "lifecycle": [lifecycle],
        "operating_models": [operating_model],
        "workloads": [],
        "capacities": capacities,
    }


def _qscale_source() -> dict[str, Any]:
    evidence_key = "qscale-q01-building-b-current-build-captured-2026-07-21"
    evidence = _evidence(
        "qscale_q01b",
        key=evidence_key,
        title="QScale Q01 Building B construction update",
        publisher="QScale",
        source_family="qscale_company_news",
        excerpt=(
            "QScale reports Q01 Building B construction well underway and "
            "labels the build as 60 MW of IT capacity."
        ),
        metadata={
            "physical_status_as_reported": "construction is now well underway",
            "capacity_label_as_reported": "60 MW of IT capacity",
            "capacity_scope": (
                "Exactly one critical_it_mw design row; not installed, energized, "
                "operationally available, current load, gross demand, or generation."
            ),
            "service_model_basis": (
                "QScale says the campus provides capacity to hyperscalers, AI "
                "companies, research institutions, public bodies, and enterprises."
            ),
            "operating_model_scope": (
                "Colocation describes the multi-customer service model only."
            ),
            "design_purpose_labels": [
                "artificial intelligence",
                "high-performance computing",
            ],
            "workload_guardrail": (
                "AI-ready, designed for AI/HPC, and ready-to-host language creates "
                "no active workload observation."
            ),
            "address_guardrail": (
                "The page footer address is not independently represented as an "
                "exact Building B address; only the explicit Lévis locality is used."
            ),
        },
    )
    roles = {"developer": ["QScale"], "operator": ["QScale"]}
    campus_key = "curated:qscale-q01-levis-campus"
    project_key = f"{campus_key}:building-b"
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="QScale Q01 Lévis Campus",
            country="Canada",
            address="Lévis, Quebec, Canada",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-06-04",
        ),
        project=_entity(
            stable_key=project_key,
            name="QScale Q01 Building B",
            country="Canada",
            address="Q01 Campus, Lévis, Quebec, Canada",
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2026-06-04",
        ),
        evidence=[evidence],
        lifecycle=_observation(
            "project",
            "under_construction",
            evidence_key,
            "2026-06-04",
            "authoritative_physical_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            evidence_key,
            "2026-06-04",
            "company_disclosure",
        ),
        capacities=[
            _capacity(
                "project",
                "critical_it_mw",
                "design",
                60.0,
                evidence_key,
                "2026-06-04",
                "Directly labeled IT-capacity design figure; no present-load or operational-capacity claim.",
            )
        ],
    )


def _estructure_source() -> dict[str, Any]:
    page_key = "estructure-cal3-current-page-captured-2026-07-21"
    sheet_key = "estructure-cal3-datasheet-captured-2026-07-21"
    page = _evidence(
        "estructure_cal3",
        key=page_key,
        title="eStruxture CAL-3 current facility page",
        publisher="eStruxture",
        source_family="estructure_current_facility_pages",
        excerpt=(
            "The current CAL-3 page says the facility is being built, is scheduled "
            "for fall 2026, and will provide colocation services."
        ),
        metadata={
            "physical_status_as_reported": "CAL-3 is being built",
            "launch_timing_as_reported": "fall 2026",
            "operating_model_as_reported": "colocation",
            "workload_guardrail": (
                "Support for AI clusters and enterprise applications is design "
                "capability, not an active workload observation."
            ),
            "coordinate_guardrail": (
                "Neither the live named-facility HTML, the datasheet, nor the live "
                "first-party locations page retained an exact CAL-3 coordinate; the "
                "audit-memory coordinate was therefore omitted."
            ),
        },
    )
    sheet = _evidence(
        "estructure_cal3_datasheet",
        key=sheet_key,
        title="eStruxture CAL-3 official datasheet",
        publisher="eStruxture",
        source_family="estructure_facility_datasheets",
        excerpt=(
            "The official datasheet reports 90 MW total power and 60 MW critical "
            "power for CAL-3."
        ),
        metadata={
            "capacity_labels_as_reported": {
                "total_power_mw": 90.0,
                "critical_power_mw": 60.0,
            },
            "capacity_scope": (
                "Total power maps once to gross_facility_mw design; critical power "
                "maps once to critical_it_mw design. Neither is measured load."
            ),
        },
    )
    roles = {"developer": ["eStruxture"], "operator": ["eStruxture"]}
    campus_key = "curated:estructure-cal3-rocky-view-campus"
    project_key = f"{campus_key}:initial-build"
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="eStruxture CAL-3 Rocky View Campus",
            country="Canada",
            address="Rocky View County, Alberta, Canada",
            roles=roles,
            evidence_key=page_key,
            as_of_date="2026-07-21",
        ),
        project=_entity(
            stable_key=project_key,
            name="eStruxture CAL-3 Initial Build",
            country="Canada",
            address="Rocky View County, Alberta, Canada",
            roles=roles,
            evidence_key=page_key,
            as_of_date="2026-07-21",
        ),
        evidence=[page, sheet],
        lifecycle=_observation(
            "project",
            "under_construction",
            page_key,
            "2026-07-21",
            "authoritative_physical_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            page_key,
            "2026-07-21",
            "company_disclosure",
        ),
        capacities=[
            _capacity(
                "project",
                "critical_it_mw",
                "design",
                60.0,
                sheet_key,
                "2026-07-21",
                "Official critical-power label normalized as design only; not installed or current IT load.",
            ),
            _capacity(
                "project",
                "gross_facility_mw",
                "design",
                90.0,
                sheet_key,
                "2026-07-21",
                "Official total-power label normalized as gross-facility design only; not present demand.",
            ),
        ],
    )


def _cologix_source() -> dict[str, Any]:
    status_key = "cologix-mtl8-operational-status-captured-2026-07-21"
    facility_key = "cologix-mtl8-current-facility-page-captured-2026-07-21"
    status = _evidence(
        "cologix_mtl8_status",
        key=status_key,
        title="Cologix MTL8 operational status announcement",
        publisher="Cologix",
        source_family="cologix_company_news",
        excerpt=(
            "Cologix reports the MTL8 structure and envelope complete and the data "
            "center in service as of March 5, 2026."
        ),
        metadata={
            "physical_status_as_reported": (
                "building structure and envelope complete; data center in service"
            ),
            "operational_scope": (
                "One last-observed operational closure; no current persistence is asserted."
            ),
        },
    )
    facility = _evidence(
        "cologix_mtl8_facility",
        key=facility_key,
        title="Cologix MTL8 current facility page",
        publisher="Cologix",
        source_family="cologix_current_facility_pages",
        excerpt=(
            "The named MTL8 facility page reports 21 MW electrical power, a "
            "colocation facility, and 7350 rue Frederick-Banting."
        ),
        metadata={
            "capacity_label_as_reported": "21 MW electrical power",
            "capacity_scope": (
                "One gross_facility_mw design row; not measured draw, critical IT, "
                "installed load, generation, or annual energy."
            ),
            "operating_model_as_reported": "colocation",
            "address_binding": (
                "The current named-facility page directly pairs MTL8 with 7350 rue "
                "Frederick-Banting, Montréal, Québec."
            ),
        },
    )
    roles = {"developer": ["Cologix"], "operator": ["Cologix"]}
    campus_key = "curated:cologix-mtl8-montreal-data-center"
    project_key = f"{campus_key}:initial-build"
    address = "7350 rue Frederick-Banting, Montréal, Quebec, Canada"
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="Cologix MTL8 Montréal Data Center",
            country="Canada",
            address=address,
            roles=roles,
            evidence_key=facility_key,
            as_of_date="2026-03-05",
        ),
        project=_entity(
            stable_key=project_key,
            name="Cologix MTL8 Initial Build",
            country="Canada",
            address=address,
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-03-05",
        ),
        evidence=[status, facility],
        lifecycle=_observation(
            "project",
            "operational",
            status_key,
            "2026-03-05",
            "authoritative_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            facility_key,
            "2026-03-05",
            "company_disclosure",
        ),
        capacities=[
            _capacity(
                "project",
                "gross_facility_mw",
                "design",
                21.0,
                facility_key,
                "2026-03-05",
                "Current facility electrical-power specification retained at design stage; not measured demand.",
            )
        ],
    )


def _odata_qr04_source() -> dict[str, Any]:
    status_key = "odata-qr04-launch-status-captured-2026-07-21"
    facility_key = "odata-qr04-current-facility-page-captured-2026-07-21"
    map_key = "odata-qr04-operator-linked-map-point-captured-2026-07-21"
    status = _evidence(
        "odata_qr04_status",
        key=status_key,
        title="ODATA QR04 launch and phase status",
        publisher="ODATA",
        source_family="odata_company_news",
        excerpt=(
            "ODATA reports QR04 designed for 24 MW IT and its first 12 MW phase "
            "already operational on August 14, 2025."
        ),
        metadata={
            "physical_status_as_reported": "first 12 MW phase already operational",
            "capacity_labels_as_reported": {
                "first_phase_it_mw": 12.0,
                "full_design_it_mw": 24.0,
            },
            "capacity_scope": (
                "The first-phase value maps to project critical_it_mw operational; "
                "the full value maps to campus critical_it_mw design."
            ),
            "workload_guardrail": (
                "Cloud/AI demand, capability, and customer language creates no "
                "active workload observation."
            ),
        },
    )
    facility = _evidence(
        "odata_qr04_facility",
        key=facility_key,
        title="ODATA QR04 current facility page and operator map link",
        publisher="ODATA",
        source_family="odata_current_facility_pages",
        excerpt=(
            "The named QR04 page places the facility near San Miguel de Allende, "
            "labels 24 MW IT power, and links its operator map target."
        ),
        metadata={
            "operating_model_as_reported": "ODATA Colocation",
            "operator_map_link": "https://maps.app.goo.gl/ZeiffYzow68Jk87C7",
            "coordinate_join_guardrail": (
                "Only the exact QR04-named first-party link is joined to the captured "
                "redirect target; no generic geocode or map search is used."
            ),
        },
    )
    map_evidence = _evidence(
        "odata_qr04_operator_map",
        key=map_key,
        title="ODATA QR04 operator-linked map target",
        publisher="ODATA-linked Google Maps target",
        source_family="odata_operator_linked_maps",
        excerpt=(
            "ODATA's exact QR04 map link resolves to the named Data Center ODATA "
            "QR04 target at 20.907398, -100.62028."
        ),
        metadata={
            "first_party_link_evidence_key": facility_key,
            "coordinate_source_locator": (
                "The captured ODATA QR04 HTML pairs its Access the map control with "
                "https://maps.app.goo.gl/ZeiffYzow68Jk87C7; the captured redirect "
                "target contains !3d20.907398!4d-100.62028."
            ),
            "coordinate_semantics": "source_reported_project_map_point",
            "coordinate_use_scope": (
                "Location only; the map point does not corroborate identity beyond "
                "the exact operator link, lifecycle, operating type, or capacity."
            ),
        },
    )
    roles = {"developer": ["ODATA"], "operator": ["ODATA"]}
    campus_key = "curated:odata-dc-qr04-san-miguel-de-allende"
    project_key = f"{campus_key}:phase-1"
    address = "Near San Miguel de Allende, Querétaro region, Mexico"
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="ODATA DC QR04",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=facility_key,
            as_of_date="2025-08-14",
        ),
        project=_entity(
            stable_key=project_key,
            name="ODATA DC QR04 Phase 1",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=map_key,
            as_of_date="2025-08-14",
            coordinates=(20.907398, -100.62028),
        ),
        evidence=[status, facility, map_evidence],
        lifecycle=_observation(
            "project",
            "operational",
            status_key,
            "2025-08-14",
            "authoritative_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            facility_key,
            "2025-08-14",
            "company_disclosure",
        ),
        capacities=[
            _capacity(
                "project",
                "critical_it_mw",
                "operational",
                12.0,
                status_key,
                "2025-08-14",
                "Operator labels the first 12 MW IT phase operational; not measured consumption or current draw.",
            ),
            _capacity(
                "campus",
                "critical_it_mw",
                "design",
                24.0,
                status_key,
                "2025-08-14",
                "Operator labels 24 MW as the full QR04 IT design; not operationally available in full.",
            ),
        ],
    )


def _equinix_mo2_source() -> dict[str, Any]:
    opening_key = "equinix-mo2-opening-captured-2026-07-21"
    facility_key = "equinix-mo2-current-facility-map-captured-2026-07-21"
    opening = _evidence(
        "equinix_mo2_opening",
        key=opening_key,
        title="Equinix MO2 phase-one opening announcement",
        publisher="Equinix",
        source_family="equinix_newsroom",
        excerpt=(
            "Equinix announces MO2 officially opened in Apodaca on October 30, "
            "2025, with more than 720 cabinets in phase one."
        ),
        metadata={
            "physical_status_as_reported": "official opening of MO2",
            "phase_scope": "first phase",
            "capacity_guardrail": (
                "Cabinet count and investment values create no MW capacity row."
            ),
            "workload_guardrail": (
                "Designed for AI-ready workloads is capability, not active workload."
            ),
        },
    )
    facility = _evidence(
        "equinix_mo2_facility",
        key=facility_key,
        title="Equinix MO2 current named-facility map object",
        publisher="Equinix",
        source_family="equinix_current_facility_pages",
        excerpt=(
            "The named MO2 page directly reports Av. Mexico 260, Parque Industrial "
            "Nexxus Aeropuerto and a facility map point."
        ),
        metadata={
            "operating_model_as_reported": "colocation",
            "coordinate_source_locator": (
                "The captured Equinix MO2 HTML object pairs title MO2, the exact "
                "address, latitude 25.725216372664335, and longitude "
                "-100.13271303039684."
            ),
            "coordinate_semantics": "source_reported_project_map_point",
            "coordinate_use_scope": (
                "Location only; the point does not corroborate status, type, or capacity."
            ),
        },
    )
    roles = {"developer": ["Equinix"], "operator": ["Equinix"]}
    campus_key = "curated:equinix-mo2-monterrey-data-center"
    project_key = f"{campus_key}:phase-1"
    address = (
        "Av. Mexico 260, Parque Industrial Nexxus Aeropuerto, "
        "Apodaca, Nuevo León 66643, Mexico"
    )
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="Equinix MO2 Monterrey Data Center",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=facility_key,
            as_of_date="2025-10-30",
        ),
        project=_entity(
            stable_key=project_key,
            name="Equinix MO2 Phase 1",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=facility_key,
            as_of_date="2025-10-30",
            coordinates=(25.725216372664335, -100.13271303039684),
        ),
        evidence=[opening, facility],
        lifecycle=_observation(
            "project",
            "operational",
            opening_key,
            "2025-10-30",
            "authoritative_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            facility_key,
            "2025-10-30",
            "company_disclosure",
        ),
        capacities=[],
    )


def _odata_qr03_source() -> dict[str, Any]:
    evidence_key = "odata-qr03-first-facility-launch-captured-2026-07-21"
    evidence = _evidence(
        "odata_qr03_opening",
        key=evidence_key,
        title="ODATA QR03 first-facility launch",
        publisher="ODATA",
        source_family="odata_company_news",
        excerpt=(
            "ODATA launches QR03's first facility with 72 MW IT available and "
            "reports a 300 MW IT full-campus design."
        ),
        metadata={
            "physical_status_as_reported": "launch of the first facility",
            "availability_as_reported": "first building readily available",
            "capacity_labels_as_reported": {
                "first_building_it_mw": 72.0,
                "full_campus_it_mw": 300.0,
            },
            "capacity_scope": (
                "72 MW maps to project critical_it_mw operational; 300 MW maps "
                "to campus critical_it_mw design. Energized upstream power is not "
                "normalized as data-center load."
            ),
            "operating_model_as_reported": "ODATA Colocation",
            "workload_guardrail": (
                "Cloud/AI provider demand and committed customers create no active "
                "workload observation."
            ),
            "coordinate_guardrail": (
                "PyME Industrial Park is retained as an authoritative locality; no "
                "coordinate or geometry is inferred."
            ),
        },
    )
    roles = {"developer": ["ODATA"], "operator": ["ODATA"]}
    campus_key = "curated:odata-dc-qr03-queretaro-campus"
    project_key = f"{campus_key}:first-facility"
    address = "PyME Industrial Park, Querétaro, Mexico"
    return _document(
        campus=_entity(
            stable_key=campus_key,
            name="ODATA DC QR03 Querétaro Campus",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2025-04-30",
        ),
        project=_entity(
            stable_key=project_key,
            name="ODATA DC QR03 First Facility",
            country="Mexico",
            address=address,
            roles=roles,
            evidence_key=evidence_key,
            as_of_date="2025-04-30",
        ),
        evidence=[evidence],
        lifecycle=_observation(
            "project",
            "operational",
            evidence_key,
            "2025-04-30",
            "authoritative_status_update",
        ),
        operating_model=_observation(
            "campus",
            "colocation",
            evidence_key,
            "2025-04-30",
            "company_disclosure",
        ),
        capacities=[
            _capacity(
                "project",
                "critical_it_mw",
                "operational",
                72.0,
                evidence_key,
                "2025-04-30",
                "First-building IT power labeled readily available; not measured consumption or current draw.",
            ),
            _capacity(
                "campus",
                "critical_it_mw",
                "design",
                300.0,
                evidence_key,
                "2025-04-30",
                "Full-campus IT capacity upon full build-out; design only, not present operational capacity.",
            ),
        ],
    )


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact six schema-1.1 source documents in publication order."""

    builders = (
        _qscale_source,
        _estructure_source,
        _cologix_source,
        _odata_qr04_source,
        _equinix_mo2_source,
        _odata_qr03_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
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
                "disposition": (
                    "seed_eligible_direct_current_physical_update"
                    if document["lifecycle"][0]["value"] == "under_construction"
                    else "seed_eligible_recent_operational_closure"
                ),
                "seed_eligible": True,
                "seeded": False,
            }
        )
    return records


def _review_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "candidate_id": "kio-qro2-queretaro",
            "country": "Mexico",
            "decision": "review_only_status_and_capacity_conflict",
            "basis": (
                "The audit found an inauguration-versus-2024-operations conflict and "
                "12 MW versus 10 MW specifications. The live news URL redirected to "
                "a generic blog and the live PDF request returned HTTP 404, so no "
                "identity-bound current bytes resolve the conflict."
            ),
            "capture_ids": ["kio_qro2_news", "kio_qro2_spec"],
        },
        {
            "candidate_id": "microsoft-two-unnamed-queretaro-builds",
            "country": "Mexico",
            "decision": "review_only_unresolved_site_identity",
            "basis": (
                "Microsoft says it is building two new Querétaro facilities, but the "
                "official PDF does not name or separately identify either physical site."
            ),
            "capture_ids": ["microsoft_mexico_pdf"],
        },
        {
            "candidate_id": "ellisdon-confidential-ontario-hyperscale-data-center",
            "country": "Canada",
            "decision": "review_only_confidential_identity",
            "basis": (
                "EllisDon reports a three-storey 27 MW critical-load colocation build "
                "scheduled for 2026, but withholds the client and exact project site; "
                "no source record or capacity row is created."
            ),
            "capture_ids": ["ellisdon_confidential"],
        },
        {
            "candidate_id": "kio-second-guatemala-data-center",
            "country": "Guatemala",
            "decision": "exact_duplicate_already_selected_in_v83",
            "basis": (
                "The accepted v83 source already contains the exact project stable key "
                "and evidence record; this artifact creates no duplicate source."
            ),
            "existing_source_path": (
                "sources/curated-official-2026-07-21-kio-second-guatemala-"
                "construction-start-v2.json"
            ),
            "existing_project_stable_key": KIO_GUATEMALA_STABLE_KEY,
            "existing_evidence_id": KIO_GUATEMALA_EVIDENCE_ID,
        },
        {
            "candidate_id": "vantage-qc24-quebec",
            "country": "Canada",
            "decision": "unverified_negative_development_evidence_only",
            "basis": (
                "The bounded audit found development evidence but no recoverable "
                "recent first-party physical-status update."
            ),
            "bounded_search": "Vantage QC24 Quebec official physical construction update",
        },
        {
            "candidate_id": "cloudhq-six-queretaro-facilities",
            "country": "Mexico",
            "decision": "unverified_negative_investment_announcement_only",
            "basis": (
                "The bounded audit found a government investment announcement, not "
                "site-specific physical-start evidence for six separately identified facilities."
            ),
            "bounded_search": "CloudHQ six Queretaro facilities government official construction",
        },
        {
            "candidate_id": "layer9-falcon-queretaro",
            "country": "Mexico",
            "decision": "unverified_negative_stale_start_only",
            "basis": (
                "The bounded audit found only a 2022 start; no later authoritative "
                "physical update supports a current-construction seed."
            ),
            "bounded_search": "Layer9 Falcon Queretaro official current construction",
        },
        {
            "candidate_id": "ascenty-third-queretaro-facility",
            "country": "Mexico",
            "decision": "unverified_negative_in_development_only",
            "basis": (
                "The bounded audit found in-development language without eligible "
                "physical-start evidence."
            ),
            "bounded_search": "Ascenty third Queretaro facility official construction",
        },
        {
            "candidate_id": "liberty-gold-data-dominicana",
            "country": "Dominican Republic",
            "decision": "unverified_negative_acquisition_service_context_only",
            "basis": (
                "The bounded Caribbean audit found acquisition and subsea-service "
                "context, not a new physical data-center build."
            ),
            "bounded_search": "Liberty Gold Data Dominicana official data center construction",
        },
        {
            "candidate_id": "bluenap-ai-curacao-existing-facility",
            "country": "Curaçao",
            "decision": "unverified_negative_existing_site_upgrade_only",
            "basis": (
                "The bounded Caribbean audit found an existing-site AI upgrade, not "
                "a separately identified new facility under construction."
            ),
            "bounded_search": "BlueNAP AI Curacao official new data center construction",
        },
        {
            "candidate_id": "puerto-rico-data-center-equipment-replacement",
            "country": "Puerto Rico",
            "decision": "unverified_negative_replacement_procurement_only",
            "basis": (
                "The bounded Caribbean audit found equipment-replacement procurement, "
                "not construction of a new data center."
            ),
            "bounded_search": "Puerto Rico government data center construction procurement",
        },
        {
            "candidate_id": "jamaica-colocation-procurement",
            "country": "Jamaica",
            "decision": "unverified_negative_service_procurement_only",
            "basis": (
                "The bounded Caribbean audit found procurement for colocation "
                "services, not construction of a new facility."
            ),
            "bounded_search": "Jamaica government data center construction colocation procurement",
        },
    ]
    return [
        {
            **row,
            "source_record_created": False,
            "seed_eligible": False,
            "normalized_claims_created": 0,
            "source_url_recovered": bool(row.get("capture_ids")),
        }
        for row in rows
    ]


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    seed_rows = []
    for name, document in expected_source_documents().items():
        seed_rows.append(
            {
                "candidate_id": document["project"]["stable_key"],
                "country": document["project"]["country"],
                "decision": (
                    "seed_eligible_direct_current_physical_update"
                    if document["lifecycle"][0]["value"] == "under_construction"
                    else "seed_eligible_recent_operational_closure"
                ),
                "source_record_created": True,
                "source_path": f"sources/{name}",
                "seed_eligible": True,
                "lifecycle_observations": 1,
                "capacity_estimates": len(document["capacities"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": 0,
                "coordinates_created": sum(
                    document[entity]["coordinates"] is not None
                    for entity in ("campus", "project")
                ),
            }
        )
    review_rows = _review_candidates()
    return {
        "artifact_id": ARTIFACT_ID,
        "format": (
            "datacenter-atlas-canada-mexico-central-america-caribbean-"
            "official-gap-assessment-v1"
        ),
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": len(seed_rows) + len(review_rows),
        "seed_eligible_count": len(seed_rows),
        "review_only_count": len(review_rows),
        "regional_completeness_claimed": False,
        "caribbean_completeness_claimed": False,
        "bounded_negative_semantics": (
            "A negative records only the stated query boundary; it is not proof of absence."
        ),
        "candidates": [*seed_rows, *review_rows],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free curl GETs with explicit 10-second connect and "
            "45-second wall-clock timeouts."
        ),
        "capture_requests": len(CAPTURES),
        "successful_http_200_body_captures": sum(
            capture["http_status"] == 200 for capture in CAPTURES.values()
        ),
        "accepted_identity_bound_captures": sum(
            capture["http_status"] == 200 and capture["identity_bound"]
            for capture in CAPTURES.values()
        ),
        "captures_used_for_normalized_claims": sum(
            capture["used_for_normalized_claims"] for capture in CAPTURES.values()
        ),
        "failed_or_partial_captures": 2,
        "failed_or_partial_capture_claims": 0,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [
            {
                "capture_id": capture_id,
                "requested_url": capture["url"],
                "effective_url": capture["effective_url"],
                "retrieved_at": capture["retrieved_at"],
                "http_status": capture["http_status"],
                "content_type": capture["content_type"],
                "identity_bound": capture["identity_bound"],
                "body": {
                    "bytes": capture["bytes"],
                    "sha256": capture["sha256"],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "capture_method": "credential_free_curl_location_compressed",
                "network_timeout_contract": (
                    "connect_timeout_10s_wall_clock_timeout_45s"
                ),
                "request_credentials_supplied": False,
                "used_for_normalized_claims": capture["used_for_normalized_claims"],
            }
            for capture_id, capture in sorted(CAPTURES.items())
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "technical_incidents": [
            {
                "capture_id": "kio_qro2_news",
                "result": "redirect_identity_mismatch",
                "http_status": 200,
                "effective_url": "https://kiodatacenters.com/blog",
                "normalized_claims_created": 0,
            },
            {
                "capture_id": "kio_qro2_spec",
                "result": "http_404",
                "http_status": 404,
                "normalized_claims_created": 0,
            },
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    review_count = len(_review_candidates())
    candidate_count = len(source_records) + review_count
    duplicate_witness = _v83_duplicate_witness(source_documents)
    readme = f"""# Canada, Mexico, Central America, and Caribbean official-build gap assessment

This immutable artifact records {candidate_count} bounded candidate dispositions researched on 2026-07-21: six seed-eligible official records and {review_count} review-only or bounded-negative candidates. It makes no regional or Caribbean completeness claim.

The six source records are QScale Q01 Building B and eStruxture CAL-3 under construction; plus operational closures for Cologix MTL8, ODATA QR04 Phase 1, Equinix MO2 Phase 1, and ODATA QR03's first facility. Every lifecycle value is last-observed. Present status after the cited evidence date remains unknown.

Eight capacity rows preserve only direct labels: Q01 Building B 60 MW critical IT design; CAL-3 60 MW critical IT and 90 MW gross-facility design; MTL8 21 MW gross-facility design; QR04 Phase 1 12 MW critical IT operational and QR04 full design 24 MW; QR03 first facility 72 MW critical IT operational and QR03 full campus 300 MW critical IT design. No value is converted between gross and IT, no MVA is treated as MW, and no row implies measured demand, energy consumption, generation, or PUE.

Each source directly supports a colocation service-model observation. QScale's AI/HPC language is retained as design-purpose metadata only. Similar AI-ready, cloud, hyperscale, enterprise, and customer language creates no active workload observation anywhere in this tranche.

Two project-only source-reported map points survive. ODATA's QR04 page directly links a captured maps.app redirect whose named target contains 20.907398, -100.62028. Equinix's named MO2 facility HTML directly binds its address to 25.725216372664335, -100.13271303039684. These points are location-only and do not corroborate lifecycle, type, or capacity. The audit-memory CAL-3 coordinates are omitted because no exact first-party binding survived the live HTML, datasheet, or locations-page recheck. No generic geocode, OSM result, imagery, or inference supplies an address, coordinate, or geometry.

KIO QRO2 remains review-only because its audit conflicts were not resolved and the live requests produced a generic-blog redirect plus HTTP 404. Microsoft's two Querétaro builds remain review-only because neither site is separately identified. EllisDon's confidential Ontario build remains review-only because client and exact site identity are withheld. KIO's second Guatemala build is an exact v83 duplicate and is not recreated. The remaining named Canadian, Mexican, Central American, and Caribbean rows are bounded negatives only; none proves absence, and no Caribbean completeness claim is made.

All planned source paths, names, URLs, stable keys, and evidence keys were checked for exact normalized absence from accepted v83. Accepted v83 and all downstream products remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete {CAPTURE_FILE_COUNT}-file capture directory was moved intact to the recoverable Trash path in the rights inventory.

All source and artifact bytes were complete in private staging before `{recorded_at}`. Final paths remained absent until the declared instant and were promoted without replacement with identity-checked rollback. Source and artifact files are frozen mode 0444; the artifact directory is mode 0555.
"""
    totals = {
        "candidate_assessments": candidate_count,
        "source_records": 6,
        "seed_eligible_source_records": 6,
        "review_only_candidates": review_count,
        "distinct_campuses": 6,
        "projects": 6,
        "entity_snapshots": 12,
        "unique_evidence_records": 11,
        "lifecycle_observations": 6,
        "operating_model_observations": 6,
        "workload_observations": 0,
        "capacity_estimates": 8,
        "coordinates_present": 2,
        "geometry_present": 0,
        "source_reported_project_map_points": 2,
    }
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "caribbean_completeness_claimed": False,
        "source_records": source_records,
        "totals": totals,
        "frozen_v83_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v83.json",
                "bytes": V83_PINS[V83_DEFINITION][0],
                "sha256": V83_PINS[V83_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v83/manifest.json",
                "bytes": V83_PINS[V83_MANIFEST][0],
                "sha256": V83_PINS[V83_MANIFEST][1],
            },
            "release_tree_sha256": V83_TREE_SHA256,
            "v83_selected_input_count": V83_INPUT_COUNT,
            "new_source_paths_selected_by_v83": False,
            "kio_guatemala_duplicate": {
                "source_path": str(KIO_GUATEMALA_SOURCE.relative_to(ROOT)),
                "bytes": KIO_GUATEMALA_PIN[0],
                "sha256": KIO_GUATEMALA_PIN[1],
                "project_stable_key": KIO_GUATEMALA_STABLE_KEY,
                "evidence_id": KIO_GUATEMALA_EVIDENCE_ID,
            },
            **duplicate_witness,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v83_mutated": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
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
            "source_file_mode": "0444",
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
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "candidate_dispositions": {
            "seed_eligible": 6,
            "review_only": review_count,
        },
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessments(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o444)
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
    review_count = len(_review_candidates())
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 6 + review_count,
        "curated_source_records": 6,
        "seed_eligible_source_records": 6,
        "review_only_candidates": review_count,
        "successful_http_200_body_captures": sum(
            capture["http_status"] == 200 for capture in CAPTURES.values()
        ),
        "accepted_identity_bound_captures": sum(
            capture["http_status"] == 200 and capture["identity_bound"]
            for capture in CAPTURES.values()
        ),
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "regional_completeness_claimed": False,
        "caribbean_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "downstream_product_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _expected_capacity_rows(
    documents: Sequence[Mapping[str, Any]],
) -> set[tuple[str, str, str, float]]:
    rows: set[tuple[str, str, str, float]] = set()
    for document in documents:
        for row in document["capacities"]:
            rows.add(
                (
                    document[row["entity"]]["stable_key"],
                    row["metric"],
                    row["stage"],
                    row["base"],
                )
            )
    return rows


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise OfficialCanadaMexicoCaribbeanGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"curated source is absent: {source}"
            )
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"curated source differs: {name}"
            )
        if stat.S_IMODE(source.stat().st_mode) != 0o444:
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"curated source mode differs: {name}"
            )

    documents = list(expected.values())
    statuses = [document["lifecycle"][0]["value"] for document in documents]
    if statuses.count("under_construction") != 2 or statuses.count("operational") != 4:
        raise OfficialCanadaMexicoCaribbeanGapError("lifecycle boundary differs")
    if sum(len(document["operating_models"]) for document in documents) != 6:
        raise OfficialCanadaMexicoCaribbeanGapError("operating-model count differs")
    if {
        observation["value"]
        for document in documents
        for observation in document["operating_models"]
    } != {"colocation"}:
        raise OfficialCanadaMexicoCaribbeanGapError("operating-model value differs")
    if any(document["workloads"] for document in documents):
        raise OfficialCanadaMexicoCaribbeanGapError(
            "design-purpose language became workload"
        )

    capacity_rows = _expected_capacity_rows(documents)
    expected_capacity_rows = {
        (
            "curated:qscale-q01-levis-campus:building-b",
            "critical_it_mw",
            "design",
            60.0,
        ),
        (
            "curated:estructure-cal3-rocky-view-campus:initial-build",
            "critical_it_mw",
            "design",
            60.0,
        ),
        (
            "curated:estructure-cal3-rocky-view-campus:initial-build",
            "gross_facility_mw",
            "design",
            90.0,
        ),
        (
            "curated:cologix-mtl8-montreal-data-center:initial-build",
            "gross_facility_mw",
            "design",
            21.0,
        ),
        (
            "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
            "critical_it_mw",
            "operational",
            12.0,
        ),
        (
            "curated:odata-dc-qr04-san-miguel-de-allende",
            "critical_it_mw",
            "design",
            24.0,
        ),
        (
            "curated:odata-dc-qr03-queretaro-campus:first-facility",
            "critical_it_mw",
            "operational",
            72.0,
        ),
        (
            "curated:odata-dc-qr03-queretaro-campus",
            "critical_it_mw",
            "design",
            300.0,
        ),
    }
    if capacity_rows != expected_capacity_rows:
        raise OfficialCanadaMexicoCaribbeanGapError(
            f"capacity boundary differs: {capacity_rows!r}"
        )

    coordinate_rows = {
        (
            document[entity]["stable_key"],
            document[entity]["coordinates"]["latitude"],
            document[entity]["coordinates"]["longitude"],
            document[entity]["method"],
        )
        for document in documents
        for entity in ("campus", "project")
        if document[entity]["coordinates"] is not None
    }
    if coordinate_rows != {
        (
            "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
            20.907398,
            -100.62028,
            "authoritative_site_plan",
        ),
        (
            "curated:equinix-mo2-monterrey-data-center:phase-1",
            25.725216372664335,
            -100.13271303039684,
            "authoritative_site_plan",
        ),
    }:
        raise OfficialCanadaMexicoCaribbeanGapError(
            f"source-reported coordinate boundary differs: {coordinate_rows!r}"
        )
    if any(
        document[entity]["geometry"] is not None
        for document in documents
        for entity in ("campus", "project")
    ):
        raise OfficialCanadaMexicoCaribbeanGapError("source invented explicit geometry")
    cal3 = expected[SOURCE_FILENAMES[1]]
    if any(cal3[entity]["coordinates"] is not None for entity in ("campus", "project")):
        raise OfficialCanadaMexicoCaribbeanGapError("unbound CAL-3 coordinate survived")
    mo2 = expected[SOURCE_FILENAMES[4]]
    if mo2["capacities"]:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "MO2 cabinet count became MW capacity"
        )
    return _source_records(expected)


def _validate_source_collisions() -> None:
    documents = expected_source_documents()
    stable_keys = [
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    ]
    evidence_keys = [
        row["key"] for document in documents.values() for row in document["evidence"]
    ]
    paths = [f"sources/{name}" for name in SOURCE_FILENAMES]
    collisions = {
        "stable_keys": sorted(
            {value for value in stable_keys if stable_keys.count(value) > 1}
        ),
        "evidence_keys": sorted(
            {value for value in evidence_keys if evidence_keys.count(value) > 1}
        ),
        "paths": sorted({value for value in paths if paths.count(value) > 1}),
    }
    if any(collisions.values()):
        raise OfficialCanadaMexicoCaribbeanGapError(
            f"curated source collision: {collisions!r}"
        )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip("/")


def _nested_strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, Mapping):
        return {text for nested in value.values() for text in _nested_strings(nested)}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {text for nested in value for text in _nested_strings(nested)}
    return set()


def _strings_for_key(value: Any, token: str) -> set[str]:
    if isinstance(value, Mapping):
        found: set[str] = set()
        for key, nested in value.items():
            if token in str(key).casefold():
                found.update(_nested_strings(nested))
            found.update(_strings_for_key(nested, token))
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {text for nested in value for text in _strings_for_key(nested, token)}
    return set()


def _selected_v83_documents() -> list[Mapping[str, Any]]:
    definition = json.loads(V83_DEFINITION.read_text(encoding="utf-8"))
    documents: list[Mapping[str, Any]] = []
    for row in definition["curated_inputs"]:
        source = ROOT / row["path"]
        document = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            documents.append(document)
    return documents


def _v83_duplicate_witness(
    planned: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = list((planned or expected_source_documents()).values())
    planned_stable = {
        document[entity]["stable_key"]
        for document in documents
        for entity in ("campus", "project")
    }
    planned_evidence = {
        row["key"] for document in documents for row in document["evidence"]
    }
    existing_stable: set[str] = set()
    existing_evidence: set[str] = set()
    existing_names: set[str] = set()
    existing_urls: set[str] = set()
    for document in _selected_v83_documents():
        existing_names.update(
            _normalize_text(text) for text in _strings_for_key(document, "alias")
        )
        existing_urls.update(
            _normalize_text(text) for text in _strings_for_key(document, "url")
        )
        for entity in ("campus", "project"):
            record = document.get(entity)
            if isinstance(record, dict):
                if isinstance(record.get("stable_key"), str):
                    existing_stable.add(record["stable_key"])
                if isinstance(record.get("name"), str):
                    existing_names.add(_normalize_text(record["name"]))
        for row in document.get("evidence", []):
            if not isinstance(row, dict):
                continue
            if isinstance(row.get("key"), str):
                existing_evidence.add(row["key"])
            if isinstance(row.get("source_url"), str):
                existing_urls.add(_normalize_text(row["source_url"]))
    with V83_ENTITIES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("name"):
                existing_names.add(_normalize_text(row["name"]))
            if row.get("source_url"):
                existing_urls.add(_normalize_text(row["source_url"]))
    alias_overlap = sorted(
        alias for alias in PLANNED_ALIASES if _normalize_text(alias) in existing_names
    )
    url_overlap = sorted(
        url for url in PLANNED_URLS if _normalize_text(url) in existing_urls
    )
    stable_overlap = sorted(planned_stable & existing_stable)
    evidence_overlap = sorted(planned_evidence & existing_evidence)
    if alias_overlap or url_overlap or stable_overlap or evidence_overlap:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "planned candidate duplicates accepted v83: "
            f"aliases={alias_overlap!r}, urls={url_overlap!r}, "
            f"stable={stable_overlap!r}, evidence={evidence_overlap!r}"
        )
    return {
        "planned_identity_aliases_checked": len(PLANNED_ALIASES),
        "planned_source_urls_checked": len(PLANNED_URLS),
        "planned_stable_keys_checked": len(planned_stable),
        "planned_evidence_keys_checked": len(planned_evidence),
        "v83_name_or_alias_exact_normalized_collisions": 0,
        "v83_source_url_exact_normalized_collisions": 0,
        "v83_stable_key_collisions": 0,
        "v83_evidence_key_collisions": 0,
    }


def _validate_v83_nonmutation() -> None:
    for source, pin in V83_PINS.items():
        _pin(source, pin)
    if tree_digest(V83_RELEASE) != V83_TREE_SHA256:
        raise OfficialCanadaMexicoCaribbeanGapError("accepted v83 release tree differs")
    definition = json.loads(V83_DEFINITION.read_text(encoding="utf-8"))
    inputs = definition.get("curated_inputs", [])
    if len(inputs) != V83_INPUT_COUNT:
        raise OfficialCanadaMexicoCaribbeanGapError("accepted v83 input count differs")
    selected = {row["path"] for row in inputs}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "v83 unexpectedly selects a new source path"
        )
    kio_path = str(KIO_GUATEMALA_SOURCE.relative_to(ROOT))
    if kio_path not in selected:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "v83 KIO Guatemala duplicate witness is absent"
        )
    _pin(KIO_GUATEMALA_SOURCE, KIO_GUATEMALA_PIN)
    with V83_ENTITIES.open(encoding="utf-8", newline="") as handle:
        kio_rows = [
            row
            for row in csv.DictReader(handle)
            if row.get("stable_key") == KIO_GUATEMALA_STABLE_KEY
        ]
    if (
        len(kio_rows) != 1
        or kio_rows[0].get("snapshot_evidence_id") != KIO_GUATEMALA_EVIDENCE_ID
    ):
        raise OfficialCanadaMexicoCaribbeanGapError(
            "v83 KIO Guatemala exact duplicate witness differs"
        )
    _v83_duplicate_witness()


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialCanadaMexicoCaribbeanGapError(
            f"capture directory is absent or unsafe: {directory}"
        )
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "capture directory file count differs"
        )
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialCanadaMexicoCaribbeanGapError(
            "capture directory contains a non-file"
        )
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "capture directory total bytes differs"
        )
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialCanadaMexicoCaribbeanGapError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "capture directory closed set differs"
        )
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for name in SOURCE_FILENAMES:
            adapter.import_file(
                connection,
                paths[name],
                recorded_at=recorded_at,
            )
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
            "lifecycle_observations": 6,
            "operating_model_observations": 6,
            "workload_observations": 0,
            "capacity_estimates": 8,
        }
        if counts != expected:
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"offline import counts differ: {counts!r}"
            )
        capacity_rows = {
            tuple(row)
            for row in connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.base "
                "FROM capacity_estimates AS c "
                "JOIN entities AS e ON e.id = c.entity_id"
            )
        }
        expected_rows = _expected_capacity_rows(
            list(expected_source_documents().values())
        )
        if capacity_rows != expected_rows:
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"offline capacity rows differ: {capacity_rows!r}"
            )
        coordinate_rows = {
            tuple(row)
            for row in connection.execute(
                "SELECT e.stable_key, s.latitude, s.longitude "
                "FROM entity_snapshots AS s "
                "JOIN entities AS e ON e.id = s.entity_id "
                "WHERE s.latitude IS NOT NULL OR s.longitude IS NOT NULL"
            )
        }
        if coordinate_rows != {
            (
                "curated:odata-dc-qr04-san-miguel-de-allende:phase-1",
                20.907398,
                -100.62028,
            ),
            (
                "curated:equinix-mo2-monterrey-data-center:phase-1",
                25.725216372664335,
                -100.13271303039684,
            ),
        }:
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"offline coordinate rows differ: {coordinate_rows!r}"
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
        raise OfficialCanadaMexicoCaribbeanGapError(
            "artifact must be an ordinary directory"
        )
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialCanadaMexicoCaribbeanGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialCanadaMexicoCaribbeanGapError(
            "artifact contains a non-ordinary file"
        )
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialCanadaMexicoCaribbeanGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialCanadaMexicoCaribbeanGapError("artifact file mode differs")

    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialCanadaMexicoCaribbeanGapError("manifest JSON is not canonical")
    review_count = len(_review_candidates())
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 6 + review_count
        or manifest.get("curated_source_records") != 6
        or manifest.get("seed_eligible_source_records") != 6
        or manifest.get("review_only_candidates") != review_count
        or manifest.get("regional_completeness_claimed") is not False
        or manifest.get("caribbean_completeness_claimed") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or manifest.get("downstream_product_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialCanadaMexicoCaribbeanGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialCanadaMexicoCaribbeanGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"manifest file pin differs: {row['path']}"
            )
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialCanadaMexicoCaribbeanGapError("manifest checksum differs")
    expected = _artifact_documents(
        manifest["recorded_at"],
        expected_source_documents(),
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialCanadaMexicoCaribbeanGapError(
                f"artifact content differs: {name}"
            )
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialCanadaMexicoCaribbeanGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialCanadaMexicoCaribbeanGapError(
            "validation wall clock lacks timezone"
        )
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialCanadaMexicoCaribbeanGapError(
                "artifact recorded_at is not live"
            )
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialCanadaMexicoCaribbeanGapError(
                "capture retrieval post-dates recorded_at"
            )
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
        raise OfficialCanadaMexicoCaribbeanGapError(
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


def _all_stage_paths(
    source_stage: Path,
    artifact_stage: Path,
) -> tuple[Path, ...]:
    return (
        source_stage,
        *sorted(source_stage.iterdir(), key=lambda item: item.name),
        artifact_stage,
        *sorted(artifact_stage.iterdir(), key=lambda item: item.name),
    )


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
        raise OfficialCanadaMexicoCaribbeanGapError(
            "recorded_at must be future before staging"
        )
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".official-builds-canada-mexico-caribbean-gap.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(
            prefix=f".{ARTIFACT_ID}.",
            dir=ARTIFACT_ROOT,
        )
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
            raise OfficialCanadaMexicoCaribbeanGapError(
                "private staging did not finish before recorded_at"
            )
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
                raise OfficialCanadaMexicoCaribbeanGapError(
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
        if not _has_identity(
            ARTIFACT,
            prepared.artifact_identity,
            directory=True,
        ):
            raise OfficialCanadaMexicoCaribbeanGapError(
                "artifact identity changed on promotion"
            )
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
        raise OfficialCanadaMexicoCaribbeanGapError(
            "both capture origin and Trash destination exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return (
        datetime.fromtimestamp(target, UTC)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish six sources and the complete bounded assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v83_nonmutation()
    capture_directory = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
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
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))
    _validate_v83_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 6 + len(_review_candidates()),
            "source_records": 6,
            "seed_eligible": 6,
            "review_only": len(_review_candidates()),
            "evidence": 11,
            "entities": 12,
            "lifecycle": 6,
            "operating_models": 6,
            "workloads": 0,
            "capacities": 8,
            "coordinates": 2,
            "geometry": 0,
            "source_reported_project_map_points": 2,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
