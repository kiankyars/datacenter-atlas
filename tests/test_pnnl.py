from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.pnnl import (
    PNNL_IM3_ARTIFACT,
    PNNL_IM3_ARTIFACT_URL,
    PNNL_IM3_DOI,
    PNNL_IM3_EXPECTED_BYTES,
    PNNL_IM3_SHA256,
    PNNL_IM3_SOURCE_FAMILY,
    PNNL_IM3_VERSION,
    ArtifactSpec,
    PNNLIM3Fetcher,
    PNNLIM3GeoPackageAdapter,
    parse_geopackage_geometry,
)
from datacenter_atlas.service import validate_database


RETRIEVED_AT = "2026-07-17T19:00:00Z"


def _point_wkb(longitude: float, latitude: float) -> bytes:
    return b"\x01" + struct.pack("<I2d", 1, longitude, latitude)


def _polygon_wkb(ring: list[tuple[float, float]]) -> bytes:
    return (
        b"\x01"
        + struct.pack("<II", 3, 1)
        + struct.pack("<I", len(ring))
        + b"".join(struct.pack("<2d", *point) for point in ring)
    )


def _multipolygon_wkb(polygons: list[bytes]) -> bytes:
    return b"\x01" + struct.pack("<II", 6, len(polygons)) + b"".join(polygons)


def _gpkg_geometry(
    wkb: bytes,
    envelope: tuple[float, float, float, float] | None = None,
) -> bytes:
    flags = 1 if envelope is None else 3
    header = b"GP" + bytes((0, flags)) + struct.pack("<i", 4326)
    if envelope is not None:
        header += struct.pack("<4d", *envelope)
    return header + wkb


