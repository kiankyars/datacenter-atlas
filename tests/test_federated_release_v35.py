from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import UTC, datetime
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


legacy = importlib.import_module("datacenter_atlas.datacenter_atlas.federated_release")
federation_v3 = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.federated_release_v3"
)
federation = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.federated_release_v4"
)
carrier_shim = importlib.import_module("datacenter_atlas.federated_release_v4")
core = importlib.import_module("datacenter_atlas.datacenter_atlas.federation_v35")
shim = importlib.import_module("datacenter_atlas.federation_v35")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v35.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v35"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v34.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v34"
V86_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
CARRIER_SOURCE = ROOT / "datacenter_atlas/federated_release_v4.py"
BUILDER = ROOT / "scripts/build_federation_v35.py"

GENERATED_AT = "2026-07-21T20:45:00Z"
CARRIER_SOURCE_PIN = (
    17_669,
    "af10b118a5941b7d9b021bb7301d58082ac738160afc9a6dc1101213192f516a",
)
DEFINITION_PIN = (
    1_788,
    "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f",
)
INDEX_PIN = (
    36_400,
    "f7cf31d905bf497a6bc7ba3db7f22fb8e281e7b1452e1f2853ea79af1d9ea802",
)
MANIFEST_PIN = (
    986,
    "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388",
)
SIDECAR_PIN = (
    80,
    "52def2639a47b81caaa2813a19cff9b5c6ca1c6de125bdb0c3897198ed86cd3b",
)
TREE_SHA256 = "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV35Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v35 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_v35_v34_v86_and_carrier_pins_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_PIN,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_PIN,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_PIN,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_PIN,
            BASE_DEFINITION: core.BASE_DEFINITION_PIN,
            BASE_INDEX_DIR / federation.MANIFEST_FILENAME: core.BASE_MANIFEST_PIN,
            V86_DEFINITION: core.V86_DEFINITION_PIN,
            V86_RELEASE / federation.MANIFEST_FILENAME: core.V86_MANIFEST_PIN,
        }
        for path, pin in pins.items():
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual((path.stat().st_size, sha256(path)), pin, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
        self.assertEqual((CARRIER_SOURCE.stat().st_size, sha256(CARRIER_SOURCE)), CARRIER_SOURCE_PIN)
        self.assertEqual(stat.S_IMODE(CARRIER_SOURCE.stat().st_mode), 0o644)
        self.assertEqual(core.tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(core.tree_digest(BASE_INDEX_DIR), core.BASE_TREE_SHA256)
        self.assertEqual(core.tree_digest(V86_RELEASE), core.V86_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            federation.FEDERATED_BUNDLE_FILES,
        )
        for path in INDEX_DIR.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated, datetime.now(UTC))
        for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.iterdir()):
            details = path.stat()
            born = datetime.fromtimestamp(details.st_birthtime, UTC)
            modified = datetime.fromtimestamp(details.st_mtime, UTC)
            self.assertLessEqual(max(born, modified), generated, path)
        self.assertGreaterEqual(
            datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), generated
        )
        self.assertGreaterEqual(
            datetime.fromtimestamp(INDEX_DIR.stat().st_ctime, UTC), generated
        )

    def test_definition_is_exact_v34_successor_with_only_v86_replacement(self) -> None:
        accepted = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(accepted)
        expected["generated_at"] = GENERATED_AT
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == "epoch-official-open-seed-v83"
        )
        child.update(
            {
                "expected_manifest_sha256": core.V86_MANIFEST_PIN[1],
                "reference": "../../releases/2026-07-21-open-seed-v86/",
                "release_id": "epoch-official-open-seed-v86",
                "release_path": "../releases/2026-07-21-open-seed-v86",
            }
        )
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        current_by_id = {row["release_id"]: row for row in current["children"]}
        accepted_by_id = {row["release_id"]: row for row in accepted["children"]}
        self.assertEqual(set(current_by_id), core.UNCHANGED_RELEASE_IDS | {core.NEW_RELEASE_ID})
        for release_id in core.UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], accepted_by_id[release_id])
            self.assertEqual(
                canonical_json(current_by_id[release_id]),
                canonical_json(accepted_by_id[release_id]),
            )
        self.assertNotIn(core.OLD_RELEASE_ID, current_by_id)

    def test_counts_delta_descriptor_and_non_inference_guards_are_exact(self) -> None:
        accepted = json.loads((BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text())
        current = core.validate_federation_v35()
        self.assertEqual(current["counts"], core.EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertEqual(
            {
                key: current["counts"][key] - accepted["counts"][key]
                for key in core.EXPECTED_DELTA
            },
            core.EXPECTED_DELTA,
        )
        current_by_id = {row["release_id"]: row for row in current["releases"]}
        accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
        for release_id in core.UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], accepted_by_id[release_id])
        child = current_by_id[core.NEW_RELEASE_ID]
        self.assertEqual(child["counts"], core.EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            child["manifest"],
            {
                "as_of": "2026-07-21",
                "bytes": 15_531,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "geometry_only_representative_point_inferred": False,
                "lifecycle_freshness_records": 517,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": core.V86_RECORDED_AT,
                "sha256": core.V86_MANIFEST_PIN[1],
            },
        )
        self.assertFalse(child["scope"]["review_only"])
        self.assertEqual(child["rights"]["license_expression"], core.LICENSE_EXPRESSION)
        self.assertEqual(child["rights"]["rights_notice"], core.RIGHTS_NOTICE)

    def test_v86_definition_public_counts_and_geometry_guard_are_pinned(self) -> None:
        definition_raw = V86_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, ensure_ascii=False) + "\n").encode(),
        )
        self.assertEqual(definition["release_id"], "2026-07-21-open-seed-v86")
        self.assertEqual(definition["build"]["recorded_at"], core.V86_RECORDED_AT)
        self.assertEqual(len(definition["curated_inputs"]), 452)
        manifest = json.loads((V86_RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["entities"], 927)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 485, "project": 442})
        self.assertEqual(manifest["evidence_records"], 611)
        self.assertEqual(manifest["capacity_estimates"], 552)
        self.assertEqual(manifest["construction_pipeline_records"], 469)
        self.assertEqual(manifest["resolution_candidates"], 9)
        self.assertEqual(len(manifest["source_families"]), 366)
        self.assertEqual(manifest["lifecycle_freshness_records"], 517)
        self.assertIs(manifest["current_status_inferred"], False)
        self.assertIs(manifest["geometry_only_representative_point_inferred"], False)

    def test_v4_isolated_extension_and_offline_double_reconstruction(self) -> None:
        self.assertIs(
            federation.validate_federated_release_index,
            carrier_shim.validate_federated_release_index,
        )
        child = legacy._ChildDefinition(
            release_id=core.NEW_RELEASE_ID,
            release_path=V86_RELEASE,
            reference="../../releases/2026-07-21-open-seed-v86/",
            expected_manifest_sha256=core.V86_MANIFEST_PIN[1],
            license_expression=core.LICENSE_EXPRESSION,
            rights_notice=core.RIGHTS_NOTICE,
        )
        with self.assertRaisesRegex(
            federation_v3.FederatedReleaseError, "manifest schema is invalid"
        ):
            federation_v3._inspect_child(child)
        self.assertIs(
            federation._inspect_child(child)["manifest"][
                federation.GEOMETRY_NON_INFERENCE_FIELD
            ],
            False,
        )

        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        replay_payloads = []
        with tempfile.TemporaryDirectory(
            prefix="federation-v35-rebuild-", dir="/private/tmp"
        ) as temporary:
            for number in range(2):
                reproduced = Path(temporary) / f"replay-{number}"
                with ExitStack() as stack:
                    self._offline(stack)
                    built = federation.write_federated_release_index(
                        DEFINITION, reproduced
                    )
                self.assertEqual(built["counts"], core.EXPECTED_COUNTS)
                payloads = {
                    path.name: path.read_bytes() for path in reproduced.iterdir()
                }
                self.assertEqual(payloads, frozen)
                self.assertEqual(core.tree_digest(reproduced), TREE_SHA256)
                replay_payloads.append(payloads)
        self.assertEqual(replay_payloads[0], replay_payloads[1])

    def test_tamper_symlink_collisions_cli_imports_and_residue_fail_closed(self) -> None:
        current = json.loads((INDEX_DIR / federation.INDEX_FILENAME).read_text())
        descriptor = next(
            row for row in current["releases"] if row["release_id"] == core.NEW_RELEASE_ID
        )
        inferred = deepcopy(descriptor)
        inferred["manifest"][federation.GEOMETRY_NON_INFERENCE_FIELD] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "must not be inferred"
        ):
            federation._validate_descriptor(inferred, 0)
        missing = deepcopy(current)
        next(
            row for row in missing["releases"] if row["release_id"] == core.NEW_RELEASE_ID
        )["manifest"].pop(federation.GEOMETRY_NON_INFERENCE_FIELD)
        accepted = json.loads((BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text())
        with self.assertRaisesRegex(core.FederationV35Error, "inferred a current status"):
            core._validate_counts(missing, accepted)

        definition_before = DEFINITION.read_bytes()
        tree_before = core.tree_digest(INDEX_DIR)
        with self.assertRaisesRegex(core.FederationV35Error, "collision"):
            core.build_and_publish_federation_v35()
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        with tempfile.TemporaryDirectory(
            prefix="federation-v35-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V86_RELEASE.name
            child_symlink.symlink_to(V86_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id=core.NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=core.V86_MANIFEST_PIN[1],
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "regular directory"
            ):
                federation._inspect_child(child_definition)

            copied = temporary_root / "tampered"
            shutil.copytree(INDEX_DIR, copied)
            copied.chmod(0o755)
            copied_index = copied / federation.INDEX_FILENAME
            copied_index.chmod(0o644)
            copied_index.write_bytes(copied_index.read_bytes() + b" ")
            with self.assertRaisesRegex(
                federation.FederatedReleaseError,
                "not canonical|checkpoint does not match",
            ):
                federation.validate_federated_release_index(
                    copied, require_frozen=False
                )

        self.assertIs(core.validate_federation_v35, shim.validate_federation_v35)
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--verify"],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["counts"], core.EXPECTED_COUNTS)
        self.assertEqual(output["generated_at"], GENERATED_AT)

        code = (
            "from datacenter_atlas.federation_v35 import validate_federation_v35 as v; "
            "r=v(); assert r['counts']['source_scoped_entity_records']==16352; "
            "assert r['counts']['non_review_source_scoped_entity_records']==10222; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v86')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['geometry_only_representative_point_inferred'] is False"
        )
        for working_directory in (ROOT, WORKSPACE):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        leftovers = [
            path.name
            for path in ROOT.iterdir()
            if path.name.startswith(".federation-v35-private-stage-")
            or path.name == ".federation-v35.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
