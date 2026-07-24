from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

from datacenter_atlas.database import initialize
from datacenter_atlas.release import build_release_documents
from datacenter_atlas.service import validate_database
from datacenter_atlas.wikidata import (
    CLASS_QUERY,
    ITEM_QUERY,
    P_COORDINATE,
    P_COUNTRY,
    P_INSTANCE_OF,
    P_OPERATOR,
    P_POWER_CONSUMED,
    P_STATE_OF_USE,
    Q_PROPOSED,
    Q_MEGAWATT,
    Q_UNDER_CONSTRUCTION,
    WIKIDATA_COUNTRY_FALLBACK_METHOD,
    WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG,
    WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG,
    WIKIDATA_COUNTRY_FALLBACK_QID_TAG,
    WIKIDATA_LICENSE,
    WIKIDATA_ROOT_QID,
    WIKIDATA_SOURCE_FAMILY,
    WikidataAdapter,
    WikidataBundleError,
    WikidataFetcher,
    WikidataFetchError,
    _candidate_tags,
    validate_wikidata_bundle,
)


RETRIEVED_AT = "2026-07-18T12:00:00Z"
ENTITY_PREFIX = "http://www.wikidata.org/entity/"


def _item_value(qid: str) -> dict:
    return {
        "entity-type": "item",
        "numeric-id": int(qid[1:]),
        "id": qid,
    }


def _item_statement(
    property_id: str,
    qid: str,
    *,
    statement_id: str,
    rank: str = "normal",
    qualifiers: dict | None = None,
    references: list | None = None,
) -> dict:
    return {
        "id": statement_id,
        "type": "statement",
        "rank": rank,
        "mainsnak": {
            "snaktype": "value",
            "property": property_id,
            "datatype": "wikibase-item",
            "datavalue": {"value": _item_value(qid), "type": "wikibase-entityid"},
        },
        "qualifiers": qualifiers or {},
        "qualifiers-order": list(qualifiers or {}),
        "references": references or [],
    }


def _coordinate_statement(qid: str, latitude: float, longitude: float) -> dict:
    return {
        "id": f"{qid}$coordinate",
        "type": "statement",
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "property": P_COORDINATE,
            "datatype": "globe-coordinate",
            "datavalue": {
                "type": "globecoordinate",
                "value": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": None,
                    "precision": 0.0001,
                    "globe": f"{ENTITY_PREFIX}Q2",
                },
            },
        },
        "qualifiers": {},
        "qualifiers-order": [],
        "references": [],
    }


def _power_statement(qid: str, amount: str, unit_qid: str) -> dict:
    qualifier = {
        "P585": [
            {
                "snaktype": "value",
                "property": "P585",
                "datatype": "time",
                "hash": "qualifier-hash",
                "datavalue": {
                    "type": "time",
                    "value": {
                        "time": "+2026-00-00T00:00:00Z",
                        "timezone": 0,
                        "before": 0,
                        "after": 0,
                        "precision": 9,
                        "calendarmodel": f"{ENTITY_PREFIX}Q1985727",
                    },
                },
            }
        ]
    }
    reference = {
        "hash": "reference-hash",
        "snaks": {
            "P854": [
                {
                    "snaktype": "value",
                    "property": "P854",
                    "datatype": "url",
                    "datavalue": {
                        "type": "string",
                        "value": "https://example.test/source",
                    },
                }
            ]
        },
        "snaks-order": ["P854"],
    }
    return {
        "id": f"{qid}$power",
        "type": "statement",
        "rank": "preferred",
        "mainsnak": {
            "snaktype": "value",
            "property": P_POWER_CONSUMED,
            "datatype": "quantity",
            "datavalue": {
                "type": "quantity",
                "value": {
                    "amount": amount,
                    "lowerBound": amount,
                    "upperBound": amount,
                    "unit": f"{ENTITY_PREFIX}{unit_qid}",
                },
            },
        },
        "qualifiers": qualifier,
        "qualifiers-order": ["P585"],
        "references": [reference],
    }


def _entity(qid: str, label: str, claims: dict) -> dict:
    return {
        "id": qid,
        "type": "item",
        "lastrevid": int(qid[1:]) + 1000,
        "modified": "2026-07-18T10:00:00Z",
        "labels": {"en": {"language": "en", "value": label}},
        "descriptions": {
            "en": {"language": "en", "value": f"Description of {label}"}
        },
        "claims": claims,
    }


