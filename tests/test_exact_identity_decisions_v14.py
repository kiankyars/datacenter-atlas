from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

identity = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.exact_identity_decisions_v14"
)
shim = importlib.import_module("datacenter_atlas.exact_identity_decisions_v14")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PREPARE_RUNNER = ROOT / "scripts/prepare_exact_identity_decisions_v14.py"
BUILD_RUNNER = ROOT / "scripts/build_exact_identity_decisions_v14.py"
assert identity.RECORDED_AT is not None
TEST_RECORDED_AT = identity.RECORDED_AT


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def live_final_state() -> dict[str, object]:
    definition_metadata = identity.DEFINITION.stat(follow_symlinks=False)
    bundle_metadata = identity.BUNDLE.stat(follow_symlinks=False)
    return {
        "definition_identity": (
            definition_metadata.st_dev,
            definition_metadata.st_ino,
            definition_metadata.st_ctime_ns,
            definition_metadata.st_mtime_ns,
            definition_metadata.st_size,
            stat.S_IMODE(definition_metadata.st_mode),
        ),
        "bundle_identity": (
            bundle_metadata.st_dev,
            bundle_metadata.st_ino,
            bundle_metadata.st_ctime_ns,
            bundle_metadata.st_mtime_ns,
            stat.S_IMODE(bundle_metadata.st_mode),
        ),
        "pins": identity._candidate_pin_report(
            identity.DEFINITION.read_bytes(), identity.BUNDLE
        ),
    }


