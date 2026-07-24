from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T06:42:12Z"

DIGITAL_HALO_SOURCE = "curated-official-2026-07-20-digital-halo-jhb1-johor-topout.json"
SERVERFARM_SOURCE = "curated-official-2026-07-20-serverfarm-ctx2-houston-topout.json"
VANTAGE_SOURCE = "curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json"
VANTAGE_ACCEPTED_SUCCESSOR = (
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v5.json"
)
VANTAGE_ACCEPTED_SUCCESSOR_SHA256 = (
    "45b8ba2a95b743fbff19df93ce4cb9b846d92aa347360bfd0606dd32d1fc90d8"
)
VANTAGE_REJECTED_SUCCESSORS = {
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json": (
        "6cd9f44731f769cf03e68ec41ee018ac312a6f41ef2ddbb462bdd6f91f2fa728"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json": (
        "d053d2a638a73c8730e1c3eae22c2f7ac83842edff2f62e04ae30b231f70c15d"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json": (
        "4248a4487577cf53f56ba9d90aa5c0ad2b8e0a8330607e4fb5fc1bd25d719376"
    ),
}
CRANE_SOURCE = "curated-official-2026-07-20-crane-pdx-current-development.json"
JOULE_SOURCE = "curated-official-2026-07-20-joule-bettergrid-phase-1.json"
META_SUCCESSOR_SOURCE = (
    "curated-official-2026-07-20-meta-richland-parish-5gw-compute-successor.json"
)
META_IDENTITY_SOURCE = "curated-official-2026-07-19-meta-richland-parish.json"

