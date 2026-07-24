from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "sources"
ARTIFACT_ID = "authoritative-coordinate-successors-v64-2026-07-20-v1"
ARTIFACT_DIR = ROOT / "source_artifacts" / ARTIFACT_ID
AS_OF_DATE = "2026-07-20"

V64_DEFINITION = {
    "path": "sources/open-seed-2026-07-20-v64.json",
    "bytes": 79_698,
    "sha256": "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e",
}

DENVER_PARCEL_URL = (
    "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
    "ODC_PROP_PARCELS_A/FeatureServer/245/query?where=SITUS_ADDRESS_ID%3D23973%20"
    "AND%20SCHEDNUM%3D%270214400131000%27&outFields=OBJECTID%2CSCHEDNUM%2C"
    "SITUS_ADDRESS_ID%2CSITUS_ADDRESS_LINE1%2CSITUS_CITY%2CSITUS_STATE%2C"
    "SITUS_ZIP%2COWNER_NAME%2CPARCELNUM&returnGeometry=true&returnCentroid=true&"
    "outSR=4326&f=json"
)
DENVER_RIGHTS_URL = (
    "https://www.denvergov.org/Government/Agencies-Departments-Offices/"
    "Agencies-Departments-Offices-Directory/Technology-Services/Functions/GIS"
)
IRVING_PERMIT_URL = (
    "https://services3.arcgis.com/OfsJXUlu8pSkbl7B/arcgis/rest/services/"
    "Planning_and_Zoning/FeatureServer/0/query?where=Permit%3D%272025-02-1125%27&"
    "outFields=OBJECTID%2CPermit%2CValue%2CArea_SF%2CStNum%2CStDir%2CStName%2C"
    "Project%2CApplied%2CApproved%2CIssued%2CFinaled%2CCO_Date%2CStatus%2CGlobalID&"
    "returnGeometry=true&outSR=4326&f=geojson"
)
IRVING_ADDRESS_URL = (
    "https://services3.arcgis.com/OfsJXUlu8pSkbl7B/ArcGIS/rest/services/"
    "SiteAddressPoints/FeatureServer/0/query?where=SITEADDID%3D%274324801%27%20AND%20"
    "ADDPTKEY%3D%274324801%27&outFields=OBJECTID%2CSITEADDID%2CADDPTKEY%2CFULLADDR%2C"
    "GlobalID&returnGeometry=true&outSR=4326&f=geojson"
)
IRVING_POLICY_URL = (
    "https://cityofirving.org/DocumentCenter/View/29730/Online-Open-Data-PolicySMDraft"
)
AURORA_ADDRESS_URL = (
    "https://services1.arcgis.com/79UxTxnBeBW8JHY4/arcgis/rest/services/"
    "Address_Points/FeatureServer/0/query?where=LOCATIONID%3D85050%20AND%20"
    "PIN%3D%2707-05-105-006%27&outFields=OBJECTID%2CLOCATIONID%2CPIN%2CADDRESS%2C"
    "CITY%2CZIPCODE%2CCOUNTY%2CZONING%2CLANDUSE%2COWNERNAME&returnGeometry=true&"
    "outSR=4326&f=geojson"
)
AURORA_RIGHTS_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/"
    "dda7cad7bcb840cebea77eae26ec6aa5?f=json"
)
GA_EPD_ADVISORY_URL = (
    "https://epd.georgia.gov/document/document/pa0326-4/download"
)
GA_EPD_DRAFT_URL = (
    "https://epd.georgia.gov/document/document/29951-draft/download"
)
WHITFIELD_ADDRESS_URL = (
    "https://gis.whitfieldcountyga.com/server/rest/services/Addressing_Points/"
    "MapServer/0/query?where=OBJECTID%3D226055%20AND%20HNUM%3D1199%20AND%20"
    "UPPER%28STREET%29%3D%27ENTERPRISE%20DR%27&outFields=OBJECTID%2CHNUM%2C"
    "STREET%2CFULL_ADDRE%2CLOCATION%2CCOMMUNITY%2CSTRUCTURE%2CMUNI%2CCity&"
    "returnGeometry=true&outSR=4326&f=geojson"
)
WHITFIELD_DISCLAIMER_URL = (
    "https://gis.whitfieldcountyga.com/GIS/disclaimer.html"
)

DENVER_RING = [
    [-104.963184722902, 39.7856242412933],
    [-104.963179734656, 39.7863032468357],
    [-104.963175995665, 39.7863414056315],
    [-104.963165423572, 39.7863787939894],
    [-104.963165323691, 39.7863790313089],
    [-104.963154106409, 39.7864175160577],
    [-104.963150145341, 39.7864568432731],
    [-104.963148623641, 39.7866638850603],
    [-104.963146455246, 39.78667993711],
    [-104.963140269725, 39.7866953544454],
    [-104.963130304737, 39.7867095446967],
    [-104.96311694316, 39.7867219626412],
    [-104.963100698373, 39.786732131152],
    [-104.963082194541, 39.7867396595307],
    [-104.963062142623, 39.786744258519],
    [-104.963041313063, 39.7867457514126],
    [-104.962568186015, 39.7867436812468],
    [-104.962568367245, 39.7867189814144],
    [-104.962547023802, 39.7867188876023],
    [-104.962547810723, 39.7866118546995],
    [-104.962435362935, 39.7866113621219],
    [-104.96241771334, 39.786609972382],
    [-104.962400732488, 39.7866060081017],
    [-104.962391708499, 39.7866018525524],
    [-104.962384652022, 39.786595844242],
    [-104.962380178868, 39.7865885075093],
    [-104.962378679404, 39.7865804826228],
    [-104.962378915748, 39.786548454352],
    [-104.962376287447, 39.7865379453045],
    [-104.962368649095, 39.7865290108154],
    [-104.962359545114, 39.7865219062551],
    [-104.962362761218, 39.7860851537574],
    [-104.962382326547, 39.7860852394855],
    [-104.962382528891, 39.786057795425],
    [-104.96236296357, 39.7860577096969],
    [-104.962366600434, 39.7855638174078],
    [-104.96238581252, 39.7855390132134],
    [-104.962411330955, 39.7855178626754],
    [-104.962475432584, 39.7855181418025],
    [-104.96247563688, 39.7854902861421],
    [-104.962502046009, 39.7854856685812],
    [-104.962529057635, 39.7854841974335],
    [-104.963007903308, 39.7854862929751],
    [-104.96304255837, 39.7854890736954],
    [-104.963075845586, 39.7854970140258],
    [-104.963106487262, 39.7855098091853],
    [-104.96313330725, 39.7855269680459],
    [-104.963155276089, 39.7855478319825],
    [-104.963171550524, 39.7855716001546],
    [-104.96318150587, 39.7855973602445],
    [-104.963184759994, 39.7856241234756],
    [-104.963184759663, 39.7856241667059],
    [-104.963184722902, 39.7856242412933],
]

DENVER_POINT = {"latitude": 39.7861942431606, "longitude": -104.96277124667975}
IRVING_POINT = {"latitude": 32.888545840931, "longitude": -96.9410613460374}
AURORA_POINT = {"latitude": 41.806967678, "longitude": -88.240996871}
WHITFIELD_POINT = {
    "latitude": 34.6948095438794,
    "longitude": -84.941093728219,
}

