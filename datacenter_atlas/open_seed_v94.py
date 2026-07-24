"""Build open seed v94 as the governed ten-source successor to v93."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import bitdeer_official_wenatchee_massillon_current_build_gap_20260722 as bitdeer
from . import goodman_databank_lax01_official_enrichment_20260722 as goodman
from . import hut8_river_bend_official_current_build_gap_20260722 as river
from . import merlin_cyrusone_beale_official_current_build_gap_v2_20260722 as merlin_v2
from . import open_seed_v69 as v69
from . import open_seed_v70 as v70
from . import open_seed_v85 as v85
from . import open_seed_v93 as v93
from .publication_release import build_release_documents
from .service import _current_rows


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v93.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v93"
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v94.json"
RELEASE_ID = "2026-07-21-open-seed-v94"
RELEASE = ROOT / "releases" / RELEASE_ID
PUBLICATION_LOCK = ROOT / ".open-seed-v94.lock"
AS_OF = "2026-07-22"

BASE_RECORDED_AT = "2026-07-22T02:54:34Z"
BASE_DEFINITION_PIN = (
    110_743,
    "cf8ed21cd0816f457fa2cede36fbf1bf012d62ed61d03a5e3213de9946394e9c",
)
BASE_MANIFEST_PIN = (
    16_832,
    "9a5b39004ab1a4c7994ad653d5d9603572b4a47a3c502ea222eeae38d32fa05c",
)
BASE_TREE_SHA256 = "71c531ffa7f8383e2ae553a71abe15e940e8d6251acccbf17556bc492df78f0d"
BASE_ENTITIES_PIN = (
    1_029_791,
    "f690d838165ced6822b891f5099adea82db46fba97e53dbcb462328b5af6628b",
)
BASE_SOURCE_INPUTS_PIN = (
    414_095,
    "81cf558da4aef80bdc957116ceda84cd565960b6471db0ada95cddd02e0f483e",
)

OFFICIAL_SPECS: dict[str, dict[str, Any]] = {}

ADDITION_ORDER = (
    *(f"sources/{name}" for name in merlin_v2.SOURCE_FILENAMES),
    *(f"sources/{name}" for name in bitdeer.SOURCE_FILENAMES),
    f"sources/{river.SOURCE_FILENAME}",
    f"sources/{goodman.SOURCE_FILENAME}",
)
ADDITION_PINS = {
    ADDITION_ORDER[0]: (6_371, "2385887a06e05885dfbb64b7868b1571d14879815e58e92a0347b9f279c4d30d"),
    ADDITION_ORDER[1]: (6_371, "40353acf426a4193037aeceb89c06ff2340f761ba6374226ab70c3e7530adb42"),
    ADDITION_ORDER[2]: (4_214, "576edad0e0eac03fbab0b4232c6cb513048c85efa5c314649916596a6bcf8806"),
    ADDITION_ORDER[3]: (6_934, "e4b3cf1d11434a434df7f412126c1f4d8f99182a8c5da0ecdedc21f47ff97b8e"),
    ADDITION_ORDER[4]: (9_123, "d0a2f250ebf8a1861a119f1e6da3512355fb6909dca62dcb8c1e6cdd367bc0e3"),
    ADDITION_ORDER[5]: (13_631, "2f9f99472b5ca33bd1833535073e81f82d1d4925eb5c1a87923922bc0f7b547a"),
    ADDITION_ORDER[6]: (5_605, "5008be9fc5496c0a6eafe97fea6b0138ba5ad4ca56f6a881d1c3aada85a75f4a"),
    ADDITION_ORDER[7]: (6_421, "ff868620cc4fc17cb64abb9e243cfaa58750dd52cbc099cb2f5e1fbf52074fa1"),
    ADDITION_ORDER[8]: (16_044, "0e5139ef2935accca6e0dafcbde324f5cfb730ff855c526f9b835afe9c7919f4"),
    ADDITION_ORDER[9]: (13_595, "fc07e93af6357b754ee6b03d052958e9f73201c177459cf1d2c19b4ca4a5ebf5"),
}
SOURCE_CTIME_NS = {
    ADDITION_ORDER[0]: 1_784_687_829_006_126_656,
    ADDITION_ORDER[1]: 1_784_687_829_006_481_367,
    ADDITION_ORDER[2]: 1_784_687_829_006_579_368,
    ADDITION_ORDER[3]: 1_784_687_829_006_668_369,
    ADDITION_ORDER[4]: 1_784_688_228_007_526_400,
    ADDITION_ORDER[5]: 1_784_688_228_008_148_988,
    ADDITION_ORDER[6]: 1_784_688_690_004_060_311,
    ADDITION_ORDER[7]: 1_784_688_690_004_184_311,
    ADDITION_ORDER[8]: 1_784_689_369_005_040_419,
    ADDITION_ORDER[9]: 1_784_689_864_001_801_208,
}

REJECTED_V1_ID = "merlin-cyrusone-beale-official-current-build-gap-2026-07-22-v1"
REJECTED_V1_RECORDED_AT = "2026-07-22T02:37:09Z"
REJECTED_V1_LOGICAL_TREE_SHA256 = "f2f2910ae25758a82e85224d5d1ab616471f22d733cc535ab35574213f48d9f5"
REJECTED_V1_PHYSICAL_TREE_SHA256 = "5ad26f77d9ef44683dec48b63b7e0bd2f32a46b6fe7ba0c0a4b94534226dba3e"
REJECTED_V1_ROOT_CTIME_NS = 1_784_687_829_007_048_496
REJECTED_V1_MEMBER_PINS = {
    "README.md": (2_103, "4d7b439826977e3bfa27eb8b7eeab16ba4d1580e60929fd71c664b7f3b543bb9", 1_784_687_829_005_061_523),
    "candidate-assessment.json": (7_095, "47423387f64056a91f3dad58a1c5e4f185aeb5afbbcc9c134080d606cd51421c", 1_784_687_829_005_019_856),
    "manifest.json": (1_824, "a2daf458cacfebc5a8614c36e7e89984e7bd7cb086482e2c0a1d4cdb888b634e", 1_784_687_829_005_102_148),
    "manifest.sha256": (80, "7d99f066d5abfbb7d8a9520a56bf391f8aeca5c858afa1550619455ba86a6527", 1_784_687_829_004_968_814),
    "retrieval-inventory.json": (20_462, "ffc15fda72de99adf4698bce7f835015a666ff7f1358e00563b325b9dfc89881", 1_784_687_829_005_140_940),
    "rights-and-disposition.json": (1_137, "bcf5492996637065102b3f2db132c45abd9ad84b4f350e40cc8a5133e875e279", 1_784_687_829_005_181_024),
    "source-snapshot.json": (8_248, "47fb016799d871571fdd36265c8120c9610c337082acceb93847ba1182f174b1", 1_784_687_829_005_220_566),
}
REJECTED_V1_SOURCE_PINS = {
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-2-current-build.json": (6_371, "2385887a06e05885dfbb64b7868b1571d14879815e58e92a0347b9f279c4d30d", 1_784_687_829_006_126_656),
    "curated-official-2026-07-22-merlin-bilbao-arasur-building-3-current-build.json": (6_371, "40353acf426a4193037aeceb89c06ff2340f761ba6374226ab70c3e7530adb42", 1_784_687_829_006_481_367),
    "curated-official-2026-07-22-cyrusone-fra5-hanau-halls-2-3-current-build.json": (4_214, "576edad0e0eac03fbab0b4232c6cb513048c85efa5c314649916596a6bcf8806", 1_784_687_829_006_579_368),
    "curated-official-2026-07-22-cyrusone-wood-dale-phase-1-current-build.json": (6_934, "e4b3cf1d11434a434df7f412126c1f4d8f99182a8c5da0ecdedc21f47ff97b8e", 1_784_687_829_006_668_369),
    "curated-official-2026-07-22-beale-tulsa-project-clydesdale-initial-phase-current-build.json": (6_681, "ccacca1bb4bb90b522719682335982be6981f5027ae94a8d0d1fbac49efe9cb0", 1_784_687_829_006_762_370),
    "curated-official-2026-07-22-beale-pima-project-blue-bobcat-site-preparation.json": (11_276, "6da1eb317e956a19c37e2e23a6ae8c142223976a01c79752fa46336a40990b73", 1_784_687_829_006_860_162),
}
REJECTED_V1_INCIDENT = {
    "accepted_as_base": False,
    "artifact_id": REJECTED_V1_ID,
    "artifact_path": f"source_artifacts/{REJECTED_V1_ID}",
    "declared_recorded_at": REJECTED_V1_RECORDED_AT,
    "failed_members": {
        name: {"bytes": size, "ctime_ns": ctime_ns, "path": f"source_artifacts/{REJECTED_V1_ID}/{name}", "sha256": digest}
        for name, (size, digest, ctime_ns) in sorted(REJECTED_V1_MEMBER_PINS.items())
    },
    "logical_tree_sha256": REJECTED_V1_LOGICAL_TREE_SHA256,
    "physical_tree_sha256": REJECTED_V1_PHYSICAL_TREE_SHA256,
    "reason": merlin_v2.REJECTION_REASON,
    "root_ctime_ns": REJECTED_V1_ROOT_CTIME_NS,
    "status": "rejected_publication_incident",
}

OFFICIAL_SPECS.update({
    "merlin_cyrusone_beale_v2": {
        "module": merlin_v2, "recorded_at": "2026-07-22T02:43:48Z",
        "manifest_pin": (1_825, "d7798b75899f312f55e2785b13982abd14c051e71cc44850bca3d67a50b5faca"),
        "logical_tree": "ff458ecf4bfc7e9b15e705f207ed2fc09b6452730915b76ea02d210479a8491c",
        "physical_tree": "f4e7bf68bdeb86ba8e3aa5353809e567a423f01622232f02345b26608b5b41e1", "source_count": 6,
        "root_ctime_ns": 1_784_688_228_008_379_406,
        "member_pins": {
            "README.md": (1_748, "2a2ffc0d6601128e4b4856b866963d14b18e719d4468b13d03b5c95a46c57b61", 1_784_688_228_001_824_398),
            "candidate-assessment.json": (7_705, "d4e0aa1287870d860b810a239aa4d22f1a67d358046fc7bd6322955e70210ad3", 1_784_688_228_001_624_188),
            "manifest.json": (1_825, "d7798b75899f312f55e2785b13982abd14c051e71cc44850bca3d67a50b5faca", 1_784_688_228_002_022_941),
            "manifest.sha256": (80, "3a28d6c9053f30a53c8a9275080c510fbde247c74d5476b6a08c316b37a9010a", 1_784_688_228_001_422_811),
            "retrieval-inventory.json": (20_621, "602dfe467470c02535cdfe640dbffe4387694ce449a58f4b2f5f898200b72e05", 1_784_688_228_002_209_734),
            "rights-and-disposition.json": (809, "ae3fd2e900d5ffbf281e5a378348a2674cd1d2baa7164ef9b42dd7ca6216896c", 1_784_688_228_002_395_360),
            "source-snapshot.json": (11_557, "dc73f9d306811ff276d7463050b857e62206056d21682116354785ab78528926", 1_784_688_228_002_581_320),
        },
    },
    "bitdeer_v1": {
        "module": bitdeer, "recorded_at": "2026-07-22T02:51:30Z",
        "manifest_pin": (1_744, "22684cb9c52fbeff00878bf3122513970d368e2282e87efb4e5592e153dbff05"),
        "logical_tree": "db81f1bb58292739155b60845bbc0033f05e7b57f2b76402c25441ebf55505c2",
        "physical_tree": "c160460bd9caad23265d133e0919577509ce9996b7203cb5f9df465120724866", "source_count": 2,
        "root_ctime_ns": 1_784_688_690_004_281_395,
        "member_pins": {
            "README.md": (2_520, "649061ed26f592384b08f0a81026dfe256b5ba1e600a6e60fff8e00f452fcf51", 1_784_688_690_003_532_515),
            "candidate-assessment.json": (7_476, "05d18fe02b09a02049f8e38c0c8a71db15053482cd52d789a42f30e660007f8f", 1_784_688_690_003_489_348),
            "manifest.json": (1_744, "22684cb9c52fbeff00878bf3122513970d368e2282e87efb4e5592e153dbff05", 1_784_688_690_003_574_599),
            "manifest.sha256": (80, "c99c6139e48e6d09f5b8ed43b5a86178cdeac983ba74b3a00a24c1cc36c6582b", 1_784_688_690_003_435_931),
            "retrieval-inventory.json": (8_189, "17d66aeab2914eef9ce94c8e839a89447c1041ab294ef03b3eed82af2ac23092", 1_784_688_690_003_611_974),
            "rights-and-disposition.json": (950, "22a8af60078600d4ce3b65bd92235a5f1e9b4a5aae2d23035781afbb786d8a26", 1_784_688_690_003_648_266),
            "source-snapshot.json": (5_193, "69c864d1124479016a288a0abbfaf8297eb525b35deceb697f78408f42609b55", 1_784_688_690_003_680_766),
        },
    },
    "river_bend_v1": {
        "module": river, "recorded_at": "2026-07-22T03:02:49Z",
        "manifest_pin": (1_737, "5c6dc48fd5cd45d62faeff0dbd3aeddbeeda90a2049345704e0978e1a11b619e"),
        "logical_tree": "fee056a4f988d959cff445db8e2a9e8c7ce992f390eb1366b4b57b923796c3a4",
        "physical_tree": "d601d2ed1b3bc83ff917969d409d6e11c8a74f772c73c4cadc0c80157971c274", "source_count": 1,
        "root_ctime_ns": 1_784_689_369_005_244_129,
        "member_pins": {
            "README.md": (2_429, "25016c05692db9e6233afd2f8be2364acaf719036dcff5c3933e75931733f682", 1_784_689_369_004_043_246),
            "candidate-assessment.json": (2_131, "1a4f4f1685f1d5c714ee766f8dcb5b6339016291a35b5045189137a4fc96129a", 1_784_689_369_003_973_329),
            "manifest.json": (1_737, "5c6dc48fd5cd45d62faeff0dbd3aeddbeeda90a2049345704e0978e1a11b619e", 1_784_689_369_004_105_205),
            "manifest.sha256": (80, "cecfe18734c00fd276d98680a01813c7ba784d3597ad417d4a245087e4c3e1f0", 1_784_689_369_003_904_412),
            "retrieval-inventory.json": (7_910, "f7e2a001582660aa542add9d2328bda7eaa7b876b675f61c2bca4f483fb38ed3", 1_784_689_369_004_167_914),
            "rights-and-disposition.json": (955, "255aa3e1707e7c2519399978574c5f368eda63a3e1947f4d38822d019df195fd", 1_784_689_369_004_229_206),
            "source-snapshot.json": (4_298, "acd481d40a146eae72b142e2f4a97f96236ca3b560233521db6a96e80039dc62", 1_784_689_369_004_287_873),
        },
    },
    "goodman_lax01_v1": {
        "module": goodman, "recorded_at": "2026-07-22T03:11:04Z",
        "manifest_pin": (2_077, "debe416fb07e7d31e040cd533de6b1c5573b7541968048d9fb825c81b2f49578"),
        "logical_tree": "6ccacbc80509d348723d4f50eb9b03b4be7a294e721ee8e8d9521fcd108c5710",
        "physical_tree": "58d8d5cdc0c81ef188bd46794c11800783f6361a4c7440bd976f92de2bb10498", "source_count": 1,
        "root_ctime_ns": 1_784_689_864_157_130_471,
        "member_pins": {
            "README.md": (2_215, "0f6d9dc40a6ca7c58416a0b1315032a236e58fc93284411241170880b16baea0", 1_784_689_864_079_616_799),
            "candidate-assessment.json": (1_603, "fd147487322cc3e9a1012a2cfa7b53039c1fc48962a074746125b716e60a1c3a", 1_784_689_864_079_570_548),
            "manifest.json": (2_077, "debe416fb07e7d31e040cd533de6b1c5573b7541968048d9fb825c81b2f49578", 1_784_689_864_079_663_132),
            "manifest.sha256": (80, "b0dc548cf2fe3f7b8617f6004f32dc9e5d58c3719182a5b0bd48479f4dd43828", 1_784_689_864_079_523_173),
            "retrieval-inventory.json": (6_292, "ff7fe12f10c4c98c8f90ffff25fc7c8325cd9e3e4fcf4a6852671c9711eed201", 1_784_689_864_079_706_966),
            "rights-and-disposition.json": (1_009, "c11cd92064f582f280959874c05b99360094a4cf21ccdf752d14f89539e3ba74", 1_784_689_864_079_756_050),
            "source-snapshot.json": (4_478, "e1556208bb097e6deb1c4e483b12bf9fb5bd5276b4b845444fb09642880e53ff", 1_784_689_864_079_801_967),
        },
    },
})

# The governed v94 claim boundary replaces the copied v93 tranche constants.
ADDED_ENTITY_KEYS = frozenset({
    "curated:merlin-edged-bilbao-arasur-campus",
    "curated:merlin-edged-bilbao-arasur-campus:building-2-current-build",
    "curated:merlin-edged-bilbao-arasur-campus:building-3-current-build",
    "curated:cyrusone-fra5-hanau-campus",
    "curated:cyrusone-fra5-hanau-campus:halls-2-3-current-build",
    "curated:cyrusone-wood-dale-campus",
    "curated:cyrusone-wood-dale-campus:phase-1-current-build",
    "curated:beale-tulsa-county-project-clydesdale-campus",
    "curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build",
    "curated:beale-pima-county-project-blue-bobcat-campus",
    "curated:beale-pima-county-project-blue-bobcat-campus:current-site-preparation",
    "curated:bitdeer-wenatchee-washington-campus",
    "curated:bitdeer-wenatchee-washington-campus:2026-ai-conversion-site-preparation",
    "curated:bitdeer-massillon-ohio-campus",
    "curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction",
    "curated:hut8-river-bend-ai-data-center-campus",
    "curated:hut8-river-bend-ai-data-center-campus:245mw-critical-it-current-build",
})
ADDED_PROJECT_KEYS = frozenset(
    key for key in ADDED_ENTITY_KEYS if ":" in key.removeprefix("curated:")
)
GOODMAN_KEYS = frozenset({goodman.CAMPUS_KEY, goodman.PROJECT_KEY})
GOODMAN_ADDRESS = "3094 E Vernon Avenue, Vernon, California 90058, United States"
ADDED_EVIDENCE_KEYS = frozenset({
    "merlin-bilbao-arasur-campus-page-captured-2026-07-22",
    "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
    "cyrusone-fra5-hanau-progress-2025-08-26",
    "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
    "cyrusone-wood-dale-phase-1-progress-2025-08-12",
    "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
    "beale-tulsa-clydesdale-progress-2025-11-24",
    "beale-locations-tulsa-500mw-context-captured-2026-07-22",
    "beale-pima-project-bobcat-location-captured-2026-07-22",
    "pima-project-blue-progress-memo-2026-04-23",
    "pima-project-blue-site-work-inspection-2026-05-11",
    "pima-project-blue-pause-response-2026-05-22",
    "beale-locations-pima-600mw-context-captured-2026-07-22",
    "bitdeer-sec-wenatchee-ai-conversion-update-2026-07-21",
    "bitdeer-sec-massillon-fire-damaged-buildings-reconstruction-2026-07-21",
    "hut8-river-bend-lease-2025-12-17-captured-2026-07-22",
    "hut8-river-bend-q1-2026-10q-captured-2026-07-22",
    "hut8-river-bend-construction-update-2026-05-06-captured-2026-07-22",
    "databank-goodman-lax01-vernon-jv-2026-04-07-captured-2026-07-22",
    "goodman-lax01-vernon-brochure-captured-2026-07-22",
})
ADDED_EXPORTED_EVIDENCE_KEYS = frozenset({
    "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
    "cyrusone-fra5-hanau-progress-2025-08-26",
    "cyrusone-wood-dale-phase-1-topping-out-2025-05-13",
    "cyrusone-wood-dale-phase-1-progress-2025-08-12",
    "beale-tulsa-clydesdale-groundbreaking-2025-10-31",
    "beale-tulsa-clydesdale-progress-2025-11-24",
    "beale-pima-project-bobcat-location-captured-2026-07-22",
    "pima-project-blue-site-work-inspection-2026-05-11",
    "bitdeer-sec-wenatchee-ai-conversion-update-2026-07-21",
    "bitdeer-sec-massillon-fire-damaged-buildings-reconstruction-2026-07-21",
    "hut8-river-bend-lease-2025-12-17-captured-2026-07-22",
    "hut8-river-bend-construction-update-2026-05-06-captured-2026-07-22",
    "databank-goodman-lax01-vernon-jv-2026-04-07-captured-2026-07-22",
    "goodman-lax01-vernon-brochure-captured-2026-07-22",
})
ADDED_SIGNAL_EVIDENCE_KEYS = frozenset({
    "merlin-bilbao-arasur-b2-b3-progress-2026-04-10",
    "cyrusone-fra5-hanau-progress-2025-08-26",
    "cyrusone-wood-dale-phase-1-progress-2025-08-12",
    "beale-tulsa-clydesdale-progress-2025-11-24",
    "pima-project-blue-site-work-inspection-2026-05-11",
    "bitdeer-sec-wenatchee-ai-conversion-update-2026-07-21",
    "bitdeer-sec-massillon-fire-damaged-buildings-reconstruction-2026-07-21",
    "hut8-river-bend-construction-update-2026-05-06-captured-2026-07-22",
})
LIFECYCLE_CONTRACT = frozenset({
    ("curated:merlin-edged-bilbao-arasur-campus:building-2-current-build", "under_construction", "2026-04-10", "authoritative_physical_status_update"),
    ("curated:merlin-edged-bilbao-arasur-campus:building-3-current-build", "under_construction", "2026-04-10", "authoritative_physical_status_update"),
    ("curated:cyrusone-fra5-hanau-campus:halls-2-3-current-build", "under_construction", "2025-08-26", "authoritative_physical_status_update"),
    ("curated:cyrusone-wood-dale-campus:phase-1-current-build", "shell", "2025-05-13", "authoritative_physical_status_update"),
    ("curated:cyrusone-wood-dale-campus:phase-1-current-build", "under_construction", "2025-08-12", "authoritative_physical_status_update"),
    ("curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build", "under_construction", "2025-10-31", "authoritative_construction_start"),
    ("curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build", "under_construction", "2025-11-24", "authoritative_physical_status_update"),
    ("curated:beale-pima-county-project-blue-bobcat-campus:current-site-preparation", "site_preparation", "2026-05-11", "authoritative_physical_status_update"),
    ("curated:bitdeer-wenatchee-washington-campus:2026-ai-conversion-site-preparation", "site_preparation", "2026-07-21", "authoritative_physical_status_update"),
    ("curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction", "under_construction", "2026-07-21", "authoritative_physical_status_update"),
    ("curated:hut8-river-bend-ai-data-center-campus:245mw-critical-it-current-build", "under_construction", "2026-05-06", "authoritative_physical_status_update"),
})
CAPACITY_CONTRACT = frozenset({
    ("curated:cyrusone-fra5-hanau-campus", "critical_it_mw", "planned", "MW", 54.0, "2025-08-26", "reported"),
    ("curated:cyrusone-wood-dale-campus:phase-1-current-build", "critical_it_mw", "planned", "MW", 18.0, "2025-05-13", "reported"),
    ("curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction", "gross_facility_mw", "planned", "MW", 26.0, "2026-07-21", "reported"),
    ("curated:hut8-river-bend-ai-data-center-campus:245mw-critical-it-current-build", "critical_it_mw", "contracted", "MW", 245.0, "2025-12-17", "reported"),
    ("curated:hut8-river-bend-ai-data-center-campus", "grid_connection_mw", "contracted", "MW", 330.0, "2025-12-17", "reported"),
    ("curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development", "critical_it_mw", "planned", "MW", 32.0, "2026-03-17", "reported"),
})
FRESHNESS_README = """
Open seed v94 is the exact governed accepted-v93 successor. It appends exactly
ten ordered curated records at input indices 488 through 497: six corrected
MERLIN/CyrusOne/Beale v2 records, two Bitdeer records, one Hut 8 River Bend
record, and one Goodman/DataBank LAX01 enrichment record. The rejected Merlin
v1 artifact is immutable incident evidence only and is never integrated.

