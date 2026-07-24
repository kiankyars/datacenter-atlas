"""Publish a bounded five-candidate Africa official-build gap assessment.

The carrier is independent of every accepted open seed and downstream product.
All source and artifact bytes are staged privately before the declared recording
instant, then promoted without replacement with identity-checked rollback.
"""

from __future__ import annotations

from contextlib import contextmanager
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

from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-africa-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-africa-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-africa-20260721.vjYILG")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-africa-20260721.vjYILG")
CAPTURE_TREE_SHA256 = "236f4463123a1bf906d5bcdbc2c5999227105fdbece1c8f4ff4ed6b34f48cbd6"
CAPTURE_FILE_COUNT = 76
CAPTURE_TOTAL_BYTES = 3_699_358

V79_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v79.json"
V79_RELEASE = ROOT / "releases/2026-07-21-open-seed-v79"
V79_MANIFEST = V79_RELEASE / "manifest.json"
V79_ENTITIES = V79_RELEASE / "entities.csv"
V79_EVIDENCE = V79_RELEASE / "evidence.csv"
V79_PINS = {
    V79_DEFINITION: (
        94_039,
        "3a8cfb0d6ed9f858f5be3ac8cfda7502673241ede8f0aa23715714a09a7d462e",
    ),
    V79_MANIFEST: (
        13_885,
        "4eaceee00a0ed0e9073bc6cd19a8f82c97a442f05e773615ee1bb470a95a5c71",
    ),
    V79_ENTITIES: (
        924_382,
        "33ba938178fcc6405f2ca44736cb9b3ba29139ef34a4adbf93e555c2b90ddd2f",
    ),
    V79_EVIDENCE: (
        219_310,
        "0b24d0c603204ad8348564eefeef50fec21acea3a82413cafc9545239ae97aec",
    ),
}
V79_TREE_SHA256 = "f5cfdebad04ccb8347cdf9cd965e88f096dc44699b938ecc111acc28348858a2"
V79_INPUT_COUNT = 421

