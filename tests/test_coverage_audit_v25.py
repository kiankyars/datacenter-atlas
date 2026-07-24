from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.coverage_audit as legacy
import datacenter_atlas.coverage_audit_v2 as coverage_v2


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v25.json"
AUDIT = ROOT / "audits/2026-07-20-public-open-coverage-v25"
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v24.json"
BASE_AUDIT = ROOT / "audits/2026-07-20-public-open-coverage-v24"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v26"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
SUPPORT_DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews/2026-07-20-open-seed-v57-active-review-v1.json"
)
SUPPORT = (
    ROOT
    / "satellite_change_reviews/2026-07-20-open-seed-v57-active-review-v1"
)

DEFINITION_SHA256 = "8a238ec8d056dd1162bcdd1e798dd20774271224cc9c6c76cacf0a8a8ada7894"
TREE_SHA256 = "cd867e629d5447a023d73fa61ad2353bfd7b3ef8398fed9183bfab97288b1548"
FEDERATION_MANIFEST_SHA256 = (
    "7c46daa54ea1de6da325f495f4a54fda2e1c16bae3a0ca7fdb6901ba7d391361"
)
V59_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
SUPPORT_DEFINITION_SHA256 = (
    "eb009c496f805d8c68e9510904f45f5a7c82af3fe3f0428a4c96d97dd38aa482"
)
SUPPORT_TREE_SHA256 = (
    "0e79d853fd6ee4ba11ead97754850efe9de16c2c9782a47ce6e01105e3358a41"
)

ARTIFACTS = {
    "REPORT.md": (
        4_763,
        "979db6938335fd9b9b795a5b32fdd8d5d7e30a93162ebf8ec70f856b4fc639fa",
    ),
    "coverage-audit.json": (
        2_368_880,
        "1182bf4e6885753a47d78f67eaa938e2a04b2f2e6db1bd8eb0af11fcb16277e4",
    ),
    "coverage.csv": (
        322_532,
        "9dc40e36c3a0088e5bb0d9fa3aeb8f86fb61354f008cf5efcc2b588b7825699a",
    ),
    "gap-registry.json": (
        1_879_261,
        "b54c937f407ae7476a890903224d210e970fcc3f8d8f4d7755be9fa929738623",
    ),
    "manifest.json": (
        3_378,
        "f4b4656b04f558a9d89af6348ede4080c55755729c5efded9fb077d0b9330012",
    ),
    "manifest.sha256": (
        80,
        "9146b37fce9da5220823a6b7b8a64d2afe2d5d419160f10825bbf4b44ed6f33a",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/coverage_audit.py": (
        82_129,
        "5b383a4b06f3a767dbb45c52c49e10da5c85f383d1739bc6af9abebff6617ad3",
    ),
    ROOT / "scripts/build_coverage_audit.py": (
        1_259,
        "e8d6558588cd37a50a162937dccb7f5dee9088f35aac2c053714bc7c211ca79d",
    ),
    ROOT / "datacenter_atlas/coverage_audit_v2.py": (
        54_772,
        "f4af61258d90054fe6f3c28c2470164c096e2186cf97d4445a09aa4675bb2b52",
    ),
    ROOT / "coverage_audit_v2.py": (
        137,
        "4923b322edd996ec977ab85c8c928b7d39b4eecb2dab080a25e6df03a2f06764",
    ),
    ROOT / "scripts/build_coverage_audit_v2.py": (
        1_456,
        "0d4f910280d1400c27fc1a91eb71b6727cfd678a8b89bd43f676c8e294d9fe30",
    ),
}

LEGACY_PINS = {
    BASE_DEFINITION: (
        3_871,
        "4f236d3bb9b39a546c592f2de2f9e5f771b5c913ea3703d5742c4b99772ed937",
    ),
    BASE_AUDIT / "manifest.json": (
        2_240,
        "7fa0fd899ba268bef8d3105fc542e29c150728e0640484c9553d83d4eca392a2",
    ),
}
LEGACY_TREE_SHA256 = (
    "3828ae78a4b9c29927a4f770fbcc4d36fa10cbada8d9cdde578d447d98e03d37"
)

EXPECTED_TOTALS = {
    "advisory_resolution_candidate_records": 100_410,
    "confirmed_duplicate_relationships": None,
    "non_review_source_scoped_entity_records": 9_994,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_124,
    "unique_physical_sites": None,
}
EXPECTED_PROPERTY_FAMILIES = {
    "cook_county_official_address_points",
    "cuzk_ruian_parcels",
    "fairfax_county_parcels_wgs84_mapserver",
    "hessen_official_house_coordinates_wfs",
    "mantsala_official_map_service",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"tree contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported tree entry: {relative}")
    return digest.hexdigest()


