from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Iterable, Sequence
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "sources"
RETRIEVED_AT = "2026-07-20T09:05:11Z"
PUBLISHED_AT = "2026-05-26"
REPORTING_AS_OF = "2026-03-31"
EVIDENCE_KEY = "goodman-q3-fy26-operational-update-pdf-captured-2026-07-20"
PDF_BYTES = 9_358_661
PDF_SHA256 = "713196902d9c92df2502874d5cfa44f86a2ac4de35022a76f33983dba8053227"
HEADERS_SHA256 = "a3ccb54c1e435a3fc0bc97c06bc53af64d7f5e5b7cdd150b8c2fe92c74da8296"
CURL_FACTS_SHA256 = "97aa4cbdb453d6d8ca4437b6f3fc925b911f6eaada28a668def0303f17a4abd7"
LAX01_ENRICHMENT = (
    "curated-official-2026-07-22-goodman-databank-lax01-enrichment.json"
)
LAX01_ENRICHMENT_BYTES = 13_595
LAX01_ENRICHMENT_SHA256 = (
    "fc07e93af6357b754ee6b03d052958e9f73201c177459cf1d2c19b4ca4a5ebf5"
)

GEDCDP = "Goodman European Data Centre Development Partnership I"
GJDP = "Goodman Japan Development Partnership"
GHKDCP = "Goodman Hong Kong Data Centre Partnership"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-goodman-ams01-amsterdam-v2.json": {
        "bytes": 21_132,
        "sha256": "802d18c2dab6091add67c798064c60dbed843a0c639abc3b843adaf68d77f1a0",
        "v1": "curated-official-2026-07-20-goodman-ams01-amsterdam.json",
        "v1_bytes": 20_945,
        "v1_sha256": "86b5bab9cd778409410e5cd769cc7d7878f1d96d5ac4a8fe12471ae7ca43abd4",
        "code": "AMS01",
        "campus": "curated:goodman-ams01-amsterdam-data-centre-campus",
        "project": "curated:goodman-ams01-amsterdam-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GEDCDP,
        "address": "Amsterdam, Netherlands",
    },
    "curated-official-2026-07-20-goodman-fra02-frankfurt-v2.json": {
        "bytes": 21_190,
        "sha256": "2016970c6feda0ed1df7299c346713a29c86eed4088994f74fce515ddb809830",
        "v1": "curated-official-2026-07-20-goodman-fra02-frankfurt.json",
        "v1_bytes": 21_003,
        "v1_sha256": "f30db3b92de147265dfe281c307482f2679e57eecb7d436de8412179521408de",
        "code": "FRA02",
        "campus": "curated:goodman-fra02-frankfurt-data-centre-campus",
        "project": "curated:goodman-fra02-frankfurt-data-centre-campus:phase-1-current-development",
        "status": "under_construction",
        "owner": GEDCDP,
        "address": "Frankfurt South Availability Zone, Frankfurt, Germany",
    },
    "curated-official-2026-07-20-goodman-hkg10-tsuen-wan-v2.json": {
        "bytes": 21_082,
        "sha256": "ce187a48475f227603a73922320a14cf03b7f6c88374830e969f5cba6d1138b9",
        "v1": "curated-official-2026-07-20-goodman-hkg10-tsuen-wan.json",
        "v1_bytes": 20_895,
        "v1_sha256": "a6d006f832c90cc98b457dc4213e4c44d1ae01b80315ab14a492bbc69b568c92",
        "code": "HKG10",
        "campus": "curated:goodman-hkg10-tsuen-wan-data-centre",
        "project": "curated:goodman-hkg10-tsuen-wan-data-centre:current-redevelopment",
        "status": "under_construction",
        "owner": GHKDCP,
        "address": "Tsuen Wan, Hong Kong",
    },
    "curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json": {
        "bytes": 21_121,
        "sha256": "296b17b45a9a6f56037b137ca68f37e549607317c2550b3e606a59e640528249",
        "v1": "curated-official-2026-07-20-goodman-lax01-los-angeles.json",
        "v1_bytes": 20_934,
        "v1_sha256": "5e79a2176b02b4be58d7531ef6a957e410ef28448e8dd7c8e9fc0f0d0839e9b7",
        "code": "LAX01",
        "campus": "curated:goodman-lax01-los-angeles-program-anchor",
        "project": "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development",
        "status": "mep_electrical",
        "owner": "Goodman DataBank JV",
        "address": "Los Angeles metro, United States",
    },
    "curated-official-2026-07-20-goodman-par01-paris-v2.json": {
        "bytes": 21_158,
        "sha256": "f7d558d0e0234379ae3013bd794bd878a0c70ae9ccfcefd1718ee23406c6711c",
        "v1": "curated-official-2026-07-20-goodman-par01-paris.json",
        "v1_bytes": 20_971,
        "v1_sha256": "28179d0b0640362a2fa2405c8fb1564c408e3966fecac776267e091da1ea801a",
        "code": "PAR01",
        "campus": "curated:goodman-par01-paris-data-centre-campus",
        "project": "curated:goodman-par01-paris-data-centre-campus:phase-1-current-development",
        "status": "under_construction",
        "owner": GEDCDP,
        "address": "North Paris Availability Zone, Paris, France",
    },
    "curated-official-2026-07-20-goodman-par02-paris-v2.json": {
        "bytes": 21_158,
        "sha256": "f7e770519d244a8b57d7710c7ae1674ec2390bcd44f8d1b73d8c642adf5319c6",
        "v1": "curated-official-2026-07-20-goodman-par02-paris.json",
        "v1_bytes": 20_971,
        "v1_sha256": "2ea8e966b737170e2e74ae829c89e61c9eacdc89fc980ceef344454834791e81",
        "code": "PAR02",
        "campus": "curated:goodman-par02-paris-data-centre-campus",
        "project": "curated:goodman-par02-paris-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GEDCDP,
        "address": "Paris Central Availability Zone, Paris, France",
    },
    "curated-official-2026-07-20-goodman-ty005-tokyo-v2.json": {
        "bytes": 21_071,
        "sha256": "045cf3bb76bc9171ce017784562bcebab5eb5fc306c9ab017981631ce2e84764",
        "v1": "curated-official-2026-07-20-goodman-ty005-tokyo.json",
        "v1_bytes": 20_884,
        "v1_sha256": "7f73b491775f176a2ab1dbacad6842e1aca60b8797771d373bc6d48987f1b47d",
        "code": "TY005",
        "campus": "curated:goodman-ty005-tokyo-data-centre-campus",
        "project": "curated:goodman-ty005-tokyo-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GJDP,
        "address": "Tokyo, Japan",
    },
    "curated-official-2026-07-20-goodman-ty006-tokyo-v2.json": {
        "bytes": 22_498,
        "sha256": "991f66bc60af577f47d2ad0a87ce861524ab805090d0215b1ff3bf5407dffdb4",
        "v1": "curated-official-2026-07-20-goodman-ty006-tokyo.json",
        "v1_bytes": 22_311,
        "v1_sha256": "76b5a70e873caa7993c18d2f546cfa993ea0ab1f110f22b5b4d7dde0c98715f0",
        "code": "TY006",
        "campus": "curated:goodman-ty006-tokyo-data-centre-site",
        "project": "curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development",
        "status": "under_construction",
        "owner": None,
        "address": "Tokyo, Japan",
    },
}
V2_SOURCES = tuple(SOURCE_SPECS)
HKG09_V1 = "curated-official-2026-07-20-goodman-hkg09-kwai-chung.json"
SYD01_V1 = "curated-official-2026-07-20-goodman-syd01-macquarie-park.json"
HKG09_V2 = "curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json"
SYD01_V2 = "curated-official-2026-07-20-goodman-syd01-macquarie-park-v2.json"
FULL_V2_SELECTION = (*V2_SOURCES, HKG09_V2, SYD01_V2)
FROZEN_DEFINITIONS = {
    "open-seed-2026-07-20-v44.json": (
        "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
    ),
    "open-seed-2026-07-20-v45.json": (
        "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13"
    ),
}