def _create_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        PRAGMA application_id = 1196444487;

        CREATE TABLE gpkg_contents (
            table_name TEXT PRIMARY KEY,
            data_type TEXT NOT NULL,
            identifier TEXT,
            srs_id INTEGER
        );
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT PRIMARY KEY,
            column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL,
            srs_id INTEGER NOT NULL,
            z INTEGER NOT NULL,
            m INTEGER NOT NULL
        );
        """
    )
    for layer, geometry_type in (
        ("point", "POINT"),
        ("building", "POLYGON"),
        ("campus", "MULTIPOLYGON"),
    ):
        connection.execute(
            "INSERT INTO gpkg_contents(table_name, data_type, identifier, srs_id) "
            "VALUES (?, 'features', ?, 4326)",
            (layer, layer),
        )
        connection.execute(
            "INSERT INTO gpkg_geometry_columns("
            "table_name, column_name, geometry_type_name, srs_id, z, m"
            ") VALUES (?, 'geom', ?, 4326, 0, 0)",
            (layer, geometry_type),
        )
        connection.execute(
            f"""
            CREATE TABLE {layer} (
                fid INTEGER PRIMARY KEY,
                geom {geometry_type},
                id TEXT,
                state TEXT,
                state_abb TEXT,
                state_id TEXT,
                county TEXT,
                county_id TEXT,
                operator TEXT,
                ref TEXT,
                name TEXT,
                sqft REAL,
                lon REAL,
                lat REAL,
                type TEXT
            )
            """
        )

    point = _gpkg_geometry(_point_wkb(-77.0, 38.9))
    building_ring = [
        (-84.6, 33.7),
        (-84.5, 33.7),
        (-84.5, 33.8),
        (-84.6, 33.8),
        (-84.6, 33.7),
    ]
    building = _gpkg_geometry(
        _polygon_wkb(building_ring),
        (-84.6, -84.5, 33.7, 33.8),
    )
    campus_ring = [
        (-93.8, 41.4),
        (-93.7, 41.4),
        (-93.7, 41.5),
        (-93.8, 41.5),
        (-93.8, 41.4),
    ]
    campus = _gpkg_geometry(
        _multipolygon_wkb([_polygon_wkb(campus_ring)]),
        (-93.8, -93.7, 41.4, 41.5),
    )
    insert = (
        "INSERT INTO {layer}("
        "fid, geom, id, state, state_abb, state_id, county, county_id, "
        "operator, ref, name, sqft, lon, lat, type"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    connection.execute(
        insert.format(layer="point"),
        (
            1,
            point,
            "00000000001",
            "District of Columbia",
            "DC",
            "11",
            "District of Columbia",
            "001",
            "CoreSite",
            None,
            "CoreSite DC1",
            None,
            -77.0,
            38.9,
            "point",
        ),
    )
    building_values = (
        building,
        "00000000002",
        "Georgia",
        "GA",
        "13",
        "Digital Realty",
        "ATL11",
        "Digital Realty Atlanta ATL11",
        313_479.0,
        -84.55,
        33.75,
        "building",
    )
    connection.execute(
        insert.format(layer="building"),
        (2, *building_values[:5], "Douglas County", "097", *building_values[5:]),
    )
    connection.execute(
        insert.format(layer="building"),
        (3, *building_values[:5], "Cobb County", "067", *building_values[5:]),
    )
    connection.execute(
        insert.format(layer="campus"),
        (
            4,
            campus,
            "00000000003",
            "Iowa",
            "IA",
            "19",
            "Madison County",
            "121",
            "Microsoft",
            None,
            "Project Osmium",
            3_691_114.0,
            -93.75,
            41.45,
            "campus",
        ),
    )
    connection.commit()
    connection.close()


def _fixture_artifact(path: Path) -> ArtifactSpec:
    raw = path.read_bytes()
    return replace(
        PNNL_IM3_ARTIFACT,
        expected_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        filename=path.name,
    )


class PNNLIM3ConstantsTests(unittest.TestCase):
    def test_official_artifact_pin_is_exact(self) -> None:
        self.assertEqual(PNNL_IM3_EXPECTED_BYTES, 843_776)
        self.assertEqual(
            PNNL_IM3_SHA256,
            "1c0d8c206eb2070785e594784fda90f615e6ed7fd9646d67e1a9de237b8cc9f4",
        )
        self.assertIn("74ab37d5b9d200400a01639f9ffc3c3a8b716314", PNNL_IM3_ARTIFACT_URL)
        self.assertEqual(PNNL_IM3_DOI, "https://doi.org/10.57931/3017294")
        self.assertEqual(PNNL_IM3_VERSION, "2026-02-09")
        self.assertEqual(PNNL_IM3_SOURCE_FAMILY, "openstreetmap:pnnl_im3")


class GeoPackageGeometryTests(unittest.TestCase):
    def test_decodes_point_polygon_and_multipolygon_without_gis_dependency(self) -> None:
        point = parse_geopackage_geometry(
            _gpkg_geometry(_point_wkb(-77.0, 38.9))
        )
        ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
        polygon_blob = _gpkg_geometry(_polygon_wkb(ring), (0.0, 1.0, 0.0, 1.0))
        polygon = parse_geopackage_geometry(polygon_blob)
        multipolygon = parse_geopackage_geometry(
            _gpkg_geometry(
                _multipolygon_wkb([_polygon_wkb(ring)]),
                (0.0, 1.0, 0.0, 1.0),
            )
        )

        self.assertEqual(point.geometry, {"type": "Point", "coordinates": [-77.0, 38.9]})
        self.assertEqual(polygon.geometry["type"], "Polygon")
        self.assertEqual(multipolygon.geometry["type"], "MultiPolygon")
        self.assertEqual(polygon.raw_sha256, hashlib.sha256(polygon_blob).hexdigest())

    def test_rejects_truncated_out_of_bounds_and_false_envelope_geometry(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated"):
            parse_geopackage_geometry(b"GP\x00")
        with self.assertRaisesRegex(ValueError, "outside valid bounds"):
            parse_geopackage_geometry(_gpkg_geometry(_point_wkb(181.0, 0.0)))
        ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]
        with self.assertRaisesRegex(ValueError, "envelope does not match"):
            parse_geopackage_geometry(
                _gpkg_geometry(_polygon_wkb(ring), (0.0, 2.0, 0.0, 1.0))
            )


class PNNLIM3FetcherTests(unittest.TestCase):
    def test_fetch_checkpoints_raw_bytes_and_reuses_verified_bundle(self) -> None:
        raw = b"pinned raw GeoPackage test bytes"
        artifact = ArtifactSpec(
            url="https://example.invalid/pinned.gpkg",
            expected_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            filename="pinned.gpkg",
        )
        calls = []

        def opener(request, *, timeout):
            calls.append((request, timeout))
            return io.BytesIO(raw)

        with tempfile.TemporaryDirectory() as directory:
            fetcher = PNNLIM3Fetcher(artifact=artifact, opener=opener)
            first = fetcher.fetch(directory, fetched_at=RETRIEVED_AT)
            second = fetcher.fetch(directory, fetched_at="later value is not used")
            output = Path(directory)

            self.assertEqual((output / "pinned.gpkg").read_bytes(), raw)
            checkpoint = json.loads((output / "manifest.json").read_text())
            self.assertEqual(checkpoint, first)
            self.assertEqual(second, first)
            self.assertEqual(checkpoint["artifact"]["bytes"], len(raw))
            self.assertEqual(checkpoint["artifact"]["sha256"], artifact.sha256)
            self.assertEqual(checkpoint["source_family"], PNNL_IM3_SOURCE_FAMILY)
            self.assertEqual(checkpoint["upstream_source_family"], "openstreetmap")
            self.assertFalse(checkpoint["independent_corroboration"])
            self.assertEqual(len(calls), 1)
            request, timeout = calls[0]
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.full_url, artifact.url)
            self.assertIsNone(request.data)
            self.assertEqual(timeout, 120.0)

    def test_bad_download_is_not_checkpointed(self) -> None:
        raw = b"expected"
        artifact = ArtifactSpec(
            url="https://example.invalid/pinned.gpkg",
            expected_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            filename="pinned.gpkg",
        )

        with tempfile.TemporaryDirectory() as directory:
            fetcher = PNNLIM3Fetcher(
                artifact=artifact,
                opener=lambda request, timeout: io.BytesIO(b"tampered"),
            )
            with self.assertRaisesRegex(ValueError, "SHA256"):
                fetcher.fetch(directory, fetched_at=RETRIEVED_AT)
            self.assertEqual(list(Path(directory).iterdir()), [])


class PNNLIM3AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.fixture = root / "fixture.gpkg"
        _create_fixture(self.fixture)
        self.artifact = _fixture_artifact(self.fixture)
        self.connection, _ = initialize(root / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def _import(self):
        return PNNLIM3GeoPackageAdapter(artifact=self.artifact).import_file(
            self.connection,
            self.fixture,
            retrieved_at=RETRIEVED_AT,
        )

    def test_groups_county_rows_and_imports_only_conservative_candidates(self) -> None:
        result = self._import()

        self.assertEqual(result.examined_elements, 4)
        self.assertEqual(result.imported_elements, 3)
        self.assertEqual(result.skipped_elements, 1)
        self.assertEqual(result.entities_created, 4)
        self.assertEqual(result.evidence_created, 3)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("not independent corroboration", result.warnings[0])
        self.assertEqual(
            {
                row["kind"]: row["count"]
                for row in self.connection.execute(
                    "SELECT kind, COUNT(*) AS count FROM entities GROUP BY kind"
                )
            },
            {"building": 1, "campus": 1, "facility": 2},
        )
        self.assertEqual(
            [tuple(row) for row in self.connection.execute(
                "SELECT status, COUNT(*) FROM lifecycle_observations GROUP BY status"
            )],
            [("unknown", 3)],
        )
        for forbidden_table in (
            "projects",
            "capacity_estimates",
            "operating_model_observations",
            "workload_observations",
        ):
            self.assertEqual(
                self.connection.execute(f"SELECT COUNT(*) FROM {forbidden_table}").fetchone()[0],
                0,
            )
        stable_keys = [
            row[0] for row in self.connection.execute("SELECT stable_key FROM entities")
        ]
        self.assertTrue(all(key.startswith("pnnl_im3:") for key in stable_keys))
        self.assertTrue(all(not key.startswith("osm:") for key in stable_keys))
        self.assertEqual(validate_database(self.connection), [])

    def test_preserves_geometry_metadata_license_and_duplicate_counties(self) -> None:
        self._import()
        row = self.connection.execute(
            """
            SELECT e.source_url, e.source_family, e.license, e.metadata_json,
                   s.geometry_json, s.tags_json
            FROM evidence e
            JOIN entity_snapshots s ON s.evidence_id = e.id
            WHERE json_extract(e.metadata_json, '$.layer') = 'building'
              AND json_extract(s.tags_json, '$."pnnl_im3:structural_role"') IS NULL
            """
        ).fetchone()

        self.assertEqual(row["source_url"], PNNL_IM3_DOI)
        self.assertEqual(row["source_family"], PNNL_IM3_SOURCE_FAMILY)
        self.assertEqual(row["license"], "ODbL-1.0")
        metadata = json.loads(row["metadata_json"])
        self.assertEqual(metadata["artifact_sha256"], self.artifact.sha256)
        self.assertEqual(metadata["input_sha256"], self.artifact.sha256)
        self.assertEqual(metadata["provenance"]["artifact_url"], self.artifact.url)
        self.assertEqual(metadata["source_row_count"], 2)
        self.assertEqual(metadata["upstream_source_family"], "openstreetmap")
        self.assertFalse(metadata["independent_corroboration"])
        self.assertFalse(metadata["duplicate_county_rows_are_independent_evidence"])
        self.assertEqual(
            {source_row["county_id"] for source_row in metadata["source_rows"]},
            {"067", "097"},
        )
        self.assertEqual(metadata["source_rows"][0]["sqft"], 313_479.0)
        self.assertEqual(metadata["source_rows"][0]["type"], "building")
        self.assertEqual(json.loads(row["geometry_json"])["type"], "Polygon")
        tags = json.loads(row["tags_json"])
        self.assertEqual(tags["country"], "United States")
        self.assertEqual(tags["addr:country"], "US")
        self.assertEqual(tags["addr:state"], "GA")
        self.assertEqual(tags["pnnl_im3:sqft"], "313479.0")
        self.assertEqual(tags["pnnl_im3:source_type"], "building")

    def test_same_offline_import_is_idempotent(self) -> None:
        first = self._import()
        second = self._import()

        self.assertEqual(first.entities_created, 4)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
        )

    def test_verified_fetch_bundle_imports_without_network(self) -> None:
        bundle = self.fixture.with_name("bundle")
        raw = self.fixture.read_bytes()
        calls = 0

        def opener(request, *, timeout):
            nonlocal calls
            calls += 1
            return io.BytesIO(raw)

        PNNLIM3Fetcher(artifact=self.artifact, opener=opener).fetch(
            bundle,
            fetched_at=RETRIEVED_AT,
        )
        result = PNNLIM3GeoPackageAdapter(artifact=self.artifact).import_file(
            self.connection,
            bundle,
            retrieved_at=RETRIEVED_AT,
        )

        self.assertEqual(calls, 1)
        self.assertEqual(result.imported_elements, 3)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
        )

    def test_retrieval_timestamp_must_include_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            PNNLIM3GeoPackageAdapter(artifact=self.artifact).import_file(
                self.connection,
                self.fixture,
                retrieved_at="2026-07-17T19:00:00",
            )

    def test_checksum_mismatch_is_rejected_before_sqlite_import(self) -> None:
        tampered = self.fixture.with_name("tampered.gpkg")
        raw = bytearray(self.fixture.read_bytes())
        raw[-1] ^= 1
        tampered.write_bytes(raw)

        with self.assertRaisesRegex(ValueError, "SHA256"):
            PNNLIM3GeoPackageAdapter(artifact=self.artifact).import_file(
                self.connection,
                tampered,
                retrieved_at=RETRIEVED_AT,
            )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0
        )

    def test_duplicate_county_rows_may_not_disagree_on_feature_metadata(self) -> None:
        source = sqlite3.connect(self.fixture)
        source.execute("UPDATE building SET operator = 'Different' WHERE fid = 3")
        source.commit()
        source.close()
        changed_artifact = _fixture_artifact(self.fixture)

        with self.assertRaisesRegex(ValueError, "duplicate county rows disagree"):
            PNNLIM3GeoPackageAdapter(artifact=changed_artifact).import_file(
                self.connection,
                self.fixture,
                retrieved_at=RETRIEVED_AT,
            )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0
        )

if __name__ == "__main__":
    unittest.main()
