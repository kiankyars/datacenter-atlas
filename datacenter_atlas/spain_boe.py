"""Frozen BOE publication assessment for Spanish data-centre evidence.

This lane is deliberately publication-level.  A BOE tender, award, grant,
audit, law, or public-information notice is evidence of an official process;
it is not evidence that physical construction is current or complete.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import urlencode, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "spain-boe-data-centre-publications-2026-07-18-v1"
SOURCE_ID = "spain-boe-data-centre-publications"
RELEASE_FORMAT = "datacenter-atlas-spain-boe-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-spain-boe-definition-v1"
SNAPSHOT_FORMAT = "datacenter-atlas-spain-boe-sanitized-search-snapshot-v1"
INVENTORY_FORMAT = "datacenter-atlas-spain-boe-retrieval-inventory-v1"
OBSERVATION_FORMAT = "datacenter-atlas-spain-boe-publication-observation-v1"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

SEARCH_TERMS = (
    "centro de datos",
    "centros de datos",
    "centro de procesamiento de datos",
    "centro de proceso de datos",
    "data center",
    "datacenter",
)
DATE_FROM = "2016-01-01"
DATE_TO = "2026-07-18"
EXPECTED_QUERY_COUNTS = {
    "centro de datos": 66,
    "centros de datos": 163,
    "centro de procesamiento de datos": 58,
    "centro de proceso de datos": 323,
    "data center": 38,
    "datacenter": 29,
}
EXPECTED_CLOSED_SET_COUNT = 658
EXPECTED_CLOSED_ID_SHA256 = (
    "1b9fbf381775e72d71637ff905e895ba256228f40bc45095b0a73de3e80aef85"
)
EXPECTED_CLASS_COUNTS = {
    "direct_project_build_expansion_candidate": 19,
    "ancillary_or_administrative_context": 31,
    "excluded_non_build_or_non_datacentre": 608,
}
MAX_NETWORK_REQUESTS = 435
MIN_REQUEST_INTERVAL_SECONDS = 0.75

BOE_BASE_URL = "https://www.boe.es"
LEGAL_NOTICE_URL = f"{BOE_BASE_URL}/informacion/aviso_legal/"
SEARCH_HELP_URL = f"{BOE_BASE_URL}/buscar/ayudas/boe_ayuda.php"
OPEN_DATA_FAQ_URL = f"{BOE_BASE_URL}/datosabiertos/faq/boe.php"
SEARCH_FORM_URL = f"{BOE_BASE_URL}/buscar/boe.php"
ATTRIBUTION = "Basado en datos de la Agencia Estatal Boletín Oficial del Estado"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BOE_ID_RE = re.compile(r"^BOE-[AB]-20\d{2}-\d+$")
_PUBLICATION_RE = re.compile(
    r"^BOE (?P<number>\d+) de (?P<day>\d{2})/(?P<month>\d{2})/"
    r"(?P<year>\d{4}) - (?P<section>[IVX]+)\. (?P<section_name>.+)$"
)


class SpainBOEError(ValueError):
    """Raised when a Spain BOE artifact violates the frozen contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def official_document_urls(boe_id: str) -> dict[str, str]:
    if not _BOE_ID_RE.fullmatch(boe_id):
        raise SpainBOEError("invalid BOE identifier")
    return {
        "html": f"{BOE_BASE_URL}/buscar/doc.php?id={boe_id}",
        "text": f"{BOE_BASE_URL}/diario_boe/txt.php?id={boe_id}",
        "xml": f"{BOE_BASE_URL}/diario_boe/xml.php?id={boe_id}",
    }


def search_url(term: str) -> str:
    if term not in SEARCH_TERMS:
        raise SpainBOEError("term is outside the closed query plan")
    fields: list[tuple[str, str]] = [
        ("campo[0]", "ORIS"),
        ("dato[0][1]", "1"),
        ("dato[0][3]", "3"),
        ("dato[0][5]", "5"),
        ("operador[0]", "and"),
        ("campo[1]", "TITULOS"),
        ("dato[1]", ""),
        ("operador[1]", "and"),
        ("campo[2]", "DEM"),
        ("dato[2]", ""),
        ("operador[2]", "and"),
        ("campo[3]", "DOC"),
        ("dato[3]", f'"{term}"'),
        ("operador[3]", "and"),
        ("campo[4]", "NBOS"),
        ("dato[4]", ""),
        ("operador[4]", "and"),
        ("campo[5]", "NOF"),
        ("dato[5]", ""),
        ("operador[5]", "and"),
        ("operador[6]", "and"),
        ("campo[6]", "FPU"),
        ("dato[6][0]", DATE_FROM),
        ("dato[6][1]", DATE_TO),
        ("page_hits", "2000"),
        ("sort_field[0]", "FPU"),
        ("sort_order[0]", "asc"),
        ("sort_field[1]", "ORI"),
        ("sort_order[1]", "asc"),
        ("sort_field[2]", "REF"),
        ("sort_order[2]", "asc"),
        ("accion", "Buscar"),
    ]
    return f"{SEARCH_FORM_URL}?{urlencode(fields)}"


