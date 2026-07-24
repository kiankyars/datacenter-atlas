from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_master import (
    ConstructionMasterError,
    _definition,
    _validate_v12_open_seed_source_allowlist,
    validate_construction_master,
    write_construction_master,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v11.json"
)
DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v12.json"
)
PREVIOUS_BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v11"
BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v12"

DEFINITION_SHA256 = (
    "286e60979bb313d0ca085ae1980009427e50521b520c6d47425452f5af9c45c5"
)
MANIFEST_SHA256 = (
    "f11a800cbaccacfc9204362d63ac08df1cdd580b5bbb5ede2d1da1e7f39a18cc"
)
BUNDLE_INVENTORY_SHA256 = (
    "d4ce629942e32fdc1f0a37921037674140bf3bb30d2ddfe656b3730ab3a61be4"
)
TIER_A_PROJECTION_SHA256 = (
    "e68e660e78cfdea7e04ee01baefd1f51f6c3e4e9910d8d57a54e31c121a2cdfd"
)
ADDITION_IDS = frozenset(
    {
        "07cf7a18-232a-57ab-ad3b-3ac79389f7d3",
        "0cdff49d-f05c-5993-acd1-d1259fd80165",
        "0d532f35-4322-5f03-b470-04fa097f6d8b",
        "0fe54eb4-72b0-5582-9235-b1ed260c5aba",
        "1b974d42-546a-5915-8207-af2c9dbb36c2",
        "1d1971ee-7f81-5f85-9f27-e648fd2b35bc",
        "25982acd-32ec-5c02-879e-512766027a3a",
        "291bbe49-9adb-599a-b6f0-3c170a7b2521",
        "34925def-87e7-5bb7-ac97-cb1fddec4e3b",
        "3941c42e-216d-52fa-b0d8-d7555b441a1a",
        "43a98226-5267-583d-a4b1-3d74ad86822c",
        "46a8cb9a-8415-56c0-96d3-54aae228e20b",
        "48085c94-30b2-53a9-bc23-070b5c7c9448",
        "4afd2551-1442-5f67-a1d9-0d245835088d",
        "5031e737-a9a4-55b6-b352-ef94d0213947",
        "517c9819-5f20-5766-a123-73d255321fce",
        "57ff0b7f-3a01-5c1e-a0d8-38495c1c1743",
        "663f54c4-7e5f-5c0b-b2db-dafff1094a38",
        "6737184c-a3f3-56b1-ae3f-449b3fccb084",
        "7acd9faf-009b-5c24-9e54-2c5e1d5376d4",
        "7ff76e22-a26d-5de6-be6a-fa0e487675bd",
        "84a9237c-cfd2-5d4a-a557-e5eea07a1b31",
        "8ca10635-6e58-5b9c-a7d7-838c40f67e13",
        "9fe862f6-ace2-5f5d-9c90-486fa4622982",
        "a1ebc792-4a47-5429-bcf1-2a63534570d1",
        "a33513b6-6cc1-5aaf-b574-687c7ed3510e",
        "a5c9c8e2-3066-53e0-a2c6-77a80a0facc6",
        "b93bf191-dcac-5125-bf0b-256aefec996d",
        "c7e61a5e-3960-5929-89e1-6e4aec96c631",
        "d3ea7208-393c-5a66-85f1-a72bc0785e91",
        "e7dc7725-c0b2-5c63-af94-55438e426d80",
        "f2b93d1a-7c33-5a9e-be4d-f7d0dadec047",
        "fa6783df-1e33-58f7-b835-9b05c83eb4d4",
    }
)


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


