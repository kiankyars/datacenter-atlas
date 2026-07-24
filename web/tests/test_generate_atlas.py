from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures") / "atlas_minimal.geojson"
SPEC = importlib.util.spec_from_file_location("generate_atlas", WEB_ROOT / "generate_atlas.py")
assert SPEC and SPEC.loader
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


class GenerateAtlasTests(unittest.TestCase):
    def test_loads_feature_collection(self) -> None:
        atlas = GENERATOR.load_feature_collection(FIXTURE)
        self.assertEqual(atlas["type"], "FeatureCollection")
        self.assertEqual(len(atlas["features"]), 2)

    def test_script_serialization_blocks_script_termination(self) -> None:
        serialized = GENERATOR.serialize_for_script(
            {"type": "FeatureCollection", "features": [], "label": "</script>&\u2028"}
        )
        self.assertNotIn("</script>", serialized)
        self.assertNotIn("&", serialized)
        self.assertNotIn("\u2028", serialized)
        self.assertEqual(json.loads(serialized)["label"], "</script>&\u2028")

    def test_generates_embedded_data_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "atlas.html"
            GENERATOR.generate(FIXTURE, output)
            page = output.read_text(encoding="utf-8")

        self.assertIn('<script id="atlas-data" type="application/json">', page)
        self.assertIn('"id":"campus-test-1"', page)
        self.assertNotIn(GENERATOR.DATA_PLACEHOLDER, page)
        self.assertNotIn("fetch(", page)
        self.assertNotIn("XMLHttpRequest", page)
        self.assertIn("geoNaturalEarth1", page)
        self.assertIn("@d3-maps/atlas@1.0.0/world/countries/countries-110m", page)

    def test_rejects_non_feature_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text('{"type":"Feature"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "FeatureCollection"):
                GENERATOR.load_feature_collection(path)

    def test_generated_map_is_added_to_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "atlas.html"
            (root / "manifest.json").write_text(
                json.dumps({"files": {}}), encoding="utf-8"
            )
            GENERATOR.generate(FIXTURE, output)
            manifest = json.loads((root / "manifest.json").read_text())
            raw = output.read_bytes()
            self.assertEqual(manifest["files"]["atlas.html"]["bytes"], len(raw))
            self.assertEqual(
                manifest["files"]["atlas.html"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
