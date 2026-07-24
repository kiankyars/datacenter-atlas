from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from datacenter_atlas.ohsome import DATA_CENTER_FILTER
from datacenter_atlas.database import initialize
from datacenter_atlas.osm import OpenStreetMapAdapter, extract_geometry
from datacenter_atlas.osm_planet import (
    DEFAULT_JSON_FILENAME,
    DEFAULT_MANIFEST_FILENAME,
    DEFAULT_XML_FILENAME,
    EXACT_TAG_PAIRS,
    MissingReferenceError,
    PlanetMaterializationError,
    build_overpass_document,
    canonical_json_bytes,
    convert_pbf_to_xml,
    is_exact_match,
    materialize_planet_extract,
    parse_osm_xml,
    validate_extraction_input,
)
from datacenter_atlas.scripts import extract_osm_planet


OSM_XML_FIXTURE = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="osmium/1.19.1">
  <bounds minlat="50.0" minlon="-1.0" maxlat="52.0" maxlon="1.0"/>
  <node id="1" lat="51.1000000" lon="0.1000000" version="3" changeset="100" timestamp="2026-07-01T12:30:00Z" uid="7" user="mapper">
    <tag k="telecom" v="data_center"/>
    <tag k="name" v="Direct node"/>
  </node>
  <node id="2" lat="51.0000000" lon="0.0000000" version="1" timestamp="2026-07-01T00:00:00Z"/>
  <node id="3" lat="51.0000000" lon="0.2000000" version="1" timestamp="2026-07-01T00:00:00Z"/>
  <node id="4" lat="51.2000000" lon="0.2000000" version="1" timestamp="2026-07-01T00:00:00Z"/>
  <node id="5" lat="51.2000000" lon="0.0000000" version="1" timestamp="2026-07-01T00:00:00Z"/>
  <node id="6" lat="50.5000000" lon="0.5000000" version="1" timestamp="2026-07-01T00:00:00Z">
    <tag k="telecom" v="Data_Center"/>
  </node>
  <way id="10" version="4" changeset="101" timestamp="2026-07-02T00:00:00Z">
    <nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="5"/><nd ref="2"/>
    <tag k="building" v="data_centre"/>
    <tag k="name" v="Exact building"/>
  </way>
  <way id="11" version="2" timestamp="2026-07-02T00:00:00Z">
    <nd ref="3"/><nd ref="4"/>
    <tag k="service" v="utility"/>
  </way>
  <relation id="20" version="5" changeset="102" timestamp="2026-07-03T00:00:00Z">
    <member type="way" ref="11" role="perimeter_fragment"/>
    <member type="node" ref="2" role="label"/>
    <tag k="type" v="site"/>
    <tag k="site" v="datacenter"/>
    <tag k="name" v="Non-area site relation"/>
  </relation>
  <relation id="21" version="1" timestamp="2026-07-03T00:00:00Z">
    <member type="relation" ref="20" role="subsite"/>
    <tag k="type" v="collection"/>
  </relation>
  <relation id="22" version="2" timestamp="2026-07-04T00:00:00Z">
    <member type="relation" ref="21" role="phase"/>
    <tag k="type" v="site"/>
    <tag k="proposed:site" v="datacentre"/>
    <tag k="name" v="Nested proposed site"/>
  </relation>
</osm>
"""


MISSING_REFERENCE_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <way id="90" version="1" timestamp="2026-07-01T00:00:00Z">
    <nd ref="999"/>
    <tag k="building" v="data_center"/>
  </way>
</osm>
"""


EMPTY_RELATION_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <relation id="91" version="1" timestamp="2026-07-01T00:00:00Z">
    <tag k="type" v="site"/>
    <tag k="site" v="data_center"/>
  </relation>
