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
RETRIEVED_AT = "2026-07-20T05:29:25Z"

TOK1_SOURCE = (
    "curated-official-2026-07-20-airtrunk-tok1-east-tokyo-expansion.json"
)
GTPL_SOURCE = (
    "curated-official-2026-07-20-gramercy-techpark-lbom-12-airoli.json"
)
SGP2_SOURCE = (
    "curated-official-2026-07-20-airtrunk-sgp2-singapore-fy25-snapshot.json"
)
JHB2_SOURCE = (
    "curated-official-2026-07-20-airtrunk-jhb2-johor-fy25-snapshot.json"
)
SOURCES = (TOK1_SOURCE, GTPL_SOURCE, SGP2_SOURCE, JHB2_SOURCE)

FY25_KEY = (
    "airtrunk-fy25-climate-nature-risk-report-published-2025-10-23-"
    "captured-2026-07-20"
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    TOK1_SOURCE: {
        "sha256": "1ac18a7d097fe869a9ad6489bdb5ce26cc8e16d9579d506f497368a4f3bcf28b",
        "evidence_count": 3,
        "campus_key": "curated:airtrunk-tok1-east-tokyo-campus",
        "project_key": (
            "curated:airtrunk-tok1-east-tokyo-campus:march-2026-expansion"
        ),
        "project_name": "AirTrunk TOK1 March 2026 Expansion",
        "country": "Japan",
        "address": "Inzai, Chiba, Japan",
        "roles": {"operator": ["AirTrunk"]},
        "status_date": "2026-03-10",
    },
    GTPL_SOURCE: {
        "sha256": "33398c938ab31a27277d33d4c03d5de90f1d19127d0eb1e705641212e817c7dc",
        "evidence_count": 1,
        "campus_key": "curated:gramercy-techpark-airoli-data-centre-campus",
        "project_key": (
            "curated:gramercy-techpark-airoli-data-centre-campus:lbom-12"
        ),
        "project_name": "GTPL LBOM-12",
        "country": "India",
        "address": "Airoli, Navi Mumbai, India",
        "roles": {"developer": ["Gramercy Techpark Private Limited"]},
        "status_date": "2026-03-31",
    },
    SGP2_SOURCE: {
        "sha256": "1343933e14031729e8dc75b52f1bb210becdb752d27e6c26f47267cc6852e8c0",
        "evidence_count": 3,
        "campus_key": "curated:airtrunk-sgp2-singapore-campus",
        "project_key": "curated:airtrunk-sgp2-singapore-campus:development",
        "project_name": "AirTrunk SGP2 Development",
        "country": "Singapore",
        "address": "Loyang, Singapore",
        "roles": {"operator": ["AirTrunk"]},
        "status_date": "2025-06-30",
    },
    JHB2_SOURCE: {
        "sha256": "1d713d6ac099df709e8d2fabc829aabda2cde785b338dd9e5b819fed4d5c31fe",
        "evidence_count": 3,
        "campus_key": "curated:airtrunk-jhb2-iskandar-puteri-campus",
        "project_key": (
            "curated:airtrunk-jhb2-iskandar-puteri-campus:development"
        ),
        "project_name": "AirTrunk JHB2 Development",
        "country": "Malaysia",
        "address": "Iskandar Puteri, Johor, Malaysia",
        "roles": {"operator": ["AirTrunk"]},
        "status_date": "2025-06-30",
    },
}