def source_definition() -> dict[str, Any]:
    return {
        "coverage": {
            "complete_for_spain": False,
            "date_from": DATE_FROM,
            "date_to_inclusive": DATE_TO,
            "official_sections_included": ["I", "III", "V"],
            "official_sections_excluded": ["II", "IV", "TC"],
            "publication_rows": EXPECTED_CLOSED_SET_COUNT,
            "scope": "exact full-text phrase search in selected BOE sections",
            "unique_physical_site_count": None,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_mwh": None,
            "automatic_promotion_permitted": False,
            "boe_process_status_is_physical_lifecycle": False,
            "identity_merge_performed": False,
            "it_power_mw": None,
            "physical_lifecycle_status": None,
            "pue": None,
            "publication_unit_preserved": True,
            "review_only": True,
            "unique_physical_site_count": None,
        },
        "network_policy": {
            "maximum_network_requests_per_capture": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "single_page_expected_per_phrase": True,
        },
        "publisher": "Agencia Estatal Boletín Oficial del Estado",
        "query": {
            "date_field": "FPU",
            "endpoint": SEARCH_FORM_URL,
            "exact_terms": list(SEARCH_TERMS),
            "full_text_field": "DOC",
            "page_hits": 2000,
            "sort": ["FPU asc", "ORI asc", "REF asc"],
        },
        "release_id": RELEASE_ID,
        "retention": {
            "excluded_titles_retained": False,
            "personal_or_contact_fields_retained": False,
            "raw_detail_xml_retained": False,
            "raw_pdf_retained": False,
            "raw_search_result_html_retained": False,
            "sanitized_publication_metadata_retained": True,
            "supporting_policy_pages_retained": True,
        },
        "rights": {
            "attribution": ATTRIBUTION,
            "commercial_reuse_permitted": True,
            "derivative_modifications_identified": True,
            "legal_notice_url": LEGAL_NOTICE_URL,
            "license_reviewed_local_date": "2026-07-18",
            "meaning_and_update_metadata_must_be_preserved": True,
            "no_implied_sponsorship": True,
            "personal_data_law_applies": True,
            "reuse_permitted": True,
            "source_link_required": True,
        },
        "schema_version": SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_urls": {
            "legal_notice": LEGAL_NOTICE_URL,
            "open_data_faq": OPEN_DATA_FAQ_URL,
            "search_form": SEARCH_FORM_URL,
            "search_help": SEARCH_HELP_URL,
        },
        "title": "Spain BOE exact-phrase data-centre publication assessment",
    }


def _unit(
    unit_id: str,
    name: str,
    work_scope: str,
    location: str | None = None,
) -> dict[str, Any]:
    return {
        "location_as_stated": location,
        "name": name,
        "unit_id": unit_id,
        "work_scope_as_stated": work_scope,
    }


