from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest

try:
    # Repository-root discovery loads the workspace shim around the inner package.
    from datacenter_atlas.datacenter_atlas.construction_master import (
        ConstructionMasterError,
        _canonical_line,
        _capacity_split,
        _definition,
        _netherlands_coordinates,
        _review_decisions,
        _structural_row,
        _tier_a_arithmetic_projection,
        _validate_output_row,
        _validate_v10_open_seed_source_allowlist,
        _validate_v11_open_seed_source_allowlist,
        _validate_v9_open_seed_source_allowlist,
        validate_construction_master,
        write_construction_master,
    )
except ModuleNotFoundError:
    from datacenter_atlas.construction_master import (
        ConstructionMasterError,
        _canonical_line,
        _capacity_split,
        _definition,
        _netherlands_coordinates,
        _review_decisions,
        _structural_row,
        _tier_a_arithmetic_projection,
        _validate_output_row,
        _validate_v10_open_seed_source_allowlist,
        _validate_v11_open_seed_source_allowlist,
        _validate_v9_open_seed_source_allowlist,
        validate_construction_master,
        write_construction_master,
    )


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-18-public-open-v1.json"
)
BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-18-public-open-v1"
)
V2_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-18-public-open-v2.json"
)
V2_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-18-public-open-v2"
)
V3_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-18-public-open-v3.json"
)
V3_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-18-public-open-v3"
)
V4_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-18-public-open-v4.json"
)
V4_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-18-public-open-v4"
)
V5_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-18-public-open-v5.json"
)
V5_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-18-public-open-v5"
)
V6_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v6.json"
)
V6_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v6"
)
V7_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v7.json"
)
V7_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v7"
)
V8_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v8.json"
)
V8_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v8"
)
V9_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v9.json"
)
V9_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v9"
)
V10_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v10.json"
)
V10_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v10"
)
V11_DEFINITION = (
    PACKAGE_ROOT
    / "sources"
    / "construction-master-2026-07-19-public-open-v11.json"
)
V11_BUNDLE = (
    PACKAGE_ROOT
    / "construction_master"
    / "2026-07-19-public-open-v11"
)
TIER_A_PROJECTION_SHA256 = (
    "5ff330359d276f2cee6e0f603321d390395564827900d16a9e1a9df2d59abe13"
)
V6_TIER_A_PROJECTION_SHA256 = (
    "b6bc6cd6afbb841e9b1f9a89cb1f4f59c6dcdc0d15af75d3ffff864e4316f6a0"
)
V7_TIER_A_PROJECTION_SHA256 = (
    "4eb28b56189e86dca6bb982c9f53153b300151858437919086d36a7913195efa"
)
V8_TIER_A_PROJECTION_SHA256 = (
    "c9d7110ac5ff37e6f3a6ca4d2e752dae6c3bbd9eb32f2bd75859ed24e9ce66f0"
)
V9_TIER_A_PROJECTION_SHA256 = (
    "10c2dfb4732f31cc15fc85078e33512ce08d5381343fa614cf9e27a531618900"
)
V10_TIER_A_PROJECTION_SHA256 = (
    "1ed1fc94fcf31862a9e67625a1f30ee0081bbcfa02d7f0c4020b63bd047d14c5"
)
V11_TIER_A_PROJECTION_SHA256 = (
    "1a181a9b456fb65fc566e7dd029885055fd6071b93cfa81dba002d4435e12346"
)
V7_MASTER_BUNDLE_INVENTORY_SHA256 = (
    "0ee0d38af1211767425bbac46246569dce0b6408c7fa87d0c1aaf5bf4261f65f"
)
V8_MASTER_BUNDLE_INVENTORY_SHA256 = (
    "e79a768aacec83a6d786b57dee455da6dbff0f1abee8a493baf4842447d6877b"
)
V9_MASTER_BUNDLE_INVENTORY_SHA256 = (
    "79f34543f4c3210c6d3a2777c5b4d91dfec058a0d9a699ad9539638bcf9bfdd3"
)
V10_MASTER_BUNDLE_INVENTORY_SHA256 = (
    "17ef53fbafcb12a2e79a2fc90393b5980b29d81d24b8f152ba40fb64e089567f"
)
V11_MASTER_BUNDLE_INVENTORY_SHA256 = (
    "d1ce6c8f84ff2f5caab140d7b464cf2844418482310c90601be38bb510897d14"
)
V9_ADDITION_IDS = {
    "1d95d387-1806-5dda-a619-a50e84852137",
    "27f804d6-f887-51a3-9564-4e738793d2f8",
    "296ce9ca-8904-5976-9226-aa9ee6b9ae70",
    "55f4eb88-750d-5aa5-b4cb-bd5b8e746fe6",
    "6564e429-77a5-5548-a5b0-ec6f2a402d47",
    "6e05e286-dbad-5550-900d-ed0c2294e5a2",
    "7206a400-093d-5c92-b1c5-c4243807de29",
    "7d936c4e-29f2-592f-984b-61f5d6367fc8",
    "9c96ba2a-1e05-53b4-a7bb-86057ddcba1f",
    "b7744ad5-aa48-5977-a70e-3d6a588f468d",
    "bdfd522f-2d7e-5d1f-8e00-3c43b462ed27",
    "c6c50c6d-b3b3-5e33-bed0-4da5b6372a9b",
    "c73ac912-e44d-5477-84f5-c5beb4813518",
}
V10_ADDITION_IDS = {
    "00e29c41-b45a-5122-bbd0-06e70b6c86c5",
    "01baa3bb-ea56-5f41-8c67-82dd84f87d51",
    "04f9041c-c8b3-5cae-9847-f42fd234cf8a",
    "07ad21b7-7b59-5350-b9ac-6219a754dfd0",
    "0bac3fe4-c3dd-54ba-a500-e37599191432",
    "1b131d68-2d8f-5a87-a381-e8379fbda89c",
    "257f3255-46fe-585e-bdf5-9689b34edbdc",
    "3b7bb37e-1ec4-5425-9ed2-8b6218f2daa2",
    "3da754aa-aecc-55d0-b376-c3c8eed7d3bc",
    "561d398c-ccd3-54ed-aca3-f3281588d258",
    "5b11c034-5a3b-5e5d-bc6a-b7122e21fbec",
    "5b758548-2a2a-5643-9ebb-d8381bbd2c52",
    "5dfce968-5eac-54c5-a918-38241575dade",
    "64289119-458d-5fc9-bf51-5af6097220eb",
    "68acede3-101f-5ae6-a45d-716a9ee15466",
    "693b48ea-a6fc-5ddd-8030-56b6738c136f",
    "86bcbcd1-702d-5afa-aeb8-1cb145224b97",
    "8a9c92d8-7316-5754-96f6-74ca16982936",
    "8d6cdc86-b9ea-5053-a3a8-9f41a527fe59",
    "901f4e12-01cc-52df-80c9-0d0a57eff3d3",
    "97c55ef3-761e-52c1-ac61-24383954d5b4",
    "ae6f1b86-660b-54e9-bdb0-d29bfeedc551",
    "b128f3c3-7a64-544d-90a2-7ffd0a04004d",
    "b3b98301-a692-5790-88e7-656d77e8fb69",
    "c1af62b5-b9a2-5c15-a8a4-717e1a65ac05",
    "e0495b75-1484-512a-a78a-d665e645423f",
    "e89851de-ce81-5716-9b25-731ca4e6bf6b",
    "eaea9fff-9fd3-506f-a490-320f64d86dc3",
    "edf978b4-fbe8-5f8a-9fe0-bd1e9f33e1d2",
    "f166440f-2ab0-57ea-9788-c66d89c8704f",
    "f8377a0f-dc89-5b7a-8257-25f25cdbac43",
    "ffcc0e27-a87b-5156-baab-7ecf742c6483",
}
V11_ADDITION_IDS = {
    "08d881e7-8a1c-50da-81a5-d2ef49f22a7a",
    "0f066630-b500-5f76-9441-f1907f296a8a",
    "1146aaae-d272-593e-a4f3-3c40758f8968",
    "19f6a887-c4b1-57a7-9fee-2f11325a5b1d",
    "20a0ee24-7743-5cd5-8e01-101d67fc45a2",
    "31e5c099-e5b2-50ad-aa96-75ab36f8d379",
    "32633f5d-f51c-5e7f-800f-60890e1aed86",
    "32e68328-bf83-586d-a61c-ff8c03033b57",
    "3b636397-fbb2-5564-a352-fa1382a218b5",
    "42e50e84-873d-562d-b6d2-945ccf04b0e8",
    "48646c6d-7c07-5abb-837d-95d6edd26ead",
    "4b29bb7c-4d76-5d38-b759-5428e33e267a",
    "58f9a985-bfa8-521c-ab85-132aec6799ed",
    "5c74734b-c174-5bab-9a07-45b003d1d15e",
    "68e0ea6c-dafd-5539-ace8-400e100a90e0",
    "6f0acd88-cd04-5f3f-915c-48a71fd51f39",
    "7352e9b5-ecec-5497-8c62-3e6a8c7bd012",
    "75bb58d8-5a41-51d7-8de4-faf05b6b83bf",
    "7b6d8192-dc67-5bf4-8edc-a00d60a3d734",
    "8987866e-e9e3-50cc-b5d8-7be2cc2a6322",
    "89ea003c-2575-583c-972f-fe36c28faec6",
    "8a5fbd17-48b6-5484-8c37-ce406068bf3e",
    "95b33a98-a85e-57af-b18d-6811a7fd3b20",
    "97c0806f-bfbe-59d6-ae4f-4e5549aeb2c8",
    "a0f607c6-6bed-51fc-a893-e21e20b6af43",
    "a862135b-2c05-5301-8040-8b956e1c8d58",
    "aa93c84a-17d6-5092-bf57-686f7e1ab4a4",
    "ad5f9b2b-80bf-5580-92f2-0f53473c882d",
    "af44300d-5ec1-54ff-a231-eefbdd86d20b",
    "b0336b49-7509-5a68-a7ff-b7aab1417abd",
    "b65afdbc-477a-5b22-b224-bf2c38d02824",
    "b971a3b7-451d-5c58-bdb5-9c2c8608484f",
    "be93b7b8-98b8-5905-92d0-8df90ab5b6d5",
    "c03e41c9-1c16-588d-b932-b884315fc310",
    "c20ad85e-1123-562a-930f-ceb41b1d15e5",
    "c789668b-ecf3-53b2-b23c-44151e199317",
    "c8d0b8fc-cb45-5911-9849-7abe0f98186d",
    "cafab9a5-428c-5442-98d3-3784f9ecc7bb",
    "d1538d73-e301-5203-9e49-924b20051374",
    "d37505c3-b07d-5b6a-b1d3-3c3a7318f572",
    "d612af72-f507-5a0c-9115-6ed7870dd389",
    "e39b5191-4a78-5781-8944-24efaf944aa9",
    "e4e51c8d-a98e-50a4-ba16-0795f1f3f63a",
    "f054a923-1869-5cee-aec7-f9673b431f14",
    "f9208ecb-fd7c-57e8-93ca-b1dfb0cae8d9",
    "faa3c855-33e5-5295-abb8-182c74f4fbd6",
}
LEGACY_MASTER_BUNDLE_INVENTORY_SHA256 = {
    "v1": "93f49154b9a837531ebf7ae8bcb1c1298de730a1078c60098db9d17c4ea748a5",
    "v2": "b196cd84a4786f21de984a0ecb0d6215dba33f89de4418b34dcb07243e1107fe",
    "v3": "ca4e52a47025666aa937af4480591715d856f4b24a3f5dff52349f7d183e6ba9",
    "v4": "7cdf61f2b119137a6d6589c05f8821f85ec6bf0513c7d9ba119e85eb90ef224b",
    "v5": "8bf52436d16baac1967905d4c7f30a3e9badb1323df5cec6301daa30d779bd37",
    "v6": "7c66df87b78437198eab280ad4db55216afadc11f2997324880eb74e99949510",
}


