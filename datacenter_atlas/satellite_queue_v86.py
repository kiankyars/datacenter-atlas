"""Strict offline publisher for the frozen open-seed v86 satellite queue.

The queue is derived only from identities, source coordinates, source geometry,
and last-observed lifecycle values already present in the accepted v86 atlas.
It performs no catalog request, imagery analysis, entity merge, coordinate
write-back, lifecycle inference, capacity inference, or operating-status claim.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping

from . import satellite_queue as carrier
from .open_seed_v56 import promote_noreplace


class SatelliteQueueV86Error(ValueError):
    """Raised when a v86 input, queue, or publication boundary differs."""


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
ATLAS = RELEASE / "atlas.geojson"
RELEASE_MANIFEST = RELEASE / carrier.MANIFEST_FILENAME
PREDECESSOR_QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v83"
QUEUE = ROOT / "satellite_review_queues/2026-07-21-open-seed-v86"
PUBLICATION_LOCK = ROOT / ".satellite-review-queue-v86.lock"

BASELINE_TARGET = "2024-07-15"
CURRENT_TARGET = "2026-07-15"
CONFIG = carrier.QueueConfig(
    baseline_target=BASELINE_TARGET,
    current_target=CURRENT_TARGET,
    provider="earth-search-v1",
    query_window_days=45,
    max_cloud_cover=20,
    catalog_limit=100,
    aoi_half_side_km=2,
    minimum_component_area_m2=5_000,
)

V86_RECORDED_AT = "2026-07-21T20:19:16Z"
CARRIER_PIN = (
    68_511,
    "1d6f747e012ff2c34be747fe003f8fc28d715a03b60ff00fd848a9a4942e2bb2",
)
DEFINITION_PIN = (
    102_240,
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
)
ATLAS_PIN = (
    3_231_931,
    "9d6ce16e913fa888bddd3b25584871e51ebd67f3ea7f09c99874bf7a01057b19",
)
RELEASE_MANIFEST_PIN = (
    15_531,
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
)
RELEASE_TREE_SHA256 = (
    "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
)
PREDECESSOR_FILE_PINS = {
    carrier.QUEUE_FILENAME: (
        553_692,
        "8792ee2d80ed9b44d3ef67d3511b29ca0f9160b8ebd641e7f54cf4f5db4e4251",
    ),
    carrier.MANIFEST_FILENAME: (
        19_851,
        "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd",
    ),
    carrier.MANIFEST_HASH_FILENAME: (
        80,
        "9554a659b8b51925377bc31e99fa29a6fda92a5aa4675c48164d3de28e583288",
    ),
}
PREDECESSOR_TREE_SHA256 = (
    "2b9fc5a30525e2e815154d1635c49badf06c436e354ccb04a4898e6f42d22eee"
)
QUEUE_PIN = (
    596_020,
    "fff4064d67f252f6973492d054debdf82fb91391dec7c57393ef62bf5051f055",
)

PUBLISHED_GENERATED_AT = "2026-07-21T20:32:37Z"
PUBLISHED_MANIFEST_PIN = (
    20_579,
    "1a417f11e94dadbca2f5c1ddf0746d6ce5eca6ccb734957f8a3c825edab217c0",
)
PUBLISHED_MANIFEST_HASH_PIN = (
    80,
    "1936b82892a9d60ebdc0e2265e96dddb477520e05ecede27c7b351de8845e7e4",
)
PUBLISHED_TREE_SHA256 = (
    "e9611d94eff7a6cc62b22a1a3291651acaa01db468889c500455b9fb2908f1c5"
)

EXPECTED_COUNTS = {
    "features_examined": 927,
    "eligible_features_by_kind": {"campus": 485, "project": 442},
    "excluded_features_by_kind": {},
    "skipped_missing_coordinates": 712,
    "entities_queued": 215,
    "queue_jobs": 215,
    "entities_split_at_antimeridian": 0,
    "queued_entities_by_priority_tier": {
        "active_construction": 111,
        "operational": 31,
        "proposed_pipeline": 5,
        "unknown": 68,
    },
    "queued_entities_by_status_freshness": {
        "age_days_0_30": 92,
        "age_days_181_365": 12,
        "age_days_31_90": 19,
        "age_days_366_plus": 4,
        "age_days_91_180": 20,
        "missing": 68,
    },
}
COORDINATE_METHOD_COUNTS = {
    "properties.latitude_longitude": 213,
    "geometry_bounds_center": 2,
}
GEOMETRY_ONLY_ENTITY_IDS = frozenset(
    {
        "881bcfb4-d6ba-550e-b68c-45816c0877d5",
        "ad179a16-e0b4-57f3-abc7-01968cbcd63b",
    }
)
V86_APPEND_STABLE_KEYS = frozenset(
    {
        "curated:stack-johor-iskandar-puteri-campus",
        "curated:stack-johor-iskandar-puteri-campus:first-building-current-build",
        "curated:echelon-dub20-arklow-campus",
        "curated:echelon-dub20-arklow-campus:current-build",
        "curated:echelon-dub40-dublin-campus",
        "curated:echelon-dub40-dublin-campus:current-build",
        "curated:odata-dc-sp04-osasco-campus",
        "curated:odata-dc-sp04-osasco-campus:phase-2-expansion",
        "curated:multidc-shoham-campus",
        "curated:multidc-shoham-campus:current-build",
    }
)
ACTIVE_ENTITY_COUNT = 111
ACTIVE_DISTINCT_AOI_COUNT = 106
ALL_DISTINCT_AOI_COUNT = 148
PREDECESSOR_RETAINED_COUNT = 200
ADDED_COUNT = 15
REMOVED_COUNT = 0
INHERITED_POSITION_CHANGE_COUNT = 182
INHERITED_UNCHANGED_POSITION_COUNT = 18
INHERITED_SEMANTIC_CHANGE_COUNT = 0
ADDED_PRIORITY_COUNTS = {
    "active_construction": 7,
    "operational": 2,
    "unknown": 6,
}
ADDED_STATUS_COUNTS = {
    "operational": 2,
    "shell": 1,
    "under_construction": 6,
    "unknown": 6,
}

ADDED_QUEUE_EXPECTATIONS: dict[str, dict[str, Any]] = {
    "satq-05283c12277a7a85b5501e1b": {
        "entity_id": "7d880424-b9f4-5a4a-a17e-94283fbccca0",
        "kind": "campus",
        "name": "Tet DC7 Salaspils Data Center",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 146,
        "center_wgs84": {
            "latitude": 56.8656322,
            "longitude": 24.3802635,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-155eff30b284380045dde458": {
        "entity_id": "ad179a16-e0b4-57f3-abc7-01968cbcd63b",
        "kind": "project",
        "name": "Microsoft ATH04 Spata Active Construction",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 25,
        "center_wgs84": {
            "latitude": 37.9763185,
            "longitude": 23.9308603,
            "method": "geometry_bounds_center",
        },
    },
    "satq-1dd005d0c7779b70463e9c3c": {
        "entity_id": "98e47ac5-8576-53f7-ab71-9f3d683b5ec5",
        "kind": "project",
        "name": "AST Jāņciems Fit-out After Building Completion",
        "priority_tier": "active_construction",
        "lifecycle_status": "shell",
        "queue_position": 53,
        "center_wgs84": {
            "latitude": 56.9331,
            "longitude": 24.1814717,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-272885c7860fa4f516ee0a75": {
        "entity_id": "5c366d64-4bb5-5c28-ab62-ec20d60fb31a",
        "kind": "project",
        "name": "CDC Eastern Creek EC6 Current Build",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 110,
        "center_wgs84": {
            "latitude": -33.818072,
            "longitude": 150.837668,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-768c24271c8eb70e5008b672": {
        "entity_id": "2e2b9d40-5024-5e6d-bbb2-56a8b16b9c16",
        "kind": "project",
        "name": "CDC Eastern Creek EC5 Current Build",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 105,
        "center_wgs84": {
            "latitude": -33.818072,
            "longitude": 150.837668,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-b4c92673d7fbe81e7f476b06": {
        "entity_id": "8fec7123-4252-56bb-8fb7-cf2281c1bfcb",
        "kind": "campus",
        "name": "Ten Brinke Spata Data Center",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 156,
        "center_wgs84": {
            "latitude": 37.9662624,
            "longitude": 23.9087018,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-b6c662e0c6a21d88f2672e9f": {
        "entity_id": "b2fd115b-f816-5c97-8e37-76582e6ca395",
        "kind": "project",
        "name": "Equinix MO2 Phase 1",
        "priority_tier": "operational",
        "lifecycle_status": "operational",
        "queue_position": 186,
        "center_wgs84": {
            "latitude": 25.7252164,
            "longitude": -100.132713,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-b89aa445c245c3c7cd7309a5": {
        "entity_id": "165bcbb1-28c8-5947-8d42-6bd2208c39dc",
        "kind": "campus",
        "name": "AST Jāņciems Dispatcher Control and Data Centre",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 119,
        "center_wgs84": {
            "latitude": 56.9331,
            "longitude": 24.1814717,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-bcf98d4dc7d4a3efcb496d35": {
        "entity_id": "881bcfb4-d6ba-550e-b68c-45816c0877d5",
        "kind": "campus",
        "name": "Microsoft ATH04 Spata Data Center",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 149,
        "center_wgs84": {
            "latitude": 37.9763185,
            "longitude": 23.9304671,
            "method": "geometry_bounds_center",
        },
    },
    "satq-cbcb527c23a4e0e2141f6e78": {
        "entity_id": "38033ec9-dbd8-56bb-8a35-0fa91dd284e2",
        "kind": "project",
        "name": "Ten Brinke Spata Data Center Active Construction",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 107,
        "center_wgs84": {
            "latitude": 37.9662624,
            "longitude": 23.9087018,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-cc2d9df061e1c2b097440def": {
        "entity_id": "d6ef74b4-4e4f-5f3f-abb2-64c2117f52e0",
        "kind": "project",
        "name": "ODATA DC QR04 Phase 1",
        "priority_tier": "operational",
        "lifecycle_status": "operational",
        "queue_position": 185,
        "center_wgs84": {
            "latitude": 20.907398,
            "longitude": -100.62028,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-da8534ce9229a06410ec76f9": {
        "entity_id": "47804028-7f90-5f2c-8b96-3a9aedddec33",
        "kind": "project",
        "name": "Tet DC7 Salaspils Phase 1 Current Build",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 19,
        "center_wgs84": {
            "latitude": 56.8656322,
            "longitude": 24.3802635,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-de1af4ba8cfeaff9cfcf23fd": {
        "entity_id": "9b00bad3-c348-5292-9e82-d40e87c2ad51",
        "kind": "campus",
        "name": "CDC Eastern Creek Campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 160,
        "center_wgs84": {
            "latitude": -33.818072,
            "longitude": 150.837668,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-e57425c97ba4de087b3f93db": {
        "entity_id": "5a76f496-c13a-5981-be19-05ef3ed30774",
        "kind": "campus",
        "name": "AirTrunk SYD3 Western Sydney Campus",
        "priority_tier": "unknown",
        "lifecycle_status": "unknown",
        "queue_position": 136,
        "center_wgs84": {
            "latitude": -33.798627,
            "longitude": 150.876,
            "method": "properties.latitude_longitude",
        },
    },
    "satq-e641773b3426205b9657438c": {
        "entity_id": "e2c7c737-5319-551f-9865-0e7eb560e86a",
        "kind": "project",
        "name": "AirTrunk SYD3 Current Build",
        "priority_tier": "active_construction",
        "lifecycle_status": "under_construction",
        "queue_position": 23,
        "center_wgs84": {
            "latitude": -33.798627,
            "longitude": 150.876,
            "method": "properties.latitude_longitude",
        },
    },
}
MAX_PUBLICATION_LEAD_SECONDS = 300


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _checkpoint(path: Path, label: str, *, mode: int | None = None) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise SatelliteQueueV86Error(f"{label} must be a regular file")
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        raise SatelliteQueueV86Error(f"{label} mode differs")
    raw = path.read_bytes()
    return len(raw), _sha256(raw)


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SatelliteQueueV86Error(f"tree root must be a regular directory: {root}")
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        metadata = path.stat(follow_symlinks=False)
        mode = stat.S_IMODE(metadata.st_mode)
        if path.is_symlink():
            raise SatelliteQueueV86Error(f"tree contains symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif stat.S_ISREG(metadata.st_mode):
            raw = path.read_bytes()
            digest.update(
                f"F\0{relative}\0{mode:04o}\0{len(raw)}\0{_sha256(raw)}\n".encode()
            )
        else:
            raise SatelliteQueueV86Error(
                f"tree contains unsupported entry: {relative}"
            )
    return digest.hexdigest()


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        canonical = carrier._timestamp(value, label)
        parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    except (TypeError, ValueError, carrier.QueueValidationError) as error:
        raise SatelliteQueueV86Error(str(error)) from error
    return parsed.astimezone(UTC)


def _wall_clock(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise SatelliteQueueV86Error("validation wall clock must include a timezone")
    return result.astimezone(UTC)


def _require_accepted_inputs() -> dict[str, Any]:
    carrier_path = Path(carrier.__file__ or "")
    predecessor_files = {
        path.name: path for path in PREDECESSOR_QUEUE.iterdir()
    } if PREDECESSOR_QUEUE.is_dir() else {}
    release_files = list(RELEASE.iterdir()) if RELEASE.is_dir() else []
    actual = {
        "carrier": _checkpoint(carrier_path, "satellite queue carrier"),
        "definition": _checkpoint(DEFINITION, "accepted v86 definition", mode=0o444),
        "atlas": _checkpoint(ATLAS, "accepted v86 atlas", mode=0o444),
        "release_manifest": _checkpoint(
            RELEASE_MANIFEST, "accepted v86 release manifest", mode=0o444
        ),
        "release_tree_sha256": _tree_digest(RELEASE),
        "predecessor_files": {
            name: _checkpoint(path, f"accepted v83 {name}", mode=0o444)
            for name, path in predecessor_files.items()
        },
        "predecessor_tree_sha256": _tree_digest(PREDECESSOR_QUEUE),
    }
    expected = {
        "carrier": CARRIER_PIN,
        "definition": DEFINITION_PIN,
        "atlas": ATLAS_PIN,
        "release_manifest": RELEASE_MANIFEST_PIN,
        "release_tree_sha256": RELEASE_TREE_SHA256,
        "predecessor_files": PREDECESSOR_FILE_PINS,
        "predecessor_tree_sha256": PREDECESSOR_TREE_SHA256,
    }
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise SatelliteQueueV86Error(
            "accepted v86 queue input drift: " + ", ".join(differing)
        )
    if (
        RELEASE.is_symlink()
        or not RELEASE.is_dir()
        or stat.S_IMODE(RELEASE.stat().st_mode) != 0o555
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in release_files
        )
        or PREDECESSOR_QUEUE.is_symlink()
        or stat.S_IMODE(PREDECESSOR_QUEUE.stat().st_mode) != 0o555
    ):
        raise SatelliteQueueV86Error("accepted v86 or v83 tree is not frozen")
    try:
        manifest = json.loads(RELEASE_MANIFEST.read_bytes())
        definition = json.loads(DEFINITION.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV86Error("accepted v86 JSON input is invalid") from error
    if (
        manifest.get("recorded_at") != V86_RECORDED_AT
        or manifest.get("files", {}).get("atlas.geojson")
        != {"bytes": ATLAS_PIN[0], "sha256": ATLAS_PIN[1]}
        or definition.get("release_id") != "2026-07-21-open-seed-v86"
        or definition.get("build", {}).get("recorded_at") != V86_RECORDED_AT
    ):
        raise SatelliteQueueV86Error("accepted v86 release lineage changed")
    return actual


def _release_lineage(raw: bytes) -> Mapping[str, Any]:
    try:
        lineage = carrier._adjacent_release_manifest_lineage(ATLAS, raw)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV86Error(str(error)) from error
    if lineage is None:
        raise SatelliteQueueV86Error("accepted v86 release lineage is absent")
    return lineage


def _bundle(generated_at: str) -> carrier.QueueBundle:
    raw = ATLAS.read_bytes()
    try:
        return carrier.build_queue_bundle(
            raw,
            source_name=ATLAS.name,
            generated_at=generated_at,
            config=CONFIG,
            release_manifest_lineage=_release_lineage(raw),
        )
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV86Error(str(error)) from error


def _payloads(bundle: carrier.QueueBundle) -> dict[str, bytes]:
    return {
        carrier.QUEUE_FILENAME: bundle.queue_bytes,
        carrier.MANIFEST_FILENAME: bundle.manifest_bytes,
        carrier.MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
    }


def _records(raw: bytes) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in raw.splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV86Error("v86 queue JSONL is invalid") from error
    if any(not isinstance(row, dict) for row in rows):
        raise SatelliteQueueV86Error("v86 queue contains a non-object record")
    return rows


def _atlas_features() -> dict[str, tuple[Mapping[str, Any], Any]]:
    try:
        document = json.loads(ATLAS.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SatelliteQueueV86Error("accepted v86 atlas is invalid JSON") from error
    features = document.get("features")
    if not isinstance(features, list) or len(features) != 927:
        raise SatelliteQueueV86Error("accepted v86 atlas feature inventory differs")
    result: dict[str, tuple[Mapping[str, Any], Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping) or not isinstance(
            feature.get("properties"), Mapping
        ):
            raise SatelliteQueueV86Error("accepted v86 atlas feature is invalid")
        properties = feature["properties"]
        entity_id = properties.get("entity_id")
        if not isinstance(entity_id, str) or entity_id in result:
            raise SatelliteQueueV86Error("accepted v86 atlas identity inventory differs")
        result[entity_id] = properties, feature.get("geometry")
    return result


def _coordinate_pairs(value: Any) -> Iterator[tuple[float, float]]:
    if (
        isinstance(value, list)
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        yield float(value[0]), float(value[1])
    elif isinstance(value, list):
        for child in value:
            yield from _coordinate_pairs(child)


def _geometry_center(geometry: Any) -> tuple[float, float]:
    if not isinstance(geometry, Mapping):
        raise SatelliteQueueV86Error("geometry-only queue entity lacks source geometry")
    pairs = list(_coordinate_pairs(geometry.get("coordinates")))
    if not pairs:
        raise SatelliteQueueV86Error("geometry-only source geometry has no coordinates")
    longitudes = [pair[0] for pair in pairs]
    latitudes = [pair[1] for pair in pairs]
    return (
        round((min(latitudes) + max(latitudes)) / 2, 7),
        round((min(longitudes) + max(longitudes)) / 2, 7),
    )


def _validate_non_inference(
    bundle: carrier.QueueBundle, records: list[dict[str, Any]]
) -> None:
    expected_scope = {
        "purpose": "bounded imagery review planning for existing atlas entities",
        "network_requests_performed": False,
        "imagery_identity_inference": False,
        "imagery_lifecycle_inference": False,
        "imagery_power_inference": False,
        "automatic_entity_merge": False,
    }
    if bundle.manifest.get("scope") != expected_scope:
        raise SatelliteQueueV86Error("v86 queue inference scope differs")
    features = _atlas_features()
    methods: Counter[str] = Counter()
    queued_ids: set[str] = set()
    forbidden_entity_keys = {
        "capacity_estimates",
        "operating_model",
        "workload_observations",
        "workloads",
    }
    for row in records:
        if row.get("review_constraints") != carrier.REVIEW_CONSTRAINTS:
            raise SatelliteQueueV86Error("v86 queue review constraints differ")
        entity = row["entity"]
        queued_ids.add(entity["id"])
        feature = features.get(entity["id"])
        if feature is None:
            raise SatelliteQueueV86Error("v86 queue inferred an entity identity")
        properties, geometry = feature
        if forbidden_entity_keys & set(entity):
            raise SatelliteQueueV86Error("v86 queue imported a capacity or model claim")
        if (
            entity["kind"] != properties.get("entity_kind")
            or entity["name"]
            != (properties.get("name") or properties.get("stable_key") or entity["id"])
            or entity["target_entity_id"] != properties.get("target_entity_id")
            or entity["status_evidence_id"] != properties.get("status_evidence_id")
            or entity["status_as_of"] != properties.get("status_as_of")
            or row["priority"]["lifecycle_status"]
            != (properties.get("status") or "unknown")
        ):
            raise SatelliteQueueV86Error("v86 queue inferred identity or lifecycle data")
        center = row["location"]["center_wgs84"]
        method = center["method"]
        methods[method] += 1
        latitude = properties.get("latitude")
        longitude = properties.get("longitude")
        if latitude is not None and longitude is not None:
            expected = (
                "properties.latitude_longitude",
                round(float(latitude), 7),
                round(float(longitude), 7),
            )
        else:
            expected_center = _geometry_center(geometry)
            expected = ("geometry_bounds_center", *expected_center)
            if entity["id"] not in GEOMETRY_ONLY_ENTITY_IDS:
                raise SatelliteQueueV86Error(
                    "unexpected v86 geometry-only review entity"
                )
        if (
            method,
            center["latitude"],
            center["longitude"],
        ) != expected:
            raise SatelliteQueueV86Error("v86 queue review center differs from source")
    append_ids = {
        entity_id
        for entity_id, (properties, _geometry) in features.items()
        if properties.get("stable_key") in V86_APPEND_STABLE_KEYS
    }
    if (
        dict(methods) != COORDINATE_METHOD_COUNTS
        or set(methods) != set(COORDINATE_METHOD_COUNTS)
        or append_ids & queued_ids
        or len(append_ids) != 10
        or any(
            properties.get("latitude") is not None
            or properties.get("longitude") is not None
            or geometry is not None
            for entity_id, (properties, geometry) in features.items()
            if entity_id in append_ids
        )
    ):
        raise SatelliteQueueV86Error("v86 coordinate and missing-coordinate boundary differs")


def _delta_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": row["entity"]["id"],
        "kind": row["entity"]["kind"],
        "name": row["entity"]["name"],
        "priority_tier": row["priority"]["tier"],
        "lifecycle_status": row["priority"]["lifecycle_status"],
        "queue_position": row["queue_position"],
        "center_wgs84": row["location"]["center_wgs84"],
    }


def _validate_delta(records: list[dict[str, Any]]) -> None:
    predecessor = _records(
        (PREDECESSOR_QUEUE / carrier.QUEUE_FILENAME).read_bytes()
    )
    before = {row["queue_id"]: row for row in predecessor}
    after = {row["queue_id"]: row for row in records}
    added = set(after) - set(before)
    removed = set(before) - set(after)
    retained = set(before) & set(after)
    position_changes = 0
    semantic_changes = 0
    for queue_id in retained:
        old = dict(before[queue_id])
        new = dict(after[queue_id])
        position_changes += old.pop("queue_position") != new.pop("queue_position")
        semantic_changes += old != new
    if (
        len(before) != PREDECESSOR_RETAINED_COUNT
        or len(retained) != PREDECESSOR_RETAINED_COUNT
        or len(added) != ADDED_COUNT
        or len(removed) != REMOVED_COUNT
        or removed
        or added != set(ADDED_QUEUE_EXPECTATIONS)
        or {
            queue_id: _delta_projection(after[queue_id]) for queue_id in added
        }
        != ADDED_QUEUE_EXPECTATIONS
        or position_changes != INHERITED_POSITION_CHANGE_COUNT
        or len(retained) - position_changes != INHERITED_UNCHANGED_POSITION_COUNT
        or semantic_changes != INHERITED_SEMANTIC_CHANGE_COUNT
    ):
        raise SatelliteQueueV86Error("v83-to-v86 queue delta differs")


def _validate_semantics(bundle: carrier.QueueBundle) -> None:
    if (len(bundle.queue_bytes), _sha256(bundle.queue_bytes)) != QUEUE_PIN:
        raise SatelliteQueueV86Error("v86 queue JSONL differs from its accepted pin")
    counts = bundle.manifest.get("counts")
    if not isinstance(counts, Mapping) or any(
        counts.get(key) != value for key, value in EXPECTED_COUNTS.items()
    ):
        raise SatelliteQueueV86Error("v86 queue counts differ")
    records = _records(bundle.queue_bytes)
    by_id = {row["queue_id"]: row for row in records}
    active = [row for row in records if row["priority"]["tier"] == "active_construction"]
    added = [by_id[queue_id] for queue_id in ADDED_QUEUE_EXPECTATIONS]
    priority_counts = Counter(row["priority"]["tier"] for row in added)
    status_counts = Counter(row["priority"]["lifecycle_status"] for row in added)
    country_rows = counts.get("queued_entities_by_country_priority_tier")
    if (
        len(records) != 215
        or len(by_id) != 215
        or [row["queue_position"] for row in records] != list(range(1, 216))
        or len(active) != ACTIVE_ENTITY_COUNT
        or len({tuple(row["location"]["aoi_bbox_wgs84"]) for row in active})
        != ACTIVE_DISTINCT_AOI_COUNT
        or len({tuple(row["location"]["aoi_bbox_wgs84"]) for row in records})
        != ALL_DISTINCT_AOI_COUNT
        or priority_counts != ADDED_PRIORITY_COUNTS
        or status_counts != ADDED_STATUS_COUNTS
        or not isinstance(country_rows, list)
        or sum(row.get("entities", 0) for row in country_rows) != 215
    ):
        raise SatelliteQueueV86Error("v86 priority, AOI, or ordering boundary differs")
    _validate_non_inference(bundle, records)
    _validate_delta(records)


def _write_stage(stage: Path, bundle: carrier.QueueBundle) -> None:
    if stage.is_symlink() or not stage.is_dir() or any(stage.iterdir()):
        raise SatelliteQueueV86Error("v86 private stage must be an empty directory")
    for name, raw in _payloads(bundle).items():
        path = stage / name
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        path.chmod(0o444)
    stage.chmod(0o555)
    carrier._fsync_directory(stage)


def _stage_paths(stage: Path) -> tuple[Path, ...]:
    if stage.is_symlink() or not stage.is_dir():
        raise SatelliteQueueV86Error("v86 private stage changed type")
    entries = sorted(stage.iterdir(), key=lambda path: path.name)
    if {path.name for path in entries} != carrier.QUEUE_BUNDLE_FILES or any(
        path.is_symlink() or not path.is_file() for path in entries
    ):
        raise SatelliteQueueV86Error("v86 private stage file set changed")
    return (stage, *entries)


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SatelliteQueueV86Error("v86 stage must remain a directory")
    return metadata.st_dev, metadata.st_ino


def _member_identities(stage: Path) -> dict[str, tuple[int, int]]:
    identities: dict[str, tuple[int, int]] = {}
    for path in stage.iterdir():
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise SatelliteQueueV86Error("v86 stage member changed type")
        identities[path.name] = (metadata.st_dev, metadata.st_ino)
    return identities


def _assert_stage_identity(
    stage: Path,
    identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _directory_identity(stage) != identity or _member_identities(stage) != dict(
        members
    ):
        raise SatelliteQueueV86Error("v86 private stage identity changed")


def _assert_stage_precedes_target(stage: Path, target: datetime) -> None:
    for path in _stage_paths(stage):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 0.000_001:
            raise SatelliteQueueV86Error(
                f"v86 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctime(path: Path, target: datetime) -> None:
    if path.is_symlink() or not path.is_dir():
        raise SatelliteQueueV86Error("v86 final queue root is absent or invalid")
    if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target.timestamp():
        raise SatelliteQueueV86Error("v86 final queue rename predates generated_at")


def _discard_stage(
    stage: Path,
    identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]] | None = None,
) -> None:
    try:
        metadata = stage.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise SatelliteQueueV86Error("refusing substituted v86 stage cleanup")
    entries = list(stage.iterdir())
    if not {entry.name for entry in entries}.issubset(carrier.QUEUE_BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise SatelliteQueueV86Error("refusing contaminated v86 stage cleanup")
    if members is not None and _member_identities(stage) != dict(members):
        raise SatelliteQueueV86Error("refusing changed v86 stage cleanup")
    stage.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    stage.rmdir()


def _require_absent(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        raise SatelliteQueueV86Error(f"{label} v86 queue path is occupied: {path}")


@contextmanager
def _publication_lock(path: Path) -> Iterator[None]:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise SatelliteQueueV86Error(
            f"active v86 queue publication lock: {path}"
        ) from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = metadata.st_dev, metadata.st_ino
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev,
                current.st_ino,
            ) != identity:
                raise SatelliteQueueV86Error(
                    "refusing substituted v86 publication-lock cleanup"
                )
            path.unlink()


def validate_satellite_queue_v86(
    path: str | Path = QUEUE,
    *,
    require_live: bool = True,
    require_frozen: bool = True,
    require_final_root_ctime: bool | None = None,
    validation_wall_clock: datetime | None = None,
    replay_count: int = 2,
) -> Mapping[str, Any]:
    """Rebuild twice and verify an exact v86 queue without network access."""

    if replay_count != 2:
        raise SatelliteQueueV86Error("v86 queue requires exactly two offline replays")
    guard = _require_accepted_inputs()
    directory = Path(path)
    if directory.is_symlink() or not directory.is_dir():
        raise SatelliteQueueV86Error("v86 queue root must be a regular directory")
    files = {entry.name: entry for entry in directory.iterdir()}
    if set(files) != carrier.QUEUE_BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in files.values()
    ):
        raise SatelliteQueueV86Error("v86 queue bundle is not closed")
    try:
        manifest = carrier.validate_queue_bundle(directory)
    except carrier.QueueValidationError as error:
        raise SatelliteQueueV86Error(str(error)) from error
    generated = _parse_timestamp(manifest.get("generated_at"), "v86 queue generated_at")
    if generated <= _parse_timestamp(V86_RECORDED_AT, "v86 recorded_at"):
        raise SatelliteQueueV86Error("v86 queue must follow its accepted release")
    wall = _wall_clock(validation_wall_clock)
    if require_live and generated > wall:
        raise SatelliteQueueV86Error("v86 queue generated_at is not yet live")
    rebuilt = [_bundle(manifest["generated_at"]) for _ in range(replay_count)]
    if (
        _payloads(rebuilt[0]) != _payloads(rebuilt[1])
        or rebuilt[0].manifest != rebuilt[1].manifest
    ):
        raise SatelliteQueueV86Error("two offline v86 queue replays differ")
    _validate_semantics(rebuilt[0])
    for name, expected in _payloads(rebuilt[0]).items():
        if files[name].read_bytes() != expected:
            raise SatelliteQueueV86Error(f"v86 queue artifact differs: {name}")
    if require_frozen and (
        stat.S_IMODE(directory.stat().st_mode) != 0o555
        or any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in files.values())
    ):
        raise SatelliteQueueV86Error("v86 queue must be frozen 0555/0444")
    is_final = directory.resolve() == QUEUE.resolve()
    if require_final_root_ctime is None:
        require_final_root_ctime = is_final
    if is_final:
        expected_final = {
            carrier.QUEUE_FILENAME: QUEUE_PIN,
            carrier.MANIFEST_FILENAME: PUBLISHED_MANIFEST_PIN,
            carrier.MANIFEST_HASH_FILENAME: PUBLISHED_MANIFEST_HASH_PIN,
        }
        actual_final = {
            name: _checkpoint(entry, f"published v86 {name}")
            for name, entry in files.items()
        }
        if (
            not PUBLISHED_GENERATED_AT
            or manifest["generated_at"] != PUBLISHED_GENERATED_AT
            or actual_final != expected_final
            or _tree_digest(directory) != PUBLISHED_TREE_SHA256
        ):
            raise SatelliteQueueV86Error("published v86 queue pins changed")
    if require_final_root_ctime:
        _assert_final_root_ctime(directory, generated)
    if _require_accepted_inputs() != guard:
        raise SatelliteQueueV86Error("v86 queue validation mutated accepted inputs")
    return manifest


def _wait_until(
    target: float,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    while True:
        remaining = target - clock()
        if remaining <= 0:
            return
        sleeper(min(remaining, 0.25))


def _rollback_final(
    output: Path,
    stage: Path,
    identity: tuple[int, int],
    members: Mapping[str, tuple[int, int]],
) -> None:
    if _directory_identity(output) != identity or _member_identities(output) != dict(
        members
    ):
        raise SatelliteQueueV86Error("refusing rollback of substituted v86 queue")
    if stage.exists() or stage.is_symlink():
        raise SatelliteQueueV86Error("v86 rollback stage is occupied")
    try:
        promote_noreplace(output, stage)
    except SystemExit as error:
        raise SatelliteQueueV86Error(str(error)) from error


def _publish_to(
    output: Path,
    lock: Path,
    *,
    generated_at: str,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> Mapping[str, Any]:
    target = _parse_timestamp(generated_at, "v86 queue generated_at")
    now = clock()
    if now >= target.timestamp():
        raise SatelliteQueueV86Error(
            "v86 queue generated_at must be future before private staging"
        )
    if target <= _parse_timestamp(V86_RECORDED_AT, "v86 recorded_at"):
        raise SatelliteQueueV86Error("v86 queue must follow its accepted release")
    if target.timestamp() - now > MAX_PUBLICATION_LEAD_SECONDS:
        raise SatelliteQueueV86Error("v86 queue publication is over five minutes ahead")
    guard = _require_accepted_inputs()
    parent = output.parent
    if parent.is_symlink() or not parent.is_dir():
        raise SatelliteQueueV86Error("v86 queue output parent must be a directory")
    if lock.parent != parent.parent and lock.parent != ROOT:
        raise SatelliteQueueV86Error("v86 queue publication lock parent is invalid")

    with _publication_lock(lock):
        _require_absent(output, "initial")
        first = _bundle(generated_at)
        second = _bundle(generated_at)
        if _payloads(first) != _payloads(second) or first.manifest != second.manifest:
            raise SatelliteQueueV86Error("two private v86 queue builds differ")
        _validate_semantics(first)
        _require_absent(output, "after private replays")

        first_stage = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.stage-a-", dir=parent)
        )
        second_stage = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.stage-b-", dir=parent)
        )
        first_identity = _directory_identity(first_stage)
        second_identity = _directory_identity(second_stage)
        first_members: dict[str, tuple[int, int]] = {}
        second_members: dict[str, tuple[int, int]] = {}
        promoted = False
        try:
            _write_stage(first_stage, first)
            _write_stage(second_stage, second)
            first_members = _member_identities(first_stage)
            second_members = _member_identities(second_stage)
            validate_satellite_queue_v86(
                first_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            validate_satellite_queue_v86(
                second_stage,
                require_live=False,
                require_final_root_ctime=False,
            )
            first_tree = _tree_digest(first_stage)
            if first_tree != _tree_digest(second_stage):
                raise SatelliteQueueV86Error("two private v86 queue trees differ")
            _assert_stage_precedes_target(first_stage, target)
            _assert_stage_precedes_target(second_stage, target)
            _require_absent(output, "pre-wait")
            _discard_stage(second_stage, second_identity, second_members)
            _wait_until(target.timestamp(), clock=clock, sleeper=sleeper)
            if clock() < target.timestamp():
                raise SatelliteQueueV86Error("v86 queue generated_at is not yet live")
            _require_absent(output, "late")
            _assert_stage_identity(first_stage, first_identity, first_members)
            validate_satellite_queue_v86(
                first_stage,
                validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
                require_final_root_ctime=False,
            )
            if _tree_digest(first_stage) != first_tree:
                raise SatelliteQueueV86Error(
                    "v86 private queue stage changed while awaiting publication"
                )
            try:
                promote_noreplace(first_stage, output)
            except SystemExit as error:
                raise SatelliteQueueV86Error(str(error)) from error
            promoted = True
            carrier._fsync_directory(parent)
            _assert_final_root_ctime(output, target)
            try:
                manifest = validate_satellite_queue_v86(
                    output,
                    validation_wall_clock=datetime.fromtimestamp(clock(), UTC),
                    require_final_root_ctime=True,
                )
            except BaseException as error:
                try:
                    _rollback_final(
                        output, first_stage, first_identity, first_members
                    )
                    promoted = False
                except Exception as rollback_error:
                    error.add_note(f"v86 queue rollback failed: {rollback_error}")
                raise
        except BaseException as primary_error:
            if not promoted:
                for stage, identity, members in (
                    (first_stage, first_identity, first_members),
                    (second_stage, second_identity, second_members),
                ):
                    try:
                        _discard_stage(stage, identity, members or None)
                    except Exception as cleanup_error:
                        primary_error.add_note(
                            f"v86 queue stage cleanup failed: {cleanup_error}"
                        )
            raise
    if _require_accepted_inputs() != guard:
        raise SatelliteQueueV86Error("v86 queue publication mutated accepted inputs")
    return manifest


def publish_satellite_queue_v86(
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Publish the single reserved frozen v86 queue path."""

    if (
        not PUBLISHED_GENERATED_AT
        or generated_at != PUBLISHED_GENERATED_AT
        or PUBLISHED_MANIFEST_PIN[0] <= 0
        or PUBLISHED_MANIFEST_HASH_PIN[0] <= 0
        or not PUBLISHED_TREE_SHA256
    ):
        raise SatelliteQueueV86Error(
            "v86 publication timestamp or final pins are not reserved"
        )
    return _publish_to(
        QUEUE,
        PUBLICATION_LOCK,
        generated_at=generated_at,
        clock=_clock,
        sleeper=_sleep,
    )


