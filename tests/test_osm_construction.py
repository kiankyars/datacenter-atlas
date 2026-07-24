from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from datacenter_atlas.osm_construction import (
    BUNDLE_PIPELINE,
    EXTRACTION_PIPELINE,
    FILTER_SHA256,
    FILTER_VERSION,
    KnownExactLayer,
    build_candidate_documents,
    filter_manifest_document,
    is_explicit_power_asset,
    materialize_construction_candidates,
    osmium_filter_expressions,
)
from datacenter_atlas.osm_planet import PlanetMaterializationError, parse_osm_xml
from datacenter_atlas.scripts import extract_osm_planet_construction


FIXTURE_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <node id="1" lat="0" lon="0"/><node id="2" lat="0" lon="0.0011"/>
  <node id="3" lat="0.0011" lon="0.0011"/><node id="4" lat="0.0011" lon="0"/>
  <node id="5" lat="0.01" lon="0.01"/><node id="6" lat="0.01" lon="0.0111"/>
  <node id="7" lat="0.0111" lon="0.0111"/><node id="8" lat="0.0111" lon="0.01"/>
  <node id="9" lat="0.02" lon="0.02"/><node id="10" lat="0.02" lon="0.0202"/>
  <node id="11" lat="0.0202" lon="0.0202"/><node id="12" lat="0.0202" lon="0.02"/>
  <node id="900" lat="0.0005" lon="0.0005"><tag k="power" v="substation"/></node>
  <way id="100" timestamp="2026-07-12T00:00:00Z">
    <nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/>
    <tag k="building" v="construction"/><tag k="construction" v="warehouse"/>
    <tag k="telecom" v="data_center"/>
  </way>
  <way id="101" timestamp="2026-07-11T00:00:00Z">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="construction"/><tag k="construction" v="warehouse"/>
  </way>
  <way id="102"><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/>
    <tag k="building" v="construction"/>
  </way>
  <way id="200"><nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/></way>
  <relation id="300" timestamp="2026-07-10T00:00:00Z">
    <member type="way" ref="200" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="proposed:building" v="industrial"/>
  </relation>
</osm>
"""

PRIMARY_MATCH_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <way id="100" timestamp="2026-07-12T00:00:00Z">
    <nd ref="5"/><nd ref="6"/><nd ref="7"/><nd ref="8"/><nd ref="5"/>
    <tag k="building" v="construction"/><tag k="construction" v="warehouse"/>
    <tag k="telecom" v="data_center"/>
  </way>
  <way id="101" timestamp="2026-07-11T00:00:00Z">
    <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="construction"/><tag k="construction" v="warehouse"/>
  </way>
  <way id="102"><nd ref="9"/><nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="9"/>
    <tag k="building" v="construction"/>
  </way>
  <relation id="300" timestamp="2026-07-10T00:00:00Z">
    <member type="way" ref="200" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="proposed:building" v="industrial"/>
  </relation>
</osm>
"""


def digest(payload: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, payload).hexdigest()


@dataclass
class FakeCompletedProcess:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class FakeExtractionOsmium:
    def __init__(self, payload: bytes = b"construction-pbf", *, fail_refs: bool = False) -> None:
        self.payload = payload
        self.fail_refs = fail_refs
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> FakeCompletedProcess:
        self.commands.append(list(command))
        if command[-1] == "--version":
            return FakeCompletedProcess("osmium version 1.19.1\n")
        if command[1] == "tags-filter":
            Path(command[command.index("--output") + 1]).write_bytes(self.payload)
            return FakeCompletedProcess()
        if command[1] == "check-refs":
            return FakeCompletedProcess(
                stderr="missing reference", returncode=1 if self.fail_refs else 0
            )
        if command[1] == "fileinfo":
            output = Path(command[-1])
            return FakeCompletedProcess(
                json.dumps(
                    {
                        "file": {
                            "name": str(output),
                            "format": "PBF",
                            "compression": "none",
                            "size": output.stat().st_size,
                        },
                        "header": {"boxes": [], "option": {"generator": "fixture"}},
                        "data": {
                            "bbox": None,
                            "timestamp": {"first": None, "last": None},
                            "objects_ordered": True,
                            "multiple_versions": False,
                            "crc32": "1234abcd",
                            "count": {"nodes": 13, "ways": 4, "relations": 1},
                        },
                    }
                )
            )
        raise AssertionError(command)


