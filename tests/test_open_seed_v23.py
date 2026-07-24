from __future__ import annotations

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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v23.json"
RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v23"
PREVIOUS_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v22.json"
PREVIOUS_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v22"

DEFINITION_SHA256 = "d36b0ea8708e117273a311da8ea0ac8c68c53072f9af3293e014d71d58f55b03"
MANIFEST_SHA256 = "2fa589dca179e1f600c695864599170bce1359ab82eb3559c70b6b6bf25398c5"
PREVIOUS_DEFINITION_SHA256 = (
    "00e22edf84e73913c3e98f72b47a1f5c4a7bd792c0fd558b2cc2a48d95fd8b84"
)
PREVIOUS_MANIFEST_SHA256 = (
    "21f0d4b98f01573fe7f9f4a5bc4dc0e2b2595d57863bfc349bd101e5b0bf2316"
)
RECORDED_AT = "2026-07-19T20:50:00Z"

SOURCE_HASHES = {
    "curated-official-2026-07-19-elea-rjo2-rio-ai-city.json": (
        "ce29b165b7599bda10b5410a1314f210adfed7c9198c24ad239f3bb52ddf7f01"
    ),
    "curated-official-2026-07-19-equinix-rj3-rio-de-janeiro-phase-2.json": (
        "43988c572ddae30921854c6ff7bc9e14ba8d06e8cf3592df0ec881ace49275af"
    ),
    "curated-official-2026-07-19-equinix-sp4-sao-paulo-phase-5.json": (
        "10f64d09105b5d2b05befaee0393376fe902c67ac721ab7eeed7986ce227c6e4"
    ),
    "curated-official-2026-07-19-equinix-sp7-sao-paulo-phase-1.json": (
        "2e53c941c1c17505f6ade429c97798021de5af39f6a3ffdceab6f93a26c369d7"
    ),
    "curated-official-2026-07-19-takoda-rj02-rio-de-janeiro.json": (
        "60bfbbe638897f28e79f8f72920eacec0f4d8e3faa1885108aef6bac18f646b6"
    ),
    "curated-official-2026-07-19-takoda-sp03-sumare.json": (
        "7c2b3935816e0c11206f71384ed2bdafa50dec66d3729fc1d3ae96e1b7b72cdd"
    ),
    "curated-official-2026-07-19-tecto-tgru1-santana-de-parnaiba.json": (
        "875e5b1777973e7dd2ded1b2dbeae5aa63700385a8b529d81ac89c75f5fd7f51"
    ),
    "curated-official-2026-07-19-tecto-tpoa1-porto-alegre.json": (
        "a84fc185750ce3e7a8739088eae88cd249fde18da28d428920a97fdd04f8f8cc"
    ),
}
TRANCHE_TEST_SHA256 = (
    "d35c999beb96393db12cc26e7b6a5270113ed8636a8f0d7cbd52b475b775fb4f"
)
EVIDENCE_CONTENT_HASHES = {
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54",
    "bcd576a3e543160839532193f938640efdb1732cd949809bd400ffed85782c8f",
    "c07cb1e22859d98c4a12802af63ca9396c36fa73755a1a2344a530f9dad5dc98",
    "c79ccd8ac6abb8d2b74867c74745b60db25c718c6941f25701a7079bbc0469cd",
    "d94b3c0e74e521f76af7c1487a6c90f5f9c502c0fb0efdcdee366a96a447810a",
    "ecdc86b877d38daaed5c5e12d35c74574c75dc386869ef80444f18568b9e885e",
}

CAMPUS_KEYS = {
    "curated:elea-rjo2-rio-ai-city-data-center",
    "curated:equinix-rj3-rio-de-janeiro-data-center",
    "curated:equinix-sp4-sao-paulo-data-center",
    "curated:equinix-sp7-sao-paulo-data-center",
    "curated:takoda-rj02-rio-de-janeiro-data-center",
    "curated:takoda-sp03-sumare-data-center",
    "curated:tecto-tgru1-santana-de-parnaiba-data-center",
    "curated:tecto-tpoa1-porto-alegre-data-center",
}
PROJECT_KEYS = {
    "curated:elea-rjo2-rio-ai-city-data-center:current-facility-build",
    "curated:equinix-rj3-rio-de-janeiro-data-center:phase-2",
    "curated:equinix-sp4-sao-paulo-data-center:phase-5",
    "curated:equinix-sp7-sao-paulo-data-center:phase-1",
    "curated:takoda-rj02-rio-de-janeiro-data-center:current-facility-build",
    "curated:takoda-sp03-sumare-data-center:current-facility-build",
    "curated:tecto-tgru1-santana-de-parnaiba-data-center:current-facility-build",
    "curated:tecto-tpoa1-porto-alegre-data-center:current-facility-build",
}
NEW_ENTITY_KEYS = CAMPUS_KEYS | PROJECT_KEYS


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_set(path: Path) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(row.items())) for row in rows(path)}


def added_rows(filename: str) -> list[dict[str, str]]:
    previous = row_set(PREVIOUS_RELEASE / filename)
    return [
        row
        for row in rows(RELEASE / filename)
        if tuple(sorted(row.items())) not in previous
    ]


