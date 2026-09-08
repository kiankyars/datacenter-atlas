"""Build and validate the 100-site Verified Construction Core v0.17 preview."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from . import verified_construction_core as v16


VerifiedConstructionCoreError = v16.VerifiedConstructionCoreError
ROOT = v16.ROOT
PROJECT_FIELDS = v16.PROJECT_FIELDS
SITE_FIELDS = v16.SITE_FIELDS
EVIDENCE_FIELDS = v16.EVIDENCE_FIELDS

LEGACY_PREVIEW_V16_DIR = v16.CURRENT_V16_PREVIEW_DIR
LEGACY_PREVIEW_V16_MANIFEST_SHA256 = (
    "562509f98417fdc48afb7bc92f58a6924fa99898bc77a0a96aee9a9c32c1bd6a"
)
LEGACY_PREVIEW_V16_COMMIT = "6939ce1b7cc2a71a2a8de3830225cf9778688bce"
CURRENT_V17_PREVIEW_ID = "2026-08-20-preview-v0.17"
CURRENT_V17_PREVIEW_DIR = ROOT / "verified_construction_core" / CURRENT_V17_PREVIEW_ID
CURRENT_V17_LIFECYCLE_REFERENCE_DATE = date(2026, 8, 20)
CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE = date(2026, 9, 6)
CURRENT_V17_REVIEW_DATE = CURRENT_V17_LIFECYCLE_REFERENCE_DATE
V17_BATCH_CONTRACT = (
    ROOT / "definitions" / "verified-construction-core-v0.17-100-site-batch.json"
)
V17_GEOMETRY_CAPTURE = (
    ROOT / "sources" / "verified-construction-core-v0.17-100-site-geometry-facts.json"
)

V17_BATCH_CONTRACT_SHA256 = (
    "4f51d5d9df30a198be882851a38a028086c3a9c03f98081616acc58e4acd8718"
)
V17_GEOMETRY_CAPTURE_SHA256 = (
    "90b50295b1ba22550a2f2a44adc4b467b4149b8eb865d135bf074df53373e99b"
)

V17_EXPECTED_PROJECT_COUNT = 103
V17_EXPECTED_SITE_COUNT = 100
V17_EXPECTED_COUNTRY_COUNT = 40
V17_EXPECTED_DELTA_COUNT = 20
V17_EXPECTED_OFFICIAL_BOUNDARY_PROJECT_COUNT = 5
V17_EXPECTED_REVIEWED_LOCATOR_PROJECT_COUNT = 98
V17_EXPECTED_V97_SELECTED_PROJECT_COUNT = 97
V17_EXPECTED_POST_V97_SELECTED_PROJECT_COUNT = 6

V17_COUNTRY_ISO_A2 = {
    "Australia": "AU",
    "Brazil": "BR",
    "Canada": "CA",
    "China": "CN",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Nepal": "NP",
    "New Zealand": "NZ",
    "Niger": "NE",
    "Romania": "RO",
    "United States": "US",
}


# Independently reviewed row fingerprints. Refreshing a file/container digest must
# not silently relocate a locator, strip rights metadata, or rewrite frozen lineage.
# Changes here require a new source-level review, not regeneration by the utility.
V17_REVIEWED_LOCATOR_SHA256 = {
    "ascenty-vinhedo-campus-vin02-factsheet-point": (
        "4dc92da78f84e71bc41ac95ee3111713776dfd845036ec191214920d0148fa69"
    ),
    "cdc-brooklyn-acma-site-10038207-point": (
        "a90c6c5114e145823b1dd43f6e722391eb8277b716978ccf9378dc37e93998e4"
    ),
    "cdc-maddington-gosnells-lot-500-582-bickley-polygon": (
        "80ea23547470b5300262f4c7c5b0f6e758dee8336458b5a95763e12a5e9b4045"
    ),
    "china-mobile-haidong-phase2-stage1-eia-project-point": (
        "32bdfc85e170b5c5f61ae1aec367318cb6d9585ee25d274ac91ee57af1a98a47"
    ),
    "cra-prague-gateway-cuzk-permit-parcels-point-on-surface": (
        "83f8639275ba511600fc92972a760d882ac256f3004097cfa61b5239d42ff823"
    ),
    "cyrusone-yorkville-c1-parcel-centroid": (
        "182089d629ef1ddab99346a6e1e18e56f3b1e4ffb53cc0ef2396c6ec5bdfc7ca"
    ),
    "dansk-data-center-1-esbjerg-dar-sahara-9-address-point": (
        "a035486478bd7dd23c01809df6acd9022a366abf4a9fc41652fc2b64ab32f2f3"
    ),
    "data-world-matatirtha-first-party-kathmandu-marker": (
        "a902e43ac2ba718fac19a2ca34cd9cec15854cbceeffcc954b0db11e5eb28a44"
    ),
    "datagrid-makarewa-linz-four-core-parcel-union": (
        "5b9da82fe038d99ec9b9066ed355693aa884f08d06e4eaee7d9ec7dce9944b57"
    ),
    "digipowerx-columbiana-census-130-industrial-parkway": (
        "1edc4f5251725cb9bf5d39db4130cbbca59ce6fec269a4b6b2f427ed93dbe11b"
    ),
    "edgecore-as02-loudoun-parcel-045465016000": (
        "33789a55fd02c4c0f623636aad9faee9eb79b5443164281b36b0bad5125318f1"
    ),
    "edged-council-bluffs-pott-address-2313-college-road": (
        "3f2514fecccae1957d773c89c9c5f6f3f597783b168e0cd6c86ed1e632bac25b"
    ),
    "meta-sturgeon-dp26-0028-ats-union-representative-point": (
        "aa3e6227a0a6d5ec1dc3b7ba299c0b52d79912e2e09e131f46fddf60b7978041"
    ),
    "microsoft-lyle-creek-usace-published-project-point": (
        "7936444c96bbb08b22cb2d06a075472d18bd34dcb52cba2b61e178f8dd028aca"
    ),
    "niger-national-dc-pk5-bnee-eies-project-point": (
        "7fc2ac063cbd4d6a45a9e550ace89905ae115b6dcda39e717554e706b0fb87c6"
    ),
    "nxdata3-buh3-inflect-datacenter-marker": (
        "3a2b6392a0f2b19e9f3715f7f226dc3dd5d81439dbfe6ace6cfdd50e04140a7c"
    ),
    "odata-sp04-terminal-place-pin": (
        "f98cdf57de6f3037cebc050cff994f2b582ac0adafca3b3130e82653ea4edbea"
    ),
    "qts-eagle-mountain-550-hyperscale-way-address-point": (
        "94604b93bde75e4506440089cc7cacd825e1ea4a418a84bb506893eed3a14409"
    ),
    "related-digital-cheyenne-first-party-map-point": (
        "d99f72316ef3bb822e8fe6fb51de18743c0e3349c4be8d30522cadfb9801b7d6"
    ),
    "vantage-lighthouse-wisconsin-dnr-project-coordinate": (
        "d3f765bff549f5910bccc511c323ee834313859c059c2538863f930d7aeed869"
    ),
}

V17_REVIEWED_SOURCE_DOCUMENT_SHA256 = {
    "ascenty-vinhedo-campus-factsheet": (
        "335c7143673bd9e31f0b0977e99f85ce43ffff889105d36eaedc1bc725c0ad22"
    ),
    "cdc-brooklyn-acma-site-10038207": (
        "4580c82ea479f197a616f27988efdd5b25dc1cf667262354f27c34dfe4df91ad"
    ),
    "cdc-maddington-gosnells-intramaps-lot-500": (
        "8fa1fe2dd5172727ad2408a7366147cfdcbdb7400138f126f9bff50b99667924"
    ),
    "china-mobile-haidong-phase2-stage1-eia": (
        "7bcaba8eb46670d1e6dbea15d43f0d17f1e75f56c795dedad34415c5bf781696"
    ),
    "cra-prague-gateway-cuzk-permit-parcels": (
        "71c107a38e4a439936783bcd40d95d7146976c38de968baca7f7ea13fa47bafb"
    ),
    "cyrusone-yorkville-kendall-pin-02-18-300-004-centroid": (
        "17a666c7e161d1181f9aea13d933d99359ba1de2691d18343c3238dc247867b8"
    ),
    "data-world-matatirtha-first-party-kathmandu-marker": (
        "82951c217510add2f36ab129ed7b34b7898faf22ad2f6846fbaa1b387d1d80eb"
    ),
    "datagrid-makarewa-linz-four-primary-parcels": (
        "1fd0617751e964367eed7c09fe08820de25116897897a5e5de140aa6981f6525"
    ),
    "datagrid-makarewa-sdc-resource-consent-application": (
        "12f22049bfd76bbea80d7f942e3bc2985e5ddaa50599585d5c841955c9e164cf"
    ),
    "ddc1-esbjerg-dar-sahara-9-address-point": (
        "191859177938eb0b39f61be452d35d6f5f9b029d6ab9bfdbd7fe1ed004b0ad80"
    ),
    "ddc1-esbjerg-dma-facility-record": (
        "ae88b3639a7545401676b5687f1ffa49dd29a53b907bcfb5b573b49ccb7e8b17"
    ),
    "digipowerx-columbiana-census-geocode": (
        "ab65ca42c93c5be2945b0ed284383679de5c1f2f71e695742aaff7cc6fcabce3"
    ),
    "edgecore-as02-loudoun-parcel-045465016000": (
        "6d48537b44e3509c90a3de06a7c970978b0d430f7f922ff2716885263259bc14"
    ),
    "edged-council-bluffs-pott-address-35068": (
        "a3df06f7a74ebf34cd6f8071384c5041d02e501339cfba735c106f85d891d11c"
    ),
    "meta-sturgeon-alberta-ats-quarter-sections": (
        "1372734eee0c8e88565f46d015dcde8b0640ac6ed66305a2d93a5ca336310fe7"
    ),
    "meta-sturgeon-dp26-0028-permit-notice": (
        "886be8863c84e3b5ccd468628fa72a580d9eaf1181c65c6d21a48ded4d01e513"
    ),
    "microsoft-lyle-creek-catawba-containing-parcel": (
        "21a36e4646be5e000cd74ec4d8a44f388507bb8f175792efab936f615fee19cf"
    ),
    "microsoft-lyle-creek-usace-saw-2023-00898-index-extract": (
        "e9f2ba5fa6f3373799344f9c0c515bcb3272b19ba1ed89a82d7115edb14b6332"
    ),
    "niger-national-dc-pk5-bnee-eies": (
        "2593444c5b07675963fc7320af0fcff29d8867cc4471d7434e37cbeaa442139c"
    ),
    "nxdata3-inflect-datacenter-marker": (
        "1e9dde6d86acdff291998b898b6a95148830c82f946b337ceb1d5d13b43ca33e"
    ),
    "odata-sp04-current-facility-page-map-pin": (
        "3364ea8f47c64432d7d4f4a581aacfbef654a7fdfcbdc27fd309a7bd9bea39d2"
    ),
    "qts-eagle-mountain-utah-county-address-258853": (
        "c9b4cb4d5cd6f02f517fbdefd7868dd0ef556c948ed4b9439ade020cc733e7e9"
    ),
    "related-digital-cheyenne-wyoming-page-map-point": (
        "5f660ca441ec59a3a3a9860e91b39e8310bebea65c988d1e3dc9d952f1083937"
    ),
    "vantage-lighthouse-wisconsin-dnr-current-page": (
        "ebdd39cc8494e069c888e34cbc5733716e77c7ed35746bf1fc5d1179ea08637d"
    ),
}

V17_REVIEWED_LINEAGE_SHA256 = {
    "curated:ascenty-vinhedo-campus:vinhedo-3": (
        "2976342416cf39a50ad89afe651d5e8a636a4bdef145ca3023d0267386f64b34"
    ),
    "curated:cdc-brooklyn-melbourne-campus:remaining-facilities-current-build": (
        "0886dce541b58fb970822c3056385fbb6e7b2a683790b53dd88cf2e03241bd84"
    ),
    "curated:cdc-maddington-perth-campus:current-build": (
        "68215f4fa4e4731f2a8098c6e9460c5b299f8b6be77914ff3717e4fba39aa2b7"
    ),
    "curated:china-mobile-plateau-big-data-center-haidong:phase-2-build": (
        "c85980deaa25ad4279b507d12956c2d2be47a5d8d41417bbea988b6b69e23715"
    ),
    "curated:cra-prague-gateway-data-center-campus:current-campus-build": (
        "b7721683e2957eb4e15818cb293585ee78cd6016f10859fc9e787900c79849a8"
    ),
    "curated:cyrusone-yorkville-technology-campus:current-site-work": (
        "17629f21758463f834af41f467458b74a1f4b8a642446aa29af9dc3ec1499542"
    ),
    "curated:dansk-data-center-1-esbjerg-campus:ddc1-current-build": (
        "1ac58a4a54327a1181c00678b0cd018a45f45d5f71a41f109e13711e24e0d509"
    ),
    "curated:data-world-matatirtha-campus:core-data-center-current-build": (
        "f738d7acb491774d69606b96d3da8769385a8d79e3017aa11b286b63222425f4"
    ),
    "curated:datagrid-makarewa-ai-factory:initial-horizontal-works": (
        "d102c8f35197cf4814239b18eb36c1caac618bcba7a74001be92255fdc54614a"
    ),
    "curated:digipowerx-columbiana-ai-data-center-campus:purpose-built-flagship-vertical-build": (
        "fedd371f5a5856e9103497d63cfadb134b0bec7fe88b22f161b0e0542e9a8c3f"
    ),
    "curated:edgecore-as02-sterling-virginia-campus:as02-data-center": (
        "d5a5cce2036b5464f19b7d35a63075c5233e4b7b0fde040aca4751e24f63d94d"
    ),
    "curated:edged-council-bluffs-data-center-campus:first-data-center": (
        "3ec0c51087b4f445d209a11faef7d0a1b2780c50386bbf5f0b6d077f2a4be47e"
    ),
    "curated:meta-sturgeon-county-alberta-data-center:current-campus-build": (
        "3568c5fbdbd9506313c5aa2be137c64ef7fca3403fec5e00f6fe0f0e543534b9"
    ),
    "curated:microsoft-lyle-creek-conover-data-center:current-build": (
        "53cdbd7a499c10d9fbc5d15ff11041724af1b4c8d7b415d42a1e565a470a23ae"
    ),
    "curated:niger-national-data-center-pk5-niamey:current-build": (
        "0446601525ea4b27f68655a0846307793dbaf1114a1e569ef54493f5c5443d8a"
    ),
    "curated:nxdata3-bucharest-ring-road-campus:nxdata3-buh3": (
        "d8116726a1c251660ac3333fdf06dd9707c9c28064f5c6d0864275d4c2f26691"
    ),
    "curated:odata-dc-sp04-osasco-campus:phase-2-expansion": (
        "d0db9769f063e93037b79b9c57843b868e0d57c0864b44073756491d5d92e99b"
    ),
    "curated:qts-eagle-mountain-slc1-data-center-campus:building-2": (
        "cc91c76a8f75fbf92d972604c52c14d7c23d1775f9fd59084b7653009546f45d"
    ),
    "curated:related-digital-cheyenne-campus:phase-1": (
        "077726dd11cdde167ef28fd02efdb1137056e7433252524e69a9cda5bb99af26"
    ),
    "curated:vantage-lighthouse-port-washington-campus:current-campus-build": (
        "694410209f0bcb17d5f57d621c732a026c47f6b967836251b88c948221cc475a"
    ),
}


def validate_frozen_v16(
    path: Path = LEGACY_PREVIEW_V16_DIR,
) -> dict[str, Any]:
    """Validate the frozen v0.16 base and its pinned manifest digest."""
    manifest = v16.validate_preview(path)
    manifest_path = Path(path) / "manifest.json"
    if v16._sha256_file(manifest_path) != LEGACY_PREVIEW_V16_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("v0.16 frozen manifest differs")
    return manifest


def _source_evidence(
    source: Mapping[str, Any], key: str, evidence_id: str
) -> dict[str, Any]:
    matches = [
        row
        for row in source.get("evidence", [])
        if isinstance(row, dict) and row.get("key") == key
    ]
    if len(matches) != 1:
        raise VerifiedConstructionCoreError(f"v0.17 source evidence differs: {key}")
    row = matches[0]
    expected_id = v16.atlas_stable_id(
        "evidence", "curated-official", key, row.get("content_hash")
    )
    if evidence_id != expected_id:
        raise VerifiedConstructionCoreError(
            f"v0.17 source evidence identifier differs: {key}"
        )
    return v16._v07_evidence_projection({**row, "evidence_id": evidence_id})


def _capture_evidence(document: Mapping[str, Any]) -> dict[str, Any]:
    evidence_id = document.get("evidence_id")
    expected_id = v16.atlas_stable_id(
        "evidence",
        "verified-construction-core-v0.17",
        document.get("source_id"),
        document.get("content_hash"),
    )
    if not isinstance(evidence_id, str) or evidence_id != expected_id:
        raise VerifiedConstructionCoreError("v0.17 capture evidence identifier differs")
    return v16._v07_evidence_projection(document)


def _source_local_relationship_id(
    project_entity_id: str,
    campus_entity_id: str,
    source_input_sha256: str,
) -> str:
    payload = "\x1f".join(
        (
            "vcc-v0.17-source-local-explicit-parent-v1",
            "project_targets",
            project_entity_id,
            campus_entity_id,
            source_input_sha256,
        )
    ).encode()
    return f"relationship:{hashlib.sha256(payload).hexdigest()}"


def _canonical_geometry(result: Mapping[str, Any]) -> dict[str, Any]:
    geometry = result.get("geometry")
    if not isinstance(geometry, dict):
        raise VerifiedConstructionCoreError("v0.17 geometry record differs")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type not in {"Point", "MultiPoint", "Polygon", "MultiPolygon"}:
        raise VerifiedConstructionCoreError("v0.17 geometry type differs")

    def point(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 2
            and all(type(number) in {int, float} for number in value)
            and all(math.isfinite(float(number)) for number in value)
            and -180 <= float(value[0]) <= 180
            and -90 <= float(value[1]) <= 90
        )

    def ring(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) >= 4
            and all(point(item) for item in value)
            and value[0] == value[-1]
        )

    valid = False
    if geometry_type == "Point":
        valid = point(coordinates)
    elif geometry_type == "MultiPoint":
        valid = (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(point(item) for item in coordinates)
        )
    elif geometry_type == "Polygon":
        valid = (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(ring(item) for item in coordinates)
        )
    elif geometry_type == "MultiPolygon":
        valid = (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(
                isinstance(polygon, list)
                and bool(polygon)
                and all(ring(item) for item in polygon)
                for polygon in coordinates
            )
        )
    if not valid:
        raise VerifiedConstructionCoreError("v0.17 geometry coordinates differ")
    canonical = v16._json_bytes(geometry)[:-1]
    expected = result.get("canonical_geometry")
    if expected != {
        "bytes_without_newline": len(canonical),
        "sha256_without_newline": v16._sha256_bytes(canonical),
    }:
        raise VerifiedConstructionCoreError("v0.17 canonical geometry differs")
    return geometry


def _required_hydrated_row(
    rows: Sequence[Mapping[str, str]],
    field: str,
    value: str,
    expected_sha256: str,
    label: str,
) -> Mapping[str, str]:
    matches = [row for row in rows if row.get(field) == value]
    if (
        len(matches) != 1
        or v16._sha256_bytes(v16._json_bytes(matches[0])) != expected_sha256
    ):
        raise VerifiedConstructionCoreError(f"v0.17 hydrated lineage {label} differs")
    return matches[0]


def _validate_hydrated_lineage(
    contract: Mapping[str, Any],
    acceptances: Sequence[Mapping[str, Any]],
) -> None:
    pipeline_rows = v16._load_csv(v16.SOURCE_RELEASE / "construction_pipeline.csv")
    entity_rows = v16._load_csv(v16.SOURCE_RELEASE / "entities.csv")
    evidence_rows = v16._load_csv(v16.SOURCE_RELEASE / "evidence.csv")
    identity_dir = ROOT / "exact_identity_decisions" / "2026-07-22-public-open-v14"
    member_rows = v16._load_csv(identity_dir / "component-members.csv")
    relationship_rows = v16._load_csv(identity_dir / "relationships.csv")
    acceptance_by_key = {row["project_stable_key"]: row for row in acceptances}
    lineage_rows = contract.get("source_lineage")
    if not isinstance(lineage_rows, list):
        raise VerifiedConstructionCoreError("v0.17 source lineage differs")

    def absent(rows: Sequence[Mapping[str, str]], field: str, value: str) -> bool:
        return not any(row.get(field) == value for row in rows)

    for lineage in lineage_rows:
        if not isinstance(lineage, dict):
            raise VerifiedConstructionCoreError("v0.17 source lineage differs")
        project_key = lineage.get("project_stable_key")
        acceptance = acceptance_by_key.get(project_key)
        if not isinstance(acceptance, dict):
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated lineage acceptance differs"
            )
        campus_key = acceptance["parent_campus_stable_key"]
        project_binding = lineage.get("v97_project", {})
        campus_binding = lineage.get("v97_campus", {})
        project_member_binding = lineage.get("v14_project_member", {})
        campus_member_binding = lineage.get("v14_campus_member", {})
        topology_binding = lineage.get("v14_topology", {})
        project_presence = project_binding.get("presence")
        if project_presence == "pipeline":
            project_row = _required_hydrated_row(
                pipeline_rows,
                "stable_key",
                project_key,
                project_binding["row_sha256"],
                "v97 project",
            )
            entity_row = _required_hydrated_row(
                entity_rows,
                "stable_key",
                project_key,
                project_binding["row_sha256"],
                "v97 project entity",
            )
            if (
                project_row != entity_row
                or project_row.get("entity_id") != acceptance["project_entity_id"]
                or project_row.get("status") != acceptance["status"]["value"]
                or project_row.get("status_as_of") != acceptance["status"]["as_of_date"]
                or project_row.get("status_evidence_id")
                != acceptance["status"]["evidence_id"]
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated v97 project projection differs"
                )
            evidence_binding = lineage.get("v97_status_evidence", {})
            if (
                evidence_binding.get("evidence_id")
                != acceptance["status"]["evidence_id"]
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated v97 evidence binding differs"
                )
            evidence_row = _required_hydrated_row(
                evidence_rows,
                "evidence_id",
                evidence_binding.get("evidence_id", ""),
                evidence_binding.get("row_sha256", ""),
                "v97 status evidence",
            )
            if evidence_row.get("content_hash") != evidence_binding.get("content_hash"):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated v97 evidence projection differs"
                )
        elif project_presence == "entity_only":
            project_row = _required_hydrated_row(
                entity_rows,
                "stable_key",
                project_key,
                project_binding["row_sha256"],
                "v97 identity-only project",
            )
            if project_row.get("entity_id") != acceptance[
                "project_entity_id"
            ] or not absent(pipeline_rows, "stable_key", project_key):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated identity-only project differs"
                )
        elif project_presence == "absent":
            if not (
                absent(entity_rows, "stable_key", project_key)
                and absent(pipeline_rows, "stable_key", project_key)
                and absent(member_rows, "stable_key", project_key)
                and absent(
                    evidence_rows, "evidence_id", acceptance["status"]["evidence_id"]
                )
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated post-v97 project presence differs"
                )
        else:
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated project presence differs"
            )

        campus_presence = campus_binding.get("presence")
        if campus_presence == "required":
            campus_row = _required_hydrated_row(
                entity_rows,
                "stable_key",
                campus_key,
                campus_binding["row_sha256"],
                "v97 campus",
            )
            if campus_row.get("entity_id") != acceptance["parent_campus_entity_id"]:
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated v97 campus projection differs"
                )
        elif campus_presence == "absent":
            if not (
                absent(entity_rows, "stable_key", campus_key)
                and absent(member_rows, "stable_key", campus_key)
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated post-v97 campus presence differs"
                )
        else:
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated campus presence differs"
            )

        project_member = None
        if project_member_binding.get("presence") == "required":
            project_member = _required_hydrated_row(
                member_rows,
                "stable_key",
                project_key,
                project_member_binding["row_sha256"],
                "v14 project member",
            )
            if project_member.get("component_id") != project_member_binding.get(
                "component_id"
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated project component differs"
                )
        elif project_member_binding.get("presence") != "absent":
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated project-member presence differs"
            )
        elif not absent(member_rows, "stable_key", project_key):
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated project-member absence differs"
            )
        campus_member = None
        if campus_member_binding.get("presence") == "required":
            campus_member = _required_hydrated_row(
                member_rows,
                "stable_key",
                campus_key,
                campus_member_binding["row_sha256"],
                "v14 campus member",
            )
            if campus_member.get("component_id") != campus_member_binding.get(
                "component_id"
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated campus component differs"
                )
        elif campus_member_binding.get("presence") != "absent":
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated campus-member presence differs"
            )
        elif not absent(member_rows, "stable_key", campus_key):
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated campus-member absence differs"
            )
        if topology_binding.get("presence") == "required":
            relationship = _required_hydrated_row(
                relationship_rows,
                "relationship_id",
                topology_binding["relationship_id"],
                topology_binding["row_sha256"],
                "v14 topology",
            )
            if (
                project_member is None
                or campus_member is None
                or relationship.get("relationship_type") != "project_targets"
                or relationship.get("subject_component_id")
                != project_member["component_id"]
                or relationship.get("object_component_id")
                != campus_member["component_id"]
                or relationship.get("relationship_id")
                != acceptance["relationship"]["relationship_id"]
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated topology projection differs"
                )
        elif topology_binding.get("presence") != "absent":
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated topology presence differs"
            )


def _selection_accounting(
    contract: Mapping[str, Any],
    acceptances: Sequence[Mapping[str, Any]],
    *,
    hydrated: bool,
) -> dict[str, Any]:
    accounting = contract.get("source_selection_accounting")
    if not isinstance(accounting, dict):
        raise VerifiedConstructionCoreError("v0.17 source accounting differs")
    base_report = v16._load_json(LEGACY_PREVIEW_V16_DIR / "selection-report.json")
    base_accounting = base_report.get("source_selection_accounting")
    lineage_rows = contract.get("source_lineage")
    promotions = accounting.get("v17_v97_promotions")
    if (
        not isinstance(base_accounting, dict)
        or not isinstance(lineage_rows, list)
        or not isinstance(promotions, list)
        or any(not isinstance(row, dict) for row in promotions)
    ):
        raise VerifiedConstructionCoreError("v0.17 source accounting differs")
    pipeline_project_keys = {
        row.get("project_stable_key")
        for row in lineage_rows
        if isinstance(row, dict)
        and row.get("v97_project", {}).get("presence") == "pipeline"
    }
    promotion_by_key = {row.get("project_stable_key"): row for row in promotions}
    if (
        None in pipeline_project_keys
        or len(promotion_by_key) != len(promotions)
        or set(promotion_by_key) != pipeline_project_keys
    ):
        raise VerifiedConstructionCoreError("v0.17 v97 promotion inventory differs")
    base_failures = base_accounting.get("resulting_v97_first_failure_counts")
    if not isinstance(base_failures, dict):
        raise VerifiedConstructionCoreError("v0.17 frozen v97 accounting differs")
    failures = Counter(base_failures)
    for project_key in sorted(promotion_by_key):
        reason = promotion_by_key[project_key].get("frozen_v16_first_failure")
        if (
            reason == "selected"
            or not isinstance(reason, str)
            or failures.get(reason, 0) <= 0
        ):
            raise VerifiedConstructionCoreError("v0.17 v97 promotion reason differs")
        failures[reason] -= 1
        failures["selected"] += 1
    acceptance_keys = {row["project_stable_key"] for row in acceptances}
    post_v97_keys = sorted(
        set(base_accounting.get("post_v97_selected_project_keys", []))
        | (acceptance_keys - pipeline_project_keys)
    )
    expected = {
        "artifact_selected_projects": V17_EXPECTED_PROJECT_COUNT,
        "derivation": (
            "Start with the frozen v0.16 first-failure ledger; promote the 16 "
            "reviewed v97 projects enumerated below, then append four portable "
            "post-v97 projects while preserving the two post-v97 v0.16 projects."
        ),
        "frozen_v16_first_failure_counts": base_failures,
        "frozen_v16_preview_id": v16.CURRENT_V16_PREVIEW_ID,
        "post_v97_selected_project_keys": post_v97_keys,
        "post_v97_selected_projects": len(post_v97_keys),
        "resulting_v97_first_failure_counts": dict(sorted(failures.items())),
        "v17_v97_promotions": [
            promotion_by_key[key] for key in sorted(promotion_by_key)
        ],
        "v97_nonselected_source_rows": (
            base_accounting["v97_nonselected_source_rows"] - len(promotions)
        ),
        "v97_pipeline_rows": base_accounting["v97_pipeline_rows"],
        "v97_selected_projects": (
            base_accounting["v97_selected_projects"] + len(promotions)
        ),
    }
    if accounting != expected:
        raise VerifiedConstructionCoreError(
            "v0.17 derived source-selection accounting differs"
        )
    if hydrated:
        pipeline_rows = v16._load_csv(v16.SOURCE_RELEASE / "construction_pipeline.csv")
        pipeline_by_key = {row["stable_key"]: row for row in pipeline_rows}
        base_projects = v16._load_csv(
            LEGACY_PREVIEW_V16_DIR / "projects.csv", PROJECT_FIELDS
        )
        base_selected_keys = {
            row["project_stable_key"]
            for row in base_projects
            if row["project_stable_key"] in pipeline_by_key
        }
        for project_key, promotion in promotion_by_key.items():
            source_row = pipeline_by_key.get(project_key)
            if (
                source_row is None
                or v16._first_failure(dict(source_row), base_selected_keys)
                != promotion["frozen_v16_first_failure"]
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated promotion reason differs"
                )
        selected_keys = base_selected_keys | pipeline_project_keys
        hydrated_failures = Counter(
            v16._first_failure(dict(row), selected_keys) for row in pipeline_rows
        )
        successor_promotions = base_accounting.get("v16_successor_status_promotions")
        if not isinstance(successor_promotions, list) or any(
            not isinstance(key, str) for key in successor_promotions
        ):
            raise VerifiedConstructionCoreError(
                "v0.17 frozen successor-status accounting differs"
            )
        for project_key in successor_promotions:
            source_row = pipeline_by_key.get(project_key)
            if (
                source_row is None
                or project_key not in base_selected_keys
                or v16._first_failure(dict(source_row), selected_keys)
                != "status_outside_90_day_window"
                or hydrated_failures["status_outside_90_day_window"] <= 0
            ):
                raise VerifiedConstructionCoreError(
                    "v0.17 hydrated successor-status accounting differs"
                )
            hydrated_failures["status_outside_90_day_window"] -= 1
            hydrated_failures["selected"] += 1
        if (
            len(pipeline_rows) != accounting["v97_pipeline_rows"]
            or dict(sorted(hydrated_failures.items()))
            != accounting["resulting_v97_first_failure_counts"]
        ):
            raise VerifiedConstructionCoreError(
                "v0.17 hydrated source-selection accounting differs"
            )
    return dict(accounting)


def _contracts() -> dict[str, Any]:
    for path, digest, label in (
        (V17_BATCH_CONTRACT, V17_BATCH_CONTRACT_SHA256, "batch contract"),
        (V17_GEOMETRY_CAPTURE, V17_GEOMETRY_CAPTURE_SHA256, "geometry capture"),
    ):
        if path.is_symlink() or not path.is_file() or v16._sha256_file(path) != digest:
            raise VerifiedConstructionCoreError(f"v0.17 {label} hash differs")
    contract = v16._load_json(V17_BATCH_CONTRACT)
    capture = v16._load_json(V17_GEOMETRY_CAPTURE)
    base = contract.get("base_preview", {})
    capture_binding = contract.get("geometry_capture", {})
    if (
        contract.get("contract_id") != "verified-construction-core-v0.17-100-site-batch"
        or contract.get("reviewed_as_of")
        != CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat()
        or contract.get("cohort_lifecycle_reference_date")
        != CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat()
        or base
        != {
            "commit": LEGACY_PREVIEW_V16_COMMIT,
            "manifest_sha256": LEGACY_PREVIEW_V16_MANIFEST_SHA256,
            "path": LEGACY_PREVIEW_V16_DIR.relative_to(ROOT).as_posix(),
            "preview_id": v16.CURRENT_V16_PREVIEW_ID,
        }
        or capture.get("capture_id")
        != "verified-construction-core-v0.17-100-site-geometry-facts"
        or capture.get("captured_on")
        != CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat()
        or capture.get("cohort_lifecycle_reference_date")
        != CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat()
        or capture_binding
        != {
            "bytes": V17_GEOMETRY_CAPTURE.stat().st_size,
            "capture_id": capture["capture_id"],
            "evidence_document_count": len(capture.get("source_documents", [])),
            "geometry_record_count": len(capture.get("results", [])),
            "path": V17_GEOMETRY_CAPTURE.relative_to(ROOT).as_posix(),
            "sha256": V17_GEOMETRY_CAPTURE_SHA256,
        }
    ):
        raise VerifiedConstructionCoreError("v0.17 batch contract differs")
    acceptances = contract.get("acceptances")
    documents = capture.get("source_documents")
    results = capture.get("results")
    lineage = contract.get("source_lineage")
    if (
        not isinstance(acceptances, list)
        or len(acceptances) != V17_EXPECTED_DELTA_COUNT
        or any(not isinstance(row, dict) for row in acceptances)
        or not isinstance(documents, list)
        or not documents
        or any(not isinstance(row, dict) for row in documents)
        or not isinstance(results, list)
        or len(results) != V17_EXPECTED_DELTA_COUNT
        or any(not isinstance(row, dict) for row in results)
        or not isinstance(lineage, list)
        or len(lineage) != V17_EXPECTED_DELTA_COUNT
    ):
        raise VerifiedConstructionCoreError("v0.17 batch inventory differs")
    acceptance_by_key = {row.get("project_stable_key"): row for row in acceptances}
    lineage_by_key = {row.get("project_stable_key"): row for row in lineage}
    documents_by_id = {row.get("source_id"): row for row in documents}
    results_by_id = {row.get("locator_id"): row for row in results}
    if (
        len(acceptance_by_key) != V17_EXPECTED_DELTA_COUNT
        or set(lineage_by_key) != set(acceptance_by_key)
        or len(documents_by_id) != len(documents)
        or len(results_by_id) != V17_EXPECTED_DELTA_COUNT
    ):
        raise VerifiedConstructionCoreError("v0.17 batch identities differ")
    for document in documents:
        capture_details = document.get("capture")
        if (
            not isinstance(document.get("source_id"), str)
            or not document["source_id"]
            or not isinstance(document.get("content_hash"), str)
            or len(document["content_hash"]) != 64
            or not isinstance(capture_details, dict)
            or capture_details.get("bytes", 0) <= 0
            or capture_details.get("sha256") != document["content_hash"]
            or not isinstance(capture_details.get("capture_kind"), str)
            or capture_details.get("redistributed") is not False
            or not isinstance(document.get("license"), str)
            or not document["license"]
            or not isinstance(document.get("attribution"), str)
            or not document["attribution"]
        ):
            raise VerifiedConstructionCoreError("v0.17 raw-source guardrail differs")
        _capture_evidence(document)
    sources: dict[str, Mapping[str, Any]] = {}
    geometries_by_id: dict[str, dict[str, Any]] = {}
    campuses: set[str] = set()
    bound_document_ids: set[str] = set()
    for project_key, acceptance in acceptance_by_key.items():
        campus_key = acceptance.get("parent_campus_stable_key")
        source_binding = acceptance.get("source_input", {})
        source_path = v16._repository_input(
            source_binding.get("path", ""),
            source_binding.get("sha256", ""),
            "v0.17 curated source",
        )
        if source_path.stat().st_size != source_binding.get("bytes"):
            raise VerifiedConstructionCoreError(
                f"v0.17 source bytes differ: {project_key}"
            )
        source = v16._load_json(source_path)
        project = source.get("project")
        campus = source.get("campus")
        result = results_by_id.get(acceptance.get("locator_id"))
        if (
            not isinstance(project, dict)
            or not isinstance(campus, dict)
            or project.get("stable_key") != project_key
            or campus.get("stable_key") != campus_key
            or campus_key in campuses
            or project.get("country") != campus.get("country")
            or project.get("country") not in V17_COUNTRY_ISO_A2
            or acceptance.get("project_entity_id")
            != v16.atlas_stable_id("entity", project_key, "project")
            or acceptance.get("parent_campus_entity_id")
            != v16.atlas_stable_id("entity", campus_key, "campus")
            or not isinstance(result, dict)
            or result.get("project_stable_key") != project_key
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 source or locator identity differs: {project_key}"
            )
        source_ids = result.get("geometry_source_document_ids")
        identity_source_ids = result.get("identity_source_document_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not isinstance(identity_source_ids, list)
            or result.get("geometry_source_document_id") != source_ids[0]
            or len(source_ids) != len(set(source_ids))
            or len(identity_source_ids) != len(set(identity_source_ids))
            or any(source_id not in documents_by_id for source_id in source_ids)
            or any(
                source_id not in documents_by_id for source_id in identity_source_ids
            )
            or (set(source_ids) | set(identity_source_ids)) & bound_document_ids
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 geometry source identity differs: {project_key}"
            )
        bound_document_ids.update(set(source_ids) | set(identity_source_ids))
        geometry = _canonical_geometry(result)
        anchor = result.get("display_anchor", {}).get("coordinates")
        if (
            not isinstance(anchor, list)
            or len(anchor) != 2
            or any(type(number) not in {int, float} for number in anchor)
            or not (-180 <= anchor[0] <= 180 and -90 <= anchor[1] <= 90)
            or (geometry["type"] == "Point" and anchor != geometry["coordinates"])
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 display anchor differs: {project_key}"
            )
        semantics = result.get("semantics")
        if not isinstance(semantics, dict):
            raise VerifiedConstructionCoreError(
                f"v0.17 geometry semantics differ: {project_key}"
            )
        uncertainty = semantics.get("horizontal_uncertainty_metres")
        unknown_reason = semantics.get("horizontal_uncertainty_unknown_reason")
        if (
            semantics.get("geometry_authority_class")
            not in {"official_source", "community_source"}
            or semantics.get("geometry_use_scope")
            not in {"campus_locator", "project_locator"}
            or semantics.get("geometry_source_entity_kind") not in {"campus", "project"}
            or semantics.get("official_boundary") is not False
            or not isinstance(semantics.get("precision_scope"), str)
            or not semantics["precision_scope"]
            or (uncertainty is None)
            == (not isinstance(unknown_reason, str) or not unknown_reason)
            or (
                uncertainty is not None
                and (type(uncertainty) not in {int, float} or uncertainty <= 0)
            )
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 geometry semantics differ: {project_key}"
            )
        relationship = acceptance.get("relationship", {})
        topology_binding = lineage_by_key[project_key].get("v14_topology", {})
        if (
            relationship.get("decision_basis") != "explicit_parent"
            or relationship.get("relationship_type") != "project_targets"
            or relationship.get("origin") not in {"v14", "source_local"}
            or (
                relationship.get("origin") == "v14"
                and (
                    topology_binding.get("presence") != "required"
                    or topology_binding.get("relationship_id")
                    != relationship.get("relationship_id")
                )
            )
            or (
                relationship.get("origin") == "source_local"
                and topology_binding.get("presence") != "absent"
            )
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 project-to-campus relationship differs: {project_key}"
            )
        if relationship["origin"] == "source_local" and relationship.get(
            "relationship_id"
        ) != _source_local_relationship_id(
            acceptance["project_entity_id"],
            acceptance["parent_campus_entity_id"],
            source_binding["sha256"],
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 source-local topology differs: {project_key}"
            )
        status = acceptance.get("status")
        lifecycle = [
            row
            for row in source.get("lifecycle", [])
            if isinstance(row, dict)
            and row.get("entity") == "project"
            and isinstance(status, dict)
            and row.get("evidence_key") == status.get("evidence_key")
        ]
        if (
            not isinstance(status, dict)
            or len(lifecycle) != 1
            or any(
                lifecycle[0].get(field) != status.get(field)
                for field in ("value", "as_of_date", "method", "confidence")
            )
            or status.get("value") not in v16.PHYSICAL_STATUSES
            or status.get("method") not in v16.AUTHORITATIVE_STATUS_METHODS
        ):
            raise VerifiedConstructionCoreError(
                f"v0.17 lifecycle differs: {project_key}"
            )
        status_date = v16._calendar_date(status["as_of_date"], "v0.17 status")
        age = (CURRENT_V17_LIFECYCLE_REFERENCE_DATE - status_date).days
        if not 0 <= age <= v16.MAX_STATUS_AGE_DAYS:
            raise VerifiedConstructionCoreError(
                f"v0.17 lifecycle window differs: {project_key}"
            )
        _source_evidence(source, status["evidence_key"], status["evidence_id"])
        location = acceptance.get("location_evidence")
        if not isinstance(location, dict):
            raise VerifiedConstructionCoreError(
                f"v0.17 location evidence differs: {project_key}"
            )
        _source_evidence(source, location["key"], location["evidence_id"])
        sources[project_key] = source
        geometries_by_id[acceptance["locator_id"]] = geometry
        campuses.add(campus_key)
    if len(campuses) != V17_EXPECTED_DELTA_COUNT:
        raise VerifiedConstructionCoreError("v0.17 physical-site inventory differs")
    if bound_document_ids != set(documents_by_id):
        raise VerifiedConstructionCoreError("v0.17 unbound capture document differs")
    invariants = {
        "accepted_physical_site_count": V17_EXPECTED_DELTA_COUNT,
        "accepted_project_count": V17_EXPECTED_DELTA_COUNT,
        "geometry_authority_classes": dict(
            sorted(
                Counter(
                    result["semantics"]["geometry_authority_class"]
                    for result in results
                ).items()
            )
        ),
        "geometry_types": dict(
            sorted(
                Counter(
                    geometry["type"] for geometry in geometries_by_id.values()
                ).items()
            )
        ),
        "geometry_use_scopes": dict(
            sorted(
                Counter(
                    result["semantics"]["geometry_use_scope"] for result in results
                ).items()
            )
        ),
        "independent_imagery_verification": False,
        "numeric_horizontal_uncertainty_rows": sum(
            result["semantics"]["horizontal_uncertainty_metres"] is not None
            for result in results
        ),
        "official_boundary": False,
        "raw_source_artifacts_redistributed": False,
    }
    if contract.get("batch_invariants") != invariants:
        raise VerifiedConstructionCoreError("v0.17 batch invariants differ")
    base_contract = v16._load_json(v16.V16_BATCH_CONTRACT)
    if contract.get("hydrated_crosscheck_inputs") != base_contract.get(
        "hydrated_crosscheck_inputs"
    ):
        raise VerifiedConstructionCoreError("v0.17 hydrated crosscheck binding differs")
    hydrated = v16._v14_hydrated_crosscheck_available(contract)
    if hydrated:
        _validate_hydrated_lineage(contract, acceptances)
    accounting = _selection_accounting(contract, acceptances, hydrated=hydrated)
    for actual, expected, label in (
        (results_by_id, V17_REVIEWED_LOCATOR_SHA256, "reviewed locator facts"),
        (
            documents_by_id,
            V17_REVIEWED_SOURCE_DOCUMENT_SHA256,
            "reviewed source document",
        ),
        (lineage_by_key, V17_REVIEWED_LINEAGE_SHA256, "reviewed lineage"),
    ):
        if set(actual) != set(expected) or any(
            v16._sha256_bytes(v16._json_bytes(row)) != expected[key]
            for key, row in actual.items()
        ):
            raise VerifiedConstructionCoreError(f"v0.17 {label} differs")
    for project_key, acceptance in acceptance_by_key.items():
        lineage_row = lineage_by_key[project_key]
        if (
            lineage_row["current_status_lineage"]["evidence_id"]
            != acceptance["status"]["evidence_id"]
            or lineage_row["location_evidence_lineage"]["evidence_id"]
            != acceptance["location_evidence"]["evidence_id"]
        ):
            raise VerifiedConstructionCoreError(
                "v0.17 portable evidence lineage differs"
            )
    return {
        "contract": contract,
        "capture": capture,
        "acceptances": sorted(acceptances, key=lambda row: row["project_stable_key"]),
        "documents_by_id": documents_by_id,
        "geometries_by_id": geometries_by_id,
        "results_by_id": results_by_id,
        "sources": sources,
        "source_selection_accounting": accounting,
        "batch_invariants": invariants,
    }


def _build_delta_rows(contracts: Mapping[str, Any]) -> dict[str, Any]:
    evidence_pool: dict[str, dict[str, Any]] = {}
    evidence_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    projects: list[dict[str, Any]] = []
    sites: list[dict[str, Any]] = []
    for acceptance in contracts["acceptances"]:
        project_key = acceptance["project_stable_key"]
        project_id = acceptance["project_entity_id"]
        campus_key = acceptance["parent_campus_stable_key"]
        source = contracts["sources"][project_key]
        project = source["project"]
        campus = source["campus"]
        status = acceptance["status"]
        location = acceptance["location_evidence"]
        result = contracts["results_by_id"][acceptance["locator_id"]]
        semantics = result["semantics"]
        for binding, role in (
            (status, "physical_status"),
            (location, "context:source_location_identity"),
        ):
            key = binding.get("evidence_key", binding.get("key"))
            evidence_id = binding["evidence_id"]
            projected = _source_evidence(source, key, evidence_id)
            previous = evidence_pool.get(evidence_id)
            if previous is not None and previous != projected:
                raise VerifiedConstructionCoreError(
                    f"v0.17 evidence collision differs: {project_key}"
                )
            evidence_pool[evidence_id] = projected
            evidence_usage[evidence_id]["roles"].add(role)
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        geometry_evidence_ids = []
        for source_id in result["geometry_source_document_ids"]:
            projected = _capture_evidence(contracts["documents_by_id"][source_id])
            evidence_id = projected["evidence_id"]
            previous = evidence_pool.get(evidence_id)
            if previous is not None and previous != projected:
                raise VerifiedConstructionCoreError(
                    f"v0.17 geometry evidence collision differs: {project_key}"
                )
            evidence_pool[evidence_id] = projected
            evidence_usage[evidence_id]["roles"].add("geometry")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
            geometry_evidence_ids.append(evidence_id)
        for source_id in result["identity_source_document_ids"]:
            projected = _capture_evidence(contracts["documents_by_id"][source_id])
            evidence_id = projected["evidence_id"]
            previous = evidence_pool.get(evidence_id)
            if previous is not None and previous != projected:
                raise VerifiedConstructionCoreError(
                    f"v0.17 identity evidence collision differs: {project_key}"
                )
            evidence_pool[evidence_id] = projected
            evidence_usage[evidence_id]["roles"].add("context:geometry_identity")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        primary_document = contracts["documents_by_id"][
            result["geometry_source_document_id"]
        ]
        primary_geometry_evidence_id = _capture_evidence(primary_document)[
            "evidence_id"
        ]
        geometry = contracts["geometries_by_id"][acceptance["locator_id"]]
        longitude, latitude = result["display_anchor"]["coordinates"]
        geometry_json = v16._json_bytes(geometry).decode().strip()
        site_id = v16._stable_id("vcc-site", campus_key)
        country = project["country"]
        status_date = v16._calendar_date(status["as_of_date"], "v0.17 status")
        uncertainty = semantics["horizontal_uncertainty_metres"]
        uncertainty_text = "" if uncertainty is None else str(uncertainty)
        unknown_reason = semantics["horizontal_uncertainty_unknown_reason"]
        project_row = {
            "project_id": project_id,
            "project_stable_key": project_key,
            "site_id": site_id,
            "physical_site_stable_key": campus_key,
            "name": project["name"],
            "country": country,
            "country_iso_a2": V17_COUNTRY_ISO_A2[country],
            "latitude": latitude,
            "longitude": longitude,
            "geometry_json": geometry_json,
            "geometry_type": geometry["type"],
            "geometry_source_entity_kind": semantics["geometry_source_entity_kind"],
            "geometry_derivation": semantics["geometry_derivation"],
            "geometry_method": semantics["geometry_method"],
            "geometry_scope_class": semantics["geometry_scope_class"],
            "geometry_authority_class": semantics["geometry_authority_class"],
            "geometry_use_scope": semantics["geometry_use_scope"],
            "geometry_precision_scope": semantics["precision_scope"],
            "horizontal_uncertainty_metres": uncertainty_text,
            "horizontal_uncertainty_unknown_reason": unknown_reason,
            "geometry_evidence_id": primary_geometry_evidence_id,
            "last_observed_physical_status": status["value"],
            "status_as_of": status["as_of_date"],
            "status_age_days_at_review": (
                CURRENT_V17_LIFECYCLE_REFERENCE_DATE - status_date
            ).days,
            "status_method": status["method"],
            "status_evidence_id": status["evidence_id"],
            "verification_posture": v16._verification_posture(
                semantics["geometry_authority_class"],
                semantics["geometry_use_scope"],
            ),
            "independent_imagery_verification": "false",
            "imagery_review_outcome": "not_reviewed_for_core_preview",
            "development_type": "unknown",
            "development_type_unknown_reason": "not selected by the v0.17 100-site batch",
            "operating_model": "unknown",
            "operating_model_unknown_reason": "not established by selected evidence",
            "operating_model_evidence_id": "",
            "workloads_json": "[]",
            "workload_unknown_reason": "not established by selected evidence",
            "role_claims_json": "[]",
            "power_observations_json": "[]",
            "power_unknown_reason": (
                "no typed project power observation selected by this batch; not estimated"
            ),
            "annual_energy_observations_json": "[]",
            "annual_energy_unknown_reason": (
                "no scoped annual-energy inputs selected; not estimated"
            ),
            "efficiency_observations_json": "[]",
            "efficiency_unknown_reason": "no scoped PUE or WUE observation selected",
            "owner": "",
            "operator": "",
            "users": "",
            "tenants": "",
            "customers": "",
            "status_source_url": evidence_pool[status["evidence_id"]]["source_url"],
            "geometry_source_url": primary_document["source_url"],
        }
        projects.append(project_row)
        sites.append(
            {
                "site_id": site_id,
                "physical_site_stable_key": campus_key,
                "name": campus["name"],
                "country": country,
                "country_iso_a2": V17_COUNTRY_ISO_A2[country],
                "latitude": latitude,
                "longitude": longitude,
                "geometry_json": geometry_json,
                "geometry_type": geometry["type"],
                "geometry_source_entity_kinds_json": v16._json_bytes(
                    [semantics["geometry_source_entity_kind"]]
                )
                .decode()
                .strip(),
                "geometry_derivations_json": v16._json_bytes(
                    [semantics["geometry_derivation"]]
                )
                .decode()
                .strip(),
                "geometry_methods_json": v16._json_bytes([semantics["geometry_method"]])
                .decode()
                .strip(),
                "geometry_scope_classes_json": v16._json_bytes(
                    [semantics["geometry_scope_class"]]
                )
                .decode()
                .strip(),
                "geometry_authority_classes_json": v16._json_bytes(
                    [semantics["geometry_authority_class"]]
                )
                .decode()
                .strip(),
                "geometry_use_scopes_json": v16._json_bytes(
                    [semantics["geometry_use_scope"]]
                )
                .decode()
                .strip(),
                "geometry_precision_scopes_json": v16._json_bytes(
                    [semantics["precision_scope"]]
                )
                .decode()
                .strip(),
                "horizontal_uncertainty_metres": uncertainty_text,
                "horizontal_uncertainty_unknown_reason": unknown_reason,
                "geometry_evidence_ids_json": v16._json_bytes(geometry_evidence_ids)
                .decode()
                .strip(),
                "project_count": 1,
                "project_ids_json": v16._json_bytes([project_id]).decode().strip(),
                "project_stable_keys_json": v16._json_bytes([project_key])
                .decode()
                .strip(),
                "statuses_json": v16._json_bytes([status["value"]]).decode().strip(),
                "oldest_status_as_of": status["as_of_date"],
                "newest_status_as_of": status["as_of_date"],
                "verification_posture": project_row["verification_posture"],
                "independent_imagery_verification": "false",
                "imagery_review_outcomes_json": v16._json_bytes(
                    ["not_reviewed_for_core_preview"]
                )
                .decode()
                .strip(),
            }
        )
    evidence_rows = [
        {
            **evidence_pool[evidence_id],
            "roles_json": v16._json_bytes(sorted(usage["roles"])).decode().strip(),
            "project_ids_json": v16._json_bytes(sorted(usage["project_ids"]))
            .decode()
            .strip(),
        }
        for evidence_id, usage in sorted(evidence_usage.items())
    ]
    if (
        len(projects) != V17_EXPECTED_DELTA_COUNT
        or len(sites) != V17_EXPECTED_DELTA_COUNT
        or len({row["project_id"] for row in projects}) != V17_EXPECTED_DELTA_COUNT
        or len({row["site_id"] for row in sites}) != V17_EXPECTED_DELTA_COUNT
        or len({row["evidence_id"] for row in evidence_rows}) != len(evidence_rows)
    ):
        raise VerifiedConstructionCoreError("v0.17 delta accounting differs")
    return {"projects": projects, "sites": sites, "evidence": evidence_rows}


def _portable_source_inputs(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    base_manifest = v16._load_json(LEGACY_PREVIEW_V16_DIR / "manifest.json")
    by_path = {
        row["path"]: dict(row) for row in base_manifest["portable_source_inputs"]
    }
    additions = [
        {
            "path": V17_BATCH_CONTRACT.relative_to(ROOT).as_posix(),
            "bytes": V17_BATCH_CONTRACT.stat().st_size,
            "sha256": V17_BATCH_CONTRACT_SHA256,
            "parent_manifests": [],
        },
        {
            "path": V17_GEOMETRY_CAPTURE.relative_to(ROOT).as_posix(),
            "bytes": V17_GEOMETRY_CAPTURE.stat().st_size,
            "sha256": V17_GEOMETRY_CAPTURE_SHA256,
            "parent_manifests": [],
        },
        *(
            {**acceptance["source_input"], "parent_manifests": []}
            for acceptance in contracts["acceptances"]
        ),
    ]
    for row in additions:
        existing = by_path.get(row["path"])
        if existing is not None and existing != row:
            raise VerifiedConstructionCoreError(
                f"v0.17 portable input collision differs: {row['path']}"
            )
        by_path[row["path"]] = row
    rows = [by_path[path] for path in sorted(by_path)]
    for row in rows:
        source_path = v16._repository_input(
            row["path"], row["sha256"], "v0.17 portable input"
        )
        if source_path.stat().st_size != row["bytes"]:
            raise VerifiedConstructionCoreError(
                f"v0.17 portable input bytes differ: {row['path']}"
            )
    return rows


def _review_queue(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for acceptance in contracts["acceptances"]:
        result = contracts["results_by_id"][acceptance["locator_id"]]
        semantics = result["semantics"]
        geometry_documents = [
            contracts["documents_by_id"][source_id]
            for source_id in result["geometry_source_document_ids"]
        ]
        evidence_ids = [
            _capture_evidence(row)["evidence_id"] for row in geometry_documents
        ]
        rows.append(
            {
                "batch_contract_path": V17_BATCH_CONTRACT.relative_to(ROOT).as_posix(),
                "batch_contract_sha256": V17_BATCH_CONTRACT_SHA256,
                "decision": "accepted",
                "decision_reason": acceptance["scope_guardrail"],
                "geometry_authority_class": semantics["geometry_authority_class"],
                "geometry_derivation": semantics["geometry_derivation"],
                "geometry_entity": semantics["geometry_source_entity_kind"],
                "geometry_evidence_id": evidence_ids[0],
                "geometry_evidence_ids": evidence_ids,
                "geometry_evidence_key": geometry_documents[0]["source_id"],
                "geometry_method": semantics["geometry_method"],
                "geometry_scope_class": semantics["geometry_scope_class"],
                "geometry_target_entity_id": (
                    acceptance["project_entity_id"]
                    if semantics["geometry_source_entity_kind"] == "project"
                    else acceptance["parent_campus_entity_id"]
                ),
                "geometry_target_entity_kind": semantics["geometry_source_entity_kind"],
                "geometry_target_entity_stable_key": (
                    acceptance["project_stable_key"]
                    if semantics["geometry_source_entity_kind"] == "project"
                    else acceptance["parent_campus_stable_key"]
                ),
                "geometry_use_scope": semantics["geometry_use_scope"],
                "horizontal_uncertainty_metres": semantics[
                    "horizontal_uncertainty_metres"
                ],
                "horizontal_uncertainty_unknown_reason": semantics[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "locator_id": acceptance["locator_id"],
                "official_boundary": False,
                "precision_scope": semantics["precision_scope"],
                "project_to_campus_decision_basis": "explicit_parent",
                "project_to_campus_relationship_id": acceptance["relationship"][
                    "relationship_id"
                ],
                "project_to_campus_relationship_type": "project_targets",
                "rejected_claims": contracts["contract"]["rejected_claims"],
                "reviewed_at": CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat(),
                "source_input_bytes": acceptance["source_input"]["bytes"],
                "source_input_path": acceptance["source_input"]["path"],
                "source_input_sha256": acceptance["source_input"]["sha256"],
                "source_project_entity_id": acceptance["project_entity_id"],
                "source_project_stable_key": acceptance["project_stable_key"],
            }
        )
    return rows


def _context_evidence_bindings(contracts: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "evidence_id": acceptance["location_evidence"]["evidence_id"],
            "evidence_key": acceptance["location_evidence"]["key"],
            "project_stable_key": acceptance["project_stable_key"],
            "semantic_scope": acceptance["scope_guardrail"],
            "source_input_path": acceptance["source_input"]["path"],
            "source_input_sha256": acceptance["source_input"]["sha256"],
            "usage_role": "geometry_identity",
        }
        for acceptance in contracts["acceptances"]
    ]
    for acceptance in contracts["acceptances"]:
        result = contracts["results_by_id"][acceptance["locator_id"]]
        for source_id in result["identity_source_document_ids"]:
            document = contracts["documents_by_id"][source_id]
            rows.append(
                {
                    "evidence_id": document["evidence_id"],
                    "evidence_key": source_id,
                    "project_stable_key": acceptance["project_stable_key"],
                    "semantic_scope": acceptance["scope_guardrail"],
                    "source_input_path": V17_GEOMETRY_CAPTURE.relative_to(
                        ROOT
                    ).as_posix(),
                    "source_input_sha256": V17_GEOMETRY_CAPTURE_SHA256,
                    "usage_role": "geometry_identity",
                }
            )
    return rows


def _map_html(
    geojson: Mapping[str, Any],
    sites: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> bytes:
    document = v16._v16_map_html(geojson, sites, evidence).decode("utf-8")
    old_title = "Verified Construction Core v0.16 preview"
    if document.count(old_title) != 1:
        raise VerifiedConstructionCoreError("v0.17 map title seam differs")
    document = document.replace(
        old_title, "Verified Construction Core v0.17 preview", 1
    )
    marker = '. <a href="ATTRIBUTION.txt">Full attribution and source terms</a>.'
    notice = (
        ' · Crown copyright — <a href="https://data.linz.govt.nz/layer/50772-nz-primary-parcels/">'
        "Land Information New Zealand (LINZ)</a>, "
        '<a href="https://data.linz.govt.nz/license/attribution-4-0-international/">CC BY 4.0</a>'
        ' · Klimadatastyrelsen / Danmarks Adresseregister (DAR), '
        '<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'
        ' · Contains information licensed under the '
        '<a href="https://open.alberta.ca/licence">Open Government Licence – Alberta</a>'
        " (Government of Alberta)"
        " · v0.17 locator-source rights and precision limits are enumerated per row"
    )
    if document.count(marker) != 1:
        raise VerifiedConstructionCoreError("v0.17 map attribution seam differs")
    return document.replace(marker, f"{notice}{marker}", 1).encode("utf-8")


def _schema(contracts: Mapping[str, Any]) -> dict[str, Any]:
    schema = v16._v16_schema()
    base_projects = v16._load_csv(
        LEGACY_PREVIEW_V16_DIR / "projects.csv", PROJECT_FIELDS
    )
    results = contracts["capture"]["results"]
    field_values = {
        "geometry_type": {
            *(row["geometry_type"] for row in base_projects),
            *(row["geometry"]["type"] for row in results),
        },
        "geometry_source_entity_kind": {
            *(row["geometry_source_entity_kind"] for row in base_projects),
            *(row["semantics"]["geometry_source_entity_kind"] for row in results),
        },
        "geometry_derivation": {
            *(row["geometry_derivation"] for row in base_projects),
            *(row["semantics"]["geometry_derivation"] for row in results),
        },
        "geometry_authority_class": {
            *(row["geometry_authority_class"] for row in base_projects),
            *(row["semantics"]["geometry_authority_class"] for row in results),
        },
        "geometry_use_scope": {
            *(row["geometry_use_scope"] for row in base_projects),
            *(row["semantics"]["geometry_use_scope"] for row in results),
        },
    }
    for definition in schema["tables"]["projects.csv"]["fields"]:
        if definition["name"] in field_values:
            definition["allowed_values"] = sorted(field_values[definition["name"]])
    for definition in schema["tables"]["sites.csv"]["fields"]:
        if definition["name"] == "geometry_type":
            definition["allowed_values"] = sorted(field_values["geometry_type"])
    schema["geojson"]["allowed_geometry_types"] = sorted(field_values["geometry_type"])
    schema["format"] = "datacenter-atlas-verified-construction-core-schema-v17"
    schema["preview_id"] = CURRENT_V17_PREVIEW_ID
    schema["v0_17_one_hundred_site_batch"] = {
        **contracts["batch_invariants"],
        "coordinate_semantics": (
            "Every v0.17 geometry is an explicitly reviewed project or campus locator. "
            "No locator is promoted to an official parcel, campus boundary, building "
            "footprint, current-work extent, or survey-accuracy claim."
        ),
        "rights_semantics": (
            "Only compact factual projections are redistributed. Raw API responses, "
            "HTML, PDFs, maps, imagery, and all-rights-reserved source artifacts remain "
            "excluded; each geometry evidence row preserves its source-specific licence "
            "or fact-extraction posture."
        ),
    }
    schema["v0_17_source_selection_accounting"] = contracts[
        "source_selection_accounting"
    ]
    schema["v0_17_temporal_scope"] = {
        "cohort_lifecycle_reference_date": (
            CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat()
        ),
        "geometry_identity_reviewed_at": (
            CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat()
        ),
        "reviewed_at_semantics": (
            "Legacy alias for cohort_lifecycle_reference_date; not the later geometry review date."
        ),
    }
    return schema


def _readme(report: Mapping[str, Any], legal_notice: str) -> bytes:
    return f"""# Verified Construction Core v0.17 preview

