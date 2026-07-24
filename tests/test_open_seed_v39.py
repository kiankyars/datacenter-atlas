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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v39.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v39"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v38.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v38"

DEFINITION_SHA256 = "2b0b219e94e98782f58128ea7db9c9b954e44d0694f33cc17e7807a71e6ef381"
MANIFEST_SHA256 = "e0877d779b235bb395158063dddf070d489308fd3b3960dafaa78036d46fed84"
BASE_DEFINITION_SHA256 = (
    "38e4152cc0d88bece3d172cde1a549c0ec45c444d97858a6cf9368eb650792a9"
)
BASE_MANIFEST_SHA256 = (
    "28e7686ddd507b74cbb7b96cab655388e5086f60bd096f0ca6263b25b49f6b00"
)
BASE_TEST_SHA256 = (
    "36132d01f86b1eebe7a119d03d36e3e406e5853c0a0a260b26617851852d6291"
)
TRANCHE_TEST_SHA256 = (
    "5de4c2e0e9d5b23c974e042d18f010ffe19f5427e35a6278de79f5ed8c3172a1"
)
RELEASE_CODE_SHA256 = (
    "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056"
)
RELEASE_TEST_SHA256 = (
    "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243"
)
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-20T02:17:49Z"

SOURCE_HASHES = {
    "sources/curated-official-2026-07-20-cipher-barber-lake-phase-1-capacity-component.json": (
        "03f328e2d249a5c5931ef9a8eea45d62782a008f810cf522fd0e77e3e9accd3a"
    ),
    "sources/curated-official-2026-07-20-cipher-barber-lake-phase-2-capacity-component.json": (
        "8c5fa1cde0c76b13e4da145bcb3344d0fa809de6085b1f4d5dd158a8da2f0f24"
    ),
    "sources/curated-official-2026-07-20-cipher-barber-lake-topped-out-building.json": (
        "e2180f05010ac18d15bb970d93439abb441453c57225b10c2577e5ef5adc3da1"
    ),
    "sources/curated-official-2026-07-20-cipher-black-pearl-phase-1-aws-retrofit.json": (
        "1fb9e5ecd778af16d4f2be305894511f94d3ca3371173cf03e38f2e4446361f9"
    ),
    "sources/curated-official-2026-07-20-cipher-black-pearl-phase-2-site-preparation.json": (
        "b82336e19b9ac6594267b9418c3f14da997a019a43532543a403fa9f5fdcc6f9"
    ),
    "sources/curated-official-2026-07-20-core-scientific-muskogee-building-2.json": (
        "c6ab36356b873285e23b83f264421d8cac3eea8b14176a3931211c0ecc3979b8"
    ),
}

BARBER_CAMPUS = (
    "curated:cipher-digital-barber-lake-colorado-city-texas-data-center-campus"
)
BLACK_CAMPUS = "curated:cipher-digital-black-pearl-wink-texas-data-center-campus"
MUSKOGEE_CAMPUS = "curated:core-scientific-muskogee-oklahoma-data-center-campus"
BARBER_BUILDING = BARBER_CAMPUS + ":current-data-center-building"
BARBER_PHASE_1 = BARBER_CAMPUS + ":phase-1-contracted-capacity-component"
BARBER_PHASE_2 = BARBER_CAMPUS + ":phase-2-contracted-capacity-component"
BLACK_PHASE_1 = BLACK_CAMPUS + ":aws-phase-1-retrofit"
BLACK_PHASE_2 = BLACK_CAMPUS + ":aws-phase-2-site-preparation"
MUSKOGEE_BUILDING_2 = MUSKOGEE_CAMPUS + ":building-2-current-construction"

CAMPUS_KEYS = {BARBER_CAMPUS, BLACK_CAMPUS, MUSKOGEE_CAMPUS}
PROJECT_KEYS = {
    BARBER_BUILDING,
    BARBER_PHASE_1,
    BARBER_PHASE_2,
    BLACK_PHASE_1,
    BLACK_PHASE_2,
    MUSKOGEE_BUILDING_2,
}
ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
PROJECT_STATUSES = {
    BARBER_BUILDING: "shell",
    BLACK_PHASE_1: "under_construction",
    BLACK_PHASE_2: "site_preparation",
    MUSKOGEE_BUILDING_2: "under_construction",
}

EVIDENCE_HASHES = {
    "1f77c00a44751e7ef52850a4245d6cb70a1230be313f757b6a2dfd21a8f7a9dc",
    "3dd8f30f1659609d358f30eb81f8c1ed29d4c23f03857232bcd9540d531abf5f",
    "57a44de751a1530cfd6aa08ae6f2b8f2e5ec5e0e9b8cc02e5d6ce9431f1bd15d",
    "8116bbe1eaa8c2ef7732cb277688e108f7ee0e43fc114435d4e17b6842d8c760",
    "e8c146f2e616aaf8ff8757989145334534bd34b306c641367d0717b97ded4eed",
}

