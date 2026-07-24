from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T05:41:07Z"

CH3_SOURCE = "curated-official-2026-07-20-ntt-chicago-ch3.json"
CH4_SOURCE = "curated-official-2026-07-20-ntt-chicago-ch4.json"
JKT2A_SOURCE = "curated-official-2026-07-20-ntt-jkt2a-jakarta.json"
OSK12_SOURCE = "curated-official-2026-07-20-ntt-osk12-osaka-north-1.json"
TKY11_B1_SOURCE = "curated-official-2026-07-20-ntt-tky11-building-1.json"
TKY11_B2_SOURCE = "curated-official-2026-07-20-ntt-tky11-building-2.json"
TX4_SOURCE = "curated-official-2026-07-20-ntt-tx4-dallas.json"
SOURCES = (
    CH3_SOURCE,
    CH4_SOURCE,
    JKT2A_SOURCE,
    OSK12_SOURCE,
    TKY11_B1_SOURCE,
    TKY11_B2_SOURCE,
    TX4_SOURCE,
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    CH3_SOURCE: {
        "sha256": "c916fc71ee91607a03311bc5c79f97725efcd96191cc8f888f4944e4e3f827a6",
        "evidence_count": 2,
        "campus_key": "curated:ntt-itasca-data-center-campus",
        "project_key": "curated:ntt-itasca-data-center-campus:ch3",
        "status": "under_construction",
        "status_date": "2025-12-16",
        "status_method": "authoritative_physical_status_update",
        "capacities": [("project", 32.0)],
    },
    CH4_SOURCE: {
        "sha256": "5f3ba11a811756dd5c23a807a6c3c95900dd094e243523fe5f9ed36104713684",
        "evidence_count": 1,
        "campus_key": "curated:ntt-itasca-data-center-campus",
        "project_key": "curated:ntt-itasca-data-center-campus:ch4",
        "status": "under_construction",
        "status_date": "2026-03-12",
        "status_method": "authoritative_physical_status_update",
        "capacities": [],
    },
    JKT2A_SOURCE: {
        "sha256": "2b81b1691bf156daff98ed34d70a7a8d0556735258a280f97019d34c4029c49b",
        "evidence_count": 3,
        "campus_key": "curated:ntt-jakarta-2-campus",
        "project_key": "curated:ntt-jakarta-2-campus:jkt2a-annex",
        "status": "shell",
        "status_date": "2025-07-24",
        "status_method": "authoritative_physical_status_update",
        "capacities": [("project", 12.0)],
    },
    OSK12_SOURCE: {
        "sha256": "5ee8cfd9eeadfd4e6e060ecf6faf1628a6985afb7f525a6c587ba48011b9f99d",
        "evidence_count": 2,
        "campus_key": "curated:ntt-osk12-osaka-north-1-campus",
        "project_key": "curated:ntt-osk12-osaka-north-1-campus:building-1",
        "status": "under_construction",
        "status_date": "2025-10-01",
        "status_method": "authoritative_construction_start",
        "capacities": [("campus", 36.0), ("project", 18.0)],
    },
    TKY11_B1_SOURCE: {
        "sha256": "a11feea3140972e4078666f07341da0a68bbbf9f3b79f87258ae40621cee1744",
        "evidence_count": 3,
        "campus_key": "curated:ntt-tky11-shiroi-1-campus",
        "project_key": "curated:ntt-tky11-shiroi-1-campus:building-1",
        "status": "under_construction",
        "status_date": "2026-04-27",
        "status_method": "authoritative_physical_status_update",
        "capacities": [("campus", 50.0), ("project", 24.0)],
    },
    TKY11_B2_SOURCE: {
        "sha256": "4d6e2798abf59e471fce731615b821bbff85a3c96aa82751b978b8453f6f7886",
        "evidence_count": 1,
        "campus_key": "curated:ntt-tky11-shiroi-1-campus",
        "project_key": "curated:ntt-tky11-shiroi-1-campus:building-2",
        "status": "announced",
        "status_date": "2026-07-20",
        "status_method": "authoritative_announcement",
        "capacities": [("project", 26.0)],
    },
    TX4_SOURCE: {
        "sha256": "10ffafeb8dd80d4ee40394e4edbc9ae422d5972f68823cbfe738a1c1e8d170d3",
        "evidence_count": 3,
        "campus_key": "curated:ntt-dallas-data-center-campus",
        "project_key": "curated:ntt-dallas-data-center-campus:tx4",
        "status": "under_construction",
        "status_date": "2026-05-31",
        "status_method": "authoritative_physical_status_update",
        "capacities": [("project", 36.0)],
    },
}