DIRECT: dict[str, dict[str, Any]] = {
    "BOE-A-2016-6294": {
        "evidence_summary": "A published agreement modification covers construction of a mathematics and computing research centre whose building program includes a computing/data-processing centre.",
        "process_status": "agreement_modification_published",
        "project_units": [_unit("rioja-research-computing-centre", "Centre for Research in Mathematics and Computing and Computing Centre", "construction", "La Rioja")],
    },
    "BOE-A-2020-17333": {
        "evidence_summary": "A funding agreement expressly includes construction and fit-out of a data-processing centre and linked installations for BSC-CNS.",
        "process_status": "funding_agreement_published",
        "project_units": [_unit("bsc-site-cpd", "BSC-CNS SITE data-processing centre", "construction and fit-out", "Catalonia")],
        "financial_facts": [{"amount_eur": 7000000.0, "amount_type": "extraordinary_ministry_contribution", "scope": "published funding agreement"}],
    },
    "BOE-A-2022-1248": {
        "evidence_summary": "A Tribunal de Cuentas audit describes the procurement of a new CNMC data-processing centre and reports contract and completion milestones from 2017-2018.",
        "process_status": "retrospective_audit_resolution_published",
        "project_units": [_unit("cnmc-alcala-47-cpd", "CNMC data-processing centre", "new centre under audited contract", "Calle Alcalá 47, Madrid")],
        "financial_facts": [{"amount_eur": 429843.76, "amount_type": "contract_amount", "scope": "audited procurement"}],
    },
    "BOE-A-2022-18446": {
        "evidence_summary": "A transport funding distribution lists design or update work for communications systems associated with Metro de Madrid's new data-processing centre.",
        "process_status": "funding_distribution_resolution_published",
        "project_units": [_unit("metro-madrid-new-cpd", "Metro de Madrid new data-processing centre", "project design/update and linked communications", "Madrid")],
        "financial_facts": [{"amount_eur": 2925445.61, "amount_type": "listed_programme_amount", "scope": "funding plan line item"}],
    },
    "BOE-A-2022-8298": {
        "evidence_summary": "A local-government digital-modernisation grant resolution lists two explicit construction/new-centre projects.",
        "process_status": "grant_award_resolution_published",
        "project_units": [
            _unit("gijon-sustainable-cpd", "Sustainable data-processing centre", "construction", "Gijón/Xixón"),
            _unit("la-linea-new-cpd", "New sustainable data-processing centre", "new centre and server infrastructure", "La Línea de la Concepción"),
        ],
        "financial_facts": [
            {"amount_eur": 809580.77, "amount_type": "grant_award", "scope": "Gijón/Xixón project"},
            {"amount_eur": 187100.22, "amount_type": "grant_award", "scope": "La Línea de la Concepción project"},
        ],
    },
    "BOE-A-2023-13746": {
        "evidence_summary": "A local-government grant resolution lists multiple explicit new or implementation data-processing-centre projects; each named project remains a separate project unit.",
        "process_status": "grant_award_resolution_published",
        "project_units": [
            _unit("calp-new-cpd", "New municipal data-processing centre", "new centre with virtual-desktop and remote-access capabilities", "Calp"),
            _unit("novelda-new-cpd", "New secured municipal data-processing centre", "new secured centre", "Novelda"),
            _unit("onda-sustainable-cpd", "Sustainable municipal data-processing centre", "implementation", "Onda"),
            _unit("lebrija-cpd", "Municipal data-processing centre", "creation with anti-ransomware backup", "Lebrija"),
        ],
    },
    "BOE-A-2025-16301": {
        "evidence_summary": "A regional-incentive decision lists an NXN DATA CENTER investment project in Valencia, with investment, subsidy, and employment figures.",
        "process_status": "regional_incentive_award_published",
        "project_units": [_unit("nxn-valencia-investment", "NXN DATA CENTER investment project", "investment project", "Valencia")],
        "financial_facts": [
            {"amount_eur": 24970439.0, "amount_type": "eligible_investment", "scope": "regional incentive table"},
            {"amount_eur": 5493496.58, "amount_type": "subsidy", "scope": "regional incentive table"},
            {"count": 26, "metric": "employment", "scope": "regional incentive table"},
        ],
    },
    "BOE-A-2026-5368": {
        "evidence_summary": "A retrospective audit revisits local-government grants that included explicit construction and new-centre projects; audit findings are not treated as physical lifecycle observations.",
        "process_status": "retrospective_audit_resolution_published",
        "project_units": [
            _unit("gijon-sustainable-cpd-audit", "Sustainable data-processing centre", "construction project under audit", "Gijón/Xixón"),
            _unit("la-linea-new-cpd-audit", "New sustainable data-processing centre", "new-centre project under audit", "La Línea de la Concepción"),
        ],
        "financial_facts": [
            {"amount_eur": 809580.77, "amount_type": "grant_amount_reviewed", "scope": "Gijón/Xixón project"},
            {"amount_eur": 187100.22, "amount_type": "grant_amount_reviewed", "scope": "La Línea de la Concepción project"},
        ],
    },
    "BOE-B-2016-49407": {
        "evidence_summary": "A works tender covers reform and adaptation of premises as a data-processing centre at Joaquín Costa 22 in Madrid.",
        "process_status": "works_tender_published",
        "project_units": [_unit("csic-joaquin-costa-cpd-tender", "CSIC Joaquín Costa data-processing centre", "reform and fit-out works", "Madrid")],
        "financial_facts": [{"amount_eur": 3209555.27, "amount_type": "tender_value_excluding_tax", "scope": "works tender"}, {"amount_eur": 3883561.88, "amount_type": "tender_value_including_tax", "scope": "works tender"}],
    },
    "BOE-B-2017-12133": {
        "evidence_summary": "A contract-formalisation notice covers reform and adaptation of premises as a data-processing centre at Joaquín Costa 22 in Madrid.",
        "process_status": "works_contract_formalisation_published",
        "project_units": [_unit("csic-joaquin-costa-cpd-award", "CSIC Joaquín Costa data-processing centre", "reform and fit-out works", "Madrid")],
        "financial_facts": [{"amount_eur": 2091346.21, "amount_type": "award_value_excluding_tax", "scope": "formalised works contract"}, {"amount_eur": 2530528.91, "amount_type": "award_value_including_tax", "scope": "formalised works contract"}],
    },
    "BOE-B-2016-59830": {
        "evidence_summary": "A services tender covers detailed design, works supervision, and commissioning support for Metro de Madrid's global data-processing centre.",
        "process_status": "design_services_tender_published",
        "project_units": [_unit("metro-global-cpd-design", "Metro de Madrid global data-processing centre", "detailed design and works/commissioning support", "Madrid")],
    },
    "BOE-B-2018-5330": {
        "evidence_summary": "A mixed supply-and-service tender covers fit-out for a new BSC data-processing centre and relocation of HPC and Big Data racks.",
        "process_status": "fitout_tender_published",
        "project_units": [_unit("bsc-new-cpd-fitout", "BSC new data-processing centre", "facility adaptation, equipment, and rack relocation", "Barcelona")],
        "financial_facts": [{"amount_eur": 1554000.0, "amount_type": "tender_value_excluding_tax", "scope": "mixed contract"}, {"amount_eur": 1880340.0, "amount_type": "tender_value_including_tax", "scope": "mixed contract"}],
    },
    "BOE-B-2019-13503": {
        "evidence_summary": "A works notice concerns construction of Metro de Madrid's global data-processing centre.",
        "process_status": "works_tender_published",
        "project_units": [_unit("metro-global-cpd-works", "Metro de Madrid global data-processing centre", "construction", "Madrid")],
    },
    "BOE-B-2020-8465": {
        "evidence_summary": "A works tender covers physical expansion and modernisation of the Ministry of Defence central data-processing centre.",
        "process_status": "works_tender_published",
        "project_units": [_unit("defence-central-cpd-tender", "Ministry of Defence central data-processing centre", "physical expansion and modernisation", "Spain")],
        "financial_facts": [{"amount_eur": 5760831.76, "amount_type": "estimated_contract_value", "scope": "works tender"}],
    },
    "BOE-B-2020-32779": {
        "evidence_summary": "A contract-formalisation notice covers physical expansion and modernisation of the Ministry of Defence central data-processing centre.",
        "process_status": "works_contract_formalisation_published",
        "project_units": [_unit("defence-central-cpd-award", "Ministry of Defence central data-processing centre", "physical expansion and modernisation", "Spain")],
        "financial_facts": [{"amount_eur": 3772768.72, "amount_type": "award_value", "scope": "formalised works contract"}],
    },
    "BOE-B-2020-38276": {
        "evidence_summary": "A contract-formalisation notice concerns works to create a new data-processing centre for the Port Authority of Huelva.",
        "process_status": "works_contract_formalisation_published",
        "project_units": [_unit("huelva-port-new-cpd", "Port Authority of Huelva data-processing centre", "creation of a new centre", "Huelva")],
        "financial_facts": [{"amount_eur": 378000.0, "amount_type": "award_value", "scope": "formalised works contract"}],
    },
    "BOE-B-2021-33832": {
        "evidence_summary": "A services tender covers design, full works supervision, commissioning, and safety coordination for construction of a new GISS data-processing-centre headquarters.",
        "process_status": "design_and_commissioning_tender_published",
        "project_units": [_unit("giss-new-cpd-hq-tender", "GISS new data-processing-centre headquarters", "design and construction-phase professional services", "Spain")],
    },
    "BOE-B-2022-2938": {
        "evidence_summary": "A contract-formalisation notice covers design, supervision, commissioning, and safety services for construction of a new GISS data-processing-centre headquarters.",
        "process_status": "design_and_commissioning_contract_formalisation_published",
        "project_units": [_unit("giss-new-cpd-hq-award", "GISS new data-processing-centre headquarters", "design and construction-phase professional services", "Spain")],
    },
    "BOE-B-2024-30949": {
        "evidence_summary": "A contract-formalisation notice covers phase-zero remodelling and capacity expansion of SGAD's data-processing centre in El Escorial.",
        "process_status": "works_contract_formalisation_published",
        "project_units": [_unit("sgad-el-escorial-phase-0", "SGAD El Escorial data-processing centre", "phase-zero remodelling and capacity expansion", "El Escorial")],
        "financial_facts": [{"amount_eur": 5074059.52, "amount_type": "award_value", "scope": "formalised works contract"}],
    },
}


