from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.external_captures import resolve_external_capture
from datacenter_atlas.service import validate_database
from datacenter_atlas.tests.test_coordinate_assessment_2026_07_21_v2 import (
    COHORT,
    SPECS as PREVIOUS_SPECS,
    TABLES,
    UNRESOLVED_REASONS,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v3"
INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-temporal-incident-"
    "2026-07-21-v1"
)
V1_INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-publication-incident-"
    "2026-07-21-v1"
)
V2 = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v2"
BUILDER = ROOT / "scripts/build_coordinate_assessment_2026_07_21_v3.py"
CAPTURE = Path(
    "/Users/kian/.Trash/datacenter-atlas-v68-coordinate-capture-"
    "20260721-1707Z-y0NdsP"
)
MANIFEST_RECORDED_AT = "2026-07-21T09:55:47.489508Z"
IMPORT_RECORDED_AT = "2026-07-21T09:55:48Z"

SPECS = copy.deepcopy(PREVIOUS_SPECS)
SPECS["lampa"].update(
    successor=SPECS["lampa"]["successor"].replace("coordinate-v2", "coordinate-v3"),
    bytes=13_780,
    sha256="970e17532a3210b72e7c5cae376302feeefbfe13b9ae059b934b693f4a7a8391",
    retrieved_at="2026-07-21T09:26:39Z",
)
SPECS["huechuraba"].update(
    successor=SPECS["huechuraba"]["successor"].replace(
        "coordinate-v2", "coordinate-v3"
    ),
    bytes=13_559,
    sha256="1bcb03a404f927e628cd1e99dab6a3505bea18312b694143911002da4970487f",
    retrieved_at="2026-07-21T09:26:39Z",
)
SPECS["fortaleza"].update(
    successor=SPECS["fortaleza"]["successor"].replace(
        "coordinate-v2", "coordinate-v3"
    ),
    bytes=13_434,
    sha256="c685989acf5fb9d405c6803f79457de930fb90e6b57a5780cbf903a876a12e6f",
    retrieved_at="2026-07-21T09:27:36Z",
)

V3_FILES = {
    "README.md": (1_357, "66d6536dccb65b795f172ee4e1107c681b03ed1d5941ed342c6a6dd407abe54a"),
    "coordinate-observations.json": (3_034, "c9ab47f95395f6f176f46b44b038433af6c2b88f7e23a077565d158ead725868"),
    "disposition.json": (10_461, "8cc0ce5f2d81a8233555cc89e9e149dd18c9eaf8bdc64036f3b63d42995d6322"),
    "manifest.json": (1_834, "acb675580c993e3af150f8a3e25f53a8d66a6d7b595b644088a84f1294acd43d"),
    "manifest.sha256": (80, "e88ce5748c8a41fd84c1d4959d2ef42b70d3a02dd29892aa6292f52d18b03e91"),
    "normalized-successors/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build-coordinate-v3.json": (13_434, "c685989acf5fb9d405c6803f79457de930fb90e6b57a5780cbf903a876a12e6f"),
    "normalized-successors/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build-coordinate-v3.json": (13_559, "1bcb03a404f927e628cd1e99dab6a3505bea18312b694143911002da4970487f"),
    "normalized-successors/curated-official-2026-07-21-scala-sscllp01-lampa-current-build-coordinate-v3.json": (13_780, "970e17532a3210b72e7c5cae376302feeefbfe13b9ae059b934b693f4a7a8391"),
    "retrieval-inventory.json": (8_368, "114d3bd7052cd953d050f6b7208beb414f8a893421979dc522aba2dbe0443e96"),
}

INCIDENT_FILES = {
    "README.md": (639, "130fcbfa542a2e9daf0df610196caf1e1dcfcebdc965473bb68e11981bd8353a"),
    "incident.json": (7_449, "5e11602c7b6c874ac3264b792cfaa11718eb4bc416af95801db99fb39be629d8"),
    "manifest.json": (799, "2812b326ca373c74d83d28278ea52780fd68da47ecb275b9027c6d91380ef930"),
    "manifest.sha256": (80, "8298378e37f8790c92f57529b30d7fd023f8ec76d7d44848f94c3dd4865663a9"),
}


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


