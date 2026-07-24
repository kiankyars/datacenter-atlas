from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    CoverageAuditError,
    build_coverage_audit,
    validate_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v13.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v14.json"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v15.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v15"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v39.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v39"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v13"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v14"

PREVIOUS_DEFINITION_SHA256 = (
    "2745fd688f2727dc954b733386a00fbe8cf00401e5aeec4a451528c6d0bc9d9e"
)
DEFINITION_SHA256 = (
    "94b237d4432278ac7e275a612f730fc9962ae580763f0da4c088568f19669874"
)
PREVIOUS_MANIFEST_SHA256 = (
    "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d"
)
MANIFEST_SHA256 = (
    "76fddae15de10e4efba3b5b8b17e788d09b119beb381e6013b3ec33fa19e0fd5"
)
MANIFEST_HASH_SHA256 = (
    "4302213be9102452cd3fbefdb653a9bd277f4dbd80046939b0bbe57091b13b60"
)
FEDERATION_DEFINITION_SHA256 = (
    "52023873cb067e4ab4278ca7acc53a4277894634e882801914bd571fabe07da7"
)
FEDERATION_MANIFEST_SHA256 = (
    "739dc3b1e33878bda97de8e99286a9cdfe0d80a9a3d758358f671da5b81daa0c"
)
FEDERATION_INDEX_SHA256 = (
    "d03f67aa9ff219a8de573d5d8137c28a2f8c3c0eea32f42498b9efd20c5c6166"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "2b0b219e94e98782f58128ea7db9c9b954e44d0694f33cc17e7807a71e6ef381"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84"
)
OLD_FEDERATION_MANIFEST_SHA256 = (
    "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
)
OLD_OPEN_SEED_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)

ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_148,
        "sha256": "c92d6a225590e70d088f16673fd2e37fc852eb1257775655dffaad4f5eb1b7b4",
    },
    "coverage-audit.json": {
        "bytes": 1_582_260,
        "sha256": "9004ba53362b5beba75cf45f30dac48fd75dbd7c572fad95c128eb296a511311",
    },
    "coverage.csv": {
        "bytes": 217_299,
        "sha256": "a3dea3c115589c40d4f60bf0fc1984ff60af316f5a7f1fb953fdb21d822f52f0",
    },
    "gap-registry.json": {
        "bytes": 1_344_167,
        "sha256": "1afdd26d4488ab106b314ac70c7104fe0cd5c66e974e59ef37336b6b3f7fc5ec",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v33"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v39"
PERMIT_EVIDENCE_IDS = {
    "435a7953-c5ef-5e7c-bb2d-1ad77b7230c9",
    "7db2bc34-1181-50d4-8cc5-9e943b7b2263",
    "928bbcd8-079d-5b85-a631-2477c6513a79",
    "ace70e8e-68ed-560f-a9e8-241aac11910b",
    "ad206c30-8e4c-569f-9edf-e8ba453378f9",
    "b133a4dc-126f-5e44-8841-f770b6fa9ad0",
    "cd9a0e24-c1f1-59e0-9234-031e6193dc0e",
}
ADDED_SOURCE_FAMILIES = {
    "atnorth_newsroom",
    "cipher_digital_sec_exhibits",
    "cipher_digital_sec_filings",
    "cipher_sec_exhibits",
    "cipher_sec_investor_presentations",
    "core_scientific_sec_exhibits",
    "digital_edge_indonesia_newsroom",
    "green_data_center_facility_pages",
    "green_mountain_project_pages",
    "iij_investor_relations",
    "iij_press_releases",
    "kouvola_city_news",
    "loviisa_city_news",
    "macquarie_data_centres_facility_pages",
    "macquarie_data_centres_newsroom",
    "macquarie_data_centres_specifications",
    "merlin_properties_asset_pages",
    "merlin_properties_press_releases",
    "metsahallitus_press_releases",
    "moro_hub_news",
    "softbank_news",
    "softbank_sustainability",
}
FIELD_TOTALS_SHA256 = (
    "977adcc3bc7585ebc8f403bf739d09659887fd6ad74909f12c9b80a175807c7e"
)
ADDED_GROUP_KEYS_SHA256 = (
    "ae8b17625ab5a20cee27aeaffb9cc84e3ba0fdf1dc79bd1dac6c66a5caf6c82e"
)
ADDED_GROUPS_SHA256 = (
    "f6a753abb4c72d4269d1179f087222647072d6560690c417895c7479c90838cf"
)
ADDED_GAP_KEYS_SHA256 = (
    "b653ec051d90ad022df73dc1ed7d06acc7d1dd92153891ea5a58519de1271139"
)
ADDED_GAPS_SHA256 = (
    "7228dd13a7c2b5f00fb9e60a7dd1a48d154025f7f3fb9f1067c4e8d61f3d3fc0"
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _canonical_hash(value: object) -> str:
    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_open_release_id(value: object) -> object:
    if isinstance(value, dict):
        return {key: _normalize_open_release_id(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_open_release_id(item) for item in value]
    if value == NEW_OPEN_RELEASE_ID:
        return OLD_OPEN_RELEASE_ID
    return value


def _group_key(group: dict[str, object]) -> tuple[object, ...]:
    normalized = _normalize_open_release_id(group)
    assert isinstance(normalized, dict)
    return (
        normalized["child_release"],
        normalized["scope_type"],
        normalized["source_family"],
        normalized["country"],
        normalized["country_iso_a2"],
        normalized["country_iso_a3"],
    )


def _normalized_group(group: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_open_release_id(group)
    assert isinstance(normalized, dict)
    return normalized


def _gap_key(gap: dict[str, object]) -> tuple[object, ...]:
    normalized = _normalize_open_release_id(gap)
    assert isinstance(normalized, dict)
    return (
        normalized["scope_type"],
        normalized["child_release"],
        normalized["source_family"],
        normalized["country"],
        normalized["field"],
    )


def _normalized_gap(gap: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_open_release_id(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


def _require_frozen_modes(directory: Path) -> None:
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise CoverageAuditError("release directory mode must be 0555")
    for path in directory.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CoverageAuditError("release file mode must be 0444")


class FrozenPublicCoverageV14Tests(unittest.TestCase):
    def test_frozen_successor_reproduces_twice_offline_with_live_pins(self) -> None:
        pins = {
            PREVIOUS_DEFINITION: PREVIOUS_DEFINITION_SHA256,
            DEFINITION: DEFINITION_SHA256,
            FEDERATION_DEFINITION: FEDERATION_DEFINITION_SHA256,
            FEDERATION_RELEASE / "manifest.json": FEDERATION_MANIFEST_SHA256,
            FEDERATION_RELEASE / "federated-index.json": FEDERATION_INDEX_SHA256,
            OPEN_SEED_DEFINITION: OPEN_SEED_DEFINITION_SHA256,
            OPEN_SEED_RELEASE / "manifest.json": OPEN_SEED_MANIFEST_SHA256,
            PREVIOUS_RELEASE / "manifest.json": PREVIOUS_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        expected_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        expected_definition["audit_id"] = "public-open-coverage-v14"
        expected_definition["generated_at"] = "2026-07-20T02:45:00Z"
        expected_definition["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v15",
        }
        open_child = next(
            child
            for child in expected_definition["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v39",
            }
        )
        for reference in expected_definition["methodology_evidence_classification"][
            "permits"
        ]:
            self.assertEqual(reference["release_id"], OLD_OPEN_RELEASE_ID)
            reference["release_id"] = NEW_OPEN_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), _json_bytes(expected_definition))
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["public_benchmark"], previous_definition["public_benchmark"])
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(definition["methodology_evidence_classification"][field], [])
        self.assertEqual(
            {
                reference["evidence_id"]
                for reference in definition["methodology_evidence_classification"][
                    "permits"
                ]
            },
            PERMIT_EVIDENCE_IDS,
        )

        stale_references = (
            b"open-seed-v33",
            b"2026-07-19-public-open-v12",
            OLD_FEDERATION_MANIFEST_SHA256.encode(),
            OLD_OPEN_SEED_MANIFEST_SHA256.encode(),
            b"2026-07-20-open-seed-v35",
            b"2026-07-20-public-open-v13",
        )
        for stale in stale_references:
            self.assertNotIn(stale, DEFINITION.read_bytes())

        offline = AssertionError("offline build attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            first_sealed = validate_coverage_audit(RELEASE, definition_path=DEFINITION)
            second_sealed = validate_coverage_audit(RELEASE, definition_path=DEFINITION)

        self.assertEqual(first, second)
        self.assertEqual(first.audit, first_sealed)
        self.assertEqual(first_sealed, second_sealed)
        self.assertEqual(set(first.payloads), {path.name for path in RELEASE.iterdir()})
        for filename, payload in first.payloads.items():
            self.assertEqual(payload, (RELEASE / filename).read_bytes())
            for stale in stale_references:
                self.assertNotIn(stale, payload)
        self.assertEqual(first.manifest["artifacts"], ARTIFACTS)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.sha256").read_bytes()).hexdigest(),
            MANIFEST_HASH_SHA256,
        )

        federation = json.loads(
            (FEDERATION_RELEASE / "federated-index.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            federation["counts"],
            {
                "capacity_estimates": 1_204,
                "construction_pipeline_records": 6_465,
                "evidence_records": 13_266,
                "non_review_construction_pipeline_records": 335,
                "non_review_source_scoped_entity_records": 9_706,
                "release_bundles": 3,
                "resolution_candidates": 100_409,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_release_bundles": 1,
                "review_only_source_scoped_entity_records": 6_130,
                "source_family_entries": 124,
                "source_scoped_entity_records": 15_836,
                "unique_physical_sites": None,
            },
        )

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_exact_v13_delta_and_scope_guardrails(self) -> None:
        previous = json.loads((PREVIOUS_RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        previous_gaps = json.loads(
            (PREVIOUS_RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        current_gaps = json.loads(
            (RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                key: current["totals"][key]
                for key in (
                    "advisory_resolution_candidate_records",
                    "non_review_source_scoped_entity_records",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                    "unique_physical_sites",
                )
            },
            {
                "advisory_resolution_candidate_records": 100_409,
                "non_review_source_scoped_entity_records": 9_706,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_836,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            current["totals"]["source_scoped_entity_records"]
            - previous["totals"]["source_scoped_entity_records"],
            33,
        )
        self.assertEqual(
            current["totals"]["non_review_source_scoped_entity_records"]
            - previous["totals"]["non_review_source_scoped_entity_records"],
            33,
        )
        self.assertEqual(
            current["totals"]["review_only_source_scoped_entity_records"],
            previous["totals"]["review_only_source_scoped_entity_records"],
        )
        self.assertEqual(
            current["totals"]["advisory_resolution_candidate_records"],
            previous["totals"]["advisory_resolution_candidate_records"],
        )

        previous_fields = previous["totals"]["field_totals"]
        current_fields = current["totals"]["field_totals"]
        self.assertEqual(_canonical_hash(current_fields), FIELD_TOTALS_SHA256)
        integer_deltas = {
            field: value - previous_fields[field]
            for field, value in current_fields.items()
            if isinstance(value, int) and value != previous_fields[field]
        }
        self.assertEqual(
            integer_deltas,
            {
                "capacity_entity_rows": 10,
                "capacity_observations": 15,
                "capacity_observations_with_evidence": 15,
                "capacity_observations_with_resolved_evidence": 15,
                "complete_lifecycle_claim_rows": 16,
                "construction_evidence_observations": 13,
                "country_iso_a2_rows": 33,
                "country_iso_a3_rows": 33,
                "country_rows": 33,
                "informative_lifecycle_status_rows": 16,
                "lifecycle_status_rows": 16,
                "non_review_rows": 33,
                "non_review_under_construction_rows": 13,
                "pipeline_rows": 13,
                "pipeline_with_status_evidence_rows": 13,
                "source_scoped_rows": 33,
                "status_as_of_rows": 16,
                "status_evidence_rows": 16,
                "status_method_rows": 16,
                "under_construction_rows": 13,
                "under_construction_with_status_evidence_rows": 13,
                "unresolved_lifecycle_status_rows": 17,
                "workload_observations": 1,
                "workload_observations_with_evidence": 1,
                "workload_observations_with_resolved_evidence": 1,
                "workload_rows": 1,
            },
        )
        expected_counter_deltas = {
            "administrative_assignment_status_counts": {"source_label_only": 33},
            "capacity_confidence_counts": {"0.95": 1, "0.98": 1, "0.99": 13},
            "capacity_method_counts": {"calculated": 1, "reported": 14},
            "capacity_metric_counts": {
                "critical_it_mw": 7,
                "grid_connection_mw": 2,
                "gross_facility_mw": 4,
                "pue": 2,
            },
            "capacity_stage_counts": {"design": 2, "planned": 13},
            "non_review_source_declared_entity_kind_counts": {"campus": 15, "project": 18},
            "pipeline_status_counts": {"under_construction": 13},
            "source_declared_entity_kind_counts": {"campus": 15, "project": 18},
            "status_counts": {
                "__MISSING__": 17,
                "shell": 2,
                "site_preparation": 1,
                "under_construction": 13,
            },
            "workload_counts": {"ai_specialized_unspecified": 1},
        }
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), expected)
            self.assertEqual(dict(old_counts - new_counts), {})
        self.assertEqual(
            current_fields["status_freshness_counts"],
            {
                "0_90_days": 1_603,
                "366_plus_days": 7_947,
                "91_365_days": 3_766,
                "missing": 2_520,
            },
        )

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        self.assertEqual((len(previous_groups), len(current_groups)), (449, 490))
        self.assertLessEqual(set(previous_groups), set(current_groups))
        added_group_keys = sorted(set(current_groups) - set(previous_groups), key=repr)
        self.assertEqual(len(added_group_keys), 41)
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 22, "release_source_country": 19},
        )
        self.assertEqual({key[2] for key in added_group_keys}, ADDED_SOURCE_FAMILIES)
        self.assertEqual(
            _canonical_hash([list(key) for key in added_group_keys]),
            ADDED_GROUP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_group(current_groups[key]) for key in added_group_keys]
            ),
            ADDED_GROUPS_SHA256,
        )

        previous_gap_rows = {_gap_key(gap): gap for gap in previous_gaps["gaps"]}
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        self.assertLessEqual(set(previous_gap_rows), set(current_gap_rows))
        added_gap_keys = sorted(set(current_gap_rows) - set(previous_gap_rows), key=repr)
        self.assertEqual(len(added_gap_keys), 159)
        self.assertEqual(
            Counter(key[0] for key in added_gap_keys),
            {"release_source": 4, "release_source_country": 155},
        )
        self.assertEqual({key[2] for key in added_gap_keys}, ADDED_SOURCE_FAMILIES)
        self.assertEqual(
            _canonical_hash([list(key) for key in added_gap_keys]),
            ADDED_GAP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_gap(current_gap_rows[key]) for key in added_gap_keys]
            ),
            ADDED_GAPS_SHA256,
        )
        changed_common_gap_keys = {
            key
            for key in previous_gap_rows
            if _normalized_gap(previous_gap_rows[key])
            != _normalized_gap(current_gap_rows[key])
        }
        stale_gap_key = (
            "release_source_country",
            "osm-fuzzy-review-v2",
            "openstreetmap:fuzzy_discovery",
            "United Kingdom",
            "status_stale_366_plus_days",
        )
        self.assertEqual(changed_common_gap_keys, {stale_gap_key})
        self.assertEqual(
            current_gap_rows[stale_gap_key]["affected_records"],
            previous_gap_rows[stale_gap_key]["affected_records"] + 1,
        )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_605,
                "by_severity": {"high": 144, "info": 21, "low": 1_472, "medium": 968},
                "by_field": {
                    "annual_energy": 355,
                    "capacity": 338,
                    "coordinates": 134,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 341,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 171,
                    "operating_model": 362,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 21,
                    "status_as_of": 171,
                    "status_evidence": 171,
                    "status_stale_366_plus_days": 171,
                    "unique_physical_sites": 1,
                    "workload": 354,
                },
            },
        )

        comparison = current["semianalysis_public_comparison"]
        previous_comparison = previous["semianalysis_public_comparison"]
        self.assertEqual(comparison["benchmark"], previous_comparison["benchmark"])
        self.assertEqual(
            comparison["licensed_row_level_benchmark"],
            previous_comparison["licensed_row_level_benchmark"],
        )
        self.assertEqual(comparison["overall_parity"], previous_comparison["overall_parity"])
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        self.assertTrue(
            all(item["parity_status"] == "pending" for item in comparison["comparisons"])
        )
        evidence_methodology = next(
            item
            for item in comparison["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        permits = evidence_methodology["permits"]
        self.assertEqual(permits["status"], "permitting_process_evidence_present")
        self.assertEqual(permits["evidence_reference_count"], 7)
        self.assertEqual(set(permits["evidence_ids"]), PERMIT_EVIDENCE_IDS)
        self.assertEqual(permits["release_ids"], [NEW_OPEN_RELEASE_ID])
        self.assertEqual(
            permits["scope_guardrail"],
            "References document permitting processes only; classification does not "
            "assert a granted permit, project approval, or physical construction.",
        )
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(evidence_methodology[field]["status"], "absent_from_audited_children")
            self.assertEqual(evidence_methodology[field]["evidence_reference_count"], 0)
        self.assertEqual(evidence_methodology["power_data"]["capacity_observation_count"], 1_204)

        scope = current["scope"]
        self.assertFalse(scope["children_merged"])
        self.assertFalse(scope["cross_source_deduplication"])
        self.assertFalse(scope["review_candidates_promoted"])
        self.assertFalse(scope["candidate_rows_counted_as_facilities"])
        self.assertIsNone(scope["confirmed_duplicate_relationships"])
        self.assertIsNone(scope["unique_physical_sites"])
        self.assertEqual(
            current["inputs"]["federated_index"]["manifest"]["sha256"],
            FEDERATION_MANIFEST_SHA256,
        )
        self.assertEqual(
            current["inputs"]["federated_index"]["index"]["sha256"],
            FEDERATION_INDEX_SHA256,
        )

        capacity_counts = current_fields["capacity_metric_counts"]
        self.assertEqual(sum(capacity_counts.values()), current_fields["capacity_observations"])
        self.assertNotIn("capacity_base_totals", current_fields)
        self.assertNotIn("capacity_totals", current_fields)
        open_summary = json.loads(
            (OPEN_SEED_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            open_summary["capacity_aggregation"],
            {
                "base_totals_published": False,
                "cross_entity_sum_valid": False,
                "reason": "Capacity rows can be nested, component-scoped, superseding, "
                "or metric-distinct. Arithmetic sums are not valid facility, site, "
                "load, energy, or unique-physical-site totals.",
                "scope": "typed_source_observation_rows",
            },
        )
        report = (RELEASE / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("not a facility census", report)
        self.assertIn("evidence observations, not sites", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

    def test_successor_fails_closed_on_wrong_pins_file_set_symlink_and_mode(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        definition_root = DEFINITION.parent
        definition["federated_index"]["path"] = str(
            (definition_root / definition["federated_index"]["path"]).resolve()
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (definition_root / child["release_path"]).resolve()
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in ("federation", "child"):
                with self.subTest(case=case):
                    mutated = json.loads(json.dumps(definition))
                    if case == "federation":
                        mutated["federated_index"]["expected_manifest_sha256"] = "0" * 64
                        pattern = "federated index manifest SHA-256"
                    else:
                        open_child = next(
                            child
                            for child in mutated["children"]
                            if child["release_id"] == NEW_OPEN_RELEASE_ID
                        )
                        open_child["expected_manifest_sha256"] = "0" * 64
                        pattern = "manifest SHA-256 does not match audit definition"
                    path = root / f"wrong-{case}.json"
                    path.write_bytes(_json_bytes(mutated))
                    with self.assertRaisesRegex(CoverageAuditError, pattern):
                        build_coverage_audit(path)

            extra_copy = root / "extra-copy"
            shutil.copytree(RELEASE, extra_copy)
            extra_copy.chmod(0o755)
            (extra_copy / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(CoverageAuditError, "file set is invalid"):
                validate_coverage_audit(extra_copy)

            symlink_copy = root / "symlink-copy"
            shutil.copytree(RELEASE, symlink_copy)
            symlink_copy.chmod(0o755)
            report = symlink_copy / "REPORT.md"
            report.chmod(0o644)
            report.unlink()
            report.symlink_to(RELEASE / "REPORT.md")
            with self.assertRaisesRegex(CoverageAuditError, "regular file"):
                validate_coverage_audit(symlink_copy)

            mode_copy = root / "mode-copy"
            shutil.copytree(RELEASE, mode_copy)
            mode_copy.chmod(0o755)
            with self.assertRaisesRegex(CoverageAuditError, "mode must be 0555"):
                _require_frozen_modes(mode_copy)


if __name__ == "__main__":
    unittest.main()
