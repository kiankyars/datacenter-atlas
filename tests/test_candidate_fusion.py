from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas.candidate_fusion import (
    _derive,
    _feature_collection,
    _source_root,
    validate_candidate_fusion,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _primary(candidate_id: str, *, west: float, south: float, east: float, north: float):
    return {
        "type": "Feature",
        "id": candidate_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
        "properties": {
            "review_only": True,
            "data_centre_identity_inferred": False,
            "source_url": f"https://www.openstreetmap.org/{candidate_id}",
            "review_score": 7,
            "footprint_square_metres": 25_000,
            "source_tag_families": ["construction"],
        },
    }


def _atlas(
    entity_id: str,
    *,
    longitude: float,
    latitude: float,
    source_family: str,
    stable_key: str,
):
    return {
        "type": "Feature",
        "id": entity_id,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": {
            "entity_id": entity_id,
            "entity_kind": "facility",
            "name": entity_id,
            "latitude": latitude,
            "longitude": longitude,
            "source_family": source_family,
            "source_url": "https://example.test/evidence",
            "stable_key": stable_key,
            "status": "under_construction",
            "status_as_of": "2026-07-01",
            "status_evidence_id": f"evidence-{entity_id}",
        },
    }


class CandidateFusionTests(unittest.TestCase):
    def test_v13_reproduces_with_forty_three_no_claim_reviews(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v13.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v13"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        v12_definition = json.loads(
            (
                PACKAGE_ROOT
                / "sources"
                / "candidate-fusion-2026-07-18-osm-planet-v12.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(definition["parameters"], v12_definition["parameters"])
        self.assertEqual(
            {
                key: value
                for key, value in definition["inputs"].items()
                if key not in {"satellite_analyst_reviews", "satellite_batch_bundles"}
            },
            {
                key: value
                for key, value in v12_definition["inputs"].items()
                if key not in {"satellite_analyst_reviews", "satellite_batch_bundles"}
            },
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][-1],
            {
                "manifest_sha256": "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8",
                "path": "../satellite_review_runs/2026-07-18-global-open-v3-unknown-015",
            },
        )
        specs = definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(specs[:37], v12_definition["inputs"]["satellite_analyst_reviews"])
        self.assertEqual(len(specs), 43)
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 43)
        expected_new = {
            "satq-2e513dfc6e0d021dd25c96c5": (
                "reject_automated_mask_for_site_promotion",
                "a0cee034af32159ae0d37825680c8f12a27e48a18471e1c6df31498f18b7065b",
                "e43f20d37fc0a992cf90939037756afdcf69253a48f4814acbd31b27cedb382f",
            ),
            "satq-53d7004bde921da52b359322": (
                "retain_site_aligned_change_candidate_for_manual_followup",
                "0d7b12322d05e610d449835a0934c24c1663c438fa891dadd436e0437bfc535d",
                "75b4be86cb68f296d99bfa4c8990bca234c8fda1fb7d16c9f2bee5ea7af1f0e5",
            ),
            "satq-555e1bb60a94146a6e33125e": (
                "retain_site_aligned_change_candidate_for_manual_followup",
                "6dc84740d3fe05b174452a4d98b39a4117178fd1a664606f7ea755c651358f64",
                "4793e497a97cfc35f6563e86850926f9b744d73a9b6fa72bfd23d0e508ccb074",
            ),
            "satq-73a81fb1881277f022fa7b5b": (
                "reject_automated_mask_for_site_promotion",
                "0036dde008d114f2b9bff1a9bfab29c5feac6d2fb3e6431876b8bce04441dd78",
                "007f02bb822413488541de92736276048a762cbc8263784b0032201d679a0057",
            ),
            "satq-d0c0963b246a5ae9d99d799b": (
                "reject_automated_mask_for_site_promotion",
                "4dc560d3fb99caa5f1a3577ee125f43a57feab01ba60ebbb179dd00e34763a56",
                "18ec514b9a0bca6710df0e5a670b90da7edae9e29ce8f62799dc5241ccf18b14",
            ),
            "satq-ebb41e7fa28c11a35664ec05": (
                "reject_automated_mask_for_site_promotion",
                "72a0cf405f4c3d408c05a72ca5ef1fb52fa5ef2608f913e719dbc6407d378f28",
                "4d6ae4f62ca21cf44b8c20f657f40354ab4e320eaf4f364385eef511b536cfdd",
            ),
        }
        self.assertEqual([spec["queue_id"] for spec in specs[-6:]], list(expected_new))
        decisions = Counter()
        for spec in specs:
            report_raw = (
                definition_path.parent / spec["report_path"]
            ).resolve().read_bytes()
            review_raw = (
                definition_path.parent / spec["path"]
            ).resolve().read_bytes()
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            report = json.loads(report_raw)
            review = json.loads(review_raw)
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            decisions[review["decision"]] += 1
            if spec["queue_id"] in expected_new:
                decision, report_hash, review_hash = expected_new[spec["queue_id"]]
                self.assertEqual(review["decision"], decision)
                self.assertEqual(spec["report_sha256"], report_hash)
                self.assertEqual(spec["sha256"], review_hash)
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 31,
                "retain_site_aligned_change_candidate_for_manual_followup": 12,
            },
        )
        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 28,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13259,
            },
        )
        sentinel = manifest["counts"]["sentinel_lane"]
        self.assertEqual(sentinel["analyst_reviews_examined"], 43)
        self.assertEqual(
            sentinel["analyst_reviews_examined_by_outcome"],
            {
                "rejected_for_site_promotion": 31,
                "retained_visible_change_aoi_followup": 12,
            },
        )
        self.assertEqual(
            sentinel["catalog_state_links"],
            {"completed": 5352, "pending": 18772, "unavailable_no_scene": 295},
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                "README.md": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                "coverage.json": "c05f3eabf7afa0165d3fa2f9fbba3a3051ce88d2e7aed3bf46fdd8967e2942bf",
                "fusion-candidates.csv": "5f5fe534daaefc763961f3ec8302c6ce240d78b62ef94b87d207cba9c1efbf2b",
                "fusion-candidates.jsonl": "aa4204a2cbd865dd3bb6f9bbb249584f2d314882bfab397553f36807f0636f60",
            },
        )

    def test_v12_reproduces_with_unknown014_and_the_v11_review_set(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v12.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v12"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "af441ed1cbb9f3a9db52530c2c2b26f229a1477543152833ec7749ca1b45332e",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "dfc7149354c1494abf6dce6b9bf70bd161ad4e33b085e87bb310bbed453f6d12",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "dfc7149354c1494abf6dce6b9bf70bd161ad4e33b085e87bb310bbed453f6d12  manifest.json\n",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        v11_definition = json.loads(
            (
                PACKAGE_ROOT
                / "sources"
                / "candidate-fusion-2026-07-18-osm-planet-v11.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(definition["parameters"], v11_definition["parameters"])
        self.assertEqual(
            {
                key: value
                for key, value in definition["inputs"].items()
                if key != "satellite_batch_bundles"
            },
            {
                key: value
                for key, value in v11_definition["inputs"].items()
                if key != "satellite_batch_bundles"
            },
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][:2],
            v11_definition["inputs"]["satellite_batch_bundles"][:2],
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][-1],
            {
                "manifest_sha256": "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8",
                "path": "../satellite_review_runs/2026-07-18-global-open-v3-unknown-014",
            },
        )
        self.assertEqual(
            definition["inputs"]["satellite_analyst_reviews"],
            v11_definition["inputs"]["satellite_analyst_reviews"],
        )
        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 24,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13263,
            },
        )
        sentinel = manifest["counts"]["sentinel_lane"]
        self.assertEqual(sentinel["analyst_reviews_examined"], 37)
        self.assertEqual(
            sentinel["analyst_reviews_examined_by_outcome"],
            {
                "rejected_for_site_promotion": 27,
                "retained_visible_change_aoi_followup": 10,
            },
        )
        self.assertEqual(sentinel["catalog_batch_jobs_examined"], 6830)
        self.assertEqual(
            sentinel["catalog_state_links"],
            {"completed": 5352, "pending": 18772, "unavailable_no_scene": 295},
        )
        self.assertFalse(sentinel["queue_or_catalog_availability_is_change_evidence"])
        self.assertFalse(
            sentinel["retained_visible_change_review_confirms_candidate_identity_or_status"]
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                "README.md": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                "coverage.json": "ff1e150b34bd1bace32440968233f0e2c68355e76aa014ea0f94618c478106c9",
                "fusion-candidates.csv": "c51a695ca3ed64465b5960c0bc1ea6dc819097ca3b87bf2bd7a1f783fa58a7c2",
                "fusion-candidates.jsonl": "0535caa3fa7f8e1ef13acada877740b431b602e965405104731e4e7190c2e257",
            },
        )

    def test_v11_reproduces_with_thirty_seven_no_claim_reviews(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v11.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v11"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "09e89ee0c9ad4c22ad081fca8c0a08fbaead8f3b1b6e1d85931a8f0974bb36cc",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "6f4cd3558f9421fda49f503b0ee8a359d8e9cd3631a2ad23ba2cbae2c6c317dc",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "6f4cd3558f9421fda49f503b0ee8a359d8e9cd3631a2ad23ba2cbae2c6c317dc  manifest.json\n",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        v10_definition = json.loads(
            (
                PACKAGE_ROOT
                / "sources"
                / "candidate-fusion-2026-07-18-osm-planet-v10.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(definition["parameters"], v10_definition["parameters"])
        self.assertEqual(
            {
                key: value
                for key, value in definition["inputs"].items()
                if not key.startswith("satellite_")
            },
            {
                key: value
                for key, value in v10_definition["inputs"].items()
                if not key.startswith("satellite_")
            },
        )
        self.assertEqual(
            definition["inputs"]["satellite_queue_bundle"],
            v10_definition["inputs"]["satellite_queue_bundle"],
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][:2],
            v10_definition["inputs"]["satellite_batch_bundles"][:2],
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][-1],
            {
                "manifest_sha256": "e3a99d23b74f56caa0eb817465f6c37a2d23cdb1927428152fdb000c0adcb9a6",
                "path": "../satellite_review_runs/2026-07-18-global-open-v3-unknown-013",
            },
        )

        specs = definition["inputs"]["satellite_analyst_reviews"]
        v10_specs = v10_definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(len(specs), 37)
        self.assertEqual(specs[:31], v10_specs)
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 37)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 37)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 37)

        expected_new = {
            "satq-09d8373cd2587b133b05a18d": (
                "reject_automated_mask_for_site_promotion",
                "79f54996c8de94785ce4e42f1eedb63ef9db793674e63d2bcde4f6084e6b2400",
                "cf96f4f20857aea3c34a1232bd7da0edb0bebeceb759be4a449de3f4a05dd8fd",
            ),
            "satq-133b99948a0977e01a6520c8": (
                "reject_automated_mask_for_site_promotion",
                "e80d602abd6bda2993c47feea7ab91ac570a62e82c432eec54fdf734105269c8",
                "d9368e64000184240cf179cae3114e8db447b4fd4c473e130f199d7cc4e8eb1d",
            ),
            "satq-5181442dce63022037a6bbc1": (
                "reject_automated_mask_for_site_promotion",
                "c30acfea160dbd57b94974154f2e18e328ca2c67a263b83b86d1c3f524daf885",
                "5628e19276012f1a8147b81677fd2fe10d7b3160cd85d1c55e9c7d37e98a37bb",
            ),
            "satq-718ecc6958a13cc59ccf71b9": (
                "retain_site_aligned_change_candidate_for_manual_followup",
                "59d09f9005cff8e991f2e8cd479d4f7126e531656b18e9ee52e6587bfaafc6e3",
                "141b2bddd51b323fa50a62bdfbe9887fe1bd735bf916abdfd87667e7a4b5c9f3",
            ),
            "satq-a1b14d7a9df2a0937106b63e": (
                "retain_site_aligned_change_candidate_for_manual_followup",
                "e7bf727277ce1e80240776a9d77cd3f888b95d92fc999bc9ae1660c5bfc67aa4",
                "a02ec30d84db30b4768b4e721183cc379ccd3ec3b49ec1e72f99bb3b6617d68d",
            ),
            "satq-e05d6e77d52e8d15e8125462": (
                "reject_automated_mask_for_site_promotion",
                "d7777a6fa0eeef623d7e73519adf856af57cfa361f260879488d2c0c27b8df61",
                "7da9d2c1ad8b476a06e9b4a4ea80e1dd2decaf742e6cca9a5d56e2d3dc6e266e",
            ),
        }
        self.assertEqual([spec["queue_id"] for spec in specs[-6:]], list(expected_new))
        decisions = Counter()
        for spec in specs:
            report_raw = (
                definition_path.parent / spec["report_path"]
            ).resolve().read_bytes()
            review_raw = (
                definition_path.parent / spec["path"]
            ).resolve().read_bytes()
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            report = json.loads(report_raw)
            review = json.loads(review_raw)
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            decisions[review["decision"]] += 1
            if spec["queue_id"] in expected_new:
                decision, report_hash, review_hash = expected_new[spec["queue_id"]]
                self.assertEqual(review["decision"], decision)
                self.assertEqual(spec["report_sha256"], report_hash)
                self.assertEqual(spec["sha256"], review_hash)
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 27,
                "retain_site_aligned_change_candidate_for_manual_followup": 10,
            },
        )

        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 24,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13263,
            },
        )
        self.assertEqual(
            manifest["counts"]["sentinel_lane"],
            {
                "analyst_review_aoi_overlap_links_by_outcome": {
                    "not_analyst_reviewed": 24265,
                    "rejected_for_site_promotion": 125,
                    "retained_visible_change_aoi_followup": 29,
                },
                "analyst_reviews_examined": 37,
                "analyst_reviews_examined_by_outcome": {
                    "rejected_for_site_promotion": 27,
                    "retained_visible_change_aoi_followup": 10,
                },
                "candidates_linked": 5795,
                "candidates_with_analyst_review_aoi_overlap_by_outcome": {
                    "rejected_for_site_promotion": 118,
                    "retained_visible_change_aoi_followup": 24,
                },
                "catalog_batch_jobs_examined": 6830,
                "catalog_state_links": {
                    "completed": 4936,
                    "pending": 19196,
                    "unavailable_no_scene": 287,
                },
                "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                    "rejected_for_site_promotion": 21,
                    "retained_visible_change_aoi_followup": 8,
                },
                "queue_aoi_overlap_links": 24419,
                "queue_jobs_examined": 6830,
                "queue_or_catalog_availability_is_change_evidence": False,
                "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            },
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                "README.md": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                "coverage.json": "643b7aa5f5e948f801b85defb6023aa27e333ed65e69548bffdb71cb6fedfdc0",
                "fusion-candidates.csv": "c51a695ca3ed64465b5960c0bc1ea6dc819097ca3b87bf2bd7a1f783fa58a7c2",
                "fusion-candidates.jsonl": "90d3b7305414451244fd275fc714142d55559f1422300b62d41e148756ef08db",
            },
        )

    def test_v10_reproduces_with_thirty_one_no_claim_reviews(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v10.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v10"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "3e8c321f17a0ff915dc55e79dcdb511b034bf5b225a8d97c8d02c15a091340e1",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "83b51f75f2063815422fce3c308af8975a134b68b93aefd0b5ccbcad5c7bf3d4",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "83b51f75f2063815422fce3c308af8975a134b68b93aefd0b5ccbcad5c7bf3d4  manifest.json\n",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        v9_definition = json.loads(
            (
                PACKAGE_ROOT
                / "sources"
                / "candidate-fusion-2026-07-18-osm-planet-v9.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(definition["parameters"], v9_definition["parameters"])
        self.assertEqual(
            {
                key: value
                for key, value in definition["inputs"].items()
                if not key.startswith("satellite_")
            },
            {
                key: value
                for key, value in v9_definition["inputs"].items()
                if not key.startswith("satellite_")
            },
        )
        self.assertEqual(
            definition["inputs"]["satellite_queue_bundle"],
            v9_definition["inputs"]["satellite_queue_bundle"],
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][:2],
            v9_definition["inputs"]["satellite_batch_bundles"][:2],
        )
        self.assertEqual(
            definition["inputs"]["satellite_batch_bundles"][-1],
            {
                "manifest_sha256": "672a92b835d4884f26f849318b1c8766706895510c11edc00bc5dcc131ea35d5",
                "path": "../satellite_review_runs/2026-07-18-global-open-v3-unknown-010",
            },
        )
        self.assertNotIn("unknown-009", definition_raw.decode("utf-8"))
        specs = definition["inputs"]["satellite_analyst_reviews"]
        v9_specs = v9_definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(len(specs), 31)
        self.assertEqual(
            [spec["queue_id"] for spec in specs[:25]],
            [spec["queue_id"] for spec in v9_specs],
        )
        for old, new in zip(v9_specs, specs[:25], strict=True):
            self.assertEqual(new["report_sha256"], old["report_sha256"])
            self.assertEqual(new["sha256"], old["sha256"])
            if "unknown-009" in old["path"]:
                self.assertEqual(
                    new["path"], old["path"].replace("unknown-009", "unknown-010")
                )
                self.assertEqual(
                    new["report_path"],
                    old["report_path"].replace("unknown-009", "unknown-010"),
                )
                self.assertEqual(
                    (definition_path.parent / new["path"]).resolve().read_bytes(),
                    (definition_path.parent / old["path"]).resolve().read_bytes(),
                )
                self.assertEqual(
                    (definition_path.parent / new["report_path"]).resolve().read_bytes(),
                    (definition_path.parent / old["report_path"]).resolve().read_bytes(),
                )
            else:
                self.assertEqual(new, old)
        self.assertEqual(
            sum("unknown-010" in spec["path"] for spec in specs), 23
        )
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 31)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 31)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 31)

        expected_new = {
            "satq-16cb9148d54b491954a169fb": (
                "retain_site_aligned_change_candidate_for_manual_followup",
                "660842b385067bcca318011808693ce1782d45d32f75b5e5206e407786a06085",
                "e4eda39a6ad768deda18b908401d722419ea0c41beeda88e44a38d88df4ab4b8",
            ),
            "satq-0384b818546e954492a85864": (
                "reject_automated_mask_for_site_promotion",
                "03a3acf7c5be5bd55220166a99dbbc32e993217ed43ef571e5b7ef5824255374",
                "c22b63ed7fcd6eda1195a7b5b72222a10d68f48636a5c2497172836639e1db52",
            ),
            "satq-1ce9513e80efaddbb12c117c": (
                "reject_automated_mask_for_site_promotion",
                "9c5ab30eae71865c4c5302eb82266055ff4a1b0e26dccdd3f98787ee2e4c4b5d",
                "a0f7c79db58d476aaced1fbeeefef9c2bebd7b99808500d22a4709d2a8aebeac",
            ),
            "satq-3a5dbdef8b0fd5a8f4e53bf1": (
                "reject_automated_mask_for_site_promotion",
                "dfa4608ea53ee475cda4e0717afafaaf95cbb11307cf04471471261dd76b8d55",
                "7d5d27271436b25445acd89ca650a736822eadd6df6e5497226acb771f4075ff",
            ),
            "satq-2df9671fb56a0fe6b09b4143": (
                "reject_automated_mask_for_site_promotion",
                "adbfcbda3039bea9fd0e8a15f09c4f069893b030f4a75985af2ae02697340465",
                "0cd4d38d9777313a5d3df8f388ec5d3ee3567f99347a26c3e5bde52dfdefe6e0",
            ),
            "satq-6553bba071b08b8a3168f3a2": (
                "reject_automated_mask_for_site_promotion",
                "4783a8f5659af854f8a4a8d1dbcd51d9953f3f52f3b0f11758aa1d9334832e3c",
                "aacbff921ad2cb0b55bbd3fdb19f54898be4d58b75a1f771a3a14ce4e7fc54d4",
            ),
        }
        self.assertEqual(
            [spec["queue_id"] for spec in specs[-6:]],
            list(expected_new),
        )
        decisions = Counter()
        for spec in specs:
            report_raw = (definition_path.parent / spec["report_path"]).resolve().read_bytes()
            review_raw = (definition_path.parent / spec["path"]).resolve().read_bytes()
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            report = json.loads(report_raw)
            review = json.loads(review_raw)
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            decisions[review["decision"]] += 1
            if spec["queue_id"] in expected_new:
                decision, report_hash, review_hash = expected_new[spec["queue_id"]]
                self.assertEqual(review["decision"], decision)
                self.assertEqual(spec["report_sha256"], report_hash)
                self.assertEqual(spec["sha256"], review_hash)
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 23,
                "retain_site_aligned_change_candidate_for_manual_followup": 8,
            },
        )

        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 22,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13265,
            },
        )
        self.assertEqual(
            manifest["counts"]["sentinel_lane"],
            {
                "analyst_review_aoi_overlap_links_by_outcome": {
                    "not_analyst_reviewed": 24291,
                    "rejected_for_site_promotion": 101,
                    "retained_visible_change_aoi_followup": 27,
                },
                "analyst_reviews_examined": 31,
                "analyst_reviews_examined_by_outcome": {
                    "rejected_for_site_promotion": 23,
                    "retained_visible_change_aoi_followup": 8,
                },
                "candidates_linked": 5795,
                "candidates_with_analyst_review_aoi_overlap_by_outcome": {
                    "rejected_for_site_promotion": 94,
                    "retained_visible_change_aoi_followup": 22,
                },
                "catalog_batch_jobs_examined": 6830,
                "catalog_state_links": {
                    "completed": 4275,
                    "pending": 19890,
                    "unavailable_no_scene": 254,
                },
                "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                    "rejected_for_site_promotion": 17,
                    "retained_visible_change_aoi_followup": 7,
                },
                "queue_aoi_overlap_links": 24419,
                "queue_jobs_examined": 6830,
                "queue_or_catalog_availability_is_change_evidence": False,
                "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            },
        )
        self.assertEqual(
            {
                name: details["sha256"]
                for name, details in manifest["outputs"].items()
            },
            {
                "ATTRIBUTION.txt": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                "README.md": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                "coverage.json": "f7ba4b6ffb8f84ee2a7034a2131f2d18699c273a397a75e4a259c62e8636c571",
                "fusion-candidates.csv": "c47c1f8ad286433fe4a6952dec5b9f15467bcbe12926dd9d2b7fb2d0c66eefed",
                "fusion-candidates.jsonl": "71578e0722bd1af07dee3fbb33fcbd1dae3b633ad95c12079a412dbd80a3070c",
            },
        )

    def test_v9_reproduces_with_unknown009_and_twenty_five_no_claim_reviews(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v9.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v9"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "e525b85df09feea10a354d41a0c0896a59963d9916e106b106aef13098f03871",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "ea0ad82b3082c7473282196246da616f2957247a80ddd126abee5a030375db11",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "ea0ad82b3082c7473282196246da616f2957247a80ddd126abee5a030375db11  manifest.json\n",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        v8_definition = json.loads(
            (
                PACKAGE_ROOT
                / "sources"
                / "candidate-fusion-2026-07-18-osm-planet-v8.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(definition["parameters"], v8_definition["parameters"])
        non_satellite = {
            key: value
            for key, value in definition["inputs"].items()
            if not key.startswith("satellite_")
        }
        v8_non_satellite = {
            key: value
            for key, value in v8_definition["inputs"].items()
            if not key.startswith("satellite_")
        }
        self.assertEqual(non_satellite, v8_non_satellite)

        batches = definition["inputs"]["satellite_batch_bundles"]
        self.assertEqual(
            [batch["path"] for batch in batches],
            [
                "../satellite_review_runs/2026-07-18-global-open-v3-active-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-proposed-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-unknown-009",
            ],
        )
        self.assertEqual(
            batches[-1]["manifest_sha256"],
            "9efff4e965e67584e0ba48d8d4d31385089f9af2e5880c44c0a24ba21eae350f",
        )
        self.assertNotRegex(definition_raw.decode("utf-8"), r"unknown-00[1-8]")
        unknown_batch = json.loads(
            (
                definition_path.parent
                / batches[-1]["path"]
                / "batch-manifest.json"
            ).resolve().read_text(encoding="utf-8")
        )
        self.assertEqual(
            unknown_batch["summary"],
            {
                "jobs_completed": 918,
                "jobs_failed": 0,
                "jobs_pending": 5786,
                "jobs_selected": 6736,
                "jobs_unavailable_no_scene": 32,
            },
        )

        specs = definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(len(specs), 25)
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 25)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 25)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 25)
        unknown_specs = [
            spec for spec in specs if "global-open-v3-unknown-" in spec["path"]
        ]
        self.assertEqual(len(unknown_specs), 23)
        self.assertTrue(
            all("global-open-v3-unknown-009" in spec["path"] for spec in unknown_specs)
        )

        v8_unknown_by_id = {
            spec["queue_id"]: spec
            for spec in v8_definition["inputs"]["satellite_analyst_reviews"]
            if "global-open-v3-unknown-" in spec["path"]
        }
        v9_unknown_by_id = {spec["queue_id"]: spec for spec in unknown_specs}
        self.assertEqual(len(v8_unknown_by_id), 19)
        self.assertTrue(v8_unknown_by_id.keys() <= v9_unknown_by_id.keys())
        for queue_id, v8_spec in v8_unknown_by_id.items():
            v9_spec = v9_unknown_by_id[queue_id]
            self.assertEqual(v9_spec["sha256"], v8_spec["sha256"])
            self.assertEqual(v9_spec["report_sha256"], v8_spec["report_sha256"])
            old_review = (definition_path.parent / v8_spec["path"]).resolve()
            new_review = (definition_path.parent / v9_spec["path"]).resolve()
            old_report = (definition_path.parent / v8_spec["report_path"]).resolve()
            new_report = (definition_path.parent / v9_spec["report_path"]).resolve()
            self.assertEqual(old_review.read_bytes(), new_review.read_bytes())
            self.assertEqual(old_report.read_bytes(), new_report.read_bytes())

        new_expected = {
            "satq-05727b50b98948308a848eab": {
                "decision": "retain_site_aligned_change_candidate_for_manual_followup",
                "report_sha256": "b0f310759278d57872703aa36ad66a691e0a3c3f39b82260a40aa6a4333fafca",
                "sha256": "0255942210ed8cff424e6ab9cf253c54e799ce55282d3f70bdb991d18e714b2e",
            },
            "satq-5b2c2d8ec553b3fcff6aac99": {
                "decision": "reject_automated_mask_for_site_promotion",
                "report_sha256": "1e6eec206e239735a518f75f8137516a31a2302a88b90db456ff862b48079866",
                "sha256": "88b00d1267baaf1c0c9cfd1a593a46995fba14b1ba15bc4fdd3f34a3f5f090b6",
            },
            "satq-7fd64307ea68612e30b6b5ac": {
                "decision": "reject_automated_mask_for_site_promotion",
                "report_sha256": "a56bd13e7a4840f68cf6d858c0dd68209ce4f7b9f39712267f8bb0747c892011",
                "sha256": "7008f2aeeea7c657f814d808f56e10d1bc071d59b39db2bbccee1ce9405efcb4",
            },
            "satq-c9481eec04ca05883267c576": {
                "decision": "reject_automated_mask_for_site_promotion",
                "report_sha256": "e469eadc01ef1c16082bc24ef9dd3962d92ececf6e530317a02547e30ba7afe0",
                "sha256": "ed8e739b78ef939b83a464bac2598b15935acc747b368d94ee42d16e18ab6c20",
            },
        }
        self.assertEqual(
            set(v9_unknown_by_id) - set(v8_unknown_by_id), set(new_expected)
        )

        decisions = Counter()
        expected_scope = {
            "data_center_identity_confirmed": False,
            "lifecycle_status_confirmed": False,
            "operating_status_inferred": False,
            "power_or_energy_inferred": False,
            "review_required": True,
        }
        for spec in specs:
            review_path = (definition_path.parent / spec["path"]).resolve()
            report_path = (definition_path.parent / spec["report_path"]).resolve()
            review_raw = review_path.read_bytes()
            report_raw = report_path.read_bytes()
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            review = json.loads(review_raw)
            report = json.loads(report_raw)
            self.assertEqual(review["scope"], expected_scope)
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            decisions[review["decision"]] += 1
            if spec["queue_id"] in new_expected:
                expected = new_expected[spec["queue_id"]]
                self.assertEqual(review["decision"], expected["decision"])
                self.assertEqual(spec["report_sha256"], expected["report_sha256"])
                self.assertEqual(spec["sha256"], expected["sha256"])
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 18,
                "retain_site_aligned_change_candidate_for_manual_followup": 7,
            },
        )

        self.assertEqual(manifest["parameters"], v8_definition["parameters"])
        self.assertEqual(
            manifest["scope"],
            {
                "automatic_atlas_import_allowed": False,
                "candidate_is_capacity_power_or_energy_claim": False,
                "candidate_is_data_centre_identity_claim": False,
                "candidate_is_lifecycle_or_status_claim": False,
                "candidate_is_operating_status_claim": False,
                "candidate_is_type_workload_or_operating_model_claim": False,
                "candidate_merge_performed": False,
                "distinct_source_root_is_confirmed_independence": False,
                "proximity_or_overlap_is_independent_corroboration": False,
                "review_only": True,
                "unique_physical_site_count_computed": False,
            },
        )
        self.assertEqual(
            manifest["outputs"],
            {
                "ATTRIBUTION.txt": {
                    "bytes": 339,
                    "sha256": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                },
                "README.md": {
                    "bytes": 1007,
                    "sha256": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                },
                "coverage.json": {
                    "bytes": 2549,
                    "sha256": "4a7e52b2eabe89ea89e2073ff581feb02603dd2e5435aff6e204cec448a1ca3b",
                },
                "fusion-candidates.csv": {
                    "bytes": 1978340,
                    "records": 14324,
                    "sha256": "105d734b154737463ed740b4eed80d9ed5ba596ba5aa02793bb39a4afdc5d627",
                },
                "fusion-candidates.jsonl": {
                    "bytes": 71996894,
                    "records": 14324,
                    "sha256": "e24d3829f3dcca359ca2a3a230b9dc17083b5dc0fd5d28d3b19c7a5eb4a462ab",
                },
            },
        )
        self.assertEqual(
            manifest["counts"]["primary_shortlist"],
            {
                "candidate_count_is_data_centre_count": False,
                "candidates_examined": 102451,
                "candidates_with_any_fusion_opportunity": 14324,
                "candidates_without_fusion_opportunity": 88127,
            },
        )
        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 22,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13265,
            },
        )
        self.assertEqual(
            manifest["counts"]["sentinel_lane"],
            {
                "analyst_review_aoi_overlap_links_by_outcome": {
                    "not_analyst_reviewed": 24333,
                    "rejected_for_site_promotion": 61,
                    "retained_visible_change_aoi_followup": 25,
                },
                "analyst_reviews_examined": 25,
                "analyst_reviews_examined_by_outcome": {
                    "rejected_for_site_promotion": 18,
                    "retained_visible_change_aoi_followup": 7,
                },
                "candidates_linked": 5795,
                "candidates_with_analyst_review_aoi_overlap_by_outcome": {
                    "rejected_for_site_promotion": 54,
                    "retained_visible_change_aoi_followup": 22,
                },
                "catalog_batch_jobs_examined": 6830,
                "catalog_state_links": {
                    "completed": 3867,
                    "pending": 20315,
                    "unavailable_no_scene": 237,
                },
                "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                    "rejected_for_site_promotion": 12,
                    "retained_visible_change_aoi_followup": 6,
                },
                "queue_aoi_overlap_links": 24419,
                "queue_jobs_examined": 6830,
                "queue_or_catalog_availability_is_change_evidence": False,
                "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            },
        )

    def test_v8_reproduces_with_unknown007_as_sole_cumulative_replacement(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v8.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v8"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "bb9bf94a1faf1a51b342c46ce587f6a6baac37fbdd8f1b69070393340d6c09bb",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "487ec311100fac7558bf92fdf9c1ea46dfd0311e158e46272f8cab1e50c82b87",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "487ec311100fac7558bf92fdf9c1ea46dfd0311e158e46272f8cab1e50c82b87  manifest.json\n",
        )

        batches = definition["inputs"]["satellite_batch_bundles"]
        self.assertEqual(
            [batch["path"] for batch in batches],
            [
                "../satellite_review_runs/2026-07-18-global-open-v3-active-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-proposed-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-unknown-007",
            ],
        )
        self.assertEqual(
            batches[-1]["manifest_sha256"],
            "7239349d62af7a7b271e398dd1b62614fa55ec312e54a659e22746754da79330",
        )
        self.assertNotRegex(definition_raw.decode("utf-8"), r"unknown-00[1-6]")
        unknown_batch = json.loads(
            (
                definition_path.parent
                / batches[-1]["path"]
                / "batch-manifest.json"
            ).resolve().read_text(encoding="utf-8")
        )
        self.assertEqual(
            unknown_batch["summary"],
            {
                "jobs_completed": 724,
                "jobs_failed": 0,
                "jobs_pending": 5986,
                "jobs_selected": 6736,
                "jobs_unavailable_no_scene": 26,
            },
        )

        specs = definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(len(specs), 21)
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 21)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 21)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 21)
        unknown_specs = [
            spec for spec in specs if "global-open-v3-unknown-" in spec["path"]
        ]
        self.assertEqual(len(unknown_specs), 19)
        self.assertTrue(
            all("global-open-v3-unknown-007" in spec["path"] for spec in unknown_specs)
        )
        prior_unknown_queue_ids = {
            spec["queue_id"]
            for spec in json.loads(
                (
                    PACKAGE_ROOT
                    / "sources"
                    / "candidate-fusion-2026-07-18-osm-planet-v7.json"
                ).read_text(encoding="utf-8")
            )["inputs"]["satellite_analyst_reviews"]
            if "global-open-v3-unknown-" in spec["path"]
        }
        self.assertEqual(
            {spec["queue_id"] for spec in unknown_specs} - prior_unknown_queue_ids,
            {
                "satq-19ba8a09e793d8f73ba71804",
                "satq-584c2da9dd872dbb30dbe70f",
                "satq-6cb90d5fbd84d2a283128423",
                "satq-b4c7c51913e4f80878b9aca7",
            },
        )

        decisions = Counter()
        expected_scope = {
            "data_center_identity_confirmed": False,
            "lifecycle_status_confirmed": False,
            "operating_status_inferred": False,
            "power_or_energy_inferred": False,
            "review_required": True,
        }
        for spec in specs:
            review_path = (definition_path.parent / spec["path"]).resolve()
            report_path = (definition_path.parent / spec["report_path"]).resolve()
            review_raw = review_path.read_bytes()
            report_raw = report_path.read_bytes()
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            review = json.loads(review_raw)
            report = json.loads(report_raw)
            self.assertEqual(review["scope"], expected_scope)
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            decisions[review["decision"]] += 1
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 15,
                "retain_site_aligned_change_candidate_for_manual_followup": 6,
            },
        )

        self.assertEqual(
            manifest["scope"],
            {
                "automatic_atlas_import_allowed": False,
                "candidate_is_capacity_power_or_energy_claim": False,
                "candidate_is_data_centre_identity_claim": False,
                "candidate_is_lifecycle_or_status_claim": False,
                "candidate_is_operating_status_claim": False,
                "candidate_is_type_workload_or_operating_model_claim": False,
                "candidate_merge_performed": False,
                "distinct_source_root_is_confirmed_independence": False,
                "proximity_or_overlap_is_independent_corroboration": False,
                "review_only": True,
                "unique_physical_site_count_computed": False,
            },
        )
        self.assertEqual(
            manifest["outputs"],
            {
                "ATTRIBUTION.txt": {
                    "bytes": 339,
                    "sha256": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                },
                "README.md": {
                    "bytes": 1007,
                    "sha256": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                },
                "coverage.json": {
                    "bytes": 2546,
                    "sha256": "f9065629c3dd8cb2c7d2bb6bc2252c11fc38176e388a057001cf2394c4663ce8",
                },
                "fusion-candidates.csv": {
                    "bytes": 1977609,
                    "records": 14324,
                    "sha256": "66c07d4e7fda1ed431db2f4742f8bbfb9c1151a0a11faffd787da25f99762508",
                },
                "fusion-candidates.jsonl": {
                    "bytes": 71993922,
                    "records": 14324,
                    "sha256": "58c9acc4dc6cd6cc85fe646f49cf438cbe42dac836820ebac5f8136ca3b85867",
                },
            },
        )
        self.assertEqual(
            manifest["counts"]["primary_shortlist"],
            {
                "candidate_count_is_data_centre_count": False,
                "candidates_examined": 102451,
                "candidates_with_any_fusion_opportunity": 14324,
                "candidates_without_fusion_opportunity": 88127,
            },
        )
        self.assertEqual(
            manifest["counts"]["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 5,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13282,
            },
        )
        self.assertEqual(
            manifest["counts"]["sentinel_lane"],
            {
                "analyst_review_aoi_overlap_links_by_outcome": {
                    "not_analyst_reviewed": 24352,
                    "rejected_for_site_promotion": 59,
                    "retained_visible_change_aoi_followup": 8,
                },
                "analyst_reviews_examined": 21,
                "analyst_reviews_examined_by_outcome": {
                    "rejected_for_site_promotion": 15,
                    "retained_visible_change_aoi_followup": 6,
                },
                "candidates_linked": 5795,
                "candidates_with_analyst_review_aoi_overlap_by_outcome": {
                    "rejected_for_site_promotion": 52,
                    "retained_visible_change_aoi_followup": 5,
                },
                "catalog_batch_jobs_examined": 6830,
                "catalog_state_links": {
                    "completed": 3172,
                    "pending": 21037,
                    "unavailable_no_scene": 210,
                },
                "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                    "rejected_for_site_promotion": 11,
                    "retained_visible_change_aoi_followup": 5,
                },
                "queue_aoi_overlap_links": 24419,
                "queue_jobs_examined": 6830,
                "queue_or_catalog_availability_is_change_evidence": False,
                "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            },
        )

    def test_v7_reproduces_with_unknown006_as_sole_cumulative_replacement(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v7.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v7"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        manifest_raw = (bundle_path / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "13ddff6239acb89e6a51c4abb9c15acb39310a2bd7134b03a6b464ef178149bf",
        )
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "c009f8291bdfd56e18e473dfa088da52d9a5748379b252a44c59f87a664613fa",
        )
        self.assertEqual(
            (bundle_path / "manifest.sha256").read_text(encoding="ascii"),
            "c009f8291bdfd56e18e473dfa088da52d9a5748379b252a44c59f87a664613fa  manifest.json\n",
        )

        batches = definition["inputs"]["satellite_batch_bundles"]
        self.assertEqual(
            [batch["path"] for batch in batches],
            [
                "../satellite_review_runs/2026-07-18-global-open-v3-active-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-proposed-001",
                "../satellite_review_runs/2026-07-18-global-open-v3-unknown-006",
            ],
        )
        self.assertEqual(
            batches[-1]["manifest_sha256"],
            "08d883b5f3a58061055b099fa9652991f015b63f2b590b7e9b70911b4fa8a7c9",
        )
        self.assertNotRegex(definition_raw.decode("utf-8"), r"unknown-00[1-5]")

        specs = definition["inputs"]["satellite_analyst_reviews"]
        self.assertEqual(len(specs), 17)
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 17)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 17)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 17)
        unknown_specs = [
            spec for spec in specs if "global-open-v3-unknown-" in spec["path"]
        ]
        self.assertEqual(len(unknown_specs), 15)
        self.assertTrue(
            all("global-open-v3-unknown-006" in spec["path"] for spec in unknown_specs)
        )
        self.assertEqual(
            {
                "satq-84c0eaa9ff38437a843f0ff6",
                "satq-90e31eb2995166e80e2f417d",
                "satq-c377e9e78f223b749ea998bb",
                "satq-f2554b764141d2591c78d3a8",
            },
            {spec["queue_id"] for spec in unknown_specs}
            - {
                "satq-0032e259e72fe68454610d49",
                "satq-151a51d3b1e410883058ec9a",
                "satq-2782dac6ff28c6658f12f84e",
                "satq-3fd1cc06b7c43dc3547a2b6b",
                "satq-4574ad91d56aced6425c5405",
                "satq-4c316eedd135d6138a145bfe",
                "satq-5a1c2165c2264a5ff491d5f0",
                "satq-7e006a775807e1cd7d52b58e",
                "satq-8c3d80c8565c7fe7ed060621",
                "satq-e20d4867a35ce034a9415f8c",
                "satq-f1aa8182923776809ac99da4",
            },
        )

        decisions = Counter()
        expected_scope = {
            "data_center_identity_confirmed": False,
            "lifecycle_status_confirmed": False,
            "operating_status_inferred": False,
            "power_or_energy_inferred": False,
            "review_required": True,
        }
        for spec in specs:
            review_path = (definition_path.parent / spec["path"]).resolve()
            report_path = (definition_path.parent / spec["report_path"]).resolve()
            review_raw = review_path.read_bytes()
            report_raw = report_path.read_bytes()
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            review = json.loads(review_raw)
            report = json.loads(report_raw)
            self.assertEqual(review["scope"], expected_scope)
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            decisions[review["decision"]] += 1
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 11,
                "retain_site_aligned_change_candidate_for_manual_followup": 6,
            },
        )

        self.assertEqual(
            manifest["scope"],
            {
                "automatic_atlas_import_allowed": False,
                "candidate_is_capacity_power_or_energy_claim": False,
                "candidate_is_data_centre_identity_claim": False,
                "candidate_is_lifecycle_or_status_claim": False,
                "candidate_is_operating_status_claim": False,
                "candidate_is_type_workload_or_operating_model_claim": False,
                "candidate_merge_performed": False,
                "distinct_source_root_is_confirmed_independence": False,
                "proximity_or_overlap_is_independent_corroboration": False,
                "review_only": True,
                "unique_physical_site_count_computed": False,
            },
        )
        self.assertEqual(
            manifest["outputs"],
            {
                "ATTRIBUTION.txt": {
                    "bytes": 339,
                    "sha256": "ae736ed2ba045cee0d2cf7669d420ed99654a33a3df2d543fe9d2efbea5158c7",
                },
                "README.md": {
                    "bytes": 1007,
                    "sha256": "c14b9997a9aaf2511393d635f914474bc6b3ddd79fe4a6113ed0dd8b3021b3d8",
                },
                "coverage.json": {
                    "bytes": 2545,
                    "sha256": "23119d02476867049e9b07f6aa2494c7a8a45d1a6ef5688ba4f37244591dd45e",
                },
                "fusion-candidates.csv": {
                    "bytes": 1977609,
                    "records": 14324,
                    "sha256": "66c07d4e7fda1ed431db2f4742f8bbfb9c1151a0a11faffd787da25f99762508",
                },
                "fusion-candidates.jsonl": {
                    "bytes": 71992712,
                    "records": 14324,
                    "sha256": "6c701dba5308dbc923cf0d047441d5dcc7492a49d161577a5e3d070016cc5457",
                },
            },
        )
        counts = manifest["counts"]
        self.assertEqual(
            counts["primary_shortlist"],
            {
                "candidate_count_is_data_centre_count": False,
                "candidates_examined": 102451,
                "candidates_with_any_fusion_opportunity": 14324,
                "candidates_without_fusion_opportunity": 88127,
            },
        )
        self.assertEqual(
            counts["review_priority_tiers"],
            {
                "analyst_retained_visible_change_aoi_overlap_followup": 5,
                "distinct_source_root_opportunity": 1037,
                "shared_osm_root_or_queue_opportunity": 13282,
            },
        )
        self.assertEqual(
            counts["sentinel_lane"],
            {
                "analyst_review_aoi_overlap_links_by_outcome": {
                    "not_analyst_reviewed": 24368,
                    "rejected_for_site_promotion": 43,
                    "retained_visible_change_aoi_followup": 8,
                },
                "analyst_reviews_examined": 17,
                "analyst_reviews_examined_by_outcome": {
                    "rejected_for_site_promotion": 11,
                    "retained_visible_change_aoi_followup": 6,
                },
                "candidates_linked": 5795,
                "candidates_with_analyst_review_aoi_overlap_by_outcome": {
                    "rejected_for_site_promotion": 36,
                    "retained_visible_change_aoi_followup": 5,
                },
                "catalog_batch_jobs_examined": 6830,
                "catalog_state_links": {
                    "completed": 2786,
                    "pending": 21431,
                    "unavailable_no_scene": 202,
                },
                "distinct_analyst_reviews_with_candidate_overlap_by_outcome": {
                    "rejected_for_site_promotion": 8,
                    "retained_visible_change_aoi_followup": 5,
                },
                "queue_aoi_overlap_links": 24419,
                "queue_jobs_examined": 6830,
                "queue_or_catalog_availability_is_change_evidence": False,
                "retained_visible_change_review_confirms_candidate_identity_or_status": False,
            },
        )

    def test_v6_reproduces_with_thirteen_unique_no_claim_reviews(self):
        definition_path = (
            PACKAGE_ROOT
            / "sources"
            / "candidate-fusion-2026-07-18-osm-planet-v6.json"
        )
        bundle_path = (
            PACKAGE_ROOT
            / "candidate_fusion"
            / "2026-07-18-osm-planet-priority-v6"
        )
        manifest = validate_candidate_fusion(
            bundle_path, definition_path=definition_path
        )
        self.assertEqual(
            manifest["counts"]["sentinel_lane"]["analyst_reviews_examined"],
            13,
        )
        specs = json.loads(definition_path.read_text(encoding="utf-8"))["inputs"][
            "satellite_analyst_reviews"
        ]
        self.assertEqual(len({spec["queue_id"] for spec in specs}), 13)
        self.assertEqual(len({spec["report_sha256"] for spec in specs}), 13)
        self.assertEqual(len({spec["sha256"] for spec in specs}), 13)
        decisions = Counter()
        expected_scope = {
            "data_center_identity_confirmed": False,
            "lifecycle_status_confirmed": False,
            "operating_status_inferred": False,
            "power_or_energy_inferred": False,
            "review_required": True,
        }
        for spec in specs:
            review_path = (definition_path.parent / spec["path"]).resolve()
            report_path = (definition_path.parent / spec["report_path"]).resolve()
            review_raw = review_path.read_bytes()
            report_raw = report_path.read_bytes()
            self.assertEqual(hashlib.sha256(review_raw).hexdigest(), spec["sha256"])
            self.assertEqual(
                hashlib.sha256(report_raw).hexdigest(), spec["report_sha256"]
            )
            review = json.loads(review_raw)
            report = json.loads(report_raw)
            self.assertEqual(review["scope"], expected_scope)
            self.assertFalse(review["atlas_claims_created"])
            self.assertFalse(review["automated_promotion_allowed"])
            self.assertFalse(report["classification"]["identity_claim"])
            self.assertFalse(report["classification"]["lifecycle_claim"])
            self.assertTrue(report["classification"]["review_required"])
            decisions[review["decision"]] += 1
        self.assertEqual(
            decisions,
            {
                "reject_automated_mask_for_site_promotion": 7,
                "retain_site_aligned_change_candidate_for_manual_followup": 6,
            },
        )

    def test_source_root_collapses_osm_derived_families(self):
        self.assertEqual(_source_root("openstreetmap"), "openstreetmap")
        self.assertEqual(_source_root("openstreetmap:pnnl_im3"), "openstreetmap")
        self.assertEqual(_source_root("wikidata"), "wikidata")

    def test_fusion_keeps_roots_and_claim_boundaries_visible(self):
        primary = [
            _primary("way/1", west=-0.01, south=-0.01, east=0.01, north=0.01),
            _primary("way/2", west=20.0, south=20.0, east=20.01, north=20.01),
        ]
        atlas = [
            _atlas(
                "osm-reference",
                longitude=0.0,
                latitude=0.0,
                source_family="openstreetmap:pnnl_im3",
                stable_key="osm:way/1",
            ),
            _atlas(
                "distinct-reference",
                longitude=0.005,
                latitude=0.0,
                source_family="wikidata",
                stable_key="wikidata:Q1",
            ),
        ]
        overture = [
            {
                "gers_id": "gers-shared",
                "bounds": (-0.005, -0.005, 0.005, 0.005),
                "upstream_source_roots": ["openstreetmap", "microsoft_ml_buildings"],
                "upstream_osm_identities": ["way/9"],
                "review_priority_tier": "novel_industrial_label",
            },
            {
                "gers_id": "gers-distinct",
                "bounds": (-0.004, -0.004, 0.004, 0.004),
                "upstream_source_roots": ["esri_community_maps"],
                "upstream_osm_identities": [],
                "review_priority_tier": "novel_very_large_footprint",
            },
        ]
        queue = {
            "distinct-reference": [
                {
                    "queue_id": "satq-one",
                    "entity_id": "distinct-reference",
                    "aoi_bbox_wgs84": [-0.02, -0.02, 0.02, 0.02],
                    "priority_tier": "active_construction",
                }
            ]
        }
        candidates, coverage = _derive(
            primary,
            atlas_features=atlas,
            overture_records=overture,
            open_buildings=[
                {
                    "bundle_id": "open-buildings-test",
                    "aoi_bbox_wgs84": [-0.02, -0.02, 0.02, 0.02],
                    "candidate_ids": ["temporal-one"],
                }
            ],
            queue_by_entity=queue,
            batch_states={"satq-one": {"state": "completed"}},
            analyst_reviews={
                "satq-one": {
                    "decision": "retain_site_aligned_change_candidate_for_manual_followup"
                }
            },
            atlas_max_distance_m=5_000,
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["candidate_id"], "way/1")
        self.assertEqual(
            candidate["review_priority"]["tier"],
            "analyst_retained_visible_change_aoi_overlap_followup",
        )
        self.assertEqual(
            candidate["review_priority"]["distinct_non_osm_source_roots"],
            ["copernicus_sentinel_2", "esri_community_maps", "wikidata"],
        )
        atlas_links = candidate["evidence_opportunities"]["atlas_reference_proximity"]
        exact_link = next(
            link for link in atlas_links if link["exact_upstream_identity_match"]
        )
        self.assertEqual(exact_link["relationship"], "exact_shared_osm_identity")
        self.assertFalse(exact_link["distinct_root_is_confirmed_independence"])
        self.assertTrue(
            exact_link["reference_status"][
                "applies_to_atlas_reference_entity_only"
            ]
        )
        self.assertFalse(
            candidate["safeguards"][
                "spatial_relationship_is_identity_status_type_capacity_power_or_energy_claim"
            ]
        )
        self.assertEqual(
            coverage["atlas_reference_lane"]["exact_shared_osm_identity_links_in_shortlist"],
            1,
        )
        self.assertEqual(
            coverage["open_buildings_temporal_lane"]["candidate_aoi_overlap_links"],
            1,
        )

    def test_feature_collection_streams_canonical_features(self):
        document = {
            "features": [
                _primary("way/1", west=0, south=0, east=0.01, north=0.01),
                _primary("way/2", west=1, south=1, east=1.01, north=1.01),
            ],
            "name": "fixture",
            "review_only": True,
            "type": "FeatureCollection",
        }
        raw = json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "features.geojson"
            path.write_text(raw, encoding="utf-8")
            self.assertEqual(
                [feature["id"] for feature in _feature_collection(path)],
                ["way/1", "way/2"],
            )

    def test_rejected_analyst_control_is_not_elevated(self):
        candidates, coverage = _derive(
            [_primary("way/3", west=-0.01, south=-0.01, east=0.01, north=0.01)],
            atlas_features=[
                _atlas(
                    "osm-reference",
                    longitude=0.0,
                    latitude=0.0,
                    source_family="openstreetmap",
                    stable_key="osm:way/99",
                )
            ],
            overture_records=[],
            open_buildings=[],
            queue_by_entity={
                "osm-reference": [
                    {
                        "queue_id": "satq-rejected",
                        "entity_id": "osm-reference",
                        "aoi_bbox_wgs84": [-0.02, -0.02, 0.02, 0.02],
                        "priority_tier": "proposed_pipeline",
                    }
                ]
            },
            batch_states={"satq-rejected": {"state": "completed"}},
            analyst_reviews={
                "satq-rejected": {
                    "decision": "reject_automated_mask_for_site_promotion"
                }
            },
            atlas_max_distance_m=5_000,
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["review_priority"]["tier"],
            "shared_osm_root_or_queue_opportunity",
        )
        satellite = candidates[0]["evidence_opportunities"][
            "sentinel_queue_or_review"
        ]
        self.assertEqual(
            satellite[0]["analyst_review_outcome_class"],
            "rejected_for_site_promotion",
        )
        self.assertFalse(satellite[0]["analyst_retained_visible_change_candidate"])
        self.assertEqual(
            coverage["sentinel_lane"][
                "analyst_review_aoi_overlap_links_by_outcome"
            ],
            {"rejected_for_site_promotion": 1},
        )


if __name__ == "__main__":
    unittest.main()
