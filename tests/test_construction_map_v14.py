from __future__ import annotations

import base64
from copy import deepcopy
import gzip
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_map import (
    ConstructionMapError,
    FIELDS,
    is_frozen_map,
    validate_construction_map,
    validate_map_definition,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "construction-map-2026-07-19-public-open-v13.json"
)
DEFINITION = ROOT / "sources" / "construction-map-2026-07-19-public-open-v14.json"
MASTER_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v14.json"
)
PREVIOUS_MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v13"
MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v14"
PREVIOUS_MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v13"
MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v14"

DEFINITION_SHA256 = (
    "7ad7320bbbb8d1ae4bef56363177fe904891be9527e35e31eedc9103b1122db9"
)
MANIFEST_SHA256 = (
    "85f102967b8a6329c6d4466e61d1773132ee71b92cad05fc014b475eb0ef75f1"
)
BUNDLE_INVENTORY_SHA256 = (
    "b69c784bd3b9f12c4a0c46cbd56784cc2aa15b332febe98764ebb3f77bfa7681"
)
MASTER_DEFINITION_SHA256 = (
    "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4"
)
MASTER_MANIFEST_SHA256 = (
    "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b"
)
MASTER_BUNDLE_INVENTORY_SHA256 = (
    "4b2ce6298788a6af9b5df90c4148b640fafdcb39ad8c0044d35832b8cd3bee60"
)
MASTER_TIER_A_PROJECTION_SHA256 = (
    "159584ad2097da71383831d4fad4983045d8b740106e32a60329b3d1fe650e4d"
)
TEMPLATE_SHA256 = (
    "c9d2005bee61e66e99ebfe64df9064697a97ee3a98cef6f282726b4fffd5af3c"
)
ADDITION_IDS = frozenset(
    {
        "3fa68a6a-4362-5a39-b676-751d205f134d",
        "5bfb4ad8-a8f4-5937-9242-a96f9292c385",
        "dcd52b51-9cad-59fc-ae4a-ff6280372dda",
        "fe92035e-3a00-5a85-b009-34fe9c2c545e",
    }
)


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


