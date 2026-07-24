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
    from datacenter_atlas.datacenter_atlas import coverage_audit_v30 as coverage
except ModuleNotFoundError:
    from datacenter_atlas import coverage_audit_v30 as coverage


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v29.json"
BASE_AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v29"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v30.json"
AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v30"
PREVIEW_AT = "2026-07-21T18:20:00Z"
GENERATED_AT = "2026-07-21T18:20:30Z"

DEFINITION_CHECKPOINT = (
    5_920,
    "8d23100aaf465a5464f3945cb4d55d4fe2b370f3ce5a8ebc6e493acdcd141eba",
)
AUDIT_TREE_SHA256 = "ca7212059190432d407908008e06a684380b04fe46bef75d4201bd7c045b0ed4"
ARTIFACTS = {
    "REPORT.md": (
        4_764,
        "db7f80aefea6574d92aaea16b6f3a6f2937442830128c2f4efa01f435a3e3c18",
    ),
    "coverage-audit.json": (
        3_084_792,
        "9c946f12aa856914e55ce40dd2192c33f5d0df00663c9cdb06ba0571afe23ffc",
    ),
    "coverage.csv": (
        421_036,
        "f23b77ec713e92ca272e28d0180189272fed68e49f370e217262abbfb66d5a1b",
    ),
    "gap-registry.json": (
        2_329_238,
        "f2bd9c133bfa0dafda61c5cb61167214678fdcb8d1414b7a40dcf230cc813a76",
    ),
    "manifest.json": (
        3_379,
        "5bd7257085f52258c5187f38f811148e8edb9a38d212fc44104f9368bf769b78",
    ),
    "manifest.sha256": (
        80,
        "1d71987cd84a1ae41739f1e7d749796bdd8a98c695f7bdbc2ba96bba64af12c6",
    ),
}

EXPECTED_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 946,
    "methodology_support_artifacts": 1,
    "methodology_support_jobs": 74,
    "methodology_support_views": 71,
    "non_review_source_scoped_entity_records": 10_200,
    "open_gaps": 4_469,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_330,
    "unique_physical_sites": None,
}

EXPECTED_FIELD_DELTA = {
    "capacity_entity_rows": 8,
    "capacity_observations": 8,
    "capacity_observations_with_evidence": 8,
    "capacity_observations_with_resolved_evidence": 8,
    "complete_lifecycle_claim_rows": 44,
    "construction_evidence_observations": 37,
    "coordinate_rows": 8,
    "country_iso_a2_rows": 85,
    "country_iso_a3_rows": 85,
    "country_rows": 87,
    "informative_lifecycle_status_rows": 44,
    "lifecycle_status_rows": 44,
    "non_review_rows": 87,
    "non_review_under_construction_rows": 37,
    "operating_model_evidence_rows": 6,
    "operating_model_resolved_evidence_rows": 6,
    "operating_model_rows": 6,
    "pipeline_rows": 37,
    "pipeline_with_status_evidence_rows": 37,
    "source_scoped_rows": 87,
    "status_as_of_rows": 44,
    "status_evidence_rows": 44,
    "status_method_rows": 44,
    "under_construction_rows": 37,
    "under_construction_with_status_evidence_rows": 37,
    "unresolved_lifecycle_status_rows": 43,
    "workload_observations": 7,
    "workload_observations_with_evidence": 7,
    "workload_observations_with_resolved_evidence": 7,
    "workload_rows": 5,
}

EXPECTED_GAP_FIELD_DELTA = {
    "annual_energy": 45,
    "capacity": 41,
    "coordinates": 41,
    "country_iso_a2": 1,
    "informative_lifecycle_status": 35,
    "lifecycle_status": 35,
    "operating_model": 43,
    "source_scoped_rows": 9,
    "status_as_of": 35,
    "status_evidence": 35,
    "status_stale_366_plus_days": 2,
    "workload": 44,
}


