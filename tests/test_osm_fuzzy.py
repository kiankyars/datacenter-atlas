from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from datacenter_atlas.database import initialize
from datacenter_atlas.osm_fuzzy import (
    CLASSIFIER_VERSION,
    DEFAULT_JSON_FILENAME,
    EXTRACTION_PIPELINE,
    FILTER_SHA256,
    MATERIALIZATION_PIPELINE,
    OpenStreetMapFuzzyDiscoveryAdapter,
    VARIANTS,
    build_fuzzy_overpass_document,
    classify_tags,
    filter_manifest_document,
    materialize_fuzzy_extract,
    osmium_filter_expressions,
)
from datacenter_atlas.osm_planet import parse_osm_xml
from datacenter_atlas.scripts import extract_osm_planet_fuzzy, fetch_osm_planet


FUZZY_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="fixture">
  <node id="1" lat="0" lon="0" timestamp="2026-07-01T00:00:00Z">
    <tag k="telecom" v="data_center"/><tag k="name" v="Exact duplicate"/>
  </node>
  <node id="2" lat="1" lon="1" timestamp="2026-07-02T00:00:00Z">
    <tag k="name" v="Former Data Center Cafe"/>
  </node>
  <node id="3" lat="2" lon="2"><tag k="mystery:use" v="data centre"/></node>
  <node id="4" lat="3" lon="3"><tag k="data_center:note" v="possible"/></node>
  <node id="5" lat="4" lon="4"><tag k="disused:telecom" v="datacentre"/></node>
  <node id="10" lat="10" lon="10"/><node id="11" lat="10" lon="11"/>
  <node id="12" lat="11" lon="11"/><node id="13" lat="11" lon="10"/>
  <node id="20" lat="20" lon="20"/><node id="21" lat="20" lon="21"/>
  <node id="22" lat="21" lon="21"/><node id="23" lat="21" lon="20"/>
  <way id="100" timestamp="2026-07-03T00:00:00Z">
    <nd ref="10"/><nd ref="11"/><nd ref="12"/><nd ref="13"/><nd ref="10"/>
    <tag k="building:use" v="office;data_center;data_centre"/>
  </way>
  <way id="101"><nd ref="10"/><nd ref="11"/>
    <tag k="construction" v="Data Center"/>
  </way>
  <way id="200">
    <nd ref="20"/><nd ref="21"/><nd ref="22"/><nd ref="23"/><nd ref="20"/>
  </way>
  <relation id="300" timestamp="2026-07-04T00:00:00Z">
    <member type="way" ref="200" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="proposed:building" v="Data Centre"/>
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


class FakeExtractorOsmium:
    def __init__(self, payload: bytes = b"fuzzy-pbf", *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> FakeCompletedProcess:
        self.commands.append(list(command))
        if command[-1] == "--version":
            return FakeCompletedProcess("osmium version 1.19.1\n")
        if command[1] == "tags-filter":
            Path(command[command.index("--output") + 1]).write_bytes(self.payload)
            return FakeCompletedProcess(stderr="synthetic failure", returncode=1) if self.fail else FakeCompletedProcess()
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
                            "count": {"nodes": 13, "ways": 3, "relations": 1},
                        },
                    }
                )
            )
        raise AssertionError(command)


class FakeMaterializerOsmium:
    def __init__(self, xml: bytes = FUZZY_XML) -> None:
        self.xml = xml
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> FakeCompletedProcess:
        self.commands.append(list(command))
        if command[-1] == "--version":
            return FakeCompletedProcess("osmium version 1.19.1\n")
        Path(command[command.index("--output") + 1]).write_bytes(self.xml)
        return FakeCompletedProcess()


def extraction_bundle(directory: Path) -> tuple[Path, Path]:
    source_payload = b"verified dated planet fixture"
    pbf_payload = b"fuzzy filtered pbf fixture"
    source = directory / "planet-260713.osm.pbf"
    pbf = directory / "planet-260713-data-center-fuzzy-review.osm.pbf"
    source.write_bytes(source_payload)
    pbf.write_bytes(pbf_payload)
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
            "sha256": digest(source_payload, "sha256"),
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
                "ways": 3,
                "relations": 1,
            }
        },
        "rights": {
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "copyright_url": "https://www.openstreetmap.org/copyright",
        },
    }
    path = directory / "fuzzy-extract-manifest.json"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path, pbf


