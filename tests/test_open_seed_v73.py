from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v73")
shim = importlib.import_module("datacenter_atlas.open_seed_v73")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v72.json"
BASE_RELEASE = ROOT / "releases/2026-07-21-open-seed-v72"
BUILDER = ROOT / "scripts/build_open_seed_v73.py"
RECORDED_AT = "2026-07-21T13:15:51Z"

DEFINITION_PIN = (
    88_004,
    "cf8a4cfb8861ab732cdb9e72a01cbdd01d0e435102c47fd6d92bc30ebf11f97d",
)
MANIFEST_PIN = (
    12_814,
    "229c572759ab493448b788946a0c8a61ff6995d0ab505bea2af08860a19e204d",
)
TREE_PIN = "692583b86324b746fd6edf0ec2dc5101efa86ce0f08e04831e0d471e767a6394"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        6_014,
        "d1e3187c05131890a09b46f27d6c7089c7042a5623154acea712b1204aa9a70c",
    ),
    "README.md": (
        3_924,
        "8b284738367298088eb9b05da75e6348b7608c130252440dce1046c58d58d6db",
    ),
    "atlas.geojson": (
        2_885_700,
        "691585d470e7284f0185515d63f3c9b0507f528f039f3070804790927ee48672",
    ),
    "capacity_estimates.csv": (
        257_212,
        "1fa99c1592e79966a2c9e823ec2ea9f5000e45a674471864bf2ad06331118cb6",
    ),
    "construction_pipeline.csv": (
        536_037,
        "751590cad43558ad2bbf655f2672be0109e12baadbbfa4288d3832b533200e59",
    ),
    "construction_source_signals.csv": (
        346_304,
        "260fbfbd0af1a8bfd8d50b300ec19f039eae697d808710fb2a3acd1847012d7c",
    ),
    "entities.csv": (
        887_459,
        "8c50475f1a58a7f7623a4eef2706be3f63bca0175a5fe4fffecdd548442944e7",
    ),
    "evidence.csv": (
        204_886,
        "536730f17c17bb37f177dfec3cae1825897b8e98ebecea1ea4c2e370bc478018",
    ),
    "lifecycle_freshness.csv": (
        138_270,
        "b286292746c17cea1f8794373fde599f4c2ff9ce1a728440d701da490b311770",
    ),
    "manifest.json": MANIFEST_PIN,
    "resolution_candidates.csv": (
        6_889,
        "b893812c703ea3bfe6beba6c56d121a2fab8f75e142313f7562bb92239564009",
    ),
    "resolution_candidates.json": (
        10_348,
        "948ea2d6989115e71f2d56cb827d430b8379b721e6a40872ed4f22665acf83f2",
    ),
    "source_inputs.json": (
        323_196,
        "b0ca3e092de3eb2372066a7a92e316c84a3c4566c35b4004661905017b834a29",
    ),
    "summary.json": (
        3_234,
        "967061d106f5639ba9b2a27414bb7d73096544d7e2b85e39dcd05a01fe2150a0",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV73Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(BASE_DEFINITION.read_text())
        cls.definition = json.loads(DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(cls.base, recorded_at=RECORDED_AT)
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v73-test-")
        cls.connection = core._build_database(
            cls.base,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
            recorded_at=RECORDED_AT,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("open seed v73 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_frozen_definition_release_and_every_file_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(
            ((RELEASE / "manifest.json").stat().st_size, sha256(RELEASE / "manifest.json")),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, sha256(path)), expected)

    def test_exact_v72_adjacency_appends_only_four_eligible_sources(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 393)
        self.assertEqual(len(after), 397)
        self.assertEqual(after[:393], before)
        self.assertEqual(
            [row["path"] for row in after[393:]], sorted(core.ADDITION_PINS)
        )
        self.assertEqual(self.definition["curated_inputs"], after)
        selected_paths = {row["path"] for row in after}
        self.assertFalse(selected_paths & core.EXCLUDED_SOURCE_PATHS)
        self.assertFalse(any("cmc-creative-space" in path for path in selected_paths))
        self.assertFalse(any("bolivia-fiscalia" in path for path in selected_paths))
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "freshness_contract",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(self.definition[key], self.base[key])
        self.assertEqual(set(self.definition), set(self.base))

    def test_official_artifact_and_typed_claim_boundaries_are_exact(self) -> None:
        carrier = core._validate_official_artifact()
        self.assertEqual(carrier["manifest"]["recorded_at"], core.OFFICIAL_RECORDED_AT)
        documents = core._validate_additions(RECORDED_AT)
        self.assertEqual(set(documents), set(core.ADDITION_PINS))
        self.assertEqual(
            {
                (row["metric"], row["stage"], row["unit"], row["base"])
                for document in documents.values()
                for row in document["capacities"]
            },
            {
                ("critical_it_mw", "planned", "MW", 5.28),
                ("pue", "design", "ratio", 1.4),
            },
        )
        bichuten = documents[
            "sources/curated-official-2026-07-21-bichuten-chovar-current-build.json"
        ]
        self.assertEqual(bichuten["capacities"], [])
        for document in documents.values():
            self.assertEqual(document["workloads"], [])
            for name in ("campus", "project"):
                self.assertIsNone(document[name]["coordinates"])
                self.assertIsNone(document[name]["geometry"])

    def test_database_delta_is_exact_and_preserves_typed_boundaries(self) -> None:
        core._validate_database_contract(
            self.connection, self.base, recorded_at=RECORDED_AT
        )
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "capacity_estimates",
                "operating_model_observations",
                "workload_observations",
            )
        }
        self.assertEqual(
            counts,
            {
                "entities": 818,
                "evidence": 643,
                "entity_snapshots": 838,
                "lifecycle_observations": 479,
                "capacity_estimates": 535,
                "operating_model_observations": 59,
                "workload_observations": 128,
            },
        )

    def test_public_counts_freshness_and_capacity_guardrails(self) -> None:
        core._validate_release_delta(RELEASE, recorded_at=RECORDED_AT)
        core._validate_release_facts(RELEASE, recorded_at=RECORDED_AT)
        summary = json.loads((RELEASE / "summary.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(
            {
                "entities": summary["entities_total"],
                "database_evidence": summary["evidence_total"],
                "exported_evidence": manifest["evidence_records"],
                "capacity": manifest["capacity_estimates"],
                "pipeline": manifest["construction_pipeline_records"],
                "signals": manifest["construction_source_signals"],
                "freshness": manifest["lifecycle_freshness_records"],
                "located": summary["entities_with_coordinates"],
            },
            {
                "entities": 818,
                "database_evidence": 643,
                "exported_evidence": 520,
                "capacity": 534,
                "pipeline": 420,
                "signals": 322,
                "freshness": 462,
                "located": 192,
            },
        )
        additions = {
            row["stable_key"]: row
            for row in csv_rows(RELEASE / "entities.csv")
            if row["stable_key"] in core.ADDED_ENTITY_KEYS
        }
        self.assertEqual(set(additions), core.ADDED_ENTITY_KEYS)
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in csv_rows(RELEASE / "lifecycle_freshness.csv")
            )
        )
        self.assertFalse(manifest["current_status_inferred"])

    def test_publication_time_contract_and_no_private_stage_or_lock(self) -> None:
        target = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(target, datetime.now(UTC))
        for path in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            with self.subTest(path=path.name):
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_birthtime, UTC), target
                )
                self.assertLessEqual(
                    datetime.fromtimestamp(path.stat().st_mtime, UTC), target
                )
        self.assertGreaterEqual(datetime.fromtimestamp(DEFINITION.stat().st_ctime, UTC), target)
        self.assertGreaterEqual(datetime.fromtimestamp(RELEASE.stat().st_ctime, UTC), target)
        core._validate_publication_times(
            DEFINITION, RELEASE, recorded_at=RECORDED_AT, require_live=True
        )
        leftovers = [
            path.name
            for parent in (ROOT / "sources", ROOT / "releases", ROOT)
            for path in parent.iterdir()
            if "v73" in path.name
            and (path.name.startswith(".") or path.name == core.PUBLICATION_LOCK.name)
        ]
        self.assertEqual(leftovers, [])

    def test_offline_replay_shim_idempotent_builder_and_base_nonmutation(self) -> None:
        self.assertIs(core.validate_open_seed_v73, shim.validate_open_seed_v73)
        guard = core._guard_state()
        with self._network_guard():
            manifest = shim.validate_open_seed_v73(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 818)
        with self.assertRaisesRegex(core.OpenSeedV73Error, "exactly two offline"):
            core.validate_open_seed_v73(replay_count=1)
        with self.assertRaisesRegex(
            core.OpenSeedV73Error, "later than validation wall clock"
        ):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-22T00:00:00Z",
                validation_wall_clock=datetime(
                    2026, 7, 21, 23, 59, 59, tzinfo=UTC
                ),
            )
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")
        self.assertEqual(core._guard_state(), guard)
        self.assertEqual(
            (BASE_DEFINITION.stat().st_size, sha256(BASE_DEFINITION)),
            core.BASE_DEFINITION_PIN,
        )
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), core.BASE_MANIFEST_SHA256
        )
        self.assertEqual(core.v69.tree_digest(BASE_RELEASE), core.BASE_TREE_SHA256)
        with self.assertRaisesRegex(
            core.OpenSeedV73Error, "later than validation wall clock"
        ):
            core._validate_definition(
                self.definition,
                self.base,
                validation_wall_clock=(
                    datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
                    - timedelta(seconds=1)
                ),
            )


if __name__ == "__main__":
    unittest.main()
