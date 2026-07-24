"""Build and atomically publish the immutable coordinate assessment v6.

This assessment is a coordinate-only overlay on the accepted open-seed v84
inputs.  It creates seven schema-1.1 successors for six campuses, retains one
two-point campus in review, and records five explicit exclusions.  Raw source
bodies are never copied into the artifact; only exact hashes and compact
factual extractions are published.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Mapping

from .open_seed_v69 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v6"
ARTIFACT_DIR = PUBLICATION_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = PUBLICATION_ROOT / f".{ARTIFACT_ID}.lock"
AS_OF_DATE = "2026-07-21"
ASSESSMENT_RETRIEVED_AT = "2026-07-21T19:25:00Z"

BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v84.json"
BASE_DEFINITION_BYTES = 100_280
BASE_DEFINITION_SHA256 = (
    "910b2f0d830106b274d8ec22849e2d637463ea5fc57c3481aca2d468218bf8ef"
)
BASE_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v84/manifest.json"
BASE_MANIFEST_BYTES = 15_118
BASE_MANIFEST_SHA256 = (
    "0c4b7b3979c5c3bcdfb3a9bef38b5b32f4da5df31633a0c38920ef937914e301"
)
BASE_RELEASE_TREE_SHA256 = (
    "3ec1197343778c51609221aedbac6f4bf8942cb6620c80fc857b7b1f3124e52b"
)
BASE_RECORDED_AT = "2026-07-21T19:10:20Z"

OCEANIA_ARTIFACT = (
    ROOT / "source_artifacts/global-official-builds-oceania-gap-2026-07-21-v1"
)
OCEANIA_MANIFEST_BYTES = 1_708
OCEANIA_MANIFEST_SHA256 = (
    "4c60b65554242278784ff726c6e176cb2ed70d9a2d1d1c062a3d729d87d77c85"
)
OCEANIA_LOGICAL_TREE_SHA256 = (
    "6eb4e2d73270fedc07113e3f3d483b9c8fd307768e230d7ab54862308e38cdba"
)
OCEANIA_PHYSICAL_TREE_SHA256 = (
    "063602c77cafc7305803f41551b6224d0b7e6a5197e274ed4b285fa66fd82615"
)
OCEANIA_CAPTURE = {
    "preserved_path": "/Users/kian/.Trash/dc-official-oceania-20260721.xLyZD6",
    "files": 40,
    "bytes": 2_824_074,
    "tree_sha256": (
        "4729444343350e9c3ec0ba388f90207e1012078656135005cb35cbc200d63148"
    ),
}

CEE_ARTIFACT = ROOT / "source_artifacts/global-official-builds-cee-gap-2026-07-21-v1"
CEE_MANIFEST_BYTES = 1_744
CEE_MANIFEST_SHA256 = (
    "13ffdc16826e4fc1caf75b3b9c97fe8f2176193247512992254bd8ae114bc4f9"
)
CEE_LOGICAL_TREE_SHA256 = (
    "cdbb23055c9380ae7d1e64048529e4476e4f222afe6d599c09c1f9dcb78fa14d"
)
CEE_PHYSICAL_TREE_SHA256 = (
    "e23ecade126ad455d9b2819b614c7b45574f099c419f73cf3457adbb7091e91e"
)
CEE_CAPTURE = {
    "preserved_path": "/Users/kian/.Trash/dc-official-cee-20260721.z5x8RN",
    "files": 83,
    "bytes": 1_664_612,
    "tree_sha256": (
        "628ce85aba4cb295a434aeb4cd1bd3b319f414445ac92e94750661232290a37c"
    ),
}

PRIOR_ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v5"
PRIOR_MANIFEST_BYTES = 2_022
PRIOR_MANIFEST_SHA256 = (
    "b05492a0454502e332c6517b60e48a99f3897f29dfae9ccd4d69569da3173b34"
)
PRIOR_LOGICAL_TREE_SHA256 = (
    "dc74260a7b03bea2f9250b8962fc47f7cb1a1e45bdedb1ee046ee67e021b17e2"
)
PRIOR_PHYSICAL_TREE_SHA256 = (
    "ecc63ed53d0151366caaf1d3d8b82a70ff4e1476baebc737356e3d8a8f77116f"
)


class SiteCoordinateAssessmentV6Error(RuntimeError):
    """Raised when a v6 provenance, delta, or publication fuse fails closed."""


COHORT: dict[str, tuple[int, str, str]] = {
    "curated-official-2026-07-21-airtrunk-syd3-current-build.json": (
        7_293,
        "050cbf1db6b1ed0ba414a352ed89607b26277802fe339e2176f15fe04ddf09ff",
        "accepted_official_facility_point",
    ),
    "curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json": (
        5_409,
        "af9c9fe758609be14a814d352aead1f78a1af7a3d5ab80ad990311c1ced03e16",
        "accepted_shared_campus_point_not_facility_specific",
    ),
    "curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json": (
        5_414,
        "27852ea8af7bc6b3c3de64747041c93212e6f0515230ad64a89077c0e7463150",
        "accepted_shared_campus_point_not_facility_specific",
    ),
    "curated-official-2026-07-21-microsoft-ath04-spata-current-build.json": (
        8_386,
        "4368d6b67766cfdcddeeaf30cf7e70f4e82d1094ea8616952b0fa7a85bdc9c97",
        "accepted_official_site_geometry_without_representative_point",
    ),
    "curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json": (
        6_455,
        "1ec21ecde6660e3ff62b469693fe277998b85fc892127ca15d9612981381a65f",
        "accepted_official_address_point",
    ),
    "curated-official-2026-07-21-ten-brinke-spata-current-build.json": (
        7_835,
        "feb7d0fb6fc9ef7da9fe06ab16177a75247b3220ffeba6572cf8dccebd61bed4",
        "accepted_publisher_embedded_project_point",
    ),
    "curated-official-2026-07-21-ast-janciems-shell-fit-out.json": (
        4_296,
        "02b9f7c85d1a22ff4b290c01954adce2909295fd33517993496f4221fc61f206",
        "accepted_official_address_point",
    ),
    "curated-official-2026-07-21-cdc-marsden-park-current-build.json": (
        3_529,
        "8ef701ac0b4346aed089996487a149dd1aea2545ce11b0b30c53faf5a1807322",
        "review_two_official_lot_points_no_multipoint_schema",
    ),
    "curated-official-2026-07-21-cdc-maddington-current-build.json": (
        7_511,
        "6b35ab149f542912d59750092903324bf8d1dcdc62ed4aa271dad8fdcb4159c8",
        "review_no_facility_coordinate_bridge",
    ),
    "curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json": (
        3_717,
        "b28d52ff6f4ba56fcfe9d52295464f18c76030bc41d9a4c12998aa101cd75c14",
        "review_aggregate_unnamed_facilities",
    ),
    "curated-official-2026-07-21-serbia-state-dc-kragujevac-modules-3-4-operational.json": (
        6_280,
        "36cccf1eaa107e1581879722438ca1f22e5c371ae77cbaeb8d0a9bc76b5d38f2",
        "review_operational_not_current_construction",
    ),
    "curated-official-2026-07-21-cdc-laverton-current-build.json": (
        3_570,
        "27f91ee149d0932fc73894a71364924dd00aed0640513f8df6af0717769309e6",
        "ineligible_locality_only",
    ),
    "curated-official-2026-07-21-gta-gu3-alupang-operational-closure.json": (
        10_101,
        "92f0a23086354133f4f9387f3f169ecf23cbacd7268e2c477611eefceeeb7d2c",
        "ineligible_operational_closure",
    ),
}


E31_NATIVE = [
    [493741.401, 4203075.250],
    [493755.451, 4203075.700],
    [493768.191, 4203081.640],
    [493961.271, 4202950.280],
    [493806.001, 4202722.040],
    [493595.091, 4202865.530],
    [493621.501, 4202904.350],
    [493643.271, 4202931.010],
    [493741.401, 4203075.250],
]
E26_NATIVE = [
    [493586.661, 4202853.120],
    [493715.791, 4202765.270],
    [493702.991, 4202725.530],
    [493551.521, 4202728.730],
    [493527.900, 4202744.800],
    [493528.830, 4202754.540],
    [493525.950, 4202763.900],
    [493586.661, 4202853.120],
]
E31_WGS84_SOURCE_ORDER = [
    [23.9304400737, 37.9778811302],
    [23.9306000486, 37.9778852805],
    [23.9307450609, 37.9779389025],
    [23.9329446228, 37.9767562439],
    [23.9311786065, 37.9746981218],
    [23.9287759585, 37.9759899514],
    [23.9290763285, 37.9763400133],
    [23.9293239745, 37.9765804459],
    [23.9304400737, 37.9778811302],
]
E26_WGS84_SOURCE_ORDER = [
    [23.9286800819, 37.9758780433],
    [23.9301511160, 37.9750871435],
    [23.9300057159, 37.9747288847],
    [23.9282810661, 37.9747566872],
    [23.9280119783, 37.9749013600],
    [23.9280224815, 37.9749891520],
    [23.9279896076, 37.9750734926],
    [23.9286800819, 37.9758780433],
]

ATH04_CAMPUS_GEOMETRY = {
    "type": "MultiPolygon",
    "coordinates": [
        [[*reversed(E31_WGS84_SOURCE_ORDER)]],
        [[*reversed(E26_WGS84_SOURCE_ORDER)]],
    ],
}
ATH04_PROJECT_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[*reversed(E31_WGS84_SOURCE_ORDER)]],
}


ACCEPTED: tuple[dict[str, Any], ...] = (
    {
        "label": "syd3",
        "predecessor": "curated-official-2026-07-21-airtrunk-syd3-current-build.json",
        "evidence_key": "nsw-airtrunk-syd3-drupal-geofield-coordinate-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "NSW Department of Planning, Housing and Infrastructure",
        "source_family": "nsw_major_projects_and_bcf_records",
        "source_url": (
            "https://www.planningportal.nsw.gov.au/major-projects/projects/"
            "51-huntingwood-drive-data-centre-mod-2-design-updates"
        ),
        "title": "51 Huntingwood Drive Data Centre official portal point",
        "content_hash": (
            "78035079c52ffaffc953da3fbf71e217ca941281968f114aae1d9d6ab12c9af5"
        ),
        "retrieved_at": "2026-07-19T00:13:19Z",
        "license": "CC-BY-4.0",
        "attribution": (
            "State of New South Wales and Department of Planning, Housing and "
            "Infrastructure"
        ),
        "excerpt": (
            "The NSW portal Drupal geofield reports the EPSG:4326 point for "
            "SSD-41589232-Mod-2; the BCF register bridges SSD-41589232 and 51 "
            "Huntingwood Drive to the data-centre site."
        ),
        "method": "authoritative_site_plan",
        "point": [150.876, -33.798627],
        "uncertainty_m": 100,
        "facility_specific": True,
    },
    {
        "label": "ec5",
        "predecessor": "curated-official-2026-07-21-cdc-eastern-creek-ec5-current-build.json",
        "evidence_key": "nsw-cdc-eastern-creek-ec5-campus-coordinate-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "NSW Department of Planning, Housing and Infrastructure",
        "source_family": "nsw_major_projects_records",
        "source_url": (
            "https://www.planningportal.nsw.gov.au/major-projects/projects/"
            "roberts-road-data-centre"
        ),
        "title": "Roberts Road Data Centre official campus point for CDC EC5",
        "content_hash": (
            "4f38942c41791c0382e88f852bd8a8da4f820ab563b6b564676fef1af5577904"
        ),
        "retrieved_at": ASSESSMENT_RETRIEVED_AT,
        "license": "no-license-stated-for-compact-factual-extraction",
        "attribution": "NSW Department of Planning, Housing and Infrastructure",
        "excerpt": (
            "The NSW SSD-10330 Roberts Road record provides a representative "
            "point for the shared CDC Eastern Creek campus; it is not an EC5 "
            "building-specific point."
        ),
        "method": "authoritative_site_plan",
        "point": [150.837668, -33.818072],
        "uncertainty_m": 250,
        "facility_specific": False,
    },
    {
        "label": "ec6",
        "predecessor": "curated-official-2026-07-21-cdc-eastern-creek-ec6-current-build.json",
        "evidence_key": "nsw-cdc-eastern-creek-ec6-campus-coordinate-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "NSW Department of Planning, Housing and Infrastructure",
        "source_family": "nsw_major_projects_records",
        "source_url": (
            "https://www.planningportal.nsw.gov.au/major-projects/projects/"
            "roberts-road-data-centre"
        ),
        "title": "Roberts Road Data Centre official campus point for CDC EC6",
        "content_hash": (
            "4f38942c41791c0382e88f852bd8a8da4f820ab563b6b564676fef1af5577904"
        ),
        "retrieved_at": ASSESSMENT_RETRIEVED_AT,
        "license": "no-license-stated-for-compact-factual-extraction",
        "attribution": "NSW Department of Planning, Housing and Infrastructure",
        "excerpt": (
            "The NSW SSD-10330 Roberts Road record provides a representative "
            "point for the shared CDC Eastern Creek campus; it is not an EC6 "
            "building-specific point."
        ),
        "method": "authoritative_site_plan",
        "point": [150.837668, -33.818072],
        "uncertainty_m": 250,
        "facility_specific": False,
    },
    {
        "label": "ath04",
        "predecessor": "curated-official-2026-07-21-microsoft-ath04-spata-current-build.json",
        "evidence_key": "greece-microsoft-ath04-e31-e26-site-geometry-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "Hellenic Ministry of Development and Investments",
        "source_family": "greece_strategic_investment_site_plan_records",
        "source_url": (
            "https://ependyseis.mindev.gov.gr/uploads/photos/"
            "i-t-01-topografiko-diagramma.pdf"
        ),
        "title": "ATH04 official E31 and E26 site-plan geometry",
        "content_hash": (
            "64a5e9f65967e443fcab288f03a3b76c35c3ed8c028024bebacfa06201e81ba2"
        ),
        "retrieved_at": ASSESSMENT_RETRIEVED_AT,
        "license": "no-license-stated-for-compact-factual-extraction",
        "attribution": "Hellenic Ministry of Development and Investments",
        "excerpt": (
            "The official topographic plan supplies closed E31 and E26 parcel "
            "rings in EPSG:2100. E31 is the active ATH04 project geometry; E31 "
            "plus E26 is the campus geometry."
        ),
        "method": "authoritative_site_plan",
        "campus_geometry": ATH04_CAMPUS_GEOMETRY,
        "project_geometry": ATH04_PROJECT_GEOMETRY,
        "facility_specific": True,
    },
    {
        "label": "tet",
        "predecessor": "curated-official-2026-07-21-tet-dc7-salaspils-phase1-current-build.json",
        "evidence_key": "latvia-vzd-tet-dc7-address-point-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "Valsts zemes dienests",
        "source_family": "latvia_vzd_address_register",
        "source_url": (
            "https://geo-dpps.viss.gov.lv/api/DPPSPackage/client/"
            "Adresu_tel_418_k6gL2A/3d692785-0c95-44a8-816c-f2f91493c4ce?"
            "service=WFS&version=2.0.0&request=GetFeature&typeNames=ad%3AAddress&"
            "featureID=AD107074603"
        ),
        "title": "VZD address point AD107074603 for Tet DC7",
        "content_hash": (
            "cd186ef19caa2fe65544ec7e3218660519aec3babd2d532350e9c83392ecd011"
        ),
        "retrieved_at": ASSESSMENT_RETRIEVED_AT,
        "license": "CC-BY-4.0",
        "attribution": "Valsts zemes dienests (State Land Service), CC BY 4.0",
        "excerpt": (
            "The current VZD address feature AD107074603 gives the address point "
            "for Krasta iela 2 k-1, Salaspils; the construction record's /1 "
            "notation resolves to the same building designator."
        ),
        "method": "authoritative_address_geocode",
        "point": [24.3802635323, 56.8656322193],
        "uncertainty_m": 20,
        "facility_specific": True,
    },
    {
        "label": "ten_brinke",
        "predecessor": "curated-official-2026-07-21-ten-brinke-spata-current-build.json",
        "evidence_key": "ten-brinke-spata-project-map-point-captured-2026-07-21",
        "kind": "company_disclosure",
        "publisher": "Ten Brinke Group",
        "source_family": "ten_brinke_project_pages",
        "source_url": (
            "https://www.tenbrinke.com/en/projects/current-projects/"
            "current-projects-details/data-center-spata-26-1052-gr.html"
        ),
        "title": "Ten Brinke Spata project-page embedded map marker",
        "content_hash": (
            "9ef57bbcb1517843d3e2e0f399d645147433f9896b1ece41f062cff8c5273c1a"
        ),
        "retrieved_at": "2026-07-21T17:01:00Z",
        "license": "all-rights-reserved",
        "attribution": "Ten Brinke Group",
        "excerpt": (
            "The credential-free first-party project page embeds the numeric "
            "project marker; no Google page, tile, basemap, or geocoder result is "
            "used."
        ),
        "method": "authoritative_site_plan",
        "point": [23.90870178233002, 37.96626241294147],
        "uncertainty_m": 50,
        "facility_specific": True,
    },
    {
        "label": "ast",
        "predecessor": "curated-official-2026-07-21-ast-janciems-shell-fit-out.json",
        "evidence_key": "latvia-vzd-ast-janciems-address-point-assessed-2026-07-21",
        "kind": "government_record",
        "publisher": "Valsts zemes dienests",
        "source_family": "latvia_vzd_address_register",
        "source_url": (
            "https://geo-dpps.viss.gov.lv/api/DPPSPackage/client/"
            "Adresu_tel_418_k6gL2A/3d692785-0c95-44a8-816c-f2f91493c4ce?"
            "service=WFS&version=2.0.0&request=GetFeature&typeNames=ad%3AAddress&"
            "featureID=AD101873308"
        ),
        "title": "VZD address point AD101873308 for AST Jāņciems",
        "content_hash": (
            "bc27b4271cbfec3e1452f53897e199e0e9d075fd05691fa35e81d431a8e20f98"
        ),
        "retrieved_at": ASSESSMENT_RETRIEVED_AT,
        "license": "CC-BY-4.0",
        "attribution": "Valsts zemes dienests (State Land Service), CC BY 4.0",
        "excerpt": (
            "The current VZD address feature AD101873308 gives the address point "
            "for Dārzciema iela 86, Rīga, LV-1073, matching the first-party AST "
            "project address."
        ),
        "method": "authoritative_address_geocode",
        "point": [24.1814716538, 56.933100002],
        "uncertainty_m": 20,
        "facility_specific": True,
    },
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SiteCoordinateAssessmentV6Error(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SiteCoordinateAssessmentV6Error(f"{label} is invalid") from error
    if parsed.microsecond:
        raise SiteCoordinateAssessmentV6Error(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _pin(filename: Path, byte_count: int, digest: str, label: str) -> dict[str, Any]:
    if filename.is_symlink() or not filename.is_file():
        raise SiteCoordinateAssessmentV6Error(f"{label} is not an ordinary file")
    raw = filename.read_bytes()
    if (len(raw), _sha256(raw)) != (byte_count, digest):
        raise SiteCoordinateAssessmentV6Error(f"{label} drifted")
    return json.loads(raw)


def _verify_lineage_and_cohort() -> dict[str, dict[str, Any]]:
    definition = _pin(
        BASE_DEFINITION,
        BASE_DEFINITION_BYTES,
        BASE_DEFINITION_SHA256,
        "accepted v84 definition",
    )
    manifest = _pin(
        BASE_MANIFEST,
        BASE_MANIFEST_BYTES,
        BASE_MANIFEST_SHA256,
        "accepted v84 manifest",
    )
    if (
        manifest.get("recorded_at") != BASE_RECORDED_AT
        or tree_digest(BASE_MANIFEST.parent) != BASE_RELEASE_TREE_SHA256
    ):
        raise SiteCoordinateAssessmentV6Error("accepted v84 release closure drifted")

    source_artifacts = (
        (
            OCEANIA_ARTIFACT,
            OCEANIA_MANIFEST_BYTES,
            OCEANIA_MANIFEST_SHA256,
            OCEANIA_LOGICAL_TREE_SHA256,
            OCEANIA_PHYSICAL_TREE_SHA256,
            "Oceania source artifact",
        ),
        (
            CEE_ARTIFACT,
            CEE_MANIFEST_BYTES,
            CEE_MANIFEST_SHA256,
            CEE_LOGICAL_TREE_SHA256,
            CEE_PHYSICAL_TREE_SHA256,
            "CEE source artifact",
        ),
        (
            PRIOR_ARTIFACT,
            PRIOR_MANIFEST_BYTES,
            PRIOR_MANIFEST_SHA256,
            PRIOR_LOGICAL_TREE_SHA256,
            PRIOR_PHYSICAL_TREE_SHA256,
            "coordinate v5 artifact",
        ),
    )
    for root, byte_count, digest, logical, physical, label in source_artifacts:
        source_manifest = _pin(root / "manifest.json", byte_count, digest, label)
        if (
            source_manifest.get("tree_sha256") != logical
            or tree_digest(root) != physical
        ):
            raise SiteCoordinateAssessmentV6Error(f"{label} tree drifted")

    selected = {
        item["path"]: item["sha256"] for item in definition.get("curated_inputs", [])
    }
    documents: dict[str, dict[str, Any]] = {}
    for name, (byte_count, digest, _disposition) in COHORT.items():
        filename = ROOT / "sources" / name
        document = _pin(filename, byte_count, digest, f"v84 cohort {name}")
        if selected.get(f"sources/{name}") != digest:
            raise SiteCoordinateAssessmentV6Error(f"v84 did not select {name}")
        if document.get("schema_version") != "1.1":
            raise SiteCoordinateAssessmentV6Error(f"schema differs for {name}")
        if document["campus"].get("coordinates") is not None or document[
            "project"
        ].get("coordinates") is not None:
            raise SiteCoordinateAssessmentV6Error(
                f"coordinate predecessor was already located: {name}"
            )
        documents[name] = document
    return documents


def _evidence_metadata(specification: Mapping[str, Any]) -> dict[str, Any]:
    label = specification["label"]
    metadata: dict[str, Any] = {
        "content_hash_scope": "SHA-256 of the exact claim-bearing source body",
        "content_hash_verification": "fetched_bytes_sha256",
        "coordinate_assessment_artifact_id": ARTIFACT_ID,
        "coordinate_reference_system": "EPSG:4326",
        "coordinate_method": specification["method"],
        "facility_specific": specification["facility_specific"],
        "claim_guardrail": (
            "This evidence changes only coordinate/geometry snapshot fields and "
            "their evidence reference. It adds no identity, lifecycle, role, "
            "operating-model, workload, capacity, load, generation, consumption, "
            "annual-energy, PUE, satellite, aerial, or computer-vision claim."
        ),
        "raw_capture_guardrail": (
            "All-rights-reserved and government response bodies are hash-bound "
            "but are not copied into this repository artifact."
        ),
        "osm_guardrail": (
            "No OpenStreetMap-derived point, polygon, address, or identity bridge "
            "contributes to this successor."
        ),
    }
    if "point" in specification:
        longitude, latitude = specification["point"]
        metadata.update(
            {
                "stored_coordinate": {
                    "longitude": longitude,
                    "latitude": latitude,
                },
                "horizontal_uncertainty_m": specification["uncertainty_m"],
                "representative_point_scope": (
                    "Source-reported project, campus, or address representative "
                    "point; not a building footprint or inferred centroid."
                ),
            }
        )

    if label == "syd3":
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact 39134-byte NSW portal detail HTML body"
                ),
                "record_id": "nsw-major-projects:active-detail:SSD-41589232-Mod-2",
                "application_id": "SSD-41589232",
                "address": "51 Huntingwood Drive, Huntingwood NSW 2148",
                "coordinate_source": "detail_page_drupal_settings_geofield",
                "source_coordinate_order": "longitude_latitude",
                "source_crs": "EPSG:4326",
                "source_assessment_manifest": {
                    "bytes": 11_162,
                    "sha256": (
                        "650c9b6e194fea0dbe1ce28ecba0cb8f114b8ec7d6571a0ee1f31c41f0d660f2"
                    ),
                },
                "active_observations": {
                    "bytes": 91_250,
                    "sha256": (
                        "d07aa45efb296532ac1657a63c246dc0bc2f5a84d43100d57e89f54d46e856d6"
                    ),
                },
                "identity_bridge": {
                    "source_url": (
                        "https://www.bct.nsw.gov.au/sites/default/files/2024-12/"
                        "web-report-bcf-charge-quotes-to-december-2024.pdf"
                    ),
                    "bytes": 4_401_258,
                    "sha256": (
                        "1419ea102642f90b0acb419babe393b4a318ffb8a472ff298a167444df13d294"
                    ),
                    "row": "Q00260-004",
                },
            }
        )
    elif label in {"ec5", "ec6"}:
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact official SSD-10330 assessment PDF"
                ),
                "portal_entity_id": 2_366_206,
                "application_id": "SSD-10330",
                "portal_page": {
                    "bytes": 62_693,
                    "sha256": (
                        "db632cd91bb4be635913425e0ec3970ce7908ad08b1ececcc2c8ee32ba57cba5"
                    ),
                },
                "shared_campus_scope": (
                    "The same campus-level point is copied to the EC5 and EC6 "
                    "project rows. It does not distinguish either facility."
                ),
                "rejected_candidates": [
                    "MP08_0108 point belongs to a different approval",
                    "90 Peter Brock Drive belongs to DCI, not CDC EC5 or EC6",
                ],
            }
        )
    elif label == "ath04":
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact official ATH04 topographic-plan PDF"
                ),
                "source_crs": "EPSG:2100",
                "source_ring_order": "clockwise",
                "normalized_geojson_exterior_order": "counterclockwise",
                "transform": {
                    "library": "proj4@2.20.2",
                    "definition": (
                        "+proj=tmerc +lat_0=0 +lon_0=24 +k=0.9996 +x_0=500000 "
                        "+y_0=0 +ellps=GRS80 +towgs84=-199.87,74.79,246.62,"
                        "0,0,0,0 +units=m +no_defs +type=crs"
                    ),
                    "target": "EPSG:4326",
                },
                "source_native_rings_epsg_2100": {
                    "E31": E31_NATIVE,
                    "E26": E26_NATIVE,
                },
                "source_wgs84_rings_clockwise": {
                    "E31": E31_WGS84_SOURCE_ORDER,
                    "E26": E26_WGS84_SOURCE_ORDER,
                },
                "areas_square_metres": {
                    "E31_stated": 69_538.91,
                    "E26_stated": 14_998.50,
                    "E31_coordinate_derived": 69_552.7847,
                    "E26_coordinate_derived": 15_004.8134,
                },
                "supporting_documents": [
                    {
                        "kind": "Official Gazette",
                        "bytes": 2_295_956,
                        "sha256": (
                            "621c984495a9236e27d883e4fcd912ec8939a942ee19cd78c1fc61db564efceb"
                        ),
                    },
                    {
                        "kind": "strategic environmental assessment",
                        "source_url": (
                            "https://ependyseis.mindev.gov.gr/uploads/photos/"
                            "meleti-smpe-ati04.pdf"
                        ),
                        "bytes": 33_557_553,
                        "sha256": (
                            "8424a814028bc3257c4c1fb7be21380cf2087bdb84a42d786256fe3ea9e4a0a6"
                        ),
                    },
                ],
                "representative_point_intentionally_absent": True,
                "downstream_guard": {
                    "curated_bbox_midpoint_synthesis_must_be_suppressed": True,
                    "release_geometry_center_must_be_suppressed": True,
                    "import_in_v6_tests": False,
                    "reason": (
                        "The official record supplies geometry only and no "
                        "publisher-designated representative point."
                    ),
                },
            }
        )
    elif label == "tet":
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact 4773-byte current VZD WFS response"
                ),
                "vzd_feature_id": "AD107074603",
                "canonical_address": "Krasta iela 2 k-1, Salaspils",
                "address_status": "current",
                "native_epsg_3059": [523183.323, 302493.311],
                "source_epsg_4258_order": [56.8656322193, 24.3802635323],
                "address_bridge": "document /1 designator maps to register k-1",
                "rejected_candidate": "base address Krasta iela 2",
            }
        )
    elif label == "ten_brinke":
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact 35413-byte credential-free first-party "
                    "project-page body"
                ),
                "source_capture_tree_sha256": CEE_CAPTURE["tree_sha256"],
                "coordinate_derivation": "publisher_embedded_numeric_map_marker",
                "google_content_requested_or_captured": False,
                "google_basemap_or_geocoder_used": False,
            }
        )
    elif label == "ast":
        metadata.update(
            {
                "content_hash_scope": (
                    "SHA-256 of the exact 4521-byte current VZD WFS response"
                ),
                "vzd_feature_id": "AD101873308",
                "canonical_address": "Dārzciema iela 86, Rīga, LV-1073",
                "address_status": "current",
                "native_epsg_3059": [511043.784, 309953.622],
                "source_epsg_4258_order": [56.933100002, 24.1814716538],
            }
        )
    return metadata


def _evidence(specification: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "key": specification["evidence_key"],
        "kind": specification["kind"],
        "title": specification["title"],
        "source_url": specification["source_url"],
        "publisher": specification["publisher"],
        "source_family": specification["source_family"],
        "published_at": None,
        "retrieved_at": specification["retrieved_at"],
        "license": specification["license"],
        "attribution": specification["attribution"],
        "excerpt": specification["excerpt"],
        "content_hash": specification["content_hash"],
        "metadata": _evidence_metadata(specification),
    }


def _successor(
    predecessor: Mapping[str, Any], specification: Mapping[str, Any]
) -> dict[str, Any]:
    successor = copy.deepcopy(predecessor)
    successor["evidence"].append(_evidence(specification))
    if "point" in specification:
        longitude, latitude = specification["point"]
        coordinates = {"latitude": latitude, "longitude": longitude}
        geometry = {"type": "Point", "coordinates": [longitude, latitude]}
        for entity_name in ("campus", "project"):
            entity = successor[entity_name]
            entity["coordinates"] = copy.deepcopy(coordinates)
            entity["geometry"] = copy.deepcopy(geometry)
            entity["evidence_key"] = specification["evidence_key"]
            entity["method"] = specification["method"]
    else:
        successor["campus"]["geometry"] = copy.deepcopy(
            specification["campus_geometry"]
        )
        successor["project"]["geometry"] = copy.deepcopy(
            specification["project_geometry"]
        )
        for entity_name in ("campus", "project"):
            entity = successor[entity_name]
            entity["evidence_key"] = specification["evidence_key"]
            entity["method"] = specification["method"]
    return successor


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    specification: Mapping[str, Any],
) -> None:
    if predecessor.get("schema_version") != "1.1" or successor.get(
        "schema_version"
    ) != "1.1":
        raise SiteCoordinateAssessmentV6Error("successor schema differs")
    if set(predecessor) != set(successor):
        raise SiteCoordinateAssessmentV6Error("successor root keys differ")
    if successor["evidence"][:-1] != predecessor["evidence"] or len(
        successor["evidence"]
    ) != len(predecessor["evidence"]) + 1:
        raise SiteCoordinateAssessmentV6Error("evidence append differs")
    added = successor["evidence"][-1]
    if (
        added.get("key") != specification["evidence_key"]
        or added.get("kind") != specification["kind"]
    ):
        raise SiteCoordinateAssessmentV6Error("added evidence differs")

    restored = copy.deepcopy(successor)
    restored["evidence"] = copy.deepcopy(predecessor["evidence"])
    expected_changed = (
        {"coordinates", "geometry", "evidence_key", "method"}
        if "point" in specification
        else {"geometry", "evidence_key", "method"}
    )
    for entity_name in ("campus", "project"):
        before = predecessor[entity_name]
        after = successor[entity_name]
        changed = {
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        if changed != expected_changed:
            raise SiteCoordinateAssessmentV6Error(
                f"coordinate-only delta differs for {entity_name}"
            )
        for key in changed:
            restored[entity_name][key] = copy.deepcopy(before[key])
    if restored != predecessor:
        raise SiteCoordinateAssessmentV6Error("successor gained a non-coordinate claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section]:
            raise SiteCoordinateAssessmentV6Error(f"successor changed {section}")
    if specification["label"] == "ath04" and any(
        successor[entity]["coordinates"] is not None for entity in ("campus", "project")
    ):
        raise SiteCoordinateAssessmentV6Error("ATH04 acquired a synthetic point")


def _successor_name(predecessor: str) -> str:
    return predecessor.removesuffix(".json") + "-coordinate-v6.json"


REVIEW_AND_EXCLUSIONS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-21-cdc-marsden-park-current-build.json": {
        "disposition": "review_two_official_lot_points_no_multipoint_schema",
        "reason": (
            "The NSW FeatureServer returns two facility-relevant lot points. "
            "Schema 1.1 has no MultiPoint geometry, and neither a centroid nor one "
            "arbitrarily selected lot point is accepted."
        ),
        "candidate_points": [
            {
                "address": "113 Northbourne Drive, Marsden Park",
                "lot": "Lot 11",
                "feature_guid": "{f516a473-f348-447a-95ce-5b1c09391068}",
                "longitude": 150.83674574995896,
                "latitude": -33.72446034010594,
            },
            {
                "address": "105 Northbourne Drive, Marsden Park",
                "lot": "Lot 10",
                "feature_guid": "{a47cbd56-a6e0-4861-807d-22dd21f8b548}",
                "longitude": 150.83660024713737,
                "latitude": -33.72260905358787,
            },
        ],
        "source_response_sha256": (
            "dc0d60ae74ad23e33def28ba49c3ac2ea1dced0e0a736cd8d4c064c74ab58040"
        ),
    },
    "curated-official-2026-07-21-cdc-maddington-current-build.json": {
        "disposition": "review_no_facility_coordinate_bridge",
        "reason": (
            "Captured official material does not bridge a candidate coordinate "
            "to the CDC Maddington facility."
        ),
    },
    "curated-official-2026-07-21-cdc-brooklyn-remaining-facilities-current-build.json": {
        "disposition": "review_aggregate_unnamed_facilities",
        "reason": (
            "The project row aggregates unnamed remaining facilities, so no "
            "single facility point or footprint can be assigned."
        ),
    },
    "curated-official-2026-07-21-serbia-state-dc-kragujevac-modules-3-4-operational.json": {
        "disposition": "review_operational_not_current_construction",
        "reason": (
            "The row records operational modules, not a current construction "
            "project in the coordinate-assessment target scope."
        ),
    },
    "curated-official-2026-07-21-cdc-laverton-current-build.json": {
        "disposition": "ineligible_locality_only",
        "reason": (
            "Only locality-level evidence is available; no facility-specific "
            "parcel, address point, or site geometry is accepted."
        ),
    },
    "curated-official-2026-07-21-gta-gu3-alupang-operational-closure.json": {
        "disposition": "ineligible_operational_closure",
        "reason": (
            "The row is an operational-closure record and is outside the current "
            "construction coordinate cohort."
        ),
    },
}


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "raw_source_bodies_redistributed": False,
        "repository_contains_new_raw_capture": False,
        "source_artifact_inputs": [
            {
                "artifact_id": OCEANIA_ARTIFACT.name,
                "manifest_bytes": OCEANIA_MANIFEST_BYTES,
                "manifest_sha256": OCEANIA_MANIFEST_SHA256,
                "logical_tree_sha256": OCEANIA_LOGICAL_TREE_SHA256,
                "physical_tree_sha256": OCEANIA_PHYSICAL_TREE_SHA256,
                "private_capture": OCEANIA_CAPTURE,
            },
            {
                "artifact_id": CEE_ARTIFACT.name,
                "manifest_bytes": CEE_MANIFEST_BYTES,
                "manifest_sha256": CEE_MANIFEST_SHA256,
                "logical_tree_sha256": CEE_LOGICAL_TREE_SHA256,
                "physical_tree_sha256": CEE_PHYSICAL_TREE_SHA256,
                "private_capture": CEE_CAPTURE,
            },
        ],
        "claim_bearing_sources": [
            {
                "source_id": "nsw_syd3_detail",
                "url": ACCEPTED[0]["source_url"],
                "bytes": 39_134,
                "sha256": ACCEPTED[0]["content_hash"],
                "coordinate_scope": "facility-specific portal geofield Point",
            },
            {
                "source_id": "nsw_syd3_bcf_identity_bridge",
                "url": (
                    "https://www.bct.nsw.gov.au/sites/default/files/2024-12/"
                    "web-report-bcf-charge-quotes-to-december-2024.pdf"
                ),
                "bytes": 4_401_258,
                "sha256": (
                    "1419ea102642f90b0acb419babe393b4a318ffb8a472ff298a167444df13d294"
                ),
                "coordinate_scope": "SSD/address/AirTrunk identity bridge only",
            },
            {
                "source_id": "nsw_cdc_roberts_road_page",
                "url": ACCEPTED[1]["source_url"],
                "bytes": 62_693,
                "sha256": (
                    "db632cd91bb4be635913425e0ec3970ce7908ad08b1ececcc2c8ee32ba57cba5"
                ),
                "coordinate_scope": "shared campus, not EC5/EC6 facility-specific",
            },
            {
                "source_id": "nsw_cdc_ssd_10330_assessment",
                "url": ACCEPTED[1]["source_url"],
                "bytes": None,
                "sha256": ACCEPTED[1]["content_hash"],
                "coordinate_scope": "shared campus representative point",
            },
            {
                "source_id": "greece_ath04_topographic_plan",
                "url": ACCEPTED[3]["source_url"],
                "bytes": None,
                "sha256": ACCEPTED[3]["content_hash"],
                "coordinate_scope": "E31 project polygon and E31+E26 campus",
            },
            {
                "source_id": "latvia_vzd_tet_dc7",
                "url": ACCEPTED[4]["source_url"],
                "bytes": 4_773,
                "sha256": ACCEPTED[4]["content_hash"],
                "coordinate_scope": "current official address point",
            },
            {
                "source_id": "ten_brinke_spata_page",
                "url": ACCEPTED[5]["source_url"],
                "bytes": 35_413,
                "sha256": ACCEPTED[5]["content_hash"],
                "coordinate_scope": "first-party embedded numeric project marker",
            },
            {
                "source_id": "latvia_vzd_ast_janciems",
                "url": ACCEPTED[6]["source_url"],
                "bytes": 4_521,
                "sha256": ACCEPTED[6]["content_hash"],
                "coordinate_scope": "current official address point",
            },
        ],
        "rights_guardrail": (
            "Only source URLs, exact hashes, byte counts where known, and compact "
            "factual coordinate extractions are released. No source body, map "
            "tile, publisher image, satellite image, or aerial image is copied."
        ),
    }


def build_payloads(recorded_at: str) -> dict[str, bytes]:
    """Reproduce every v6 artifact byte without network access."""

    recorded = _parse_utc(recorded_at, "v6 recorded_at")
    if recorded < _parse_utc(ASSESSMENT_RETRIEVED_AT, "assessment retrieved_at"):
        raise SiteCoordinateAssessmentV6Error("recorded_at precedes assessment")
    documents = _verify_lineage_and_cohort()

    successors: dict[str, bytes] = {}
    successor_rows: dict[str, dict[str, Any]] = {}
    observation_rows: list[dict[str, Any]] = []
    for specification in ACCEPTED:
        label = specification["label"]
        predecessor_name = specification["predecessor"]
        predecessor = documents[predecessor_name]
        successor = _successor(predecessor, specification)
        _validate_successor(predecessor, successor, specification)
        relative = (
            "normalized-successors/" + _successor_name(predecessor_name)
        )
        raw = _canonical_json(successor)
        successors[relative] = raw
        successor_rows[label] = {
            "path": relative,
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "predecessor": f"sources/{predecessor_name}",
            "predecessor_sha256": COHORT[predecessor_name][1],
            "campus_key": predecessor["campus"]["stable_key"],
            "project_key": predecessor["project"]["stable_key"],
            "added_evidence_key": specification["evidence_key"],
            "added_evidence_kind": specification["kind"],
            "method": specification["method"],
            "facility_specific": specification["facility_specific"],
            "changed_entities": ["campus", "project"],
            "changed_snapshot_fields": (
                ["coordinates", "geometry", "evidence_key", "method"]
                if "point" in specification
                else ["geometry", "evidence_key", "method"]
            ),
        }
        observation: dict[str, Any] = {
            "predecessor": f"sources/{predecessor_name}",
            "predecessor_bytes": COHORT[predecessor_name][0],
            "predecessor_sha256": COHORT[predecessor_name][1],
            "campus_key": predecessor["campus"]["stable_key"],
            "project_key": predecessor["project"]["stable_key"],
            "disposition": COHORT[predecessor_name][2],
            "successor": relative,
            "facility_specific": specification["facility_specific"],
        }
        if "point" in specification:
            longitude, latitude = specification["point"]
            observation["coordinate"] = {
                "longitude": longitude,
                "latitude": latitude,
                "horizontal_uncertainty_m": specification["uncertainty_m"],
            }
        else:
            observation["coordinate"] = None
            observation["geometry"] = {
                "campus_type": "MultiPolygon",
                "project_type": "Polygon",
                "campus_parcels": ["E31", "E26"],
                "project_parcels": ["E31"],
                "representative_point_intentionally_absent": True,
            }
        observation_rows.append(observation)

    nonaccepted_rows: list[dict[str, Any]] = []
    for predecessor_name, assessment in REVIEW_AND_EXCLUSIONS.items():
        predecessor = documents[predecessor_name]
        row = {
            "predecessor": f"sources/{predecessor_name}",
            "predecessor_bytes": COHORT[predecessor_name][0],
            "predecessor_sha256": COHORT[predecessor_name][1],
            "campus_key": predecessor["campus"]["stable_key"],
            "project_key": predecessor["project"]["stable_key"],
            "successor": None,
            **copy.deepcopy(assessment),
        }
        nonaccepted_rows.append(row)
        observation_rows.append(row)

    coordinate_observations = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "assessment_scope": {
            "candidate_project_rows": 13,
            "accepted_successors": 7,
            "accepted_project_locations": 6,
            "accepted_campus_identities": 6,
            "accepted_point_successors": 6,
            "accepted_geometry_only_successors": 1,
            "review_or_ineligible_rows": 6,
        },
        "accepted_order": [specification["label"] for specification in ACCEPTED],
        "rows": observation_rows,
    }

    publication_contract = {
        "recorded_at": recorded_at,
        "all_private_stage_birth_and_mtime_not_later_than_recorded_at": True,
        "final_paths_absent_until_recorded_at_live": True,
        "frozen_before_promotion": True,
        "atomic_no_replace_promotion": True,
        "final_root_ctime_not_earlier_than_recorded_at": True,
        "identity_safe_cleanup": True,
        "existing_identical_replay_only": True,
    }
    disposition = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "integration": "none",
        "accepted_seed_definition": None,
        "non_coordinate_claims_added": [],
        "accepted": {
            "successors": successor_rows,
            "project_rows": 7,
            "campus_identities": 6,
            "policy": (
                "Only source-reported official or first-party coordinates with a "
                "direct facility/campus identity bridge create successors."
            ),
        },
        "not_accepted": {
            "rows": nonaccepted_rows,
            "policy": (
                "No locality centroid, polygon bbox midpoint, arbitrary point "
                "selection, OSM point, or cross-operator address is accepted."
            ),
        },
        "ath04_geometry_only_guard": {
            "coordinates_remain_null": True,
            "representative_point_published": False,
            "curated_bbox_midpoint_synthesis_must_be_suppressed": True,
            "release_geometry_center_must_be_suppressed": True,
            "adapter_import_deferred": True,
        },
        "source_boundaries": {
            "osm_inputs_consumed": [],
            "google_content_captured_or_redistributed": False,
            "raw_official_or_company_bodies_redistributed": False,
            "satellite_or_cv_claims_added": False,
        },
        "lineage": {
            "base_definition": {
                "path": "sources/open-seed-2026-07-21-v84.json",
                "bytes": BASE_DEFINITION_BYTES,
                "sha256": BASE_DEFINITION_SHA256,
            },
            "base_release": {
                "path": "releases/2026-07-21-open-seed-v84",
                "recorded_at": BASE_RECORDED_AT,
                "manifest_bytes": BASE_MANIFEST_BYTES,
                "manifest_sha256": BASE_MANIFEST_SHA256,
                "physical_tree_sha256": BASE_RELEASE_TREE_SHA256,
            },
            "source_artifacts": [
                {
                    "path": f"source_artifacts/{OCEANIA_ARTIFACT.name}",
                    "manifest_sha256": OCEANIA_MANIFEST_SHA256,
                    "physical_tree_sha256": OCEANIA_PHYSICAL_TREE_SHA256,
                    "preserved_unchanged": True,
                },
                {
                    "path": f"source_artifacts/{CEE_ARTIFACT.name}",
                    "manifest_sha256": CEE_MANIFEST_SHA256,
                    "physical_tree_sha256": CEE_PHYSICAL_TREE_SHA256,
                    "preserved_unchanged": True,
                },
            ],
            "prior_coordinate_artifact": {
                "path": f"source_artifacts/{PRIOR_ARTIFACT.name}",
                "manifest_sha256": PRIOR_MANIFEST_SHA256,
                "physical_tree_sha256": PRIOR_PHYSICAL_TREE_SHA256,
                "preserved_unchanged": True,
            },
        },
        "publication_contract": publication_contract,
    }

    readme = """# Site coordinate assessment 2026-07-21 v6