def _jsonl_rows(path: Path):
    with path.open("rb") as source:
        for raw_line in source:
            yield json.loads(raw_line)


def _tier_a_projections(bundle: Path) -> list[dict]:
    projections = []
    for row in _jsonl_rows(bundle / "construction-master.jsonl"):
        if row["tier"] != "A":
            break
        projections.append(_tier_a_arithmetic_projection(row))
    return projections


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def _first_ireland_row() -> dict:
    for row in _jsonl_rows(V2_BUNDLE / "construction-master.jsonl"):
        if row["observation_kind"] == "official_planning_application_review_lead":
            return row
    raise AssertionError("frozen v2 bundle has no Ireland planning row")


def _first_england_row() -> dict:
    for row in _jsonl_rows(V3_BUNDLE / "construction-master.jsonl"):
        if (
            row["observation_kind"]
            == "official_england_planning_application_review_lead"
        ):
            return row
    raise AssertionError("frozen v3 bundle has no England planning row")


def _rows_of_kind(bundle: Path, observation_kind: str) -> list[dict]:
    return [
        row
        for row in _jsonl_rows(bundle / "construction-master.jsonl")
        if row["observation_kind"] == observation_kind
    ]


def _release_rows(bundle: Path, artifact_id: str) -> dict[str, dict]:
    rows = {}
    for row in _jsonl_rows(bundle / "construction-master.jsonl"):
        if row["source"]["artifact_id"] == artifact_id:
            rows[row["source"]["record_id"]] = row
        elif rows:
            break
    return rows


