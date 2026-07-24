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
RECORDED_AT = "2026-07-21T09:00:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts/second-underrepresented-official-discovery-2026-07-21-v1"
)
PRIOR_SCALA_SOURCE = (
    ROOT
    / "sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json"
)
V67_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V67_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v67/manifest.json"
SHARED_CAMPUS = "curated:scala-tambore-campus"
SHARED_CAMPUS_EVIDENCE = "scala-sgrutb07-current-portfolio-captured-2026-07-21"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json": {
        "bytes": 10805,
        "sha256": "1b43db6573bac2d62848abd8775a9542ca46e282a7057be7afc1353293c65763",
        "campus": SHARED_CAMPUS,
        "project": "curated:scala-tambore-campus:sgrutb09",
        "evidence": "scala-sgrutb09-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.99,
        ),
        "capacity": ("critical_it_mw", "design", 36.0),
        "scala": True,
    },
    "curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json": {
        "bytes": 10968,
        "sha256": "7858e23a565879feb9e5fd4254b9f793809735e5fdd3b96717bfb77f3f3ddc14",
        "campus": SHARED_CAMPUS,
        "project": "curated:scala-tambore-campus:sgrutb10",
        "evidence": "scala-sgrutb10-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.95,
        ),
        "capacity": ("critical_it_mw", "design", 36.0),
        "scala": True,
    },
    "curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json": {
        "bytes": 10971,
        "sha256": "3c1d13af526ff67b54af365252d25639352cca6608d6ca4e76a2f69a4b81624c",
        "campus": SHARED_CAMPUS,
        "project": "curated:scala-tambore-campus:sgrutb11",
        "evidence": "scala-sgrutb11-current-portfolio-captured-2026-07-21",
        "lifecycle": (
            "under_construction",
            "2026-07-21",
            "authoritative_physical_status_update",
            0.95,
        ),
        "capacity": ("critical_it_mw", "design", 12.0),
        "scala": True,
    },
    "curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json": {
        "bytes": 6687,
        "sha256": "154ea1798c6926ac48d2528f0e2dbe5fd9651fa2b0f547b01e0e364acb13cb95",
        "campus": "curated:firebird-ai-center-hrazdan-site",
        "project": (
            "curated:firebird-ai-center-hrazdan-site:current-center-development"
        ),
        "evidence": (
            "armenia-firebird-hrazdan-progress-2026-06-05-captured-2026-07-21"
        ),
        "lifecycle": (
            "under_construction",
            "2026-06-05",
            "authoritative_physical_status_update",
            0.98,
        ),
        "capacity": None,
        "scala": False,
    },
    "curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json": {
        "bytes": 6583,
        "sha256": "dc887d47d91abbd7e53da238414cf387263569cded4079a0db04f3881c4c2b56",
        "campus": "curated:azerbaijan-undisclosed-new-data-center-site",
        "project": (
            "curated:azerbaijan-undisclosed-new-data-center-site:"
            "unnamed-new-data-center"
        ),
        "evidence": (
            "azerbaijan-new-data-center-construction-2026-06-30-captured-2026-07-21"
        ),
        "lifecycle": (
            "under_construction",
            "2026-06-30",
            "authoritative_physical_status_update",
            0.9,
        ),
        "capacity": None,
        "scala": False,
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        4720,
        "2b3f3711f46d9d07d2ca933665bf1c836b3ec75b2df499211e11fc6f6ec0bddc",
    ),
    "identity-and-capacity-guardrails.json": (
        4014,
        "6c97bfcc760b66dc1c1c2afcb9278c51a25a1cc7b520fce53c7b26e433c927c1",
    ),
    "manifest.json": (
        1423,
        "df5e44d95af1fe7b81c10f3d58006b4db6cbe68816aa502673b93c863c1b9750",
    ),
    "manifest.sha256": (
        80,
        "e6872684d61c27d0d52ca192d5555faa4fc7af5e99f0c1f25e8d4faaacc21493",
    ),
    "retrieval-inventory.json": (
        7603,
        "2988746fe11eb67e9daafe36189d4fd2e7a044bf8dc9908a722f7f8c7469338c",
    ),
    "rights-and-disposition.json": (
        1591,
        "4e15d3759fd1f9acde59066e4a337bc48f9c16d56a51d79a00e6016071a645c7",
    ),
    "source-snapshot.json": (
        8358,
        "f96206e36891819b224d936bdf5fe9fdd6931d92d1ffd9b86bab62c1a477a349",
    ),
}

