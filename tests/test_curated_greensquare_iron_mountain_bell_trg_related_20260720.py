from __future__ import annotations

from contextlib import ExitStack
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

GREEN_SOURCE = "curated-official-2026-07-20-greensquaredc-syd1-stage2.json"
IRON_SOURCE = "curated-official-2026-07-20-iron-mountain-mum3-navi-mumbai.json"
BELL_SOURCE = "curated-official-2026-07-20-bell-ai-fabric-saskatchewan.json"
TRG_SOURCE = "curated-official-2026-07-20-trg-hou2-spring-texas.json"
RELATED_SOURCE = "curated-official-2026-07-20-related-digital-cheyenne-phase1.json"
SOURCES = (
    GREEN_SOURCE,
    IRON_SOURCE,
    BELL_SOURCE,
    TRG_SOURCE,
    RELATED_SOURCE,
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    GREEN_SOURCE: {
        "bytes": 17_017,
        "sha256": "7e5628efb8beae2a3e43c015800dfe37d4ea74f2a58e4b227e0b23c2e83adfa4",
        "retrieved_at": "2026-07-20T17:35:25Z",
        "evidence_count": 3,
        "campus_key": "curated:greensquaredc-syd1-norwest-campus",
        "project_key": "curated:greensquaredc-syd1-norwest-campus:stage-2",
    },
    IRON_SOURCE: {
        "bytes": 13_319,
        "sha256": "6913bff64fb893a8377ad384936a8873f1d886b1654590ac62d8b7f7130e3080",
        "retrieved_at": "2026-07-20T17:32:09Z",
        "evidence_count": 2,
        "campus_key": "curated:iron-mountain-navi-mumbai-campus",
        "project_key": "curated:iron-mountain-navi-mumbai-campus:mum-3",
    },
    BELL_SOURCE: {
        "bytes": 18_277,
        "sha256": "212173178a5b04e1299ef62bd8de0aabac6cdcdb84132fb53d06ba6bb2994a39",
        "retrieved_at": "2026-07-20T17:32:10Z",
        "evidence_count": 3,
        "campus_key": "curated:bell-ai-fabric-sherwood-campus",
        "project_key": ("curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility"),
    },
    TRG_SOURCE: {
        "bytes": 9_056,
        "sha256": "1689c544d726d8eb9c1e21602c8b3e8a20209c7e5650b84e589ad604a4bff60d",
        "retrieved_at": "2026-07-20T17:32:09Z",
        "evidence_count": 1,
        "campus_key": "curated:trg-spring-cypress-campus",
        "project_key": "curated:trg-spring-cypress-campus:hou2",
    },
    RELATED_SOURCE: {
        "bytes": 16_925,
        "sha256": "5889a849ed963fd59b944d2c2da0bfa0d8920eaf76489a0c6f8f68f7c25119c2",
        "retrieved_at": "2026-07-20T17:32:09Z",
        "evidence_count": 3,
        "campus_key": "curated:related-digital-cheyenne-campus",
        "project_key": "curated:related-digital-cheyenne-campus:phase-1",
    },
}

