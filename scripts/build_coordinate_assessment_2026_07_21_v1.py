from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "sources"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v1"
ARTIFACT_DIR = ROOT / "source_artifacts" / ARTIFACT_ID
AS_OF_DATE = "2026-07-21"

COHORT: dict[str, tuple[int, str]] = {
    "curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json": (
        6_583,
        "dc887d47d91abbd7e53da238414cf387263569cded4079a0db04f3881c4c2b56",
    ),
    "curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json": (
        6_687,
        "154ea1798c6926ac48d2528f0e2dbe5fd9651fa2b0f547b01e0e364acb13cb95",
    ),
    "curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json": (
        7_048,
        "0e976c4fd1e47bdd60495bbb1b9d98c0d9fc76b15d0aa7450b58088203a01b8f",
    ),
    "curated-official-2026-07-21-harch-dakhla-groundbreaking.json": (
        6_882,
        "15fd52022e98268ff7911dd6a013e5a22d0d6eeea5da411c670b271dbf44712e",
    ),
    "curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json": (
        5_334,
        "2ff597a72913f8650f7c4bfad476388972c087f4a92bb557900ab187ce56d5f5",
    ),
    "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json": (
        6_032,
        "aaf91ac612720e5aaaf66fcc13a5061701b4f95ee5cd4499485b347f9a3d314c",
    ),
    "curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json": (
        5_998,
        "d87b556c1dd1aa9f979eaf37dd4d432b8f90884564e08cc8c32f8f619df3724b",
    ),
    "curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json": (
        10_805,
        "1b43db6573bac2d62848abd8775a9542ca46e282a7057be7afc1353293c65763",
    ),
    "curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json": (
        10_968,
        "7858e23a565879feb9e5fd4254b9f793809735e5fdd3b96717bfb77f3f3ddc14",
    ),
    "curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json": (
        10_971,
        "3c1d13af526ff67b54af365252d25639352cca6608d6ca4e76a2f69a4b81624c",
    ),
    "curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json": (
        6_033,
        "5d8ffb54fbf33f9eead89b21f1d69f148f8f69ed1047a6adc8a160e24801a23c",
    ),
    "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json": (
        5_666,
        "1894b5625adfa95f03a4a3ba981fa0a5e28010ef1cfa0fe1e7ba858e9a877699",
    ),
    "curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json": (
        5_948,
        "04c1747343928095b9c2901c6ed95717766e8c6abce3e480d1157959791ab8c1",
    ),
}

SIMBIO_ENDPOINT = "https://simbio.mma.gob.cl/DPA/GetSEIA?Codigo=13"
SIMBIO_CONTEXT = "https://simbio.mma.gob.cl/DPA/DetailsRegion/12"
FORTALEZA_SITE_PLAN = (
    "https://urbanismoemeioambiente.fortaleza.ce.gov.br/images/"
    "urbanismo-e-meio-ambiente/infocidade/cppd/"
    "PROJETO_ARQUITETONICO_FL01-02.pdf"
)

FORTALEZA_RING = [
    [-38.458162, -3.753499],
    [-38.459020, -3.753223],
    [-38.457840, -3.749518],
    [-38.456983, -3.749794],
    [-38.458162, -3.753499],
]