class CoverageAuditV25Tests(unittest.TestCase):
    maxDiff = None

    def _definition_copy(
        self, directory: Path, transform: object | None = None
    ) -> Path:
        document = json.loads(DEFINITION.read_text(encoding="utf-8"))
        document["federated_index"]["path"] = str(FEDERATION)
        for child in document["children"]:
            if child["release_id"] == "epoch-official-open-seed-v59":
                child["release_path"] = str(V59_RELEASE)
            elif child["release_id"] == "global-open-v3":
                child["release_path"] = str(
                    ROOT / "releases/2026-07-18-global-open-v3"
                )
            else:
                child["release_path"] = str(
                    ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"
                )
        support = document["methodology_support_artifacts"][0]
        support["directory"] = str(SUPPORT)
        support["definition"]["path"] = str(SUPPORT_DEFINITION)
        if callable(transform):
            transform(document)
        path = directory / "definition.json"
        path.write_bytes(canonical_json(document))
        return path

    def test_frozen_bundle_and_exact_successor_inputs(self) -> None:
        self.assertEqual(checkpoint(DEFINITION), (5_920, DEFINITION_SHA256))
        self.assertEqual(
            sha256(FEDERATION / "manifest.json"), FEDERATION_MANIFEST_SHA256
        )
        self.assertEqual(
            sha256(V59_RELEASE / "manifest.json"), V59_MANIFEST_SHA256
        )
        self.assertEqual(sha256(SUPPORT_DEFINITION), SUPPORT_DEFINITION_SHA256)
        self.assertEqual(tree_digest(SUPPORT), SUPPORT_TREE_SHA256)
        self.assertEqual(
            {path.name: checkpoint(path) for path in AUDIT.iterdir()}, ARTIFACTS
        )
        self.assertEqual(tree_digest(AUDIT), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(AUDIT.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in AUDIT.iterdir())
        )
        validated = coverage_v2.validate_coverage_audit(
            AUDIT, definition_path=DEFINITION
        )
        self.assertEqual(validated["audit_id"], "public-open-coverage-v25")

    def test_counts_lifecycle_and_exact_v59_delta(self) -> None:
        audit = json.loads((AUDIT / "coverage-audit.json").read_text())
        base = json.loads((BASE_AUDIT / "coverage-audit.json").read_text())
        self.assertEqual(audit["as_of"], "2026-07-20")
        self.assertEqual(audit["generated_at"], "2026-07-21T04:00:00Z")
        self.assertEqual(len(audit["groups"]), 724)
        for field, value in EXPECTED_TOTALS.items():
            self.assertEqual(audit["totals"][field], value)
        fields = audit["totals"]["field_totals"]
        self.assertEqual(fields["capacity_observations"], 1_277)
        self.assertEqual(fields["under_construction_rows"], 378)
        self.assertEqual(fields["non_review_under_construction_rows"], 360)
        self.assertEqual(fields["coordinate_rows"], 15_485)
        self.assertEqual(fields["construction_evidence_observations"], 257)
        self.assertEqual(
            audit["totals"]["source_scoped_entity_records"]
            - base["totals"]["source_scoped_entity_records"],
            32,
        )
        self.assertEqual(len(audit["groups"]) - len(base["groups"]), 45)
        lifecycle = audit["lifecycle_contract"]
        self.assertEqual(lifecycle["status_semantics"], "last_observed")
        self.assertIs(lifecycle["current_status_inferred"], False)
        self.assertEqual(lifecycle["current_status_classification"], "unknown")
        self.assertEqual(
            lifecycle["publication_v4_children"],
            [
                {
                    "current_status_inferred": False,
                    "lifecycle_freshness_records": 399,
                    "lifecycle_status_semantics": "last_observed",
                    "publication_contract_version": 4,
                    "release_id": "epoch-official-open-seed-v59",
                }
            ],
        )

    def test_method_support_and_property_evidence_remain_nonadditive(self) -> None:
        audit = json.loads((AUDIT / "coverage-audit.json").read_text())
        support = audit["inputs"]["methodology_support_artifacts"]
        self.assertEqual(len(support), 1)
        record = support[0]
        self.assertEqual(
            record["support_id"], "2026-07-20-open-seed-v57-active-review-v1"
        )
        self.assertEqual(record["schema_version"], 4)
        self.assertEqual(record["counts"], {"jobs": 74, "views": 71})
        self.assertEqual(record["status_semantics"], "last_observed")
        self.assertTrue(record["scope"]["review_only"])
        self.assertTrue(
            all(
                record["scope"][field] is False
                for field in (
                    "child_evidence",
                    "facility_rows",
                    "lifecycle_observations",
                    "current_status_claim",
                    "atlas_mutation",
                    "promoted",
                    "countable",
                )
            )
        )
        self.assertTrue(all(value is False for value in record["guardrails"].values()))
        methodology = audit["methodology_evidence_classification"]
        for category in ("computer_vision", "satellite_imagery"):
            item = methodology[category]
            self.assertEqual(item["status"], "partial_reviewed_method_evidence")
            self.assertEqual(item["evidence_reference_count"], 0)
            self.assertEqual(item["methodology_support_artifact_count"], 1)
            self.assertIs(item["methodology_support_is_child_evidence"], False)
            self.assertIs(item["methodology_support_is_promoted"], False)
            self.assertIs(item["methodology_support_is_countable"], False)
        property_records = methodology["property_records"]
        self.assertEqual(property_records["evidence_reference_count"], 5)
        self.assertEqual(
            set(property_records["source_families"]), EXPECTED_PROPERTY_FAMILIES
        )
        self.assertEqual(
            methodology["foia"]["status"], "absent_from_audited_children"
        )
        comparison = next(
            item
            for item in audit["semianalysis_public_comparison"]["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )
        self.assertEqual(
            comparison["atlas_status"],
            "partial_reviewed_method_evidence_with_material_gaps",
        )
        self.assertEqual(comparison["parity_status"], "pending")
        self.assertEqual(
            audit["semianalysis_public_comparison"]["overall_parity"]["status"],
            "pending",
        )

    def test_offline_double_reconstruction_matches_frozen_bytes(self) -> None:
        failure = AssertionError("coverage v25 attempted network access")
        with ExitStack() as stack:
            stack.enter_context(patch.object(socket, "socket", side_effect=failure))
            stack.enter_context(
                patch.object(socket, "create_connection", side_effect=failure)
            )
            stack.enter_context(patch.object(subprocess, "run", side_effect=failure))
            stack.enter_context(patch.object(subprocess, "Popen", side_effect=failure))
            first = coverage_v2.build_coverage_audit(DEFINITION)
            second = coverage_v2.build_coverage_audit(DEFINITION)
        self.assertEqual(dict(first.payloads), dict(second.payloads))
        self.assertEqual(
            dict(first.payloads),
            {path.name: path.read_bytes() for path in AUDIT.iterdir()},
        )

    def test_definition_and_support_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-v25-tamper-") as temporary:
            root = Path(temporary)
            cases = []

            def bad_tree(document: dict[str, object]) -> None:
                support = document["methodology_support_artifacts"][0]
                support["closed_tree"]["inventory_sha256"] = "0" * 64

            cases.append((bad_tree, "closed tree changed"))

            def bad_summary_hash(document: dict[str, object]) -> None:
                support = document["methodology_support_artifacts"][0]
                support["summary"]["sha256"] = "0" * 64

            cases.append((bad_summary_hash, "summary checkpoint does not match"))

            def unknown_property_evidence(document: dict[str, object]) -> None:
                document["methodology_evidence_classification"]["property_records"][0][
                    "evidence_id"
                ] = "00000000-0000-0000-0000-000000000000"

            cases.append((unknown_property_evidence, "does not exist in exact child"))

            for position, (transform, message) in enumerate(cases):
                case_root = root / str(position)
                case_root.mkdir()
                definition = self._definition_copy(case_root, transform)
                with self.subTest(message=message):
                    with self.assertRaisesRegex(coverage_v2.CoverageAuditError, message):
                        coverage_v2.build_coverage_audit(definition)

            copied_support = root / "copied-support"
            shutil.copytree(SUPPORT, copied_support)
            copied_support.chmod(0o755)
            summary = copied_support / "summary.json"
            summary.chmod(0o644)
            summary.write_bytes(summary.read_bytes() + b" ")
            summary.chmod(0o444)
            copied_support.chmod(0o555)
            case_root = root / "artifact-bytes"
            case_root.mkdir()

            def changed_support_directory(document: dict[str, object]) -> None:
                document["methodology_support_artifacts"][0]["directory"] = str(
                    copied_support
                )

            definition = self._definition_copy(
                case_root, changed_support_directory
            )
            with self.assertRaisesRegex(
                coverage_v2.CoverageAuditError, "closed tree changed"
            ):
                coverage_v2.build_coverage_audit(definition)

    def test_closed_audit_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="coverage-v25-output-") as temporary:
            copied = Path(temporary) / "audit"
            shutil.copytree(AUDIT, copied)
            copied.chmod(0o755)
            report = copied / "REPORT.md"
            report.chmod(0o644)
            report.write_bytes(report.read_bytes() + b"tamper\n")
            report.chmod(0o444)
            copied.chmod(0o555)
            with self.assertRaisesRegex(
                coverage_v2.CoverageAuditError, "artifact checkpoint mismatch"
            ):
                coverage_v2.validate_coverage_audit(copied)

    def test_legacy_v24_and_implementation_bytes_are_unchanged(self) -> None:
        for path, expected in {**CODE_PINS, **LEGACY_PINS}.items():
            with self.subTest(path=path):
                self.assertEqual(checkpoint(path), expected)
        self.assertEqual(tree_digest(BASE_AUDIT), LEGACY_TREE_SHA256)
        validated = legacy.validate_coverage_audit(
            BASE_AUDIT, definition_path=BASE_DEFINITION
        )
        self.assertEqual(validated["audit_id"], "public-open-coverage-v24")

    def test_existing_frozen_publication_is_idempotent(self) -> None:
        result = coverage_v2.write_coverage_audit(DEFINITION, AUDIT)
        self.assertEqual(result["audit_id"], "public-open-coverage-v25")
        self.assertEqual(tree_digest(AUDIT), TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
