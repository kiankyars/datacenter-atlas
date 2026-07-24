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
    ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v14.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v17.json"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v18.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v18"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v42.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v42"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v14"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v17"

PREVIOUS_DEFINITION_SHA256 = (
    "94b237d4432278ac7e275a612f730fc9962ae580763f0da4c088568f19669874"
)
DEFINITION_SHA256 = (
    "964926e8432b4bf83233201c07cad0c40dc2fc34d9d4b1f89cd871f51c461f3d"
)
PREVIOUS_MANIFEST_SHA256 = (
    "76fddae15de10e4efba3b5b8b17e788d09b119beb381e6013b3ec33fa19e0fd5"
)
MANIFEST_SHA256 = (
    "37807873e8dc0009d31b1a1eb8d4d6cc4dd2dceb88a1ab52076c166e37f04755"
)
MANIFEST_HASH_SHA256 = (
    "562794ef41c62fe7f9e6bf0d623e3b06732d51f9554749079e9004c0a5c3c867"
)
FEDERATION_DEFINITION_SHA256 = (
    "bab7ae5e2f09e34d658663112c70b88ac3ca3b02a075380356cfe3f7af7298d0"
)
FEDERATION_MANIFEST_SHA256 = (
    "3f52b09facdaa5bbea82bbef045e459901a6f3206452271482d0ea798a7f28d6"
)
FEDERATION_INDEX_SHA256 = (
    "45048828bf4cc90e1c70fd0da86962c5a0bc0a00d588ad8c3f22e35e2597f6df"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680"
)

ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_149,
        "sha256": "932ef21bc38ea7aab527e789f43e8c5dde0bb801025c6ecd81c536f3095f036d",
    },
    "coverage-audit.json": {
        "bytes": 1_698_003,
        "sha256": "925abb9218e11a31a423348cb3ba29b722e98aa844d23f04e68569251faa9cf7",
    },
    "coverage.csv": {
        "bytes": 233_992,
        "sha256": "826380bb2249030efa6442987b172b18f3312a2b047126214afdd134ecb92093",
    },
    "gap-registry.json": {
        "bytes": 1_469_682,
        "sha256": "3203d7cce86aa72475f2b1a706e5f836ab70bff5523550b2cd535e75e0efd2f3",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v39"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v42"
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
    "cirion_company_blog",
    "cirion_pressroom",
    "equinix_newsroom",
    "equinix_sec_filings",
    "iron_mountain_data_center_location_pages",
    "iron_mountain_resources",
    "iron_mountain_sec_filings",
    "stc_sustainability_reports",
}
TOTALS_SHA256 = (
    "16e58412a2cdacd09b7591d7ba11eaa17853bf16b089971953f6c5da9db57597"
)
FIELD_TOTALS_SHA256 = (
    "69aeb81ad4b864c521c5e5d8839b8aeaef085920423ba89840b75d3097e0ce0d"
)
INTEGER_DELTAS_SHA256 = (
    "8e6ceabceb8a9cea8b928b3f5837a5fec1cd7f62738546dd898877b8d72ac1a1"
)
ADDED_GROUP_KEYS_SHA256 = (
    "9102b56c0ac63f09de6c697093d737bb72d683ea428e1e0ce579ba25cd0b3302"
)
ADDED_GROUPS_SHA256 = (
    "77b3293f811047230abc6e4773ec9a5df178f1ee152a3beadd21616f94818526"
)
REMOVED_GROUP_KEYS_SHA256 = (
    "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
)
CHANGED_GROUP_KEYS_SHA256 = (
    "6497c2c374cb3872212a268e25096ef25791c7de53e3065d3e2940a0806415e3"
)
CHANGED_GROUPS_SHA256 = (
    "ddb865a57e69408ff62224379347de1587b79341d8bea9aa589d1469f47f5de5"
)
ADDED_GAP_KEYS_SHA256 = (
    "4c526386a9efbcf66b4f7d7f86b0dda4e8cf2c3729a9828c9e2a9d141a836993"
)
ADDED_GAPS_SHA256 = (
    "ec8109ba8ae8dfb31db2ef61acc3ab3fbdabf026d0bd9cdee7fc5f8ba8d2fbeb"
)
REMOVED_GAP_KEYS_SHA256 = (
    "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
)
CHANGED_GAP_KEYS_SHA256 = (
    "9cf73d4d7d33be12afce004df2470e4dce2ac43c72b10cdcff6efa07104b05f4"
)
CHANGED_GAPS_SHA256 = (
    "a94cc81808760bc137189e2d8be7dc57711e8b66a70e35f037bab76c1250c107"
)
GAP_SUMMARY_SHA256 = (
    "fb4805ce89989427c3e753c58a3bcfa3277848dfb24957fb73fa79f7193067f6"
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


class FrozenPublicCoverageV17Tests(unittest.TestCase):
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
        expected_definition["audit_id"] = "public-open-coverage-v17"
        expected_definition["generated_at"] = "2026-07-20T05:30:00Z"
        expected_definition["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v18",
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
                "release_path": "../releases/2026-07-20-open-seed-v42",
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
        self.assertEqual(
            definition["children"][1:], previous_definition["children"][1:]
        )
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

        open_definition = json.loads(OPEN_SEED_DEFINITION.read_text(encoding="utf-8"))
        open_manifest = json.loads(
            (OPEN_SEED_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        federation = json.loads(
            (FEDERATION_RELEASE / "federated-index.json").read_text(encoding="utf-8")
        )
        federation_child = next(
            child for child in federation["releases"] if child["release_id"] == NEW_OPEN_RELEASE_ID
        )
        contract_markers = (
            open_definition["publication_contract_version"],
            open_definition["expected_release"]["publication_contract_version"],
            open_manifest["publication_contract_version"],
            federation_child["manifest"]["publication_contract_version"],
        )
        for marker in contract_markers:
            self.assertIs(type(marker), int)
            self.assertEqual(marker, 4)

        stale_references = (
            b"epoch-official-open-seed-v39",
            b"2026-07-20-open-seed-v39",
            b"../federated_indexes/2026-07-20-public-open-v15",
            b"e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84",
            b"739dc3b1e33878bda97de8e99286a9cdfe0d80a9a3d758358f671da5b81daa0c",
            b"epoch-official-open-seed-v41",
            b"2026-07-20-open-seed-v41",
            b"../federated_indexes/2026-07-20-public-open-v16",
            b"../federated_indexes/2026-07-20-public-open-v17",
            b"e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
            b"dff68953b205cc2cc27553bddf50a8b3e7bc11ed02e7af028c98500df0d94ae9",
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
        self.assertEqual(first.manifest["artifacts"], ARTIFACTS)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.sha256").read_bytes()).hexdigest(),
            MANIFEST_HASH_SHA256,
        )
        self.assertEqual(
            federation["counts"],
            {
                "capacity_estimates": 1_213,
                "construction_pipeline_records": 6_512,
                "evidence_records": 13_286,
                "non_review_construction_pipeline_records": 382,
                "non_review_source_scoped_entity_records": 9_797,
                "release_bundles": 3,
                "resolution_candidates": 100_409,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_release_bundles": 1,
                "review_only_source_scoped_entity_records": 6_130,
                "source_family_entries": 130,
                "source_scoped_entity_records": 15_927,
                "unique_physical_sites": None,
            },
        )

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_exact_v14_delta_groups_gaps_and_scope_guardrails(self) -> None:
        previous = json.loads((PREVIOUS_RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        previous_gaps = json.loads(
            (PREVIOUS_RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        current_gaps = json.loads(
            (RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )

        self.assertEqual(_canonical_hash(current["totals"]), TOTALS_SHA256)
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
                "non_review_source_scoped_entity_records": 9_797,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_927,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            current["totals"]["source_scoped_entity_records"]
            - previous["totals"]["source_scoped_entity_records"],
            91,
        )
        self.assertEqual(
            current["totals"]["non_review_source_scoped_entity_records"]
            - previous["totals"]["non_review_source_scoped_entity_records"],
            91,
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
                "capacity_entity_rows": 9,
                "capacity_observations": 9,
                "capacity_observations_with_evidence": 9,
                "capacity_observations_with_resolved_evidence": 9,
                "complete_lifecycle_claim_rows": 51,
                "construction_evidence_observations": 8,
                "country_iso_a2_rows": 91,
                "country_iso_a3_rows": 91,
                "country_rows": 91,
                "informative_lifecycle_status_rows": 51,
                "lifecycle_status_rows": 51,
                "non_review_rows": 91,
                "non_review_under_construction_rows": 47,
                "operating_model_evidence_rows": 7,
                "operating_model_resolved_evidence_rows": 7,
                "operating_model_rows": 7,
                "pipeline_rows": 47,
                "pipeline_with_status_evidence_rows": 47,
                "source_scoped_rows": 91,
                "status_as_of_rows": 51,
                "status_evidence_rows": 51,
                "status_method_rows": 51,
                "under_construction_rows": 47,
                "under_construction_with_status_evidence_rows": 47,
                "unresolved_lifecycle_status_rows": 40,
            },
        )
        self.assertEqual(_canonical_hash(integer_deltas), INTEGER_DELTAS_SHA256)

        expected_counter_deltas = {
            "administrative_assignment_status_counts": {"source_label_only": 91},
            "capacity_confidence_counts": {"0.99": 9},
            "capacity_method_counts": {"reported": 9},
            "capacity_metric_counts": {"critical_it_mw": 9},
            "capacity_stage_counts": {"planned": 9},
            "non_review_source_declared_entity_kind_counts": {"campus": 43, "project": 48},
            "operating_model_counts": {"colocation": 7},
            "pipeline_status_counts": {"under_construction": 47},
            "source_declared_entity_kind_counts": {"campus": 43, "project": 48},
            "status_counts": {"__MISSING__": 40, "operational": 4, "under_construction": 47},
            "status_freshness_counts": {
                "0_90_days": 5,
                "91_365_days": 42,
                "366_plus_days": 4,
                "missing": 40,
            },
        }
        changed_counter_fields = {
            field
            for field, value in current_fields.items()
            if isinstance(value, dict) and value != previous_fields[field]
        }
        self.assertEqual(changed_counter_fields, set(expected_counter_deltas))
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), expected)
            self.assertEqual(dict(old_counts - new_counts), {})

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        added_group_keys = sorted(set(current_groups) - set(previous_groups), key=repr)
        removed_group_keys = sorted(set(previous_groups) - set(current_groups), key=repr)
        changed_group_keys = sorted(
            (
                key
                for key in set(previous_groups) & set(current_groups)
                if _normalized_group(previous_groups[key])
                != _normalized_group(current_groups[key])
            ),
            key=repr,
        )
        self.assertEqual((len(previous_groups), len(current_groups)), (490, 526))
        self.assertEqual((len(added_group_keys), len(removed_group_keys)), (36, 0))
        self.assertEqual(526, 490 + len(added_group_keys) - len(removed_group_keys))
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 6, "release_source_country": 30},
        )
        self.assertEqual({key[2] for key in added_group_keys}, ADDED_SOURCE_FAMILIES)
        self.assertEqual(removed_group_keys, [])
        self.assertEqual(len(changed_group_keys), 7)
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
        self.assertEqual(
            _canonical_hash([list(key) for key in removed_group_keys]),
            REMOVED_GROUP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash([list(key) for key in changed_group_keys]),
            CHANGED_GROUP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_group(current_groups[key]) for key in changed_group_keys]
            ),
            CHANGED_GROUPS_SHA256,
        )

        previous_gap_rows = {_gap_key(gap): gap for gap in previous_gaps["gaps"]}
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        added_gap_keys = sorted(set(current_gap_rows) - set(previous_gap_rows), key=repr)
        removed_gap_keys = sorted(set(previous_gap_rows) - set(current_gap_rows), key=repr)
        changed_gap_keys = sorted(
            (
                key
                for key in set(previous_gap_rows) & set(current_gap_rows)
                if _normalized_gap(previous_gap_rows[key])
                != _normalized_gap(current_gap_rows[key])
            ),
            key=repr,
        )
        self.assertEqual((len(previous_gap_rows), len(current_gap_rows)), (2_605, 2_845))
        self.assertEqual((len(added_gap_keys), len(removed_gap_keys)), (240, 0))
        self.assertEqual(2_845, 2_605 + len(added_gap_keys) - len(removed_gap_keys))
        self.assertEqual(
            Counter(key[0] for key in added_gap_keys),
            {"release_source": 1, "release_source_country": 239},
        )
        self.assertEqual({key[2] for key in added_gap_keys}, ADDED_SOURCE_FAMILIES)
        self.assertEqual(removed_gap_keys, [])
        self.assertEqual(len(changed_gap_keys), 27)
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
        self.assertEqual(
            _canonical_hash([list(key) for key in removed_gap_keys]),
            REMOVED_GAP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash([list(key) for key in changed_gap_keys]),
            CHANGED_GAP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_gap(current_gap_rows[key]) for key in changed_gap_keys]
            ),
            CHANGED_GAPS_SHA256,
        )

        expected_gap_summary = {
            "open_gaps": 2_845,
            "by_severity": {"high": 174, "info": 22, "low": 1_586, "medium": 1_063},
            "by_field": {
                "annual_energy": 385,
                "capacity": 365,
                "coordinates": 164,
                "country": 3,
                "country_iso_a2": 5,
                "informative_lifecycle_status": 364,
                "licensed_row_level_benchmark": 1,
                "lifecycle_status": 194,
                "operating_model": 389,
                "parity": 1,
                "semianalysis_public_capacity_outputs": 1,
                "semianalysis_public_construction_timeline_pjm": 1,
                "semianalysis_public_evidence_methodology": 1,
                "semianalysis_public_facility_scope_count": 1,
                "semianalysis_public_temporal_granularity": 1,
                "source_scoped_rows": 22,
                "status_as_of": 194,
                "status_evidence": 194,
                "status_stale_366_plus_days": 174,
                "unique_physical_sites": 1,
                "workload": 384,
            },
        }
        self.assertEqual(current_gaps["summary"], expected_gap_summary)
        self.assertEqual(sum(current_gaps["summary"]["by_severity"].values()), 2_845)
        self.assertEqual(sum(current_gaps["summary"]["by_field"].values()), 2_845)
        self.assertEqual(_canonical_hash(current_gaps["summary"]), GAP_SUMMARY_SHA256)

        comparison = current["semianalysis_public_comparison"]
        previous_comparison = previous["semianalysis_public_comparison"]
        self.assertEqual(comparison["benchmark"], previous_comparison["benchmark"])
        self.assertEqual(
            comparison["licensed_row_level_benchmark"],
            previous_comparison["licensed_row_level_benchmark"],
        )
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
        self.assertEqual(evidence_methodology["power_data"]["capacity_observation_count"], 1_213)

        scope = current["scope"]
        self.assertFalse(scope["children_merged"])
        self.assertFalse(scope["cross_source_deduplication"])
        self.assertFalse(scope["review_candidates_promoted"])
        self.assertFalse(scope["candidate_rows_counted_as_facilities"])
        self.assertIsNone(scope["confirmed_duplicate_relationships"])
        self.assertIsNone(scope["unique_physical_sites"])
        self.assertEqual(current["totals"]["unique_physical_sites"], None)
        self.assertEqual(
            current["inputs"]["federated_index"]["manifest"]["sha256"],
            FEDERATION_MANIFEST_SHA256,
        )
        self.assertEqual(
            current["inputs"]["federated_index"]["index"]["sha256"],
            FEDERATION_INDEX_SHA256,
        )
        current_open_child = next(
            child
            for child in current["inputs"]["children"]
            if child["release_id"] == NEW_OPEN_RELEASE_ID
        )
        marker = current_open_child["manifest"]["publication_contract_version"]
        self.assertIs(type(marker), int)
        self.assertEqual(marker, 4)

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
        self.assertIn("Unique physical sites: **unknown**", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

    def test_successor_fails_closed_on_wrong_pins_and_tamper(self) -> None:
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

            tampered_copy = root / "tampered-copy"
            shutil.copytree(RELEASE, tampered_copy)
            tampered_copy.chmod(0o755)
            report = tampered_copy / "REPORT.md"
            report.chmod(0o644)
            report.write_bytes(report.read_bytes() + b"tampered\n")
            with self.assertRaisesRegex(CoverageAuditError, "artifact checkpoint mismatch"):
                validate_coverage_audit(tampered_copy)


if __name__ == "__main__":
    unittest.main()
