from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackageLayoutTests(unittest.TestCase):
    def test_repository_root_has_no_python_modules(self) -> None:
        self.assertEqual(list(ROOT.glob("*.py")), [])

    def test_package_import_has_one_identity_and_does_not_load_legacy_builders(self) -> None:
        code = """
from pathlib import Path
import sys
import datacenter_atlas
from datacenter_atlas import models
assert Path(datacenter_atlas.__file__).resolve() == Path(sys.argv[1]) / 'datacenter_atlas' / '__init__.py'
assert datacenter_atlas.LifecycleStatus is models.LifecycleStatus
assert models.LifecycleStatus.__module__ == 'datacenter_atlas.models'
assert 'datacenter_atlas.current_coverage_v20' not in sys.modules
assert not any(name.startswith('datacenter_atlas.datacenter_atlas') for name in sys.modules)
"""
        with tempfile.TemporaryDirectory() as elsewhere:
            for cwd in (ROOT, Path(elsewhere)):
                with self.subTest(cwd=cwd):
                    result = subprocess.run(
                        [sys.executable, "-c", code, str(ROOT)], cwd=cwd,
                        env={**os.environ, 'PYTHONPATH': str(ROOT)},
                        text=True, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_runs_from_checkout(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "datacenter_atlas", "--help"],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("datacenter-atlas", result.stdout)

    def test_enrichment_entry_point_uses_the_package_loader(self) -> None:
        name = "datacenter_atlas.goodman_databank_lax01_official_enrichment_20260722"
        spec = importlib.util.find_spec(name)
        self.assertIsNotNone(spec.loader.get_code(name))


if __name__ == "__main__":
    unittest.main()
