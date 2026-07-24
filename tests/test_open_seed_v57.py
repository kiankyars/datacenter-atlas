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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v2 as release_v2
    from datacenter_atlas.datacenter_atlas import open_seed_v57 as v57
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v2 as release_v2
    from datacenter_atlas import open_seed_v57 as v57
from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_release import validate_open_seed_release
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v57.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v57"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"

DEFINITION_SHA256 = "421a8992616cea1e0b9779d47ed1f7052465cbf59c22c3d00b8a79d9463c1bc8"
MANIFEST_SHA256 = "37f33308466d3707e2bf9f5225bd3c3546dcb2539e7f537286dd8237728d6403"
TREE_SHA256 = "2651d54295954e4a791e0dbc44b9e2f6947f6b519473468bcec5277299f4c8fe"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (3_576, "c00fbe27c423efe54b8f23aafdb958cffedf5a94953f95a60b641e080cb09857"),
    "README.md": (2_625, "9f972e62672e18ce6cf866c23178e4427c7975f46b3e75d0e5b8912c5f82b26f"),
    "atlas.geojson": (2_375_109, "23921f0f8373925321d7d203402d2035a6768c82838d3fa1f8778ebb19111cd4"),
    "capacity_estimates.csv": (228_985, "66393d2cb27a5746c4f0aba2becf1e31b462e3a948c532e9c95c83039fddd5f2"),
    "construction_pipeline.csv": (460_241, "33be7d4e62478fb01027e3e4af7965b444eab5b82bd4bb22dac812750daaf078"),
    "construction_source_signals.csv": (280_294, "346610bf6f6ae29a147fc5a5a406793972a24fc472491fb1282f689db5bcd992"),
    "entities.csv": (742_136, "55939a7d7df66f982aafc033cdeac9d7510ccbe29f0abc9b69836f36d212b253"),
    "evidence.csv": (150_570, "acb4e21c8fc43bbe628f8066aa081faa9181ec12dc2556490a11433df4470500"),
    "manifest.json": (9_403, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_011, "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897"),
    "resolution_candidates.json": (5_874, "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0"),
    "source_inputs.json": (227_727, "c2c672708a440a96baa07d949156bc337c2d0b5c0d014727c021dff7989a70e6"),
    "summary.json": (2_905, "c252d51d9b20fc454347ef0fc2921f3b7279f3c88e1675f1fc2bb7803016cb59"),
}

