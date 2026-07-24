from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v42.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v42"
ACCEPTED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v40.json"
ACCEPTED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v40"

DEFINITION_SHA256 = "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
MANIFEST_SHA256 = "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680"
ACCEPTED_DEFINITION_SHA256 = (
    "5e4d8b3f6c507dcd515f5bd92facddb5b4bbb350fe3a0851fc5b08285c5897ff"
)
ACCEPTED_MANIFEST_SHA256 = (
    "1b34fedfcef6c564aa17d20efefced3669b648c150f3dca74a3ecba78f341bc5"
)
RECORDED_AT = "2026-07-20T04:45:00Z"

CODE_HASHES = {
    "datacenter_atlas/curated.py": "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12",
    "datacenter_atlas/open_seed_release.py": "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
    "datacenter_atlas/publication_release.py": "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510",
    "datacenter_atlas/release.py": "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056",
    "datacenter_atlas/release_contract_v4.py": "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169",
}

TEST_HASHES = {
    "tests/test_curated_equinix_americas_10k_20260720.py": "0fc790b071902505fd3abe347fec6934f790ae611f5e86238f89a31292aa5a96",
    "tests/test_curated_equinix_emea_10k_20260720.py": "53977ae8610cfb41012bfc66798d287715ac4e897803b2ab45220978e19817b7",
    "tests/test_curated_equinix_remaining14_10k_20260720.py": "862638092092dc83491a95053c00fafea5bba31c8bff5c69dfd304166f32f51d",
    "tests/test_curated_equinix_current_openings.py": "3965dd102717bf37a427990188eef767e8649c5740e3738035e0998ff2ce1a2d",
    "tests/test_curated_official_digital_realty_manassas.py": "ad42fdc6d0d5f616b8d3115e1bd326ac651af1a356dc9f8924b53ef8a18abdbb",
    "tests/test_curated_iron_mountain_q1_2026.py": "14e7a64615fb98d3864f7bc0fad201b8a053d0d82cb7e700322c84e278e926cd",
    "tests/test_open_seed_release.py": "392b806639033497b7c9f43f577cce2e18864c2710fb9d6c393191d1f924e05e",
    "tests/test_release.py": "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243",
    "tests/test_release_contract_v4.py": "7bc3c7d31576bd18597b1792f067abc018540e94b30ba960ef4e990828353ebd",
}

ADDED_INPUT_COUNT = 46
ADDED_INPUTS_SHA256 = (
    "22047c1037cc3dc06ffac74a71e9667190aa37e5162c6e5e5db1b0018c300555"
)
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        421,
        81,
        "87097f0710b6af8ecbdc662498d3635eab0a47710cd656d819237d99f3fec17a",
    ),
    "construction_pipeline.csv": (
        220,
        42,
        "60570dbde303cd17d9896e0ea72cf9d0d13aa3256643caaf8935c10c5a30d0e5",
    ),
    "evidence.csv": (
        256,
        17,
        "5f1fcb40d77f255d08bf1e017b26c0b22e7dbad920a0522cbac469a951802ba1",
    ),
    "capacity_estimates.csv": (
        418,
        9,
        "8570fa82faa62a76044e479f49b3ddfb62f50b74f3e0162ade99b9ce35de9a07",
    ),
    "construction_source_signals.csv": (
        182,
        5,
        "fe2b4526b422b93c4599e6e24f29ced1d4efcfe282b02f756e377d3c942fe7d2",
    ),
}
REJECTED_PATH_FRAGMENTS = (
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
)
REJECTED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        "epoch-official-open-seed-v41",
        "2026-07-20-open-seed-v41",
        "967127f07f0e30be989bfbeba2ab7884a20b4ff570357648af8c48652e67c1b5",
        "e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
    )
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    source_rows = rows(path)
    result = {row[key]: row for row in source_rows}
    if len(result) != len(source_rows):
        raise AssertionError(f"duplicate {key} in {path}")
    return result


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


