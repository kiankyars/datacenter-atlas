from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import UTC, datetime
import hashlib
import importlib
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


builder = importlib.import_module(
    "datacenter_atlas.datacenter_atlas.site_coordinate_assessment_v5"
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v5"
PUBLISHER = ROOT / "scripts/publish_coordinate_assessment_2026_07_21_v5.py"
CAPTURE_INPUT = Path("/private/tmp/coordinate-evidence.MctywO")
CAPTURE = Path(
    "/Users/kian/.Trash/datacenter-atlas-coordinate-official-20260721-v5-MctywO"
)
RECORDED_AT = "2026-07-21T15:42:33Z"
MANIFEST_SHA256 = (
    "b05492a0454502e332c6517b60e48a99f3897f29dfae9ccd4d69569da3173b34"
)
MANIFEST_TREE_SHA256 = (
    "dc74260a7b03bea2f9250b8962fc47f7cb1a1e45bdedb1ee046ee67e021b17e2"
)
PHYSICAL_TREE_SHA256 = (
    "ecc63ed53d0151366caaf1d3d8b82a70ff4e1476baebc737356e3d8a8f77116f"
)
CAPTURE_TREE_SHA256 = (
    "0a0cc6dd755976590fea64b9d29e778159986ffb30a1bf0264376940eb4483d6"
)

FILES = {
    "README.md": (
        2_106,
        "347343358fe3d48731d7d315bb395823d01ed2d902271a2eed75a922bc87c88a",
    ),
    "coordinate-observations.json": (
        3_538,
        "2d290dfce36edb768bb1d4980fad5d8bbbffcce80cda332489ca6de9e329f7dd",
    ),
    "disposition.json": (
        5_383,
        "32cbca26705ff85f7ce56fd39c2ae52b1c1b3d51ada0af12e8cd10be989c33eb",
    ),
    "manifest.json": (2_022, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "e88ec80d58ef209ed5895f008b5a356e85acdea0cae6f49ad8ffe9cbe211bb9c",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-akashi-astana-"
        "phase-1-current-build-coordinate-v5.json"
    ): (
        13_490,
        "b1f3f37927895d6e7a02adc9afd8b93aac9e0a322d846158fe362c645a07e3a6",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-icatec-ica-"
        "current-build-coordinate-v5.json"
    ): (
        13_113,
        "88d05044c8a3ab7ad7c4f0a42227cb610b2b0fff43863672c5faf0a121d31e2a",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-lvrtc-pozitrons-"
        "kurzeme-current-build-coordinate-v5.json"
    ): (
        14_366,
        "5fce778372ee4d01b8e7990a11624ed2d588007c9a071e7f73a9e2a8a117e426",
    ),
    "retrieval-inventory.json": (
        12_075,
        "a7c0f30147116bc6ace175c54336db0f4f3705cefe4b3408f70fd5d03fae9fdf",
    ),
}


def sha256(filename: Path) -> str:
    return hashlib.sha256(filename.read_bytes()).hexdigest()


class SiteCoordinateAssessmentV5Tests(unittest.TestCase):
    def _load(self, filename: Path) -> dict:
        return json.loads(filename.read_text(encoding="utf-8"))

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("coordinate v5 attempted network access")
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
            filename.relative_to(ARTIFACT).as_posix()
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        self.assertEqual(actual, set(FILES))
        for relative, expected in FILES.items():
            filename = ARTIFACT / relative
            self.assertFalse(filename.is_symlink())
            self.assertEqual(stat.S_IMODE(filename.stat().st_mode), 0o444)
            self.assertEqual((filename.stat().st_size, sha256(filename)), expected)
            if filename.suffix == ".json":
                document = self._load(filename)
                canonical = (
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n"
                ).encode()
                self.assertEqual(filename.read_bytes(), canonical)
        for directory in (candidate for candidate in ARTIFACT.rglob("*") if candidate.is_dir()):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)

        manifest = self._load(ARTIFACT / "manifest.json")
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["tree_sha256"], MANIFEST_TREE_SHA256)
        self.assertEqual(manifest["publication_contract_version"], 5)
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
        for filename in (ARTIFACT, *ARTIFACT.rglob("*")):
            self.assertLessEqual(
                datetime.fromtimestamp(filename.stat().st_birthtime, UTC), target
            )
            self.assertLessEqual(
                datetime.fromtimestamp(filename.stat().st_mtime, UTC), target
            )
        self.assertGreaterEqual(
            datetime.fromtimestamp(ARTIFACT.stat().st_ctime, UTC), target
        )

    def test_exact_four_row_partition_and_bichuten_block(self) -> None:
        observations = self._load(ARTIFACT / "coordinate-observations.json")
        self.assertEqual(
            observations["assessment_scope"],
            {
                "project_rows": 4,
                "campus_identities": 4,
                "accepted_successors": 3,
                "accepted_project_locations": 3,
                "accepted_campus_location_mutations": 3,
                "blocked_project_rows": 1,
            },
        )
        rows = observations["rows"]
        self.assertEqual(len(rows), 4)
        accepted = [row for row in rows if row["successor"]]
        blocked = [row for row in rows if not row["successor"]]
        self.assertEqual(len(accepted), 3)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(
            {row["project_key"] for row in accepted},
            {
                "curated:lvrtc-pozitrons-kurzeme-data-center:phase-1-current-build",
                "curated:akashi-astana-data-center-campus:phase-1-current-build",
                (
                    "curated:icatec-ica-digital-transformation-data-center:"
                    "four-storey-technology-center-build"
                ),
            },
        )
        self.assertEqual(
            blocked[0]["project_key"],
            "curated:bichuten-chovar-data-center:initial-container-build",
        )
        self.assertEqual(
            blocked[0]["disposition"], "blocked_no_authoritative_coordinate"
        )
        self.assertIn("No facility-specific parcel", blocked[0]["block_reason"])

        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])
        boundaries = disposition["source_boundaries"]
        self.assertEqual(boundaries["osm_inputs_consumed"], [])
        self.assertFalse(boundaries["osm_routed_through_curated_official_importer"])
        self.assertFalse(boundaries["google_content_captured_or_redistributed"])
        self.assertFalse(boundaries["raw_official_bodies_redistributed"])

    def test_successors_are_coordinate_only_schema_11_deltas(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        successors = disposition["accepted"]["successors"]
        self.assertEqual(set(successors), {"akashi", "icatec", "lvrtc"})
        expected = {
            "akashi": (51.2067694444, 71.4577083333, 500),
            "icatec": (-14.075622, -75.734798, 150),
            "lvrtc": (56.9356302057, 22.0132502617, 300),
        }
        for label, row in successors.items():
            predecessor = self._load(ROOT / row["predecessor"])
            successor_filename = ARTIFACT / row["path"]
            successor = self._load(successor_filename)
            self.assertEqual(
                (successor_filename.stat().st_size, sha256(successor_filename)),
                (row["bytes"], row["sha256"]),
            )
            self.assertEqual(predecessor["schema_version"], "1.1")
            self.assertEqual(successor["schema_version"], "1.1")
            self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
            self.assertEqual(successor["evidence"][-1]["kind"], "government_record")
            self.assertEqual(
                successor["evidence"][-1]["key"], row["added_evidence_key"]
            )
            latitude, longitude, uncertainty = expected[label]
            metadata = successor["evidence"][-1]["metadata"]
            self.assertEqual(metadata["horizontal_uncertainty_m"], uncertainty)
            self.assertIn("changes only", metadata["claim_guardrail"])
            self.assertIn("No OpenStreetMap", metadata["osm_guardrail"])

            restored = copy.deepcopy(successor)
            restored["evidence"] = copy.deepcopy(predecessor["evidence"])
            for entity_name in ("campus", "project"):
                before = predecessor[entity_name]
                after = successor[entity_name]
                changed = {
                    key
                    for key in set(before) | set(after)
                    if before.get(key) != after.get(key)
                }
                self.assertEqual(
                    changed, {"coordinates", "geometry", "evidence_key", "method"}
                )
                self.assertEqual(
                    after["coordinates"],
                    {"latitude": latitude, "longitude": longitude},
                )
                self.assertEqual(
                    after["geometry"],
                    {"type": "Point", "coordinates": [longitude, latitude]},
                )
                self.assertEqual(after["method"], "authoritative_site_plan")
                for key in changed:
                    restored[entity_name][key] = copy.deepcopy(before[key])
            for section in (
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            ):
                self.assertEqual(successor[section], predecessor[section])
            self.assertEqual(restored, predecessor)

    def test_source_specific_rights_and_coordinate_scopes(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        successors = disposition["accepted"]["successors"]
        evidence = {
            label: self._load(ARTIFACT / row["path"])["evidence"][-1]
            for label, row in successors.items()
        }

        lvrtc = evidence["lvrtc"]
        self.assertEqual(lvrtc["license"], "CC-BY-4.0")
        self.assertIn("Valsts zemes dienests", lvrtc["attribution"])
        lvrtc_derivation = lvrtc["metadata"]["coordinate_derivation"]
        self.assertEqual(lvrtc_derivation["parcel_label"], "62740010343")
        self.assertEqual(lvrtc_derivation["source_crs"], "EPSG:4258")
        self.assertTrue(lvrtc_derivation["stored_without_numeric_shift"])
        self.assertIn("CC BY 4.0 applies", lvrtc["metadata"]["license_scope"])

        akashi = evidence["akashi"]
        akashi_derivation = akashi["metadata"]["coordinate_derivation"]
        self.assertEqual(akashi_derivation["cadastral_parcel"], "21-324-059-695")
        self.assertEqual(akashi_derivation["parcel_area_hectares_as_reported"], 11.0587)
        self.assertEqual(akashi_derivation["source_latitude_dms"], "51°12'24.37\"N")
        self.assertIn("campus/AOI lead", akashi["metadata"]["representative_point_scope"])
        self.assertIn("neither official PDF", akashi["metadata"]["rights_scope"])

        icatec = evidence["icatec"]
        icatec_derivation = icatec["metadata"]["coordinate_derivation"]
        self.assertEqual(
            icatec_derivation["official_page_destination_parameter"],
            "daddr=-14.075622,-75.734798",
        )
        self.assertFalse(icatec_derivation["google_content_requested_or_captured"])
        self.assertFalse(icatec_derivation["google_basemap_or_geocoder_used"])
        self.assertIn("No Google page", icatec["metadata"]["google_rights_guardrail"])

    def test_capture_is_preserved_hash_only_and_inventory_is_exact(self) -> None:
        self.assertFalse(CAPTURE_INPUT.exists())
        self.assertTrue(CAPTURE.is_dir())
        filenames = sorted(candidate for candidate in CAPTURE.iterdir() if candidate.is_file())
        self.assertEqual(len(filenames), 18)
        self.assertEqual(sum(filename.stat().st_size for filename in filenames), 6_538_063)
        closure = bytearray()
        for filename in filenames:
            closure.extend(f"{sha256(filename)}  ./{filename.name}\n".encode())
        self.assertEqual(hashlib.sha256(closure).hexdigest(), CAPTURE_TREE_SHA256)

        inventory = self._load(ARTIFACT / "retrieval-inventory.json")
        capture = inventory["capture"]
        self.assertEqual(capture["tree_sha256"], CAPTURE_TREE_SHA256)
        self.assertEqual(capture["files"], 18)
        self.assertEqual(capture["bytes"], 6_538_063)
        self.assertFalse(capture["raw_bytes_redistributed"])
        self.assertFalse(capture["repository_contains_raw_capture"])
        requests = {row["request_id"]: row for row in inventory["requests"]}
        self.assertEqual(len(requests), 9)
        self.assertEqual(requests["akashi_eco"]["http_status"], 200)
        self.assertFalse(requests["akashi_eco"]["server_date_used_as_retrieval_time"])
        self.assertIn("no_parcel_or_address", requests["bichuten_care"]["decision"])
        self.assertIn("destination_coordinate", requests["icatec_sedes"]["decision"])
        self.assertEqual(requests["lvrtc_wfs"]["carriers"]["body"]["bytes"], 2_187)

    def test_offline_import_idempotence_collisions_and_publisher_replay(self) -> None:
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
                        self.assertEqual(repeated.entities_created, 0)
                        self.assertEqual(repeated.evidence_created, 0)
                        self.assertEqual(validate_database(connection), [])
                    finally:
                        connection.close()
                for first, second in (
                    (predecessor, successor),
                    (successor, predecessor),
                ):
                    with tempfile.TemporaryDirectory() as temporary:
                        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                        try:
                            with self._network_guard():
                                CuratedOfficialSourceAdapterV11().import_file(
                                    connection, first, recorded_at=RECORDED_AT
                                )
                                with self.assertRaisesRegex(
                                    ValueError,
                                    "conflicts on persisted fields|already has a claim",
                                ):
                                    CuratedOfficialSourceAdapterV11().import_file(
                                        connection, second, recorded_at=RECORDED_AT
                                    )
                        finally:
                            connection.close()

        before = {
            filename.relative_to(ARTIFACT).as_posix(): sha256(filename)
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        result = subprocess.run(
            [sys.executable, str(PUBLISHER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "existing-identical")
        self.assertEqual(output["capture_preserved_at"], str(CAPTURE))
        after = {
            filename.relative_to(ARTIFACT).as_posix(): sha256(filename)
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        self.assertEqual(after, before)
        leftovers = [
            candidate.name
            for candidate in ARTIFACT.parent.iterdir()
            if candidate.name.startswith(f".{ARTIFACT.name}.stage-")
            or candidate.name == f".{ARTIFACT.name}.lock"
        ]
        self.assertEqual(leftovers, [])

    def test_builder_reproduction_is_offline_and_exact(self) -> None:
        with self._network_guard():
            payloads = builder.build_payloads(RECORDED_AT)
        self.assertEqual(set(payloads), set(FILES))
        for relative, raw in payloads.items():
            self.assertEqual(raw, (ARTIFACT / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
