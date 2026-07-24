from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v45.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v45"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"

DEFINITION_SHA256 = "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13"
MANIFEST_SHA256 = "275f5767c5f08208be7178126855ce5d3a77b217dbd53b2483450c46673b7a27"
BASE_DEFINITION_SHA256 = (
    "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
)
BASE_MANIFEST_SHA256 = (
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
)
RECORDED_AT = "2026-07-20T07:57:36Z"
MAX_INPUT_RETRIEVED_AT = "2026-07-20T07:24:40Z"
VNET_RETRIEVED_AT = "2026-07-20T07:24:19Z"
VNET_EVIDENCE_ID = "bb4018ca-2cb3-507e-b6a7-70c41d1ded23"
VNET_EVIDENCE_KEY = (
    "vnet-1q26-ir-presentation-wholesale-construction-pdf-"
    "captured-2026-07-20"
)

CODE_HASHES = {
    "datacenter_atlas/curated.py": "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12",
    "datacenter_atlas/open_seed_release.py": "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
    "datacenter_atlas/publication_release.py": "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510",
    "datacenter_atlas/release.py": "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056",
    "datacenter_atlas/release_contract_v4.py": "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169",
    "scripts/build_open_seed.py": "0603c8025ea4dc77866c9cb913ffbe9d8c9db2dbfda87ecc446732258d6732a8",
    "scripts/validate_open_seed_release.py": "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
}

TEST_HASHES = {
    "tests/test_curated_vnet_q1_2026.py": "7b34e6d1229b3a3daf66c4ae2fff476b437a1e3a8642492b5cb04331cc1d0966",
    "tests/test_open_seed_v44.py": "36c50b528a17d14397cab565b9d6fe3d3d6b7f7c4f98dea3a758601b568adcb0",
    "tests/test_open_seed_release.py": "392b806639033497b7c9f43f577cce2e18864c2710fb9d6c393191d1f924e05e",
    "tests/test_release.py": "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243",
    "tests/test_release_contract_v4.py": "7bc3c7d31576bd18597b1792f067abc018540e94b30ba960ef4e990828353ebd",
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-vnet-e-js03b.json": "acfae78267f91e6820b9f4d22a35fa3a828e4c9d53ae17b8ed58042a4f72330b",
    "sources/curated-official-2026-07-20-vnet-n-hb02.json": "6e0a83110457229986e6ab703954c221b5d6904b4a480c22dc9b65a1e05d79a6",
    "sources/curated-official-2026-07-20-vnet-n-hb03.json": "1bfdc6e845755e11871c882c4b80292f53f2407c6cdd25c30f69c504dfce5a01",
    "sources/curated-official-2026-07-20-vnet-n-hb04.json": "c89b4c2b0f93307e85f4fa5cb187c4157552c7d15eaea11587a59da4883fcfe9",
    "sources/curated-official-2026-07-20-vnet-n-or01.json": "b5963e09b58ec96fcd6065959ee9ee7b0c900ac15baa40dad99f813f543f7a4f",
    "sources/curated-official-2026-07-20-vnet-n-or02a.json": "0f7f78b11809e2d926df5820e6999b7dd843278fc6454a0249fb7dae7efda697",
    "sources/curated-official-2026-07-20-vnet-n-or02b.json": "50278632f21512a44c8d9549915f7a7239c6e21e9f5a49d04858802a07609645",
    "sources/curated-official-2026-07-20-vnet-n-or03.json": "4a6413620c698fda95ff58b90238b20b4ae474073bfe437b92f80bd5d21f31bb",
}

