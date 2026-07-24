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
    "curated-official-2026-07-19-microsoft-local-boyd-farms-nc.json":
        "56e9dd61d607ba1f131633787d8f0713b6ce8d80b55bbf350c34175d9b855db2",
    "curated-official-2026-07-19-microsoft-local-heath-oh.json":
        "7baa853f3fbaa2c2c2a8ae9acade07066dcc68ead8dc70c30be18a7a3ca4f078",
    "curated-official-2026-07-19-microsoft-local-hebron-oh.json":
        "0b4cb18b64ac7858fc098994e110043ef6c745ea020a5f8d9cbc85a953e449a2",
    "curated-official-2026-07-19-microsoft-local-koge-phase-2-denmark.json":
        "92783c9bc0e6bceda588c3c414aca47994000dd5b64477ea9837fa38bd732aa1",
    "curated-official-2026-07-19-microsoft-local-new-albany-oh.json":
        "1c4037db5728baf062b739a5eee0ce423c681b51225cffcc79973c8b94813ac6",
    "curated-official-2026-07-19-microsoft-local-northwest-hortolandia-brazil.json":
        "46aa032296f076898c851ee00187e1f592cccde2c0f28342b471dbad0eadbb5c",
    "curated-official-2026-07-19-microsoft-local-san-bovio-italy.json":
        "00c9e055f0df79ea1226033b40aca969f8b2948e5f5b4d9f8a913ea735f11e9f",
    "curated-official-2026-07-19-microsoft-local-southwest-hortolandia-brazil.json":
        "291e22ec999df35161432d69d5e744f761167939c8d00832a48a3a7d080dddbe",
    "curated-official-2026-07-19-microsoft-local-stover-hickory-nc.json":
        "cce2c35cfe6db14787b0577277ebffaae83ad464be7244303afb2fb7023b76c9",
    "curated-official-2026-07-19-microsoft-local-sumare-east-brazil.json":
        "7b500dfd59682e2a4155adfab32547ec3afefff578b670ddfb1091b1047a4b48",
}
CONTENT_HASHES = {
    "13110258be455213c41e734c003cd4441c140610eeca6a165d7166613678cb51",
    "2b2c4f915e8204a7bc4946860b4803961a22be78d50bc476c90946fee6b0f104",
    "4fcfb1a9b1f146ac4c280dce6a572a61a06c57a7a27dbbac36c31e25cea8bd0b",
    "6192e61642f75629465c903d6c210c8457400a7745936d91cf08fed1f7cd1221",
    "68c02c64d943b027aedcb8e387b7dfb879d6389a000933a4f86c5ff1e9f42510",
    "69670e37c59258cabf6f0a491cd24505e7273b481409ec10ec5c09766b6ec084",
    "8dd20a8d7323ca08508cf4c2515f36fcb0d81577e8e75a73cb22485afbf286d6",
    "8fd2a41e978d0e9afb1bba0fa0921379ab9f1e2431b54290aa2640c2cfcf8bc5",
    "bb360441ea52b9f4d23ed6ee7c45c39ddc98eb20dc25991999f9726d84fb02e2",
    "c73ef71a24f7c016cad524ef550e1c2ec332baf5668618582a087c913e015c40",
}


class MicrosoftLocalCurrentConstructionTests(unittest.TestCase):
    def test_current_physical_stages_import_without_inferred_coordinates_or_metrics(self) -> None:
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
                    [("campus", 10), ("project", 10)],
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
                            "curated:microsoft-boyd-farms-maiden-nc-datacenter:current-development",
                            "foundations",
                            "2026-05-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-heath-oh-datacenter:initial-site-preparation",
                            "site_preparation",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-hebron-oh-datacenter:initial-site-preparation",
                            "site_preparation",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-koge-denmark-datacenter:phase-2",
                            "civil_works",
                            "2026-03-09",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-new-albany-oh-datacenter:initial-site-preparation",
                            "site_preparation",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-northwest-hortolandia-brazil-datacenter:current-development",
                            "mep_electrical",
                            "2026-03-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-san-bovio-italy-datacenter:initial-development",
                            "site_preparation",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-southwest-hortolandia-brazil-datacenter:current-development",
                            "mep_electrical",
                            "2026-03-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-stover-hickory-nc-datacenter:current-development",
                            "foundations",
                            "2026-05-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:microsoft-sumare-east-brazil-datacenter:current-development",
                            "mep_electrical",
                            "2026-03-01",
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
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT content_hash FROM evidence"
                        )
                    },
                    CONTENT_HASHES,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE source_url LIKE '%east-point%'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
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

                san_bovio = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence WHERE source_url LIKE '%san-bovio%'"
                ).fetchone()[0])["record"]
                self.assertIn("principal works for September 2026", san_bovio["status_scope"])
                self.assertIn("not recast", san_bovio["redevelopment_guardrail"])

                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
