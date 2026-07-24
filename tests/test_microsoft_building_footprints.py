from __future__ import annotations

import base64
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

from datacenter_atlas.microsoft_building_footprints import (
    INDEX_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    REVIEW_FILENAME,
    MicrosoftBuildingFootprintsError,
    fetch_and_build_bundle,
    inventory_index,
    validate_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_DEFINITION = (
    PROJECT_ROOT
    / "sources"
    / "microsoft-global-ml-building-footprints-2026-07-18-v1.json"
)
PINNED_BUNDLE = (
    PROJECT_ROOT
    / "source_cache"
    / "microsoft-global-ml-buildings-2026-07-18-v1"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _md5_base64(raw: bytes) -> str:
    return base64.b64encode(
        hashlib.md5(raw, usedforsecurity=False).digest()
    ).decode("ascii")


def _canonical(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, indent=2, sort_keys=True)
    else:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode()


def _feature(
    longitude: float,
    latitude: float,
    *,
    height: float = -1.0,
    confidence: float = -1.0,
) -> dict[str, object]:
    delta = 0.0001
    return {
        "type": "Feature",
        "properties": {"height": height, "confidence": confidence},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [longitude - delta, latitude - delta],
                    [longitude + delta, latitude - delta],
                    [longitude + delta, latitude + delta],
                    [longitude - delta, latitude + delta],
                    [longitude - delta, latitude - delta],
                ]
            ],
        },
    }


def _master_row(
    row_id: str,
    name: str,
    country: str,
    longitude: float,
    latitude: float,
    status: str,
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "tier": "A",
        "entity": {
            "name": name,
            "country": country,
            "kind": "campus",
            "longitude": longitude,
            "latitude": latitude,
        },
        "lifecycle": {
            "normalized_status": status,
            "reported_status": status,
            "reported_status_date": "2026-07-17",
        },
        "construction": {
            "method": "fixture_source_supported",
            "source_supported": True,
            "verification_status": "source_supported_not_independently_verified",
            "verified": False,
        },
        "source": {
            "release_id": "fixture-release",
            "record_id": f"source-{row_id}",
            "manifest_sha256": "1" * 64,
            "artifact_sha256": "2" * 64,
            "source_url": "https://example.test/construction",
            "source_license": "CC-BY-4.0",
            "evidence_ids": [f"evidence-{row_id}"],
        },
    }


class _FixtureDownloader:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.calls: list[str] = []

    def download(self, url: str, destination: Path, expected_bytes: int) -> dict:
        self.calls.append(url)
        raw = self.objects[url]
        if len(raw) != expected_bytes:
            raise AssertionError("fixture byte pin differs")
        destination.write_bytes(raw)
        return {"bytes": len(raw), "sha256": _sha256(raw)}


