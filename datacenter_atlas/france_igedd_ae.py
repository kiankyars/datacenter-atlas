"""Bounded France IGEDD environmental-authority data-centre assessment.

The closed archive is the 17 annual IGEDD Ae opinion indexes for 2009-2025.
The current 2026 index is requested as part of the transport audit but is not
counted as closed-set coverage because the canonical official route returned
404 during capture.  One directly fetched 2026 official PDF is retained as a
separate supplemental follow-up observation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-france-igedd-ae-release-v1"
DEFINITION_FORMAT = "datacenter-atlas-france-igedd-ae-definition-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-france-igedd-ae-assessment-v1"
ANNUAL_INVENTORY_FORMAT = "datacenter-atlas-france-igedd-annual-index-inventory-v1"
OBSERVATION_FORMAT = "datacenter-atlas-france-igedd-observation-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-france-igedd-retrieval-inventory-v1"
SOURCE_INVENTORY_FORMAT = "datacenter-atlas-france-igedd-source-inventory-v1"
SCHEMA_FORMAT = "datacenter-atlas-france-igedd-schema-v1"
CAPTURE_FORMAT = "datacenter-atlas-france-igedd-quarantine-capture-v1"

BASE_URL = "https://www.igedd.developpement-durable.gouv.fr/"
RIGHTS_URL = urljoin(BASE_URL, "mentions-legales-a3434.html?lang=fr")
OPEN_LICENCE_URL = "https://github.com/etalab/licence-ouverte/blob/master/LO.md"
CURRENT_2026_URL = urljoin(
    BASE_URL,
    "autorite-environnementale-les-avis-deliberes-2026-a4348.html?lang=fr",
)
OFFICIAL_HOST = "www.igedd.developpement-durable.gouv.fr"

ANNUAL_INDEX_URLS = {
    2009: urljoin(BASE_URL, "les-avis-rendus-en-2009-a1164.html"),
    2010: urljoin(BASE_URL, "les-avis-rendus-en-2010-a1165.html"),
    2011: urljoin(BASE_URL, "les-avis-rendus-en-2011-a1242.html"),
    2012: urljoin(BASE_URL, "les-avis-rendus-en-2012-a1430.html"),
    2013: urljoin(BASE_URL, "les-avis-rendus-en-2013-a1571.html"),
    2014: urljoin(BASE_URL, "les-avis-rendus-en-2014-a1911.html"),
    2015: urljoin(BASE_URL, "les-avis-rendus-en-2015-a2126.html"),
    2016: urljoin(BASE_URL, "les-avis-rendus-en-2016-a2353.html"),
    2017: urljoin(BASE_URL, "les-avis-rendus-en-2017-a2540.html"),
    2018: urljoin(BASE_URL, "les-avis-rendus-en-2018-a2708.html"),
    2019: urljoin(BASE_URL, "les-avis-rendus-en-2019-a2896.html"),
    2020: urljoin(BASE_URL, "les-avis-rendus-en-2020-a3040.html"),
    2021: urljoin(BASE_URL, "les-avis-rendus-en-2021-a3212.html"),
    2022: urljoin(BASE_URL, "les-avis-deliberes-2022-a3039.html"),
    2023: urljoin(BASE_URL, "les-avis-deliberes-en-2023-a3660.html"),
    2024: urljoin(
        BASE_URL,
        "autorite-environnementale-les-avis-deliberes-2024-a3916.html",
    ),
    2025: urljoin(
        BASE_URL,
        "autorite-environnementale-les-avis-deliberes-2025-a4113.html",
    ),
    2026: CURRENT_2026_URL,
}

TITLE_TERMS_EXACT = (
    "centre de données",
    "centres de données",
    "data center",
    "data centers",
    "data centre",
    "data centres",
    "datacenter",
    "datacenters",
    "data-center",
    "data-centers",
    "data-centre",
    "data-centres",
)
TITLE_TERM_RE = re.compile(
    r"(?:\bcentres?\s+de\s+donn(?:ée|ee)s\b|"
    r"\bdata(?:\s+|-)cent(?:er|re)s?\b|\bdatacenters?\b)",
    flags=re.IGNORECASE,
)

EXPECTED_ARCHIVE_MATCH_COUNTS = {
    year: (1 if year in {2021, 2024, 2025} else 0)
    for year in range(2009, 2026)
}
EXPECTED_ARCHIVE_MATCHES = {
    2021: {
        "title": "Création de deux centres de données - Les Ulis (91)",
        "url": urljoin(
            BASE_URL,
            "IMG/pdf/211209_centre_donnees_ulis91_delibere_cle26febf.pdf",
        ),
    },
    2024: {
        "title": (
            "Création et l'exploitation du centre de données informatiques "
            "Dugny Digital Hub sur la commune de Dugny (93)"
        ),
        "url": urljoin(
            BASE_URL,
            "IMG/pdf/240411_centre_donnees_dugny_digital_hub_93_"
            "debattu_corrige_cle565e1b.pdf",
        ),
    },
    2025: {
        "title": "Création du centre de données « Digital MRS6 » Bouc Bel Air (13)",
        "url": urljoin(
            BASE_URL,
            "IMG/pdf/4_-_centre_de_donnees_a_bouc-bel-air_13__cle71f681.pdf",
        ),
    },
}

SUPPLEMENTAL_2026 = {
    "classification": "ancillary_grid_connection_follow_up",
    "discovery_note": (
        "The official current-year index was visible through official web indexing, "
        "but its canonical origin route returned HTTP 404 to the capture client. "
        "The official PDF was fetched directly and is not counted in the closed "
        "2009-2025 archive query."
    ),
    "index_title_observed": "Raccordement du data Center MRS6 à Bouc-Bel Air",
    "pdf_url": urljoin(
        BASE_URL,
        "IMG/pdf/3-raccordement_du_data_center_mrs6_a_bouc-bel_air_cle0e31c4.pdf",
    ),
    "year": 2026,
}

DOCUMENTS = {
    "igedd-ae-2021-104": {
        "annual_index_year": 2021,
        "bytes": 1_285_130,
        "docket_number_exact": "2021-104",
        "opinion_date": "2021-12-09",
        "pages": 25,
        "sha256": "4e1a270dfc8fc9b53ab966161e3d2055d345509b629444868cdbf19fc82495ec",
        "url": EXPECTED_ARCHIVE_MATCHES[2021]["url"],
    },
    "igedd-ae-2024-08": {
        "annual_index_year": 2024,
        "bytes": 1_346_001,
        "docket_number_exact": "2024-08",
        "opinion_date": "2024-04-11",
        "pages": 27,
        "sha256": "67d4dfecd9ac58e2e3ac0866d3456db0906a9b07fc000779ee1ba9260a3c483a",
        "url": EXPECTED_ARCHIVE_MATCHES[2024]["url"],
    },
    "igedd-ae-2025-058": {
        "annual_index_year": 2025,
        "bytes": 947_558,
        "docket_number_exact": "2025-058",
        "opinion_date": "2025-06-12",
        "pages": 23,
        "sha256": "151d5fc006e5f4e2f702db0ece3f89a4eb5182653711cdbd0ddab97bd46eba76",
        "url": EXPECTED_ARCHIVE_MATCHES[2025]["url"],
    },
    "igedd-ae-2026-33": {
        "annual_index_year": None,
        "bytes": 1_646_421,
        "docket_number_exact": "2026-33",
        "opinion_date": "2026-06-11",
        "pages": 19,
        "sha256": "bcb9939e72aafd1f57239c03b80828b951f0c72a3a509f281e2beff5318fae99",
        "url": SUPPLEMENTAL_2026["pdf_url"],
    },
}

MAX_NETWORK_REQUESTS = 30
EXPECTED_NETWORK_REQUESTS = 23
EXPECTED_SUCCESSFUL_REQUESTS = 22
EXPECTED_RAW_ARTIFACTS = 23
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_ATTEMPTS_PER_REQUEST = 2
EXPECTED_DIRECT_PROJECTS = 3
EXPECTED_FOLLOW_UPS = 1
EXPECTED_UNIQUE_PROJECT_SITES = 3
EXPECTED_PLANNED_DATA_CENTRE_UNITS = 6

RIGHTS_POLICY = {
    "attribution_required": True,
    "derived_factual_rows_publication_eligible": True,
    "document_redistribution_in_release": False,
    "legal_conclusion_claimed": False,
    "license_name": "Licence Ouverte / Open Licence Etalab 2.0",
    "license_url": OPEN_LICENCE_URL,
    "pdf_reproduction_conditions_found": {
        "free_distribution": True,
        "integrity_required": True,
        "source_citation_required": True,
        "rights_reserved_and_strictly_limited_wording": True,
    },
    "raw_html_or_pdf_released": False,
    "site_content_open_absent_explicit_ip_notice": True,
    "source_terms_url": RIGHTS_URL,
    "verified_local_date": "2026-07-18",
}

LIFECYCLE_BOUNDARY = {
    "atlas_lifecycle_status": None,
    "construction_verified": False,
    "environmental_opinion_is_development_consent": False,
    "environmental_opinion_is_physical_construction_evidence": False,
    "operation_verified": False,
    "source_process_status": "environmental_authority_opinion_issued",
}

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
DERIVED_FILENAMES = {
    "ATTRIBUTION.txt",
    "README.md",
    "annual-index-inventory.json",
    "assessment.json",
    "definition.json",
    "observations.jsonl",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
}


class FranceIGEDDAEError(ValueError):
    """Raised when the bounded official-source contract changes."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def jsonl(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(dict(row)) for row in rows)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FranceIGEDDAEError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FranceIGEDDAEError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FranceIGEDDAEError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FranceIGEDDAEError(f"{field} must be an object")
    return value