class FuzzyFilterAndClassifierTests(unittest.TestCase):
    def test_filter_is_versioned_case_sensitive_any_key_and_any_value(self) -> None:
        expressions = osmium_filter_expressions()
        self.assertEqual(len(expressions), 16)
        self.assertEqual(
            expressions,
            tuple(expression for variant in VARIANTS for expression in (f"nwr/*{variant}*", f"nwr/*=*{variant}*")),
        )
        self.assertFalse(any("DATA CENTER" in expression for expression in expressions))
        contract = filter_manifest_document()
        self.assertEqual(contract["contract_sha256"], FILTER_SHA256)
        self.assertTrue(contract["referenced_nodes_and_members_retained"])

    @unittest.skipUnless(shutil.which("osmium"), "osmium is not installed")
    def test_osmium_119_wildcards_capture_semicolon_unknown_keys_and_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "fixture.osm"
            pbf = directory / "source.pbf"
            filtered = directory / "filtered.pbf"
            xml = directory / "filtered.osm"
            source.write_bytes(FUZZY_XML)
            subprocess.run(["osmium", "cat", str(source), "-o", str(pbf)], check=True)
            subprocess.run(
                ["osmium", "tags-filter", str(pbf), *osmium_filter_expressions(), "-o", str(filtered)],
                check=True,
            )
            subprocess.run(["osmium", "cat", str(filtered), "-o", str(xml)], check=True)
            parsed = parse_osm_xml(xml)
        self.assertIn(100, parsed.ways)
        self.assertIn(300, parsed.relations)
        self.assertIn(200, parsed.ways)
        self.assertIn(20, parsed.nodes)
        self.assertIn(4, parsed.nodes)

    def test_classifier_separates_exact_structural_unknown_text_and_ambiguous(self) -> None:
        cases = {
            "exact_92_pair": {"telecom": "data_center"},
            "explicit_marker_variant": {"building:use": "office;data_center;data_centre"},
            "unknown_key_explicit_value": {"mystery:use": "data centre"},
            "textual_only": {"name": "Former Data Center Cafe"},
            "ambiguous": {"data_center:note": "possible"},
        }
        for expected, tags in cases.items():
            with self.subTest(expected=expected):
                result = classify_tags(tags)
                self.assertIsNotNone(result)
                self.assertEqual(result.classification, expected)
                self.assertTrue(result.trigger_tags)
        self.assertEqual(classify_tags({"construction": "Data Center"}).lifecycle_hint, "under_construction")
        self.assertEqual(classify_tags({"proposed:building": "Data Centre"}).lifecycle_hint, "proposed")
        self.assertEqual(classify_tags({"disused:telecom": "datacentre"}).lifecycle_hint, "lead")


class FuzzyExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.payload = b"synthetic verified planet"
        self.source = self.directory / "planet-test.osm.pbf"
        self.source.write_bytes(self.payload)
        self.output = self.directory / "fuzzy.osm.pbf"
        self.manifest = self.directory / "fuzzy-extract-manifest.json"

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

    def test_plan_preserves_refs_and_verified_run_is_idempotent(self) -> None:
        plan = extract_osm_planet_fuzzy.build_command_plan(
            self.source, self.output, self.manifest, osmium_executable="/test/osmium"
        )
        self.assertEqual(plan.filter_expressions, osmium_filter_expressions())
        self.assertNotIn("-R", plan.tags_filter_command)
        self.assertNotIn("--omit-referenced", plan.tags_filter_command)
        runner = FakeExtractorOsmium()
        times = iter(("2026-07-18T10:00:00Z", "2026-07-18T10:01:00Z"))
        result = extract_osm_planet_fuzzy.extract_fuzzy_planet(
            self.source,
            self.output,
            self.manifest,
            runner=runner,
            clock=lambda: next(times),
            **self.arguments(),
        )
        self.assertEqual(result["pipeline"], EXTRACTION_PIPELINE)
        self.assertTrue(result["review_only"])
        self.assertEqual(result["filter"], filter_manifest_document())
        self.assertEqual(result["source"]["sha256"], digest(self.payload, "sha256"))
        self.assertEqual(result["output"]["sha256"], digest(b"fuzzy-pbf", "sha256"))
        self.assertEqual(result["rights"]["license"], "ODbL-1.0")

        class NeverRun:
            def __call__(self, *_: object, **__: object) -> object:
                raise AssertionError("idempotence must not rerun osmium")

        second = extract_osm_planet_fuzzy.extract_fuzzy_planet(
            self.source, self.output, self.manifest, runner=NeverRun(), **self.arguments()
        )
        self.assertEqual(second, result)

    def test_failed_filter_publishes_nothing(self) -> None:
        with self.assertRaises(Exception):
            extract_osm_planet_fuzzy.extract_fuzzy_planet(
                self.source,
                self.output,
                self.manifest,
                runner=FakeExtractorOsmium(fail=True),
                **self.arguments(),
            )
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.directory.glob(".*extracting*")), [])


