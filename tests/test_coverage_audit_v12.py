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
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v11.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v12.json"
FEDERATION_DEFINITION = (
    ROOT / "sources" / "federation-2026-07-19-public-open-v11.json"
)
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-19-public-open-v11"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v11"
RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v12"

PREVIOUS_DEFINITION_SHA256 = (
    "dfa4abdd17a2cdd0ce4b0b1a668db0d13d7d40d02bec1d862cf6b47a4faa3191"
)
DEFINITION_SHA256 = (
    "1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f"
)
PREVIOUS_MANIFEST_SHA256 = (
    "edf1b0cdf1e842b1ea8a848c1e07d0c5cb0860b34fe267798daeef0158a0ea2c"
)
MANIFEST_SHA256 = (
    "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
)
FEDERATION_DEFINITION_SHA256 = (
    "e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c"
)
FEDERATION_MANIFEST_SHA256 = (
    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
)
FEDERATION_INDEX_SHA256 = (
    "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)
OLD_FEDERATION_MANIFEST_SHA256 = (
    "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2"
)
OLD_FEDERATION_INDEX_SHA256 = (
    "aa6b55f29d237aa298cc6d2f3dfe5dfd57ed7bbd1ef6bd63688efd6be1e38251"
)
ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_148,
        "sha256": "498d41bef0f20b3ce95a4fa02d7beca5d3a0664a568c01b4324a3560a4983131",
    },
    "coverage-audit.json": {
        "bytes": 1_423_825,
        "sha256": "3a22822c84e48c55736317e50a3e1c1ca8dd1294624a78a43de41a5d8ea0cab7",
    },
    "coverage.csv": {
        "bytes": 195_237,
        "sha256": "ad7c40d85c92f993cdfd0f035bba64d836114517f20cd0d2cc52537acc5734f9",
    },
    "gap-registry.json": {
        "bytes": 1_242_499,
        "sha256": "8a192302603887895eb6d004a7d9e1693e6d18fd632bdb776a51196f09070f94",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v30"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v32"
PERMIT_EVIDENCE_IDS = {
    "435a7953-c5ef-5e7c-bb2d-1ad77b7230c9",
    "7db2bc34-1181-50d4-8cc5-9e943b7b2263",
    "928bbcd8-079d-5b85-a631-2477c6513a79",
    "ace70e8e-68ed-560f-a9e8-241aac11910b",
    "ad206c30-8e4c-569f-9edf-e8ba453378f9",
    "b133a4dc-126f-5e44-8841-f770b6fa9ad0",
    "cd9a0e24-c1f1-59e0-9234-031e6193dc0e",
}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


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


class FrozenPublicCoverageV12Tests(unittest.TestCase):
    def test_frozen_successor_reproduces_twice_offline_with_exact_v11_delta(
        self,
    ) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256(FEDERATION_DEFINITION.read_bytes()).hexdigest(),
            FEDERATION_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((FEDERATION_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            FEDERATION_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (FEDERATION_RELEASE / "federated-index.json").read_bytes()
            ).hexdigest(),
            FEDERATION_INDEX_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        expected_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        expected_definition["audit_id"] = "public-open-coverage-v12"
        expected_definition["generated_at"] = "2026-07-19T22:45:00Z"
        expected_definition["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-19-public-open-v11",
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
                "release_path": "../releases/2026-07-19-open-seed-v32",
            }
        )
        for reference in expected_definition["methodology_evidence_classification"][
            "permits"
        ]:
            self.assertEqual(reference["release_id"], OLD_OPEN_RELEASE_ID)
            reference["release_id"] = NEW_OPEN_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), _json_bytes(expected_definition))
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(definition["public_benchmark"], previous_definition["public_benchmark"])
        for field in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
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

        stale_federation_references = (
            b"public-open-v10",
            OLD_FEDERATION_MANIFEST_SHA256.encode(),
            OLD_FEDERATION_INDEX_SHA256.encode(),
        )
        for stale in stale_federation_references:
            self.assertNotIn(stale, DEFINITION.read_bytes())

        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "getaddrinfo",
            side_effect=AssertionError("offline build attempted DNS resolution"),
        ):
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            sealed = validate_coverage_audit(RELEASE, definition_path=DEFINITION)

        self.assertEqual(first, second)
        self.assertEqual(first.audit, sealed)
        self.assertEqual(set(first.payloads), {path.name for path in RELEASE.iterdir()})
        for filename, payload in first.payloads.items():
            self.assertEqual(payload, (RELEASE / filename).read_bytes())
            for stale in stale_federation_references:
                self.assertNotIn(stale, payload)
        self.assertEqual(first.manifest["artifacts"], ARTIFACTS)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )

        federation = json.loads(
            (FEDERATION_RELEASE / "federated-index.json").read_text()
        )
        self.assertEqual(
            federation["counts"],
            {
                "capacity_estimates": 1_187,
                "construction_pipeline_records": 6_445,
                "evidence_records": 13_239,
                "non_review_construction_pipeline_records": 315,
                "non_review_source_scoped_entity_records": 9_665,
                "release_bundles": 3,
                "resolution_candidates": 100_409,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_release_bundles": 1,
                "review_only_source_scoped_entity_records": 6_130,
                "source_family_entries": 98,
                "source_scoped_entity_records": 15_795,
                "unique_physical_sites": None,
            },
        )

        previous = json.loads((PREVIOUS_RELEASE / AUDIT_FILENAME).read_text())
        current = first.audit
        previous_gaps = json.loads(
            (PREVIOUS_RELEASE / GAP_REGISTRY_FILENAME).read_text()
        )
        current_gaps = first.gaps
        self.assertEqual(
            {
                field: current["totals"][field] - previous["totals"][field]
                for field in (
                    "advisory_resolution_candidate_records",
                    "non_review_source_scoped_entity_records",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                )
            },
            {
                "advisory_resolution_candidate_records": 0,
                "non_review_source_scoped_entity_records": 22,
                "review_only_source_scoped_entity_records": 0,
                "source_scoped_entity_records": 22,
            },
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
                "non_review_source_scoped_entity_records": 9_665,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_795,
                "unique_physical_sites": None,
            },
        )

        previous_fields = previous["totals"]["field_totals"]
        current_fields = current["totals"]["field_totals"]
        integer_deltas = {
            field: value - previous_fields[field]
            for field, value in current_fields.items()
            if isinstance(value, int) and value != previous_fields[field]
        }
        self.assertEqual(
            integer_deltas,
            {
                "complete_lifecycle_claim_rows": 11,
                "construction_evidence_observations": 8,
                "country_iso_a2_rows": 22,
                "country_iso_a3_rows": 22,
                "country_rows": 22,
                "informative_lifecycle_status_rows": 11,
                "lifecycle_status_rows": 11,
                "non_review_rows": 22,
                "non_review_under_construction_rows": 11,
                "pipeline_rows": 11,
                "pipeline_with_status_evidence_rows": 11,
                "source_scoped_rows": 22,
                "status_as_of_rows": 11,
                "status_evidence_rows": 11,
                "status_method_rows": 11,
                "under_construction_rows": 11,
                "under_construction_with_status_evidence_rows": 11,
                "unresolved_lifecycle_status_rows": 11,
            },
        )
        expected_counter_deltas = {
            "administrative_assignment_status_counts": {"source_label_only": 22},
            "non_review_source_declared_entity_kind_counts": {
                "campus": 11,
                "project": 11,
            },
            "pipeline_status_counts": {"under_construction": 11},
            "source_declared_entity_kind_counts": {"campus": 11, "project": 11},
            "status_counts": {"__MISSING__": 11, "under_construction": 11},
            "status_freshness_counts": {
                "0_90_days": 1,
                "366_plus_days": 2,
                "91_365_days": 8,
                "missing": 11,
            },
        }
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), expected)
            self.assertEqual(dict(old_counts - new_counts), {})
        self.assertEqual(current_fields["capacity_observations"], 1_187)
        self.assertEqual(current_fields["pipeline_rows"], 296)
        self.assertEqual(current_fields["operating_model_rows"], 275)
        self.assertEqual(current_fields["workload_rows"], 105)

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        previous_group_keys = set(previous_groups)
        current_group_keys = set(current_groups)
        self.assertEqual((len(previous_groups), len(current_groups)), (421, 441))
        self.assertLessEqual(previous_group_keys, current_group_keys)
        added_group_keys = current_group_keys - previous_group_keys
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 9, "release_source_country": 11},
        )
        self.assertEqual(
            {key[2] for key in added_group_keys},
            {
                "data4_csr_reports",
                "data4_location_pages",
                "equinix_sec_filings",
                "keppel_media",
                "larsen_toubro_press_releases",
                "servpac_press_releases",
                "telehouse_news",
                "uruguay_presidency_news",
                "vietnam_news_agency_vietnamplus",
                "viettel_official_linkedin",
            },
        )
        changed_common_groups = {
            key
            for key in previous_group_keys
            if _normalize_open_release_id(previous_groups[key])
            != _normalize_open_release_id(current_groups[key])
        }
        self.assertEqual(
            changed_common_groups,
            {
                (OLD_OPEN_RELEASE_ID, "release", "__ALL__", "__ALL__", None, None),
                (
                    OLD_OPEN_RELEASE_ID,
                    "release_source",
                    "equinix_sec_filings",
                    "__ALL__",
                    None,
                    None,
                ),
            },
        )
        release_group = current_groups[
            (OLD_OPEN_RELEASE_ID, "release", "__ALL__", "__ALL__", None, None)
        ]
        equinix_group = current_groups[
            (
                OLD_OPEN_RELEASE_ID,
                "release_source",
                "equinix_sec_filings",
                "__ALL__",
                None,
                None,
            )
        ]
        self.assertEqual(release_group["source_scoped_rows"], 370)
        self.assertEqual(equinix_group["source_scoped_rows"], 14)

        previous_gap_rows = {_gap_key(gap): gap for gap in previous_gaps["gaps"]}
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        previous_gap_keys = set(previous_gap_rows)
        current_gap_keys = set(current_gap_rows)
        self.assertLessEqual(previous_gap_keys, current_gap_keys)
        added_gap_keys = current_gap_keys - previous_gap_keys
        self.assertEqual(len(added_gap_keys), 103)
        self.assertEqual(
            Counter(key[4] for key in added_gap_keys),
            {
                "annual_energy": 11,
                "capacity": 11,
                "coordinates": 11,
                "informative_lifecycle_status": 11,
                "lifecycle_status": 11,
                "operating_model": 11,
                "source_scoped_rows": 2,
                "status_as_of": 11,
                "status_evidence": 11,
                "status_stale_366_plus_days": 2,
                "workload": 11,
            },
        )
        self.assertEqual(
            Counter(key[0] for key in added_gap_keys),
            {"release_source": 2, "release_source_country": 101},
        )
        for key in previous_gap_keys:
            self.assertEqual(
                _normalized_gap(current_gap_rows[key]),
                _normalized_gap(previous_gap_rows[key]),
            )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_411,
                "by_severity": {
                    "high": 121,
                    "info": 17,
                    "low": 1_386,
                    "medium": 887,
                },
                "by_field": {
                    "annual_energy": 332,
                    "capacity": 321,
                    "coordinates": 111,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 321,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 151,
                    "operating_model": 339,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 17,
                    "status_as_of": 151,
                    "status_evidence": 151,
                    "status_stale_366_plus_days": 170,
                    "unique_physical_sites": 1,
                    "workload": 331,
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
        for field in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
            self.assertEqual(
                evidence_methodology[field]["status"],
                "absent_from_audited_children",
            )
            self.assertEqual(evidence_methodology[field]["evidence_reference_count"], 0)
        self.assertEqual(
            evidence_methodology["power_data"]["capacity_observation_count"], 1_187
        )
        self.assertEqual(
            evidence_methodology["power_data"][
                "capacity_observations_with_resolved_evidence"
            ],
            1_187,
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
        report = (RELEASE / "REPORT.md").read_text()
        self.assertIn("not a facility census", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_successor_fails_closed_on_wrong_pins_file_set_symlink_and_mode(
        self,
    ) -> None:
        definition = json.loads(DEFINITION.read_text())
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
            (extra_copy / "unexpected.txt").write_text("unexpected\n")
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