</osm>
"""


SPLIT_OUTER_WITH_HOLE_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <node id="1" lat="0" lon="0"/><node id="2" lat="0" lon="4"/>
  <node id="3" lat="4" lon="4"/><node id="4" lat="4" lon="0"/>
  <node id="5" lat="1" lon="1"/><node id="6" lat="1" lon="2"/>
  <node id="7" lat="2" lon="2"/><node id="8" lat="2" lon="1"/>
  <way id="100"><nd ref="1"/><nd ref="2"/></way>
  <way id="101"><nd ref="3"/><nd ref="2"/></way>
  <way id="102"><nd ref="3"/><nd ref="4"/></way>
  <way id="103"><nd ref="1"/><nd ref="4"/></way>
  <way id="104">
    <nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/>
  </way>
  <relation id="200" version="1" timestamp="2026-07-01T00:00:00Z">
    <member type="way" ref="102" role="outer"/>
    <member type="way" ref="100" role="outer"/>
    <member type="way" ref="103" role=""/>
    <member type="way" ref="101" role="outer"/>
    <member type="way" ref="104" role="inner"/>
    <tag k="type" v="multipolygon"/><tag k="site" v="data_center"/>
  </relation>
</osm>
"""


UNRESOLVED_OUTER_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <node id="1" lat="0" lon="0"/><node id="2" lat="0" lon="4"/>
  <node id="3" lat="4" lon="4"/><node id="4" lat="4" lon="0"/>
  <way id="100"><nd ref="1"/><nd ref="2"/></way>
  <way id="101"><nd ref="3"/><nd ref="2"/></way>
  <way id="102"><nd ref="3"/><nd ref="4"/></way>
  <relation id="201" version="1" timestamp="2026-07-01T00:00:00Z">
    <member type="way" ref="100" role="outer"/>
    <member type="way" ref="101" role="outer"/>
    <member type="way" ref="102" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="site" v="data_center"/>
  </relation>
