from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys
import unittest

import datacenter_atlas


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_SHIM = Path(datacenter_atlas.__file__).resolve() == ROOT / "__init__.py"


class WorkspaceShimTests(unittest.TestCase):
    @unittest.skipUnless(WORKSPACE_SHIM, "workspace aliases apply when importing from the repository parent")
    def test_reviewed_release_and_consolidation_modules_share_one_identity(self) -> None:
        for name in (
            "consolidation", "dataset_update", "project_details", "public_site", "publication_pair_v32",
            "verified_construction_core_v017", "verified_construction_core_v018",
            "expansion_200_initial_three", "expansion_200_thirty_fifth_reviewed", "expansion_200_thirty_seventh_reviewed",
        ):
            with self.subTest(module=name):
                public = importlib.import_module(f"datacenter_atlas.{name}")
                nested = importlib.import_module(f"datacenter_atlas.datacenter_atlas.{name}")
                self.assertIs(public, nested)
                self.assertIs(getattr(sys.modules["datacenter_atlas"], name), nested)

    @unittest.skipUnless(WORKSPACE_SHIM, "workspace aliases apply when importing from the repository parent")
    def test_public_and_nested_timestamp_modules_share_one_identity(self) -> None:
        public = importlib.import_module("datacenter_atlas.timestamps")
        nested = importlib.import_module(
            "datacenter_atlas.datacenter_atlas.timestamps"
        )
        public_repository = importlib.import_module("datacenter_atlas.repository")
        nested_repository = importlib.import_module(
            "datacenter_atlas.datacenter_atlas.repository"
        )
        public_europe = importlib.import_module(
            "datacenter_atlas.europe_latam_official_discovery_20260721"
        )
        nested_europe = importlib.import_module(
            "datacenter_atlas.datacenter_atlas.europe_latam_official_discovery_20260721"
        )

        self.assertIs(public, nested)
        self.assertIs(public_repository, nested_repository)
        self.assertIs(sys.modules["datacenter_atlas.timestamps"], public)
        self.assertIs(
            sys.modules["datacenter_atlas.datacenter_atlas.timestamps"], public
        )
        self.assertIs(
            public.canonical_read_cutoff,
            nested.canonical_read_cutoff,
        )
        self.assertIs(
            public.canonical_persistence_write,
            nested.canonical_persistence_write,
        )
        self.assertIs(public._state_cache, nested._state_cache)
        self.assertIs(
            public_repository.canonical_storage_timestamp,
            public.canonical_storage_timestamp,
        )
        self.assertIs(
            public_europe._validate_captures,
            nested_europe._validate_captures,
        )

    def test_installable_package_imports_without_workspace_aliases(self) -> None:
        code = """
from pathlib import Path
import datacenter_atlas
from datacenter_atlas import consolidation, dataset_update, expansion_200_thirty_fifth_reviewed, models, project_details, public_site
assert Path(datacenter_atlas.__file__).resolve() == Path.cwd() / 'datacenter_atlas' / '__init__.py'
assert datacenter_atlas.LifecycleStatus is models.LifecycleStatus
assert consolidation.ROOT == dataset_update.ROOT == Path.cwd()
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