CONTEXT_IDS = {
    "BOE-A-2018-13701", "BOE-A-2021-20690", "BOE-A-2022-15443",
    "BOE-A-2022-23737", "BOE-A-2023-7736", "BOE-A-2024-2774",
    "BOE-A-2024-4783", "BOE-A-2024-27289", "BOE-A-2025-6456",
    "BOE-A-2025-14863", "BOE-A-2025-26705", "BOE-A-2026-3218",
    "BOE-A-2026-6544", "BOE-B-2017-7113", "BOE-B-2017-31270",
    "BOE-B-2017-38908", "BOE-B-2018-6425", "BOE-B-2018-15589",
    "BOE-B-2019-24377", "BOE-B-2019-38699", "BOE-B-2022-27998",
    "BOE-B-2022-34372", "BOE-B-2022-38222", "BOE-B-2023-2757",
    "BOE-B-2023-5999", "BOE-B-2023-6146", "BOE-B-2023-22941",
    "BOE-B-2023-33562", "BOE-B-2025-22920", "BOE-B-2025-46258",
    "BOE-B-2026-3291",
}


CONTEXT_OVERRIDES: dict[str, dict[str, Any]] = {
    "BOE-B-2025-22920": {
        "evidence_summary": "A water-availability competition notice records an Amazon Data Services application whose stated destination is a data centre; it is water-process context, not build status.",
        "process_status": "water_use_competition_notice_published",
        "facility_metrics": [
            {"metric": "water_flow", "unit": "litres_per_second", "value": 26.30, "scope": "maximum requested flow as stated"},
            {"metric": "water_volume", "unit": "cubic_metres_per_year", "value": 204697.0, "scope": "maximum requested annual volume as stated"},
        ],
    },
    "BOE-B-2026-3291": {
        "evidence_summary": "A public-information notice covers a 220/20 kV substation and line for IGNIS DATA BETA II and states a 181.62 MW data-centre power figure; this is grid authorisation context, not IT power, energy use, or construction status.",
        "process_status": "prior_and_construction_authorisation_application_under_public_information",
        "facility_metrics": [
            {"metric": "facility_power_as_stated", "unit": "megawatt", "value": 181.62, "scope": "data-centre facility power stated in grid application; not IT power or measured consumption"},
            {"metric": "transformer_count", "unit": "count", "value": 4, "scope": "100 MVA transformers in linked substation project"},
            {"metric": "transformer_rating", "unit": "megavolt_ampere_each", "value": 100.0, "scope": "four linked substation transformers"},
            {"metric": "underground_line_length", "unit": "metre", "value": 986.18, "scope": "linked 220 kV line"},
        ],
    },
}


