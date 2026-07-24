from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

FLEET_SOURCE = "curated-official-2026-07-20-fleet-reno-storey-county-program.json"
DFW9_SOURCE = "curated-official-2026-07-20-databank-red-oak-dfw9.json"
DFW10_SOURCE = "curated-official-2026-07-20-databank-red-oak-dfw10-v2.json"
DFW11_SOURCE = "curated-official-2026-07-20-databank-red-oak-dfw11-v2.json"
SPO06_SOURCE = "curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json"
VINHEDO3_SOURCE = "curated-official-2026-07-20-ascenty-vinhedo-3.json"
PORTS_SOURCE = "curated-official-2026-07-20-sb-energy-ports-technology-campus.json"
SOURCES = (
    FLEET_SOURCE,
    DFW9_SOURCE,
    DFW10_SOURCE,
    DFW11_SOURCE,
    SPO06_SOURCE,
    VINHEDO3_SOURCE,
    PORTS_SOURCE,
)

REJECTED_V1_SOURCES = frozenset(
    {
        "curated-official-2026-07-20-databank-red-oak-dfw10.json",
        "curated-official-2026-07-20-databank-red-oak-dfw11.json",
    }
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    FLEET_SOURCE: {
        "bytes": 12_770,
        "sha256": "7ada494873559da3782bc31773af1f312b3362df3706a7f8cf90ac97011c7e70",
        "retrieved_at": "2026-07-20T18:04:34Z",
        "evidence_count": 2,
        "entity_count": 1,
        "campus_key": "curated:fleet-reno-storey-county-program",
        "project_key": None,
    },
    DFW9_SOURCE: {
        "bytes": 20_402,
        "sha256": "2e49ef1fb5659929878ef7418911d9af13e4f45487a013a3e9f7120ea081fab1",
        "retrieved_at": "2026-07-20T18:04:34Z",
        "evidence_count": 4,
        "entity_count": 2,
        "campus_key": "curated:databank-red-oak-campus",
        "project_key": "curated:databank-red-oak-campus:dfw9",
    },
    DFW10_SOURCE: {
        "bytes": 20_420,
        "sha256": "a5da37d9cab7b326e7f08db9ae0561cc20c63dc2e363f87834c146167e7ac14d",
        "retrieved_at": "2026-07-20T18:04:34Z",
        "evidence_count": 4,
        "entity_count": 2,
        "campus_key": "curated:databank-red-oak-campus",
        "project_key": "curated:databank-red-oak-campus:dfw10",
    },
    DFW11_SOURCE: {
        "bytes": 20_417,
        "sha256": "a01a6f59e2f52de29b867c35e16f124c15a09704c82c980a344efebb4f4512b0",
        "retrieved_at": "2026-07-20T18:04:34Z",
        "evidence_count": 4,
        "entity_count": 2,
        "campus_key": "curated:databank-red-oak-campus",
        "project_key": "curated:databank-red-oak-campus:dfw11",
    },
    SPO06_SOURCE: {
        "bytes": 12_945,
        "sha256": "6217582ee8cdf3c0e3d1ad175ab33debd90a4fa3ce88288b0e2ce96c9535a491",
        "retrieved_at": "2026-07-20T18:06:07Z",
        "evidence_count": 2,
        "entity_count": 2,
        "campus_key": "curated:ascenty-greater-sao-paulo-campus",
        "project_key": "curated:ascenty-greater-sao-paulo-campus:spo06",
    },
    VINHEDO3_SOURCE: {
        "bytes": 7_243,
        "sha256": "1dfc6f7de38b62692f88c0a8153f7ab3b50117b67fc292c7df97d0ca2f2df8a9",
        "retrieved_at": "2026-07-20T18:06:07Z",
        "evidence_count": 1,
        "entity_count": 2,
        "campus_key": "curated:ascenty-vinhedo-campus",
        "project_key": "curated:ascenty-vinhedo-campus:vinhedo-3",
    },
    PORTS_SOURCE: {
        "bytes": 20_411,
        "sha256": "7a8a6c639b0b26a7c14949ff8787473714eb774d57bf39612adc219584c24260",
        "retrieved_at": "2026-07-20T18:05:12Z",
        "evidence_count": 4,
        "entity_count": 1,
        "campus_key": "curated:sb-energy-ports-technology-campus",
        "project_key": None,
    },
}

