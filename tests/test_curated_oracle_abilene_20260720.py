from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAME = "curated-official-2026-07-20-lancium-crusoe-oracle-abilene.json"
SOURCE = ROOT / "sources" / SOURCE_NAME
SOURCE_BYTES = 26_322
SOURCE_SHA256 = "bffd47864bb2d013caff5c8888974c761ca5abe3a03025f3b19c90d52fb92eaa"
RETRIEVED_AT = "2026-07-21T06:07:08Z"
ARTIFACT = ROOT / "source_artifacts" / "oracle-abilene-official-2026-07-20-v1"
V64_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v64.json"
V64_DEFINITION_SHA256 = (
    "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e"
)

CAMPUS_KEY = "curated:lancium-clean-campus-abilene-ai-data-center"
PROJECT_KEY = f"{CAMPUS_KEY}:remaining-six-building-expansion"
PORTFOLIO_KEY = "oracle-abilene-portfolio-status-captured-2026-07-20"
FACTS_KEY = "oracle-abilene-facts-captured-2026-07-20"
CRUSOE_KEY = (
    "crusoe-abilene-phase-2-expansion-2025-03-18-captured-2026-07-20"
)
DCOA_KEY = "dcoa-abilene-project-radiance-2025-03-18-captured-2026-07-20"
CITY_KEY = (
    "abilene-planning-q2-2025-lancium-buildings-5-8-captured-2026-07-20"
)

ARTIFACT_FILE_SPECS = {
    "README.md": (
        2_635,
        "9b0b52d709a291d30716287b3291b342a55c779db4a2ef97b6439778155cacd2",
    ),
    "manifest.json": (
        1_079,
        "46d2c0bdc89835457ec1619ed0d06dc41988d0193cc3b36212c199e481f49cc2",
    ),
    "manifest.sha256": (
        80,
        "60547c564f180c23c41b9dca2c6f70ae4f92cdf3b86e5a7d7f6ace5aa4ad2d70",
    ),
    "retrieval-inventory.json": (
        11_256,
        "f457b88562229f20c85e0b918470dae4025d70f8f9d400d304636e9b2ddd9d43",
    ),
    "source-snapshot.json": (
        4_498,
        "ed4ad3f8e380975dd9a2da1cbd533bf55635cb21d8c95e2ce2b250ffcfe0bb1c",
    ),
}
ARTIFACT_TREE_SHA256 = (
    "34df1ccd0f80bd56333cb13487c671bb1c6c487373555451d7ccd91717a6d80d"
)