def _fixture(root: Path) -> tuple[Path, Path, _FixtureDownloader, dict[str, object]]:
    license_raw = b"Fixture Microsoft data license\n"
    readme_raw = b"Fixture pinned upstream documentation\n"
    pilots = [
        {
            "pilot_id": "iceland-fixture",
            "location": "Iceland",
            "quadkey": "031013111",
            "center": (-22.54, 63.96),
            "bbox": [-22.56, 63.955, -22.52, 63.965],
            "row_id": "row-iceland",
            "name": "M24 fixture",
            "status": "under_construction",
            "features": [
                _feature(-22.54, 63.96),
                _feature(-22.545, 63.959, height=12.0, confidence=0.8),
                _feature(-22.4, 64.1),
            ],
            "selected": 2,
        },
        {
            "pilot_id": "portugal-fixture",
            "location": "Portugal",
            "quadkey": "033110213",
            "center": (-8.81, 37.93),
            "bbox": [-8.82, 37.925, -8.80, 37.935],
            "row_id": "row-portugal",
            "name": "Sines fixture",
            "status": "expansion",
            "features": [_feature(-8.81, 37.93)],
            "selected": 1,
        },
    ]
    master_lines = [
        _canonical(
            _master_row(
                pilot["row_id"],
                pilot["name"],
                pilot["location"],
                pilot["center"][0],
                pilot["center"][1],
                pilot["status"],
            )
        )
        for pilot in pilots
    ]
    master_raw = b"".join(master_lines)
    master_path = root / "construction-master.jsonl"
    master_path.write_bytes(master_raw)
    master_manifest_raw = _canonical(
        {
            "outputs": {
                master_path.name: {
                    "bytes": len(master_raw),
                    "sha256": _sha256(master_raw),
                }
            }
        },
        pretty=True,
    )
    (root / MANIFEST_FILENAME).write_bytes(master_manifest_raw)
    (root / MANIFEST_HASH_FILENAME).write_text(
        f"{_sha256(master_manifest_raw)}  {MANIFEST_FILENAME}\n"
    )

    objects: dict[str, bytes] = {}
    index_rows: list[str] = []
    pilot_definitions: list[dict[str, object]] = []
    for line_number, (pilot, master_line) in enumerate(
        zip(pilots, master_lines), 1
    ):
        decompressed = b"".join(_canonical(feature) for feature in pilot["features"])
        compressed = gzip.compress(decompressed, mtime=0)
        url = (
            "https://minedbuildings.z5.web.core.windows.net/global-buildings/"
            "fixture/global-buildings.geojsonl/"
            f"RegionName={pilot['location']}/quadkey={pilot['quadkey']}/"
            "part-fixture.csv.gz"
        )
        objects[url] = compressed
        index_rows.append(
            f"{pilot['location']},{pilot['quadkey']},{url},{len(compressed)}B,2026-02-23\n"
        )
        longitude, latitude = pilot["center"]
        pilot_definitions.append(
            {
                "advertised_size": f"{len(compressed)}B",
                "aoi": {
                    "bbox": pilot["bbox"],
                    "center_latitude": latitude,
                    "center_longitude": longitude,
                },
                "construction_prior": {
                    "construction_method": "fixture_source_supported",
                    "country": pilot["location"],
                    "entity_kind": "campus",
                    "evidence_ids": [f"evidence-{pilot['row_id']}"],
                    "latitude": latitude,
                    "longitude": longitude,
                    "name": pilot["name"],
                    "normalized_status": pilot["status"],
                    "reported_status": pilot["status"],
                    "reported_status_date": "2026-07-17",
                    "row_id": pilot["row_id"],
                    "source_artifact_sha256": "2" * 64,
                    "source_line_bytes": len(master_line),
                    "source_line_number": line_number,
                    "source_line_sha256": _sha256(master_line),
                    "source_license": "CC-BY-4.0",
                    "source_manifest_sha256": "1" * 64,
                    "source_record_id": f"source-{pilot['row_id']}",
                    "source_release_id": "fixture-release",
                    "source_url": "https://example.test/construction",
                    "tier": "A",
                },
                "content_md5_base64": _md5_base64(compressed),
                "country_specific": True,
                "decompressed_bytes": len(decompressed),
                "decompressed_sha256": _sha256(decompressed),
                "etag": '"fixture"',
                "expected_selected_features": pilot["selected"],
                "expected_source_features": len(pilot["features"]),
                "last_modified": "Tue, 03 Feb 2026 23:36:27 GMT",
                "location": pilot["location"],
                "pilot_id": pilot["pilot_id"],
                "quadkey": pilot["quadkey"],
                "shard_bytes": len(compressed),
                "shard_filename": (
                    f"shard-{pilot['location']}-{pilot['quadkey']}.csv.gz"
                ),
                "shard_sha256": _sha256(compressed),
                "shard_url": url,
                "upload_date": "2026-02-23",
            }
        )

    index_raw = (
        "Location,QuadKey,Url,Size,UploadDate\n" + "".join(index_rows)
    ).encode()
    index_url = (
        "https://minedbuildings.z5.web.core.windows.net/global-buildings/"
        "dataset-links.csv"
    )
    license_url = (
        "https://raw.githubusercontent.com/microsoft/GlobalMLBuildingFootprints/"
        f"{'a' * 40}/LICENSE"
    )
    readme_url = (
        "https://raw.githubusercontent.com/microsoft/GlobalMLBuildingFootprints/"
        f"{'a' * 40}/README.md"
    )
    objects[index_url] = index_raw
    objects[license_url] = license_raw
    objects[readme_url] = readme_raw
    advertised = sum(len(objects[pilot["shard_url"]]) for pilot in pilot_definitions)
    definition = {
        "bundle_id": "microsoft-buildings-fixture-v1",
        "construction_master": {
            "bytes": len(master_raw),
            "manifest_sha256": _sha256(master_manifest_raw),
            "path": "fixtures/construction-master.jsonl",
            "sha256": _sha256(master_raw),
        },
        "format": "datacenter-atlas-microsoft-global-ml-buildings-review-v1",
        "generated_at": "2026-07-18T23:10:00Z",
        "pilots": pilot_definitions,
        "schema_version": 1,
        "selection": {
            "aoi_half_width_m": 1000,
            "continental_duplicate_shards_excluded": True,
            "country_specific_shards_only": True,
            "geometry_predicate": (
                "source_footprint_bbox_intersects_inclusive_aoi_bbox"
            ),
            "maximum_aoi_area_km2": 4.1,
        },
        "upstream": {
            "data_license": "CDLA-Permissive-2.0",
            "dataset_id": "microsoft-global-ml-building-footprints",
            "index": {
                "advertised_compressed_bytes_binary_approx": advertised,
                "bytes": len(index_raw),
                "content_md5_base64": _md5_base64(index_raw),
                "etag": '"fixture-index"',
                "expected_locations": 2,
                "expected_rows": 2,
                "expected_unique_location_quadkeys": 2,
                "expected_unique_urls": 2,
                "last_modified": "Wed, 25 Feb 2026 23:01:46 GMT",
                "sha256": _sha256(index_raw),
                "url": index_url,
            },
            "publisher": "Microsoft",
            "repository": {
                "commit": "a" * 40,
                "license_file": {
                    "bytes": len(license_raw),
                    "sha256": _sha256(license_raw),
                },
                "license_url": license_url,
                "readme_file": {
                    "bytes": len(readme_raw),
                    "sha256": _sha256(readme_raw),
                },
                "readme_url": readme_url,
                "url": "https://github.com/microsoft/GlobalMLBuildingFootprints",
            },
        },
    }
    definition_path = root / "definition.json"
    definition_path.write_bytes(_canonical(definition, pretty=True))
    return definition_path, master_path, _FixtureDownloader(objects), definition