PEERINGDB_ASSESSMENT = (
    ROOT / "source_assessments/peeringdb-2026-07-18-v1/assessment.json"
)
PEERINGDB_ASSESSMENT_PIN = (
    12_036,
    "f21ccde34a4e24847b997fce5b8234934356b58d569113eb7bb028f53e2830dc",
)

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-icolo-nbo2-current-build.json",
    "curated-official-2026-07-21-telecom-egypt-rdh2-commissioning.json",
    "curated-official-2026-07-21-teraco-jb7-review-only.json",
    "curated-official-2026-07-21-adc-accra-review-only.json",
    "curated-official-2026-07-21-ixafrica-nbox-phase2-review-only.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialAfricaGapError = publication.OfficialTrancheError
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
    "adc_accra_2023.body": (
        114_974,
        "9648516eaede3dc20d35a985540e4a94df9442b9e6e3f8267fe09d18f3d54c8d",
    ),
    "adc_accra_2023.facts": (
        400,
        "d367c3c49054c5fffcc39943b32b1de388c5d46acd50c7b3663617a9f0b774fc",
    ),
    "adc_accra_2023.headers": (
        486,
        "bf6afd376413c3d85ebba81d3dc8835ce8c2f2c358931caeffb01004dd08b159",
    ),
    "adc_dfc_partnership_2023.body": (
        115_250,
        "7f2e097aab9345fad62a52b214fc6eafc883503be0278c835ad453b54784fcf6",
    ),
    "adc_dfc_partnership_2023.facts": (
        442,
        "bd74dfcde7b024b9339c4b668223fa89d6004cd0abdae100189226befc0be5f3",
    ),
    "adc_dfc_partnership_2023.headers": (
        486,
        "9036ae5bbe112f45b6bf6f729747a6a3f00b4e89dba158e2dced496e62f7aed6",
    ),
    "asaase_adc_delay_2024.body": (
        229_981,
        "1e12f3df1457db47b2b2982f0ee524f67541247502e32085c7bdf25ca958e5c0",
    ),
    "asaase_adc_delay_2024.facts": (
        360,
        "3257d9c1ce3bd946bed9627b0b7ada69e92a41a25db184a257f339f1a1fe5e4a",
    ),
    "asaase_adc_delay_2024.headers": (
        805,
        "a44d48fa92a2940ec2214ffc0df4d4e75bd9c70885414a76c65bc88505c5b1d1",
    ),
    "digital_realty_2022_acquisition.facts": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "digital_realty_2022_acquisition.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "digital_realty_2022_acquisition_q4cdn.body": (
        1_438,
        "3c69bc39bbd289e5e0c51a61a1af86c531d9a49f2d36cffe82ebc0ce4055ee01",
    ),
    "digital_realty_2022_acquisition_q4cdn.facts": (
        367,
        "65b217d35f465f42b6eb4a53805d42d0aec622d0a24790b4107f364368db3aa7",
    ),
    "digital_realty_2022_acquisition_q4cdn.headers": (
        164,
        "65e5a542d6de6f524d2a709663c87617d9df1204975a4f61560c98b83752a661",
    ),
    "digital_realty_2022_brand_release.body": (
        262_566,
        "498667730b815119d3a9eac163f52f562739a1b6335889b5ffca7b415aa0d806",
    ),
    "digital_realty_2022_brand_release.facts": (
        340,
        "51eb4b7b8a9fd160eabbc6d128dd55693725b0f50595b58f4944b7e9c16c2c94",
    ),
    "digital_realty_2022_brand_release.headers": (
        384,
        "89cef45e407e78bfa20924264ecb40587fe47ae8b02d817adcc6dffb98eb1bff",
    ),
    "digital_realty_2026_supplement.facts": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "digital_realty_2026_supplement.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "digital_realty_current_brand_release.body": (
        256_960,
        "ba1e011312bfd91b6f6bdcc89e971a478f2ab39e9473b7c0bb38cad06948fda7",
    ),
    "digital_realty_current_brand_release.facts": (
        418,
        "6c807c58a544df5cdf7e7ec115283a103d9b5bac0625b88e826ca7bbee6ab6c1",
    ),
    "digital_realty_current_brand_release.headers": (
        383,
        "b3e34429620ca2234462566574e1db915c9839d3eaaed4472802edf3a6ece044",
    ),
    "digital_realty_current_release.facts": (
        378,
        "43cb9dbd8de0d87525907eb14f8b552d7468abed28d6e4ddb9ed61b435aa03d4",
    ),
    "digital_realty_current_release.headers": (
        0,
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    "digital_realty_sec_424b7.body": (
        762_389,
        "8ad4cf7bd5934cdb4faec44780a87d01f57d69ad2f77232b81785683eab604d4",
    ),
    "digital_realty_sec_424b7.facts": (
        296,
        "6dbe138daacd068b226ad9bac8e67d93b10fb3dbfb632ff349acf5d784088c37",
    ),
    "digital_realty_sec_424b7.headers": (
        683,
        "80d936cf55d7f71022627785e2eda3b52dbc958e42a5c1d619533436ba46cd21",
    ),
    "dlr_test.body": (
        453,
        "8cd9df01b3153f1dd2a6210f97790a2ba2ac5a493414ef15f817229d74a26281",
    ),
    "ecg_rdh2_page.body": (
        192_653,
        "6d7c0708bed91751ad0d5641efd224a8f63ca59e890d0b879bbd0104a1397d78",
    ),
    "ecg_rdh2_page.facts": (
        288,
        "79c3a306a14774d44b42bc8346b954d2c666d7f83eb5f95997c57b94ef07864c",
    ),
    "ecg_rdh2_page.headers": (
        441,
        "1561829489addb5a8593d2eece36fd60fbdf1758adf03f73cdc18ec81973fe98",
    ),
    "ecg_rdh2_pdf.body": (
        125_070,
        "cd14925dccec5a358b24fa653d57dd78a5f50454303e7997cd2f061029f08ba2",
    ),
    "ecg_rdh2_pdf.facts": (
        286,
        "3d54f4bb5dbad4f1f55521c17c4dae1656552f92caf9be4e6c5db4ab0c53d98c",
    ),
    "ecg_rdh2_pdf.headers": (
        623,
        "efd608b7ddd6b37ece8c41437a43b269f7da341f513fda3b4b9866c97469837f",
    ),
    "icolo_nbo2_specs_embed.body": (
        25_819,
        "29ece47b4e57faa556eb716f834175363a2b4f082aa4290a9f38ead326f10812",
    ),
    "icolo_nbo2_specs_embed.facts": (
        297,
        "79c48a285511113b10dfed28e4715d579868894c0b65ad96cb5bd8988f64c777",
    ),
    "icolo_nbo2_specs_embed.headers": (
        3_870,
        "37c3454079c88a6aa219d57d39dbad3718fff9e472754265caa83d730b16c50a",
    ),
    "icolo_nbo2_specs_post.body": (
        381_435,
        "d9e67ee6ddc2667d114f5e6db67ad6c3b2352a2d9d26357b85deceb9f5652d7a",
    ),
    "icolo_nbo2_specs_post.facts": (
        334,
        "5c789fb2fc207761b1a01f116986ca4e8c025aa773c12ff588ebf81621f45921",
    ),
    "icolo_nbo2_specs_post.headers": (
        5_347,
        "641120f3893522d428baf1f9780279845294c041787a2167b1773b08129ee0c2",
    ),
    "icolo_nbo2_status_embed.body": (
        25_236,
        "b9c9d14aa3131004410623a1e5618b63791e29f95738b5fbb34c37b8c64af82d",
    ),
    "icolo_nbo2_status_embed.facts": (
        297,
        "5d62a31fa9a4b1aa52f2aa7ed6331200c3ed0ccd77cd5edfa021b67c3fdbb6c3",
    ),
    "icolo_nbo2_status_embed.headers": (
        3_870,
        "bf0f973679a88429229687a65460308828282a920f9e20f4404a361697a4a547",
    ),
    "icolo_nbo2_status_post.body": (
        296_608,
        "565264be0fa6c66c7e349f38255e66ca1152090359dd3f37719566d564a24b4c",
    ),
    "icolo_nbo2_status_post.facts": (
        360,
        "15849e6fa61b74fda342385133669cbf76c0b8bcc9fbbb777be8bca8d98ed979",
    ),
    "icolo_nbo2_status_post.headers": (
        5_616,
        "d9758057657351b774ef8db7ec7739c52f0c986351e8661eda7d0c81f7b7ad51",
    ),
    "ixafrica_campus_specs.body": (
        52_812,
        "b6bf1e7c40f93e1cb57be4f9c7761ecac4d891612c803a97d18cb49f86d1b5ab",
    ),
    "ixafrica_campus_specs.facts": (
        214,
        "ae2b54df61654d1eeb402a4ecc0d1b604aac3c623a3c06b76a53e6e5f09c9715",
    ),
    "ixafrica_campus_specs.headers": (
        448,
        "bdcdd07746b8b8837ec858a255223138f37ceb992f412813a82d77fce399ddf6",
    ),
    "ixafrica_nbox_embed.body": (
        34_344,
        "1a65ce44dd5895b32fc98f2aff5561b328d4d15564995f77de2cf439f5666f2b",
    ),
    "ixafrica_nbox_embed.facts": (
        297,
        "79b592f87d7a5096aeeb5958afe3a11396e469d600d79da1b2b5543015154b85",
    ),
    "ixafrica_nbox_embed.headers": (
        3_870,
        "db27a08e0f0760f0ac11db68d6262c356edcc5043a9ba11fd85cdfe2dd849fce",
    ),
    "ixafrica_nbox_post.body": (
        332_693,
        "54dc0ee504f0ff3e4d3700aa18df9979431d40d947ae1e65d283c1f94eceedfd",
    ),
    "ixafrica_nbox_post.facts": (
        378,
        "7ed53909f756b0ac54bff52b9209c5e307e222a8698bbd2b710baf3539208f63",
    ),
    "ixafrica_nbox_post.headers": (
        5_348,
        "e0acbf8cdbf6544422b0e8635e912709bad552d882ada3a79ce6c3fad67be5e0",
    ),
    "peeringdb_api_fac_14166.body": (
        3_951,
        "ca587c206fa224fee01786bf5c383f6d2688ae97e4e7760f55ae249a3a277a5e",
    ),
    "peeringdb_api_fac_14166.facts": (
        226,
        "59da158efe6fa6dc19597e3fb293625485d169de6b1530d9f82dc19920d19c40",
    ),
    "peeringdb_api_fac_14166.headers": (
        1_053,
        "a3704f5b39a3ecf4ff151b913186da3198efd263248867cc2a56cdf09adf2269",
    ),
    "peeringdb_aup.body": (
        14_865,
        "79bb8fd9c5ba8c0ac685a8cf1f6211c84fad4828231ed144c354db306acbecba",
    ),
    "peeringdb_aup.facts": (
        200,
        "257798534ab73c205f5e2d4304e145db1069777a2cba0be1a472590fbbc5ae50",
    ),
    "peeringdb_aup.headers": (
        1_022,
        "34405a1cef8a9ed71962811af59f7c6de4a0adaf0bebd2f052e98bdf947910d4",
    ),
    "peeringdb_fac_14166.body": (
        45_978,
        "60fe38db2337fc7d61989c8278a5d03ce0cd0c015cbbd7c255c59efa05499682",
    ),
    "peeringdb_fac_14166.facts": (
        212,
        "1b9e08a4bcba84216e457531ec10c40d299188af388a9c0d11c455353a21d7b7",
    ),
    "peeringdb_fac_14166.headers": (
        1_000,
        "804aea12691acf9d0d48e2a216eb7643a0e3f0eebcadc89419b98e892b834e8b",
    ),
    "tab_rdh2_embed.body": (
        23_475,
        "41f75217480fcf6e837838a715524a16db96ccdb6fbd7baa46bc460732b8f0fe",
    ),
    "tab_rdh2_embed.facts": (
        297,
        "6fe1ad73156ff5295ec264d6c98fee3ba21aa21484ea75e52d571d6cdcf2d778",
    ),
    "tab_rdh2_embed.headers": (
        3_870,
        "015e5e3e9b32a582b3a85d6e4b3fc3adac1acfcb392411912377bc608f54f34a",
    ),
    "tab_rdh2_post.body": (
        94_877,
        "8eb0e21e172e2e21d7fccbde0886a6a1bc72f9e2f21d0c13026d2a4c602a046d",
    ),
    "tab_rdh2_post.facts": (
        358,
        "92f503e98afe9131a857c707921348f8ddecdf8742099b59afaf6040664161fe",
    ),
    "tab_rdh2_post.headers": (
        5_348,
        "29671de2308ec6f4c0c61e1589cbb78373cad4841dc736dc16e89e1aabdeff67",
    ),
    "telecom_egypt_rdh2.body": (
        96_984,
        "51c71bc663040314c88d704bf1b22896c69195767c83db49325bb9d6fa5b39ac",
    ),
    "telecom_egypt_rdh2.facts": (
        390,
        "990ab504bf49b704ea6d6e0f2150b79271a35f2e01aca92cbc7d6fb72897efab",
    ),
    "telecom_egypt_rdh2.headers": (
        376,
        "c5953bd16b5b76546d0aef43f4dffe0c62ce4dd95c4ba18d63a448864ff533b4",
    ),
    "teraco_jb7.body": (
        154_183,
        "f0c618fbfd3c735151284b99bcb3dc41c82f61f4fd46edddbbc6eac71a5cce77",
    ),
    "teraco_jb7.facts": (
        318,
        "b730213864230344c70fffa864c0ea2433e1ec2e8de164ea9ec7b6e0147a3155",
    ),
    "teraco_jb7.headers": (
        1_118,
        "3fb77b252df01de4ac46eb2ff37dc9683cdb269cfeed7d09388d72193414df7d",
    ),
}


