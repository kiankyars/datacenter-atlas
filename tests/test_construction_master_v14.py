from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_master import (
    ConstructionMasterError,
    _V13_OPEN_SEED_LICENSES,
    _V13_OPEN_SEED_PUBLISHERS,
    _V13_OPEN_SEED_SOURCE_ROOTS,
    _V14_OPEN_SEED_LICENSES,
    _V14_OPEN_SEED_PUBLISHERS,
    _V14_OPEN_SEED_SOURCE_ROOTS,
    _definition,
    _validate_v14_open_seed_source_allowlist,
    validate_construction_master,
    write_construction_master,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v13.json"
)
DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v14.json"
)
PREVIOUS_BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v13"
BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v14"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"

DEFINITION_SHA256 = (
    "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4"
)
MANIFEST_SHA256 = (
    "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b"
)
BUNDLE_INVENTORY_SHA256 = (
    "4b2ce6298788a6af9b5df90c4148b640fafdcb39ad8c0044d35832b8cd3bee60"
)
INPUT_CHECKPOINT_INVENTORY_SHA256 = (
    "a0e86cd8676c890b91b83a5d101676085f33544ba96089a6f0365b6bdb0d8d33"
)
TIER_A_PROJECTION_SHA256 = (
    "159584ad2097da71383831d4fad4983045d8b740106e32a60329b3d1fe650e4d"
)
ACCEPTED_DEFINITION_SHA256 = {
    "sources/open-seed-2026-07-19-v33.json": (
        "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
    ),
    "sources/federation-2026-07-19-public-open-v12.json": (
        "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
    ),
    "sources/coverage-audit-2026-07-19-public-open-v13.json": (
        "2745fd688f2727dc954b733386a00fbe8cf00401e5aeec4a451528c6d0bc9d9e"
    ),
}
ACCEPTED_MANIFEST_SHA256 = {
    "releases/2026-07-19-open-seed-v33/manifest.json": (
        "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
    ),
    "federated_indexes/2026-07-19-public-open-v12/manifest.json": (
        "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
    ),
    "audits/2026-07-19-public-open-coverage-v13/manifest.json": (
        "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d"
    ),
}
ADDITIONS = {
    "3fa68a6a-4362-5a39-b676-751d205f134d": {
        "evidence_id": "ae7a6e22-23d2-570e-b7a8-9ffa13e27bf3",
        "method": "authoritative_construction_start",
        "publisher": "Adani Group",
        "source_root": "adani_connect_magazine",
        "status": "under_construction",
        "title": "Breaking Ground On Odisha’s Next Growth Chapter",
    },
    "5bfb4ad8-a8f4-5937-9242-a96f9292c385": {
        "evidence_id": "a315ac77-14e1-553f-ac3d-6f03c2b9c52b",
        "method": "authoritative_physical_status_update",
        "publisher": "CSC – IT Center for Science Ltd.",
        "source_root": "csc_news_and_blog",
        "status": "under_construction",
        "title": "Construction of the LUMI-AI data center in full swing",
    },
    "dcd52b51-9cad-59fc-ae4a-ff6280372dda": {
        "evidence_id": "13416d2d-284c-522a-b1c8-c6c425b019fb",
        "method": "authoritative_physical_status_update",
        "publisher": "ESR",
        "source_root": "esr_newsroom",
        "status": "site_preparation",
        "title": (
            "ESR and Colt DCS Announce Joint Venture on New Osaka Data Centre "
            "Development"
        ),
    },
    "fe92035e-3a00-5a85-b009-34fe9c2c545e": {
        "evidence_id": "487fa332-bffe-5313-8efb-b83fd605348b",
        "method": "authoritative_construction_start",
        "publisher": "SRV Group Plc",
        "source_root": "srv_cision_press_releases",
        "status": "under_construction",
        "title": (
            "DayOne data center construction to start in Lahti – SRV strengthens "
            "its position in the growing market for data center construction"
        ),
    },
}
ADDITION_IDS = frozenset(ADDITIONS)
MINOH_PHASE_ID = "dcd52b51-9cad-59fc-ae4a-ff6280372dda"
MINOH_CAMPUS_ID = "7afe083f-1eb0-5d25-aabd-cc02e624c789"


def _jsonl_rows(bundle: Path):
    with (bundle / "construction-master.jsonl").open("rb") as source:
        for raw_line in source:
            yield json.loads(raw_line)