class FakeMaterializerOsmium:
    def __init__(self, xml: bytes = FIXTURE_XML) -> None:
        self.xml = xml
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> FakeCompletedProcess:
        self.commands.append(list(command))
        if command[-1] == "--version":
            return FakeCompletedProcess("osmium version 1.19.1\n")
        if command[1] == "tags-filter":
            Path(command[command.index("--output") + 1]).write_bytes(b"fixture-pbf")
            return FakeCompletedProcess()
        if command[1] == "check-refs":
            return FakeCompletedProcess()
        if command[1] == "fileinfo":
            name = Path(command[-1]).name
            if name == "primary-matches-only.osm.pbf":
                counts = {"nodes": 0, "ways": 3, "relations": 1}
            elif name == "power-context-matches-only.osm.pbf":
                counts = {"nodes": 1, "ways": 0, "relations": 0}
            elif name == "primary-matches-with-references.osm.pbf":
                counts = {"nodes": 12, "ways": 4, "relations": 1}
            else:
                counts = {"nodes": 1, "ways": 0, "relations": 0}
            return FakeCompletedProcess(
                json.dumps({"data": {"count": counts}})
            )
        if command[1] == "cat":
            Path(command[command.index("--output") + 1]).write_bytes(PRIMARY_MATCH_XML)
            return FakeCompletedProcess()
        if command[1] == "export":
            output = Path(command[command.index("--output") + 1])
            if "point,polygon" in command:
                features = [
                    {
                        "type": "Feature",
                        "id": "n900",
                        "geometry": {"type": "Point", "coordinates": [0.0005, 0.0005]},
                        "properties": {"power": "substation"},
                    }
                ]
            else:
                polygons = {
                    "a200": ([[0.01, 0.01], [0.0111, 0.01], [0.0111, 0.0111], [0.01, 0.0111], [0.01, 0.01]], {"building": "construction", "construction": "warehouse", "telecom": "data_center"}),
                    "a202": ([[0, 0], [0.0011, 0], [0.0011, 0.0011], [0, 0.0011], [0, 0]], {"building": "construction", "construction": "warehouse"}),
                    "a204": ([[0.02, 0.02], [0.0202, 0.02], [0.0202, 0.0202], [0.02, 0.0202], [0.02, 0.02]], {"building": "construction"}),
                    "a601": ([[0.01, 0.01], [0.0111, 0.01], [0.0111, 0.0111], [0.01, 0.0111], [0.01, 0.01]], {"type": "multipolygon", "proposed:building": "industrial"}),
                }
                features = [
                    {
                        "type": "Feature",
                        "id": feature_id,
                        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
                        "properties": properties,
                    }
                    for feature_id, (coordinates, properties) in polygons.items()
                ]
            output.write_bytes(
                b"".join(
                    b"\x1e" + json.dumps(feature, sort_keys=True).encode() + b"\n"
                    for feature in features
                )
            )
            return FakeCompletedProcess()
        raise AssertionError(command)