This immutable, non-integrated overlay assesses thirteen accepted-v84 project
rows. It publishes seven coordinate-only schema-1.1 successors for six campus
identities: six Point successors and one geometry-only ATH04 successor.

- AirTrunk SYD3 uses the NSW portal's EPSG:4326 Drupal geofield point, bridged
  to SSD-41589232 and 51 Huntingwood Drive through the official BCF register.
- CDC EC5 and EC6 each receive the same SSD-10330 Roberts Road campus point.
  The point is explicitly not facility-specific and does not distinguish EC5
  from EC6.
- Microsoft ATH04 retains `coordinates: null`. Its campus receives the official
  E31+E26 MultiPolygon and its project receives the E31 Polygon. Source-order
  EPSG:2100 and transformed WGS84 rings are preserved as evidence; only the
  normalized GeoJSON exterior order is reversed. Current curated/release code
  synthesizes polygon centers, so ATH04 import is deliberately deferred and
  both midpoint paths are marked for suppression.
- Tet DC7 and AST Jāņciems use current official VZD address-register points.
- Ten Brinke Spata uses the numeric marker embedded in the captured first-party
  project page. No Google page, tile, basemap, or geocoder result is used.

Marsden Park remains review-only because the official response supplies two lot
points and schema 1.1 has no MultiPoint. Maddington, Brooklyn, Serbia, Laverton,
and GU3 retain explicit no-successor dispositions. No locality centroid,
polygon bbox midpoint, arbitrary lot selection, cross-operator point, or OSM
point is accepted.