CAPTURES: dict[str, tuple[int, str, int, str, int, str]] = {
    "fleet-reno-groundbreaking-linkedin-2026-05-21-captured-2026-07-20": (
        195_454,
        "e0c1ae990238bf18716f4dae496251c8fcde754ae4fe1c32128f0c219167ddb2",
        5_347,
        "21dd5d05c4412b0576747dffae63ac58e153e21a074bee53c6e9194fa44f24f7",
        17_796,
        "9c5bf38545709cf5e2eec65c2d165a46ed7a94919770211305f75286b658a368",
    ),
    "fleet-storey-county-financing-2026-02-24-captured-2026-07-20": (
        184_716,
        "7265aa702f693e8f1e00b157604dc233938614fd74e32c519997b301678b4322",
        378,
        "b60322936fd6aff7ec2b75eabadf3787c970d9ed58c2d70f7779f6f0b00bdcd9",
        16_871,
        "d3501db8f11fd2f1c191d9068525c573f902d0c77f8d50584f31968d61cc6662",
    ),
    "databank-red-oak-construction-2025-11-10-captured-2026-07-20": (
        132_991,
        "d77a71239c1c7d7a850a81fc930ba1e249d78565e31f20b92f931591b47765fa",
        6_973,
        "2074582bc154ae3ba1a439ba8fcdcce043cc3814f8b5384538c54fe0d02ba293",
        10_963,
        "1cbf50c342ab991f1a699db6e14995c49ec4648189c6f1a1a32dd909f8e46d70",
    ),
    "databank-red-oak-first-three-financing-2026-04-21-captured-2026-07-20": (
        127_161,
        "4a8b8583d59f0a1927e27bbd0ff1fee4cbc629c3370a8c77bd3679b92021563b",
        6_971,
        "b2d385a79770ca29c948de0365fc54561d09b7c27d4d7a3a77972c02507da920",
        11_157,
        "353fb7da4c30bce7efd3c11645228b6750ee4033cd43081178be107aa81c0414",
    ),
    "databank-red-oak-campus-current-captured-2026-07-20": (
        118_501,
        "1c08dd9b746d0cf45af229e79e3d195fee2340e00c4757116d92d42b2d065d71",
        7_098,
        "233a7b55687ea2a0de662b3756dc91deef5dc4fa37574e4bed49fa679bd4f14c",
        10_773,
        "aaf24cc4ffb86c96fd9d4c3a20bf3f448a94c88183e72047eefdd63c7518ebaf",
    ),
    "databank-dfw9-current-captured-2026-07-20": (
        113_664,
        "3ca3253561d8cb17e857aee910aae6438bfe7c4d6a8f5d12f8a187ee1a4731b2",
        7_095,
        "eed4163ed1380c0bff74bf2a8b368156a4a01b113ca1bab4543b42cf454752ac",
        10_783,
        "73f7ef1a8c37b67b595db34d9246934c05e0caadc059e970de854bf5c9909897",
    ),
    "databank-dfw10-current-captured-2026-07-20": (
        114_022,
        "1f6fc48795414821901bc2cd63eb9243bfbb9dd999a19127557a220ad0103f77",
        7_098,
        "6a1a3a690347d064795f6d63914beccd6ea6d384837a2378f5bd9a2b68d1ac06",
        10_788,
        "8027931b63445c62946bf438bb1683ff57d8d7dc887ae2ee39c60b43e8742b34",
    ),
    "databank-dfw11-current-captured-2026-07-20": (
        112_329,
        "05b820f12ce0835ae6fb7fd77fe184ca05463b3273b4b8cee73355a49bdb8a27",
        7_095,
        "a3e947db387cb134b2328e35e4c7d469f6a0c877f34929b262ab583750ae045b",
        10_788,
        "e407861eb062779a2cbb368308d99ea1702c1cbf169a56997b9e958eb67df999",
    ),
    "ascenty-spo06-construction-2026-05-08-captured-2026-07-20": (
        131_070,
        "50b1f1abd24ae0eb4ec7f453043cea09255f448477312edaf932feb404618e77",
        3_363,
        "6f65c69f648d940c00e5d3fb4f67685a2f0f45845eaadbb2a7df31b43bbf9f6c",
        15_176,
        "08b3f897356b92edec613b1b7b2cd2f72922497d5f6dc3a344e31594251e05b7",
    ),
    "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20": (
        133_552,
        "966870f4e9dc712246aaa91720f200ebb422da97c408f2ddedb8b9b1daa0e132",
        3_359,
        "38791919eca129c933302b4d8814723dd6521e38f15d7ac9fa27bba05db86f74",
        15_167,
        "b35194ceeff4ac63a8c136b74e759ab7de1dfe5f314b998109624e543b76dca5",
    ),
    "sb-energy-ports-current-captured-2026-07-20": (
        59_045,
        "e900032ad28add961c911768fd50aa884aa9c6b6902b2d558195dcee0503696e",
        757,
        "e03b8b67ae3aae0314f1219111d18e8726456a308245ab4ec69863c22d162002",
        12_688,
        "28125e1ca00072856cdbad5eb91135b4556d9f18034fd1b1e1e6657a4e1668df",
    ),
    "doe-ports-groundbreaking-2026-03-24-captured-2026-07-20": (
        123_692,
        "9e5b3e4ed1ccb8e3f34c3333fe879f15d5feb89da8223346cf0aca168ce3c859",
        1_212,
        "33407a6a74a45fc4e049034f41df5d6fb3d01e9bde3d094cb97e3d91cbb7af31",
        14_529,
        "cef0249d9aa3fa84d242ffcd44840c4c3ed52a8f07a89168bcdbdcbbde049fc1",
    ),
    "doe-ports-lease-record-2026-04-29-captured-2026-07-20": (
        114_166,
        "174f7e1993b1a5f3ced70614fb08afe514179d542f799c16d0bf33f7edb50ea1",
        1_211,
        "de06cc47c08b36ae758f229680ffb90ef6b1cc7e05f84d0bc3a8dcf08d9af5e2",
        14_561,
        "6d032480db815e241f8a4bc46de4cebe6ebfd11b1758926cb45e18f794041cfb",
    ),
    "doe-ports-partnership-announcement-2026-03-20-captured-2026-07-20": (
        122_464,
        "cdbde8bb003681344ff79d3d0141e1fdb957183b0b23672797911bdc9e523be2",
        1_211,
        "b3165aa1722fc2c3d712b14e3be4a2a508b283d4817978cf5d0db0bf57aa8c08",
        14_580,
        "80755f2396f9ce9bcff1d4bdc497c0d8b77b315ae5f3b9a1de67dc05844bf533",
    ),
}