NEW_CAPTURE_SPECS = {
    "scala_portfolio_failed_recapture": {
        "file_stem": "scala_portfolio",
        "http_status": 403,
        "contributes_evidence": False,
        "body": (
            75193,
            "ac4f780358ba4326a07c3a9bb83dff5a70cbb95a22be0f4c9385efe182cd722f",
        ),
        "headers": (
            238,
            "c7609a5e2e6936c8a0447e286ca4b5f672e5cd8e013038fa87032fef804f0182",
        ),
        "writeout": (
            11968,
            "892bd2af9edec0c684ed6caf33d048ed7d4f6f8624cc0db39be889482589f54d",
        ),
    },
    "firebird_hrazdan": {
        "file_stem": "firebird_hrazdan",
        "http_status": 200,
        "contributes_evidence": True,
        "body": (
            76155,
            "f5c8279b14e8b52fdc00aef7897c773ba3f4bf78f89d94566b8559271027de23",
        ),
        "headers": (
            575,
            "6f5ba7c9739fc0aa605600cd625ea89ce8f30d57b5e791c7885d4f644b9c7eb8",
        ),
        "writeout": (
            16370,
            "f398a6382ca13b285cb78920c391e7159c3c1d12256e18e4fe4af379e335d6cc",
        ),
    },
    "azerbaijan_government_cloud": {
        "file_stem": "azerbaijan_government_cloud",
        "http_status": 200,
        "contributes_evidence": True,
        "body": (
            130721,
            "1ae75d6a28d1fcdfd5d718e36ca3638660c1cca64918135dd3d90d52ca7eea7c",
        ),
        "headers": (
            273,
            "040036cdae1590921bafa1a3f10ff0b926f8f6af340a03e535a009682e597585",
        ),
        "writeout": (
            19306,
            "d834ec4d1519eedd0379a04a48395c7bdba23f40c2c89220b42b714d8f258998",
        ),
    },
}