The release creates 17 entities and updates only the two pre-existing Goodman
rows. Every other v93 public row is byte-identical. No appended entity has
coordinates or geometry, and the Goodman enrichment adds an exact address but
no coordinates or geometry. All 553 v93 lifecycle-freshness rows remain frozen;
nine new project rows are last-observed/current-unknown.

The database adds 20 evidence records, 11 lifecycle observations, six typed
capacity estimates, one River Bend hyperscale-lease observation, and one River
Bend AI-specialized-unspecified workload. Public projection adds 14 referenced
evidence rows, nine freshness rows, six capacities, nine net pipeline rows, and
eight source signals.

No Beale 500/600 MW context, Bitdeer 13/21/47/174 MW context, River Bend future
1,000 MW or current-load context, or Goodman 49.5 MW/PUE 1.5/6 MW/26 MW context
is normalized. No inferred energy, PUE, WUE, coordinate, geometry, cross-source
identity, or unique-site claim is added.
""".strip()


class OpenSeedV94Error(RuntimeError):
    """Raised when a v94 lineage, claim, or publication guard fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _read_json(
    path: Path, *, mode: int | None = None, sort_keys: bool = False
) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise OpenSeedV94Error(f"expected ordinary JSON file: {path}")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise OpenSeedV94Error(f"file mode differs: {path}")
    raw = path.read_bytes()
    document = json.loads(raw)
    if raw != _canonical(document, sort_keys=sort_keys):
        raise OpenSeedV94Error(f"JSON is not canonical: {path}")
    return raw, document


