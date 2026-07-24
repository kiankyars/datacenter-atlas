from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.osm import OpenStreetMapAdapter
from datacenter_atlas.publication_release import (
    build_release_documents,
    write_release,
)


class PublicationTimestampBoundaryTests(unittest.TestCase):
    def test_publication_contracts_canonicalize_equivalent_cutoffs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                OpenStreetMapAdapter().import_file(
                    connection,
                    Path(__file__).parent / "fixtures" / "osm_minimal.json",
                    retrieved_at="2026-07-17T12:00:00Z",
                )
                for version in (1, 2, 3, 4):
                    with self.subTest(publication_contract_version=version):
                        canonical = build_release_documents(
                            connection,
                            as_of="2026-07-17",
                            recorded_at="2026-07-17T13:00:00Z",
                            publication_contract_version=version,
                        )
                        equivalent = build_release_documents(
                            connection,
                            as_of="2026-07-17",
                            recorded_at="2026-07-17T14:00:00.000+01:00",
                            publication_contract_version=version,
                        )
                        self.assertEqual(equivalent, canonical)
                        self.assertEqual(
                            json.loads(equivalent["manifest.json"])["recorded_at"],
                            "2026-07-17T13:00:00Z",
                        )

                written = write_release(
                    connection,
                    root / "release",
                    as_of="2026-07-17",
                    recorded_at="2026-07-17T14:00:00.000+01:00",
                    publication_contract_version=4,
                )
                self.assertEqual(written["recorded_at"], "2026-07-17T13:00:00Z")

                for cutoff in (
                    "2026-07-17T13:00:00.500000Z",
                    "2026-07-17T13:00:00.0000001Z",
                ):
                    with self.subTest(rejected_cutoff=cutoff):
                        with self.assertRaisesRegex(
                            ValueError, "whole-second precision"
                        ):
                            build_release_documents(
                                connection,
                                as_of="2026-07-17",
                                recorded_at=cutoff,
                                publication_contract_version=4,
                            )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
