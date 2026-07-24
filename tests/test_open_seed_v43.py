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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v43.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v43"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v42.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v42"

DEFINITION_SHA256 = "3b789babfbaaad54166bb7b94305c24258644bec239dd76dcf19186fdd56d6fa"
MANIFEST_SHA256 = "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537"
BASE_DEFINITION_SHA256 = (
    "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
)
BASE_MANIFEST_SHA256 = (
    "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680"
)
RECORDED_AT = "2026-07-20T06:41:44Z"
MAX_INPUT_RETRIEVED_AT = "2026-07-20T06:14:45Z"

CODE_HASHES = {
    "datacenter_atlas/curated.py": "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12",
    "datacenter_atlas/open_seed_release.py": "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
    "datacenter_atlas/publication_release.py": "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510",
    "datacenter_atlas/release.py": "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056",
    "datacenter_atlas/release_contract_v4.py": "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169",
    "scripts/build_open_seed.py": "0603c8025ea4dc77866c9cb913ffbe9d8c9db2dbfda87ecc446732258d6732a8",
}

TEST_HASHES = {
    "tests/test_curated_airtrunk_gtpl_current.py": "e1821b0090cdd5a0e6dd3750f3fd7fb17112907b135b9933d0b03336cd03395c",
    "tests/test_curated_avaio_taurus.py": "51a972fc2d695d54bbb02f513c40b87b91a74c946aef4a7f751c103d674c3dc7",
    "tests/test_curated_compass_current.py": "b07b587090fa443b5b4140dd7af68c1b0d934685e0cb7be1850a80431cf33e6f",
    "tests/test_curated_creekstone_delta.py": "216d81efde95c384f70fb8af7aebfad89da630938f9a7f7e8dc25466ba35a1df",
    "tests/test_curated_edgecore_ashburn.py": "f48a1d7a15e48b27500c00f66c9d679cd7fb82f5db1e9397f0fcbb0f9dd200c9",
    "tests/test_curated_july_primary_builds_20260720.py": "b307cea28987fbb2dd46300bd7b44bd56c063544d883eb10ffed6255cfb5b156",
    "tests/test_curated_microsoft_alviso.py": "3179265546e8180a0f3b2823677a42fb1943a3df5d53380a1b86cd538c0bac5d",
    "tests/test_curated_ntt_current_construction_20260720.py": "4025c4d3f03e8051a35718ebac3a53080d0fcc59a54273237648969a4e4e7747",
    "tests/test_curated_xai_southaven.py": "c1d9cffc578d4a6a42c757beffc1d39058ffe2a6d04638c1a3f73489f03e4dd3",
    "tests/test_open_seed_release.py": "392b806639033497b7c9f43f577cce2e18864c2710fb9d6c393191d1f924e05e",
    "tests/test_release.py": "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243",
    "tests/test_release_contract_v4.py": "7bc3c7d31576bd18597b1792f067abc018540e94b30ba960ef4e990828353ebd",
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-airtrunk-jhb2-johor-fy25-snapshot.json": "1d713d6ac099df709e8d2fabc829aabda2cde785b338dd9e5b819fed4d5c31fe",
    "sources/curated-official-2026-07-20-airtrunk-sgp2-singapore-fy25-snapshot.json": "1343933e14031729e8dc75b52f1bb210becdb752d27e6c26f47267cc6852e8c0",
    "sources/curated-official-2026-07-20-airtrunk-tok1-east-tokyo-expansion.json": "1ac18a7d097fe869a9ad6489bdb5ce26cc8e16d9579d506f497368a4f3bcf28b",
    "sources/curated-official-2026-07-20-avaio-taurus-brandon.json": "b5f56dba59f31af34355fe694d9c9a55e3120545d790dced23310d8676964b35",
    "sources/curated-official-2026-07-20-aws-bharat-future-city-groundbreaking.json": "6080fbf53e1921321f5c03c25975c2d5adfb3d827d7891b08bff4585d9231a68",
    "sources/curated-official-2026-07-20-compass-meridian-current-development.json": "a964e25a27f719b9533727dfa09732295a25379ace88c6acc688bde0772abec4",
    "sources/curated-official-2026-07-20-compass-red-oak-current-development.json": "f6ca71ac9267b43124a86f7550d33453e25e0ba129cfb70ba35d008903462dc5",
    "sources/curated-official-2026-07-20-creekstone-delta-gigasite.json": "9fa05e548c624f96ed3d6c5bfbf51681e05fdfc6483df7f10b2b9c110338da90",
    "sources/curated-official-2026-07-20-edgecore-as01-sterling.json": "dd9b10b617ece6c59d5e50c3fc01ba43590656b33d44688d84d7f90a3c53efca",
    "sources/curated-official-2026-07-20-edgecore-as02-sterling.json": "ffbb3fe0340194e909fd443478bca2fe79009d686784e78847d7a41c441329f9",
    "sources/curated-official-2026-07-20-edged-council-bluffs-first-data-center.json": "d65f65e715c84fd6f93d6d248811c6a83258714a65244b6130e90c2ee77f5117",
    "sources/curated-official-2026-07-20-equinix-mu4-munich-phase-3-topout.json": "87caf33997afbd8663486511815a141e6c7cb18d59ee5951648a21d3591a27d2",
    "sources/curated-official-2026-07-20-gramercy-techpark-lbom-12-airoli.json": "33398c938ab31a27277d33d4c03d5de90f1d19127d0eb1e705641212e817c7dc",
    "sources/curated-official-2026-07-20-microsoft-alviso-phase-2.json": "7dcd5b73ffe64319c234c16a1db94e0e883096663396eae55a071f626b6bca3a",
    "sources/curated-official-2026-07-20-ntt-chicago-ch3.json": "c916fc71ee91607a03311bc5c79f97725efcd96191cc8f888f4944e4e3f827a6",
    "sources/curated-official-2026-07-20-ntt-chicago-ch4.json": "5f3ba11a811756dd5c23a807a6c3c95900dd094e243523fe5f9ed36104713684",
    "sources/curated-official-2026-07-20-ntt-jkt2a-jakarta.json": "2b81b1691bf156daff98ed34d70a7a8d0556735258a280f97019d34c4029c49b",
    "sources/curated-official-2026-07-20-ntt-osk12-osaka-north-1.json": "5ee8cfd9eeadfd4e6e060ecf6faf1628a6985afb7f525a6c587ba48011b9f99d",
    "sources/curated-official-2026-07-20-ntt-tky11-building-1.json": "a11feea3140972e4078666f07341da0a68bbbf9f3b79f87258ae40621cee1744",
    "sources/curated-official-2026-07-20-ntt-tky11-building-2.json": "4d6e2798abf59e471fce731615b821bbff85a3c96aa82751b978b8453f6f7886",
    "sources/curated-official-2026-07-20-ntt-tx4-dallas.json": "10ffafeb8dd80d4ee40394e4edbc9ae422d5972f68823cbfe738a1c1e8d170d3",
    "sources/curated-official-2026-07-20-qts-hall-county-proposed-campus.json": "cbbd00b617cc0150cf6ad5b5ce70f12c7e108f7aed78067a18b11a6a1cb92ea5",
    "sources/curated-official-2026-07-20-xai-macrohardrr-southaven.json": "deff762efb7c40a89e783f779a932bfc71843ce2b216371685eb980999714ec2",
}

