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
    "datacenter_atlas.datacenter_atlas.federated_release_v4"
)
carrier_shim = importlib.import_module("datacenter_atlas.federated_release_v4")
core = importlib.import_module("datacenter_atlas.datacenter_atlas.federation_v36")
shim = importlib.import_module("datacenter_atlas.federation_v36")
open_seed = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v87")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v36.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v36"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v35.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v35"
V87_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v87.json"
V87_RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
CARRIER_SOURCE = ROOT / "datacenter_atlas/federated_release_v4.py"
BUILDER = ROOT / "scripts/build_federation_v36.py"

CARRIER_SOURCE_PIN = (
    17_669,
    "af10b118a5941b7d9b021bb7301d58082ac738160afc9a6dc1101213192f516a",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV36Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v36 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_v36_v35_v87_and_carrier_pins_are_exact(self) -> None:
        pins = {
            DEFINITION: core.DEFINITION_PIN,
            INDEX_DIR / federation.INDEX_FILENAME: core.INDEX_PIN,
            INDEX_DIR / federation.MANIFEST_FILENAME: core.MANIFEST_PIN,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: core.SIDECAR_PIN,
            BASE_DEFINITION: core.BASE_DEFINITION_PIN,
            BASE_INDEX_DIR / federation.MANIFEST_FILENAME: core.BASE_MANIFEST_PIN,
            V87_DEFINITION: core.V87_DEFINITION_PIN,
            V87_RELEASE / federation.MANIFEST_FILENAME: core.V87_MANIFEST_PIN,
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
        self.assertEqual(core.tree_digest(V87_RELEASE), core.V87_TREE_SHA256)
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
        self.assertGreaterEqual(
            datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), generated
        )
        self.assertGreaterEqual(
            datetime.fromtimestamp(INDEX_DIR.stat().st_ctime, UTC), generated
        )

    def test_definition_is_exact_v35_successor_with_only_v87_replacement(self) -> None:
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
                "expected_manifest_sha256": core.V87_MANIFEST_PIN[1],
                "reference": "../../releases/2026-07-21-open-seed-v87/",
                "release_id": core.NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v87",
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
        current = core.validate_federation_v36()
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
                "bytes": 15_566,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "geometry_only_representative_point_inferred": False,
                "lifecycle_freshness_records": 521,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": core.V87_RECORDED_AT,
                "sha256": core.V87_MANIFEST_PIN[1],
            },
        )
        serialized = canonical_json(current).decode().casefold()
        self.assertTrue(all(marker not in serialized for marker in core.BANNED_CLAIMS))

    def test_v87_source_family_provenance_and_capacity_closure_are_exact(self) -> None:
        core._validate_v87_provenance()
        definition = json.loads(V87_DEFINITION.read_text())
        base_definition = json.loads(open_seed.BASE_DEFINITION.read_text())
        self.assertEqual(definition["curated_inputs"][:452], base_definition["curated_inputs"])
        self.assertEqual(
            definition["curated_inputs"][452:],
            [
                {"path": path, "sha256": open_seed.ADDITION_PINS[path][1]}
                for path in open_seed.ADDITION_ORDER
            ],
        )
        source_rows = {
            row["provenance"]["curated_record_key"]: row
            for row in json.loads(
                (V87_RELEASE / "source_inputs.json").read_text()
            )["sources"]
            if row["provenance"].get("curated_record_key")
            in open_seed.ADDED_EVIDENCE_KEYS
        }
        self.assertEqual(set(source_rows), open_seed.ADDED_EVIDENCE_KEYS)
        self.assertEqual(
            {key: row["source_family"] for key, row in source_rows.items()},
            core.EXPECTED_SOURCE_FAMILIES,
        )
        entities = {
            row["stable_key"]: row
            for row in core._csv_rows(V87_RELEASE / "entities.csv")
            if row["stable_key"] in open_seed.ADDED_ENTITY_KEYS
        }
        first_phase = entities["curated:riot-rockdale-site:amd-lease-first-phase"]
        self.assertEqual(first_phase["status"], "operational")
        self.assertEqual(first_phase["capacity_estimates_json"], "[]")
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
            (V87_RELEASE / "resolution_candidates.csv").read_bytes(),
            (V86_RELEASE / "resolution_candidates.csv").read_bytes(),
        )
        self.assertEqual(
            (V87_RELEASE / "resolution_candidates.json").read_bytes(),
            (V86_RELEASE / "resolution_candidates.json").read_bytes(),
        )

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        self.assertIs(
            federation.validate_federated_release_index,
            carrier_shim.validate_federated_release_index,
        )
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        replay_payloads = []
        with tempfile.TemporaryDirectory(
            prefix="federation-v36-rebuild-", dir="/private/tmp"
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
        with self.assertRaisesRegex(core.FederationV36Error, "inferred"):
            core._validate_counts(missing, accepted)
        with self.assertRaisesRegex(core.FederationV36Error, "completeness claim"):
            core._validate_no_completeness_claims(
                {"unsupported_claim": "SemiAnalysis parity"}
            )

        definition_before = DEFINITION.read_bytes()
        tree_before = core.tree_digest(INDEX_DIR)
        with self.assertRaisesRegex(core.FederationV36Error, "collision"):
            core.build_and_publish_federation_v36()
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        with tempfile.TemporaryDirectory(
            prefix="federation-v36-rollback-", dir="/private/tmp"
        ) as temporary:
            occupied_bundle = Path(temporary) / "occupied-bundle"
            occupied_bundle.mkdir()
            occupied_definition = Path(temporary) / "occupied-definition"
            occupied_definition.write_text("occupied")
            with self.assertRaisesRegex(core.FederationV36Error, "occupied"):
                core._rollback_bundle(occupied_bundle)
            with self.assertRaisesRegex(core.FederationV36Error, "occupied"):
                core._rollback_definition(occupied_definition)
        self.assertEqual(DEFINITION.read_bytes(), definition_before)
        self.assertEqual(core.tree_digest(INDEX_DIR), tree_before)

        descriptor = next(
            row for row in current["releases"] if row["release_id"] == core.NEW_RELEASE_ID
        )
        with tempfile.TemporaryDirectory(
            prefix="federation-v36-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V87_RELEASE.name
            child_symlink.symlink_to(V87_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id=core.NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=core.V87_MANIFEST_PIN[1],
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

        self.assertIs(core.validate_federation_v36, shim.validate_federation_v36)
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
            "from datacenter_atlas.federation_v36 import validate_federation_v36 as v; "
            "r=v(); assert r['counts']['source_scoped_entity_records']==16358; "
            "assert r['counts']['non_review_source_scoped_entity_records']==10228; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v87')); "
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
            if path.name.startswith(".federation-v36-private-stage-")
            or path.name == ".federation-v36.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
