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
RETRIEVED_AT = "2026-07-20T04:22:16Z"
SEC_KEY = (
    "iron-mountain-q1-2026-supplemental-development-table-sec-"
    "captured-2026-07-20"
)
SEC_BODY_SHA256 = (
    "c671db65dca07449425fbd846dd33528d9a32f14206a34f499e59851cde1fb29"
)

AMS_SOURCE = "curated-official-2026-07-20-iron-mountain-ams-2-amsterdam.json"
AZP_SOURCE = "curated-official-2026-07-20-iron-mountain-azp-3-phase-3.json"
LON_SOURCE = "curated-official-2026-07-20-iron-mountain-lon-3-london.json"
MAD_SOURCE = (
    "curated-official-2026-07-20-iron-mountain-mad-2-mad-3-madrid.json"
)
VA1_SOURCE = "curated-official-2026-07-20-iron-mountain-va-9-phase-1.json"
VA2_SOURCE = "curated-official-2026-07-20-iron-mountain-va-9-phase-2.json"
MIA_SOURCE = "curated-official-2026-07-20-iron-mountain-mia-1-miami.json"
SOURCES = (
    AMS_SOURCE,
    AZP_SOURCE,
    LON_SOURCE,
    MAD_SOURCE,
    VA1_SOURCE,
    VA2_SOURCE,
    MIA_SOURCE,
)

