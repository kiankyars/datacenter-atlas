from __future__ import annotations

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

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RECORDED_AT = "2026-07-21T07:06:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "official-gap-authoritative-tranche-2026-07-20-v1"
)

SEL3 = "curated-official-2026-07-20-digital-edge-sel3-bupyeong.json"
SMX01 = "curated-official-2026-07-20-smplus-smx01-jakarta-cbd.json"
SYD06 = (
    "curated-official-2026-07-20-microsoft-kemps-creek-syd06-building-two.json"
)
AURORA = "curated-official-2026-07-20-aurora-core-mikkeli-phase-1.json"
ALPS = "curated-official-2026-07-20-alps-duqm-under-construction.json"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    SEL3: {
        "bytes": 12_604,
        "sha256": "b8f6ff6a9cebe6630bf9757eb78c56af1cd63cd0b949c9f72615bb0ae44ff67b",
        "evidence_count": 3,
        "campus": "curated:digital-edge-seoul-bupyeong-campus",
        "project": "curated:digital-edge-seoul-bupyeong-campus:sel3-phase-2",
    },
    SMX01: {
        "bytes": 19_150,
        "sha256": "fce7c2103f43a97dd296874c602443829d747b836658e00d4b74eaa6a6ecdf9f",
        "evidence_count": 5,
        "campus": "curated:smplus-smx01-jakarta-cbd",
        "project": "curated:smplus-smx01-jakarta-cbd:initial-18mw-build",
    },
    SYD06: {
        "bytes": 15_323,
        "sha256": "9268190e7851dc5b613baf11d4aee199a63487b1c19b2709863560f1b0f43818",
        "evidence_count": 4,
        "campus": "curated:microsoft-kemps-creek-data-centre",
        "project": "curated:microsoft-kemps-creek-data-centre:syd06-building-two",
    },
    AURORA: {
        "bytes": 13_241,
        "sha256": "c9fdc17a73bd225cd31eaa19134375b5f6f0399993fd89bab1cecad11787ce6d",
        "evidence_count": 3,
        "campus": "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre",
        "project": (
            "curated:aurora-core-mikkeli-pellosniemi-ai-data-centre:phase-1"
        ),
    },
    ALPS: {
        "bytes": 10_312,
        "sha256": "a7f6ef7e6474971b2f69663e0735814a38e26c866e708e966a364b853bfd9be8",
        "evidence_count": 2,
        "campus": "curated:alps-middle-east-duqm-data-center",
        "project": "curated:alps-middle-east-duqm-data-center:initial-80mw-build",
    },
}

