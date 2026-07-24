#!/usr/bin/env python3
"""Publish the conservative official-coordinate assessment v4.

The raw response bodies stay outside the repository.  This builder verifies their
closed byte inventory, emits only factual hash carriers and compact extractions,
and publishes the artifact through a future-dated private stage with atomic
no-replace promotion.
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
import sys
import tempfile
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
PUBLICATION_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "site-coordinate-assessment-2026-07-21-v4"
ARTIFACT_DIR = PUBLICATION_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = PUBLICATION_ROOT / f".{ARTIFACT_ID}.lock"
AS_OF_DATE = "2026-07-21"

CAPTURE_INPUT_PATH = Path("/private/tmp/dc-coordinate-official-20260721.xrw579")
CAPTURE_TRASH_PATH = Path(
    "/Users/kian/.Trash/datacenter-atlas-coordinate-official-20260721-v4-xrw579"
)
CAPTURE_FILE_COUNT = 54
CAPTURE_TOTAL_BYTES = 1_692_764
CAPTURE_TREE_SHA256 = (
    "1c84a37eaa06a0f04a72d6c1b4f7e62c7ce00645fcb79a1df2463598db14beef"
)

BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
BASE_DEFINITION_BYTES = 86_839
BASE_DEFINITION_SHA256 = (
    "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
)
BASE_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v71/manifest.json"
BASE_MANIFEST_SHA256 = (
    "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
)
PRIOR_COORDINATE_MANIFEST = (
    ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v3/manifest.json"
)
PRIOR_COORDINATE_MANIFEST_SHA256 = (
    "acb675580c993e3af150f8a3e25f53a8d66a6d7b595b644088a84f1294acd43d"
)


class CoordinateAssessmentV4Error(RuntimeError):
    """Raised when a v4 provenance or publication fuse fails closed."""


COHORT: dict[str, tuple[int, str, str]] = {
    "curated-official-2026-07-19-nextdc-d2-darwin-1h26-fitout.json": (
        14_267,
        "77cf37681f3bdf093bd381b5cbd325f33e3fc8e3f8ff5e48e35de324b9caad65",
        "official_capture_identity_gap",
    ),
    "curated-official-2026-07-19-nextdc-ge1-geelong-1h26-fitout.json": (
        14_268,
        "5cffac3c97fd9faaa5644d18d7c0bbac8a6016be6930685dea32dce0a89347c4",
        "osm_review_only",
    ),
    "curated-official-2026-07-19-nextdc-m3-melbourne-1h26-fitout.json": (
        14_282,
        "998ddd53d217df3a1411c55e0ff1037488b6456d5f62d50e1d7429a8842b6ceb",
        "osm_review_only",
    ),
    "curated-official-2026-07-19-nextdc-s3-sydney-1h26-fitout.json": (
        14_263,
        "3269918319752e643a38b7391beea53377eff987547864dcb624dacd6cf1b969",
        "osm_review_only",
    ),
    "curated-official-2026-07-19-nextdc-s4-sydney-1h26-early-works.json": (
        13_507,
        "4f465a73da77cc106c37aff41050079c1f07e78d25e3bdd92319b78a30418082",
        "accepted_official_coordinate",
    ),
    "curated-official-2026-07-19-nextdc-s6-sydney-1h26-fitout.json": (
        14_271,
        "4a7482e8169884bd98cd8159217459064088e78a21c11c28584da766bc19ce7b",
        "osm_review_only",
    ),
    "curated-official-2026-07-19-nextdc-sc1-sunshine-coast-1h26-fitout.json": (
        14_311,
        "418ed5e49ff689d140b10040e458758793418797d6179340b0e7441e6216f1d9",
        "osm_review_only",
    ),
    "curated-official-2026-07-19-nextdc-sc2-sunshine-coast-1h26-fitout.json": (
        14_284,
        "768526b34023aac438eca3513898102b90d29f0107e52da16e6e16c6fe7e01c2",
        "accepted_official_coordinate",
    ),
    "curated-official-2026-07-20-equinix-ch5-chicago-phase-2.json": (
        11_637,
        "adb0539295241508fdcb46f2b10bc1962b52db7062b78631f825abff8978065e",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-da12-dallas-phase-1.json": (
        11_636,
        "d062e18f3ed965209d88da719faa8d2274ebd973d6a897dd7a44b9feca8fa5cc",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-fr8-frankfurt-phase-3.json": (
        13_161,
        "bafbaf95eda8734be62fa461bbe7de16ccf5d5b42740f9a39962253fb6049101",
        "osm_midpoint_review_only",
    ),
    "curated-official-2026-07-20-equinix-jk1-jakarta-phase-2.json": (
        15_337,
        "f14cd026fab1eafca6675f107d9f7505ea0646a01baaa8c166fa91f9086d9a3f",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-ld14-london-phase-1.json": (
        13_178,
        "7efc590aaf649df2a5ea583a00a80444a545dea7459f42322937575dfad56c7e",
        "official_report_not_captured",
    ),
    "curated-official-2026-07-20-equinix-ld14-london-phase-2.json": (
        13_178,
        "1fc10cc8b1ab18e293815854f0265d6e74342537246f17e7f2b8b39d864226ff",
        "official_report_not_captured",
    ),
    "curated-official-2026-07-20-equinix-mi1-miami-redevelopment.json": (
        11_639,
        "55e40fce1b15eed4b306826f9d888a49e25b58567f285077c57c93b516d367dc",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-ny11-new-york-phase-5.json": (
        15_374,
        "7bd94a58c4fede51a67f9e4af52e31a010ea83456ff5eea4fcd8d5e5ec59fe7a",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-os3-osaka-phase-4.json": (
        15_311,
        "92de5f9fa26d00ab34118e2aeb6058426bd2db610bf89e88d9191c9c886ffffe",
        "official_capture_identity_gap",
    ),
    "curated-official-2026-07-20-equinix-sy5-sydney-phase-4.json": (
        15_332,
        "2fb64fcf40db4dd6b84e3bbbd857edc0b16beb5dd7df0b73035d691bd6571bf1",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-tr6-toronto-phase-3.json": (
        11_609,
        "3946e649d8ff0fa1c090eb390dbb0196350d3cc64a0001b9461516c67f2c5bca",
        "osm_review_only",
    ),
    "curated-official-2026-07-20-equinix-zh4-zurich-phase-6.json": (
        13_162,
        "e7c0ee0403a66e4cda73045b4f0d3aa29f2bfa0ebb7661593d3ae34fe7f94b89",
        "official_capture_identity_gap",
    ),
}


ACCEPTED: dict[str, dict[str, Any]] = {
    "sc2": {
        "predecessor": (
            "curated-official-2026-07-19-nextdc-sc2-sunshine-coast-"
            "1h26-fitout.json"
        ),
        "successor": (
            "curated-official-2026-07-19-nextdc-sc2-sunshine-coast-"
            "1h26-fitout-coordinate-v4.json"
        ),
        "campus_key": "curated:nextdc-sc2-maroochydore",
        "project_key": (
            "curated:nextdc-sc2-maroochydore:incremental-in-progress-fit-out"
        ),
        "changed_entities": ("project",),
        "latitude": -26.6600114,
        "longitude": 153.0924068,
        "horizontal_uncertainty_m": 50,
        "evidence_key": (
            "queensland-nextdc-sc2-lot-10-sp305311-centroid-captured-2026-07-21"
        ),
        "retrieved_at": "2026-07-21T12:25:50Z",
        "capture_stems": ("nextdc_sc2", "qld_sc2_da", "qld_sc2_parcel"),
    },
    "s4": {
        "predecessor": (
            "curated-official-2026-07-19-nextdc-s4-sydney-1h26-early-works.json"
        ),
        "successor": (
            "curated-official-2026-07-19-nextdc-s4-sydney-1h26-early-"
            "works-coordinate-v4.json"
        ),
        "campus_key": "curated:nextdc-s4-sydney",
        "project_key": "curated:nextdc-s4-sydney:early-works",
        "changed_entities": ("campus", "project"),
        "latitude": -33.8278399,
        "longitude": 150.825,
        "horizontal_uncertainty_m": 100,
        "evidence_key": "nsw-planning-nextdc-s4-pda-coordinate-captured-2026-07-21",
        "retrieved_at": "2026-07-21T12:25:55Z",
        "capture_stems": ("nextdc_s4", "nsw_s4_project", "nsw_s4_pda"),
    },
}


REQUEST_DECISIONS = {
    "equinix_ld14": "http_403_no_identity_or_address_content",
    "equinix_os3": "http_403_no_identity_or_address_content",
    "equinix_zh4": "http_403_no_identity_or_address_content",
    "japan_gsi_os3": "geocoder_result_has_address_but_no_os3_identity_bridge",
    "nextdc_d2": "facility_identity_only_no_parcel_bridge",
    "nextdc_s4": "accepted_identity_context",
    "nextdc_sc2": "accepted_identity_context",
    "nsw_s4_pda": "accepted_direct_project_coordinate",
    "nsw_s4_project": "accepted_direct_project_identity_and_map_context",
    "nt_d2_planning": "http_403_cloudflare_challenge_not_official_pdf",
    "nt_d2_survey_plan": "parcel_geometry_without_d2_identity_bridge",
    "ntlis_d2_lot11310_featureinfo": "parcel_hit_without_d2_identity_bridge",
    "ntlis_wms_capabilities": "http_404",
    "ntlis_wms_capabilities_http": "service_metadata_only",
    "qld_sc2_da": "accepted_operator_address_and_lot_bridge",
    "qld_sc2_parcel": "accepted_official_parcel_geometry",
    "swiss_zh4": "geocoder_result_has_address_but_no_zh4_identity_bridge",
    "uk_ld14_report": "redirected_to_general_html_not_the_report_pdf",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _parse_utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoordinateAssessmentV4Error(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CoordinateAssessmentV4Error(f"{label} is invalid") from error
    if parsed.microsecond:
        raise CoordinateAssessmentV4Error(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _capture_root() -> Path:
    roots = [
        path
        for path in (CAPTURE_INPUT_PATH, CAPTURE_TRASH_PATH)
        if path.exists() or path.is_symlink()
    ]
    if len(roots) != 1:
        raise CoordinateAssessmentV4Error(
            "exactly one private or preserved capture root must exist"
        )
    root = roots[0]
    if root.is_symlink() or not root.is_dir():
        raise CoordinateAssessmentV4Error("capture root must be an ordinary directory")
    return root


def _capture_rows(root: Path) -> list[dict[str, Any]]:
    paths = sorted(path for path in root.iterdir() if path.is_file())
    if len(paths) != CAPTURE_FILE_COUNT or any(path.is_symlink() for path in paths):
        raise CoordinateAssessmentV4Error("capture file inventory differs")
    total = 0
    closure = bytearray()
    rows: list[dict[str, Any]] = []
    for path in paths:
        raw = path.read_bytes()
        metadata = path.stat(follow_symlinks=False)
        digest = _sha256(raw)
        total += len(raw)
        closure.extend(f"{digest}  ./{path.name}\n".encode())
        rows.append(
            {
                "capture_name": path.name,
                "bytes": len(raw),
                "sha256": digest,
                "birth_epoch": int(metadata.st_birthtime),
                "mtime_epoch": int(metadata.st_mtime),
            }
        )
    if total != CAPTURE_TOTAL_BYTES or _sha256(bytes(closure)) != CAPTURE_TREE_SHA256:
        raise CoordinateAssessmentV4Error("capture byte closure differs")
    return rows


def _verify_base_and_cohort() -> dict[str, dict[str, Any]]:
    base_raw = BASE_DEFINITION.read_bytes()
    if (len(base_raw), _sha256(base_raw)) != (
        BASE_DEFINITION_BYTES,
        BASE_DEFINITION_SHA256,
    ):
        raise CoordinateAssessmentV4Error("accepted v71 definition drifted")
    if _sha256(BASE_MANIFEST.read_bytes()) != BASE_MANIFEST_SHA256:
        raise CoordinateAssessmentV4Error("accepted v71 manifest drifted")
    if _sha256(PRIOR_COORDINATE_MANIFEST.read_bytes()) != (
        PRIOR_COORDINATE_MANIFEST_SHA256
    ):
        raise CoordinateAssessmentV4Error("accepted coordinate v3 manifest drifted")
    selected = {
        row["path"]: row["sha256"]
        for row in json.loads(base_raw)["curated_inputs"]
    }
    documents: dict[str, dict[str, Any]] = {}
    for name, (expected_bytes, expected_sha256, _reason) in COHORT.items():
        path = ROOT / "sources" / name
        raw = path.read_bytes()
        if (
            path.is_symlink()
            or stat.S_IMODE(path.stat().st_mode) != 0o644
            or (len(raw), _sha256(raw)) != (expected_bytes, expected_sha256)
            or selected.get(f"sources/{name}") != expected_sha256
        ):
            raise CoordinateAssessmentV4Error(f"cohort pin differs: {name}")
        document = json.loads(raw)
        if document.get("schema_version") != "1.0":
            raise CoordinateAssessmentV4Error(f"cohort schema differs: {name}")
        documents[name] = document
    return documents


def _carrier(rows: Mapping[str, Mapping[str, Any]], name: str) -> dict[str, Any]:
    try:
        return dict(rows[name])
    except KeyError as error:
        raise CoordinateAssessmentV4Error(f"capture carrier missing: {name}") from error


def _evidence(
    label: str,
    specification: Mapping[str, Any],
    capture: Path,
    carriers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    captured = {
        stem: {
            suffix: _carrier(carriers, f"{stem}.{suffix}")
            for suffix in ("body", "headers", "writeout")
        }
        for stem in specification["capture_stems"]
    }
    if label == "sc2":
        body = captured["qld_sc2_parcel"]["body"]
        source_url = json.loads((capture / "qld_sc2_parcel.writeout").read_text())[
            "url_effective"
        ]
        title = "Queensland cadastral parcel and development record for NEXTDC SC2"
        publisher = "Queensland Government"
        family = "queensland_government_development_and_cadastre"
        excerpt = (
            "The official development record identifies NEXTDC Limited at 10 South "
            "Sea Islander Way, Lot 10 on SP305311; the official cadastral response "
            "returns that exact lot polygon."
        )
        derivation = {
            "kind": "area_weighted_polygon_centroid",
            "input_feature_id": 870025,
            "input_lotplan": "10SP305311",
            "input_ring_vertices_including_closure": 13,
            "unrounded_longitude": "153.09240679583692",
            "unrounded_latitude": "-26.660011370099085",
            "stored_decimal_places": 7,
        }
        identity = (
            "NEXTDC's captured SC2 page names SC2 in Maroochydore; the captured "
            "Queensland application names applicant NEXTDC Limited, the exact "
            "Maroochydore address, and Lot 10 SP305311; the cadastral response is "
            "queried by and returns that exact lotplan."
        )
        point_scope = (
            "Derived representative point inside the official 3711-square-metre "
            "parcel polygon; it is neither a building centroid nor a footprint."
        )
    else:
        body = captured["nsw_s4_pda"]["body"]
        source_url = json.loads((capture / "nsw_s4_pda.writeout").read_text())[
            "url_effective"
        ]
        title = "NSW Planning pre-development application for NEXTDC S4"
        publisher = "NSW Government Planning Portal"
        family = "nsw_planning_major_projects"
        excerpt = (
            "The official PDA names NEXTDC S4 Data Centre Horsley Park and directly "
            "reports latitude -33.827839926255706 and longitude 150.825."
        )
        derivation = {
            "kind": "source_reported_point_rounded",
            "source_latitude_decimal_text": "-33.827839926255706",
            "source_longitude_decimal_text": "150.825",
            "stored_latitude_decimal_places": 7,
            "stored_longitude_decimal_places": 3,
        }
        identity = (
            "The captured NSW PDA directly names NEXTDC S4 Data Centre Horsley "
            "Park and reports the point; the captured NSW project page and NEXTDC "
            "S4 page independently preserve the same project identity and locality."
        )
        point_scope = (
            "Publisher-reported project representative point; it is not a surveyed "
            "boundary, building centroid, or footprint."
        )
    return {
        "key": specification["evidence_key"],
        "kind": "government_record",
        "title": title,
        "source_url": source_url,
        "publisher": publisher,
        "source_family": family,
        "published_at": None,
        "retrieved_at": specification["retrieved_at"],
        "license": "no-license-stated-for-compact-factual-extraction",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": body["sha256"],
        "metadata": {
            "content_hash_scope": (
                f"SHA-256 of the exact {body['bytes']}-byte official response body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "capture_artifact_id": ARTIFACT_ID,
            "capture_tree_sha256": CAPTURE_TREE_SHA256,
            "capture_carriers": captured,
            "retrieval_time_basis": (
                "latest whole-second local filesystem mtime among the exact "
                "identity and coordinate response carriers"
            ),
            "identity_chain": identity,
            "coordinate_derivation": derivation,
            "stored_coordinate": {
                "latitude": specification["latitude"],
                "longitude": specification["longitude"],
            },
            "coordinate_reference_system": "EPSG:4326",
            "coordinate_method": "authoritative_site_plan",
            "horizontal_uncertainty_m": specification["horizontal_uncertainty_m"],
            "uncertainty_scope": (
                "Conservative analyst envelope for a site representative point; "
                "not publisher accuracy metadata."
            ),
            "representative_point_scope": point_scope,
            "claim_guardrail": (
                "This evidence changes only selected coordinate snapshot fields. "
                "It adds no lifecycle, capacity, energy, consumption, owner, "
                "operator, tenant, workload, type, or current-status claim."
            ),
            "raw_capture_guardrail": (
                "Response bodies, headers, and curl writeouts are hash-bound, "
                "kept outside the repository, and not redistributed."
            ),
        },
    }


def _successor(
    label: str,
    specification: Mapping[str, Any],
    predecessor: Mapping[str, Any],
    capture: Path,
    carriers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    output = copy.deepcopy(predecessor)
    output["schema_version"] = "1.1"
    output["evidence"].append(_evidence(label, specification, capture, carriers))
    point = {
        "latitude": specification["latitude"],
        "longitude": specification["longitude"],
    }
    geometry = {
        "type": "Point",
        "coordinates": [specification["longitude"], specification["latitude"]],
    }
    for entity_name in specification["changed_entities"]:
        entity = output[entity_name]
        entity["coordinates"] = copy.deepcopy(point)
        entity["geometry"] = copy.deepcopy(geometry)
        entity["evidence_key"] = specification["evidence_key"]
        entity["method"] = "authoritative_site_plan"
    return output


def _validate_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    specification: Mapping[str, Any],
) -> None:
    if predecessor.get("schema_version") != "1.0" or successor.get(
        "schema_version"
    ) != "1.1":
        raise CoordinateAssessmentV4Error("coordinate schema upgrade differs")
    if set(predecessor) != set(successor):
        raise CoordinateAssessmentV4Error("coordinate successor root keys differ")
    if successor["evidence"][:-1] != predecessor["evidence"] or len(
        successor["evidence"]
    ) != len(predecessor["evidence"]) + 1:
        raise CoordinateAssessmentV4Error("coordinate evidence append differs")
    if (
        successor["evidence"][-1].get("key") != specification["evidence_key"]
        or successor["evidence"][-1].get("kind") != "government_record"
    ):
        raise CoordinateAssessmentV4Error("coordinate evidence identity differs")
    restored = copy.deepcopy(successor)
    restored["schema_version"] = predecessor["schema_version"]
    restored["evidence"] = copy.deepcopy(predecessor["evidence"])
    for entity_name in ("campus", "project"):
        before = predecessor[entity_name]
        after = successor[entity_name]
        changed = {
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        }
        if entity_name in specification["changed_entities"]:
            if changed != {"coordinates", "geometry", "evidence_key", "method"}:
                raise CoordinateAssessmentV4Error(
                    f"coordinate-only delta differs for {entity_name}"
                )
            if before.get("coordinates") is not None or before.get("geometry") is not None:
                raise CoordinateAssessmentV4Error("coordinate predecessor was located")
            for key in changed:
                restored[entity_name][key] = copy.deepcopy(before[key])
        elif changed:
            raise CoordinateAssessmentV4Error(
                f"unchanged coordinate entity drifted: {entity_name}"
            )
    if restored != predecessor:
        raise CoordinateAssessmentV4Error("successor gained a non-coordinate claim")
    for section in ("lifecycle", "operating_models", "workloads", "capacities"):
        if successor[section] != predecessor[section]:
            raise CoordinateAssessmentV4Error(f"successor changed {section}")


def _inventory(
    capture: Path, capture_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    by_name = {row["capture_name"]: row for row in capture_rows}
    requests = []
    for stem, decision in sorted(REQUEST_DECISIONS.items()):
        writeout = json.loads((capture / f"{stem}.writeout").read_text())
        requests.append(
            {
                "request_id": stem,
                "effective_url": writeout["url_effective"],
                "http_status": writeout["http_code"],
                "curl_exit_code": writeout.get("exitcode"),
                "decision": decision,
                "retrieved_at": datetime.fromtimestamp(
                    max(
                        by_name[f"{stem}.{suffix}"]["mtime_epoch"]
                        for suffix in ("body", "headers", "writeout")
                    ),
                    UTC,
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "carriers": {
                    suffix: by_name[f"{stem}.{suffix}"]
                    for suffix in ("body", "headers", "writeout")
                },
            }
        )
    return {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "capture": {
            "original_private_path": str(CAPTURE_INPUT_PATH),
            "preserved_recovery_path": str(CAPTURE_TRASH_PATH),
            "files": CAPTURE_FILE_COUNT,
            "bytes": CAPTURE_TOTAL_BYTES,
            "tree_sha256": CAPTURE_TREE_SHA256,
            "tree_hash_algorithm": (
                "SHA-256 of sorted '<file-sha256>  ./<basename>\\n' rows"
            ),
            "raw_bytes_redistributed": False,
        },
        "requests": requests,
    }


def _payloads(recorded_at: str) -> dict[str, bytes]:
    recorded = _parse_utc(recorded_at, "v4 recorded_at")
    capture = _capture_root()
    capture_rows = _capture_rows(capture)
    carriers = {row["capture_name"]: row for row in capture_rows}
    documents = _verify_base_and_cohort()

    successors: dict[str, bytes] = {}
    successor_rows: dict[str, dict[str, Any]] = {}
    for label, specification in ACCEPTED.items():
        predecessor = documents[specification["predecessor"]]
        successor = _successor(
            label, specification, predecessor, capture, carriers
        )
        _validate_successor(predecessor, successor, specification)
        relative = f"normalized-successors/{specification['successor']}"
        raw = _canonical_json(successor)
        successors[relative] = raw
        successor_rows[label] = {
            "path": relative,
            "bytes": len(raw),
            "sha256": _sha256(raw),
            "predecessor": f"sources/{specification['predecessor']}",
            "predecessor_sha256": COHORT[specification["predecessor"]][1],
            "campus_key": specification["campus_key"],
            "project_key": specification["project_key"],
            "changed_entities": list(specification["changed_entities"]),
            "added_evidence_key": specification["evidence_key"],
        }

    observations = []
    for name, (byte_count, digest, reason) in COHORT.items():
        document = documents[name]
        accepted_label = next(
            (
                label
                for label, specification in ACCEPTED.items()
                if specification["predecessor"] == name
            ),
            None,
        )
        row: dict[str, Any] = {
            "predecessor": f"sources/{name}",
            "predecessor_bytes": byte_count,
            "predecessor_sha256": digest,
            "campus_key": document["campus"]["stable_key"],
            "project_key": document["project"]["stable_key"],
            "disposition": reason,
            "successor": None,
        }
        if accepted_label is not None:
            specification = ACCEPTED[accepted_label]
            row.update(
                {
                    "successor": successor_rows[accepted_label]["path"],
                    "changed_entities": list(specification["changed_entities"]),
                    "coordinate": {
                        "latitude": specification["latitude"],
                        "longitude": specification["longitude"],
                        "horizontal_uncertainty_m": specification[
                            "horizontal_uncertainty_m"
                        ],
                    },
                }
            )
        observations.append(row)

    coordinate_observations = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "integration": "none",
        "assessment_scope": {
            "project_rows": 20,
            "campus_identities": 19,
            "accepted_successors": 2,
            "accepted_project_locations": 2,
            "accepted_campus_location_mutations": 1,
            "review_only_project_rows": 18,
        },
        "rows": observations,
    }
    review_rows = [row for row in observations if row["successor"] is None]
    disposition = {
        "schema_version": "1.0",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": recorded_at,
        "integration": "none",
        "accepted_seed_definition": None,
        "non_coordinate_claims_added": [],
        "accepted": {
            "successors": successor_rows,
            "policy": (
                "Only captured official or government bytes with a direct facility "
                "identity chain may create a normalized successor."
            ),
        },
        "review_only": {
            "project_rows": len(review_rows),
            "rows": review_rows,
            "osm_policy": (
                "OSM-derived candidates remain review leads. OPENSTREETMAP is not "
                "an allowed evidence kind in the curated-official importer, and no "
                "OSM candidate is routed through that importer."
            ),
            "ld14_policy": (
                "The attempted official report capture redirected to a general HTML "
                "consultation page, so both LD14 phase rows remain review-only."
            ),
            "identity_gap_policy": (
                "A government parcel or geocoder point without captured bytes that "
                "directly bridge the exact facility identity remains review-only."
            ),
        },
        "lineage": {
            "base_definition": {
                "path": "sources/open-seed-2026-07-21-v71.json",
                "bytes": BASE_DEFINITION_BYTES,
                "sha256": BASE_DEFINITION_SHA256,
            },
            "base_manifest_sha256": BASE_MANIFEST_SHA256,
            "prior_coordinate_artifact": {
                "path": "source_artifacts/site-coordinate-assessment-2026-07-21-v3",
                "manifest_sha256": PRIOR_COORDINATE_MANIFEST_SHA256,
                "preserved_unchanged": True,
            },
        },
        "publication_contract": {
            "recorded_at": recorded_at,
            "all_private_stage_birth_and_mtime_not_later_than_recorded_at": True,
            "final_paths_absent_until_recorded_at_live": True,
            "frozen_before_promotion": True,
            "atomic_no_replace_promotion": True,
            "final_root_ctime_not_earlier_than_recorded_at": True,
            "identity_safe_cleanup": True,
        },
    }
    inventory = _inventory(capture, capture_rows)
    inventory["publication_recorded_at"] = recorded_at

    readme = f"""# Site coordinate assessment 2026-07-21 v4

