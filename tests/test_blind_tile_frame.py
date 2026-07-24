from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.blind_tile_frame import (
    ATTRIBUTION_FILENAME,
    BlindTileFrameError,
    COVERAGE_FILENAME,
    DEFINITION_FILENAME,
    FRAME_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    QUOTAS,
    RELEASE_ID,
    SAMPLE_FILENAME,
    SEED_SHA256,
    STRATA_FILENAME,
    build_preflight_bundle,
    canonical_json,
    classify_stratum,
    draw_key,
    is_frozen_release,
    sha256_bytes,
    tile_id,
    validate_release_bundle,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFINITION = PACKAGE_ROOT / "sources" / f"{RELEASE_ID}.json"
BUNDLE = PACKAGE_ROOT / "blind_tile_frames" / RELEASE_ID
FIXTURE = (
    PACKAGE_ROOT
    / "sources"
    / "blind_tile_frame_inputs"
    / "preflight-fixture-2026-07-19-v1.json"
)
NATURAL_EARTH = (
    PACKAGE_ROOT
    / "source_cache"
    / "natural-earth-5.1.1-ca96624"
    / "ne_10m_admin_0_countries.geojson"
)


def _frame_rows(bundle: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in gzip.decompress((bundle / FRAME_FILENAME).read_bytes()).splitlines()
    ]


def _sample_rows(bundle: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (bundle / SAMPLE_FILENAME).read_text(encoding="utf-8").splitlines()
    ]


def _copy_as_mutable(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, copy_function=shutil.copyfile)
    destination.chmod(0o755)
    for path in destination.iterdir():
        path.chmod(0o644)


def _rehash_bundle(bundle: Path) -> None:
    manifest = json.loads((bundle / MANIFEST_FILENAME).read_bytes())
    for name in manifest["files"]:
        raw = (bundle / name).read_bytes()
        manifest["files"][name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    raw = canonical_json(manifest)
    (bundle / MANIFEST_FILENAME).write_bytes(raw)
    (bundle / MANIFEST_HASH_FILENAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {MANIFEST_FILENAME}\n",
        encoding="ascii",
    )


class BlindTileFrameTests(unittest.TestCase):
    def test_seed_and_draw_key_are_literal_ascii_contract(self) -> None:
        seed = "datacenter-atlas-blind-tile-audit-v1|frame-2026-07-19"
        self.assertEqual(hashlib.sha256(seed.encode("ascii")).hexdigest(), SEED_SHA256)
        identifier = "e6933-4km-x-003000-y-001200"
        self.assertEqual(
            draw_key(identifier),
            hashlib.sha256(
                SEED_SHA256.encode("ascii") + b"\0" + identifier.encode("ascii")
            ).hexdigest(),
        )
        self.assertEqual(tile_id(-3000, -1200), identifier)

    def test_four_strata_and_unknown_lower_policy(self) -> None:
        common = {
            "land_intersection_area_m2": 12_000_000,
            "ghsl_smod_urban_cluster": False,
            "osm_stable_grid_max_parsed_voltage_kv": 110,
            "osm_stable_grid_min_distance_m": 6_000,
        }
        background, flags = classify_stratum(
            land_intersection_area_m2=12_000_000,
            ghsl_built_surface_2020_m2=None,
            ghsl_smod_urban_cluster=None,
            osm_stable_industrial_intersection_m2_after_exclusions=None,
            osm_stable_grid_min_distance_m=None,
            osm_stable_grid_max_parsed_voltage_kv=None,
        )
        self.assertEqual(background, "background")
        self.assertEqual(
            flags["unknown_signal_fields"],
            [
                "ghsl_built_surface_2020_m2",
                "ghsl_smod_urban_cluster",
                "osm_stable_grid_max_parsed_voltage_kv",
                "osm_stable_grid_min_distance_m",
                "osm_stable_industrial_intersection_m2_after_exclusions",
            ],
        )
        urban, _ = classify_stratum(
            **common,
            ghsl_built_surface_2020_m2=60_000,
            osm_stable_industrial_intersection_m2_after_exclusions=0,
        )
        self.assertEqual(urban, "urban_built")
        xor, xor_flags = classify_stratum(
            **common,
            ghsl_built_surface_2020_m2=80_000,
            osm_stable_industrial_intersection_m2_after_exclusions=10_000,
        )
        self.assertEqual(xor, "industrial_xor_grid")
        self.assertTrue(xor_flags["urban"])
        both, _ = classify_stratum(
            land_intersection_area_m2=12_000_000,
            ghsl_built_surface_2020_m2=0,
            ghsl_smod_urban_cluster=False,
            osm_stable_industrial_intersection_m2_after_exclusions=10_000,
            osm_stable_grid_min_distance_m=5_000,
            osm_stable_grid_max_parsed_voltage_kv=110,
        )
        self.assertEqual(both, "industrial_and_grid")

    def test_frozen_preflight_reproduces_and_discloses_blockers(self) -> None:
        result = validate_release_bundle(BUNDLE, definition_path=DEFINITION)
        self.assertEqual(result["frame_cell_count"], 184)
        self.assertEqual(result["sample_cell_count"], 180)
        self.assertTrue(is_frozen_release(BUNDLE))
        self.assertTrue(result["coverage"]["fixture_only"])
        self.assertFalse(result["coverage"]["production_frame_built"])
        self.assertEqual(len(result["coverage"]["blockers"]), 3)
        self.assertFalse(
            result["coverage"]["claims"]["complete_global_land_frame"]
        )
        self.assertFalse(
            result["coverage"]["claims"]["production_960_tile_sample_built"]
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            "7ac8dbb38e2c7e30d891e460d4e93af198125f2e3ac3dc593be6a1ccb5a6b812",
        )
        self.assertEqual(
            result["manifest_sha256"],
            "7517e133339d529d019229ee1d58cc2a06fb46cbfd82c7c00b46af0bba121af5",
        )
        self.assertEqual(BUNDLE.stat().st_mode & 0o777, 0o555)
        for path in BUNDLE.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_fixture_exercises_all_overlaps_ties_and_stratum_quotas(self) -> None:
        frame = _frame_rows(BUNDLE)
        self.assertEqual([row["tile_id"] for row in frame], sorted(row["tile_id"] for row in frame))
        equal_ties = [
            row
            for row in frame
            if len(row["country_overlaps"]) == 2
            and row["country_overlaps"][0]["area_m2"]
            == row["country_overlaps"][1]["area_m2"]
        ]
        self.assertEqual(len(equal_ties), 24)
        for row in equal_ties:
            self.assertEqual(
                row["assigned_country"]["country_key"],
                min(item["country_key"] for item in row["country_overlaps"]),
            )
        strata = json.loads((BUNDLE / STRATA_FILENAME).read_bytes())
        europe = {
            row["stratum"]: row
            for row in strata["groups"]
            if row["macroregion"] == "Europe"
        }
        self.assertEqual(
            {name: row["population_size"] for name, row in europe.items()},
            {
                "background": 17,
                "urban_built": 25,
                "industrial_xor_grid": 41,
                "industrial_and_grid": 81,
            },
        )
        self.assertEqual(
            {name: row["sample_size"] for name, row in europe.items()}, QUOTAS
        )
        self.assertTrue(all(not row["census"] for row in europe.values()))

    def test_sample_keeps_exact_unreduced_probabilities_and_weights(self) -> None:
        rows = _sample_rows(BUNDLE)
        europe_background = [
            row
            for row in rows
            if row["macroregion"] == "Europe" and row["stratum"] == "background"
        ]
        self.assertEqual(len(europe_background), 16)
        self.assertEqual(
            [row["rank_within_stratum"] for row in europe_background],
            list(range(1, 17)),
        )
        for row in europe_background:
            self.assertEqual(
                row["inclusion_probability"], {"numerator": 16, "denominator": 17}
            )
            self.assertEqual(
                row["design_weight"], {"numerator": 17, "denominator": 16}
            )
            self.assertFalse(row["selection_is_data_centre_evidence"])

    def test_candidate_artifact_mutation_cannot_change_bundle_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sources" / "blind_tile_frame_inputs").mkdir(parents=True)
            (root / "source_cache" / "natural-earth-5.1.1-ca96624").mkdir(
                parents=True
            )
            (root / "datacenter_atlas").mkdir()
            shutil.copyfile(DEFINITION, root / "sources" / DEFINITION.name)
            shutil.copyfile(
                PACKAGE_ROOT / "datacenter_atlas" / "blind_tile_frame.py",
                root / "datacenter_atlas" / "blind_tile_frame.py",
            )
            shutil.copyfile(
                FIXTURE,
                root
                / "sources"
                / "blind_tile_frame_inputs"
                / "preflight-fixture-2026-07-19-v1.json",
            )
            shutil.copyfile(
                NATURAL_EARTH,
                root
                / "source_cache"
                / "natural-earth-5.1.1-ca96624"
                / "ne_10m_admin_0_countries.geojson",
            )
            decoy = root / "candidate_fusion" / "decoy.json"
            decoy.parent.mkdir()
            decoy.write_text('{"version":1}\n', encoding="utf-8")
            first = root / "first"
            second = root / "second"
            build_preflight_bundle(
                first,
                definition_path=root / "sources" / DEFINITION.name,
                freeze=False,
            )
            decoy.write_text('{"version":2,"changed":true}\n', encoding="utf-8")
            build_preflight_bundle(
                second,
                definition_path=root / "sources" / DEFINITION.name,
                freeze=False,
            )
            self.assertEqual(
                {path.name: path.read_bytes() for path in first.iterdir()},
                {path.name: path.read_bytes() for path in second.iterdir()},
            )

    def test_forbidden_candidate_input_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            definition = json.loads(DEFINITION.read_bytes())
            definition["input_contract"]["normalized_fixture"]["path"] = (
                "../candidate_fusion/fixture.json"
            )
            path = Path(temporary) / "definition.json"
            path.write_bytes(canonical_json(definition))
            with self.assertRaisesRegex(
                BlindTileFrameError, "forbidden candidate-derived reference"
            ):
                build_preflight_bundle(
                    Path(temporary) / "output",
                    definition_path=path,
                    freeze=False,
                )

    def test_semantic_tamper_fails_even_after_manifest_is_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _copy_as_mutable(BUNDLE, bundle)
            rows = _sample_rows(bundle)
            rows[0]["selection_is_data_centre_evidence"] = True
            (bundle / SAMPLE_FILENAME).write_bytes(
                b"".join(
                    json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
                    + b"\n"
                    for row in rows
                )
            )
            _rehash_bundle(bundle)
            with self.assertRaisesRegex(BlindTileFrameError, "sample rows"):
                validate_release_bundle(
                    bundle, definition_path=DEFINITION, require_frozen=False
                )

    def test_bundle_has_only_declared_frame_sample_files(self) -> None:
        self.assertEqual(
            {path.name for path in BUNDLE.iterdir()},
            {
                ATTRIBUTION_FILENAME,
                COVERAGE_FILENAME,
                DEFINITION_FILENAME,
                FRAME_FILENAME,
                MANIFEST_FILENAME,
                MANIFEST_HASH_FILENAME,
                "README.md",
                SAMPLE_FILENAME,
                STRATA_FILENAME,
            },
        )


if __name__ == "__main__":
    unittest.main()