This tracked, non-final preview contains **{report["selected_physical_site_count"]} physical sites**
and **{report["selected_project_count"]} linked projects** in {len(report["country_counts"])}
countries. The v0.17 delta adds exactly 20 distinct physical sites to the byte-frozen v0.16
artifact. Every new project has a dated authoritative physical-status observation effective no
later than the fixed 2026-08-20 lifecycle cutoff and a separately reviewed locator.

The count and diversity milestones are now met: 100 physical sites and 40 countries. This remains
a preview because imagery-review coverage and the required blind review are incomplete. Those
unmet gates remain explicit in `selection-report.json`, so `publishable_as_final` is false.

All v0.17 geometries are locators, not official boundaries or construction footprints. Source
precision and rights constraints are preserved per row. Raw HTML, PDFs, API responses, map tiles,
imagery, and publisher media are not redistributed. Capacity, energy, efficiency, roles,
workloads, customers, tenants, users, and operating model remain unselected and unknown for all
20 new projects.

## Files

- `projects.csv`: one row per selected physical construction project
- `sites.csv`: one row per distinct physical site
- `sites.geojson`: reviewed locator or boundary geometry for each physical site
- `evidence.csv`: locally bound evidence and exact usage roles
- `selection-report.json`: cohort, provenance, rejection, and release-gate audit
- `schema.json`: field and v0.17 scope semantics
- `map.html`: deterministic offline map; no tile requests
- `manifest.json` and `manifest.sha256`: byte inventory and trust root
- `ATTRIBUTION.txt`: source-specific attribution and terms

