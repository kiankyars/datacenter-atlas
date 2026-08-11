"""Publish four governed official current-build source records.

This carrier is intentionally source-only. It preserves direct response bytes,
archived replays of exact official URLs where live publisher routes failed, and
strictly dated lifecycle observations without integrating an open-seed or any
downstream product.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from . import global_official_builds_six_candidate_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-batam-jakarta-hanoi-bue1-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-batam-jakarta-hanoi-bue1.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-global-official-gap-20260722.k6hMux")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-global-official-gap-20260722.k6hMux")
CAPTURE_FILE_COUNT = 50
CAPTURE_TOTAL_BYTES = 7_661_235
CAPTURE_TREE_SHA256 = "7f011dad62d1e10f33a8c1e6722adddd4395b522cea605d5fec95e2b07e2ae99"
LATEST_CAPTURE_AT = "2026-07-22T03:31:08Z"

SOURCE_FILENAMES = (
    "curated-official-2026-07-22-neutradc-nxera-batam-btm1-current-build.json",
    "curated-official-2026-07-22-cirion-bue1-expansion-current-build.json",
    "curated-official-2026-07-22-edgnex-second-jakarta-ai-current-build.json",
    "curated-official-2026-07-22-cmc-creative-space-hanoi-data-center-tower-current-build.json",
)

V93_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v93.json"
V93_RELEASE = ROOT / "releases/2026-07-21-open-seed-v93"
V93_MANIFEST = V93_RELEASE / "manifest.json"
V93_ENTITIES = V93_RELEASE / "entities.csv"
V93_SOURCE_INPUTS = V93_RELEASE / "source_inputs.json"
V93_PINS = {
    V93_DEFINITION: (
        110_743,
        "cf8ed21cd0816f457fa2cede36fbf1bf012d62ed61d03a5e3213de9946394e9c",
    ),
    V93_MANIFEST: (
        16_832,
        "9a5b39004ab1a4c7994ad653d5d9603572b4a47a3c502ea222eeae38d32fa05c",
    ),
    V93_ENTITIES: (
        1_029_791,
        "f690d838165ced6822b891f5099adea82db46fba97e53dbcb462328b5af6628b",
    ),
    V93_SOURCE_INPUTS: (
        414_095,
        "81cf558da4aef80bdc957116ceda84cd565960b6471db0ada95cddd02e0f483e",
    ),
}
V93_TREE_SHA256 = "71c531ffa7f8383e2ae553a71abe15e940e8d6251acccbf17556bc492df78f0d"
V93_INPUT_COUNT = 488
V93_ENTITY_COUNT = 994

INFLIGHT_V94_SOURCE_FILENAMES = (
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json",
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-3-current-build.json",
    "curated-official-2026-07-22-cyrusone-fra5-hanau-halls-2-3-current-build.json",
    "curated-official-2026-07-22-cyrusone-wood-dale-phase-1-current-build.json",
    "curated-official-2026-07-22-beale-tulsa-project-clydesdale-initial-phase-current-build-v2.json",
    "curated-official-2026-07-22-beale-pima-project-blue-bobcat-site-preparation-v2.json",
    "curated-official-2026-07-22-bitdeer-wenatchee-ai-conversion-current-build.json",
    "curated-official-2026-07-22-bitdeer-massillon-reconstruction-current-build.json",
    "curated-official-2026-07-22-hut8-river-bend-current-build.json",
    "curated-official-2026-07-22-goodman-databank-lax01-enrichment.json",
)

CMC_HISTORICAL_SOURCE = SOURCES_ROOT / (
    "curated-official-2026-07-21-cmc-creative-space-hanoi-phase-2-historical.json"
)
CMC_HISTORICAL_PIN = (
    4_908,
    "5bdf8e19ca3528b8533449f38eacb56e8778adf3fd2e5c3ff57f88e89a68985b",
)

BTM_CAMPUS = "curated:neutradc-nxera-batam-campus"
BTM_PROJECT = f"{BTM_CAMPUS}:btm-1"
CIRION_CAMPUS = "curated:cirion-bue1-buenos-aires-data-center"
CIRION_PROJECT = f"{CIRION_CAMPUS}:2025-expansion"
JAKARTA_CAMPUS = "curated:edgnex-second-jakarta-ai-data-center"
JAKARTA_PROJECT = f"{JAKARTA_CAMPUS}:phase-1-early-construction"
CMC_CAMPUS = "curated:cmc-creative-space-hanoi"
CMC_PROJECT = f"{CMC_CAMPUS}:data-center-tower"

BTM_TOPPING_EVIDENCE = (
    "neutradc-nxera-batam-btm1-topping-2025-10-30-captured-2026-07-22"
)
BTM_ITLOAD_EVIDENCE = "telkom-batam-btm1-it-load-2025-11-04-captured-2026-07-22"
BTM_LATER_EVIDENCE = (
    "telkom-batam-btm1-preoperation-update-2026-06-05-captured-2026-07-22"
)
CIRION_EXPANSION_EVIDENCE = "cirion-bue1-expansion-2025-08-21-captured-2026-07-22"
CIRION_FACILITY_EVIDENCE = "cirion-bue1-current-facility-page-captured-2026-07-22"
JAKARTA_EVIDENCE = (
    "damac-second-jakarta-early-construction-2025-06-17-archived-captured-2026-07-22"
)
CMC_RELEASE_EVIDENCE = (
    "cmc-creative-space-hanoi-groundbreaking-2025-06-01-archived-captured-2026-07-22"
)
CMC_LANDING_EVIDENCE = "cmc-annual-report-2024-landing-archived-captured-2026-07-22"
CMC_REPORT_EVIDENCE = "cmc-annual-report-2024-pdf-captured-2026-07-22"

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

_canonical = publication._canonical
_promote_noreplace = publication._promote_noreplace
_identity = publication._identity


class GlobalOfficialGapError(RuntimeError):
    """Raised when an evidence, semantic, or publication invariant differs."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GlobalOfficialGapError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise GlobalOfficialGapError(f"pinned ordinary file is absent: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise GlobalOfficialGapError(f"pinned file differs: {path}: {actual!r}")


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


def _has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    correct_type = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    return correct_type and (metadata.st_dev, metadata.st_ino) == identity


CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "cirion_bue1.body": (
        84_712,
        "a598a4134bb987730f4a3286310ea324f8bd805f4c1909e59e85a44140409d83",
    ),
    "cirion_bue1.headers": (
        1_722,
        "acbab5a1250f1d8ea05a0ec0a767e9d60f0b65a7c892ccd2cd212d0da812f5cd",
    ),
    "cirion_bue1.writeout": (
        12_885,
        "740d17e409a70cc21df0690e4012606170ac330204d4bac238c270220d22be61",
    ),
    "cirion_bue1_facility.body": (
        257_992,
        "01071c3faef040b0ba1b216e44fa6cdb88c216ef2b50b307ded86fed8da64186",
    ),
    "cirion_bue1_facility.headers": (
        883,
        "a7dae42a5e259753a2e92b932d7797e223cb69fec4a8e551e394553a94dc82d6",
    ),
    "cirion_bue1_facility.writeout": (
        12_786,
        "08310ebdba40ff398dcea11150cd746cf06d8437402fa7ccbb69390a4ef75927",
    ),
    "cmc_annual_landing.body": (
        146,
        "32f2fa940d4b4fe19aca1e53a24e5aac29c57b7c5ee78588325b87f1b649c864",
    ),
    "cmc_annual_landing.headers": (
        163,
        "dae105db301fc4cdcda107d60f310d2dd027406cc62b48bba44dc985ab99afb9",
    ),
    "cmc_annual_landing.writeout": (
        16_730,
        "7cb9e83a2ecb6c18ca8b86cbb3abbc1eb67ba2e0d5474f1732e2486ade36da3f",
    ),
    "cmc_annual_landing_wayback.body": (
        52_363,
        "e8ed447ceabf337adb6f49afb97b372014f706a5f44b33cb33974eee32362182",
    ),
    "cmc_annual_landing_wayback.headers": (
        3_301,
        "62b8ec6fccfce781deb8c83b588792fcddc8c675f1af5d348a05f48f582138a5",
    ),
    "cmc_annual_landing_wayback.writeout": (
        18_647,
        "09a97c9aea25ee5848a4c96cf26867a2731f5754067c7c5a8de45996578f4324",
    ),
    "cmc_annual_pdf.body": (
        5_259_042,
        "97f94110030f0b5289740324c3625b0480d754c672d364045b5271c42bed3c64",
    ),
    "cmc_annual_pdf.headers": (
        421,
        "a40b641da32468acc190d994288ff266e1568358a52277a4895a60ae020cd1d6",
    ),
    "cmc_annual_pdf.writeout": (
        16_812,
        "8a8bae0f129312d1a47a401667b8009dcb67e0c9b9998c70c607e07f5478d6f0",
    ),
    "cmc_hanoi_release.body": (
        146,
        "32f2fa940d4b4fe19aca1e53a24e5aac29c57b7c5ee78588325b87f1b649c864",
    ),
    "cmc_hanoi_release.headers": (
        163,
        "aa700a8c89591c3f18f55a0844512142aaa63380860c368b75c6c2ddb10c0d6d",
    ),
    "cmc_hanoi_release.writeout": (
        17_037,
        "a9bd4b7844bb0c18bccfa58ba8dd64d3272282933cc926c769aa344ecef19d6e",
    ),
    "cmc_hanoi_release_wayback.body": (
        58_601,
        "5391a10d9112112778593d5800351591511bf8de75d3039b8fcb89df9b3ff3c4",
    ),
    "cmc_hanoi_release_wayback.headers": (
        3_528,
        "a7063db5b50bd717c3b527dbefe63726bb6f7c591c18817afa2978a5c2a7cd2a",
    ),
    "cmc_hanoi_release_wayback.writeout": (
        18_956,
        "0a47aa8358f7230e86f8d378beaeb062e0c77e243ce0208aab893a23f243f16f",
    ),
    "damac_jakarta.body": (
        110_343,
        "64be87beef05a0dd10524fd6a6e87fcf3aa271b0c137a40751a82c4967015414",
    ),
    "damac_jakarta.headers": (
        4_758,
        "76b8149c3cde3568fc262698d02a4809004108f5cf9a90e300ed9e2b8e90e10c",
    ),
    "damac_jakarta.writeout": (
        1_985,
        "b0faa73a7d8cd84fcab740af442d86210d27de3e119c426a1c2ac455de6ae875",
    ),
    "damac_jakarta_enae.body": (
        110_357,
        "1a3e7dfc9faf72a5459320e0507aa729e112ec90e7bd07e5e4cf6b81412496ee",
    ),
    "damac_jakarta_enae.headers": (
        2_378,
        "f620340a8b8e5a779d6c10318731bfef3e9f29b78fb419ce33de4ad5a5967377",
    ),
    "damac_jakarta_enae.writeout": (
        13_370,
        "a31ec1c3cc7211788b324b35580266d5ffc120f153b91606e95e06ce64c995e1",
    ),
    "damac_jakarta_encn.body": (
        110_394,
        "419993c4f631489ae3e4bbc5f04aa99d70d6f17475be7f208abf4fcba3e1f02b",
    ),
    "damac_jakarta_encn.headers": (
        2_379,
        "97920e538e19784273f55e86638a845554b8ddc514f84235d2abbd33b5452ef8",
    ),
    "damac_jakarta_encn.writeout": (
        13_370,
        "b5e01058e05a08543166a190a5e3845bb35932976b9884ec1071598e5feaf2c1",
    ),
    "damac_jakarta_enru.body": (
        110_394,
        "2949cee06416eacc1ee9e52cf9d91cb17272f92e5cf62efbc39eda1010688225",
    ),
    "damac_jakarta_enru.headers": (
        2_377,
        "181876da38a798e8a67532b4068940008016cf98cfba446716055a088feb8db5",
    ),
    "damac_jakarta_enru.writeout": (
        13_369,
        "11c5a6be51e237e60904d791c8b56ee66d81885a6fef69542aedc2e527d75f75",
    ),
    "damac_jakarta_wayback.body": (
        185_189,
        "31b746886040c42e77f8b2662eb4531c9a7591fa3360aae76e4e78502a47b225",
    ),
    "damac_jakarta_wayback.headers": (
        6_861,
        "a703a27eb85046a894ce90fd692911245a96c674c9ac94b8f0d35b124fc582ef",
    ),
    "damac_jakarta_wayback.writeout": (
        18_944,
        "ea3e7791087ae28e3840c0d9d08fffdc2eef3fec2ae4c325b30cb738e3e38fd9",
    ),
    "damac_rebrand.body": (
        129_163,
        "598d3dab49ed8b07accf4f4602f1acf8ee5ed156e4bd2abc937ae2620734dfbc",
    ),
    "damac_rebrand.headers": (
        2_212,
        "3d6b41e5d83ae78b0996dcef5d7389b4cf0fe5fb064fd4bc1697aa70bc394894",
    ),
    "damac_rebrand.writeout": (
        13_249,
        "6c454f59002af80368e1d8619b35408c57ac1adf03aeb3fb90b50b8b9d172c28",
    ),
    "neutradc_topping.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "neutradc_topping.writeout": (
        1_851,
        "1ad70378a370b73c03da7ec239feecf6668628e73163cc31a21bdd52f72b81fc",
    ),
    "neutradc_topping_wayback.body": (
        687_666,
        "c4ba0e7f61f108faf15e549d8643b7ad197570df7b0c17fefe2711c2978b39e7",
    ),
    "neutradc_topping_wayback.headers": (
        3_239,
        "326af479cbcb264ef48e05a8a544be156edd53edffa2d84234a24f0b73f90813",
    ),
    "neutradc_topping_wayback.writeout": (
        18_857,
        "0ce2415a81638968f7f338df395c0159d8fec37eb0b13581248935f74ea9eae9",
    ),
    "telkom_batam_itload.body": (
        114_512,
        "25cd2828ab0e97e0c69871a1f8d831929a76934a6f880a3b790bd95468813abb",
    ),
    "telkom_batam_itload.headers": (
        1_276,
        "3cfe1cfc0d33c061033eafb6e7e266962e3f754845a46e52ecd4e60bf01543ae",
    ),
    "telkom_batam_itload.writeout": (
        14_289,
        "545a0429f8f1283ae82036bbbd224452b9b75b213e0b0181763e518a6ce4a14d",
    ),
    "telkom_batam_later.body": (
        115_881,
        "ddfa063b513e053cc5807c1518ec8b20457effb187d6d0b713f1824e84faf1a6",
    ),
    "telkom_batam_later.headers": (
        1_276,
        "588967427e3ed0a45586bd6f0edc2b892adea843cbc8d7612eb8facde8af3523",
    ),
    "telkom_batam_later.writeout": (
        14_260,
        "e7c962caf575a5977de700823e799600de4d6e7aee0b9bd5c376da48b2333610",
    ),
}


@dataclass(frozen=True)
class CaptureSpec:
    requested_url: str
    effective_url: str
    completed_at: str
    exit_code: int
    http_status: int
    http_version: str
    content_type: str | None
    wire_bytes: int
    header_bytes: int
    header_count: int
    error: str | None = None
    original_official_url: str | None = None
    archive_timestamp: str | None = None