def exact_layer(directory: Path, planet_sha256: str) -> tuple[Path, KnownExactLayer]:
    exact_document = {
        "version": 0.6,
        "elements": [
            {
                "type": "way",
                "id": 100,
                "tags": {"telecom": "data_center"},
            }
        ],
    }
    raw = (json.dumps(exact_document, sort_keys=True) + "\n").encode()
    json_path = directory / "exact-overpass.json"
    json_path.write_bytes(raw)
    manifest = {
        "schema_version": 1,
        "pipeline": "openstreetmap_planet_materialize",
        "state": "completed",
        "inputs": {"planet_source": {"sha256": planet_sha256}},
        "outputs": {
            "overpass_json": {
                "path": json_path.name,
                "bytes": len(raw),
                "md5": digest(raw, "md5"),
                "sha256": digest(raw, "sha256"),
                "element_count": 1,
            }
        },
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    manifest_path = directory / "exact-manifest.json"
    manifest_path.write_bytes(manifest_raw)
    known = KnownExactLayer(
        manifest_path,
        manifest_raw,
        manifest,
        json_path,
        raw,
        frozenset({("way", 100)}),
        {("way", 100): exact_document["elements"][0]},
    )
    return manifest_path, known


def extraction_bundle(directory: Path) -> tuple[Path, Path, Path]:
    source_payload = b"verified dated planet fixture"
    pbf_payload = b"construction filtered pbf fixture"
    source = directory / "planet-260713.osm.pbf"
    pbf = directory / "construction.osm.pbf"
    source.write_bytes(source_payload)
    pbf.write_bytes(pbf_payload)
    source_sha = digest(source_payload, "sha256")
    exact_manifest, _ = exact_layer(directory, source_sha)
    manifest = {
        "schema_version": 1,
        "pipeline": EXTRACTION_PIPELINE,
        "state": "completed",
        "review_only": True,
        "snapshot_date": "2026-07-13",
        "source": {
            "path": source.name,
            "url": f"https://planet.openstreetmap.org/pbf/{source.name}",
            "snapshot_date": "2026-07-13",
            "bytes": len(source_payload),
            "md5": digest(source_payload, "md5"),
            "sha256": source_sha,
            "verification": {
                "mode": "exact_size_and_md5",
                "exact_size": True,
                "official_md5": True,
                "verified_before_extraction": True,
            },
            "fetch_manifest": None,
        },
        "filter": filter_manifest_document(),
        "output": {
            "path": pbf.name,
            "bytes": len(pbf_payload),
            "md5": digest(pbf_payload, "md5"),
            "sha256": digest(pbf_payload, "sha256"),
        },
        "fileinfo": {
            "object_counts_including_references": {
                "nodes": 13,
                "ways": 4,
                "relations": 1,
            }
        },
        "rights": {
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "copyright_url": "https://www.openstreetmap.org/copyright",
        },
    }
    path = directory / "construction-extract-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path, pbf, exact_manifest


class ConstructionFilterTests(unittest.TestCase):
    def test_filter_is_versioned_bounded_and_preserves_references(self) -> None:
        expressions = osmium_filter_expressions()
        self.assertEqual(len(expressions), 49)
        self.assertIn("nwr/building=construction", expressions)
        self.assertIn("nwr/proposed:building", expressions)
        self.assertIn("nwr/man_made=foundation", expressions)
        self.assertIn("nwr/power=substation", expressions)
        self.assertNotIn("nwr/construction=*", expressions)
        self.assertFalse(any("highway" in item or "railway" in item for item in expressions))
        contract = filter_manifest_document()
        self.assertEqual(contract["version"], FILTER_VERSION)
        self.assertEqual(contract["contract_sha256"], FILTER_SHA256)
        self.assertTrue(contract["referenced_nodes_and_members_retained"])

    def test_explicit_power_assets_are_source_tag_exclusions(self) -> None:
        self.assertTrue(is_explicit_power_asset({"power": "plant"}))
        self.assertTrue(is_explicit_power_asset({"proposed:power": "substation"}))
        self.assertTrue(is_explicit_power_asset({"construction": "plant"}))
        self.assertTrue(is_explicit_power_asset({"construction": "power:plant"}))
        self.assertTrue(is_explicit_power_asset({"industrial": "power_generation"}))
        self.assertTrue(is_explicit_power_asset({"generator:source": "solar"}))
        self.assertTrue(is_explicit_power_asset({"plant:source": "solar"}))
        self.assertFalse(is_explicit_power_asset({"building": "construction"}))

    @unittest.skipUnless(shutil.which("osmium"), "osmium is not installed")
    def test_real_osmium_filter_retains_way_and_relation_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "fixture.osm"
            pbf = directory / "source.pbf"
            filtered = directory / "filtered.pbf"
            xml = directory / "filtered.osm"
            source.write_bytes(FIXTURE_XML)
            subprocess.run(["osmium", "cat", str(source), "-o", str(pbf)], check=True)
            subprocess.run(
                ["osmium", "tags-filter", str(pbf), *osmium_filter_expressions(), "-o", str(filtered)],
                check=True,
            )
            subprocess.run(["osmium", "check-refs", "-r", str(filtered)], check=True)
            subprocess.run(["osmium", "cat", str(filtered), "-o", str(xml)], check=True)
            parsed = parse_osm_xml(xml)
        self.assertIn(101, parsed.ways)
        self.assertIn(1, parsed.nodes)
        self.assertIn(300, parsed.relations)
        self.assertIn(200, parsed.ways)


class ConstructionExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.payload = b"synthetic verified planet"
        self.source = self.directory / "planet-test.osm.pbf"
        self.source.write_bytes(self.payload)
        self.output = self.directory / "construction.osm.pbf"
        self.manifest = self.directory / "construction-extract-manifest.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def arguments(self) -> dict[str, object]:
        return {
            "expected_snapshot_date": "2026-07-13",
            "expected_filename": self.source.name,
            "expected_source_url": f"https://planet.openstreetmap.org/pbf/{self.source.name}",
            "expected_size": len(self.payload),
            "expected_md5": digest(self.payload, "md5"),
            "osmium_executable": "/test/osmium",
        }

    def test_extraction_is_reference_checked_atomic_and_idempotent(self) -> None:
        plan = extract_osm_planet_construction.build_command_plan(
            self.source, self.output, self.manifest, osmium_executable="/test/osmium"
        )
        self.assertNotIn("-R", plan.tags_filter_command)
        self.assertNotIn("--omit-referenced", plan.tags_filter_command)
        self.assertIn("-r", plan.check_refs_command)
        runner = FakeExtractionOsmium()
        times = iter(("2026-07-18T10:00:00Z", "2026-07-18T10:01:00Z"))
        result = extract_osm_planet_construction.extract_construction_planet(
            self.source,
            self.output,
            self.manifest,
            runner=runner,
            clock=lambda: next(times),
            **self.arguments(),
        )
        self.assertEqual(result["pipeline"], EXTRACTION_PIPELINE)
        self.assertTrue(result["referential_integrity_check"]["passed"])
        self.assertEqual(result["filter"], filter_manifest_document())

        class NeverRun:
            def __call__(self, *_: object, **__: object) -> object:
                raise AssertionError("verified extraction must be reused")

        second = extract_osm_planet_construction.extract_construction_planet(
            self.source, self.output, self.manifest, runner=NeverRun(), **self.arguments()
        )
        self.assertEqual(second, result)

    def test_failed_reference_check_publishes_nothing(self) -> None:
        with self.assertRaises(Exception):
            extract_osm_planet_construction.extract_construction_planet(
                self.source,
                self.output,
                self.manifest,
                runner=FakeExtractionOsmium(fail_refs=True),
                **self.arguments(),
            )
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.directory.glob(".*extracting*")), [])