## Legal notice

{legal_notice}

This preview is an evidence product, not legal, surveying, investment, engineering, or operational
advice. Unknowns remain unknown, and no capacity, role, workload, energy, efficiency, or lifecycle
claim is inferred from geometry.
""".encode("utf-8")


def _attribution(
    evidence: Sequence[Mapping[str, Any]],
    legal_notice: str,
    contracts: Mapping[str, Any],
) -> bytes:
    document = v16._v16_attribution(evidence, legal_notice).decode("utf-8")
    heading = "Data Center Atlas Verified Construction Core v0.16 preview"
    if document.count(heading) != 1:
        raise VerifiedConstructionCoreError("v0.17 attribution heading seam differs")
    document = document.replace(
        heading, "Data Center Atlas Verified Construction Core v0.17 preview", 1
    )
    marker = "Map-provider terms:\n"
    notice = (
        "v0.17 geometry notice: The 20 new records are locator facts only. Their exact "
        "source, attribution, licence or fact-extraction posture, raw-capture digest, "
        "and precision limitation are preserved in evidence.csv and selection-report.json. "
        "No raw source document, map, API response, imagery, or publisher media is redistributed.\n\n"
    )
    notice += (
        "Contains information licensed under the Open Government Licence – Alberta. "
        "The Alberta quarter-section polygons and LINZ primary parcels are selected and "
        "dissolved into locator unions; the DAR address point is selected without changing "
        "its coordinates. These derived locators do not imply provider endorsement.\n\n"
        "v0.17 captured source credits and rights links:\n"
    )
    for source in contracts["capture"]["source_documents"]:
        links = "; ".join(source.get("rights_urls", [])) or "No separate rights URL captured"
        notice += (
            f"- {source['source_id']}: {source['attribution']} | {source['license']} | "
            f"{source['source_url']} | Rights: {links}\n"
        )
    notice += "\n"
    if document.count(marker) != 1:
        raise VerifiedConstructionCoreError("v0.17 attribution notice seam differs")
    return document.replace(marker, f"{notice}{marker}", 1).encode("utf-8")


def _payloads() -> tuple[dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
    validate_frozen_v16()
    contracts = _contracts()
    base_projects = v16._load_csv(
        LEGACY_PREVIEW_V16_DIR / "projects.csv", PROJECT_FIELDS
    )
    base_sites = v16._load_csv(LEGACY_PREVIEW_V16_DIR / "sites.csv", SITE_FIELDS)
    base_evidence = v16._load_csv(
        LEGACY_PREVIEW_V16_DIR / "evidence.csv", EVIDENCE_FIELDS
    )
    base_report = v16._load_json(LEGACY_PREVIEW_V16_DIR / "selection-report.json")
    delta = _build_delta_rows(contracts)
    if (
        {row["project_id"] for row in base_projects}
        & {row["project_id"] for row in delta["projects"]}
        or {row["site_id"] for row in base_sites}
        & {row["site_id"] for row in delta["sites"]}
        or {row["evidence_id"] for row in base_evidence}
        & {row["evidence_id"] for row in delta["evidence"]}
    ):
        raise VerifiedConstructionCoreError("v0.17 delta identity collision")
    projects = sorted(
        [*base_projects, *delta["projects"]], key=lambda row: row["project_stable_key"]
    )
    sites = sorted(
        [*base_sites, *delta["sites"]], key=lambda row: row["physical_site_stable_key"]
    )
    evidence = sorted(
        [*base_evidence, *delta["evidence"]], key=lambda row: row["evidence_id"]
    )
    if (
        len(projects) != V17_EXPECTED_PROJECT_COUNT
        or len(sites) != V17_EXPECTED_SITE_COUNT
        or len({row["project_id"] for row in projects}) != len(projects)
        or len({row["project_stable_key"] for row in projects}) != len(projects)
        or len({row["site_id"] for row in sites}) != len(sites)
        or len({row["physical_site_stable_key"] for row in sites}) != len(sites)
        or len({row["evidence_id"] for row in evidence}) != len(evidence)
    ):
        raise VerifiedConstructionCoreError("v0.17 cohort count or uniqueness differs")
    by_project = {row["project_id"]: row for row in projects}
    by_site = {row["site_id"]: row for row in sites}
    by_evidence = {row["evidence_id"]: row for row in evidence}
    if (
        any(by_project[row["project_id"]] != row for row in base_projects)
        or any(by_site[row["site_id"]] != row for row in base_sites)
        or any(by_evidence[row["evidence_id"]] != row for row in base_evidence)
    ):
        raise VerifiedConstructionCoreError("v0.17 inherited row changed")
    gates = v16._final_release_gates(sites, projects)
    gates["clean_clone_rebuild"] = {
        "passed": True,
        "reason": "all v0.17 inputs and the frozen v0.16 base are tracked and hash-bound",
    }
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    provenance_decisions = {
        key: list(base_report["provenance_decisions"][key])
        for key in (
            "workload_scope_bindings",
            "role_bindings",
            "excluded_source_roles",
            "context_evidence_bindings",
        )
    }
    provenance_decisions["context_evidence_bindings"].extend(
        _context_evidence_bindings(contracts)
    )
    accounting = contracts["source_selection_accounting"]
    report = {
        **base_report,
        "format": "datacenter-atlas-verified-construction-core-selection-v17",
        "publishable_as_final": all(
            gate.get("passed", False) for gate in gates.values()
        ),
        "reviewed_at": CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat(),
        "cohort_lifecycle_reference_date": (
            CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat()
        ),
        "geometry_identity_reviewed_at": (
            CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat()
        ),
        "selected_project_count": len(projects),
        "selected_physical_site_count": len(sites),
        "selected_evidence_count": len(evidence),
        "official_boundary_project_count": sum(
            v16._is_official_boundary(row) for row in projects
        ),
        "reviewed_site_locator_project_count": sum(
            v16._is_reviewed_locator(row) for row in projects
        ),
        "non_selected_source_row_count": accounting["v97_nonselected_source_rows"],
        "selection_first_failure_counts": accounting[
            "resulting_v97_first_failure_counts"
        ],
        "source_selection_accounting": accounting,
        "country_counts": country_counts,
        "final_release_gates": gates,
        "imagery_review_provenance": list(base_report["imagery_review_provenance"]),
        "provenance_decisions": provenance_decisions,
        "reviewed_overlay_queue": [
            *base_report["reviewed_overlay_queue"],
            *_review_queue(contracts),
        ],
        "one_hundred_site_batch": {
            **contracts["batch_invariants"],
            "batch_contract_path": V17_BATCH_CONTRACT.relative_to(ROOT).as_posix(),
            "batch_contract_sha256": V17_BATCH_CONTRACT_SHA256,
            "capture_path": V17_GEOMETRY_CAPTURE.relative_to(ROOT).as_posix(),
            "capture_sha256": V17_GEOMETRY_CAPTURE_SHA256,
            "capture_source_document_count": len(contracts["documents_by_id"]),
            "project_stable_keys": sorted(
                row["project_stable_key"] for row in contracts["acceptances"]
            ),
            "rejected_claims": contracts["contract"]["rejected_claims"],
        },
    }
    if (
        len(country_counts) != V17_EXPECTED_COUNTRY_COUNT
        or report["official_boundary_project_count"]
        != V17_EXPECTED_OFFICIAL_BOUNDARY_PROJECT_COUNT
        or report["reviewed_site_locator_project_count"]
        != V17_EXPECTED_REVIEWED_LOCATOR_PROJECT_COUNT
        or gates["site_count"] != {"actual": 100, "required": 100, "passed": True}
        or gates["country_count"]
        != {"actual": 40, "required_minimum": 40, "passed": True}
        or gates["imagery_outcomes_complete"]
        != {"actual": 10, "required": 103, "passed": False}
        or report["publishable_as_final"] is not False
        or accounting["artifact_selected_projects"] != len(projects)
        or accounting["v97_selected_projects"]
        != V17_EXPECTED_V97_SELECTED_PROJECT_COUNT
        or accounting["post_v97_selected_projects"]
        != V17_EXPECTED_POST_V97_SELECTED_PROJECT_COUNT
        or accounting["v97_nonselected_source_rows"]
        + accounting["v97_selected_projects"]
        != accounting["v97_pipeline_rows"]
        or any(
            row[field] != "[]"
            for row in delta["projects"]
            for field in (
                "workloads_json",
                "role_claims_json",
                "power_observations_json",
                "annual_energy_observations_json",
                "efficiency_observations_json",
            )
        )
        or any(
            row[field]
            for row in delta["projects"]
            for field in ("owner", "operator", "users", "tenants", "customers")
        )
    ):
        raise VerifiedConstructionCoreError("v0.17 expected accounting differs")
    geojson = v16._geojson(sites)
    geojson["name"] = "Data Center Atlas Verified Construction Core v0.17 preview"
    legal_notice = v16._v10_city_legal_notice_from_base()
    payloads = {
        "ATTRIBUTION.txt": _attribution(evidence, legal_notice, contracts),
        "README.md": _readme(report, legal_notice),
        "evidence.csv": v16._csv_bytes(evidence, EVIDENCE_FIELDS),
        "map.html": _map_html(geojson, sites, evidence),
        "projects.csv": v16._csv_bytes(projects, PROJECT_FIELDS),
        "schema.json": v16._json_bytes(_schema(contracts)),
        "selection-report.json": v16._json_bytes(report),
        "sites.csv": v16._csv_bytes(sites, SITE_FIELDS),
        "sites.geojson": v16._json_bytes(geojson),
    }
    return payloads, report, _portable_source_inputs(contracts)


def _manifest(
    payloads: Mapping[str, bytes],
    report: Mapping[str, Any],
    portable: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-verified-construction-core-preview-v17",
        "preview_id": CURRENT_V17_PREVIEW_ID,
        "release_status": "preview",
        "publishable_as_final": report["publishable_as_final"],
        "base_preview_id": v16.CURRENT_V16_PREVIEW_ID,
        "base_preview_manifest_sha256": LEGACY_PREVIEW_V16_MANIFEST_SHA256,
        "base_preview_commit": LEGACY_PREVIEW_V16_COMMIT,
        "source_release_id": v16.SOURCE_RELEASE_ID,
        "source_release_manifest_path": "releases/2026-07-22-open-seed-v97/manifest.json",
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "definition_paths": {
            "one_hundred_site_batch": V17_BATCH_CONTRACT.relative_to(ROOT).as_posix()
        },
        "one_hundred_site_batch_sha256": V17_BATCH_CONTRACT_SHA256,
        "geometry_capture": {
            "path": V17_GEOMETRY_CAPTURE.relative_to(ROOT).as_posix(),
            "bytes": V17_GEOMETRY_CAPTURE.stat().st_size,
            "sha256": V17_GEOMETRY_CAPTURE_SHA256,
            "evidence_ids": sorted(
                _capture_evidence(row)["evidence_id"]
                for row in v16._load_json(V17_GEOMETRY_CAPTURE)["source_documents"]
            ),
        },
        "portable_source_inputs": list(portable),
        "reviewed_at": CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat(),
        "cohort_lifecycle_reference_date": (
            CURRENT_V17_LIFECYCLE_REFERENCE_DATE.isoformat()
        ),
        "geometry_identity_reviewed_at": (
            CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE.isoformat()
        ),
        "counts": {
            "physical_sites": report["selected_physical_site_count"],
            "projects": report["selected_project_count"],
            "evidence": report["selected_evidence_count"],
            "countries": len(report["country_counts"]),
            "non_us_sites": sum(
                count
                for country, count in report["country_counts"].items()
                if country != "United States"
            ),
            "official_boundary_projects": report["official_boundary_project_count"],
            "reviewed_site_locator_projects": report[
                "reviewed_site_locator_project_count"
            ],
        },
        "files": {
            name: {"bytes": len(payload), "sha256": v16._sha256_bytes(payload)}
            for name, payload in sorted(payloads.items())
        },
    }


def build_preview(output_dir: Path = CURRENT_V17_PREVIEW_DIR) -> dict[str, Any]:
    """Build v0.17 from byte-frozen v0.16 and tracked, hash-bound inputs."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise VerifiedConstructionCoreError(f"refusing to overwrite {output_dir}")
    payloads, report, portable = _payloads()
    manifest = _manifest(payloads, report, portable)
    manifest_bytes = v16._json_bytes(manifest)
    complete = {
        **payloads,
        "manifest.json": manifest_bytes,
        "manifest.sha256": (
            f"{v16._sha256_bytes(manifest_bytes)}  manifest.json\n".encode()
        ),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, payload in complete.items():
            with (stage / name).open("xb") as handle:
                handle.write(payload)
        os.replace(stage, output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_preview(output_dir)
    return manifest


def _validate_v17_preview(path: Path) -> dict[str, Any]:
    path = Path(path)
    manifest_path = path / "manifest.json"
    checksum_path = path / "manifest.sha256"
    if (
        path.is_symlink()
        or not path.is_dir()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
        or checksum_path.is_symlink()
        or not checksum_path.is_file()
    ):
        raise VerifiedConstructionCoreError("v0.17 manifest trust root differs")
    manifest_bytes = manifest_path.read_bytes()
    if checksum_path.read_bytes() != (
        f"{v16._sha256_bytes(manifest_bytes)}  manifest.json\n".encode()
    ):
        raise VerifiedConstructionCoreError("v0.17 manifest checksum differs")
    manifest = v16._load_json(manifest_path)
    if (
        not isinstance(manifest, dict)
        or manifest.get("format")
        != "datacenter-atlas-verified-construction-core-preview-v17"
        or manifest.get("preview_id") != CURRENT_V17_PREVIEW_ID
        or manifest.get("release_status") != "preview"
        or manifest.get("publishable_as_final") is not False
        or manifest.get("base_preview_id") != v16.CURRENT_V16_PREVIEW_ID
        or manifest.get("base_preview_manifest_sha256")
        != LEGACY_PREVIEW_V16_MANIFEST_SHA256
        or manifest.get("base_preview_commit") != LEGACY_PREVIEW_V16_COMMIT
        or manifest.get("counts", {}).get("physical_sites") != 100
        or manifest.get("counts", {}).get("projects") != 103
        or manifest.get("counts", {}).get("countries") != 40
    ):
        raise VerifiedConstructionCoreError("v0.17 manifest semantics differ")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("v0.17 manifest files differ")
    expected_inventory = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_inventory:
        raise VerifiedConstructionCoreError("v0.17 preview inventory differs")
    for name, metadata in files.items():
        member = path / name
        if (
            Path(name).name != name
            or member.is_symlink()
            or not member.is_file()
            or member.stat().st_size != metadata.get("bytes")
            or v16._sha256_file(member) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(f"v0.17 member differs: {name}")
    payloads, report, portable = _payloads()
    if manifest != _manifest(payloads, report, portable):
        raise VerifiedConstructionCoreError("v0.17 manifest semantics differ")
    for name, expected in payloads.items():
        if (path / name).read_bytes() != expected:
            raise VerifiedConstructionCoreError(
                f"v0.17 generated member differs: {name}"
            )
    for filename, key, fields in (
        ("projects.csv", "project_id", PROJECT_FIELDS),
        ("sites.csv", "site_id", SITE_FIELDS),
        ("evidence.csv", "evidence_id", EVIDENCE_FIELDS),
    ):
        inherited = {
            row[key]: row
            for row in v16._load_csv(LEGACY_PREVIEW_V16_DIR / filename, fields)
        }
        current = {row[key]: row for row in v16._load_csv(path / filename, fields)}
        if any(current.get(row_id) != row for row_id, row in inherited.items()):
            raise VerifiedConstructionCoreError(
                f"v0.17 inherited {filename} row changed"
            )
    return manifest


def validate_preview(path: Path = CURRENT_V17_PREVIEW_DIR) -> dict[str, Any]:
    """Validate current v0.17 or dispatch v0.1-v0.16 to the frozen validator."""
    path = Path(path)
    manifest_path = path / "manifest.json"
    if (
        path.is_symlink()
        or not path.is_dir()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        raise VerifiedConstructionCoreError("preview manifest trust root differs")
    manifest = v16._load_json(manifest_path)
    if (
        isinstance(manifest, dict)
        and manifest.get("preview_id") == CURRENT_V17_PREVIEW_ID
    ):
        return _validate_v17_preview(path)
    return v16.validate_preview(path)


__all__ = [
    "CURRENT_V17_GEOMETRY_IDENTITY_REVIEW_DATE",
    "CURRENT_V17_LIFECYCLE_REFERENCE_DATE",
    "CURRENT_V17_PREVIEW_DIR",
    "CURRENT_V17_PREVIEW_ID",
    "CURRENT_V17_REVIEW_DATE",
    "LEGACY_PREVIEW_V16_COMMIT",
    "LEGACY_PREVIEW_V16_DIR",
    "LEGACY_PREVIEW_V16_MANIFEST_SHA256",
    "V17_BATCH_CONTRACT",
    "V17_BATCH_CONTRACT_SHA256",
    "V17_GEOMETRY_CAPTURE",
    "V17_GEOMETRY_CAPTURE_SHA256",
    "VerifiedConstructionCoreError",
    "build_preview",
    "validate_frozen_v16",
    "validate_preview",
]