AMS_CAMPUS = "curated:iron-mountain-amsterdam-data-center-campus"
AZP_CAMPUS = "curated:iron-mountain-azp-3-phoenix-data-center"
LON_CAMPUS = "curated:iron-mountain-lon-3-london-data-center"
MAD_CAMPUS = "curated:iron-mountain-madrid-data-center-campus"
VA_CAMPUS = "curated:iron-mountain-va-9-northern-virginia-data-center"
MIA_CAMPUS = "curated:iron-mountain-mia-1-miami-data-center"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    AMS_SOURCE: {
        "sha256": "b28d58d7b400794b570b9fbf91be3305e669ec019c0b359dc46027c5d1f755aa",
        "evidence_count": 3,
        "campus_key": AMS_CAMPUS,
        "project_key": f"{AMS_CAMPUS}:ams-2-10mw-expansion",
        "project_name": "Iron Mountain AMS-2 10 MW Expansion",
        "country": "Netherlands",
        "address": "J.W. Lucasweg 35, 2031 BE Haarlem, Netherlands",
        "mw": 10,
        "model_evidence": (
            "iron-mountain-amsterdam-location-current-browser-captured-2026-07-20"
        ),
        "model_date": "2026-07-20",
    },
    AZP_SOURCE: {
        "sha256": "048498eac0ec9d135b597aa88376ef00dda67e3a6c823ed1e6d2f80c5a9f74df",
        "evidence_count": 2,
        "campus_key": AZP_CAMPUS,
        "project_key": f"{AZP_CAMPUS}:phase-3",
        "project_name": "Iron Mountain AZP-3 Phase 3",
        "country": "United States",
        "address": "Phoenix, Arizona, United States",
        "mw": 8,
        "model_evidence": (
            "iron-mountain-phoenix-location-current-browser-captured-2026-07-20"
        ),
        "model_date": "2026-07-20",
    },
    LON_SOURCE: {
        "sha256": "6045d0e0368b48192b6030ecd1d54f16566e436d506d04fc799653c52d267aa1",
        "evidence_count": 3,
        "campus_key": LON_CAMPUS,
        "project_key": f"{LON_CAMPUS}:25mw-build",
        "project_name": "Iron Mountain LON-3 25 MW Build",
        "country": "United Kingdom",
        "address": "111 Buckingham Avenue, Slough SL1 4PF, United Kingdom",
        "mw": 25,
        "model_evidence": (
            "iron-mountain-lon-3-guide-2025-11-20-browser-captured-2026-07-20"
        ),
        "model_date": "2025-11-20",
    },
    MAD_SOURCE: {
        "sha256": "c03c64835393eeb95b9fd07378b97245bbb028ae48620fe96c9da04f90202741",
        "evidence_count": 2,
        "campus_key": MAD_CAMPUS,
        "project_key": f"{MAD_CAMPUS}:mad-2-mad-3-20mw-development",
        "project_name": "Iron Mountain MAD-2 and MAD-3 20 MW Development",
        "country": "Spain",
        "address": "Calle Mar Egeo, San Fernando de Henares, Madrid, Spain",
        "mw": 20,
        "model_evidence": (
            "iron-mountain-madrid-campus-guide-2026-06-26-"
            "browser-captured-2026-07-20"
        ),
        "model_date": "2026-06-26",
    },
    VA1_SOURCE: {
        "sha256": "3b55e46de0f279ee4bb983ec40812747fcef96f2b0509acb4dd96583b1938b35",
        "evidence_count": 3,
        "campus_key": VA_CAMPUS,
        "project_key": f"{VA_CAMPUS}:phase-1",
        "project_name": "Iron Mountain VA-9 Phase 1",
        "country": "United States",
        "address": (
            "11530 Elevate Drive, Suite 100, Manassas, VA 20109, United States"
        ),
        "mw": 14,
        "model_evidence": (
            "iron-mountain-va-9-guide-2025-10-07-browser-captured-2026-07-20"
        ),
        "model_date": "2025-10-07",
    },
    VA2_SOURCE: {
        "sha256": "59575a1b574b58acbf6f22e9a733e376d39573db24fa8d49af8140e83415e59d",
        "evidence_count": 3,
        "campus_key": VA_CAMPUS,
        "project_key": f"{VA_CAMPUS}:phase-2",
        "project_name": "Iron Mountain VA-9 Phase 2",
        "country": "United States",
        "address": (
            "11530 Elevate Drive, Suite 100, Manassas, VA 20109, United States"
        ),
        "mw": 14,
        "model_evidence": (
            "iron-mountain-va-9-guide-2025-10-07-browser-captured-2026-07-20"
        ),
        "model_date": "2025-10-07",
    },
    MIA_SOURCE: {
        "sha256": "5f17030fdb0b929ef57faf332175664330f598558ab059f593400eea80aa7c48",
        "evidence_count": 2,
        "campus_key": MIA_CAMPUS,
        "project_key": f"{MIA_CAMPUS}:build",
        "project_name": "Iron Mountain MIA-1 Build",
        "country": "United States",
        "address": "2925 NW 120th Terrace, Miami, FL 33167, United States",
        "mw": 16,
        "model_evidence": (
            "iron-mountain-miami-location-current-browser-captured-2026-07-20"
        ),
        "model_date": "2026-07-20",
    },
}

