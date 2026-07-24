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
core = importlib.import_module("datacenter_atlas.datacenter_atlas.federation_v33")
shim = importlib.import_module("datacenter_atlas.federation_v33")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v33.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v33"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v31.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v31"
V73_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
REJECTED_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v32.json"
REJECTED_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v32"
INCIDENT = (
    ROOT
    / "source_artifacts/federation-v32-partial-publication-incident-2026-07-21-v1"
)
BUILDER = ROOT / "scripts/build_federation_v33.py"

GENERATED_AT = "2026-07-21T13:29:00Z"
DEFINITION_PIN = (
    1_788,
    "6472c052092860af73da784b233261c6e8de6a7e9d853d215fa459d5347b4e89",
)
INDEX_PIN = (
    31_626,
    "0d865517b715edf69ccfb8df19ba0ea63b50c8d51167e9c64ff12daf60c5df1a",
)
MANIFEST_PIN = (
    986,
    "4c2db492362d57d792fb9a162576e9505883bdc8daad6b08a9547d1ecb27ac7b",
)
SIDECAR_PIN = (
    80,
    "d60051ced9f427d23a4e79380d5917e056ebd1b100fdaa583cc5f438b779403e",
)
TREE_SHA256 = "0fa59ad26d24d6266df33613102828a42e231eb2f231872bc0a9146c9aa0c760"

REJECTED_DEFINITION_PIN = (
    1_788,
    "29ff67c72cbe83f48ed28db6e4c059f1513358cf43d20c6039ae5e27cc924dc9",
)
INCIDENT_FILE_PINS = {
    "README.md": (
        797,
        "3f11b3181e9bd37275c164ecc6488ab100d5a5e9df70e2f75f493235a4be7f02",
    ),
    "incident.json": (
        3_788,
        "2df3c27a344fd0afc0eef52b167533c6d76967dbca1b6b64a6cbafb9e1dc08d2",
    ),
    "manifest.json": (
        1_122,
        "4ef894097a41683a6d446e2c93e0a58127ceb1f4b7bf7b18e6cfce8eb9f51891",
    ),
    "manifest.sha256": (
        80,
        "1361456479393bac8eace283aed802ff6e05445570bb9e6874ae50a4bb9e0de9",
    ),
}
INCIDENT_TREE_SHA256 = (
    "9305aeb9d08e8d0f88a10c7f89e348f13ba41ec28a6bc6ff59648a666d5fa119"
)