def _fixture_entities() -> dict[str, dict]:
    reference = [
        {
            "hash": "status-reference",
            "snaks": {},
            "snaks-order": [],
        }
    ]
    q1 = _entity(
        "Q1",
        "Structured construction site",
        {
            P_INSTANCE_OF: [
                _item_statement(P_INSTANCE_OF, WIKIDATA_ROOT_QID, statement_id="Q1$P31")
            ],
            P_COORDINATE: [_coordinate_statement("Q1", 51.5, -0.1)],
            P_OPERATOR: [
                _item_statement(P_OPERATOR, "Q10", statement_id="Q1$P137")
            ],
            P_COUNTRY: [
                _item_statement(P_COUNTRY, "Q20", statement_id="Q1$P17")
            ],
            P_STATE_OF_USE: [
                _item_statement(
                    P_STATE_OF_USE,
                    Q_UNDER_CONSTRUCTION,
                    statement_id="Q1$P5817",
                    qualifiers={
                        "P585": [
                            {
                                "snaktype": "value",
                                "property": "P585",
                                "datatype": "time",
                                "datavalue": {
                                    "type": "time",
                                    "value": {
                                        "time": "+2026-07-01T00:00:00Z",
                                        "precision": 11,
                                    },
                                },
                            }
                        ]
                    },
                    references=reference,
                )
            ],
            P_POWER_CONSUMED: [_power_statement("Q1", "+20", Q_MEGAWATT)],
        },
    )
    q2 = _entity(
        "Q2",
        "Under construction in name only",
        {
            P_INSTANCE_OF: [
                _item_statement(P_INSTANCE_OF, "Q137571914", statement_id="Q2$P31")
            ],
            P_COUNTRY: [
                _item_statement(P_COUNTRY, "Q20", statement_id="Q2$P17")
            ],
            P_POWER_CONSUMED: [_power_statement("Q2", "+5", "Q999")],
        },
    )
    q3 = _entity(
        "Q3",
        "Explicit proposed site",
        {
            P_INSTANCE_OF: [
                _item_statement(P_INSTANCE_OF, WIKIDATA_ROOT_QID, statement_id="Q3$P31")
            ],
            P_COORDINATE: [_coordinate_statement("Q3", -33.8, 151.2)],
            P_COUNTRY: [
                _item_statement(P_COUNTRY, "Q20", statement_id="Q3$P17-a"),
                _item_statement(P_COUNTRY, "Q21", statement_id="Q3$P17-b"),
            ],
            P_STATE_OF_USE: [
                _item_statement(
                    P_STATE_OF_USE, Q_PROPOSED, statement_id="Q3$P5817"
                )
            ],
        },
    )
    return {"Q1": q1, "Q2": q2, "Q3": q3}


class _Response(io.BytesIO):
    def __init__(self, raw: bytes, url: str) -> None:
        super().__init__(raw)
        self.status = 200
        self.url = url
        self.headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Date": "Sat, 18 Jul 2026 12:00:00 GMT",
            "Server": "fixture",
        }


class WikidataCountryFallbackTests(unittest.TestCase):
    def _tags(
        self, statements: list[dict], *, labels: dict[str, str]
    ) -> dict[str, str]:
        candidate = SimpleNamespace(
            qid="Q100",
            entity=_entity("Q100", "Country fallback fixture", {P_COUNTRY: statements}),
            description=None,
            selected_claims={},
        )
        return _candidate_tags(candidate, labels)

    def test_fallback_requires_one_distinct_truthy_qid_with_a_label(self) -> None:
        duplicate_qid = self._tags(
            [
                _item_statement(P_COUNTRY, "Q20", statement_id="one"),
                _item_statement(P_COUNTRY, "Q20", statement_id="two"),
            ],
            labels={"Q20": "Country Twenty"},
        )
        self.assertEqual(
            duplicate_qid[WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG], "Country Twenty"
        )
        self.assertEqual(duplicate_qid[WIKIDATA_COUNTRY_FALLBACK_QID_TAG], "Q20")
        self.assertEqual(
            duplicate_qid[WIKIDATA_COUNTRY_FALLBACK_METHOD_TAG],
            WIKIDATA_COUNTRY_FALLBACK_METHOD,
        )

        preferred_qid = self._tags(
            [
                _item_statement(
                    P_COUNTRY, "Q20", statement_id="preferred", rank="preferred"
                ),
                _item_statement(P_COUNTRY, "Q21", statement_id="normal"),
            ],
            labels={"Q20": "Country Twenty", "Q21": "Country Twenty-One"},
        )
        self.assertEqual(preferred_qid[WIKIDATA_COUNTRY_FALLBACK_QID_TAG], "Q20")

        ambiguous = self._tags(
            [
                _item_statement(P_COUNTRY, "Q20", statement_id="one"),
                _item_statement(P_COUNTRY, "Q21", statement_id="two"),
            ],
            labels={"Q20": "Country Twenty", "Q21": "Country Twenty-One"},
        )
        self.assertNotIn(WIKIDATA_COUNTRY_FALLBACK_LABEL_TAG, ambiguous)
        self.assertNotIn(WIKIDATA_COUNTRY_FALLBACK_QID_TAG, ambiguous)

        deprecated = self._tags(
            [_item_statement(P_COUNTRY, "Q20", statement_id="deprecated", rank="deprecated")],
            labels={"Q20": "Country Twenty"},
        )
        self.assertNotIn(WIKIDATA_COUNTRY_FALLBACK_QID_TAG, deprecated)

        unlabeled = self._tags(
            [_item_statement(P_COUNTRY, "Q20", statement_id="unlabeled")], labels={}
        )
        self.assertNotIn(WIKIDATA_COUNTRY_FALLBACK_QID_TAG, unlabeled)