class FuzzyMaterializationAndImportTests(unittest.TestCase):
    def test_lossless_materialization_classifies_refs_relations_and_exact_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            xml = Path(temporary) / "fuzzy.osm"
            xml.write_bytes(FUZZY_XML)
            document, integrity = build_fuzzy_overpass_document(parse_osm_xml(xml))
        identities = [(item["type"], item["id"]) for item in document["elements"]]
        self.assertEqual(
            identities,
            [("node", 1), ("node", 2), ("node", 3), ("node", 4), ("node", 5), ("way", 100), ("way", 101), ("relation", 300)],
        )
        self.assertEqual(integrity["exact_layer_duplicate_count"], 1)
        self.assertEqual(integrity["supplemental_eligible_count"], 7)
        relation = document["elements"][-1]
        self.assertEqual(relation["members"][0]["ref"], 200)
        self.assertEqual(relation["geometry"]["type"], "Polygon")
        self.assertEqual(relation["center"], {"lat": 20.5, "lon": 20.5})
        self.assertEqual(relation["fuzzy_discovery"]["classification"], "explicit_marker_variant")
        self.assertEqual(document["materialization"]["classifier_version"], CLASSIFIER_VERSION)

    def test_bundle_is_lineage_bound_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest, pbf = extraction_bundle(directory)
            output = directory / "review-bundle"
            runner = FakeMaterializerOsmium()
            result = materialize_fuzzy_extract(
                manifest,
                output,
                filtered_pbf=pbf,
                osmium_binary="/test/osmium",
                runner=runner,
                clock=lambda: "2026-07-18T12:00:00Z",
            )
            self.assertEqual(result["pipeline"], MATERIALIZATION_PIPELINE)
            self.assertTrue(result["review_only"])
            self.assertEqual(result["counts"]["broad_match_counts"]["total"], 8)
            review = json.loads((output / DEFAULT_JSON_FILENAME).read_text())
            self.assertEqual(review["materialization"]["snapshot_date"], "2026-07-13")

            class NeverRun:
                def __call__(self, *_: object, **__: object) -> object:
                    raise AssertionError("existing verified bundle must not rerun osmium")

            second = materialize_fuzzy_extract(
                manifest, output, filtered_pbf=pbf, runner=NeverRun()
            )
            self.assertEqual(second, result)

            connection, _ = initialize(directory / "bundle-import.sqlite")
            try:
                imported = OpenStreetMapFuzzyDiscoveryAdapter().import_file(
                    connection, output, retrieved_at="2026-07-18T12:30:00Z"
                )
                self.assertEqual(imported.imported_elements, 7)
                metadata = json.loads(
                    connection.execute("SELECT metadata_json FROM evidence LIMIT 1").fetchone()[0]
                )
                self.assertEqual(
                    metadata["provenance"]["planet_source"]["sha256"],
                    digest(b"verified dated planet fixture", "sha256"),
                )
                self.assertEqual(
                    metadata["provenance"]["materialization_manifest"]["pipeline"],
                    MATERIALIZATION_PIPELINE,
                )
            finally:
                connection.close()

    def test_adapter_imports_only_supplemental_facility_leads_and_no_other_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            xml = directory / "fuzzy.osm"
            review = directory / "fuzzy-review.json"
            database = directory / "atlas.sqlite"
            xml.write_bytes(FUZZY_XML)
            document, _ = build_fuzzy_overpass_document(parse_osm_xml(xml))
            document["materialization"]["snapshot_date"] = "2026-07-13"
            review.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            connection, _ = initialize(database)
            try:
                adapter = OpenStreetMapFuzzyDiscoveryAdapter()
                first = adapter.import_file(
                    connection, review, retrieved_at="2026-07-18T13:00:00Z"
                )
                second = adapter.import_file(
                    connection, review, retrieved_at="2026-07-18T13:00:00Z"
                )
                self.assertEqual(first.examined_elements, 8)
                self.assertEqual(first.imported_elements, 7)
                self.assertEqual(first.skipped_elements, 1)
                self.assertEqual(first.entities_created, 7)
                self.assertEqual(second.entities_created, 0)
                self.assertEqual(second.evidence_created, 0)
                entity_counts = connection.execute(
                    "SELECT kind, COUNT(*) AS count FROM entities GROUP BY kind"
                ).fetchall()
                self.assertEqual([(row["kind"], row["count"]) for row in entity_counts], [("facility", 7)])
                statuses = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT status, COUNT(*) FROM lifecycle_observations GROUP BY status"
                    )
                }
                self.assertEqual(statuses, {"lead": 5, "proposed": 1, "under_construction": 1})
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0], 0)
                evidence = connection.execute(
                    "SELECT source_family, source_url, metadata_json FROM evidence ORDER BY source_url"
                ).fetchall()
                self.assertTrue(all(row["source_family"] == "openstreetmap:fuzzy_discovery" for row in evidence))
                self.assertTrue(all(row["source_url"].startswith("https://www.openstreetmap.org/") for row in evidence))
                metadata = [json.loads(row["metadata_json"]) for row in evidence]
                self.assertTrue(all(item["upstream_source_root"] == "openstreetmap" for item in metadata))
                self.assertTrue(all(item["review_only"] for item in metadata))
                self.assertFalse(any("node/1" in row["source_url"] for row in evidence))
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
