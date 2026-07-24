from __future__ import annotations

import ast
from hashlib import sha256
import json
import multiprocessing
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib

import datacenter_atlas.satellite_change_batch as change_batch_module
from datacenter_atlas.satellite_batch import BatchConfig, execute_satellite_queue
from datacenter_atlas.satellite_catalog import (
    CatalogQuery,
    Provider,
    build_pair_manifest,
    manifest_json,
)
from datacenter_atlas.satellite_change import (
    ALGORITHM_VERSION,
    EARTH_SEARCH_ASSET_HOST,
    EARTH_SEARCH_ASSET_PATH_PREFIX,
    REPORT_SCHEMA_VERSION,
    item_summary,
    report_source,
    select_feature,
    validate_asset_href,
)
from datacenter_atlas.satellite_change_batch import (
    GEOJSON_COLLECTION_PROPERTIES,
    REPORT_CLASSIFICATION,
    ChangeBatchConfig,
    SatelliteChangeBatchError,
    execute_satellite_change_batch,
    validate_satellite_change_batch,
)
from datacenter_atlas.satellite_queue import (
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUEUE_FILENAME,
    QueueConfig,
    build_queue_bundle,
)
from scripts.sentinel_change import _write_proposals


RUN_AT = "2026-07-18T23:30:00Z"
CATALOG_AT = "2026-07-18T23:00:00Z"


def _feature(entity_id: str) -> dict:
    return {
        "type": "Feature",
        "id": entity_id,
        "geometry": None,
        "properties": {
            "entity_id": entity_id,
            "entity_kind": "facility",
            "stable_key": f"fixture:{entity_id}",
            "name": f"Site {entity_id}",
            "latitude": 38.9,
            "longitude": -77.0,
            "status": "under_construction",
            "status_as_of": "2026-07-01",
            "snapshot_evidence_id": f"snapshot-{entity_id}",
            "status_evidence_id": f"status-{entity_id}",
            "source_family": "fixture",
            "source_url": f"https://example.test/{entity_id}",
            "source_license": "CC0-1.0",
            "country": "United States",
            "country_iso_a2": "US",
            "country_iso_a3": "USA",
        },
    }


def _queue_bundle(
    path: Path, count: int = 2, *, provider: Provider | str = Provider.EARTH_SEARCH
) -> list[str]:
    atlas = (
        json.dumps(
            {
                "type": "FeatureCollection",
                "atlas_as_of": "2026-07-18",
                "atlas_recorded_at": "2026-07-18T20:00:00Z",
                "attribution": ["Fixture attribution"],
                "features": [_feature(f"entity-{index}") for index in range(count)],
            }
        )
        + "\n"
    ).encode()
    bundle = build_queue_bundle(
        atlas,
        source_name="atlas.geojson",
        generated_at="2026-07-18T21:00:00Z",
        config=QueueConfig(
            baseline_target="2024-06-15",
            current_target="2026-06-15",
            provider=provider,
            query_window_days=30,
            aoi_half_side_km=2,
        ),
    )
    path.mkdir()
    (path / QUEUE_FILENAME).write_bytes(bundle.queue_bytes)
    (path / MANIFEST_FILENAME).write_bytes(bundle.manifest_bytes)
    (path / MANIFEST_HASH_FILENAME).write_bytes(bundle.manifest_hash_bytes)
    return [
        json.loads(line)["queue_id"]
        for line in bundle.queue_bytes.decode("utf-8").splitlines()
    ]


