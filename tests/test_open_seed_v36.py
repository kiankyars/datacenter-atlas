from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import copy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import (
    OpenSeedReleaseError,
    validate_open_seed_release,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v36.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v36"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v35.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v35"

DEFINITION_SHA256 = "3ab5d787cfc21d644f4be883a061bb934d8c6014ef9c5b93c9cd6cab870694b7"
MANIFEST_SHA256 = "30bbc607d51dedd558ff698738314f2a22c9acde86608928433825f9d0940e7b"
PREVIOUS_DEFINITION_SHA256 = (
    "ade1722f44a8a97f848d94579a4cfc45bc96f7f706df80f38ad6c46cabc5735d"
)
PREVIOUS_MANIFEST_SHA256 = (
    "47994a012f4a97ca6dcdafb55c6b98a7121397a843ec1857328acd7953988123"
)
RECORDED_AT = "2026-07-20T01:15:00Z"
AS_OF = "2026-07-20"

SOURCE_HASHES = {
    "curated-official-2026-07-20-digital-edge-cgk1-bekasi.json": (
        "f2634a600ced7b901b84af36817881cdf9f060dd8aed56cfa1489c2e4f1d7432"
    ),
    "curated-official-2026-07-20-green-zrh1-dc4-lupfig.json": (
        "7161ad1721c77f39b432aa3b0ebf8de42c8140230b61c5a89ea843ea664d868e"
    ),
    "curated-official-2026-07-20-iij-shiroi-phase-3.json": (
        "ed214cfed7495ad6b1cf7a65f2cc1e90d80d12b58b615afb2931b98cb0bb6714"
    ),
    "curated-official-2026-07-20-macquarie-ic3-super-west-phase-1.json": (
        "9fe5625d1cbb2d59dbeb8d329ab1b79fb65a7e43346161f2c92901076cc7cb4f"
    ),
    "curated-official-2026-07-20-merlin-lisbon-phase-2.json": (
        "30aa6dda670bdeecd03fe47eb0dc8e39bd5b6f08b44fba5ee2442579c0c5e587"
    ),
    "curated-official-2026-07-20-moro-hub-warsan-phase-1.json": (
        "c74dd8a78f2a9fd5fabdb95637fc26680958473a20a3f84f4296b0b87b2034c6"
    ),
    "curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json": (
        "2efccf401355b50ce559e64c060d5cf6f1350d326440c0035ce63bf008e07d73"
    ),
}

SOURCE_KEYS = {
    "curated-official-2026-07-20-digital-edge-cgk1-bekasi.json": (
        "curated:digital-edge-cgk-campus-bekasi",
        "curated:digital-edge-cgk-campus-bekasi:cgk1",
    ),
    "curated-official-2026-07-20-green-zrh1-dc4-lupfig.json": (
        "curated:green-campus-zrh1-lupfig",
        "curated:green-campus-zrh1-lupfig:data-center-4",
    ),
    "curated-official-2026-07-20-iij-shiroi-phase-3.json": (
        "curated:iij-shiroi-data-center-campus",
        "curated:iij-shiroi-data-center-campus:phase-3-server-building",
    ),
    "curated-official-2026-07-20-macquarie-ic3-super-west-phase-1.json": (
        "curated:macquarie-ic3-super-west-facility",
        "curated:macquarie-ic3-super-west-facility:phase-1-build",
    ),
    "curated-official-2026-07-20-merlin-lisbon-phase-2.json": (
        "curated:merlin-lisbon-data-center-campus",
        "curated:merlin-lisbon-data-center-campus:phase-2-two-building-development",
    ),
    "curated-official-2026-07-20-moro-hub-warsan-phase-1.json": (
        "curated:moro-hub-warsan-new-green-data-centre",
        "curated:moro-hub-warsan-new-green-data-centre:phase-1",
    ),
    "curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json": (
        "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-campus",
        (
            "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-"
            "campus:planned-data-hall-building"
        ),
    ),
}
CAMPUS_KEYS = {keys[0] for keys in SOURCE_KEYS.values()}
PROJECT_KEYS = {keys[1] for keys in SOURCE_KEYS.values()}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
SOFTBANK_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json"
][1]
CGK_CAMPUS_KEY, CGK_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-digital-edge-cgk1-bekasi.json"
]
GREEN_CAMPUS_KEY, GREEN_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-green-zrh1-dc4-lupfig.json"
]
IIJ_CAMPUS_KEY, IIJ_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-iij-shiroi-phase-3.json"
]
IC3_CAMPUS_KEY, IC3_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-macquarie-ic3-super-west-phase-1.json"
]
MERLIN_CAMPUS_KEY, MERLIN_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-merlin-lisbon-phase-2.json"
]
MORO_CAMPUS_KEY, MORO_PROJECT_KEY = SOURCE_KEYS[
    "curated-official-2026-07-20-moro-hub-warsan-phase-1.json"
]

