from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_calibration_aggregate import (
    MULTITILE_MARKER,
    RELEASE_FILES,
    SatelliteCalibrationAggregateError,
    _cleanup_staging,
    _definition_project_root,
    _freeze_tree,
    _inside_project,
    _release_rows,
    _source_state,
    _validate_multitile_failure,
    _validate_release_tree,
    canonical_json,
    canonical_line,
    validate_satellite_calibration_aggregate,
    write_satellite_calibration_aggregate,
)


def _runtime(marker: str = "pinned") -> dict:
    return {"marker": marker}


def _definition() -> dict:
    return {
        "preparation": {"directory": "prep"},
        "release_id": "fixture-v2-aggregate-v1",
        "shards": [{"directory": f"shards/{index}"} for index in range(10)],
    }


def _rows() -> list[dict]:
    result = []
    for index in range(43):
        blind_id = f"v2rr-{index:024x}"
        base = {
            "aoi_bbox_wgs84": [float(index), 1.0, float(index) + 0.5, 1.5],
            "blind_item_id": blind_id,
            "entity": {"id": f"entity-{index}", "name": f"Entity {index}"},
            "rerun_spec_sha256": f"{index:064x}",
            "schema_version": 1,
            "selected_scenes": {
                "baseline": {"id": f"b-{index}", "stac_item_sha256": "a" * 64},
                "current": {"id": f"c-{index}", "stac_item_sha256": "b" * 64},
            },
            "source_shard": {
                "manifest_sha256": f"{index // 5:064x}",
                "path": f"shards/{index // 5}",
            },
            "attempts": 1,
        }
        if index < 36:
            result.append(
                {
                    **base,
                    "artifacts": {
                        "comparison.png": {
                            "bytes": 1,
                            "path": f"shards/{index // 5}/jobs/{blind_id}/change/comparison.png",
                            "sha256": "c" * 64,
                        }
                    },
                    "failure_evidence_sha256": None,
                    "state": "ready_for_blind_review",
                }
            )
        else:
            result.append(
                {
                    **base,
                    "artifacts": None,
                    "blocker": "aoi_crosses_scene_asset_requires_multitile_mosaic",
                    "failure_evidence_sha256": "d" * 64,
                    "state": "blocked_multitile_required",
                }
            )
    return result


class SatelliteCalibrationAggregateReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "sources").mkdir()
        self.definition_path = self.root / "sources" / "aggregate.json"
        self.definition_path.write_bytes(canonical_json({"fixture": True}))
        os.chmod(self.definition_path, 0o444)
        self.output = self.root / "releases" / "aggregate"
        self.output.parent.mkdir()
        self.state = (_definition(), self.root, _rows(), _runtime(), self.root / "prep")
        self.builder_patch = patch(
            "datacenter_atlas.satellite_calibration_aggregate._builder_files",
            return_value={"fixture.py": {"bytes": 1, "sha256": "f" * 64}},
        )
        self.source_patch = patch(
            "datacenter_atlas.satellite_calibration_aggregate._source_state",
            return_value=self.state,
        )
        self.builder_patch.start()
        self.source_patch.start()

    def tearDown(self) -> None:
        self.source_patch.stop()
        self.builder_patch.stop()
        if self.output.exists():
            _cleanup_staging(self.output)
        os.chmod(self.definition_path, 0o644)
        self.temporary.cleanup()

    def _build(self) -> dict:
        return write_satellite_calibration_aggregate(
            self.output, definition_path=self.definition_path
        )

    def test_atomic_publish_freezes_exact_closed_release(self) -> None:
        manifest = self._build()
        self.assertEqual(manifest["summary"]["blind_items_ready_for_review"], 36)
        self.assertEqual(manifest["summary"]["blind_items_blocked_multitile"], 7)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o555)
        self.assertEqual({path.name for path in self.output.iterdir()}, RELEASE_FILES)
        self.assertTrue(
            all(path.stat().st_mode & 0o777 == 0o444 for path in self.output.iterdir())
        )
        validate_satellite_calibration_aggregate(
            self.output, definition_path=self.definition_path
        )

    def test_semantic_tamper_and_recomputed_sidecar_are_rejected(self) -> None:
        self._build()
        os.chmod(self.output, 0o755)
        summary_path = self.output / "summary.json"
        manifest_path = self.output / "manifest.json"
        sidecar_path = self.output / "manifest.sha256"
        for path in (summary_path, manifest_path, sidecar_path):
            os.chmod(path, 0o644)
        summary = json.loads(summary_path.read_text())
        summary["numerical_items"] = 42
        summary_path.write_bytes(canonical_json(summary))
        os.chmod(summary_path, 0o444)
        manifest = json.loads(manifest_path.read_text())
        manifest["summary"] = summary
        raw = summary_path.read_bytes()
        manifest["outputs"]["summary.json"] = {
            "bytes": len(raw),
            "mode": "0444",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        manifest_raw = canonical_json(manifest)
        manifest_path.write_bytes(manifest_raw)
        sidecar_path.write_text(
            f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
        )
        os.chmod(manifest_path, 0o444)
        os.chmod(sidecar_path, 0o444)
        os.chmod(self.output, 0o555)
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "summary.json differs"):
            validate_satellite_calibration_aggregate(
                self.output, definition_path=self.definition_path
            )

    def test_label_leakage_in_reviewer_queue_is_rejected_even_if_rehashed(self) -> None:
        self._build()
        os.chmod(self.output, 0o755)
        queue_path = self.output / "reviewer-queue.jsonl"
        manifest_path = self.output / "manifest.json"
        sidecar_path = self.output / "manifest.sha256"
        for path in (queue_path, manifest_path, sidecar_path):
            os.chmod(path, 0o644)
        lines = queue_path.read_bytes().splitlines()
        first = json.loads(lines[0])
        first["decision"] = "retain"
        lines[0] = canonical_line(first).rstrip(b"\n")
        queue_path.write_bytes(b"\n".join(lines) + b"\n")
        os.chmod(queue_path, 0o444)
        manifest = json.loads(manifest_path.read_text())
        raw = queue_path.read_bytes()
        manifest["outputs"]["reviewer-queue.jsonl"] = {
            "bytes": len(raw),
            "mode": "0444",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        manifest_raw = canonical_json(manifest)
        manifest_path.write_bytes(manifest_raw)
        sidecar_path.write_text(
            f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
        )
        os.chmod(manifest_path, 0o444)
        os.chmod(sidecar_path, 0o444)
        os.chmod(self.output, 0o555)
        with self.assertRaisesRegex(
            SatelliteCalibrationAggregateError, "reviewer-queue.jsonl differs"
        ):
            validate_satellite_calibration_aggregate(
                self.output, definition_path=self.definition_path
            )

    def test_extra_file_and_mode_drift_are_rejected(self) -> None:
        self._build()
        os.chmod(self.output, 0o755)
        extra = self.output / "extra.json"
        extra.write_text("{}\n")
        os.chmod(extra, 0o444)
        os.chmod(self.output, 0o555)
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "not closed"):
            _validate_release_tree(self.output)
        os.chmod(self.output, 0o755)
        extra.unlink()
        os.chmod(self.output / "summary.json", 0o644)
        os.chmod(self.output, 0o555)
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "mode mismatch"):
            _validate_release_tree(self.output)

    def test_symlink_is_rejected(self) -> None:
        self._build()
        os.chmod(self.output, 0o755)
        readme = self.output / "README.md"
        os.chmod(readme, 0o644)
        readme.unlink()
        readme.symlink_to(self.output / "ATTRIBUTION.txt")
        os.chmod(self.output, 0o555)
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "symlink"):
            _validate_release_tree(self.output)


