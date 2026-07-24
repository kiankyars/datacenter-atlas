from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.current_coverage import (
    CurrentCoverageError,
    SCOPE_POLICY,
    SCOPE_POLICY_V2,
    build_current_coverage_ledger,
    validate_current_coverage_ledger,
    write_current_coverage_ledger,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _checkpoint(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _pointer(document: object, pointer: str) -> object:
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            current = current[int(token)]
        else:
            raise AssertionError(f"pointer does not resolve: {pointer}")
    return current


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
V5_DEFINITION = PACKAGE_ROOT / "sources" / "current-coverage-2026-07-18-v5.json"
V5_BUNDLE = PACKAGE_ROOT / "current_coverage_ledgers" / "2026-07-18-v5"
V6_DEFINITION = PACKAGE_ROOT / "sources" / "current-coverage-2026-07-19-v6.json"
V6_BUNDLE = PACKAGE_ROOT / "current_coverage_ledgers" / "2026-07-19-v6"
V7_DEFINITION = PACKAGE_ROOT / "sources" / "current-coverage-2026-07-19-v7.json"
V7_BUNDLE = PACKAGE_ROOT / "current_coverage_ledgers" / "2026-07-19-v7"


class CurrentCoverageTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        package = root / "atlas"
        sources = package / "sources"
        artifacts = package / "artifacts"
        sources.mkdir(parents=True)
        artifacts.mkdir()

        index_path = artifacts / "index.json"
        index_path.write_bytes(
            _canonical({"counts": {"rows": 7}, "items": ["one", "two"]})
        )
        index_checkpoint = _checkpoint(index_path)
        manifest_path = artifacts / "manifest.json"
        manifest_path.write_bytes(
            _canonical({"artifacts": {"index.json": index_checkpoint}})
        )
        manifest_checkpoint = _checkpoint(manifest_path)
        (artifacts / "manifest.sha256").write_text(
            f"{manifest_checkpoint['sha256']}  manifest.json\n",
            encoding="ascii",
        )

        definition = {
            "entries": [
                {
                    "access_tier": "public_open",
                    "artifact_id": "fixture-index",
                    "artifact_kind": "federated_release_index",
                    "checkpoints": [
                        {
                            "binding": {
                                "checkpoint_id": "manifest",
                                "json_pointer": "/artifacts/index.json",
                            },
                            "bytes": index_checkpoint["bytes"],
                            "checkpoint_id": "index",
                            "path": "artifacts/index.json",
                            "sha256": index_checkpoint["sha256"],
                        },
                        {
                            "bytes": manifest_checkpoint["bytes"],
                            "checkpoint_id": "manifest",
                            "path": "artifacts/manifest.json",
                            "sha256": manifest_checkpoint["sha256"],
                        },
                    ],
                    "current_role": "authoritative_public_core",
                    "evidence_scope": "mixed_source_scoped_and_review",
                    "limitations": ["Rows are not unique sites."],
                    "metrics": [
                        {
                            "checkpoint_id": "index",
                            "json_pointer": "/items",
                            "label": "item_count",
                            "operation": "length",
                            "value": 2,
                        },
                        {
                            "checkpoint_id": "index",
                            "json_pointer": "/counts/rows",
                            "label": "rows",
                            "value": 7,
                        }
                    ],
                    "redistribution_status": "eligible_with_upstream_terms",
                }
            ],
            "generated_at": "2026-07-18T21:31:30Z",
            "ledger_id": "fixture-v1",
            "schema_version": 1,
            "scope": SCOPE_POLICY,
        }
        definition_path = sources / "fixture.json"
        definition_path.write_bytes(_canonical(definition))
        return definition_path, package / "ledger", index_path

    def _fixture_v2(self, root: Path) -> tuple[Path, Path, Path]:
        definition_path, output, index_path = self._fixture(root)
        document = json.loads(definition_path.read_text(encoding="utf-8"))
        document["ledger_id"] = "fixture-v2"
        document["schema_version"] = 2
        document["scope"] = SCOPE_POLICY_V2
        document["entries"][0]["publication_mode"] = "public_row_release"
        document["entries"][0]["record_units"] = ["source_scoped_entity_row"]
        document["parity_gaps"] = [
            {
                "affected_artifact_ids": ["fixture-index"],
                "gap_id": "benchmark-site-parity",
                "status": "not_computed",
                "summary": "No external benchmark denominator is licensed for comparison.",
            }
        ]
        definition_path.write_bytes(_canonical(document))
        return definition_path, output, index_path

    def test_build_write_and_offline_validate(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, output, _ = self._fixture(Path(temporary))
            bundle = build_current_coverage_ledger(definition)
            self.assertEqual(
                bundle.ledger["artifact_inventory_counts"]["artifacts"], 1
            )
            self.assertEqual(
                bundle.ledger["artifacts"][0]["reported_metrics"],
                {"item_count": 2, "rows": 7},
            )
            write_current_coverage_ledger(definition, output)
            manifest = validate_current_coverage_ledger(
                output, definition_path=definition
            )
            self.assertEqual(manifest["ledger_id"], "fixture-v1")

    def test_changed_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, index_path = self._fixture(Path(temporary))
            index_path.write_bytes(_canonical({"counts": {"rows": 8}}))
            with self.assertRaisesRegex(CurrentCoverageError, "checkpoint changed"):
                build_current_coverage_ledger(definition)

    def test_manifest_binding_must_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture(Path(temporary))
            manifest_path = definition.parent.parent / "artifacts" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["index.json"]["bytes"] += 1
            manifest_path.write_bytes(_canonical(manifest))
            manifest_checkpoint = _checkpoint(manifest_path)
            manifest_path.with_name("manifest.sha256").write_text(
                f"{manifest_checkpoint['sha256']}  manifest.json\n",
                encoding="ascii",
            )
            document = json.loads(definition.read_text(encoding="utf-8"))
            manifest_spec = document["entries"][0]["checkpoints"][1]
            manifest_spec.update(manifest_checkpoint)
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "manifest binding"):
                build_current_coverage_ledger(definition)

    def test_scope_cannot_claim_parity_or_unique_sites(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["scope"]["benchmark_parity_claimed"] = True
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "scope weakens"):
                build_current_coverage_ledger(definition)

    def test_local_restricted_artifact_must_remain_quarantined(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            entry = document["entries"][0]
            entry["access_tier"] = "local_restricted"
            entry["current_role"] = "local_restricted_research"
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "must remain quarantined"):
                build_current_coverage_ledger(definition)

    def test_existing_destination_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, output, _ = self._fixture(Path(temporary))
            write_current_coverage_ledger(definition, output)
            with self.assertRaisesRegex(CurrentCoverageError, "refusing existing output"):
                write_current_coverage_ledger(definition, output)

    def test_bundle_tampering_fails_reconstruction(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, output, _ = self._fixture(Path(temporary))
            write_current_coverage_ledger(definition, output)
            ledger_path = output / "current-coverage-ledger.json"
            document = json.loads(ledger_path.read_text(encoding="utf-8"))
            document["artifact_inventory_counts"]["artifacts"] = 2
            ledger_path.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "offline reconstruction"):
                validate_current_coverage_ledger(output, definition_path=definition)

    def test_v2_build_reports_publication_units_rights_and_parity_gaps(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            bundle = build_current_coverage_ledger(definition)
            counts = bundle.ledger["artifact_inventory_counts"]
            self.assertEqual(counts["by_publication_mode"]["public_row_release"], 1)
            self.assertEqual(
                counts["by_record_unit"]["source_scoped_entity_row"], 1
            )
            self.assertEqual(
                counts["by_redistribution_status"][
                    "eligible_with_upstream_terms"
                ],
                1,
            )
            self.assertEqual(counts["parity_gaps_by_status"]["not_computed"], 1)
            self.assertEqual(bundle.ledger["schema_version"], 2)

    def test_v2_scope_cannot_enable_cross_entity_construction_arithmetic(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["scope"][
                "construction_arithmetic_across_entity_levels_performed"
            ] = True
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "scope weakens"):
                build_current_coverage_ledger(definition)

    def test_v2_metadata_only_artifact_cannot_claim_public_row_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            entry = document["entries"][0]
            entry["evidence_scope"] = "metadata_only"
            entry["redistribution_status"] = "metadata_only_no_source_rows"
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(
                CurrentCoverageError, "publication mode conflicts"
            ):
                build_current_coverage_ledger(definition)

    def test_v2_public_index_mode_is_limited_to_index_or_audit_kinds(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["entries"][0]["artifact_kind"] = "construction_master"
            document["entries"][0]["publication_mode"] = "public_index_or_audit"
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "index/audit"):
                build_current_coverage_ledger(definition)

    def test_v2_record_units_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["entries"][0]["record_units"] = []
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "record_units"):
                build_current_coverage_ledger(definition)

    def test_v2_parity_gap_must_reference_a_current_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, _, _ = self._fixture_v2(Path(temporary))
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["parity_gaps"][0]["affected_artifact_ids"] = ["missing"]
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(CurrentCoverageError, "parity_gaps"):
                build_current_coverage_ledger(definition)

    def test_v2_freeze_sets_immutable_bundle_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            definition, output, _ = self._fixture_v2(Path(temporary))
            write_current_coverage_ledger(definition, output, freeze=True)
            try:
                self.assertEqual(output.stat().st_mode & 0o777, 0o555)
                for path in output.iterdir():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o444)
                validate_current_coverage_ledger(output, definition_path=definition)
            finally:
                output.chmod(0o755)
                for path in output.iterdir():
                    path.chmod(0o644)

    def test_frozen_v1_through_v4_bundles_reproduce_byte_for_byte(self):
        package_root = Path(__file__).resolve().parents[1]
        for version in ("v1", "v2", "v3", "v4"):
            with self.subTest(version=version):
                validate_current_coverage_ledger(
                    package_root
                    / "current_coverage_ledgers"
                    / f"2026-07-18-{version}",
                    definition_path=package_root
                    / "sources"
                    / f"current-coverage-2026-07-18-{version}.json",
                )

    def test_v3_keeps_current_progress_and_non_site_units_separate(self):
        package_root = Path(__file__).resolve().parents[1]
        definition = json.loads(
            (
                package_root
                / "sources"
                / "current-coverage-2026-07-18-v3.json"
            ).read_text(encoding="utf-8")
        )
        entries = {entry["artifact_id"]: entry for entry in definition["entries"]}
        unknown_paths = [
            checkpoint["path"]
            for entry in definition["entries"]
            for checkpoint in entry["checkpoints"]
            if "global-open-v3-unknown-" in checkpoint["path"]
        ]
        self.assertEqual(
            unknown_paths,
            [
                "satellite_review_runs/2026-07-18-global-open-v3-unknown-008/"
                "batch-manifest.json"
            ],
        )
        self.assertEqual(
            entries["satellite-unknown-batch-008"]["metrics"][0]["value"],
            821,
        )
        self.assertEqual(
            entries["construction-master-public-open-v2"]["record_units"],
            ["construction_master_row"],
        )
        self.assertEqual(
            entries["microsoft-global-ml-buildings-review-v1"][
                "publication_mode"
            ],
            "public_review_or_discovery",
        )
        self.assertEqual(
            entries["loudoun-data-center-assessment-v1"]["publication_mode"],
            "public_metadata_or_aggregate_only",
        )
        self.assertFalse(
            definition["scope"][
                "parcels_applications_permits_and_footprints_are_additive"
            ]
        )

    def test_v4_has_exact_inventory_replacements_metrics_and_modes(self):
        package_root = Path(__file__).resolve().parents[1]
        definition_path = (
            package_root / "sources" / "current-coverage-2026-07-18-v4.json"
        )
        bundle_path = (
            package_root / "current_coverage_ledgers" / "2026-07-18-v4"
        )
        definition_raw = definition_path.read_bytes()
        definition = json.loads(definition_raw)
        entries = {entry["artifact_id"]: entry for entry in definition["entries"]}
        expected_ids = [
            "candidate-fusion-osm-planet-priority-v9",
            "cleanview-rights-assessment-v1",
            "construction-map-public-open-v3",
            "construction-master-public-open-v3",
            "coverage-audit-four-layer-v1",
            "coverage-audit-public-open-v1",
            "edgemode-sec-assessment-v1",
            "england-planning-data-2026-07-18-v1",
            "epa-echo-frs-local-review-v1",
            "federation-four-layer-v2",
            "federation-public-open-v1",
            "gdelt-news-review-pilot",
            "gdelt-news-triage-pilot",
            "global-open-v3",
            "ireland-planning-observations-v1",
            "loudoun-data-center-assessment-v1",
            "microsoft-global-ml-buildings-review-v1",
            "nsw-major-projects-data-storage-2026-07-18-v1",
            "open-buildings-temporal-review-v2",
            "open-buildings-temporal-source-v2",
            "osm-fuzzy-global-open-v3-crosswalk-v2",
            "osm-fuzzy-review-v2",
            "osm-planet-structural-construction-v3",
            "overture-memphis-pilot",
            "peeringdb-rights-assessment-v1",
            "pjm-large-load-assessment-v1",
            "pwc-build-out-assessment-v1",
            "satellite-active-batch-001",
            "satellite-calibration-analyst-reviews-v1",
            "satellite-proposed-batch-001",
            "satellite-queue-global-open-v3",
            "satellite-unknown-batch-009",
            "scrutica-global-open-v3-crosswalk-v3",
            "scrutica-release-2026-07-18",
            "seed-epoch-official-v1",
            "virginia-deq-air-permits-local-review-v1",
            "within-release-resolution-public-open-v1",
        ]
        self.assertEqual(list(entries), expected_ids)
        self.assertEqual(len(entries), 37)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "dd02b5ef0bc1c4d62fb8fa3216421a55d28c9db632b2eb2c7b3e5860776cc2e5",
        )
        self.assertEqual(
            hashlib.sha256(
                (bundle_path / "current-coverage-ledger.json").read_bytes()
            ).hexdigest(),
            "c9215177aec87aa43e8088a12105084b6008d04134b78e5ed7118f7e236f2651",
        )
        self.assertEqual(
            hashlib.sha256((bundle_path / "manifest.json").read_bytes()).hexdigest(),
            "0d416245a2cbd5ccd004d4bad9da171a2788af2d48149c1ab6c45dbfbc2299b7",
        )
        self.assertEqual(bundle_path.stat().st_mode & 0o777, 0o555)
        for path in bundle_path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

        retired_ids = {
            "candidate-fusion-osm-planet-priority-v8",
            "construction-map-public-open-v2",
            "construction-master-public-open-v2",
            "satellite-unknown-batch-008",
        }
        self.assertFalse(retired_ids & set(entries))
        checkpoint_paths = {
            checkpoint["path"]
            for entry in definition["entries"]
            for checkpoint in entry["checkpoints"]
        }
        self.assertFalse(
            any("osm-planet-priority-v8" in path for path in checkpoint_paths)
        )
        self.assertFalse(
            any("public-open-v2" in path for path in checkpoint_paths)
        )
        self.assertEqual(
            [path for path in checkpoint_paths if "global-open-v3-unknown-" in path],
            [
                "satellite_review_runs/2026-07-18-global-open-v3-unknown-009/"
                "batch-manifest.json"
            ],
        )

        built = build_current_coverage_ledger(definition_path).ledger
        artifacts = {item["artifact_id"]: item for item in built["artifacts"]}
        self.assertEqual(built["artifact_inventory_counts"]["artifacts"], 37)
        self.assertEqual(
            built["artifact_inventory_counts"]["by_access_tier"],
            {"local_restricted": 6, "public_open": 31},
        )
        self.assertEqual(
            artifacts["construction-master-public-open-v3"]["reported_metrics"],
            {
                "annual_energy_evidence_observations": 71,
                "construction_arithmetic_rows": 168,
                "england_planning_review_rows": 3,
                "independent_master_reviews": 0,
                "ireland_planning_review_rows": 114,
                "master_rows_with_annual_energy": 44,
                "master_rows_with_capacity": 50,
                "master_rows_with_pue": 1,
                "master_rows_with_workload": 57,
                "operating_model_evidence_observations": 0,
                "pue_evidence_observations": 1,
                "review_only_rows": 108732,
                "satellite_analyst_review_rows": 25,
                "status_announced_rows": 1,
                "status_expansion_rows": 27,
                "status_proposed_rows": 21,
                "status_under_construction_rows": 119,
                "tier_a_rows": 168,
                "tier_b_rows": 6256,
                "tier_c_rows": 102476,
                "total_master_rows": 108900,
                "typed_capacity_evidence_observations": 183,
                "unique_physical_sites": None,
                "untyped_capacity_statements": 13,
                "workload_evidence_observations": 78,
            },
        )
        self.assertEqual(
            artifacts["construction-map-public-open-v3"]["reported_metrics"],
            {
                "default_visible_rows": 6413,
                "mapped_tier_a_rows": 167,
                "mapped_tier_b_rows": 6246,
                "mapped_tier_c_rows": 102476,
                "mapped_total_rows": 108889,
                "mapped_unknown_country_rows": 102523,
                "master_total_rows": 108900,
                "unique_physical_sites": None,
                "unmapped_rows": 11,
            },
        )
        self.assertEqual(
            artifacts["satellite-unknown-batch-009"]["reported_metrics"],
            {
                "jobs_completed": 918,
                "jobs_failed": 0,
                "jobs_pending": 5786,
                "jobs_selected": 6736,
                "jobs_unavailable_no_scene": 32,
            },
        )
        self.assertEqual(
            artifacts["england-planning-data-2026-07-18-v1"]["reported_metrics"],
            {
                "construction_evidence": False,
                "context_only_excluded": 1,
                "direct_scope_exact_phrase_rows": 3,
                "exact_phrase_rows": 4,
                "optional_observations_added": 0,
                "promotion_permitted": False,
                "recall_claimed": False,
                "source_rows": 100627,
            },
        )
        self.assertEqual(
            artifacts["nsw-major-projects-data-storage-2026-07-18-v1"][
                "reported_metrics"
            ],
            {
                "active_base_rows": 19,
                "active_detail_rows": 22,
                "active_modification_rows": 3,
                "base_rows": 35,
                "construction_verified_rows": 0,
                "list_rows": 44,
                "modification_rows": 9,
                "power_statement_rows": 10,
                "typed_power_or_energy_promotion_permitted": False,
                "unique_physical_sites": None,
            },
        )
        calibration = artifacts["satellite-calibration-analyst-reviews-v1"][
            "reported_metrics"
        ]
        self.assertEqual(calibration["selected_review_pairs"], 25)
        self.assertEqual(calibration["analyst_retained"], 7)
        self.assertEqual(calibration["analyst_rejected"], 18)
        self.assertFalse(calibration["accuracy_generalization_claimed"])
        self.assertFalse(calibration["production_threshold_selected"])
        self.assertFalse(calibration["recall_denominator_available"])

        backlog = next(
            gap
            for gap in definition["parity_gaps"]
            if gap["gap_id"] == "satellite-review-backlog"
        )
        self.assertEqual(
            backlog["affected_artifact_ids"],
            [
                "candidate-fusion-osm-planet-priority-v9",
                "satellite-calibration-analyst-reviews-v1",
                "satellite-queue-global-open-v3",
                "satellite-unknown-batch-009",
            ],
        )
        self.assertIn("5,786 pending", backlog["summary"])
        self.assertIn("25 selected analyst reviews", backlog["summary"])

    def test_v4_planning_manifests_bind_released_jsonl_members(self):
        package_root = Path(__file__).resolve().parents[1]
        england_root = (
            package_root
            / "source_assessments"
            / "england-planning-data-2026-07-18-v1"
        )
        england_manifest = json.loads(
            (england_root / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            _checkpoint(england_root / "observations.jsonl"),
            {
                key: england_manifest["files"]["observations.jsonl"][key]
                for key in ("bytes", "sha256")
            },
        )
        source_definition = json.loads(
            (
                package_root
                / "sources"
                / "england-planning-data-2026-07-18-v1.json"
            ).read_text(encoding="utf-8")
        )
        bundled_definition = json.loads(
            (england_root / "definition.json").read_text(encoding="utf-8")
        )
        self.assertEqual(source_definition, bundled_definition)
        self.assertEqual(
            _checkpoint(england_root / "definition.json"),
            {
                key: england_manifest["files"]["definition.json"][key]
                for key in ("bytes", "sha256")
            },
        )

        nsw_root = (
            package_root
            / "source_assessments"
            / "nsw-major-projects-data-storage-2026-07-18-v1"
        )
        nsw_manifest = json.loads(
            (nsw_root / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            _checkpoint(nsw_root / "active-planning-observations.jsonl"),
            {
                key: nsw_manifest["files"]["active-planning-observations.jsonl"][
                    key
                ]
                for key in ("bytes", "sha256")
            },
        )

    def test_v5_has_only_current_replacements_and_three_new_public_lanes(self):
        definition = json.loads(V5_DEFINITION.read_text(encoding="utf-8"))
        v4 = json.loads(
            (
                PACKAGE_ROOT / "sources" / "current-coverage-2026-07-18-v4.json"
            ).read_text(encoding="utf-8")
        )
        replacements = {
            "candidate-fusion-osm-planet-priority-v9": (
                "candidate-fusion-osm-planet-priority-v13"
            ),
            "construction-map-public-open-v3": "construction-map-public-open-v5",
            "construction-master-public-open-v3": (
                "construction-master-public-open-v5"
            ),
            "satellite-calibration-analyst-reviews-v1": (
                "satellite-calibration-analyst-reviews-v4"
            ),
            "satellite-unknown-batch-009": "satellite-unknown-batch-015",
        }
        additions = {
            "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1",
            "netherlands-koop-official-publications-2026-07-18-v1",
            "new-zealand-fast-track-2026-07-18-v1",
        }
        v4_ids = {entry["artifact_id"] for entry in v4["entries"]}
        expected_ids = {
            replacements.get(artifact_id, artifact_id) for artifact_id in v4_ids
        } | additions
        entries = {entry["artifact_id"]: entry for entry in definition["entries"]}
        self.assertEqual(list(entries), sorted(expected_ids))
        self.assertEqual(len(entries), 40)
        self.assertFalse(set(replacements) & set(entries))

        expected_current_checkpoints = {
            "candidate-fusion-osm-planet-priority-v13": {
                "coverage": (
                    "candidate_fusion/2026-07-18-osm-planet-priority-v13/coverage.json",
                    "c05f3eabf7afa0165d3fa2f9fbba3a3051ce88d2e7aed3bf46fdd8967e2942bf",
                ),
                "definition": (
                    "sources/candidate-fusion-2026-07-18-osm-planet-v13.json",
                    "63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33",
                ),
                "manifest": (
                    "candidate_fusion/2026-07-18-osm-planet-priority-v13/manifest.json",
                    "12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9",
                ),
            },
            "construction-map-public-open-v5": {
                "coverage": (
                    "construction_maps/2026-07-18-public-open-v5/coverage.json",
                    "1ba5141180acdac46c1c1b9c104c75f459f8252dc1b16d941c97f8df90b5c9de",
                ),
                "definition": (
                    "sources/construction-map-2026-07-18-public-open-v5.json",
                    "cc21bbc7f2ee0bd9e043dd8fde8c477632e9d6f301e9da77cb43500e8781da07",
                ),
                "manifest": (
                    "construction_maps/2026-07-18-public-open-v5/manifest.json",
                    "f1820bced7d1641ac9cb8821a70e0ba148c2b390980654accbef852fa8798030",
                ),
            },
            "construction-master-public-open-v5": {
                "coverage": (
                    "construction_master/2026-07-18-public-open-v5/coverage.json",
                    "8e791b8e7503e5e9f8674f1e82fd34b9641ff4453875e31205b1966758a1e5cb",
                ),
                "definition": (
                    "sources/construction-master-2026-07-18-public-open-v5.json",
                    "2438b76b58e985346e1c688d9a4fcba92fc4d0dbac23d383e0f52bbf529d88b4",
                ),
                "manifest": (
                    "construction_master/2026-07-18-public-open-v5/manifest.json",
                    "3f3b4fad0dc16e42d0e8a3507c6e9cc2d83a76ecf695032b6eb34f5a946a9cd5",
                ),
            },
            "satellite-calibration-analyst-reviews-v4": {
                "definition": (
                    "sources/satellite-calibration-2026-07-18-analyst-reviews-v4.json",
                    "876d88ff2c8ad137799714408b39016bf10b12820f637c3c2ff9ab3f30283414",
                ),
                "manifest": (
                    "satellite_calibration/2026-07-18-analyst-reviews-v4/manifest.json",
                    "a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41",
                ),
                "summary": (
                    "satellite_calibration/2026-07-18-analyst-reviews-v4/summary.json",
                    "6b8261b0f8040c156283f530232ac969ec079cd8b298bdde5b84ab638e331a0f",
                ),
            },
            "satellite-unknown-batch-015": {
                "manifest": (
                    "satellite_review_runs/2026-07-18-global-open-v3-unknown-015/batch-manifest.json",
                    "97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8",
                )
            },
        }
        for artifact_id, expected in expected_current_checkpoints.items():
            actual = {
                checkpoint["checkpoint_id"]: (
                    checkpoint["path"],
                    checkpoint["sha256"],
                )
                for checkpoint in entries[artifact_id]["checkpoints"]
            }
            self.assertEqual(actual, expected)

        identity_and_paths = [
            *entries,
            *(
                checkpoint["path"]
                for entry in definition["entries"]
                for checkpoint in entry["checkpoints"]
            ),
        ]
        forbidden = {
            "brazil-pncp",
            "chile-sea",
            "epbc",
            "germany-uvp",
            "iaac",
            "italy-mase",
            "spain-boe",
        }
        self.assertFalse(
            {
                value
                for value in identity_and_paths
                if any(fragment in value.lower() for fragment in forbidden)
            }
        )
        unknown_paths = [
            path for path in identity_and_paths if "global-open-v3-unknown-" in path
        ]
        self.assertEqual(
            unknown_paths,
            [
                "satellite_review_runs/2026-07-18-global-open-v3-unknown-015/batch-manifest.json"
            ],
        )

    def test_v5_metrics_modes_and_parity_gaps_are_checkpoint_bound(self):
        definition = json.loads(V5_DEFINITION.read_text(encoding="utf-8"))
        built = build_current_coverage_ledger(V5_DEFINITION).ledger
        counts = built["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 40)
        self.assertEqual(
            counts["by_access_tier"],
            {"local_restricted": 6, "public_open": 34},
        )
        self.assertEqual(
            counts["by_publication_mode"],
            {
                "local_quarantined": 6,
                "public_index_or_audit": 4,
                "public_metadata_or_aggregate_only": 5,
                "public_review_or_discovery": 20,
                "public_row_release": 5,
            },
        )
        self.assertEqual(
            counts["by_redistribution_status"],
            {
                "eligible_with_upstream_terms": 29,
                "metadata_only_no_source_rows": 5,
                "quarantined_pending_rights": 6,
            },
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 21)
        self.assertFalse(built["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(built["scope"]["global_completeness_claimed"])
        self.assertFalse(built["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(built["scope"]["unique_physical_site_count"])

        for entry in definition["entries"]:
            checkpoints = {
                checkpoint["checkpoint_id"]: json.loads(
                    (PACKAGE_ROOT / checkpoint["path"]).read_text(encoding="utf-8")
                )
                for checkpoint in entry["checkpoints"]
            }
            for metric in entry["metrics"]:
                actual = _pointer(
                    checkpoints[metric["checkpoint_id"]], metric["json_pointer"]
                )
                if metric.get("operation", "identity") == "length":
                    actual = len(actual)
                self.assertEqual(actual, metric["value"])
                self.assertIs(type(actual), type(metric["value"]))

        artifacts = {entry["artifact_id"]: entry for entry in built["artifacts"]}
        self.assertEqual(
            artifacts["satellite-unknown-batch-015"]["reported_metrics"],
            {
                "jobs_completed": 1308,
                "jobs_failed": 0,
                "jobs_pending": 5386,
                "jobs_selected": 6736,
                "jobs_unavailable_no_scene": 42,
            },
        )
        calibration = artifacts["satellite-calibration-analyst-reviews-v4"][
            "reported_metrics"
        ]
        self.assertEqual(calibration["selected_review_pairs"], 43)
        self.assertEqual(calibration["analyst_retained"], 12)
        self.assertEqual(calibration["analyst_rejected"], 31)
        master = artifacts["construction-master-public-open-v5"][
            "reported_metrics"
        ]
        self.assertEqual(master["total_master_rows"], 108960)
        self.assertEqual(
            (master["tier_a_rows"], master["tier_b_rows"], master["tier_c_rows"]),
            (168, 6298, 102494),
        )
        map_metrics = artifacts["construction-map-public-open-v5"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                map_metrics["master_total_rows"],
                map_metrics["mapped_total_rows"],
                map_metrics["unmapped_rows"],
                map_metrics["default_visible_rows"],
            ),
            (108960, 108941, 19, 6447),
        )
        self.assertEqual(
            artifacts[
                "france-igedd-ae-data-centres-2009-2026-2026-07-18-v1"
            ]["reported_metrics"]["derived_rows_publication_eligible"],
            True,
        )
        self.assertEqual(
            artifacts["netherlands-koop-official-publications-2026-07-18-v1"][
                "reported_metrics"
            ]["direct_project_review_candidates"],
            13,
        )
        self.assertEqual(
            artifacts["new-zealand-fast-track-2026-07-18-v1"][
                "reported_metrics"
            ]["direct_project_candidates"],
            2,
        )

        gaps = {gap["gap_id"]: gap for gap in definition["parity_gaps"]}
        backlog = gaps["satellite-review-backlog"]
        self.assertEqual(
            backlog["affected_artifact_ids"],
            [
                "candidate-fusion-osm-planet-priority-v13",
                "satellite-calibration-analyst-reviews-v4",
                "satellite-queue-global-open-v3",
                "satellite-unknown-batch-015",
            ],
        )
        for text in (
            "5,386 pending",
            "1,389 completed",
            "55 no-scene",
            "43 selected analyst reviews",
            "12 retain",
            "31 reject",
        ):
            self.assertIn(text, backlog["summary"])

    def test_frozen_v5_bundle_reproduces_offline_with_exact_permissions(self):
        manifest = validate_current_coverage_ledger(
            V5_BUNDLE, definition_path=V5_DEFINITION
        )
        self.assertEqual(manifest["ledger_id"], "current-coverage-2026-07-18-v5")
        expected_hashes = {
            V5_DEFINITION: "87bd725016c1717aa130bb871c298f62402083ead65182a16814edadc931a9d7",
            V5_BUNDLE
            / "current-coverage-ledger.json": "84d078131aa3a7cda95c2491234d8f78c048a2693d95c3ff1d12040733f5f8b1",
            V5_BUNDLE
            / "manifest.json": "e70a78f7512f9d61407e4f5373662a7ffcc434e2458b4a51d9ee0de8a8bb371d",
            V5_BUNDLE
            / "manifest.sha256": "aa6a13d8c4d6dd00f16cdf79bbc0997cf01a3bcbef1a91cb52eff39159a6010c",
        }
        for path, expected_hash in expected_hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
        self.assertEqual(V5_BUNDLE.stat().st_mode & 0o777, 0o555)
        for path in V5_BUNDLE.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_v5_contract_rejects_stale_inventory_even_with_valid_json(self):
        document = json.loads(V5_DEFINITION.read_text(encoding="utf-8"))
        document["entries"][0][
            "artifact_id"
        ] = "candidate-fusion-osm-planet-priority-v9"
        with tempfile.NamedTemporaryFile(
            dir=V5_DEFINITION.parent,
            prefix=".current-coverage-v5-stale-",
            suffix=".json",
            delete=False,
        ) as temporary:
            changed = Path(temporary.name)
            temporary.write(_canonical(document))
        try:
            with self.assertRaisesRegex(
                CurrentCoverageError, "exactly 40 current artifacts"
            ):
                build_current_coverage_ledger(changed)
        finally:
            changed.unlink()

    def test_v6_replaces_every_current_core_checkpoint_without_stale_overlap(self):
        definition = json.loads(V6_DEFINITION.read_text(encoding="utf-8"))
        entries = {entry["artifact_id"]: entry for entry in definition["entries"]}
        self.assertEqual(len(entries), 40)
        replacements = {
            "construction-map-public-open-v5": "construction-map-public-open-v10",
            "construction-master-public-open-v5": "construction-master-public-open-v10",
            "coverage-audit-public-open-v1": "coverage-audit-public-open-v9",
            "federation-public-open-v1": "federation-public-open-v8",
            "satellite-unknown-batch-015": "satellite-unknown-batch-030",
            "seed-epoch-official-v1": "seed-epoch-official-v13",
        }
        self.assertFalse(set(replacements) & set(entries))
        self.assertTrue(set(replacements.values()).issubset(entries))
        expected_checkpoints = {
            "construction-map-public-open-v10": {
                "coverage": (
                    "construction_maps/2026-07-19-public-open-v10/coverage.json",
                    "6146cf3edcb985c67da872c76745f7346d20ca0c11bc8bc8b6964446c49069da",
                ),
                "definition": (
                    "sources/construction-map-2026-07-19-public-open-v10.json",
                    "e713cc3c18823c26cd3759fb5a1522b0c0d25771bacaf96cd0472af5fd960383",
                ),
                "manifest": (
                    "construction_maps/2026-07-19-public-open-v10/manifest.json",
                    "5b57a6655e11c424b79bf820673c2e55d9cd2eb4687ed1d1c9bca163421e556f",
                ),
            },
            "construction-master-public-open-v10": {
                "coverage": (
                    "construction_master/2026-07-19-public-open-v10/coverage.json",
                    "6c6bb9c0d90267003e0f376e7d79f13638687b7d81207371b774146dc6d7b061",
                ),
                "definition": (
                    "sources/construction-master-2026-07-19-public-open-v10.json",
                    "aa252132da08ee5f224097dfcbf50dbdbe9e7e5a1416b58e85af304030a3fa34",
                ),
                "manifest": (
                    "construction_master/2026-07-19-public-open-v10/manifest.json",
                    "739f340d9413c9a54b5f38174cc5808620326cd1cf6aa59a85738027ff5c2bbb",
                ),
            },
            "coverage-audit-public-open-v9": {
                "manifest": (
                    "audits/2026-07-19-public-open-coverage-v9/manifest.json",
                    "657216c910e300314f691e1e726a188c24095bd7b4ec000a97d2a4db7e4ff247",
                )
            },
            "federation-public-open-v8": {
                "index": (
                    "federated_indexes/2026-07-19-public-open-v8/federated-index.json",
                    "75737e6175f4de03f84e9b0cead12e92cf5fcdfa9e59a85ba845bd0a7fa60bd4",
                ),
                "manifest": (
                    "federated_indexes/2026-07-19-public-open-v8/manifest.json",
                    "0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48",
                ),
            },
            "satellite-unknown-batch-030": {
                "manifest": (
                    "satellite_review_runs/2026-07-18-global-open-v3-unknown-030/batch-manifest.json",
                    "18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053",
                )
            },
            "seed-epoch-official-v13": {
                "manifest": (
                    "releases/2026-07-19-open-seed-v13/manifest.json",
                    "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7",
                )
            },
        }
        for artifact_id, expected in expected_checkpoints.items():
            actual = {
                checkpoint["checkpoint_id"]: (
                    checkpoint["path"],
                    checkpoint["sha256"],
                )
                for checkpoint in entries[artifact_id]["checkpoints"]
            }
            self.assertEqual(actual, expected)

    def test_v6_metrics_and_parity_backlog_are_checkpoint_bound(self):
        built = build_current_coverage_ledger(V6_DEFINITION).ledger
        counts = built["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 40)
        self.assertEqual(
            counts["by_access_tier"], {"local_restricted": 6, "public_open": 34}
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 21)
        artifacts = {entry["artifact_id"]: entry for entry in built["artifacts"]}

        satellite = artifacts["satellite-unknown-batch-030"]["reported_metrics"]
        self.assertEqual(
            satellite,
            {
                "jobs_completed": 4350,
                "jobs_failed": 0,
                "jobs_pending": 2086,
                "jobs_selected": 6736,
                "jobs_unavailable_no_scene": 300,
            },
        )
        master = artifacts["construction-master-public-open-v10"][
            "reported_metrics"
        ]
        self.assertEqual(
            (master["total_master_rows"], master["tier_a_rows"], master["tier_b_rows"], master["tier_c_rows"]),
            (109017, 225, 6298, 102494),
        )
        self.assertEqual(
            {
                label: master[label]
                for label in (
                    "status_announced_rows",
                    "status_civil_works_rows",
                    "status_expansion_rows",
                    "status_foundations_rows",
                    "status_mep_electrical_rows",
                    "status_permitted_rows",
                    "status_proposed_rows",
                    "status_shell_rows",
                    "status_site_preparation_rows",
                    "status_under_construction_rows",
                )
            },
            {
                "status_announced_rows": 2,
                "status_civil_works_rows": 2,
                "status_expansion_rows": 27,
                "status_foundations_rows": 2,
                "status_mep_electrical_rows": 3,
                "status_permitted_rows": 2,
                "status_proposed_rows": 21,
                "status_shell_rows": 2,
                "status_site_preparation_rows": 5,
                "status_under_construction_rows": 159,
            },
        )
        self.assertEqual(master["typed_capacity_evidence_observations"], 203)
        self.assertEqual(master["annual_energy_evidence_observations"], 73)
        self.assertEqual(master["operating_model_evidence_observations"], 1)
        self.assertEqual(master["pue_evidence_observations"], 2)
        self.assertEqual(master["workload_evidence_observations"], 97)

        map_metrics = artifacts["construction-map-public-open-v10"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                map_metrics["master_total_rows"],
                map_metrics["mapped_total_rows"],
                map_metrics["unmapped_rows"],
                map_metrics["default_visible_rows"],
            ),
            (109017, 108972, 45, 6478),
        )
        audit = artifacts["coverage-audit-public-open-v9"]["reported_metrics"]
        self.assertEqual(
            (audit["coverage_groups"], audit["open_gaps"], audit["source_scoped_rows"]),
            (320, 1819, 15619),
        )
        federation = artifacts["federation-public-open-v8"]["reported_metrics"]
        self.assertEqual(
            (
                federation["source_scoped_rows"],
                federation["construction_pipeline_records"],
                federation["non_review_construction_pipeline_records"],
                federation["review_only_construction_pipeline_records"],
            ),
            (15619, 6355, 225, 6130),
        )
        seed = artifacts["seed-epoch-official-v13"]["reported_metrics"]
        self.assertEqual(
            seed,
            {
                "capacity_observations": 362,
                "construction_pipeline_records": 105,
                "construction_source_signals": 95,
                "evidence_records": 140,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 194,
            },
        )

        gaps = {gap["gap_id"]: gap for gap in built["parity_gaps"]}
        backlog = gaps["satellite-review-backlog"]
        self.assertEqual(
            backlog["affected_artifact_ids"],
            [
                "candidate-fusion-osm-planet-priority-v13",
                "satellite-calibration-analyst-reviews-v4",
                "satellite-queue-global-open-v3",
                "satellite-unknown-batch-030",
            ],
        )
        for marker in (
            "2,086 pending",
            "4,431 completed",
            "313 no-scene",
            "43 selected analyst reviews",
            "12 retain",
            "31 reject",
        ):
            self.assertIn(marker, backlog["summary"])

    def test_frozen_v6_bundle_reproduces_offline_with_exact_permissions(self):
        manifest = validate_current_coverage_ledger(
            V6_BUNDLE, definition_path=V6_DEFINITION
        )
        self.assertEqual(manifest["ledger_id"], "current-coverage-2026-07-19-v6")
        expected_hashes = {
            V6_DEFINITION: "533b6120ee3d0af916c083bc8246d0ca5e0b6b1c3bb9cf287f9dc3d75b09d2c3",
            V6_BUNDLE
            / "current-coverage-ledger.json": "86c7b9161bce4fa4eb0877b239643b3d81dd0fd3f2b374f8c996f519b0749dbd",
            V6_BUNDLE
            / "manifest.json": "a5210a81b01eee86b2eb84ff9bafcd71c21f99910121247334cd3880b80e8351",
            V6_BUNDLE
            / "manifest.sha256": "f14df9b18970c3275cdcb5f33380bab90c6e1ce0936ea0dd2f496a69ca53e816",
        }
        for path, expected_hash in expected_hashes.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
        self.assertEqual(V6_BUNDLE.stat().st_mode & 0o777, 0o555)
        for path in V6_BUNDLE.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_v6_contract_rejects_stale_inventory_even_with_valid_json(self):
        document = json.loads(V6_DEFINITION.read_text(encoding="utf-8"))
        document["entries"][2]["artifact_id"] = "construction-map-public-open-v5"
        with tempfile.NamedTemporaryFile(
            dir=V6_DEFINITION.parent,
            prefix=".current-coverage-v6-stale-",
            suffix=".json",
            delete=False,
        ) as temporary:
            changed = Path(temporary.name)
            temporary.write(_canonical(document))
        try:
            with self.assertRaisesRegex(
                CurrentCoverageError, "exactly 40 current artifacts"
            ):
                build_current_coverage_ledger(changed)
        finally:
            changed.unlink()

    def test_v7_replaces_exactly_five_artifacts_and_preserves_the_other_35(self):
        previous = json.loads(V6_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(V7_DEFINITION.read_text(encoding="utf-8"))
        replacements = {
            "construction-map-public-open-v10": "construction-map-public-open-v11",
            "construction-master-public-open-v10": "construction-master-public-open-v11",
            "coverage-audit-public-open-v9": "coverage-audit-public-open-v10",
            "federation-public-open-v8": "federation-public-open-v9",
            "seed-epoch-official-v13": "seed-epoch-official-v20",
        }
        previous_entries = {
            entry["artifact_id"]: entry for entry in previous["entries"]
        }
        current_entries = {
            entry["artifact_id"]: entry for entry in current["entries"]
        }
        self.assertEqual(len(previous_entries), 40)
        self.assertEqual(len(current_entries), 40)
        self.assertFalse(set(replacements) & set(current_entries))
        self.assertTrue(set(replacements.values()).issubset(current_entries))
        unchanged_ids = set(previous_entries) - set(replacements)
        self.assertEqual(len(unchanged_ids), 35)
        for artifact_id in sorted(unchanged_ids):
            self.assertEqual(
                current_entries[artifact_id], previous_entries[artifact_id]
            )
        self.assertEqual(
            current_entries["satellite-unknown-batch-030"],
            previous_entries["satellite-unknown-batch-030"],
        )

        expected_checkpoints = {
            "construction-map-public-open-v11": {
                "coverage": (
                    "construction_maps/2026-07-19-public-open-v11/coverage.json",
                    6235,
                    "7b19c8a4303fe3b75e6075cf5d8b3167bbce22527de38ecbbb0e924ce68c2d3e",
                ),
                "definition": (
                    "sources/construction-map-2026-07-19-public-open-v11.json",
                    5926,
                    "2af41d8d846ea56fbf68a0489e708973ea087351349fb3adc386cc3e3c268986",
                ),
                "manifest": (
                    "construction_maps/2026-07-19-public-open-v11/manifest.json",
                    1967,
                    "e9aa6e9778edba365572eb92bc87b0612e6daf1f02387eac96046c935ce2c56c",
                ),
            },
            "construction-master-public-open-v11": {
                "coverage": (
                    "construction_master/2026-07-19-public-open-v11/coverage.json",
                    29702,
                    "38e4306a57127a412939532104255a881eb9d24671f47ee83420efcec949daa8",
                ),
                "definition": (
                    "sources/construction-master-2026-07-19-public-open-v11.json",
                    15026,
                    "1689dd992ae482dbf464c42300fb0b32289c2d795b6edce2d4b1ac8f6a7fb65c",
                ),
                "manifest": (
                    "construction_master/2026-07-19-public-open-v11/manifest.json",
                    47667,
                    "dd0648d98e27d2f11b1ce117c92e45647d00b9226083f54025c27e0979e5f951",
                ),
            },
            "coverage-audit-public-open-v10": {
                "manifest": (
                    "audits/2026-07-19-public-open-coverage-v10/manifest.json",
                    2240,
                    "ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e",
                ),
            },
            "federation-public-open-v9": {
                "index": (
                    "federated_indexes/2026-07-19-public-open-v9/federated-index.json",
                    16592,
                    "600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1",
                ),
                "manifest": (
                    "federated_indexes/2026-07-19-public-open-v9/manifest.json",
                    985,
                    "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5",
                ),
            },
            "seed-epoch-official-v20": {
                "manifest": (
                    "releases/2026-07-19-open-seed-v20/manifest.json",
                    4293,
                    "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456",
                ),
            },
        }
        for artifact_id, expected in expected_checkpoints.items():
            actual = {
                checkpoint["checkpoint_id"]: (
                    checkpoint["path"],
                    checkpoint["bytes"],
                    checkpoint["sha256"],
                )
                for checkpoint in current_entries[artifact_id]["checkpoints"]
            }
            self.assertEqual(actual, expected)

        previous_gaps = {
            gap["gap_id"]: gap for gap in previous["parity_gaps"]
        }
        current_gaps = {gap["gap_id"]: gap for gap in current["parity_gaps"]}
        self.assertEqual(len(current_gaps), 6)
        self.assertEqual(set(current_gaps), set(previous_gaps))
        for gap_id, gap in previous_gaps.items():
            self.assertEqual(
                current_gaps[gap_id],
                {
                    **gap,
                    "affected_artifact_ids": [
                        replacements.get(artifact_id, artifact_id)
                        for artifact_id in gap["affected_artifact_ids"]
                    ],
                },
            )

    def test_v7_metrics_and_scope_are_bound_to_current_checkpoints(self):
        built = build_current_coverage_ledger(V7_DEFINITION).ledger
        counts = built["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 40)
        self.assertEqual(
            counts["by_access_tier"],
            {"local_restricted": 6, "public_open": 34},
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 21)
        self.assertFalse(built["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(built["scope"]["global_completeness_claimed"])
        self.assertFalse(
            built["scope"]["source_scoped_rows_are_unique_physical_sites"]
        )
        self.assertIsNone(built["scope"]["unique_physical_site_count"])
        artifacts = {
            entry["artifact_id"]: entry for entry in built["artifacts"]
        }

        map_metrics = artifacts["construction-map-public-open-v11"][
            "reported_metrics"
        ]
        self.assertEqual(
            {
                label: map_metrics[label]
                for label in (
                    "default_visible_rows",
                    "mapped_tier_a_rows",
                    "mapped_tier_b_rows",
                    "mapped_tier_c_rows",
                    "mapped_total_rows",
                    "master_total_rows",
                    "unmapped_rows",
                    "unique_physical_sites",
                )
            },
            {
                "default_visible_rows": 6478,
                "mapped_tier_a_rows": 198,
                "mapped_tier_b_rows": 6280,
                "mapped_tier_c_rows": 102494,
                "mapped_total_rows": 108972,
                "master_total_rows": 109063,
                "unmapped_rows": 91,
                "unique_physical_sites": None,
            },
        )

        master = artifacts["construction-master-public-open-v11"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                master["total_master_rows"],
                master["tier_a_rows"],
                master["tier_b_rows"],
                master["tier_c_rows"],
                master["review_only_rows"],
            ),
            (109063, 271, 6298, 102494, 108792),
        )
        self.assertEqual(
            {
                label: master[label]
                for label in (
                    "status_announced_rows",
                    "status_civil_works_rows",
                    "status_expansion_rows",
                    "status_foundations_rows",
                    "status_mep_electrical_rows",
                    "status_permitted_rows",
                    "status_proposed_rows",
                    "status_shell_rows",
                    "status_site_preparation_rows",
                    "status_under_construction_rows",
                )
            },
            {
                "status_announced_rows": 3,
                "status_civil_works_rows": 2,
                "status_expansion_rows": 27,
                "status_foundations_rows": 2,
                "status_mep_electrical_rows": 15,
                "status_permitted_rows": 2,
                "status_proposed_rows": 21,
                "status_shell_rows": 5,
                "status_site_preparation_rows": 8,
                "status_under_construction_rows": 186,
            },
        )
        self.assertEqual(master["typed_capacity_evidence_observations"], 228)
        self.assertEqual(master["annual_energy_evidence_observations"], 73)
        self.assertEqual(master["operating_model_evidence_observations"], 2)
        self.assertEqual(master["pue_evidence_observations"], 2)
        self.assertEqual(master["workload_evidence_observations"], 98)
        self.assertEqual(master["master_rows_with_capacity"], 89)
        self.assertEqual(master["master_rows_with_workload"], 77)
        self.assertIsNone(master["unique_physical_sites"])

        audit = artifacts["coverage-audit-public-open-v10"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                audit["coverage_groups"],
                audit["open_gaps"],
                audit["source_scoped_rows"],
                audit["non_review_source_scoped_rows"],
                audit["review_only_source_scoped_rows"],
            ),
            (372, 2063, 15707, 9577, 6130),
        )
        federation = artifacts["federation-public-open-v9"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                federation["source_scoped_rows"],
                federation["construction_pipeline_records"],
                federation["non_review_construction_pipeline_records"],
                federation["review_only_construction_pipeline_records"],
                federation["capacity_observations"],
            ),
            (15707, 6401, 271, 6130, 1178),
        )
        seed = artifacts["seed-epoch-official-v20"]["reported_metrics"]
        self.assertEqual(
            seed,
            {
                "capacity_observations": 392,
                "construction_pipeline_records": 151,
                "construction_source_signals": 124,
                "evidence_records": 182,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 282,
            },
        )

        self.assertEqual(len(built["parity_gaps"]), 6)
        affected = {
            artifact_id
            for gap in built["parity_gaps"]
            for artifact_id in gap["affected_artifact_ids"]
        }
        self.assertTrue(
            {
                "construction-map-public-open-v11",
                "construction-master-public-open-v11",
                "coverage-audit-public-open-v10",
                "federation-public-open-v9",
                "seed-epoch-official-v20",
            }.issubset(affected)
        )

    def test_frozen_v7_bundle_reproduces_twice_offline(self):
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("ledger validation attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("ledger validation attempted network access"),
        ):
            first = validate_current_coverage_ledger(
                V7_BUNDLE, definition_path=V7_DEFINITION
            )
            second = validate_current_coverage_ledger(
                V7_BUNDLE, definition_path=V7_DEFINITION
            )
        self.assertEqual(first, second)
        self.assertEqual(first["ledger_id"], "current-coverage-2026-07-19-v7")
        expected_hashes = {
            V7_DEFINITION: "9f9ef309276d5e5d15cd96ffccb08afb5043455d63482f978a1068dc0ec350b6",
            V7_BUNDLE
            / "current-coverage-ledger.json": "e4c7a59dff63e49e27771dcb81646e8b4cace4c875bd894439f184b85d1bdb8f",
            V7_BUNDLE
            / "manifest.json": "73f48e8856395410956295a5cd6221b105876663b933675c955b379deb421e52",
            V7_BUNDLE
            / "manifest.sha256": "d43c6141ef72e9891530d794261ef74e765829d4d93a556684908251bb51e6cd",
        }
        for path, expected_hash in expected_hashes.items():
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash
            )
        self.assertEqual(V7_BUNDLE.stat().st_mode & 0o777, 0o555)
        for path in V7_BUNDLE.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_v7_contract_rejects_stale_pins_and_unfrozen_output(self):
        original = json.loads(V7_DEFINITION.read_text(encoding="utf-8"))
        cases = []

        changed = json.loads(json.dumps(original))
        changed["generated_at"] = "2026-07-19T21:20:01Z"
        cases.append((changed, "v7 generation timestamp changed"))

        changed = json.loads(json.dumps(original))
        changed["entries"][2]["artifact_id"] = "construction-map-public-open-v10"
        cases.append((changed, "exactly 40 current artifacts"))

        changed = json.loads(json.dumps(original))
        master = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "construction-master-public-open-v11"
        )
        master["checkpoints"][0]["sha256"] = "0" * 64
        cases.append((changed, "current checkpoint contract changed"))

        changed = json.loads(json.dumps(original))
        changed["parity_gaps"][0]["affected_artifact_ids"][0] = (
            "construction-map-public-open-v10"
        )
        cases.append((changed, "stale current artifacts"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (document, pattern) in enumerate(cases):
                definition = root / f"changed-v7-{index}.json"
                definition.write_bytes(_canonical(document))
                with self.assertRaisesRegex(CurrentCoverageError, pattern):
                    build_current_coverage_ledger(definition)

            unfrozen = root / "unfrozen-v7"
            write_current_coverage_ledger(V7_DEFINITION, unfrozen)
            with self.assertRaisesRegex(
                CurrentCoverageError, "must be frozen 0555/0444"
            ):
                validate_current_coverage_ledger(
                    unfrozen, definition_path=V7_DEFINITION
                )


if __name__ == "__main__":
    unittest.main()
