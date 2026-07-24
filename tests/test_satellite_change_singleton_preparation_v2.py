from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from rasterio.warp import transform_bounds

from datacenter_atlas.satellite_change import REQUIRED_ASSETS, canonical_sha256
from datacenter_atlas.satellite_change_singleton_preparation_v2 import (
    DEFINITION_PATH,
    EXPECTED_QUEUE_IDS,
    OUTPUT_PATH,
    ROOT,
    SatelliteChangeSingletonPreparationV2Error,
    derive_singleton_row_v2,
    validate_satellite_change_singleton_preparation_v2,
)


DEFINITION = ROOT / DEFINITION_PATH
OUTPUT = ROOT / OUTPUT_PATH
SOURCE_READY = (
    ROOT
    / "satellite_change_preparation/2026-07-20-open-seed-v57-active-v1/"
    "multi-tile-ready.jsonl"
)
EXPECTED_REBINDINGS = {
    "satq-54c6402eb93d14f1ea754e66": "12SVB",
    "satq-cef871428da247c3ecfadec6": "30UYC",
    "satq-96fca962064e09f0dbafa93b": "14SPF",
    "satq-78500568b1f6227789ae36f4": "30TYM",
    "satq-fb6b6f815dad079c059cf412": "29SNC",
    "satq-0ffe3647dc32ee25ef77eab7": "17TNF",
}
COVERAGE_PATCH_TARGET = (
    f"{derive_singleton_row_v2.__module__}.epoch_metadata_coverage"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _source_fixture() -> tuple[dict, dict[str, dict], dict]:
    row = _jsonl(SOURCE_READY)[0]
    documents = {}
    for epoch in ("baseline", "current"):
        path = ROOT / row["epochs"][epoch]["archived_stac_response"]["path"]
        documents[epoch] = _json(path)
    return row, documents, _json(DEFINITION)["processor"]


def _feature(document: dict, item_id: str) -> dict:
    return next(item for item in document["features"] if item["id"] == item_id)


def _update_prepared_digest(row: dict, epoch: str, role: str, digest: str) -> None:
    prepared = next(
        item
        for item in row["epochs"][epoch]["selected_item_asset_bindings"]
        if item["role"] == role
    )
    prepared["stac_item_sha256"] = digest


def _coverage(complete: bool) -> dict:
    return {
        "assets": {
            asset_name: {
                "complete": complete,
                "interpolation_halo_pixels": 1 if asset_name == "swir16" else 0,
                "required_window": {
                    "col_off": 0,
                    "height": 1,
                    "row_off": 0,
                    "width": 1,
                },
            }
            for asset_name in REQUIRED_ASSETS
        },
        "complete": complete,
    }


class SatelliteChangeSingletonPreparationV2Tests(unittest.TestCase):
    def test_frozen_release_validates_and_is_exactly_six_rows(self) -> None:
        manifest = validate_satellite_change_singleton_preparation_v2(
            OUTPUT, definition_path=DEFINITION
        )
        self.assertEqual(manifest["summary"]["jobs_ready"], 6)
        self.assertEqual(manifest["summary"]["candidate_bindings_assessed"], 24)
        self.assertEqual(
            manifest["summary"]["prior_companions_rebound_as_primary"], 12
        )
        self.assertEqual(manifest["summary"]["catalog_rediscoveries"], 0)
        self.assertEqual(manifest["summary"]["catalog_rerankings"], 0)
        rows = _jsonl(OUTPUT / "singleton-ready.jsonl")
        self.assertEqual(tuple(row["queue_id"] for row in rows), EXPECTED_QUEUE_IDS)
        self.assertEqual(stat.S_IMODE(OUTPUT.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in OUTPUT.iterdir())
        )

    def test_only_prepared_bindings_are_enumerated_and_companions_are_rebound(self) -> None:
        source = {row["queue_id"]: row for row in _jsonl(SOURCE_READY)}
        rows = _jsonl(OUTPUT / "singleton-ready.jsonl")
        for row in rows:
            queue_id = row["queue_id"]
            self.assertEqual(
                row["selection_scope"], "v1_prepared_selected_item_bindings_only"
            )
            flags = row["execution"]["arguments"][::2]
            self.assertFalse(any("companion" in flag for flag in flags))
            for epoch in ("baseline", "current"):
                source_ids = {
                    item["id"]
                    for item in source[queue_id]["epochs"][epoch][
                        "selected_item_asset_bindings"
                    ]
                }
                candidate_ids = {
                    candidate["binding"]["id"]
                    for candidate in row["epochs"][epoch]["singleton_candidates"]
                }
                self.assertEqual(candidate_ids, source_ids)
                self.assertEqual(row["epochs"][epoch]["selected_companions"], [])
                selected = row["epochs"][epoch]["selected_primary"]
                self.assertEqual(selected["prior_prepared_role"], "companion")
                self.assertEqual(selected["mgrs_tile"], EXPECTED_REBINDINGS[queue_id])
                self.assertTrue(row["epochs"][epoch]["selected_coverage"]["complete"])
                for asset_name in REQUIRED_ASSETS:
                    asset = row["epochs"][epoch]["selected_coverage"]["assets"][
                        asset_name
                    ]
                    self.assertTrue(asset["complete"])
                    self.assertEqual(
                        asset["interpolation_halo_pixels"],
                        1 if asset_name == "swir16" else 0,
                    )

    def test_old_primary_is_incomplete_and_selected_companion_is_complete(self) -> None:
        for row in _jsonl(OUTPUT / "singleton-ready.jsonl"):
            for epoch in ("baseline", "current"):
                candidates = {
                    value["prior_prepared_role"]: value
                    for value in row["epochs"][epoch]["singleton_candidates"]
                }
                self.assertFalse(candidates["primary"]["complete"])
                self.assertTrue(candidates["companion"]["complete"])

    def test_mutated_hash_fails_closed(self) -> None:
        row, documents, processor = _source_fixture()
        companion = next(
            item
            for item in row["epochs"]["baseline"]["selected_item_asset_bindings"]
            if item["role"] == "companion"
        )
        _feature(documents["baseline"], companion["id"])["properties"][
            "datetime"
        ] = "2024-06-05T18:25:05Z"
        with self.assertRaisesRegex(
            SatelliteChangeSingletonPreparationV2Error, "binding or acquisition"
        ):
            derive_singleton_row_v2(
                row,
                documents,
                transform_bounds=transform_bounds,
                processor=processor,
            )

    def test_mutated_acquisition_fails_closed_even_with_rebound_hash(self) -> None:
        row, documents, processor = _source_fixture()
        companion = next(
            item
            for item in row["epochs"]["baseline"]["selected_item_asset_bindings"]
            if item["role"] == "companion"
        )
        feature = _feature(documents["baseline"], companion["id"])
        feature["properties"]["s2:datatake_id"] = "MUTATED-DATATAKE"
        _update_prepared_digest(
            row, "baseline", "companion", canonical_sha256(feature)
        )
        with self.assertRaisesRegex(
            SatelliteChangeSingletonPreparationV2Error, "binding or acquisition"
        ):
            derive_singleton_row_v2(
                row,
                documents,
                transform_bounds=transform_bounds,
                processor=processor,
            )

    def test_mutated_grid_fails_closed(self) -> None:
        row, documents, processor = _source_fixture()
        companion = next(
            item
            for item in row["epochs"]["baseline"]["selected_item_asset_bindings"]
            if item["role"] == "companion"
        )
        feature = _feature(documents["baseline"], companion["id"])
        feature["assets"]["red"]["proj:transform"][1] = 1
        _update_prepared_digest(
            row, "baseline", "companion", canonical_sha256(feature)
        )
        with self.assertRaisesRegex(
            SatelliteChangeSingletonPreparationV2Error, "grid is invalid"
        ):
            derive_singleton_row_v2(
                row,
                documents,
                transform_bounds=transform_bounds,
                processor=processor,
            )

    def test_incomplete_singletons_fail_closed(self) -> None:
        row, documents, processor = _source_fixture()
        with patch(
            COVERAGE_PATCH_TARGET,
            return_value=_coverage(False),
        ):
            with self.assertRaisesRegex(
                SatelliteChangeSingletonPreparationV2Error, "pair is missing"
            ):
                derive_singleton_row_v2(
                    row,
                    documents,
                    transform_bounds=transform_bounds,
                    processor=processor,
                )

    def test_multiple_complete_singleton_pairs_fail_ambiguous(self) -> None:
        row, documents, processor = _source_fixture()
        with patch(
            COVERAGE_PATCH_TARGET,
            return_value=_coverage(True),
        ):
            with self.assertRaisesRegex(
                SatelliteChangeSingletonPreparationV2Error, "pair is ambiguous"
            ):
                derive_singleton_row_v2(
                    row,
                    documents,
                    transform_bounds=transform_bounds,
                    processor=processor,
                )

    def test_preserved_v1_files_and_failed_incident_remain_exact(self) -> None:
        definition = _json(DEFINITION)
        records = [
            *definition["preserved_lineage"].values(),
            definition["source_preparation"]["definition"],
            definition["source_preparation"]["manifest"],
            definition["source_preparation"]["ready_partition"],
            definition["technical_incident"]["manifest"],
        ]
        for record in records:
            path = ROOT / record["path"]
            raw = path.read_bytes()
            self.assertEqual(len(raw), record["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record["sha256"])
            self.assertEqual(f"{stat.S_IMODE(path.stat().st_mode):04o}", record["mode"])
        incident = _json(OUTPUT / "technical-incident.json")
        self.assertEqual(incident["jobs_failed"], 6)
        self.assertEqual(incident["jobs_completed"], 0)
        self.assertEqual(incident["retry_semantics"], "successor_selection_not_retry")


if __name__ == "__main__":
    unittest.main()