class SatelliteCalibrationAggregatePolicyTests(unittest.TestCase):
    def test_release_rows_are_label_blind_and_partitioned(self) -> None:
        inventory, reviewers, blocked = _release_rows(_rows())
        self.assertEqual((len(inventory), len(reviewers), len(blocked)), (43, 36, 7))
        encoded = canonical_jsonl_for_test([*reviewers, *blocked])
        self.assertNotIn(b"historical_queue_id", encoded)
        self.assertNotIn(b"historical_identity_sha256", encoded)
        self.assertNotIn(b'"decision"', encoded)
        self.assertNotIn(b'"outcome"', encoded)

    def test_direct_label_key_is_rejected(self) -> None:
        rows = _rows()
        rows[0]["decision"] = "retain"
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "forbidden"):
            _release_rows(rows)

    def test_only_explicit_multitile_process_failure_is_accepted(self) -> None:
        _validate_multitile_failure(
            {
                "kind": "process_exit",
                "returncode": 1,
                "stderr_tail": f"ValueError: {MULTITILE_MARKER}\n",
            }
        )
        for failure in (
            {"kind": "timeout", "timeout_seconds": 1},
            {"kind": "process_exit", "returncode": 1, "stderr_tail": "other"},
        ):
            with self.assertRaises(SatelliteCalibrationAggregateError):
                _validate_multitile_failure(failure)

    def test_source_symlink_alias_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            target = root / "target"
            target.mkdir()
            (root / "alias").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "symlink"):
                _inside_project(root, "alias/source.json", "source")

    def test_definition_symlink_alias_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sources = root / "sources"
            sources.mkdir()
            alias = root / "alias"
            alias.symlink_to(sources, target_is_directory=True)
            with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "inside sources"):
                _definition_project_root(alias / "aggregate.json")


def canonical_jsonl_for_test(rows: list[dict]) -> bytes:
    return b"".join(canonical_line(row) for row in rows)


class SatelliteCalibrationAggregateSourcePartitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "sources").mkdir()
        (self.root / "prep").mkdir()
        (self.root / "shards").mkdir()
        for index in range(10):
            (self.root / "shards" / str(index)).mkdir()
        self.definition_path = self.root / "sources" / "aggregate.json"
        self.definition_path.write_text("{}\n")
        self.definition = _definition()
        self.specs = [{"blind_item_id": f"v2rr-{index:024x}"} for index in range(43)]
        self.ranges = [
            (0, 1),
            (1, 6),
            (6, 11),
            (11, 16),
            (16, 21),
            (21, 26),
            (26, 31),
            (31, 36),
            (36, 41),
            (41, 43),
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, ranges=None, definition=None, current_runtime=None):
        ranges = ranges or self.ranges
        definition = definition or self.definition
        calls = iter(ranges)

        def validate_shard(shard, *_args, **_kwargs):
            interval = next(calls)
            rows = _rows()[interval[0] : interval[1]]
            return interval, _runtime(), rows

        with (
            patch(
                "datacenter_atlas.satellite_calibration_aggregate._load_definition",
                return_value=(definition, self.root),
            ),
            patch(
                "datacenter_atlas.satellite_calibration_aggregate._load_preparation",
                return_value=(self.root / "prep", self.specs, {}),
            ),
            patch(
                "datacenter_atlas.satellite_calibration_aggregate._validate_shard",
                side_effect=validate_shard,
            ),
            patch(
                "datacenter_atlas.satellite_calibration_aggregate._runtime_lineage",
                return_value=current_runtime or _runtime(),
            ),
        ):
            return _source_state(self.definition_path)

    def test_exact_ten_shard_partition_is_accepted(self) -> None:
        state = self._run()
        self.assertEqual(len(state[2]), 43)

    def test_overlap_and_missing_range_are_rejected(self) -> None:
        ranges = copy.deepcopy(self.ranges)
        ranges[2] = (5, 11)
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "exact 43-spec partition"):
            self._run(ranges=ranges)

    def test_duplicate_shard_path_is_rejected(self) -> None:
        definition = copy.deepcopy(self.definition)
        definition["shards"][9]["directory"] = "shards/8"
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "duplicated"):
            self._run(definition=definition)

    def test_path_overlap_is_rejected(self) -> None:
        definition = copy.deepcopy(self.definition)
        definition["shards"][0]["directory"] = "prep/child"
        (self.root / "prep" / "child").mkdir()
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "overlaps"):
            self._run(definition=definition)

    def test_runtime_drift_is_rejected(self) -> None:
        with self.assertRaisesRegex(SatelliteCalibrationAggregateError, "runtime drifted"):
            self._run(current_runtime=_runtime("drifted"))


if __name__ == "__main__":
    unittest.main()