def _thaw(directory: Path) -> None:
    directory.chmod(0o755)
    for entry in directory.iterdir():
        entry.chmod(0o644)


def _freeze(directory: Path) -> None:
    for entry in directory.iterdir():
        entry.chmod(0o444)
    directory.chmod(0o555)


class MicrosoftBuildingFootprintsTests(unittest.TestCase):
    def test_fixture_fetch_builds_and_validates_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            manifest = fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            self.assertEqual(len(downloader.calls), 5)
            self.assertEqual(manifest["totals"]["selected_features"], 3)
            validated = validate_bundle(output, definition_path=definition)
            self.assertEqual(validated, manifest)
            self.assertEqual(len(downloader.calls), 5)

    def test_inventory_preserves_every_row_and_binary_size_sum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, _, downloader, fixture = _fixture(root)
            index = root / "index.csv"
            index.write_bytes(
                downloader.objects[fixture["upstream"]["index"]["url"]]
            )
            rows, locations, summary = inventory_index(
                index, definition_path=definition
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(locations), 2)
            self.assertEqual(summary["selected_country_shards"], 2)
            self.assertEqual(
                summary["advertised_compressed_bytes_binary_approx"],
                fixture["upstream"]["index"][
                    "advertised_compressed_bytes_binary_approx"
                ],
            )

    def test_rows_are_non_merging_and_preserve_attribute_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            rows = [json.loads(line) for line in (output / REVIEW_FILENAME).read_text().splitlines()]
            self.assertEqual(len(rows), 3)
            for row in rows:
                properties = row["properties"]
                self.assertTrue(properties["review_only"])
                self.assertFalse(properties["auto_merge_permitted"])
                self.assertFalse(properties["independent_lifecycle_corroboration"])
                self.assertTrue(
                    all(value is None for value in properties["atlas_fields"].values())
                )
            measured = next(
                row
                for row in rows
                if row["properties"]["source_attributes"]["height_raw"] == 12.0
            )
            attributes = measured["properties"]["source_attributes"]
            self.assertEqual(attributes["height_m"], 12.0)
            self.assertEqual(attributes["footprint_confidence"], 0.8)
            self.assertTrue(attributes["confidence_applies_to_footprint_not_height"])

    def test_published_permissions_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
            self.assertTrue(
                all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in output.iterdir())
            )

    def test_permission_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            output.chmod(0o755)
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "not frozen 0555"
            ):
                validate_bundle(output, definition_path=definition)

    def test_frozen_source_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, fixture = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            copied = root / "copied"
            shutil.copytree(output, copied)
            _thaw(copied)
            shard = copied / fixture["pilots"][0]["shard_filename"]
            shard.write_bytes(shard.read_bytes() + b"tamper")
            _freeze(copied)
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "bundle output changed"
            ):
                validate_bundle(copied, definition_path=definition)

    def test_manifest_rehash_cannot_promote_a_review_row(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            copied = root / "copied"
            shutil.copytree(output, copied)
            _thaw(copied)
            review_path = copied / REVIEW_FILENAME
            lines = review_path.read_text().splitlines()
            row = json.loads(lines[0])
            row["properties"]["atlas_fields"]["data_centre_identity"] = "promoted"
            row["properties"]["auto_merge_permitted"] = True
            lines[0] = _canonical(row).decode().rstrip("\n")
            review_raw = ("\n".join(lines) + "\n").encode()
            review_path.write_bytes(review_raw)
            manifest_path = copied / MANIFEST_FILENAME
            manifest = json.loads(manifest_path.read_text())
            manifest["outputs"][REVIEW_FILENAME].update(
                {"bytes": len(review_raw), "sha256": _sha256(review_raw)}
            )
            manifest_raw = _canonical(manifest, pretty=True)
            manifest_path.write_bytes(manifest_raw)
            (copied / MANIFEST_HASH_FILENAME).write_text(
                f"{_sha256(manifest_raw)}  {MANIFEST_FILENAME}\n"
            )
            _freeze(copied)
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "offline reproduction"
            ):
                validate_bundle(copied, definition_path=definition)

    def test_closed_bundle_rejects_an_extra_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            output = root / "bundle"
            fetch_and_build_bundle(
                definition,
                output,
                construction_master_path=master,
                downloader=downloader,
            )
            output.chmod(0o755)
            extra = output / "untracked.txt"
            extra.write_text("unexpected")
            extra.chmod(0o444)
            output.chmod(0o555)
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "closed file set"
            ):
                validate_bundle(output, definition_path=definition)

    def test_continental_duplicate_shard_definition_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition_path, _, downloader, definition = _fixture(root)
            changed = deepcopy(definition)
            changed["pilots"][0]["location"] = "Europe"
            changed["pilots"][0]["shard_filename"] = "shard-Europe-031013111.csv.gz"
            changed["pilots"][0]["shard_url"] = changed["pilots"][0][
                "shard_url"
            ].replace("RegionName=Iceland", "RegionName=Europe")
            changed_path = root / "continental.json"
            changed_path.write_bytes(_canonical(changed, pretty=True))
            index = root / "index.csv"
            index.write_bytes(
                downloader.objects[definition["upstream"]["index"]["url"]]
            )
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "non-continental"
            ):
                inventory_index(index, definition_path=changed_path)
            self.assertTrue(definition_path.exists())

    def test_construction_master_checkpoint_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition, master, downloader, _ = _fixture(root)
            master.write_bytes(master.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(
                MicrosoftBuildingFootprintsError, "construction master checkpoint"
            ):
                fetch_and_build_bundle(
                    definition,
                    root / "bundle",
                    construction_master_path=master,
                    downloader=downloader,
                )

    def test_pinned_real_bundle_validates_with_exact_counts_after_chmod(self) -> None:
        manifest = validate_bundle(
            PINNED_BUNDLE,
            definition_path=PINNED_DEFINITION,
            require_frozen=True,
        )
        self.assertEqual(manifest["inventory"]["index_rows"], 30344)
        self.assertEqual(manifest["inventory"]["locations"], 225)
        self.assertEqual(manifest["totals"]["source_features_in_selected_shards"], 476989)
        self.assertEqual(manifest["totals"]["selected_features"], 671)
        self.assertEqual(manifest["totals"]["height_present_selected_features"], 0)
        self.assertEqual(manifest["totals"]["confidence_present_selected_features"], 0)


if __name__ == "__main__":
    unittest.main()
