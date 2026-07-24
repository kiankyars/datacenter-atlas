from __future__ import annotations

import io
import hashlib
import json
import shutil
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.ohsome import (
    DATA_CENTER_FILTER,
    BoundingBox,
    OhsomeFetcher,
    OhsomeGeoJSONAdapter,
    initial_grid,
)


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "ohsome"
RETRIEVED_AT = "2026-07-17T19:00:00Z"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        return self.body if limit < 0 else self.body[:limit]


def response_for(request_url: str, features: list[dict] | None = None) -> FakeResponse:
    return FakeResponse(
        {
            "apiVersion": "1.10.4",
            "metadata": {"requestUrl": request_url},
            "type": "FeatureCollection",
            "features": features or [],
        }
    )


TARGETING_SIGNAL = "Taginfo occupied-cell targeting signal; not facility geometry or a facility count"


def target_bboxes_document(entries: list[tuple[str, list[int]]]) -> dict:
    bboxes = []
    for identifier, bbox in entries:
        west, south, east, north = bbox
        bboxes.append(
            {
                "id": identifier,
                "bbox": bbox,
                "west": west,
                "south": south,
                "east": east,
                "north": north,
                "ohsome_bbox": f"{identifier}:{west},{south},{east},{north}",
                "targeting_signal": TARGETING_SIGNAL,
                "occupied_1deg_signal_cells": 1,
                "tag_signals": [
                    {
                        "key": "telecom",
                        "value": "data_center",
                        "element_type": "ways",
                    }
                ],
            }
        )
    return {
        "schema_version": 1,
        "targeting_signal": TARGETING_SIGNAL,
        "cell_degrees": 5,
        "bbox_count": len(bboxes),
        "ohsome_bboxes_parameter": "|".join(
            bbox["ohsome_bbox"] for bbox in bboxes
        ),
        "bboxes": bboxes,
    }