def _context_record(boe_id: str) -> dict[str, Any]:
    if boe_id in CONTEXT_OVERRIDES:
        return CONTEXT_OVERRIDES[boe_id]
    if boe_id.startswith("BOE-A-"):
        return {
            "evidence_summary": "The publication supplies policy, budget, funding, audit, or regulatory context involving data-processing centres, without a retained direct build/expansion project unit.",
            "process_status": "administrative_or_policy_publication",
        }
    return {
        "evidence_summary": "The notice concerns equipment, utilities, communications, migration, or other ancillary work around a data-processing centre, not retained as a direct facility build/expansion publication.",
        "process_status": "ancillary_procurement_or_public_notice",
    }


def _excluded_category(title: str) -> str:
    value = title.casefold()
    if any(token in value for token in ("windows server", "datacenter edition", "jira data center", "data center edition")):
        return "software_or_product_name"
    if any(token in value for token in ("mantenimiento", "monitorización", "soporte", "servicio de alojamiento", "servicios gestionados")):
        return "routine_operations_or_maintenance"
    if any(token in value for token in ("servidores", "almacenamiento", "equipamiento", "hardware", "licencias", "red de datos")):
        return "hardware_or_network_only"
    if any(token in value for token in ("curso", "investigación", "universidad", "formación", "beca")):
        return "existing_facility_use_or_research"
    if any(token in value for token in ("norma", "ley", "real decreto", "reglamento", "convenio colectivo")):
        return "standards_or_generic_policy_boilerplate"
    if any(token in value for token in ("personal", "impuesto", "auditoría", "cuentas anuales")):
        return "personnel_tax_audit_or_unrelated_administration"
    return "no_direct_build_expansion_or_ancillary_project_evidence_after_official_review"


def _parse_publication(value: str) -> dict[str, Any]:
    match = _PUBLICATION_RE.fullmatch(value)
    if match is None:
        raise SpainBOEError(f"unrecognised BOE publication label: {value}")
    data = match.groupdict()
    return {
        "date": f"{data['year']}-{data['month']}-{data['day']}",
        "number": int(data["number"]),
        "section": data["section"],
        "section_name": data["section_name"],
    }


