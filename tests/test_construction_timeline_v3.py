from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_timeline_v3 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v3.json"
)
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v3"
V2_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-20-public-open-v2.json"
)
V2_BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v2"
V67_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V67_RELEASE = ROOT / "releases/2026-07-21-open-seed-v67"

DEFINITION_PIN = (
    2_838,
    "698648dda386a00e62247a4fdaf1aaf83ca2bc62f865ea366c5f51da2813d055",
)
MANIFEST_SHA256 = (
    "4dc0c03968d2b3b07db225df3b3388ebabaeedb3ecb4f1ca0e3996a4e5070d20"
)
BUNDLE_TREE_SHA256 = (
    "4b8bf25f4177bdeeacb87a17836060de225172db73731a2e73a192ce78ce773a"
)

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        26_071,
        "d7988dda4f011f73bb1f089e825a3165407184a0d6150cd9c779f2379f08c5e9",
    ),
    "README.md": (
        1_405,
        "bb58f53295fa6bfd3a7c72df658dada1164f0e4adba0355ff6e3fb7b89fdbd1d",
    ),
    "coverage.json": (
        72_215,
        "6fbe901557f1f872c668c76f4f668d1548b9f2fc9c25509bab0aad4ba01b01c8",
    ),
    "entity-timelines.jsonl": (
        695_024,
        "6b7e7c4619ad65671d49e4e63ae6cf276403cff0b04761f51eea28108b1c9fad",
    ),
    "lifecycle-observations.csv": (
        307_759,
        "ccebbfd243c9cdf2eb1c9ef1d52b9f03018137a7056c0770ff4143e02d058780",
    ),
    "manifest.json": (3_794, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "6839ec8e15fad1ac3ae4f6a038f6b85715ec174def3179a5a94ad48707c55f14",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v3.py": (
        67_780,
        "78735896a390f2cab9ba039d30968076f2eeac65f737686c8e3e0bc6dfb65e85",
    ),
    ROOT / "construction_timeline_v3.py": (
        2_463,
        "d9b9384b1f81c1ad6084a89208c725dbd00fbe1d7373f0bd3aa62d28d077b1da",
    ),
    ROOT / "scripts/build_construction_timeline_v3.py": (
        697,
        "3d13bff57112216f8c281c458f32305fc81f07d02bc861ae4e1dc343484f1c1a",
    ),
}

V2_PINS = {
    V2_DEFINITION: (
        1_672,
        "ca48de509f23a0ba0b856bab8815a1872594840e0a83cf9dba09c37133b5909a",
    ),
    V2_BUNDLE / "manifest.json": (
        2_560,
        "ab8e798b1b0d2d25ec43744e935565603f8ce138d7d820038ad838702b3b28a7",
    ),
    ROOT / "datacenter_atlas/construction_timeline_v2.py": (
        10_763,
        "6950de8cd16d141cefecb95ef20c3535d346207f98768bd3925b427b4dc412ff",
    ),
}