SOURCES = (
    DIGITAL_HALO_SOURCE,
    SERVERFARM_SOURCE,
    VANTAGE_SOURCE,
    CRANE_SOURCE,
    JOULE_SOURCE,
    META_SUCCESSOR_SOURCE,
)
COMBINED_SOURCES = (META_IDENTITY_SOURCE,) + SOURCES
RETRIEVED_AT_BY_SOURCE = {
    **{name: RETRIEVED_AT for name in SOURCES},
    META_IDENTITY_SOURCE: "2026-07-19T11:41:40Z",
}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    DIGITAL_HALO_SOURCE: {
        "sha256": "dfac2adbae97ce67418a1818064dad510e8af1b5b0b316af38df648f32f5796b",
        "bytes": 7_833,
        "evidence_count": 1,
        "campus_key": "curated:digital-halo-johor-campus",
        "project_key": "curated:digital-halo-johor-campus:jhb1",
    },
    SERVERFARM_SOURCE: {
        "sha256": "dfd38f20bd4d8b2bcbf927cae5b5915d9e769e9f687aa7255801730d08673941",
        "bytes": 22_175,
        "evidence_count": 4,
        "campus_key": "curated:serverfarm-ctx-houston-campus",
        "project_key": "curated:serverfarm-ctx-houston-campus:ctx2",
    },
    VANTAGE_SOURCE: {
        "sha256": "587318195fb538e94bbbea1aea27abe12f47e7526b055acd8d22143815d13515",
        "bytes": 17_287,
        "evidence_count": 3,
        "campus_key": "curated:vantage-zrh1-winterthur-campus",
        "project_key": "curated:vantage-zrh1-winterthur-campus:zrh12",
    },
    CRANE_SOURCE: {
        "sha256": "46bf6c33739134c8653827d47eed2a7b4cb8f068a594c6c5b7cd5f7740d5c6b1",
        "bytes": 16_841,
        "evidence_count": 3,
        "campus_key": "curated:crane-portland-metro-forest-grove-campus",
        "project_key": (
            "curated:crane-portland-metro-forest-grove-campus:current-pdx-development"
        ),
    },
    JOULE_SOURCE: {
        "sha256": "4426ff573e5c5c62bd44edd752bee3102b26d34edc5184ae5dd15a11a075e1da",
        "bytes": 12_788,
        "evidence_count": 2,
        "campus_key": "curated:joule-bettergrid-millard-county-campus",
        "project_key": (
            "curated:joule-bettergrid-millard-county-campus:phase-1-development"
        ),
    },
    META_SUCCESSOR_SOURCE: {
        "sha256": "ea2ad4357ec401be3089b3ee6df9411d2ef466d6ea2daf971f0f39fa5ef9bf84",
        "bytes": 7_016,
        "evidence_count": 1,
        "campus_key": "curated:meta-richland-parish-data-center",
        "project_key": ("curated:meta-richland-parish-data-center:current-development"),
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "digital-halo-jhb1-topout-2026-04-27-captured-2026-07-20": {
        "body_bytes": 210_687,
        "body_sha256": "cae1ca2b3d8ab18a42f151862189ae28083b20e1c693afaa31882560f04f0493",
        "headers_bytes": 5_347,
        "headers_sha256": "ad168718cf3e8ba0f382eae15e15f63d214ff46223fb8bd2a725f47efc56dced",
        "writeout_bytes": 17_700,
        "writeout_sha256": "e3fd9ad37c2303ce438ffeebd151c1012d42187565db23452372ba894acf6819",
        "download_bytes": 22_594,
        "response_http_date": "2026-07-20T06:42:07Z",
        "source_url": (
            "https://www.linkedin.com/posts/digital-halo_johor-toppingout-"
            "hyperscale-activity-7454375035122683904-I6Nr"
        ),
    },
    "serverfarm-ctx2-topout-linkedin-2026-02-06-captured-2026-07-20": {
        "body_bytes": 212_575,
        "body_sha256": "e1839a7bb4a4624d6a5253f635e12e2e4753507152bc3113a2b96e96a3565b37",
        "headers_bytes": 5_615,
        "headers_sha256": "f5a7b7a3c896df4c38e24c9d61558ceb2e8881bc35cb0758a1b6f5170e11829f",
        "writeout_bytes": 17_703,
        "writeout_sha256": "aa5d9b9f9f6d173de5048ba8e82561de9d9c13964ac7646f1d1b65e440fd58ff",
        "download_bytes": 25_803,
        "response_http_date": "2026-07-20T06:42:07Z",
        "source_url": (
            "https://www.linkedin.com/posts/serverfarm_hyperscale-datacenter-"
            "houston-activity-7425621286208319488-PJoe"
        ),
    },
    "clune-serverfarm-ctx2-topout-linkedin-2026-02-09-captured-2026-07-20": {
        "body_bytes": 182_324,
        "body_sha256": "b3733b2c49dc53a264b19f567fd8e7515a31d9c92a6de5e5c57b737120e1878a",
        "headers_bytes": 5_347,
        "headers_sha256": "0a075aa8cc93d848ce9bc1485a6930478c335f7a73f2e58ced2a22f6f76bdbe9",
        "writeout_bytes": 17_818,
        "writeout_sha256": "14358e9026518e885aa3d4f15361f756133bcd6fb48d145c0940a0ad723d6262",
        "download_bytes": 21_789,
        "response_http_date": "2026-07-20T06:42:07Z",
        "source_url": (
            "https://www.linkedin.com/posts/cluneconstruction_"
            "datacenterconstruction-inpursuitofyourperfectproject-activity-"
            "7426660166546178048-shba"
        ),
    },
    "serverfarm-ctx2-structural-completion-blog-2026-02-27-captured-2026-07-20": {
        "body_bytes": 342_382,
        "body_sha256": "39d4edc7b575383fb22de4061a43a3aec98139ee88a5c6520c5efc679942ccf6",
        "headers_bytes": 1_936,
        "headers_sha256": "b02468c049328d7d6cac28efd8b2ac0f3a551552bf91021418978bb0f3536520",
        "writeout_bytes": 11_104,
        "writeout_sha256": "186bf3eead8efab104e0dbe0a8bcf5b31fb9493c4401fb7bd0499cbeedfaa63f",
        "download_bytes": 69_158,
        "response_http_date": "2026-07-20T06:42:07Z",
        "source_url": (
            "https://www.serverfarmllc.com/blog/ctx2-tops-out-serverfarm-marks-"
            "structural-completion-of-houstons-next-60mw-ai-ready-facility/"
        ),
    },
    "texas-tdlr-tabs2025014250-current-captured-2026-07-20": {
        "body_bytes": 16_630,
        "body_sha256": "fcd42eb8ea1a16613badf2fdf175887355fdcc7b81ba83e3a9399a75dd276b64",
        "headers_bytes": 979,
        "headers_sha256": "1ffecb29f39624481a0b344feedd3fc076429bb1f2af4ebc34dfd8fbff482a63",
        "writeout_bytes": 13_159,
        "writeout_sha256": "7e2a9189cf9be9d7659695a04ee94beeea0d073d9ff6d51d6dc7241ddf62256d",
        "download_bytes": 16_630,
        "response_http_date": "2026-07-20T06:42:07Z",
        "source_url": ("https://www.tdlr.texas.gov/TABS/Search/Project/TABS2025014250"),
    },
    "dpr-vantage-zrh12-topout-linkedin-2026-01-15-captured-2026-07-20": {
        "body_bytes": 189_145,
        "body_sha256": "652078eeff3b47877b2084e77bb8d0c6e41ef49b70f5f90f835d097214fdb913",
        "headers_bytes": 5_347,
        "headers_sha256": "0a1b6a10885024c4db807f0d92232c16d92cf6f559744c1c38154b7be8f165f3",
        "writeout_bytes": 17_808,
        "writeout_sha256": "f56846d6547e6ec134d4bd0c39ae25cb26361d54066f98f31703a6d86c51b226",
        "download_bytes": 22_590,
        "response_http_date": "2026-07-20T06:42:08Z",
        "source_url": (
            "https://www.linkedin.com/posts/dpr-construction-inc_datacenter-"
            "vantagedatacenters-projectmilestone-activity-"
            "7417373744987426816-REKH"
        ),
    },
    "vantage-zrh1-winterthur-campus-current-captured-2026-07-20": {
        "body_bytes": 220_986,
        "body_sha256": "211623c8cbbc8872dc91fc3fbfd062aa20222558ef237ed3bf94f408bc08fa62",
        "headers_bytes": 2_008,
        "headers_sha256": "37fc1f71a267af040cbf4ed69ef5f0b9c0c5d8c3bbf01ce2bd15a50895577ee3",
        "writeout_bytes": 9_532,
        "writeout_sha256": "63ae74fbdcd78edc82d59ecc4535ed09d90b62b67b94ff6cfd9f92224ba0a8c9",
        "download_bytes": 34_057,
        "response_http_date": "2026-07-20T06:42:11Z",
        "source_url": (
            "https://vantage-dc.com/data-center-locations/emea/zurich-i-switzerland/"
        ),
    },
    "vantage-zrh1-campus-datasheet-current-captured-2026-07-20": {
        "body_bytes": 2_056_913,
        "body_sha256": "14ba4c5b5ca07e7075c5cab500a2ad751fe9e859c6293f07488fa6399720360f",
        "headers_bytes": 746,
        "headers_sha256": "2129b1483869568dab009300b18661ec08efafcdf0819761626b4e5dc41d8988",
        "writeout_bytes": 9_562,
        "writeout_sha256": "0f7491a83eaf6b468682c7df1bd5765b6e7d68ff13bf8383bb0accc3871412b4",
        "download_bytes": 2_056_913,
        "response_http_date": "2026-07-20T06:42:08Z",
        "source_url": (
            "https://vantage-dc.com/wp-content/uploads/2024/04/"
            "VDC_DataSheet_Zurich-I_EN.pdf"
        ),
    },
    "crane-pdx-topout-linkedin-2025-12-10-captured-2026-07-20": {
        "body_bytes": 193_804,
        "body_sha256": "8c86b12d7104b3f1aac417338b271adc7df8c63a22639104dc7d5343f63fcf53",
        "headers_bytes": 5_347,
        "headers_sha256": "c088b2ad39b6b4369b914f8b9837e267159b5e0b47603b3d9097fbb04bdfc3fb",
        "writeout_bytes": 17_747,
        "writeout_sha256": "11420f52776a08e8b4205fddcbf599aee25c44d7d3a98649cba1e581adb13526",
        "download_bytes": 22_428,
        "response_http_date": "2026-07-20T06:42:11Z",
        "source_url": (
            "https://www.linkedin.com/posts/cranedc_toppingout-"
            "constructionmilestone-datacenters-activity-"
            "7404566916545171457-DG62"
        ),
    },
    "crane-oregon-campus-current-captured-2026-07-20": {
        "body_bytes": 34_089,
        "body_sha256": "d7e4cd368d46378d5736b63a78ab25657c15098a5289e0cfde2bba3e911298cc",
        "headers_bytes": 750,
        "headers_sha256": "2d21b147437ae084ccf9000c94c67eb97c8ad2fd099a20cbfe9f8763cbed8efe",
        "writeout_bytes": 9_468,
        "writeout_sha256": "f2156ea3115bafb2f3a64413bf17c2cc99c974d887f865404305f97b143b210f",
        "download_bytes": 7_333,
        "response_http_date": "2026-07-20T06:42:11Z",
        "source_url": "https://www.cranedc.com/data-centers/oregon-data-center",
    },
    "crane-pdx-campus-update-linkedin-2026-02-27-captured-2026-07-20": {
        "body_bytes": 376_847,
        "body_sha256": "bba291dd6999670d4483ea77924732e836517b82752dc7f1ee594b0f406f553a",
        "headers_bytes": 5_906,
        "headers_sha256": "567b3f647a0a1658bcce8c19455f9e26fc827a00856b22b2d4168783f650589d",
        "writeout_bytes": 17_703,
        "writeout_sha256": "74a866a7513a58a3aa350c9b58c409a64662539983d4f3ef6bc50164a10a5e75",
        "download_bytes": 35_549,
        "response_http_date": "2026-07-20T06:42:12Z",
        "source_url": (
            "https://www.linkedin.com/posts/cranedc_pdx-campus-update-were-"
            "officially-activity-7433223795106263040-rLp5"
        ),
    },
    "joule-bettergrid-home-current-captured-2026-07-20": {
        "body_bytes": 140_877,
        "body_sha256": "2c559e331e6615641c6ce275ecae8e3661bff096b31421c4c848ce1eb4f53a00",
        "headers_bytes": 951,
        "headers_sha256": "6f70fc8bcb912aa4cb027709fcdad41dc141a3c7541b92440e4dd25dfaef3d04",
        "writeout_bytes": 9_310,
        "writeout_sha256": "0c28209c4f3458c7057eaed24b1dcda2d2d209497963a0dc016de73a3132975a",
        "download_bytes": 26_434,
        "response_http_date": "2026-07-20T06:42:11Z",
        "source_url": "https://joulepower.ai/",
    },
    "joule-bettergrid-campus-current-captured-2026-07-20": {
        "body_bytes": 111_243,
        "body_sha256": "30fd4cccf6b236b5913b318e19adc3069be0793f27578e124746442b16de61ee",
        "headers_bytes": 956,
        "headers_sha256": "507897052eb26ffd832e1b5f862e9b8c7c434004228a853eba3122d6dcb0534b",
        "writeout_bytes": 9_360,
        "writeout_sha256": "4a88b95be539da14ef15a1c82d624caa5a9fb8a2aa6388703c903535df63ea4a",
        "download_bytes": 20_327,
        "response_http_date": "2026-07-20T06:42:12Z",
        "source_url": "https://joulepower.ai/campus-page/",
    },
    "meta-richland-parish-5gw-compute-2026-07-13-captured-2026-07-20": {
        "body_bytes": 354_606,
        "body_sha256": "90ce75edec92bb16e0481d7758b4cf204c9b1d2a70e1a9dd1ee42c6f3b5223e9",
        "headers_bytes": 806,
        "headers_sha256": "76ff9cf9fba9bba0df53cafc95fc1a029be922e60df22359fb20420b984ba179",
        "writeout_bytes": 11_481,
        "writeout_sha256": "48f130e953a77e7ba2b86ec3bd50c17de82bdcc1d9fd2b79555d7ccd3b8e4b37",
        "download_bytes": 85_024,
        "response_http_date": "2026-07-20T06:42:12Z",
        "source_url": (
            "https://about.fb.com/news/2026/07/teachers-local-businesses-win-"
            "as-meta-expands-louisiana-data-center/"
        ),
    },
}


