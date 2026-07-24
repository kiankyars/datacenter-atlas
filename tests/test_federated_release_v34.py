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
federation = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.federated_release_v3"
)
core = importlib.import_module("datacenter_atlas.datacenter_atlas.federation_v34")
shim = importlib.import_module("datacenter_atlas.federation_v34")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v34.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v34"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v33.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v33"
V83_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
V83_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"
BUILDER = ROOT / "scripts/build_federation_v34.py"

GENERATED_AT = "2026-07-21T17:47:00Z"
DEFINITION_PIN = (
    1_788,
    "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82",
)
INDEX_PIN = (
    35_181,
    "6389e18f6a1085e0a2cba577e412406187ea89d017e921aba6e7fb3edede60ba",
)
MANIFEST_PIN = (
    986,
    "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
)
SIDECAR_PIN = (
    80,
    "9700de599f58cd252acf4e4e0e25d24eeecb1c28c0007fa837e76ddf9b73fb4d",
)
TREE_SHA256 = "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV34Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v34 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_v34_v33_and_v83_pins_modes_trees_and_times_are_exact(
        self,
    ) -> None:
        pins = {
            DEFINITION: DEFINITION_PIN,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_PIN,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_PIN,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_PIN,
            BASE_DEFINITION: core.BASE_DEFINITION_PIN,
            BASE_INDEX_DIR / federation.MANIFEST_FILENAME: core.BASE_MANIFEST_PIN,
            V83_DEFINITION: core.V83_DEFINITION_PIN,
            V83_RELEASE / federation.MANIFEST_FILENAME: core.V83_MANIFEST_PIN,
        }
        for path, pin in pins.items():
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual((path.stat().st_size, sha256(path)), pin, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
        self.assertEqual(core.tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(core.tree_digest(BASE_INDEX_DIR), core.BASE_TREE_SHA256)
        self.assertEqual(core.tree_digest(V83_RELEASE), core.V83_TREE_SHA256)
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

    def test_definition_is_exact_v33_successor_with_only_v83_replacement(
        self,
    ) -> None:
        accepted = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(accepted)
        expected["generated_at"] = GENERATED_AT
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == "epoch-official-open-seed-v73"
        )
        child.update(
            {
                "expected_manifest_sha256": core.V83_MANIFEST_PIN[1],
                "reference": "../../releases/2026-07-21-open-seed-v83/",
                "release_id": "epoch-official-open-seed-v83",
                "release_path": "../releases/2026-07-21-open-seed-v83",
            }
        )
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(set(current), set(accepted))
        current_by_id = {row["release_id"]: row for row in current["children"]}
        accepted_by_id = {row["release_id"]: row for row in accepted["children"]}
        self.assertEqual(
            set(current_by_id),
            {"epoch-official-open-seed-v83", "global-open-v3", "osm-fuzzy-review-v2"},
        )
        for release_id in core.UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], accepted_by_id[release_id])
            self.assertEqual(
                canonical_json(current_by_id[release_id]),
                canonical_json(accepted_by_id[release_id]),
            )
        release_ids = set(current_by_id)
        self.assertNotIn("epoch-official-open-seed-v73", release_ids)
        for version in range(74, 83):
            self.assertNotIn(f"epoch-official-open-seed-v{version}", release_ids)

    def test_counts_delta_v83_descriptor_and_status_boundaries_are_exact(
        self,
    ) -> None:
        accepted = json.loads(
            (BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text()
        )
        current = core.validate_federation_v34()
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
                "bytes": 14_812,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 506,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T17:38:10Z",
                "sha256": core.V83_MANIFEST_PIN[1],
            },
        )
        self.assertFalse(child["scope"]["review_only"])
        self.assertEqual(
            child["rights"]["license_expression"], core.LICENSE_EXPRESSION
        )
        self.assertEqual(child["rights"]["rights_notice"], core.RIGHTS_NOTICE)

    def test_v83_definition_and_public_counts_are_independently_pinned(self) -> None:
        definition_raw = V83_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, ensure_ascii=False) + "\n").encode(),
        )
        self.assertEqual(definition["release_id"], "2026-07-21-open-seed-v83")
        self.assertEqual(definition["build"]["recorded_at"], core.V83_RECORDED_AT)
        self.assertEqual(len(definition["curated_inputs"]), 441)
        manifest = json.loads((V83_RELEASE / "manifest.json").read_text())
        self.assertEqual(manifest["entities"], 905)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 474, "project": 431})
        self.assertEqual(manifest["evidence_records"], 586)
        self.assertEqual(manifest["capacity_estimates"], 542)
        self.assertEqual(manifest["construction_pipeline_records"], 462)
        self.assertEqual(manifest["resolution_candidates"], 7)
        self.assertEqual(len(manifest["source_families"]), 348)
        self.assertEqual(manifest["lifecycle_freshness_records"], 506)
        self.assertEqual(manifest["lifecycle_status_semantics"], "last_observed")
        self.assertIs(manifest["current_status_inferred"], False)

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v34-rebuild-", dir="/private/tmp"
        ) as temporary:
            reproduced = Path(temporary) / INDEX_DIR.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = federation.build_federated_release_index
                with patch.object(
                    federation, "build_federated_release_index", wraps=wrapped
                ) as rebuild:
                    built = federation.write_federated_release_index(
                        DEFINITION, reproduced
                    )
                self.assertEqual(rebuild.call_count, 2)
            self.assertEqual(built["counts"], core.EXPECTED_COUNTS)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()},
                frozen,
            )
            self.assertEqual(core.tree_digest(reproduced), TREE_SHA256)

    def test_tamper_inference_symlink_and_collisions_fail_closed(self) -> None:
        current = json.loads((INDEX_DIR / federation.INDEX_FILENAME).read_text())
        descriptor = next(
            row for row in current["releases"] if row["release_id"] == core.NEW_RELEASE_ID
        )
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "current_status_inferred must be false"
        ):
            federation._validate_descriptor(inferred, 0)

        definition_before = DEFINITION.read_bytes()
        tree_before = core.tree_digest(INDEX_DIR)
        with self.assertRaisesRegex(core.FederationV34Error, "collision"):
            core.build_and_publish_federation_v34()
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        with tempfile.TemporaryDirectory(
            prefix="federation-v34-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V83_RELEASE.name
            child_symlink.symlink_to(V83_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id=core.NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=core.V83_MANIFEST_PIN[1],
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

            collision = temporary_root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(federation.FederatedReleaseError):
                federation.write_federated_release_index(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

    def test_shim_cli_both_import_layouts_and_residue_are_exact(self) -> None:
        self.assertIs(core.validate_federation_v34, shim.validate_federation_v34)
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
            "from datacenter_atlas.federation_v34 import validate_federation_v34 as v; "
            "r=v(); "
            "assert r['counts']['source_scoped_entity_records']==16330; "
            "assert r['counts']['non_review_source_scoped_entity_records']==10200; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v83')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['lifecycle_status_semantics']=='last_observed'; "
            "assert c['manifest']['lifecycle_freshness_records']==506"
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
            if path.name.startswith(".federation-v34-private-stage-")
            or path.name == ".federation-v34.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
