from __future__ import annotations

import copy
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
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T00:50:00Z"
FIRST_ACCEPTED_SEED_VERSION = 60
FIRST_ACCEPTED_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v60.json"
)
FIRST_ACCEPTED_DEFINITION_SHA256 = (
    "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66"
)
FIRST_ACCEPTED_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v60" / "manifest.json"
)
FIRST_ACCEPTED_MANIFEST_SHA256 = (
    "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430"
)
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "global-official-builds-eight-source-2026-07-20-v1"
)

ARTIFACT_FILE_SPECS = {
    "README.md": (
        1_648,
        "ee8b545138173843ccfed7ee5983ac23dd47b5c64a75ee0a9d1e3589362bcba8",
    ),
    "manifest.json": (
        709,
        "717c38110ba78e20ac276b452e8e541172bb57b059314ece1484b7da75a108eb",
    ),
    "manifest.sha256": (
        80,
        "df837b669048dfa7edf6ca8d3ccbf635b16e145be5eccad723271bfa7d106c3f",
    ),
    "retrieval-inventory.json": (
        14_655,
        "7c8493f11402030e9c2bea77712d21e1e7833870d16841e097f65f88f6a509af",
    ),
    "source-snapshot.json": (
        5_359,
        "6f638f64122375f71474a33b4b57ee4734ddb33be5dab5f8ac3b45b6f18876c5",
    ),
}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-wingu-addis-ababa-groundbreaking.json": {
        "bytes": 13_216,
        "sha256": "22c7b4c3f63971afd896a468d23d37cff5f22ee740ef606e48ebc1e20c97bf3f",
        "campus": "curated:wingu-addis-ababa-hyperscale-data-centre-park",
        "project": "curated:wingu-addis-ababa-hyperscale-data-centre-park:initial-development",
        "evidence_count": 2,
        "lifecycle": [
            ("under_construction", "2022-01-14"),
            ("operational", "2023-06-13"),
        ],
        "capacities": [],
        "models": [],
        "status_evidence": "wingu-addis-ababa-main-facility-inauguration-2023-06-13-captured-2026-07-20",
        "unresolved": False,
    },
    "curated-official-2026-07-20-africa-data-centres-sameer-nairobi-expansion.json": {
        "bytes": 8_875,
        "sha256": "6ac50d29d73e8fe6ed1ff88703d5d26c9435d8a7526e983b4e40097a1fdeb7e2",
        "campus": "curated:africa-data-centres-sameer-nairobi-campus",
        "project": "curated:africa-data-centres-sameer-nairobi-campus:additional-facility-expansion",
        "evidence_count": 1,
        "lifecycle": [("under_construction", "2023-01-19")],
        "capacities": [("project", "critical_it_mw", 5, "2023-01-19")],
        "models": [],
        "status_evidence": "africa-data-centres-sameer-nairobi-groundbreaking-2023-01-19-captured-2026-07-20",
        "unresolved": True,
    },
    "curated-official-2026-07-20-raxio-civ1-abidjan.json": {
        "bytes": 14_491,
        "sha256": "56ac63bf426f61034703d24a5e2b9213b0fc737cd487909fd565d3f3302200f3",
        "campus": "curated:raxio-civ1-abidjan-data-centre",
        "project": "curated:raxio-civ1-abidjan-data-centre:initial-build",
        "evidence_count": 2,
        "lifecycle": [
            ("under_construction", "2022-11-07"),
            ("operational", "2024-09-24"),
        ],
        "capacities": [("project", "critical_it_mw", 3, "2022-11-07")],
        "models": ["colocation"],
        "status_evidence": "raxio-civ1-abidjan-inauguration-2024-09-24-captured-2026-07-20",
        "unresolved": False,
    },
    "curated-official-2026-07-20-zdata-gp3-johor-building-1-topout.json": {
        "bytes": 7_593,
        "sha256": "9b74c0b49088b5de4c5041ae71d6b217cc333ec9e206ef180cb5a8659e1be6e1",
        "campus": "curated:zdata-gp3-johor-data-center",
        "project": "curated:zdata-gp3-johor-data-center:building-1",
        "evidence_count": 1,
        "lifecycle": [("shell", "2025-07-08")],
        "capacities": [],
        "models": [],
        "status_evidence": "cscec-zdata-gp3-johor-building-1-topout-2025-07-08-captured-2026-07-20",
        "unresolved": True,
    },
    "curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json": {
        "bytes": 12_915,
        "sha256": "a1aa648483ac151ce6d385cbfe842debddd32216f87b9032d70e9fcd0d2920a2",
        "campus": "curated:tm-global-klang-valley-data-centre-cyberjaya",
        "project": "curated:tm-global-klang-valley-data-centre-cyberjaya:block-2",
        "evidence_count": 2,
        "lifecycle": [("shell", "2025-05-30")],
        "capacities": [],
        "models": [],
        "status_evidence": "tm-global-kvdc-block-2-topout-2025-05-30-captured-2026-07-20",
        "unresolved": True,
    },
    "curated-official-2026-07-20-africa-data-centres-samrand-expansion.json": {
        "bytes": 9_078,
        "sha256": "41abf2616b0ec557131be6af84d5223bb033bcafa2e0ba2e62c124cbd07453a4",
        "campus": "curated:africa-data-centres-jhb2-samrand-campus",
        "project": "curated:africa-data-centres-jhb2-samrand-campus:2022-phase-1-expansion",
        "evidence_count": 1,
        "lifecycle": [("under_construction", "2022-08-30")],
        "capacities": [("project", "critical_it_mw", 20, "2022-08-30")],
        "models": [],
        "status_evidence": "africa-data-centres-samrand-phase-1-start-2022-08-30-captured-2026-07-20",
        "unresolved": True,
    },
    "curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json": {
        "bytes": 18_560,
        "sha256": "757642d2a9bdfb64464eb143444d27bd38341e95c251f7763ecd711b5099b984",
        "campus": "curated:cloudhq-gru-paulinia-campus",
        "project": "curated:cloudhq-gru-paulinia-campus:phase-1",
        "evidence_count": 3,
        "lifecycle": [("under_construction", "2023-03-04")],
        "capacities": [("campus", "critical_it_mw", 288, "2026-07-20")],
        "models": [],
        "status_evidence": "cloudhq-gru-paulinia-groundbreaking-post-2023-03-04-captured-2026-07-20",
        "unresolved": True,
    },
    "curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json": {
        "bytes": 13_376,
        "sha256": "48eead465a7de1af47770a14cf41579ffd822d7b8b1bf0a9ca2307701beb5d7d",
        "campus": "curated:airtrunk-tok2-west-tokyo-data-centre",
        "project": "curated:airtrunk-tok2-west-tokyo-data-centre:initial-build",
        "evidence_count": 2,
        "lifecycle": [
            ("under_construction", "2022-11-17"),
            ("operational", "2024-05-31"),
        ],
        "capacities": [],
        "models": [],
        "status_evidence": "airtrunk-fy24-sustainability-report-tok2-operational-2024-05-captured-2026-07-20",
        "unresolved": False,
    },
}

