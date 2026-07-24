from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from datacenter_atlas.exact_identity_decisions import (
    ACCOUNTING_FILENAME,
    BUNDLE_FILES,
    COMPONENTS_FILENAME,
    MANIFEST_FILENAME,
    POLICY,
    RELATIONSHIPS_FILENAME,
    UNRESOLVED_FILENAME,
    validate_exact_identity_decision_bundle,
    write_exact_identity_decision_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v2.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v2"
BASE_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v1.json"
)
BASE_BUNDLE = ROOT / "exact_identity_decisions/2026-07-20-public-open-v1"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v24"
V55_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"

RECORDED_AT = "2026-07-20T20:08:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v49"
NEW_RELEASE_ID = "epoch-official-open-seed-v55"
PINS = {
    DEFINITION: "65ffef9681c982b2149591706542c6b8277eedc22de63b2ffd2253ec94332a03",
    BASE_DEFINITION: "c5a1adee3366bfa55407904074464d4d6c0c52bbbee1b523544721117582b428",
    BASE_BUNDLE
    / MANIFEST_FILENAME: "2f892bdfd427321052676909b2109d2cdcc0fef32a80f1a805a58a621977fe96",
    FEDERATION
    / "federated-index.json": "eb0fce0a9ccac0d22290efeba71959f811d7b01b179437b90bd96c12aa177f0d",
    FEDERATION
    / MANIFEST_FILENAME: "46e57834a7133eb00a27d5db900018379c040d1834b202c018617af8a5cde5b1",
    V55_RELEASE
    / MANIFEST_FILENAME: "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b",
}
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        4_066,
        "ce1337668dbeadd269b9830f6110232c2d3d61fc42c5e77dbe0f66ae77b81c4e",
    ),
    "README.md": (
        628,
        "a130e1b75511c425d21aeffbb37957d0f180cd54207c1f342f9abe324e9a7525",
    ),
    "accounting.json": (
        980,
        "e01dc4f0381d3ff4449fe8d5acbce6bb85584f2e164bdcf660efa96da19e0e6e",
    ),
    "component-members.csv": (
        3_608_498,
        "2a02b6b7deec89a7d356426ce73bc54c481c0c5043ee240d07651604f0c46580",
    ),
    "manifest.json": (
        11_274,
        "43724ed405b77ae64505a05a708e514bbdcf9c13044c3255908563eddb5e7d5c",
    ),
    "manifest.sha256": (
        80,
        "8a3dcb915d906e816663f2c9a299db14d20e72e06771670c69184fd495081f55",
    ),
    "relationships.csv": (
        904_941,
        "295ef67a51e288ff623893a547509836d1b51e2f921a6b9250e136a9b2fc5ce1",
    ),
    "source-lineage.csv": (
        24_265,
        "8bed3fadad26c96e3f36516bf0ed84e723619f72fb49a30ce99a83e2f5ba25a9",
    ),
    "unresolved-candidate-references.csv": (
        38_419_568,
        "50e6ae8e193323ff44b34c8a98006b53984001408dfe8c51b0c7e2352592a215",
    ),
}
EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2_315,
    "exact_component_reductions": 1_732,
    "exact_source_record_components": 8_226,
    "non_review_source_scoped_entity_records": 9_958,
    "raw_topology_links": 2_720,
    "release_candidate_references": 100_409,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_088,
    "unresolved_candidate_references": 100_536,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 17,
    "exact_component_reductions": 0,
    "exact_source_record_components": 34,
    "non_review_source_scoped_entity_records": 34,
    "raw_topology_links": 17,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 34,
    "unresolved_candidate_references": 0,
}
NEW_OCCURRENCES = {
    f"{NEW_RELEASE_ID}:8986c3e6-998c-5ce4-9e2e-0eab52e3daa0": "campus",
    f"{NEW_RELEASE_ID}:462ba91a-e5a2-58f6-8e73-c9b8bce5564c": "project",
    f"{NEW_RELEASE_ID}:33d64034-dbcb-5143-ae89-6f20b8a59a8f": "campus",
    f"{NEW_RELEASE_ID}:4d4321d8-bdec-5073-b608-12ce8ed20e70": "project",
}
FORBIDDEN = (
    "epoch-official-open-seed-v49",
    "epoch-official-open-seed-v54",
    "federated_indexes/2026-07-20-public-open-v23",
    "releases/2026-07-20-open-seed-v49",
    "releases/2026-07-20-open-seed-v54",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class ExactIdentityDecisionV2Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("exact-identity v2 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_double_offline_reproduction_and_modes(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(BUNDLE.is_symlink())
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        frozen = {}
        for path in BUNDLE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
            frozen[path.name] = path.read_bytes()

        with ExitStack() as stack:
            self._offline(stack)
            first = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
            second = validate_exact_identity_decision_bundle(
                BUNDLE, definition_path=DEFINITION, verify_inputs=True
            )
            idempotent = write_exact_identity_decision_bundle(DEFINITION, BUNDLE)
        self.assertEqual(first, second)
        self.assertEqual(first, idempotent)
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )
        payload = b"".join([DEFINITION.read_bytes(), *frozen.values()])
        for marker in FORBIDDEN:
            self.assertNotIn(marker.encode(), payload)
        self.assertEqual(first["scope"], POLICY)
        self.assertIsNone(first["counts"]["unique_physical_sites"])
        self.assertIsNone(first["counts"]["physical_site_lower_bound"])
        self.assertIsNone(first["counts"]["physical_site_upper_bound"])
        for key, expected in EXPECTED_COUNTS.items():
            self.assertEqual(first["counts"][key], expected, key)

    def test_definition_is_exact_v1_to_v55_transition_and_counts(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected["bundle_id"] = "2026-07-20-public-open-v2"
        expected["recorded_at"] = RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": PINS[FEDERATION / "federated-index.json"],
            "expected_manifest_sha256": PINS[FEDERATION / MANIFEST_FILENAME],
            "index_path": "../federated_indexes/2026-07-20-public-open-v24",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[V55_RELEASE / MANIFEST_FILENAME],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v55",
            }
        )
        expected["expected"] = EXPECTED_COUNTS
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)

        base_accounting = json.loads((BASE_BUNDLE / ACCOUNTING_FILENAME).read_text())
        accounting = json.loads((BUNDLE / ACCOUNTING_FILENAME).read_text())
        self.assertEqual(
            {key: accounting[key] - base_accounting[key] for key in EXPECTED_DELTA},
            EXPECTED_DELTA,
        )
        self.assertEqual(accounting["exact_component_reductions"], 1_732)
        self.assertIsNone(accounting["unique_physical_sites"])
        self.assertIsNone(accounting["physical_site_lower_bound"])
        self.assertIsNone(accounting["physical_site_upper_bound"])
        self.assertEqual(base["expected"]["exact_component_reductions"], 1_732)

    def test_new_sources_create_exact_components_and_explicit_topology_only(
        self,
    ) -> None:
        with (BUNDLE / COMPONENTS_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            rows = {
                row["occurrence_id"]: row
                for row in csv.DictReader(source)
                if row["occurrence_id"] in NEW_OCCURRENCES
            }
        self.assertEqual(set(rows), set(NEW_OCCURRENCES))
        for occurrence_id, kind in NEW_OCCURRENCES.items():
            row = rows[occurrence_id]
            self.assertEqual(row["entity_kind"], kind)
            self.assertEqual(row["component_member_count"], "1")
            self.assertEqual(row["typed_identity_tokens_json"], "[]")
            self.assertEqual(row["ambiguous_identity_tokens_json"], "[]")

        component_ids = {row["component_id"] for row in rows.values()}
        with (BUNDLE / RELATIONSHIPS_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            relationships = [
                row
                for row in csv.DictReader(source)
                if row["subject_component_id"] in component_ids
                or row["object_component_id"] in component_ids
            ]
        self.assertEqual(len(relationships), 2)
        self.assertEqual(
            {row["relationship_type"] for row in relationships}, {"project_targets"}
        )
        self.assertTrue(
            all(row["decision_basis"] == "explicit_parent" for row in relationships)
        )

        with (BUNDLE / UNRESOLVED_FILENAME).open(
            newline="", encoding="utf-8"
        ) as source:
            reader = csv.DictReader(source)
            self.assertFalse(
                {"name", "latitude", "longitude", "distance", "score"}
                & set(reader.fieldnames or [])
            )

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.exact_identity_decisions"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.exact_identity_decisions"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_exact_identity_decision_bundle; "
                f"result=validate_exact_identity_decision_bundle(Path({str(BUNDLE)!r}), "
                f"definition_path=Path({str(DEFINITION)!r}), verify_inputs=False); "
                "assert result['counts']['exact_source_record_components']==8226; "
                "assert result['counts']['unique_physical_sites'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
