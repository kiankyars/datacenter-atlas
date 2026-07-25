from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import stat
import unittest
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from datacenter_atlas import construction_map_v32 as shim
    from datacenter_atlas.datacenter_atlas import construction_map_v32 as map_v32
    from datacenter_atlas.datacenter_atlas.open_seed_v56 import tree_digest
except ModuleNotFoundError:
    import construction_map_v32 as shim
    from datacenter_atlas import construction_map_v32 as map_v32
    from datacenter_atlas.open_seed_v56 import tree_digest


DEFINITION_PIN = (
    2_509,
    "67789635b3f197e12705fcd8ad635b5ad552c6d315cf0dab3d487c6f5379d32d",
)
BUNDLE_TREE_PIN = "ae25def835f0715566ffed2aa12dad6834484ed6a93a692eef310bfee07aa0c2"
BUNDLE_PINS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "24b0e3143fc9f9a130869c7b546e34ed369228e7772f69669835ac9368cbb96d",
    ),
    "construction-map-index.json.gz": (
        6_683_678,
        "2b59b4cc377d335ec1db1534dfe28e7f7050683df209b3ea836e7a371e16b294",
    ),
    "construction-map.html": (
        8_929_180,
        "08ec618175707ec6b6167969ce96741f86f751518654c479c0e0e8f8520ee7b9",
    ),
    "coverage.json": (
        7_524,
        "98e7b1c7841c2480d69f87fe63416247703b3e28f3f4220f1b0899227198967b",
    ),
    "manifest.json": (
        2_172,
        "b4176ec21fde9a30f5c727e2061d4d6ebb00a5d9eb80bea76b60b06ea0887ef9",
    ),
    "manifest.sha256": (
        80,
        "d5361beb8aa2be4de265387ea35b6bbb1409ec98cec487fed9eb759d4a2395c2",
    ),
}


