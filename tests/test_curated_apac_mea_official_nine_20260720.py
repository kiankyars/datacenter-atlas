from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RECORDED_AT = "2026-07-21T07:10:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts/apac-mea-official-nine-source-tranche-2026-07-20-v1"
)
V65_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v65.json"
V65_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v65/entities.csv"
V65_MANIFEST = ROOT / "releases/2026-07-20-open-seed-v65/manifest.json"

SOURCE_SPECS = {
    "curated-official-2026-07-20-sk-ai-data-center-ulsan.json": (
        8_727,
        "28c3e84fae1d949768da053f16209439bb694295c7629634d18e09e605a58bc9",
    ),
    "curated-official-2026-07-20-dci-koramco-ansan-sel02.json": (
        10_874,
        "98ee45a625ee6366ff89676fa48b058a711dfd168efb83369cef618a784d5ae3",
    ),
    "curated-official-2026-07-20-sify-bengaluru-02-current-build.json": (
        4_775,
        "ee6b6472e9a757239e19438f78c5b302d9761acc51dbe323e6b0bc4cb65e5203",
    ),
    "curated-official-2026-07-20-datavolt-tashkent-green-data-center.json": (
        10_389,
        "ebe6f8e5456f51cc64f66e03a9e3db5d4b6c9cd07ce9596a8e027054f911cec3",
    ),
    "curated-official-2026-07-20-datavolt-riyadh-first-phase.json": (
        5_184,
        "247f6daacd22f81c13aa5248d769165c416c5d35672c2c33a332a24158ceaac5",
    ),
    "curated-official-2026-07-20-datavolt-yanbu-first-phase.json": (
        5_133,
        "893eb78ff834f507cb9cc05b9ca5ae1379f16ce4c3a2a35df96e19277b1e31d4",
    ),
    "curated-official-2026-07-20-capitaland-navi-mumbai-tower-2.json": (
        8_319,
        "787c41abd758cecd9d91d08cbf975fd136a917ab39910537bcb11d3a4a757ac6",
    ),
    "curated-official-2026-07-20-capitaland-chennai-ambattur.json": (
        8_353,
        "702e8eb7624998684e9afaeed4de4234ab5349c3b214cd52c141f022a854abad",
    ),
    "curated-official-2026-07-20-stt-johor-1-current-build.json": (
        9_468,
        "785959fb2fb9962e1acefbd954ebb40b7d91305d180391c6311fc128c8899e7e",
    ),
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        3_036,
        "53c9a1697dcaabdc0aca09966be28e30058842479c1416cb1c6b5b1aa1f659eb",
    ),
    "identity-and-capacity-guardrails.json": (
        4_175,
        "64ab9ea38f594ca5679d7055d135c0e760c93b5acc4796d98f57078651831dbe",
    ),
    "manifest.json": (
        1_360,
        "1692f8d147ecd386c383c87dcf0f9f94f7b152aae5855c83f1ce14bbb3549772",
    ),
    "manifest.sha256": (
        80,
        "10cbf810114545ac87e3ec44bdfd92d41148379c2d62125e1059dae7dcf02d90",
    ),
    "retrieval-inventory.json": (
        24_536,
        "e49a304cfe6b1fa104e959b784d422c4274b8182d397306b43c4b7b9e26f84e8",
    ),
    "rights-and-disposition.json": (
        1_385,
        "b4cc9a667b36e4f06672251962530cd37f5568f5482738eeb50eda1a50cf6a2f",
    ),
    "source-snapshot.json": (
        7_112,
        "1aac01c8ebf30de8525cd02774dc5790d75344b9e6ff6a968a189c5b53f5eb0a",
    ),
}

CAMPUS_KEYS = {
    "curated:sk-ai-data-center-ulsan-campus",
    "curated:dci-koramco-ansan-sihwa-sel02-data-center",
    "curated:sify-bengaluru-02-data-center-campus",
    "curated:datavolt-tashkent-green-data-center",
    "curated:datavolt-riyadh-16mw-liquid-cooled-facility",
    "curated:datavolt-yanbu-4mw-facility",
    "curated:capitaland-dc-navi-mumbai-campus",
    "curated:capitaland-dc-chennai-ambattur",
    "curated:stt-johor-data-centre-campus",
}