def build_sanitized_snapshot(union: Mapping[str, Any]) -> dict[str, Any]:
    records = union.get("records")
    if not isinstance(records, list):
        raise SpainBOEError("union records must be a list")
    rows: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, Mapping):
            raise SpainBOEError("union row must be an object")
        boe_id = raw.get("boe_id")
        title = raw.get("title")
        department = raw.get("department")
        memberships = raw.get("query_memberships")
        if (
            not isinstance(boe_id, str)
            or not _BOE_ID_RE.fullmatch(boe_id)
            or not isinstance(title, str)
            or not isinstance(department, str)
            or not isinstance(memberships, list)
        ):
            raise SpainBOEError("invalid union row")
        if boe_id in DIRECT:
            classification = "direct_project_build_expansion_candidate"
            review_category = "direct_official_project_or_procurement_evidence"
        elif boe_id in CONTEXT_IDS:
            classification = "ancillary_or_administrative_context"
            review_category = "ancillary_or_administrative_context"
        else:
            classification = "excluded_non_build_or_non_datacentre"
            review_category = _excluded_category(title)
        parsed_memberships = sorted(
            [
                {"position": int(item["position"]), "term": str(item["term"])}
                for item in memberships
            ],
            key=lambda item: SEARCH_TERMS.index(item["term"]),
        )
        rows.append(
            {
                "boe_id": boe_id,
                "classification": classification,
                "department": department,
                "official_urls": official_document_urls(boe_id),
                "publication": _parse_publication(str(raw.get("publication"))),
                "query_memberships": parsed_memberships,
                "review_category": review_category,
            }
        )
    rows.sort(key=lambda row: row["boe_id"])
    snapshot = {
        "date_from": DATE_FROM,
        "date_to_inclusive": DATE_TO,
        "format": SNAPSHOT_FORMAT,
        "modifications": [
            "titles removed after classification",
            "raw result HTML and detail bodies omitted",
            "records deduplicated only by exact BOE identifier",
        ],
        "query_counts": {term: int(union.get("counts", {}).get(term, -1)) for term in SEARCH_TERMS},
        "release_id": RELEASE_ID,
        "rows": rows,
        "schema_version": SCHEMA_VERSION,
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("format") != SNAPSHOT_FORMAT:
        raise SpainBOEError("snapshot format differs")
    if snapshot.get("query_counts") != EXPECTED_QUERY_COUNTS:
        raise SpainBOEError("query counts differ")
    rows = snapshot.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CLOSED_SET_COUNT:
        raise SpainBOEError("closed set must contain 658 rows")
    ids = [row.get("boe_id") for row in rows if isinstance(row, Mapping)]
    if len(ids) != len(set(ids)) or ids != sorted(ids):
        raise SpainBOEError("BOE IDs must be unique and sorted")
    closed_hash = sha256_bytes(("\n".join(ids) + "\n").encode("utf-8"))
    if closed_hash != EXPECTED_CLOSED_ID_SHA256:
        raise SpainBOEError("closed BOE-ID set differs")
    counts = Counter(row.get("classification") for row in rows)
    if dict(counts) != EXPECTED_CLASS_COUNTS:
        raise SpainBOEError("classification arithmetic differs")
    if set(DIRECT) & CONTEXT_IDS or set(DIRECT) | CONTEXT_IDS != {
        row["boe_id"] for row in rows if row["classification"] != "excluded_non_build_or_non_datacentre"
    }:
        raise SpainBOEError("manual decision sets differ from snapshot")
    for row in rows:
        if set(row) != {"boe_id", "classification", "department", "official_urls", "publication", "query_memberships", "review_category"}:
            raise SpainBOEError("snapshot row fields differ")
        if row["publication"]["section"] not in {"I", "III", "V"}:
            raise SpainBOEError("snapshot contains an excluded BOE section")
        for membership in row["query_memberships"]:
            if membership["term"] not in SEARCH_TERMS or membership["position"] < 1:
                raise SpainBOEError("invalid query membership")


def observations(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_snapshot(snapshot)
    result: list[dict[str, Any]] = []
    for row in snapshot["rows"]:
        boe_id = row["boe_id"]
        classification = row["classification"]
        if classification == "direct_project_build_expansion_candidate":
            decision = DIRECT[boe_id]
        elif classification == "ancillary_or_administrative_context":
            decision = _context_record(boe_id)
        else:
            decision = {}
        result.append(
            {
                "annual_energy_mwh": None,
                "auto_merge": False,
                "boe_id": boe_id,
                "classification": classification,
                "classification_reason": row["review_category"],
                "data_centre_type_as_stated": None,
                "department": row["department"],
                "evidence_summary": decision.get("evidence_summary"),
                "facility_metrics": decision.get("facility_metrics", []),
                "financial_facts": decision.get("financial_facts", []),
                "format": OBSERVATION_FORMAT,
                "it_power_mw": None,
                "official_urls": row["official_urls"],
                "physical_lifecycle_status": None,
                "process_status": decision.get("process_status"),
                "process_status_scope": "official_publication_or_procurement_process_only",
                "project_units": decision.get("project_units", []),
                "publication": row["publication"],
                "publication_unit_preserved": True,
                "pue": None,
                "query_memberships": row["query_memberships"],
                "review_only": True,
                "source_id": SOURCE_ID,
                "unique_site_counted": False,
            }
        )
    validate_observations(result)
    return result


def validate_observations(rows: Sequence[Mapping[str, Any]]) -> None:
    if len(rows) != EXPECTED_CLOSED_SET_COUNT:
        raise SpainBOEError("observation count differs")
    for row in rows:
        if (
            row.get("physical_lifecycle_status") is not None
            or row.get("it_power_mw") is not None
            or row.get("annual_energy_mwh") is not None
            or row.get("pue") is not None
            or row.get("review_only") is not True
            or row.get("auto_merge") is not False
            or row.get("unique_site_counted") is not False
            or row.get("publication_unit_preserved") is not True
        ):
            raise SpainBOEError("an observation violates the inference contract")
        if row["classification"] == "excluded_non_build_or_non_datacentre":
            if row.get("evidence_summary") is not None or row.get("process_status") is not None or row.get("project_units"):
                raise SpainBOEError("excluded rows must remain metadata-minimal")
        if row["classification"] == "direct_project_build_expansion_candidate" and not row.get("project_units"):
            raise SpainBOEError("direct publication must retain a project unit")
        for metric in row.get("facility_metrics", []):
            if set(metric) != {"metric", "unit", "value", "scope"} or not metric["scope"]:
                raise SpainBOEError("numeric facility fact lacks a typed scope")
            if metric["metric"] == "facility_power_as_stated" and row["boe_id"] != "BOE-B-2026-3291":
                raise SpainBOEError("facility power is attached to the wrong publication")
    serialized = canonical_json(list(rows)).decode("utf-8").casefold()
    forbidden = ("nif", "correo electrónico", "e-mail", "teléfono", "firma:", "domicilio particular")
    if any(token in serialized for token in forbidden):
        raise SpainBOEError("personal/contact-data token retained")


def query_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_snapshot(snapshot)
    rows = snapshot["rows"]
    return {
        "classification_counts": dict(Counter(row["classification"] for row in rows)),
        "closed_id_sha256": EXPECTED_CLOSED_ID_SHA256,
        "closed_set_count": len(rows),
        "date_from": DATE_FROM,
        "date_to_inclusive": DATE_TO,
        "deduplication": "exact BOE identifier only",
        "query_counts_before_union": EXPECTED_QUERY_COUNTS,
        "query_membership_multiplicity": dict(sorted(Counter(len(row["query_memberships"]) for row in rows).items())),
        "sections": dict(sorted(Counter(row["publication"]["section"] for row in rows).items())),
        "years": dict(sorted(Counter(row["publication"]["date"][:4] for row in rows).items())),
    }


def assessment_document(snapshot: Mapping[str, Any], inventory: Mapping[str, Any]) -> dict[str, Any]:
    validate_snapshot(snapshot)
    validate_inventory(inventory)
    summary = query_summary(snapshot)
    return {
        "assessment_id": RELEASE_ID,
        "atlas_decision": {
            "automatic_promotion_permitted": False,
            "construction_master_import_permitted": False,
            "current_coverage_ledger_import_permitted": False,
            "map_import_permitted": False,
            "status": "publication_level_review_only",
        },
        "coverage_assessment": {
            "all_spain_data_centres_claim_supported": False,
            "classification_counts": summary["classification_counts"],
            "closed_query_completed": True,
            "closed_set_count": EXPECTED_CLOSED_SET_COUNT,
            "complete_for_spain": False,
            "publication_unit_preserved": True,
            "unique_physical_site_count": None,
        },
        "format": RELEASE_FORMAT,
        "inference_policy": source_definition()["inference_policy"],
        "release_id": RELEASE_ID,
        "retention_assessment": source_definition()["retention"],
        "retrieval_batch": {
            "controlled_network_requests": inventory["network_requests"],
            "maximum_network_requests": inventory["maximum_network_requests"],
            "raw_detail_and_search_bodies_retained": False,
        },
        "rights_assessment": source_definition()["rights"],
        "schema_version": SCHEMA_VERSION,
    }


def schema_document() -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-spain-boe-schema-v1",
        "lifecycle_contract": {
            "physical_lifecycle_status": None,
            "process_status_is_physical_lifecycle": False,
        },
        "metric_contract": {
            "annual_energy_mwh": None,
            "it_power_mw": None,
            "pue": None,
            "retained_numeric_facts_require_metric_unit_value_scope": True,
        },
        "publication_contract": {
            "duplicate_project_publications_may_exist": True,
            "identity_merge_performed": False,
            "publication_is_primary_unit": True,
            "unique_physical_site_count": None,
        },
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    fields = ["boe_id", "publication_date", "section", "classification", "classification_reason", "process_status", "physical_lifecycle_status", "project_unit_count", "review_only", "auto_merge"]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "boe_id": row["boe_id"], "publication_date": row["publication"]["date"],
            "section": row["publication"]["section"], "classification": row["classification"],
            "classification_reason": row["classification_reason"], "process_status": row["process_status"] or "",
            "physical_lifecycle_status": "", "project_unit_count": len(row["project_units"]),
            "review_only": "true", "auto_merge": "false",
        })
    return stream.getvalue().encode("utf-8")


