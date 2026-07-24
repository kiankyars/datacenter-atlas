from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import (
    OpenSeedReleaseError,
    validate_open_seed_release,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v5.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v5"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v8.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v8"
CURRENT_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v9.json"
CURRENT_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v9"
CANDIDATE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v10.json"
CANDIDATE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v10"
V11_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v11.json"
V11_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v11"
V10_DEFINITION_SHA256 = "b04137a0044faa7d1418b82f5c4376d6f498867f3285124942b1ac4b8c88dc3c"
V10_MANIFEST_SHA256 = "91f33c70bc1e073577a172250cea5496c2074bcefd3248619c3dd6be28202aca"
V11_DEFINITION_SHA256 = "2572be30ce26960021b1b73bf7965a6568ddf21170bc0185673e51794fd6efef"
V11_MANIFEST_SHA256 = "31004d8c7f9144be00ad847ba3e0def6c33cbc8c64fd67e8b659dc86ffb89905"
V11_SOURCE_PATHS = (
    ROOT / "sources" / "curated-official-2026-07-19-ntt-amsterdam-1.json",
    ROOT / "sources" / "curated-official-2026-07-19-ntt-frankfurt-1.json",
    ROOT / "sources" / "curated-official-2026-07-19-vantage-kix1-osaka.json",
    ROOT / "sources" / "curated-official-2026-07-19-vantage-kul2-cyberjaya.json",
    ROOT / "sources" / "curated-official-2026-07-19-vantage-oh1-new-albany.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedReleaseTests(unittest.TestCase):
    def mutable_copy(self, temporary: Path) -> Path:
        target = temporary / "release"
        shutil.copytree(RELEASE, target)
        target.chmod(0o755)
        for path in target.iterdir():
            path.chmod(0o644)
        return target

    def test_frozen_release_rebuilds_byte_for_byte_offline(self) -> None:
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            manifest = validate_open_seed_release(DEFINITION, RELEASE)
        self.assertEqual(manifest["entities"], 104)
        self.assertEqual(manifest["evidence_records"], 86)
        self.assertEqual(manifest["construction_pipeline_records"], 60)
        self.assertEqual(manifest["capacity_estimates"], 340)
        self.assertEqual(manifest["resolution_candidates"], 1)
        self.assertIn("google_infrastructure_blog", manifest["source_families"])
        self.assertIn("microsoft_official_news", manifest["source_families"])

    def test_mutable_release_requires_explicit_opt_out(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            validate_open_seed_release(DEFINITION, copy, require_frozen=False)
            with self.assertRaisesRegex(OpenSeedReleaseError, "mode 0555"):
                validate_open_seed_release(DEFINITION, copy)

    def test_changed_release_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary_name:
            copy = self.mutable_copy(Path(temporary_name))
            (copy / "evidence.csv").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(OpenSeedReleaseError, "evidence.csv"):
                validate_open_seed_release(DEFINITION, copy, require_frozen=False)

    def test_symlinked_release_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary_name:
            temporary = Path(temporary_name)
            alias = temporary / "alias"
            alias.symlink_to(RELEASE, target_is_directory=True)
            with self.assertRaisesRegex(OpenSeedReleaseError, "symlink component"):
                validate_open_seed_release(DEFINITION, alias)

    def test_previous_v8_rebuilds_offline_with_publication_contract_v2(self) -> None:
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            manifest = validate_open_seed_release(PREVIOUS_DEFINITION, PREVIOUS_RELEASE)
        self.assertEqual(manifest["entities"], 112)
        self.assertEqual(manifest["evidence_records"], 91)
        self.assertEqual(manifest["capacity_estimates"], 342)
        self.assertEqual(manifest["construction_pipeline_records"], 64)
        self.assertEqual(manifest["construction_source_signals"], 60)
        self.assertEqual(manifest["resolution_candidates"], 2)
        attribution = (PREVIOUS_RELEASE / "ATTRIBUTION.txt").read_text()
        self.assertIn("DTE Energy\n", attribution)
        readme = (PREVIOUS_RELEASE / "README.md").read_text()
        self.assertNotIn("atlas.html", readme)
        self.assertIn("Capacity and energy semantics are row-specific", readme)

    def test_current_v9_rebuilds_offline_with_typed_construction_capacity(self) -> None:
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            manifest = validate_open_seed_release(CURRENT_DEFINITION, CURRENT_RELEASE)
        self.assertEqual(manifest["entities"], 127)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 99, "project": 28})
        self.assertEqual(manifest["evidence_records"], 101)
        self.assertEqual(manifest["capacity_estimates"], 348)
        self.assertEqual(manifest["construction_pipeline_records"], 73)
        self.assertEqual(manifest["construction_source_signals"], 65)
        self.assertEqual(manifest["resolution_candidates"], 3)
        self.assertIn("applied_digital_sec_filings", manifest["source_families"])
        self.assertIn(
            "environment_agency_permit_application_supporting_document",
            manifest["source_families"],
        )
        self.assertIn("north_dakota_deq_air_quality_records", manifest["source_families"])
        self.assertIn("nzx_company_announcement", manifest["source_families"])
        attribution = (CURRENT_RELEASE / "ATTRIBUTION.txt").read_text()
        self.assertIn("Applied Digital Corporation\n", attribution)
        self.assertIn("North Dakota Department of Environmental Quality\n", attribution)
        self.assertIn("Infratil Limited via NZX\n", attribution)
        readme = (CURRENT_RELEASE / "README.md").read_text()
        self.assertNotIn("atlas.html", readme)
        self.assertIn("Capacity and energy semantics are row-specific", readme)

    def test_candidate_v10_rebuilds_offline_with_finland_phase_guardrails(self) -> None:
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            manifest = validate_open_seed_release(
                CANDIDATE_DEFINITION,
                CANDIDATE_RELEASE,
            )
        self.assertEqual(manifest["entities"], 136)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 102, "project": 34})
        self.assertEqual(manifest["evidence_records"], 106)
        self.assertEqual(manifest["capacity_estimates"], 348)
        self.assertEqual(manifest["construction_pipeline_records"], 79)
        self.assertEqual(manifest["construction_source_signals"], 70)
        self.assertEqual(manifest["resolution_candidates"], 3)
        self.assertIn(
            "finnish_municipal_data_center_updates",
            manifest["source_families"],
        )
        self.assertIn("microsoft_local_project_updates", manifest["source_families"])
        attribution = (CANDIDATE_RELEASE / "ATTRIBUTION.txt").read_text()
        self.assertIn("City of Espoo\n", attribution)
        self.assertIn("Microsoft Local\n", attribution)
        self.assertIn("Municipality of Vihti\n", attribution)
        summary = (CANDIDATE_RELEASE / "summary.json").read_text()
        self.assertIn('"permitted": 2', summary)
        self.assertIn('"under_construction": 48', summary)

    def test_accepted_v10_definition_and_release_inventory_are_exactly_preserved(self) -> None:
        self.assertEqual(sha256(CANDIDATE_DEFINITION), V10_DEFINITION_SHA256)
        self.assertEqual(sha256(CANDIDATE_RELEASE / "manifest.json"), V10_MANIFEST_SHA256)
        validate_open_seed_release(CANDIDATE_DEFINITION, CANDIDATE_RELEASE)

    def test_accepted_v11_rebuilds_twice_offline_with_expected_delta(self) -> None:
        self.assertEqual(sha256(V11_DEFINITION), V11_DEFINITION_SHA256)
        self.assertEqual(sha256(V11_RELEASE / "manifest.json"), V11_MANIFEST_SHA256)
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_open_seed_release(
                V11_DEFINITION,
                V11_RELEASE,
            )
            second = validate_open_seed_release(
                V11_DEFINITION,
                V11_RELEASE,
            )
        self.assertEqual(first, second)
        self.assertEqual(first["entities"], 146)
        self.assertEqual(first["entities_by_kind"], {"campus": 107, "project": 39})
        self.assertEqual(first["evidence_records"], 112)
        self.assertEqual(first["capacity_estimates"], 358)
        self.assertEqual(first["construction_pipeline_records"], 80)
        self.assertEqual(first["construction_source_signals"], 71)
        self.assertEqual(first["resolution_candidates"], 4)
        self.assertIn("ntt_global_data_center_brochures", first["source_families"])
        self.assertIn("ntt_global_data_center_location_pages", first["source_families"])
        self.assertIn("vantage_data_center_location_pages", first["source_families"])

        summary = json.loads((V11_RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 2,
                "expansion": 27,
                "operational": 31,
                "permitted": 2,
                "under_construction": 49,
            },
        )

    def test_v11_stale_lifecycle_and_location_guardrails(self) -> None:
        entities = {
            row["stable_key"]: row for row in csv_rows(V11_RELEASE / "entities.csv")
        }
        status_null_projects = {
            "curated:vantage-kix1-osaka-campus:first-facility",
            "curated:vantage-kul2-cyberjaya-campus:full-campus-development",
            "curated:vantage-oh1-new-albany-campus:first-building",
            "curated:ntt-amsterdam-1-campus:buildings-c-and-d-expansion",
        }
        for stable_key in status_null_projects:
            self.assertEqual(entities[stable_key]["status"], "")
            self.assertEqual(entities[stable_key]["status_as_of"], "")

        self.assertEqual(
            entities["curated:ntt-frankfurt-1-campus"]["status"], "operational"
        )
        self.assertEqual(
            entities["curated:ntt-frankfurt-1-campus:7-3mw-expansion"]["status"],
            "under_construction",
        )
        self.assertEqual(
            entities["curated:ntt-amsterdam-1-campus"]["status"], "operational"
        )

        oh1 = entities["curated:vantage-oh1-new-albany-campus"]
        self.assertEqual(oh1["address"], "3325 Horizon Court, New Albany, OH 43031, USA")
        self.assertEqual((oh1["latitude"], oh1["longitude"]), ("40.09458", "-82.73014"))
        self.assertEqual(
            entities["curated:vantage-oh1-new-albany-campus:first-building"]["latitude"],
            "",
        )
        self.assertEqual(
            entities["curated:ntt-frankfurt-1-campus"]["address"],
            "Eschborner Landstraße 100, 60489 Frankfurt am Main, Germany",
        )
        self.assertEqual(entities["curated:ntt-frankfurt-1-campus"]["latitude"], "")
        self.assertEqual(
            entities["curated:ntt-amsterdam-1-campus"]["address"],
            "Aviolanda 1, 1437 ED Rozenburg, Netherlands",
        )
        self.assertEqual(entities["curated:ntt-amsterdam-1-campus"]["latitude"], "")

        for source_path in V11_SOURCE_PATHS:
            source = json.loads(source_path.read_text(encoding="utf-8"))
            self.assertEqual(source["campus"]["roles"], {})
            self.assertEqual(source["project"]["roles"], {})
            self.assertEqual(source["operating_models"], [])
            self.assertEqual(source["workloads"], [])
            for evidence in source["evidence"]:
                self.assertEqual(evidence["license"], "all-rights-reserved")
                self.assertEqual(
                    evidence["metadata"]["content_hash_verification"],
                    "fetched_bytes_sha256",
                )

    def test_v11_capacity_revisions_scopes_and_mva_exclusion(self) -> None:
        sources = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in V11_SOURCE_PATHS
        }
        expected_capacities = {
            "curated-official-2026-07-19-vantage-kix1-osaka.json": [
                ("campus", "planned", 68),
                ("project", "forecast", 28),
            ],
            "curated-official-2026-07-19-vantage-kul2-cyberjaya.json": [
                ("campus", "planned", 256),
                ("campus", "planned", 436),
            ],
            "curated-official-2026-07-19-vantage-oh1-new-albany.json": [
                ("campus", "planned", 192),
                ("project", "forecast", 64),
            ],
            "curated-official-2026-07-19-ntt-frankfurt-1.json": [
                ("campus", "operational", 70.1),
                ("project", "planned", 7.3),
                ("campus", "planned", 77.4),
            ],
            "curated-official-2026-07-19-ntt-amsterdam-1.json": [
                ("campus", "operational", 20.7),
                ("project", "planned", 22),
            ],
        }
        for filename, expected in expected_capacities.items():
            capacities = sources[filename]["capacities"]
            self.assertEqual(
                [(row["entity"], row["stage"], row["base"]) for row in capacities],
                expected,
            )
            self.assertTrue(
                all(row["metric"] == "critical_it_mw" and row["unit"] == "MW" for row in capacities)
            )

        kul2 = sources["curated-official-2026-07-19-vantage-kul2-cyberjaya.json"]
        self.assertEqual(
            [(row["as_of_date"], row["base"]) for row in kul2["capacities"]],
            [("2024-08-06", 256), ("2025-12-02", 436)],
        )
        self.assertIn("supersedes", kul2["capacities"][1]["notes"])
        kul2_current_rows = [
            row
            for row in csv_rows(V11_RELEASE / "capacity_estimates.csv")
            if row["name"] == "Vantage KUL2 Cyberjaya II Data Center Campus"
        ]
        self.assertEqual([(row["stage"], row["base"]) for row in kul2_current_rows], [("planned", "436.0")])

        self.assertIn("500MVA", json.dumps(kul2["evidence"]))
        self.assertIn(
            "120MVA",
            json.dumps(sources["curated-official-2026-07-19-ntt-frankfurt-1.json"]["evidence"]),
        )
        self.assertIn(
            "60MVA",
            json.dumps(sources["curated-official-2026-07-19-ntt-amsterdam-1.json"]["evidence"]),
        )
        new_entity_names = {
            "Vantage KIX1 Osaka Data Center Campus",
            "Vantage KIX1 First Facility",
            "Vantage KUL2 Cyberjaya II Data Center Campus",
            "Vantage OH1 New Albany Data Center Campus",
            "Vantage OH1 First Building",
            "NTT Frankfurt 1 Data Center Campus",
            "NTT Frankfurt 1 7.3MW Expansion",
            "NTT Amsterdam 1 Data Center Campus",
            "NTT Amsterdam 1 Buildings C and D Expansion",
        }
        release_capacities = [
            row
            for row in csv_rows(V11_RELEASE / "capacity_estimates.csv")
            if row["name"] in new_entity_names
        ]
        self.assertTrue(
            all(row["metric"] == "critical_it_mw" and row["unit"] == "MW" for row in release_capacities)
        )
        self.assertNotIn("42.7", {row["base"] for row in release_capacities})
        self.assertTrue({"70.1", "7.3", "77.4"}.issubset({row["base"] for row in release_capacities}))


if __name__ == "__main__":
    unittest.main()
