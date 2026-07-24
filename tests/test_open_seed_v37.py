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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v37.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v37"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v34.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v34"
REJECTED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v36.json"
REJECTED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v36"

DEFINITION_SHA256 = "c6786e684d76bfa72f5428e26396317bc05495da1afc656be4026c8c2acb9a66"
MANIFEST_SHA256 = "bcc0d1207e5b4c709557f49fc6d42e1080dcaebb762b32093848461afd52d30a"
BASE_DEFINITION_SHA256 = (
    "004513441aaffbe7ce85562b993fcf4a6d15f9630aad6fab21ce46f359f47264"
)
BASE_MANIFEST_SHA256 = (
    "66344585b802b3640d5921e37cf64cbc990eaa3a2e8b2a44f1891acbe8887d4a"
)
REJECTED_DEFINITION_SHA256 = (
    "3ab5d787cfc21d644f4be883a061bb934d8c6014ef9c5b93c9cd6cab870694b7"
)
REJECTED_MANIFEST_SHA256 = (
    "30bbc607d51dedd558ff698738314f2a22c9acde86608928433825f9d0940e7b"
)
AS_OF = "2026-07-20"
RECORDED_AT = "2026-07-20T01:29:39Z"

SOURCE_HASHES = {
    "sources/curated-official-2026-07-20-digital-edge-cgk1-bekasi.json": (
        "f2634a600ced7b901b84af36817881cdf9f060dd8aed56cfa1489c2e4f1d7432"
    ),
    "sources/curated-official-2026-07-20-hyperco-dayone-koria-v2.json": (
        "3de36878ff5e8ceac7571c0e267ae087ecd5571bae2284ccde230eb860ff5dc0"
    ),
    "sources/curated-official-2026-07-20-hyperco-loviisa.json": (
        "048814c8816ca428d2e3ec557836c907049fcf327279870e01480b46a6a4d19d"
    ),
    "sources/curated-official-2026-07-20-macquarie-ic3-super-west-phase-1.json": (
        "9fe5625d1cbb2d59dbeb8d329ab1b79fb65a7e43346161f2c92901076cc7cb4f"
    ),
    "sources/curated-official-2026-07-20-merlin-lisbon-phase-2.json": (
        "30aa6dda670bdeecd03fe47eb0dc8e39bd5b6f08b44fba5ee2442579c0c5e587"
    ),
    "sources/curated-official-2026-07-20-moro-hub-warsan-phase-1.json": (
        "c74dd8a78f2a9fd5fabdb95637fc26680958473a20a3f84f4296b0b87b2034c6"
    ),
}

REJECTED_PATHS = {
    "sources/curated-official-2026-07-20-green-zrh1-dc4-lupfig.json",
    "sources/curated-official-2026-07-20-hyperco-dayone-koria.json",
    "sources/curated-official-2026-07-20-iij-shiroi-phase-3.json",
    "sources/curated-official-2026-07-20-softbank-idc-frontier-tomakomai.json",
}

ENTITY_KEYS = {
    "curated:digital-edge-cgk-campus-bekasi",
    "curated:digital-edge-cgk-campus-bekasi:cgk1",
    "curated:hyperco-dayone-koria-unnamed-data-center-campus",
    "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build",
    "curated:hyperco-loviisa-data-center-campus",
    "curated:hyperco-loviisa-data-center-campus:current-development",
    "curated:macquarie-ic3-super-west-facility",
    "curated:macquarie-ic3-super-west-facility:phase-1-build",
    "curated:merlin-lisbon-data-center-campus",
    "curated:merlin-lisbon-data-center-campus:phase-2-two-building-development",
    "curated:moro-hub-warsan-new-green-data-centre",
    "curated:moro-hub-warsan-new-green-data-centre:phase-1",
}

PROJECT_STATUSES = {
    "curated:digital-edge-cgk-campus-bekasi:cgk1": "shell",
    "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build": (
        "under_construction"
    ),
    "curated:hyperco-loviisa-data-center-campus:current-development": (
        "under_construction"
    ),
    "curated:macquarie-ic3-super-west-facility:phase-1-build": (
        "under_construction"
    ),
    "curated:merlin-lisbon-data-center-campus:phase-2-two-building-development": (
        "under_construction"
    ),
    "curated:moro-hub-warsan-new-green-data-centre:phase-1": (
        "under_construction"
    ),
}