REUSED_SCALA_CAPTURE = {
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
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SecondUnderrepresentedOfficialDiscoveryTests(unittest.TestCase):
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
            "entities": (
                "SELECT kind, stable_key, created_from_evidence_id, created_at "
                "FROM entities ORDER BY kind, stable_key"
            ),
            "evidence": (
                "SELECT id, kind, source_url, published_at, retrieved_at, "
                "content_hash, metadata_json FROM evidence ORDER BY id"
            ),
            "snapshots": (
                "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
                "tags_json, evidence_id, as_of_date, method, confidence "
                "FROM entity_snapshots JOIN entities "
                "ON entities.id = entity_snapshots.entity_id "
                "ORDER BY entities.stable_key, evidence_id"
            ),
            "lifecycle": (
                "SELECT entities.stable_key, status, evidence_id, as_of_date, method, "
                "confidence FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id "
                "ORDER BY entities.stable_key"
            ),
            "capacity": (
                "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                "method, confidence, evidence_id, as_of_date "
                "FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id "
                "ORDER BY entities.stable_key, metric, stage"
            ),
        }
        return {
            name: tuple(tuple(row) for row in connection.execute(query))
            for name, query in queries.items()
        }

    def _counts(self, connection) -> dict[str, int]:
        return {
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

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        documents = self._documents()
        self.assertEqual(len(documents), 5)
        self.assertEqual(len({spec["project"] for spec in SOURCE_SPECS.values()}), 5)
        self.assertEqual(len({spec["evidence"] for spec in SOURCE_SPECS.values()}), 5)
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
            self.assertIn(spec["evidence"], [row["key"] for row in document["evidence"]])
            self.assertEqual(document["project"]["evidence_key"], spec["evidence"])
            self.assertEqual(document["lifecycle"][0]["evidence_key"], spec["evidence"])
            self.assertTrue(
                all(row["license"] == "all-rights-reserved" for row in document["evidence"])
            )
            for entity in (document["campus"], document["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})

    def test_scala_shared_campus_and_evidence_are_exact_controlled_reuse(self) -> None:
        documents = self._documents()
        prior = json.loads(PRIOR_SCALA_SOURCE.read_text(encoding="utf-8"))
        shared_evidence = prior["evidence"][0]
        shared_bytes = json.dumps(
            shared_evidence, indent=2, ensure_ascii=False
        ).encode("utf-8")
        scala_names = [name for name, spec in SOURCE_SPECS.items() if spec["scala"]]
        self.assertEqual(len(scala_names), 3)
        for name in scala_names:
            document = documents[name]
            self.assertEqual(document["campus"], prior["campus"])
            self.assertEqual(document["evidence"][0], shared_evidence)
            self.assertEqual(
                json.dumps(
                    document["evidence"][0], indent=2, ensure_ascii=False
                ).encode("utf-8"),
                shared_bytes,
            )
            self.assertEqual(
                [row["key"] for row in document["evidence"]],
                [SHARED_CAMPUS_EVIDENCE, SOURCE_SPECS[name]["evidence"]],
            )
            self.assertEqual(document["campus"]["stable_key"], SHARED_CAMPUS)
            self.assertEqual(document["campus"]["evidence_key"], SHARED_CAMPUS_EVIDENCE)
            self.assertNotEqual(document["project"]["evidence_key"], SHARED_CAMPUS_EVIDENCE)

    def test_offline_import_is_exact_idempotent_order_independent_and_composable(self) -> None:
        order = list(SOURCE_SPECS)
        temporary, connection, results = self._import(order, repetitions=2)
        reverse_temporary, reverse_connection, reverse_results = self._import(
            reversed(order)
        )
        try:
            first, second = results[:5], results[5:]
            self.assertEqual(sum(row.entities_created for row in first), 8)
            self.assertEqual(sum(row.evidence_created for row in first), 6)
            self.assertEqual(sum(row.entities_created for row in second), 0)
            self.assertEqual(sum(row.evidence_created for row in second), 0)
            self.assertTrue(all(row.warnings == () for row in results))
            self.assertTrue(all(row.warnings == () for row in reverse_results))
            self.assertEqual(sum(row.entities_created for row in reverse_results), 8)
            self.assertEqual(sum(row.evidence_created for row in reverse_results), 6)
            self.assertEqual(validate_database(connection), [])
            self.assertEqual(validate_database(reverse_connection), [])
            self.assertEqual(
                self._semantic_snapshot(connection),
                self._semantic_snapshot(reverse_connection),
            )
            self.assertEqual(
                self._counts(connection),
                {
                    "entities": 8,
                    "evidence": 6,
                    "entity_snapshots": 8,
                    "lifecycle_observations": 5,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 3,
                },
            )
        finally:
            connection.close()
            temporary.cleanup()
            reverse_connection.close()
            reverse_temporary.cleanup()

        combined_orders = (
            [PRIOR_SCALA_SOURCE.name, *order],
            [*reversed(order), PRIOR_SCALA_SOURCE.name],
        )
        combined_snapshots = []
        for combined_order in combined_orders:
            combined_temporary, combined_connection, combined_results = self._import(
                combined_order,
                repetitions=2,
            )
            try:
                first_count = len(combined_order)
                self.assertEqual(
                    sum(row.entities_created for row in combined_results[:first_count]),
                    9,
                )
                self.assertEqual(
                    sum(row.evidence_created for row in combined_results[:first_count]),
                    6,
                )
                self.assertEqual(
                    sum(row.entities_created for row in combined_results[first_count:]),
                    0,
                )
                self.assertEqual(
                    sum(row.evidence_created for row in combined_results[first_count:]),
                    0,
                )
                self.assertEqual(
                    self._counts(combined_connection),
                    {
                        "entities": 9,
                        "evidence": 6,
                        "entity_snapshots": 9,
                        "lifecycle_observations": 6,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 4,
                    },
                )
                self.assertEqual(validate_database(combined_connection), [])
                combined_snapshots.append(self._semantic_snapshot(combined_connection))
            finally:
                combined_connection.close()
                combined_temporary.cleanup()
        self.assertEqual(combined_snapshots[0], combined_snapshots[1])

    def test_currentness_identity_roles_and_physical_status_are_exact(self) -> None:
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

        scala_names = [name for name, spec in SOURCE_SPECS.items() if spec["scala"]]
        for name in scala_names:
            document = documents[name]
            metadata = document["evidence"][1]["metadata"]
            self.assertEqual(metadata["portfolio_section_as_reported"], "Under construction")
            self.assertIn(
                "Ongoing Civil Works",
                metadata["under_construction_definition_as_reported"],
            )
            self.assertIn("stale", metadata["forecast_guardrail"])
            self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-07-21")
        self.assertIn(
            "also names SGRUTB09",
            documents[scala_names[0]]["evidence"][1]["metadata"]["map_crosscheck_scope"],
        )
        for name in scala_names[1:]:
            self.assertIn(
                "omits",
                documents[name]["evidence"][1]["metadata"]["map_crosscheck_guardrail"],
            )

        firebird = documents[
            "curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json"
        ]
        firebird_metadata = firebird["evidence"][0]["metadata"]
        self.assertEqual(firebird["evidence"][0]["published_at"], "2026-06-05")
        self.assertEqual(firebird["lifecycle"][0]["as_of_date"], "2026-06-05")
        self.assertIn("July current status remains independently unverified", firebird_metadata["currentness_scope"])
        self.assertEqual(
            (
                firebird_metadata["capacity_mw_untyped_as_reported"],
                firebird_metadata["phase_one_gpu_count_more_than_as_reported"],
                firebird_metadata["phase_two_additional_gpu_count_more_than_as_reported"],
                firebird_metadata["compute_fp4_tensor_exaflops_up_to_as_reported"],
            ),
            (18, 6000, 41000, 110.6),
        )

        azerbaijan = documents[
            "curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json"
        ]
        azerbaijan_metadata = azerbaijan["evidence"][0]["metadata"]
        self.assertEqual(azerbaijan["evidence"][0]["published_at"], "2026-06-30")
        self.assertIsNone(azerbaijan["campus"]["address"])
        self.assertIsNone(azerbaijan["project"]["address"])
        self.assertNotIn("government-cloud", azerbaijan["project"]["stable_key"])
        self.assertIn("not linked or merged", azerbaijan_metadata["identity_guardrail"])
        self.assertIn("adjacent program context only", azerbaijan_metadata["government_cloud_guardrail"])

    def test_capacity_workload_hardware_and_type_boundaries_are_exact(self) -> None:
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
                    "('gross_facility_mw', 'grid_connection_mw', "
                    "'generation_nameplate_mw', 'annual_energy_mwh', 'pue')"
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
        for name, spec in SOURCE_SPECS.items():
            document = documents[name]
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(len(document["capacities"]), int(spec["capacity"] is not None))

    def test_v67_boundary_and_controlled_source_tree_reuse_are_exact(self) -> None:
        v67 = json.loads(V67_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(len(v67["curated_inputs"]), 378)
        v67_paths = {row["path"] for row in v67["curated_inputs"]}
        proposed_paths = {f"sources/{name}" for name in SOURCE_SPECS}
        self.assertTrue(proposed_paths.isdisjoint(v67_paths))

        prior = json.loads(PRIOR_SCALA_SOURCE.read_text(encoding="utf-8"))
        new_projects = {spec["project"] for spec in SOURCE_SPECS.values()}
        new_facility_evidence = {spec["evidence"] for spec in SOURCE_SPECS.values()}
        new_unshared_campuses = {
            spec["campus"]
            for spec in SOURCE_SPECS.values()
            if spec["campus"] != SHARED_CAMPUS
        }
        other_projects: set[str] = set()
        other_campuses: set[str] = set()
        other_evidence: set[str] = set()
        shared_campus_paths: set[str] = set()
        shared_evidence_paths: set[str] = set()
        for path in (ROOT / "sources").glob("*.json"):
            if path.name in SOURCE_SPECS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            campus = document.get("campus")
            if isinstance(campus, dict) and isinstance(campus.get("stable_key"), str):
                other_campuses.add(campus["stable_key"])
                if campus["stable_key"] == SHARED_CAMPUS:
                    self.assertEqual(campus, prior["campus"])
                    shared_campus_paths.add(path.name)
            project = document.get("project")
            if isinstance(project, dict) and isinstance(project.get("stable_key"), str):
                other_projects.add(project["stable_key"])
            evidence = document.get("evidence")
            if isinstance(evidence, list):
                for row in evidence:
                    if not isinstance(row, dict) or not isinstance(row.get("key"), str):
                        continue
                    other_evidence.add(row["key"])
                    if row["key"] == SHARED_CAMPUS_EVIDENCE:
                        self.assertEqual(row, prior["evidence"][0])
                        shared_evidence_paths.add(path.name)

        self.assertTrue(new_projects.isdisjoint(other_projects))
        self.assertTrue(new_facility_evidence.isdisjoint(other_evidence))
        self.assertTrue(new_unshared_campuses.isdisjoint(other_campuses))
        self.assertEqual(shared_campus_paths, {PRIOR_SCALA_SOURCE.name})
        self.assertEqual(shared_evidence_paths, {PRIOR_SCALA_SOURCE.name})
        self.assertIn(SHARED_CAMPUS, other_campuses)
        self.assertIn(SHARED_CAMPUS_EVIDENCE, other_evidence)
        self.assertEqual(len(new_projects), 5)
        self.assertEqual(len(new_facility_evidence), 5)

        self.assertEqual(
            (len(V67_DEFINITION.read_bytes()), sha256(V67_DEFINITION)),
            (
                83386,
                "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5",
            ),
        )
        self.assertEqual(
            (len(V67_MANIFEST.read_bytes()), sha256(V67_MANIFEST)),
            (
                12274,
                "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb",
            ),
        )

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
            manifest["tree_sha256"],
            "1a918b5045f90dbe7c6c66f9229fd7668bcb04979def38677d000017997c8cff",
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )

        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            (
                inventory["direct_request_attempts"],
                inventory["successful_http_requests"],
                inventory["failed_http_requests"],
                inventory["reused_successful_captures"],
                inventory["evidence_supporting_captures"],
            ),
            (3, 2, 1, 1, 3),
        )
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        requests = {row["request_id"]: row for row in inventory["controlled_http_requests"]}
        self.assertEqual(set(requests), set(NEW_CAPTURE_SPECS))
        for request_id, spec in NEW_CAPTURE_SPECS.items():
            request = requests[request_id]
            self.assertEqual(request["http_status"], spec["http_status"])
            self.assertEqual(request["contributes_evidence"], spec["contributes_evidence"])
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

        reused_records = inventory["reused_evidence_capture_records"]
        self.assertEqual(len(reused_records), 1)
        reused = reused_records[0]
        self.assertEqual(reused["http_status"], 200)
        self.assertTrue(reused["raw_capture_reused_by_hash_only"])
        for key, record_key in (
            ("body", "body"),
            ("headers", "headers"),
            ("writeout", "curl_writeout"),
        ):
            self.assertEqual(
                (reused[record_key]["bytes"], reused[record_key]["sha256"]),
                REUSED_SCALA_CAPTURE[key],
            )
        self.assertEqual(
            set(reused["evidence_keys"]),
            {SHARED_CAMPUS_EVIDENCE}
            | {spec["evidence"] for spec in SOURCE_SPECS.values() if spec["scala"]},
        )

        forbidden_suffixes = {".body", ".headers", ".html", ".pdf", ".png", ".jpg"}
        self.assertTrue(
            all(path.suffix not in forbidden_suffixes for path in ARTIFACT.iterdir())
        )
        original = Path(inventory["temporary_capture_directory_original_path"])
        trash = Path(inventory["temporary_capture_trash_path"])
        self.assertFalse(original.exists())
        self.assertTrue(trash.is_dir())
        self.assertEqual(trash.name, "dc-second-underrepresented-20260721.neWRig")
        for spec in NEW_CAPTURE_SPECS.values():
            for suffix, capture_key in (
                ("body", "body"),
                ("headers", "headers"),
                ("writeout.json", "writeout"),
            ):
                path = trash / f"{spec['file_stem']}.{suffix}"
                self.assertEqual(
                    (len(path.read_bytes()), sha256(path)),
                    spec[capture_key],
                )

        reused_trash = Path(reused["source_trash_path"])
        if reused_trash.is_dir():
            for suffix, capture_key in (
                ("body", "body"),
                ("headers", "headers"),
                ("writeout.json", "writeout"),
            ):
                path = reused_trash / f"scala_portfolio.{suffix}"
                self.assertEqual(
                    (len(path.read_bytes()), sha256(path)),
                    REUSED_SCALA_CAPTURE[capture_key],
                )

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            snapshot["totals"],
            {
                "source_records": 5,
                "distinct_campuses": 3,
                "projects": 5,
                "unique_evidence_records": 6,
                "facility_evidence_records": 5,
                "shared_campus_evidence_records": 1,
                "entity_snapshots": 8,
                "lifecycle_observations": 5,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 3,
                "coordinates_present": 0,
                "geometry_present": 0,
            },
        )
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        decisions = {row["decision"] for row in snapshot["bounded_discovery_exclusions"]}
        self.assertEqual(
            decisions,
            {
                "duplicate_not_added",
                "historical_only_current_unknown",
                "identity_or_status_ambiguous",
                "not_current_build",
                "not_promoted",
            },
        )


if __name__ == "__main__":
    unittest.main()
