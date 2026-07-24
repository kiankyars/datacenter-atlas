from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v14.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v14"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v13.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v13"
DEFINITION_SHA256 = "897773e8fbba40e7fe69ce1c6ad79f8881981ef9d3cc034d33d3cc93d30296f1"
MANIFEST_SHA256 = "64b0524897777915fcb43334a85dc5c9605f95f141257a521396be32a71be568"

SOURCE_HASHES = {
    "curated-official-2026-07-19-colt-frankfurt3-sossenheim.json": (
        "322e3929b2542204ed2f543fd9462f9f2cf9cd2afeb76b9448ece38a82295c9d"
    ),
    "curated-official-2026-07-19-colt-paris2-villebon-sur-yvette.json": (
        "aac09ee130b7d721f0605d8ea0f9916955baf6666f692eb397f7fcb6dc6737ff"
    ),
    "curated-official-2026-07-19-cyrusone-dfw10-building-1.json": (
        "00f3d66646a1f775028f21e3c482157ed2b4b6fadff8972cb4ced0e839fb123c"
    ),
    "curated-official-2026-07-19-cyrusone-dfw10-current-campus-development.json": (
        "1ca71a38e270f40d4c4933d6a99dc9a30026f51e6d72188d5bd020db2ad860ac"
    ),
    "curated-official-2026-07-19-cyrusone-fra6-sossenheim.json": (
        "551624cd9f2e96a979a50391b5eebee44f156b1a0b4cdb80b4fe794cf9dceeb3"
    ),
    "curated-official-2026-07-19-cyrusone-fra7-frankfurt-westside.json": (
        "fa736c847a85f5d99bb4f0cd608cea5dc82f381905fea017a9a7d8e3b66324c0"
    ),
    "curated-official-2026-07-19-cyrusone-freestone-initial-facility.json": (
        "85c35586d67365c12fc7332ef736ad829f6f2bef3cd1d6c5c0f6a3a58b5fc7ad"
    ),
    "curated-official-2026-07-19-cyrusone-new-albany-building-1.json": (
        "8911834b22cd48fd31135f01d407944cd6fbd0784d25c1c0fc338eeaac952059"
    ),
    "curated-official-2026-07-19-cyrusone-osk1-seika.json": (
        "09f16a91356f27ad00f293d8bf1d95c5578ef622713e872e14c42111a4bb67ef"
    ),
}

NEW_ENTITY_KEYS = {
    "curated:colt-frankfurt3-sossenheim-campus",
    "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build",
    "curated:colt-villebon-sur-yvette-campus",
    "curated:colt-villebon-sur-yvette-campus:paris2-current-facility-build",
    "curated:cyrusone-dfw10-bosque-county-campus",
    "curated:cyrusone-dfw10-bosque-county-campus:building-1-current-build",
    "curated:cyrusone-dfw10-bosque-county-campus:current-campus-development",
    "curated:cyrusone-fra6-sossenheim-campus",
    "curated:cyrusone-fra6-sossenheim-campus:current-brownfield-redevelopment",
    "curated:cyrusone-fra7-frankfurt-westside-campus",
    "curated:cyrusone-fra7-frankfurt-westside-campus:current-multi-building-development",
    "curated:cyrusone-freestone-county-campus",
    "curated:cyrusone-freestone-county-campus:initial-facility-build",
    "curated:cyrusone-kep-osk1-seika-data-center",
    "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build",
    "curated:cyrusone-new-albany-campus",
    "curated:cyrusone-new-albany-campus:building-1-current-build",
}

EXPECTED_STATUSES = {
    "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build": (
        "under_construction",
        "2026-07-19",
    ),
    "curated:colt-villebon-sur-yvette-campus:paris2-current-facility-build": (
        "under_construction",
        "2026-07-19",
    ),
    "curated:cyrusone-dfw10-bosque-county-campus:building-1-current-build": (
        "shell",
        "2026-03-13",
    ),
    "curated:cyrusone-dfw10-bosque-county-campus:current-campus-development": (
        "under_construction",
        "2025-11-03",
    ),
    "curated:cyrusone-fra6-sossenheim-campus:current-brownfield-redevelopment": (
        "site_preparation",
        "2025-11-26",
    ),
    "curated:cyrusone-fra7-frankfurt-westside-campus:current-multi-building-development": (
        "under_construction",
        "2026-06-12",
    ),
    "curated:cyrusone-freestone-county-campus:initial-facility-build": (
        "under_construction",
        "2026-06-05",
    ),
    "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build": (
        "under_construction",
        "2025-08-19",
    ),
    "curated:cyrusone-new-albany-campus:building-1-current-build": (
        "under_construction",
        "2025-10-09",
    ),
}

