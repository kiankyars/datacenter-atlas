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
    from datacenter_atlas.datacenter_atlas import federated_release as legacy
    from datacenter_atlas.datacenter_atlas import federated_release_v3 as federation
    from datacenter_atlas.datacenter_atlas import federation_publication as publication
    from datacenter_atlas import federation_publication as publication_shim
except ModuleNotFoundError:
    from datacenter_atlas import federated_release as legacy
    from datacenter_atlas import federated_release_v3 as federation
    from datacenter_atlas import federation_publication as publication
    import federation_publication as publication_shim


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v31.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v31"
BASE_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v28.json"
BASE_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v28"
V71_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"
V30_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v30.json"
V30_INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v30"
INCIDENT = (
    ROOT
    / "source_artifacts/federation-v30-prepublication-temporal-incident-2026-07-21-v1"
)
V30_RECOVERY = Path(
    "/Users/kian/.Trash/"
    "datacenter-atlas-federation-v30-prepublication-20260721-0322Z-9UHbCZ/bundle"
)

GENERATED_AT = "2026-07-21T10:32:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v67"
NEW_RELEASE_ID = "epoch-official-open-seed-v71"
UNCHANGED_RELEASE_IDS = {"global-open-v3", "osm-fuzzy-review-v2"}

DEFINITION_SHA256 = "83a878ee72563e6572a53cf09236c0af469e629bc04482401d6891b54d108ee1"
INDEX_SHA256 = "02907b58973b74461a6117bc4373ea6ac06e5026b4fdf632e43fdaa05043e576"
MANIFEST_SHA256 = "7adc941dd73fa33315322ce19ff9c9887cdc2fb80cbd0aca3385a1c005781101"
SIDECAR_SHA256 = "af1fde6783975c049dd04ac15b1014d29da905448c7c6e8fd6140ab54c78c41e"
TREE_SHA256 = "978b1a574071f0128538aafee4503436fd0ae95284a60e236b0ee9065834f55c"
V71_DEFINITION_SHA256 = "f5115fa57f32c8d9451609a662f6b524a15283b8e4fa1d9b65af59430d9e3b38"
V71_MANIFEST_SHA256 = "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22"
V71_TREE_SHA256 = "7636964f1d640268ed8627d5f18d800a43a35a4d7dbc1f62b8386e60bd1fa720"

V30_DEFINITION_SHA256 = "d1b9772d4185e7521939caa409daae7ebc7b6608c256b493951893d972641234"
V30_STAGED_INDEX_SHA256 = "6ffa173d006f36f42f9b77f7b2bd189bc2cdfe804d113349494f3582ebf055e9"
V30_STAGED_MANIFEST_SHA256 = "b0fb77b87dc3fd09aa79b2cb87408af0b6fd41628cf7f2ef91a65eff85c66b2e"
V30_STAGED_SIDECAR_SHA256 = "939e854ae33a3846b61163037fcf654c5c597c792b7039a82756f28125cc1bf9"
V30_STAGED_TREE_SHA256 = "02b4977aa750025fa1b906ecbb0b918474ee83517bc3aa7d4eacad81ea9be883"
INCIDENT_MANIFEST_SHA256 = "be59c0f61dbc2d4a1d6aa2798339bdae616ff4d09b1a61c28ca9d66663248229"
INCIDENT_SIDECAR_SHA256 = "fd3feb130e8c3091e91de44617dfbd4ac52e724101bb8ee5df2c8452b939b4fe"
INCIDENT_TREE_SHA256 = "f2b2d8e0d2c57c4f4699ec0b6a4000101802097e5ee28f48f8dbcfa0dfe5ea5c"