def _pairs(arguments: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        flag = arguments[index]
        if flag.startswith("--") and "=" in flag:
            name, value = flag.split("=", 1)
            parsed[name] = value
            index += 1
        else:
            parsed[flag] = arguments[index + 1]
            index += 2
    return parsed


def _stac_item(item_id: str, timestamp: str, bbox: tuple[float, ...]) -> dict:
    acquired = timestamp[:7].replace("-", "/")
    assets = {
        band: {
            "href": (
                f"https://{EARTH_SEARCH_ASSET_HOST}"
                f"{EARTH_SEARCH_ASSET_PATH_PREFIX}18/S/UJ/{acquired}/{item_id}/{band}.tif"
            ),
            "raster:bands": [{"scale": 0.0001, "offset": -0.1}],
        }
        for band in ("blue", "green", "red", "nir", "swir16")
    }
    assets["scl"] = {
        "href": (
            f"https://{EARTH_SEARCH_ASSET_HOST}"
            f"{EARTH_SEARCH_ASSET_PATH_PREFIX}18/S/UJ/{acquired}/{item_id}/scl.tif"
        )
    }
    return {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "bbox": list(bbox),
        "properties": {
            "datetime": timestamp,
            "eo:cloud_cover": 1,
            "mgrs:utm_zone": 18,
            "mgrs:latitude_band": "S",
            "mgrs:grid_square": "UJ",
        },
        "assets": assets,
    }


class _CatalogRunner:
    def __init__(self, *, baseline_red_href: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.baseline_red_href = baseline_red_href

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        arguments = _pairs(command[2:])
        output = Path(arguments["--output-dir"])
        output.mkdir(parents=True)
        bbox = tuple(float(value) for value in arguments["--bbox"].split(","))
        baseline = _stac_item(
            f"baseline-{output.parent.name}",
            f"{arguments['--baseline-target']}T12:00:00Z",
            bbox,
        )
        if self.baseline_red_href is not None:
            baseline["assets"]["red"]["href"] = self.baseline_red_href
        current = _stac_item(
            f"current-{output.parent.name}",
            f"{arguments['--current-target']}T12:00:00Z",
            bbox,
        )
        baseline_raw = json.dumps(
            {"type": "FeatureCollection", "features": [baseline]}, sort_keys=True
        ).encode()
        current_raw = json.dumps(
            {"type": "FeatureCollection", "features": [current]}, sort_keys=True
        ).encode()
        provider = Provider(arguments["--provider"])
        baseline_query = CatalogQuery(
            bbox,
            arguments["--baseline-start"],
            arguments["--baseline-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        current_query = CatalogQuery(
            bbox,
            arguments["--current-start"],
            arguments["--current-end"],
            float(arguments["--max-cloud-cover"]),
            int(arguments["--limit"]),
        )
        manifest = build_pair_manifest(
            provider,
            baseline_query,
            baseline_raw,
            current_query,
            current_raw,
            baseline_date=arguments["--baseline-target"],
            current_date=arguments["--current-target"],
            retrieved_at=CATALOG_AT,
            temporal_window_days=int(arguments["--temporal-window-days"]),
        )
        (output / "baseline-response.json").write_bytes(baseline_raw)
        (output / "current-response.json").write_bytes(current_raw)
        (output / "manifest.json").write_text(manifest_json(manifest), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "ok", "")


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def _record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}


class _ChangeRunner:
    def __init__(self, *, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if self.returncode:
            return subprocess.CompletedProcess(command, self.returncode, "", "fixture failure")
        arguments = _pairs(command[2:])
        output = Path(arguments["--output-dir"])
        output.mkdir(parents=True)
        baseline_document = json.loads(Path(arguments["--baseline-stac"]).read_text())
        current_document = json.loads(Path(arguments["--current-stac"]).read_text())
        baseline = select_feature(baseline_document, arguments["--baseline-id"])
        current = select_feature(current_document, arguments["--current-id"])
        (output / "before.png").write_bytes(_png(1, 1, (10, 20, 30)))
        (output / "after.png").write_bytes(_png(1, 1, (20, 30, 40)))
        (output / "change-overlay.png").write_bytes(_png(1, 1, (200, 30, 40)))
        (output / "comparison.png").write_bytes(_png(3, 1, (30, 40, 50)))
        areas = (5_000.1, 5_000.2)
        features = []
        for index, area in enumerate(areas, start=1):
            longitude = -77.0 + index / 100
            ring = [
                [longitude, 38.9],
                [longitude + 0.001, 38.9],
                [longitude + 0.001, 38.901],
                [longitude, 38.901],
                [longitude, 38.9],
            ]
            features.append(
                {
                    "type": "Feature",
                    "id": f"change-proposal-{index}",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {
                        "class": "large_spectral_change_candidate",
                        "area_m2": area,
                        "identity_claim": False,
                        "lifecycle_claim": False,
                        "operating_status_claim": False,
                        "power_claim": False,
                        "energy_claim": False,
                        "operator_claim": False,
                        "data_centre_type_claim": False,
                        "it_capacity_claim": False,
                        "pue_claim": False,
                        "workload_claim": False,
                        "review_required": True,
                    },
                }
            )
        proposals = {
            "type": "FeatureCollection",
            "features": features,
            "properties": GEOJSON_COLLECTION_PROPERTIES,
        }
        (output / "change-proposals.geojson").write_text(
            json.dumps(proposals, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        outputs = {
            name: _record(output / name)
            for name in (
                "after.png",
                "before.png",
                "change-overlay.png",
                "change-proposals.geojson",
                "comparison.png",
            )
        }
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "entity": {
                "id": arguments["--entity-id"],
                "name": arguments["--entity-name"],
            },
            "aoi_bbox_wgs84": [
                float(value) for value in arguments["--bbox"].split(",")
            ],
            "baseline": item_summary(baseline),
            "current": item_summary(current),
            "source": report_source(baseline, current),
            "classification": REPORT_CLASSIFICATION,
            "grid": {
                "crs": "EPSG:32618",
                "width": 1,
                "height": 1,
                "pixel_area_m2": 100.0,
                "clear_scl_classes": [4, 5, 6, 7],
            },
            "thresholds": {
                "minimum_absolute_reflectance_change": 0.08,
                "adaptive_quantile": 0.9,
                "adaptive_absolute_reflectance_change": 0.09,
                "applied_absolute_reflectance_change": 0.09,
                "ndvi_loss": -0.12,
                "ndbi_gain": 0.12,
                "absolute_brightness_change": 0.1,
            },
            "radiometry": {
                "reflectance": "STAC raster scale and offset applied per scene and band",
                "normalized_index_negative_reflectance_policy": "clip_to_zero",
            },
            "metrics": {
                "valid_pixel_fraction": 1.0,
                "proposal_pixel_fraction_of_valid": 0.5,
                "mean_baseline_ndvi": 0.1,
                "mean_current_ndvi": 0.2,
                "mean_ndvi_change": 0.1,
                "mean_ndbi_change": 0.1,
                "mean_absolute_reflectance_change": 0.1,
                "proposal_component_count": len(features),
                "proposal_area_m2_after_component_filter": round(sum(areas), 1),
            },
            "outputs": outputs,
        }
        (output / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return subprocess.CompletedProcess(command, 0, "ok", "")


def _catalog_fixture(
    root: Path,
    count: int = 2,
    *,
    catalog_runner: _CatalogRunner | None = None,
) -> tuple[Path, Path, list[str]]:
    queue = root / "queue"
    catalog = root / "catalog-run"
    queue_ids = _queue_bundle(queue, count)
    execute_satellite_queue(
        queue,
        catalog,
        config=BatchConfig(
            priority_tiers=("active_construction",),
            minimum_interval_seconds=0.1,
        ),
        max_jobs=count,
        max_http_attempts=count * 2,
        command_runner=catalog_runner or _CatalogRunner(),
        sleep=lambda _: None,
        timestamp=lambda: CATALOG_AT,
    )
    return queue, catalog, queue_ids


class SatelliteChangeBatchTests(unittest.TestCase):
    def test_explicit_selection_runs_in_queue_order_caps_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            first_runner = _ChangeRunner()
            first = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=[queue_ids[1], queue_ids[0]],
                max_jobs=1,
                command_runner=first_runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(first["selection"]["selected_queue_ids"], queue_ids)
            self.assertEqual(first["summary"]["jobs_selected"], 2)
            self.assertEqual(first["summary"]["jobs_completed"], 1)
            self.assertTrue(first["runs"][-1]["budget_exhausted"])
            self.assertEqual(len(first_runner.calls), 1)
            command_text = " ".join(first_runner.calls[0])
            self.assertNotIn("{selected_ids.", command_text)
            self.assertIn("/.change.staging", command_text)
            self.assertFalse(any(output.rglob("*.staging")))
            for field in (
                "imagery_identity_inference",
                "imagery_operator_inference",
                "imagery_lifecycle_inference",
                "imagery_operating_status_inference",
                "imagery_data_centre_type_inference",
                "imagery_it_capacity_inference",
                "imagery_pue_inference",
                "imagery_workload_inference",
                "imagery_power_inference",
                "imagery_energy_inference",
            ):
                self.assertIs(first["scope"][field], False)
            processor = first["processor"]
            self.assertIn(
                "datacenter_atlas/satellite_change_batch.py", processor["files"]
            )
            self.assertEqual(
                set(processor["files"]),
                {
                    "datacenter_atlas/satellite_change_batch.py",
                    "datacenter_atlas/satellite_change.py",
                    "datacenter_atlas/satellite_batch.py",
                    "datacenter_atlas/satellite_queue.py",
                    "datacenter_atlas/satellite_catalog.py",
                    "datacenter_atlas/models.py",
                    "scripts/sentinel_change.py",
                },
            )
            self.assertEqual(
                set(processor["runtime"]["packages"]),
                {"numpy", "PIL", "rasterio"},
            )
            self.assertEqual(
                processor["runtime"]["python"]["version"],
                __import__("platform").python_version(),
            )
            self.assertEqual(
                processor["runtime"]["platform"]["system"],
                __import__("platform").system(),
            )
            self.assertIn("runtime_version", processor["runtime"]["zlib"])
            self.assertEqual(
                set(processor["runtime"]["geospatial_runtime"]),
                {"gdal", "proj"},
            )

            second_runner = _ChangeRunner()
            resumed = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=1,
                command_runner=second_runner,
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(resumed["summary"]["jobs_completed"], 2)
            self.assertEqual(len(second_runner.calls), 1)
            self.assertEqual(
                validate_satellite_change_batch(queue, [catalog], output, config=config),
                resumed,
            )

    def test_asset_href_policy_and_year_specific_legal_attribution(self) -> None:
        bbox = (-77.02, 38.88, -76.98, 38.92)
        baseline = _stac_item("baseline", "2024-06-15T12:00:00Z", bbox)
        current = _stac_item("current", "2026-06-15T12:00:00Z", bbox)
        valid = baseline["assets"]["red"]["href"]
        validate_asset_href(valid)
        for unsafe in (
            "file:///tmp/red.tif",
            f"/vsicurl/https://{EARTH_SEARCH_ASSET_HOST}{EARTH_SEARCH_ASSET_PATH_PREFIX}red.tif",
            valid.replace("https://", "http://"),
            valid.replace("https://", "https://user:secret@"),
            valid.replace(EARTH_SEARCH_ASSET_HOST, "localhost"),
            valid.replace(EARTH_SEARCH_ASSET_HOST, "127.0.0.1"),
            valid.replace(EARTH_SEARCH_ASSET_HOST, "example.test"),
            valid.replace(EARTH_SEARCH_ASSET_HOST, f"{EARTH_SEARCH_ASSET_HOST}:8443"),
            valid + "?token=secret",
            valid + "#fragment",
            valid.replace(EARTH_SEARCH_ASSET_PATH_PREFIX, "/other-prefix/"),
            valid.replace("/baseline/", "/../"),
            valid.replace("baseline", "%2e%2e"),
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                validate_asset_href(unsafe)

        source = report_source(baseline, current)
        self.assertEqual(
            source["attribution_notices"],
            [
                "Contains modified Copernicus Sentinel data 2024",
                "Contains modified Copernicus Sentinel data 2026",
            ],
        )
        self.assertEqual(
            source["license_url"],
            "https://sentinels.copernicus.eu/documents/247904/690755/"
            "Sentinel_Data_Legal_Notice",
        )
        same_year = _stac_item("current-same-year", "2024-08-01T12:00:00Z", bbox)
        self.assertEqual(
            report_source(baseline, same_year)["attribution_notices"],
            ["Contains modified Copernicus Sentinel data 2024"],
        )

    def test_unsafe_selected_asset_is_rejected_before_change_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(
                root,
                1,
                catalog_runner=_CatalogRunner(baseline_red_href="file:///tmp/red.tif"),
            )
            output = root / "change-run"
            runner = _ChangeRunner()
            with self.assertRaisesRegex(SatelliteChangeBatchError, "unsafe href"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=ChangeBatchConfig(minimum_interval_seconds=0),
                    include_queue_ids=queue_ids,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])
            self.assertFalse((output / "batch-manifest.json").exists())

    def test_report_attribution_is_reconstructed_from_selected_scene_years(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"

            class WrongAttributionRunner(_ChangeRunner):
                def __call__(
                    self, command: list[str], **kwargs: object
                ) -> subprocess.CompletedProcess[str]:
                    completed = super().__call__(command, **kwargs)
                    report_path = Path(_pairs(command[2:])["--output-dir"]) / "report.json"
                    report = json.loads(report_path.read_text())
                    report["source"]["attribution_notices"] = [
                        "Contains modified Copernicus Sentinel data 2026"
                    ]
                    report_path.write_text(
                        json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return completed

            manifest = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=ChangeBatchConfig(minimum_interval_seconds=0),
                include_queue_ids=queue_ids,
                command_runner=WrongAttributionRunner(),
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(manifest["jobs"].values()))
            self.assertEqual(task["state"], "failed")
            self.assertIn("report source changed", task["failures"][-1]["error"])
            self.assertFalse(any(output.glob("jobs/*/change")))

    def test_non_earth_search_queue_is_rejected_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            _queue_bundle(queue, 1, provider=Provider.COPERNICUS)
            output = root / "change-run"
            with self.assertRaisesRegex(SatelliteChangeBatchError, "earth-search-v1"):
                execute_satellite_change_batch(
                    queue,
                    [root / "catalog-not-needed"],
                    output,
                    include_queue_ids=["not-reached"],
                )
            self.assertFalse(output.exists())

    def test_exclusive_directory_lock_blocks_a_concurrent_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            context = multiprocessing.get_context("fork")
            command_started = context.Event()
            release_command = context.Event()

            def first_process() -> None:
                class BlockingRunner(_ChangeRunner):
                    def __call__(
                        self, command: list[str], **kwargs: object
                    ) -> subprocess.CompletedProcess[str]:
                        command_started.set()
                        if not release_command.wait(20):
                            raise RuntimeError("test did not release blocked command")
                        return super().__call__(command, **kwargs)

                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    include_queue_ids=queue_ids,
                    command_runner=BlockingRunner(),
                    timestamp=lambda: RUN_AT,
                )

            process = context.Process(target=first_process)
            process.start()
            try:
                self.assertTrue(command_started.wait(10), "first executor never started")
                checkpoint = output / "batch-manifest.json"
                before = checkpoint.read_bytes()
                second_runner = _ChangeRunner()
                with self.assertRaisesRegex(SatelliteChangeBatchError, "locked"):
                    execute_satellite_change_batch(
                        queue,
                        [catalog],
                        output,
                        config=config,
                        command_runner=second_runner,
                        timestamp=lambda: RUN_AT,
                    )
                with self.assertRaisesRegex(SatelliteChangeBatchError, "locked"):
                    validate_satellite_change_batch(queue, [catalog], output, config=config)
                self.assertEqual(second_runner.calls, [])
                self.assertEqual(checkpoint.read_bytes(), before)
            finally:
                release_command.set()
                process.join(20)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            self.assertEqual(process.exitcode, 0)
            validate_satellite_change_batch(queue, [catalog], output, config=config)

    def test_first_run_requires_selection_and_exclusion_is_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root)
            with self.assertRaisesRegex(SatelliteChangeBatchError, "explicit"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    root / "unsafe-default",
                    config=ChangeBatchConfig(minimum_interval_seconds=0),
                    command_runner=_ChangeRunner(),
                    timestamp=lambda: RUN_AT,
                )
            queue_manifest_hash = sha256((queue / MANIFEST_FILENAME).read_bytes()).hexdigest()
            exclusion = root / "reviewed-exclusions.json"
            exclusion_document = {
                "schema_version": 1,
                "purpose": "satellite_change_batch_exclusions",
                "queue_manifest_sha256": queue_manifest_hash,
                "queue_ids": [queue_ids[0]],
            }
            exclusion.write_text(
                json.dumps(exclusion_document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            output = root / "change-run"
            manifest = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=ChangeBatchConfig(minimum_interval_seconds=0),
                exclusion_file=exclusion,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(manifest["selection"]["selected_queue_ids"], [queue_ids[1]])
            self.assertEqual(
                manifest["summary"]["catalog_completed_jobs_excluded"], 1
            )
            self.assertEqual(
                manifest["selection"]["selection_source"]["sha256"],
                sha256(exclusion.read_bytes()).hexdigest(),
            )
            exclusion_document["queue_ids"] = [queue_ids[1]]
            exclusion.write_text(
                json.dumps(exclusion_document, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "selection"):
                validate_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    exclusion_file=exclusion,
                )

    def test_exclusion_provenance_is_required_and_strictly_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root)
            exclusion = root / "reviewed-exclusions.json"
            exclusion.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "purpose": "satellite_change_batch_exclusions",
                        "queue_manifest_sha256": sha256(
                            (queue / MANIFEST_FILENAME).read_bytes()
                        ).hexdigest(),
                        "queue_ids": [queue_ids[0]],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            output = root / "change-run"
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=ChangeBatchConfig(minimum_interval_seconds=0),
                include_queue_ids=[queue_ids[1]],
                exclusion_file=exclusion,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            checkpoint = output / "batch-manifest.json"
            valid = json.loads(checkpoint.read_text())

            def assert_rejected(mutator) -> None:
                document = json.loads(json.dumps(valid))
                mutator(document["selection"])
                checkpoint.write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(SatelliteChangeBatchError, "exclusion source"):
                    validate_satellite_change_batch(queue, [catalog], output)

            assert_rejected(lambda selection: selection.__setitem__("selection_source", None))
            assert_rejected(
                lambda selection: selection["selection_source"].__setitem__(
                    "file", "../reviewed-exclusions.json"
                )
            )
            assert_rejected(
                lambda selection: selection["selection_source"].__setitem__("bytes", 0)
            )
            assert_rejected(
                lambda selection: selection["selection_source"].__setitem__(
                    "sha256", "A" * 64
                )
            )

    def test_task_failures_and_run_outcome_counters_are_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(
                minimum_interval_seconds=0, max_job_attempts=2
            )
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                command_runner=_ChangeRunner(returncode=1),
                timestamp=lambda: RUN_AT,
            )
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            checkpoint = output / "batch-manifest.json"
            valid = json.loads(checkpoint.read_text())
            task = next(iter(valid["jobs"].values()))
            self.assertEqual(task["attempts"], 2)
            self.assertEqual([failure["attempt"] for failure in task["failures"]], [1])

            missing_failure = json.loads(json.dumps(valid))
            next(iter(missing_failure["jobs"].values()))["failures"] = []
            checkpoint.write_text(
                json.dumps(missing_failure, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "reconcile"):
                validate_satellite_change_batch(queue, [catalog], output)

            missing_counter = json.loads(json.dumps(valid))
            missing_counter["runs"][0]["jobs_failed"] = 0
            checkpoint.write_text(
                json.dumps(missing_counter, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "reconcile"):
                validate_satellite_change_batch(queue, [catalog], output)

            failed_to_interrupted = json.loads(json.dumps(valid))
            failed_to_interrupted["runs"][0]["jobs_failed"] = 0
            failed_to_interrupted["runs"][0]["jobs_interrupted"] = 1
            checkpoint.write_text(
                json.dumps(failed_to_interrupted, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "recovery outcome"):
                validate_satellite_change_batch(queue, [catalog], output)

            completed_to_recovered = json.loads(json.dumps(valid))
            completed_to_recovered["runs"][1]["jobs_completed"] = 0
            completed_to_recovered["runs"][1]["jobs_recovered_after_publish"] = 1
            checkpoint.write_text(
                json.dumps(completed_to_recovered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "recovery outcome"):
                validate_satellite_change_batch(queue, [catalog], output)

    def test_completed_output_tamper_stops_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            before = next(output.glob("jobs/*/change/before.png"))
            before.write_bytes(before.read_bytes() + b"tamper")
            runner = _ChangeRunner()
            with self.assertRaisesRegex(SatelliteChangeBatchError, "PNG|artifact"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])

    def test_in_wgs84_but_out_of_aoi_proposal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"

            class OutOfAoiRunner(_ChangeRunner):
                def __call__(
                    self, command: list[str], **kwargs: object
                ) -> subprocess.CompletedProcess[str]:
                    completed = super().__call__(command, **kwargs)
                    change = Path(_pairs(command[2:])["--output-dir"])
                    proposals_path = change / "change-proposals.geojson"
                    proposals = json.loads(proposals_path.read_text())
                    proposals["features"][0]["geometry"]["coordinates"] = [
                        [[0.0, 0.0], [0.001, 0.0], [0.001, 0.001], [0.0, 0.001], [0.0, 0.0]]
                    ]
                    proposals_path.write_text(
                        json.dumps(proposals, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    report_path = change / "report.json"
                    report = json.loads(report_path.read_text())
                    report["outputs"]["change-proposals.geojson"] = _record(
                        proposals_path
                    )
                    report_path.write_text(
                        json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    return completed

            manifest = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=ChangeBatchConfig(minimum_interval_seconds=0),
                include_queue_ids=queue_ids,
                command_runner=OutOfAoiRunner(),
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(manifest["jobs"].values()))
            self.assertEqual(task["state"], "failed")
            self.assertEqual(task["failures"][-1]["kind"], "output_validation")
            self.assertIn("outside the queue AOI", task["failures"][-1]["error"])
            self.assertFalse(any(output.glob("jobs/*/change")))

    def test_config_catalog_and_template_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "configuration"):
                validate_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=ChangeBatchConfig(
                        timeout_seconds=900, minimum_interval_seconds=0
                    ),
                )

            checkpoint = output / "batch-manifest.json"
            document = json.loads(checkpoint.read_text())
            task = next(iter(document["jobs"].values()))
            entity_name_index = task["change_job"]["arguments"].index("--entity-name") + 1
            task["change_job"]["arguments"][entity_name_index] = "drift"
            checkpoint.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SatelliteChangeBatchError, "immutable"):
                validate_satellite_change_batch(queue, [catalog], output)

            # Restore the valid checkpoint, then prove exact catalog bytes are
            # revalidated before any further command can run.
            task["change_job"]["arguments"][entity_name_index] = task["entity"]["name"]
            checkpoint.write_text(
                json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            baseline = next(catalog.glob("jobs/*/catalog/baseline-response.json"))
            baseline.write_bytes(baseline.read_bytes() + b"\n")
            runner = _ChangeRunner()
            with self.assertRaisesRegex(SatelliteChangeBatchError, "offline validation"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])

    def test_mid_command_catalog_tamper_prevents_publication_and_clears_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"

            class CatalogTamperRunner(_ChangeRunner):
                def __call__(
                    self, command: list[str], **kwargs: object
                ) -> subprocess.CompletedProcess[str]:
                    arguments = _pairs(command[2:])
                    baseline = Path(arguments["--baseline-stac"])
                    baseline.write_bytes(baseline.read_bytes() + b"\n")
                    return super().__call__(command, **kwargs)

            manifest = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=ChangeBatchConfig(minimum_interval_seconds=0),
                include_queue_ids=queue_ids,
                command_runner=CatalogTamperRunner(),
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(manifest["jobs"].values()))
            self.assertEqual(task["state"], "failed")
            self.assertEqual(task["failures"][-1]["kind"], "output_validation")
            self.assertIn("catalog artifact changed", task["failures"][-1]["error"])
            self.assertFalse(any(output.glob("jobs/*/change")))
            self.assertFalse(any(output.rglob("*.staging")))

    def test_mid_command_processor_runtime_drift_prevents_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            package_root = Path(change_batch_module.__file__).resolve().parents[1]
            actual_processor = change_batch_module._processor_lineage(package_root)
            changed_processor = json.loads(json.dumps(actual_processor))
            changed_processor["runtime"]["python"]["version"] = "999.0-drift"
            with patch.object(
                change_batch_module,
                "_processor_lineage",
                side_effect=[actual_processor, actual_processor, changed_processor],
            ):
                manifest = execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=ChangeBatchConfig(minimum_interval_seconds=0),
                    include_queue_ids=queue_ids,
                    command_runner=_ChangeRunner(),
                    timestamp=lambda: RUN_AT,
                )
            task = next(iter(manifest["jobs"].values()))
            self.assertEqual(task["state"], "failed")
            self.assertEqual(task["failures"][-1]["kind"], "output_validation")
            self.assertIn("changed during the job", task["failures"][-1]["error"])
            self.assertFalse(any(output.glob("jobs/*/change")))
            self.assertFalse(any(output.rglob("*.staging")))

    def test_runtime_drift_is_rejected_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                command_runner=_ChangeRunner(returncode=1),
                timestamp=lambda: RUN_AT,
            )
            actual_runtime = change_batch_module._runtime_lineage()
            changed_runtime = json.loads(json.dumps(actual_runtime))
            changed_runtime["packages"]["numpy"]["version"] = "999.0-drift"
            runner = _ChangeRunner()
            with patch.object(
                change_batch_module, "_runtime_lineage", return_value=changed_runtime
            ), self.assertRaisesRegex(SatelliteChangeBatchError, "processor"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])

    def test_transitive_processor_dependency_drift_is_rejected_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)
            execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                command_runner=_ChangeRunner(returncode=1),
                timestamp=lambda: RUN_AT,
            )
            package_root = Path(change_batch_module.__file__).resolve().parents[1]
            changed_processor = change_batch_module._processor_lineage(package_root)
            changed_processor = json.loads(json.dumps(changed_processor))
            changed_processor["files"]["datacenter_atlas/models.py"]["sha256"] = "0" * 64
            runner = _ChangeRunner()
            with patch.object(
                change_batch_module,
                "_processor_lineage",
                return_value=changed_processor,
            ), self.assertRaisesRegex(SatelliteChangeBatchError, "processor"):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])

    def test_missing_optional_runtime_versions_are_explicit(self) -> None:
        with patch.object(
            change_batch_module,
            "distribution_version",
            side_effect=change_batch_module.PackageNotFoundError,
        ):
            runtime = change_batch_module._runtime_lineage()
        self.assertFalse(runtime["required_packages_available"])
        self.assertTrue(
            all(package["version"] is None for package in runtime["packages"].values())
        )
        self.assertEqual(runtime["geospatial_runtime"], {"gdal": None, "proj": None})

    def test_interruption_is_recorded_and_partial_stage_is_not_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)

            def interrupt(command: list[str], **_: object) -> None:
                stage = Path(_pairs(command[2:])["--output-dir"])
                stage.mkdir(parents=True)
                (stage / "partial.tmp").write_text("partial", encoding="utf-8")
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    include_queue_ids=queue_ids,
                    command_runner=interrupt,
                    timestamp=lambda: RUN_AT,
                )
            interrupted = json.loads((output / "batch-manifest.json").read_text())
            self.assertEqual(next(iter(interrupted["jobs"].values()))["state"], "running")
            resumed = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(resumed["jobs"].values()))
            self.assertEqual(task["state"], "completed")
            self.assertEqual(task["attempts"], 2)
            self.assertEqual(task["failures"][0]["kind"], "interrupted")
            self.assertEqual(resumed["runs"][0]["state"], "interrupted")
            self.assertEqual(resumed["runs"][0]["jobs_interrupted"], 1)

    def test_atomic_publish_is_recovered_without_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0)

            class PublishThenInterrupt(_ChangeRunner):
                def __call__(self, command: list[str], **kwargs: object) -> None:
                    super().__call__(command, **kwargs)
                    stage = Path(_pairs(command[2:])["--output-dir"])
                    stage.replace(stage.with_name("change"))
                    raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    include_queue_ids=queue_ids,
                    command_runner=PublishThenInterrupt(),
                    timestamp=lambda: RUN_AT,
                )
            runner = _ChangeRunner()
            resumed = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                command_runner=runner,
                timestamp=lambda: RUN_AT,
            )
            task = next(iter(resumed["jobs"].values()))
            self.assertEqual(task["state"], "completed")
            self.assertEqual(task["attempts"], 1)
            self.assertEqual(runner.calls, [])
            self.assertEqual(resumed["runs"][0]["jobs_recovered_after_publish"], 1)

    def test_interruption_between_jobs_is_recorded_without_false_task_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 2)
            output = root / "change-run"
            config = ChangeBatchConfig(minimum_interval_seconds=0.1)
            runner = _ChangeRunner()

            def interrupt_between_jobs(_: float) -> None:
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    include_queue_ids=queue_ids,
                    max_jobs=2,
                    command_runner=runner,
                    sleep=interrupt_between_jobs,
                    timestamp=lambda: RUN_AT,
                )
            interrupted = json.loads((output / "batch-manifest.json").read_text())
            self.assertEqual(interrupted["runs"][0]["state"], "running")
            self.assertFalse(
                any(task["state"] == "running" for task in interrupted["jobs"].values())
            )
            self.assertEqual(interrupted["summary"]["jobs_completed"], 1)

            resumed = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=1,
                command_runner=_ChangeRunner(),
                sleep=lambda _: None,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(resumed["runs"][0]["state"], "interrupted")
            self.assertEqual(resumed["runs"][0]["jobs_interrupted"], 0)
            self.assertTrue(
                all(task["attempts"] == 1 for task in resumed["jobs"].values())
            )

    def test_interrupted_run_failure_counters_match_exact_failure_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 2)
            output = root / "change-run"
            config = ChangeBatchConfig(
                minimum_interval_seconds=0.1, max_job_attempts=1
            )

            def interrupt_between_jobs(_: float) -> None:
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=config,
                    include_queue_ids=queue_ids,
                    max_jobs=2,
                    command_runner=_ChangeRunner(returncode=1),
                    sleep=interrupt_between_jobs,
                    timestamp=lambda: RUN_AT,
                )
            resumed = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=1,
                command_runner=_ChangeRunner(),
                timestamp=lambda: RUN_AT,
            )
            first_run = resumed["runs"][0]
            self.assertEqual(first_run["state"], "interrupted")
            self.assertEqual(first_run["jobs_failed"], 1)
            self.assertEqual(first_run["jobs_interrupted"], 0)
            first_failure = resumed["jobs"][queue_ids[0]]["failures"][0]
            self.assertEqual(first_failure["kind"], "command_exit")

            checkpoint = output / "batch-manifest.json"
            tampered = json.loads(checkpoint.read_text())
            tampered["runs"][0]["jobs_failed"] = 0
            tampered["runs"][0]["jobs_interrupted"] = 1
            checkpoint.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SatelliteChangeBatchError, "interrupted outcomes"
            ):
                validate_satellite_change_batch(queue, [catalog], output)

    def test_symlink_stage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"

            def interrupt(*_: object, **__: object) -> None:
                raise KeyboardInterrupt

            with self.assertRaises(KeyboardInterrupt):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=ChangeBatchConfig(minimum_interval_seconds=0),
                    include_queue_ids=queue_ids,
                    command_runner=interrupt,
                    timestamp=lambda: RUN_AT,
                )
            task_dir = next((output / "jobs").iterdir())
            stage = task_dir / ".change.staging"
            stage.symlink_to(root / "elsewhere", target_is_directory=True)
            with self.assertRaisesRegex(SatelliteChangeBatchError, "stage|symlink"):
                validate_satellite_change_batch(queue, [catalog], output)

    def test_preexisting_output_without_checkpoint_is_never_adopted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 1)
            output = root / "change-run"
            unbound = output / "jobs" / queue_ids[0] / "change" / "report.json"
            unbound.parent.mkdir(parents=True)
            unbound.write_text("unbound historical output\n", encoding="utf-8")
            runner = _ChangeRunner()
            with self.assertRaisesRegex(
                SatelliteChangeBatchError, "without a checkpoint"
            ):
                execute_satellite_change_batch(
                    queue,
                    [catalog],
                    output,
                    config=ChangeBatchConfig(minimum_interval_seconds=0),
                    include_queue_ids=queue_ids,
                    command_runner=runner,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(runner.calls, [])
            self.assertEqual(unbound.read_text(), "unbound historical output\n")
            self.assertFalse((output / "batch-manifest.json").exists())

    def test_command_failures_clear_stage_and_obey_both_attempt_caps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, catalog, queue_ids = _catalog_fixture(root, 2)
            output = root / "change-run"
            config = ChangeBatchConfig(
                minimum_interval_seconds=0, max_job_attempts=2
            )

            class PartialFailure:
                def __init__(self) -> None:
                    self.calls: list[list[str]] = []

                def __call__(
                    self, command: list[str], **_: object
                ) -> subprocess.CompletedProcess[str]:
                    self.calls.append(command)
                    stage = Path(_pairs(command[2:])["--output-dir"])
                    stage.mkdir(parents=True)
                    (stage / "partial.tmp").write_text("partial", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 9, "", "fixture failure")

            runner = PartialFailure()
            first = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                include_queue_ids=queue_ids,
                max_jobs=1,
                command_runner=runner,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(first["runs"][-1]["job_attempts"], 1)
            self.assertEqual(len(runner.calls), 1)
            self.assertFalse(any(output.rglob("*.staging")))

            second = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=2,
                command_runner=runner,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(second["runs"][-1]["job_attempts"], 2)
            self.assertEqual(len(runner.calls), 3)
            tasks = [second["jobs"][queue_id] for queue_id in queue_ids]
            self.assertEqual([task["attempts"] for task in tasks], [2, 1])
            self.assertFalse(any(output.rglob("*.staging")))

            third = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=1,
                command_runner=runner,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(third["runs"][-1]["job_attempts"], 1)
            self.assertEqual(len(runner.calls), 4)
            self.assertEqual(third["summary"]["jobs_exhausted"], 2)
            self.assertTrue(
                all(task["attempts"] == 2 for task in third["jobs"].values())
            )
            fourth = execute_satellite_change_batch(
                queue,
                [catalog],
                output,
                config=config,
                max_jobs=5,
                command_runner=runner,
                timestamp=lambda: RUN_AT,
            )
            self.assertEqual(fourth["runs"][-1]["job_attempts"], 0)
            self.assertEqual(len(runner.calls), 4)
            self.assertFalse(any(output.rglob("*.staging")))

    def test_producer_uses_same_rounded_area_for_features_and_report_total(self) -> None:
        class NP:
            uint8 = object()

        class Mask:
            def astype(self, _: object) -> "Mask":
                return self

        area = 5_000.04
        width = 100.0
        height = area / width
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [[0.0, 0.0], [width, 0.0], [width, height], [0.0, height], [0.0, 0.0]]
            ],
        }

        def shapes(*_: object, **__: object):
            yield geometry, 1
            yield geometry, 1

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proposals.geojson"
            count, total = _write_proposals(
                NP(),
                shapes,
                lambda _source, _target, value, precision: value,
                output,
                Mask(),
                object(),
                "EPSG:32618",
                minimum_area_m2=5_000,
            )
            document = json.loads(output.read_text())
            feature_total = sum(
                feature["properties"]["area_m2"] for feature in document["features"]
            )
            self.assertEqual(count, 2)
            self.assertEqual(total, feature_total)
            self.assertEqual(total, 10_000.0)
            self.assertEqual(
                document["properties"]["schema_version"], REPORT_SCHEMA_VERSION
            )
            for feature in document["features"]:
                for field in (
                    "identity_claim",
                    "operator_claim",
                    "lifecycle_claim",
                    "operating_status_claim",
                    "data_centre_type_claim",
                    "it_capacity_claim",
                    "pue_claim",
                    "workload_claim",
                    "power_claim",
                    "energy_claim",
                ):
                    self.assertIs(feature["properties"][field], False)

    def test_module_has_no_duplicate_literal_dict_keys_or_top_level_defs(self) -> None:
        tree = ast.parse(Path(change_batch_module.__file__).read_text(encoding="utf-8"))
        top_level: dict[str, int] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.assertNotIn(node.name, top_level, f"duplicate top-level name {node.name}")
                top_level[node.name] = node.lineno
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys: dict[object, int] = {}
            for key in node.keys:
                if not isinstance(key, ast.Constant):
                    continue
                try:
                    hash(key.value)
                except TypeError:
                    continue
                self.assertNotIn(
                    key.value,
                    literal_keys,
                    f"duplicate literal dict key {key.value!r} at line {key.lineno}",
                )
                literal_keys[key.value] = key.lineno


if __name__ == "__main__":
    unittest.main()
