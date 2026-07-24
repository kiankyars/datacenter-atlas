from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SOURCE = (
    "curated-official-2026-07-20-leighton-johor-bahru-57-6mw-contract.json"
)
GROUNDBREAKING_SOURCE = (
    "curated-official-2026-07-20-leighton-anonymous-johor-groundbreaking.json"
)
SOURCE_PINS = {
    CONTRACT_SOURCE: (
        "2026-07-20T03:58:41Z",
        14_319,
        "29ec37c89471f591a1f4f9d12d06da9021b257a0b1317e295f33d9a16d38553a",
    ),
    GROUNDBREAKING_SOURCE: (
        "2026-07-20T04:11:19Z",
        8_470,
        "51b3bbd33dbe5f7d921f0e0428495277c433c48e629966eba5c092276306ebef",
    ),
}
CONTRACT_PROJECT = (
    "curated:leighton-anonymous-johor-bahru-57-6mw-campus:development"
)
GROUNDBREAKING_PROJECT = (
    "curated:leighton-anonymous-johor-july-2026-groundbreaking-campus:development"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LeightonJohorProjectsCuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        blocked = AssertionError("Leighton curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=blocked))
        return stack

    def _state(
        self,
        order: tuple[str, ...],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[object, ...], ...], ...]:
        with tempfile.TemporaryDirectory(prefix="leighton-johor-test-") as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=SOURCE_PINS[name][0],
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, metric, stage, base, unit "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_sources_are_canonical_hash_pinned_and_capture_bound(self) -> None:
        for name, (_retrieved_at, size, digest) in SOURCE_PINS.items():
            with self.subTest(name=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual((path.stat().st_size, _sha256(path)), (size, digest))
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertTrue(all(item["retrieved_at"] == _retrieved_at for item in document["evidence"]))
                for evidence in document["evidence"]:
                    self.assertEqual(evidence["metadata"]["http_status"], 200)
                    self.assertEqual(evidence["metadata"]["curl_exit_code"], 0)
                    self.assertEqual(evidence["metadata"]["redirect_count"], 0)
                    self.assertEqual(
                        evidence["metadata"]["content_hash_verification"],
                        "fetched_bytes_sha256",
                    )

        contract = self._load(CONTRACT_SOURCE)
        self.assertEqual(len(contract["evidence"]), 2)
        captures = {
            item["key"]: (
                item["metadata"]["content_hash_scope"],
                item["content_hash"],
                item["metadata"]["capture_headers_sha256"],
                item["metadata"]["capture_curl_writeout_sha256"],
            )
            for item in contract["evidence"]
        }
        self.assertEqual(
            captures[
                "leighton-johor-bahru-data-centre-contract-2026-02-08-"
                "captured-2026-07-20"
            ],
            (
                "SHA-256 of the exact 164333-byte content-decoded official HTML "
                "response body captured with curl --compressed",
                "2662c8e67a7016698644adc3e6f52bab7c09695997d5a681d5e1d2cc1fdc9def",
                "4ae5f1acb3e1607b8f960803249a2635788051b0318f91ca3a69ace419812b47",
                "3ffbb6a9a4972f461e7062b12efe45894725c44183cf53d73bb285a9cc9777e0",
            ),
        )
        self.assertEqual(
            captures[
                "leighton-johor-bahru-data-centre-current-project-"
                "captured-2026-07-20"
            ],
            (
                "SHA-256 of the exact 208646-byte content-decoded official HTML "
                "response body captured with curl --compressed",
                "3c70e11eadd9409f7f5184b60ab19b1db03a8829e59dead71660712dfb924ae5",
                "52153859889b8a53ebf246e974bfb6c9a65927a19fd2540655deb7e37cb408f5",
                "0ba26cebe1948a70583d4a2dcea44d2600c7fe2f951840c8dbcbe32bb7f07b5c",
            ),
        )

        groundbreaking = self._load(GROUNDBREAKING_SOURCE)["evidence"][0]
        self.assertEqual(
            (
                groundbreaking["content_hash"],
                groundbreaking["metadata"]["capture_headers_sha256"],
                groundbreaking["metadata"]["capture_curl_writeout_sha256"],
            ),
            (
                "548f0d5c44561625e43450a41a6c902562729049dd8052d8137cd2faf1c9c52d",
                "ed5538155127a2c7173526ed7411a279bc6879bb4df75cfa705eddbd67f0b3ce",
                "b4c02d824e5f9fbaf68b43ba7b951fe6d400a9db2af19ac23bcc0fcb3371076c",
            ),
        )

    def test_contract_award_is_not_promoted_to_physical_construction(self) -> None:
        document = self._load(CONTRACT_SOURCE)
        self.assertEqual(document["campus"]["roles"], {"contractor": ["Leighton Asia"]})
        self.assertEqual(document["project"]["roles"], {"contractor": ["Leighton Asia"]})
        self.assertIsNone(document["campus"]["coordinates"])
        self.assertIsNone(document["campus"]["geometry"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "announced",
                    "evidence_key": (
                        "leighton-johor-bahru-data-centre-contract-2026-02-08-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-02-08",
                    "method": "authoritative_announcement",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["unit"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
            ),
            ("project", "critical_it_mw", "planned", "MW", 57.6, 57.6, 57.6),
        )
        self.assertEqual(
            [(row["entity"], row["value"]) for row in document["operating_models"]],
            [("project", "colocation")],
        )
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("do not by themselves prove", metadata["physical_status_scope"])
        self.assertIn("upper-bound 57.6 MW", metadata["capacity_scope"])
        self.assertIn("anonymous", metadata["role_scope"])
        self.assertIn("not merged", metadata["identity_separation_guardrail"])
        self.assertIn("no PUE", metadata["energy_guardrail"])

    def test_groundbreaking_is_physical_but_identity_and_metrics_stay_unresolved(self) -> None:
        document = self._load(GROUNDBREAKING_SOURCE)
        self.assertEqual(document["campus"]["address"], "Johor, Malaysia")
        self.assertEqual(document["project"]["roles"], {"contractor": ["Leighton Asia"]})
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "leighton-anonymous-johor-groundbreaking-2026-07-08-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-08",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        metadata = document["evidence"][0]["metadata"]
        self.assertIn("advisory", metadata["publisher_image_identity_guardrail"])
        self.assertIn("not authoritative", metadata["publisher_image_identity_guardrail"])
        self.assertIn("not transferred", metadata["capacity_guardrail"])
        self.assertIn("None is inferred", metadata["classification_guardrail"])
        self.assertIn("solely from the official text", metadata["imagery_guardrail"])

    def test_two_unresolved_observations_import_offline_without_merging(self) -> None:
        first = self._state((CONTRACT_SOURCE, GROUNDBREAKING_SOURCE))
        reverse = self._state((GROUNDBREAKING_SOURCE, CONTRACT_SOURCE))
        repeated = self._state(
            (CONTRACT_SOURCE, GROUNDBREAKING_SOURCE), repetitions=2
        )
        self.assertEqual(first, reverse)
        self.assertEqual(first, repeated)

        entities, evidence, lifecycle, capacities, models, snapshots = first
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(evidence), 3)
        self.assertEqual(
            lifecycle,
            (
                (
                    CONTRACT_PROJECT,
                    "announced",
                    "2026-02-08",
                    "authoritative_announcement",
                ),
                (
                    GROUNDBREAKING_PROJECT,
                    "under_construction",
                    "2026-07-08",
                    "authoritative_physical_status_update",
                ),
            ),
        )
        self.assertEqual(
            capacities,
            ((CONTRACT_PROJECT, "critical_it_mw", "planned", 57.6, "MW"),),
        )
        self.assertEqual(models, ((CONTRACT_PROJECT, "colocation"),))
        self.assertEqual(
            {row[0] for row in snapshots},
            {
                "curated:leighton-anonymous-johor-bahru-57-6mw-campus",
                CONTRACT_PROJECT,
                "curated:leighton-anonymous-johor-july-2026-groundbreaking-campus",
                GROUNDBREAKING_PROJECT,
            },
        )
        for stable_key, tags_json, latitude, longitude, geometry in snapshots:
            self.assertIsNone(latitude, stable_key)
            self.assertIsNone(longitude, stable_key)
            self.assertIsNone(geometry, stable_key)
            tags = json.loads(tags_json)
            self.assertEqual(tags["role:contractor"], "Leighton Asia")
            self.assertNotIn("role:operator", tags)
            self.assertNotIn("role:owner", tags)
            self.assertNotIn("role:developer", tags)


if __name__ == "__main__":
    unittest.main()