CAPTURE_SPECS: Mapping[str, CaptureSpec] = {
    "cirion_bue1": CaptureSpec(
        "https://press.ciriontechnologies.com/en/2025/08/21/data-center-buenos-aires-digital-transformation-argentina/",
        "https://press.ciriontechnologies.com/en/2025/08/21/data-center-buenos-aires-digital-transformation-argentina/",
        "2026-07-22T03:27:55Z",
        0,
        200,
        "2",
        "text/html; charset=UTF-8",
        20_364,
        1_722,
        28,
    ),
    "cirion_bue1_facility": CaptureSpec(
        "https://www.ciriontechnologies.com/en/data-center/our-data-centers/buenos-aires-1/",
        "https://www.ciriontechnologies.com/en/data-center/our-data-centers/buenos-aires-1/",
        "2026-07-22T03:31:08Z",
        0,
        200,
        "2",
        "text/html; charset=UTF-8",
        55_887,
        883,
        17,
    ),
    "cmc_annual_landing": CaptureSpec(
        "https://www.cmc.com.vn/insight-detail/annual-report-2024-202507219021.html",
        "https://www.cmc.com.vn/insight-detail/annual-report-2024-202507219021.html",
        "2026-07-22T03:28:02Z",
        22,
        403,
        "1.1",
        "text/html; charset=utf-8",
        146,
        163,
        5,
        "HTTP response code said error",
    ),
    "cmc_annual_landing_wayback": CaptureSpec(
        "https://web.archive.org/web/20260215231822id_/https://www.cmc.com.vn/insight-detail/annual-report-2024-202507219021.html",
        "https://web.archive.org/web/20260215231822id_/https://www.cmc.com.vn/insight-detail/annual-report-2024-202507219021.html",
        "2026-07-22T03:31:06Z",
        0,
        200,
        "2",
        "text/html; charset=UTF-8",
        8_633,
        3_301,
        43,
        original_official_url="https://www.cmc.com.vn/insight-detail/annual-report-2024-202507219021.html",
        archive_timestamp="20260215231822",
    ),
    "cmc_annual_pdf": CaptureSpec(
        "https://cdn.cmc.com.vn/img/posts/files/20250718%20-%20CMG%20-%20Annual%20report%202024%20-%20signed.pdf",
        "https://cdn.cmc.com.vn/img/posts/files/20250718%20-%20CMG%20-%20Annual%20report%202024%20-%20signed.pdf",
        "2026-07-22T03:28:07Z",
        0,
        200,
        "1.1",
        "application/pdf",
        5_259_042,
        421,
        11,
    ),
    "cmc_hanoi_release": CaptureSpec(
        "https://www.cmc.com.vn/insight-detail/cmc-creative-space-hanoi-a-new-symbol-for-the-make-in-vietnam-artificial-intelligence-ecosystem-202506028821.html",
        "https://www.cmc.com.vn/insight-detail/cmc-creative-space-hanoi-a-new-symbol-for-the-make-in-vietnam-artificial-intelligence-ecosystem-202506028821.html",
        "2026-07-22T03:28:01Z",
        22,
        403,
        "1.1",
        "text/html; charset=utf-8",
        146,
        163,
        5,
        "HTTP response code said error",
    ),
    "cmc_hanoi_release_wayback": CaptureSpec(
        "https://web.archive.org/web/20260419043023id_/https://www.cmc.com.vn/insight-detail/cmc-creative-space-hanoi-a-new-symbol-for-the-make-in-vietnam-artificial-intelligence-ecosystem-202506028821.html",
        "https://web.archive.org/web/20260419043023id_/https://www.cmc.com.vn/insight-detail/cmc-creative-space-hanoi-a-new-symbol-for-the-make-in-vietnam-artificial-intelligence-ecosystem-202506028821.html",
        "2026-07-22T03:31:05Z",
        0,
        200,
        "2",
        "text/html; charset=UTF-8",
        13_120,
        3_528,
        43,
        original_official_url="https://www.cmc.com.vn/insight-detail/cmc-creative-space-hanoi-a-new-symbol-for-the-make-in-vietnam-artificial-intelligence-ecosystem-202506028821.html",
        archive_timestamp="20260419043023",
    ),
    "damac_jakarta": CaptureSpec(
        "https://www.damacgroup.com/en-gb/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "https://www.damacgroup.com/en-gb/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "2026-07-22T03:28:00Z",
        22,
        500,
        "2",
        "text/html; charset=utf-8",
        27_985,
        2_378,
        21,
        "HTTP response code said error",
    ),
    "damac_jakarta_enae": CaptureSpec(
        "https://www.damacgroup.com/en-ae/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "https://www.damacgroup.com/en-ae/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "2026-07-22T03:29:02Z",
        22,
        500,
        "2",
        "text/html; charset=utf-8",
        27_999,
        2_378,
        21,
        "HTTP response code said error",
    ),
    "damac_jakarta_encn": CaptureSpec(
        "https://www.damacgroup.com/en-cn/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "https://www.damacgroup.com/en-cn/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "2026-07-22T03:29:04Z",
        22,
        500,
        "2",
        "text/html; charset=utf-8",
        27_999,
        2_379,
        21,
        "HTTP response code said error",
    ),
    "damac_jakarta_enru": CaptureSpec(
        "https://www.damacgroup.com/en-ru/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "https://www.damacgroup.com/en-ru/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "2026-07-22T03:29:09Z",
        22,
        500,
        "2",
        "text/html; charset=utf-8",
        28_000,
        2_377,
        21,
        "HTTP response code said error",
    ),
    "damac_jakarta_wayback": CaptureSpec(
        "https://web.archive.org/web/20260122183232id_/https://www.damacgroup.com/en-gb/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "https://web.archive.org/web/20260122183232id_/https://www.damacgroup.com/en-gb/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        "2026-07-22T03:30:08Z",
        0,
        200,
        "2",
        "text/html; charset=utf-8",
        42_255,
        6_861,
        47,
        original_official_url="https://www.damacgroup.com/en-gb/d-hub/press-releases/edgnex-data-centers-by-damac-announces-2-3-billion-ai-focused-data-center-in-jakarta-indonesia/",
        archive_timestamp="20260122183232",
    ),
    "damac_rebrand": CaptureSpec(
        "https://www.damacgroup.com/en-cn/d-hub/press-releases/damac-group-unveils-damac-digital-as-global-expansion-accelerates/",
        "https://www.damacgroup.com/en-cn/d-hub/press-releases/damac-group-unveils-damac-digital-as-global-expansion-accelerates/",
        "2026-07-22T03:29:11Z",
        22,
        500,
        "2",
        "text/html; charset=utf-8",
        35_540,
        2_212,
        20,
        "HTTP response code said error",
    ),
    "neutradc_topping": CaptureSpec(
        "https://www.neutradc.com/news/51114/telkomgroup-tops-off-neutradc-nxera-batam-hyperscale-data-center-to-power-the-ai-ecosystem",
        "https://www.neutradc.com/news/51114/telkomgroup-tops-off-neutradc-nxera-batam-hyperscale-data-center-to-power-the-ai-ecosystem",
        "2026-07-22T03:27:51Z",
        28,
        0,
        "0",
        None,
        0,
        0,
        0,
        "SSL connection timeout",
    ),
    "neutradc_topping_wayback": CaptureSpec(
        "https://web.archive.org/web/20260316065909id_/https://www.neutradc.com/news/51114/telkomgroup-tops-off-neutradc-nxera-batam-hyperscale-data-center-to-power-the-ai-ecosystem",
        "https://web.archive.org/web/20260316065909id_/https://www.neutradc.com/news/51114/telkomgroup-tops-off-neutradc-nxera-batam-hyperscale-data-center-to-power-the-ai-ecosystem",
        "2026-07-22T03:31:05Z",
        0,
        200,
        "2",
        "text/html; charset=utf-8",
        165_631,
        3_239,
        38,
        original_official_url="https://www.neutradc.com/news/51114/telkomgroup-tops-off-neutradc-nxera-batam-hyperscale-data-center-to-power-the-ai-ecosystem",
        archive_timestamp="20260316065909",
    ),
    "telkom_batam_itload": CaptureSpec(
        "https://www.telkom.co.id/sites/berita/id_ID/news/telkomgroup-jadikan-batam-sebagai-pusat-hyperscale-data-center-berbasis-ai-melalui-neutradc-nxera-batam-3401",
        "https://www.telkom.co.id/sites/berita/id_ID/news/telkomgroup-jadikan-batam-sebagai-pusat-hyperscale-data-center-berbasis-ai-melalui-neutradc-nxera-batam-3401",
        "2026-07-22T03:27:53Z",
        0,
        200,
        "2",
        "text/html; charset=utf-8",
        114_512,
        1_276,
        20,
    ),
    "telkom_batam_later": CaptureSpec(
        "https://www.telkom.co.id/sites/berita/id_ID/news/data-center-terisi-penuh-sebelum-beroperasi-telkom-percepat-ekspansi-kapasitas-neutradc-di-batam-3797",
        "https://www.telkom.co.id/sites/berita/id_ID/news/data-center-terisi-penuh-sebelum-beroperasi-telkom-percepat-ekspansi-kapasitas-neutradc-di-batam-3797",
        "2026-07-22T03:27:55Z",
        0,
        200,
        "2",
        "text/html; charset=utf-8",
        115_881,
        1_276,
        20,
    ),
}