EXCLUDED_V2_INPUTS = {
    "sources/curated-official-2026-07-20-vnet-e-js03b-v2.json": "fca0e08c8a0348e54596d9b3009d3b61a4602bfb44e143530827d338f69cf933",
    "sources/curated-official-2026-07-20-vnet-n-hb02-v2.json": "d564746bc94cc05f93344ea427fce48796de9b6747bcf8b9073e2e1aef0d2522",
    "sources/curated-official-2026-07-20-vnet-n-hb03-v2.json": "06fe2a9d44ce961c06e8ea168d5a444fb3aec5da248cbbc178abe693e0c8e7c7",
    "sources/curated-official-2026-07-20-vnet-n-hb04-v2.json": "d109533127851b157df10ad017b552ea50ca82d6571386d7ae70a1efaf210854",
    "sources/curated-official-2026-07-20-vnet-n-or01-v2.json": "698b8cf3ec1ed5b578589dc1b9c34d92e30ab19305e0f242825862473447eb8f",
    "sources/curated-official-2026-07-20-vnet-n-or02a-v2.json": "6645c9853e1c4efe4c366e00086513f3ef7ca10b22c7cff512abca16053e8a82",
    "sources/curated-official-2026-07-20-vnet-n-or02b-v2.json": "d84c2febccae8c6c7c871fcd2bca7a2e14462538fa2d5c26b590ba0c3258589b",
    "sources/curated-official-2026-07-20-vnet-n-or03-v2.json": "980da0dea024ae56e6f30f855db78c9ce834c2ffc9dc5a024bfe9f8414ede895",
}
EXCLUDED_V2_TEST = {
    "tests/test_curated_vnet_q1_2026_v2.py": "ce1d8fb920c9ffcb3cafb9bfbbf4bff4a8234b8757356d031d3216dfbfeda79f",
}
EXCLUDED_V2_CAMPUS_KEYS = {
    f"curated:vnet-{slug}-locality-scoped-campus"
    for slug in (
        "e-js03b",
        "n-hb02",
        "n-hb03",
        "n-hb04",
        "n-or01",
        "n-or02a",
        "n-or02b",
        "n-or03",
    )
}
EXCLUDED_V2_PROJECT_KEYS = {
    f"{campus}:{campus.removeprefix('curated:vnet-').removesuffix('-locality-scoped-campus')}-under-construction"
    for campus in EXCLUDED_V2_CAMPUS_KEYS
}

YRD_ANCHOR = "curated:vnet-yangtze-river-delta-regional-wholesale-anchor"
BEIJING_ANCHOR = "curated:vnet-greater-beijing-area-regional-wholesale-anchor"
PROJECT_KEYS = {
    f"{YRD_ANCHOR}:e-js03b-under-construction",
    *{
        f"{BEIJING_ANCHOR}:{code}-under-construction"
        for code in ("n-hb02", "n-hb03", "n-hb04", "n-or01", "n-or02a", "n-or02b", "n-or03")
    },
}
ANCHOR_KEYS = {YRD_ANCHOR, BEIJING_ANCHOR}

# common, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        573,
        10,
        "765a51771712956a9c9286f53a4534e377b097fa3baab7cac1a193430af2a0ce",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        327,
        1,
        "78448b221eedc7bbb1c901a89aa4f710e9daeb0e2c95e85f715966f200470d4a",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        449,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        299,
        8,
        "6acc40bae19d1dfd88a2667a1d8fa13f58a8c6e34cff9bfa1146642b597e6fa5",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        221,
        1,
        "c88cb27d78b762806b3f9e969d953cb4f6adee7aa4ac9b43cf3342ad54b9d1f5",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "resolution_candidates.csv": (
        4,
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
}

FORBIDDEN_PATH_FRAGMENTS = (
    *EXCLUDED_V2_INPUTS,
    *EXCLUDED_V2_TEST,
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
    "construction_maps/2026-07-20-public-open-v18",
    "construction_master/2026-07-20-public-open-v18",
    "construction-map-2026-07-20-public-open-v18.json",
    "construction-master-2026-07-20-public-open-v18.json",
    "construction_maps/2026-07-20-public-open-v19",
    "construction_master/2026-07-20-public-open-v19",
    "construction-map-2026-07-20-public-open-v19.json",
    "construction-master-2026-07-20-public-open-v19.json",
    "sources/current-coverage-2026-07-20-v14.json",
    "current_coverage_ledgers/2026-07-20-v14",
)
FORBIDDEN_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        *FORBIDDEN_PATH_FRAGMENTS,
        *EXCLUDED_V2_INPUTS.values(),
        *EXCLUDED_V2_TEST.values(),
        *EXCLUDED_V2_CAMPUS_KEYS,
        *EXCLUDED_V2_PROJECT_KEYS,
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


