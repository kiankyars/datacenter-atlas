from __future__ import annotations

from contextlib import ExitStack, contextmanager
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
from typing import Any, Iterator
import unittest
from unittest.mock import patch
import urllib.request

import rasterio

try:
    from datacenter_atlas.datacenter_atlas import (
        satellite_change_preparation_v1 as v1,
    )
except ModuleNotFoundError:
    from datacenter_atlas import satellite_change_preparation_v1 as v1
from datacenter_atlas.satellite_change import REQUIRED_ASSETS, canonical_sha256
from datacenter_atlas.satellite_change_mosaic import ItemBinding, grid_from_item
from datacenter_atlas.satellite_change_preparation_v1 import (
    CLAIM_CONSTRAINTS,
    RELEASE_FILES,
    RUNTIME,
    SatelliteChangePreparationV1Error,
    validate_satellite_change_preparation_v1,
    write_satellite_change_preparation_v1,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "sources/satellite-change-preparation-2026-07-20-open-seed-v57-active-v1.json"
)
RELEASE = (
    ROOT
    / "satellite_change_preparation/2026-07-20-open-seed-v57-active-v1"
)
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v57"
CATALOG = ROOT / "satellite_review_runs/2026-07-20-open-seed-v57-active-001"
CATALOG_MANIFEST = CATALOG / "batch-manifest.json"
CLI = ROOT / "scripts/build_satellite_change_preparation_v1.py"
MODULE = ROOT / "datacenter_atlas/satellite_change_preparation_v1.py"
OUTER_SHIM = ROOT / "satellite_change_preparation_v1.py"

DEFINITION_SHA256 = "9700380bf1e45110d4b4efa8538ce3bc98793a79343ddfca018fc73ef962f8d8"
MODULE_SHA256 = "2e0c3e462fa0a6a6c4d59290444b17dca6ee075c7cf648ebeb349cd1040988c7"
OUTER_SHIM_SHA256 = "0f14ddddf49d59672efe930edf29bfd5d36108b6ebd071e34a1634cd6caaaa74"
CLI_SHA256 = "9f52ed3be4fb58977691a1ad4e92aee120d95342b7a366250c6232ab5f5db55a"
TREE_SHA256 = "6ba201e2c634a98816fdca5d6cdef2f18b2d04a516a38d3d76370fbb74cd72b6"
BINDING_INVENTORY_SHA256 = (
    "ac81ec456bc75e7dfa9d0ad78a62b02eb1160fc600ea889a0e3dd67e25665d51"
)
BLOCKED_REASON_INVENTORY_SHA256 = (
    "e98d684b547e7098fed3f42f145f9938b5a912796cb7a46455c7f9d9bf7bd74b"
)
NO_SCENE_REASON_INVENTORY_SHA256 = (
    "9aab605d03fb1cde469822817e9c1d3fd3dc7d746b8a9eb524d4071ccadfa537"
)
MULTI_READY_ITEM_INVENTORY_SHA256 = (
    "455da23f6f701a9b95f82d9e968e3894d437fedf90cc4c3edd76fede7dafb182"
)

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        128,
        "b781266a8d13d79f2530fe7085d9f651b9f4e55afae1deb43c64ae998e6e459e",
    ),
    "README.md": (
        741,
        "783c2ca924a89a196e980e057f87732321e0ca53850d94cfebbbd9ff15b84d57",
    ),
    "aoi-relationships.jsonl": (
        28_442,
        "95081255b2361ff1b05fa32d895926f0e0013ce7a346a1cf300262355fd9c5fe",
    ),
    "manifest.json": (
        5_885,
        "84073fc695a3ef500bd11d5077935083a7869cd4adb30db5342f6c0e215011ff",
    ),
    "manifest.sha256": (
        80,
        "3edd33ed470a1e5a830c9afc7355dab1ad93d01b5d4d24875e99eeeb5e6e78a9",
    ),
    "multi-tile-blocked.jsonl": (
        63_682,
        "37dd36ee9c0c2785783c21909109820e34cd3490e0120eb03594fbe2b986d108",
    ),
    "multi-tile-ready.jsonl": (
        116_276,
        "5d9745f40fd495d129f08e8acd8a1dba76dd10ba6a800ec05dde33d0bcdd5ef1",
    ),
    "single-tile-ready.jsonl": (
        979_200,
        "c98d73b20411ac1fc7ee065bd6d34f35839ddb8e679c389c068f181eecd12e6c",
    ),
    "source-inventory.json": (
        83_983,
        "288836e9a6b28968b506a15eb9c6595aba750d23b00fb781275e1fce9c0f1071",
    ),
    "summary.json": (
        1_393,
        "430d4ba109e0bb600a8c76ac9b3f3c23f995fe52d3909a4334e010d5ea952da9",
    ),
    "terminal-no-scene.jsonl": (
        4_587,
        "44bd7849494f9b4820fc579d46bed361ae082f754a019ecfd8ee68a2fcc7f104",
    ),
}

