from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v35.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v35"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v34.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v34"

DEFINITION_SHA256 = "ade1722f44a8a97f848d94579a4cfc45bc96f7f706df80f38ad6c46cabc5735d"
MANIFEST_SHA256 = "47994a012f4a97ca6dcdafb55c6b98a7121397a843ec1857328acd7953988123"
PREVIOUS_DEFINITION_SHA256 = (
    "004513441aaffbe7ce85562b993fcf4a6d15f9630aad6fab21ce46f359f47264"
)
PREVIOUS_MANIFEST_SHA256 = (
    "66344585b802b3640d5921e37cf64cbc990eaa3a2e8b2a44f1891acbe8887d4a"
)
RECORDED_AT = "2026-07-20T00:40:00Z"
AS_OF = "2026-07-20"

SOURCE_HASHES = {
    "curated-official-2026-07-20-hyperco-dayone-koria.json": (
        "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63"
    ),
    "curated-official-2026-07-20-hyperco-loviisa.json": (
        "048814c8816ca428d2e3ec557836c907049fcf327279870e01480b46a6a4d19d"
    ),
}

KORIA_KEYS = {
    "curated:hyperco-dayone-koria-unnamed-data-center-campus",
    "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build",
}
LOVIISA_KEYS = {
    "curated:hyperco-loviisa-data-center-campus",
    "curated:hyperco-loviisa-data-center-campus:current-development",
}
PROJECT_KEYS = {
    "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build",
    "curated:hyperco-loviisa-data-center-campus:current-development",
}
NEW_ENTITY_KEYS = KORIA_KEYS | LOVIISA_KEYS

EXPORTED_EVIDENCE_HASHES = {
    "cf29dcde78b9e08e421b599658dc93396a03bef0b7a7aaf18e1e05dc98312269",
    "631f136b57cea6d06ef390665dfc86b7a42c84a7b517d6863b69d76cb3a4358a",
    "3951720ead85f71d6e79f833efcd95bc97811377cfa0067ca22f30798f8c44aa",
}
STATUS_EVIDENCE_HASHES = {
    "cf29dcde78b9e08e421b599658dc93396a03bef0b7a7aaf18e1e05dc98312269",
    "631f136b57cea6d06ef390665dfc86b7a42c84a7b517d6863b69d76cb3a4358a",
}
NEW_SOURCE_FAMILIES = {
    "kouvola_city_news",
    "loviisa_city_news",
    "metsahallitus_press_releases",
}