EXPECTED_COUNTS = {
    "capacity_estimates": 1318,
    "construction_pipeline_records": 6666,
    "evidence_records": 13525,
    "non_review_construction_pipeline_records": 536,
    "non_review_source_scoped_entity_records": 10105,
    "release_bundles": 3,
    "resolution_candidates": 100411,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 295,
    "source_scoped_entity_records": 16235,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 11,
    "construction_pipeline_records": 15,
    "evidence_records": 18,
    "non_review_construction_pipeline_records": 15,
    "non_review_source_scoped_entity_records": 27,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 8,
    "source_scoped_entity_records": 27,
}
EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 532,
    "construction_pipeline_records": 416,
    "entities_by_kind": {"campus": 427, "project": 383},
    "evidence_records": 512,
    "resolution_candidates": 6,
    "source_family_entries": 288,
    "source_scoped_entity_records": 810,
}
CHILDREN = {
    NEW_RELEASE_ID: V71_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"bundle contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


class FederatedReleaseV31Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v31 federation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_incident_pins_rejected_v30_and_absent_final_bundle(self) -> None:
        self.assertEqual((V30_DEFINITION.stat().st_size, sha256(V30_DEFINITION)), (1788, V30_DEFINITION_SHA256))
        self.assertEqual(int(V30_DEFINITION.stat().st_birthtime), 1784629342)
        self.assertEqual(int(V30_DEFINITION.stat().st_mtime), 1784629342)
        self.assertFalse(V30_INDEX_DIR.exists())
        self.assertFalse(V30_INDEX_DIR.is_symlink())

        self.assertEqual(sha256(INCIDENT / "manifest.json"), INCIDENT_MANIFEST_SHA256)
        self.assertEqual(sha256(INCIDENT / "manifest.sha256"), INCIDENT_SIDECAR_SHA256)
        self.assertEqual(tree_digest(INCIDENT), INCIDENT_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(INCIDENT.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in INCIDENT.iterdir()
            )
        )
        incident = json.loads((INCIDENT / "incident.json").read_text())
        rejected = incident["rejected_v30"]
        self.assertEqual(incident["acceptance"], "accepted_technical_incident_record")
        self.assertEqual(incident["integration"], "none")
        self.assertEqual(rejected["acceptance"], "non_accepted")
        self.assertEqual(rejected["definition"]["sha256"], V30_DEFINITION_SHA256)
        self.assertEqual(rejected["definition"]["claimed_minus_birth_seconds"], 158)
        self.assertEqual(rejected["final_bundle"]["exists_at_detection"], False)
        self.assertIn("never retroactively", incident["policy"]["passage_of_time"])

        self.assertTrue(V30_RECOVERY.is_dir())
        self.assertFalse(V30_RECOVERY.is_symlink())
        self.assertEqual(tree_digest(V30_RECOVERY), V30_STAGED_TREE_SHA256)
        self.assertEqual(
            sha256(V30_RECOVERY / federation.INDEX_FILENAME),
            V30_STAGED_INDEX_SHA256,
        )
        self.assertEqual(
            sha256(V30_RECOVERY / federation.MANIFEST_FILENAME),
            V30_STAGED_MANIFEST_SHA256,
        )
        self.assertEqual(
            sha256(V30_RECOVERY / federation.MANIFEST_HASH_FILENAME),
            V30_STAGED_SIDECAR_SHA256,
        )

    def test_frozen_pins_modes_trees_and_temporal_boundary_are_exact(self) -> None:
        pins = {
            DEFINITION: DEFINITION_SHA256,
            INDEX_DIR / federation.INDEX_FILENAME: INDEX_SHA256,
            INDEX_DIR / federation.MANIFEST_FILENAME: MANIFEST_SHA256,
            INDEX_DIR / federation.MANIFEST_HASH_FILENAME: SIDECAR_SHA256,
            V71_DEFINITION: V71_DEFINITION_SHA256,
            V71_RELEASE / federation.MANIFEST_FILENAME: V71_MANIFEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(sha256(path), expected, path)
        self.assertEqual(tree_digest(INDEX_DIR), TREE_SHA256)
        self.assertEqual(tree_digest(V71_RELEASE), V71_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
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
        for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.iterdir()):
            birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            self.assertLessEqual(max(birth, modified), generated, path)
        self.assertLessEqual(generated, datetime.now(timezone.utc))
        incident_manifest = json.loads((INCIDENT / "manifest.json").read_text())
        incident_recorded = datetime.fromisoformat(
            incident_manifest["recorded_at"].replace("Z", "+00:00")
        )
        for path in (INCIDENT, *INCIDENT.iterdir()):
            birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            self.assertLessEqual(max(birth, modified), incident_recorded, path)
        self.assertLessEqual(incident_recorded, datetime.now(timezone.utc))

    def test_definition_is_exact_v28_successor_and_counts_reconcile(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text())
        expected_definition = deepcopy(base_definition)
        expected_definition["generated_at"] = GENERATED_AT
        child = next(
            item
            for item in expected_definition["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": V71_MANIFEST_SHA256,
                "reference": "../../releases/2026-07-21-open-seed-v71/",
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v71",
            }
        )
        current_definition = json.loads(DEFINITION.read_text())
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current_definition))
        self.assertEqual(current_definition, expected_definition)
        release_ids = {row["release_id"] for row in current_definition["children"]}
        self.assertEqual(release_ids, UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        self.assertTrue(
            {"epoch-official-open-seed-v68", "epoch-official-open-seed-v70"}.isdisjoint(
                release_ids
            )
        )

        base = json.loads(
            (BASE_INDEX_DIR / federation.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        current = federation.validate_federated_release_index(
            INDEX_DIR, child_release_paths=CHILDREN
        )
        self.assertEqual(current["counts"], EXPECTED_COUNTS)
        self.assertEqual(current["policy"], federation.FEDERATION_POLICY)
        self.assertIsNone(current["counts"]["unique_physical_sites"])
        self.assertEqual(
            {
                key: current["counts"][key] - base["counts"][key]
                for key in EXPECTED_DELTA
            },
            EXPECTED_DELTA,
        )

        current_by_id = {row["release_id"]: row for row in current["releases"]}
        base_by_id = {row["release_id"]: row for row in base["releases"]}
        self.assertEqual(set(current_by_id), UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID})
        for release_id in UNCHANGED_RELEASE_IDS:
            self.assertEqual(current_by_id[release_id], base_by_id[release_id])
        open_child = current_by_id[NEW_RELEASE_ID]
        self.assertEqual(open_child["counts"], EXPECTED_OPEN_COUNTS)
        self.assertEqual(len(open_child["source_families"]), 288)
        self.assertEqual(
            open_child["manifest"],
            {
                "as_of": "2026-07-21",
                "bytes": 12577,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 458,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T10:17:38Z",
                "sha256": V71_MANIFEST_SHA256,
            },
        )
        self.assertIn(
            "no-use-restriction-stated-for-reference-cartography",
            open_child["rights"]["source_licenses"],
        )

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}
        with tempfile.TemporaryDirectory(
            prefix="federation-v31-rebuild-", dir="/private/tmp"
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
            self.assertEqual(built["counts"], EXPECTED_COUNTS)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()},
                frozen,
            )
        self.assertEqual(
            {path.name: path.read_bytes() for path in INDEX_DIR.iterdir()}, frozen
        )

    def test_early_final_future_collision_tamper_and_symlink_fail_closed(self) -> None:
        current = json.loads(
            (INDEX_DIR / federation.INDEX_FILENAME).read_text(encoding="utf-8")
        )
        descriptor = next(
            row for row in current["releases"] if row["release_id"] == NEW_RELEASE_ID
        )
        inferred = deepcopy(descriptor)
        inferred["manifest"]["current_status_inferred"] = True
        with self.assertRaisesRegex(
            federation.FederatedReleaseError, "current_status_inferred must be false"
        ):
            federation._validate_descriptor(inferred, 0)

        with tempfile.TemporaryDirectory(
            prefix="federation-v31-fail-closed-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            child_symlink = temporary_root / V71_RELEASE.name
            child_symlink.symlink_to(V71_RELEASE, target_is_directory=True)
            child_definition = legacy._ChildDefinition(
                release_id=NEW_RELEASE_ID,
                release_path=child_symlink,
                reference=descriptor["reference"],
                expected_manifest_sha256=V71_MANIFEST_SHA256,
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
            linked_output = temporary_root / "linked-output"
            linked_output.symlink_to(INDEX_DIR, target_is_directory=True)
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "output may not be a symlink"
            ):
                federation.write_federated_release_index(DEFINITION, linked_output)

            stage = temporary_root / "stage"
            destination = temporary_root / "destination"
            stage.mkdir()
            destination.mkdir()
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "late output collision"
            ):
                federation._promote_noreplace(stage, destination)

            now = datetime.now(timezone.utc)
            future_document = json.loads(DEFINITION.read_text())
            future_document["generated_at"] = (
                (now + timedelta(minutes=5))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            future_stage = temporary_root / "future-definition.json"
            future_stage.write_bytes(canonical_json(future_document))
            early_final = temporary_root / DEFINITION.name
            early_final.write_bytes(future_stage.read_bytes())
            with self.assertRaisesRegex(
                federation.FederatedReleaseError,
                "final federation definition was exposed before generated_at",
            ):
                publication.validate_prepublication_boundary(
                    future_stage,
                    early_final,
                    temporary_root / INDEX_DIR.name,
                    wall_clock=now,
                )
            early_final.unlink()
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "generated_at is not yet live"
            ):
                publication.validate_prepublication_boundary(
                    future_stage,
                    early_final,
                    temporary_root / INDEX_DIR.name,
                    wall_clock=now,
                )

            late_stage = temporary_root / "late-stage.json"
            late_stage.write_bytes(DEFINITION.read_bytes())
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "stage post-dates generated_at"
            ):
                publication.validate_prepublication_boundary(
                    late_stage,
                    temporary_root / "unused-definition.json",
                    temporary_root / "unused-bundle",
                    wall_clock=now,
                )
            linked_definition = temporary_root / "linked-definition.json"
            linked_definition.symlink_to(DEFINITION)
            with self.assertRaisesRegex(
                federation.FederatedReleaseError, "regular file"
            ):
                publication.validate_prepublication_boundary(
                    linked_definition,
                    temporary_root / "unused-definition-2.json",
                    temporary_root / "unused-bundle-2",
                    wall_clock=now,
                )

    def test_parent_and_nested_imports_validate_guardrails(self) -> None:
        self.assertIs(
            publication.publish_staged_federation,
            publication_shim.publish_staged_federation,
        )
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.federated_release_v3 import "
            "validate_federated_release_index as v; "
            f"r=v(Path({str(INDEX_DIR)!r})); "
            "assert r['counts']['source_scoped_entity_records']==16235; "
            "assert r['counts']['evidence_records']==13525; "
            "assert r['counts']['source_family_entries']==295; "
            "assert r['counts']['unique_physical_sites'] is None; "
            "c=next(x for x in r['releases'] if x['release_id'].endswith('v71')); "
            "assert c['manifest']['current_status_inferred'] is False; "
            "assert c['manifest']['lifecycle_freshness_records']==458"
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
