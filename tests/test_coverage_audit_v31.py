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
    from datacenter_atlas.datacenter_atlas import coverage_audit_v31 as coverage
except ModuleNotFoundError:
    from datacenter_atlas import coverage_audit_v31 as coverage


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v30.json"
BASE_AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v30"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v31.json"
AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v31"
PREVIEW_AT = "2026-07-22T01:30:00Z"
GENERATED_AT = "2026-07-22T01:17:00Z"
DEFINITION_CHECKPOINT = (
    9_520,
    "cd7e3f2a0b519ab0c8de44c31c1edf7facd5e3ccc2a43f136750cc209ad93030",
)
AUDIT_TREE_SHA256 = "21b037ce0fb845184fe6cede7a954815482f5b7df84e79b62c06f1b70c77d45c"
ARTIFACTS = {
    "REPORT.md": (
        5_728,
        "2e0f59abe29ff57cbcf94fe83cbc714bbc0f9d614ab9b1c1df315f623824423f",
    ),
    "coverage-audit.json": (
        3_481_612,
        "c6b5cb2eaff0004bd984ccb2c65e4a6704bcb1fe5f599d926c29ae383185526b",
    ),
    "coverage.csv": (
        435_252,
        "938c2fd0248d58c25acf7835639e8230f5aed6b052fc3fecc58039356b93cdf7",
    ),
    "gap-registry.json": (
        2_389_097,
        "17255349de93ccd3b01ef6be86545d3797063ca31dca9f389ea609efd8c139a1",
    ),
    "manifest.json": (
        269_591,
        "717917b2c566da936b2f85fd45f17d71b6ecd83ac48e2111d1bd183b052db132",
    ),
    "manifest.sha256": (
        80,
        "3cc415757f7c86023b25df6435287a6a0e40eea366ed311c20e6553b0f26a730",
    ),
}