def _validate_pinned_tree(
    root: Path,
    *,
    member_pins: Mapping[str, tuple[int, str, int]],
    root_ctime_ns: int,
    recorded_at: str,
    label: str,
    accepted_chronology: bool = True,
) -> None:
    if (
        root.is_symlink()
        or not root.is_dir()
        or stat.S_IMODE(root.stat().st_mode) != 0o555
        or root.stat().st_ctime_ns != root_ctime_ns
    ):
        raise OpenSeedV94Error(f"{label} root chronology or mode differs")
    members = {path.name: path for path in root.iterdir()}
    if set(members) != set(member_pins):
        raise OpenSeedV94Error(f"{label} closed member inventory differs")
    target = v70.parse_utc(recorded_at, label=f"{label} recorded_at").timestamp()
    for name, (size, digest, ctime_ns) in member_pins.items():
        path = members[name]
        metadata = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(metadata.st_mode) != 0o444
            or (metadata.st_size, _sha256(path.read_bytes()), metadata.st_ctime_ns)
            != (size, digest, ctime_ns)
            or max(metadata.st_birthtime, metadata.st_mtime) > target + 1e-6
            or (accepted_chronology and metadata.st_ctime + 1e-6 < target)
            or (not accepted_chronology and metadata.st_ctime >= target)
        ):
            raise OpenSeedV94Error(f"{label} member pin or chronology differs: {name}")


def _validate_rejected_v1_incident() -> None:
    root = ROOT / "source_artifacts" / REJECTED_V1_ID
    _validate_pinned_tree(
        root,
        member_pins=REJECTED_V1_MEMBER_PINS,
        root_ctime_ns=REJECTED_V1_ROOT_CTIME_NS,
        recorded_at=REJECTED_V1_RECORDED_AT,
        label="rejected Merlin v1 incident",
    )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (
        v69.tree_digest(root) != REJECTED_V1_PHYSICAL_TREE_SHA256
        or manifest.get("artifact_id") != REJECTED_V1_ID
        or manifest.get("recorded_at") != REJECTED_V1_RECORDED_AT
        or manifest.get("tree_sha256") != REJECTED_V1_LOGICAL_TREE_SHA256
        or merlin_v2.V1_ARTIFACT_ID != REJECTED_V1_ID
        or merlin_v2.V1_RECORDED_AT != REJECTED_V1_RECORDED_AT
        or merlin_v2.V1_LOGICAL_TREE_SHA256 != REJECTED_V1_LOGICAL_TREE_SHA256
        or merlin_v2.V1_PHYSICAL_TREE_SHA256 != REJECTED_V1_PHYSICAL_TREE_SHA256
        or merlin_v2.V1_ROOT_CTIME_NS != REJECTED_V1_ROOT_CTIME_NS
        or dict(merlin_v2.V1_ARTIFACT_MEMBER_PINS) != REJECTED_V1_MEMBER_PINS
        or dict(merlin_v2.V1_SOURCE_PINS) != REJECTED_V1_SOURCE_PINS
    ):
        raise OpenSeedV94Error("rejected Merlin v1 incident lineage differs")
    for name, (size, digest, ctime_ns) in REJECTED_V1_SOURCE_PINS.items():
        path = ROOT / "sources" / name
        metadata = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(metadata.st_mode) != 0o444
            or (metadata.st_size, _sha256(path.read_bytes()), metadata.st_ctime_ns)
            != (size, digest, ctime_ns)
        ):
            raise OpenSeedV94Error(f"rejected Merlin v1 source pin differs: {name}")


