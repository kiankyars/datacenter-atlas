from __future__ import annotations

from hashlib import md5, sha256
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from datacenter_atlas import osm_blind_tile_auxiliary_v3 as auxiliary


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "osm_blind_tile_auxiliary_v3_minimal.osm"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _checkpoint(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "path": path.name, "sha256": sha256(raw).hexdigest()}


def _freeze(root: Path) -> None:
    for path in root.iterdir():
        path.chmod(0o444)
    root.chmod(0o555)


def _resign(root: Path, manifest: dict) -> None:
    manifest_path = root / auxiliary.MANIFEST_FILENAME
    sidecar = root / auxiliary.MANIFEST_SHA_FILENAME
    root.chmod(0o755)
    manifest_path.chmod(0o644)
    sidecar.chmod(0o644)
    raw = auxiliary.canonical_json(manifest)
    manifest_path.write_bytes(raw)
    sidecar.write_text(
        f"{sha256(raw).hexdigest()}  {auxiliary.MANIFEST_FILENAME}\n",
        encoding="ascii",
    )
    _freeze(root)


class OsmBlindTileAuxiliaryV3UnitTests(unittest.TestCase):
    def test_preselection_defers_all_direct_way_roles_to_libosmium(self) -> None:
        root = ET.parse(FIXTURE).getroot()
        elements = {
            (element.tag, int(element.attrib["id"])): element
            for element in root
            if element.tag in {"node", "way", "relation"}
        }
        area_no, _ = auxiliary.classify_element(elements[("way", 101)])
        empty, _ = auxiliary.classify_element(elements[("relation", 201)])
        inner_only, _ = auxiliary.classify_element(elements[("relation", 202)])
        nested, _ = auxiliary.classify_element(elements[("relation", 203)])
        blank_role, _ = auxiliary.classify_element(elements[("relation", 204)])
        other_role, _ = auxiliary.classify_element(elements[("relation", 205)])
        self.assertEqual(area_no["geometry_preselection_reason"], "explicit_area_no")
        self.assertEqual(area_no["accepted_preexport_signals"], ["grid"])
        self.assertEqual(empty["geometry_preselection_reason"], "relation_empty")
        self.assertEqual(empty["accepted_preexport_signals"], [])
        self.assertIsNone(inner_only["geometry_preselection_reason"])
        self.assertEqual(inner_only["accepted_preexport_signals"], ["industrial"])
        self.assertIsNone(blank_role["geometry_preselection_reason"])
        self.assertEqual(blank_role["accepted_preexport_signals"], ["industrial"])
        self.assertIsNone(other_role["geometry_preselection_reason"])
        self.assertEqual(other_role["accepted_preexport_signals"], ["industrial"])
        self.assertEqual(
            nested["geometry_preselection_reason"],
            "relation_no_direct_way_member",
        )
        self.assertEqual(nested["accepted_preexport_signals"], [])
        geometry_contract = auxiliary.filter_contract_document()["geometry_v3"]
        self.assertTrue(
            geometry_contract[
                "relation_member_roles_deferred_to_pinned_polygon_exporter"
            ]
        )

    def test_stream_scan_preserves_grid_and_records_structural_rejections(self) -> None:
        root = ET.parse(FIXTURE).getroot()
        broad = ET.Element("osm", {"version": "0.6"})
        broad_ids = {
            20,
            100,
            101,
            102,
            103,
            104,
            105,
            200,
            201,
            202,
            203,
            204,
            205,
        }
        for element in root:
            if element.tag in {"node", "way", "relation"} and int(
                element.attrib["id"]
            ) in broad_ids:
                broad.append(element)
        ids = io.StringIO()
        ledger = io.StringIO()
        industrial = io.StringIO()
        statistics = auxiliary.scan_osm_xml(
            io.BytesIO(ET.tostring(broad)), ids, ledger, industrial
        )
        self.assertEqual(
            ids.getvalue(),
            "n20\nw100\nw101\nw102\nw103\nw104\nw105\nr200\nr201\nr202\nr203\nr204\nr205\n",
        )
        self.assertEqual(
            industrial.getvalue(), "w100\nw102\nr200\nr202\nr204\nr205\n"
        )
        self.assertEqual(statistics["preselection_industrial_rejected"], 4)
        self.assertEqual(statistics["preselection_explicit_area_no"], 2)
        self.assertEqual(statistics["preselection_relation_empty"], 1)
        self.assertEqual(
            statistics["preselection_relation_no_direct_way_member"], 1
        )

    def test_candidate_derived_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            auxiliary.OsmBlindTileAuxiliaryV3Error, "forbidden candidate-derived"
        ):
            auxiliary.build_plan(
                "/tmp/candidate_fusion/planet-260713.osm.pbf",
                "/tmp/candidate_fusion/fetch-manifest.json",
                "/tmp/output-v3",
            )

    def test_downstream_contract_is_fail_closed(self) -> None:
        contract = auxiliary.DOWNSTREAM_CONTRACT
        self.assertIn("incomplete/unknown", contract["bounded_unresolved"])
        self.assertIn("establishes no tile fact", contract["null_bounds_unresolved"])
        self.assertFalse(contract["candidate_or_atlas_input_used"])