NEW_SOURCE_FAMILIES = {
    "cipher_digital_sec_exhibits",
    "cipher_digital_sec_filings",
    "cipher_sec_exhibits",
    "cipher_sec_investor_presentations",
    "core_scientific_sec_exhibits",
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


def normalized_v3_entity_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    tags = json.loads(normalized["tags_json"])
    normalized["users"] = (
        tags.get("users")
        or tags.get("tenants")
        or tags.get("role:user")
        or tags.get("role:tenant")
        or tags.get("role:customer")
        or ""
    )
    normalized.pop("tenants")
    normalized.pop("customers")
    return normalized


class OpenSeedV39Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v39 validation attempted network access")
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

    def test_release_rebuilds_twice_offline_with_v3_code_and_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "datacenter_atlas" / "release.py").read_bytes()).hexdigest(),
            RELEASE_CODE_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_release.py").read_bytes()).hexdigest(),
            RELEASE_TEST_SHA256,
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
        self.assertEqual(first["entities"], 411)
        self.assertEqual(first["entities_by_kind"], {"campus": 235, "project": 176})
        self.assertEqual(first["evidence_records"], 253)
        self.assertEqual(first["capacity_estimates"], 418)
        self.assertEqual(first["construction_pipeline_records"], 215)
        self.assertEqual(first["construction_source_signals"], 179)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exact_v38_plus_six_sources_and_v3_contract(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(), BASE_DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_open_seed_v38.py").read_bytes()).hexdigest(),
            BASE_TEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (
                    ROOT
                    / "tests"
                    / "test_curated_cipher_barber_black_pearl_core_muskogee.py"
                ).read_bytes()
            ).hexdigest(),
            TRANCHE_TEST_SHA256,
        )

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_pins = {record["path"]: record["sha256"] for record in base["curated_inputs"]}
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        self.assertEqual(len(base_pins), 173)
        self.assertEqual(len(current_pins), 179)
        self.assertEqual(set(current_pins) - set(base_pins), set(SOURCE_HASHES))
        self.assertEqual(set(base_pins) - set(current_pins), set())
        self.assertEqual(
            {path: current_pins[path] for path in SOURCE_HASHES}, SOURCE_HASHES
        )
        ordered_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered_paths, sorted(ordered_paths))
        self.assertEqual(len(ordered_paths), len(set(ordered_paths)))
        self.assertEqual(base["publication_contract_version"], 2)
        self.assertEqual(current["publication_contract_version"], 3)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v39")
        self.assertEqual(current["build"], {"as_of": AS_OF, "recorded_at": RECORDED_AT})
        for key in set(base) - {
            "build",
            "curated_inputs",
            "expected_release",
            "expected_summary",
            "publication_contract_version",
            "release_id",
        }:
            self.assertEqual(current[key], base[key], key)

        for relative, digest in SOURCE_HASHES.items():
            path = ROOT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_v38_rows_survive_exactly_except_explicit_role_column_split(self) -> None:
        base_entities = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        self.assertEqual(
            {key: normalized_v3_entity_row(current_entities[key]) for key in base_entities},
            base_entities,
        )
        added_entities = [
            current_entities[key] for key in set(current_entities) - set(base_entities)
        ]
        self.assertEqual({row["stable_key"] for row in added_entities}, ENTITY_KEYS)

        base_pipeline = by_id(BASE_RELEASE / "construction_pipeline.csv", "entity_id")
        current_pipeline = by_id(RELEASE / "construction_pipeline.csv", "entity_id")
        self.assertEqual(
            {key: normalized_v3_entity_row(current_pipeline[key]) for key in base_pipeline},
            base_pipeline,
        )
        added_pipeline = [
            current_pipeline[key] for key in set(current_pipeline) - set(base_pipeline)
        ]
        self.assertEqual(
            {row["stable_key"]: row["status"] for row in added_pipeline},
            PROJECT_STATUSES,
        )

        exact_csv_counts = {
            "evidence.csv": (248, 253),
            "capacity_estimates.csv": (413, 418),
            "construction_source_signals.csv": (177, 179),
            "resolution_candidates.csv": (4, 4),
        }
        for filename, (base_count, current_count) in exact_csv_counts.items():
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

        base_evidence = by_id(BASE_RELEASE / "evidence.csv", "evidence_id")
        current_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        added_evidence = [
            current_evidence[key] for key in set(current_evidence) - set(base_evidence)
        ]
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_HASHES)

    def test_added_rows_keep_phase_status_capacity_roles_and_mining_boundaries(self) -> None:
        base = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current = by_id(RELEASE / "entities.csv", "entity_id")
        added = [current[key] for key in set(current) - set(base)]
        by_key = {row["stable_key"]: row for row in added}
        for stable_key, row in by_key.items():
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["customers"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["status"], PROJECT_STATUSES.get(stable_key, ""))
            self.assertEqual(
                row["tenants"],
                "Amazon Web Services, Inc."
                if stable_key in {BLACK_PHASE_1, BLACK_PHASE_2}
                else "",
            )

        entity_keys = {row["entity_id"]: row["stable_key"] for row in added}
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
                (BARBER_CAMPUS, "gross_facility_mw", "planned", "300.0", "MW", "reported"),
                (BARBER_PHASE_1, "critical_it_mw", "planned", "168.0", "MW", "reported"),
                (BARBER_PHASE_1, "gross_facility_mw", "planned", "244.0", "MW", "reported"),
                (BARBER_PHASE_2, "critical_it_mw", "planned", "39.0", "MW", "reported"),
                (BARBER_PHASE_2, "gross_facility_mw", "planned", "56.0", "MW", "reported"),
            },
        )
        self.assertEqual(244 + 56, 300)
        self.assertEqual(168 + 39, 207)
        self.assertFalse(
            any(
                stable_key in {BARBER_BUILDING, BLACK_PHASE_1, BLACK_PHASE_2, MUSKOGEE_BUILDING_2}
                for stable_key, *_ in capacity_specs
            )
        )

        muskogee = json.loads(
            (
                ROOT
                / "sources"
                / "curated-official-2026-07-20-core-scientific-muskogee-building-2.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("82.5", json.dumps(muskogee["evidence"]))
        self.assertEqual(muskogee["capacities"], [])
        self.assertEqual(muskogee["workloads"], [])
        self.assertEqual(muskogee["operating_models"], [])

    def test_v3_summary_signals_and_source_families_are_nonadditive(self) -> None:
        with (RELEASE / "entities.csv").open(newline="", encoding="utf-8") as stream:
            fieldnames = csv.DictReader(stream).fieldnames
        assert fieldnames is not None
        self.assertEqual(
            fieldnames[fieldnames.index("users") : fieldnames.index("users") + 3],
            ["users", "tenants", "customers"],
        )
        with (RELEASE / "construction_pipeline.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            pipeline_fields = csv.DictReader(stream).fieldnames
        assert pipeline_fields is not None
        self.assertEqual(
            pipeline_fields[
                pipeline_fields.index("users") : pipeline_fields.index("users") + 3
            ],
            ["users", "tenants", "customers"],
        )

        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text(encoding="utf-8"))
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(len(manifest["source_families"]), 117)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(
            summary["capacity_aggregation"],
            {
                "base_totals_published": False,
                "cross_entity_sum_valid": False,
                "reason": (
                    "Capacity rows can be nested, component-scoped, superseding, or "
                    "metric-distinct. Arithmetic sums are not valid facility, site, load, "
                    "energy, or unique-physical-site totals."
                ),
                "scope": "typed_source_observation_rows",
            },
        )
        self.assertEqual(summary["entities_total"], 411)
        self.assertEqual(summary["projects_total"], 176)
        self.assertEqual(summary["evidence_total"], 284)
        self.assertEqual(summary["entities_by_status"]["shell"], 8)
        self.assertEqual(summary["entities_by_status"]["site_preparation"], 11)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 143)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(summary["capacity_estimates_current"], 418)
        self.assertEqual(summary["capacity_estimates_by_metric"]["critical_it_mw"], 178)
        self.assertEqual(summary["capacity_estimates_by_metric"]["gross_facility_mw"], 125)

        signals = rows(RELEASE / "construction_source_signals.csv")
        base_signal_ids = {
            row["source_observation_evidence_id"]
            for row in rows(BASE_RELEASE / "construction_source_signals.csv")
        }
        added_signals = [
            row
            for row in signals
            if row["source_observation_evidence_id"] not in base_signal_ids
        ]
        self.assertEqual(len(added_signals), 2)
        affected_keys = {
            entity["stable_key"]
            for signal in added_signals
            for entity in json.loads(signal["affected_entities_json"])
        }
        self.assertEqual(affected_keys, set(PROJECT_STATUSES))

        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("Role columns are dimensioned", readme)
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)


if __name__ == "__main__":
    unittest.main()