def _official_url(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise FranceIGEDDAEError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST:
        raise FranceIGEDDAEError(f"{field} is outside the official IGEDD host")
    return value


def _plain_text(markup: str) -> str:
    class PlainTextParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self.parts.append(data)

    parser = PlainTextParser()
    parser.feed(markup)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href is not None:
            text = " ".join("".join(self.current_text).split())
            self.links.append((self.current_href, unescape(text)))
            self.current_href = None
            self.current_text = []


def title_matches_exact_terms(title: str) -> bool:
    return TITLE_TERM_RE.search(" ".join(title.split())) is not None


def _strip_download_suffix(title: str) -> str:
    return re.sub(
        r"\s+pdf\s*-\s*[\d.,]+\s*(?:kio|mio)\s*$",
        "",
        " ".join(title.split()),
        flags=re.IGNORECASE,
    )


def parse_annual_index(body: bytes, *, year: int, source_url: str) -> list[dict[str, str]]:
    if year not in range(2009, 2026):
        raise FranceIGEDDAEError("only the closed 2009-2025 archive is parseable")
    if source_url != ANNUAL_INDEX_URLS[year]:
        raise FranceIGEDDAEError("annual index URL differs from the closed contract")
    try:
        markup = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FranceIGEDDAEError("annual index is not UTF-8") from error
    if str(year) not in _plain_text(markup):
        raise FranceIGEDDAEError("annual index does not identify its year")
    parser = _LinkParser()
    parser.feed(markup)
    parser.close()
    matches: list[dict[str, str]] = []
    for href, display_title in parser.links:
        absolute = urljoin(source_url, href)
        if not urlsplit(absolute).path.lower().endswith(".pdf"):
            continue
        title = _strip_download_suffix(display_title)
        if not title_matches_exact_terms(title):
            continue
        _official_url(absolute, "annual PDF link")
        matches.append({"title": title, "url": absolute})
    matches.sort(key=lambda row: (row["title"].casefold(), row["url"]))
    expected_count = EXPECTED_ARCHIVE_MATCH_COUNTS[year]
    if len(matches) != expected_count:
        raise FranceIGEDDAEError(f"annual title-match count changed for {year}")
    if expected_count and matches != [EXPECTED_ARCHIVE_MATCHES[year]]:
        raise FranceIGEDDAEError(f"annual title match changed for {year}")
    return matches


def verify_rights_page(body: bytes) -> dict[str, bool]:
    try:
        text = _plain_text(body.decode("utf-8")).casefold()
    except UnicodeDecodeError as error:
        raise FranceIGEDDAEError("rights page is not UTF-8") from error
    checks = {
        "free_distribution": "gratuité de la diffusion" in text,
        "integrity_required": "respect de l’intégrité des documents reproduits" in text,
        "open_absent_explicit_ip": (
            "sauf mention explicite de propriété intellectuelle" in text
            and "licence ouverte" in text
        ),
        "rights_reserved_and_strictly_limited_wording": (
            "droits de reproduction sont réservés et strictement limités" in text
        ),
        "source_citation_required": "citation explicite du site de l’igedd" in text,
    }
    if not all(checks.values()):
        raise FranceIGEDDAEError("IGEDD rights language changed")
    return checks


def _metric(
    metric_type: str,
    value: float,
    unit: str,
    scope: str,
    qualifier: str,
    source_page_label: int,
) -> dict[str, Any]:
    return {
        "metric_type": metric_type,
        "qualifier": qualifier,
        "scope": scope,
        "source_page_label": source_page_label,
        "unit": unit,
        "value": value,
    }


def curated_observations() -> list[dict[str, Any]]:
    observations = [
        {
            "annual_index_year": 2021,
            "atlas_data_centre_type": None,
            "classification": "direct_data_centre_project",
            "country_code": "FR",
            "data_centre_unit_count": 2,
            "department": "Essonne (91)",
            "document_id": "igedd-ae-2021-104",
            "document_title": "Création de deux centres de données – Les Ulis (91)",
            "environmental_review": dict(LIFECYCLE_BOUNDARY),
            "location": "Parc d’activités de Courtabœuf, Les Ulis",
            "metrics": [
                _metric(
                    "it_power_capacity",
                    60,
                    "MW",
                    "DC1 information-technology uses",
                    "source-reported planned at-term capacity; not gross site power",
                    5,
                ),
                _metric(
                    "it_power_capacity",
                    36,
                    "MW",
                    "DC2 information-technology uses",
                    "source-reported planned at-term capacity; not gross site power",
                    5,
                ),
                _metric(
                    "backup_generation_thermal_capacity",
                    423,
                    "MWth",
                    "64 emergency generators",
                    "backup generation; never mapped to IT or facility load",
                    5,
                ),
                _metric(
                    "backup_generation_electrical_capacity",
                    123,
                    "MWe",
                    "56 concurrently usable generators plus 8 redundant units",
                    "backup generation; never mapped to IT or facility load",
                    10,
                ),
                _metric(
                    "ups_and_battery_power",
                    97,
                    "MW",
                    "project UPS and batteries",
                    "electrical support equipment; not IT load",
                    5,
                ),
            ],
            "observation_id": "fr-igedd-ae-2021-104",
            "planned_annual_electricity_consumption": None,
            "project_configuration": "two_data_centre_buildings_one_project_site",
            "project_group_id": "digital-les-ulis",
            "project_name": "Digital Les Ulis",
            "site_group_id": "les-ulis-courtaboeuf",
            "source_scope_note": (
                "The opinion explicitly says annual electricity consumption and "
                "consumed power were not specified."
            ),
        },
        {
            "annual_index_year": 2024,
            "atlas_data_centre_type": None,
            "classification": "direct_data_centre_project",
            "country_code": "FR",
            "data_centre_unit_count": 3,
            "department": "Seine-Saint-Denis (93)",
            "document_id": "igedd-ae-2024-08",
            "document_title": (
                "Création et exploitation du centre de données informatiques "
                "Dugny Digital Hub à Dugny (93)"
            ),
            "environmental_review": dict(LIFECYCLE_BOUNDARY),
            "location": "Dugny, adjacent to Paris-Le Bourget airport",
            "metrics": [
                _metric(
                    "projected_full_load_annual_electricity_consumption",
                    1930,
                    "GWh/year",
                    "Dugny Digital Hub project",
                    (
                        "theoretical full-load estimate at 100 percent occupancy and "
                        "100 percent server load; not measured consumption"
                    ),
                    16,
                ),
                _metric(
                    "target_pue",
                    1.3,
                    "ratio",
                    "Dugny Digital Hub project",
                    "operator target; not measured operating PUE",
                    18,
                ),
                _metric(
                    "backup_generation_thermal_capacity",
                    814,
                    "MWth",
                    "maximum 108 emergency generators",
                    "backup generation; never mapped to IT or facility load",
                    5,
                ),
                _metric(
                    "backup_generation_electrical_capacity",
                    324,
                    "MWe",
                    "maximum 108 emergency generators",
                    "backup generation; never mapped to IT or facility load",
                    5,
                ),
                _metric(
                    "battery_maximum_recharge_power",
                    283,
                    "MW",
                    "project batteries",
                    "support equipment recharge maximum; not IT load",
                    6,
                ),
            ],
            "observation_id": "fr-igedd-ae-2024-08",
            "planned_annual_electricity_consumption": {
                "qualifier": "theoretical_full_load_not_measured",
                "unit": "GWh/year",
                "value": 1930,
            },
            "project_configuration": "three_data_centres_one_project_site",
            "project_group_id": "dugny-digital-hub",
            "project_name": "Dugny Digital Hub",
            "site_group_id": "dugny-digital-hub-site",
            "source_scope_note": (
                "The three source-named centres are PAR15, PAR16, and PAR17. "
                "The opinion's projected works window is not used as lifecycle proof."
            ),
        },
        {
            "annual_index_year": 2025,
            "atlas_data_centre_type": None,
            "classification": "direct_data_centre_project",
            "country_code": "FR",
            "data_centre_unit_count": 1,
            "department": "Bouches-du-Rhône (13)",
            "document_id": "igedd-ae-2025-058",
            "document_title": "Création du centre de données Digital MRS6 à Bouc-Bel-Air (13)",
            "environmental_review": dict(LIFECYCLE_BOUNDARY),
            "location": "Zone d’activités des Chabauds, Bouc-Bel-Air",
            "metrics": [
                _metric(
                    "projected_annual_site_electricity_consumption",
                    245,
                    "GWh/year",
                    "Digital MRS6 site",
                    "source-reported project consumption; not measured operation",
                    15,
                ),
                _metric(
                    "backup_generation_thermal_capacity",
                    219,
                    "MWth",
                    "30 IT-room and 2 office emergency generators",
                    "backup generation; never mapped to IT or facility load",
                    7,
                ),
            ],
            "observation_id": "fr-igedd-ae-2025-058",
            "planned_annual_electricity_consumption": {
                "qualifier": "source_reported_project_not_measured",
                "unit": "GWh/year",
                "value": 245,
            },
            "project_configuration": "one_data_centre_in_existing_warehouse_redevelopment",
            "project_group_id": "digital-mrs6",
            "project_name": "Digital MRS6",
            "site_group_id": "bouc-bel-air-digital-mrs6",
            "source_scope_note": (
                "The source says 90 percent of electricity is mainly attributable "
                "to hosted IT equipment; no derived IT-energy value is calculated."
            ),
        },
        {
            "annual_index_year": None,
            "atlas_data_centre_type": None,
            "classification": "ancillary_grid_connection_follow_up",
            "country_code": "FR",
            "data_centre_unit_count": 0,
            "department": "Bouches-du-Rhône (13)",
            "document_id": "igedd-ae-2026-33",
            "document_title": (
                "Création du centre de données Digital MRS6 – 2e avis - "
                "actualisation : opération de raccordement au réseau public "
                "de transport d’électricité"
            ),
            "environmental_review": dict(LIFECYCLE_BOUNDARY),
            "location": "Bouc-Bel-Air and Cabriès",
            "metrics": [
                _metric(
                    "requested_grid_connection_power",
                    80,
                    "MW",
                    "MRS6 grid connection request",
                    "connection request; not IT capacity, facility load, or consumption",
                    4,
                )
            ],
            "observation_id": "fr-igedd-ae-2026-33",
            "planned_annual_electricity_consumption": None,
            "project_configuration": "grid_connection_follow_up_only",
            "project_group_id": "digital-mrs6",
            "project_name": "Digital MRS6 connection follow-up",
            "related_direct_observation_id": "fr-igedd-ae-2025-058",
            "site_group_id": "bouc-bel-air-digital-mrs6",
            "source_scope_note": (
                "Supplemental directly fetched official PDF. The opinion concerns "
                "only the RTE connection and is not a new data-centre project or site."
            ),
        },
    ]
    for row in observations:
        document = DOCUMENTS[row["document_id"]]
        row["document_sha256"] = document["sha256"]
        row["document_url"] = document["url"]
        row["format"] = OBSERVATION_FORMAT
        row["opinion_date"] = document["opinion_date"]
        row["docket_number_exact"] = document["docket_number_exact"]
        row["physical_unique_site_count_contribution"] = (
            1 if row["classification"] == "direct_data_centre_project" else 0
        )
    return observations


EXPECTED_OBSERVATIONS_SHA256 = (
    "9f9e91325049f66e1ad7b65fe329030e9725518404aa10540bd66942fcf8522e"
)


def source_definition() -> dict[str, Any]:
    return {
        "format": DEFINITION_FORMAT,
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "country": "France",
            "name": "IGEDD Autorité environnementale annual opinion indexes",
            "publisher": (
                "Inspection générale de l’Environnement et du Développement durable"
            ),
            "url": ANNUAL_INDEX_URLS[2025],
        },
        "scope": {
            "annual_index_urls": {
                str(year): url for year, url in ANNUAL_INDEX_URLS.items()
            },
            "archive_closed_years": list(range(2009, 2026)),
            "archive_title_terms_exact": list(TITLE_TERMS_EXACT),
            "current_2026_origin_capture_complete": False,
            "current_2026_status": (
                "canonical official page returned HTTP 404; supplemental PDF only"
            ),
            "france_complete": False,
            "regional_environmental_authorities_in_scope": False,
        },
        "retrieval_policy": {
            "allowed_hosts": [OFFICIAL_HOST],
            "expected_first_attempt_requests": EXPECTED_NETWORK_REQUESTS,
            "maximum_attempts_per_request": MAX_ATTEMPTS_PER_REQUEST,
            "maximum_network_requests": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "pdfs_released": False,
            "raw_destination": "operator-supplied quarantine outside release",
        },
        "rights_policy": RIGHTS_POLICY,
        "release_policy": {
            "derived_factual_rows_released": True,
            "pdf_or_raw_html_released": False,
            "status": "open_derived_facts_pdf_redistribution_excluded",
        },
        "update_policy": {
            "immutable_release": True,
            "recommended_refresh": "new dated release after origin-access recheck",
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:datacenter-atlas:{RELEASE_ID}:assessment",
        "additionalProperties": True,
        "format": SCHEMA_FORMAT,
        "properties": {
            "assessment_id": {"const": RELEASE_ID},
            "format": {"const": ASSESSMENT_FORMAT},
            "schema_version": {"const": SCHEMA_VERSION},
        },
        "required": ["assessment_id", "format", "schema_version"],
        "schema_version": SCHEMA_VERSION,
        "title": "France IGEDD Ae data-centre bounded source assessment",
        "type": "object",
    }


def attribution_text() -> str:
    return (
        "Source: Inspection générale de l’Environnement et du Développement durable "
        "(IGEDD), Autorité environnementale\n"
        "Annual opinion indexes and the four exact opinion documents listed in "
        "source-inventory.json\n"
        f"Terms: {RIGHTS_URL}\n"
        "Licence: Licence Ouverte / Open Licence Etalab 2.0 — "
        f"{OPEN_LICENCE_URL}\n"
        "Captured: 2026-07-18 local audit date; exact UTC retrieval times are in "
        "retrieval-inventory.json\n\n"
        "This release contains attributed derived facts and hashes, not IGEDD HTML "
        "or PDF files.\n"
    )


def readme_text() -> str:
    return f"""# France IGEDD Ae bounded data-centre assessment

This release scans the 17 official annual Ae opinion indexes for 2009-2025
with the exact multilingual title terms recorded in `definition.json`. It finds
three direct project opinions: Digital Les Ulis (two centres on one project
site), Dugny Digital Hub (three centres on one project site), and Digital MRS6
(one centre). That is three project observations, three source-supported sites,
and six planned data-centre units. It is not a France-wide facility census.

The canonical official 2026 annual page returned HTTP 404 to the capture
client, including with `?lang=fr`. Current-year recall is therefore incomplete
and 2026 is not included in the closed annual-index match count. A directly
fetched official 2026 opinion PDF is preserved only as a separate supplemental
grid-connection follow-up to MRS6. It is not a fourth project or site.

An IGEDD environmental opinion is process evidence, not development consent or
proof of physical construction or operation. Every observation therefore keeps
atlas lifecycle status null. Power and energy fields retain their source scope:
IT capacity, theoretical full-load consumption, projected site consumption,
backup generation, batteries, and requested grid connection are never
interchanged or converted.

The site states that content without an explicit intellectual-property notice
is under the Etalab Open Licence 2.0. Its legal notice also gives conditions for
document reproduction, including free distribution, integrity, attribution,
and rights-reserved wording. This release conservatively publishes attributed
derived facts, URLs, and hashes only. No source HTML or PDF is redistributed.
This is a source-governance decision, not legal advice.
"""


def validate_capture_state_hash(capture: Mapping[str, Any]) -> str:
    supplied = capture.get("capture_state_sha256")
    if not isinstance(supplied, str) or re.fullmatch(r"[0-9a-f]{64}", supplied) is None:
        raise FranceIGEDDAEError("capture-state hash is invalid")
    unhashed = dict(capture)
    del unhashed["capture_state_sha256"]
    if sha256_bytes(canonical_json(unhashed)) != supplied:
        raise FranceIGEDDAEError("capture-state hash mismatch")
    return supplied


def _validate_capture(capture: Mapping[str, Any]) -> None:
    if (
        capture.get("format") != CAPTURE_FORMAT
        or capture.get("release_id") != RELEASE_ID
        or capture.get("schema_version") != SCHEMA_VERSION
    ):
        raise FranceIGEDDAEError("capture identity changed")
    _timestamp(capture.get("captured_at"), "captured_at")
    validate_capture_state_hash(capture)
    if capture.get("network_attempt_count") != EXPECTED_NETWORK_REQUESTS:
        raise FranceIGEDDAEError("capture network-attempt count changed")
    if capture.get("successful_request_count") != EXPECTED_SUCCESSFUL_REQUESTS:
        raise FranceIGEDDAEError("capture successful-request count changed")
    annual = capture.get("annual_indexes")
    retrievals = capture.get("retrievals")
    documents = capture.get("documents")
    if not isinstance(annual, list) or len(annual) != 18:
        raise FranceIGEDDAEError("capture annual-index inventory changed")
    if not isinstance(retrievals, list) or len(retrievals) != EXPECTED_RAW_ARTIFACTS:
        raise FranceIGEDDAEError("capture retrieval inventory changed")
    if not isinstance(documents, list) or len(documents) != len(DOCUMENTS):
        raise FranceIGEDDAEError("capture document inventory changed")
    for year, row in zip(range(2009, 2027), annual, strict=True):
        item = _object(row, f"annual index {year}")
        if item.get("year") != year or item.get("url") != ANNUAL_INDEX_URLS[year]:
            raise FranceIGEDDAEError("annual-index order or URL changed")
        if year <= 2025:
            if item.get("http_status") != 200:
                raise FranceIGEDDAEError("closed archive page was not fetched")
            if item.get("matches") != (
                [EXPECTED_ARCHIVE_MATCHES[year]]
                if year in EXPECTED_ARCHIVE_MATCHES
                else []
            ):
                raise FranceIGEDDAEError("closed archive matches changed")
        else:
            if item.get("http_status") != 404 or item.get("matches") != []:
                raise FranceIGEDDAEError("2026 transport anomaly changed")
        if (
            not isinstance(item.get("bytes"), int)
            or item["bytes"] <= 0
            or not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
        ):
            raise FranceIGEDDAEError("annual-index response inventory changed")
    captured_documents = {row.get("document_id"): row for row in documents}
    if set(captured_documents) != set(DOCUMENTS):
        raise FranceIGEDDAEError("captured document set changed")
    for document_id, expected in DOCUMENTS.items():
        row = _object(captured_documents[document_id], document_id)
        for field in ("bytes", "sha256", "url"):
            if row.get(field) != expected[field]:
                raise FranceIGEDDAEError(f"captured document {document_id} changed")
    if capture.get("rights_checks") != {
        "free_distribution": True,
        "integrity_required": True,
        "open_absent_explicit_ip": True,
        "rights_reserved_and_strictly_limited_wording": True,
        "source_citation_required": True,
    }:
        raise FranceIGEDDAEError("capture rights checks changed")


def build_release_documents(capture: Mapping[str, Any]) -> dict[str, bytes]:
    _validate_capture(capture)
    captured_at = _timestamp(capture["captured_at"], "captured_at")
    annual_rows = [dict(_object(row, "annual row")) for row in capture["annual_indexes"]]
    observations = curated_observations()
    if sha256_bytes(jsonl(observations)) != EXPECTED_OBSERVATIONS_SHA256:
        raise FranceIGEDDAEError("curated observation set changed")
    raw_inventory = [
        {
            "bytes": row.get("bytes"),
            "request_id": row.get("request_id"),
            "sha256": row.get("sha256"),
        }
        for row in capture["retrievals"]
    ]
    annual_document = {
        "archive_closed_match_count": sum(len(row["matches"]) for row in annual_rows[:17]),
        "archive_closed_years": list(range(2009, 2026)),
        "archive_pages_fetched": 17,
        "current_2026_origin_capture_complete": False,
        "current_2026_http_status": 404,
        "format": ANNUAL_INVENTORY_FORMAT,
        "release_id": RELEASE_ID,
        "rows": annual_rows,
        "schema_version": SCHEMA_VERSION,
        "supplemental_2026_observation_count": 1,
    }
    retrieval_document = {
        "capture_state_sha256": capture["capture_state_sha256"],
        "captured_at": captured_at,
        "expected_first_attempt_requests": EXPECTED_NETWORK_REQUESTS,
        "format": RETRIEVAL_FORMAT,
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
        "network_attempt_count": capture["network_attempt_count"],
        "quarantined_raw_artifact_count": len(raw_inventory),
        "quarantined_raw_inventory_sha256": sha256_bytes(canonical_json(raw_inventory)),
        "raw_artifacts_released": 0,
        "release_id": RELEASE_ID,
        "retrievals": [
            {
                "bytes": row.get("bytes"),
                "content_type": row.get("content_type"),
                "endpoint_kind": row.get("endpoint_kind"),
                "http_status": row.get("http_status"),
                "method": row.get("method"),
                "raw_artifact_released": False,
                "raw_artifact_retained_in_operator_quarantine": True,
                "request_id": row.get("request_id"),
                "retrieved_at": row.get("retrieved_at"),
                "sha256": row.get("sha256"),
                "url": row.get("url"),
            }
            for row in capture["retrievals"]
        ],
        "schema_version": SCHEMA_VERSION,
        "successful_request_count": capture["successful_request_count"],
    }
    source_inventory = {
        "documents": [
            {
                "annual_index_year": expected["annual_index_year"],
                "bytes": expected["bytes"],
                "document_id": document_id,
                "docket_number_exact": expected["docket_number_exact"],
                "opinion_date": expected["opinion_date"],
                "pages": expected["pages"],
                "pdf_released": False,
                "sha256": expected["sha256"],
                "url": expected["url"],
            }
            for document_id, expected in DOCUMENTS.items()
        ],
        "format": SOURCE_INVENTORY_FORMAT,
        "raw_html_or_pdf_count_in_release": 0,
        "release_id": RELEASE_ID,
        "rights_url": RIGHTS_URL,
        "schema_version": SCHEMA_VERSION,
    }
    classification_counts = Counter(row["classification"] for row in observations)
    direct = [
        row for row in observations if row["classification"] == "direct_data_centre_project"
    ]
    assessment = {
        "assessed_at": captured_at,
        "assessment_id": RELEASE_ID,
        "atlas_decision": {
            "derived_rows_publication_eligible": True,
            "pdf_redistribution_permitted_by_this_release": False,
            "status": "open_derived_facts_pdf_redistribution_excluded",
        },
        "classification_counts": dict(sorted(classification_counts.items())),
        "coverage_assessment": {
            "archive_2009_2025_closed_scan_complete": True,
            "archive_title_matches": 3,
            "current_2026_origin_capture_complete": False,
            "france_complete": False,
            "planned_data_centre_units_in_direct_projects": sum(
                row["data_centre_unit_count"] for row in direct
            ),
            "regional_mrae_coverage_included": False,
            "supplemental_2026_follow_up_observations": 1,
            "unique_direct_project_count": len({row["project_group_id"] for row in direct}),
            "unique_project_site_count": len({row["site_group_id"] for row in direct}),
        },
        "format": ASSESSMENT_FORMAT,
        "inference_boundary": {
            "annual_energy_values_are_measured_actuals": False,
            "backup_or_battery_power_promoted_to_it_or_facility_load": False,
            "connection_power_promoted_to_it_or_facility_load": False,
            "environmental_opinion_promoted_to_physical_lifecycle": False,
            "unit_multiplicity_promoted_to_distinct_sites": False,
        },
        "observations_sha256": EXPECTED_OBSERVATIONS_SHA256,
        "release_id": RELEASE_ID,
        "rights_assessment": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "source_scope": {
            "annual_indexes_requested": 18,
            "annual_indexes_successfully_fetched": 17,
            "current_year_transport_anomaly": SUPPLEMENTAL_2026["discovery_note"],
        },
    }
    return {
        "ATTRIBUTION.txt": attribution_text().encode("utf-8"),
        "README.md": readme_text().encode("utf-8"),
        "annual-index-inventory.json": canonical_json(annual_document),
        "assessment.json": canonical_json(assessment),
        "definition.json": canonical_json(source_definition()),
        "observations.jsonl": jsonl(observations),
        "retrieval-inventory.json": canonical_json(retrieval_document),
        "schema.json": canonical_json(schema_document()),
        "source-inventory.json": canonical_json(source_inventory),
    }


def _manifest(documents: Mapping[str, bytes]) -> bytes:
    return canonical_json(
        {
            "files": [
                {
                    "bytes": len(documents[name]),
                    "filename": name,
                    "sha256": sha256_bytes(documents[name]),
                }
                for name in sorted(documents)
            ],
            "format": "datacenter-atlas-france-igedd-manifest-v1",
            "release_id": RELEASE_ID,
            "schema_version": SCHEMA_VERSION,
        }
    )


def write_release_bundle(destination: Path, documents: Mapping[str, bytes]) -> None:
    if set(documents) != DERIVED_FILENAMES:
        raise FranceIGEDDAEError("release document set changed")
    if destination.exists() or destination.is_symlink():
        raise FranceIGEDDAEError("release destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for name, body in documents.items():
            path = stage / name
            path.write_bytes(body)
            path.chmod(0o444)
        manifest = _manifest(documents)
        (stage / MANIFEST_FILENAME).write_bytes(manifest)
        (stage / MANIFEST_FILENAME).chmod(0o444)
        (stage / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest)}  {MANIFEST_FILENAME}\n", encoding="ascii"
        )
        (stage / MANIFEST_HASH_FILENAME).chmod(0o444)
        stage.chmod(0o555)
        os.replace(stage, destination)
    except Exception:
        if stage.exists():
            for path in stage.iterdir():
                path.chmod(0o600)
            stage.chmod(0o700)
            shutil.rmtree(stage)
        raise


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o644)


