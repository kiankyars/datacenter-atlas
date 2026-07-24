from __future__ import annotations

from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map import (
    ConstructionMapError,
    is_frozen_map,
    validate_construction_map,
    validate_map_definition,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "construction-map-2026-07-19-public-open-v11.json"
)
DEFINITION = ROOT / "sources" / "construction-map-2026-07-19-public-open-v12.json"
MASTER_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v12.json"
)
PREVIOUS_MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v11"
MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v12"
PREVIOUS_MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v11"
MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v12"

DEFINITION_SHA256 = (
    "aa94b20bd4e3264ead3756fd21e31fcea0a26fd8084e7511f970a9aad34644a2"
)
MANIFEST_SHA256 = (
    "2e5d68db464ef88cea1df4477b8adc75a4a79b197c246adeaa8771cef65756e7"
)
BUNDLE_INVENTORY_SHA256 = (
    "c091270356dc41d9b755f7790590d151528c933d0b829ee17efa83ab3b43412f"
)
MAPPED_ADDITION_ID = "3941c42e-216d-52fa-b0d8-d7555b441a1a"


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def _master_release_ids(master: Path, artifact_id: str) -> set[str]:
    result: set[str] = set()
    with (master / "construction-master.jsonl").open() as source:
        for raw_line in source:
            row = json.loads(raw_line)
            if row["source"]["artifact_id"] == artifact_id:
                result.add(row["source"]["record_id"])
            elif result:
                break
    return result


def _map_release_rows(bundle: Path, artifact_id: str) -> dict[str, dict]:
    index = json.loads(
        gzip.decompress((bundle / "construction-map-index.json.gz").read_bytes())
    )
    return {
        row["source_record_id"]: row
        for row in (
            dict(zip(index["fields"], values, strict=True))
            for values in index["rows"]
        )
        if row["source_artifact_id"] == artifact_id
    }


class FrozenConstructionMapV12Tests(unittest.TestCase):
    def test_frozen_map_reproduces_exact_projection_offline(self) -> None:
        definition_raw = DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(), DEFINITION_SHA256
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6_479)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 199, "B": 6_280, "C": 102_494}
        )
        self.assertEqual(expected["mapped_rows"], 108_973)
        self.assertEqual(expected["master_rows"], 109_096)
        self.assertEqual(expected["unmapped_rows"], 123)

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
            manifest = validate_construction_map(
                MAP,
                master_directory=MASTER,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=DEFINITION,
                reproduce=True,
            )

        self.assertEqual(
            hashlib.sha256((MAP / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(MAP), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(manifest["master"]["rows"], 109_096)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108_973,
        )
        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(
            coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"]
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in MAP.iterdir()
            )
        )
        self.assertTrue(is_frozen_map(MAP))

    def test_one_v30_addition_maps_and_thirty_two_remain_explicitly_unmapped(
        self,
    ) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        definition = json.loads(DEFINITION.read_text())
        previous_unmapped = set(
            previous_definition["expected_projection"]["unmapped_source_record_ids"]
        )
        current_unmapped = set(
            definition["expected_projection"]["unmapped_source_record_ids"]
        )
        previous_master_ids = _master_release_ids(
            PREVIOUS_MASTER, "epoch-official-open-seed-v20"
        )
        current_master_ids = _master_release_ids(
            MASTER, "epoch-official-open-seed-v30"
        )
        additions = current_master_ids - previous_master_ids
        self.assertEqual(len(additions), 33)
        self.assertEqual(previous_master_ids - current_master_ids, set())
        self.assertEqual(
            current_unmapped - previous_unmapped,
            additions - {MAPPED_ADDITION_ID},
        )
        self.assertEqual(previous_unmapped - current_unmapped, set())

        previous_rows = _map_release_rows(
            PREVIOUS_MAP, "epoch-official-open-seed-v20"
        )
        current_rows = _map_release_rows(MAP, "epoch-official-open-seed-v30")
        self.assertEqual(set(current_rows) - set(previous_rows), {MAPPED_ADDITION_ID})
        self.assertEqual(set(previous_rows) - set(current_rows), set())
        ignored = {"row_id", "source_artifact_id", "source_release_id"}
        for record_id in sorted(previous_rows):
            self.assertEqual(
                {
                    key: value
                    for key, value in current_rows[record_id].items()
                    if key not in ignored
                },
                {
                    key: value
                    for key, value in previous_rows[record_id].items()
                    if key not in ignored
                },
            )

        addition = current_rows[MAPPED_ADDITION_ID]
        self.assertEqual(addition["name"], "maincubes BER02")
        self.assertEqual((addition["latitude"], addition["longitude"]), (52.5935, 12.8929999))
        self.assertEqual(addition["tier"], "A")
        self.assertEqual(addition["entity_kind"], "project")
        self.assertEqual(addition["normalized_status"], "under_construction")
        self.assertTrue(addition["construction_source_supported"])
        self.assertFalse(addition["construction_verified"])
        self.assertEqual(addition["capacity_observations"], [])
        self.assertEqual(addition["annual_energy_observations"], [])
        self.assertEqual(addition["pue_observations"], [])
        self.assertEqual(addition["untyped_capacity_statements"], [])
        self.assertEqual(addition["workloads"], [])
        self.assertIsNone(addition["operating_model"])

        self.assertEqual(
            Counter(
                row["normalized_status"]
                for record_id, row in current_rows.items()
                if record_id in additions
            ),
            Counter({"under_construction": 1}),
        )

    def test_strict_definition_guardrails_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []
        changed = deepcopy(document)
        changed["expected_projection"]["mapped_rows"] -= 1
        changes.append((changed, "map definition projection arithmetic differs"))
        changed = deepcopy(document)
        changed["master"]["manifest"]["sha256"] = "0" * 64
        changes.append((changed, "master manifest checkpoint differs"))
        changed = deepcopy(document)
        changed["map_id"] = "changed-map-id"
        changes.append((changed, "map definition master identity changed"))

        for index, (changed, message) in enumerate(changes):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DEFINITION.parent,
                prefix=f"changed-v12-map-{index}-",
                suffix=".json",
            ) as temporary:
                temporary.write(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                temporary.flush()
                with self.assertRaisesRegex(ConstructionMapError, message):
                    validate_map_definition(
                        temporary.name,
                        master_directory=MASTER,
                        master_definition_path=MASTER_DEFINITION,
                    )


if __name__ == "__main__":
    unittest.main()
