from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import coverage_audit_v29 as coverage
except ModuleNotFoundError:
    from datacenter_atlas import coverage_audit_v29 as coverage


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BASE_AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v28"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v29.json"
AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v29"
GENERATED_AT = "2026-07-21T13:52:30Z"

EXPECTED_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 847,
    "methodology_support_artifacts": 1,
    "methodology_support_jobs": 74,
    "methodology_support_views": 71,
    "non_review_source_scoped_entity_records": 10_113,
    "open_gaps": 4_103,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_243,
    "unique_physical_sites": None,
}

EXPECTED_FIELD_DELTA = {
    "capacity_entity_rows": 2,
    "capacity_observations": 2,
    "capacity_observations_with_evidence": 2,
    "capacity_observations_with_resolved_evidence": 2,
    "complete_lifecycle_claim_rows": 4,
    "construction_evidence_observations": 4,
    "coordinate_rows": 3,
    "country_iso_a2_rows": 8,
    "country_iso_a3_rows": 8,
    "country_rows": 8,
    "informative_lifecycle_status_rows": 4,
    "lifecycle_status_rows": 4,
    "non_review_rows": 8,
    "non_review_under_construction_rows": 4,
    "operating_model_evidence_rows": 3,
    "operating_model_resolved_evidence_rows": 3,
    "operating_model_rows": 3,
    "pipeline_rows": 4,
    "pipeline_with_status_evidence_rows": 4,
    "source_scoped_rows": 8,
    "status_as_of_rows": 4,
    "status_evidence_rows": 4,
    "status_method_rows": 4,
    "under_construction_rows": 4,
    "under_construction_with_status_evidence_rows": 4,
    "unresolved_lifecycle_status_rows": 4,
}

DEFINITION_CHECKPOINT = (
    5_920,
    "ed2ad9f176dedef97f1cf0d91e4894570adf226b89fa460f9edbc9233ed67078",
)
AUDIT_TREE_SHA256 = "c497902893f477001ec270c611febed97ef6c73ec9ffb35c8ec3080b1cef9ec7"
ARTIFACTS = {
    "REPORT.md": (
        4_764,
        "94b25e2dde03a4e45c5957ad9b3cfb54cc177d115cf08f178ab21289770c7d14",
    ),
    "coverage-audit.json": (
        2_768_701,
        "36c879483ecd8ba364cc1a1b93f10f18191bf81e580b4b8e412d40936c705f99",
    ),
    "coverage.csv": (
        379_098,
        "1bbc39c4de41e5488dda929f93c05e6cde199a42c9ee5afdf748034edd82dfde",
    ),
    "gap-registry.json": (
        2_136_062,
        "5ac6b57f24abc1601c137d479927fcb7a2b3a058fc2ea62f73681d48444f94a2",
    ),
    "manifest.json": (
        3_379,
        "41df0bf668cba5e8ec8a2e484361e41614cdc2b58395bf204bcd8fac12714b68",
    ),
    "manifest.sha256": (
        80,
        "eeee2ce46c769fe71df860618e771f4e25720e285d2c3929e7a7d9da4d3a6a16",
    ),
}


