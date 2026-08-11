from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v56 import tree_digest
from datacenter_atlas.service import validate_database


try:
    tranche = importlib.import_module(
        "datacenter_atlas.datacenter_atlas."
        "global_official_builds_us_operator_gap_20260721"
    )
except ModuleNotFoundError:
    tranche = importlib.import_module(
        "datacenter_atlas.global_official_builds_us_operator_gap_20260721"
    )


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT / "source_artifacts/global-official-builds-us-operator-gap-2026-07-21-v1"
)
TRASH = Path("/Users/kian/.Trash/dc-riot-20260721.DX92tY")
RECORDED_AT = "2026-07-22T00:01:20Z"
ARTIFACT_TREE_SHA256 = (
    "a3d16d54c370764b8eb4278a6dddf161717825ac3790f731308627301f5ed4c0"
)
ARTIFACT_PINS = {
    "README.md": (
        1_301,
        "c66b6d5b3c0645beb025b04f4e1e157590e4490269b650f36546be1ec703ea4d",
    ),
    "candidate-assessment.json": (
        6_407,
        "71a0c2cd9cc315e9d3d11a2d050a5b49a1ccaef570228ae212cec18a65a527a4",
    ),
    "manifest.json": (
        1_704,
        "2f6c50c48cddf94cf82c2218e6c53857be744a0d1b9c78aeefb830becf24990e",
    ),
    "manifest.sha256": (
        80,
        "47abf9f0ef9750e95ba2973024eca048c04ef6632a6d6f0967e69e7eda983126",
    ),
    "retrieval-inventory.json": (
        11_380,
        "569ba4f9519f8f2b8d3ef55fc30bca0ad7610f18b05722aa8f33fd78e2fa6c04",
    ),
    "rights-and-disposition.json": (
        1_171,
        "ab1428ee4ad1af3ac87c59b6141cc304a3187e1cda159fc0eb856a7b884c8c54",
    ),
    "source-snapshot.json": (
        5_682,
        "d9d7ce079d10f440f725a41d09e1f75929d85caea5ede83ee2bb08ab2aff8a86",
    ),
}
SOURCE_PINS = {
    "curated-official-2026-07-21-riot-rockdale-amd-25mw-retrofit.json": (
        6_049,
        "da0c2da55005f36bb518ac6153a7aa8474f8d11a6d34348e27221423bbd42653",
    ),
    "curated-official-2026-07-21-riot-rockdale-amd-first-phase-operational-closure.json": (
        8_922,
        "d0c749f1d5b8da22adb194cd84ef8a9a9ed6c3fd814fa87e95039999ec201cbc",
    ),
    "curated-official-2026-07-21-databank-atl5-current-build.json": (
        12_462,
        "7f12bee0ea8dc86222fb314df9fcd5e3e2eefccf36284b2ed09868649548656c",
    ),
    "curated-official-2026-07-21-databank-atl6-current-build.json": (
        12_430,
        "1ce9df5cf2293b7b609c621722e05909f3e6a0be369b8fa76c58f49cd873146a",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class GlobalOfficialBuildsUSOperatorGapTests(unittest.TestCase):
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

    def test_frozen_artifact_exact_closure_and_temporal_publication(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = tranche.validate_artifact(ARTIFACT)
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)
        self.assertEqual(set(ARTIFACT_PINS), {item.name for item in ARTIFACT.iterdir()})
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        for name, expected in ARTIFACT_PINS.items():
            path = ARTIFACT / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(ARTIFACT), ARTIFACT_TREE_SHA256)

        target = instant(RECORDED_AT).timestamp()
        for path in (ARTIFACT, *ARTIFACT.iterdir()):
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime), target
            )
        self.assertGreaterEqual(ARTIFACT.stat().st_ctime, target)
        for name in SOURCE_PINS:
            self.assertGreaterEqual((ROOT / "sources" / name).stat().st_ctime, target)

    def test_sources_import_exact_claim_contract_idempotently_offline(self) -> None:
        documents = tranche.expected_source_documents()
        self.assertEqual(set(SOURCE_PINS), set(documents))
        for name, expected in SOURCE_PINS.items():
            path = ROOT / "sources" / name
            self.assertFalse(path.is_symlink())
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(path.read_bytes(), tranche._canonical(documents[name]))
            self.assertEqual(documents[name]["workloads"], [])
            for entity in ("campus", "project"):
                self.assertIsNone(documents[name][entity]["coordinates"])
                self.assertIsNone(documents[name][entity]["geometry"])

        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for _ in range(2):
                for name in SOURCE_PINS:
                    adapter.import_file(
                        connection,
                        ROOT / "sources" / name,
                        recorded_at=RECORDED_AT,
                    )
            validate_database(connection)
            actual = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "entity_snapshots",
                    "evidence",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                actual,
                {
                    "entities": 6,
                    "entity_snapshots": 6,
                    "evidence": 6,
                    "lifecycle_observations": 4,
                    "operating_model_observations": 2,
                    "workload_observations": 0,
                    "capacity_estimates": 3,
                },
            )
            lifecycle = {
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, l.status, l.as_of_date "
                    "FROM lifecycle_observations AS l "
                    "JOIN entities AS e ON e.id=l.entity_id"
                )
            }
            self.assertEqual(
                lifecycle,
                {
                    (
                        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
                        "under_construction",
                        "2026-01-16",
                    ),
                    (
                        "curated:riot-rockdale-site:amd-lease-first-phase",
                        "operational",
                        "2026-01-31",
                    ),
                    (
                        "curated:databank-lithia-springs-campus:atl5-current-build",
                        "under_construction",
                        "2026-05-07",
                    ),
                    (
                        "curated:databank-lithia-springs-campus:atl6-current-build",
                        "under_construction",
                        "2026-05-07",
                    ),
                },
            )
            capacities = {
                tuple(row)
                for row in connection.execute(
                    "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                    "FROM capacity_estimates AS c "
                    "JOIN entities AS e ON e.id=c.entity_id"
                )
            }
            self.assertEqual(
                capacities,
                {
                    (
                        "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
                        "critical_it_mw",
                        "planned",
                        "MW",
                        25.0,
                    ),
                    (
                        "curated:databank-lithia-springs-campus:atl5-current-build",
                        "critical_it_mw",
                        "design",
                        "MW",
                        48.0,
                    ),
                    (
                        "curated:databank-lithia-springs-campus:atl6-current-build",
                        "critical_it_mw",
                        "design",
                        "MW",
                        72.0,
                    ),
                },
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM capacity_estimates WHERE stage='operational'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                {
                    tuple(row)
                    for row in connection.execute(
                        "SELECT e.stable_key, o.operating_model "
                        "FROM operating_model_observations AS o "
                        "JOIN entities AS e ON e.id=o.entity_id"
                    )
                },
                {
                    (
                        "curated:databank-lithia-springs-campus:atl5-current-build",
                        "colocation",
                    ),
                    (
                        "curated:databank-lithia-springs-campus:atl6-current-build",
                        "colocation",
                    ),
                },
            )

    def test_collision_rights_and_excluded_expansion_witnesses(self) -> None:
        capture = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, TRASH)
        with self._offline():
            tranche._validate_frozen_witnesses()
            tranche._validate_source_collisions()
            tranche._validate_capture_directory(capture)
        self.assertFalse(tranche.CAPTURE_ORIGIN.exists())
        self.assertEqual(tree_digest(capture), tranche.CAPTURE_TREE_SHA256)
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["successful_http_200_body_captures"], 7)
        self.assertEqual(inventory["http_error_header_only_captures"], 3)
        self.assertFalse(inventory["raw_capture_redistributed"])
        self.assertFalse(
            next(
                row
                for row in inventory["controlled_captures"]
                if row["capture_id"] == "riot_q1"
            )["used_for_normalized_claims"]
        )
        rights = json.loads(
            (ARTIFACT / "rights-and-disposition.json").read_text(encoding="utf-8")
        )
        self.assertTrue(rights["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(rights["temporary_capture_recoverable"])
        self.assertFalse(rights["raw_capture_redistributed"])

    def test_existing_build_is_idempotent_and_network_free(self) -> None:
        with self._offline():
            result = tranche.build()
        self.assertEqual(result["status"], "existing-identical")
        self.assertEqual(result["recorded_at"], RECORDED_AT)
        self.assertEqual(result["artifact_tree_sha256"], ARTIFACT_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