CSV_COUNTS = {
    "entities.csv": (384, 388),
    "evidence.csv": (233, 236),
    "capacity_estimates.csv": (405, 405),
    "construction_pipeline.csv": (202, 204),
    "construction_source_signals.csv": (168, 170),
    "resolution_candidates.csv": (4, 4),
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def by_id(path: Path, field: str) -> dict[str, dict[str, str]]:
    result = {row[field]: row for row in rows(path)}
    if len(result) != len(rows(path)):
        raise AssertionError(f"duplicate {field} in {path}")
    return result


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


class OpenSeedV35Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        network_error = AssertionError("offline v35 validation attempted network access")
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

        self.assertEqual(first["as_of"], AS_OF)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 388)
        self.assertEqual(first["entities_by_kind"], {"campus": 225, "project": 163})
        self.assertEqual(first["evidence_records"], 236)
        self.assertEqual(first["capacity_estimates"], 405)
        self.assertEqual(first["construction_pipeline_records"], 204)
        self.assertEqual(first["construction_source_signals"], 170)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exact_v34_successor(self) -> None:
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
        self.assertEqual(len(previous["curated_inputs"]), 164)
        self.assertEqual(len(current["curated_inputs"]), 166)
        self.assertEqual(current["curated_inputs"][:164], previous["curated_inputs"])
        self.assertEqual(
            current["curated_inputs"][164:],
            [
                {"path": f"sources/{name}", "sha256": digest}
                for name, digest in SOURCE_HASHES.items()
            ],
        )
        input_paths = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(set(input_paths)), 166)

        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v35")
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

        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertFalse(source.is_symlink())
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)

        source_documents = {
            name: json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))
            for name in SOURCE_HASHES
        }
        self.assertEqual(
            {
                evidence["content_hash"]
                for document in source_documents.values()
                for evidence in document["evidence"]
            },
            EXPORTED_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {
                evidence["source_family"]
                for document in source_documents.values()
                for evidence in document["evidence"]
            },
            NEW_SOURCE_FAMILIES,
        )
        self.assertEqual(
            source_documents[
                "curated-official-2026-07-20-hyperco-dayone-koria.json"
            ]["campus"]["roles"],
            {"user": ["TikTok"]},
        )
        self.assertEqual(
            source_documents[
                "curated-official-2026-07-20-hyperco-loviisa.json"
            ]["campus"]["roles"],
            {"developer": ["Hyperco"]},
        )
        for document in source_documents.values():
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            for entity in (document["campus"], document["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])

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

    def test_all_predecessor_csv_rows_are_exactly_unchanged(self) -> None:
        for filename, (previous_count, current_count) in CSV_COUNTS.items():
            before = row_counter(PREVIOUS_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            self.assertEqual(sum(before.values()), previous_count, filename)
            self.assertEqual(sum(after.values()), current_count, filename)
            self.assertEqual(before & after, before, filename)
            self.assertEqual(
                sum((after - before).values()), current_count - previous_count, filename
            )

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

        previous_entities = by_id(PREVIOUS_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        self.assertEqual(
            {key: current_entities[key] for key in previous_entities},
            previous_entities,
        )
        self.assertEqual(
            {
                current_entities[key]["stable_key"]
                for key in set(current_entities) - set(previous_entities)
            },
            NEW_ENTITY_KEYS,
        )

    def test_new_entities_roles_and_missing_fields_are_narrow(self) -> None:
        previous_entities = by_id(PREVIOUS_RELEASE / "entities.csv", "entity_id")
        current_entities = by_id(RELEASE / "entities.csv", "entity_id")
        added = [
            current_entities[key]
            for key in set(current_entities) - set(previous_entities)
        ]
        self.assertEqual(len(added), 4)

        for row in added:
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            role_tags = {
                key: value
                for key, value in json.loads(row["tags_json"]).items()
                if key.startswith("role:")
            }
            if row["stable_key"] in KORIA_KEYS:
                self.assertEqual(row["users"], "TikTok")
                self.assertEqual(role_tags, {"role:user": "TikTok"})
            else:
                self.assertIn(row["stable_key"], LOVIISA_KEYS)
                self.assertEqual(row["users"], "")
                self.assertEqual(role_tags, {"role:developer": "Hyperco"})

            if row["stable_key"] in PROJECT_KEYS:
                self.assertEqual(row["status"], "under_construction")
            else:
                self.assertEqual(row["status"], "")

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
        self.assertEqual(len(added_evidence), 3)
        self.assertEqual(
            {row["content_hash"] for row in added_evidence},
            EXPORTED_EVIDENCE_HASHES,
        )

    def test_pipeline_signals_summary_and_families_match_exact_delta(self) -> None:
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
        self.assertEqual(
            {row["stable_key"] for row in added_pipeline}, PROJECT_KEYS
        )
        self.assertEqual({row["status"] for row in added_pipeline}, {"under_construction"})

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
        self.assertEqual(len(added_signals), 2)
        self.assertEqual(
            {row["source_content_hash"] for row in added_signals},
            STATUS_EVIDENCE_HASHES,
        )
        self.assertEqual(
            {row["representative_stable_key"] for row in added_signals},
            PROJECT_KEYS,
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
        current_summary = json.loads(
            (RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(current_summary["entities_total"], 388)
        self.assertEqual(current_summary["projects_total"], 163)
        self.assertEqual(current_summary["evidence_total"], 265)
        self.assertEqual(current_summary["entities_by_status"]["under_construction"], 135)
        self.assertEqual(current_summary["entities_with_coordinates"], 139)
        self.assertEqual(current_summary["capacity_estimates_current"], 405)
        self.assertEqual(current_summary["capacity_base_totals"], previous_summary["capacity_base_totals"])
        self.assertEqual(
            current_summary["capacity_estimates_by_metric"],
            previous_summary["capacity_estimates_by_metric"],
        )
        self.assertEqual(current_summary["capacity_estimates_by_metric"]["pue"], 1)


if __name__ == "__main__":
    unittest.main()
