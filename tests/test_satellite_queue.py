from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    QueueConfig,
    QueueValidationError,
    build_queue_bundle,
    validate_queue_bundle,
    write_queue_bundle,
)


GENERATED_AT = "2026-07-18T14:30:00-07:00"
CONFIG = QueueConfig(
    baseline_target="2024-06-15",
    current_target="2026-06-15",
    query_window_days=30,
    aoi_half_side_km=2,
)


def feature(
    entity_id: str,
    status: str | None,
    *,
    kind: str = "facility",
    latitude: float | None = 38.9,
    longitude: float | None = -77.0,
    geometry: dict | None = None,
    status_as_of: str | None = "2026-07-18",
    country: str | None = None,
    country_iso_a2: str | None = None,
    country_iso_a3: str | None = None,
) -> dict:
    properties = {
        "entity_id": entity_id,
        "entity_kind": kind,
        "stable_key": f"fixture:{entity_id}",
        "name": f"Site {entity_id}",
        "latitude": latitude,
        "longitude": longitude,
        "status": status,
        "status_as_of": status_as_of,
        "country": country,
        "country_iso_a2": country_iso_a2,
        "country_iso_a3": country_iso_a3,
        "snapshot_evidence_id": f"snapshot-{entity_id}",
        "status_evidence_id": f"status-{entity_id}" if status else None,
        "source_family": "fixture",
        "source_url": f"https://example.test/{entity_id}",
        "source_license": "CC0-1.0",
        "capacity_estimates": [
            {"metric": "gross_facility_mw", "base": 999_999}
        ],
    }
    return {
        "type": "Feature",
        "id": entity_id,
        "geometry": geometry,
        "properties": properties,
    }


def atlas(*features: dict) -> bytes:
    return (
        json.dumps(
            {
                "type": "FeatureCollection",
                "atlas_as_of": "2026-07-18",
                "atlas_recorded_at": "2026-07-18T20:00:00Z",
                "attribution": ["Fixture attribution"],
                "features": list(features),
            },
            indent=2,
        )
        + "\n"
    ).encode()


def queue_records(raw: bytes) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines()]


def rewrite_manifest(output: Path, manifest: dict) -> None:
    raw = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    (output / MANIFEST_FILENAME).write_bytes(raw)
    (output / MANIFEST_HASH_FILENAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {MANIFEST_FILENAME}\n",
        encoding="ascii",
    )