ARTIFACT_SPECS = {
    "README.md": (
        2_882,
        "7b49ffb63a3da6131553d3bebb5e0b03ec2e61f9fdb2b58185fd1bd653d29b0f",
    ),
    "manifest.json": (
        866,
        "cf4ecd9870fd28cd29e3ff201f30bf549216d46e1e17fb70c4057ac9bab79ab4",
    ),
    "manifest.sha256": (
        80,
        "3ab839021c0252f1d3445a81e463dae7221fb7a0631234010dca2b242c18af2c",
    ),
    "retrieval-inventory.json": (
        23_244,
        "377ec663c8cc5ca6a3f5e16157ba72d3e4718baea6037ee3448c160ccbb36245",
    ),
    "review-nonpromotions.json": (
        4_190,
        "cbd2a00dc841b1c3d05f3c848819f8b3155098f6a6d9d71891cd9844aa932b3e",
    ),
    "source-snapshot.json": (
        4_761,
        "88ee6b0327f591b41ad734fea0331c66d175984db345de43e2edb6ffc5fea70b",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfficialGapAuthoritativeTrancheTests(unittest.TestCase):
    def _document(self, source_name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / source_name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("curated tranche import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def test_sources_are_canonical_regular_and_byte_pinned(self) -> None:
        for source_name, expected in SOURCE_SPECS.items():
            with self.subTest(source=source_name):
                source = ROOT / "sources" / source_name
                self.assertTrue(source.is_file())
                self.assertFalse(source.is_symlink())
                self.assertTrue(stat.S_ISREG(source.stat().st_mode))
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                raw = source.read_bytes()
                self.assertEqual(len(raw), expected["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
                text = raw.decode("utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.1")
                self.assertEqual(len(document["evidence"]), expected["evidence_count"])
                self.assertEqual(document["campus"]["stable_key"], expected["campus"])
                self.assertEqual(document["project"]["stable_key"], expected["project"])
                self.assertNotIn("captured-2026-07-21", text)

    def test_capacity_lifecycle_geometry_and_workload_boundaries(self) -> None:
        documents = {name: self._document(name) for name in SOURCE_SPECS}
        for source_name, document in documents.items():
            with self.subTest(source=source_name):
                self.assertEqual(document["workloads"], [])
                self.assertEqual(document["operating_models"], [])
                serialized = json.dumps(document).lower()
                self.assertNotIn('"metric": "annual_energy_mwh"', serialized)
                self.assertNotIn('"metric": "pue"', serialized)
                self.assertNotIn('"stage": "current"', serialized)

        self.assertEqual(
            documents[SEL3]["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "sk-ecoplant-bupyeong-phase-2-current-update-2026-07-09-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-09",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in documents[SMX01]["lifecycle"]],
            [("under_construction", "2025-03-06"), ("shell", "2026-05-08")],
        )
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in documents[SYD06]["lifecycle"]],
            [("under_construction", "2026-05-01")],
        )
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in documents[AURORA]["lifecycle"]],
            [("civil_works", "2026-04-06")],
        )
        self.assertEqual(
            [(row["value"], row["as_of_date"]) for row in documents[ALPS]["lifecycle"]],
            [("under_construction", "2026-07-21")],
        )

        capacities = {
            source_name: [
                (row["metric"], row["stage"], row["base"], row["unit"])
                for row in document["capacities"]
            ]
            for source_name, document in documents.items()
        }
        self.assertEqual(capacities[SEL3], [("critical_it_mw", "planned", 60, "MW")])
        self.assertEqual(capacities[SMX01], [("critical_it_mw", "planned", 18, "MW")])
        self.assertEqual(capacities[SYD06], [])
        self.assertEqual(capacities[AURORA], [])
        self.assertEqual(capacities[ALPS], [("gross_facility_mw", "planned", 80, "MW")])
        self.assertIn("nested 96 MW", documents[SEL3]["capacities"][0]["notes"])
        self.assertIn("MVA", documents[SMX01]["capacities"][0]["notes"])
        self.assertIn("150 MW", documents[ALPS]["capacities"][0]["notes"])

        point = {"latitude": -33.83614, "longitude": 150.78015}
        self.assertEqual(documents[SYD06]["campus"]["coordinates"], point)
        self.assertEqual(documents[SYD06]["project"]["coordinates"], point)
        for source_name in (SEL3, SMX01, AURORA, ALPS):
            self.assertIsNone(documents[source_name]["campus"]["coordinates"])
            self.assertIsNone(documents[source_name]["campus"]["geometry"])
            self.assertIsNone(documents[source_name]["project"]["coordinates"])
            self.assertIsNone(documents[source_name]["project"]["geometry"])

    def test_roles_are_explicit_and_do_not_promote_operation(self) -> None:
        smx = self._document(SMX01)
        self.assertEqual(
            smx["project"]["roles"],
            {
                "developer": ["SM+ Data Centers"],
                "investor": ["Korea Investment Real Asset Management"],
                "operator": ["LG Sinar Mas"],
            },
        )
        evidence = {row["key"]: row for row in smx["evidence"]}
        guardrail = evidence[
            "smplus-smx01-topping-off-2026-05-08-captured-2026-07-20"
        ]["metadata"]["operator_role_guardrail"]
        self.assertIn("source-reported design-and-operation-partner", guardrail)
        self.assertIn("still under construction", guardrail)
        self.assertIn("not evidence", guardrail)
        self.assertIn("current IT load", guardrail)
        self.assertEqual(smx["workloads"], [])

        microsoft = self._document(SYD06)
        self.assertEqual(
            microsoft["project"]["roles"],
            {
                "developer": ["Microsoft Datacenter (Australia) Pty Ltd"],
                "contractor": ["AW Edwards"],
            },
        )
        self.assertNotIn("owner", microsoft["project"]["roles"])
        self.assertNotIn("operator", microsoft["project"]["roles"])

        aurora = self._document(AURORA)
        self.assertEqual(
            aurora["project"]["roles"],
            {"developer": ["Aurora Core Technology Oy"]},
        )
        self.assertNotIn("operator", aurora["project"]["roles"])
        self.assertEqual(
            self._document(ALPS)["project"]["roles"],
            {"developer": ["ALPS Middle East"]},
        )

    def test_exact_identity_nonmerge_advisories_are_pinned(self) -> None:
        sel3 = self._document(SEL3)
        sel3_guardrail = next(
            row["metadata"]["collision_guardrail"]
            for row in sel3["evidence"]
            if "collision_guardrail" in row["metadata"]
        )
        self.assertIn("ESR/Wide Creek/PDG Bupyeong KR1", sel3_guardrail)
        self.assertIn("60 MW IT capacity", sel3_guardrail)
        self.assertIn("80 MW Facility Load", sel3_guardrail)
        self.assertIn("not identity evidence", sel3_guardrail)

        microsoft = self._document(SYD06)
        microsoft_guardrail = next(
            row["metadata"]["identity_guardrail"]
            for row in microsoft["evidence"]
            if "identity_guardrail" in row["metadata"]
        )
        self.assertIn("osm:way/1479632522", microsoft_guardrail)
        self.assertIn("no curated status", microsoft_guardrail)
        self.assertIn("SSD-92743706", microsoft_guardrail)
        self.assertIn("706–752 Mamre Road", microsoft_guardrail)
        self.assertIn("absent direct authoritative Microsoft identity proof", microsoft_guardrail)

        aurora = self._document(AURORA)
        aurora_guardrail = next(
            row["metadata"]["collision_guardrail"]
            for row in aurora["evidence"]
            if "collision_guardrail" in row["metadata"]
        )
        self.assertIn("EcoSairila", aurora_guardrail)
        alps = self._document(ALPS)
        alps_guardrail = next(
            row["metadata"]["collision_guardrail"]
            for row in alps["evidence"]
            if "collision_guardrail" in row["metadata"]
        )
        self.assertIn("Taqah", alps_guardrail)
        self.assertIn("Oman Data Park/Otech Duqm", alps_guardrail)

    def test_capture_inventory_closes_every_request_and_matches_evidence(self) -> None:
        inventory_path = ARTIFACT / "retrieval-inventory.json"
        inventory_text = inventory_path.read_text(encoding="utf-8")
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["direct_request_attempts"], 21)
        self.assertEqual(inventory["successful_http_requests"], 20)
        self.assertEqual(inventory["failed_http_requests"], 1)
        self.assertEqual(inventory["curated_evidence_supporting_requests"], 17)
        self.assertEqual(inventory["review_nonpromotion_supporting_requests"], 3)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        self.assertTrue(inventory["temporary_capture_recoverable"])
        self.assertEqual(
            Path(inventory["temporary_capture_trash_path"]).name,
            "official-gap-tranche-2026-07-20-jliZz1",
        )
        requests = {
            row["request_id"]: row for row in inventory["controlled_http_requests"]
        }
        self.assertEqual(len(requests), 21)
        self.assertEqual(requests["aurora_permit_pdf"]["http_status"], 404)
        self.assertEqual(requests["aurora_permit_pdf"]["disposition"], "failed_not_evidence")
        self.assertEqual(requests["aurora_permit_pdf"]["body"]["bytes"], 0)

        evidence_count = 0
        for source_name in SOURCE_SPECS:
            for evidence in self._document(source_name)["evidence"]:
                evidence_count += 1
                request = requests[evidence["metadata"]["capture_request_id"]]
                self.assertEqual(request["disposition"], "curated_evidence")
                self.assertEqual(request["requested_url"], evidence["source_url"])
                self.assertEqual(request["retrieved_at"], evidence["retrieved_at"])
                self.assertEqual(request["body"]["sha256"], evidence["content_hash"])
                self.assertEqual(
                    request["headers"]["sha256"],
                    evidence["metadata"]["capture_headers_sha256"],
                )
                self.assertEqual(
                    request["curl_writeout"]["sha256"],
                    evidence["metadata"]["capture_curl_writeout_sha256"],
                )
                self.assertFalse(request["body"]["retained_in_artifact"])
                self.assertFalse(request["headers"]["retained_in_artifact"])
                self.assertFalse(request["curl_writeout"]["retained_in_artifact"])
        self.assertEqual(evidence_count, 17)

    def test_blue_tongue_is_review_only_without_invented_day(self) -> None:
        review_path = ARTIFACT / "review-nonpromotions.json"
        review_text = review_path.read_text(encoding="utf-8")
        review = json.loads(review_text)
        self.assertEqual(
            review_text,
            json.dumps(review, indent=2, ensure_ascii=False) + "\n",
        )
        record = review["records"][0]
        self.assertEqual(record["decision"], "review_nonpromotion")
        self.assertIn("requires YYYY-MM-DD", record["reason"])
        self.assertIn("No arbitrary 2026 date", record["reason"])
        self.assertFalse(record["status_boundary"]["normalized_lifecycle_created"])
        self.assertFalse(record["status_boundary"]["future_dc02_created"])
        self.assertFalse(record["capacity_boundary"]["normalized_capacity_created"])
        self.assertEqual(
            record["capacity_boundary"][
                "approved_two_building_site_maximum_power_consumption_mw"
            ],
            160.85,
        )
        self.assertEqual(
            {row["request_id"] for row in record["sources"]},
            {"blue_lendlease", "blue_nsw_project", "blue_consent_pdf"},
        )

    def test_offline_import_is_clean_idempotent_and_has_no_workloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for repetition in range(2):
                        for source_name, expected in SOURCE_SPECS.items():
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                ROOT / "sources" / source_name,
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                            self.assertEqual(
                                result.entities_created,
                                2 if repetition == 0 else 0,
                            )
                            self.assertEqual(
                                result.evidence_created,
                                expected["evidence_count"] if repetition == 0 else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    10,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    17,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations"
                    ).fetchone()[0],
                    6,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
                    0,
                )
                capacity_rows = tuple(
                    tuple(row)
                    for row in connection.execute(
                        "SELECT metric, stage, base, unit FROM capacity_estimates "
                        "ORDER BY metric, base"
                    )
                )
                self.assertEqual(
                    capacity_rows,
                    (
                        ("critical_it_mw", "planned", 18.0, "MW"),
                        ("critical_it_mw", "planned", 60.0, "MW"),
                        ("gross_facility_mw", "planned", 80.0, "MW"),
                    ),
                )
            finally:
                connection.close()

    def test_artifact_is_frozen_hash_bound_and_contains_no_raw_capture(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_SPECS.items():
            path = ARTIFACT / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_SPECS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(
            {row["path"] for row in manifest["files"]},
            {
                "README.md",
                "retrieval-inventory.json",
                "review-nonpromotions.json",
                "source-snapshot.json",
            },
        )
        for row in manifest["files"]:
            path = ARTIFACT / row["path"]
            self.assertEqual(len(path.read_bytes()), row["bytes"])
            self.assertEqual(sha256(path), row["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )

        forbidden_suffixes = {
            ".body",
            ".headers",
            ".writeout",
            ".html",
            ".htm",
            ".pdf",
            ".txt",
        }
        self.assertEqual(
            [path for path in ARTIFACT.rglob("*") if path.suffix in forbidden_suffixes],
            [],
        )
        serialized = b"\n".join(
            path.read_bytes() for path in ARTIFACT.iterdir() if path.is_file()
        ).lower()
        for marker in (b"%pdf-", b"<!doctype html", b"set-cookie:"):
            self.assertNotIn(marker, serialized)

        snapshot = json.loads((ARTIFACT / "source-snapshot.json").read_text())
        self.assertEqual(snapshot["research_date"], "2026-07-20")
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        self.assertTrue(all(not row["seeded"] for row in snapshot["source_records"]))
        self.assertTrue(
            all(value is False for value in snapshot["semantic_boundary"].values())
        )


if __name__ == "__main__":
    unittest.main()