class ConstructionMaterializationTests(unittest.TestCase):
    def test_lossless_matches_geometry_prior_and_exact_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            xml = directory / "construction.osm"
            xml.write_bytes(FIXTURE_XML)
            _, known = exact_layer(directory, "a" * 64)
            matches, contexts, links, shortlist, integrity = build_candidate_documents(
                parse_osm_xml(xml), known
            )
        identities = [(item["type"], item["id"]) for item in matches["elements"]]
        self.assertEqual(
            identities,
            [("way", 100), ("way", 101), ("way", 102), ("relation", 300)],
        )
        self.assertEqual(contexts["elements"][0]["id"], 900)
        self.assertEqual(len(links["links"]), 1)
        self.assertEqual(links["links"][0]["link_method"], "identical_osm_object_type_and_id")
        shortlisted_ids = {(item["type"], item["id"]) for item in shortlist}
        self.assertNotIn(("way", 100), shortlisted_ids)
        self.assertIn(("way", 101), shortlisted_ids)
        self.assertIn(("relation", 300), shortlisted_ids)
        candidate = next(item for item in shortlist if item["id"] == 101)
        self.assertGreater(candidate["review_prior"]["footprint_square_metres"], 10_000)
        self.assertTrue(candidate["review_prior"]["explicit_industrial_source_tag"])
        self.assertIsNotNone(candidate["review_prior"]["nearest_power_context"])
        self.assertNotIn("capacity", candidate)
        self.assertNotIn("workload", candidate)
        self.assertEqual(integrity["raw_primary_match_counts"]["total"], 4)
        self.assertEqual(integrity["known_exact_identity_exclusion_count"], 1)

    def test_exact_tag_missing_from_exact_layer_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            xml = directory / "construction.osm"
            xml.write_bytes(FIXTURE_XML)
            exact_manifest, known = exact_layer(directory, "a" * 64)
            empty = KnownExactLayer(
                exact_manifest,
                known.manifest_raw,
                known.document,
                known.json_path,
                known.json_raw,
                frozenset(),
                {},
            )
            with self.assertRaisesRegex(PlanetMaterializationError, "absent from"):
                build_candidate_documents(parse_osm_xml(xml), empty)

    def test_bundle_is_hash_bound_atomic_idempotent_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            extraction, pbf, exact_manifest = extraction_bundle(directory)
            output = directory / "candidate-bundle"
            runner = FakeMaterializerOsmium()
            result = materialize_construction_candidates(
                extraction,
                exact_manifest,
                output,
                filtered_pbf=pbf,
                osmium_binary="/test/osmium",
                runner=runner,
                clock=lambda: "2026-07-18T12:00:00Z",
            )
            self.assertEqual(result["pipeline"], BUNDLE_PIPELINE)
            self.assertEqual(result["counts"]["raw_primary_match_counts"]["total"], 4)
            self.assertGreaterEqual(result["counts"]["shortlisted_counts"]["total"], 2)
            self.assertFalse((output / "construction-filtered.osm").exists())

            class NeverRun:
                def __call__(self, *_: object, **__: object) -> object:
                    raise AssertionError("verified bundle must be reused")

            second = materialize_construction_candidates(
                extraction, exact_manifest, output, filtered_pbf=pbf, runner=NeverRun()
            )
            self.assertEqual(second, result)
            with (output / "shortlist.csv").open("ab") as tampered:
                tampered.write(b"tampered")
            with self.assertRaisesRegex(PlanetMaterializationError, "hash does not match"):
                materialize_construction_candidates(
                    extraction, exact_manifest, output, filtered_pbf=pbf, runner=NeverRun()
                )


if __name__ == "__main__":
    unittest.main()