</osm>
"""


@dataclass
class FakeCompletedProcess:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class OsmiumFixtureRunner:
    def __init__(self, xml: bytes = OSM_XML_FIXTURE) -> None:
        self.xml = xml
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> FakeCompletedProcess:
        self.commands.append(list(command))
        if command[-1] == "--version":
            return FakeCompletedProcess("osmium version 1.19.1\n")
        output_index = command.index("--output") + 1
        Path(command[output_index]).write_bytes(self.xml)
        return FakeCompletedProcess()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def extraction_bundle(
    directory: Path,
    *,
    pbf_payload: bytes = b"filtered-pbf-fixture",
    xml: bytes = OSM_XML_FIXTURE,
) -> tuple[Path, Path, OsmiumFixtureRunner]:
    source_payload = b"verified planet fixture"
    source = directory / "planet-260713.osm.pbf"
    source.write_bytes(source_payload)
    pbf = directory / "data-centers-260713.osm.pbf"
    pbf.write_bytes(pbf_payload)
    expressions = tuple(f"nwr/{key}={value}" for key, value in EXACT_TAG_PAIRS)
    document = {
        "schema_version": 1,
        "pipeline": "openstreetmap_planet_data_center_extraction",
        "state": "completed",
        "snapshot_date": "2026-07-13",
        "source": {
            "path": source.name,
            "url": f"https://planet.openstreetmap.org/pbf/{source.name}",
            "snapshot_date": "2026-07-13",
            "bytes": len(source_payload),
            "md5": hashlib.md5(source_payload).hexdigest(),
            "sha256": sha256(source_payload),
            "verification": {
                "mode": "exact_size_and_md5",
                "exact_size": True,
                "official_md5": True,
                "verified_before_extraction": True,
            },
            "fetch_manifest": None,
        },
        "filter": extract_osm_planet.filter_manifest_document(expressions),
        "output": {
            "path": pbf.name,
            "bytes": len(pbf_payload),
            "md5": hashlib.md5(pbf_payload).hexdigest(),
            "sha256": sha256(pbf_payload),
        },
        "fileinfo": {
            "object_counts_including_references": {
                "nodes": 6 if xml == OSM_XML_FIXTURE else 0,
                "ways": 2 if xml == OSM_XML_FIXTURE else 1,
                "relations": 3 if xml == OSM_XML_FIXTURE else 0,
            }
        },
        "rights": {
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "copyright_url": "https://www.openstreetmap.org/copyright",
        },
    }
    manifest = directory / "extract-manifest.json"
    manifest.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    return manifest, pbf, OsmiumFixtureRunner(xml)


class PlanetXMLTests(unittest.TestCase):
    def test_fixture_preserves_exact_nodes_ways_and_non_area_relations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.osm"
            path.write_bytes(OSM_XML_FIXTURE)
            parsed = parse_osm_xml(path)
            document, integrity = build_overpass_document(parsed)

        self.assertEqual(
            [(item["type"], item["id"]) for item in document["elements"]],
            [("node", 1), ("way", 10), ("relation", 20), ("relation", 22)],
        )
        self.assertEqual(integrity["source_object_counts"], {"node": 6, "way": 2, "relation": 3})
        self.assertEqual(integrity["exact_match_counts"]["total"], 4)
        self.assertEqual(integrity["missing_reference_count"], 0)
        self.assertTrue(integrity["all_exact_matches_emitted_once"])

        node = document["elements"][0]
        self.assertEqual(node["timestamp"], "2026-07-01T12:30:00Z")
        self.assertEqual(node["version"], 3)
        self.assertEqual(node["changeset"], 100)
        self.assertEqual(node["uid"], 7)
        self.assertEqual(node["user"], "mapper")

        way = document["elements"][1]
        self.assertEqual(way["nodes"], [2, 3, 4, 5, 2])
        self.assertEqual(len(way["geometry"]), 5)
        self.assertEqual(way["bounds"]["maxlat"], 51.2)

        relation = document["elements"][2]
        self.assertEqual(relation["tags"]["type"], "site")
        self.assertEqual(relation["members"][0]["ref"], 11)
        self.assertEqual(len(relation["members"][0]["geometry"]), 2)
        self.assertIn("bounds", relation)

        nested_relation = document["elements"][3]
        self.assertEqual(nested_relation["members"][0]["type"], "relation")
        self.assertIn("bounds", nested_relation["members"][0])
        self.assertIn("bounds", nested_relation)

    def test_materialized_document_is_consumed_without_loss_by_osm_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            xml_path = root / "fixture.osm"
            json_path = root / "overpass.json"
            xml_path.write_bytes(OSM_XML_FIXTURE)
            document, _ = build_overpass_document(parse_osm_xml(xml_path))
            json_path.write_bytes(canonical_json_bytes(document))
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                result = OpenStreetMapAdapter().import_file(
                    connection,
                    json_path,
                    retrieved_at="2026-07-18T12:00:00Z",
                )
            finally:
                connection.close()
        self.assertEqual(result.examined_elements, 4)
        self.assertEqual(result.imported_elements, 4)
        self.assertEqual(result.skipped_elements, 0)

    def test_case_normalization_is_not_used_for_planet_selection(self) -> None:
        self.assertFalse(is_exact_match({"telecom": "Data_Center"}))
        self.assertFalse(is_exact_match({"building": "data-center"}))
        self.assertTrue(is_exact_match({"telecom": "data_center"}))
        for key, value in EXACT_TAG_PAIRS:
            self.assertTrue(is_exact_match({key: value}), (key, value))
        self.assertEqual(len(EXACT_TAG_PAIRS), 92)

    def test_missing_retained_reference_is_a_structured_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "missing.osm"
            path.write_bytes(MISSING_REFERENCE_XML)
            with self.assertRaises(MissingReferenceError) as caught:
                build_overpass_document(parse_osm_xml(path))
        self.assertEqual(
            caught.exception.missing_references,
            (
                {
                    "owner_type": "way",
                    "owner_id": 90,
                    "member_type": "node",
                    "member_id": 999,
                },
            ),
        )

    def test_empty_non_area_relation_is_retained_with_geometry_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty-relation.osm"
            path.write_bytes(EMPTY_RELATION_XML)
            document, integrity = build_overpass_document(parse_osm_xml(path))
        self.assertEqual(len(document["elements"]), 1)
        self.assertEqual(document["elements"][0]["type"], "relation")
        self.assertEqual(
            document["elements"][0]["geometry_status"],
            "unavailable_no_coordinate_members",
        )
        self.assertEqual(integrity["geometry_unavailable_count"], 1)

    def test_split_outer_members_are_stitched_and_inner_hole_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "split-with-hole.osm"
            path.write_bytes(SPLIT_OUTER_WITH_HOLE_XML)
            document, integrity = build_overpass_document(parse_osm_xml(path))
        self.assertEqual(len(document["elements"]), 1)
        relation = document["elements"][0]
        self.assertEqual(relation["type"], "relation")
        self.assertEqual(
            [member["ref"] for member in relation["members"]],
            [102, 100, 103, 101, 104],
        )
        self.assertTrue(all("geometry" in member for member in relation["members"]))
        self.assertEqual(relation["geometry_source"], "stitched_relation_member_ways")
        self.assertEqual(relation["geometry"]["type"], "Polygon")
        self.assertEqual(len(relation["geometry"]["coordinates"]), 2)
        outer, inner = relation["geometry"]["coordinates"]
        self.assertEqual(outer[0], outer[-1])
        self.assertEqual(inner[0], inner[-1])
        self.assertEqual(len(outer), 5)
        self.assertEqual(len(inner), 5)
        self.assertEqual(relation["geometry_assembly"]["status"], "assembled")
        self.assertEqual(relation["geometry_assembly"]["outer_ring_count"], 1)
        self.assertEqual(relation["geometry_assembly"]["inner_ring_count"], 1)
        self.assertEqual(extract_geometry(relation), relation["geometry"])
        self.assertEqual(integrity["relation_geometry_assembled_count"], 1)
        self.assertEqual(integrity["relation_geometry_unresolved_count"], 0)

    def test_open_outer_fragments_are_surfaced_without_guessing_a_ring(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "open-outer.osm"
            path.write_bytes(UNRESOLVED_OUTER_XML)
            document, integrity = build_overpass_document(parse_osm_xml(path))
        relation = document["elements"][0]
        self.assertNotIn("geometry", relation)
        report = relation["geometry_assembly"]
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(
            report["unresolved_fragments"],
            [
                {
                    "role": "outer_or_empty",
                    "reason": "open_or_branched_component",
                    "member_indices": [0, 1, 2],
                    "way_ids": [100, 101, 102],
                }
            ],
        )
        self.assertEqual(extract_geometry(relation)["type"], "MultiLineString")
        self.assertEqual(integrity["relation_geometry_assembled_count"], 0)
        self.assertEqual(integrity["relation_geometry_unresolved_count"], 1)

    def test_duplicate_osm_identity_is_rejected(self) -> None:
        xml = (
            b"<osm version='0.6'><node id='1' lat='0' lon='0'/>"
            b"<node id='1' lat='1' lon='1'/></osm>"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.osm"
            path.write_bytes(xml)
            with self.assertRaisesRegex(PlanetMaterializationError, "duplicate node/1"):
                parse_osm_xml(path)

    def test_canonical_json_is_deterministic(self) -> None:
        first = canonical_json_bytes({"z": 1, "a": "é"})
        second = canonical_json_bytes({"a": "é", "z": 1})
        self.assertEqual(first, second)
        self.assertEqual(first, b'{"a":"\xc3\xa9","z":1}\n')


class ConversionTests(unittest.TestCase):
    def test_osmium_cat_conversion_is_atomic_and_explicitly_xml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbf = root / "filtered.pbf"
            pbf.write_bytes(b"pbf")
            output = root / "filtered.osm"
            runner = OsmiumFixtureRunner()
            command = convert_pbf_to_xml(pbf, output, runner=runner)
            self.assertEqual(output.read_bytes(), OSM_XML_FIXTURE)
            self.assertIn("--output-format", command)
            self.assertEqual(command[command.index("--output-format") + 1], "osm")
            self.assertNotIn("geojson", command)
            self.assertFalse((root / ".filtered.osm.tmp").exists())

    def test_failed_osmium_cat_does_not_expose_partial_output(self) -> None:
        def failing_runner(command: list[str], **_: object) -> FakeCompletedProcess:
            output = Path(command[command.index("--output") + 1])
            output.write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, command, stderr="fixture failure")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pbf = root / "filtered.pbf"
            pbf.write_bytes(b"pbf")
            output = root / "filtered.osm"
            with self.assertRaisesRegex(PlanetMaterializationError, "fixture failure"):
                convert_pbf_to_xml(pbf, output, runner=failing_runner)
            self.assertFalse(output.exists())
            self.assertFalse((root / ".filtered.osm.tmp").exists())


class BundleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("osmium"), "osmium-tool is not installed")
    def test_real_extractor_to_xml_to_adapter_json_contract(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "osm_planet_minimal.osm"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "planet-real-materialize.osm.pbf"
            subprocess.run(
                ["osmium", "cat", "--output", str(source), str(fixture)],
                check=True,
                capture_output=True,
                text=True,
            )
            source_payload = source.read_bytes()
            filtered = root / "planet-real-materialize-data-centers.osm.pbf"
            extraction_manifest = root / "extract-manifest.json"
            extract_osm_planet.extract_planet(
                source,
                filtered,
                extraction_manifest,
                expected_snapshot_date="2026-07-13",
                expected_filename=source.name,
                expected_source_url=(
                    f"https://planet.openstreetmap.org/pbf/{source.name}"
                ),
                expected_size=len(source_payload),
                expected_md5=hashlib.md5(source_payload).hexdigest(),
                osmium_executable=shutil.which("osmium") or "osmium",
                clock=iter(
                    ("2026-07-18T12:00:00Z", "2026-07-18T12:01:00Z")
                ).__next__,
            )
            output = root / "materialized"
            result = materialize_planet_extract(
                extraction_manifest,
                output,
                osmium_binary=shutil.which("osmium") or "osmium",
                clock=lambda: "2026-07-18T12:02:00Z",
            )
            overpass = json.loads((output / DEFAULT_JSON_FILENAME).read_text())

        self.assertEqual(result["counts"]["missing_reference_count"], 0)
        self.assertEqual(result["counts"]["exact_match_counts"]["total"], 3)
        self.assertEqual(
            [(element["type"], element["id"]) for element in overpass["elements"]],
            [("node", 1), ("way", 10), ("relation", 20)],
        )

    def test_materializes_lineage_bound_bundle_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, pbf_path, runner = extraction_bundle(root)
            output = root / "bundle"
            result = materialize_planet_extract(
                manifest_path,
                output,
                filtered_pbf=pbf_path,
                runner=runner,
                clock=lambda: "2026-07-18T12:00:00Z",
            )

            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["outputs"]["overpass_json"]["element_count"], 4)
            self.assertEqual(
                result["inputs"]["extraction_manifest"]["path"],
                "../extract-manifest.json",
            )
            self.assertEqual(
                result["inputs"]["filtered_pbf"]["path"],
                "../data-centers-260713.osm.pbf",
            )
            self.assertEqual(result["transform"]["tag_pair_count"], 92)
            self.assertEqual(result["rights"]["license"], "ODbL-1.0")
            self.assertFalse(result["transform"]["status_or_capacity_inference"])
            self.assertEqual(len(runner.commands), 2)
            self.assertEqual(runner.commands[0], ["osmium", "--version"])
            self.assertEqual(runner.commands[1][0:2], ["osmium", "cat"])
            self.assertNotIn(".bundle.stage-", " ".join(result["transform"]["command"]))

            saved_manifest = json.loads((output / DEFAULT_MANIFEST_FILENAME).read_text())
            self.assertEqual(saved_manifest, result)
            overpass_raw = (output / DEFAULT_JSON_FILENAME).read_bytes()
            xml_raw = (output / DEFAULT_XML_FILENAME).read_bytes()
            self.assertEqual(
                result["outputs"]["overpass_json"]["sha256"], sha256(overpass_raw)
            )
            self.assertEqual(result["outputs"]["osm_xml"]["sha256"], sha256(xml_raw))

            def should_not_run(*_: object, **__: object) -> object:
                raise AssertionError("idempotent rerun invoked osmium")

            rerun = materialize_planet_extract(
                manifest_path,
                output,
                filtered_pbf=pbf_path,
                runner=should_not_run,
            )
            self.assertEqual(rerun, result)

    def test_dry_run_validates_inputs_without_subprocess_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, pbf_path, _ = extraction_bundle(root)
            output = root / "not-created"

            def should_not_run(*_: object, **__: object) -> object:
                raise AssertionError("dry-run invoked a subprocess")

            result = materialize_planet_extract(
                manifest_path,
                output,
                filtered_pbf=pbf_path,
                runner=should_not_run,
                dry_run=True,
            )
            self.assertEqual(result["state"], "dry_run")
            self.assertFalse(result["writes_performed"])
            self.assertIn("--no-progress", result["planned_command"])
            self.assertEqual(
                result["planned_command"][
                    result["planned_command"].index("--output-format") + 1
                ],
                "osm",
            )
            self.assertFalse(output.exists())

    def test_pbf_hash_mismatch_is_rejected_before_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, pbf_path, _ = extraction_bundle(root)
            pbf_path.write_bytes(b"tampered")
            with self.assertRaisesRegex(PlanetMaterializationError, "byte count|SHA256"):
                validate_extraction_input(manifest_path, filtered_pbf=pbf_path)

    def test_filter_or_reference_semantics_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, _, _ = extraction_bundle(root)
            document = json.loads(manifest_path.read_text())
            document["filter"]["referenced_nodes_and_members_retained"] = False
            manifest_path.write_text(json.dumps(document))
            with self.assertRaisesRegex(PlanetMaterializationError, "canonical contract"):
                validate_extraction_input(manifest_path)

    def test_declared_fetch_manifest_hash_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, _, _ = extraction_bundle(root)
            fetch_path = root / "fetch-manifest.json"
            fetch_path.write_bytes(
                b'{"pipeline":"openstreetmap_planet_fetch",'
                b'"state":"completed",'
                b'"finished_at":"2026-07-18T11:59:00Z"}\n'
            )
            document = json.loads(manifest_path.read_text())
            document["source"]["fetch_manifest"] = {
                "path": fetch_path.name,
                "sha256": sha256(fetch_path.read_bytes()),
            }
            document["source"]["verification"]["mode"] = (
                "completed_fetch_manifest_plus_exact_size_and_md5"
            )
            manifest_path.write_text(json.dumps(document))
            validated = validate_extraction_input(manifest_path)
            self.assertEqual(
                validated.source_retrieved_at, "2026-07-18T11:59:00Z"
            )
            fetch_path.write_bytes(b"tampered")
            with self.assertRaisesRegex(PlanetMaterializationError, "fetch manifest SHA256"):
                validate_extraction_input(manifest_path)

    def test_xml_count_mismatch_is_an_atomic_integrity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, _, runner = extraction_bundle(root)
            document = json.loads(manifest_path.read_text())
            document["fileinfo"]["object_counts_including_references"]["nodes"] = 7
            manifest_path.write_text(json.dumps(document))
            output = root / "bundle"
            with self.assertRaisesRegex(PlanetMaterializationError, "object counts"):
                materialize_planet_extract(manifest_path, output, runner=runner)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".bundle.stage-*")), [])

            document["filter"]["referenced_nodes_and_members_retained"] = True
            document["filter"]["source_filter_expression"] = "building=data_center"
            manifest_path.write_text(json.dumps(document))
            with self.assertRaisesRegex(PlanetMaterializationError, "canonical contract"):
                validate_extraction_input(manifest_path)

    def test_corrupt_existing_output_is_not_treated_as_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, pbf_path, runner = extraction_bundle(root)
            output = root / "bundle"
            materialize_planet_extract(manifest_path, output, runner=runner)
            (output / DEFAULT_JSON_FILENAME).write_bytes(b"tampered")
            with self.assertRaisesRegex(PlanetMaterializationError, "hash or byte count"):
                materialize_planet_extract(manifest_path, output, filtered_pbf=pbf_path)

    def test_integrity_failure_leaves_no_bundle_or_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, _, runner = extraction_bundle(
                root, xml=MISSING_REFERENCE_XML
            )
            output = root / "bundle"
            with self.assertRaises(MissingReferenceError):
                materialize_planet_extract(manifest_path, output, runner=runner)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".bundle.stage-*")), [])

    def test_explicit_pbf_must_be_the_manifest_bound_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path, _, _ = extraction_bundle(root)
            alternate = root / "alternate.pbf"
            alternate.write_bytes(b"filtered-pbf-fixture")
            with self.assertRaisesRegex(PlanetMaterializationError, "does not match"):
                validate_extraction_input(manifest_path, filtered_pbf=alternate)


if __name__ == "__main__":
    unittest.main()