RESOLVED: dict[str, dict[str, Any]] = {
    "lampa": {
        "predecessor": (
            "curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-sscllp01-lampa-current-build-"
            "coordinate-v1.json"
        ),
        "campus_key": "curated:scala-lampa-campus",
        "project_key": "curated:scala-lampa-campus:sscllp01",
        "coordinates": {"latitude": -33.29298, "longitude": -70.73915},
        "campus_geometry": {
            "type": "Point",
            "coordinates": [-70.73915, -33.29298],
        },
        "project_geometry": {
            "type": "Point",
            "coordinates": [-70.73915, -33.29298],
        },
        "evidence_key": (
            "chile-mma-simbio-scala-lampa-point-2152920300-captured-2026-07-21"
        ),
        "method": "authoritative_site_plan",
        "geometry_semantics": "official_environmental_review_representative_point",
        "stored_decimal_places": 5,
        "horizontal_uncertainty_m": 50,
        "source_decimal_text": {
            "x": "-70.739149706490736",
            "y": "-33.292981624952226",
        },
        "expediente_id": 2_152_920_300,
        "project_name_as_reported": "SCALA DATA CENTER CAMPUS",
        "feature_canonical_sha256": (
            "dcb75ca391d2c907b52e8951b7c31fb69028817ed72ce3d1f31f32a1fd4c460b"
        ),
    },
    "huechuraba": {
        "predecessor": (
            "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build-"
            "coordinate-v1.json"
        ),
        "campus_key": "curated:scala-huechuraba-campus",
        "project_key": "curated:scala-huechuraba-campus:ssclhb01",
        "coordinates": {"latitude": -33.36636, "longitude": -70.67394},
        "campus_geometry": {
            "type": "Point",
            "coordinates": [-70.67394, -33.36636],
        },
        "project_geometry": {
            "type": "Point",
            "coordinates": [-70.67394, -33.36636],
        },
        "evidence_key": (
            "chile-mma-simbio-scala-huechuraba-point-2162968448-captured-"
            "2026-07-21"
        ),
        "method": "authoritative_site_plan",
        "geometry_semantics": "official_environmental_review_representative_point",
        "stored_decimal_places": 5,
        "horizontal_uncertainty_m": 50,
        "source_decimal_text": {
            "x": "-70.673941427872251",
            "y": "-33.366357816565355",
        },
        "expediente_id": 2_162_968_448,
        "project_name_as_reported": (
            "Ampliación Data Center Campus Scala Huechuraba"
        ),
        "feature_canonical_sha256": (
            "dd22406541de3c67b063d653173d07b3e1658c91fa41d5b1e5548738b69daedb"
        ),
    },
    "fortaleza": {
        "predecessor": (
            "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build-"
            "coordinate-v1.json"
        ),
        "campus_key": "curated:scala-praia-do-futuro-campus",
        "project_key": "curated:scala-praia-do-futuro-campus:sforpf01",
        "coordinates": {"latitude": -3.751509, "longitude": -38.458001},
        "campus_geometry": {
            "type": "Point",
            "coordinates": [-38.458001, -3.751509],
        },
        "project_geometry": {
            "type": "Polygon",
            "coordinates": [FORTALEZA_RING],
        },
        "evidence_key": (
            "fortaleza-seuma-sforpf01-survey-plan-captured-2026-07-21"
        ),
        "method": "authoritative_site_plan",
        "geometry_semantics": "official_surveyed_project_boundary",
        "stored_decimal_places": 6,
        "horizontal_uncertainty_m": 5,
    },
}

