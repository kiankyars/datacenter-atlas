from __future__ import annotations

from collections import Counter
import copy
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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v34.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v34"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v33.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v33"

DEFINITION_SHA256 = "004513441aaffbe7ce85562b993fcf4a6d15f9630aad6fab21ce46f359f47264"
MANIFEST_SHA256 = "66344585b802b3640d5921e37cf64cbc990eaa3a2e8b2a44f1891acbe8887d4a"
PREVIOUS_DEFINITION_SHA256 = (
    "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
)
PREVIOUS_MANIFEST_SHA256 = (
    "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
)
PREVIOUS_TEST_SHA256 = (
    "77b506c113a45e950997fee9ae310e2d3d0a59d472b0fd396366bff2e144a773"
)
TRANCHE_TEST_SHA256 = (
    "967403436b4f14c169ddb0e0fae08ac0d080bcb7645ddc8dd464d7ea80ad69a7"
)
RECORDED_AT = "2026-07-20T00:04:32Z"
PREVIOUS_AS_OF = "2026-07-19"
CURRENT_AS_OF = "2026-07-20"

SOURCE_HASHES = {
    "curated-official-2026-07-20-atnorth-fin04-kouvola.json": (
        "28773caea4d839386074e6bd3003953c75c9f1bbd3441442a83cfc2d9ca22fe4"
    ),
    "curated-official-2026-07-20-atnorth-swe02-stockholm.json": (
        "c69edf4c7c7b7f705ce3489f3ee1f112fab2032c0483a3a1b4ace77d84283169"
    ),
    "curated-official-2026-07-20-green-mountain-undheim.json": (
        "98ebd4adc98dae26061b64445f6e1f33c8ed92ffeed30b99c163ff42ad03f5f0"
    ),
}
TERACO_SOURCE = "curated-official-2026-07-20-teraco-jb7-isando.json"

