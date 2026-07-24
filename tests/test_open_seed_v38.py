from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v38.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v38"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v37.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v37"

DEFINITION_SHA256 = "38e4152cc0d88bece3d172cde1a549c0ec45c444d97858a6cf9368eb650792a9"
MANIFEST_SHA256 = "28e7686ddd507b74cbb7b96cab655388e5086f60bd096f0ca6263b25b49f6b00"
BASE_DEFINITION_SHA256 = (
    "c6786e684d76bfa72f5428e26396317bc05495da1afc656be4026c8c2acb9a66"
)
BASE_MANIFEST_SHA256 = (
    "bcc0d1207e5b4c709557f49fc6d42e1080dcaebb762b32093848461afd52d30a"
)
BASE_TEST_SHA256 = (
    "7c086ad7df6a6b7d5807c6c539bf9687f5bad79023ac044862fec2d208a35bcd"
)
TRANCHE_TEST_SHA256 = (
    "0a20aa048652f907a7c511eec4bb2ec05e2fe91f35012c92bab9036dc47e71f5"
)
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-20T02:01:07Z"

SOURCE_HASHES = {
    "sources/curated-official-2026-07-20-green-zrh1-dc4-lupfig.json": (
        "7161ad1721c77f39b432aa3b0ebf8de42c8140230b61c5a89ea843ea664d868e"
    ),
    "sources/curated-official-2026-07-20-iij-shiroi-phase-3.json": (
        "ed214cfed7495ad6b1cf7a65f2cc1e90d80d12b58b615afb2931b98cb0bb6714"
    ),
    "sources/curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json": (
        "2efccf401355b50ce559e64c060d5cf6f1350d326440c0035ce63bf008e07d73"
    ),
}

CAMPUS_KEYS = {
    "curated:green-campus-zrh1-lupfig",
    "curated:iij-shiroi-data-center-campus",
    "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-campus",
}
PROJECT_KEYS = {
    "curated:green-campus-zrh1-lupfig:data-center-4",
    "curated:iij-shiroi-data-center-campus:phase-3-server-building",
    (
        "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-"
        "campus:planned-data-hall-building"
    ),
}
ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS

EVIDENCE_HASHES = {
    "02ab48dcfbb12802f3e2c01789f26acff3e516832b074645b7b160aa241372b0",
    "7c9f965f4d6c229f0aaab2ecd4584d9943c6d6fca13ed6c528316c72956d18b8",
    "a241bca1a18774e0b82c7b2d23e59dbf86bbb30cc1160604808de34e626d3ce4",
    "c189dce34805edb292c07c6204122b6e4a9d8d30cd7cd7e91080ea92905edd1e",
    "d665d479045420e991eba21ab02f6fe3bc01607cf2cb7382895427a8defb33e3",
}

NEW_SOURCE_FAMILIES = {
    "green_data_center_facility_pages",
    "iij_investor_relations",
    "iij_press_releases",
    "softbank_news",
    "softbank_sustainability",
}

