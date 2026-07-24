from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
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

try:
    from datacenter_atlas.datacenter_atlas import (
        exact_identity_decisions_v11 as identity,
    )
    from datacenter_atlas import exact_identity_decisions_v11 as shim
except ModuleNotFoundError:
    from datacenter_atlas import exact_identity_decisions_v11 as identity
    import exact_identity_decisions_v11 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T23:44:08Z"
DEFINITION_SHA256 = (
    "658ca591e25045245e2709564cd11a3cdd7d338f5be11913aca4ba54a6656a40"
)
BUNDLE_TREE_SHA256 = (
    "b25b7b568df098a0405452cf3c0608d9d840ace15af120625f7650423d22f6d9"
)
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        8271,
        "83054ecf2bffa226ba774163632393321b98952f4c9155d6737dbc680b5d503e",
    ),
    "README.md": (
        629,
        "e9acb59b6c742326b55b7884c3a67f3087f0518c4aed657981aed161bdf0e0bf",
    ),
    "accounting.json": (
        981,
        "b37514dcc86a52b3254f62ff740507e609c661a0179ee931af13aa4ba9a0f258",
    ),
    "component-members.csv": (
        3706417,
        "401ab53d71c8d5e9d19ff92260878bab92cd423f7947ec6f0996d4a27cbe70ef",
    ),
    "manifest.json": (
        11441,
        "cd54ee06c75272974d2ba43859226b61965d04c7ca6c515d19e44447fe48cbb9",
    ),
    "manifest.sha256": (
        80,
        "d5b1b6944c0de9b0c2ac1aa3cbba4402fe7867d3f9d112a5d5f2f7adb2724c9a",
    ),
    "relationships.csv": (
        946965,
        "00bc28f4fc6dbd30bc5e6ca54695ffda3839dc16a5a5a04242ea629ba77e2698",
    ),
    "source-lineage.csv": (
        44698,
        "2907fd12dcfd119afa536e3dba083bef251f1b3a917bd11d315f53e9e9901fab",
    ),
    "unresolved-candidate-references.csv": (
        38421688,
        "5db0cc67f45ed9a7a85c16a4a498994c43314cac6a7d3936f08f673d2a0f11f4",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExactIdentityDecisionV11Tests(unittest.TestCase):
    def test_v11_is_exact_v10_structural_successor(self) -> None:
        recorded_at = "2026-07-21T23:44:00Z"
        base = json.loads(
            identity.PREDECESSOR_DEFINITION.read_text(encoding="utf-8")
        )
        expected = deepcopy(base)
        inherited = {
            row["release_id"]: deepcopy(row)
            for row in base["children"]
            if row["release_id"] != identity.OLD_RELEASE_ID
        }
        expected["bundle_id"] = identity.BUNDLE_ID
        expected["recorded_at"] = recorded_at
        expected["federation"] = {
            "expected_index_sha256": identity.FEDERATION_INDEX_SHA256,
            "expected_manifest_sha256": identity.FEDERATION_MANIFEST_SHA256,
            "index_path": "../federated_indexes/2026-07-21-public-open-v35",
        }
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == identity.OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": identity.V86_MANIFEST_SHA256,
                "release_id": identity.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v86",
            }
        )
        expected["expected"] = identity.EXPECTED_COUNTS
        current = identity._v11_document(recorded_at)
        self.assertEqual(current, expected)
        self.assertEqual(
            {
                row["release_id"]: row
                for row in current["children"]
                if row["release_id"] in inherited
            },
            inherited,
        )
        raw = identity._canonical_json(current)
        for token in (
            *identity.REJECTED_LINEAGE_TOKENS,
            *identity.SUPERSEDED_LINEAGE_TOKENS,
        ):
            self.assertNotIn(token, raw)

    def test_expected_counts_are_only_the_v35_delta(self) -> None:
        base = json.loads(
            (
                identity.PREDECESSOR_BUNDLE / identity.ACCOUNTING_FILENAME
            ).read_text(encoding="utf-8")
        )
        expected_delta = {
            "ambiguous_identity_candidate_references": 0,
            "canonical_topology_links": 11,
            "exact_component_reductions": 0,
            "exact_source_record_components": 22,
            "non_review_source_scoped_entity_records": 22,
            "raw_topology_links": 11,
            "release_candidate_references": 2,
            "review_only_source_scoped_entity_records": 0,
            "source_scoped_entity_records": 22,
            "unresolved_candidate_references": 2,
        }
        self.assertEqual(
            {
                key: identity.EXPECTED_COUNTS[key] - base[key]
                for key in expected_delta
            },
            expected_delta,
        )
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        ):
            self.assertIsNone(base[field])

    def test_v35_v86_and_v10_are_exactly_pinned_and_old_lineage_is_forbidden(
        self,
    ) -> None:
        self.assertEqual(identity._require_guard_state(), identity._guard_state())
        self.assertEqual(
            sha256(identity.PREDECESSOR_DEFINITION),
            identity.PREDECESSOR_DEFINITION_SHA256,
        )
        self.assertEqual(
            tree_digest(identity.PREDECESSOR_BUNDLE),
            identity.PREDECESSOR_TREE_SHA256,
        )
        self.assertEqual(
            sha256(identity.FEDERATION_DEFINITION),
            identity.FEDERATION_DEFINITION_SHA256,
        )
        self.assertEqual(
            tree_digest(identity.FEDERATION_BUNDLE),
            identity.FEDERATION_TREE_SHA256,
        )
        self.assertEqual(
            sha256(identity.V86_DEFINITION), identity.V86_DEFINITION_SHA256
        )
        self.assertEqual(
            sha256(identity.V86_RELEASE / identity.MANIFEST_FILENAME),
            identity.V86_MANIFEST_SHA256,
        )
        self.assertEqual(
            tree_digest(identity.V86_RELEASE), identity.V86_TREE_SHA256
        )
        with patch.multiple(
            identity,
            FEDERATION_DEFINITION_SHA256="",
            FEDERATION_INDEX_SHA256="",
            FEDERATION_MANIFEST_SHA256="",
            FEDERATION_TREE_SHA256="",
        ):
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "federation v35 is not final-green",
            ):
                identity._require_configured_federation()
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "forbidden lineage token"
        ):
            identity._assert_forbidden_lineage_absent(
                {"definition": b"2026-07-21-public-open-v32"}
            )
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "forbidden lineage token"
        ):
            identity._assert_forbidden_lineage_absent(
                {"definition": b"2026-07-21-public-open-v33"}
            )

    def test_frozen_pins_modes_temporal_bounds_and_final_ctimes(self) -> None:
        self.assertEqual(sha256(identity.DEFINITION), DEFINITION_SHA256)
        self.assertEqual(tree_digest(identity.BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(identity.DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(identity.BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(
            {entry.name for entry in identity.BUNDLE.iterdir()},
            identity.BUNDLE_FILES,
        )
        for entry in identity.BUNDLE.iterdir():
            self.assertFalse(entry.is_symlink())
            self.assertTrue(entry.is_file())
            self.assertEqual(stat.S_IMODE(entry.stat().st_mode), 0o444)
            self.assertEqual(
                (entry.stat().st_size, sha256(entry)), ARTIFACTS[entry.name]
            )

        recorded = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(recorded, datetime.now(timezone.utc))
        for artifact in (
            identity.DEFINITION,
            identity.BUNDLE,
            *identity.BUNDLE.iterdir(),
        ):
            status = artifact.stat()
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
        combined = identity.DEFINITION.read_bytes() + b"".join(
            entry.read_bytes() for entry in identity.BUNDLE.iterdir()
        )
        for token in (
            *identity.REJECTED_LINEAGE_TOKENS,
            *identity.SUPERSEDED_LINEAGE_TOKENS,
        ):
            self.assertNotIn(token, combined)

    def test_offline_double_replay_and_conservative_policy(self) -> None:
        failure = AssertionError("identity v11 validation attempted network access")
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
            with patch.object(
                identity.carrier, "_prepare_bundle", wraps=wrapped
            ) as replay:
                manifest = identity.validate_exact_identity_decision_bundle()
            self.assertEqual(replay.call_count, 2)

        for key, value in identity.EXPECTED_COUNTS.items():
            self.assertEqual(manifest["counts"][key], value, key)
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        ):
            self.assertIsNone(manifest["counts"][field])
        self.assertEqual(manifest["scope"], identity.POLICY)
        self.assertFalse(manifest["scope"]["automatic_physical_site_merges"])
        self.assertFalse(manifest["scope"]["cross_kind_identity_union"])
        children = {row["release_id"]: row for row in manifest["input_children"]}
        self.assertEqual(
            set(children),
            {
                identity.NEW_RELEASE_ID,
                "global-open-v3",
                "osm-fuzzy-review-v2",
            },
        )
        self.assertEqual(
            children["osm-fuzzy-review-v2"]["disposition"],
            "excluded_review_only",
        )
        self.assertEqual(
            manifest["federation_input"]["federated_index"]["sha256"],
            identity.FEDERATION_INDEX_SHA256,
        )
        federation_index = json.loads(
            (identity.FEDERATION_BUNDLE / "federated-index.json").read_text(
                encoding="utf-8"
            )
        )
        open_descriptor = next(
            row
            for row in federation_index["releases"]
            if row["release_id"] == identity.NEW_RELEASE_ID
        )
        self.assertIs(
            open_descriptor["manifest"][
                "geometry_only_representative_point_inferred"
            ],
            False,
        )

    def test_future_tamper_symlink_collision_and_write_refusal(self) -> None:
        recorded = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "recorded_at exceeds validation wall clock",
        ):
            identity.validate_exact_identity_decision_bundle(
                validation_wall_clock=recorded - timedelta(seconds=1)
            )

        with tempfile.TemporaryDirectory(
            prefix="identity-v11-fail-closed-", dir="/private/tmp"
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

        definition_state = (
            identity.DEFINITION.stat().st_ino,
            identity.DEFINITION.stat().st_mtime_ns,
            sha256(identity.DEFINITION),
        )
        bundle_state = tree_digest(identity.BUNDLE)
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "final path already exists"
        ):
            identity.write_exact_identity_decision_bundle()
        self.assertEqual(
            (
                identity.DEFINITION.stat().st_ino,
                identity.DEFINITION.stat().st_mtime_ns,
                sha256(identity.DEFINITION),
            ),
            definition_state,
        )
        self.assertEqual(tree_digest(identity.BUNDLE), bundle_state)

    def test_workspace_shim_cli_and_both_import_layouts(self) -> None:
        self.assertIs(
            shim.validate_exact_identity_decision_bundle,
            identity.validate_exact_identity_decision_bundle,
        )
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_exact_identity_decisions_v11.py",
                "--validate-only",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["bundle_id"], identity.BUNDLE_ID)

        code = (
            "from datacenter_atlas.exact_identity_decisions_v11 import "
            "validate_exact_identity_decision_bundle; "
            "m=validate_exact_identity_decision_bundle(); "
            "assert m['counts']['exact_source_record_components']==8490; "
            "assert m['counts']['unique_physical_sites'] is None"
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


if __name__ == "__main__":
    unittest.main()