SUMMARY = {
    "active_jobs": 87,
    "distinct_aois": 84,
    "jobs_in_shared_aois": 6,
    "multi_tile_blocked": 5,
    "multi_tile_ready": 6,
    "partition_inventory_sha256": (
        "2b68215d023217735f32a5920c22406adb25e47ba83d744ff9f6de45db11e809"
    ),
    "shared_aoi_groups": 3,
    "single_tile_ready": 74,
    "terminal_no_scene": 2,
}

MULTI_READY = {
    "satq-54c6402eb93d14f1ea754e66": (
        3,
        ("S2B_12SUB_20240605_0_L2A", "S2B_12SVB_20240605_0_L2A"),
        ("S2B_12SUB_20260605_0_L2A", "S2B_12SVB_20260605_0_L2A"),
        ("12SUB", "12SVB"),
    ),
    "satq-cef871428da247c3ecfadec6": (
        13,
        ("S2B_30UXC_20240626_0_L2A", "S2B_30UYC_20240626_0_L2A"),
        ("S2C_30UXC_20260624_0_L2A", "S2C_30UYC_20260624_0_L2A"),
        ("30UXC", "30UYC"),
    ),
    "satq-96fca962064e09f0dbafa93b": (
        30,
        ("S2B_14SPE_20240627_0_L2A", "S2B_14SPF_20240627_0_L2A"),
        ("S2B_14SPE_20260627_0_L2A", "S2B_14SPF_20260627_0_L2A"),
        ("14SPE", "14SPF"),
    ),
    "satq-78500568b1f6227789ae36f4": (
        38,
        ("S2A_30TXM_20240711_0_L2A", "S2A_30TYM_20240711_0_L2A"),
        ("S2C_30TXM_20260711_0_L2A", "S2C_30TYM_20260711_0_L2A"),
        ("30TXM", "30TYM"),
    ),
    "satq-fb6b6f815dad079c059cf412": (
        46,
        ("S2A_29SNB_20240717_0_L2A", "S2A_29SNC_20240717_0_L2A"),
        ("S2C_29SNB_20260717_0_L2A", "S2C_29SNC_20260717_0_L2A"),
        ("29SNB", "29SNC"),
    ),
    "satq-0ffe3647dc32ee25ef77eab7": (
        87,
        ("S2B_17TMF_20240719_0_L2A", "S2B_17TNF_20240719_0_L2A"),
        ("S2C_17TMF_20260714_0_L2A", "S2C_17TNF_20260714_0_L2A"),
        ("17TMF", "17TNF"),
    ),
}

