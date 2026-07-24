"""Immutable v2-successor construction timeline derived from open seed v67.

The bundle preserves every accepted v2 flat observation and entity-timeline
row exactly, then appends all twenty-nine post-v62 lifecycle observations in
two separately pinned partitions: fourteen intermediate-seed rows and fifteen
rows for the fourteen project identities first selected by open seed v67.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from . import construction_timeline_v2 as v2
from . import open_seed_v67
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]

TIMELINE_ID = "2026-07-21-public-open-v3"
AS_OF = "2026-07-21"
GENERATED_AT = "2026-07-21T07:52:10Z"

OPEN_SEED_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
OPEN_SEED_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"
OPEN_SEED_CORE = ROOT / "datacenter_atlas/open_seed_v67.py"
OPEN_SEED_DEFINITION_SHA256 = (
    "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb"
)
OPEN_SEED_TREE_SHA256 = (
    "fb4a8016c3c0c143cef2e5ac35d0787bb2b0dbd45115e27a83a70167ccb0b4fb"
)
OPEN_SEED_CORE_SHA256 = (
    "3bdba3404182bed32f5491826d027344d2b9d4cea01ef9670cb8ffa44bc67259"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-20-public-open-v2.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v2"
PREDECESSOR_CORE = ROOT / "datacenter_atlas/construction_timeline_v2.py"
PREDECESSOR_DEFINITION_SHA256 = (
    "ca48de509f23a0ba0b856bab8815a1872594840e0a83cf9dba09c37133b5909a"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "ab8e798b1b0d2d25ec43744e935565603f8ce138d7d820038ad838702b3b28a7"
)
PREDECESSOR_TREE_SHA256 = (
    "c0e0db549f8336c012da31a997797814b368b87bae4c42a6173597e920e6b8e3"
)
PREDECESSOR_CORE_SHA256 = (
    "6950de8cd16d141cefecb95ef20c3535d346207f98768bd3925b427b4dc412ff"
)

DEFINITION_FORMAT = "datacenter-atlas-construction-timeline-definition-v3"
BUNDLE_FORMAT = "datacenter-atlas-construction-timeline-bundle-v3"
COVERAGE_FORMAT = "datacenter-atlas-construction-timeline-coverage-v3"
SCHEMA_VERSION = 3

# Entity rows retain the accepted v2 carrier schema so every inherited JSONL
# line is byte-identical.  Bundle, definition, and coverage schemas advance.
TIMELINE_FORMAT = v2.TIMELINE_FORMAT
TIMELINE_SCHEMA_VERSION = v2.SCHEMA_VERSION

OBSERVATIONS_FILENAME = v2.OBSERVATIONS_FILENAME
TIMELINES_FILENAME = v2.TIMELINES_FILENAME
COVERAGE_FILENAME = v2.COVERAGE_FILENAME
README_FILENAME = v2.README_FILENAME
ATTRIBUTION_FILENAME = v2.ATTRIBUTION_FILENAME
MANIFEST_FILENAME = v2.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = v2.MANIFEST_HASH_FILENAME
BUNDLE_FILES = v2.BUNDLE_FILES
OBSERVATION_FIELDS = v2.OBSERVATION_FIELDS
FROZEN_DIRECTORY_MODE = v2.FROZEN_DIRECTORY_MODE
FROZEN_FILE_MODE = v2.FROZEN_FILE_MODE

SCOPE = {
    **v2.SCOPE,
    "latest_status_semantics": "last_observed",
    "permit_or_forecast_promoted_to_physical_construction": False,
}

EXPECTED_COUNTS = {
    "entities_with_lifecycle_observations": 443,
    "multi_observation_entities": 16,
    "raw_lifecycle_observations": 459,
    "repeated_status_multi_observation_entities": 4,
    "single_observation_entities": 427,
    "single_old_observation_entities": 26,
    "source_families": 197,
    "status_changing_multi_observation_entities": 12,
}

FULL_V67_RAW_OBSERVATIONS = 459
PREDECESSOR_OBSERVATIONS = 430
PREDECESSOR_TIMELINES = 415
POST_V62_ADDED_PROJECTS = 28
POST_V62_ADDED_OBSERVATIONS = 29
INTERMEDIATE_ADDED_PROJECTS = 14
INTERMEDIATE_ADDED_OBSERVATIONS = 14
NEW_TRANCHE_ADDED_PROJECTS = 14
NEW_TRANCHE_ADDED_OBSERVATIONS = 15
V67_RECORDED_AT_REWRITES_IGNORED = 46

NEW_TRANCHE_PROJECT_SOURCE_BY_KEY = {
    "curated:alps-middle-east-duqm-data-center:initial-80mw-build": (
        "sources/curated-official-2026-07-20-alps-duqm-under-construction.json"
    ),
    "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre:phase-1": (
        "sources/curated-official-2026-07-20-aurora-core-mikkeli-phase-1.json"
    ),
    "curated:capitaland-dc-chennai-ambattur:current-facility-build": (
        "sources/curated-official-2026-07-20-capitaland-chennai-ambattur.json"
    ),
    "curated:capitaland-dc-navi-mumbai-campus:tower-2": (
        "sources/curated-official-2026-07-20-capitaland-navi-mumbai-tower-2.json"
    ),
    "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase": (
        "sources/curated-official-2026-07-20-datavolt-riyadh-first-phase.json"
    ),
    "curated:datavolt-tashkent-green-data-center:current-facility-build": (
        "sources/curated-official-2026-07-20-datavolt-tashkent-green-data-center.json"
    ),
    "curated:datavolt-yanbu-4mw-facility:first-phase": (
        "sources/curated-official-2026-07-20-datavolt-yanbu-first-phase.json"
    ),
    "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build": (
        "sources/curated-official-2026-07-20-dci-koramco-ansan-sel02.json"
    ),
    "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2": (
        "sources/curated-official-2026-07-20-digital-edge-sel3-bupyeong.json"
    ),
    "curated:microsoft-kemps-creek-data-centre:syd06-building-two": (
        "sources/curated-official-2026-07-20-microsoft-kemps-creek-syd06-building-two.json"
    ),
    "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build": (
        "sources/curated-official-2026-07-20-sify-bengaluru-02-current-build.json"
    ),
    "curated:sk-ai-data-center-ulsan-campus:current-facility-build": (
        "sources/curated-official-2026-07-20-sk-ai-data-center-ulsan.json"
    ),
    "curated:smplus-smx01-jakarta-cbd:initial-18mw-build": (
        "sources/curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json"
    ),
    "curated:stt-johor-data-centre-campus:stt-johor-1": (
        "sources/curated-official-2026-07-20-stt-johor-1-current-build.json"
    ),
}

INTERMEDIATE_PROJECT_SOURCE_BY_KEY = {
    "curated:cdc-beard-campus:be1-current-build": (
        "sources/curated-official-2026-07-20-cdc-beard-be1.json"
    ),
    "curated:core-scientific-dalton-4-data-center-campus:greenfield-build": (
        "sources/curated-official-2026-07-20-core-scientific-dalton-4-v2.json"
    ),
    "curated:databank-culpeper-campus:iad6-current-build": (
        "sources/curated-official-2026-07-20-databank-iad6-culpeper.json"
    ),
    "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build": (
        "sources/curated-official-2026-07-20-digital-realty-vie13-phase-1.json"
    ),
    "curated:ecodatacenter-2-borlange-data-center-campus:data-center-b1-current-build": (
        "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json"
    ),
    "curated:ecodatacenter-2-borlange-data-center-campus:data-center-b2-current-build": (
        "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json"
    ),
    "curated:ecodatacenter-falun-data-center-campus:data-center-e-current-build": (
        "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json"
    ),
    "curated:ecodatacenter-falun-data-center-campus:data-center-f-current-build": (
        "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json"
    ),
    "curated:esr-bupyeong-kr1-data-centre:core-shell-building-construction": (
        "sources/curated-official-2026-07-20-esr-bupyeong-kr1.json"
    ),
    "curated:esr-kwai-chung-hk1-data-centre:phase-2-conversion": (
        "sources/curated-official-2026-07-20-esr-kwai-chung-hk1-phase-2.json"
    ),
    "curated:lancium-clean-campus-abilene-ai-data-center:remaining-six-building-expansion": (
        "sources/curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json"
    ),
    "curated:powerhouse-irving-data-center-campus:building-1-current-build": (
        "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout-v2.json"
    ),
    "curated:qts-fayetteville-georgia-data-center-campus:active-campus-construction-program": (
        "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json"
    ),
    "curated:teraco-ct1-rondebosch-data-centre:current-expansion": (
        "sources/curated-official-2026-07-20-teraco-ct1-rondebosch-expansion.json"
    ),
}

PROJECT_SOURCE_BY_KEY = {
    **INTERMEDIATE_PROJECT_SOURCE_BY_KEY,
    **NEW_TRANCHE_PROJECT_SOURCE_BY_KEY,
}

EVENT_CONTRACT_FIELDS = (
    "source_path",
    "entity_stable_key",
    "observation_id",
    "observed_date",
    "status",
    "method",
    "evidence_id",
    "evidence_source_family",
    "evidence_retrieved_at",
    "evidence_content_hash",
    "observation_age_days",
    "freshness_class",
)

V67_NEW_TRANCHE_EVENT_CONTRACT = (
    ("sources/curated-official-2026-07-20-alps-duqm-under-construction.json", "curated:alps-middle-east-duqm-data-center:initial-80mw-build", "376d7369-4d51-5d5e-90ae-29e8b16452cb", "2026-07-21", "under_construction", "authoritative_physical_status_update", "9a176ce0-a8d8-5ac9-bee0-4b0269217cef", "alps_middle_east_live_site_pages", "2026-07-21T07:04:54Z", "533504bf5bce2be158099bb65d110abb68d2e5cdaf823bf483094b20a4ea554a", 0, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-aurora-core-mikkeli-phase-1.json", "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre:phase-1", "6c0edef7-2ee1-5021-bd2e-b1ed8bcf6d70", "2026-04-06", "civil_works", "authoritative_physical_status_update", "02d55210-deb1-5dcd-9eea-c04b88e93e05", "three_e_network_investor_relations", "2026-07-21T07:03:17Z", "c7363b3f038aa3d459fafb51e61995d6bde0efedae99fb6ea45aa9d3433050d4", 106, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-capitaland-chennai-ambattur.json", "curated:capitaland-dc-chennai-ambattur:current-facility-build", "b3eb16d6-f2ee-51f9-ba68-0ea6309bb761", "2025-12-31", "under_construction", "authoritative_physical_status_update", "79c00d39-f1a1-5d47-8941-7c759281e18c", "capitaland_india_trust_financial_results", "2026-07-21T07:01:32Z", "d7676b244b41c82c80790b256a33d0eb7d866025bca86b93d5ce3714c0c6113a", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-capitaland-navi-mumbai-tower-2.json", "curated:capitaland-dc-navi-mumbai-campus:tower-2", "9ad133a8-c83f-59ae-a0bf-e6888ee25589", "2025-12-31", "under_construction", "authoritative_physical_status_update", "79c00d39-f1a1-5d47-8941-7c759281e18c", "capitaland_india_trust_financial_results", "2026-07-21T07:01:32Z", "d7676b244b41c82c80790b256a33d0eb7d866025bca86b93d5ce3714c0c6113a", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-datavolt-riyadh-first-phase.json", "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase", "73c959d7-ce9e-5794-82d5-7ef7f2b52eee", "2025-12-31", "under_construction", "authoritative_construction_start", "3f39fc45-0c8c-5bba-9125-fa8dceede4b8", "datavolt_linkedin_public_post", "2026-07-21T07:01:32Z", "2f061445001f5f30e85c87d48776996c8a6dd38f5b2674948d6d726805ff661e", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-datavolt-tashkent-green-data-center.json", "curated:datavolt-tashkent-green-data-center:current-facility-build", "8afa6f52-c3f8-5058-8562-8b91cba6bc95", "2025-12-31", "under_construction", "authoritative_physical_status_update", "3f39fc45-0c8c-5bba-9125-fa8dceede4b8", "datavolt_linkedin_public_post", "2026-07-21T07:01:32Z", "2f061445001f5f30e85c87d48776996c8a6dd38f5b2674948d6d726805ff661e", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-datavolt-yanbu-first-phase.json", "curated:datavolt-yanbu-4mw-facility:first-phase", "be97a9aa-dde0-565d-8cd3-6e64bf84e84d", "2025-12-31", "under_construction", "authoritative_construction_start", "3f39fc45-0c8c-5bba-9125-fa8dceede4b8", "datavolt_linkedin_public_post", "2026-07-21T07:01:32Z", "2f061445001f5f30e85c87d48776996c8a6dd38f5b2674948d6d726805ff661e", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-dci-koramco-ansan-sel02.json", "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build", "0c3d2bc8-a3f2-54db-97ca-2279249abfdd", "2026-06-09", "under_construction", "authoritative_construction_start", "f01c66c1-0b93-5777-8a07-464c5aba3146", "koramco_media_news_listing", "2026-07-21T07:01:32Z", "22166617d13cba0149f61c60e8124e3be4ae0b306ee8237795773f697a8609b7", 42, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-digital-edge-sel3-bupyeong.json", "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2", "0736c86c-3724-5838-8acf-97a87f5b0a22", "2026-07-09", "under_construction", "authoritative_physical_status_update", "4319b4ff-25cd-51ce-bf9b-e17197ff1fbf", "sk_ecoplant_newsroom", "2026-07-21T07:02:22Z", "a86acc48fadb7fe6143016fd05e4af6aaf18e624cc4ca6f4ecae4b03a7f69b9a", 12, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-microsoft-kemps-creek-syd06-building-two.json", "curated:microsoft-kemps-creek-data-centre:syd06-building-two", "49353f00-cd78-51a1-b5e0-60bf94236a0f", "2026-05-01", "under_construction", "authoritative_physical_status_update", "fc7d93ba-644a-5652-a4c3-790cd22dbfbc", "microsoft_local_project_updates", "2026-07-21T07:03:14Z", "d7b5c4472533b0a3c96ab1e7746d0164e7dd086abc84e59996f3d65b2ca1ed15", 81, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-sify-bengaluru-02-current-build.json", "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build", "2b09f44b-1cb1-5ae6-bd28-4929cf25a1e4", "2025-05-14", "under_construction", "authoritative_construction_start", "17b61546-81a2-5875-80ec-1dc8f489306c", "sify_technologies_events", "2026-07-21T07:01:32Z", "bcdbf55a64b59e0ba745bc38b1e20ce54e94c20b06a2ca168d07c21d6f2aa207", 433, "stale_over_365_days"),
    ("sources/curated-official-2026-07-20-sk-ai-data-center-ulsan.json", "curated:sk-ai-data-center-ulsan-campus:current-facility-build", "ab57362a-08a3-5194-883c-56e774286062", "2026-07-05", "under_construction", "authoritative_physical_status_update", "b1a1555e-965b-5796-897e-8e49a00ee7aa", "sk_telecom_newsroom", "2026-07-21T07:01:31Z", "fd097e1b482707dc6b2f29ba109efa4f29435e9d7196aae5c03549ae92ba8210", 16, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json", "curated:smplus-smx01-jakarta-cbd:initial-18mw-build", "bfd5ef5d-9f7b-5803-acfc-cd3cb3864570", "2025-03-06", "under_construction", "authoritative_construction_start", "1d579fc1-25f9-59d5-93e2-f8a305a6b13e", "dssa_press_releases", "2026-07-21T07:02:30Z", "f397bcdb40125d54caff63894c46c9b2b55c8a624f7126edb34d4a74a2e5bc58", 502, "stale_over_365_days"),
    ("sources/curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json", "curated:smplus-smx01-jakarta-cbd:initial-18mw-build", "0a955b0c-9145-5257-ae8a-001c5cc35fd5", "2026-05-08", "shell", "authoritative_physical_status_update", "1cc28b43-7d17-545a-88f0-2bfd57996787", "smplus_newsroom", "2026-07-21T07:02:25Z", "d77fc16023e1bf7708df90c9b6dd0c2d3a4bfe7c80f1429f7fae5fa991b5f96d", 74, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-stt-johor-1-current-build.json", "curated:stt-johor-data-centre-campus:stt-johor-1", "6792e3b7-da91-5659-9877-5a4aa0a09fc0", "2025-02-24", "under_construction", "authoritative_construction_start", "e06facd1-6479-5dd2-ba55-bf44666cadf1", "stt_gdc_company_news", "2026-07-21T02:07:06Z", "732bf280c6d94daaa3afd0b9cb7875bc40737296109f39786a5cd8620b055ceb", 512, "stale_over_365_days"),
)

V67_INTERMEDIATE_EVENT_CONTRACT = (
    ("sources/curated-official-2026-07-20-cdc-beard-be1.json", "curated:cdc-beard-campus:be1-current-build", "653d8cae-28a2-5665-b418-701ae6b0d57a", "2026-07-20", "under_construction", "authoritative_physical_status_update", "c6cc7f23-5fd6-5f6a-9efb-af631204f5c3", "cdc_data_centres_location_pages", "2026-07-21T05:32:34Z", "2ed5c67bfe164a1941dcbc6425cb3610afc60ddba5525bd487fd720821468eed", 1, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-core-scientific-dalton-4-v2.json", "curated:core-scientific-dalton-4-data-center-campus:greenfield-build", "2f256201-e738-5575-a009-d2e5076b19bf", "2026-05-06", "under_construction", "authoritative_physical_status_update", "feba9c75-c868-540c-a777-9f25c45ec8e5", "core_scientific_sec_exhibits", "2026-07-21T04:40:54Z", "59d88adc09a5bac6e2bc5f8a9cd86f4e29ceb71718bbd3e1b8bcf1e68bc69dc9", 76, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-databank-iad6-culpeper.json", "curated:databank-culpeper-campus:iad6-current-build", "8f313286-67f2-5112-8906-977ac03c23dc", "2026-02-19", "under_construction", "authoritative_physical_status_update", "decb8792-512d-5f29-87df-e5a6142d745b", "databank_official_linkedin", "2026-07-21T04:36:19Z", "8e31aba45178e81c547545bed4b12e6024c10baf71dd1bbb6cd05d1ab66ea8ee", 152, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-digital-realty-vie13-phase-1.json", "curated:digital-realty-vienna-vie13-vie16-expansion:vie13-phase-1-current-build", "f9792639-4f30-599b-bc7d-cdf535282769", "2026-06-18", "under_construction", "authoritative_physical_status_update", "9ef151e3-b5f8-5421-b9df-f5ac0bfca4a6", "digital_realty_company_linkedin", "2026-07-21T05:43:03Z", "f4840f3349c84440e0664b1ccf2a4a9ce224611b466afcffaeea1363b166824b", 33, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json", "curated:ecodatacenter-2-borlange-data-center-campus:data-center-b1-current-build", "09bc0f73-29b9-515b-a19d-de52a4e42626", "2025-12-31", "under_construction", "authoritative_construction_start", "8b3dcad1-06da-5c64-b620-6f345538b455", "ecodatacenter_financial_reports", "2026-07-21T04:51:37Z", "3f2a1140583ff741dc67cd6b17f9b7c9fbebb347b0ca6bc67622d2a1f3caaacd", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json", "curated:ecodatacenter-2-borlange-data-center-campus:data-center-b2-current-build", "24691958-43df-5024-a519-2ffb8a22e82b", "2025-12-31", "under_construction", "authoritative_construction_start", "8b3dcad1-06da-5c64-b620-6f345538b455", "ecodatacenter_financial_reports", "2026-07-21T04:51:37Z", "3f2a1140583ff741dc67cd6b17f9b7c9fbebb347b0ca6bc67622d2a1f3caaacd", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json", "curated:ecodatacenter-falun-data-center-campus:data-center-e-current-build", "97b7dd71-58f9-53d3-9ed1-2080ed56904f", "2025-12-31", "under_construction", "authoritative_construction_start", "d360cd57-c0a5-507a-950a-5a21dd8c9301", "ecodatacenter_financial_reports", "2026-07-21T04:51:37Z", "3f2a1140583ff741dc67cd6b17f9b7c9fbebb347b0ca6bc67622d2a1f3caaacd", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json", "curated:ecodatacenter-falun-data-center-campus:data-center-f-current-build", "913ed157-3dda-5e54-950e-e8e00f40e6f0", "2025-12-31", "under_construction", "authoritative_construction_start", "d360cd57-c0a5-507a-950a-5a21dd8c9301", "ecodatacenter_financial_reports", "2026-07-21T04:51:37Z", "3f2a1140583ff741dc67cd6b17f9b7c9fbebb347b0ca6bc67622d2a1f3caaacd", 202, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-esr-bupyeong-kr1.json", "curated:esr-bupyeong-kr1-data-centre:core-shell-building-construction", "2bdfee8b-7b59-57d2-b8bc-59da4f5936a6", "2025-11-20", "under_construction", "authoritative_physical_status_update", "1c0b89f0-2a74-5ec8-81b4-055a722b31aa", "esr_data_centre_portfolio", "2026-07-21T05:03:04Z", "ffb42ab037b99f2c4b2e75ebadca3c98a169b265d6cf1827f16e3220da517b1b", 243, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-esr-kwai-chung-hk1-phase-2.json", "curated:esr-kwai-chung-hk1-data-centre:phase-2-conversion", "ce3f7dcb-96e9-5d55-83c2-a29d9b427183", "2026-03-27", "under_construction", "authoritative_physical_status_update", "93834bcf-1ff7-503a-8d89-7182fe1892dc", "esr_linkedin", "2026-07-21T05:19:22Z", "74b8784d211d41d933e4bc1e48836db9549f004aa8590c51c91121174abbc2d1", 116, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json", "curated:lancium-clean-campus-abilene-ai-data-center:remaining-six-building-expansion", "6ab94474-f3c5-542b-90fa-4cd0326ee19d", "2026-06-04", "under_construction", "authoritative_physical_status_update", "c721a602-e557-5a4d-8518-d5fce69a64d2", "oracle_data_center_pages", "2026-07-21T06:07:08Z", "3222773fcc16f4415692dd48c2254c15b00ea3bd5c5e4a1d4988a7a977b05e91", 47, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout-v2.json", "curated:powerhouse-irving-data-center-campus:building-1-current-build", "092dd7b7-2e2d-5bec-9908-0a741c5ac2b9", "2026-03-27", "shell", "authoritative_physical_status_update", "2250dd31-c3fb-500c-a488-f84c2e4cfca3", "powerhouse_data_centers_linkedin_company_posts", "2026-07-21T04:38:25Z", "590313c03194a2d12d7451932a15835fd4298962e0acf0c5e40cdc3d9cb64bc4", 116, "aging_91_365_days"),
    ("sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json", "curated:qts-fayetteville-georgia-data-center-campus:active-campus-construction-program", "50afc0b3-e93b-5dc8-942c-9c224ab62135", "2026-05-13", "under_construction", "authoritative_physical_status_update", "1b426878-bd82-5001-be4e-125348a289e0", "fayette_county_georgia_board_minutes", "2026-07-21T04:49:21Z", "f5500b24a646524e8a3c939c1868071a482cc7fce595ece10182dd2875bfe9bd", 69, "recent_0_90_days"),
    ("sources/curated-official-2026-07-20-teraco-ct1-rondebosch-expansion.json", "curated:teraco-ct1-rondebosch-data-centre:current-expansion", "f57aa8db-485f-57af-91d3-a45bef324d8a", "2026-07-17", "under_construction", "authoritative_physical_status_update", "d54597bf-8089-5001-969c-0357d6218721", "teraco_newsroom", "2026-07-21T05:27:43Z", "7a0daa8edc0c82b8c876250b187cbb0acbbe8e9c766080d868227d6660c8161e", 4, "recent_0_90_days"),
)

V67_ADDITION_EVENT_CONTRACT = tuple(
    sorted(
        (*V67_INTERMEDIATE_EVENT_CONTRACT, *V67_NEW_TRANCHE_EVENT_CONTRACT),
        key=lambda event: (event[1], event[3], event[2]),
    )
)

DELTA_CONTRACT = {
    "full_v67_raw_lifecycle_observations": FULL_V67_RAW_OBSERVATIONS,
    "inherited_observations": PREDECESSOR_OBSERVATIONS,
    "inherited_timelines": PREDECESSOR_TIMELINES,
    "intermediate_lifecycle_observations": INTERMEDIATE_ADDED_OBSERVATIONS,
    "intermediate_project_entities": INTERMEDIATE_ADDED_PROJECTS,
    "new_tranche_lifecycle_observations": NEW_TRANCHE_ADDED_OBSERVATIONS,
    "new_tranche_project_entities": NEW_TRANCHE_ADDED_PROJECTS,
    "post_v62_lifecycle_observations": POST_V62_ADDED_OBSERVATIONS,
    "post_v62_project_entities": POST_V62_ADDED_PROJECTS,
    "recorded_at_values_preserved_from_v2": True,
    "v67_recorded_at_rewrites_ignored": V67_RECORDED_AT_REWRITES_IGNORED,
}

ConstructionTimelineError = v2.ConstructionTimelineError


@dataclass(frozen=True, slots=True)
class _Definition:
    path: Path
    raw: bytes
    timeline_id: str
    as_of: str
    generated_at: str
    open_seed_definition: Path
    open_seed_release: Path
    predecessor_definition: Path
    predecessor_bundle: Path
    expected: Mapping[str, Any]


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ConstructionTimelineError(f"{label} must be an ordinary file")
    return path.read_bytes()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(_regular_bytes(path, str(path)))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_json_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionTimelineError(f"{label} must be UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ConstructionTimelineError(f"{label} must be a JSON object")
    return value


def _resolve(definition: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConstructionTimelineError(f"{label} must be non-empty text")
    path = Path(value)
    if not path.is_absolute():
        path = definition.parent / path
    return Path(os.path.abspath(os.fspath(path)))


def _checkpoint(value: Any, label: str) -> tuple[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        raise ConstructionTimelineError(f"{label} checkpoint schema is invalid")
    path = value.get("path")
    digest = value.get("sha256")
    if not isinstance(path, str) or not path.strip():
        raise ConstructionTimelineError(f"{label} path is invalid")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ConstructionTimelineError(f"{label} SHA-256 is invalid")
    return path, digest


def _load_definition(path_value: str | Path) -> _Definition:
    path = Path(os.path.abspath(os.fspath(path_value)))
    raw = _regular_bytes(path, "timeline definition")
    document = _json_object(raw, "timeline definition")
    if raw != _canonical_json(document):
        raise ConstructionTimelineError("timeline definition must be canonical JSON")
    if set(document) != {
        "as_of",
        "delta",
        "expected",
        "format",
        "generated_at",
        "open_seed",
        "predecessor",
        "schema_version",
        "scope",
        "timeline_id",
    }:
        raise ConstructionTimelineError("timeline definition schema is invalid")
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["format"] != DEFINITION_FORMAT
        or document["timeline_id"] != TIMELINE_ID
        or document["as_of"] != AS_OF
        or document["generated_at"] != GENERATED_AT
        or document["scope"] != SCOPE
        or document["delta"] != DELTA_CONTRACT
        or document["expected"] != EXPECTED_COUNTS
    ):
        raise ConstructionTimelineError("timeline v3 definition contract differs")
    if GENERATED_AT <= open_seed_v67.RECORDED_AT:
        raise ConstructionTimelineError("timeline generated_at must follow v67")

    open_seed = document["open_seed"]
    predecessor = document["predecessor"]
    expected_checkpoint_fields = {
        "definition",
        "expected_release_tree_sha256",
        "manifest",
        "release_path",
    }
    if not isinstance(open_seed, Mapping) or set(open_seed) != expected_checkpoint_fields:
        raise ConstructionTimelineError("open seed checkpoint schema is invalid")
    if not isinstance(predecessor, Mapping) or set(predecessor) != {
        "bundle_path",
        "definition",
        "expected_bundle_tree_sha256",
        "manifest",
    }:
        raise ConstructionTimelineError("predecessor checkpoint schema is invalid")

    seed_definition_display, seed_definition_digest = _checkpoint(
        open_seed["definition"], "open seed definition"
    )
    seed_manifest_display, seed_manifest_digest = _checkpoint(
        open_seed["manifest"], "open seed manifest"
    )
    predecessor_definition_display, predecessor_definition_digest = _checkpoint(
        predecessor["definition"], "predecessor definition"
    )
    predecessor_manifest_display, predecessor_manifest_digest = _checkpoint(
        predecessor["manifest"], "predecessor manifest"
    )
    seed_definition = _resolve(path, seed_definition_display, "open seed definition")
    seed_release = _resolve(path, open_seed["release_path"], "open seed release")
    seed_manifest = _resolve(path, seed_manifest_display, "open seed manifest")
    predecessor_definition = _resolve(
        path, predecessor_definition_display, "predecessor definition"
    )
    predecessor_bundle = _resolve(
        path, predecessor["bundle_path"], "predecessor bundle"
    )
    predecessor_manifest = _resolve(
        path, predecessor_manifest_display, "predecessor manifest"
    )
    if (
        seed_definition != OPEN_SEED_DEFINITION
        or seed_release != OPEN_SEED_RELEASE
        or seed_manifest != OPEN_SEED_RELEASE / MANIFEST_FILENAME
        or seed_definition_digest != OPEN_SEED_DEFINITION_SHA256
        or seed_manifest_digest != OPEN_SEED_MANIFEST_SHA256
        or open_seed["expected_release_tree_sha256"] != OPEN_SEED_TREE_SHA256
        or predecessor_definition != PREDECESSOR_DEFINITION
        or predecessor_bundle != PREDECESSOR_BUNDLE
        or predecessor_manifest != PREDECESSOR_BUNDLE / MANIFEST_FILENAME
        or predecessor_definition_digest != PREDECESSOR_DEFINITION_SHA256
        or predecessor_manifest_digest != PREDECESSOR_MANIFEST_SHA256
        or predecessor["expected_bundle_tree_sha256"] != PREDECESSOR_TREE_SHA256
    ):
        raise ConstructionTimelineError("accepted v67 or v2 pins differ")
    return _Definition(
        path=path,
        raw=raw,
        timeline_id=TIMELINE_ID,
        as_of=AS_OF,
        generated_at=GENERATED_AT,
        open_seed_definition=seed_definition,
        open_seed_release=seed_release,
        predecessor_definition=predecessor_definition,
        predecessor_bundle=predecessor_bundle,
        expected=EXPECTED_COUNTS,
    )


def _validate_inputs(definition: _Definition) -> None:
    checkpoints = {
        definition.open_seed_definition: OPEN_SEED_DEFINITION_SHA256,
        definition.open_seed_release / MANIFEST_FILENAME: OPEN_SEED_MANIFEST_SHA256,
        OPEN_SEED_CORE: OPEN_SEED_CORE_SHA256,
        definition.predecessor_definition: PREDECESSOR_DEFINITION_SHA256,
        definition.predecessor_bundle / MANIFEST_FILENAME: PREDECESSOR_MANIFEST_SHA256,
        PREDECESSOR_CORE: PREDECESSOR_CORE_SHA256,
    }
    for path, digest in checkpoints.items():
        if _sha256_file(path) != digest:
            raise ConstructionTimelineError(f"frozen input changed: {path}")
    if tree_digest(definition.open_seed_release) != OPEN_SEED_TREE_SHA256:
        raise ConstructionTimelineError("frozen open seed v67 tree changed")
    if tree_digest(definition.predecessor_bundle) != PREDECESSOR_TREE_SHA256:
        raise ConstructionTimelineError("frozen timeline v2 tree changed")
    try:
        seed_manifest = open_seed_v67.validate_open_seed_v67(
            definition.open_seed_definition, definition.open_seed_release
        )
        predecessor_manifest = v2.validate_construction_timeline_bundle(
            definition.predecessor_bundle,
            definition_path=definition.predecessor_definition,
            verify_inputs=True,
        )
    except (OSError, ValueError, SystemExit) as error:
        raise ConstructionTimelineError("frozen input validation failed") from error
    frozen_seed_manifest = _json_object(
        _regular_bytes(
            definition.open_seed_release / MANIFEST_FILENAME, "v67 manifest"
        ),
        "v67 manifest",
    )
    frozen_predecessor_manifest = _json_object(
        _regular_bytes(
            definition.predecessor_bundle / MANIFEST_FILENAME, "v2 manifest"
        ),
        "v2 manifest",
    )
    if seed_manifest != frozen_seed_manifest or predecessor_manifest != frozen_predecessor_manifest:
        raise ConstructionTimelineError("validated frozen input manifest differs")


def _release_labels(release: Path) -> dict[str, dict[str, str]]:
    raw = _regular_bytes(release / "entities.csv", "v67 entities.csv")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("v67 entities.csv is not UTF-8") from error
    if len(rows) != 783:
        raise ConstructionTimelineError("v67 entity label inventory differs")
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        entity_id = row.get("entity_id", "")
        if not entity_id or entity_id in labels:
            raise ConstructionTimelineError("v67 entity label identity is invalid")
        labels[entity_id] = row
    return labels


def _full_v67_observations(definition: _Definition) -> list[dict[str, Any]]:
    _validate_inputs(definition)
    v67_document = _json_object(
        _regular_bytes(definition.open_seed_definition, "v67 definition"),
        "v67 definition",
    )
    base = _json_object(
        _regular_bytes(open_seed_v67.BASE_DEFINITION, "v66 base definition"),
        "v66 base definition",
    )
    try:
        selected_rows, paths = open_seed_v67.selected_inputs(base)
    except (OSError, ValueError, SystemExit) as error:
        raise ConstructionTimelineError("v67 source selection failed") from error
    if selected_rows != v67_document.get("curated_inputs") or len(paths) != 378:
        raise ConstructionTimelineError("fresh v67 source inventory differs")
    labels = _release_labels(definition.open_seed_release)
    with tempfile.TemporaryDirectory(
        prefix="construction-timeline-v3-db-", dir="/private/tmp"
    ) as temporary:
        try:
            connection = open_seed_v67._build_database(
                base, paths, Path(temporary) / "atlas.sqlite"
            )
        except (OSError, ValueError, SystemExit) as error:
            raise ConstructionTimelineError("fresh v67 database rebuild failed") from error
        try:
            raw_rows = connection.execute(
                """
                SELECT lifecycle.id AS observation_id,
                       lifecycle.entity_id AS entity_id,
                       entities.stable_key AS entity_stable_key,
                       entities.kind AS entity_kind,
                       lifecycle.as_of_date AS observed_date,
                       lifecycle.valid_to_date AS valid_to_date,
                       lifecycle.status AS status,
                       lifecycle.method AS method,
                       lifecycle.confidence AS confidence,
                       lifecycle.notes AS notes,
                       lifecycle.recorded_at AS recorded_at,
                       lifecycle.superseded_at AS superseded_at,
                       evidence.id AS evidence_id,
                       evidence.kind AS evidence_kind,
                       evidence.source_family AS evidence_source_family,
                       evidence.title AS evidence_title,
                       evidence.publisher AS evidence_publisher,
                       evidence.source_url AS evidence_source_url,
                       evidence.license AS evidence_license,
                       evidence.attribution AS evidence_attribution,
                       evidence.published_at AS evidence_published_at,
                       evidence.retrieved_at AS evidence_retrieved_at,
                       evidence.content_hash AS evidence_content_hash
                FROM lifecycle_observations AS lifecycle
                JOIN entities ON entities.id = lifecycle.entity_id
                JOIN evidence ON evidence.id = lifecycle.evidence_id
                ORDER BY entities.stable_key, lifecycle.as_of_date,
                         lifecycle.recorded_at, lifecycle.id
                """
            ).fetchall()
        finally:
            connection.close()
    observations: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        row = dict(raw_row)
        label = labels.get(row["entity_id"])
        if (
            label is None
            or label.get("stable_key") != row["entity_stable_key"]
            or label.get("entity_kind") != row["entity_kind"]
            or not label.get("name")
            or not label.get("country")
        ):
            raise ConstructionTimelineError("v67 lifecycle entity label differs")
        row["entity_name"] = label["name"]
        row["entity_country"] = label["country"]
        observations.append({field: row[field] for field in OBSERVATION_FIELDS})
    if (
        len(observations) != FULL_V67_RAW_OBSERVATIONS
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("full v67 lifecycle inventory differs")
    return observations


def _csv_scalar(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return str(value)
    return value


def _csv_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(_csv_scalar(row[field])) for field in OBSERVATION_FIELDS}


def _csv_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=OBSERVATION_FIELDS,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_scalar(row[field]) for field in OBSERVATION_FIELDS})
    return stream.getvalue().encode("utf-8")


def _predecessor_observations(definition: _Definition) -> list[dict[str, str]]:
    rows = v2._parse_csv(definition.predecessor_bundle / OBSERVATIONS_FILENAME)
    if len(rows) != PREDECESSOR_OBSERVATIONS:
        raise ConstructionTimelineError("v2 observation inventory differs")
    if _csv_bytes(rows) != _regular_bytes(
        definition.predecessor_bundle / OBSERVATIONS_FILENAME, "v2 observations"
    ):
        raise ConstructionTimelineError("v2 observation byte semantics differ")
    return rows


def _predecessor_timelines(definition: _Definition) -> list[dict[str, Any]]:
    rows = v2._parse_jsonl(definition.predecessor_bundle / TIMELINES_FILENAME)
    if len(rows) != PREDECESSOR_TIMELINES:
        raise ConstructionTimelineError("v2 timeline inventory differs")
    if b"".join(_canonical_json_line(row) for row in rows) != _regular_bytes(
        definition.predecessor_bundle / TIMELINES_FILENAME, "v2 timelines"
    ):
        raise ConstructionTimelineError("v2 timeline byte semantics differ")
    as_of = date.fromisoformat(AS_OF)
    for row in rows:
        observations = row["observations"]
        expected_old = len(observations) == 1 and (
            as_of - date.fromisoformat(observations[0]["observed_date"])
        ).days > 365
        if row["single_old_observation_current_unknown"] is not expected_old:
            raise ConstructionTimelineError("v2 timeline age boundary changed on 2026-07-21")
    return rows


def _freshness_class(age: int) -> str:
    if age <= 90:
        return "recent_0_90_days"
    if age <= 365:
        return "aging_91_365_days"
    return "stale_over_365_days"


def _event_contract(rows: Iterable[Mapping[str, Any]]) -> tuple[tuple[Any, ...], ...]:
    as_of = date.fromisoformat(AS_OF)
    contract = []
    for row in rows:
        stable_key = str(row["entity_stable_key"])
        age = (as_of - date.fromisoformat(str(row["observed_date"]))).days
        contract.append(
            (
                PROJECT_SOURCE_BY_KEY[stable_key],
                stable_key,
                str(row["observation_id"]),
                str(row["observed_date"]),
                str(row["status"]),
                str(row["method"]),
                str(row["evidence_id"]),
                str(row["evidence_source_family"]),
                str(row["evidence_retrieved_at"]),
                str(row["evidence_content_hash"]),
                age,
                _freshness_class(age),
            )
        )
    return tuple(sorted(contract, key=lambda item: (item[1], item[3], item[2])))


def _reconstruct_observations(
    definition: _Definition,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = _full_v67_observations(definition)
    predecessor = _predecessor_observations(definition)
    full_by_id = {str(row["observation_id"]): row for row in full}
    predecessor_ids = {row["observation_id"] for row in predecessor}
    if not predecessor_ids <= set(full_by_id):
        raise ConstructionTimelineError("v67 dropped a v2 observation identity")
    rewrite_count = 0
    for row in predecessor:
        fresh = _csv_row(full_by_id[row["observation_id"]])
        differences = {field for field in OBSERVATION_FIELDS if row[field] != fresh[field]}
        if differences - {"recorded_at"}:
            raise ConstructionTimelineError(
                f"v67 changed inherited observation semantics: {row['observation_id']}"
            )
        rewrite_count += differences == {"recorded_at"}
    if rewrite_count != V67_RECORDED_AT_REWRITES_IGNORED:
        raise ConstructionTimelineError("v67 inherited recorded_at rewrite count differs")

    intermediate = [
        row
        for row in full
        if row["entity_stable_key"] in INTERMEDIATE_PROJECT_SOURCE_BY_KEY
    ]
    new_tranche = [
        row
        for row in full
        if row["entity_stable_key"] in NEW_TRANCHE_PROJECT_SOURCE_BY_KEY
    ]
    if (
        len(intermediate) != INTERMEDIATE_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in intermediate})
        != INTERMEDIATE_ADDED_PROJECTS
        or _event_contract(intermediate) != V67_INTERMEDIATE_EVENT_CONTRACT
    ):
        raise ConstructionTimelineError("v67 intermediate event contract differs")
    if (
        len(new_tranche) != NEW_TRANCHE_ADDED_OBSERVATIONS
        or len({row["entity_stable_key"] for row in new_tranche})
        != NEW_TRANCHE_ADDED_PROJECTS
        or _event_contract(new_tranche) != V67_NEW_TRANCHE_EVENT_CONTRACT
    ):
        raise ConstructionTimelineError("v67 new-tranche event contract differs")
    additions = [*intermediate, *new_tranche]
    if _event_contract(additions) != V67_ADDITION_EVENT_CONTRACT:
        raise ConstructionTimelineError("v67 combined addition event contract differs")
    addition_ids = {str(row["observation_id"]) for row in additions}
    if predecessor_ids & addition_ids:
        raise ConstructionTimelineError("v67 addition collides with v2 observation")
    extra_ids = set(full_by_id) - predecessor_ids
    if (
        len(extra_ids) != POST_V62_ADDED_OBSERVATIONS
        or extra_ids != addition_ids
    ):
        raise ConstructionTimelineError("v67 full-to-v2 delta boundary differs")

    combined: list[dict[str, Any]] = [*predecessor, *additions]
    combined.sort(
        key=lambda row: (
            str(row["entity_stable_key"]),
            str(row["observed_date"]),
            str(row["recorded_at"]),
            str(row["observation_id"]),
        )
    )
    if len(combined) != EXPECTED_COUNTS["raw_lifecycle_observations"]:
        raise ConstructionTimelineError("v3 observation inventory differs")
    return combined, additions


def _timeline_rows(
    definition: _Definition, additions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    predecessor = _predecessor_timelines(definition)
    new_rows = v2._timeline_rows(additions, as_of=AS_OF)
    if (
        len(new_rows) != POST_V62_ADDED_PROJECTS
        or any(
            row["format"] != TIMELINE_FORMAT
            or row["schema_version"] != TIMELINE_SCHEMA_VERSION
            or row["current_status_classification"] != "unknown"
            or row["current_construction_claim"] is not False
            or row["latest_observation_persistence_assumed"] is not False
            for row in new_rows
        )
    ):
        raise ConstructionTimelineError("v67 addition timeline guardrails differ")
    predecessor_keys = {row["entity_stable_key"] for row in predecessor}
    if predecessor_keys & {row["entity_stable_key"] for row in new_rows}:
        raise ConstructionTimelineError("v3 timeline identity collides with v2")
    rows = [*predecessor, *new_rows]
    rows.sort(key=lambda row: (row["entity_stable_key"], row["entity_id"]))
    return rows


def _event_documents(
    contract: tuple[tuple[Any, ...], ...] = V67_ADDITION_EVENT_CONTRACT,
) -> list[dict[str, Any]]:
    documents = []
    for event in contract:
        document = dict(zip(EVENT_CONTRACT_FIELDS, event, strict=True))
        document.update(
            {
                "current_construction_claim": False,
                "current_status_classification": "unknown",
                "latest_observation_persistence_assumed": False,
                "status_semantics": "last_observed",
            }
        )
        documents.append(document)
    return documents


def _coverage(
    observations: list[dict[str, Any]],
    timelines: list[dict[str, Any]],
    definition: _Definition,
) -> dict[str, Any]:
    multi = [row for row in timelines if row["has_multiple_observations"]]
    single = [row for row in timelines if not row["has_multiple_observations"]]
    changing = [row for row in multi if row["has_status_change"]]
    repeated = [row for row in multi if not row["has_status_change"]]
    single_old = [row for row in single if row["single_old_observation_current_unknown"]]
    counts = {
        "entities_with_lifecycle_observations": len(timelines),
        "multi_observation_entities": len(multi),
        "raw_lifecycle_observations": len(observations),
        "repeated_status_multi_observation_entities": len(repeated),
        "single_observation_entities": len(single),
        "single_old_observation_entities": len(single_old),
        "source_families": len({row["evidence_source_family"] for row in observations}),
        "status_changing_multi_observation_entities": len(changing),
    }
    if counts != dict(definition.expected):
        raise ConstructionTimelineError(f"timeline coverage counts differ: {counts}")
    intermediate_events = _event_documents(V67_INTERMEDIATE_EVENT_CONTRACT)
    new_tranche_events = _event_documents(V67_NEW_TRANCHE_EVENT_CONTRACT)
    events = _event_documents()
    stt = next(
        event
        for event in events
        if event["entity_stable_key"]
        == "curated:stt-johor-data-centre-campus:stt-johor-1"
    )
    return {
        "as_of": definition.as_of,
        "counts": counts,
        "current_status_classification_counts": {"unknown": len(timelines)},
        "date_coverage": {
            "latest_observed_date": max(str(row["observed_date"]) for row in observations),
            "oldest_observed_date": min(str(row["observed_date"]) for row in observations),
        },
        "delta": DELTA_CONTRACT,
        "format": COVERAGE_FORMAT,
        "generated_at": definition.generated_at,
        "intermediate_addition_events": intermediate_events,
        "intermediate_addition_freshness_counts": dict(
            sorted(
                Counter(
                    str(event["freshness_class"])
                    for event in intermediate_events
                ).items()
            )
        ),
        "multi_observation_timelines": [
            {
                "entity_stable_key": row["entity_stable_key"],
                "observations": [
                    {
                        "observed_date": item["observed_date"],
                        "status": item["status"],
                    }
                    for item in row["observations"]
                ],
                "status_change": row["has_status_change"],
            }
            for row in multi
        ],
        "observation_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in observations).items())
        ),
        "observation_status_counts": dict(
            sorted(Counter(str(row["status"]) for row in observations).items())
        ),
        "predecessor": {
            "definition_sha256": PREDECESSOR_DEFINITION_SHA256,
            "manifest_sha256": PREDECESSOR_MANIFEST_SHA256,
            "timeline_id": v2.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "source_family_observation_counts": dict(
            sorted(
                Counter(
                    str(row["evidence_source_family"]) for row in observations
                ).items()
            )
        ),
        "stt_johor_historical_only": stt,
        "timeline_entity_kind_counts": dict(
            sorted(Counter(str(row["entity_kind"]) for row in timelines).items())
        ),
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
        "v67_addition_events": events,
        "v67_addition_freshness_counts": dict(
            sorted(Counter(str(event["freshness_class"]) for event in events).items())
        ),
        "v67_new_tranche_events": new_tranche_events,
        "v67_new_tranche_freshness_counts": dict(
            sorted(
                Counter(
                    str(event["freshness_class"])
                    for event in new_tranche_events
                ).items()
            )
        ),
    }


def _readme(coverage: Mapping[str, Any]) -> bytes:
    counts = coverage["counts"]
    return (
        "# Source-scoped construction milestone timeline v3\n\n"
        "This immutable exact successor preserves all 430 accepted v2 lifecycle "
        "observations and all 415 accepted v2 entity-timeline rows byte-for-byte, "
        "then appends all 29 post-v62 observations: 14 intermediate-seed rows on "
        "14 projects plus 15 new-tranche rows on 14 projects. SMX01 contributes "
        "the sole second milestone in the additive partitions. "
        f"The result contains {counts['raw_lifecycle_observations']} observations "
        f"for {counts['entities_with_lifecycle_observations']} source-scoped entities.\n\n"
        "A complete 459-row v67 lifecycle database is rebuilt offline to verify both "
        "separately pinned additive partitions. V67 recorded_at rewrites never replace "
        "the predecessor's accepted recording lineage.\n\n"
        "Every lifecycle status is a dated last-observed historical fact. Current "
        "status remains unknown, current construction is never claimed, and the latest "
        "observation is never assumed to persist. STT Johor is explicitly stale "
        "historical-only at 512 days old. Permits, forecasts, planned dates, satellite "
        "or CV review, and missing milestones are not promoted or interpolated into "
        "physical construction. Cross-source identities remain unresolved and unique "
        "physical sites remain null.\n\n"
        "The v2 entity-timeline row format and schema version are retained so every "
        "inherited JSONL line remains byte-identical; v3 versioning applies to the "
        "definition, bundle, manifest, and coverage contracts. Blank CSV values retain "
        "their predecessor null semantics.\n"
    ).encode("utf-8")


def _attribution(observations: list[dict[str, Any]]) -> bytes:
    by_family: dict[str, dict[str, set[str]]] = {}
    for row in observations:
        record = by_family.setdefault(
            str(row["evidence_source_family"]),
            {"attributions": set(), "licenses": set(), "publishers": set()},
        )
        record["attributions"].add(str(row["evidence_attribution"]))
        record["licenses"].add(str(row["evidence_license"]))
        record["publishers"].add(str(row["evidence_publisher"]))
    lines = [
        "Derived from the hash-pinned construction timeline v2 and open seed v67 inputs.",
        "Every row retains its accepted or source-derived evidence identity, URL, publisher, license, attribution, content hash, and retrieval timestamp.",
        "Source-family attribution inventory:",
    ]
    for family, values in sorted(by_family.items()):
        lines.append(
            f"- {family} | publishers: {'; '.join(sorted(values['publishers']))} "
            f"| licenses: {'; '.join(sorted(values['licenses']))} "
            f"| attribution: {'; '.join(sorted(values['attributions']))}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _prepare_payloads(
    definition: _Definition,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    observations, additions = _reconstruct_observations(definition)
    timelines = _timeline_rows(definition, additions)
    coverage = _coverage(observations, timelines, definition)
    payloads = {
        ATTRIBUTION_FILENAME: _attribution(observations),
        COVERAGE_FILENAME: _canonical_json(coverage),
        OBSERVATIONS_FILENAME: _csv_bytes(observations),
        README_FILENAME: _readme(coverage),
        TIMELINES_FILENAME: b"".join(_canonical_json_line(row) for row in timelines),
    }
    manifest = {
        "as_of": definition.as_of,
        "counts": coverage["counts"],
        "definition": {
            "bytes": len(definition.raw),
            "file": definition.path.name,
            "sha256": _sha256_bytes(definition.raw),
        },
        "delta": DELTA_CONTRACT,
        "files": {
            name: {"bytes": len(raw), "sha256": _sha256_bytes(raw)}
            for name, raw in sorted(payloads.items())
        },
        "format": BUNDLE_FORMAT,
        "generated_at": definition.generated_at,
        "open_seed_input": {
            "definition": {
                "bytes": definition.open_seed_definition.stat().st_size,
                "file": definition.open_seed_definition.name,
                "sha256": OPEN_SEED_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": (definition.open_seed_release / MANIFEST_FILENAME).stat().st_size,
                "file": MANIFEST_FILENAME,
                "sha256": OPEN_SEED_MANIFEST_SHA256,
            },
            "release_id": definition.open_seed_release.name,
            "release_tree_sha256": OPEN_SEED_TREE_SHA256,
        },
        "predecessor_input": {
            "definition": {
                "bytes": definition.predecessor_definition.stat().st_size,
                "file": definition.predecessor_definition.name,
                "sha256": PREDECESSOR_DEFINITION_SHA256,
            },
            "manifest": {
                "bytes": (
                    definition.predecessor_bundle / MANIFEST_FILENAME
                ).stat().st_size,
                "file": MANIFEST_FILENAME,
                "sha256": PREDECESSOR_MANIFEST_SHA256,
            },
            "timeline_id": v2.TIMELINE_ID,
            "tree_sha256": PREDECESSOR_TREE_SHA256,
        },
        "schema_version": SCHEMA_VERSION,
        "scope": SCOPE,
        "timeline_id": definition.timeline_id,
        "timeline_row_format": TIMELINE_FORMAT,
        "timeline_row_schema_version": TIMELINE_SCHEMA_VERSION,
    }
    manifest_raw = _canonical_json(manifest)
    payloads[MANIFEST_FILENAME] = manifest_raw
    payloads[MANIFEST_HASH_FILENAME] = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return payloads, manifest


def _parse_csv(path: Path) -> list[dict[str, str]]:
    raw = _regular_bytes(path, OBSERVATIONS_FILENAME)
    try:
        stream = io.StringIO(raw.decode("utf-8"), newline="")
    except UnicodeDecodeError as error:
        raise ConstructionTimelineError("observation CSV is not UTF-8") from error
    reader = csv.DictReader(stream)
    if tuple(reader.fieldnames or ()) != OBSERVATION_FIELDS:
        raise ConstructionTimelineError("observation CSV header differs")
    return list(reader)


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _regular_bytes(path, TIMELINES_FILENAME)
    if not raw.endswith(b"\n"):
        raise ConstructionTimelineError("timeline JSONL must end with a newline")
    rows = []
    for position, line in enumerate(raw.splitlines(keepends=True), start=1):
        value = _json_object(line, f"timeline JSONL row {position}")
        if line != _canonical_json_line(value):
            raise ConstructionTimelineError("timeline JSONL row is not canonical")
        rows.append(value)
    return rows


def _validate_payload_semantics(
    directory: Path, manifest: Mapping[str, Any]
) -> None:
    observations = _parse_csv(directory / OBSERVATIONS_FILENAME)
    timelines = _parse_jsonl(directory / TIMELINES_FILENAME)
    coverage_raw = _regular_bytes(directory / COVERAGE_FILENAME, COVERAGE_FILENAME)
    coverage = _json_object(coverage_raw, COVERAGE_FILENAME)
    if coverage_raw != _canonical_json(coverage):
        raise ConstructionTimelineError("coverage JSON is not canonical")
    if (
        len(observations) != EXPECTED_COUNTS["raw_lifecycle_observations"]
        or len(timelines) != EXPECTED_COUNTS["entities_with_lifecycle_observations"]
        or len({row["observation_id"] for row in observations}) != len(observations)
    ):
        raise ConstructionTimelineError("timeline row inventory differs")
    stable_order = [
        (
            row["entity_stable_key"],
            row["observed_date"],
            row["recorded_at"],
            row["observation_id"],
        )
        for row in observations
    ]
    if stable_order != sorted(stable_order):
        raise ConstructionTimelineError("observation CSV ordering differs")
    timeline_order = [
        (row.get("entity_stable_key"), row.get("entity_id")) for row in timelines
    ]
    if timeline_order != sorted(timeline_order) or len(set(timeline_order)) != len(timeline_order):
        raise ConstructionTimelineError("timeline JSONL identity ordering differs")
    flattened_ids = []
    for timeline in timelines:
        if (
            timeline.get("format") != TIMELINE_FORMAT
            or timeline.get("schema_version") != TIMELINE_SCHEMA_VERSION
            or timeline.get("current_status_classification") != "unknown"
            or timeline.get("current_construction_claim") is not False
            or timeline.get("latest_observation_persistence_assumed") is not False
            or timeline.get("source_scoped_identity_only") is not True
        ):
            raise ConstructionTimelineError("timeline JSONL guardrails differ")
        nested = timeline.get("observations")
        if not isinstance(nested, list) or timeline.get("observation_count") != len(nested):
            raise ConstructionTimelineError("timeline observation accounting differs")
        flattened_ids.extend(str(item["observation_id"]) for item in nested)
    if sorted(flattened_ids) != sorted(row["observation_id"] for row in observations):
        raise ConstructionTimelineError("flat and grouped observation inventories differ")
    if (
        coverage.get("format") != COVERAGE_FORMAT
        or coverage.get("schema_version") != SCHEMA_VERSION
        or coverage.get("scope") != SCOPE
        or coverage.get("counts") != EXPECTED_COUNTS
        or coverage.get("delta") != DELTA_CONTRACT
        or manifest.get("counts") != EXPECTED_COUNTS
        or manifest.get("delta") != DELTA_CONTRACT
    ):
        raise ConstructionTimelineError("coverage or manifest contract differs")
    predecessor_rows = v2._parse_csv(PREDECESSOR_BUNDLE / OBSERVATIONS_FILENAME)
    current_by_id = {row["observation_id"]: row for row in observations}
    if any(current_by_id.get(row["observation_id"]) != row for row in predecessor_rows):
        raise ConstructionTimelineError("inherited observation semantics changed")
    predecessor_timelines = v2._parse_jsonl(PREDECESSOR_BUNDLE / TIMELINES_FILENAME)
    current_by_key = {row["entity_stable_key"]: row for row in timelines}
    if any(current_by_key.get(row["entity_stable_key"]) != row for row in predecessor_timelines):
        raise ConstructionTimelineError("inherited timeline semantics changed")
    stt = coverage.get("stt_johor_historical_only")
    if (
        not isinstance(stt, Mapping)
        or stt.get("observation_age_days") != 512
        or stt.get("freshness_class") != "stale_over_365_days"
        or stt.get("status_semantics") != "last_observed"
        or stt.get("current_status_classification") != "unknown"
        or stt.get("current_construction_claim") is not False
        or stt.get("latest_observation_persistence_assumed") is not False
    ):
        raise ConstructionTimelineError("STT Johor historical-only contract differs")


def validate_construction_timeline_bundle(
    path_value: str | Path,
    *,
    definition_path: str | Path | None = None,
    verify_inputs: bool = False,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate a closed v3 bundle and optionally replay all inputs offline."""

    directory = Path(os.path.abspath(os.fspath(path_value)))
    if directory.is_symlink() or not directory.is_dir():
        raise ConstructionTimelineError("timeline bundle must be an ordinary directory")
    if require_frozen and stat.S_IMODE(directory.stat().st_mode) != FROZEN_DIRECTORY_MODE:
        raise ConstructionTimelineError("timeline bundle directory must be mode 0555")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES:
        raise ConstructionTimelineError("timeline bundle file inventory differs")
    for entry in entries:
        _regular_bytes(entry, f"timeline bundle file {entry.name}")
        if require_frozen and stat.S_IMODE(entry.stat().st_mode) != FROZEN_FILE_MODE:
            raise ConstructionTimelineError("timeline bundle files must be mode 0444")
    manifest_raw = _regular_bytes(directory / MANIFEST_FILENAME, MANIFEST_FILENAME)
    manifest = _json_object(manifest_raw, MANIFEST_FILENAME)
    if manifest_raw != _canonical_json(manifest):
        raise ConstructionTimelineError("timeline manifest is not canonical")
    sidecar = _regular_bytes(directory / MANIFEST_HASH_FILENAME, MANIFEST_HASH_FILENAME)
    expected_sidecar = (
        f"{_sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar != expected_sidecar:
        raise ConstructionTimelineError("timeline manifest sidecar differs")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != BUNDLE_FORMAT
        or manifest.get("timeline_id") != TIMELINE_ID
        or manifest.get("as_of") != AS_OF
        or manifest.get("generated_at") != GENERATED_AT
        or manifest.get("scope") != SCOPE
        or manifest.get("timeline_row_format") != TIMELINE_FORMAT
        or manifest.get("timeline_row_schema_version") != TIMELINE_SCHEMA_VERSION
    ):
        raise ConstructionTimelineError("timeline manifest contract differs")
    files = manifest.get("files")
    payload_names = BUNDLE_FILES - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not isinstance(files, Mapping) or set(files) != payload_names:
        raise ConstructionTimelineError("timeline manifest file inventory differs")
    for name in payload_names:
        raw = _regular_bytes(directory / name, name)
        if files[name] != {"bytes": len(raw), "sha256": _sha256_bytes(raw)}:
            raise ConstructionTimelineError(f"timeline file checkpoint differs: {name}")
    _validate_payload_semantics(directory, manifest)
    if definition_path is not None:
        definition = _load_definition(definition_path)
        if manifest.get("definition") != {
            "bytes": len(definition.raw),
            "file": definition.path.name,
            "sha256": _sha256_bytes(definition.raw),
        }:
            raise ConstructionTimelineError("timeline definition checkpoint differs")
        if verify_inputs:
            expected_payloads, expected_manifest = _prepare_payloads(definition)
            actual_payloads = {entry.name: entry.read_bytes() for entry in entries}
            if actual_payloads != expected_payloads or manifest != expected_manifest:
                raise ConstructionTimelineError("exact-input timeline rebuild differs")
    elif verify_inputs:
        raise ConstructionTimelineError("verify_inputs requires definition_path")
    return manifest