class ConstructionMasterTests(unittest.TestCase):
    def test_netherlands_nearby_points_use_mean_and_distant_points_fail_closed(self) -> None:
        def metadata(points):
            return {
                "geographic_markers": [
                    {
                        "location_points": [
                            {
                                "crs": "ETRS89",
                                "latitude": latitude,
                                "longitude": longitude,
                            }
                        ]
                    }
                    for latitude, longitude in points
                ]
            }

        nearby = [
            (52.3954478250084, 4.87018675162924),
            (52.3955062967764, 4.87122920359996),
        ]
        latitude, longitude, method = _netherlands_coordinates(metadata(nearby))
        self.assertAlmostEqual(latitude, sum(point[0] for point in nearby) / 2)
        self.assertAlmostEqual(longitude, sum(point[1] for point in nearby) / 2)
        self.assertEqual(
            method,
            "official_koop_mean_of_nearby_etrs89_points_review_only",
        )

        distant = [(52.0, 4.0), (52.01, 4.0)]
        self.assertEqual(
            _netherlands_coordinates(metadata(distant)),
            (None, None, None),
        )

        duplicated = [(52.0, 4.0), (52.0, 4.0)]
        self.assertEqual(
            _netherlands_coordinates(metadata(duplicated)),
            (52.0, 4.0, "official_koop_single_unambiguous_etrs89_point"),
        )

    def test_capacity_energy_and_pue_are_separate_typed_observations(self) -> None:
        capacity, annual, pue = _capacity_split(
            [
                {
                    "base": 100,
                    "confidence": 0.8,
                    "metric": "gross_facility_mw",
                    "stage": "forecast",
                    "unit": "MW",
                },
                {
                    "base": 750000,
                    "confidence": 0.5,
                    "metric": "annual_energy_mwh",
                    "stage": "forecast",
                    "unit": "MWh/year",
                },
                {
                    "base": 1.2,
                    "confidence": 0.6,
                    "metric": "pue",
                    "stage": "target",
                    "unit": "ratio",
                },
            ]
        )

        self.assertEqual([item["metric"] for item in capacity], ["gross_facility_mw"])
        self.assertEqual([item["metric"] for item in annual], ["annual_energy_mwh"])
        self.assertEqual([item["metric"] for item in pue], ["pue"])
        self.assertTrue(all(item["scope"] == "source_scoped_entity" for item in [*capacity, *annual, *pue]))

    def test_structural_row_cannot_be_promoted_and_keeps_overlay_advisory(self) -> None:
        feature = {
            "geometry": {
                "coordinates": [[[10.0, 20.0], [12.0, 20.0], [12.0, 22.0], [10.0, 20.0]]],
                "type": "Polygon",
            },
            "id": "way/1",
            "properties": {
                "data_centre_identity_inferred": False,
                "footprint_square_metres": 1000,
                "review_only": True,
                "review_reasons": [],
                "review_score": 3,
                "source_tag_families": ["proposed"],
                "source_tags": {"landuse": "proposed"},
                "source_url": "https://www.openstreetmap.org/way/1",
            },
            "type": "Feature",
        }
        spec = {
            "artifact_id": "fixture-structural",
            "data": {"path": "shortlist.geojson", "sha256": "a" * 64},
            "manifest": {"sha256": "b" * 64},
            "release_id": "fixture-v1",
        }
        row = _structural_row(
            feature,
            spec=spec,
            overlay={
                "fusion_rank": 1,
                "priority_tier": "review",
                "satellite_links": [{"queue_id": "satq-one"}],
            },
        )

        self.assertEqual(row["tier"], "C")
        self.assertEqual(row["lifecycle"]["normalized_status"], "structural_proposed_signal")
        self.assertFalse(row["construction"]["verified"])
        self.assertFalse(row["disposition"]["construction_arithmetic_included"])
        self.assertEqual(row["identity"]["status"], "data_centre_identity_not_inferred")
        self.assertEqual(row["satellite_links"], [{"queue_id": "satq-one"}])
        self.assertNotIn("satellite_links", row["fusion_overlay"])

    def test_frozen_bundle_reproduces_byte_for_byte_offline(self) -> None:
        manifest = validate_construction_master(BUNDLE, definition_path=DEFINITION)
        self.assertEqual(manifest["row_counts"]["total"], 108766)
        self.assertEqual(manifest["row_counts"]["by_tier"], {"A": 168, "B": 6139, "C": 102459})
        coverage = json.loads((BUNDLE / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["construction_arithmetic"]["rows"], 168)
        self.assertIsNone(coverage["construction_arithmetic"]["unique_physical_sites"])
        self.assertEqual(coverage["fusion"]["rows_with_opportunity_overlay"], 14324)
        self.assertEqual(coverage["within_release_resolution"]["advisory_links"], 8586)
        self.assertEqual(
            coverage["satellite"]["batch_accounting"]["satellite-global-open-v3-unknown-003"]["states"],
            {"completed": 337, "pending": 6386, "unavailable_no_scene": 13},
        )
        self.assertIn("replaces unknown-002", coverage["satellite"]["cumulative_unknown_batch_policy"])

    def test_frozen_v2_bundle_reproduces_byte_for_byte_offline(self) -> None:
        manifest = validate_construction_master(
            V2_BUNDLE, definition_path=V2_DEFINITION
        )
        self.assertEqual(manifest["row_counts"]["total"], 108893)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 168, "B": 6253, "C": 102472},
        )
        coverage = json.loads(
            (V2_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        arithmetic = coverage["construction_arithmetic"]
        self.assertEqual(arithmetic["rows"], 168)
        self.assertEqual(arithmetic["verified_by_independent_master_review"], 0)
        self.assertEqual(
            arithmetic["tier_a_arithmetic_projection_sha256"],
            TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["review_leads"]["ireland_planning"]["observation_rows"],
            114,
        )
        ireland_relationships = coverage["review_leads"]["ireland_planning"][
            "relationship_suggestions"
        ]
        self.assertEqual(ireland_relationships["suggestion_groups"], 32)
        self.assertEqual(ireland_relationships["accepted_relationships"], 0)
        self.assertEqual(ireland_relationships["automatic_merges"], 0)
        self.assertIsNone(ireland_relationships["unique_physical_site_count"])
        self.assertEqual(coverage["satellite"]["analyst_review_rows"], 21)
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-007"
            ]["states"],
            {"completed": 724, "pending": 5986, "unavailable_no_scene": 26},
        )
        batch_ids = set(coverage["satellite"]["batch_accounting"])
        self.assertFalse(
            batch_ids
            & {
                f"satellite-global-open-v3-unknown-{number:03d}"
                for number in range(1, 7)
            }
        )

    def test_frozen_v3_bundle_reproduces_byte_for_byte_offline(self) -> None:
        manifest = validate_construction_master(
            V3_BUNDLE, definition_path=V3_DEFINITION
        )
        self.assertEqual(manifest["row_counts"]["total"], 108900)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 168, "B": 6256, "C": 102476},
        )
        coverage = json.loads(
            (V3_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["satellite"]["analyst_review_rows"], 25)
        self.assertEqual(
            coverage["satellite"]["analyst_decisions"],
            {
                "reject_automated_mask_for_site_promotion": 18,
                "retain_site_aligned_change_candidate_for_manual_followup": 7,
            },
        )
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-009"
            ]["states"],
            {"completed": 918, "pending": 5786, "unavailable_no_scene": 32},
        )
        self.assertEqual(
            set(coverage["satellite"]["batch_accounting"]),
            {
                "satellite-global-open-v3-active-001",
                "satellite-global-open-v3-proposed-001",
                "satellite-global-open-v3-unknown-009",
            },
        )
        self.assertEqual(
            coverage["fusion"]["rows_with_opportunity_overlay"], 14324
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            TIER_A_PROJECTION_SHA256,
        )

    def test_v3_is_frozen_and_tier_a_projection_matches_v1_and_v2(self) -> None:
        self.assertEqual(stat.S_IMODE(V3_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V3_BUNDLE.iterdir()
            )
        )
        v1 = _tier_a_projections(BUNDLE)
        self.assertEqual(_tier_a_projections(V2_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V3_BUNDLE), v1)

    def test_frozen_v4_bundle_reproduces_exact_accounting_offline(self) -> None:
        manifest = validate_construction_master(
            V4_BUNDLE, definition_path=V4_DEFINITION
        )
        self.assertEqual(manifest["row_counts"]["total"], 108944)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 168, "B": 6294, "C": 102482},
        )
        coverage = json.loads(
            (V4_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["row_counts"]["review_only"], 108776)
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 1,
                "expansion": 27,
                "proposed": 21,
                "under_construction": 119,
            },
        )
        self.assertEqual(
            coverage["satellite"]["analyst_decisions"],
            {
                "reject_automated_mask_for_site_promotion": 23,
                "retain_site_aligned_change_candidate_for_manual_followup": 8,
            },
        )
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-011"
            ]["states"],
            {"completed": 1114, "pending": 5586, "unavailable_no_scene": 36},
        )

    def test_v4_is_frozen_and_preserves_every_legacy_tier_a_projection(self) -> None:
        self.assertEqual(stat.S_IMODE(V4_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V4_BUNDLE.iterdir()
            )
        )
        v1 = _tier_a_projections(BUNDLE)
        self.assertEqual(_tier_a_projections(V2_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V3_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V4_BUNDLE), v1)

    def test_v4_official_lanes_preserve_source_boundaries(self) -> None:
        nsw_kind = "official_nsw_major_projects_planning_review_lead"
        netherlands_kind = "official_netherlands_koop_permit_review_lead"
        new_zealand_kind = "official_new_zealand_fast_track_review_lead"
        nsw_rows = _rows_of_kind(V4_BUNDLE, nsw_kind)
        netherlands_rows = _rows_of_kind(V4_BUNDLE, netherlands_kind)
        new_zealand_rows = _rows_of_kind(V4_BUNDLE, new_zealand_kind)
        self.assertEqual(
            (len(nsw_rows), len(netherlands_rows), len(new_zealand_rows)),
            (22, 13, 3),
        )

        self.assertEqual(
            sum(len(row["untyped_capacity_statements"]) for row in nsw_rows),
            10,
        )
        for row in nsw_rows:
            _validate_output_row(row)
            metadata = row["source_evidence"][0]["planning_metadata"]
            self.assertFalse(
                metadata["portal_process_fields_are_physical_lifecycle"]
            )
            self.assertFalse(metadata["typed_power_or_energy_promoted"])
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])

        for row in netherlands_rows:
            _validate_output_row(row)
            metadata = row["source_evidence"][0]["permit_metadata"]
            self.assertFalse(metadata["permit_stage_is_physical_lifecycle"])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertEqual(row["workload_observations"], [])
        self.assertEqual(
            sum(row["entity"]["latitude"] is not None for row in netherlands_rows),
            12,
        )
        self.assertEqual(
            sum(
                row["entity"]["coordinate_method"]
                == "official_koop_mean_of_nearby_etrs89_points_review_only"
                for row in netherlands_rows
            ),
            4,
        )

        workload_rows = []
        classifications = []
        for row in new_zealand_rows:
            _validate_output_row(row)
            metadata = row["source_evidence"][0]["planning_metadata"]
            observation = metadata["source_observation"]
            classifications.append(observation["candidate_classification"])
            self.assertFalse(metadata["facility_lifecycle_from_process_stage"])
            self.assertFalse(
                metadata["land_area_promoted_to_data_centre_area_or_power"]
            )
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            if row["workload_observations"]:
                workload_rows.append(row)
        self.assertEqual(
            sorted(classifications),
            [
                "direct_data_centre_project_candidate",
                "direct_data_centre_project_candidate",
                "prior_related_planning_observation",
            ],
        )
        self.assertEqual(len(workload_rows), 1)
        self.assertEqual(
            workload_rows[0]["workload_observations"],
            [
                {
                    "operationally_verified": False,
                    "scope": "proposed component of a mixed-use project",
                    "stage": "proposed",
                    "workload": "artificial_intelligence",
                }
            ],
        )
        characterisation = workload_rows[0]["source_evidence"][0][
            "planning_metadata"
        ]["source_observation"]["data_centre_characterisation"]
        self.assertEqual(characterisation["declared_facility_type"], "hyperscale")
        self.assertFalse(characterisation["operationally_verified"])

    def test_v4_excludes_restricted_source_lanes_and_context_rows(self) -> None:
        coverage = json.loads(
            (V4_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        artifacts = set(coverage["row_counts"]["by_source_artifact"])
        self.assertFalse(
            artifacts
            & {
                "chile-sea-pertinence-data-centres-2026-07-18-v1",
                "epbc-public-portal-data-centre-search-2026-07-18-v1",
                "iaac-data-center-search-2026-07-18-v1",
            }
        )
        self.assertEqual(
            coverage["review_leads"]["netherlands_koop"][
                "context_rows_excluded"
            ],
            7,
        )
        self.assertEqual(
            coverage["review_leads"]["new_zealand_fast_track"][
                "candidate_classifications_exact"
            ],
            {
                "direct_data_centre_project_candidate": 2,
                "prior_related_planning_observation": 1,
            },
        )

    def test_v4_keeps_unknown010_review_lineage_and_unknown011_catalog_state(self) -> None:
        unknown_review_rows = [
            row
            for row in _rows_of_kind(
                V4_BUNDLE, "sentinel_analyst_change_review"
            )
            if "unknown-010" in row["source"]["artifact_path"]
        ]
        self.assertTrue(unknown_review_rows)
        for row in unknown_review_rows:
            link = row["satellite_links"][0]
            self.assertEqual(
                link["batch_artifact_id"],
                "satellite-global-open-v3-unknown-010",
            )
            self.assertEqual(
                link["catalog_batch_artifact_id"],
                "satellite-global-open-v3-unknown-011",
            )
        manifest = json.loads(
            (V4_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        self.assertIn(
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-011/batch-manifest.json",
            lineage_paths,
        )
        self.assertTrue(
            any("unknown-010/jobs/" in path for path in lineage_paths)
        )

    def test_v4_definition_contract_rejects_count_drift(self) -> None:
        document = json.loads(V4_DEFINITION.read_text(encoding="utf-8"))
        document["expected_counts"]["nsw_planning_rows"] = 21
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / "construction-master-v4.json"
            changed.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConstructionMasterError, "v4 count or Tier-A parity contract changed"
            ):
                _definition(changed)

    def test_frozen_v5_bundle_reproduces_exact_accounting_offline(self) -> None:
        manifest = validate_construction_master(
            V5_BUNDLE, definition_path=V5_DEFINITION
        )
        self.assertEqual(manifest["row_counts"]["total"], 108960)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 168, "B": 6298, "C": 102494},
        )
        coverage = json.loads(
            (V5_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["satellite"]["analyst_decisions"],
            {
                "reject_automated_mask_for_site_promotion": 31,
                "retain_site_aligned_change_candidate_for_manual_followup": 12,
            },
        )
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-015"
            ]["states"],
            {"completed": 1308, "pending": 5386, "unavailable_no_scene": 42},
        )

    def test_v5_is_frozen_and_preserves_every_legacy_tier_a_projection(self) -> None:
        self.assertEqual(stat.S_IMODE(V5_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V5_BUNDLE.iterdir()
            )
        )
        v1 = _tier_a_projections(BUNDLE)
        self.assertEqual(_tier_a_projections(V2_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V3_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V4_BUNDLE), v1)
        self.assertEqual(_tier_a_projections(V5_BUNDLE), v1)

    def test_v5_france_rows_preserve_metric_and_relationship_boundaries(self) -> None:
        kind = "official_france_igedd_environmental_opinion_review_lead"
        rows = _rows_of_kind(V5_BUNDLE, kind)
        self.assertEqual(len(rows), 4)
        classifications = Counter()
        metric_types = Counter()
        relationship_rows = []
        for row in rows:
            _validate_output_row(row)
            metadata = row["source_evidence"][0][
                "environmental_review_metadata"
            ]
            source_observation = metadata["source_observation"]
            classifications[metadata["classification"]] += 1
            metric_types.update(
                metric["metric_type"] for metric in source_observation["metrics"]
            )
            self.assertEqual(
                row["lifecycle"],
                {
                    "normalized_status": None,
                    "reported_status": None,
                    "reported_status_date": None,
                },
            )
            self.assertIsNone(row["entity"]["latitude"])
            self.assertIsNone(row["entity"]["longitude"])
            self.assertIsNone(row["entity"]["coordinate_method"])
            self.assertFalse(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertFalse(
                row["disposition"]["construction_arithmetic_included"]
            )
            self.assertFalse(row["disposition"]["unique_site_counted"])
            self.assertEqual(row["workload_observations"], [])
            self.assertIsNone(row["operating_model_observation"])
            self.assertTrue(
                metadata["typed_metric_semantics_preserved_without_conversion"]
            )
            relationship = metadata["within_source_relationship"]
            if relationship is not None:
                relationship_rows.append(row)
                self.assertEqual(
                    relationship,
                    {
                        "advisory_only": True,
                        "automatic_merge_permitted": False,
                        "relationship_type": "related_direct_observation",
                        "related_observation_id": "fr-igedd-ae-2025-058",
                        "source_stated": True,
                    },
                )
        self.assertEqual(
            classifications,
            Counter(
                {
                    "direct_data_centre_project": 3,
                    "ancillary_grid_connection_follow_up": 1,
                }
            ),
        )
        self.assertEqual(
            metric_types,
            Counter(
                {
                    "backup_generation_thermal_capacity": 3,
                    "backup_generation_electrical_capacity": 2,
                    "it_power_capacity": 2,
                    "battery_maximum_recharge_power": 1,
                    "projected_annual_site_electricity_consumption": 1,
                    "projected_full_load_annual_electricity_consumption": 1,
                    "requested_grid_connection_power": 1,
                    "target_pue": 1,
                    "ups_and_battery_power": 1,
                }
            ),
        )
        self.assertEqual(len(relationship_rows), 1)
        self.assertEqual(
            relationship_rows[0]["source"]["record_id"],
            "fr-igedd-ae-2026-33",
        )
        self.assertEqual(
            sum(len(row["capacity_observations"]) for row in rows), 10
        )
        self.assertEqual(
            sum(len(row["annual_energy_observations"]) for row in rows), 2
        )
        self.assertEqual(sum(len(row["pue_observations"]) for row in rows), 1)
        explicit_it = [
            metric
            for row in rows
            for metric in row["capacity_observations"]
            if metric["metric_type"] == "it_power_capacity"
        ]
        self.assertEqual(
            [(metric["value"], metric["unit"]) for metric in explicit_it],
            [(60, "MW"), (36, "MW")],
        )
        projected = [
            metric
            for row in rows
            for metric in [
                *row["annual_energy_observations"],
                *row["pue_observations"],
            ]
        ]
        self.assertTrue(
            all(
                "not measured" in metric["qualifier"]
                for metric in projected
            )
        )

        coverage = json.loads(
            (V5_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        france = coverage["review_leads"]["france_igedd"]
        self.assertEqual(france["observation_rows"], 4)
        self.assertEqual(france["metric_observations"], 13)
        self.assertEqual(france["relationship_evidence_records"], 1)
        self.assertTrue(france["derived_rows_publication_eligible"])
        self.assertFalse(france["unit_conversions_applied"])
        self.assertFalse(
            france[
                "backup_support_and_grid_metrics_promoted_to_it_or_facility_load"
            ]
        )
        self.assertIsNone(france["unique_physical_site_count"])

    def test_v5_france_rows_fail_closed_against_semantic_promotion(self) -> None:
        kind = "official_france_igedd_environmental_opinion_review_lead"
        rows = _rows_of_kind(V5_BUNDLE, kind)
        lifecycle_promoted = deepcopy(rows[0])
        lifecycle_promoted["lifecycle"]["normalized_status"] = "under_construction"
        with self.assertRaisesRegex(
            ConstructionMasterError, "France IGEDD row was promoted"
        ):
            _validate_output_row(lifecycle_promoted)

        metric_relabelled = deepcopy(rows[0])
        metric_relabelled["capacity_observations"][2][
            "metric_type"
        ] = "it_power_capacity"
        with self.assertRaisesRegex(
            ConstructionMasterError, "France IGEDD metric semantics changed"
        ):
            _validate_output_row(metric_relabelled)

        ancillary = next(
            row
            for row in rows
            if row["source"]["record_id"] == "fr-igedd-ae-2026-33"
        )
        relationship_promoted = deepcopy(ancillary)
        relationship_promoted["source_evidence"][0][
            "environmental_review_metadata"
        ]["within_source_relationship"]["automatic_merge_permitted"] = True
        with self.assertRaisesRegex(
            ConstructionMasterError, "France IGEDD relationship evidence changed"
        ):
            _validate_output_row(relationship_promoted)

    def test_v5_keeps_frozen_review_lineage_and_unknown015_catalog_state(self) -> None:
        review_rows = _rows_of_kind(
            V5_BUNDLE, "sentinel_analyst_change_review"
        )
        self.assertEqual(len(review_rows), 43)
        self.assertEqual(
            Counter(
                row["satellite_links"][0]["batch_artifact_id"]
                for row in review_rows
            ),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        older_unknown = [
            row
            for row in review_rows
            if row["satellite_links"][0]["batch_artifact_id"]
            in {
                "satellite-global-open-v3-unknown-010",
                "satellite-global-open-v3-unknown-013",
            }
        ]
        self.assertEqual(len(older_unknown), 29)
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-015"
                for row in older_unknown
            )
        )
        manifest = json.loads(
            (V5_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        self.assertIn(
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-015/batch-manifest.json",
            lineage_paths,
        )
        self.assertTrue(any("unknown-010/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-013/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-015/jobs/" in path for path in lineage_paths))

    def test_v5_excludes_unapproved_country_lanes(self) -> None:
        coverage = json.loads(
            (V5_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        artifacts = set(coverage["row_counts"]["by_source_artifact"])
        excluded_fragments = {
            "brazil",
            "chile",
            "epbc",
            "germany",
            "iaac",
            "italy",
            "spain",
        }
        self.assertFalse(
            {
                artifact
                for artifact in artifacts
                if any(fragment in artifact.lower() for fragment in excluded_fragments)
            }
        )

    def test_v5_definition_contract_rejects_count_or_france_pin_drift(self) -> None:
        document = json.loads(V5_DEFINITION.read_text(encoding="utf-8"))
        count_changed = deepcopy(document)
        count_changed["expected_counts"]["france_igedd_rows"] = 3
        france_changed = deepcopy(document)
        france_changed["inputs"]["tier_b_france_igedd"]["manifest"][
            "sha256"
        ] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            for name, changed, message in (
                (
                    "count.json",
                    count_changed,
                    "v5 count or Tier-A parity contract changed",
                ),
                ("france.json", france_changed, "v5 France IGEDD release changed"),
            ):
                path = Path(temporary) / name
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

    def test_frozen_v6_bundle_reproduces_exact_accounting_offline(self) -> None:
        definition_raw = V6_DEFINITION.read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "9eb853b78573ad99cffacb605f0a3f052973c99bcaa7c2f1f857865cdcc1bd04",
        )
        manifest = validate_construction_master(
            V6_BUNDLE, definition_path=V6_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V6_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "d73e9560a5ce0a6b9e9853c6bf9ecb0d181e42b768259eff32d8e229a0d8f746",
        )
        self.assertEqual(manifest["row_counts"]["total"], 108964)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 172, "B": 6298, "C": 102494},
        )
        coverage = json.loads(
            (V6_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V6_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-020"
            ]["states"],
            {"completed": 2079, "pending": 4586, "unavailable_no_scene": 71},
        )
        self.assertEqual(
            coverage["upstream_context"]["coverage_audit"][
                "source_scoped_entity_records"
            ],
            15513,
        )
        self.assertEqual(stat.S_IMODE(V6_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V6_BUNDLE.iterdir()
            )
        )

    def test_v6_adds_only_four_metric_free_meta_tier_a_rows(self) -> None:
        v5_tier_a = _tier_a_projections(V5_BUNDLE)
        v6_tier_a = _tier_a_projections(V6_BUNDLE)
        self.assertEqual(len(v6_tier_a) - len(v5_tier_a), 4)
        meta_rows = [
            row
            for row in _jsonl_rows(V6_BUNDLE / "construction-master.jsonl")
            if row["source"]["source_roots"] == ["meta_newsroom"]
        ]
        self.assertEqual(len(meta_rows), 4)
        self.assertEqual(
            {row["entity"]["name"] for row in meta_rows},
            {
                "Meta El Paso Current Development",
                "Meta Lebanon Current Development",
                "Meta Richland Parish Current Development",
                "Meta Tulsa Current Development",
            },
        )
        self.assertEqual(
            {
                row["entity"]["name"]: (
                    row["entity"]["latitude"],
                    row["entity"]["longitude"],
                )
                for row in meta_rows
            },
            {
                "Meta El Paso Current Development": (31.7619, -106.485),
                "Meta Lebanon Current Development": (40.0484, -86.4692),
                "Meta Richland Parish Current Development": (32.43, -91.76),
                "Meta Tulsa Current Development": (36.154, -95.9928),
            },
        )
        evidence_ids = {
            evidence_id
            for row in meta_rows
            for evidence_id in row["source"]["evidence_ids"]
        }
        self.assertEqual(
            evidence_ids, {"624ec417-5585-529d-82ea-ffd8d3978dc4"}
        )
        for row in meta_rows:
            _validate_output_row(row)
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity"]["kind"], "project")
            self.assertEqual(
                row["lifecycle"],
                {
                    "normalized_status": "under_construction",
                    "reported_status": "under_construction",
                    "reported_status_date": "2026-04-28",
                },
            )
            self.assertTrue(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertEqual(len(row["source_evidence"]), 1)
            self.assertEqual(row["source_evidence"][0]["publisher"], "Meta")
            self.assertEqual(
                row["source_evidence"][0]["license"], "all-rights-reserved"
            )
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model_observation"])
            self.assertEqual(
                [item["workload"] for item in row["workload_observations"]],
                ["mixed"],
            )

    def test_v6_keeps_v13_review_source_lineage_and_uses_unknown020_as_catalog_only(
        self,
    ) -> None:
        rows = _rows_of_kind(V6_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(len(rows), 43)
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        unknown_source_rows = [
            row
            for row in rows
            if row["satellite_links"][0]["batch_artifact_id"].startswith(
                "satellite-global-open-v3-unknown-"
            )
        ]
        self.assertEqual(len(unknown_source_rows), 35)
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-020"
                for row in unknown_source_rows
            )
        )
        manifest = json.loads(
            (V6_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        self.assertIn(
            "satellite_review_runs/2026-07-18-global-open-v3-unknown-020/batch-manifest.json",
            lineage_paths,
        )
        self.assertTrue(any("unknown-010/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-013/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-015/jobs/" in path for path in lineage_paths))

    def test_v6_contract_rejects_seed_catalog_or_count_drift(self) -> None:
        document = json.loads(V6_DEFINITION.read_text(encoding="utf-8"))
        changed_documents = []
        count_changed = deepcopy(document)
        count_changed["expected_counts"]["tier_a_rows"] = 171
        changed_documents.append(
            (count_changed, "v6 count or Tier-A projection contract changed")
        )
        seed_changed = deepcopy(document)
        seed_changed["inputs"]["tier_a_releases"][0]["manifest"]["sha256"] = (
            "0" * 64
        )
        changed_documents.append((seed_changed, "v6 open-seed v2 checkpoints changed"))
        catalog_changed = deepcopy(document)
        catalog_changed["inputs"]["satellite_batches"][2]["manifest"][
            "sha256"
        ] = "0" * 64
        changed_documents.append((catalog_changed, "v6 satellite identity or hash changed"))
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changed_documents):
                path = Path(temporary) / f"changed-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

    def test_v7_preserves_v1_through_v6_master_bytes(self) -> None:
        for version, expected in LEGACY_MASTER_BUNDLE_INVENTORY_SHA256.items():
            release_date = "2026-07-19" if version == "v6" else "2026-07-18"
            bundle = (
                PACKAGE_ROOT
                / "construction_master"
                / f"{release_date}-public-open-{version}"
            )
            self.assertEqual(_bundle_inventory_sha256(bundle), expected)

    def test_frozen_v7_bundle_reproduces_exact_accounting_offline(self) -> None:
        definition_raw = V7_DEFINITION.read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "87250eaa13056e206103738b4bf0044091ea04937ec3a358f21624a57f11fc05",
        )
        manifest = validate_construction_master(
            V7_BUNDLE, definition_path=V7_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V7_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "4632b8870c0261043091364a468f14f562abf592f0854092e1d62274c522b796",
        )
        self.assertEqual(manifest["row_counts"]["total"], 108970)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 178, "B": 6298, "C": 102494},
        )
        coverage = json.loads(
            (V7_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V7_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["row_counts"]["by_source_artifact"].get(
                "epoch-official-open-seed-v4"
            ),
            58,
        )
        self.assertNotIn(
            "epoch-official-open-seed-v2",
            coverage["row_counts"]["by_source_artifact"],
        )
        self.assertEqual(stat.S_IMODE(V7_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V7_BUNDLE.iterdir()
            )
        )

    def test_v7_adds_six_metric_free_google_rows_without_duplicating_meta(self) -> None:
        self.assertEqual(
            len(_tier_a_projections(V7_BUNDLE))
            - len(_tier_a_projections(V6_BUNDLE)),
            6,
        )
        official_rows = [
            row
            for row in _jsonl_rows(V7_BUNDLE / "construction-master.jsonl")
            if row["source"]["artifact_id"] == "epoch-official-open-seed-v4"
            and row["source"]["source_roots"]
            in (["google_infrastructure_blog"], ["meta_newsroom"])
        ]
        google_rows = [
            row
            for row in official_rows
            if row["source"]["source_roots"] == ["google_infrastructure_blog"]
        ]
        meta_rows = [
            row
            for row in official_rows
            if row["source"]["source_roots"] == ["meta_newsroom"]
        ]
        self.assertEqual(
            {row["entity"]["name"] for row in google_rows},
            {
                "Google Horndal Data Center Current Development",
                "Google Meitner Energy Center Data Center Current Development",
                "Google Muskogee Data Center Current Development",
                "Google Stillwater Data Center Current Development",
                "Google Visakhapatnam AI Hub Data Center Current Development",
                "Google Wilbarger County Data Center Current Development",
            },
        )
        self.assertEqual(
            {row["entity"]["name"] for row in meta_rows},
            {
                "Meta El Paso Current Development",
                "Meta Lebanon Current Development",
                "Meta Richland Parish Current Development",
                "Meta Tulsa Current Development",
            },
        )
        self.assertEqual(len(google_rows), 6)
        self.assertEqual(len(meta_rows), 4)
        for row in google_rows:
            _validate_output_row(row)
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity"]["kind"], "project")
            self.assertEqual(
                row["lifecycle"]["normalized_status"], "under_construction"
            )
            self.assertTrue(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model_observation"])
            self.assertTrue(
                all(
                    evidence["publisher"] == "Google"
                    and evidence["license"] == "all-rights-reserved"
                    for evidence in row["source_evidence"]
                )
            )

    def test_v7_keeps_review_lineage_and_excludes_new_catalogs(self) -> None:
        rows = _rows_of_kind(V7_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        unknown_rows = [
            row
            for row in rows
            if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
        ]
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-020"
                for row in unknown_rows
            )
        )
        manifest = json.loads(
            (V7_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        self.assertTrue(any("unknown-010/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-013/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-015/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-020/" in path for path in lineage_paths))
        self.assertFalse(any("unknown-021/" in path for path in lineage_paths))
        self.assertFalse(any("unknown-022/" in path for path in lineage_paths))

    def test_v7_contract_rejects_seed_or_count_drift(self) -> None:
        document = json.loads(V7_DEFINITION.read_text(encoding="utf-8"))
        count_changed = deepcopy(document)
        count_changed["expected_counts"]["tier_a_rows"] = 177
        seed_changed = deepcopy(document)
        seed_changed["inputs"]["tier_a_releases"][0]["manifest"][
            "sha256"
        ] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(
                (
                    (
                        count_changed,
                        "v7 count or Tier-A projection contract changed",
                    ),
                    (seed_changed, "v7 open-seed v4 checkpoints changed"),
                )
            ):
                path = Path(temporary) / f"changed-v7-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

    def test_frozen_v8_bundle_reproduces_exact_accounting_offline(self) -> None:
        self.assertEqual(
            _bundle_inventory_sha256(V7_BUNDLE),
            V7_MASTER_BUNDLE_INVENTORY_SHA256,
        )
        definition_raw = V8_DEFINITION.read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "8d960373add4b1f1b29f1ecdb256b17590839eb03b48f17870cb64cc76075846",
        )
        manifest = validate_construction_master(
            V8_BUNDLE, definition_path=V8_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V8_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "5e99ac8e8af244142f4f308797de069e69b3c718a373249746e83bf4066aade8",
        )
        self.assertEqual(manifest["row_counts"]["total"], 108972)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 180, "B": 6298, "C": 102494},
        )
        coverage = json.loads(
            (V8_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 2,
                "expansion": 27,
                "proposed": 21,
                "under_construction": 130,
            },
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V8_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["row_counts"]["by_source_artifact"].get(
                "epoch-official-open-seed-v5"
            ),
            60,
        )
        self.assertNotIn(
            "epoch-official-open-seed-v4",
            coverage["row_counts"]["by_source_artifact"],
        )
        self.assertEqual(stat.S_IMODE(V8_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in V8_BUNDLE.iterdir()
            )
        )

    def test_v8_adds_exactly_two_metric_free_microsoft_projects(self) -> None:
        self.assertEqual(
            len(_tier_a_projections(V8_BUNDLE))
            - len(_tier_a_projections(V7_BUNDLE)),
            2,
        )
        rows = [
            row
            for row in _jsonl_rows(V8_BUNDLE / "construction-master.jsonl")
            if row["source"]["artifact_id"] == "epoch-official-open-seed-v5"
        ]
        microsoft_rows = [
            row
            for row in rows
            if row["source"]["source_roots"] == ["microsoft_official_news"]
        ]
        self.assertEqual(len(rows), 60)
        self.assertEqual(len(microsoft_rows), 2)
        self.assertEqual(
            {row["entity"]["name"] for row in microsoft_rows},
            {
                "Microsoft Mount Pleasant Second Datacenter Facility",
                "Microsoft Pecos Datacenter Campus Development",
            },
        )
        self.assertTrue(all(row["entity"]["kind"] == "project" for row in microsoft_rows))
        by_name = {row["entity"]["name"]: row for row in microsoft_rows}
        self.assertEqual(
            by_name["Microsoft Mount Pleasant Second Datacenter Facility"][
                "lifecycle"
            ]["normalized_status"],
            "under_construction",
        )
        self.assertEqual(
            by_name["Microsoft Pecos Datacenter Campus Development"]["lifecycle"][
                "normalized_status"
            ],
            "announced",
        )
        self.assertEqual(
            by_name["Microsoft Mount Pleasant Second Datacenter Facility"][
                "workload_observations"
            ],
            [],
        )
        self.assertEqual(
            [
                item["workload"]
                for item in by_name[
                    "Microsoft Pecos Datacenter Campus Development"
                ]["workload_observations"]
            ],
            ["mixed"],
        )
        for row in microsoft_rows:
            _validate_output_row(row)
            self.assertEqual(row["tier"], "A")
            self.assertTrue(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model_observation"])
            self.assertTrue(
                all(
                    evidence["publisher"] == "Microsoft"
                    and evidence["license"] == "all-rights-reserved"
                    for evidence in row["source_evidence"]
                )
            )

        retained_names = {
            "Google Horndal Data Center Current Development",
            "Google Meitner Energy Center Data Center Current Development",
            "Google Muskogee Data Center Current Development",
            "Google Stillwater Data Center Current Development",
            "Google Visakhapatnam AI Hub Data Center Current Development",
            "Google Wilbarger County Data Center Current Development",
            "Meta El Paso Current Development",
            "Meta Lebanon Current Development",
            "Meta Richland Parish Current Development",
            "Meta Tulsa Current Development",
        }
        counts = Counter(row["entity"]["name"] for row in rows)
        self.assertTrue(all(counts[name] == 1 for name in retained_names))

    def test_v8_updates_only_catalog_and_context_not_review_lineage(self) -> None:
        rows = _rows_of_kind(V8_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        unknown_rows = [
            row
            for row in rows
            if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
        ]
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-022"
                for row in unknown_rows
            )
        )
        manifest = json.loads(
            (V8_BUNDLE / "manifest.json").read_text(encoding="utf-8")
        )
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        self.assertTrue(any("unknown-010/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-013/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-015/jobs/" in path for path in lineage_paths))
        self.assertTrue(any("unknown-022/" in path for path in lineage_paths))
        self.assertFalse(any("unknown-020/" in path for path in lineage_paths))
        self.assertFalse(any("unknown-021/" in path for path in lineage_paths))
        coverage = json.loads(
            (V8_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            coverage["upstream_context"]["coverage_audit"][
                "source_scoped_entity_records"
            ],
            15529,
        )
        self.assertEqual(
            coverage["upstream_context"]["federation"]["source_scoped_rows"],
            15529,
        )
        self.assertEqual(
            coverage["row_counts"]["total"],
            108972,
            "contextual federation arithmetic must not become master rows",
        )

    def test_v8_contract_rejects_seed_catalog_context_or_count_drift(self) -> None:
        document = json.loads(V8_DEFINITION.read_text(encoding="utf-8"))
        count_changed = deepcopy(document)
        count_changed["expected_counts"]["tier_a_rows"] = 179
        seed_changed = deepcopy(document)
        seed_changed["inputs"]["tier_a_releases"][0]["manifest"][
            "sha256"
        ] = "0" * 64
        catalog_changed = deepcopy(document)
        catalog_changed["inputs"]["satellite_batches"][2]["manifest"][
            "sha256"
        ] = "0" * 64
        context_changed = deepcopy(document)
        context_changed["inputs"]["coverage_context"]["federation_manifest"][
            "sha256"
        ] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(
                (
                    (
                        count_changed,
                        "v8 count or Tier-A projection contract changed",
                    ),
                    (seed_changed, "v8 open-seed v5 checkpoints changed"),
                    (catalog_changed, "v8 satellite identity or hash changed"),
                    (
                        context_changed,
                        "v8 federation or coverage-audit context changed",
                    ),
                )
            ):
                path = Path(temporary) / f"changed-v8-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

    def test_frozen_v9_bundle_reproduces_exact_accounting_offline(self) -> None:
        self.assertEqual(
            _bundle_inventory_sha256(V8_BUNDLE),
            V8_MASTER_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(V9_DEFINITION.read_bytes()).hexdigest(),
            "c9096669f02d7d39ee3768dcaf1c3670c6d22b3c89278ede392abdcedf617848",
        )
        manifest = validate_construction_master(
            V9_BUNDLE, definition_path=V9_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V9_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "b5e0dbe86ed5df4aa4d5b3ddcd42c5f4b3ae8a0e564ae55864e9236e2dd2d6ba",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V9_BUNDLE),
            V9_MASTER_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["row_counts"]["total"], 108985)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 193, "B": 6298, "C": 102494},
        )
        coverage = json.loads((V9_BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 2,
                "expansion": 27,
                "proposed": 21,
                "under_construction": 143,
            },
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V9_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["evidence_observations"],
            {
                "annual_energy": 73,
                "operating_model": 1,
                "pue": 2,
                "source_evidence_records": 115263,
                "typed_capacity_excluding_annual_energy_and_pue": 198,
                "untyped_capacity_statements": 23,
                "workload": 97,
            },
        )
        self.assertEqual(stat.S_IMODE(V9_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in V9_BUNDLE.iterdir()
            )
        )
        readme = (V9_BUNDLE / "README.md").read_text()
        attribution = (V9_BUNDLE / "ATTRIBUTION.txt").read_text()
        self.assertIn("576 MW", readme)
        self.assertIn("is not promoted to data-centre load", readme)
        for publisher in (
            "Indiana IDEM",
            "Applied Digital",
            "Sunshine Coast Council",
            "Government of Aragón",
            "North Carolina DEQ",
            "Richmond County",
        ):
            self.assertIn(publisher, attribution)

    def test_v9_adds_exactly_thirteen_projects_with_bounded_capacity_semantics(self) -> None:
        previous = _release_rows(V8_BUNDLE, "epoch-official-open-seed-v5")
        current = _release_rows(V9_BUNDLE, "epoch-official-open-seed-v9")
        self.assertEqual(set(current) - set(previous), V9_ADDITION_IDS)
        self.assertEqual(set(previous) - set(current), set())
        additions = [current[record_id] for record_id in sorted(V9_ADDITION_IDS)]
        expected_identity = {
            "1d95d387-1806-5dda-a619-a50e84852137": (
                "Amazon SBN100 New Carlisle Physical Build",
                "2025-07-14",
                0.97,
            ),
            "27f804d6-f887-51a3-9564-4e738793d2f8": (
                "Polaris Forge 2 Building 2",
                "2026-04-08",
                0.99,
            ),
            "296ce9ca-8904-5976-9226-aa9ee6b9ae70": (
                "NEXTDC SC2 Current Data Center Build",
                "2026-03-26",
                0.99,
            ),
            "55f4eb88-750d-5aa5-b4cb-bd5b8e746fe6": (
                "AWS Walqa Current Data Center Build",
                "2026-06-25",
                0.98,
            ),
            "6564e429-77a5-5548-a5b0-ec6f2a402d47": (
                "Polaris Forge 1 Third 150 MW Facility",
                "2026-04-08",
                0.98,
            ),
            "6e05e286-dbad-5550-900d-ed0c2294e5a2": (
                "Polaris Forge 2 Building 1",
                "2026-04-08",
                0.99,
            ),
            "7206a400-093d-5c92-b1c5-c4243807de29": (
                "KAO Data KLON-03 Data Centre Building",
                "2026-05-26",
                0.99,
            ),
            "7d936c4e-29f2-592f-984b-61f5d6367fc8": (
                "The Barn Stargate Current Data Center Build",
                "2026-06-01",
                0.99,
            ),
            "9c96ba2a-1e05-53b4-a7bb-86057ddcba1f": (
                "Polaris Forge 1 Second 150 MW Facility",
                "2026-04-08",
                0.99,
            ),
            "b7744ad5-aa48-5977-a70e-3d6a588f468d": (
                "Delta Forge 1 Current 300 MW Critical-IT Build",
                "2026-04-08",
                0.99,
            ),
            "bdfd522f-2d7e-5d1f-8e00-3c43b462ed27": (
                "Amazon Falls Township Active Campus Buildout",
                "2026-07-19",
                0.98,
            ),
            "c6c50c6d-b3b3-5e33-bed0-4da5b6372a9b": (
                "Amazon Energy Way Tech Campus Physical Build",
                "2025-10-30",
                0.98,
            ),
            "c73ac912-e44d-5477-84f5-c5beb4813518": (
                "Amazon Salem Township Active Campus Buildout",
                "2026-07-19",
                0.98,
            ),
        }
        for row in additions:
            _validate_output_row(row)
            record_id = row["source"]["record_id"]
            self.assertEqual(
                (
                    row["entity"]["name"],
                    row["lifecycle"]["reported_status_date"],
                    row["construction"]["confidence"],
                ),
                expected_identity[record_id],
            )
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity"]["kind"], "project")
            self.assertEqual(
                row["lifecycle"]["normalized_status"], "under_construction"
            )
            self.assertEqual(
                row["construction"]["method"],
                "authoritative_construction_start",
            )
            self.assertTrue(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model_observation"])

        capacity = [
            observation
            for row in additions
            for observation in row["capacity_observations"]
        ]
        self.assertEqual(len(capacity), 5)
        self.assertTrue(
            all(
                observation["metric"] == "critical_it_mw"
                and observation["method"] == "reported"
                and observation["confidence"] == 0.99
                and observation["target_date"] is None
                and observation["low"]
                == observation["value"]
                == observation["high"]
                for observation in capacity
            )
        )
        by_stage = Counter()
        for observation in capacity:
            by_stage[observation["stage"]] += observation["value"]
        self.assertEqual(by_stage, Counter({"contracted": 600.0, "planned": 300.0}))
        self.assertNotIn(576.0, [observation["value"] for observation in capacity])
        workloads = [
            observation["workload"]
            for row in additions
            for observation in row["workload_observations"]
        ]
        self.assertEqual(
            Counter(workloads),
            Counter({"mixed": 8, "ai_specialized_unspecified": 2}),
        )

    def test_v9_shared_seed_semantics_change_only_for_coreweave_operating_model(self) -> None:
        previous = _release_rows(V8_BUNDLE, "epoch-official-open-seed-v5")
        current = _release_rows(V9_BUNDLE, "epoch-official-open-seed-v9")
        self.assertEqual(set(previous), set(current) - V9_ADDITION_IDS)
        release_fields = {
            "artifact_id",
            "artifact_path",
            "artifact_sha256",
            "manifest_sha256",
            "release_id",
        }
        for record_id in sorted(set(previous) - {"b99b03ae-8105-517c-a9ac-7c6d4d4fecbd"}):
            before = deepcopy(previous[record_id])
            after = deepcopy(current[record_id])
            before.pop("row_id")
            after.pop("row_id")
            for field in release_fields:
                before["source"].pop(field)
                after["source"].pop(field)
            self.assertEqual(after, before)

        coreweave_id = "b99b03ae-8105-517c-a9ac-7c6d4d4fecbd"
        before = previous[coreweave_id]
        after = current[coreweave_id]
        self.assertIsNone(before["operating_model_observation"])
        self.assertEqual(
            after["operating_model_observation"],
            {
                "confidence": 0.95,
                "evidence_id": "ba4b5d07-7b23-5968-b705-3023ba2ad8ab",
                "value": "wholesale_colocation",
            },
        )
        for field in (
            "annual_energy_observations",
            "capacity_observations",
            "construction",
            "entity",
            "lifecycle",
            "pue_observations",
            "untyped_capacity_statements",
            "workload_observations",
        ):
            self.assertEqual(after[field], before[field])

    def test_v9_keeps_review_lineage_and_uses_unknown025_catalog_context(self) -> None:
        rows = _rows_of_kind(V9_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        unknown_rows = [
            row
            for row in rows
            if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
        ]
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-025"
                for row in unknown_rows
            )
        )
        manifest = json.loads((V9_BUNDLE / "manifest.json").read_text())
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        for marker in ("unknown-010/jobs/", "unknown-013/jobs/", "unknown-015/jobs/", "unknown-025/"):
            self.assertTrue(any(marker in path for path in lineage_paths))
        self.assertFalse(any("unknown-026/" in path for path in lineage_paths))
        coverage = json.loads((V9_BUNDLE / "coverage.json").read_text())
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-025"
            ]["states"],
            {"completed": 3216, "pending": 3336, "unavailable_no_scene": 184},
        )
        self.assertEqual(
            coverage["upstream_context"]["coverage_audit"][
                "source_scoped_entity_records"
            ],
            15552,
        )
        self.assertEqual(
            coverage["upstream_context"]["federation"]["source_scoped_rows"],
            15552,
        )

    def test_v9_contract_and_open_seed_source_allowlist_fail_closed(self) -> None:
        document = json.loads(V9_DEFINITION.read_text())
        changes = []
        for field_path, message in (
            (("expected_counts", "tier_a_rows"), "v9 count or Tier-A projection contract changed"),
            (("inputs", "tier_a_releases", 0, "manifest", "sha256"), "v9 open-seed v9 checkpoints changed"),
            (("inputs", "satellite_batches", 2, "manifest", "sha256"), "v9 satellite identity or hash changed"),
            (("inputs", "coverage_context", "federation_manifest", "sha256"), "v9 federation or coverage-audit context changed"),
        ):
            changed = deepcopy(document)
            target = changed
            for key in field_path[:-1]:
                target = target[key]
            target[field_path[-1]] = 0 if field_path[-1] == "tier_a_rows" else "0" * 64
            changes.append((changed, message))
        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T15:10:01Z"
        changes.append((changed, "v9 generation timestamp changed"))
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v9-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        with (
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v9" / "construction_pipeline.csv").open(
                newline="", encoding="utf-8"
            ) as source,
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v9" / "evidence.csv").open(
                newline="", encoding="utf-8"
            ) as evidence_source,
        ):
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v9_open_seed_source_allowlist(rows, evidence)
        changed_evidence = deepcopy(evidence)
        changed_evidence[next(iter(changed_evidence))]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v9 open-seed source allowlist changed"
        ):
            _validate_v9_open_seed_source_allowlist(rows, changed_evidence)

    def test_frozen_v10_bundle_reproduces_exact_accounting_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(V10_DEFINITION.read_bytes()).hexdigest(),
            "aa252132da08ee5f224097dfcbf50dbdbe9e7e5a1416b58e85af304030a3fa34",
        )
        manifest = validate_construction_master(
            V10_BUNDLE, definition_path=V10_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V10_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "739f340d9413c9a54b5f38174cc5808620326cd1cf6aa59a85738027ff5c2bbb",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V10_BUNDLE),
            V10_MASTER_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["row_counts"]["total"], 109017)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 225, "B": 6298, "C": 102494},
        )
        coverage = json.loads((V10_BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 2,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 3,
                "permitted": 2,
                "proposed": 21,
                "shell": 2,
                "site_preparation": 5,
                "under_construction": 159,
            },
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V10_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["evidence_observations"],
            {
                "annual_energy": 73,
                "operating_model": 1,
                "pue": 2,
                "source_evidence_records": 115298,
                "typed_capacity_excluding_annual_energy_and_pue": 203,
                "untyped_capacity_statements": 23,
                "workload": 97,
            },
        )
        self.assertEqual(stat.S_IMODE(V10_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in V10_BUNDLE.iterdir()
            )
        )
        readme = (V10_BUNDLE / "README.md").read_text()
        attribution = (V10_BUNDLE / "ATTRIBUTION.txt").read_text()
        for marker in ("Five", "7.3 MW", "not current operating load", "Unknown030"):
            self.assertIn(marker, readme)
        for publisher in (
            "City of Espoo",
            "Municipality of Vihti",
            "NTT DATA, Inc.",
            "QTS Data Centers",
            "STACK Infrastructure",
            "Digital Realty",
            "CyrusOne",
            "Colt Data Centre Services",
            "Gilbane Building Company",
        ):
            self.assertIn(publisher, attribution)

    def test_v10_adds_exact_source_rows_and_preserves_shared_semantics(self) -> None:
        previous = _release_rows(V9_BUNDLE, "epoch-official-open-seed-v9")
        current = _release_rows(V10_BUNDLE, "epoch-official-open-seed-v13")
        self.assertEqual(set(current) - set(previous), V10_ADDITION_IDS)
        self.assertEqual(set(previous) - set(current), set())
        release_fields = {
            "artifact_id",
            "artifact_path",
            "artifact_sha256",
            "manifest_sha256",
            "release_id",
        }
        for record_id in sorted(previous):
            before = deepcopy(previous[record_id])
            after = deepcopy(current[record_id])
            before.pop("row_id")
            after.pop("row_id")
            for field in release_fields:
                before["source"].pop(field)
                after["source"].pop(field)
            self.assertEqual(after, before)

        additions = [current[record_id] for record_id in sorted(V10_ADDITION_IDS)]
        self.assertEqual(
            Counter(row["entity"]["kind"] for row in additions),
            Counter({"project": 31, "campus": 1}),
        )
        self.assertEqual(
            Counter(row["lifecycle"]["normalized_status"] for row in additions),
            Counter(
                {
                    "under_construction": 16,
                    "site_preparation": 5,
                    "mep_electrical": 3,
                    "shell": 2,
                    "foundations": 2,
                    "civil_works": 2,
                    "permitted": 2,
                }
            ),
        )
        for row in additions:
            _validate_output_row(row)
            self.assertEqual(row["tier"], "A")
            self.assertTrue(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertEqual(row["workload_observations"], [])
            self.assertIsNone(row["operating_model_observation"])

        capacity = [
            (row["entity"]["name"], observation)
            for row in additions
            for observation in row["capacity_observations"]
        ]
        self.assertEqual(
            Counter((name, observation["value"]) for name, observation in capacity),
            Counter(
                {
                    ("Colt London 4 Current Facility Build", 31.0): 1,
                    ("CyrusOne MIL1 Current Facility Build", 27.0): 1,
                    ("Digital Realty Dugny Digital Hub", 176.0): 1,
                    ("Digital Realty FRA20 Current Facility Build", 16.0): 1,
                    ("NTT Frankfurt 1 7.3MW Expansion", 7.3): 1,
                }
            ),
        )
        self.assertTrue(
            all(
                observation["metric"] == "critical_it_mw"
                and observation["stage"] == "planned"
                and observation["method"] == "reported"
                and observation["low"]
                == observation["value"]
                == observation["high"]
                for _name, observation in capacity
            )
        )

    def test_v10_keeps_review_lineage_and_uses_unknown030_catalog_context(self) -> None:
        rows = _rows_of_kind(V10_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        unknown_rows = [
            row
            for row in rows
            if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
        ]
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-030"
                for row in unknown_rows
            )
        )
        manifest = json.loads((V10_BUNDLE / "manifest.json").read_text())
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        for marker in (
            "unknown-010/jobs/",
            "unknown-013/jobs/",
            "unknown-015/jobs/",
            "unknown-030/",
        ):
            self.assertTrue(any(marker in path for path in lineage_paths))
        for batch_number in range(26, 30):
            self.assertFalse(
                any(f"unknown-{batch_number:03d}/" in path for path in lineage_paths)
            )
        coverage = json.loads((V10_BUNDLE / "coverage.json").read_text())
        self.assertEqual(
            coverage["satellite"]["batch_accounting"][
                "satellite-global-open-v3-unknown-030"
            ]["states"],
            {"completed": 4350, "pending": 2086, "unavailable_no_scene": 300},
        )
        self.assertEqual(
            coverage["upstream_context"]["coverage_audit"],
            {
                "confirmed_duplicate_relationships": None,
                "coverage_groups": 320,
                "non_review_source_scoped_entity_records": 9489,
                "open_gaps": 1819,
                "review_only_source_scoped_entity_records": 6130,
                "source_scoped_entity_records": 15619,
                "unique_physical_sites": None,
            },
        )

    def test_v10_contract_and_open_seed_source_allowlist_fail_closed(self) -> None:
        document = json.loads(V10_DEFINITION.read_text())
        changes = []
        for field_path, message in (
            (("expected_counts", "tier_a_rows"), "v10 count or Tier-A projection contract changed"),
            (("inputs", "tier_a_releases", 0, "manifest", "sha256"), "v10 open-seed v13 checkpoints changed"),
            (("inputs", "satellite_batches", 2, "manifest", "sha256"), "v10 satellite identity or hash changed"),
            (("inputs", "coverage_context", "federation_manifest", "sha256"), "v10 federation or coverage-audit context changed"),
        ):
            changed = deepcopy(document)
            target = changed
            for key in field_path[:-1]:
                target = target[key]
            target[field_path[-1]] = 0 if field_path[-1] == "tier_a_rows" else "0" * 64
            changes.append((changed, message))
        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T18:30:01Z"
        changes.append((changed, "v10 generation timestamp changed"))
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v10-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        with (
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v13" / "construction_pipeline.csv").open(
                newline="", encoding="utf-8"
            ) as source,
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v13" / "evidence.csv").open(
                newline="", encoding="utf-8"
            ) as evidence_source,
        ):
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v10_open_seed_source_allowlist(rows, evidence)
        changed_evidence = deepcopy(evidence)
        selected_id = rows[0]["status_evidence_id"]
        changed_evidence[selected_id]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v10 open-seed source allowlist changed"
        ):
            _validate_v10_open_seed_source_allowlist(rows, changed_evidence)

    def test_frozen_v11_bundle_reproduces_exact_accounting_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(V11_DEFINITION.read_bytes()).hexdigest(),
            "1689dd992ae482dbf464c42300fb0b32289c2d795b6edce2d4b1ac8f6a7fb65c",
        )
        manifest = validate_construction_master(
            V11_BUNDLE, definition_path=V11_DEFINITION
        )
        self.assertEqual(
            hashlib.sha256((V11_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            "dd0648d98e27d2f11b1ce117c92e45647d00b9226083f54025c27e0979e5f951",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V11_BUNDLE),
            V11_MASTER_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["row_counts"]["total"], 109063)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 271, "B": 6298, "C": 102494},
        )
        coverage = json.loads((V11_BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108792)
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 3,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 15,
                "permitted": 2,
                "proposed": 21,
                "shell": 5,
                "site_preparation": 8,
                "under_construction": 186,
            },
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            V11_TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["evidence_observations"],
            {
                "annual_energy": 73,
                "operating_model": 2,
                "pue": 2,
                "source_evidence_records": 115351,
                "typed_capacity_excluding_annual_energy_and_pue": 228,
                "untyped_capacity_statements": 23,
                "workload": 98,
            },
        )
        self.assertEqual(stat.S_IMODE(V11_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in V11_BUNDLE.iterdir()
            )
        )
        readme = (V11_BUNDLE / "README.md").read_text()
        attribution = (V11_BUNDLE / "ATTRIBUTION.txt").read_text()
        for marker in ("46", "Unknown030", "federation-v9", "coverage-audit-v10"):
            self.assertIn(marker, readme)
        for marker in (
            "Khazna Data Centers",
            "Wisconsin Department of Natural Resources",
            "Public-government-record",
            "Yondr Group",
        ):
            self.assertIn(marker, attribution)

    def test_v11_adds_exact_v20_rows_and_preserves_shared_semantics(self) -> None:
        previous = _release_rows(V10_BUNDLE, "epoch-official-open-seed-v13")
        current = _release_rows(V11_BUNDLE, "epoch-official-open-seed-v20")
        self.assertEqual(set(current) - set(previous), V11_ADDITION_IDS)
        self.assertEqual(set(previous) - set(current), set())
        release_fields = {
            "artifact_id",
            "artifact_path",
            "artifact_sha256",
            "manifest_sha256",
            "release_id",
        }
        for record_id in sorted(previous):
            before = deepcopy(previous[record_id])
            after = deepcopy(current[record_id])
            before.pop("row_id")
            after.pop("row_id")
            for field in release_fields:
                before["source"].pop(field)
                after["source"].pop(field)
            self.assertEqual(after, before)

        additions = [current[record_id] for record_id in sorted(V11_ADDITION_IDS)]
        self.assertEqual(
            Counter(row["entity"]["kind"] for row in additions),
            Counter({"project": 46}),
        )
        self.assertEqual(
            Counter(row["lifecycle"]["normalized_status"] for row in additions),
            Counter(
                {
                    "under_construction": 27,
                    "mep_electrical": 12,
                    "shell": 3,
                    "site_preparation": 3,
                    "announced": 1,
                }
            ),
        )
        self.assertEqual(
            Counter(row["source"]["source_license"] for row in additions),
            Counter({"all-rights-reserved": 45, "public-government-record": 1}),
        )
        self.assertEqual(sum(len(row["source_evidence"]) for row in additions), 53)
        self.assertTrue(
            all(
                row["entity"]["latitude"] is None
                and row["entity"]["longitude"] is None
                and row["tier"] == "A"
                and row["construction"]["source_supported"]
                and not row["construction"]["verified"]
                and row["annual_energy_observations"] == []
                and row["pue_observations"] == []
                and row["untyped_capacity_statements"] == []
                for row in additions
            )
        )
        capacities = [
            observation
            for row in additions
            for observation in row["capacity_observations"]
        ]
        self.assertEqual(
            Counter((item["metric"], item["stage"]) for item in capacities),
            Counter({("critical_it_mw", "planned"): 24, ("grid_connection_mw", "contracted"): 1}),
        )
        self.assertEqual(
            Counter(
                item["workload"]
                for row in additions
                for item in row["workload_observations"]
            ),
            Counter({"ai_specialized_unspecified": 1}),
        )
        self.assertEqual(
            Counter(
                row["operating_model_observation"]["value"]
                for row in additions
                if row["operating_model_observation"] is not None
            ),
            Counter({"retail_colocation": 1}),
        )

    def test_v11_keeps_unknown030_and_frozen_review_lineage(self) -> None:
        rows = _rows_of_kind(V11_BUNDLE, "sentinel_analyst_change_review")
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        self.assertTrue(
            all(
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-030"
                for row in rows
                if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
            )
        )
        manifest = json.loads((V11_BUNDLE / "manifest.json").read_text())
        lineage_paths = {item["path"] for item in manifest["input_checkpoints"]}
        for marker in (
            "unknown-010/jobs/",
            "unknown-013/jobs/",
            "unknown-015/jobs/",
            "unknown-030/",
        ):
            self.assertTrue(any(marker in path for path in lineage_paths))
        self.assertTrue(
            any("public-open-coverage-v10/" in path for path in lineage_paths)
        )
        self.assertTrue(
            any("public-open-v9/manifest.json" in path for path in lineage_paths)
        )

    def test_v11_contract_and_cumulative_source_allowlist_fail_closed(self) -> None:
        document = json.loads(V11_DEFINITION.read_text())
        changes = []
        for field_path, message in (
            (("expected_counts", "tier_a_rows"), "v11 count or Tier-A projection contract changed"),
            (("inputs", "tier_a_releases", 0, "manifest", "sha256"), "v11 open-seed v20 checkpoints changed"),
            (("inputs", "coverage_context", "audit_manifest", "sha256"), "v11 federation or coverage-audit context changed"),
        ):
            changed = deepcopy(document)
            target = changed
            for key in field_path[:-1]:
                target = target[key]
            target[field_path[-1]] = 0 if field_path[-1] == "tier_a_rows" else "0" * 64
            changes.append((changed, message))
        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T21:00:01Z"
        changes.append((changed, "v11 generation timestamp changed"))
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v11-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        with (
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v20" / "construction_pipeline.csv").open(
                newline="", encoding="utf-8"
            ) as source,
            (PACKAGE_ROOT / "releases" / "2026-07-19-open-seed-v20" / "evidence.csv").open(
                newline="", encoding="utf-8"
            ) as evidence_source,
        ):
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v11_open_seed_source_allowlist(rows, evidence)

        changed_evidence = deepcopy(evidence)
        selected_id = rows[0]["status_evidence_id"]
        changed_evidence[selected_id]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v11 open-seed source allowlist changed"
        ):
            _validate_v11_open_seed_source_allowlist(rows, changed_evidence)

        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["source_family"] = "unexpected_source_root"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v11 open-seed source allowlist changed"
        ):
            _validate_v11_open_seed_source_allowlist(rows, changed_evidence)

        changed_rows = deepcopy(rows)
        government_row = next(
            row
            for row in changed_rows
            if row["source_license"] == "public-government-record"
        )
        government_row["source_license"] = "all-rights-reserved"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v11 open-seed source allowlist changed"
        ):
            _validate_v11_open_seed_source_allowlist(changed_rows, evidence)

    def test_england_rows_preserve_official_lineage_without_promotion(self) -> None:
        rows = [
            row
            for row in _jsonl_rows(V3_BUNDLE / "construction-master.jsonl")
            if row["observation_kind"]
            == "official_england_planning_application_review_lead"
        ]
        self.assertEqual(len(rows), 3)
        source_entities = set()
        point_presence = []
        for row in rows:
            _validate_output_row(row)
            metadata = row["source_evidence"][0]["planning_metadata"]
            source_entities.add(str(metadata["source_attributes"]["entity"]))
            point_presence.append(metadata["source_point"] is not None)
            self.assertEqual(
                metadata["raw_description"],
                metadata["source_attributes"]["description"],
            )
            self.assertEqual(row["tier"], "B")
            self.assertTrue(row["review_only"])
            self.assertFalse(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertIsNone(row["identity"]["confidence"])
            self.assertIsNone(row["source"]["source_entity_id"])
            self.assertEqual(
                row["source"]["source_license"],
                "Open Government Licence v3.0",
            )
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["workload_observations"], [])
        self.assertEqual(
            source_entities, {"10000009092", "10000088724", "10000090380"}
        )
        self.assertEqual(sorted(point_presence), [False, True, True])

        coverage = json.loads(
            (V3_BUNDLE / "coverage.json").read_text(encoding="utf-8")
        )
        england = coverage["review_leads"]["england_planning"]
        self.assertEqual(england["observation_rows"], 3)
        self.assertEqual(
            england["context_assessment"]["context_only_entity_ids_excluded"],
            ["10000057188"],
        )
        self.assertEqual(
            england["context_assessment"][
                "context_only_exact_phrase_rows_excluded"
            ],
            1,
        )
        self.assertEqual(
            england["context_assessment"]["optional_server_room_rows_excluded"],
            3,
        )
        self.assertIsNone(england["unique_physical_site_count"])

    def test_england_rows_fail_closed_against_lifecycle_or_metric_promotion(self) -> None:
        lifecycle_promoted = deepcopy(_first_england_row())
        lifecycle_promoted["lifecycle"]["normalized_status"] = "under_construction"
        with self.assertRaisesRegex(
            ConstructionMasterError, "England planning row was promoted"
        ):
            _validate_output_row(lifecycle_promoted)

        metric_promoted = deepcopy(_first_england_row())
        metric_promoted["capacity_observations"].append(
            {"metric": "gross_facility_mw", "unit": "MW", "value": 10}
        )
        with self.assertRaisesRegex(
            ConstructionMasterError, "England planning row was promoted"
        ):
            _validate_output_row(metric_promoted)

    def test_v2_is_frozen_and_tier_a_arithmetic_is_byte_stable_from_v1(self) -> None:
        self.assertEqual(stat.S_IMODE(V2_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in V2_BUNDLE.iterdir()
            )
        )
        v1 = _tier_a_projections(BUNDLE)
        v2 = _tier_a_projections(V2_BUNDLE)
        self.assertEqual(len(v1), 168)
        self.assertEqual(v2, v1)
        digest = hashlib.sha256()
        for projection in v2:
            digest.update(_canonical_line(projection))
        self.assertEqual(digest.hexdigest(), TIER_A_PROJECTION_SHA256)
        self.assertTrue(
            all(row["construction"]["verified"] is False for row in v2)
        )

    def test_ireland_rows_are_review_only_planning_observations(self) -> None:
        rows = [
            row
            for row in _jsonl_rows(V2_BUNDLE / "construction-master.jsonl")
            if row["observation_kind"]
            == "official_planning_application_review_lead"
        ]
        self.assertEqual(len(rows), 114)
        for row in rows:
            _validate_output_row(row)
            self.assertEqual(row["tier"], "B")
            self.assertTrue(row["review_only"])
            self.assertIsInstance(row["entity"]["latitude"], float)
            self.assertIsInstance(row["entity"]["longitude"], float)
            self.assertFalse(row["construction"]["source_supported"])
            self.assertFalse(row["construction"]["verified"])
            self.assertFalse(
                row["disposition"]["construction_arithmetic_included"]
            )
            self.assertFalse(row["disposition"]["unique_site_counted"])

    def test_ireland_rows_fail_closed_against_lifecycle_or_metric_promotion(self) -> None:
        lifecycle_promoted = deepcopy(_first_ireland_row())
        lifecycle_promoted["lifecycle"]["normalized_status"] = "under_construction"
        lifecycle_promoted["lifecycle"]["reported_status"] = "GRANT PERMISSION"
        with self.assertRaisesRegex(ConstructionMasterError, "Ireland planning row was promoted"):
            _validate_output_row(lifecycle_promoted)

        metric_promoted = deepcopy(_first_ireland_row())
        metric_promoted["capacity_observations"].append(
            {
                "metric": "gross_facility_mw",
                "unit": "MW",
                "value": 10,
            }
        )
        with self.assertRaisesRegex(ConstructionMasterError, "Ireland planning row was promoted"):
            _validate_output_row(metric_promoted)

    def test_duplicate_analyst_review_inputs_fail_closed(self) -> None:
        definition, _, _, resolved = _definition(V2_DEFINITION)
        reviews = deepcopy(definition["inputs"]["analyst_reviews"])
        reviews[1]["report"]["sha256"] = reviews[0]["report"]["sha256"]
        with self.assertRaisesRegex(
            ConstructionMasterError, "analyst reviews are not deduplicated"
        ):
            _review_decisions(reviews, resolved)

    def test_existing_destination_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            with self.assertRaisesRegex(ConstructionMasterError, "refusing existing output"):
                write_construction_master(DEFINITION, output)


if __name__ == "__main__":
    unittest.main()