CURRENT_CAPTURES = {
    "iron-mountain-ams-2-rendering-2026-06-12-browser-captured-2026-07-20": (
        149693,
        "cf3624ab97b5d5e8b372655cecd2f9c98df3406fa2a2678eea8d5ecba25391de",
        1082,
        "f0735ecf035f6539823b47ee3181f1189b15be5af73d2cefa6a72895de062938",
    ),
    "iron-mountain-amsterdam-location-current-browser-captured-2026-07-20": (
        408901,
        "62be35adea69fb7cddf87a9a1a07734afac9898e3e9a76416d8a64b598f7b392",
        983,
        "e134a2ee6cca189bc2d38b831546fb9be4300e027a86f338ababb33eea0fe531",
    ),
    "iron-mountain-phoenix-location-current-browser-captured-2026-07-20": (
        401879,
        "74cce7a656a2e9a556cffe855238e50dc54de5e5bfa8fbce3dd97297b9b856db",
        982,
        "6b621bcab84959f06b704676e41d054d715bfa755d4cd6e4452e402236bc2b59",
    ),
    "iron-mountain-lon-3-guide-2025-11-20-browser-captured-2026-07-20": (
        160357,
        "68ccf18eb36d29e65aa10b69654563085e2c1ae1d6cc87e1e9f023e65ddec118",
        996,
        "b35a8001823732b58be91e5790e0a79359df7710ddbc657e1f2062b7f91557d9",
    ),
    "iron-mountain-london-location-current-browser-captured-2026-07-20": (
        386231,
        "852d4a4ef069ecbcbe9fc1102b2c74284cea9c9d514483ebec922ac3658cffbf",
        980,
        "66eafbbd69c36bf5891604c49643b44edae6cec59370170065e6b59ff27700da",
    ),
    "iron-mountain-madrid-campus-guide-2026-06-26-browser-captured-2026-07-20": (
        158838,
        "4df0e1d5631bc98002556d3bd30a53c310e3ea869c0349c2c022e3cba9262e65",
        1016,
        "1aaf11c4dd78f1a44f85c3d9f05c78e83712ac80a7d58373247b503c581ed497",
    ),
    "iron-mountain-va-9-guide-2025-10-07-browser-captured-2026-07-20": (
        144825,
        "65b4d27dcc8e78cf5e5900958e72162028273d8e6cdbac1e98057075c144c44a",
        1016,
        "fa726b834fcfe0683c21cde154a64b97e7ec36578d558d69ff20ea46dfe56479",
    ),
    "iron-mountain-virginia-location-current-browser-captured-2026-07-20": (
        446591,
        "d81244ec86dce333f61f91b5fbeee062dcd904cad602dc7b355d9a5f2a178582",
        984,
        "d61041f1932d745de4c98bd277198ef023386c31f038ec9c12eed2589fb56287",
    ),
    "iron-mountain-miami-location-current-browser-captured-2026-07-20": (
        392599,
        "4cd12e16ff73ff3d23b33d70611042821c16d8cab5bba5ac1f2017bbee9cf3d4",
        978,
        "64ad068e0c02b8035b7a5205d7b6f197c122ac3b76518c54d703c8f3abf6742e",
    ),
}