# common, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        500,
        44,
        "080d1e76feba1ee2e8548188ab24f5f77c714c02a73461d1dec92391e38a542f",
        2,
        "1d43f49b5abde3db5d1ad095009d311fa1261a7f81f908d72bc9326db7b12c1c",
    ),
    "construction_pipeline.csv": (
        261,
        23,
        "5ff37289f5d24fae71620a9138374ebea468114c8c9ac88204466f66585b54df",
        1,
        "21313999a0a6b199386b220344c4895f8bbbb0c0a47e4d0fab50d087ef3a900d",
    ),
    "evidence.csv": (
        273,
        35,
        "a58374b829198add8287d2bba1788999ba2061a691368ea4a560141ba3a7a6ff",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        427,
        14,
        "c4e52c8dcfd6349d035ad760a16537d9280cb7197b3697bae4bae5e975b838af",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        186,
        22,
        "5acc400ead2ca33245f988676baee8416ea73996e812edfa8c72847d330908fd",
        1,
        "7ccbf47977e3b3d30852f71444ae71b81dce4a913aa36a036ddc75f6159ef005",
    ),
}

MU4_CAMPUS = "curated:equinix-mu4-munich-data-center"
MU4_PROJECT = MU4_CAMPUS + ":phase-3"
MU4_OLD_EVIDENCE_ID = "d87464cc-342f-51c8-a25b-5963e5eca708"
MU4_NEW_EVIDENCE_ID = "4302b7fb-1bf4-5dc7-abf5-9ba24f4556fa"

REJECTED_INPUTS = {
    "sources/curated-official-2026-07-20-hyperco-dayone-koria.json": (
        "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63"
    ),
    "sources/curated-official-2026-07-20-teraco-jb7-isando.json": (
        "d76b0a162d7894e0738a39feb4505a5460e28b86cc2f7daa4deb9f9e00cf7092"
    ),
}
REJECTED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        "curated-official-2026-07-20-hyperco-dayone-koria.json",
        "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63",
        "curated-official-2026-07-20-teraco-jb7-isando.json",
        "d76b0a162d7894e0738a39feb4505a5460e28b86cc2f7daa4deb9f9e00cf7092",
        "curated:teraco-isando-campus",
        "teraco-jb7-construction-commencement-2024-11-13-captured-2026-07-20",
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


