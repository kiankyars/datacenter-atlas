from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "definitions/satellite_recoveries/accepted-2026-07-20-v1.json"
)
REGISTRY_SHA256 = (
    "507b606c4ab65605766d7726072d715649830467838d9d24d423ba3b8aac59ad"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SatelliteRecoveryAcceptanceV1Tests(unittest.TestCase):
    def test_registry_is_canonical_pinned_and_fail_closed(self) -> None:
        raw = REGISTRY.read_bytes()
        document = json.loads(raw)
        self.assertEqual(
            raw,
            (
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n"
            ).encode("utf-8"),
        )
        self.assertEqual(_sha256(REGISTRY), REGISTRY_SHA256)
        self.assertEqual(stat.S_IMODE(REGISTRY.stat().st_mode), 0o644)
        self.assertEqual(
            set(document),
            {
                "accepted",
                "accepted_at",
                "format",
                "schema_version",
                "scope",
                "superseded",
            },
        )
        self.assertEqual(
            document["format"],
            "datacenter-atlas-satellite-recovery-acceptance-v1",
        )
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(
            document["scope"],
            {
                "atlas_release_integration": False,
                "global_completeness_claimed": False,
                "imagery_inference_created": False,
                "review_only": True,
                "source_batch_promoted": False,
                "unique_physical_site_count": None,
            },
        )

    def test_one_current_artifact_and_one_retained_superseded_wrapper(self) -> None:
        document = json.loads(REGISTRY.read_text(encoding="utf-8"))
        accepted = document["accepted"]
        self.assertEqual(
            accepted["artifact_id"],
            "2026-07-19-global-open-v3-unknown-033-recovered-25",
        )
        self.assertEqual(len(document["superseded"]), 1)
        superseded = document["superseded"][0]
        self.assertEqual(
            superseded["artifact_id"],
            "2026-07-19-global-open-v3-unknown-032-recovered-25",
        )
        self.assertNotEqual(accepted["artifact_id"], superseded["artifact_id"])
        self.assertIn("guard PID 4234", accepted["reason"])
        self.assertIn("unverified", accepted["reason"])
        self.assertIn("disclaims causal linkage", accepted["reason"])
        self.assertIn("obsolete reported guard PID 89259", superseded["reason"])

        for designation in (accepted, superseded):
            artifact_id = designation["artifact_id"]
            for label in (
                "batch_manifest",
                "definition",
                "inventory",
                "recovery_manifest",
                "sidecar",
            ):
                checkpoint = designation[label]
                path = ROOT / checkpoint["path"]
                self.assertTrue(path.is_file() and not path.is_symlink())
                self.assertEqual(path.stat().st_size, checkpoint["bytes"])
                self.assertEqual(_sha256(path), checkpoint["sha256"])
                if label in {"batch_manifest", "inventory", "recovery_manifest", "sidecar"}:
                    self.assertIn(artifact_id, path.parts)

        accepted_definition = json.loads(
            (ROOT / accepted["definition"]["path"]).read_text(encoding="utf-8")
        )
        accepted_manifest = json.loads(
            (ROOT / accepted["recovery_manifest"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(accepted_definition["incident"]["reported_guard_pid"], 4234)
        incident = accepted_manifest["source_evidence"]["incident"]
        self.assertEqual(incident["observation_verification"], "operator_supplied_unverified")
        self.assertFalse(incident["process_state_verified_by_recovery"])
        self.assertFalse(incident["guard_lock_verified_by_recovery"])
        self.assertFalse(incident["causal_linkage_claimed"])
        self.assertFalse(accepted_manifest["scope"]["source_batch_promoted"])
        self.assertFalse(
            accepted_manifest["scope"]["source_evidence_accepted_for_release"]
        )


if __name__ == "__main__":
    unittest.main()