CAPTURES: dict[str, tuple[int, str, int, str, int, str]] = {
    "greensquaredc-syd1-construction-2026-01-14-captured-2026-07-20": (
        55_304,
        "ca42835bbaef09a7cf254acc7954a357d159271a017f329243a96fba6edca389",
        550,
        "84279fdaf5037c56a6a62bf042c7715bf462c602b870e1d61ea1b106a299449d",
        16_678,
        "4efe7a3836985c1d93959b46091f0c8e60d1177daf5633094de3ab05fb8b9575",
    ),
    "greensquaredc-syd1-locations-wayback-2025-11-26-captured-2026-07-20": (
        56_782,
        "20ffb381c37bb904cde57ebf6064ce6f99d180c5fccd1a3ad2c0c054e2bafa2b",
        2_316,
        "b0082b07c536c7c55dba3eaaeaff210351ce06108055f53a4197c917ea1e44f9",
        18_509,
        "7bee7e9a4e56189f1deb36df06c5ac84c97123bf9d3ecd1699f2bc5f3ea63102",
    ),
    "greensquaredc-syd1-locations-current-captured-2026-07-20": (
        53_528,
        "04e23f5146172d4bbc3e6a1aaa29e2081f8a20e539b6e26ad5b4c30c4ce2ee35",
        550,
        "3cde40f713ed062b9cf124fd0bf392cf7a324568fb768c7701c20ce328f471d4",
        16_255,
        "c21943936730a34e0bea2d406f8f0aeda0451decfc64e5303081a833c294281e",
    ),
    "iron-mountain-mum3-groundbreaking-linkedin-2026-01-20-captured-2026-07-20": (
        126_477,
        "5820ea8c115906490a0d3b857d700545b38d366777e366b0475657b18dc613b0",
        5_349,
        "759a0834665975005ec81cb8c4a9806f604d744a23944801c7b0bcc0e7e7cda6",
        16_507,
        "e60d7b001bb1f5bee5acbee10e6467c727c5671fa10982534bf8e74f5011c992",
    ),
    "iron-mountain-india-current-mum3-captured-2026-07-20": (
        134_699,
        "0d787499cd5eed7e585d745c4cdeed3bd01ca5dbb168871dd26f461e92fb26be",
        3_158,
        "86137d34ce3f8c854aff4789068b8c1a7e4ad2d51a4d2bc1d233049d7abd7ebf",
        9_682,
        "fb54c71c815cf26829a9737488bdd090401aae7cab45bd183c875925ca210a51",
    ),
    "bell-sherwood-early-site-works-2026-05-04-captured-2026-07-20": (
        521_268,
        "1f229bdfebfece69bb0626bb4df418e6e02e2c53ad4d2a9cab59fd68aaae5e87",
        3_576,
        "5473dcaadc5a6050a57aeed002e126d4c1ffa4dca7afb69bc1f606cbcf0c0845",
        19_336,
        "dd91617b20bd66e527c409da1210991e1eed29d7c73192e1ee3cb91cedef372e",
    ),
    "bell-sherwood-construction-partners-2026-05-14-captured-2026-07-20": (
        536_021,
        "25716e7dbac99c92446fe7661287e4671167005531a706cbfd317b3dc85e1549",
        3_566,
        "035420b5389ba9b2dfbe092828be750015c816a9f8e3c13eca34373d94c41c4f",
        19_534,
        "18698b128ce097b001aaf29decf1d2d12baab040e3a342f2b1e46bae3429c73c",
    ),
    "bell-sherwood-community-current-captured-2026-07-20": (
        109_500,
        "4da8478aaa8f5475b4580b8eb92b82fc9e385baf52661453a6f779a37a500b82",
        1_030,
        "f0caac7268050a6b4e977097a873334fb18e20c14881eb12201eed2e4ff67a49",
        16_241,
        "60d6153b817cb4691840ac2c8737c29dad10eaa12375a692601c7c2db4fa09de",
    ),
    "trg-hou2-campus-brochure-2026-captured-2026-07-20": (
        3_679_553,
        "5864de217fc954c10498ada7c05978ea634077106de20aae26c5bebb02ded605",
        743,
        "cfe4394991bac802767a4fce6cf49222f0877c7db693729050035bb777bf0744",
        9_711,
        "49c954426ae94e894fe26293d2d9cedeac6cd974f291b14428ffa16a49a2ebb3",
    ),
    "related-digital-cheyenne-current-captured-2026-07-20": (
        505_940,
        "96662e2e42875d37ee182665b40e0b54ac086365fb2eb2633b5a8e1cf5105783",
        554,
        "d4f2afc2b16de6c6993ff5ccc9e623d8023221bacfb7ba96c995c18f6e50016a",
        16_233,
        "c8588b20e6dc2b3969da9f448a77df0b2ac51a12e6ae29cce81eb868ad22d456",
    ),
    "clayco-related-cheyenne-current-captured-2026-07-20": (
        141_144,
        "2678b4f72cdb3000d6b3f6237c2b68c27e246fa1f7ceb0e6a40c2ccc961c6a71",
        870,
        "c051ae9ea21dcf6bdb0a4ef3c18550324dfa18fd29a547e6b727c20d7367221e",
        9_564,
        "139419bdf13cf0720ced55ec624a1be778c2fcb7f794759b91f398e832fbfc8f",
    ),
    "related-digital-cheyenne-news-index-2026-06-14-captured-2026-07-20": (
        924_645,
        "1938c6f5c3c6e5c6b18ffbeebd543ccacbe6b6e8f78149a5a6c857ae1eb77b6a",
        553,
        "3191ececcb21fbce30436763c190c33a55661ed7c30e72d1f6649de7333897ea",
        16_218,
        "309f4c9688cbef5eaf41ecc05469e48ed36448e03d741a05e32f5f059c23aa20",
    ),
}