def canonical_source_json(document: object) -> bytes:
    return (
        json.dumps(document, indent=2, ensure_ascii=False) + "\n"
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


class OpenSeedV43Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v43 validation attempted network access")
        rejected = {(ROOT / relative).resolve() for relative in REJECTED_INPUTS}
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def guarded_read_bytes(path: Path) -> bytes:
            if path.resolve() in rejected:
                raise AssertionError(f"v43 attempted rejected input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in rejected:
                raise AssertionError(f"v43 attempted rejected input access: {path}")
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
            sha256(BASE_RELEASE / "manifest.json"),
            BASE_MANIFEST_SHA256,
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
        self.assertEqual(
            {path.name: path.read_bytes() for path in entries},
            frozen,
        )
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 544)
        self.assertEqual(first["entities_by_kind"], {"campus": 298, "project": 246})
        self.assertEqual(first["evidence_records"], 308)
        self.assertEqual(first["capacity_estimates"], 441)
        self.assertEqual(first["construction_pipeline_records"], 284)
        self.assertEqual(first["construction_source_signals"], 208)
        self.assertEqual(first["resolution_candidates"], 4)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in REJECTED_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_is_exact_v42_plus_23_and_timestamps_are_bounded(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current_raw = DEFINITION.read_bytes()
        current = json.loads(current_raw)
        self.assertEqual(current_raw, canonical_json(current))

        base_pins = {
            record["path"]: record["sha256"] for record in base["curated_inputs"]
        }
        current_pins = {
            record["path"]: record["sha256"] for record in current["curated_inputs"]
        }
        self.assertEqual(len(base_pins), 230)
        self.assertEqual(len(current_pins), 253)
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
        self.assertTrue(set(REJECTED_INPUTS).isdisjoint(current_pins))

        retrieved_at: list[str] = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            if relative in ADDED_INPUTS:
                self.assertEqual(path.read_bytes(), canonical_source_json(document))
            for evidence in document.get("evidence", []):
                retrieved_at.append(evidence["retrieved_at"])

        self.assertEqual(max(retrieved_at), MAX_INPUT_RETRIEVED_AT)
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertTrue(
            all(
                datetime.fromisoformat(value.replace("Z", "+00:00")) <= cutoff
                for value in retrieved_at
            )
        )
        self.assertEqual(
            current["build"],
            {"as_of": "2026-07-20", "recorded_at": RECORDED_AT},
        )
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v43")
        self.assertEqual(current["publication_contract_version"], 4)
        self.assertEqual(current["epoch_capture"], base["epoch_capture"])
        self.assertEqual(
            current["expected_epoch_result"],
            base["expected_epoch_result"],
        )
        self.assertEqual(current["scope"], base["scope"])

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

    def test_exact_v42_to_v43_csv_delta_and_temporal_replacement(self) -> None:
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

        for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
                filename,
            )

        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        self.assertEqual(set(before_entities) - set(after_entities), set())
        self.assertEqual(len(set(after_entities) - set(before_entities)), 42)
        self.assertEqual(
            {
                key
                for key in set(before_entities) & set(after_entities)
                if before_entities[key] != after_entities[key]
            },
            {MU4_CAMPUS, MU4_PROJECT},
        )
        self.assertEqual(
            after_entities[MU4_CAMPUS]["snapshot_as_of"],
            "2026-07-16",
        )
        self.assertEqual(after_entities[MU4_PROJECT]["status"], "shell")
        self.assertEqual(
            after_entities[MU4_PROJECT]["status_as_of"],
            "2026-07-16",
        )
        self.assertEqual(
            after_entities[MU4_PROJECT]["status_evidence_id"],
            MU4_NEW_EVIDENCE_ID,
        )

        before_pipeline = by_key(
            BASE_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        after_pipeline = by_key(
            RELEASE / "construction_pipeline.csv", "stable_key"
        )
        self.assertEqual(set(before_pipeline) - set(after_pipeline), set())
        self.assertEqual(len(set(after_pipeline) - set(before_pipeline)), 22)
        self.assertEqual(
            {
                key
                for key in set(before_pipeline) & set(after_pipeline)
                if before_pipeline[key] != after_pipeline[key]
            },
            {MU4_PROJECT},
        )

        before_signals = by_key(
            BASE_RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        after_signals = by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        self.assertEqual(set(before_signals) - set(after_signals), set())
        self.assertEqual(len(set(after_signals) - set(before_signals)), 21)
        self.assertEqual(
            {
                key
                for key in set(before_signals) & set(after_signals)
                if before_signals[key] != after_signals[key]
            },
            {MU4_OLD_EVIDENCE_ID},
        )
        old_signal = before_signals[MU4_OLD_EVIDENCE_ID]
        current_signal = after_signals[MU4_OLD_EVIDENCE_ID]
        self.assertEqual(old_signal["affected_entity_count"], "12")
        self.assertEqual(current_signal["affected_entity_count"], "11")
        self.assertIn(MU4_PROJECT, old_signal["affected_entities_json"])
        self.assertNotIn(MU4_PROJECT, current_signal["affected_entities_json"])

    def test_added_release_semantics_and_nonaggregation_guardrails(self) -> None:
        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        added_entities = [
            after_entities[key]
            for key in set(after_entities) - set(before_entities)
        ]
        self.assertEqual(
            Counter(row["entity_kind"] for row in added_entities),
            {"campus": 20, "project": 22},
        )
        self.assertEqual(
            Counter(row["status"] for row in added_entities),
            {
                "": 20,
                "announced": 1,
                "proposed": 1,
                "shell": 2,
                "under_construction": 18,
            },
        )

        before_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        after_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        entity_keys = {
            row["entity_id"]: row["stable_key"]
            for row in rows(RELEASE / "entities.csv")
        }
        added_capacity = [
            dict(packed) for packed in (after_capacity - before_capacity).elements()
        ]
        observed_capacity = {
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
            observed_capacity,
            {
                ("curated:avaio-taurus-brandon-mississippi-campus", "generation_nameplate_mw", "planned", "500.0", "MW", "2026-07-20"),
                ("curated:avaio-taurus-brandon-mississippi-campus", "grid_connection_mw", "contracted", "116.0", "MW", "2026-07-20"),
                ("curated:avaio-taurus-brandon-mississippi-campus", "grid_connection_mw", "planned", "536.0", "MW", "2026-07-20"),
                ("curated:compass-meridian-mississippi-data-center-campus", "grid_connection_mw", "planned", "500.0", "MW", "2025-01-09"),
                ("curated:edged-council-bluffs-data-center-campus", "critical_it_mw", "planned", "200.0", "MW", "2025-10-29"),
                ("curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development", "critical_it_mw", "planned", "48.0", "MW", "2026-06-10"),
                ("curated:ntt-dallas-data-center-campus:tx4", "critical_it_mw", "planned", "36.0", "MW", "2026-07-20"),
                ("curated:ntt-itasca-data-center-campus:ch3", "critical_it_mw", "planned", "32.0", "MW", "2026-07-20"),
                ("curated:ntt-jakarta-2-campus:jkt2a-annex", "critical_it_mw", "planned", "12.0", "MW", "2026-07-20"),
                ("curated:ntt-osk12-osaka-north-1-campus", "critical_it_mw", "planned", "36.0", "MW", "2026-07-20"),
                ("curated:ntt-osk12-osaka-north-1-campus:building-1", "critical_it_mw", "planned", "18.0", "MW", "2026-07-20"),
                ("curated:ntt-tky11-shiroi-1-campus", "critical_it_mw", "planned", "50.0", "MW", "2026-07-20"),
                ("curated:ntt-tky11-shiroi-1-campus:building-1", "critical_it_mw", "planned", "24.0", "MW", "2026-07-20"),
                ("curated:ntt-tky11-shiroi-1-campus:building-2", "critical_it_mw", "planned", "26.0", "MW", "2026-07-20"),
            },
        )
        self.assertEqual(len(added_capacity), 14)
        capacity_entities = {row[0] for row in observed_capacity}
        for excluded_prefix in (
            "curated:creekstone-delta-gigasite",
            "curated:edgecore-as01",
            "curated:edgecore-as02",
        ):
            self.assertFalse(
                any(key.startswith(excluded_prefix) for key in capacity_entities)
            )

        base_inputs = json.loads(
            (BASE_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        current_inputs = json.loads(
            (RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        base_epoch = [
            row for row in base_inputs if row["source_family"] == "epoch_ai_data_centers"
        ]
        current_epoch = [
            row
            for row in current_inputs
            if row["source_family"] == "epoch_ai_data_centers"
        ]
        self.assertEqual(current_epoch, base_epoch)
        self.assertEqual(len(current_epoch), 1)

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertNotIn("capacity_base_totals", summary)
        self.assertEqual(summary["capacity_estimates_current"], 441)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)


if __name__ == "__main__":
    unittest.main()