CSV_COUNTS = {
    "entities.csv": (396, 402),
    "evidence.csv": (243, 248),
    "capacity_estimates.csv": (411, 413),
    "construction_pipeline.csv": (208, 211),
    "construction_source_signals.csv": (174, 177),
    "resolution_candidates.csv": (4, 4),
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


class OpenSeedV38Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v38 validation attempted network access")
        with ExitStack() as stack:
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=network_error))
            return validate_open_seed_release(DEFINITION, RELEASE)

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
        self.assertEqual(len(entries), 13)
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in entries))
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in entries))
        frozen = {path.name: path.read_bytes() for path in entries}

        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["as_of"], AS_OF)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 402)
        self.assertEqual(first["entities_by_kind"], {"campus": 232, "project": 170})
        self.assertEqual(first["evidence_records"], 248)
        self.assertEqual(first["capacity_estimates"], 413)
        self.assertEqual(first["construction_pipeline_records"], 211)
        self.assertEqual(first["construction_source_signals"], 177)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exactly_v37_plus_three_accepted_sources(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_open_seed_v37.py").read_bytes()).hexdigest(),
            BASE_TEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "tests" / "test_curated_softbank_green_iij_20260720.py").read_bytes()
            ).hexdigest(),
            TRANCHE_TEST_SHA256,
        )

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_pins = {record["path"]: record["sha256"] for record in base["curated_inputs"]}
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        self.assertEqual(len(base_pins), 170)
        self.assertEqual(len(current_pins), 173)
        self.assertEqual(set(current_pins) - set(base_pins), set(SOURCE_HASHES))
        self.assertEqual(set(base_pins) - set(current_pins), set())
        self.assertEqual(
            {path: current_pins[path] for path in SOURCE_HASHES}, SOURCE_HASHES
        )
        ordered_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered_paths, sorted(ordered_paths))
        self.assertEqual(len(ordered_paths), len(set(ordered_paths)))
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v38")
        self.assertEqual(current["build"], {"as_of": AS_OF, "recorded_at": RECORDED_AT})
        for key in set(base) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "release_id",
        }:
            self.assertEqual(current[key], base[key], key)

        for relative, digest in SOURCE_HASHES.items():
            path = ROOT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_all_v37_rows_are_preserved_and_delta_is_exact(self) -> None:
        for filename, (base_count, current_count) in CSV_COUNTS.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            self.assertEqual(sum(before.values()), base_count, filename)
            self.assertEqual(sum(after.values()), current_count, filename)
            self.assertEqual(before & after, before, filename)
            self.assertEqual(
                sum((after - before).values()), current_count - base_count, filename
            )

        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
                filename,
            )

        before_entities = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        added_entities = [
            current_entities[key] for key in set(current_entities) - set(before_entities)
        ]
        self.assertEqual({row["stable_key"] for row in added_entities}, ENTITY_KEYS)

        before_evidence = by_id(BASE_RELEASE / "evidence.csv", "evidence_id")
        current_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        added_evidence = [
            current_evidence[key] for key in set(current_evidence) - set(before_evidence)
        ]
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_HASHES)

        entity_keys = {row["entity_id"]: row["stable_key"] for row in added_entities}
        capacity_delta = (
            row_counter(RELEASE / "capacity_estimates.csv")
            - row_counter(BASE_RELEASE / "capacity_estimates.csv")
        )
        capacity_specs = {
            (
                entity_keys[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["base"],
                row["unit"],
                row["method"],
            )
            for packed, count in capacity_delta.items()
            for row in [dict(packed)]
            for _ in range(count)
        }
        self.assertEqual(
            capacity_specs,
            {
                (
                    "curated:iij-shiroi-data-center-campus:phase-3-server-building",
                    "grid_connection_mw",
                    "planned",
                    "10.0",
                    "MW",
                    "reported",
                ),
                (
                    "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-"
                    "campus:planned-data-hall-building",
                    "grid_connection_mw",
                    "planned",
                    "50.0",
                    "MW",
                    "reported",
                ),
            },
        )

    def test_new_rows_preserve_narrow_status_roles_workload_and_power_types(self) -> None:
        base = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current = by_id(RELEASE / "entities.csv", "entity_id")
        added = [current[key] for key in set(current) - set(base)]
        by_key = {row["stable_key"]: row for row in added}

        for stable_key, row in by_key.items():
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(
                row["status"], "under_construction" if stable_key in PROJECT_KEYS else ""
            )

        self.assertEqual(
            json.loads(
                by_key[
                    "curated:softbank-idc-frontier-hokkaido-tomakomai-ai-data-center-"
                    "campus:planned-data-hall-building"
                ]["workloads_json"]
            )[0]["workload"],
            "ai_specialized_unspecified",
        )
        self.assertTrue(
            all(
                row["workloads_json"] == "[]"
                for key, row in by_key.items()
                if "softbank" not in key or key in CAMPUS_KEYS
            )
        )
        self.assertEqual(
            json.loads(by_key["curated:green-campus-zrh1-lupfig"]["tags_json"]),
            {
                "address": "Lupfig, Aargau, Switzerland",
                "country": "Switzerland",
                "source_dataset": "curated_official_sources",
            },
        )

        softbank = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json").read_text(
                encoding="utf-8"
            )
        )
        iij = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-iij-shiroi-phase-3.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            next(
                evidence
                for evidence in softbank["evidence"]
                if evidence["key"].startswith(
                    "softbank-tomakomai-ai-data-center-groundbreaking"
                )
            )["metadata"]["reported_end_state_power_capacity_mw_untyped"],
            ">300",
        )
        self.assertEqual(
            next(
                evidence
                for evidence in iij["evidence"]
                if evidence["key"].startswith("iij-shiroi-phase-3-plan-10mw")
            )["metadata"]["reported_expandable_maximum_power_received_mw"],
            25,
        )
        self.assertEqual({row["base"] for row in rows(RELEASE / "capacity_estimates.csv") if row["entity_id"] in {item["entity_id"] for item in added}}, {"10.0", "50.0"})

    def test_pipeline_signals_summary_and_source_families_match_delta(self) -> None:
        base_pipeline = by_id(BASE_RELEASE / "construction_pipeline.csv", "entity_id")
        current_pipeline = by_id(RELEASE / "construction_pipeline.csv", "entity_id")
        added_pipeline = [
            current_pipeline[key] for key in set(current_pipeline) - set(base_pipeline)
        ]
        self.assertEqual(
            {row["stable_key"]: row["status"] for row in added_pipeline},
            {key: "under_construction" for key in PROJECT_KEYS},
        )

        signal_id = "source_observation_evidence_id"
        base_signals = by_id(BASE_RELEASE / "construction_source_signals.csv", signal_id)
        current_signals = by_id(RELEASE / "construction_source_signals.csv", signal_id)
        added_signals = [
            current_signals[key] for key in set(current_signals) - set(base_signals)
        ]
        self.assertEqual(len(added_signals), 3)
        self.assertEqual(
            {row["representative_stable_key"] for row in added_signals}, PROJECT_KEYS
        )

        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text(encoding="utf-8"))
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(len(manifest["source_families"]), 112)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 402)
        self.assertEqual(summary["projects_total"], 170)
        self.assertEqual(summary["evidence_total"], 279)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 141)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(summary["capacity_estimates_current"], 413)
        self.assertEqual(summary["capacity_estimates_by_metric"]["grid_connection_mw"], 8)


if __name__ == "__main__":
    unittest.main()