class IronMountainQ12026CuratedTests(unittest.TestCase):
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
        self.assertEqual(len(SOURCES), 7)
        raw_sec_evidence: list[bytes] = []
        documents: dict[str, dict[str, Any]] = {}
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
                self.assertEqual(document["evidence"][0]["key"], SEC_KEY)
                documents[name] = document
                raw_sec_evidence.append(
                    json.dumps(
                        document["evidence"][0],
                        indent=2,
                        ensure_ascii=False,
                    ).encode()
                )

        self.assertTrue(all(raw == raw_sec_evidence[0] for raw in raw_sec_evidence))
        self.assertEqual(documents[VA1_SOURCE]["evidence"], documents[VA2_SOURCE]["evidence"])

    def test_exact_capture_provenance_and_same_publisher_nonindependence(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            for item in self._load(name)["evidence"]:
                previous = evidence.setdefault(item["key"], item)
                self.assertEqual(previous, item)

        self.assertEqual(len(evidence), 10)
        sec = evidence[SEC_KEY]
        self.assertEqual(sec["content_hash"], SEC_BODY_SHA256)
        self.assertEqual(sec["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(sec["published_at"], "2026-04-30")
        self.assertEqual(sec["metadata"]["development_table_as_of_date"], "2026-03-31")
        self.assertIn("72224-byte", sec["metadata"]["content_hash_scope"])
        self.assertIn("662-byte", sec["metadata"]["capture_headers_scope"])
        self.assertEqual(
            sec["metadata"]["capture_headers_sha256"],
            "e0ac4b1e0494865c33f2904411d41ad315f24cf9e8200b126da48b3e1c3666a9",
        )
        self.assertIn("15119-byte", sec["metadata"]["capture_curl_writeout_scope"])
        self.assertEqual(
            sec["metadata"]["capture_curl_writeout_sha256"],
            "c83283adf1d3289157c0c27fd2d221442933ff41f1841e953dd64cc012026458",
        )
        self.assertEqual(sec["metadata"]["selected_rows_total_mw"], 107)
        self.assertEqual(len(sec["metadata"]["selected_rows_as_reported"]), 7)

        for key, expected in CURRENT_CAPTURES.items():
            with self.subTest(evidence=key):
                body_bytes, body_hash, metadata_bytes, metadata_hash = expected
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["content_hash"], body_hash)
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["publisher"], "Iron Mountain Data Centers")
                self.assertIn(
                    f"{body_bytes}-byte",
                    metadata["content_hash_scope"],
                )
                self.assertIn(
                    f"{metadata_bytes}-byte",
                    metadata["capture_cdp_metadata_scope"],
                )
                self.assertEqual(
                    metadata["capture_cdp_metadata_sha256"],
                    metadata_hash,
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
                self.assertEqual(metadata["content_encoding_as_received"], "br")
                self.assertFalse(metadata["cdp_body_base64_encoded"])
                self.assertFalse(metadata["independent_factual_corroboration"])
                self.assertIn(
                    "not counted as independent",
                    metadata["same_publisher_guardrail"],
                )
                self.assertIn("browser challenge", metadata["retrieval_method"])
                self.assertIn(
                    "satellite imagery",
                    metadata["imagery_guardrail"],
                )
                self.assertIn(
                    "do not contribute",
                    metadata["imagery_guardrail"],
                )

        self.assertFalse(sec["metadata"]["independent_factual_corroboration"])

    def test_exact_seven_components_total_107_mw_without_dimension_leakage(self) -> None:
        project_keys: list[str] = []
        campus_keys: list[str] = []
        capacities: list[float] = []
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], expected["campus_key"])
                self.assertEqual(project["stable_key"], expected["project_key"])
                self.assertEqual(project["name"], expected["project_name"])
                project_keys.append(project["stable_key"])
                campus_keys.append(campus["stable_key"])

                for entity in (campus, project):
                    self.assertEqual(entity["country"], expected["country"])
                    self.assertEqual(entity["address"], expected["address"])
                    self.assertEqual(
                        entity["roles"],
                        {"operator": ["Iron Mountain Data Centers"]},
                    )
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["method"], "authoritative_locality")

                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": "under_construction",
                            "evidence_key": SEC_KEY,
                            "as_of_date": "2026-03-31",
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(
                    document["operating_models"],
                    [
                        {
                            "entity": "project",
                            "value": "colocation",
                            "evidence_key": expected["model_evidence"],
                            "as_of_date": expected["model_date"],
                            "method": "company_disclosure",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(document["workloads"], [])
                self.assertEqual(len(document["capacities"]), 1)
                capacity = document["capacities"][0]
                self.assertEqual(capacity["entity"], "project")
                self.assertEqual(capacity["metric"], "critical_it_mw")
                self.assertEqual(capacity["stage"], "planned")
                self.assertEqual(capacity["unit"], "MW")
                self.assertEqual(
                    (capacity["low"], capacity["base"], capacity["high"]),
                    (expected["mw"], expected["mw"], expected["mw"]),
                )
                self.assertEqual(capacity["evidence_key"], SEC_KEY)
                self.assertEqual(capacity["as_of_date"], "2026-03-31")
                self.assertIsNone(capacity["target_date"])
                capacities.append(capacity["base"])

        self.assertEqual(capacities, [10, 8, 25, 20, 14, 14, 16])
        self.assertEqual(sum(capacities), 107)
        self.assertEqual(len(set(project_keys)), 7)
        self.assertEqual(len(set(campus_keys)), 6)
        self.assertEqual(campus_keys.count(VA_CAMPUS), 2)
        self.assertTrue(set(project_keys).isdisjoint(set(campus_keys)))

    def test_alias_schedule_and_exclusion_guardrails_are_explicit(self) -> None:
        ams = self._load(AMS_SOURCE)
        ams_metadata = ams["evidence"][1]["metadata"]
        alias = ams_metadata["alias_resolution"]
        self.assertEqual(alias["current_canonical_identity"], "AMS-2 10 MW expansion")
        self.assertEqual(alias["historical_sec_identity"], "AMS-1 Phase 4")
        self.assertIn("held-development", alias["historical_name_conflict"])
        self.assertIn("Only the 10 MW", ams_metadata["nonadditive_guardrail"])

        madrid = self._load(MAD_SOURCE)
        madrid_metadata = madrid["evidence"][1]["metadata"]
        self.assertEqual(
            madrid_metadata["identity_alias_resolution"]["current_canonical_identity"],
            "MAD-2 and MAD-3 20 MW development",
        )
        self.assertEqual(
            madrid_metadata["identity_alias_resolution"]["historical_sec_identity"],
            "Madrid MAD-1 20 MW",
        )
        self.assertEqual(
            madrid_metadata["schedule_conflict"],
            {
                "sec_expected_completion": "Q4 2026",
                "current_summary_completion": "Q1 2027",
                "detailed_dc02_completion": "Q4 2026",
                "detailed_dc03_completion": "Q2 2027",
            },
        )
        self.assertIn("not split", madrid_metadata["aggregate_guardrail"])

        va1 = self._load(VA1_SOURCE)
        va2 = self._load(VA2_SOURCE)
        va_metadata = va1["evidence"][1]["metadata"]
        self.assertEqual(va1["evidence"], va2["evidence"])
        self.assertIn("two distinct 14 MW", va_metadata["phase_component_guardrail"])
        self.assertIn("no additional 28 MW", va_metadata["phase_component_guardrail"])
        self.assertIn("150 MW", va_metadata["manassas_150_mw_guardrail"])
        self.assertTrue(
            all(capacity["target_date"] is None for capacity in va1["capacities"])
        )
        self.assertTrue(
            all(capacity["target_date"] is None for capacity in va2["capacities"])
        )

        mia_metadata = self._load(MIA_SOURCE)["evidence"][1]["metadata"]
        self.assertEqual(mia_metadata["reported_redundant_operational_power_mva"], 26)
        self.assertIn("not MW", mia_metadata["mva_guardrail"])
        self.assertIn("not converted", mia_metadata["mva_guardrail"])

        sec_metadata = ams["evidence"][0]["metadata"]
        self.assertIn("CHI-1", sec_metadata["planned_not_commenced_exclusion"])
        self.assertIn("No Chicago", sec_metadata["chicago_guardrail"])
        self.assertIn("No India", sec_metadata["india_guardrail"])
        self.assertIn("aggregate-plus-component", sec_metadata["aggregate_component_guardrail"])

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
                    self.assertEqual(
                        result.evidence_created,
                        expected["evidence_count"],
                    )
                    self.assertEqual(validate_database(connection), [])
                    expected_counts = {
                        "evidence": expected["evidence_count"],
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 1,
                        "workload_observations": 0,
                        "capacity_estimates": 1,
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
        self.assertEqual(len(entities), 13)
        self.assertEqual(len(evidence), 10)
        self.assertEqual(len(lifecycle), 7)
        self.assertEqual(len(snapshots), 13)
        self.assertEqual(len(capacities), 7)
        self.assertEqual(len(models), 7)
        self.assertEqual(workloads, ())
        self.assertEqual(sum(row[3] for row in capacities), 107)
        self.assertEqual(
            {row[0] for row in entities if row[0] == "project"},
            {"project"},
        )
        self.assertEqual(
            [row[1] for row in entities].count(VA_CAMPUS),
            1,
        )
        for row in snapshots:
            tags = json.loads(row[2])
            self.assertEqual(tags["role:operator"], "Iron Mountain Data Centers")
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
