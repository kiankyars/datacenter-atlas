from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest


core = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.corrected_discovery_wrappers_v2"
)
shim = importlib.import_module("datacenter_atlas.corrected_discovery_wrappers_v2")

ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "source_artifacts/temporal-integrity-incident-2026-07-21-v1"
INCIDENT_MANIFEST_PIN = (
    897,
    "7876a3134daba719e7fd25afc330301ce7909ee91cdcecf118bc7340dc79c8f7",
)
INCIDENT_TREE_PIN = "954cdcc7fa08a5cade9e4e64785f4fec3415743898885f09dfd9ad4c6b8448a7"

WRAPPER_PINS = {
    "global-underrepresented-official-discovery-2026-07-21-v2": (
        2_527,
        "708b6ee86f3505ddb027b547fa30468a9dd6c96873ed6b56fcc2295ed1b12565",
        "f70ea09e5b0ab3df3662e559b09994eff74a8ae9219d51fa9e8fbc6a5b46d752",
    ),
    "second-underrepresented-official-discovery-2026-07-21-v2": (
        2_527,
        "02f42e7a866f391c7fe4c06e988018d646801ea001081e7847d063f08a3f9b4a",
        "9a7f10be0b5783acccb7d0a94596290d393269ce2162078fb5d7edc4f5aa0970",
    ),
    "gap-region-official-discovery-2026-07-21-v2": (
        2_478,
        "28298b4094143d807d78f6296c6d0e45a316a907e3d02f44436e21f4eb17f741",
        "a369f440e6cf0ddc290911a8677eb71fbf049522cd98412e6385eb0eb8134b63",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/corrected_discovery_wrappers_v2.py": (
        18_394,
        "8935f8f048d77f961c4964798f796a59ce1e333310dcabd554dfed7a91f38bf5",
    ),
    ROOT / "corrected_discovery_wrappers_v2.py": (
        165,
        "da73e10a88a6c3e0297b2f1f1cf7cda9e4867266286b7cdf8618d97927c0339d",
    ),
    ROOT / "scripts/build_corrected_discovery_wrappers_v2.py": (
        384,
        "73c7075251146d5f754cfc508e84d546bd416b0e97d57d262629b6fc3c8a427e",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TemporalIntegrityCorrectionTests(unittest.TestCase):
    def test_incident_is_honest_frozen_and_marks_all_subjects_non_accepted(
        self,
    ) -> None:
        self.assertEqual(
            ((INCIDENT / "manifest.json").stat().st_size, sha256(INCIDENT / "manifest.json")),
            INCIDENT_MANIFEST_PIN,
        )
        self.assertEqual(core.tree_digest(INCIDENT), INCIDENT_TREE_PIN)
        self.assertEqual(stat.S_IMODE(INCIDENT.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in INCIDENT.iterdir()
            )
        )
        manifest = json.loads((INCIDENT / "manifest.json").read_text())
        incident = json.loads((INCIDENT / "incident.json").read_text())
        self.assertEqual((manifest["subject_count"], len(incident["subjects"])), (7, 7))
        self.assertEqual(manifest["accepted_subject_count"], 0)
        self.assertTrue(
            all(
                row["acceptance_status"] == "non_accepted"
                for row in incident["subjects"]
            )
        )
        recorded_at = datetime.fromisoformat(
            manifest["recorded_at"].replace("Z", "+00:00")
        )
        birth = datetime.fromtimestamp(INCIDENT.stat().st_birthtime, timezone.utc)
        self.assertLessEqual(birth, recorded_at)
        self.assertLessEqual(recorded_at, datetime.now(timezone.utc))

    def test_incident_target_pins_and_filesystem_evidence_are_exact(self) -> None:
        incident = json.loads((INCIDENT / "incident.json").read_text())
        subjects = {row["subject_id"]: row for row in incident["subjects"]}
        self.assertEqual(
            set(subjects),
            {
                "open-seed-v68",
                "construction-timeline-v4",
                "federated-index-v29",
                "exact-identity-v7-definition",
                "gap-region-official-discovery-v1",
                "global-underrepresented-official-discovery-v1",
                "second-underrepresented-official-discovery-v1",
            },
        )
        for subject in subjects.values():
            self.assertEqual(subject["acceptance_status"], "non_accepted")
            for component in subject["components"]:
                path = ROOT / component["path"]
                if component["type"] == "absent_expected_bundle":
                    self.assertFalse(path.exists())
                    continue
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode), int(component["mode"], 8)
                )
                self.assertEqual(int(path.stat().st_birthtime), component["birth_epoch"])
                self.assertEqual(int(path.stat().st_mtime), component["mtime_epoch"])
                self.assertGreater(component["claimed_minus_birth_seconds"], 0)
                if component["type"] == "file":
                    self.assertEqual(
                        (path.stat().st_size, sha256(path)),
                        (component["bytes"], component["sha256"]),
                    )
                else:
                    self.assertEqual(core.tree_digest(path), component["tree_sha256"])

    def test_corrected_wrappers_are_frozen_honest_and_exactly_pinned(self) -> None:
        for wrapper_id, (size, digest, tree) in WRAPPER_PINS.items():
            path = ROOT / "source_artifacts" / wrapper_id
            with self.subTest(wrapper_id=wrapper_id):
                manifest = core.validate_corrected_wrapper(wrapper_id)
                self.assertEqual(
                    ((path / "manifest.json").stat().st_size, sha256(path / "manifest.json")),
                    (size, digest),
                )
                self.assertEqual(core.tree_digest(path), tree)
                recorded_at = datetime.fromisoformat(
                    manifest["recorded_at"].replace("Z", "+00:00")
                )
                birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
                self.assertLessEqual(birth, recorded_at)
                self.assertLessEqual(recorded_at, datetime.now(timezone.utc))
                self.assertEqual(
                    manifest["supersedes_non_accepted_origin"][
                        "incident_manifest_sha256"
                    ],
                    INCIDENT_MANIFEST_PIN[1],
                )
                self.assertEqual(manifest["factual_semantic_delta_from_origin"], "none")

    def test_wrapper_v2_facts_rights_hashes_and_zero_promotions_are_unchanged(
        self,
    ) -> None:
        for wrapper_id, config in core.WRAPPER_CONFIGS.items():
            origin = ROOT / "source_artifacts" / config["origin_id"]
            corrected = ROOT / "source_artifacts" / wrapper_id
            with self.subTest(wrapper_id=wrapper_id):
                self.assertEqual(
                    (corrected / "README.md").read_bytes(),
                    (origin / "README.md").read_bytes(),
                )
                for filename in core.CONTENT_FILES[1:]:
                    old = json.loads((origin / filename).read_text())
                    new = json.loads((corrected / filename).read_text())
                    self.assertEqual(
                        core._semantic_document(
                            old,
                            origin_id=config["origin_id"],
                            wrapper_id=wrapper_id,
                        ),
                        core._semantic_document(
                            new,
                            origin_id=config["origin_id"],
                            wrapper_id=wrapper_id,
                        ),
                    )
                snapshot = json.loads((corrected / "source-snapshot.json").read_text())
                self.assertEqual(snapshot["source_records"], json.loads(
                    (origin / "source-snapshot.json").read_text()
                )["source_records"])
        gap_id = "gap-region-official-discovery-2026-07-21-v2"
        gap = ROOT / "source_artifacts" / gap_id
        gap_manifest = json.loads((gap / "manifest.json").read_text())
        gap_snapshot = json.loads((gap / "source-snapshot.json").read_text())
        self.assertEqual(gap_manifest["open_seed_integration"], "none")
        self.assertEqual(gap_snapshot["source_records"], [])
        self.assertTrue(all(value == 0 for value in gap_snapshot["totals"].values()))

    def test_parent_and_nested_imports_collision_tamper_and_symlink_fail_closed(
        self,
    ) -> None:
        self.assertNotEqual(core.__file__, shim.__file__)
        self.assertIs(core.validate_corrected_wrapper, shim.validate_corrected_wrapper)
        with self.assertRaisesRegex(SystemExit, "already exists"):
            core.build_corrected_discovery_wrappers_v2()
        wrapper_id = "global-underrepresented-official-discovery-2026-07-21-v2"
        source = ROOT / "source_artifacts" / wrapper_id
        with tempfile.TemporaryDirectory(prefix="wrapper-v2-tamper-") as temporary:
            copied = Path(temporary) / wrapper_id
            shutil.copytree(source, copied)
            manifest = copied / "manifest.json"
            manifest.chmod(0o644)
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "manifest is not canonical"):
                core.validate_corrected_wrapper(
                    wrapper_id, copied, require_frozen=False
                )
        with tempfile.TemporaryDirectory(prefix="wrapper-v2-symlink-") as temporary:
            linked = Path(temporary) / wrapper_id
            os.symlink(source, linked, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "ordinary directory"):
                core.validate_corrected_wrapper(wrapper_id, linked)

    def test_corrective_wrapper_code_pins_are_exact(self) -> None:
        for path, expected in CODE_PINS.items():
            with self.subTest(path=path.name):
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
