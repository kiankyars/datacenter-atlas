from __future__ import annotations

import base64
from datetime import UTC, datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import datacenter_atlas.open_buildings_temporal as obt
from datacenter_atlas.open_buildings_temporal import (
    ATLAS_PRIORS_FILENAME,
    CANDIDATES_FILENAME,
    DELTAS_FILENAME,
    OpenBuildingsTemporalConfig,
    OpenBuildingsTemporalValidationError,
    validate_candidate_bundle,
    validate_source_bundle,
    write_candidate_bundle,
    write_source_bundle,
)


GENERATED_AT = "2026-07-18T21:00:00Z"
PROJECTED_BBOX = (10.0, 20.0, 20.0, 30.0)


def _manifest_raw(config: OpenBuildingsTemporalConfig, year: int) -> bytes:
    return json.dumps(
        {
            "name": (
                "projects/mmeka-ee/assets/open-buildings-temporal/"
                f"{config.s2cell_token}_{config.projected_crs.replace(':', '_')}_"
                f"{year}_06_30"
            ),
            "startTime": f"{year}-06-30T07:00:00Z",
            "endTime": f"{year}-06-30T07:00:00Z",
            "properties": {
                "imagery_start_time_epoch_s": 1.0,
                "imagery_end_time_epoch_s": 2.0,
                "inference_time_epoch_s": datetime(
                    year, 6, 30, 7, tzinfo=UTC
                ).timestamp(),
                "s2cell_token": config.s2cell_token,
            },
            "bands": [
                {
                    "id": "building_fractional_count",
                    "tilesetId": "a0",
                    "missingData": {"values": [-99.0]},
                },
                {
                    "id": "building_height",
                    "tilesetId": "a0",
                    "tilesetBandIndex": 1,
                    "missingData": {"values": [-99.0]},
                },
                {
                    "id": "building_presence",
                    "tilesetId": "a0",
                    "tilesetBandIndex": 2,
                    "missingData": {"values": [-99.0]},
                },
            ],
            "tilesets": [
                {
                    "id": "a0",
                    "crs": config.projected_crs,
                    "dataType": "FLOAT",
                    "sources": [
                        {
                            "uris": [f"fixture_{year}/tile.tif"],
                            "affineTransform": {
                                "scaleX": 0.5,
                                "translateX": 0.0,
                                "scaleY": -0.5,
                                "translateY": 100.0,
                            },
                            "dimensions": {"width": 25000, "height": 25000},
                        }
                    ],
                }
            ],
            "uriPrefix": "gs://open-buildings-temporal-data/v1/geotiffs/1",
            "skipMetadataRead": True,
        },
        separators=(",", ":"),
    ).encode()


def _metadata(name: str, raw: bytes = b"tile") -> dict:
    md5 = hashlib.md5(raw, usedforsecurity=False).digest()
    return {
        "name": name,
        "generation": "1730000000000000",
        "bytes": len(raw),
        "md5_base64": base64.b64encode(md5).decode(),
        "md5_hex": md5.hex(),
        "crc32c_base64": "AAAAAA==",
        "etag": "fixture-etag",
        "updated": "2024-10-31T09:43:01Z",
    }


class _FakeClient:
    def __init__(
        self, config: OpenBuildingsTemporalConfig, *, fail_after: int | None = None
    ):
        self.config = config
        self.fail_after = fail_after
        self.calls = 0
        self.manifests = {
            obt._manifest_object_name(config, year): _manifest_raw(config, year)
            for year in config.years
        }

    def _tick(self) -> None:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise OpenBuildingsTemporalValidationError("fixture fetch failure")

    def metadata(self, name: str) -> dict:
        self._tick()
        if name in self.manifests:
            return _metadata(name, self.manifests[name])
        return _metadata(name)

    def download(self, metadata: dict) -> bytes:
        self._tick()
        return self.manifests[metadata["name"]]


def _write_source(root: Path) -> tuple[Path, OpenBuildingsTemporalConfig]:
    config = OpenBuildingsTemporalConfig()
    source = root / "source"
    write_source_bundle(
        source,
        generated_at=GENERATED_AT,
        config=config,
        client=_FakeClient(config),
        project_bbox=lambda _bbox, _crs: PROJECTED_BBOX,
    )
    return source, config


