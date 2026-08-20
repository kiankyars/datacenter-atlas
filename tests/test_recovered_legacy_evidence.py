from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
QUEUE_MANIFEST_SHA256 = (
    "58c39d64510f37fda8eaf6912ed36001845f276239dcaeec0ea24ba4a6a2836c"
)

EXPECTED_INVENTORIES = {
    "satellite_evidence": {
        "README.md": "5de4e706d20e0e06d9eea7f13bbe51e708b1837747991114c81226603494f58d",
        "colossus-2-2024-2026/README.md": "c147028f525c58afb51c05fd1f6a41a077ab2e955be6a1062a5c8036f6fcad06",
        "colossus-2-2024-2026/catalog/baseline-response.json": "9f1690b96565e6caaa4fa79900ff73f45d5115cecd6c59cc4ef04ae191d2ba77",
        "colossus-2-2024-2026/catalog/current-response.json": "ef9f43b692144c65b87257577c6b780c5cc907d64d7082a5ee678c2897c66fc9",
        "colossus-2-2024-2026/catalog/manifest.json": "12d79f260a1f23c6788a85af0015e2d88a1ee2422410c24ad88cf7b66a99e6e7",
        "colossus-2-2024-2026/change/after.png": "5629026fdb6ac578f58a5d12d1d91b00517e5552a8bc01205024585ad620abec",
        "colossus-2-2024-2026/change/before.png": "d4a1381b14989269826f586c0d9a1d726067f0194d273e9efcd43567892c3d63",
        "colossus-2-2024-2026/change/change-overlay.png": "7b147af2ea5f4dfb6299c28649b318f6de9388b11bb5609284297f3edc50e46a",
        "colossus-2-2024-2026/change/change-proposals.geojson": "d48fc1a88608425e28f12cce2bfe298164960a8ee88e700983506263f893edd7",
        "colossus-2-2024-2026/change/comparison.png": "219977c807dc5630428787292e41ce7d94441601deef8e5ed1ed391116c2ff9e",
        "colossus-2-2024-2026/change/report.json": "6524657da26a4224f061bfcae0612ff9583d8524c7142fa6c28c4a2c4b560a57",
        "docklands-2024-2026/README.md": "9bf34bcbf141c369b669db3de64ab8cc7770b04d202e9dc7363067d0ce1af79c",
        "docklands-2024-2026/catalog/baseline-response.json": "0bb4a9634e427b7a123acb90868a1051b41e06c5abe4c0c33c341bf48ded0d7e",
        "docklands-2024-2026/catalog/current-response.json": "00779b3f45e51061152b820daeee46cfc4ca252d19a99a37c88f23414df68eae",
        "docklands-2024-2026/catalog/manifest.json": "5e7ed5e6b29ff243e7a9a7b39f308ede554543ae2b24d459c0fd11249c8f5607",
        "docklands-2024-2026/change/after.png": "a11f42651af746a64c8085f2259db89c24c83951b91f996127530741c6fe925f",
        "docklands-2024-2026/change/before.png": "e8337284ba93d4e611ae721ceefc047c9122ce667334b7ac9106076770302012",
        "docklands-2024-2026/change/change-overlay.png": "1919ed0f2c39a9f8abd968f6d7e83619695ffe790234aa18bec8951e8652b825",
        "docklands-2024-2026/change/change-proposals.geojson": "d3fd5fc9cdd4f8e07e89b4f42cfab501798e998bd3b540893da3892abe02594b",
        "docklands-2024-2026/change/comparison.png": "b8e169e9208b318ed4d3a7ab345d99d279d283810678ac254bdc8f5512207bec",
        "docklands-2024-2026/change/report.json": "1a230113214244be4e70fecaaf439eabb979f70dd8d6f60579323004a17b23c6",
    },
    "satellite_change_selections": {
        "2026-07-18-global-open-v3-active-exclusions-v1.json": "8f6155b9720ce78b8536748294f37ed10079fa496a9f08d26f80e89a36446a6f",
        "2026-07-18-global-open-v3-active-exclusions-v2.json": "08e98a2e11c8181d17cb0d8d8076efafd57616ae595ff1ce4ec9274932c9473a",
        "2026-07-18-global-open-v3-active-exclusions-v3.json": "829d5a0e6c7fa6897423d04cde58e1fdfca62e9ea1d4a04e96658769c56e5bb1",
        "README.md": "f9db226b3762533d0e9c391db52e2049568e80fa3a5a1aa9dbdd85488520eedb",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecoveredLegacyEvidenceTests(unittest.TestCase):
    def test_closed_inventories_and_source_hashes(self) -> None:
        for directory, expected in EXPECTED_INVENTORIES.items():
            root = ROOT / directory
            actual = {
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, set(expected), directory)
            for relative_path, expected_hash in expected.items():
                with self.subTest(path=f"{directory}/{relative_path}"):
                    self.assertEqual(_sha256(root / relative_path), expected_hash)

    def test_json_and_png_files_are_structurally_readable(self) -> None:
        for directory, expected in EXPECTED_INVENTORIES.items():
            root = ROOT / directory
            for relative_path in expected:
                path = root / relative_path
                with self.subTest(path=f"{directory}/{relative_path}"):
                    if path.suffix in {".json", ".geojson"}:
                        with path.open(encoding="utf-8") as handle:
                            json.load(handle)
                    elif path.suffix == ".png":
                        self.assertEqual(path.read_bytes()[:8], PNG_SIGNATURE)

    def test_satellite_evidence_embedded_hashes(self) -> None:
        evidence_root = ROOT / "satellite_evidence"
        expected_outputs = {
            "after.png",
            "before.png",
            "change-overlay.png",
            "change-proposals.geojson",
            "comparison.png",
        }
        for pilot in ("colossus-2-2024-2026", "docklands-2024-2026"):
            pilot_root = evidence_root / pilot
            with (pilot_root / "catalog/manifest.json").open(
                encoding="utf-8"
            ) as handle:
                catalog_manifest = json.load(handle)
            for period in ("baseline", "current"):
                response = pilot_root / f"catalog/{period}-response.json"
                self.assertEqual(
                    _sha256(response),
                    catalog_manifest["queries"][period]["raw_response_sha256"],
                )

            with (pilot_root / "change/report.json").open(
                encoding="utf-8"
            ) as handle:
                report = json.load(handle)
            self.assertEqual(set(report["outputs"]), expected_outputs)
            for filename, metadata in report["outputs"].items():
                output = pilot_root / "change" / filename
                with self.subTest(pilot=pilot, output=filename):
                    self.assertEqual(output.stat().st_size, metadata["bytes"])
                    self.assertEqual(_sha256(output), metadata["sha256"])

    def test_selection_inputs_bind_the_preserved_queue_manifest(self) -> None:
        queue_manifest = (
            ROOT
            / "satellite_review_queues/2026-07-18-global-open-v3/manifest.json"
        )
        if queue_manifest.is_file():
            self.assertEqual(_sha256(queue_manifest), QUEUE_MANIFEST_SHA256)
        selections_root = ROOT / "satellite_change_selections"
        expected_counts = {
            "2026-07-18-global-open-v3-active-exclusions-v1.json": 12,
            "2026-07-18-global-open-v3-active-exclusions-v2.json": 22,
            "2026-07-18-global-open-v3-active-exclusions-v3.json": 44,
        }
        for filename, expected_count in expected_counts.items():
            with (selections_root / filename).open(encoding="utf-8") as handle:
                selection = json.load(handle)
            with self.subTest(filename=filename):
                self.assertEqual(selection["schema_version"], 1)
                self.assertEqual(
                    selection["purpose"], "satellite_change_batch_exclusions"
                )
                self.assertEqual(
                    selection["queue_manifest_sha256"], QUEUE_MANIFEST_SHA256
                )
                self.assertEqual(len(selection["queue_ids"]), expected_count)
                self.assertEqual(
                    len(selection["queue_ids"]), len(set(selection["queue_ids"]))
                )


if __name__ == "__main__":
    unittest.main()