def _entity(
    *,
    stable_key: str,
    name: str,
    country: str,
    address: str,
    roles: Mapping[str, Sequence[str]],
    evidence_key: str,
    as_of_date: str,
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": {key: list(value) for key, value in roles.items()},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _evidence(
    capture_id: str,
    *,
    key: str,
    title: str,
    publisher: str,
    source_family: str,
    published_at: str | None,
    excerpt: str,
    claim_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    spec = CAPTURE_SPECS[capture_id]
    body_name = f"{capture_id}.body"
    header_name = f"{capture_id}.headers"
    body_pin = CAPTURE_FILE_PINS[body_name]
    header_pin = CAPTURE_FILE_PINS[header_name]
    metadata: dict[str, Any] = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "content_hash_scope": (
            f"SHA-256 of the exact {body_pin[0]}-byte captured response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_sha256": header_pin[1],
        "capture_headers_bytes": header_pin[0],
        "requested_url": spec.requested_url,
        "effective_url": spec.effective_url,
        "retrieved_at_semantics": (
            "UTC whole-second completion time recorded immediately after curl returned"
        ),
        "request_credentials_supplied": False,
        "http_status": spec.http_status,
        "http_version_as_received": spec.http_version,
        "content_type": spec.content_type,
        "redirect_count": 0,
        "rights_scope": (
            "Compact factual extraction only; raw all-rights-reserved response bytes "
            "are not redistributed."
        ),
        "imagery_guardrail": (
            "Publisher imagery, satellite imagery, aerial imagery, computer vision, "
            "and analyst geolocation contribute no identity, lifecycle, capacity, "
            "coordinate, or geometry claim."
        ),
        **claim_metadata,
    }
    if spec.original_official_url:
        metadata.update(
            {
                "evidence_class": "archived_company_disclosure",
                "official_canonical_url": spec.original_official_url,
                "archive_replay_url": spec.effective_url,
                "archive_capture_timestamp": spec.archive_timestamp,
                "archive_transport": "Internet Archive Wayback raw replay",
                "live_origin_capture_used_for_claims": False,
            }
        )
    return {
        "key": key,
        "kind": "company_disclosure",
        "title": title,
        "source_url": spec.effective_url,
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": spec.completed_at,
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": body_pin[1],
        "metadata": metadata,
    }


def _batam_source() -> dict[str, Any]:
    evidence = [
        _evidence(
            "neutradc_topping_wayback",
            key=BTM_TOPPING_EVIDENCE,
            title=(
                "TelkomGroup Tops Off NeutraDC Nxera Batam Hyperscale Data "
                "Center to Power the AI Ecosystem"
            ),
            publisher="NeutraDC",
            source_family="neutradc_official_news_archived",
            published_at="2025-10-30",
            excerpt=(
                "The archived replay of NeutraDC's exact official page says BTM-1 "
                "in Kabil Industrial Estate reached topping off and has an initial "
                "IT load capacity of 18 MW."
            ),
            claim_metadata={
                "status_scope": (
                    "Topping off supports one shell observation for BTM-1 dated "
                    "2025-10-30. It does not establish completion, commissioning, "
                    "energization, occupancy, or operation."
                ),
                "capacity_scope": (
                    "The page literally assigns an initial 18 MW IT load to the first "
                    "building BTM-1. This supports one planned project critical-IT row."
                ),
                "future_phase_guardrail": (
                    "The 54 MW subsequent-phase figure is metadata only, is not assigned "
                    "to BTM-1, and creates no BTM-2 project or capacity row."
                ),
                "location_scope": (
                    "Kabil Industrial Estate, Batam is an authoritative locality, not "
                    "a parcel, point, footprint, coordinate, or geometry."
                ),
            },
        ),
        _evidence(
            "telkom_batam_itload",
            key=BTM_ITLOAD_EVIDENCE,
            title=(
                "TelkomGroup Positions Batam as an AI-Based Hyperscale Data "
                "Center Hub Through NeutraDC Nxera Batam"
            ),
            publisher="PT Telkom Indonesia (Persero) Tbk",
            source_family="telkom_indonesia_official_news",
            published_at="2025-11-04",
            excerpt=(
                "Telkom explicitly reports a target total IT load of 18 MW for the "
                "first building BTM-1 in Kabil Integrated Industrial Estate."
            ),
            claim_metadata={
                "capacity_corroboration_scope": (
                    "This direct official body independently corroborates the same "
                    "planned 18 MW BTM-1 critical-IT scope; it creates no duplicate row."
                ),
                "classification_guardrail": (
                    "General AI, cloud, Big Data, and ecosystem language creates no "
                    "operating-model or workload observation."
                ),
            },
        ),
        _evidence(
            "telkom_batam_later",
            key=BTM_LATER_EVIDENCE,
            title=(
                "Data Center Fully Allocated Before Operations, Telkom Accelerates "
                "NeutraDC Capacity Expansion in Batam"
            ),
            publisher="PT Telkom Indonesia (Persero) Tbk",
            source_family="telkom_indonesia_official_news",
            published_at="2026-06-05",
            excerpt=(
                "Telkom says BTM-1 was scheduled to become ready during 2026 and had "
                "secured partners for all capacity before operations."
            ),
            claim_metadata={
                "current_context_scope": (
                    "The June 2026 disclosure confirms BTM-1 remained pre-operational "
                    "at that date but supplies no later physical stage than topping off."
                ),
                "current_status_guardrail": (
                    "The persisted lifecycle remains the last physical shell observation "
                    "from 2025-10-30. Current status is not inferred."
                ),
                "future_campus_guardrail": (
                    "The 100 MW campus-development statement and planned BTM-2 response "
                    "to demand remain metadata only. No BTM-2 entity or capacity is added."
                ),
            },
        ),
    ]
    roles = {"developer": ["NeutraDC Nxera Batam"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=BTM_CAMPUS,
            name="NeutraDC Nxera Batam Campus",
            country="Indonesia",
            address="Kabil Industrial Estate, Batam, Indonesia",
            roles=roles,
            evidence_key=BTM_TOPPING_EVIDENCE,
            as_of_date="2025-10-30",
        ),
        "project": _entity(
            stable_key=BTM_PROJECT,
            name="NeutraDC Nxera Batam BTM-1",
            country="Indonesia",
            address="Kabil Industrial Estate, Batam, Indonesia",
            roles=roles,
            evidence_key=BTM_TOPPING_EVIDENCE,
            as_of_date="2025-10-30",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "shell",
                "evidence_key": BTM_TOPPING_EVIDENCE,
                "as_of_date": "2025-10-30",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 18,
                "base": 18,
                "high": 18,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": BTM_TOPPING_EVIDENCE,
                "as_of_date": "2025-10-30",
                "target_date": None,
                "notes": (
                    "Initial IT load explicitly assigned to the first building BTM-1. "
                    "It is not current load, consumption, gross facility power, grid "
                    "connection, generation, annual energy, or the 54/100 MW future scope."
                ),
            }
        ],
    }


def _cirion_source() -> dict[str, Any]:
    evidence = [
        _evidence(
            "cirion_bue1",
            key=CIRION_EXPANSION_EVIDENCE,
            title=(
                "Cirion Expands Its Data Center in Buenos Aires to Drive Digital "
                "Transformation in Argentina"
            ),
            publisher="Cirion Technologies",
            source_family="cirion_pressroom",
            published_at="2025-08-21",
            excerpt=(
                "Cirion says it was executing a new expansion of BUE1 that would add "
                "more than 2 MW of untyped capacity and about 160 racks."
            ),
            claim_metadata={
                "status_scope": (
                    "The active wording supports one expansion observation dated to "
                    "the release. It does not prove a finer construction stage or current "
                    "status after 2025-08-21."
                ),
                "capacity_guardrail": (
                    "More than 2 MW is not typed as critical IT, gross facility, grid "
                    "connection, generation, or current load and is not normalized."
                ),
                "rack_guardrail": (
                    "Approximately 160 additional racks remains descriptive metadata, "
                    "not a power, energy, utilization, or capacity conversion."
                ),
                "connectivity_guardrail": (
                    "Every PeeringDB-derived claim and all connectivity rankings are "
                    "explicitly excluded. The unrelated greater-than-20 MW statement for "
                    "SAN2, LIM2, and RIO2 is also excluded."
                ),
            },
        ),
        _evidence(
            "cirion_bue1_facility",
            key=CIRION_FACILITY_EVIDENCE,
            title="Buenos Aires 1 Data Center",
            publisher="Cirion Technologies",
            source_family="cirion_current_facility_pages",
            published_at=None,
            excerpt=(
                "Cirion's current BUE1 page gives the Av. del Campo 1301 address and "
                "describes the facility as carrier-neutral with colocation services."
            ),
            claim_metadata={
                "address_scope": (
                    "The exact publisher address supports the campus address only. The "
                    "2025 expansion project retains Buenos Aires-level locality."
                ),
                "operating_model_scope": (
                    "The current facility page explicitly offers colocation; this supports "
                    "one campus colocation observation dated to retrieval."
                ),
                "installed_power_guardrail": (
                    "The page's 7 MW installed figure is a whole-facility untyped power "
                    "figure. It is not assigned to the 2025 expansion, normalized, or "
                    "combined with the release's greater-than-2 MW statement."
                ),
                "connectivity_guardrail": (
                    "Carrier names, network counts, interconnection, peering counts, and "
                    "every PeeringDB-derived assertion are excluded."
                ),
            },
        ),
    ]
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=CIRION_CAMPUS,
            name="Cirion BUE1 Buenos Aires Data Center",
            country="Argentina",
            address=(
                "Av. del Campo 1301, C1427 Cdad. Autónoma de Buenos Aires, Argentina"
            ),
            roles={"operator": ["Cirion Technologies"]},
            evidence_key=CIRION_FACILITY_EVIDENCE,
            as_of_date="2026-07-22",
        ),
        "project": _entity(
            stable_key=CIRION_PROJECT,
            name="Cirion BUE1 2025 Expansion",
            country="Argentina",
            address="Buenos Aires, Argentina",
            roles={"developer": ["Cirion Technologies"]},
            evidence_key=CIRION_EXPANSION_EVIDENCE,
            as_of_date="2025-08-21",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "expansion",
                "evidence_key": CIRION_EXPANSION_EVIDENCE,
                "as_of_date": "2025-08-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [
            {
                "entity": "campus",
                "value": "colocation",
                "evidence_key": CIRION_FACILITY_EVIDENCE,
                "as_of_date": "2026-07-22",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ],
        "workloads": [],
        "capacities": [],
    }


