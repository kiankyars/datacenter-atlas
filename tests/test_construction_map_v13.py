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
    ROOT / "sources" / "construction-map-2026-07-19-public-open-v12.json"
)
DEFINITION = ROOT / "sources" / "construction-map-2026-07-19-public-open-v13.json"
MASTER_DEFINITION = (
    ROOT / "sources" / "construction-master-2026-07-19-public-open-v13.json"
)
PREVIOUS_MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v12"
MASTER = ROOT / "construction_master" / "2026-07-19-public-open-v13"
PREVIOUS_MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v12"
MAP = ROOT / "construction_maps" / "2026-07-19-public-open-v13"

DEFINITION_SHA256 = (
    "56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483"
)
MANIFEST_SHA256 = (
    "0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49"
)
BUNDLE_INVENTORY_SHA256 = (
    "2b046d96219bb989baccb5004dba3cc8d84231dca00fead3c1e4796c266bc5ea"
)
MASTER_DEFINITION_SHA256 = (
    "6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07"
)
MASTER_MANIFEST_SHA256 = (
    "d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0"
)
MASTER_BUNDLE_INVENTORY_SHA256 = (
    "95ae7507ef0baafe5b82d231b48cfa876023cf464832b5a3f7ed34e7320949a8"
)
MASTER_TIER_A_PROJECTION_SHA256 = (
    "0bdebf32e3df7af34aa1a234c90c1da8c2796ae9efb3b41e50b0bbb01d5b097c"
)
TEMPLATE_SHA256 = (
    "c9d2005bee61e66e99ebfe64df9064697a97ee3a98cef6f282726b4fffd5af3c"
)
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


class FrozenConstructionMapV13Tests(unittest.TestCase):
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
        self.assertEqual(expected["master_rows"], 109_107)
        self.assertEqual(expected["unmapped_rows"], 134)

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
        self.assertEqual(manifest["master"]["rows"], 109_107)
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

    def test_v32_additions_are_all_explicitly_unmapped(self) -> None:
        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text())
        definition = json.loads(DEFINITION.read_text())
        previous_unmapped = set(
            previous_definition["expected_projection"]["unmapped_source_record_ids"]
        )
        current_unmapped = set(
            definition["expected_projection"]["unmapped_source_record_ids"]
        )
        previous_ids = _master_release_ids(
            PREVIOUS_MASTER, "epoch-official-open-seed-v30"
        )
        current_ids = _master_release_ids(MASTER, "epoch-official-open-seed-v32")
        additions = current_ids - previous_ids
        self.assertEqual(additions, ADDITION_IDS)
        self.assertEqual(previous_ids - current_ids, set())
        self.assertEqual(current_unmapped - previous_unmapped, additions)
        self.assertEqual(previous_unmapped - current_unmapped, set())

        previous_rows = _map_release_rows(
            PREVIOUS_MAP, "epoch-official-open-seed-v30"
        )
        current_rows = _map_release_rows(MAP, "epoch-official-open-seed-v32")
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
            MASTER, "epoch-official-open-seed-v32"
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
                prefix=f"changed-v13-map-{index}-",
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
