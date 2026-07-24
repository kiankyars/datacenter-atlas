from __future__ import annotations

from hashlib import md5, sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from datacenter_atlas import osm_blind_tile_auxiliary as auxiliary


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "osm_blind_tile_auxiliary_minimal.osm"


class OsmBlindTileAuxiliaryTests(unittest.TestCase):
    def test_voltage_parser_is_strict_and_uses_osm_volts_convention(self) -> None:
        self.assertEqual(auxiliary.parse_voltage_token("110000"), 110_000)
        self.assertEqual(auxiliary.parse_voltage_token("110 kV"), 110_000)
        self.assertEqual(auxiliary.parse_voltage_token("110.5kv"), 110_500)
        self.assertEqual(auxiliary.parse_voltage_token("380"), 380)
        self.assertIsNone(auxiliary.parse_voltage_token("110-220 kV"))
        self.assertIsNone(auxiliary.parse_voltage_token("unknown"))
        self.assertEqual(
            auxiliary.parsed_voltages(
                {"voltage": "33000;110000", "voltage:primary": "220 kV"}
            ),
            (33_000, 110_000, 220_000),
        )

    def test_candidate_and_lifecycle_exclusions_are_tag_only(self) -> None:
        self.assertTrue(auxiliary.has_data_center_identity({"name": "West Data Centre"}))
        self.assertTrue(auxiliary.has_data_center_identity({"amenity": "data_center"}))
        self.assertTrue(auxiliary.has_data_center_identity({"site": "server_farm"}))
        self.assertTrue(auxiliary.has_data_center_identity({"name": "West Server Farm"}))
        self.assertTrue(auxiliary.has_data_center_identity({"name": "West Serverfarm"}))
        for localized_name in (
            "Centro de Datos Norte",
            "Rechenzentrum Frankfurt",
            "Центр обработки данных Север",
            "مركز بيانات الرياض",
            "東京データセンター",
            "मुंबई डेटा सेंटर",
            "北京数据中心",
        ):
            with self.subTest(localized_name=localized_name):
                self.assertTrue(
                    auxiliary.has_data_center_identity({"name": localized_name})
                )
        self.assertFalse(auxiliary.has_data_center_identity({"name": "West Industrial Park"}))
        self.assertTrue(auxiliary.has_unstable_lifecycle({"construction": "yes"}))
        self.assertTrue(auxiliary.has_unstable_lifecycle({"disused:power": "substation"}))
        self.assertTrue(auxiliary.has_unstable_lifecycle({"status": "planned"}))
        self.assertFalse(auxiliary.has_unstable_lifecycle({"construction": "no"}))
        exclusion = auxiliary.filter_contract_document()["data_center_exclusion"]
        self.assertFalse(exclusion["localized_name_exclusion_complete"])
        self.assertTrue(exclusion["residual_unlisted_language_or_synonym_leakage_is_blocker"])

    def test_stream_selector_is_ordered_and_excludes_dc_low_voltage_and_construction(self) -> None:
        ids = io.StringIO()
        ledger = io.StringIO()
        fixture_root = ET.parse(FIXTURE).getroot()
        broad_ids = {20, 100, 101, 102, 103, 104, 105, 107, 108, 200}
        broad_root = ET.Element("osm", {"version": "0.6"})
        for element in fixture_root:
            if element.tag in {"node", "way", "relation"} and int(
                element.attrib["id"]
            ) in broad_ids:
                broad_root.append(element)
        statistics = auxiliary.scan_osm_xml(
            io.BytesIO(ET.tostring(broad_root)), ids, ledger
        )
        self.assertEqual(ids.getvalue(), "n20\nw100\nw102\nw105\nr200\n")
        records = [json.loads(line) for line in ledger.getvalue().splitlines()]
        self.assertEqual(
            [(row["osm_type"], row["osm_id"], row["signals"]) for row in records],
            [
                ("node", 20, ["grid"]),
                ("way", 100, ["industrial"]),
                ("way", 102, ["grid"]),
                ("way", 105, ["industrial", "grid"]),
                ("relation", 200, ["industrial"]),
            ],
        )
        self.assertEqual(statistics["selected_objects"], 5)
        self.assertEqual(statistics["excluded_data_center_identity"], 2)
        self.assertEqual(statistics["excluded_unstable_lifecycle"], 1)
        self.assertEqual(statistics["grid_without_parsed_110kv"], 2)

    def test_input_paths_reject_candidate_derived_segments(self) -> None:
        with self.assertRaisesRegex(
            auxiliary.OsmBlindTileAuxiliaryError, "forbidden candidate-derived"
        ):
            auxiliary.build_plan(
                "/tmp/candidate_fusion/planet-260713.osm.pbf",
                "/tmp/candidate_fusion/fetch-manifest.json",
                "/tmp/output",
            )

    def test_planet_scan_invokes_stream_selector_exactly_once(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(b"<osm version='0.6'/>")
                self.wait_calls = 0

            def wait(self) -> int:
                self.wait_calls += 1
                return 0

            def terminate(self) -> None:
                raise AssertionError("successful scan must not terminate osmium")

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_directory = directory / "source"
            source_directory.mkdir()
            plan = auxiliary.build_plan(
                source_directory / auxiliary.PLANET_FILENAME,
                source_directory / "fetch-manifest.json",
                directory / "output",
            )
            plan.output_directory.mkdir()
            process = FakeProcess()
            expected = {"selected_objects": 1}
            with mock.patch.object(
                auxiliary, "scan_osm_xml", return_value=expected
            ) as selector:
                statistics, stderr = auxiliary._scan_planet(
                    plan, popen_factory=lambda *args, **kwargs: process
                )
            self.assertEqual(selector.call_count, 1)
            self.assertEqual(process.wait_calls, 1)
            self.assertEqual(statistics, expected)
            self.assertEqual(stderr["bytes"], 0)

    @unittest.skipUnless(shutil.which("osmium"), "osmium-tool is not installed")
    def test_real_osmium_pipeline_recovers_only_selected_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source_directory = directory / "source"
            source_directory.mkdir()
            source = source_directory / auxiliary.PLANET_FILENAME
            subprocess.run(
                ["osmium", "cat", "--output", str(source), str(FIXTURE)], check=True
            )
            raw = source.read_bytes()
            input_md5 = md5(raw).hexdigest()
            input_sha256 = sha256(raw).hexdigest()
            fetch_manifest = source_directory / "fetch-manifest.json"
            fetch_document = {
                "input": {
                    "bytes": len(raw),
                    "md5": input_md5,
                    "path": source.name,
                    "sha256": input_sha256,
                },
                "pipeline": "openstreetmap_planet_fetch",
                "rights": {
                    "attribution": auxiliary.OSM_ATTRIBUTION,
                    "copyright_url": auxiliary.OSM_COPYRIGHT_URL,
                    "license": auxiliary.OSM_LICENSE,
                },
                "schema_version": 1,
                "snapshot_date": auxiliary.PLANET_SNAPSHOT_DATE,
                "state": "completed",
                "verification": {
                    "exact_size": True,
                    "official_md5": True,
                    "verified_before_extraction": True,
                },
            }
            fetch_manifest.write_bytes(auxiliary.canonical_json(fetch_document))
            output = directory / "output"
            osmium = auxiliary.resolve_osmium()
            document = auxiliary.extract_auxiliary(
                source,
                fetch_manifest,
                output,
                osmium_executable=osmium,
                expected_bytes=len(raw),
                expected_md5=input_md5,
                expected_sha256=input_sha256,
                expected_fetch_manifest_sha256=sha256(
                    fetch_manifest.read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(document["selection_statistics"]["selected_objects"], 5)
            self.assertTrue(document["integrity"]["check_refs_passed"])
            selected_xml = directory / "selected.osm"
            subprocess.run(
                [
                    osmium,
                    "cat",
                    str(output / auxiliary.OUTPUT_PBF_FILENAME),
                    "--output",
                    str(selected_xml),
                ],
                check=True,
            )
            root = ET.parse(selected_xml).getroot()
            objects = {
                (element.tag, int(element.attrib["id"])): {
                    child.attrib["k"]: child.attrib["v"]
                    for child in element
                    if child.tag == "tag"
                }
                for element in root
                if element.tag in {"node", "way", "relation"}
            }
            self.assertIn(("way", 106), objects)
            self.assertEqual(objects[("way", 106)], {})
            self.assertNotIn(("way", 101), objects)
            self.assertNotIn(("way", 104), objects)
            self.assertNotIn(("way", 107), objects)
            second = auxiliary.validate_bundle(
                output,
                source_path=source,
                fetch_manifest_path=fetch_manifest,
                expected_bytes=len(raw),
                expected_md5=input_md5,
                expected_sha256=input_sha256,
                expected_fetch_manifest_sha256=sha256(
                    fetch_manifest.read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(second, document)
            self.assertEqual(output.stat().st_mode & 0o777, 0o555)
            for name in (
                auxiliary.OUTPUT_PBF_FILENAME,
                auxiliary.IDS_FILENAME,
                auxiliary.LEDGER_FILENAME,
                auxiliary.MANIFEST_FILENAME,
                auxiliary.MANIFEST_SHA_FILENAME,
            ):
                self.assertEqual((output / name).stat().st_mode & 0o777, 0o444)
            self.assertEqual(
                set(document["processor"]["files"]),
                set(auxiliary.PROCESSOR_FILES),
            )

            output.chmod(0o755)
            unexpected = output / "unexpected.txt"
            unexpected.write_text("closed-tree regression\n", encoding="utf-8")
            output.chmod(0o555)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryError, "inventory changed"
            ):
                auxiliary.validate_bundle(
                    output,
                    source_path=source,
                    fetch_manifest_path=fetch_manifest,
                    expected_bytes=len(raw),
                    expected_md5=input_md5,
                    expected_sha256=input_sha256,
                    expected_fetch_manifest_sha256=sha256(
                        fetch_manifest.read_bytes()
                    ).hexdigest(),
                )
            output.chmod(0o755)
            unexpected.unlink()
            output.chmod(0o555)

            ids_path = output / auxiliary.IDS_FILENAME
            ids_path.chmod(0o644)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryError, "mode must be 0444"
            ):
                auxiliary.validate_bundle(
                    output,
                    source_path=source,
                    fetch_manifest_path=fetch_manifest,
                    expected_bytes=len(raw),
                    expected_md5=input_md5,
                    expected_sha256=input_sha256,
                    expected_fetch_manifest_sha256=sha256(
                        fetch_manifest.read_bytes()
                    ).hexdigest(),
                )
            ids_path.chmod(0o444)

            tampered = directory / "tampered"
            shutil.copytree(output, tampered)
            tampered.chmod(0o755)
            manifest_path = tampered / auxiliary.MANIFEST_FILENAME
            manifest_path.chmod(0o644)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            first_processor_file = auxiliary.PROCESSOR_FILES[0]
            manifest["processor"]["files"][first_processor_file]["sha256"] = "0" * 64
            manifest_path.write_bytes(auxiliary.canonical_json(manifest))
            sidecar = tampered / auxiliary.MANIFEST_SHA_FILENAME
            sidecar.chmod(0o644)
            sidecar.write_text(
                f"{sha256(manifest_path.read_bytes()).hexdigest()}  "
                f"{auxiliary.MANIFEST_FILENAME}\n",
                encoding="ascii",
            )
            for path in tampered.iterdir():
                path.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                auxiliary.OsmBlindTileAuxiliaryError, "lineage changed"
            ):
                auxiliary.validate_bundle(
                    tampered,
                    source_path=source,
                    fetch_manifest_path=fetch_manifest,
                    expected_bytes=len(raw),
                    expected_md5=input_md5,
                    expected_sha256=input_sha256,
                    expected_fetch_manifest_sha256=sha256(
                        fetch_manifest.read_bytes()
                    ).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
