from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import csv
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_v56 import tree_digest


try:
    v87 = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v87")
except ModuleNotFoundError:
    v87 = importlib.import_module("datacenter_atlas.open_seed_v87")


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v87.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
RECORDED_AT = "2026-07-22T00:06:19Z"
DEFINITION_PIN = (
    103_031,
    "bf0ef1b6bbe9f4f7edb4525de89d487de1e03ed5eaaccc1a0e122e24d5c9bf08",
)
RELEASE_TREE_SHA256 = (
    "02be747070df5f998080ca7c54a94146649a54b84078850c4c31522ae05c6185"
)
RELEASE_PINS = {
    "ATTRIBUTION.txt": (
        7_662,
        "f20b4b1fc20f8d9fde2ab6dca828ee14b33fa396ed9c1cd3f1d6dc5b2d44a502",
    ),
    "README.md": (
        7_226,
        "36c0a816d8b78c47ab1cc931dcfba44ae73e6f14351e5fcd8f3976ce774abf4f",
    ),
    "atlas.geojson": (
        3_252_268,
        "0eceafe042f6e91b17dac8f8d03d56ab2e484b429ee6ddbaedd6cc4215e59445",
    ),
    "capacity_estimates.csv": (
        266_863,
        "b1422f036b66507d62d48613259d5151f3128e5962e9b22c42debbdf9659b11b",
    ),
    "construction_pipeline.csv": (
        584_213,
        "68b3dca51389ff26dd7ce2e62299828a6cb4aa80ac80b458e17c1d8f3df5a96f",
    ),
    "construction_source_signals.csv": (
        397_133,
        "b7d1c8fe522df80de76884483c302454eff34b1a8bc258bdf9c151042069bd24",
    ),
    "entities.csv": (
        984_920,
        "1d214eba7d0482dae402930cfa5eb1b6e26b3df6a60c27571670c0929c8f02dc",
    ),
    "evidence.csv": (
        242_654,
        "3674ca751f00ae2c574d275ec66bcbf929437ee633c72c98f6c4903474ebc14b",
    ),
    "lifecycle_freshness.csv": (
        156_474,
        "602f07bf7f28f8f1e0a3f4f91a4b7e113ef2972590b6db4bdf1e07228ff5c31d",
    ),
    "manifest.json": (
        15_566,
        "6b2787e982049f1bcab139fce874880499c8610e2e71bb6bde091bcc101abf35",
    ),
    "resolution_candidates.csv": (
        8_749,
        "ac5b26629b02892e8f5a950221a2f0fcffcb848f40cfc47ae3ae6fb4da14e0cc",
    ),
    "resolution_candidates.json": (
        13_272,
        "a5d26da56b133ffe32f7b6f9d57f123af7bb3f647636301e678036fcb029e87d",
    ),
    "source_inputs.json": (
        390_691,
        "16b8d2126c467680c8e047ed0e933161fac80e384a449fac3299bc7c71f2536e",
    ),
    "summary.json": (
        3_446,
        "e4efa5a4b6983ca301faf723c9930edae9b8921ba46a8845adf93cee81be3b2c",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV87Tests(unittest.TestCase):
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

    def test_frozen_definition_release_and_temporal_publication(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_PINS), {path.name for path in RELEASE.iterdir()})
        for name, expected in RELEASE_PINS.items():
            path = RELEASE / name
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(tree_digest(RELEASE), RELEASE_TREE_SHA256)

        target = instant(RECORDED_AT).timestamp()
        for path in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            metadata = path.stat(follow_symlinks=False)
            self.assertLessEqual(
                max(metadata.st_birthtime, metadata.st_mtime), target
            )
        self.assertGreaterEqual(DEFINITION.stat().st_ctime, target)
        self.assertGreaterEqual(RELEASE.stat().st_ctime, target)

    def test_definition_is_exact_four_input_append_to_v86(self) -> None:
        base = json.loads(v87.BASE_DEFINITION.read_text(encoding="utf-8"))
        document = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(document["release_id"], v87.RELEASE_ID)
        self.assertEqual(document["build"], {"as_of": v87.AS_OF, "recorded_at": RECORDED_AT})
        self.assertEqual(len(base["curated_inputs"]), 452)
        self.assertEqual(len(document["curated_inputs"]), 456)
        self.assertEqual(document["curated_inputs"][:452], base["curated_inputs"])
        self.assertEqual(
            [row["path"] for row in document["curated_inputs"][452:]],
            list(v87.ADDITION_ORDER),
        )
        self.assertEqual(
            [row["sha256"] for row in document["curated_inputs"][452:]],
            [v87.ADDITION_PINS[path][1] for path in v87.ADDITION_ORDER],
        )
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "freshness_contract",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(document[key], base[key])

    def test_exact_summary_and_added_release_contract(self) -> None:
        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 933)
        self.assertEqual(summary["campuses_total"], 487)
        self.assertEqual(summary["projects_total"], 446)
        self.assertEqual(summary["evidence_total"], 769)
        self.assertEqual(summary["construction_pipeline_records"], 472)
        self.assertEqual(summary["entities_with_coordinates"], 213)
        self.assertEqual(summary["campuses_with_coordinates"], 141)
        self.assertEqual(summary["capacity_estimates_current"], 555)
        self.assertEqual(summary["recorded_at"], RECORDED_AT)

        entities = {
            row["stable_key"]: row
            for row in csv_rows(RELEASE / "entities.csv")
            if row["stable_key"] in v87.ADDED_ENTITY_KEYS
        }
        self.assertEqual(set(entities), v87.ADDED_ENTITY_KEYS)
        self.assertTrue(
            all(not row["latitude"] and not row["longitude"] for row in entities.values())
        )
        self.assertEqual(
            entities[
                "curated:riot-rockdale-site:amd-lease-first-phase"
            ]["capacity_estimates_json"],
            "[]",
        )
        self.assertEqual(
            entities[
                "curated:databank-lithia-springs-campus:atl5-current-build"
            ]["operating_model"],
            "colocation",
        )
        self.assertEqual(
            entities[
                "curated:databank-lithia-springs-campus:atl6-current-build"
            ]["operating_model"],
            "colocation",
        )
        freshness = {
            row["stable_key"]: row
            for row in csv_rows(RELEASE / "lifecycle_freshness.csv")
            if row["stable_key"] in v87.ADDED_PROJECT_KEYS
        }
        self.assertEqual(set(freshness), v87.ADDED_PROJECT_KEYS)
        self.assertTrue(
            all(
                row["status_semantics"] == "last_observed"
                and row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness.values()
            )
        )

    def test_two_exact_network_free_replays(self) -> None:
        before = datetime.now(UTC)
        with self._offline():
            manifest = v87.validate_open_seed_v87(
                DEFINITION,
                RELEASE,
                replay_count=2,
            )
        after = datetime.now(UTC)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertLessEqual(instant(RECORDED_AT), before)
        self.assertLessEqual(instant(RECORDED_AT), after)

    def test_future_and_semantic_collision_guards_fail_closed(self) -> None:
        base = json.loads(v87.BASE_DEFINITION.read_text(encoding="utf-8"))
        future = (datetime.now(UTC) + timedelta(hours=1)).replace(microsecond=0)
        with self.assertRaisesRegex(v87.OpenSeedV87Error, "publication time"):
            v87.selected_inputs(
                base,
                recorded_at=future.isoformat().replace("+00:00", "Z"),
                validation_wall_clock=datetime.now(UTC),
            )

        colliding = json.loads(json.dumps(base))
        colliding["curated_inputs"][-1] = {
            "path": v87.ADDITION_ORDER[0],
            "sha256": v87.ADDITION_PINS[v87.ADDITION_ORDER[0]][1],
        }
        with self.assertRaisesRegex(v87.OpenSeedV87Error, "collides"):
            v87.selected_inputs(
                colliding,
                recorded_at=RECORDED_AT,
                validation_wall_clock=datetime.now(UTC),
            )

    def test_existing_build_is_idempotent_and_network_free(self) -> None:
        with self._offline():
            result = v87.build_open_seed_v87()
        self.assertEqual(result["status"], "existing-identical")
        self.assertEqual(result["definition_sha256"], DEFINITION_PIN[1])
        self.assertEqual(result["release_tree_sha256"], RELEASE_TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