CAPTURES = {
    "ntt-chicago-ch3-location-page-current-captured-2026-07-20": (
        405348,
        "18a15dd8866a446efe23f18945be4bd00eef3677b4263737f2fa49c065b8d31f",
        19122,
        "610356d5e72485053541b1d3ab371f362485c31240445cfb08a085effbf42a56",
        12227,
        "3503b40f07b883cf57995ed55232bf2025ea9ec1e558f730b8bff4607a29c20e",
    ),
    "itasca-ntt-ch3-development-agreement-current-construction-captured-2026-07-20": (
        403953,
        "163932d6b8ee81eb7318a74822a59219493afeec74f55e4882bc4041067118bd",
        857,
        "6f9eda0ca2cacc7de69560dd5a7315a0467d1590282e1fbf136c41c77152a26c",
        16315,
        "f0e3476fd1f0bb79c52b7b22711378c889a916963df96ba2e5a2fc4fbf0a42ec",
    ),
    "itasca-2026-05-05-agenda-packet-ch4-current-construction-captured-2026-07-20": (
        92022092,
        "096cbe587390b6ed15a0a46a77e0590a7bfa45d82c02357d61dfa7a631245c62",
        875,
        "ff5344eb1103483c2b87ed57759b934c6b2aabd8d26bfed1d884f4e797c789b3",
        16359,
        "8fb29b849ccaaa3738d364cc44f4cf7af68a2d76b696d47b1247730995c27429",
    ),
    "ntt-jkt2a-location-page-current-captured-2026-07-20": (
        372222,
        "253cc770a2da0a3ee8ba8d0ece060f0d4500226178fcbfd718dac84f0db33c9a",
        19121,
        "f8df186590e529c61e24957ac504dd67f972ad29d5d7efa413c7fa4df383784e",
        12242,
        "e60b29aecb914f1592edf275e08b25512f3d83303cd78c5493358e2c9fef8e5c",
    ),
    "ntt-jkt2a-construction-release-2024-05-15-captured-2026-07-20": (
        314398,
        "e60ed3aaf4d60dc54aee7f0546e50dadefc11a818581464bedfe3023e9fc214f",
        19121,
        "d938dbddf608fa803320de429f95db369791deb6efdbba43de4ee399c3b91f03",
        12188,
        "bcfbbd3e017dba2aac32b4968d79c0ffb028774dad88050de0494122257cf299",
    ),
    "ntt-jkt2a-topping-out-linkedin-2025-07-24-captured-2026-07-20": (
        173224,
        "30d740a142a5d25f4dc39da88b6cb11ba03f152a6b410c3fbdc69661ff123a33",
        5348,
        "dc044d9e4ecd0b26da6e7fc17018af7b52d59a9b933ef4b6fc4331b617ff4fbd",
        17841,
        "ce5dbd8db4c81c7e5b19035b8df3ea9404c9872dde08b96eb5954d4a76c5bbc5",
    ),
    "ntt-osk12-location-page-current-captured-2026-07-20": (
        364505,
        "8debb9f70cfe5930fe340614ef11a42813eeb103ecc228ef0edf6945f44390b3",
        19083,
        "20f687b137ed43544062ffeebcd74a9210e4b65501ac7c14edd154c6f0b1b391",
        12246,
        "79699c146824dedae669bd981af4e435824b8e5ced576536149337f19b4931ac",
    ),
    "ntt-osk12-groundbreaking-linkedin-2025-10-07-captured-2026-07-20": (
        143643,
        "c302b9f4f84c03ceb3f8c596277b94824434e153415c782d39ed2e8ca65782a6",
        5347,
        "d73c3660ee573d6399edd09826f6eeddb2e072835358fea54e01ebd7222f5e32",
        17833,
        "7a90ae3eb683132c01d3cdd713ced89524dd1f6bf890348c3305132c42fe4423",
    ),
    "ntt-tky11-location-page-current-captured-2026-07-20": (
        398469,
        "9fdc16dc63ef0a9eb90a85c15c3878c599352967fcd4f8c52ecfab7ff0d0d1cd",
        19121,
        "e3ea0bdd0f37ecfb9c904ad8caa68e8fdafd2492d1f8d7042d239d1f9eaef3bd",
        12246,
        "4f21fbe72d153449caa6d9ec048928a7c32b30929c3f6bec0c437e20f136837a",
    ),
    "ntt-data-tky11-tky12-release-2026-04-17-captured-2026-07-20": (
        43720,
        "5777f11a99478894a65c1b28386490ed1be78456cd34d93a5f7e097e1c9b8126",
        935,
        "5532ec6390c506bb53ce28ec0d0d4e4d02a3113dfce470e58ed4f4de1299a5de",
        15104,
        "0332c30b6b34b5a4655bd71c07203eb25e48fdd8e6534c7670e41670b6dafa8c",
    ),
    "ntt-group-data-center-briefing-2026-04-27-captured-2026-07-20": (
        6835719,
        "e6a181645bb0f4ed6fcd3ab1a07685be01f1b19f7bee7ece7d3a4f43a876e82f",
        687,
        "6f6da2471932f0532278bf6f48a5f69bdf3db66997dc6aef30db134977543b08",
        14030,
        "20c8d7998fd65cc9da07f9431d2bfd05dda0124bd1ab3037e05b3a205b1999a8",
    ),
    "ntt-tx4-location-page-current-captured-2026-07-20": (
        405925,
        "8477b8e75e9f30ee2c38136b7001042a18d16aafabf66725cd56e5b15115787f",
        19119,
        "38d52f895fa76d68d5f1f78b8b580a28a967f727f8c00815727416bc5f4344dd",
        12228,
        "0a0dce88d53aa377b4e686c59f3529e9fe4cc014c0eb0ceccaf1ad2375b35f92",
    ),
    "ntt-tx4-construction-timelapse-linkedin-2026-06-17-captured-2026-07-20": (
        129685,
        "aad2ec60df3f58a87d98d5656f58da9305c701276083920aa939b0510c554dad",
        5347,
        "fc3cd53da4e12710eb88aeff05e2ea7264519cf32d204d8e68fc8c2f6f4a2b60",
        17769,
        "ac4a4b395d4b0955c6aee9368d344353833ec0a215bbe0d1484a876344593826",
    ),
    "texas-tdlr-tabs-tx4-registration-captured-2026-07-20": (
        6707,
        "45286eacc336fe2095b5d5809daa2cfb7906088549181e20160bc8564ea174e2",
        978,
        "b5f516ad115c2998dbe75dc63173945d3d8802ccf880bff4e4d4b9a26439a34c",
        13149,
        "3c2c149ef45c6385d2c00a2c2e4c0afdb19ff3fd34b4cc4d54520ea8c5b4e105",
    ),
}


