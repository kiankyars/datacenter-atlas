from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v12 as map_v12
    from datacenter_atlas.datacenter_atlas import construction_master_v12 as master_v12
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v12 as map_v12
    from datacenter_atlas import construction_master_v12 as master_v12


ROOT = Path(__file__).resolve().parents[1]
V27_MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v27.json"
)
V14_MASTER_JSONL = (
    ROOT
    / "construction_master/2026-07-19-public-open-v14/construction-master.jsonl"
)
V71_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"


def checkpoint(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "bytes": len(raw),
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def projected_v28_rowstream() -> tuple[
    dict[str, object], dict[str, dict[str, object]], set[str]
]:
    document = deepcopy(json.loads(V27_MASTER_DEFINITION.read_bytes()))
    document["master_id"] = master_v12.MASTER_ID
    document["generated_at"] = master_v12.GENERATED_AT
    document["expected"].update(master_v12.EXPECTED_FIXED)
    replacement = document["inputs"]["replacement_release"]
    replacement.update(
        {
            "artifact_id": "epoch-official-open-seed-v71",
            "data": checkpoint(V71_RELEASE / "construction_pipeline.csv"),
            "definition": checkpoint(V71_DEFINITION),
            "evidence": checkpoint(V71_RELEASE / "evidence.csv"),
            "manifest": checkpoint(V71_RELEASE / "manifest.json"),
            "publication_contract_version": 4,
            "release_id": "epoch-official-open-seed-v71",
        }
    )
    resolved = {
        spec["path"]: ROOT / spec["path"]
        for lane in document["inputs"].values()
        for spec in lane.values()
        if isinstance(spec, dict) and set(spec) == {"bytes", "path", "sha256"}
    }
    rows, _invariants = master_v12._rows_and_invariants(document, resolved)

    old_ids: set[str] = set()
    with V14_MASTER_JSONL.open("rb") as source:
        for raw in source:
            row = json.loads(raw)
            if row.get("source", {}).get("artifact_id") != (
                "epoch-official-open-seed-v33"
            ):
                break
            old_ids.add(row["source"]["record_id"])
    with (V71_RELEASE / "construction_pipeline.csv").open(
        newline="", encoding="utf-8"
    ) as source:
        replacement_ids = {row["entity_id"] for row in csv.DictReader(source)}
    added = replacement_ids - old_ids
    all_ids: set[str] = set()

    def observed_rows():
        for row in rows:
            record_id = row["source"]["record_id"]
            if record_id in all_ids:
                raise AssertionError("candidate rowstream repeats a record ID")
            all_ids.add(record_id)
            yield row

    index, coverage = map_v12._core_build_index(
        observed_rows(),
        master_manifest={
            "master_id": master_v12.MASTER_ID,
            "row_counts": {"total": 109328},
        },
        master_manifest_sha256="0" * 64,
        added_source_record_ids=added,
        expected_projection=None,
    )
    projected = {
        row[map_v12.FIELDS.index("source_record_id")]: dict(
            zip(map_v12.FIELDS, row, strict=True)
        )
        for row in index["rows"]
    }
    return coverage["projection"], projected, all_ids


class ConstructionMapV28PrepTests(unittest.TestCase):
    def test_accepted_master_fuse_is_exact_and_map_paths_are_paired(self) -> None:
        expected = {
            "definition": map_v12.CANDIDATE_MASTER_DEFINITION_SHA256,
            "jsonl": map_v12.CANDIDATE_MASTER_JSONL_SHA256,
            "manifest": map_v12.CANDIDATE_MASTER_MANIFEST_SHA256,
            "tree": map_v12.CANDIDATE_MASTER_TREE_SHA256,
        }
        self.assertEqual(map_v12._accepted_master_pins(), expected)
        self.assertEqual(map_v12._require_accepted_master(), expected)
        self.assertEqual(map_v12.DEFINITION.exists(), map_v12.BUNDLE.exists())
        self.assertEqual(
            map_v12.DEFINITION.is_symlink(), map_v12.BUNDLE.is_symlink()
        )

    def test_projection_is_derived_from_the_v71_rowstream(self) -> None:
        projection, projected, all_ids = projected_v28_rowstream()
        self.assertEqual(projection, map_v12.EXPECTED_PROJECTION)
        map_v12._assert_exact_v27_delta(projected, all_ids)

        old_all_ids = map_v12._master_record_ids(
            ROOT
            / "construction_master/2026-07-21-public-open-v27/"
            "construction-master.jsonl"
        )
        additions = all_ids - old_all_ids
        old_mapped = set(
            map_v12._map_rows(
                map_v12.PREDECESSOR_BUNDLE / map_v12.INDEX_FILENAME
            )
        )
        self.assertEqual(len(additions), 15)
        self.assertEqual(
            set(projected) - old_mapped, map_v12.NEW_COORDINATE_MAPPING_IDS
        )
        self.assertEqual(
            additions - set(projected),
            additions - map_v12.NEW_COORDINATE_MAPPING_IDS,
        )
        self.assertEqual(len(additions - set(projected)), 12)

    def test_replay_gate_requires_byte_exact_second_build(self) -> None:
        with tempfile.TemporaryDirectory(prefix="map-v28-replay-test-") as temporary:
            first = Path(temporary) / "first"
            first.mkdir()
            manifest = {"format": "test"}
            (first / map_v12.MANIFEST_FILENAME).write_bytes(
                map_v12._canonical_json(manifest)
            )
            (first / "payload").write_bytes(b"same")

            def same_build(destination: Path, **_kwargs):
                (destination / map_v12.MANIFEST_FILENAME).write_bytes(
                    map_v12._canonical_json(manifest)
                )
                (destination / "payload").write_bytes(b"same")
                return manifest

            with patch.object(map_v12, "_build_bundle_stage", same_build):
                map_v12._assert_two_replays(
                    first,
                    definition_path=Path("unused"),
                    master_directory=Path("unused"),
                    master_definition_path=Path("unused"),
                )

            def changed_build(destination: Path, **_kwargs):
                (destination / map_v12.MANIFEST_FILENAME).write_bytes(
                    map_v12._canonical_json(manifest)
                )
                (destination / "payload").write_bytes(b"changed")
                return manifest

            with (
                patch.object(map_v12, "_build_bundle_stage", changed_build),
                self.assertRaisesRegex(
                    map_v12.ConstructionMapV12Error,
                    "two offline construction-map v28 reconstructions differ",
                ),
            ):
                map_v12._assert_two_replays(
                    first,
                    definition_path=Path("unused"),
                    master_directory=Path("unused"),
                    master_definition_path=Path("unused"),
                )

    def test_collision_symlink_and_future_time_guards(self) -> None:
        with tempfile.TemporaryDirectory(prefix="map-v28-guards-") as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            bundle = root / "bundle"
            definition.write_text("occupied", encoding="utf-8")
            with (
                patch.object(map_v12, "DEFINITION", definition),
                patch.object(map_v12, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v12.ConstructionMapV12Error, "refusing replacement"
                ),
            ):
                map_v12._require_unpublished()

            definition.unlink()
            definition.symlink_to(root / "missing")
            with (
                patch.object(map_v12, "DEFINITION", definition),
                patch.object(map_v12, "BUNDLE", bundle),
                self.assertRaisesRegex(
                    map_v12.ConstructionMapV12Error, "refusing replacement"
                ),
            ):
                map_v12._require_unpublished()

            regular = root / "regular"
            regular.write_bytes(b"x")
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=1)
            with self.assertRaisesRegex(
                map_v12.ConstructionMapV12Error, "post-dates"
            ):
                map_v12._path_timestamp_bounds(regular, cutoff, "test artifact")

            stage = root / "stage"
            stage.mkdir()
            (stage / "bad").symlink_to(root / "missing")
            with self.assertRaisesRegex(
                map_v12.ConstructionMapV12Error, "contaminated"
            ):
                map_v12._discard_bundle_stage(stage)

    def test_timestamp_and_reserved_path_contracts(self) -> None:
        for value in (
            "2026-07-21T10:00:00+00:00",
            "2026-07-21T10:00:00.1Z",
            "2026-07-21",
            0,
        ):
            with self.subTest(value=value), self.assertRaises(
                map_v12.ConstructionMapV12Error
            ):
                map_v12._parse_utc(value, label="test timestamp")
        with self.assertRaisesRegex(
            map_v12.ConstructionMapV12Error, "paths and frozen mode are reserved"
        ):
            map_v12.write_construction_map_v12(
                output_directory=Path("elsewhere"),
                generated_at="2099-01-01T00:00:01Z",
            )


if __name__ == "__main__":
    unittest.main()
