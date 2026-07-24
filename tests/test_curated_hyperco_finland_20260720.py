from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
KORIA_SOURCE = "curated-official-2026-07-20-hyperco-dayone-koria.json"
LOVIISA_SOURCE = "curated-official-2026-07-20-hyperco-loviisa.json"
SOURCE_ORDER = (KORIA_SOURCE, LOVIISA_SOURCE)

SOURCES: dict[str, dict[str, Any]] = {
    KORIA_SOURCE: {
        "sha256": "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63",
        "retrieved_at": "2026-07-20T00:35:14Z",
        "evidence_count": 1,
        "campus_key": "curated:hyperco-dayone-koria-unnamed-data-center-campus",
        "project_key": (
            "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build"
        ),
        "address": "Koria, Kouvola, Finland",
        "roles": {"user": ["TikTok"]},
        "lifecycle_date": "2026-05-11",
        "lifecycle_evidence": (
            "kouvola-koria-hyperco-dayone-topping-out-2026-05-11-"
            "captured-2026-07-20"
        ),
    },
    LOVIISA_SOURCE: {
        "sha256": "048814c8816ca428d2e3ec557836c907049fcf327279870e01480b46a6a4d19d",
        "retrieved_at": "2026-07-20T00:35:16Z",
        "evidence_count": 2,
        "campus_key": "curated:hyperco-loviisa-data-center-campus",
        "project_key": "curated:hyperco-loviisa-data-center-campus:current-development",
        "address": "Itäinen liittymä, Loviisa, Finland",
        "roles": {"developer": ["Hyperco"]},
        "lifecycle_date": "2026-07-02",
        "lifecycle_evidence": (
            "loviisa-hyperco-active-noisy-works-2026-07-02-captured-2026-07-20"
        ),
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "kouvola-koria-hyperco-dayone-topping-out-2026-05-11-captured-2026-07-20": {
        "source": KORIA_SOURCE,
        "publisher": "City of Kouvola",
        "source_family": "kouvola_city_news",
        "published_at": "2026-05-11T10:15:24Z",
        "body_bytes": 68557,
        "content_hash": "cf29dcde78b9e08e421b599658dc93396a03bef0b7a7aaf18e1e05dc98312269",
        "headers_bytes": 993,
        "headers_hash": "7a9da928c4d35be91fad782514cfea7e2d95dc8399f94fa23f308da6a97d58a5",
        "writeout_bytes": 16394,
        "writeout_hash": "862fb2bdf267262a7f6f18cba1fa3f08ec960e84956d85ea9268de308638c780",
        "download_bytes": 17136,
        "response_date": "2026-07-20T00:35:14Z",
        "page_modified_at": "2026-05-12T05:20:13Z",
        "url": (
            "https://www.kouvola.fi/ajankohtaiset/"
            "korian-datakeskushankkeessa-juhlitaan-harjannostajaisia/"
        ),
    },
    "loviisa-hyperco-active-noisy-works-2026-07-02-captured-2026-07-20": {
        "source": LOVIISA_SOURCE,
        "publisher": "City of Loviisa",
        "source_family": "loviisa_city_news",
        "published_at": "2026-07-02T10:34:57Z",
        "body_bytes": 145564,
        "content_hash": "631f136b57cea6d06ef390665dfc86b7a42c84a7b517d6863b69d76cb3a4358a",
        "headers_bytes": 936,
        "headers_hash": "3d0abbfb6e015b97330c4f4cd6e0d9047699cfcffc69dd0846d7abe45c4fe352",
        "writeout_bytes": 16363,
        "writeout_hash": "38b00fc1283a462857b58b06da3e9ec71a16fadcb6ffedd3900dc281b9c721f4",
        "download_bytes": 30408,
        "response_date": "2026-07-20T00:35:15Z",
        "page_modified_at": "2026-07-02T10:34:58Z",
        "url": (
            "https://www.loviisa.fi/ajankohtaista/"
            "meluavat-tyot-datakeskuksen-tyomaalla-jatkuvat/"
        ),
    },
    "metsahallitus-hyperco-loviisa-groundworks-2026-06-04-captured-2026-07-20": {
        "source": LOVIISA_SOURCE,
        "publisher": "Metsähallitus",
        "source_family": "metsahallitus_press_releases",
        "published_at": "2026-06-04T10:35:15Z",
        "body_bytes": 201582,
        "content_hash": "3951720ead85f71d6e79f833efcd95bc97811377cfa0067ca22f30798f8c44aa",
        "headers_bytes": 987,
        "headers_hash": "7720c7c1d9f231c2eec9e55e7f25158826ea0746baef5d5e9a279d2a370ba9e9",
        "writeout_bytes": 16437,
        "writeout_hash": "2c9bb952ddef4709c4f88dd47e0fa43e8245ac7733d3bfaa3e6f6b12ae4516b2",
        "download_bytes": 29227,
        "response_date": "2026-07-20T00:35:16Z",
        "page_modified_at": "2026-06-04T10:50:32Z",
        "url": (
            "https://www.metsa.fi/tiedotteet/"
            "metsahallitus-vuokraa-tontin-loviisasta-"
            "hypercon-datakeskushankkeelle/"
        ),
    },
}

SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class HypercoFinlandOfficialSourceTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (
                        tuple(row)
                        for row in connection.execute(f"SELECT * FROM {table}")
                    ),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(self, order: Iterable[str]) -> dict[str, tuple[tuple[Any, ...], ...]]:
        network_error = AssertionError("network used")
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=network_error))
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in order:
                    expected = SOURCES[name]
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=expected["retrieved_at"],
                    )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                    self.assertEqual(result.warnings, ())

                first_state = self._state(connection)
                for name in SOURCE_ORDER:
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=SOURCES[name]["retrieved_at"],
                    )
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)

                self.assertEqual(self._state(connection), first_state)
                self.assertEqual(validate_database(connection), [])
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    4,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations"
                    ).fetchone()[0],
                    2,
                )
                for table in (
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                    )
                return first_state
            finally:
                connection.close()

    def test_sources_are_byte_pinned_and_semantically_narrow(self) -> None:
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            document = self._load(name)

            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(len(document["evidence"]), expected["evidence_count"])
            self.assertEqual(
                {item["retrieved_at"] for item in document["evidence"]},
                {expected["retrieved_at"]},
            )
            self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
            self.assertEqual(document["project"]["stable_key"], expected["project_key"])
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], "Finland")
                self.assertEqual(entity["address"], expected["address"])
                self.assertEqual(entity["roles"], expected["roles"])
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")

            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            lifecycle = document["lifecycle"][0]
            self.assertEqual(lifecycle["entity"], "project")
            self.assertEqual(lifecycle["value"], "under_construction")
            self.assertEqual(lifecycle["as_of_date"], expected["lifecycle_date"])
            self.assertEqual(
                lifecycle["evidence_key"], expected["lifecycle_evidence"]
            )
            self.assertEqual(
                lifecycle["method"], "authoritative_physical_status_update"
            )

        koria = self._load(KORIA_SOURCE)
        self.assertEqual(koria["campus"]["roles"], {"user": ["TikTok"]})
        adjacent_guardrail = koria["evidence"][0]["metadata"][
            "adjacent_project_guardrail"
        ]
        for boundary in (
            "Hyperco Data Systems",
            "west of",
            "now under construction",
            "100 MW IT",
            "130 MW total",
            "outside this record",
            "not merged, allocated, or normalized",
        ):
            self.assertIn(boundary, adjacent_guardrail)
        self.assertIn(
            "No workload observation is created",
            koria["evidence"][0]["metadata"]["workload_guardrail"],
        )

        loviisa = self._load(LOVIISA_SOURCE)
        lease_evidence = loviisa["evidence"][1]
        self.assertIn(
            "not a second data center",
            lease_evidence["metadata"]["adjacent_lease_scope"],
        )
        self.assertEqual(loviisa["campus"]["roles"], {"developer": ["Hyperco"]})

    def test_capture_facts_and_bounded_envelopes_are_exact(self) -> None:
        records = {
            evidence["key"]: evidence
            for name in SOURCE_ORDER
            for evidence in self._load(name)["evidence"]
        }
        self.assertEqual(set(records), set(CAPTURES))

        for key, expected in CAPTURES.items():
            evidence = records[key]
            metadata = evidence["metadata"]
            source = SOURCES[expected["source"]]
            self.assertEqual(evidence["kind"], "government_record")
            self.assertEqual(evidence["publisher"], expected["publisher"])
            self.assertEqual(evidence["source_family"], expected["source_family"])
            self.assertEqual(evidence["published_at"], expected["published_at"])
            self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
            self.assertEqual(evidence["content_hash"], expected["content_hash"])
            self.assertIn(
                f"exact {expected['body_bytes']}-byte content-decoded",
                metadata["content_hash_scope"],
            )
            self.assertEqual(
                metadata["capture_headers_sha256"], expected["headers_hash"]
            )
            self.assertIn(
                f"exact {expected['headers_bytes']}-byte raw",
                metadata["capture_headers_scope"],
            )
            self.assertEqual(
                metadata["capture_curl_writeout_sha256"],
                expected["writeout_hash"],
            )
            self.assertIn(
                f"exact {expected['writeout_bytes']}-byte",
                metadata["capture_curl_writeout_scope"],
            )
            self.assertEqual(metadata["http_status"], 200)
            self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
            self.assertEqual(metadata["content_encoding_as_received"], "gzip")
            self.assertIsNone(metadata["http_transfer_encoding_as_received"])
            self.assertIsNone(metadata["http_content_length_bytes_as_received"])
            self.assertEqual(
                metadata["curl_size_download_bytes_as_received"],
                expected["download_bytes"],
            )
            self.assertEqual(metadata["response_http_date"], expected["response_date"])
            self.assertEqual(metadata["page_modified_at"], expected["page_modified_at"])
            self.assertEqual(metadata["requested_url"], expected["url"])
            self.assertEqual(metadata["effective_url"], expected["url"])
            self.assertEqual(metadata["canonical_url"], expected["url"])
            self.assertEqual(evidence["source_url"], expected["url"])
            self.assertEqual(metadata["redirect_count"], 0)
            self.assertEqual(metadata["response_header_blocks"], 1)

        loviisa = self._load(LOVIISA_SOURCE)
        self.assertEqual(
            {item["retrieved_at"] for item in loviisa["evidence"]},
            {"2026-07-20T00:35:16Z"},
        )
        self.assertEqual(
            {item["metadata"]["response_http_date"] for item in loviisa["evidence"]},
            {"2026-07-20T00:35:15Z", "2026-07-20T00:35:16Z"},
        )

    def test_import_is_offline_idempotent_and_order_independent(self) -> None:
        self.assertEqual(self._build(SOURCE_ORDER), self._build(reversed(SOURCE_ORDER)))


if __name__ == "__main__":
    unittest.main()
