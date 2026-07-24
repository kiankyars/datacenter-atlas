from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, date, datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from datacenter_atlas.adapters import ImportResult
from datacenter_atlas.global_snapshot import (
    DEFAULT_MAP_GENERATOR,
    GlobalSnapshotError,
    _add_manifest_file,
    _assert_database_cutoffs,
    build_global_snapshot,
    global_release_readme,
    planet_import_provenance,
    validate_release_files,
)
from datacenter_atlas.natural_earth import EnrichmentResult
from datacenter_atlas.database import initialize
from datacenter_atlas.models import Evidence, EvidenceKind
from datacenter_atlas.repository import add_evidence


class GlobalSnapshotTests(unittest.TestCase):
    def _run_fixture_build(
        self,
        root: Path,
        *,
        map_generator: Path = DEFAULT_MAP_GENERATOR,
        as_of: str = "2026-07-18",
        recorded_at: str = "2026-07-18T19:00:00Z",
        osm_exact_total: int = 3,
        osm_element_timestamp: str | None = None,
        adapter_results: dict[str, ImportResult] | None = None,
        country_result: EnrichmentResult | None = None,
    ) -> dict[str, object]:
        materialized = root / "materialized"
        materialized.mkdir()
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "osm_minimal.json").read_text()
        )
        fixture["elements"] = fixture["elements"][:3]
        if osm_element_timestamp is not None:
            fixture["elements"][0]["timestamp"] = osm_element_timestamp
        overpass_raw = (
            json.dumps(fixture, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        (materialized / "overpass.json").write_bytes(overpass_raw)
        materialization = {
            "schema_version": 1,
            "pipeline": "openstreetmap_planet_materialize",
            "state": "completed",
            "materialized_at": "2026-07-18T18:30:00Z",
            "source_retrieved_at": "2026-07-18T18:15:02Z",
            "snapshot_date": "2026-07-13",
            "inputs": {
                "extraction_manifest": {
                    "bytes": 100,
                    "sha256": "a" * 64,
                    "pipeline": "openstreetmap_planet_extract",
                    "schema_version": 1,
                },
                "filtered_pbf": {
                    "bytes": 200,
                    "md5": "b" * 32,
                    "sha256": "c" * 64,
                },
                "planet_source": {
                    "url": "https://planet.openstreetmap.org/pbf/planet-260713.osm.pbf",
                    "snapshot_date": "2026-07-13",
                    "bytes": 300,
                    "md5": "d" * 32,
                    "sha256": "e" * 64,
                },
            },
            "outputs": {
                "overpass_json": {
                    "path": "overpass.json",
                    "bytes": len(overpass_raw),
                    "sha256": hashlib.sha256(overpass_raw).hexdigest(),
                }
            },
            "transform": {
                "selection": "exact_tag_pairs_only",
                "tag_filter_sha256": "1" * 64,
                "tag_pair_count": 92,
                "references_required": True,
            },
            "rights": {"license": "ODbL-1.0"},
            "counts": {
                "exact_match_counts": {"total": osm_exact_total},
                "geometry_unavailable_count": 0,
                "relation_geometry_unresolved_count": 0,
                "all_exact_matches_emitted_once": True,
            },
        }
        (materialized / "manifest.json").write_text(
            json.dumps(materialization), encoding="utf-8"
        )

        source_directories = {}
        for name, fetched_at in (
            ("pnnl", "2026-07-17T19:44:14Z"),
            ("uva", "2026-07-18T18:20:00Z"),
            ("natural-earth", "2026-07-18T18:07:00Z"),
        ):
            directory = root / name
            directory.mkdir()
            (directory / "manifest.json").write_text(
                json.dumps({"fetched_at": fetched_at}), encoding="utf-8"
            )
            source_directories[name] = directory
        wikidata = root / "wikidata"
        wikidata.mkdir()

        empty_import = ImportResult(source="fixture")
        adapter_results = adapter_results or {}
        wikidata_view = SimpleNamespace(
            manifest={
                "retrieved_completed_at": "2026-07-18T18:04:01Z",
                "candidate_qids": {"count": 0},
            }
        )
        country_result = country_result or EnrichmentResult(0, 0, 0, 0, 0, 0, 0, 0)
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "datacenter_atlas.global_snapshot.materialize_planet_extract",
                    return_value=materialization,
                )
            )
            stack.enter_context(
                patch(
                    "datacenter_atlas.global_snapshot.validate_wikidata_bundle",
                    return_value=wikidata_view,
                )
            )
            for adapter_name in (
                "PNNLIM3GeoPackageAdapter",
                "WikidataAdapter",
                "UVADataverseAdapter",
            ):
                adapter = stack.enter_context(
                    patch(f"datacenter_atlas.global_snapshot.{adapter_name}")
                )
                adapter.return_value.import_file.return_value = adapter_results.get(
                    adapter_name, empty_import
                )
            stack.enter_context(
                patch(
                    "datacenter_atlas.global_snapshot.enrich_administrative_assignments",
                    return_value=country_result,
                )
            )
            stack.enter_context(
                patch("datacenter_atlas.global_snapshot.PNNL_EXPECTED_SOURCE_ROWS", 0)
            )
            stack.enter_context(
                patch("datacenter_atlas.global_snapshot.PNNL_EXPECTED_CANDIDATES", 0)
            )
            stack.enter_context(
                patch("datacenter_atlas.global_snapshot.PNNL_EXPECTED_DUPLICATE_ROWS", 0)
            )
            stack.enter_context(
                patch("datacenter_atlas.global_snapshot.UVA_EXPECTED_ROWS", 0)
            )
            return build_global_snapshot(
                extraction_manifest=root / "extract-manifest.json",
                osm_materialization=materialized,
                pnnl_input=source_directories["pnnl"],
                pnnl_retrieved_at=None,
                wikidata_input=wikidata,
                uva_input=source_directories["uva"],
                natural_earth_input=source_directories["natural-earth"],
                output_directory=root / "release",
                as_of=as_of,
                recorded_at=recorded_at,
                map_generator=map_generator,
            )

    def test_planet_provenance_is_compact_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "schema_version": 1,
                "pipeline": "openstreetmap_planet_materialize",
                "materialized_at": "2026-07-18T19:00:00Z",
                "inputs": {
                    "extraction_manifest": {
                        "bytes": 100,
                        "sha256": "a" * 64,
                        "pipeline": "openstreetmap_planet_extract",
                        "schema_version": 1,
                    },
                    "filtered_pbf": {
                        "bytes": 200,
                        "md5": "b" * 32,
                        "sha256": "c" * 64,
                    },
                    "planet_source": {
                        "url": "https://planet.openstreetmap.org/pbf/planet-260713.osm.pbf",
                        "snapshot_date": "2026-07-13",
                        "bytes": 300,
                        "md5": "d" * 32,
                        "sha256": "e" * 64,
                    },
                },
                "outputs": {
                    "overpass_json": {
                        "path": "overpass.json",
                        "bytes": 400,
                        "sha256": "f" * 64,
                    }
                },
                "transform": {
                    "selection": "exact_tag_pairs_only",
                    "tag_filter_sha256": "1" * 64,
                    "tag_pair_count": 92,
                    "references_required": True,
                },
                "rights": {"license": "ODbL-1.0"},
                "counts": {
                    "exact_match_counts": {"total": 7},
                    "geometry_unavailable_count": 1,
                    "relation_geometry_unresolved_count": 2,
                    "all_exact_matches_emitted_once": True,
                },
            }
            raw = json.dumps(manifest, indent=2).encode()
            (root / "manifest.json").write_bytes(raw)
            provenance = planet_import_provenance(root, manifest)

        self.assertEqual(provenance["input_sha256"], "f" * 64)
        self.assertEqual(
            provenance["materialization_manifest"]["sha256"],
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(provenance["selection"]["tag_pair_count"], 92)
        self.assertEqual(
            provenance["integrity_counts"]["exact_match_counts"]["total"], 7
        )
        self.assertNotIn("path", provenance["planet_source"])

    def test_global_readme_labels_scope_and_rights(self) -> None:
        readme = global_release_readme(
            as_of="2026-07-18",
            osm_snapshot_date="2026-07-13",
            osm_integrity={
                "exact_match_counts": {"total": 75},
                "geometry_unavailable_count": 2,
                "relation_geometry_unresolved_count": 1,
            },
            summary={
                "entities_total": 100,
                "entities_with_coordinates": 90,
                "construction_source_signals": 2,
                "entities_by_status": {
                    "under_construction": 4,
                    "unknown": 96,
                },
            },
        )
        self.assertIn("100 source-scoped records", readme)
        self.assertIn("4 entity rows in the active/pre-construction view", readme)
        self.assertIn("2 distinct lifecycle evidence/source observations", readme)
        self.assertIn("not cross-source deduplication", readme)
        self.assertIn("neither number is a count of unique physical sites", readme)
        self.assertIn("construction_source_signals.csv", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)
        self.assertIn("OpenStreetMap planet", readme)
        self.assertIn("all 75 exact matches", readme)
        self.assertIn("2 retained matches", readme)
        self.assertIn("ODbL", readme)
        self.assertIn("Scrutica is published separately", readme)

    def test_release_file_validation_detects_tampering_and_unlisted_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = b"release payload"
            (root / "data.txt").write_bytes(payload)
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "files": {
                            "data.txt": {
                                "bytes": len(payload),
                                "sha256": hashlib.sha256(payload).hexdigest(),
                            }
                        }
                    }
                )
            )
            validate_release_files(root)
            (root / "unlisted.txt").write_text("unexpected")
            with self.assertRaisesRegex(GlobalSnapshotError, "file set"):
                validate_release_files(root)
            (root / "unlisted.txt").unlink()
            (root / "data.txt").write_text("changed")
            with self.assertRaisesRegex(GlobalSnapshotError, "hash mismatch"):
                validate_release_files(root)

    def test_binary_file_can_be_added_to_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text('{"files": {}}')
            (root / "atlas.sqlite").write_bytes(b"sqlite fixture")
            _add_manifest_file(root, "atlas.sqlite")
            manifest = validate_release_files(root)
        self.assertEqual(manifest["files"]["atlas.sqlite"]["bytes"], 14)

    def test_full_builder_publishes_atomic_hashed_database_and_map(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._run_fixture_build(root)
            release = root / "release"
            manifest = validate_release_files(release)
            self.assertTrue((release / "atlas.sqlite").is_file())
            self.assertTrue((release / "atlas.html").is_file())
            self.assertIn("atlas.sqlite", manifest["files"])
            self.assertIn("atlas.html", manifest["files"])
            self.assertEqual(
                result["sources"]["openstreetmap_planet"]["imported_elements"], 3
            )

    def test_builder_canonicalizes_equivalent_recorded_at_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._run_fixture_build(
                root,
                recorded_at="2026-07-18T20:00:00.000+01:00",
            )
            manifest = validate_release_files(root / "release")
            self.assertEqual(manifest["recorded_at"], "2026-07-18T19:00:00Z")

    def test_builder_rejects_fractional_recorded_at_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(GlobalSnapshotError, "whole-second precision"):
                self._run_fixture_build(
                    root,
                    recorded_at="2026-07-18T19:00:00.5Z",
                )
            self.assertFalse((root / "release").exists())

    def test_successful_generator_without_map_cleans_atomic_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            empty_generator = root / "empty_generator.py"
            empty_generator.write_text("# intentionally creates no output\n")
            with self.assertRaisesRegex(GlobalSnapshotError, "atlas.html"):
                self._run_fixture_build(root, map_generator=empty_generator)
            self.assertFalse((root / "release").exists())
            self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_temporal_gates_reject_future_observations_and_retrievals(self) -> None:
        cases = (
            (
                "future OSM snapshot",
                {"as_of": "2026-07-12"},
                "OSM snapshot date is later than as_of",
            ),
            (
                "future imported source observation",
                {"as_of": "2026-07-13"},
                "as_of precedes imported source observations",
            ),
            (
                "future imported claim hidden behind an older source snapshot",
                {"osm_element_timestamp": "2026-07-19T00:00:00Z"},
                "database contains imported observations later than as_of",
            ),
            (
                "future source retrieval",
                {"recorded_at": "2026-07-18T18:10:00Z"},
                "recorded_at precedes source retrievals",
            ),
        )
        for label, arguments, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.assertRaisesRegex(GlobalSnapshotError, expected_error):
                    self._run_fixture_build(root, **arguments)
                self.assertFalse((root / "release").exists())
                self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_every_import_lane_is_count_reconciled_before_release(self) -> None:
        cases = (
            (
                "OpenStreetMap",
                {"osm_exact_total": 4},
                "OpenStreetMap import counts",
            ),
            (
                "PNNL/IM3",
                {
                    "adapter_results": {
                        "PNNLIM3GeoPackageAdapter": ImportResult(
                            source="fixture", examined_elements=1
                        )
                    }
                },
                "PNNL/IM3 import counts",
            ),
            (
                "Wikidata",
                {
                    "adapter_results": {
                        "WikidataAdapter": ImportResult(
                            source="fixture", examined_elements=1
                        )
                    }
                },
                "Wikidata import counts",
            ),
            (
                "UVA DC-SENSE",
                {
                    "adapter_results": {
                        "UVADataverseAdapter": ImportResult(
                            source="fixture", examined_elements=1
                        )
                    }
                },
                "UVA DC-SENSE import counts",
            ),
            (
                "Natural Earth",
                {"country_result": EnrichmentResult(1, 0, 0, 0, 1, 0, 0, 0)},
                "one assignment result per examined snapshot",
            ),
        )
        for label, arguments, expected_error in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with self.assertRaisesRegex(GlobalSnapshotError, expected_error):
                    self._run_fixture_build(root, **arguments)
                self.assertFalse((root / "release").exists())
                self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_database_cutoff_checks_evidence_retrieval_time(self) -> None:
        connection, _ = initialize(":memory:")
        try:
            add_evidence(
                connection,
                Evidence(
                    id="future-evidence",
                    kind=EvidenceKind.OTHER,
                    title="Future evidence fixture",
                    source_url="https://example.test/future",
                    retrieved_at="2026-07-18T20:00:00Z",
                ),
            )
            with self.assertRaisesRegex(
                GlobalSnapshotError, "retrieval times later than recorded_at"
            ):
                _assert_database_cutoffs(
                    connection,
                    as_of=date(2026, 7, 18),
                    recorded_at=datetime(2026, 7, 18, 19, tzinfo=UTC),
                )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
