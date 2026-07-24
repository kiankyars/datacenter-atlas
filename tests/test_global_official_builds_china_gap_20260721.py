from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import global_official_builds_china_gap_20260721 as tranche
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts/global-official-builds-china-gap-2026-07-21-v1"
TRASH = Path("/Users/kian/.Trash/dc-official-china-gap-20260721.BUEbM9")
RECORDED_AT = "2026-07-21T16:09:40Z"

SOURCE_PINS = {
    "curated-official-2026-07-21-runze-chongqing-phase-2-p6-current-build.json": (
        3_979,
        "c773e6639f7e313d67e64ab19f95a8b643dcabbe87b29e247d2cf3e04cbc6bc2",
    ),
    "curated-official-2026-07-21-china-telecom-guizhou-b5-b6-current-build.json": (
        4_143,
        "5a01059d9352a79cfd5fd46c686d339125c110d179ecbfe49d3eda740d0d8d14",
    ),
    "curated-official-2026-07-21-baoji-digital-building-mobile-dc-current-build.json": (
        3_535,
        "4103dfebb86ee5b22d39a09874708129ec5985e568ad552d86c2f9d234bd27a5",
    ),
    "curated-official-2026-07-21-digital-qinghai-telecom-phase-2-current-build.json": (
        4_048,
        "3fc30fdb279d8b812b74ce1a719d3ca8a46aa804c139ddda14c42ab6ce3fcfe1",
    ),
    "curated-official-2026-07-21-mobile-plateau-haidong-phase-2-current-build.json": (
        3_998,
        "7db2d1cbeb6b81ceb0f62e5e826acff0df90d8810ccd9d267862ed1b7a93ff0d",
    ),
    "curated-official-2026-07-21-zhipu-iflytek-haidong-ai-base-current-build.json": (
        4_090,
        "211f3a87d4f3db27234759f3f5211639eae0487d69125837a89cd93971cc2788",
    ),
    "curated-official-2026-07-21-haidong-training-inference-ai-current-build.json": (
        4_070,
        "6a4cc0a34924e083a5d1e68015577143b0de7040d407551f1d82d4414f543fb0",
    ),
    "curated-official-2026-07-21-wuhu-longteng-ai-park-current-build.json": (
        3_998,
        "13b769290b17bbd0b2fb61587ff207cb9bbae5b82c2494de3ab4a66f5a6dc05c",
    ),
    "curated-official-2026-07-21-china-telecom-tongling-dated-build.json": (
        4_104,
        "4861bd60429a24577eef9bb89f51035f2306c0249f061389a9a75c64e495b5de",
    ),
    "curated-official-2026-07-21-runze-hong-kong-sandy-ridge-current-build.json": (
        6_054,
        "f16529810f7d6043f1eb46c93892bd75bc99f776c1df0d941d4debbbf1e18de4",
    ),
}

