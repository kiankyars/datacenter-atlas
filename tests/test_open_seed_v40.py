from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v40.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v40"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v39.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v39"

DEFINITION_SHA256 = "5e4d8b3f6c507dcd515f5bd92facddb5b4bbb350fe3a0851fc5b08285c5897ff"
MANIFEST_SHA256 = "1b34fedfcef6c564aa17d20efefced3669b648c150f3dca74a3ecba78f341bc5"
BASE_DEFINITION_SHA256 = (
    "2b0b219e94e98782f58128ea7db9c9b954e44d0694f33cc17e7807a71e6ef381"
)
BASE_MANIFEST_SHA256 = (
    "e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84"
)
BASE_TEST_SHA256 = (
    "19bbb8875cec5645b5dbc240213450dbe0366f61f964e5fc871beb9cd51f940c"
)
TRANCHE_TEST_SHA256 = (
    "cdae2a0add4677b8f1edfe04e5a30389b1029f5cfafe9a2ef6bcdc259aac8c48"
)
RELEASE_CODE_SHA256 = (
    "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056"
)
RELEASE_TEST_SHA256 = (
    "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243"
)
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-20T03:10:00Z"

SOURCE_HASHES = {
    "sources/curated-official-2026-07-20-cirion-lim2-lurin.json": (
        "c1d9b3c63f5fc974f672ed2477d7fd828376dcb63a217da59b765ca182018dc4"
    ),
    "sources/curated-official-2026-07-20-cirion-san2-quilicura.json": (
        "2e4360de4e5188678205d1aa1612141fda3728788b77e981253ace41c56dec60"
    ),
    "sources/curated-official-2026-07-20-stc-bahrain-dc.json": (
        "f67bc593369e9fbdcf994f8238ab1c6291ba64408563590c10064437c6784273"
    ),
    "sources/curated-official-2026-07-20-stc-ddc306-dammam.json": (
        "d9f02994c2199642d630fe709df548041e8a6c9706b25b63d617ed0247c9f66b"
    ),
    "sources/curated-official-2026-07-20-stc-ruh-new-mursalat.json": (
        "0d8d7693cc5abf676837363ad4d2b5282c5bde58bc0356054c7d13c3150ea4c2"
    ),
}

LIM2_CAMPUS = "curated:cirion-lim2-lurin-data-center"
SAN2_CAMPUS = "curated:cirion-san2-quilicura-data-center"
STC_BAHRAIN_CAMPUS = "curated:stc-bahrain-data-center"
STC_DAMMAM_CAMPUS = "curated:stc-ddc306-dammam-data-center"
STC_MURSALAT_CAMPUS = "curated:stc-ruh-new-mursalat-data-center"
CAMPUS_KEYS = {
    LIM2_CAMPUS,
    SAN2_CAMPUS,
    STC_BAHRAIN_CAMPUS,
    STC_DAMMAM_CAMPUS,
    STC_MURSALAT_CAMPUS,
}
PROJECT_DATES = {
    LIM2_CAMPUS + ":facility-build": "2025-06-17",
    SAN2_CAMPUS + ":facility-build": "2025-07-22",
    STC_BAHRAIN_CAMPUS + ":facility-build": "2024-12-31",
    STC_DAMMAM_CAMPUS + ":facility-build": "2024-12-31",
    STC_MURSALAT_CAMPUS + ":facility-build": "2024-12-31",
}
SNAPSHOT_DATES = {
    **PROJECT_DATES,
    LIM2_CAMPUS: "2025-06-17",
    SAN2_CAMPUS: "2025-07-22",
    STC_BAHRAIN_CAMPUS: "2024-12-31",
    STC_DAMMAM_CAMPUS: "2024-12-31",
    STC_MURSALAT_CAMPUS: "2024-12-31",
}
ENTITY_KEYS = CAMPUS_KEYS | set(PROJECT_DATES)
CIRION_KEYS = {
    key for key in ENTITY_KEYS if key.startswith("curated:cirion-")
}
STC_KEYS = ENTITY_KEYS - CIRION_KEYS