class _FixtureEndpoint:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...] | int]] = []
        self.entities = _fixture_entities()

    @staticmethod
    def _sparql(variable: str, qids: list[str]) -> bytes:
        return json.dumps(
            {
                "head": {"vars": [variable]},
                "results": {
                    "bindings": [
                        {
                            variable: {
                                "type": "uri",
                                "value": f"{ENTITY_PREFIX}{qid}",
                            }
                        }
                        for qid in qids
                    ]
                },
            },
            separators=(",", ":"),
        ).encode()

    def __call__(self, request, *, timeout):
        self.assert_request(request, timeout)
        parsed = urllib.parse.urlparse(request.full_url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc == "query.wikidata.org":
            sparql = query["query"][0]
            offset = int(sparql.rsplit("OFFSET ", 1)[1].strip())
            if "?class wdt:P279*" in sparql:
                qids = ["Q137571914", WIKIDATA_ROOT_QID] if offset == 0 else []
                variable = "class"
                self.calls.append(("classes", offset))
            else:
                qids = {0: ["Q1", "Q2"], 2: ["Q3"]}.get(offset, [])
                variable = "item"
                self.calls.append(("items", offset))
            return _Response(self._sparql(variable, qids), request.full_url)

        qids = tuple(query["ids"][0].split("|"))
        props = query["props"][0]
        self.calls.append(("entities" if "claims" in props else "lookups", qids))
        if "claims" in props:
            entities = {qid: self.entities[qid] for qid in qids}
        else:
            entities = {
                qid: {
                    "id": qid,
                    "type": "item",
                    "labels": {
                        "en": {"language": "en", "value": f"Label {qid}"}
                    },
                    "descriptions": {},
                }
                for qid in qids
            }
        raw = json.dumps({"success": 1, "entities": entities}, separators=(",", ":")).encode()
        return _Response(raw, request.full_url)

    def assert_request(self, request, timeout) -> None:
        if request.method != "GET" or request.data is not None:
            raise AssertionError("fetcher must issue bodyless GET requests")
        if timeout != 60.0:
            raise AssertionError("fixture expected default timeout")
        if not request.headers.get("User-agent"):
            raise AssertionError("transparent User-Agent is required")


class WikidataQueryDefinitionTests(unittest.TestCase):
    def test_selection_is_explicit_and_license_is_cc0(self) -> None:
        self.assertIn("wdt:P279* wd:Q671224", CLASS_QUERY)
        self.assertIn("wdt:P31/wdt:P279* wd:Q671224", ITEM_QUERY)
        self.assertEqual(WIKIDATA_ROOT_QID, "Q671224")
        self.assertEqual(WIKIDATA_LICENSE, "CC0-1.0")
        self.assertEqual(WIKIDATA_SOURCE_FAMILY, "wikidata")


class WikidataFetcherTests(unittest.TestCase):
    def test_fetch_resumes_without_refetch_and_preserves_raw_statements(self) -> None:
        endpoint = _FixtureEndpoint()
        fetcher = WikidataFetcher(
            opener=endpoint,
            sleeper=lambda _seconds: None,
            clock=lambda: RETRIEVED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            partial = fetcher.fetch(
                directory, page_size=2, batch_size=2, max_requests=3
            )
            self.assertEqual(partial["state"], "in_progress")
            self.assertEqual(partial["last_run"]["stop_reason"], "max_requests")
            first_calls = list(endpoint.calls)

            complete = fetcher.fetch(directory, page_size=2, batch_size=2)
            self.assertEqual(complete["state"], "complete")
            self.assertEqual(complete["counts"]["classes"], 2)
            self.assertEqual(complete["counts"]["candidates"], 3)
            self.assertEqual(complete["counts"]["candidates_with_coordinates"], 2)
            self.assertEqual(complete["counts"]["power_consumed_claim_items"], 2)
            self.assertEqual(complete["counts"]["state_of_use_claim_items"], 2)
            self.assertEqual(endpoint.calls[: len(first_calls)], first_calls)
            self.assertEqual(endpoint.calls.count(("classes", 0)), 1)
            self.assertEqual(endpoint.calls.count(("classes", 2)), 1)
            self.assertEqual(endpoint.calls.count(("items", 0)), 1)

            view = validate_wikidata_bundle(directory)
            statement = view.entities["Q1"]["claims"][P_POWER_CONSUMED][0]
            self.assertEqual(statement["rank"], "preferred")
            self.assertIn("P585", statement["qualifiers"])
            self.assertEqual(statement["references"][0]["hash"], "reference-hash")
            self.assertEqual(
                json.loads((Path(directory) / "candidate-qids.json").read_text()),
                ["Q1", "Q2", "Q3"],
            )

            calls_before_cache_hit = len(endpoint.calls)
            cached = fetcher.fetch(directory, page_size=2, batch_size=2)
            self.assertEqual(cached, complete)
            self.assertEqual(len(endpoint.calls), calls_before_cache_hit)

    def test_transient_failures_open_a_persistent_circuit_breaker(self) -> None:
        calls = []

        def unavailable(request, *, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(
                request.full_url, 503, "unavailable", {}, None
            )

        with tempfile.TemporaryDirectory() as directory:
            fetcher = WikidataFetcher(
                opener=unavailable,
                max_retries=1,
                transient_failure_limit=2,
                retry_base_seconds=0,
                sleeper=lambda _seconds: None,
                clock=lambda: RETRIEVED_AT,
            )
            with self.assertRaisesRegex(WikidataFetchError, "circuit breaker"):
                fetcher.fetch(directory, page_size=2, batch_size=2)
            self.assertEqual(len(calls), 4)
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(len(manifest["failure_history"]), 2)
            self.assertEqual(
                manifest["last_run"]["stop_reason"], "transient_circuit_break"
            )
            validate_wikidata_bundle(directory, require_complete=False)

    def test_tampered_response_is_rejected(self) -> None:
        endpoint = _FixtureEndpoint()
        with tempfile.TemporaryDirectory() as directory:
            WikidataFetcher(
                opener=endpoint,
                sleeper=lambda _seconds: None,
                clock=lambda: RETRIEVED_AT,
            ).fetch(directory, page_size=2, batch_size=2)
            raw_file = Path(directory) / "entities/batch-00000.json"
            raw_file.write_bytes(raw_file.read_bytes() + b" ")
            with self.assertRaisesRegex(WikidataBundleError, "hash does not match"):
                validate_wikidata_bundle(directory)


class WikidataAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.bundle = root / "bundle"
        endpoint = _FixtureEndpoint()
        WikidataFetcher(
            opener=endpoint,
            sleeper=lambda _seconds: None,
            clock=lambda: RETRIEVED_AT,
        ).fetch(self.bundle, page_size=2, batch_size=2)
        self.connection, _ = initialize(root / "atlas.sqlite")

    def tearDown(self) -> None:
        self.connection.close()
        self.temporary_directory.cleanup()

    def test_import_is_conservative_provenanced_and_idempotent(self) -> None:
        first = WikidataAdapter().import_file(
            self.connection, self.bundle, retrieved_at=RETRIEVED_AT
        )
        self.assertEqual(first.examined_elements, 3)
        self.assertEqual(first.imported_elements, 3)
        self.assertEqual(first.entities_created, 3)
        self.assertEqual(first.evidence_created, 3)
        self.assertIn("source-scoped candidates", first.warnings[0])
        self.assertIn("no annual energy", first.warnings[-1])

        statuses = {
            row["status"]: row["count"]
            for row in self.connection.execute(
                "SELECT status, COUNT(*) AS count FROM lifecycle_observations GROUP BY status"
            )
        }
        self.assertEqual(
            statuses,
            {"under_construction": 1, "proposed": 1, "unknown": 1},
        )
        q2_status = self.connection.execute(
            """
            SELECT lifecycle_observations.status
            FROM lifecycle_observations
            JOIN entities ON entities.id = lifecycle_observations.entity_id
            WHERE entities.stable_key = 'wikidata:Q2'
            """
        ).fetchone()["status"]
        self.assertEqual(q2_status, "unknown")

        capacity = self.connection.execute(
            "SELECT metric, stage, base, unit, notes FROM capacity_estimates"
        ).fetchone()
        self.assertEqual(capacity["metric"], "gross_facility_mw")
        self.assertEqual(capacity["stage"], "unknown")
        self.assertEqual(capacity["base"], 20.0)
        self.assertEqual(capacity["unit"], "MW")
        self.assertIn("not critical IT", capacity["notes"])

        evidence = self.connection.execute(
            "SELECT * FROM evidence WHERE title LIKE 'Wikidata item Q1:%'"
        ).fetchone()
        self.assertEqual(evidence["license"], "CC0-1.0")
        self.assertEqual(evidence["source_family"], "wikidata")
        self.assertIn("?revision=1001", evidence["source_url"])
        metadata = json.loads(evidence["metadata_json"])
        retained = metadata["selected_claims"][P_POWER_CONSUMED][0]
        self.assertEqual(retained["rank"], "preferred")
        self.assertIn("P585", retained["qualifiers"])
        self.assertEqual(retained["references"][0]["hash"], "reference-hash")
        self.assertFalse(metadata["independent_corroboration"])
        self.assertEqual(
            metadata["provenance"]["raw_batch_sha256"],
            metadata["raw_batch_sha256"],
        )
        self.assertIn("?revision=1001", metadata["provenance"]["entity_data_url"])

        documents = build_release_documents(
            self.connection,
            as_of="2026-07-18",
            recorded_at=RETRIEVED_AT,
        )
        source_inputs = json.loads(documents["source_inputs.json"])["sources"]
        wikidata_inputs = [
            source for source in source_inputs if source["source_family"] == "wikidata"
        ]
        self.assertEqual(len(wikidata_inputs), 3)
        self.assertTrue(
            all(source["provenance"].get("raw_batch_sha256") for source in wikidata_inputs)
        )

        entity_rows = {
            row["name"]: row
            for row in csv.DictReader(io.StringIO(documents["entities.csv"]))
        }
        unlocated_single_country = entity_rows["Under construction in name only"]
        self.assertEqual(unlocated_single_country["country"], "Label Q20")
        self.assertEqual(
            unlocated_single_country["source_country_tag"], "Label Q20"
        )
        self.assertEqual(
            unlocated_single_country["source_country_method"],
            WIKIDATA_COUNTRY_FALLBACK_METHOD,
        )
        self.assertEqual(unlocated_single_country["source_country_qid"], "Q20")
        single_country_tags = json.loads(unlocated_single_country["tags_json"])
        self.assertEqual(single_country_tags["wikidata:country"], "Q20|Label Q20")

        ambiguous_country = entity_rows["Explicit proposed site"]
        self.assertEqual(ambiguous_country["country"], "")
        self.assertEqual(ambiguous_country["source_country_method"], "")
        self.assertEqual(ambiguous_country["source_country_qid"], "")
        ambiguous_tags = json.loads(ambiguous_country["tags_json"])
        self.assertEqual(
            ambiguous_tags["wikidata:country"], "Q20|Label Q20;Q21|Label Q21"
        )

        geojson = json.loads(documents["atlas.geojson"])
        unlocated_properties = next(
            feature["properties"]
            for feature in geojson["features"]
            if feature["properties"]["name"] == "Under construction in name only"
        )
        self.assertIsNone(unlocated_properties["administrative_assignment_status"])
        self.assertEqual(unlocated_properties["source_country_tag"], "Label Q20")
        self.assertEqual(
            unlocated_properties["source_country_method"],
            WIKIDATA_COUNTRY_FALLBACK_METHOD,
        )
        self.assertEqual(unlocated_properties["source_country_qid"], "Q20")

        summary = json.loads(documents["summary.json"])
        self.assertEqual(
            summary["country_source_claims_by_method"],
            {WIKIDATA_COUNTRY_FALLBACK_METHOD: 2},
        )

        counts_before = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "capacity_estimates",
            )
        }
        second = WikidataAdapter().import_file(
            self.connection, self.bundle, retrieved_at=RETRIEVED_AT
        )
        self.assertEqual(second.entities_created, 0)
        self.assertEqual(second.evidence_created, 0)
        counts_after = {
            table: self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in counts_before
        }
        self.assertEqual(counts_after, counts_before)
        self.assertEqual(validate_database(self.connection), [])

    def test_import_rejects_a_different_retrieval_identity(self) -> None:
        with self.assertRaisesRegex(WikidataBundleError, "must equal"):
            WikidataAdapter().import_file(
                self.connection,
                self.bundle,
                retrieved_at="2026-07-18T13:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