ARTIFACT_PINS = {
    "README.md": (
        2_236,
        "de13b07713497fe492a6f4ac4526d235edd4e13ea357c96380564c86b487aabd",
    ),
    "candidate-assessment.json": (
        9_172,
        "a0ab737c353aad62774aaf1160cb437aebfc9bb97bcda2e046a198ffc7318fa7",
    ),
    "manifest.json": (
        1_781,
        "6de9a1a2e0b05a1b4523d45cc10a9cba8ecb36c3893243bb789f9687c26c6db8",
    ),
    "manifest.sha256": (
        80,
        "1adc85c15b38eeb8b0616befc559f2453b01d1cb5f5e4cb477b04b60b3bb356d",
    ),
    "retrieval-inventory.json": (
        13_603,
        "75079fb2285a30a7f3dfd14f67c1776c12ab82f9d8327632bb59d3377f3ef32c",
    ),
    "rights-and-disposition.json": (
        1_390,
        "a72d59ff28ea4b676156aed1dc9c71a49d955e812927f9d1798962790abc4f1a",
    ),
    "source-snapshot.json": (
        10_494,
        "47a888270f1f25de13a20e561bb8fa4322178b703d7394f86597784409db6346",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsChinaGapTests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        stack.enter_context(
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network access during offline replay"),
            )
        )
        return stack

    def test_frozen_artifact_hashes_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(set(ARTIFACT_PINS), {path.name for path in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            path = ARTIFACT / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(
            tree_digest(ARTIFACT),
            "3d102335bee0f6d34ac4b6c07e8801ce8b05ca15ab6396f9a07744eaf1b408fc",
        )

        target = instant(RECORDED_AT).timestamp()
        artifact_metadata = ARTIFACT.stat(follow_symlinks=False)
        self.assertLessEqual(
            max(artifact_metadata.st_birthtime, artifact_metadata.st_mtime), target
        )
        self.assertGreaterEqual(artifact_metadata.st_ctime, target)
        for path in ARTIFACT.iterdir():
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
        for name in SOURCE_PINS:
            metadata = (ROOT / "sources" / name).stat(follow_symlinks=False)
            self.assertLessEqual(max(metadata.st_birthtime, metadata.st_mtime), target)
            self.assertGreaterEqual(metadata.st_ctime, target)

    def test_sources_are_exact_schema_v11_and_double_import_offline(self) -> None:
        expected_documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(expected_documents))
        for name, expected_pin in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected_pin)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(path.read_bytes(), tranche._canonical(expected_documents[name]))

        with self._offline():
            counts = tranche._offline_import(
                tranche._source_paths(ROOT / "sources"), RECORDED_AT
            )
        self.assertEqual(
            counts,
            {
                "entities": 20,
                "entity_snapshots": 20,
                "evidence": 11,
                "lifecycle_observations": 11,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
            },
        )

    def test_claim_boundaries_and_all_dated_statuses(self) -> None:
        documents = tranche.expected_source_documents()
        for document in documents.values():
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])

        expected_statuses = {
            tranche.SOURCE_FILENAMES[0]: [
                ("shell", "2026-04-01", "authoritative_physical_status_update")
            ],
            tranche.SOURCE_FILENAMES[1]: [
                ("shell", "2026-04-22", "authoritative_physical_status_update")
            ],
            tranche.SOURCE_FILENAMES[2]: [
                (
                    "under_construction",
                    "2026-07-15",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[3]: [
                (
                    "under_construction",
                    "2026-06-23",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[4]: [
                (
                    "under_construction",
                    "2026-06-23",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[5]: [
                (
                    "under_construction",
                    "2026-06-23",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[6]: [
                (
                    "under_construction",
                    "2026-06-23",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[7]: [
                (
                    "under_construction",
                    "2026-02-26",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[8]: [
                (
                    "under_construction",
                    "2026-02-07",
                    "authoritative_physical_status_update",
                )
            ],
            tranche.SOURCE_FILENAMES[9]: [
                (
                    "under_construction",
                    "2026-03-28",
                    "authoritative_construction_start",
                ),
                ("under_construction", "2026-05-20", "physical_observation"),
            ],
        }
        self.assertEqual(set(expected_statuses), set(documents))
        for name, expected in expected_statuses.items():
            actual = [
                (row["value"], row["as_of_date"], row["method"])
                for row in documents[name]["lifecycle"]
            ]
            self.assertEqual(actual, expected)

        source_blob = json.dumps(documents, ensure_ascii=False)
        self.assertNotIn("changle-airport", source_blob.lower())
        self.assertNotIn("chinatelecom.com.cn", source_blob)
        self.assertNotIn("15000P", source_blob)
        self.assertNotIn("30EFLOPS", source_blob)

    def test_candidate_incidents_capture_and_v73_nonmutation(self) -> None:
        assessment = json.loads((ARTIFACT / "candidate-assessment.json").read_text())
        self.assertEqual(
            (
                assessment["candidate_count"],
                assessment["source_record_count"],
                assessment["seed_eligible_count"],
                assessment["review_only_count"],
            ),
            (11, 10, 10, 1),
        )
        rows = {row["candidate_id"]: row for row in assessment["candidates"]}
        changle = rows["changle-airport-free-trade-zone-ai-computing-center"]
        self.assertEqual(
            changle["decision"], "review_only_no_direct_publisher_capture"
        )
        self.assertFalse(changle["source_record_created"])
        self.assertFalse(changle["seed_eligible"])
        self.assertIsNone(changle["last_observed_physical_date"])
        self.assertFalse(
            changle["browser_context_not_evidence"]["used_for_normalized_claims"]
        )
        for row in rows.values():
            self.assertFalse(row["confirmed_current_status"])
            self.assertEqual(row["current_status_after_last_observation"], "unknown")

        inventory = json.loads((ARTIFACT / "retrieval-inventory.json").read_text())
        self.assertEqual(inventory["successful_direct_publisher_body_count"], 8)
        self.assertEqual(inventory["technical_incident_group_count"], 2)
        incidents = {row["incident_id"]: row for row in inventory["technical_incidents"]}
        self.assertFalse(incidents["changle-direct-publisher-timeouts"]["evidence_use"])
        self.assertFalse(incidents["china-telecom-http-412"]["evidence_use"])
        self.assertFalse(incidents["china-telecom-http-412"]["claims_copied"])

        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        tranche._validate_capture_directory(TRASH)
        self.assertEqual(len(list(TRASH.iterdir())), 39)
        self.assertEqual(tree_digest(TRASH), tranche.CAPTURE_TREE_SHA256)
        tranche._validate_v73_nonmutation()
        definition = json.loads(tranche.V73_DEFINITION.read_text())
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertFalse(
            selected & {f"sources/{name}" for name in tranche.SOURCE_FILENAMES}
        )

    def test_no_replace_collision_and_no_staging_residue(self) -> None:
        self.assertFalse(tranche.PUBLICATION_LOCK.exists())
        self.assertEqual(list(ROOT.glob("sources/.official-builds-china-gap.*")), [])
        self.assertEqual(
            list(
                ROOT.glob(
                    "source_artifacts/.global-official-builds-china-gap-2026-07-21-v1.*"
                )
            ),
            [],
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            stage = directory / "stage"
            final = directory / "final"
            stage.write_bytes(b"owned")
            final.write_bytes(b"late")
            with self.assertRaisesRegex(tranche.ChinaGapError, "collision"):
                tranche._promote_noreplace(stage, final)
            self.assertEqual(stage.read_bytes(), b"owned")
            self.assertEqual(final.read_bytes(), b"late")


if __name__ == "__main__":
    unittest.main()