class FrozenConstructionMasterV12Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_exact_accounting_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
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
                rebuilt = Path(temporary) / "bundle"
                write_construction_master(DEFINITION, rebuilt)
                for filename in (
                    "ATTRIBUTION.txt",
                    "README.md",
                    "construction-master.csv",
                    "construction-master.jsonl",
                    "coverage.json",
                    "manifest.json",
                    "manifest.sha256",
                ):
                    self.assertEqual(
                        (rebuilt / filename).read_bytes(),
                        (BUNDLE / filename).read_bytes(),
                    )

        self.assertEqual(
            hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(manifest["row_counts"]["total"], 109_096)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 304, "B": 6_298, "C": 102_494},
        )

        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108_792)
        self.assertEqual(
            coverage["construction_arithmetic"]["statuses"],
            {
                "announced": 3,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 15,
                "permitted": 3,
                "proposed": 22,
                "shell": 6,
                "site_preparation": 9,
                "under_construction": 215,
            },
        )
        self.assertEqual(
            coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            TIER_A_PROJECTION_SHA256,
        )
        self.assertEqual(
            coverage["evidence_observations"],
            {
                "annual_energy": 73,
                "operating_model": 2,
                "pue": 2,
                "source_evidence_records": 115_388,
                "typed_capacity_excluding_annual_energy_and_pue": 233,
                "untyped_capacity_statements": 23,
                "workload": 103,
            },
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in BUNDLE.iterdir()
            )
        )

        manifest_paths = {
            checkpoint["path"] for checkpoint in manifest["input_checkpoints"]
        }
        for marker in (
            "releases/2026-07-19-open-seed-v30/manifest.json",
            "federated_indexes/2026-07-19-public-open-v10/manifest.json",
            "audits/2026-07-19-public-open-coverage-v11/manifest.json",
        ):
            self.assertIn(marker, manifest_paths)
        readme = (BUNDLE / "README.md").read_text()
        attribution = (BUNDLE / "ATTRIBUTION.txt").read_text()
        for marker in ("33", "Unknown030", "federation-v10", "coverage-audit-v11"):
            self.assertIn(marker, readme)
        for marker in (
            "AtlasEdge",
            "City of Independence",
            "Pure DC",
            "Telekom Malaysia",
        ):
            self.assertIn(marker, attribution)

    def test_exact_v30_additions_preserve_every_shared_row(self) -> None:
        previous = _release_rows(PREVIOUS_BUNDLE, "epoch-official-open-seed-v20")
        current = _release_rows(BUNDLE, "epoch-official-open-seed-v30")
        self.assertEqual(set(current) - set(previous), ADDITION_IDS)
        self.assertEqual(set(previous) - set(current), set())

        release_fields = {
            "artifact_id",
            "artifact_path",
            "artifact_sha256",
            "manifest_sha256",
            "release_id",
        }
        for record_id in sorted(previous):
            before = deepcopy(previous[record_id])
            after = deepcopy(current[record_id])
            before.pop("row_id")
            after.pop("row_id")
            for field in release_fields:
                before["source"].pop(field)
                after["source"].pop(field)
            self.assertEqual(after, before)

        additions = [current[record_id] for record_id in sorted(ADDITION_IDS)]
        self.assertEqual(
            Counter(row["entity"]["kind"] for row in additions),
            Counter({"project": 33}),
        )
        self.assertEqual(
            Counter(row["lifecycle"]["normalized_status"] for row in additions),
            Counter(
                {
                    "under_construction": 29,
                    "permitted": 1,
                    "proposed": 1,
                    "shell": 1,
                    "site_preparation": 1,
                }
            ),
        )
        self.assertEqual(
            Counter(row["source"]["source_license"] for row in additions),
            Counter({"all-rights-reserved": 32, "public-government-record": 1}),
        )
        self.assertEqual(sum(len(row["source_evidence"]) for row in additions), 37)
        self.assertEqual(
            sum(row["entity"]["latitude"] is not None for row in additions), 1
        )
        self.assertTrue(
            all(
                row["tier"] == "A"
                and row["construction"]["source_supported"]
                and not row["construction"]["verified"]
                and row["annual_energy_observations"] == []
                and row["pue_observations"] == []
                and row["untyped_capacity_statements"] == []
                and row["operating_model_observation"] is None
                for row in additions
            )
        )
        self.assertEqual(
            Counter(
                (observation["metric"], observation["stage"])
                for row in additions
                for observation in row["capacity_observations"]
            ),
            Counter({("critical_it_mw", "planned"): 5}),
        )
        self.assertEqual(
            Counter(
                observation["workload"]
                for row in additions
                for observation in row["workload_observations"]
            ),
            Counter({"ai_specialized_unspecified": 4, "crypto_mining": 1}),
        )

    def test_unknown030_and_frozen_review_lineage_are_unchanged(self) -> None:
        rows = [
            row
            for row in _jsonl_rows(BUNDLE)
            if row["observation_kind"] == "sentinel_analyst_change_review"
        ]
        self.assertEqual(
            Counter(row["satellite_links"][0]["batch_artifact_id"] for row in rows),
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
                row["satellite_links"][0]["catalog_batch_artifact_id"]
                == "satellite-global-open-v3-unknown-030"
                for row in rows
                if "unknown-" in row["satellite_links"][0]["batch_artifact_id"]
            )
        )

    def test_contract_and_cumulative_source_allowlist_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []
        for field_path, message in (
            (
                ("expected_counts", "tier_a_rows"),
                "v12 count or Tier-A projection contract changed",
            ),
            (
                ("inputs", "tier_a_releases", 0, "manifest", "sha256"),
                "v12 open-seed v30 checkpoints changed",
            ),
            (
                ("inputs", "coverage_context", "audit_manifest", "sha256"),
                "v12 federation or coverage-audit context changed",
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
        changed["generated_at"] = "2026-07-19T21:45:01Z"
        changes.append((changed, "v12 generation timestamp changed"))

        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v12-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        release = ROOT / "releases" / "2026-07-19-open-seed-v30"
        with (release / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source, (release / "evidence.csv").open(
            newline="", encoding="utf-8"
        ) as evidence_source:
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v12_open_seed_source_allowlist(rows, evidence)

        changed_evidence = deepcopy(evidence)
        selected_id = rows[0]["status_evidence_id"]
        changed_evidence[selected_id]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v12 open-seed source allowlist changed"
        ):
            _validate_v12_open_seed_source_allowlist(rows, changed_evidence)

        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["source_family"] = "unexpected_source_root"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v12 open-seed source allowlist changed"
        ):
            _validate_v12_open_seed_source_allowlist(rows, changed_evidence)

        changed_rows = deepcopy(rows)
        government_row = next(
            row
            for row in changed_rows
            if row["source_license"] == "public-government-record"
        )
        government_row["source_license"] = "unexpected-license"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v12 open-seed source allowlist changed"
        ):
            _validate_v12_open_seed_source_allowlist(changed_rows, evidence)


if __name__ == "__main__":
    unittest.main()
