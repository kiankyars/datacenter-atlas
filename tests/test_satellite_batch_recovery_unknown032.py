from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPERSEDED = (
    ROOT
    / "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-032-recovered-25"
)
SUPERSEDED_DEFINITION = (
    ROOT
    / "definitions/satellite_recoveries/2026-07-19-global-open-v3-unknown-032-recovered-25.json"
)
ACCEPTED = (
    ROOT
    / "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25"
)
ACCEPTED_DEFINITION = (
    ROOT
    / "definitions/satellite_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25.json"
)

SUPERSEDED_DEFINITION_SHA256 = (
    "8a566e028f75adaeae93e2cce0b7a37c76c383459ba49c2e4cfe588a232591a2"
)
SUPERSEDED_MANIFEST_SHA256 = (
    "e2bdc1a230cbe8b37e29ec55269531afdfa23c56c5f7b5d09f45bf7ee68da8c9"
)
ACCEPTED_DEFINITION_SHA256 = (
    "1b054ac9c1091e1470576fcf9f14df05a64cb6d679a22ab413430957ffbcb420"
)
ACCEPTED_MANIFEST_SHA256 = (
    "178f52ad3c42117ea19561c123eef87fe1ed7331c79e9c5c1596bd8d2b7cbfb1"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Unknown032SupersededProvenanceTests(unittest.TestCase):
    def test_unknown032_is_pinned_but_not_the_accepted_recovery(self) -> None:
        self.assertEqual(
            _sha256(SUPERSEDED_DEFINITION), SUPERSEDED_DEFINITION_SHA256
        )
        self.assertEqual(
            _sha256(SUPERSEDED / "recovery-manifest.json"),
            SUPERSEDED_MANIFEST_SHA256,
        )
        self.assertEqual(_sha256(ACCEPTED_DEFINITION), ACCEPTED_DEFINITION_SHA256)
        self.assertEqual(
            _sha256(ACCEPTED / "recovery-manifest.json"),
            ACCEPTED_MANIFEST_SHA256,
        )

        superseded_definition = json.loads(
            SUPERSEDED_DEFINITION.read_text(encoding="utf-8")
        )
        superseded_manifest = json.loads(
            (SUPERSEDED / "recovery-manifest.json").read_text(encoding="utf-8")
        )
        accepted_definition = json.loads(
            ACCEPTED_DEFINITION.read_text(encoding="utf-8")
        )
        accepted_manifest = json.loads(
            (ACCEPTED / "recovery-manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            superseded_definition["artifact_id"],
            "2026-07-19-global-open-v3-unknown-032-recovered-25",
        )
        self.assertEqual(
            superseded_definition["artifact_id"], superseded_manifest["artifact_id"]
        )
        self.assertEqual(superseded_definition["recovered_at"], "2026-07-19T23:10:00Z")
        self.assertEqual(superseded_manifest["recovered_at"], "2026-07-19T23:10:00Z")
        superseded_incident = superseded_definition["incident"]
        self.assertEqual(superseded_incident["reported_guard_pid"], 89259)
        self.assertEqual(
            [row["status"] for row in superseded_incident["launchd_service_observations"]],
            ["reported absent after termination", "exact service booted out"],
        )
        self.assertIn(
            "operator reported that writer processes had been stopped externally",
            superseded_incident["handling"],
        )
        self.assertNotIn(
            "operator-supplied incident notes are retained as unverified context only",
            superseded_incident["handling"],
        )

        self.assertEqual(
            accepted_definition["artifact_id"],
            "2026-07-19-global-open-v3-unknown-033-recovered-25",
        )
        self.assertEqual(
            accepted_definition["artifact_id"], accepted_manifest["artifact_id"]
        )
        self.assertEqual(accepted_definition["recovered_at"], "2026-07-19T23:56:32Z")
        self.assertEqual(accepted_manifest["recovered_at"], "2026-07-19T23:56:32Z")
        accepted_incident = accepted_definition["incident"]
        self.assertEqual(accepted_incident["reported_guard_pid"], 4234)
        self.assertTrue(
            all(
                row["status"].endswith("; unverified by recovery")
                for row in accepted_incident["launchd_service_observations"]
            )
        )
        self.assertIn("unverified context only", accepted_incident["handling"])
        self.assertIn("did not infer causal linkage", accepted_incident["handling"])

        self.assertNotEqual(
            superseded_definition["artifact_id"], accepted_definition["artifact_id"]
        )
        self.assertNotEqual(SUPERSEDED.name, ACCEPTED.name)
        self.assertEqual(ACCEPTED.name, accepted_definition["artifact_id"])


if __name__ == "__main__":
    unittest.main()
