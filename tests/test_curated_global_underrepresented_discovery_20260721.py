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

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RECORDED_AT = "2026-07-21T08:15:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts/global-underrepresented-official-discovery-2026-07-21-v1"
)
V66_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v66.json"
V67_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V67_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v67/manifest.json"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json": {
        "bytes": 5998,
        "sha256": "d87b556c1dd1aa9f979eaf37dd4d432b8f90884564e08cc8c32f8f619df3724b",
        "campus": "curated:scala-tambore-campus",
        "project": "curated:scala-tambore-campus:sgrutb07",
        "evidence": "scala-sgrutb07-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 36.0),
    },
    "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json": {
        "bytes": 6032,
        "sha256": "aaf91ac612720e5aaaf66fcc13a5061701b4f95ee5cd4499485b347f9a3d314c",
        "campus": "curated:scala-praia-do-futuro-campus",
        "project": "curated:scala-praia-do-futuro-campus:sforpf01",
        "evidence": "scala-sforpf01-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 7.2),
    },
    "curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json": {
        "bytes": 5948,
        "sha256": "04c1747343928095b9c2901c6ed95717766e8c6abce3e480d1157959791ab8c1",
        "campus": "curated:scala-lampa-campus",
        "project": "curated:scala-lampa-campus:sscllp01",
        "evidence": "scala-sscllp01-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 48.0),
    },
    "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json": {
        "bytes": 5666,
        "sha256": "1894b5625adfa95f03a4a3ba981fa0a5e28010ef1cfa0fe1e7ba858e9a877699",
        "campus": "curated:scala-huechuraba-campus",
        "project": "curated:scala-huechuraba-campus:ssclhb01",
        "evidence": "scala-ssclhb01-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 4.8),
    },
    "curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json": {
        "bytes": 5334,
        "sha256": "2ff597a72913f8650f7c4bfad476388972c087f4a92bb557900ab187ce56d5f5",
        "campus": "curated:scala-zona-franca-bogota-campus",
        "project": "curated:scala-zona-franca-bogota-campus:sbogzb01",
        "evidence": "scala-sbogzb01-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": None,
    },
    "curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json": {
        "bytes": 6033,
        "sha256": "5d8ffb54fbf33f9eead89b21f1d69f148f8f69ed1047a6adc8a160e24801a23c",
        "campus": "curated:scala-smextp02-tepotzotlan-data-center",
        "project": "curated:scala-smextp02-tepotzotlan-data-center:smextp02",
        "evidence": "scala-smextp02-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 2.0),
    },
    "curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json": {
        "bytes": 7048,
        "sha256": "0e976c4fd1e47bdd60495bbb1b9d98c0d9fc76b15d0aa7450b58088203a01b8f",
        "campus": "curated:green-mountain-fra-mainz-campus",
        "project": (
            "curated:green-mountain-fra-mainz-campus:"
            "current-three-building-development"
        ),
        "evidence": (
            "green-mountain-fra-mainz-current-project-page-captured-2026-07-21"
        ),
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("gross_facility_mw", "planned", 54.0),
    },
    "curated-official-2026-07-21-harch-dakhla-groundbreaking.json": {
        "bytes": 6882,
        "sha256": "15fd52022e98268ff7911dd6a013e5a22d0d6eeea5da411c670b271dbf44712e",
        "campus": "curated:harch-intelligence-dakhla-campus",
        "project": "curated:harch-intelligence-dakhla-campus:initial-development",
        "evidence": (
            "harch-dakhla-groundbreaking-2026-03-15-captured-2026-07-21"
        ),
        "lifecycle": (
            "under_construction",
            "2026-03-15",
            "authoritative_construction_start",
            0.9,
        ),
        "capacity": None,
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        3386,
        "f438d8ace1497e7070ed338a5d0bde13eafbb9a123cc26a299398d61e6d79828",
    ),
    "identity-and-capacity-guardrails.json": (
        3760,
        "9bb06d6b49a5713a46d8b66e502a5a5759f92348ebc4640157520ec05b7a3cd8",
    ),
    "manifest.json": (
        1364,
        "2a55ae530cdb478fd922d6fad30ce836682671cb0fed95a040d2788e6292c7be",
    ),
    "manifest.sha256": (
        80,
        "d168970c54626b216495a999e0f6e494a71548a6e9a8d4d1d79ed9d7a506324a",
    ),
    "retrieval-inventory.json": (
        5582,
        "72da82317157d378425ccd0657a1c92f402dc6fe629221518b40395c6635aa7f",
    ),
    "rights-and-disposition.json": (
        1219,
        "8b99b9525ce623769f9234cca6b0e1f0d3135c3c29be3cb7b02b407a5d965c03",
    ),
    "source-snapshot.json": (
        8902,
        "e58a912dbc6a278872fa030fd684480ff1d50284538736fe79df52d1e9c49927",
    ),
}