class OpenSeedV45Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v45 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def forbidden(path: Path) -> bool:
            rendered = path.resolve().as_posix()
            return any(marker in rendered for marker in FORBIDDEN_PATH_FRAGMENTS)

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v45 attempted forbidden input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if forbidden(path):
                raise AssertionError(f"v45 attempted forbidden input access: {path}")
            return original_read_text(path, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(Path, "read_bytes", new=guarded_read_bytes)
            )
            stack.enter_context(
                patch.object(Path, "read_text", new=guarded_read_text)
            )
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=offline))
            return validate_open_seed_release(DEFINITION, RELEASE)

    def test_exact_pins_double_offline_reproduction_and_frozen_bundle(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256
        )
        for relative, expected in CODE_HASHES.items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)
        for relative, expected in TEST_HASHES.items():
            self.assertEqual(sha256(ROOT / relative), expected, relative)

        self.assertTrue(DEFINITION.is_file())
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertTrue(RELEASE.is_dir())
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
        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 583)
        self.assertEqual(first["entities_by_kind"], {"campus": 314, "project": 269})
        self.assertEqual(first["evidence_records"], 328)
        self.assertEqual(first["capacity_estimates"], 449)
        self.assertEqual(first["construction_pipeline_records"], 307)
        self.assertEqual(first["construction_source_signals"], 222)
        self.assertEqual(first["resolution_candidates"], 4)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in FORBIDDEN_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_is_exact_v44_plus_eight_and_chronology_is_strict(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current_raw = DEFINITION.read_bytes()
        current = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current))

        base_pins = {
            record["path"]: record["sha256"] for record in base["curated_inputs"]
        }
        current_pins = {
            record["path"]: record["sha256"]
            for record in current["curated_inputs"]
        }
        self.assertEqual(len(base_pins), 269)
        self.assertEqual(len(current_pins), 277)
        self.assertEqual(
            {
                path: digest
                for path, digest in current_pins.items()
                if path not in base_pins
            },
            ADDED_INPUTS,
        )
        self.assertFalse(set(base_pins) - set(current_pins))
        self.assertEqual(
            {
                path
                for path in base_pins
                if base_pins[path] != current_pins[path]
            },
            set(),
        )
        ordered = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered, sorted(set(ordered)))
        self.assertTrue(set(EXCLUDED_V2_INPUTS).isdisjoint(current_pins))

        retrieved_at: list[str] = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            timestamps = [row["retrieved_at"] for row in document.get("evidence", [])]
            if relative in ADDED_INPUTS:
                self.assertEqual(set(timestamps), {VNET_RETRIEVED_AT})
            retrieved_at.extend(timestamps)

        self.assertEqual(max(retrieved_at), MAX_INPUT_RETRIEVED_AT)
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertGreater(
            cutoff,
            datetime.fromisoformat(MAX_INPUT_RETRIEVED_AT.replace("Z", "+00:00")),
        )
        self.assertTrue(
            all(
                datetime.fromisoformat(value.replace("Z", "+00:00")) < cutoff
                for value in retrieved_at
            )
        )
        self.assertEqual(
            current["build"],
            {"as_of": "2026-07-20", "recorded_at": RECORDED_AT},
        )
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v45")
        self.assertEqual(current["publication_contract_version"], 4)
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(current[key], base[key], key)

        manifest_raw = (RELEASE / "manifest.json").read_bytes()
        manifest = json.loads(manifest_raw)
        expected_release = {
            key: value for key, value in manifest.items() if key != "files"
        }
        expected_release["manifest_sha256"] = hashlib.sha256(
            manifest_raw
        ).hexdigest()
        self.assertEqual(current["expected_release"], expected_release)
        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(
            current["expected_summary"],
            {
                "entities_by_status": summary["entities_by_status"],
                "entities_total": summary["entities_total"],
                "evidence_total": summary["evidence_total"],
                "projects_total": summary["projects_total"],
            },
        )

    def test_exact_v44_to_v45_additive_release_delta(self) -> None:
        for filename, (
            common_count,
            added_count,
            added_sha256,
            removed_count,
            removed_sha256,
        ) in CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            added = normalized_counter_rows(after - before)
            removed = normalized_counter_rows(before - after)
            self.assertEqual(sum((before & after).values()), common_count, filename)
            self.assertEqual(len(added), added_count, filename)
            self.assertEqual(canonical_hash(added), added_sha256, filename)
            self.assertEqual(len(removed), removed_count, filename)
            self.assertEqual(canonical_hash(removed), removed_sha256, filename)

        for filename in ("capacity_estimates.csv", "resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
                filename,
            )

        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        self.assertEqual(set(after_entities) - set(before_entities), ANCHOR_KEYS | PROJECT_KEYS)
        self.assertFalse(set(before_entities) - set(after_entities))
        self.assertFalse(
            {
                key
                for key in set(before_entities) & set(after_entities)
                if before_entities[key] != after_entities[key]
            }
        )

        before_pipeline = by_key(BASE_RELEASE / "construction_pipeline.csv", "stable_key")
        after_pipeline = by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        self.assertEqual(set(after_pipeline) - set(before_pipeline), PROJECT_KEYS)
        self.assertFalse(set(before_pipeline) - set(after_pipeline))
        self.assertFalse(
            {
                key
                for key in set(before_pipeline) & set(after_pipeline)
                if before_pipeline[key] != after_pipeline[key]
            }
        )

        before_signals = by_key(
            BASE_RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        after_signals = by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        self.assertEqual(
            set(after_signals) - set(before_signals), {VNET_EVIDENCE_ID}
        )
        self.assertFalse(set(before_signals) - set(after_signals))
        self.assertFalse(
            {
                key
                for key in set(before_signals) & set(after_signals)
                if before_signals[key] != after_signals[key]
            }
        )

    def test_vnet_semantics_are_exact_and_create_no_inferred_claims(self) -> None:
        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        added = {
            key: after_entities[key]
            for key in set(after_entities) - set(before_entities)
        }
        self.assertEqual(
            Counter(row["entity_kind"] for row in added.values()),
            {"campus": 2, "project": 8},
        )
        self.assertEqual(
            Counter(row["status"] for row in added.values()),
            {"": 2, "under_construction": 8},
        )

        for key, row in added.items():
            self.assertEqual(row["country"], "China")
            self.assertIn(
                row["address"],
                {"Yangtze River Delta, China", "Greater Beijing Area, China"},
            )
            for field in (
                "latitude",
                "longitude",
                "owner",
                "operator",
                "users",
                "tenants",
                "customers",
            ):
                self.assertEqual(row[field], "", (key, field))
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["capacity_estimates_json"], "[]")
            self.assertEqual(row["snapshot_as_of"], "2026-03-31")
            self.assertEqual(row["snapshot_evidence_id"], VNET_EVIDENCE_ID)
            self.assertEqual(row["source_retrieved_at"], VNET_RETRIEVED_AT)
            self.assertNotIn("role:", row["tags_json"])
            if key in ANCHOR_KEYS:
                self.assertEqual(row["status"], "")
                self.assertEqual(row["operating_model"], "")
            else:
                self.assertEqual(row["status"], "under_construction")
                self.assertEqual(
                    row["status_method"],
                    "authoritative_physical_status_update",
                )
                self.assertEqual(row["operating_model"], "wholesale_colocation")
                self.assertEqual(row["status_evidence_id"], VNET_EVIDENCE_ID)
                self.assertEqual(
                    row["operating_model_evidence_id"], VNET_EVIDENCE_ID
                )

        evidence_before = by_key(BASE_RELEASE / "evidence.csv", "evidence_id")
        evidence_after = by_key(RELEASE / "evidence.csv", "evidence_id")
        self.assertEqual(set(evidence_after) - set(evidence_before), {VNET_EVIDENCE_ID})
        evidence = evidence_after[VNET_EVIDENCE_ID]
        self.assertEqual(evidence["source_family"], "vnet_investor_relations")
        self.assertEqual(evidence["retrieved_at"], VNET_RETRIEVED_AT)
        self.assertEqual(
            evidence["content_hash"],
            "02ffcae20b92eefb1d8f70fbd6eb15f1b0213eb356713cac23b676c0b10cea0a",
        )

        signals = by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        signal = signals[VNET_EVIDENCE_ID]
        self.assertEqual(signal["affected_entity_count"], "8")
        affected = json.loads(signal["affected_entities_json"])
        self.assertEqual({row["stable_key"] for row in affected}, PROJECT_KEYS)

        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(document["project"]["roles"], {})
            self.assertIsNone(document["campus"]["coordinates"])
            self.assertIsNone(document["project"]["coordinates"])
            self.assertIsNone(document["campus"]["geometry"])
            self.assertIsNone(document["project"]["geometry"])
            self.assertEqual(document["evidence"][0]["key"], VNET_EVIDENCE_KEY)
            metadata = document["evidence"][0]["metadata"]
            self.assertIn("no normalized capacity rows", metadata["capacity_guardrail"])
            self.assertIn("annual energy", metadata["capacity_guardrail"])
            self.assertIn("PUE", metadata["capacity_guardrail"])
            self.assertIn("non-geographic grouping anchors", metadata["site_count_guardrail"])
            self.assertIn("not verified unique physical sites", metadata["site_count_guardrail"])
            self.assertIn("no city, province", metadata["locality_guardrail"])

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_current"], 449)
        self.assertNotIn("capacity_base_totals", summary)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])


if __name__ == "__main__":
    unittest.main()
