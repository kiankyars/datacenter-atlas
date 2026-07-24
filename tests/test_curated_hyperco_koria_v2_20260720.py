from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "sources" / "curated-official-2026-07-20-hyperco-dayone-koria.json"
V2 = ROOT / "sources" / "curated-official-2026-07-20-hyperco-dayone-koria-v2.json"

V1_SHA256 = "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63"
V2_SHA256 = "3de36878ff5e8ceac7571c0e267ae087ecd5571bae2284ccde230eb860ff5dc0"
RETRIEVED_AT = "2026-07-20T01:29:39Z"
CURRENT_EVIDENCE_KEY = (
    "kouvola-koria-hyperco-dayone-topping-out-2026-05-11-"
    "captured-2026-07-20"
)
YVA_EVIDENCE_KEY = (
    "kouvola-hyperco-data-systems-hiivuri-yva-"
    "2026-04-08-captured-2026-07-20"
)
CURRENT_CONTENT_HASH = (
    "cf29dcde78b9e08e421b599658dc93396a03bef0b7a7aaf18e1e05dc98312269"
)
YVA_CONTENT_HASH = (
    "a8f3161d4ae67cf2296d19e61533234ef675ee92e869f97bad12d3122effff6f"
)


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class HypercoKoriaV2Tests(unittest.TestCase):
    def test_v1_is_untouched_and_v2_is_a_narrow_append_only_correction(self) -> None:
        self.assertEqual(hashlib.sha256(V1.read_bytes()).hexdigest(), V1_SHA256)
        self.assertEqual(hashlib.sha256(V2.read_bytes()).hexdigest(), V2_SHA256)
        v1 = load(V1)
        v2 = load(V2)

        for key in (
            "schema_version",
            "campus",
            "project",
            "lifecycle",
            "operating_models",
            "workloads",
            "capacities",
        ):
            self.assertEqual(v2[key], v1[key], key)

        self.assertEqual(len(v1["evidence"]), 1)
        self.assertEqual(len(v2["evidence"]), 2)
        current, yva = v2["evidence"]
        self.assertEqual(current["key"], CURRENT_EVIDENCE_KEY)
        self.assertEqual(current["content_hash"], CURRENT_CONTENT_HASH)
        self.assertEqual(current["published_at"], v1["evidence"][0]["published_at"])
        self.assertEqual(current["source_url"], v1["evidence"][0]["source_url"])
        self.assertEqual(current["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(
            {
                key: value
                for key, value in current["metadata"].items()
                if key not in {"retrieved_at_semantics", "adjacent_project_guardrail"}
            },
            {
                key: value
                for key, value in v1["evidence"][0]["metadata"].items()
                if key not in {"retrieved_at_semantics", "adjacent_project_guardrail"}
            },
        )
        self.assertIn("Companion official Kouvola meeting-record evidence", current["metadata"]["adjacent_project_guardrail"])

        self.assertEqual(yva["key"], YVA_EVIDENCE_KEY)
        self.assertEqual(yva["kind"], "government_record")
        self.assertEqual(yva["publisher"], "City of Kouvola")
        self.assertEqual(yva["source_family"], "kouvola_city_meeting_records")
        self.assertEqual(yva["published_at"], "2026-04-08T00:00:00Z")
        self.assertEqual(yva["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(yva["content_hash"], YVA_CONTENT_HASH)

        metadata = yva["metadata"]
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 7185)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 7185)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "5f8182096aaee4501236e7a0de3851af58151b1ba1ddaa60dadd61d61a485dd8",
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "7b00bc4d9db0f124fe6cfb26020c33e21de4833dcd86c7c1eb039c491e9e8830",
        )
        self.assertEqual(
            metadata["reported_proposed_option"],
            {
                "option": "VE1",
                "critical_it_capacity": {
                    "qualifier": "about",
                    "unit": "MW",
                    "value": 100,
                },
                "total_electric_capacity": {
                    "qualifier": "about",
                    "unit": "MW",
                    "value": 130,
                },
            },
        )
        self.assertIn("west of", metadata["relationship_wording_as_reported"])

    def test_v2_imports_offline_idempotently_with_only_current_site_semantics(self) -> None:
        network_error = AssertionError("Koria v2 import attempted network access")
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary, ExitStack() as stack:
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
                first = CuratedOfficialSourceAdapter().import_file(
                    connection, V2, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual(first.entities_created, 2)
                self.assertEqual(first.evidence_created, 2)
                self.assertEqual(first.warnings, ())
                frozen = {
                    table: tuple(
                        tuple(row)
                        for row in connection.execute(
                            f"SELECT * FROM {table} ORDER BY rowid"
                        )
                    )
                    for table in (
                        "evidence",
                        "entities",
                        "entity_snapshots",
                        "lifecycle_observations",
                        "capacity_estimates",
                        "operating_model_observations",
                        "workload_observations",
                    )
                }

                second = CuratedOfficialSourceAdapter().import_file(
                    connection, V2, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual(second.entities_created, 0)
                self.assertEqual(second.evidence_created, 0)
                self.assertEqual(second.warnings, ())
                self.assertEqual(validate_database(connection), [])

                for table, rows in frozen.items():
                    self.assertEqual(
                        tuple(
                            tuple(row)
                            for row in connection.execute(
                                f"SELECT * FROM {table} ORDER BY rowid"
                            )
                        ),
                        rows,
                        table,
                    )
                self.assertEqual(len(frozen["evidence"]), 2)
                self.assertEqual(len(frozen["entities"]), 2)
                self.assertEqual(len(frozen["entity_snapshots"]), 2)
                self.assertEqual(len(frozen["lifecycle_observations"]), 1)
                self.assertEqual(len(frozen["capacity_estimates"]), 0)
                self.assertEqual(len(frozen["operating_model_observations"]), 0)
                self.assertEqual(len(frozen["workload_observations"]), 0)
            finally:
                connection.close()

    def test_yva_guardrail_cannot_leak_into_current_site_rows(self) -> None:
        document = load(V2)
        yva = next(item for item in document["evidence"] if item["key"] == YVA_EVIDENCE_KEY)
        current = next(
            item for item in document["evidence"] if item["key"] == CURRENT_EVIDENCE_KEY
        )

        self.assertEqual(document["campus"]["roles"], {"user": ["TikTok"]})
        self.assertEqual(document["project"]["roles"], {"user": ["TikTok"]})
        for entity in (document["campus"], document["project"]):
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], CURRENT_EVIDENCE_KEY)

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "as_of_date": "2026-05-11",
                    "confidence": 0.99,
                    "entity": "project",
                    "evidence_key": CURRENT_EVIDENCE_KEY,
                    "method": "authoritative_physical_status_update",
                    "value": "under_construction",
                }
            ],
        )
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertNotIn(YVA_EVIDENCE_KEY, json.dumps(document["campus"], sort_keys=True))
        self.assertNotIn(YVA_EVIDENCE_KEY, json.dumps(document["project"], sort_keys=True))
        self.assertNotIn(YVA_EVIDENCE_KEY, json.dumps(document["lifecycle"], sort_keys=True))
        self.assertIn("separate", yva["metadata"]["identity_boundary"])
        self.assertIn("create no capacity estimate", yva["metadata"]["capacity_scope"])
        self.assertIn("separate planned", current["metadata"]["adjacent_project_guardrail"])


if __name__ == "__main__":
    unittest.main()
