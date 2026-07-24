from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v32.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v32"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v31.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v31"

DEFINITION_SHA256 = "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
MANIFEST_SHA256 = "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
PREVIOUS_DEFINITION_SHA256 = (
    "15d5d8a29b2a1cef0a8cbfa1f24276ea5619f9811aab53959bf83cfb3b5050dd"
)
PREVIOUS_MANIFEST_SHA256 = (
    "f81df7005c17ee75ab09ff8e81d86589ad64bfe75164b10b5c643cc14d55f2ea"
)
RECORDED_AT = "2026-07-19T22:35:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-data4-ath1-first-data-center.json": (
        "028990145023dd581beff459437414324bcf76b0da893a2c46c0a13aa065df7c"
    ),
    "curated-official-2026-07-19-equinix-bk1-bangkok-phase-1.json": (
        "a7484b6bede27e681203268a9cd2a3d43366d231816f367cd42005bd03433747"
    ),
    "curated-official-2026-07-19-equinix-jh2-johor-phases-1-2.json": (
        "e1bcddf890dc2cd01c3d2313e251494cf73501569b8763722c4d9fd15b802505"
    ),
    "curated-official-2026-07-19-equinix-lg4-lagos-phase-1.json": (
        "febd36ed1e50cec8d35f81b610072931d9ed39992c54fc2bdfc695a2ee615ca9"
    ),
    "curated-official-2026-07-19-equinix-sg6-singapore-phase-1.json": (
        "9624e173b67e49323c30bd25954fb0d8e1bc77eeee60a57de8707354a9766707"
    ),
    "curated-official-2026-07-19-google-canelones-uruguay.json": (
        "7ca2b59fdddc843e62d8e1661e13416daa109238bdf37ef414decff53af586a7"
    ),
    "curated-official-2026-07-19-viettel-tan-phu-trung-hcmc.json": (
        "ecdf26ee064eb9513867940211e0c4c07a51fade9aa94786279542465f46b652"
    ),
}
TRANCHE_TEST_HASHES = {
    "test_curated_equinix_lg4_bk1_jh2_sg6.py": (
        "63cbbf054911cc6416dd21f9ef72d60616dd5add938dbb2e0a409216b51e8a04"
    ),
    "test_curated_google_viettel_data4.py": (
        "c5b5550ba8f22d95ef778ae2f49b269b4a9ea4393d36bdb35606e2411618d0fb"
    ),
}

