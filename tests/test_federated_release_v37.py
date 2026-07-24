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
carrier_v4 = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.federated_release_v4"
)
federation = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.federated_release_v5"
)
carrier_shim = importlib.import_module("datacenter_atlas.federated_release_v5")
core = importlib.import_module("datacenter_atlas.datacenter_atlas.federation_v37")
shim = importlib.import_module("datacenter_atlas.federation_v37")
open_seed = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v92")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v37.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v37"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v36.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v36"
V92_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v92.json"
V92_RELEASE = ROOT / "releases/2026-07-21-open-seed-v92"
V87_RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
V91_RELEASE = ROOT / "releases/2026-07-21-open-seed-v91"
CARRIER_SOURCE = ROOT / "datacenter_atlas/federated_release_v5.py"
BUILDER = ROOT / "scripts/build_federation_v37.py"

CARRIER_SOURCE_PIN = (
    13_330,
    "b2984555b053d0de64cac0e747fcec02e5ee133983ccf23a44f369e897b1f851",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV37Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v37 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_v37_v36_v92_and_carrier_pins_are_exact(self) -> None:
        pins = {
            DEFINITION: core.DEFINITION_PIN,
            INDEX_DIR / federation.INDEX_FILENAME: core.INDEX_PIN,
            INDEX_DIR / federation.MANIFEST_FILENAME: core.MANIFEST_PIN,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: core.SIDECAR_PIN,
            BASE_DEFINITION: core.BASE_DEFINITION_PIN,
            BASE_INDEX_DIR / federation.MANIFEST_FILENAME: core.BASE_MANIFEST_PIN,
            V92_DEFINITION: core.V92_DEFINITION_PIN,
            V92_RELEASE / federation.MANIFEST_FILENAME: core.V92_MANIFEST_PIN,
        }
        for path, pin in pins.items():
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual((path.stat().st_size, sha256(path)), pin, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
        self.assertEqual(
            (CARRIER_SOURCE.stat().st_size, sha256(CARRIER_SOURCE)),
            CARRIER_SOURCE_PIN,
        )
        self.assertEqual(stat.S_IMODE(CARRIER_SOURCE.stat().st_mode), 0o644)
        self.assertEqual(core.tree_digest(INDEX_DIR), core.TREE_SHA256)
        self.assertEqual(core.tree_digest(BASE_INDEX_DIR), core.BASE_TREE_SHA256)
        self.assertEqual(core.tree_digest(V92_RELEASE), core.V92_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()},
            federation.FEDERATED_BUNDLE_FILES,
        )
        for path in INDEX_DIR.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        generated = datetime.fromisoformat(core.GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated, datetime.now(UTC))
        for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.iterdir()):
            details = path.stat()
            born = datetime.fromtimestamp(details.st_birthtime, UTC)
            modified = datetime.fromtimestamp(details.st_mtime, UTC)
            self.assertLessEqual(max(born, modified), generated, path)
        for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.rglob("*")):
            self.assertGreaterEqual(
                datetime.fromtimestamp(path.stat().st_ctime, UTC), generated, path
            )

    def test_definition_is_exact_v36_successor_with_only_v92_replacement(self) -> None:
        accepted = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(accepted)
        expected["generated_at"] = core.GENERATED_AT
        child = next(
            row
            for row in expected["children"]
            if row["release_id"] == core.OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": core.V92_MANIFEST_PIN[1],
                "reference": "../../releases/2026-07-21-open-seed-v92/",
                "release_id": core.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v92",
            }
        )
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        current_by_id = {row["release_id"]: row for row in current["children"]}
        accepted_by_id = {row["release_id"]: row for row in accepted["children"]}
        self.assertEqual(
            set(current_by_id), core.UNCHANGED_RELEASE_IDS | {core.NEW_RELEASE_ID}
        )
        for release_id in core.UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], accepted_by_id[release_id])
            self.assertEqual(
                canonical_json(current_by_id[release_id]),
                canonical_json(accepted_by_id[release_id]),
            )
        self.assertNotIn(core.OLD_RELEASE_ID, current_by_id)

    def test_counts_delta_descriptor_and_claim_guards_are_exact(self) -> None:
        accepted = json.loads((BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text())
        current = core.validate_federation_v37()
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
                "as_of": "2026-07-22",
                "bytes": 16_558,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "geometry_only_representative_point_inferred": False,
                "lifecycle_freshness_records": 550,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": core.V92_RECORDED_AT,
                "sha256": core.V92_MANIFEST_PIN[1],
            },
        )
        serialized = canonical_json(current).decode().casefold()
        self.assertTrue(all(marker not in serialized for marker in core.BANNED_CLAIMS))

    def test_v87_to_v92_lineage_capacity_and_v5_carrier_are_exact(self) -> None:
        core._validate_v92_provenance()
        definition = json.loads(V92_DEFINITION.read_text())
        base_definition = json.loads(open_seed.BASE_DEFINITION.read_text())
        self.assertEqual(
            definition["curated_inputs"][:480], base_definition["curated_inputs"]
        )
        self.assertEqual(
            definition["curated_inputs"][480:],
            [
                {"path": path, "sha256": open_seed.ADDITION_PINS[path][1]}
                for path in open_seed.ADDITION_ORDER
            ],
        )
        entities = {
            row["stable_key"]: row
            for row in core._csv_rows(V92_RELEASE / "entities.csv")
            if row["stable_key"] in open_seed.ADDED_ENTITY_KEYS
        }
        self.assertEqual(set(entities), open_seed.ADDED_ENTITY_KEYS)
        self.assertEqual(len(entities), 10)
        self.assertTrue(
            all(
                key.startswith("curated:")
                and not row["latitude"]
                and not row["longitude"]
                and row["geometry_json"] == "null"
                for key, row in entities.items()
            )
        )
        for key, expected in core.EXPECTED_CAPACITY_EXPORT.items():
            capacity = json.loads(entities[key]["capacity_estimates_json"])
            self.assertEqual(len(capacity), 1)
            self.assertEqual(
                (
                    capacity[0]["metric"],
                    capacity[0]["stage"],
                    capacity[0]["unit"],
                    capacity[0]["base"],
                ),
                expected,
            )
        self.assertEqual(
            (V92_RELEASE / "resolution_candidates.csv").read_bytes(),
            (V91_RELEASE / "resolution_candidates.csv").read_bytes(),
        )
        self.assertEqual(
            (V92_RELEASE / "resolution_candidates.json").read_bytes(),
            (V91_RELEASE / "resolution_candidates.json").read_bytes(),
        )

        child = legacy._ChildDefinition(
            release_id=core.NEW_RELEASE_ID,
            release_path=V92_RELEASE,
            reference="../../releases/2026-07-21-open-seed-v92/",
            expected_manifest_sha256=core.V92_MANIFEST_PIN[1],
            license_expression=core.LICENSE_EXPRESSION,
            rights_notice=core.RIGHTS_NOTICE,
        )
        with self.assertRaisesRegex(
            carrier_v4.FederatedReleaseError, "manifest schema is invalid"
        ):
            carrier_v4._inspect_child(child)
        self.assertEqual(federation._inspect_child(child)["counts"], core.EXPECTED_OPEN_COUNTS)

        manifest = json.loads((V92_RELEASE / "manifest.json").read_text())
        manifest["base_rows_frozen"] = False
        manifest_raw = canonical_json(manifest)
        with tempfile.TemporaryDirectory(
            prefix="federation-v37-v5-tamper-", dir="/private/tmp"
        ) as temporary:
            shadow = Path(temporary) / "release"
            shadow.mkdir()
            (shadow / "manifest.json").write_bytes(manifest_raw)
            tampered = legacy._ChildDefinition(
                release_id=core.NEW_RELEASE_ID,
                release_path=shadow,
                reference=child.reference,
                expected_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                license_expression=core.LICENSE_EXPRESSION,
                rights_notice=core.RIGHTS_NOTICE,
            )
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "base_rows_frozen must be true"
            ):
                federation._inspect_child(tampered)

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        self.assertIs(
            federation.validate_federated_release_index,
            carrier_shim.validate_federated_release_index,
        )
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        replay_payloads = []
        with tempfile.TemporaryDirectory(
            prefix="federation-v37-rebuild-", dir="/private/tmp"
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
                self.assertEqual(core.tree_digest(reproduced), core.TREE_SHA256)
                replay_payloads.append(payloads)
        self.assertEqual(replay_payloads[0], replay_payloads[1])

    def test_tamper_collision_rollback_cli_imports_and_residue_fail_closed(self) -> None:
        current = json.loads((INDEX_DIR / federation.INDEX_FILENAME).read_text())
        accepted = json.loads((BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text())
        missing = deepcopy(current)
        next(
            row
            for row in missing["releases"]
            if row["release_id"] == core.NEW_RELEASE_ID
        )["manifest"].pop(federation.GEOMETRY_NON_INFERENCE_FIELD)
        with self.assertRaisesRegex(core.FederationV37Error, "inferred"):
            core._validate_counts(missing, accepted)
        with self.assertRaisesRegex(core.FederationV37Error, "completeness claim"):
            core._validate_no_completeness_claims(
                {"unsupported_claim": "SemiAnalysis parity"}
            )

        definition_before = DEFINITION.read_bytes()
        tree_before = core.tree_digest(INDEX_DIR)
        with self.assertRaisesRegex(core.FederationV37Error, "collision"):
            core.build_and_publish_federation_v37()
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        with tempfile.TemporaryDirectory(
            prefix="federation-v37-rollback-", dir="/private/tmp"
        ) as temporary:
            occupied_bundle = Path(temporary) / "occupied-bundle"
            occupied_bundle.mkdir()
            occupied_definition = Path(temporary) / "occupied-definition"
            occupied_definition.write_text("occupied")
            with self.assertRaisesRegex(core.FederationV37Error, "occupied"):
                core._rollback_bundle(occupied_bundle)
            with self.assertRaisesRegex(core.FederationV37Error, "occupied"):
                core._rollback_definition(occupied_definition)
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        descriptor = next(
            row for row in current["releases"] if row["release_id"] == core.NEW_RELEASE_ID
        )
        with tempfile.TemporaryDirectory(
            prefix="federation-v37-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V92_RELEASE.name
            child_symlink.symlink_to(V92_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id=core.NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=core.V92_MANIFEST_PIN[1],
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

        self.assertIs(core.validate_federation_v37, shim.validate_federation_v37)
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
        self.assertEqual(output["generated_at"], core.GENERATED_AT)

        code = (
            "from datacenter_atlas.federation_v37 import validate_federation_v37 as v; "
            "r=v(); assert r['counts']['source_scoped_entity_records']==16413; "
            "assert r['counts']['non_review_source_scoped_entity_records']==10283; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v92')); "
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
            if path.name.startswith(".federation-v37-private-stage-")
            or path.name == ".federation-v37.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
