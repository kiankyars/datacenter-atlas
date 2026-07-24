from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from datacenter_atlas.ohsome import DATA_CENTER_FILTER
from datacenter_atlas.scripts import extract_osm_planet, fetch_osm_planet
from datacenter_atlas.taginfo_targets import explicit_tag_pairs


class FakeOsmium:
    def __init__(
        self,
        *,
        output_payload: bytes = b"filtered-pbf",
        fail_tags_filter: bool = False,
        invalid_fileinfo: bool = False,
    ) -> None:
        self.output_payload = output_payload
        self.fail_tags_filter = fail_tags_filter
        self.invalid_fileinfo = invalid_fileinfo
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                command,
                0,
                "osmium version 1.19.1\nlibosmium version 2.23.1\n",
                "",
            )
        if command[1] == "tags-filter":
            temporary_output = Path(command[command.index("--output") + 1])
            temporary_output.write_bytes(self.output_payload)
            if self.fail_tags_filter:
                return subprocess.CompletedProcess(command, 1, "", "synthetic failure")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[1] == "fileinfo":
            if self.invalid_fileinfo:
                return subprocess.CompletedProcess(command, 0, "not-json", "")
            output = Path(command[-1])
            document = {
                "file": {
                    "name": str(output),
                    "format": "PBF",
                    "compression": "none",
                    "size": output.stat().st_size,
                },
                "header": {
                    "boxes": [[[-180.0, -90.0], [180.0, 90.0]]],
                    "with_history": False,
                    "option": {
                        "generator": extract_osm_planet.GENERATOR,
                        "osmosis_replication_timestamp": "2026-07-13T00:59:57Z",
                    },
                },
                "data": {
                    "bbox": [[-99.0, 32.0], [1.0, 52.0]],
                    "timestamp": {
                        "first": "2009-01-01T00:00:00Z",
                        "last": "2026-07-13T00:59:57Z",
                    },
                    "objects_ordered": True,
                    "multiple_versions": False,
                    "crc32": "0123abcd",
                    "count": {
                        "nodes": 17,
                        "ways": 4,
                        "relations": 2,
                        "changesets": 0,
                    },
                },
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(document), "")
        raise AssertionError(f"unexpected command: {command}")


def digest(payload: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, payload).hexdigest()


def fetch_manifest_document(
    *,
    source: Path,
    payload: bytes,
    snapshot_date: str,
    source_url: str,
) -> dict[str, object]:
    md5 = digest(payload, "md5")
    sidecar_payload = f"{md5}  {source.name}\n".encode("ascii")
    return {
        "schema_version": 1,
        "pipeline": "openstreetmap_planet_fetch",
        "state": "completed",
        "snapshot_date": snapshot_date,
        "source": {
            "url": source_url,
            "md5_url": f"{source_url}.md5",
            "filename": source.name,
            "expected_bytes": len(payload),
            "expected_md5": md5,
        },
        "sidecar": {
            "url": f"{source_url}.md5",
            "path": f"{source.name}.md5",
            "bytes": len(sidecar_payload),
            "md5": md5,
            "sha256": digest(sidecar_payload, "sha256"),
            "http_status": 200,
        },
        "input": {
            "path": source.name,
            "bytes": len(payload),
            "md5": md5,
            "sha256": digest(payload, "sha256"),
        },
        "verification": {
            "exact_size": True,
            "official_md5": True,
            "verified_before_extraction": True,
        },
        "rights": {
            "license": fetch_osm_planet.OSM_LICENSE,
            "attribution": fetch_osm_planet.OSM_ATTRIBUTION,
            "copyright_url": fetch_osm_planet.OSM_COPYRIGHT_URL,
        },
    }


class OSMPlanetExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.source_payload = b"synthetic verified Planet PBF"
        self.source = self.directory / "planet-test.osm.pbf"
        self.source.write_bytes(self.source_payload)
        self.output = self.directory / "planet-test-data-centers.osm.pbf"
        self.manifest = self.directory / "extract-manifest.json"
        self.snapshot_date = "2026-07-13"
        self.source_url = "https://planet.openstreetmap.org/pbf/planet-test.osm.pbf"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def extraction_arguments(self) -> dict[str, object]:
        return {
            "expected_snapshot_date": self.snapshot_date,
            "expected_filename": self.source.name,
            "expected_source_url": self.source_url,
            "expected_size": len(self.source_payload),
            "expected_md5": digest(self.source_payload, "md5"),
            "osmium_executable": "/test/bin/osmium",
        }

    def test_plan_contains_all_exact_pairs_for_nodes_ways_and_relations(self) -> None:
        pairs = explicit_tag_pairs(DATA_CENTER_FILTER)
        self.assertEqual(len(pairs), 92)
        plan = extract_osm_planet.build_command_plan(
            self.source,
            self.output,
            self.manifest,
            osmium_executable="/test/bin/osmium",
        )
        expected = tuple(f"nwr/{key}={value}" for key, value in pairs)
        self.assertEqual(plan.filter_expressions, expected)
        self.assertEqual(plan.tags_filter_command[-92:], expected)
        self.assertNotIn("-R", plan.tags_filter_command)
        self.assertNotIn("--omit-referenced", plan.tags_filter_command)
        self.assertNotIn("-t", plan.tags_filter_command)
        self.assertNotIn("--remove-tags", plan.tags_filter_command)
        self.assertIn("--fsync", plan.tags_filter_command)
        self.assertEqual(
            plan,
            extract_osm_planet.build_command_plan(
                self.source,
                self.output,
                self.manifest,
                osmium_executable="/test/bin/osmium",
            ),
        )
        dry_run = plan.dry_run_document()
        self.assertTrue(dry_run["dry_run"])
        self.assertEqual(dry_run["filter"]["equality_pair_count"], 92)
        self.assertEqual(
            dry_run["filter"]["match_scope"],
            "all_relations_including_non_area_relations",
        )
        self.assertTrue(dry_run["filter"]["referenced_nodes_and_members_retained"])

    def test_verified_extraction_records_full_provenance_and_is_idempotent(self) -> None:
        fetch_manifest = self.directory / "fetch-manifest.json"
        fetch_manifest.write_text(
            json.dumps(
                fetch_manifest_document(
                    source=self.source,
                    payload=self.source_payload,
                    snapshot_date=self.snapshot_date,
                    source_url=self.source_url,
                )
            )
        )
        runner = FakeOsmium()
        timestamps = iter(("2026-07-18T10:00:00Z", "2026-07-18T10:01:00Z"))
        result = extract_osm_planet.extract_planet(
            self.source,
            self.output,
            self.manifest,
            fetch_manifest_path=fetch_manifest,
            runner=runner,
            clock=lambda: next(timestamps),
            invocation=["python", "extract_osm_planet.py"],
            **self.extraction_arguments(),
        )

        self.assertEqual(self.output.read_bytes(), b"filtered-pbf")
        self.assertEqual(result, json.loads(self.manifest.read_text()))
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(
            result["pipeline"], "openstreetmap_planet_data_center_extraction"
        )
        self.assertEqual(result["state"], "completed")
        self.assertEqual(
            result["source"]["verification"]["mode"],
            "completed_fetch_manifest_plus_exact_size_and_md5",
        )
        self.assertEqual(
            result["source"]["fetch_manifest"]["sha256"],
            digest(fetch_manifest.read_bytes(), "sha256"),
        )
        self.assertEqual(result["output"]["bytes"], len(b"filtered-pbf"))
        self.assertEqual(result["output"]["sha256"], digest(b"filtered-pbf", "sha256"))
        self.assertEqual(
            result["fileinfo"]["object_counts_including_references"],
            {"nodes": 17, "ways": 4, "relations": 2, "changesets": 0},
        )
        self.assertEqual(
            result["fileinfo"]["timestamps"]["last"], "2026-07-13T00:59:57Z"
        )
        self.assertEqual(result["fileinfo"]["bounds"]["data"][1], [1.0, 52.0])
        self.assertEqual(result["rights"]["license"], "ODbL-1.0")
        self.assertEqual(result["rights"]["attribution"], "© OpenStreetMap contributors")
        tags_command = runner.calls[1]
        self.assertEqual(tags_command[1], "tags-filter")
        self.assertEqual(len(tags_command[-92:]), 92)

        class UnexpectedRunner:
            def __call__(self, *_: object, **__: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("idempotent validation must not rerun osmium")

        second = extract_osm_planet.extract_planet(
            self.source,
            self.output,
            self.manifest,
            fetch_manifest_path=fetch_manifest,
            runner=UnexpectedRunner(),
            **self.extraction_arguments(),
        )
        self.assertEqual(second, result)

    def test_exact_size_and_md5_are_sufficient_without_fetch_manifest(self) -> None:
        verified = extract_osm_planet.verify_source(
            self.source,
            **{
                key: value
                for key, value in self.extraction_arguments().items()
                if key != "osmium_executable"
            },
        )
        self.assertEqual(verified.verification_mode, "exact_size_and_md5")
        self.assertEqual(verified.sha256, digest(self.source_payload, "sha256"))

    def test_fetch_manifest_must_match_the_verified_source(self) -> None:
        document = fetch_manifest_document(
            source=self.source,
            payload=self.source_payload,
            snapshot_date=self.snapshot_date,
            source_url=self.source_url,
        )
        document["input"]["sha256"] = "0" * 64
        fetch_manifest = self.directory / "fetch-manifest.json"
        fetch_manifest.write_text(json.dumps(document))
        with self.assertRaisesRegex(
            extract_osm_planet.ExtractionError, "input.sha256"
        ):
            extract_osm_planet.verify_source(
                self.source,
                fetch_manifest_path=fetch_manifest,
                **{
                    key: value
                    for key, value in self.extraction_arguments().items()
                    if key != "osmium_executable"
                },
            )

    def test_source_size_digest_and_symlink_are_rejected(self) -> None:
        arguments = {
            key: value
            for key, value in self.extraction_arguments().items()
            if key != "osmium_executable"
        }
        with self.assertRaisesRegex(extract_osm_planet.ExtractionError, "expected exactly"):
            extract_osm_planet.verify_source(
                self.source, **{**arguments, "expected_size": len(self.source_payload) + 1}
            )
        with self.assertRaisesRegex(extract_osm_planet.ExtractionError, "MD5"):
            extract_osm_planet.verify_source(
                self.source, **{**arguments, "expected_md5": "0" * 32}
            )
        linked_source = self.directory / "planet-linked.osm.pbf"
        linked_source.symlink_to(self.source)
        with self.assertRaisesRegex(extract_osm_planet.ExtractionError, "symlink"):
            extract_osm_planet.verify_source(
                linked_source,
                **{**arguments, "expected_filename": linked_source.name},
            )

    def test_tags_filter_failure_leaves_no_publishable_artifact(self) -> None:
        runner = FakeOsmium(fail_tags_filter=True)
        with self.assertRaisesRegex(extract_osm_planet.ExtractionError, "synthetic failure"):
            extract_osm_planet.extract_planet(
                self.source,
                self.output,
                self.manifest,
                runner=runner,
                clock=lambda: "2026-07-18T10:00:00Z",
                **self.extraction_arguments(),
            )
        plan = extract_osm_planet.build_command_plan(
            self.source,
            self.output,
            self.manifest,
            osmium_executable="/test/bin/osmium",
        )
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(plan.temporary_output_path.exists())
        self.assertFalse(plan.temporary_manifest_path.exists())

    def test_invalid_fileinfo_leaves_no_publishable_artifact(self) -> None:
        runner = FakeOsmium(invalid_fileinfo=True)
        with self.assertRaisesRegex(extract_osm_planet.ExtractionError, "valid JSON"):
            extract_osm_planet.extract_planet(
                self.source,
                self.output,
                self.manifest,
                runner=runner,
                clock=lambda: "2026-07-18T10:00:00Z",
                **self.extraction_arguments(),
            )
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_fetch_verifiers_reject_symlinks(self) -> None:
        sidecar_target = self.directory / "sidecar-target"
        sidecar_target.write_text(
            f"{fetch_osm_planet.PLANET_MD5}  {fetch_osm_planet.PLANET_FILENAME}\n"
        )
        sidecar_link = self.directory / fetch_osm_planet.PLANET_MD5_FILENAME
        sidecar_link.symlink_to(sidecar_target)
        with self.assertRaisesRegex(fetch_osm_planet.VerificationError, "symlink"):
            fetch_osm_planet.verify_cached_sidecar(sidecar_link)
        pbf_link = self.directory / fetch_osm_planet.PLANET_FILENAME
        pbf_link.symlink_to(self.source)
        with self.assertRaisesRegex(fetch_osm_planet.VerificationError, "symlink"):
            fetch_osm_planet.verify_exact_file(
                pbf_link,
                expected_size=len(self.source_payload),
                expected_md5=digest(self.source_payload, "md5"),
            )

    @unittest.skipUnless(shutil.which("osmium"), "osmium-tool is not installed")
    def test_real_osmium_retains_way_nodes_and_non_area_relation_members(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "osm_planet_minimal.osm"
        real_source = self.directory / "planet-real-test.osm.pbf"
        subprocess.run(
            ["osmium", "cat", "--output", str(real_source), str(fixture)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        real_output = self.directory / "planet-real-test-data-centers.osm.pbf"
        real_manifest = self.directory / "real-extract-manifest.json"
        payload = real_source.read_bytes()
        result = extract_osm_planet.extract_planet(
            real_source,
            real_output,
            real_manifest,
            expected_snapshot_date=self.snapshot_date,
            expected_filename=real_source.name,
            expected_source_url="https://example.test/planet-real-test.osm.pbf",
            expected_size=len(payload),
            expected_md5=digest(payload, "md5"),
            osmium_executable=extract_osm_planet.resolve_osmium(),
            clock=iter(("2026-07-18T10:00:00Z", "2026-07-18T10:01:00Z")).__next__,
        )
        self.assertEqual(
            result["fileinfo"]["object_counts_including_references"],
            {"nodes": 6, "ways": 1, "relations": 1, "changesets": 0},
        )
        self.assertEqual(
            result["filter"]["match_scope"],
            "all_relations_including_non_area_relations",
        )


if __name__ == "__main__":
    unittest.main()