EXPECTED_CAPACITIES = {
    (
        "curated:colt-frankfurt3-sossenheim-campus:frankfurt3-current-facility-build",
        "critical_it_mw",
        "planned",
        32.4,
    ),
    (
        "curated:colt-villebon-sur-yvette-campus:paris2-current-facility-build",
        "critical_it_mw",
        "planned",
        39.6,
    ),
    (
        "curated:cyrusone-dfw10-bosque-county-campus",
        "grid_connection_mw",
        "contracted",
        400.0,
    ),
    (
        "curated:cyrusone-fra6-sossenheim-campus:current-brownfield-redevelopment",
        "critical_it_mw",
        "planned",
        72.0,
    ),
    (
        "curated:cyrusone-fra7-frankfurt-westside-campus",
        "critical_it_mw",
        "planned",
        81.0,
    ),
    (
        "curated:cyrusone-freestone-county-campus:initial-facility-build",
        "grid_connection_mw",
        "contracted",
        380.0,
    ),
    (
        "curated:cyrusone-kep-osk1-seika-data-center:current-facility-build",
        "critical_it_mw",
        "planned",
        48.0,
    ),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class OpenSeedV14Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_exact_accounting(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_open_seed_release(DEFINITION, RELEASE)
            second = validate_open_seed_release(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first["entities"], 211)
        self.assertEqual(first["entities_by_kind"], {"campus": 138, "project": 73})
        self.assertEqual(first["evidence_records"], 156)
        self.assertEqual(first["capacity_estimates"], 369)
        self.assertEqual(first["construction_pipeline_records"], 114)
        self.assertEqual(first["construction_source_signals"], 104)
        self.assertEqual(first["resolution_candidates"], 4)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 211)
        self.assertEqual(summary["projects_total"], 73)
        self.assertEqual(summary["evidence_total"], 168)
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 2,
                "civil_works": 2,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 3,
                "operational": 31,
                "permitted": 2,
                "shell": 3,
                "site_preparation": 6,
                "under_construction": 67,
            },
        )

    def test_v13_rows_are_preserved_and_v14_is_exactly_additive(self) -> None:
        expected_deltas = {
            "entities.csv": 17,
            "evidence.csv": 16,
            "capacity_estimates.csv": 7,
            "construction_pipeline.csv": 9,
            "construction_source_signals.csv": 9,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous = rows(PREVIOUS_RELEASE / filename)
            current = rows(RELEASE / filename)
            previous_rows = {tuple(sorted(row.items())) for row in previous}
            current_rows = {tuple(sorted(row.items())) for row in current}
            self.assertTrue(previous_rows <= current_rows, filename)
            self.assertEqual(len(current) - len(previous), expected_delta, filename)

        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_inputs = {
            (record["path"], record["sha256"])
            for record in previous["curated_inputs"]
        }
        current_inputs = {
            (record["path"], record["sha256"])
            for record in current["curated_inputs"]
        }
        self.assertEqual(len(previous_inputs), 66)
        self.assertEqual(len(current_inputs), 75)
        self.assertTrue(previous_inputs < current_inputs)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )

    def test_new_sources_and_release_rows_keep_narrow_semantics(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        input_by_name = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(input_by_name[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])

        entities = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        self.assertEqual(NEW_ENTITY_KEYS - set(entities), set())
        self.assertEqual(
            len([key for key in entities if key == "curated:cyrusone-dfw10-bosque-county-campus"]),
            1,
        )
        for stable_key in NEW_ENTITY_KEYS:
            entity = entities[stable_key]
            self.assertEqual((entity["latitude"], entity["longitude"]), ("", ""))
            self.assertEqual((entity["owner"], entity["operator"], entity["users"]), ("", "", ""))
            self.assertEqual(entity["operating_model"], "")
            self.assertEqual(entity["workloads_json"], "[]")

        for stable_key, (status, as_of) in EXPECTED_STATUSES.items():
            self.assertEqual(entities[stable_key]["status"], status)
            self.assertEqual(entities[stable_key]["status_as_of"], as_of)
            self.assertNotIn(status, {"commissioning", "operational"})

        entity_id_to_key = {row["entity_id"]: row["stable_key"] for row in entities.values()}
        observed_capacities = {
            (
                entity_id_to_key[row["entity_id"]],
                row["metric"],
                row["stage"],
                float(row["base"]),
            )
            for row in rows(RELEASE / "capacity_estimates.csv")
            if entity_id_to_key[row["entity_id"]] in NEW_ENTITY_KEYS
        }
        self.assertEqual(observed_capacities, EXPECTED_CAPACITIES)
        self.assertTrue(
            all(metric in {"critical_it_mw", "grid_connection_mw"} for _, metric, _, _ in observed_capacities)
        )

        definition_text = DEFINITION.read_text(encoding="utf-8")
        self.assertNotIn("oracle-project-jupiter", definition_text)
        self.assertNotIn("edgeconnex-greater-osaka", definition_text)
        self.assertNotIn("vantage-lighthouse-port-washington", definition_text)
        self.assertNotIn("digital-realty-digital-dulles-current-development", definition_text)


if __name__ == "__main__":
    unittest.main()