class StopBeforePublication(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


class CoverageAuditV31Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage v31 attempted network access")
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
            root / ".coverage-audit-v31.lock",
        )

    def _replay(self) -> tuple[dict[str, bytes], dict, dict, dict]:
        document = coverage.definition_document(PREVIEW_AT)
        serialized = coverage._canonical_json(document)
        with tempfile.TemporaryDirectory(
            prefix="coverage-v31-replay-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, lock = self._layout(Path(temporary))
            definition.write_bytes(serialized)
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                first = dict(coverage._patched_payloads(document))
                second = dict(coverage._patched_payloads(document))
                self.assertEqual(first, second)
                bundle.mkdir()
                coverage._write_bundle_stage(bundle, first)
                audit = coverage._validate_payloads(
                    bundle, definition_path=definition, rebuild=True
                )
        return (
            first,
            audit,
            json.loads(first[coverage.legacy.GAP_REGISTRY_FILENAME]),
            json.loads(first[coverage.legacy.MANIFEST_FILENAME]),
        )

    def test_exact_successor_and_complete_accepted_dependency_gate(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            coverage._require_inputs()
        document = coverage.definition_document(PREVIEW_AT)
        base = json.loads(BASE_DEFINITION.read_bytes())
        self.assertEqual(document["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(document["generated_at"], PREVIEW_AT)
        self.assertEqual(
            [child["release_id"] for child in document["children"]],
            [
                "epoch-official-open-seed-v86",
                "global-open-v3",
                "osm-fuzzy-review-v2",
            ],
        )
        self.assertEqual(document["children"][1:], base["children"][1:])
        self.assertEqual(
            document["federated_index"],
            {
                "expected_manifest_sha256": coverage.FEDERATION_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-21-public-open-v35",
            },
        )
        self.assertEqual(document["public_benchmark"], base["public_benchmark"])
        supports = document["methodology_support_artifacts"]
        self.assertEqual(supports[0], base["methodology_support_artifacts"][0])
        self.assertEqual(supports[1]["support_id"], coverage.V83_SUPPORT_ID)
        self.assertFalse(supports[1]["scope"]["countable"])
        self.assertFalse(supports[1]["scope"]["promoted"])
        self.assertEqual(
            supports[1]["members"],
            {
                name: {"bytes": size, "sha256": digest}
                for name, (size, digest) in sorted(
                    coverage.V83_REVIEW_MEMBER_PINS.items()
                )
            },
        )
        references = [
            reference
            for rows in document["methodology_evidence_classification"].values()
            for reference in rows
        ]
        self.assertEqual(len(references), 12)
        self.assertEqual(
            {reference["release_id"] for reference in references},
            {"epoch-official-open-seed-v86"},
        )
        serialized = coverage._canonical_json(document)
        self.assertTrue(
            all(token not in serialized for token in coverage.FORBIDDEN_FUTURE_TOKENS)
        )
        self.assertEqual(
            [label for label, _timestamp in coverage._dependency_times()],
            [
                "accepted coverage v30",
                "accepted open-seed v86",
                "accepted federation v35",
                "accepted identity v11",
                "accepted timeline v8",
                "accepted master v31",
                "accepted map v31",
                "accepted v83 review support",
            ],
        )
        self.assertTrue(
            all(
                timestamp
                < coverage._parse_utc(PREVIEW_AT, label="preview generated_at")
                for _label, timestamp in coverage._dependency_times()
            )
        )
        with self.assertRaisesRegex(
            coverage.CoverageAuditV31Error, "canonical UTC seconds"
        ):
            coverage.definition_document("2026-07-22T01:30:00.000000Z")

    def test_offline_replay_counts_deltas_support_timeline_and_semantics(self) -> None:
        first, audit, gaps, manifest = self._replay()
        self.assertEqual(manifest["counts"], coverage.EXPECTED_COVERAGE_COUNTS)
        carrier = manifest["implementation"]["coverage_audit_v4_carrier"]
        self.assertEqual(carrier["classification"], "non_release_validator_dependency")
        self.assertEqual(
            carrier["contract"],
            "federation_v35_geometry_non_inference_validation_only",
        )
        self.assertFalse(carrier["adds_lifecycle_claims"])
        self.assertFalse(carrier["adds_identity_claims"])
        self.assertFalse(carrier["release_artifact"])
        self.assertIn(
            b"non-release validator dependency", first[coverage.legacy.REPORT_FILENAME]
        )
        self.assertEqual(len(audit["groups"]), 979)
        self.assertEqual(len(audit["entity_source_families"]), 300)
        self.assertEqual(len(gaps["gaps"]), 4_582)
        self.assertEqual(
            audit["totals"]["source_scoped_entity_records"], 16_352
        )
        self.assertEqual(
            audit["totals"]["non_review_source_scoped_entity_records"], 10_222
        )
        self.assertEqual(
            audit["totals"]["review_only_source_scoped_entity_records"], 6_130
        )
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertFalse(audit["scope"]["children_merged"])
        self.assertFalse(audit["scope"]["current_status_inferred"])

        supports = audit["inputs"]["methodology_support_artifacts"]
        self.assertEqual(
            [row["support_id"] for row in supports],
            [
                "2026-07-20-open-seed-v57-active-review-v1",
                coverage.V83_SUPPORT_ID,
            ],
        )
        self.assertEqual(
            supports[1]["accounting"],
            {
                **coverage.EXPECTED_REVIEW_ACCOUNTING,
                "exact_duplicate_group_members": (
                    coverage.EXPECTED_EXACT_DUPLICATE_GROUPS
                ),
                "x052_x041_similarity": (
                    "reviewer_approximate_only_no_exact_deduplication"
                ),
            },
        )
        self.assertEqual(
            supports[1]["status_semantics"],
            "not_a_status_observation_current_status_unknown",
        )
        self.assertTrue(all(value is False for value in supports[1]["guardrails"].values()))
        self.assertTrue(all(value is False for value in supports[1]["scope"].values()))

        evidence = audit["methodology_evidence_classification"]
        for category in ("computer_vision", "satellite_imagery"):
            self.assertEqual(evidence[category]["evidence_reference_count"], 0)
            self.assertEqual(evidence[category]["methodology_support_promotions"], 0)
            self.assertFalse(evidence[category]["methodology_support_is_countable"])
            self.assertFalse(evidence[category]["methodology_support_is_promoted"])
        self.assertEqual(evidence["foia"]["evidence_reference_count"], 0)
        self.assertEqual(
            evidence["foia"]["status"], "absent_from_audited_children"
        )

        self.assertEqual(
            audit["bounded_partial_timeline_gate"],
            {
                **coverage.EXPECTED_TIMELINE_GATE,
                "definition_sha256": coverage.TIMELINE_DEFINITION_SHA256,
                "manifest_sha256": coverage.TIMELINE_MANIFEST_SHA256,
                "scope": {
                    "current_status_inferred": False,
                    "every_facility_coverage_claimed": False,
                    "quarterly_2017_2032_parity_claimed": False,
                    "row_provenance": False,
                    "unique_physical_sites": None,
                },
                "tree_sha256": coverage.TIMELINE_TREE_SHA256,
            },
        )
        comparison = audit["semianalysis_public_comparison"]
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        facility = next(
            row
            for row in comparison["comparisons"]
            if row["claim_id"] == "facility_scope_count"
        )
        self.assertIsNone(facility["atlas_evidence"]["unique_physical_sites"])
        timeline = next(
            row
            for row in comparison["comparisons"]
            if row["claim_id"] == "construction_timeline_pjm"
        )
        self.assertEqual(timeline["atlas_status"], "partial_bounded_timeline_gate")
        self.assertEqual(timeline["parity_status"], "pending")

        delta = audit["successor_delta_from_v30"]
        self.assertEqual(
            delta["coverage_groups"],
            {"current": 979, "delta": 33, "previous": 946},
        )
        self.assertEqual(
            delta["open_seed_groups"],
            {"current": 748, "delta": 33, "previous": 715},
        )
        self.assertEqual(
            delta["gap_summary_deltas"]["open_gaps"],
            {"current": 4_582, "delta": 113, "previous": 4_469},
        )
        self.assertEqual(
            delta["totals_deltas"]["source_scoped_entity_records"],
            {"current": 16_352, "delta": 22, "previous": 16_330},
        )
        self.assertEqual(delta["unrelated_child_groups_compared"], 231)
        self.assertTrue(delta["unrelated_child_groups_byte_equivalent"])

        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_bytes())
        previous_other = [
            group
            for group in base["groups"]
            if group["child_release"] != coverage.OLD_RELEASE_ID
        ]
        current_other = [
            group
            for group in audit["groups"]
            if group["child_release"] != coverage.NEW_RELEASE_ID
        ]
        self.assertEqual(previous_other, current_other)
        self.assertTrue(
            all(
                token not in raw
                for raw in first.values()
                for token in coverage.FORBIDDEN_FUTURE_TOKENS
            )
        )

    def test_collision_symlink_future_stage_and_rollback_fail_closed(self) -> None:
        target = (datetime.now(timezone.utc) + timedelta(seconds=90)).replace(
            microsecond=0
        )
        generated_at = target.isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory(
            prefix="coverage-v31-collision-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, lock = self._layout(Path(temporary))
            definition.write_bytes(b"occupied")
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                with self.assertRaisesRegex(
                    coverage.CoverageAuditV31Error, "refusing replacement"
                ):
                    coverage.publish_coverage_audit_v31(generated_at)
            self.assertEqual(definition.read_bytes(), b"occupied")
            self.assertFalse(bundle.exists() or bundle.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="coverage-v31-symlink-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)
            os.symlink(root / "absent", definition)
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                with self.assertRaisesRegex(
                    coverage.CoverageAuditV31Error, "refusing replacement"
                ):
                    coverage.publish_coverage_audit_v31(generated_at)
            self.assertTrue(definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="coverage-v31-future-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)

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
                    coverage.publish_coverage_audit_v31(generated_at)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.stage-*")))
            self.assertFalse(list((root / "audits").glob(".*.stage-*")))

        with tempfile.TemporaryDirectory(
            prefix="coverage-v31-rollback-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition, bundle, lock = self._layout(root)
            real_promote = coverage.promote_noreplace
            calls = 0

            def fail_second(stage: Path, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated definition promotion failure")
                real_promote(stage, destination)

            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                stack.enter_context(patch.object(coverage, "_wait_until", return_value=None))
                stack.enter_context(
                    patch.object(coverage, "promote_noreplace", side_effect=fail_second)
                )
                with self.assertRaisesRegex(
                    RuntimeError, "simulated definition promotion failure"
                ):
                    coverage.publish_coverage_audit_v31(generated_at)
            self.assertEqual(calls, 3)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.rollback-*")))
            self.assertFalse(list((root / "audits").glob(".*.rollback-*")))

    def test_v30_regression_and_published_v31_when_present(self) -> None:
        before = {
            path.name: checkpoint(path)
            for path in (BASE_DEFINITION, *BASE_AUDIT.iterdir())
        }
        with ExitStack() as stack:
            self._offline(stack)
            predecessor = coverage.predecessor.validate_coverage_audit_v30()
        self.assertEqual(predecessor["audit_id"], "public-open-coverage-v30")
        self.assertEqual(
            before,
            {
                path.name: checkpoint(path)
                for path in (BASE_DEFINITION, *BASE_AUDIT.iterdir())
            },
        )
        if not DEFINITION.exists() and not AUDIT.exists():
            return
        self.assertTrue(DEFINITION.is_file())
        self.assertTrue(AUDIT.is_dir())
        self.assertEqual(checkpoint(DEFINITION), DEFINITION_CHECKPOINT)
        self.assertEqual(
            {entry.name: checkpoint(entry) for entry in AUDIT.iterdir()},
            ARTIFACTS,
        )
        self.assertEqual(coverage.tree_digest(AUDIT), AUDIT_TREE_SHA256)
        with ExitStack() as stack:
            self._offline(stack)
            validated = coverage.validate_coverage_audit_v31()
            first = dict(
                coverage._patched_payloads(json.loads(DEFINITION.read_bytes()))
            )
            second = dict(
                coverage._patched_payloads(json.loads(DEFINITION.read_bytes()))
            )
        self.assertEqual(first, second)
        self.assertEqual(
            first, {entry.name: entry.read_bytes() for entry in AUDIT.iterdir()}
        )
        self.assertEqual(validated["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(validated["generated_at"], GENERATED_AT)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(AUDIT.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(entry.stat().st_mode) == 0o444 for entry in AUDIT.iterdir())
        )
        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        for artifact in (DEFINITION, AUDIT, *AUDIT.iterdir()):
            metadata = artifact.stat()
            self.assertLessEqual(
                metadata.st_birthtime, generated.timestamp() + 0.000_001
            )
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
        for root in (DEFINITION, AUDIT):
            self.assertGreaterEqual(
                root.stat().st_ctime + 0.000_001, generated.timestamp()
            )
        self.assertFalse((ROOT / ".coverage-audit-v31.lock").exists())
        self.assertFalse(list((ROOT / "sources").glob(".*v31.json.stage-*")))
        self.assertFalse(list((ROOT / "audits").glob(".*coverage-v31.stage-*")))
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_coverage_audit_v31.py"),
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
                "coverage_groups": 979,
                "generated_at": validated["generated_at"],
                "source_scoped_entity_records": 16_352,
            },
        )
        with self.assertRaisesRegex(
            coverage.CoverageAuditV31Error, "must be in the future|refusing replacement"
        ):
            coverage.publish_coverage_audit_v31(validated["generated_at"])


if __name__ == "__main__":
    unittest.main()