def readme_bytes() -> bytes:
    return f"""# Spain BOE data-centre publication assessment

This frozen lane contains every BOE-ID returned by six exact full-text phrase searches across sections I, III, and V from {DATE_FROM} through {DATE_TO}. It is complete only for that bounded query contract, not for Spain or for all data-centre terminology.

The 658 publications are classified as 19 direct project/build/expansion candidates, 31 ancillary or administrative-context records, and 608 exclusions. The unit is the BOE publication. Tenders, formalised contracts, grants, audits, and repeated notices have not been merged into facilities. `unique_physical_site_count` and every `physical_lifecycle_status` remain null.

BOE process labels describe publication, procurement, grant, audit, water, grid, or policy state. They do not establish physical construction or operation. The 181.62 MW figure in BOE-B-2026-3291 is retained only as facility power stated in a grid application; it is not IT power or measured energy consumption. PUE, IT power, and annual energy remain null throughout.

Raw search HTML, detail XML, PDFs, titles of excluded records, names, signatures, addresses, tax identifiers, phone numbers, and email addresses are not retained. Search metadata was sanitized and all modifications are identified in the snapshot.

{ATTRIBUTION}. Source: {LEGAL_NOTICE_URL}

Validate offline:

```bash
python3 scripts/validate_spain_boe.py
```
""".encode("utf-8")


def attribution_bytes() -> bytes:
    return f"""{ATTRIBUTION}
Source: {BOE_BASE_URL}/
Reuse terms: {LEGAL_NOTICE_URL}

This derivative removes raw result/detail bodies and personal/contact fields, omits excluded titles, paraphrases retained evidence, and adds review classifications. It does not imply BOE sponsorship.
""".encode("utf-8")