def _write_atlas(root: Path, config: OpenBuildingsTemporalConfig) -> Path:
    release = root / "2026-07-18-global-open-v3"
    release.mkdir()
    west, south, east, north = config.bbox
    atlas = release / "atlas.geojson"
    atlas_document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "known",
                "geometry": {
                    "type": "Point",
                    "coordinates": [(west + east) / 2, (south + north) / 2],
                },
                "properties": {
                    "entity_id": "known",
                    "name": "Known prior",
                    "source_family": "fixture",
                    "stable_key": "fixture:known",
                },
            },
            {
                "type": "Feature",
                "id": "far",
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {
                    "entity_id": "far",
                    "name": "Far away",
                    "source_family": "fixture",
                    "stable_key": "fixture:far",
                },
            },
        ],
    }
    atlas_raw = (json.dumps(atlas_document, sort_keys=True) + "\n").encode()
    atlas.write_bytes(atlas_raw)
    (release / "manifest.json").write_text(
        json.dumps(
            {
                "as_of": "2026-07-18",
                "recorded_at": "2026-07-18T20:00:00Z",
                "files": {"atlas.geojson": obt._raw_record(atlas_raw)},
            }
        )
        + "\n"
    )
    return atlas


COUNT_SUMS = (10.0, 9.0, 20.0, 21.0, 40.0, 38.0, 30.0, 65.0)
PRESENCE_MEANS = (0.20, 0.19, 0.21, 0.20, 0.25, 0.24, 0.23, 0.30)


def _observation(tile: dict, query: dict) -> dict:
    year = tile["year"]
    index = year - 2016
    count_sum = COUNT_SUMS[index]
    presence_mean = PRESENCE_MEANS[index]
    digest = hashlib.sha256(str(year).encode()).hexdigest()
    return {
        "schema_version": 1,
        "year": year,
        "inference_time": f"{year}-06-30T07:00:00Z",
        "source_object": tile["object"],
        "window": {
            "projected_crs": query["aoi"]["projected_crs"],
            "column_offset": 20,
            "row_offset": 140,
            "width_storage_pixels": 100,
            "height_storage_pixels": 40,
            "projected_bounds": [10.0, 20.0, 20.0, 30.0],
            "storage_grid_resolution_m": 0.5,
            "effective_spatial_resolution_m": 4.0,
        },
        "samples": {
            "total_storage_pixels": 4000,
            "valid_storage_pixels": 4000,
            "storage_pixels_are_not_independent_half_metre_detections": True,
        },
        "band_array_hashes": {
            name: {
                "float32_little_endian_row_major_sha256": digest,
                "valid_samples": 4000,
            }
            for name in obt.BANDS
        },
        "band_statistics": {
            "building_fractional_count": {
                "minimum": 0.0,
                "maximum": 0.021,
                "mean": round(count_sum / 4000, 6),
                "sum": count_sum,
                "sum_is_modelled_fractional_count_signal": True,
            },
            "building_height": {
                "raw_minimum_for_range_validation_only": 0.0,
                "raw_maximum_for_range_validation_only": 20.0,
                "interpreted_only_after_building_presence_screen": True,
            },
            "building_presence": {
                "minimum": 0.0,
                "maximum": 0.9,
                "mean": presence_mean,
                "mean_is_uncalibrated_relative_confidence": True,
                "samples_gte_height_screen": 1000,
                "fraction_gte_height_screen": 0.25,
            },
        },
        "presence_screened_height": {
            "building_presence_threshold": 0.5,
            "threshold_is_relative_screen_not_probability": True,
            "samples": 1000,
            "mean_m": 10.0 + index / 10,
            "maximum_m": 20.0,
        },
        "semantics": {
            "fractional_count_is_model_signal_not_observed_building_count": True,
            "presence_is_uncalibrated_relative_confidence": True,
            "height_is_modelled_above_terrain_not_measured": True,
        },
    }