CAPTURES = {
    "airtrunk-tok1-financing-expansion-2026-03-10-captured-2026-07-20": (
        96508,
        "f3f9f6fe795062b8bf090879644513c440badb834a206a4f401d05180cc893f7",
        537,
        "a79a3e8af62d929eec3a8c80317c9c639f1eeb4c288ac971e824555b9200879b",
        11321,
        "c2bbad9e1d42dfcbf3da483dd051af1eedf2d1167a317f867b86c623611e6075",
    ),
    "airtrunk-tok1-groundbreaking-2025-06-19-captured-2026-07-20": (
        88633,
        "5b8ed41b64183df8a42e01e9a5256d5c08178f38824476b30dff2babe776f007",
        537,
        "a79a3e8af62d929eec3a8c80317c9c639f1eeb4c288ac971e824555b9200879b",
        11198,
        "2bec7c9fae592e2bc51da1a19bc9bd05f5e3041b6833d38b90f287b7e2630187",
    ),
    "airtrunk-tok1-location-current-captured-2026-07-20": (
        91348,
        "c052af257a2896b688448f1c24f85ba809dcb531b21c7fdbcf8182f8db2f104a",
        537,
        "a79a3e8af62d929eec3a8c80317c9c639f1eeb4c288ac971e824555b9200879b",
        10932,
        "5acca54bb42499155db2b1c715c96f74b6ed524fdb6f4370fa7b56132d8f3cc8",
    ),
    "careedge-gramercy-techpark-rating-2026-05-22-captured-2026-07-20": (
        181039,
        "5598113a856a8c45f3a0578b2446db28927615e7f8aa482e60eda7e8fdeb57a7",
        676,
        "0df32a92bcc9e6a3a2245ce44aa570cd962cae43c9a4f5440a3be42ce09ac274",
        24466,
        "a6e631fa41701fcfbab520e5aa1c9bbf8632daffb4f54933b826940c586182c3",
    ),
    FY25_KEY: (
        7940739,
        "9743eb2b741cd3e1abd06c4e4209f29fd0dac432381d4e9ce2ac817762ea82cf",
        594,
        "11ef9a2bdfbe9f90323e693151d82075c710377c0743d1dbadbf048d6c92e3a8",
        11162,
        "4644a55d914cc221fdd4fa5da2dbba82085663e4384758a3b23a382a85c67ce7",
    ),
    "airtrunk-sgp2-green-loan-2025-08-18-captured-2026-07-20": (
        95872,
        "4fe3553009521a248289e0efea31c32ca06ce565790f13f2ee23819a14c0412b",
        538,
        "31ce5e3b15b903b9c0536217852390a6f99e9bbd34d14a9d805464861dc80855",
        11248,
        "97fe843d80e34a5ba7af3e69dcd23d3568920d4247498c1ee81b3b2cfb7edad0",
    ),
    "airtrunk-sgp2-location-current-captured-2026-07-20": (
        88607,
        "a24445caa7f2aaf5d1292060676870dbf67a748d20c89868177191f702b01e45",
        717,
        "31eeae35f5de70ac7a45892e06517918ee4102e98ae190f046f8877f3efe5b00",
        10927,
        "539432252bda392729ef2041fd6b99c4a32797949828aaeff73069df3252a4b1",
    ),
    "airtrunk-jhb2-announcement-2025-02-12-captured-2026-07-20": (
        95725,
        "16b7726a2712e8e35fce6650e89f302de4ca3ccbdaba456a9918451ef0be6dc2",
        751,
        "96319a790a26a2f97bc6f44ea413bfb09ef4a1356ef4372f1d28fcfb2e36ab89",
        11220,
        "50a02134e54f267b58b8ea8ad1ab9ca0c79879b5119c85e434856eb686ee13f7",
    ),
    "airtrunk-jhb2-location-current-captured-2026-07-20": (
        87435,
        "ba4c5b0c38f76390c88ad68769160d4d5830d8cceb5379bca935360a8f1567db",
        716,
        "a1524c69dd3519c0db3815a1c91e18bf4aefa490adb8a38330754afaeb777d27",
        10912,
        "744a5e6413c52d161e9855415c1a9a363a7badb2a93eafeef41528712a9b53ec",
    ),
}