UNRESOLVED = [
    {
        "campus_key": "curated:azerbaijan-undisclosed-new-data-center-site",
        "project_keys": [
            "curated:azerbaijan-undisclosed-new-data-center-site:unnamed-new-data-center"
        ],
        "reason": "official_source_withholds_city_district_address_and_parcel",
        "guardrail": (
            "No coordinate is assigned. The National Data Center or an Azerbaijan "
            "locality centroid is not transferred without a primary site-identity link."
        ),
    },
    {
        "campus_key": "curated:firebird-ai-center-hrazdan-site",
        "project_keys": [
            "curated:firebird-ai-center-hrazdan-site:current-center-development"
        ],
        "reason": "official_source_only_reports_near_hrazdan_without_site_identifier",
        "guardrail": (
            "No Hrazdan city or power-station centroid is used; the official progress "
            "release gives area but no address, cadastral parcel, or boundary."
        ),
    },
    {
        "campus_key": "curated:green-mountain-fra-mainz-campus",
        "project_keys": [
            "curated:green-mountain-fra-mainz-campus:current-three-building-development"
        ],
        "reason": "no_deterministic_official_bridge_to_exact_osm_construction_polygon",
        "guardrail": (
            "Official sources tie the project to Kraftwerkallee 1, the KMW site, and "
            "parcel 20/67. The exact OSM construction polygon is not promoted because "
            "the project-to-polygon identity remains inferential."
        ),
    },
    {
        "campus_key": "curated:harch-intelligence-dakhla-campus",
        "project_keys": [
            "curated:harch-intelligence-dakhla-campus:initial-development"
        ],
        "reason": "operator_reports_50_hectare_dakhla_site_without_parcel_or_address",
        "guardrail": "No Dakhla locality, Igoudar program, or unrelated land centroid is used.",
    },
    {
        "campus_key": "curated:scala-smextp02-tepotzotlan-data-center",
        "project_keys": [
            "curated:scala-smextp02-tepotzotlan-data-center:smextp02"
        ],
        "reason": "no_primary_site_specific_smextp02_address_or_parcel",
        "guardrail": (
            "The separately identified SMEXTP01 coordinate and address are not "
            "transferred to SMEXTP02; unlicensed third-party address listings are excluded."
        ),
    },
    {
        "campus_key": "curated:scala-tambore-campus",
        "project_keys": [
            "curated:scala-tambore-campus:sgrutb07",
            "curated:scala-tambore-campus:sgrutb09",
            "curated:scala-tambore-campus:sgrutb10",
            "curated:scala-tambore-campus:sgrutb11",
        ],
        "reason": "official_addresses_do_not_disambiguate_the_four_project_site_cluster",
        "guardrail": (
            "Municipal records tie Scala to Avenida Ceci and nearby works, but the "
            "address complex is shared and OSM labels conflict. No street midpoint, "
            "substation point, or unnamed data-center footprint is promoted."
        ),
    },
    {
        "campus_key": "curated:scala-zona-franca-bogota-campus",
        "project_keys": [
            "curated:scala-zona-franca-bogota-campus:sbogzb01"
        ],
        "reason": "no_official_or_open_site_specific_parcel_for_sbogzb01",
        "guardrail": (
            "Zona Franca Bogota is too broad for a site point; proprietary directory "
            "coordinates and other operators' addresses are excluded."
        ),
    },
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"refusing to overwrite non-identical file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _load_source(name: str) -> dict[str, Any]:
    expected_bytes, expected_sha256 = COHORT[name]
    path = SOURCE_DIR / name
    raw = path.read_bytes()
    if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
        raise RuntimeError(f"direct curated-source pin mismatch: {path}")
    return json.loads(raw)


def _simbio_evidence(spec: dict[str, Any]) -> dict[str, Any]:
    expediente_id = spec["expediente_id"]
    return {
        "key": spec["evidence_key"],
        "kind": "government_record",
        "title": (
            "Chile MMA SIMBIO SEIA representative point for expediente "
            f"{expediente_id}"
        ),
        "source_url": SIMBIO_ENDPOINT,
        "publisher": "Ministerio del Medio Ambiente de Chile - SIMBIO",
        "source_family": "chile_mma_simbio_seia_project_points",
        "published_at": None,
        "retrieved_at": "2026-07-21T17:05:51Z",
        "license": "no-use-restriction-stated-for-reference-cartography",
        "attribution": "Ministerio del Medio Ambiente de Chile - SIMBIO",
        "excerpt": (
            f"The official Region 13 SEIA feature identifies expediente {expediente_id} "
            f"as {spec['project_name_as_reported']} and publishes an EPSG:4326 "
            "representative point."
        ),
        "content_hash": (
            "f1725341e873eb005b8d3a9566980d9d0b10173b97b9c5527e0173bb2062ebd6"
        ),
        "metadata": {
            "content_hash_scope": (
                "SHA-256 of the exact 4460168-byte content-decoded official GetSEIA "
                "response body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_body_bytes": 4_460_168,
            "capture_headers_bytes": 177,
            "capture_headers_sha256": (
                "d580f7cd5907e635b7e3a9d970d66446f93b9c5406f87433e8fd4eabe59355e1"
            ),
            "capture_curl_writeout_bytes": 18_656,
            "capture_curl_writeout_sha256": (
                "76c8af10bf6407a96a4a26b106f249e73618e85c0cbd9faf821482a2e89890d3"
            ),
            "http_status": 200,
            "http_version_as_received": "HTTP/1.1",
            "content_type": "text/html; charset=utf-8",
            "response_http_date": "2026-07-21T17:05:51Z",
            "context_page_url": SIMBIO_CONTEXT,
            "context_page_body_bytes": 3_162_804,
            "context_page_body_sha256": (
                "e05d13b56b25b28b2e42c670df31b8bb63b5d378fcd23a8c6c2624a9382cde3c"
            ),
            "context_page_headers_bytes": 177,
            "context_page_headers_sha256": (
                "7f17a1addc030bb7fadce1eafc84ebde62e1d37aa0c43706d6f96710e9159c27"
            ),
            "context_page_curl_writeout_bytes": 18_652,
            "context_page_curl_writeout_sha256": (
                "3fa06ee67af0c3acfb7411741812c3b7ef20941c966f928afc8639d48b241e0f"
            ),
            "context_page_response_http_date": "2026-07-21T17:06:29Z",
            "last_synchronization_as_reported": "2026-03-05",
            "cartography_rights_scope": (
                "The official context page states that use of its cartography is "
                "unrestricted while warning that the base is referential."
            ),
            "representative_point_scope": (
                "The publisher says SEIA data are based only on a representative point "
                "for the submitted project and do not represent its complete spatial extent."
            ),
            "returned_feature_count_for_exact_expediente": 1,
            "returned_object_id": expediente_id,
            "returned_expediente_id": expediente_id,
            "returned_project_name": spec["project_name_as_reported"],
            "returned_geometry_type": "esriGeometryPoint",
            "returned_spatial_reference_wkid": 4326,
            "returned_geometry_decimal_text": spec["source_decimal_text"],
            "selected_feature_canonical_sha256": spec["feature_canonical_sha256"],
            "stored_coordinate": spec["coordinates"],
            "stored_coordinate_decimal_places": spec["stored_decimal_places"],
            "coordinate_reference_system": "EPSG:4326",
            "coordinate_method": spec["geometry_semantics"],
            "horizontal_uncertainty_m": spec["horizontal_uncertainty_m"],
            "uncertainty_scope": (
                "Conservative analyst envelope for using a publisher-declared "
                "representative point as a site anchor; it is not publisher accuracy "
                "metadata and does not turn the point into a footprint or centroid."
            ),
            "precision_guardrail": (
                "The exact source decimal text is retained in metadata, while normalized "
                "coordinates are rounded to five decimals. Source digits are not claimed "
                "as horizontal survey accuracy."
            ),
            "parent_child_coordinate_scope": (
                "The same point is attached to the explicitly parented curated campus and "
                "project records. The project point is inherited site location, not an "
                "independent building centroid or footprint."
            ),
            "claim_guardrail": (
                "This evidence changes only coordinate snapshot fields. Evaluation state, "
                "lifecycle, capacity, operator, owner, workload, type, energy, and current "
                "status are not normalized from this record."
            ),
            "raw_capture_guardrail": (
                "The official response bodies, headers, and curl writeouts are hash-bound "
                "but are not redistributed in the repository artifact."
            ),
        },
    }


def _fortaleza_evidence(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": spec["evidence_key"],
        "kind": "government_record",
        "title": "Fortaleza municipal SFORPF01 surveyed site plan",
        "source_url": FORTALEZA_SITE_PLAN,
        "publisher": "Prefeitura de Fortaleza - SEUMA",
        "source_family": "fortaleza_cppd_project_plans",
        "published_at": None,
        "retrieved_at": "2026-07-21T09:27:32Z",
        "license": "all-rights-reserved",
        "attribution": "Prefeitura de Fortaleza - SEUMA; Scala Data Centers",
        "excerpt": (
            "The official municipal planning file identifies Praia do Futuro SFORPF01 "
            "and publishes four surveyed SIRGAS 2000 boundary vertices."
        ),
        "content_hash": (
            "039df7d2426a28c602fcdb2bafee8cb9bb2ce72ca3d3d2d55d1d44442c2d8b24"
        ),
        "metadata": {
            "content_hash_scope": (
                "SHA-256 of the exact 2965297-byte official two-page PDF response body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_body_bytes": 2_965_297,
            "capture_headers_bytes": 369,
            "capture_headers_sha256": (
                "37626eb25e33e5274cff2c4ea0a4e00804c6e8fca92bce99ccf65156895b306d"
            ),
            "capture_curl_writeout_bytes": 14_524,
            "capture_curl_writeout_sha256": (
                "7b42d06afcd44c63e772f434353c3a26e58e552120a2773ec299ffd5aa74b6a8"
            ),
            "http_status": 200,
            "http_version_as_received": "HTTP/1.1",
            "content_type": "application/pdf",
            "response_http_date": "2026-07-21T09:27:32Z",
            "http_last_modified_at": "2023-11-06T13:31:55Z",
            "pdf_pages": 2,
            "relevant_pdf_page": 1,
            "project_name_as_reported": "PRAIA DO FUTURO - SFORPF01",
            "plan_code_as_reported": "SFORPF01-B-SCD-DC01-AR20-DE-0002",
            "plan_date_as_reported": "09/23",
            "source_coordinate_reference_system": (
                "SIRGAS 2000 / UTM zone 24S (EPSG:31984)"
            ),
            "source_boundary_vertices_xy_m": [
                {"vertex": "P1", "x": "560165.382", "y": "9585100.992"},
                {"vertex": "P2", "x": "560070.156", "y": "9585131.517"},
                {"vertex": "P3", "x": "560201.416", "y": "9585540.994"},
                {"vertex": "P4", "x": "560296.643", "y": "9585510.468"},
            ],
            "source_boundary_area_square_meters_as_reported": "43000.00",
            "source_boundary_perimeter_meters_as_reported": "1060.00",
            "source_crs_centroid_xy_m": {
                "x": "560183.39925",
                "y": "9585320.99275",
            },
            "transformation": {
                "source_crs": "EPSG:31984",
                "target_crs": "EPSG:4326",
                "axis_order": "always_xy",
                "pyproj_version": "3.7.2",
                "proj_version": "9.5.1",
                "epsg_database_version": "v11.022",
                "epsg_database_date": "2024-11-05",
                "unrounded_centroid": {
                    "latitude": "-3.751508763660",
                    "longitude": "-38.458001391848",
                },
            },
            "stored_coordinate": spec["coordinates"],
            "stored_coordinate_decimal_places": spec["stored_decimal_places"],
            "stored_project_boundary_geojson": spec["project_geometry"],
            "coordinate_method": (
                "centroid_in_source_crs_of_official_surveyed_project_boundary_then_"
                "epsg_transform"
            ),
            "horizontal_uncertainty_m": spec["horizontal_uncertainty_m"],
            "uncertainty_scope": (
                "Conservative analyst envelope for PDF transcription, CRS interpretation, "
                "and transformation. It is not a publisher accuracy specification."
            ),
            "precision_guardrail": (
                "Millimeter-formatted source vertices are retained as text, but the "
                "normalized WGS84 point and ring are rounded to six decimals and carry a "
                "five-meter uncertainty envelope. Decimal representation is not accuracy."
            ),
            "geometry_scope": (
                "The project geometry is the surveyed SFORPF01 property boundary shown in "
                "the municipal planning file, not a building footprint or full future "
                "Praia do Futuro campus boundary. The campus stores only the same point as "
                "an anchor because SFORPF01 is explicitly parented to that curated campus."
            ),
            "claim_guardrail": (
                "This evidence changes only coordinate snapshot fields. It creates no "
                "lifecycle, capacity, operator, owner, workload, type, energy, or current-"
                "status claim."
            ),
            "raw_capture_guardrail": (
                "The all-rights-reserved PDF, headers, curl writeout, extracted text, and "
                "renders are hash-bound but are not redistributed in the repository artifact."
            ),
        },
    }


def _successor(label: str, spec: dict[str, Any]) -> dict[str, Any]:
    document = copy.deepcopy(_load_source(spec["predecessor"]))
    if document["campus"]["stable_key"] != spec["campus_key"]:
        raise RuntimeError(f"campus key mismatch for {label}")
    if document["project"]["stable_key"] != spec["project_key"]:
        raise RuntimeError(f"project key mismatch for {label}")
    evidence = (
        _fortaleza_evidence(spec)
        if label == "fortaleza"
        else _simbio_evidence(spec)
    )
    document["evidence"].append(evidence)
    for entity_name, geometry_key in (
        ("campus", "campus_geometry"),
        ("project", "project_geometry"),
    ):
        entity = document[entity_name]
        entity["coordinates"] = copy.deepcopy(spec["coordinates"])
        entity["geometry"] = copy.deepcopy(spec[geometry_key])
        entity["evidence_key"] = spec["evidence_key"]
        entity["method"] = spec["method"]
    return document


def _coordinate_observations() -> dict[str, Any]:
    rows = []
    for label, spec in RESOLVED.items():
        rows.append(
            {
                "label": label,
                "campus_key": spec["campus_key"],
                "project_key": spec["project_key"],
                "coordinates": spec["coordinates"],
                "campus_geometry_type": spec["campus_geometry"]["type"],
                "project_geometry_type": spec["project_geometry"]["type"],
                "geometry_semantics": spec["geometry_semantics"],
                "stored_decimal_places": spec["stored_decimal_places"],
                "horizontal_uncertainty_m": spec["horizontal_uncertainty_m"],
                "evidence_key": spec["evidence_key"],
                "predecessor": f"sources/{spec['predecessor']}",
                "successor": f"normalized-successors/{spec['successor']}",
                "integration": "none",
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "accepted_coordinate_campuses": len(rows),
        "explicitly_parented_projects_receiving_same_site_anchor": len(rows),
        "rows": rows,
    }


def _disposition(successor_pins: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cohort_rows = [
        {"path": f"sources/{name}", "bytes": pin[0], "sha256": pin[1]}
        for name, pin in COHORT.items()
    ]
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "scope": "coordinate_only_assessment",
        "integration": "none",
        "accepted_seed_definition": None,
        "lineage": {
            "direct_curated_source_pins_only": True,
            "rejected_as_lineage": [
                {
                    "path": "sources/open-seed-2026-07-21-v68.json",
                    "reason": "rejected_future_recorded_at_metadata",
                },
                {
                    "path": (
                        "source_artifacts/global-underrepresented-official-discovery-"
                        "2026-07-21-v1"
                    ),
                    "reason": "rejected_future_recorded_at_metadata",
                },
                {
                    "path": (
                        "source_artifacts/second-underrepresented-official-discovery-"
                        "2026-07-21-v1"
                    ),
                    "reason": "rejected_future_recorded_at_metadata",
                },
            ],
            "guardrail": (
                "Rejected seed/wrapper v1 artifacts are cohort-discovery context only, "
                "not accepted lineage. This artifact pins the unchanged underlying "
                "curated files directly and selects nothing downstream."
            ),
        },
        "cohort": {
            "curated_source_files": 13,
            "campuses": 10,
            "projects": 13,
            "rows": cohort_rows,
        },
        "accepted": {
            "campuses": 3,
            "projects": 3,
            "coordinate_rows": 6,
            "successors": successor_pins,
        },
        "unresolved": {
            "campuses": 7,
            "projects": 10,
            "rows": UNRESOLVED,
        },
        "excluded_methods": [
            "generic_city_or_locality_centroid",
            "street_midpoint_or_range_interpolation",
            "google_derived_coordinate",
            "unlicensed_proprietary_directory_coordinate",
            "coordinate_transfer_from_distinct_facility_without_site_identity",
            "non_deterministic_visual_or_osm_match",
        ],
        "non_coordinate_claims_added": [],
    }


def _retrieval_inventory() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "raw_payloads_redistributed": False,
        "raw_response_bodies_retained_in_repository": False,
        "raw_response_headers_retained_in_repository": False,
        "raw_curl_writeouts_retained_in_repository": False,
        "all_rights_reserved_raw_bytes_hash_only": True,
        "analysis_capture_directory_moved_intact_to_trash": True,
        "trash_recovery_path": (
            "/Users/kian/.Trash/datacenter-atlas-v68-coordinate-capture-"
            "20260721-1707Z-y0NdsP"
        ),
        "accepted_capture_requests": [
            {
                "request_id": "chile_simbio_region_13_seia",
                "url": SIMBIO_ENDPOINT,
                "retrieved_at": "2026-07-21T17:05:51Z",
                "license": "no-use-restriction-stated-for-reference-cartography",
                "body": {
                    "bytes": 4_460_168,
                    "sha256": (
                        "f1725341e873eb005b8d3a9566980d9d0b10173b97b9c5527e0173bb2062ebd6"
                    ),
                    "retained_in_repository": False,
                },
                "headers": {
                    "bytes": 177,
                    "sha256": (
                        "d580f7cd5907e635b7e3a9d970d66446f93b9c5406f87433e8fd4eabe59355e1"
                    ),
                    "retained_in_repository": False,
                },
                "curl_writeout": {
                    "bytes": 18_656,
                    "sha256": (
                        "76c8af10bf6407a96a4a26b106f249e73618e85c0cbd9faf821482a2e89890d3"
                    ),
                    "retained_in_repository": False,
                },
                "normalized_evidence_keys": [
                    RESOLVED["lampa"]["evidence_key"],
                    RESOLVED["huechuraba"]["evidence_key"],
                ],
            },
            {
                "request_id": "chile_simbio_region_context",
                "url": SIMBIO_CONTEXT,
                "retrieved_at": "2026-07-21T17:06:29Z",
                "license": "no-use-restriction-stated-for-reference-cartography",
                "body": {
                    "bytes": 3_162_804,
                    "sha256": (
                        "e05d13b56b25b28b2e42c670df31b8bb63b5d378fcd23a8c6c2624a9382cde3c"
                    ),
                    "retained_in_repository": False,
                },
                "headers": {
                    "bytes": 177,
                    "sha256": (
                        "7f17a1addc030bb7fadce1eafc84ebde62e1d37aa0c43706d6f96710e9159c27"
                    ),
                    "retained_in_repository": False,
                },
                "curl_writeout": {
                    "bytes": 18_652,
                    "sha256": (
                        "3fa06ee67af0c3acfb7411741812c3b7ef20941c966f928afc8639d48b241e0f"
                    ),
                    "retained_in_repository": False,
                },
                "normalized_evidence_keys": [],
                "scope": "representative_point_semantics_and_rights_context",
            },
            {
                "request_id": "fortaleza_sforpf01_site_plan",
                "url": FORTALEZA_SITE_PLAN,
                "retrieved_at": "2026-07-21T09:27:32Z",
                "license": "all-rights-reserved",
                "body": {
                    "bytes": 2_965_297,
                    "sha256": (
                        "039df7d2426a28c602fcdb2bafee8cb9bb2ce72ca3d3d2d55d1d44442c2d8b24"
                    ),
                    "retained_in_repository": False,
                },
                "headers": {
                    "bytes": 369,
                    "sha256": (
                        "37626eb25e33e5274cff2c4ea0a4e00804c6e8fca92bce99ccf65156895b306d"
                    ),
                    "retained_in_repository": False,
                },
                "curl_writeout": {
                    "bytes": 14_524,
                    "sha256": (
                        "7b42d06afcd44c63e772f434353c3a26e58e552120a2773ec299ffd5aa74b6a8"
                    ),
                    "retained_in_repository": False,
                },
                "normalized_evidence_keys": [RESOLVED["fortaleza"]["evidence_key"]],
            },
        ],
        "research_exclusions": [
            {
                "site": "green_mountain_fra_mainz",
                "capture": "osm-map-mainz-kmw.osm",
                "bytes": 5_341_853,
                "sha256": (
                    "b538d7c834cea3169d164807461262e08a2742974f91b8ec77fa351db2df3a24"
                ),
                "license": "ODbL-1.0",
                "disposition": "unresolved_non_deterministic_project_polygon_bridge",
            },
            {
                "site": "scala_tambore",
                "capture": "osm-map-tambore.osm",
                "bytes": 2_010_770,
                "sha256": (
                    "bea3ae76ab22feffcc7e9bad68ae2305975fb700207c08409707616c30579e8d"
                ),
                "license": "ODbL-1.0",
                "disposition": "unresolved_conflicting_identity_and_shared_addresses",
            },
            {
                "site": "scala_smextp02",
                "capture": "osm-map-tepotzotlan-scala.osm",
                "bytes": 358_976,
                "sha256": (
                    "bea19f4bbc16e243e5eee88f02fabaed6a2f5e74552b4a2e61b1fd3bfd538c93"
                ),
                "license": "ODbL-1.0",
                "disposition": "excluded_distinct_smextp01_only",
            },
        ],
        "request_guardrail": (
            "All requests were credential-free. No Authorization, cookies, client "
            "certificates, or private accounts were used. Raw capture bytes are recoverable "
            "from Trash but are not part of this artifact."
        ),
    }


def _readme() -> bytes:
    text = """# Site coordinate assessment 2026-07-21 v1

This collision-isolated artifact assesses the ten campuses and thirteen explicitly
parented projects in thirteen directly pinned curated files. It accepts only three
official site anchors: two Chilean environmental-review representative points and
one Fortaleza surveyed project boundary. Their three explicitly parented projects
receive the same site anchor with explicit non-footprint semantics.

Seven campuses and ten projects remain unresolved. Generic locality centroids,
street midpoints, Google-derived coordinates, unlicensed directory points,
coordinates from distinct facilities, and non-deterministic OSM matches are excluded.

Integration is `none`. The temporally invalid open-seed v68 and both discovery-wrapper
v1 artifacts are expressly rejected as lineage. The unchanged thirteen curated files
are pinned directly. No lifecycle, capacity, operator, owner, workload, data-center
type, energy, consumption, or current-status claim is added.

Normalized successor documents live only under `normalized-successors/`; they are not
copied into `sources/` or selected by a release. All-rights-reserved raw captures are
hash-only here and the entire analysis capture directory was moved intact to the unique
Trash path recorded in `retrieval-inventory.json`.
"""
    return text.encode("utf-8")


def _freeze_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)
    root.chmod(0o555)


def main() -> None:
    for name in COHORT:
        _load_source(name)

    successors: dict[str, bytes] = {}
    successor_pins: dict[str, dict[str, Any]] = {}
    for label, spec in RESOLVED.items():
        raw = _canonical_json(_successor(label, spec))
        relative = f"normalized-successors/{spec['successor']}"
        successors[relative] = raw
        successor_pins[label] = {
            "path": relative,
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "predecessor": f"sources/{spec['predecessor']}",
            "campus_key": spec["campus_key"],
            "project_key": spec["project_key"],
        }

    payloads: dict[str, bytes] = {
        "README.md": _readme(),
        "coordinate-observations.json": _canonical_json(_coordinate_observations()),
        "disposition.json": _canonical_json(_disposition(successor_pins)),
        "retrieval-inventory.json": _canonical_json(_retrieval_inventory()),
        **successors,
    }
    for relative, raw in payloads.items():
        _write_exact(ARTIFACT_DIR / relative, raw)

    manifest_rows = [
        {"path": relative, "bytes": len(raw), "sha256": _sha256(raw)}
        for relative, raw in sorted(payloads.items())
    ]
    tree_payload = _canonical_json(manifest_rows)
    manifest = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "files": manifest_rows,
        "tree_sha256": _sha256(tree_payload),
    }
    manifest_raw = _canonical_json(manifest)
    _write_exact(ARTIFACT_DIR / "manifest.json", manifest_raw)
    _write_exact(
        ARTIFACT_DIR / "manifest.sha256",
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii"),
    )
    _freeze_tree(ARTIFACT_DIR)


if __name__ == "__main__":
    main()