ALL_SOURCE_EVIDENCE_HASHES = {
    "0a7bbd094f67937d1453e784c12c56e15e99c3ffab8a76c51b2fad9c7ffc2d25",
    "182adde10e93ad9818a8bb9bb815d9416511429252807d385d503a3ac8e72276",
    "9e4570b465ab66b282d46dd5008216b575b250e4ea4438fa8fc4839b90988f13",
    "16a1571bb186309f7acde2221984e742de9c6d8e743c8048a1b020cb14de0a06",
    "f0b9f73134963abe529a1a39373fd89b983a855e2972bfc8e4d3ac5c2e716d3f",
    "f8f86d1d3f36d46c81f9fe23edce1416f11193e7a16fc32014f98acd96f053e3",
    "aea8b63b826c60a6e2027712d124a087c032f2073b611a0ca81b0742a4f5d9f9",
    "bc455a2fa3310e76108b15e8459292aea83dea36beb0fafbc91d2e17ec04e6ce",
    "c189dce34805edb292c07c6204122b6e4a9d8d30cd7cd7e91080ea92905edd1e",
    "02ab48dcfbb12802f3e2c01789f26acff3e516832b074645b7b160aa241372b0",
    "a241bca1a18774e0b82c7b2d23e59dbf86bbb30cc1160604808de34e626d3ce4",
    "d665d479045420e991eba21ab02f6fe3bc01607cf2cb7382895427a8defb33e3",
    "7c9f965f4d6c229f0aaab2ecd4584d9943c6d6fca13ed6c528316c72956d18b8",
}
EXPORTED_EVIDENCE_HASHES = ALL_SOURCE_EVIDENCE_HASHES - {
    "182adde10e93ad9818a8bb9bb815d9416511429252807d385d503a3ac8e72276"
}
STATUS_EVIDENCE_HASHES = {
    "0a7bbd094f67937d1453e784c12c56e15e99c3ffab8a76c51b2fad9c7ffc2d25",
    "9e4570b465ab66b282d46dd5008216b575b250e4ea4438fa8fc4839b90988f13",
    "f0b9f73134963abe529a1a39373fd89b983a855e2972bfc8e4d3ac5c2e716d3f",
    "aea8b63b826c60a6e2027712d124a087c032f2073b611a0ca81b0742a4f5d9f9",
    "c189dce34805edb292c07c6204122b6e4a9d8d30cd7cd7e91080ea92905edd1e",
    "a241bca1a18774e0b82c7b2d23e59dbf86bbb30cc1160604808de34e626d3ce4",
    "d665d479045420e991eba21ab02f6fe3bc01607cf2cb7382895427a8defb33e3",
}
NEW_SOURCE_FAMILIES = {
    "digital_edge_indonesia_newsroom",
    "green_data_center_facility_pages",
    "iij_investor_relations",
    "iij_press_releases",
    "macquarie_data_centres_facility_pages",
    "macquarie_data_centres_newsroom",
    "macquarie_data_centres_specifications",
    "merlin_properties_asset_pages",
    "merlin_properties_press_releases",
    "moro_hub_news",
    "softbank_news",
    "softbank_sustainability",
}
EXPECTED_PROJECT_STATUS = {
    CGK_PROJECT_KEY: ("shell", "2026-06-08"),
    GREEN_PROJECT_KEY: ("under_construction", "2026-07-20"),
    IIJ_PROJECT_KEY: ("under_construction", "2026-06-25"),
    IC3_PROJECT_KEY: ("under_construction", "2026-07-17"),
    MERLIN_PROJECT_KEY: ("under_construction", "2026-05-13"),
    MORO_PROJECT_KEY: ("under_construction", "2026-01-23"),
    SOFTBANK_PROJECT_KEY: ("under_construction", "2025-05-01"),
}
EXPECTED_CAPACITIES = {
    (CGK_CAMPUS_KEY, "critical_it_mw", "planned", "MW", 500.0, "reported"),
    (CGK_CAMPUS_KEY, "pue", "design", "ratio", 1.25, "reported"),
    (IIJ_PROJECT_KEY, "grid_connection_mw", "planned", "MW", 10.0, "reported"),
    (IC3_CAMPUS_KEY, "critical_it_mw", "planned", "MW", 47.0, "reported"),
    (IC3_CAMPUS_KEY, "pue", "design", "ratio", 1.28, "reported"),
    (IC3_PROJECT_KEY, "critical_it_mw", "planned", "MW", 6.0, "reported"),
    (MERLIN_PROJECT_KEY, "critical_it_mw", "planned", "MW", 80.0, "calculated"),
    (SOFTBANK_PROJECT_KEY, "grid_connection_mw", "planned", "MW", 50.0, "reported"),
}
CSV_COUNTS = {
    "entities.csv": (388, 402, 14),
    "evidence.csv": (236, 248, 12),
    "capacity_estimates.csv": (405, 413, 8),
    "construction_pipeline.csv": (204, 211, 7),
    "construction_source_signals.csv": (170, 177, 7),
    "resolution_candidates.csv": (4, 4, 0),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def by_id(path: Path, field: str) -> dict[str, dict[str, str]]:
    source_rows = rows(path)
    result = {row[field]: row for row in source_rows}
    if len(result) != len(source_rows):
        raise AssertionError(f"duplicate {field} in {path}")
    return result


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


def physical_record_counter(path: Path) -> Counter[bytes]:
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) != len(rows(path)) + 1:
        raise AssertionError(f"embedded newline in CSV record: {path}")
    return Counter(lines[1:])