EXPORTED_EVIDENCE_HASHES = {
    "0a7bbd094f67937d1453e784c12c56e15e99c3ffab8a76c51b2fad9c7ffc2d25",
    "16a1571bb186309f7acde2221984e742de9c6d8e743c8048a1b020cb14de0a06",
    "3951720ead85f71d6e79f833efcd95bc97811377cfa0067ca22f30798f8c44aa",
    "631f136b57cea6d06ef390665dfc86b7a42c84a7b517d6863b69d76cb3a4358a",
    "9e4570b465ab66b282d46dd5008216b575b250e4ea4438fa8fc4839b90988f13",
    "aea8b63b826c60a6e2027712d124a087c032f2073b611a0ca81b0742a4f5d9f9",
    "bc455a2fa3310e76108b15e8459292aea83dea36beb0fafbc91d2e17ec04e6ce",
    "cf29dcde78b9e08e421b599658dc93396a03bef0b7a7aaf18e1e05dc98312269",
    "f0b9f73134963abe529a1a39373fd89b983a855e2972bfc8e4d3ac5c2e716d3f",
    "f8f86d1d3f36d46c81f9fe23edce1416f11193e7a16fc32014f98acd96f053e3",
}
YVA_GUARDRAIL_HASH = (
    "a8f3161d4ae67cf2296d19e61533234ef675ee92e869f97bad12d3122effff6f"
)

NEW_SOURCE_FAMILIES = {
    "digital_edge_indonesia_newsroom",
    "kouvola_city_news",
    "loviisa_city_news",
    "macquarie_data_centres_facility_pages",
    "macquarie_data_centres_newsroom",
    "macquarie_data_centres_specifications",
    "merlin_properties_asset_pages",
    "merlin_properties_press_releases",
    "metsahallitus_press_releases",
    "moro_hub_news",
}

