from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import date
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
    from datacenter_atlas.datacenter_atlas import open_seed_release_v4 as release_v4
    from datacenter_atlas.datacenter_atlas import open_seed_v59 as v59
except ModuleNotFoundError:
    from datacenter_atlas import open_seed_release_v4 as release_v4
    from datacenter_atlas import open_seed_v59 as v59
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v58.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v58"

DEFINITION_SHA256 = "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
MANIFEST_SHA256 = "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
TREE_SHA256 = "53cb173fb0e07b8dba8f9bb974cc533b38ba006590583725baf122cb8ba8d636"
PURE_SHA256 = "38faffdec1c464f4e5870355b247bbf3af228888ad3429f647b01db216ac33f6"

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (4_226, "f948f82747177b4ad36723232d21780636f17aebae04fc21eb8d165646112411"),
    "README.md": (3_164, "0671bdc329144161759af7eb8d1bcfb718d519e4954c1f209767262895b7bea9"),
    "atlas.geojson": (2_486_143, "e449c9c4e9fcdcfd9bc3f1424a8f20b041a7ddfbdfd94f6ceb7aff68e4992d89"),
    "capacity_estimates.csv": (232_551, "dad96e700dc6ed6f401ade6569252be95b1462bbef2921c33e89019609a3e35c"),
    "construction_pipeline.csv": (470_471, "4c05a7e0356bc8842df88a0a808d0573005a58b6bd0258860ca07317add8078e"),
    "construction_source_signals.csv": (292_783, "063de1a2ef5de86160defdf300d6243ce22b9a342f8e787b943b943bc1b3a271"),
    "entities.csv": (775_061, "3e661f318e394e06992427c254729863ee1ba7f1ffd6c933b800e68a276fe353"),
    "evidence.csv": (163_751, "956b02d0982768241bbdc78487f500ec4237aea89744a983ca4bca538526b25e"),
    "lifecycle_freshness.csv": (119_281, "455520488aab8ff5578f16195298ab1db314bd39cb389780f25fb12f66f1dbf9"),
    "manifest.json": (10_441, MANIFEST_SHA256),
    "resolution_candidates.csv": (4_989, "abcf4d20ebba7a20dd70931efec7f1c168abeafa491ed779e0c773fc9fc48264"),
    "resolution_candidates.json": (7_384, "a3a33723cd8660148eba81ef0133d459cce1bb23b8dc80514aea663766ab08a7"),
    "source_inputs.json": (249_180, "e5a55622adffd6b4ab58d6a5ec188ebb3e94e69df1130afebf661e31bb34a818"),
    "summary.json": (3_001, "d98b1405759ae896146d7c870ade100d6bd35c3e9a85336e409a0c1acc1ab77c"),
}