PROJECT_KEYS = {
    "curated:sk-ai-data-center-ulsan-campus:current-facility-build",
    "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
    "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build",
    "curated:datavolt-tashkent-green-data-center:current-facility-build",
    "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase",
    "curated:datavolt-yanbu-4mw-facility:first-phase",
    "curated:capitaland-dc-navi-mumbai-campus:tower-2",
    "curated:capitaland-dc-chennai-ambattur:current-facility-build",
    "curated:stt-johor-data-centre-campus:stt-johor-1",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApacMeaOfficialNineCuratedTests(unittest.TestCase):
    def _documents(self) -> dict[str, dict[str, Any]]:
        return {
            name: json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))
            for name in SOURCE_SPECS
        }

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("APAC/MEA curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import(self, *, repetitions: int = 1):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = []
        with self._offline():
            for _ in range(repetitions):
                for name in SOURCE_SPECS:
                    results.append(
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            ROOT / "sources" / name,
                            recorded_at=RECORDED_AT,
                        )
                    )
        return temporary, connection, results

    def test_sources_are_canonical_mode_and_byte_pinned(self) -> None:
        documents = self._documents()
        self.assertEqual(len(documents), 9)
        for name, (expected_bytes, expected_hash) in SOURCE_SPECS.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertTrue(stat.S_ISREG(path.stat().st_mode))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            data = path.read_bytes()
            self.assertEqual(len(data), expected_bytes)
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected_hash)
            text = data.decode("utf-8")
            document = documents[name]
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            self.assertEqual(document["schema_version"], "1.1")
            self.assertNotIn("captured-2026-07-21", text)
            self.assertNotIn('"as_of_date": "2026-07-21"', text)
            for evidence in document["evidence"]:
                self.assertRegex(evidence["content_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(
                    evidence["metadata"]["content_hash_verification"],
                    "fetched_bytes_sha256",
                )
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["roles"], {})
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])

    def test_offline_import_is_exact_valid_and_idempotent(self) -> None:
        temporary, connection, results = self._import(repetitions=2)
        try:
            first, second = results[:9], results[9:]
            self.assertEqual(sum(row.entities_created for row in first), 18)
            self.assertEqual(sum(row.evidence_created for row in first), 15)
            self.assertTrue(all(row.warnings == () for row in first))
            self.assertEqual(sum(row.entities_created for row in second), 0)
            self.assertEqual(sum(row.evidence_created for row in second), 0)
            self.assertTrue(all(row.warnings == () for row in second))
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 18,
                    "evidence": 15,
                    "entity_snapshots": 18,
                    "lifecycle_observations": 9,
                    "operating_model_observations": 0,
                    "workload_observations": 3,
                    "capacity_estimates": 6,
                },
            )
            entities = list(
                connection.execute(
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key"
                )
            )
            self.assertEqual(
                {row["stable_key"] for row in entities if row["kind"] == "campus"},
                CAMPUS_KEYS,
            )
            self.assertEqual(
                {row["stable_key"] for row in entities if row["kind"] == "project"},
                PROJECT_KEYS,
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_physical_status_dates_are_exact_and_not_inflated(self) -> None:
        expected = {
            "curated:sk-ai-data-center-ulsan-campus:current-facility-build": (
                "under_construction",
                "2026-07-05",
                "authoritative_physical_status_update",
            ),
            "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build": (
                "under_construction",
                "2026-06-09",
                "authoritative_construction_start",
            ),
            "curated:sify-bengaluru-02-data-center-campus:two-tower-current-build": (
                "under_construction",
                "2025-05-14",
                "authoritative_construction_start",
            ),
            "curated:datavolt-tashkent-green-data-center:current-facility-build": (
                "under_construction",
                "2025-12-31",
                "authoritative_physical_status_update",
            ),
            "curated:datavolt-riyadh-16mw-liquid-cooled-facility:first-phase": (
                "under_construction",
                "2025-12-31",
                "authoritative_construction_start",
            ),
            "curated:datavolt-yanbu-4mw-facility:first-phase": (
                "under_construction",
                "2025-12-31",
                "authoritative_construction_start",
            ),
            "curated:capitaland-dc-navi-mumbai-campus:tower-2": (
                "under_construction",
                "2025-12-31",
                "authoritative_physical_status_update",
            ),
            "curated:capitaland-dc-chennai-ambattur:current-facility-build": (
                "under_construction",
                "2025-12-31",
                "authoritative_physical_status_update",
            ),
            "curated:stt-johor-data-centre-campus:stt-johor-1": (
                "under_construction",
                "2025-02-24",
                "authoritative_construction_start",
            ),
        }
        temporary, connection, _ = self._import()
        try:
            rows = connection.execute(
                "SELECT entities.stable_key, status, as_of_date, method "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id"
            )
            actual = {
                row["stable_key"]: (row["status"], row["as_of_date"], row["method"])
                for row in rows
            }
            self.assertEqual(actual, expected)
        finally:
            connection.close()
            temporary.cleanup()

        documents = self._documents()
        sify = documents[
            "curated-official-2026-07-20-sify-bengaluru-02-current-build.json"
        ]
        metadata = sify["evidence"][0]["metadata"]
        self.assertEqual(metadata["article_published_time"][:10], "2025-05-14")
        self.assertEqual(metadata["article_modified_time"][:10], "2026-03-16")
        self.assertIn("does not inflate", metadata["date_guardrail"])

    def test_capacity_bases_conflicts_and_non_additivity_are_exact(self) -> None:
        temporary, connection, _ = self._import()
        try:
            rows = connection.execute(
                "SELECT entities.stable_key, metric, stage, base, as_of_date, notes "
                "FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id "
                "ORDER BY entities.stable_key, metric"
            )
            actual = [tuple(row) for row in rows]
            self.assertEqual(
                [(row[0], row[1], row[2], row[3], row[4]) for row in actual],
                [
                    (
                        "curated:capitaland-dc-chennai-ambattur:current-facility-build",
                        "critical_it_mw",
                        "planned",
                        34.0,
                        "2025-12-31",
                    ),
                    (
                        "curated:capitaland-dc-chennai-ambattur:current-facility-build",
                        "gross_facility_mw",
                        "planned",
                        53.0,
                        "2025-12-31",
                    ),
                    (
                        "curated:capitaland-dc-navi-mumbai-campus:tower-2",
                        "critical_it_mw",
                        "planned",
                        37.0,
                        "2025-12-31",
                    ),
                    (
                        "curated:capitaland-dc-navi-mumbai-campus:tower-2",
                        "gross_facility_mw",
                        "planned",
                        55.0,
                        "2025-12-31",
                    ),
                    (
                        "curated:stt-johor-data-centre-campus",
                        "critical_it_mw",
                        "planned",
                        120.0,
                        "2025-12-01",
                    ),
                    (
                        "curated:stt-johor-data-centre-campus:stt-johor-1",
                        "critical_it_mw",
                        "planned",
                        16.0,
                        "2025-12-01",
                    ),
                ],
            )
            self.assertTrue(
                all(
                    "must not" in row[5]
                    or "alternative basis" in row[5]
                    or "nested within" in row[5]
                    for row in actual
                )
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM capacity_estimates "
                    "WHERE metric IN ('annual_energy_mwh', 'pue', "
                    "'grid_connection_mw', 'generation_mw')"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()
            temporary.cleanup()

        documents = self._documents()
        no_capacity = {
            "curated-official-2026-07-20-sk-ai-data-center-ulsan.json",
            "curated-official-2026-07-20-dci-koramco-ansan-sel02.json",
            "curated-official-2026-07-20-sify-bengaluru-02-current-build.json",
            "curated-official-2026-07-20-datavolt-tashkent-green-data-center.json",
            "curated-official-2026-07-20-datavolt-riyadh-first-phase.json",
            "curated-official-2026-07-20-datavolt-yanbu-first-phase.json",
        }
        for name in no_capacity:
            self.assertEqual(documents[name]["capacities"], [], name)

        serialized = "\n".join(json.dumps(documents[name]) for name in no_capacity)
        for prohibited in (
            '"metric": "annual_energy_mwh"',
            '"metric": "pue"',
            '"metric": "grid_connection_mw"',
            '"metric": "generation_mw"',
            '"metric": "critical_it_mw"',
            '"metric": "gross_facility_mw"',
        ):
            self.assertNotIn(prohibited, serialized)

    def test_workloads_are_intended_type_not_current_runtime(self) -> None:
        temporary, connection, _ = self._import()
        try:
            rows = connection.execute(
                "SELECT entities.stable_key, workload, as_of_date, method "
                "FROM workload_observations JOIN entities "
                "ON entities.id = workload_observations.entity_id "
                "ORDER BY entities.stable_key, workload"
            )
            self.assertEqual(
                [tuple(row) for row in rows],
                [
                    (
                        "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
                        "ai_specialized_unspecified",
                        "2026-06-11",
                        "company_disclosure",
                    ),
                    (
                        "curated:dci-koramco-ansan-sihwa-sel02-data-center:current-facility-build",
                        "general_cloud",
                        "2026-06-11",
                        "company_disclosure",
                    ),
                    (
                        "curated:sk-ai-data-center-ulsan-campus:current-facility-build",
                        "ai_specialized_unspecified",
                        "2026-07-05",
                        "company_disclosure",
                    ),
                ],
            )
        finally:
            connection.close()
            temporary.cleanup()

        documents = self._documents()
        guards = [
            documents[
                "curated-official-2026-07-20-sk-ai-data-center-ulsan.json"
            ]["evidence"][0]["metadata"]["workload_guardrail"],
            documents[
                "curated-official-2026-07-20-dci-koramco-ansan-sel02.json"
            ]["evidence"][2]["metadata"]["workload_guardrail"],
        ]
        for guard in guards:
            for phrase in (
                "under-construction project",
                "intended",
                "current runtime",
                "tenant or customer",
                "installed accelerator hardware",
                "utilization",
                "operational load",
                "training or inference workload",
            ):
                self.assertIn(phrase, guard)

    def test_linkedin_and_identity_guardrails_are_pinned(self) -> None:
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        requests = {row["request_id"]: row for row in inventory["controlled_http_requests"]}
        for request_id in ("dci_linkedin", "hsbc_linkedin", "datavolt_linkedin"):
            request = requests[request_id]
            self.assertEqual(request["http_status"], 200)
            self.assertEqual(request["curl_exit_code"], 0)
            self.assertTrue(request["unauthenticated_public_linkedin_representation"])
            self.assertEqual(len(request["body"]["sha256"]), 64)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertFalse(inventory["linkedin_login_used"])

        guardrails = json.loads(
            (ARTIFACT / "identity-and-capacity-guardrails.json").read_text(
                encoding="utf-8"
            )
        )
        identity = guardrails["identity_guardrails"]
        self.assertIn("SEL01", identity["dci_sel02"])
        self.assertIn("RYD SA1/SA2", identity["datavolt_riyadh"])
        self.assertIn("YANBU SA4", identity["datavolt_yanbu"])
        self.assertIn("Tower 1", identity["capitaland_navi_mumbai"])
        self.assertIn("ITPH", identity["capitaland_chennai"])

    def test_hash_only_artifact_and_trash_disposition_are_exact(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            path = ARTIFACT / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)

        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["closed_file_set"]), set(ARTIFACT_FILE_SPECS))
        self.assertFalse(manifest["raw_capture_redistributed"])
        for row in manifest["files"]:
            path = ARTIFACT / row["path"]
            self.assertEqual((len(path.read_bytes()), sha256(path)), (row["bytes"], row["sha256"]))
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )

        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["direct_request_attempts"], 18)
        self.assertEqual(inventory["successful_http_requests"], 14)
        self.assertEqual(inventory["failed_http_requests"], 4)
        self.assertEqual(inventory["evidence_supporting_requests"], 13)
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        original = Path(inventory["temporary_capture_directory_original_path"])
        trash = Path(inventory["temporary_capture_trash_path"])
        self.assertFalse(original.exists())
        self.assertEqual(trash.name, "dca-apac-mea-nine.gop3VK")

        if trash.is_dir():
            for request in inventory["controlled_http_requests"]:
                request_id = request["request_id"]
                for suffix, key in (
                    ("body", "body"),
                    ("headers", "headers"),
                    ("writeout", "curl_writeout"),
                ):
                    spec = request[key]
                    path = trash / f"{request_id}.{suffix}"
                    if spec.get("file_created") is False:
                        self.assertFalse(path.exists())
                        continue
                    self.assertEqual(
                        (len(path.read_bytes()), sha256(path)),
                        (spec["bytes"], spec["sha256"]),
                    )
            self.assertTrue((trash / "capitaland_filing.txt").is_file())

    def test_source_snapshot_and_frozen_v65_non_mutation_are_exact(self) -> None:
        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["totals"]["source_records"], 9)
        self.assertEqual(snapshot["totals"]["new_source_records"], 8)
        self.assertEqual(snapshot["totals"]["reused_source_records"], 1)
        for row in snapshot["source_records"]:
            path = ROOT / row["path"]
            self.assertEqual(
                (len(path.read_bytes()), sha256(path)),
                (row["bytes"], row["sha256"]),
            )

        self.assertEqual(len(V65_DEFINITION.read_bytes()), 79_924)
        self.assertEqual(
            sha256(V65_DEFINITION),
            "7431234bac3158ceada1f9545c841a5c59557ed97ec602695e0a3849da9c3d7d",
        )
        self.assertEqual(len(V65_MANIFEST.read_bytes()), 11_430)
        self.assertEqual(
            sha256(V65_MANIFEST),
            "38fcfc7fbd051decdb73c071762c2bb38e430ea43a4f9054489f51b6cb55c92b",
        )
        definition_text = V65_DEFINITION.read_text(encoding="utf-8")
        for name in SOURCE_SPECS:
            if name == "curated-official-2026-07-20-stt-johor-1-current-build.json":
                continue
            self.assertNotIn(name, definition_text)

        with V65_ENTITIES.open(newline="", encoding="utf-8") as handle:
            stable_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertTrue((CAMPUS_KEYS | PROJECT_KEYS).isdisjoint(stable_keys))


if __name__ == "__main__":
    unittest.main()