PREDECESSORS = {
    "coresite": {
        "path": "curated-official-2026-07-20-coresite-de3-denver.json",
        "bytes": 35_669,
        "sha256": "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868",
        "successor": "curated-official-2026-07-20-coresite-de3-denver-v2.json",
    },
    "powerhouse": {
        "path": "curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
        "bytes": 21_449,
        "sha256": "03e3c1de817fba2a0b14d42ec5d063caf07ac23df4083b22bd0a99f6803d0990",
        "successor": (
            "curated-official-2026-07-20-powerhouse-irving-building-1-topout-v2.json"
        ),
    },
    "edged": {
        "path": "curated-official-2026-07-20-edged-ord01-2-chicago-topout.json",
        "bytes": 17_750,
        "sha256": "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
        "successor": "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v3.json",
    },
    "dalton4": {
        "path": "curated-official-2026-07-20-core-scientific-dalton-4.json",
        "bytes": 19_614,
        "sha256": "ed121928047032b1740d7f6e30faa0fad7304cb6b5144c1b708812300ebe9a09",
        "successor": "curated-official-2026-07-20-core-scientific-dalton-4-v2.json",
    },
}

REJECTED_EDGED_V2 = {
    "path": "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
    "bytes": 21_279,
    "sha256": "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368",
    "disposition": "rejected_nonpromotion_google_maps_derived_coordinate",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(document: Any) -> bytes:
    return (
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"refusing to overwrite non-identical file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _load_predecessor(label: str) -> dict[str, Any]:
    spec = PREDECESSORS[label]
    path = SOURCE_DIR / spec["path"]
    raw = path.read_bytes()
    if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
        raise RuntimeError(f"predecessor pin mismatch: {path}")
    return json.loads(raw)


def _capture_metadata(
    *,
    body_bytes: int,
    body_sha256: str,
    header_bytes: int,
    header_sha256: str,
    curl_bytes: int,
    curl_sha256: str,
    retrieved_at: str,
    http_version: str,
    content_type: str,
    content_encoding: str | None,
    size_download: int,
    header_count: int,
    url: str,
) -> dict[str, Any]:
    return {
        "content_hash_scope": (
            f"SHA-256 of the exact {body_bytes}-byte content-decoded official "
            "response body captured with curl --compressed"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture"
        ),
        "capture_headers_sha256": header_sha256,
        "capture_curl_writeout_scope": (
            f"SHA-256 of the exact {curl_bytes}-byte newline-terminated full curl "
            "%{json} effective-response facts capture"
        ),
        "capture_curl_writeout_sha256": curl_sha256,
        "capture_completed_at": retrieved_at,
        "capture_artifact_guardrail": (
            "The response body, raw headers, and full curl facts were temporary "
            "verification artifacts and are not redistributed. Only exact byte counts, "
            "hashes, safe response facts, and compact factual extraction are retained."
        ),
        "request_metadata_guardrail": (
            "No credentials, Authorization, Proxy-Authorization, authentication option, "
            "cookie input, cookie jar, client certificate, or proxy credential was "
            "supplied. Server-set cookies were not persisted or reused; endpoint and TLS "
            "telemetry are not copied into this record."
        ),
        "retrieval_method": (
            "One credential-free curl --fail --location --compressed GET with a "
            "five-redirect bound, retries disabled, and separate exact response-body, "
            "raw-header, and full effective-response-facts captures."
        ),
        "http_status": 200,
        "curl_exit_code": 0,
        "http_version_as_received": http_version,
        "content_type": content_type,
        "content_encoding_as_received": content_encoding,
        "curl_size_download_bytes_as_received": size_download,
        "curl_size_header_bytes": header_bytes,
        "curl_num_headers": header_count,
        "requested_url": url,
        "effective_url": url,
        "response_header_blocks": 1,
        "redirect_count": 0,
        "retrieved_at_semantics": (
            "The evidence retrieved_at equals the exact response HTTP Date. The UTC date "
            "is July 21 while the America/Los_Angeles local research date and all source, "
            "evidence-key, as-of, and artifact identifiers remain July 20."
        ),
        "rights_scope": (
            "Compact factual extraction only; captured response bytes, response headers, "
            "full curl telemetry, PDFs, and GIS payloads are not redistributed."
        ),
        "request_method": "GET",
        "captured_body_bytes": body_bytes,
        "captured_body_sha256": body_sha256,
    }


def _evidence_records() -> dict[str, list[dict[str, Any]]]:
    denver_metadata = _capture_metadata(
        body_bytes=3_919,
        body_sha256="41387d3d2d09af9e88e494d24f29ccc6897f25b0b077edf5f9011a470de0c7e2",
        header_bytes=1_118,
        header_sha256="fcc46caa6d9c1693f648395d3a81be9cfb7d1489521c64475a78eb372db2f719",
        curl_bytes=12_647,
        curl_sha256="073fc0fd71d0c126f6ed1cc9bbde919f3cce4d3a6c501e4a659f6b3367e2bed9",
        retrieved_at="2026-07-21T06:33:52Z",
        http_version="HTTP/2",
        content_type="application/json; charset=utf-8",
        content_encoding="gzip",
        size_download=1_327,
        header_count=26,
        url=DENVER_PARCEL_URL,
    )
    denver_metadata.update(
        {
            "query_predicate": (
                "SITUS_ADDRESS_ID=23973 AND SCHEDNUM='0214400131000'"
            ),
            "query_out_fields": [
                "OBJECTID",
                "SCHEDNUM",
                "SITUS_ADDRESS_ID",
                "SITUS_ADDRESS_LINE1",
                "SITUS_CITY",
                "SITUS_STATE",
                "SITUS_ZIP",
                "OWNER_NAME",
                "PARCELNUM",
            ],
            "query_return_geometry": True,
            "query_return_centroid": True,
            "query_output_crs": "EPSG:4326",
            "returned_feature_count": 1,
            "returned_object_id": 1_231_023,
            "returned_schedule_number": "0214400131000",
            "returned_situs_address_id": 23_973,
            "returned_situs_address": "4900 N RACE ST, DENVER, CO 80216-2242",
            "returned_owner_name": "CORESITE REAL ESTATE DE3 LLC",
            "returned_parcel_number": "131",
            "returned_geometry_type": "Polygon",
            "returned_ring_count": 1,
            "returned_position_count": 53,
            "raw_esri_geometry_canonical_sha256": (
                "7f59d73280de0e969591732643a31b4df5848cdedd1e30c5c1a43d964c1875ce"
            ),
            "stored_geojson_geometry_canonical_sha256": (
                "7dfc83d83c26a99cb935a0022e2310a3249d02db2a7737675050936072d84914"
            ),
            "geometry_label": "de3_tax_parcel_boundary",
            "geometry_scope": (
                "Exact WGS84 Denver tax-parcel boundary for schedule number "
                "0214400131000, whose returned owner is CORESITE REAL ESTATE DE3 LLC. "
                "It is evidence-scoped tax-parcel geometry, not a building footprint, "
                "construction limit, or imagery-derived outline."
            ),
            "topology_validation": {
                "library": "Shapely 2.1.2",
                "geos": "3.13.1",
                "is_valid": True,
                "validity_reason": "Valid Geometry",
                "is_simple": True,
                "ring_closed": True,
                "area_square_degrees": 9.804961291450332e-07,
            },
            "representative_point_method": (
                "Shapely 2.1.2 representative_point using GEOS 3.13.1 on the exact "
                "returned polygon; the deterministic point is strictly within the valid "
                "polygon."
            ),
            "representative_point": DENVER_POINT,
            "returned_server_centroid": {
                "latitude": 39.78609961134673,
                "longitude": -104.96277589662026,
            },
            "sliver_exclusion_guardrail": (
                "The exact stable-ID predicate returned one CoreSite-owned parcel. "
                "Nearby city-owned approximate slivers were neither queried into the "
                "result nor unioned, transferred, interpolated, or drawn."
            ),
            "coordinate_scope": (
                "The same representative point and exact DE3 tax parcel are attached to "
                "the campus and project snapshots because both selected entities denote "
                "DE3 at 4900 Race Street; neither snapshot treats the parcel as a DE3 "
                "building footprint."
            ),
            "license_reference_url": DENVER_RIGHTS_URL,
            "license_reference_body_bytes": 158_115,
            "license_reference_body_sha256": (
                "dd38845675c959b61e56f6e58e1bf7c967e6279793d7561d7d40af010a442d13"
            ),
            "license_reference_statement": (
                "Denver states that catalog data may be copied, distributed, transmitted, "
                "and adapted under Creative Commons Attribution 3.0."
            ),
            "imagery_guardrail": (
                "Satellite imagery, aerial imagery, maps, computer vision, and map clicks "
                "contributed nothing to the identity, coordinates, or geometry."
            ),
        }
    )

    irving_permit_metadata = _capture_metadata(
        body_bytes=582,
        body_sha256="c01d04e1303c2c66df6449656f0cc102d487bcb9c5564b58d8a3ddce405ebb0d",
        header_bytes=1_156,
        header_sha256="f6ca4dcc3a222ac6cf54ae068aaa422e9d7dc0458ff2de06147669d4a0873d6e",
        curl_bytes=12_494,
        curl_sha256="5cf75c3fe508367bd69ad5b3973847b8d56281a2eee880e1ac54e4991797853c",
        retrieved_at="2026-07-21T06:33:53Z",
        http_version="HTTP/2",
        content_type="application/json; charset=utf-8",
        content_encoding="gzip",
        size_download=412,
        header_count=27,
        url=IRVING_PERMIT_URL,
    )
    irving_permit_metadata.update(
        {
            "query_predicate": "Permit='2025-02-1125'",
            "query_return_geometry": True,
            "query_output_crs": "EPSG:4326",
            "returned_feature_count": 1,
            "returned_object_id": 658,
            "returned_global_id": "2581c8c2-7038-463b-b2e4-f6df2b86cd2f",
            "returned_permit": "2025-02-1125",
            "returned_address": "111 CUSTOMER WAY",
            "returned_project": "AREP POWERHOUSE LAS COLINAS (SHELL DATA WHSE)",
            "returned_status": "UNDER CONSTRUCTION",
            "returned_geometry_type": "Point",
            "returned_geometry": IRVING_POINT,
            "coordinate_reference_system": "EPSG:4326",
            "coordinate_scopes": {
                "campus": "official_site_address_point",
                "project": "official_permit_project_address_point",
            },
            "coordinate_scope": (
                "The City permit point directly identifies permit 2025-02-1125, 111 "
                "Customer Way, and the PowerHouse Las Colinas shell data-warehouse "
                "project. It is a permit/address point, not a parcel, campus boundary, "
                "building centroid, footprint, or construction limit."
            ),
            "status_nonpromotion_guardrail": (
                "The returned UNDER CONSTRUCTION permit text is retained as coordinate-"
                "evidence metadata only. It creates no lifecycle observation and does not "
                "replace, update, or reinterpret the selected source's frozen shell "
                "observation dated 2026-03-27."
            ),
            "license_reference_url": IRVING_POLICY_URL,
            "license_reference_statement": (
                "The City of Irving open-data policy places published datasets in the "
                "public domain without restrictions or requirements on use."
            ),
            "license_capture_guardrail": (
                "The legacy cityofirving.org policy URL had a certificate-hostname "
                "mismatch and its current irvingtx.gov migration target presented a "
                "Cloudflare challenge during this run. No policy response body or hash is "
                "invented; the exact policy URL remains a reference only."
            ),
            "imagery_guardrail": (
                "Satellite imagery, aerial imagery, maps, computer vision, and map clicks "
                "contributed nothing to the identity or point."
            ),
        }
    )

    irving_address_metadata = _capture_metadata(
        body_bytes=359,
        body_sha256="5713981c26c61f9571361e35e0f29461eaa51d8e60a75df9f6999c056540d10e",
        header_bytes=1_154,
        header_sha256="4899f9534a5aa56d52a223349c22aedb194cc2ff60cc9f9bf6b9402cc65c23f1",
        curl_bytes=12_262,
        curl_sha256="b0891c68596c96502af832e7adb9a391deae389707e109ad705ca7a0d7aa0448",
        retrieved_at="2026-07-21T06:33:53Z",
        http_version="HTTP/2",
        content_type="application/json; charset=utf-8",
        content_encoding="gzip",
        size_download=264,
        header_count=27,
        url=IRVING_ADDRESS_URL,
    )
    irving_address_metadata.update(
        {
            "query_predicate": (
                "SITEADDID='4324801' AND ADDPTKEY='4324801'"
            ),
            "query_return_geometry": True,
            "query_output_crs": "EPSG:4326",
            "returned_feature_count": 1,
            "returned_object_id": 5_827,
            "returned_site_address_id": "4324801",
            "returned_address_point_key": "4324801",
            "returned_global_id": "83f2443b-497e-4142-849c-3a1e1a547840",
            "returned_full_address": "111 CUSTOMER WAY",
            "returned_geometry_type": "Point",
            "returned_geometry": {
                "latitude": 32.8885458409312,
                "longitude": -96.9410613460371,
            },
            "coordinate_reference_system": "EPSG:4326",
            "corroboration_scope": (
                "The independent City site-address layer returns the same 111 Customer "
                "Way location to sub-nanodegree precision and corroborates the permit "
                "point. The normalized snapshots retain the permit geometry rather than "
                "averaging, interpolating, or substituting the corroborating point."
            ),
            "geometry_guardrail": (
                "This is an official address point, not a parcel, campus boundary, "
                "building centroid, building footprint, or construction limit."
            ),
            "license_reference_url": IRVING_POLICY_URL,
        }
    )

    aurora_metadata = _capture_metadata(
        body_bytes=426,
        body_sha256="8db6b8217609665b4b58ab8ade5e5bb0a252321f056a1e80d6203533d837a84a",
        header_bytes=1_158,
        header_sha256="d0783cf4a5ffb9a72bd129abd417b09c5377e2f9a5f676b168de11ce6e489324",
        curl_bytes=12_390,
        curl_sha256="d375bc28d8a41fc4584528e22b1429014b3f53920186a614f2c30dcf1a6463a1",
        retrieved_at="2026-07-21T06:33:55Z",
        http_version="HTTP/2",
        content_type="application/json; charset=utf-8",
        content_encoding="gzip",
        size_download=309,
        header_count=27,
        url=AURORA_ADDRESS_URL,
    )
    aurora_metadata.update(
        {
            "query_predicate": (
                "LOCATIONID=85050 AND PIN='07-05-105-006'"
            ),
            "query_return_geometry": True,
            "query_output_crs": "EPSG:4326",
            "returned_feature_count": 1,
            "returned_object_id": 166_456_816,
            "returned_location_id": 85_050,
            "returned_pin": "07-05-105-006",
            "returned_address": "2835 BILTER RD, AURORA, IL 60502",
            "returned_county": "DUPAGE",
            "returned_owner_name": "EDGED CHICAGO LLC",
            "returned_geometry_type": "Point",
            "returned_geometry": AURORA_POINT,
            "returned_geometry_decimal_text": {
                "x": "-88.2409968709999",
                "y": "41.806967678",
            },
            "coordinate_reference_system": "EPSG:4326",
            "geometry_scope": "campus_address_point",
            "coordinate_scope": (
                "Exact City of Aurora address point for 2835 Bilter Road on PIN "
                "07-05-105-006, whose returned owner is EDGED CHICAGO LLC. The same "
                "campus-address point is attached to both snapshots to keep the project "
                "locatable, but the project point is inherited site location and is not "
                "an ORD01-2 building centroid, footprint, parcel, or construction limit."
            ),
            "license_reference_url": AURORA_RIGHTS_URL,
            "license_reference_body_bytes": 2_080,
            "license_reference_body_sha256": (
                "172afdc84cbd96063c3bb410889ae69889d05e4fab2a84f23f1ab1783ce1a347"
            ),
            "license_reference_statement": (
                "The City of Aurora Open Data Disclaimer states that City Data Analytics "
                "information is in the public domain and may be copied without permission; "
                "source citation is appreciated."
            ),
            "excluded_source_guardrail": (
                "The pre-existing Google Maps-derived v2 is rejected and unselected. "
                "Neither Google Maps nor Kane County/Sidwell contributes to this successor."
            ),
            "status_nonpromotion_guardrail": (
                "This coordinate addition creates no lifecycle row and preserves the "
                "selected source's shell observation dated 2026-06-04 exactly."
            ),
            "imagery_guardrail": (
                "Satellite imagery, aerial imagery, maps, computer vision, and map clicks "
                "contributed nothing to the identity or point."
            ),
        }
    )

    epd_metadata = _capture_metadata(
        body_bytes=104_495,
        body_sha256="2f292f0c5b03dedfcd3beaba324875f247b487bbe2a5267d82b30888b5bd49a9",
        header_bytes=1_027,
        header_sha256="5ff944aafe8d704a4c9a42bf4fc9e03d46117f193d4040b3d8886d198c792c9f",
        curl_bytes=9_566,
        curl_sha256="9434c4c85424a86dca8ae1fc0eb91c7bae7a360fe6138e65a94190a6001f651d",
        retrieved_at="2026-07-21T06:35:08Z",
        http_version="HTTP/2",
        content_type="application/pdf",
        content_encoding=None,
        size_download=104_495,
        header_count=24,
        url=GA_EPD_ADVISORY_URL,
    )
    epd_metadata.update(
        {
            "reported_facility_name": "Core Scientific-Dalton 4 Enterprise Drive",
            "reported_application_number": 29_951,
            "reported_facility_address": "Old Tilton Road, Dalton, 30721",
            "reported_operation": (
                "Computer Processing and Data Preparation and Processing Services"
            ),
            "identity_bridge_scope": (
                "The live Georgia EPD advisory binds Core Scientific, Dalton 4, "
                "Enterprise Drive, application 29951, Old Tilton Road, and a new data "
                "center. It does not by itself supply a coordinate or replace the "
                "publisher-reported canonical 3024 Old Tilton Road address."
            ),
            "draft_permit_retrieval_incident_id": "ga_epd_draft_unpublished",
            "draft_permit_guardrail": (
                "The exact draft-permit URL redirected to an unpublished route and "
                "returned HTTP 403 during this run. That failed response is retained only "
                "as a technical incident in the hash-only inventory, never as evidence or "
                "a fabricated PDF body hash."
            ),
            "status_guardrail": (
                "A proposed air permit and generator description are not a physical "
                "construction-status update. This record creates no lifecycle, capacity, "
                "energy, workload, role, or operating-model observation."
            ),
        }
    )

    whitfield_metadata = _capture_metadata(
        body_bytes=346,
        body_sha256="add0b6ce576afa5b0de6e6a23ee7990d64ae19b805414106b938baefdfd3f5a9",
        header_bytes=559,
        header_sha256="77067c16e7b014d8da445cbf65cee6913977b42385a2ecaf6d4db454825e2963",
        curl_bytes=16_034,
        curl_sha256="c35e5f9da8da6d5ea5d225ad82c960c96b82433e46b9771cd195334211b73cf5",
        retrieved_at="2026-07-21T06:33:56Z",
        http_version="HTTP/2",
        content_type="application/geo+json; charset=UTF-8",
        content_encoding="gzip",
        size_download=263,
        header_count=12,
        url=WHITFIELD_ADDRESS_URL,
    )
    whitfield_metadata.update(
        {
            "query_predicate": (
                "OBJECTID=226055 AND HNUM=1199 AND UPPER(STREET)='ENTERPRISE DR'"
            ),
            "query_return_geometry": True,
            "query_output_crs": "EPSG:4326",
            "returned_feature_count": 1,
            "returned_object_id": 226_055,
            "returned_house_number": 1_199,
            "returned_street": "ENTERPRISE DR",
            "returned_full_address": "1199 ENTERPRISE DR",
            "returned_structure": "COMMERCIAL",
            "returned_geometry_type": "Point",
            "returned_geometry": WHITFIELD_POINT,
            "returned_geometry_decimal_text": {
                "x": "-84.941093728218959",
                "y": "34.694809543879366",
            },
            "coordinate_reference_system": "EPSG:4326",
            "canonical_address": (
                "3024 Old Tilton Road, Dalton, Georgia, United States"
            ),
            "official_address_alias": (
                "1199 Enterprise Drive, Dalton, Georgia 30721, United States"
            ),
            "address_alias_scope": (
                "The selected Core Scientific filing address remains canonical and "
                "unchanged. The EPD application-29951 identity bridge and exact Whitfield "
                "911 point support 1199 Enterprise Drive only as an official address alias "
                "for the same Dalton 4 project."
            ),
            "coordinate_scope": (
                "Exact official Whitfield County 911 commercial address point for 1199 "
                "Enterprise Drive, attached to both Dalton 4 snapshots after the EPD "
                "identity bridge. It is an address point, not a parcel, parcel union, "
                "building centroid, footprint, or construction limit."
            ),
            "license": "no_affirmative_open_license_found",
            "license_reference_url": WHITFIELD_DISCLAIMER_URL,
            "license_reference_body_bytes": 3_442,
            "license_reference_body_sha256": (
                "c562307d57768eef89836eb22c7f19a572b8d2bbb2781da898f45b6d5a810fef"
            ),
            "redistribution_guardrail": (
                "Whitfield County's disclaimer provides no affirmative open license. The "
                "raw GIS response is not redistributed; only compact facts and exact "
                "capture hashes are retained."
            ),
            "status_nonpromotion_guardrail": (
                "The address point and EPD advisory create no lifecycle row and preserve "
                "the selected source's under_construction observation dated 2026-05-06 "
                "exactly."
            ),
            "imagery_guardrail": (
                "Satellite imagery, aerial imagery, maps, computer vision, and map clicks "
                "contributed nothing to the identity or point."
            ),
        }
    )

    return {
        "coresite": [
            {
                "key": "denver-coresite-de3-tax-parcel-captured-2026-07-20",
                "kind": "government_record",
                "title": "Denver tax parcel 0214400131000 at 4900 North Race Street",
                "source_url": DENVER_PARCEL_URL,
                "publisher": "City and County of Denver",
                "source_family": "denver_open_data_property_parcels",
                "published_at": None,
                "retrieved_at": "2026-07-21T06:33:52Z",
                "license": "CC-BY-3.0",
                "attribution": "City and County of Denver",
                "excerpt": (
                    "The exact Denver parcel query returns one WGS84 polygon, OBJECTID "
                    "1231023, schedule number 0214400131000, situs-address ID 23973 at "
                    "4900 North Race Street, owned by CORESITE REAL ESTATE DE3 LLC."
                ),
                "content_hash": (
                    "41387d3d2d09af9e88e494d24f29ccc6897f25b0b077edf5f9011a470de0c7e2"
                ),
                "metadata": denver_metadata,
            }
        ],
        "powerhouse": [
            {
                "key": "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20",
                "kind": "government_record",
                "title": (
                    "City of Irving permit 2025-02-1125 at 111 Customer Way"
                ),
                "source_url": IRVING_PERMIT_URL,
                "publisher": "City of Irving",
                "source_family": "irving_planning_and_zoning_open_data",
                "published_at": None,
                "retrieved_at": "2026-07-21T06:33:53Z",
                "license": "public-domain",
                "attribution": "City of Irving",
                "excerpt": (
                    "The exact permit query returns one point for permit 2025-02-1125, "
                    "OBJECTID 658 and GlobalID 2581c8c2-7038-463b-b2e4-f6df2b86cd2f, "
                    "at 111 Customer Way for the PowerHouse Las Colinas shell project."
                ),
                "content_hash": (
                    "c01d04e1303c2c66df6449656f0cc102d487bcb9c5564b58d8a3ddce405ebb0d"
                ),
                "metadata": irving_permit_metadata,
            },
            {
                "key": "irving-site-address-4324801-captured-2026-07-20",
                "kind": "government_record",
                "title": "City of Irving site-address point 4324801",
                "source_url": IRVING_ADDRESS_URL,
                "publisher": "City of Irving",
                "source_family": "irving_site_address_points",
                "published_at": None,
                "retrieved_at": "2026-07-21T06:33:53Z",
                "license": "public-domain",
                "attribution": "City of Irving",
                "excerpt": (
                    "The exact SiteAddressPoints query returns one point, OBJECTID 5827, "
                    "with SITEADDID and ADDPTKEY both 4324801 and FULLADDR 111 CUSTOMER WAY."
                ),
                "content_hash": (
                    "5713981c26c61f9571361e35e0f29461eaa51d8e60a75df9f6999c056540d10e"
                ),
                "metadata": irving_address_metadata,
            },
        ],
        "edged": [
            {
                "key": "aurora-edged-chicago-address-point-85050-captured-2026-07-20",
                "kind": "government_record",
                "title": "City of Aurora address point 85050 at 2835 Bilter Road",
                "source_url": AURORA_ADDRESS_URL,
                "publisher": "City of Aurora",
                "source_family": "aurora_open_data_address_points",
                "published_at": None,
                "retrieved_at": "2026-07-21T06:33:55Z",
                "license": "public-domain",
                "attribution": "City of Aurora GIS",
                "excerpt": (
                    "The exact City of Aurora query returns one point, OBJECTID "
                    "166456816 and LOCATIONID 85050, for 2835 Bilter Road on PIN "
                    "07-05-105-006, owned by EDGED CHICAGO LLC."
                ),
                "content_hash": (
                    "8db6b8217609665b4b58ab8ade5e5bb0a252321f056a1e80d6203533d837a84a"
                ),
                "metadata": aurora_metadata,
            }
        ],
        "dalton4": [
            {
                "key": "ga-epd-dalton4-application-29951-advisory-captured-2026-07-20",
                "kind": "government_record",
                "title": "Georgia EPD public advisory for application 29951",
                "source_url": GA_EPD_ADVISORY_URL,
                "publisher": "Georgia Environmental Protection Division",
                "source_family": "georgia_epd_air_permit_advisories",
                "published_at": "2026-03-25",
                "retrieved_at": "2026-07-21T06:35:08Z",
                "license": "all-rights-reserved",
                "attribution": "Georgia Environmental Protection Division",
                "excerpt": (
                    "The advisory identifies Core Scientific-Dalton 4 Enterprise Drive, "
                    "application 29951, Old Tilton Road in Dalton, and a proposed new data "
                    "center with emergency generators."
                ),
                "content_hash": (
                    "2f292f0c5b03dedfcd3beaba324875f247b487bbe2a5267d82b30888b5bd49a9"
                ),
                "metadata": epd_metadata,
            },
            {
                "key": "whitfield-1199-enterprise-address-point-captured-2026-07-20",
                "kind": "government_record",
                "title": "Whitfield County 911 point for 1199 Enterprise Drive",
                "source_url": WHITFIELD_ADDRESS_URL,
                "publisher": "Whitfield County, Georgia",
                "source_family": "whitfield_county_addressing_points",
                "published_at": None,
                "retrieved_at": "2026-07-21T06:33:56Z",
                "license": "all-rights-reserved",
                "attribution": "Whitfield County, Georgia",
                "excerpt": (
                    "The exact Whitfield query returns one commercial address point, "
                    "OBJECTID 226055, for 1199 Enterprise Drive."
                ),
                "content_hash": (
                    "add0b6ce576afa5b0de6e6a23ee7990d64ae19b805414106b938baefdfd3f5a9"
                ),
                "metadata": whitfield_metadata,
            },
        ],
    }


def _point_geometry(point: dict[str, float]) -> dict[str, Any]:
    return {
        "type": "Point",
        "coordinates": [point["longitude"], point["latitude"]],
    }


def _build_successors() -> dict[str, dict[str, Any]]:
    evidence = _evidence_records()
    outputs: dict[str, dict[str, Any]] = {}
    locations = {
        "coresite": {
            "point": DENVER_POINT,
            "geometry": {"type": "Polygon", "coordinates": [DENVER_RING]},
            "evidence_key": evidence["coresite"][-1]["key"],
            "method": "authoritative_site_plan",
        },
        "powerhouse": {
            "point": IRVING_POINT,
            "geometry": _point_geometry(IRVING_POINT),
            "evidence_key": evidence["powerhouse"][0]["key"],
            "method": "authoritative_address_geocode",
        },
        "edged": {
            "point": AURORA_POINT,
            "geometry": _point_geometry(AURORA_POINT),
            "evidence_key": evidence["edged"][-1]["key"],
            "method": "authoritative_address_geocode",
        },
        "dalton4": {
            "point": WHITFIELD_POINT,
            "geometry": _point_geometry(WHITFIELD_POINT),
            "evidence_key": evidence["dalton4"][-1]["key"],
            "method": "authoritative_address_geocode",
        },
    }
    for label, spec in PREDECESSORS.items():
        predecessor = _load_predecessor(label)
        successor = copy.deepcopy(predecessor)
        successor["schema_version"] = "1.1"
        successor["evidence"].extend(copy.deepcopy(evidence[label]))
        location = locations[label]
        for entity_name in ("campus", "project"):
            entity = successor[entity_name]
            entity["coordinates"] = copy.deepcopy(location["point"])
            entity["geometry"] = copy.deepcopy(location["geometry"])
            entity["evidence_key"] = location["evidence_key"]
            entity["as_of_date"] = AS_OF_DATE
            entity["method"] = location["method"]
        output_path = SOURCE_DIR / spec["successor"]
        raw = _canonical_json(successor)
        _write_exact(output_path, raw)
        output_path.chmod(0o644)
        outputs[label] = {
            "path": f"sources/{spec['successor']}",
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "document": successor,
        }
    return outputs


def _capture_row(
    *,
    request_id: str,
    review_role: str,
    evidence_key: str | None,
    url: str,
    retrieved_at: str,
    http_version: str,
    content_type: str,
    content_encoding: str | None,
    size_download: int,
    header_count: int,
    body: tuple[int, str],
    headers: tuple[int, str],
    curl_writeout: tuple[int, str],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "review_role": review_role,
        "disposition": "accepted_hash_only",
        "evidence_key": evidence_key,
        "method": "GET",
        "url": url,
        "effective_url": url,
        "retrieved_at": retrieved_at,
        "http_status": 200,
        "http_version": http_version,
        "content_type": content_type,
        "content_encoding": content_encoding,
        "curl_size_download_bytes_as_received": size_download,
        "curl_num_headers": header_count,
        "redirect_count": 0,
        "request_credentials_supplied": False,
        "request_cookie_input_supplied": False,
        "response_cookies_persisted_or_reused": False,
        "body": {"bytes": body[0], "sha256": body[1], "retained": False},
        "headers": {
            "bytes": headers[0],
            "sha256": headers[1],
            "retained": False,
        },
        "curl_writeout": {
            "bytes": curl_writeout[0],
            "sha256": curl_writeout[1],
            "retained": False,
        },
    }


def _retrieval_inventory() -> dict[str, Any]:
    requests = [
        _capture_row(
            request_id="denver_parcel",
            review_role="coordinate_evidence",
            evidence_key="denver-coresite-de3-tax-parcel-captured-2026-07-20",
            url=DENVER_PARCEL_URL,
            retrieved_at="2026-07-21T06:33:52Z",
            http_version="HTTP/2",
            content_type="application/json; charset=utf-8",
            content_encoding="gzip",
            size_download=1_327,
            header_count=26,
            body=(
                3_919,
                "41387d3d2d09af9e88e494d24f29ccc6897f25b0b077edf5f9011a470de0c7e2",
            ),
            headers=(
                1_118,
                "fcc46caa6d9c1693f648395d3a81be9cfb7d1489521c64475a78eb372db2f719",
            ),
            curl_writeout=(
                12_647,
                "073fc0fd71d0c126f6ed1cc9bbde919f3cce4d3a6c501e4a659f6b3367e2bed9",
            ),
        ),
        _capture_row(
            request_id="denver_rights",
            review_role="license_context",
            evidence_key=None,
            url=DENVER_RIGHTS_URL,
            retrieved_at="2026-07-21T06:33:52Z",
            http_version="HTTP/1.1",
            content_type="text/html; charset=utf-8",
            content_encoding=None,
            size_download=158_115,
            header_count=23,
            body=(
                158_115,
                "dd38845675c959b61e56f6e58e1bf7c967e6279793d7561d7d40af010a442d13",
            ),
            headers=(
                1_053,
                "7989f91b9b648636537b20b02d1832b527798f70ed2a1b99f82addd2ad4f866a",
            ),
            curl_writeout=(
                27_193,
                "f6aac63cee8cf3b1d2adb05a72a08d411229cd3ff0e2997875d0c1e107d8d411",
            ),
        ),
        _capture_row(
            request_id="irving_permit",
            review_role="coordinate_evidence",
            evidence_key=(
                "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20"
            ),
            url=IRVING_PERMIT_URL,
            retrieved_at="2026-07-21T06:33:53Z",
            http_version="HTTP/2",
            content_type="application/json; charset=utf-8",
            content_encoding="gzip",
            size_download=412,
            header_count=27,
            body=(
                582,
                "c01d04e1303c2c66df6449656f0cc102d487bcb9c5564b58d8a3ddce405ebb0d",
            ),
            headers=(
                1_156,
                "f6ca4dcc3a222ac6cf54ae068aaa422e9d7dc0458ff2de06147669d4a0873d6e",
            ),
            curl_writeout=(
                12_494,
                "5cf75c3fe508367bd69ad5b3973847b8d56281a2eee880e1ac54e4991797853c",
            ),
        ),
        _capture_row(
            request_id="irving_address",
            review_role="coordinate_corroboration",
            evidence_key="irving-site-address-4324801-captured-2026-07-20",
            url=IRVING_ADDRESS_URL,
            retrieved_at="2026-07-21T06:33:53Z",
            http_version="HTTP/2",
            content_type="application/json; charset=utf-8",
            content_encoding="gzip",
            size_download=264,
            header_count=27,
            body=(
                359,
                "5713981c26c61f9571361e35e0f29461eaa51d8e60a75df9f6999c056540d10e",
            ),
            headers=(
                1_154,
                "4899f9534a5aa56d52a223349c22aedb194cc2ff60cc9f9bf6b9402cc65c23f1",
            ),
            curl_writeout=(
                12_262,
                "b0891c68596c96502af832e7adb9a391deae389707e109ad705ca7a0d7aa0448",
            ),
        ),
        _capture_row(
            request_id="aurora_address",
            review_role="coordinate_evidence",
            evidence_key=(
                "aurora-edged-chicago-address-point-85050-captured-2026-07-20"
            ),
            url=AURORA_ADDRESS_URL,
            retrieved_at="2026-07-21T06:33:55Z",
            http_version="HTTP/2",
            content_type="application/json; charset=utf-8",
            content_encoding="gzip",
            size_download=309,
            header_count=27,
            body=(
                426,
                "8db6b8217609665b4b58ab8ade5e5bb0a252321f056a1e80d6203533d837a84a",
            ),
            headers=(
                1_158,
                "d0783cf4a5ffb9a72bd129abd417b09c5377e2f9a5f676b168de11ce6e489324",
            ),
            curl_writeout=(
                12_390,
                "d375bc28d8a41fc4584528e22b1429014b3f53920186a614f2c30dcf1a6463a1",
            ),
        ),
        _capture_row(
            request_id="aurora_public_domain",
            review_role="license_context",
            evidence_key=None,
            url=AURORA_RIGHTS_URL,
            retrieved_at="2026-07-21T06:33:55Z",
            http_version="HTTP/2",
            content_type="application/json;charset=utf-8",
            content_encoding="gzip",
            size_download=1_039,
            header_count=14,
            body=(
                2_080,
                "172afdc84cbd96063c3bb410889ae69889d05e4fab2a84f23f1ab1783ce1a347",
            ),
            headers=(
                491,
                "64c5dbf46cb4bc6972b2eeb5e7e1f76913df9576bd6f3b9604503687045a7b76",
            ),
            curl_writeout=(
                14_545,
                "936d5ab187eec2850d1ad5d6c897be2abd5ba0e179a706d8e8da5dd5edab973c",
            ),
        ),
        _capture_row(
            request_id="ga_epd_advisory",
            review_role="identity_bridge_evidence",
            evidence_key=(
                "ga-epd-dalton4-application-29951-advisory-captured-2026-07-20"
            ),
            url=GA_EPD_ADVISORY_URL,
            retrieved_at="2026-07-21T06:35:08Z",
            http_version="HTTP/2",
            content_type="application/pdf",
            content_encoding=None,
            size_download=104_495,
            header_count=24,
            body=(
                104_495,
                "2f292f0c5b03dedfcd3beaba324875f247b487bbe2a5267d82b30888b5bd49a9",
            ),
            headers=(
                1_027,
                "5ff944aafe8d704a4c9a42bf4fc9e03d46117f193d4040b3d8886d198c792c9f",
            ),
            curl_writeout=(
                9_566,
                "9434c4c85424a86dca8ae1fc0eb91c7bae7a360fe6138e65a94190a6001f651d",
            ),
        ),
        _capture_row(
            request_id="whitfield_address",
            review_role="coordinate_evidence",
            evidence_key=(
                "whitfield-1199-enterprise-address-point-captured-2026-07-20"
            ),
            url=WHITFIELD_ADDRESS_URL,
            retrieved_at="2026-07-21T06:33:56Z",
            http_version="HTTP/2",
            content_type="application/geo+json; charset=UTF-8",
            content_encoding="gzip",
            size_download=263,
            header_count=12,
            body=(
                346,
                "add0b6ce576afa5b0de6e6a23ee7990d64ae19b805414106b938baefdfd3f5a9",
            ),
            headers=(
                559,
                "77067c16e7b014d8da445cbf65cee6913977b42385a2ecaf6d4db454825e2963",
            ),
            curl_writeout=(
                16_034,
                "c35e5f9da8da6d5ea5d225ad82c960c96b82433e46b9771cd195334211b73cf5",
            ),
        ),
        _capture_row(
            request_id="whitfield_disclaimer",
            review_role="license_context",
            evidence_key=None,
            url=WHITFIELD_DISCLAIMER_URL,
            retrieved_at="2026-07-21T06:33:56Z",
            http_version="HTTP/2",
            content_type="text/html",
            content_encoding=None,
            size_download=3_442,
            header_count=8,
            body=(
                3_442,
                "c562307d57768eef89836eb22c7f19a572b8d2bbb2781da898f45b6d5a810fef",
            ),
            headers=(
                245,
                "e212567f6683d0bdec7babea04bf12f2b791bcdee68799b7326537fc1ebd9a4d",
            ),
            curl_writeout=(
                14_943,
                "1725fc5ad554568a1991a5190ece54a4c6a6239f6887a2f950a3b8849c483f7f",
            ),
        ),
    ]
    requests.append(
        {
            "request_id": "ga_epd_draft_unpublished",
            "review_role": "identity_bridge_candidate",
            "disposition": "technical_incident_unpublished_no_evidence",
            "evidence_key": None,
            "method": "GET",
            "url": GA_EPD_DRAFT_URL,
            "effective_url": (
                "https://epd.georgia.gov/document/document/29951-draft--UNPUBLISHED-"
                "document--DO-NOT-SHARE-this-URL--/download"
            ),
            "retrieved_at": "2026-07-21T06:33:56Z",
            "http_status": 403,
            "http_version": "HTTP/2",
            "content_type": "text/html; charset=UTF-8",
            "content_encoding": "gzip",
            "curl_size_download_bytes_as_received": 0,
            "curl_num_headers": 23,
            "redirect_count": 1,
            "request_credentials_supplied": False,
            "request_cookie_input_supplied": False,
            "response_cookies_persisted_or_reused": False,
            "body": {
                "bytes": None,
                "sha256": None,
                "retained": False,
                "reason": (
                    "curl --fail stopped on HTTP 403 after the official route redirected "
                    "to an unpublished document path; no response body was written or "
                    "hashed"
                ),
            },
            "headers": {
                "bytes": 1_945,
                "sha256": (
                    "5ad25830f2a404b4c1115b38a7132e87205e5c958cc9a90998cc375c141c465c"
                ),
                "retained": False,
            },
            "curl_writeout": {
                "bytes": 9_705,
                "sha256": (
                    "b87ce28b0babbf0818ceb5e12644788076c47e5fe5162febd6af8a75396de73b"
                ),
                "retained": False,
            },
            "guardrail": (
                "This failed request is a technical incident only. It creates no source "
                "evidence, no content hash, no 1199-address assertion, and no lifecycle, "
                "capacity, energy, role, workload, or status observation."
            ),
        }
    )
    return {
        "schema_version": "1.0",
        "collection_id": ARTIFACT_ID,
        "analysis_date": AS_OF_DATE,
        "analysis_timezone": "America/Los_Angeles",
        "analysis_temporary_response_bodies_deleted": True,
        "raw_response_bodies_retained": False,
        "raw_response_headers_retained": False,
        "raw_curl_writeouts_retained": False,
        "raw_payloads_redistributed": False,
        "direct_request_attempts": 10,
        "successful_response_requests": 9,
        "coordinate_or_identity_evidence_requests": 6,
        "license_context_requests": 3,
        "technical_incidents": 1,
        "capture_policy": (
            "All controlled requests were credential-free reads of official operator, "
            "government, municipal, cadastral, or GIS endpoints. Exact body, raw-header, "
            "and full curl-writeout files were retained only temporarily for hash "
            "validation and are not redistributed."
        ),
        "telemetry_guardrail": (
            "Only safe response facts are inventoried. Request secrets, cookies, local "
            "and remote addresses, ports, certificate paths, connection identifiers, and "
            "TLS telemetry are excluded."
        ),
        "reference_only_urls": [
            {
                "role": "license_policy_reference",
                "url": IRVING_POLICY_URL,
                "capture_status": (
                    "legacy hostname certificate mismatch; migrated irvingtx.gov target "
                    "returned a Cloudflare challenge"
                ),
                "body_bytes": None,
                "body_sha256": None,
                "guardrail": (
                    "No policy response body or hash is claimed. The URL is retained only "
                    "as the City policy reference for the public-domain disposition."
                ),
            }
        ],
        "controlled_http_requests": requests,
    }


def _disposition(outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sites = []
    scopes = {
        "coresite": {
            "site": "CoreSite DE3",
            "geometry_scope": "de3_tax_parcel_boundary",
            "appended": [
                "denver-coresite-de3-tax-parcel-captured-2026-07-20"
            ],
        },
        "powerhouse": {
            "site": "PowerHouse Irving Building 1",
            "geometry_scope": (
                "official_site_address_point / official_permit_project_address_point"
            ),
            "appended": [
                "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20",
                "irving-site-address-4324801-captured-2026-07-20",
            ],
        },
        "edged": {
            "site": "Edged Chicago ORD01-2",
            "geometry_scope": "campus_address_point",
            "appended": [
                "aurora-edged-chicago-address-point-85050-captured-2026-07-20"
            ],
        },
        "dalton4": {
            "site": "Core Scientific Dalton 4",
            "geometry_scope": "official_911_facility_address_point",
            "appended": [
                "ga-epd-dalton4-application-29951-advisory-captured-2026-07-20",
                "whitfield-1199-enterprise-address-point-captured-2026-07-20",
            ],
        },
    }
    for label, spec in PREDECESSORS.items():
        sites.append(
            {
                "site": scopes[label]["site"],
                "predecessor": {
                    "path": f"sources/{spec['path']}",
                    "bytes": spec["bytes"],
                    "sha256": spec["sha256"],
                },
                "disposition": "coordinate_only_full_file_successor_unseeded",
                "successor": {
                    "path": outputs[label]["path"],
                    "bytes": outputs[label]["bytes"],
                    "sha256": outputs[label]["sha256"],
                },
                "changed_entities": ["campus", "project"],
                "changed_entity_fields": [
                    "coordinates",
                    "geometry",
                    "evidence_key",
                    "as_of_date",
                    "method",
                ],
                "geometry_scope": scopes[label]["geometry_scope"],
                "appended_evidence_keys": scopes[label]["appended"],
                "claim_guardrail": (
                    "No lifecycle, capacity, workload, role, operating-model, energy, "
                    "status, canonical-address, or inherited evidence row is changed."
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "review_id": ARTIFACT_ID,
        "review_date": AS_OF_DATE,
        "predecessor_release": "v64",
        "predecessor_release_definition": V64_DEFINITION,
        "integration_status": "standalone_unseeded",
        "replacement_semantics": (
            "Each accepted successor is a full-file replacement candidate for the exact "
            "v64-selected predecessor. A predecessor and successor must never coexist in "
            "one seed or release."
        ),
        "authority_policy": (
            "Coordinates and geometry require an exact operator, government, municipal, "
            "cadastral, or official-GIS bridge. Generic geocoders, map clicks, satellite "
            "or image alignment, interpolation, and analyst-drawn geometry are forbidden."
        ),
        "claim_policy": (
            "Only schema_version where necessary, appended coordinate evidence, and the "
            "explicitly listed location snapshot fields may differ. Every inherited "
            "evidence row and all lifecycle, capacity, role, workload, operating-model, "
            "energy, and status content remain predecessor-identical."
        ),
        "summary": {
            "reviewed_sites": 4,
            "coordinate_successors": 4,
            "appended_evidence_records": 6,
            "rejected_nonpromotions": 1,
            "technical_incidents": 1,
        },
        "rejected_nonpromotions": [REJECTED_EDGED_V2],
        "technical_incidents": [
            {
                "incident_id": "ga_epd_draft_unpublished",
                "url": GA_EPD_DRAFT_URL,
                "disposition": "no_evidence_no_body_hash",
                "fallback": (
                    "Live Georgia EPD advisory binds Dalton 4, Enterprise Drive, and "
                    "application 29951; exact Whitfield OBJECTID 226055 supplies the 1199 "
                    "Enterprise address point."
                ),
            }
        ],
        "sites": sites,
    }


def _readme() -> str:
    return """# Authoritative coordinate successors after open-seed v64

This closed, hash-only source artifact records four coordinate-only full-file
successors for the exact files selected by open-seed v64: CoreSite DE3,
PowerHouse Irving Building 1, Edged Chicago ORD01-2, and Core Scientific
Dalton 4.

The successors append compact factual evidence and update only the campus and
project location snapshots. They do not change lifecycle, capacity, energy,
roles, workload, operating model, status, or canonical address. They are
standalone and unseeded; a future release must replace each predecessor rather
than selecting both versions.

CoreSite uses the exact Denver-owned WGS84 tax parcel for schedule number
0214400131000 and a deterministic Shapely representative point inside the
valid polygon. PowerHouse uses the exact Irving permit point, corroborated by
site-address point 4324801. Edged uses Aurora address point 85050 as a campus
address point, not an ORD01-2 centroid. Dalton 4 uses the live Georgia EPD
application-29951 identity bridge and Whitfield 911 OBJECTID 226055 while
preserving 3024 Old Tilton Road as canonical and recording 1199 Enterprise
Drive only as an official alias.

The pre-existing Edged Google Maps-derived v2 remains untouched, rejected,
and unselected. The Georgia EPD draft-permit URL became unpublished during
capture; its 403 is retained only as a technical incident, with no fabricated
PDF body hash or evidence row.

No raw response body, response header, curl telemetry, PDF, GIS payload, map,
or publisher media is redistributed. The inventory retains only hashes, byte
counts, safe response facts, and compact factual extracts. All source and
artifact identifiers use the America/Los_Angeles research date 2026-07-20;
UTC retrieval timestamps may fall on 2026-07-21.
"""


def _build_artifact(outputs: dict[str, dict[str, Any]]) -> None:
    documents = {
        "README.md": _readme().encode("utf-8"),
        "disposition.json": _canonical_json(_disposition(outputs)),
        "retrieval-inventory.json": _canonical_json(_retrieval_inventory()),
    }
    for name, data in documents.items():
        _write_exact(ARTIFACT_DIR / name, data)
    file_entries = [
        {
            "bytes": len(documents[name]),
            "path": name,
            "sha256": _sha256(documents[name]),
        }
        for name in sorted(documents)
    ]
    tree_payload = (
        json.dumps(file_entries, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "files": file_entries,
        "format": "datacenter-atlas-coordinate-source-artifact-manifest-v1",
        "tree_sha256": _sha256(tree_payload),
    }
    manifest_raw = _canonical_json(manifest)
    _write_exact(ARTIFACT_DIR / "manifest.json", manifest_raw)
    manifest_hash_raw = f"{_sha256(manifest_raw)}  manifest.json\n".encode()
    _write_exact(ARTIFACT_DIR / "manifest.sha256", manifest_hash_raw)
    for artifact_file in ARTIFACT_DIR.iterdir():
        if artifact_file.is_file():
            artifact_file.chmod(0o444)
    ARTIFACT_DIR.chmod(0o555)


def main() -> None:
    definition_path = ROOT / V64_DEFINITION["path"]
    definition_raw = definition_path.read_bytes()
    if (
        len(definition_raw) != V64_DEFINITION["bytes"]
        or _sha256(definition_raw) != V64_DEFINITION["sha256"]
    ):
        raise RuntimeError("open-seed v64 definition pin mismatch")
    selected = {
        row["path"]: row["sha256"]
        for row in json.loads(definition_raw)["curated_inputs"]
    }
    for spec in PREDECESSORS.values():
        selected_path = f"sources/{spec['path']}"
        if selected.get(selected_path) != spec["sha256"]:
            raise RuntimeError(f"v64 predecessor selection mismatch: {selected_path}")
        if f"sources/{spec['successor']}" in selected:
            raise RuntimeError(f"successor unexpectedly selected by v64: {spec['successor']}")
    if REJECTED_EDGED_V2["path"] in selected:
        raise RuntimeError("rejected Edged Google-derived v2 is selected by v64")
    outputs = _build_successors()
    _build_artifact(outputs)
    for label, output in outputs.items():
        print(label, output["bytes"], output["sha256"], output["path"])
    manifest_raw = (ARTIFACT_DIR / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    print("manifest", len(manifest_raw), _sha256(manifest_raw))
    print("tree", manifest["tree_sha256"])


if __name__ == "__main__":
    main()
