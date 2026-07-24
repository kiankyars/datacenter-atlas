from __future__ import annotations

import copy
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
V1_NAME = "curated-official-2026-07-20-digipower-columbiana-shell.json"
V2_NAME = "curated-official-2026-07-20-digipower-columbiana-shell-v2.json"
V1_PATH = ROOT / "sources" / V1_NAME
V2_PATH = ROOT / "sources" / V2_NAME
V1_BYTES = 13_473
V1_SHA256 = "7728f26d064c0ec3a47ac34aa60fdb635770a7b49e2fa90c4a0de91ca91e2ace"
V2_BYTES = 13_477
V2_SHA256 = "a137bd6356ead2052ad160aa50c7ab27d7871f4b2552dba276ffa86949f46ccd"
OLD_PHYSICAL_WORK = (
    "site and civil work completed or superseded for the active shell scope"
)
NEW_PHYSICAL_WORK = (
    "project is transitioning from site and civil work to vertical construction"
)
PDF_URL = (
    "https://thankful-miracle-1ed8bdfdaf.media.strapiapp.com/"
    "Digi_Power_X_Provides_Operations_and_Financial_Update_4a179c433b.pdf"
)
EVIDENCE_KEY = (
    "digipower-columbiana-shell-update-2026-07-07-captured-2026-07-20"
)
CAMPUS_KEY = "curated:digipowerx-columbiana-ai-data-center-campus"
PROJECT_KEY = (
    "curated:digipowerx-columbiana-ai-data-center-campus:"
    "purpose-built-flagship-vertical-build"
)
RETRIEVED_AT = "2026-07-20T08:30:56Z"
AS_OF_DATE = "2026-07-07"


class DigiPowerColumbianaShellV2CuratedTests(unittest.TestCase):
    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Digi Power X v2 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _normalized_state(
        self,
        source_path: Path,
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=RETRIEVED_AT,
                        )
                        self.assertEqual(result.warnings, ())
                        self.assertEqual(result.entities_created, 2 if iteration == 0 else 0)
                        self.assertEqual(result.evidence_created, 1 if iteration == 0 else 0)
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, metric, stage, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id",
                    "SELECT entities.stable_key, operating_model, as_of_date, "
                    "recorded_at, method, confidence "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id",
                    "SELECT entities.stable_key, workload, as_of_date, recorded_at, "
                    "method, confidence FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_original_source_pin_is_unchanged(self) -> None:
        self.assertTrue(V1_PATH.is_file())
        self.assertFalse(V1_PATH.is_symlink())
        self.assertTrue(stat.S_ISREG(V1_PATH.stat().st_mode))
        self.assertEqual(stat.S_IMODE(V1_PATH.stat().st_mode), 0o644)
        self.assertEqual(V1_PATH.stat().st_size, V1_BYTES)
        self.assertEqual(hashlib.sha256(V1_PATH.read_bytes()).hexdigest(), V1_SHA256)

    def test_v2_source_is_canonical_regular_mode_and_byte_pinned(self) -> None:
        self.assertTrue(V2_PATH.is_file())
        self.assertFalse(V2_PATH.is_symlink())
        self.assertTrue(stat.S_ISREG(V2_PATH.stat().st_mode))
        self.assertEqual(stat.S_IMODE(V2_PATH.stat().st_mode), 0o644)
        self.assertEqual(V2_PATH.stat().st_size, V2_BYTES)
        self.assertEqual(hashlib.sha256(V2_PATH.read_bytes()).hexdigest(), V2_SHA256)
        text = V2_PATH.read_text(encoding="utf-8")
        document = json.loads(text)
        self.assertEqual(text, json.dumps(document, indent=2, ensure_ascii=False) + "\n")

    def test_v2_has_exactly_one_source_faithful_metadata_delta(self) -> None:
        original = self._load(V1_PATH)
        corrected = self._load(V2_PATH)
        physical_work = original["evidence"][0]["metadata"]["reported_physical_work"]
        self.assertEqual(physical_work[0], OLD_PHYSICAL_WORK)

        expected = copy.deepcopy(original)
        expected["evidence"][0]["metadata"]["reported_physical_work"][0] = (
            NEW_PHYSICAL_WORK
        )
        self.assertEqual(corrected, expected)

    def test_v2_makes_no_completion_or_superseded_inference(self) -> None:
        document = self._load(V2_PATH)
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["reported_physical_work"],
            [
                NEW_PHYSICAL_WORK,
                "building shell being erected",
                "vertical construction underway",
            ],
        )
        for observation in metadata["reported_physical_work"]:
            folded = observation.casefold()
            self.assertNotIn("completed", folded)
            self.assertNotIn("superseded", folded)
        self.assertNotIn(OLD_PHYSICAL_WORK, V2_PATH.read_text(encoding="utf-8"))
        self.assertIn(
            "does not establish shell completion",
            metadata["construction_scope"],
        )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )

    def test_v2_offline_import_is_exact_idempotent_and_matches_v1_outputs(self) -> None:
        original_state = self._normalized_state(V1_PATH)
        corrected_state = self._normalized_state(V2_PATH)
        self.assertEqual(corrected_state, original_state)
        self.assertEqual(self._normalized_state(V2_PATH, repetitions=2), corrected_state)

        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = (
            corrected_state
        )
        self.assertEqual(
            entities,
            (
                ("campus", CAMPUS_KEY, RETRIEVED_AT),
                ("project", PROJECT_KEY, RETRIEVED_AT),
            ),
        )
        self.assertEqual(
            evidence,
            ((
                EVIDENCE_KEY,
                "ebcddc3bc3e8d35325e56fe7b81803a90a3a69938d1451401051f8eea135f734",
                RETRIEVED_AT,
                PDF_URL,
            ),),
        )
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual(
            lifecycle,
            ((
                PROJECT_KEY,
                "shell",
                AS_OF_DATE,
                RETRIEVED_AT,
                "authoritative_physical_status_update",
                0.99,
            ),),
        )
        self.assertEqual(capacities, ())
        self.assertEqual(
            models,
            ((PROJECT_KEY, "colocation", AS_OF_DATE, RETRIEVED_AT, "company_disclosure", 0.95),),
        )
        self.assertEqual(
            workloads,
            ((
                PROJECT_KEY,
                "ai_specialized_unspecified",
                AS_OF_DATE,
                RETRIEVED_AT,
                "company_disclosure",
                0.99,
            ),),
        )
        self.assertEqual(projects, ((PROJECT_KEY, CAMPUS_KEY),))


if __name__ == "__main__":
    unittest.main()