def _jakarta_source() -> dict[str, Any]:
    evidence = [
        _evidence(
            "damac_jakarta_wayback",
            key=JAKARTA_EVIDENCE,
            title=(
                "EDGNEX Data Centers by DAMAC Announces $2.3 Billion AI-Focused "
                "Data Center in Jakarta, Indonesia"
            ),
            publisher="DAMAC Group",
            source_family="damac_group_official_press_releases_archived",
            published_at="2025-06-17",
            excerpt=(
                "An archived replay of the exact official DAMAC URL says the second "
                "Jakarta data-center site had entered early construction phases."
            ),
            claim_metadata={
                "status_scope": (
                    "Archive-derived normalized use is limited to the exact early-"
                    "construction sentence. It supports under_construction on 2025-06-17 "
                    "and no persisted current state."
                ),
                "current_status_guardrail": (
                    "The live official route returned HTTP 500 during this capture. The "
                    "last normalized status is historical; status in July 2026 is unknown."
                ),
                "future_capacity_guardrail": (
                    "The reported 144 MW is a future projected whole-facility figure. It "
                    "is retained only as excluded context; phase-one capacity is unknown."
                ),
                "pue_guardrail": (
                    "The reported 1.32 target PUE is design intent and is retained only as "
                    "excluded context; no PUE observation is emitted."
                ),
                "first_facility_guardrail": (
                    "The separately described first 19.2 MW MT Haryono facility is not "
                    "this second Jakarta site and creates no entity or capacity here."
                ),
                "classification_guardrail": (
                    "AI-focused design and planned high-density racks create no operating-"
                    "model or workload observation."
                ),
            },
        )
    ]
    roles = {"developer": ["EDGNEX Data Centers by DAMAC"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=JAKARTA_CAMPUS,
            name="EDGNEX Second Jakarta AI Data Center",
            country="Indonesia",
            address="Jakarta, Indonesia",
            roles=roles,
            evidence_key=JAKARTA_EVIDENCE,
            as_of_date="2025-06-17",
            confidence=0.98,
        ),
        "project": _entity(
            stable_key=JAKARTA_PROJECT,
            name="EDGNEX Second Jakarta Phase 1 Early Construction",
            country="Indonesia",
            address="Jakarta, Indonesia",
            roles=roles,
            evidence_key=JAKARTA_EVIDENCE,
            as_of_date="2025-06-17",
            confidence=0.98,
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": JAKARTA_EVIDENCE,
                "as_of_date": "2025-06-17",
                "method": "authoritative_physical_status_update",
                "confidence": 0.98,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _cmc_source() -> dict[str, Any]:
    evidence = [
        _evidence(
            "cmc_hanoi_release_wayback",
            key=CMC_RELEASE_EVIDENCE,
            title=(
                "CMC Creative Space Hanoi: A New Symbol for the Make in Vietnam "
                "Artificial Intelligence Ecosystem"
            ),
            publisher="CMC Corporation",
            source_family="cmc_corporation_official_releases_archived",
            published_at="2025-06-01",
            excerpt=(
                "The archived replay of CMC's exact official release records the June 1, "
                "2025 groundbreaking in the Tay Ho Tay urban area."
            ),
            claim_metadata={
                "location_scope": (
                    "Tay Ho Tay urban area, Hanoi is an authoritative locality, not a "
                    "street address, parcel, point, coordinate, or geometry."
                ),
                "whole_complex_guardrail": (
                    "The release's USD 300 million investment and greater-than-90,000 m2 "
                    "whole-complex floor area are not allocated to the data-center tower."
                ),
            },
        ),
        _evidence(
            "cmc_annual_landing_wayback",
            key=CMC_LANDING_EVIDENCE,
            title="CMC Annual Report 2024 Landing Page",
            publisher="CMC Corporation",
            source_family="cmc_corporation_annual_report_landing_pages_archived",
            published_at=None,
            excerpt=(
                "The archived official landing page identifies and links CMC Annual "
                "Report 2024 at the captured official CDN URL."
            ),
            claim_metadata={
                "lineage_scope": (
                    "This landing page establishes publisher-controlled report lineage. "
                    "It creates no independent lifecycle, capacity, or classification row."
                )
            },
        ),
        _evidence(
            "cmc_annual_pdf",
            key=CMC_REPORT_EVIDENCE,
            title="CMC Annual Report 2024",
            publisher="CMC Corporation",
            source_family="cmc_corporation_annual_reports",
            published_at=None,
            excerpt=(
                "CMC's annual report says CCS Hanoi moved into Phase 2, including "
                "construction of a distinct five-storey data-center tower, and officially "
                "broke ground on June 1, 2025."
            ),
            claim_metadata={
                "selected_pdf_page": 50,
                "status_scope": (
                    "The report corroborates that Phase 2 includes construction of a "
                    "distinct five-storey data-center tower and the 2025-06-01 start."
                ),
                "current_status_guardrail": (
                    "No later physical update is captured. The persisted observation is "
                    "historical and current July 2026 status remains unknown."
                ),
                "area_guardrail": (
                    "The 90,095 m2 construction area covers the data center, office tower, "
                    "and integrated complex and is not allocated to the data-center tower."
                ),
                "investment_guardrail": (
                    "Whole-project investment figures are not allocated to the data-center "
                    "tower and create no capacity, power, or energy observation."
                ),
                "capacity_guardrail": (
                    "Storeys and floor area are not power or energy. No critical IT, gross "
                    "facility, grid, generation, annual energy, PUE, or WUE row is emitted."
                ),
            },
        ),
    ]
    roles = {"developer": ["CMC Corporation"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=CMC_CAMPUS,
            name="CMC Creative Space Hanoi",
            country="Vietnam",
            address="Tay Ho Tay urban area, Hanoi, Vietnam",
            roles=roles,
            evidence_key=CMC_RELEASE_EVIDENCE,
            as_of_date="2025-06-01",
        ),
        "project": _entity(
            stable_key=CMC_PROJECT,
            name="CMC Creative Space Hanoi Data Center Tower",
            country="Vietnam",
            address="Hanoi, Vietnam",
            roles=roles,
            evidence_key=CMC_REPORT_EVIDENCE,
            as_of_date="2025-06-01",
        ),
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": CMC_REPORT_EVIDENCE,
                "as_of_date": "2025-06-01",
                "method": "authoritative_construction_start",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the four exact schema-1.1 source documents."""

    builders = (_batam_source, _cirion_source, _jakarta_source, _cmc_source)
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


SOURCE_DISPOSITIONS = {
    SOURCE_FILENAMES[0]: "dated_shell_with_fresh_preoperation_context",
    SOURCE_FILENAMES[1]: "dated_expansion_with_current_facility_enrichment",
    SOURCE_FILENAMES[2]: "historical_archived_early_construction_current_unknown",
    SOURCE_FILENAMES[3]: "historical_official_construction_start_current_unknown",
}
CURRENT_OPEN_SEED_ELIGIBILITY = {
    SOURCE_FILENAMES[0]: True,
    SOURCE_FILENAMES[1]: True,
    SOURCE_FILENAMES[2]: False,
    SOURCE_FILENAMES[3]: False,
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
                "country": document["campus"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": len(document["workloads"]),
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": SOURCE_DISPOSITIONS[name],
                "current_open_seed_eligible": CURRENT_OPEN_SEED_ELIGIBILITY[name],
                "seeded": False,
            }
        )
    return records


def _planned_keys(
    documents: Mapping[str, Mapping[str, Any]],
) -> tuple[set[str], set[str]]:
    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    if len(stable_keys) != 8 or len(evidence_keys) != 9:
        raise GlobalOfficialGapError("planned key inventory differs")
    return stable_keys, evidence_keys


def _document_keys(path: Path) -> tuple[set[str], set[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set(), set()
    if not isinstance(document, dict):
        return set(), set()
    stable_keys = {
        row.get("stable_key")
        for name in ("campus", "project")
        if isinstance((row := document.get(name)), dict)
        and isinstance(row.get("stable_key"), str)
    }
    evidence_keys = {
        row.get("key")
        for row in document.get("evidence", [])
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    return stable_keys, evidence_keys


def _collision_witness(
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    for path, pin in V93_PINS.items():
        _pin(path, pin)
    if tree_digest(V93_RELEASE) != V93_TREE_SHA256:
        raise GlobalOfficialGapError("accepted v93 release tree differs")
    definition = json.loads(V93_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V93_INPUT_COUNT:
        raise GlobalOfficialGapError("accepted v93 input count differs")
    if sum(1 for _ in V93_ENTITIES.open(encoding="utf-8")) - 1 != V93_ENTITY_COUNT:
        raise GlobalOfficialGapError("accepted v93 entity count differs")

    planned_stable, planned_evidence = _planned_keys(documents)
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    selected_paths = {row["path"] for row in definition["curated_inputs"]}
    if planned_paths & selected_paths:
        raise GlobalOfficialGapError("v93 unexpectedly selects a planned source")
    entities_text = V93_ENTITIES.read_text(encoding="utf-8")
    v93_stable_collisions = sorted(
        key for key in planned_stable if key in entities_text
    )
    if v93_stable_collisions:
        raise GlobalOfficialGapError(
            f"planned stable key collides with v93: {v93_stable_collisions!r}"
        )

    inflight_paths = [SOURCES_ROOT / name for name in INFLIGHT_V94_SOURCE_FILENAMES]
    if len(inflight_paths) != 10 or any(
        path.is_symlink() or not path.is_file() for path in inflight_paths
    ):
        raise GlobalOfficialGapError("known ten-source v94 input set differs")
    inflight_stable: set[str] = set()
    inflight_evidence: set[str] = set()
    for path in inflight_paths:
        stable, evidence = _document_keys(path)
        inflight_stable.update(stable)
        inflight_evidence.update(evidence)
    if planned_stable & inflight_stable or planned_evidence & inflight_evidence:
        raise GlobalOfficialGapError("planned keys collide with in-flight v94 sources")

    _pin(CMC_HISTORICAL_SOURCE, CMC_HISTORICAL_PIN)
    collisions: dict[str, dict[str, list[str]]] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in SOURCE_FILENAMES:
            continue
        stable, evidence = _document_keys(path)
        stable_overlap = sorted(planned_stable & stable)
        evidence_overlap = sorted(planned_evidence & evidence)
        if stable_overlap or evidence_overlap:
            collisions[path.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    allowed = {
        CMC_HISTORICAL_SOURCE.name: {
            "stable_keys": [CMC_CAMPUS],
            "evidence_keys": [],
        }
    }
    if collisions != allowed:
        raise GlobalOfficialGapError(
            f"unexpected curated source collisions: {collisions!r}"
        )
    return {
        "v93_definition_sha256": V93_PINS[V93_DEFINITION][1],
        "v93_manifest_sha256": V93_PINS[V93_MANIFEST][1],
        "v93_release_tree_sha256": V93_TREE_SHA256,
        "v93_selected_input_count": V93_INPUT_COUNT,
        "v93_entity_count": V93_ENTITY_COUNT,
        "planned_source_paths_selected_by_v93": False,
        "planned_stable_key_collisions_with_v93": [],
        "inflight_v94_source_count_checked": 10,
        "planned_stable_key_collisions_with_inflight_v94": [],
        "planned_evidence_key_collisions_with_inflight_v94": [],
        "intentional_existing_source_alignment": allowed,
        "cross_source_identity_inference_used": False,
    }


def _validate_capture_claim_literals(directory: Path) -> None:
    requirements = {
        "neutradc_topping_wayback.body": (
            b"IT load capacity of 18 MW",
            b"scalable up to 54 MW",
            b"Kabil Industrial Estate",
            b"BTM-1",
        ),
        "telkom_batam_itload.body": (
            b"total IT load",
            b"18 MW",
            b"BTM-1",
        ),
        "telkom_batam_later.body": (
            b"BTM-1",
            b"100 MW",
            b"BTM-2",
        ),
        "cirion_bue1.body": (
            b"executing a new expansion",
            b"more than 2MW",
            b"160 additional racks",
            b"PeeringDB",
        ),
        "cirion_bue1_facility.body": (
            "Av. del Campo 1301, C1427 Cdad. Autónoma de Buenos Aires".encode(),
            b"Carrier-Neutral",
            b"Colocation",
            b"7 MW installed",
        ),
        "damac_jakarta_wayback.body": (
            b"entered early construction phases",
            b"future projected capacity of 144 MW",
            b"Power Usage Effectiveness (PUE) of 1.32",
            b"second in the market",
        ),
        "cmc_hanoi_release_wayback.body": (
            b"Tay Ho Tay urban area",
            b"USD 300 million",
            b"June 1, 2025",
        ),
        "cmc_annual_landing_wayback.body": (
            b"Annual Report 2024",
            b"20250718 - CMG - Annual report 2024 - signed.pdf",
        ),
        "cmc_annual_pdf.body": (b"%PDF-",),
    }
    for name, needles in requirements.items():
        payload = (directory / name).read_bytes()
        missing = [needle for needle in needles if needle not in payload]
        if missing:
            raise GlobalOfficialGapError(
                f"captured claim literal differs for {name}: {missing!r}"
            )


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise GlobalOfficialGapError("capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if (
        len(entries) != CAPTURE_FILE_COUNT
        or {entry.name for entry in entries} != set(CAPTURE_FILE_PINS)
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise GlobalOfficialGapError("capture directory closed set differs")
    if (
        sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES
        or tree_digest(directory) != CAPTURE_TREE_SHA256
    ):
        raise GlobalOfficialGapError("capture aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)
    for capture_id, spec in CAPTURE_SPECS.items():
        writeout_path = directory / f"{capture_id}.writeout"
        writeout = json.loads(writeout_path.read_text(encoding="utf-8"))
        actual = (
            writeout["url_effective"],
            writeout["exitcode"],
            writeout["response_code"],
            writeout["http_version"],
            writeout["content_type"],
            writeout["size_download"],
            writeout["size_header"],
            writeout["num_headers"],
            writeout["num_redirects"],
            writeout["errormsg"] or None,
        )
        expected = (
            spec.effective_url,
            spec.exit_code,
            spec.http_status,
            spec.http_version,
            spec.content_type,
            spec.wire_bytes,
            spec.header_bytes,
            spec.header_count,
            0,
            spec.error,
        )
        if actual != expected:
            raise GlobalOfficialGapError(
                f"capture writeout differs for {capture_id}: {actual!r}"
            )
        completed = datetime.fromtimestamp(writeout_path.stat().st_mtime, UTC).replace(
            microsecond=0
        )
        if completed != _instant(spec.completed_at):
            raise GlobalOfficialGapError(
                f"capture completion time differs for {capture_id}"
            )
    _validate_capture_claim_literals(directory)


def _validate_sources(
    paths: Mapping[str, Path], *, require_frozen: bool
) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise GlobalOfficialGapError("source path inventory differs")
    wanted_mode = 0o444 if require_frozen else 0o600
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != _canonical(expected[name])
            or stat.S_IMODE(path.stat().st_mode) != wanted_mode
        ):
            raise GlobalOfficialGapError(f"curated source differs: {name}")

    documents = list(expected.values())
    if any(
        document[entity][field] is not None
        for document in documents
        for entity in ("campus", "project")
        for field in ("coordinates", "geometry")
    ):
        raise GlobalOfficialGapError("source invented coordinates or geometry")
    lifecycle = [
        (
            document["project"]["stable_key"],
            row["value"],
            row["as_of_date"],
        )
        for document in documents
        for row in document["lifecycle"]
    ]
    if lifecycle != [
        (BTM_PROJECT, "shell", "2025-10-30"),
        (CIRION_PROJECT, "expansion", "2025-08-21"),
        (JAKARTA_PROJECT, "under_construction", "2025-06-17"),
        (CMC_PROJECT, "under_construction", "2025-06-01"),
    ]:
        raise GlobalOfficialGapError("lifecycle contract differs")
    capacities = [row for document in documents for row in document["capacities"]]
    if [
        (row["entity"], row["metric"], row["stage"], row["base"]) for row in capacities
    ] != [("project", "critical_it_mw", "planned", 18)]:
        raise GlobalOfficialGapError("capacity contract differs")
    operating_models = [
        row for document in documents for row in document["operating_models"]
    ]
    if [
        (row["entity"], row["value"], row["as_of_date"]) for row in operating_models
    ] != [("campus", "colocation", "2026-07-22")]:
        raise GlobalOfficialGapError("operating-model contract differs")
    if any(document["workloads"] for document in documents):
        raise GlobalOfficialGapError("source invented workload observations")
    jakarta_evidence = expected[SOURCE_FILENAMES[2]]["evidence"][0]
    if (
        jakarta_evidence["source_url"]
        != CAPTURE_SPECS["damac_jakarta_wayback"].effective_url
        or jakarta_evidence["metadata"]["evidence_class"]
        != "archived_company_disclosure"
        or jakarta_evidence["metadata"]["official_canonical_url"]
        != CAPTURE_SPECS["damac_jakarta_wayback"].original_official_url
    ):
        raise GlobalOfficialGapError("DAMAC archive boundary differs")
    return _source_records(expected)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="global-official-gap-import-", dir="/private/tmp"
    ) as temporary:
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
            "entities": 8,
            "entity_snapshots": 8,
            "evidence": 9,
            "lifecycle_observations": 4,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise GlobalOfficialGapError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v2",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 4,
        "source_record_count": 4,
        "dated_lifecycle_observation_count": 4,
        "current_status_inferred": False,
        "regional_completeness_claimed": False,
        "candidates": [
            {
                "candidate_id": "neutradc-nxera-batam-btm1",
                "country": "Indonesia",
                "decision": "normalize_dated_shell_with_fresh_preoperation_context",
                "source_record": f"sources/{SOURCE_FILENAMES[0]}",
                "campus_stable_key": BTM_CAMPUS,
                "project_stable_key": BTM_PROJECT,
                "lifecycle": {
                    "value": "shell",
                    "as_of_date": "2025-10-30",
                    "current_status": "unknown",
                },
                "normalized_capacity": {
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "base": 18,
                    "entity": BTM_PROJECT,
                },
                "withheld_context": {
                    "subsequent_phases_mw": 54,
                    "future_campus_development_mw": 100,
                    "btm2_entity_created": False,
                },
            },
            {
                "candidate_id": "cirion-bue1-2025-expansion",
                "country": "Argentina",
                "decision": "normalize_dated_expansion_and_current_facility_enrichment",
                "source_record": f"sources/{SOURCE_FILENAMES[1]}",
                "campus_stable_key": CIRION_CAMPUS,
                "project_stable_key": CIRION_PROJECT,
                "lifecycle": {
                    "value": "expansion",
                    "as_of_date": "2025-08-21",
                    "current_expansion_status": "unknown",
                },
                "operating_model": "colocation",
                "withheld_context": {
                    "expansion_capacity_as_reported": "more than 2 MW, untyped",
                    "additional_racks_as_reported": "approximately 160",
                    "whole_facility_installed_power_mw": 7,
                    "peeringdb_or_connectivity_claims_used": False,
                    "other_facilities_greater_than_20_mw_used": False,
                },
            },
            {
                "candidate_id": "edgnex-second-jakarta-phase1",
                "country": "Indonesia",
                "decision": "normalize_historical_archived_early_construction_only",
                "source_record": f"sources/{SOURCE_FILENAMES[2]}",
                "campus_stable_key": JAKARTA_CAMPUS,
                "project_stable_key": JAKARTA_PROJECT,
                "lifecycle": {
                    "value": "under_construction",
                    "as_of_date": "2025-06-17",
                    "scope": "early_construction",
                    "current_status": "unknown",
                },
                "archive_boundary": {
                    "classification": "archived_company_disclosure",
                    "archive_capture_timestamp": "20260122183232",
                    "replay_url": CAPTURE_SPECS["damac_jakarta_wayback"].effective_url,
                    "official_canonical_url": CAPTURE_SPECS[
                        "damac_jakarta_wayback"
                    ].original_official_url,
                    "live_origin_http_status": 500,
                    "live_origin_used_for_claims": False,
                },
                "withheld_context": {
                    "future_projected_facility_mw": 144,
                    "phase_one_capacity": "unknown",
                    "target_pue": 1.32,
                    "first_mt_haryono_facility_is_distinct": True,
                    "capacity_or_pue_rows_created": 0,
                },
            },
            {
                "candidate_id": "cmc-creative-space-hanoi-data-center-tower",
                "country": "Vietnam",
                "decision": "normalize_historical_distinct_tower_construction_start",
                "source_record": f"sources/{SOURCE_FILENAMES[3]}",
                "campus_stable_key": CMC_CAMPUS,
                "project_stable_key": CMC_PROJECT,
                "lifecycle": {
                    "value": "under_construction",
                    "as_of_date": "2025-06-01",
                    "current_status": "unknown",
                },
                "annual_report_corroboration": {
                    "phase": 2,
                    "data_center_tower_storeys": 5,
                    "distinct_office_tower_storeys": 23,
                },
                "withheld_context": {
                    "whole_complex_area_square_metres": 90_095,
                    "whole_complex_investment_usd": 300_000_000,
                    "area_or_investment_allocated_to_data_center": False,
                    "capacity_rows_created": 0,
                },
            },
        ],
    }


CAPTURE_EVIDENCE_KEYS: Mapping[str, Sequence[str]] = {
    "cirion_bue1": (CIRION_EXPANSION_EVIDENCE,),
    "cirion_bue1_facility": (CIRION_FACILITY_EVIDENCE,),
    "cmc_annual_landing_wayback": (CMC_LANDING_EVIDENCE,),
    "cmc_annual_pdf": (CMC_REPORT_EVIDENCE,),
    "cmc_hanoi_release_wayback": (CMC_RELEASE_EVIDENCE,),
    "damac_jakarta_wayback": (JAKARTA_EVIDENCE,),
    "neutradc_topping_wayback": (BTM_TOPPING_EVIDENCE,),
    "telkom_batam_itload": (BTM_ITLOAD_EVIDENCE,),
    "telkom_batam_later": (BTM_LATER_EVIDENCE,),
}


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    rows = []
    for capture_id, spec in CAPTURE_SPECS.items():
        body_name = f"{capture_id}.body"
        row: dict[str, Any] = {
            "capture_id": capture_id,
            "requested_url": spec.requested_url,
            "effective_url": spec.effective_url,
            "completed_at": spec.completed_at,
            "curl_exit_code": spec.exit_code,
            "http_status": spec.http_status,
            "http_version": spec.http_version,
            "content_type": spec.content_type,
            "wire_download_bytes": spec.wire_bytes,
            "curl_header_bytes": spec.header_bytes,
            "curl_num_headers": spec.header_count,
            "redirect_count": 0,
            "error": spec.error,
            "contributes_evidence": capture_id in CAPTURE_EVIDENCE_KEYS,
            "evidence_keys": list(CAPTURE_EVIDENCE_KEYS.get(capture_id, ())),
            "headers": {
                "path": f"{capture_id}.headers",
                "bytes": CAPTURE_FILE_PINS[f"{capture_id}.headers"][0],
                "sha256": CAPTURE_FILE_PINS[f"{capture_id}.headers"][1],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "curl_writeout": {
                "path": f"{capture_id}.writeout",
                "bytes": CAPTURE_FILE_PINS[f"{capture_id}.writeout"][0],
                "sha256": CAPTURE_FILE_PINS[f"{capture_id}.writeout"][1],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
        }
        if body_name in CAPTURE_FILE_PINS:
            row["body"] = {
                "path": body_name,
                "bytes": CAPTURE_FILE_PINS[body_name][0],
                "sha256": CAPTURE_FILE_PINS[body_name][1],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            }
        else:
            row["body_created"] = False
        if spec.original_official_url:
            row["archive"] = {
                "classification": "archived_company_disclosure",
                "archive_capture_timestamp": spec.archive_timestamp,
                "archive_replay_url": spec.effective_url,
                "official_canonical_url": spec.original_official_url,
            }
        rows.append(row)
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public curl GETs with redirects, content decoding, "
            "separate bodies, raw response-header streams, and curl JSON writeouts. "
            "Internet Archive raw replays were used only after exact official origin "
            "routes returned timeout, 403, or 500 responses."
        ),
        "direct_request_attempts": 13,
        "archive_replay_attempts": 4,
        "successful_http_200_body_captures": 9,
        "failed_origin_body_captures": 8,
        "evidence_supporting_captures": 9,
        "captured_file_count": CAPTURE_FILE_COUNT,
        "captured_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "request_credentials_supplied": False,
        "browser_session_used_for_evidence": False,
        "raw_capture_redistributed": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": rows,
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _artifact_documents(
    recorded_at: str, documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, bytes]:
    source_records = _source_records(documents)
    collision = _collision_witness(documents)
    readme = f"""# Four-site official current-build gap source artifact

This immutable artifact publishes four schema-1.1 source records for NeutraDC Nxera Batam BTM-1, Cirion BUE1's 2025 expansion, EDGNEX's second Jakarta site, and the CMC Creative Space Hanoi data-center tower. It performs no open-seed or downstream integration.

Lifecycle values are dated last observations, never automatic current-state claims. BTM-1 reached shell at topping off on 2025-10-30; a June 2026 Telkom update only establishes that it was still pre-operational and supplies no later physical stage. Cirion said it was executing an expansion on 2025-08-21; the current facility page contributes the exact campus address and a colocation operating model, not a current expansion stage. DAMAC's live route returned HTTP 500, so the Jakarta record is limited to the exact early-construction sentence in a 2026-01-22 archived replay of the exact official URL; its current status remains unknown. CMC's official annual-report PDF corroborates that Phase 2 includes a distinct five-storey data-center tower and the 2025-06-01 groundbreaking; no later physical status is inferred.

Exactly one capacity is normalized: 18 MW planned critical IT for BTM-1, supported literally as its initial IT load. Batam's 54 MW subsequent phases and 100 MW future campus scope, Cirion's untyped greater-than-2 MW expansion figure and 7 MW whole-facility installed power, Jakarta's future 144 MW facility and target PUE 1.32, and CMC's whole-complex area and investment remain excluded context. No values are summed. No current load, consumption, annual energy, grid connection, generation, PUE, WUE, utilization, model, or workload is asserted.

PeeringDB-derived and other connectivity claims are excluded. No coordinates or geometry are present. Publisher imagery, satellite imagery, aerial imagery, computer vision, and analyst geolocation contribute no identity, status, type, role, capacity, point, or footprint claim.

All source and artifact stage bytes and mtimes preceded the declared instant `{recorded_at}`. Final paths remained absent until that instant, then frozen sources and artifact members were promoted without replacement with identity-protected rollback. Every final source, artifact member, and artifact-root ctime is at or after the declared instant. The complete 50-file raw directory, including eight failed live-origin responses, moves intact to recoverable Trash only after successful live validation. Raw all-rights-reserved bodies, headers, cookies, and writeouts are not redistributed.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 4,
            "source_records": 4,
            "current_open_seed_eligible_source_records": 2,
            "historical_current_unknown_source_records": 2,
            "distinct_campuses": 4,
            "projects": 4,
            "distinct_entities": 8,
            "unique_imported_entity_snapshots": 8,
            "unique_evidence_records": 9,
            "lifecycle_observations": 4,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 1,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "normalized_capacity_boundary": {
            "rows": [
                {
                    "entity": BTM_PROJECT,
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "base": 18,
                }
            ],
            "forbidden_or_withheld_numeric_context": {
                "batam_subsequent_phases_mw": 54,
                "batam_future_campus_mw": 100,
                "cirion_expansion_untyped_mw": "more than 2",
                "cirion_whole_facility_installed_mw": 7,
                "jakarta_future_projected_facility_mw": 144,
                "jakarta_target_pue": 1.32,
                "cmc_whole_complex_square_metres": 90_095,
            },
            "nonadditive": True,
        },
        "frozen_v93_and_inflight_v94_noncollision_witness": collision,
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v93_mutated": False,
            "unfinished_v94_module_pinned": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "coordinate_integration": "none",
            "coverage_integration": "none",
        },
        "publication_contract": {
            "version": 3,
            "all_stage_birthtimes_and_mtimes_not_after_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "all_final_source_member_and_root_ctimes_at_or_after_recorded_at": True,
            "raw_capture_moved_after_successful_live_validation": True,
            "source_file_mode": "0444",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": (
            "All publisher bodies and archived official-page replays are treated as "
            "all-rights-reserved. No redistribution license is relied on."
        ),
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "curl_writeouts_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "response_cookies_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "raw_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "raw_capture_file_count": CAPTURE_FILE_COUNT,
        "raw_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_move_scope": (
            "The complete closed 50-file source capture directory moves intact, "
            "including every successful body/header/writeout and every failed live "
            "origin body/header/writeout that existed."
        ),
        "deletion_performed": False,
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _assert_stage_prebarrier(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        birthtime = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if birthtime > threshold + 0.000_001:
            raise GlobalOfficialGapError(
                f"stage birthtime post-dates recorded_at: {path}"
            )
        if metadata.st_mtime > threshold + 0.000_001:
            raise GlobalOfficialGapError(f"stage mtime post-dates recorded_at: {path}")


def _assert_final_ctimes(paths: Sequence[Path], recorded_at: str) -> None:
    threshold = _instant(recorded_at).timestamp()
    for path in paths:
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < threshold:
            raise GlobalOfficialGapError(
                f"final member ctime predates recorded_at: {path}"
            )


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    require_frozen: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths, require_frozen=require_frozen)
    _collision_witness(expected_source_documents())
    if path.is_symlink() or not path.is_dir():
        raise GlobalOfficialGapError("artifact must be an ordinary directory")
    wanted_root = 0o555 if require_frozen else 0o700
    if stat.S_IMODE(path.stat().st_mode) != wanted_root:
        raise GlobalOfficialGapError("artifact root mode differs")
    entries = {entry.name: entry for entry in path.iterdir()}
    wanted_member = 0o444 if require_frozen else 0o600
    if set(entries) != CLOSED_FILES or any(
        entry.is_symlink()
        or not entry.is_file()
        or stat.S_IMODE(entry.stat().st_mode) != wanted_member
        for entry in entries.values()
    ):
        raise GlobalOfficialGapError("artifact closed member contract differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise GlobalOfficialGapError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest_raw != _canonical(manifest)
        or manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 4
        or manifest.get("curated_source_records") != 4
        or manifest.get("dated_lifecycle_observations") != 4
        or manifest.get("successful_http_200_body_captures") != 9
        or manifest.get("failed_origin_body_captures") != 8
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise GlobalOfficialGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise GlobalOfficialGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (
            row["bytes"],
            row["sha256"],
        ):
            raise GlobalOfficialGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise GlobalOfficialGapError("manifest checksum differs")
    expected_payloads = _artifact_documents(
        manifest["recorded_at"], expected_source_documents()
    )
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise GlobalOfficialGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise GlobalOfficialGapError("artifact source pins differ")

    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise GlobalOfficialGapError("validation wall clock lacks timezone")
    if require_live and now.astimezone(UTC) < target:
        raise GlobalOfficialGapError("artifact recorded_at is not live")
    if _instant(LATEST_CAPTURE_AT) > target:
        raise GlobalOfficialGapError("raw capture post-dates recorded_at")
    replays = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replays[0] != replays[1]:
        raise GlobalOfficialGapError("deterministic offline replay differs")
    if require_frozen:
        _assert_final_ctimes(
            [path, *entries.values(), *paths.values()], manifest["recorded_at"]
        )
    return manifest


def _write_source_stage(
    stage: Path, documents: Mapping[str, Mapping[str, Any]]
) -> None:
    for name in SOURCE_FILENAMES:
        path = stage / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)
        _fsync_regular(path)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = stage / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
        _fsync_regular(path)
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
        "candidate_assessments": 4,
        "curated_source_records": 4,
        "current_open_seed_eligible_source_records": 2,
        "historical_current_unknown_source_records": 2,
        "distinct_entities": 8,
        "unique_evidence_records": 9,
        "dated_lifecycle_observations": 4,
        "operating_model_observations": 1,
        "workload_observations": 0,
        "capacity_estimates": 1,
        "successful_http_200_body_captures": 9,
        "failed_origin_body_captures": 8,
        "archive_replay_captures": 4,
        "raw_capture_redistributed": False,
        "raw_capture_moved_after_successful_live_validation": True,
        "all_final_source_member_and_root_ctimes_at_or_after_recorded_at": True,
        "regional_completeness_claimed": False,
        "current_status_inferred": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o600)
    _fsync_regular(sidecar)
    stage.chmod(0o700)
    _fsync_directory(stage)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise GlobalOfficialGapError("active publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise GlobalOfficialGapError(
                    "refusing substituted publication lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise GlobalOfficialGapError("final-path collision")
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    _collision_witness(documents)
    source_stage = Path(
        tempfile.mkdtemp(prefix=".global-official-gap-sources.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        prepared = _Prepared(source_stage, artifact_stage, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=_source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=_instant(recorded_at),
        )
        stage_paths = [
            source_stage,
            artifact_stage,
            *source_stage.iterdir(),
            *artifact_stage.iterdir(),
        ]
        _assert_stage_prebarrier(stage_paths, recorded_at)
        if (
            ARTIFACT.exists()
            or ARTIFACT.is_symlink()
            or any(
                (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
                for name in SOURCE_FILENAMES
            )
        ):
            raise GlobalOfficialGapError(
                "final paths were not absent before publication barrier"
            )
        return prepared
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def _freeze_after_barrier(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    for name in SOURCE_FILENAMES:
        path = prepared.source_stage / name
        path.chmod(0o444)
        _fsync_regular(path)
    for member in prepared.artifact_stage.iterdir():
        member.chmod(0o444)
        _fsync_regular(member)
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.source_stage)
    _fsync_directory(prepared.artifact_stage)
    _assert_final_ctimes(
        [
            prepared.artifact_stage,
            *prepared.artifact_stage.iterdir(),
            *prepared.source_stage.iterdir(),
        ],
        prepared.recorded_at,
    )


def _publish(prepared: _Prepared) -> None:
    _freeze_after_barrier(prepared)
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise GlobalOfficialGapError("late final-path collision")
    operations = [
        (prepared.source_stage / name, SOURCES_ROOT / name, False)
        for name in SOURCE_FILENAMES
    ]
    operations.append((prepared.artifact_stage, ARTIFACT, True))
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for staged, final, directory in operations:
            identity = _identity(staged, directory=directory)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=directory):
                raise GlobalOfficialGapError(f"promoted identity differs: {final}")
            promoted.append((final, staged, identity, directory))
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise GlobalOfficialGapError(
                        f"refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise GlobalOfficialGapError("both raw origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _result(manifest: Mapping[str, Any], status_value: str) -> dict[str, Any]:
    source_rows = []
    for name in SOURCE_FILENAMES:
        path = SOURCES_ROOT / name
        source_rows.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return {
        "artifact": str(ARTIFACT),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "logical_tree_sha256": manifest["tree_sha256"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "capture_trash": str(CAPTURE_TRASH),
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "recorded_at": manifest["recorded_at"],
        "source_records": source_rows,
        "unique_entities": 8,
        "unique_evidence_records": 9,
        "lifecycle_observations": 4,
        "operating_model_observations": 1,
        "capacity_estimates": 1,
        "status": status_value,
    }


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all(
        (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
    ):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return _result(manifest, "existing-identical")
    if (
        ARTIFACT.exists()
        or ARTIFACT.is_symlink()
        or any(
            (SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink()
            for name in SOURCE_FILENAMES
        )
    ):
        raise GlobalOfficialGapError("partial final-path collision")
    target = (
        _instant(recorded_at)
        if recorded_at
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise GlobalOfficialGapError(
            "recorded_at must be future before private staging"
        )
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        manifest = validate_artifact()
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise GlobalOfficialGapError("source stage is not empty")
        prepared.source_stage.rmdir()
    return _result(manifest, "published")


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