CAMPUS_KEYS = {
    "curated:atnorth-fin04-kouvola-campus",
    "curated:atnorth-swe02-stockholm-campus",
    "curated:green-mountain-undheim-campus",
}
PROJECT_KEYS = {
    "curated:atnorth-fin04-kouvola-campus:phase-1",
    "curated:atnorth-swe02-stockholm-campus:current-development",
    "curated:green-mountain-undheim-campus:current-two-building-development",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS
TERACO_KEYS = {
    "curated:teraco-isando-campus",
    "curated:teraco-isando-campus:jb7",
}

ALL_SOURCE_EVIDENCE_HASHES = {
    "0149380e87955775c8cbd6df91e795c45fc45a1b60cce9632afb941bac4a2efc",
    "134e4704fe1e193077c73dfa938660c4e6ff422052d9e883ca9f5c4b2c877a9f",
    "2b7995a34c638735c41705c077f6c6adbc00af1154ef8890f3b58f0a26df743c",
    "43ffdfa6c4b1c83c367e27aa282e0e307026a1a0d2419da7e54453626f1ed26c",
    "7d503232b148c6069a4cd2a3f92be6b50b2dd43bb99fa7c370f77a3feb8eba6b",
    "fe78d9e79cf8afe02db9cbd5fe225b9d3d9ebd93ca484c692a4ae8941ff75e04",
}
EXPORTED_EVIDENCE_HASHES = {
    "2b7995a34c638735c41705c077f6c6adbc00af1154ef8890f3b58f0a26df743c",
    "43ffdfa6c4b1c83c367e27aa282e0e307026a1a0d2419da7e54453626f1ed26c",
    "7d503232b148c6069a4cd2a3f92be6b50b2dd43bb99fa7c370f77a3feb8eba6b",
}
SOURCE_LEVEL_FAMILIES = {
    "atnorth_newsroom",
    "green_mountain_project_pages",
    "kouvola_city_news",
}
EXPORTED_SOURCE_FAMILIES = {
    "atnorth_newsroom",
    "green_mountain_project_pages",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def by_id(path: Path, field: str) -> dict[str, dict[str, str]]:
    return {row[field]: row for row in rows(path)}


def _normalize_release_date(value: str) -> str:
    return "<release-as-of>" if value in {PREVIOUS_AS_OF, CURRENT_AS_OF} else value


def _normalize_json_dates(raw: str) -> str:
    document = json.loads(raw)
    for record in document:
        if "as_of_date" in record:
            record["as_of_date"] = _normalize_release_date(record["as_of_date"])
        if "status_as_of" in record:
            record["status_as_of"] = _normalize_release_date(record["status_as_of"])
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def normalize_entity_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    normalized["status_as_of"] = _normalize_release_date(normalized["status_as_of"])
    normalized["snapshot_as_of"] = _normalize_release_date(
        normalized["snapshot_as_of"]
    )
    normalized["workloads_json"] = _normalize_json_dates(normalized["workloads_json"])
    normalized["capacity_estimates_json"] = _normalize_json_dates(
        normalized["capacity_estimates_json"]
    )
    return normalized


def normalize_capacity_row(row: dict[str, str]) -> tuple[tuple[str, str], ...]:
    normalized = dict(row)
    normalized["as_of_date"] = _normalize_release_date(normalized["as_of_date"])
    return tuple(sorted(normalized.items()))


def normalize_signal_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    normalized["representative_status_as_of"] = _normalize_release_date(
        normalized["representative_status_as_of"]
    )
    normalized["affected_entities_json"] = _normalize_json_dates(
        normalized["affected_entities_json"]
    )
    return normalized


class OpenSeedV34Tests(unittest.TestCase):
    def _offline_patches(self) -> tuple[object, ...]:
        error = AssertionError("offline validator attempted network access")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

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

        patches = self._offline_patches()
        for network_patch in patches:
            network_patch.start()
        try:
            first = validate_open_seed_release(DEFINITION, RELEASE)
            self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
            second = validate_open_seed_release(DEFINITION, RELEASE)
        finally:
            for network_patch in reversed(patches):
                network_patch.stop()

        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["as_of"], CURRENT_AS_OF)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 384)
        self.assertEqual(first["entities_by_kind"], {"campus": 223, "project": 161})
        self.assertEqual(first["evidence_records"], 233)
        self.assertEqual(first["capacity_estimates"], 405)
        self.assertEqual(first["construction_pipeline_records"], 202)
        self.assertEqual(first["construction_source_signals"], 168)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 384)
        self.assertEqual(summary["projects_total"], 161)
        self.assertEqual(summary["evidence_total"], 262)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 133)
        self.assertEqual(summary["entities_with_coordinates"], 139)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4954.6, "count": 46, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["gross_facility_mw"]["planned"],
            {"base": 295.0, "count": 3, "unit": "MW"},
        )
        self.assertEqual(
            summary["capacity_base_totals"]["pue"],
            {"design": {"base": 1.2, "count": 1, "unit": "ratio"}},
        )

    def test_definition_is_exact_v33_successor_and_excludes_teraco(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((ROOT / "tests" / "test_open_seed_v33.py").read_bytes()).hexdigest(),
            PREVIOUS_TEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "tests" / "test_curated_green_teraco_atnorth_20260720.py").read_bytes()
            ).hexdigest(),
            TRANCHE_TEST_SHA256,
        )

        previous = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(len(previous["curated_inputs"]), 161)
        self.assertEqual(len(current["curated_inputs"]), 164)
        self.assertEqual(current["curated_inputs"][:161], previous["curated_inputs"])
        expected_additions = [
            {"path": f"sources/{name}", "sha256": digest}
            for name, digest in SOURCE_HASHES.items()
        ]
        self.assertEqual(current["curated_inputs"][161:], expected_additions)
        self.assertEqual(
            [record["path"] for record in current["curated_inputs"]],
            sorted(record["path"] for record in current["curated_inputs"]),
        )
        self.assertEqual(
            len({record["path"] for record in current["curated_inputs"]}), 164
        )
        self.assertNotIn(
            f"sources/{TERACO_SOURCE}",
            {record["path"] for record in current["curated_inputs"]},
        )
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v34")
        self.assertEqual(
            current["build"],
            {"as_of": CURRENT_AS_OF, "recorded_at": RECORDED_AT},
        )
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

        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertFalse(source.is_symlink())
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            evidence = json.loads(source.read_text(encoding="utf-8"))["evidence"]
            self.assertEqual({row["retrieved_at"] for row in evidence}, {
                max(row["retrieved_at"] for row in evidence)
            })
        source_documents = [
            json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))
            for name in SOURCE_HASHES
        ]
        self.assertEqual(
            {row["content_hash"] for document in source_documents for row in document["evidence"]},
            ALL_SOURCE_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {row["source_family"] for document in source_documents for row in document["evidence"]},
            SOURCE_LEVEL_FAMILIES,
        )
        self.assertEqual(
            max(row["retrieved_at"] for document in source_documents for row in document["evidence"]),
            RECORDED_AT,
        )

        mutated = copy.deepcopy(current)
        mutated["scope"]["commercial_census_parity_claimed"] = True
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            candidate = Path(temporary) / "sources" / "mutated.json"
            candidate.parent.mkdir()
            candidate.write_text(
                json.dumps(mutated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(OpenSeedReleaseError, "scope guardrails"):
                validate_open_seed_release(candidate, RELEASE)

    def test_exact_additions_and_controlled_epoch_date_refresh(self) -> None:
        previous_entities = by_id(PREVIOUS_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        self.assertEqual(set(previous_entities), set(previous_entities) & set(current_entities))
        added_entity_ids = set(current_entities) - set(previous_entities)
        self.assertEqual(
            {current_entities[key]["stable_key"] for key in added_entity_ids},
            NEW_ENTITY_KEYS,
        )
        self.assertTrue(
            TERACO_KEYS.isdisjoint(row["stable_key"] for row in current_entities.values())
        )

        changed_ids = {
            key
            for key in previous_entities
            if previous_entities[key] != current_entities[key]
        }
        self.assertEqual(len(changed_ids), 74)
        self.assertTrue(
            all(previous_entities[key]["stable_key"].startswith("epoch-ai:") for key in changed_ids)
        )
        allowed_columns = {
            "status_as_of",
            "snapshot_as_of",
            "workloads_json",
            "capacity_estimates_json",
        }
        for key in previous_entities:
            before = previous_entities[key]
            after = current_entities[key]
            changed_columns = {
                column for column in before if before[column] != after[column]
            }
            self.assertTrue(changed_columns <= allowed_columns)
            self.assertEqual(normalize_entity_row(before), normalize_entity_row(after))

        for key in added_entity_ids:
            row = current_entities[key]
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            if row["stable_key"] in CAMPUS_KEYS:
                self.assertEqual(row["status"], "")
            else:
                self.assertEqual(row["status"], "under_construction")

        previous_evidence = by_id(PREVIOUS_RELEASE / "evidence.csv", "evidence_id")
        current_evidence = by_id(RELEASE / "evidence.csv", "evidence_id")
        self.assertEqual(
            {key: current_evidence[key] for key in previous_evidence}, previous_evidence
        )
        added_evidence = [
            current_evidence[key] for key in set(current_evidence) - set(previous_evidence)
        ]
        self.assertEqual(len(added_evidence), 3)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence}, EXPORTED_EVIDENCE_HASHES
        )
        self.assertEqual(
            json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))["evidence_total"]
            - json.loads((PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8"))["evidence_total"],
            6,
        )

        previous_capacity = Counter(
            normalize_capacity_row(row) for row in rows(PREVIOUS_RELEASE / "capacity_estimates.csv")
        )
        current_capacity = Counter(
            normalize_capacity_row(row) for row in rows(RELEASE / "capacity_estimates.csv")
        )
        self.assertEqual(previous_capacity & current_capacity, previous_capacity)
        additions = [dict(signature) for signature in (current_capacity - previous_capacity).elements()]
        self.assertEqual(len(additions), 2)
        id_to_key = {row["entity_id"]: row["stable_key"] for row in current_entities.values()}
        self.assertEqual(
            {
                (id_to_key[row["entity_id"]], row["metric"], row["stage"], float(row["base"]))
                for row in additions
            },
            {
                (
                    "curated:green-mountain-undheim-campus:current-two-building-development",
                    "critical_it_mw",
                    "planned",
                    80.0,
                ),
                (
                    "curated:green-mountain-undheim-campus:current-two-building-development",
                    "gross_facility_mw",
                    "planned",
                    100.0,
                ),
            },
        )
        self.assertEqual(
            [row for row in additions if row["metric"] == "pue"], []
        )

    def test_pipeline_signals_families_and_resolution_are_narrow(self) -> None:
        previous_pipeline = by_id(PREVIOUS_RELEASE / "construction_pipeline.csv", "entity_id")
        current_pipeline = by_id(RELEASE / "construction_pipeline.csv", "entity_id")
        self.assertEqual(set(previous_pipeline), set(previous_pipeline) & set(current_pipeline))
        self.assertEqual(
            {
                current_pipeline[key]["stable_key"]
                for key in set(current_pipeline) - set(previous_pipeline)
            },
            PROJECT_KEYS,
        )
        changed_pipeline = {
            key for key in previous_pipeline if previous_pipeline[key] != current_pipeline[key]
        }
        self.assertEqual(len(changed_pipeline), 45)
        for key in previous_pipeline:
            self.assertEqual(
                normalize_entity_row(previous_pipeline[key]),
                normalize_entity_row(current_pipeline[key]),
            )

        previous_signals = by_id(
            PREVIOUS_RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        current_signals = by_id(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        self.assertEqual(set(previous_signals), set(previous_signals) & set(current_signals))
        added_signals = [
            current_signals[key] for key in set(current_signals) - set(previous_signals)
        ]
        self.assertEqual(len(added_signals), 3)
        self.assertEqual(
            {row["source_content_hash"] for row in added_signals},
            EXPORTED_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {
                json.loads(row["affected_entities_json"])[0]["stable_key"]
                for row in added_signals
            },
            PROJECT_KEYS,
        )
        changed_signals = {
            key for key in previous_signals if previous_signals[key] != current_signals[key]
        }
        self.assertEqual(len(changed_signals), 45)
        for key in previous_signals:
            self.assertEqual(
                normalize_signal_row(previous_signals[key]),
                normalize_signal_row(current_signals[key]),
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
            EXPORTED_SOURCE_FAMILIES,
        )
        self.assertEqual(
            (RELEASE / "resolution_candidates.csv").read_bytes(),
            (PREVIOUS_RELEASE / "resolution_candidates.csv").read_bytes(),
        )
        self.assertEqual(
            (RELEASE / "resolution_candidates.json").read_bytes(),
            (PREVIOUS_RELEASE / "resolution_candidates.json").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