class OpenSeedV36Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v36 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(
                    patch.object(socket, name, side_effect=network_error)
                )
            return validate_open_seed_release(DEFINITION, RELEASE)

    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)

        entries = list(RELEASE.iterdir())
        self.assertEqual(len(entries), 13)
        self.assertTrue(
            all(path.is_file() and not path.is_symlink() for path in entries)
        )
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries)
        )
        frozen = {path.name: path.read_bytes() for path in entries}

        first = self._validate_offline()
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(
            {
                "as_of": first["as_of"],
                "recorded_at": first["recorded_at"],
                "entities": first["entities"],
                "entities_by_kind": first["entities_by_kind"],
                "evidence_records": first["evidence_records"],
                "capacity_estimates": first["capacity_estimates"],
                "construction_pipeline_records": first[
                    "construction_pipeline_records"
                ],
                "construction_source_signals": first[
                    "construction_source_signals"
                ],
                "resolution_candidates": first["resolution_candidates"],
            },
            {
                "as_of": AS_OF,
                "recorded_at": RECORDED_AT,
                "entities": 402,
                "entities_by_kind": {"campus": 232, "project": 170},
                "evidence_records": 248,
                "capacity_estimates": 413,
                "construction_pipeline_records": 211,
                "construction_source_signals": 177,
                "resolution_candidates": 4,
            },
        )

    def test_definition_is_exact_sorted_v35_plus_seven_successor(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        additions = [
            {"path": f"sources/{name}", "sha256": digest}
            for name, digest in SOURCE_HASHES.items()
        ]
        expected_inputs = sorted(
            previous["curated_inputs"] + additions, key=lambda row: row["path"]
        )
        self.assertEqual(len(previous["curated_inputs"]), 166)
        self.assertEqual(len(current["curated_inputs"]), 173)
        self.assertEqual(current["curated_inputs"], expected_inputs)
        self.assertEqual(
            set(map(tuple, (tuple(sorted(row.items())) for row in current["curated_inputs"])))
            - set(map(tuple, (tuple(sorted(row.items())) for row in previous["curated_inputs"]))),
            set(map(tuple, (tuple(sorted(row.items())) for row in additions))),
        )
        input_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(set(input_paths)), 173)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v36")
        self.assertEqual(
            current["build"], {"as_of": AS_OF, "recorded_at": RECORDED_AT}
        )
        self.assertEqual(previous["build"]["as_of"], current["build"]["as_of"])
        self.assertEqual(
            current["scope"],
            {
                "commercial_census_parity_claimed": False,
                "epoch_selected_site_count_is_global_census": False,
                "orphan_timeline_imported": False,
                "source_scoped_estimates_only": True,
            },
        )
        for key in set(previous) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], previous[key], key)

        documents = {}
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash
            )
            document = json.loads(source.read_text(encoding="utf-8"))
            documents[filename] = document
            self.assertEqual(
                (document["campus"]["stable_key"], document["project"]["stable_key"]),
                SOURCE_KEYS[filename],
            )
            self.assertEqual(
                len({row["retrieved_at"] for row in document["evidence"]}), 1
            )

        self.assertEqual(
            {
                evidence["content_hash"]
                for document in documents.values()
                for evidence in document["evidence"]
            },
            ALL_SOURCE_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {
                evidence["source_family"]
                for document in documents.values()
                for evidence in document["evidence"]
            },
            NEW_SOURCE_FAMILIES,
        )

    def test_every_v35_csv_record_is_byte_identical_and_preserved(self) -> None:
        for filename, (previous_count, current_count, delta) in CSV_COUNTS.items():
            self.assertEqual(
                (PREVIOUS_RELEASE / filename).read_bytes().splitlines(keepends=True)[0],
                (RELEASE / filename).read_bytes().splitlines(keepends=True)[0],
                filename,
            )
            before = physical_record_counter(PREVIOUS_RELEASE / filename)
            after = physical_record_counter(RELEASE / filename)
            self.assertEqual(sum(before.values()), previous_count, filename)
            self.assertEqual(sum(after.values()), current_count, filename)
            self.assertEqual(before & after, before, filename)
            self.assertEqual(sum((after - before).values()), delta, filename)
            self.assertEqual(sum((before - after).values()), 0, filename)

        self.assertEqual(
            (RELEASE / "resolution_candidates.json").read_bytes(),
            (PREVIOUS_RELEASE / "resolution_candidates.json").read_bytes(),
        )

    def test_exact_new_entities_evidence_pipeline_signals_and_families(self) -> None:
        previous_entities = by_id(PREVIOUS_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        self.assertEqual(
            {key: current_entities[key] for key in previous_entities},
            previous_entities,
        )
        added_entities = [
            current_entities[key]
            for key in set(current_entities) - set(previous_entities)
        ]
        self.assertEqual(len(added_entities), 14)
        self.assertEqual(
            {row["stable_key"] for row in added_entities}, NEW_ENTITY_KEYS
        )
        for row in added_entities:
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["operating_model_confidence"], "")
            self.assertEqual(row["operating_model_evidence_id"], "")
            if row["stable_key"] in CAMPUS_KEYS:
                self.assertEqual((row["status"], row["status_as_of"]), ("", ""))
            else:
                self.assertEqual(
                    (row["status"], row["status_as_of"]),
                    EXPECTED_PROJECT_STATUS[row["stable_key"]],
                )

        previous_evidence = by_id(PREVIOUS_RELEASE / "evidence.csv", "evidence_id")
        current_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        self.assertEqual(
            {key: current_evidence[key] for key in previous_evidence},
            previous_evidence,
        )
        added_evidence = [
            current_evidence[key]
            for key in set(current_evidence) - set(previous_evidence)
        ]
        self.assertEqual(len(added_evidence), 12)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence},
            EXPORTED_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {row["source_family"] for row in added_evidence},
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual({row["kind"] for row in added_evidence}, {"company_disclosure"})

        previous_pipeline = by_id(
            PREVIOUS_RELEASE / "construction_pipeline.csv", "entity_id"
        )
        current_pipeline = by_id(RELEASE / "construction_pipeline.csv", "entity_id")
        self.assertEqual(
            {key: current_pipeline[key] for key in previous_pipeline},
            previous_pipeline,
        )
        added_pipeline = [
            current_pipeline[key]
            for key in set(current_pipeline) - set(previous_pipeline)
        ]
        self.assertEqual(len(added_pipeline), 7)
        self.assertEqual(
            {row["stable_key"] for row in added_pipeline}, PROJECT_KEYS
        )
        self.assertEqual(
            {
                row["stable_key"]: (row["status"], row["status_as_of"])
                for row in added_pipeline
            },
            EXPECTED_PROJECT_STATUS,
        )

        signal_id = "source_observation_evidence_id"
        previous_signals = by_id(
            PREVIOUS_RELEASE / "construction_source_signals.csv", signal_id
        )
        current_signals = by_id(
            RELEASE / "construction_source_signals.csv", signal_id
        )
        self.assertEqual(
            {key: current_signals[key] for key in previous_signals},
            previous_signals,
        )
        added_signals = [
            current_signals[key]
            for key in set(current_signals) - set(previous_signals)
        ]
        self.assertEqual(len(added_signals), 7)
        self.assertEqual(
            {row["source_content_hash"] for row in added_signals},
            STATUS_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {row["representative_stable_key"] for row in added_signals},
            PROJECT_KEYS,
        )
        self.assertEqual(
            {
                row["representative_stable_key"]: (
                    row["representative_status"],
                    row["representative_status_as_of"],
                )
                for row in added_signals
            },
            EXPECTED_PROJECT_STATUS,
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

    def test_capacity_workload_and_normalization_guardrails_are_exact(self) -> None:
        before = row_counter(PREVIOUS_RELEASE / "capacity_estimates.csv")
        after = row_counter(RELEASE / "capacity_estimates.csv")
        self.assertEqual(before & after, before)
        added_capacity = [
            dict(signature) for signature in (after - before).elements()
        ]
        self.assertEqual(len(added_capacity), 8)

        entities = by_id(RELEASE / "entities.csv", "entity_id")
        id_to_key = {
            row["entity_id"]: row["stable_key"] for row in entities.values()
        }
        normalized = {
            (
                id_to_key[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["unit"],
                float(row["base"]),
                row["method"],
            )
            for row in added_capacity
        }
        self.assertEqual(normalized, EXPECTED_CAPACITIES)
        self.assertTrue(
            all(row["low"] == row["base"] == row["high"] for row in added_capacity)
        )
        self.assertTrue(all(row["target_date"] == "" for row in added_capacity))
        self.assertTrue(
            all(row["stage"] not in {"operational", "measured"} for row in added_capacity)
        )
        self.assertTrue(
            all(
                row["metric"]
                not in {
                    "annual_energy_mwh",
                    "generation_nameplate_mw",
                    "gross_facility_mw",
                }
                for row in added_capacity
            )
        )
        self.assertTrue(
            {12.0, 25.0, 45.0, 63.0, 100.0, 300.0, 1450.0}.isdisjoint(
                float(row["base"]) for row in added_capacity
            )
        )

        by_key: dict[str, list[dict[str, str]]] = {
            key: [] for key in NEW_ENTITY_KEYS
        }
        for row in added_capacity:
            by_key[id_to_key[row["entity_id"]]].append(row)
        self.assertEqual(by_key[GREEN_CAMPUS_KEY], [])
        self.assertEqual(by_key[GREEN_PROJECT_KEY], [])
        self.assertEqual(by_key[MORO_CAMPUS_KEY], [])
        self.assertEqual(by_key[MORO_PROJECT_KEY], [])
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[CGK_CAMPUS_KEY]},
            {("critical_it_mw", 500.0), ("pue", 1.25)},
        )
        self.assertEqual(by_key[CGK_PROJECT_KEY], [])
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[IIJ_PROJECT_KEY]},
            {("grid_connection_mw", 10.0)},
        )
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[SOFTBANK_PROJECT_KEY]},
            {("grid_connection_mw", 50.0)},
        )
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[MERLIN_PROJECT_KEY]},
            {("critical_it_mw", 80.0)},
        )
        self.assertEqual(by_key[MERLIN_PROJECT_KEY][0]["method"], "calculated")
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[IC3_CAMPUS_KEY]},
            {("critical_it_mw", 47.0), ("pue", 1.28)},
        )
        self.assertEqual(
            {(row["metric"], float(row["base"])) for row in by_key[IC3_PROJECT_KEY]},
            {("critical_it_mw", 6.0)},
        )
        self.assertIn("not additive", by_key[IC3_PROJECT_KEY][0]["notes"])
        self.assertIn("must not be summed", " ".join(
            row["notes"] for row in by_key[IC3_CAMPUS_KEY]
        ))

        previous_entities = by_id(PREVIOUS_RELEASE / "entities.csv", "entity_id")
        added_entities = [
            row
            for entity_id, row in entities.items()
            if entity_id not in previous_entities
        ]
        workload_rows = [
            (row["stable_key"], json.loads(row["workloads_json"]))
            for row in added_entities
            if json.loads(row["workloads_json"])
        ]
        self.assertEqual(
            workload_rows,
            [
                (
                    SOFTBANK_PROJECT_KEY,
                    [
                        {
                            "as_of_date": "2025-05-01",
                            "confidence": 0.99,
                            "evidence_id": "a64b5b8d-807d-5106-b6cc-028615980f5c",
                            "method": "company_disclosure",
                            "workload": "ai_specialized_unspecified",
                        }
                    ],
                )
            ],
        )

        summary = json.loads(
            (RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["entities_total"], 402)
        self.assertEqual(summary["projects_total"], 170)
        self.assertEqual(summary["evidence_total"], 278)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(summary["capacity_estimates_current"], 413)
        self.assertEqual(summary["construction_pipeline_records"], 211)
        self.assertEqual(summary["construction_source_signals"], 177)
        self.assertEqual(summary["lifecycle_observations_current"], 242)
        self.assertEqual(
            summary["entities_by_status"]["under_construction"], 141
        )
        self.assertEqual(summary["entities_by_status"]["shell"], 7)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 5587.6, "count": 50, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["grid_connection_mw"]["planned"],
            {"base": 1060.0, "count": 3, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["pue"]["design"],
            {"base": 3.73, "count": 3, "unit": "ratio"},
        )

    def test_adversarial_definition_and_release_mutations_fail_closed(self) -> None:
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(current)
        mutated["scope"]["commercial_census_parity_claimed"] = True
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            candidate = Path(temporary) / "sources" / "mutated.json"
            candidate.parent.mkdir()
            candidate.write_text(
                json.dumps(mutated, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(OpenSeedReleaseError, "scope guardrails"):
                validate_open_seed_release(candidate, RELEASE)

        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            copied_release = Path(temporary) / "release"
            shutil.copytree(RELEASE, copied_release)
            target = copied_release / "entities.csv"
            target.chmod(0o644)
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(OpenSeedReleaseError, "release file changed"):
                validate_open_seed_release(
                    DEFINITION, copied_release, require_frozen=False
                )


if __name__ == "__main__":
    unittest.main()
