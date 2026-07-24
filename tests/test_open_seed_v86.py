from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import UTC, datetime, timedelta
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


core = importlib.import_module("datacenter_atlas.datacenter_atlas.open_seed_v86")
shim = importlib.import_module("datacenter_atlas.open_seed_v86")

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
BUILDER = ROOT / "scripts/build_open_seed_v86.py"
DRY_RUN_RECORDED_AT = "2026-07-21T20:20:00Z"

RECORDED_AT = "2026-07-21T20:19:16Z"
DEFINITION_PIN = (
    102_240,
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d",
)
MANIFEST_PIN = (
    15_531,
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488",
)
TREE_PIN = "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        7_617,
        "3373df0ee928b9fed31a0a56451622f5f8c3b84cc14a69cffd0159843eac723a",
    ),
    "README.md": (
        5_615,
        "e431231bc001ebf567a6671f6dcb4446798d5a47c811cf1d86da56a1883dd465",
    ),
    "atlas.geojson": (
        3_231_931,
        "9d6ce16e913fa888bddd3b25584871e51ebd67f3ea7f09c99874bf7a01057b19",
    ),
    "capacity_estimates.csv": (
        265_446,
        "372f2c993da99b2dc5c672137ce7abc637e0708246624db48614ec05d41e5066",
    ),
    "construction_pipeline.csv": (
        580_273,
        "bdb1196b1845bea465f3e1104dd26a7d909e5766f352d2915da6abdf0c798199",
    ),
    "construction_source_signals.csv": (
        394_777,
        "d479d777460d54c29af7052c0037275ceabc6e8ae593435a96f26d67a4059ae2",
    ),
    "entities.csv": (
        978_587,
        "a32bca2890df0d6434024c451c93a23dd8f67169f6e81b8cf2bb22f0d9172b93",
    ),
    "evidence.csv": (
        240_378,
        "2cfbae5b2b9c24c91e95b421be44bfe789070dc0917e88f68712083aa7e8a6d7",
    ),
    "lifecycle_freshness.csv": (
        155_231,
        "5563137c1c57e92377cbc0a28f8ff586d19b84a794179dec31769cf44cc56be2",
    ),
    "manifest.json": MANIFEST_PIN,
    "resolution_candidates.csv": (
        8_749,
        "ac5b26629b02892e8f5a950221a2f0fcffcb848f40cfc47ae3ae6fb4da14e0cc",
    ),
    "resolution_candidates.json": (
        13_272,
        "a5d26da56b133ffe32f7b6f9d57f123af7bb3f647636301e678036fcb029e87d",
    ),
    "source_inputs.json": (
        386_499,
        "8f814534419f641886a81fad6f31437a30e495f15bb2eb1d9c1b99f95a6cb70a",
    ),
    "summary.json": (
        3_446,
        "c4411cd0cb6e1d2d80c8ef0fa3f52444ae71dccbd0bc8a4ec461f6abe797aeb0",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV86Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = json.loads(core.BASE_DEFINITION.read_text())
        cls.selected, paths = core.selected_inputs(
            cls.base,
            recorded_at=DRY_RUN_RECORDED_AT,
            validation_wall_clock=datetime.fromisoformat(
                DRY_RUN_RECORDED_AT.replace("Z", "+00:00")
            ),
        )
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v86-test-")
        root = Path(cls.temporary.name)
        cls.connection = core._build_database(
            cls.base,
            paths,
            root / "atlas.sqlite",
            recorded_at=DRY_RUN_RECORDED_AT,
        )
        cls.release = root / "release"
        core._write_release(
            cls.connection,
            cls.release,
            recorded_at=DRY_RUN_RECORDED_AT,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("open seed v86 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_exact_v85_prefix_and_five_source_append(self) -> None:
        before = self.base["curated_inputs"]
        after = self.selected
        self.assertEqual(len(before), 447)
        self.assertEqual(len(after), 452)
        self.assertEqual(after[:447], before)
        self.assertEqual(
            [row["path"] for row in after[447:]], list(core.ADDITION_ORDER)
        )
        self.assertEqual(
            [row["sha256"] for row in after[447:]],
            [core.ADDITION_PINS[path][1] for path in core.ADDITION_ORDER],
        )
        for index, expected in core.PROTECTED_INDEX_PINS.items():
            self.assertEqual(
                (after[index]["path"], after[index]["sha256"]), expected
            )

    def test_artifact_contract_and_prior_review_resolution(self) -> None:
        with self._network_guard():
            documents = core._validate_official_artifact()
        self.assertEqual(tuple(documents), core.ADDITION_ORDER)
        snapshot = json.loads(
            (core.OFFICIAL_ARTIFACT / "source-snapshot.json").read_text()
        )
        self.assertEqual(
            snapshot["prior_review_only_resolution"],
            {
                "artifact_id": "global-official-builds-next-tranche-2026-07-21-v1",
                "candidate_id": "odata-sp04-phase-2",
                "prior_decision": "review_only_uncaptured_official_linkedin",
                "prior_artifact_mutated": False,
                "resolution": (
                    "credential_free_public_embed_body_captured_and_hash_bound"
                ),
            },
        )

    def test_database_is_append_only_with_exact_claim_boundary(self) -> None:
        expected_counts = {
            "entities": 927,
            "entity_snapshots": 948,
            "evidence": 763,
            "lifecycle_observations": 537,
            "capacity_estimates": 553,
            "operating_model_observations": 71,
            "workload_observations": 135,
        }
        self.assertEqual(
            {
                table: self.connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in expected_counts
            },
            expected_counts,
        )
        rows = {
            row["stable_key"]: row
            for row in self.connection.execute(
                """
                SELECT entities.stable_key, entities.id, latitude, longitude,
                       geometry_json
                FROM entity_snapshots
                JOIN entities ON entities.id = entity_id
                WHERE entities.stable_key IN ({})
                """.format(",".join("?" for _ in core.ADDED_ENTITY_KEYS)),
                tuple(sorted(core.ADDED_ENTITY_KEYS)),
            )
        }
        self.assertEqual(set(rows), core.ADDED_ENTITY_KEYS)
        for stable_key, row in rows.items():
            self.assertEqual(row["id"], core.ENTITY_IDS[stable_key])
            self.assertIsNone(row["latitude"])
            self.assertIsNone(row["longitude"])
            self.assertIn(row["geometry_json"], {None, "null"})

        evidence = {
            json.loads(row["metadata_json"] or "{}").get("curated_record_key")
            for row in self.connection.execute("SELECT metadata_json FROM evidence")
        }
        self.assertTrue(core.ADDED_EVIDENCE_KEYS <= evidence)
        self.assertEqual(len(core.ADDED_EVIDENCE_KEYS), 9)

    def test_public_projection_has_only_two_normalized_capacities(self) -> None:
        with self._network_guard():
            core._validate_release_delta(
                self.release, recorded_at=DRY_RUN_RECORDED_AT
            )
            core._validate_release_facts(
                self.release, recorded_at=DRY_RUN_RECORDED_AT
            )
        added_entities = {
            row["stable_key"]: row
            for row in csv_rows(self.release / "entities.csv")
            if row["stable_key"] in core.ADDED_ENTITY_KEYS
        }
        capacities = [
            row
            for row in csv_rows(self.release / "capacity_estimates.csv")
            if row["entity_id"] in set(core.ENTITY_IDS.values())
        ]
        self.assertEqual(len(added_entities), 10)
        self.assertEqual(len(capacities), 2)
        self.assertEqual(
            {
                (
                    next(
                        key
                        for key, entity_id in core.ENTITY_IDS.items()
                        if entity_id == row["entity_id"]
                    ),
                    row["metric"],
                    row["stage"],
                    row["unit"],
                    float(row["base"]),
                )
                for row in capacities
            },
            {
                (
                    "curated:odata-dc-sp04-osasco-campus",
                    "critical_it_mw",
                    "design",
                    "MW",
                    48.0,
                ),
                (
                    "curated:multidc-shoham-campus",
                    "critical_it_mw",
                    "design",
                    "MW",
                    30.0,
                ),
            },
        )
        for row in added_entities.values():
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(json.loads(row["workloads_json"]), [])

    def test_nine_database_evidence_rows_close_to_eight_public_rows(self) -> None:
        before = {
            row["evidence_id"]
            for row in csv_rows(core.BASE_RELEASE / "evidence.csv")
        }
        added = [
            row
            for row in csv_rows(self.release / "evidence.csv")
            if row["evidence_id"] not in before
        ]
        sources = json.loads((self.release / "source_inputs.json").read_text())[
            "sources"
        ]
        base_sources = json.loads(
            (core.BASE_RELEASE / "source_inputs.json").read_text()
        )["sources"]
        base_serialized = {
            json.dumps(row, sort_keys=True, ensure_ascii=False)
            for row in base_sources
        }
        added_sources = [
            row
            for row in sources
            if json.dumps(row, sort_keys=True, ensure_ascii=False)
            not in base_serialized
        ]
        self.assertEqual(len(added), 8)
        self.assertEqual(len(added_sources), 8)
        self.assertEqual(
            Counter(row["source_family"] for row in added),
            Counter(core.ALL_ADDITION_SOURCE_FAMILIES),
        )
        public_keys = {
            row["provenance"]["curated_record_key"] for row in added_sources
        }
        self.assertEqual(public_keys, core.PUBLIC_ADDED_EVIDENCE_KEYS)
        self.assertNotIn(core.OMITTED_PUBLIC_EVIDENCE_KEY, public_keys)

    def test_v85_geometry_resolution_and_coordinate_curation_are_unchanged(self) -> None:
        for filename in (
            "resolution_candidates.csv",
            "resolution_candidates.json",
        ):
            self.assertEqual(
                (self.release / filename).read_bytes(),
                (core.BASE_RELEASE / filename).read_bytes(),
            )
        entities = {
            row["stable_key"]: row for row in csv_rows(self.release / "entities.csv")
        }
        for stable_key in core.v85.ATH04_KEYS:
            self.assertEqual(entities[stable_key]["latitude"], "")
            self.assertEqual(entities[stable_key]["longitude"], "")
        atlas = json.loads((self.release / "atlas.geojson").read_text())
        geometry = Counter(
            feature["geometry"]["type"]
            for feature in atlas["features"]
            if feature["geometry"] is not None
        )
        self.assertEqual(
            geometry, {"Point": 133, "Polygon": 81, "MultiPolygon": 1}
        )
        summary = json.loads((self.release / "summary.json").read_text())
        manifest = json.loads((self.release / "manifest.json").read_text())
        self.assertEqual(summary["entities_with_coordinates"], 213)
        self.assertEqual(summary["campuses_with_coordinates"], 141)
        self.assertEqual(manifest["resolution_candidates"], 9)
        self.assertIs(manifest["geometry_only_representative_point_inferred"], False)

    def test_freshness_and_manifest_exact_counts(self) -> None:
        manifest = json.loads((self.release / "manifest.json").read_text())
        freshness = csv_rows(self.release / core.FRESHNESS_FILENAME)
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "entities",
                    "evidence_records",
                    "capacity_estimates",
                    "construction_pipeline_records",
                    "construction_source_signals",
                    "lifecycle_freshness_records",
                    "resolution_candidates",
                )
            },
            {
                "entities": 927,
                "evidence_records": 611,
                "capacity_estimates": 552,
                "construction_pipeline_records": 469,
                "construction_source_signals": 371,
                "lifecycle_freshness_records": 517,
                "resolution_candidates": 9,
            },
        )
        self.assertEqual(len(manifest["source_families"]), 366)
        self.assertEqual(len(freshness), 517)
        self.assertEqual(
            Counter(row["freshness_class"] for row in freshness),
            {
                "recent_0_90_days": 270,
                "aging_91_365_days": 214,
                "stale_over_365_days": 33,
            },
        )
        current = {
            row["stable_key"]: (
                row["last_observed_status"],
                row["last_observed_status_as_of"],
                row["freshness_class"],
                row["observation_age_days"],
            )
            for row in freshness
            if row["stable_key"] in core.ADDED_PROJECT_KEYS
        }
        self.assertEqual(current, core.FRESHNESS_CONTRACT)
        self.assertTrue(
            all(
                row["status_semantics"] == "last_observed"
                and row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] == "false"
                for row in freshness
            )
        )

    def test_future_binding_and_exact_two_replay_guard(self) -> None:
        with self.assertRaisesRegex(core.OpenSeedV86Error, "precedes an input"):
            core.selected_inputs(
                self.base,
                recorded_at="2026-07-21T19:50:52Z",
                validation_wall_clock=datetime.fromisoformat(
                    "2026-07-21T19:50:52+00:00"
                ),
            )
        with self.assertRaisesRegex(core.OpenSeedV86Error, "exactly two"):
            core.validate_open_seed_v86(replay_count=1)
        weakened = json.loads(DEFINITION.read_text())
        weakened["expected_summary"] = {}
        with self.assertRaisesRegex(core.OpenSeedV86Error, "expected-summary"):
            core._validate_definition(
                weakened,
                self.base,
                validation_wall_clock=datetime.now(UTC),
            )

    def test_partial_collision_and_definition_collision_rollback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v86-partial-") as temporary:
            root = Path(temporary)
            definition = root / core.DEFINITION.name
            release = root / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            definition.write_text("collision\n")
            with (
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                self.assertRaisesRegex(core.OpenSeedV86Error, "partial"),
            ):
                core.build_open_seed_v86()

        with tempfile.TemporaryDirectory(prefix="open-seed-v86-collision-") as temporary:
            root = Path(temporary)
            sources = root / "sources"
            releases = root / "releases"
            sources.mkdir()
            releases.mkdir()
            definition = sources / core.DEFINITION.name
            release = releases / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            original_promote = core.v69.promote_noreplace

            def collide_on_definition(source: Path, destination: Path) -> None:
                if Path(destination) == definition:
                    raise FileExistsError("injected v86 definition collision")
                original_promote(source, destination)

            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
            target_text = target.isoformat(timespec="seconds").replace("+00:00", "Z")
            with (
                self._network_guard(),
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                patch.object(core, "_wait_until", return_value=None),
                patch.object(
                    core.v69,
                    "promote_noreplace",
                    side_effect=collide_on_definition,
                ),
            ):
                with self.assertRaisesRegex(FileExistsError, "injected"):
                    core.build_open_seed_v86(recorded_at=target_text)
            self.assertFalse(definition.exists())
            self.assertFalse(release.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(sources.iterdir()), [])
            self.assertEqual(list(releases.iterdir()), [])

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v86-post-validation-"
        ) as temporary:
            root = Path(temporary)
            sources = root / "sources"
            releases = root / "releases"
            sources.mkdir()
            releases.mkdir()
            definition = sources / core.DEFINITION.name
            release = releases / core.RELEASE.name
            lock = root / core.PUBLICATION_LOCK.name
            target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
            target_text = target.isoformat(timespec="seconds").replace("+00:00", "Z")
            injected = core.OpenSeedV86Error(
                "injected post-promotion validation failure"
            )
            with (
                self._network_guard(),
                patch.object(core, "DEFINITION", definition),
                patch.object(core, "RELEASE", release),
                patch.object(core, "PUBLICATION_LOCK", lock),
                patch.object(core, "_wait_until", return_value=None),
                patch.object(core, "validate_open_seed_v86", side_effect=injected),
            ):
                with self.assertRaisesRegex(
                    core.OpenSeedV86Error, "post-promotion"
                ):
                    core.build_open_seed_v86(recorded_at=target_text)
            self.assertFalse(definition.exists())
            self.assertFalse(release.exists())
            self.assertFalse(lock.exists())
            self.assertEqual(list(sources.iterdir()), [])
            self.assertEqual(list(releases.iterdir()), [])

    def test_frozen_publication_or_clean_prepublication_state(self) -> None:
        present = (DEFINITION.exists(), RELEASE.exists())
        self.assertNotIn(present, {(True, False), (False, True)})
        if present == (False, False):
            return
        self.assertIsNotNone(RECORDED_AT)
        self.assertIsNotNone(DEFINITION_PIN)
        self.assertIsNotNone(MANIFEST_PIN)
        self.assertIsNotNone(TREE_PIN)
        self.assertTrue(RELEASE_FILE_PINS)
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(
            (
                (RELEASE / "manifest.json").stat().st_size,
                sha256(RELEASE / "manifest.json"),
            ),
            MANIFEST_PIN,
        )
        self.assertEqual(core.v69.tree_digest(RELEASE), TREE_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(
            set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()}
        )
        for filename, expected in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual((path.stat().st_size, sha256(path)), expected)
        with self._network_guard():
            manifest = shim.validate_open_seed_v86(DEFINITION, RELEASE)
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")


if __name__ == "__main__":
    unittest.main()