CAPTURE_SPECS = {
    "oracle_data_center_portfolio": {
        "evidence_key": PORTFOLIO_KEY,
        "body": (
            58_754,
            "3222773fcc16f4415692dd48c2254c15b00ea3bd5c5e4a1d4988a7a977b05e91",
        ),
        "headers": (
            1_816,
            "6d65f34e4c3cd07b0e4422fa04f918c892aedf2f413b97a963ca3d4c13796923",
        ),
        "writeout": (
            12_827,
            "5e9e2b9b5c769b0a6f86efbc04ed4cb35ed56aec002c0b4a9550ff0bbeb5f6aa",
        ),
    },
    "oracle_abilene_facts_page": {
        "evidence_key": FACTS_KEY,
        "body": (
            31_569,
            "1ddbdd2625af5a2ab4ecf6ec50bcf7c0b64c709edfe87c03c60b0868c2f020a8",
        ),
        "headers": (
            1_816,
            "0634dfe684aecbda8e33cc5b15dab34f34598178dcbf95fefde71c6cc58995cd",
        ),
        "writeout": (
            12_857,
            "0d69040b87f62ab5be3469f86dd78a4d5f265f3de28a046c9de817179e572656",
        ),
    },
    "crusoe_abilene_expansion": {
        "evidence_key": CRUSOE_KEY,
        "body": (
            214_819,
            "b87b1da18f85bd6542951ac0cf85ef85dc1e34616ce711e9c43f050838dde593",
        ),
        "headers": (
            1_687,
            "8b73d6c069f3f9709ec19fbd1bf367bc340d334f3c3a5c756ab3d74ca156729e",
        ),
        "writeout": (
            9_762,
            "01bbdc5a53a3ceab39d49336f2e0c323ba96e8bbf60f795014b6adadc88fb4c4",
        ),
    },
    "dcoa_project_radiance": {
        "evidence_key": DCOA_KEY,
        "body": (
            106_318,
            "179651b5f8074a86063d96ce9f12013211a5bdaee4d876af49d8bf32358077fe",
        ),
        "headers": (
            1_032,
            "9c334ab195b211eb11034e7f65cdd70e75763e3bb30fe82729222c73f5e9246f",
        ),
        "writeout": (
            13_260,
            "bf33c30f842e9a87220c9aa7b6c4e9b1eba1e2b0c0b7a3137428aae0434c73ff",
        ),
    },
    "city_abilene_q2_2025_planning_report": {
        "evidence_key": CITY_KEY,
        "body": (
            1_854_718,
            "181c419ff99ec07a93801da2fc43f0174040dd770ac2c02ba9f933a64db50bff",
        ),
        "headers": (
            993,
            "77700980cdd07acef9c61e5a00ccc7d5da9e6f8d79e5a60200e4d5e956409161",
        ),
        "writeout": (
            9_711,
            "dfe10c144db83845c5d35222ae3ad1f7a8d20f29a21b29c0f808c69e9bb3a881",
        ),
    },
    "oracle_abilene_data_halls_aerial": {
        "evidence_key": PORTFOLIO_KEY,
        "body": (
            52_979,
            "720ddbeed3d6b9e0969e83074ecec8fee529443371ba3179e70e35193b86185b",
        ),
        "headers": (
            1_787,
            "d0fa2c47ce88d008c0b56d645be414211612d0ec187c3da5581ef4b872ed08ee",
        ),
        "writeout": (
            13_097,
            "d7403bc822a9b47ce75676ac194d683770542c55d594eef426c97cae0e49087f",
        ),
    },
}


def sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class OracleAbileneCuratedTests(unittest.TestCase):
    def _load(self) -> dict:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Abilene curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _import(self, repetitions: int = 1):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results = []
        with self._offline():
            for _ in range(repetitions):
                results.append(
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        SOURCE,
                        retrieved_at=RETRIEVED_AT,
                    )
                )
        return temporary, connection, results

    def test_source_is_canonical_byte_pinned_and_calendar_safe(self) -> None:
        self.assertTrue(SOURCE.is_file())
        self.assertFalse(SOURCE.is_symlink())
        self.assertTrue(stat.S_ISREG(SOURCE.stat().st_mode))
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        text = data.decode("utf-8")
        document = json.loads(text)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(document["schema_version"], "1.0")
        self.assertNotIn("captured-2026-07-21", text)
        self.assertNotIn("official-2026-07-21", text)
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [PORTFOLIO_KEY, FACTS_KEY, CRUSOE_KEY, DCOA_KEY, CITY_KEY],
        )
        cutoff = date(2026, 7, 20)
        for entity_name in ("campus", "project"):
            self.assertLessEqual(
                date.fromisoformat(document[entity_name]["as_of_date"]), cutoff
            )
        for field in ("lifecycle", "operating_models", "workloads", "capacities"):
            for row in document[field]:
                self.assertLessEqual(date.fromisoformat(row["as_of_date"]), cutoff)
        recorded_at = datetime.fromisoformat(RETRIEVED_AT.replace("Z", "+00:00"))
        for row in document["evidence"]:
            observed = datetime.fromisoformat(
                row["retrieved_at"].replace("Z", "+00:00")
            )
            self.assertLessEqual(observed, recorded_at)

    def test_frozen_capture_artifact_is_closed_and_hash_pinned(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {item.name for item in ARTIFACT.iterdir() if item.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            file_path = ARTIFACT / name
            self.assertTrue(file_path.is_file())
            self.assertFalse(file_path.is_symlink())
            self.assertEqual(stat.S_IMODE(file_path.stat().st_mode), 0o444)
            self.assertEqual(len(file_path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(file_path), expected_hash)

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
        self.assertEqual(set(manifest["closed_file_set"]), set(ARTIFACT_FILE_SPECS))
        self.assertFalse(manifest["raw_capture_redistributed"])
        self.assertFalse(manifest["publisher_media_redistributed"])
        self.assertFalse(manifest["municipal_pdf_redistributed"])
        for entry in manifest["files"]:
            file_path = ARTIFACT / entry["path"]
            self.assertEqual(len(file_path.read_bytes()), entry["bytes"])
            self.assertEqual(sha256(file_path), entry["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(), ARTIFACT_TREE_SHA256
        )
        self.assertEqual(manifest["tree_sha256"], ARTIFACT_TREE_SHA256)
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )

        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 14)
        self.assertEqual(inventory["exploratory_response_requests"], 8)
        self.assertEqual(inventory["accepted_final_response_requests"], 6)
        self.assertEqual(inventory["successful_http_requests"], 14)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertFalse(
            Path(inventory["temporary_capture_directory_original_path"]).exists()
        )
        self.assertTrue(Path(inventory["temporary_capture_trash_path"]).is_dir())
        requests = {
            row["request_id"]: row for row in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for request_id, expected in CAPTURE_SPECS.items():
            row = requests[request_id]
            self.assertEqual(row["evidence_key"], expected["evidence_key"])
            self.assertEqual(
                (row["body"]["bytes"], row["body"]["sha256"]), expected["body"]
            )
            self.assertEqual(
                (row["headers"]["bytes"], row["headers"]["sha256"]),
                expected["headers"],
            )
            self.assertEqual(
                (row["curl_writeout"]["bytes"], row["curl_writeout"]["sha256"]),
                expected["writeout"],
            )
            self.assertFalse(row["body"]["retained_in_artifact"])
            self.assertFalse(row["headers"]["retained_in_artifact"])
            self.assertFalse(row["curl_writeout"]["retained_in_artifact"])

    def test_normalized_claims_preserve_partial_delivery_and_metric_scope(self) -> None:
        document = self._load()
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(
                entity["address"], "617 FM 2404, Abilene, Texas, United States"
            )
            self.assertEqual(
                entity["roles"], {"owner": ["Lancium"], "developer": ["Crusoe"]}
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
                    "evidence_key": PORTFOLIO_KEY,
                    "as_of_date": "2026-06-04",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(len(document["workloads"]), 1)
        self.assertEqual(document["workloads"][0]["value"], "ai_specialized_unspecified")
        self.assertEqual(document["workloads"][0]["as_of_date"], "2026-01-31")
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (capacity["entity"], capacity["metric"], capacity["stage"], capacity["unit"]),
            ("campus", "grid_connection_mw", "planned", "MW"),
        )
        self.assertEqual(
            (capacity["low"], capacity["base"], capacity["high"]),
            (1200, 1200, 1200),
        )
        self.assertIsNone(capacity["target_date"])

        evidence = {row["key"]: row for row in document["evidence"]}
        portfolio = evidence[PORTFOLIO_KEY]["metadata"]
        self.assertEqual(portfolio["capacity_delivery_wording_as_reported"][:13], "Delivered 42%")
        self.assertIn("does not create", portfolio["capacity_delivery_guardrail"])
        self.assertIn("not independent satellite", portfolio["imagery_provenance_guardrail"])
        self.assertEqual(
            portfolio["data_halls_aerial_body_sha256"],
            CAPTURE_SPECS["oracle_abilene_data_halls_aerial"]["body"][1],
        )
        facts = evidence[FACTS_KEY]["metadata"]
        self.assertEqual(facts["campus_building_count_as_reported"], 8)
        self.assertEqual(facts["campus_floor_area_square_feet_as_reported"], 4_000_000)
        self.assertIn("no MW rating", facts["ercot_connection_guardrail"])
        self.assertIn("creates no generation", facts["backup_power_scope"])
        crusoe = evidence[CRUSOE_KEY]["metadata"]
        self.assertEqual(crusoe["grid_interconnection_as_reported_mw"], 1200)
        self.assertIn("not critical IT load", crusoe["capacity_guardrail"])
        self.assertIn("no ai_training", crusoe["training_inference_guardrail"])
        dcoa = evidence[DCOA_KEY]["metadata"]
        self.assertEqual(dcoa["completed_substation_as_reported_mw"], 200)
        self.assertEqual(
            dcoa["additional_substation_under_construction_as_reported_gw"], 1
        )
        self.assertIn("do not create additive", dcoa["substation_guardrail"])
        city = evidence[CITY_KEY]["metadata"]
        self.assertEqual(city["project_address_as_reported"], "617 FM 2404")
        self.assertIn("not a physical construction stage", city["status_guardrail"])

    def test_offline_import_is_valid_and_idempotent(self) -> None:
        temporary, connection, results = self._import(repetitions=2)
        try:
            self.assertEqual(results[0].entities_created, 2)
            self.assertEqual(results[0].evidence_created, 5)
            self.assertEqual(results[0].warnings, ())
            self.assertEqual(results[1].entities_created, 0)
            self.assertEqual(results[1].evidence_created, 0)
            self.assertEqual(results[1].warnings, ())
            self.assertEqual(validate_database(connection), [])
            expected_counts = {
                "entities": 2,
                "evidence": 5,
                "entity_snapshots": 2,
                "lifecycle_observations": 1,
                "capacity_estimates": 1,
                "workload_observations": 1,
                "operating_model_observations": 0,
            }
            for table, expected in expected_counts.items():
                actual = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                self.assertEqual(actual, expected, table)
        finally:
            connection.close()
            temporary.cleanup()

    def test_database_rows_preserve_roles_dates_and_nonadditive_capacity(self) -> None:
        temporary, connection, _ = self._import()
        try:
            snapshots = connection.execute(
                """
                SELECT e.stable_key, s.latitude, s.longitude, s.geometry_json,
                       s.tags_json, s.as_of_date, s.method
                FROM entities AS e
                JOIN entity_snapshots AS s ON s.entity_id = e.id
                ORDER BY e.stable_key
                """
            ).fetchall()
            self.assertEqual([row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY])
            for row in snapshots:
                self.assertIsNone(row["latitude"])
                self.assertIsNone(row["longitude"])
                self.assertIsNone(row["geometry_json"])
                self.assertEqual(row["as_of_date"], "2025-04-30")
                self.assertEqual(row["method"], "authoritative_locality")
                tags = json.loads(row["tags_json"])
                self.assertEqual(tags["role:owner"], "Lancium")
                self.assertEqual(tags["role:developer"], "Crusoe")
                self.assertNotIn("role:tenant", tags)
                self.assertNotIn("role:operator", tags)

            lifecycle = connection.execute(
                "SELECT status, as_of_date, method FROM lifecycle_observations"
            ).fetchone()
            self.assertEqual(
                tuple(lifecycle),
                ("under_construction", "2026-06-04", "authoritative_physical_status_update"),
            )
            workload = connection.execute(
                "SELECT workload, as_of_date, method FROM workload_observations"
            ).fetchone()
            self.assertEqual(
                tuple(workload),
                ("ai_specialized_unspecified", "2026-01-31", "company_disclosure"),
            )
            capacity = connection.execute(
                """
                SELECT metric, stage, unit, low, base, high, method, as_of_date,
                       target_date, notes
                FROM capacity_estimates
                """
            ).fetchone()
            self.assertEqual(
                tuple(capacity)[:9],
                (
                    "grid_connection_mw",
                    "planned",
                    "MW",
                    1200.0,
                    1200.0,
                    1200.0,
                    "reported",
                    "2025-03-18",
                    None,
                ),
            )
            self.assertIn("not critical IT load", capacity["notes"])
        finally:
            connection.close()
            temporary.cleanup()

    def test_v64_remains_frozen_and_excludes_the_v65_input(self) -> None:
        self.assertEqual(sha256(V64_DEFINITION), V64_DEFINITION_SHA256)
        definition = json.loads(V64_DEFINITION.read_text(encoding="utf-8"))
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertEqual(len(selected), 363)
        self.assertNotIn(f"sources/{SOURCE_NAME}", selected)
        self.assertEqual(
            definition["build"],
            {"as_of": "2026-07-20", "recorded_at": "2026-07-21T05:50:00Z"},
        )


if __name__ == "__main__":
    unittest.main()