COORDINATES = {
    "curated:nextdc-b2-brisbane": ("-27.4539022", "153.0332005", "454 St Pauls Terrace, Fortitude Valley QLD 4006"),
    "curated:nextdc-kl1-kuala-lumpur": ("3.0965132", "101.6241451", "1, Jln 51a/229, Seksyen 51a, Petaling Jaya, 46100 Selangor"),
    "curated:nextdc-m2-melbourne": ("-37.7080294", "144.8756939", "75 Sharps Road, Tullamarine VIC 3043"),
    "curated:nextdc-p1-perth": ("-31.8644016", "115.895935", "4 Millrose Drive, Malaga WA 6090"),
    "curated:nextdc-p2-perth": ("-31.9496948", "115.8685493", "11 Newcastle Street, Perth WA 6000"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


class OpenSeedV57Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v57-test-db-")
        selected_rows, paths = v57.selected_inputs(cls.base_definition)
        cls.selected_rows = selected_rows
        cls.connection = v57._build_database(
            cls.base_definition,
            paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_bytes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 68_443)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v57.tree_digest(RELEASE), TREE_SHA256)
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
            {key: manifest[key] for key in (
                "entities",
                "evidence_records",
                "capacity_estimates",
                "construction_pipeline_records",
                "construction_source_signals",
                "resolution_candidates",
            )},
            {
                "entities": 671,
                "evidence_records": 391,
                "capacity_estimates": 484,
                "construction_pipeline_records": 350,
                "construction_source_signals": 256,
                "resolution_candidates": 4,
            },
        )
        self.assertEqual(len(manifest["source_families"]), 206)

    def test_exact_v56_adjacency_has_five_replacements_and_two_additions(self) -> None:
        before = {row["path"]: row["sha256"] for row in self.base_definition["curated_inputs"]}
        after = {row["path"]: row["sha256"] for row in self.definition["curated_inputs"]}
        self.assertEqual(len(before), 318)
        self.assertEqual(len(after), 320)
        self.assertEqual(set(before) - set(after), set(v57.REPLACEMENTS))
        self.assertEqual(
            set(after) - set(before),
            set(v57.REPLACEMENTS.values()) | set(v57.ADDITION_PINS),
        )
        common = set(before) & set(after)
        self.assertEqual({path: after[path] for path in common}, {path: before[path] for path in common})
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual([row["path"] for row in self.selected_rows], sorted(after))
        for predecessor, successor in v57.REPLACEMENTS.items():
            self.assertNotIn(predecessor, after)
            self.assertIn(successor, after)

    def test_exact_csv_delta_and_semantically_unchanged_rows(self) -> None:
        v57._validate_release_delta(RELEASE)
        self.assertEqual(
            (BASE_RELEASE / "capacity_estimates.csv").read_bytes(),
            (RELEASE / "capacity_estimates.csv").read_bytes(),
        )
        self.assertEqual(
            (BASE_RELEASE / "resolution_candidates.csv").read_bytes(),
            (RELEASE / "resolution_candidates.csv").read_bytes(),
        )
        for filename, expected in v57.CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            self.assertEqual(sum(common.values()), expected[0], filename)

    def test_nextdc_projection_changes_only_explicit_snapshot_provenance(self) -> None:
        before = {row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")}
        after = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        expected_changed_fields = {
            "latitude",
            "longitude",
            "address",
            "geometry_json",
            "tags_json",
            "snapshot_as_of",
            "snapshot_evidence_id",
            "source_url",
            "source_retrieved_at",
        }
        for campus_key, (latitude, longitude, address) in COORDINATES.items():
            for stable_key in (campus_key, next(key for key in after if key.startswith(campus_key + ":"))):
                with self.subTest(stable_key=stable_key):
                    changed = {
                        field for field in after[stable_key] if after[stable_key][field] != before[stable_key][field]
                    }
                    self.assertEqual(changed, expected_changed_fields)
                    self.assertEqual(after[stable_key]["latitude"], latitude)
                    self.assertEqual(after[stable_key]["longitude"], longitude)
                    self.assertEqual(after[stable_key]["address"], address)
                    self.assertEqual(after[stable_key]["snapshot_as_of"], "2026-07-20")
                    self.assertEqual(after[stable_key]["source_url"], "https://www.nextdc.com/contact")
                    self.assertEqual(after[stable_key]["source_retrieved_at"], "2026-07-20T23:13:48Z")
                    self.assertEqual(after[stable_key]["status"], before[stable_key]["status"])
                    self.assertEqual(after[stable_key]["status_as_of"], before[stable_key]["status_as_of"])
                    self.assertEqual(after[stable_key]["status_evidence_id"], before[stable_key]["status_evidence_id"])
                    self.assertEqual(after[stable_key]["capacity_estimates_json"], before[stable_key]["capacity_estimates_json"])

    def test_google_and_aligned_are_narrow_historical_lifecycle_additions(self) -> None:
        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        expected = {
            "curated:google-bermuda-hundred-chesterfield-campus:current-development": (
                "under_construction",
                "2025-08-28",
            ),
            "curated:aligned-quantum-frederick-campus:iad06": ("shell", "2026-03-09"),
        }
        for stable_key, (status, as_of) in expected.items():
            row = entities[stable_key]
            self.assertEqual((row["status"], row["status_as_of"]), (status, as_of))
            self.assertEqual((row["latitude"], row["longitude"]), ("", ""))
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
        aligned_rows = [
            row for row in rows(RELEASE / "capacity_estimates.csv")
            if "Aligned" in row["name"] or "IAD-06" in row["name"]
        ]
        self.assertEqual(aligned_rows, [])

    def test_all_evidence_timestamps_persist_and_claim_export_is_narrower(self) -> None:
        before_inputs = {
            row["path"] for row in self.base_definition["curated_inputs"]
        }
        new_paths = [
            ROOT / row["path"]
            for row in self.definition["curated_inputs"]
            if row["path"] not in before_inputs
        ]
        base_evidence = set()
        for row in self.base_definition["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
            base_evidence.update(
                (item["key"], item["content_hash"]) for item in document["evidence"]
            )
        expected_new: dict[tuple[str, str], str] = {}
        for path in new_paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            for item in document["evidence"]:
                identity = (item["key"], item["content_hash"])
                if identity not in base_evidence:
                    expected_new[identity] = item["retrieved_at"]
        self.assertEqual(len(expected_new), 11)
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
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 470)

        published_hashes = {row["content_hash"] for row in rows(RELEASE / "evidence.csv")}
        new_hashes = {content_hash for _, content_hash in expected_new}
        self.assertEqual(
            published_hashes & new_hashes,
            {
                "73792fd9af539fcc5316f184d7f6ccb6ee00770069705995e04f1d2efa669cb0",
                "678f589c75b03989eeb9fd69566002b1eb6b29cef8f21b64604cfdbe674106ec",
                "31083a50a0fa93148f3189c3876a7d083220dc0b746ae4dcc43454b7b589336b",
            },
        )
        self.assertEqual(len(rows(RELEASE / "evidence.csv")), 391)
        self.assertEqual(len(new_hashes - published_hashes), 8)

    def test_mixed_schema_import_is_collision_safe_and_idempotent(self) -> None:
        versions = Counter()
        selected_paths = []
        for row in self.definition["curated_inputs"]:
            path = ROOT / row["path"]
            document = json.loads(path.read_text(encoding="utf-8"))
            versions[document["schema_version"]] += 1
            if row["path"] in set(v57.SUCCESSOR_PINS) | set(v57.ADDITION_PINS):
                selected_paths.append((path, document))
        self.assertEqual(versions, Counter({"1.0": 315, "1.1": 5}))
        before = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("evidence", "entities", "lifecycle_observations", "capacity_estimates")
        }
        for path, document in selected_paths:
            if document["schema_version"] == "1.0":
                timestamp = {item["retrieved_at"] for item in document["evidence"]}.pop()
                result = CuratedOfficialSourceAdapter().import_file(
                    self.connection, path, retrieved_at=timestamp
                )
            else:
                result = CuratedOfficialSourceAdapterV11().import_file(
                    self.connection, path, recorded_at=v57.RECORDED_AT
                )
            self.assertEqual((result.entities_created, result.evidence_created), (0, 0))
        after = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        self.assertEqual(after, before)
        self.assertEqual(validate_database(self.connection), [])

    def test_v11_persists_nonempty_operating_model_and_workload(self) -> None:
        source = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-digipower-columbiana-shell.json").read_text(
                encoding="utf-8"
            )
        )
        source["schema_version"] = "1.1"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.json"
            path.write_text(json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapterV11().import_file(
                    connection, path, recorded_at="2026-07-20T23:56:00Z"
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
                    1,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_persisted_shared_evidence_conflict_rolls_back_atomically(self) -> None:
        source = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-digipower-columbiana-shell.json").read_text(
                encoding="utf-8"
            )
        )
        source["schema_version"] = "1.1"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.json"
            first.write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                adapter = CuratedOfficialSourceAdapterV11()
                adapter.import_file(connection, first, recorded_at=v57.RECORDED_AT)
                before = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("evidence", "entities", "entity_snapshots")
                }
                conflict = copy.deepcopy(source)
                original = conflict["evidence"][0]
                unique = copy.deepcopy(original)
                unique["key"] += "-transaction-probe"
                unique["content_hash"] = "1" * 64
                collision = copy.deepcopy(original)
                collision["title"] += " conflicting persisted metadata"
                conflict["evidence"] = [unique, collision]
                second = root / "second.json"
                second.write_text(json.dumps(conflict, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "conflicts on persisted fields"):
                    adapter.import_file(connection, second, recorded_at=v57.RECORDED_AT)
                after = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in before
                }
                self.assertEqual(after, before)
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE content_hash = ?", ("1" * 64,)
                    ).fetchone()[0],
                    0,
                )
                self.assertFalse(connection.in_transaction)
            finally:
                connection.close()

    def test_legacy_v56_still_validates_with_pinned_adapter(self) -> None:
        manifest = validate_open_seed_release(BASE_DEFINITION, BASE_RELEASE)
        self.assertEqual(manifest["entities"], 667)
        self.assertEqual(sha256(ROOT / "datacenter_atlas/curated.py"), "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12")
        self.assertEqual(sha256(ROOT / "datacenter_atlas/open_seed_release.py"), "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab")

    def test_v2_validator_double_rebuilds_offline_without_network(self) -> None:
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
            wrapped = release_v2._rebuild_documents
            with patch.object(release_v2, "_rebuild_documents", wraps=wrapped) as rebuild:
                manifest = release_v2.validate_open_seed_release_v2(DEFINITION, RELEASE)
            self.assertEqual(rebuild.call_count, 2)
        self.assertEqual(manifest["evidence_records"], 391)

    def test_duplicate_canonical_future_and_double_selection_rejection(self) -> None:
        with self.assertRaisesRegex(release_v2.OpenSeedReleaseV2Error, "duplicate JSON key"):
            release_v2._json_object(b'{"a": 1, "a": 2}\n', "probe", canonical=False)
        with self.assertRaisesRegex(release_v2.OpenSeedReleaseV2Error, "not canonical"):
            release_v2._json_object(b'{"b": 1, "a": 2}\n', "probe", canonical=True)
        future_source = {
            "schema_version": "1.1",
            "evidence": [{"retrieved_at": "2026-07-20T23:56:01Z"}],
        }
        with self.assertRaisesRegex(release_v2.OpenSeedReleaseV2Error, "post-dates"):
            release_v2._evidence_timestamps(
                future_source,
                cutoff=datetime(2026, 7, 20, 23, 56, tzinfo=timezone.utc),
                label="future-probe",
            )
        paths = [row["path"] for row in self.definition["curated_inputs"]]
        predecessor, _ = next(iter(v57.REPLACEMENTS.items()))
        with self.assertRaisesRegex(release_v2.OpenSeedReleaseV2Error, "never be selected together"):
            release_v2._validate_selection(sorted([*paths, predecessor]))

    def test_release_tamper_and_repeat_build_are_rejected_without_mutation(self) -> None:
        before_definition = sha256(DEFINITION)
        before_tree = v57.tree_digest(RELEASE)
        with tempfile.TemporaryDirectory(dir=ROOT / ".staging") as temporary:
            copied = Path(temporary) / RELEASE.name
            shutil.copytree(RELEASE, copied)
            summary = copied / "summary.json"
            summary.chmod(0o644)
            summary.write_bytes(summary.read_bytes() + b" ")
            with patch.object(release_v2, "validate_frozen_v56", return_value={}):
                with self.assertRaisesRegex(release_v2.OpenSeedReleaseV2Error, "release file changed"):
                    release_v2.validate_open_seed_release_v2(
                        DEFINITION, copied, require_frozen=False
                    )
        completed = subprocess.run(
            [sys.executable, "scripts/build_open_seed_v57.py"],
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
        self.assertEqual(v57.tree_digest(RELEASE), before_tree)

    def test_both_package_layouts_import_the_v57_carriers(self) -> None:
        command = [
            sys.executable,
            "-c",
            (
                "from datacenter_atlas.open_seed_v57 import RECORDED_AT; "
                "from datacenter_atlas.open_seed_release_v2 import V56_TREE_SHA256; "
                "print(RECORDED_AT, V56_TREE_SHA256)"
            ),
        ]
        expected = f"{v57.RECORDED_AT} {release_v2.V56_TREE_SHA256}"
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