def _master_release_rows(master: Path, artifact_id: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    with (master / "construction-master.jsonl").open() as source:
        for raw_line in source:
            row = json.loads(raw_line)
            if row["source"]["artifact_id"] == artifact_id:
                result[row["source"]["record_id"]] = row
            elif result:
                break
    return result


def _map_rows(bundle: Path):
    decoder = json.JSONDecoder()
    marker = '"rows":['
    with gzip.open(
        bundle / "construction-map-index.json.gz", mode="rt", encoding="utf-8"
    ) as source:
        buffer = source.read(1024 * 1024)
        position = buffer.find(marker)
        if position < 0:
            raise AssertionError("map index row array marker is absent")
        position += len(marker)
        while True:
            while position < len(buffer) and buffer[position] in " \n\r\t,":
                position += 1
            if position >= len(buffer):
                more = source.read(1024 * 1024)
                if not more:
                    raise AssertionError("map index row array is truncated")
                buffer = buffer[position:] + more
                position = 0
                continue
            if buffer[position] == "]":
                return
            try:
                row, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                more = source.read(1024 * 1024)
                if not more:
                    raise AssertionError("map index row is truncated")
                buffer = buffer[position:] + more
                position = 0
                continue
            if not isinstance(row, list) or len(row) != len(FIELDS):
                raise AssertionError("map index row schema differs")
            yield row
            position = end
            if position > 4 * 1024 * 1024:
                buffer = buffer[position:]
                position = 0


def _map_release_rows(bundle: Path, artifact_id: str) -> dict[str, dict]:
    return {
        row["source_record_id"]: row
        for row in (
            dict(zip(FIELDS, values, strict=True)) for values in _map_rows(bundle)
        )
        if row["source_artifact_id"] == artifact_id
    }


class FrozenConstructionMapV14Tests(unittest.TestCase):
    def test_frozen_map_reproduces_exact_projection_offline(self) -> None:
        definition_raw = DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (
                json.dumps(definition, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode(),
        )
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256(MASTER_DEFINITION.read_bytes()).hexdigest(),
            MASTER_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((MASTER / "manifest.json").read_bytes()).hexdigest(),
            MASTER_MANIFEST_SHA256,
        )
        self.assertEqual(
            _bundle_inventory_sha256(MASTER), MASTER_BUNDLE_INVENTORY_SHA256
        )
        master_coverage = json.loads((MASTER / "coverage.json").read_text())
        self.assertEqual(
            master_coverage["construction_arithmetic"][
                "tier_a_arithmetic_projection_sha256"
            ],
            MASTER_TIER_A_PROJECTION_SHA256,
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6_479)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 199, "B": 6_280, "C": 102_494}
        )
        self.assertEqual(expected["mapped_rows"], 108_973)
        self.assertEqual(expected["master_rows"], 109_111)
        self.assertEqual(expected["unmapped_rows"], 138)

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
            manifests = [
                validate_construction_map(
                    MAP,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    reproduce=True,
                )
                for _ in range(2)
            ]
        self.assertEqual(manifests[0], manifests[1])
        manifest = manifests[0]

        self.assertEqual(
            hashlib.sha256((MAP / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(MAP), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(manifest["master"]["rows"], 109_111)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108_973,
        )
        coverage = json.loads((MAP / "coverage.json").read_text())
        self.assertEqual(
            coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"]
        )
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["entity_merges_created"])
        self.assertTrue(
            coverage["scope"]["review_and_discovery_rows_remain_unpromoted"]
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertEqual(
            {entry.name for entry in MAP.iterdir()},
            {
                "ATTRIBUTION.txt",
                "README.md",
                "construction-map-index.json.gz",
                "construction-map.html",
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
                for entry in MAP.iterdir()
            )
        )
        self.assertTrue(is_frozen_map(MAP))

        compressed = (MAP / "construction-map-index.json.gz").read_bytes()
        self.assertEqual(compressed[:4], b"\x1f\x8b\x08\x00")
        self.assertEqual(compressed[4:8], b"\0" * 4)
        self.assertEqual(compressed[9], 255)
        template_path = ROOT / "web" / "construction-map-template.html"
        template = template_path.read_text()
        self.assertEqual(
            hashlib.sha256(template_path.read_bytes()).hexdigest(), TEMPLATE_SHA256
        )
        self.assertEqual(
            definition["template"],
            json.loads(PREVIOUS_DEFINITION.read_text())["template"],
        )
        expected_html = template.replace(
            "__CONSTRUCTION_MAP_GZIP_BASE64__",
            base64.b64encode(compressed).decode("ascii"),
        ).encode()
        self.assertEqual((MAP / "construction-map.html").read_bytes(), expected_html)
        self.assertEqual(
            (MAP / "ATTRIBUTION.txt").read_bytes(),
            (PREVIOUS_MAP / "ATTRIBUTION.txt").read_bytes(),
        )

    def test_v33_additions_are_all_explicitly_unmapped(self) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        definition = json.loads(DEFINITION.read_text())
        previous_unmapped = set(
            previous_definition["expected_projection"]["unmapped_source_record_ids"]
        )
        current_unmapped = set(
            definition["expected_projection"]["unmapped_source_record_ids"]
        )
        previous_ids = _master_release_ids(
            PREVIOUS_MASTER, "epoch-official-open-seed-v32"
        )
        current_ids = _master_release_ids(MASTER, "epoch-official-open-seed-v33")
        additions = current_ids - previous_ids
        self.assertEqual(additions, ADDITION_IDS)
        self.assertEqual(previous_ids - current_ids, set())
        self.assertEqual(current_unmapped - previous_unmapped, additions)
        self.assertEqual(previous_unmapped - current_unmapped, set())

        previous_rows = _map_release_rows(
            PREVIOUS_MAP, "epoch-official-open-seed-v32"
        )
        current_rows = _map_release_rows(MAP, "epoch-official-open-seed-v33")
        self.assertEqual(set(previous_rows), set(current_rows))
        self.assertEqual(set(current_rows) & additions, set())
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

        current_master_rows = _master_release_rows(
            MASTER, "epoch-official-open-seed-v33"
        )
        self.assertTrue(
            all(
                current_master_rows[record_id]["entity"]["latitude"] is None
                and current_master_rows[record_id]["entity"]["longitude"] is None
                for record_id in additions
            )
        )

        ignored_indexes = {
            FIELDS.index("row_id"),
            FIELDS.index("source_artifact_id"),
            FIELDS.index("source_release_id"),
        }
        sentinel = object()
        compared = 0
        release_envelope_changes = 0
        for previous_values, current_values in zip_longest(
            _map_rows(PREVIOUS_MAP), _map_rows(MAP), fillvalue=sentinel
        ):
            self.assertIsNot(previous_values, sentinel)
            self.assertIsNot(current_values, sentinel)
            self.assertEqual(
                [
                    value
                    for index, value in enumerate(current_values)
                    if index not in ignored_indexes
                ],
                [
                    value
                    for index, value in enumerate(previous_values)
                    if index not in ignored_indexes
                ],
            )
            release_envelope_changes += current_values != previous_values
            compared += 1
        self.assertEqual(compared, 108_973)
        self.assertEqual(release_envelope_changes, 80)

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
                prefix=f"changed-v14-map-{index}-",
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
