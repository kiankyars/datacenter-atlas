from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database
from datacenter_atlas.uva import (
    EXPECTED_COLUMNS,
    UVA_ARTIFACT,
    UVA_DATAFILE_ID,
    UVA_DATA_URL,
    UVA_DOI,
    UVA_EXPECTED_BYTES,
    UVA_EXPECTED_COLUMNS,
    UVA_EXPECTED_ROWS,
    UVA_LICENSE,
    UVA_MD5,
    UVA_METADATA_URL,
    UVA_RELEASE_DATE,
    UVA_SHA256,
    UVA_SOURCE_FAMILY,
    UVA_VERSION,
    UVAArtifactSpec,
    UVADataFetcher,
    UVADataverseAdapter,
    read_uva_facilities,
    validate_metadata_document,
    verify_artifact,
    verify_metadata,
)


RETRIEVED_AT = "2026-07-18T18:00:00Z"
LIVE_BUNDLE = (
    Path(__file__).parents[1]
    / "source_cache"
    / "uva-dc-v2.0-2026-05-18"
)


def _row(
    latitude: float,
    longitude: float,
    facility_type: str,
    *,
    critical_it_mean: float = 10.0,
    critical_it_std: float = 2.0,
    typical_mean: float = 2.0,
    typical_std: float = 0.5,
) -> dict[str, str]:
    row = {field: "1" for field in EXPECTED_COLUMNS}
    row.update(
        {
            "lat": str(latitude),
            "lon": str(longitude),
            "building_footprint_polygon": json.dumps(
                [
                    [latitude - 0.001, longitude - 0.001],
                    [latitude - 0.001, longitude + 0.001],
                    [latitude + 0.001, longitude + 0.001],
                    [latitude + 0.001, longitude - 0.001],
                ]
            ),
            "building_footprint_area": "1000.0",
            "number_of_floors": "2",
            "total_building_area": "2000.0",
            "construction_year": "2020",
            "Predicted_IT_Whitespace_Area_mean": "500.0",
            "Predicted_IT_Whitespace_Area_std": "50.0",
            "Predicted_Built-out_Power_mean": str(critical_it_mean),
            "Predicted_Built-out_Power_std": str(critical_it_std),
            "Predicted_Facility_Type": facility_type,
        }
    )
    for hour in range(24):
        row[f"IT_power_mean_AtHour_{hour:02d}"] = "1.5"
        row[f"IT_power_std_AtHour_{hour:02d}"] = "0.25"
        row[f"Typical_Day_Facility_Power_mean_AtHour_{hour:02d}"] = str(
            typical_mean
        )
        row[f"Typical_Day_Facility_Power_std_AtHour_{hour:02d}"] = str(
            typical_std
        )
        row[f"Peak_Temperature_Day_Facility_Power_mean_AtHour_{hour:02d}"] = "3.0"
        row[f"Peak_Temperature_Day_Facility_Power_std_AtHour_{hour:02d}"] = "0.75"
    for index, field in enumerate(
        (
            "distance_to_substation",
            "distance_to_highway",
            "distance_to_residential",
            "distance_to_water",
            "distance_to_transmission",
        ),
        start=1,
    ):
        row[field] = str(index * 100.0)
    return row


def _csv_bytes(rows: list[dict[str, str]], columns: tuple[str, ...] = EXPECTED_COLUMNS) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in columns})
    return output.getvalue().encode("utf-8")


def _artifact(path: Path, payload: bytes, rows: int) -> UVAArtifactSpec:
    return replace(
        UVA_ARTIFACT,
        metadata_url="https://example.invalid/versions/2.0",
        data_url="https://example.invalid/datafile/120633?format=original",
        local_filename=path.name,
        expected_bytes=len(payload),
        md5=hashlib.md5(payload).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        expected_rows=rows,
    )


