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
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v10.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v11.json"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v10"
RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v11"

PREVIOUS_DEFINITION_SHA256 = (
    "17dbc93024e49a9a12af31452c4c97a7c521e612472462031fe3a76deb817eee"
)
DEFINITION_SHA256 = (
    "dfa4abdd17a2cdd0ce4b0b1a668db0d13d7d40d02bec1d862cf6b47a4faa3191"
)
PREVIOUS_MANIFEST_SHA256 = (
    "ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e"
)
MANIFEST_SHA256 = (
    "edf1b0cdf1e842b1ea8a848c1e07d0c5cb0860b34fe267798daeef0158a0ea2c"
)
FEDERATION_MANIFEST_SHA256 = (
    "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2"
)
FEDERATION_INDEX_SHA256 = (
    "aa6b55f29d237aa298cc6d2f3dfe5dfd57ed7bbd1ef6bd63688efd6be1e38251"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
)
ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_148,
        "sha256": "f6c7f509281652724d059501b7c977b1d7da0679d37aa5150dfe7a66241aa930",
    },
    "coverage-audit.json": {
        "bytes": 1_359_961,
        "sha256": "0e82e7c3c6ad6e104bb065d4ae7661eeeb15ba1df749ce8680f1f36ec1afadd9",
    },
    "coverage.csv": {
        "bytes": 186_546,
        "sha256": "24e89d3970cf35e3b7766a091f987f6e21788e77e5e7ede6124835c5983c8eab",
    },
    "gap-registry.json": {
        "bytes": 1_188_834,
        "sha256": "e716069e79aedffdad81b7a98ce3bca57dfb01a712cc250b9e5e54e4046b1b6a",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v20"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v30"
ADDED_PERMIT_EVIDENCE_IDS = {
    "ace70e8e-68ed-560f-a9e8-241aac11910b",
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


class FrozenPublicCoverageV11Tests(unittest.TestCase):
    def test_frozen_successor_reproduces_twice_offline_with_exact_v10_delta(
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
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

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
        self.assertEqual(first.manifest["artifacts"], ARTIFACTS)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )

        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(definition["public_benchmark"], previous_definition["public_benchmark"])
        self.assertEqual(
            definition["federated_index"],
            {
                "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-19-public-open-v10",
            },
        )
        previous_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        children = {child["release_id"]: child for child in definition["children"]}
        self.assertEqual(
            set(children),
            (set(previous_children) - {OLD_OPEN_RELEASE_ID}) | {NEW_OPEN_RELEASE_ID},
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(children[release_id], previous_children[release_id])
        self.assertEqual(
            children[NEW_OPEN_RELEASE_ID],
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-19-open-seed-v30",
            },
        )

        previous_methodology = previous_definition["methodology_evidence_classification"]
        methodology = _normalize_open_release_id(
            definition["methodology_evidence_classification"]
        )
        assert isinstance(methodology, dict)
        permits = [
            reference
            for reference in methodology["permits"]
            if reference["evidence_id"] not in ADDED_PERMIT_EVIDENCE_IDS
        ]
        self.assertEqual(
            {**methodology, "permits": permits},
            previous_methodology,
        )
        self.assertEqual(
            {
                reference["evidence_id"]
                for reference in methodology["permits"]
                if reference["evidence_id"] in ADDED_PERMIT_EVIDENCE_IDS
            },
            ADDED_PERMIT_EVIDENCE_IDS,
        )
        for field in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
            self.assertEqual(definition["methodology_evidence_classification"][field], [])

        previous = json.loads((PREVIOUS_RELEASE / AUDIT_FILENAME).read_text())
        current = first.audit
        previous_gaps = json.loads(
            (PREVIOUS_RELEASE / GAP_REGISTRY_FILENAME).read_text()
        )
        current_gaps = first.gaps

        expected_total_deltas = {
            "advisory_resolution_candidate_records": 0,
            "non_review_source_scoped_entity_records": 66,
            "review_only_source_scoped_entity_records": 0,
            "source_scoped_entity_records": 66,
        }
        self.assertEqual(
            {
                field: current["totals"][field] - previous["totals"][field]
                for field in expected_total_deltas
            },
            expected_total_deltas,
        )
        self.assertEqual(
            {
                "source_scoped_entity_records": current["totals"][
                    "source_scoped_entity_records"
                ],
                "non_review_source_scoped_entity_records": current["totals"][
                    "non_review_source_scoped_entity_records"
                ],
                "review_only_source_scoped_entity_records": current["totals"][
                    "review_only_source_scoped_entity_records"
                ],
                "advisory_resolution_candidate_records": current["totals"][
                    "advisory_resolution_candidate_records"
                ],
            },
            {
                "source_scoped_entity_records": 15_773,
                "non_review_source_scoped_entity_records": 9_643,
                "review_only_source_scoped_entity_records": 6_130,
                "advisory_resolution_candidate_records": 100_409,
            },
        )

        previous_fields = previous["totals"]["field_totals"]
        current_fields = current["totals"]["field_totals"]
        expected_field_deltas = {
            "capacity_entity_rows": 8,
            "capacity_observations": 9,
            "complete_lifecycle_claim_rows": 33,
            "construction_evidence_observations": 25,
            "coordinate_rows": 2,
            "country_rows": 66,
            "informative_lifecycle_status_rows": 33,
            "lifecycle_status_rows": 33,
            "non_review_under_construction_rows": 29,
            "operating_model_rows": 0,
            "pipeline_rows": 30,
            "source_scoped_rows": 66,
            "status_as_of_rows": 33,
            "status_evidence_rows": 33,
            "under_construction_rows": 29,
            "unresolved_lifecycle_status_rows": 33,
            "workload_rows": 5,
        }
        self.assertEqual(
            {
                field: current_fields[field] - previous_fields[field]
                for field in expected_field_deltas
            },
            expected_field_deltas,
        )
        expected_counter_deltas = {
            "capacity_metric_counts": {
                "critical_it_mw": 6,
                "generation_nameplate_mw": 1,
                "grid_connection_mw": 2,
            },
            "capacity_stage_counts": {"contracted": 2, "planned": 7},
            "non_review_source_declared_entity_kind_counts": {
                "campus": 33,
                "project": 33,
            },
            "pipeline_status_counts": {"proposed": 1, "under_construction": 29},
            "status_counts": {
                "__MISSING__": 33,
                "permitted": 1,
                "proposed": 1,
                "shell": 1,
                "site_preparation": 1,
                "under_construction": 29,
            },
            "workload_counts": {
                "ai_specialized_unspecified": 4,
                "crypto_mining": 1,
            },
        }
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), expected)

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        self.assertEqual((len(previous_groups), len(current_groups)), (372, 421))
        self.assertLessEqual(previous_groups.keys(), current_groups.keys())
        self.assertEqual(
            Counter(key[1] for key in current_groups.keys() - previous_groups.keys()),
            {"release_source": 22, "release_source_country": 27},
        )
        for key, group in previous_groups.items():
            if key[0] != OLD_OPEN_RELEASE_ID:
                self.assertEqual(current_groups[key], group)

        previous_gap_rows = {
            _gap_key(gap): gap for gap in previous_gaps["gaps"]
        }
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        self.assertLessEqual(previous_gap_rows.keys(), current_gap_rows.keys())
        self.assertEqual(len(current_gap_rows) - len(previous_gap_rows), 245)
        for key in previous_gap_rows.keys():
            if key[1] != OLD_OPEN_RELEASE_ID:
                self.assertEqual(
                    _normalized_gap(current_gap_rows[key]),
                    _normalized_gap(previous_gap_rows[key]),
                )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_308,
                "by_severity": {
                    "high": 110,
                    "info": 15,
                    "low": 1_342,
                    "medium": 841,
                },
                "by_field": {
                    "annual_energy": 321,
                    "capacity": 310,
                    "coordinates": 100,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 310,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 140,
                    "operating_model": 328,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 15,
                    "status_as_of": 140,
                    "status_evidence": 140,
                    "status_stale_366_plus_days": 168,
                    "unique_physical_sites": 1,
                    "workload": 320,
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
        self.assertEqual(evidence_methodology["permits"]["evidence_reference_count"], 7)
        self.assertEqual(
            evidence_methodology["permits"]["source_families"],
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

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_successor_fails_closed_on_wrong_pins_symlink_and_mode(self) -> None:
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