CSV_COUNTS = {
    "entities.csv": (384, 396),
    "evidence.csv": (233, 243),
    "capacity_estimates.csv": (405, 411),
    "construction_pipeline.csv": (202, 208),
    "construction_source_signals.csv": (168, 174),
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


class OpenSeedV37Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v37 validation attempted network access")
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
        self.assertEqual(first["entities"], 396)
        self.assertEqual(first["entities_by_kind"], {"campus": 229, "project": 167})
        self.assertEqual(first["evidence_records"], 243)
        self.assertEqual(first["capacity_estimates"], 411)
        self.assertEqual(first["construction_pipeline_records"], 208)
        self.assertEqual(first["construction_source_signals"], 174)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exactly_v34_plus_the_six_approved_sources(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(REJECTED_DEFINITION.read_bytes()).hexdigest(),
            REJECTED_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((REJECTED_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            REJECTED_MANIFEST_SHA256,
        )

        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        rejected = json.loads(REJECTED_DEFINITION.read_text(encoding="utf-8"))
        base_pins = {record["path"]: record["sha256"] for record in base["curated_inputs"]}
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        rejected_paths = {record["path"] for record in rejected["curated_inputs"]}

        self.assertEqual(len(base_pins), 164)
        self.assertEqual(len(current_pins), 170)
        self.assertEqual(set(current_pins) - set(base_pins), set(SOURCE_HASHES))
        self.assertEqual(set(base_pins) - set(current_pins), set())
        self.assertEqual(
            {path: current_pins[path] for path in SOURCE_HASHES}, SOURCE_HASHES
        )
        self.assertTrue(REJECTED_PATHS <= rejected_paths)
        self.assertTrue(REJECTED_PATHS.isdisjoint(current_pins))
        self.assertNotEqual(set(current_pins), rejected_paths)
        ordered_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered_paths, sorted(ordered_paths))
        self.assertEqual(len(set(ordered_paths)), 170)

        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v37")
        self.assertEqual(current["build"], {"as_of": AS_OF, "recorded_at": RECORDED_AT})
        self.assertEqual(base["build"]["as_of"], current["build"]["as_of"])
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

    def test_every_v34_csv_row_is_byte_exact_and_only_expected_rows_are_added(self) -> None:
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
        after_entities = by_id(RELEASE / "entities.csv", "entity_id")
        self.assertEqual(
            {key: after_entities[key] for key in before_entities}, before_entities
        )
        added_entities = [
            after_entities[key] for key in set(after_entities) - set(before_entities)
        ]
        self.assertEqual({row["stable_key"] for row in added_entities}, ENTITY_KEYS)

        before_evidence = by_id(BASE_RELEASE / "evidence.csv", "evidence_id")
        after_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        self.assertEqual(
            {key: after_evidence[key] for key in before_evidence}, before_evidence
        )
        added_evidence = [
            after_evidence[key] for key in set(after_evidence) - set(before_evidence)
        ]
        self.assertEqual(
            {row["content_hash"] for row in added_evidence}, EXPORTED_EVIDENCE_HASHES
        )
        self.assertNotIn(YVA_GUARDRAIL_HASH, {row["content_hash"] for row in after_evidence.values()})

    def test_new_rows_preserve_narrow_roles_status_capacity_and_yva_boundary(self) -> None:
        before = by_id(BASE_RELEASE / "entities.csv", "entity_id")
        current = by_id(RELEASE / "entities.csv", "entity_id")
        added = [current[key] for key in set(current) - set(before)]
        by_key = {row["stable_key"]: row for row in added}

        for stable_key, row in by_key.items():
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["status"], PROJECT_STATUSES.get(stable_key, ""))

        expected_roles = {
            "curated:digital-edge-cgk-campus-bekasi": {"role:developer": "Digital Edge"},
            "curated:digital-edge-cgk-campus-bekasi:cgk1": {"role:developer": "Digital Edge"},
            "curated:hyperco-dayone-koria-unnamed-data-center-campus": {"role:user": "TikTok"},
            "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build": {"role:user": "TikTok"},
            "curated:hyperco-loviisa-data-center-campus": {"role:developer": "Hyperco"},
            "curated:hyperco-loviisa-data-center-campus:current-development": {"role:developer": "Hyperco"},
            "curated:macquarie-ic3-super-west-facility": {"role:developer": "Macquarie Data Centres"},
            "curated:macquarie-ic3-super-west-facility:phase-1-build": {"role:developer": "Macquarie Data Centres"},
            "curated:merlin-lisbon-data-center-campus": {},
            "curated:merlin-lisbon-data-center-campus:phase-2-two-building-development": {},
            "curated:moro-hub-warsan-new-green-data-centre": {"role:developer": "Moro Hub"},
            "curated:moro-hub-warsan-new-green-data-centre:phase-1": {"role:developer": "Moro Hub"},
        }
        for stable_key, expected in expected_roles.items():
            tags = json.loads(by_key[stable_key]["tags_json"])
            roles = {key: value for key, value in tags.items() if key.startswith("role:")}
            self.assertEqual(roles, expected, stable_key)

        entity_keys = {row["entity_id"]: row["stable_key"] for row in added}
        base_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        current_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        capacity_specs = {
            (
                entity_keys[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["base"],
                row["unit"],
                row["method"],
            )
            for packed, count in (current_capacity - base_capacity).items()
            for row in [dict(packed)]
            for _ in range(count)
        }
        self.assertEqual(
            capacity_specs,
            {
                ("curated:digital-edge-cgk-campus-bekasi", "critical_it_mw", "planned", "500.0", "MW", "reported"),
                ("curated:digital-edge-cgk-campus-bekasi", "pue", "design", "1.25", "ratio", "reported"),
                ("curated:macquarie-ic3-super-west-facility", "critical_it_mw", "planned", "47.0", "MW", "reported"),
                ("curated:macquarie-ic3-super-west-facility", "pue", "design", "1.28", "ratio", "reported"),
                ("curated:macquarie-ic3-super-west-facility:phase-1-build", "critical_it_mw", "planned", "6.0", "MW", "reported"),
                ("curated:merlin-lisbon-data-center-campus:phase-2-two-building-development", "critical_it_mw", "planned", "80.0", "MW", "calculated"),
            },
        )
        self.assertFalse(any("hyperco-dayone-koria" in key for key, *_ in capacity_specs))

        koria_source = json.loads(
            (ROOT / "sources/curated-official-2026-07-20-hyperco-dayone-koria-v2.json").read_text(encoding="utf-8")
        )
        yva = next(item for item in koria_source["evidence"] if item["content_hash"] == YVA_GUARDRAIL_HASH)
        self.assertEqual(yva["metadata"]["reported_proposed_option"]["critical_it_capacity"]["value"], 100)
        self.assertEqual(yva["metadata"]["reported_proposed_option"]["total_electric_capacity"]["value"], 130)
        self.assertEqual(koria_source["capacities"], [])

    def test_pipeline_signals_summary_and_source_families_match_exact_delta(self) -> None:
        base_pipeline = by_id(BASE_RELEASE / "construction_pipeline.csv", "entity_id")
        current_pipeline = by_id(RELEASE / "construction_pipeline.csv", "entity_id")
        added_pipeline = [
            current_pipeline[key]
            for key in set(current_pipeline) - set(base_pipeline)
        ]
        self.assertEqual(
            {row["stable_key"]: row["status"] for row in added_pipeline},
            PROJECT_STATUSES,
        )

        signal_id = "source_observation_evidence_id"
        base_signals = by_id(BASE_RELEASE / "construction_source_signals.csv", signal_id)
        current_signals = by_id(RELEASE / "construction_source_signals.csv", signal_id)
        added_signals = [
            current_signals[key] for key in set(current_signals) - set(base_signals)
        ]
        self.assertEqual(len(added_signals), 6)
        self.assertEqual(
            {row["representative_stable_key"] for row in added_signals},
            set(PROJECT_STATUSES),
        )

        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text(encoding="utf-8"))
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            NEW_SOURCE_FAMILIES,
        )
        self.assertNotIn("kouvola_city_meeting_records", manifest["source_families"])

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 396)
        self.assertEqual(summary["projects_total"], 167)
        self.assertEqual(summary["evidence_total"], 274)
        self.assertEqual(summary["entities_by_status"]["shell"], 7)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 138)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(summary["capacity_estimates_current"], 411)
        self.assertEqual(summary["capacity_estimates_by_metric"]["critical_it_mw"], 176)
        self.assertEqual(summary["capacity_estimates_by_metric"]["pue"], 3)


if __name__ == "__main__":
    unittest.main()
