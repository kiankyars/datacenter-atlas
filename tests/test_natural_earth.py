from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.models import Evidence, EvidenceKind, Facility
from datacenter_atlas.natural_earth import (
    NATURAL_EARTH_COMMIT,
    NATURAL_EARTH_EXPECTED_BYTES,
    NATURAL_EARTH_FEATURE_COUNT,
    NATURAL_EARTH_LICENSE,
    NATURAL_EARTH_SHA256,
    NATURAL_EARTH_VERSION,
    NaturalEarthArtifact,
    NaturalEarthError,
    NaturalEarthFetcher,
    assign_country,
    canonicalize_source_country,
    enrich_administrative_assignments,
    load_natural_earth_dataset,
    validate_natural_earth_bundle,
)
from datacenter_atlas.release import build_release_documents
from datacenter_atlas.repository import add_evidence, add_facility, add_snapshot
from datacenter_atlas.service import export_geojson, summarize, validate_database


FIXTURE = Path(__file__).parent / "fixtures" / "natural_earth_minimal.geojson"
LIVE_BUNDLE = (
    Path(__file__).parents[1]
    / "source_cache"
    / "natural-earth-5.1.1-ca96624"
)
FETCHED_AT = "2026-07-18T18:07:00Z"
RECORDED_AT = "2026-07-18T19:00:00Z"


def _fixture_artifact() -> NaturalEarthArtifact:
    raw = FIXTURE.read_bytes()
    return NaturalEarthArtifact(
        url="https://example.invalid/natural-earth-fixture.geojson",
        version="fixture-1",
        commit="fixture-commit",
        filename=FIXTURE.name,
        expected_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        feature_count=4,
    )


def _fixture_bundle(root: Path) -> tuple[Path, NaturalEarthArtifact]:
    artifact = _fixture_artifact()
    bundle = root / "boundary-bundle"
    bundle.mkdir()
    shutil.copyfile(FIXTURE, bundle / artifact.filename)
    NaturalEarthFetcher(artifact=artifact).fetch(bundle, fetched_at=FETCHED_AT)
    return bundle, artifact


class NaturalEarthLivePinTests(unittest.TestCase):
    def test_source_country_aliases_normalize_to_the_iso_canonical_name(self) -> None:
        ivory_coast = canonicalize_source_country("Ivory Coast")
        self.assertIsNotNone(ivory_coast)
        self.assertEqual(
            (ivory_coast.name, ivory_coast.iso_a2, ivory_coast.iso_a3),
            ("Côte d'Ivoire", "CI", "CIV"),
        )

    def test_live_artifact_is_exact_and_all_features_validate(self) -> None:
        source, manifest, verification = validate_natural_earth_bundle(LIVE_BUNDLE)
        self.assertEqual(source.stat().st_size, NATURAL_EARTH_EXPECTED_BYTES)
        self.assertEqual(verification.sha256, NATURAL_EARTH_SHA256)
        self.assertEqual(manifest["theme_version"], NATURAL_EARTH_VERSION)
        self.assertEqual(manifest["git_commit"], NATURAL_EARTH_COMMIT)
        self.assertEqual(manifest["license"], NATURAL_EARTH_LICENSE)
        self.assertTrue(manifest["public_domain"])

        dataset = load_natural_earth_dataset(LIVE_BUNDLE)
        self.assertEqual(len(dataset.features), NATURAL_EARTH_FEATURE_COUNT)
        self.assertEqual(
            dataset.canonicalization_counts,
            {
                "iso_standard": 235,
                "iso_eh_fallback": 8,
                "natural_earth_non_iso_label": 15,
            },
        )
        france = next(feature for feature in dataset.features if feature.admin == "France")
        self.assertEqual(
            (
                france.canonical_country.name,
                france.canonical_country.iso_a2,
                france.canonical_country.iso_a3,
                france.canonical_country.method,
            ),
            ("France", "FR", "FRA", "iso_eh_fallback"),
        )
        kosovo = next(feature for feature in dataset.features if feature.admin == "Kosovo")
        self.assertEqual(kosovo.canonical_country.name, "Kosovo")
        self.assertIsNone(kosovo.canonical_country.iso_a2)
        self.assertEqual(kosovo.canonical_country.method, "natural_earth_non_iso_label")

    def test_checkpoint_reuses_verified_existing_bytes(self) -> None:
        raw = FIXTURE.read_bytes()
        artifact = _fixture_artifact()
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / artifact.filename).write_bytes(raw)
            fetcher = NaturalEarthFetcher(
                artifact=artifact,
                opener=lambda *_args, **_kwargs: calls.append(True),
            )
            first = fetcher.fetch(output, fetched_at=FETCHED_AT)
            second = fetcher.fetch(output, fetched_at="2026-07-18T20:00:00Z")
            self.assertEqual(first, second)
            self.assertEqual(calls, [])
            self.assertEqual(first["artifact"]["sha256"], artifact.sha256)

    def test_download_checkpoints_exact_raw_bytes_with_a_bodyless_get(self) -> None:
        raw = FIXTURE.read_bytes()
        artifact = _fixture_artifact()
        calls = []

        def opener(request, *, timeout):
            calls.append((request, timeout))
            return io.BytesIO(raw)

        with tempfile.TemporaryDirectory() as directory:
            manifest = NaturalEarthFetcher(
                artifact=artifact, opener=opener
            ).fetch(directory, fetched_at=FETCHED_AT)
            output = Path(directory)
            self.assertEqual((output / artifact.filename).read_bytes(), raw)
            self.assertEqual(manifest["artifact"]["sha256"], artifact.sha256)
            self.assertEqual(len(calls), 1)
            request, timeout = calls[0]
            self.assertEqual(request.method, "GET")
            self.assertIsNone(request.data)
            self.assertTrue(request.headers["User-agent"])
            self.assertEqual(timeout, 120.0)

    def test_tampered_artifact_is_rejected(self) -> None:
        artifact = _fixture_artifact()
        with tempfile.TemporaryDirectory() as directory:
            bundle, _ = _fixture_bundle(Path(directory))
            source = bundle / artifact.filename
            source.write_bytes(source.read_bytes() + b" ")
            with self.assertRaisesRegex(NaturalEarthError, "byte count"):
                validate_natural_earth_bundle(bundle, artifact=artifact)


class PointInPolygonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.bundle, self.artifact = _fixture_bundle(
            Path(self.temporary_directory.name)
        )
        self.dataset = load_natural_earth_dataset(
            self.bundle, artifact=self.artifact
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_polygon_holes_multipolygon_and_overlap_policy(self) -> None:
        assigned = assign_country(self.dataset, 2.0, 2.0)
        hole = assign_country(self.dataset, 5.0, 5.0)
        hole_edge = assign_country(self.dataset, 4.0, 5.0)
        overlap = assign_country(self.dataset, 9.0, 9.0)
        multipolygon_first = assign_country(self.dataset, 21.0, 21.0)
        multipolygon_second = assign_country(self.dataset, 31.0, 31.0)

        self.assertEqual(assigned.status.value, "assigned")
        self.assertEqual(assigned.feature.canonical_country.iso_a3, "USA")
        self.assertEqual(hole.status.value, "unmatched")
        self.assertEqual(hole_edge.status.value, "boundary")
        self.assertEqual(overlap.status.value, "ambiguous")
        self.assertEqual(overlap.match_feature_ids, ("1", "4"))
        self.assertEqual(multipolygon_first.feature.canonical_country.iso_a3, "CAN")
        self.assertEqual(multipolygon_second.feature.canonical_country.iso_a3, "CAN")

    def test_antimeridian_is_unwrapped_relative_to_the_query_point(self) -> None:
        east = assign_country(self.dataset, 179.0, 0.0)
        west = assign_country(self.dataset, -179.0, 0.0)
        prime_meridian = assign_country(self.dataset, 0.0, -5.0)

        self.assertEqual(east.feature.canonical_country.iso_a3, "JPN")
        self.assertEqual(west.feature.canonical_country.iso_a3, "JPN")
        self.assertEqual(prime_meridian.status.value, "unmatched")


class NaturalEarthEnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.bundle, self.artifact = _fixture_bundle(root)
        self.connection, _ = initialize(root / "atlas.sqlite")
        evidence = Evidence(
            id="source-evidence",
            kind=EvidenceKind.GOVERNMENT_RECORD,
            title="Coordinate source",
            source_url="https://example.test/coordinates",
            retrieved_at="2026-07-17T12:00:00Z",
        )
        add_evidence(self.connection, evidence)
        points = (
            ("assigned-conflict", 2.0, 2.0, {"country": "Canada"}),
            ("hole-unmatched", 5.0, 5.0, {"addr:country": "FI"}),
            ("overlap-ambiguous", 9.0, 9.0, {}),
            ("hole-boundary", 4.0, 5.0, {}),
            ("dateline-japan", 179.0, 0.0, {"addr:country": "JP"}),
            ("multipolygon-canada", 21.0, 21.0, {"country": "CA"}),
        )
        for key, longitude, latitude, tags in points:
            entity_id = f"facility-{key}"
            add_facility(
                self.connection,
                Facility(entity_id, f"fixture:{key}", evidence.id),
                created_at=evidence.retrieved_at,
            )
            add_snapshot(
                self.connection,
                snapshot_id=f"snapshot-{key}",
                entity_id=entity_id,
                name=key,
                latitude=latitude,
                longitude=longitude,
                geometry={"type": "Point", "coordinates": [longitude, latitude]},
                tags=tags,
                evidence_id=evidence.id,
                as_of_date="2026-07-17",
                recorded_at=evidence.retrieved_at,
                method="fixture",
                confidence=1.0,
            )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def _enrich(self):
        return enrich_administrative_assignments(
            self.connection,
            self.bundle,
            as_of="2026-07-18",
            recorded_at=RECORDED_AT,
            artifact=self.artifact,
        )

    def test_enrichment_cutoff_normalizes_whole_second_offsets(self) -> None:
        result = enrich_administrative_assignments(
            self.connection,
            self.bundle,
            as_of="2026-07-18",
            recorded_at="2026-07-18T20:00:00.000+01:00",
            artifact=self.artifact,
        )
        self.assertEqual(result.examined_snapshots, 6)
        self.assertEqual(
            {
                row[0]
                for row in self.connection.execute(
                    "SELECT DISTINCT recorded_at FROM administrative_assignments"
                )
            },
            {RECORDED_AT},
        )

    def test_enrichment_cutoff_is_instant_aware_and_rejects_fractions(self) -> None:
        before_snapshots = enrich_administrative_assignments(
            self.connection,
            self.bundle,
            as_of="2026-07-18",
            recorded_at="2026-07-17T13:00:00+02:00",
            artifact=self.artifact,
        )
        self.assertEqual(before_snapshots.examined_snapshots, 0)
        self.assertEqual(before_snapshots.assignments_created, 0)

        for label, cutoff in (
            ("fraction", "2026-07-18T19:00:00.500000Z"),
            ("submicrosecond", "2026-07-18T19:00:00.0000001Z"),
            ("naive", "2026-07-18T19:00:00"),
            ("invalid", "not-a-timestamp"),
        ):
            with self.subTest(rejected_cutoff=label):
                changes_before = self.connection.total_changes
                with self.assertRaises(NaturalEarthError):
                    enrich_administrative_assignments(
                        self.connection,
                        self.bundle,
                        as_of="2026-07-18",
                        recorded_at=cutoff,
                        artifact=self.artifact,
                    )
                self.assertEqual(self.connection.total_changes, changes_before)

    def test_enrichment_is_separate_provenanced_conservative_and_idempotent(self) -> None:
        tags_before = {
            row["id"]: row["tags_json"]
            for row in self.connection.execute("SELECT id, tags_json FROM entity_snapshots")
        }
        first = self._enrich()
        self.assertEqual(first.examined_snapshots, 6)
        self.assertEqual(first.assignments_created, 6)
        self.assertEqual(first.evidence_created, 1)
        self.assertEqual(
            (first.assigned, first.unmatched, first.ambiguous, first.boundary),
            (3, 1, 1, 1),
        )
        self.assertEqual(first.source_conflicts, 1)
        self.assertEqual(validate_database(self.connection), [])
        tags_after = {
            row["id"]: row["tags_json"]
            for row in self.connection.execute("SELECT id, tags_json FROM entity_snapshots")
        }
        self.assertEqual(tags_after, tags_before)

        evidence = self.connection.execute(
            "SELECT * FROM evidence WHERE source_family = 'natural_earth'"
        ).fetchone()
        self.assertEqual(evidence["license"], "Public Domain")
        self.assertEqual(evidence["content_hash"], self.artifact.sha256)
        metadata = json.loads(evidence["metadata_json"])
        self.assertEqual(metadata["git_commit"], self.artifact.commit)
        self.assertEqual(metadata["feature_count"], 4)
        self.assertEqual(
            metadata["point_in_polygon_policy"]["multiple_feature_matches"],
            "unresolved as ambiguous",
        )

        unresolved = {
            row["entity_id"]: row
            for row in self.connection.execute(
                "SELECT * FROM administrative_assignments WHERE resolution_status != 'assigned'"
            )
        }
        self.assertIsNone(unresolved["facility-overlap-ambiguous"]["country_name"])
        self.assertEqual(
            json.loads(
                unresolved["facility-overlap-ambiguous"]["match_feature_ids_json"]
            ),
            ["1", "4"],
        )
        self.assertIn(
            "unresolved", unresolved["facility-hole-boundary"]["method"]
        )

        second = self._enrich()
        self.assertEqual(second.assignments_created, 0)
        self.assertEqual(second.evidence_created, 0)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM administrative_assignments"
            ).fetchone()[0],
            6,
        )

    def test_export_release_and_summary_prefer_assignment_but_keep_source_tag(self) -> None:
        self._enrich()
        geojson = export_geojson(
            self.connection,
            as_of="2026-07-18",
            recorded_at=RECORDED_AT,
        )
        by_name = {
            feature["properties"]["name"]: feature["properties"]
            for feature in geojson["features"]
        }
        assigned = by_name["assigned-conflict"]
        self.assertEqual(assigned["country"], "United States")
        self.assertEqual(assigned["country_iso_a3"], "USA")
        self.assertEqual(assigned["administrative_country_name"], "United States")
        self.assertEqual(assigned["administrative_country_iso_a3"], "USA")
        self.assertEqual(assigned["source_country_tag"], "Canada")
        self.assertTrue(assigned["administrative_assignment_evidence_id"])
        self.assertIn("Natural Earth", geojson["attribution"])
        unmatched = by_name["hole-unmatched"]
        self.assertEqual(unmatched["country"], "Finland")
        self.assertEqual(unmatched["country_iso_a2"], "FI")
        self.assertEqual(unmatched["country_iso_a3"], "FIN")
        self.assertEqual(unmatched["source_country_tag"], "FI")
        self.assertEqual(unmatched["administrative_assignment_status"], "unmatched")

        summary = summarize(
            self.connection,
            as_of="2026-07-18",
            recorded_at=RECORDED_AT,
        )
        self.assertEqual(
            summary["country_assignment_counts"],
            {
                "assigned": 3,
                "unmatched": 1,
                "conflict": 2,
                "ambiguous": 1,
                "boundary": 1,
                "not_evaluated": 0,
            },
        )
        self.assertEqual(summary["country_source_tag_conflicts"], 1)
        self.assertEqual(summary["country_source_tag_fallbacks"], 1)
        self.assertEqual(
            summary["entities_by_country"],
            {"Canada": 1, "Finland": 1, "Japan": 1, "United States": 1},
        )

        documents = build_release_documents(
            self.connection,
            as_of="2026-07-18",
            recorded_at=RECORDED_AT,
        )
        rows = list(csv.DictReader(io.StringIO(documents["entities.csv"])))
        release_assigned = next(row for row in rows if row["name"] == "assigned-conflict")
        self.assertEqual(release_assigned["country"], "United States")
        self.assertEqual(release_assigned["country_iso_a3"], "USA")
        self.assertEqual(release_assigned["source_country_tag"], "Canada")
        self.assertTrue(release_assigned["country_assignment_evidence_id"])
        release_unmatched = next(row for row in rows if row["name"] == "hole-unmatched")
        self.assertEqual(release_unmatched["country"], "Finland")
        self.assertEqual(release_unmatched["country_iso_a2"], "FI")
        self.assertEqual(release_unmatched["country_iso_a3"], "FIN")
        self.assertEqual(release_unmatched["source_country_tag"], "FI")
        self.assertIn("Natural Earth", documents["ATTRIBUTION.txt"])
        self.assertIn("natural_earth", documents["evidence.csv"])


if __name__ == "__main__":
    unittest.main()