NEW_SOURCE_FAMILIES = {
    "cook_county_official_address_points",
    "cuzk_ruian_parcels",
    "fairfax_county_parcels_wgs84_mapserver",
    "google_official_blog",
    "hessen_official_house_coordinates_wfs",
    "kazakhstan_prime_minister_official_news",
    "kio_public_company_linkedin_posts",
    "mantsala_official_map_service",
    "pse_edge_company_filing",
    "scala_certification_documents",
    "scala_data_center_portfolio_pages",
    "stt_gdc_data_center_location_pages",
    "wallonia_official_news",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


def source_identities(document: dict[str, object]) -> tuple[set[str], set[tuple[str, str]]]:
    campus = document["campus"]
    project = document.get("project")
    evidence = document["evidence"]
    assert isinstance(campus, dict)
    assert isinstance(evidence, list)
    stable_keys = {str(campus["stable_key"])}
    if project is not None:
        assert isinstance(project, dict)
        stable_keys.add(str(project["stable_key"]))
    return (
        stable_keys,
        {
            (str(item["key"]), str(item["content_hash"]))
            for item in evidence
            if isinstance(item, dict)
        },
    )


class OpenSeedV59Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        cls.definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        cls.temporary = tempfile.TemporaryDirectory(prefix="open-seed-v59-test-db-")
        cls.selected_rows, selected_paths = v59.selected_inputs(cls.base_definition)
        cls.connection = v59._build_database(
            cls.base_definition,
            selected_paths,
            Path(cls.temporary.name) / "atlas.sqlite",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary.cleanup()

    def test_frozen_hashes_bytes_modes_manifest_and_scope(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 73_276)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(v59.tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(set(RELEASE_FILE_PINS), {path.name for path in RELEASE.iterdir()})
        for filename, (size, digest) in RELEASE_FILE_PINS.items():
            output = RELEASE / filename
            with self.subTest(filename=filename):
                self.assertEqual(output.stat().st_size, size)
                self.assertEqual(sha256(output), digest)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o444)

        self.assertEqual(self.definition["release_id"], release_v4.RELEASE_ID)
        self.assertEqual(
            self.definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T03:00:00Z"},
        )
        self.assertEqual(self.definition["publication_contract_version"], 4)
        self.assertEqual(self.definition["freshness_contract"], v59.freshness_contract())
        self.assertFalse(
            self.definition["scope"]["commercial_census_parity_claimed"]
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
                    "lifecycle_freshness_records",
                    "lifecycle_status_semantics",
                    "current_status_inferred",
                )
            },
            {
                "entities": 699,
                "evidence_records": 418,
                "capacity_estimates": 491,
                "construction_pipeline_records": 362,
                "construction_source_signals": 268,
                "resolution_candidates": 5,
                "lifecycle_freshness_records": 399,
                "lifecycle_status_semantics": "last_observed",
                "current_status_inferred": False,
            },
        )
        base_manifest = json.loads(
            (BASE_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(len(manifest["source_families"]), 227)

    def test_exact_v58_adjacency_and_calendar_boundary(self) -> None:
        before = {
            row["path"]: row["sha256"]
            for row in self.base_definition["curated_inputs"]
        }
        after = {
            row["path"]: row["sha256"] for row in self.definition["curated_inputs"]
        }
        successors = {successor for successor, _ in release_v4.REPLACEMENT_PINS.values()}
        self.assertEqual((len(before), len(after)), (327, 334))
        self.assertEqual(set(before) - set(after), set(release_v4.REPLACEMENT_PINS))
        self.assertEqual(
            set(after) - set(before), successors | set(release_v4.ADDITION_PINS)
        )
        common = set(before) & set(after)
        self.assertEqual({key: after[key] for key in common}, {key: before[key] for key in common})
        self.assertEqual(self.definition["curated_inputs"], self.selected_rows)
        self.assertEqual([row["path"] for row in self.selected_rows], sorted(after))
        excluded = (
            release_v4.STALE_EXCLUSIONS
            | release_v4.HISTORICAL_EXCLUSIONS
            | release_v4.PENDING_NEXT_DAY_EXCLUSIONS
        )
        self.assertFalse(excluded & set(after))
        self.assertEqual(
            self.definition["epoch_capture"], self.base_definition["epoch_capture"]
        )
        self.assertEqual(
            self.definition["expected_epoch_result"],
            self.base_definition["expected_epoch_result"],
        )

        versions = Counter(
            json.loads((ROOT / item["path"]).read_text(encoding="utf-8"))[
                "schema_version"
            ]
            for item in self.selected_rows
        )
        self.assertEqual(versions, Counter({"1.0": 317, "1.1": 17}))

        pure_path = ROOT / next(iter(release_v4.PENDING_NEXT_DAY_EXCLUSIONS))
        pure = json.loads(pure_path.read_text(encoding="utf-8"))
        self.assertEqual(sha256(pure_path), PURE_SHA256)
        self.assertEqual(stat.S_IMODE(pure_path.stat().st_mode), 0o644)
        self.assertEqual(
            {pure["campus"]["as_of_date"], pure["project"]["as_of_date"]},
            {"2026-07-21"},
        )
        johor = json.loads(
            (ROOT / next(iter(release_v4.STALE_EXCLUSIONS))).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(johor["lifecycle"][0]["as_of_date"], "2025-02-24")
        self.assertEqual((date(2026, 7, 20) - date(2025, 2, 24)).days, 511)

    def test_exact_csv_delta_and_zero_epoch_churn(self) -> None:
        v59._validate_release_delta(RELEASE)
        for filename, expected in v59.CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            self.assertEqual(
                (
                    sum(common.values()),
                    sum((after - common).values()),
                    sum((before - common).values()),
                ),
                (expected[0], expected[1], expected[3]),
                filename,
            )
        before_entities = {
            row["stable_key"]: row for row in rows(BASE_RELEASE / "entities.csv")
        }
        after_entities = {
            row["stable_key"]: row for row in rows(RELEASE / "entities.csv")
        }
        changed = {
            key
            for key in before_entities.keys() & after_entities.keys()
            if before_entities[key] != after_entities[key]
        }
        self.assertEqual(changed, v59.COORDINATE_MUTATED_KEYS)
        self.assertFalse(any(key.startswith("epoch-ai:") for key in changed))
        self.assertEqual(
            set(after_entities) - set(before_entities), v59.ADDED_ENTITY_KEYS
        )

        before_candidates = row_counter(BASE_RELEASE / "resolution_candidates.csv")
        added = [
            dict(packed)
            for packed in (
                row_counter(RELEASE / "resolution_candidates.csv") - before_candidates
            ).elements()
        ]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["relationship_suggestion"], "nearby_only")
        self.assertEqual(added[0]["distance_m"], "4503.543")
        self.assertEqual(
            {added[0]["left_name"], added[0]["right_name"]},
            {
                "Menlo Digital MD-VA1 Herndon Data Center",
                "Penzance Chantilly Premier Data Center",
            },
        )

    def test_database_delta_is_typed_and_valid(self) -> None:
        self.assertEqual(validate_database(self.connection), [])
        v59._validate_database_delta(self.connection)
        placeholders = ",".join("?" for _ in v59.ADDED_ENTITY_KEYS)
        lifecycle = {
            tuple(row)
            for row in self.connection.execute(
                f"""
                SELECT entities.stable_key, lifecycle_observations.status,
                       lifecycle_observations.as_of_date
                FROM lifecycle_observations
                JOIN entities ON entities.id = lifecycle_observations.entity_id
                WHERE entities.stable_key IN ({placeholders})
                """,
                tuple(sorted(v59.ADDED_ENTITY_KEYS)),
            )
        }
        self.assertEqual(lifecycle, v59.LIFECYCLE_CONTRACT)
        capacity = {
            row[0]: tuple(row[1:])
            for row in self.connection.execute(
                f"""
                SELECT entities.stable_key, capacity_estimates.metric,
                       capacity_estimates.stage, capacity_estimates.unit,
                       capacity_estimates.base, capacity_estimates.as_of_date
                FROM capacity_estimates
                JOIN entities ON entities.id = capacity_estimates.entity_id
                WHERE entities.stable_key IN ({placeholders})
                """,
                tuple(sorted(v59.ADDED_ENTITY_KEYS)),
            )
        }
        self.assertEqual(capacity, v59.CAPACITY_CONTRACT)

    def test_lifecycle_freshness_is_explicitly_non_current(self) -> None:
        freshness = rows(RELEASE / "lifecycle_freshness.csv")
        self.assertEqual(len(freshness), 399)
        self.assertEqual(
            Counter(row["freshness_class"] for row in freshness),
            Counter(
                {
                    "recent_0_90_days": 208,
                    "aging_91_365_days": 171,
                    "stale_over_365_days": 20,
                }
            ),
        )
        as_of = date.fromisoformat("2026-07-20")
        for row in freshness:
            age = (as_of - date.fromisoformat(row["last_observed_status_as_of"])).days
            self.assertEqual(row["observation_age_days"], str(age))
            self.assertEqual(row["freshness_class"], v59._freshness_class(age))
            self.assertEqual(row["status_semantics"], "last_observed")
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertEqual(row["current_construction_claim"], "false")
        self.assertFalse(
            any(
                "stt-johor" in row["stable_key"]
                or "pure-dc-ams01" in row["stable_key"]
                for row in freshness
            )
        )
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("makes no current-construction inference", readme)
        self.assertIn("Pure AMS01 record is pending the next local release day", readme)

    def test_source_collisions_are_deliberate_and_bounded(self) -> None:
        base_stable: set[str] = set()
        base_evidence: set[tuple[str, str]] = set()
        for item in self.base_definition["curated_inputs"]:
            document = json.loads((ROOT / item["path"]).read_text(encoding="utf-8"))
            stable, evidence = source_identities(document)
            base_stable.update(stable)
            base_evidence.update(evidence)

        addition_hashes: Counter[str] = Counter()
        for source_path in release_v4.ADDITION_PINS:
            document = json.loads((ROOT / source_path).read_text(encoding="utf-8"))
            stable, evidence = source_identities(document)
            self.assertFalse(stable & base_stable, source_path)
            self.assertFalse(evidence & base_evidence, source_path)
            addition_hashes.update(content_hash for _, content_hash in evidence)
        self.assertEqual(
            {digest for digest, count in addition_hashes.items() if count > 1},
            {
                "e9168b8fc558894ec367e035d44eb01e3ef27d511f344bfe845017ecab514c51",
                "66da77b690b61e6606785ef604b20582d7d9f8de51b939cfd7fed2002656c5af",
            },
        )

        for predecessor, (successor, _) in release_v4.REPLACEMENT_PINS.items():
            before = json.loads((ROOT / predecessor).read_text(encoding="utf-8"))
            after = json.loads((ROOT / successor).read_text(encoding="utf-8"))
            stable_before, evidence_before = source_identities(before)
            stable_after, evidence_after = source_identities(after)
            self.assertEqual(stable_after, stable_before)
            self.assertTrue(evidence_before < evidence_after)

    def test_v58_is_pinned_and_validator_rebuilds_v59_twice_offline(self) -> None:
        before = (sha256(BASE_DEFINITION), v59.tree_digest(BASE_RELEASE))
        self.assertEqual(
            before,
            (release_v4.V58_DEFINITION_SHA256, release_v4.V58_TREE_SHA256),
        )
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
            wrapped = release_v4._rebuild_documents
            with patch.object(release_v4, "_rebuild_documents", wraps=wrapped) as rebuild:
                manifest = release_v4.validate_open_seed_release_v4(DEFINITION, RELEASE)
            self.assertEqual(rebuild.call_count, 2)
        self.assertEqual(manifest["entities"], 699)
        self.assertEqual(before, (sha256(BASE_DEFINITION), v59.tree_digest(BASE_RELEASE)))

    def test_tamper_repeat_build_and_both_import_layouts(self) -> None:
        before = (sha256(DEFINITION), v59.tree_digest(RELEASE))
        with tempfile.TemporaryDirectory(prefix="open-seed-v59-tamper-", dir="/private/tmp") as temporary:
            copied = Path(temporary) / f".{RELEASE.name}.tampered"
            shutil.copytree(RELEASE, copied)
            summary = copied / "summary.json"
            summary.chmod(0o644)
            summary.write_bytes(summary.read_bytes() + b" ")
            with patch.object(release_v4, "validate_frozen_v58", return_value={}):
                with self.assertRaisesRegex(ValueError, "release file changed"):
                    release_v4.validate_open_seed_release_v4(
                        DEFINITION, copied, require_frozen=False
                    )

        repeated = subprocess.run(
            [sys.executable, "scripts/build_open_seed_v59.py"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1"},
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("definition already exists", repeated.stderr + repeated.stdout)
        self.assertEqual(before, (sha256(DEFINITION), v59.tree_digest(RELEASE)))

        command = [
            sys.executable,
            "-c",
            (
                "from datacenter_atlas.open_seed_v59 import AS_OF; "
                "from datacenter_atlas.open_seed_release_v4 import RELEASE_ID; "
                "print(AS_OF, RELEASE_ID)"
            ),
        ]
        for working_directory in (ROOT, WORKSPACE):
            completed = subprocess.run(
                command,
                cwd=working_directory,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                text=True,
                capture_output=True,
                timeout=30,
                check=True,
            )
            self.assertEqual(
                completed.stdout.strip(), "2026-07-20 2026-07-20-open-seed-v59"
            )


if __name__ == "__main__":
    unittest.main()
