from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.overture import (
    CANDIDATES_FILENAME,
    MANIFEST_FILENAME,
    OvertureConfig,
    OvertureValidationError,
    SOURCE_FILENAME,
    geometry_metrics,
    validate_overture_bundle,
    write_overture_bundle,
)


GENERATED_AT = "2026-07-18T20:00:00Z"


def _ring(x: float, y: float, size: float) -> list[list[float]]:
    return [
        [x, y],
        [x + size, y],
        [x + size, y + size],
        [x, y + size],
        [x, y],
    ]


def _source(
    gers_id: str,
    x: float,
    y: float,
    size: float,
    *,
    record_id: str | None,
    building_class: str | None,
) -> dict:
    properties = {
        "sources": [
            {
                "property": "",
                "dataset": "OpenStreetMap",
                "license": "ODbL-1.0",
                "record_id": record_id,
                "update_time": "2026-06-01T00:00:00.000Z",
                "confidence": None,
                "between": None,
            }
        ],
        "is_underground": False,
        "has_parts": False,
        "version": 2,
    }
    if building_class is not None:
        properties["class"] = building_class
        properties["subtype"] = "industrial"
    return {
        "id": gers_id,
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [_ring(x, y, size)]},
        "properties": properties,
    }


def _write_fixture(root: Path) -> tuple[Path, Path, Path, OvertureConfig, list[dict]]:
    source = root / "source.geojsonseq"
    features = [
        _source(
            "11111111-1111-4111-8111-111111111111",
            0.010,
            0.010,
            0.001,
            record_id="w123@2",
            building_class="warehouse",
        ),
        _source(
            "22222222-2222-4222-8222-222222222222",
            0.080,
            0.080,
            0.001,
            record_id="w456@1",
            building_class=None,
        ),
        _source(
            "33333333-3333-4333-8333-333333333333",
            0.050,
            0.050,
            0.0001,
            record_id=None,
            building_class="warehouse",
        ),
    ]
    source.write_bytes(
        b"".join(
            (json.dumps(feature, separators=(",", ":")) + "\n").encode()
            for feature in features
        )
    )
    state = Path(f"{source}.state")
    state.write_text(
        json.dumps(
            {
                "last_release": "2026-06-17.0",
                "last_run": "2026-07-18T19:00:00+00:00",
                "theme": "buildings",
                "type": "building",
                "bbox": {"xmin": 0.0, "ymin": 0.0, "xmax": 0.1, "ymax": 0.1},
                "backend": "geojsonseq",
                "output": str(source.resolve()),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    release = root / "2026-07-18-global-open-v3"
    release.mkdir()
    atlas = release / "atlas.geojson"
    atlas_document = {
        "type": "FeatureCollection",
        "atlas_as_of": "2026-07-18",
        "atlas_recorded_at": "2026-07-18T18:00:00Z",
        "attribution": ["fixture"],
        "features": [
            {
                "type": "Feature",
                "id": "atlas-known",
                "geometry": {"type": "Point", "coordinates": [0.0105, 0.0105]},
                "properties": {
                    "entity_id": "atlas-known",
                    "entity_kind": "facility",
                    "name": "Known source feature",
                    "longitude": 0.0105,
                    "latitude": 0.0105,
                    "stable_key": "osm:way/123",
                    "source_family": "openstreetmap",
                    "source_url": "https://www.openstreetmap.org/way/123",
                    "tags": {},
                },
            }
        ],
    }
    atlas_raw = (json.dumps(atlas_document, sort_keys=True) + "\n").encode()
    atlas.write_bytes(atlas_raw)
    (release / MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "files": {
                    "atlas.geojson": {
                        "bytes": len(atlas_raw),
                        "sha256": hashlib.sha256(atlas_raw).hexdigest(),
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = OvertureConfig(
        bbox=(0.0, 0.0, 0.1, 0.1),
        minimum_large_area_m2=5_000,
        minimum_very_large_area_m2=10_000,
        near_distance_m=100,
        possible_distance_m=500,
        novel_distance_m=2_000,
    )
    return source, state, atlas, config, features


class OvertureGeometryTests(unittest.TestCase):
    def test_polygon_hole_and_multipolygon_are_measured_without_mutation(self) -> None:
        polygon = {
            "type": "Polygon",
            "coordinates": [
                _ring(0, 0, 0.001),
                _ring(0.00025, 0.00025, 0.0005),
            ],
        }
        original = json.loads(json.dumps(polygon))
        metrics = geometry_metrics(polygon)
        self.assertEqual(polygon, original)
        self.assertAlmostEqual(metrics.rectangularity, 0.75, places=4)
        self.assertGreater(metrics.area_m2, 9_000)
        self.assertEqual(metrics.rings, 2)

        multi = {
            "type": "MultiPolygon",
            "coordinates": [
                [_ring(0, 0, 0.001)],
                [_ring(0.002, 0, 0.001)],
            ],
        }
        multi_metrics = geometry_metrics(multi)
        self.assertEqual(multi_metrics.geometry_type, "MultiPolygon")
        self.assertAlmostEqual(multi_metrics.centroid_longitude, 0.0015, places=5)
        self.assertTrue(math.isfinite(multi_metrics.area_m2))


class OvertureBundleTests(unittest.TestCase):
    def test_atomic_bundle_preserves_sources_and_non_merging_cross_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, state, atlas, config, features = _write_fixture(root)
            output = root / "bundle"
            manifest = write_overture_bundle(
                source,
                state,
                atlas,
                output,
                generated_at=GENERATED_AT,
                config=config,
            )
            self.assertEqual((output / SOURCE_FILENAME).read_bytes(), source.read_bytes())
            self.assertEqual(manifest["counts"]["source_features"], 3)
            self.assertEqual(manifest["counts"]["candidate_features"], 2)
            self.assertEqual(manifest["source_inventory"][0]["license"], "ODbL-1.0")
            self.assertEqual(validate_overture_bundle(output, atlas_path=atlas), manifest)

            candidates = [
                json.loads(line)
                for line in (output / CANDIDATES_FILENAME).read_text().splitlines()
            ]
            by_id = {candidate["id"]: candidate for candidate in candidates}
            known = by_id[features[0]["id"]]
            novel = by_id[features[1]["id"]]
            self.assertEqual(known["geometry"], features[0]["geometry"])
            self.assertEqual(
                known["properties"]["overture_properties"]["sources"],
                features[0]["properties"]["sources"],
            )
            known_reference = known["properties"]["atlas_cross_reference"]
            self.assertEqual(
                known_reference["label"], "known_exact_upstream_osm_identity"
            )
            self.assertFalse(known_reference["atlas_merge_performed"])
            self.assertEqual(
                novel["properties"]["atlas_cross_reference"]["label"],
                "novel_to_v3_atlas_no_coordinate_within_2km",
            )
            self.assertTrue(
                novel["properties"]["review_constraints"][
                    "candidate_is_not_data_centre_identity"
                ]
            )

    def test_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, state, atlas, config, _ = _write_fixture(root)
            output = root / "bundle"
            write_overture_bundle(
                source,
                state,
                atlas,
                output,
                generated_at=GENERATED_AT,
                config=config,
            )
            candidate_path = output / CANDIDATES_FILENAME
            candidate_path.write_bytes(candidate_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(OvertureValidationError, "artifact"):
                validate_overture_bundle(output)

    def test_invalid_input_leaves_no_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, state, atlas, config, _ = _write_fixture(root)
            records = source.read_text().splitlines()
            feature = json.loads(records[0])
            feature["geometry"]["coordinates"][0][-1] = [0.012, 0.012]
            records[0] = json.dumps(feature, separators=(",", ":"))
            source.write_text("\n".join(records) + "\n", encoding="utf-8")
            output = root / "bundle"
            with self.assertRaisesRegex(OvertureValidationError, "not closed"):
                write_overture_bundle(
                    source,
                    state,
                    atlas,
                    output,
                    generated_at=GENERATED_AT,
                    config=config,
                )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".bundle.stage-*")), [])

    def test_fetch_state_must_identify_exact_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, state, atlas, config, _ = _write_fixture(root)
            document = json.loads(state.read_text())
            document["output"] = str(root / "different.geojsonseq")
            state.write_text(json.dumps(document) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(OvertureValidationError, "identify"):
                write_overture_bundle(
                    source,
                    state,
                    atlas,
                    root / "bundle",
                    generated_at=GENERATED_AT,
                    config=config,
                )


if __name__ == "__main__":
    unittest.main()