def validate_inventory(inventory: Mapping[str, Any]) -> None:
    if inventory.get("format") != INVENTORY_FORMAT or inventory.get("release_id") != RELEASE_ID:
        raise SpainBOEError("retrieval inventory identity differs")
    records = inventory.get("responses")
    if not isinstance(records, list) or len(records) != 429:
        raise SpainBOEError("retrieval inventory must contain 429 responses")
    if inventory.get("network_requests") != 429 or inventory.get("maximum_network_requests") != MAX_NETWORK_REQUESTS:
        raise SpainBOEError("retrieval request arithmetic differs")
    if inventory.get("minimum_request_interval_seconds") != MIN_REQUEST_INTERVAL_SECONDS:
        raise SpainBOEError("retrieval pacing differs")
    if Counter(row.get("kind") for row in records) != Counter({"detail_xml": 376, "detail_pdf": 43, "search_result": 6, "support_policy": 4}):
        raise SpainBOEError("retrieval response-kind arithmetic differs")
    for row in records:
        if row.get("http_status") != 200 or not isinstance(row.get("bytes"), int) or row["bytes"] <= 0 or not _SHA256_RE.fullmatch(str(row.get("sha256", ""))):
            raise SpainBOEError("retrieval response metadata is invalid")
        parsed = urlsplit(str(row.get("url", "")))
        if parsed.scheme != "https" or parsed.hostname != "www.boe.es":
            raise SpainBOEError("retrieval URL is not official BOE HTTPS")
        if row["kind"] in {"search_result", "detail_xml", "detail_pdf"} and row.get("body_retained") is not False:
            raise SpainBOEError("raw search/detail bodies must not be retained")
        if row["kind"] == "support_policy" and row.get("body_retained") is not True:
            raise SpainBOEError("support-policy retention differs")


def derive_release_files(snapshot: Mapping[str, Any], inventory: Mapping[str, Any], support: Mapping[str, bytes]) -> dict[str, bytes]:
    validate_snapshot(snapshot)
    validate_inventory(inventory)
    rows = observations(snapshot)
    expected_support = {"legal-notice.html", "open-data-faq.html", "search-form.html", "search-help.html"}
    if set(support) != expected_support:
        raise SpainBOEError("support file set differs")
    support_inventory = {Path(row["release_path"]).name: row for row in inventory["responses"] if row["kind"] == "support_policy"}
    for name, body in support.items():
        record = support_inventory.get(name)
        if record is None or record["bytes"] != len(body) or record["sha256"] != sha256_bytes(body):
            raise SpainBOEError(f"support file differs: {name}")
    return {
        "ATTRIBUTION.txt": attribution_bytes(),
        "README.md": readme_bytes(),
        "assessment.json": canonical_json(assessment_document(snapshot, inventory)),
        "definition.json": canonical_json(source_definition()),
        "observations.csv": _csv_bytes(rows),
        "observations.jsonl": _jsonl(rows),
        "query-summary.json": canonical_json(query_summary(snapshot)),
        "retrieval-inventory.json": canonical_json(inventory),
        "sanitized-search-snapshot.json": canonical_json(snapshot),
        "schema.json": canonical_json(schema_document()),
        **{f"support/{name}": body for name, body in support.items()},
    }


def _manifest(files: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "files": {name: {"bytes": len(body), "sha256": sha256_bytes(body)} for name, body in sorted(files.items())},
        "format": "datacenter-atlas-manifest-v1",
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _freeze_tree(root: Path) -> None:
    for entry in sorted(root.rglob("*"), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def is_frozen_release(root: Path) -> bool:
    return root.is_dir() and not root.is_symlink() and stat.S_IMODE(root.stat().st_mode) == 0o555 and all(stat.S_IMODE(entry.stat().st_mode) == (0o555 if entry.is_dir() else 0o444) for entry in root.rglob("*"))


def write_release_bundle(snapshot: Mapping[str, Any], inventory: Mapping[str, Any], support: Mapping[str, bytes], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise SpainBOEError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent)))
    try:
        files = derive_release_files(snapshot, inventory, support)
        for name, body in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        manifest_body = canonical_json(_manifest(files))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n", encoding="utf-8")
        _freeze_tree(temporary)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SpainBOEError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SpainBOEError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise SpainBOEError(f"{label} must be canonical JSON")
    return value


def validate_release_bundle(root: Path) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink() or not is_frozen_release(root):
        raise SpainBOEError("release must be a frozen regular directory")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise SpainBOEError("release cannot contain symlinks")
    snapshot = _load_json(root / "sanitized-search-snapshot.json", "snapshot")
    inventory = _load_json(root / "retrieval-inventory.json", "inventory")
    support = {path.name: path.read_bytes() for path in (root / "support").iterdir() if path.is_file()}
    derived = derive_release_files(snapshot, inventory, support)
    expected_paths = set(derived) | {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME, "support"}
    actual_paths = {str(path.relative_to(root)) for path in root.rglob("*")}
    if actual_paths != expected_paths:
        raise SpainBOEError("release file set differs")
    for name, body in derived.items():
        if (root / name).read_bytes() != body:
            raise SpainBOEError(f"derived file differs: {name}")
    manifest = _load_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise SpainBOEError("manifest differs")
    expected_sidecar = f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  {MANIFEST_FILENAME}\n"
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != expected_sidecar:
        raise SpainBOEError("manifest sidecar differs")
    definition = _load_json(root / "definition.json", "definition")
    assessment = _load_json(root / "assessment.json", "assessment")
    if definition != source_definition() or assessment["atlas_decision"]["status"] != "publication_level_review_only":
        raise SpainBOEError("release policy differs")
    return {"assessment": assessment, "definition": definition, "inventory": inventory, "manifest": manifest, "snapshot": snapshot}