def write_target_bboxes(path: Path, entries: list[tuple[str, list[int]]]) -> bytes:
    payload = (json.dumps(target_bboxes_document(entries), sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return payload


class OhsomeFetchTests(unittest.TestCase):
    def test_filter_is_explicit_and_covers_direct_and_development_tags(self) -> None:
        for key in (
            "telecom",
            "building",
            "man_made",
            "landuse",
            "site",
            "amenity",
            "industrial",
            "construction",
            "proposed",
            "construction:telecom",
            "proposed:industrial",
        ):
            for value in ("data_center", "data_centre", "datacenter", "datacentre"):
                self.assertIn(f"{key}={value}", DATA_CENTER_FILTER)
        self.assertNotIn(" in (", DATA_CENTER_FILTER)

    def test_initial_grid_is_complete_without_overlap(self) -> None:
        grid = initial_grid(BoundingBox(-20, -10, 20, 10), 10)
        self.assertEqual(len(grid), 8)
        area = sum(
            (bbox.east - bbox.west) * (bbox.north - bbox.south)
            for _, bbox in grid
        )
        self.assertEqual(area, 800)

    def test_fetch_uses_required_post_parameters_and_transparent_user_agent(self) -> None:
        requests = []

        def opener(request, *, timeout):
            requests.append((request, timeout))
            return response_for("https://api.ohsome.org/exact-request")

        with tempfile.TemporaryDirectory() as directory:
            manifest = OhsomeFetcher(
                opener=opener,
                sleeper=lambda _: None,
                request_interval=0,
            ).fetch(
                directory,
                snapshot_time="2026-07-17T00:00:00Z",
                bounds=BoundingBox(0, 0, 1, 1),
                cell_degrees=1,
            )
            self.assertEqual(manifest["summary"]["completed"], 1)
            self.assertEqual(len(requests), 1)
            request, timeout = requests[0]
            self.assertEqual(request.method, "POST")
            self.assertEqual(timeout, 120.0)
            form = urllib.parse.parse_qs(request.data.decode())
            self.assertEqual(form["properties"], ["tags,metadata"])
            self.assertEqual(form["clipGeometry"], ["false"])
            self.assertEqual(form["filter"], [DATA_CENTER_FILTER])
            self.assertEqual(form["time"], ["2026-07-17T00:00:00Z"])
            self.assertIn("DataCenterAtlas", request.get_header("User-agent"))

    def test_timeout_splits_cell_and_retry_after_is_honored(self) -> None:
        sleeps = []
        calls = 0

        def opener(request, *, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise urllib.error.HTTPError(
                    request.full_url,
                    504,
                    "Gateway Timeout",
                    {"Retry-After": "7"},
                    io.BytesIO(b"query timeout"),
                )
            if calls == 2:
                raise urllib.error.HTTPError(
                    request.full_url,
                    504,
                    "Gateway Timeout",
                    {},
                    io.BytesIO(b"query timeout"),
                )
            return response_for("https://api.ohsome.org/child")

        with tempfile.TemporaryDirectory() as directory:
            manifest = OhsomeFetcher(
                opener=opener,
                sleeper=sleeps.append,
                monotonic=lambda: 100.0,
                request_interval=0,
                max_retries=1,
            ).fetch(
                directory,
                snapshot_time="2026-07-17",
                bounds=BoundingBox(0, 0, 2, 2),
                cell_degrees=2,
                minimum_span=0.1,
            )
        self.assertIn(7.0, sleeps)
        self.assertEqual(manifest["summary"]["split"], 1)
        self.assertEqual(manifest["summary"]["completed"], 4)
        self.assertEqual(calls, 6)

    def test_resume_does_not_refetch_completed_shards(self) -> None:
        calls = []

        def opener(request, *, timeout):
            calls.append(request)
            return response_for("https://api.ohsome.org/request")

        with tempfile.TemporaryDirectory() as directory:
            fetcher = OhsomeFetcher(opener=opener, sleeper=lambda _: None, request_interval=0)
            first = fetcher.fetch(
                directory,
                snapshot_time="2026-07-17",
                bounds=BoundingBox(0, 0, 2, 1),
                cell_degrees=1,
                max_requests=1,
            )
            self.assertEqual(first["summary"]["completed"], 1)
            self.assertEqual(first["summary"]["pending"], 1)
            second = fetcher.fetch(
                directory,
                snapshot_time="2026-07-17",
                bounds=BoundingBox(0, 0, 2, 1),
                cell_degrees=1,
            )
            self.assertEqual(second["summary"]["completed"], 2)
            self.assertEqual(len(calls), 2)

    def test_transient_circuit_break_and_explicit_failed_retry(self) -> None:
        first_run_calls = 0

        def unstable_opener(request, *, timeout):
            nonlocal first_run_calls
            first_run_calls += 1
            if first_run_calls == 1:
                return response_for("https://api.ohsome.org/completed-before-outage")
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                {},
                io.BytesIO(b'{"error":"Service Unavailable"}'),
            )

        with tempfile.TemporaryDirectory() as directory:
            first = OhsomeFetcher(
                opener=unstable_opener,
                sleeper=lambda _: None,
                request_interval=0,
                max_retries=0,
            ).fetch(
                directory,
                snapshot_time="2026-07-17",
                bounds=BoundingBox(0, 0, 4, 1),
                cell_degrees=1,
                transient_failure_limit=2,
            )
            self.assertEqual(first_run_calls, 3)
            self.assertEqual(first["summary"]["completed"], 1)
            self.assertEqual(first["summary"]["failed"], 2)
            self.assertEqual(first["summary"]["pending"], 1)
            self.assertEqual(
                first["last_run"]["stop_reason"],
                "transient_service_circuit_break",
            )

            resumed_calls = []

            def recovered_opener(request, *, timeout):
                resumed_calls.append(request)
                return response_for("https://api.ohsome.org/recovered")

            resumed = OhsomeFetcher(
                opener=recovered_opener,
                sleeper=lambda _: None,
                request_interval=0,
            ).fetch(
                directory,
                snapshot_time="2026-07-17",
                bounds=BoundingBox(0, 0, 4, 1),
                cell_degrees=1,
                retry_failed=True,
            )
            self.assertEqual(len(resumed_calls), 3)
            self.assertEqual(resumed["summary"]["completed"], 4)
            self.assertEqual(resumed["summary"]["failed"], 0)
            self.assertEqual(resumed["summary"]["pending"], 0)
            self.assertEqual(
                resumed["last_run"]["retried_failed_task_ids"],
                ["g000_001", "g000_002"],
            )
            self.assertEqual(len(resumed["retry_events"]), 1)

    def test_targeted_fetch_uses_named_bboxes_and_keeps_far_targets_separate(self) -> None:
        forms = []

        def opener(request, *, timeout):
            form = urllib.parse.parse_qs(request.data.decode())
            forms.append(form)
            return response_for("https://api.ohsome.org/targeted")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target_path = root / "target_bboxes.json"
            raw = write_target_bboxes(
                target_path,
                [
                    ("near_a", [0, 0, 5, 5]),
                    ("near_b", [5, 0, 10, 5]),
                    ("far", [100, 0, 105, 5]),
                ],
            )
            output = root / "output"
            manifest = OhsomeFetcher(
                opener=opener, sleeper=lambda _: None, request_interval=0
            ).fetch(
                output,
                snapshot_time="2026-07-17",
                target_bboxes=target_path,
                target_bboxes_sha256=hashlib.sha256(raw).hexdigest(),
                target_batch_size=10,
                max_batch_span_degrees=20,
            )

            self.assertEqual(len(forms), 2)
            parameters = {form["bboxes"][0] for form in forms}
            self.assertEqual(
                parameters,
                {
                    "near_a:0,0,5,5|near_b:5,0,10,5",
                    "far:100,0,105,5",
                },
            )
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(
                (output / "inputs" / "target_bboxes.json").read_bytes(), raw
            )
            self.assertEqual(
                manifest["inputs"]["target_bboxes"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )
            for task in manifest["tasks"].values():
                west, south, east, north = task["request_envelope"]
                self.assertLessEqual(east - west, 20)
                self.assertLessEqual(north - south, 20)
                self.assertEqual(task["target_ids"], [box["id"] for box in task["bboxes"]])

    def test_targeted_failure_splits_batch_before_subdividing_singleton(self) -> None:
        calls: list[str] = []
        failed_singleton = False

        def opener(request, *, timeout):
            nonlocal failed_singleton
            parameter = urllib.parse.parse_qs(request.data.decode())["bboxes"][0]
            calls.append(parameter)
            if "|" in parameter or (parameter.startswith("a:") and not failed_singleton):
                if "|" not in parameter:
                    failed_singleton = True
                raise urllib.error.HTTPError(
                    request.full_url,
                    413,
                    "Payload Too Large",
                    {},
                    io.BytesIO(b"query too large"),
                )
            return response_for("https://api.ohsome.org/child")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = root / "target_bboxes.json"
            write_target_bboxes(
                targets,
                [("a", [0, 0, 5, 5]), ("b", [5, 0, 10, 5])],
            )
            manifest = OhsomeFetcher(
                opener=opener,
                sleeper=lambda _: None,
                request_interval=0,
                max_retries=0,
            ).fetch(
                root / "output",
                snapshot_time="2026-07-17",
                target_bboxes=targets,
                target_batch_size=10,
            )

            root_task = manifest["tasks"][manifest["root_tasks"][0]]
            self.assertEqual(len(root_task["children"]), 2)
            first_singleton = manifest["tasks"][root_task["children"][0]]
            self.assertEqual(len(first_singleton["children"]), 4)
            self.assertEqual(manifest["summary"]["split"], 2)
            self.assertEqual(manifest["summary"]["completed"], 5)
            self.assertEqual(calls[0], "a:0,0,5,5|b:5,0,10,5")
            self.assertEqual(calls[1], "a:0,0,5,5")

    def test_targeted_resume_does_not_refetch_and_rejects_config_change(self) -> None:
        calls = []

        def opener(request, *, timeout):
            calls.append(urllib.parse.parse_qs(request.data.decode())["bboxes"][0])
            return response_for("https://api.ohsome.org/targeted")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = root / "target_bboxes.json"
            write_target_bboxes(
                targets,
                [("west", [-100, 0, -95, 5]), ("east", [100, 0, 105, 5])],
            )
            output = root / "output"
            fetcher = OhsomeFetcher(
                opener=opener, sleeper=lambda _: None, request_interval=0
            )
            first = fetcher.fetch(
                output,
                snapshot_time="2026-07-17",
                target_bboxes=targets,
                max_requests=1,
            )
            self.assertEqual(first["summary"]["completed"], 1)
            self.assertEqual(first["summary"]["pending"], 1)
            targets.unlink()
            saved_targets = output / "inputs" / "target_bboxes.json"
            second = fetcher.fetch(
                output,
                snapshot_time="2026-07-17",
                target_bboxes=saved_targets,
            )
            self.assertEqual(second["summary"]["completed"], 2)
            self.assertEqual(len(calls), 2)
            with self.assertRaisesRegex(ValueError, "configuration does not match"):
                fetcher.fetch(
                    output,
                    snapshot_time="2026-07-17",
                    target_bboxes=saved_targets,
                    target_batch_size=1,
                )

    def test_target_file_rejects_unsafe_duplicate_ids_and_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, entries, message in (
                ("unsafe", [("../bad", [0, 0, 5, 5])], "unsafe target bbox id"),
                (
                    "duplicate",
                    [("same", [0, 0, 5, 5]), ("same", [5, 0, 10, 5])],
                    "duplicate target bbox id",
                ),
            ):
                target_path = root / f"{name}.json"
                write_target_bboxes(target_path, entries)
                with self.assertRaisesRegex(ValueError, message):
                    OhsomeFetcher().fetch(
                        root / f"{name}-output",
                        snapshot_time="2026-07-17",
                        target_bboxes=target_path,
                    )

            valid = root / "valid.json"
            write_target_bboxes(valid, [("safe", [0, 0, 5, 5])])
            with self.assertRaisesRegex(ValueError, "SHA256 does not match"):
                OhsomeFetcher().fetch(
                    root / "hash-output",
                    snapshot_time="2026-07-17",
                    target_bboxes=valid,
                    target_bboxes_sha256="0" * 64,
                )


class OhsomeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(Path(self.temporary_directory.name) / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def _manifest_bundle(
        self,
        tasks: dict[str, dict] | None = None,
    ) -> Path:
        bundle = Path(self.temporary_directory.name) / "bundle"
        shards = bundle / "shards"
        shards.mkdir(parents=True)
        source = FIXTURE_DIRECTORY / "shard-a.geojson"
        destination = shards / "g000_000.geojson"
        shutil.copyfile(source, destination)
        raw = destination.read_bytes()
        completed = {
            "state": "completed",
            "parent": None,
            "file": "shards/g000_000.geojson",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "feature_count": len(json.loads(raw)["features"]),
            "error": None,
        }
        manifest = {"schema_version": 1, "tasks": tasks or {"g000_000": completed}}
        (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return bundle

    def test_offline_directory_import_deduplicates_boundary_overlap(self) -> None:
        result = OhsomeGeoJSONAdapter().import_path(
            self.connection, FIXTURE_DIRECTORY, retrieved_at=RETRIEVED_AT
        )
        self.assertEqual(result.examined_elements, 4)
        self.assertEqual(result.imported_elements, 2)
        self.assertEqual(result.skipped_elements, 2)
        self.assertEqual(result.entities_created, 4)
        self.assertEqual(result.evidence_created, 2)
        self.assertTrue(any("boundary-overlap" in warning for warning in result.warnings))
        stable_keys = {
            row[0] for row in self.connection.execute("SELECT stable_key FROM entities")
        }
        self.assertIn("osm:node/101", stable_keys)
        self.assertIn("osm:way/202", stable_keys)

    def test_standalone_shard_import_remains_supported(self) -> None:
        result = OhsomeGeoJSONAdapter().import_path(
            self.connection,
            FIXTURE_DIRECTORY / "shard-a.geojson",
            retrieved_at=RETRIEVED_AT,
        )

        self.assertEqual(result.examined_elements, 2)
        self.assertEqual(result.imported_elements, 2)

    def test_import_preserves_exact_urls_hashes_and_snapshot_metadata(self) -> None:
        OhsomeGeoJSONAdapter().import_path(
            self.connection, FIXTURE_DIRECTORY, retrieved_at=RETRIEVED_AT
        )
        row = self.connection.execute(
            "SELECT source_url, license, attribution, content_hash, metadata_json "
            "FROM evidence WHERE source_url = ?",
            ("https://www.openstreetmap.org/node/101",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["license"], "ODbL-1.0")
        self.assertEqual(row["attribution"], "© OpenStreetMap contributors")
        self.assertEqual(len(row["content_hash"]), 64)
        metadata = json.loads(row["metadata_json"])
        self.assertIn("api.ohsome.org/v1/elements/geometry", metadata["api_request_url"])
        self.assertEqual(metadata["last_edit_at"], "2026-06-01T12:00:00Z")
        self.assertEqual(metadata["snapshot_at"], "2026-07-17T00:00:00Z")
        self.assertEqual(metadata["osm_version"], 3)
        self.assertEqual(len(metadata["input_sha256"]), 64)

    def test_same_offline_import_is_idempotent(self) -> None:
        adapter = OhsomeGeoJSONAdapter()
        first = adapter.import_path(self.connection, FIXTURE_DIRECTORY, retrieved_at=RETRIEVED_AT)
        second = adapter.import_path(self.connection, FIXTURE_DIRECTORY, retrieved_at=RETRIEVED_AT)
        self.assertEqual(first.entities_created, 4)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)

    def test_manifest_import_rejects_partial_tasks_by_default(self) -> None:
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_001"] = {
            "state": "pending",
            "parent": None,
            "file": None,
            "sha256": None,
            "feature_count": None,
            "error": "request interrupted",
        }
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, r"pending=1.*errors=1"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_manifest_partial_import_is_explicit_and_warns_with_counts(self) -> None:
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_001"] = {
            "state": "failed",
            "parent": None,
            "file": None,
            "sha256": None,
            "feature_count": None,
            "error": "permanent failure",
        }
        manifest_path.write_text(json.dumps(manifest))

        result = OhsomeGeoJSONAdapter().import_path(
            self.connection,
            bundle,
            retrieved_at=RETRIEVED_AT,
            allow_partial=True,
        )

        self.assertEqual(result.examined_elements, 2)
        self.assertTrue(
            any(
                "completed=1" in warning
                and "failed=1" in warning
                and "errors=1" in warning
                for warning in result.warnings
            )
        )

    def test_manifest_import_rejects_path_traversal(self) -> None:
        bundle = self._manifest_bundle()
        outside = Path(self.temporary_directory.name) / "outside.geojson"
        shutil.copyfile(FIXTURE_DIRECTORY / "shard-a.geojson", outside)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_000"]["file"] = "../outside.geojson"
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, "escapes input directory"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_manifest_import_rejects_symlink_escape(self) -> None:
        bundle = self._manifest_bundle()
        outside = Path(self.temporary_directory.name) / "outside.geojson"
        shutil.copyfile(FIXTURE_DIRECTORY / "shard-a.geojson", outside)
        shard = bundle / "shards" / "g000_000.geojson"
        shard.unlink()
        shard.symlink_to(outside)

        with self.assertRaisesRegex(ValueError, "escapes input directory"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_manifest_import_rejects_hash_mismatch(self) -> None:
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_000"]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, "SHA256 does not match"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_manifest_import_rejects_feature_count_mismatch(self) -> None:
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_000"]["feature_count"] = 999
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, "feature_count does not match"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_manifest_import_rejects_split_with_incomplete_descendants(self) -> None:
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["g000_001"] = {
            "state": "split",
            "parent": None,
            "file": None,
            "sha256": None,
            "feature_count": None,
            "error": None,
        }
        manifest["tasks"]["g000_001q0"] = {
            "state": "pending",
            "parent": "g000_001",
            "file": None,
            "sha256": None,
            "feature_count": None,
            "error": None,
        }
        manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, r"pending=1.*incomplete_split=1"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

    def test_targeted_two_child_split_is_incomplete_then_importable_after_resume(self) -> None:
        calls = 0

        def opener(request, *, timeout):
            nonlocal calls
            calls += 1
            parameter = urllib.parse.parse_qs(request.data.decode())["bboxes"][0]
            if calls == 1:
                self.assertIn("|", parameter)
                raise urllib.error.HTTPError(
                    request.full_url,
                    413,
                    "Payload Too Large",
                    {},
                    io.BytesIO(b"query too large"),
                )
            return response_for("https://api.ohsome.org/targeted")

        root = Path(self.temporary_directory.name)
        target_path = root / "target_bboxes.json"
        write_target_bboxes(
            target_path,
            [("a", [0, 0, 5, 5]), ("b", [5, 0, 10, 5])],
        )
        output = root / "targeted-bundle"
        fetcher = OhsomeFetcher(
            opener=opener,
            sleeper=lambda _: None,
            request_interval=0,
            max_retries=0,
        )
        partial = fetcher.fetch(
            output,
            snapshot_time="2026-07-17",
            target_bboxes=target_path,
            max_requests=2,
        )
        self.assertEqual(partial["summary"]["split"], 1)
        self.assertEqual(partial["summary"]["completed"], 1)
        self.assertEqual(partial["summary"]["pending"], 1)
        with self.assertRaisesRegex(ValueError, r"pending=1.*incomplete_split=1"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, output, retrieved_at=RETRIEVED_AT
            )

        complete = fetcher.fetch(
            output,
            snapshot_time="2026-07-17",
            target_bboxes=target_path,
        )
        self.assertEqual(complete["summary"]["completed"], 2)
        result = OhsomeGeoJSONAdapter().import_path(
            self.connection, output, retrieved_at=RETRIEVED_AT
        )
        self.assertEqual(result.examined_elements, 0)

    def test_manifest_rejects_undeclared_children_and_cycles(self) -> None:
        pending = {
            "state": "pending",
            "parent": None,
            "file": None,
            "sha256": None,
            "feature_count": None,
            "error": None,
        }
        bundle = self._manifest_bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["tasks"]["parent"] = {
            **pending,
            "state": "split",
            "children": ["child0", "child1"],
        }
        for child_id in ("child0", "child1", "child2"):
            manifest["tasks"][child_id] = {**pending, "parent": "parent"}
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "undeclared or mis-parented"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )

        bundle = Path(self.temporary_directory.name) / "cycle-bundle"
        shards = bundle / "shards"
        shards.mkdir(parents=True)
        cyclic_tasks = {
            "a": {
                **pending,
                "parent": "b",
                "state": "split",
                "children": ["b", "a_leaf"],
            },
            "b": {
                **pending,
                "parent": "a",
                "state": "split",
                "children": ["a", "b_leaf"],
            },
            "a_leaf": {**pending, "parent": "a"},
            "b_leaf": {**pending, "parent": "b"},
        }
        (bundle / "manifest.json").write_text(
            json.dumps({"schema_version": 2, "tasks": cyclic_tasks})
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            OhsomeGeoJSONAdapter().import_path(
                self.connection, bundle, retrieved_at=RETRIEVED_AT
            )


if __name__ == "__main__":
    unittest.main()