BLOCKED_CLASSIFICATIONS = {
    "satq-d0a872a7aee9f9f54a8631ef": (16, "multi_tile_missing", "multi_tile_missing"),
    "satq-3288e71f7387eee72714a756": (24, "multi_tile_missing", "multi_tile_missing"),
    "satq-1478784c38a09b1d3c588c3b": (50, "multi_tile_missing", "multi_tile_missing"),
    "satq-66d1dc2e7f8654ac10d7980c": (53, "multi_tile_complete", "multi_tile_missing"),
    "satq-6936ad65587f752edbc1ba41": (65, "multi_tile_missing", "multi_tile_complete"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _rows(filename: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (RELEASE / filename).read_text(encoding="utf-8").splitlines()
    ]


def _all_partition_rows() -> list[dict[str, Any]]:
    rows = [
        *_rows("terminal-no-scene.jsonl"),
        *_rows("single-tile-ready.jsonl"),
        *_rows("multi-tile-ready.jsonl"),
        *_rows("multi-tile-blocked.jsonl"),
    ]
    return sorted(rows, key=lambda row: row["queue_position"])


def _tree_inventory(root: Path) -> tuple[int, int, int, str]:
    digest = hashlib.sha256()
    directories = 0
    files = 0
    file_bytes = 0
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"release contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            directories += 1
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            files += 1
            file_bytes += len(raw)
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported release entry: {relative}")
    return directories, files, file_bytes, digest.hexdigest()


def _legacy_tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for node in sorted([root, *root.rglob("*")]):
        relative = "." if node == root else node.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(f"{stat.S_IMODE(node.stat().st_mode):04o}".encode())
        if node.is_file():
            digest.update(hashlib.sha256(node.read_bytes()).digest())
    return digest.hexdigest()


def _force_remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    for node in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not node.is_symlink():
            node.chmod(0o700 if node.is_dir() else 0o600)
    path.chmod(0o700)
    shutil.rmtree(path)


@contextmanager
def _deny_external_io() -> Iterator[None]:
    failure = AssertionError("metadata preparation attempted external I/O")
    with ExitStack() as stack:
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        stack.enter_context(patch.object(urllib.request, "urlopen", side_effect=failure))
        stack.enter_context(patch.object(rasterio, "open", side_effect=failure))
        yield


class SatelliteChangePreparationV1Tests(unittest.TestCase):
    def _temporary_parent(self) -> Path:
        return Path(tempfile.mkdtemp(prefix=".change-preparation-v1-test-", dir=ROOT))

    def test_frozen_release_validates_offline_with_exact_pins_and_tree(self) -> None:
        with _deny_external_io():
            manifest = validate_satellite_change_preparation_v1(
                RELEASE, definition_path=DEFINITION
            )

        self.assertEqual((_sha256(DEFINITION), DEFINITION.stat().st_size), (DEFINITION_SHA256, 4_181))
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual((_sha256(MODULE), MODULE.stat().st_size), (MODULE_SHA256, 46_019))
        self.assertEqual((_sha256(OUTER_SHIM), OUTER_SHIM.stat().st_size), (OUTER_SHIM_SHA256, 157))
        self.assertEqual((_sha256(CLI), CLI.stat().st_size), (CLI_SHA256, 1_866))
        self.assertEqual(set(ARTIFACTS), RELEASE_FILES)
        for filename, expected in ARTIFACTS.items():
            path = RELEASE / filename
            self.assertEqual((path.stat().st_size, _sha256(path)), expected, path)
        self.assertEqual(
            (RELEASE / "manifest.sha256").read_text(encoding="ascii"),
            f"{ARTIFACTS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(_tree_inventory(RELEASE), (1, 11, 1_284_397, TREE_SHA256))
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in RELEASE.iterdir())
        )
        self.assertEqual(manifest["format"], "datacenter-atlas-satellite-change-preparation-v1")
        self.assertEqual(manifest["summary"], SUMMARY)
        self.assertEqual(manifest["runtime"], RUNTIME)
        self.assertEqual(manifest["claim_constraints"], CLAIM_CONSTRAINTS)
        self.assertEqual(
            manifest["scope"],
            {
                "aoi_deduplication_applied": False,
                "entity_jobs_retained": 87,
                "imagery_downloads": 0,
                "imagery_opens": 0,
                "network_requests": 0,
                "preparation_only": True,
                "raster_analyses": 0,
            },
        )
        self.assertEqual(manifest["definition"]["sha256"], DEFINITION_SHA256)
        self.assertEqual(manifest["builder"]["module"]["sha256"], MODULE_SHA256)
        self.assertEqual(manifest["builder"]["outer_shim"]["sha256"], OUTER_SHIM_SHA256)
        self.assertEqual(manifest["builder"]["cli"]["sha256"], CLI_SHA256)

    def test_partition_retains_every_job_and_shared_aois_are_relationships_only(self) -> None:
        rows = _all_partition_rows()
        self.assertEqual(len(rows), 87)
        self.assertEqual([row["queue_position"] for row in rows], list(range(1, 88)))
        self.assertEqual(len({row["queue_id"] for row in rows}), 87)
        self.assertEqual(
            {state: sum(row["state"] == state for row in rows) for state in v1.STATES},
            {
                "terminal_no_scene": 2,
                "single_tile_ready": 74,
                "multi_tile_ready": 6,
                "multi_tile_blocked": 5,
            },
        )

        relationships = _rows("aoi-relationships.jsonl")
        self.assertEqual(len(relationships), 84)
        shared = [row for row in relationships if row["shared_aoi"]]
        self.assertEqual(
            [[job["queue_position"] for job in row["jobs"]] for row in shared],
            [[17, 18], [19, 21], [20, 22]],
        )
        self.assertEqual(sum(row["job_count"] for row in shared), 6)
        relationship_by_id = {
            row["aoi_relationship_id"]: row for row in relationships
        }
        for row in rows:
            relationship = relationship_by_id[
                row["aoi_relationship"]["aoi_relationship_id"]
            ]
            self.assertIn(
                row["queue_id"], [job["queue_id"] for job in relationship["jobs"]]
            )
            self.assertFalse(relationship["processing_deduplicated"])
            self.assertTrue(relationship["relationship_only"])
            self.assertFalse(row["aoi_relationship"]["processing_deduplicated"])
            self.assertEqual(row["claim_constraints"], CLAIM_CONSTRAINTS)
            self.assertTrue(all(value is False for value in row["claim_constraints"].values()))
            self.assertEqual(row["network_requests"], 0)
            self.assertFalse(row["raster_analysis_executed"])
            self.assertTrue(row["preparation_only"])

    def test_every_response_item_asset_bbox_and_execution_binding_is_exact(self) -> None:
        queue_rows = {
            row["queue_id"]: row
            for row in (
                json.loads(line)
                for line in (QUEUE / "satellite-review-queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            if row["priority"]["tier"] == "active_construction"
        }
        binding_inventory: list[dict[str, Any]] = []
        for row in _all_partition_rows():
            queue_row = queue_rows[row["queue_id"]]
            self.assertEqual(row["aoi_bbox_wgs84"], queue_row["location"]["aoi_bbox_wgs84"])
            self.assertEqual(row["entity"], queue_row["entity"])
            inventory_row = {
                key: row[key]
                for key in (
                    "queue_position",
                    "queue_id",
                    "state",
                    "aoi_bbox_wgs84",
                    "entity",
                    "execution",
                )
            }
            if row["state"] == "terminal_no_scene":
                inventory_row["unavailability"] = row["unavailability"]
                binding_inventory.append(inventory_row)
                continue

            inventory_row["epochs"] = {}
            for epoch in ("baseline", "current"):
                epoch_record = row["epochs"][epoch]
                response_pin = epoch_record["archived_stac_response"]
                response_path = ROOT / response_pin["path"]
                response_raw = response_path.read_bytes()
                self.assertEqual(len(response_raw), response_pin["bytes"])
                self.assertEqual(hashlib.sha256(response_raw).hexdigest(), response_pin["sha256"])
                self.assertEqual(
                    row["catalog_artifacts"][f"{epoch}-response.json"], response_pin
                )
                document = json.loads(response_raw)
                by_id = {item["id"]: item for item in document["features"]}
                selected = epoch_record["selected_item_asset_bindings"]
                self.assertEqual(selected[0]["role"], "primary")
                self.assertEqual(selected[0]["id"], epoch_record["primary"]["id"])
                self.assertEqual(
                    [item["id"] for item in selected[1:]],
                    [item["id"] for item in epoch_record["selected_companions"]],
                )
                self.assertEqual(
                    epoch_record["tile_coverage"]["selected_tiles"],
                    [item["mgrs_tile"] for item in selected],
                )
                for binding in selected:
                    item = by_id[binding["id"]]
                    self.assertEqual(canonical_sha256(item), binding["stac_item_sha256"])
                    properties = item["properties"]
                    self.assertEqual(
                        binding["acquisition"],
                        {
                            "datastrip_id": properties["s2:datastrip_id"],
                            "datatake_id": properties["s2:datatake_id"],
                        },
                    )
                    self.assertEqual(set(binding["assets"]), set(REQUIRED_ASSETS))
                    for asset_name, asset_binding in binding["assets"].items():
                        source_asset = item["assets"][asset_name]
                        href = source_asset["href"]
                        grid = grid_from_item(item, asset_name)
                        self.assertEqual(asset_binding["href"], href)
                        self.assertEqual(
                            asset_binding["href_sha256"],
                            hashlib.sha256(href.encode("utf-8")).hexdigest(),
                        )
                        self.assertEqual(asset_binding["proj_epsg"], grid.epsg)
                        self.assertEqual(
                            asset_binding["proj_shape"], [grid.height, grid.width]
                        )
                        self.assertEqual(
                            asset_binding["proj_transform"], list(grid.transform_tuple)
                        )

                inventory_row["epochs"][epoch] = {
                    key: epoch_record[key]
                    for key in (
                        "archived_stac_response",
                        "primary",
                        "selected_companions",
                        "selected_item_asset_bindings",
                        "tile_coverage",
                        "classification",
                        "blocker",
                        "rejected_companion_candidates",
                    )
                }
            if row["execution"] is not None:
                self.assertEqual(row["execution"]["runtime"], RUNTIME)
                arguments = row["execution"]["arguments"]
                self.assertEqual(arguments[-2:], ["--minimum-component-area-m2", "5000"])
                bbox_index = arguments.index("--bbox")
                self.assertEqual(
                    arguments[bbox_index + 1],
                    ",".join(v1._number_text(value) for value in row["aoi_bbox_wgs84"]),
                )
                self.assertIn(row["entity"]["id"], arguments)
                self.assertIn(row["entity"]["name"], arguments)
            binding_inventory.append(inventory_row)

        self.assertEqual(_canonical_digest(binding_inventory), BINDING_INVENTORY_SHA256)

    def test_multi_tile_ready_companions_are_exact_same_acquisition_pairs(self) -> None:
        rows = {row["queue_id"]: row for row in _rows("multi-tile-ready.jsonl")}
        self.assertEqual(set(rows), set(MULTI_READY))
        item_inventory: list[dict[str, Any]] = []
        for queue_id, (position, baseline, current, tiles) in MULTI_READY.items():
            row = rows[queue_id]
            self.assertEqual(row["queue_position"], position)
            self.assertEqual(row["execution"]["cli"], "scripts/sentinel_change_mosaic.py")
            self.assertTrue(row["cross_epoch_contract"]["primary_mgrs_tile_equal"])
            self.assertTrue(
                row["cross_epoch_contract"]["primary_grids_equal_for_red_swir16_scl"]
            )
            item_inventory.append(
                {
                    "queue_position": position,
                    "queue_id": queue_id,
                    "baseline": list(baseline),
                    "current": list(current),
                }
            )
            for epoch, expected_items in (("baseline", baseline), ("current", current)):
                record = row["epochs"][epoch]
                selected = record["selected_item_asset_bindings"]
                self.assertEqual(record["classification"], "multi_tile_complete")
                self.assertEqual([item["id"] for item in selected], list(expected_items))
                self.assertEqual([item["mgrs_tile"] for item in selected], list(tiles))
                self.assertFalse(record["primary_only_coverage"]["complete"])
                self.assertTrue(record["selected_coverage"]["complete"])
                self.assertTrue(record["tile_coverage"]["coverage_complete"])
                self.assertEqual(len(record["selected_companions"]), 1)
                acquisitions = [item["acquisition"] for item in selected]
                self.assertEqual(acquisitions[0], acquisitions[1])
                self.assertTrue(acquisitions[0]["datatake_id"])
                self.assertTrue(acquisitions[0]["datastrip_id"])
                arguments = row["execution"]["arguments"]
                primary = selected[0]
                companion = selected[1]
                self.assertIn(
                    f"{primary['id']}={primary['stac_item_sha256']}", arguments
                )
                self.assertIn(
                    f"{companion['id']}={companion['stac_item_sha256']}", arguments
                )
                self.assertIn(record["archived_stac_response"]["sha256"], arguments)
        item_inventory.sort(key=lambda row: row["queue_position"])
        self.assertEqual(
            _canonical_digest(item_inventory), MULTI_READY_ITEM_INVENTORY_SHA256
        )

    def test_blocked_and_no_scene_reason_inventories_are_preserved_exactly(self) -> None:
        blocked = _rows("multi-tile-blocked.jsonl")
        blocked_inventory: list[dict[str, Any]] = []
        for row in blocked:
            expected = BLOCKED_CLASSIFICATIONS[row["queue_id"]]
            self.assertEqual(row["queue_position"], expected[0])
            self.assertEqual(row["epochs"]["baseline"]["classification"], expected[1])
            self.assertEqual(row["epochs"]["current"]["classification"], expected[2])
            self.assertIsNone(row["execution"])
            self.assertIn(
                "multi_tile_missing",
                {
                    row["epochs"]["baseline"]["classification"],
                    row["epochs"]["current"]["classification"],
                },
            )
            blocked_inventory.append(
                {
                    "queue_position": row["queue_position"],
                    "queue_id": row["queue_id"],
                    "baseline": {
                        "classification": row["epochs"]["baseline"]["classification"],
                        "blocker": row["epochs"]["baseline"]["blocker"],
                        "rejected": row["epochs"]["baseline"][
                            "rejected_companion_candidates"
                        ],
                    },
                    "current": {
                        "classification": row["epochs"]["current"]["classification"],
                        "blocker": row["epochs"]["current"]["blocker"],
                        "rejected": row["epochs"]["current"][
                            "rejected_companion_candidates"
                        ],
                    },
                }
            )
        self.assertEqual(
            _canonical_digest(blocked_inventory), BLOCKED_REASON_INVENTORY_SHA256
        )
        self.assertEqual(
            {
                candidate["reason_code"]
                for row in blocked_inventory
                for epoch in ("baseline", "current")
                for candidate in row[epoch]["rejected"]
            },
            {"incompatible_crs"},
        )

        batch = json.loads(CATALOG_MANIFEST.read_text(encoding="utf-8"))
        no_scene = _rows("terminal-no-scene.jsonl")
        no_scene_inventory = []
        for row in no_scene:
            job = batch["jobs"][row["queue_id"]]
            self.assertEqual(job["state"], "unavailable_no_scene")
            self.assertEqual(row["unavailability"], job["unavailability"])
            self.assertIsNone(row["execution"])
            self.assertNotIn("epochs", row)
            self.assertNotIn("processor", row)
            no_scene_inventory.append(
                {
                    "queue_position": row["queue_position"],
                    "queue_id": row["queue_id"],
                    "unavailability": row["unavailability"],
                }
            )
        self.assertEqual(
            [(row["queue_position"], row["unavailability"]["window"]) for row in no_scene],
            [(10, "baseline"), (14, "current")],
        )
        self.assertEqual(
            _canonical_digest(no_scene_inventory), NO_SCENE_REASON_INVENTORY_SHA256
        )

    def test_two_denied_io_replays_are_byte_identical_to_frozen_release(self) -> None:
        first_parent = self._temporary_parent()
        second_parent = self._temporary_parent()
        first = first_parent / "release"
        second = second_parent / "release"
        try:
            with _deny_external_io():
                write_satellite_change_preparation_v1(first, definition_path=DEFINITION)
                write_satellite_change_preparation_v1(second, definition_path=DEFINITION)
            self.assertEqual(_tree_inventory(first), _tree_inventory(RELEASE))
            self.assertEqual(_tree_inventory(second), _tree_inventory(RELEASE))
            for filename in RELEASE_FILES:
                self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
                self.assertEqual((first / filename).read_bytes(), (RELEASE / filename).read_bytes())
        finally:
            _force_remove(first_parent)
            _force_remove(second_parent)

    def test_source_response_and_emitted_binding_tampering_fail_closed(self) -> None:
        target = (
            CATALOG
            / "jobs/satq-54c6402eb93d14f1ea754e66/catalog/baseline-response.json"
        ).resolve()
        original_read_bytes = Path.read_bytes

        def tampered_source(path: Path) -> bytes:
            raw = original_read_bytes(path)
            return raw + b" " if path.resolve() == target else raw

        with patch.object(Path, "read_bytes", tampered_source), self.assertRaisesRegex(
            SatelliteChangePreparationV1Error, "catalog batch closed-tree pin mismatch"
        ):
            validate_satellite_change_preparation_v1(RELEASE, definition_path=DEFINITION)

        expected_payloads = {
            filename: (RELEASE / filename).read_bytes() for filename in RELEASE_FILES
        }
        accepted_manifest = json.loads((RELEASE / "manifest.json").read_text())

        def alter_response(row: dict[str, Any]) -> None:
            row["epochs"]["baseline"]["archived_stac_response"]["sha256"] = "0" * 64

        def alter_item(row: dict[str, Any]) -> None:
            row["epochs"]["baseline"]["selected_item_asset_bindings"][0]["id"] += "-tampered"

        def alter_asset(row: dict[str, Any]) -> None:
            asset = row["epochs"]["baseline"]["selected_item_asset_bindings"][0][
                "assets"
            ]["red"]
            asset["href"] += "?tampered=1"

        def alter_bbox(row: dict[str, Any]) -> None:
            row["aoi_bbox_wgs84"][0] += 0.0001

        for label, mutator in (
            ("archived response binding", alter_response),
            ("item binding", alter_item),
            ("asset binding", alter_asset),
            ("bbox binding", alter_bbox),
        ):
            parent = self._temporary_parent()
            output = parent / "release"
            try:
                shutil.copytree(RELEASE, output)
                path = output / "multi-tile-ready.jsonl"
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                mutator(rows[0])
                raw = b"".join(
                    (
                        json.dumps(
                            row,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                    for row in rows
                )
                path.chmod(0o600)
                path.write_bytes(raw)
                path.chmod(0o444)
                with self.subTest(label=label), patch.object(
                    v1,
                    "_payloads",
                    return_value=(expected_payloads, accepted_manifest),
                ), self.assertRaisesRegex(
                    SatelliteChangePreparationV1Error,
                    "preparation artifact differs: multi-tile-ready.jsonl",
                ):
                    validate_satellite_change_preparation_v1(
                        output, definition_path=DEFINITION
                    )
            finally:
                _force_remove(parent)

    def test_symlinks_freeze_drift_and_existing_target_are_rejected(self) -> None:
        parent = self._temporary_parent()
        try:
            output_link = parent / "output-link"
            output_link.symlink_to(RELEASE, target_is_directory=True)
            with self.assertRaisesRegex(
                SatelliteChangePreparationV1Error, "not a regular directory"
            ):
                validate_satellite_change_preparation_v1(
                    output_link, definition_path=DEFINITION
                )

            definition_link = parent / "definition-link.json"
            definition_link.symlink_to(DEFINITION)
            with self.assertRaisesRegex(
                SatelliteChangePreparationV1Error, "definition is not a regular file"
            ):
                validate_satellite_change_preparation_v1(
                    RELEASE, definition_path=definition_link
                )

            source_tree = parent / "source-tree"
            source_tree.mkdir()
            (source_tree / "linked-response.json").symlink_to(
                CATALOG
                / "jobs/satq-54c6402eb93d14f1ea754e66/catalog/baseline-response.json"
            )
            with self.assertRaisesRegex(
                SatelliteChangePreparationV1Error, "closed tree contains symlink"
            ):
                v1._tree_inventory(source_tree)

            existing = parent / "existing"
            existing.mkdir()
            sentinel = existing / "sentinel.txt"
            sentinel.write_text("retain\n", encoding="utf-8")
            before = (sentinel.stat().st_ino, sentinel.read_bytes())
            with self.assertRaisesRegex(
                SatelliteChangePreparationV1Error, "refusing to replace"
            ):
                write_satellite_change_preparation_v1(
                    existing, definition_path=DEFINITION
                )
            self.assertEqual((sentinel.stat().st_ino, sentinel.read_bytes()), before)

            thawed = parent / "thawed"
            shutil.copytree(RELEASE, thawed)
            (thawed / "summary.json").chmod(0o644)
            expected_payloads = {
                filename: (RELEASE / filename).read_bytes()
                for filename in RELEASE_FILES
            }
            accepted_manifest = json.loads((RELEASE / "manifest.json").read_text())
            with patch.object(
                v1,
                "_payloads",
                return_value=(expected_payloads, accepted_manifest),
            ), self.assertRaisesRegex(
                SatelliteChangePreparationV1Error, "artifact is not frozen"
            ):
                validate_satellite_change_preparation_v1(
                    thawed, definition_path=DEFINITION
                )
        finally:
            _force_remove(parent)

    def test_generic_companion_partition_marks_absent_and_ambiguous_sets(self) -> None:
        document = {
            "type": "FeatureCollection",
            "features": [
                {"id": "primary"},
                {"id": "companion-a"},
                {"id": "companion-b"},
            ],
        }
        companions = (
            ItemBinding("companion-a", "a" * 64),
            ItemBinding("companion-b", "b" * 64),
        )

        def select_bound_items(
            _document: object, primary: ItemBinding, selected: tuple[ItemBinding, ...]
        ) -> tuple[dict[str, str], list[dict[str, str]]]:
            by_id = {item["id"]: item for item in document["features"]}
            return by_id[primary.item_id], [
                by_id[primary.item_id],
                *(by_id[binding.item_id] for binding in selected),
            ]

        def coverage(
            _primary: object,
            items: list[dict[str, str]],
            _bbox: object,
            _transform: object,
        ) -> dict[str, bool]:
            return {"complete": len(items) > 1}

        def item_binding(
            _item: object, binding: ItemBinding, role: str
        ) -> dict[str, str]:
            return {
                "id": binding.item_id,
                "mgrs_tile": "31TAA" if role == "primary" else "31TAB",
                "role": role,
            }

        with patch.object(v1, "select_bound_items", side_effect=select_bound_items), patch.object(
            v1, "epoch_metadata_coverage", side_effect=coverage
        ), patch.object(
            v1,
            "_candidate_summary",
            side_effect=lambda _document, binding: {
                "id": binding.item_id,
                "mgrs_tile": "31TAB",
                "stac_item_sha256": binding.stac_item_sha256,
            },
        ), patch.object(v1, "_item_binding", side_effect=item_binding), patch.object(
            v1, "mgrs_tile", return_value="31TAA"
        ):
            with patch.object(
                v1, "discover_same_acquisition_bindings", return_value=companions
            ):
                ambiguous, _ = v1._assess_epoch(
                    document=document,
                    epoch="baseline",
                    primary_id="primary",
                    response_pin={"bytes": 1, "path": "fixture", "sha256": "0" * 64},
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    transform_bounds=lambda *_args: (0.0, 0.0, 1.0, 1.0),
                )
            with patch.object(
                v1, "discover_same_acquisition_bindings", return_value=()
            ):
                missing, _ = v1._assess_epoch(
                    document=document,
                    epoch="current",
                    primary_id="primary",
                    response_pin={"bytes": 1, "path": "fixture", "sha256": "0" * 64},
                    bbox=(0.0, 0.0, 1.0, 1.0),
                    transform_bounds=lambda *_args: (0.0, 0.0, 1.0, 1.0),
                )

        self.assertEqual(ambiguous["classification"], "multi_tile_ambiguous")
        self.assertEqual(
            ambiguous["blocker"]["reason"],
            "multiple_minimal_archived_companion_sets_cover_aoi",
        )
        self.assertEqual(len(ambiguous["blocker"]["candidate_solutions"]), 2)
        self.assertEqual(missing["classification"], "multi_tile_missing")
        self.assertEqual(
            missing["blocker"]["reason"],
            "no_archived_compatible_companion_set_covers_aoi",
        )

    def test_source_inventory_is_closed_and_all_267_pins_resolve(self) -> None:
        inventory = json.loads((RELEASE / "source-inventory.json").read_text())
        self.assertEqual(inventory["source_file_count"], 267)
        groups: dict[str, int] = {}
        for pin in inventory["files"]:
            groups[pin["source_group"]] = groups.get(pin["source_group"], 0) + 1
            path = ROOT / pin["path"]
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(path.stat().st_size, pin["bytes"], path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), int(pin["mode"], 8), path)
            self.assertEqual(_sha256(path), pin["sha256"], path)
        self.assertEqual(
            groups,
            {
                "builder:cli": 1,
                "builder:module": 1,
                "builder:outer_shim": 1,
                "catalog_batch": 256,
                "catalog_lock": 1,
                "processor:multi_tile:cli": 1,
                "processor:multi_tile:module": 1,
                "processor:single_tile:cli": 1,
                "processor:single_tile:module": 1,
                "queue_bundle": 3,
            },
        )

    def test_cli_and_both_package_layouts_expose_the_same_preparation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                os.fspath(CLI),
                "--validate-only",
                "--definition",
                os.fspath(DEFINITION),
                "--output-dir",
                os.fspath(RELEASE),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["summary"], SUMMARY)

        code = (
            "from datacenter_atlas.satellite_change_preparation_v1 import "
            "PREPARATION_ID, RELEASE_FORMAT; "
            "print(PREPARATION_ID); print(RELEASE_FORMAT)"
        )
        for cwd in (ROOT, WORKSPACE):
            with self.subTest(cwd=cwd):
                imported = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(imported.returncode, 0, imported.stderr)
                self.assertEqual(
                    imported.stdout.splitlines(),
                    [
                        "2026-07-20-open-seed-v57-active-change-preparation-v1",
                        "datacenter-atlas-satellite-change-preparation-v1",
                    ],
                )

    def test_prior_mosaic_processor_and_frozen_v6_bundle_are_unchanged(self) -> None:
        mosaic_module = ROOT / "datacenter_atlas/satellite_change_mosaic.py"
        mosaic_cli = ROOT / "scripts/sentinel_change_mosaic.py"
        definition = (
            ROOT
            / "sources/satellite-mosaic-preparation-2026-07-19-algorithm-v2-blocked-v6.json"
        )
        release = (
            ROOT
            / "satellite_mosaic_preparation/2026-07-19-algorithm-v2-blocked-v6"
        )
        self.assertEqual(
            _sha256(mosaic_module),
            "68a89c8aedd16326c530d3c07416a10432e64af1458dba630ded89d4b5ace071",
        )
        self.assertEqual(
            _sha256(mosaic_cli),
            "6e5ffc0dbb04a1f8202d13556e26fe45a9075966da9037e70f417152360e2183",
        )
        self.assertEqual(
            _sha256(definition),
            "3c8920f5d0779f9286da0361f0256efb285d84e842aaa74083b1b8d08a5e95b1",
        )
        self.assertEqual(
            _sha256(release / "manifest.json"),
            "f0cb59766c68e7cc54da8f103f7a92a7eb4943e2fe4533702df9d19c0cd366e6",
        )
        self.assertEqual(
            _legacy_tree_digest(release),
            "bc421a39012ab9cfdf5142e5a71163f94d030c57ac837ea058dd34ccf72dc57e",
        )


if __name__ == "__main__":
    unittest.main()