def _validate_official_artifact() -> dict[str, dict[str, Any]]:
    records_by_path: dict[str, dict[str, Any]] = {}
    source_recorded_at: dict[str, str] = {}
    _validate_rejected_v1_incident()
    for label, spec in OFFICIAL_SPECS.items():
        module = spec["module"]
        artifact = ROOT / "source_artifacts" / module.ARTIFACT_ID
        try:
            manifest = module.validate_artifact(artifact)
        except RuntimeError as error:
            raise OpenSeedV94Error(
                f"{label} official artifact invalid: {error}"
            ) from error
        _validate_pinned_tree(
            artifact,
            member_pins=spec["member_pins"],
            root_ctime_ns=spec["root_ctime_ns"],
            recorded_at=spec["recorded_at"],
            label=label,
        )
        manifest_raw = (artifact / "manifest.json").read_bytes()
        if (
            (len(manifest_raw), _sha256(manifest_raw)) != spec["manifest_pin"]
            or manifest.get("recorded_at") != spec["recorded_at"]
            or manifest.get("tree_sha256") != spec["logical_tree"]
            or v69.tree_digest(artifact) != spec["physical_tree"]
            or manifest.get("curated_source_records") != spec["source_count"]
            or manifest.get("open_seed_successor_created") is not False
            or manifest.get("release_integration") != "none"
            or manifest.get("regional_completeness_claimed") is not False
        ):
            raise OpenSeedV94Error(f"{label} official artifact pin differs")
        if label == "merlin_cyrusone_beale_v2" and (
            manifest.get("rejected_v1_artifact_id") != REJECTED_V1_ID
            or manifest.get("rejected_v1_integrated") is not False
        ):
            raise OpenSeedV94Error("corrected Merlin v2 rejected-v1 lineage differs")
        snapshot = json.loads(
            (artifact / "source-snapshot.json").read_text(encoding="utf-8")
        )
        for record in snapshot.get("source_records", []):
            path = record.get("path")
            if not isinstance(path, str) or path in records_by_path:
                raise OpenSeedV94Error("official artifact source inventory overlaps")
            records_by_path[path] = record
            source_recorded_at[path] = spec["recorded_at"]

    if tuple(records_by_path) != ADDITION_ORDER:
        raise OpenSeedV94Error("official artifact source order differs")
    documents: dict[str, dict[str, Any]] = {}
    for relative in ADDITION_ORDER:
        path = ROOT / relative
        raw, document = _read_json(path, mode=0o444)
        record = records_by_path[relative]
        pin = ADDITION_PINS[relative]
        metadata = path.stat(follow_symlinks=False)
        expected_ctime_ns = SOURCE_CTIME_NS[relative]
        if (
            (len(raw), _sha256(raw)) != pin
            or (record.get("bytes"), record.get("sha256")) != pin
            or metadata.st_ctime_ns != expected_ctime_ns
            or max(metadata.st_birthtime, metadata.st_mtime)
            > v70.parse_utc(
                source_recorded_at[relative],
                label=f"{relative} artifact recorded_at",
            ).timestamp()
            + 1e-6
        ):
            raise OpenSeedV94Error(f"v94 source pin differs: {relative}")
        documents[relative] = document

    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    lifecycle = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["lifecycle"]
    }
    capacities = {
        (
            document[row["entity"]]["stable_key"],
            row["metric"],
            row["stage"],
            row["unit"],
            float(row["base"]),
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["capacities"]
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    if (
        stable_keys != ADDED_ENTITY_KEYS | GOODMAN_KEYS
        or lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or evidence_keys != ADDED_EVIDENCE_KEYS
        or any(
            document[entity][field] is not None
            for document in documents.values()
            for entity in ("campus", "project")
            for field in ("coordinates", "geometry")
        )
    ):
        raise OpenSeedV94Error(
            "official current-build normalized claim contract differs"
        )
    if any(
        row["metric"] in {"annual_energy_mwh", "pue", "wue"}
        for document in documents.values()
        for row in document["capacities"]
    ):
        raise OpenSeedV94Error("v94 source adds energy or efficiency capacity")
    operating_models = {
        (document[row["entity"]]["stable_key"], row["value"])
        for document in documents.values()
        for row in document["operating_models"]
    }
    workloads = {
        (document[row["entity"]]["stable_key"], row["value"])
        for document in documents.values()
        for row in document["workloads"]
    }
    goodman_document = documents[f"sources/{goodman.SOURCE_FILENAME}"]
    if (
        operating_models
        != {(river.PROJECT_KEY, "hyperscale_lease")}
        or workloads
        != {(river.PROJECT_KEY, "ai_specialized_unspecified")}
        or goodman_document["campus"]["roles"]
        != {"owner": ["Goodman DataBank JV"]}
        or goodman_document["project"]["roles"] != {}
        or any(
            goodman_document[entity]["address"] != GOODMAN_ADDRESS
            or goodman_document[entity]["as_of_date"] != "2026-04-07"
            for entity in ("campus", "project")
        )
    ):
        raise OpenSeedV94Error("v94 model, workload, or Goodman contract differs")
    return documents


def _base_paths(base: Mapping[str, Any]) -> list[Path]:
    paths = []
    for row in base["curated_inputs"]:
        path = ROOT / row["path"]
        if path.is_symlink() or not path.is_file() or v69.sha256(path) != row["sha256"]:
            raise OpenSeedV94Error(f"accepted v93 input pin differs: {row['path']}")
        paths.append(path)
    return paths


def selected_inputs(
    base: Mapping[str, Any],
    *,
    recorded_at: str,
    validation_wall_clock: datetime | None = None,
) -> tuple[list[dict[str, str]], list[Path]]:
    if base.get("release_id") != v93.RELEASE_ID:
        raise OpenSeedV94Error("v94 base must be exactly accepted v93")
    rows = base.get("curated_inputs")
    if (
        not isinstance(rows, list)
        or len(rows) != 488
        or any(
            not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in rows
        )
    ):
        raise OpenSeedV94Error("accepted v93 curated inventory differs")
    documents = _validate_official_artifact()
    target = v70.parse_utc(recorded_at, label="v94 recorded_at")
    wall = validation_wall_clock or datetime.now(UTC)
    if (
        wall.tzinfo is None
        or target > wall.astimezone(UTC)
        or any(
            v70.parse_utc(spec["recorded_at"], label=f"{label} recorded_at") > target
            for label, spec in OFFICIAL_SPECS.items()
        )
    ):
        raise OpenSeedV94Error("v94 publication time precedes an input")

    paths = _base_paths(base)
    base_evidence: set[str] = set()
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        base_evidence.update(
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        )
    if base_evidence & ADDED_EVIDENCE_KEYS:
        raise OpenSeedV94Error("v94 evidence append collides with accepted v93")
    base_stable = {
        row["stable_key"] for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    if base_stable & (ADDED_ENTITY_KEYS | GOODMAN_KEYS) != GOODMAN_KEYS:
        raise OpenSeedV94Error("v94 stable-key replacement boundary differs")

    selected = [dict(row) for row in rows]
    for relative in ADDITION_ORDER:
        selected.append({"path": relative, "sha256": ADDITION_PINS[relative][1]})
        paths.append(ROOT / relative)
    if (
        selected[:488] != rows
        or [row["path"] for row in selected[488:]] != list(ADDITION_ORDER)
        or tuple(documents) != ADDITION_ORDER
        or len(selected) != 498
        or len({row["path"] for row in selected}) != 498
    ):
        raise OpenSeedV94Error("v94 did not append exactly ten ordered inputs")
    for relative, document in documents.items():
        for index, evidence in enumerate(document["evidence"]):
            retrieved = v70.parse_utc(
                evidence["retrieved_at"],
                label=f"{relative} evidence[{index}].retrieved_at",
            )
            if retrieved > target or retrieved > wall.astimezone(UTC):
                raise OpenSeedV94Error("v94 selected evidence is future-dated")
    return selected, paths


def _guard_state() -> dict[str, Any]:
    _validate_official_artifact()
    return {
        "base_definition": (
            BASE_DEFINITION.stat().st_size,
            v69.sha256(BASE_DEFINITION),
        ),
        "base_manifest": (
            (BASE_RELEASE / "manifest.json").stat().st_size,
            v69.sha256(BASE_RELEASE / "manifest.json"),
        ),
        "base_tree": v69.tree_digest(BASE_RELEASE),
        "base_entities": (
            (BASE_RELEASE / "entities.csv").stat().st_size,
            v69.sha256(BASE_RELEASE / "entities.csv"),
        ),
        "base_source_inputs": (
            (BASE_RELEASE / "source_inputs.json").stat().st_size,
            v69.sha256(BASE_RELEASE / "source_inputs.json"),
        ),
        "official_manifests": {
            label: (
                (
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                )
                .stat()
                .st_size,
                v69.sha256(
                    ROOT
                    / "source_artifacts"
                    / spec["module"].ARTIFACT_ID
                    / "manifest.json"
                ),
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
        "official_trees": {
            label: v69.tree_digest(
                ROOT / "source_artifacts" / spec["module"].ARTIFACT_ID
            )
            for label, spec in OFFICIAL_SPECS.items()
        },
        "additions": {
            relative: ((ROOT / relative).stat().st_size, v69.sha256(ROOT / relative))
            for relative in ADDITION_ORDER
        },
    }


def _table_state(connection: sqlite3.Connection, table: str) -> set[tuple[Any, ...]]:
    return {tuple(row) for row in connection.execute(f"SELECT * FROM {table}")}


def _validate_database_contract(
    connection: sqlite3.Connection,
    base: Mapping[str, Any],
    *,
    recorded_at: str,
) -> None:
    expected_counts = {
        "entities": 1_011,
        "entity_snapshots": 1_036,
        "evidence": 845,
        "lifecycle_observations": 585,
        "capacity_estimates": 565,
        "operating_model_observations": 74,
        "workload_observations": 136,
    }
    actual_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in expected_counts
    }
    if actual_counts != expected_counts:
        raise OpenSeedV94Error(f"v94 database counts differ: {actual_counts}")
    with tempfile.TemporaryDirectory(
        prefix="open-seed-v94-base-", dir="/private/tmp"
    ) as temporary:
        prior = v69._populate_database(
            base,
            _base_paths(base),
            Path(temporary) / "v93.sqlite",
            recorded_at=recorded_at,
        )
        try:
            for table in (
                "entities",
                "evidence",
                "campuses",
                "facilities",
                "buildings",
                "projects",
                "administrative_assignments",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            ):
                if not _table_state(prior, table) <= _table_state(connection, table):
                    raise OpenSeedV94Error(f"v94 changed a v93 database row: {table}")
            before_entities = {
                row[0] for row in prior.execute("SELECT stable_key FROM entities")
            }
            after_entities = {
                row[0] for row in connection.execute("SELECT stable_key FROM entities")
            }
            if (
                after_entities - before_entities != ADDED_ENTITY_KEYS
                or before_entities - after_entities
            ):
                raise OpenSeedV94Error("v94 database identity delta differs")
            before_evidence = set(v70._evidence_by_key(prior))
            after_evidence = set(v70._evidence_by_key(connection))
            if (
                after_evidence - before_evidence != ADDED_EVIDENCE_KEYS
                or before_evidence - after_evidence
            ):
                raise OpenSeedV94Error("v94 database evidence delta differs")
        finally:
            prior.close()

    relevant_project_keys = ADDED_PROJECT_KEYS | {goodman.PROJECT_KEY}
    project_targets = {
        row["project_key"]: row["campus_key"]
        for row in connection.execute(
            """
            SELECT project.stable_key AS project_key,
                   target.stable_key AS campus_key
            FROM projects
            JOIN entities project ON project.id=projects.entity_id
            JOIN entities target ON target.id=projects.target_entity_id
            """
        )
        if row["project_key"] in relevant_project_keys
    }
    expected_targets = {
        document["project"]["stable_key"]: document["campus"]["stable_key"]
        for document in _validate_official_artifact().values()
    }
    if project_targets != expected_targets:
        raise OpenSeedV94Error("v94 project/campus boundaries differ")

    project_keys = tuple(sorted(relevant_project_keys))
    project_placeholders = ",".join("?" for _ in project_keys)
    lifecycle_keys = tuple(sorted(ADDED_PROJECT_KEYS))
    lifecycle_placeholders = ",".join("?" for _ in lifecycle_keys)
    lifecycle = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, status, as_of_date,
                   lifecycle_observations.method
            FROM lifecycle_observations
            JOIN entities ON entities.id=entity_id
            WHERE entities.stable_key IN ({lifecycle_placeholders})
            """,
            lifecycle_keys,
        )
    }
    relevant_entity_keys = ADDED_ENTITY_KEYS | GOODMAN_KEYS
    capacity_keys = tuple(sorted(relevant_entity_keys))
    capacity_placeholders = ",".join("?" for _ in capacity_keys)
    evidence_keys = tuple(sorted(ADDED_EVIDENCE_KEYS))
    evidence_placeholders = ",".join("?" for _ in evidence_keys)
    capacities = {
        tuple(row)
        for row in connection.execute(
            f"""
            SELECT entities.stable_key, metric, stage, unit, base, as_of_date,
                   capacity_estimates.method
            FROM capacity_estimates
            JOIN entities ON entities.id=entity_id
            JOIN evidence ON evidence.id=capacity_estimates.evidence_id
            WHERE entities.stable_key IN ({capacity_placeholders})
              AND json_extract(evidence.metadata_json,
                  '$.curated_record_key') IN ({evidence_placeholders})
            """,
            (*capacity_keys, *evidence_keys),
        )
    }
    models = {
        tuple(row)
        for row in connection.execute(
        f"""
        SELECT entities.stable_key, operating_model
        FROM operating_model_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
        )
    }
    workloads = {
        tuple(row)
        for row in connection.execute(
        f"""
        SELECT entities.stable_key, workload
        FROM workload_observations
        JOIN entities ON entities.id=entity_id
        WHERE entities.stable_key IN ({project_placeholders})
        """,
        project_keys,
        )
    }
    stable_by_id = {
        row["id"]: row["stable_key"]
        for row in connection.execute("SELECT id, stable_key FROM entities")
    }
    current_snapshots = {
        stable_by_id[row["entity_id"]]: row
        for row in _current_rows(
            connection, "entity_snapshots", as_of=AS_OF, recorded_at=recorded_at
        )
        if stable_by_id[row["entity_id"]] in relevant_entity_keys
    }
    if (
        lifecycle != LIFECYCLE_CONTRACT
        or capacities != CAPACITY_CONTRACT
        or models != {(river.PROJECT_KEY, "hyperscale_lease")}
        or workloads != {(river.PROJECT_KEY, "ai_specialized_unspecified")}
        or set(current_snapshots) != relevant_entity_keys
        or any(
            row["latitude"] is not None
            or row["longitude"] is not None
            or row["geometry_json"] not in {None, "null"}
            for row in current_snapshots.values()
        )
    ):
        raise OpenSeedV94Error("v94 imported claim contract differs")

    evidence_rows = {
        json.loads(row["metadata_json"] or "{}").get("curated_record_key"): row
        for row in connection.execute(
            "SELECT kind, source_family, metadata_json FROM evidence"
        )
        if json.loads(row["metadata_json"] or "{}").get("curated_record_key")
        in ADDED_EVIDENCE_KEYS
    }
    if set(evidence_rows) != ADDED_EVIDENCE_KEYS or not {
        row["kind"] for row in evidence_rows.values()
    } <= {"company_disclosure", "government_record", "utility_record"}:
        raise OpenSeedV94Error("v94 imported evidence classification differs")

    current = _current_rows(
        connection, "entity_snapshots", as_of=AS_OF, recorded_at=recorded_at
    )
    kinds = {
        row["id"]: row["kind"]
        for row in connection.execute("SELECT id, kind FROM entities")
    }
    located = [
        row
        for row in current
        if row["latitude"] is not None and row["longitude"] is not None
    ]
    if (
        len(located) != 213
        or sum(kinds[row["entity_id"]] == "campus" for row in located) != 141
    ):
        raise OpenSeedV94Error("v94 internal as-of coordinate coverage differs")


def _build_database(
    base: Mapping[str, Any],
    paths: list[Path],
    sqlite_path: Path,
    *,
    recorded_at: str,
) -> sqlite3.Connection:
    connection = v69._populate_database(
        base, paths, sqlite_path, recorded_at=recorded_at
    )
    try:
        _validate_database_contract(connection, base, recorded_at=recorded_at)
        return connection
    except Exception:
        connection.close()
        raise


def _csv_text(template: str, rows: list[dict[str, str]]) -> str:
    reader = csv.DictReader(io.StringIO(template))
    fields = reader.fieldnames
    if fields is None:
        raise OpenSeedV94Error("CSV template lacks a header")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _successor_csv(
    output: dict[str, str],
    filename: str,
    *,
    key: str,
    expected_base: int,
    expected_added: int,
    replacements: frozenset[str] = frozenset(),
    allow_base_recomputation: bool = False,
) -> None:
    base_rows = _csv_rows(BASE_RELEASE / filename)
    current_rows = list(csv.DictReader(io.StringIO(output[filename])))
    if len(base_rows) != expected_base:
        raise OpenSeedV94Error(f"v93 {filename} baseline count differs")
    base_by_key = {row[key]: row for row in base_rows}
    current_by_key = {row[key]: row for row in current_rows}
    if (
        len(base_by_key) != len(base_rows)
        or len(current_by_key) != len(current_rows)
        or not set(base_by_key) <= set(current_by_key)
    ):
        raise OpenSeedV94Error(f"v94 {filename} baseline identity differs")
    changed = {
        row_key
        for row_key, base_row in base_by_key.items()
        if current_by_key[row_key] != base_row
    }
    if not allow_base_recomputation and changed != replacements:
        raise OpenSeedV94Error(f"v94 {filename} replacement boundary differs")
    added = [row for row in current_rows if row[key] not in base_by_key]
    if len(added) != expected_added or len({row[key] for row in added}) != len(added):
        raise OpenSeedV94Error(f"v94 {filename} append count differs")
    carried = [
        current_by_key[row[key]] if row[key] in replacements else row
        for row in base_rows
    ]
    output[filename] = _csv_text(output[filename], [*carried, *added])


def _append_only_projection(output: dict[str, str]) -> None:
    _successor_csv(
        output,
        "entities.csv",
        key="stable_key",
        expected_base=994,
        expected_added=17,
        replacements=GOODMAN_KEYS,
    )
    _successor_csv(
        output,
        "evidence.csv",
        key="evidence_id",
        expected_base=651,
        expected_added=14,
    )
    _successor_csv(
        output,
        "construction_pipeline.csv",
        key="stable_key",
        expected_base=504,
        expected_added=9,
        replacements=frozenset({goodman.PROJECT_KEY}),
    )
    _successor_csv(
        output,
        "construction_source_signals.csv",
        key="source_observation_evidence_id",
        expected_base=403,
        expected_added=8,
    )
    _successor_csv(
        output,
        "lifecycle_freshness.csv",
        key="stable_key",
        expected_base=553,
        expected_added=9,
        allow_base_recomputation=True,
    )

    entity_rows = list(csv.DictReader(io.StringIO(output["entities.csv"])))
    relevant_entity_ids = {
        row["entity_id"]
        for row in entity_rows
        if row["stable_key"] in ADDED_ENTITY_KEYS | GOODMAN_KEYS
    }
    base_capacity = _csv_rows(BASE_RELEASE / "capacity_estimates.csv")
    raw_capacity = list(csv.DictReader(io.StringIO(output["capacity_estimates.csv"])))
    base_capacity_canonical = {
        json.dumps(row, sort_keys=True, separators=(",", ":"))
        for row in base_capacity
    }
    added_capacity = [
        row
        for row in raw_capacity
        if row["entity_id"] in relevant_entity_ids
        and json.dumps(row, sort_keys=True, separators=(",", ":"))
        not in base_capacity_canonical
    ]
    if len(base_capacity) != 558 or len(added_capacity) != 6:
        raise OpenSeedV94Error("v94 capacity append count differs")
    output["capacity_estimates.csv"] = _csv_text(
        output["capacity_estimates.csv"], [*base_capacity, *added_capacity]
    )

    base_geojson = json.loads((BASE_RELEASE / "atlas.geojson").read_text())
    current_geojson = json.loads(output["atlas.geojson"])
    base_by_key = {
        feature["properties"]["stable_key"]: feature
        for feature in base_geojson["features"]
    }
    current_by_key = {
        feature["properties"]["stable_key"]: feature
        for feature in current_geojson["features"]
    }
    changed_features = {
        key
        for key, feature in base_by_key.items()
        if current_by_key.get(key) != feature
    }
    new_features = [
        feature for key, feature in current_by_key.items() if key not in base_by_key
    ]
    if (
        len(base_geojson["features"]) != 994
        or len(current_geojson["features"]) != 1_011
        or changed_features != GOODMAN_KEYS
        or len(new_features) != 17
        or {feature["properties"]["stable_key"] for feature in new_features}
        != ADDED_ENTITY_KEYS
        or any(
            feature.get("geometry") is not None
            or feature["properties"].get("latitude") is not None
            or feature["properties"].get("longitude") is not None
            for feature in new_features
        )
    ):
        raise OpenSeedV94Error("v94 GeoJSON append boundary differs")
    current_geojson["features"] = [
        current_by_key[key] if key in GOODMAN_KEYS else feature
        for key, feature in base_by_key.items()
    ] + new_features
    output["atlas.geojson"] = (
        json.dumps(current_geojson, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    base_sources = json.loads(
        (BASE_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
    )["sources"]
    current_sources = json.loads(output["source_inputs.json"])["sources"]
    base_canonical = {
        json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for row in base_sources
    }
    added_sources = [
        row
        for row in current_sources
        if json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        not in base_canonical
    ]
    if len(base_sources) != 578 or len(added_sources) != 14:
        raise OpenSeedV94Error("v94 source-input projection differs")
    output["source_inputs.json"] = (
        json.dumps(
            {"sources": [*base_sources, *added_sources]},
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )

    summary = json.loads(output["summary.json"])
    summary["entities_with_coordinates"] = 213
    summary["campuses_with_coordinates"] = 141
    summary["append_projection"] = {
        "base_release_id": v93.RELEASE_ID,
        "base_rows_frozen": False,
        "unaffected_base_rows_frozen": True,
        "governed_base_row_replacements": {
            "entities": sorted(GOODMAN_KEYS),
            "construction_pipeline": [goodman.PROJECT_KEY],
            "atlas_geojson": sorted(GOODMAN_KEYS),
        },
        "curated_source_input_delta": 10,
        "internal_database_delta": {
            "entities": 17,
            "entity_snapshots": 19,
            "evidence": 20,
            "lifecycle_observations": 11,
            "capacity_estimates": 6,
            "operating_model_observations": 1,
            "workload_observations": 1,
        },
        "public_release_delta": {
            "entities": 17,
            "evidence": 14,
            "lifecycle_freshness": 9,
            "capacity_estimates": 6,
            "construction_pipeline": 9,
            "construction_source_signals": 8,
        },
        "projection_explanation": "Public claim evidence includes the 14 new evidence records referenced by exported current identity, lifecycle, capacity, operating-model, and workload fields; all 20 new evidence records remain in the internal database.",
        "public_source_input_rows_delta": 14,
        "unrelated_future_effective_base_coordinates_published": False,
    }
    output["summary.json"] = _canonical(summary, sort_keys=True).decode()


def _augment_release(documents: Mapping[str, str]) -> dict[str, str]:
    previous_as_of = v85.AS_OF
    try:
        v85.AS_OF = AS_OF
        output = v93.v92.v91._augment_release(documents)
    finally:
        v85.AS_OF = previous_as_of
    _append_only_projection(output)
    output["README.md"] = (
        output["README.md"].rstrip() + "\n\n" + FRESHNESS_README + "\n"
    )
    manifest = json.loads(output["manifest.json"])
    manifest.update(
        {
            "as_of": AS_OF,
            "entities": 1_011,
            "entities_by_kind": {"campus": 524, "project": 487},
            "capacity_estimates": 564,
            "construction_pipeline_records": 513,
            "construction_source_signals": 411,
            "evidence_records": 665,
            "lifecycle_freshness_records": 562,
            "append_only_base_release": v93.RELEASE_ID,
            "base_rows_frozen": False,
            "unaffected_base_rows_frozen": True,
            "governed_base_row_replacements": {
                "entities": sorted(GOODMAN_KEYS),
                "construction_pipeline": [goodman.PROJECT_KEY],
                "atlas_geojson": sorted(GOODMAN_KEYS),
            },
            "curated_source_input_delta": 10,
            "internal_database_delta": {
                "entities": 17,
                "entity_snapshots": 19,
                "evidence": 20,
                "lifecycle_observations": 11,
                "capacity_estimates": 6,
                "operating_model_observations": 1,
                "workload_observations": 1,
            },
            "public_release_delta": {
                "entities": 17,
                "evidence": 14,
                "lifecycle_freshness": 9,
                "capacity_estimates": 6,
                "construction_pipeline": 9,
                "construction_source_signals": 8,
            },
            "public_source_input_rows_delta": 14,
        }
    )
    for filename, text in output.items():
        if filename == "manifest.json":
            continue
        manifest["files"][filename] = {
            "bytes": len(text.encode()),
            "sha256": _sha256(text.encode()),
        }
    output["manifest.json"] = _canonical(manifest, sort_keys=True).decode()
    return output


def _write_release(
    connection: sqlite3.Connection,
    output: Path,
    *,
    recorded_at: str,
    precreated: bool = False,
) -> None:
    if precreated:
        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
            raise OpenSeedV94Error("precreated v94 release stage must be empty")
    else:
        output.mkdir(parents=True, exist_ok=False)
    documents = build_release_documents(
        connection,
        as_of=AS_OF,
        recorded_at=recorded_at,
        publication_contract_version=4,
    )
    for filename, text in _augment_release(documents).items():
        path = output / filename
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode())
            stream.flush()
            os.fsync(stream.fileno())


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _entity_csv_record(path: Path, stable_key: str) -> bytes:
    marker = f",{stable_key},".encode()
    matches = [
        line for line in path.read_bytes().splitlines(keepends=True) if marker in line
    ]
    if len(matches) != 1:
        raise OpenSeedV94Error(f"entity CSV record lookup differs: {stable_key}")
    return matches[0]


PUBLIC_CSV_DELTA = {
    "entities.csv": (994, 17, 2),
    "evidence.csv": (651, 14, 0),
    "capacity_estimates.csv": (558, 6, 0),
    "construction_pipeline.csv": (504, 9, 1),
    "construction_source_signals.csv": (403, 8, 0),
    "lifecycle_freshness.csv": (553, 9, 0),
}


def _validate_public_delta(stage: Path) -> None:
    for filename, (base_count, added_count, replacement_count) in PUBLIC_CSV_DELTA.items():
        base_lines = Counter(
            (BASE_RELEASE / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        stage_lines = Counter(
            (stage / filename).read_bytes().splitlines(keepends=True)[1:]
        )
        if (
            sum(base_lines.values()) != base_count
            or sum((stage_lines - base_lines).values())
            != added_count + replacement_count
            or sum((base_lines - stage_lines).values()) != replacement_count
        ):
            raise OpenSeedV94Error(f"v94 governed CSV delta differs: {filename}")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (stage / filename).read_bytes() != (BASE_RELEASE / filename).read_bytes():
            raise OpenSeedV94Error(
                f"v94 unrelated resolution output changed: {filename}"
            )

    base_features = json.loads((BASE_RELEASE / "atlas.geojson").read_text())["features"]
    current_features = json.loads((stage / "atlas.geojson").read_text())["features"]
    base_by_key = {row["properties"]["stable_key"]: row for row in base_features}
    current_by_key = {
        row["properties"]["stable_key"]: row for row in current_features
    }
    if (
        len(base_features) != 994
        or len(current_features) != 1_011
        or set(current_by_key) - set(base_by_key) != ADDED_ENTITY_KEYS
        or {
            key
            for key in base_by_key
            if current_by_key.get(key) != base_by_key[key]
        }
        != GOODMAN_KEYS
    ):
        raise OpenSeedV94Error("v94 GeoJSON replacement boundary differs")

    base_entities = {
        row["stable_key"]: row for row in _csv_rows(BASE_RELEASE / "entities.csv")
    }
    current_entities = {
        row["stable_key"]: row for row in _csv_rows(stage / "entities.csv")
    }
    permitted_entity_changes = {
        goodman.CAMPUS_KEY: {
            "address", "tags_json", "snapshot_as_of", "snapshot_evidence_id",
            "source_url", "source_publisher", "source_retrieved_at",
        },
        goodman.PROJECT_KEY: {
            "address", "capacity_estimates_json", "tags_json", "snapshot_as_of",
            "snapshot_evidence_id", "source_url", "source_publisher",
            "source_retrieved_at",
        },
    }
    for key, permitted in permitted_entity_changes.items():
        changed = {
            field
            for field in base_entities[key]
            if base_entities[key][field] != current_entities[key][field]
        }
        if changed != permitted:
            raise OpenSeedV94Error(f"v94 Goodman entity field delta differs: {key}")

    base_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(BASE_RELEASE / "construction_pipeline.csv")
    }
    current_pipeline = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "construction_pipeline.csv")
    }
    project_changes = {
        field
        for field in base_pipeline[goodman.PROJECT_KEY]
        if base_pipeline[goodman.PROJECT_KEY][field]
        != current_pipeline[goodman.PROJECT_KEY][field]
    }
    if project_changes != permitted_entity_changes[goodman.PROJECT_KEY]:
        raise OpenSeedV94Error("v94 Goodman pipeline field delta differs")
    if any(
        current_pipeline[goodman.PROJECT_KEY][field]
        != current_entities[goodman.PROJECT_KEY][field]
        for field in permitted_entity_changes[goodman.PROJECT_KEY]
    ):
        raise OpenSeedV94Error("v94 Goodman pipeline literals differ")

    expected_geo_changes = {
        goodman.CAMPUS_KEY: {
            "snapshot_as_of", "snapshot_evidence_id", "source_attribution",
            "source_family", "source_published_at", "source_publisher",
            "source_retrieved_at", "source_url", "tags",
        },
        goodman.PROJECT_KEY: {
            "capacity_estimates", "snapshot_as_of", "snapshot_evidence_id",
            "source_attribution", "source_family", "source_published_at",
            "source_publisher", "source_retrieved_at", "source_url", "tags",
        },
    }
    for key, expected in expected_geo_changes.items():
        changed = {
            field
            for field in base_by_key[key]["properties"]
            if base_by_key[key]["properties"][field]
            != current_by_key[key]["properties"][field]
        }
        if (
            changed != expected
            or base_by_key[key]["geometry"] is not None
            or current_by_key[key]["geometry"] is not None
        ):
            raise OpenSeedV94Error(f"v94 Goodman GeoJSON field delta differs: {key}")

    montgomery = "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    if _entity_csv_record(stage / "entities.csv", montgomery) != _entity_csv_record(
        BASE_RELEASE / "entities.csv", montgomery
    ):
        raise OpenSeedV94Error("v94 altered the v93 Montgomery campus CSV record")


def _validate_release_facts(stage: Path, *, recorded_at: str) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise OpenSeedV94Error("v94 release is not an ordinary directory")
    entries = {path.name: path for path in stage.iterdir()}
    if len(entries) != 14 or any(
        path.is_symlink() or not path.is_file() for path in entries.values()
    ):
        raise OpenSeedV94Error("v94 release file inventory differs")
    _raw, manifest = _read_json(stage / "manifest.json", sort_keys=True)
    if (
        manifest.get("as_of") != AS_OF
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("publication_contract_version") != 4
        or manifest.get("entities") != 1_011
        or manifest.get("entities_by_kind") != {"campus": 524, "project": 487}
        or manifest.get("evidence_records") != 665
        or manifest.get("lifecycle_freshness_records") != 562
        or manifest.get("capacity_estimates") != 564
        or manifest.get("construction_pipeline_records") != 513
        or manifest.get("construction_source_signals") != 411
        or manifest.get("append_only_base_release") != v93.RELEASE_ID
        or manifest.get("base_rows_frozen") is not False
        or manifest.get("unaffected_base_rows_frozen") is not True
        or manifest.get("curated_source_input_delta") != 10
        or manifest.get("public_source_input_rows_delta") != 14
        or set(entries) != set(manifest["files"]) | {"manifest.json"}
    ):
        raise OpenSeedV94Error("v94 manifest release facts differ")
    for filename, pin in manifest["files"].items():
        raw = entries[filename].read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV94Error(f"v94 release pin differs: {filename}")
    _validate_public_delta(stage)

    source_inputs = json.loads((stage / "source_inputs.json").read_text())
    sources = source_inputs.get("sources")
    base_sources = json.loads((BASE_RELEASE / "source_inputs.json").read_text())[
        "sources"
    ]
    added_source_inputs = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in sources or []
        if row.get("provenance", {}).get("curated_record_key")
        in ADDED_EXPORTED_EVIDENCE_KEYS
    }
    if (
        not isinstance(sources, list)
        or len(sources) != 592
        or sources[: len(base_sources)] != base_sources
        or len(sources) - len(base_sources) != 14
        or set(added_source_inputs) != ADDED_EXPORTED_EVIDENCE_KEYS
        or any(
            row.get("license") != "all-rights-reserved"
            for row in added_source_inputs.values()
        )
    ):
        raise OpenSeedV94Error("v94 source-input inventory differs")

    relevant_keys = ADDED_ENTITY_KEYS | GOODMAN_KEYS
    entities = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "entities.csv")
        if row["stable_key"] in relevant_keys
    }
    if set(entities) != relevant_keys:
        raise OpenSeedV94Error("v94 relevant entity export differs")
    expected_country = dict.fromkeys(ADDED_ENTITY_KEYS, "United States")
    expected_country.update({
        "curated:merlin-edged-bilbao-arasur-campus": "Spain",
        "curated:merlin-edged-bilbao-arasur-campus:building-2-current-build": "Spain",
        "curated:merlin-edged-bilbao-arasur-campus:building-3-current-build": "Spain",
        "curated:cyrusone-fra5-hanau-campus": "Germany",
        "curated:cyrusone-fra5-hanau-campus:halls-2-3-current-build": "Germany",
    })
    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        if (
            row["latitude"]
            or row["longitude"]
            or row["geometry_json"] not in {"", "null"}
            or row["country"] != expected_country[key]
        ):
            raise OpenSeedV94Error(f"v94 added entity scope differs: {key}")

    for key in ADDED_ENTITY_KEYS:
        row = entities[key]
        workloads = json.loads(row["workloads_json"])
        if key == river.PROJECT_KEY:
            if (
                row["operating_model"] != "hyperscale_lease"
                or [item["workload"] for item in workloads]
                != ["ai_specialized_unspecified"]
            ):
                raise OpenSeedV94Error("v94 River Bend model/workload differs")
        elif row["operating_model"] or workloads:
            raise OpenSeedV94Error(f"v94 unexpected model/workload: {key}")

    expected_entity_capacities = {
        "curated:cyrusone-fra5-hanau-campus": [("critical_it_mw", "planned", 54.0, "2025-08-26")],
        "curated:cyrusone-wood-dale-campus:phase-1-current-build": [("critical_it_mw", "planned", 18.0, "2025-05-13")],
        "curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction": [("gross_facility_mw", "planned", 26.0, "2026-07-21")],
        river.PROJECT_KEY: [("critical_it_mw", "contracted", 245.0, "2025-12-17")],
        river.CAMPUS_KEY: [("grid_connection_mw", "contracted", 330.0, "2025-12-17")],
    }
    for key in ADDED_ENTITY_KEYS:
        capacities = json.loads(entities[key]["capacity_estimates_json"])
        actual = [
            (row["metric"], row["stage"], float(row["base"]), row["as_of_date"])
            for row in capacities
        ]
        if actual != expected_entity_capacities.get(key, []):
            raise OpenSeedV94Error(f"v94 added capacity differs: {key}")

    expected_goodman_source = (
        "https://www.databank.com/resources/press-releases/"
        "databank-and-goodman-group-partner-to-open-new-landmark-data-center-in-los-angeles/"
    )
    for key in GOODMAN_KEYS:
        row = entities[key]
        tags = json.loads(row["tags_json"])
        if (
            row["address"] != GOODMAN_ADDRESS
            or tags.get("address") != GOODMAN_ADDRESS
            or row["snapshot_as_of"] != "2026-04-07"
            or row["snapshot_evidence_id"]
            != "b244ccdf-e6bb-55a0-9048-be08e7fe57fd"
            or row["source_url"] != expected_goodman_source
            or row["source_publisher"] != "DataBank"
            or row["source_retrieved_at"] != "2026-07-22T02:37:32Z"
            or row["latitude"]
            or row["longitude"]
            or row["geometry_json"] not in {"", "null"}
        ):
            raise OpenSeedV94Error(f"v94 Goodman entity literal differs: {key}")
    goodman_capacity = json.loads(
        entities[goodman.PROJECT_KEY]["capacity_estimates_json"]
    )
    if (
        json.loads(entities[goodman.CAMPUS_KEY]["capacity_estimates_json"]) != []
        or len(goodman_capacity) != 1
        or (
            goodman_capacity[0]["metric"], goodman_capacity[0]["stage"],
            float(goodman_capacity[0]["base"]), goodman_capacity[0]["as_of_date"],
            goodman_capacity[0]["evidence_id"],
        )
        != (
            "critical_it_mw", "planned", 32.0, "2026-03-17",
            "deb97e46-bf87-5c68-a6b0-a40874801540",
        )
    ):
        raise OpenSeedV94Error("v94 Goodman capacity literal differs")

    stable_by_entity_id = {
        row["entity_id"]: row["stable_key"]
        for row in _csv_rows(stage / "entities.csv")
    }
    relevant_capacity_rows = {
        (
            stable_by_entity_id[row["entity_id"]], row["metric"], row["stage"],
            row["unit"], float(row["base"]), row["as_of_date"], row["method"],
        )
        for row in _csv_rows(stage / "capacity_estimates.csv")
        if stable_by_entity_id[row["entity_id"]] in relevant_keys
        and row["evidence_id"]
        in {
            "70577de9-8d9c-5621-9e39-61bd5b71b393",
            "39f8ed62-fa3e-5e7b-8516-c91d083331db",
            "5e48435e-d49f-5e10-aef3-9b672b64e571",
            "50374023-9e57-549f-836a-efeec6483a0f",
            "deb97e46-bf87-5c68-a6b0-a40874801540",
        }
    }
    if relevant_capacity_rows != CAPACITY_CONTRACT:
        raise OpenSeedV94Error("v94 public six-capacity contract differs")

    expected_status = {
        key: ("", "") for key in ADDED_ENTITY_KEYS - ADDED_PROJECT_KEYS
    } | {
        "curated:merlin-edged-bilbao-arasur-campus:building-2-current-build": ("under_construction", "2026-04-10"),
        "curated:merlin-edged-bilbao-arasur-campus:building-3-current-build": ("under_construction", "2026-04-10"),
        "curated:cyrusone-fra5-hanau-campus:halls-2-3-current-build": ("under_construction", "2025-08-26"),
        "curated:cyrusone-wood-dale-campus:phase-1-current-build": ("under_construction", "2025-08-12"),
        "curated:beale-tulsa-county-project-clydesdale-campus:initial-phase-current-build": ("under_construction", "2025-11-24"),
        "curated:beale-pima-county-project-blue-bobcat-campus:current-site-preparation": ("site_preparation", "2026-05-11"),
        "curated:bitdeer-wenatchee-washington-campus:2026-ai-conversion-site-preparation": ("site_preparation", "2026-07-21"),
        "curated:bitdeer-massillon-ohio-campus:2026-fire-damaged-buildings-reconstruction": ("under_construction", "2026-07-21"),
        river.PROJECT_KEY: ("under_construction", "2026-05-06"),
    }
    if {
        key: (entities[key]["status"], entities[key]["status_as_of"])
        for key in ADDED_ENTITY_KEYS
    } != expected_status:
        raise OpenSeedV94Error("v94 exported lifecycle facts differ")

    freshness = {
        row["stable_key"]: row
        for row in _csv_rows(stage / "lifecycle_freshness.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if set(freshness) != ADDED_PROJECT_KEYS or any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in freshness.values()
    ):
        raise OpenSeedV94Error("v94 freshness boundary differs")
    pipeline = {
        row["stable_key"]
        for row in _csv_rows(stage / "construction_pipeline.csv")
        if row["stable_key"] in ADDED_PROJECT_KEYS
    }
    if pipeline != ADDED_PROJECT_KEYS:
        raise OpenSeedV94Error("v94 construction-pipeline delta differs")
    added_signals = [
        row
        for row in _csv_rows(stage / "construction_source_signals.csv")
        if row["representative_stable_key"] in ADDED_PROJECT_KEYS
    ]
    expected_signal_representatives = ADDED_PROJECT_KEYS - {
        "curated:merlin-edged-bilbao-arasur-campus:building-3-current-build"
    }
    expected_signal_evidence_ids = {
        "59802962-9ff1-5535-9951-ffb6af59cf8b",
        "70577de9-8d9c-5621-9e39-61bd5b71b393",
        "12d2082e-c823-53ef-a063-1ab49f41388c",
        "d1589797-40b2-5504-9915-7c42882f96b7",
        "a2528000-6723-5204-bad8-6a19a5220011",
        "9bb3b9ad-0b64-5c9f-adc9-abc7463b1a61",
        "5e48435e-d49f-5e10-aef3-9b672b64e571",
        "a3a1a93a-3192-5395-9d0f-eab177eb3935",
    }
    if (
        len(added_signals) != 8
        or {row["representative_stable_key"] for row in added_signals}
        != expected_signal_representatives
        or {row["source_observation_evidence_id"] for row in added_signals}
        != expected_signal_evidence_ids
        or any(
            row["representative_latitude"] or row["representative_longitude"]
            for row in added_signals
        )
    ):
        raise OpenSeedV94Error("v94 construction-source-signal delta differs")

    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    projection = summary.get("append_projection")
    if (
        summary.get("entities_total") != 1_011
        or summary.get("campuses_total") != 524
        or summary.get("projects_total") != 487
        or summary.get("evidence_total") != 845
        or summary.get("lifecycle_observations_current") != 562
        or summary.get("capacity_estimates_current") != 564
        or summary.get("construction_pipeline_records") != 513
        or summary.get("construction_source_signals") != 411
        or summary.get("entities_with_coordinates") != 213
        or summary.get("campuses_with_coordinates") != 141
        or not isinstance(projection, dict)
        or projection.get("curated_source_input_delta") != 10
        or projection.get("public_source_input_rows_delta") != 14
        or projection.get("unaffected_base_rows_frozen") is not True
        or projection.get("internal_database_delta")
        != {
            "entities": 17,
            "entity_snapshots": 19,
            "evidence": 20,
            "lifecycle_observations": 11,
            "capacity_estimates": 6,
            "operating_model_observations": 1,
            "workload_observations": 1,
        }
        or projection.get("public_release_delta")
        != {
            "entities": 17,
            "evidence": 14,
            "lifecycle_freshness": 9,
            "capacity_estimates": 6,
            "construction_pipeline": 9,
            "construction_source_signals": 8,
        }
    ):
        raise OpenSeedV94Error("v94 summary projection contract differs")

    new_features = [
        feature
        for feature in json.loads((stage / "atlas.geojson").read_text())["features"]
        if feature["properties"]["stable_key"] in ADDED_ENTITY_KEYS
    ]
    if len(new_features) != 17 or any(
        feature.get("geometry") is not None for feature in new_features
    ):
        raise OpenSeedV94Error("v94 public geometry append differs")
    readme = (stage / "README.md").read_text(encoding="utf-8")
    for marker in (
        "Open seed v94 is the exact governed accepted-v93 successor",
        "ten ordered curated records at input indices 488 through 497",
        "rejected Merlin",
        "17 entities and updates only the two pre-existing Goodman",
        "All 553 v93 lifecycle-freshness rows remain frozen",
        "adds 20 evidence records, 11 lifecycle observations, six typed",
        "No Beale 500/600 MW context",
        "No inferred energy, PUE, WUE, coordinate, geometry, cross-source",
    ):
        if marker not in readme:
            raise OpenSeedV94Error(f"v94 README guardrail differs: {marker}")


def _validate_definition(
    document: Mapping[str, Any],
    base: Mapping[str, Any],
    *,
    validation_wall_clock: datetime,
) -> str:
    if set(document) != set(base) or document.get("release_id") != RELEASE_ID:
        raise OpenSeedV94Error("v94 definition identity or schema differs")
    build = document.get("build")
    if not isinstance(build, dict) or set(build) != {"as_of", "recorded_at"}:
        raise OpenSeedV94Error("v94 definition build carrier differs")
    if build["as_of"] != AS_OF:
        raise OpenSeedV94Error("v94 as_of differs")
    expected_summary = document.get("expected_summary")
    if not isinstance(expected_summary, dict) or set(expected_summary) != set(
        base["expected_summary"]
    ):
        raise OpenSeedV94Error("v94 expected-summary key contract differs")
    recorded = v70.parse_utc(build["recorded_at"], label="v94 recorded_at")
    if (
        validation_wall_clock.tzinfo is None
        or recorded > validation_wall_clock.astimezone(UTC)
    ):
        raise OpenSeedV94Error("v94 recorded_at is later than validation wall clock")
    for key in (
        "epoch_capture",
        "expected_epoch_result",
        "freshness_contract",
        "publication_contract_version",
        "schema_version",
        "scope",
    ):
        if document.get(key) != base.get(key):
            raise OpenSeedV94Error(f"v94 inherited definition field differs: {key}")
    return build["recorded_at"]


def _validate_publication_times(
    definition: Path,
    release: Path,
    *,
    recorded_at: str,
    require_live: bool,
) -> None:
    target = v70.parse_utc(recorded_at, label="v94 recorded_at")
    for path in (definition, release, *release.iterdir()):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise OpenSeedV94Error(
                f"v94 staged inode post-dates recorded_at: {path.name}"
            )
    if require_live:
        if datetime.now(UTC) < target:
            raise OpenSeedV94Error("v94 recorded_at is not live")
        for path in (definition, release, *release.iterdir()):
            if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
                raise OpenSeedV94Error(
                    f"v94 final inode ctime predates recorded_at: {path.name}"
                )


def _validate_guard(guard: Mapping[str, Any]) -> None:
    base_files = list(BASE_RELEASE.iterdir()) if BASE_RELEASE.is_dir() else []
    base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
    base_manifest = json.loads(
        (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
    )
    if (
        v93.DEFINITION != BASE_DEFINITION
        or v93.RELEASE != BASE_RELEASE
        or BASE_DEFINITION.is_symlink()
        or not BASE_DEFINITION.is_file()
        or stat.S_IMODE(BASE_DEFINITION.stat().st_mode) != 0o444
        or BASE_RELEASE.is_symlink()
        or not BASE_RELEASE.is_dir()
        or stat.S_IMODE(BASE_RELEASE.stat().st_mode) != 0o555
        or not base_files
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in base_files
        )
        or guard["base_definition"] != BASE_DEFINITION_PIN
        or guard["base_manifest"] != BASE_MANIFEST_PIN
        or guard["base_tree"] != BASE_TREE_SHA256
        or guard["base_entities"] != BASE_ENTITIES_PIN
        or guard["base_source_inputs"] != BASE_SOURCE_INPUTS_PIN
        or base_definition.get("build", {}).get("recorded_at") != BASE_RECORDED_AT
        or base_manifest.get("recorded_at") != BASE_RECORDED_AT
    ):
        raise OpenSeedV94Error("accepted v93 base pin differs")
    expected_manifests = {
        label: spec["manifest_pin"] for label, spec in OFFICIAL_SPECS.items()
    }
    expected_trees = {
        label: spec["physical_tree"] for label, spec in OFFICIAL_SPECS.items()
    }
    if (
        guard["official_manifests"] != expected_manifests
        or guard["official_trees"] != expected_trees
        or guard["additions"] != ADDITION_PINS
    ):
        raise OpenSeedV94Error("v94 official-source pin differs")


def validate_open_seed_v94(
    definition_path: Path = DEFINITION,
    release_path: Path = RELEASE,
    *,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
    require_live: bool = True,
) -> dict[str, Any]:
    if replay_count != 2:
        raise OpenSeedV94Error("v94 requires exactly two offline replays")
    wall = validation_wall_clock or datetime.now(UTC)
    guard = _guard_state()
    _validate_guard(guard)
    base = json.loads(BASE_DEFINITION.read_text())
    _definition_raw, definition = _read_json(
        definition_path, mode=0o444, sort_keys=True
    )
    recorded_at = _validate_definition(definition, base, validation_wall_clock=wall)
    selected, paths = selected_inputs(
        base, recorded_at=recorded_at, validation_wall_clock=wall
    )
    if definition.get("curated_inputs") != selected:
        raise OpenSeedV94Error("v94 selected input inventory differs")
    if release_path.is_symlink() or not release_path.is_dir():
        raise OpenSeedV94Error("v94 release must be an ordinary directory")
    if require_frozen and stat.S_IMODE(release_path.stat().st_mode) != 0o555:
        raise OpenSeedV94Error("v94 release root is not frozen")
    release_files = {path.name: path for path in release_path.iterdir()}
    if any(path.is_symlink() or not path.is_file() for path in release_files.values()):
        raise OpenSeedV94Error("v94 release contains a non-file")
    if require_frozen and any(
        stat.S_IMODE(path.stat().st_mode) != 0o444 for path in release_files.values()
    ):
        raise OpenSeedV94Error("v94 release file is not frozen")
    manifest_raw, manifest = _read_json(
        release_path / "manifest.json", mode=0o444, sort_keys=True
    )
    if _sha256(manifest_raw) != definition["expected_release"].get("manifest_sha256"):
        raise OpenSeedV94Error("v94 manifest hash differs")
    expected_release = {
        key: value
        for key, value in definition["expected_release"].items()
        if key != "manifest_sha256"
    }
    if {
        key: value for key, value in manifest.items() if key != "files"
    } != expected_release:
        raise OpenSeedV94Error("v94 expected release facts differ")
    if set(release_files) != set(manifest["files"]) | {"manifest.json"}:
        raise OpenSeedV94Error("v94 release file inventory differs")
    for filename, pin in manifest["files"].items():
        raw = (release_path / filename).read_bytes()
        if (len(raw), _sha256(raw)) != (pin["bytes"], pin["sha256"]):
            raise OpenSeedV94Error(f"v94 release pin differs: {filename}")
    _validate_publication_times(
        definition_path,
        release_path,
        recorded_at=recorded_at,
        require_live=require_live,
    )
    _validate_release_facts(release_path, recorded_at=recorded_at)
    summary = json.loads((release_path / "summary.json").read_text())
    if {key: summary[key] for key in definition["expected_summary"]} != definition[
        "expected_summary"
    ]:
        raise OpenSeedV94Error("v94 expected summary differs")

    for replay in range(replay_count):
        with tempfile.TemporaryDirectory(
            prefix=f"open-seed-v94-replay-{replay + 1}-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            connection = _build_database(
                base, paths, root / "atlas.sqlite", recorded_at=recorded_at
            )
            try:
                replay_release = root / "release"
                _write_release(connection, replay_release, recorded_at=recorded_at)
            finally:
                connection.close()
            _validate_release_facts(replay_release, recorded_at=recorded_at)
            if {path.name for path in replay_release.iterdir()} != set(release_files):
                raise OpenSeedV94Error("v94 replay file inventory differs")
            for filename, frozen in release_files.items():
                if (replay_release / filename).read_bytes() != frozen.read_bytes():
                    raise OpenSeedV94Error(f"v94 offline replay differs: {filename}")
    if _guard_state() != guard:
        raise OpenSeedV94Error("v94 validation mutated accepted inputs")
    return manifest


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = (
        stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    )
    if not expected:
        raise OpenSeedV94Error(f"v94 stage type differs: {path}")
    return metadata.st_dev, metadata.st_ino


def _release_identities(root: Path) -> dict[str, tuple[int, int]]:
    return {path.name: _path_identity(path, directory=False) for path in root.iterdir()}


def _assert_release_identities(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _path_identity(root, directory=True) != root_identity:
        raise OpenSeedV94Error("v94 release stage root identity changed")
    if _release_identities(root) != dict(members):
        raise OpenSeedV94Error("v94 release stage member identity changed")


def _discard_release_stage(
    root: Path,
    root_identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_release_identities(root, root_identity, members)
    root.chmod(0o700)
    for path in root.iterdir():
        path.chmod(0o600)
        path.unlink()
    root.rmdir()


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if _path_identity(path, directory=False) != identity:
        raise OpenSeedV94Error("refusing substituted v94 definition cleanup")
    path.chmod(0o600)
    path.unlink()


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise OpenSeedV94Error("active v94 publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISREG(current.st_mode)
                or (
                    current.st_dev,
                    current.st_ino,
                )
                != identity
            ):
                raise OpenSeedV94Error("refusing substituted v94 lock cleanup")
            PUBLICATION_LOCK.unlink()


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _refresh_publication_ctimes(definition: Path, release: Path) -> None:
    definition.chmod(0o400)
    definition.chmod(0o444)
    _fsync(definition)
    release.chmod(0o500)
    for path in release.iterdir():
        path.chmod(0o400)
        path.chmod(0o444)
        _fsync(path)
    release.chmod(0o555)
    _fsync(release)


def _require_absent(label: str) -> None:
    if DEFINITION.exists() or DEFINITION.is_symlink():
        raise OpenSeedV94Error(f"{label} v94 definition collision")
    if RELEASE.exists() or RELEASE.is_symlink():
        raise OpenSeedV94Error(f"{label} v94 release collision")


def _rollback_release(release_identity: tuple[int, int], release_stage: Path) -> None:
    if _path_identity(RELEASE, directory=True) != release_identity:
        raise OpenSeedV94Error("refusing rollback of substituted v94 release")
    if release_stage.exists() or release_stage.is_symlink():
        raise OpenSeedV94Error("v94 release rollback stage is occupied")
    v69.promote_noreplace(RELEASE, release_stage)


def _rollback_definition(
    definition_identity: tuple[int, int], definition_stage: Path
) -> None:
    if _path_identity(DEFINITION, directory=False) != definition_identity:
        raise OpenSeedV94Error("refusing rollback of substituted v94 definition")
    if definition_stage.exists() or definition_stage.is_symlink():
        raise OpenSeedV94Error("v94 definition rollback stage is occupied")
    v69.promote_noreplace(DEFINITION, definition_stage)


def build_open_seed_v94(recorded_at: str | None = None) -> dict[str, Any]:
    """Build and atomically publish the governed ten-source v93 successor."""

    if (DEFINITION.exists() or DEFINITION.is_symlink()) and (
        RELEASE.exists() or RELEASE.is_symlink()
    ):
        manifest = validate_open_seed_v94()
        return {
            "definition": str(DEFINITION),
            "definition_sha256": v69.sha256(DEFINITION),
            "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
            "recorded_at": manifest["recorded_at"],
            "release": str(RELEASE),
            "release_tree_sha256": v69.tree_digest(RELEASE),
            "status": "existing-identical",
        }
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or RELEASE.exists()
        or RELEASE.is_symlink()
    ):
        raise OpenSeedV94Error("partial v94 final-path collision")

    guard = _guard_state()
    _validate_guard(guard)
    target = (
        v70.parse_utc(recorded_at, label="v94 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if datetime.now(UTC) >= target:
        raise OpenSeedV94Error("v94 recorded_at must be future before staging")
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")

    with _publication_lock():
        _require_absent("initial")
        release_stage = Path(
            tempfile.mkdtemp(prefix=f".{RELEASE.name}.", dir=RELEASE.parent)
        )
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.", suffix=".stage", dir=DEFINITION.parent
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        release_identity = _path_identity(release_stage, directory=True)
        release_members: dict[str, tuple[int, int]] = {}
        published_release = False
        published_definition = False
        try:
            os.close(descriptor)
            base = json.loads(BASE_DEFINITION.read_text())
            input_rows, paths = selected_inputs(
                base, recorded_at=recorded_at, validation_wall_clock=target
            )
            with tempfile.TemporaryDirectory(
                prefix="open-seed-v94-db-", dir="/private/tmp"
            ) as temporary_database:
                connection = _build_database(
                    base,
                    paths,
                    Path(temporary_database) / "atlas.sqlite",
                    recorded_at=recorded_at,
                )
                try:
                    _write_release(
                        connection,
                        release_stage,
                        recorded_at=recorded_at,
                        precreated=True,
                    )
                finally:
                    connection.close()
            _validate_release_facts(release_stage, recorded_at=recorded_at)
            summary = json.loads(
                (release_stage / "summary.json").read_text(encoding="utf-8")
            )
            manifest_raw = (release_stage / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = _sha256(manifest_raw)
            definition = dict(base)
            definition["build"] = {"as_of": AS_OF, "recorded_at": recorded_at}
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary[key] for key in base["expected_summary"]
            }
            definition["release_id"] = RELEASE_ID
            with definition_stage.open("r+b") as stream:
                stream.write(_canonical(definition, sort_keys=True))
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            definition_stage.chmod(0o444)
            _fsync(definition_stage)
            for path in release_stage.iterdir():
                path.chmod(0o444)
                _fsync(path)
            release_stage.chmod(0o555)
            _fsync(release_stage)
            release_members = _release_identities(release_stage)
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=False,
            )
            _require_absent("pre-wait")
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = v69.tree_digest(release_stage)
            _wait_until(target)
            _require_absent("late")
            if _path_identity(definition_stage, directory=False) != definition_identity:
                raise OpenSeedV94Error("v94 definition stage identity changed")
            _assert_release_identities(release_stage, release_identity, release_members)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV94Error("v94 private stage changed while waiting")
            _refresh_publication_ctimes(definition_stage, release_stage)
            _assert_release_identities(release_stage, release_identity, release_members)
            if (
                definition_stage.read_bytes() != frozen_definition
                or v69.tree_digest(release_stage) != frozen_tree
            ):
                raise OpenSeedV94Error("v94 private bytes changed at publication")
            _validate_publication_times(
                definition_stage,
                release_stage,
                recorded_at=recorded_at,
                require_live=True,
            )
            v69.promote_noreplace(release_stage, RELEASE)
            published_release = True
            try:
                v69.promote_noreplace(definition_stage, DEFINITION)
                published_definition = True
            except BaseException as error:
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    error.add_note(f"v94 release rollback failed: {rollback_error}")
                raise
            try:
                manifest = validate_open_seed_v94(DEFINITION, RELEASE)
            except BaseException as error:
                rollback_errors = []
                try:
                    _rollback_definition(definition_identity, definition_stage)
                    published_definition = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v94 definition rollback failed: {rollback_error}"
                    )
                try:
                    _rollback_release(release_identity, release_stage)
                    published_release = False
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"v94 release rollback failed: {rollback_error}"
                    )
                for note in rollback_errors:
                    error.add_note(note)
                raise
        finally:
            if not published_release and release_stage.exists():
                if release_members:
                    _discard_release_stage(
                        release_stage, release_identity, release_members
                    )
                else:
                    shutil.rmtree(release_stage)
            if not published_definition and definition_stage.exists():
                _discard_file_stage(definition_stage, definition_identity)
    if _guard_state() != guard:
        raise OpenSeedV94Error("v94 build mutated accepted inputs")
    return {
        "definition": str(DEFINITION),
        "definition_sha256": v69.sha256(DEFINITION),
        "manifest_sha256": v69.sha256(RELEASE / "manifest.json"),
        "recorded_at": manifest["recorded_at"],
        "release": str(RELEASE),
        "release_tree_sha256": v69.tree_digest(RELEASE),
        "status": "published",
    }


def main() -> int:
    print(json.dumps(build_open_seed_v94(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
