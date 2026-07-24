from __future__ import annotations

import csv
import io
import json
import random
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.models import Campus, Evidence, EvidenceKind, Facility
from datacenter_atlas.repository import add_campus, add_evidence, add_facility, add_snapshot
from datacenter_atlas.resolution import (
    _Record,
    _country,
    _current_records,
    _source_root,
    _spatial_candidate_pairs,
    _spatial_candidate_pairs_between,
    ISO_3166_1,
    ResolutionThresholds,
    candidate_links_to_csv,
    candidate_links_to_json,
    generate_candidate_links,
    generate_candidate_links_between,
    haversine_distance_m,
)


FIXTURE = Path(__file__).parent / "fixtures" / "resolution_sites.json"
AS_OF = "2026-07-17"
RECORDED_AT = "2026-07-17T20:00:00Z"


class ResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection, _ = initialize(
            Path(self.temporary_directory.name) / "atlas.sqlite"
        )
        self.records = {record["id"]: record for record in json.loads(FIXTURE.read_text())}

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def seed(self, *record_ids: str, reverse: bool = False) -> None:
        records = [self.records[record_id] for record_id in record_ids]
        if reverse:
            records.reverse()
        self.seed_records(records)

    def seed_records(self, records: list[dict], *, connection=None) -> None:
        connection = connection or self.connection
        for record in records:
            entity_id = record["id"]
            evidence_id = f"evidence:{entity_id}"
            add_evidence(
                connection,
                Evidence(
                    id=evidence_id,
                    kind=EvidenceKind.OTHER,
                    title=f"Source record {entity_id}",
                    source_url=record.get(
                        "source_url",
                        f"https://{record['source_family']}.example/{entity_id}",
                    ),
                    retrieved_at=RECORDED_AT,
                    source_family=record["source_family"],
                ),
                metadata=(
                    {"upstream_source_family": record["upstream_source_family"]}
                    if record.get("upstream_source_family")
                    else None
                ),
            )
            if record["kind"] == "campus":
                add_campus(
                    connection,
                    Campus(
                        entity_id,
                        record.get("stable_key", f"test:{entity_id}"),
                        evidence_id,
                    ),
                    created_at=RECORDED_AT,
                )
            else:
                add_facility(
                    connection,
                    Facility(
                        entity_id,
                        record.get("stable_key", f"test:{entity_id}"),
                        evidence_id,
                    ),
                    created_at=RECORDED_AT,
                )
            add_snapshot(
                connection,
                snapshot_id=f"snapshot:{entity_id}",
                entity_id=entity_id,
                name=record["name"],
                latitude=record["latitude"],
                longitude=record["longitude"],
                geometry=record.get("geometry"),
                tags=record["tags"],
                evidence_id=evidence_id,
                as_of_date=AS_OF,
                recorded_at=RECORDED_AT,
                method="test_fixture",
                confidence=0.9,
            )
        connection.commit()

    def report(self):
        return generate_candidate_links(
            self.connection, as_of=AS_OF, recorded_at=RECORDED_AT
        )

    def test_true_near_name_match_is_same_site_candidate(self) -> None:
        self.seed("same-a", "same-b")
        links = self.report()
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.relationship_suggestion, "same_site_candidate")
        self.assertGreater(link.score, 0.9)
        self.assertLess(link.distance_m, 50)
        self.assertEqual(link.signals["country_match"], True)
        self.assertEqual(link.signals["name_similarity"], 1.0)
        self.assertEqual(link.signals["left_source_root"], "county_permits")
        self.assertEqual(link.signals["right_source_root"], "satellite_inventory")
        self.assertIs(link.signals["source_independent"], True)
        self.assertEqual(
            {link.left_evidence_id, link.right_evidence_id},
            {"evidence:same-a", "evidence:same-b"},
        )

    def test_resolution_cutoff_normalizes_offsets_and_rejects_fractions(self) -> None:
        self.seed("same-a", "same-b")
        canonical = generate_candidate_links(
            self.connection,
            as_of=AS_OF,
            recorded_at=RECORDED_AT,
        )
        equivalent = generate_candidate_links(
            self.connection,
            as_of=AS_OF,
            recorded_at="2026-07-17T21:00:00.000+01:00",
        )
        before_snapshots = generate_candidate_links(
            self.connection,
            as_of=AS_OF,
            recorded_at="2026-07-17T21:00:00+02:00",
        )
        self.assertEqual(equivalent, canonical)
        self.assertEqual(before_snapshots, [])

        for label, cutoff in (
            ("fraction", "2026-07-17T20:00:00.500000Z"),
            ("submicrosecond", "2026-07-17T20:00:00.0000001Z"),
            ("naive", "2026-07-17T20:00:00"),
            ("invalid", "not-a-timestamp"),
        ):
            with self.subTest(rejected_cutoff=label):
                with self.assertRaises(ValueError):
                    generate_candidate_links(
                        self.connection,
                        as_of=AS_OF,
                        recorded_at=cutoff,
                    )

    def test_osm_derived_pnnl_link_is_retained_but_not_independent(self) -> None:
        self.assertEqual(
            _source_root("openstreetmap:pnnl_im3"),
            "openstreetmap",
        )
        self.seed_records(
            [
                {
                    "id": "osm-direct",
                    "kind": "facility",
                    "source_family": "openstreetmap",
                    "name": "Shared Compute Building",
                    "latitude": 39.0000,
                    "longitude": -77.0000,
                    "tags": {"country": "US", "operator": "Shared Compute"},
                },
                {
                    "id": "pnnl-derived",
                    "kind": "facility",
                    "source_family": "openstreetmap:pnnl_im3",
                    "name": "Shared Compute Building",
                    "latitude": 39.0001,
                    "longitude": -77.0001,
                    "tags": {"country": "USA", "operator": "Shared Compute"},
                },
            ]
        )

        links = self.report()
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertEqual(link.relationship_suggestion, "same_site_candidate")
        self.assertEqual(
            (link.left_entity_id, link.right_entity_id),
            ("osm-direct", "pnnl-derived"),
        )
        self.assertEqual(link.signals["left_source_root"], "openstreetmap")
        self.assertEqual(link.signals["right_source_root"], "openstreetmap")
        self.assertIs(link.signals["source_independent"], False)

        json_signals = json.loads(candidate_links_to_json(links))[0]["signals"]
        self.assertEqual(json_signals, link.signals)
        csv_row = next(csv.DictReader(io.StringIO(candidate_links_to_csv(links))))
        self.assertEqual(json.loads(csv_row["signals_json"]), link.signals)

    def test_explicit_upstream_metadata_controls_independence_for_any_family(self) -> None:
        self.seed_records(
            [
                {
                    "id": "permit-direct",
                    "kind": "facility",
                    "source_family": "county_permits",
                    "name": "Metadata Root Campus",
                    "latitude": 38.9,
                    "longitude": -77.1,
                "tags": {"country": "US"},
                },
                {
                    "id": "derived-index",
                    "kind": "facility",
                    "source_family": "third_party_index",
                    "upstream_source_family": "county permits",
                    "name": "Metadata Root Campus",
                    "latitude": 38.9001,
                    "longitude": -77.1001,
                    "tags": {"country": "US"},
                },
            ]
        )

        link = self.report()[0]
        self.assertEqual(link.signals["left_source_root"], "county_permits")
        self.assertEqual(link.signals["right_source_root"], "county_permits")
        self.assertIs(link.signals["source_independent"], False)

    def test_campus_facility_match_is_directional_part_of_candidate(self) -> None:
        self.seed("part-campus", "part-facility")
        link = self.report()[0]
        self.assertEqual(link.relationship_suggestion, "part_of_candidate")
        self.assertEqual(link.suggested_parent_entity_id, "part-campus")
        self.assertEqual(link.suggested_child_entity_id, "part-facility")
        self.assertTrue(link.signals["geometry_left_contains_right"])
        self.assertNotEqual(link.relationship_suggestion, "same_site_candidate")

    def test_neighboring_unrelated_sites_are_advisory_nearby_only(self) -> None:
        self.seed("near-a", "near-b")
        link = self.report()[0]
        self.assertEqual(link.relationship_suggestion, "nearby_only")
        self.assertLess(link.score, ResolutionThresholds().same_site_min_score)
        self.assertIsNone(link.suggested_parent_entity_id)
        self.assertIsNone(link.suggested_child_entity_id)

    def test_no_coordinate_country_mismatch_and_same_source_fail_closed(self) -> None:
        self.seed(
            "no-coordinate",
            "same-a",
            "country-mismatch-a",
            "country-mismatch-b",
            "same-source-a",
            "same-source-b",
        )
        pairs = {(link.left_entity_id, link.right_entity_id) for link in self.report()}
        self.assertFalse(any("no-coordinate" in pair for pair in pairs))
        self.assertNotIn(("country-mismatch-a", "country-mismatch-b"), pairs)
        self.assertNotIn(("same-source-a", "same-source-b"), pairs)

    def test_iso_country_name_alpha_2_and_alpha_3_match_for_japan(self) -> None:
        self.seed_records(
            [
                {
                    "id": f"japan-{index}",
                    "kind": "campus",
                    "source_family": f"source_{index}",
                    "name": "Tokyo Compute Campus",
                    "latitude": 35.68 + index * 0.00001,
                    "longitude": 139.76,
                    "tags": {"country": country},
                }
                for index, country in enumerate(("Japan", "JP", "JPN"))
            ]
        )
        links = self.report()
        self.assertEqual(len(links), 3)
        self.assertTrue(all(link.signals["country_match"] for link in links))
        self.assertTrue(
            all(
                link.signals["country_left"] == "JP"
                and link.signals["country_right"] == "JP"
                for link in links
            )
        )

    def test_every_embedded_iso_identifier_and_name_has_one_canonical_code(self) -> None:
        self.assertEqual(len(ISO_3166_1), 249)
        for alpha_2, alpha_3, names in ISO_3166_1:
            for value in (alpha_2, alpha_3, *names):
                with self.subTest(value=value):
                    self.assertEqual(_country({"country": value}), alpha_2)

    def test_curated_role_owner_matches_osm_operator(self) -> None:
        self.seed_records(
            [
                {
                    "id": "curated-role",
                    "kind": "campus",
                    "source_family": "official_disclosure",
                    "name": "Operator Campus",
                    "latitude": 35.0,
                    "longitude": 139.0,
                    "tags": {
                        "country": "JP",
                        "role:owner": "Example Infrastructure",
                    },
                },
                {
                    "id": "osm-role",
                    "kind": "campus",
                    "source_family": "openstreetmap",
                    "name": "Unlabelled Site",
                    "latitude": 35.0001,
                    "longitude": 139.0001,
                    "tags": {
                        "addr:country": "JPN",
                        "operator": "Example Infrastructure",
                    },
                },
            ]
        )
        link = self.report()[0]
        self.assertEqual(link.signals["owner_operator_similarity"], 1.0)

    def test_spatial_blocking_matches_brute_force_on_seeded_random_points(self) -> None:
        random_generator = random.Random(17072026)
        records = [
            _Record(
                entity_id=f"random-{index:03d}",
                kind="campus",
                name=None,
                latitude=random_generator.uniform(-75, 75),
                longitude=random_generator.uniform(-180, 180),
                geometry=None,
                tags={},
                evidence_id=f"evidence-{index:03d}",
                source_family=f"source-{index:03d}",
            )
            for index in range(180)
        ]
        records.extend(
            _Record(
                entity_id=f"cluster-{index:03d}",
                kind="campus",
                name=None,
                latitude=35 + random_generator.uniform(-0.03, 0.03),
                longitude=139 + random_generator.uniform(-0.03, 0.03),
                geometry=None,
                tags={},
                evidence_id=f"cluster-evidence-{index:03d}",
                source_family=f"cluster-source-{index:03d}",
            )
            for index in range(40)
        )
        threshold = 5_000.0

        brute_force = {
            (left.entity_id, right.entity_id)
            for index, left in enumerate(records)
            for right in records[index + 1 :]
            if haversine_distance_m(
                left.latitude, left.longitude, right.latitude, right.longitude
            )
            <= threshold
        }
        blocked = {
            (left.entity_id, right.entity_id)
            for left, right in _spatial_candidate_pairs(records, threshold)
            if haversine_distance_m(
                left.latitude, left.longitude, right.latitude, right.longitude
            )
            <= threshold
        }
        self.assertEqual(blocked, brute_force)

    def test_spatial_blocking_handles_antimeridian_and_high_latitude(self) -> None:
        coordinates = (
            ("date-line-east", 0.0, 179.999),
            ("date-line-west", 0.0, -179.999),
            ("north-a", 89.999, 0.0),
            ("north-b", 89.999, 180.0),
        )
        records = [
            _Record(
                entity_id=entity_id,
                kind="campus",
                name=None,
                latitude=latitude,
                longitude=longitude,
                geometry=None,
                tags={},
                evidence_id=f"evidence:{entity_id}",
                source_family=f"source:{entity_id}",
            )
            for entity_id, latitude, longitude in coordinates
        ]
        nearby_pairs = {
            frozenset((left.entity_id, right.entity_id))
            for left, right in _spatial_candidate_pairs(records, 500.0)
            if haversine_distance_m(
                left.latitude, left.longitude, right.latitude, right.longitude
            )
            <= 500.0
        }
        self.assertIn(frozenset(("date-line-east", "date-line-west")), nearby_pairs)
        self.assertIn(frozenset(("north-a", "north-b")), nearby_pairs)

    def test_cross_release_resolution_preserves_orientation_and_source_roots(self) -> None:
        right_directory = tempfile.TemporaryDirectory()
        right_connection, _ = initialize(Path(right_directory.name) / "atlas.sqlite")
        try:
            left_record = {
                "id": "scrutica-site",
                "kind": "facility",
                "source_family": "scrutica",
                "upstream_source_family": "openstreetmap",
                "name": "Digital Realty MRS1",
                "latitude": 43.3110164,
                "longitude": 5.3739134,
                "tags": {
                    "country": "France",
                    "operator": "Digital Realty",
                    "scrutica:upstream_source_url": "https://www.openstreetmap.org/way/68940404",
                },
            }
            right_record = {
                "id": "open-site",
                "kind": "facility",
                "source_family": "openstreetmap",
                "stable_key": "osm:way/68940404:facility-container",
                "source_url": "https://www.openstreetmap.org/way/68940404",
                "name": "Digital Realty MRS1",
                "latitude": 43.31101645,
                "longitude": 5.37391345,
                "tags": {"country": "FR", "operator": "Digital Realty"},
            }
            self.seed_records([left_record])
            self.seed_records([right_record], connection=right_connection)

            links = generate_candidate_links_between(
                self.connection,
                right_connection,
                left_as_of=AS_OF,
                left_recorded_at=RECORDED_AT,
                right_as_of=AS_OF,
                right_recorded_at=RECORDED_AT,
            )

            self.assertEqual(len(links), 1)
            link = links[0]
            self.assertEqual(
                (link.left_entity_id, link.right_entity_id),
                ("scrutica-site", "open-site"),
            )
            self.assertEqual(link.relationship_suggestion, "same_site_candidate")
            self.assertEqual(link.signals["left_source_root"], "openstreetmap")
            self.assertEqual(link.signals["right_source_root"], "openstreetmap")
            self.assertIs(link.signals["source_independent"], False)
            self.assertIs(link.signals["exact_upstream_identity_match"], True)
            self.assertEqual(
                link.signals["matching_upstream_identities"],
                ["openstreetmap:way/68940404"],
            )

            blocked = list(
                _spatial_candidate_pairs_between(
                    _current_records(
                        self.connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    ),
                    _current_records(
                        right_connection, as_of=AS_OF, recorded_at=RECORDED_AT
                    ),
                    5_000.0,
                )
            )
            self.assertEqual(
                [(left.entity_id, right.entity_id) for left, right in blocked],
                [("scrutica-site", "open-site")],
            )
        finally:
            right_connection.close()
            right_directory.cleanup()

    def test_cross_release_exact_osm_identity_survives_coordinate_conflict(self) -> None:
        right_directory = tempfile.TemporaryDirectory()
        right_connection, _ = initialize(Path(right_directory.name) / "atlas.sqlite")
        try:
            self.seed_records(
                [
                    {
                        "id": "left-coordinate-conflict",
                        "kind": "facility",
                        "source_family": "scrutica",
                        "name": "Conflicted Site",
                        "latitude": 40.0,
                        "longitude": -77.0,
                        "tags": {
                            "country": "US",
                            "scrutica:upstream_source_url": "https://www.openstreetmap.org/way/12345",
                        },
                    }
                ]
            )
            self.seed_records(
                [
                    {
                        "id": "right-coordinate-conflict",
                        "kind": "facility",
                        "source_family": "openstreetmap",
                        "stable_key": "osm:way/12345:facility-container",
                        "source_url": "https://www.openstreetmap.org/way/12345",
                        "name": "Conflicted Site",
                        "latitude": 40.2,
                        "longitude": -77.0,
                        "tags": {"country": "US"},
                    }
                ],
                connection=right_connection,
            )

            links = generate_candidate_links_between(
                self.connection,
                right_connection,
                left_as_of=AS_OF,
                left_recorded_at=RECORDED_AT,
                right_as_of=AS_OF,
                right_recorded_at=RECORDED_AT,
            )

            self.assertEqual(len(links), 1)
            self.assertGreater(links[0].distance_m, 5_000)
            self.assertEqual(links[0].relationship_suggestion, "nearby_only")
            self.assertTrue(links[0].signals["exact_upstream_identity_match"])
            self.assertGreaterEqual(links[0].score, 0.99)
        finally:
            right_connection.close()
            right_directory.cleanup()

    def test_cross_release_generic_urls_do_not_create_osm_identity(self) -> None:
        right_directory = tempfile.TemporaryDirectory()
        right_connection, _ = initialize(Path(right_directory.name) / "atlas.sqlite")
        try:
            self.seed_records(
                [
                    {
                        "id": "left-generic-url",
                        "kind": "facility",
                        "source_family": "left-source",
                        "source_url": "https://left.example/archive/way/12345",
                        "name": "Left Site",
                        "latitude": 40.0,
                        "longitude": -77.0,
                        "tags": {"country": "US"},
                    }
                ]
            )
            self.seed_records(
                [
                    {
                        "id": "right-generic-url",
                        "kind": "facility",
                        "source_family": "right-source",
                        "source_url": "https://right.example/source/way/12345",
                        "name": "Right Site",
                        "latitude": 40.2,
                        "longitude": -77.0,
                        "tags": {"country": "US"},
                    }
                ],
                connection=right_connection,
            )

            links = generate_candidate_links_between(
                self.connection,
                right_connection,
                left_as_of=AS_OF,
                left_recorded_at=RECORDED_AT,
                right_as_of=AS_OF,
                right_recorded_at=RECORDED_AT,
            )

            self.assertEqual(links, [])
        finally:
            right_connection.close()
            right_directory.cleanup()

    def test_large_distance_and_configured_thresholds_fail_closed(self) -> None:
        self.seed("same-a", "part-campus")
        self.assertEqual(self.report(), [])
        with self.assertRaises(ValueError):
            ResolutionThresholds(
                nearby_max_distance_m=100,
                same_site_max_distance_m=200,
            )

    def test_output_is_order_independent_idempotent_json_and_csv(self) -> None:
        ids = ("same-a", "same-b", "part-campus", "part-facility", "near-a", "near-b")
        self.seed(*ids, reverse=True)
        changes_before = self.connection.total_changes
        first = self.report()
        second = self.report()
        self.assertEqual(self.connection.total_changes, changes_before)
        self.assertEqual(first, second)
        json_once = candidate_links_to_json(first)
        self.assertEqual(json_once, candidate_links_to_json(second))
        self.assertEqual(json.loads(json_once)[0]["left_entity_id"], first[0].left_entity_id)
        csv_once = candidate_links_to_csv(first)
        self.assertEqual(csv_once, candidate_links_to_csv(second))
        rows = list(csv.DictReader(io.StringIO(csv_once)))
        self.assertEqual(len(rows), len(first))
        self.assertTrue(all(row["signals_json"] for row in rows))


if __name__ == "__main__":
    unittest.main()
