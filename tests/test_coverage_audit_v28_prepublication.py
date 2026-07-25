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
    from datacenter_atlas.datacenter_atlas import coverage_audit_v28 as coverage
except ModuleNotFoundError:
    from datacenter_atlas import coverage_audit_v28 as coverage


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BASE_AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v27"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v28.json"
AUDIT = ROOT / "audits/2026-07-21-public-open-coverage-v28"
GENERATED_AT = "2026-07-21T10:49:30Z"

DEFINITION_CHECKPOINT = (
    5_920,
    "5fb9f2d544f3411014271461fee8b821d7677a5c6db6ebad70586545e706cff0",
)
AUDIT_TREE_SHA256 = "5d2f271b5dcd6eee6d2f53f1347370fafad7ff6d32effe0defe5e6516acc2207"
ARTIFACTS = {
    "REPORT.md": (
        4_764,
        "889180c7765d9e1327a87386cbd3bc57933a669e31e41b1c539fd9b74523ea39",
    ),
    "coverage-audit.json": (
        2_729_334,
        "4a30ad8d94f6000b68cf16a58b9c9b17295a94cd947de71e2e9cf2145a3f19f7",
    ),
    "coverage.csv": (
        373_361,
        "85da4c2d271ddb774e8cde04b19aec0061c6757d5ab636e042d1196367a71149",
    ),
    "gap-registry.json": (
        2_111_236,
        "dfd88bec8660f02c2abfd676ffc07c875660913392cdd65b2f73e426580551c7",
    ),
    "manifest.json": (
        3_379,
        "e45f001d3bcd5d619889ed8bb6a96da4aed0e8e8331daed2a98bac8e65d8f1a0",
    ),
    "manifest.sha256": (
        80,
        "24fb4201457d470444a41719b6deda006d246626a57617221e06e7fe20466932",
    ),
}

EXPECTED_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 835,
    "methodology_support_artifacts": 1,
    "methodology_support_jobs": 74,
    "methodology_support_views": 71,
    "non_review_source_scoped_entity_records": 10_105,
    "open_gaps": 4_056,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_235,
    "unique_physical_sites": None,
}

EXPECTED_FIELD_DELTA = {
    "annual_energy_entity_rows": 0,
    "annual_energy_observations": 0,
    "capacity_entity_rows": 10,
    "capacity_observations": 11,
    "construction_evidence_observations": 15,
    "coordinate_rows": 6,
    "informative_lifecycle_status_rows": 15,
    "lifecycle_status_rows": 15,
    "non_review_rows": 27,
    "non_review_under_construction_rows": 15,
    "operating_model_rows": 0,
    "pipeline_rows": 15,
    "review_only_rows": 0,
    "source_scoped_rows": 27,
    "status_as_of_rows": 15,
    "status_evidence_rows": 15,
    "under_construction_rows": 15,
    "unresolved_lifecycle_status_rows": 12,
    "workload_rows": 0,
}


