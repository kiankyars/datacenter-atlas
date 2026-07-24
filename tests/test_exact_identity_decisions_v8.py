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
        exact_identity_decisions_v4 as identity,
    )
    from datacenter_atlas import exact_identity_decisions_v4 as shim
except ModuleNotFoundError:
    from datacenter_atlas import exact_identity_decisions_v4 as identity
    import exact_identity_decisions_v4 as shim

from datacenter_atlas.datacenter_atlas.open_seed_v56 import (
    promote_noreplace,
    tree_digest,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T10:34:40Z"
DEFINITION_SHA256 = (
    "304144a09b1ec4773b662823501ac4a01505e2550d4a0270123fb20391980704"
)
BUNDLE_TREE_SHA256 = (
    "607485d7106a06dd32f31f56fd2b5ca395f76e300b3a12b3c55ab533c1fa2b0f"
)
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        6467,
        "7486a2184f5ec3bd1b1e420e3e26b8a5b1a1d3f874226fa6ef88a3195641a78d",
    ),
    "README.md": (
        629,
        "d8d173c91309e63c854a2d9ff676b8905bd94efb64f14e092012e87658f21f64",
    ),
    "accounting.json": (
        981,
        "f0102c137cf17a76994f94ac43c23c4f9b98963f956e295aaea16935a5d457fb",
    ),
    "component-members.csv": (
        3662523,
        "5d4324fc4e23d6c14176234da5758f93751deac0b980d24fff7e145eab8c3b49",
    ),
    "manifest.json": (
        11438,
        "63492e7fe633591577cdbb3f8c05c5097a52ac4f85190bdc532c869d5fe93401",
    ),
    "manifest.sha256": (
        80,
        "c097d3423f1abd3ab59d74ea3b25a96e6fd3ce267be45b55165d618bc4b4350f",
    ),
    "relationships.csv": (
        928734,
        "19bd30021a2e53e818bcf9a88b425f585087e7216c9044ec84225c35744ad80c",
    ),
    "source-lineage.csv": (
        34821,
        "7ba1516addae9eae7890782fd5e379e028c7d7eb788f7b92880672905651ce17",
    ),
    "unresolved-candidate-references.csv": (
        38420416,
        "11a3e3cb887b4ccee159535937c92e5b8e3812c6da67981c1e4148d85a76e4cb",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExactIdentityDecisionV8PreparationTests(unittest.TestCase):
    def test_v8_is_exact_v6_structural_successor(self) -> None:
        recorded_at = "2026-07-21T10:40:00Z"
        base = json.loads(
            identity.PREDECESSOR_DEFINITION.read_text(encoding="utf-8")
        )
        expected = deepcopy(base)
        expected["bundle_id"] = identity.BUNDLE_ID
        expected["recorded_at"] = recorded_at
        expected["federation"] = {
            "expected_index_sha256": identity.FEDERATION_INDEX_SHA256,
            "expected_manifest_sha256": identity.FEDERATION_MANIFEST_SHA256,
            "index_path": "../federated_indexes/2026-07-21-public-open-v31",
        }
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == identity.OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": identity.V71_MANIFEST_SHA256,
                "release_id": identity.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v71",
            }
        )
        expected["expected"] = identity.EXPECTED_COUNTS
        current = identity._v8_document(recorded_at)
        self.assertEqual(current, expected)
        raw = identity._canonical_json(current)
        for token in identity.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, raw)

    def test_expected_counts_are_the_bounded_v6_delta(self) -> None:
        base = json.loads(
            (
                identity.PREDECESSOR_BUNDLE / identity.ACCOUNTING_FILENAME
            ).read_text(encoding="utf-8")
        )
        expected_delta = {
            "ambiguous_identity_candidate_references": 0,
            "canonical_topology_links": 15,
            "exact_component_reductions": 0,
            "exact_source_record_components": 27,
            "non_review_source_scoped_entity_records": 27,
            "raw_topology_links": 15,
            "release_candidate_references": 0,
            "review_only_source_scoped_entity_records": 0,
            "source_scoped_entity_records": 27,
            "unresolved_candidate_references": 0,
        }
        self.assertEqual(
            {
                key: identity.EXPECTED_COUNTS[key] - base[key]
                for key in expected_delta
            },
            expected_delta,
        )
        self.assertIsNone(base["unique_physical_sites"])
        self.assertIsNone(base["physical_site_lower_bound"])
        self.assertIsNone(base["physical_site_upper_bound"])

    def test_unconfigured_or_rejected_federation_cannot_publish(self) -> None:
        with patch.multiple(
            identity,
            FEDERATION_DEFINITION_SHA256="",
            FEDERATION_INDEX_SHA256="",
            FEDERATION_MANIFEST_SHA256="",
            FEDERATION_TREE_SHA256="",
        ):
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "federation v31 is not final-green",
            ):
                identity._require_configured_federation()

        document = identity._v8_document("2026-07-21T10:40:00Z")
        document["federation"]["index_path"] = (
            "../federated_indexes/2026-07-21-public-open-v30"
        )
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "accepted-v6 structural successor",
        ):
            identity._definition_object(
                document, identity._canonical_json(document)
            )

    def test_timestamp_birth_mtime_and_wall_clock_guards(self) -> None:
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "must include a timezone"
        ):
            identity._wall_clock(datetime(2026, 7, 21, 10, 40))

        with tempfile.TemporaryDirectory(
            prefix="identity-v8-time-", dir="/private/tmp"
        ) as temporary:
            artifact = Path(temporary) / "artifact"
            artifact.write_bytes(b"bounded\n")
            observed = datetime.fromtimestamp(
                artifact.stat().st_mtime, timezone.utc
            )
            identity._path_timestamp_bounds(
                artifact, observed + timedelta(seconds=1), "test artifact"
            )
            with self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "after its recorded/generated timestamp",
            ):
                identity._path_timestamp_bounds(
                    artifact, observed - timedelta(seconds=1), "test artifact"
                )

    def test_collision_symlink_and_rejected_payload_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="identity-v8-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            bundle = root / "bundle"
            definition.write_bytes(b"do-not-replace\n")
            with patch.multiple(
                identity, DEFINITION=definition, BUNDLE=bundle
            ):
                with self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "refusing replacement",
                ):
                    identity._require_unpublished()
            self.assertEqual(definition.read_bytes(), b"do-not-replace\n")

            definition.unlink()
            bundle.symlink_to(identity.PREDECESSOR_BUNDLE, target_is_directory=True)
            with patch.multiple(
                identity, DEFINITION=definition, BUNDLE=bundle
            ):
                with self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "refusing replacement",
                ):
                    identity._require_unpublished()
            self.assertTrue(bundle.is_symlink())

        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError, "rejected lineage token"
        ):
            identity._assert_rejected_lineage_absent(
                {"definition": b"2026-07-21-public-open-v30"}
            )

    def test_workspace_shim_exports_hardened_carrier(self) -> None:
        self.assertIs(
            shim.validate_exact_identity_decision_bundle,
            identity.validate_exact_identity_decision_bundle,
        )
        self.assertIs(
            shim.write_exact_identity_decision_bundle,
            identity.write_exact_identity_decision_bundle,
        )

    def test_frozen_pins_modes_temporal_bounds_and_rejected_absence(self) -> None:
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
        combined = identity.DEFINITION.read_bytes() + b"".join(
            entry.read_bytes() for entry in identity.BUNDLE.iterdir()
        )
        for token in identity.REJECTED_LINEAGE_TOKENS:
            self.assertNotIn(token, combined)

    def test_offline_double_replay_child_closure_and_conservative_policy(self) -> None:
        failure = AssertionError("identity v8 validation attempted network access")
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
        self.assertFalse(
            manifest["scope"]["review_only_rows_in_public_accounting"]
        )
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
        self.assertEqual(
            manifest["federation_input"]["manifest"]["sha256"],
            identity.FEDERATION_MANIFEST_SHA256,
        )

    def test_future_tamper_symlink_and_late_collision_fail_closed(self) -> None:
        recorded = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "recorded_at exceeds validation wall clock",
        ):
            identity.validate_exact_identity_decision_bundle(
                validation_wall_clock=recorded - timedelta(seconds=1)
            )

        with tempfile.TemporaryDirectory(
            prefix="identity-v8-fail-closed-", dir="/private/tmp"
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

            stage = root / "stage"
            collision = root / "collision"
            stage.write_bytes(b"new\n")
            collision.write_bytes(b"preserve\n")
            with self.assertRaises(SystemExit):
                promote_noreplace(stage, collision)
            self.assertEqual(collision.read_bytes(), b"preserve\n")
            self.assertEqual(stage.read_bytes(), b"new\n")

        definition_state = (
            identity.DEFINITION.stat().st_ino,
            identity.DEFINITION.stat().st_mtime_ns,
            sha256(identity.DEFINITION),
        )
        bundle_state = tree_digest(identity.BUNDLE)
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "final path already exists",
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

    def test_cli_validate_only_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_exact_identity_decisions_v4.py",
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
            "from datacenter_atlas.exact_identity_decisions_v4 import "
            "validate_exact_identity_decision_bundle; "
            "m=validate_exact_identity_decision_bundle(); "
            "assert m['counts']['exact_source_record_components']==8373; "
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