__all__ = [
    "ACTIVE_DISTINCT_AOI_COUNT",
    "ACTIVE_ENTITY_COUNT",
    "ADDED_COUNT",
    "ADDED_PRIORITY_COUNTS",
    "ADDED_QUEUE_EXPECTATIONS",
    "ADDED_STATUS_COUNTS",
    "ALL_DISTINCT_AOI_COUNT",
    "ATLAS",
    "ATLAS_PIN",
    "CONFIG",
    "COORDINATE_METHOD_COUNTS",
    "DEFINITION",
    "DEFINITION_PIN",
    "EXPECTED_COUNTS",
    "GEOMETRY_ONLY_ENTITY_IDS",
    "INHERITED_POSITION_CHANGE_COUNT",
    "INHERITED_SEMANTIC_CHANGE_COUNT",
    "INHERITED_UNCHANGED_POSITION_COUNT",
    "PREDECESSOR_QUEUE",
    "PREDECESSOR_RETAINED_COUNT",
    "PUBLISHED_GENERATED_AT",
    "PUBLISHED_MANIFEST_HASH_PIN",
    "PUBLISHED_MANIFEST_PIN",
    "PUBLISHED_TREE_SHA256",
    "QUEUE",
    "QUEUE_PIN",
    "RELEASE",
    "RELEASE_MANIFEST_PIN",
    "RELEASE_TREE_SHA256",
    "REMOVED_COUNT",
    "SatelliteQueueV86Error",
    "V86_APPEND_STABLE_KEYS",
    "publish_satellite_queue_v86",
    "validate_satellite_queue_v86",
]
