from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
SOURCES = {
    "curated-official-2026-07-19-digital-realty-330-east-cermak-chicago.json":
        "0fecb93df76c3a2f4ad276da3b3fc5710551f843109ea9f43971a7d57a1fa8a5",
    "curated-official-2026-07-19-digital-realty-dugny-par15.json":
        "e4e5982c65534f2c09787faade0a435d9cbf70e1e2ad706a32f1644f7d5e268e",
    "curated-official-2026-07-19-digital-realty-fra20-frankfurt.json":
        "096378e468cfd10d4ed41e25b5fe1b32fff3d2c19b8bc71df6ab51cdadb38e59",
    "curated-official-2026-07-19-digital-realty-rom1-rome.json":
        "f809518a71f8d0f4333daabab2e94534af03ea1a1b6b19cd35a91bdecd52e84e",
    "curated-official-2026-07-19-stack-northwest-louisiana-multi-campus.json":
        "c632b30f4f966e334af288f6ab6ee6684a9279fbd670406059346b939752ebfe",
}
CONTENT_HASHES = {
    "26077d3be8a69839b11998bb59c086c7e39b8a7151e1db3b90876b8a9e140245",
    "29c8aa83149888ed7f654af4d35709f6fc0279017af4cf813406bfd34baac638",
    "3c91fabbb617a5195a6643fe718ea69cfe3f92284dee94fe3e7e3337ec3da1a8",
    "6da7a22041647d901e36067838d8089c37a5cea983e3b3a14e6e3ee4451248ff",
    "941f98c52430f6e930833d366dc11a014f229bc3ea4683d222a7a9598dbe88d9",
    "a4e9b5abff02050c4f5e2f04fd1e069aa76091d92b2dcc76f97c359e7b1aca31",
    "afef5cf22f2ef3d6d0251a86caf9eb94412ea2b332dc180178463e02e1acde88",
    "eeb31f9db1fd12b01e83ee76a0e5810ec29a2acbe28670abb5e900400f8ccca3",
}
SOURCE_URLS = {
    "https://www.digitalrealty.com/about/newsroom/press-releases/123340/digital-realty-breaks-ground-in-rome-expanding-mediterranean-connectivity",
    "https://www.digitalrealty.com/about/newsroom/press-releases/19811/digital-realty-begins-construction-of-its-latest-state-of-the-art-data-center-in-frankfurt",
    "https://www.digitalrealty.com/about/newsroom/press-releases/30011/digital-realty-further-expands-mediterranean-presence-with-strategic-land-acquisitions-in-milan",
    "https://www.digitalrealty.com/about/projects/digital-cermak",
    "https://www.digitalrealty.com/about/projects/dugny-digital-hub",
    "https://www.digitalrealty.com/data-centers/emea/rome/rom1",
    "https://www.digitalrealty.com/de/data-centers/emea/frankfurt/fra20",
    "https://www.stackinfra.com/about/news-press/press-releases/stack-infrastructure-partners-with-amazon-to-invest-in-northwest-louisiana-communities/",
}


class StackDigitalRealtyConstructionTests(unittest.TestCase):
    def test_strict_physical_records_import_offline_without_scope_inference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket,
                    "socket",
                    side_effect=AssertionError("network used"),
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected_sha256 in sorted(SOURCES.items()):
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=document["evidence"][0]["retrieved_at"],
                        )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 5), ("project", 5)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:digital-realty-330-east-cermak-chicago:current-facility-build",
                            "under_construction",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:digital-realty-dugny-digital-hub",
                            "under_construction",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:digital-realty-fra20-frankfurt:current-facility-build",
                            "under_construction",
                            "2025-11-26",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:digital-realty-rom1-rome:current-facility-build",
                            "under_construction",
                            "2026-03-24",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:stack-northwest-louisiana-multi-campus-program:current-construction",
                            "under_construction",
                            "2026-06-10",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM entity_snapshots
                        WHERE latitude IS NOT NULL
                           OR longitude IS NOT NULL
                           OR geometry_json IS NOT NULL
                        """
                    ).fetchone()[0],
                    0,
                )

                snapshot_tags = [
                    json.loads(row[0])
                    for row in connection.execute("SELECT tags_json FROM entity_snapshots")
                ]
                self.assertTrue(
                    all(
                        not any(key.startswith("role:") for key in tags)
                        for tags in snapshot_tags
                    )
                )
                self.assertEqual(
                    {
                        tags["address"]
                        for tags in snapshot_tags
                    },
                    {
                        "330 E. Cermak, Chicago",
                        "Caddo and Bossier Parishes, Northwest Louisiana, United States",
                        "Dugny, France",
                        "Hugo-Junkers-Strasse 5a, 60386 Frankfurt am Main",
                        "Via delle Testuggini, 98-100, Rome",
                    },
                )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               capacity_estimates.metric,
                               capacity_estimates.stage,
                               capacity_estimates.low,
                               capacity_estimates.base,
                               capacity_estimates.high,
                               capacity_estimates.unit,
                               capacity_estimates.as_of_date
                        FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:digital-realty-dugny-digital-hub",
                            "critical_it_mw",
                            "planned",
                            176.0,
                            176.0,
                            176.0,
                            "MW",
                            "2026-07-19",
                        ),
                        (
                            "curated:digital-realty-fra20-frankfurt:current-facility-build",
                            "critical_it_mw",
                            "planned",
                            16.0,
                            16.0,
                            16.0,
                            "MW",
                            "2025-11-26",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        WHERE entities.stable_key LIKE '%rom1%'
                        """
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
                    0,
                )

                self.assertEqual(
                    {row[0] for row in connection.execute("SELECT source_url FROM evidence")},
                    SOURCE_URLS,
                )
                self.assertEqual(
                    {row[0] for row in connection.execute("SELECT content_hash FROM evidence")},
                    CONTENT_HASHES,
                )

                evidence_metadata = {
                    row["source_url"]: json.loads(row["metadata_json"])["record"]
                    for row in connection.execute(
                        "SELECT source_url, metadata_json FROM evidence"
                    )
                }
                fra20_url = next(url for url in SOURCE_URLS if "/19811/" in url)
                self.assertEqual(
                    evidence_metadata[fra20_url]["displayed_page_date"],
                    "2025-11-26",
                )
                self.assertEqual(
                    evidence_metadata[fra20_url]["body_dateline"],
                    "2025-11-27",
                )
                rom1_groundbreaking_url = next(
                    url for url in SOURCE_URLS if "/123340/" in url
                )
                self.assertIn(
                    "no open-bound qualifier",
                    evidence_metadata[rom1_groundbreaking_url][
                        "capacity_schema_guardrail"
                    ],
                )
                stack_url = next(url for url in SOURCE_URLS if "stackinfra.com" in url)
                self.assertIn(
                    "One multi-campus program is modeled",
                    evidence_metadata[stack_url]["program_scope"],
                )
                dugny_url = next(url for url in SOURCE_URLS if "dugny" in url)
                self.assertIn(
                    "lifecycle is attached only to the campus entity",
                    evidence_metadata[dugny_url]["status_scope"],
                )
                cermak_url = next(url for url in SOURCE_URLS if "digital-cermak" in url)
                self.assertIn(
                    "separate from the modeled 330 E. Cermak build",
                    evidence_metadata[cermak_url]["separation_guardrail"],
                )

                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
