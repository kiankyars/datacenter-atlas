from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


identity = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.exact_identity_decisions_v12"
)
shim = importlib.import_module("datacenter_atlas.exact_identity_decisions_v12")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
BUILDER = ROOT / "scripts/build_exact_identity_decisions_v12.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExactIdentityDecisionV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = identity.validate_exact_identity_decision_bundle()

    def test_v12_is_exact_v11_structural_successor(self) -> None:
        base = json.loads(identity.PREDECESSOR_DEFINITION.read_text())
        expected = deepcopy(base)
        expected["bundle_id"] = identity.BUNDLE_ID
        expected["recorded_at"] = identity.RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": identity.FEDERATION_INDEX_PIN[1],
            "expected_manifest_sha256": identity.FEDERATION_MANIFEST_PIN[1],
            "index_path": "../federated_indexes/2026-07-21-public-open-v36",
        }
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == identity.OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": identity.V87_MANIFEST_PIN[1],
                "release_id": identity.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v87",
            }
        )
        expected["expected"] = identity.EXPECTED_COUNTS
        current = json.loads(identity.DEFINITION.read_text())
        self.assertEqual(current, expected)
        self.assertEqual(identity.DEFINITION.read_bytes(), identity._canonical_json(expected))
        inherited = {"global-open-v3", "osm-fuzzy-review-v2"}
        base_by_id = {row["release_id"]: row for row in base["children"]}
        current_by_id = {row["release_id"]: row for row in current["children"]}
        for release_id in inherited:
            self.assertEqual(current_by_id[release_id], base_by_id[release_id])
        combined = identity.DEFINITION.read_bytes() + b"".join(
            entry.read_bytes() for entry in identity.BUNDLE.iterdir()
        )
        for token in (
            *identity.REJECTED_LINEAGE_TOKENS,
            *identity.SUPERSEDED_LINEAGE_TOKENS,
        ):
            self.assertNotIn(token, combined)

    def test_exact_pins_modes_temporal_chain_and_counts(self) -> None:
        self.assertEqual(
            (identity.DEFINITION.stat().st_size, sha256(identity.DEFINITION)),
            identity.DEFINITION_PIN,
        )
        self.assertEqual(identity.tree_digest(identity.BUNDLE), identity.BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(identity.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(identity.BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(
            {entry.name for entry in identity.BUNDLE.iterdir()},
            set(identity.ARTIFACT_PINS),
        )
        for entry in identity.BUNDLE.iterdir():
            self.assertFalse(entry.is_symlink())
            self.assertTrue(entry.is_file())
            self.assertEqual(stat.S_IMODE(entry.stat().st_mode), 0o444)
            self.assertEqual(
                (entry.stat().st_size, sha256(entry)),
                identity.ARTIFACT_PINS[entry.name],
            )

        recorded = datetime.fromisoformat(identity.RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(recorded, datetime.now(timezone.utc))
        for path in (identity.DEFINITION, identity.BUNDLE, *identity.BUNDLE.iterdir()):
            status = path.stat()
            self.assertLessEqual(
                datetime.fromtimestamp(status.st_mtime, timezone.utc), recorded
            )
            birth = getattr(status, "st_birthtime", None)
            if birth is not None:
                self.assertLessEqual(
                    datetime.fromtimestamp(birth, timezone.utc), recorded
                )
        for root in (identity.DEFINITION, identity.BUNDLE):
            self.assertGreaterEqual(
                datetime.fromtimestamp(root.stat().st_ctime, timezone.utc), recorded
            )

        self.assertEqual(self.manifest["counts"], json.loads(
            (identity.BUNDLE / identity.ACCOUNTING_FILENAME).read_text()
        ))
        predecessor = json.loads(
            (identity.PREDECESSOR_BUNDLE / identity.ACCOUNTING_FILENAME).read_text()
        )
        self.assertEqual(
            {
                key: self.manifest["counts"][key] - predecessor[key]
                for key in identity.EXPECTED_DELTA
            },
            identity.EXPECTED_DELTA,
        )
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        ):
            self.assertIsNone(self.manifest["counts"][field])
        self.assertFalse(self.manifest["scope"]["automatic_physical_site_merges"])
        self.assertFalse(self.manifest["scope"]["cross_kind_identity_union"])

    def test_six_singletons_and_four_explicit_campus_edges_are_exact(self) -> None:
        identity._validate_decision_delta(identity.BUNDLE)
        components = identity._csv_rows(identity.BUNDLE / identity.COMPONENTS_FILENAME)
        added = [
            row
            for row in components
            if row["release_id"] == identity.NEW_RELEASE_ID
            and row["stable_key"] in identity.NEW_ENTITY_CONTRACT
        ]
        self.assertEqual({row["stable_key"] for row in added}, set(identity.NEW_ENTITY_CONTRACT))
        self.assertEqual(len({row["component_id"] for row in added}), 6)
        self.assertTrue(all(row["component_member_count"] == "1" for row in added))
        self.assertTrue(all(row["typed_identity_tokens_json"] == "[]" for row in added))
        self.assertEqual(
            {row["entity_kind"] for row in added}, {"campus", "project"}
        )

        component_for = {row["stable_key"]: row["component_id"] for row in added}
        relationship_pairs = {
            (row["subject_component_id"], row["object_component_id"])
            for row in identity._csv_rows(
                identity.BUNDLE / identity.RELATIONSHIPS_FILENAME
            )
            if row["subject_component_id"]
            in {component_for[key] for key in identity.EXPECTED_TARGETS}
        }
        self.assertEqual(
            relationship_pairs,
            {
                (component_for[project], component_for[campus])
                for project, campus in identity.EXPECTED_TARGETS.items()
            },
        )
        self.assertEqual(len(relationship_pairs), 4)

        component_header = set(components[0])
        relationship_header = set(
            identity._csv_rows(identity.BUNDLE / identity.RELATIONSHIPS_FILENAME)[0]
        )
        for unsupported in (
            "latitude",
            "longitude",
            "coordinates",
            "operator",
            "owner",
            "site_owner",
            "capacity",
            "critical_it_mw",
            "physical_site_id",
        ):
            self.assertNotIn(unsupported, component_header | relationship_header)

    def test_offline_double_replay_is_byte_exact(self) -> None:
        document, raw = identity._regular_document(
            identity.DEFINITION, "identity v12 definition"
        )
        definition = identity._definition_object(document, raw)
        frozen = {entry.name: entry.read_bytes() for entry in identity.BUNDLE.iterdir()}
        failure = AssertionError("identity v12 replay attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=failure))
            wrapped = identity.carrier._prepare_bundle
            with patch.object(identity.carrier, "_prepare_bundle", wraps=wrapped) as replay:
                first, first_manifest = identity.carrier._prepare_bundle(definition)
                second, second_manifest = identity.carrier._prepare_bundle(definition)
        self.assertEqual(replay.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first, frozen)

    def test_future_tamper_symlink_collision_no_replace_and_rollback_fail_closed(
        self,
    ) -> None:
        recorded = datetime.fromisoformat(identity.RECORDED_AT.replace("Z", "+00:00"))
        with patch.object(identity, "_require_guard_state", return_value=identity._guard_state()):
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "recorded_at exceeds validation wall clock",
            ):
                identity.validate_exact_identity_decision_bundle(
                    validation_wall_clock=recorded - timedelta(seconds=1)
                )

        definition_state = (
            identity.DEFINITION.stat().st_ino,
            identity.DEFINITION.stat().st_mtime_ns,
            sha256(identity.DEFINITION),
        )
        bundle_state = identity.tree_digest(identity.BUNDLE)
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "final path already exists"
        ):
            identity.write_exact_identity_decision_bundle()

        with tempfile.TemporaryDirectory(
            prefix="identity-v12-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            copied = root / "tampered"
            shutil.copytree(identity.BUNDLE, copied)
            copied.chmod(0o755)
            component = copied / identity.COMPONENTS_FILENAME
            component.chmod(0o644)
            component.write_bytes(component.read_bytes() + b"tamper\n")
            with self.assertRaises(identity.ExactIdentityDecisionError):
                identity.carrier.validate_exact_identity_decision_bundle(
                    copied, require_frozen=False
                )

            symlink = root / "symlink"
            symlink.symlink_to(identity.BUNDLE, target_is_directory=True)
            with patch.object(
                identity, "_require_guard_state", return_value=identity._guard_state()
            ):
                with self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "bundle must be a regular directory",
                ):
                    identity.validate_exact_identity_decision_bundle(symlink)

            staged = root / "staged"
            collision = root / "collision"
            staged.write_bytes(b"new\n")
            collision.write_bytes(b"preserve\n")
            with self.assertRaises(identity.federation.FederatedReleaseError):
                identity.federation._promote_noreplace(staged, collision)
            self.assertEqual(collision.read_bytes(), b"preserve\n")
            self.assertEqual(staged.read_bytes(), b"new\n")

            occupied_bundle = root / "occupied-bundle"
            occupied_bundle.mkdir()
            occupied_definition = root / "occupied-definition"
            occupied_definition.write_text("occupied")
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError, "occupied"
            ):
                identity._rollback_bundle(occupied_bundle)
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError, "occupied"
            ):
                identity._rollback_definition(occupied_definition)

            rollback_bundle = root / "published-bundle"
            rollback_bundle.mkdir(mode=0o755)
            (rollback_bundle / "member").write_text("frozen")
            rollback_bundle.chmod(0o555)
            rolled_bundle = root / "rolled-bundle"
            with patch.object(identity, "BUNDLE", rollback_bundle):
                identity._rollback_bundle(rolled_bundle)
            self.assertFalse(rollback_bundle.exists())
            self.assertTrue(rolled_bundle.is_dir())
            self.assertEqual(stat.S_IMODE(rolled_bundle.stat().st_mode), 0o555)

            rollback_definition = root / "published-definition"
            rollback_definition.write_text("frozen")
            rolled_definition = root / "rolled-definition"
            with patch.object(identity, "DEFINITION", rollback_definition):
                identity._rollback_definition(rolled_definition)
            self.assertFalse(rollback_definition.exists())
            self.assertEqual(rolled_definition.read_text(), "frozen")

        self.assertEqual(
            (
                identity.DEFINITION.stat().st_ino,
                identity.DEFINITION.stat().st_mtime_ns,
                sha256(identity.DEFINITION),
            ),
            definition_state,
        )
        self.assertEqual(identity.tree_digest(identity.BUNDLE), bundle_state)

    def test_shim_cli_imports_and_residue(self) -> None:
        self.assertIs(
            shim.validate_exact_identity_decision_bundle,
            identity.validate_exact_identity_decision_bundle,
        )
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [sys.executable, str(BUILDER), "--validate-only"],
            cwd=WORKSPACE,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertEqual(output["bundle_id"], identity.BUNDLE_ID)
        self.assertEqual(output["recorded_at"], identity.RECORDED_AT)

        code = (
            "from datacenter_atlas.exact_identity_decisions_v12 import BUNDLE_ID, "
            "EXPECTED_COUNTS; assert BUNDLE_ID.endswith('v12'); "
            "assert EXPECTED_COUNTS['exact_source_record_components']==8496"
        )
        for working_directory in (ROOT, WORKSPACE):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        leftovers = [
            path.name
            for path in ROOT.iterdir()
            if path.name.startswith(".identity-v12-private-stage-")
            or path.name == ".exact-identity-v12.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
