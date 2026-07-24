from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import UTC, datetime
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
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v69 import tree_digest
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v4"
BUILDER = ROOT / "scripts/build_coordinate_assessment_2026_07_21_v4.py"
CAPTURE_INPUT = Path("/private/tmp/dc-coordinate-official-20260721.xrw579")
CAPTURE = Path(
    "/Users/kian/.Trash/datacenter-atlas-coordinate-official-20260721-v4-xrw579"
)
RECORDED_AT = "2026-07-21T13:00:18Z"
MANIFEST_SHA256 = (
    "8bcd9842af00890e4820e2b011a9fa799a1c4d5c98b0a77c4dc874c79b4c04b8"
)
MANIFEST_TREE_SHA256 = (
    "df7d66252ac82c80679638c059b0d4edbd6bd86be788e9b997298945a1c13ccf"
)
PHYSICAL_TREE_SHA256 = (
    "ee9da27dadb203dc44d4c4e23b2012c9849aa2f528d5753d4f5d466d15e9ccda"
)
CAPTURE_TREE_SHA256 = (
    "1c84a37eaa06a0f04a72d6c1b4f7e62c7ce00645fcb79a1df2463598db14beef"
)

FILES = {
    "README.md": (
        1_564,
        "df8230c90c43031b71f0ee2a353bac5eb1c6639c3fb2ba33646ad7996684fc38",
    ),
    "coordinate-observations.json": (
        9_813,
        "8ba6864a25bc0509cbf5492f4fdfc42033ab029d7eb3e820ab439764157e1b52",
    ),
    "disposition.json": (
        11_672,
        "32d73afc1c097b1184cfed75aa1630420f38851ab106f063e605e3c1e0b6014d",
    ),
    "manifest.json": (1_792, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "8ceb2a0ff2997a390a5d4c304d2988a358d86ed7f860103ada040b91ac589d0d",
    ),
    (
        "normalized-successors/curated-official-2026-07-19-nextdc-s4-"
        "sydney-1h26-early-works-coordinate-v4.json"
    ): (
        19_467,
        "aca10cb2fccefb0cbfe6afff0fd0393ff75fe78ad2d7f26716d3720935541984",
    ),
    (
        "normalized-successors/curated-official-2026-07-19-nextdc-sc2-"
        "sunshine-coast-1h26-fitout-coordinate-v4.json"
    ): (
        20_349,
        "c1fcf2d397f241ff98969d6ccc3d21712e01077f6be6bfbc95e266633fd981b8",
    ),
    "retrieval-inventory.json": (
        21_901,
        "d8779f46ffebd75b939222311d03edbaf47c20b8aea86617de01f1c9ca1bb240",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CoordinateAssessmentV4Tests(unittest.TestCase):
    def _load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("coordinate v4 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_frozen_closed_artifact_exact_pins_and_publication_time(self) -> None:
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(tree_digest(ARTIFACT), PHYSICAL_TREE_SHA256)
        actual = {
            path.relative_to(ARTIFACT).as_posix()
            for path in ARTIFACT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, set(FILES))
        for relative, expected in FILES.items():
            path = ARTIFACT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
            if path.suffix == ".json":
                document = self._load(path)
                self.assertEqual(
                    path.read_bytes(),
                    (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(),
                )
        for path in ARTIFACT.rglob("*"):
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555)
        manifest = self._load(ARTIFACT / "manifest.json")
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["tree_sha256"], MANIFEST_TREE_SHA256)
        self.assertEqual(manifest["publication_contract_version"], 4)
        self.assertEqual(
            hashlib.sha256(
                (
                    json.dumps(manifest["files"], indent=2, ensure_ascii=False)
                    + "\n"
                ).encode()
            ).hexdigest(),
            MANIFEST_TREE_SHA256,
        )
        target = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(target, datetime.now(UTC))
        for path in (ARTIFACT, *ARTIFACT.rglob("*")):
            self.assertLessEqual(
                datetime.fromtimestamp(path.stat().st_birthtime, UTC), target
            )
            self.assertLessEqual(
                datetime.fromtimestamp(path.stat().st_mtime, UTC), target
            )
        self.assertGreaterEqual(
            datetime.fromtimestamp(ARTIFACT.stat().st_ctime, UTC), target
        )

    def test_exact_twenty_row_partition_and_no_osm_successor(self) -> None:
        observations = self._load(ARTIFACT / "coordinate-observations.json")
        scope = observations["assessment_scope"]
        self.assertEqual(
            scope,
            {
                "project_rows": 20,
                "campus_identities": 19,
                "accepted_successors": 2,
                "accepted_project_locations": 2,
                "accepted_campus_location_mutations": 1,
                "review_only_project_rows": 18,
            },
        )
        rows = observations["rows"]
        self.assertEqual(len(rows), 20)
        accepted = [row for row in rows if row["successor"]]
        review = [row for row in rows if not row["successor"]]
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(review), 18)
        self.assertEqual(
            {row["project_key"] for row in accepted},
            {
                "curated:nextdc-s4-sydney:early-works",
                (
                    "curated:nextdc-sc2-maroochydore:"
                    "incremental-in-progress-fit-out"
                ),
            },
        )
        self.assertEqual(
            sum(row["disposition"] == "osm_review_only" for row in review), 12
        )
        self.assertEqual(
            sum(row["disposition"] == "osm_midpoint_review_only" for row in review),
            1,
        )
        self.assertEqual(
            sum(
                row["disposition"] == "official_report_not_captured"
                for row in review
            ),
            2,
        )
        self.assertFalse(any("osm" in (row["successor"] or "") for row in rows))
        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])
        self.assertIn("OPENSTREETMAP", disposition["review_only"]["osm_policy"])
        self.assertIn("general HTML", disposition["review_only"]["ld14_policy"])

    def test_successors_are_schema_upgrade_plus_coordinate_only_delta(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        successors = disposition["accepted"]["successors"]
        self.assertEqual(set(successors), {"s4", "sc2"})
        expected_coordinates = {
            "s4": (-33.8278399, 150.825),
            "sc2": (-26.6600114, 153.0924068),
        }
        for label, row in successors.items():
            predecessor = self._load(ROOT / row["predecessor"])
            successor_path = ARTIFACT / row["path"]
            successor = self._load(successor_path)
            self.assertEqual(
                (successor_path.stat().st_size, sha256(successor_path)),
                (row["bytes"], row["sha256"]),
            )
            self.assertEqual(predecessor["schema_version"], "1.0")
            self.assertEqual(successor["schema_version"], "1.1")
            self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
            self.assertEqual(successor["evidence"][-1]["kind"], "government_record")
            self.assertEqual(
                successor["evidence"][-1]["key"], row["added_evidence_key"]
            )
            restored = copy.deepcopy(successor)
            restored["schema_version"] = "1.0"
            restored["evidence"] = copy.deepcopy(predecessor["evidence"])
            latitude, longitude = expected_coordinates[label]
            for entity_name in ("campus", "project"):
                before = predecessor[entity_name]
                after = successor[entity_name]
                changed = {
                    key
                    for key in set(before) | set(after)
                    if before.get(key) != after.get(key)
                }
                if entity_name in row["changed_entities"]:
                    self.assertEqual(
                        changed,
                        {"coordinates", "geometry", "evidence_key", "method"},
                    )
                    self.assertEqual(
                        after["coordinates"],
                        {"latitude": latitude, "longitude": longitude},
                    )
                    self.assertEqual(
                        after["geometry"],
                        {"type": "Point", "coordinates": [longitude, latitude]},
                    )
                    for key in changed:
                        restored[entity_name][key] = copy.deepcopy(before[key])
                else:
                    self.assertEqual(changed, set())
            for section in (
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            ):
                self.assertEqual(successor[section], predecessor[section])
            self.assertEqual(restored, predecessor)
        self.assertEqual(successors["sc2"]["changed_entities"], ["project"])

    def test_capture_tree_is_preserved_hash_only_and_inventory_is_exact(self) -> None:
        self.assertFalse(CAPTURE_INPUT.exists())
        self.assertTrue(CAPTURE.is_dir())
        paths = sorted(path for path in CAPTURE.iterdir() if path.is_file())
        self.assertEqual(len(paths), 54)
        self.assertEqual(sum(path.stat().st_size for path in paths), 1_692_764)
        closure = bytearray()
        for path in paths:
            closure.extend(f"{sha256(path)}  ./{path.name}\n".encode())
        self.assertEqual(hashlib.sha256(closure).hexdigest(), CAPTURE_TREE_SHA256)
        inventory = self._load(ARTIFACT / "retrieval-inventory.json")
        self.assertEqual(inventory["capture"]["tree_sha256"], CAPTURE_TREE_SHA256)
        self.assertEqual(inventory["capture"]["files"], 54)
        self.assertEqual(inventory["capture"]["bytes"], 1_692_764)
        self.assertFalse(inventory["capture"]["raw_bytes_redistributed"])
        requests = {row["request_id"]: row for row in inventory["requests"]}
        self.assertEqual(len(requests), 18)
        self.assertEqual(requests["uk_ld14_report"]["http_status"], 200)
        self.assertEqual(
            requests["uk_ld14_report"]["decision"],
            "redirected_to_general_html_not_the_report_pdf",
        )
        self.assertEqual(requests["equinix_os3"]["http_status"], 403)
        self.assertIn("no_os3_identity_bridge", requests["japan_gsi_os3"]["decision"])

    def test_offline_import_idempotence_collision_and_builder_replay(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        for label, row in disposition["accepted"]["successors"].items():
            predecessor = ROOT / row["predecessor"]
            successor = ARTIFACT / row["path"]
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary:
                    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                    try:
                        with self._network_guard():
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection, successor, recorded_at=RECORDED_AT
                            )
                            repeated = CuratedOfficialSourceAdapterV11().import_file(
                                connection, successor, recorded_at=RECORDED_AT
                            )
                        self.assertEqual(result.entities_created, 2)
                        self.assertEqual(result.evidence_created, 2)
                        self.assertEqual(repeated.entities_created, 0)
                        self.assertEqual(repeated.evidence_created, 0)
                        self.assertEqual(validate_database(connection), [])
                    finally:
                        connection.close()
                for first, second in ((predecessor, successor), (successor, predecessor)):
                    with tempfile.TemporaryDirectory() as temporary:
                        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                        try:
                            first_document = self._load(first)
                            second_document = self._load(second)
                            first_recorded_at = (
                                first_document["evidence"][0]["retrieved_at"]
                                if first_document["schema_version"] == "1.0"
                                else RECORDED_AT
                            )
                            second_recorded_at = (
                                second_document["evidence"][0]["retrieved_at"]
                                if second_document["schema_version"] == "1.0"
                                else RECORDED_AT
                            )
                            with self._network_guard():
                                CuratedOfficialSourceAdapterV11().import_file(
                                    connection, first, recorded_at=first_recorded_at
                                )
                                with self.assertRaisesRegex(
                                    ValueError,
                                    "conflicts on persisted fields|already has a claim",
                                ):
                                    CuratedOfficialSourceAdapterV11().import_file(
                                        connection,
                                        second,
                                        recorded_at=second_recorded_at,
                                    )
                        finally:
                            connection.close()

        before = {
            path.relative_to(ARTIFACT).as_posix(): sha256(path)
            for path in ARTIFACT.rglob("*")
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
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")
        after = {
            path.relative_to(ARTIFACT).as_posix(): sha256(path)
            for path in ARTIFACT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        leftovers = [
            path.name
            for path in ARTIFACT.parent.iterdir()
            if path.name.startswith(f".{ARTIFACT.name}.stage-")
            or path.name == f".{ARTIFACT.name}.lock"
        ]
        self.assertEqual(leftovers, [])

    def test_builder_payload_reproduction_is_offline_and_exact(self) -> None:
        module_spec = importlib.util.spec_from_file_location(
            "coordinate_v4_builder_test", BUILDER
        )
        assert module_spec is not None and module_spec.loader is not None
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        with self._network_guard():
            payloads = module._payloads(RECORDED_AT)
        self.assertEqual(set(payloads), set(FILES))
        for relative, raw in payloads.items():
            self.assertEqual(raw, (ARTIFACT / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