class GoodmanQ3FY26RemainingV2CuratedTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((SOURCES_DIR / name).read_text(encoding="utf-8"))

    def _expected_identity_occurrences(
        self, v2: str, spec: dict[str, Any]
    ) -> set[str]:
        expected = {spec["v1"], v2}
        if spec["code"] == "LAX01":
            expected.add(LAX01_ENRICHMENT)
        return expected

    def _assert_exact_identity_occurrences(
        self, actual: set[str], v2: str, spec: dict[str, Any]
    ) -> None:
        self.assertEqual(
            actual,
            self._expected_identity_occurrences(v2, spec),
            "identity occurrence set differs",
        )

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Goodman Q3 remaining-v2 import used the network")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _selection_claims(self, names: Iterable[str]) -> dict[tuple[str, str], str]:
        claims: dict[tuple[str, str], str] = {}
        evidence: dict[str, tuple[str, str, str]] = {}
        for name in names:
            document = self._load(name)
            for kind in ("campus", "project"):
                entity = document[kind]
                claim = (kind, entity["stable_key"])
                if claim in claims:
                    raise ValueError(
                        "stable-key source-selection collision: "
                        f"{claims[claim]} and {name} claim {kind} "
                        f"{entity['stable_key']}"
                    )
                claims[claim] = name
            for item in document["evidence"]:
                fingerprint = (
                    item["content_hash"],
                    item["source_url"],
                    item["publisher"],
                )
                prior = evidence.get(item["key"])
                if prior is not None and prior != fingerprint:
                    raise ValueError(
                        "conflicting evidence-key source-selection collision: "
                        f"{item['key']}"
                    )
                evidence[item["key"]] = fingerprint
        return claims

    def _state(
        self,
        names: Sequence[str],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in names:
                            document = self._load(name)
                            retrieved_at = document["evidence"][0]["retrieved_at"]
                            result = CuratedOfficialSourceAdapter().import_file(
                                connection,
                                SOURCES_DIR / name,
                                retrieved_at=retrieved_at,
                            )
                            self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, method FROM entity_snapshots "
                    "JOIN entities ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, as_of_date",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date, "
                    "target_date, notes FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model FROM "
                    "operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key, operating_model",
                    "SELECT entities.stable_key, workload FROM workload_observations "
                    "JOIN entities ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
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
        forbidden_metadata_fragments = (
            "authorization",
            "cookie",
            "local_ip",
            "local_port",
            "primary_ip",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        )
        for name, spec in SOURCE_SPECS.items():
            document = documents[name]
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
            self.assertEqual(len(document["evidence"]), 1)
            evidence = document["evidence"][0]
            metadata = evidence["metadata"]
            self.assertEqual(evidence["key"], EVIDENCE_KEY)
            self.assertEqual(evidence["published_at"], PUBLISHED_AT)
            self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
            self.assertEqual(evidence["content_hash"], PDF_SHA256)
            self.assertIn("as at March 31, 2026", evidence["excerpt"])
            self.assertNotIn("current at the May", evidence["excerpt"])
            self.assertEqual(metadata["reporting_date_as_reported"], "31 March 2026")
            self.assertIn("later row-specific", metadata["status_scope"])
            self.assertIn("does not establish", metadata["status_scope"])
            self.assertIn("no later row-specific", metadata["activity_date_basis"])
            self.assertIn("does not advance", metadata["activity_date_basis"])
            self.assertIn("Evidence publication remains", metadata["semantic_date_guardrail"])
            self.assertTrue(
                all(
                    fragment not in field.casefold()
                    for field in metadata
                    for fragment in forbidden_metadata_fragments
                )
            )

            campus = document["campus"]
            project = document["project"]
            self.assertEqual(campus["stable_key"], spec["campus"])
            self.assertEqual(project["stable_key"], spec["project"])
            expected_roles = (
                {} if spec["owner"] is None else {"owner": [spec["owner"]]}
            )
            self.assertEqual(campus["roles"], expected_roles)
            self.assertEqual(project["roles"], {})
            for entity in (campus, project):
                self.assertEqual(entity["address"], spec["address"])
                self.assertEqual(entity["as_of_date"], REPORTING_AS_OF)
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
            self.assertEqual(
                document["lifecycle"],
                [
                    {
                        "entity": "project",
                        "value": spec["status"],
                        "evidence_key": EVIDENCE_KEY,
                        "as_of_date": REPORTING_AS_OF,
                        "method": "authoritative_physical_status_update",
                        "confidence": 0.99,
                    }
                ],
            )
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            if spec["code"] == "TY006":
                self.assertEqual(
                    {(row["metric"], row["base"]) for row in document["capacities"]},
                    {("gross_facility_mw", 50), ("critical_it_mw", 33)},
                )
                for row in document["capacities"]:
                    self.assertEqual(row["stage"], "planned")
                    self.assertEqual(row["as_of_date"], REPORTING_AS_OF)
                    self.assertIsNone(row["target_date"])
                    self.assertIn("not additive", row["notes"])
            else:
                self.assertEqual(document["capacities"], [])

        lax_metadata = documents[
            "curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json"
        ]["evidence"][0]["metadata"]
        self.assertIn("locality-scoped non-site", lax_metadata["lax01_program_anchor_guardrail"])
        self.assertIn("raw reported program_site_count of 3", lax_metadata["unique_site_guardrail"])
        self.assertIn("untyped evidence metadata", lax_metadata["main_table_power_typing_guardrail"])
        self.assertIn("no site-level current electrical load", lax_metadata["energy_guardrail"])

    def test_exact_canonical_files_v1_pins_and_shared_evidence(self) -> None:
        shared_evidence: bytes | None = None
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = SOURCES_DIR / name
                raw = path.read_bytes()
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (
                    spec["bytes"],
                    spec["sha256"],
                ))
                text = raw.decode("utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                evidence = json.dumps(
                    document["evidence"][0], indent=2, ensure_ascii=False
                ).encode()
                if shared_evidence is None:
                    shared_evidence = evidence
                self.assertEqual(evidence, shared_evidence)

                v1_raw = (SOURCES_DIR / spec["v1"]).read_bytes()
                self.assertEqual(
                    (len(v1_raw), hashlib.sha256(v1_raw).hexdigest()),
                    (spec["v1_bytes"], spec["v1_sha256"]),
                )

    def test_publication_reporting_lineage_and_forbidden_telemetry(self) -> None:
        documents = {name: self._load(name) for name in V2_SOURCES}
        self._assert_semantic_contract(documents)
        evidence = documents[V2_SOURCES[0]]["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(metadata["http_content_length_bytes_as_received"], PDF_BYTES)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], PDF_BYTES)
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertEqual(metadata["capture_curl_writeout_sha256"], CURL_FACTS_SHA256)
        self.assertEqual(metadata["document_date_as_reported"], "26 May 2026")
        self.assertEqual(metadata["asx_release_date"], PUBLISHED_AT)
        self.assertNotEqual(evidence["published_at"], REPORTING_AS_OF)
        source_text = "\n".join(
            (SOURCES_DIR / name).read_text(encoding="utf-8")
            for name in V2_SOURCES
        )
        self.assertNotIn("curl_ssl_verify_result", source_text)
        self.assertNotIn("curl_remote_ip_as_received", source_text)
        self.assertNotIn('"as_of_date": "2026-05-26"', source_text)

    def test_eight_v2_import_is_offline_order_independent_and_idempotent(self) -> None:
        self._selection_claims(V2_SOURCES)
        forward = self._state(V2_SOURCES)
        self.assertEqual(self._state(tuple(reversed(V2_SOURCES))), forward)
        self.assertEqual(self._state(V2_SOURCES, repetitions=2), forward)
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = forward
        self.assertEqual(len(entities), 16)
        self.assertEqual(Counter(kind for kind, _ in entities), {"campus": 8, "project": 8})
        self.assertEqual(evidence, ((EVIDENCE_KEY, PDF_SHA256),))
        self.assertEqual(len(snapshots), 16)
        self.assertEqual({row[6] for row in snapshots}, {REPORTING_AS_OF})
        self.assertEqual(len(lifecycle), 8)
        self.assertEqual(Counter(row[1] for row in lifecycle), {
            "mep_electrical": 4,
            "under_construction": 4,
        })
        self.assertEqual({row[2] for row in lifecycle}, {REPORTING_AS_OF})
        self.assertEqual(
            {(row[1], row[2], row[3], row[4], row[5]) for row in capacities},
            {
                ("critical_it_mw", "planned", 33.0, REPORTING_AS_OF, None),
                ("gross_facility_mw", "planned", 50.0, REPORTING_AS_OF, None),
            },
        )
        self.assertTrue(all("not additive" in row[6] for row in capacities))
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 8)

    def test_full_v2_selection_excludes_hkg09_syd01_originals(self) -> None:
        self.assertNotIn(HKG09_V1, FULL_V2_SELECTION)
        self.assertNotIn(SYD01_V1, FULL_V2_SELECTION)
        self.assertIn(HKG09_V2, FULL_V2_SELECTION)
        self.assertIn(SYD01_V2, FULL_V2_SELECTION)
        claims = self._selection_claims(FULL_V2_SELECTION)
        self.assertEqual(len(claims), 20)
        state = self._state(FULL_V2_SELECTION)
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = state
        self.assertEqual(len(entities), 20)
        self.assertEqual(len(evidence), 6)
        self.assertEqual(len(snapshots), 20)
        self.assertEqual(len(lifecycle), 10)
        self.assertEqual(len(capacities), 6)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 10)

    def test_each_v1_v2_pair_collides_and_preserves_stable_identity(self) -> None:
        selected_claims = self._selection_claims(V2_SOURCES)
        self.assertEqual(len(selected_claims), 16)
        for v2, spec in SOURCE_SPECS.items():
            with self.subTest(v2=v2):
                with self.assertRaisesRegex(ValueError, "source-selection collision"):
                    self._selection_claims((*V2_SOURCES, spec["v1"]))
                old = self._load(spec["v1"])
                new = self._load(v2)
                self.assertEqual(old["campus"]["stable_key"], new["campus"]["stable_key"])
                self.assertEqual(old["project"]["stable_key"], new["project"]["stable_key"])
                self.assertEqual(old["evidence"][0]["key"], new["evidence"][0]["key"])
                self.assertEqual(old["evidence"][0]["content_hash"], PDF_SHA256)
                self.assertNotEqual(old["evidence"][0], new["evidence"][0])

        claimed_keys = {key for kind, key in selected_claims if kind in {"campus", "project"}}
        occurrences: dict[str, set[str]] = {key: set() for key in claimed_keys}
        for path in sorted(SOURCES_DIR.glob("curated-official-*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if isinstance(entity, dict) and entity["stable_key"] in occurrences:
                    occurrences[entity["stable_key"]].add(path.name)
        for v2, spec in SOURCE_SPECS.items():
            if spec["code"] == "LAX01":
                enrichment_path = SOURCES_DIR / LAX01_ENRICHMENT
                raw = enrichment_path.read_bytes()
                self.assertEqual(len(raw), LAX01_ENRICHMENT_BYTES)
                self.assertEqual(
                    hashlib.sha256(raw).hexdigest(), LAX01_ENRICHMENT_SHA256
                )
                enrichment = json.loads(raw)
                self.assertEqual(
                    enrichment["campus"]["stable_key"], spec["campus"]
                )
                self.assertEqual(
                    enrichment["project"]["stable_key"], spec["project"]
                )
                self.assertEqual(enrichment["lifecycle"], [])
            self._assert_exact_identity_occurrences(
                occurrences[spec["campus"]], v2, spec
            )
            self._assert_exact_identity_occurrences(
                occurrences[spec["project"]], v2, spec
            )

    def test_arbitrary_fourth_lax01_identity_occurrence_still_fails(self) -> None:
        v2, spec = next(
            (name, row)
            for name, row in SOURCE_SPECS.items()
            if row["code"] == "LAX01"
        )
        arbitrary = self._expected_identity_occurrences(v2, spec) | {
            "curated-official-arbitrary-fourth-lax01.json"
        }
        with self.assertRaisesRegex(AssertionError, "identity occurrence set differs"):
            self._assert_exact_identity_occurrences(arbitrary, v2, spec)

    def test_v2_tranche_is_excluded_from_frozen_v44_and_v45(self) -> None:
        markers = {
            EVIDENCE_KEY,
            *(f"sources/{name}" for name in V2_SOURCES),
            *(spec["sha256"] for spec in SOURCE_SPECS.values()),
            *(spec["campus"] for spec in SOURCE_SPECS.values()),
            *(spec["project"] for spec in SOURCE_SPECS.values()),
        }
        for definition_name, expected_sha256 in FROZEN_DEFINITIONS.items():
            with self.subTest(definition=definition_name):
                definition_path = SOURCES_DIR / definition_name
                raw = definition_path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_sha256)
                definition = json.loads(raw)
                pinned = {row["path"] for row in definition["curated_inputs"]}
                self.assertTrue(
                    {f"sources/{name}" for name in V2_SOURCES}.isdisjoint(pinned)
                )
                version = definition_name.removeprefix("open-seed-").removesuffix(".json")
                release = ROOT / "releases" / f"2026-07-20-open-seed-{version.rsplit('-', 1)[-1]}"
                payloads = [raw]
                payloads.extend(
                    path.read_bytes() for path in release.rglob("*") if path.is_file()
                )
                for marker in markers:
                    self.assertFalse(
                        any(marker.encode("utf-8") in payload for payload in payloads),
                        marker,
                    )

    def test_semantic_date_telemetry_and_lax_mutations_fail(self) -> None:
        original = {name: self._load(name) for name in V2_SOURCES}
        mutations: list[tuple[str, dict[str, dict[str, Any]]]] = []

        changed = copy.deepcopy(original)
        changed[V2_SOURCES[0]]["lifecycle"][0]["as_of_date"] = PUBLISHED_AT
        mutations.append(("publication-promoted-to-status-date", changed))

        changed = copy.deepcopy(original)
        changed[V2_SOURCES[0]]["evidence"][0]["metadata"][
            "curl_remote_ip_as_received"
        ] = "192.0.2.1"
        mutations.append(("transport-telemetry-added", changed))

        lax = "curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json"
        changed = copy.deepcopy(original)
        changed[lax]["campus"]["geometry"] = {
            "type": "Point",
            "coordinates": [-118.2, 34.0],
        }
        mutations.append(("lax-program-anchor-mapped-as-site", changed))

        for label, documents in mutations:
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                self._assert_semantic_contract(documents)


if __name__ == "__main__":
    unittest.main()