@unittest.skipUnless(shutil.which("osmium"), "osmium-tool is not installed")
class OsmBlindTileAuxiliaryV3PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        source_directory = cls.root / "source"
        source_directory.mkdir()
        cls.source = source_directory / "planet-260713.osm.pbf"
        subprocess.run(
            ["osmium", "cat", "--output", str(cls.source), str(FIXTURE)],
            check=True,
        )
        raw = cls.source.read_bytes()
        cls.expected_bytes = len(raw)
        cls.expected_md5 = md5(raw).hexdigest()
        cls.expected_sha256 = sha256(raw).hexdigest()
        cls.fetch_manifest = source_directory / "fetch-manifest.json"
        fetch_document = {
            "input": {
                "bytes": len(raw),
                "md5": cls.expected_md5,
                "path": cls.source.name,
                "sha256": cls.expected_sha256,
            },
            "pipeline": "openstreetmap_planet_fetch",
            "rights": {
                "attribution": auxiliary.v1.OSM_ATTRIBUTION,
                "copyright_url": auxiliary.v1.OSM_COPYRIGHT_URL,
                "license": auxiliary.v1.OSM_LICENSE,
            },
            "schema_version": 1,
            "snapshot_date": auxiliary.v1.PLANET_SNAPSHOT_DATE,
            "state": "completed",
            "verification": {
                "exact_size": True,
                "official_md5": True,
                "verified_before_extraction": True,
            },
        }
        cls.fetch_manifest.write_bytes(auxiliary.canonical_json(fetch_document))
        cls.fetch_manifest_sha256 = sha256(cls.fetch_manifest.read_bytes()).hexdigest()
        cls.output = cls.root / "output"
        cls.document = auxiliary.extract_auxiliary(
            cls.source,
            cls.fetch_manifest,
            cls.output,
            osmium_executable=auxiliary.resolve_osmium(),
            expected_bytes=cls.expected_bytes,
            expected_md5=cls.expected_md5,
            expected_sha256=cls.expected_sha256,
            expected_fetch_manifest_sha256=cls.fetch_manifest_sha256,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def _validate(self, output: Path | None = None) -> dict:
        return auxiliary.validate_bundle(
            output or self.output,
            source_path=self.source,
            fetch_manifest_path=self.fetch_manifest,
            osmium_executable=auxiliary.resolve_osmium(),
            expected_bytes=self.expected_bytes,
            expected_md5=self.expected_md5,
            expected_sha256=self.expected_sha256,
            expected_fetch_manifest_sha256=self.fetch_manifest_sha256,
        )

    def test_fixture_pipeline_is_geometry_complete_and_offline_reproducible(self) -> None:
        final = self.document["selection_statistics"]["final"]
        self.assertEqual(final["selected_objects"], 9)
        self.assertEqual(final["selected_industrial"], 5)
        self.assertEqual(final["selected_grid"], 4)
        self.assertEqual(final["unresolved_geometry_objects"], 5)
        self.assertEqual(final["preselection_geometry_rejections"], 4)
        self.assertEqual(final["polygon_export_unresolved"], 1)
        self.assertEqual(final["unresolved_with_bounds"], 4)
        self.assertEqual(final["unresolved_without_bounds"], 1)
        completeness = self.document["geometry_completeness"]
        self.assertEqual(completeness["initial_expected_industrial"], 6)
        self.assertEqual(completeness["initial_exported_industrial"], 5)
        self.assertEqual(completeness["initial_missing_industrial"], 1)
        self.assertTrue(completeness["final_stop_on_error_passed"])
        self.assertEqual(self._validate(), self.document)

    def test_unresolved_ledger_encodes_bounded_and_null_tile_contracts(self) -> None:
        records = {
            row["source_reference"]: row
            for row in _rows(self.output / auxiliary.UNRESOLVED_FILENAME)
        }
        self.assertEqual(
            set(records), {"w101", "w102", "w105", "r201", "r203"}
        )
        self.assertEqual(records["w101"]["reason"], "explicit_area_no")
        self.assertEqual(records["w101"]["accepted_signals"], ["grid"])
        self.assertEqual(
            records["w101"]["downstream_coverage"],
            auxiliary.BOUNDED_DOWNSTREAM_TREATMENT,
        )
        self.assertEqual(
            records["r201"]["location"],
            {
                "bounds_wgs84": None,
                "geometry_invented": False,
                "method": "unavailable_no_referenced_nodes",
            },
        )
        self.assertEqual(
            records["r201"]["downstream_coverage"],
            auxiliary.UNLOCATED_DOWNSTREAM_TREATMENT,
        )
        self.assertFalse(records["r201"]["downstream_coverage"]["tile_fact_established"])

    def test_grid_point_line_polygon_and_mixed_signal_are_preserved(self) -> None:
        records = {
            f"{auxiliary.TYPE_LETTERS[row['osm_type']]}{row['osm_id']}": row
            for row in _rows(self.output / auxiliary.LEDGER_FILENAME)
        }
        self.assertEqual(records["n20"]["signals"], ["grid"])
        self.assertEqual(records["w103"]["signals"], ["grid"])
        self.assertEqual(records["w104"]["signals"], ["grid"])
        self.assertEqual(records["w101"]["signals"], ["grid"])
        self.assertEqual(
            records["w101"]["geometry_status"],
            "grid_preserved_industrial_unresolved",
        )
        for reference in ("r200", "r202", "r204", "r205"):
            self.assertEqual(records[reference]["signals"], ["industrial"])
            self.assertEqual(
                records[reference]["geometry_status"],
                "polygon_export_verified",
            )
        exported = subprocess.run(
            [
                "osmium",
                "export",
                "--no-progress",
                "--add-unique-id=type_id",
                "--output-format=geojsonseq",
                str(self.output / auxiliary.OUTPUT_PBF_FILENAME),
            ],
            check=True,
            capture_output=True,
        ).stdout
        features = [
            json.loads(line[1:])
            for line in exported.splitlines()
            if line.startswith(b"\x1e")
        ]
        geometry_types = {feature["id"]: feature["geometry"]["type"] for feature in features}
        self.assertEqual(geometry_types["n20"], "Point")
        self.assertEqual(geometry_types["w101"], "LineString")
        self.assertEqual(geometry_types["w103"], "LineString")
        self.assertIn(geometry_types["a208"], {"Polygon", "MultiPolygon"})

    def test_frozen_modes_and_closed_tree(self) -> None:
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o555)
        self.assertEqual({path.name for path in self.output.iterdir()}, auxiliary.OUTPUT_NAMES)
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o444 for path in self.output.iterdir())
        )
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            copied.chmod(0o755)
            (copied / "extra.txt").write_text("unexpected\n", encoding="utf-8")
            copied.chmod(0o555)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "inventory is not closed"
            ):
                self._validate(copied)

    def test_recomputed_unresolved_tamper_fails_semantically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            copied.chmod(0o755)
            unresolved = copied / auxiliary.UNRESOLVED_FILENAME
            unresolved.chmod(0o644)
            rows = _rows(unresolved)
            rows[0]["downstream_coverage"]["industrial_coverage"] = "false"
            unresolved.write_bytes(
                b"".join(
                    auxiliary.canonical_json_line(row).encode("utf-8") for row in rows
                )
            )
            manifest_path = copied / auxiliary.MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["outputs"]["unresolved_geometry"] = _checkpoint(unresolved)
            _resign(copied, manifest)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error,
                "downstream contract is invalid",
            ):
                self._validate(copied)

    def test_recomputed_manifest_extra_key_fails_exact_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            manifest = json.loads(
                (copied / auxiliary.MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            manifest["extra"] = False
            _resign(copied, manifest)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "top-level schema"
            ):
                self._validate(copied)

    def test_recomputed_processor_lineage_tamper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            manifest = json.loads(
                (copied / auxiliary.MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            first = next(iter(manifest["processor"]["files"]))
            manifest["processor"]["files"][first]["sha256"] = "0" * 64
            _resign(copied, manifest)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "lineage changed"
            ):
                self._validate(copied)

    def test_recomputed_selection_signal_tamper_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            copied.chmod(0o755)
            ledger = copied / auxiliary.LEDGER_FILENAME
            ledger.chmod(0o644)
            rows = _rows(ledger)
            mixed = next(row for row in rows if row["osm_id"] == 101)
            mixed["signals"] = ["industrial"]
            ledger.write_bytes(
                b"".join(
                    auxiliary.canonical_json_line(row).encode("utf-8") for row in rows
                )
            )
            manifest = json.loads(
                (copied / auxiliary.MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            manifest["outputs"]["selection_ledger"] = _checkpoint(ledger)
            _resign(copied, manifest)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error,
                "industrial selection lacks polygon verification",
            ):
                self._validate(copied)

    def test_sidecar_and_symlink_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "sidecar"
            shutil.copytree(self.output, copied)
            sidecar = copied / auxiliary.MANIFEST_SHA_FILENAME
            sidecar.chmod(0o644)
            sidecar.write_text(
                f"{'0' * 64}  {auxiliary.MANIFEST_FILENAME}\n", encoding="ascii"
            )
            sidecar.chmod(0o444)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "sidecar mismatch"
            ):
                self._validate(copied)

            linked = Path(temporary) / "linked"
            shutil.copytree(self.output, linked)
            linked.chmod(0o755)
            target = linked / auxiliary.IDS_FILENAME
            target.unlink()
            target.symlink_to(self.source)
            linked.chmod(0o555)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "must not be a symlink"
            ):
                self._validate(linked)

    def test_mode_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "copied"
            shutil.copytree(self.output, copied)
            target = copied / auxiliary.IDS_FILENAME
            target.chmod(0o644)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "mode must be 0444"
            ):
                self._validate(copied)

    def test_forced_prepublish_validation_failure_publishes_nothing(self) -> None:
        output = self.root / "forced-failure"
        with mock.patch.object(
            auxiliary,
            "validate_bundle",
            side_effect=auxiliary.OsmBlindTileAuxiliaryV3Error("forced validation failure"),
        ):
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryV3Error, "forced validation failure"
            ):
                auxiliary.extract_auxiliary(
                    self.source,
                    self.fetch_manifest,
                    output,
                    osmium_executable=auxiliary.resolve_osmium(),
                    expected_bytes=self.expected_bytes,
                    expected_md5=self.expected_md5,
                    expected_sha256=self.expected_sha256,
                    expected_fetch_manifest_sha256=self.fetch_manifest_sha256,
                )
        self.assertFalse(output.exists())
        self.assertFalse(output.is_symlink())


if __name__ == "__main__":
    unittest.main()