SOURCE_LICENSES = [
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-4.0-subject-to-third-party-material",
    "all-rights-reserved",
    "all-rights-reserved-facts-only",
    "government-public-record",
    "no-license-stated-for-compact-factual-extraction",
    "no-use-restriction-stated-for-reference-cartography",
    "public-domain",
    "public-domain-us-government",
    "public-government-record",
    "public-record",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


class FederatedReleaseV33Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v33 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_rejected_v32_and_incident_are_exact_and_non_integrated(self) -> None:
        self.assertEqual(
            (REJECTED_DEFINITION.stat().st_size, sha256(REJECTED_DEFINITION)),
            REJECTED_DEFINITION_PIN,
        )
        self.assertEqual(stat.S_IMODE(REJECTED_DEFINITION.stat().st_mode), 0o444)
        self.assertFalse(REJECTED_INDEX_DIR.exists())
        self.assertFalse(REJECTED_INDEX_DIR.is_symlink())
        self.assertEqual(stat.S_IMODE(INCIDENT.stat().st_mode), 0o555)
        self.assertEqual(core.rejected.tree_digest(INCIDENT), INCIDENT_TREE_SHA256)
        self.assertEqual(set(INCIDENT_FILE_PINS), {path.name for path in INCIDENT.iterdir()})
        for filename, pin in INCIDENT_FILE_PINS.items():
            path = INCIDENT / filename
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), pin)

        incident = json.loads((INCIDENT / "incident.json").read_text())
        self.assertEqual(incident["acceptance"], "accepted_technical_incident_record")
        self.assertEqual(incident["integration"], "none")
        self.assertEqual(incident["corrective_successor"], "federated-index-2026-07-21-public-open-v33")
        rejected = incident["rejected_v32"]
        self.assertEqual(rejected["acceptance"], "non_accepted")
        self.assertEqual(rejected["definition"]["sha256"], REJECTED_DEFINITION_PIN[1])
        self.assertEqual(rejected["definition"]["ctime_epoch_ns"], 1_784_640_060_054_008_560)
        self.assertFalse(rejected["final_bundle"]["exists_at_detection"])
        self.assertEqual(rejected["original_private_stage"]["retained"], False)
        self.assertIn(
            "not the original private-stage inode",
            rejected["deterministic_expected_bundle_reconstruction"]["claim_boundary"],
        )
        diagnosis = incident["diagnosis"]
        self.assertEqual(diagnosis["destination_parent"]["mode_at_detection"], "0755")
        self.assertEqual(
            diagnosis["minimum_corrective_mode_transition"],
            {
                "final_bundle_root_after_promotion": "0555",
                "private_bundle_root_during_no_replace_rename": "0755",
                "private_bundle_root_members": "0444",
            },
        )
        self.assertIn("not the cause", diagnosis["root_cause"])

    def test_frozen_v33_v31_and_v73_pins_modes_trees_and_times_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_PIN,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_PIN,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_PIN,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_PIN,
            BASE_DEFINITION: core.rejected.BASE_DEFINITION_PIN,
            BASE_INDEX_DIR / federation.MANIFEST_FILENAME: core.rejected.BASE_MANIFEST_PIN,
            V73_DEFINITION: core.rejected.V73_DEFINITION_PIN,
            V73_RELEASE / federation.MANIFEST_FILENAME: core.rejected.V73_MANIFEST_PIN,
        }
        for path, pin in pins.items():
            self.assertEqual((path.stat().st_size, sha256(path)), pin, path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
        self.assertEqual(core.rejected.tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(
            core.rejected.tree_digest(BASE_INDEX_DIR), core.rejected.BASE_TREE_SHA256
        )
        self.assertEqual(
            core.rejected.tree_digest(V73_RELEASE), core.rejected.V73_TREE_SHA256
        )
        self.assertEqual(stat.S_IMODE(INDEX_DIR.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in INDEX_DIR.iterdir()}, federation.FEDERATED_BUNDLE_FILES
        )
        for path in INDEX_DIR.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        generated = datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))
        for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.iterdir()):
            details = path.stat()
            born = datetime.fromtimestamp(details.st_birthtime, UTC)
            modified = datetime.fromtimestamp(details.st_mtime, UTC)
            self.assertLessEqual(max(born, modified), generated, path)
        self.assertGreaterEqual(datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), generated)
        self.assertGreaterEqual(datetime.fromtimestamp(INDEX_DIR.stat().st_ctime, UTC), generated)
        self.assertLessEqual(generated, datetime.now(UTC))

        incident_recorded = datetime.fromisoformat("2026-07-21T13:27:00+00:00")
        for path in (INCIDENT, *INCIDENT.iterdir()):
            details = path.stat()
            self.assertLessEqual(
                max(
                    datetime.fromtimestamp(details.st_birthtime, UTC),
                    datetime.fromtimestamp(details.st_mtime, UTC),
                ),
                incident_recorded,
            )
        self.assertGreaterEqual(
            datetime.fromtimestamp(INCIDENT.stat().st_ctime, UTC), incident_recorded
        )

    def test_definition_is_exact_v31_successor_and_only_v73_delta_integrates(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text())
        expected = deepcopy(base_definition)
        expected["generated_at"] = GENERATED_AT
        child = next(
            row for row in expected["children"] if row["release_id"] == "epoch-official-open-seed-v71"
        )
        child.update(
            {
                "expected_manifest_sha256": core.rejected.V73_MANIFEST_PIN[1],
                "reference": "../../releases/2026-07-21-open-seed-v73/",
                "release_id": "epoch-official-open-seed-v73",
                "release_path": "../releases/2026-07-21-open-seed-v73",
            }
        )
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        release_ids = {row["release_id"] for row in current_definition["children"]}
        self.assertEqual(
            release_ids,
            {"epoch-official-open-seed-v73", "global-open-v3", "osm-fuzzy-review-v2"},
        )
        self.assertFalse(any(release_id.endswith(("v29", "v30", "v32")) for release_id in release_ids))

        base = json.loads(
            (BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = core.validate_federation_v33()
        self.assertEqual(current["counts"], core.EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertEqual(
            {
                key: current["counts"][key] - base["counts"][key]
                for key in core.EXPECTED_DELTA
            },
            core.EXPECTED_DELTA,
        )
        current_by_id = {row["release_id"]: row for row in current["releases"]}
        base_by_id = {row["release_id"]: row for row in base["releases"]}
        for release_id in core.UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], base_by_id[release_id])
        child = current_by_id["epoch-official-open-seed-v73"]
        self.assertEqual(child["counts"], core.EXPECTED_OPEN_COUNTS)
        self.assertEqual(
            child["manifest"],
            {
                "as_of": "2026-07-21",
                "bytes": 12_814,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 462,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T13:15:51Z",
                "sha256": core.rejected.V73_MANIFEST_PIN[1],
            },
        )
        self.assertEqual(child["rights"]["source_licenses"], SOURCE_LICENSES)
        self.assertEqual(child["rights"]["license_expression"], core.rejected.LICENSE_EXPRESSION)
        self.assertEqual(child["rights"]["rights_notice"], core.rejected.RIGHTS_NOTICE)

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v33-rebuild-", dir="/private/tmp"
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
                {path.name: path.read_bytes() for path in reproduced.iterdir()}, frozen
            )

    def test_tamper_inference_symlink_and_collision_fail_closed(self) -> None:
        current = json.loads((INDEX_DIR / federation.INDEX_FILENAME).read_text())
        descriptor = next(
            row for row in current["releases"] if row["release_id"].endswith("v73")
        )
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "current_status_inferred must be false"
        ):
            federation._validate_descriptor(inferred, 0)

        with tempfile.TemporaryDirectory(
            prefix="federation-v33-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V73_RELEASE.name
            child_symlink.symlink_to(V73_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id="epoch-official-open-seed-v73",
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=core.rejected.V73_MANIFEST_PIN[1],
                license_expression=descriptor["rights"]["license_expression"],
                rights_notice=descriptor["rights"]["rights_notice"],
            )
            with self.assertRaisesRegex(federation.FederatedReleaseError, "regular directory"):
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
                federation.validate_federated_release_index(copied, require_frozen=False)

            collision = temporary_root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(federation.FederatedReleaseError):
                federation.write_federated_release_index(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

    @unittest.skipUnless(sys.platform == "darwin", "macOS renamex_np contract")
    def test_macos_no_replace_requires_only_bundle_root_mode_transition(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="federation-v33-mode-contract-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            source_parent = root / "source"
            destination_parent = root / "destination"
            source_parent.mkdir()
            destination_parent.mkdir()
            frozen = source_parent / "frozen"
            frozen.mkdir()
            (frozen / "member").write_bytes(b"frozen\n")
            (frozen / "member").chmod(0o444)
            frozen.chmod(0o555)
            with self.assertRaisesRegex(federation.FederatedReleaseError, "Permission denied"):
                federation._promote_noreplace(frozen, destination_parent / "blocked")
            frozen.chmod(0o755)
            destination = destination_parent / "promoted"
            federation._promote_noreplace(frozen, destination)
            destination.chmod(0o555)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
            self.assertEqual(stat.S_IMODE((destination / "member").stat().st_mode), 0o444)

    def test_shim_cli_and_both_import_layouts_verify_exact_v33(self) -> None:
        self.assertIs(core.validate_federation_v33, shim.validate_federation_v33)
        command = [sys.executable, str(BUILDER), "--verify"]
        result = subprocess.run(
            command,
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
            "from pathlib import Path; "
            "from datacenter_atlas.federation_v33 import validate_federation_v33 as v; "
            "r=v(); "
            "assert r['counts']['source_scoped_entity_records']==16243; "
            "assert r['counts']['review_only_source_scoped_entity_records']==6130; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v73')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['lifecycle_freshness_records']==462"
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


if __name__ == "__main__":
    unittest.main()