This artifact assesses 20 explicitly parented project rows across 19 campus
identities. It accepts two coordinate-only successors: NEXTDC SC2, whose project
receives the area-weighted centroid of the exact Queensland Lot 10 SP305311
parcel, and NEXTDC S4, whose campus and project receive the point directly
reported in the NSW Planning PDA.

The other 18 project rows remain review-only. Thirteen candidates came from OSM
review and are not routed through the curated-official importer. D2 lacks a
captured facility-to-parcel identity bridge. OS3 and ZH4 have government geocoder
responses but no captured exact-facility-to-address bridge. The attempted LD14
report capture returned a general consultation HTML page rather than the report,
so both phases remain unresolved. No midpoint, locality centroid, query seed,
failed-response URL, or analyst-supplied address becomes a normalized coordinate.

Integration is `none`. The successors add no lifecycle, capacity, energy,
consumption, ownership, operator, tenant, workload, type, or current-status
claim. Raw response bodies remain outside the repository and are pinned by the
closed {CAPTURE_FILE_COUNT}-file, {CAPTURE_TOTAL_BYTES}-byte capture tree
`{CAPTURE_TREE_SHA256}`.

Publication uses a future-dated private stage. Every staged inode is frozen and
must be born and modified no later than `recorded_at`; final paths remain absent
until that instant is live, then atomic no-replace promotion establishes a final
root ctime at or after publication.
""".encode()

    payloads = {
        "README.md": readme,
        "coordinate-observations.json": _canonical_json(coordinate_observations),
        "disposition.json": _canonical_json(disposition),
        "retrieval-inventory.json": _canonical_json(inventory),
        **successors,
    }
    files = [
        {"path": path, "bytes": len(raw), "sha256": _sha256(raw)}
        for path, raw in sorted(payloads.items())
    ]
    manifest = {
        "schema_version": "1.2",
        "artifact_id": ARTIFACT_ID,
        "as_of_date": AS_OF_DATE,
        "recorded_at": recorded_at,
        "integration": "none",
        "publication_contract_version": 4,
        "publication": disposition["publication_contract"],
        "files": files,
        "tree_sha256": _sha256(_canonical_json(files)),
    }
    manifest_raw = _canonical_json(manifest)
    payloads["manifest.json"] = manifest_raw
    payloads["manifest.sha256"] = (
        f"{_sha256(manifest_raw)}  manifest.json\n".encode("ascii")
    )
    if recorded < max(
        _parse_utc(specification["retrieved_at"], "evidence retrieved_at")
        for specification in ACCEPTED.values()
    ):
        raise CoordinateAssessmentV4Error("recorded_at precedes accepted evidence")
    return payloads


def _expected_paths(payloads: Mapping[str, bytes]) -> set[str]:
    directories: set[str] = {"."}
    for relative in payloads:
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _inspect_exact(root: Path, payloads: Mapping[str, bytes], *, frozen: bool) -> None:
    if root.is_symlink() or not root.is_dir():
        raise CoordinateAssessmentV4Error("artifact root must be an ordinary directory")
    files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }
    if set(files) != set(payloads):
        raise CoordinateAssessmentV4Error("artifact file set differs")
    for relative, raw in payloads.items():
        path = files[relative]
        if path.is_symlink() or path.read_bytes() != raw:
            raise CoordinateAssessmentV4Error(f"artifact payload differs: {relative}")
        if frozen and stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise CoordinateAssessmentV4Error(f"artifact file is not frozen: {relative}")
    directories = {
        ".": root,
        **{
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_dir()
        },
    }
    if set(directories) != _expected_paths(payloads):
        raise CoordinateAssessmentV4Error("artifact directory set differs")
    if frozen and any(
        path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o555
        for path in directories.values()
    ):
        raise CoordinateAssessmentV4Error("artifact directory is not frozen")


def _path_identities(root: Path) -> dict[str, tuple[int, int]]:
    paths = [root, *sorted(root.rglob("*"), key=lambda path: path.as_posix())]
    return {
        "." if path == root else path.relative_to(root).as_posix(): (
            path.stat(follow_symlinks=False).st_dev,
            path.stat(follow_symlinks=False).st_ino,
        )
        for path in paths
    }


def _assert_identities(root: Path, expected: Mapping[str, tuple[int, int]]) -> None:
    if _path_identities(root) != dict(expected):
        raise CoordinateAssessmentV4Error("private stage identity changed")


def _discard_stage(root: Path, identities: Mapping[str, tuple[int, int]]) -> None:
    if not root.exists() and not root.is_symlink():
        return
    _assert_identities(root, identities)
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir():
            path.chmod(0o700)
        else:
            path.chmod(0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_stage(root: Path, payloads: Mapping[str, bytes]) -> None:
    for relative, raw in payloads.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)
        _fsync(path)
    for path in (item for item in root.rglob("*") if item.is_file()):
        path.chmod(0o444)
        _fsync(path)
    root.chmod(0o555)
    _fsync(root)


def _assert_stage_precedes(root: Path, target: datetime) -> None:
    for path in (root, *root.rglob("*")):
        metadata = path.stat(follow_symlinks=False)
        if max(metadata.st_birthtime, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise CoordinateAssessmentV4Error(
                f"private stage post-dates recorded_at: {path.name}"
            )


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(stage: Path, destination: Path) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from datacenter_atlas.open_seed_v69 import promote_noreplace

    promote_noreplace(stage, destination)


def _verify_live_artifact(root: Path, payloads: Mapping[str, bytes]) -> None:
    _inspect_exact(root, payloads, frozen=True)
    manifest = json.loads(payloads["manifest.json"])
    target = _parse_utc(manifest["recorded_at"], "v4 recorded_at")
    if datetime.now(UTC) < target:
        raise CoordinateAssessmentV4Error("v4 recorded_at is not live")
    if root.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
        raise CoordinateAssessmentV4Error("final root ctime predates recorded_at")


def publish(recorded_at: str | None = None) -> dict[str, Any]:
    """Publish v4 once, or prove an existing artifact is byte-identical."""

    if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
        manifest = json.loads((ARTIFACT_DIR / "manifest.json").read_text())
        existing_recorded_at = manifest["recorded_at"]
        if recorded_at is not None and recorded_at != existing_recorded_at:
            raise CoordinateAssessmentV4Error("existing recorded_at differs")
        payloads = _payloads(existing_recorded_at)
        _verify_live_artifact(ARTIFACT_DIR, payloads)
        return {
            "artifact": str(ARTIFACT_DIR),
            "manifest_sha256": _sha256(payloads["manifest.json"]),
            "recorded_at": existing_recorded_at,
            "status": "existing-identical",
        }

    target = (
        _parse_utc(recorded_at, "v4 recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=20)
    )
    if datetime.now(UTC) >= target:
        raise CoordinateAssessmentV4Error(
            "recorded_at must be future before private staging starts"
        )
    recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    payloads = _payloads(recorded_at)
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
        raise CoordinateAssessmentV4Error("active v4 publication lock exists") from error

    stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=PUBLICATION_ROOT)
    )
    stage_identities: dict[str, tuple[int, int]] | None = None
    published = False
    try:
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise CoordinateAssessmentV4Error("initial final path collision")
        _write_stage(stage, payloads)
        _inspect_exact(stage, payloads, frozen=True)
        _assert_stage_precedes(stage, target)
        stage_identities = _path_identities(stage)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise CoordinateAssessmentV4Error("pre-wait final path collision")
        _wait_until(target)
        if ARTIFACT_DIR.exists() or ARTIFACT_DIR.is_symlink():
            raise CoordinateAssessmentV4Error("late final path collision")
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
                    raise CoordinateAssessmentV4Error(
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
