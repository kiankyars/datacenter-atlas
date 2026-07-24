from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

from datacenter_atlas import blind_tile_auxiliary_integration as integration


FIXED_TIME = "2026-07-19T12:00:00Z"
LAND = 12_000_000_000
TILES = tuple(
    f"e6933-4km-x+00000{index}-y+000001" for index in range(1, 6)
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_bytes(b"".join(integration.canonical_line(row) for row in rows))


def _file_checkpoint(path: Path, relative_path: str) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": relative_path,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _fixture_rows() -> dict[str, list[dict[str, object]]]:
    a, b, c, d, e = TILES
    tiles = [{"land_area_mm2": LAND, "tile_id": tile} for tile in TILES]
    built_cells = [
        {
            "built_surface_m2": 60,
            "fragments": [{"area_mm2": LAND, "tile_id": a}],
            "source_cell_id": "built:a",
            "source_land_area_mm2": LAND,
        },
        {
            "built_surface_m2": 59,
            "fragments": [{"area_mm2": LAND, "tile_id": b}],
            "source_cell_id": "built:b",
            "source_land_area_mm2": LAND,
        },
        {
            "built_surface_m2": 35,
            "fragments": [{"area_mm2": LAND // 2, "tile_id": c}],
            "source_cell_id": "built:c-valid",
            "source_land_area_mm2": LAND // 2,
        },
        {
            "built_surface_m2": None,
            "fragments": [{"area_mm2": LAND // 2, "tile_id": c}],
            "source_cell_id": "built:c-nodata",
            "source_land_area_mm2": LAND // 2,
        },
        {
            "built_surface_m2": 0,
            "fragments": [{"area_mm2": LAND, "tile_id": d}],
            "source_cell_id": "built:d",
            "source_land_area_mm2": LAND,
        },
        {
            "built_surface_m2": 0,
            "fragments": [{"area_mm2": LAND, "tile_id": e}],
            "source_cell_id": "built:e",
            "source_land_area_mm2": LAND,
        },
    ]
    smod_cells = [
        {
            "code": 10,
            "fragments": [{"area_mm2": LAND, "tile_id": a}],
            "source_cell_id": "smod:a",
            "source_land_area_mm2": LAND,
        },
        {
            "code": 21,
            "fragments": [{"area_mm2": LAND, "tile_id": b}],
            "source_cell_id": "smod:b",
            "source_land_area_mm2": LAND,
        },
        {
            "code": 10,
            "fragments": [{"area_mm2": LAND // 2, "tile_id": c}],
            "source_cell_id": "smod:c-valid",
            "source_land_area_mm2": LAND // 2,
        },
        {
            "code": None,
            "fragments": [{"area_mm2": LAND // 2, "tile_id": c}],
            "source_cell_id": "smod:c-nodata",
            "source_land_area_mm2": LAND // 2,
        },
        {
            "code": 21,
            "fragments": [{"area_mm2": 1, "tile_id": d}],
            "source_cell_id": "smod:d-urban",
            "source_land_area_mm2": 1,
        },
        {
            "code": None,
            "fragments": [{"area_mm2": LAND - 1, "tile_id": d}],
            "source_cell_id": "smod:d-nodata",
            "source_land_area_mm2": LAND - 1,
        },
        {
            "code": 10,
            "fragments": [{"area_mm2": LAND, "tile_id": e}],
            "source_cell_id": "smod:e",
            "source_land_area_mm2": LAND,
        },
    ]
    osm_tiles = [
        {
            "coverage_complete": True,
            "grid_max_voltage_v": None,
            "grid_min_distance_mm": None,
            "industrial_union_area_mm2": 9_999_999_999,
            "tile_id": a,
        },
        {
            "coverage_complete": True,
            "grid_max_voltage_v": 110_000,
            "grid_min_distance_mm": 5_000_000,
            "industrial_union_area_mm2": 10_000_000_000,
            "tile_id": b,
        },
        {
            "coverage_complete": False,
            "grid_max_voltage_v": None,
            "grid_min_distance_mm": None,
            "industrial_union_area_mm2": 10_000_000_000,
            "tile_id": c,
        },
        {
            "coverage_complete": False,
            "grid_max_voltage_v": 110_000,
            "grid_min_distance_mm": 5_000_000,
            "industrial_union_area_mm2": 0,
            "tile_id": d,
        },
    ]
    return {
        "built_cells": built_cells,
        "osm_tiles": osm_tiles,
        "smod_cells": smod_cells,
        "tiles": tiles,
    }


def _create_definition(
    root: Path,
    *,
    fixture_only: bool = True,
    rows: dict[str, list[dict[str, object]]] | None = None,
) -> Path:
    inputs = root / "inputs"
    sources = root / "sources"
    inputs.mkdir(parents=True)
    sources.mkdir(parents=True)
    rows = rows or _fixture_rows()
    checkpoints: dict[str, dict[str, object]] = {}
    for role in integration.INPUT_ROLES:
        path = inputs / f"{role}.jsonl"
        _write_jsonl(path, rows[role])
        checkpoints[role] = _file_checkpoint(path, f"../inputs/{path.name}")
    if fixture_only:
        lineage: dict[str, object] = {
            "mode": "synthetic_fixture",
            "production_sources_used": False,
        }
    else:
        source_cache = root / "source_cache"
        source_cache.mkdir()
        natural_earth_path = source_cache / "natural-earth-land.bin"
        natural_earth_path.write_bytes(b"synthetic Natural Earth checkpoint\n")
        lineage = {
            "ghsl_cache_path": "../source_cache/ghsl-r2023a-2020-1km",
            "mode": "frozen_production",
            "natural_earth_artifact": _file_checkpoint(
                natural_earth_path, "../source_cache/natural-earth-land.bin"
            ),
            "osm_derivative_manifest_sha256": "a" * 64,
            "osm_derivative_path": (
                "../source_cache/osm-blind-tile-auxiliary-260713-v3"
            ),
            "production_sources_used": True,
        }
    definition = {
        "algorithm": integration.current_algorithm_checkpoints(),
        "candidate_independent": True,
        "fixture_only": fixture_only,
        "format": integration.DEFINITION_FORMAT,
        "generated_at": FIXED_TIME,
        "input_contract": {
            "area_crs": "EPSG:6933",
            "area_unit": "square_millimetre",
            "canonical_jsonl": True,
            "inputs": checkpoints,
            "source_role_bindings": integration.NORMALIZED_INPUT_SOURCE_BINDINGS,
            "stream_order": list(integration.INPUT_ROLES),
        },
        "production_frame_built": False,
        "release_id": "synthetic-integration-v1",
        "schema_version": 1,
        "semantic_contract": integration.SEMANTIC_CONTRACT,
        "source_lineage": lineage,
    }
    path = sources / "definition.json"
    path.write_bytes(integration.canonical_json(definition))
    return path


def _read_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class BlindTileAuxiliaryIntegrationTests(unittest.TestCase):
    def test_largest_remainder_is_deterministic_and_exactly_conservative(self) -> None:
        fragments = [
            {"area_mm2": 1_000_000, "tile_id": TILES[0]},
            {"area_mm2": 1_000_000, "tile_id": TILES[1]},
            {"area_mm2": 1_000_000, "tile_id": TILES[2]},
        ]
        allocation = integration.allocate_extensive_built_area(
            1, 3_000_000, fragments
        )
        self.assertEqual(
            [row["allocated_area_mm2"] for row in allocation],
            [333_334, 333_333, 333_333],
        )
        self.assertEqual(
            sum(row["allocated_area_mm2"] for row in allocation), 1_000_000
        )
        self.assertFalse(
            integration.SEMANTIC_CONTRACT["built"][
                "bilinear_interpolation_allowed"
            ]
        )

    def test_fixture_build_freezes_exact_bundle_and_preserves_tri_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            result = integration.build_integration_bundle(
                output,
                definition_path=definition,
                work_database_path=root / "work.sqlite3",
                batch_size=2,
                clock=lambda: FIXED_TIME,
            )
            self.assertEqual(result["tile_count"], 5)
            self.assertFalse(result["production_frame_built"])
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
            self.assertEqual(
                {path.name for path in output.iterdir()}, integration.BUNDLE_FILES
            )
            for path in output.iterdir():
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

            rows = {row["tile_id"]: row for row in _read_rows(output / integration.OUTPUT_FILENAME)}
            expected = {
                TILES[0]: (
                    {
                        "built": "true",
                        "grid": "false",
                        "industrial": "false",
                        "smod": "false",
                        "urban": "true",
                    },
                    "urban_built",
                    [],
                ),
                TILES[1]: (
                    {
                        "built": "false",
                        "grid": "true",
                        "industrial": "true",
                        "smod": "true",
                        "urban": "true",
                    },
                    "industrial_and_grid",
                    [],
                ),
                TILES[2]: (
                    {
                        "built": "unknown",
                        "grid": "unknown",
                        "industrial": "true",
                        "smod": "unknown",
                        "urban": "unknown",
                    },
                    "industrial_xor_grid",
                    ["built", "grid", "smod", "urban"],
                ),
                TILES[3]: (
                    {
                        "built": "false",
                        "grid": "true",
                        "industrial": "unknown",
                        "smod": "true",
                        "urban": "true",
                    },
                    "industrial_xor_grid",
                    ["industrial"],
                ),
                TILES[4]: (
                    {
                        "built": "false",
                        "grid": "unknown",
                        "industrial": "unknown",
                        "smod": "false",
                        "urban": "false",
                    },
                    "background",
                    ["grid", "industrial"],
                ),
            }
            for tile, (signals, stratum, unknowns) in expected.items():
                with self.subTest(tile=tile):
                    self.assertEqual(rows[tile]["signals"], signals)
                    self.assertEqual(rows[tile]["stratum_lower_bound"], stratum)
                    self.assertEqual(rows[tile]["unknown_signal_fields"], unknowns)
            coverage = result["coverage"]
            self.assertEqual(coverage["source_built_area_mm2"], 154_000_000)
            self.assertEqual(
                coverage["source_built_area_mm2"],
                coverage["allocated_built_area_mm2"],
            )
            self.assertFalse(coverage["claims"]["production_sample_built"])

    def test_resumed_batches_match_a_fresh_build_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            resumed = root / "resumed"
            database = root / "resume.sqlite3"
            partial = integration.build_integration_bundle(
                resumed,
                definition_path=definition,
                work_database_path=database,
                batch_size=1,
                maximum_batches=2,
                clock=lambda: FIXED_TIME,
            )
            self.assertEqual(partial["state"], "in_progress")
            self.assertFalse(resumed.exists())
            with sqlite3.connect(database) as connection:
                progress = connection.execute(
                    "SELECT row_count,completed FROM progress WHERE role='tiles'"
                ).fetchone()
            self.assertEqual(progress, (2, 0))

            integration.build_integration_bundle(
                resumed,
                definition_path=definition,
                work_database_path=database,
                batch_size=1,
                clock=lambda: FIXED_TIME,
            )
            fresh = root / "fresh"
            integration.build_integration_bundle(
                fresh,
                definition_path=definition,
                work_database_path=root / "fresh.sqlite3",
                batch_size=4,
                clock=lambda: FIXED_TIME,
            )
            self.assertEqual(
                {path.name: path.read_bytes() for path in resumed.iterdir()},
                {path.name: path.read_bytes() for path in fresh.iterdir()},
            )

    def test_partial_database_smod_zero_to_one_tamper_cannot_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            database = root / "resume.sqlite3"
            partial = integration.build_integration_bundle(
                output,
                definition_path=definition,
                work_database_path=database,
                batch_size=100,
                maximum_batches=3,
                clock=lambda: FIXED_TIME,
            )
            self.assertEqual(partial["state"], "in_progress")
            with sqlite3.connect(database) as connection:
                before = connection.execute(
                    "SELECT smod_urban_area_mm2 FROM tiles WHERE tile_id=?",
                    (TILES[4],),
                ).fetchone()
                self.assertEqual(before, (0,))
                connection.execute(
                    "UPDATE tiles SET smod_urban_area_mm2=1 WHERE tile_id=?",
                    (TILES[4],),
                )
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "fresh normalized-stream replay",
            ):
                integration.build_integration_bundle(
                    output,
                    definition_path=definition,
                    work_database_path=database,
                    batch_size=100,
                    clock=lambda: FIXED_TIME,
                )
            self.assertFalse(output.exists())
            self.assertFalse((root / ".bundle.tmp").exists())

    def test_validator_recomputes_semantics_even_after_attacker_rehash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            integration.build_integration_bundle(
                output,
                definition_path=definition,
                work_database_path=root / "work.sqlite3",
                freeze=False,
                clock=lambda: FIXED_TIME,
            )
            output_rows = _read_rows(output / integration.OUTPUT_FILENAME)
            output_rows[0]["ghsl"]["built"]["allocated_area_mm2"] = 0
            _write_jsonl(output / integration.OUTPUT_FILENAME, output_rows)
            manifest_path = output / integration.MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_bytes())
            raw_output = (output / integration.OUTPUT_FILENAME).read_bytes()
            manifest["files"][integration.OUTPUT_FILENAME] = {
                "bytes": len(raw_output),
                "sha256": hashlib.sha256(raw_output).hexdigest(),
            }
            manifest_raw = integration.canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            (output / integration.MANIFEST_SHA_FILENAME).write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {integration.MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "BUILT signal changed",
            ):
                integration.validate_integration_bundle(
                    output,
                    definition_path=definition,
                    require_frozen=False,
                )

    def test_validator_binds_published_conservation_to_source_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            integration.build_integration_bundle(
                output,
                definition_path=definition,
                work_database_path=root / "work.sqlite3",
                freeze=False,
                clock=lambda: FIXED_TIME,
            )
            output_path = output / integration.OUTPUT_FILENAME
            output_rows = _read_rows(output_path)
            output_rows[0]["ghsl"]["built"]["allocated_area_mm2"] += 1_000_000
            _write_jsonl(output_path, output_rows)
            coverage_path = output / integration.COVERAGE_FILENAME
            coverage = json.loads(coverage_path.read_bytes())
            coverage["source_built_area_mm2"] += 1_000_000
            coverage["allocated_built_area_mm2"] += 1_000_000
            coverage_path.write_bytes(integration.canonical_json(coverage))
            manifest_path = output / integration.MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_bytes())
            for name in (integration.OUTPUT_FILENAME, integration.COVERAGE_FILENAME):
                raw = (output / name).read_bytes()
                manifest["files"][name] = {
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            manifest_raw = integration.canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            (output / integration.MANIFEST_SHA_FILENAME).write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {integration.MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "source BUILT total changed",
            ):
                integration.validate_integration_bundle(
                    output,
                    definition_path=definition,
                    require_frozen=False,
                )

    def test_rehashed_source_primitive_redistribution_fails_fresh_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            integration.build_integration_bundle(
                output,
                definition_path=definition,
                work_database_path=root / "work.sqlite3",
                freeze=False,
                clock=lambda: FIXED_TIME,
            )
            output_path = output / integration.OUTPUT_FILENAME
            output_rows = _read_rows(output_path)
            output_rows[0]["ghsl"]["built"]["allocated_area_mm2"] += 1
            output_rows[1]["ghsl"]["built"]["allocated_area_mm2"] -= 1
            _write_jsonl(output_path, output_rows)
            manifest_path = output / integration.MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_bytes())
            raw_output = output_path.read_bytes()
            manifest["files"][integration.OUTPUT_FILENAME] = {
                "bytes": len(raw_output),
                "sha256": hashlib.sha256(raw_output).hexdigest(),
            }
            manifest_raw = integration.canonical_json(manifest)
            manifest_path.write_bytes(manifest_raw)
            (output / integration.MANIFEST_SHA_FILENAME).write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  {integration.MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "fresh normalized-stream replay",
            ):
                integration.validate_integration_bundle(
                    output,
                    definition_path=definition,
                    require_frozen=False,
                )

    def test_candidate_derived_input_path_is_rejected_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            document = json.loads(definition.read_bytes())
            document["input_contract"]["inputs"]["tiles"]["path"] = (
                "../candidate_fusion/tiles.jsonl"
            )
            definition.write_bytes(integration.canonical_json(document))
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "forbidden candidate-derived",
            ):
                integration.load_definition(definition)

    def test_identical_target_symlink_component_in_bound_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            (root / "inputs-alias").symlink_to(
                root / "inputs", target_is_directory=True
            )
            document = json.loads(definition.read_bytes())
            document["input_contract"]["inputs"]["tiles"]["path"] = (
                "../inputs-alias/../inputs/tiles.jsonl"
            )
            definition.write_bytes(integration.canonical_json(document))
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "symlink component",
            ):
                integration.load_definition(definition)

    def test_storage_overlap_hazards_fail_before_sqlite_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            cases = {
                "equal": (root / "equal", root / "equal"),
                "work_inside_output": (
                    root / "output-parent",
                    root / "output-parent" / "state.sqlite3",
                ),
                "output_inside_work": (
                    root / "work-parent" / "bundle",
                    root / "work-parent",
                ),
                "work_equals_sibling_temp": (
                    root / "bundle-temp-equal",
                    root / ".bundle-temp-equal.tmp",
                ),
                "work_inside_sibling_temp": (
                    root / "bundle-temp-parent",
                    root / ".bundle-temp-parent.tmp" / "state.sqlite3",
                ),
                "output_equals_sqlite_journal": (
                    root / "sidecar-journal",
                    root / "sidecar",
                ),
                "output_overlaps_inputs": (
                    root / "inputs",
                    root / "separate.sqlite3",
                ),
                "work_overlaps_inputs": (
                    root / "separate-bundle",
                    root / "inputs",
                ),
            }
            with mock.patch.object(
                integration.sqlite3,
                "connect",
                side_effect=AssertionError("SQLite must not open"),
            ) as connect:
                for label, (output, database) in cases.items():
                    with self.subTest(label=label), self.assertRaisesRegex(
                        integration.BlindTileAuxiliaryIntegrationError,
                        "overlap",
                    ):
                        integration.build_integration_bundle(
                            output,
                            definition_path=definition,
                            work_database_path=database,
                        )
                connect.assert_not_called()

    def test_preexisting_sibling_temp_fails_before_sqlite_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            (root / ".bundle.tmp").mkdir()
            with mock.patch.object(
                integration.sqlite3,
                "connect",
                side_effect=AssertionError("SQLite must not open"),
            ) as connect, self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "before SQLite open",
            ):
                integration.build_integration_bundle(
                    root / "bundle",
                    definition_path=definition,
                    work_database_path=root / "work.sqlite3",
                )
            connect.assert_not_called()

    def test_publication_fsyncs_temp_and_parent_around_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            output = root / "bundle"
            with mock.patch.object(
                integration,
                "_fsync_directory",
                wraps=integration._fsync_directory,
            ) as fsync_directory:
                integration.build_integration_bundle(
                    output,
                    definition_path=definition,
                    work_database_path=root / "work.sqlite3",
                    freeze=False,
                    clock=lambda: FIXED_TIME,
                )
            self.assertEqual(
                [call.args[0] for call in fsync_directory.call_args_list],
                [root / ".bundle.tmp", root, root],
            )

    def test_production_definition_cannot_pass_without_frozen_osm_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root, fixture_only=False)
            with mock.patch.object(
                integration,
                "_validate_frozen_ghsl_cache",
                return_value={"frozen": True},
            ), mock.patch.object(
                integration,
                "_validate_frozen_osm_derivative",
                side_effect=integration.BlindTileAuxiliaryIntegrationError(
                    "OSM derivative unfinished"
                ),
            ) as osm_gate:
                with self.assertRaisesRegex(
                    integration.BlindTileAuxiliaryIntegrationError,
                    "OSM derivative unfinished",
                ):
                    integration.load_definition(definition)
            osm_gate.assert_called_once()
            self.assertFalse((root / "work.sqlite3").exists())

    def test_frozen_osm_gate_uses_v3_geometry_completeness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            derivative = root / integration.OSM_DERIVATIVE_BASENAME
            derivative.mkdir()
            manifest = derivative / "extract-manifest.json"
            manifest.write_bytes(b"v3 manifest fixture\n")
            expected_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            document = {
                "downstream_contract": {
                    "bounded_unresolved_geometry": "incomplete_unknown"
                },
                "selection_statistics": {
                    "final": {
                        "selected_objects": 2_271_693,
                        "unresolved_geometry_objects": 20,
                        "unresolved_with_bounds": 18,
                        "unresolved_without_bounds": 2,
                    }
                },
            }
            with mock.patch(
                "datacenter_atlas.osm_blind_tile_auxiliary_v3.validate_bundle",
                return_value=document,
            ) as validate:
                result = integration._validate_frozen_osm_derivative(
                    derivative, expected_digest
                )
            validate.assert_called_once_with(derivative, deep_source_hash=False)
            self.assertEqual(result["selected_objects"], 2_271_693)
            self.assertEqual(result["unresolved_geometry_objects"], 20)
            self.assertEqual(result["unresolved_with_bounds"], 18)
            self.assertEqual(result["unresolved_without_bounds"], 2)
            self.assertEqual(
                result["downstream_contract"],
                {"bounded_unresolved_geometry": "incomplete_unknown"},
            )

    def test_production_build_is_disabled_without_bound_geometry_producer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root, fixture_only=False)
            with mock.patch.object(
                integration,
                "_validate_frozen_ghsl_cache",
                return_value={"frozen": True},
            ), mock.patch.object(
                integration,
                "_validate_frozen_osm_derivative",
                return_value={"frozen": True},
            ):
                with self.assertRaisesRegex(
                    integration.BlindTileAuxiliaryIntegrationError,
                    "production normalized geometry producer bytes",
                ):
                    integration.build_integration_bundle(
                        root / "bundle",
                        definition_path=definition,
                        work_database_path=root / "work.sqlite3",
                    )
            self.assertFalse((root / "work.sqlite3").exists())
            self.assertFalse((root / "bundle").exists())

    def test_naive_definition_timestamp_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            definition = _create_definition(root)
            document = json.loads(definition.read_bytes())
            document["generated_at"] = "2026-07-19T12:00:00"
            definition.write_bytes(integration.canonical_json(document))
            with self.assertRaisesRegex(
                integration.BlindTileAuxiliaryIntegrationError,
                "canonical UTC",
            ):
                integration.load_definition(definition)


if __name__ == "__main__":
    unittest.main()
