"""Fail-closed current-coverage ledger v25 successor over frozen v24.

V25 replaces exactly eight active public-chain contracts with seed v86 and
its queue, federation v35, identity v11, timeline v8, master/map v31, and
coverage v31. Two v83 execution-lane artifacts become explicitly historical.
The frozen 68-decision v83 review carrier is added only as non-countable,
non-promoted analyst-review support. Forty-two unrelated entries remain byte
and order equivalent to v24.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import current_coverage_v21 as _v21
from . import current_coverage_v22 as _v22
from . import current_coverage_v24 as _v24
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
V25_LEDGER_ID = "current-coverage-2026-07-21-v25"
V25_GENERATED_AT: str | None = "2026-07-22T01:48:00Z"
V25_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v25.json"
V25_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v25"
DEFINITION = ROOT / V25_DEFINITION_PATH
BUNDLE = ROOT / V25_BUNDLE_PATH
PUBLICATION_LOCK = ROOT / ".current-coverage-v25.lock"

BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-21-v24.json"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-21-v24"
BASE_LINEAGE = {
    "definition": {
        "bytes": 180_371,
        "path": "sources/current-coverage-2026-07-21-v24.json",
        "sha256": "50dd329704c38e127a206b2c3fda4c45deebe2592406e21edc365f4022d5fb5a",
    },
    "ledger": {
        "bytes": 118_293,
        "path": (
            "current_coverage_ledgers/2026-07-21-v24/"
            "current-coverage-ledger.json"
        ),
        "sha256": "85996a9f1636beb45ed42b82b4d3523bec642abd1bba22dd77e2cbb3d12a96a5",
    },
    "ledger_id": "current-coverage-2026-07-21-v24",
    "manifest": {
        "bytes": 32_046,
        "path": "current_coverage_ledgers/2026-07-21-v24/manifest.json",
        "sha256": "9f2be85cad5df2553f531f05d8fad7824b77e9e77509f1d0dc575f224f047af0",
    },
}
BASE_SIDECAR = {
    "bytes": 80,
    "path": "current_coverage_ledgers/2026-07-21-v24/manifest.sha256",
    "sha256": "2caaf44a24162e06badaa0264fb58035f4a0a765dc7d3b4145c0e70ccaf7908d",
}
BASE_TREE_SHA256 = "f866659110cb0ab2d8b2d6e68667109f8526ff2580fbf49c7a07a7c7126792ce"

DEFINITION_SCHEMA_VERSION_V4 = _v24.DEFINITION_SCHEMA_VERSION_V4
LEDGER_SCHEMA_VERSION_V4 = _v24.LEDGER_SCHEMA_VERSION_V4
LEDGER_FORMAT_V4 = _v24.LEDGER_FORMAT_V4
BUNDLE_FORMAT_V4 = _v24.BUNDLE_FORMAT_V4
SCOPE_POLICY = _v24.SCOPE_POLICY
BUNDLE_FILES = _v24.BUNDLE_FILES
LEDGER_FILENAME = _v24.LEDGER_FILENAME
MANIFEST_FILENAME = _v24.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _v24.MANIFEST_HASH_FILENAME

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v30": "construction-map-public-open-v31",
    "construction-master-public-open-v30": "construction-master-public-open-v31",
    "construction-timeline-public-open-v7": "construction-timeline-public-open-v8",
    "coverage-audit-public-open-v30": "coverage-audit-public-open-v31",
    "exact-identity-decisions-public-open-v10": (
        "exact-identity-decisions-public-open-v11"
    ),
    "federation-public-open-v34": "federation-public-open-v35",
    "satellite-queue-open-seed-v83": "satellite-queue-open-seed-v86",
    "seed-epoch-official-v83": "seed-epoch-official-v86",
}
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
HISTORICALIZED_ARTIFACT_IDS = frozenset(
    {
        "satellite-catalog-open-seed-v83-active-explicit-new-projects-final-v1",
        "satellite-change-review-open-seed-v83-active-explicit-new-projects-3-review-v2",
    }
)
V83_REVIEW_ARTIFACT_ID = (
    "satellite-change-review-open-seed-v83-active-unreviewed-single-68-review-v1"
)
ADDED_ARTIFACT_IDS = frozenset({V83_REVIEW_ARTIFACT_ID})
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS

UNCHANGED_42_SHA256: str | None = (
    "cd7ed875ac9dbc29dbb32dfef7efa7db55db0d457d3bf6ffa882bddef9f0402d"
)
REMOVED_8_SHA256: str | None = (
    "ea0c3a7a279f6f7b619ac9856a1c65df38eaa9b5d6e74c5cf004539a0e1f179d"
)
HISTORICALIZED_2_SHA256: str | None = (
    "a30d708029a4f01bdb2c714066c52be258a77c3b1b0c8c30381e82ce350f8cf1"
)
REPLACEMENT_8_SHA256: str | None = (
    "0b96354a0ab8b859960a182fc1383f97bf227c0a228e9efce1616f0b0f5bfc93"
)
ADDED_1_SHA256: str | None = (
    "ecb0dd89f557512eed81820845332763757e1b4540335fc5f41806aae44706ae"
)
ALL_53_SHA256: str | None = (
    "876dd451ae0ba2af59428163ff88b017df928f100610dbf74e4b0b258c014d89"
)
PARITY_GAPS_SHA256: str | None = (
    "a3447a3dbaf526e5001b580572458148da33d372467cd4896f646488e0a1ac4a"
)
V25_DEFINITION_SHA256: str | None = (
    "40f85a544b3fd62e7fadbfd54dc52640ad04d91b04cbedcfeec09f82d5970e1c"
)

FORBIDDEN_FUTURE_TOKENS = (
    b"open-seed-v87",
    b"open-seed-v88",
    b"public-open-v36",
    b"federation-public-open-v36",
)

PINNED_FILES: Mapping[str, tuple[int, str]] = {
    "sources/current-coverage-2026-07-21-v24.json": (
        180_371,
        "50dd329704c38e127a206b2c3fda4c45deebe2592406e21edc365f4022d5fb5a",
    ),
    "current_coverage_ledgers/2026-07-21-v24/current-coverage-ledger.json": (
        118_293,
        "85996a9f1636beb45ed42b82b4d3523bec642abd1bba22dd77e2cbb3d12a96a5",
    ),
    "current_coverage_ledgers/2026-07-21-v24/manifest.json": (
        32_046,
        "9f2be85cad5df2553f531f05d8fad7824b77e9e77509f1d0dc575f224f047af0",
    ),
    "current_coverage_ledgers/2026-07-21-v24/manifest.sha256": (
        80,
        "2caaf44a24162e06badaa0264fb58035f4a0a765dc7d3b4145c0e70ccaf7908d",
    ),
    "sources/open-seed-2026-07-21-v86.json": (
        102_240,
        "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
    ),
    "releases/2026-07-21-open-seed-v86/manifest.json": (
        15_531,
        "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
    ),
    "satellite_review_queues/2026-07-21-open-seed-v86/manifest.json": (
        20_579,
        "1a417f11e94dadbca2f5c1ddf0746d6ce5eca6ccb734957f8a3c825edab217c0",
    ),
    "sources/federation-2026-07-21-public-open-v35.json": (
        1_788,
        "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f",
    ),
    "federated_indexes/2026-07-21-public-open-v35/federated-index.json": (
        36_400,
        "f7cf31d905bf497a6bc7ba3db7f22fb8e281e7b1452e1f2853ea79af1d9ea802",
    ),
    "federated_indexes/2026-07-21-public-open-v35/manifest.json": (
        986,
        "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388",
    ),
    "sources/exact-identity-decisions-2026-07-21-public-open-v11.json": (
        1_736,
        "658ca591e25045245e2709564cd11a3cdd7d338f5be11913aca4ba54a6656a40",
    ),
    "exact_identity_decisions/2026-07-21-public-open-v11/accounting.json": (
        981,
        "b37514dcc86a52b3254f62ff740507e609c661a0179ee931af13aa4ba9a0f258",
    ),
    "exact_identity_decisions/2026-07-21-public-open-v11/manifest.json": (
        11_441,
        "cd54ee06c75272974d2ba43859226b61965d04c7ca6c515d19e44447fe48cbb9",
    ),
    "sources/construction-timeline-2026-07-21-public-open-v8.json": (
        2_881,
        "9f67b19847aadf326cdd3701c3e4a8aa5309a9b59c58d3d749a6369fdfc3ec97",
    ),
    "construction_timelines/2026-07-21-public-open-v8/coverage.json": (
        35_509,
        "5a8708f2f581fb6541931733648cb23f943eee1b4a7b1f975b5e59b5e4a004aa",
    ),
    "construction_timelines/2026-07-21-public-open-v8/manifest.json": (
        3_881,
        "4a71dd94b0ab97a8b0e9add0b4688bececec285832de991f7c71a23a7dc8a02d",
    ),
    "sources/construction-master-2026-07-21-public-open-v31.json": (
        5_660,
        "a1b4761820aa6adb3406d5ff3ad6bc52898309fed72fe4f857aca01197597c25",
    ),
    "construction_master/2026-07-21-public-open-v31/coverage.json": (
        8_550,
        "2705b2772b3e64891a73b3c07a56d54e3f94cfa6ed16495ca02825253bb29c68",
    ),
    "construction_master/2026-07-21-public-open-v31/manifest.json": (
        9_721,
        "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e",
    ),
    "sources/construction-map-2026-07-21-public-open-v31.json": (
        2_442,
        "a8c15cc5f78e3b0c2b7a40b46b496b7c3561662aefda237424dc1c4b6d138f97",
    ),
    "construction_maps/2026-07-21-public-open-v31/coverage.json": (
        7_524,
        "64d4413ec97faf3dedd8ef463dbde3efdf8b51d054585afaaca819e01e0f59d1",
    ),
    "construction_maps/2026-07-21-public-open-v31/manifest.json": (
        2_192,
        "5305dd9c637a74dbd2a3b355e19185e1fd9f49b815b8a9a51786ce8428b33631",
    ),
    "sources/coverage-audit-2026-07-21-public-open-v31.json": (
        9_520,
        "cd7e3f2a0b519ab0c8de44c31c1edf7facd5e3ccc2a43f136750cc209ad93030",
    ),
    "audits/2026-07-21-public-open-coverage-v31/coverage-audit.json": (
        3_481_612,
        "c6b5cb2eaff0004bd984ccb2c65e4a6704bcb1fe5f599d926c29ae383185526b",
    ),
    "audits/2026-07-21-public-open-coverage-v31/manifest.json": (
        269_591,
        "717917b2c566da936b2f85fd45f17d71b6ecd83ac48e2111d1bd183b052db132",
    ),
}

V83_REVIEW_DIRECTORY = (
    "satellite_change_reviews/"
    "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1"
)
V83_REVIEW_MEMBER_PINS: Mapping[str, tuple[int, str]] = {
    "ATTRIBUTION.txt": (
        305,
        "ea2508601c684b7814ec6eae3285deb8623d18d06517d1b525d3b208587ef935",
    ),
    "README.md": (
        1_093,
        "74cd732b7f801324f39aecc1e04b1a3a26c47c86cfa95db6888ec1ab99a70f57",
    ),
    "analyst-reviews.jsonl": (
        284_085,
        "66cef2ffa8067fc729dfbc5097049623688cca4e5a6fd46341b0b1feb05e1603",
    ),
    "blind-decisions.json": (
        28_320,
        "dea4ce947fb6d4debbdd4bd71c319b1011ac81397318a61909991e28b62ebec3",
    ),
    "blind-review-part-a.json": (
        14_135,
        "2c752d82b541f2793bb02a4a4a3d916b6131f500f06452ae52721f70279bc396",
    ),
    "blind-review-part-b.json": (
        13_230,
        "ae62a835bef166687bbc81653bf8c57bf55dd58d98801a3ced938512d315a11f",
    ),
    "definition.json": (
        7_659,
        "7ab24635cb6fd3bc8a64740f6318a4b21bcbd03b74e243a3489cc3fbb415a2f6",
    ),
    "manifest.json": (
        5_622,
        "54229a5fa1fe29eef212ac4263563c776cfd12a5df11b7d0ecd22b6eca034399",
    ),
    "manifest.sha256": (
        80,
        "7f178b876ad741f5749099cc5b21b2c341d00024d453835765d96232c087f77d",
    ),
    "summary.json": (
        6_464,
        "275ce8feab06f18d6dd3c17e7f645d00631b5759fb5399e2436a671964ab3bc8",
    ),
}

PINNED_TREES: Mapping[str, str] = {
    "current_coverage_ledgers/2026-07-21-v24": BASE_TREE_SHA256,
    "releases/2026-07-21-open-seed-v86": (
        "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
    ),
    "satellite_review_queues/2026-07-21-open-seed-v86": (
        "e9611d94eff7a6cc62b22a1a3291651acaa01db468889c500455b9fb2908f1c5"
    ),
    "federated_indexes/2026-07-21-public-open-v35": (
        "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"
    ),
    "exact_identity_decisions/2026-07-21-public-open-v11": (
        "b25b7b568df098a0405452cf3c0608d9d840ace15af120625f7650423d22f6d9"
    ),
    "construction_timelines/2026-07-21-public-open-v8": (
        "f3231947d338bd201bc416dd7d78cba51e5193d484a8fb84a0f2bab2b4b65f12"
    ),
    "construction_master/2026-07-21-public-open-v31": (
        "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
    ),
    "construction_maps/2026-07-21-public-open-v31": (
        "73e913f53287a2474274b6ff16daf10dcb8cd2ceceadc766e9aedd9ba3852973"
    ),
    "audits/2026-07-21-public-open-coverage-v31": (
        "21b037ce0fb845184fe6cede7a954815482f5b7df84e79b62c06f1b70c77d45c"
    ),
    V83_REVIEW_DIRECTORY: (
        "20d577cf384a37994e7ecc6eb5494d5e3e1e790e505b7b867866292b4297fbec"
    ),
}

TIMESTAMP_PINS: tuple[tuple[str, tuple[str, ...], str, str, bool], ...] = (
    (
        "sources/current-coverage-2026-07-21-v24.json",
        ("generated_at",),
        "2026-07-21T19:02:00Z",
        "current_coverage_ledgers/2026-07-21-v24",
        False,
    ),
    (
        "sources/open-seed-2026-07-21-v86.json",
        ("build", "recorded_at"),
        "2026-07-21T20:19:16Z",
        "releases/2026-07-21-open-seed-v86",
        False,
    ),
    (
        "satellite_review_queues/2026-07-21-open-seed-v86/manifest.json",
        ("generated_at",),
        "2026-07-21T20:32:37Z",
        "satellite_review_queues/2026-07-21-open-seed-v86",
        True,
    ),
    (
        "sources/federation-2026-07-21-public-open-v35.json",
        ("generated_at",),
        "2026-07-21T20:45:00Z",
        "federated_indexes/2026-07-21-public-open-v35",
        False,
    ),
    (
        "sources/exact-identity-decisions-2026-07-21-public-open-v11.json",
        ("recorded_at",),
        "2026-07-21T23:44:08Z",
        "exact_identity_decisions/2026-07-21-public-open-v11",
        False,
    ),
    (
        "sources/construction-timeline-2026-07-21-public-open-v8.json",
        ("generated_at",),
        "2026-07-21T20:42:50Z",
        "construction_timelines/2026-07-21-public-open-v8",
        False,
    ),
    (
        "sources/construction-master-2026-07-21-public-open-v31.json",
        ("generated_at",),
        "2026-07-22T00:05:00Z",
        "construction_master/2026-07-21-public-open-v31",
        False,
    ),
    (
        "sources/construction-map-2026-07-21-public-open-v31.json",
        ("generated_at",),
        "2026-07-22T00:20:00Z",
        "construction_maps/2026-07-21-public-open-v31",
        False,
    ),
    (
        "sources/coverage-audit-2026-07-21-public-open-v31.json",
        ("generated_at",),
        "2026-07-22T01:17:00Z",
        "audits/2026-07-21-public-open-coverage-v31",
        False,
    ),
    (
        f"{V83_REVIEW_DIRECTORY}/definition.json",
        ("generated_at",),
        "2026-07-22T00:36:00.000000Z",
        V83_REVIEW_DIRECTORY,
        True,
    ),
)

CHECKPOINT_PATHS: Mapping[str, tuple[tuple[str, str], ...]] = {
    "construction-map-public-open-v31": (
        ("coverage", "construction_maps/2026-07-21-public-open-v31/coverage.json"),
        ("definition", "sources/construction-map-2026-07-21-public-open-v31.json"),
        ("manifest", "construction_maps/2026-07-21-public-open-v31/manifest.json"),
    ),
    "construction-master-public-open-v31": (
        ("coverage", "construction_master/2026-07-21-public-open-v31/coverage.json"),
        ("definition", "sources/construction-master-2026-07-21-public-open-v31.json"),
        ("manifest", "construction_master/2026-07-21-public-open-v31/manifest.json"),
    ),
    "construction-timeline-public-open-v8": (
        ("coverage", "construction_timelines/2026-07-21-public-open-v8/coverage.json"),
        ("definition", "sources/construction-timeline-2026-07-21-public-open-v8.json"),
        ("manifest", "construction_timelines/2026-07-21-public-open-v8/manifest.json"),
    ),
    "federation-public-open-v35": (
        ("index", "federated_indexes/2026-07-21-public-open-v35/federated-index.json"),
        ("manifest", "federated_indexes/2026-07-21-public-open-v35/manifest.json"),
    ),
    "exact-identity-decisions-public-open-v11": (
        ("accounting", "exact_identity_decisions/2026-07-21-public-open-v11/accounting.json"),
        ("definition", "sources/exact-identity-decisions-2026-07-21-public-open-v11.json"),
        ("manifest", "exact_identity_decisions/2026-07-21-public-open-v11/manifest.json"),
    ),
    "satellite-queue-open-seed-v86": (
        ("manifest", "satellite_review_queues/2026-07-21-open-seed-v86/manifest.json"),
        ("release_manifest", "releases/2026-07-21-open-seed-v86/manifest.json"),
    ),
    "seed-epoch-official-v86": (
        ("manifest", "releases/2026-07-21-open-seed-v86/manifest.json"),
    ),
}

LIMITATIONS: Mapping[str, tuple[str, ...]] = {
    "construction-map-public-open-v31": (
        "Map rows are a presentation derivative of construction-master v31 and must never be added to the master-row total.",
        "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
        "The 109,008 mapped rows and 373 unmapped rows are observation counts, not facilities or current construction claims.",
    ),
    "construction-master-public-open-v31": (
        "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred.",
        "Historical statuses are last-observed facts and do not establish current construction.",
        "The 109,381 master rows include review and discovery observations and are not unique physical sites.",
        "Candidate, review, imagery, and structural records remain outside Tier-A construction arithmetic.",
    ),
    "construction-timeline-public-open-v8": (
        "The 537 dated observations across 517 source-scoped timelines are a bounded partial chronology, not every-facility coverage.",
        "Last-observed statuses do not establish current construction; current status remains unknown.",
        "No interpolation, persistence, quarterly parity, cross-source identity resolution, or satellite lifecycle promotion is applied.",
    ),
    "federation-public-open-v35": (
        "Historical lifecycle observations are last-observed facts and do not establish current construction.",
        "The 16,352 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
        "The 6,719 pipeline records include 6,130 review-only rows and are not all confirmed construction sites.",
    ),
    "exact-identity-decisions-public-open-v11": (
        "Exact same-kind source-record components authorize neither cross-kind nor cross-source identity union.",
        "Explicit topology links are non-additive and are not unique physical-site counts.",
        "Review-only candidates remain excluded; physical-site bounds and unique physical sites remain null.",
    ),
    "satellite-queue-open-seed-v86": (
        "Queue jobs are review plans for source-scoped seed-v86 observations, not sites, imagery findings, or current construction evidence.",
        "Priority tiers use last-observed source status and do not establish that any observation remains under construction now.",
        "The queue is non-additive with seed v86; 712 coordinate-null observations remain outside imagery execution.",
    ),
    "seed-epoch-official-v86": (
        "The 927 source-scoped campus and project observations are not deduplicated physical sites.",
        "Status and lifecycle fields remain last-observed source facts; current status is not inferred.",
        "Capacity and energy fields remain source-scoped and are not globally additive.",
        "Representative points are source geometry only; geometry-only inference remains explicitly false.",
    ),
}

HISTORICAL_LIMITATION = (
    "This accepted seed-v83 execution-lane artifact is historical under the active seed-v86 chain and is not seed-v86 satellite coverage."
)


class CurrentCoverageV25Error(RuntimeError):
    """Raised when the bounded v25 transition cannot be proved."""


@dataclass(frozen=True)
class CurrentCoverageV25Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


def _canonical_json(value: object) -> bytes:
    return _v24._canonical_json(value)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_utc(value: str, label: str, *, seconds_only: bool = False) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CurrentCoverageV25Error(f"{label} must use canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as error:
        raise CurrentCoverageV25Error(f"{label} must use canonical UTC") from error
    allowed = {parsed.strftime("%Y-%m-%dT%H:%M:%SZ")}
    if not seconds_only:
        allowed.add(parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    if value not in allowed:
        raise CurrentCoverageV25Error(f"{label} must use canonical UTC")
    return parsed


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV25Error(f"{label} is not a regular file")
    return path.read_bytes()


def _json(path: Path, label: str) -> dict[str, Any]:
    raw = _regular_bytes(path, label)
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != _canonical_json(value):
        raise CurrentCoverageV25Error(f"{label} is not canonical JSON")
    return value


def _pointer(value: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise CurrentCoverageV25Error(f"invalid JSON pointer: {pointer}")
    current = value
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise CurrentCoverageV25Error(f"unresolved JSON pointer: {pointer}")
    return current


def _component_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    return _v24._component_digest(rows)


def _require_frozen_tree(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CurrentCoverageV25Error(f"{label} is not a regular directory")
    if tree_digest(path) != expected:
        raise CurrentCoverageV25Error(f"{label} tree changed")
    for item in (path, *path.rglob("*")):
        if item.is_symlink():
            raise CurrentCoverageV25Error(f"{label} contains a symlink")
        expected_mode = 0o555 if item.is_dir() else 0o444
        if stat.S_IMODE(item.stat().st_mode) != expected_mode:
            raise CurrentCoverageV25Error(f"{label} is not frozen: {item}")


def _timestamp_value(path: Path, keys: Sequence[str]) -> str:
    value: Any = _json(path, "timestamp source")
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise CurrentCoverageV25Error("timestamp field is absent")
        value = value[key]
    if not isinstance(value, str):
        raise CurrentCoverageV25Error("timestamp value is not a string")
    return value


def _require_inputs() -> tuple[tuple[str, datetime], ...]:
    review_prefix = f"{V83_REVIEW_DIRECTORY}/"
    files = dict(PINNED_FILES)
    files.update(
        {
            review_prefix + name: pin
            for name, pin in V83_REVIEW_MEMBER_PINS.items()
        }
    )
    for relative, (expected_bytes, expected_sha) in files.items():
        path = ROOT / relative
        raw = _regular_bytes(path, f"accepted {relative}")
        if (
            len(raw) != expected_bytes
            or _sha256(raw) != expected_sha
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CurrentCoverageV25Error(f"accepted file changed: {relative}")
    for relative, digest in PINNED_TREES.items():
        _require_frozen_tree(ROOT / relative, digest, f"accepted {relative}")

    result: list[tuple[str, datetime]] = []
    for source_rel, keys, expected, bundle_rel, source_is_member in TIMESTAMP_PINS:
        source = ROOT / source_rel
        bundle = ROOT / bundle_rel
        if _timestamp_value(source, keys) != expected:
            raise CurrentCoverageV25Error(f"accepted timestamp changed: {source_rel}")
        timestamp = _parse_utc(expected, f"accepted {source_rel}")
        for path in (source, bundle, *bundle.rglob("*")):
            metadata = path.stat(follow_symlinks=False)
            birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
            if max(birth, metadata.st_mtime) > timestamp.timestamp() + 0.000_001:
                raise CurrentCoverageV25Error(
                    f"accepted input post-dates timestamp: {path}"
                )
        roots = (bundle,) if source_is_member else (source, bundle)
        for path in roots:
            if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < timestamp.timestamp():
                raise CurrentCoverageV25Error(
                    f"accepted publication root predates timestamp: {path}"
                )
        result.append((source_rel, timestamp))
    return tuple(result)


def _require_dependencies_before(target: datetime) -> None:
    for label, timestamp in _require_inputs():
        if timestamp >= target:
            raise CurrentCoverageV25Error(
                f"accepted dependency is not prior to v25: {label}"
            )


def _load_base() -> tuple[dict[str, Any], dict[str, Any]]:
    definition = _json(BASE_DEFINITION, "accepted v24 definition")
    ledger = _json(BASE_BUNDLE / LEDGER_FILENAME, "accepted v24 ledger")
    manifest = _json(BASE_BUNDLE / MANIFEST_FILENAME, "accepted v24 manifest")
    if (
        definition.get("ledger_id") != BASE_LINEAGE["ledger_id"]
        or ledger.get("ledger_id") != BASE_LINEAGE["ledger_id"]
        or manifest.get("ledger_id") != BASE_LINEAGE["ledger_id"]
        or manifest.get("definition") != BASE_LINEAGE["definition"]
    ):
        raise CurrentCoverageV25Error("accepted v24 lineage changed")
    return definition, ledger


def _checkpoint(
    checkpoint_id: str,
    path: str,
    *,
    binding: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    raw = _regular_bytes(ROOT / path, f"checkpoint {checkpoint_id}")
    result: dict[str, Any] = {
        "bytes": len(raw),
        "checkpoint_id": checkpoint_id,
        "path": path,
        "sha256": _sha256(raw),
    }
    if binding is not None:
        result["binding"] = dict(binding)
    return result


def _metric(
    label: str, checkpoint_id: str, pointer: str, value: Any
) -> dict[str, Any]:
    return {
        "checkpoint_id": checkpoint_id,
        "json_pointer": pointer,
        "label": label,
        "value": value,
    }


def _refreshed_metrics(
    base: Mapping[str, Any], checkpoints: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    documents = {
        checkpoint["checkpoint_id"]: _json(
            ROOT / checkpoint["path"],
            f"metric checkpoint {checkpoint['checkpoint_id']}",
        )
        for checkpoint in checkpoints
    }
    metrics = []
    for raw in base["metrics"]:
        metric = deepcopy(raw)
        metric["value"] = _pointer(
            documents[metric["checkpoint_id"]], metric["json_pointer"]
        )
        metrics.append(metric)
    return metrics


def _replacement_entries(
    base_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for old_id, new_id in sorted(ARTIFACT_REPLACEMENTS.items()):
        base = deepcopy(dict(base_entries[old_id]))
        base["artifact_id"] = new_id
        if new_id == "coverage-audit-public-open-v31":
            checkpoints = [
                _checkpoint(
                    "audit",
                    "audits/2026-07-21-public-open-coverage-v31/coverage-audit.json",
                    binding={
                        "checkpoint_id": "manifest",
                        "json_pointer": "/artifacts/coverage-audit.json",
                    },
                ),
                _checkpoint(
                    "manifest",
                    "audits/2026-07-21-public-open-coverage-v31/manifest.json",
                ),
            ]
            metrics = [
                _metric("coverage_groups", "manifest", "/counts/coverage_groups", 979),
                _metric(
                    "methodology_support_artifacts",
                    "manifest",
                    "/counts/methodology_support_artifacts",
                    2,
                ),
                _metric(
                    "non_review_source_scoped_rows",
                    "audit",
                    "/totals/non_review_source_scoped_entity_records",
                    10_222,
                ),
                _metric("open_gaps", "manifest", "/counts/open_gaps", 4_582),
                _metric(
                    "review_only_source_scoped_rows",
                    "audit",
                    "/totals/review_only_source_scoped_entity_records",
                    6_130,
                ),
                _metric(
                    "source_scoped_rows",
                    "manifest",
                    "/counts/source_scoped_entity_records",
                    16_352,
                ),
                _metric(
                    "unique_physical_sites",
                    "manifest",
                    "/counts/unique_physical_sites",
                    None,
                ),
                _metric("v57_review_jobs", "manifest", "/counts/v57_review_jobs", 74),
                _metric("v57_review_views", "manifest", "/counts/v57_review_views", 71),
                _metric("v83_decision_rows", "manifest", "/counts/v83_decision_rows", 68),
                _metric("v83_promotions", "manifest", "/counts/v83_promotions", 0),
                _metric(
                    "v83_unique_exact_visual_evidence_sets",
                    "manifest",
                    "/counts/v83_unique_exact_visual_evidence_sets",
                    65,
                ),
            ]
            limitations = [
                "Gap and group counts are source-scoped coverage-accounting units, not site counts.",
                "The two reviewed imagery artifacts are non-countable, non-promoted methodology support and create no facility, lifecycle, identity, status, or capacity claim.",
                "Unique physical sites and SemiAnalysis parity remain unknown and pending.",
            ]
        else:
            old_by_id = {
                checkpoint["checkpoint_id"]: checkpoint
                for checkpoint in base["checkpoints"]
            }
            checkpoints = [
                _checkpoint(
                    checkpoint_id,
                    path,
                    binding=old_by_id[checkpoint_id].get("binding"),
                )
                for checkpoint_id, path in CHECKPOINT_PATHS[new_id]
            ]
            metrics = _refreshed_metrics(base, checkpoints)
            if new_id == "seed-epoch-official-v86":
                metrics.append(
                    _metric(
                        "geometry_only_representative_point_inferred",
                        "manifest",
                        "/geometry_only_representative_point_inferred",
                        False,
                    )
                )
                metrics.sort(key=lambda metric: metric["label"])
            limitations = list(LIMITATIONS[new_id])
        base["checkpoints"] = checkpoints
        base["limitations"] = sorted(limitations)
        base["metrics"] = metrics
        result[new_id] = base
    return result


def _review_addition() -> dict[str, Any]:
    artifact_paths = {
        "blind_decisions": "blind-decisions.json",
        "blind_review_part_a": "blind-review-part-a.json",
        "blind_review_part_b": "blind-review-part-b.json",
        "definition": "definition.json",
        "summary": "summary.json",
    }
    checkpoints = []
    for checkpoint_id, filename in sorted(artifact_paths.items()):
        checkpoints.append(
            _checkpoint(
                checkpoint_id,
                f"{V83_REVIEW_DIRECTORY}/{filename}",
                binding={
                    "checkpoint_id": "manifest",
                    "json_pointer": f"/artifacts/{filename}",
                },
            )
        )
    checkpoints.append(
        _checkpoint("manifest", f"{V83_REVIEW_DIRECTORY}/manifest.json")
    )
    checkpoints.sort(key=lambda checkpoint: checkpoint["checkpoint_id"])
    metrics = [
        _metric("analyst_decision_rows", "summary", "/counts/analyst_decision_rows", 68),
        _metric("atlas_mutation", "manifest", "/guardrails/atlas_mutation", False),
        _metric(
            "automated_promotion_allowed",
            "manifest",
            "/guardrails/automated_promotion_allowed",
            False,
        ),
        _metric(
            "construction_status_claim_created",
            "manifest",
            "/guardrails/construction_status_claim_created",
            False,
        ),
        _metric(
            "current_status_claim_created",
            "manifest",
            "/guardrails/current_status_claim_created",
            False,
        ),
        _metric(
            "decisions_rejected_for_site_promotion",
            "summary",
            "/accounting/decision_rows/promotion_dispositions/rejected_for_site_promotion",
            21,
        ),
        _metric(
            "decisions_retained_for_manual_followup",
            "summary",
            "/accounting/decision_rows/promotion_dispositions/retained_for_manual_followup",
            47,
        ),
        _metric(
            "exact_duplicate_groups",
            "summary",
            "/counts/exact_duplicate_groups",
            3,
        ),
        _metric(
            "lifecycle_status_claim_created",
            "manifest",
            "/guardrails/lifecycle_status_claim_created",
            False,
        ),
        _metric(
            "reviewer_similarity_used_for_exact_deduplication",
            "summary",
            "/accounting/reviewer_similarity_flags/1/counted_as_exact_duplicate",
            False,
        ),
        _metric(
            "satellite_confirmation_claim_created",
            "manifest",
            "/guardrails/satellite_confirmation_claim_created",
            False,
        ),
        _metric(
            "unique_exact_visual_evidence_sets",
            "summary",
            "/counts/unique_exact_visual_evidence_sets",
            65,
        ),
        _metric(
            "unique_retained_exact_visual_evidence_sets",
            "summary",
            "/accounting/unique_exact_visual_evidence_sets/promotion_dispositions/retained_for_manual_followup",
            44,
        ),
        _metric(
            "unique_site_claim_created",
            "manifest",
            "/guardrails/unique_site_claim_created",
            False,
        ),
        _metric(
            "x052_x041_exact_four_image_hash_match",
            "summary",
            "/accounting/reviewer_similarity_flags/1/exact_four_image_hash_match",
            False,
        ),
    ]
    metrics.sort(key=lambda metric: metric["label"])
    return {
        "access_tier": "public_open",
        "artifact_id": V83_REVIEW_ARTIFACT_ID,
        "artifact_kind": "analyst_imagery_review",
        "checkpoints": checkpoints,
        "current_role": "public_supporting_review_lane",
        "evidence_scope": "review_only",
        "limitations": sorted(
            [
                "The 68 fixed analyst decisions and 65 unique exact visual-evidence sets are non-additive review records, not sites, facilities, construction truths, lifecycle observations, or child evidence.",
                "Forty-seven decisions covering 44 unique exact sets remain manual follow-up only; 21 decisions are rejected for site promotion and zero decisions are promoted.",
                "Three exact duplicate groups are counted once; X052/X041 is approximate-only and is not used for exact deduplication.",
                "The frozen review creates no Atlas mutation, satellite confirmation, current-status, identity, capacity, power, workload, or unique-site claim.",
            ]
        ),
        "metrics": metrics,
        "publication_mode": "public_review_or_discovery",
        "record_units": ["aggregate_report_metric", "review_record"],
        "redistribution_status": "eligible_with_upstream_terms",
    }


UPDATED_GAP_SUMMARIES = {
    "benchmark-parity-not-computed": (
        "No licensed row-level external benchmark denominator is pinned. The "
        "517 bounded source-scoped timelines and reviewed imagery support provide "
        "neither recall nor SemiAnalysis-equivalent current-status, field, feature, "
        "or quarterly parity."
    ),
    "global-construction-coverage-partial": (
        "The expanded source-scoped seed, review lanes, and 517 last-observed "
        "timelines do not establish a complete global construction census. Review "
        "support is non-additive and promotes no site or lifecycle claim."
    ),
    "satellite-review-backlog": (
        "The current seed-v86 queue has 215 review jobs while 712 seed observations "
        "lack coordinates. The frozen 68-decision v83 carrier retains 47 decisions "
        "for manual follow-up, rejects 21, and promotes zero; three exact duplicate "
        "groups count once and X052/X041 remains approximate-only. Older v83 and "
        "v71 execution lanes are historical."
    ),
    "site-resolution-partial": (
        "Resolution links, 517 source-scoped timelines, and selected imagery labels "
        "are not cross-source-deduplicated; unique physical sites remain null."
    ),
}


def _parity_gaps(base: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for raw in base["parity_gaps"]:
        gap = deepcopy(raw)
        gap["affected_artifact_ids"] = sorted(
            ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        )
        if gap["gap_id"] in {
            "global-construction-coverage-partial",
            "satellite-review-backlog",
        }:
            gap["affected_artifact_ids"] = sorted(
                {*gap["affected_artifact_ids"], V83_REVIEW_ARTIFACT_ID}
            )
        if gap["gap_id"] in UPDATED_GAP_SUMMARIES:
            gap["summary"] = UPDATED_GAP_SUMMARIES[gap["gap_id"]]
        result.append(gap)
    return result


def _transformed_entries() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base, _ledger = _load_base()
    base_entries = {
        entry["artifact_id"]: deepcopy(entry) for entry in base["entries"]
    }
    unchanged = [
        base_entries[artifact_id]
        for artifact_id in sorted(
            set(base_entries) - REMOVED_ARTIFACT_IDS - HISTORICALIZED_ARTIFACT_IDS
        )
    ]
    removed = [base_entries[artifact_id] for artifact_id in sorted(REMOVED_ARTIFACT_IDS)]
    historicalized = []
    for artifact_id in sorted(HISTORICALIZED_ARTIFACT_IDS):
        entry = base_entries[artifact_id]
        entry["limitations"] = sorted([*entry["limitations"], HISTORICAL_LIMITATION])
        historicalized.append(entry)
    replacements = list(_replacement_entries(base_entries).values())
    addition = _review_addition()
    additions = [addition]
    combined = {
        entry["artifact_id"]: entry
        for entry in (*unchanged, *historicalized, *replacements, *additions)
    }
    ordered = [combined[artifact_id] for artifact_id in sorted(combined)]
    components = {
        "added_1_sha256": _component_digest(additions),
        "all_53_sha256": _component_digest(ordered),
        "historicalized_2_sha256": _component_digest(historicalized),
        "removed_8_sha256": _component_digest(removed),
        "replacement_8_sha256": _component_digest(replacements),
        "unchanged_42_sha256": _component_digest(unchanged),
    }
    if (
        len(base_entries) != 52
        or len(unchanged) != 42
        or len(removed) != 8
        or len(historicalized) != 2
        or len(replacements) != 8
        or len(additions) != 1
        or len(ordered) != 53
    ):
        raise CurrentCoverageV25Error("v25 successor arithmetic changed")
    return ordered, components


def preview_v25_delta() -> dict[str, Any]:
    _require_inputs()
    base, _ledger = _load_base()
    entries, components = _transformed_entries()
    gaps = _parity_gaps(base)
    return {
        **components,
        "added_ids": sorted(ADDED_ARTIFACT_IDS),
        "base_entries": 52,
        "final_entries": len(entries),
        "historicalized_ids": sorted(HISTORICALIZED_ARTIFACT_IDS),
        "parity_gaps_sha256": _sha256(_canonical_json(gaps)),
        "replacement_ids": sorted(REPLACEMENT_ARTIFACT_IDS),
    }


def _require_component_fuses(preview: Mapping[str, Any]) -> None:
    expected = {
        "added_1_sha256": ADDED_1_SHA256,
        "all_53_sha256": ALL_53_SHA256,
        "historicalized_2_sha256": HISTORICALIZED_2_SHA256,
        "parity_gaps_sha256": PARITY_GAPS_SHA256,
        "removed_8_sha256": REMOVED_8_SHA256,
        "replacement_8_sha256": REPLACEMENT_8_SHA256,
        "unchanged_42_sha256": UNCHANGED_42_SHA256,
    }
    if any(value is None for value in expected.values()):
        raise CurrentCoverageV25Error("v25 component digest fuses are unresolved")
    for key, value in expected.items():
        if preview[key] != value:
            raise CurrentCoverageV25Error(f"v25 component digest changed: {key}")


def definition_document(generated_at: str, *, require_fuses: bool = True) -> dict[str, Any]:
    generated = _parse_utc(generated_at, "v25 generated_at", seconds_only=True)
    _require_dependencies_before(generated)
    base, _ledger = _load_base()
    entries, components = _transformed_entries()
    gaps = _parity_gaps(base)
    preview = {
        **components,
        "parity_gaps_sha256": _sha256(_canonical_json(gaps)),
    }
    if require_fuses:
        _require_component_fuses(preview)
        if V25_GENERATED_AT is None or generated_at != V25_GENERATED_AT:
            raise CurrentCoverageV25Error("v25 generated_at fuse changed")
    document = {
        "base_ledger": BASE_LINEAGE,
        "entries": entries,
        "generated_at": generated_at,
        "ledger_id": V25_LEDGER_ID,
        "parity_gaps": gaps,
        "schema_version": DEFINITION_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    if any(token in raw for token in FORBIDDEN_FUTURE_TOKENS):
        raise CurrentCoverageV25Error("v25 contains future lineage")
    if require_fuses:
        if V25_DEFINITION_SHA256 is None or _sha256(raw) != V25_DEFINITION_SHA256:
            raise CurrentCoverageV25Error("v25 definition digest fuse changed")
    return document


def _implementation_pins() -> dict[str, Any]:
    paths = {
        "cli": ROOT / "scripts/build_current_coverage_ledger_v25.py",
        "module": Path(__file__).resolve(),
        "root_shim": ROOT / "current_coverage_v25.py",
        "v21_schema_helper": Path(_v21.__file__).resolve(),
        "v22_schema_helper": Path(_v22.__file__).resolve(),
        "v24_predecessor": Path(_v24.__file__).resolve(),
    }
    result = {}
    for label, path in sorted(paths.items()):
        raw = path.read_bytes()
        result[label] = {
            "bytes": len(raw),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": _sha256(raw),
        }
    return result


def _validate_definition(
    definition_path: Path, *, require_live: bool
) -> tuple[dict[str, Any], bytes, datetime]:
    raw = _regular_bytes(definition_path, "v25 definition")
    document = json.loads(raw)
    if raw != _canonical_json(document):
        raise CurrentCoverageV25Error("v25 definition is not canonical")
    if stat.S_IMODE(definition_path.stat().st_mode) != 0o444:
        raise CurrentCoverageV25Error("v25 definition is not frozen 0444")
    generated_at = document.get("generated_at")
    generated = _parse_utc(generated_at, "v25 generated_at", seconds_only=True)
    if require_live and generated > datetime.now(UTC):
        raise CurrentCoverageV25Error("v25 generated_at exceeds wall clock")
    if document != definition_document(generated_at):
        raise CurrentCoverageV25Error("v25 definition is not the bounded successor")
    if V25_DEFINITION_SHA256 is None or _sha256(raw) != V25_DEFINITION_SHA256:
        raise CurrentCoverageV25Error("v25 definition checkpoint changed")
    return document, raw, generated


def build_current_coverage_ledger_v25(
    definition_path: str | Path,
) -> CurrentCoverageV25Bundle:
    definition, definition_raw, _generated = _validate_definition(
        Path(definition_path), require_live=False
    )
    _base_definition, base_ledger = _load_base()
    artifacts = []
    previous_id: str | None = None
    for entry in definition["entries"]:
        try:
            artifact = _v21._entry_v4(ROOT, entry, previous_id)
        except _v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV25Error(str(error)) from error
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _v21._legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _v21._legacy.CurrentCoverageError as error:
        raise CurrentCoverageV25Error(str(error)) from error
    inventory = _v21._inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(base_ledger["artifact_inventory_counts"])
    addition = next(
        entry for entry in definition["entries"] if entry["artifact_id"] == V83_REVIEW_ARTIFACT_ID
    )
    expected_inventory["artifacts"] += 1
    expected_inventory["by_access_tier"][addition["access_tier"]] += 1
    expected_inventory["by_evidence_scope"][addition["evidence_scope"]] += 1
    expected_inventory["by_publication_mode"][addition["publication_mode"]] += 1
    expected_inventory["by_redistribution_status"][addition["redistribution_status"]] += 1
    for unit in addition["record_units"]:
        expected_inventory["by_record_unit"][unit] += 1
    expected_inventory["public_open_review_only_artifacts"] += 1
    if inventory != expected_inventory:
        raise CurrentCoverageV25Error("v25 inventory arithmetic changed")
    ledger = {
        "artifact_inventory_counts": inventory,
        "artifacts": artifacts,
        "base_ledger": BASE_LINEAGE,
        "format": LEDGER_FORMAT_V4,
        "generated_at": definition["generated_at"],
        "ledger_id": V25_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    ledger_bytes = _canonical_json(ledger)
    preview = preview_v25_delta()
    _require_component_fuses(preview)
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "base_bundle": {
            "manifest_sidecar": BASE_SIDECAR,
            "tree_sha256": BASE_TREE_SHA256,
        },
        "base_ledger": BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V25_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT_V4,
        "generated_at": definition["generated_at"],
        "implementation": _implementation_pins(),
        "input_checkpoints": {
            artifact["artifact_id"]: {
                checkpoint["checkpoint_id"]: {
                    "bytes": checkpoint["bytes"],
                    "path": checkpoint["path"],
                    "sha256": checkpoint["sha256"],
                }
                for checkpoint in artifact["checkpoints"]
            }
            for artifact in artifacts
        },
        "input_member_checkpoints": {
            V83_REVIEW_ARTIFACT_ID: {
                name: {"bytes": size, "sha256": digest}
                for name, (size, digest) in sorted(V83_REVIEW_MEMBER_PINS.items())
            }
        },
        "input_modes": {
            "bundle_directories": "0555",
            "bundle_files": "0444",
            "standalone_definitions": "0444",
        },
        "input_timestamps": {
            source: {
                "bundle": bundle,
                "field": ".".join(keys),
                "source_is_bundle_member": source_is_member,
                "value": value,
            }
            for source, keys, value, bundle, source_is_member in TIMESTAMP_PINS
        },
        "input_trees": dict(sorted(PINNED_TREES.items())),
        "ledger_id": V25_LEDGER_ID,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
        "successor_delta": preview,
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar = f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    return CurrentCoverageV25Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=sidecar,
        ledger=ledger,
        manifest=manifest,
    )


def _validate_bundle(
    bundle: Path, *, definition_path: Path, require_live: bool, rebuild: bool
) -> dict[str, Any]:
    if bundle.is_symlink() or not bundle.is_dir():
        raise CurrentCoverageV25Error("v25 bundle is not a regular directory")
    entries = list(bundle.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV25Error("v25 bundle file set changed")
    if stat.S_IMODE(bundle.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV25Error("v25 bundle is not frozen 0555/0444")
    definition, _raw, generated = _validate_definition(
        definition_path, require_live=require_live
    )
    expected = build_current_coverage_ledger_v25(definition_path)
    expected_files = {
        LEDGER_FILENAME: expected.ledger_bytes,
        MANIFEST_FILENAME: expected.manifest_bytes,
        MANIFEST_HASH_FILENAME: expected.manifest_hash_bytes,
    }
    for filename, raw in expected_files.items():
        if bundle.joinpath(filename).read_bytes() != raw:
            raise CurrentCoverageV25Error(f"v25 artifact changed: {filename}")
    ledger = expected.ledger
    ids = {artifact["artifact_id"] for artifact in ledger["artifacts"]}
    if (
        len(ids) != 53
        or ids & REMOVED_ARTIFACT_IDS
        or not NEW_ARTIFACT_IDS <= ids
        or ledger["scope"]["unique_physical_site_count"] is not None
    ):
        raise CurrentCoverageV25Error("v25 semantic inventory changed")
    review = next(
        artifact
        for artifact in ledger["artifacts"]
        if artifact["artifact_id"] == V83_REVIEW_ARTIFACT_ID
    )
    if (
        review["review_only"] is not True
        or review["reported_metrics"]["analyst_decision_rows"] != 68
        or review["reported_metrics"]["unique_exact_visual_evidence_sets"] != 65
        or review["reported_metrics"]["automated_promotion_allowed"] is not False
    ):
        raise CurrentCoverageV25Error("v25 review-support semantics changed")
    if expected.manifest["implementation"] != _implementation_pins():
        raise CurrentCoverageV25Error("v25 implementation pins changed")
    if require_live:
        for root in (definition_path, bundle):
            if root.stat().st_ctime + 0.000_001 < generated.timestamp():
                raise CurrentCoverageV25Error("v25 final rename predates generated_at")
    if rebuild:
        second = build_current_coverage_ledger_v25(definition_path)
        if second != expected:
            raise CurrentCoverageV25Error("v25 double reconstruction changed")
    if definition["generated_at"] != expected.manifest["generated_at"]:
        raise CurrentCoverageV25Error("v25 definition and bundle time differ")
    return dict(expected.manifest)


def _write_bundle(path: Path, bundle: CurrentCoverageV25Bundle) -> None:
    files = {
        LEDGER_FILENAME: bundle.ledger_bytes,
        MANIFEST_FILENAME: bundle.manifest_bytes,
        MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }
    for filename, raw in sorted(files.items()):
        with path.joinpath(filename).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _stage_latest(definition: Path, bundle: Path) -> float:
    values = []
    for path in (definition, bundle, *bundle.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise CurrentCoverageV25Error("filesystem birth time is unavailable")
        values.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(values)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise CurrentCoverageV25Error("v25 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _now() -> datetime:
    return datetime.now(UTC)


def _discard_file(path: Path) -> None:
    if path.exists() and not path.is_symlink() and path.is_file():
        path.chmod(0o600)
        path.unlink()


def _discard_bundle(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for item in path.iterdir():
        if item.is_symlink() or not item.is_file() or item.name not in BUNDLE_FILES:
            raise CurrentCoverageV25Error("refusing contaminated v25 cleanup")
        item.chmod(0o600)
    shutil.rmtree(path)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise CurrentCoverageV25Error("active v25 publication lock exists") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        PUBLICATION_LOCK.unlink(missing_ok=True)


def _require_unpublished() -> None:
    for path in (DEFINITION, BUNDLE):
        if path.exists() or path.is_symlink():
            raise CurrentCoverageV25Error(f"refusing replacement of v25: {path}")


def _rollback(definition_published: bool, bundle_published: bool) -> None:
    if definition_published and DEFINITION.exists():
        rollback = DEFINITION.parent / f".{DEFINITION.name}.rollback-{os.getpid()}"
        promote_noreplace(DEFINITION, rollback)
        _discard_file(rollback)
    if bundle_published and BUNDLE.exists():
        rollback = BUNDLE.parent / f".{BUNDLE.name}.rollback-{os.getpid()}"
        BUNDLE.chmod(0o755)
        promote_noreplace(BUNDLE, rollback)
        _discard_bundle(rollback)


def publish_current_coverage_ledger_v25(generated_at: str) -> dict[str, Any]:
    target = _parse_utc(generated_at, "v25 generated_at", seconds_only=True)
    if target <= _now():
        raise CurrentCoverageV25Error("v25 generated_at must be in the future")
    if V25_GENERATED_AT is None or generated_at != V25_GENERATED_AT:
        raise CurrentCoverageV25Error("v25 generated_at fuse changed")
    _require_dependencies_before(target)
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CurrentCoverageV25Error(f"invalid v25 output parent: {parent}")
    with _publication_lock():
        _require_unpublished()
        descriptor, definition_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.stage-", dir=DEFINITION.parent
        )
        definition_stage = Path(definition_name)
        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.stage-", dir=BUNDLE.parent)
        )
        definition_published = False
        bundle_published = False
        try:
            raw = _canonical_json(definition_document(generated_at))
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            first = build_current_coverage_ledger_v25(definition_stage)
            second = build_current_coverage_ledger_v25(definition_stage)
            if first != second:
                raise CurrentCoverageV25Error("two offline v25 builds differ")
            _write_bundle(bundle_stage, first)
            for item in bundle_stage.iterdir():
                item.chmod(0o444)
            bundle_stage.chmod(0o555)
            _validate_bundle(
                bundle_stage,
                definition_path=definition_stage,
                require_live=False,
                rebuild=True,
            )
            if _stage_latest(definition_stage, bundle_stage) > target.timestamp() + 0.000_001:
                raise CurrentCoverageV25Error("v25 private stage post-dates generated_at")
            _wait_until(target)
            _require_unpublished()
            bundle_stage.chmod(0o755)
            promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            BUNDLE.chmod(0o555)
            promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            return validate_current_coverage_ledger_v25()
        except BaseException as error:
            try:
                _rollback(definition_published, bundle_published)
            except BaseException as rollback_error:
                error.add_note(f"v25 rollback failed: {rollback_error}")
            raise
        finally:
            if not bundle_published:
                _discard_bundle(bundle_stage)
            if not definition_published:
                _discard_file(definition_stage)


def validate_current_coverage_ledger_v25() -> dict[str, Any]:
    _require_inputs()
    manifest = _validate_bundle(
        BUNDLE, definition_path=DEFINITION, require_live=True, rebuild=True
    )
    generated = _parse_utc(manifest["generated_at"], "v25 generated_at", seconds_only=True)
    for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        expected_mode = 0o555 if path.is_dir() else 0o444
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise CurrentCoverageV25Error(f"v25 artifact is not frozen: {path}")
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise CurrentCoverageV25Error(f"v25 artifact post-dates generated_at: {path}")
    return manifest


__all__ = [
    "ADDED_ARTIFACT_IDS",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE",
    "CurrentCoverageV25Error",
    "DEFINITION",
    "HISTORICALIZED_ARTIFACT_IDS",
    "REPLACEMENT_ARTIFACT_IDS",
    "V25_LEDGER_ID",
    "V83_REVIEW_ARTIFACT_ID",
    "build_current_coverage_ledger_v25",
    "definition_document",
    "preview_v25_delta",
    "publish_current_coverage_ledger_v25",
    "validate_current_coverage_ledger_v25",
]