CAMPUS_KEYS = {
    "curated:data4-ath1-paiania-campus",
    "curated:equinix-bk1-bangkok-data-center",
    "curated:equinix-jh2-johor-data-center",
    "curated:equinix-lg4-lagos-data-center",
    "curated:equinix-sg6-singapore-data-center",
    "curated:google-parque-de-las-ciencias-data-center-campus",
    "curated:viettel-tan-phu-trung-data-center-campus",
}
PROJECT_KEYS = {
    "curated:data4-ath1-paiania-campus:first-data-center",
    "curated:equinix-bk1-bangkok-data-center:phase-1",
    "curated:equinix-jh2-johor-data-center:phases-1-and-2",
    "curated:equinix-lg4-lagos-data-center:phase-1",
    "curated:equinix-sg6-singapore-data-center:phase-1",
    "curated:google-parque-de-las-ciencias-data-center-campus:data-center-project",
    "curated:viettel-tan-phu-trung-data-center-campus:high-tech-data-rd-center",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
EQUINIX_PROJECT_KEYS = {
    key for key in PROJECT_KEYS if key.startswith("curated:equinix-")
}

SOURCE_EVIDENCE_HASHES = {
    "24071a2e81a9bad978a0dca46c427dc75d99b4a48fede7381bda4acce139c3e8",
    "252b6498c5780f2e0ae63119267fe4b0e26cc5cb56c76a98208ef0c97809aed5",
    "3036824a2f3e4db6b0c2051287d24a73bff99a273a00537c20cb9cb9ee9ec770",
    "3aa58d57fb70fa904d467e5456c31de365151e4833a60f36fdf8b3878de557f6",
    "8336a93fcad5e06e386eb82a3a0f38edad2eb9f5d44b0847ddde12a61d0ce82f",
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54",
    "bb095d16556595f008438f75f0f4ec80338d571a09005b68c6e4933f0f5b0d8d",
    "de06c22ffb3a4587772bd3de6b98baac3bb84f16c48dcf178da74db296fc5734",
}
EXPORTED_NEW_EVIDENCE_HASHES = {
    "24071a2e81a9bad978a0dca46c427dc75d99b4a48fede7381bda4acce139c3e8",
    "252b6498c5780f2e0ae63119267fe4b0e26cc5cb56c76a98208ef0c97809aed5",
    "3036824a2f3e4db6b0c2051287d24a73bff99a273a00537c20cb9cb9ee9ec770",
    "3aa58d57fb70fa904d467e5456c31de365151e4833a60f36fdf8b3878de557f6",
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54",
    "de06c22ffb3a4587772bd3de6b98baac3bb84f16c48dcf178da74db296fc5734",
}
STATUS_CONTENT_HASHES = {
    "252b6498c5780f2e0ae63119267fe4b0e26cc5cb56c76a98208ef0c97809aed5",
    "3aa58d57fb70fa904d467e5456c31de365151e4833a60f36fdf8b3878de557f6",
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54",
    "de06c22ffb3a4587772bd3de6b98baac3bb84f16c48dcf178da74db296fc5734",
}
NEW_SOURCE_FAMILIES = {
    "data4_csr_reports",
    "data4_location_pages",
    "uruguay_presidency_news",
    "vietnam_news_agency_vietnamplus",
    "viettel_official_linkedin",
}
EXPECTED_SIGNAL_ENTITY_COUNTS = {
    "252b6498c5780f2e0ae63119267fe4b0e26cc5cb56c76a98208ef0c97809aed5": 1,
    "3aa58d57fb70fa904d467e5456c31de365151e4833a60f36fdf8b3878de557f6": 1,
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54": 4,
    "de06c22ffb3a4587772bd3de6b98baac3bb84f16c48dcf178da74db296fc5734": 1,
}
PROJECT_STATUS_METHODS = {
    "curated:data4-ath1-paiania-campus:first-data-center": (
        "authoritative_construction_start"
    ),
    "curated:equinix-bk1-bangkok-data-center:phase-1": (
        "authoritative_physical_status_update"
    ),
    "curated:equinix-jh2-johor-data-center:phases-1-and-2": (
        "authoritative_physical_status_update"
    ),
    "curated:equinix-lg4-lagos-data-center:phase-1": (
        "authoritative_physical_status_update"
    ),
    "curated:equinix-sg6-singapore-data-center:phase-1": (
        "authoritative_physical_status_update"
    ),
    "curated:google-parque-de-las-ciencias-data-center-campus:data-center-project": (
        "authoritative_physical_status_update"
    ),
    "curated:viettel-tan-phu-trung-data-center-campus:high-tech-data-rd-center": (
        "authoritative_construction_start"
    ),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_signature(row: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(row.items()))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(row_signature(row) for row in rows(path))


def added_rows(filename: str) -> list[dict[str, str]]:
    previous = row_counter(PREVIOUS_RELEASE / filename)
    added: list[dict[str, str]] = []
    for row in rows(RELEASE / filename):
        signature = row_signature(row)
        if previous[signature]:
            previous[signature] -= 1
        else:
            added.append(row)
    return added


def load_new_documents() -> dict[str, dict[str, object]]:
    documents: dict[str, dict[str, object]] = {}
    for filename in SOURCE_HASHES:
        document = json.loads((ROOT / "sources" / filename).read_text(encoding="utf-8"))
        documents[document["campus"]["stable_key"]] = document
    return documents


class OpenSeedV32Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertTrue(entries)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in entries))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries))
        frozen = {path.name: path.read_bytes() for path in entries}

        offline = AssertionError("offline validator attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first = validate_open_seed_release(DEFINITION, RELEASE)
            self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
            second = validate_open_seed_release(DEFINITION, RELEASE)

        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 370)
        self.assertEqual(first["entities_by_kind"], {"campus": 216, "project": 154})
        self.assertEqual(first["evidence_records"], 226)
        self.assertEqual(first["capacity_estimates"], 401)
        self.assertEqual(first["construction_pipeline_records"], 195)
        self.assertEqual(first["construction_source_signals"], 161)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 370)
        self.assertEqual(summary["projects_total"], 154)
        self.assertEqual(summary["evidence_total"], 252)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 127)
        self.assertEqual(summary["entities_by_country"]["Greece"], 2)
        self.assertEqual(summary["entities_by_country"]["Malaysia"], 9)
        self.assertEqual(summary["entities_by_country"]["Nigeria"], 4)
        self.assertEqual(summary["entities_by_country"]["Singapore"], 6)
        self.assertEqual(summary["entities_by_country"]["Thailand"], 12)
        self.assertEqual(summary["entities_by_country"]["Uruguay"], 2)
        self.assertEqual(summary["entities_by_country"]["Viet Nam"], 2)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4874.6, "count": 45, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["grid_connection_mw"]["contracted"],
            {"base": 2560.0, "count": 5, "unit": "MW"},
        )

    def test_v31_closure_and_exact_multiset_additivity(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PREVIOUS_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PREVIOUS_RELEASE.iterdir()
            )
        )

        expected_deltas = {
            "entities.csv": 14,
            "evidence.csv": 6,
            "capacity_estimates.csv": 0,
            "construction_pipeline.csv": 7,
            "construction_source_signals.csv": 4,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            previous = row_counter(PREVIOUS_RELEASE / filename)
            current = row_counter(RELEASE / filename)
            self.assertEqual(previous & current, previous, filename)
            self.assertEqual(sum(current.values()) - sum(previous.values()), expected_delta)
            self.assertEqual(sum((current - previous).values()), expected_delta, filename)
            self.assertEqual(sum((previous - current).values()), 0, filename)

        previous_geojson = json.loads(
            (PREVIOUS_RELEASE / "atlas.geojson").read_text(encoding="utf-8")
        )
        current_geojson = json.loads(
            (RELEASE / "atlas.geojson").read_text(encoding="utf-8")
        )
        previous_features = {
            feature["properties"]["stable_key"]: feature
            for feature in previous_geojson["features"]
        }
        current_features = {
            feature["properties"]["stable_key"]: feature
            for feature in current_geojson["features"]
        }
        self.assertEqual(
            {key: current_features[key] for key in previous_features}, previous_features
        )
        self.assertEqual(set(current_features) - set(previous_features), NEW_ENTITY_KEYS)
        self.assertTrue(all(current_features[key]["geometry"] is None for key in NEW_ENTITY_KEYS))

        for filename in (
            "capacity_estimates.csv",
            "resolution_candidates.csv",
            "resolution_candidates.json",
        ):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (PREVIOUS_RELEASE / filename).read_bytes(),
                filename,
            )

        previous_sources = json.loads(
            (PREVIOUS_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        current_sources = json.loads(
            (RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        previous_records = Counter(
            json.dumps(record, sort_keys=True) for record in previous_sources
        )
        current_records = Counter(
            json.dumps(record, sort_keys=True) for record in current_sources
        )
        self.assertEqual(previous_records & current_records, previous_records)
        added_sources = [
            json.loads(record)
            for record in (current_records - previous_records).elements()
        ]
        self.assertEqual(len(added_sources), 6)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EXPORTED_NEW_EVIDENCE_HASHES,
        )
        equinix_sources = [
            record
            for record in added_sources
            if record["provenance"]["content_hash"]
            == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
        ]
        self.assertEqual(len(equinix_sources), 1)
        self.assertEqual(
            equinix_sources[0]["provenance"]["curated_record_key"],
            "equinix-2025-form-10-k-lg4-bk1-jh2-sg6-construction-table-captured-2026-07-19",
        )
        previous_equinix_sources = [
            record
            for record in previous_sources
            if record["provenance"].get("content_hash")
            == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
        ]
        current_equinix_sources = [
            record
            for record in current_sources
            if record["provenance"].get("content_hash")
            == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
        ]
        self.assertEqual(len(previous_equinix_sources), 1)
        self.assertEqual(len(current_equinix_sources), 2)
        self.assertEqual(
            {
                record["provenance"]["curated_record_key"]
                for record in previous_equinix_sources
            },
            {"equinix-2025-form-10-k-construction-table-captured-2026-07-19"},
        )
        self.assertEqual(
            {
                record["provenance"]["curated_record_key"]
                for record in current_equinix_sources
            },
            {
                "equinix-2025-form-10-k-construction-table-captured-2026-07-19",
                "equinix-2025-form-10-k-lg4-bk1-jh2-sg6-construction-table-captured-2026-07-19",
            },
        )

        previous_manifest = json.loads(
            (PREVIOUS_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        current_manifest = json.loads(
            (RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(current_manifest["source_families"])
            - set(previous_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 8)
        self.assertEqual(
            current_summary["entities_by_status"]["under_construction"]
            - previous_summary["entities_by_status"]["under_construction"],
            7,
        )

    def test_definition_is_exactly_seven_sorted_inputs_additive(self) -> None:
        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        previous_inputs = {
            (record["path"], record["sha256"]) for record in previous["curated_inputs"]
        }
        current_inputs = {
            (record["path"], record["sha256"]) for record in current["curated_inputs"]
        }
        expected_additions = {
            (f"sources/{filename}", digest) for filename, digest in SOURCE_HASHES.items()
        }
        self.assertEqual(len(previous_inputs), 150)
        self.assertEqual(len(current_inputs), 157)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)

        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v32")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in set(previous) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], previous[key], key)

    def test_source_hashes_schema_and_metadata_only_quantities(self) -> None:
        for filename, expected_hash in TRANCHE_TEST_HASHES.items():
            self.assertEqual(
                hashlib.sha256((ROOT / "tests" / filename).read_bytes()).hexdigest(),
                expected_hash,
            )

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        inputs = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents = load_new_documents()
        self.assertEqual(set(documents), CAMPUS_KEYS)

        evidence_occurrences = []
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(inputs[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(
                set(document),
                {
                    "campus",
                    "capacities",
                    "evidence",
                    "lifecycle",
                    "operating_models",
                    "project",
                    "schema_version",
                    "workloads",
                },
            )
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            self.assertEqual(document["lifecycle"][0]["value"], "under_construction")
            evidence_occurrences.extend(document["evidence"])
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")

        self.assertEqual(
            {document["project"]["stable_key"] for document in documents.values()},
            PROJECT_KEYS,
        )
        self.assertEqual(len(evidence_occurrences), 11)
        self.assertEqual(
            {evidence["content_hash"] for evidence in evidence_occurrences},
            SOURCE_EVIDENCE_HASHES,
        )

        data4 = documents["curated:data4-ath1-paiania-campus"]
        data4_evidence = {evidence["key"]: evidence for evidence in data4["evidence"]}
        announcement = data4_evidence[
            "data4-ath1-paiania-announcement-2024-09-20-captured-2026-07-19"
        ]["metadata"]
        location = data4_evidence[
            "data4-athens-campus-current-location-captured-2026-07-19"
        ]["metadata"]
        self.assertEqual(announcement["reported_power_capacity_mw_maximum"], 90)
        self.assertEqual(location["reported_available_electricity_reserves_mw"], 90)
        self.assertIn("no normalized capacity row", announcement["power_metric_guardrail"])
        self.assertIn("no normalized capacity row", location["power_metric_guardrail"])

        google = documents["curated:google-parque-de-las-ciencias-data-center-campus"]
        google_evidence = {evidence["key"]: evidence for evidence in google["evidence"]}
        google_blog = google_evidence[
            "google-canelones-construction-start-2024-08-29-captured-2026-07-19"
        ]["metadata"]
        presidency = google_evidence[
            "uruguay-presidency-google-canelones-construction-2026-04-14-captured-2026-07-19"
        ]["metadata"]
        self.assertEqual(google_blog["reported_project_investment_usd"], 850_000_000)
        self.assertEqual(google_blog["reported_project_investment_qualifier"], "more than")
        self.assertIn("850.000.000", presidency["reported_project_investment_wording_as_reported"])
        self.assertIn("metadata only", google_blog["investment_guardrail"])
        self.assertIn("metadata only", presidency["investment_guardrail"])

        viettel = documents["curated:viettel-tan-phu-trung-data-center-campus"]
        vna = next(
            evidence["metadata"]
            for evidence in viettel["evidence"]
            if evidence["key"].startswith("vna-viettel")
        )
        self.assertEqual(vna["reported_design_or_projected_power_mw"], 140)
        self.assertEqual(vna["reported_target_pue_inequality"], "< 1.4")
        self.assertEqual(vna["reported_design_standard_wording_as_reported"], "Uptime Tier III")
        self.assertEqual(vna["reported_rack_count_approximate"], 10_000)
        self.assertEqual(vna["reported_average_rack_density_kw"], 10)
        self.assertEqual(vna["reported_maximum_rack_density_kw"], 60)
        self.assertIn("no normalized capacity row", vna["power_metric_guardrail"])
        self.assertIn("no structured PUE observation", vna["pue_guardrail"])
        self.assertIn("does not establish certification", vna["certification_guardrail"])
        self.assertIn("not multiplied", vna["rack_metric_guardrail"])

        equinix_documents = [
            document
            for key, document in documents.items()
            if key.startswith("curated:equinix-")
        ]
        self.assertEqual(len(equinix_documents), 4)
        canonical_evidence = json.dumps(
            equinix_documents[0]["evidence"][0], sort_keys=True
        )
        self.assertTrue(
            all(
                json.dumps(document["evidence"][0], sort_keys=True) == canonical_evidence
                for document in equinix_documents
            )
        )
        equinix = equinix_documents[0]["evidence"][0]["metadata"]
        self.assertEqual(
            equinix["target_projects_as_reported"],
            [
                {
                    "property": "LG4 phase 1",
                    "location": "Lagos",
                    "target_open_quarter": "Q4 2027",
                    "sellable_cabinets": 975,
                    "approximate_total_capex_usd_millions": 78,
                },
                {
                    "property": "BK1 phase 1",
                    "location": "Bangkok",
                    "target_open_quarter": "Q3 2027",
                    "sellable_cabinets": 1175,
                    "approximate_total_capex_usd_millions": 110,
                },
                {
                    "property": "JH2 phases 1 and 2",
                    "location": "Johor",
                    "target_open_quarter": "Q3 2027",
                    "sellable_cabinets": 2225,
                    "approximate_total_capex_usd_millions": 201,
                },
                {
                    "property": "SG6 phase 1",
                    "location": "Singapore",
                    "target_open_quarter": "Q1 2027",
                    "sellable_cabinets": 1550,
                    "approximate_total_capex_usd_millions": 290,
                },
            ],
        )
        self.assertEqual(
            equinix["sg6_full_build_capacity_as_reported_mw_untyped_context"], 20
        )
        self.assertIn("not typed as critical IT", equinix["sg6_capacity_guardrail"])
        self.assertIn("no workload", equinix["sg6_ai_ready_guardrail"])
        self.assertIn("create no capacity", equinix["cabinet_guardrail"])
        self.assertIn("create no capacity", equinix["capex_guardrail"])
        self.assertIn("remain evidence metadata", equinix["target_date_guardrail"])

    def test_export_adds_generic_lifecycle_only_without_semantic_leakage(self) -> None:
        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_rows = {
            row["stable_key"]: row for row in rows(PREVIOUS_RELEASE / "entities.csv")
        }
        self.assertEqual(set(entity_rows) - set(previous_rows), NEW_ENTITY_KEYS)
        self.assertEqual(
            {key: entity_rows[key] for key in previous_rows},
            previous_rows,
        )
        self.assertEqual(len(entity_rows), len(rows(RELEASE / "entities.csv")))

        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertFalse(
                any(name.startswith("role:") for name in json.loads(row["tags_json"]))
            )
        for key in CAMPUS_KEYS:
            self.assertEqual(entity_rows[key]["status"], "")
            self.assertEqual(entity_rows[key]["status_method"], "")
        for key, method in PROJECT_STATUS_METHODS.items():
            self.assertEqual(entity_rows[key]["status"], "under_construction")
            self.assertEqual(entity_rows[key]["status_method"], method)

        self.assertEqual(added_rows("capacity_estimates.csv"), [])
        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )
        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 4)
        self.assertEqual(
            {signal["source_content_hash"] for signal in added_signals},
            STATUS_CONTENT_HASHES,
        )
        self.assertEqual(
            {
                signal["source_content_hash"]: int(signal["affected_entity_count"])
                for signal in added_signals
            },
            EXPECTED_SIGNAL_ENTITY_COUNTS,
        )
        affected_by_hash = {
            signal["source_content_hash"]: {
                entity["stable_key"]
                for entity in json.loads(signal["affected_entities_json"])
            }
            for signal in added_signals
        }
        self.assertEqual(
            affected_by_hash[
                "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
            ],
            EQUINIX_PROJECT_KEYS,
        )
        self.assertEqual(
            set().union(*affected_by_hash.values()),
            PROJECT_KEYS,
        )

        added_evidence = added_rows("evidence.csv")
        self.assertEqual(len(added_evidence), 6)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence},
            EXPORTED_NEW_EVIDENCE_HASHES,
        )
        self.assertEqual(
            sum(
                row["content_hash"]
                == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
                for row in added_evidence
            ),
            1,
        )
        self.assertEqual(
            sum(
                row["content_hash"]
                == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
                for row in rows(PREVIOUS_RELEASE / "evidence.csv")
            ),
            1,
        )
        self.assertEqual(
            sum(
                row["content_hash"]
                == "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
                for row in rows(RELEASE / "evidence.csv")
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