def canonical_json(document: object) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_hash(document: object) -> str:
    raw = (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def normalized_counter_rows(
    counter: Counter[tuple[tuple[str, str], ...]],
) -> list[dict[str, str]]:
    result = [dict(packed) for packed in counter.elements()]
    result.sort(
        key=lambda row: json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return result


class OpenSeedV42Tests(unittest.TestCase):
    def _validate_offline(
        self,
        definition: Path,
        release: Path,
    ) -> dict[str, object]:
        offline = AssertionError("v42 validation attempted network access")
        original_read_bytes = Path.read_bytes

        def guarded_read_bytes(path: Path) -> bytes:
            normalized = path.resolve().as_posix()
            if any(fragment in normalized for fragment in REJECTED_PATH_FRAGMENTS):
                raise AssertionError(f"v42 attempted rejected path access: {path}")
            return original_read_bytes(path)

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(Path, "read_bytes", new=guarded_read_bytes)
            )
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=offline))
            return validate_open_seed_release(definition, release)

    def test_exact_pins_double_offline_rebuild_and_frozen_bundle(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(sha256(ACCEPTED_DEFINITION), ACCEPTED_DEFINITION_SHA256)
        self.assertEqual(
            sha256(ACCEPTED_RELEASE / "manifest.json"),
            ACCEPTED_MANIFEST_SHA256,
        )
        for relative, expected in CODE_HASHES.items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)
        for relative, expected in TEST_HASHES.items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertEqual(len(entries), 13)
        self.assertTrue(
            all(
                path.is_file()
                and not path.is_symlink()
                and stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in entries
            )
        )
        frozen = {path.name: path.read_bytes() for path in entries}
        accepted_entries = list(ACCEPTED_RELEASE.iterdir())
        self.assertEqual(len(accepted_entries), 13)
        accepted_frozen = {
            path.name: path.read_bytes() for path in accepted_entries
        }
        first = self._validate_offline(DEFINITION, RELEASE)
        second = self._validate_offline(DEFINITION, RELEASE)
        accepted_first = self._validate_offline(
            ACCEPTED_DEFINITION,
            ACCEPTED_RELEASE,
        )
        accepted_second = self._validate_offline(
            ACCEPTED_DEFINITION,
            ACCEPTED_RELEASE,
        )
        self.assertEqual(first, second)
        self.assertEqual(accepted_first, accepted_second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in accepted_entries},
            accepted_frozen,
        )
        self.assertEqual(accepted_first["recorded_at"], "2026-07-20T03:10:00Z")
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 502)
        self.assertEqual(first["entities_by_kind"], {"campus": 278, "project": 224})
        self.assertEqual(first["evidence_records"], 273)
        self.assertEqual(first["capacity_estimates"], 427)
        self.assertEqual(first["construction_pipeline_records"], 262)
        self.assertEqual(first["construction_source_signals"], 187)
        self.assertEqual(first["resolution_candidates"], 4)

        current_payloads = [DEFINITION.read_bytes()]
        current_payloads.extend(path.read_bytes() for path in entries)
        for marker in REJECTED_MARKERS:
            self.assertFalse(any(marker in payload for payload in current_payloads))

    def test_definition_is_exact_accepted_v40_plus_46_inputs_and_v4(self) -> None:
        accepted = json.loads(ACCEPTED_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        accepted_pins = {
            record["path"]: record["sha256"]
            for record in accepted["curated_inputs"]
        }
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        self.assertEqual(len(accepted_pins), 184)
        self.assertEqual(len(current_pins), 230)
        added = {
            path: current_pins[path]
            for path in set(current_pins) - set(accepted_pins)
        }
        self.assertEqual(len(added), ADDED_INPUT_COUNT)
        self.assertEqual(canonical_hash(added), ADDED_INPUTS_SHA256)
        self.assertFalse(set(accepted_pins) - set(current_pins))
        changed = {
            path: current_pins[path]
            for path in set(accepted_pins) & set(current_pins)
            if accepted_pins[path] != current_pins[path]
        }
        self.assertEqual(changed, {})
        ordered = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered, sorted(set(ordered)))
        self.assertNotIn(
            "sources/curated-official-2026-07-20-hyperco-dayone-koria.json",
            current_pins,
        )
        self.assertNotIn(
            "sources/curated-official-2026-07-20-teraco-jb7-isando.json",
            current_pins,
        )
        self.assertIn(
            "sources/curated-official-2026-07-20-hyperco-dayone-koria-v2.json",
            current_pins,
        )
        self.assertIn(
            "sources/curated-official-2026-07-20-hyperco-loviisa.json",
            current_pins,
        )
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file() and not path.is_symlink(), relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            for evidence in document.get("evidence", []):
                self.assertLessEqual(evidence["retrieved_at"], RECORDED_AT, relative)

        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v42")
        self.assertEqual(current["build"], {"as_of": "2026-07-20", "recorded_at": RECORDED_AT})
        self.assertEqual(accepted["publication_contract_version"], 3)
        self.assertNotIn("publication_contract_version", accepted["expected_release"])
        marker = current["publication_contract_version"]
        self.assertIs(type(marker), int)
        self.assertEqual(marker, 4)
        self.assertEqual(current["expected_release"]["publication_contract_version"], 4)

        for invalid in (4.0, True, "4", None, [], {}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory(
                dir="/private/tmp"
            ) as temporary:
                sources = Path(temporary) / "sources"
                sources.mkdir()
                drifted = dict(current)
                drifted["publication_contract_version"] = invalid
                drifted_path = sources / "definition.json"
                drifted_path.write_bytes(canonical_json(drifted))
                with self.assertRaisesRegex(
                    OpenSeedReleaseError, "publication contract version"
                ):
                    validate_open_seed_release(drifted_path, RELEASE)

    def test_exact_v40_to_v42_release_delta_is_purely_additive(self) -> None:
        for filename, (common_count, added_count, added_sha256) in (
            CSV_DELTA_CONTRACT.items()
        ):
            before = row_counter(ACCEPTED_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            added_rows = normalized_counter_rows(after - before)
            removed_rows = normalized_counter_rows(before - after)
            self.assertEqual(sum((before & after).values()), common_count, filename)
            self.assertEqual(len(added_rows), added_count, filename)
            self.assertEqual(canonical_hash(added_rows), added_sha256, filename)
            self.assertEqual(removed_rows, [], filename)
        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (ACCEPTED_RELEASE / filename).read_bytes(),
                filename,
            )

        before_entities = by_key(ACCEPTED_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        self.assertEqual(len(after_entities) - len(before_entities), 81)
        self.assertFalse(set(before_entities) - set(after_entities))
        changed_keys = set(before_entities) & set(after_entities)
        changed_keys = {
            key for key in changed_keys if before_entities[key] != after_entities[key]
        }
        self.assertEqual(changed_keys, set())

        il3_campus = "curated:equinix-il3-istanbul-data-center"
        il3_project = il3_campus + ":phase-1"
        sv18_campus = "curated:equinix-sv18-silicon-valley-data-center"
        for key in (il3_campus, il3_project):
            self.assertEqual(after_entities[key]["country"], "Türkiye")
            self.assertEqual(after_entities[key]["country_iso_a2"], "TR")
            self.assertEqual(after_entities[key]["country_iso_a3"], "TUR")
        self.assertEqual(
            after_entities[sv18_campus]["source_url"],
            "https://www.sec.gov/Archives/edgar/data/1101239/000110123926000075/EQIXAnnualRpt2025PRINT.pdf",
        )

        before_pipeline = by_key(
            ACCEPTED_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        after_pipeline = by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        self.assertEqual(len(after_pipeline) - len(before_pipeline), 42)
        pipeline_changed = {
            key
            for key in set(before_pipeline) & set(after_pipeline)
            if before_pipeline[key] != after_pipeline[key]
        }
        self.assertEqual(pipeline_changed, set())
        added_pipeline = [
            after_pipeline[key] for key in set(after_pipeline) - set(before_pipeline)
        ]
        self.assertEqual(
            Counter(row["status"] for row in added_pipeline),
            {"under_construction": 42},
        )
        self.assertEqual(
            Counter(row["status_as_of"] for row in added_pipeline),
            {"2025-12-31": 33, "2026-03-31": 7, "2026-06-29": 2},
        )

    def test_current_openings_roles_capacities_and_nonadditive_boundaries(self) -> None:
        entities = by_key(RELEASE / "entities.csv", "stable_key")
        expected_statuses = {
            "curated:equinix-hk6-hong-kong-data-center": ("operational", "2026-06-16"),
            "curated:equinix-hk6-hong-kong-data-center:phase-1": ("operational", "2026-06-16"),
            "curated:equinix-md5-madrid-data-center": ("operational", "2026-05-22"),
            "curated:equinix-md5-madrid-data-center:phase-1": ("under_construction", "2025-12-31"),
            "curated:equinix-mb3-mumbai-data-center": ("operational", "2026-04-08"),
            "curated:equinix-mb3-mumbai-data-center:phase-2": ("under_construction", "2025-12-31"),
        }
        for key, (status_value, status_date) in expected_statuses.items():
            self.assertEqual(
                (entities[key]["status"], entities[key]["status_as_of"]),
                (status_value, status_date),
                key,
            )

        accepted_entity_rows = rows(ACCEPTED_RELEASE / "entities.csv")
        current_entity_rows = rows(RELEASE / "entities.csv")
        for column, expected_delta in {
            "owner": 0,
            "operator": 13,
            "users": 0,
            "tenants": 0,
            "customers": 0,
        }.items():
            self.assertEqual(
                sum(bool(row[column]) for row in current_entity_rows)
                - sum(bool(row[column]) for row in accepted_entity_rows),
                expected_delta,
                column,
            )
        accepted_entities = by_key(ACCEPTED_RELEASE / "entities.csv", "stable_key")
        added_entities = [
            row
            for key, row in entities.items()
            if key not in accepted_entities
        ]
        for row in added_entities:
            is_iron = row["stable_key"].startswith("curated:iron-mountain-")
            self.assertEqual(
                row["operator"], "Iron Mountain Data Centers" if is_iron else ""
            )
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["tenants"], "")
            self.assertEqual(row["customers"], "")

        before_capacity = row_counter(ACCEPTED_RELEASE / "capacity_estimates.csv")
        after_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        entity_keys = {
            row["entity_id"]: row["stable_key"] for row in current_entity_rows
        }
        added_capacity = [dict(packed) for packed in (after_capacity - before_capacity)]
        observed_specs = {
            (
                entity_keys[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["base"],
                row["unit"],
                row["as_of_date"],
            )
            for row in added_capacity
        }
        self.assertEqual(
            observed_specs,
            {
                ("curated:digital-realty-manassas-source-scoped-campus:source-facility-1", "critical_it_mw", "planned", "96.0", "MW", "2026-06-29"),
                ("curated:digital-realty-manassas-source-scoped-campus:source-facility-2", "critical_it_mw", "planned", "96.0", "MW", "2026-06-29"),
                ("curated:iron-mountain-amsterdam-data-center-campus:ams-2-10mw-expansion", "critical_it_mw", "planned", "10.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-azp-3-phoenix-data-center:phase-3", "critical_it_mw", "planned", "8.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-lon-3-london-data-center:25mw-build", "critical_it_mw", "planned", "25.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-madrid-data-center-campus:mad-2-mad-3-20mw-development", "critical_it_mw", "planned", "20.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-mia-1-miami-data-center:build", "critical_it_mw", "planned", "16.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-va-9-northern-virginia-data-center:phase-1", "critical_it_mw", "planned", "14.0", "MW", "2026-03-31"),
                ("curated:iron-mountain-va-9-northern-virginia-data-center:phase-2", "critical_it_mw", "planned", "14.0", "MW", "2026-03-31"),
            },
        )
        self.assertEqual(len(added_capacity), 9)

        before_signals = by_key(
            ACCEPTED_RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        after_signals = by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        added_signals = [
            after_signals[key] for key in set(after_signals) - set(before_signals)
        ]
        self.assertEqual(
            Counter(
                (row["source_family"], int(row["affected_entity_count"]))
                for row in added_signals
            ),
            Counter(
                {
                    ("digital_realty_press_releases", 2): 1,
                    ("equinix_sec_filings", 8): 1,
                    ("equinix_sec_filings", 12): 1,
                    ("equinix_sec_filings", 13): 1,
                    ("iron_mountain_sec_filings", 7): 1,
                }
            ),
        )

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(summary["capacity_estimates_current"], 427)
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
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)


if __name__ == "__main__":
    unittest.main()