EVIDENCE_HASHES = {
    "85ab1a0ed34b0ff890f916f46f011b79a36739e21f15d3c8dfcd6c439f328c8e",
    "81407ef02c305a2ea82ff035fc60a24efc111f2b49e4515978a133b5c6fab4b6",
    "9fd63f9e2e1a2ac3f6d2984504f2e37d93de709dc3578bca58a17e974c3c0b2e",
}
NEW_SOURCE_FAMILIES = {
    "cirion_company_blog",
    "cirion_pressroom",
    "stc_sustainability_reports",
}
CSV_COUNTS = {
    "entities.csv": (411, 421),
    "evidence.csv": (253, 256),
    "capacity_estimates.csv": (418, 418),
    "construction_pipeline.csv": (215, 220),
    "construction_source_signals.csv": (179, 182),
    "resolution_candidates.csv": (4, 4),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def by_id(path: Path, field: str) -> dict[str, dict[str, str]]:
    source_rows = rows(path)
    result = {row[field]: row for row in source_rows}
    if len(result) != len(source_rows):
        raise AssertionError(f"duplicate {field} in {path}")
    return result


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


class OpenSeedV40Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v40 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=network_error))
            return validate_open_seed_release(DEFINITION, RELEASE)

    def test_release_rebuilds_twice_offline_with_v3_byte_identity(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "datacenter_atlas" / "release.py").read_bytes()).hexdigest(),
            RELEASE_CODE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_release.py").read_bytes()).hexdigest(),
            RELEASE_TEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)

        entries = list(RELEASE.iterdir())
        self.assertEqual(len(entries), 13)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in entries))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries))
        frozen = {path.name: path.read_bytes() for path in entries}
        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["as_of"], AS_OF)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 421)
        self.assertEqual(first["entities_by_kind"], {"campus": 240, "project": 181})
        self.assertEqual(first["evidence_records"], 256)
        self.assertEqual(first["capacity_estimates"], 418)
        self.assertEqual(first["construction_pipeline_records"], 220)
        self.assertEqual(first["construction_source_signals"], 182)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exact_v39_plus_five_accepted_sources(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_open_seed_v39.py").read_bytes()).hexdigest(),
            BASE_TEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (
                    ROOT
                    / "tests"
                    / "test_curated_stc_cirion_underrepresented_20260720.py"
                ).read_bytes()
            ).hexdigest(),
            TRANCHE_TEST_SHA256,
        )

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_pins = {record["path"]: record["sha256"] for record in base["curated_inputs"]}
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        self.assertEqual(len(base_pins), 179)
        self.assertEqual(len(current_pins), 184)
        self.assertEqual(set(current_pins) - set(base_pins), set(SOURCE_HASHES))
        self.assertEqual(set(base_pins) - set(current_pins), set())
        self.assertEqual(
            {path: current_pins[path] for path in SOURCE_HASHES}, SOURCE_HASHES
        )
        ordered_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered_paths, sorted(ordered_paths))
        self.assertEqual(len(ordered_paths), len(set(ordered_paths)))
        self.assertEqual(base["publication_contract_version"], 3)
        self.assertEqual(current["publication_contract_version"], 3)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v40")
        self.assertEqual(current["build"], {"as_of": AS_OF, "recorded_at": RECORDED_AT})
        for key in set(base) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], base[key], key)

        equinix_v40_sources = {
            path
            for path in current_pins
            if path.startswith("sources/curated-official-2026-07-20-equinix-")
        }
        self.assertEqual(
            equinix_v40_sources,
            {
                path
                for path in base_pins
                if path.startswith("sources/curated-official-2026-07-20-equinix-")
            },
        )

        for relative, digest in SOURCE_HASHES.items():
            path = ROOT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_all_v39_rows_survive_and_delta_is_exact(self) -> None:
        for filename, (base_count, current_count) in CSV_COUNTS.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            self.assertEqual(sum(before.values()), base_count, filename)
            self.assertEqual(sum(after.values()), current_count, filename)
            self.assertEqual(before & after, before, filename)
            self.assertEqual(
                sum((after - before).values()), current_count - base_count, filename
            )

        for filename in (
            "capacity_estimates.csv",
            "resolution_candidates.csv",
            "resolution_candidates.json",
        ):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
                filename,
            )

        base_entities = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        added_entities = [
            current_entities[key] for key in set(current_entities) - set(base_entities)
        ]
        self.assertEqual({row["stable_key"] for row in added_entities}, ENTITY_KEYS)

        base_evidence = by_id(BASE_RELEASE / "evidence.csv", "evidence_id")
        current_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        added_evidence = [
            current_evidence[key] for key in set(current_evidence) - set(base_evidence)
        ]
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_HASHES)

    def test_added_rows_are_historical_role_bounded_and_non_inferential(self) -> None:
        base_entities = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        added = [
            current_entities[key] for key in set(current_entities) - set(base_entities)
        ]
        by_key = {row["stable_key"]: row for row in added}
        self.assertEqual(set(by_key), ENTITY_KEYS)

        for stable_key, row in by_key.items():
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["tenants"], "")
            self.assertEqual(row["customers"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            tags = json.loads(row["tags_json"])
            role_tags = {key: value for key, value in tags.items() if key.startswith("role:")}
            self.assertEqual(
                role_tags,
                {"role:developer": "Cirion Technologies"}
                if stable_key in CIRION_KEYS
                else {},
            )
            if stable_key in PROJECT_DATES:
                self.assertEqual(row["status"], "under_construction")
                self.assertEqual(row["status_as_of"], PROJECT_DATES[stable_key])
                self.assertEqual(
                    row["status_method"], "authoritative_physical_status_update"
                )
                self.assertNotEqual(row["status_as_of"], AS_OF)
            else:
                self.assertEqual(row["status"], "")
                self.assertEqual(row["status_as_of"], "")
            self.assertEqual(row["snapshot_as_of"], SNAPSHOT_DATES[stable_key])

        released_identity_text = json.dumps(
            [
                {
                    key: row[key]
                    for key in ("stable_key", "name", "country", "address")
                }
                for row in added
            ]
        )
        self.assertNotIn("Jeddah", released_identity_text)

        documents = {
            relative: json.loads((ROOT / relative).read_text(encoding="utf-8"))
            for relative in SOURCE_HASHES
        }
        for relative, document in documents.items():
            is_cirion = "cirion-" in relative
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(
                    entity["roles"],
                    {"developer": ["Cirion Technologies"]} if is_cirion else {},
                )
                self.assertNotEqual(entity["as_of_date"], AS_OF)
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["operating_models"], [])
            metadata = document["evidence"][0]["metadata"]
            self.assertIn("historical", metadata["historical_status_guardrail"].lower())

        lim2 = documents[
            "sources/curated-official-2026-07-20-cirion-lim2-lurin.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(lim2["reported_untyped_power_mw"], 20)
        self.assertIn("remains untyped evidence metadata", lim2["capacity_guardrail"])
        self.assertIn("does not establish current status", lim2["historical_status_guardrail"])

        san2 = documents[
            "sources/curated-official-2026-07-20-cirion-san2-quilicura.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(san2["physical_progress_percent_as_reported"], 85)
        self.assertIn("not converted into a finer lifecycle stage", san2["status_scope"])
        self.assertIn("status after that date", san2["historical_status_guardrail"])

        stc_documents = [
            document for relative, document in documents.items() if "stc-" in relative
        ]
        for document in stc_documents:
            metadata = document["evidence"][0]["metadata"]
            self.assertEqual(
                metadata["portfolio_capacity_as_reported"],
                {
                    "phase_4_total_it_shell_capacity_mw": 20,
                    "phase_4_initial_day_1_it_load_mw": 10.8,
                    "year_end_total_it_capacity_mw": 125,
                    "year_end_live_active_capacity_mw": 92,
                },
            )
            self.assertIn("cannot be allocated", metadata["capacity_guardrail"])
            self.assertIn("None creates", metadata["capacity_guardrail"])
            self.assertIn("Riyadh, Jeddah, and Bahrain", metadata["internal_inconsistency_guardrail"])
            self.assertIn(
                "Dammam, Bahrain, and RUH - New Mursalat",
                metadata["internal_inconsistency_guardrail"],
            )
            self.assertIn("creates no Jeddah record", metadata["internal_inconsistency_guardrail"])
            self.assertEqual(
                metadata["under_construction_projects_as_reported"],
                ["Dammam DDC306", "Bahrain DC", "RUH - New Mursalat"],
            )

    def test_v3_summary_signals_and_claim_boundaries_remain_explicit(self) -> None:
        for filename in ("entities.csv", "construction_pipeline.csv"):
            with (RELEASE / filename).open(newline="", encoding="utf-8") as stream:
                fieldnames = csv.DictReader(stream).fieldnames
            assert fieldnames is not None
            self.assertEqual(
                fieldnames[fieldnames.index("users") : fieldnames.index("users") + 3],
                ["users", "tenants", "customers"],
            )

        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text(encoding="utf-8"))
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("publication_contract_version", manifest)
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(len(manifest["source_families"]), 120)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(
            summary["capacity_aggregation"],
            {
                "base_totals_published": False,
                "cross_entity_sum_valid": False,
                "reason": (
                    "Capacity rows can be nested, component-scoped, superseding, or "
                    "metric-distinct. Arithmetic sums are not valid facility, site, load, "
                    "energy, or unique-physical-site totals."
                ),
                "scope": "typed_source_observation_rows",
            },
        )
        self.assertEqual(summary["entities_total"], 421)
        self.assertEqual(summary["projects_total"], 181)
        self.assertEqual(summary["evidence_total"], 287)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 148)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(summary["capacity_estimates_current"], 418)

        base_signal_ids = {
            row["source_observation_evidence_id"]
            for row in rows(BASE_RELEASE / "construction_source_signals.csv")
        }
        added_signals = [
            row
            for row in rows(RELEASE / "construction_source_signals.csv")
            if row["source_observation_evidence_id"] not in base_signal_ids
        ]
        self.assertEqual(len(added_signals), 3)
        self.assertEqual(
            {row["source_content_hash"] for row in added_signals}, EVIDENCE_HASHES
        )
        self.assertEqual(
            {
                entity["stable_key"]
                for signal in added_signals
                for entity in json.loads(signal["affected_entities_json"])
            },
            set(PROJECT_DATES),
        )
        stc_signal = next(
            row for row in added_signals if row["source_family"] == "stc_sustainability_reports"
        )
        self.assertEqual(stc_signal["affected_entity_count"], "3")

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(
            definition["scope"],
            {
                "commercial_census_parity_claimed": False,
                "epoch_selected_site_count_is_global_census": False,
                "orphan_timeline_imported": False,
                "source_scoped_estimates_only": True,
            },
        )
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("Role columns are dimensioned", readme)
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)
        self.assertIn("not a count of unique physical sites", readme)


if __name__ == "__main__":
    unittest.main()
