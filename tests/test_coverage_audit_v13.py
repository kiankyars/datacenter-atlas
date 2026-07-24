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
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v12.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v13.json"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-19-public-open-v12.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-19-public-open-v12"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v33.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v12"
RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v13"

PREVIOUS_DEFINITION_SHA256 = (
    "1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f"
)
DEFINITION_SHA256 = (
    "2745fd688f2727dc954b733386a00fbe8cf00401e5aeec4a451528c6d0bc9d9e"
)
PREVIOUS_MANIFEST_SHA256 = (
    "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
)
MANIFEST_SHA256 = (
    "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d"
)
MANIFEST_HASH_SHA256 = (
    "35a1c1c6d72a3b1383bf657cd0cfbebd022e7fceb9170b12d75b2dd266bdc291"
)
FEDERATION_DEFINITION_SHA256 = (
    "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
)
FEDERATION_MANIFEST_SHA256 = (
    "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
)
FEDERATION_INDEX_SHA256 = (
    "266afde03fbb9eca16a0a9bfbd64c47fd50447b1b805da15542ff617f1629772"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)
OLD_FEDERATION_MANIFEST_SHA256 = (
    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
)
OLD_FEDERATION_INDEX_SHA256 = (
    "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd"
)
OLD_OPEN_SEED_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)

ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_148,
        "sha256": "49e96fab8de950fe25fd49dc08844572eb77958cf834c5171ccfb963f8e8f2cb",
    },
    "coverage-audit.json": {
        "bytes": 1_449_755,
        "sha256": "a162ce7a329ed9cd332bd15b059415375becd9bfc61e951b9e863b7ad1f463eb",
    },
    "coverage.csv": {
        "bytes": 198_943,
        "sha256": "dadd88b3433ef54ca3f3a0fc023a8bd0f7f596fd87f94d248c0645c6cae16a83",
    },
    "gap-registry.json": {
        "bytes": 1_260_625,
        "sha256": "8e3f91982dbff020e9f5591194de2154a391042853e45263d52beded7f536785",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v32"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v33"
PERMIT_EVIDENCE_IDS = {
    "435a7953-c5ef-5e7c-bb2d-1ad77b7230c9",
    "7db2bc34-1181-50d4-8cc5-9e943b7b2263",
    "928bbcd8-079d-5b85-a631-2477c6513a79",
    "ace70e8e-68ed-560f-a9e8-241aac11910b",
    "ad206c30-8e4c-569f-9edf-e8ba453378f9",
    "b133a4dc-126f-5e44-8841-f770b6fa9ad0",
    "cd9a0e24-c1f1-59e0-9234-031e6193dc0e",
}
NEW_SOURCE_FAMILIES = {
    "adani_connect_magazine",
    "csc_news_and_blog",
    "esr_newsroom",
    "srv_cision_press_releases",
}

ADDED_GROUP_HASHES = {
    (
        OLD_OPEN_RELEASE_ID,
        "release_source",
        "adani_connect_magazine",
        "__ALL__",
        None,
        None,
    ): "09497243fd08c62e315e3b18c973bf7af33bfe322ba0a03627c4b48c725545a9",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source",
        "csc_news_and_blog",
        "__ALL__",
        None,
        None,
    ): "8574bab231b923dedc55ddfc78adbd87be88bc5a2e4ada311b8a8a0c5f4c90e0",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source",
        "esr_newsroom",
        "__ALL__",
        None,
        None,
    ): "8f27cf3c115b339bf586bd44980edd54d6c5dab3ce84a9b4cf8aa06b18196599",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source",
        "srv_cision_press_releases",
        "__ALL__",
        None,
        None,
    ): "89cf1d2df1e377ebff5a09ece7cedfa9be744e830618ee1b62f09e415b16750a",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source_country",
        "adani_connect_magazine",
        "India",
        "IN",
        "IND",
    ): "4368ce1954353027535142aee3b82c0ad70a86e856b0c3f27991e3fd814f66b3",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source_country",
        "csc_news_and_blog",
        "Finland",
        "FI",
        "FIN",
    ): "254a53a29ffe25bb4f92e1753d1f4dd886e65b1994482c88ad1d5d7fb4ca0db3",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source_country",
        "esr_newsroom",
        "Japan",
        "JP",
        "JPN",
    ): "decd9811cf690bbab0a3a0c52df31512540ad465e70b2e3c6d555f2ff60dbcc1",
    (
        OLD_OPEN_RELEASE_ID,
        "release_source_country",
        "srv_cision_press_releases",
        "Finland",
        "FI",
        "FIN",
    ): "499cda3d03d3fa4273135f035aaf96a663980bfc3245b5df414fe466c80fdc5e",
}
OPEN_RELEASE_GROUP_SHA256 = (
    "d0db8547cb92a2bfadfb1f54d906e998aa442b4ade29d6090c187c2c4c9ab9b0"
)
FIELD_TOTALS_SHA256 = (
    "54f3d7785ab55a56d888a070133e1bf9054c24b74014a35bbf914f87cb9df14e"
)
ADDED_GAP_KEYS_SHA256 = (
    "7842071adb25dc7159e7fb2d918b5b6ba164960e173e4bb65fb3039d88217ff6"
)
ADDED_GAPS_SHA256 = (
    "fa173958e11b0b461bcab8f4bb200c945f96168866e82630b422c09a79b4ac26"
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


class FrozenPublicCoverageV13Tests(unittest.TestCase):
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
        expected_definition["audit_id"] = "public-open-coverage-v13"
        expected_definition["generated_at"] = "2026-07-19T23:59:45Z"
        expected_definition["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-19-public-open-v12",
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
                "release_path": "../releases/2026-07-19-open-seed-v33",
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
            b"public-open-v11",
            b"open-seed-v32",
            OLD_FEDERATION_MANIFEST_SHA256.encode(),
            OLD_FEDERATION_INDEX_SHA256.encode(),
            OLD_OPEN_SEED_MANIFEST_SHA256.encode(),
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
        self.assertEqual(hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(), MANIFEST_SHA256)
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
                "capacity_estimates": 1_189,
                "construction_pipeline_records": 6_449,
                "evidence_records": 13_243,
                "non_review_construction_pipeline_records": 319,
                "non_review_source_scoped_entity_records": 9_673,
                "release_bundles": 3,
                "resolution_candidates": 100_409,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_release_bundles": 1,
                "review_only_source_scoped_entity_records": 6_130,
                "source_family_entries": 102,
                "source_scoped_entity_records": 15_803,
                "unique_physical_sites": None,
            },
        )

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_normalized_groups_gaps_and_methodology_have_exact_v12_delta(self) -> None:
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
                "non_review_source_scoped_entity_records": 9_673,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_803,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            current["totals"]["source_scoped_entity_records"]
            - previous["totals"]["source_scoped_entity_records"],
            8,
        )
        self.assertEqual(
            current["totals"]["non_review_source_scoped_entity_records"]
            - previous["totals"]["non_review_source_scoped_entity_records"],
            8,
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
                "capacity_entity_rows": 2,
                "capacity_observations": 2,
                "capacity_observations_with_evidence": 2,
                "capacity_observations_with_resolved_evidence": 2,
                "complete_lifecycle_claim_rows": 4,
                "construction_evidence_observations": 3,
                "country_iso_a2_rows": 8,
                "country_iso_a3_rows": 8,
                "country_rows": 8,
                "informative_lifecycle_status_rows": 4,
                "lifecycle_status_rows": 4,
                "non_review_rows": 8,
                "non_review_under_construction_rows": 3,
                "pipeline_rows": 3,
                "pipeline_with_status_evidence_rows": 3,
                "source_scoped_rows": 8,
                "status_as_of_rows": 4,
                "status_evidence_rows": 4,
                "status_method_rows": 4,
                "under_construction_rows": 3,
                "under_construction_with_status_evidence_rows": 3,
                "unresolved_lifecycle_status_rows": 4,
            },
        )
        expected_counter_deltas = {
            "administrative_assignment_status_counts": {"source_label_only": 8},
            "capacity_confidence_counts": {"0.99": 2},
            "capacity_method_counts": {"reported": 2},
            "capacity_metric_counts": {"gross_facility_mw": 2},
            "capacity_stage_counts": {"planned": 2},
            "non_review_source_declared_entity_kind_counts": {"campus": 4, "project": 4},
            "pipeline_status_counts": {"under_construction": 3},
            "source_declared_entity_kind_counts": {"campus": 4, "project": 4},
            "status_counts": {"__MISSING__": 4, "site_preparation": 1, "under_construction": 3},
            "status_freshness_counts": {"0_90_days": 1, "91_365_days": 3, "missing": 4},
        }
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), expected)
            self.assertEqual(dict(old_counts - new_counts), {})
        self.assertEqual(current_fields["capacity_observations"], 1_189)
        self.assertEqual(current_fields["pipeline_rows"], 299)
        self.assertEqual(current_fields["operating_model_rows"], 275)
        self.assertEqual(current_fields["workload_rows"], 105)

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        previous_group_keys = set(previous_groups)
        current_group_keys = set(current_groups)
        self.assertEqual((len(previous_groups), len(current_groups)), (441, 449))
        self.assertLessEqual(previous_group_keys, current_group_keys)
        added_group_keys = current_group_keys - previous_group_keys
        self.assertEqual(added_group_keys, set(ADDED_GROUP_HASHES))
        self.assertEqual(
            {
                key: _canonical_hash(_normalize_open_release_id(current_groups[key]))
                for key in added_group_keys
            },
            ADDED_GROUP_HASHES,
        )
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 4, "release_source_country": 4},
        )
        self.assertEqual({key[2] for key in added_group_keys}, NEW_SOURCE_FAMILIES)
        changed_common_groups = {
            key
            for key in previous_group_keys
            if _normalize_open_release_id(previous_groups[key])
            != _normalize_open_release_id(current_groups[key])
        }
        release_group_key = (
            OLD_OPEN_RELEASE_ID,
            "release",
            "__ALL__",
            "__ALL__",
            None,
            None,
        )
        self.assertEqual(changed_common_groups, {release_group_key})
        self.assertEqual(
            _canonical_hash(
                _normalize_open_release_id(current_groups[release_group_key])
            ),
            OPEN_RELEASE_GROUP_SHA256,
        )

        previous_gap_rows = {_gap_key(gap): gap for gap in previous_gaps["gaps"]}
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        previous_gap_keys = set(previous_gap_rows)
        current_gap_keys = set(current_gap_rows)
        self.assertLessEqual(previous_gap_keys, current_gap_keys)
        for key in previous_gap_keys:
            self.assertEqual(
                _normalized_gap(current_gap_rows[key]),
                _normalized_gap(previous_gap_rows[key]),
            )
        added_gap_keys = current_gap_keys - previous_gap_keys
        self.assertEqual(len(added_gap_keys), 35)
        ordered_added_keys = sorted(added_gap_keys, key=repr)
        self.assertEqual(
            _canonical_hash([list(key) for key in ordered_added_keys]),
            ADDED_GAP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_gap(current_gap_rows[key]) for key in ordered_added_keys]
            ),
            ADDED_GAPS_SHA256,
        )
        self.assertEqual(Counter(key[0] for key in added_gap_keys), {"release_source_country": 35})
        self.assertEqual(
            Counter(key[4] for key in added_gap_keys),
            {
                "annual_energy": 4,
                "capacity": 3,
                "coordinates": 4,
                "informative_lifecycle_status": 4,
                "lifecycle_status": 4,
                "operating_model": 4,
                "status_as_of": 4,
                "status_evidence": 4,
                "workload": 4,
            },
        )
        self.assertEqual(
            Counter(key[2] for key in added_gap_keys),
            {
                "adani_connect_magazine": 9,
                "csc_news_and_blog": 9,
                "esr_newsroom": 8,
                "srv_cision_press_releases": 9,
            },
        )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_446,
                "by_severity": {"high": 125, "info": 17, "low": 1_401, "medium": 903},
                "by_field": {
                    "annual_energy": 336,
                    "capacity": 324,
                    "coordinates": 115,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 325,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 155,
                    "operating_model": 343,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 17,
                    "status_as_of": 155,
                    "status_evidence": 155,
                    "status_stale_366_plus_days": 170,
                    "unique_physical_sites": 1,
                    "workload": 335,
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
        self.assertEqual(permits["evidence_reference_count"], 7)
        self.assertEqual(set(permits["evidence_ids"]), PERMIT_EVIDENCE_IDS)
        self.assertEqual(permits["release_ids"], [NEW_OPEN_RELEASE_ID])
        self.assertEqual(
            permits["source_families"],
            [
                "environment_agency_permit_application_supporting_document",
                "finnish_municipal_data_center_updates",
                "independence_mo_monthly_building_permit_reports",
                "indiana_idem_air_permit",
                "north_carolina_deq_air_permit_public_notice",
                "north_dakota_deq_air_quality_records",
                "wisconsin_dnr_environmental_review_pages",
            ],
        )
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(evidence_methodology[field]["status"], "absent_from_audited_children")
            self.assertEqual(evidence_methodology[field]["evidence_reference_count"], 0)
        self.assertEqual(evidence_methodology["power_data"]["capacity_observation_count"], 1_189)
        self.assertEqual(
            evidence_methodology["power_data"][
                "capacity_observations_with_resolved_evidence"
            ],
            1_189,
        )

        self.assertEqual(current["scope"], previous["scope"])
        self.assertFalse(current["scope"]["children_merged"])
        self.assertFalse(current["scope"]["cross_source_deduplication"])
        self.assertFalse(current["scope"]["review_candidates_promoted"])
        self.assertIsNone(current["scope"]["confirmed_duplicate_relationships"])
        self.assertIsNone(current["scope"]["unique_physical_sites"])
        self.assertEqual(
            current["inputs"]["federated_index"]["manifest"]["sha256"],
            FEDERATION_MANIFEST_SHA256,
        )
        self.assertEqual(
            current["inputs"]["federated_index"]["index"]["sha256"],
            FEDERATION_INDEX_SHA256,
        )
        report = (RELEASE / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("not a facility census", report)
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