class StopBeforePublication(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


class CoverageAuditV29Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage v29 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _layout(self, root: Path) -> tuple[Path, Path, Path]:
        sources = root / "sources"
        audits = root / "audits"
        sources.mkdir()
        audits.mkdir()
        for name in (
            "definitions",
            "federated_indexes",
            "releases",
            "satellite_change_reviews",
        ):
            os.symlink(ROOT / name, root / name, target_is_directory=True)
        return (
            sources / coverage.DEFINITION.name,
            audits / coverage.BUNDLE.name,
            root / ".coverage-audit-v29.lock",
        )

    def test_exact_successor_and_complete_accepted_dependency_gate(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            coverage._require_inputs()
        document = coverage.definition_document(GENERATED_AT)
        self.assertEqual(document["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(document["generated_at"], GENERATED_AT)
        self.assertEqual(
            [child["release_id"] for child in document["children"]],
            [
                "epoch-official-open-seed-v73",
                "global-open-v3",
                "osm-fuzzy-review-v2",
            ],
        )
        self.assertEqual(
            document["federated_index"],
            {
                "expected_manifest_sha256": coverage.FEDERATION_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-21-public-open-v33",
            },
        )
        serialized = coverage._canonical_json(document)
        self.assertTrue(
            all(token not in serialized for token in coverage.REJECTED_LINEAGE_TOKENS)
        )
        references = [
            reference
            for rows in document["methodology_evidence_classification"].values()
            for reference in rows
        ]
        self.assertEqual(len(references), 12)
        self.assertEqual(
            {reference["release_id"] for reference in references},
            {"epoch-official-open-seed-v73"},
        )
        with patch.object(coverage, "MAP_TREE_SHA256", ""):
            with self.assertRaisesRegex(
                coverage.CoverageAuditV29Error, "map v29 tree pin is not configured"
            ):
                coverage._require_inputs()

    def test_exact_offline_replay_counts_deltas_and_semantics(self) -> None:
        serialized = coverage._canonical_json(
            coverage.definition_document(GENERATED_AT)
        )
        with tempfile.TemporaryDirectory(
            prefix="coverage-v29-replay-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, _ = self._layout(Path(temporary))
            definition.write_bytes(serialized)
            with ExitStack() as stack:
                self._offline(stack)
                first = dict(coverage._patched_payloads(definition))
                second = dict(coverage._patched_payloads(definition))
            self.assertEqual(first, second)
            bundle.mkdir()
            coverage._write_bundle_stage(bundle, first)
            for entry in bundle.iterdir():
                entry.chmod(0o444)
            bundle.chmod(0o555)
            audit = coverage.legacy.validate_coverage_audit(
                bundle, definition_path=definition
            )

        manifest = json.loads(first[coverage.legacy.MANIFEST_FILENAME])
        gaps = json.loads(first[coverage.legacy.GAP_REGISTRY_FILENAME])
        self.assertEqual(manifest["counts"], EXPECTED_COUNTS)
        self.assertEqual(len(audit["groups"]), 847)
        self.assertEqual(len(audit["entity_source_families"]), 243)
        self.assertEqual(gaps["summary"]["open_gaps"], 4_103)
        self.assertEqual(audit["scope"]["unit"], "source_scoped_release_row")
        self.assertFalse(audit["scope"]["children_merged"])
        self.assertFalse(audit["scope"]["current_status_inferred"])
        self.assertTrue(audit["scope"]["review_only_rows_separately_counted"])
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertEqual(
            audit["lifecycle_contract"]["publication_v4_children"],
            [
                {
                    "current_status_inferred": False,
                    "lifecycle_freshness_records": 462,
                    "lifecycle_status_semantics": "last_observed",
                    "publication_contract_version": 4,
                    "release_id": "epoch-official-open-seed-v73",
                }
            ],
        )
        comparison = audit["semianalysis_public_comparison"]
        facility = next(
            row
            for row in comparison["comparisons"]
            if row["claim_id"] == "facility_scope_count"
        )
        self.assertEqual(facility["atlas_status"], "not_comparable")
        self.assertEqual(facility["parity_status"], "pending")
        self.assertIn("more than 5,000 facilities", facility["paraphrase"])
        self.assertIsNone(facility["atlas_evidence"]["unique_physical_sites"])
        self.assertEqual(comparison["overall_parity"]["status"], "pending")

        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_bytes())
        base_gaps = json.loads((BASE_AUDIT / "gap-registry.json").read_bytes())
        self.assertEqual(len(audit["groups"]) - len(base["groups"]), 12)
        self.assertEqual(
            len(audit["entity_source_families"])
            - len(base["entity_source_families"]),
            6,
        )
        self.assertEqual(
            gaps["summary"]["open_gaps"] - base_gaps["summary"]["open_gaps"],
            47,
        )
        self.assertEqual(
            set(gaps["summary"]["by_field"]),
            set(base_gaps["summary"]["by_field"]),
        )
        self.assertEqual(
            audit["totals"]["advisory_resolution_candidate_records"]
            - base["totals"]["advisory_resolution_candidate_records"],
            1,
        )
        fields = audit["totals"]["field_totals"]
        base_fields = base["totals"]["field_totals"]
        self.assertEqual(
            {
                field: fields[field] - base_fields[field]
                for field in EXPECTED_FIELD_DELTA
            },
            EXPECTED_FIELD_DELTA,
        )
        old_other = [
            group
            for group in base["groups"]
            if group["child_release"] != coverage.OLD_RELEASE_ID
        ]
        new_other = [
            group
            for group in audit["groups"]
            if group["child_release"] != coverage.NEW_RELEASE_ID
        ]
        self.assertEqual(old_other, new_other)

    def test_frozen_artifacts_modes_times_and_offline_reproduction(self) -> None:
        self.assertEqual(checkpoint(DEFINITION), DEFINITION_CHECKPOINT)
        self.assertEqual(
            {entry.name: checkpoint(entry) for entry in AUDIT.iterdir()},
            ARTIFACTS,
        )
        self.assertEqual(coverage.tree_digest(AUDIT), AUDIT_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(AUDIT.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(entry.stat().st_mode) == 0o444 for entry in AUDIT.iterdir())
        )
        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        for artifact in (DEFINITION, AUDIT, *AUDIT.iterdir()):
            metadata = artifact.stat()
            self.assertLessEqual(metadata.st_birthtime, generated.timestamp() + 0.000_001)
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
        for root in (DEFINITION, AUDIT):
            self.assertGreaterEqual(root.stat().st_ctime + 0.000_001, generated.timestamp())

        with ExitStack() as stack:
            self._offline(stack)
            validated = coverage.validate_coverage_audit_v29()
            first = dict(coverage._patched_payloads(DEFINITION))
            second = dict(coverage._patched_payloads(DEFINITION))
        self.assertEqual(validated["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(validated["generated_at"], GENERATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(
            first, {entry.name: entry.read_bytes() for entry in AUDIT.iterdir()}
        )

    def test_cli_collision_and_future_staging_fail_closed(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_coverage_audit_v29.py"),
                "--validate-only",
            ],
            cwd=WORKSPACE,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "audit_id": coverage.AUDIT_ID,
                "coverage_groups": 847,
                "generated_at": GENERATED_AT,
                "source_scoped_entity_records": 16_243,
            },
        )
        with tempfile.TemporaryDirectory(
            prefix="coverage-v29-collision-", dir="/private/tmp"
        ) as temporary:
            with patch.object(
                coverage,
                "PUBLICATION_LOCK",
                Path(temporary) / ".coverage-audit-v29.lock",
            ):
                with self.assertRaisesRegex(
                    coverage.CoverageAuditV29Error, "refusing replacement"
                ):
                    coverage.publish_coverage_audit_v29(GENERATED_AT)

        with tempfile.TemporaryDirectory(
            prefix="coverage-v29-temporal-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)
            target = (datetime.now(timezone.utc) + timedelta(seconds=90)).replace(
                microsecond=0
            )
            generated_at = target.isoformat().replace("+00:00", "Z")

            def stop_at_wait(actual: datetime) -> None:
                self.assertEqual(actual, target)
                self.assertFalse(definition.exists() or definition.is_symlink())
                self.assertFalse(bundle.exists() or bundle.is_symlink())
                raise StopBeforePublication("stages remained private")

            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                stack.enter_context(
                    patch.object(coverage, "_wait_until", side_effect=stop_at_wait)
                )
                with self.assertRaisesRegex(
                    StopBeforePublication, "stages remained private"
                ):
                    coverage.publish_coverage_audit_v29(generated_at)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.stage-*")))
            self.assertFalse(list((root / "audits").glob(".*.stage-*")))


if __name__ == "__main__":
    unittest.main()
