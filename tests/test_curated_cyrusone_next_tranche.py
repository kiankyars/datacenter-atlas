from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
DFW10_CAMPUS_KEY = "curated:cyrusone-dfw10-bosque-county-campus"
DFW10_ADDRESS = (
    "Adjacent to Thad Hill Energy Center, Bosque County, Texas, United States"
)


def _capacity(
    entity: str,
    metric: str,
    stage: str,
    value: float,
    as_of_date: str,
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
        "as_of_date": as_of_date,
        "target_date": None,
    }


SOURCES: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-19-cyrusone-osk1-seika.json": {
        "sha256": "09f16a91356f27ad00f293d8bf1d95c5578ef622713e872e14c42111a4bb67ef",
        "country": "Japan",
        "address": "2-2-7 Hikaridai, Seika town, Sorakugun, Kyoto 619-0288, Japan",
        "campus_key": "curated:cyrusone-kep-osk1-seika-data-center",
        "campus_name": "CyrusOne KEP OSK1 Seika Data Center",
        "project_key": (
            "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build"
        ),
        "project_name": "CyrusOne KEP OSK1 Current Facility Build",
        "lifecycle": ("under_construction", "2025-08-19"),
        "capacity": _capacity(
            "project", "critical_it_mw", "planned", 48, "2026-07-19"
        ),
        "evidence_keys": (
            "cyrusone-osk1-linkedin-construction-captured-2026-07-19",
            "cyrusone-osk1-facility-page-captured-2026-07-19",
            "kepco-annual-report-2025-osk1-section-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-fra7-frankfurt-westside.json": {
        "sha256": "fa736c847a85f5d99bb4f0cd608cea5dc82f381905fea017a9a7d8e3b66324c0",
        "country": "Germany",
        "address": "Stroofstraße 49, 65933 Frankfurt am Main, Germany",
        "campus_key": "curated:cyrusone-fra7-frankfurt-westside-campus",
        "campus_name": "CyrusOne FRA7 Frankfurt Westside Campus",
        "project_key": (
            "curated:cyrusone-fra7-frankfurt-westside-campus:"
            "current-multi-building-development"
        ),
        "project_name": "CyrusOne FRA7 Current Multi-Building Development",
        "lifecycle": ("under_construction", "2026-06-12"),
        "capacity": _capacity(
            "campus", "critical_it_mw", "planned", 81, "2026-07-19"
        ),
        "evidence_keys": (
            "cyrusone-fra7-linkedin-transformer-milestone-captured-2026-07-19",
            "cyrusone-fra7-facility-page-captured-2026-07-19",
            "cyrusone-fra7-eon-correction-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-dfw10-current-campus-development.json": {
        "sha256": "1ca71a38e270f40d4c4933d6a99dc9a30026f51e6d72188d5bd020db2ad860ac",
        "country": "United States",
        "address": DFW10_ADDRESS,
        "campus_key": DFW10_CAMPUS_KEY,
        "campus_name": "CyrusOne DFW10 Bosque County Campus",
        "project_key": f"{DFW10_CAMPUS_KEY}:current-campus-development",
        "project_name": "CyrusOne DFW10 Current Campus Development",
        "lifecycle": ("under_construction", "2025-11-03"),
        "capacity": _capacity(
            "campus", "grid_connection_mw", "contracted", 400, "2025-11-03"
        ),
        "evidence_keys": (
            "cyrusone-dfw10-identity-release-captured-2026-07-19",
            "cyrusone-dfw10-phase2-release-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-dfw10-building-1.json": {
        "sha256": "00f3d66646a1f775028f21e3c482157ed2b4b6fadff8972cb4ced0e839fb123c",
        "country": "United States",
        "address": DFW10_ADDRESS,
        "campus_key": DFW10_CAMPUS_KEY,
        "campus_name": "CyrusOne DFW10 Bosque County Campus",
        "project_key": f"{DFW10_CAMPUS_KEY}:building-1-current-build",
        "project_name": "CyrusOne DFW10 Building 1 Current Build",
        "lifecycle": ("shell", "2026-03-13"),
        "capacity": None,
        "evidence_keys": (
            "cyrusone-dfw10-identity-release-captured-2026-07-19",
            "clune-dfw10-building1-topout-captured-2026-07-19",
            "clune-dfw10-general-contractor-coverage-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-freestone-initial-facility.json": {
        "sha256": "85c35586d67365c12fc7332ef736ad829f6f2bef3cd1d6c5c0f6a3a58b5fc7ad",
        "country": "United States",
        "address": (
            "Near Freestone Energy Center, Freestone County, Texas, United States"
        ),
        "campus_key": "curated:cyrusone-freestone-county-campus",
        "campus_name": "CyrusOne Freestone County Campus",
        "project_key": (
            "curated:cyrusone-freestone-county-campus:initial-facility-build"
        ),
        "project_name": "CyrusOne Freestone Initial Facility Build",
        "lifecycle": ("under_construction", "2026-06-05"),
        "capacity": _capacity(
            "project", "grid_connection_mw", "contracted", 380, "2026-02-09"
        ),
        "evidence_keys": (
            "cyrusone-freestone-linkedin-groundbreaking-captured-2026-07-19",
            "cyrusone-freestone-power-agreement-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-new-albany-building-1.json": {
        "sha256": "8911834b22cd48fd31135f01d407944cd6fbd0784d25c1c0fc338eeaac952059",
        "country": "United States",
        "address": "2470 Clover Valley Rd., New Albany, Ohio, United States",
        "campus_key": "curated:cyrusone-new-albany-campus",
        "campus_name": "CyrusOne New Albany Campus",
        "project_key": "curated:cyrusone-new-albany-campus:building-1-current-build",
        "project_name": "CyrusOne New Albany Building 1",
        "lifecycle": ("under_construction", "2025-10-09"),
        "capacity": None,
        "evidence_keys": (
            "cyrusone-new-albany-linkedin-construction-captured-2026-07-19",
            "new-albany-cyrusone-building1-project-page-captured-2026-07-19",
        ),
    },
    "curated-official-2026-07-19-cyrusone-fra6-sossenheim.json": {
        "sha256": "551624cd9f2e96a979a50391b5eebee44f156b1a0b4cdb80b4fe794cf9dceeb3",
        "country": "Germany",
        "address": "Wilhelm-Fay-Straße 32, 65936 Frankfurt am Main, Germany",
        "campus_key": "curated:cyrusone-fra6-sossenheim-campus",
        "campus_name": "CyrusOne FRA6 Sossenheim Campus",
        "project_key": (
            "curated:cyrusone-fra6-sossenheim-campus:"
            "current-brownfield-redevelopment"
        ),
        "project_name": "CyrusOne FRA6 Current Brownfield Redevelopment",
        "lifecycle": ("site_preparation", "2025-11-26"),
        "capacity": _capacity(
            "project", "critical_it_mw", "planned", 72, "2026-07-19"
        ),
        "evidence_keys": (
            "cyrusone-fra6-linkedin-demolition-captured-2026-07-19",
            "carsten-schneider-fra6-personal-update-captured-2026-07-19",
            "cyrusone-fra6-facility-page-captured-2026-07-19",
            "cyrusone-fra6-europark-police-release-captured-2026-07-19",
        ),
    },
}


def _capture(
    sha256: str,
    body_bytes: int,
    headers_sha256: str,
    retrieved_at: str,
    response_http_date: str,
    last_modified: str | None,
    content_type: str,
    url: str,
    *,
    canonical_url: str | None = None,
    request_started_at: str | None = None,
    activity_id: str | None = None,
) -> dict[str, Any]:
    return {
        "sha256": sha256,
        "body_bytes": body_bytes,
        "headers_sha256": headers_sha256,
        "retrieved_at": retrieved_at,
        "response_http_date": response_http_date,
        "last_modified": last_modified,
        "content_type": content_type,
        "url": url,
        "canonical_url": canonical_url or url,
        "request_started_at": request_started_at,
        "activity_id": activity_id,
    }


CAPTURES_BY_KEY: dict[str, dict[str, Any]] = {
    "cyrusone-osk1-linkedin-construction-captured-2026-07-19": _capture(
        "90742a9a51653251e860ce63356bb4255d62eb1f076f4e6e24412b2beabc58b7",
        173874,
        "99bc6fd53668f975a63fcb8e322d62c8669ae5ca3ed2e95731bbeb0852acfab8",
        "2026-07-19T17:32:29Z",
        "2026-07-19T17:32:10Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/cyrusone_cyrusone-japan-shintoceremony-activity-7363589315555119106-tTxL",
        activity_id="7363589315555119106",
    ),
    "cyrusone-osk1-facility-page-captured-2026-07-19": _capture(
        "f8fc3261f3daa384e0e14a118481631874f2d253172cb33da39c519dc4ca02c5",
        81757,
        "2c14c1dbf7410ebe9d12b569deaf032c2878bb583c3d32b25735cce46c611815",
        "2026-07-19T17:32:29Z",
        "2026-07-19T17:32:10Z",
        "2026-07-16T12:21:57Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/data-centers/apac/osaka-japan",
    ),
    "kepco-annual-report-2025-osk1-section-captured-2026-07-19": _capture(
        "71ce079d1c6c142fe5657a9560e796eb308bcea42c136204ece84cced1738e75",
        3444339,
        "d3eb62b191c4379f5d6afb395bb4dd6348bd01791170ad0b4419a41c3c222a2d",
        "2026-07-19T17:32:29Z",
        "2026-07-19T17:32:29Z",
        "2025-11-10T07:17:13Z",
        "application/pdf",
        "https://www.kepco.co.jp/english/corporate/list/report/pdf/ar2025_e_16.pdf",
    ),
    "cyrusone-fra7-linkedin-transformer-milestone-captured-2026-07-19": _capture(
        "95ed134f976f8a5ac8e8afec29aa8dc38709e04ce4ca87c3a02aa33acd887c8f",
        369836,
        "b8ef81372f2fd4657ac9c65ec25e1308a41a034912ff70f1169f85d9b1684538",
        "2026-07-19T17:32:10Z",
        "2026-07-19T17:32:10Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/cyrusone_datacenters-digitalinfrastructure-operationalexcellence-activity-7471180193492078592-WzIz",
        activity_id="7471180193492078592",
    ),
    "cyrusone-fra7-facility-page-captured-2026-07-19": _capture(
        "36f5e6984f10b01744e8601af6aabf6fe4dc6d2c09849a869c7e0096bda5a2bd",
        86254,
        "0d3658194d04c152acd544ec3cec24ec5479529fc707376b76b0e53e82a92e35",
        "2026-07-19T17:32:10Z",
        "2026-07-19T17:32:10Z",
        "2026-07-16T12:21:59Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/data-centers/emea/frankfurt-germany-fra7",
    ),
    "cyrusone-fra7-eon-correction-captured-2026-07-19": _capture(
        "65972218302aecbfb23a2a89d90c6f173773006c06271534b668fc89dc50dfb4",
        92093,
        "fbb967a63c02ed1ac837bad945f5757968bd5e7354be7ccb9492e4c06c9def2e",
        "2026-07-19T17:32:10Z",
        "2026-07-19T17:32:10Z",
        "2026-07-16T12:21:56Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-and-e.on-announce-strategic-partnership-to-overcome-data-center-grid-capacity-constraints-for-customers-in-europe",
    ),
    "cyrusone-dfw10-identity-release-captured-2026-07-19": _capture(
        "5b830edbf087a54e19757e1a18e08fe1bb7b2ba51ab09a22f96b0a0a04fdcbc2",
        88536,
        "b4bd81240fa721586f6cff5353410bb39d19c6450f1ce78d7a7ff657a0439f98",
        "2026-07-19T18:16:02Z",
        "2026-07-19T18:16:02Z",
        "2026-07-16T12:21:52Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-and-calpine-announce-newhyperscale-data-center-development-in-texas",
        request_started_at="2026-07-19T18:16:01Z",
    ),
    "cyrusone-dfw10-phase2-release-captured-2026-07-19": _capture(
        "e8fcfe9cc09ba2ff4f92da26feed6a5b8e6119b42dcea232dbe40a76a38d255f",
        12987,
        "d4953b75406a82a830d44f33f828efff55488e1b74d35fc1af128bc94bea8b12",
        "2026-07-19T18:16:02Z",
        "2026-07-19T17:32:09Z",
        "2026-07-07T04:58:46Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/resources/press-releases/calpine-and-cyrusone-announce-phase-2-of-powered-land-agreement-to-support-hyperscale-data-center-at-thad-hill-energy-center-in-texas?hs_amp=true",
        canonical_url=(
            "https://www.cyrusone.com/resources/press-releases/"
            "calpine-and-cyrusone-announce-phase-2-of-powered-land-agreement-to-"
            "support-hyperscale-data-center-at-thad-hill-energy-center-in-texas"
        ),
    ),
    "clune-dfw10-building1-topout-captured-2026-07-19": _capture(
        "f39ea6f0f2b6fd4fcbfd036334bcded908a1be8d2fc2569b68b195a5fdc7516e",
        185683,
        "c34580af47b29f2c1be63de92b604e21c265645468d4246c0d6f1a328c1185e4",
        "2026-07-19T18:16:02Z",
        "2026-07-19T17:32:09Z",
        "2026-07-19T17:30:23Z",
        "text/html; charset=UTF-8",
        "https://www.clunegc.com/the-tech-capital-cyrusone-completes-construction-milestone-at-texas-data-centre-development/",
    ),
    "clune-dfw10-general-contractor-coverage-captured-2026-07-19": _capture(
        "e2f04f5ab2928a6d74ce3f5fe2b728f3ef0f29cc6c0d44205a74cafb6a73f6d4",
        184788,
        "91f294fb9d13aef4e6d8bfc2f0bceb4d937777440bef3dedbf34dc4001af678d",
        "2026-07-19T18:16:02Z",
        "2026-07-19T17:33:38Z",
        "2026-07-19T17:33:38Z",
        "text/html; charset=UTF-8",
        "https://www.clunegc.com/bosque-county-data-center-celebrated-by-community-in-topping-out-ceremony/",
    ),
    "cyrusone-freestone-linkedin-groundbreaking-captured-2026-07-19": _capture(
        "d607c746e2b830993501b5de74bf84daffc3367e301a2a4a7678edadb1bbcdd4",
        152370,
        "90d47470c1ca57861ef756f075c34b1382dde7c101c0d7e96578e02aab7033d6",
        "2026-07-19T17:32:10Z",
        "2026-07-19T17:32:10Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/cyrusone_datacenters-groundbreaking-digitalinfrastructure-activity-7468647950265790466-iEJj",
        activity_id="7468647950265790466",
    ),
    "cyrusone-freestone-power-agreement-captured-2026-07-19": _capture(
        "da2ef8795f7c4b1d69e67765aa389b53ac1d2e197faf0fdd02e6c4cecf2d8b15",
        92973,
        "b2ef684555ba0dc99c323818454bc7dc0ce462550d116ef6cee657f3d803ef23",
        "2026-07-19T17:32:10Z",
        "2026-07-19T17:32:10Z",
        "2026-07-16T12:21:52Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/resources/press-releases/constellation-and-cyrusone-announce-agreement-to-support-new-data-center-facility-at-freestone-energy-center-in-texas",
    ),
    "cyrusone-new-albany-linkedin-construction-captured-2026-07-19": _capture(
        "4374bd3b882bf2d2989c88fd5d73de2243f14898b397d43595c8b4d039a2a613",
        254210,
        "e1aa8d9642509e55e266ea2c34aef23beb693dbdba93e8e09076aa664e44864c",
        "2026-07-19T17:34:16Z",
        "2026-07-19T17:32:10Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/cyrusone_newalbany-ohio-datacenter-activity-7382080506374356992-G1M_",
        activity_id="7382080506374356992",
    ),
    "new-albany-cyrusone-building1-project-page-captured-2026-07-19": _capture(
        "da988568f682a9e1293b4ffd55e9568315e743e4f1b2a20712c0286677443348",
        883257,
        "daf2c6164dbc59ea5089c762f3758c4f3588d1873a3c6e38cb0c87967e2e5205",
        "2026-07-19T17:34:16Z",
        "2026-07-19T17:34:16Z",
        None,
        "text/html; charset=UTF-8",
        "https://newalbanyohio.org/community-development/project-updates/",
    ),
    "cyrusone-fra6-linkedin-demolition-captured-2026-07-19": _capture(
        "5e883277d19bd3dc0840dda0e635c9edde68cbd5d93aae481b0e517dd5bd6f46",
        384146,
        "64e0f4df004523bd8e6374100382d4d9c4bedc4a9577f47bff3e3f33a6fbac41",
        "2026-07-19T17:35:28Z",
        "2026-07-19T17:32:10Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/cyrusone_cyrusone-datacenters-frankfurt-activity-7399472066313478144-1nH_",
        activity_id="7399472066313478144",
    ),
    "carsten-schneider-fra6-personal-update-captured-2026-07-19": _capture(
        "59b269106b201d0322e3ec4f96d25862e3df680c13d601d43f2c0536daca400e",
        165755,
        "86801c7188656d4b6ea5fe45342d111b6caa76e9ea42e728a6454aa186d0b3a8",
        "2026-07-19T17:35:28Z",
        "2026-07-19T17:35:28Z",
        None,
        "text/html; charset=utf-8",
        "https://www.linkedin.com/posts/carsten-schneider-b026409a_today-members-of-my-team-took-me-to-our-cyrusone-activity-7452267748799340544-TbUx",
        activity_id="7452267748799340544",
    ),
    "cyrusone-fra6-facility-page-captured-2026-07-19": _capture(
        "4a82d8bd34944c8ff44f87c3b9e96cacc2f1cf679db1384dd803f3bcfba15e86",
        82214,
        "3d612b917e1c6aa9ff0b54f0d3bd1df7d7d5a9572cae01eb083bdd5594d4df06",
        "2026-07-19T17:35:28Z",
        "2026-07-19T17:32:10Z",
        "2026-07-16T12:21:59Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/data-centers/emea/frankfurt-germany-fra6",
    ),
    "cyrusone-fra6-europark-police-release-captured-2026-07-19": _capture(
        "86780983caa73fcb5f459b9b2c2e56788a84475d508c0669394413631b4ce150",
        87280,
        "a2d555f284d44acc7fa6e31eda407ce5abf298b98328e9ea8a4412c4eb6339ac",
        "2026-07-19T17:35:28Z",
        "2026-07-19T17:32:11Z",
        "2026-07-16T12:21:54Z",
        "text/html; charset=UTF-8",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-supports-local-police-training-initiative-at-former-europark-site-ahead-of-data-center-development",
    ),
}

EXPECTED_LIFECYCLE_ROWS = [
    (
        f"{DFW10_CAMPUS_KEY}:building-1-current-build",
        DFW10_CAMPUS_KEY,
        "shell",
        "2026-03-13",
        "authoritative_physical_status_update",
    ),
    (
        f"{DFW10_CAMPUS_KEY}:current-campus-development",
        DFW10_CAMPUS_KEY,
        "under_construction",
        "2025-11-03",
        "authoritative_physical_status_update",
    ),
    (
        "curated:cyrusone-fra6-sossenheim-campus:current-brownfield-redevelopment",
        "curated:cyrusone-fra6-sossenheim-campus",
        "site_preparation",
        "2025-11-26",
        "authoritative_physical_status_update",
    ),
    (
        "curated:cyrusone-fra7-frankfurt-westside-campus:current-multi-building-development",
        "curated:cyrusone-fra7-frankfurt-westside-campus",
        "under_construction",
        "2026-06-12",
        "authoritative_physical_status_update",
    ),
    (
        "curated:cyrusone-freestone-county-campus:initial-facility-build",
        "curated:cyrusone-freestone-county-campus",
        "under_construction",
        "2026-06-05",
        "authoritative_physical_status_update",
    ),
    (
        "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build",
        "curated:cyrusone-kep-osk1-seika-data-center",
        "under_construction",
        "2025-08-19",
        "authoritative_physical_status_update",
    ),
    (
        "curated:cyrusone-new-albany-campus:building-1-current-build",
        "curated:cyrusone-new-albany-campus",
        "under_construction",
        "2025-10-09",
        "authoritative_physical_status_update",
    ),
]

EXPECTED_CAPACITY_ROWS = [
    (DFW10_CAMPUS_KEY, "grid_connection_mw", "contracted", 400, 400, 400, "MW", None),
    (
        "curated:cyrusone-fra6-sossenheim-campus:current-brownfield-redevelopment",
        "critical_it_mw",
        "planned",
        72,
        72,
        72,
        "MW",
        None,
    ),
    (
        "curated:cyrusone-fra7-frankfurt-westside-campus",
        "critical_it_mw",
        "planned",
        81,
        81,
        81,
        "MW",
        None,
    ),
    (
        "curated:cyrusone-freestone-county-campus:initial-facility-build",
        "grid_connection_mw",
        "contracted",
        380,
        380,
        380,
        "MW",
        None,
    ),
    (
        "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build",
        "critical_it_mw",
        "planned",
        48,
        48,
        48,
        "MW",
        None,
    ),
]


class CyrusOneNextTrancheCandidateTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_candidate_guardrails(
        self, name: str, document: dict[str, Any]
    ) -> None:
        expected = SOURCES[name]
        self.assertEqual(
            set(document),
            {
                "schema_version",
                "campus",
                "project",
                "lifecycle",
                "capacities",
                "operating_models",
                "workloads",
                "evidence",
            },
        )
        self.assertEqual(document["schema_version"], "1.0")

        for entity_name, key_name, name_name in (
            ("campus", "campus_key", "campus_name"),
            ("project", "project_key", "project_name"),
        ):
            entity = document[entity_name]
            self.assertEqual(entity["stable_key"], expected[key_name])
            self.assertEqual(entity["name"], expected[name_name])
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")

        self.assertTrue(document["campus"]["name"].startswith("CyrusOne "))
        self.assertTrue(document["project"]["name"].startswith("CyrusOne "))
        if "fra6" in name:
            self.assertIn("FRA6", document["campus"]["name"])
        if "fra7" in name:
            self.assertIn("FRA7", document["campus"]["name"])

        self.assertEqual(len(document["lifecycle"]), 1)
        lifecycle = document["lifecycle"][0]
        self.assertEqual(lifecycle["entity"], "project")
        self.assertEqual(
            (lifecycle["value"], lifecycle["as_of_date"]), expected["lifecycle"]
        )
        self.assertEqual(
            lifecycle["method"], "authoritative_physical_status_update"
        )
        self.assertNotIn(
            lifecycle["value"], {"mep", "commissioning", "operational"}
        )

        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        expected_capacity = expected["capacity"]
        if expected_capacity is None:
            self.assertEqual(document["capacities"], [])
        else:
            self.assertEqual(len(document["capacities"]), 1)
            capacity = document["capacities"][0]
            for field, value in expected_capacity.items():
                self.assertEqual(capacity[field], value)
            self.assertIn(capacity["metric"], {"critical_it_mw", "grid_connection_mw"})

        evidence_by_key = {row["key"]: row for row in document["evidence"]}
        self.assertEqual(tuple(evidence_by_key), expected["evidence_keys"])
        for key, evidence in evidence_by_key.items():
            self.assertNotEqual(evidence["kind"], "satellite_imagery")
            capture = CAPTURES_BY_KEY[key]
            metadata = evidence["metadata"]
            self.assertEqual(evidence["content_hash"], capture["sha256"])
            self.assertEqual(evidence["retrieved_at"], capture["retrieved_at"])
            self.assertEqual(evidence["source_url"], capture["url"])
            self.assertEqual(metadata["canonical_url"], capture["canonical_url"])
            self.assertEqual(
                metadata["content_hash_verification"], "fetched_bytes_sha256"
            )
            self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
            self.assertEqual(
                metadata["capture_headers_sha256"], capture["headers_sha256"]
            )
            self.assertEqual(
                metadata["response_http_date"], capture["response_http_date"]
            )
            self.assertEqual(
                metadata["http_last_modified_at"], capture["last_modified"]
            )
            self.assertEqual(metadata["content_type"], capture["content_type"])
            if capture["request_started_at"] is None:
                self.assertNotIn("request_started_at", metadata)
                self.assertNotIn("request_start_utc", metadata)
            else:
                self.assertEqual(
                    metadata["request_started_at"], capture["request_started_at"]
                )
                self.assertEqual(
                    metadata["capture_request_start_sha256"],
                    "1bc71e6cd31de41bc45d939a24aeb5a3ed3175ffeb718046e0f3f814beb25f54",
                )
            if capture["activity_id"] is not None:
                self.assertEqual(
                    metadata["linkedin_activity_id"], capture["activity_id"]
                )
                self.assertIn(
                    f"activity-{capture['activity_id']}", evidence["source_url"]
                )
                self.assertIn("dynamic", metadata["linkedin_host_guardrail"])
                self.assertEqual(evidence["license"], "all-rights-reserved")

        if "osk1" in name:
            facility = evidence_by_key[
                "cyrusone-osk1-facility-page-captured-2026-07-19"
            ]["metadata"]
            utility = evidence_by_key[
                "kepco-annual-report-2025-osk1-section-captured-2026-07-19"
            ]["metadata"]
            self.assertIn("70 MVA", facility["utility_supply_as_reported"])
            self.assertIn("not converted", facility["utility_supply_guardrail"])
            self.assertEqual(utility["incoming_capacity_as_reported_mw"], 70)
            self.assertIn("conflicting", utility["incoming_capacity_guardrail"])
            self.assertEqual(
                utility["sustainability_exclusion_capture"],
                {
                    "body_bytes": 12359449,
                    "body_sha256": "f7c56d3853def62b07b6cdca625d83a8d25fb7918c8652a966afae83716435c6",
                    "headers_bytes": 1717,
                    "headers_sha256": "98fa053f3ebb1d6d74cf17f69f650d0b274c1431e67f17c9f3cd83cf210d6a58",
                    "scope": utility["sustainability_exclusion_capture"]["scope"],
                },
            )
        elif "fra7" in name:
            facility = evidence_by_key[
                "cyrusone-fra7-facility-page-captured-2026-07-19"
            ]["metadata"]
            correction = evidence_by_key[
                "cyrusone-fra7-eon-correction-captured-2026-07-19"
            ]["metadata"]
            self.assertIn("150 MVA", facility["utility_supply_as_reported"])
            self.assertEqual(
                (
                    correction["superseded_generation_as_reported_mw"],
                    correction["superseded_incremental_it_as_reported_mw"],
                    correction["superseded_total_it_as_reported_mw"],
                ),
                (61, 45, 126),
            )
            self.assertIn("No superseded value is imported", correction["capacity_guardrail"])
        elif "dfw10-current" in name:
            identity = evidence_by_key[
                "cyrusone-dfw10-identity-release-captured-2026-07-19"
            ]["metadata"]
            phase2 = evidence_by_key[
                "cyrusone-dfw10-phase2-release-captured-2026-07-19"
            ]["metadata"]
            self.assertEqual(identity["initial_agreement_as_reported_mw"], 190)
            self.assertEqual(phase2["agreement_total_as_reported_mw"], 400)
            self.assertEqual(phase2["agreement_components_as_reported_mw"], [190, 210])
            self.assertIn("not imported as separate rows", phase2["component_guardrail"])
            self.assertIn("?hs_amp=true", evidence_by_key[
                "cyrusone-dfw10-phase2-release-captured-2026-07-19"
            ]["source_url"])
            self.assertNotIn("?", phase2["canonical_url"])
        elif "dfw10-building" in name:
            topout = evidence_by_key[
                "clune-dfw10-building1-topout-captured-2026-07-19"
            ]["metadata"]
            corroboration = evidence_by_key[
                "clune-dfw10-general-contractor-coverage-captured-2026-07-19"
            ]["metadata"]
            self.assertIn("Building 1 project only", topout["status_scope"])
            self.assertIn("same-family", corroboration["source_family_guardrail"])
        elif "freestone" in name:
            social = evidence_by_key[
                "cyrusone-freestone-linkedin-groundbreaking-captured-2026-07-19"
            ]["metadata"]
            agreement = evidence_by_key[
                "cyrusone-freestone-power-agreement-captured-2026-07-19"
            ]["metadata"]
            self.assertEqual(agreement["initial_agreement_as_reported_mw"], 380)
            self.assertEqual(agreement["future_phase2_as_reported_mw"], 380)
            self.assertIn("not imported", agreement["future_phase2_guardrail"])
            self.assertIn("760 MW", agreement["aggregate_guardrail"])
            self.assertEqual(
                social["contractor_exclusion_capture"]["body_sha256"],
                "140e4c423b1f24ed3e74fa2b059bf4574769cc2696458ea8e0d1d227434f58f7",
            )
            self.assertEqual(
                social["contractor_exclusion_capture"]["headers_sha256"],
                "9fe397e02d8c84e4cdd1d8a32b6ab267a33c8eccfa1eca4dbdf8875426417b0a",
            )
        elif "new-albany" in name:
            social = evidence_by_key[
                "cyrusone-new-albany-linkedin-construction-captured-2026-07-19"
            ]["metadata"]
            city = evidence_by_key[
                "new-albany-cyrusone-building1-project-page-captured-2026-07-19"
            ]["metadata"]
            self.assertEqual(
                (
                    social["initial_capacity_as_reported_mw"],
                    social["scaled_capacity_as_reported_mw"],
                    social["video_transcript_full_build_as_reported"],
                ),
                (36, 180, "more than 200 MW"),
            )
            self.assertIn("conflicts", social["capacity_guardrail"])
            self.assertIn("COL-1", social["label_guardrail"])
            self.assertIn("Cologix COL1", social["label_guardrail"])
            self.assertEqual(city["project_label_as_reported"], "CyrusOne, Building 1")
            for entity_name in ("campus", "project"):
                self.assertNotIn("COL-1", document[entity_name]["name"])
                self.assertNotIn("COL1", document[entity_name]["stable_key"])
            for evidence in document["evidence"]:
                self.assertNotIn("COL-1", evidence["title"])
        elif "fra6" in name:
            personal = evidence_by_key[
                "carsten-schneider-fra6-personal-update-captured-2026-07-19"
            ]["metadata"]
            facility = evidence_by_key[
                "cyrusone-fra6-facility-page-captured-2026-07-19"
            ]["metadata"]
            demolition = evidence_by_key[
                "cyrusone-fra6-linkedin-demolition-captured-2026-07-19"
            ]["metadata"]
            self.assertEqual(personal["substation_capacity_as_reported"], "greater than 80 MWIT")
            self.assertIn("open-bound", personal["substation_capacity_guardrail"])
            self.assertEqual(facility["capacity_components_as_reported"], "four floors at 18 MW each")
            self.assertIn("not imported or summed again", facility["component_guardrail"])
            self.assertIn("demolition", demolition["status_scope"])

    def _assert_no_pretranche_collisions(self) -> None:
        target_keys = {
            expected[field]
            for expected in SOURCES.values()
            for field in ("campus_key", "project_key")
        }
        target_names = {
            expected[field]
            for expected in SOURCES.values()
            for field in ("campus_name", "project_name")
        }
        target_evidence_keys = set(CAPTURES_BY_KEY)
        target_urls = {capture["url"] for capture in CAPTURES_BY_KEY.values()}
        target_hashes = {capture["sha256"] for capture in CAPTURES_BY_KEY.values()}

        for path in sorted((ROOT / "sources").glob("curated-*.json")):
            if path.name in SOURCES:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if not isinstance(entity, dict):
                    continue
                self.assertNotIn(entity.get("stable_key"), target_keys, path.name)
                self.assertNotIn(entity.get("name"), target_names, path.name)
            for evidence in document.get("evidence", []):
                self.assertNotIn(evidence.get("key"), target_evidence_keys, path.name)
                self.assertNotIn(evidence.get("source_url"), target_urls, path.name)
                self.assertNotIn(evidence.get("content_hash"), target_hashes, path.name)

    def test_exact_candidates_import_offline_with_narrow_semantics(self) -> None:
        self._assert_no_pretranche_collisions()
        v13_definition = (
            ROOT / "sources" / "open-seed-2026-07-19-v13.json"
        ).read_text(encoding="utf-8")
        documents: dict[str, dict[str, Any]] = {}
        observed_evidence: dict[str, tuple[str, str]] = {}
        observed_url_to_key: dict[str, str] = {}
        observed_hash_to_key: dict[str, str] = {}

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected in SOURCES.items():
                        self.assertNotIn(name, v13_definition)
                        self.assertNotIn(expected["campus_key"], v13_definition)
                        self.assertNotIn(expected["project_key"], v13_definition)
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected["sha256"],
                        )
                        document = self._load(name)
                        documents[name] = document
                        self._assert_candidate_guardrails(name, document)
                        for evidence in document["evidence"]:
                            identity = (
                                evidence["content_hash"], evidence["source_url"]
                            )
                            previous = observed_evidence.setdefault(evidence["key"], identity)
                            self.assertEqual(previous, identity)
                            previous_key = observed_url_to_key.setdefault(
                                evidence["source_url"], evidence["key"]
                            )
                            self.assertEqual(previous_key, evidence["key"])
                            previous_key = observed_hash_to_key.setdefault(
                                evidence["content_hash"], evidence["key"]
                            )
                            self.assertEqual(previous_key, evidence["key"])
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=max(
                                row["retrieved_at"] for row in document["evidence"]
                            ),
                        )

                self.assertEqual(set(observed_evidence), set(CAPTURES_BY_KEY))
                current_dfw = documents[
                    "curated-official-2026-07-19-cyrusone-dfw10-current-campus-development.json"
                ]
                building_dfw = documents[
                    "curated-official-2026-07-19-cyrusone-dfw10-building-1.json"
                ]
                self.assertEqual(current_dfw["campus"], building_dfw["campus"])
                self.assertEqual(current_dfw["evidence"][0], building_dfw["evidence"][0])

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 6), ("project", 7)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT project_entity.stable_key,
                               campus_entity.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities AS project_entity
                          ON project_entity.id = lifecycle_observations.entity_id
                        JOIN projects ON projects.entity_id = project_entity.id
                        JOIN entities AS campus_entity
                          ON campus_entity.id = projects.target_entity_id
                        ORDER BY project_entity.stable_key
                        """
                    )],
                    EXPECTED_LIFECYCLE_ROWS,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key, capacity_estimates.metric,
                               capacity_estimates.stage, capacity_estimates.low,
                               capacity_estimates.base, capacity_estimates.high,
                               capacity_estimates.unit, capacity_estimates.target_date
                        FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    EXPECTED_CAPACITY_ROWS,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    18,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
                    13,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL "
                        "OR longitude IS NOT NULL OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates WHERE metric NOT IN "
                        "('critical_it_mw', 'grid_connection_mw')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    {row[0] for row in connection.execute(
                        "SELECT content_hash FROM evidence"
                    )},
                    {capture["sha256"] for capture in CAPTURES_BY_KEY.values()},
                )
                self.assertTrue(
                    all(
                        evidence["kind"] != "satellite_imagery"
                        for document in documents.values()
                        for evidence in document["evidence"]
                    )
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_candidate_guardrails(self) -> None:
        osk_name = "curated-official-2026-07-19-cyrusone-osk1-seika.json"
        fra7_name = (
            "curated-official-2026-07-19-cyrusone-fra7-frankfurt-westside.json"
        )
        dfw_name = (
            "curated-official-2026-07-19-cyrusone-dfw10-current-campus-development.json"
        )
        dfw_building_name = (
            "curated-official-2026-07-19-cyrusone-dfw10-building-1.json"
        )
        freestone_name = (
            "curated-official-2026-07-19-cyrusone-freestone-initial-facility.json"
        )
        new_albany_name = (
            "curated-official-2026-07-19-cyrusone-new-albany-building-1.json"
        )
        fra6_name = "curated-official-2026-07-19-cyrusone-fra6-sossenheim.json"
        originals = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, Any]]] = []

        def changed(name: str) -> dict[str, Any]:
            return copy.deepcopy(originals[name])

        mutated = changed(new_albany_name)
        mutated["project"]["name"] = "CyrusOne COL-1"
        mutations.append((new_albany_name, mutated))

        mutated = changed(fra7_name)
        mutated["campus"]["name"] = "FRA7 Frankfurt Campus"
        mutations.append((fra7_name, mutated))

        mutated = changed(fra6_name)
        mutated["campus"]["name"] = "Digital Realty FRA6 Campus"
        mutations.append((fra6_name, mutated))

        mutated = changed(dfw_building_name)
        mutated["campus"]["stable_key"] += ":building-1"
        mutations.append((dfw_building_name, mutated))

        mutated = changed(dfw_name)
        mutated["capacities"][0]["metric"] = "critical_it_mw"
        mutations.append((dfw_name, mutated))

        mutated = changed(dfw_name)
        component = copy.deepcopy(mutated["capacities"][0])
        component.update({"low": 190, "base": 190, "high": 190})
        mutated["capacities"].append(component)
        mutations.append((dfw_name, mutated))

        mutated = changed(dfw_building_name)
        mutated["capacities"] = [
            _capacity("project", "grid_connection_mw", "contracted", 400, "2025-11-03")
        ]
        mutations.append((dfw_building_name, mutated))

        mutated = changed(osk_name)
        mutated["capacities"][0].update(
            {"metric": "grid_connection_mw", "low": 70, "base": 70, "high": 70}
        )
        mutations.append((osk_name, mutated))

        mutated = changed(fra7_name)
        mutated["capacities"][0].update({"low": 126, "base": 126, "high": 126})
        mutations.append((fra7_name, mutated))

        mutated = changed(freestone_name)
        mutated["capacities"][0]["metric"] = "critical_it_mw"
        mutations.append((freestone_name, mutated))

        mutated = changed(freestone_name)
        mutated["capacities"][0].update({"low": 760, "base": 760, "high": 760})
        mutations.append((freestone_name, mutated))

        mutated = changed(new_albany_name)
        mutated["capacities"] = [
            _capacity("project", "critical_it_mw", "planned", 180, "2026-07-19")
        ]
        mutations.append((new_albany_name, mutated))

        mutated = changed(fra6_name)
        mutated["capacities"][0].update({"low": 80, "base": 80, "high": 80})
        mutations.append((fra6_name, mutated))

        mutated = changed(fra6_name)
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((fra6_name, mutated))

        mutated = changed(osk_name)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append((osk_name, mutated))

        mutated = changed(freestone_name)
        mutated["project"]["roles"] = {"contractor": ["Rogers-O'Brien"]}
        mutations.append((freestone_name, mutated))

        mutated = changed(new_albany_name)
        mutated["campus"]["coordinates"] = {
            "latitude": 40.1,
            "longitude": -82.8,
        }
        mutations.append((new_albany_name, mutated))

        mutated = changed(fra7_name)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-06-12",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append((fra7_name, mutated))

        mutated = changed(fra6_name)
        pue = copy.deepcopy(mutated["capacities"][0])
        pue.update({"metric": "pue", "unit": "ratio", "low": 1.2, "base": 1.2, "high": 1.2})
        mutated["capacities"].append(pue)
        mutations.append((fra6_name, mutated))

        mutated = changed(osk_name)
        mutated["capacities"][0]["target_date"] = "2028-03-31"
        mutations.append((osk_name, mutated))

        mutated = changed(dfw_name)
        mutated["evidence"][1]["metadata"]["agreement_components_as_reported_mw"] = [400]
        mutations.append((dfw_name, mutated))

        mutated = changed(freestone_name)
        mutated["evidence"][1]["metadata"]["future_phase2_guardrail"] = "import it"
        mutations.append((freestone_name, mutated))

        mutated = changed(osk_name)
        mutated["evidence"][0]["kind"] = "satellite_imagery"
        mutations.append((osk_name, mutated))

        for name, document in mutations:
            with self.subTest(source=name):
                with self.assertRaises(AssertionError):
                    self._assert_candidate_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