def _metadata_document(artifact: UVAArtifactSpec) -> dict[str, object]:
    return {
        "status": "OK",
        "data": {
            "id": artifact.dataset_version_id,
            "datasetId": artifact.dataset_id,
            "datasetPersistentId": artifact.persistent_id,
            "versionNumber": 2,
            "versionMinorNumber": 0,
            "versionState": "RELEASED",
            "releaseTime": artifact.release_time,
            "license": {"rightsIdentifier": "CC0-1.0"},
            "metadataBlocks": {
                "citation": {
                    "fields": [
                        {
                            "typeName": "title",
                            "value": (
                                "AI-Enabled Synthesis of Open Source Multi-Attribute, "
                                "Temporal Dataset Related to Data Centers in Virginia"
                            ),
                        }
                    ]
                }
            },
            "files": [
                {
                    "label": artifact.local_filename,
                    "datasetVersionId": artifact.dataset_version_id,
                    "dataFile": {
                        "id": artifact.datafile_id,
                        "originalFileName": artifact.original_filename,
                        "originalFileSize": artifact.expected_bytes,
                        "md5": artifact.md5,
                        "checksum": {"type": "MD5", "value": artifact.md5},
                        "tabularData": True,
                    },
                }
            ],
        },
    }


class UVAConstantsTests(unittest.TestCase):
    def test_official_v2_pin_is_exact(self) -> None:
        self.assertEqual(UVA_DOI, "https://doi.org/10.18130/V3/AYLB4S")
        self.assertEqual(UVA_VERSION, "2.0")
        self.assertEqual(UVA_RELEASE_DATE, "2026-05-18")
        self.assertEqual(UVA_DATAFILE_ID, 120633)
        self.assertEqual(UVA_EXPECTED_BYTES, 1_273_747)
        self.assertEqual(UVA_MD5, "947213715a464b3ee9538af4da70cc2e")
        self.assertEqual(
            UVA_SHA256,
            "e5caed9572af6dec15dd525de105301baae2c1fbbca31c552b2a33c28befd69c",
        )
        self.assertEqual(UVA_EXPECTED_ROWS, 382)
        self.assertEqual(UVA_EXPECTED_COLUMNS, 161)
        self.assertEqual(len(EXPECTED_COLUMNS), 161)
        self.assertIn("versions/2.0", UVA_METADATA_URL)
        self.assertEqual(UVA_DATA_URL.split("?")[0].rsplit("/", 1)[-1], "120633")
        self.assertEqual(UVA_LICENSE, "CC0-1.0")
        self.assertEqual(UVA_SOURCE_FAMILY, "uva_dataverse_dc_sense")


class UVAFetcherTests(unittest.TestCase):
    def test_dataset_level_metadata_is_rejected_in_favor_of_exact_version(self) -> None:
        payload = _csv_bytes([_row(38.9, -77.4, "Hyperscale")])
        artifact = _artifact(Path("fixture.csv"), payload, 1)
        version = _metadata_document(artifact)["data"]
        moving_document = {"status": "OK", "data": {"latestVersion": version}}
        with self.assertRaisesRegex(ValueError, "moving dataset-level response"):
            validate_metadata_document(moving_document, artifact=artifact)

    def test_fetches_exact_metadata_and_original_bytes_then_reuses_bundle(self) -> None:
        rows = [_row(38.9, -77.4, "Hyperscale")]
        payload = _csv_bytes(rows)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            artifact = _artifact(output / "fixture.csv", payload, len(rows))
            metadata_raw = json.dumps(_metadata_document(artifact)).encode("utf-8")
            calls: list[object] = []

            def opener(request, *, timeout):
                calls.append((request, timeout))
                if request.full_url == artifact.metadata_url:
                    return io.BytesIO(metadata_raw)
                if request.full_url == artifact.data_url:
                    return io.BytesIO(payload)
                raise AssertionError(request.full_url)

            fetcher = UVADataFetcher(artifact=artifact, opener=opener)
            first = fetcher.fetch(output, fetched_at=RETRIEVED_AT)
            second = fetcher.fetch(output, fetched_at="unused invalid timestamp")

            self.assertEqual(first, second)
            self.assertEqual((output / artifact.local_filename).read_bytes(), payload)
            self.assertEqual(
                (output / artifact.metadata_filename).read_bytes(), metadata_raw
            )
            self.assertEqual(first["artifact"]["md5"], artifact.md5)
            self.assertEqual(first["artifact"]["sha256"], artifact.sha256)
            self.assertEqual(first["version_metadata"]["url"], artifact.metadata_url)
            self.assertTrue(first["independent_corroboration"])
            self.assertEqual(len(calls), 2)
            for request, timeout in calls:
                self.assertEqual(request.method, "GET")
                self.assertIsNone(request.data)
                self.assertEqual(timeout, 120.0)

    def test_bad_download_is_not_published(self) -> None:
        payload = _csv_bytes([_row(38.9, -77.4, "Hyperscale")])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            artifact = _artifact(output / "fixture.csv", payload, 1)
            metadata = json.dumps(_metadata_document(artifact)).encode()

            def opener(request, *, timeout):
                if request.full_url == artifact.metadata_url:
                    return io.BytesIO(metadata)
                return io.BytesIO(b"x" * len(payload))

            with self.assertRaisesRegex(ValueError, "MD5|SHA256"):
                UVADataFetcher(artifact=artifact, opener=opener).fetch(
                    output, fetched_at=RETRIEVED_AT
                )
            self.assertEqual(list(output.iterdir()), [])


class UVAAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.rows = [
            _row(38.90, -77.40, "Hyperscale"),
            _row(38.91, -77.41, "Colocation"),
            _row(38.92, -77.42, "Enterprise"),
            _row(38.93, -77.43, "Large Campus"),
        ]
        self.payload = _csv_bytes(self.rows)
        self.source = self.root / "fixture.csv"
        self.source.write_bytes(self.payload)
        self.artifact = _artifact(self.source, self.payload, len(self.rows))
        self.connection, _ = initialize(self.root / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def _import(self):
        return UVADataverseAdapter(artifact=self.artifact).import_file(
            self.connection, self.source, retrieved_at=RETRIEVED_AT
        )

    def test_imports_source_scoped_facilities_without_lifecycle_or_project_misclaim(self) -> None:
        result = self._import()
        self.assertEqual(result.examined_elements, 4)
        self.assertEqual(result.imported_elements, 4)
        self.assertEqual(result.entities_created, 4)
        self.assertEqual(result.evidence_created, 4)
        self.assertEqual(
            [tuple(row) for row in self.connection.execute(
                "SELECT kind, COUNT(*) FROM entities GROUP BY kind"
            )],
            [("facility", 4)],
        )
        self.assertEqual(
            [tuple(row) for row in self.connection.execute(
                "SELECT status, COUNT(*) FROM lifecycle_observations GROUP BY status"
            )],
            [("unknown", 4)],
        )
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            8,
        )
        operating_models = [
            tuple(row)
            for row in self.connection.execute(
                "SELECT operating_model, confidence FROM operating_model_observations "
                "ORDER BY operating_model"
            )
        ]
        self.assertEqual(
            operating_models,
            [("colocation", 0.6), ("enterprise_private", 0.5), ("hyperscaler", 0.55)],
        )
        stable_keys = [
            row[0] for row in self.connection.execute("SELECT stable_key FROM entities")
        ]
        self.assertTrue(all(key.startswith("uva_dc_sense:2.0:") for key in stable_keys))
        self.assertTrue(all(len(key.rsplit(":", 1)[-1]) == 64 for key in stable_keys))
        tags = [
            json.loads(row[0])
            for row in self.connection.execute("SELECT tags_json FROM entity_snapshots")
        ]
        self.assertTrue(all(tag["addr:state"] == "VA" for tag in tags))
        self.assertTrue(
            all("uva_dc_sense:construction_year_model_output" in tag for tag in tags)
        )
        self.assertTrue(all("construction" not in tag for tag in tags))
        self.assertEqual(validate_database(self.connection), [])

    def test_capacity_geometry_profiles_and_distance_metadata_are_exact(self) -> None:
        self._import()
        capacities = {
            row["metric"]: row
            for row in self.connection.execute(
                "SELECT * FROM capacity_estimates WHERE entity_id = "
                "(SELECT entity_id FROM entity_snapshots ORDER BY latitude LIMIT 1)"
            )
        }
        critical = capacities["critical_it_mw"]
        self.assertEqual((critical["low"], critical["base"], critical["high"]), (8.0, 10.0, 12.0))
        self.assertEqual(critical["stage"], "unknown")
        self.assertEqual(critical["method"], "modeled")
        self.assertIn("not a calibrated confidence interval", critical["notes"])
        energy = capacities["annual_energy_mwh"]
        self.assertEqual(
            (energy["low"], energy["base"], energy["high"]),
            (1.5 * 24 * 365, 2.0 * 24 * 365, 2.5 * 24 * 365),
        )
        self.assertIn("not metered energy", energy["notes"])

        row = self.connection.execute(
            "SELECT e.kind, e.source_family, e.license, e.metadata_json, s.geometry_json "
            "FROM evidence e JOIN entity_snapshots s ON s.evidence_id=e.id "
            "ORDER BY s.latitude LIMIT 1"
        ).fetchone()
        self.assertEqual(row["kind"], "third_party_dataset")
        self.assertEqual(row["source_family"], UVA_SOURCE_FAMILY)
        self.assertEqual(row["license"], "CC0-1.0")
        metadata = json.loads(row["metadata_json"])
        self.assertTrue(metadata["independent_corroboration"])
        self.assertEqual(metadata["input_sha256"], self.artifact.sha256)
        self.assertEqual(metadata["provenance"]["artifact_url"], self.artifact.data_url)
        self.assertEqual(metadata["provenance"]["artifact_bytes"], len(self.payload))
        self.assertEqual(metadata["provenance"]["artifact_md5"], self.artifact.md5)
        self.assertEqual(
            metadata["provenance"]["artifact_sha256"], self.artifact.sha256
        )
        self.assertIsNone(metadata["provenance"]["version_metadata"])
        self.assertEqual(len(metadata["profiles"]["it_power"]["mean_mw"]), 24)
        self.assertEqual(
            len(metadata["profiles"]["typical_day_facility_power"]["reported_std_mw"]),
            24,
        )
        self.assertEqual(
            len(metadata["profiles"]["peak_temperature_day_facility_power"]["mean_mw"]),
            24,
        )
        self.assertEqual(metadata["distance_fields"]["values"]["distance_to_water"], 400.0)
        self.assertIsNone(metadata["distance_fields"]["unit"])
        self.assertIn(
            "not evidence of current construction",
            metadata["modeled_attributes"]["construction_year"]["interpretation"],
        )
        geometry = json.loads(row["geometry_json"])
        ring = geometry["coordinates"][0]
        self.assertEqual(ring[0], [-77.40100000000001, 38.899])
        self.assertEqual(ring[0], ring[-1])

    def test_import_is_idempotent(self) -> None:
        first = self._import()
        second = self._import()
        self.assertEqual(first.entities_created, 4)
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 4
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            8,
        )

    def test_verified_bundle_exposes_artifact_and_version_metadata_provenance(self) -> None:
        bundle = self.root / "bundle"
        metadata_raw = json.dumps(_metadata_document(self.artifact)).encode("utf-8")

        def opener(request, *, timeout):
            if request.full_url == self.artifact.metadata_url:
                return io.BytesIO(metadata_raw)
            if request.full_url == self.artifact.data_url:
                return io.BytesIO(self.payload)
            raise AssertionError(request.full_url)

        UVADataFetcher(artifact=self.artifact, opener=opener).fetch(
            bundle, fetched_at=RETRIEVED_AT
        )
        UVADataverseAdapter(artifact=self.artifact).import_file(
            self.connection, bundle, retrieved_at=RETRIEVED_AT
        )
        metadata = json.loads(
            self.connection.execute("SELECT metadata_json FROM evidence LIMIT 1").fetchone()[0]
        )
        provenance = metadata["provenance"]
        self.assertEqual(provenance["artifact_url"], self.artifact.data_url)
        self.assertEqual(provenance["artifact_bytes"], len(self.payload))
        self.assertEqual(provenance["artifact_md5"], self.artifact.md5)
        self.assertEqual(provenance["artifact_sha256"], self.artifact.sha256)
        self.assertEqual(
            provenance["version_metadata"]["sha256"],
            hashlib.sha256(metadata_raw).hexdigest(),
        )

    def test_strict_schema_numeric_coordinate_and_polygon_validation(self) -> None:
        cases: list[tuple[str, list[dict[str, str]], tuple[str, ...], str]] = []
        duplicate = [self.rows[0].copy(), self.rows[0].copy()]
        cases.append(
            ("duplicate", duplicate, EXPECTED_COLUMNS, "duplicates facility coordinates")
        )
        negative = [self.rows[0].copy()]
        negative[0]["distance_to_water"] = "-1"
        cases.append(("negative", negative, EXPECTED_COLUMNS, "non-negative"))
        nonfinite = [self.rows[0].copy()]
        nonfinite[0]["Predicted_Built-out_Power_mean"] = "nan"
        cases.append(("nonfinite", nonfinite, EXPECTED_COLUMNS, "finite"))
        outside = [self.rows[0].copy()]
        outside[0]["lat"] = "40.0"
        cases.append(("outside", outside, EXPECTED_COLUMNS, "Virginia envelope"))
        polygon = [self.rows[0].copy()]
        polygon[0]["building_footprint_polygon"] = "[[38.9,-77.4],[38.9,-77.4]]"
        cases.append(("polygon", polygon, EXPECTED_COLUMNS, "at least three"))
        columns = EXPECTED_COLUMNS[:-1]
        cases.append(("schema", [self.rows[0].copy()], columns, "columns or column order"))

        for name, rows, fields, message in cases:
            with self.subTest(name=name):
                path = self.root / f"{name}.csv"
                payload = _csv_bytes(rows, fields)
                path.write_bytes(payload)
                artifact = _artifact(path, payload, len(rows))
                with self.assertRaisesRegex(ValueError, message):
                    read_uva_facilities(path, artifact=artifact)