class CoordinateAssessmentV3Tests(unittest.TestCase):
    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in TABLES
        }

    def _build(
        self, paths: Iterable[Path], *, repeat: bool = False
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                paths = tuple(paths)
                with self._network_guard():
                    for path in paths:
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection, path, recorded_at=IMPORT_RECORDED_AT
                        )
                    state = self._state(connection)
                    if repeat:
                        for path in paths:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection, path, recorded_at=IMPORT_RECORDED_AT
                            )
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                        self.assertEqual(self._state(connection), state)
                self.assertEqual(validate_database(connection), [])
                return state
            finally:
                connection.close()

    def _assert_bundle(
        self,
        root: Path,
        expected: dict[str, tuple[int, str]],
        *,
        tree_sha256: str,
        recorded_at: str,
        stage_birth_at: str,
    ) -> None:
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o555)
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, set(expected))
        for relative, (size, digest) in expected.items():
            path = root / relative
            raw = path.read_bytes()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (size, digest))
            if path.suffix == ".json":
                document = json.loads(raw)
                self.assertEqual(
                    raw,
                    (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(),
                )
        for path in root.rglob("*"):
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555)
        manifest = self._load(root / "manifest.json")
        self.assertEqual(manifest["recorded_at"], recorded_at)
        self.assertEqual(manifest["publication"]["stage_birth_at"], stage_birth_at)
        self.assertEqual(manifest["tree_sha256"], tree_sha256)
        self.assertEqual(
            hashlib.sha256(
                (
                    json.dumps(manifest["files"], indent=2, ensure_ascii=False) + "\n"
                ).encode()
            ).hexdigest(),
            tree_sha256,
        )
        stage = _instant(stage_birth_at)
        recorded = _instant(recorded_at)
        artifact_birth = datetime.fromtimestamp(root.stat().st_birthtime, timezone.utc)
        self.assertLessEqual(stage, recorded)
        self.assertLessEqual(artifact_birth, recorded)
        self.assertLessEqual(recorded, datetime.now(timezone.utc))
        self.assertEqual(
            (root / "manifest.sha256").read_text(),
            f"{expected['manifest.json'][1]}  manifest.json\n",
        )

    def test_frozen_recorded_manifests_and_all_temporal_values_are_nonfuture(self) -> None:
        self._assert_bundle(
            ARTIFACT,
            V3_FILES,
            tree_sha256="aeaebd102f00c4e6b25ff4b86e15d2c88ad3b1fbe8d23cc216c4f0c57995a6b2",
            recorded_at=MANIFEST_RECORDED_AT,
            stage_birth_at="2026-07-21T09:55:47.489483Z",
        )
        self._assert_bundle(
            INCIDENT,
            INCIDENT_FILES,
            tree_sha256="6525e60fc718471e1550562e493ecded668dfe115c982ed37e53bdb1fad9c260",
            recorded_at="2026-07-21T09:55:47.487842Z",
            stage_birth_at="2026-07-21T09:55:47.487806Z",
        )
        recorded = _instant(MANIFEST_RECORDED_AT)
        for label, spec in SPECS.items():
            document = self._load(ARTIFACT / "normalized-successors" / spec["successor"])
            self.assertTrue(all(_instant(row["retrieved_at"]) <= recorded for row in document["evidence"]))
            added = document["evidence"][-1]
            self.assertEqual(added["retrieved_at"], spec["retrieved_at"], label)
            self.assertNotIn("response_http_date", added["metadata"])
            self.assertIn("server_response_http_date_as_reported", added["metadata"])
            self.assertIn("retrieval_time_basis", added["metadata"])
        inventory = self._load(ARTIFACT / "retrieval-inventory.json")
        self.assertEqual(inventory["publication_recorded_at"], MANIFEST_RECORDED_AT)
        self.assertTrue(
            all(
                _instant(request["retrieved_at"]) <= recorded
                for request in inventory["accepted_capture_requests"]
            )
        )
        self.assertEqual(
            {row["request_id"]: row["retrieved_at"] for row in inventory["accepted_capture_requests"]},
            {
                "chile_simbio_region_13_seia": "2026-07-21T09:26:39Z",
                "chile_simbio_region_context": "2026-07-21T09:27:17Z",
                "fortaleza_sforpf01_site_plan": "2026-07-21T09:27:36Z",
            },
        )

    def test_temporal_incident_pins_v2_and_exact_local_capture_witness(self) -> None:
        incident = self._load(INCIDENT / "incident.json")
        self.assertEqual(incident["acceptance"], "non_accepted")
        rejected = incident["rejected_v2"]
        self.assertEqual(rejected["manifest_sha256"], "5b2e8c6d4ea3638ffb75ed3f00b4cdf672c2aaca04fd8fc899a4633506b09024")
        self.assertEqual(rejected["tree_sha256"], "d104bd68bdb7e3d9fec7d748f639cad51f96a8a3421c0378ba0d86e6e294a1ca")
        self.assertEqual(rejected["files"], self._load(V2 / "manifest.json")["files"])
        self.assertEqual(
            hashlib.sha256((V2 / "manifest.json").read_bytes()).hexdigest(),
            rejected["manifest_sha256"],
        )
        invalid = incident["invalid_temporal_metadata"]
        self.assertEqual(invalid["v2_retrieved_at"], "2026-07-21T17:05:51Z")
        self.assertLess(_instant(invalid["artifact_birth_at"]), _instant(invalid["v2_retrieved_at"]))
        self.assertIn("never cure", invalid["passage_of_time_guardrail"])
        self.assertFalse(incident["containment"]["v2_accepted"])
        self.assertTrue(incident["containment"]["v1_remains_rejected"])
        self.assertEqual(
            incident["containment"]["v1_publication_incident_manifest_sha256"],
            hashlib.sha256((V1_INCIDENT / "manifest.json").read_bytes()).hexdigest(),
        )

        witness = incident["truthful_capture_witness"]
        self.assertEqual(witness["capture_tree_sha256"], "25e73755344fb8e6db9ef32b6f1f967afc4a8db8f9e714971f00a1b8685adf49")
        rows = bytearray()
        capture_root = resolve_external_capture(CAPTURE)
        paths = sorted(path for path in capture_root.rglob("*") if path.is_file())
        self.assertEqual(len(paths), 79)
        self.assertEqual(sum(path.stat().st_size for path in paths), 57_610_841)
        for path in paths:
            relative = path.relative_to(capture_root).as_posix()
            rows.extend(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{relative}\n".encode()
            )
        self.assertEqual(hashlib.sha256(rows).hexdigest(), witness["capture_tree_sha256"])
        for capture_id in ("simbio_seia", "simbio_context", "fortaleza_site_plan"):
            capture = witness[capture_id]
            self.assertEqual(
                int(_instant(capture["local_capture_completed_at"]).timestamp()),
                capture["completion_mtime_epoch"],
            )
            for carrier in ("body", "headers", "curl_writeout"):
                expected = capture[carrier]
                path = capture_root / expected["capture_name"]
                self.assertEqual(path.stat().st_size, expected["bytes"])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
                if capture_root == CAPTURE:
                    self.assertEqual(
                        int(path.stat().st_birthtime),
                        expected["birth_epoch"],
                    )
                self.assertEqual(int(path.stat().st_mtime), expected["mtime_epoch"])

    def test_direct_pins_partition_geometry_and_coordinate_only_delta(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])
        rejected = {row["path"]: row["reason"] for row in disposition["lineage"]["rejected_as_lineage"]}
        self.assertEqual(rejected["source_artifacts/site-coordinate-assessment-2026-07-21-v2"], "rejected_future_retrieved_at_metadata_at_publication")
        self.assertFalse(disposition["publication_integrity"]["v1_accepted"])
        self.assertFalse(disposition["publication_integrity"]["v2_accepted"])

        cohort_rows = {Path(row["path"]).name: row for row in disposition["cohort"]["rows"]}
        self.assertEqual(set(cohort_rows), set(COHORT))
        for name, (size, digest) in COHORT.items():
            path = ROOT / "sources" / name
            self.assertEqual((path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()), (size, digest))

        for label, spec in SPECS.items():
            predecessor = self._load(ROOT / "sources" / spec["predecessor"])
            path = ARTIFACT / "normalized-successors" / spec["successor"]
            successor = self._load(path)
            self.assertEqual((path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()), (spec["bytes"], spec["sha256"]))
            self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
            restored = copy.deepcopy(successor)
            restored["evidence"] = copy.deepcopy(predecessor["evidence"])
            for entity_name in ("campus", "project"):
                before = predecessor[entity_name]
                after = successor[entity_name]
                changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)}
                self.assertEqual(changed, {"coordinates", "geometry", "evidence_key", "method"})
                self.assertEqual(after["coordinates"], spec["coordinates"])
                expected_geometry = (
                    spec.get("project_geometry", spec["geometry"])
                    if entity_name == "project"
                    else spec["geometry"]
                )
                self.assertEqual(after["geometry"], expected_geometry)
                for key in changed:
                    restored[entity_name][key] = copy.deepcopy(before[key])
            for section in ("lifecycle", "operating_models", "workloads", "capacities"):
                self.assertEqual(successor[section], predecessor[section])
            self.assertEqual(restored, predecessor)
            self.assertFalse((ROOT / "sources" / spec["successor"]).exists())

        fortaleza = self._load(
            ARTIFACT / "normalized-successors" / SPECS["fortaleza"]["successor"]
        )
        ring = fortaleza["project"]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(fortaleza["campus"]["geometry"]["type"], "Point")
        self.assertEqual(fortaleza["project"]["geometry"]["type"], "Polygon")

        unresolved = {row["campus_key"]: row for row in disposition["unresolved"]["rows"]}
        self.assertEqual((disposition["unresolved"]["campuses"], disposition["unresolved"]["projects"]), (7, 10))
        self.assertEqual({key: row["reason"] for key, row in unresolved.items()}, UNRESOLVED_REASONS)
        self.assertEqual(sum(len(row["project_keys"]) for row in unresolved.values()), 10)

    def test_offline_import_is_idempotent_order_independent_and_collision_safe(self) -> None:
        paths = tuple(
            ARTIFACT / "normalized-successors" / spec["successor"]
            for spec in SPECS.values()
        )
        for path in paths:
            with self.subTest(source=path.name):
                state = self._build((path,), repeat=True)
                self.assertEqual(len(state["evidence"]), 2)
                self.assertEqual(len(state["entities"]), 2)
                self.assertEqual(len(state["entity_snapshots"]), 2)
        forward = self._build(paths, repeat=True)
        reverse = self._build(reversed(paths), repeat=True)
        self.assertEqual(reverse, forward)
        self.assertEqual(
            {table: len(rows) for table, rows in forward.items()},
            {
                "evidence": 6,
                "entities": 6,
                "campuses": 3,
                "facilities": 0,
                "buildings": 0,
                "projects": 3,
                "entity_snapshots": 6,
                "administrative_assignments": 0,
                "lifecycle_observations": 3,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 3,
            },
        )

        for label, spec in SPECS.items():
            predecessor = ROOT / "sources" / spec["predecessor"]
            successor = ARTIFACT / "normalized-successors" / spec["successor"]
            for first, second in ((predecessor, successor), (successor, predecessor)):
                with self.subTest(site=label, first=first.name):
                    with tempfile.TemporaryDirectory() as temporary:
                        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                        try:
                            with self._network_guard():
                                CuratedOfficialSourceAdapterV11().import_file(
                                    connection, first, recorded_at=IMPORT_RECORDED_AT
                                )
                                before = self._state(connection)
                                with self.assertRaisesRegex(ValueError, "entity_snapshots already has a claim"):
                                    CuratedOfficialSourceAdapterV11().import_file(
                                        connection,
                                        second,
                                        recorded_at=IMPORT_RECORDED_AT,
                                    )
                            self.assertEqual(self._state(connection), before)
                            self.assertEqual(validate_database(connection), [])
                        finally:
                            connection.close()

    def test_import_and_builder_future_guards_fail_closed(self) -> None:
        too_early = "2026-07-21T09:26:38Z"
        for spec in SPECS.values():
            path = ARTIFACT / "normalized-successors" / spec["successor"]
            with tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._network_guard():
                        with self.assertRaisesRegex(
                            ValueError,
                            r"evidence\[1\]\.retrieved_at must not be later than the import recorded_at",
                        ):
                            CuratedOfficialSourceAdapterV11().import_file(
                                connection, path, recorded_at=too_early
                            )
                    for table in TABLES:
                        self.assertEqual(
                            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                            0,
                        )
                finally:
                    connection.close()

        scripts = str(BUILDER.parent)
        sys.path.insert(0, scripts)
        try:
            module_spec = importlib.util.spec_from_file_location(
                "coordinate_assessment_v3_builder_future_test", BUILDER
            )
            assert module_spec is not None and module_spec.loader is not None
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts)
        manifest = self._load(ARTIFACT / "manifest.json")
        payloads = module._v3_payloads(
            recorded_at=manifest["recorded_at"],
            stage_birth_at=manifest["publication"]["stage_birth_at"],
            incident_manifest_sha256=INCIDENT_FILES["manifest.json"][1],
        )
        document_path = next(
            relative for relative in payloads if relative.endswith("coordinate-v3.json")
        )
        document = json.loads(payloads[document_path])
        document["evidence"][-1]["retrieved_at"] = "2026-07-21T17:05:51Z"
        payloads[document_path] = (
            json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        ).encode()
        with self.assertRaisesRegex(module.TemporalPublicationError, "future evidence"):
            module._validate_temporal_payloads(
                payloads,
                recorded_at=manifest["recorded_at"],
                stage_birth_at=manifest["publication"]["stage_birth_at"],
            )

    def test_builder_is_read_only_idempotent_no_replace_and_leaves_no_stage(self) -> None:
        protected = (V1_INCIDENT, V2, INCIDENT, ARTIFACT)
        before = {
            path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for root in protected
            for path in root.rglob("*")
            if path.is_file()
        }
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"assessment": "existing-identical", "incident": "existing-identical"},
        )
        after = {
            path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for root in protected
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

        scripts = str(BUILDER.parent)
        sys.path.insert(0, scripts)
        try:
            module_spec = importlib.util.spec_from_file_location(
                "coordinate_assessment_v3_builder_collision_test", BUILDER
            )
            assert module_spec is not None and module_spec.loader is not None
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts)
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            publication_root = Path(temporary)
            self.assertEqual(
                module.publish_all(publication_root),
                {"incident": "published", "assessment": "published"},
            )
            self.assertEqual(
                module.publish_all(publication_root),
                {"incident": "existing-identical", "assessment": "existing-identical"},
            )

        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            collision = Path(temporary) / module.ARTIFACT_ID
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_bytes(b"do-not-overwrite\n")
            with self.assertRaises(
                (KeyError, FileNotFoundError, module.TemporalPublicationError)
            ):
                module._publish_dynamic(collision, lambda _recorded, _birth: {})
            self.assertEqual(sentinel.read_bytes(), b"do-not-overwrite\n")

        stages = [
            path
            for path in (ROOT / "source_artifacts").iterdir()
            if path.name.startswith(f".{module.ARTIFACT_ID}.stage-")
            or path.name.startswith(f".{module.INCIDENT_ID}.stage-")
        ]
        self.assertEqual(stages, [])


if __name__ == "__main__":
    unittest.main()
