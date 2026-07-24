from __future__ import annotations

import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas import coverage_audit_v32 as coverage


class CoverageAuditV32Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage v32 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_definition_and_explicit_private_dependency_boundary(self) -> None:
        document = coverage.definition_document()
        self.assertEqual(document["audit_id"], coverage.AUDIT_ID)
        self.assertEqual(document["generated_at"], coverage.GENERATED_AT)
        self.assertEqual(
            [child["release_id"] for child in document["children"]],
            [
                "2026-07-22-open-seed-v97",
                "global-open-v3",
                "osm-fuzzy-review-v2",
            ],
        )
        self.assertEqual(
            document["federated_index"],
            {
                "expected_manifest_sha256": coverage.DEPENDENCIES[
                    "federation_v38"
                ]["manifest_sha256"],
                "path": "../federated_indexes/2026-07-22-public-open-v38",
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
            {"2026-07-22-open-seed-v97"},
        )
        self.assertEqual(
            [row["support_id"] for row in document["methodology_support_artifacts"]],
            [
                "2026-07-20-open-seed-v57-active-review-v1",
                coverage.V83_SUPPORT_ID,
            ],
        )

        dependencies = deepcopy(coverage.DEPENDENCIES)
        dependencies["master_v32"]["definition"] = (
            "sources/definitely-absent-public-master-v32.json"
        )
        dependencies["master_v32"]["bundle"] = (
            "construction_master/definitely-absent-public-master-v32"
        )
        dependencies["map_v32"]["definition"] = (
            "sources/definitely-absent-public-map-v32.json"
        )
        dependencies["map_v32"]["bundle"] = (
            "construction_maps/definitely-absent-public-map-v32"
        )
        with (
            ExitStack() as stack,
            patch.object(coverage, "DEPENDENCIES", dependencies),
        ):
            self._offline(stack)
            with self.assertRaisesRegex(
                coverage.CoverageAuditV32Error,
                "not a regular file|explicit private",
            ):
                coverage._require_inputs(allow_private_dependencies=False)
            modes = coverage._require_inputs(allow_private_dependencies=True)
        self.assertTrue(modes["master_v32"])
        self.assertTrue(modes["map_v32"])
        self.assertFalse(modes["exact_identity_v14"])

    def test_private_double_replay_accounting_and_claim_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="coverage-v32-test-", dir="/private/tmp"
        ) as temporary:
            candidate = Path(temporary) / "candidate"
            with ExitStack() as stack:
                self._offline(stack)
                definition, bundle, manifest = coverage.prepare_private_candidate(
                    candidate
                )
                replay = coverage.validate_private_candidate(candidate)
            self.assertEqual(manifest, replay)
            self.assertEqual(manifest["counts"], coverage.EXPECTED_COVERAGE_COUNTS)
            audit = json.loads(
                (bundle / coverage.legacy.AUDIT_FILENAME).read_bytes()
            )
            gaps = json.loads(
                (bundle / coverage.legacy.GAP_REGISTRY_FILENAME).read_bytes()
            )
            self.assertEqual(audit["audit_id"], coverage.AUDIT_ID)
            self.assertEqual(audit["generated_at"], coverage.GENERATED_AT)
            self.assertEqual(len(audit["groups"]), 1_089)
            self.assertEqual(len(audit["entity_source_families"]), 349)
            self.assertEqual(len(gaps["gaps"]), 5_048)
            self.assertEqual(
                audit["totals"]["source_scoped_entity_records"], 16_478
            )
            self.assertEqual(
                audit["totals"]["non_review_source_scoped_entity_records"],
                10_348,
            )
            self.assertEqual(
                audit["totals"]["review_only_source_scoped_entity_records"],
                6_130,
            )
            self.assertIsNone(audit["totals"]["unique_physical_sites"])
            self.assertFalse(audit["scope"]["children_merged"])
            self.assertFalse(audit["scope"]["current_status_inferred"])
            self.assertEqual(
                audit["bounded_partial_timeline_gate"],
                coverage._timeline_gate(),
            )
            self.assertEqual(
                audit["semianalysis_public_comparison"]["overall_parity"][
                    "status"
                ],
                "pending",
            )
            delta = audit["successor_delta_from_v31"]
            self.assertEqual(
                delta["coverage_groups"],
                {"current": 1_089, "delta": 110, "previous": 979},
            )
            self.assertEqual(
                delta["open_seed_groups"],
                {"current": 858, "delta": 110, "previous": 748},
            )
            self.assertEqual(
                delta["gap_summary_deltas"]["open_gaps"],
                {"current": 5_048, "delta": 466, "previous": 4_582},
            )
            self.assertTrue(delta["unrelated_child_groups_byte_equivalent"])
            self.assertEqual(delta["unrelated_child_groups_compared"], 231)
            self.assertEqual(
                definition.read_bytes(),
                coverage._canonical_json(coverage.definition_document()),
            )
            self.assertFalse(
                any(
                    token in member.read_bytes()
                    for member in bundle.iterdir()
                    for token in coverage.FORBIDDEN_STALE_ACTIVE_TOKENS
                )
            )


if __name__ == "__main__":
    unittest.main()
