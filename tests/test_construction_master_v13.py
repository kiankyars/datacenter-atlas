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
    _definition,
    _validate_v13_open_seed_source_allowlist,
    validate_construction_master,
    write_construction_master,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v12.json"
)
DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v13.json"
)
PREVIOUS_BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v12"
BUNDLE = ROOT / "construction_master" / "2026-07-19-public-open-v13"

DEFINITION_SHA256 = (
    "6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07"
)
MANIFEST_SHA256 = (
    "d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0"
)
BUNDLE_INVENTORY_SHA256 = (
    "95ae7507ef0baafe5b82d231b48cfa876023cf464832b5a3f7ed34e7320949a8"
)
INPUT_CHECKPOINT_INVENTORY_SHA256 = (
    "8d2c94f6b4d5b046111b1e928ea1255dacf3c302d8e8b0ac273b1b666873a42c"
)
TIER_A_PROJECTION_SHA256 = (
    "0bdebf32e3df7af34aa1a234c90c1da8c2796ae9efb3b41e50b0bbb01d5b097c"
)
ACCEPTED_DEFINITION_SHA256 = {
    "sources/open-seed-2026-07-19-v32.json": (
        "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
    ),
    "sources/federation-2026-07-19-public-open-v11.json": (
        "e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c"
    ),
    "sources/coverage-audit-2026-07-19-public-open-v12.json": (
        "1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f"
    ),
}
ACCEPTED_MANIFEST_SHA256 = {
    "releases/2026-07-19-open-seed-v32/manifest.json": (
        "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
    ),
    "federated_indexes/2026-07-19-public-open-v11/manifest.json": (
        "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
    ),
    "audits/2026-07-19-public-open-coverage-v12/manifest.json": (
        "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
    ),
}
ADDITION_IDS = frozenset(
    {
        "079a08b1-db98-5324-a63f-ee646860f4a4",
        "0de2b9bf-b7e7-5494-ad33-fb0a28cd38e2",
        "13a5c5e7-aff5-5cbb-9d26-df1cf829a6a4",
        "570e537d-5091-54e0-99eb-1cf4032953fc",
        "5d697e53-fb66-5a24-8f41-2f386595f485",
        "75e506d4-a334-5c02-ac02-9cab81f5d017",
        "8966a315-7510-5754-a5e4-71849896b96b",
        "b547d033-e33f-5535-9d27-eedb4cab5735",
        "d403e092-ae3a-5457-b28f-617b135b9f3f",
        "df7495d6-73d4-58a3-a357-ef56012d92d8",
        "e83599ba-c2cc-5903-a044-743f73f51280",
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


class FrozenConstructionMasterV13Tests(unittest.TestCase):
    def test_frozen_bundle_validates_and_reproduces_twice_offline(self) -> None:
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
                rebuilt = Path(temporary) / "bundle"
                write_construction_master(DEFINITION, rebuilt)
                for filename in sorted(entry.name for entry in BUNDLE.iterdir()):
                    self.assertEqual(
                        (rebuilt / filename).read_bytes(),
                        (BUNDLE / filename).read_bytes(),
                    )

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
        self.assertEqual(manifest["row_counts"]["total"], 109_107)
        self.assertEqual(
            manifest["row_counts"]["by_tier"],
            {"A": 315, "B": 6_298, "C": 102_494},
        )

        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertEqual(coverage["row_counts"]["review_only"], 108_792)
        self.assertEqual(
            coverage["construction_arithmetic"],
            {
                "rows": 315,
                "source_supported_rows": 315,
                "statuses": {
                    "announced": 3,
                    "civil_works": 2,
                    "expansion": 27,
                    "foundations": 2,
                    "mep_electrical": 15,
                    "permitted": 3,
                    "proposed": 22,
                    "shell": 6,
                    "site_preparation": 9,
                    "under_construction": 226,
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
                "source_evidence_records": 115_402,
                "typed_capacity_excluding_annual_energy_and_pue": 233,
                "untyped_capacity_statements": 23,
                "workload": 103,
            },
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["benchmark_parity_claimed"])

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

    def test_v32_additions_and_every_shared_seed_row_are_exact(self) -> None:
        previous = _release_rows(PREVIOUS_BUNDLE, "epoch-official-open-seed-v30")
        current = _release_rows(BUNDLE, "epoch-official-open-seed-v32")
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
            Counter({"project": 11}),
        )
        self.assertEqual(
            Counter(row["lifecycle"]["normalized_status"] for row in additions),
            Counter({"under_construction": 11}),
        )
        self.assertEqual(
            Counter(row["source"]["source_license"] for row in additions),
            Counter({"all-rights-reserved": 11}),
        )
        self.assertEqual(sum(len(row["source_evidence"]) for row in additions), 14)
        self.assertTrue(
            all(
                row["tier"] == "A"
                and row["entity"]["latitude"] is None
                and row["entity"]["longitude"] is None
                and row["construction"]["source_supported"]
                and not row["construction"]["verified"]
                and row["capacity_observations"] == []
                and row["annual_energy_observations"] == []
                and row["pue_observations"] == []
                and row["untyped_capacity_statements"] == []
                and row["workload_observations"] == []
                and row["operating_model_observation"] is None
                and row["satellite_links"] == []
                and row["resolution_advisories"] == []
                and row["fusion_overlay"] is None
                for row in additions
            )
        )

        release = ROOT / "releases" / "2026-07-19-open-seed-v32"
        with (release / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source:
            source_additions = [
                row for row in csv.DictReader(source) if row["entity_id"] in ADDITION_IDS
            ]
        self.assertEqual(len(source_additions), 11)
        self.assertTrue(
            all(
                row["owner"] == ""
                and row["operator"] == ""
                and row["users"] == ""
                and row["operating_model"] == ""
                and row["workloads_json"] == "[]"
                and row["capacity_estimates_json"] == "[]"
                for row in source_additions
            )
        )

    def test_all_nonseed_rows_and_review_lineage_are_byte_exact(self) -> None:
        before_path = PREVIOUS_BUNDLE / "construction-master.jsonl"
        after_path = BUNDLE / "construction-master.jsonl"
        sentinel = object()
        with before_path.open("rb") as before, after_path.open("rb") as after:
            for _ in range(184):
                next(before)
            for _ in range(195):
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
            "releases/2026-07-19-open-seed-v32/manifest.json",
            "federated_indexes/2026-07-19-public-open-v11/manifest.json",
            "audits/2026-07-19-public-open-coverage-v12/manifest.json",
        ):
            self.assertIn(marker, manifest_paths)
        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        self.assertNotIn(
            "public-open-coverage-v12",
            coverage["row_counts"]["by_source_artifact"],
        )
        self.assertNotIn(
            "public-open-federation-v11",
            coverage["row_counts"]["by_source_artifact"],
        )

    def test_v13_contract_and_cumulative_source_allowlist_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []
        for field_path, message in (
            (
                ("expected_counts", "tier_a_rows"),
                "v13 count or Tier-A projection contract changed",
            ),
            (
                ("inputs", "tier_a_releases", 0, "manifest", "sha256"),
                "v13 open-seed v32 checkpoints changed",
            ),
            (
                ("inputs", "coverage_context", "audit_manifest", "sha256"),
                "v13 federation or coverage-audit context changed",
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
        changed["generated_at"] = "2026-07-19T22:50:01Z"
        changes.append((changed, "v13 generation timestamp changed"))

        with tempfile.TemporaryDirectory() as temporary:
            for index, (changed, message) in enumerate(changes):
                path = Path(temporary) / f"changed-v13-{index}.json"
                path.write_text(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                with self.assertRaisesRegex(ConstructionMasterError, message):
                    _definition(path)

        release = ROOT / "releases" / "2026-07-19-open-seed-v32"
        with (release / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as source, (release / "evidence.csv").open(
            newline="", encoding="utf-8"
        ) as evidence_source:
            rows = list(csv.DictReader(source))
            evidence = {
                row["evidence_id"]: row for row in csv.DictReader(evidence_source)
            }
        _validate_v13_open_seed_source_allowlist(rows, evidence)

        selected_id = rows[0]["status_evidence_id"]
        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["publisher"] = "Unexpected Publisher"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v13 open-seed source allowlist changed"
        ):
            _validate_v13_open_seed_source_allowlist(rows, changed_evidence)

        changed_evidence = deepcopy(evidence)
        changed_evidence[selected_id]["source_family"] = "unexpected_source_root"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v13 open-seed source allowlist changed"
        ):
            _validate_v13_open_seed_source_allowlist(rows, changed_evidence)

        changed_rows = deepcopy(rows)
        changed_rows[0]["source_license"] = "unexpected-license"
        with self.assertRaisesRegex(
            ConstructionMasterError, "v13 open-seed source allowlist changed"
        ):
            _validate_v13_open_seed_source_allowlist(changed_rows, evidence)


if __name__ == "__main__":
    unittest.main()