def _release_rows(bundle: Path, artifact_id: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for row in _jsonl_rows(bundle):
        if row["source"]["artifact_id"] == artifact_id:
            rows[row["source"]["record_id"]] = row
        elif rows:
            break
    return rows


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def _checkpoint_inventory_sha256(manifest: dict) -> str:
    raw = json.dumps(
        manifest["input_checkpoints"], sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _without_release_envelope(row: dict) -> dict:
    normalized = deepcopy(row)
    normalized.pop("row_id")
    for field in (
        "artifact_id",
        "artifact_path",
        "artifact_sha256",
        "manifest_sha256",
        "release_id",
    ):
        normalized["source"].pop(field)
    return normalized


class FrozenConstructionMasterV14Tests(unittest.TestCase):
    def test_frozen_bundle_validates_and_rebuilds_twice_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        for relative_path, expected_sha256 in ACCEPTED_DEFINITION_SHA256.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                expected_sha256,
            )
        for relative_path, expected_sha256 in ACCEPTED_MANIFEST_SHA256.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                expected_sha256,
            )

        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "getaddrinfo",
            side_effect=AssertionError("offline build attempted DNS resolution"),
        ):
            manifest = validate_construction_master(
                BUNDLE, definition_path=DEFINITION
            )
            with tempfile.TemporaryDirectory() as temporary:
                rebuilt_one = Path(temporary) / "bundle-one"
                rebuilt_two = Path(temporary) / "bundle-two"
                write_construction_master(DEFINITION, rebuilt_one)
                write_construction_master(DEFINITION, rebuilt_two)
                for filename in sorted(entry.name for entry in BUNDLE.iterdir()):
                    expected = (BUNDLE / filename).read_bytes()
                    self.assertEqual((rebuilt_one / filename).read_bytes(), expected)
                    self.assertEqual((rebuilt_two / filename).read_bytes(), expected)

        self.assertEqual(
            hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(
            _checkpoint_inventory_sha256(manifest),
            INPUT_CHECKPOINT_INVENTORY_SHA256,
        )
        self.assertEqual(len(manifest["input_checkpoints"]), 132)
        self.assertEqual(manifest["row_counts"]["total"], 109_111)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 319, "B": 6_298, "C": 102_494},
        )

        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108_792)
        self.assertEqual(
            coverage["construction_arithmetic"],
            {
                "rows": 319,
                "source_supported_rows": 319,
                "statuses": {
                    "announced": 3,
                    "civil_works": 2,
                    "expansion": 27,
                    "foundations": 2,
                    "mep_electrical": 15,
                    "permitted": 3,
                    "proposed": 22,
                    "shell": 6,
                    "site_preparation": 10,
                    "under_construction": 229,
                },
                "tier_a_arithmetic_projection_sha256": TIER_A_PROJECTION_SHA256,
                "unique_physical_sites": None,
                "unit": "source_supported_observation_row",
                "verified_by_independent_master_review": 0,
            },
        )
        self.assertEqual(
            coverage["evidence_observations"],
            {
                "annual_energy": 73,
                "operating_model": 2,
                "pue": 2,
                "source_evidence_records": 115_406,
                "typed_capacity_excluding_annual_energy_and_pue": 234,
                "untyped_capacity_statements": 23,
                "workload": 103,
            },
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["benchmark_parity_claimed"])
        self.assertFalse(coverage["scope"]["candidate_or_review_rows_promoted"])

        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(
            {entry.name for entry in BUNDLE.iterdir()},
            {
                "ATTRIBUTION.txt",
                "README.md",
                "construction-master.csv",
                "construction-master.jsonl",
                "coverage.json",
                "manifest.json",
                "manifest.sha256",
            },
        )
        self.assertTrue(
            all(
                entry.is_file()
                and not entry.is_symlink()
                and stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in BUNDLE.iterdir()
            )
        )

    def test_v33_four_row_delta_evidence_capacity_and_roles_are_exact(self) -> None:
        previous = _release_rows(PREVIOUS_BUNDLE, "epoch-official-open-seed-v32")
        current = _release_rows(BUNDLE, "epoch-official-open-seed-v33")
        self.assertEqual(set(current) - set(previous), ADDITION_IDS)
        self.assertEqual(set(previous) - set(current), set())
        for record_id in sorted(previous):
            self.assertEqual(
                _without_release_envelope(current[record_id]),
                _without_release_envelope(previous[record_id]),
            )

        additions = [current[record_id] for record_id in sorted(ADDITION_IDS)]
        self.assertEqual(
            Counter(row["entity"]["kind"] for row in additions),
            Counter({"project": 4}),
        )
        self.assertEqual(
            Counter(row["lifecycle"]["normalized_status"] for row in additions),
            Counter({"under_construction": 3, "site_preparation": 1}),
        )
        self.assertEqual(
            Counter(row["source"]["source_license"] for row in additions),
            Counter({"all-rights-reserved": 4}),
        )
        self.assertEqual(sum(len(row["source_evidence"]) for row in additions), 4)
        self.assertTrue(
            all(
                row["tier"] == "A"
                and row["entity"]["latitude"] is None
                and row["entity"]["longitude"] is None
                and row["construction"]["source_supported"]
                and not row["construction"]["verified"]
                and row["construction"]["verification_status"]
                == "source_supported_not_independently_verified"
                and not row["review_only"]
                and not row["disposition"]["unique_site_counted"]
                and row["annual_energy_observations"] == []
                and row["pue_observations"] == []
                and row["untyped_capacity_statements"] == []
                and row["workload_observations"] == []
                and row["operating_model_observation"] is None
                and row["satellite_links"] == []
                and row["resolution_advisories"] == []
                and row["fusion_overlay"] is None
                and "role_observations" not in row
                for row in additions
            )
        )

        for record_id, expected in ADDITIONS.items():
            row = current[record_id]
            self.assertEqual(row["lifecycle"]["normalized_status"], expected["status"])
            self.assertEqual(row["construction"]["method"], expected["method"])
            self.assertEqual(row["source"]["evidence_ids"], [expected["evidence_id"]])
            self.assertEqual(row["source"]["source_roots"], [expected["source_root"]])
            self.assertEqual(
                {
                    "evidence_id": row["source_evidence"][0]["evidence_id"],
                    "license": row["source_evidence"][0]["license"],
                    "publisher": row["source_evidence"][0]["publisher"],
                    "source_family": row["source_evidence"][0]["source_family"],
                    "title": row["source_evidence"][0]["title"],
                },
                {
                    "evidence_id": expected["evidence_id"],
                    "license": "all-rights-reserved",
                    "publisher": expected["publisher"],
                    "source_family": expected["source_root"],
                    "title": expected["title"],
                },
            )

        expected_phase_capacity = {
            "as_of_date": "2025-10-16",
            "confidence": 0.99,
            "evidence_id": "13416d2d-284c-522a-b1c8-c6c425b019fb",
            "high": 65.0,
            "low": 65.0,
            "method": "reported",
            "metric": "gross_facility_mw",
            "notes": (
                "Planned 65 MW Facility Load for Phase 1; treated as gross facility "
                "demand, not IT, grid, generation, current load, or energy. It is "
                "contained within and non-additive to the 130 MW site row."
            ),
            "scope": "source_scoped_entity",
            "stage": "planned",
            "target_date": None,
            "unit": "MW",
            "value": 65.0,
        }
        self.assertEqual(
            current[MINOH_PHASE_ID]["capacity_observations"],
            [expected_phase_capacity],
        )
        self.assertTrue(
            all(
                current[record_id]["capacity_observations"] == []
                for record_id in ADDITION_IDS - {MINOH_PHASE_ID}
            )
        )

        with (OPEN_SEED_RELEASE / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            source_additions = {
                row["entity_id"]: row
                for row in csv.DictReader(source)
                if row["entity_id"] in ADDITION_IDS
            }
        self.assertEqual(set(source_additions), ADDITION_IDS)
        expected_roles = {
            record_id: {"operator": "", "owner": "", "users": ""}
            for record_id in ADDITION_IDS
        }
        expected_roles[MINOH_PHASE_ID]["operator"] = "Colt Data Centre Services"
        self.assertEqual(
            {
                record_id: {
                    "operator": row["operator"],
                    "owner": row["owner"],
                    "users": row["users"],
                }
                for record_id, row in source_additions.items()
            },
            expected_roles,
        )
        self.assertTrue(
            all(
                row["operating_model"] == "" and row["workloads_json"] == "[]"
                for row in source_additions.values()
            )
        )
        self.assertEqual(
            json.loads(source_additions[MINOH_PHASE_ID]["tags_json"])[
                "role:developer"
            ],
            "ESR–Colt DCS joint venture",
        )
        self.assertEqual(
            json.loads(source_additions[MINOH_PHASE_ID]["tags_json"])[
                "role:operator"
            ],
            "Colt Data Centre Services",
        )
        lumi_id = "5bfb4ad8-a8f4-5937-9242-a96f9292c385"
        self.assertEqual(
            json.loads(source_additions[lumi_id]["tags_json"])["role:contractor"],
            "SRV",
        )

        with (OPEN_SEED_RELEASE / "entities.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            minoh_entities = {
                row["entity_id"]: row
                for row in csv.DictReader(source)
                if row["entity_id"] in {MINOH_CAMPUS_ID, MINOH_PHASE_ID}
            }
        self.assertEqual(set(minoh_entities), {MINOH_CAMPUS_ID, MINOH_PHASE_ID})
        campus_capacity = json.loads(
            minoh_entities[MINOH_CAMPUS_ID]["capacity_estimates_json"]
        )
        phase_capacity = json.loads(
            minoh_entities[MINOH_PHASE_ID]["capacity_estimates_json"]
        )
        self.assertEqual(len(campus_capacity), 1)
        self.assertEqual(len(phase_capacity), 1)
        self.assertEqual(
            {
                "campus": (
                    campus_capacity[0]["base"],
                    campus_capacity[0]["metric"],
                    campus_capacity[0]["stage"],
                ),
                "phase": (
                    phase_capacity[0]["base"],
                    phase_capacity[0]["metric"],
                    phase_capacity[0]["stage"],
                ),
            },
            {
                "campus": (130.0, "gross_facility_mw", "planned"),
                "phase": (65.0, "gross_facility_mw", "planned"),
            },
        )
        self.assertEqual(
            campus_capacity[0]["evidence_id"], phase_capacity[0]["evidence_id"]
        )
        self.assertIn("non-additive", campus_capacity[0]["notes"])
        self.assertIn("non-additive", phase_capacity[0]["notes"])
        for observation in (campus_capacity[0], phase_capacity[0]):
            notes = observation["notes"]
            for excluded_semantic in (
                "not IT",
                "grid",
                "generation",
                "current load",
                "energy",
            ):
                self.assertIn(excluded_semantic, notes)

        with (OPEN_SEED_RELEASE / "capacity_estimates.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            minoh_capacity_rows = [
                row
                for row in csv.DictReader(source)
                if row["entity_id"] in {MINOH_CAMPUS_ID, MINOH_PHASE_ID}
            ]
        self.assertEqual(
            {
                (row["entity_id"], row["base"], row["metric"], row["stage"])
                for row in minoh_capacity_rows
            },
            {
                (MINOH_CAMPUS_ID, "130.0", "gross_facility_mw", "planned"),
                (MINOH_PHASE_ID, "65.0", "gross_facility_mw", "planned"),
            },
        )
        self.assertNotIn(MINOH_CAMPUS_ID, current)
        self.assertFalse(
            any(
                observation.get("value") == 195
                for observation in current[MINOH_PHASE_ID]["capacity_observations"]
            )
        )
        readme = (BUNDLE / "README.md").read_text()
        self.assertIn("contained within and non-additive", readme)
        self.assertIn("Neither value is current load", readme)
        self.assertNotIn("195 MW", readme)

    def test_all_nonseed_rows_and_review_lineage_are_byte_exact(self) -> None:
        before_path = PREVIOUS_BUNDLE / "construction-master.jsonl"
        after_path = BUNDLE / "construction-master.jsonl"
        sentinel = object()
        with before_path.open("rb") as before, after_path.open("rb") as after:
            for _ in range(195):
                next(before)
            for _ in range(199):
                next(after)
            compared = 0
            for previous_line, current_line in zip_longest(
                before, after, fillvalue=sentinel
            ):
                self.assertIsNot(previous_line, sentinel)
                self.assertIsNot(current_line, sentinel)
                self.assertEqual(current_line, previous_line)
                compared += 1
        self.assertEqual(compared, 108_912)

        review_rows = [
            row
            for row in _jsonl_rows(BUNDLE)
            if row["observation_kind"] == "sentinel_analyst_change_review"
        ]
        self.assertEqual(len(review_rows), 43)
        self.assertEqual(
            Counter(
                row["satellite_links"][0]["batch_artifact_id"]
                for row in review_rows
            ),
            Counter(
                {
                    "satellite-global-open-v3-active-001": 7,
                    "satellite-global-open-v3-proposed-001": 1,
                    "satellite-global-open-v3-unknown-010": 23,
                    "satellite-global-open-v3-unknown-013": 6,
                    "satellite-global-open-v3-unknown-015": 6,
                }
            ),
        )
        self.assertTrue(
            all(
                row["satellite_links"][0].get("catalog_batch_artifact_id")
                == "satellite-global-open-v3-unknown-030"
                for row in review_rows
                if "unknown-"
                in row["satellite_links"][0]["batch_artifact_id"]
            )
        )

        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        manifest_paths = {
            checkpoint["path"] for checkpoint in manifest["input_checkpoints"]
        }
        for marker in (
            "releases/2026-07-19-open-seed-v33/manifest.json",
            "federated_indexes/2026-07-19-public-open-v12/manifest.json",
            "audits/2026-07-19-public-open-coverage-v13/manifest.json",
        ):
            self.assertIn(marker, manifest_paths)
        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertNotIn(
            "public-open-coverage-v13",
            coverage["row_counts"]["by_source_artifact"],
        )
        self.assertNotIn(
            "public-open-federation-v12",
            coverage["row_counts"]["by_source_artifact"],
        )

    def test_v14_contract_allowlist_and_attribution_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []
        for field_path, message in (
            (
                ("expected_counts", "tier_a_rows"),
                "v14 count or Tier-A projection contract changed",
            ),
            (
                ("inputs", "tier_a_releases", 0, "manifest", "sha256"),
                "v14 open-seed v33 checkpoints changed",
            ),
            (
                ("inputs", "coverage_context", "audit_manifest", "sha256"),
                "v14 federation or coverage-audit context changed",
            ),
        ):
            changed = deepcopy(document)
            target = changed
            for key in field_path[:-1]:
                target = target[key]
            target[field_path[-1]] = (
                0 if field_path[-1] == "tier_a_rows" else "0" * 64
            )
            changes.append((changed, message))
        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T23:59:56Z"
        changes.append((changed, "v14 generation timestamp changed"))

        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v14-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        self.assertEqual(
            _V14_OPEN_SEED_SOURCE_ROOTS - _V13_OPEN_SEED_SOURCE_ROOTS,
            {
                "adani_connect_magazine",
                "csc_news_and_blog",
                "esr_newsroom",
                "srv_cision_press_releases",
            },
        )
        self.assertEqual(
            _V14_OPEN_SEED_PUBLISHERS - _V13_OPEN_SEED_PUBLISHERS,
            {
                "Adani Group",
                "CSC – IT Center for Science Ltd.",
                "ESR",
                "SRV Group Plc",
            },
        )
        self.assertEqual(_V14_OPEN_SEED_LICENSES, _V13_OPEN_SEED_LICENSES)

        with (OPEN_SEED_RELEASE / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source, (OPEN_SEED_RELEASE / "evidence.csv").open(
            newline="", encoding="utf-8"
        ) as evidence_source:
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v14_open_seed_source_allowlist(rows, evidence)

        selected_id = ADDITIONS[
            "3fa68a6a-4362-5a39-b676-751d205f134d"
        ]["evidence_id"]
        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v14 open-seed source allowlist changed"
        ):
            _validate_v14_open_seed_source_allowlist(rows, changed_evidence)

        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["source_family"] = "unexpected_source_root"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v14 open-seed source allowlist changed"
        ):
            _validate_v14_open_seed_source_allowlist(rows, changed_evidence)

        changed_rows = deepcopy(rows)
        changed_rows[0]["source_license"] = "unexpected-license"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v14 open-seed source allowlist changed"
        ):
            _validate_v14_open_seed_source_allowlist(changed_rows, evidence)

        attribution = (BUNDLE / "ATTRIBUTION.txt").read_text()
        for publisher in (
            "Adani Group",
            "CSC – IT Center for Science Ltd.",
            "ESR",
            "SRV Group Plc",
        ):
            self.assertIn(publisher, attribution)
        self.assertIn("not redistributed or relicensed", attribution)


if __name__ == "__main__":
    unittest.main()
