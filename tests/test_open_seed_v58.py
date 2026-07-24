from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import copy
import csv
from datetime import datetime, timezone
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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v3 as release_v3
    from datacenter_atlas.datacenter_atlas import open_seed_v58 as v58
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v3 as release_v3
    from datacenter_atlas import open_seed_v58 as v58
from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v58.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v58"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v57.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v57"

DEFINITION_SHA256 = "76b9200c892c62a579007f7024a3802019c8b06ad34e0dbbd42e5529fb391a74"
MANIFEST_SHA256 = "52261833ac75e2153d4298352a517a0beecb4938f4098ca0f280da3cf367d83e"
TREE_SHA256 = "6534726c7011dcf3af9664f4bd796509a4535cfbca75d507aa3ffea2a227bc0f"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (3_728, "8e4bfbac4e3d1d9c614f51ba5749d50a02a3af3ee14fee17191456ae2e24c5ef"),
    "README.md": (2_625, "13547d4ab3cd7a7ed9e517a19fbc5577d77c6055d05f9dc210780fd56ab28ed5"),
    "atlas.geojson": (2_417_775, "d9a600c3356284d068a0254d9ffae36935e75c46862c5c9b002124650bd4f7ec"),
    "capacity_estimates.csv": (229_949, "38cc8737351a76733bb0f1e30ba7771c2994efaffb4007b50a0e208e99bebc9e"),
    "construction_pipeline.csv": (465_873, "92216f67dc71e29d62ed743f6dd4877546a18092d3a7a2424b00b2b45222bd59"),
    "construction_source_signals.csv": (287_531, "fc439604a24ccd847e27a114e190555dab4529ac853b677613ddcaacc2386d82"),
    "entities.csv": (752_565, "2e800c2bf51ce795d27097e3f331bef37ae1e8d6fb8d7ac40d2838e030f2199b"),
    "evidence.csv": (154_542, "afb8aae2116c7c5b6604c9cadbae6fe61dcefee09da31f6bfe605d4f922ef1d1"),
    "manifest.json": (9_678, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_011, "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897"),
    "resolution_candidates.json": (5_874, "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0"),
    "source_inputs.json": (234_599, "985ea795d2741901f6d231821c8bae8da81b9bc49a1f458d02e6136e6f00b841"),
    "summary.json": (2_923, "62aa6163a3ee3f02a675997b38339d7ed7f93c2244bc57cf3982ae424b6650c7"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


class OpenSeedV58Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v58-test-db-")
        selected_rows, paths = v58.selected_inputs(cls.base_definition)
        cls.selected_rows = selected_rows
        cls.connection = v58._build_database(
            cls.base_definition,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_bytes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 70_057)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v58.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            path = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(
            self.definition["scope"],
            {
                "commercial_census_parity_claimed": False,
                "epoch_selected_site_count_is_global_census": False,
                "orphan_timeline_imported": False,
                "source_scoped_estimates_only": True,
            },
        )
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                key: manifest[key]
                for key in (
                    "entities",
                    "evidence_records",
                    "capacity_estimates",
                    "construction_pipeline_records",
                    "construction_source_signals",
                    "resolution_candidates",
                )
            },
            {
                "entities": 685,
                "evidence_records": 400,
                "capacity_estimates": 486,
                "construction_pipeline_records": 357,
                "construction_source_signals": 263,
                "resolution_candidates": 4,
            },
        )
        self.assertEqual(len(manifest["source_families"]), 214)

    def test_exact_v57_adjacency_adds_only_the_seven_sources(self) -> None:
        before = {
            row["path"]: row["sha256"]
            for row in self.base_definition["curated_inputs"]
        }
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        self.assertEqual(len(before), 320)
        self.assertEqual(len(after), 327)
        self.assertEqual(set(before) - set(after), set())
        self.assertEqual(set(after) - set(before), set(v58.ADDITION_PINS))
        self.assertEqual({path: after[path] for path in before}, before)
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual([row["path"] for row in self.selected_rows], sorted(after))

    def test_exact_csv_delta_has_no_changed_or_removed_common_rows(self) -> None:
        v58._validate_release_delta(RELEASE)
        for filename, expected in v58.CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            self.assertEqual(sum(common.values()), expected[0], filename)
            self.assertEqual(sum((before - common).values()), 0, filename)
        self.assertEqual(
            (BASE_RELEASE / "resolution_candidates.json").read_bytes(),
            (RELEASE / "resolution_candidates.json").read_bytes(),
        )

    def test_added_entities_lifecycle_countries_and_capacity_are_exact(self) -> None:
        before = {row["stable_key"] for row in rows(BASE_RELEASE / "entities.csv")}
        added = [row for row in rows(RELEASE / "entities.csv") if row["stable_key"] not in before]
        self.assertEqual({row["stable_key"] for row in added}, v58.ADDED_ENTITY_KEYS)
        self.assertEqual(
            Counter(row["country"] for row in added),
            Counter(
                {
                    "Czechia": 2,
                    "Finland": 2,
                    "Germany": 2,
                    "India": 2,
                    "United States": 6,
                }
            ),
        )
        for row in added:
            self.assertEqual((row["latitude"], row["longitude"]), ("", ""))
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            if row["stable_key"] in v58.PROJECT_KEYS:
                self.assertEqual(row["status"], "under_construction")
            else:
                self.assertEqual(row["status"], "")

        entity_ids = {row["entity_id"]: row["stable_key"] for row in added}
        capacity = {
            entity_ids[row["entity_id"]]: (
                row["metric"],
                row["stage"],
                row["unit"],
                float(row["base"]),
                row["as_of_date"],
            )
            for row in rows(RELEASE / "capacity_estimates.csv")
            if row["entity_id"] in entity_ids
        }
        self.assertEqual(capacity, v58.CAPACITY_CONTRACT)
        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_by_metric"]["critical_it_mw"], 230)
        self.assertEqual(summary["capacity_estimates_by_stage"]["planned"], 123)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 258)
        self.assertEqual(summary["lifecycle_observations_current"], 392)
        self.assertEqual(summary["entities_with_coordinates"], 164)
        self.assertEqual(summary["campuses_with_coordinates"], 117)

    def test_all_ten_evidence_records_persist_but_only_nine_claims_publish(self) -> None:
        expected_new: dict[tuple[str, str], str] = {}
        for path in sorted(v58.ADDITION_PINS):
            document = json.loads((ROOT / path).read_text(encoding="utf-8"))
            for item in document["evidence"]:
                expected_new[(item["key"], item["content_hash"])] = item["retrieved_at"]
        self.assertEqual(len(expected_new), 10)
        stored = {
            (row["curated_key"], row["content_hash"]): row["retrieved_at"]
            for row in self.connection.execute(
                """
                SELECT content_hash, retrieved_at,
                       json_extract(metadata_json, '$.curated_record_key') AS curated_key
                FROM evidence
                WHERE json_extract(metadata_json, '$.curated_record_key') IS NOT NULL
                """
            )
            if (row["curated_key"], row["content_hash"]) in expected_new
        }
        self.assertEqual(stored, expected_new)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 480)

        published_hashes = {row["content_hash"] for row in rows(RELEASE / "evidence.csv")}
        new_hashes = {content_hash for _, content_hash in expected_new}
        self.assertEqual(len(published_hashes & new_hashes), 9)
        self.assertEqual(
            new_hashes - published_hashes,
            {"ddfd58615b4bd5598c39e0faa7556727463978ed45c8565f85244a9afe87e714"},
        )

    def test_mixed_schema_import_is_collision_safe_and_idempotent(self) -> None:
        versions = Counter()
        additions = []
        for row in self.definition["curated_inputs"]:
            path = ROOT / row["path"]
            document = json.loads(path.read_text(encoding="utf-8"))
            versions[document["schema_version"]] += 1
            if row["path"] in v58.ADDITIONS:
                additions.append((path, document))
        self.assertEqual(versions, Counter({"1.0": 322, "1.1": 5}))
        before = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "evidence",
                "entities",
                "lifecycle_observations",
                "capacity_estimates",
            )
        }
        for path, document in additions:
            timestamp = {item["retrieved_at"] for item in document["evidence"]}.pop()
            result = CuratedOfficialSourceAdapter().import_file(
                self.connection, path, retrieved_at=timestamp
            )
            self.assertEqual((result.entities_created, result.evidence_created), (0, 0))
        after = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        self.assertEqual(after, before)
        self.assertEqual(validate_database(self.connection), [])

    def test_v57_base_and_validator_are_pinned_and_untouched(self) -> None:
        before = (sha256(BASE_DEFINITION), v58.tree_digest(BASE_RELEASE))
        manifest = release_v3.validate_frozen_v57(ROOT)
        self.assertEqual(manifest["entities"], 671)
        self.assertEqual(before, (release_v3.V57_DEFINITION_SHA256, release_v3.V57_TREE_SHA256))
        self.assertEqual(sha256(ROOT / "datacenter_atlas/open_seed_v57.py"), "4388d88e5c837be7f804b33671e83f79d4337d32be52b6df8c9fe75742588109")
        self.assertEqual(sha256(ROOT / "datacenter_atlas/open_seed_release_v2.py"), "f7ab34fc805b1ee17ad37db6b7855ef9c7a04bdfc0018b3df9d58c37a37ea3f9")
        self.assertEqual(before, (sha256(BASE_DEFINITION), v58.tree_digest(BASE_RELEASE)))

    def test_v3_validator_double_rebuilds_offline_without_network(self) -> None:
        error = AssertionError("network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            wrapped = release_v3._rebuild_documents
            with patch.object(release_v3, "_rebuild_documents", wraps=wrapped) as rebuild:
                manifest = release_v3.validate_open_seed_release_v3(DEFINITION, RELEASE)
            self.assertEqual(rebuild.call_count, 2)
        self.assertEqual(manifest["evidence_records"], 400)

    def test_duplicate_canonical_future_and_selection_collisions_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            release_v3.v2._json_object(b'{"a": 1, "a": 2}\n', "probe", canonical=False)
        with self.assertRaisesRegex(ValueError, "not canonical"):
            release_v3.v2._json_object(b'{"b": 1, "a": 2}\n', "probe", canonical=True)
        future_source = {
            "schema_version": "1.0",
            "evidence": [{"retrieved_at": "2026-07-21T00:21:01Z"}],
        }
        with self.assertRaisesRegex(ValueError, "post-dates"):
            release_v3.v2._evidence_timestamps(
                future_source,
                cutoff=datetime(2026, 7, 21, 0, 21, tzinfo=timezone.utc),
                label="future-probe",
            )
        paths = [row["path"] for row in self.definition["curated_inputs"]]
        missing_addition = next(iter(v58.ADDITIONS))
        with self.assertRaisesRegex(ValueError, "all seven"):
            release_v3._validate_selection(
                [path for path in paths if path != missing_addition]
            )
        predecessor = next(iter(release_v3.v2.REPLACEMENTS))
        with self.assertRaisesRegex(ValueError, "never be selected together"):
            release_v3._validate_selection(sorted([*paths, predecessor]))

        collision = copy.deepcopy(self.base_definition)
        collision["curated_inputs"][-1] = {
            "path": next(iter(v58.ADDITION_PINS)),
            "sha256": next(iter(v58.ADDITION_PINS.values())),
        }
        with self.assertRaisesRegex(SystemExit, "already occurs"):
            v58.selected_inputs(collision)

    def test_release_tamper_and_repeat_build_are_rejected_without_mutation(self) -> None:
        before_definition = sha256(DEFINITION)
        before_tree = v58.tree_digest(RELEASE)
        with tempfile.TemporaryDirectory(dir=ROOT / ".staging") as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            summary = copied / "summary.json"
            summary.chmod(0o644)
            summary.write_bytes(summary.read_bytes() + b" ")
            with patch.object(release_v3, "validate_frozen_v57", return_value={}):
                with self.assertRaisesRegex(ValueError, "release file changed"):
                    release_v3.validate_open_seed_release_v3(
                        DEFINITION, copied, require_frozen=False
                    )
        completed = subprocess.run(
            [sys.executable, "scripts/build_open_seed_v58.py"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1"},
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("definition already exists", completed.stderr + completed.stdout)
        self.assertEqual(sha256(DEFINITION), before_definition)
        self.assertEqual(v58.tree_digest(RELEASE), before_tree)

    def test_both_package_layouts_import_the_v58_carriers(self) -> None:
        command = [
            sys.executable,
            "-c",
            (
                "from datacenter_atlas.open_seed_v58 import RECORDED_AT; "
                "from datacenter_atlas.open_seed_release_v3 import V57_TREE_SHA256; "
                "print(RECORDED_AT, V57_TREE_SHA256)"
            ),
        ]
        expected = f"{v58.RECORDED_AT} {release_v3.V57_TREE_SHA256}"
        for cwd in (ROOT, WORKSPACE):
            completed = subprocess.run(
                command,
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(completed.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