class CuratedOfficialFleetDataBankAscentyPortsV2Tests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(
        self,
        order: Iterable[str],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=SOURCE_SPECS[name]["retrieved_at"],
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "as_of_date, target_date FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key, operating_model",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_files_are_canonical_hash_pinned_and_source_scoped(self) -> None:
        self.assertEqual(len(SOURCES), 7)
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                raw = path.read_bytes()
                self.assertEqual(len(raw), expected["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
                text = raw.decode("utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(
                    set(document),
                    {
                        "schema_version",
                        "evidence",
                        "campus",
                        "project",
                        "lifecycle",
                        "operating_models",
                        "workloads",
                        "capacities",
                    },
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(len(document["evidence"]), expected["evidence_count"])
                self.assertEqual(
                    document["campus"]["stable_key"], expected["campus_key"]
                )
                project = document["project"]
                if expected["project_key"] is None:
                    self.assertIsNone(project)
                else:
                    self.assertEqual(project["stable_key"], expected["project_key"])
                    self.assertIsNone(project["coordinates"])
                    self.assertIsNone(project["geometry"])
                self.assertIsNone(document["campus"]["coordinates"])
                self.assertIsNone(document["campus"]["geometry"])
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                self.assertNotIn("/private/tmp", text)

    def test_capture_hashes_dates_redirects_and_failed_fetches_are_exact(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            document = self._load(name)
            expected_retrieved_at = SOURCE_SPECS[name]["retrieved_at"]
            for item in document["evidence"]:
                self.assertEqual(item["retrieved_at"], expected_retrieved_at)
                self.assertTrue(item["source_url"].startswith("https://"))
                existing = evidence.setdefault(item["key"], item)
                self.assertEqual(existing, item)

        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                (
                    body_bytes,
                    body_hash,
                    header_bytes,
                    header_hash,
                    out_bytes,
                    out_hash,
                ) = expected
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["content_hash"], body_hash)
                self.assertIn(str(body_bytes), metadata["content_hash_scope"])
                self.assertIn(str(header_bytes), metadata["capture_headers_scope"])
                self.assertEqual(metadata["capture_headers_sha256"], header_hash)
                self.assertIn(str(out_bytes), metadata["capture_curl_writeout_scope"])
                self.assertEqual(metadata["capture_curl_writeout_sha256"], out_hash)
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )

        ascenty = {
            key: evidence[key]["metadata"]["blocked_standard_research_request"]
            for key in (
                "ascenty-spo06-construction-2026-05-08-captured-2026-07-20",
                "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20",
            )
        }
        self.assertEqual(
            ascenty["ascenty-spo06-construction-2026-05-08-captured-2026-07-20"][
                "headers_sha256"
            ],
            "59b50f5d00c45a9a4970b720c0e4ef4c5d45264751899e09d596c2d2ffa46800",
        )
        self.assertEqual(
            ascenty[
                "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20"
            ]["writeout_sha256"],
            "81a957b1f4bfe8b64647895245274cc07673a0fee6b16b89a957857573b52897",
        )
        for failed in ascenty.values():
            self.assertEqual(failed["http_status"], 403)
            self.assertEqual(failed["curl_exit_code"], 56)
            self.assertFalse(failed["response_body_retained"])

        self.assertEqual(
            evidence[
                "fleet-reno-groundbreaking-linkedin-2026-05-21-captured-2026-07-20"
            ]["published_at"],
            "2026-05-21T13:42:31.510Z",
        )
        self.assertEqual(
            evidence["ascenty-spo06-construction-2026-05-08-captured-2026-07-20"][
                "metadata"
            ]["redirect_count"],
            1,
        )
        self.assertEqual(
            evidence["doe-ports-lease-record-2026-04-29-captured-2026-07-20"][
                "published_at"
            ],
            "2026-04-29",
        )

    def test_normalized_claims_and_guardrails_are_exact(self) -> None:
        fleet = self._load(FLEET_SOURCE)
        self.assertIsNone(fleet["project"])
        self.assertEqual(
            fleet["campus"]["roles"], {"contractor": ["Clark Construction Group"]}
        )
        self.assertEqual(
            [
                (row["entity"], row["metric"], row["base"])
                for row in fleet["capacities"]
            ],
            [("campus", "critical_it_mw", 400)],
        )
        financing = fleet["evidence"][1]["metadata"]
        self.assertEqual(
            financing["reported_unnamed_facility_utility_capacity_mw"], 230
        )
        self.assertEqual(
            financing["reported_unnamed_facility_critical_it_capacity_mw"], 200
        )
        self.assertIn("does not map it", financing["identity_guardrail"])

        dfw_documents = [
            self._load(DFW9_SOURCE),
            self._load(DFW10_SOURCE),
            self._load(DFW11_SOURCE),
        ]
        self.assertEqual(
            {document["project"]["stable_key"] for document in dfw_documents},
            {
                "curated:databank-red-oak-campus:dfw9",
                "curated:databank-red-oak-campus:dfw10",
                "curated:databank-red-oak-campus:dfw11",
            },
        )
        for document in dfw_documents:
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(document["project"]["roles"], {})
            self.assertEqual(document["lifecycle"][0]["as_of_date"], "2025-11-10")
            self.assertEqual(
                (
                    document["capacities"][0]["metric"],
                    document["capacities"][0]["base"],
                ),
                ("critical_it_mw", 60),
            )
            self.assertTrue(
                document["capacities"][0]["evidence_key"].startswith("databank-dfw")
            )
            conflict = document["evidence"][2]["metadata"][
                "capacity_conflict_guardrail"
            ]
            self.assertIn("300 MW", conflict)
            self.assertIn("240 MW", conflict)
            self.assertEqual(
                document["evidence"][1]["metadata"][
                    "reported_first_three_power_mw_untyped"
                ],
                180,
            )
        self.assertNotIn(
            "curated:databank-red-oak-campus:dfw12",
            {document["project"]["stable_key"] for document in dfw_documents},
        )

        spo06 = self._load(SPO06_SOURCE)
        vinhedo3 = self._load(VINHEDO3_SOURCE)
        self.assertEqual(spo06["capacities"], [])
        self.assertEqual(vinhedo3["capacities"], [])
        shared = spo06["evidence"][1]
        self.assertEqual(shared, vinhedo3["evidence"][0])
        self.assertEqual(
            shared["metadata"][
                "reported_sao_paulo_sixth_facility_untyped_capacity_increase_mw"
            ],
            20,
        )
        self.assertEqual(
            shared["metadata"]["reported_vinhedo_3_untyped_capacity_mw"], 90
        )
        self.assertIn("Vinhedo 2", shared["metadata"]["identity_scope"])

        ports = self._load(PORTS_SOURCE)
        self.assertIsNone(ports["project"])
        self.assertEqual(ports["campus"]["roles"], {})
        self.assertEqual(ports["capacities"], [])
        self.assertEqual(ports["lifecycle"][0]["as_of_date"], "2026-03-20")
        self.assertEqual(
            ports["lifecycle"][0]["method"], "authoritative_construction_start"
        )
        current = ports["evidence"][0]["metadata"]
        announcement = ports["evidence"][3]["metadata"]
        self.assertEqual(current["reported_total_site_capacity_gw_untyped"], 10)
        self.assertEqual(announcement["reported_new_power_generation_gw"], 10)
        self.assertIn(
            "Neither is normalized", announcement["capacity_separation_guardrail"]
        )

    def test_v2_identity_guardrails_exclude_only_siblings(self) -> None:
        self.assertTrue(REJECTED_V1_SOURCES.isdisjoint(SOURCES))
        expected = {
            DFW9_SOURCE: ("DFW9", {"DFW10", "DFW11", "DFW12"}),
            DFW10_SOURCE: ("DFW10", {"DFW9", "DFW11", "DFW12"}),
            DFW11_SOURCE: ("DFW11", {"DFW9", "DFW10", "DFW12"}),
        }
        for source, (self_name, siblings) in expected.items():
            with self.subTest(source=source):
                document = self._load(source)
                current_key = (
                    f"databank-{self_name.lower()}-current-captured-2026-07-20"
                )
                current = next(
                    item for item in document["evidence"] if item["key"] == current_key
                )
                guardrail = current["metadata"]["identity_guardrail"]
                self.assertIn(f"{self_name} is a distinct", guardrail)
                exclusions = guardrail.split("It is not ", 1)[1].split(
                    ", any other", 1
                )[0]
                actual = {value.strip() for value in exclusions.split(",")}
                self.assertEqual(actual, siblings)
                self.assertNotIn(self_name, actual)

    def test_each_source_imports_offline_in_isolation(self) -> None:
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=expected["retrieved_at"],
                        )
                    self.assertEqual(result.entities_created, expected["entity_count"])
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                    self.assertEqual(result.warnings, ())
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_combined_import_is_offline_idempotent_order_independent_and_exact(
        self,
    ) -> None:
        baseline = self._state(SOURCES)
        self.assertEqual(baseline, self._state(reversed(SOURCES)))
        self.assertEqual(baseline, self._state(SOURCES, repetitions=2))

        entities, evidence, snapshots, lifecycle, capacities, models, workloads = (
            baseline
        )
        self.assertEqual(len(entities), 10)
        self.assertEqual(len(evidence), 14)
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(len(lifecycle), 7)
        self.assertEqual(len(capacities), 4)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertTrue(
            all(
                latitude is None and longitude is None and geometry is None
                for _, _, _, latitude, longitude, geometry in snapshots
            )
        )
        self.assertEqual(
            set(lifecycle),
            {
                (
                    "curated:fleet-reno-storey-county-program",
                    "under_construction",
                    "2026-05-21",
                    "authoritative_construction_start",
                ),
                *{
                    (
                        f"curated:databank-red-oak-campus:dfw{number}",
                        "under_construction",
                        "2025-11-10",
                        "authoritative_physical_status_update",
                    )
                    for number in (9, 10, 11)
                },
                (
                    "curated:ascenty-greater-sao-paulo-campus:spo06",
                    "under_construction",
                    "2026-05-08",
                    "authoritative_physical_status_update",
                ),
                (
                    "curated:ascenty-vinhedo-campus:vinhedo-3",
                    "under_construction",
                    "2026-05-28",
                    "authoritative_physical_status_update",
                ),
                (
                    "curated:sb-energy-ports-technology-campus",
                    "under_construction",
                    "2026-03-20",
                    "authoritative_construction_start",
                ),
            },
        )
        self.assertEqual(
            set(capacities),
            {
                (
                    "curated:fleet-reno-storey-county-program",
                    "critical_it_mw",
                    "planned",
                    400.0,
                    400.0,
                    400.0,
                    "2026-05-21",
                    None,
                ),
                *{
                    (
                        f"curated:databank-red-oak-campus:dfw{number}",
                        "critical_it_mw",
                        "planned",
                        60.0,
                        60.0,
                        60.0,
                        "2026-07-20",
                        None,
                    )
                    for number in (9, 10, 11)
                },
            },
        )

    def test_adapter_imports_offline_in_both_workspace_layouts(self) -> None:
        specs = [
            (str(self._path(name)), SOURCE_SPECS[name]["retrieved_at"])
            for name in SOURCES
        ]
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated import CuratedOfficialSourceAdapter
from {package}.database import initialize
from {package}.service import validate_database

specs = {specs!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for source, retrieved_at in specs:
                CuratedOfficialSourceAdapter().import_file(connection, source, retrieved_at=retrieved_at)
        assert validate_database(connection) == []
        tables = ("entities", "evidence", "entity_snapshots", "lifecycle_observations", "capacity_estimates")
        print(json.dumps({{table: connection.execute(f"SELECT COUNT(*) FROM {{table}}").fetchone()[0] for table in tables}}, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "capacity_estimates": 4,
                        "entities": 10,
                        "entity_snapshots": 10,
                        "evidence": 14,
                        "lifecycle_observations": 7,
                    },
                )


if __name__ == "__main__":
    unittest.main()