@unittest.skipUnless(
    (LIVE_BUNDLE / "ModelOutput.tab").is_file(),
    "pinned UVA live artifact is not cached",
)
class UVALiveArtifactTests(unittest.TestCase):
    def test_live_artifact_exact_aggregates_and_import_claims(self) -> None:
        source = LIVE_BUNDLE / "ModelOutput.tab"
        metadata = LIVE_BUNDLE / "dataverse-dataset-metadata.json"
        verification = verify_artifact(source)
        metadata_verification = verify_metadata(metadata)
        records = read_uva_facilities(source)
        self.assertEqual(verification.byte_count, 1_273_747)
        self.assertGreater(metadata_verification.byte_count, 10_000)
        self.assertEqual(len(records), 382)
        counts: dict[str, int] = {}
        for record in records:
            counts[record.facility_type] = counts.get(record.facility_type, 0) + 1
        self.assertEqual(
            counts,
            {
                "Hyperscale": 221,
                "Large Campus": 129,
                "Colocation": 21,
                "Enterprise": 11,
            },
        )
        self.assertEqual(len({(r.latitude, r.longitude) for r in records}), 382)
        self.assertAlmostEqual(
            sum(r.critical_it_interval[0] for r in records), 10_566.19069679797
        )
        self.assertAlmostEqual(
            sum(r.critical_it_interval[1] for r in records), 15_271.526189651886
        )
        self.assertAlmostEqual(
            sum(r.critical_it_interval[2] for r in records), 19_976.8616825058
        )
        self.assertAlmostEqual(
            sum(r.annual_energy_interval[0] for r in records), 70_009_685.48339377
        )
        self.assertAlmostEqual(
            sum(r.annual_energy_interval[1] for r in records), 108_849_924.4515579
        )
        self.assertAlmostEqual(
            sum(r.annual_energy_interval[2] for r in records), 147_690_163.41972202
        )

        with tempfile.TemporaryDirectory() as directory:
            connection, _ = initialize(Path(directory) / "atlas.sqlite")
            try:
                result = UVADataverseAdapter().import_file(
                    connection, source, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual(result.imported_elements, 382)
                self.assertEqual(result.entities_created, 382)
                self.assertEqual(result.evidence_created, 382)
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations WHERE status='unknown'"
                    ).fetchone()[0],
                    382,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates"
                    ).fetchone()[0],
                    764,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    253,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
