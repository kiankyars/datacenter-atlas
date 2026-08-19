from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

from datacenter_atlas import europe_latam_official_discovery_20260721 as europe_v1
from datacenter_atlas import europe_latam_official_discovery_temporal_v2 as europe_v2
from datacenter_atlas import site_coordinate_assessment_v5 as coordinate_v5
from datacenter_atlas.external_captures import DEFAULT_PACKAGE_ROOT


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PAYLOAD = DEFAULT_PACKAGE_ROOT / "payload"


def _load_script(module_name: str, filename: str):
    scripts = str(SCRIPTS)
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            module_name,
            SCRIPTS / filename,
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts)


@unittest.skipUnless(PAYLOAD.is_dir(), "external capture payload is not installed")
class ExternalCaptureReplayTests(unittest.TestCase):
    def test_europe_capture_replay_preserves_pinned_content_and_times(self) -> None:
        capture = europe_v1.resolve_external_capture(
            europe_v1.CAPTURE_ORIGIN,
            europe_v1.CAPTURE_TRASH,
        )
        self.assertNotEqual(capture, europe_v2.CAPTURE_TRASH)
        europe_v1._validate_captures(capture)
        europe_v2._validate_raw_capture()

    def test_coordinate_v3_capture_replay(self) -> None:
        builder = _load_script(
            "external_capture_replay_coordinate_v3",
            "build_coordinate_assessment_2026_07_21_v3.py",
        )
        builder._verify_capture_tree()
        for witness in (
            builder.SIMBIO_SEIA_WITNESS,
            builder.SIMBIO_CONTEXT_WITNESS,
            builder.FORTALEZA_WITNESS,
        ):
            builder._verify_capture_witness(witness)

    def test_coordinate_v4_rows_reproduce_historical_times(self) -> None:
        builder = _load_script(
            "external_capture_replay_coordinate_v4",
            "build_coordinate_assessment_2026_07_21_v4.py",
        )
        rows = builder._capture_rows(builder._capture_root())
        by_name = {row["capture_name"]: row for row in rows}
        self.assertEqual(set(by_name), set(builder.CAPTURE_MTIME_EPOCHS))
        for name, row in by_name.items():
            expected_mtime = builder.CAPTURE_MTIME_EPOCHS[name]
            self.assertEqual(row["mtime_epoch"], expected_mtime)
            self.assertEqual(
                row["birth_epoch"],
                builder.CAPTURE_BIRTH_EPOCH_OVERRIDES.get(
                    name,
                    expected_mtime,
                ),
            )

        frozen_inventory = builder.ARTIFACT_DIR / "retrieval-inventory.json"
        if frozen_inventory.is_file():
            expected = {
                carrier["capture_name"]: carrier
                for request in json.loads(frozen_inventory.read_text())["requests"]
                for carrier in request["carriers"].values()
            }
            self.assertEqual(by_name, expected)

    def test_coordinate_v5_rows_reproduce_pinned_carriers(self) -> None:
        rows = coordinate_v5._capture_rows(coordinate_v5._capture_root())
        observed = {
            row["capture_name"]: (
                row["bytes"],
                row["sha256"],
                row["birth_epoch"],
                row["mtime_epoch"],
            )
            for row in rows
        }
        self.assertEqual(observed, coordinate_v5.CAPTURE_FILES)


if __name__ == "__main__":
    unittest.main()