CAPTURES: dict[str, dict[str, Any]] = {
    "icolo_nbo2_status": {
        "filename": "icolo_nbo2_status_embed.body",
        "url": "https://www.linkedin.com/embed/feed/update/urn:li:activity:7452265528620015617",
        "retrieved_at": "2026-07-21T16:40:39Z",
        "http_status": 200,
        "bytes": 25_236,
        "sha256": "b9c9d14aa3131004410623a1e5618b63791e29f95738b5fbb34c37b8c64af82d",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": True,
    },
    "icolo_nbo2_specs": {
        "filename": "icolo_nbo2_specs_embed.body",
        "url": "https://www.linkedin.com/embed/feed/update/urn:li:activity:7422549433390727168",
        "retrieved_at": "2026-07-21T16:40:40Z",
        "http_status": 200,
        "bytes": 25_819,
        "sha256": "29ece47b4e57faa556eb716f834175363a2b4f082aa4290a9f38ead326f10812",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": True,
    },
    "peeringdb_fac_14166": {
        "filename": "peeringdb_api_fac_14166.body",
        "url": "https://www.peeringdb.com/api/fac/14166",
        "retrieved_at": "2026-07-21T16:40:41Z",
        "http_status": 200,
        "bytes": 3_951,
        "sha256": "ca587c206fa224fee01786bf5c383f6d2688ae97e4e7760f55ae249a3a277a5e",
        "content_type": "application/json; charset=utf-8",
        "used_for_normalized_claims": False,
    },
    "tab_rdh2_commissioning": {
        "filename": "tab_rdh2_embed.body",
        "url": "https://www.linkedin.com/embed/feed/update/urn:li:activity:7470418236245942286",
        "retrieved_at": "2026-07-21T16:40:42Z",
        "http_status": 200,
        "bytes": 23_475,
        "sha256": "41f75217480fcf6e837838a715524a16db96ccdb6fbd7baa46bc460732b8f0fe",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": True,
    },
    "telecom_egypt_rdh2": {
        "filename": "telecom_egypt_rdh2.body",
        "url": "https://ir.te.eg/en/CorporateNews/PressRelease/211/Telecom-Egypt-s-Regional-Data-Hub-2-Awarded-Tier-III-Design-Certification",
        "retrieved_at": "2026-07-21T16:40:43Z",
        "http_status": 200,
        "bytes": 96_984,
        "sha256": "51c71bc663040314c88d704bf1b22896c69195767c83db49325bb9d6fa5b39ac",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": True,
    },
    "ecg_rdh2": {
        "filename": "ecg_rdh2_page.body",
        "url": "https://www.ecgsa.com/telecom-egypt-regional-data-hub-2-rdh2-data-center/",
        "retrieved_at": "2026-07-21T16:40:44Z",
        "http_status": 200,
        "bytes": 192_653,
        "sha256": "6d7c0708bed91751ad0d5641efd224a8f63ca59e890d0b879bbd0104a1397d78",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
    },
    "teraco_jb7": {
        "filename": "teraco_jb7.body",
        "url": "https://www.teraco.co.za/news/teraco-announces-jb7-and-a-new-r8-billion-syndicated-loan/",
        "retrieved_at": "2026-07-21T16:40:45Z",
        "http_status": 200,
        "bytes": 154_183,
        "sha256": "f0c618fbfd3c735151284b99bcb3dc41c82f61f4fd46edddbbc6eac71a5cce77",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
    },
    "digital_realty_sec_424b7": {
        "filename": "digital_realty_sec_424b7.body",
        "url": "https://www.sec.gov/Archives/edgar/data/1297996/000119312526291397/d100245d424b7.htm",
        "retrieved_at": "2026-07-21T16:44:27Z",
        "http_status": 200,
        "bytes": 762_389,
        "sha256": "8ad4cf7bd5934cdb4faec44780a87d01f57d69ad2f77232b81785683eab604d4",
        "content_type": "text/html",
        "used_for_normalized_claims": False,
    },
    "digital_realty_current_brand": {
        "filename": "digital_realty_current_brand_release.body",
        "url": "https://www.digitalrealty.com/about/newsroom/press-releases/30396/digital-realty-announces-transactions-to-drive-continued-platform-growth",
        "retrieved_at": "2026-07-21T16:44:34Z",
        "http_status": 200,
        "bytes": 256_960,
        "sha256": "ba1e011312bfd91b6f6bdcc89e971a478f2ab39e9473b7c0bb38cad06948fda7",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": False,
    },
    "digital_realty_2022_brand": {
        "filename": "digital_realty_2022_brand_release.body",
        "url": "https://www.digitalrealty.com/about/newsroom/press-releases/122963/digital-realty-to-acquire-teraco",
        "retrieved_at": "2026-07-21T16:44:43Z",
        "http_status": 200,
        "bytes": 262_566,
        "sha256": "498667730b815119d3a9eac163f52f562739a1b6335889b5ffca7b415aa0d806",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": False,
    },
    "adc_accra_2023": {
        "filename": "adc_accra_2023.body",
        "url": "https://www.africadatacentres.com/africa-data-centres-announces-that-it-will-start-construction-on-a-new-facility-in-accra-ghana/",
        "retrieved_at": "2026-07-21T16:40:48Z",
        "http_status": 200,
        "bytes": 114_974,
        "sha256": "9648516eaede3dc20d35a985540e4a94df9442b9e6e3f8267fe09d18f3d54c8d",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
    },
    "adc_dfc_partnership_2023": {
        "filename": "adc_dfc_partnership_2023.body",
        "url": "https://www.africadatacentres.com/africa-data-centres-dfc-sign-statement-reaffirming-ongoing-partnership-for-ghana-facility-investment-of-300-million/",
        "retrieved_at": "2026-07-21T16:40:51Z",
        "http_status": 200,
        "bytes": 115_250,
        "sha256": "7f2e097aab9345fad62a52b214fc6eafc883503be0278c835ad453b54784fcf6",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
    },
    "asaase_adc_delay_2024": {
        "filename": "asaase_adc_delay_2024.body",
        "url": "https://asaaseradio.com/300-million-us-funded-mega-data-centre-at-trade-fair-on-course-ignore-bright-simmons/",
        "retrieved_at": "2026-07-21T16:40:58Z",
        "http_status": 200,
        "bytes": 229_981,
        "sha256": "1e12f3df1457db47b2b2982f0ee524f67541247502e32085c7bdf25ca958e5c0",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
    },
    "ixafrica_nbox": {
        "filename": "ixafrica_nbox_embed.body",
        "url": "https://www.linkedin.com/embed/feed/update/urn:li:activity:7422639430353444864",
        "retrieved_at": "2026-07-21T16:41:00Z",
        "http_status": 200,
        "bytes": 34_344,
        "sha256": "1a65ce44dd5895b32fc98f2aff5561b328d4d15564995f77de2cf439f5666f2b",
        "content_type": "text/html; charset=utf-8",
        "used_for_normalized_claims": False,
    },
    "ixafrica_specs": {
        "filename": "ixafrica_campus_specs.body",
        "url": "https://ixafrica.co.ke/campus-specs/",
        "retrieved_at": "2026-07-21T16:41:00Z",
        "http_status": 200,
        "bytes": 52_812,
        "sha256": "b6bf1e7c40f93e1cb57be4f9c7761ecac4d891612c803a97d18cb49f86d1b5ab",
        "content_type": "text/html; charset=UTF-8",
        "used_for_normalized_claims": False,
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
        "http_status": capture["http_status"],
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved bytes; response "
            "bodies, headers, telemetry, and publisher media are not redistributed."
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
    confidence: float = 0.99,
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


def _lifecycle(value: str, evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": 0.99,
    }


def _classification(value: str, evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": value,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "company_disclosure",
        "confidence": 0.99,
    }


def _capacity(
    value: float,
    evidence_key: str,
    as_of_date: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "entity": "project",
        "metric": "critical_it_mw",
        "stage": "design",
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


def _icolo_nbo2_source() -> dict[str, Any]:
    status_key = "icolo-nbo2-physical-update-2026-04-21-captured-2026-07-21"
    specs_key = "icolo-nbo2-design-specs-2026-01-29-captured-2026-07-21"
    peering_key = "peeringdb-fac-14166-rights-metadata-only-captured-2026-07-21"
    evidence = [
        _evidence(
            "icolo_nbo2_status",
            key=status_key,
            kind="company_disclosure",
            title="iColo NBO2 construction update",
            publisher="iColo",
            source_family="icolo_official_linkedin_updates",
            published_at="2026-04-21",
            excerpt=(
                "iColo reports NBO2 weather-tight, live site power supporting ongoing "
                "commissioning, installed electrical equipment, cooling work, and active fit-out."
            ),
            metadata={
                "canonical_post_url": (
                    "https://www.linkedin.com/posts/icolo-io_nbo2-constructionupdate-"
                    "datacentres-activity-7452265528620015617-qhTs"
                ),
                "linkedin_activity_id": "7452265528620015617",
                "activity_date_utc": "2026-04-21",
                "capture_surface": "unauthenticated_public_linkedin_embed",
                "physical_status_scope": (
                    "Direct contemporaneous equipment, testing, fit-out, and commissioning "
                    "details support generic under_construction on the post date only."
                ),
                "power_guardrail": (
                    "Live site power supports commissioning; it is not current IT load, "
                    "gross demand, annual energy, or proof that customer service is operational."
                ),
            },
        ),
        _evidence(
            "icolo_nbo2_specs",
            key=specs_key,
            kind="company_disclosure",
            title="Meet iColo NBO2",
            publisher="iColo",
            source_family="icolo_official_linkedin_updates",
            published_at="2026-01-29",
            excerpt=(
                "iColo describes carrier-neutral NBO2 in Nairobi as under construction "
                "with a 6.5 MW IT-load design and enterprise and cloud customer intent."
            ),
            metadata={
                "canonical_post_url": (
                    "https://www.linkedin.com/posts/icolo-io_icolo-nbo2-datacenters-"
                    "activity-7422549433390727168-wUCS"
                ),
                "linkedin_activity_id": "7422549433390727168",
                "activity_date_utc": "2026-01-29",
                "capture_surface": "unauthenticated_public_linkedin_embed",
                "critical_it_mw_as_reported": 6.5,
                "white_space_sqm_as_reported": 3_600,
                "distance_from_nbo1_metres_as_reported": 300,
                "operating_model_scope": (
                    "Carrier-neutral wording supports generic colocation only; wholesale "
                    "versus retail service is not inferred."
                ),
                "workload_scope": (
                    "Enterprises and cloud providers are prospective design/customer segments, "
                    "not active load, named tenants, users, contracts, or installed hardware."
                ),
                "hyperscale_guardrail": (
                    "Hyperscaler design intent is retained as narrative because the workload "
                    "taxonomy has no equivalent and no tenant is identified."
                ),
            },
        ),
        _evidence(
            "peeringdb_fac_14166",
            key=peering_key,
            kind="company_disclosure",
            title="PeeringDB facility 14166 access and rights metadata only",
            publisher="PeeringDB",
            source_family="peeringdb_blocked_direct_lane_metadata",
            published_at=None,
            excerpt=(
                "An anonymous record response was captured only to document access and "
                "rights handling; no PeeringDB record value is released or normalized."
            ),
            metadata={
                "anonymous_access": True,
                "record_values_released": 0,
                "address_values_released": 0,
                "coordinate_values_released": 0,
                "identity_values_released": 0,
                "placement_rows_created": 0,
                "direct_release_permitted": False,
                "publication_eligible": False,
                "assessment_status": "blocked_pending_written_permission",
                "assessment_path": (
                    "source_assessments/peeringdb-2026-07-18-v1/assessment.json"
                ),
                "assessment_bytes": PEERINGDB_ASSESSMENT_PIN[0],
                "assessment_sha256": PEERINGDB_ASSESSMENT_PIN[1],
                "aup_url": "https://www.peeringdb.com/aup",
                "aup_capture_bytes": CAPTURE_FILE_PINS["peeringdb_aup.body"][0],
                "aup_capture_sha256": CAPTURE_FILE_PINS["peeringdb_aup.body"][1],
                "rights_guardrail": (
                    "The repository assessment forbids direct release, cache, bulk fetch, "
                    "and derivative publication pending written permission. The response "
                    "remains private in Trash and contributes no identity or placement."
                ),
            },
        ),
    ]
    campus_key = "curated:icolo-nbo2-karen-nairobi-campus"
    project_key = f"{campus_key}:initial-build"
    roles = {"operator": ["iColo"], "developer": ["iColo"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="iColo NBO2 Nairobi Campus",
            country="Kenya",
            address="Nairobi, Kenya",
            roles=roles,
            evidence_key=specs_key,
            as_of_date="2026-01-29",
        ),
        "project": _entity(
            stable_key=project_key,
            name="iColo NBO2 Initial Build",
            country="Kenya",
            address="Nairobi, Kenya",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-04-21",
        ),
        "lifecycle": [_lifecycle("under_construction", status_key, "2026-04-21")],
        "operating_models": [_classification("colocation", specs_key, "2026-01-29")],
        "workloads": [
            _classification("enterprise_it", specs_key, "2026-01-29"),
            _classification("general_cloud", specs_key, "2026-01-29"),
        ],
        "capacities": [
            _capacity(
                6.5,
                specs_key,
                "2026-01-29",
                "Publisher-reported design IT load for NBO2. It is not current draw, "
                "gross facility demand, utility supply, generation, annual energy, PUE, "
                "or proof of energization or operation.",
            )
        ],
    }


def _telecom_egypt_rdh2_source() -> dict[str, Any]:
    status_key = "tab-rdh2-commissioning-2026-06-10-captured-2026-07-21"
    specs_key = "telecom-egypt-rdh2-design-2024-11-18-captured-2026-07-21"
    ecg_key = "ecg-rdh2-project-page-2026-01-20-captured-2026-07-21"
    evidence = [
        _evidence(
            "tab_rdh2_commissioning",
            key=status_key,
            kind="company_disclosure",
            title="TAB commissioning services for Regional Data Hub 2",
            publisher="TAB Egypt",
            source_family="tab_egypt_official_linkedin_updates",
            published_at="2026-06-10",
            excerpt=(
                "TAB reports current comprehensive commissioning services for RDH2, "
                "validating functionality, performance, and integration before operation."
            ),
            metadata={
                "canonical_post_url": (
                    "https://www.linkedin.com/posts/tabegypt_tab-commissioning-"
                    "regionaldatahub2-activity-7470418236245942286-F1v9"
                ),
                "linkedin_activity_id": "7470418236245942286",
                "activity_date_utc": "2026-06-10",
                "capture_surface": "unauthenticated_public_linkedin_embed",
                "delivery_party_as_reported": "Raya Network Services",
                "physical_status_scope": (
                    "Commissioning services and explicit before-operation wording support "
                    "commissioning as a dated last-observed status, never operation."
                ),
            },
        ),
        _evidence(
            "telecom_egypt_rdh2",
            key=specs_key,
            kind="company_disclosure",
            title="Telecom Egypt RDH2 awarded Tier III Design Certification",
            publisher="Telecom Egypt",
            source_family="telecom_egypt_corporate_news",
            published_at="2024-11-18",
            excerpt=(
                "Telecom Egypt reports a Tier III design certificate and estimated 4.6 MW "
                "IT load for RDH2, with business-continuity and cloud-transition design intent."
            ),
            metadata={
                "critical_it_mw_as_reported": 4.6,
                "tier_certification_scope": "Tier III Design Certification",
                "old_completion_target_as_reported": "end of 2025",
                "completion_guardrail": (
                    "The old target is forward-looking and superseded for status purposes "
                    "by the June 2026 pre-operation commissioning observation."
                ),
                "workload_scope": (
                    "Business continuity and businesses transitioning to cloud support "
                    "prospective enterprise and cloud design intent only."
                ),
            },
        ),
        _evidence(
            "ecg_rdh2",
            key=ecg_key,
            kind="company_disclosure",
            title="ECG Telecom Egypt Regional Data Hub 2 project page",
            publisher="Engineering Consultants Group S.A.",
            source_family="ecg_project_pages",
            published_at="2026-01-20",
            excerpt=(
                "ECG lists a 4.9 MW IT figure, 510 racks, three halls, and a completed "
                "project status for its RDH2 design and supervision engagement."
            ),
            metadata={
                "page_modified_at": "2026-07-16",
                "client_as_reported": "Raya Networks Services",
                "land_area_sqm_as_reported": 3_825,
                "built_area_sqm_as_reported": 2_300,
                "critical_it_mw_as_reported": 4.9,
                "racks_as_reported": 510,
                "data_halls_as_reported": 3,
                "project_status_as_reported": "Completed",
                "capacity_conflict": (
                    "The contractor's 4.9 MW conflicts with Telecom Egypt's 4.6 MW. "
                    "No reconciliation or arithmetic is attempted; only the operator's "
                    "earlier 4.6 MW design row is normalized."
                ),
                "status_conflict": (
                    "Completed is retained as contractor project-page context, not facility "
                    "operation. The later TAB source explicitly says commissioning is before operation."
                ),
            },
        ),
    ]
    campus_key = "curated:telecom-egypt-rdh2-smart-village-campus"
    project_key = f"{campus_key}:regional-data-hub-2"
    roles = {"owner": ["Telecom Egypt"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Telecom Egypt RDH2 Smart Village Campus",
            country="Egypt",
            address="Smart Village, Giza, Egypt",
            roles=roles,
            evidence_key=specs_key,
            as_of_date="2024-11-18",
        ),
        "project": _entity(
            stable_key=project_key,
            name="Telecom Egypt Regional Data Hub 2",
            country="Egypt",
            address="Smart Village, Giza, Egypt",
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-06-10",
        ),
        "lifecycle": [_lifecycle("commissioning", status_key, "2026-06-10")],
        "operating_models": [],
        "workloads": [
            _classification("enterprise_it", specs_key, "2024-11-18"),
            _classification("general_cloud", specs_key, "2024-11-18"),
        ],
        "capacities": [
            _capacity(
                4.6,
                specs_key,
                "2024-11-18",
                "Telecom Egypt's estimated design IT load. ECG later reports 4.9 MW; "
                "the unresolved conflict is not averaged, summed, or converted. This row "
                "is not current draw, gross demand, utility supply, annual energy, or PUE.",
            )
        ],
    }


def _teraco_jb7_source() -> dict[str, Any]:
    start_key = "africa-gap-jb7-old-start-review-captured-2026-07-21"
    aggregate_key = "africa-gap-teraco-aggregate-2026-03-31-captured-2026-07-21"
    evidence = [
        _evidence(
            "teraco_jb7",
            key=start_key,
            kind="company_disclosure",
            title="Teraco announces JB7 and a new R8 billion syndicated loan",
            publisher="Teraco",
            source_family="teraco_newsroom_africa_gap_review",
            published_at="2024-11-13",
            excerpt=(
                "Teraco reported that JB7 construction commenced in November 2024 and "
                "described 40 MW critical-power design and a forward 2026 completion schedule."
            ),
            metadata={
                "critical_power_mw_as_reported": 40,
                "utility_supply_mva_as_reported": 68,
                "building_area_sqm_as_reported": 71_000,
                "completion_forecast_as_reported": "2026",
                "lifecycle_guardrail": (
                    "The 2024 start is outside the current-status window. A forecast year "
                    "is not evidence of completion, commissioning, operation, or continuing work."
                ),
                "capacity_guardrail": (
                    "All figures remain review narrative in this source-scoped quarantine "
                    "record; MVA is not converted to MW and no current load is asserted."
                ),
                "classification_guardrail": (
                    "Colocation, cloud, enterprise, hyperscale, and AI-capable design wording "
                    "creates no observation in this current-gap review record."
                ),
            },
        ),
        _evidence(
            "digital_realty_sec_424b7",
            key=aggregate_key,
            kind="government_record",
            title="Digital Realty Trust prospectus supplement filed July 1, 2026",
            publisher="U.S. Securities and Exchange Commission",
            source_family="sec_edgar_digital_realty_filings",
            published_at="2026-07-01",
            excerpt=(
                "The filing reports Teraco joint-venture totals of 126 MW existing and "
                "41 MW under construction as of March 31, 2026."
            ),
            metadata={
                "sec_accession": "0001193125-26-291397",
                "information_as_of": "2026-03-31",
                "teraco_existing_capacity_mw_as_reported": 126,
                "teraco_under_construction_mw_as_reported": 41,
                "site_binding": "none",
                "site_binding_guardrail": (
                    "The filing gives a portfolio aggregate and does not name JB7, bind "
                    "any portion to JB7, or establish a JB7 physical status."
                ),
                "capacity_guardrail": (
                    "The aggregate is not allocated, divided, subtracted, or normalized "
                    "as JB7 capacity, current load, demand, energy, or project progress."
                ),
            },
        ),
    ]
    campus_key = "curated-review:africa-gap-teraco-isando-campus"
    project_key = f"{campus_key}:jb7"
    roles = {"operator": ["Teraco"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Teraco Isando Campus (Africa gap review)",
            country="South Africa",
            address="Isando, Ekurhuleni, South Africa",
            roles=roles,
            evidence_key=start_key,
            as_of_date="2024-11-13",
        ),
        "project": _entity(
            stable_key=project_key,
            name="Teraco JB7 (Africa gap review only)",
            country="South Africa",
            address="Isando, Ekurhuleni, South Africa",
            roles=roles,
            evidence_key=start_key,
            as_of_date="2024-11-13",
        ),
        "lifecycle": [],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _adc_accra_source() -> dict[str, Any]:
    future_key = "africa-gap-adc-accra-future-start-2023-05-18-captured-2026-07-21"
    partnership_key = "africa-gap-adc-accra-partnership-2023-10-13-captured-2026-07-21"
    evidence = [
        _evidence(
            "adc_accra_2023",
            key=future_key,
            kind="company_disclosure",
            title="Africa Data Centres announces intended Accra construction",
            publisher="Africa Data Centres",
            source_family="africa_data_centres_news_africa_gap_review",
            published_at="2023-05-18",
            excerpt=(
                "Africa Data Centres said it would shortly start a facility within the "
                "Ghana Trade Fair redevelopment at La in Accra."
            ),
            metadata={
                "initial_design_mw_as_reported": 10,
                "potential_expansion_mw_as_reported": 30,
                "old_phase_one_schedule_as_reported": "within 12 months",
                "lifecycle_guardrail": (
                    "Future-start and schedule wording from 2023 is not a physical start, "
                    "current 2026 status, completion, commissioning, or operation."
                ),
                "capacity_guardrail": (
                    "The 10 MW and possible 30 MW figures remain review narrative because "
                    "the current site state is unresolved; no stage or current load is asserted."
                ),
            },
        ),
        _evidence(
            "adc_dfc_partnership_2023",
            key=partnership_key,
            kind="company_disclosure",
            title="Africa Data Centres and DFC reaffirm Ghana facility partnership",
            publisher="Africa Data Centres",
            source_family="africa_data_centres_news_africa_gap_review",
            published_at="2023-10-13",
            excerpt=(
                "Africa Data Centres and DFC reaffirmed intent to mobilize part of an "
                "existing financing commitment for a Ghana data-centre facility."
            ),
            metadata={
                "financing_commitment_usd_as_reported": 300_000_000,
                "finance_guardrail": (
                    "The amount is a broader existing financing commitment and is not "
                    "facility capex, power, energy, physical progress, or proof of construction."
                ),
                "secondary_review_metadata": {
                    "publisher": "Asaase Radio",
                    "source_url": CAPTURES["asaase_adc_delay_2024"]["url"],
                    "published_at": "2024-12-18",
                    "body_bytes": CAPTURES["asaase_adc_delay_2024"]["bytes"],
                    "body_sha256": CAPTURES["asaase_adc_delay_2024"]["sha256"],
                    "disposition": (
                        "Contextual report of delay amid restructuring and financing; "
                        "metadata only, not official-source evidence or physical status."
                    ),
                },
                "current_status_guardrail": (
                    "No selected 2026 site-specific source establishes continuing work, a "
                    "restart, completion, commissioning, cancellation, or operation."
                ),
                "contractor_source_guardrail": (
                    "The task-referenced contractor/FY2025 source was not recovered and "
                    "is neither invented nor used."
                ),
            },
        ),
    ]
    campus_key = "curated-review:africa-gap-adc-accra-trade-fair-campus"
    project_key = f"{campus_key}:planned-initial-build"
    roles = {"developer": ["Africa Data Centres"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Africa Data Centres Accra Trade Fair Campus (review)",
            country="Ghana",
            address="Ghana Trade Fair, La, Accra, Ghana",
            roles=roles,
            evidence_key=future_key,
            as_of_date="2023-05-18",
        ),
        "project": _entity(
            stable_key=project_key,
            name="Africa Data Centres Accra Planned Initial Build (review only)",
            country="Ghana",
            address="Ghana Trade Fair, La, Accra, Ghana",
            roles=roles,
            evidence_key=future_key,
            as_of_date="2023-05-18",
        ),
        "lifecycle": [],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _ixafrica_nbox_source() -> dict[str, Any]:
    post_key = "africa-gap-ixafrica-nbox2-phase2-2026-01-29-captured-2026-07-21"
    specs_key = "africa-gap-ixafrica-campus-specs-captured-2026-07-21"
    evidence = [
        _evidence(
            "ixafrica_nbox",
            key=post_key,
            kind="company_disclosure",
            title="iXAfrica NBOX1 and NBOX2 Phase 2 overview",
            publisher="iXAfrica Data Centre",
            source_family="ixafrica_official_linkedin_updates",
            published_at="2026-01-29",
            excerpt=(
                "iXAfrica labels NBOX1 live and NBOX2 Phase 2, with 18 MW NBOX2 IT-power "
                "design, but gives no NBOX2 physical construction status."
            ),
            metadata={
                "canonical_post_url": (
                    "https://www.linkedin.com/posts/ixafrica-datacentre_kenya-"
                    "digitalinfrastructure-cloud-activity-7422639430353444864-c4QO"
                ),
                "linkedin_activity_id": "7422639430353444864",
                "activity_date_utc": "2026-01-29",
                "capture_surface": "unauthenticated_public_linkedin_embed",
                "nbox1_status_as_reported": "live",
                "nbox2_label_as_reported": "Phase 2",
                "nbox2_it_power_mw_as_reported": 18,
                "nbox2_data_halls_as_reported": 6,
                "nbox2_racks_as_reported": 3_740,
                "campus_pue_as_reported": 1.25,
                "lifecycle_guardrail": (
                    "A phase label and specification list do not establish physical start, "
                    "continuing work, commissioning, completion, or operation for NBOX2."
                ),
                "capacity_guardrail": (
                    "The 18 MW and PUE remain review narrative and are not current load, "
                    "measured performance, energy, or a normalized phase capacity row."
                ),
                "classification_guardrail": (
                    "Carrier-neutral, cloud, high-density, AI-ready, OCI, and liquid-cooling "
                    "wording creates no NBOX2 operating model, workload, tenant, or hardware claim."
                ),
            },
        ),
        _evidence(
            "ixafrica_specs",
            key=specs_key,
            kind="company_disclosure",
            title="iXAfrica campus specifications",
            publisher="iXAfrica Data Centre",
            source_family="ixafrica_current_campus_pages",
            published_at=None,
            excerpt=(
                "The current campus page lists NBOX1.1 live and NBOX1.2 at 18 MW, but "
                "does not establish that the NBOX2 Phase 2 physical build has started."
            ),
            metadata={
                "status_date_basis": "retrieval_date_of_current_operator_page",
                "full_site_it_power_mw_as_reported": 22.5,
                "nbox1_1_it_power_mw_as_reported": 4.5,
                "nbox1_1_status_as_reported": "Live",
                "nbox1_2_it_power_mw_as_reported": 18,
                "identity_guardrail": (
                    "NBOX1.2 on the site page and NBOX2 Phase 2 in the social post are "
                    "not automatically reconciled beyond this source-scoped review record."
                ),
                "current_status_guardrail": (
                    "A current specification page without physical-status wording cannot seed construction."
                ),
            },
        ),
    ]
    campus_key = "curated-review:africa-gap-ixafrica-nbox-nairobi-campus"
    project_key = f"{campus_key}:nbox2-phase-2"
    roles = {"operator": ["iXAfrica Data Centre"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="iXAfrica Nairobi X One Campus (review)",
            country="Kenya",
            address="Mombasa Road, Nairobi, Kenya",
            roles=roles,
            evidence_key=specs_key,
            as_of_date="2026-07-21",
        ),
        "project": _entity(
            stable_key=project_key,
            name="iXAfrica NBOX2 Phase 2 (review only)",
            country="Kenya",
            address="Mombasa Road, Nairobi, Kenya",
            roles=roles,
            evidence_key=post_key,
            as_of_date="2026-01-29",
        ),
        "lifecycle": [],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact five schema-1.1 source documents."""

    builders = (
        _icolo_nbo2_source,
        _telecom_egypt_rdh2_source,
        _teraco_jb7_source,
        _adc_accra_source,
        _ixafrica_nbox_source,
    )
    return {
        name: builder()
        for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for index, name in enumerate(SOURCE_FILENAMES):
        document = documents[name]
        payload = _canonical(document)
        seed_eligible = index < 2
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
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": (
                    "seed_eligible_official_physical_update"
                    if seed_eligible
                    else "review_only_no_current_site_physical_status"
                ),
                "seed_eligible": seed_eligible,
                "seeded": False,
            }
        )
    return records


def _capture_reference(capture_id: str) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    return {
        "source_url": capture["url"],
        "http_status": capture["http_status"],
        "body_bytes": capture["bytes"],
        "body_sha256": capture["sha256"],
    }


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-five-candidate-africa-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 5,
        "seed_eligible_count": 2,
        "review_only_count": 3,
        "candidates": [
            {
                "candidate_id": "icolo-nbo2-karen-nairobi",
                "country": "Kenya",
                "decision": "seed_eligible_first_party_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "iColo directly reports current equipment installation, testing, "
                    "commissioning support, cooling work, and fit-out at NBO2."
                ),
                "lifecycle_disposition": "under_construction as of 2026-04-21",
                "capacity_disposition": "6.5 MW critical IT at design stage only",
                "operating_model_disposition": "generic colocation from carrier-neutral wording",
                "workload_disposition": (
                    "enterprise_it and general_cloud as prospective design/customer intent only"
                ),
                "peeringdb_disposition": {
                    "direct_release_permitted": False,
                    "record_values_released": 0,
                    "placements_created": 0,
                    "address_values_released": 0,
                    "coordinate_values_released": 0,
                    "assessment_status": "blocked_pending_written_permission",
                },
                "coordinate_created": False,
            },
            {
                "candidate_id": "telecom-egypt-rdh2-smart-village",
                "country": "Egypt",
                "decision": "seed_eligible_current_pre_operation_commissioning",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "TAB's June 2026 update directly reports comprehensive system "
                    "commissioning and explicitly says the work occurs before operation."
                ),
                "lifecycle_disposition": "commissioning as of 2026-06-10",
                "capacity_disposition": (
                    "Telecom Egypt 4.6 MW design IT load normalized once; ECG 4.9 MW "
                    "conflict retained without reconciliation"
                ),
                "workload_disposition": (
                    "enterprise_it and general_cloud as operator-stated design intent only"
                ),
                "status_conflict_disposition": (
                    "ECG completed label is contractor project-page context; the later "
                    "TAB source explicitly places facility systems before operation"
                ),
                "coordinate_created": False,
            },
            {
                "candidate_id": "teraco-jb7-isando",
                "country": "South Africa",
                "decision": "review_only_old_start_and_unbound_current_portfolio_aggregate",
                "source_record_created": True,
                "seed_eligible": False,
                "basis": (
                    "Teraco's only site-specific physical statement is the November 2024 "
                    "start. The SEC's current 41 MW under-construction total is portfolio-wide "
                    "and cannot be allocated to JB7."
                ),
                "normalized_observations_created": 0,
                "existing_repo_context": (
                    "A separate historical schema-1.0 JB7 source exists locally but is not "
                    "selected by accepted v79; this review uses collision-free quarantine keys."
                ),
                "negative_source_url_metadata": [
                    {
                        "url": (
                            "https://investor.digitalrealty.com/static-files/"
                            "c48b8fee-1eb8-4830-87b3-6c9d7bdd5396"
                        ),
                        "disposition": (
                            "Stopped unbounded access attempt; failed technical incident only, "
                            "no factual evidence and no source record claim."
                        ),
                    },
                    {
                        "url": (
                            "https://investor.digitalrealty.com/static-files/"
                            "5b81cdae-c126-466c-aba8-1028988f863f"
                        ),
                        "disposition": (
                            "Stopped access attempt; referenced material belongs to the 2022 "
                            "Teraco acquisition context, not a 2026 JB7 physical update. URL "
                            "metadata only and no factual-evidence record."
                        ),
                    },
                ],
            },
            {
                "candidate_id": "africa-data-centres-accra-trade-fair",
                "country": "Ghana",
                "decision": "review_only_no_2026_site_specific_physical_continuation",
                "source_record_created": True,
                "seed_eligible": False,
                "basis": (
                    "The operator supplied future-start and financing intent in 2023, and "
                    "secondary reporting described a 2024 delay. No selected 2026 source "
                    "establishes current site work."
                ),
                "normalized_observations_created": 0,
                "capacity_disposition": "10 MW initial and possible 30 MW remain review narrative",
                "unrecovered_source_disposition": (
                    "No exact contractor/FY2025 source was recovered; none is invented or used."
                ),
            },
            {
                "candidate_id": "ixafrica-nbox2-phase-2",
                "country": "Kenya",
                "decision": "review_only_phase_and_specs_without_physical_status",
                "source_record_created": True,
                "seed_eligible": False,
                "basis": (
                    "The operator labels NBOX2 Phase 2 and reports specifications, but neither "
                    "selected source textually establishes a physical construction start or continuation."
                ),
                "normalized_observations_created": 0,
                "capacity_disposition": "18 MW IT and PUE 1.25 remain review narrative",
                "identity_disposition": (
                    "NBOX1.2 and NBOX2 Phase 2 are not automatically merged outside this "
                    "source-scoped quarantine record."
                ),
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    selected = [
        {
            "capture_id": capture_id,
            "requested_url": spec["url"],
            "effective_url": spec["url"],
            "retrieved_at": spec["retrieved_at"],
            "http_status": spec["http_status"],
            "content_type": spec["content_type"],
            "body": {
                "path": spec["filename"],
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "capture_method": "credential_free_curl_location_compressed",
            "request_credentials_supplied": False,
            "used_for_normalized_claims": spec["used_for_normalized_claims"],
        }
        for capture_id, spec in sorted(CAPTURES.items())
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public HTTP GETs. Successful response bodies, headers, facts, "
            "404 bodies, and stopped-attempt empty metadata files are retained privately."
        ),
        "successful_http_200_requests": 21,
        "http_404_requests": 2,
        "stopped_or_no_http_status_requests": 3,
        "selected_capture_records": len(CAPTURES),
        "source_evidence_body_captures": 12,
        "normalized_claim_body_captures": 4,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "selected_captures": selected,
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "technical_incidents": [
            {
                "source_url": (
                    "https://investor.digitalrealty.com/static-files/"
                    "c48b8fee-1eb8-4830-87b3-6c9d7bdd5396"
                ),
                "result": "unbounded request stopped externally; no completed HTTP facts",
                "private_files": [
                    "digital_realty_2026_supplement.facts",
                    "digital_realty_2026_supplement.headers",
                    "dlr_test.body",
                ],
                "used_for_claims": False,
            },
            {
                "source_url": (
                    "https://investor.digitalrealty.com/static-files/"
                    "5b81cdae-c126-466c-aba8-1028988f863f"
                ),
                "result": "unbounded request stopped externally; no completed HTTP facts",
                "private_files": [
                    "digital_realty_2022_acquisition.facts",
                    "digital_realty_2022_acquisition.headers",
                ],
                "used_for_claims": False,
            },
            {
                "source_url": (
                    "https://s29.q4cdn.com/106493612/files/doc_presentation/2022/01/01/"
                    "Digital-Realty-to-Acquire-Teraco-Presentation-FINAL.pdf"
                ),
                "result": "HTTP 404 fallback response",
                "used_for_claims": False,
            },
            {
                "source_url": (
                    "https://www.ecgsa.com/app/uploads/2024/12/"
                    "1767001842_914_136304_3288.pdf"
                ),
                "result": "HTTP 404 response",
                "used_for_claims": False,
            },
        ],
        "rights_incidents": [
            {
                "source_url": "https://www.peeringdb.com/api/fac/14166",
                "http_status": 200,
                "anonymous_access": True,
                "direct_release_permitted": False,
                "record_values_released": 0,
                "placements_created": 0,
                "private_body_moved_to_trash": True,
                "assessment_path": (
                    "source_assessments/peeringdb-2026-07-18-v1/assessment.json"
                ),
                "assessment_sha256": PEERINGDB_ASSESSMENT_PIN[1],
            }
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build Africa gap assessment

This immutable artifact records five official-source candidate dispositions researched on 2026-07-21. iColo NBO2 and Telecom Egypt RDH2 pass the current physical-status boundary. Their lifecycle rows are dated last-observed facts, never timeless current claims.

NBO2 is under construction as of 2026-04-21. Its 6.5 MW is design critical IT only. Carrier-neutral wording supports generic colocation; enterprise and cloud rows are prospective customer/design intent, not active load, tenants, users, or installed hardware. PeeringDB contributes only URL/hash/access/rights metadata. The repository's fail-closed assessment prohibits direct record release pending written permission, so no PeeringDB identity, address, coordinate, or placement is published.

RDH2 is in pre-operation commissioning as of 2026-06-10. Telecom Egypt's 4.6 MW design IT figure is normalized once; ECG's conflicting 4.9 MW remains narrative and is not averaged or reconciled. ECG's completed label is contractor project-page context, while the later TAB source explicitly describes commissioning before operation.

JB7 is review-only: its site-specific start is from 2024, and the SEC's 41 MW under-construction figure is a Teraco portfolio aggregate with no JB7 binding. The stopped Digital Realty static-file requests are technical incidents and URL metadata only. Accra remains review-only because 2023 intent and 2024 delay reporting lack a 2026 physical continuation. NBOX2 remains review-only because phase and specification language does not establish physical construction.

No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation asserts identity, lifecycle, capacity, type, roles, or workload. No energy-consumption or PUE row is created.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. Accepted open seed v79 and every downstream artifact remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete {CAPTURE_FILE_COUNT}-file directory was moved intact to the recoverable Trash path recorded in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 5,
            "source_records": 5,
            "seed_eligible_source_records": 2,
            "review_only_candidates": 3,
            "review_only_source_records": 3,
            "distinct_campuses": 5,
            "projects": 5,
            "entity_snapshots": 10,
            "unique_evidence_records": 12,
            "lifecycle_observations": 2,
            "operating_model_observations": 1,
            "workload_observations": 4,
            "capacity_estimates": 2,
            "coordinates_present": 0,
            "geometry_present": 0,
            "peeringdb_placements": 0,
            "energy_consumption_observations": 0,
            "pue_observations": 0,
        },
        "frozen_v79_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v79.json",
                "bytes": V79_PINS[V79_DEFINITION][0],
                "sha256": V79_PINS[V79_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v79/manifest.json",
                "bytes": V79_PINS[V79_MANIFEST][0],
                "sha256": V79_PINS[V79_MANIFEST][1],
            },
            "release_entities": {
                "path": "releases/2026-07-21-open-seed-v79/entities.csv",
                "bytes": V79_PINS[V79_ENTITIES][0],
                "sha256": V79_PINS[V79_ENTITIES][1],
            },
            "release_evidence": {
                "path": "releases/2026-07-21-open-seed-v79/evidence.csv",
                "bytes": V79_PINS[V79_EVIDENCE][0],
                "sha256": V79_PINS[V79_EVIDENCE][1],
            },
            "release_tree_sha256": V79_TREE_SHA256,
            "v79_selected_input_count": V79_INPUT_COUNT,
            "new_source_paths_selected_by_v79": False,
            "new_stable_keys_present_in_v79": False,
            "new_source_urls_present_in_v79": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "peeringdb_rights_witness": {
            "assessment_path": (
                "source_assessments/peeringdb-2026-07-18-v1/assessment.json"
            ),
            "assessment_bytes": PEERINGDB_ASSESSMENT_PIN[0],
            "assessment_sha256": PEERINGDB_ASSESSMENT_PIN[1],
            "direct_release_permitted": False,
            "record_values_released": 0,
            "placements_created": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v79_mutated": False,
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
        "peeringdb_direct_release_permitted": False,
        "peeringdb_record_values_released": 0,
        "peeringdb_placements_created": 0,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "candidate_dispositions": {"seed_eligible": 2, "review_only": 3},
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
        "candidate_assessments": 5,
        "curated_source_records": 5,
        "seed_eligible_source_records": 2,
        "review_only_candidates": 3,
        "review_only_source_records": 3,
        "successful_http_200_requests": 21,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "peeringdb_direct_release_permitted": False,
        "peeringdb_record_values_released": 0,
        "peeringdb_placements_created": 0,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "downstream_product_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise OfficialAfricaGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialAfricaGapError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialAfricaGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise OfficialAfricaGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity]["coordinates"] is not None
        or document[entity]["geometry"] is not None
        for document in documents
        for entity in ("campus", "project")
    ):
        raise OfficialAfricaGapError("source invented coordinates or geometry")
    if len(documents[0]["operating_models"]) != 1 or any(
        document["operating_models"] for document in documents[1:]
    ):
        raise OfficialAfricaGapError("operating-model boundary differs")
    if [len(document["workloads"]) for document in documents] != [2, 2, 0, 0, 0]:
        raise OfficialAfricaGapError("workload boundary differs")
    if [len(document["capacities"]) for document in documents] != [1, 1, 0, 0, 0]:
        raise OfficialAfricaGapError("capacity boundary differs")
    if [len(document["lifecycle"]) for document in documents] != [1, 1, 0, 0, 0]:
        raise OfficialAfricaGapError("lifecycle boundary differs")
    peering_metadata = documents[0]["evidence"][2]["metadata"]
    if (
        peering_metadata.get("direct_release_permitted") is not False
        or peering_metadata.get("record_values_released") != 0
        or peering_metadata.get("placement_rows_created") != 0
        or peering_metadata.get("address_values_released") != 0
        or peering_metadata.get("coordinate_values_released") != 0
    ):
        raise OfficialAfricaGapError("PeeringDB fail-closed boundary differs")
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
    if len(stable_keys) != 10 or len(evidence_keys) != 12:
        raise OfficialAfricaGapError("planned source keys are not unique")
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
        raise OfficialAfricaGapError(f"curated source collision: {collisions!r}")


def _validate_v79_nonmutation() -> None:
    for source, pin in V79_PINS.items():
        _pin(source, pin)
    if tree_digest(V79_RELEASE) != V79_TREE_SHA256:
        raise OfficialAfricaGapError("accepted v79 release tree differs")
    definition = json.loads(V79_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V79_INPUT_COUNT:
        raise OfficialAfricaGapError("accepted v79 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialAfricaGapError("v79 unexpectedly selects a new source path")
    documents = expected_source_documents()
    entities_text = V79_ENTITIES.read_text(encoding="utf-8")
    evidence_text = V79_EVIDENCE.read_text(encoding="utf-8")
    for document in documents.values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialAfricaGapError("new stable key is present in v79")
        for evidence in document["evidence"]:
            if evidence["key"] in evidence_text:
                raise OfficialAfricaGapError("new evidence key is present in v79")
            if evidence["source_url"] in evidence_text:
                raise OfficialAfricaGapError("new source URL is present in v79")
    metadata_only_urls = {capture["url"] for capture in CAPTURES.values()} | {
        "https://investor.digitalrealty.com/static-files/c48b8fee-1eb8-4830-87b3-6c9d7bdd5396",
        "https://investor.digitalrealty.com/static-files/5b81cdae-c126-466c-aba8-1028988f863f",
    }
    if any(url in evidence_text for url in metadata_only_urls):
        raise OfficialAfricaGapError("new metadata-only URL is present in v79")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialAfricaGapError(
            f"capture directory is absent or unsafe: {directory}"
        )
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialAfricaGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialAfricaGapError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialAfricaGapError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialAfricaGapError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialAfricaGapError("capture directory closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
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
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 12,
            "lifecycle_observations": 2,
            "operating_model_observations": 1,
            "workload_observations": 4,
            "capacity_estimates": 2,
        }
        if counts != expected:
            raise OfficialAfricaGapError(f"offline import counts differ: {counts!r}")
        capacities = connection.execute(
            "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
            "FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id "
            "ORDER BY e.stable_key"
        ).fetchall()
        expected_capacities = [
            (
                "curated:icolo-nbo2-karen-nairobi-campus:initial-build",
                "critical_it_mw",
                "design",
                "MW",
                6.5,
            ),
            (
                "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2",
                "critical_it_mw",
                "design",
                "MW",
                4.6,
            ),
        ]
        if [tuple(row) for row in capacities] != expected_capacities:
            raise OfficialAfricaGapError(
                f"offline capacity rows differ: {[tuple(row) for row in capacities]!r}"
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
    _pin(PEERINGDB_ASSESSMENT, PEERINGDB_ASSESSMENT_PIN)
    if path.is_symlink() or not path.is_dir():
        raise OfficialAfricaGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialAfricaGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialAfricaGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialAfricaGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialAfricaGapError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialAfricaGapError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 5
        or manifest.get("curated_source_records") != 5
        or manifest.get("seed_eligible_source_records") != 2
        or manifest.get("review_only_candidates") != 3
        or manifest.get("review_only_source_records") != 3
        or manifest.get("peeringdb_direct_release_permitted") is not False
        or manifest.get("peeringdb_record_values_released") != 0
        or manifest.get("peeringdb_placements_created") != 0
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialAfricaGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialAfricaGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialAfricaGapError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialAfricaGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialAfricaGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialAfricaGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialAfricaGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialAfricaGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialAfricaGapError("capture retrieval post-dates recorded_at")
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
        raise OfficialAfricaGapError(
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
        raise OfficialAfricaGapError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-africa-gap.", dir=SOURCES_ROOT)
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
            _all_stage_paths(source_stage, artifact_stage), target
        )
        if datetime.now(UTC) >= target:
            raise OfficialAfricaGapError(
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
                _discard_owned_directory(artifact_stage, artifact_identity, members)
            if source_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
                _discard_owned_directory(source_stage, source_stage_identity, members)
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
                raise OfficialAfricaGapError(
                    f"source identity changed on promotion: {name}"
                )
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append(
            (prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True)
        )
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialAfricaGapError("artifact identity changed on promotion")
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
        raise OfficialAfricaGapError("both capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(CAPTURE_TRASH)


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish five source records and the bounded Africa gap assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v79_nonmutation()
    _pin(PEERINGDB_ASSESSMENT, PEERINGDB_ASSESSMENT_PIN)
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
    _validate_v79_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "manifest_logical_tree_sha256": manifest["tree_sha256"],
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 5,
            "source_records": 5,
            "seed_eligible": 2,
            "review_only": 3,
            "review_only_source_records": 3,
            "evidence": 12,
            "entities": 10,
            "entity_snapshots": 10,
            "lifecycle": 2,
            "operating_models": 1,
            "workloads": 4,
            "capacities": 2,
            "coordinates": 0,
            "geometry": 0,
            "peeringdb_placements": 0,
            "energy_consumption": 0,
            "pue": 0,
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
