from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
BATCH_RETRIEVED_AT = "2026-07-19T17:42:54Z"
LONDON_SOURCE = "curated-official-2026-07-19-colt-london4-hayes.json"
LONDON_SOURCE_SHA256 = (
    "44a4569bed0c12103d726d0e73f8a05078f4528c74c7f032dfc5feaa9ea0b05b"
)
SOURCES = {
    "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json": {
        "sha256": "322e3929b2542204ed2f543fd9462f9f2cf9cd2afeb76b9448ece38a82295c9d",
        "country": "Germany",
        "address": "Sossenheim, Frankfurt, Germany",
        "campus_key": "curated:colt-frankfurt3-sossenheim-campus",
        "campus_name": "Colt Frankfurt 3 Sossenheim Campus",
        "project_key": (
            "curated:colt-frankfurt3-sossenheim-campus:"
            "frankfurt3-current-facility-build"
        ),
        "project_name": "Colt Frankfurt 3 Current Facility Build",
        "capacity_mw": 32.4,
    },
    "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json": {
        "sha256": "aac09ee130b7d721f0605d8ea0f9916955baf6666f692eb397f7fcb6dc6737ff",
        "country": "France",
        "address": "Villebon-sur-Yvette, France",
        "campus_key": "curated:colt-villebon-sur-yvette-campus",
        "campus_name": "Colt Villebon-sur-Yvette Campus",
        "project_key": (
            "curated:colt-villebon-sur-yvette-campus:"
            "paris2-current-facility-build"
        ),
        "project_name": "Colt Paris 2 Current Facility Build",
        "capacity_mw": 39.6,
    },
}
CAPTURES = {
    "07701aa16437bf96df1974c94e510db29bc82b99fbc96e4a8af47ebcf5ea2d4c": {
        "bytes": 287886,
        "request_start": "2026-07-19T17:42:53Z",
        "http_date": "2026-07-19T17:42:53Z",
        "last_modified": "2026-07-19T17:24:10Z",
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://www.coltdatacentres.net/en-GB/our-locations/"
            "data-centre-locations-europe/frankfurt-three/timeline"
        ),
    },
    "14f8f9373d8662b145bf72c62f4f8d2410ba9f8a9e451b0c22951252d81efd20": {
        "bytes": 249856,
        "request_start": "2026-07-19T17:42:53Z",
        "http_date": "2026-07-19T17:42:53Z",
        "last_modified": "2026-07-19T17:24:11Z",
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://www.coltdatacentres.net/en-GB/our-locations/"
            "data-centre-locations-europe/paris-2"
        ),
    },
    "5408bd489729ba167e40678b5952ba827720f29edb239e7dbbc2fde4d40f5348": {
        "bytes": 258507,
        "request_start": "2026-07-19T17:42:52Z",
        "http_date": "2026-07-19T17:42:53Z",
        "last_modified": "2026-07-19T17:24:10Z",
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://www.coltdatacentres.net/en-GB/our-locations/"
            "data-centre-locations-europe/frankfurt-three"
        ),
    },
    "d79b5975647667fd9dc234707acb6cd4c36c72ada03f29f001866661fa296d52": {
        "bytes": 27720035,
        "request_start": "2026-07-19T17:42:53Z",
        "http_date": "2026-07-19T17:42:53Z",
        "last_modified": "2026-06-25T08:03:04Z",
        "content_type": "application/pdf",
        "url": (
            "https://www.coltdatacentres.net/-/media/Files/guides/"
            "colt-dcs-sustainability-report-cy2025.pdf"
        ),
    },
}


class ColtNextTrancheCandidateTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_candidate_guardrails(
        self, name: str, document: dict[str, Any]
    ) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("locality must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("locality method must remain authoritative_locality")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain authoritative locality only")
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")

        if (
            document["campus"]["stable_key"] != expected["campus_key"]
            or document["campus"]["name"] != expected["campus_name"]
        ):
            raise AssertionError("one canonical campus must remain")
        if (
            document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("one canonical current facility project must remain")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        if lifecycle[0]["value"] != "under_construction":
            raise AssertionError("lifecycle must remain generic under_construction")
        if lifecycle[0]["method"] != "authoritative_physical_status_update":
            raise AssertionError("lifecycle method must remain authoritative")

        if document["operating_models"] or document["workloads"]:
            raise AssertionError("classifications must remain empty")

        capacities = document["capacities"]
        if len(capacities) != 1:
            raise AssertionError("one planned critical-IT capacity row must remain")
        capacity = capacities[0]
        if (
            capacity["entity"] != "project"
            or capacity["metric"] != "critical_it_mw"
            or capacity["stage"] != "planned"
            or capacity["unit"] != "MW"
            or capacity["method"] != "reported"
        ):
            raise AssertionError("capacity must remain planned reported critical IT")
        capacity_values = (capacity["low"], capacity["base"], capacity["high"])
        if capacity_values != (expected["capacity_mw"],) * 3:
            raise AssertionError("exact planned capacity must remain unchanged")
        if capacity["target_date"] is not None:
            raise AssertionError("target date must remain null")

        evidence_by_key = {row["key"]: row for row in document["evidence"]}
        if "frankfurt3" in name:
            location = evidence_by_key[
                "colt-frankfurt3-location-page-captured-2026-07-19"
            ]["metadata"]
            timeline = evidence_by_key[
                "colt-frankfurt3-construction-timeline-captured-2026-07-19"
            ]["metadata"]
            if "not assigned to phase one" not in location["phase_scope_guardrail"]:
                raise AssertionError("Frankfurt phase-one allocation guardrail must remain")
            if "stale" not in timeline["completion_forecast_guardrail"]:
                raise AssertionError("Frankfurt stale forecast must remain excluded")
            if (
                timeline["pue_as_reported"] != 1.35
                or "not imported" not in timeline["pue_guardrail"]
            ):
                raise AssertionError("Frankfurt PUE must remain excluded metadata")
        else:
            location_evidence = evidence_by_key[
                "colt-paris2-location-page-captured-2026-07-19"
            ]
            location = location_evidence["metadata"]
            report = evidence_by_key[
                "colt-dcs-cy2025-sustainability-report-captured-2026-07-19"
            ]["metadata"]
            if (
                "construction has begun" not in location_evidence["excerpt"]
                or "currently under construction" in location_evidence["excerpt"]
                or not all(
                    phrase in location["status_scope"]
                    for phrase in (
                        "has begun construction",
                        "being developed",
                        "once fully operational",
                    )
                )
            ):
                raise AssertionError("Paris status wording must remain source-scoped")
            if (
                "London 4" not in location["related_card_guardrail"]
                or "does not describe Paris 2" not in location["related_card_guardrail"]
            ):
                raise AssertionError("London 4 card must remain excluded")
            if (
                location["rounded_capacity_as_reported_mw"] != 40
                or report["capacity_as_reported_mw"] != 39.6
            ):
                raise AssertionError("Paris precision guardrail must retain 40 versus 39.6")
            if (
                report["pue_as_reported"] != 1.27
                or report["pue_semantics_as_reported"]
                != "design target; annualised"
                or "not imported" not in report["pue_guardrail"]
            ):
                raise AssertionError("Paris PUE must remain excluded typed metadata")
            if (
                "conflict" not in location["cooling_conflict_guardrail"]
                or "conflict" not in report["cooling_conflict_guardrail"]
            ):
                raise AssertionError("Paris cooling conflict must remain excluded")
            if (
                report["rooftop_solar_area_as_reported_square_metres"] != 1096
                or "does not establish rated power" not in report["rooftop_solar_guardrail"]
                or "measured generation" not in report["rooftop_solar_guardrail"]
                or "current facility load" not in report["rooftop_solar_guardrail"]
                or "rooftop-solar" in report["operation_guardrail"]
            ):
                raise AssertionError("installed solar must remain guarded metadata")

    def test_exact_candidates_import_offline_with_narrow_semantics(self) -> None:
        documents: dict[str, dict[str, Any]] = {}
        seen_captures: set[str] = set()

        london_path = ROOT / "sources" / LONDON_SOURCE
        self.assertEqual(
            hashlib.sha256(london_path.read_bytes()).hexdigest(),
            LONDON_SOURCE_SHA256,
        )
        v13_definition = (ROOT / "sources" / "open-seed-2026-07-19-v13.json").read_text(
            encoding="utf-8"
        )
        for name in SOURCES:
            self.assertNotIn(name, v13_definition)

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected in sorted(SOURCES.items()):
                        source_path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(source_path.read_bytes()).hexdigest(),
                            expected["sha256"],
                        )
                        document = self._load(name)
                        documents[name] = document
                        self._assert_candidate_guardrails(name, document)
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {BATCH_RETRIEVED_AT},
                        )

                        for evidence in document["evidence"]:
                            capture = CAPTURES[evidence["content_hash"]]
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(
                                str(capture["bytes"]), metadata["content_hash_scope"]
                            )
                            self.assertEqual(
                                metadata["request_start_utc"], capture["request_start"]
                            )
                            self.assertEqual(
                                metadata["response_http_date"], capture["http_date"]
                            )
                            self.assertEqual(
                                metadata["http_last_modified_at"],
                                capture["last_modified"],
                            )
                            self.assertEqual(
                                metadata["content_type"], capture["content_type"]
                            )
                            self.assertEqual(evidence["source_url"], capture["url"])
                            self.assertEqual(metadata["requested_url"], capture["url"])
                            self.assertEqual(metadata["effective_url"], capture["url"])
                            self.assertEqual(metadata["canonical_url"], capture["url"])
                            self.assertEqual(metadata["redirect_count"], 0)
                            seen_captures.add(evidence["content_hash"])

                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=BATCH_RETRIEVED_AT,
                        )

                self.assertEqual(seen_captures, set(CAPTURES))
                paris_report = next(
                    row
                    for row in documents[
                        "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json"
                    ]["evidence"]
                    if row["key"]
                    == "colt-dcs-cy2025-sustainability-report-captured-2026-07-19"
                )
                self.assertIsNone(paris_report["published_at"])
                self.assertEqual(
                    paris_report["metadata"]["http_content_length_bytes"], 27720035
                )
                self.assertEqual(
                    paris_report["metadata"]["claim_location"],
                    "Report page 13, Paris 2, France case study",
                )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT project_entity.stable_key,
                               campus_entity.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities AS project_entity
                          ON project_entity.id = lifecycle_observations.entity_id
                        JOIN projects ON projects.entity_id = project_entity.id
                        JOIN entities AS campus_entity
                          ON campus_entity.id = projects.target_entity_id
                        ORDER BY project_entity.stable_key
                        """
                    )],
                    [
                        (
                            SOURCES[
                                "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json"
                            ]["project_key"],
                            SOURCES[
                                "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json"
                            ]["campus_key"],
                            "under_construction",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key, capacity_estimates.metric,
                               capacity_estimates.stage, capacity_estimates.low,
                               capacity_estimates.base, capacity_estimates.high,
                               capacity_estimates.unit, capacity_estimates.target_date
                        FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            SOURCES[
                                "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json"
                            ]["project_key"],
                            "critical_it_mw",
                            "planned",
                            32.4,
                            32.4,
                            32.4,
                            "MW",
                            None,
                        ),
                        (
                            SOURCES[
                                "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json"
                            ]["project_key"],
                            "critical_it_mw",
                            "planned",
                            39.6,
                            39.6,
                            39.6,
                            "MW",
                            None,
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates WHERE metric = 'pue'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL "
                        "OR longitude IS NOT NULL OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
                    4,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 4
                )
                self.assertEqual(
                    {row[0] for row in connection.execute(
                        "SELECT content_hash FROM evidence"
                    )},
                    set(CAPTURES),
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "WHERE status != 'under_construction'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_candidate_guardrails(self) -> None:
        frankfurt_name = (
            "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json"
        )
        paris_name = (
            "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json"
        )
        frankfurt = self._load(frankfurt_name)
        paris = self._load(paris_name)
        mutations: list[tuple[str, dict[str, Any], str]] = []

        mutated = copy.deepcopy(frankfurt)
        mutated["project"]["roles"] = {"tenant": ["Unverified Tenant"]}
        mutations.append((frankfurt_name, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(paris)
        mutated["campus"]["coordinates"] = {"latitude": 48.7, "longitude": 2.2}
        mutations.append((paris_name, mutated, "locality must remain ungeocoded"))

        mutated = copy.deepcopy(paris)
        mutated["campus"]["stable_key"] = (
            "curated:colt-paris2-villebon-sur-yvette-campus"
        )
        mutations.append((paris_name, mutated, "one canonical campus must remain"))

        mutated = copy.deepcopy(frankfurt)
        mutated["project"]["stable_key"] += ":phase-one"
        mutations.append(
            (frankfurt_name, mutated, "one canonical current facility project")
        )

        mutated = copy.deepcopy(paris)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append((paris_name, mutated, "generic under_construction"))

        mutated = copy.deepcopy(paris)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": "colt-paris2-location-page-captured-2026-07-19",
                "as_of_date": "2026-07-19",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append((paris_name, mutated, "classifications must remain empty"))

        mutated = copy.deepcopy(frankfurt)
        mutated["capacities"][0]["base"] = 16.2
        mutations.append((frankfurt_name, mutated, "exact planned capacity"))

        mutated = copy.deepcopy(paris)
        mutated["capacities"][0]["low"] = 40
        mutated["capacities"][0]["base"] = 40
        mutated["capacities"][0]["high"] = 40
        mutations.append((paris_name, mutated, "exact planned capacity"))

        mutated = copy.deepcopy(paris)
        pue_row = copy.deepcopy(mutated["capacities"][0])
        pue_row.update(
            {
                "metric": "pue",
                "unit": "ratio",
                "low": 1.27,
                "base": 1.27,
                "high": 1.27,
            }
        )
        mutated["capacities"].append(pue_row)
        mutations.append((paris_name, mutated, "one planned critical-IT capacity row"))

        mutated = copy.deepcopy(frankfurt)
        mutated["capacities"][0]["target_date"] = "2025-12-31"
        mutations.append((frankfurt_name, mutated, "target date must remain null"))

        mutated = copy.deepcopy(paris)
        paris_evidence = {row["key"]: row for row in mutated["evidence"]}
        paris_evidence[
            "colt-paris2-location-page-captured-2026-07-19"
        ]["metadata"]["cooling_conflict_guardrail"] = ""
        mutations.append((paris_name, mutated, "cooling conflict must remain excluded"))

        mutated = copy.deepcopy(paris)
        paris_evidence = {row["key"]: row for row in mutated["evidence"]}
        paris_evidence[
            "colt-paris2-location-page-captured-2026-07-19"
        ]["excerpt"] += " It is currently under construction."
        mutations.append((paris_name, mutated, "Paris status wording must remain source-scoped"))

        mutated = copy.deepcopy(paris)
        paris_evidence = {row["key"]: row for row in mutated["evidence"]}
        paris_evidence[
            "colt-paris2-location-page-captured-2026-07-19"
        ]["metadata"]["related_card_guardrail"] = ""
        mutations.append((paris_name, mutated, "London 4 card must remain excluded"))

        mutated = copy.deepcopy(paris)
        paris_evidence = {row["key"]: row for row in mutated["evidence"]}
        paris_evidence[
            "colt-dcs-cy2025-sustainability-report-captured-2026-07-19"
        ]["metadata"]["rooftop_solar_area_as_reported_square_metres"] = 0
        mutations.append((paris_name, mutated, "installed solar must remain guarded metadata"))

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_candidate_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
