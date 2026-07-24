from __future__ import annotations

import hashlib
import json
import unittest

from datacenter_atlas.satellite_catalog import (
    COPERNICUS_STAC_ENDPOINT,
    EARTH_SEARCH_V1_ENDPOINT,
    CatalogQuery,
    CatalogValidationError,
    Provider,
    build_pair_manifest,
    build_manifest,
    build_stac_request,
    manifest_json,
    normalize_feature_collection,
    select_scene_pair,
)


def item(
    item_id: str,
    timestamp: str,
    cloud: float,
    tile: str,
    *,
    assets: dict | None = None,
    license_name: str | None = None,
) -> dict:
    value = {
        "type": "Feature",
        "id": item_id,
        "collection": "sentinel-2-l2a",
        "bbox": [-77.6, 38.7, -77.5, 38.8],
        "properties": {
            "datetime": timestamp,
            "eo:cloud_cover": cloud,
            "grid:code": f"MGRS-{tile}",
        },
        "assets": assets
        or {
            "blue": {"href": f"https://example.test/{item_id}/blue.tif"},
            "green": {"href": f"https://example.test/{item_id}/green.tif"},
            "red": {"href": f"https://example.test/{item_id}/red.tif"},
            "nir": {"href": f"https://example.test/{item_id}/nir.tif"},
            "scl": {"href": f"https://example.test/{item_id}/scl.tif"},
            "thumbnail": {"href": f"https://example.test/{item_id}/thumb.jpg"},
        },
    }
    if license_name is not None:
        value["license"] = license_name
        value["attribution"] = "Fixture attribution"
    return value


class QueryTests(unittest.TestCase):
    def test_provider_request_payloads_are_bounded_and_deterministic(self) -> None:
        query = CatalogQuery(
            bbox=(-77.6, 38.7, -77.5, 38.8),
            start_date="2024-05-01",
            end_date="2026-06-30",
            max_cloud_cover=12,
            limit=25,
        )
        earth = build_stac_request(Provider.EARTH_SEARCH, query)
        copernicus = build_stac_request(Provider.COPERNICUS, query)
        self.assertEqual(earth["url"], EARTH_SEARCH_V1_ENDPOINT)
        self.assertEqual(copernicus["url"], COPERNICUS_STAC_ENDPOINT)
        self.assertEqual(earth["method"], "POST")
        self.assertEqual(earth["payload"], copernicus["payload"])
        self.assertEqual(earth["payload"]["collections"], ["sentinel-2-l2a"])
        self.assertEqual(earth["payload"]["bbox"], [-77.6, 38.7, -77.5, 38.8])
        self.assertEqual(
            earth["payload"]["datetime"],
            "2024-05-01T00:00:00Z/2026-06-30T23:59:59Z",
        )
        self.assertEqual(earth["payload"]["query"], {"eo:cloud_cover": {"lte": 12}})
        self.assertEqual(
            earth["payload"]["sortby"],
            [
                {"field": "properties.datetime", "direction": "asc"},
                {"field": "id", "direction": "asc"},
            ],
        )

    def test_query_validation_rejects_unbounded_or_ambiguous_values(self) -> None:
        invalid = (
            {"bbox": (-181, 0, 1, 1)},
            {"bbox": (0, 0, 0, 1)},
            {"bbox": (0, 0, 1, 91)},
            {"bbox": (0, 0, 1, 1), "start_date": "2025-02-30"},
            {
                "bbox": (0, 0, 1, 1),
                "start_date": "2025-02-01",
                "end_date": "2025-01-01",
            },
            {"bbox": (0, 0, 1, 1), "max_cloud_cover": -1},
            {"bbox": (0, 0, 1, 1), "max_cloud_cover": 101},
            {"bbox": (0, 0, 1, 1), "limit": 101},
        )
        defaults = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(CatalogValidationError):
                CatalogQuery(**(defaults | changes))