def is_frozen_release(root: Path) -> bool:
    if stat.S_IMODE(root.stat().st_mode) & 0o222:
        return False
    return all(
        not (stat.S_IMODE(path.stat().st_mode) & 0o222)
        for path in root.iterdir()
        if path.is_file()
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FranceIGEDDAEError(f"invalid JSON: {path.name}") from error
    return _object(value, path.name)


def validate_release_bundle(root: Path) -> dict[str, Any]:
    expected_files = DERIVED_FILENAMES | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    if not root.is_dir() or root.is_symlink():
        raise FranceIGEDDAEError("release root is not a directory")
    if {path.name for path in root.iterdir()} != expected_files:
        raise FranceIGEDDAEError("release file set changed")
    if not is_frozen_release(root):
        raise FranceIGEDDAEError("release is not frozen read-only")
    manifest = _load_json(root / MANIFEST_FILENAME)
    files = manifest.get("files")
    if (
        manifest.get("release_id") != RELEASE_ID
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("format") != "datacenter-atlas-france-igedd-manifest-v1"
        or not isinstance(files, list)
        or len(files) != len(DERIVED_FILENAMES)
    ):
        raise FranceIGEDDAEError("manifest identity changed")
    seen: set[str] = set()
    for raw in files:
        row = _object(raw, "manifest file")
        name = row.get("filename")
        if name not in DERIVED_FILENAMES or name in seen:
            raise FranceIGEDDAEError("manifest filename changed or duplicated")
        seen.add(str(name))
        path = root / str(name)
        if row.get("bytes") != path.stat().st_size or row.get("sha256") != sha256_file(path):
            raise FranceIGEDDAEError(f"manifest mismatch for {name}")
    expected_hash_line = (
        f"{sha256_file(root / MANIFEST_FILENAME)}  {MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="ascii") != expected_hash_line:
        raise FranceIGEDDAEError("manifest sidecar mismatch")
    if seen != DERIVED_FILENAMES:
        raise FranceIGEDDAEError("manifest file set changed")

    definition = _load_json(root / "definition.json")
    if definition != source_definition():
        raise FranceIGEDDAEError("source definition changed")
    assessment = _load_json(root / "assessment.json")
    if (
        assessment.get("format") != ASSESSMENT_FORMAT
        or assessment.get("assessment_id") != RELEASE_ID
        or assessment.get("rights_assessment") != RIGHTS_POLICY
    ):
        raise FranceIGEDDAEError("assessment identity or rights changed")
    coverage = _object(assessment.get("coverage_assessment"), "coverage")
    expected_coverage = {
        "archive_2009_2025_closed_scan_complete": True,
        "archive_title_matches": 3,
        "current_2026_origin_capture_complete": False,
        "france_complete": False,
        "planned_data_centre_units_in_direct_projects": 6,
        "regional_mrae_coverage_included": False,
        "supplemental_2026_follow_up_observations": 1,
        "unique_direct_project_count": 3,
        "unique_project_site_count": 3,
    }
    if coverage != expected_coverage:
        raise FranceIGEDDAEError("coverage arithmetic changed")
    boundary = _object(assessment.get("inference_boundary"), "inference boundary")
    if any(value is not False for value in boundary.values()):
        raise FranceIGEDDAEError("unsafe inference boundary changed")

    annual = _load_json(root / "annual-index-inventory.json")
    if (
        annual.get("format") != ANNUAL_INVENTORY_FORMAT
        or annual.get("archive_closed_match_count") != 3
        or annual.get("archive_pages_fetched") != 17
        or annual.get("current_2026_origin_capture_complete") is not False
        or annual.get("current_2026_http_status") != 404
    ):
        raise FranceIGEDDAEError("annual index assessment changed")
    annual_rows = annual.get("rows")
    if not isinstance(annual_rows, list) or len(annual_rows) != 18:
        raise FranceIGEDDAEError("annual index rows changed")
    for year, raw in zip(range(2009, 2027), annual_rows, strict=True):
        row = _object(raw, "annual index row")
        if row.get("year") != year or row.get("url") != ANNUAL_INDEX_URLS[year]:
            raise FranceIGEDDAEError("annual index row order changed")
        expected_matches = (
            [EXPECTED_ARCHIVE_MATCHES[year]] if year in EXPECTED_ARCHIVE_MATCHES else []
        )
        if row.get("matches") != expected_matches:
            raise FranceIGEDDAEError("annual index match set changed")

    observations = [
        json.loads(line)
        for line in (root / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if observations != curated_observations():
        raise FranceIGEDDAEError("observation rows changed")
    if sha256_bytes(jsonl(observations)) != EXPECTED_OBSERVATIONS_SHA256:
        raise FranceIGEDDAEError("observation hash changed")
    if Counter(row["classification"] for row in observations) != Counter(
        {"direct_data_centre_project": 3, "ancillary_grid_connection_follow_up": 1}
    ):
        raise FranceIGEDDAEError("observation classification arithmetic changed")
    if any(row["environmental_review"] != LIFECYCLE_BOUNDARY for row in observations):
        raise FranceIGEDDAEError("lifecycle boundary changed")
    for row in observations:
        for metric in row["metrics"]:
            metric_type = metric["metric_type"]
            if metric_type.startswith("backup_") and "never mapped" not in metric["qualifier"]:
                raise FranceIGEDDAEError("backup scope changed")
            if (
                metric_type == "requested_grid_connection_power"
                and "not IT" not in metric["qualifier"]
            ):
                raise FranceIGEDDAEError("connection scope changed")

    source_inventory = _load_json(root / "source-inventory.json")
    source_documents = source_inventory.get("documents")
    if (
        source_inventory.get("format") != SOURCE_INVENTORY_FORMAT
        or source_inventory.get("raw_html_or_pdf_count_in_release") != 0
        or not isinstance(source_documents, list)
        or len(source_documents) != 4
    ):
        raise FranceIGEDDAEError("source inventory changed")
    retrieval = _load_json(root / "retrieval-inventory.json")
    if (
        retrieval.get("format") != RETRIEVAL_FORMAT
        or retrieval.get("network_attempt_count") != EXPECTED_NETWORK_REQUESTS
        or retrieval.get("successful_request_count") != EXPECTED_SUCCESSFUL_REQUESTS
        or retrieval.get("quarantined_raw_artifact_count") != EXPECTED_RAW_ARTIFACTS
        or retrieval.get("raw_artifacts_released") != 0
    ):
        raise FranceIGEDDAEError("retrieval inventory changed")
    retrieval_rows = retrieval.get("retrievals")
    if not isinstance(retrieval_rows, list) or len(retrieval_rows) != EXPECTED_RAW_ARTIFACTS:
        raise FranceIGEDDAEError("retrieval rows changed")
    if any(row.get("raw_artifact_released") is not False for row in retrieval_rows):
        raise FranceIGEDDAEError("raw artifact release changed")
    for row in retrieval_rows:
        _official_url(row.get("url"), "retrieval URL")
    return {
        "annual_index": annual,
        "assessment": assessment,
        "definition": definition,
        "manifest": manifest,
        "observations": observations,
        "retrieval_inventory": retrieval,
        "source_inventory": source_inventory,
    }