def rewrite_queue(output: Path, records: list[dict]) -> None:
    raw = b"".join(
        (
            json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode()
        for record in records
    )
    (output / QUEUE_FILENAME).write_bytes(raw)
    manifest = json.loads((output / MANIFEST_FILENAME).read_text())
    manifest["artifacts"][QUEUE_FILENAME] = {
        "format": "application/x-ndjson",
        "records": len(records),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    rewrite_manifest(output, manifest)


class QueuePlanningTests(unittest.TestCase):
    def test_lifecycle_priority_is_deterministic_and_capacity_is_not_copied(self) -> None:
        raw = atlas(
            feature("operating", "operational"),
            feature("unknown", None, kind="campus"),
            feature("proposed", "proposed", kind="project"),
            feature("building", "under_construction", kind="building"),
            feature("missing", "under_construction", latitude=None, longitude=None),
            feature("construction", "under_construction"),
        )
        bundle = build_queue_bundle(
            raw,
            source_name="atlas.geojson",
            generated_at=GENERATED_AT,
            config=CONFIG,
        )
        records = queue_records(bundle.queue_bytes)
        self.assertEqual(
            [record["entity"]["id"] for record in records],
            ["construction", "proposed", "unknown", "operating"],
        )
        self.assertEqual(
            [record["priority"]["rank"] for record in records], [0, 1, 2, 3]
        )
        self.assertEqual(
            [record["queue_position"] for record in records], [1, 2, 3, 4]
        )
        self.assertNotIn("capacity_estimates", bundle.queue_bytes.decode())
        for record in records:
            self.assertFalse(record["review_constraints"]["imagery_identity_claim"])
            self.assertFalse(record["review_constraints"]["imagery_lifecycle_claim"])
            self.assertFalse(record["review_constraints"]["imagery_power_claim"])
            bbox = record["location"]["aoi_bbox_wgs84"]
            self.assertLess(bbox[0], bbox[2])
            self.assertIn("scripts/catalog_satellite.py", record["catalog_job"]["script"])
            self.assertIn("--bbox", record["catalog_job"]["arguments"])
            self.assertEqual(
                record["change_job_template"]["selected_id_json_pointers"],
                {
                    "{selected_ids.baseline}": "/selected_ids/baseline",
                    "{selected_ids.current}": "/selected_ids/current",
                },
            )
        counts = bundle.manifest["counts"]
        self.assertEqual(counts["features_examined"], 6)
        self.assertEqual(counts["entities_queued"], 4)
        self.assertEqual(counts["queue_jobs"], 4)
        self.assertEqual(counts["skipped_missing_coordinates"], 1)
        self.assertEqual(counts["excluded_features_by_kind"], {"building": 1})
        self.assertEqual(bundle.manifest["generated_at"], "2026-07-18T21:30:00Z")
        self.assertEqual(
            bundle.manifest["source"]["sha256"], hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual(
            bundle.manifest["artifacts"][QUEUE_FILENAME]["sha256"],
            hashlib.sha256(bundle.queue_bytes).hexdigest(),
        )
        repeated = build_queue_bundle(
            raw,
            source_name="atlas.geojson",
            generated_at=GENERATED_AT,
            config=CONFIG,
        )
        self.assertEqual(bundle.queue_bytes, repeated.queue_bytes)
        self.assertEqual(bundle.manifest_bytes, repeated.manifest_bytes)
        self.assertEqual(bundle.manifest_hash_bytes, repeated.manifest_hash_bytes)

    def test_country_balance_and_status_freshness_are_auditable(self) -> None:
        raw = atlas(
            feature(
                "fresh",
                "proposed",
                status_as_of="2026-07-17",
                country="United States",
                country_iso_a2="US",
                country_iso_a3="USA",
            ),
            feature(
                "old",
                "proposed",
                status_as_of="2025-01-01",
                country="United States",
                country_iso_a2="US",
                country_iso_a3="USA",
            ),
            feature(
                "missing-date",
                "proposed",
                status_as_of=None,
                country="Finland",
                country_iso_a2="FI",
                country_iso_a3="FIN",
            ),
            feature("unmatched", "operational", status_as_of="2026-06-01"),
        )
        bundle = build_queue_bundle(
            raw,
            source_name="atlas.geojson",
            generated_at=GENERATED_AT,
            config=CONFIG,
        )
        records = queue_records(bundle.queue_bytes)
        self.assertEqual(
            [record["entity"]["id"] for record in records],
            ["missing-date", "old", "fresh", "unmatched"],
        )
        freshness = {record["entity"]["id"]: record["status_freshness"] for record in records}
        self.assertEqual(
            freshness["missing-date"],
            {
                "status_as_of": None,
                "age_days_at_atlas_as_of": None,
                "missing": True,
            },
        )
        self.assertEqual(freshness["old"]["age_days_at_atlas_as_of"], 563)
        self.assertEqual(freshness["fresh"]["age_days_at_atlas_as_of"], 1)
        self.assertEqual(
            {
                field: records[0]["entity"][field]
                for field in ("country", "country_iso_a2", "country_iso_a3")
            },
            {
                "country": "Finland",
                "country_iso_a2": "FI",
                "country_iso_a3": "FIN",
            },
        )
        country_counts = bundle.manifest["counts"][
            "queued_entities_by_country_priority_tier"
        ]
        self.assertEqual(
            country_counts,
            [
                {
                    "country": None,
                    "country_iso_a2": None,
                    "country_iso_a3": None,
                    "entities": 1,
                    "by_priority_tier": {"operational": 1},
                },
                {
                    "country": "Finland",
                    "country_iso_a2": "FI",
                    "country_iso_a3": "FIN",
                    "entities": 1,
                    "by_priority_tier": {"proposed_pipeline": 1},
                },
                {
                    "country": "United States",
                    "country_iso_a2": "US",
                    "country_iso_a3": "USA",
                    "entities": 2,
                    "by_priority_tier": {"proposed_pipeline": 2},
                },
            ],
        )
        self.assertEqual(
            bundle.manifest["counts"]["queued_entities_by_status_freshness"],
            {
                "missing": 1,
                "age_days_0_30": 1,
                "age_days_31_90": 1,
                "age_days_91_180": 0,
                "age_days_181_365": 0,
                "age_days_366_plus": 1,
            },
        )

    def test_geometry_center_and_antimeridian_are_losslessly_split_into_jobs(self) -> None:
        raw = atlas(
            feature(
                "dateline",
                "unknown",
                latitude=None,
                longitude=None,
                geometry={"type": "Point", "coordinates": [179.99, 1.0]},
            )
        )
        bundle = build_queue_bundle(
            raw,
            source_name="atlas.geojson",
            generated_at="2026-07-18T20:00:00Z",
            config=QueueConfig(
                baseline_target="2024-01-01",
                current_target="2026-01-01",
                aoi_half_side_km=5,
            ),
        )
        records = queue_records(bundle.queue_bytes)
        self.assertEqual(len(records), 2)
        self.assertEqual(bundle.manifest["counts"]["entities_queued"], 1)
        self.assertEqual(bundle.manifest["counts"]["queue_jobs"], 2)
        self.assertEqual(
            bundle.manifest["counts"]["entities_split_at_antimeridian"], 1
        )
        self.assertEqual({record["location"]["part_count"] for record in records}, {2})
        self.assertEqual(
            {record["location"]["center_wgs84"]["method"] for record in records},
            {"geometry_bounds_center"},
        )
        for record in records:
            west, south, east, north = record["location"]["aoi_bbox_wgs84"]
            self.assertTrue(-180 <= west < east <= 180)
            self.assertTrue(-90 <= south < north <= 90)

    def test_input_and_config_errors_fail_closed(self) -> None:
        invalid_features = (
            [feature("duplicate", "unknown"), feature("duplicate", "operational")],
            [feature("bad-status", "invented")],
            [feature("bad-kind", "unknown", kind="power_asset")],
            [feature("half-coordinate", "unknown", longitude=None)],
        )
        patterns = ("duplicate", "unknown lifecycle", "entity_kind", "both be present")
        for features, pattern in zip(invalid_features, patterns):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(
                QueueValidationError, pattern
            ):
                build_queue_bundle(
                    atlas(*features),
                    source_name="atlas.geojson",
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )
        mismatch = feature("mismatch", "unknown")
        mismatch["id"] = "different"
        with self.assertRaisesRegex(QueueValidationError, "must match"):
            build_queue_bundle(
                atlas(mismatch),
                source_name="atlas.geojson",
                generated_at=GENERATED_AT,
                config=CONFIG,
            )
        with self.assertRaisesRegex(QueueValidationError, "before current"):
            QueueConfig("2026-01-01", "2026-01-01")
        with self.assertRaisesRegex(QueueValidationError, "must not overlap"):
            QueueConfig("2026-01-01", "2026-02-01", query_window_days=20)
        with self.assertRaisesRegex(QueueValidationError, "must not exceed"):
            QueueConfig("2024-01-01", "2026-01-01", aoi_half_side_km=26)
        for invalid, pattern in (
            (
                feature("future", "proposed", status_as_of="2026-07-19"),
                "after atlas_as_of",
            ),
            (
                feature("invalid-date", "proposed", status_as_of="2026-02-30"),
                "valid YYYY-MM-DD",
            ),
            (
                feature("invalid-a2", "proposed", country_iso_a2="us"),
                "uppercase ISO alpha-2",
            ),
            (
                feature("invalid-a3", "proposed", country_iso_a3="US"),
                "uppercase ISO alpha-3",
            ),
        ):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(
                QueueValidationError, pattern
            ):
                build_queue_bundle(
                    atlas(invalid),
                    source_name="atlas.geojson",
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )


class QueueBundleWritingTests(unittest.TestCase):
    def test_writer_hashes_exact_manifest_and_queue_bytes(self) -> None:
        raw = atlas(
            feature(
                "site",
                "under_construction",
                latitude=38.123456789,
                longitude=-77.987654321,
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "atlas.geojson"
            output = root / "queue"
            source.write_bytes(raw)
            first = write_queue_bundle(
                source,
                output,
                generated_at=GENERATED_AT,
                config=CONFIG,
            )
            queue_raw = (output / QUEUE_FILENAME).read_bytes()
            manifest_raw = (output / MANIFEST_FILENAME).read_bytes()
            sidecar = (output / MANIFEST_HASH_FILENAME).read_text(encoding="ascii")
            self.assertEqual(
                hashlib.sha256(queue_raw).hexdigest(),
                first["artifacts"][QUEUE_FILENAME]["sha256"],
            )
            self.assertEqual(
                sidecar,
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n",
            )
            before = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            second = write_queue_bundle(
                source,
                output,
                generated_at=GENERATED_AT,
                config=CONFIG,
            )
            after = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            self.assertEqual(first, second)
            self.assertEqual(before, after)

    def test_validator_rejects_every_tampered_bundle_surface(self) -> None:
        def publish(root: Path) -> Path:
            source = root / "atlas.geojson"
            output = root / "queue"
            source.write_bytes(
                atlas(
                    feature("one", "proposed"),
                    feature("two", "operational"),
                )
            )
            write_queue_bundle(
                source, output, generated_at=GENERATED_AT, config=CONFIG
            )
            self.assertEqual(validate_queue_bundle(output)["counts"]["queue_jobs"], 2)
            return output

        def extra_file(output: Path) -> None:
            (output / "unexpected.txt").write_text("unexpected")

        def queue_bytes(output: Path) -> None:
            with (output / QUEUE_FILENAME).open("ab") as destination:
                destination.write(b" ")

        def sidecar(output: Path) -> None:
            (output / MANIFEST_HASH_FILENAME).write_text("0" * 64 + "  manifest.json\n")

        def manifest_schema(output: Path) -> None:
            manifest = json.loads((output / MANIFEST_FILENAME).read_text())
            manifest["unexpected"] = True
            rewrite_manifest(output, manifest)

        def queue_position(output: Path) -> None:
            records = queue_records((output / QUEUE_FILENAME).read_bytes())
            records[0]["queue_position"] = 2
            rewrite_queue(output, records)

        def duplicate_queue_id(output: Path) -> None:
            records = queue_records((output / QUEUE_FILENAME).read_bytes())
            records[1]["queue_id"] = records[0]["queue_id"]
            rewrite_queue(output, records)

        for name, mutate in (
            ("extra file", extra_file),
            ("queue bytes", queue_bytes),
            ("sidecar", sidecar),
            ("manifest schema", manifest_schema),
            ("queue position", queue_position),
            ("duplicate queue id", duplicate_queue_id),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                output = publish(Path(temporary))
                mutate(output)
                with self.assertRaises(QueueValidationError):
                    validate_queue_bundle(output)

    def test_existing_bundle_is_never_replaced_unless_byte_identical(self) -> None:
        raw = atlas(feature("site", "under_construction"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "atlas.geojson"
            output = root / "queue"
            source.write_bytes(raw)
            write_queue_bundle(
                source, output, generated_at=GENERATED_AT, config=CONFIG
            )
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            with self.assertRaisesRegex(QueueValidationError, "not byte-identical"):
                write_queue_bundle(
                    source,
                    output,
                    generated_at="2026-07-18T22:00:00Z",
                    config=CONFIG,
                )
            self.assertEqual(
                before, {path.name: path.read_bytes() for path in output.iterdir()}
            )
            with (output / QUEUE_FILENAME).open("ab") as destination:
                destination.write(b"tampered")
            tampered = (output / QUEUE_FILENAME).read_bytes()
            with self.assertRaises(QueueValidationError):
                write_queue_bundle(
                    source, output, generated_at=GENERATED_AT, config=CONFIG
                )
            self.assertEqual((output / QUEUE_FILENAME).read_bytes(), tampered)

    def test_first_publication_cleans_staging_on_validation_failure(self) -> None:
        raw = atlas(feature("site", "under_construction"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "atlas.geojson"
            output = root / "queue"
            source.write_bytes(raw)
            with patch(
                "datacenter_atlas.satellite_queue.validate_queue_bundle",
                side_effect=QueueValidationError("injected validation failure"),
            ), self.assertRaisesRegex(QueueValidationError, "injected"):
                write_queue_bundle(
                    source, output, generated_at=GENERATED_AT, config=CONFIG
                )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".queue.staging-*")), [])

    def test_adjacent_release_manifest_is_verified_and_hash_bound(self) -> None:
        raw = atlas(feature("site", "under_construction"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "atlas.geojson"
            output = root / "queue"
            source.write_bytes(raw)
            release_manifest = {
                "format": "datacenter-atlas-release-v1",
                "as_of": "2026-07-18",
                "recorded_at": "2026-07-18T20:00:00Z",
                "files": {
                    "atlas.geojson": {
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                },
            }
            release_raw = (json.dumps(release_manifest, sort_keys=True) + "\n").encode()
            (root / MANIFEST_FILENAME).write_bytes(release_raw)
            manifest = write_queue_bundle(
                source, output, generated_at=GENERATED_AT, config=CONFIG
            )
            lineage = manifest["source"]["release_manifest"]
            self.assertEqual(lineage["bytes"], len(release_raw))
            self.assertEqual(lineage["sha256"], hashlib.sha256(release_raw).hexdigest())
            self.assertEqual(lineage["atlas_bytes"], len(raw))
            self.assertEqual(lineage["atlas_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(validate_queue_bundle(output), manifest)

            release_manifest["files"]["atlas.geojson"]["bytes"] += 1
            (root / MANIFEST_FILENAME).write_text(json.dumps(release_manifest))
            rejected_output = root / "rejected-queue"
            with self.assertRaisesRegex(QueueValidationError, "does not match exact"):
                write_queue_bundle(
                    source,
                    rejected_output,
                    generated_at=GENERATED_AT,
                    config=CONFIG,
                )
            self.assertFalse(rejected_output.exists())


if __name__ == "__main__":
    unittest.main()
