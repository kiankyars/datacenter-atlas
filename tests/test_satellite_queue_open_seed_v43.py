from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
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
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v43"
QUEUE = ROOT / "satellite_review_queues" / "2026-07-20-open-seed-v43"

GENERATED_AT = "2026-07-20T06:52:14Z"
MANIFEST_SHA256 = "ca0d03f03749f30001533c79b15e31af841f392cb60eb23c7319d7c7ffce7d97"
MANIFEST_SIDECAR_SHA256 = (
    "2ffdbb9c23fcaefd4c189601131d250e5598df7472d11c76e9a22f3fe41fc46c"
)
QUEUE_SHA256 = "638eb3a3ee6312bef92c3046d3809592db17db58d70ad46afcf4f1720ac51f49"
SOURCE_ATLAS_SHA256 = (
    "90a360895650e424a8e623f028a4a3df8d9036c89679b4c8462922bac69954be"
)
SOURCE_MANIFEST_SHA256 = (
    "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records() -> list[dict]:
    return [json.loads(line) for line in (QUEUE / QUEUE_FILENAME).read_text().splitlines()]


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


class OpenSeedV43SatelliteQueueTests(unittest.TestCase):
    def test_exact_bundle_and_release_lineage(self) -> None:
        manifest = validate_queue_bundle(QUEUE)
        self.assertEqual(_sha256(QUEUE / MANIFEST_FILENAME), MANIFEST_SHA256)
        self.assertEqual(
            _sha256(QUEUE / MANIFEST_HASH_FILENAME), MANIFEST_SIDECAR_SHA256
        )
        self.assertEqual(_sha256(QUEUE / QUEUE_FILENAME), QUEUE_SHA256)
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
        self.assertEqual(source["bytes"], 1_960_393)
        self.assertEqual(source["sha256"], SOURCE_ATLAS_SHA256)
        self.assertEqual(source["atlas_as_of"], "2026-07-20")
        self.assertEqual(source["atlas_recorded_at"], "2026-07-20T06:41:44Z")
        self.assertEqual(
            source["release_manifest"],
            {
                "as_of": "2026-07-20",
                "atlas_bytes": 1_960_393,
                "atlas_file": "atlas.geojson",
                "atlas_sha256": SOURCE_ATLAS_SHA256,
                "bytes": 7_056,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "recorded_at": "2026-07-20T06:41:44Z",
                "sha256": SOURCE_MANIFEST_SHA256,
            },
        )
        self.assertEqual(_sha256(RELEASE / "atlas.geojson"), SOURCE_ATLAS_SHA256)
        self.assertEqual(_sha256(RELEASE / "manifest.json"), SOURCE_MANIFEST_SHA256)

    def test_counts_ordering_and_imagery_guardrails(self) -> None:
        manifest = json.loads((QUEUE / MANIFEST_FILENAME).read_text())
        counts = manifest["counts"]
        self.assertEqual(counts["features_examined"], 544)
        self.assertEqual(counts["eligible_features_by_kind"], {"campus": 298, "project": 246})
        self.assertEqual(counts["entities_queued"], 141)
        self.assertEqual(counts["queue_jobs"], 141)
        self.assertEqual(counts["skipped_missing_coordinates"], 403)
        self.assertEqual(counts["entities_split_at_antimeridian"], 0)
        self.assertEqual(
            counts["queued_entities_by_priority_tier"],
            {
                "active_construction": 77,
                "operational": 29,
                "proposed_pipeline": 4,
                "unknown": 31,
            },
        )
        self.assertEqual(
            counts["queued_entities_by_status_freshness"],
            {
                "age_days_0_30": 82,
                "age_days_181_365": 1,
                "age_days_31_90": 15,
                "age_days_366_plus": 1,
                "age_days_91_180": 11,
                "missing": 31,
            },
        )

        records = _records()
        self.assertEqual([row["queue_position"] for row in records], list(range(1, 142)))
        self.assertEqual(len({row["queue_id"] for row in records}), 141)
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
            self.assertEqual(row["change_job_template"]["script"], "scripts/sentinel_change.py")
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
                stack.enter_context(
                    patch.object(socket, "create_connection", side_effect=AssertionError("network"))
                )
                stack.enter_context(
                    patch.object(socket, "getaddrinfo", side_effect=AssertionError("network"))
                )
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