def checkpoint(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


class ConstructionMapV32Tests(unittest.TestCase):
    def test_exact_structured_projection(self) -> None:
        projection = map_v32.derive_candidate_projection(
            map_v32.CANDIDATE_MASTER,
            map_v32.CANDIDATE_MASTER_DEFINITION,
        )
        self.assertEqual(projection, map_v32.EXPECTED_PROJECTION)

    def test_private_candidate_definition_pins_and_static_validation(self) -> None:
        with map_v32._runtime_timestamps(
            map_v32.MAP_GENERATED_AT,
            map_v32.CANDIDATE_MASTER_GENERATED_AT,
        ):
            manifest = map_v32._core_validate_static(
                map_v32.CANDIDATE_BUNDLE_STAGE,
                frozen=True,
            )
        self.assertEqual(checkpoint(map_v32.CANDIDATE_DEFINITION_STAGE), DEFINITION_PIN)
        self.assertEqual(
            {
                path.name: checkpoint(path)
                for path in map_v32.CANDIDATE_BUNDLE_STAGE.iterdir()
            },
            BUNDLE_PINS,
        )
        self.assertEqual(tree_digest(map_v32.CANDIDATE_BUNDLE_STAGE), BUNDLE_TREE_PIN)
        self.assertEqual(manifest["master"]["rows"], 109_443)
        coverage = json.loads(
            (map_v32.CANDIDATE_BUNDLE_STAGE / "coverage.json").read_bytes()
        )
        self.assertEqual(coverage["projection"], map_v32.EXPECTED_PROJECTION)
        self.assertEqual(
            stat.S_IMODE(map_v32.CANDIDATE_DEFINITION_STAGE.stat().st_mode),
            0o444,
        )
        self.assertEqual(
            stat.S_IMODE(map_v32.CANDIDATE_BUNDLE_STAGE.stat().st_mode),
            0o555,
        )

        predecessor = json.loads(map_v32.PREDECESSOR_DEFINITION.read_bytes())
        current = json.loads(map_v32.CANDIDATE_DEFINITION_STAGE.read_bytes())
        expected = deepcopy(predecessor)
        expected["map_id"] = map_v32.MAP_ID
        expected["generated_at"] = map_v32.MAP_GENERATED_AT
        expected["expected_projection"] = map_v32.EXPECTED_PROJECTION
        expected["master"] = current["master"]
        self.assertEqual(current, expected)

    def test_public_output_stays_blocked_until_public_master_bytes_are_pinned(
        self,
    ) -> None:
        self.assertEqual(
            (
                map_v32.PUBLIC_DEFINITION_SHA256,
                map_v32.PUBLIC_MANIFEST_SHA256,
                map_v32.PUBLIC_TREE_SHA256,
            ),
            (None, None, None),
        )
        with self.assertRaisesRegex(
            map_v32.ConstructionMapV32Error,
            "public-output pins are not reviewed",
        ):
            map_v32._require_public_output_pins(
                map_v32.CANDIDATE_DEFINITION_STAGE,
                map_v32.CANDIDATE_BUNDLE_STAGE,
            )

        with TemporaryDirectory(prefix="map-v32-existing-unpinned-") as temporary:
            root = Path(temporary)
            sources = root / "sources"
            maps = root / "construction_maps"
            masters = root / "construction_master"
            sources.mkdir()
            maps.mkdir()
            masters.mkdir()
            definition = sources / "map.json"
            bundle = maps / "map"
            definition.write_bytes(b"definition")
            bundle.mkdir()
            (bundle / map_v32.MANIFEST_FILENAME).write_bytes(b"manifest")
            with (
                patch.multiple(
                    map_v32,
                    DEFINITION=definition,
                    BUNDLE=bundle,
                    PUBLICATION_LOCK=root / ".map.lock",
                    MASTER=masters / "master",
                    MASTER_DEFINITION=sources / "master.json",
                    MAP_GENERATED_AT="2026-07-25T00:00:00Z",
                ),
                self.assertRaisesRegex(
                    map_v32.ConstructionMapV32Error,
                    "public-output pins are not reviewed",
                ),
            ):
                map_v32.publish_construction_map_v32(
                    "2026-07-25T00:00:00Z",
                    publication_authorized=True,
                )

    def test_four_bare_collisions_are_distinct_rows_and_not_map_collapses(
        self,
    ) -> None:
        bare_counts: Counter[str] = Counter()
        row_ids: set[str] = set()
        source_identities: set[tuple[str, str]] = set()
        collision_rows: dict[str, list[dict[str, object]]] = {
            record_id: []
            for record_id in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
        }
        master_path = map_v32.CANDIDATE_MASTER / "construction-master.jsonl"
        with master_path.open("rb") as source:
            for raw in source:
                row = json.loads(raw)
                artifact_id = row["source"]["artifact_id"]
                record_id = row["source"]["record_id"]
                row_id = row["row_id"]
                self.assertNotIn(row_id, row_ids)
                self.assertNotIn((artifact_id, record_id), source_identities)
                row_ids.add(row_id)
                source_identities.add((artifact_id, record_id))
                bare_counts[record_id] += 1
                if record_id in collision_rows:
                    collision_rows[record_id].append(row)
        self.assertEqual(len(row_ids), 109_443)
        self.assertEqual(len(source_identities), 109_443)
        self.assertEqual(len(bare_counts), 109_439)
        self.assertEqual(
            {record_id for record_id, count in bare_counts.items() if count > 1},
            map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS,
        )
        for rows in collision_rows.values():
            self.assertEqual(len(rows), 2)
            by_artifact = {row["source"]["artifact_id"]: row for row in rows}
            self.assertEqual(
                set(by_artifact),
                {"epoch-official-open-seed-v97", "global-open-v3"},
            )
            self.assertIsNone(
                by_artifact["epoch-official-open-seed-v97"]["entity"]["latitude"]
            )
            self.assertIsNotNone(by_artifact["global-open-v3"]["entity"]["latitude"])

        index = json.loads(
            gzip.decompress(
                (map_v32.CANDIDATE_BUNDLE_STAGE / map_v32.INDEX_FILENAME).read_bytes()
            )
        )
        rows = [
            dict(zip(index["fields"], values, strict=True)) for values in index["rows"]
        ]
        mapped_collisions = {
            row["source_record_id"]: row["source_artifact_id"]
            for row in rows
            if row["source_record_id"] in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
        }
        self.assertEqual(
            mapped_collisions,
            {
                record_id: "global-open-v3"
                for record_id in map_v32.EXPECTED_BARE_SOURCE_RECORD_COLLISIONS
            },
        )
        northc = next(
            row
            for row in rows
            if row["source_record_id"] == "ab9bf6d5-73d7-5d84-9b66-b80d2da64866"
        )
        self.assertEqual(
            (northc["longitude"], northc["latitude"]),
            (4.77335841, 52.25979593),
        )
        self.assertEqual(northc["source_artifact_id"], "epoch-official-open-seed-v97")

    def test_shim_and_final_paths_remain_unpublished(self) -> None:
        self.assertIs(
            shim.publish_construction_map_v32,
            map_v32.publish_construction_map_v32,
        )
        self.assertFalse(map_v32.PUBLICATION_LOCK.exists())
        self.assertFalse(map_v32.DEFINITION.exists())
        self.assertFalse(map_v32.BUNDLE.exists())
        with self.assertRaisesRegex(
            map_v32.ConstructionMapV32Error,
            "requires authorization",
        ):
            map_v32.publish_construction_map_v32()

    def test_public_defaults_bind_dated_v32_paths(self) -> None:
        definition_defaults = map_v32.definition_document.__kwdefaults__
        validation_defaults = map_v32.validate_construction_map_v32.__kwdefaults__
        write_defaults = map_v32.write_construction_map_v32.__kwdefaults__
        self.assertIsNotNone(definition_defaults)
        self.assertIsNotNone(validation_defaults)
        self.assertIsNotNone(write_defaults)
        self.assertEqual(definition_defaults["master_directory"], map_v32.MASTER)
        self.assertEqual(
            definition_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(
            map_v32.validate_construction_map_v32.__defaults__,
            (map_v32.BUNDLE,),
        )
        self.assertEqual(validation_defaults["master_directory"], map_v32.MASTER)
        self.assertEqual(
            validation_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(validation_defaults["map_definition_path"], map_v32.DEFINITION)
        self.assertEqual(
            map_v32.write_construction_map_v32.__defaults__,
            (map_v32.MASTER, map_v32.BUNDLE),
        )
        self.assertEqual(
            write_defaults["master_definition_path"],
            map_v32.MASTER_DEFINITION,
        )
        self.assertEqual(write_defaults["map_definition_path"], map_v32.DEFINITION)
        self.assertIs(
            map_v32.build_construction_map_v32,
            map_v32.write_construction_map_v32,
        )

    def test_public_defaults_call_through_to_dated_v32_paths(self) -> None:
        with patch.object(
            map_v32,
            "_carrier_validate_public",
            return_value={"ok": True},
        ) as validate:
            self.assertEqual(map_v32.validate_construction_map_v32(), {"ok": True})
        validate.assert_called_once_with(
            map_v32.BUNDLE,
            master_directory=map_v32.MASTER,
            master_definition_path=map_v32.MASTER_DEFINITION,
            map_definition_path=map_v32.DEFINITION,
            replay_count=2,
            require_accepted_master=True,
            require_frozen=True,
            validation_wall_clock=None,
        )

        with patch.object(
            map_v32,
            "publish_construction_map_v32",
            return_value={"published": True},
        ) as publish:
            self.assertEqual(
                map_v32.write_construction_map_v32(
                    generated_at=map_v32.MAP_GENERATED_AT,
                    publication_authorized=True,
                ),
                {"published": True},
            )
        publish.assert_called_once_with(
            map_v32.MAP_GENERATED_AT,
            publication_authorized=True,
        )

    def test_final_validation_failure_rolls_back_both_owned_finals(self) -> None:
        with TemporaryDirectory(prefix="construction-map-v32-publish-") as temporary:
            root = Path(temporary)
            sources = root / "sources"
            maps = root / "construction_maps"
            masters = root / "construction_master"
            sources.mkdir()
            maps.mkdir()
            masters.mkdir()
            master = masters / "master"
            master.mkdir()
            master_definition = sources / "master.json"
            master_definition.write_bytes(b"accepted master")
            definition = sources / "map.json"
            bundle = maps / "map"
            lock = root / ".map.lock"
            target = (datetime.now(UTC) + timedelta(seconds=2)).replace(
                microsecond=0
            )
            generated_at = target.isoformat().replace("+00:00", "Z")

            def build_bundle(destination: Path, **_kwargs: object) -> dict[str, object]:
                nested = destination / "nested"
                nested.mkdir()
                (nested / "payload.json").write_bytes(b'{"ok":true}\n')
                return {}

            validations = [{}, map_v32.ConstructionMapV32Error("final validation")]
            with (
                patch.multiple(
                    map_v32,
                    DEFINITION=definition,
                    BUNDLE=bundle,
                    PUBLICATION_LOCK=lock,
                    MASTER=master,
                    MASTER_DEFINITION=master_definition,
                    MAP_GENERATED_AT=generated_at,
                ),
                patch.object(map_v32, "_require_predecessor"),
                patch.object(map_v32, "_require_accepted_master"),
                patch.object(map_v32, "definition_document", return_value={}),
                patch.object(
                    map_v32,
                    "_build_bundle_stage",
                    side_effect=build_bundle,
                ),
                patch.object(map_v32, "_assert_two_replays"),
                patch.object(map_v32, "_core_validate_static"),
                patch.object(map_v32, "_require_public_output_pins"),
                patch.object(
                    map_v32,
                    "_definition_generated_at",
                    return_value=generated_at,
                ),
                patch.object(
                    map_v32,
                    "_master_generated_at",
                    return_value="2026-07-25T00:00:00Z",
                ),
                patch.object(
                    map_v32,
                    "_runtime_timestamps",
                    side_effect=lambda *_args: nullcontext(),
                ),
                patch.object(map_v32, "tree_digest", return_value="tree"),
                patch.object(
                    map_v32,
                    "validate_construction_map_v32",
                    side_effect=validations,
                ),
                self.assertRaisesRegex(
                    map_v32.ConstructionMapV32Error,
                    "final validation",
                ),
            ):
                map_v32.publish_construction_map_v32(
                    generated_at,
                    publication_authorized=True,
                )

            self.assertFalse(definition.exists())
            self.assertFalse(bundle.exists())
            self.assertFalse(lock.exists())
            definition_stages = tuple(sources.glob(".map.json.stage-*"))
            bundle_stages = tuple(maps.glob(".map.stage-*"))
            self.assertEqual(len(definition_stages), 1)
            self.assertEqual(len(bundle_stages), 1)
            definition_stages[0].chmod(0o600)
            definition_stages[0].unlink()
            bundle_stages[0].chmod(0o700)
            for path in bundle_stages[0].rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
            shutil.rmtree(bundle_stages[0])


if __name__ == "__main__":
    unittest.main()