V67_ADDITIONS = {
    "sources/curated-official-2026-07-20-alps-duqm-under-construction.json",
    "sources/curated-official-2026-07-20-aurora-core-mikkeli-phase-1.json",
    "sources/curated-official-2026-07-20-capitaland-chennai-ambattur.json",
    "sources/curated-official-2026-07-20-capitaland-navi-mumbai-tower-2.json",
    "sources/curated-official-2026-07-20-datavolt-riyadh-first-phase.json",
    "sources/curated-official-2026-07-20-datavolt-tashkent-green-data-center.json",
    "sources/curated-official-2026-07-20-datavolt-yanbu-first-phase.json",
    "sources/curated-official-2026-07-20-dci-koramco-ansan-sel02.json",
    "sources/curated-official-2026-07-20-digital-edge-sel3-bupyeong.json",
    "sources/curated-official-2026-07-20-microsoft-kemps-creek-syd06-building-two.json",
    "sources/curated-official-2026-07-20-sify-bengaluru-02-current-build.json",
    "sources/curated-official-2026-07-20-sk-ai-data-center-ulsan.json",
    "sources/curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json",
    "sources/curated-official-2026-07-20-stt-johor-1-current-build.json",
}

CAPTURE_SPECS = {
    "scala_portfolio": {
        "body": (
            610118,
            "8a78e94b27e3cc375549845cf680b76eb678b19605de0c1411dbc6aafc84972b",
        ),
        "headers": (
            519,
            "3cc4a9b73a797f071ed123c0a782cc92cb13b22b22566d307189c6dda2c2cd3c",
        ),
        "writeout": (
            11985,
            "d5586b27a0b259330663404de8d2c2a7ced853ece20324719d618d2807a7b80b",
        ),
    },
    "green_mountain_mainz": {
        "body": (
            134900,
            "f8720070b7d4048db848a9addbc489b34da0e75267e40813497dab14eccb1505",
        ),
        "headers": (
            1242,
            "524b969a7ef4526d558d26ceda5700cd43d0726d8eac91c549def13255b09fae",
        ),
        "writeout": (
            9595,
            "5176889b8cafe785ab067de35d684a0f2f224bd59b1a04c802379ceb5d995053",
        ),
    },
    "harch_dakhla": {
        "body": (
            39736,
            "e7a4383fe2a8ce31043978b22ec5d9e8e4063ee1e73e47583f40b65dca4ae73b",
        ),
        "headers": (
            1598,
            "d55229afe95cc5ac8ec375795db9d0744be7fe173ac77e5460a7a676912f83f7",
        ),
        "writeout": (
            16267,
            "738de0f630ad229bb15b50111646684b97b25abef1a48f7534233e9dd68c7377",
        ),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GlobalUnderrepresentedOfficialDiscoveryTests(unittest.TestCase):
    def _documents(self) -> dict[str, dict[str, Any]]:
        return {
            name: json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))
            for name in SOURCE_SPECS
        }

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("curated discovery import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import(self, order: Iterable[str], *, repetitions: int = 1):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = []
        with self._offline():
            for _ in range(repetitions):
                for name in order:
                    results.append(
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            ROOT / "sources" / name,
                            recorded_at=RECORDED_AT,
                        )
                    )
        return temporary, connection, results

    def _semantic_snapshot(self, connection) -> dict[str, tuple[tuple[Any, ...], ...]]:
        queries = {
            "entities": "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
            "evidence": (
                "SELECT id, kind, source_url, published_at, retrieved_at, content_hash "
                "FROM evidence ORDER BY id"
            ),
            "snapshots": (
                "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
                "tags_json, as_of_date, method, confidence FROM entity_snapshots "
                "JOIN entities ON entities.id = entity_snapshots.entity_id "
                "ORDER BY entities.stable_key"
            ),
            "lifecycle": (
                "SELECT entities.stable_key, status, as_of_date, method, confidence "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id "
                "ORDER BY entities.stable_key"
            ),
            "capacity": (
                "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                "method, confidence, as_of_date FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id "
                "ORDER BY entities.stable_key, metric, stage"
            ),
        }
        return {
            name: tuple(tuple(row) for row in connection.execute(query))
            for name, query in queries.items()
        }

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        documents = self._documents()
        self.assertEqual(len(documents), 8)
        for name, spec in SOURCE_SPECS.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertTrue(stat.S_ISREG(path.stat().st_mode))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            data = path.read_bytes()
            self.assertEqual((len(data), sha256(path)), (spec["bytes"], spec["sha256"]))
            text = data.decode("utf-8")
            document = documents[name]
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            self.assertEqual(document["schema_version"], "1.1")
            self.assertEqual(document["campus"]["stable_key"], spec["campus"])
            self.assertEqual(document["project"]["stable_key"], spec["project"])
            self.assertEqual([row["key"] for row in document["evidence"]], [spec["evidence"]])
            self.assertEqual(document["evidence"][0]["license"], "all-rights-reserved")
            for entity in (document["campus"], document["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])

    def test_offline_import_is_exact_idempotent_and_order_independent(self) -> None:
        order = list(SOURCE_SPECS)
        temporary, connection, results = self._import(order, repetitions=2)
        reverse_temporary, reverse_connection, reverse_results = self._import(
            reversed(order)
        )
        try:
            first, second = results[:8], results[8:]
            self.assertEqual(sum(row.entities_created for row in first), 16)
            self.assertEqual(sum(row.evidence_created for row in first), 8)
            self.assertTrue(all(row.warnings == () for row in first))
            self.assertEqual(sum(row.entities_created for row in second), 0)
            self.assertEqual(sum(row.evidence_created for row in second), 0)
            self.assertTrue(all(row.warnings == () for row in second))
            self.assertTrue(all(row.warnings == () for row in reverse_results))
            self.assertEqual(validate_database(connection), [])
            self.assertEqual(validate_database(reverse_connection), [])
            self.assertEqual(
                self._semantic_snapshot(connection),
                self._semantic_snapshot(reverse_connection),
            )
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
                    "entities": 16,
                    "evidence": 8,
                    "entity_snapshots": 16,
                    "lifecycle_observations": 8,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 6,
                },
            )
        finally:
            connection.close()
            temporary.cleanup()
            reverse_connection.close()
            reverse_temporary.cleanup()

    def test_currentness_roles_and_physical_status_are_exact(self) -> None:
        documents = self._documents()
        expected_lifecycle = {
            spec["project"]: spec["lifecycle"] for spec in SOURCE_SPECS.values()
        }
        temporary, connection, _ = self._import(SOURCE_SPECS)
        try:
            rows = connection.execute(
                "SELECT entities.stable_key, status, as_of_date, method, confidence "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id"
            )
            actual = {
                row["stable_key"]: (
                    row["status"],
                    row["as_of_date"],
                    row["method"],
                    row["confidence"],
                )
                for row in rows
            }
            self.assertEqual(actual, expected_lifecycle)
        finally:
            connection.close()
            temporary.cleanup()

        scala_names = [name for name in SOURCE_SPECS if "scala-" in name]
        self.assertEqual(len(scala_names), 6)
        for name in scala_names:
            document = documents[name]
            self.assertIsNone(document["evidence"][0]["published_at"])
            self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-07-21")
            metadata = document["evidence"][0]["metadata"]
            self.assertEqual(metadata["portfolio_section_as_reported"], "Under construction")
            self.assertIn("Ongoing Civil Works", metadata["under_construction_definition_as_reported"])
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(document["project"]["roles"], {})

        green = documents[
            "curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json"
        ]
        expected_green_roles = {"developer": ["Green Mountain", "KMW"]}
        self.assertEqual(green["campus"]["roles"], expected_green_roles)
        self.assertEqual(green["project"]["roles"], expected_green_roles)
        self.assertEqual(green["lifecycle"][0]["as_of_date"], "2026-07-21")

        harch = documents[
            "curated-official-2026-07-21-harch-dakhla-groundbreaking.json"
        ]
        self.assertEqual(harch["evidence"][0]["published_at"], "2026-03-15")
        self.assertEqual(harch["evidence"][0]["retrieved_at"][:10], "2026-07-21")
        self.assertEqual(harch["lifecycle"][0]["as_of_date"], "2026-03-15")
        self.assertIn(
            "July current status remains independently unverified",
            harch["evidence"][0]["metadata"]["currentness_scope"],
        )
        expected_harch_roles = {"developer": ["Harch Intelligence"]}
        self.assertEqual(harch["campus"]["roles"], expected_harch_roles)
        self.assertEqual(harch["project"]["roles"], expected_harch_roles)
        self.assertIn(
            "does not adjudicate",
            harch["evidence"][0]["metadata"]["territorial_guardrail"],
        )

    def test_capacity_workload_and_hardware_boundaries_are_exact(self) -> None:
        expected = {
            spec["project"]: spec["capacity"]
            for spec in SOURCE_SPECS.values()
            if spec["capacity"] is not None
        }
        temporary, connection, _ = self._import(SOURCE_SPECS)
        try:
            rows = connection.execute(
                "SELECT entities.stable_key, metric, stage, base "
                "FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id"
            )
            actual = {
                row["stable_key"]: (row["metric"], row["stage"], row["base"])
                for row in rows
            }
            self.assertEqual(actual, expected)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM capacity_estimates WHERE metric IN "
                    "('grid_connection_mw', 'generation_nameplate_mw', "
                    "'annual_energy_mwh', 'pue')"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM operating_model_observations"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()
            temporary.cleanup()

        documents = self._documents()
        bogota = documents[
            "curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json"
        ]
        self.assertEqual(bogota["capacities"], [])
        green = documents[
            "curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json"
        ]
        self.assertEqual(green["capacities"][0]["metric"], "gross_facility_mw")
        self.assertIn("80 MW", green["capacities"][0]["notes"])
        self.assertIn("60 MW", green["capacities"][0]["notes"])
        harch = documents[
            "curated-official-2026-07-21-harch-dakhla-groundbreaking.json"
        ]
        metadata = harch["evidence"][0]["metadata"]
        self.assertEqual(
            (
                metadata["pipeline_capacity_mw_untyped_as_reported"],
                metadata["first_module_mw_untyped_as_reported"],
                metadata["gpu_count_as_reported"],
            ),
            (500, 100, 1798),
        )
        self.assertEqual(harch["capacities"], [])
        self.assertEqual(harch["workloads"], [])

    def test_v67_boundary_and_all_source_keys_are_collision_free(self) -> None:
        v66 = json.loads(V66_DEFINITION.read_text(encoding="utf-8"))
        v67 = json.loads(V67_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(len(v67["curated_inputs"]), 378)
        v66_paths = {row["path"] for row in v66["curated_inputs"]}
        v67_paths = {row["path"] for row in v67["curated_inputs"]}
        self.assertEqual(v67_paths - v66_paths, V67_ADDITIONS)
        proposed_paths = {f"sources/{name}" for name in SOURCE_SPECS}
        self.assertTrue(proposed_paths.isdisjoint(v67_paths))

        proposed_stable = {
            key
            for spec in SOURCE_SPECS.values()
            for key in (spec["campus"], spec["project"])
        }
        proposed_evidence = {spec["evidence"] for spec in SOURCE_SPECS.values()}
        other_stable: set[str] = set()
        other_evidence: set[str] = set()
        for path in (ROOT / "sources").glob("*.json"):
            if path.name in SOURCE_SPECS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str):
                    other_stable.add(entity["stable_key"])
            evidence = document.get("evidence")
            if isinstance(evidence, list):
                other_evidence.update(
                    row["key"]
                    for row in evidence
                    if isinstance(row, dict) and isinstance(row.get("key"), str)
                )
        self.assertEqual(
            proposed_stable & other_stable,
            {"curated:scala-tambore-campus"},
        )
        self.assertEqual(
            proposed_evidence & other_evidence,
            {"scala-sgrutb07-current-portfolio-captured-2026-07-21"},
        )
        self.assertEqual(len(proposed_stable), 16)
        self.assertEqual(len(proposed_evidence), 8)

        self.assertEqual((len(V67_DEFINITION.read_bytes()), sha256(V67_DEFINITION)), (
            83386,
            "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5",
        ))
        self.assertEqual((len(V67_MANIFEST.read_bytes()), sha256(V67_MANIFEST)), (
            12274,
            "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb",
        ))

    def test_hash_only_artifact_capture_closure_and_exclusions_are_exact(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, expected in ARTIFACT_FILE_SPECS.items():
            path = ARTIFACT / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((len(path.read_bytes()), sha256(path)), expected)
            if path.suffix == ".json":
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    text,
                    json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n",
                )

        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["closed_file_set"]), set(ARTIFACT_FILE_SPECS))
        for row in manifest["files"]:
            path = ARTIFACT / row["path"]
            self.assertEqual(
                (len(path.read_bytes()), sha256(path)),
                (row["bytes"], row["sha256"]),
            )
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
        requests = {row["request_id"]: row for row in inventory["controlled_http_requests"]}
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        for request_id, spec in CAPTURE_SPECS.items():
            request = requests[request_id]
            self.assertEqual(request["http_status"], 200)
            self.assertEqual(request["curl_exit_code"], 0)
            self.assertEqual(
                (request["body"]["bytes"], request["body"]["sha256"]),
                spec["body"],
            )
            self.assertEqual(
                (request["headers"]["bytes"], request["headers"]["sha256"]),
                spec["headers"],
            )
            self.assertEqual(
                (
                    request["curl_writeout"]["bytes"],
                    request["curl_writeout"]["sha256"],
                ),
                spec["writeout"],
            )
        forbidden_suffixes = {".body", ".headers", ".html", ".pdf", ".png", ".jpg"}
        self.assertTrue(
            all(path.suffix not in forbidden_suffixes for path in ARTIFACT.iterdir())
        )

        original = Path(inventory["temporary_capture_directory_original_path"])
        trash = Path(inventory["temporary_capture_trash_path"])
        self.assertFalse(original.exists())
        self.assertEqual(trash.name, "dc-global-underrepresented-20260721.iuUSa2")
        if trash.is_dir():
            for request_id, spec in CAPTURE_SPECS.items():
                for suffix, capture_key in (
                    ("body", "body"),
                    ("headers", "headers"),
                    ("writeout.json", "writeout"),
                ):
                    path = trash / f"{request_id}.{suffix}"
                    self.assertEqual(
                        (len(path.read_bytes()), sha256(path)),
                        spec[capture_key],
                    )

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["totals"]["source_records"], 8)
        self.assertEqual(snapshot["totals"]["capacity_estimates"], 6)
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        decisions = {row["decision"] for row in snapshot["bounded_discovery_exclusions"]}
        self.assertEqual(
            decisions,
            {
                "duplicate_not_added",
                "not_promoted",
                "historical_only_current_unknown",
                "not_current_build",
            },
        )


if __name__ == "__main__":
    unittest.main()