V67_PINS = {
    V67_DEFINITION: (
        83_386,
        "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5",
    ),
    V67_RELEASE / "manifest.json": (
        12_274,
        "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb",
    ),
    ROOT / "datacenter_atlas/open_seed_v67.py": (
        53_678,
        "3bdba3404182bed32f5491826d027344d2b9d4cea01ef9670cb8ffa44bc67259",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV3Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v3 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_definition_bundle_input_and_code_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V2_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V67_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for pins in (V2_PINS, V67_PINS, CODE_PINS):
            for path, expected in pins.items():
                self.assertEqual((path.stat().st_size, sha256(path)), expected)

    def test_parent_and_nested_import_carriers_export_every_consumed_symbol(self) -> None:
        import datacenter_atlas.construction_timeline_v3 as selected

        consumed = {
            "AS_OF",
            "BUNDLE_FILES",
            "ConstructionTimelineError",
            "DELTA_CONTRACT",
            "EXPECTED_COUNTS",
            "INTERMEDIATE_PROJECT_SOURCE_BY_KEY",
            "NEW_TRANCHE_PROJECT_SOURCE_BY_KEY",
            "OBSERVATIONS_FILENAME",
            "OPEN_SEED_TREE_SHA256",
            "PREDECESSOR_TREE_SHA256",
            "TIMELINES_FILENAME",
            "TIMELINE_FORMAT",
            "TIMELINE_SCHEMA_VERSION",
            "V67_ADDITION_EVENT_CONTRACT",
            "V67_INTERMEDIATE_EVENT_CONTRACT",
            "V67_NEW_TRANCHE_EVENT_CONTRACT",
            "_canonical_json",
            "_event_documents",
            "_load_definition",
            "_parse_csv",
            "_parse_jsonl",
            "_prepare_payloads",
            "validate_construction_timeline_bundle",
            "write_construction_timeline_bundle",
        }
        self.assertTrue(consumed <= set(dir(selected)))
        self.assertEqual(selected.EXPECTED_COUNTS, timeline.EXPECTED_COUNTS)
        self.assertEqual(selected.DELTA_CONTRACT, timeline.DELTA_CONTRACT)
        self.assertEqual(
            selected.V67_ADDITION_EVENT_CONTRACT,
            timeline.V67_ADDITION_EVENT_CONTRACT,
        )

    def test_exact_v2_rows_and_timelines_are_preserved(self) -> None:
        predecessor = timeline._parse_csv(V2_BUNDLE / timeline.OBSERVATIONS_FILENAME)
        current = timeline._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        self.assertEqual((len(predecessor), len(current)), (430, 459))
        current_by_id = {row["observation_id"]: row for row in current}
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
        predecessor_timelines = timeline._parse_jsonl(
            V2_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (415, 443))
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        for row in predecessor_timelines:
            self.assertEqual(current_by_key[row["entity_stable_key"]], row)
        self.assertTrue(
            all(
                row["format"] == timeline.TIMELINE_FORMAT
                and row["schema_version"] == timeline.TIMELINE_SCHEMA_VERSION
                for row in current_timelines
            )
        )

    def test_two_post_v62_partitions_are_complete_disjoint_and_exact(self) -> None:
        predecessor = timeline._parse_csv(V2_BUNDLE / timeline.OBSERVATIONS_FILENAME)
        current = timeline._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        added = [row for row in current if row["observation_id"] not in predecessor_ids]
        intermediate_ids = {
            event[2] for event in timeline.V67_INTERMEDIATE_EVENT_CONTRACT
        }
        new_tranche_ids = {
            event[2] for event in timeline.V67_NEW_TRANCHE_EVENT_CONTRACT
        }
        added_ids = {row["observation_id"] for row in added}
        self.assertEqual((len(added), len(added_ids)), (29, 29))
        self.assertFalse(intermediate_ids & new_tranche_ids)
        self.assertEqual(added_ids, intermediate_ids | new_tranche_ids)
        self.assertEqual(len(intermediate_ids), 14)
        self.assertEqual(len(new_tranche_ids), 15)
        self.assertEqual(
            len({row["entity_stable_key"] for row in added}),
            28,
        )
        by_key = Counter(row["entity_stable_key"] for row in added)
        self.assertEqual(set(by_key), set(timeline.PROJECT_SOURCE_BY_KEY))
        self.assertEqual(sorted(by_key.values()), [1] * 27 + [2])
        self.assertEqual(
            next(key for key, count in by_key.items() if count == 2),
            "curated:smplus-smx01-jakarta-cbd:initial-18mw-build",
        )
        self.assertEqual(
            timeline.DELTA_CONTRACT,
            {
                "full_v67_raw_lifecycle_observations": 459,
                "inherited_observations": 430,
                "inherited_timelines": 415,
                "intermediate_lifecycle_observations": 14,
                "intermediate_project_entities": 14,
                "new_tranche_lifecycle_observations": 15,
                "new_tranche_project_entities": 14,
                "post_v62_lifecycle_observations": 29,
                "post_v62_project_entities": 28,
                "recorded_at_values_preserved_from_v2": True,
                "v67_recorded_at_rewrites_ignored": 46,
            },
        )

    def test_exact_source_evidence_date_status_and_age_contracts(self) -> None:
        events = timeline._event_documents()
        self.assertEqual(len(events), 29)
        self.assertEqual(
            len(timeline._event_documents(timeline.V67_INTERMEDIATE_EVENT_CONTRACT)),
            14,
        )
        self.assertEqual(
            len(timeline._event_documents(timeline.V67_NEW_TRANCHE_EVENT_CONTRACT)),
            15,
        )
        as_of = date.fromisoformat(timeline.AS_OF)
        for event in events:
            age = (as_of - date.fromisoformat(event["observed_date"])).days
            self.assertEqual(event["observation_age_days"], age)
            expected_class = (
                "recent_0_90_days"
                if age <= 90
                else "aging_91_365_days"
                if age <= 365
                else "stale_over_365_days"
            )
            self.assertEqual(event["freshness_class"], expected_class)
            self.assertEqual(
                event["source_path"],
                timeline.PROJECT_SOURCE_BY_KEY[event["entity_stable_key"]],
            )
            self.assertEqual(len(event["evidence_content_hash"]), 64)
            self.assertTrue(event["evidence_id"])
            self.assertTrue(event["evidence_source_family"])
            self.assertEqual(event["status_semantics"], "last_observed")
            self.assertEqual(event["current_status_classification"], "unknown")
            self.assertFalse(event["current_construction_claim"])
            self.assertFalse(event["latest_observation_persistence_assumed"])

    def test_stt_is_stale_historical_only_and_never_current(self) -> None:
        coverage = json.loads(
            (BUNDLE / timeline.COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        stt = coverage["stt_johor_historical_only"]
        self.assertEqual(
            stt["entity_stable_key"],
            "curated:stt-johor-data-centre-campus:stt-johor-1",
        )
        self.assertEqual(stt["observed_date"], "2025-02-24")
        self.assertEqual(stt["status"], "under_construction")
        self.assertEqual(stt["observation_age_days"], 512)
        self.assertEqual(stt["freshness_class"], "stale_over_365_days")
        self.assertEqual(stt["status_semantics"], "last_observed")
        self.assertEqual(stt["current_status_classification"], "unknown")
        self.assertFalse(stt["current_construction_claim"])
        self.assertFalse(stt["latest_observation_persistence_assumed"])

    def test_counts_statuses_freshness_and_noninference_scope_are_exact(self) -> None:
        coverage = json.loads(
            (BUNDLE / timeline.COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["observation_entity_kind_counts"], {
            "campus": 83,
            "project": 376,
        })
        self.assertEqual(coverage["timeline_entity_kind_counts"], {
            "campus": 83,
            "project": 360,
        })
        self.assertEqual(coverage["observation_status_counts"], {
            "announced": 6,
            "civil_works": 3,
            "commissioning": 2,
            "expansion": 29,
            "foundations": 2,
            "mep_electrical": 19,
            "operational": 42,
            "permitted": 3,
            "proposed": 2,
            "shell": 29,
            "site_control": 1,
            "site_preparation": 13,
            "under_construction": 308,
        })
        self.assertEqual(coverage["intermediate_addition_freshness_counts"], {
            "aging_91_365_days": 8,
            "recent_0_90_days": 6,
        })
        self.assertEqual(coverage["v67_new_tranche_freshness_counts"], {
            "aging_91_365_days": 6,
            "recent_0_90_days": 6,
            "stale_over_365_days": 3,
        })
        self.assertEqual(coverage["v67_addition_freshness_counts"], {
            "aging_91_365_days": 14,
            "recent_0_90_days": 12,
            "stale_over_365_days": 3,
        })
        self.assertEqual(coverage["current_status_classification_counts"], {
            "unknown": 443,
        })
        for field in (
            "cross_source_identity_resolution_applied",
            "current_construction_claimed",
            "forecast_conversion_applied",
            "interpolation_applied",
            "latest_observation_persistence_assumed",
            "permit_or_forecast_promoted_to_physical_construction",
            "quarterly_2017_2032_parity_claimed",
            "satellite_cv_promoted_to_lifecycle",
        ):
            self.assertFalse(coverage["scope"][field], field)
        self.assertEqual(coverage["scope"]["latest_status_semantics"], "last_observed")
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        timelines = timeline._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        for row in timelines:
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertFalse(row["current_construction_claim"])
            self.assertFalse(row["latest_observation_persistence_assumed"])

    def test_offline_exact_replay_and_internal_double_rebuild(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            validated = timeline.validate_construction_timeline_bundle(
                BUNDLE,
                definition_path=DEFINITION,
                verify_inputs=True,
            )
            self.assertEqual(validated["counts"], timeline.EXPECTED_COUNTS)
            with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
                output = Path(temporary) / "timeline-v3"
                rebuilt = timeline.write_construction_timeline_bundle(
                    DEFINITION, output
                )
                self.assertEqual(rebuilt, validated)
                self.assertEqual(tree_digest(output), BUNDLE_TREE_SHA256)

    def test_collision_tamper_symlink_and_corrected_definition_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_path = Path(temporary)
            collision = temporary_path / "collision"
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_text("preserve\n", encoding="utf-8")
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "refusing overwrite"
            ):
                timeline.write_construction_timeline_bundle(DEFINITION, collision)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")

            tampered = temporary_path / "tampered"
            shutil.copytree(BUNDLE, tampered)
            tampered.chmod(0o755)
            target = tampered / timeline.OBSERVATIONS_FILENAME
            target.chmod(0o644)
            target.write_bytes(target.read_bytes().replace(b"shell", b"shelL", 1))
            for path in tampered.iterdir():
                path.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "checkpoint differs"
            ):
                timeline.validate_construction_timeline_bundle(tampered)

            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            self.assertEqual(document["expected"]["raw_lifecycle_observations"], 459)
            self.assertEqual(document["expected"]["entities_with_lifecycle_observations"], 443)
            document["delta"]["intermediate_lifecycle_observations"] = 0
            altered_definition = temporary_path / DEFINITION.name
            altered_definition.write_bytes(timeline._canonical_json(document))
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "definition contract differs"
            ):
                timeline._load_definition(altered_definition)

            linked_bundle = temporary_path / "linked-bundle"
            os.symlink(BUNDLE, linked_bundle)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "ordinary directory"
            ):
                timeline.validate_construction_timeline_bundle(linked_bundle)
            linked_definition = temporary_path / "linked-definition.json"
            os.symlink(DEFINITION, linked_definition)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "ordinary file"
            ):
                timeline._load_definition(linked_definition)


if __name__ == "__main__":
    unittest.main()