class GlobalGapTrancheCuratedTests(unittest.TestCase):
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
                                retrieved_at=RETRIEVED_AT_BY_SOURCE[name],
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at, created_from_evidence_id "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, evidence_id, as_of_date, recorded_at, method "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, evidence_id",
                    "SELECT entities.stable_key, status, evidence_id, as_of_date, "
                    "recorded_at, method FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, evidence_id",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "evidence_id, as_of_date, recorded_at, target_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage, evidence_id",
                    "SELECT entities.stable_key, operating_model, evidence_id "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key, operating_model, evidence_id",
                    "SELECT entities.stable_key, workload, evidence_id "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload, evidence_id",
                    "SELECT entities.stable_key, projects.target_entity_id "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _assert_semantic_contract(
        self,
        documents: dict[str, dict[str, Any]],
    ) -> None:
        expected_lifecycle = {
            DIGITAL_HALO_SOURCE: [("project", "shell", "2026-04-27")],
            SERVERFARM_SOURCE: [("project", "shell", "2026-02-27")],
            VANTAGE_SOURCE: [("project", "shell", "2026-01-15")],
            CRANE_SOURCE: [("project", "shell", "2025-12-10")],
            JOULE_SOURCE: [("project", "under_construction", "2026-06-24")],
            META_SUCCESSOR_SOURCE: [],
        }
        expected_capacities = {
            DIGITAL_HALO_SOURCE: [("project", "critical_it_mw", "planned", 20)],
            SERVERFARM_SOURCE: [],
            VANTAGE_SOURCE: [("campus", "critical_it_mw", "planned", 40)],
            CRANE_SOURCE: [],
            JOULE_SOURCE: [],
            META_SUCCESSOR_SOURCE: [],
        }
        expected_keys = {
            name: (spec["campus_key"], spec["project_key"])
            for name, spec in SOURCE_SPECS.items()
        }

        self.assertEqual(set(documents), set(SOURCES))
        for name, document in documents.items():
            self.assertEqual(
                (
                    document["campus"]["stable_key"],
                    document["project"]["stable_key"],
                ),
                expected_keys[name],
            )
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertEqual(entity["roles"], {})
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(
                [
                    (row["entity"], row["value"], row["as_of_date"])
                    for row in document["lifecycle"]
                ],
                expected_lifecycle[name],
            )
            self.assertEqual(
                [
                    (row["entity"], row["metric"], row["stage"], row["base"])
                    for row in document["capacities"]
                ],
                expected_capacities[name],
            )

        serverfarm_blog = documents[SERVERFARM_SOURCE]["evidence"][2]["metadata"]
        self.assertEqual(
            serverfarm_blog["publisher_ceremony_date_as_reported"],
            "January 29, 2025",
        )
        self.assertIn(
            "internally impossible",
            serverfarm_blog["publisher_ceremony_date_error"],
        )
        self.assertIn(
            "never normalized",
            serverfarm_blog["publisher_date_error_handling"],
        )
        self.assertEqual(
            documents[VANTAGE_SOURCE]["evidence"][0]["metadata"][
                "reported_project_untyped_mw"
            ],
            8,
        )
        self.assertNotIn(
            "pdx01",
            documents[CRANE_SOURCE]["project"]["stable_key"].lower(),
        )
        self.assertNotIn(
            "pdx02",
            documents[CRANE_SOURCE]["project"]["stable_key"].lower(),
        )
        self.assertEqual(
            documents[JOULE_SOURCE]["evidence"][1]["metadata"][
                "reported_phase_1_facility_count"
            ],
            6,
        )
        self.assertEqual(
            documents[META_SUCCESSOR_SOURCE]["evidence"][0]["metadata"][
                "reported_compute_capacity_gw"
            ],
            5,
        )

    def test_sources_are_canonical_byte_pinned_ordinary_files(self) -> None:
        self.assertEqual(len(SOURCES), 6)
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(path.stat().st_size, expected["bytes"])
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
                self.assertEqual(
                    document["campus"]["stable_key"], expected["campus_key"]
                )
                self.assertEqual(
                    document["project"]["stable_key"], expected["project_key"]
                )

    def test_capture_provenance_is_exact_and_unauthenticated(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            for item in self._load(name)["evidence"]:
                self.assertNotIn(item["key"], evidence)
                evidence[item["key"]] = item

        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte",
                    metadata["content_hash_scope"],
                )
                self.assertIn(
                    f"{expected['headers_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download_bytes"],
                )
                self.assertEqual(
                    metadata["response_http_date"],
                    expected["response_http_date"],
                )
                self.assertEqual(item["source_url"], expected["source_url"])
                self.assertEqual(metadata["requested_url"], expected["source_url"])
                self.assertEqual(metadata["effective_url"], expected["source_url"])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("--disable", metadata["retrieval_method"])
                self.assertIn("--retry 0", metadata["retrieval_method"])
                self.assertIn("--connect-timeout 0", metadata["retrieval_method"])
                self.assertIn("--max-time 0", metadata["retrieval_method"])
                self.assertIn(
                    "supplied no Authorization",
                    metadata["request_credentials_guardrail"],
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )

    def test_new_keys_are_collision_checked_against_every_curated_file(self) -> None:
        successor_paths = {
            VANTAGE_SOURCE,
            VANTAGE_ACCEPTED_SUCCESSOR,
        }
        for name, expected_hash in (
            (VANTAGE_ACCEPTED_SUCCESSOR, VANTAGE_ACCEPTED_SUCCESSOR_SHA256),
            *VANTAGE_REJECTED_SUCCESSORS.items(),
        ):
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash
            )

        vantage = self._load(VANTAGE_SOURCE)
        vantage_evidence_keys = {item["key"] for item in vantage["evidence"]}
        vantage_stable_keys = {
            vantage[entity]["stable_key"] for entity in ("campus", "project")
        }
        evidence_appearances: dict[str, list[str]] = defaultdict(list)
        stable_appearances: dict[str, list[tuple[str, str, str, str, str]]] = (
            defaultdict(list)
        )
        for path in sorted((ROOT / "sources").glob("curated-*.json")):
            if path.name in VANTAGE_REJECTED_SUCCESSORS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for item in document.get("evidence", []):
                evidence_appearances[item["key"]].append(path.name)
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if not isinstance(entity, dict):
                    continue
                stable_appearances[entity["stable_key"]].append(
                    (
                        path.name,
                        entity["name"],
                        entity["country"],
                        entity["address"],
                        kind,
                    )
                )

        for key in CAPTURES:
            with self.subTest(evidence_key=key):
                if key in vantage_evidence_keys:
                    self.assertEqual(set(evidence_appearances[key]), successor_paths)
                else:
                    self.assertEqual(len(evidence_appearances[key]), 1)

        meta_keys = {
            "curated:meta-richland-parish-data-center",
            "curated:meta-richland-parish-data-center:current-development",
        }
        for expected in SOURCE_SPECS.values():
            for key in (expected["campus_key"], expected["project_key"]):
                with self.subTest(stable_key=key):
                    appearances = stable_appearances[key]
                    if key in meta_keys:
                        self.assertEqual(len(appearances), 2)
                        identities = {
                            (name, country, address, kind)
                            for _, name, country, address, kind in appearances
                        }
                        self.assertEqual(len(identities), 1)
                        self.assertEqual(
                            {path for path, *_ in appearances},
                            {META_IDENTITY_SOURCE, META_SUCCESSOR_SOURCE},
                        )
                    elif key in vantage_stable_keys:
                        self.assertEqual(len(appearances), 2)
                        identities = {
                            (name, country, address, kind)
                            for _, name, country, address, kind in appearances
                        }
                        self.assertEqual(len(identities), 1)
                        self.assertEqual(
                            {path for path, *_ in appearances}, successor_paths
                        )
                    else:
                        self.assertEqual(len(appearances), 1)

    def test_document_semantics_match_the_narrow_acceptance_boundary(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        self._assert_semantic_contract(documents)
        for name, document in documents.items():
            with self.subTest(source=name):
                for entity_name in ("campus", "project"):
                    entity = document[entity_name]
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])

        halo = documents[DIGITAL_HALO_SOURCE]
        self.assertEqual(
            [(row["value"], row["entity"]) for row in halo["lifecycle"]],
            [("shell", "project")],
        )
        self.assertEqual(len(halo["capacities"]), 1)
        self.assertEqual(
            {
                key: halo["capacities"][0][key]
                for key in ("entity", "metric", "stage", "base")
            },
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "base": 20,
            },
        )

        serverfarm = documents[SERVERFARM_SOURCE]
        self.assertEqual(
            [(row["value"], row["entity"]) for row in serverfarm["lifecycle"]],
            [("shell", "project")],
        )
        self.assertEqual(serverfarm["capacities"], [])
        blog = next(
            item
            for item in serverfarm["evidence"]
            if item["key"].startswith("serverfarm-ctx2-structural-completion")
        )["metadata"]
        self.assertEqual(
            blog["publisher_ceremony_date_as_reported"], "January 29, 2025"
        )
        self.assertIn("internally impossible", blog["publisher_ceremony_date_error"])
        self.assertEqual(blog["reported_full_facility_mw"], 60)
        self.assertEqual(blog["reported_future_available_for_occupancy_mw"], 36)
        self.assertIn("never normalized", blog["publisher_date_error_handling"])

        vantage = documents[VANTAGE_SOURCE]
        self.assertEqual(
            [(row["value"], row["entity"]) for row in vantage["lifecycle"]],
            [("shell", "project")],
        )
        self.assertEqual(len(vantage["capacities"]), 1)
        self.assertEqual(
            {
                key: vantage["capacities"][0][key]
                for key in ("entity", "metric", "stage", "base")
            },
            {
                "entity": "campus",
                "metric": "critical_it_mw",
                "stage": "planned",
                "base": 40,
            },
        )
        dpr = vantage["evidence"][0]["metadata"]
        self.assertEqual(dpr["reported_project_untyped_mw"], 8)
        self.assertIn("no project capacity row", dpr["project_capacity_guardrail"])

        crane = documents[CRANE_SOURCE]
        self.assertEqual(
            [(row["value"], row["entity"]) for row in crane["lifecycle"]],
            [("shell", "project")],
        )
        self.assertEqual(crane["capacities"], [])
        self.assertNotIn("pdx01", crane["project"]["stable_key"].lower())
        self.assertNotIn("pdx02", crane["project"]["stable_key"].lower())
        campus_metadata = crane["evidence"][1]["metadata"]
        self.assertEqual(
            campus_metadata["reported_design_pue_at_full_it_capacity"], 1.3
        )
        self.assertIn("no capacity", campus_metadata["capacity_guardrail"].lower())

        joule = documents[JOULE_SOURCE]
        self.assertEqual(
            [(row["value"], row["entity"]) for row in joule["lifecycle"]],
            [("under_construction", "project")],
        )
        self.assertEqual(joule["capacities"], [])
        self.assertEqual(len({joule["project"]["stable_key"]}), 1)
        self.assertEqual(
            joule["evidence"][1]["metadata"]["reported_phase_1_facility_count"], 6
        )
        self.assertIn(
            "do not create six projects",
            joule["evidence"][1]["metadata"]["facility_count_guardrail"],
        )

        meta = documents[META_SUCCESSOR_SOURCE]
        old_meta = self._load(META_IDENTITY_SOURCE)
        for entity_name in ("campus", "project"):
            for field in ("stable_key", "name", "country", "address"):
                self.assertEqual(meta[entity_name][field], old_meta[entity_name][field])
        self.assertEqual(meta["lifecycle"], [])
        self.assertEqual(meta["capacities"], [])
        meta_metadata = meta["evidence"][0]["metadata"]
        self.assertEqual(meta_metadata["reported_compute_capacity_gw"], 5)
        self.assertIn(
            "not a defined electrical-power metric", meta_metadata["capacity_guardrail"]
        )
        self.assertIn("adds no lifecycle row", meta_metadata["lifecycle_guardrail"])

        serialized = json.dumps(documents, sort_keys=True).lower()
        self.assertNotIn("novva", serialized)

    def test_semantic_leakage_mutations_fail_the_focused_contract(self) -> None:
        original = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, dict[str, Any]]]] = []

        candidate = copy.deepcopy(original)
        candidate[DIGITAL_HALO_SOURCE]["campus"]["roles"] = {
            "operator": ["Digital Halo"]
        }
        mutations.append(("inferred-role", candidate))

        candidate = copy.deepcopy(original)
        candidate[VANTAGE_SOURCE]["project"]["coordinates"] = {
            "latitude": 47.5,
            "longitude": 8.7,
        }
        mutations.append(("inferred-coordinate", candidate))

        candidate = copy.deepcopy(original)
        candidate[CRANE_SOURCE]["workloads"].append(
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
            }
        )
        mutations.append(("inferred-workload", candidate))

        candidate = copy.deepcopy(original)
        candidate[DIGITAL_HALO_SOURCE]["capacities"][0]["base"] = 21
        mutations.append(("jhb1-capacity-drift", candidate))

        candidate = copy.deepcopy(original)
        leaked_capacity = copy.deepcopy(candidate[DIGITAL_HALO_SOURCE]["capacities"][0])
        leaked_capacity["base"] = 60
        leaked_capacity["low"] = 60
        leaked_capacity["high"] = 60
        candidate[SERVERFARM_SOURCE]["capacities"].append(leaked_capacity)
        mutations.append(("ctx2-60mw-promotion", candidate))

        candidate = copy.deepcopy(original)
        candidate[SERVERFARM_SOURCE]["lifecycle"][0]["as_of_date"] = "2025-01-29"
        mutations.append(("ctx2-impossible-ceremony-date-promotion", candidate))

        candidate = copy.deepcopy(original)
        project_capacity = copy.deepcopy(candidate[VANTAGE_SOURCE]["capacities"][0])
        project_capacity.update({"entity": "project", "low": 8, "base": 8, "high": 8})
        candidate[VANTAGE_SOURCE]["capacities"].append(project_capacity)
        mutations.append(("zrh12-untyped-8mw-promotion", candidate))

        candidate = copy.deepcopy(original)
        candidate[CRANE_SOURCE]["project"]["stable_key"] = (
            "curated:crane-portland-metro-forest-grove-campus:pdx01"
        )
        mutations.append(("crane-facility-code-inference", candidate))

        candidate = copy.deepcopy(original)
        joule_capacity = copy.deepcopy(candidate[DIGITAL_HALO_SOURCE]["capacities"][0])
        joule_capacity.update({"low": 1000, "base": 1000, "high": 1000})
        candidate[JOULE_SOURCE]["capacities"].append(joule_capacity)
        mutations.append(("joule-gw-promotion", candidate))

        candidate = copy.deepcopy(original)
        candidate[JOULE_SOURCE]["project"]["stable_key"] = (
            "curated:joule-bettergrid-millard-county-campus:building-a"
        )
        mutations.append(("joule-facility-identity-inference", candidate))

        candidate = copy.deepcopy(original)
        candidate[META_SUCCESSOR_SOURCE]["lifecycle"].append(
            copy.deepcopy(candidate[JOULE_SOURCE]["lifecycle"][0])
        )
        mutations.append(("meta-lifecycle-promotion", candidate))

        candidate = copy.deepcopy(original)
        meta_capacity = copy.deepcopy(candidate[VANTAGE_SOURCE]["capacities"][0])
        meta_capacity.update({"low": 5000, "base": 5000, "high": 5000})
        candidate[META_SUCCESSOR_SOURCE]["capacities"].append(meta_capacity)
        mutations.append(("meta-compute-to-power-promotion", candidate))

        candidate = copy.deepcopy(original)
        candidate[META_SUCCESSOR_SOURCE]["campus"]["stable_key"] = (
            "curated:meta-hyperion-data-center"
        )
        mutations.append(("meta-hyperion-alias", candidate))

        candidate = copy.deepcopy(original)
        candidate[SERVERFARM_SOURCE]["evidence"][2]["metadata"][
            "publisher_date_error_handling"
        ] = "Use the reported ceremony date."
        mutations.append(("ctx2-publisher-error-erasure", candidate))

        for label, documents in mutations:
            with self.subTest(mutation=label):
                with self.assertRaises(AssertionError):
                    self._assert_semantic_contract(documents)

    def test_import_is_offline_idempotent_and_order_independent(self) -> None:
        forward = self._state(SOURCES)
        reverse = self._state(reversed(SOURCES))
        repeated = self._state(SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        with_identity_forward = self._state(COMBINED_SOURCES)
        with_identity_reverse = self._state(reversed(COMBINED_SOURCES))
        with_identity_repeated = self._state(COMBINED_SOURCES, repetitions=2)
        self.assertEqual(with_identity_forward, with_identity_reverse)
        self.assertEqual(with_identity_forward, with_identity_repeated)

    def test_normalized_rows_have_only_the_accepted_positive_claims(self) -> None:
        state = self._state(SOURCES)
        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            models,
            workloads,
            projects,
        ) = state
        self.assertEqual(len(entities), 12)
        self.assertEqual(len(evidence), 14)
        self.assertEqual(len(snapshots), 12)
        self.assertEqual(len(projects), 6)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())

        for row in snapshots:
            with self.subTest(stable_key=row[0]):
                tags = json.loads(row[2])
                self.assertIsNone(row[3])
                self.assertIsNone(row[4])
                self.assertIsNone(row[5])
                self.assertFalse(any(key.startswith("role:") for key in tags))

        self.assertEqual(
            {(row[0], row[1], row[3]) for row in lifecycle},
            {
                ("curated:digital-halo-johor-campus:jhb1", "shell", "2026-04-27"),
                ("curated:serverfarm-ctx-houston-campus:ctx2", "shell", "2026-02-27"),
                ("curated:vantage-zrh1-winterthur-campus:zrh12", "shell", "2026-01-15"),
                (
                    "curated:crane-portland-metro-forest-grove-campus:"
                    "current-pdx-development",
                    "shell",
                    "2025-12-10",
                ),
                (
                    "curated:joule-bettergrid-millard-county-campus:"
                    "phase-1-development",
                    "under_construction",
                    "2026-06-24",
                ),
            },
        )
        self.assertEqual(
            {(row[0], row[1], row[2], row[4]) for row in capacities},
            {
                (
                    "curated:digital-halo-johor-campus:jhb1",
                    "critical_it_mw",
                    "planned",
                    20.0,
                ),
                (
                    "curated:vantage-zrh1-winterthur-campus",
                    "critical_it_mw",
                    "planned",
                    40.0,
                ),
            },
        )

    def test_meta_successor_reuses_identity_without_new_claim_rows(self) -> None:
        state = self._state((META_IDENTITY_SOURCE, META_SUCCESSOR_SOURCE))
        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            models,
            workloads,
            projects,
        ) = state
        self.assertEqual(len(entities), 2)
        self.assertEqual(len(evidence), 2)
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(len(projects), 1)
        self.assertEqual(len(lifecycle), 1)
        self.assertEqual(capacities, ())
        self.assertEqual(len(models), 1)
        self.assertEqual(len(workloads), 1)

        successor_key = (
            "meta-richland-parish-5gw-compute-2026-07-13-captured-2026-07-20"
        )
        successor_hash = CAPTURES[successor_key]["body_sha256"]
        successor_evidence_rows = [
            row
            for row in evidence
            if row[0] == successor_key and row[1] == successor_hash
        ]
        self.assertEqual(len(successor_evidence_rows), 1)
        successor_snapshots = [row for row in snapshots if row[8] == RETRIEVED_AT]
        self.assertEqual(len(successor_snapshots), 2)
        for row in successor_snapshots:
            tags = json.loads(row[2])
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])
            self.assertFalse(any(key.startswith("role:") for key in tags))
        self.assertFalse(any(row[4] == RETRIEVED_AT for row in lifecycle))


if __name__ == "__main__":
    unittest.main()