class OpenBuildingsTemporalSourceTests(unittest.TestCase):
    def test_configuration_is_bounded_and_requires_the_full_annual_series(self) -> None:
        with self.assertRaisesRegex(OpenBuildingsTemporalValidationError, "area"):
            OpenBuildingsTemporalConfig(bbox=(0.0, 0.0, 1.0, 1.0))
        with self.assertRaisesRegex(OpenBuildingsTemporalValidationError, "2016-2023"):
            OpenBuildingsTemporalConfig(years=(2022, 2023))

    def test_source_bundle_is_closed_hash_bound_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, config = _write_source(root)
            manifest = validate_source_bundle(source)
            self.assertEqual(len(manifest["source_files"]), 8)
            self.assertEqual(len(manifest["selected_tiles"]), 8)
            self.assertEqual(manifest["query"]["years"], list(range(2016, 2024)))
            self.assertEqual(
                manifest["query"]["semantics"]["effective_spatial_resolution_m"],
                4.0,
            )
            with self.assertRaisesRegex(
                OpenBuildingsTemporalValidationError, "refusing"
            ):
                write_source_bundle(
                    source,
                    generated_at=GENERATED_AT,
                    config=config,
                    client=_FakeClient(config),
                    project_bbox=lambda _bbox, _crs: PROJECTED_BBOX,
                )

    def test_source_tampering_and_partial_failure_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, config = _write_source(root)
            first = source / obt._manifest_filename(config, 2016)
            first.write_bytes(first.read_bytes() + b" ")
            with self.assertRaisesRegex(OpenBuildingsTemporalValidationError, "hash"):
                validate_source_bundle(source)

            failed = root / "failed"
            with self.assertRaisesRegex(
                OpenBuildingsTemporalValidationError, "fixture"
            ):
                write_source_bundle(
                    failed,
                    generated_at=GENERATED_AT,
                    config=config,
                    client=_FakeClient(config, fail_after=4),
                    project_bbox=lambda _bbox, _crs: PROJECTED_BBOX,
                )
            self.assertFalse(failed.exists())
            self.assertEqual(list(root.glob(".failed.stage-*")), [])


class OpenBuildingsTemporalCandidateTests(unittest.TestCase):
    def test_review_bundle_preserves_semantics_and_non_merging_priors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, config = _write_source(root)
            atlas = _write_atlas(root, config)
            output = root / "review"
            manifest = write_candidate_bundle(
                source,
                atlas,
                output,
                generated_at=GENERATED_AT,
                observation_reader=_observation,
            )
            self.assertEqual(
                manifest["counts"],
                {
                    "annual_observations": 8,
                    "annual_deltas": 7,
                    "review_candidates": 3,
                    "nearby_v3_atlas_priors": 1,
                },
            )
            self.assertEqual(
                validate_candidate_bundle(
                    output, source_directory=source, atlas_path=atlas
                ),
                manifest,
            )
            priors = [
                json.loads(line)
                for line in (output / ATLAS_PRIORS_FILENAME).read_text().splitlines()
            ]
            self.assertEqual([prior["entity_id"] for prior in priors], ["known"])
            self.assertFalse(priors[0]["merge_performed"])
            candidates = [
                json.loads(line)
                for line in (output / CANDIDATES_FILENAME).read_text().splitlines()
            ]
            self.assertEqual(
                [candidate["interval"]["end_year"] for candidate in candidates],
                [2018, 2020, 2023],
            )
            forbidden = {"status", "facility_type", "capacity", "power", "energy"}
            found: set[str] = set()

            def walk(value: object) -> None:
                if isinstance(value, dict):
                    found.update(forbidden.intersection(value))
                    for nested in value.values():
                        walk(nested)
                elif isinstance(value, list):
                    for nested in value:
                        walk(nested)

            for candidate in candidates:
                walk(candidate)
            self.assertEqual(found, set())
            with self.assertRaisesRegex(
                OpenBuildingsTemporalValidationError, "refusing"
            ):
                write_candidate_bundle(
                    source,
                    atlas,
                    output,
                    generated_at=GENERATED_AT,
                    observation_reader=_observation,
                )

    def test_candidate_artifact_tampering_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, config = _write_source(root)
            atlas = _write_atlas(root, config)
            output = root / "review"
            write_candidate_bundle(
                source,
                atlas,
                output,
                generated_at=GENERATED_AT,
                observation_reader=_observation,
            )
            delta_path = output / DELTAS_FILENAME
            delta_path.write_bytes(delta_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(OpenBuildingsTemporalValidationError, "hash"):
                validate_candidate_bundle(output)

    def test_invalid_observation_leaves_no_partial_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, config = _write_source(root)
            atlas = _write_atlas(root, config)
            output = root / "review"

            def invalid(tile: dict, query: dict) -> dict:
                record = _observation(tile, query)
                record["band_statistics"]["building_height"][
                    "raw_maximum_for_range_validation_only"
                ] = 101.0
                return record

            with self.assertRaisesRegex(
                OpenBuildingsTemporalValidationError, "band values"
            ):
                write_candidate_bundle(
                    source,
                    atlas,
                    output,
                    generated_at=GENERATED_AT,
                    observation_reader=invalid,
                )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".review.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