class NormalizationTests(unittest.TestCase):
    def test_normalizes_provider_variants_and_preserves_rights(self) -> None:
        feature = item(
            "S2A_MSIL2A_20250520T000000_T18SUJ_20250520T010000",
            "2025-05-20T01:02:03+00:00",
            7.5,
            "18SUJ",
            assets={
                "B02_10m": {"href": "https://cdse.test/B02.tif"},
                "B03_10m": {"href": "https://cdse.test/B03.tif"},
                "B04_10m": {"href": "https://cdse.test/B04.tif"},
                "B08_10m": {"href": "https://cdse.test/B08.tif"},
                "SCL_20m": {"href": "https://cdse.test/SCL.tif"},
                "metadata": {"href": "https://cdse.test/metadata.xml"},
            },
            license_name="fixture-license",
        )
        result = normalize_feature_collection(
            Provider.COPERNICUS,
            {"type": "FeatureCollection", "features": [feature]},
        )
        self.assertEqual(
            result,
            [
                {
                    "output_label": "imagery_evidence",
                    "provider": "copernicus-data-space",
                    "collection": "sentinel-2-l2a",
                    "item_id": feature["id"],
                    "datetime": "2025-05-20T01:02:03Z",
                    "cloud_cover": 7.5,
                    "bbox": [-77.6, 38.7, -77.5, 38.8],
                    "mgrs_tile": "18SUJ",
                    "assets": {
                        "B02": "https://cdse.test/B02.tif",
                        "B03": "https://cdse.test/B03.tif",
                        "B04": "https://cdse.test/B04.tif",
                        "B08": "https://cdse.test/B08.tif",
                        "SCL": "https://cdse.test/SCL.tif",
                    },
                    "license": "fixture-license",
                    "license_url": (
                        "https://sentinels.copernicus.eu/documents/247904/690755/"
                        "Sentinel_Data_Legal_Notice"
                    ),
                    "attribution": "Fixture attribution",
                }
            ],
        )

    def test_results_are_sorted_and_defaults_are_explicit(self) -> None:
        later = item("later", "2025-05-21T00:00:00Z", 2, "18SUJ")
        earlier = item("earlier", "2025-05-20T00:00:00Z", 3, "18SUJ")
        records = normalize_feature_collection(
            Provider.EARTH_SEARCH,
            {"type": "FeatureCollection", "features": [later, earlier]},
        )
        self.assertEqual([record["item_id"] for record in records], ["earlier", "later"])
        self.assertEqual(records[0]["license"], "proprietary")
        self.assertIn("Sentinel_Data_Legal_Notice", records[0]["license_url"])
        self.assertIn("Copernicus", records[0]["attribution"])

    def test_malformed_feature_collection_fails_instead_of_dropping_data(self) -> None:
        bad_cases = [
            {},
            {"type": "FeatureCollection", "features": {}},
            {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
            {
                "type": "FeatureCollection",
                "features": [item("bad-cloud", "2025-01-01T00:00:00Z", 101, "18SUJ")],
            },
            {
                "type": "FeatureCollection",
                "features": [
                    item("no-zone", "2025-01-01T00:00:00", 1, "18SUJ")
                ],
            },
        ]
        no_bbox = item("no-bbox", "2025-01-01T00:00:00Z", 1, "18SUJ")
        del no_bbox["bbox"]
        bad_cases.append({"type": "FeatureCollection", "features": [no_bbox]})
        no_assets = item("no-assets", "2025-01-01T00:00:00Z", 1, "18SUJ")
        no_assets["assets"] = {"thumbnail": {"href": "https://example.test/thumb.jpg"}}
        bad_cases.append({"type": "FeatureCollection", "features": [no_assets]})
        wrong_collection = item("landsat", "2025-01-01T00:00:00Z", 1, "18SUJ")
        wrong_collection["collection"] = "landsat-c2-l2"
        bad_cases.append({"type": "FeatureCollection", "features": [wrong_collection]})
        for feature_collection in bad_cases:
            with self.subTest(feature_collection=feature_collection), self.assertRaises(
                CatalogValidationError
            ):
                normalize_feature_collection(Provider.EARTH_SEARCH, feature_collection)


class SelectionAndManifestTests(unittest.TestCase):
    def _records(self, *features: dict) -> list[dict]:
        return normalize_feature_collection(
            Provider.EARTH_SEARCH,
            {"type": "FeatureCollection", "features": list(features)},
        )

    def test_selection_prefers_same_tile_then_season_then_cloud(self) -> None:
        records = self._records(
            item("base-low-cross-tile", "2024-05-20T00:00:00Z", 0, "17SPU"),
            item("base-same-tile", "2024-05-22T00:00:00Z", 9, "18SUJ"),
            item("current-same-season", "2025-05-23T00:00:00Z", 8, "18SUJ"),
            item("current-wrong-season", "2025-06-10T00:00:00Z", 1, "18SUJ"),
            item("current-low-cross-tile", "2025-05-20T00:00:00Z", 0, "17TNE"),
        )
        selected = select_scene_pair(
            records,
            baseline_date="2024-05-20",
            current_date="2025-05-20",
            temporal_window_days=30,
        )
        self.assertEqual(selected["baseline"]["item_id"], "base-same-tile")
        self.assertEqual(selected["current"]["item_id"], "current-same-season")

    def test_cloud_and_ids_break_otherwise_equal_ties_deterministically(self) -> None:
        records = self._records(
            item("base", "2024-05-20T10:15:00Z", 5, "18SUJ"),
            item("current-cloudy", "2025-05-20T10:15:00Z", 9, "18SUJ"),
            item("current-clear-z", "2025-05-20T10:15:00Z", 2, "18SUJ"),
            item("current-clear-a", "2025-05-20T10:15:00Z", 2, "18SUJ"),
        )
        selected = select_scene_pair(
            records,
            baseline_date="2024-05-20",
            current_date="2025-05-20",
            temporal_window_days=0,
        )
        self.assertEqual(selected["current"]["item_id"], "current-clear-a")

    def test_selection_requires_both_bounded_windows(self) -> None:
        records = self._records(item("only-current", "2025-05-20T00:00:00Z", 1, "18SUJ"))
        with self.assertRaisesRegex(CatalogValidationError, "baseline temporal window"):
            select_scene_pair(
                records,
                baseline_date="2024-05-20",
                current_date="2025-05-20",
                temporal_window_days=10,
            )

    def test_manifest_hashes_exact_response_and_labels_scope(self) -> None:
        response = {
            "type": "FeatureCollection",
            "features": [
                item("base", "2024-05-20T00:00:00Z", 3, "18SUJ"),
                item("current", "2025-05-21T00:00:00Z", 2, "18SUJ"),
            ],
        }
        raw = json.dumps(response, indent=2).encode("utf-8")
        query = CatalogQuery(
            (-77.6, 38.7, -77.5, 38.8), "2024-05-01", "2025-06-01", 20
        )
        manifest = build_manifest(
            Provider.EARTH_SEARCH,
            query,
            raw,
            baseline_date="2024-05-20",
            current_date="2025-05-20",
            retrieved_at="2026-07-17T19:00:00-07:00",
            temporal_window_days=10,
        )
        self.assertEqual(
            manifest["selected_ids"], {"baseline": "base", "current": "current"}
        )
        self.assertEqual(manifest["output_labels"], ["imagery_evidence", "visible_change_proposal"])
        self.assertIn("independent corroboration", manifest["scope_note"])
        self.assertEqual(manifest["retrieved_at"], "2026-07-18T02:00:00Z")
        self.assertEqual(manifest["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(manifest["normalized_results"]), 2)
        encoded_once = manifest_json(manifest)
        self.assertEqual(encoded_once, manifest_json(manifest))
        self.assertEqual(json.loads(encoded_once), manifest)

    def test_pair_manifest_hashes_two_bounded_windows(self) -> None:
        baseline_response = {
            "type": "FeatureCollection",
            "features": [item("base", "2024-06-13T00:00:00Z", 1, "18SUJ")],
        }
        current_response = {
            "type": "FeatureCollection",
            "features": [item("current", "2026-07-03T00:00:00Z", 2, "18SUJ")],
        }
        baseline_raw = json.dumps(baseline_response).encode()
        current_raw = json.dumps(current_response).encode()
        baseline_query = CatalogQuery(
            (-77.6, 38.7, -77.5, 38.8), "2024-05-01", "2024-07-31", 20
        )
        current_query = CatalogQuery(
            (-77.6, 38.7, -77.5, 38.8), "2026-06-01", "2026-07-31", 20
        )
        manifest = build_pair_manifest(
            Provider.EARTH_SEARCH,
            baseline_query,
            baseline_raw,
            current_query,
            current_raw,
            baseline_date="2024-06-13",
            current_date="2026-07-03",
            retrieved_at="2026-07-18T02:00:00Z",
            temporal_window_days=10,
        )
        self.assertEqual(manifest["selected_ids"], {"baseline": "base", "current": "current"})
        self.assertEqual(
            manifest["queries"]["baseline"]["raw_response_sha256"],
            hashlib.sha256(baseline_raw).hexdigest(),
        )
        self.assertEqual(
            manifest["queries"]["current"]["raw_response_sha256"],
            hashlib.sha256(current_raw).hexdigest(),
        )

    def test_pair_manifest_rejects_out_of_query_items(self) -> None:
        baseline_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [item("bad", "2023-06-13T00:00:00Z", 1, "18SUJ")],
            }
        )
        current_raw = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [item("current", "2026-07-03T00:00:00Z", 2, "18SUJ")],
            }
        )
        with self.assertRaisesRegex(CatalogValidationError, "outside its query dates"):
            build_pair_manifest(
                Provider.EARTH_SEARCH,
                CatalogQuery((-77.6, 38.7, -77.5, 38.8), "2024-05-01", "2024-07-31"),
                baseline_raw,
                CatalogQuery((-77.6, 38.7, -77.5, 38.8), "2026-06-01", "2026-07-31"),
                current_raw,
                baseline_date="2024-06-13",
                current_date="2026-07-03",
                retrieved_at="2026-07-18T02:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
