from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    QueueConfig,
    validate_queue_bundle,
    write_queue_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"
QUEUE = ROOT / "satellite_review_queues" / "2026-07-20-open-seed-v44"
BASE_QUEUE = ROOT / "satellite_review_queues" / "2026-07-20-open-seed-v43"

GENERATED_AT = "2026-07-20T08:05:47Z"
MANIFEST_SHA256 = "41846b8f5d2f79e8c5251f845aad23d4bb1489ec69e0c254becf2fd55531c17e"
MANIFEST_SIDECAR_SHA256 = (
    "b997d94938cab67cc4a849c6fc72624c65c50bdd1a1147a3a7738dcff7b8cb75"
)
QUEUE_SHA256 = "be3e2fee5085bb26c5038d4fe33f40e80844500ff5d126889e9be74002369821"
BASE_QUEUE_SHA256 = "638eb3a3ee6312bef92c3046d3809592db17db58d70ad46afcf4f1720ac51f49"
SOURCE_ATLAS_SHA256 = (
    "12fce409ccbdddd75f26ea77c7b2d283f8b7f5ad9fb7116b6a36629566024903"
)
SOURCE_MANIFEST_SHA256 = (
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
)

ADDED = {
    "curated:menlo-digital-md-phx1-phoenix-campus": (
        101,
        "satq-905b7cac296079e986b955e1",
        "unknown",
    ),
    "curated:menlo-digital-md-phx1-phoenix-campus:current-site-preparation": (
        2,
        "satq-54c6402eb93d14f1ea754e66",
        "site_preparation",
    ),
    "curated:menlo-digital-md-va1-herndon-data-center": (
        86,
        "satq-fca9c2c4e38da3e927f67f81",
        "unknown",
    ),
    "curated:menlo-digital-md-va1-herndon-data-center:48mw-facility-build": (
        15,
        "satq-3288e71f7387eee72714a756",
        "shell",
    ),
}
REMOVED = {
    "curated:meta-richland-parish-data-center": (
        99,
        "satq-8666def6dbaeeca31b993693",
        "unknown",
    ),
    "curated:meta-richland-parish-data-center:current-development": (
        15,
        "satq-47b13b12d5cf43c9e64dd460",
        "under_construction",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (directory / QUEUE_FILENAME).read_text().splitlines()
    ]


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


class OpenSeedV44SatelliteQueueTests(unittest.TestCase):
    def test_exact_bundle_release_lineage_and_frozen_modes(self) -> None:
        manifest = validate_queue_bundle(QUEUE)
        self.assertEqual(_sha256(QUEUE / MANIFEST_FILENAME), MANIFEST_SHA256)
        self.assertEqual(
            _sha256(QUEUE / MANIFEST_HASH_FILENAME), MANIFEST_SIDECAR_SHA256
        )
        self.assertEqual(_sha256(QUEUE / QUEUE_FILENAME), QUEUE_SHA256)
        self.assertEqual(_sha256(BASE_QUEUE / QUEUE_FILENAME), BASE_QUEUE_SHA256)
        self.assertEqual(manifest["generated_at"], GENERATED_AT)
        self.assertEqual(
            manifest["configuration"],
            {
                "aoi_half_side_km": 2,
                "baseline_target": "2024-07-15",
                "catalog_limit": 100,
                "current_target": "2026-07-15",
                "eligible_entity_kinds": ["campus", "facility", "project"],
                "max_cloud_cover": 20,
                "minimum_component_area_m2": 5000,
                "provider": "earth-search-v1",
                "query_window_days": 45,
            },
        )
        source = manifest["source"]
        self.assertEqual(source["file"], "atlas.geojson")
        self.assertEqual(source["bytes"], 2_052_204)
        self.assertEqual(source["sha256"], SOURCE_ATLAS_SHA256)
        self.assertEqual(source["atlas_as_of"], "2026-07-20")
        self.assertEqual(source["atlas_recorded_at"], "2026-07-20T07:47:00Z")
        self.assertEqual(
            source["release_manifest"],
            {
                "as_of": "2026-07-20",
                "atlas_bytes": 2_052_204,
                "atlas_file": "atlas.geojson",
                "atlas_sha256": SOURCE_ATLAS_SHA256,
                "bytes": 7_672,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "recorded_at": "2026-07-20T07:47:00Z",
                "sha256": SOURCE_MANIFEST_SHA256,
            },
        )
        self.assertEqual(_sha256(RELEASE / "atlas.geojson"), SOURCE_ATLAS_SHA256)
        self.assertEqual(_sha256(RELEASE / "manifest.json"), SOURCE_MANIFEST_SHA256)

        self.assertFalse(QUEUE.is_symlink())
        self.assertEqual(stat.S_IMODE(QUEUE.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in QUEUE.iterdir()},
            {QUEUE_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME},
        )
        for path in QUEUE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

    def test_counts_ordering_and_imagery_guardrails(self) -> None:
        manifest = json.loads((QUEUE / MANIFEST_FILENAME).read_text())
        counts = manifest["counts"]
        self.assertEqual(counts["features_examined"], 573)
        self.assertEqual(
            counts["eligible_features_by_kind"], {"campus": 312, "project": 261}
        )
        self.assertEqual(counts["entities_queued"], 143)
        self.assertEqual(counts["queue_jobs"], 143)
        self.assertEqual(counts["skipped_missing_coordinates"], 430)
        self.assertEqual(counts["entities_split_at_antimeridian"], 0)
        self.assertEqual(
            counts["queued_entities_by_priority_tier"],
            {
                "active_construction": 78,
                "operational": 29,
                "proposed_pipeline": 4,
                "unknown": 32,
            },
        )
        self.assertEqual(
            counts["queued_entities_by_status_freshness"],
            {
                "age_days_0_30": 82,
                "age_days_181_365": 2,
                "age_days_31_90": 15,
                "age_days_366_plus": 1,
                "age_days_91_180": 11,
                "missing": 32,
            },
        )

        records = _records(QUEUE)
        self.assertEqual([row["queue_position"] for row in records], list(range(1, 144)))
        self.assertEqual(len({row["queue_id"] for row in records}), 143)
        self.assertEqual(records[0]["queue_id"], "satq-02a713b5d0ec25375cffb0c3")
        self.assertEqual(records[-1]["entity"]["id"], "f71ea294-a158-54a7-b08d-43f900b14ac4")
        expected_constraints = {
            "imagery_identity_claim": False,
            "imagery_lifecycle_claim": False,
            "imagery_operating_status_claim": False,
            "imagery_power_claim": False,
            "queue_basis": "existing_atlas_entity_and_location",
            "review_required": True,
        }
        for row in records:
            self.assertEqual(row["review_constraints"], expected_constraints)
            self.assertFalse(_contains_key(row, "capacity_estimates"))
            self.assertFalse(_contains_key(row, "workload_tags"))
            self.assertEqual(row["catalog_job"]["script"], "scripts/catalog_satellite.py")
            self.assertEqual(
                row["change_job_template"]["script"], "scripts/sentinel_change.py"
            )
        self.assertEqual(
            manifest["scope"],
            {
                "automatic_entity_merge": False,
                "imagery_identity_inference": False,
                "imagery_lifecycle_inference": False,
                "imagery_power_inference": False,
                "network_requests_performed": False,
                "purpose": "bounded imagery review planning for existing atlas entities",
            },
        )

    def test_exact_v43_queue_delta_and_meta_coordinate_retirement(self) -> None:
        old = {row["entity"]["stable_key"]: row for row in _records(BASE_QUEUE)}
        new = {row["entity"]["stable_key"]: row for row in _records(QUEUE)}
        self.assertEqual((len(old), len(new), len(old.keys() & new.keys())), (141, 143, 139))
        self.assertEqual(set(new) - set(old), set(ADDED))
        self.assertEqual(set(old) - set(new), set(REMOVED))

        for stable_key, (position, queue_id, status) in ADDED.items():
            row = new[stable_key]
            self.assertEqual(
                (row["queue_position"], row["queue_id"], row["priority"]["lifecycle_status"]),
                (position, queue_id, status),
            )
        for stable_key, (position, queue_id, status) in REMOVED.items():
            row = old[stable_key]
            self.assertEqual(
                (row["queue_position"], row["queue_id"], row["priority"]["lifecycle_status"]),
                (position, queue_id, status),
            )

        for stable_key in old.keys() & new.keys():
            before = deepcopy(old[stable_key])
            after = deepcopy(new[stable_key])
            before.pop("queue_position")
            after.pop("queue_position")
            self.assertEqual(after, before, stable_key)

        self.assertNotIn("curated:meta-richland-parish-data-center", new)
        self.assertNotIn(
            "curated:meta-richland-parish-data-center:current-development", new
        )

    def test_offline_reproduction_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_directory = root / "release"
            source_directory.mkdir()
            for name in ("atlas.geojson", "manifest.json"):
                (source_directory / name).write_bytes((RELEASE / name).read_bytes())
            output = root / "queue"
            config = QueueConfig(
                baseline_target="2024-07-15",
                current_target="2026-07-15",
                provider="earth-search-v1",
                query_window_days=45,
                max_cloud_cover=20,
                catalog_limit=100,
                aoi_half_side_km=2,
                minimum_component_area_m2=5_000,
            )
            with ExitStack() as stack:
                failure = AssertionError("v44 queue reproduction attempted network access")
                for name in (
                    "socket",
                    "create_connection",
                    "getaddrinfo",
                    "gethostbyname",
                ):
                    stack.enter_context(patch.object(socket, name, side_effect=failure))
                write_queue_bundle(
                    source_directory / "atlas.geojson",
                    output,
                    generated_at=GENERATED_AT,
                    config=config,
                )
            for name in (QUEUE_FILENAME, MANIFEST_FILENAME, MANIFEST_HASH_FILENAME):
                self.assertEqual((output / name).read_bytes(), (QUEUE / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
