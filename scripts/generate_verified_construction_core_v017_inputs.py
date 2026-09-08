#!/usr/bin/env python3
"""Generate the reviewed v0.17 contract and compact geometry-fact capture.

This maintainer utility requires the ignored hydrated v97 and v14 audit corpora.
The generated contract is sufficient for ordinary corpus-free rebuilds.
"""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas import verified_construction_core as v16  # noqa: E402
from datacenter_atlas import verified_construction_core_v017 as v17  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = (
    ROOT / "sources" / "verified-construction-core-v0.17-100-site-geometry-facts.json"
)
CONTRACT_PATH = (
    ROOT / "definitions" / "verified-construction-core-v0.17-100-site-batch.json"
)
V16_CONTRACT_PATH = (
    ROOT
    / "definitions"
    / "verified-construction-core-v0.16-seven-country-diversity-site-batch.json"
)
IDENTITY_DIR = ROOT / "exact_identity_decisions" / "2026-07-22-public-open-v14"


# Reviewed records are intentionally explicit. Raw source bodies remain excluded.
VOLUME_RECORDS = [
    {
        "source_path": "sources/curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json",
        "status_evidence_key": "cdc-brooklyn-remaining-facilities-current-status-captured-2026-07-21",
        "location_evidence_key": "cdc-brooklyn-remaining-facilities-current-status-captured-2026-07-21",
        "locator_id": "cdc-brooklyn-acma-site-10038207-point",
        "geometry_source_document_ids": ["cdc-brooklyn-acma-site-10038207"],
        "geometry": {"type": "Point", "coordinates": [144.843826, -37.817378]},
        "display_anchor": {"type": "Point", "coordinates": [144.843826, -37.817378]},
        "source_documents": [
            {
                "source_id": "cdc-brooklyn-acma-site-10038207",
                "kind": "government_record",
                "title": "ACMA Spectrum Licensing Register site 10038207, 598B Geelong Road Brooklyn",
                "source_url": "https://api.acma.gov.au/SpectrumLicensingAPIOuterService/OuterService.svc/SiteSearchJSON/10038207?searchField=SITE_ID",
                "publisher": "Australian Communications and Media Authority",
                "source_family": "acma_spectrum_licensing_api_site_search",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:50:19Z",
                "license": "ACMA-radiocomms-licence-data-terms",
                "attribution": "Australian Communications and Media Authority",
                "content_hash": "d5e8cd732a84d67b15d2ede54030df677a4f782913997f82f70469055a236ecb",
                "capture": {
                    "bytes": 348,
                    "sha256": "d5e8cd732a84d67b15d2ede54030df677a4f782913997f82f70469055a236ecb",
                    "capture_kind": "official_json_api_response",
                    "redistributed": False,
                },
                "rights_urls": ["https://www.acma.gov.au/radiocomms-licence-data"],
                "facts": {
                    "site_id": 10038207,
                    "address": "598B Geelong Road Brooklyn",
                    "selected_coordinates": [144.843826, -37.817378],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "official_regulatory_site_coordinate",
            "geometry_derivation": "coordinates_to_point",
            "geometry_scope_class": "addressed_regulatory_site_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "ACMA publishes no bounded positional accuracy for this radio-site coordinate.",
            "precision_scope": "Exact ACMA-published six-decimal coordinate for a CDC-linked radio site at the named campus address; not a parcel, building, work area, or facility-allocation boundary.",
        },
        "scope_guardrail": "Use only as a broad Brooklyn campus locator; the row remains the unresolved aggregate of remaining facilities.",
    },
    {
        "source_path": "sources/curated-official-2026-07-21-cdc-maddington-current-build.json",
        "status_evidence_key": "cdc-maddington-structural-shell-captured-2026-07-21",
        "location_evidence_key": "cdc-maddington-current-campus-page-captured-2026-07-21",
        "locator_id": "cdc-maddington-gosnells-lot-500-582-bickley-polygon",
        "geometry_source_document_ids": ["cdc-maddington-gosnells-intramaps-lot-500"],
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [116.00521702, -32.03353993],
                    [116.00570919, -32.0331194],
                    [116.00640586, -32.03371098],
                    [116.00494486, -32.03495966],
                    [116.00391608, -32.03465151],
                    [116.00521702, -32.03353993],
                ]
            ],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [116.0051610444321, -32.034181245],
        },
        "source_documents": [
            {
                "source_id": "cdc-maddington-gosnells-intramaps-lot-500",
                "kind": "government_record",
                "title": "City of Gosnells IntraMaps property result, Lot 500 / 582 Bickley Road",
                "source_url": "https://maps.gosnells.wa.gov.au/intramaps22A/?project=Gosnells",
                "publisher": "City of Gosnells",
                "source_family": "city_of_gosnells_intramaps_property",
                "published_at": None,
                "retrieved_at": "2026-08-23",
                "license": "rights-status-uncertain-fact-extraction-only",
                "attribution": "City of Gosnells",
                "content_hash": "40dbab2d5aa393d92f1f60e27c366d72336764d0a15ba650a6518074f09863d6",
                "capture": {
                    "bytes": 3197,
                    "sha256": "40dbab2d5aa393d92f1f60e27c366d72336764d0a15ba650a6518074f09863d6",
                    "capture_kind": "anonymous_intramaps_property_result",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://www.gosnells.wa.gov.au/Your_property/Online_services/Intramaps"
                ],
                "facts": {
                    "source_crs": "EPSG:7850",
                    "source_wkt": "POLYGON ((406069.5715985168 6455414.109460914,406115.6169012951 6455461.153750732,406182.0042977362 6455396.182130603,406045.3221788193 6455256.495397944,405947.8637164433 6455289.7581829615,406069.5715985168 6455414.109460914))",
                    "transform": "EPSG:7850 to OGC:CRS84 with pyproj 3.7.2; round to 8 decimal degrees",
                    "property": "Lot 500 / 582 Bickley Road",
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "official_property_polygon",
            "geometry_derivation": "official_coordinate_transform",
            "geometry_scope_class": "one_constituent_campus_lot",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The public property service states no survey-grade horizontal accuracy after transformation.",
            "precision_scope": "Exact transformed polygon for one of four officially identified Maddington campus lots; not the complete campus, an individual building, or current work area.",
        },
        "scope_guardrail": "Do not promote the one-lot polygon to the complete CDC Maddington campus or a construction footprint.",
    },
    {
        "source_path": "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json",
        "status_evidence_key": "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20",
        "location_evidence_key": "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20",
        "locator_id": "ascenty-vinhedo-campus-vin02-factsheet-point",
        "geometry_source_document_ids": ["ascenty-vinhedo-campus-factsheet"],
        "geometry": {"type": "Point", "coordinates": [-47.012995, -23.070216]},
        "display_anchor": {"type": "Point", "coordinates": [-47.012995, -23.070216]},
        "source_documents": [
            {
                "source_id": "ascenty-vinhedo-campus-factsheet",
                "kind": "company_disclosure",
                "title": "Ascenty Campus Vinhedo factsheet",
                "source_url": "https://ascenty.com/wp-content/uploads/2025/02/EN-Campus-Vinhedo_compressed.pdf",
                "publisher": "Ascenty",
                "source_family": "ascenty_campus_factsheets",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:50:21Z",
                "license": "all-rights-reserved-fact-extraction-only",
                "attribution": "Ascenty",
                "content_hash": "c30210635d897e4545605e8f035a1678a7e0449d950f206fd4f27cb782c66e3a",
                "capture": {
                    "bytes": 496128,
                    "sha256": "c30210635d897e4545605e8f035a1678a7e0449d950f206fd4f27cb782c66e3a",
                    "capture_kind": "official_pdf_response_body",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://ascenty.com/wp-content/uploads/2025/02/EN-Campus-Vinhedo_compressed.pdf"
                ],
                "facts": {
                    "facility": "VIN02",
                    "address": "Av. João Batista Nunes 50",
                    "selected_coordinates": [-47.012995, -23.070216],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "first_party_published_coordinate",
            "geometry_derivation": "coordinates_to_point",
            "geometry_scope_class": "named_constituent_facility_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The factsheet does not state coordinate accuracy.",
            "precision_scope": "Exact publisher coordinate for VIN02, used only as a broad Vinhedo campus locator for Vinhedo 3; not Vinhedo 3 parcel, building, or work footprint.",
        },
        "scope_guardrail": "The point locates the Vinhedo campus through VIN02 and must not be presented as Vinhedo 3-specific geometry.",
    },
    {
        "source_path": "sources/curated-official-2026-07-21-odata-sp04-phase2-current-build.json",
        "status_evidence_key": "odata-sp04-phase2-site-mobilization-captured-2026-07-21",
        "location_evidence_key": "odata-sp04-current-facility-specification-captured-2026-07-21",
        "locator_id": "odata-sp04-terminal-place-pin",
        "geometry_source_document_ids": ["odata-sp04-current-facility-page-map-pin"],
        "geometry": {"type": "Point", "coordinates": [-46.7760035, -23.4832219]},
        "display_anchor": {"type": "Point", "coordinates": [-46.7760035, -23.4832219]},
        "source_documents": [
            {
                "source_id": "odata-sp04-current-facility-page-map-pin",
                "kind": "company_disclosure",
                "title": "ODATA DC SP04 facility page",
                "source_url": "https://odatacolocation.com/blog/data-center/dc-sp04/",
                "publisher": "ODATA",
                "source_family": "odata_facility_pages",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:50:22Z",
                "license": "all-rights-reserved-fact-extraction-only",
                "attribution": "ODATA",
                "content_hash": "981fe60e0686e205e2ad56f613962f0bc24ba0d49b378348cf81bfb45c1bcae2",
                "capture": {
                    "bytes": 49023,
                    "sha256": "981fe60e0686e205e2ad56f613962f0bc24ba0d49b378348cf81bfb45c1bcae2",
                    "capture_kind": "official_html_response_body",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://odatacolocation.com/blog/data-center/dc-sp04/"
                ],
                "facts": {
                    "address": "Rua Herman 02, Industrial Anhanguera, Osasco",
                    "map_terminal_tokens": "!3d-23.4832219!4d-46.7760035",
                    "selected_coordinates": [-46.7760035, -23.4832219],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "first_party_published_map_pin",
            "geometry_derivation": "first_party_published_map_pin",
            "geometry_scope_class": "operator_facility_pin",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The embedded Google place pin carries no publisher-stated accuracy.",
            "precision_scope": "Operator-embedded terminal place-pin values, not the map viewport center and not a parcel or Phase 2 work footprint; decimal digits are not an accuracy claim.",
        },
        "scope_guardrail": "Use only as a campus locator; never as Phase 2 boundary or construction-footprint geometry.",
    },
    {
        "source_path": "sources/curated-official-2026-07-19-meta-sturgeon-county-alberta.json",
        "status_evidence_key": "meta-sturgeon-county-groundbreaking-2026-07-08-captured-2026-07-19",
        "location_evidence_key": "meta-sturgeon-county-groundbreaking-2026-07-08-captured-2026-07-19",
        "locator_id": "meta-sturgeon-dp26-0028-ats-union-representative-point",
        "geometry_source_document_ids": ["meta-sturgeon-alberta-ats-quarter-sections"],
        "geometry": {
            "type": "Point",
            "coordinates": [-113.18668173255557, 53.8180670512532],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-113.18668173255557, 53.8180670512532],
        },
        "identity_source_document_ids": ["meta-sturgeon-dp26-0028-permit-notice"],
        "source_documents": [
            {
                "source_id": "meta-sturgeon-alberta-ats-quarter-sections",
                "kind": "government_record",
                "title": "Alberta Township System quarter sections named by Sturgeon County DP-26-0028",
                "source_url": "https://geospatial.alberta.ca/titan/rest/services/ags_apps/ags_apps_alberta_township_system/MapServer/2/query",
                "publisher": "Government of Alberta",
                "source_family": "alberta_township_system_arcgis",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:25:17Z",
                "license": "Open-Government-Licence-Alberta",
                "attribution": "Government of Alberta",
                "content_hash": "f55a2324cb403d33cd89deaa6ce47b2e27bb24b77845403c3d1d6d1005194a3a",
                "capture": {
                    "bytes": 7559,
                    "sha256": "f55a2324cb403d33cd89deaa6ce47b2e27bb24b77845403c3d1d6d1005194a3a",
                    "capture_kind": "official_arcgis_geojson_query",
                    "redistributed": False,
                },
                "rights_urls": ["https://open.alberta.ca/licence"],
                "facts": {
                    "query_where": "M=4 AND RGE=22 AND TWP=56 AND ((SEC=2 AND QS IN ('NW','SW')) OR (SEC=3 AND QS IN ('NE','NW','SE','SW')) OR (SEC=10 AND QS IN ('NW','SW','SE')) OR (SEC=11 AND QS IN ('NW','SW'))) AND RA=' '",
                    "query_parameters": {
                        "outFields": "*",
                        "returnGeometry": "true",
                        "outSR": 4326,
                        "f": "geojson",
                    },
                    "feature_count": 11,
                    "raw_feature_ids": [
                        284502,
                        293164,
                        393600,
                        475524,
                        518759,
                        547537,
                        589003,
                        604817,
                        659588,
                        733022,
                        764535,
                    ],
                },
            },
            {
                "source_id": "meta-sturgeon-dp26-0028-permit-notice",
                "kind": "government_record",
                "title": "Development permit approval notice for 56111 Rge Rd 223",
                "source_url": "https://www.sturgeoncounty.ca/development-permit-approval-notice-for-56111-rge-rd-223/",
                "publisher": "Sturgeon County",
                "source_family": "sturgeon_county_development_permit_notices",
                "published_at": "2026-06-16",
                "retrieved_at": "2026-09-07T02:25:33Z",
                "license": "government-copyright-fact-extraction-only",
                "attribution": "Sturgeon County",
                "content_hash": "7efcc7d83996b817bf33374b88e0f2fec005eca9006afc2884393961ca8722fb",
                "capture": {
                    "bytes": 714399,
                    "sha256": "7efcc7d83996b817bf33374b88e0f2fec005eca9006afc2884393961ca8722fb",
                    "capture_kind": "official_html_response_body",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://www.sturgeoncounty.ca/development-permit-approval-notice-for-56111-rge-rd-223/"
                ],
                "facts": {
                    "permit": "DP-26-0028",
                    "approved_use": "Data Processing Facility (Major)",
                    "address": "56111 Rge Rd 223",
                    "named_quarter_sections": [
                        "NW-10-56-22-4",
                        "SW-10-56-22-4",
                        "NW-3-56-22-4",
                        "SW-3-56-22-4",
                        "SE-3-56-22-4",
                        "NE-3-56-22-4",
                        "SW-2-56-22-4",
                        "NW-2-56-22-4",
                        "SW-11-56-22-4",
                        "SE-10-56-22-4",
                        "NW-11-56-22-4",
                    ],
                },
            },
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "project",
            "geometry_use_scope": "project_locator",
            "geometry_method": "official_permit_units_representative_point",
            "geometry_derivation": "official_parcel_union",
            "geometry_scope_class": "representative_point_of_partial_permit_envelope",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The selected permit units include road allowances and non-quarter cadastral identifiers that are not represented by the 11 queried quarter-section polygons.",
            "precision_scope": "Representative point of the deterministic union of 11 official ATS quarter sections named by DP-26-0028; Shapely 2.1.2/GEOS 3.13.1 unary_union followed by representative_point. It is a partial permit-envelope locator, not the full project boundary, parcel survey, building, or work area.",
        },
        "scope_guardrail": "The point is derived from a pinned partial permit envelope and must not be promoted to a complete Meta campus boundary.",
    },
    {
        "source_path": "sources/curated-official-2026-07-19-cyrusone-yorkville-technology-campus.json",
        "status_evidence_key": "cyrusone-yorkville-technology-campus-page-captured-2026-07-19",
        "location_evidence_key": "cyrusone-yorkville-technology-campus-page-captured-2026-07-19",
        "locator_id": "cyrusone-yorkville-c1-parcel-centroid",
        "geometry_source_document_ids": [
            "cyrusone-yorkville-kendall-pin-02-18-300-004-centroid"
        ],
        "geometry": {
            "type": "Point",
            "coordinates": [-88.48222230060607, 41.67716859169509],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-88.48222230060607, 41.67716859169509],
        },
        "source_documents": [
            {
                "source_id": "cyrusone-yorkville-kendall-pin-02-18-300-004-centroid",
                "kind": "government_record",
                "title": "Kendall County parcel centroid for C1 YORKVILLE LLC PIN 02-18-300-004",
                "source_url": "https://maps.co.kendall.il.us/server/rest/services/Hosted/Current_Cadastral_Features/FeatureServer/1/query",
                "publisher": "Kendall County GIS",
                "source_family": "kendall_county_current_cadastral_features",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:58:42Z",
                "license": "county-public-gis-fact-extraction-only",
                "attribution": "Kendall County GIS",
                "content_hash": "6192994f7280ac81e887d52b54223d4b260d6a306d8d9326a9273ffb36547b27",
                "capture": {
                    "bytes": 1535,
                    "sha256": "6192994f7280ac81e887d52b54223d4b260d6a306d8d9326a9273ffb36547b27",
                    "capture_kind": "official_arcgis_json_query",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://maps.co.kendall.il.us/server/rest/services/Hosted/Current_Cadastral_Features/FeatureServer/1"
                ],
                "facts": {
                    "query_where": "pin='02-18-300-004'",
                    "query_parameters": {
                        "outFields": "pin,owner_name,site_address,gis_acres,objectid",
                        "returnGeometry": "false",
                        "returnCentroid": "true",
                        "outSR": 4326,
                        "f": "pjson",
                    },
                    "owner": "C1 YORKVILLE LLC",
                    "address": "2700 ELDAMAIN RD",
                    "gis_acres": 72.52475709,
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "official_parcel_centroid",
            "geometry_derivation": "official_parcel_centroid_to_point",
            "geometry_scope_class": "largest_identified_owner_parcel_centroid",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The county service provides a derived parcel centroid but no survey-grade horizontal accuracy.",
            "precision_scope": "Exact county-returned centroid of one 72.52475709-acre C1 YORKVILLE LLC parcel; not the full campus, a building, or active work area.",
        },
        "scope_guardrail": "Use as a Yorkville campus locator only; it is the centroid of one constituent owner parcel.",
    },
    {
        "source_path": "sources/curated-official-2026-07-20-edged-council-bluffs-first-data-center.json",
        "status_evidence_key": "edged-council-bluffs-first-data-center-topout-2026-07-17-captured-2026-07-20",
        "location_evidence_key": "edged-council-bluffs-groundbreaking-capacity-release-captured-2026-07-20",
        "locator_id": "edged-council-bluffs-pott-address-2313-college-road",
        "geometry_source_document_ids": ["edged-council-bluffs-pott-address-35068"],
        "geometry": {
            "type": "Point",
            "coordinates": [-95.79123326138523, 41.275003017921172],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-95.79123326138523, 41.275003017921172],
        },
        "source_documents": [
            {
                "source_id": "edged-council-bluffs-pott-address-35068",
                "kind": "government_record",
                "title": "Pottawattamie County address point 2313 College Road",
                "source_url": "https://gis.pottcounty-ia.gov/arcgis/rest/services/OpenData/MapServer/9/query",
                "publisher": "Pottawattamie County GIS",
                "source_family": "pottawattamie_county_open_data_address_points",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:58:43Z",
                "license": "county-open-data-no-explicit-license",
                "attribution": "Pottawattamie County GIS",
                "content_hash": "af7fc312e0055acebbbf5bd866219a3d7fd48fc1536c65e1ca5378c979ea8cd1",
                "capture": {
                    "bytes": 437,
                    "sha256": "af7fc312e0055acebbbf5bd866219a3d7fd48fc1536c65e1ca5378c979ea8cd1",
                    "capture_kind": "official_arcgis_geojson_query",
                    "redistributed": False,
                },
                "rights_urls": ["https://www.pottcounty-ia.gov/gis/download_data/"],
                "facts": {
                    "query_where": "Full_Address='2313 COLLEGE RD, COUNCIL BLUFFS, IA 51503'",
                    "object_id": 35068,
                    "global_id": "{AD9D3BA4-0E2F-4D5E-9D54-C6891B4B5E95}",
                    "selected_coordinates": [-95.79123326138523, 41.275003017921172],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "project",
            "geometry_use_scope": "project_locator",
            "geometry_method": "official_address_point",
            "geometry_derivation": "official_address_point",
            "geometry_scope_class": "project_address_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The county address-point layer states no bounded capture accuracy.",
            "precision_scope": "Exact county address point for the permit-linked 2313 College Road site; not a parcel, building footprint, or current work boundary.",
        },
        "scope_guardrail": "Use only as the first Council Bluffs data-center project locator, not an official boundary.",
    },
    {
        "source_path": "sources/curated-official-2026-07-20-digipower-columbiana-shell-v2.json",
        "status_evidence_key": "digipower-columbiana-shell-update-2026-07-07-captured-2026-07-20",
        "location_evidence_key": "digipower-columbiana-shell-update-2026-07-07-captured-2026-07-20",
        "locator_id": "digipowerx-columbiana-census-130-industrial-parkway",
        "geometry_source_document_ids": ["digipowerx-columbiana-census-geocode"],
        "geometry": {
            "type": "Point",
            "coordinates": [-86.61848137903, 33.182787519671],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-86.61848137903, 33.182787519671],
        },
        "source_documents": [
            {
                "source_id": "digipowerx-columbiana-census-geocode",
                "kind": "government_record",
                "title": "U.S. Census geocode for 130 Industrial Parkway, Columbiana",
                "source_url": "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress?address=130%20Industrial%20Pkwy%2C%20Columbiana%2C%20AL&benchmark=Public_AR_Current&vintage=Current_Current&format=json",
                "publisher": "United States Census Bureau",
                "source_family": "census_geocoder_public_ar_current",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:34:21Z",
                "license": "US-federal-public-domain",
                "attribution": "United States Census Bureau",
                "content_hash": "eff57c2bf59f9541f2f0bf4fddd221b89ecc05db93fdf67d60d39ea984b3c096",
                "capture": {
                    "bytes": 4749,
                    "sha256": "eff57c2bf59f9541f2f0bf4fddd221b89ecc05db93fdf67d60d39ea984b3c096",
                    "capture_kind": "official_json_api_response",
                    "redistributed": False,
                },
                "rights_urls": ["https://www.census.gov/about/policies/copyright.html"],
                "facts": {
                    "requested_address": "130 Industrial Pkwy, Columbiana, AL",
                    "selected_coordinates": [-86.61848137903, 33.182787519671],
                    "match_type": "Census address-range geocode",
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "official_address_geocode",
            "geometry_derivation": "official_address_geocode",
            "geometry_scope_class": "address_range_geocode",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "Census supplies an address-range geocode without a bounded horizontal error for this match.",
            "precision_scope": "Exact returned Census coordinate for the project-linked street address; digits are not positional accuracy and the point is not parcel, rooftop, building, or work-area geometry.",
        },
        "scope_guardrail": "Use only as a Columbiana campus locator derived from the project address.",
    },
    {
        "source_path": "sources/curated-official-2026-07-19-vantage-lighthouse-port-washington.json",
        "status_evidence_key": "wisconsin-dnr-lighthouse-current-page-captured-2026-07-19",
        "location_evidence_key": "vantage-lighthouse-location-page-captured-2026-07-19",
        "locator_id": "vantage-lighthouse-wisconsin-dnr-project-coordinate",
        "geometry_source_document_ids": [
            "vantage-lighthouse-wisconsin-dnr-current-page"
        ],
        "geometry": {"type": "Point", "coordinates": [-87.861494, 43.430735]},
        "display_anchor": {"type": "Point", "coordinates": [-87.861494, 43.430735]},
        "source_documents": [
            {
                "source_id": "vantage-lighthouse-wisconsin-dnr-current-page",
                "kind": "government_record",
                "title": "Wisconsin DNR Lighthouse Data Center environmental review page",
                "source_url": "https://dnr.wisconsin.gov/topic/EIA/Portwashington.html",
                "publisher": "Wisconsin Department of Natural Resources",
                "source_family": "wisconsin_dnr_environmental_impact_analysis_pages",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:50:23Z",
                "license": "public-government-record-fact-extraction-only",
                "attribution": "Wisconsin Department of Natural Resources",
                "content_hash": "7452e95750d278a03a1e803d08280b325cc0013f9e842d52da8e637e5f9ca679",
                "capture": {
                    "bytes": 109081,
                    "sha256": "7452e95750d278a03a1e803d08280b325cc0013f9e842d52da8e637e5f9ca679",
                    "capture_kind": "official_html_response_body",
                    "redistributed": False,
                },
                "rights_urls": ["https://dnr.wisconsin.gov/about/publicRecords"],
                "facts": {
                    "source_coordinate_text": "N43430735 W87861494",
                    "selected_coordinates": [-87.861494, 43.430735],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "project",
            "geometry_use_scope": "project_locator",
            "geometry_method": "official_project_coordinate",
            "geometry_derivation": "coordinates_to_point",
            "geometry_scope_class": "environmental_review_project_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "Wisconsin DNR publishes no bounded accuracy for the project coordinate.",
            "precision_scope": "Exact sign-and-decimal parsing of the DNR project coordinate; not a parcel, building, or construction footprint.",
        },
        "scope_guardrail": "The official project point locates Lighthouse broadly and must not be treated as boundary geometry.",
    },
    {
        "source_path": "sources/curated-official-2026-07-20-related-digital-cheyenne-phase1.json",
        "status_evidence_key": "related-digital-cheyenne-current-captured-2026-07-20",
        "location_evidence_key": "related-digital-cheyenne-current-captured-2026-07-20",
        "locator_id": "related-digital-cheyenne-first-party-map-point",
        "geometry_source_document_ids": [
            "related-digital-cheyenne-wyoming-page-map-point"
        ],
        "geometry": {"type": "Point", "coordinates": [-104.7015111, 41.1426277]},
        "display_anchor": {"type": "Point", "coordinates": [-104.7015111, 41.1426277]},
        "source_documents": [
            {
                "source_id": "related-digital-cheyenne-wyoming-page-map-point",
                "kind": "company_disclosure",
                "title": "Related Digital Wyoming campus page",
                "source_url": "https://www.related-digital.com/wyoming",
                "publisher": "Related Digital",
                "source_family": "related_digital_location_pages",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:50:23Z",
                "license": "all-rights-reserved-fact-extraction-only",
                "attribution": "Related Digital",
                "content_hash": "abc21fe88dfdc8dea7f65720db4e9d39c004076f8b24a9204e26f7957c55b2b2",
                "capture": {
                    "bytes": 219717,
                    "sha256": "abc21fe88dfdc8dea7f65720db4e9d39c004076f8b24a9204e26f7957c55b2b2",
                    "capture_kind": "official_html_response_body",
                    "redistributed": False,
                },
                "rights_urls": ["https://www.related-digital.com/wyoming"],
                "facts": {
                    "selected_coordinates": [-104.7015111, 41.1426277],
                    "coordinate_context": "first-party Wyoming project map",
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "first_party_published_map_pin",
            "geometry_derivation": "first_party_published_map_pin",
            "geometry_scope_class": "operator_project_map_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "Related Digital states no bounded accuracy for its embedded map coordinate.",
            "precision_scope": "Exact first-party Wyoming page coordinate, used only as a broad Cheyenne campus locator; not a parcel, Phase 1 building, or work footprint.",
        },
        "scope_guardrail": "Use as a Cheyenne campus locator only; do not imply Phase 1 boundary precision.",
    },
    {
        "source_path": "sources/curated-official-2026-07-21-microsoft-lyle-creek-conover-current-build.json",
        "status_evidence_key": "microsoft-lyle-creek-current-build-captured-2026-07-21",
        "location_evidence_key": "microsoft-lyle-creek-current-build-captured-2026-07-21",
        "locator_id": "microsoft-lyle-creek-usace-published-project-point",
        "geometry_source_document_ids": [
            "microsoft-lyle-creek-usace-saw-2023-00898-index-extract",
            "microsoft-lyle-creek-catawba-containing-parcel",
        ],
        "geometry": {"type": "Point", "coordinates": [-81.205389, 35.731135]},
        "display_anchor": {"type": "Point", "coordinates": [-81.205389, 35.731135]},
        "source_documents": [
            {
                "source_id": "microsoft-lyle-creek-usace-saw-2023-00898-index-extract",
                "kind": "government_record",
                "title": "USACE SAW-2023-00898 public notice indexed coordinate extract",
                "source_url": "https://saw-reg.usace.army.mil/PN/2023/SAW-2023-00898-PN.pdf",
                "publisher": "U.S. Army Corps of Engineers, Wilmington District",
                "source_family": "usace_wilmington_regulatory_public_notices",
                "published_at": "2023-06-01",
                "retrieved_at": "2026-09-06",
                "license": "US-federal-public-domain",
                "attribution": "U.S. Army Corps of Engineers, Wilmington District",
                "content_hash": "68304cc87cc3346f92ed9683f32cefd6651be03dd490a9108e17b9f2929ab623",
                "capture": {
                    "bytes": 242,
                    "sha256": "68304cc87cc3346f92ed9683f32cefd6651be03dd490a9108e17b9f2929ab623",
                    "capture_kind": "official_search_index_exact_text_extraction",
                    "redistributed": False,
                },
                "rights_urls": ["https://www.usa.gov/government-copyright"],
                "facts": {
                    "exact_capture_scope": "UTF-8 bytes of two exact indexed lines separated and terminated by LF",
                    "captured_text_lines": [
                        "Location Description: The 220.19-acre site is located on seven (7) parcels to the northwest of intersection of NC Highway 16 and Northern Drive NW. in Conover, Catawba County, North Carolina.",
                        "Latitude and Longitude: 35.731135 N, -81.205389 W",
                    ],
                    "selected_coordinates": [-81.205389, 35.731135],
                    "raw_pdf_retrieval_guardrail": "The retired saw-reg hostname did not resolve on 2026-09-06; this is not represented as a raw PDF capture.",
                },
            },
            {
                "source_id": "microsoft-lyle-creek-catawba-containing-parcel",
                "kind": "government_record",
                "title": "Catawba County parcel containing the USACE project point",
                "source_url": "https://arcgis2.catawbacountync.gov/arcgis/rest/services/Catawba_Basic_MIL1/MapServer/2/query",
                "publisher": "Catawba County GIS",
                "source_family": "catawba_county_public_parcels",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:43:58Z",
                "license": "county-public-gis-fact-extraction-only",
                "attribution": "Catawba County GIS",
                "content_hash": "0c24acb507b7c8455fab96a03a3388706a92d36d0b94e9b0367833d9c6dd1d3f",
                "capture": {
                    "bytes": 8064,
                    "sha256": "0c24acb507b7c8455fab96a03a3388706a92d36d0b94e9b0367833d9c6dd1d3f",
                    "capture_kind": "official_arcgis_geojson_point_intersection_query",
                    "redistributed": False,
                },
                "rights_urls": ["https://gis.catawbacountync.gov/"],
                "facts": {
                    "query_geometry": "-81.205389,35.731135",
                    "spatial_relation": "esriSpatialRelIntersects",
                    "containing_pin": "374207698666",
                    "calculated_acres": 221.01,
                },
            },
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "project",
            "geometry_use_scope": "project_locator",
            "geometry_method": "official_permit_project_coordinate",
            "geometry_derivation": "coordinates_to_point",
            "geometry_scope_class": "permit_notice_project_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "USACE gives no bounded positional accuracy and the live legacy PDF body is currently unavailable.",
            "precision_scope": "Exact USACE-published project coordinate, independently shown inside a current official Catawba parcel; not a parcel boundary, building, or work footprint. The primary capture is an indexed-text extract, not fetched PDF bytes.",
        },
        "scope_guardrail": "Retain the explicit indexed-extraction caveat; do not relabel its 242-byte hash as the original PDF hash.",
    },
    {
        "source_path": "sources/curated-official-2026-07-19-qts-eagle-mountain-building-2.json",
        "status_evidence_key": "qts-eagle-mountain-location-page-captured-2026-07-19",
        "location_evidence_key": "qts-eagle-mountain-location-page-captured-2026-07-19",
        "locator_id": "qts-eagle-mountain-550-hyperscale-way-address-point",
        "geometry_source_document_ids": [
            "qts-eagle-mountain-utah-county-address-258853"
        ],
        "geometry": {
            "type": "Point",
            "coordinates": [-112.03332438583949, 40.267749221659585],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-112.03332438583949, 40.267749221659585],
        },
        "source_documents": [
            {
                "source_id": "qts-eagle-mountain-utah-county-address-258853",
                "kind": "government_record",
                "title": "Utah County address point 550 E Hyperscale Way",
                "source_url": "https://maps.utahcounty.gov/arcgis/rest/services/Parcels/Parcel_AddressPoints/MapServer/0/query",
                "publisher": "Utah County GIS Division",
                "source_family": "utah_county_parcel_address_points",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:58:44Z",
                "license": "county-public-gis-fact-extraction-only",
                "attribution": "GIS Division, Utah County Information Systems Department",
                "content_hash": "411b422d0166554c31b2989755309d9c40a1003218669f01b3aa624566e81225",
                "capture": {
                    "bytes": 573,
                    "sha256": "411b422d0166554c31b2989755309d9c40a1003218669f01b3aa624566e81225",
                    "capture_kind": "official_arcgis_geojson_query",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://maps.utahcounty.gov/arcgis/rest/services/Parcels/Parcel_AddressPoints/MapServer/0"
                ],
                "facts": {
                    "query_where": "FULLADDR='550 E HYPERSCALE WAY EAGLE MOUNTAIN UT 84005'",
                    "address_id": 258853,
                    "global_id": "{9F10EADF-B64B-4564-9AAF-36ABCF26BA54}",
                    "capture_method": "Placed on Map (Calc Parcel)",
                    "selected_coordinates": [-112.03332438583949, 40.267749221659585],
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "campus",
            "geometry_use_scope": "campus_locator",
            "geometry_method": "official_address_point",
            "geometry_derivation": "official_address_point",
            "geometry_scope_class": "campus_address_point",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The county says the point was calculated from a parcel and supplies no bounded positional error.",
            "precision_scope": "Exact county-returned point for 550 E Hyperscale Way, capture method Placed on Map (Calc Parcel); broad SLC1 campus locator, not Building 2 footprint or parcel boundary.",
        },
        "scope_guardrail": "Use only as a QTS Eagle Mountain campus locator; do not assign the point exclusively to Building 2.",
    },
    {
        "source_path": "sources/curated-official-2026-07-20-edgecore-as02-sterling.json",
        "status_evidence_key": "edgecore-as02-topping-out-linkedin-2026-07-01-captured-2026-07-20",
        "location_evidence_key": "edgecore-ashburn-location-page-current-captured-2026-07-20",
        "locator_id": "edgecore-as02-loudoun-parcel-045465016000",
        "geometry_source_document_ids": ["edgecore-as02-loudoun-parcel-045465016000"],
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-77.4471731, 38.99456075],
                    [-77.4471197, 38.9945421],
                    [-77.44515195, 38.99385516],
                    [-77.44550803, 38.99448669],
                    [-77.44547655, 38.99452871],
                    [-77.44508422, 38.99466447],
                    [-77.44508015, 38.99466564],
                    [-77.44507633, 38.99466746],
                    [-77.44507286, 38.99466989],
                    [-77.44506985, 38.99467286],
                    [-77.44506737, 38.99467629],
                    [-77.44506549, 38.99468009],
                    [-77.44506427, 38.99468414],
                    [-77.44506373, 38.99468834],
                    [-77.44506389, 38.99469257],
                    [-77.44506475, 38.99469671],
                    [-77.44506629, 38.99470065],
                    [-77.44517076, 38.99488108],
                    [-77.44518771, 38.99491599],
                    [-77.44519912, 38.99495307],
                    [-77.44520473, 38.99499147],
                    [-77.4452044, 38.99503027],
                    [-77.44519816, 38.99506857],
                    [-77.44518613, 38.99510546],
                    [-77.44517373, 38.9951427],
                    [-77.44516683, 38.99518133],
                    [-77.44516557, 38.99522056],
                    [-77.44516997, 38.99525955],
                    [-77.44517153, 38.99527921],
                    [-77.44517001, 38.99529887],
                    [-77.44516544, 38.99531806],
                    [-77.44515792, 38.99533629],
                    [-77.44514766, 38.99535313],
                    [-77.44513489, 38.99536816],
                    [-77.44511993, 38.99538101],
                    [-77.44514401, 38.99542407],
                    [-77.44451923, 38.99563945],
                    [-77.44457548, 38.99568029],
                    [-77.44462745, 38.99572646],
                    [-77.44467465, 38.99577751],
                    [-77.4447166, 38.99583294],
                    [-77.44475292, 38.99589222],
                    [-77.44481094, 38.99600199],
                    [-77.44480487, 38.99601799],
                    [-77.44480137, 38.99603474],
                    [-77.44480053, 38.99605182],
                    [-77.44480235, 38.99606883],
                    [-77.4448068, 38.99608535],
                    [-77.44481377, 38.99610098],
                    [-77.44486643, 38.9962006],
                    [-77.4452897, 38.99606437],
                    [-77.4453208, 38.99605585],
                    [-77.44615368, 38.99578777],
                    [-77.4462419, 38.99575848],
                    [-77.44632803, 38.9957235],
                    [-77.44641169, 38.99568299],
                    [-77.44649255, 38.99563713],
                    [-77.44657025, 38.9955861],
                    [-77.44664446, 38.99553012],
                    [-77.44671488, 38.99546944],
                    [-77.4467812, 38.9954043],
                    [-77.44684314, 38.99533498],
                    [-77.44690043, 38.99526178],
                    [-77.44694928, 38.99518698],
                    [-77.44699347, 38.99510935],
                    [-77.44703286, 38.99502916],
                    [-77.44706728, 38.99494673],
                    [-77.44709661, 38.99486235],
                    [-77.44712075, 38.99477634],
                    [-77.4471731, 38.99456075],
                ]
            ],
        },
        "display_anchor": {
            "type": "Point",
            "coordinates": [-77.44612264937976, 38.995010315],
        },
        "source_documents": [
            {
                "source_id": "edgecore-as02-loudoun-parcel-045465016000",
                "kind": "government_record",
                "title": "Loudoun County parcel 045465016000",
                "source_url": "https://logis.loudoun.gov/gis/rest/services/COL_WebMercator/Parcels4DIT/MapServer/0/query",
                "publisher": "Loudoun County, Virginia",
                "source_family": "loudoun_county_parcels4dit",
                "published_at": None,
                "retrieved_at": "2026-09-07T02:41:10Z",
                "license": "Loudoun-County-GIS-disclaimer",
                "attribution": "Loudoun County, Virginia",
                "content_hash": "de595d9f59a4e5c6be959aafe2694df6c3f75a715352dab3579982d80aa33f3c",
                "capture": {
                    "bytes": 2229,
                    "sha256": "de595d9f59a4e5c6be959aafe2694df6c3f75a715352dab3579982d80aa33f3c",
                    "capture_kind": "official_arcgis_geojson_query",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://logis.loudoun.gov/gis/rest/services/COL_WebMercator/Parcels4DIT/MapServer/info/iteminfo"
                ],
                "facts": {
                    "query_where": "PA_MCPI='045465016000'",
                    "query_parameters": {
                        "outFields": "*",
                        "returnGeometry": "true",
                        "outSR": 4326,
                        "f": "geojson",
                    },
                    "mcpi": "045465016000",
                    "arcgis_server_version": 10.91,
                },
            }
        ],
        "semantics": {
            "geometry_authority_class": "official_source",
            "geometry_source_entity_kind": "project",
            "geometry_use_scope": "project_locator",
            "geometry_method": "official_parcel_polygon",
            "geometry_derivation": "direct_geometry",
            "geometry_scope_class": "assessor_linked_project_parcel",
            "official_boundary": False,
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "Loudoun County disclaims accuracy and supplies no survey-grade horizontal error.",
            "precision_scope": "Exact geometryPrecision=8 county parcel geometry for MCPI 045465016000, identity-linked through assessor records to the AS02 address; project locator only, not a surveyed data-center or active-work footprint.",
        },
        "scope_guardrail": "Do not promote the assessor parcel to an official construction or building boundary.",
    },
]

COUNTRY_A_RECORDS = [
    {
        "source_path": "sources/curated-official-2026-09-06-datagrid-makarewa-initial-horizontal-works.json",
        "status_evidence_key": "datagrid-makarewa-horizontal-works-commenced-2026-08-18-captured-2026-09-06",
        "location_evidence_key": "linz-datagrid-makarewa-four-primary-parcels-captured-2026-09-06",
        "locator_id": "datagrid-makarewa-linz-four-core-parcel-union",
        "geometry_source_document_ids": ["datagrid-makarewa-linz-four-primary-parcels"],
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [168.384827983, -46.3295291660578],
                    [168.384828317, -46.3301537660578],
                    [168.38482835, -46.3303396820578],
                    [168.38482825, -46.3324287990578],
                    [168.384828883, -46.3403480990578],
                    [168.386062717, -46.3402225660578],
                    [168.38858755, -46.3400982660578],
                    [168.390196467, -46.3403199320578],
                    [168.390195033, -46.3337380490578],
                    [168.390194017, -46.3324285990578],
                    [168.390191983, -46.3295114820578],
                    [168.38737445, -46.3295208320578],
                    [168.387316117, -46.3295210820578],
                    [168.38492565, -46.3295289990578],
                    [168.384827983, -46.3295291660578],
                ]
            ],
        },
        "display_anchor": {
            "method": "point_on_surface_of_canonical_parcel_union",
            "coordinates": [168.38751216734653, -46.336918157557804],
        },
        "source_documents": [
            {
                "source_id": "datagrid-makarewa-linz-four-primary-parcels",
                "kind": "government_record",
                "title": "LINZ NZ Primary Parcels - four Datagrid Makarewa core-campus parcels",
                "source_url": "https://services.arcgis.com/xdsHIIxuCWByZiCB/ArcGIS/rest/services/LINZ_NZ_Primary_Parcels/FeatureServer/0/query?where=appellation+IN+%28%27Lot+1+DP+595572%27%2c%27Lot+2+DP+595572%27%2c%27Lot+3+DP+595572%27%2c%27Lot+2+DP+526953%27%29&outFields=OBJECTID%2cid%2cappellation%2cparcel_intent%2ctopology_type%2cland_district%2ctitles%2csurvey_area%2ccalc_area%2cShape__Area%2cShape__Length&returnGeometry=true&outSR=4326&orderByFields=appellation+ASC&f=geojson",
                "publisher": "Land Information New Zealand",
                "source_family": "linz_nz_primary_parcels",
                "published_at": "",
                "retrieved_at": "2026-09-07T02:26:38Z",
                "license": "CC-BY-4.0",
                "attribution": "Crown copyright - Land Information New Zealand; CC BY 4.0",
                "content_hash": "e8823967334879161cf139277879260228bea45bd079647ec71467f5718a6059",
                "capture": {
                    "bytes": 2855,
                    "sha256": "e8823967334879161cf139277879260228bea45bd079647ec71467f5718a6059",
                    "capture_kind": "raw_official_geojson_response_hash_only",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://data.linz.govt.nz/layer/50772-nz-primary-parcels/",
                    "https://data.linz.govt.nz/license/attribution-4-0-international/",
                ],
                "facts": {
                    "arcgis_item_id": "7442ad2e98534d67a3c45df9b7fbcf5e",
                    "arcgis_item_metadata_bytes": 6250,
                    "arcgis_item_metadata_sha256": "4a9855a460716b60a195888d8ded367f85b74bee9ef4f1d420ec34284b040aa4",
                    "returned_feature_count": 4,
                    "selected_features": [
                        {
                            "feature_id": 8584007,
                            "appellation": "Lot 1 DP 595572",
                            "title": "1149470",
                        },
                        {
                            "feature_id": 7926438,
                            "appellation": "Lot 2 DP 526953",
                            "title": "847503",
                        },
                        {
                            "feature_id": 8584008,
                            "appellation": "Lot 2 DP 595572",
                            "title": "1149471",
                        },
                        {
                            "feature_id": 8584009,
                            "appellation": "Lot 3 DP 595572",
                            "title": "1149472",
                        },
                    ],
                    "geometry_crs": "EPSG:4326",
                    "canonical_union_bytes_without_newline": 541,
                    "canonical_union_sha256_without_newline": "839bcebf9f75a452c6bd24107c68f09768013a5e36b38c1fee26e0a1b0a7bae8",
                    "derivation": "Require the four pinned feature ids, appellations and titles; dissolve their exact returned polygons; serialize the GeoJSON geometry with UTF-8, sorted keys and compact separators.",
                },
            },
            {
                "source_id": "datagrid-makarewa-sdc-resource-consent-application",
                "kind": "government_record",
                "title": "Application - Datagrid New Zealand Partnership Limited",
                "source_url": "https://www.southlanddc.govt.nz/assets/Planning-Resource-Consent/datagrid/01-Application/0-Application-Datagrid-New-Zealand-Partnership-Limited.pdf",
                "publisher": "Southland District Council",
                "source_family": "southland_district_council_resource_consent_records",
                "published_at": "",
                "retrieved_at": "2026-09-07T02:58:29Z",
                "license": "all-rights-reserved",
                "attribution": "Southland District Council",
                "content_hash": "0be599c4ee13fec35028279ab6a0db7bfed287f885651ec8f26ee6f5e0fac994",
                "capture": {
                    "bytes": 3842279,
                    "sha256": "0be599c4ee13fec35028279ab6a0db7bfed287f885651ec8f26ee6f5e0fac994",
                    "capture_kind": "raw_public_pdf_response_hash_only",
                    "redistributed": False,
                },
                "facts": {
                    "applicant": "Datagrid New Zealand Partnership Limited",
                    "site_addresses": [
                        "342 and 370 Flora Road East, Makarewa",
                        "63 Taylor Road, Makarewa",
                    ],
                    "core_campus_parcels": [
                        "Lot 1 DP 595572 (RT 1149470)",
                        "Lot 2 DP 595572 (RT 1149471)",
                        "Lot 3 DP 595572 (RT 1149472)",
                        "Lot 2 DP 526953 (RT 847503)",
                    ],
                    "excluded_access_property_parcels": [
                        "Lot 10 DP 14668 (RT SL11C/835)",
                        "Lot 13 DP 14668 (RT 7092)",
                    ],
                    "identity_bridge": "Applicant, Makarewa data-centre description, addresses, legal descriptions and title ids bind the first-party build to the selected LINZ parcels.",
                },
            },
        ],
        "identity_source_document_ids": [
            "datagrid-makarewa-sdc-resource-consent-application"
        ],
        "semantics": {
            "geometry_source_entity_kind": "campus",
            "geometry_derivation": "official_primary_parcel_union",
            "geometry_method": "linz_title_matched_primary_parcels_deterministic_union",
            "geometry_scope_class": "official_cadastral_union_as_core_campus_locator",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "campus_locator",
            "official_boundary": False,
            "precision_scope": "Current LINZ cadastral union for the four exact title-matched parcels making up about 49.2 hectares. It is not an asserted official project boundary, work extent, building footprint, as-built survey, or the full six-parcel consent property.",
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "LINZ publishes broad nominal urban and rural ranges but no bounded project-specific horizontal accuracy for this dissolved four-parcel locator.",
        },
        "scope_guardrail": "Accept as a campus locator inherited through explicit project_targets only; exclude the two DP 14668 access or haul-road parcels; create no lifecycle, capacity, workload, boundary, construction-extent, or as-built claim from geometry.",
    },
    {
        "source_path": "sources/curated-official-2026-07-21-niger-national-dc-pk5-current-build.json",
        "status_evidence_key": "niger-national-dc-equipment-installation-june-2026-captured-2026-07-21",
        "location_evidence_key": "niger-national-dc-equipment-installation-june-2026-captured-2026-07-21",
        "locator_id": "niger-national-dc-pk5-bnee-eies-project-point",
        "geometry_source_document_ids": ["niger-national-dc-pk5-bnee-eies"],
        "geometry": {"type": "Point", "coordinates": [2.113511111111, 13.559683333333]},
        "display_anchor": {
            "method": "official_project_area_coordinate",
            "coordinates": [2.113511111111, 13.559683333333],
        },
        "source_documents": [
            {
                "source_id": "niger-national-dc-pk5-bnee-eies",
                "kind": "government_record",
                "title": "Final environmental and social impact assessment - national data center at PK5, Niamey II",
                "source_url": "https://www.bnee.ne/wp-content/uploads/2022/08/Rapport-de%CC%81finitif-EIES-DATACENTER-PK5-Niamey_VP.pdf",
                "publisher": "Bureau National d'Evaluation Environnementale, Republic of Niger",
                "source_family": "niger_bnee_environmental_assessment_records",
                "published_at": "2022-08",
                "retrieved_at": "2026-09-07T03:05:27Z",
                "license": "all-rights-reserved",
                "attribution": "Republic of Niger, Ministry of Posts and New Information Technologies / BNEE",
                "content_hash": "f9fc8e51e9cabc4e6bfd30f9b09f678a2a68fb92a61b1f62973c41210f108fb1",
                "capture": {
                    "bytes": 7069422,
                    "sha256": "f9fc8e51e9cabc4e6bfd30f9b09f678a2a68fb92a61b1f62973c41210f108fb1",
                    "capture_kind": "raw_public_pdf_response_hash_only",
                    "redistributed": False,
                },
                "facts": {
                    "document_version": "Version Definitive",
                    "document_date": "2022-08",
                    "pages": 133,
                    "project_name": "National data center at PK5, Arrondissement Communal Niamey II",
                    "project_area_coordinate_dms": {
                        "longitude": "2°6'48.64\"E",
                        "latitude": "13°33'34.86\"N",
                    },
                    "coordinate_decimal_rounded_12dp": [
                        2.113511111111,
                        13.559683333333,
                    ],
                    "coordinate_derivation": "Convert the repeatedly reported project-area DMS values to positive east/north decimal degrees and round each once to 12 decimal places.",
                    "capture_headers_bytes": 261,
                    "capture_headers_sha256": "87d35e537fd1024719f8a431b5e005b2d7a5310830bf7ba3e05ac278549b0278",
                },
            },
        ],
        "identity_source_document_ids": ["niger-national-dc-pk5-bnee-eies"],
        "semantics": {
            "geometry_source_entity_kind": "project",
            "geometry_derivation": "official_dms_coordinate_to_point",
            "geometry_method": "bnee_eies_project_area_coordinate",
            "geometry_scope_class": "official_environmental_assessment_project_point",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "project_locator",
            "official_boundary": False,
            "precision_scope": "The point is the EIES-reported coordinate of the project area at the selected Niger Telecom PK5 site. It is not a surveyed entrance, parcel centroid, building footprint, campus boundary, or current-work extent.",
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The EIES reports DMS precision but no survey method, datum-specific accuracy statement, or bounded horizontal uncertainty.",
        },
        "scope_guardrail": "Use only as the exact official project-area point for the PK5 national data-center build; do not infer boundary, entrance, work extent, capacity, completion, commissioning, occupancy, or operation.",
    },
    {
        "source_path": "sources/curated-official-2026-07-21-mobile-plateau-haidong-phase-2-current-build.json",
        "status_evidence_key": "china-mobile-plateau-haidong-phase2-build-2026-06-23",
        "location_evidence_key": "china-mobile-plateau-haidong-phase2-build-2026-06-23",
        "locator_id": "china-mobile-haidong-phase2-stage1-eia-project-point",
        "geometry_source_document_ids": ["china-mobile-haidong-phase2-stage1-eia"],
        "geometry": {
            "type": "Point",
            "coordinates": [102.007272777778, 36.509652222222],
        },
        "display_anchor": {
            "method": "official_project_center_coordinate",
            "coordinates": [102.007272777778, 36.509652222222],
        },
        "source_documents": [
            {
                "source_id": "china-mobile-haidong-phase2-stage1-eia",
                "kind": "government_record",
                "title": "Environmental impact report - China Mobile (Qinghai Haidong) Data Center Phase 2 Stage 1",
                "source_url": "https://www.haidong.gov.cn/haidongos/ewebeditor/uploadfile/2025051314534893333.pdf",
                "publisher": "Haidong Municipal People's Government",
                "source_family": "haidong_government_environmental_assessment_records",
                "published_at": "2025-05-13",
                "retrieved_at": "2026-09-07T02:24:44Z",
                "license": "all-rights-reserved",
                "attribution": "Haidong Municipal People's Government",
                "content_hash": "17b3d141857a4b0dcc92c59bf35a6349bf844525f7cd9c6d470b22ee655d9c2e",
                "capture": {
                    "bytes": 7681148,
                    "sha256": "17b3d141857a4b0dcc92c59bf35a6349bf844525f7cd9c6d470b22ee655d9c2e",
                    "capture_kind": "raw_public_pdf_response_hash_only",
                    "redistributed": False,
                },
                "facts": {
                    "project_name": "China Mobile (Qinghai Haidong) Data Center Phase 2 Stage 1 B01 data-center building, C01 power center and outdoor supporting project",
                    "project_code": "2408-631000-04-01-977150",
                    "project_center_coordinate_dms": {
                        "longitude": "102°0'26.182\"E",
                        "latitude": "36°30'34.748\"N",
                    },
                    "coordinate_decimal_rounded_12dp": [
                        102.007272777778,
                        36.509652222222,
                    ],
                    "coordinate_derivation": "Convert the report's project-center DMS values to positive east/north decimal degrees and round each once to 12 decimal places.",
                    "site_context": "Haidong Hehuang New Area; north of the site is the existing Phase 1 Plateau Big Data Center, east is Zhiyuan Road, south is Tangfan Avenue.",
                    "capture_headers_bytes": 187,
                    "capture_headers_sha256": "5c4ad807ba07b587440a2c266749b09a25697b831a9cad2ff510743bc604d3b6",
                },
            },
        ],
        "identity_source_document_ids": ["china-mobile-haidong-phase2-stage1-eia"],
        "semantics": {
            "geometry_source_entity_kind": "project",
            "geometry_derivation": "official_dms_coordinate_to_point",
            "geometry_method": "haidong_government_eia_project_center_coordinate",
            "geometry_scope_class": "official_environmental_assessment_phase2_stage1_project_point",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "project_locator",
            "official_boundary": False,
            "precision_scope": "The point is the official EIA project-center coordinate for Phase 2 Stage 1 and locates the named Phase 2 build. It is not a surveyed entrance, parcel centroid, campus boundary, building footprint, or current-work extent.",
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "The EIA reports a project-center coordinate but no bounded horizontal-accuracy or survey-method statement.",
        },
        "scope_guardrail": "Use only as the phase-specific official project locator. The 2026-06-23 municipal bulletin supports generic under_construction only; do not infer operation, completion, finer construction stage, capacity, workload, boundary, or work extent.",
    },
    {
        "source_path": "sources/curated-official-2026-09-06-dansk-data-center-1-esbjerg-current-build.json",
        "status_evidence_key": "dansk-data-center-1-esbjerg-groundbreaking-2026-08-13-captured-2026-09-06",
        "location_evidence_key": "dataforsyningen-sahara-9-address-point-captured-2026-09-06",
        "locator_id": "dansk-data-center-1-esbjerg-dar-sahara-9-address-point",
        "geometry_source_document_ids": ["ddc1-esbjerg-dar-sahara-9-address-point"],
        "geometry": {"type": "Point", "coordinates": [8.45990497, 55.45823408]},
        "display_anchor": {
            "method": "official_access_address_point",
            "coordinates": [8.45990497, 55.45823408],
        },
        "source_documents": [
            {
                "source_id": "ddc1-esbjerg-dar-sahara-9-address-point",
                "kind": "government_record",
                "title": "Danmarks Adresseregister access-address point for Sahara 9, Esbjerg",
                "source_url": "https://api.dataforsyningen.dk/adgangsadresser/b0351879-20c7-47f9-8cde-54dad6a417a8?format=geojson&srid=4326",
                "publisher": "Klimadatastyrelsen",
                "source_family": "denmark_authoritative_address_register_points",
                "published_at": "",
                "retrieved_at": "2026-09-07T02:43:39Z",
                "license": "CC-BY-4.0",
                "attribution": "Klimadatastyrelsen / Danmarks Adresseregister (DAR); CC BY 4.0",
                "content_hash": "91c713f41cf392a2ea54625308c13b9e5d9311ebe8bc2415a27db8b14187e099",
                "capture": {
                    "bytes": 2821,
                    "sha256": "91c713f41cf392a2ea54625308c13b9e5d9311ebe8bc2415a27db8b14187e099",
                    "capture_kind": "raw_official_geojson_response_hash_only",
                    "redistributed": False,
                },
                "rights_urls": [
                    "https://dataforsyningen.dk/asset/PDF/rettigheder_vilkaar/Vilk%C3%A5r%20for%20frie%20geografiske%20data%20og%20CC%20BY%204_0%20licens.pdf"
                ],
                "facts": {
                    "address_feature_id": "b0351879-20c7-47f9-8cde-54dad6a417a8",
                    "address_point_id": "8d781621-1f64-4c6e-b81b-d82f871f8493",
                    "designation": "Sahara 9, 6700 Esbjerg",
                    "cadastral_district": "Esbjerg Bygrunde",
                    "cadastral_parcel": "1419o",
                    "coordinate": [8.45990497, 55.45823408],
                    "point_accuracy_code": "A",
                    "point_source_code": 5,
                    "technical_standard": "TK",
                    "license_pdf_bytes": 28206,
                    "license_pdf_sha256": "8b91278be13f6091383e79e505de6a404ee17a1fdbf11a9a19550bb601bfa1a1",
                },
            },
            {
                "source_id": "ddc1-esbjerg-dma-facility-record",
                "kind": "government_record",
                "title": "Dansk Datacenter 1 K/S - Digital Miljoeadministration",
                "source_url": "https://dma.mst.dk/vis-virksomhed/6caab521-290e-45ba-aabd-17d4f2a86c17",
                "publisher": "Danish Environmental Protection Agency",
                "source_family": "denmark_digital_environmental_administration_facility_records",
                "published_at": "",
                "retrieved_at": "2026-09-07T02:43:12Z",
                "license": "all-rights-reserved",
                "attribution": "Danish Environmental Protection Agency",
                "content_hash": "338bdebd3abb7e48fccb3aa2f84e6eac747d7667e5fd7b2f3edcdd280ded7708",
                "capture": {
                    "bytes": 23919,
                    "sha256": "338bdebd3abb7e48fccb3aa2f84e6eac747d7667e5fd7b2f3edcdd280ded7708",
                    "capture_kind": "raw_public_html_response_hash_only",
                    "redistributed": False,
                },
                "facts": {
                    "facility_name": "Dansk Datacenter 1 K/S",
                    "cvr_number": "45807061",
                    "facility_system_key": "d6948c4b-0c13-4e40-9bd2-519bb8450b69",
                    "address": "Sahara 9, 6700 Esbjerg",
                    "cadastral_parcel": "1419o - Esbjerg Bygrunde",
                    "identity_bridge": "The exact legal-facility name, address and cadastral parcel bind DDC1 to the DAR feature without a generic geocoder or third-party directory.",
                },
            },
        ],
        "identity_source_document_ids": ["ddc1-esbjerg-dma-facility-record"],
        "semantics": {
            "geometry_source_entity_kind": "campus",
            "geometry_derivation": "official_address_feature_to_point",
            "geometry_method": "dar_access_address_point_for_dma_bound_ddc1_site",
            "geometry_scope_class": "official_access_address_point_as_campus_locator",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "campus_locator",
            "official_boundary": False,
            "precision_scope": "Exact current DAR access-address point for Sahara 9, inherited through the DDC1 project_targets relationship. It is not a surveyed project point, entrance, parcel centroid, site boundary, building footprint, or construction extent.",
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "DAR returns accuracy code A but the captured feature supplies no bounded numeric horizontal uncertainty applicable to this point.",
        },
        "scope_guardrail": "Address-point locator only; create no official-boundary, building, work-extent, capacity, completion, commissioning, occupancy, energization, or operation claim.",
    },
]

COUNTRY_B_RECORDS = [
    {
        "source_path": "sources/curated-official-2026-09-06-cra-prague-gateway-current-campus-build-successor.json",
        "status_evidence_key": "cra-prague-gateway-broken-ground-current-build-2026-08-20-captured-2026-09-06",
        "locator_id": "cra-prague-gateway-cuzk-permit-parcels-point-on-surface",
        "geometry_source_document_ids": ["cra-prague-gateway-cuzk-permit-parcels"],
        "scope_guardrail": (
            "The official permit names the two cadastral parcels and the current "
            "official RUIAN service supplies their geometry. The selected point on "
            "their topological union is only a campus locator. It is not an official "
            "boundary, first-building location, project or construction footprint, "
            "entrance, surveyed point, or accuracy claim."
        ),
        "source_documents": [
            {
                "source_id": "cra-prague-gateway-cuzk-permit-parcels",
                "kind": "government_record",
                "title": "CUZK RUIAN geometries for permit-named Jiloviste parcels 505/2 and st. 379",
                "source_url": "https://ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/5/query?where=katastralniuzemi%3d660175+AND+%28%28cisloparcely%3d%27505%2f2%27+AND+druhcislovanikod%3d2%29+OR+%28cisloparcely%3d%27379%27+AND+druhcislovanikod%3d1%29%29&outFields=id%2ccisloparcely%2ckatastralniuzemi%2ckmenovecislo%2cpoddelenicisla%2cdruhcislovanikod%2cvymeraparcely%2cplatiod%2cplatido%2czdroj&returnGeometry=true&outSR=4326&f=geojson",
                "publisher": "Czech Office for Surveying, Mapping and Cadastre (CUZK)",
                "source_family": "cuzk_ruian_parcels",
                "published_at": "",
                "retrieved_at": "2026-09-06",
                "license": "all-rights-reserved",
                "attribution": "Czech Office for Surveying, Mapping and Cadastre (CUZK)",
                "content_hash": "f0256622e85d0b2662e2c38a4938b4735e95a6982872f397009c6a2eb3e08c42",
                "capture": {
                    "bytes": 5638,
                    "sha256": "f0256622e85d0b2662e2c38a4938b4735e95a6982872f397009c6a2eb3e08c42",
                    "capture_kind": "content_decoded_geojson_response",
                    "redistributed": False,
                },
                "facts": {
                    "returned_feature_count": 2,
                    "cadastral_unit_code": 660175,
                    "permit_named_parcels": ["505/2", "st. 379"],
                    "permit_source_url": "https://jiloviste.cz/wp-content/uploads/2024/10/OUR-kabel-TR-Zbraslav.pdf",
                    "permit_capture_bytes": 206720,
                    "permit_capture_sha256": "d4fe60f75a119f580d64948d657ecda820515c16cbb5e4fb1b572bc80e15547c",
                    "derivation": (
                        "Require the two exact permit-named features, form their "
                        "topological union, then take the union's point on surface."
                    ),
                    "representative_point": [14.36784629256487, 49.948186441032426],
                },
            }
        ],
        "identity_source_document_ids": ["cra-prague-gateway-cuzk-permit-parcels"],
        "geometry": {
            "type": "Point",
            "coordinates": [14.36784629256487, 49.948186441032426],
        },
        "display_anchor": {
            "method": "point_on_surface_of_permit_linked_parcel_union",
            "coordinates": [14.36784629256487, 49.948186441032426],
        },
        "semantics": {
            "geometry_source_entity_kind": "campus",
            "geometry_derivation": "official_parcel_union_point_on_surface",
            "geometry_method": "cuzk_permit_named_parcel_union_as_campus_locator",
            "geometry_scope_class": "official_parcels_as_campus_locator",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "campus_locator",
            "official_boundary": False,
            "precision_scope": (
                "A deterministic point on the union of two current official parcel "
                "geometries named by the permit. It locates the wider CRA site only "
                "and is not an official campus boundary, building or work footprint, "
                "entrance, surveyed project point, or horizontal-accuracy claim."
            ),
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": (
                "No project-applicable bounded horizontal accuracy was selected from CUZK."
            ),
        },
    },
    {
        "source_path": "sources/curated-official-2026-09-06-data-world-matatirtha-current-build.json",
        "status_evidence_key": "ifc-worldlink-matatirtha-green-data-center-current-build-july-2026-captured-2026-09-06",
        "locator_id": "data-world-matatirtha-first-party-kathmandu-marker",
        "geometry_source_document_ids": [
            "data-world-matatirtha-first-party-kathmandu-marker"
        ],
        "scope_guardrail": (
            "The first-party Data World site publishes a Kathmandu marker and Ward "
            "no. 8, Chandragiri for its in-development facility. The exact marker is "
            "a broad campus locator only, not a project point, entrance, parcel, "
            "building footprint, construction extent, or accuracy claim."
        ),
        "source_documents": [
            {
                "source_id": "data-world-matatirtha-first-party-kathmandu-marker",
                "kind": "company_disclosure",
                "title": "Data World data-center locations map",
                "source_url": "https://dataworld.com.np/",
                "publisher": "Data World",
                "source_family": "data_world_facility_pages",
                "published_at": "",
                "retrieved_at": "2026-09-06",
                "license": "all-rights-reserved",
                "attribution": "Data World",
                "content_hash": "1322f2ae76690dfbaf0b0a5f494b7485db72e27e81799faef3aa8c0ac6819735",
                "capture": {
                    "bytes": 169600,
                    "sha256": "1322f2ae76690dfbaf0b0a5f494b7485db72e27e81799faef3aa8c0ac6819735",
                    "capture_kind": "content_decoded_html_response",
                    "redistributed": False,
                },
                "facts": {
                    "marker_name": "Kathmandu",
                    "facility_state": "In Development",
                    "location_as_reported": "Ward no. 8, Chandragiri",
                    "marker_coordinate": [85.2365411, 27.6786359],
                    "capacity_guardrail": (
                        "Page capacity and rack marketing figures are not selected, "
                        "reconciled, or emitted."
                    ),
                },
            }
        ],
        "identity_source_document_ids": [
            "data-world-matatirtha-first-party-kathmandu-marker"
        ],
        "geometry": {
            "type": "Point",
            "coordinates": [85.2365411, 27.6786359],
        },
        "display_anchor": {
            "method": "source_published_location_marker",
            "coordinates": [85.2365411, 27.6786359],
        },
        "semantics": {
            "geometry_source_entity_kind": "campus",
            "geometry_derivation": "source_marker_decimal_coordinates_to_point_without_centroiding",
            "geometry_method": "data_world_named_kathmandu_marker_as_matatirtha_campus_locator",
            "geometry_scope_class": "first_party_facility_map_marker_as_campus_locator",
            "geometry_authority_class": "official_source",
            "geometry_use_scope": "campus_locator",
            "official_boundary": False,
            "precision_scope": (
                "The exact first-party Kathmandu marker is linked to the IFC-named "
                "Matatirtha project through Data World, Chandragiri, and singular "
                "facility context. It is only a broad campus locator, not an entrance, "
                "parcel, surveyed point, boundary, footprint, or work extent."
            ),
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": (
                "Data World publishes no marker collection method, represented "
                "feature, datum, or bounded horizontal accuracy."
            ),
        },
    },
]

ROMANIA_RECORD: dict[str, Any] = {
    "source_path": (
        "sources/curated-official-2026-07-22-"
        "nxdata3-bucharest-current-build-successor.json"
    ),
    "status_evidence_key": (
        "nxdata3-official-foundation-progress-2026-06-02-captured-2026-07-22"
    ),
    "location_evidence_key": "nxdata3-project-page-design-captured-2026-07-22",
    "locator_id": "nxdata3-buh3-inflect-datacenter-marker",
    "geometry_source_document_ids": ["nxdata3-inflect-datacenter-marker"],
    "source_documents": [
        {
            "source_id": "nxdata3-inflect-datacenter-marker",
            "kind": "commercial_directory_record",
            "title": "NXDATA Bucharest 3",
            "source_url": (
                "https://inflect.com/building/38-ring-road-tunari/"
                "nxdata/datacenter/nxdata-3"
            ),
            "publisher": "Inflect, Inc.",
            "source_family": "inflect_datacenter_directory_pages",
            "published_at": "",
            "retrieved_at": "2026-09-07T02:53:15Z",
            "license": "all-rights-reserved-fact-extraction-only",
            "attribution": "Inflect, Inc.; compact factual extraction only",
            "content_hash": (
                "b548279e42881c26ff54e44fd92d6ade111c7ec98dbcdabeae7d3f70ab30f83b"
            ),
            "capture": {
                "bytes": 270907,
                "sha256": (
                    "b548279e42881c26ff54e44fd92d6ade111c7ec98dbcdabeae7d3f70ab30f83b"
                ),
                "capture_kind": "content_decoded_html_response",
                "method": (
                    "credential_free_curl_fail_location_compressed_desktop_user_agent"
                ),
                "http_status": 200,
                "effective_url": (
                    "https://inflect.com/building/38-ring-road-tunari/"
                    "nxdata/datacenter/nxdata-3"
                ),
                "content_type": "text/html; charset=utf-8",
                "transfer_compressed_bytes": 41597,
                "headers_bytes": 1768,
                "headers_sha256": (
                    "082e330dd534dd1ff63fa8e4da1539e506cfca83a4a5721fc224c2e546afec04"
                ),
                "started_at": "2026-09-07T02:53:15Z",
                "finished_at": "2026-09-07T02:53:15Z",
                "credentials_used": False,
                "redistributed": False,
                "repeat_fetch_raw_hash_stable": False,
            },
            "rights_urls": ["https://inflect.com/terms"],
            "rights_metadata": {
                "source_url": "https://inflect.com/terms",
                "retrieved_at": "2026-09-07T02:53:27Z",
                "http_status": 200,
                "capture_kind": "content_decoded_html_response",
                "bytes": 293916,
                "sha256": (
                    "4451cb93a2f158bd68d25c13c0b136bb60cbdfdcef380486b7a5b84bab007f91"
                ),
                "headers_bytes": 1346,
                "headers_sha256": (
                    "b4a492c4789bfd7032579022618ddbecc7f75d2270e15d1e3b64286b4809d8df"
                ),
                "license_label": "all-rights-reserved",
                "redistributed": False,
            },
            "facts": {
                "location_id": "4e8a6767-f5bc-4496-b795-37d5c2bd55cf",
                "name": "NXDATA Bucharest 3",
                "operator": "NXDATA",
                "facility_type": "Data Center",
                "address": "38 Bucharest Ring Road Bucharest 077180 ROU",
                "coordinate_crs": "CRS84",
                "coordinate": [26.129117, 44.538685],
                "source_encoding": (
                    "Next.js serialized page properties and Google Static Maps "
                    "center/marker"
                ),
                "capture_derivation": (
                    "The exact decimal marker was read from the named NXDATA Bucharest "
                    "3 page properties and repeated by its static-map center/marker. "
                    "Atlas performs no centroid calculation."
                ),
            },
        }
    ],
    "geometry": {
        "type": "Point",
        "coordinates": [26.129117, 44.538685],
    },
    "display_anchor": {
        "method": "source_published_location_marker",
        "coordinates": [26.129117, 44.538685],
    },
    "identity_source_document_ids": ["nxdata3-inflect-datacenter-marker"],
    "semantics": {
        "geometry_source_entity_kind": "project",
        "geometry_derivation": (
            "source_published_marker_to_point_without_atlas_centroiding"
        ),
        "geometry_method": (
            "inflect_named_nxdata_bucharest_3_location_marker_as_project_locator"
        ),
        "geometry_scope_class": (
            "commercial_directory_named_data_center_marker_as_project_locator"
        ),
        "geometry_authority_class": "community_source",
        "geometry_use_scope": "project_locator",
        "official_boundary": False,
        "precision_scope": (
            "Atlas copies the exact page-issued marker and calculates no centroid. "
            "Treat it only as a locator for the named NXDATA Bucharest 3 record. "
            "It is not an entrance, surveyed point, parcel, building footprint, "
            "campus boundary, project footprint, construction extent, or horizontal-"
            "accuracy claim. Inflect does not disclose whether its upstream marker was "
            "geocoded, manually selected, or otherwise derived."
        ),
        "horizontal_uncertainty_metres": None,
        "horizontal_uncertainty_unknown_reason": (
            "Inflect publishes no collection method, represented feature, datum, or "
            "bounded horizontal accuracy for this marker."
        ),
    },
    "scope_guardrail": (
        "Accept only the exact Inflect marker as a project locator after binding it to "
        "the official NXDATA project name, operator, and 38 Bucharest Ring Road address. "
        "Do not redistribute the captured HTML or terms, infer a boundary or footprint, "
        "or use geometry as lifecycle evidence."
    ),
}

RECORDS: list[dict[str, Any]] = [
    *VOLUME_RECORDS,
    *COUNTRY_A_RECORDS,
    *COUNTRY_B_RECORDS,
    ROMANIA_RECORD,
]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_sha256(row: dict[str, str]) -> str:
    return hashlib.sha256(v16._json_bytes(row)).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _replace_payloads(payloads: tuple[tuple[Path, bytes], ...]) -> None:
    """Stage every payload before replacing any output, atomically per file.

    Validation and staging errors leave the existing pair untouched. Replacing
    two paths is not a crash-atomic transaction: an interruption or replacement
    error can still leave a mixed pair. The contract's capture hash detects that
    state; rerun this utility to replace both files from the reviewed records.
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for path, payload in payloads:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
            ) as handle:
                temporary_path = Path(handle.name)
                staged.append((temporary_path, path))
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                os.fchmod(
                    handle.fileno(),
                    path.stat().st_mode & 0o777 if path.exists() else 0o644,
                )
        for temporary_path, path in staged:
            temporary_path.replace(path)
    finally:
        for temporary_path, _ in staged:
            temporary_path.unlink(missing_ok=True)


def _evidence_binding(source: dict[str, Any], key: str) -> dict[str, str]:
    matches = [row for row in source["evidence"] if row["key"] == key]
    if len(matches) != 1:
        raise RuntimeError(f"source evidence differs: {key}")
    row = matches[0]
    return {
        "evidence_id": v16.atlas_stable_id(
            "evidence", "curated-official", key, row["content_hash"]
        ),
        "key": key,
    }


def _required(
    rows: list[dict[str, str]], field: str, value: str
) -> dict[str, str] | None:
    matches = [row for row in rows if row[field] == value]
    if len(matches) > 1:
        raise RuntimeError(f"duplicate hydrated row: {field}={value}")
    return matches[0] if matches else None


def _capture_document(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    content_hash = result["content_hash"]
    result["evidence_id"] = v16.atlas_stable_id(
        "evidence",
        "verified-construction-core-v0.17",
        result["source_id"],
        content_hash,
    )
    if result["capture"] != {
        **result["capture"],
        "sha256": content_hash,
        "redistributed": False,
    }:
        raise RuntimeError(f"capture guardrail differs: {result['source_id']}")
    return result


def _lineage(
    *,
    project_key: str,
    campus_key: str,
    project_id: str,
    campus_id: str,
    status: dict[str, Any],
    location: dict[str, str],
    relationship: dict[str, str],
    pipeline_rows: list[dict[str, str]],
    entity_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    member_rows: list[dict[str, str]],
    relationship_rows: list[dict[str, str]],
) -> dict[str, Any]:
    pipeline = _required(pipeline_rows, "stable_key", project_key)
    project_entity = _required(entity_rows, "stable_key", project_key)
    campus_entity = _required(entity_rows, "stable_key", campus_key)
    project_member = _required(member_rows, "stable_key", project_key)
    campus_member = _required(member_rows, "stable_key", campus_key)
    topology = _required(
        relationship_rows, "relationship_id", relationship["relationship_id"]
    )
    if pipeline is not None:
        if pipeline != project_entity:
            raise RuntimeError(f"v97 project projection differs: {project_key}")
        status_evidence = _required(evidence_rows, "evidence_id", status["evidence_id"])
        if status_evidence is None:
            raise RuntimeError(f"v97 status evidence absent: {project_key}")
        v97_project: dict[str, Any] = {
            "entity_id": project_id,
            "presence": "pipeline",
            "row_sha256": _row_sha256(pipeline),
            "stable_key": project_key,
            "status": pipeline["status"],
            "status_as_of": pipeline["status_as_of"],
            "status_evidence_id": pipeline["status_evidence_id"],
        }
        v97_status_evidence: dict[str, Any] = {
            "content_hash": status_evidence["content_hash"],
            "evidence_id": status_evidence["evidence_id"],
            "presence": "required",
            "row_sha256": _row_sha256(status_evidence),
        }
    elif project_entity is not None:
        v97_project = {
            "entity_id": project_id,
            "presence": "entity_only",
            "row_sha256": _row_sha256(project_entity),
            "stable_key": project_key,
        }
        v97_status_evidence = {"presence": "not_applicable"}
    else:
        v97_project = {"presence": "absent", "stable_key": project_key}
        v97_status_evidence = {"presence": "absent"}
    v97_campus = (
        {
            "entity_id": campus_id,
            "presence": "required",
            "row_sha256": _row_sha256(campus_entity),
            "stable_key": campus_key,
        }
        if campus_entity is not None
        else {"presence": "absent", "stable_key": campus_key}
    )
    v14_project_member = (
        {
            "component_id": project_member["component_id"],
            "presence": "required",
            "row_sha256": _row_sha256(project_member),
        }
        if project_member is not None
        else {"presence": "absent"}
    )
    v14_campus_member = (
        {
            "component_id": campus_member["component_id"],
            "presence": "required",
            "row_sha256": _row_sha256(campus_member),
        }
        if campus_member is not None
        else {"presence": "absent"}
    )
    v14_topology = (
        {
            "presence": "required",
            "relationship_id": topology["relationship_id"],
            "row_sha256": _row_sha256(topology),
        }
        if topology is not None
        else {"presence": "absent"}
    )
    if relationship["origin"] == "v14" and topology is None:
        raise RuntimeError(f"v14 topology absent: {project_key}")
    if relationship["origin"] == "source_local" and topology is not None:
        raise RuntimeError(f"unexpected v14 topology: {project_key}")
    return {
        "current_status_lineage": {
            "classification": (
                "v97_exact_project_status"
                if pipeline is not None
                else "portable_post_v97_source_status"
            ),
            "evidence_id": status["evidence_id"],
        },
        "lineage_class": (
            "v97_project_status_and_v14_topology"
            if pipeline is not None
            else "portable_post_v97_project_and_source_local_topology"
        ),
        "location_evidence_lineage": {
            "classification": "portable_curated_source_location_identity",
            "evidence_id": location["evidence_id"],
        },
        "project_stable_key": project_key,
        "v14_campus_member": v14_campus_member,
        "v14_project_member": v14_project_member,
        "v14_topology": v14_topology,
        "v97_campus": v97_campus,
        "v97_project": v97_project,
        "v97_status_evidence": v97_status_evidence,
    }


def main() -> int:
    if len(RECORDS) != v17.V17_EXPECTED_DELTA_COUNT:
        raise RuntimeError("the reviewed v0.17 record inventory must contain 20 rows")
    pipeline_rows = _load_csv(v16.SOURCE_RELEASE / "construction_pipeline.csv")
    entity_rows = _load_csv(v16.SOURCE_RELEASE / "entities.csv")
    evidence_rows = _load_csv(v16.SOURCE_RELEASE / "evidence.csv")
    member_rows = _load_csv(IDENTITY_DIR / "component-members.csv")
    relationship_rows = _load_csv(IDENTITY_DIR / "relationships.csv")
    pipeline_by_key = {row["stable_key"]: row for row in pipeline_rows}
    member_by_key = {row["stable_key"]: row for row in member_rows}
    documents: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    acceptances: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    seen_campuses: set[str] = set()
    for spec in sorted(RECORDS, key=lambda row: row["source_path"]):
        source_path = ROOT / spec["source_path"]
        source = json.loads(source_path.read_text(encoding="utf-8"))
        project = source["project"]
        campus = source["campus"]
        project_key = project["stable_key"]
        campus_key = campus["stable_key"]
        if campus_key in seen_campuses:
            raise RuntimeError(f"duplicate physical site: {campus_key}")
        seen_campuses.add(campus_key)
        project_id = v16.atlas_stable_id("entity", project_key, "project")
        campus_id = v16.atlas_stable_id("entity", campus_key, "campus")
        source_sha256 = _sha256_file(source_path)
        status_key = spec["status_evidence_key"]
        lifecycle = [
            row
            for row in source["lifecycle"]
            if row["entity"] == "project" and row["evidence_key"] == status_key
        ]
        if len(lifecycle) != 1:
            raise RuntimeError(f"status observation differs: {project_key}")
        status = {
            **lifecycle[0],
            **_evidence_binding(source, status_key),
        }
        status["evidence_key"] = status.pop("key")
        location = _evidence_binding(
            source, spec.get("location_evidence_key", project["evidence_key"])
        )
        project_member = member_by_key.get(project_key)
        campus_member = member_by_key.get(campus_key)
        topology_matches = []
        if project_member is not None and campus_member is not None:
            topology_matches = [
                row
                for row in relationship_rows
                if row["relationship_type"] == "project_targets"
                and row["subject_component_id"] == project_member["component_id"]
                and row["object_component_id"] == campus_member["component_id"]
            ]
        if len(topology_matches) > 1:
            raise RuntimeError(f"ambiguous topology: {project_key}")
        relationship = {
            "decision_basis": "explicit_parent",
            "origin": "v14" if topology_matches else "source_local",
            "relationship_id": (
                topology_matches[0]["relationship_id"]
                if topology_matches
                else v17._source_local_relationship_id(
                    project_id, campus_id, source_sha256
                )
            ),
            "relationship_type": "project_targets",
        }
        document_ids = []
        for source_document in spec["source_documents"]:
            document = _capture_document(source_document)
            documents.append(document)
            document_ids.append(document["source_id"])
        geometry_document_ids = spec["geometry_source_document_ids"]
        identity_document_ids = spec.get("identity_source_document_ids", [])
        document_id_set = set(document_ids)
        if (
            not geometry_document_ids
            or len(document_ids) != len(document_id_set)
            or len(geometry_document_ids) != len(set(geometry_document_ids))
            or len(identity_document_ids) != len(set(identity_document_ids))
            or not set(geometry_document_ids) <= document_id_set
            or not set(identity_document_ids) <= document_id_set
            or set(geometry_document_ids) | set(identity_document_ids)
            != document_id_set
        ):
            raise RuntimeError(f"capture source roles differ: {project_key}")
        geometry = spec["geometry"]
        canonical = v16._json_bytes(geometry)[:-1]
        result = {
            "canonical_geometry": {
                "bytes_without_newline": len(canonical),
                "sha256_without_newline": hashlib.sha256(canonical).hexdigest(),
            },
            "display_anchor": spec["display_anchor"],
            "geometry": geometry,
            "geometry_source_document_id": geometry_document_ids[0],
            "geometry_source_document_ids": geometry_document_ids,
            "identity_source_document_ids": identity_document_ids,
            "locator_id": spec["locator_id"],
            "project_stable_key": project_key,
            "semantics": spec["semantics"],
        }
        results.append(result)
        acceptance = {
            "location_evidence": location,
            "locator_id": spec["locator_id"],
            "parent_campus_entity_id": campus_id,
            "parent_campus_stable_key": campus_key,
            "project_entity_id": project_id,
            "project_stable_key": project_key,
            "relationship": relationship,
            "scope_guardrail": spec["scope_guardrail"],
            "source_input": {
                "bytes": source_path.stat().st_size,
                "path": source_path.relative_to(ROOT).as_posix(),
                "sha256": source_sha256,
            },
            "status": status,
        }
        acceptances.append(acceptance)
        lineage_rows.append(
            _lineage(
                project_key=project_key,
                campus_key=campus_key,
                project_id=project_id,
                campus_id=campus_id,
                status=status,
                location=location,
                relationship=relationship,
                pipeline_rows=pipeline_rows,
                entity_rows=entity_rows,
                evidence_rows=evidence_rows,
                member_rows=member_rows,
                relationship_rows=relationship_rows,
            )
        )
    if len({row["source_id"] for row in documents}) != len(documents):
        raise RuntimeError("geometry source identifiers must be unique")
    capture = {
        "capture_id": "verified-construction-core-v0.17-100-site-geometry-facts",
        "captured_on": "2026-09-06",
        "cohort_lifecycle_reference_date": "2026-08-20",
        "results": sorted(results, key=lambda row: row["project_stable_key"]),
        "source_documents": sorted(documents, key=lambda row: row["source_id"]),
    }
    capture_bytes = _json_bytes(capture)
    capture_sha256 = hashlib.sha256(capture_bytes).hexdigest()
    base_report = json.loads(
        (v16.CURRENT_V16_PREVIEW_DIR / "selection-report.json").read_text(
            encoding="utf-8"
        )
    )
    base_accounting = base_report["source_selection_accounting"]
    base_projects = _load_csv(v16.CURRENT_V16_PREVIEW_DIR / "projects.csv")
    base_selected = {
        row["project_stable_key"]
        for row in base_projects
        if row["project_stable_key"] in pipeline_by_key
    }
    pipeline_promotions = sorted(
        (
            {
                "frozen_v16_first_failure": v16._first_failure(
                    dict(pipeline_by_key[row["project_stable_key"]]), base_selected
                ),
                "project_stable_key": row["project_stable_key"],
            }
            for row in acceptances
            if row["project_stable_key"] in pipeline_by_key
        ),
        key=lambda row: row["project_stable_key"],
    )
    selected = base_selected | {
        row["project_stable_key"] for row in pipeline_promotions
    }
    failures = Counter(base_accounting["resulting_v97_first_failure_counts"])
    for promotion in pipeline_promotions:
        failure = promotion["frozen_v16_first_failure"]
        if failure == "selected" or failures[failure] <= 0:
            raise RuntimeError("invalid frozen v0.16 promotion accounting")
        failures[failure] -= 1
        failures["selected"] += 1
    post_v97_keys = sorted(
        set(base_accounting["post_v97_selected_project_keys"])
        | {
            row["project_stable_key"]
            for row in acceptances
            if row["project_stable_key"] not in pipeline_by_key
        }
    )
    accounting = {
        "artifact_selected_projects": 103,
        "derivation": (
            "Start with the frozen v0.16 first-failure ledger; promote the 16 "
            "reviewed v97 projects enumerated below, then append four portable "
            "post-v97 projects while preserving the two post-v97 v0.16 projects."
        ),
        "frozen_v16_first_failure_counts": base_accounting[
            "resulting_v97_first_failure_counts"
        ],
        "frozen_v16_preview_id": v16.CURRENT_V16_PREVIEW_ID,
        "post_v97_selected_project_keys": post_v97_keys,
        "post_v97_selected_projects": len(post_v97_keys),
        "resulting_v97_first_failure_counts": dict(sorted(failures.items())),
        "v17_v97_promotions": pipeline_promotions,
        "v97_nonselected_source_rows": len(pipeline_rows) - len(selected),
        "v97_pipeline_rows": len(pipeline_rows),
        "v97_selected_projects": len(selected),
    }
    invariants = {
        "accepted_physical_site_count": len(acceptances),
        "accepted_project_count": len(acceptances),
        "geometry_authority_classes": dict(
            sorted(
                Counter(
                    row["semantics"]["geometry_authority_class"] for row in results
                ).items()
            )
        ),
        "geometry_types": dict(
            sorted(Counter(row["geometry"]["type"] for row in results).items())
        ),
        "geometry_use_scopes": dict(
            sorted(
                Counter(
                    row["semantics"]["geometry_use_scope"] for row in results
                ).items()
            )
        ),
        "independent_imagery_verification": False,
        "numeric_horizontal_uncertainty_rows": sum(
            row["semantics"]["horizontal_uncertainty_metres"] is not None
            for row in results
        ),
        "official_boundary": False,
        "raw_source_artifacts_redistributed": False,
    }
    v16_contract = json.loads(V16_CONTRACT_PATH.read_text(encoding="utf-8"))
    contract = {
        "acceptances": sorted(acceptances, key=lambda row: row["project_stable_key"]),
        "base_preview": {
            "commit": v17.LEGACY_PREVIEW_V16_COMMIT,
            "manifest_sha256": v17.LEGACY_PREVIEW_V16_MANIFEST_SHA256,
            "path": v16.CURRENT_V16_PREVIEW_DIR.relative_to(ROOT).as_posix(),
            "preview_id": v16.CURRENT_V16_PREVIEW_ID,
        },
        "batch_invariants": invariants,
        "cohort_lifecycle_reference_date": "2026-08-20",
        "contract_id": "verified-construction-core-v0.17-100-site-batch",
        "geometry_capture": {
            "bytes": len(capture_bytes),
            "capture_id": capture["capture_id"],
            "evidence_document_count": len(documents),
            "geometry_record_count": len(results),
            "path": CAPTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": capture_sha256,
        },
        "hydrated_crosscheck_inputs": v16_contract["hydrated_crosscheck_inputs"],
        "rejected_claims": [
            "official_boundary",
            "building_or_construction_footprint",
            "map_or_imagery_derived_lifecycle",
            "capacity_or_energy_inference",
            "role_or_workload_inference",
            "commissioning_completion_or_operation_without_selected_evidence",
        ],
        "review_scope": (
            "Twenty distinct physical-site additions needed to advance the frozen "
            "v0.16 artifact from 80 to 100 sites while reaching 40 countries."
        ),
        "reviewed_as_of": "2026-09-06",
        "schema_version": "1.0",
        "source_lineage": sorted(
            lineage_rows, key=lambda row: row["project_stable_key"]
        ),
        "source_selection_accounting": accounting,
    }
    contract_bytes = _json_bytes(contract)
    _replace_payloads(((CAPTURE_PATH, capture_bytes), (CONTRACT_PATH, contract_bytes)))
    print(
        json.dumps(
            {
                "capture": {
                    "bytes": CAPTURE_PATH.stat().st_size,
                    "sha256": _sha256_file(CAPTURE_PATH),
                },
                "contract": {
                    "bytes": CONTRACT_PATH.stat().st_size,
                    "sha256": _sha256_file(CONTRACT_PATH),
                },
                "invariants": invariants,
                "source_selection_accounting": accounting,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