class NttCurrentConstructionCuratedTests(unittest.TestCase):
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
        order: tuple[str, ...],
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
                                retrieved_at=RETRIEVED_AT,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, name",
                    "SELECT entities.stable_key, metric, stage, base, target_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, base",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_exact_files_are_new_canonical_hash_pinned_and_source_scoped(self) -> None:
        self.assertEqual(len(SOURCES), 7)
        self.assertEqual(set(SOURCES), set(SOURCE_SPECS))
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(len(document["evidence"]), expected["evidence_count"])
                self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
                self.assertEqual(document["project"]["stable_key"], expected["project_key"])

        self.assertEqual(
            self._load(TKY11_B1_SOURCE)["evidence"][0],
            self._load(TKY11_B2_SOURCE)["evidence"][0],
        )

    def test_exact_capture_provenance_is_byte_bound(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            for item in self._load(name)["evidence"]:
                previous = evidence.setdefault(item["key"], item)
                self.assertEqual(previous, item)

        self.assertEqual(set(evidence), set(CAPTURES))
        self.assertEqual(len(evidence), 14)
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                (
                    body_bytes,
                    body_hash,
                    header_bytes,
                    header_hash,
                    facts_bytes,
                    facts_hash,
                ) = expected
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], body_hash)
                self.assertIn(f"{body_bytes}-byte", metadata["content_hash_scope"])
                self.assertIn(f"{header_bytes}-byte", metadata["capture_headers_scope"])
                self.assertEqual(metadata["capture_headers_sha256"], header_hash)
                self.assertIn(
                    f"{facts_bytes}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(metadata["capture_curl_writeout_sha256"], facts_hash)
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("retries disabled", metadata["retrieval_method"])
                self.assertIn(
                    "supplied no Authorization",
                    metadata["request_credentials_guardrail"],
                )
                self.assertIn("satellite imagery", metadata["imagery_guardrail"])

    def test_exact_status_capacity_role_and_geometry_semantics(self) -> None:
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                for entity in (document["campus"], document["project"]):
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["method"], "authoritative_locality")

                self.assertEqual(len(document["lifecycle"]), 1)
                lifecycle = document["lifecycle"][0]
                self.assertEqual(lifecycle["entity"], "project")
                self.assertEqual(lifecycle["value"], expected["status"])
                self.assertEqual(lifecycle["as_of_date"], expected["status_date"])
                self.assertEqual(lifecycle["method"], expected["status_method"])

                capacities = document["capacities"]
                self.assertEqual(
                    [(row["entity"], float(row["base"])) for row in capacities],
                    expected["capacities"],
                )
                for row in capacities:
                    self.assertEqual(row["metric"], "critical_it_mw")
                    self.assertEqual(row["stage"], "planned")
                    self.assertEqual(row["unit"], "MW")
                    self.assertEqual(row["low"], row["base"])
                    self.assertEqual(row["base"], row["high"])
                    self.assertIsNone(row["target_date"])
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])

    def test_scope_boundaries_nonoperation_and_exclusions_are_literal(self) -> None:
        tky1 = self._load(TKY11_B1_SOURCE)
        tky2 = self._load(TKY11_B2_SOURCE)
        tky_capacities = tky1["capacities"] + tky2["capacities"]
        self.assertEqual(
            [(row["entity"], row["base"]) for row in tky_capacities],
            [("campus", 50), ("project", 24), ("project", 26)],
        )
        self.assertFalse(any(row["base"] == 100 for row in tky_capacities))
        aliases = tky1["evidence"][0]["metadata"]["identity_aliases_retained"]
        self.assertEqual(aliases, ["Tokyo TKY11 Data Center", "Shiroi 1 Data Center", "SHR1"])
        self.assertEqual(tky2["lifecycle"][0]["value"], "announced")
        self.assertIn("No fourth 100 MW", tky1["evidence"][0]["metadata"]["capacity_guardrail"])

        ch3 = self._load(CH3_SOURCE)
        ch4 = self._load(CH4_SOURCE)
        self.assertEqual([row["base"] for row in ch3["capacities"]], [32])
        self.assertEqual(ch4["capacities"], [])
        self.assertIn("CH4 capacity remains null", ch4["evidence"][0]["metadata"]["capacity_guardrail"])
        self.assertIn("never assigned to CH4", ch3["capacities"][0]["notes"])

        osk12 = self._load(OSK12_SOURCE)
        self.assertEqual([row["base"] for row in osk12["capacities"]], [36, 18])
        self.assertFalse(any(row["base"] == 54 for row in osk12["capacities"]))
        self.assertIn("No 54 MW", osk12["evidence"][0]["metadata"]["capacity_guardrail"])

        jkt2a = self._load(JKT2A_SOURCE)
        self.assertEqual(jkt2a["lifecycle"][0]["value"], "shell")
        self.assertEqual(jkt2a["capacities"][0]["base"], 12)
        self.assertEqual(
            jkt2a["evidence"][0]["metadata"]["current_page_wording_as_captured"],
            "Jakarta 2A Data Center is coming soon.",
        )
        self.assertIn("no completion", jkt2a["evidence"][1]["metadata"]["completion_guardrail"])

        tx4 = self._load(TX4_SOURCE)
        self.assertEqual([row["base"] for row in tx4["capacities"]], [36])
        self.assertNotIn(124, [row["base"] for row in tx4["capacities"]])
        self.assertIn("2060 Lookout Drive", tx4["campus"]["address"])
        self.assertIn("2008 Lookout Drive", tx4["evidence"][2]["metadata"]["location_conflict"])
        self.assertIn("no frame", tx4["evidence"][1]["metadata"]["video_guardrail"].lower())
        self.assertIn("does not establish an opening date", tx4["evidence"][0]["metadata"]["availability_guardrail"])

        all_documents = [self._load(name) for name in SOURCES]
        all_keys = {
            document[entity]["stable_key"]
            for document in all_documents
            for entity in ("campus", "project")
        }
        for excluded in (
            "va11",
            "bkk3",
            "bkk4",
            "kol1",
            "nav2",
            "blr4a",
            "ph4",
            "osk11",
            "keihanna",
        ):
            self.assertFalse(any(excluded in key.lower() for key in all_keys), excluded)
        self.assertFalse(
            (ROOT / "sources" / "curated-official-2026-07-20-ntt-va11-gainesville.json").exists()
        )

        for document in all_documents:
            self.assertFalse(
                any(row["value"] == "operational" for row in document["lifecycle"])
            )
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["roles"], {})

    def test_each_source_imports_offline_in_isolation(self) -> None:
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, expected["evidence_count"])
                    self.assertEqual(validate_database(connection), [])
                    expected_counts = {
                        "evidence": expected["evidence_count"],
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": len(expected["capacities"]),
                    }
                    for table, count in expected_counts.items():
                        observed = connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        self.assertEqual(observed, count, table)
                finally:
                    connection.close()

    def test_combined_import_is_idempotent_order_independent_and_collision_safe(self) -> None:
        forward = self._state(SOURCES)
        reverse = self._state(tuple(reversed(SOURCES)))
        repeated = self._state(SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        entities, evidence, lifecycle, snapshots, capacities, models, workloads = forward
        self.assertEqual(len(entities), 12)
        self.assertEqual(len(evidence), 14)
        self.assertEqual(len(lifecycle), 7)
        self.assertEqual(len(snapshots), 13)
        self.assertEqual(len(capacities), 8)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            sorted(row[1] for row in lifecycle),
            ["announced", "shell"] + ["under_construction"] * 5,
        )
        self.assertEqual(sorted(row[3] for row in capacities), [12, 18, 24, 26, 32, 36, 36, 50])
        for row in snapshots:
            tags = json.loads(row[2])
            self.assertFalse(any(key.startswith("role:") for key in tags))
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