def _discard_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    stage.chmod(0o700)
    for entry in stage.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise ConstructionTimelineError("refusing contaminated timeline stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(stage)


def write_construction_timeline_bundle(
    definition_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Double-rebuild, freeze, and atomically publish construction timeline v3."""

    definition = _load_definition(definition_path)
    output = Path(os.path.abspath(os.fspath(output_directory)))
    if output.exists() or output.is_symlink():
        raise ConstructionTimelineError(
            f"timeline output already exists; refusing overwrite: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir() or not output.name:
        raise ConstructionTimelineError("timeline output parent is invalid")
    payloads, manifest = _prepare_payloads(definition)
    replay_payloads, replay_manifest = _prepare_payloads(definition)
    if payloads != replay_payloads or manifest != replay_manifest:
        raise ConstructionTimelineError(
            "v67 inputs changed or two offline timeline reconstructions differ"
        )
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    published = False
    try:
        for name, raw in payloads.items():
            target = stage / name
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        validate_construction_timeline_bundle(stage, require_frozen=False)
        for target in stage.iterdir():
            target.chmod(FROZEN_FILE_MODE)
        stage.chmod(FROZEN_DIRECTORY_MODE)
        validate_construction_timeline_bundle(stage)
        try:
            promote_noreplace(stage, output)
        except SystemExit as error:
            raise ConstructionTimelineError(str(error)) from error
        published = True
        return validate_construction_timeline_bundle(
            output,
            definition_path=definition.path,
            verify_inputs=True,
        )
    finally:
        if not published:
            _discard_stage(stage)


build_construction_timeline_bundle = write_construction_timeline_bundle


__all__ = [
    "AS_OF",
    "ATTRIBUTION_FILENAME",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "COVERAGE_FILENAME",
    "ConstructionTimelineError",
    "DELTA_CONTRACT",
    "EXPECTED_COUNTS",
    "GENERATED_AT",
    "INTERMEDIATE_PROJECT_SOURCE_BY_KEY",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "NEW_TRANCHE_PROJECT_SOURCE_BY_KEY",
    "OBSERVATIONS_FILENAME",
    "OBSERVATION_FIELDS",
    "OPEN_SEED_DEFINITION_SHA256",
    "OPEN_SEED_MANIFEST_SHA256",
    "OPEN_SEED_TREE_SHA256",
    "POST_V62_ADDED_OBSERVATIONS",
    "POST_V62_ADDED_PROJECTS",
    "PREDECESSOR_DEFINITION_SHA256",
    "PREDECESSOR_MANIFEST_SHA256",
    "PREDECESSOR_TREE_SHA256",
    "PROJECT_SOURCE_BY_KEY",
    "SCHEMA_VERSION",
    "SCOPE",
    "TIMELINES_FILENAME",
    "TIMELINE_FORMAT",
    "TIMELINE_ID",
    "TIMELINE_SCHEMA_VERSION",
    "V67_ADDITION_EVENT_CONTRACT",
    "V67_INTERMEDIATE_EVENT_CONTRACT",
    "V67_NEW_TRANCHE_EVENT_CONTRACT",
    "build_construction_timeline_bundle",
    "validate_construction_timeline_bundle",
    "write_construction_timeline_bundle",
]