class StopBeforePublication(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


class CoverageAuditV30Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage v30 attempted network access")
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
            root / ".coverage-audit-v30.lock",
        )

    def _replay(self) -> tuple[dict[str, bytes], dict, dict, dict]:
        serialized = coverage._canonical_json(
            coverage.definition_document(PREVIEW_AT)
        )
        with tempfile.TemporaryDirectory(
            prefix="coverage-v30-replay-", dir="/private/tmp"
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
                "epoch-official-open-seed-v83",
                "global-open-v3",
                "osm-fuzzy-review-v2",
            ],
        )
        self.assertEqual(document["children"][1:], base["children"][1:])
        self.assertEqual(
            document["federated_index"],
            {
                "expected_manifest_sha256": coverage.FEDERATION_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-21-public-open-v34",
            },
        )
        self.assertEqual(
            document["methodology_support_artifacts"],
            base["methodology_support_artifacts"],
        )
        self.assertEqual(document["public_benchmark"], base["public_benchmark"])
        references = [
            reference
            for rows in document["methodology_evidence_classification"].values()
            for reference in rows
        ]
        self.assertEqual(len(references), 12)
        self.assertEqual(
            {reference["release_id"] for reference in references},
            {"epoch-official-open-seed-v83"},
        )
        serialized = coverage._canonical_json(document)
        self.assertTrue(
            all(token not in serialized for token in coverage.REJECTED_LINEAGE_TOKENS)
        )
        dependency_times = coverage._dependency_times()
        self.assertEqual(
            [label for label, _ in dependency_times],
            [
                "accepted coverage v29",
                "accepted open-seed v83",
                "accepted federation v34",
                "accepted identity v10",
                "accepted timeline v7",
                "accepted master v30",
                "accepted map v30",
            ],
        )
        self.assertTrue(
            all(
                timestamp
                < coverage._parse_utc(PREVIEW_AT, label="preview generated_at")
                for _, timestamp in dependency_times
            )
        )
        with self.assertRaisesRegex(
            coverage.CoverageAuditV30Error, "map v30 is not temporally prior"
        ):
            coverage._require_dependencies_before(
                coverage._parse_utc(
                    "2026-07-21T18:11:00Z", label="map generated_at"
                )
            )

    def test_exact_offline_replay_counts_deltas_and_semantics(self) -> None:
        first, audit, gaps, manifest = self._replay()
        self.assertEqual(manifest["counts"], EXPECTED_COUNTS)
        self.assertEqual(len(audit["groups"]), 946)
        self.assertEqual(len(audit["entity_source_families"]), 288)
        self.assertEqual(gaps["summary"]["open_gaps"], 4_469)
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
                    "lifecycle_freshness_records": 506,
                    "lifecycle_status_semantics": "last_observed",
                    "publication_contract_version": 4,
                    "release_id": "epoch-official-open-seed-v83",
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
        self.assertIsNone(facility["atlas_evidence"]["unique_physical_sites"])
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        self.assertTrue(
            all(
                token not in raw
                for raw in first.values()
                for token in coverage.REJECTED_LINEAGE_TOKENS
            )
        )

        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_bytes())
        base_gaps = json.loads((BASE_AUDIT / "gap-registry.json").read_bytes())
        self.assertEqual(len(audit["groups"]) - len(base["groups"]), 99)
        self.assertEqual(
            len(audit["entity_source_families"])
            - len(base["entity_source_families"]),
            45,
        )
        self.assertEqual(
            gaps["summary"]["open_gaps"] - base_gaps["summary"]["open_gaps"],
            366,
        )
        self.assertEqual(
            audit["totals"]["advisory_resolution_candidate_records"],
            base["totals"]["advisory_resolution_candidate_records"],
        )
        fields = audit["totals"]["field_totals"]
        base_fields = base["totals"]["field_totals"]
        observed_numeric_delta = {
            field: value - base_fields[field]
            for field, value in fields.items()
            if type(value) is int and value != base_fields[field]
        }
        self.assertEqual(observed_numeric_delta, EXPECTED_FIELD_DELTA)
        observed_gap_delta = {
            field: value - base_gaps["summary"]["by_field"].get(field, 0)
            for field, value in gaps["summary"]["by_field"].items()
            if value != base_gaps["summary"]["by_field"].get(field, 0)
        }
        self.assertEqual(observed_gap_delta, EXPECTED_GAP_FIELD_DELTA)
        self.assertEqual(
            {
                severity: value
                - base_gaps["summary"]["by_severity"].get(severity, 0)
                for severity, value in gaps["summary"]["by_severity"].items()
            },
            {"high": 41, "info": 9, "low": 173, "medium": 143},
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

    def test_collision_and_future_stages_fail_closed(self) -> None:
        target = (datetime.now(timezone.utc) + timedelta(seconds=90)).replace(
            microsecond=0
        )
        generated_at = target.isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory(
            prefix="coverage-v30-collision-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, lock = self._layout(Path(temporary))
            definition.write_bytes(b"occupied")
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(patch.object(coverage, "DEFINITION", definition))
                stack.enter_context(patch.object(coverage, "BUNDLE", bundle))
                stack.enter_context(patch.object(coverage, "PUBLICATION_LOCK", lock))
                with self.assertRaisesRegex(
                    coverage.CoverageAuditV30Error, "refusing replacement"
                ):
                    coverage.publish_coverage_audit_v30(generated_at)
            self.assertEqual(definition.read_bytes(), b"occupied")
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())

        with tempfile.TemporaryDirectory(
            prefix="coverage-v30-temporal-", dir="/private/tmp"
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
                    coverage.publish_coverage_audit_v30(generated_at)
            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.stage-*")))
            self.assertFalse(list((root / "audits").glob(".*.stage-*")))

    def test_frozen_artifacts_modes_times_reproduction_cli_and_collision(self) -> None:
        self.assertEqual(checkpoint(DEFINITION), DEFINITION_CHECKPOINT)
        self.assertEqual(
            {entry.name: checkpoint(entry) for entry in AUDIT.iterdir()},
            ARTIFACTS,
        )
        self.assertEqual(coverage.tree_digest(AUDIT), AUDIT_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(AUDIT.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in AUDIT.iterdir()
            )
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

        with ExitStack() as stack:
            self._offline(stack)
            validated = coverage.validate_coverage_audit_v30()
            first = dict(coverage._patched_payloads(DEFINITION))
            second = dict(coverage._patched_payloads(DEFINITION))
        self.assertEqual(validated["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(validated["generated_at"], GENERATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(
            first, {entry.name: entry.read_bytes() for entry in AUDIT.iterdir()}
        )
        self.assertFalse((ROOT / ".coverage-audit-v30.lock").exists())
        self.assertFalse(list((ROOT / "sources").glob(".*v30.json.stage-*")))
        self.assertFalse(list((ROOT / "audits").glob(".*coverage-v30.stage-*")))

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_coverage_audit_v30.py"),
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
                "coverage_groups": 946,
                "generated_at": GENERATED_AT,
                "source_scoped_entity_records": 16_330,
            },
        )
        with self.assertRaisesRegex(
            coverage.CoverageAuditV30Error, "refusing replacement"
        ):
            coverage.publish_coverage_audit_v30(GENERATED_AT)


if __name__ == "__main__":
    unittest.main()