class ExactIdentityDecisionV14Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        wrapped = identity.carrier._prepare_bundle
        with patch.object(
            identity.carrier, "_prepare_bundle", wraps=wrapped
        ) as replay:
            (
                cls.definition_raw,
                cls.payloads,
                cls.manifest,
                cls.definition,
            ) = identity._prepare_payloads(TEST_RECORDED_AT)
        cls.replay_count = replay.call_count
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="identity-v14-tests-", dir="/private/tmp"
        )
        cls.bundle = Path(cls.temporary.name) / "bundle"
        cls.bundle.mkdir(mode=0o700)
        for name, payload in cls.payloads.items():
            path = cls.bundle / name
            path.write_bytes(payload)
            path.chmod(identity.FROZEN_FILE_MODE)
        cls.bundle.chmod(identity.FROZEN_DIRECTORY_MODE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.bundle.chmod(0o700)
        for path in cls.bundle.iterdir():
            path.chmod(0o600)
        cls.temporary.cleanup()

    def test_v14_is_exact_v13_structural_successor(self) -> None:
        base = json.loads(identity.PREDECESSOR_DEFINITION.read_text())
        expected = deepcopy(base)
        expected["bundle_id"] = identity.BUNDLE_ID
        expected["recorded_at"] = TEST_RECORDED_AT
        expected["federation"] = {
            "expected_index_sha256": identity.FEDERATION_INDEX_PIN[1],
            "expected_manifest_sha256": identity.FEDERATION_MANIFEST_PIN[1],
            "index_path": "../federated_indexes/2026-07-22-public-open-v38",
        }
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == identity.OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": identity.V97_MANIFEST_PIN[1],
                "release_id": identity.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-22-open-seed-v97",
            }
        )
        expected["expected"] = identity.EXPECTED_COUNTS
        self.assertEqual(json.loads(self.definition_raw), expected)
        self.assertEqual(self.definition_raw, identity._canonical_json(expected))
        base_by_id = {row["release_id"]: row for row in base["children"]}
        current_by_id = {
            row["release_id"]: row for row in expected["children"]
        }
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_by_id[release_id], base_by_id[release_id])

    def test_exact_65_singletons_33_edges_and_source_replacements(self) -> None:
        self.assertEqual(self.replay_count, 2)
        identity._validate_decision_delta(self.bundle)
        self.assertEqual(len(identity.NEW_ENTITY_KEYS), 65)
        self.assertEqual(len(identity.NEW_PROJECT_KEYS), 33)
        self.assertEqual(
            set(identity.SOURCE_REPLACEMENT_CONTRACT),
            identity.GOODMAN_KEYS | identity.FIN04_KEYS,
        )
        self.assertEqual(
            identity.STALE_CURRENT_UNKNOWN_KEYS,
            {
                "curated:cmc-creative-space-hanoi:data-center-tower",
                (
                    "curated:edgnex-second-jakarta-ai-data-center:"
                    "phase-1-early-construction"
                ),
                "curated:oran-ai-data-center-campus:current-build",
            },
        )
        accounting = json.loads(self.payloads[identity.ACCOUNTING_FILENAME])
        for key, value in identity.EXPECTED_COUNTS.items():
            self.assertEqual(accounting[key], value)
        for field in (
            "unique_physical_sites",
            "physical_site_lower_bound",
            "physical_site_upper_bound",
        ):
            self.assertIsNone(accounting[field])
        combined = self.definition_raw + b"".join(self.payloads.values())
        for token in (
            *identity.REJECTED_LINEAGE_TOKENS,
            *identity.SUPERSEDED_LINEAGE_TOKENS,
        ):
            self.assertNotIn(token, combined)
        self.assertNotIn(identity.PEERINGDB_FORBIDDEN, combined.lower())

    def test_carrier_v6_release_and_collision_inventory_fail_closed(self) -> None:
        self.assertEqual(
            identity.carrier.EXPECTED_RELEASE_IDS,
            {
                identity.NEW_RELEASE_ID,
                "global-open-v3",
                "osm-fuzzy-review-v2",
            },
        )
        self.assertEqual(len(identity.carrier.CROSS_ROOT_SINGLETON_TOKENS), 5)
        self.assertEqual(identity.carrier.EXPECTED_SUCCESSOR_OCCURRENCES, 9)
        with patch.object(
            identity.carrier, "CROSS_ROOT_SINGLETON_TOKENS", frozenset()
        ), self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "collision inventory differs",
        ):
            identity.carrier._prepare_bundle(self.definition)

    def test_live_bundle_matches_reviewed_candidate_and_preflight_is_closed(
        self,
    ) -> None:
        guard = identity._guard_state()
        before = live_final_state()
        manifest = identity.validate_exact_identity_decision_bundle()
        self.assertEqual(manifest["counts"], self.manifest["counts"])
        self.assertEqual(
            before["pins"],
            (
                identity.DEFINITION_PIN,
                identity.ARTIFACT_PINS,
                identity.BUNDLE_TREE_SHA256,
            ),
        )
        with tempfile.TemporaryDirectory(
            prefix="identity-v14-live-preflight-", dir="/private/tmp"
        ) as temporary:
            temporary_lock = Path(temporary) / "publication.lock"
            with (
                patch.object(identity, "PUBLICATION_LOCK", temporary_lock),
                self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "preflight final path already exists",
                ),
            ):
                identity.prepare_exact_identity_decisions_v14(
                    TEST_RECORDED_AT
                )
            self.assertFalse(temporary_lock.exists())
        self.assertEqual(identity._guard_state(), guard)
        self.assertEqual(live_final_state(), before)
        self.assertFalse(identity.PUBLICATION_LOCK.exists())
        self.assertFalse(
            any(
                path.name.startswith(
                    f".{identity.DEFINITION.name}."
                )
                or path.name.startswith(f".{identity.BUNDLE.name}.")
                for parent in (identity.DEFINITION.parent, identity.BUNDLE.parent)
                for path in parent.iterdir()
            )
        )

    def test_safe_prepare_and_build_rejections_preserve_live_finals(self) -> None:
        before = live_final_state()
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        for command in (
            [
                sys.executable,
                str(PREPARE_RUNNER),
                "--publish-authorized",
            ],
            [sys.executable, str(BUILD_RUNNER)],
        ):
            completed = subprocess.run(
                command,
                cwd=WORKSPACE,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
        with self.assertRaisesRegex(
            identity.ExactIdentityDecisionError,
            "requires explicit authorization",
        ):
            identity.publish_exact_identity_decisions_v14(TEST_RECORDED_AT)
        self.assertIs(
            shim.prepare_exact_identity_decisions_v14,
            identity.prepare_exact_identity_decisions_v14,
        )
        self.assertEqual(live_final_state(), before)
        self.assertFalse(identity.PUBLICATION_LOCK.exists())

    def test_active_lock_wins_before_preflight_phase_checks(self) -> None:
        with (
            identity._bound_output_parents() as bindings,
            identity._publication_lock(bindings),
            self.assertRaisesRegex(
                identity.ExactIdentityDecisionError,
                "active identity-v14 publication lock",
            ),
        ):
            identity.prepare_exact_identity_decisions_v14(TEST_RECORDED_AT)
        self.assertFalse(identity.PUBLICATION_LOCK.exists())

    def test_descriptor_bound_cleanup_does_not_follow_parent_swap(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="identity-v14-parent-swap-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            bundles = root / "bundles"
            sources.mkdir()
            bundles.mkdir()
            definition = sources / "definition.json"
            bundle = bundles / "bundle"
            publication_lock = root / "lock"
            with (
                patch.object(identity, "DEFINITION", definition),
                patch.object(identity, "BUNDLE", bundle),
                patch.object(identity, "PUBLICATION_LOCK", publication_lock),
                identity._bound_output_parents() as bindings,
            ):
                stage, stage_identity = identity._create_definition_stage(
                    b"owned\n", parent_bindings=bindings
                )
                original = root / "sources-original"
                sources.rename(original)
                sources.mkdir()
                foreign = sources / stage.name
                foreign.write_bytes(b"foreign\n")
                binding = bindings["definition"]
                identity._discard_bound_file(
                    binding, stage.name, stage_identity
                )
                self.assertTrue(foreign.exists())
                self.assertEqual(foreign.read_bytes(), b"foreign\n")
                self.assertFalse((original / stage.name).exists())
                with self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "parent identity changed",
                ):
                    identity._assert_parent_bindings(
                        bindings, label="parent swap regression"
                    )

    def test_no_replace_collision_preserves_destination_and_stage(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="identity-v14-collision-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            bundles = root / "bundles"
            sources.mkdir()
            bundles.mkdir()
            definition = sources / "definition.json"
            bundle = bundles / "bundle"
            publication_lock = root / "lock"
            with (
                patch.object(identity, "DEFINITION", definition),
                patch.object(identity, "BUNDLE", bundle),
                patch.object(identity, "PUBLICATION_LOCK", publication_lock),
                identity._bound_output_parents() as bindings,
            ):
                stage, stage_identity = identity._create_definition_stage(
                    b"stage\n", parent_bindings=bindings
                )
                definition.write_bytes(b"preserve\n")
                with self.assertRaisesRegex(
                    identity.ExactIdentityDecisionError,
                    "final path collision",
                ):
                    identity._promote_noreplace(
                        stage,
                        definition,
                        directory=False,
                        parent_bindings=bindings,
                    )
                self.assertEqual(definition.read_bytes(), b"preserve\n")
                binding = identity._binding_for_parent(bindings, sources)
                self.assertTrue(
                    identity._has_bound_identity(
                        binding,
                        stage.name,
                        stage_identity,
                        directory=False,
                    )
                )
                identity._discard_bound_file(
                    binding, stage.name, stage_identity
                )

    def test_reporting_failure_rolls_both_finals_back(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="identity-v14-reporting-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            bundles = root / "bundles"
            sources.mkdir()
            bundles.mkdir()
            definition = sources / "definition.json"
            bundle = bundles / "bundle"
            publication_lock = root / "lock"
            target = (
                datetime.now(UTC) + timedelta(seconds=1)
            ).replace(microsecond=0)
            if target <= datetime.now(UTC):
                target += timedelta(seconds=1)
            timestamp = target.isoformat().replace("+00:00", "Z")
            guard = identity._guard_state()
            failure = RuntimeError("reporting failed")
            with ExitStack() as stack:
                stack.enter_context(patch.object(identity, "DEFINITION", definition))
                stack.enter_context(patch.object(identity, "BUNDLE", bundle))
                stack.enter_context(
                    patch.object(identity, "PUBLICATION_LOCK", publication_lock)
                )
                stack.enter_context(patch.object(identity, "RECORDED_AT", None))
                stack.enter_context(
                    patch.object(
                        identity,
                        "_prepare_payloads",
                        return_value=(
                            self.definition_raw,
                            self.payloads,
                            self.manifest,
                            self.definition,
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(
                        identity, "_require_guard_state", return_value=guard
                    )
                )
                stack.enter_context(
                    patch.object(
                        identity,
                        "_validate_payload_bundle",
                        return_value=self.manifest,
                    )
                )
                stack.enter_context(
                    patch.object(
                        identity,
                        "validate_exact_identity_decision_bundle",
                        return_value=self.manifest,
                    )
                )
                stack.enter_context(
                    patch.object(identity, "_require_candidate_pins")
                )
                with self.assertRaisesRegex(RuntimeError, "reporting failed"):
                    identity.publish_exact_identity_decisions_v14(
                        timestamp,
                        publication_authorized=True,
                        completion_callback=lambda _result: (_ for _ in ()).throw(
                            failure
                        ),
                    )
            self.assertFalse(definition.exists())
            self.assertFalse(bundle.exists())
            self.assertFalse(publication_lock.exists())
            self.assertFalse(
                any(
                    path.name.startswith(".")
                    for parent in (sources, bundles)
                    for path in parent.iterdir()
                )
            )

    def test_modes_and_unsupported_fields_remain_absent(self) -> None:
        self.assertEqual(stat.S_IMODE(self.bundle.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in self.bundle.iterdir()
            )
        )
        components = identity._csv_rows(
            self.bundle / identity.COMPONENTS_FILENAME
        )
        relationships = identity._csv_rows(
            self.bundle / identity.RELATIONSHIPS_FILENAME
        )
        fields = set(components[0]) | set(relationships[0])
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
            "status",
        ):
            self.assertNotIn(unsupported, fields)


if __name__ == "__main__":
    unittest.main()
