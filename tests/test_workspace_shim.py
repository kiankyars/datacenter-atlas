from __future__ import annotations

import importlib
import sys
import unittest


class WorkspaceShimTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