Every successor preserves identity, name, country, address, roles, confidence,
as-of date, lifecycle, operating model, workload, and capacity claims. Each
appends exactly one evidence record and changes only coordinate/geometry
snapshot fields and their evidence reference. Raw claim-bearing bodies are not
redistributed; the inventory publishes exact hashes and compact factual
extractions only.

Publication uses a future-dated private stage. Every staged inode is frozen and
must be born and modified no later than `recorded_at`; the final path remains
absent until that instant is live, then atomic no-replace promotion establishes
a final-root ctime at or after publication.
""".encode("utf-8")

    payloads = {
        "README.md": readme,
        "coordinate-observations.json": _canonical_json(coordinate_observations),
        "disposition.json": _canonical_json(disposition),
        "retrieval-inventory.json": _canonical_json(
            _retrieval_inventory(recorded_at)
        ),
        **successors,
    }
    files = [
        {"path": relative, "bytes": len(raw), "sha256": _sha256(raw)}
        for relative, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.2",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "recorded_at": recorded_at,
        "integration": "none",
        "publication_contract_version": 6,
        "publication": publication_contract,
        "files": files,
        "tree_sha256": _sha256(_canonical_json(files)),
    }
    manifest_raw = _canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    return payloads


def _expected_directories(payloads: Mapping[str, bytes]) -> set[str]:
    directories = {"."}
    for relative in payloads:
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _inspect_exact(root: Path, payloads: Mapping[str, bytes], *, frozen: bool) -> None:
    if root.is_symlink() or not root.is_dir():
        raise SiteCoordinateAssessmentV6Error(
            "artifact root must be an ordinary directory"
        )
    files = {
        candidate.relative_to(root).as_posix(): candidate
        for candidate in root.rglob("*")
        if candidate.is_file()
    }
    if set(files) != set(payloads):
        raise SiteCoordinateAssessmentV6Error("artifact file set differs")
    for relative, raw in payloads.items():
        candidate = files[relative]
        if candidate.is_symlink() or candidate.read_bytes() != raw:
            raise SiteCoordinateAssessmentV6Error(
                f"artifact payload differs: {relative}"
            )
        if frozen and stat.S_IMODE(candidate.stat().st_mode) != 0o444:
            raise SiteCoordinateAssessmentV6Error(
                f"artifact file is not frozen: {relative}"
            )
    directories = {
        ".": root,
        **{
            candidate.relative_to(root).as_posix(): candidate
            for candidate in root.rglob("*")
            if candidate.is_dir()
        },
    }
    if set(directories) != _expected_directories(payloads):
        raise SiteCoordinateAssessmentV6Error("artifact directory set differs")
    if frozen and any(
        candidate.is_symlink() or stat.S_IMODE(candidate.stat().st_mode) != 0o555
        for candidate in directories.values()
    ):
        raise SiteCoordinateAssessmentV6Error("artifact directory is not frozen")


def _path_identities(root: Path) -> dict[str, tuple[int, int]]:
    candidates = [
        root,
        *sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix()),
    ]
    return {
        "." if candidate == root else candidate.relative_to(root).as_posix(): (
            candidate.stat(follow_symlinks=False).st_dev,
            candidate.stat(follow_symlinks=False).st_ino,
        )
        for candidate in candidates
    }


def _assert_identities(root: Path, expected: Mapping[str, tuple[int, int]]) -> None:
    if _path_identities(root) != dict(expected):
        raise SiteCoordinateAssessmentV6Error("private stage identity changed")


def _discard_stage(root: Path, identities: Mapping[str, tuple[int, int]]) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_identities(root, identities)
    for candidate in sorted(
        root.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        candidate.chmod(0o700 if candidate.is_dir() else 0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


def _fsync(filename: Path) -> None:
    descriptor = os.open(filename, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_stage(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, raw in payloads.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for directory in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_dir()),
        key=lambda candidate: len(candidate.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
        _fsync(directory)
    for filename in (
        candidate for candidate in root.rglob("*") if candidate.is_file()
    ):
        filename.chmod(0o444)
        _fsync(filename)
    root.chmod(0o555)
    _fsync(root)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    for candidate in (root, *root.rglob("*")):
        metadata = candidate.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise SiteCoordinateAssessmentV6Error(
                f"private stage post-dates recorded_at: {candidate.name}"
            )


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(source: Path, destination: Path) -> None:
    try:
        promote_noreplace(source, destination)
    except SystemExit as error:
        raise SiteCoordinateAssessmentV6Error(str(error)) from error


def _verify_live_artifact(root: Path, payloads: Mapping[str, bytes]) -> None:
    _inspect_exact(root, payloads, frozen=True)
    manifest = json.loads(payloads["manifest.json"])
    target = _parse_utc(manifest["recorded_at"], "v6 recorded_at")
    if datetime.now(UTC) < target:
        raise SiteCoordinateAssessmentV6Error("v6 recorded_at is not live")
    if root.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
        raise SiteCoordinateAssessmentV6Error("final root ctime predates recorded_at")


def publish(recorded_at: str | None = None) -> dict[str, Any]:
    """Publish v6 once, or prove an existing artifact is byte-identical."""

    if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
        manifest = json.loads((ARTIFACT_DIR / "manifest.json").read_text())
        existing_recorded_at = manifest["recorded_at"]
        if recorded_at is not None and recorded_at != existing_recorded_at:
            raise SiteCoordinateAssessmentV6Error("existing recorded_at differs")
        payloads = build_payloads(existing_recorded_at)
        _verify_live_artifact(ARTIFACT_DIR, payloads)
        return {
            "artifact": str(ARTIFACT_DIR),
            "manifest_sha256": _sha256(payloads["manifest.json"]),
            "recorded_at": existing_recorded_at,
            "status": "existing-identical",
        }

    target = (
        _parse_utc(recorded_at, "v6 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=20)
    )
    if datetime.now(UTC) >= target:
        raise SiteCoordinateAssessmentV6Error(
            "recorded_at must be future before private staging starts"
        )
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    payloads = build_payloads(recorded_at)
    PUBLICATION_ROOT.mkdir(parents=True, exist_ok=True)

    lock_descriptor: int | None = None
    lock_identity: tuple[int, int] | None = None
    try:
        lock_descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        os.write(lock_descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(lock_descriptor)
        lock_metadata = os.fstat(lock_descriptor)
        lock_identity = (lock_metadata.st_dev, lock_metadata.st_ino)
    except FileExistsError as error:
        raise SiteCoordinateAssessmentV6Error(
            "active v6 publication lock exists"
        ) from error

    stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=PUBLICATION_ROOT)
    )
    stage_identities: dict[str, tuple[int, int]] | None = None
    published = False
    try:
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV6Error("initial final path collision")
        _write_stage(stage, payloads)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        stage_identities = _path_identities(stage)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV6Error("pre-wait final path collision")
        _wait_until(target)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise SiteCoordinateAssessmentV6Error("late final path collision")
        _assert_identities(stage, stage_identities)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        _promote_noreplace(stage, ARTIFACT_DIR)
        published = True
        _verify_live_artifact(ARTIFACT_DIR, payloads)
    finally:
        if not published and stage.exists() and stage_identities is not None:
            _discard_stage(stage, stage_identities)
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if lock_identity is not None:
            try:
                metadata = PUBLICATION_LOCK.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or (metadata.st_dev, metadata.st_ino) != lock_identity
                ):
                    raise SiteCoordinateAssessmentV6Error(
                        "refusing substituted publication-lock cleanup"
                    )
                PUBLICATION_LOCK.unlink()
    return {
        "artifact": str(ARTIFACT_DIR),
        "manifest_sha256": _sha256(payloads["manifest.json"]),
        "recorded_at": recorded_at,
        "status": "published",
    }


def main() -> int:
    print(json.dumps(publish(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