class OpenSeedV23Tests(unittest.TestCase):
    def test_release_rebuilds_twice_offline_with_byte_identity(self) -> None:
        self.assertEqual(hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
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
        self.assertEqual(first["entities"], 316)
        self.assertEqual(first["entities_by_kind"], {"campus": 189, "project": 127})
        self.assertEqual(first["evidence_records"], 196)
        self.assertEqual(first["capacity_estimates"], 393)
        self.assertEqual(first["construction_pipeline_records"], 168)
        self.assertEqual(first["construction_source_signals"], 137)
        self.assertEqual(first["resolution_candidates"], 4)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["entities_total"], 316)
        self.assertEqual(summary["projects_total"], 127)
        self.assertEqual(summary["evidence_total"], 218)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 104)
        self.assertEqual(summary["entities_by_country"]["Brazil"], 24)
        self.assertEqual(
            summary["capacity_base_totals"]["critical_it_mw"]["planned"],
            {"base": 4704.6, "count": 40, "unit": "MW"},
        )

    def test_v22_closure_is_sealed_and_v23_is_exactly_eight_inputs_additive(self) -> None:
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )

        expected_deltas = {
            "entities.csv": 16,
            "evidence.csv": 6,
            "capacity_estimates.csv": 0,
            "construction_pipeline.csv": 8,
            "construction_source_signals.csv": 5,
            "resolution_candidates.csv": 0,
        }
        for filename, expected_delta in expected_deltas.items():
            self.assertTrue(
                row_set(PREVIOUS_RELEASE / filename) <= row_set(RELEASE / filename),
                filename,
            )
            self.assertEqual(
                len(rows(RELEASE / filename)) - len(rows(PREVIOUS_RELEASE / filename)),
                expected_delta,
                filename,
            )

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
        previous_records = {json.dumps(record, sort_keys=True) for record in previous_sources}
        current_records = {json.dumps(record, sort_keys=True) for record in current_sources}
        self.assertTrue(previous_records <= current_records)
        added_sources = [
            record
            for record in current_sources
            if json.dumps(record, sort_keys=True) not in previous_records
        ]
        self.assertEqual(len(added_sources), 6)
        self.assertEqual(
            {record["provenance"]["content_hash"] for record in added_sources},
            EVIDENCE_CONTENT_HASHES,
        )

        previous_summary = json.loads(
            (PREVIOUS_RELEASE / "summary.json").read_text(encoding="utf-8")
        )
        current_summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(current_summary["evidence_total"] - previous_summary["evidence_total"], 9)

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
        self.assertEqual(len(previous_inputs), 122)
        self.assertEqual(len(current_inputs), 130)
        self.assertEqual(current_inputs, previous_inputs | expected_additions)
        self.assertEqual(current_inputs - previous_inputs, expected_additions)
        self.assertEqual(previous_inputs, current_inputs - expected_additions)
        input_paths = [record["path"] for record in current["curated_inputs"]]
        input_hashes = [record["sha256"] for record in current["curated_inputs"]]
        self.assertEqual(input_paths, sorted(input_paths))
        self.assertEqual(len(input_paths), len(set(input_paths)))
        self.assertEqual(len(input_hashes), len(set(input_hashes)))
        self.assertEqual(current["release_id"], "2026-07-19-open-seed-v23")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in set(previous) - {"build", "curated_inputs", "expected_release", "expected_summary", "release_id"}:
            self.assertEqual(current[key], previous[key], key)

    def test_new_rows_preserve_only_audited_semantics(self) -> None:
        tranche_test = ROOT / "tests" / "test_curated_latam_official_next_tranche.py"
        self.assertEqual(hashlib.sha256(tranche_test.read_bytes()).hexdigest(), TRANCHE_TEST_SHA256)

        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        inputs = {
            Path(record["path"]).name: record["sha256"]
            for record in definition["curated_inputs"]
        }
        documents = []
        for filename, expected_hash in SOURCE_HASHES.items():
            source = ROOT / "sources" / filename
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected_hash)
            self.assertEqual(inputs[filename], expected_hash)
            document = json.loads(source.read_text(encoding="utf-8"))
            documents.append(document)
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            self.assertEqual(document["lifecycle"][0]["value"], "under_construction")

        self.assertEqual({d["campus"]["stable_key"] for d in documents}, CAMPUS_KEYS)
        self.assertEqual({d["project"]["stable_key"] for d in documents}, PROJECT_KEYS)

        entity_rows = {row["stable_key"]: row for row in rows(RELEASE / "entities.csv")}
        previous_keys = {row["stable_key"] for row in rows(PREVIOUS_RELEASE / "entities.csv")}
        self.assertEqual(set(entity_rows) - previous_keys, NEW_ENTITY_KEYS)
        for key in NEW_ENTITY_KEYS:
            row = entity_rows[key]
            self.assertEqual(row["country"], "Brazil")
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["owner"], "")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertEqual(row["geometry_json"], "null")
            self.assertFalse(any(name.startswith("role:") for name in json.loads(row["tags_json"])))
        self.assertTrue(all(entity_rows[key]["status"] == "under_construction" for key in PROJECT_KEYS))
        self.assertEqual(
            {row["stable_key"] for row in added_rows("construction_pipeline.csv")},
            PROJECT_KEYS,
        )

        added_signals = added_rows("construction_source_signals.csv")
        self.assertEqual(len(added_signals), 5)
        affected_keys = []
        counts_by_hash = {}
        for signal in added_signals:
            affected = json.loads(signal["affected_entities_json"])
            self.assertEqual(int(signal["affected_entity_count"]), len(affected))
            affected_keys.extend(entity["stable_key"] for entity in affected)
            counts_by_hash[signal["source_content_hash"]] = len(affected)
        self.assertEqual(set(affected_keys), PROJECT_KEYS)
        self.assertEqual(len(affected_keys), len(PROJECT_KEYS))
        self.assertEqual(counts_by_hash["a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"], 3)
        self.assertEqual(counts_by_hash["bcd576a3e543160839532193f938640efdb1732cd949809bd400ffed85782c8f"], 2)

        added_evidence = added_rows("evidence.csv")
        self.assertEqual(len(added_evidence), 6)
        self.assertEqual({row["content_hash"] for row in added_evidence}, EVIDENCE_CONTENT_HASHES)


if __name__ == "__main__":
    unittest.main()