class CuratedOfficialFiveGapTests(unittest.TestCase):
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

    def test_exact_files_are_canonical_hash_pinned_and_source_scoped(self) -> None:
        self.assertEqual(len(SOURCES), 5)
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
                self.assertEqual(
                    document["project"]["stable_key"], expected["project_key"]
                )
                self.assertIsNone(document["campus"]["coordinates"])
                self.assertIsNone(document["campus"]["geometry"])
                self.assertIsNone(document["project"]["coordinates"])
                self.assertIsNone(document["project"]["geometry"])
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                self.assertNotIn("/private/tmp", text)

    def test_capture_hashes_dates_and_failed_fetch_boundaries_are_exact(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            document = self._load(name)
            expected_retrieved_at = SOURCE_SPECS[name]["retrieved_at"]
            for item in document["evidence"]:
                self.assertEqual(item["retrieved_at"], expected_retrieved_at)
                self.assertTrue(item["source_url"].startswith("https://"))
                self.assertNotIn(item["key"], evidence)
                evidence[item["key"]] = item

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

        green = self._load(GREEN_SOURCE)
        green_by_key = {item["key"]: item for item in green["evidence"]}
        green_news = green_by_key[
            "greensquaredc-syd1-construction-2026-01-14-captured-2026-07-20"
        ]
        archived = green_by_key[
            "greensquaredc-syd1-locations-wayback-2025-11-26-captured-2026-07-20"
        ]
        current = green_by_key[
            "greensquaredc-syd1-locations-current-captured-2026-07-20"
        ]
        self.assertEqual(green_news["published_at"], "2026-01-14T08:37:49+11:00")
        self.assertIsNone(archived["published_at"])
        self.assertIsNone(current["published_at"])
        archive_index = archived["metadata"]["archive_index_capture"]
        self.assertEqual(archive_index["body_bytes"], 284)
        self.assertEqual(
            archive_index["body_sha256"],
            "fd3cfe685a648b87d1ef12c68d8c1b6d937f8a6f34ef4bdecfd9373596767278",
        )
        self.assertEqual(archive_index["headers_bytes"], 598)
        self.assertEqual(
            archive_index["headers_sha256"],
            "a3ef3028ac4d964f7fef0f4e01e32f553cdaa77ab806a0816807832b7b68cc30",
        )
        self.assertEqual(archive_index["writeout_bytes"], 19_076)
        self.assertEqual(
            archive_index["writeout_sha256"],
            "ef274a439ad8ddb4b41a96df2ce820afbcdddb85ea4c0226680e6625efb3b872",
        )

        iron = self._load(IRON_SOURCE)
        iron_by_key = {item["key"]: item for item in iron["evidence"]}
        post = iron_by_key[
            "iron-mountain-mum3-groundbreaking-linkedin-2026-01-20-captured-2026-07-20"
        ]
        self.assertEqual(post["published_at"], "2026-01-20T08:00:02.667Z")
        self.assertIsNone(
            iron_by_key["iron-mountain-india-current-mum3-captured-2026-07-20"][
                "published_at"
            ]
        )
        blocked = post["metadata"]["blocked_official_news_capture"]
        self.assertEqual(blocked["http_status"], 429)
        self.assertFalse(blocked["response_body_retained"])
        self.assertEqual(blocked["headers_bytes"], 501)
        self.assertEqual(
            blocked["headers_sha256"],
            "61fa0506511015663d6a0aedd822100823ca3d4827ab156d6ed6e424a4a76587",
        )
        self.assertEqual(blocked["writeout_bytes"], 11_981)
        self.assertEqual(
            blocked["writeout_sha256"],
            "30641eef4c923e80013a05dd377afc41836e620890e8b7e0f498cb7cb456bef8",
        )

        bell = self._load(BELL_SOURCE)
        self.assertEqual(
            [item["published_at"] for item in bell["evidence"]],
            ["2026-05-04", "2026-05-14", None],
        )
        self.assertIsNone(self._load(TRG_SOURCE)["evidence"][0]["published_at"])
        related = self._load(RELATED_SOURCE)
        self.assertEqual(
            [item["published_at"] for item in related["evidence"]],
            [None, None, "2026-06-14"],
        )

    def test_normalized_claims_roles_and_scope_guardrails_are_exact(self) -> None:
        green = self._load(GREEN_SOURCE)
        self.assertEqual(
            green["lifecycle"],
            [
                {
                    "entity": "campus",
                    "value": "under_construction",
                    "evidence_key": (
                        "greensquaredc-syd1-construction-2026-01-14-captured-2026-07-20"
                    ),
                    "as_of_date": "2026-01-14",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            [
                (row["entity"], row["metric"], row["stage"], row["base"])
                for row in green["capacities"]
            ],
            [("project", "critical_it_mw", "planned", 96)],
        )
        self.assertIn(
            "not substituted for, added to, or used to recalculate",
            green["evidence"][2]["metadata"]["capacity_conflict_guardrail"],
        )

        iron = self._load(IRON_SOURCE)
        self.assertEqual(iron["campus"]["roles"], {})
        self.assertEqual(iron["project"]["roles"], {})
        self.assertEqual(iron["lifecycle"][0]["as_of_date"], "2026-01-20")
        self.assertEqual(
            [(row["metric"], row["stage"], row["base"]) for row in iron["capacities"]],
            [("critical_it_mw", "planned", 85)],
        )
        self.assertIn(
            "MUM-3 beside MUM-1 and MUM-2",
            iron["evidence"][0]["metadata"]["identity_guardrail"],
        )

        bell = self._load(BELL_SOURCE)
        self.assertEqual(bell["campus"]["roles"], {"utility": ["SaskPower"]})
        self.assertEqual(
            bell["project"]["roles"],
            {
                "contractor": ["Bird Construction Inc."],
                "customer": ["Cerebras", "CoreWeave"],
            },
        )
        self.assertEqual(bell["lifecycle"][0]["as_of_date"], "2026-04-21")
        self.assertEqual(
            [(row["metric"], row["stage"], row["base"]) for row in bell["capacities"]],
            [("gross_facility_mw", "planned", 300)],
        )
        self.assertIn(
            "gross power demand up to 300 MW",
            bell["evidence"][2]["metadata"]["gross_power_demand_wording_as_reported"],
        )

        trg = self._load(TRG_SOURCE)
        self.assertEqual(trg["campus"]["roles"], {"owner": ["TRG Datacenters"]})
        self.assertEqual(trg["project"]["roles"], {})
        self.assertEqual(
            [
                (row["entity"], row["metric"], row["stage"], row["base"])
                for row in trg["capacities"]
            ],
            [
                ("campus", "grid_connection_mw", "planned", 30),
                ("project", "grid_connection_mw", "planned", 24),
            ],
        )
        serialized_trg_capacities = json.dumps(trg["capacities"], sort_keys=True)
        self.assertNotIn('"base": 12', serialized_trg_capacities)
        self.assertNotIn("105M", serialized_trg_capacities)
        self.assertIn(
            "HOU1 and HOU2",
            trg["evidence"][0]["metadata"]["campus_identity_advisory"],
        )

        related = self._load(RELATED_SOURCE)
        self.assertEqual(related["campus"]["roles"], {"developer": ["Related Digital"]})
        self.assertEqual(
            related["project"]["roles"],
            {"contractor": ["Clayco"], "tenant": ["CoreWeave"]},
        )
        self.assertEqual(
            [
                (row["metric"], row["stage"], row["base"])
                for row in related["capacities"]
            ],
            [("critical_it_mw", "planned", 88)],
        )
        self.assertIn(
            "distinct from Meta's separate Cheyenne project",
            related["evidence"][0]["metadata"]["identity_guardrail"],
        )
        self.assertIn(
            "302 MW",
            related["evidence"][1]["metadata"]["capacity_guardrail"],
        )
        self.assertIn(
            "420 MW",
            related["evidence"][1]["metadata"]["capacity_guardrail"],
        )

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
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, expected["evidence_count"]
                    )
                    self.assertEqual(result.warnings, ())
                    self.assertEqual(validate_database(connection), [])
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM entities").fetchone()[
                            0
                        ],
                        2,
                    )
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[
                            0
                        ],
                        expected["evidence_count"],
                    )
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
        self.assertEqual(len(evidence), 12)
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(len(lifecycle), 5)
        self.assertEqual(len(capacities), 6)
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
                    "curated:greensquaredc-syd1-norwest-campus",
                    "under_construction",
                    "2026-01-14",
                    "authoritative_physical_status_update",
                ),
                (
                    "curated:iron-mountain-navi-mumbai-campus:mum-3",
                    "under_construction",
                    "2026-01-20",
                    "authoritative_construction_start",
                ),
                (
                    "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility",
                    "under_construction",
                    "2026-04-21",
                    "authoritative_construction_start",
                ),
                (
                    "curated:trg-spring-cypress-campus:hou2",
                    "under_construction",
                    "2026-07-20",
                    "authoritative_physical_status_update",
                ),
                (
                    "curated:related-digital-cheyenne-campus:phase-1",
                    "under_construction",
                    "2026-07-20",
                    "authoritative_physical_status_update",
                ),
            },
        )
        self.assertEqual(
            set(capacities),
            {
                (
                    "curated:greensquaredc-syd1-norwest-campus:stage-2",
                    "critical_it_mw",
                    "planned",
                    96.0,
                    96.0,
                    96.0,
                    "2025-11-26",
                    None,
                ),
                (
                    "curated:iron-mountain-navi-mumbai-campus:mum-3",
                    "critical_it_mw",
                    "planned",
                    85.0,
                    85.0,
                    85.0,
                    "2026-01-20",
                    None,
                ),
                (
                    "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility",
                    "gross_facility_mw",
                    "planned",
                    300.0,
                    300.0,
                    300.0,
                    "2026-07-20",
                    None,
                ),
                (
                    "curated:trg-spring-cypress-campus",
                    "grid_connection_mw",
                    "planned",
                    30.0,
                    30.0,
                    30.0,
                    "2026-07-20",
                    None,
                ),
                (
                    "curated:trg-spring-cypress-campus:hou2",
                    "grid_connection_mw",
                    "planned",
                    24.0,
                    24.0,
                    24.0,
                    "2026-07-20",
                    None,
                ),
                (
                    "curated:related-digital-cheyenne-campus:phase-1",
                    "critical_it_mw",
                    "planned",
                    88.0,
                    88.0,
                    88.0,
                    "2026-07-20",
                    None,
                ),
            },
        )

        tags_by_key = {
            stable_key: json.loads(tags_json)
            for stable_key, _, tags_json, _, _, _ in snapshots
        }
        self.assertEqual(
            tags_by_key["curated:bell-ai-fabric-sherwood-campus"]["role:utility"],
            "SaskPower",
        )
        self.assertEqual(
            tags_by_key["curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility"][
                "role:customer"
            ],
            "Cerebras; CoreWeave",
        )
        self.assertEqual(
            tags_by_key["curated:trg-spring-cypress-campus"]["role:owner"],
            "TRG Datacenters",
        )
        self.assertEqual(
            tags_by_key["curated:related-digital-cheyenne-campus"]["role:developer"],
            "Related Digital",
        )
        self.assertEqual(
            tags_by_key["curated:related-digital-cheyenne-campus:phase-1"][
                "role:tenant"
            ],
            "CoreWeave",
        )
        for stable_key in (
            "curated:greensquaredc-syd1-norwest-campus",
            "curated:greensquaredc-syd1-norwest-campus:stage-2",
            "curated:iron-mountain-navi-mumbai-campus",
            "curated:iron-mountain-navi-mumbai-campus:mum-3",
            "curated:trg-spring-cypress-campus:hou2",
        ):
            self.assertFalse(
                any(key.startswith("role:") for key in tags_by_key[stable_key])
            )


if __name__ == "__main__":
    unittest.main()