class StopBeforePublication(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


class CoverageAuditV28PrepublicationTests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage v28 attempted network access")
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
            root / ".coverage-audit-v28.lock",
        )

    def test_frozen_definition_bundle_timing_and_modes(self) -> None:
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

        generated = datetime.fromisoformat(
            GENERATED_AT.replace("Z", "+00:00")
        ).timestamp()
        for path in (DEFINITION, AUDIT, *AUDIT.iterdir()):
            metadata = path.stat()
            self.assertTrue(hasattr(metadata, "st_birthtime"))
            self.assertLessEqual(metadata.st_birthtime, generated + 0.000_001)
            self.assertLessEqual(metadata.st_mtime, generated + 0.000_001)
        for path in (DEFINITION, AUDIT):
            self.assertGreaterEqual(path.stat().st_ctime, generated)
            self.assertLess(path.stat().st_ctime, generated + 0.1)

        with ExitStack() as stack:
            self._offline(stack)
            validated = coverage.validate_coverage_audit_v28()
        self.assertEqual(validated["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(validated["generated_at"], GENERATED_AT)

    def test_exact_transform_double_build_and_counts(self) -> None:
        document = coverage.definition_document(GENERATED_AT)
        self.assertEqual(document["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(
            [child["release_id"] for child in document["children"]],
            [
                "epoch-official-open-seed-v71",
                "global-open-v3",
                "osm-fuzzy-review-v2",
            ],
        )
        self.assertEqual(
            document["federated_index"],
            {
                "expected_manifest_sha256": coverage.FEDERATION_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-21-public-open-v31",
            },
        )
        serialized = coverage._canonical_json(document)
        self.assertTrue(
            all(token not in serialized for token in coverage.REJECTED_LINEAGE_TOKENS)
        )

        with tempfile.TemporaryDirectory(
            prefix="coverage-v28-prepublication-", dir="/private/tmp"
        ) as temporary:
            definition, bundle, _ = self._layout(Path(temporary))
            definition.write_bytes(serialized)
            with ExitStack() as stack:
                self._offline(stack)
                first = coverage._patched_payloads(definition)
                second = coverage._patched_payloads(definition)
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
        self.assertEqual(len(audit["groups"]), 835)
        self.assertEqual(gaps["summary"]["open_gaps"], 4_056)
        self.assertEqual(len(audit["entity_source_families"]), 237)
        self.assertIs(audit["scope"]["current_status_inferred"], False)
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertEqual(
            audit["lifecycle_contract"]["publication_v4_children"],
            [
                {
                    "current_status_inferred": False,
                    "lifecycle_freshness_records": 458,
                    "lifecycle_status_semantics": "last_observed",
                    "publication_contract_version": 4,
                    "release_id": "epoch-official-open-seed-v71",
                }
            ],
        )

        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_bytes())
        old_unchanged = [
            group
            for group in base["groups"]
            if group["child_release"] != coverage.OLD_RELEASE_ID
        ]
        new_unchanged = [
            group
            for group in audit["groups"]
            if group["child_release"] != coverage.NEW_RELEASE_ID
        ]
        self.assertEqual(new_unchanged, old_unchanged)
        self.assertEqual(
            audit["totals"]["source_scoped_entity_records"]
            - base["totals"]["source_scoped_entity_records"],
            27,
        )

    def test_exact_v27_delta_and_offline_replay(self) -> None:
        audit = json.loads((AUDIT / "coverage-audit.json").read_bytes())
        gaps = json.loads((AUDIT / "gap-registry.json").read_bytes())
        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_bytes())
        base_gaps = json.loads((BASE_AUDIT / "gap-registry.json").read_bytes())

        self.assertEqual(len(audit["groups"]) - len(base["groups"]), 19)
        self.assertEqual(
            gaps["summary"]["open_gaps"] - base_gaps["summary"]["open_gaps"],
            97,
        )
        self.assertEqual(
            len(audit["entity_source_families"])
            - len(base["entity_source_families"]),
            9,
        )
        for field, expected in (
            ("source_scoped_entity_records", 27),
            ("non_review_source_scoped_entity_records", 27),
            ("review_only_source_scoped_entity_records", 0),
            ("advisory_resolution_candidate_records", 0),
        ):
            self.assertEqual(
                audit["totals"][field] - base["totals"][field], expected
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

        with ExitStack() as stack:
            self._offline(stack)
            first = dict(coverage._patched_payloads(DEFINITION))
            second = dict(coverage._patched_payloads(DEFINITION))
        frozen = {entry.name: entry.read_bytes() for entry in AUDIT.iterdir()}
        self.assertEqual(first, second)
        self.assertEqual(first, frozen)

    def test_cli_and_collision_fail_closed(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_coverage_audit_v4.py"),
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
                "coverage_groups": 835,
                "generated_at": GENERATED_AT,
                "source_scoped_entity_records": 16_235,
            },
        )

        before = (checkpoint(DEFINITION), coverage.tree_digest(AUDIT))
        with tempfile.TemporaryDirectory(
            prefix="coverage-v28-collision-", dir="/private/tmp"
        ) as temporary:
            with ExitStack() as stack:
                self._offline(stack)
                stack.enter_context(
                    patch.object(
                        coverage,
                        "PUBLICATION_LOCK",
                        Path(temporary) / ".coverage-audit-v28.lock",
                    )
                )
                with self.assertRaisesRegex(
                    coverage.CoverageAuditV4Error, "refusing replacement"
                ):
                    coverage.publish_coverage_audit_v28(GENERATED_AT)
        self.assertEqual(
            (checkpoint(DEFINITION), coverage.tree_digest(AUDIT)), before
        )

    def test_future_publication_keeps_both_final_paths_hidden(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="coverage-v28-temporal-", dir="/private/tmp"
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
                    coverage.publish_coverage_audit_v28(generated_at)

            self.assertFalse(definition.exists() or definition.is_symlink())
            self.assertFalse(bundle.exists() or bundle.is_symlink())
            self.assertFalse(lock.exists() or lock.is_symlink())
            self.assertFalse(list((root / "sources").glob(".*.stage-*")))
            self.assertFalse(list((root / "audits").glob(".*.stage-*")))


if __name__ == "__main__":
    unittest.main()