class AirTrunkAndGtplCurrentCuratedTests(unittest.TestCase):
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
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, base, target_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key",
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

    def test_exact_files_are_canonical_hash_pinned_and_source_scoped(self) -> None:
        self.assertEqual(len(SOURCES), 4)
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

        self.assertEqual(
            self._load(SGP2_SOURCE)["evidence"][0],
            self._load(JHB2_SOURCE)["evidence"][0],
        )

    def test_exact_capture_provenance_is_byte_bound(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            for item in self._load(name)["evidence"]:
                previous = evidence.setdefault(item["key"], item)
                self.assertEqual(previous, item)

        self.assertEqual(set(evidence), set(CAPTURES))
        self.assertEqual(len(evidence), 9)
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                body_bytes, body_hash, header_bytes, header_hash, facts_bytes, facts_hash = expected
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
                self.assertIn("supplied no Authorization", metadata["request_credentials_guardrail"])
                self.assertIn("satellite imagery", metadata["imagery_guardrail"])

    def test_exact_entities_status_dates_roles_and_zero_capacity_leakage(self) -> None:
        stable_keys: set[str] = set()
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], expected["campus_key"])
                self.assertEqual(project["stable_key"], expected["project_key"])
                self.assertEqual(project["name"], expected["project_name"])
                stable_keys.update((campus["stable_key"], project["stable_key"]))
                for entity in (campus, project):
                    self.assertEqual(entity["country"], expected["country"])
                    self.assertEqual(entity["address"], expected["address"])
                    self.assertEqual(entity["roles"], expected["roles"])
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": "under_construction",
                            "evidence_key": document["lifecycle"][0]["evidence_key"],
                            "as_of_date": expected["status_date"],
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(document["capacities"], [])
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])

        self.assertEqual(len(stable_keys), 8)
        self.assertFalse(any("bom1" in key for key in stable_keys))
        self.assertFalse(any("syd3" in key for key in stable_keys))
        self.assertFalse(any("hkg2" in key or "osk1" in key for key in stable_keys))

    def test_open_bounds_aliases_freshness_pue_and_exclusions_are_explicit(self) -> None:
        tok1 = self._load(TOK1_SOURCE)
        tok1_current = tok1["evidence"][0]["metadata"]
        tok1_groundbreaking = tok1["evidence"][1]["metadata"]
        self.assertEqual(tok1_current["reported_open_bound_it_load_mw"], "over 100")
        self.assertEqual(tok1_current["reported_open_bound_campus_scale_mw"], "over 300")
        self.assertIn("cannot preserve open bounds", tok1_current["capacity_guardrail"])
        self.assertIn("may overlap", tok1_current["phase_overlap_guardrail"])
        self.assertEqual(tok1_groundbreaking["reported_open_bound_phase_mw"], "40+")
        self.assertIn("never added", tok1_groundbreaking["phase_overlap_guardrail"])

        gtpl = self._load(GTPL_SOURCE)
        gtpl_metadata = gtpl["evidence"][0]["metadata"]
        self.assertEqual(gtpl_metadata["reported_capacity_text"], "approximately 30.5 MW")
        self.assertIn("dimensionally untyped", gtpl_metadata["capacity_guardrail"])
        self.assertIn("not merged", gtpl_metadata["identity_nonmerge_guardrail"])
        self.assertIn("AirTrunk BOM1", gtpl_metadata["identity_nonmerge_guardrail"])
        self.assertIn("financial progress", gtpl_metadata["financial_progress_guardrail"])
        self.assertEqual(gtpl["campus"]["roles"], {"developer": ["Gramercy Techpark Private Limited"]})

        sgp2 = self._load(SGP2_SOURCE)
        jhb2 = self._load(JHB2_SOURCE)
        for document in (sgp2, jhb2):
            report_metadata = document["evidence"][0]["metadata"]
            self.assertEqual(report_metadata["reporting_period_end"], "2025-06-30")
            self.assertIn("historical", report_metadata["freshness_guardrail"])
            self.assertIn("never be presented", report_metadata["freshness_guardrail"])
            self.assertIn("no SYD3 record", report_metadata["syd3_scope"])

        sgp2_release = sgp2["evidence"][1]["metadata"]
        self.assertEqual(sgp2_release["reported_open_bound_capacity_mw"], "70+")
        self.assertEqual(sgp2_release["reported_design_pue"], 1.2)
        self.assertIn("no PUE row", sgp2_release["pue_guardrail"])

        jhb2_release = jhb2["evidence"][1]["metadata"]
        jhb2_location = jhb2["evidence"][2]["metadata"]
        self.assertEqual(jhb2_release["reported_open_bound_capacity_mw"], "over 270")
        self.assertEqual(jhb2_release["reported_announcement_design_pue"], 1.25)
        self.assertEqual(jhb2_location["reported_current_page_design_pue"], 1.37)
        self.assertIn("conflict", jhb2_release["pue_conflict_guardrail"])
        self.assertIn("PUE row", jhb2_release["pue_conflict_guardrail"])

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
                        "capacity_estimates": 0,
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
        self.assertEqual(len(entities), 8)
        self.assertEqual(len(evidence), 9)
        self.assertEqual(len(lifecycle), 4)
        self.assertEqual(len(snapshots), 8)
        self.assertEqual(capacities, ())
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        for row in snapshots:
            tags = json.loads(row[2])
            self.assertTrue(
                tags.get("role:operator") == "AirTrunk"
                or tags.get("role:developer") == "Gramercy Techpark Private Limited"
            )
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