# source, URL, retrieved_at, body, headers, writeout, HTTP version, content type,
# encoding, downloaded bytes, header count, content length, last modified.
CAPTURE_SPECS: dict[str, tuple[Any, ...]] = {
    "wingu-addis-ababa-groundbreaking-2022-01-14-captured-2026-07-20": (
        "curated-official-2026-07-20-wingu-addis-ababa-groundbreaking.json",
        "https://www.wingu.africa/latest-news/ethiopia-wingu-africa-breaks-ground-ethiopia",
        "2026-07-21T00:39:33Z",
        (76_338, "1392d14b98b490785aa5e64391b29cf7d37ac2ff0a15d6acbfc91c6097522b6e"),
        (1_239, "c1ded059acf3c9ea007214a6e027d15e7c9cb1a970f617831ca0b1ebbdefd680"),
        (9_648, "8b33af96c1c3ee07258b2b8b524c1ec046b561e6baa2c3598a326e623b86ffd8"),
        "HTTP/2", "text/html; charset=utf-8", "gzip", 18_306, 17, None,
        "2026-07-21T00:30:37Z",
    ),
    "wingu-addis-ababa-main-facility-inauguration-2023-06-13-captured-2026-07-20": (
        "curated-official-2026-07-20-wingu-addis-ababa-groundbreaking.json",
        "https://www.wingu.africa/latest-news/wingu-inaugurates-world-class-data-centre-advancing-ethiopias-digital-economy",
        "2026-07-21T00:49:45Z",
        (80_232, "d7296033f0579e0eb63417c70e2901f5f51240c5924348f52a2c8a5742cbe419"),
        (1_239, "3b46fa67249fa161c846f5c8a2591d32c94eab89f73b72cc45d52ef7d2d74d18"),
        (9_787, "18d968192da56899b8d7b70e1a2fd0d6f9376e2ea099cc9d2cc2d9a96a935023"),
        "HTTP/2", "text/html; charset=utf-8", "gzip", 21_266, 17, None,
        "2026-07-21T00:49:45Z",
    ),
    "africa-data-centres-sameer-nairobi-groundbreaking-2023-01-19-captured-2026-07-20": (
        "curated-official-2026-07-20-africa-data-centres-sameer-nairobi-expansion.json",
        "https://www.africadatacentres.com/africa-data-centres-breaks-ground-on-new-sameer-facility-in-nairobi/",
        "2026-07-21T00:39:35Z",
        (114_811, "9dd4ea33bc2fe5c7438ba70ba57594462aca1db67c69e400e25bb3c8d70ee960"),
        (486, "93a2518fd484fada9a03d07754db2da739e853e5500d53433a7db6359dbaae45"),
        (16_516, "140a76fbe3f72a4808577e18e5c22f1b40a56a97917fc62c4a6e7835ac508435"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 25_035, 9, None, None,
    ),
    "raxio-civ1-abidjan-groundbreaking-2022-11-07-captured-2026-07-20": (
        "curated-official-2026-07-20-raxio-civ1-abidjan.json",
        "https://www.raxiogroup.com/raxio-group-breaks-ground-for-construction-of-raxio-abidjan-in-cote-divoire/",
        "2026-07-21T00:39:36Z",
        (220_062, "1fa44d72ca99e3ac6145f69d1cf6a6c47f8017b4c630dd486ec5a3b1329afb3d"),
        (1_628, "9dbf28dd4e72db957e1fe2600f54a72bab74f6ebf188936ed5abdc1fa9b718d9"),
        (9_780, "7feab1fa811eed36092989ec0614ca3c3db9c2734f30b44e9707b74bf27185fa"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 33_421, 26, None,
        "2026-07-21T00:31:08Z",
    ),
    "raxio-civ1-abidjan-inauguration-2024-09-24-captured-2026-07-20": (
        "curated-official-2026-07-20-raxio-civ1-abidjan.json",
        "https://www.raxiogroup.com/ivory-coast-gains-significant-boost-to-digital-economy-with-launch-of-raxio-data-centre/",
        "2026-07-21T00:49:45Z",
        (330_093, "4d63348bc0f4877b5c8ee66b08823cd495bd38afeded8f3d5602170a765db692"),
        (1_542, "2940a87dcd3b9fa518e8755de4d641a8e4d8d3d9d71e3b603b2c369e280c4ce2"),
        (9_833, "b5cf81d58b83a662519aa74922021db85510cd1ff067ea2e549e8f9563a45d33"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 62_092, 25, None, None,
    ),
    "cscec-zdata-gp3-johor-building-1-topout-2025-07-08-captured-2026-07-20": (
        "curated-official-2026-07-20-zdata-gp3-johor-building-1-topout.json",
        "https://english.cscec.com/CompanyNews/CorporateNews/202507/3883767.html",
        "2026-07-21T00:39:37Z",
        (40_015, "8c56cfa070b63d329f2fe75e5b2535f85b6da7806d6b93bdc7fbbc96f841c7c5"),
        (460, "cf94d77c357258a547af188ee85be76ca41007a3c1f9d6e8a3014bc43e823aa9"),
        (17_121, "cb7053d94c7a7a5514fca6a7d5a0b28a8de59c0b18c4fbb598b4b7a0ed7bcb15"),
        "HTTP/1.1", "text/html", "gzip", 6_600, 11, None,
        "2026-01-16T08:41:48Z",
    ),
    "tm-global-kvdc-block-2-topout-2025-05-30-captured-2026-07-20": (
        "curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json",
        "https://tmglobal.com.my/key-highlights/news-and-article/articles/events/KVDC-IPDC-Expansion",
        "2026-07-21T00:39:37Z",
        (114_152, "0ef6a8d1ddfca2819bf073baf527a9dc3a72cc50aaf82a73bbfedcd8a2dd728e"),
        (1_119, "d9b0faab9b300b278ea50f88be33818bc83a474f8eb5e7f070f30eb74eb720d5"),
        (19_617, "0244a59011c621f8b856525eeacd066922984e6b9cbe817f9f60f591b62f3c4c"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 23_445, 20, None, None,
    ),
    "tm-global-kvdc-cyberjaya-expansion-identity-2024-11-11-captured-2026-07-20": (
        "curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json",
        "https://tm.com.my/news/tm_global_expands_data_centres_cyberjaya_johor",
        "2026-07-21T00:39:39Z",
        (64_146, "315bf5a5b4ca5690a780f3ee0ce09ea57ca50309944bbbefa0e068ec86153838"),
        (1_213, "938dafa233d3be55c760bff6378bc702a8ce761d7380228c413ad5737678467e"),
        (19_056, "7d79d23bf79c619aa28b083569c23e50861ee4fbd9e11096a3ce4b0829e712f6"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 15_486, 27, None, None,
    ),
    "africa-data-centres-samrand-phase-1-start-2022-08-30-captured-2026-07-20": (
        "curated-official-2026-07-20-africa-data-centres-samrand-expansion.json",
        "https://www.africadatacentres.com/africa-data-centres-breaks-ground-for-samrand-facility-expansion/",
        "2026-07-21T00:39:41Z",
        (115_041, "07cd38e0a0c799f7362054743b5aef0fa67e1cf431c0728becb7cc531069fcad"),
        (486, "43835a1344c83055609c50a52084bcece788b302135f646b1ae8c74b740801a9"),
        (16_505, "7ab6461ec571360dd1579078b74da083b8e2a46d14c766bc4eff3542cb2cf1a8"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 24_544, 9, None, None,
    ),
    "cloudhq-gru-paulinia-groundbreaking-post-2023-03-04-captured-2026-07-20": (
        "curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json",
        "https://www.linkedin.com/posts/hossein-fateh-298355_the-cloudhq-team-and-i-were-proud-to-break-activity-7037787766914486273-rdzO",
        "2026-07-21T00:39:42Z",
        (177_825, "73947dcf3bc9811feaaeea4534ffdcddd263ac791823af503dd76acb9bdd6a4d"),
        (5_347, "d31d24fac39093ab07fecd8d47b7583c2d20ac198dc7aa7733ec0fcdc2e22d49"),
        (17_797, "53da2587d2f6b659240ecc2320bab2a0dc13fe777187e1df72a53549a7463308"),
        "HTTP/2", "text/html; charset=utf-8", "gzip", 19_586, 27, 19_586, None,
    ),
    "cloudhq-gru-paulinia-campus-page-captured-2026-07-20": (
        "curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json",
        "https://cloudhq.com/campus/gru-campus/",
        "2026-07-21T00:39:42Z",
        (157_800, "108dec57f4ade97f37fce63c98a079ea8d781f9b341e2b96ae3a52f92d7cb24d"),
        (1_375, "8ceb7f8b38a7c7ed19c0941a81dad166eef8748305b48c76b945b34927a0f039"),
        (9_464, "81118380fa1da84724a9b42b6518a280ea9b12ee18553b06b71f503717d3843d"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 29_826, 24, None, None,
    ),
    "cloudhq-hossein-fateh-founder-page-captured-2026-07-20": (
        "curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json",
        "https://cloudhq.com/learn-about-our-founder/",
        "2026-07-21T00:39:42Z",
        (149_460, "57befb84cad9de27af64d10fd9d8017cfe796ed766a6ab915a2384f8fbd1f3d6"),
        (1_373, "4c2cc0db213c84edc975727546eb4dd3691f3cb235d9a848e8a8e90ae225cf5a"),
        (9_489, "b640d22e018d89ec934e51510331e2a1e6568c77873e913de44096f278172c92"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 29_146, 24, None, None,
    ),
    "airtrunk-tok2-west-tokyo-groundbreaking-2022-11-17-captured-2026-07-20": (
        "curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json",
        "https://airtrunk.com/airtrunk-breaks-ground-on-tok2-begins-construction-on-110mw-facility-in-west-tokyo/",
        "2026-07-21T00:39:44Z",
        (99_911, "55f553509e7ff853919d59c0b45820d72469dc54ba07f6598a2b1d613bc001f8"),
        (757, "12e5f60e2227115b7c115fce037da38d026d63c54b18d2b55ae25c436467484c"),
        (11_162, "537efa27f9acc40fa1c0b75af2b10f6dfaf811497038e5289385fb0e8de4a813"),
        "HTTP/2", "text/html; charset=UTF-8", "gzip", 21_921, 16, None, None,
    ),
    "airtrunk-fy24-sustainability-report-tok2-operational-2024-05-captured-2026-07-20": (
        "curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json",
        "https://airtrunk.com/wp-content/uploads/2024/10/FY24-Sustainability-Report-by-AirTrunk.pdf",
        "2026-07-21T00:49:47Z",
        (4_309_251, "7baff2ed50603768eadbece2f189f4be3479ad43fdac7cd35c3743e1a0e29eb7"),
        (595, "645c286026fcbf3407da6d5d88d5d2fe4b507b7d4303ac09e1390a2c35f22170"),
        (11_108, "1a7645f46fb30b7a2ab75ce9022e6dc259d13078ba37753aada4d7a0231181ff"),
        "HTTP/2", "application/pdf", None, 4_309_251, 17, 4_309_251,
        "2024-12-11T06:16:38Z",
    ),
}

TRANSFER_ENCODINGS = {
    "cscec-zdata-gp3-johor-building-1-topout-2025-07-08-captured-2026-07-20": "chunked"
}


class GlobalHistoricalBuildsSuccessorTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("historical-build successor attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write(self, path: Path, document: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _assert_semantics(self, name: str, document: dict[str, Any]) -> None:
        spec = SOURCE_SPECS[name]
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(len(document["evidence"]), spec["evidence_count"])
        self.assertEqual(document["campus"]["stable_key"], spec["campus"])
        self.assertEqual(document["project"]["stable_key"], spec["project"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in document["lifecycle"]],
            spec["lifecycle"],
        )
        self.assertEqual(
            [
                (row["entity"], row["metric"], row["base"], row["as_of_date"])
                for row in document["capacities"]
            ],
            spec["capacities"],
        )
        self.assertEqual(
            [row["value"] for row in document["operating_models"]],
            spec["models"],
        )
        self.assertEqual(document["workloads"], [])
        for row in document["capacities"]:
            self.assertEqual(row["metric"], "critical_it_mw")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual((row["low"], row["base"], row["high"]), (row["base"],) * 3)
        if spec["unresolved"]:
            evidence = {item["key"]: item for item in document["evidence"]}
            metadata = evidence[spec["status_evidence"]]["metadata"]
            self.assertEqual(metadata["current_status_classification"], "unknown")
            self.assertEqual(
                (
                    metadata["last_observed_physical_status"],
                    metadata["last_observed_physical_status_date"],
                ),
                spec["lifecycle"][-1],
            )
            self.assertIn("present status is unknown", metadata["freshness_review_guardrail"])
            self.assertTrue(
                all(row["as_of_date"] < "2026-01-01" for row in document["lifecycle"])
            )

    def _database_state(
        self, order: tuple[str, ...], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        for name in order:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                self._path(name),
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                            self.assertEqual(
                                result.entities_created, 2 if iteration == 0 else 0
                            )
                            self.assertEqual(
                                result.evidence_created,
                                SOURCE_SPECS[name]["evidence_count"]
                                if iteration == 0
                                else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities ORDER BY 1, 2",
                    "SELECT source_url, content_hash, retrieved_at FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id ORDER BY 1, 3",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id ORDER BY 1, 2",
                    "SELECT entity_id, operating_model "
                    "FROM operating_model_observations ORDER BY 1, 2",
                    "SELECT entity_id, workload FROM workload_observations ORDER BY 1, 2",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_files_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                data = path.read_bytes()
                self.assertEqual(len(data), spec["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), spec["sha256"])
                text = data.decode("utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
                )
                self._assert_semantics(name, document)

    def test_all_capture_metadata_is_exact_closed_and_credential_free(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        evidence_sources: dict[str, str] = {}
        for name in SOURCE_SPECS:
            for item in self._load(name)["evidence"]:
                self.assertNotIn(item["key"], evidence)
                evidence[item["key"]] = item
                evidence_sources[item["key"]] = name
        self.assertEqual(set(evidence), set(CAPTURE_SPECS))
        forbidden_telemetry = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for key, expected in CAPTURE_SPECS.items():
            with self.subTest(evidence=key):
                (
                    source,
                    url,
                    retrieved_at,
                    body,
                    headers,
                    writeout,
                    http_version,
                    content_type,
                    encoding,
                    download,
                    header_count,
                    content_length,
                    last_modified,
                ) = expected
                self.assertEqual(evidence_sources[key], source)
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["source_url"], url)
                self.assertEqual(item["retrieved_at"], retrieved_at)
                self.assertEqual(item["content_hash"], body[1])
                self.assertIn(f"{body[0]}-byte", metadata["content_hash_scope"])
                self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
                self.assertIn(f"{headers[0]}-byte", metadata["capture_headers_scope"])
                self.assertEqual(metadata["capture_headers_sha256"], headers[1])
                self.assertIn(
                    f"{writeout[0]}-byte", metadata["capture_curl_writeout_scope"]
                )
                self.assertEqual(metadata["capture_curl_writeout_sha256"], writeout[1])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["http_version_as_received"], http_version)
                self.assertEqual(metadata["content_type"], content_type)
                self.assertEqual(metadata["content_encoding_as_received"], encoding)
                self.assertEqual(
                    metadata["http_transfer_encoding_as_received"],
                    TRANSFER_ENCODINGS.get(key),
                )
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"], content_length
                )
                self.assertEqual(metadata["decoded_body_bytes"], body[0])
                self.assertEqual(metadata["curl_size_download_bytes_as_received"], download)
                self.assertEqual(metadata["curl_size_header_bytes"], headers[0])
                self.assertEqual(metadata["curl_num_headers"], header_count)
                self.assertEqual(metadata["response_http_date"], retrieved_at)
                self.assertEqual(metadata["http_last_modified_at"], last_modified)
                self.assertEqual(metadata["requested_url"], url)
                self.assertEqual(metadata["effective_url"], url)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("credential-free", metadata["retrieval_method"])
                self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
                self.assertTrue(
                    forbidden_telemetry.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )

    def test_capacity_status_and_freshness_exclusions_are_exact(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        all_capacities = [
            row for document in documents.values() for row in document["capacities"]
        ]
        self.assertEqual(
            sorted((row["entity"], row["base"]) for row in all_capacities),
            [("campus", 288), ("project", 3), ("project", 5), ("project", 20)],
        )
        serialized = json.dumps(documents, ensure_ascii=False)
        for metric in (
            "annual_energy_mwh",
            "grid_connection_mw",
            "gross_facility_mw",
            "generation_nameplate_mw",
            '"metric": "pue"',
        ):
            self.assertNotIn(metric, serialized)

        kvdc = documents[
            "curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json"
        ]
        self.assertEqual(kvdc["capacities"], [])
        self.assertEqual(
            kvdc["evidence"][0]["metadata"]["reported_combined_kvdc_ipdc_it_load_mw"],
            20,
        )
        self.assertIn("no KVDC capacity row", kvdc["evidence"][0]["metadata"]["capacity_guardrail"])

        tok2 = documents[
            "curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json"
        ]
        self.assertEqual(tok2["capacities"], [])
        self.assertEqual(
            tok2["evidence"][0]["metadata"]["reported_capacity_mw_untyped_lower_bound"],
            110,
        )
        self.assertIn("open-bounded and untyped", tok2["evidence"][0]["metadata"]["capacity_guardrail"])
        self.assertEqual(
            tok2["evidence"][1]["metadata"]["month_end_as_of_date"], "2024-05-31"
        )

        samrand = documents[
            "curated-official-2026-07-20-africa-data-centres-samrand-expansion.json"
        ]
        metadata = samrand["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_first_phase_critical_it_mw"], 20)
        self.assertEqual(metadata["reported_next_phase_additional_it_mw"], 10)
        self.assertIn("no arithmetic", metadata["capacity_ambiguity_guardrail"])
        self.assertEqual([row["base"] for row in samrand["capacities"]], [20])

        cloudhq = documents[
            "curated-official-2026-07-20-cloudhq-gru-paulinia-campus.json"
        ]
        self.assertEqual(cloudhq["capacities"][0]["entity"], "campus")
        self.assertEqual(cloudhq["capacities"][0]["base"], 288)
        self.assertIn("not allocated to Phase 1", cloudhq["capacities"][0]["notes"])
        campus_metadata = cloudhq["evidence"][1]["metadata"]
        self.assertIn("not a dated physical observation", campus_metadata["target_guardrail"])

        statuses = [
            (name, row["value"], row["as_of_date"])
            for name, document in documents.items()
            for row in document["lifecycle"]
        ]
        self.assertEqual(sum(value == "operational" for _, value, _ in statuses), 3)
        self.assertEqual(sum(value == "shell" for _, value, _ in statuses), 2)
        self.assertEqual(sum(value == "under_construction" for _, value, _ in statuses), 6)
        self.assertTrue(all(date < "2026-01-01" for _, _, date in statuses))

    def test_import_is_offline_idempotent_and_order_independent(self) -> None:
        names = tuple(SOURCE_SPECS)
        once = self._database_state(names)
        self.assertEqual(self._database_state(names, repetitions=2), once)
        self.assertEqual(self._database_state(tuple(reversed(names))), once)
        entities, evidence, lifecycle, capacities, models, workloads = once
        self.assertEqual(len(entities), 16)
        self.assertEqual(len(evidence), 14)
        self.assertEqual(len(lifecycle), 11)
        self.assertEqual(len(capacities), 4)
        self.assertEqual(len(models), 1)
        self.assertEqual(workloads, ())
        self.assertEqual({row[1] for row in lifecycle}, {"operational", "shell", "under_construction"})
        self.assertEqual({row[1] for row in capacities}, {"critical_it_mw"})
        self.assertEqual({row[3] for row in capacities}, {3.0, 5.0, 20.0, 288.0})

    def test_capture_artifact_is_closed_hash_pinned_and_has_no_raw_bodies(self) -> None:
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_sha256) in ARTIFACT_FILE_SPECS.items():
            with self.subTest(artifact_file=name):
                path = ARTIFACT / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                data = path.read_bytes()
                self.assertEqual(len(data), expected_bytes)
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected_sha256)

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        expected_manifest_line = (
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n"
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            expected_manifest_line,
        )
        file_entries = manifest["files"]
        for entry in file_entries:
            path = ARTIFACT / entry["path"]
            data = path.read_bytes()
            self.assertEqual(len(data), entry["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
        tree_payload = json.dumps(file_entries, indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )

        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertFalse(inventory["raw_response_headers_retained"])
        self.assertEqual(inventory["direct_request_attempts"], 14)
        self.assertEqual(inventory["completed_response_requests"], 14)
        requests = {
            item["evidence_key"]: item
            for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for key, expected in CAPTURE_SPECS.items():
            item = requests[key]
            self.assertEqual(item["url"], expected[1])
            self.assertEqual(item["retrieved_at"], expected[2])
            for field, capture in (
                ("body", expected[3]),
                ("headers", expected[4]),
                ("curl_writeout", expected[5]),
            ):
                self.assertEqual(item[field]["bytes"], capture[0])
                self.assertEqual(item[field]["sha256"], capture[1])
                self.assertFalse(item[field]["retained"])
            self.assertEqual(item["http_version"], expected[6])
            self.assertEqual(item["content_type"], expected[7])
            self.assertEqual(item["content_encoding"], expected[8])
            self.assertFalse(item["request_credentials_supplied"])
        self.assertEqual(
            [
                path
                for path in ARTIFACT.rglob("*")
                if path.suffix in {".body", ".headers", ".writeout"}
            ],
            [],
        )

        snapshot_text = (ARTIFACT / "source-snapshot.json").read_text(
            encoding="utf-8"
        )
        snapshot = json.loads(snapshot_text)
        self.assertEqual(
            snapshot_text,
            json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(snapshot["release_integration"], "none")
        records = {Path(item["path"]).name: item for item in snapshot["source_records"]}
        self.assertEqual(set(records), set(SOURCE_SPECS))
        self.assertEqual(
            sum(item["current_2026_status"] == "unknown" for item in records.values()),
            5,
        )
        for name, spec in SOURCE_SPECS.items():
            item = records[name]
            self.assertEqual(item["bytes"], spec["bytes"])
            self.assertEqual(item["sha256"], spec["sha256"])
            self.assertEqual(item["campus_stable_key"], spec["campus"])
            self.assertEqual(item["project_stable_key"], spec["project"])
            self.assertEqual(
                (
                    item["latest_dated_physical_observation"]["status"],
                    item["latest_dated_physical_observation"]["as_of_date"],
                ),
                spec["lifecycle"][-1],
            )

    def test_stable_and_evidence_keys_do_not_collide_and_seed_lineage_is_exact(
        self,
    ) -> None:
        new_names = set(SOURCE_SPECS)
        stable_keys = {
            spec[field]
            for spec in SOURCE_SPECS.values()
            for field in ("campus", "project")
        }
        evidence_keys = set(CAPTURE_SPECS)
        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("*.json")):
            if path.name in new_names:
                continue
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            existing_stable = {
                entity["stable_key"]
                for entity in (document.get("campus"), document.get("project"))
                if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str)
            }
            existing_evidence = {
                item["key"]
                for item in document.get("evidence", [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            }
            stable_overlap = sorted(stable_keys & existing_stable)
            evidence_overlap = sorted(evidence_keys & existing_evidence)
            if stable_overlap or evidence_overlap:
                collisions[path.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(collisions, {})

        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_DEFINITION.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_MANIFEST.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_MANIFEST_SHA256,
        )
        expected_inputs = {
            name: spec["sha256"] for name, spec in SOURCE_SPECS.items()
        }
        for path in sorted((ROOT / "sources").glob("open-seed-*.json")):
            version_text = path.stem.rpartition("-v")[2]
            self.assertTrue(version_text.isdecimal(), path.name)
            version = int(version_text)
            definition = json.loads(path.read_text(encoding="utf-8"))
            selected_inputs = {
                Path(item["path"]).name: item["sha256"]
                for item in definition["curated_inputs"]
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            selected_new = new_names & set(selected_inputs)
            with self.subTest(seed_definition=path.name):
                if version < FIRST_ACCEPTED_SEED_VERSION:
                    self.assertEqual(selected_new, set())
                    continue
                self.assertEqual(selected_new, new_names)
                self.assertEqual(
                    {name: selected_inputs[name] for name in new_names},
                    expected_inputs,
                )

    def test_tamper_and_semantic_leakage_are_detected(self) -> None:
        name = "curated-official-2026-07-20-zdata-gp3-johor-building-1-topout.json"
        original = self._load(name)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            invalid_hash = copy.deepcopy(original)
            invalid_hash["evidence"][0]["content_hash"] = "not-a-sha256"
            invalid_path = base / "invalid-hash.json"
            self._write(invalid_path, invalid_hash)
            connection, _ = initialize(base / "invalid.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "content_hash must be a lowercase SHA-256"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, invalid_path, recorded_at=RECORDED_AT
                    )
            finally:
                connection.close()

            weak_method = copy.deepcopy(original)
            weak_method["lifecycle"][0]["method"] = "authoritative_status_update"
            weak_path = base / "weak-method.json"
            self._write(weak_path, weak_method)
            connection, _ = initialize(base / "weak.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "construction status requires"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, weak_path, recorded_at=RECORDED_AT
                    )
            finally:
                connection.close()

            duplicate_path = base / "duplicate.json"
            duplicate_path.write_text(
                self._path(name)
                .read_text(encoding="utf-8")
                .replace(
                    '  "schema_version": "1.1",',
                    '  "schema_version": "1.1",\n  "schema_version": "1.1",',
                    1,
                ),
                encoding="utf-8",
            )
            connection, _ = initialize(base / "duplicate.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "duplicate JSON field"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection, duplicate_path, recorded_at=RECORDED_AT
                    )
            finally:
                connection.close()

        kvdc_name = "curated-official-2026-07-20-tm-global-kvdc-block-2-topout.json"
        leaked_kvdc = copy.deepcopy(self._load(kvdc_name))
        leaked_kvdc["capacities"].append(copy.deepcopy(self._load(
            "curated-official-2026-07-20-africa-data-centres-samrand-expansion.json"
        )["capacities"][0]))
        with self.assertRaises(AssertionError):
            self._assert_semantics(kvdc_name, leaked_kvdc)

        tok2_name = "curated-official-2026-07-20-airtrunk-tok2-west-tokyo.json"
        leaked_tok2 = copy.deepcopy(self._load(tok2_name))
        leaked_tok2["capacities"] = copy.deepcopy(leaked_kvdc["capacities"])
        with self.assertRaises(AssertionError):
            self._assert_semantics(tok2_name, leaked_tok2)

        samrand_name = "curated-official-2026-07-20-africa-data-centres-samrand-expansion.json"
        leaked_samrand = copy.deepcopy(self._load(samrand_name))
        derived = copy.deepcopy(leaked_samrand["capacities"][0])
        derived.update({"base": 30, "low": 30, "high": 30, "as_of_date": "2022-08-31"})
        leaked_samrand["capacities"].append(derived)
        with self.assertRaises(AssertionError):
            self._assert_semantics(samrand_name, leaked_samrand)

        current_sameer_name = (
            "curated-official-2026-07-20-africa-data-centres-sameer-nairobi-expansion.json"
        )
        current_sameer = copy.deepcopy(self._load(current_sameer_name))
        current_sameer["lifecycle"].append(
            {
                **current_sameer["lifecycle"][0],
                "as_of_date": "2026-07-20",
            }
        )
        with self.assertRaises(AssertionError):
            self._assert_semantics(current_sameer_name, current_sameer)

    def test_sources_import_offline_in_both_workspace_layouts(self) -> None:
        sources = [str(self._path(name)) for name in SOURCE_SPECS]
        expected = {
            "capacity": 4,
            "entities": 16,
            "evidence": 14,
            "lifecycle": 11,
            "operating_models": 1,
            "snapshots": 16,
            "workloads": 0,
        }
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
from {package}.curated_v11 import CuratedOfficialSourceAdapterV11
from {package}.database import initialize
from {package}.service import validate_database

sources = {sources!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for iteration in range(2):
                for source in sources:
                    result = CuratedOfficialSourceAdapterV11().import_file(
                        connection, Path(source), recorded_at={RECORDED_AT!r}
                    )
                    assert result.warnings == ()
                    assert result.entities_created == (2 if iteration == 0 else 0)
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        print(json.dumps(counts, sort_keys=True))
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
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
